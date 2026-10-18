"""Blind scoring of structural search evaluations and the Phase 1 readout.

Plan: docs/plans/2026-10-18-orc-structural-search-live-phase1-plan.md, Task 3. Every evaluation runs through the
comparison harness's `run_arm` with the evaluation id as its arm, so `summarize.py` treats each evaluation as its
own arm and knows nothing of policies. This module adds the three steps around the harness:

  pool_evaluations   collects (`prepare.collect`) every completed evaluation of one task in the driver's log
                     (<evidence>/log.jsonl) and builds the harness's blind pool with ONE batch of all final
                     patches plus the package's anchors. The harness's `pool` composes batches only for its own
                     named arms (`pool.compose`), so this function reuses `pool`'s helpers with that one batch;
                     every other refusal (uncollected, unscanned, hits without a verdict, Fable, mixed bases,
                     paths under the main checkout or a sandbox mount) is the harness's.
  join_scores        maps each `summarize` run row (its `run` path, the records directory) to the evaluation
                     record whose `records_dir` it is; values, hidden fractions, calls and wall clock are
                     summarize's, never re-derived. An unmapped run, or one whose arm is not the record's
                     evaluation id, raises.
  phase1_readout     per task and policy mean and within-arm SD, separation per task, DIRECT's rank, the
                     unguided I1 diversity and collapse figures of the driver's readout (<evidence>/readout.json)
                     and the roadmap decision. Rules are frozen in criteria/phase1.json.

A policy is the seed stem for a catalog evaluation and `unguided:<candidate_id>` for an accepted I1 child.

  python -m experiments.orc_structural_search.scoring pool --evidence E --task T --out P --criterion C \
      --judge claude-opus-5-5 --judge gpt-6-sol=$RT/experiments/compare/providers/score_codex.json
  python -m experiments.orc_structural_search.scoring readout --log E/log.jsonl --driver-readout E/readout.json \
      P1/records/results.json P2/records/results.json
"""

import argparse
import json
import math
import secrets
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import mean, stdev, variance

from experiments.compare import pool as pooling, prepare
from experiments.compare.repos import dump, guard, load, runtime_commit, sha256_file, visible_in_sandbox
from experiments.orc_structural_search.records import UNAVAILABLE, read_records

DIRECT = "direct"  # the DIRECT seed's stem
MIN_SEPARATED_TASKS = 2  # roadmap "Phase 1 separation": required on at least two tasks
DIVERSITY = ("episodes", "distinct_skeletons", "revisit_rate", "terminal_only_share", "allocation_distinct",
             "collapsed")  # driver readout keys reported as they are


def policy(record: Mapping) -> str:
    return record["seed"] if record["mode"] == "catalog" else f"unguided:{record['candidate_id']}"


def pool_evaluations(evidence_root: Path, task_package: Path, *, out: Path, judges: Sequence[str],
                     criterion: Path) -> Path:
    """Collect every completed evaluation of `task_package` in the log and build the blind pool at `out` with one
    batch (all final patches plus anchors); return the pool directory. Judges are MODEL[=PROVIDERS_JSON] as for
    `prepare.py pool` and must be the criterion's."""
    task, out = Path(task_package).resolve(), Path(out).resolve()
    names = sorted(spec.partition("=")[0] for spec in judges)
    if names != sorted(json.loads(Path(criterion).read_text())["judges"]):
        raise ValueError(f"judges {names} are not the criterion's {criterion}")
    completed = [row for row in read_records(Path(evidence_root) / "log.jsonl")
                 if row["kind"] == "evaluation" and row["task_id"] == task.name and row["outcome"] == "completed"]
    if not completed:
        raise ValueError(f"no completed evaluation of {task.name} in {evidence_root}/log.jsonl")
    records = {}
    for row in completed:
        path = Path(row["records_dir"]).resolve()
        prepare.collect(path)
        records[str(path)] = load(path / "record.json")
    build_pool(task, Path(criterion), out, judges, records)
    return out


