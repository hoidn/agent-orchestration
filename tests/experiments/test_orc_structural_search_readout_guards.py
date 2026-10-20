"""Public readouts require actual scoring provenance; explicit execution projections omit quality."""
import json

import pytest

from experiments.orc_structural_search import scoring, scoring_phase2, three_arm_readout
from experiments.orc_structural_search.records import append_record
from tests.experiments.qualification_support import qualified, write


def test_missing_pool_provenance_never_falls_back_to_quality(tmp_path):
    q = qualified(tmp_path / 'qualified')
    results = write(tmp_path / 'pool/records/results.json', {'criterion_sha256': scoring.sha256_file(q.criterion),
        'runs': [], 'anchors': [], 'agreement': {}, 'excluded_judges': {}})
    log = tmp_path / 'empty.jsonl'
    log.write_text('')
    with pytest.raises(ValueError, match='qualification|scoring runtime|mapping'):
        scoring.read_pool(results, log, q.criterion)


def test_explicit_measure_free_read_pool_emits_execution_only(tmp_path):
    q = qualified(tmp_path / 'qualified')
    log = tmp_path / 'log.jsonl'
    append_record(log, {'kind': 'evaluation', 'candidate_id': 'C', 'evaluation_id': 'e', 'mode': 'three_arm',
        'task_id': q.tasks[0].name, 'replicate': 1, 'outcome': 'failed', 'provider_calls': 2,
        'wall_clock_sec': 7, 'records_dir': str(tmp_path / 'e')})
    result = scoring.read_pool(tmp_path / 'missing-results.json', log, q.criterion, measure_free=True)
    assert result['mode'] == 'measure-free'
    assert result['executions'][0]['provider_calls'] == 2
    assert not any(key in result for key in ('anchors', 'rows', 'mean', 'values', 'decision', 'frontier'))


def test_phase_boundaries_allow_explicit_measure_free_without_historical_metadata(tmp_path):
    q = qualified(tmp_path / 'qualified')
    log = tmp_path / 'log.jsonl'
    log.write_text('')
    driver = write(tmp_path / 'readout.json', {'arms': {}, 'mean': 999, 'anchors': ['secret']})
    a = scoring.phase1_command(log, driver, q.criterion, [], None, measure_free=True)
    b = scoring_phase2.phase2_readout([log], [], None, q.criterion, measure_free=True)
    c = three_arm_readout.readout(log, driver, q.criterion, [], measure_free=True)
    for result in (a, b, c):
        text = json.dumps(result)
        assert result['mode'] == 'measure-free'
        assert 'secret' not in text
        assert 'mean' not in result.get('compile_only', {})
        assert not set(result).intersection({'anchors', 'frontier', 'improvements', 'final_choice', 'decision'})


def test_site_figures_use_native_identity_rows_and_report_unavailable_without_memo():
    rows = [{'evaluation_id': 'e'}]
    evidence = {'e': {'realized_perform_sites': [{'identity': 'run / named.change', 'effect_class': 'provider',
                                               'attempts': 2, 'status': 'completed'}],
                      'planned_perform_sites': [{'identity': 'run / named.change', 'effect_class': 'provider'},
                                               {'identity': 'run / else / repair', 'effect_class': 'provider'}],
                      'unexercised_perform_sites': [{'identity': 'run / else / repair', 'effect_class': 'provider'}]}}
    result = three_arm_readout.child_figures([], {})
    assert result['realized_perform_sites'] == 'unavailable'
    result = three_arm_readout.site_figures(rows, evidence)
    assert result['realized_perform_sites'] == {'run / named.change': 2}
    assert result['unexercised_perform_sites'] == ['run / else / repair']


