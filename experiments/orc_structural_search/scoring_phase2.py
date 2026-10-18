"""The Phase 2 readout of structural search under criteria/phase2.json (`scoring.py readout --phase 2`).

Plan: docs/plans/2026-10-18-orc-structural-search-phase2-plan.md, Task 4. Figures are per run and interface, never
pooled across interfaces; every rule parameter comes from the criterion file, whose SHA-256 every pool's
results.json must carry (scoring.read_pool).

Inputs per mode 2 run (written by adaptive.py):
  <E2>/log.jsonl            rows read here:
      {"kind": "episode", "interface", "generation", "outcome", "candidate_id", "parent_candidate_id",
       "candidate_root", "skeleton", "parent_skeleton", "provider_allocation", "parent_provider_allocation"}
      {"kind": "judging", "generation", "task", "pool", "results"}   one per adaptive pool; `results` is the
                                                                     pool's records/results.json
      {"kind": "reference", "candidate_id", "run"}                    the reference seed (the initial incumbent),
                                                                     written once when the initial archive is built
  <E2>/archive/gen-<n>.json a JSON list of archive entries {candidate_id, candidate_root, seed (stem or null),
                            mean_value, mean_calls, ...}
The validation pool is scoring.read_pool's result for the validation task's results.json and its log.

Means are failure-inclusive (criteria amendment of 2026-10-18): a failed evaluation counts FAILED_POINTS (0) and an
incident is left out (scoring.primary_value). Adaptive failures come from each run's log (`kind: evaluation`,
`split: adaptive`, `outcome: failed`), not from the pools: a generation whose evaluations of a task all failed has no
pool, and each pool's read_pool rows hold every generation's failures of its task.

Gates come before decisions: a generation's adaptive pool with inverted anchors, or an anchor spread across
generations above the limit, marks the run's improvements untrusted; inverted validation anchors or a validation
spread above the limit withhold the final choice.
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import mean

from experiments.compare.repos import sha256_file
from experiments.orc_structural_search.readout import diversity, share
from experiments.orc_structural_search.records import UNAVAILABLE, control_heads, final_choice, read_records
from experiments.orc_structural_search.scoring import (
    DIRECT, FAILED_POINTS, anchor_checks, policy_stats, read_pool,
)

COMPLETED = ("accepted", "rejected")  # an episode that reached a verdict; stopped ones (exhausted, incident) did not
UNTRUSTED = "untrusted"


def archive_files(directory: Path) -> list[tuple[int, list[dict]]]:
    """(generation, entries) per gen-<n>.json, in generation order."""
    files = [(int(p.stem.removeprefix("gen-")), json.loads(p.read_text())) for p in Path(directory).glob("gen-*.json")]
    if not files:
        raise ValueError(f"no gen-<n>.json archive file in {directory}")
    return sorted(files, key=lambda f: f[0])


def reference(logs: Sequence[Path], rows: Sequence[Sequence[Mapping]]) -> str:
    """The candidate every run's single `reference` row names; a missing or repeated row, or a disagreement,
    raises."""
    found: dict[str, list] = {}
    for log, run in zip(logs, rows, strict=True):
        named = [row["candidate_id"] for row in run if row["kind"] == "reference"]
        if len(named) != 1:
            raise ValueError(f"{log}: expected one reference row, found {len(named)} naming {sorted(named)}")
        found.setdefault(named[0], []).append(str(log))
    if len(found) != 1:
        raise ValueError(f"runs disagree on the reference seed: {found}")
    return next(iter(found))


def adaptive_means(pools: Sequence[tuple[int, Mapping]], log_rows: Sequence[Mapping],
                   tasks: Sequence[str]) -> dict[str, float]:
    """candidate_id -> the mean over `tasks` of its per-task primary mean (pooled completed runs' values, and
    FAILED_POINTS per failed adaptive evaluation in `log_rows`), for candidates with a primary value on every task."""
    values: dict[str, dict[str, list]] = {}
    for _, pool in pools:
        for row in pool["rows"]:
            if row["outcome"] == "completed" and row["value"] is not None:
                values.setdefault(row["candidate_id"], {}).setdefault(row["task"], []).append(row["value"])
    failed = [row for row in log_rows if row["kind"] == "evaluation" and row.get("split") == "adaptive"
              and row["outcome"] == "failed" and row["task_id"] in tasks]
    for row in failed:
        values.setdefault(row["candidate_id"], {}).setdefault(row["task_id"], []).append(FAILED_POINTS)
    return {cid: mean(mean(per[t]) for t in tasks) for cid, per in values.items() if set(per) >= set(tasks)}


def adaptive_anchors(pools: Sequence[tuple[int, Mapping]], tasks: Sequence[str], criterion: Mapping) -> dict:
    """Per adaptive task: anchors_ok per generation (all its pools) and the anchor spread per judge across every
    generation's batches (one batch per (generation, pool, batch): a generation may hold several pools of a task),
    with spread_ok against the criterion's limit."""
    limit, result = criterion["anchor_spread_limit"], {}
    for task in tasks:
        roles, mine = criterion["anchors"][task], [(g, pool) for g, pool in pools if pool["task"] == task]
        generations: dict[int, bool] = {}
        for g, pool in mine:
            generations[g] = generations.get(g, True) and anchor_checks(pool["anchors"], roles, limit)["anchors_ok"]
        merged = [a | {"batch": (g, k, a["batch"])} for k, (g, pool) in enumerate(mine) for a in pool["anchors"]]
        checks = anchor_checks(merged, roles, limit)
        result[task] = {"generations": generations, "anchor_spread": checks["anchor_spread"],
                        "spread_ok": checks["spread_ok"]}
    return result


