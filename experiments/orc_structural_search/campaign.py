"""Cumulative campaigns: persistent evidence, identities, exposures, estimates and checkpoints.

The evidence store is append-only and indexes are rebuilt per call; run records are referenced by path, dispositions
supersede without deletion, and estimates pool equal-context trials while candidate sets remain campaign-scoped.
See docs/design/orc_structural_search_cumulative_campaigns.md for the governing storage and attribution contract.
"""

import hashlib
import json
import os
import re
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from statistics import mean, stdev

from experiments.compare import repos
from experiments.orc_structural_search import driver, pareto_readout, pricing, scoring
from experiments.orc_structural_search.briefs import structural_summary
from experiments.orc_structural_search.config import check_criterion_hashes
from experiments.orc_structural_search.quota import job_key
from experiments.orc_structural_search.pareto import bounded_frontier, reservoir_update, select_parent
from experiments.orc_structural_search.records import (
    CHECKPOINT, CHECKPOINT_KEYS, LOG, SCHEMA, Index, Store, UNAVAILABLE, _checkpoint,
    add_assessments as _assess, add_trials as _add_trials,
    append_record, campaign_candidates, check_roots, check_row, find_campaign as _campaign,
    open_campaign_store as _open_store, read_checkpoint, read_records, trial_id,
    trial_record as _trial, write_checkpoint,
)

ESTIMATOR_VERSION = "campaign-estimate-1"
WARM_START = "warm_start"  # the policy of a context's shared warm-start campaign
ROLES = ("adaptive", "validation", "sealed")
FORBIDDEN = {"adaptive": {"sealed"}, "validation": {"adaptive", "sealed"},  # prior exposures that refuse a role
             "sealed": {"adaptive", "validation", "sealed"}}
DISPOSITIONS = ("contaminated", "invalidated", "superseded", "frozen", "sealed_opened")


def _sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def context_key(criterion: Mapping, *, package_digests: Mapping[str, str], runtime_commit: str,
                evaluator_version: str) -> str:
    """`ctx1:` + sha256 over the criterion-frozen context: adaptive package digests, the loaded criterion's
    `criterion_sha256`, runtime commit, evaluator version, the criterion's `envelope` and `model_policy`."""
    return "ctx1:" + _sha({"packages": dict(package_digests), "criterion_sha256": criterion["criterion_sha256"],
                           "runtime_commit": runtime_commit, "evaluator_version": evaluator_version,
                           "envelope": criterion["envelope"], "model_policy": criterion["model_policy"]})


def campaign_label(label: str) -> str:
    if not re.fullmatch(r"[a-z0-9-]{1,32}", label):
        raise ValueError(f"campaign label {label!r} must match [a-z0-9-]{{1,32}}")
    return label


def main_prefix() -> Path:
    return repos.main_checkout(Path(__file__).resolve().parents[2])


def open_store(root: Path, *, writer: bool) -> Store:
    """The store at `root`, every row validated; refuses a root under the main checkout prefix or nested with a
    recorded campaign's roots, a second writer and a malformed file."""
    return _open_store(root, writer=writer, checkout_prefix=main_prefix())


def _campaign_label_for(store: Store, policy: str, label: str, context: str) -> tuple[list[dict], str]:
    if policy == WARM_START:
        if label != "warm":
            raise ValueError(f"a warm-start campaign takes the label 'warm', not {label!r}")
        label = f"warm-{context[5:17]}"
    campaigns = store.rows("campaign")
    label = campaign_label(label)
    if any(row["label"] == label for row in campaigns):
        raise ValueError(f"the campaign label {label} is already used in {store.root}: a label is never reused")
    return campaigns, label


