"""Mode 2 of the structural search driver: feedback-guided adaptive search over an archive, with I1 and I2 episodes
interleaved, per-generation blind judging and a validation split.

Design: docs/design/orc_structural_search_driver.md ("Search Modes" mode 2, "Objective And Selection"); plan
docs/plans/2026-10-18-orc-structural-search-phase2-plan.md (Decisions 1, 4-8, Task 3). The readout of a run is
scoring_phase2.phase2_readout; this module writes what it reads.

An archive entry: {candidate_id, candidate_root, seed (stem, or None for a child), module (the lineage seed's stem:
its configuration, driver.seed_config), values {task: [primary value: a completed run's judged value, 0 for a
failed or timed-out run; other incidents and unvalued runs left out]}, calls [provider calls per counted evaluation], mean_value (mean
over the adaptive tasks of the per-task means), mean_calls, evidence ("phase1-prior" or "adaptive"), generation
(the one it entered in; 0 for seeds)}. The archive is the incumbent plus at most ARCHIVE_SIZE frontier members: non-dominated on (mean_value higher, mean_calls lower), ranked by mean_value, then
fewer calls, then the earlier id (the incumbent is the first). Phase 1's joined catalog rows are prior evidence.

A run (run_mode2) on a fresh evidence root E:
  generation 0   archive the seeds; build the initial archive from the Phase 1 rows; log one
                 {"kind": "reference", "candidate_id", "run"} row naming the initial incumbent; evaluate the
                 incumbent once per adaptive task, judge it and replace its prior values with the fresh ones;
                 write E/archive/gen-0.json, the whole initial archive (every valued seed, `direct` included).
  generation n   episodes_per_generation episodes, interfaces alternating I1, I2 (Decision 4), episode indexes
                 (n-1) * episodes_per_generation + k (unique in the run: they name the work trees); per episode a
                 parent drawn uniformly from the archive (random.Random(run_seed)), for I2 a site drawn uniformly
                 from the parent's eligible sites (random.Random(f"{run_seed} {index}"), Decision 1), and the
                 parent's own evidence as feedback (Decision 7). Accepted children not evaluated before in the run
                 (a revisit is never re-evaluated: equal ids would share an evaluation id) are evaluated once per
                 adaptive task and judged; each child valued on every adaptive task is offered to the archive
                 (retain); E/archive/gen-<n>.json is the archive after generation n.
  readout        E/readout.json: per interface the mode 1 readout of its episodes (outcomes, refusals,
                 readout.diversity, scan_pending), and the archive trajectory.
Every evaluation row carries `generation` and `split` ("adaptive", or "validation" from validate_finalists). The
validation task is a holdout root of every scan and never an episode's or an adaptive evaluation's task.

Judging (judge_generation): one pool per (generation, task) at P/gen-<n>/<task> (validation: P/validation/<task>),
P the pools root, outside the evidence root E and the work root W (judges must not see the archive or the log,
mutators and evaluated agents must not find the pools at a known place); through scoring.pool_evaluations, batches of at most eight evaluations plus both
anchors; one ledger entry per judge (`kind: "judge"`, one planned call per batch) reserved before any judge runs;
each judge's scoring, verify_pool and scan_judge (pool.scan_judge takes no extra root, so E is not among the judge
scan's patterns; keeping P outside E is the guard), then summarize; one {"kind": "judging", "generation", "task",
"pool", "results"} log row per pool. Before a generation's evaluations the planned calls of its evaluations and
judges must fit under the call cap, or the generation is refused (CallCapExceeded) with no evaluation started:
its episodes stay logged and no archive file is written for it.
"""

import json
import math
import random
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from statistics import mean

from experiments.compare import pool as pooling, summarize
from experiments.orc_structural_search import ledger
from experiments.orc_structural_search.config import ExperimentConfig, load_config
from experiments.orc_structural_search.driver import (
    archive_seed, check_roots, check_solutions, entry_source, evaluate_all, run_episode, seed_config)
from experiments.orc_structural_search.readout import readout
from experiments.orc_structural_search.records import UNAVAILABLE, append_record, read_records
from experiments.orc_structural_search.scoring import (
    ANCHORS_PER_BATCH, BATCH_CLONES, DIRECT, join_scores, latest_evaluations, outcome_rows, pool_evaluations,
    primary_value)