def trust_rule(anchors: Mapping[str, Mapping]) -> str:
    if not all(ok for task in anchors.values() for ok in task["generations"].values()):
        return "anchors_inverted"
    if not all(task["spread_ok"] for task in anchors.values()):
        return "anchor_spread"
    return "trusted"


def gain(row: Mapping, child_means: Mapping[str, float], archive: Mapping[int, list]) -> float | str:
    """The child's adaptive mean minus its parent's mean_value in the archive it was drawn from (gen-<g-1>)."""
    parent = [e["mean_value"] for e in archive.get(row["generation"] - 1, ())
              if e["candidate_id"] == row["parent_candidate_id"]]
    child = child_means.get(row["candidate_id"])
    return UNAVAILABLE if not parent or child is None else child - parent[0]


def heads(root: str, definitions: Sequence[str]) -> dict[str, int]:
    source = "\n".join(path.read_text() for path in sorted(Path(root).glob("*.orc")))
    return control_heads(source, definitions=definitions)


def control_flow_changes(accepted: Sequence[Mapping], roots: Mapping[str, str], definitions: Sequence[str]) -> list:
    changes = []
    for row in accepted:
        parent, child = (heads(roots[row[key]], definitions) for key in ("parent_candidate_id", "candidate_id"))
        if parent != child:
            changes.append({"candidate_id": row["candidate_id"], "parent_candidate_id": row["parent_candidate_id"],
                            "parent": parent, "child": child})
    return changes


