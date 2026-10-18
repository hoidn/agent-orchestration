"""Blind scoring of structural search evaluations and the Phase 1 and Phase 2 readouts.

Plan: docs/plans/2026-10-18-orc-structural-search-live-phase1-plan.md, Task 3. Every evaluation runs through the
comparison harness's `run_arm` with the evaluation id as its arm, so `summarize.py` treats each evaluation as its
own arm and knows nothing of policies. This module adds the three steps around the harness:

  pool_evaluations   collects (`prepare.collect`) every completed evaluation of one task in the driver's log
                     (<evidence>/log.jsonl) and builds the harness's blind pool: final patches shuffled, blocked
                     by policy and dealt round-robin into batches of at most ten clones, both anchors repeated in
                     each. The harness's `pool` composes batches only for its own named arms (`pool.compose`), so
                     this function reuses `pool`'s helpers with its own batches; every other refusal (uncollected,
                     unscanned, hits without a verdict, Fable, mixed bases, path guards) is the harness's.
  join_scores        maps each `summarize` run row (its `run` path, the records directory) to the evaluation
                     record whose `records_dir` it is; values, hidden fractions, calls and wall clock are
                     summarize's, never re-derived. An unmapped run, or one whose arm is not the record's
                     evaluation id, raises.
  read_pool          one task's pool: joined rows plus summarize's anchors, agreement and excluded judges, and
                     the completed evaluations no run row names (`unpooled`); refuses another criterion's results.
  phase1_readout     per task: catalog policy, child and pooled `unguided` stats; separation over arms with two or
                     more valued evaluations; DIRECT's rank; anchor order and cross-batch spread per judge; the
                     I1 diversity figures of the driver's readout (<evidence>/readout.json), collapse against the
                     criterion's threshold, and the roadmap decision. Every rule parameter comes from
                     criteria/phase1.json.
  readout --phase 2  scoring_phase2.phase2_readout (criteria/phase2.json), built on read_pool and anchor_checks.

A policy is the seed stem for a catalog evaluation and `<mode>:<candidate_id>` otherwise (`unguided:` for an accepted
I1 child of mode 1, `adaptive:` for every mode 2 evaluation).

  python -m experiments.orc_structural_search.scoring pool --evidence E --task T --out P --criterion C \
      --judge claude-opus-5-5 --judge gpt-6-sol=$RT/experiments/compare/providers/score_codex.json
  python -m experiments.orc_structural_search.scoring readout --log E/log.jsonl --driver-readout E/readout.json \
      --criterion C P1/records/results.json P2/records/results.json
  python -m experiments.orc_structural_search.scoring readout --phase 2 --criterion C \
      --log E2/run-1/log.jsonl --archive E2/run-1/archive [--log ... --archive ...] \
      [--validation-log V/log.jsonl V/pool/records/results.json]
"""

import argparse
import json
import math
import random
import secrets
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from statistics import mean, stdev, variance

from experiments.compare import pool as pooling, prepare
from experiments.compare.repos import dump, guard, load, runtime_commit, sha256_file, visible_in_sandbox
from experiments.orc_structural_search.records import UNAVAILABLE, read_records

DIRECT = "direct"  # the DIRECT seed's stem
UNGUIDED = "unguided"  # the one arm pooling every accepted I1 child's evaluations
BATCH_CLONES = 10  # harness D4: at most ten clones per batch, both anchors included and repeated in each
ANCHORS_PER_BATCH = 2
DIVERSITY = ("episodes", "distinct_skeletons", "revisit_rate", "terminal_only_share",
             "allocation_distinct")  # driver readout keys reported as they are; collapse is judged on the criterion


def policy(record: Mapping) -> str:
    return record["seed"] if record["mode"] == "catalog" else f"{record['mode']}:{record['candidate_id']}"


def pool_evaluations(evidence_root: Path, task_package: Path, *, out: Path, judges: Sequence[str],
                     criterion: Path, include: Callable[[Mapping], bool] = lambda row: True) -> Path:
    """Collect every completed evaluation of `task_package` in the log that `include` keeps (mode 2: one
    generation's, or the validation split's) and build the blind pool at `out` (batches of at most ten clones,
    anchors repeated); return the pool directory. Judges are MODEL[=PROVIDERS_JSON] as for `prepare.py pool` and
    must be the criterion's."""
    task, out = Path(task_package).resolve(), Path(out).resolve()
    names = sorted(spec.partition("=")[0] for spec in judges)
    if names != sorted(json.loads(Path(criterion).read_text())["judges"]):
        raise ValueError(f"judges {names} are not the criterion's {criterion}")
    completed = [row for row in read_records(Path(evidence_root) / "log.jsonl")
                 if row["kind"] == "evaluation" and row["task_id"] == task.name and row["outcome"] == "completed"
                 and include(row)]
    if not completed:
        raise ValueError(f"no completed evaluation of {task.name} in {evidence_root}/log.jsonl")
    records, policies = {}, {}
    for row in completed:
        path = Path(row["records_dir"]).resolve()
        prepare.collect(path)
        records[str(path)], policies[str(path)] = load(path / "record.json"), policy(row)
    build_pool(task, Path(criterion), out, judges, records, key=lambda final: policies[final[0]])
    return out


