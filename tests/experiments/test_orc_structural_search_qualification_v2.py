"""V2 uses original ratings and per-package family provenance, never cached verdicts."""
import json
from pathlib import Path

import pytest

from tests.experiments.qualification_support import qualified, qualified_v2, ref, sha, write


def load(path):
    return json.loads(Path(path).read_text())


def validate(q, **kw):
    from experiments.orc_structural_search.qualification import validate as gate
    return gate(q.criterion, tasks=q.tasks, runtime=q.runtime, config_sha256=sha(q.criterion), **kw)


def rehash(q):
    receipt = load(q.receipt)
    for task in receipt['family']['tasks'].values():
        for sample in task['samples']:
            for key, value in sample.items():
                if value is not None:
                    sample[key] = ref(Path(value['file']))
        task['sources'] = [ref(Path(r['file'])) for r in task['sources']]
    for pool in receipt['measure']['pools']:
        for key in ('mapping', 'results', 'criterion'):
            pool[key] = ref(Path(pool[key]['file']))
        pool['patches'] = {k: ref(Path(v['file'])) for k, v in pool['patches'].items()}
    receipt['measure']['criterion'] = ref(q.calibration)
    write(q.receipt, receipt)
    study = load(q.criterion)
    study['qualification'] = ref(q.receipt)
    write(q.criterion, study)


@pytest.mark.parametrize('reference', [False, True])
def test_v2_recomputes_four_roles_across_all_stages(tmp_path, reference):
    from tests.experiments.qualification_support import ABSOLUTE_RUBRIC
    q = qualified_v2(tmp_path, rubric=ABSOLUTE_RUBRIC | {'reference': 'upstream' if reference else None})
    proof = validate(q)
    assert set(proof['family']) == {'adaptive', 'validation', 'sealed'}
    assert proof['measure']['adaptive']['pairs'] == 3
    assert proof['measure']['validation']['pairs'] == 2


def _adversarial_pool(tmp_path):
    from tests.experiments.qualification_support import ABSOLUTE_RUBRIC
    q = qualified_v2(tmp_path, rubric=ABSOLUTE_RUBRIC | {'reference': 'upstream'})
    pool = q.pools[0]
    mapping, results = load(pool['mapping']['file']), load(pool['results']['file'])
    judge = q.judges[0]
    ratings = results['clones']['0-upstream']['ratings'][judge]
    return q, pool, mapping, results, judge, ratings


def _reject_rehashed_pool(q, pool, mapping, results):
    write(Path(pool['mapping']['file']), mapping)
    write(Path(pool['results']['file']), results)
    rehash(q)
    with pytest.raises(ValueError):
        validate(q)


@pytest.mark.parametrize('change', ['p1', 'p2', 'p3', 'boolean'])
def test_v2_rejects_rehashed_rating_changes(tmp_path, change):
    q, pool, mapping, results, judge, ratings = _adversarial_pool(tmp_path)
    if change == 'p1':
        results['clones']['0-stub']['ratings'][judge] = {k: 2 for k in ratings}
    elif change in ('p2', 'p3'):
        role = 'partial' if change == 'p2' else 'mutant'
        results['clones'][f'0-{role}']['ratings'][judge] = dict(ratings)
    else:
        ratings[next(iter(ratings))] = True
    _reject_rehashed_pool(q, pool, mapping, results)


@pytest.mark.parametrize('change', ['missing_control', 'duplicate_control', 'missing_batch'])
def test_v2_rejects_rehashed_control_changes(tmp_path, change):
    q, pool, mapping, results, _judge, _ratings = _adversarial_pool(tmp_path)
    if change == 'missing_control':
        mapping['batches'][0].remove('0-mutant')
    elif change == 'duplicate_control':
        mapping['clones']['0-mutant']['labels'] = mapping['clones']['0-partial']['labels']
        results['clones']['0-mutant']['labels'] = mapping['clones']['0-partial']['labels']
    else:
        mapping['batches'].pop()
    _reject_rehashed_pool(q, pool, mapping, results)


