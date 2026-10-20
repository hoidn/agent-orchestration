"""Append-only JSONL records and Workflow Lisp structural metrics."""

from __future__ import annotations

import json
import fcntl
import hashlib
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


def campaign_candidates(store: Store, campaign_id: str, *, scheduled: Sequence[Mapping] = ()) -> dict[str, dict]:
    campaign, trials = find_campaign(store, campaign_id), store.index().trials
    held = [trials[t]["candidate_id"] for t in campaign["warm_start"]]
    held += [t["candidate_id"] for t in trials.values() if t["campaign_id"] == campaign_id]
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