def interface_figures(episodes: Sequence[Mapping], *, child_means: Mapping[str, float], archive: Mapping[int, list],
                      roots: Mapping[str, str], criterion: Mapping, trusted: bool) -> dict:
    """One interface's episodes of one run: completed, accepted, improvements (gain above min_gain) per completed
    episode (`untrusted` when the run's adaptive anchors are not), diversity over its accepted children, collapse
    against the criterion, control-flow changes."""
    completed = [row for row in episodes if row["outcome"] in COMPLETED]
    accepted = [row for row in completed if row["outcome"] == "accepted"]
    gains = {row["candidate_id"]: gain(row, child_means, archive) for row in accepted}
    improved = sorted(c for c, g in gains.items() if g != UNAVAILABLE and g > criterion["improvement"]["min_gain"])
    figures = diversity(accepted)
    terminal = figures["terminal_only_share"]
    counted = {"improved": improved, "improvements": len(improved),
               "improvements_per_episode": share(len(improved), len(completed))}
    return {"completed": len(completed), "accepted": len(accepted), "gains": gains,
            **(counted if trusted else dict.fromkeys(counted, UNTRUSTED)), **figures,
            "collapsed": terminal if terminal == UNAVAILABLE else terminal > criterion["collapse_threshold"],
            "control_flow_changes": control_flow_changes(accepted, roots, criterion["control_flow"]["definitions"])}


def run_readout(log: Path, rows: Sequence[Mapping], files: Sequence[tuple[int, list]], criterion: Mapping,
                criterion_path: Path) -> dict:
    tasks = [Path(task).name for task in criterion["adaptive_tasks"]]
    pools = [(row["generation"], read_pool(Path(row["results"]), log, criterion_path))
             for row in rows if row["kind"] == "judging" and row["task"] in tasks]
    anchors = adaptive_anchors(pools, tasks, criterion)
    rule = trust_rule(anchors)
    episodes = [row for row in rows if row["kind"] == "episode"]
    roots = {e["candidate_id"]: e["candidate_root"] for _, entries in files for e in entries}
    roots |= {row["candidate_id"]: row["candidate_root"] for row in episodes if row["outcome"] == "accepted"}
    context = {"child_means": adaptive_means(pools, rows, tasks), "archive": dict(files), "roots": roots,
               "criterion": criterion, "trusted": rule == "trusted"}
    interfaces = {name: interface_figures([row for row in episodes if row["interface"] == name], **context)
                  for name in dict.fromkeys(criterion["scale"]["interfaces"])}
    trajectory = [{"generation": n, "incumbent_mean": max(e["mean_value"] for e in entries)} for n, entries in files]
    return {"log": str(log), "anchors": anchors, "improvement_rule": rule, "interfaces": interfaces,
            "trajectory": trajectory}


def expected_candidates(runs: Sequence[Sequence[tuple[int, list]]], ref: str, criterion: Mapping) -> set[str]:
    """The top finalists_per_run of each run's final archive by mean_value (ties: fewer calls, earlier id), the
    reference and the direct seed's entry."""
    top = criterion["scale"]["finalists_per_run"]
    def rank(entry: Mapping) -> tuple:
        return -entry["mean_value"], entry["mean_calls"], entry["candidate_id"]

    finalists = {e["candidate_id"] for files in runs for e in sorted(files[-1][1], key=rank)[:top]}
    direct = {e["candidate_id"] for files in runs for _, entries in files for e in entries if e.get("seed") == DIRECT}
    if len(direct) != 1:
        raise ValueError(f"expected one {DIRECT} seed entry in the archives, found {sorted(direct)}")
    return finalists | {ref} | direct


def validation_rows(grouped: Mapping[str, list], runs: Sequence[Sequence[tuple[int, list]]], ref: str) -> list:
    table = []
    for cid, rows in sorted(grouped.items()):
        held = [next((e["mean_value"] for _, entries in reversed(files) for e in entries if e["candidate_id"] == cid),
                     None) for files in runs]  # its mean_value in each run's latest archive file that holds it
        screening = mean(v for v in held if v is not None) if any(v is not None for v in held) else UNAVAILABLE
        stats = policy_stats(rows)
        validation = stats["mean"]
        table.append({"candidate_id": cid, "is_reference": cid == ref, "screening_mean": screening,
                      "validation_mean": validation,
                      "shrinkage": UNAVAILABLE if UNAVAILABLE in (screening, validation) else screening - validation,
                      "mean_cost": stats["wall_clock_mean"], "provider_calls": stats["calls_mean"],
                      **{key: stats[key] for key in ("valued_mean", "failed", "failure_rate", "incidents",
                                                     "excluded")}})
    return table


