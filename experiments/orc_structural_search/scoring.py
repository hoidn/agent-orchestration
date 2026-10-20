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
  read_pool          one task's pool: joined rows plus the task's failed and incident evaluations from the log
                     (collect records no patch for them, so summarize has no run row), summarize's anchors,
                     agreement and excluded judges, and the completed evaluations no run row names (`unpooled`);
                     refuses another criterion's results. Log rows count once per evaluation id
                     (latest_evaluations: per job, quota.job_key, the last row wins, so a resumed
                     incident counts as its later outcome and a quota relaunch supersedes its quota incident).
  log_only_pool      a task with no completed, uncontaminated evaluation has no pool: its rows from the log alone
                     (`no_pool`; contaminated completed runs unvalued; anchors not applicable, so the anchor gate
                     skips it).
  scored_outcome     an incident whose latest incidents entry shows `launcher exit -9` (killed at its wall-clock
                     envelope) is a `timeout`: 0 points, counted under failed and reported as timeouts. A failed
                     or incident evaluation whose launch hit a provider quota (quota.quota_reason, which also reads
                     the records of failed rows from before the quota guard) is a `quota_incident`: excluded,
                     counted as quota_incidents.
  contaminated_children  the children of unguided episodes with a contaminated scan verdict: the Phase 1 readout
                     leaves out every row of them (and lists them as `excluded_children`).
  phase1_readout     per task: catalog policy, child and pooled `unguided` stats; separation over arms with two or
                     more primary values (primary_value: a completed run's value, 0 for a failed run; criterion
                     amendment of 2026-10-18); DIRECT's rank; anchor order and cross-batch spread per judge; the
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
from experiments.orc_structural_search import qualification
from experiments.orc_structural_search.config import check_criterion_hashes
from experiments.orc_structural_search.quota import job_key
from experiments.orc_structural_search.readout import QUOTA_INCIDENT, diversity, outcome, share
from experiments.orc_structural_search.records import UNAVAILABLE, read_records

DIRECT = "direct"  # the DIRECT seed's stem
UNGUIDED = "unguided"  # the one arm pooling every accepted I1 child's evaluations
BATCH_CLONES = 10  # harness D4: at most ten clones per batch, both anchors included and repeated in each
ANCHORS_PER_BATCH = 2
FAILED_POINTS = 0.0  # a failed or timed-out evaluation's primary value (criteria amendment of 2026-10-18)
FAILURES = ("failed", "timeout")  # scored outcomes worth FAILED_POINTS
KILLED = "(launcher exit -9;"  # evaluation._launch's incidents entry for a run killed at its wall-clock envelope
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
    if json.loads(Path(criterion).read_text()).get('purpose') in ('measure-free', 'calibration'):
        qualification.validate(criterion, operation='quality')
    names = sorted(spec.partition("=")[0] for spec in judges)
    if names != sorted(json.loads(Path(criterion).read_text())["judges"]):
        raise ValueError(f"judges {names} are not the criterion's {criterion}")
    completed = [row for row in read_records(Path(evidence_root) / "log.jsonl")
                 if row["kind"] == "evaluation" and row["task_id"] == task.name and row["outcome"] == "completed"
                 and include(row)]
    if not completed:
        raise ValueError(f"no completed evaluation of {task.name} in {evidence_root}/log.jsonl")
    check_criterion_hashes(completed, sha256_file(criterion))
    runtime = Path(load(Path(completed[0]['records_dir']) / 'record.json')['runtime'])
    qualification.validate(criterion, tasks=[task], runtime=runtime, judges=judges, operation='quality')
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
    checked = qualification.validate(criterion, tasks=[task], runtime=Path(ref['runtime']), judges=judges,
                                     operation='quality')
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
    mapping = {"task": str(task), "criterion_sha256": sha256_file(criterion), "qualification": checked, "compare_base": ref["compare_base"],
               "main": ref["main"], "runtime": ref["runtime"], "runtime_commit": commit, "created_at": time.time(),
               "judges": {name: {"dir": secrets.token_hex(8), "providers": str(Path(providers or default).resolve())}
                          for name, _, providers in (spec.partition("=") for spec in judges)},
               "runs": rows, "clones": clones, "batches": members}
    dump(out / "records" / "mapping.json", mapping)
    pooling.write_score_inputs(out, mapping, (task / "intent.txt").read_text(), Path(ref["runtime"]))
    (out / "clones").chmod(pooling.HIDDEN_DIR)
    print(f"# {len(clones)} clones in {len(members)} batches; run the judges one after another, "
          f"each followed by: prepare.py verify-pool --pool {out}")