def split_batches(finals: Sequence, key: Callable, size: int = BATCH_CLONES - ANCHORS_PER_BATCH) -> list[list]:
    """`finals` shuffled, stable-sorted by `key` (the policy) and dealt round-robin into the fewest batches of at
    most `size` members: sizes differ by at most one and a policy's replicates land in different batches when
    there are several (the anchors join every batch in pool.build_batches)."""
    shuffled = list(finals)
    random.SystemRandom().shuffle(shuffled)
    ordered = sorted(shuffled, key=key)
    count = math.ceil(len(ordered) / size)
    return [ordered[k::count] for k in range(count)]


# ponytail: copy of experiments/compare/pool.py::pool with split_batches in place of pool.compose (which batches
# only the harness's named arms); keep the mapping and checks in sync with that function.
def build_pool(task: Path, criterion: Path, out: Path, judges: Sequence[str], records: dict[str, dict], *,
               key: Callable) -> None:
    """`pool.pool` with every usable run's final patch in batches of at most ten clones, anchors repeated."""
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
    clones, members = pooling.build_batches(out, task, ref, split_batches(finals, key))
    default = Path(ref["runtime"]) / "experiments/compare/score.providers.json"
    mapping = {"task": str(task), "criterion_sha256": sha256_file(criterion), "compare_base": ref["compare_base"],
               "main": ref["main"], "runtime": ref["runtime"], "runtime_commit": commit, "created_at": time.time(),
               "judges": {name: {"dir": secrets.token_hex(8), "providers": str(Path(providers or default).resolve())}
                          for name, _, providers in (spec.partition("=") for spec in judges)},
               "runs": rows, "clones": clones, "batches": members}
    dump(out / "records" / "mapping.json", mapping)
    pooling.write_score_inputs(out, mapping, (task / "intent.txt").read_text(), Path(ref["runtime"]))
    (out / "clones").chmod(pooling.HIDDEN_DIR)
    print(f"# {len(clones)} clones in {len(members)} batches; run the judges one after another, "
          f"each followed by: prepare.py verify-pool --pool {out}")


def join_scores(results_json: Path, log: Path) -> list[dict]:
    """One row per summarize run: {evaluation_id, candidate_id, mode, policy, task, replicate, value, hidden, calls,
    wall_clock_sec}."""
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
        rows.append({"evaluation_id": record["evaluation_id"], "candidate_id": record["candidate_id"],
                     "mode": record["mode"], "policy": policy(record), "task": record["task_id"],
                     "replicate": record["replicate"], "value": run["value"], "hidden": run.get("hidden_value"),
                     "calls": run["calls"], "wall_clock_sec": run["wall_clock_sec"]})
    return rows


def read_pool(results_json: Path, log: Path, criterion: Path) -> dict:
    """One task's pool for phase1_readout (and each pool of scoring_phase2): joined rows, summarize's anchors,
    agreement and excluded judges, the criterion hash it was checked against, and the
    completed evaluations of the task in the log that no run row names (`unpooled`). Refuses results summarized
    under another criterion file, and runs of several tasks."""
    results, sha = json.loads(Path(results_json).read_text()), sha256_file(criterion)
    if results["criterion_sha256"] != sha:
        raise ValueError(f"{results_json} was summarized under criterion sha256 {results['criterion_sha256']}, "
                         f"not {criterion}'s {sha}")
    rows = join_scores(results_json, log)
    tasks = {row["task"] for row in rows}
    if len(tasks) != 1:
        raise ValueError(f"{results_json}: expected the runs of one task, found {sorted(tasks)}")
    task, pooled = tasks.pop(), {row["evaluation_id"] for row in rows}
    unpooled = sorted(r["evaluation_id"] for r in read_records(log) if r["kind"] == "evaluation"
                      and r["task_id"] == task and r["outcome"] == "completed" and r["evaluation_id"] not in pooled)
    return {"task": task, "results": str(results_json), "rows": rows, "anchors": results["anchors"],
            "agreement": results["agreement"], "excluded_judges": results["excluded_judges"], "unpooled": unpooled,
            "criterion_sha256": sha}