from experiments.orc_structural_search.scoring_phase2 import archive_files
from experiments.orc_structural_search.sites import eligible_sites, select_site, site_manifest

ADAPTIVE, VALIDATION, PRIOR = "adaptive", "validation", "phase1-prior"
ARCHIVE_SIZE = 6
EVALUATION_KEYS = ("work_root", "evidence_root", "runtime", "env", "timeout_sec", "solutions", "call_cap")


def rank(entry: Mapping) -> tuple:
    return -entry["mean_value"], entry["mean_calls"], entry["candidate_id"]


def make_entry(rows: Sequence[Mapping], tasks: Sequence[str], **fields: object) -> dict | None:
    """The entry (`fields` plus values and means) of one candidate's scored rows (any outcome); None unless it has a
    primary value (scoring.primary_value: a completed run's value, 0 for a failed run; incidents and unvalued runs
    left out) on every task of `tasks`."""
    counted = [row for row in rows if primary_value(row) is not None]
    values: dict[str, list] = {}
    for row in counted:
        values.setdefault(row["task"], []).append(primary_value(row))
    if not tasks or set(values) != set(tasks):
        return None
    calls = [row["calls"] for row in counted]
    return {**fields, "values": values, "calls": calls, "mean_value": mean(mean(v) for v in values.values()),
            "mean_calls": mean(calls)}


def initial_archive(phase1_rows: Sequence[Mapping], catalog_roots: Mapping[str, str], *,
                    tasks: Sequence[str]) -> list[dict]:
    """One prior entry per seed of `catalog_roots` (stem -> this run's archived root) from its `catalog` rows of
    Phase 1's joined rows, valued on every adaptive task of `tasks` (names); ranked. Refuses a row of another task
    and an archive without `direct`."""
    stray = sorted({row["task"] for row in phase1_rows} - set(tasks))
    if stray:
        raise ValueError(f"Phase 1 rows of tasks {stray}, which are not the adaptive tasks {sorted(tasks)}")
    entries = []
    for stem, root in sorted(catalog_roots.items()):
        rows = [row for row in phase1_rows if row["mode"] == "catalog" and row["policy"] == stem]
        found = make_entry(rows, tasks, candidate_id=Path(root).name, candidate_root=str(root), seed=stem,
                           module=stem, evidence=PRIOR, generation=0)
        entries += [found] if found else []
    if not any(entry["seed"] == DIRECT for entry in entries):
        raise ValueError(f"no Phase 1 values of the {DIRECT} seed on every task {tasks}: the Phase 2 readout needs "
                         "its archive entry")
    return sorted(entries, key=rank)


def incumbent(entries: Sequence[Mapping]) -> dict:
    return min(entries, key=rank)


def dominates(a: Mapping, b: Mapping) -> bool:
    return (a["mean_value"] >= b["mean_value"] and a["mean_calls"] <= b["mean_calls"]
            and (a["mean_value"], a["mean_calls"]) != (b["mean_value"], b["mean_calls"]))


def frontier(entries: Sequence[Mapping]) -> list[dict]:
    """The non-dominated entries, ranked (the incumbent first)."""
    return sorted((e for e in entries if not any(dominates(other, e) for other in entries)), key=rank)


def prune(entries: Sequence[Mapping], size: int = ARCHIVE_SIZE) -> list[dict]:
    # ponytail: a frontier wider than size + 1 keeps its best-valued members; crowding distance if spread matters
    return frontier(entries)[:size + 1]


def retain(entries: Sequence[Mapping], child: Mapping, *, size: int = ARCHIVE_SIZE) -> list[dict]:
    """The archive after offering `child` (an entry of the same id is replaced): it enters when non-dominated."""
    return prune([e for e in entries if e["candidate_id"] != child["candidate_id"]] + [dict(child)], size)


def select_parent(entries: Sequence[Mapping], rng: random.Random) -> dict:
    return rng.choice(list(entries))


def terminal(value: object) -> str:
    return value.get("variant", UNAVAILABLE) if isinstance(value, dict) else UNAVAILABLE


