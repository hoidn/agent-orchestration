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
  phase2_readout     per mode 2 run and interface (never pooled): completed and accepted episodes, improvements
                     over the parent's archived mean, diversity and collapse, control-flow changes; the archive
                     trajectory; the validation table with shrinkage, the final choice and the validation anchors.
                     Every rule parameter comes from criteria/phase2.json.

A policy is the seed stem for a catalog evaluation and `unguided:<candidate_id>` for an accepted I1 child.

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
from experiments.orc_structural_search.readout import diversity, share
from experiments.orc_structural_search.records import UNAVAILABLE, control_heads, final_choice, read_records

DIRECT = "direct"  # the DIRECT seed's stem
UNGUIDED = "unguided"  # the one arm pooling every accepted I1 child's evaluations
BATCH_CLONES = 10  # harness D4: at most ten clones per batch, both anchors included and repeated in each
ANCHORS_PER_BATCH = 2
DIVERSITY = ("episodes", "distinct_skeletons", "revisit_rate", "terminal_only_share",
             "allocation_distinct")  # driver readout keys reported as they are; collapse is judged on the criterion


def policy(record: Mapping) -> str:
    return record["seed"] if record["mode"] == "catalog" else f"unguided:{record['candidate_id']}"


def pool_evaluations(evidence_root: Path, task_package: Path, *, out: Path, judges: Sequence[str],
                     criterion: Path) -> Path:
    """Collect every completed evaluation of `task_package` in the log and build the blind pool at `out` (batches of
    at most ten clones, anchors repeated); return the pool directory. Judges are MODEL[=PROVIDERS_JSON] as for
    `prepare.py pool` and must be the criterion's."""
    task, out = Path(task_package).resolve(), Path(out).resolve()
    names = sorted(spec.partition("=")[0] for spec in judges)
    if names != sorted(json.loads(Path(criterion).read_text())["judges"]):
        raise ValueError(f"judges {names} are not the criterion's {criterion}")
    completed = [row for row in read_records(Path(evidence_root) / "log.jsonl")
                 if row["kind"] == "evaluation" and row["task_id"] == task.name and row["outcome"] == "completed"]
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
    """One task's pool for phase1_readout (and the validation pool for phase2_readout): joined rows, summarize's anchors, agreement and excluded judges, and the
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


# Phase 2. A run is its log and its archive directory (<E2>/archive/gen-<n>.json, each a list of archive entries
# {candidate_id, candidate_root, mean_value, mean_calls, ...}); judged values come from the log's `judging` rows
# ({generation, task, pool, results}: that pool's results.json), joined by join_scores.
COMPLETED = ("accepted", "rejected")  # an episode that reached a verdict; stopped ones (exhausted, incident) did not


def archive_files(directory: Path) -> list[tuple[int, list[dict]]]:
    """(generation, entries) per gen-<n>.json, in generation order."""
    files = [(int(p.stem.removeprefix("gen-")), json.loads(p.read_text())) for p in Path(directory).glob("gen-*.json")]
    if not files:
        raise ValueError(f"no gen-<n>.json archive file in {directory}")
    return sorted(files, key=lambda f: f[0])


def leader(entries: Sequence[Mapping]) -> Mapping:
    """The incumbent (Decision 6): highest mean_value, then fewer mean_calls, then the earlier candidate_id."""
    return min(entries, key=lambda e: (-e["mean_value"], e["mean_calls"], e["candidate_id"]))


def adaptive_means(log: Path, rows: Sequence[Mapping], tasks: Sequence[str]) -> dict[str, float]:
    """candidate_id -> the mean over `tasks` of its per-task mean judged value, for candidates valued on every task."""
    values: dict[str, dict[str, list]] = {}
    for judging in (row for row in rows if row["kind"] == "judging"):
        for row in join_scores(Path(judging["results"]), log):
            if row["task"] in tasks and row["value"] is not None:
                values.setdefault(row["candidate_id"], {}).setdefault(row["task"], []).append(row["value"])
    return {cid: mean(mean(per[t]) for t in tasks) for cid, per in values.items() if set(per) >= set(tasks)}


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
                      roots: Mapping[str, str], criterion: Mapping) -> dict:
    """One interface's episodes of one run: completed, accepted, improvements (gain above min_gain) per completed
    episode, diversity over its accepted children, collapse against the criterion, control-flow changes."""
    completed = [row for row in episodes if row["outcome"] in COMPLETED]
    accepted = [row for row in completed if row["outcome"] == "accepted"]
    gains = {row["candidate_id"]: gain(row, child_means, archive) for row in accepted}
    improved = sorted(c for c, g in gains.items() if g != UNAVAILABLE and g > criterion["improvement"]["min_gain"])
    figures = diversity(accepted)
    terminal = figures["terminal_only_share"]
    return {"completed": len(completed), "accepted": len(accepted), "gains": gains, "improved": improved,
            "improvements": len(improved), "improvements_per_episode": share(len(improved), len(completed)),
            **figures, "collapsed": terminal if terminal == UNAVAILABLE else terminal > criterion["collapse_threshold"],
            "control_flow_changes": control_flow_changes(accepted, roots, criterion["control_flow"]["definitions"])}


def run_readout(log: Path, files: Sequence[tuple[int, list]], criterion: Mapping) -> dict:
    rows = read_records(log)
    episodes = [row for row in rows if row["kind"] == "episode"]
    roots = {e["candidate_id"]: e["candidate_root"] for _, entries in files for e in entries}
    roots |= {row["candidate_id"]: row["candidate_root"] for row in episodes if row["outcome"] == "accepted"}
    means = adaptive_means(log, rows, [Path(task).name for task in criterion["adaptive_tasks"]])
    context = {"child_means": means, "archive": dict(files), "roots": roots, "criterion": criterion}
    interfaces = {name: interface_figures([row for row in episodes if row["interface"] == name], **context)
                  for name in dict.fromkeys(criterion["scale"]["interfaces"])}
    trajectory = [{"generation": n, "incumbent": leader(entries)["candidate_id"],
                   "mean_value": leader(entries)["mean_value"]} for n, entries in files]
    return {"log": str(log), "interfaces": interfaces, "trajectory": trajectory}


def reference(runs: Sequence[Sequence[tuple[int, list]]]) -> str:
    """The reference seed: the incumbent of every run's earliest archive file (the initial incumbent)."""
    found = {leader(files[0][1])["candidate_id"] for files in runs}
    if len(found) != 1:
        raise ValueError(f"the runs' earliest archives name different incumbents {sorted(found)}")
    return found.pop()


