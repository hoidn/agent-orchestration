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
import math
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from experiments.compare import pool as pooling, summarize
from experiments.orc_structural_search import ledger, qualification, metering
from experiments.orc_structural_search.records import append_record, read_records
from experiments.orc_structural_search.scoring import (
    join_scores, latest_evaluations, outcome_rows, pool_evaluations, unvalued_row)

VALIDATION = "validation"
POLL_SEC = 60  # how often a wait for a scan verdict rereads the scan
PREPARE = f"{sys.executable} {Path(pooling.__file__).with_name('prepare.py')}"
HIT_SUMMARY = 5  # hits named in the printed summary


class JudgeIncident(RuntimeError):
    pass


def run_judge(pool: Path, judge: str, script: str = "score", *, env=None) -> None:
    """The judge's scoring command (`script` "score") or its resume script ("resume", given the judge's one
    scoring run id) behind the shims, as prepare.py pool wrote them."""
    args = []
    if script == "resume":
        mapping = json.loads((pool / "records" / "mapping.json").read_text())
        state = pool / "judges" / mapping["judges"][judge]["dir"] / "state"
        args = [path.parent.name for path in sorted(state.glob("*/run.json"))][-1:]
        if not args:
            raise subprocess.CalledProcessError(1, f"resume-{judge}.sh: no scoring run under {state} to resume")
    subprocess.run(["bash", str(pool / "records" / f"{script}-{judge}.sh"), *args], check=True, env=env)


def attempt_judge(scorer: Callable[[Path, str, str], None], pool: Path, name: str, *, criterion: Path,
                  script="score") -> None:
    """Score; on a nonzero exit resume once; a second failure is a JudgeIncident."""
    def launch(script):
        checked = qualification.validate(criterion, **qualification.pool_context(pool), operation='quality')
        mapping = json.loads((pool / 'records/mapping.json').read_text())
        if mapping['criterion_sha256'] != checked['criterion_sha256']:
            raise ValueError('qualification: actual pool criterion changed before dispatch')
        scorer(pool, name, script)
    try:
        launch(script)
    except subprocess.CalledProcessError:
        try:
            launch('resume')
        except subprocess.CalledProcessError as error:
            raise JudgeIncident(f"judge {name} of {pool} failed, and so did its resume: {error}") from error


def score_pool(evidence_root: Path, pool: Path, key: str, *, names: Sequence[str], solution: str, call_cap: int,
               scorer: Callable[[Path, str, str], None], criterion: Path | None = None,
               resume=False, settled=None) -> dict:
    """Reserve every judge's ledger entry (one planned call per batch), then per judge: score (attempt_judge),
    verify the clones, scan the judge; every entry is settled at the end, whatever happened."""
    if criterion is None:
        qualification.validate(None)
    context = qualification.pool_context(pool)
    checked = qualification.validate(criterion, **context, operation='quality')
    mapping = json.loads((pool / 'records/mapping.json').read_text())
    if mapping['criterion_sha256'] != checked['criterion_sha256'] or len(names) != len(set(names)) or set(names) != set(mapping['judges']):
        raise ValueError('qualification: actual pool criterion/judge dispatch mismatch')
    slots = {name: judge_slot(evidence_root, f"{key} {name}", len(mapping['batches']), call_cap, resume) for name in names}
    def dispatch(pool, name, script):
        if resume:
            check_judge_dispatch(evidence_root, slots[name], pool, name, mapping, call_cap)
        scorer(pool, name, script)
    finished = set()
    try:
        for name in names:
            started = time.time()
            try:
                judge_once(pool, name, mapping, criterion, dispatch, solution, resume)
            finally:
                finished.add(name)
                settle_judge(evidence_root, slots[name], pool, name, mapping, criterion, solution, started, resume, settled)
    finally:
        for name in set(names) - finished:
            settle_judge(evidence_root, slots[name], pool, name, mapping, criterion, solution, time.time(), False, None)
    return checked


def judge_once(pool, name, mapping, criterion, scorer, solution, resume):
    if not resume or not judge_complete(pool, name, mapping):
        state = pool / 'judges' / mapping['judges'][name]['dir'] / 'state'
        script = 'resume' if resume and list(state.glob('*/run.json')) else 'score'
        attempt_judge(scorer, pool, name, criterion=criterion, script=script)
    pooling.verify_pool(pool)
    pooling.scan_judge(pool, name, solution)


def settle_judge(evidence, slot, pool, name, mapping, criterion, solution, started, resume, settled):
    records = pool / 'records' / 'judges' / name
    calls = ledger.settle(evidence, slot, records)
    save_judge_receipts(records, pool, name, mapping, calls, started)
    if resume:
        from experiments.orc_structural_search.call_identity import require_campaign_scan
        if not (records / 'scan.json').exists():
            pooling.scan_judge(pool, name, solution)
        require_campaign_scan(json.loads((records / 'record.json').read_text()),
                              json.loads(criterion.read_text())['model_policy']['allowed'])
    if settled:
        settled()


