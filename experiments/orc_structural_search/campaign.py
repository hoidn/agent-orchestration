"""Cumulative search campaigns: the persistent evidence store, C1 identities, exposure on actual use, the
campaign-scoped candidate set, idempotent ingestion, dispositions, estimates and the campaign checkpoint.

Design: docs/design/orc_structural_search_cumulative_campaigns.md ("Identities", "Persistent Evidence Store",
"Campaign Protocol", "Estimates And Attribution"). The store root S (outside every work, evidence and pools root
and the main checkout prefix) holds S/evidence.jsonl (append-only `campaign-evidence-v1` rows, `seq` = line
number; indexes are rebuilt from them on every call), S/.lock (one writer process), S/candidates/<candidate_id>/
(driver.archive) and S/campaigns/<campaign_id>/checkpoint.json (replaced atomically). Run records are referenced
by path; dispositions supersede and nothing is deleted. Estimates pool every trial of equal `context_key` across
campaigns; the candidate set a campaign selects from is its own (campaign_candidates).
"""

import fcntl
import hashlib
import json
import os
import re
from collections import defaultdict, namedtuple
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, stdev
from typing import TextIO

from experiments.compare import repos
from experiments.orc_structural_search import driver, pricing, scoring
from experiments.orc_structural_search.config import check_criterion_hashes
from experiments.orc_structural_search.quota import job_key
from experiments.orc_structural_search.records import UNAVAILABLE, append_record, read_records

SCHEMA, CHECKPOINT, LOG = "campaign-evidence-v1", "campaign-checkpoint-v1", "evidence.jsonl"
ESTIMATOR_VERSION = "campaign-estimate-1"
WARM_START = "warm_start"  # the policy of a context's shared warm-start campaign
ROLES = ("adaptive", "validation", "sealed")
FORBIDDEN = {"adaptive": {"sealed"}, "validation": {"adaptive", "sealed"},  # prior exposures that refuse a role
             "sealed": {"adaptive", "validation", "sealed"}}
DISPOSITIONS = ("contaminated", "invalidated", "superseded", "frozen", "sealed_opened")
REQUIRED = {kind: fields.split() for kind, fields in {  # the fields every row of a kind carries
    "campaign": "campaign_id label context_key criterion_sha256 policy parameters budget seeds run_seed warm_start "
                "declared_roles roots",
    "subject": "candidate_id parent source skeleton policies idea_key descriptor campaign_id",
    "trial": "trial_id origin_trial_id campaign_id context_key evaluation_id run_id attempt candidate_id task "
             "replicate outcome records_dir",
    "assessment": "trial_id results clone_ids task outcome value criterion_sha256 proof_sha256 split",
    "disposition": "target_kind target_id disposition reason supersedes",
    "exposure": "package_sha256 role campaign_id criterion_sha256"}.items()}
CHECKPOINT_KEYS = ("generation", "frontier", "reservoir", "rng_state", "ingestion_position", "ledger_index",
                   "futility_streak", "budget", "stopped")

# {trial_id: latest trial}, {trial_id: [assessment]}, {target_id: [disposition]}, {package_sha256: exposure}
Index = namedtuple("Index", "trials assessments dispositions exposure")


def _sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def context_key(criterion: Mapping, *, package_digests: Mapping[str, str], runtime_commit: str,
                evaluator_version: str) -> str:
    """`ctx1:` + sha256 over the criterion-frozen context: adaptive package digests, the loaded criterion's
    `criterion_sha256`, runtime commit, evaluator version, the criterion's `envelope` and `model_policy`."""
    return "ctx1:" + _sha({"packages": dict(package_digests), "criterion_sha256": criterion["criterion_sha256"],
                           "runtime_commit": runtime_commit, "evaluator_version": evaluator_version,
                           "envelope": criterion["envelope"], "model_policy": criterion["model_policy"]})


def trial_id(campaign_id: str, run_id: str, evaluation_id: str, attempt: int) -> str:
    return "trial:" + _sha([campaign_id, run_id, evaluation_id, attempt])


