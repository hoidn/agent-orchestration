"""The mode 1 readout (mode1.run_mode1 writes it to <evidence>/readout.json): per-seed outcomes, episode outcomes
and refusals, skeleton diversity and provider allocation among accepted children, their evaluation outcomes and
the records pending a scan verdict. Input: the log's records (records.read_records). A failed or incident row
whose launch hit a provider quota (quota.quota_reason) reads as `quota_incident`."""

from collections import Counter, defaultdict
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


def behaviour_descriptor(evaluation_rows: Sequence[Mapping], episode_row: Mapping | None) -> dict:
    """A reporting-only descriptor from recorded provider effects and accepted source evidence."""
    calls = _realized_provider_calls(evaluation_rows)
    role_count = UNAVAILABLE if calls == UNAVAILABLE else len({call["provider_role"] for call in calls})
    structure = episode_row.get("structure", {}) if episode_row is not None else {}
    controls = structure.get("control_heads", {}) if isinstance(structure, Mapping) else {}
    loop = structure.get("loop")
    if type(loop) is not bool:
        loop = isinstance(controls, Mapping) and type(controls.get("loop/recur")) is int \
            and controls["loop/recur"] > 0
    changed = episode_row.get("allocation_changed", UNAVAILABLE) if episode_row is not None else UNAVAILABLE
    return {"realized_provider_calls": calls, "distinct_provider_roles": role_count, "loop_present": loop,
            "allocation_changed": changed if type(changed) is bool else UNAVAILABLE}


def _realized_provider_calls(evaluation_rows: Sequence[Mapping]) -> list[dict] | str:
    if not evaluation_rows:
        return UNAVAILABLE
    calls = []
    for row in evaluation_rows:
        sites = row.get("realized_perform_sites")
        if not isinstance(sites, list):
            return UNAVAILABLE
        for site in sites:
            call = _provider_call(site)
            if call == UNAVAILABLE:
                return UNAVAILABLE
            if call is not None:
                calls.append(call | ({"task_id": row["task_id"]} if isinstance(row.get("task_id"), str) else {}))
    return calls


def _provider_call(site: Mapping) -> dict | None | str:
    if not isinstance(site, Mapping):
        return UNAVAILABLE
    if site.get("effect_class") != "provider":
        return None
    identity, attempts, role = site.get("identity"), site.get("attempts"), site.get("provider_role")
    if (not isinstance(identity, str) or type(attempts) is not int or attempts < 1
            or not isinstance(role, str) or not role or role == UNAVAILABLE):
        return UNAVAILABLE
    return {"identity": identity, "attempts": attempts, "provider_role": role}


def convergence(store, campaign_id: str) -> dict:
    """Share of campaign-local evaluated children per idea key; warm starts and siblings do not count."""
    from experiments.orc_structural_search.campaign import _campaign, campaign_candidates

    candidates, campaign = campaign_candidates(store, campaign_id), _campaign(store, campaign_id)
    trials = store.index().trials
    initial = {trials[trial_id]["candidate_id"] for trial_id in campaign["warm_start"]}
    children = {trial["candidate_id"] for trial in store.rows("trial")
                if trial["campaign_id"] == campaign_id and trial["candidate_id"] not in initial}
    counts = defaultdict(int)
    for candidate_id in children:
        subject, structure = candidates[candidate_id], candidates[candidate_id].get("structure")
        idea = subject.get("idea_key") or (structure.get("idea_key") if isinstance(structure, Mapping) else None)
        if not isinstance(idea, str):
            raise ValueError(f"evaluated candidate {candidate_id} has no structural idea_key")
        counts[idea] += 1
    shares = {idea: count / len(children) for idea, count in sorted(counts.items())} if children else {}
    return {"shares": shares, "max_share": max(shares.values(), default=0.0)}
