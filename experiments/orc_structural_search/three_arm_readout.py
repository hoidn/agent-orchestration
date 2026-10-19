"""The judged readout of the three-arm run (three_arm.py; `three_arm readout`): per task, per arm and per subset
child, descriptively, from each task pool's results.json (scoring.read_pool), the run's log and its compile-only
readout (E/readout.json). Criterion: criteria/three_arm.json (tasks, anchors, separation.anchor_spread_limit).
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from experiments.orc_structural_search.records import UNAVAILABLE, read_records
from experiments.orc_structural_search.scoring import (
    anchor_checks, log_only_pool, policy_stats, primary_value, read_pool)
from experiments.orc_structural_search.three_arm import (
    HISTORICAL_CRITERION_SHA256, MODE, arm_specs, check_row_criteria, load_criterion)

DECISION = "descriptive; no separation rule applied (Phase 1 decision stands)"


def child_figures(rows: Sequence[Mapping]) -> dict:
    """scoring.policy_stats and the primary value of each evaluation (unavailable when excluded)."""
    return policy_stats(rows) | {"values": [UNAVAILABLE if v is None else v for v in map(primary_value, rows)]}


def task_figures(pool: Mapping, arms: Mapping[str, str], chosen: Mapping[str, str], criterion: Mapping,
                 evidence: Mapping[str, Mapping] | None = None) -> dict:
    """One task's figures: per arm (`arms`: evaluation id -> arm) scoring.policy_stats over its subset children's
    evaluations and child_figures per subset child (`chosen`: candidate id -> arm; one without an evaluation of the
    task has unavailable figures); the anchors, scoring.anchor_checks (reported, not a gate), agreement, excluded
    judges and unpooled evaluations."""
    rows = [row for row in pool["rows"] if row["evaluation_id"] in arms]
    figures = {}
    for arm in arm_specs(criterion):
        mine = [row for row in rows if arms[row["evaluation_id"]] == arm]
        children = sorted(cid for cid, owner in chosen.items() if owner == arm)
        figures[arm] = policy_stats(mine) | {"children": {
            cid: child_figures([r for r in mine if r["candidate_id"] == cid]) for cid in children},
            "evaluations": [evaluation_evidence(row, (evidence or {}).get(row["evaluation_id"], {}))
                            for row in mine]}
    checks = UNAVAILABLE if pool["no_pool"] else anchor_checks(
        pool["anchors"], criterion["anchors"][pool["task"]], criterion["separation"]["anchor_spread_limit"])
    return {"arms": figures, "anchors": pool["anchors"], "anchor_checks": checks, "agreement": pool["agreement"],
            "excluded_judges": pool["excluded_judges"], "unpooled": pool["unpooled"], "no_pool": pool["no_pool"]}



def evaluation_evidence(row: Mapping, record: Mapping) -> dict:
    """Calls and memo evidence stay separate; older rows have no effect or branch receipt."""
    return {"evaluation_id": row["evaluation_id"], "candidate_id": row["candidate_id"],
            "provider_calls": row.get("calls", UNAVAILABLE),
            **{key: record.get(key, UNAVAILABLE) for key in (
                "realized_perform_sites", "exercised_branches", "branch_coverage_reason")}}


def readout(log: Path, driver_readout: Path, criterion: Path, results: Sequence[Path]) -> dict:
    """Per task (scoring.read_pool of each results.json, criterion hash checked; a criterion task without one:
    scoring.log_only_pool) task_figures over the evaluations of the subset children the driver's readout
    (E/readout.json) names (a child a continued run's subset no longer chooses is left out); the driver readout's
    compile-only figures; no decision rule."""
    frozen, compile_only = load_criterion(criterion), json.loads(Path(driver_readout).read_text())
    rows = read_records(log)
    check_row_criteria(rows, frozen)
    got = compile_only.get("criterion_sha256")
    if got != frozen["criterion_sha256"] and not (got is None and frozen["criterion_sha256"] == HISTORICAL_CRITERION_SHA256):
        raise ValueError("driver readout criterion_sha256 differs from the criterion")
    if set(compile_only["arms"]) != set(arm_specs(frozen)):
        raise ValueError("driver readout arms differ from the criterion")
    chosen = {cid: arm for arm, figures in compile_only["arms"].items() for cid in figures["subset"]}
    arms = {row["evaluation_id"]: row["arm"] for row in rows if row["kind"] == "evaluation"
            and row.get("mode") == MODE and chosen.get(row["candidate_id"]) == row["arm"]}
    evidence = {row["evaluation_id"]: row for row in rows if row["kind"] == "evaluation"}
    pools = [read_pool(path, log, criterion) for path in results]
    pooled = {pool["task"] for pool in pools}
    pools += [log_only_pool(log, Path(task).name) for task in frozen["tasks"] if Path(task).name not in pooled]
    return {"tasks": {pool["task"]: task_figures(pool, arms, chosen, frozen, evidence)
                      for pool in sorted(pools, key=lambda p: p["task"])},
            "compile_only": compile_only, "decision": DECISION}