@pytest.mark.parametrize('change', ['absent_judge', 'excluded_judge', 'rubric', 'binding', 'rated_reference'])
def test_v2_rejects_rehashed_evaluator_changes(tmp_path, change):
    q, pool, mapping, results, judge, ratings = _adversarial_pool(tmp_path)
    if change == 'absent_judge':
        results['judges'] = []
    elif change == 'excluded_judge':
        results['excluded_judges'] = {judge: 'excluded'}
    elif change == 'rubric':
        mapping['rubric'] = dict(mapping['rubric'], criteria=['wrong'])
    elif change == 'binding':
        other = write(q.runtime / 'wrong.json', {'wrong': True})
        mapping['judges'][judge]['providers'] = str(other)
    else:
        results['clones']['0-reference']['ratings'] = {judge: dict(ratings)}
    _reject_rehashed_pool(q, pool, mapping, results)


@pytest.mark.parametrize('missing', ['baseline', 'B2', 'Q1', 'Q2', 'rule', 'family_task'])
def test_v2_requires_all_packages_stages_and_rules(tmp_path, missing):
    q = qualified_v2(tmp_path)
    receipt = load(q.receipt)
    if missing == 'rule':
        receipt['family']['rules'].pop(next(iter(receipt['family']['rules'])))
    elif missing == 'family_task':
        del receipt['family']['tasks'][q.sealed.name]
    else:
        stage = 'A_prime' if missing == 'baseline' else missing
        receipt['measure']['pools'] = [p for p in receipt['measure']['pools'] if p['stage'] != stage]
    write(q.receipt, receipt)
    rehash(q)
    with pytest.raises(ValueError):
        validate(q)


@pytest.mark.parametrize('change', ['runtime', 'review_model', 'review_repo', 'direct_model', 'pair', 'source', 'extra_run'])
def test_v2_family_revalidates_original_provenance(tmp_path, change):
    q = qualified_v2(tmp_path)
    receipt = load(q.receipt)
    sample = receipt['family']['tasks']['adaptive']['samples'][0]
    key = 'review_inputs' if change in ('review_model', 'review_repo') else 'direct_inputs' if change == 'direct_model' else 'review_record'
    path = Path(sample[key]['file'])
    value = load(path)
    if change == 'runtime':
        value['runtime_commit'] = 'c' * 40
    elif change == 'review_repo':
        value['repo'] = '/wrong/candidate'
    elif change.endswith('_model'):
        value['intent' if change == 'review_model' else 'model'] = 'wrong'
    elif change == 'pair':
        value['applied']['path'] = '/wrong/final.diff'
    elif change == 'source':
        path = Path(receipt['family']['tasks']['adaptive']['sources'][0]['file'])
        value = load(path)
        value['single_calls'] = value['single_calls'][:1]
    else:
        path = Path(sample['direct_record']['file']).parent.parent / 'run-3/record.json'
        value = load(Path(sample['direct_record']['file']))
    write(path, value)
    rehash(q)
    with pytest.raises(ValueError):
        validate(q)


def test_v1_stays_separate_and_cannot_take_v2_receipt(tmp_path):
    old, new = qualified(tmp_path / 'v1'), qualified_v2(tmp_path / 'v2')
    assert validate(old)['measure']['task']['failing_pairs'] == 0
    study = load(old.criterion) | {'qualification': ref(new.receipt)}
    write(old.criterion, study)
    with pytest.raises(ValueError):
        validate(old)


def test_campaign_shape_rejects_missing_fields_and_call_cost(tmp_path):
    from experiments.orc_structural_search.qualification import validate_campaign_criterion
    q = qualified_v2(tmp_path)
    value = load(q.criterion)
    validate_campaign_criterion(value, q.criterion)
    for field in value:
        if field == 'runtime':
            continue
        broken = dict(value)
        del broken[field]
        with pytest.raises(ValueError, match='qualification'):
            validate_campaign_criterion(broken, q.criterion)
    value['final_choice']['mean_cost'] = 'provider_calls'
    with pytest.raises(ValueError):
        validate_campaign_criterion(value, q.criterion)


