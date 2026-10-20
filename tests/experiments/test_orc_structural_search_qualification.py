"""Fail-closed qualification of external raw evidence, with no provider spend."""

import json
from pathlib import Path

import pytest

from tests.experiments.qualification_support import qualified, refresh, sha, write, measure_free


def validate(q, **kwargs):
    from experiments.orc_structural_search.qualification import validate as gate
    return gate(q.criterion, runtime=q.runtime, tasks=q.tasks, config_sha256=sha(q.criterion), **kwargs)


def test_raw_qualified_receipt_recomputes_family_and_measure(tmp_path):
    q = qualified(tmp_path)
    result = validate(q)
    assert result['qualification_sha256'] == sha(q.receipt)
    assert result['family']['task']['blockers'] == [2, 2]
    assert result['measure']['task']['failing_pairs'] == 0


def test_missing_criterion_is_not_measure_free():
    from experiments.orc_structural_search.qualification import validate as gate
    with pytest.raises(ValueError, match='criterion'):
        gate(None)


def test_measure_free_execution_and_explicit_historical_projection(tmp_path):
    from experiments.orc_structural_search.qualification import validate as gate
    path = measure_free(tmp_path)
    assert gate(path, config_sha256=sha(path))['mode'] == 'measure-free'
    with pytest.raises(ValueError, match='measure-free'):
        gate(path, operation='quality')
    old = write(tmp_path / 'old.json', {})
    assert gate(old, operation='readout', measure_free=True)['mode'] == 'measure-free'
    with pytest.raises(ValueError):
        gate(old, config_sha256=sha(old))


@pytest.mark.parametrize('field', ['purpose', 'qualification', 'measurement'])
def test_quality_requires_explicit_valid_evidence(tmp_path, field):
    q = qualified(tmp_path)
    study = json.loads(q.criterion.read_text())
    if field == 'purpose':
        study[field] = 'calibration'
    else:
        del study[field]
    write(q.criterion, study)
    with pytest.raises(ValueError):
        validate(q)


def test_hashes_are_reverified_each_operation(tmp_path):
    q = qualified(tmp_path)
    validate(q)
    q.receipt.write_text(q.receipt.read_text() + ' ')
    with pytest.raises(ValueError, match='hash mismatch'):
        validate(q)


@pytest.mark.parametrize('change', ['model', 'effort', 'pair', 'findings', 'variant', 'scan', 'order', 'base'])
def test_r55_rejects_raw_evidence_mismatches_even_after_rehashing(tmp_path, change):
    q = qualified(tmp_path)
    receipt = json.loads(q.receipt.read_text())
    sample = receipt['family']['tasks']['task']['samples'][0]
    key = 'direct_inputs' if change in ('model', 'effort') else 'review_record'
    path = Path(sample[key]['file'])
    value = json.loads(path.read_text())
    if change in ('model', 'effort'):
        value[change] = 'wrong'
    elif change == 'pair':
        value['applied']['path'] = '/other/final.diff'
    elif change == 'findings':
        value['review']['findings'] = [True]
    elif change == 'variant':
        value['review']['variant'] = 'FAKE'
    elif change == 'scan':
        value['scan']['calls'] = 0
    elif change == 'order':
        path = Path(sample['direct_record']['file'])
        value = json.loads(path.read_text())
        value['records'] = str(Path(value['records']).with_name('run-5'))
    else:
        value['base'] = 'wrong'
    write(path, value)
    refresh(q)
    with pytest.raises(ValueError):
        validate(q)


def blockers(q, counts):
    receipt = json.loads(q.receipt.read_text())
    samples = receipt['family']['tasks']['task']['samples']
    if len(counts) == 3:
        import copy
        third = copy.deepcopy(samples[-1])
        for key, value in third.items():
            old = Path(value['file'])
            new = Path(str(old).replace('run-2', 'run-3'))
            new.parent.mkdir(parents=True, exist_ok=True)
            new.write_bytes(old.read_bytes())
            if key.endswith('_record'):
                record = json.loads(new.read_text())
                record['records'] = record['records'].replace('run-2', 'run-3')
                if key == 'review_record':
                    record['applied']['path'] = record['applied']['path'].replace('run-2', 'run-3')
                write(new, record)
            third[key]['file'] = str(new)
        samples.append(third)
        write(q.receipt, receipt)
    for sample, count in zip(samples, counts):
        path = Path(sample['review_record']['file'])
        record = json.loads(path.read_text())
        record['review']['findings'] = ['finding'] * count
        write(path, record)
    refresh(q)


