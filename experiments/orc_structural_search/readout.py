"""The mode 1 readout (driver.run_mode1 writes it to <evidence>/readout.json): per-seed outcomes, episode outcomes
and refusals, skeleton diversity and provider allocation among accepted children, their evaluation outcomes and
the records pending a scan verdict. Input: the log's records (records.read_records). A failed or incident row
whose launch hit a provider quota (quota.quota_reason) reads as `quota_incident`."""

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from experiments.orc_structural_search.quota import quota_reason
from experiments.orc_structural_search.records import UNAVAILABLE

QUOTA_INCIDENT = "quota_incident"

COLLAPSE_THRESHOLD = 0.75  # design default: a terminal-only share above it means the interface collapsed


def share(count: int, total: int) -> float | str:
    return count / total if total else UNAVAILABLE


def outcome(row: Mapping, evidence_root: Path | None = None) -> str:
    return QUOTA_INCIDENT if quota_reason(row, evidence_root) else row["outcome"]


def catalog_outcomes(rows: Sequence[Mapping]) -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for row in rows:
        if row["kind"] == "evaluation" and row["mode"] == "catalog":
            entry = catalog.setdefault(row["seed"], {"candidate_id": row["candidate_id"], "outcomes": []})
            entry["outcomes"].append(outcome(row))
    return catalog


def child_outcomes(rows: Sequence[Mapping]) -> dict[str, list]:
    children: dict[str, list] = {}
    for row in rows:
        if row["kind"] == "evaluation" and row["mode"] == "unguided":
            children.setdefault(row["candidate_id"], []).append(outcome(row))
    return children


def revisit_count(accepted: Sequence[Mapping]) -> int:
    seen, revisits = set(), 0
    for row in accepted:
        seen.add(row["parent_skeleton"])
        revisits += row["skeleton"] in seen
        seen.add(row["skeleton"])
    return revisits


def diversity(accepted: Sequence[Mapping]) -> dict:
    """Skeleton diversity among accepted children. A child is terminal-only when both its skeleton and its
    provider allocation equal the parent's; one with the parent's skeleton but another allocation is
    `allocation_distinct`."""
    same_skeleton = [row for row in accepted if row["skeleton"] == row["parent_skeleton"]]
    terminal = sum(row["provider_allocation"] == row["parent_provider_allocation"] for row in same_skeleton)
    terminal_only = share(terminal, len(accepted))
    return {"distinct_skeletons": len({row["skeleton"] for row in accepted}),
            "revisit_rate": share(revisit_count(accepted), len(accepted)), "terminal_only_share": terminal_only,
            "allocation_distinct": len(same_skeleton) - terminal,
            "collapsed": terminal_only if terminal_only == UNAVAILABLE else terminal_only > COLLAPSE_THRESHOLD}


def readout(rows: Sequence[Mapping], evidence_root: Path | None = None) -> dict:
    """Per-seed outcomes, episode outcomes and refusals, skeleton diversity and provider allocation among
    accepted children, their evaluation outcomes and the evaluations and episodes pending a scan verdict;
    `evidence_root` lets episode rows from before the quota guard be read for quota messages."""
    episodes = [row for row in rows if row["kind"] == "episode"]
    accepted = [row for row in episodes if row["outcome"] == "accepted"]
    return {"catalog": catalog_outcomes(rows),
            "episodes": dict(Counter(outcome(row, evidence_root) for row in episodes)),
            "refused": dict(Counter(row["refusal_code"] or row["diagnostics_class"]
                                    for row in episodes if row["outcome"] == "rejected")),
            **diversity(accepted), "child_outcomes": child_outcomes(rows),
            "scan_pending": [row.get("evaluation_id") or row["episode_id"] for row in rows if row.get("scan_pending")]}