def test_v2_accepts_original_runtime_and_packages_from_different_checkout(tmp_path):
    import shutil
    import subprocess
    q = qualified_v2(tmp_path / 'origin')
    current = tmp_path / 'current'
    subprocess.run(['git', 'clone', '-q', str(q.runtime), str(current)], check=True)
    (current / 'new-runtime.txt').write_text('current implementation')
    subprocess.run(['git', '-C', str(current), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(current), '-c', 'user.name=Fixture', '-c', 'user.email=x@y',
                    'commit', '-qm', 'current implementation'], check=True)
    study = load(q.criterion)
    for field in ('tasks', 'validation_task', 'sealed_task'):
        old_paths = study[field] if field == 'tasks' else [study[field]]
        copied = []
        for old in old_paths:
            path = current / 'tasks' / Path(old).name
            shutil.copytree(old, path)
            copied.append(str(path))
        study[field] = copied if field == 'tasks' else copied[0]
    write(q.criterion, study)
    q.runtime, q.tasks = current, list(map(Path, study['tasks']))
    proof = validate(q)
    assert proof['family']['adaptive']['runtime_commit'] != subprocess.check_output(
        ['git', '-C', str(current), 'rev-parse', 'HEAD'], text=True).strip()


def test_v2_recomputes_aggregate_spread_instead_of_trusting_cached_anchors(tmp_path):
    q = qualified_v2(tmp_path)
    path = Path(q.pools[1]['results']['file'])
    results = load(path)
    scores = {'upstream': [2, 2, 1, 0], 'stub': [0, 0, 0, 0],
              'partial': [2, 1, 0, 0], 'mutant': [2, 1, 0, 0]}
    for cid, clone in results['clones'].items():
        clone['ratings'][q.judges[0]] = dict(zip(load(q.criterion)['rubric']['criteria'], scores[cid.split('-', 1)[1]]))
    results['anchors'] = []
    results['calibration'] = {'passed': True}
    write(path, results)
    rehash(q)
    with pytest.raises(ValueError, match='aggregate anchor spread'):
        validate(q)


def test_v2_accepts_fillers_and_checks_their_raw_components_and_hashes(tmp_path):
    q = qualified_v2(tmp_path)
    receipt = load(q.receipt)
    pool = receipt['measure']['pools'][0]
    mapping_path, result_path = Path(pool['mapping']['file']), Path(pool['results']['file'])
    mapping, results = load(mapping_path), load(result_path)
    info = {'arm': 'filler', 'run': None, 'labels': ['candidate']}
    mapping['clones']['filler'] = info
    mapping['batches'][0].append('filler')
    patch = mapping_path.parent / 'patches/filler.diff'
    patch.write_text('synthetic filler')
    pool['patches']['filler'] = ref(patch)
    results['clones']['filler'] = info | {'ratings': {q.judges[0]: {k: 1 for k in load(q.criterion)['rubric']['criteria']}}}
    write(mapping_path, mapping)
    write(result_path, results)
    write(q.receipt, receipt)
    rehash(q)
    assert validate(q)['measure']['adaptive']['pairs'] == 3
    results['clones']['filler']['ratings'][q.judges[0]]['scope'] = -1
    write(result_path, results)
    rehash(q)
    with pytest.raises(ValueError, match='components'):
        validate(q)


def test_v2_private_roots_cover_all_rules_criteria_originals_and_patches(tmp_path):
    from experiments.orc_structural_search.qualification import private_roots
    q = qualified_v2(tmp_path)
    roots = private_roots(q.criterion, public_roots=[q.runtime, *q.tasks])
    receipt = load(q.receipt)
    refs = [*receipt['family']['rules'].values(), receipt['measure']['criterion']]
    refs += [p['criterion'] for p in receipt['measure']['pools']]
    refs += [r for p in receipt['measure']['pools'] for r in p['patches'].values()]
    assert all(any(Path(ref['file']).is_relative_to(root) for root in roots) for ref in refs)
    assert all(not q.runtime.is_relative_to(root) for root in roots)


