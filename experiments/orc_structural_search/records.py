"""Append-only JSONL records and Workflow Lisp structural metrics."""

from __future__ import annotations

import json
import fcntl
import hashlib
import os
from collections import defaultdict, namedtuple
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from experiments.compare import repos
from experiments.orc_structural_search.record_normalization import (
    CONTROL_HEADS,
    control_heads,
    provider_allocation,
    skeleton_hash,
)

UNAVAILABLE = "unavailable"
SCHEMA, LOG = "campaign-evidence-v1", "evidence.jsonl"
CHECKPOINT = "campaign-checkpoint-v1"
CHECKPOINT_KEYS = ("generation", "frontier", "reservoir", "rng_state", "ingestion_position", "ledger_index",
                   "futility_streak", "budget", "stopped")
REQUIRED = {kind: fields.split() for kind, fields in {
    "campaign": "campaign_id label context_key criterion_sha256 policy parameters budget seeds run_seed warm_start "
                "declared_roles roots",
    "subject": "candidate_id parent source skeleton policies idea_key descriptor campaign_id",
    "trial": "trial_id origin_trial_id campaign_id context_key evaluation_id run_id attempt candidate_id task "
             "replicate outcome records_dir",
    "assessment": "trial_id results clone_ids task outcome value criterion_sha256 proof_sha256 split",
    "disposition": "target_kind target_id disposition reason supersedes",
    "exposure": "package_sha256 role campaign_id criterion_sha256"}.items()}
Index = namedtuple("Index", "trials assessments dispositions exposure")


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


def _load_campaign_rows(log: Path) -> list[dict]:
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


def trial_id(campaign_id: str, run_id: str, evaluation_id: str, attempt: int) -> str:
    digest = hashlib.sha256(json.dumps([campaign_id, run_id, evaluation_id, attempt], sort_keys=True).encode()).hexdigest()
    return "trial:" + digest


def find_campaign(store: Store, campaign_id: str) -> dict:
    if found := [row for row in store.rows("campaign") if row["campaign_id"] == campaign_id]:
        return found[0]
    raise KeyError(f"no campaign {campaign_id} in {store.root}")


def _checkpoint(store: Store, campaign_id: str) -> tuple[Path, dict]:
    """Return the checkpoint path and its required campaign identity."""
    campaign = find_campaign(store, campaign_id)
    identity = {key: campaign[key] for key in ("campaign_id", "context_key", "criterion_sha256")}
    return store.root / "campaigns" / campaign_id / "checkpoint.json", {"schema": CHECKPOINT, **identity}


def write_checkpoint(store: Store, campaign_id: str, state: Mapping) -> Path:
    """Atomically replace the checkpoint after requiring every persisted state key."""
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
    """Return the campaign checkpoint or refuse one with another identity."""
    path, identity = _checkpoint(store, campaign_id)
    if not path.exists():
        return None
    state = json.loads(path.read_text())
    if any(state.get(key) != value for key, value in identity.items()):
        raise ValueError(f"{path} is not a {CHECKPOINT} of campaign {campaign_id} under its context and criterion")
    return state


def tuples(value):
    """Restore the tuple tree required by random.Random.setstate after JSON serialization."""
    return tuple(tuples(v) for v in value) if isinstance(value, list) else value


def campaign_candidates(store: Store, campaign_id: str, *, scheduled: Sequence[Mapping] = ()) -> dict[str, dict]:
    campaign, trials = find_campaign(store, campaign_id), store.index().trials
    held = [trials[t]["candidate_id"] for t in campaign["warm_start"]]
    held += [t["candidate_id"] for t in trials.values() if t["campaign_id"] == campaign_id and t.get("split") not in ("validation", "sealed")]
    subjects = {}
    for row in store.rows("subject"):
        if row["candidate_id"] not in subjects or row["campaign_id"] == campaign_id:
            subjects[row["candidate_id"]] = row
    if missing := sorted(set(held) - set(subjects)):
        raise ValueError(f"campaign {campaign_id} holds unregistered candidates {missing}")
    return {cid: subjects[cid] for cid in held} | {row["candidate_id"]: dict(row) for row in scheduled}


def trial_record(row: Mapping, campaign_id: str, context: str) -> dict:
    attempt = row.get("attempt", 1)
    return {"kind": "trial", "trial_id": trial_id(campaign_id, row["run_id"], row["evaluation_id"], attempt),
            "origin_trial_id": None, "campaign_id": campaign_id, "context_key": context, "attempt": attempt,
            "task": row["task_id"], "split": row.get("split", UNAVAILABLE), "generation": row.get("generation"),
            "incidents": row.get("incidents", []), "state_dir": row.get("state_dir"),
            **{key: row[key] for key in ("evaluation_id", "run_id", "candidate_id", "replicate", "outcome",
                                         "records_dir")},
            **{key: row.get(key, UNAVAILABLE) for key in ("provider_calls", "wall_clock_sec", "consumption",
                                                          "receipt_usage")}}