def campaign_label(label: str) -> str:
    if not re.fullmatch(r"[a-z0-9-]{1,32}", label):
        raise ValueError(f"campaign label {label!r} must match [a-z0-9-]{{1,32}}")
    return label


def main_prefix() -> Path:
    return repos.main_checkout(Path(__file__).resolve().parents[2])


def check_roots(root: Path, roots) -> None:
    for other in (Path(path).resolve() for path in roots):
        if root.is_relative_to(other) or other.is_relative_to(root):
            raise ValueError(f"the store root {root} and the campaign root {other} must not nest")


def check_row(row, number: int) -> None:
    if not isinstance(row, dict) or (row.get("schema"), row.get("seq")) != (SCHEMA, number) \
            or row.get("kind") not in REQUIRED:
        raise ValueError(f"line {number}: not a {SCHEMA} row of a known kind with seq {number}: {str(row)[:200]}")
    if missing := [key for key in REQUIRED[row["kind"]] if key not in row]:
        raise ValueError(f"line {number}: the {row['kind']} row lacks {missing}")


def _load(log: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(log.read_text(encoding="utf-8").splitlines(), 1):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"{log}: line {number}: malformed JSON: {error}") from error
        check_row(rows[-1], number)
    return rows


@dataclass
class Store:
    root: Path
    _rows: list[dict]
    _lock: TextIO | None = None

    @property
    def writer(self) -> bool:
        return self._lock is not None

    def append(self, record: Mapping) -> int:
        if self._lock is None:
            raise PermissionError(f"the store {self.root} is open read-only")
        row = json.loads(json.dumps({**record, "schema": SCHEMA, "seq": len(self._rows) + 1}))
        check_row(row, row["seq"])
        append_record(self.root / LOG, row)
        self._rows.append(row)
        return row["seq"]

    def rows(self, kind: str | None = None) -> list[dict]:
        return [row for row in self._rows if kind is None or row["kind"] == kind]

    def index(self) -> Index:
        assessments, dispositions, exposures = defaultdict(list), defaultdict(list), {}
        for row in self.rows("assessment"):
            assessments[row["trial_id"]].append(row)
        for row in self.rows("disposition"):
            dispositions[row["target_id"]].append(row)
        for row in self.rows("exposure"):
            entry = exposures.setdefault(row["package_sha256"], {"roles": set(), "campaigns": []})
            entry["roles"].add(row["role"])
            if row["campaign_id"] not in entry["campaigns"]:
                entry["campaigns"].append(row["campaign_id"])
        trials = {row["trial_id"]: row for row in self.rows("trial")}
        return Index(trials, dict(assessments), dict(dispositions), exposures)

    def close(self) -> None:
        if self._lock is not None:
            self._lock.close()
            self._lock = None


def _writer_lock(root: Path) -> TextIO:
    root.mkdir(parents=True, exist_ok=True)
    (root / LOG).touch()
    handle = (root / ".lock").open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        handle.close()
        raise RuntimeError(f"another writer holds {root / '.lock'}") from error
    return handle


def open_store(root: Path, *, writer: bool) -> Store:
    """The store at `root`, every row validated; refuses a root under the main checkout prefix or nested with a
    recorded campaign's roots, a second writer and a malformed file."""
    root = Path(root).resolve()
    repos.guard(main_prefix(), root)
    repos.visible_in_sandbox(root)
    store = Store(root, [], _writer_lock(root) if writer else None)
    try:
        store._rows = _load(root / LOG)
        for row in store.rows("campaign"):
            check_roots(root, row["roots"].values())
    except BaseException:
        store.close()
        raise
    return store


def _campaign(store: Store, campaign_id: str) -> dict:
    if found := [row for row in store.rows("campaign") if row["campaign_id"] == campaign_id]:
        return found[0]
    raise KeyError(f"no campaign {campaign_id} in {store.root}")