def change_blockers(q, counts):
    import copy
    receipt = load(q.receipt)
    evidence = receipt['family']['tasks']['adaptive']
    samples = evidence['samples']
    if len(counts) == 3:
        sample = copy.deepcopy(samples[-1])
        for key, info in sample.items():
            old = Path(info['file'])
            new = Path(str(old).replace('run-2', 'run-3'))
            new.parent.mkdir(parents=True, exist_ok=True)
            new.write_bytes(old.read_bytes())
            if key.endswith('_record'):
                value = load(new)
                value['records'] = str(new.parent)
                value['command'] = value['command'].replace('run-2', 'run-3')
                if key == 'review_record':
                    value['applied']['path'] = value['applied']['path'].replace('run-2', 'run-3')
                write(new, value)
            if key == 'patch':
                new.write_text('distinct third patch')
            sample[key] = ref(new)
        review = Path(sample['review_record']['file'])
        write(review, load(review) | {'applied': {'path': sample['patch']['file'], 'sha256': sample['patch']['sha256']}})
        samples.append(sample)
        source = Path(evidence['sources'][0]['file'])
        write(source, load(source) | {'single_calls': [{'run': f'direct_task/run-{i + 1}'} for i in range(3)]})
    for sample, count in zip(samples, counts):
        path = Path(sample['review_record']['file'])
        value = load(path)
        value['review']['findings'] = ['finding'] * count
        write(path, value)
    write(q.receipt, receipt)
    rehash(q)


@pytest.mark.parametrize('counts,passed', [([1, 2], True), ([1, 1], False), ([1, 1, 1], True),
                                         ([0, 1, 4], False), ([2, 2, 2], False)])
def test_v2_family_threshold_and_borderline_are_recomputed(tmp_path, counts, passed):
    q = qualified_v2(tmp_path)
    change_blockers(q, counts)
    if passed:
        assert validate(q)['family']['adaptive']['blockers'] == counts
    else:
        with pytest.raises(ValueError):
            validate(q)


def test_v2_rejects_origin_timeout_mismatch(tmp_path):
    q = qualified_v2(tmp_path)
    study = load(q.criterion)
    study['judge_bindings'][q.judges[0]]['timeout_sec'] += 1
    write(q.criterion, study)
    with pytest.raises(ValueError, match='binding'):
        validate(q)


def test_v2_scoring_read_pool_reaches_actual_qualification_and_clone_join(tmp_path):
    from experiments.orc_structural_search import qualification, scoring
    from experiments.compare import summarize
    from experiments.orc_structural_search.records import append_record
    q = qualified_v2(tmp_path / 'evidence')
    root = tmp_path / 'pool'
    records = root / 'records'
    records.mkdir(parents=True)
    run = str(tmp_path / 'candidate/run-1')
    mapping = {'runtime': str(q.runtime), 'task': str(q.tasks[0]), 'criterion_sha256': sha(q.criterion),
        'judges': {q.judges[0]: {'providers': str(q.bindings)}}, 'rubric': load(q.criterion)['rubric'],
        'clones': {'candidate': {'arm': 'e1', 'run': run, 'labels': ['final']}},
        'runs': {run: {'arm': 'e1', 'selected': 'final', 'calls': 1, 'wall_clock_sec': 3}}}
    write(records / 'mapping.json', mapping)
    write(records / f'score-inputs-{q.judges[0]}.json', {'judge_model': q.judges[0], 'criterion_sha256': sha(q.criterion)})
    results = {'criterion_sha256': sha(q.criterion), 'clones': {'candidate': mapping['clones']['candidate'] |
        {'score': 4, 'hidden': None}}, 'runs': summarize.run_rows(mapping, {'candidate': 4}, {}),
        'anchors': [], 'agreement': {}, 'excluded_judges': {}}
    result_path = write(records / 'results.json', results)
    log = tmp_path / 'log.jsonl'
    append_record(log, {'kind': 'evaluation', 'evaluation_id': 'e1', 'candidate_id': 'candidate',
        'task_id': q.tasks[0].name, 'outcome': 'completed', 'replicate': 1, 'mode': 'catalog',
        'seed': 'direct', 'criterion_sha256': sha(q.criterion), 'records_dir': run})
    joined = scoring.read_pool(result_path, log, q.criterion)
    assert joined['rows'][0]['clone_ids'] == ['candidate']
    assert qualification.private_roots(q.criterion, public_roots=[q.runtime, *q.tasks])
    results['clones']['candidate']['run'] = '/wrong/run'
    write(result_path, results)
    with pytest.raises(ValueError, match='lineage'):
        scoring.read_pool(result_path, log, q.criterion)