def start_campaign(store: Store, *, label: str, context: str, policy: str, parameters: Mapping, budget: Mapping,
                   seeds: Sequence[str], run_seed: int, warm_start: Sequence[str], declared_roles: Mapping[str, str],
                   roots: Mapping) -> str:
    """Register `<label>-<campaign sequence>` (a `warm_start` campaign, label `warm`, is `warm-<context_key[5:17]>`,
    one per context) and its adaptive exposures; `declared_roles` maps package sha256 to role, `parameters` carry
    `criterion_sha256`. Refuses a reused label, nested roots, foreign warm-start trials and forbidden roles."""
    campaigns, label = _campaign_label_for(store, policy, label, context)
    check_roots(store.root, roots.values())
    trials = store.index().trials
    if foreign := sorted(t for t in warm_start if t not in trials or trials[t]["context_key"] != context):
        raise ValueError(f"warm-start trials {foreign} are not in the store under context {context}")
    held = _held_roles(store, declared_roles)
    campaign_id, criterion_sha256 = f"{label}-{len(campaigns) + 1}", parameters["criterion_sha256"]
    store.append({"kind": "campaign", "campaign_id": campaign_id, "label": label, "context_key": context,
                  "criterion_sha256": criterion_sha256, "policy": policy, "parameters": dict(parameters),
                  "budget": dict(budget), "seeds": list(seeds), "run_seed": run_seed, "warm_start": list(warm_start),
                  "declared_roles": dict(declared_roles), "roots": {k: str(v) for k, v in roots.items()}})
    for package in held["adaptive"]:
        record_exposure(store, package_sha256=package, role="adaptive", campaign_id=campaign_id,
                        criterion_sha256=criterion_sha256)
    return campaign_id


def _held_roles(store: Store, declared_roles: Mapping[str, str]) -> dict[str, list[str]]:
    held = {role: [sha for sha, used in declared_roles.items() if used == role] for role in ROLES}
    if set(declared_roles.values()) - set(ROLES) or len(held["validation"]) > 1 or len(held["sealed"]) > 1:
        raise ValueError(f"declared roles {dict(declared_roles)}: roles are {ROLES}, one validation and one sealed")
    check_split_roles(store, adaptive=held["adaptive"], validation=next(iter(held["validation"]), None),
                      sealed=next(iter(held["sealed"]), None))
    return held


def warm_start_id(store: Store, context: str) -> str | None:
    return next((row["campaign_id"] for row in store.rows("campaign")
                 if row["policy"] == WARM_START and row["context_key"] == context), None)


def register_subject(store: Store, candidate_root: Path, *, runtime: Path, parent: str | None, skeleton: str,
                     policies: frozenset, idea_key: str, descriptor: Mapping, campaign_id: str,
                     structure: Mapping | None = None, program_digest: str | None = None) -> str:
    """Archive `candidate_root` into S/candidates/ and register it for `campaign_id` once."""
    if not store.writer:
        raise PermissionError(f"the store {store.root} is open read-only")
    _campaign(store, campaign_id)
    cid, dest = driver.archive(Path(candidate_root), store.root, runtime)
    driver.check_archived(dest, repos.runtime_commit(runtime))
    if not any(row["candidate_id"] == cid and row["campaign_id"] == campaign_id for row in store.rows("subject")):
        store.append({"kind": "subject", "candidate_id": cid, "parent": parent, "source": str(dest),
                      "skeleton": skeleton, "policies": sorted(policies), "idea_key": idea_key,
                      "descriptor": dict(descriptor), "structure": dict(structure or {}),
                      "program_digest": program_digest, "campaign_id": campaign_id})
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


def _evidence_trials(index: Index, candidate_id: str, context: str, names: Sequence[str]) -> tuple[list, list, list]:
    attempts = [t for t in index.trials.values() if (t["candidate_id"], t["context_key"]) == (candidate_id, context)
                and t["origin_trial_id"] is None and t["task"] in names]
    excluded = sorted(t["trial_id"] for t in attempts if t["trial_id"] in index.dispositions)
    counted = [t for t in attempts if t["trial_id"] not in excluded]
    return attempts, excluded, counted


def _evidence_values(index: Index, counted: Sequence[Mapping], names: Sequence[str]) -> dict[str, list]:
    values = {name: [] for name in names}
    for trial in counted:
        assessed = index.assessments.get(trial["trial_id"])
        row = assessed[-1] if assessed else {
            "outcome": scoring.scored_outcome(trial | {"kind": "evaluation", "task_id": trial["task"]}),
            "value": None}
        if (value := scoring.primary_value(row)) is not None:
            values[trial["task"]].append(value)
    return values


def _observed_summary(values: Mapping[str, Sequence], counted: Sequence[Mapping], price_table: Mapping,
                      min_trials: int) -> dict:
    per_task = {name: {"n": len(v), "mean": mean(v) if v else UNAVAILABLE,
                       "sd": stdev(v) if len(v) > 1 else "insufficient_support"} for name, v in values.items()}
    supported = all(summary["n"] >= min_trials for summary in per_task.values())
    costs = [pricing.cost(trial, price_table) for trial in counted]
    return {"tasks": per_task, "support": "every_adaptive_task" if supported else "insufficient",
            "quality": mean(summary["mean"] for summary in per_task.values()) if supported else UNAVAILABLE,
            "cost": UNAVAILABLE if UNAVAILABLE in costs else mean(costs),
            "calls": scoring.known_mean([trial["provider_calls"] for trial in counted]),
            "wall_clock_sec": scoring.known_mean([trial["wall_clock_sec"] for trial in counted])}


