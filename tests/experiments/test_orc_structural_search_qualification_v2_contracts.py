"""Review regressions: bounded C1 declarations, launch identity and reference scope."""
import copy
import os
from pathlib import Path

import pytest

from tests.experiments.qualification_support import qualified_v2, ref, sha, write
from tests.experiments.test_orc_structural_search_qualification_v2 import change_blockers, load, rehash, validate


@pytest.mark.parametrize('field,value', [
    ('budget', {}), ('power', {}), ('context', {}),
    ('horizon.generations', 10000), ('horizon.episodes_per_generation', 10000),
    ('horizon.generations', True), ('horizon.adaptive_replicates', 2),
    ('horizon.validation_replicates', 4), ('horizon.sealed_replicates', 4),
    ('horizon.finalists_per_campaign', 10000), ('envelope.episode', 10000),
    ('envelope.evaluation', 100000), ('envelope.child_planned_maximum', 10000),
    ('envelope.concurrency', 10000), ('envelope.wall_clock_ceiling_h', 10000),
    ('envelope.per_call_timeout_sec', 10000), ('envelope.child_planned_maximum', 1.5),
    ('final_choice.mean_cost_ceiling_rule', 'unlimited'),
    ('stop_rules', {'persistent_infrastructure': 3}),
    ('budget.steps.P0.planned', 0), ('budget.steps.P0.cap', True),
    ('budget.steps.P1.cap', 1), ('budget.cap_rule', ''), ('power.formula', ''),
    ('power.assumptions', ''), ('power.delta', 2), ('power.R', True),
    ('power.bracket', [2, 1]), ('power.statement', 'superiority demonstrated'),
    ('context.evaluator_version', ''),
])
def test_v2_launch_rejects_unbounded_or_empty_nested_declarations(tmp_path, field, value):
    q = qualified_v2(tmp_path)
    study = load(q.criterion)
    target = study
    keys = field.split('.')
    for key in keys[:-1]:
        target = target.setdefault(key, {})
    target[keys[-1]] = value
    write(q.criterion, study)
    with pytest.raises(ValueError):
        validate(q)


def test_v2_launch_accepts_a_smaller_frozen_offline_horizon(tmp_path):
    q = qualified_v2(tmp_path)
    study = load(q.criterion)
    study['horizon']['generations'] = 2
    study['envelope'].update(episode=15.5, evaluation=30.5, per_call_timeout_sec=15,
                             concurrency=1, wall_clock_ceiling_h=.25)
    study['per_call_timeout_sec'] = 15
    write(q.criterion, study)
    assert validate(q)['mode'] == 'quality'


def test_v2_independent_empty_outputs_qualify_with_borderline_third_sample(tmp_path):
    import shutil
    q = qualified_v2(tmp_path)
    change_blockers(q, [1, 1, 1])
    receipt = load(q.receipt)
    for sample in receipt['family']['tasks']['adaptive']['samples']:
        Path(sample['patch']['file']).write_bytes(b'')
        shutil.rmtree(Path(sample['review_record']['file']).parent)
        sample['review_record'] = sample['review_inputs'] = None
    write(q.receipt, receipt)
    rehash(q)
    assert validate(q)['family']['adaptive']['blockers'] == [1, 1, 1]


def test_v2_independent_identical_nonempty_outputs_remain_independent(tmp_path):
    q = qualified_v2(tmp_path)
    receipt = load(q.receipt)
    first, second = receipt['family']['tasks']['adaptive']['samples']
    patch = Path(second['patch']['file'])
    patch.write_bytes(Path(first['patch']['file']).read_bytes())
    review = Path(second['review_record']['file'])
    value = load(review)
    value['applied']['sha256'] = sha(patch)
    write(review, value)
    rehash(q)
    assert validate(q)['family']['adaptive']['blockers'] == [2, 2]


def test_v2_duplicate_physical_run_is_still_refused(tmp_path):
    q = qualified_v2(tmp_path)
    receipt = load(q.receipt)
    samples = receipt['family']['tasks']['adaptive']['samples']
    samples[1] = copy.deepcopy(samples[0])
    write(q.receipt, receipt)
    rehash(q)
    with pytest.raises(ValueError, match='duplicate original sample'):
        validate(q)


@pytest.mark.parametrize('relative_study', [False, True])
def test_v2_cross_document_references_resolve_against_their_own_parents(tmp_path, relative_study):
    q = qualified_v2(tmp_path)
    receipt, study = load(q.receipt), load(q.criterion)
    old_receipt = q.receipt
    q.receipt = tmp_path / 'other-evidence/receipt.json'
    q.criterion = tmp_path / 'different-config/study.json'
    def relative(value, containing):
        return {**value, 'file': os.path.relpath(value['file'], containing.parent)}
    if relative_study:
        study['family_amendments'] = {k: relative(v, q.criterion) for k, v in study['family_amendments'].items()}
        study['accepted_measure']['criterion'] = relative(study['accepted_measure']['criterion'], q.criterion)
    else:
        receipt['family']['rules'] = {k: relative(v, q.receipt) for k, v in receipt['family']['rules'].items()}
        receipt['measure']['criterion'] = relative(receipt['measure']['criterion'], q.receipt)
    for pool in receipt['measure']['pools']:
        pool['criterion'] = relative(pool['criterion'], q.receipt)
    write(q.receipt, receipt)
    study['qualification'] = relative(ref(q.receipt), q.criterion)
    write(q.criterion, study)
    assert validate(q)['mode'] == 'quality'
    old_receipt.unlink()
    assert validate(q)['mode'] == 'quality'


def test_v2_accepts_byte_identical_evidence_copies_and_rechecks_their_hashes(tmp_path):
    import shutil
    q = qualified_v2(tmp_path)
    study = load(q.criterion)
    copied = tmp_path / 'frozen-copies'
    copied.mkdir()
    for key, value in study['family_amendments'].items():
        target = copied / f'{key}.json'
        shutil.copyfile(value['file'], target)
        study['family_amendments'][key] = ref(target)
    accepted = copied / 'accepted.json'
    shutil.copyfile(study['accepted_measure']['criterion']['file'], accepted)
    study['accepted_measure']['criterion'] = ref(accepted)
    write(q.criterion, study)
    assert validate(q)['mode'] == 'quality'
    from experiments.orc_structural_search.qualification import private_roots
    roots = private_roots(q.criterion, public_roots=[q.runtime, *q.tasks])
    assert any(copied.is_relative_to(root) for root in roots)
    accepted.write_text(accepted.read_text() + ' ')
    with pytest.raises(ValueError, match='hash mismatch'):
        validate(q)


def test_v2_launch_requires_every_stop_rule(tmp_path):
    q = qualified_v2(tmp_path)
    study = load(q.criterion)
    for key in study['stop_rules']:
        broken = copy.deepcopy(study)
        del broken['stop_rules'][key]
        write(q.criterion, broken)
        with pytest.raises(ValueError, match='stop rule'):
            validate(q)


def test_v2_preserves_the_frozen_5400_second_seed_call_allocation(tmp_path):
    q = qualified_v2(tmp_path)
    study = load(q.criterion)
    study['per_call_timeout_sec'] = 5400
    study['envelope']['per_call_timeout_sec'] = 5400
    write(q.criterion, study)
    assert validate(q)['mode'] == 'quality'