def pooled_sd(groups: Sequence[Sequence[float]]) -> float | str:
    """sqrt(sum((n-1) s^2) / sum(n-1)) over groups with two or more values; unavailable without any."""
    multi = [g for g in groups if len(g) > 1]
    df = sum(len(g) - 1 for g in multi)
    return math.sqrt(sum((len(g) - 1) * variance(g) for g in multi) / df) if df else UNAVAILABLE


def policy_stats(rows: Sequence[Mapping]) -> dict:
    values, hidden = [r["value"] for r in rows], [r["hidden"] for r in rows if r["hidden"] is not None]
    return {"runs": len(values), "mean": mean(values), "sd": stdev(values) if len(values) > 1 else UNAVAILABLE,
            "hidden_mean": mean(hidden) if hidden else UNAVAILABLE,
            "calls_mean": mean(r["calls"] for r in rows), "wall_clock_mean": mean(r["wall_clock_sec"] for r in rows)}


def anchor_checks(anchors: Sequence[Mapping], roles: Mapping[str, str], spread_limit: float) -> dict:
    """anchors_ok: in every batch and for every judge the upstream anchor's total is strictly above the stub's (a
    missing one fails); anchor_spread: per judge, the largest difference of one anchor's total across batches;
    spread_ok: no spread above `spread_limit`."""
    totals = {(a["batch"], a["judge"], a["anchor"]): a["total"] for a in anchors}
    pairs = {(batch, judge) for batch, judge, _ in totals}
    up, stub = roles["upstream"], roles["stub"]
    ok = bool(pairs) and all(totals.get((b, j, up), -math.inf) > totals.get((b, j, stub), math.inf) for b, j in pairs)
    by_judge: dict[str, dict[str, list]] = {}
    for (_, judge, name), total in totals.items():
        by_judge.setdefault(judge, {}).setdefault(name, []).append(total)
    spread = {judge: max(max(v) - min(v) for v in names.values()) for judge, names in sorted(by_judge.items())}
    return {"anchors_ok": ok, "anchor_spread": spread, "spread_ok": all(s <= spread_limit for s in spread.values())}


def separation(means: Mapping[str, float], sd: float | str, rules: Mapping) -> dict:
    """Over the compared arms: gap_separated (largest gap between means above max(tolerance_sd x pooled SD,
    min_tolerance)), DIRECT's competition rank (1 = best) and whether DIRECT alone is above every other arm by more
    than the threshold."""
    threshold = UNAVAILABLE if sd == UNAVAILABLE else max(rules["tolerance_sd"] * sd, rules["min_tolerance"])
    gap = max(means.values()) - min(means.values()) if means else 0.0
    others = [m for p, m in means.items() if p != DIRECT]
    direct = means.get(DIRECT)
    known = threshold != UNAVAILABLE
    return {"threshold": threshold, "max_gap": gap, "gap_separated": known and len(means) > 1 and gap > threshold,
            "direct_rank": UNAVAILABLE if direct is None else 1 + sum(m > direct for m in others),
            "direct_sole_winner": known and direct is not None and bool(others) and direct - max(others) > threshold}


def arms(rows: Sequence[Mapping]) -> tuple[dict, dict]:
    """(catalog policy -> valued rows, unguided child -> valued rows)."""
    catalog: dict[str, list] = {}
    children: dict[str, list] = {}
    for row in rows:
        if row["value"] is not None:
            (catalog if row["mode"] == "catalog" else children).setdefault(row["policy"], []).append(row)
    return catalog, children


def task_readout(pool: Mapping, criterion: Mapping) -> dict:
    """Descriptive stats per catalog policy, per child and for the pooled `unguided` arm; separation over the arms
    with two or more valued evaluations (catalog policies and the pooled unguided arm), counted only when the
    anchors' cross-batch spread is within the limit; anchor checks, agreement, excluded judges, unpooled runs."""
    rules = criterion["separation"]
    catalog, children = arms(pool["rows"])
    unguided = [row for group in children.values() for row in group]
    compared = {p: [r["value"] for r in g] for p, g in [*catalog.items(), (UNGUIDED, unguided)] if len(g) > 1}
    sd = pooled_sd(list(compared.values()))
    split = separation({p: mean(v) for p, v in compared.items()}, sd, rules)
    checks = anchor_checks(pool["anchors"], criterion["anchors"][pool["task"]], rules["anchor_spread_limit"])
    return {"policies": {p: policy_stats(g) for p, g in sorted(catalog.items())},
            "children": {p: policy_stats(g) for p, g in sorted(children.items())},
            UNGUIDED: policy_stats(unguided) if unguided else UNAVAILABLE, "compared": sorted(compared),
            "pooled_sd": sd, **split, **checks, "separated": split["gap_separated"] and checks["spread_ok"],
            "agreement": pool["agreement"], "excluded_judges": pool["excluded_judges"], "unpooled": pool["unpooled"]}