def start_campaign(store: Store, *, label: str, context: str, policy: str, parameters: Mapping, budget: Mapping,
                   seeds: Sequence[str], run_seed: int, warm_start: Sequence[str], declared_roles: Mapping[str, str],
                   roots: Mapping) -> str:
    """Register `<label>-<campaign sequence>` (a `warm_start` campaign, label `warm`, is `warm-<context_key[5:17]>`,
    one per context) and its adaptive exposures; `declared_roles` maps package sha256 to role, `parameters` carry
    `criterion_sha256`. Refuses a reused label, nested roots, foreign warm-start trials and forbidden roles."""
    if policy == WARM_START:
        if label != "warm":
            raise ValueError(f"a warm-start campaign takes the label 'warm', not {label!r}")
        label = f"warm-{context[5:17]}"
    campaigns, label = store.rows("campaign"), campaign_label(label)
    if any(row["label"] == label for row in campaigns):
        raise ValueError(f"the campaign label {label} is already used in {store.root}: a label is never reused")
    check_roots(store.root, roots.values())
    trials = store.index().trials
    if foreign := sorted(t for t in warm_start if t not in trials or trials[t]["context_key"] != context):
        raise ValueError(f"warm-start trials {foreign} are not in the store under context {context}")
    held = {role: [sha for sha, used in declared_roles.items() if used == role] for role in ROLES}
    if set(declared_roles.values()) - set(ROLES) or len(held["validation"]) > 1 or len(held["sealed"]) > 1:
        raise ValueError(f"declared roles {dict(declared_roles)}: roles are {ROLES}, one validation and one sealed")
    check_split_roles(store, adaptive=held["adaptive"], validation=next(iter(held["validation"]), None),
                      sealed=next(iter(held["sealed"]), None))
    campaign_id, criterion_sha256 = f"{label}-{len(campaigns) + 1}", parameters["criterion_sha256"]
    store.append({"kind": "campaign", "campaign_id": campaign_id, "label": label, "context_key": context,
                  "criterion_sha256": criterion_sha256, "policy": policy, "parameters": dict(parameters),
                  "budget": dict(budget), "seeds": list(seeds), "run_seed": run_seed, "warm_start": list(warm_start),
                  "declared_roles": dict(declared_roles), "roots": {k: str(v) for k, v in roots.items()}})
    for package in held["adaptive"]:
        record_exposure(store, package_sha256=package, role="adaptive", campaign_id=campaign_id,
                        criterion_sha256=criterion_sha256)
    return campaign_id


def warm_start_id(store: Store, context: str) -> str | None:
    return next((row["campaign_id"] for row in store.rows("campaign")
                 if row["policy"] == WARM_START and row["context_key"] == context), None)


def campaign_candidates(store: Store, campaign_id: str, *, scheduled: Sequence[Mapping] = ()) -> dict[str, dict]:
    """{candidate_id: subject} of the campaign's initial-evidence candidates, its own evaluated children and the
    `scheduled` subjects, never a sibling campaign's children; the campaign's own registration is preferred."""
    campaign, trials = _campaign(store, campaign_id), store.index().trials
    held = [trials[t]["candidate_id"] for t in campaign["warm_start"]]
    held += [t["candidate_id"] for t in trials.values() if t["campaign_id"] == campaign_id]
    subjects = {}
    for row in store.rows("subject"):
        if row["candidate_id"] not in subjects or row["campaign_id"] == campaign_id:
            subjects[row["candidate_id"]] = row
    if missing := sorted(set(held) - set(subjects)):
        raise ValueError(f"campaign {campaign_id} holds unregistered candidates {missing}")
    return {cid: subjects[cid] for cid in held} | {row["candidate_id"]: dict(row) for row in scheduled}