@pytest.mark.parametrize('counts,passes', [([0, 1], False), ([1, 1], False), ([1, 2], True),
    ([1, 1, 1], True), ([1, 1, 0], False), ([2, 2, 2], False)])
def test_r55_exact_two_or_three_sample_rule(tmp_path, counts, passes):
    q = qualified(tmp_path)
    blockers(q, counts)
    if passes:
        assert validate(q)['family']['task']['blockers'] == counts
    else:
        with pytest.raises(ValueError):
            validate(q)


def test_completed_empty_diff_counts_one_without_review(tmp_path):
    q = qualified(tmp_path)
    receipt = json.loads(q.receipt.read_text())
    sample = receipt['family']['tasks']['task']['samples'][0]
    Path(sample['patch']['file']).write_text('')
    sample['review_record'] = None
    write(q.receipt, receipt)
    refresh(q)
    assert validate(q)['family']['task']['blockers'] == [1, 2]


@pytest.mark.parametrize('change', ['candidate', 'label', 'hash', 'batch', 'rating', 'criterion', 'judge'])
def test_measure_rejects_contradictory_or_candidate_calibration_evidence(tmp_path, change):
    q = qualified(tmp_path)
    pool = q.pools[0]
    mapping_path, result_path = Path(pool['mapping']['file']), Path(pool['results']['file'])
    mapping, result = json.loads(mapping_path.read_text()), json.loads(result_path.read_text())
    if change == 'candidate':
        mapping['clones']['upstream']['arm'] = 'candidate'
    elif change == 'label':
        mapping['clones']['upstream']['labels'] = ['unknown']
    elif change == 'hash':
        Path(pool['patches']['upstream']['file']).write_text('other')
    elif change == 'batch':
        mapping['batches'] = [['upstream', 'upstream']]
    elif change == 'rating':
        result['clones']['upstream']['ratings'][q.judges[0]]['scope'] = True
    elif change == 'criterion':
        result['criterion_sha256'] = '0' * 64
    else:
        mapping['judges']['other'] = mapping['judges'].pop(q.judges[0])
    write(mapping_path, mapping)
    write(result_path, result)
    refresh(q)
    with pytest.raises(ValueError):
        validate(q)


def test_missing_pairs_cannot_be_hidden_by_error_tolerance(tmp_path):
    q = qualified(tmp_path, judges=('judge-a', 'judge-b'))
    for path in (q.criterion, q.calibration):
        data = json.loads(path.read_text())
        data['calibration']['error_rate'] = 1
        write(path, data)
    mapping = Path(q.pools[0]['mapping']['file'])
    data = json.loads(mapping.read_text())
    data['criterion_sha256'] = sha(q.calibration)
    write(mapping, data)
    result = Path(q.pools[0]['results']['file'])
    data = json.loads(result.read_text())
    data['criterion_sha256'] = sha(q.calibration)
    data['judges'].remove('judge-b')
    data['excluded_judges'] = {'judge-b': 'excluded'}
    for clone in data['clones'].values():
        clone['ratings'].pop('judge-b')
    write(result, data)
    refresh(q)
    with pytest.raises(ValueError, match='observed'):
        validate(q)


@pytest.mark.parametrize('alter', ['runtime', 'binding', 'judge'])
def test_actual_scoring_dispatch_must_match_verified_measurement(tmp_path, alter):
    q = qualified(tmp_path)
    options = {}
    if alter == 'runtime':
        (q.runtime / 'experiments/compare/score.orc').write_text('other workflow')
    elif alter == 'binding':
        other = write(tmp_path / 'other.json', {'providers.judge': 'other'})
        options['judges'] = [f'{q.judges[0]}={other}']
    else:
        options['judges'] = ['other']
    with pytest.raises(ValueError):
        validate(q, **options)


def test_measurement_reference_locations_are_not_identity(tmp_path):
    q = qualified(tmp_path)
    data = json.loads(q.calibration.read_text())
    source = Path(data['measurement']['evaluator']['score_workflow']['file'])
    moved = tmp_path / 'other-score.orc'
    moved.write_bytes(source.read_bytes())
    data['measurement']['evaluator']['score_workflow']['file'] = str(moved)
    write(q.calibration, data)
    for ref in (q.pools[0]['mapping'], q.pools[0]['results']):
        path = Path(ref['file'])
        data = json.loads(path.read_text())
        data['criterion_sha256'] = sha(q.calibration)
        write(path, data)
    refresh(q)
    assert validate(q)['mode'] == 'quality'