def screening_mean(cid: str, runs: Sequence[Sequence[tuple[int, list]]]) -> float | str:
    """The mean over runs of the candidate's mean_value in the latest archive file that holds it."""
    latest = [next((e["mean_value"] for _, entries in reversed(files) for e in entries if e["candidate_id"] == cid),
                   None) for files in runs]
    found = [value for value in latest if value is not None]
    return mean(found) if found else UNAVAILABLE


def validation_rows(pool: Mapping, runs: Sequence[Sequence[tuple[int, list]]]) -> list[dict]:
    grouped: dict[str, list] = {}
    for row in pool["rows"]:
        grouped.setdefault(row["candidate_id"], []).append(row)
    ref, table = reference(runs), []
    for cid, rows in sorted(grouped.items()):
        valued = [row["value"] for row in rows if row["value"] is not None]
        screening, validation = screening_mean(cid, runs), mean(valued) if valued else UNAVAILABLE
        table.append({"candidate_id": cid, "is_reference": cid == ref, "screening_mean": screening,
                      "validation_mean": validation,
                      "shrinkage": UNAVAILABLE if UNAVAILABLE in (screening, validation) else screening - validation,
                      "mean_cost": mean(row["wall_clock_sec"] for row in rows),
                      "provider_calls": mean(row["calls"] for row in rows)})
    return table


def validation_readout(pool: Mapping, runs: Sequence[Sequence[tuple[int, list]]], criterion: Mapping) -> dict:
    """The validation table, records.final_choice over its valued rows under the criterion, and anchor checks."""
    if pool["task"] != Path(criterion["validation_task"]).name:
        raise ValueError(f"the validation pool is of {pool['task']}, not {criterion['validation_task']}")
    table = validation_rows(pool, runs)
    valued = [row | {"validation_success": row["validation_mean"]} for row in table
              if row["validation_mean"] != UNAVAILABLE]
    rules = criterion["final_choice"] | {"criterion_sha256": pool["criterion_sha256"]}
    return {"validation": table, "final_choice": final_choice(valued, criterion=rules),
            **anchor_checks(pool["anchors"], criterion["anchors"][pool["task"]], criterion["anchor_spread_limit"])}


def phase2_readout(logs: Sequence[Path], archives: Sequence[Path], validation_pool: Mapping | None,
                   criterion: Mapping) -> dict:
    """`logs` and `archives` pair up per run (each run's log.jsonl and archive directory); `validation_pool` is
    read_pool's result for the validation task's pool, or None before validation; `criterion` is
    criteria/phase2.json. Figures are per run and interface; nothing is pooled across interfaces."""
    runs = [archive_files(directory) for directory in archives]
    result = {"min_gain": criterion["improvement"]["min_gain"], "collapse_threshold": criterion["collapse_threshold"],
              "runs": [run_readout(Path(log), files, criterion) for log, files in zip(logs, runs, strict=True)]}
    if validation_pool is None:
        return result | dict.fromkeys(("validation", "final_choice", "anchors_ok", "anchor_spread", "spread_ok"),
                                      UNAVAILABLE)
    return result | validation_readout(validation_pool, runs, criterion)


def readout_command(a: argparse.Namespace) -> dict:
    criterion = json.loads(a.criterion.read_text())
    if a.phase == 2:
        if len(a.results) > 1 or bool(a.results) != bool(a.validation_log):
            raise SystemExit("--phase 2 takes at most one results.json, the validation pool's, with --validation-log")
        pool = read_pool(a.results[0], a.validation_log, a.criterion) if a.results else None
        return phase2_readout(a.log, a.archive, pool, criterion)
    if len(a.log) != 1 or a.driver_readout is None or not a.results:
        raise SystemExit("--phase 1 takes one --log, --driver-readout and each task pool's results.json")
    pools = [read_pool(results, a.log[0], a.criterion) for results in a.results]
    return phase1_readout(pools, json.loads(a.driver_readout.read_text()), criterion)


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