def register_subject(store: Store, candidate_root: Path, *, runtime: Path, parent: str | None, skeleton: str,
                     policies: frozenset, idea_key: str, descriptor: Mapping, campaign_id: str) -> str:
    """Archive `candidate_root` into S/candidates/ and register it for `campaign_id` once."""
    if not store.writer:
        raise PermissionError(f"the store {store.root} is open read-only")
    _campaign(store, campaign_id)
    cid, dest = driver.archive(Path(candidate_root), store.root, runtime)
    driver.check_archived(dest, repos.runtime_commit(runtime))
    if not any(row["candidate_id"] == cid and row["campaign_id"] == campaign_id for row in store.rows("subject")):
        store.append({"kind": "subject", "candidate_id": cid, "parent": parent, "source": str(dest),
                      "skeleton": skeleton, "policies": sorted(policies), "idea_key": idea_key,
                      "descriptor": dict(descriptor), "campaign_id": campaign_id})
    return cid


def dispose(store: Store, *, target_kind: str, target_id: str, kind: str, reason: str,
            supersedes: Sequence[int] = ()) -> int:
    if target_kind not in ("trial", "campaign") or kind not in DISPOSITIONS:
        raise ValueError(f"disposition {kind!r} of a {target_kind!r}: kinds are {DISPOSITIONS}")
    if target_id not in {row[f"{target_kind}_id"] for row in store.rows(target_kind)}:
        raise KeyError(f"no {target_kind} {target_id} in {store.root}")
    return store.append({"kind": "disposition", "target_kind": target_kind, "target_id": target_id,
                         "disposition": kind, "reason": reason, "supersedes": list(supersedes)})


def record_exposure(store: Store, *, package_sha256: str, role: str, campaign_id: str, criterion_sha256: str) -> int:
    """Written when `role` is actually used; a declared but unused role is no exposure."""
    if role not in ROLES:
        raise ValueError(f"exposure role {role!r} is not one of {ROLES}")
    _campaign(store, campaign_id)
    return store.append({"kind": "exposure", "package_sha256": package_sha256, "role": role,
                         "campaign_id": campaign_id, "criterion_sha256": criterion_sha256})


def exposure(store: Store) -> dict[str, dict]:
    return store.index().exposure


def check_split_roles(store: Store, *, adaptive: Sequence[str], validation: str | None, sealed: str | None) -> None:
    """Refuse a declared role that a prior actual exposure forbids (FORBIDDEN), or a package in two roles."""
    declared = [(sha, "adaptive") for sha in adaptive] + [
        (sha, role) for sha, role in ((validation, "validation"), (sealed, "sealed")) if sha]
    if len({sha for sha, _ in declared}) != len(declared):
        raise ValueError(f"a package is declared in two roles: {declared}")
    prior = exposure(store)
    for sha, role in declared:
        if held := sorted(prior.get(sha, {}).get("roles", set()) & FORBIDDEN[role]):
            raise ValueError(f"package {sha} was exposed as {held} in {prior[sha]['campaigns']}: refused as {role}")


def _trial(row: Mapping, campaign_id: str, context: str) -> dict:
    attempt = row.get("attempt", 1)
    return {"kind": "trial", "trial_id": trial_id(campaign_id, row["run_id"], row["evaluation_id"], attempt),
            "origin_trial_id": None, "campaign_id": campaign_id, "context_key": context, "attempt": attempt,
            "task": row["task_id"], "split": row.get("split", UNAVAILABLE), "generation": row.get("generation"),
            "incidents": row.get("incidents", []), "state_dir": row.get("state_dir"),
            **{key: row[key] for key in ("evaluation_id", "run_id", "candidate_id", "replicate", "outcome",
                                         "records_dir")},
            **{key: row.get(key, UNAVAILABLE) for key in ("provider_calls", "wall_clock_sec", "consumption",
                                                          "receipt_usage")}}


def _add_trials(store: Store, trials: Sequence[dict]) -> int:
    """Append each trial not yet stored or whose log row changed (an incident resumed under its trial id)."""
    stored, added = store.index().trials, 0
    for trial in trials:
        known = stored.get(trial["trial_id"])
        if known is None or {k: v for k, v in known.items() if k not in ("schema", "seq")} != trial:
            store.append(trial)
            added += 1
    return added