def decision(tasks: Mapping[str, Mapping], collapsed: bool | str, min_tasks: int) -> dict:
    """Roadmap "Decision Points And Stop Rules", first rule that fires: an anchor inversion in any pool
    (anchors_inverted); fewer than `min_tasks` separated tasks (within_tolerance); DIRECT the sole winner on every
    separated task (direct_sole_winner); the only Phase 1 interface (I1) without a collapse figure, no accepted
    child, so the adaptive claim is untested (collapse_unavailable), or collapsed (collapsed); otherwise separated
    and Phase 2 is selected."""
    separated = sorted(t for t, r in tasks.items() if r["separated"])
    if not all(r["anchors_ok"] for r in tasks.values()):
        rule = "anchors_inverted"
    elif len(separated) < min_tasks:
        rule = "within_tolerance"
    elif all(tasks[t]["direct_sole_winner"] for t in separated):
        rule = "direct_sole_winner"
    elif collapsed == UNAVAILABLE:
        rule = "collapse_unavailable"
    elif collapsed:
        rule = "collapsed"
    else:
        rule = "separated"
    return {"phase2_selected": rule == "separated", "rule": rule, "separated_tasks": separated}


def phase1_readout(pools: Sequence[Mapping], driver_readout: Mapping, criterion: Mapping) -> dict:
    """`pools` from read_pool, one per criterion task; `driver_readout` is the driver's <evidence>/readout.json;
    `criterion` is criteria/phase1.json (separation rules, anchor roles, collapse threshold). Collapse is the
    driver's terminal-only share above the criterion's threshold."""
    expected = sorted(Path(task).name for task in criterion["tasks"])
    if sorted(pool["task"] for pool in pools) != expected:
        raise ValueError(f"expected one pool per criterion task {expected}, got {sorted(p['task'] for p in pools)}")
    tasks = {pool["task"]: task_readout(pool, criterion) for pool in sorted(pools, key=lambda p: p["task"])}
    share = driver_readout["terminal_only_share"]
    collapsed = share if share == UNAVAILABLE else share > criterion["collapse_threshold"]
    unguided = {key: driver_readout[key] for key in DIVERSITY} | {"collapsed": collapsed}
    return {"separation": criterion["separation"], "collapse_threshold": criterion["collapse_threshold"],
            "tasks": tasks, "unguided": unguided,
            **decision(tasks, collapsed, criterion["separation"]["min_tasks"])}



def readout_command(a: argparse.Namespace) -> dict:
    if a.phase == 2:
        from experiments.orc_structural_search.scoring_phase2 import phase2_readout  # it imports this module
        if len(a.results) > 1 or bool(a.results) != bool(a.validation_log):
            raise SystemExit("--phase 2 takes at most one results.json, the validation pool's, with --validation-log")
        pool = read_pool(a.results[0], a.validation_log, a.criterion) if a.results else None
        return phase2_readout(a.log, a.archive, pool, a.criterion)
    if len(a.log) != 1 or a.driver_readout is None or not a.results:
        raise SystemExit("--phase 1 takes one --log, --driver-readout and each task pool's results.json")
    pools = [read_pool(results, a.log[0], a.criterion) for results in a.results]
    return phase1_readout(pools, json.loads(a.driver_readout.read_text()), json.loads(a.criterion.read_text()))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    pool_cmd = sub.add_parser("pool")
    for name in ("--evidence", "--task", "--out", "--criterion"):
        pool_cmd.add_argument(name, type=Path, required=True)
    pool_cmd.add_argument("--judge", action="append", required=True, metavar="MODEL[=PROVIDERS_JSON]")
    readout_cmd = sub.add_parser("readout")
    readout_cmd.add_argument("--phase", type=int, choices=(1, 2), default=1)
    readout_cmd.add_argument("--criterion", type=Path, required=True)
    readout_cmd.add_argument("--log", type=Path, action="append", required=True,
                             help="phase 1: the driver's log; phase 2: one per run, in --archive order")
    readout_cmd.add_argument("--driver-readout", type=Path, help="phase 1: the driver's readout.json")
    readout_cmd.add_argument("--archive", type=Path, action="append", default=[],
                             help="phase 2: each run's archive directory")
    readout_cmd.add_argument("--validation-log", type=Path, help="phase 2: the log of the validation evaluations")
    readout_cmd.add_argument("results", type=Path, nargs="*",
                             help="phase 1: each task pool's records/results.json; phase 2: the validation pool's")
    a = parser.parse_args(argv)
    if a.command == "pool":
        print(pool_evaluations(a.evidence, a.task, out=a.out, judges=a.judge, criterion=a.criterion))
        return
    print(json.dumps(readout_command(a), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