def add_trials(store: Store, trials: Sequence[dict]) -> int:
    stored, added = store.index().trials, 0
    for trial in trials:
        known = stored.get(trial["trial_id"])
        if known is None or {k: v for k, v in known.items() if k not in ("schema", "seq")} != trial:
            store.append(trial)
            added += 1
    return added


def add_assessments(store: Store, pools: Sequence[tuple[str, dict]], trials: Mapping[str, dict], proof: str | None) -> int:
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


def writer_lock(root: Path) -> TextIO:
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
    store = Store(root, [], writer_lock(root) if writer else None)
    try:
        store._rows = _load_campaign_rows(root / LOG)
    except BaseException:
        store.close()
        raise
    return store


def open_campaign_store(root: Path, *, writer: bool, checkout_prefix: Path) -> Store:
    root = Path(root).resolve()
    repos.guard(Path(checkout_prefix), root)
    repos.visible_in_sandbox(root)
    store = open_store(root, writer=writer)
    try:
        for row in store.rows("campaign"):
            check_roots(root, row["roots"].values())
    except BaseException:
        store.close()
        raise
    return store


def append_record(log: Path, record: Mapping[str, object]) -> None:
    """Append `record` to `log` as one JSON line with sorted keys.

    Missing receipts are the caller's string "unavailable" and are written
    verbatim; nothing here substitutes zero.
    """
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True) + "\n")


def read_records(log: Path) -> list[dict]:
    """Return every record in `log`, in append order."""
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def prepare_log(evidence, continued):
    path = evidence / 'log.jsonl'
    if continued and not path.exists():
        raise ValueError('resume requires its missing append-only log to be restored')
    if path.exists() and not continued:
        raise ValueError('fresh campaign evidence already contains a log; use resume')
    path.touch(exist_ok=True)


def replay_judge_incidents(state, rows):
    """Resolve durable incident events ahead of the saved ingestion position before any new work."""
    for row in rows[state['ingestion_position']:]:
        if row['kind'] == 'judge_incident' and row['campaign_id'] == state['campaign_id']:
            state.update({key: row[key] for key in ('generation', 'completed_generation', 'judge_incidents',
                                                  'rng_state', 'stopped')})
            state['scheduled'] = []


def study_manifest(store, campaign_ids):
    ids = sorted(campaign_ids)
    found = [row for row in store.rows('exposure') if row['role'] == 'validation'
             and set(row.get('campaign_ids', ())).intersection(ids)]
    if len(found) != 1 or found[0]['campaign_ids'] != ids:
        raise ValueError('study requires its complete frozen validation manifest')
    return found[0]


def _payload(row):
    return {key: value for key, value in row.items() if key not in ('schema', 'seq')}


def require_adaptive(store, campaign_id):
    if any(campaign_id in row.get('campaign_ids', ()) for row in store.rows('exposure') if row['role'] == 'validation'):
        raise ValueError('validation exposure forbids further adaptive continuation')


def _study_headers(store, campaign_ids, criterion, config_path):
    from experiments.compare.repos import sha256_file
    ids = sorted(campaign_ids)
    frozen = json.loads(Path(criterion).read_text())
    headers = [find_campaign(store, cid) for cid in ids]
    expected = {(r['label'], r['policy'], r['run_seed']) for r in frozen['campaigns']}
    actual = {(r['label'], r['policy'], r['run_seed']) for r in headers}
    if len(headers) != len(expected) or actual != expected:
        raise ValueError('validation requires the complete frozen campaign pair')
    if len({(r['context_key'], r['criterion_sha256'], tuple(r['warm_start'])) for r in headers}) != 1:
        raise ValueError('final campaigns differ in context, criterion or warm start')
    if any(r['criterion_sha256'] != sha256_file(criterion) for r in headers):
        raise ValueError('campaign criterion differs from requested final study')
    if any(r['parameters']['config_sha256'] != sha256_file(config_path) for r in headers):
        raise ValueError('final configuration differs from frozen campaign config')
    return frozen, headers


def _assessment_roots(store, launch):
    from itertools import combinations
    keys = ('work_root', 'evidence_root', 'pools_root')
    validation = {key: str(Path(launch[key]).resolve()) for key in keys}
    sealed = {key: str(Path(launch['sealed_roots'][key]).resolve()) for key in keys}
    roots = [Path(path) for path in [*validation.values(), *sealed.values()]]
    check_roots(store.root, roots)
    previous = [Path(path).resolve() for row in store.rows('campaign') for path in row['roots'].values()]
    for left, right in [*combinations(roots, 2), *((a, b) for a in roots for b in previous)]:
        if left.is_relative_to(right) or right.is_relative_to(left):
            raise ValueError('final assessment roots must be separate from each other and adaptive roots')
    return validation, sealed