def judge_slot(evidence_root, key, batches, call_cap, resume):
    entries = ledger._read(evidence_root / ledger.LEDGER)
    prior = [i for i, row in enumerate(entries) if (row['kind'], row['key']) == ('judge', key)]
    return prior[-1] if resume and prior else ledger.reserve(
        evidence_root, kind='judge', key=key, planned=batches, cap=call_cap)


def judge_complete(pool, name, mapping):
    try:
        summarize.scoring_run(pool, name, mapping['judges'][name], mapping['criterion_sha256'])
        return True
    except (SystemExit, OSError, ValueError, KeyError):
        return False


def save_judge_receipts(records, pool, name, mapping, calls, started):
    path = records / 'record.json'
    previous = json.loads(path.read_text()) if path.exists() else {}
    tree = pool / 'judges' / mapping['judges'][name]['dir']
    row = {'kind': 'judge', 'pool': str(pool), 'judge': name, 'records_dir': str(records),
           'tree': str(tree), 'created_at': mapping['created_at'],
           'provider_calls': calls, 'wall_clock_sec': previous.get('wall_clock_sec', 0) + time.time() - started,
           **metering.receipts(records, tree=tree, since=mapping['created_at'], home=Path.home())}
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(row) + '\n')
    os.replace(temporary, path)


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
                     include: Callable[[Mapping], bool] | None = None, resume=False,
                     settled=None, env=None) -> list[dict]:
    """Judge each task's completed evaluations of `generation` (or those `include` keeps) in one blind pool (see
    the module docstring); the joined rows of every pool followed by the kept failed and incident evaluations of
    each task from the log (scoring.outcome_rows; once per evaluation id). A task without a completed,
    uncontaminated evaluation has no pool, only those rows and an unvalued row per contaminated one."""
    log = evidence_root / 'log.jsonl'
    scorer = scorer or (lambda pool, name, script: run_judge(pool, name, script, env=env))
    include = include or (lambda row: row.get("generation") == generation)
    joined = []
    for task in tasks:
        prior = logged_judging(log, generation, task)
        if resume and prior:
            joined += join_scores(Path(prior[-1]['results']), log)
            continue
        failures, completed = task_evaluations(log, task, include)
        if all([excluded(run_scan(r)) for r in completed]):  # a list: wait for every verdict
            joined += [unvalued_row(r) for r in completed] + failures
            continue
        row = judge_task(log, generation, task, criterion=criterion, judges=judges, solutions=solutions,
            call_cap=call_cap, pool_root=pool_root, scorer=scorer, include=include, resume=resume, settled=settled)
        joined += join_scores(Path(row['results']), log) + failures
        append_record(log, row)
        if settled:
            settled()
    return joined


def logged_judging(log, generation, task):
    return [row for row in optional_records(log) if row['kind'] == 'judging'
            and (row.get('generation'), row['task']) == (generation, task.name)]


def judge_task(log, generation, task, *, criterion, judges, solutions, call_cap, pool_root, scorer, include, resume, settled):
    label = f"gen-{generation}" if generation >= 0 else VALIDATION
    pool = pool_root / label / task.name
    if not (resume and (pool / 'records/mapping.json').exists()):
        pool = pool_evaluations(log.parent, task, out=pool, judges=judges, criterion=criterion, include=include)
        if resume:
            append_record(log, {'kind': 'judge_pool', 'generation': generation, 'task': task.name, 'pool': str(pool)})
    names = [spec.partition('=')[0] for spec in judges]
    checked = score_pool(log.parent, pool, f'gen {generation} {task.name}', names=names, solution=solutions[task.name],
        call_cap=call_cap, scorer=scorer, criterion=criterion, resume=resume, settled=settled)
    for name in names:
        judge_scan(pool, name)
    summarize.summarize(pool, criterion)
    return {'kind': 'judging', 'generation': generation, 'task': task.name, 'pool': str(pool),
            'results': str(pool / 'records/results.json'), 'qualification': checked}


def task_evaluations(log, task, include):
    kept = [r for r in latest_evaluations(read_records(log)) if include(r)]
    failures = outcome_rows(kept, task.name)
    completed = [r for r in kept if r["task_id"] == task.name and r["outcome"] == "completed"]
    return failures, completed


def optional_records(path):
    return read_records(path) if path.exists() else []


