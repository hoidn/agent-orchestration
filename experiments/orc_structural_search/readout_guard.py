"""Public quality-readout admission and explicit measure-free execution projections."""
import json
from collections.abc import Mapping
from pathlib import Path

from experiments.orc_structural_search import pricing, qualification
from experiments.orc_structural_search.records import UNAVAILABLE, read_records

EXECUTION_KEYS = ('evaluation_id', 'candidate_id', 'task_id', 'replicate', 'outcome', 'mode', 'arm',
                  'provider_calls', 'wall_clock_sec', 'allocation_changed', 'planned_perform_sites',
                  'realized_perform_sites', 'unexercised_sites', 'branch_coverage_reason')
COMPILE_KEYS = ('criterion_sha256', 'episodes', 'completed', 'judged', 'accepted', 'acceptance_rate',
                'refused', 'locality', 'files_touched', 'distinct_skeletons', 'revisit_rate',
                'terminal_only_share', 'allocation_distinct', 'exact_repeats', 'subset', 'frozen_surface')


def mode(criterion, measure_free=False):
    frozen = json.loads(Path(criterion).read_text())
    if measure_free or frozen.get('purpose') == 'measure-free':
        return qualification.validate(criterion, operation='readout', measure_free=measure_free)
    return None


def pool_path(results):
    path = Path(results).resolve().parent
    return path.parent if path.name == 'records' else path


def quality(results, criterion):
    """Prove the actual judge runtime/bindings, never infer them from the current checkout."""
    try:
        pool = pool_path(results)
        context = qualification.pool_context(pool)
        mapping = json.loads((pool / 'records/mapping.json').read_text())
        proof = qualification.validate(criterion, **context, operation='readout')
        if mapping['criterion_sha256'] != proof['criterion_sha256']:
            raise ValueError('pool mapping criterion differs from requested criterion')
        return proof
    except (OSError, KeyError, TypeError) as error:
        raise ValueError(f'qualification: missing or malformed scoring pool provenance: {error}') from error


def require_pools(results, criterion):
    if not results:
        raise ValueError('quality readout requires actual scoring pool provenance; use explicit measure_free')
    return [quality(result, criterion) for result in results]


def compile_projection(value):
    if not isinstance(value, Mapping):
        return {}
    result = {key: value[key] for key in COMPILE_KEYS if key in value}
    if isinstance(value.get('arms'), Mapping):
        result['arms'] = {arm: compile_projection(figures) for arm, figures in value['arms'].items()}
    return result


def execution(logs, criterion, *, driver=None, measure_free=False):
    """Read only raw execution/compile/call/cost evidence; no quality fields are carried through."""
    proof = qualification.validate(criterion, operation='readout', measure_free=measure_free)
    frozen = json.loads(Path(criterion).read_text())
    rows = [row for log in logs for row in read_records(log) if row['kind'] == 'evaluation']
    check_execution_criteria(rows, proof['criterion_sha256'])
    executions = []
    for row in rows:
        projected = {key: row.get(key, UNAVAILABLE) for key in EXECUTION_KEYS}
        if 'price_table' in frozen:
            projected['metered_cost'] = pricing.cost(row, frozen['price_table'])
        executions.append(projected)
    result = {'mode': 'measure-free', 'criterion_sha256': proof['criterion_sha256'], 'executions': executions}
    if driver is not None:
        result['compile_only'] = compile_projection(json.loads(Path(driver).read_text()))
    return result


def check_execution_criteria(rows, sha):
    if any(row.get('criterion_sha256') not in (None, sha) for row in rows):
        raise ValueError('execution criterion_sha256 differs from requested criterion')