def _validation_record(store, campaign_ids, frozen, headers, checkpoints, reference, launch, criterion, validation, sealed, finalists, replicates, mean_cost_ceiling):
    from experiments.orc_structural_search.qualification_io import package_digest
    selected = {cid: sorted(state['frontier'], key=lambda c: (-state['table'][c]['quality'], state['table'][c]['cost'], c))[:finalists]
                for cid, (state, _) in checkpoints.items()}
    validation_roots, sealed_roots = _assessment_roots(store, launch)
    ids = sorted(campaign_ids)
    record = {'kind': 'exposure', 'role': 'validation', 'campaign_id': min(ids), 'campaign_ids': ids,
        'criterion_sha256': headers[0]['criterion_sha256'], 'context_key': headers[0]['context_key'],
        'criterion_path': str(Path(criterion).resolve()), 'package_sha256': package_digest(validation),
        'validation_task': str(validation), 'sealed_task': str(sealed), 'reference_id': reference['candidate_id'],
        'warm_reference_trial_ids': reference['trial_ids'], 'reference': reference, 'replicates': replicates,
        'mean_cost_ceiling': mean_cost_ceiling, 'checkpoints': {cid: ref for cid, (_, ref) in checkpoints.items()},
        'finalists': selected, 'candidate_ids': sorted({reference['candidate_id'], *(c for values in selected.values() for c in values)}),
        'finalist_projection': {cid: {c: state['table'][c] for c in selected[cid]} for cid, (state, _) in checkpoints.items()},
        'validation_roots': validation_roots, 'sealed_roots': sealed_roots}
    return record


def validation_manifest(store, campaign_ids, *, validation_task, replicates, finalists,
                        mean_cost_ceiling, launch, criterion):
    from experiments.orc_structural_search import campaign, readout_join
    from experiments.orc_structural_search.qualification_io import package_digest
    from experiments.orc_structural_search.pareto_readout import _comparison_reference
    frozen, headers = _study_headers(store, campaign_ids, criterion, launch['config_path'])
    if (replicates, finalists) != (frozen['horizon']['validation_replicates'], frozen['horizon']['finalists_per_campaign']):
        raise ValueError('final assessment support differs from frozen horizon')
    runtime = Path(headers[0]['parameters']['runtime'])
    validation, sealed = ((runtime / frozen[key]).resolve() for key in ('validation_task', 'sealed_task'))
    if Path(validation_task).resolve() != validation:
        raise ValueError('validation task differs from frozen package')
    checkpoints = {r['campaign_id']: readout_join.terminal_checkpoint(store, r['campaign_id'], criterion) for r in headers}
    reference = readout_join.warm_reference(store, headers[0], criterion)
    _comparison_reference({'P0': {'reference': reference}}, mean_cost_ceiling)
    record = _validation_record(store, campaign_ids, frozen, headers, checkpoints, reference, launch,
                                criterion, validation, sealed, finalists, replicates, mean_cost_ceiling)
    ids = sorted(campaign_ids)
    prior = [row for row in store.rows('exposure') if row['role'] == 'validation'
             and (row['package_sha256'] == record['package_sha256'] or set(row.get('campaign_ids', ())).intersection(ids))]
    if prior:
        if len(prior) != 1 or _payload(prior[0]) != record:
            raise ValueError('validation manifest differs from exact retry')
        return prior[0]
    campaign.check_split_roles(store, adaptive=[], validation=record['package_sha256'], sealed=package_digest(sealed))
    store.append(record)
    return store.rows()[-1]


def _frozen_rows(store, manifest, reason):
    from experiments.orc_structural_search import readout_join, selection
    from experiments.compare.repos import sha256_file
    criterion = Path(manifest['criterion_path'])
    for cid, expected in manifest['checkpoints'].items():
        _, actual = readout_join.terminal_checkpoint(store, cid, criterion)
        if actual != expected:
            raise ValueError('terminal checkpoint or adaptive evidence changed after validation exposure')
    pool = readout_join.final_pool(store, manifest, role='validation')
    projection = selection.validation_projection(store, manifest, pool)
    assessment_seqs = selection.assessment_sequences(store, manifest, pool)
    return [{'kind': 'disposition', 'target_kind': 'campaign', 'target_id': cid, 'disposition': 'frozen',
        'reason': reason, 'supersedes': [], 'validation_manifest_seq': manifest['seq'],
        'checkpoint_sha256': manifest['checkpoints'][cid]['checkpoint_sha256'],
        'validation_log_sha256': pool['log_sha256'], 'validation_results': pool['results'],
        'validation_results_sha256': pool['results_sha256'], 'assessment_seqs': assessment_seqs,
        'numeric_rule': {'mean_cost_ceiling': manifest['mean_cost_ceiling']}, **projection[cid]}
        for cid in manifest['campaign_ids']]