def feedback(entry: Mapping, evaluations: Sequence[Mapping]) -> dict:
    """Decision 7: the entry's judged mean and n per task, and the outcome, terminal variant, provider calls and
    wall clock of its own adaptive evaluations among `evaluations` (log rows); nothing else."""
    mine = [r for r in evaluations if r["kind"] == "evaluation" and r["candidate_id"] == entry["candidate_id"]
            and r.get("split") == ADAPTIVE]
    return {"mean_value": {task: {"mean": mean(v), "n": len(v)} for task, v in sorted(entry["values"].items())},
            "runs": [{"task": r["task_id"], "outcome": r["outcome"], "terminal": terminal(r["value"]),
                      "provider_calls": r["provider_calls"], "wall_clock_sec": r["wall_clock_sec"]} for r in mine]}


def run_judge(pool: Path, judge: str) -> None:
    """The judge's scoring command behind the shims, as prepare.py pool wrote it."""
    subprocess.run(["bash", str(pool / "records" / f"score-{judge}.sh")], check=True)


def score_pool(evidence_root: Path, pool: Path, key: str, *, names: Sequence[str], solution: str, call_cap: int,
               scorer: Callable[[Path, str], None]) -> None:
    """Reserve every judge's ledger entry (one planned call per batch), then per judge: score, settle, verify the
    clones, scan the judge."""
    batches = len(json.loads((pool / "records" / "mapping.json").read_text())["batches"])
    slots = {name: ledger.reserve(evidence_root, kind="judge", key=f"{key} {name}", planned=batches, cap=call_cap)
             for name in names}
    for name, slot in slots.items():
        scorer(pool, name)
        ledger.settle(evidence_root, slot, pool / "records" / "judges" / name)
        pooling.verify_pool(pool)
        pooling.scan_judge(pool, name, solution)


def judge_generation(evidence_root: Path, generation: int, tasks: Sequence[Path], *, criterion: Path,
                     judges: Sequence[str], solutions: Mapping[str, str], call_cap: int, pool_root: Path,
                     scorer: Callable[[Path, str], None] | None = None,
                     include: Callable[[Mapping], bool] | None = None) -> list[dict]:
    """Judge each task's completed evaluations of `generation` (or those `include` keeps) in one blind pool (see
    the module docstring); the joined rows of every pool followed by the kept failed and incident evaluations of
    each task from the log (scoring.outcome_rows; once per evaluation id). A task without a completed evaluation
    has no pool, only those rows."""
    log, scorer = evidence_root / "log.jsonl", scorer or run_judge
    include = include or (lambda row: row.get("generation") == generation)
    names = [spec.partition("=")[0] for spec in judges]
    joined = []
    for task in tasks:
        kept = [r for r in latest_evaluations(read_records(log)) if include(r)]
        failures = outcome_rows(kept, task.name)
        if not any(r["task_id"] == task.name and r["outcome"] == "completed" for r in kept):
            joined += failures
            continue
        label = f"gen-{generation}" if generation >= 0 else VALIDATION
        pool = pool_evaluations(evidence_root, task, out=pool_root / label / task.name, judges=judges,
                                criterion=criterion, include=include)
        score_pool(evidence_root, pool, f"gen {generation} {task.name}", names=names, solution=solutions[task.name],
                   call_cap=call_cap, scorer=scorer)
        summarize.summarize(pool, criterion)
        results = pool / "records" / "results.json"
        joined += join_scores(results, log) + failures
        append_record(log, {"kind": "judging", "generation": generation, "task": task.name, "pool": str(pool),
                            "results": str(results)})
    return joined


def lineage_config(entry: Mapping, config: ExperimentConfig) -> ExperimentConfig:
    return seed_config(Path(f"{entry['module']}.orc"), config)


def check_budget(evidence_root: Path, planned: int, cap: int, what: str) -> None:
    path = evidence_root / ledger.LEDGER
    used = ledger.total(json.loads(path.read_text()) if path.exists() else [])
    if used + planned > cap:
        raise ledger.CallCapExceeded(f"{what}: {used} provider calls recorded or reserved in {path} plus at most "
                                     f"{planned} for its evaluations and judges exceed the call cap {cap}")