def _supersede(store: Store, evaluations: Sequence[Mapping], trials: Mapping[str, dict]) -> int:
    """A `superseded` disposition per attempt a quota relaunch replaced (a later evaluation id of its job)."""
    latest = {job_key(row): row["evaluation_id"] for row in evaluations}
    done = {row["target_id"] for row in store.rows("disposition") if row["disposition"] == "superseded"}
    added = 0
    for row in evaluations:
        tid, current = trials[row["evaluation_id"]]["trial_id"], latest[job_key(row)]
        if current != row["evaluation_id"] and tid not in done:
            dispose(store, target_kind="trial", target_id=tid, kind="superseded",
                    reason=f"quota relaunch: evaluation {current} replaced this attempt")
            done.add(tid)
            added += 1
    return added


def _assess(store: Store, pools: Sequence[tuple[str, dict]], trials: Mapping[str, dict], proof: str | None) -> int:
    seen, added = {(row["trial_id"], row["results"]) for row in store.rows("assessment")}, 0
    for results, pool in pools:
        for row in pool["rows"]:
            trial = trials[row["evaluation_id"]]
            if (trial["trial_id"], results) not in seen:
                store.append({"kind": "assessment", "trial_id": trial["trial_id"], "results": results,
                              "clone_ids": row.get("clone_ids", []), "task": row["task"], "outcome": row["outcome"],
                              "value": row["value"], "hidden": row["hidden"], "split": trial["split"],
                              "criterion_sha256": pool["criterion_sha256"], "proof_sha256": proof})
                seen.add((trial["trial_id"], results))
                added += 1
    return added


def _reject_foreign_original_runs(store: Store, campaign_id: str, trials: Sequence[Mapping]) -> None:
    """A public run already stored as an original belongs to its original campaign; reuse its warm-start id."""
    run_ids = {trial["run_id"] for trial in trials if trial["run_id"] != UNAVAILABLE}
    foreign = next((trial for trial in store.index().trials.values()
                    if trial["origin_trial_id"] is None and trial["campaign_id"] != campaign_id
                    and trial["run_id"] != UNAVAILABLE and trial["run_id"] in run_ids), None)
    if foreign:
        raise ValueError(f"public run {foreign['run_id']} evaluation {foreign['evaluation_id']} attempt "
                         f"{foreign['attempt']} is an original trial in another campaign; reuse its warm-start id")


def ingest(store: Store, campaign_id: str, context: str, evidence_root: Path, pools: Sequence[Path], *,
           criterion: Path) -> dict:
    """One trial per evaluation row of E/log.jsonl (every attempt), one assessment per `scoring.read_pool` row of
    each pool (all read before any append: a refused pool adds nothing), a `superseded` disposition per
    quota-replaced attempt; idempotent by trial_id and (trial_id, results). Counts and the log position."""
    campaign, sha = _campaign(store, campaign_id), repos.sha256_file(criterion)
    if (campaign["context_key"], campaign["criterion_sha256"]) != (context, sha):
        raise ValueError(f"campaign {campaign_id} runs under context {campaign['context_key']} and criterion "
                         f"{campaign['criterion_sha256']}, not {context} and {criterion}'s {sha}")
    log = Path(evidence_root) / "log.jsonl"
    rows = read_records(log)
    evaluations = [row for row in rows if row["kind"] == "evaluation"]
    check_criterion_hashes(evaluations, sha)
    read = [(str(Path(results).resolve()), scoring.read_pool(results, log, criterion)) for results in pools]
    if measure_free := [results for results, pool in read if "rows" not in pool]:
        raise ValueError(f"{measure_free}: a measure-free criterion carries no assessment")
    trials = {row["evaluation_id"]: _trial(row, campaign_id, context) for row in evaluations}  # the latest row
    _reject_foreign_original_runs(store, campaign_id, list(trials.values()))
    proof = json.loads(Path(criterion).read_text())["qualification"]["sha256"] if read else None
    return {"trials": _add_trials(store, list(trials.values())),
            "assessments": _assess(store, read, trials, proof), "superseded": _supersede(store, evaluations, trials),
            "position": len(rows)}