def frozen_rows(store, manifest, reason):
    records = _frozen_rows(store, manifest, reason)
    prior = {r['target_id']: r for r in store.rows('disposition') if r['disposition'] == 'frozen'
             and r['target_id'] in manifest['campaign_ids']}
    for record in records:
        if record['target_id'] in prior and _payload(prior[record['target_id']]) != record:
            raise ValueError('frozen disposition differs from exact retry')
    return records, prior


def freeze_study(store, campaign_ids, reason):
    manifest = study_manifest(store, campaign_ids)
    records, prior = frozen_rows(store, manifest, reason)
    for record in records:
        if record['target_id'] not in prior:
            store.append(record)
    return len(records) - len(prior)


def _sealed_record(manifest, frozen, sealed_task):
    from experiments.orc_structural_search.qualification_io import package_digest
    frozen_criterion = json.loads(Path(manifest['criterion_path']).read_text())
    record = {**{k: v for k, v in manifest.items() if k not in ('schema', 'seq')}, 'role': 'sealed',
        'package_sha256': package_digest(sealed_task), 'validation_manifest_seq': manifest['seq'],
        'frozen_seqs': sorted(r['seq'] for r in frozen), 'replicates': frozen_criterion['horizon']['sealed_replicates'],
        'candidate_ids': sorted({manifest['reference_id'], *(r['choice'] for r in frozen)})}
    return record


def _commit_sealed_exposure(store, manifest, record):
    from experiments.orc_structural_search import campaign
    prior = [r for r in store.rows('exposure') if r['role'] == 'sealed' and r.get('validation_manifest_seq') == manifest['seq']]
    if prior:
        if len(prior) != 1 or _payload(prior[0]) != record:
            raise ValueError('sealed authorization differs from exact retry')
        exposure_seq = prior[0]['seq']
    else:
        campaign.check_split_roles(store, adaptive=[], validation=None, sealed=record['package_sha256'])
        exposure_seq = store.append(record)
    return exposure_seq


def open_sealed_study(store, campaign_ids, sealed_task):
    from experiments.orc_structural_search import campaign
    from experiments.orc_structural_search.qualification_io import package_digest
    manifest = study_manifest(store, campaign_ids)
    frozen = [r for r in store.rows('disposition') if r['disposition'] == 'frozen'
              and r.get('validation_manifest_seq') == manifest['seq']]
    if {r['target_id'] for r in frozen} != set(manifest['campaign_ids']):
        raise ValueError('sealed split requires every selected campaign frozen')
    if any(r['disposition'] == 'sealed_opened' and r.get('validation_manifest_seq') == manifest['seq'] for r in store.rows('disposition')):
        raise ValueError('sealed study was already opened; a second opening is refused')
    if Path(sealed_task).resolve() != Path(manifest['sealed_task']):
        raise ValueError('sealed task differs from frozen manifest')
    freeze_study(store, campaign_ids, frozen[0]['reason'])
    record = _sealed_record(manifest, frozen, sealed_task)
    exposure_seq = _commit_sealed_exposure(store, manifest, record)
    return store.append({'kind': 'disposition', 'target_kind': 'campaign', 'target_id': manifest['campaign_id'],
        'disposition': 'sealed_opened', 'reason': 'open frozen study holdout', 'supersedes': [],
        'campaign_ids': manifest['campaign_ids'], 'validation_manifest_seq': manifest['seq'], 'exposure_seq': exposure_seq})


def campaign_parameters(config_path, frozen, *, seeds, run_seed, call_cap, concurrency, runtime, judges, roots):
    from experiments.orc_structural_search import mode1
    return {'criterion_sha256': frozen['criterion_sha256'], 'config_sha256': repos.sha256_file(config_path),
        'horizon': frozen['horizon'], 'seeds': {str(p.resolve()): mode1.seed_digest(p) for p in seeds},
        'run_seed': run_seed, 'call_cap': call_cap, 'concurrency': concurrency,
        'runtime': str(runtime.resolve()), 'runtime_commit': repos.runtime_commit(runtime),
        'judges': list(judges), 'roots': {k: str(Path(v).resolve()) for k, v in roots.items()}}


def require_adaptive_label(store, label):
    header = next((row for row in store.rows('campaign') if row['label'] == label), None)
    if header:
        require_adaptive(store, header['campaign_id'])