def evaluate_and_judge(jobs: Sequence[tuple[Path, ExperimentConfig, Mapping]], generation: int, tasks: Sequence[Path],
                       *, replicates: int, launch: Mapping, judge: Mapping,
                       include: Callable[[Mapping], bool] | None = None) -> list[dict]:
    """Refuse unless the jobs' evaluations and their judges fit under the call cap; evaluate each job `replicates`
    times per task (at most launch["concurrency"] at a time) and judge them; the joined rows."""
    if not jobs:
        return []
    batches = math.ceil(len(jobs) * replicates / (BATCH_CLONES - ANCHORS_PER_BATCH))
    calls = sum(ledger.max_provider_calls(entry_source(root, config)) for root, config, _ in jobs)
    planned = len(tasks) * (replicates * calls + batches * len(judge["judges"]))
    check_budget(launch["evidence_root"], planned, launch["call_cap"], f"generation {generation}")
    evaluate_all(jobs, tasks=tasks, replicates=replicates, concurrency=launch["concurrency"],
                 holdouts=launch.get("holdouts", ()), **{key: launch[key] for key in EVALUATION_KEYS})
    return judge_generation(launch["evidence_root"], generation, tasks, solutions=launch["solutions"],
                            call_cap=launch["call_cap"], pool_root=launch["pools_root"], include=include,
                            **judge)


def write_archive(evidence_root: Path, generation: int, entries: Sequence[Mapping]) -> None:
    (evidence_root / "archive").mkdir(exist_ok=True)
    text = json.dumps(list(entries), indent=2, sort_keys=True) + "\n"
    (evidence_root / "archive" / f"gen-{generation}.json").write_text(text)


def episode(parent: Mapping, config: ExperimentConfig, *, interface: str, index: int, generation: int,
            launch: Mapping) -> dict:
    """One adaptive episode against `parent` with its own evidence as feedback; I2 at a seeded uniform site."""
    lineage, root = lineage_config(parent, config), Path(parent["candidate_root"])
    site = None
    if interface == "I2":
        sites = eligible_sites(site_manifest(root, lineage, runtime=launch["runtime"]), lineage)
        site = select_site(sites, random.Random(f"{launch['run_seed']} {index}"))
    rows = read_records(launch["evidence_root"] / "log.jsonl")
    return run_episode(root, lineage, interface=interface, mode=ADAPTIVE, agent_cmd=launch["agent_cmd"],
                       episode_index=index, holdouts=launch["holdouts"], site=site, feedback=feedback(parent, rows),
                       generation=generation, run_seed=launch["run_seed"],
                       **{key: launch[key] for key in EVALUATION_KEYS if key != "timeout_sec"})


def generation(n: int, archive: list[dict], config: ExperimentConfig, *, rng: random.Random,
               adaptive_tasks: Sequence[Path], interfaces: Sequence[str] = ("I1", "I2", "I1", "I2"),
               launch: Mapping, judge: Mapping) -> list[dict]:
    """Generation `n` (see the module docstring); the archive after it, also written to gen-<n>.json."""
    children: dict[str, tuple[Mapping, Mapping]] = {}
    for k, interface in enumerate(interfaces):
        parent = select_parent(archive, rng)
        row = episode(parent, config, interface=interface, index=(n - 1) * len(interfaces) + k, generation=n,
                      launch=launch)
        if row["outcome"] == "accepted":
            children.setdefault(row["candidate_id"], (parent, row))
    log = launch["evidence_root"] / "log.jsonl"
    known = {r["candidate_id"] for r in read_records(log) if r["kind"] == "evaluation"} | {
        e["candidate_id"] for e in archive}
    fresh = {cid: pair for cid, pair in children.items() if cid not in known}
    jobs = [(Path(row["candidate_root"]), lineage_config(parent, config),
             {"mode": ADAPTIVE, "split": ADAPTIVE, "generation": n, "candidate_id": cid,
              "candidate_root": row["candidate_root"], "episode_id": row["episode_id"],
              "parent_candidate_id": row["parent_candidate_id"], "interface": row["interface"]})
            for cid, (parent, row) in fresh.items()]
    rows = evaluate_and_judge(jobs, n, adaptive_tasks, replicates=1, launch=launch, judge=judge)
    for cid, (parent, row) in fresh.items():
        child = make_entry([r for r in rows if r["candidate_id"] == cid], [t.name for t in adaptive_tasks],
                           candidate_id=cid, candidate_root=row["candidate_root"], seed=None, module=parent["module"],
                           evidence=ADAPTIVE, generation=n)
        archive = retain(archive, child) if child else archive
    write_archive(launch["evidence_root"], n, archive)
    return archive


