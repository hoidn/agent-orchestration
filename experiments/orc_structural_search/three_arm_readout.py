"""Qualified judged readout over all evaluated children and matched parent baselines."""
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import mean

from experiments.orc_structural_search import pareto_readout, readout_guard
from experiments.orc_structural_search.records import UNAVAILABLE, read_records
from experiments.orc_structural_search.scoring import (
    anchor_checks, contaminated_children, latest_evaluations, log_only_pool, policy_stats, primary_value, read_pool)
from experiments.orc_structural_search.three_arm import (
    HISTORICAL_CRITERION_SHA256, MODE, arm_specs, check_row_criteria, load_criterion)

DECISION = 'descriptive; no separation rule applied (Phase 1 decision stands)'


def site_figures(rows, evidence):
    records = [evidence.get(row['evaluation_id'], {}) for row in rows]
    counts = Counter()
    known = False
    for record in records:
        sites = record.get('realized_perform_sites')
        if isinstance(sites, list):
            known = True
            counts.update({row['identity']: row['attempts'] for row in sites})
    return {'realized_perform_sites': dict(counts) if known else UNAVAILABLE,
            'planned_perform_sites': merged_labels(records, 'planned_perform_sites'),
            'unexercised_perform_sites': merged_labels(records, 'unexercised_perform_sites')}


def merged_labels(records, key):
    known = [record[key] for record in records if isinstance(record.get(key), list)]
    return sorted({row['identity'] for sites in known for row in sites}) if known else UNAVAILABLE


def child_figures(rows: Sequence[Mapping], evidence: Mapping | None = None) -> dict:
    return policy_stats(rows) | {'values': [UNAVAILABLE if v is None else v for v in map(primary_value, rows)],
                                **site_figures(rows, evidence or {})}


def evaluation_evidence(row: Mapping, record: Mapping) -> dict:
    return {'evaluation_id': row['evaluation_id'], 'candidate_id': row['candidate_id'],
            'provider_calls': row.get('calls', UNAVAILABLE),
            **{key: record.get(key, UNAVAILABLE) for key in (
                'realized_perform_sites', 'planned_perform_sites', 'unexercised_perform_sites', 'exercised_branches',
                'branch_coverage_reason', 'allocation_changed')}}


def arm_task_figures(pool, children, parent, evidence):
    mine = [row for row in pool['rows'] if row['candidate_id'] in children]
    baseline = [row for row in pool['rows'] if row['candidate_id'] == parent]
    sites = unexercised_counts(mine, evidence)
    return policy_stats(mine) | {
        'children': {cid: child_figures([row for row in mine if row['candidate_id'] == cid], evidence)
                     for cid in sorted(children)}, 'parent_candidate_id': parent,
        'parent': child_figures(baseline, evidence),
        'sites_unexercised_mean': mean(sites) if sites else UNAVAILABLE,
        'evaluations': [evaluation_evidence(row, evidence.get(row['evaluation_id'], {})) for row in mine]}


def unexercised_counts(rows, evidence):
    return [len(evidence[row['evaluation_id']]['unexercised_perform_sites']) for row in rows
            if primary_value(row) is not None and
            isinstance(evidence.get(row['evaluation_id'], {}).get('unexercised_perform_sites'), list)]


def task_figures(pool, chosen, parents, criterion, evidence):
    checks = UNAVAILABLE if pool['no_pool'] else anchor_checks(
        pool['anchors'], criterion['anchors'][pool['task']], criterion['separation']['anchor_spread_limit'])
    arms = {arm: arm_task_figures(pool, chosen[arm], parents.get(spec['parent']), evidence)
            for arm, spec in arm_specs(criterion).items()}
    return {'anchors': pool['anchors'], 'anchor_checks': checks, 'arms': arms, 'agreement': pool['agreement'],
            'excluded_judges': pool['excluded_judges'], 'unpooled': pool['unpooled'], 'no_pool': pool['no_pool']}


def check_compile(compile_only, frozen):
    got = compile_only.get('criterion_sha256')
    historical = got is None and frozen['criterion_sha256'] == HISTORICAL_CRITERION_SHA256
    if got != frozen['criterion_sha256'] and not historical:
        raise ValueError('driver readout criterion_sha256 differs from the criterion')
    if set(compile_only['arms']) != set(arm_specs(frozen)):
        raise ValueError('driver readout arms differ from the criterion')


def all_children(rows, compile_only):
    chosen = {arm: set(figures['subset']) for arm, figures in compile_only['arms'].items()}
    for row in latest_evaluations(rows):
        if row.get('mode') == MODE and not row.get('parent_for_arms') and not row.get('parent'):
            chosen[row['arm']].add(row['candidate_id'])
    return chosen


def study_pools(results, log, criterion, frozen):
    pools = [read_pool(path, log, criterion) for path in results]
    pooled = [pool['task'] for pool in pools]
    if len(pooled) != len(set(pooled)):
        raise ValueError('duplicate task pools: supply one cumulative harness pool per task')
    for task in frozen['tasks']:
        if Path(task).name not in pooled:
            pools.append(log_only_pool(log, Path(task).name) | {'criterion_sha256': frozen['criterion_sha256']})
    return sorted(pools, key=lambda p: p['task'])


def readout(log: Path, driver_readout: Path, criterion: Path, results: Sequence[Path], *, measure_free=False) -> dict:
    if readout_guard.mode(criterion, measure_free):
        return readout_guard.execution([log], criterion, driver=driver_readout, measure_free=measure_free)
    readout_guard.require_pools(results, criterion)
    frozen, compile_only = load_criterion(criterion), json.loads(Path(driver_readout).read_text())
    rows = read_records(log)
    check_row_criteria(rows, frozen)
    check_compile(compile_only, frozen)
    chosen = all_children(rows, compile_only)
    parents = next((row for row in rows if row['kind'] == 'parents'), {})
    evidence = {row['evaluation_id']: row for row in latest_evaluations(rows)}
    pools = study_pools(results, log, criterion, frozen)
    excluded = contaminated_children(log)
    pools = [pool | {'rows': [row for row in pool['rows'] if row['candidate_id'] not in excluded]} for pool in pools]
    result = {'tasks': {pool['task']: task_figures(pool, chosen, parents, frozen, evidence) for pool in pools},
              'compile_only': compile_only, 'decision': DECISION, 'excluded_children': sorted(excluded)}
    if 'arms' in frozen:
        result['pareto'] = pareto_readout.report(pools, rows, frozen, Path(log).parent, excluded=excluded)
    return result