def evaluate_and_judge(jobs, generation, tasks, *, replicates, launch, judge, include=None):
    """Historical batch dispatch plus opt-in pending-unit and settled-pool recovery."""
    from experiments.orc_structural_search import driver, mode1, scoring
    from experiments.orc_structural_search.adaptive import EVALUATION_KEYS
    from experiments.compare.pool import rubric
    if not jobs:
        return []
    pending = mode1.continued(jobs, tasks, replicates, optional_records(launch['evidence_root'] / 'log.jsonl'))
    calls = [ledger.planned_calls(u.root, u.config, runtime=launch['runtime']) for u in pending]
    capacities = [scoring.fillers_per_batch(task, rubric(judge['criterion'])) for task in tasks]
    planned = sum(calls) + planned_judging(jobs, generation, tasks, replicates, launch, judge, capacities)
    ledger.check_budget(launch['evidence_root'], planned, launch['call_cap'], f'generation {generation} evaluations')
    driver.launch_units(pending, concurrency=launch['concurrency'], holdouts=launch.get('holdouts', ()),
        gate=launch.get('gate'), guard=launch.get('guard'), criterion=judge['criterion'], scan_roots=launch.get('scan_roots', ()),
        **{key: launch[key] for key in EVALUATION_KEYS})
    if launch.get('cap_gate') and launch['cap_gate'].exhausted:
        from experiments.orc_structural_search.three_arm_gate import QuotaExhausted
        raise QuotaExhausted(launch['cap_gate'].exhausted)
    return judge_generation(launch['evidence_root'], generation, tasks, solutions=launch['solutions'],
        call_cap=launch['call_cap'], pool_root=launch['pools_root'], include=include,
        resume=launch.get('resume', False), settled=launch.get('settled'), env=launch.get('judge_env'), **judge)


def planned_judging(jobs, generation, tasks, replicates, launch, judge, capacities):
    """Count only pending batches beyond existing reservations; completed scoring is reused."""
    reserved = {row['key']: row['planned'] for row in ledger._read(launch['evidence_root'] / ledger.LEDGER)
                if (row['kind'], row['calls']) == ('judge', None)}
    names, planned = [spec.partition('=')[0] for spec in judge['judges']], 0
    label = f'gen-{generation}' if generation >= 0 else VALIDATION
    for task, capacity in zip(tasks, capacities):
        if launch.get('resume') and logged_judging(launch['evidence_root'] / 'log.jsonl', generation, task):
            continue
        pool = launch['pools_root'] / label / task.name
        if launch.get('resume') and (pool / 'records/mapping.json').exists():
            mapping = json.loads((pool / 'records/mapping.json').read_text())
            planned += sum(max(0, remaining_judge_batches(pool, name, mapping) -
                reserved.get(f'gen {generation} {task.name} {name}', 0)) for name in names)
        else:
            planned += math.ceil(len(jobs) * replicates / capacity) * len(names)
    return planned


def remaining_judge_batches(pool, name, mapping):
    """A partial memo earns credit only for bound, physically paired committed provider effects."""
    if judge_complete(pool, name, mapping):
        return 0
    state = pool / 'judges' / mapping['judges'][name]['dir'] / 'state'
    headers = list(state.glob('*/run.json'))
    if not headers:
        return len(mapping['batches'])
    expected = json.loads((pool / 'records' / f'score-inputs-{name}.json').read_text())
    if len(headers) != 1 or json.loads(headers[0].read_text())['bound_inputs'] != expected:
        raise ValueError('partial judge inputs differ from frozen pool')
    memo = headers[0].with_name('memo.jsonl')
    rows = summarize.read_memo(memo) if memo.exists() else []
    pairs = summarize.paired_calls(pool / 'records/judges' / name, rows)
    committed = {r['identity'] for r in rows if r['record'] == 'committed' and r['effect_class'] == 'provider'
                 and (r['identity'], r['attempt']) in pairs}
    if len(committed) > len(mapping['batches']):
        raise ValueError('partial judge exceeds the frozen batch count')
    return len(mapping['batches']) - len(committed)


def check_judge_dispatch(evidence, slot, pool, name, mapping, cap):
    """Keep other reservations while checking actual spend plus this judge's remaining batches."""
    calls = pool / 'records/judges' / name / 'calls'
    calls.mkdir(exist_ok=True)
    entries = ledger._read(evidence / ledger.LEDGER)
    entry = entries[slot]
    own = entry['planned'] if entry['calls'] is None else entry['calls']
    used = ledger.total(entries) - own + len(list(calls.glob('*')))
    remaining = remaining_judge_batches(pool, name, mapping)
    if used + remaining > cap:
        raise ledger.CallCapExceeded(f'judge {name}: {used} actual/reserved + {remaining} pending exceeds call cap {cap}')
