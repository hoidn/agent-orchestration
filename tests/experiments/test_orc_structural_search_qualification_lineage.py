"""Original R55 sample membership is independent of archive filenames and raw blocker totals."""

import json
from pathlib import Path

import pytest

from tests.experiments.qualification_support import qualified, refresh, write, sha, ref
from tests.experiments.test_orc_structural_search_qualification import validate


def original_numbers(q, numbers):
    receipt = json.loads(q.receipt.read_text())
    samples = receipt['family']['tasks']['task']['samples']
    for sample, number in zip(samples, numbers):
        for kind in ('direct_record', 'review_record'):
            path = Path(sample[kind]['file'])
            record = json.loads(path.read_text())
            record['records'] = str(Path(record['records']).with_name(f'run-{number}'))
            if kind == 'review_record':
                record['applied']['path'] = str(Path(record['applied']['path']).parents[1].with_name(f'run-{number}') /
                                               'collected/final.diff')
            write(path, record)
    source = Path(receipt['family']['tasks']['task']['sources'][0]['file'])
    value = json.loads(source.read_text())
    value['single_calls'] = [{'run': f'direct_task/run-{n}'} for n in numbers]
    write(source, value)
    refresh(q)


@pytest.mark.parametrize('numbers', [(3, 4), (7, 8)])
def test_r55_accepts_ordered_original_run_numbers_without_per_task_renumbering(tmp_path, numbers):
    q = qualified(tmp_path)
    original_numbers(q, numbers)
    assert validate(q)['family']['task']['blockers'] == [2, 2]


@pytest.mark.parametrize('numbers', [(4, 3), (3, 3), (3, 5)])
def test_r55_refuses_unordered_duplicate_or_ambiguous_original_runs(tmp_path, numbers):
    q = qualified(tmp_path)
    original_numbers(q, numbers)
    with pytest.raises(ValueError, match='order|duplicate|ambiguous'):
        validate(q)


def test_r55_rejects_consecutive_suffix_omitting_an_original_sample(tmp_path):
    q = qualified(tmp_path)
    original_numbers(q, (4, 5))
    source = Path(json.loads(q.receipt.read_text())['family']['tasks']['task']['sources'][0]['file'])
    value = json.loads(source.read_text())
    value['single_calls'].insert(0, {'run': 'direct_task/run-3'})
    write(source, value)
    refresh(q)
    with pytest.raises(ValueError, match='complete source run membership'):
        validate(q)


def test_empty_diff_does_not_force_review_number_to_equal_direct_number(tmp_path):
    q = qualified(tmp_path)
    receipt = json.loads(q.receipt.read_text())
    first, second = receipt['family']['tasks']['task']['samples']
    Path(first['patch']['file']).write_text('')
    first['review_record'] = None
    path = Path(second['review_record']['file'])
    record = json.loads(path.read_text())
    record['records'] = str(Path(record['records']).with_name('run-1'))
    write(path, record)
    write(q.receipt, receipt)
    refresh(q)
    assert validate(q)['family']['task']['blockers'] == [1, 2]


def frozen_continuation():
    from tests.experiments.qualification_support import REPO
    rule = json.loads((REPO / 'experiments/compare/criteria/calibration-continuation.json').read_text())
    reused = rule['reused_samples']['rung_1']
    samples = [{'direct_record': {'sha256': item['record_sha256']},
                'patch': {'sha256': item['final_diff_sha256']},
                'review_record': {'sha256': item['review_record_sha256']}} for item in reused['samples']]
    samples.append({'review_record': None})
    return rule, dict(reused['summary']), samples


def test_frozen_continuation_keeps_full_identity_in_separate_work_root(tmp_path):
    from experiments.orc_structural_search.qualification_lineage import continuation
    rule, source, samples = frozen_continuation()
    task = Path(rule['new_sample']['slug'])
    package = rule['new_sample']['package_sha256'].split()[0]
    original = Path(rule['work_root']) / 'records/direct_task/run-1'
    assert continuation(samples, tmp_path / 'receipt.json', source, rule, task, package, original) is None


@pytest.mark.parametrize('change', ['reused', 'source', 'task', 'third', 'root', 'review'])
def test_frozen_continuation_rejects_replaced_or_mismatched_evidence(tmp_path, change):
    from experiments.orc_structural_search.qualification_lineage import continuation
    rule, source, samples = frozen_continuation()
    task = Path(rule['new_sample']['slug'])
    package = rule['new_sample']['package_sha256'].split()[0]
    original = Path(rule['work_root']) / 'records/direct_task/run-1'
    if change == 'reused':
        samples[0]['direct_record']['sha256'] = '0' * 64
    elif change == 'source':
        source['sha256'] = '0' * 64
    elif change == 'task':
        task = Path('other')
    elif change == 'third':
        original = original.with_name('run-2')
    elif change == 'root':
        original = tmp_path / 'different-root/records/direct_task/run-1'
    else:
        review = write(tmp_path / 'review.json', {'records': str(Path(rule['work_root']) / 'records/review_once/run-2')})
        samples[-1]['review_record'] = ref(review)
    with pytest.raises(ValueError, match='continuation'):
        continuation(samples, tmp_path / 'receipt.json', source, rule, task, package, original)


def test_same_task_identity_can_have_different_runtime_locations(tmp_path):
    q = qualified(tmp_path)
    sample = json.loads(q.receipt.read_text())['family']['tasks']['task']['samples'][1]
    for key in ('direct_record', 'review_record'):
        path = Path(sample[key]['file'])
        record = json.loads(path.read_text())
        record['task'] = str(tmp_path / 'another-runtime' / 'task')
        write(path, record)
    refresh(q)
    assert validate(q)['family']['task']['blockers'] == [2, 2]


@pytest.mark.parametrize('manifest', ['absent', 'not-frozen'])
def test_cross_root_third_sample_requires_exact_frozen_continuation(tmp_path, manifest):
    from tests.experiments.test_orc_structural_search_qualification import blockers
    q = qualified(tmp_path)
    blockers(q, [1, 1, 1])
    receipt = json.loads(q.receipt.read_text())
    evidence = receipt['family']['tasks']['task']
    third = evidence['samples'][-1]
    work = tmp_path / 'continuation'
    for kind, arm in [('direct_record', 'direct_task'), ('review_record', 'review_once')]:
        path = Path(third[kind]['file'])
        record = json.loads(path.read_text())
        record['records'] = str(work / 'records' / arm / 'run-1')
        if arm == 'review_once':
            record['applied']['path'] = str(work / 'records/direct_task/run-1/collected/final.diff')
        write(path, record)
    source = Path(evidence['sources'][0]['file'])
    data = json.loads(source.read_text())
    data['single_calls'] = data['single_calls'][:2]
    write(source, data)
    if manifest == 'not-frozen':
        rule, _, _ = frozen_continuation()
        rule['work_root'] = str(work)
        evidence['sources'].append(ref(write(tmp_path / 'not-frozen.json', rule)))
    write(q.receipt, receipt)
    refresh(q)
    with pytest.raises(ValueError, match='complete source run membership'):
        validate(q)