def initial_generation(entries: list[dict], config: ExperimentConfig, adaptive_tasks: Sequence[Path], *,
                       launch: Mapping, judge: Mapping) -> list[dict]:
    """Generation 0: the reference row, the incumbent re-measured on every adaptive task, gen-0.json (every
    entry); the pruned archive the first generation draws from."""
    evidence_root, ref = launch["evidence_root"], incumbent(entries)
    append_record(evidence_root / "log.jsonl",
                  {"kind": "reference", "candidate_id": ref["candidate_id"], "run": evidence_root.name})
    identity = {key: ref[key] for key in ("candidate_id", "candidate_root", "seed")}
    fields = {"mode": ADAPTIVE, "split": ADAPTIVE, "generation": 0, **identity}
    rows = evaluate_and_judge([(Path(ref["candidate_root"]), lineage_config(ref, config), fields)], 0, adaptive_tasks,
                              replicates=1, launch=launch, judge=judge)
    fresh = make_entry(rows, [t.name for t in adaptive_tasks], **identity, module=ref["module"], evidence=ADAPTIVE,
                       generation=0)
    entries = sorted([fresh if fresh and e is ref else e for e in entries], key=rank)
    write_archive(evidence_root, 0, entries)
    return prune(entries)


def mode2_readout(rows: Sequence[Mapping], archive_dir: Path) -> dict:
    """Per interface, the mode 1 readout of its episodes; the archive trajectory (incumbent per generation)."""
    episodes = [row for row in rows if row["kind"] == "episode"]
    interfaces = {name: readout([row for row in episodes if row["interface"] == name])
                  for name in sorted({row["interface"] for row in episodes})}
    trajectory = [{"generation": n, "size": len(entries), "incumbent": incumbent(entries)["candidate_id"],
                   "mean_value": incumbent(entries)["mean_value"], "mean_calls": incumbent(entries)["mean_calls"]}
                  for n, entries in archive_files(archive_dir)]
    return {"interfaces": interfaces, "trajectory": trajectory}


def check_splits(adaptive_tasks: Sequence[Path], validation_task: Path, criterion: Path) -> None:
    """Refuse a validation task among the adaptive tasks, or task packages other than the criterion's (compared by
    package name: the criterion names them relative to the runtime checkout)."""
    names, validation = sorted(Path(t).name for t in adaptive_tasks), Path(validation_task).name
    if validation in names:
        raise ValueError(f"the validation task {validation} is among the adaptive tasks {names}")
    frozen = json.loads(Path(criterion).read_text())
    expected = sorted(Path(t).name for t in frozen["adaptive_tasks"]), Path(frozen["validation_task"]).name
    if (names, validation) != expected:
        raise ValueError(f"adaptive tasks {names} and validation task {validation} are not the criterion's "
                         f"{expected[0]} and {expected[1]} ({criterion})")


def check_pools_root(pools_root: Path, work_root: Path, evidence_root: Path) -> Path:
    """The resolved pools root; refuse one inside the evidence or the work root, or holding the evidence root."""
    pools_root = Path(pools_root).resolve()
    nested = [name for name, root in (("evidence", evidence_root.resolve()), ("work", work_root.resolve()))
              if pools_root.is_relative_to(root)]
    if nested or evidence_root.resolve().is_relative_to(pools_root):
        raise ValueError(f"the pools root {pools_root} must lie outside the evidence root {evidence_root} and the "
                         f"work root {work_root}, and must not hold the evidence root")
    return pools_root