def evidence(store: Store, candidate_id: str, context: str, *, tasks: Sequence[str], price_table: Mapping,
             min_trials: int) -> dict:
    """The observed estimate of `candidate_id` on `tasks` over every non-disposed original trial of equal
    `context`, across campaigns: per-task primary means (failure-inclusive) with n and SD, quality = their
    equal-weight mean when every task has `min_trials`, mean metered cost per trial (unavailable when any is),
    calls and wall clock; `unobserved` without trials, never a score."""
    index, names = store.index(), [Path(task).name for task in tasks]
    attempts = [t for t in index.trials.values() if (t["candidate_id"], t["context_key"]) == (candidate_id, context)
                and t["origin_trial_id"] is None and t["task"] in names]
    excluded = sorted(t["trial_id"] for t in attempts if t["trial_id"] in index.dispositions)
    counted = [t for t in attempts if t["trial_id"] not in excluded]
    result = {"estimator_version": ESTIMATOR_VERSION, "candidate_id": candidate_id, "context_key": context,
              "trial_ids": sorted(t["trial_id"] for t in counted), "trials": len(counted), "attempts": len(attempts),
              "disposed": len(excluded), "excluded": excluded}
    if not counted:
        return result | {"kind": "unobserved", "quality": UNAVAILABLE, "cost": UNAVAILABLE}
    values = {name: [] for name in names}
    for trial in counted:
        assessed = index.assessments.get(trial["trial_id"])
        row = assessed[-1] if assessed else {
            "outcome": scoring.scored_outcome(trial | {"kind": "evaluation", "task_id": trial["task"]}),
            "value": None}
        if (value := scoring.primary_value(row)) is not None:
            values[trial["task"]].append(value)
    per_task = {name: {"n": len(v), "mean": mean(v) if v else UNAVAILABLE,
                       "sd": stdev(v) if len(v) > 1 else "insufficient_support"} for name, v in values.items()}
    supported = all(summary["n"] >= min_trials for summary in per_task.values())
    costs = [pricing.cost(trial, price_table) for trial in counted]
    return result | {
        "kind": "observed", "tasks": per_task, "support": "every_adaptive_task" if supported else "insufficient",
        "quality": mean(summary["mean"] for summary in per_task.values()) if supported else UNAVAILABLE,
        "cost": UNAVAILABLE if UNAVAILABLE in costs else mean(costs),
        "calls": scoring.known_mean([trial["provider_calls"] for trial in counted]),
        "wall_clock_sec": scoring.known_mean([trial["wall_clock_sec"] for trial in counted])}


def _checkpoint(store: Store, campaign_id: str) -> tuple[Path, dict]:
    """The checkpoint path and the identity it must carry (the campaign record's)."""
    campaign = _campaign(store, campaign_id)
    identity = {key: campaign[key] for key in ("campaign_id", "context_key", "criterion_sha256")}
    return store.root / "campaigns" / campaign_id / "checkpoint.json", {"schema": CHECKPOINT, **identity}


def write_checkpoint(store: Store, campaign_id: str, state: Mapping) -> Path:
    """`state` (CHECKPOINT_KEYS) under the campaign's identity, via a temporary file renamed over the last one."""
    if not store.writer:
        raise PermissionError(f"the store {store.root} is open read-only")
    if missing := sorted(set(CHECKPOINT_KEYS) - set(state)):
        raise ValueError(f"checkpoint state lacks {missing}")
    path, identity = _checkpoint(store, campaign_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({**state, **identity}, sort_keys=True) + "\n")
    os.replace(temporary, path)
    return path


def read_checkpoint(store: Store, campaign_id: str) -> dict | None:
    """The campaign's checkpoint or None; refuses one whose identity is not the campaign record's."""
    path, identity = _checkpoint(store, campaign_id)
    if not path.exists():
        return None
    state = json.loads(path.read_text())
    if any(state.get(key) != value for key, value in identity.items()):
        raise ValueError(f"{path} is not a {CHECKPOINT} of campaign {campaign_id} under its context and criterion")
    return state
