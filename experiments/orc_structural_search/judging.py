"""Mode 2 judging: one blind pool per (generation, task), the judges' ledger entries, waiting for scan verdicts and
the judge retry.

Design: docs/design/orc_structural_search_driver.md ("Search Modes" mode 2); adaptive.py runs the loop around it.

judge_generation: one pool per (generation, task) at P/gen-<n>/<task> (validation: P/validation/<task>), P the pools
root, outside the evidence root E and the work root W (judges must not see the archive or the log, mutators and
evaluated agents must not find the pools at a known place); through scoring.pool_evaluations, batches of at most
eight evaluations plus both anchors; one ledger entry per judge (`kind: "judge"`, one planned call per batch)
reserved before any judge runs and settled (again) after it, a resume included; each judge's scoring, verify_pool
and scan_judge (pool.scan_judge takes no extra root, so E is not among the judge scan's patterns; keeping P outside
E is the guard), then summarize; one {"kind": "judging", "generation", "task", "pool", "results"} log row per pool.

Scan verdicts: before a task's evaluations are pooled, and before summarize, a run or judge scan with hits and no
verdict (the harness would refuse it; a Fable hit needs none) is waited for: the exact `prepare.py scan ...
--verdict` command and the hit summary are printed once, and the scan is reread every POLL_SEC seconds until the
operator records a verdict. A contaminated run stays out of the pool (pool.exclusion); a task whose completed
evaluations are all excluded has no pool, only unvalued rows (scoring.log_only_pool's rule).

Judge failure: a judge's scoring command that exits nonzero is retried once through its resume script
(records/resume-<judge>.sh with the judge's one scoring run id); a second failure raises JudgeIncident, which
adaptive.py records as a judge incident of the generation.
"""

import json
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from experiments.compare import pool as pooling, summarize
from experiments.orc_structural_search import ledger, qualification
from experiments.orc_structural_search.records import append_record, read_records
from experiments.orc_structural_search.scoring import (
    join_scores, latest_evaluations, outcome_rows, pool_evaluations, unvalued_row)

VALIDATION = "validation"
POLL_SEC = 60  # how often a wait for a scan verdict rereads the scan
PREPARE = f"{sys.executable} {Path(pooling.__file__).with_name('prepare.py')}"
HIT_SUMMARY = 5  # hits named in the printed summary


class JudgeIncident(RuntimeError):
    pass


def run_judge(pool: Path, judge: str, script: str = "score") -> None:
    """The judge's scoring command (`script` "score") or its resume script ("resume", given the judge's one
    scoring run id) behind the shims, as prepare.py pool wrote them."""
    args = []
    if script == "resume":
        mapping = json.loads((pool / "records" / "mapping.json").read_text())
        state = pool / "judges" / mapping["judges"][judge]["dir"] / "state"
        args = [path.parent.name for path in sorted(state.glob("*/run.json"))][-1:]
        if not args:
            raise subprocess.CalledProcessError(1, f"resume-{judge}.sh: no scoring run under {state} to resume")
    subprocess.run(["bash", str(pool / "records" / f"{script}-{judge}.sh"), *args], check=True)


def attempt_judge(scorer: Callable[[Path, str, str], None], pool: Path, name: str, *, criterion: Path) -> None:
    """Score; on a nonzero exit resume once; a second failure is a JudgeIncident."""
    def launch(script):
        qualification.validate(criterion, **qualification.pool_context(pool), operation='quality')
        scorer(pool, name, script)
    try:
        launch('score')
    except subprocess.CalledProcessError:
        try:
            launch('resume')
        except subprocess.CalledProcessError as error:
            raise JudgeIncident(f"judge {name} of {pool} failed, and so did its resume: {error}") from error


def score_pool(evidence_root: Path, pool: Path, key: str, *, names: Sequence[str], solution: str, call_cap: int,
               scorer: Callable[[Path, str, str], None], criterion: Path | None = None) -> dict:
    """Reserve every judge's ledger entry (one planned call per batch), then per judge: score (attempt_judge),
    verify the clones, scan the judge; every entry is settled at the end, whatever happened."""
    if criterion is None:
        qualification.validate(None)
    context = qualification.pool_context(pool)
    checked = qualification.validate(criterion, **context, operation='quality')
    mapping = json.loads((pool / 'records/mapping.json').read_text())
    if mapping['criterion_sha256'] != checked['criterion_sha256'] or len(names) != len(set(names)) or set(names) != set(mapping['judges']):
        raise ValueError('qualification: actual pool criterion/judge dispatch mismatch')
    batches = len(mapping['batches'])
    slots = {name: ledger.reserve(evidence_root, kind="judge", key=f"{key} {name}", planned=batches, cap=call_cap)
             for name in names}
    try:
        for name in names:
            attempt_judge(scorer, pool, name, criterion=criterion)
            pooling.verify_pool(pool)
            pooling.scan_judge(pool, name, solution)
    finally:
        for name, slot in slots.items():
            ledger.settle(evidence_root, slot, pool / "records" / "judges" / name)
    return checked