def run_mode2(config_path: Path, *, phase1_joined: Path, seeds: Sequence[Path], adaptive_tasks: Sequence[Path],
              validation_task: Path, generations: int, episodes_per_generation: int, run_seed: int, work_root: Path,
              evidence_root: Path, agent_cmd: Sequence[str], runtime: Path, env: Mapping[str, str],
              timeout_sec: float, solutions: Mapping[str, str], call_cap: int, concurrency: int, criterion: Path,
              judges: Sequence[str], pools_root: Path,
              scorer: Callable[[Path, str], None] | None = None) -> dict:
    """One mode 2 run on a fresh evidence root (see the module docstring); the readout, also <evidence>/readout.json.
    `phase1_joined` is Phase 1's joined.json (each task pool's scoring.read_pool rows: join_scores rows plus the
    failed and incident evaluations); judges are MODEL[=PROVIDERS_JSON]; the
    tasks must be the criterion's; judge pools go under `pools_root` (check_pools_root)."""
    config = load_config(config_path)
    check_splits(adaptive_tasks, validation_task, criterion)
    pools_root = check_pools_root(pools_root, work_root, evidence_root)
    work_root, evidence_root = check_roots(work_root, evidence_root)
    if (evidence_root / "log.jsonl").exists():
        raise FileExistsError(f"{evidence_root / 'log.jsonl'} exists: give every mode 2 run a fresh evidence root")
    launch = {"work_root": work_root, "evidence_root": evidence_root, "runtime": runtime, "env": env,
              "timeout_sec": timeout_sec, "call_cap": call_cap, "concurrency": concurrency, "agent_cmd": agent_cmd,
              "run_seed": run_seed, "holdouts": (validation_task,), "pools_root": pools_root,
              "solutions": check_solutions([*adaptive_tasks, validation_task], solutions, runtime)}
    judge = {"criterion": criterion, "judges": judges, "scorer": scorer}
    roots = {seed.stem: str(archive_seed(seed, evidence_root, runtime)[1]) for seed in seeds}
    entries = initial_archive(json.loads(Path(phase1_joined).read_text()), roots,
                              tasks=[t.name for t in adaptive_tasks])
    archive = initial_generation(entries, config, adaptive_tasks, launch=launch, judge=judge)
    rng = random.Random(run_seed)
    interfaces = [("I1", "I2")[k % 2] for k in range(episodes_per_generation)]
    for n in range(1, generations + 1):
        archive = generation(n, archive, config, rng=rng, adaptive_tasks=adaptive_tasks, interfaces=interfaces,
                             launch=launch, judge=judge)
    result = mode2_readout(read_records(evidence_root / "log.jsonl"), evidence_root / "archive")
    (evidence_root / "readout.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def validate_finalists(evidence_root: Path, archive_path: Path, *, config: ExperimentConfig, reference_seed: str,
                       validation_task: Path, replicates: int = 2, finalists: int = 2, launch: Mapping,
                       judge: Mapping) -> list[dict]:
    """Evaluate the top `finalists` of the archive file by rank, the reference seed's and `direct`'s gen-0 entries
    (each candidate once) `replicates` times on the validation task (`split: "validation"`, no holdout root: the
    task is no longer held out) and judge them in one pool; the joined rows. `launch` as for evaluate_and_judge."""
    initial = json.loads((Path(archive_path).parent / "gen-0.json").read_text())
    named = [e for e in initial if e["seed"] in (reference_seed, DIRECT)]
    if {e["seed"] for e in named} != {reference_seed, DIRECT}:
        raise ValueError(f"gen-0.json beside {archive_path} lacks the {reference_seed} or {DIRECT} seed entry")
    candidates: dict[str, Mapping] = {}
    for entry in sorted(json.loads(Path(archive_path).read_text()), key=rank)[:finalists] + named:
        candidates.setdefault(entry["candidate_id"], entry)
    jobs = [(Path(e["candidate_root"]), lineage_config(e, config),
             {"mode": ADAPTIVE, "split": VALIDATION, "generation": -1, "seed": e["seed"], "candidate_id": cid,
              "candidate_root": e["candidate_root"]}) for cid, e in candidates.items()]
    return evaluate_and_judge(jobs, -1, [validation_task], replicates=replicates,
                              launch={**launch, "evidence_root": Path(evidence_root), "holdouts": ()}, judge=judge,
                              include=lambda row: row.get("split") == VALIDATION)