def evidence(store: Store, candidate_id: str, context: str, *, tasks: Sequence[str], price_table: Mapping,
             min_trials: int) -> dict:
    """The observed estimate of `candidate_id` on `tasks` over every non-disposed original trial of equal
    `context`, across campaigns: per-task primary means (failure-inclusive) with n and SD, quality = their
    equal-weight mean when every task has `min_trials`, mean metered cost per trial (unavailable when any is),
    calls and wall clock; `unobserved` without trials, never a score."""
    index, names = store.index(), [Path(task).name for task in tasks]
    attempts, excluded, counted = _evidence_trials(index, candidate_id, context, names)
    result = {"estimator_version": ESTIMATOR_VERSION, "candidate_id": candidate_id, "context_key": context,
              "trial_ids": sorted(t["trial_id"] for t in counted), "trials": len(counted),
              "attempts": len(attempts), "disposed": len(excluded), "excluded": excluded}
    if not counted:
        return result | {"kind": "unobserved", "quality": UNAVAILABLE, "cost": UNAVAILABLE}
    return result | {"kind": "observed"} | _observed_summary(
        _evidence_values(index, counted, names), counted, price_table, min_trials)


def quality_floor(pools: Sequence[Mapping], criterion: Mapping) -> float | str:
    return pareto_readout.stub_floor(pools, criterion)


def _candidate_row(store: Store, candidate_id: str, context: str, tasks: Sequence[str], price_table: Mapping,
                   floor: float | str, min_trials: int) -> dict:
    estimate = evidence(store, candidate_id, context, tasks=tasks, price_table=price_table, min_trials=min_trials)
    quality, cost = estimate["quality"], estimate["cost"]
    above_floor = (estimate.get("support") == "every_adaptive_task" and floor != UNAVAILABLE
                   and pricing.number(quality) and quality > floor)
    if estimate["kind"] == "unobserved":
        reason = "unobserved"
    elif estimate.get("support") != "every_adaptive_task":
        reason = "insufficient_support"
    elif floor == UNAVAILABLE:
        reason = "quality_floor_unavailable"
    elif not pricing.number(quality):
        reason = "quality_unavailable"
    elif not above_floor:
        reason = "below_quality_floor"
    elif cost == UNAVAILABLE:
        reason = "cost_unavailable"
    else:
        reason = None
    return {"candidate_id": candidate_id, "quality": quality, "cost": cost, "above_floor": above_floor,
            "reason": reason, "support": estimate.get("support", "unobserved"),
            "provider_calls": estimate.get("calls", UNAVAILABLE),
            "wall_clock_sec": estimate.get("wall_clock_sec", UNAVAILABLE)}


def _candidate_table_names(context, tasks):
    if not isinstance(context, str) or not context or not isinstance(tasks, Sequence) or not tasks:
        raise ValueError("candidate table requires a context and nonempty tasks")
    names = [Path(task).name for task in tasks]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("candidate table tasks must have unique nonempty basenames")
    return names


def _validate_candidate_cost(min_trials, floor, price_table):
    if type(min_trials) is not int or min_trials < 1:
        raise ValueError("candidate table min_trials must be a positive integer")
    if floor != UNAVAILABLE and not pricing.number(floor):
        raise ValueError("candidate table floor must be a finite nonnegative number or unavailable")
    pricing.validate(price_table)


def candidate_table(store: Store, campaign_id: str, *, context: str, tasks: Sequence[str], price_table: Mapping,
                    floor: float | str, min_trials: int, scheduled: Sequence[Mapping] = ()) -> dict[str, dict]:
    _candidate_table_names(context, tasks)
    _validate_candidate_cost(min_trials, floor, price_table)
    campaign = _campaign(store, campaign_id)
    if campaign["context_key"] != context:
        raise ValueError(f"candidate table context {context} differs from campaign {campaign_id}'s context")
    subjects = campaign_candidates(store, campaign_id, scheduled=scheduled)
    return {candidate_id: _candidate_row(store, candidate_id, context, tasks, price_table, floor, min_trials)
            for candidate_id in sorted(subjects)}