def latest_evaluations(rows: Sequence[Mapping]) -> list[dict]:
    """The evaluation rows among log `rows`, one per job (quota.job_key: candidate, task, replicate, split,
    generation; a quota relaunch has another evaluation id): the last appended."""
    return list({job_key(row): row for row in rows if row["kind"] == "evaluation"}.values())


def scored_outcome(record: Mapping) -> str:
    """The log outcome, except a quota launch is a `quota_incident` (readout.outcome) and an incident whose latest
    incidents entry shows the launcher killed at the wall-clock envelope (KILLED) is a `timeout`."""
    incidents = record.get("incidents") or ()
    killed = record["outcome"] == "incident" and incidents and KILLED in incidents[-1]
    return "timeout" if killed else outcome(record)


def unvalued_row(record: Mapping) -> dict:
    """A scored row of a log record with no summarize run: value and hidden None, calls and wall clock the log's."""
    return evaluation_row(record, value=None, hidden=None, calls=record.get("provider_calls", UNAVAILABLE),
                          wall_clock_sec=record.get("wall_clock_sec", UNAVAILABLE))


def outcome_rows(records: Sequence[Mapping], task: str) -> list[dict]:
    """An unvalued row per failed or incident (or timeout) evaluation of `task` among the deduplicated log
    `records`."""
    return [unvalued_row(r) for r in records if r["task_id"] == task and r["outcome"] in ("failed", "incident")]


def evaluation_row(record: Mapping, **measures) -> dict:
    """A log evaluation record as a scored row: identity, outcome, then `measures` (value, hidden, calls,
    wall_clock_sec)."""
    return {"evaluation_id": record["evaluation_id"], "candidate_id": record["candidate_id"], "mode": record["mode"],
            "policy": policy(record), "task": record["task_id"], "replicate": record["replicate"],
            "outcome": scored_outcome(record), **measures}


def primary_value(row: Mapping) -> float | None:
    """A completed run's value (None when summarize excluded it), FAILED_POINTS for a failed or timed-out run, None
    for an incident."""
    return {"completed": row["value"], "failed": FAILED_POINTS, "timeout": FAILED_POINTS}.get(row["outcome"])


def join_scores(results_json: Path, log: Path) -> list[dict]:
    """One row per summarize run: {evaluation_id, candidate_id, mode, policy, task, replicate, outcome, value, hidden,
    calls, wall_clock_sec}."""
    evaluations = {str(Path(row["records_dir"]).resolve()): row for row in latest_evaluations(read_records(log))}
    rows = []
    for run in json.loads(Path(results_json).read_text())["runs"]:
        record = evaluations.get(str(Path(run["run"]).resolve()))
        if record is None:
            raise ValueError(f"{results_json}: run {run['run']} maps to no evaluation record in {log}")
        if run["arm"] != record["evaluation_id"]:
            raise ValueError(f"{results_json}: run {run['run']} has arm {run['arm']} but its records directory is "
                             f"evaluation {record['evaluation_id']}'s")
        rows.append(evaluation_row(record, value=run["value"], hidden=run.get("hidden_value"), calls=run["calls"],
                                   wall_clock_sec=run["wall_clock_sec"]))
    return rows