def unadjudicated(scan: Mapping) -> bool:
    return bool(scan["hits"]) and scan["verdict"] is None and not pooling.contamination.model_policy(scan["hits"])


def excluded(scan: Mapping) -> bool:
    """pool.exclusion's rule on an adjudicated scan: Fable answers or a contaminated verdict."""
    return bool(pooling.contamination.model_policy(scan["hits"])) or (
        (scan["verdict"] or {}).get("verdict") == "contaminated")


def await_verdict(path: Path, scan_of: Callable[[dict], dict], command: str) -> dict:
    """The scan (`scan_of` the JSON file at `path`) once it has no unadjudicated hit; until then print `command`
    and the hit summary once (and once that the file is not JSON, if it is not) and reread the file every POLL_SEC
    seconds."""
    shown = garbled = False
    while True:
        try:
            scan = scan_of(json.loads(path.read_text()))
        except json.JSONDecodeError as error:  # being written (repos.dump is not atomic), or broken: say so, reread
            if not garbled:
                print(f"{path} is not JSON ({error}); rereading it every {POLL_SEC} s", flush=True)
                garbled = True
            scan = None
        if scan is not None and not unadjudicated(scan):
            return scan
        if scan is not None and not shown:
            hits = "; ".join(f"{h['file']}:{h['line']}: {h['pattern']}" for h in scan["hits"][:HIT_SUMMARY])
            print(f"waiting for a scan verdict on {path}: {len(scan['hits'])} hits ({hits})\n  {command} "
                  "--verdict contaminated|cleared --reason TEXT", flush=True)
            shown = True
        time.sleep(POLL_SEC)


def run_scan(row: Mapping) -> dict:
    records = Path(row["records_dir"])
    return await_verdict(records / "record.json", lambda record: record["scan"], f"{PREPARE} scan --run {records}")


def judge_scan(pool: Path, name: str) -> dict:
    return await_verdict(pool / "records" / "judges" / name / "scan.json", lambda scan: scan,
                         f"{PREPARE} scan --pool {pool} --judge {name}")


def judge_generation(evidence_root: Path, generation: int, tasks: Sequence[Path], *, criterion: Path,
                     judges: Sequence[str], solutions: Mapping[str, str], call_cap: int, pool_root: Path,
                     scorer: Callable[[Path, str, str], None] | None = None,
                     include: Callable[[Mapping], bool] | None = None) -> list[dict]:
    """Judge each task's completed evaluations of `generation` (or those `include` keeps) in one blind pool (see
    the module docstring); the joined rows of every pool followed by the kept failed and incident evaluations of
    each task from the log (scoring.outcome_rows; once per evaluation id). A task without a completed,
    uncontaminated evaluation has no pool, only those rows and an unvalued row per contaminated one."""
    log, scorer = evidence_root / "log.jsonl", scorer or run_judge
    include = include or (lambda row: row.get("generation") == generation)
    names = [spec.partition("=")[0] for spec in judges]
    joined = []
    for task in tasks:
        failures, completed = task_evaluations(log, task, include)
        if all([excluded(run_scan(r)) for r in completed]):  # a list: wait for every verdict
            joined += [unvalued_row(r) for r in completed] + failures
            continue
        label = f"gen-{generation}" if generation >= 0 else VALIDATION
        pool = pool_evaluations(evidence_root, task, out=pool_root / label / task.name, judges=judges,
                                criterion=criterion, include=include)
        checked = score_pool(evidence_root, pool, f"gen {generation} {task.name}", names=names, solution=solutions[task.name],
                   call_cap=call_cap, scorer=scorer, criterion=criterion)
        for name in names:
            judge_scan(pool, name)
        summarize.summarize(pool, criterion)
        results = pool / "records" / "results.json"
        joined += join_scores(results, log) + failures
        append_record(log, {"kind": "judging", "generation": generation, "task": task.name, "pool": str(pool),
                            "results": str(results), "qualification": checked})
    return joined


def task_evaluations(log, task, include):
    kept = [r for r in latest_evaluations(read_records(log)) if include(r)]
    failures = outcome_rows(kept, task.name)
    completed = [r for r in kept if r["task_id"] == task.name and r["outcome"] == "completed"]
    return failures, completed