def grouped_validation(pool: Mapping, expected: set[str], replicates: int) -> dict[str, list]:
    """candidate_id -> its validation rows (any outcome); the candidates with a completed or failed evaluation must
    be `expected`, each with `replicates` of them (incidents do not count)."""
    grouped: dict[str, list] = {}
    for row in pool["rows"]:
        grouped.setdefault(row["candidate_id"], []).append(row)
    runs = {cid: sum(row["outcome"] in ("completed", "failed") for row in rows) for cid, rows in grouped.items()}
    if {cid for cid, n in runs.items() if n} != expected:
        raise ValueError(f"the validation pool holds {sorted(c for c, n in runs.items() if n)}, not the finalists, "
                         f"reference and direct {sorted(expected)}")
    counts = {cid: runs[cid] for cid in expected if runs[cid] != replicates}
    if counts:
        raise ValueError(f"validation candidates without {replicates} replicates: {counts}")
    return {cid: grouped[cid] for cid in expected}


def validation_readout(pool: Mapping, runs: Sequence[Sequence[tuple[int, list]]], ref: str, criterion: Mapping,
                       sha: str) -> dict:
    """Anchor checks first; the validation table and its unvalued candidates; records.final_choice over the valued
    rows unless the anchors are inverted, spread beyond the limit, or the reference is unvalued (`rule`)."""
    if pool["task"] != Path(criterion["validation_task"]).name or pool["criterion_sha256"] != sha:
        raise ValueError(f"the validation pool ({pool['task']}, criterion {pool['criterion_sha256']}) is not "
                         f"{criterion['validation_task']} under criterion {sha}")
    checks = anchor_checks(pool["anchors"], criterion["anchors"][pool["task"]], criterion["anchor_spread_limit"])
    expected = expected_candidates(runs, ref, criterion)
    table = validation_rows(grouped_validation(pool, expected, criterion["scale"]["validation_replicates"]), runs, ref)
    unvalued = [row["candidate_id"] for row in table if row["validation_mean"] == UNAVAILABLE]
    rule = ("anchors_inverted" if not checks["anchors_ok"] else "anchor_spread" if not checks["spread_ok"]
            else "reference_unvalued" if ref in unvalued else "chosen")
    valued = [row | {"validation_success": row["validation_mean"]} for row in table
              if row["candidate_id"] not in unvalued]
    choice = UNAVAILABLE if rule != "chosen" else final_choice(
        valued, criterion=criterion["final_choice"] | {"criterion_sha256": sha})
    return {"validation": table, "unvalued": unvalued, "final_choice": choice, "rule": rule, **checks}


def phase2_readout(logs: Sequence[Path], archives: Sequence[Path], validation_pool: Mapping | None,
                   criterion: Path) -> dict:
    """`logs` and `archives` pair up per run (each run's log.jsonl and archive directory); `validation_pool` is
    read_pool's result for the validation pool, or None before validation; `criterion` is criteria/phase2.json's
    path (its SHA-256 is checked against every pool)."""
    criterion_path = Path(criterion)
    rules, sha = json.loads(criterion_path.read_text()), sha256_file(criterion_path)
    runs = [archive_files(directory) for directory in archives]
    rows = [read_records(Path(log)) for log in logs]
    ref = reference(logs, rows)
    result = {"min_gain": rules["improvement"]["min_gain"], "collapse_threshold": rules["collapse_threshold"],
              "reference": ref, "runs": [run_readout(Path(log), run_rows, files, rules, criterion_path)
                                         for log, run_rows, files in zip(logs, rows, runs, strict=True)]}
    if validation_pool is None:
        return result | dict.fromkeys(("validation", "unvalued", "final_choice", "rule", "anchors_ok",
                                       "anchor_spread", "spread_ok"), UNAVAILABLE)
    return result | validation_readout(validation_pool, runs, ref, rules, sha)