def _rebuild_options(criterion, generation, previous):
    if type(generation) is not int or generation < 0 or not isinstance(previous, Mapping):
        raise ValueError("rebuild requires a nonnegative generation and prior state mapping")
    tau_q, tau_c = pareto_readout.rules(criterion)
    size, capacity = criterion["archive"]["size"], criterion["reservoir"]["capacity"]
    min_trials = criterion["support"]["min_trials"]
    if type(size) is not int or size < 1 or type(capacity) is not int or capacity < 0:
        raise ValueError("archive size must be positive and reservoir capacity nonnegative integers")
    if type(min_trials) is not int or min_trials < 1:
        raise ValueError("support.min_trials must be a positive integer")
    return tau_q, tau_c, size, capacity, min_trials


def _fully_valued(row):
    return row.get("support") == "every_adaptive_task" and pricing.number(row.get("quality"))


def _reservoir_admissions(table, previous, frontier):
    prior_members = {row["candidate_id"] for row in previous.get("reservoir", ())}
    prior_table = previous.get("table", {})
    demoted = set(previous.get("frontier", ())) - set(frontier)
    return {candidate_id: row for candidate_id, row in table.items()
            if candidate_id in prior_members or candidate_id in demoted or
            (_fully_valued(row) and not _fully_valued(prior_table.get(candidate_id, {})))}


def rebuild(store: Store, campaign_id: str, *, criterion: Mapping, pools: Sequence[Mapping], generation: int,
            previous: Mapping) -> dict:
    tau_q, tau_c, size, capacity, min_trials = _rebuild_options(criterion, generation, previous)
    campaign = _campaign(store, campaign_id)
    floor = quality_floor(pools, criterion)
    table = candidate_table(store, campaign_id, context=campaign["context_key"], tasks=criterion["tasks"],
                            price_table=criterion["price_table"], floor=floor, min_trials=min_trials)
    bounded = bounded_frontier(table, size=size, tau_q=tau_q, tau_c=tau_c)
    index = store.index()
    disposed = {trial["candidate_id"] for trial_id, trial in index.trials.items()
                if trial["candidate_id"] in table and trial["origin_trial_id"] is None
                and trial["context_key"] == campaign["context_key"]
                and trial_id in index.dispositions}
    admissions = _reservoir_admissions(table, previous, bounded)
    reservoir = reservoir_update(previous.get("reservoir", ()), admissions, bounded, generation=generation,
                                 capacity=capacity, disposed=disposed)
    return {"floor": floor, "table": table, "frontier": bounded, "reservoir": reservoir}


def behaviour_descriptor(evaluation_rows: Sequence[Mapping], episode_row: Mapping | None) -> dict:
    """A reporting-only descriptor from recorded provider effects and the accepted episode's source evidence."""
    calls = _realized_provider_calls(evaluation_rows)
    roles, loop = _descriptor_roles(calls, episode_row), _loop_present(episode_row)
    return {"realized_provider_calls": calls, "distinct_provider_roles": len(roles), "loop_present": loop,
            "allocation_changed": episode_row.get("allocation_changed", UNAVAILABLE)
            if episode_row is not None else UNAVAILABLE}


def _realized_provider_calls(evaluation_rows: Sequence[Mapping]) -> list[dict]:
    calls = []
    for row in evaluation_rows:
        sites = row.get("realized_perform_sites")
        if not isinstance(sites, list):
            continue
        calls.extend({"task_id": row.get("task_id"), "identity": site["identity"],
                      "attempts": site.get("attempts", 1)}
                     for site in sites if isinstance(site, Mapping) and site.get("effect_class") == "provider"
                     and isinstance(site.get("identity"), str))
    return calls


def _descriptor_roles(calls: Sequence[Mapping], episode_row: Mapping | None) -> set[str]:
    signature = episode_row.get("allocation_signature", {}) if episode_row is not None else {}
    if not isinstance(signature, Mapping):
        return set()
    return {signature[call["identity"]]["provider"] for call in calls
            if isinstance(signature.get(call["identity"]), Mapping)
            and isinstance(signature[call["identity"]].get("provider"), str)}


def _loop_present(episode_row: Mapping | None) -> bool:
    if episode_row is None:
        return False
    structure = episode_row.get("structure", {})
    if not isinstance(structure, Mapping):
        structure = {}
    if type(structure.get("loop")) is bool:
        return structure["loop"]
    controls = structure.get("control_heads", {})
    return isinstance(controls, Mapping) and type(controls.get("loop/recur")) is int \
        and controls["loop/recur"] > 0