def test_quality_read_pool_refuses_forged_run_value_and_foreign_row_hash(tmp_path):
    from tests.experiments.readout_support import report_qualification, report_pool
    from tests.experiments.test_orc_structural_search_scoring import log_row, run_row
    q = report_qualification(tmp_path / 'quality', {'tasks': ['task']})
    log = tmp_path / 'log.jsonl'
    record = log_row(tmp_path / 'e', eid='e') | {'criterion_sha256': scoring.sha256_file(q.criterion)}
    append_record(log, record)
    result = write(tmp_path / 'pool/results.json', {'criterion_sha256': scoring.sha256_file(q.criterion),
        'runs': [run_row(tmp_path / 'e', 'e', 8)], 'anchors': [], 'agreement': {}, 'excluded_judges': {}})
    report_pool(result, q, 'task')
    data = json.loads(result.read_text())
    next(iter(data['clones'].values()))['score'] = 1
    write(result, data)
    with pytest.raises(ValueError, match='clone|harness'):
        scoring.read_pool(result, log, q.criterion)
    data['runs'][0]['value'] = 1
    write(result, data)
    log.write_text(json.dumps(record | {'criterion_sha256': 'foreign'}) + '\n')
    with pytest.raises(ValueError, match='criterion_sha256'):
        scoring.read_pool(result, log, q.criterion)


def test_calibrated_anchor_roles_cannot_be_relabelled(tmp_path):
    from experiments.orc_structural_search.readout_guard import anchor_roles
    from tests.experiments.readout_support import report_qualification
    q = report_qualification(tmp_path / 'quality', {'tasks': ['task']})
    criterion = json.loads(q.criterion.read_text())
    anchor_roles(criterion)
    criterion['anchors']['task']['stub'] = criterion['anchors']['task']['upstream']
    with pytest.raises(ValueError, match='calibrated measurement controls'):
        anchor_roles(criterion)


def test_missing_task_anchor_pool_reports_unavailable_floor_without_dropping_failures(tmp_path):
    from tests.experiments.readout_support import report_qualification, report_pool
    from tests.experiments.qualification_support import module_criterion
    from tests.experiments.test_orc_structural_search_pricing import TABLE
    from tests.experiments.test_orc_structural_search_scoring import run_row
    template = json.loads(module_criterion(tmp_path).read_text())
    template.update(quality_floor={'kind': 'above_stub'}, dominance_cost_tolerance=.1,
                    final_choice={'equivalence_tolerance': .5}, price_table=TABLE)
    q = report_qualification(tmp_path / 'qualified', template, ['a', 'b'])
    digest = scoring.sha256_file(q.criterion)
    log = tmp_path / 'log.jsonl'
    append_record(log, {'kind': 'parents', 'orc': 'P', 'python': 'PY'})
    append_record(log, {'kind': 'episode', 'mode': 'three_arm', 'arm': 'I1', 'episode_id': 'C', 'outcome': 'accepted',
                       'candidate_id': 'C', 'parent_candidate_id': 'P', 'provider_calls': 0,
                       'criterion_sha256': digest, 'allocation_changed': False})
    write(tmp_path / 'episodes/C/record.json', {'scan': {'calls': 0, 'hits': [], 'verdict': None}})
    runs = []
    for task in ['a', 'b']:
        for cid in ['P', 'C']:
            eid, records = f'{cid}-{task}', tmp_path / f'{cid}-{task}'
            append_record(log, {'kind': 'evaluation', 'mode': 'three_arm', 'arm': 'I1', 'evaluation_id': eid,
                'candidate_id': cid, 'task_id': task, 'replicate': 1, 'criterion_sha256': digest,
                'records_dir': str(records), 'provider_calls': 1, 'wall_clock_sec': 2,
                'outcome': 'completed' if task == 'a' else 'failed', 'split': 'unavailable',
                'parent_for_arms': ['I1', 'I2', 'I1/module'] if cid == 'P' else []})
            if task == 'a':
                runs.append(run_row(records, eid, 5 if cid == 'P' else 6))
    results = write(tmp_path / 'pool/results.json', {'criterion_sha256': digest, 'runs': runs,
        'anchors': [{'batch': 0, 'judge': 'j', 'anchor': 'a-upstream', 'total': 8},
                    {'batch': 0, 'judge': 'j', 'anchor': 'a-stub', 'total': 0}], 'agreement': {}, 'excluded_judges': {}})
    report_pool(results, q, 'a')
    driver = write(tmp_path / 'driver.json', {'criterion_sha256': digest, 'arms': {
        arm: {'subset': ['C'] if arm == 'I1' else []} for arm in template['arms']}})
    result = three_arm_readout.readout(log, driver, q.criterion, [results])
    assert result['tasks']['b']['no_pool']
    assert result['pareto']['quality_floor'] == 'unavailable'
    assert all(not arm['frontier'] for arm in result['pareto']['arms'].values())
    assert result['pareto']['candidates']['C']['quality'] == 3