def test_package_hash_matches_sha256sum_and_rejects_symlinks(tmp_path):
    from experiments.orc_structural_search.qualification_io import package_digest
    q = qualified(tmp_path)
    assert package_digest(q.tasks[0]) == json.loads(q.criterion.read_text())['measurement']['tasks']['task']['package_sha256']
    (q.tasks[0] / 'linked').symlink_to(q.criterion)
    with pytest.raises(ValueError, match='symlink'):
        validate(q)


def test_private_roots_hide_only_evidence_and_refuse_broad_layout(tmp_path):
    from experiments.orc_structural_search.qualification import private_roots
    q = qualified(tmp_path)
    roots = private_roots(q.criterion, public_roots=[q.runtime, *q.tasks])
    assert roots == (q.receipt.parent,)
    assert not any(q.runtime.is_relative_to(root) for root in roots)
    with pytest.raises(ValueError, match='mask public'):
        private_roots(q.criterion, workspace_roots=[q.receipt.parent / 'active'])


def oracle(q):
    from tests.experiments.qualification_support import ref
    engine = q.receipt.parent / 'oracle/engine.py'
    engine.parent.mkdir()
    engine.write_text('frozen oracle')
    controls, proofs = [], []
    package = json.loads(q.criterion.read_text())['measurement']['tasks']['task']['package_sha256']
    for index, expected in enumerate(('accept', 'accept', 'reject')):
        submission = engine.parent / f'submission-{index}.txt'
        submission.write_text(str(index))
        controls.append({'id': str(index), 'expected': expected, 'structure_class': str(index),
                         'submission_sha256': sha(submission)})
        result = write(engine.parent / f'result-{index}.json', {
            'task_id': 'task', 'package_sha256': package, 'oracle_sha256': sha(engine),
            'submission_sha256': sha(submission), 'checks': {'behavior': expected == 'accept'}})
        proofs.append({'id': str(index), 'submission': ref(submission), 'result': ref(result)})
    rule = write(engine.parent / 'rule.json', {'oracle': ref(engine), 'checks': ['behavior'],
        'tasks': {'task': {'package_sha256': package, 'controls': controls}}})
    receipt = json.loads(q.receipt.read_text())
    receipt['family'] = {'kind': 'oracle-controls-v1', 'rule': ref(rule),
                        'tasks': {'task': {'package_sha256': package, 'controls': proofs}}}
    write(q.receipt, receipt)
    refresh(q)
    return rule, proofs


def test_oracle_family_qualifies_controls_but_still_requires_blind_measure(tmp_path):
    q = qualified(tmp_path)
    oracle(q)
    result = validate(q)
    assert result['family']['task'] == {'controls': 3, 'accepted': 2, 'rejected': 1}
    assert result['measure']['task']['pairs'] == 1


@pytest.mark.parametrize('change', ['structure', 'submission', 'checktype', 'oracle', 'expected'])
def test_oracle_rejects_bad_frozen_control_identities(tmp_path, change):
    from tests.experiments.qualification_support import ref
    q = qualified(tmp_path)
    rule, controls = oracle(q)
    value = json.loads(rule.read_text())
    if change == 'structure':
        value['tasks']['task']['controls'][1]['structure_class'] = '0'
        write(rule, value)
    elif change == 'expected':
        value['tasks']['task']['controls'][2]['expected'] = 'accept'
        write(rule, value)
    else:
        path = Path(controls[0]['result']['file'])
        result = json.loads(path.read_text())
        if change == 'submission':
            result['submission_sha256'] = '0' * 64
        elif change == 'checktype':
            result['checks']['behavior'] = 1
        else:
            result['oracle_sha256'] = '0' * 64
        write(path, result)
    receipt = json.loads(q.receipt.read_text())
    receipt['family']['rule'] = ref(rule)
    for control in receipt['family']['tasks']['task']['controls']:
        control['result'] = ref(Path(control['result']['file']))
    write(q.receipt, receipt)
    refresh(q)
    with pytest.raises(ValueError):
        validate(q)