def evaluated_structures(store: Store, campaign_id: str, *, scheduled: Sequence[Mapping]) -> list[dict]:
    """The newest twelve campaign-local source summaries, ordered by candidate id for the brief."""
    candidates = campaign_candidates(store, campaign_id, scheduled=scheduled)
    campaign = _campaign(store, campaign_id)
    initial = set(campaign["warm_start"])
    recency = {}
    for position, trial in enumerate(store.rows("trial")):
        if trial["trial_id"] in initial or trial["campaign_id"] == campaign_id:
            recency[trial["candidate_id"]] = trial.get("seq", position)
    latest = max(recency.values(), default=0)
    for position, subject in enumerate(scheduled, latest + 1):
        recency[subject["candidate_id"]] = position
    candidates = {candidate_id: subject for candidate_id, subject in candidates.items()
                  if isinstance(subject.get("structure"), Mapping)}
    recent = sorted(candidates.items(), key=lambda item: recency.get(item[0], item[1].get("seq", -1)), reverse=True)[:12]
    fields = ("heads_outline", "control_heads", "provider_roles", "policy_set", "call_sites", "loop",
              "check_gated", "private_definitions", "idea_key")
    return [{"candidate_id": candidate_id,
             **{key: subject["structure"][key] for key in fields if key in subject["structure"]}}
            for candidate_id, subject in sorted(recent) if isinstance(subject.get("structure"), Mapping)]


def _policy_set(value) -> frozenset | None:
    if not isinstance(value, Collection) or isinstance(value, (str, bytes, Mapping)):
        return None
    if any(not isinstance(policy, Collection) or isinstance(policy, (str, bytes, Mapping)) for policy in value):
        return None
    return frozenset(tuple(policy) for policy in value)


def known_structures(store: Store, campaign_id: str, *, scheduled: Sequence[Mapping]) \
        -> tuple[Mapping[str, Collection[frozenset]], Collection[str]]:
    """Return this campaign's seen skeleton/policy sets and compiled program digests."""
    known, digests = defaultdict(set), set()
    for subject in campaign_candidates(store, campaign_id, scheduled=scheduled).values():
        skeleton, policies, digest = subject.get("skeleton"), _policy_set(subject.get("policies")), subject.get("program_digest")
        if isinstance(skeleton, str) and policies is not None:
            known[skeleton].add(policies)
        if isinstance(digest, str) and digest and digest != UNAVAILABLE:
            digests.add(digest)
    return dict(known), digests


def is_revisit(skeleton: str, program_digest: str | None, policies: frozenset, *,
               known: Mapping[str, Collection[frozenset]], known_digests: Collection[str]) -> bool:
    """A compiled digest repeats exactly; otherwise only a seen skeleton and full policy set repeats."""
    return ((isinstance(program_digest, str) and program_digest in known_digests)
            or policies in known.get(skeleton, ()))


def futility(outcomes: Sequence[str], *, consecutive: int) -> bool:
    """Whether the trailing episode streak reaches its limit; incidents preserve, and fresh children reset it."""
    if type(consecutive) is not int or consecutive < 1:
        raise ValueError("consecutive must be a positive integer")
    streak = 0
    for outcome in outcomes:
        if outcome == "incident":
            continue
        if outcome == "fresh":
            streak = 0
        elif outcome in ("revisit", "rejected", "exhausted"):
            streak += 1
        else:
            raise ValueError(f"unknown episode outcome {outcome!r}")
    return streak >= consecutive


def convergence(store: Store, campaign_id: str) -> dict:
    """Share of this campaign's distinct evaluated children per coarse idea key; warm starts and siblings do not count."""
    candidates = campaign_candidates(store, campaign_id)
    children = {trial["candidate_id"] for trial in store.rows("trial") if trial["campaign_id"] == campaign_id}
    counts = defaultdict(int)
    for candidate_id in children:
        subject = candidates[candidate_id]
        structure = subject.get("structure")
        idea = subject.get("idea_key") or (structure.get("idea_key") if isinstance(structure, Mapping) else None)
        if not isinstance(idea, str):
            raise ValueError(f"evaluated candidate {candidate_id} has no structural idea_key")
        counts[idea] += 1
    total = len(children)
    shares = {idea: count / total for idea, count in sorted(counts.items())} if total else {}
    return {"shares": shares, "max_share": max(shares.values(), default=0.0)}