def build_pool(task: Path, criterion: Path, out: Path, judges: Sequence[str], records: dict[str, dict]) -> None:
    """`pool.pool` with one batch of every usable run's final patch (pool.compose names only the harness's arms)."""
    ref = next(iter(records.values()))
    if {(r["task"], r["compare_base"]) for r in records.values()} != {(str(task), ref["compare_base"])}:
        raise SystemExit("runs in one pool must share the task and the seeded commit")
    guard(Path(ref["main"]), out)
    visible_in_sandbox(out)
    commit = runtime_commit(ref["runtime"])
    rows, usable = pooling.pool_runs(records)
    finals = [(path, rec, ["final"]) for runs in usable.values() for path, rec in runs]
    if not finals:
        raise SystemExit("no completed, uncontaminated evaluation to pool")
    for directory in (out / "clones", out / "judges", out / "records" / "patches"):
        directory.mkdir(parents=True)
    clones, members = pooling.build_batches(out, task, ref, [finals])
    default = Path(ref["runtime"]) / "experiments/compare/score.providers.json"
    mapping = {"task": str(task), "criterion_sha256": sha256_file(criterion), "compare_base": ref["compare_base"],
               "main": ref["main"], "runtime": ref["runtime"], "runtime_commit": commit, "created_at": time.time(),
               "judges": {name: {"dir": secrets.token_hex(8), "providers": str(Path(providers or default).resolve())}
                          for name, _, providers in (spec.partition("=") for spec in judges)},
               "runs": rows, "clones": clones, "batches": members}
    dump(out / "records" / "mapping.json", mapping)
    pooling.write_score_inputs(out, mapping, (task / "intent.txt").read_text(), Path(ref["runtime"]))
    (out / "clones").chmod(pooling.HIDDEN_DIR)
    print(f"# {len(clones)} clones in one batch; run the judges one after another, "
          f"each followed by: prepare.py verify-pool --pool {out}")


def join_scores(results_json: Path, log: Path) -> list[dict]:
    """One row per summarize run: {candidate_id, policy, task, replicate, value, hidden, calls, wall_clock_sec}."""
    evaluations = {str(Path(row["records_dir"]).resolve()): row
                   for row in read_records(log) if row["kind"] == "evaluation"}
    rows = []
    for run in json.loads(Path(results_json).read_text())["runs"]:
        record = evaluations.get(str(Path(run["run"]).resolve()))
        if record is None:
            raise ValueError(f"{results_json}: run {run['run']} maps to no evaluation record in {log}")
        if run["arm"] != record["evaluation_id"]:
            raise ValueError(f"{results_json}: run {run['run']} has arm {run['arm']} but its records directory is "
                             f"evaluation {record['evaluation_id']}'s")
        rows.append({"candidate_id": record["candidate_id"], "policy": policy(record), "task": record["task_id"],
                     "replicate": record["replicate"], "value": run["value"], "hidden": run.get("hidden_value"),
                     "calls": run["calls"], "wall_clock_sec": run["wall_clock_sec"]})
    return rows


def pooled_sd(groups: Sequence[Sequence[float]]) -> float | str:
    """sqrt(sum((n-1) s^2) / sum(n-1)) over groups with two or more values; unavailable without any."""
    multi = [g for g in groups if len(g) > 1]
    df = sum(len(g) - 1 for g in multi)
    return math.sqrt(sum((len(g) - 1) * variance(g) for g in multi) / df) if df else UNAVAILABLE


def policy_stats(values: Sequence[float], rows: Sequence[Mapping]) -> dict:
    hidden = [r["hidden"] for r in rows if r["hidden"] is not None]
    return {"runs": len(values), "mean": mean(values), "sd": stdev(values) if len(values) > 1 else UNAVAILABLE,
            "hidden_mean": mean(hidden) if hidden else UNAVAILABLE,
            "calls_mean": mean(r["calls"] for r in rows), "wall_clock_mean": mean(r["wall_clock_sec"] for r in rows)}