def read_pool(results_json: Path, log: Path, criterion: Path) -> dict:
    """One task's pool for phase1_readout (and each pool of scoring_phase2): joined rows followed by a row (value
    and hidden None; calls and wall clock the log's) per failed or incident evaluation of the task in the log,
    summarize's anchors, agreement and excluded judges, the criterion hash it was checked against, and the
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
    records = latest_evaluations(read_records(log))
    unpooled = sorted(r["evaluation_id"] for r in records
                      if r["task_id"] == task and r["outcome"] == "completed" and r["evaluation_id"] not in pooled)
    return {"task": task, "results": str(results_json), "rows": rows + outcome_rows(records, task),
            "anchors": results["anchors"], "agreement": results["agreement"],
            "excluded_judges": results["excluded_judges"], "unpooled": unpooled, "criterion_sha256": sha,
            "no_pool": False}


def contaminated(records_dir: Path) -> bool:
    """Whether the collected, scanned run is excluded from a pool (pool.exclusion: Fable answers or a contaminated
    verdict); refuses a run not collected or scanned, and hits without a verdict."""
    record = load(Path(records_dir) / "record.json")
    if "outcome" not in record or "scan" not in record:
        raise ValueError(f"{records_dir} has not been collected and scanned")
    return pooling.exclusion(record["scan"], record["calls"], f"prepare.py scan --run {records_dir}") is not None


def log_only_pool(log: Path, task: str, excluded: frozenset[str] = frozenset()) -> dict:
    """read_pool's shape for a task with no completed, uncontaminated evaluation in `log` (so no pool): an unvalued
    row per completed (contaminated: counted as excluded), failed or incident evaluation, no anchors, `no_pool`
    true. Refuses a task with a completed, uncontaminated evaluation that is not an `excluded` child's: that one
    needs its pool."""
    records = [r for r in latest_evaluations(read_records(log)) if r["task_id"] == task]
    completed = [r for r in records if r["outcome"] == "completed"]
    usable = sorted(r["evaluation_id"] for r in completed
                    if not (r["mode"] != "catalog" and r["candidate_id"] in excluded)
                    and not contaminated(r["records_dir"]))
    if usable:
        raise ValueError(f"{task} has completed, uncontaminated evaluations {usable} in {log}: pass its pool's "
                         "results.json")
    return {"task": task, "results": UNAVAILABLE, "rows": [unvalued_row(r) for r in completed] +
            outcome_rows(records, task), "anchors": [], "agreement": {}, "excluded_judges": {}, "unpooled": [],
            "no_pool": True}


def contaminated_children(log: Path) -> set[str]:
    """The candidate ids of the accepted unguided children whose episode scan (<log's directory>/episodes/
    <episode_id>/record.json) has a contaminated verdict: the mutator read sibling episodes or the evidence root, so
    the child is no independent unguided sample and the readout leaves out every unguided row of it and its
    episode's diversity figures. Refuses an accepted episode that was not scanned, or has scan hits and no
    verdict."""
    children = set()
    for row in read_records(log):
        if row["kind"] != "episode" or row["outcome"] != "accepted":
            continue
        scan = load(Path(log).parent / "episodes" / row["episode_id"] / "record.json").get("scan")
        if scan is None:
            raise ValueError(f"episode {row['episode_id']} was not scanned: prepare.py scan --run <its records>")
        if scan["hits"] and scan["verdict"] is None:
            raise ValueError(f"episode {row['episode_id']} has {len(scan['hits'])} scan hits and no verdict")
        if scan["verdict"] and scan["verdict"]["verdict"] == "contaminated":
            children.add(row["candidate_id"])
    return children


def pooled_sd(groups: Sequence[Sequence[float]]) -> float | str:
    """sqrt(sum((n-1) s^2) / sum(n-1)) over groups with two or more values; unavailable without any."""
    multi = [g for g in groups if len(g) > 1]
    df = sum(len(g) - 1 for g in multi)
    return math.sqrt(sum((len(g) - 1) * variance(g) for g in multi) / df) if df else UNAVAILABLE


def known_mean(values: Sequence) -> float | str:
    """The mean of the numeric `values` (a log's UNAVAILABLE calls or wall clock left out); unavailable without."""
    known = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return mean(known) if known else UNAVAILABLE


def primary_values(rows: Sequence[Mapping]) -> list[float]:
    return [v for v in map(primary_value, rows) if v is not None]


def policy_stats(rows: Sequence[Mapping]) -> dict:
    """One arm's rows (any outcome): runs, mean and sd over primary values; valued_runs and valued_mean over
    completed runs' values; failed (failed and timed-out runs), timeouts, failure_rate (failed over completed and
    failed), incidents (quota incidents not included), quota_incidents, excluded (completed without a value);
    hidden, calls and wall clock means over the rows with a primary value."""
    values, counted = primary_values(rows), [r for r in rows if primary_value(r) is not None]
    valued = [r["value"] for r in counted if r["outcome"] == "completed"]
    outcomes = [r["outcome"] for r in rows]
    failed, completed = sum(map(outcomes.count, FAILURES)), outcomes.count("completed")
    return {"runs": len(values), "mean": known_mean(values), "sd": stdev(values) if len(values) > 1 else UNAVAILABLE,
            "valued_runs": len(valued), "valued_mean": known_mean(valued), "failed": failed,
            "timeouts": outcomes.count("timeout"),
            "failure_rate": share(failed, failed + completed), "incidents": outcomes.count("incident"),
            "quota_incidents": outcomes.count(QUOTA_INCIDENT),
            "excluded": completed - len(valued),
            "hidden_mean": known_mean([r["hidden"] for r in counted if r["hidden"] is not None]),
            "calls_mean": known_mean([r["calls"] for r in counted]),
            "wall_clock_mean": known_mean([r["wall_clock_sec"] for r in counted])}


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
    """(catalog policy -> rows, unguided child -> rows), rows of every outcome."""
    catalog: dict[str, list] = {}
    children: dict[str, list] = {}
    for row in rows:
        (catalog if row["mode"] == "catalog" else children).setdefault(row["policy"], []).append(row)
    return catalog, children


def task_readout(pool: Mapping, criterion: Mapping) -> dict:
    """Descriptive stats per catalog policy, per child and for the pooled `unguided` arm; separation over the arms
    with two or more primary values (catalog policies and the pooled unguided arm), counted only when the
    anchors' cross-batch spread is within the limit; anchor checks, agreement, excluded judges, unpooled runs."""
    rules = criterion["separation"]
    catalog, children = arms(pool["rows"])
    unguided = [row for group in children.values() for row in group]
    primary = {p: primary_values(g) for p, g in [*catalog.items(), (UNGUIDED, unguided)]}
    compared = {p: values for p, values in primary.items() if len(values) > 1}
    sd = pooled_sd(list(compared.values()))
    split = separation({p: mean(v) for p, v in compared.items()}, sd, rules)
    checks = ({"anchors_ok": UNAVAILABLE, "anchor_spread": {}, "spread_ok": True} if pool["no_pool"] else
              anchor_checks(pool["anchors"], criterion["anchors"][pool["task"]], rules["anchor_spread_limit"]))
    return {"policies": {p: policy_stats(g) for p, g in sorted(catalog.items())},
            "children": {p: policy_stats(g) for p, g in sorted(children.items())},
            UNGUIDED: policy_stats(unguided) if unguided else UNAVAILABLE, "compared": sorted(compared),
            "pooled_sd": sd, **split, **checks, "separated": split["gap_separated"] and checks["spread_ok"],
            "agreement": pool["agreement"], "excluded_judges": pool["excluded_judges"], "unpooled": pool["unpooled"],
            "no_pool": pool["no_pool"]}


def decision(tasks: Mapping[str, Mapping], collapsed: bool | str, min_tasks: int) -> dict:
    """Roadmap "Decision Points And Stop Rules", first rule that fires: an anchor inversion in any pool
    (anchors_inverted; a no_pool task has no anchors and is skipped); fewer than `min_tasks` separated tasks
    (within_tolerance); DIRECT the sole winner on every separated task (direct_sole_winner); the only Phase 1 interface (I1) without a collapse figure, no accepted
    child, so the adaptive claim is untested (collapse_unavailable), or collapsed (collapsed); otherwise separated
    and Phase 2 is selected."""
    separated = sorted(t for t, r in tasks.items() if r["separated"])
    if not all(r["anchors_ok"] for r in tasks.values() if not r["no_pool"]):
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
    if len(a.log) != 1 or a.driver_readout is None:
        raise SystemExit("--phase 1 takes one --log, --driver-readout and each task pool's results.json")
    return phase1_command(a.log[0], a.driver_readout, a.criterion, a.results, a.joined_out)


def phase1_command(log: Path, driver_readout: Path, criterion: Path, results: Sequence[Path],
                   joined_out: Path | None) -> dict:
    """The Phase 1 readout over each task's pool (a log-only pool for a task without one), without the children
    of contaminated episodes (contaminated_children): their unguided rows leave the pools and, when there are any,
    the driver's diversity figures are recomputed over the remaining accepted children (readout.diversity, the
    driver's own computation); `excluded_children` lists them."""
    excluded = frozenset(contaminated_children(log))
    pools = [read_pool(path, log, criterion) for path in results]
    pooled = {pool["task"] for pool in pools}
    pools += [log_only_pool(log, Path(task).name, excluded) for task in json.loads(criterion.read_text())["tasks"]
              if Path(task).name not in pooled]
    pools = [pool | {"rows": [r for r in pool["rows"] if r["mode"] == "catalog" or r["candidate_id"] not in excluded]}
             for pool in pools]
    accepted = [r for r in read_records(log) if r["kind"] == "episode" and r["outcome"] == "accepted"
                and r["candidate_id"] not in excluded]
    figures = json.loads(driver_readout.read_text()) | (diversity(accepted) if excluded else {})
    result = phase1_readout(pools, figures, json.loads(criterion.read_text())) | {"excluded_children": sorted(excluded)}
    if joined_out:  # the Phase 2 initial archive's input (adaptive.run_mode2 phase1_joined); only after a readout
        joined_out.write_text(json.dumps([row for pool in pools for row in pool["rows"]], indent=2) + "\n")
    return result


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
    readout_cmd.add_argument("--joined-out", type=Path,
                             help="phase 1: write every task's scored rows (outcomes included) here, Phase 2's "
                                  "phase1_joined")
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
