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
        assert 'secret' not in text and '999' not in text
        assert not set(result).intersection({'anchors', 'frontier', 'improvements', 'final_choice', 'decision'})