def separation(means: Mapping[str, float], sd: float | str, tolerance_sd: float) -> dict:
    """Separation (largest gap between policy means above tolerance_sd x pooled SD), DIRECT's competition rank
    (1 = best) and whether DIRECT alone is separated above every other policy."""
    threshold = UNAVAILABLE if sd == UNAVAILABLE else tolerance_sd * sd
    gap = max(means.values()) - min(means.values()) if means else 0.0
    others = [m for p, m in means.items() if p != DIRECT]
    direct = means.get(DIRECT)
    known = threshold != UNAVAILABLE
    return {"threshold": threshold, "max_gap": gap, "separated": known and len(means) > 1 and gap > threshold,
            "direct_rank": UNAVAILABLE if direct is None else 1 + sum(m > direct for m in others),
            "direct_sole_winner": known and direct is not None and bool(others) and direct - max(others) > threshold}


def task_readout(rows: Sequence[Mapping], tolerance_sd: float) -> dict:
    """Per policy stats of the valued rows, the pooled within-arm SD and the separation figures."""
    groups: dict[str, list] = {}
    for row in rows:
        if row["value"] is not None:
            groups.setdefault(row["policy"], []).append(row)
    policies = {p: policy_stats([r["value"] for r in g], g) for p, g in sorted(groups.items())}
    sd = pooled_sd([[r["value"] for r in g] for g in groups.values()])
    return {"policies": policies, "pooled_sd": sd,
            **separation({p: s["mean"] for p, s in policies.items()}, sd, tolerance_sd)}


def decision(tasks: Mapping[str, Mapping], unguided: Mapping) -> dict:
    """Roadmap "Decision Points And Stop Rules", first rule that fires: fewer than two separated tasks
    (within_tolerance), DIRECT the sole winner on every separated task (direct_sole_winner), the only Phase 1
    interface (I1) collapsed (collapsed); otherwise separated and Phase 2 is selected. An unavailable collapse
    figure (no accepted child) does not fire."""
    separated = sorted(t for t, r in tasks.items() if r["separated"])
    if len(separated) < MIN_SEPARATED_TASKS:
        rule = "within_tolerance"
    elif all(tasks[t]["direct_sole_winner"] for t in separated):
        rule = "direct_sole_winner"
    elif unguided["collapsed"] is True:
        rule = "collapsed"
    else:
        rule = "separated"
    return {"phase2_selected": rule == "separated", "rule": rule, "separated_tasks": separated}


def phase1_readout(rows: Sequence[Mapping], driver_readout: Mapping, *, tolerance_sd: float = 2.0) -> dict:
    """`rows` from join_scores (every task's pool); `driver_readout` is the driver's <evidence>/readout.json."""
    tasks = {task: task_readout([r for r in rows if r["task"] == task], tolerance_sd)
             for task in sorted({r["task"] for r in rows})}
    unguided = {key: driver_readout[key] for key in DIVERSITY}
    return {"tolerance_sd": tolerance_sd, "tasks": tasks, "unguided": unguided, **decision(tasks, unguided)}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    pool_cmd = sub.add_parser("pool")
    for name in ("--evidence", "--task", "--out", "--criterion"):
        pool_cmd.add_argument(name, type=Path, required=True)
    pool_cmd.add_argument("--judge", action="append", required=True, metavar="MODEL[=PROVIDERS_JSON]")
    readout_cmd = sub.add_parser("readout")
    readout_cmd.add_argument("--log", type=Path, required=True)
    readout_cmd.add_argument("--driver-readout", type=Path, required=True)
    readout_cmd.add_argument("--tolerance-sd", type=float, default=2.0)
    readout_cmd.add_argument("results", type=Path, nargs="+", help="each task pool's records/results.json")
    a = parser.parse_args(argv)
    if a.command == "pool":
        print(pool_evaluations(a.evidence, a.task, out=a.out, judges=a.judge, criterion=a.criterion))
        return
    rows = [row for results in a.results for row in join_scores(results, a.log)]
    print(json.dumps(phase1_readout(rows, json.loads(a.driver_readout.read_text()), tolerance_sd=a.tolerance_sd),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