def test_v2_family_tracks_one_contaminated_replacement_without_omitting_attempts(tmp_path):
    import copy
    q = qualified_v2(tmp_path)
    change_blockers(q, [2, 2, 2])
    receipt = load(q.receipt)
    evidence = receipt['family']['tasks']['adaptive']
    omitted = evidence['samples'].pop(0)
    original = Path(omitted['direct_record']['file'])
    record = load(original)
    record['scan']['hits'] = [{'pattern': 'private'}]
    record['scan']['verdict'] = {'verdict': 'contaminated', 'reason': 'synthetic contamination'}
    write(original, record)
    # The contaminated direct is replaced before it is reviewed.
    import shutil
    shutil.rmtree(Path(omitted['review_record']['file']).parent)
    evidence['attempts'] = [{'record': ref(original), 'replaced_by': copy.deepcopy(evidence['samples'][0]['direct_record'])}]
    write(q.receipt, receipt)
    rehash(q)
    assert validate(q)['family']['adaptive']['blockers'] == [2, 2]


@pytest.mark.parametrize('change', ['price_table', 'judge_subset', 'reference_free_with_reference', 'amendment'])
def test_v2_rejects_changed_accepted_identity_and_family_selection(tmp_path, change):
    q = qualified_v2(tmp_path)
    study, receipt = load(q.criterion), load(q.receipt)
    if change == 'price_table':
        study['price_table']['models'][q.judges[0]]['output'] += 1
        write(q.criterion, study)
    elif change == 'judge_subset':
        origin = load(q.calibration)
        origin['judges'].append('claude-sonnet-5-5')
        write(q.calibration, origin)
        study['accepted_measure']['criterion'] = ref(q.calibration)
        write(q.criterion, study)
        for pool in receipt['measure']['pools']:
            for key in ('mapping', 'results'):
                path = Path(pool[key]['file'])
                value = load(path)
                value['criterion_sha256'] = sha(q.calibration)
                write(path, value)
        write(q.receipt, receipt)
        rehash(q)
    elif change == 'reference_free_with_reference':
        pool = receipt['measure']['pools'][0]
        path = Path(pool['mapping']['file'])
        mapping = load(path)
        mapping['references'] = ['0-upstream']
        write(path, mapping)
        rehash(q)
    elif change == 'amendment':
        package = next(iter(receipt['family']['rules']))
        receipt['family']['rules'][package] = study['family_amendments']['amends_6']
        write(q.receipt, receipt)
        rehash(q)
    with pytest.raises(ValueError):
        validate(q)


def test_v2_supports_accepted_A_and_the_full_declared_two_judge_denominator(tmp_path):
    q = qualified_v2(tmp_path, judges=('gpt-5.6-terra', 'claude-sonnet-5-5'), accepted_step='A')
    assert validate(q)['measure']['adaptive']['pairs'] == 6


def test_campaign_schema_refuses_missing_nested_horizon_and_endpoint_fields(tmp_path):
    import copy
    from experiments.orc_structural_search.qualification import validate_campaign_criterion
    q = qualified_v2(tmp_path)
    value = load(q.criterion)
    for field in ('horizon', 'endpoints', 'final_choice'):
        for key in value[field]:
            broken = copy.deepcopy(value)
            del broken[field][key]
            with pytest.raises(ValueError):
                validate_campaign_criterion(broken, q.criterion)


def test_v2_disclosed_reference_must_be_the_verified_upstream_patch(tmp_path):
    from tests.experiments.qualification_support import ABSOLUTE_RUBRIC
    q = qualified_v2(tmp_path, rubric=ABSOLUTE_RUBRIC | {'reference': 'upstream'})
    Path(q.pools[0]['patches']['0-reference']['file']).write_text('wrong disclosed reference')
    rehash(q)
    with pytest.raises(ValueError):
        validate(q)
