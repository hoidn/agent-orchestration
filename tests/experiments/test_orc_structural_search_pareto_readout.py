"""Matched parent/child quality, all-task support, proxy eligibility and endpoint denominators."""
import copy

import pytest

from experiments.orc_structural_search import pareto_readout
from tests.experiments.test_orc_structural_search_pricing import TABLE, receipt


def fixture():
    criterion = {'criterion_sha256': 'a' * 64, 'tasks': ['a', 'b'], 'subset': {'replicates': 2},
        'final_choice': {'equivalence_tolerance': .5}, 'dominance_cost_tolerance': .1,
        'quality_floor': {'kind': 'above_stub'}, 'price_table': TABLE, 'calibration': {'margin': 2, 'error_rate': 0},
        'anchors': {'a': {'stub': 'stub'}, 'b': {'stub': 'stub'}},
        'arms': {'I1': {'parent': 'orc'}, 'module': {'parent': 'orc'}}}
    log = [{'kind': 'parents', 'orc': 'P', 'python': 'PY'}]
    for arm, cid, changed in [('I1', 'C', False), ('module', 'M', True), ('module', 'U', 'unavailable')]:
        log.append({'kind': 'episode', 'episode_id': cid, 'mode': 'three_arm', 'arm': arm, 'outcome': 'accepted',
                    'candidate_id': cid, 'parent_candidate_id': 'P', 'allocation_changed': changed})
    log += [{'kind': 'episode', 'episode_id': 'rejected', 'mode': 'three_arm', 'arm': 'module', 'outcome': 'rejected'}]
    pools = []
    for task in ['a', 'b']:
        rows = []
        for cid, value in [('P', 5), ('C', 6), ('M', 7), ('U', None)]:
            for rep in [1, 2]:
                eid = f'{cid}-{task}-{rep}'
                rows.append({'evaluation_id': eid, 'candidate_id': cid, 'task': task, 'replicate': rep,
                             'outcome': 'completed', 'value': value, 'calls': 1})
                raw = {'kind': 'evaluation', 'mode': 'three_arm', 'evaluation_id': eid, 'candidate_id': cid,
                    'task_id': task, 'replicate': rep, 'outcome': 'completed', 'criterion_sha256': 'a' * 64,
                    'split': 'unavailable', 'allocation_signature': {'run#0': {'provider': 'codex', 'model': 'm',
                                                                            'effort': 'high'}}, **receipt()}
                log.append(raw)
        pools.append({'task': task, 'rows': rows, 'anchors': [{'anchor': 'stub', 'total': 1}],
                      'criterion_sha256': 'a' * 64})
    return criterion, log, pools


def test_full_frontier_and_parent_improvements_split_by_allocation_with_unvalued_denominator(tmp_path):
    criterion, log, pools = fixture()
    result = pareto_readout.report(pools, log, criterion, tmp_path)
    assert result['frontier'] == ['M']
    assert result['cost_axis'] == 'metered_USD'
    assert result['arms']['module']['completed'] == 3
    assert result['arms']['module']['unvalued'] == ['U']
    assert result['arms']['module']['dominating_improvements'] == ['M']
    assert result['arms']['module']['allocation_changed']['improvements_per_completed_episode'] == pytest.approx(1/3)
    assert result['arms']['module']['frontier_entries_per_completed_episode'] == pytest.approx(1/3)


def test_mismatched_replicates_do_not_silently_compare_means(tmp_path):
    criterion, log, pools = fixture()
    pools[0]['rows'] = [r for r in pools[0]['rows'] if not (r['candidate_id'] == 'M' and r['replicate'] == 2)]
    result = pareto_readout.report(pools, log, criterion, tmp_path)
    assert result['candidates']['M']['quality'] == 'unavailable'
    assert result['candidates']['M']['reason'] == 'unmatched_task_replicate_support'
    assert 'M' not in result['frontier']


def test_missing_stub_and_quality_equal_to_stub_are_off_frontier(tmp_path):
    criterion, log, pools = fixture()
    for p in pools:
        p['anchors'][0]['total'] = 7
    assert pareto_readout.report(pools, log, criterion, tmp_path)['frontier'] == []
    pools[0]['anchors'] = []
    result = pareto_readout.report(pools, log, criterion, tmp_path)
    assert result['quality_floor'] == 'unavailable'
    assert result['frontier'] == []


def test_proxy_needs_all_candidates_resolved_to_same_single_pair(tmp_path):
    criterion, log, pools = fixture()
    for row in log:
        if row['kind'] == 'evaluation':
            row['receipt_usage'] = 'unavailable'
    assert pareto_readout.report(pools, log, criterion, tmp_path)['cost_axis'] == 'provider_calls'
    next(row for row in log if row.get('candidate_id') == 'U' and row['kind'] == 'evaluation')['allocation_signature'] = 'unavailable'
    result = pareto_readout.report(pools, log, criterion, tmp_path)
    assert result['cost_axis'] == 'metered_USD'
    assert result['frontier'] == []


def test_mixed_models_require_metering_even_if_declarations_allow_both(tmp_path):
    criterion, log, pools = fixture()
    for row in log:
        if row['kind'] == 'evaluation':
            row['receipt_usage'] = 'unavailable'
            if row['candidate_id'] == 'M':
                row['allocation_signature']['run#0']['model'] = 'expensive'
    result = pareto_readout.report(pools, log, criterion, tmp_path)
    assert result['cost_axis'] == 'metered_USD' and result['frontier'] == []


def test_failures_zero_incidents_excluded_and_study_hash_never_pooled(tmp_path):
    criterion, log, pools = fixture()
    pools[0]['rows'][2].update(outcome='failed', value=None)  # C first a replicate
    result = pareto_readout.report(pools, log, criterion, tmp_path)
    assert result['candidates']['C']['quality'] == 4.5
    pools[0]['rows'][2].update(outcome='incident')
    assert pareto_readout.report(pools, log, criterion, tmp_path)['candidates']['C']['quality'] == 'unavailable'
    log[-1]['criterion_sha256'] = 'b' * 64
    with pytest.raises(ValueError, match='criterion'):
        pareto_readout.report(pools, log, criterion, tmp_path)
