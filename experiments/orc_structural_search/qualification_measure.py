"""Verified evaluator identities and clone-joined blind-control calibration."""

from pathlib import Path

from experiments.compare.pool import DEFAULT_RUBRIC

from experiments.orc_structural_search.qualification_io import (
    calibration, digest, names, normalized, read, reference, require)

V1_RUBRIC = '72ede203ff5ac3b7552d033474db2d8e45fdba11b3cfb514bce643e70c284700'
COMPONENTS = ('root_cause', 'scope', 'generality', 'layering')


def measurement(criterion, containing, tasks, packages):
    block = criterion['measurement']
    require(isinstance(block, dict) and set(block) == {'evaluator', 'tasks'}, 'invalid measurement identity')
    require(set(block['tasks']) == set(tasks), 'measurement tasks differ from study tasks')
    declared = names(criterion['judges'], 'judges')
    evaluator = block['evaluator']
    require(set(evaluator) == {'score_workflow', 'judges'} and set(evaluator['judges']) == declared,
            'measurement judges differ from criterion')
    for name, judge in evaluator['judges'].items():
        require('fable' not in name.lower() and judge['effort'] == 'high', 'unsupported judge model/effort')
    for name, task in tasks.items():
        info = block['tasks'][name]
        require(info['package_sha256'] == packages[name], 'measurement package hash mismatch')
        require(set(info['controls']) == {'upstream', 'stub'}, 'expected upstream/stub controls')
        labels = []
        for control in info['controls'].values():
            source = reference(control['source'], containing)
            label = control['label']
            require(isinstance(label, str) and label , 'anchor label mismatch')
            anchor = task / 'anchors' / f'{label}.diff'
            require(anchor.is_file() and digest(anchor) == control['source']['sha256'], 'control differs from task anchor')
            labels.append(label)
        require(len(set(labels)) == 2, 'duplicate anchor labels')
    return normalized(block, containing)


def dispatch(criterion, containing, runtime, judges):
    require(runtime is not None, 'actual scoring runtime required')
    require(criterion.get('rubric', DEFAULT_RUBRIC) == DEFAULT_RUBRIC, 'unsupported v1 rubric selection')
    evaluator = criterion['measurement']['evaluator']
    workflow = Path(runtime) / 'experiments/compare/score.orc'
    reference(evaluator['score_workflow'], containing)
    require(evaluator['score_workflow']['sha256'] == V1_RUBRIC, 'unsupported v1 rubric workflow')
    require(workflow.is_file() and digest(workflow) == evaluator['score_workflow']['sha256'],
            'actual runtime score workflow differs from measurement')
    specs = judges if judges is not None else planned_judges(criterion, containing, runtime)
    selected = {}
    for spec in specs:
        require(isinstance(spec, str) and bool(spec), 'invalid judge dispatch')
        name, _, binding = spec.partition('=')
        require(name not in selected, 'duplicate dispatch judge')
        selected[name] = Path(binding) if binding else Path(runtime) / 'experiments/compare/score.providers.json'
    require(set(selected) == set(criterion['judges']), 'actual dispatch judges differ from criterion')
    for name, binding in selected.items():
        expected = evaluator['judges'][name]['providers']
        reference(expected, containing)
        require(binding.is_file() and digest(binding) == expected['sha256'], 'actual judge provider binding differs')


def planned_judges(criterion, containing, runtime):
    """Launches validate planned bindings; explicit judge arguments still own actual dispatch."""
    evaluator = criterion['measurement']['evaluator']['judges']
    declared = criterion.get('judge_bindings')
    if 'judge_bindings' in criterion:
        require(isinstance(declared, dict) and set(declared) == set(evaluator), 'planned judge bindings differ')
    selected = []
    for name, info in evaluator.items():
        path = reference(info['providers'], containing)
        if declared is not None:
            raw = declared[name]
            require(isinstance(raw, str) and bool(raw), 'invalid planned judge binding path')
            path = Path(runtime) / raw
        selected.append(f'{name}={path}')
    return selected


def rating_total(value):
    require(isinstance(value, dict), 'malformed control rating')
    components = [value[key] for key in COMPONENTS]
    require(all(type(number) is int and 0 <= number <= 2 for number in components), 'invalid rating components')
    return sum(components)


def check_rating_judges(results, observed, declared):
    for clone in results['clones'].values():
        ratings = clone['ratings']
        require(isinstance(ratings, dict) and set(ratings) <= observed <= declared,
                'rating judges contradict results judge identities')


def control_clones(pool, mapping, results, containing, controls):
    clones = mapping['clones']
    require(isinstance(clones, dict) and clones and set(clones) == set(results['clones']) == set(pool['patches']),
            'contradictory calibration clone identities')
    roles = {}
    for cid, clone in clones.items():
        require(clone.get('arm') == 'anchor' and clone.get('run') is None, 'candidate in calibration pool')
        labels = clone.get('labels')
        require(isinstance(labels, list) and len(labels) == 1, 'invalid anchor label')
        role = next((role for role, c in controls.items() if c['label'] == labels[0]), None)
        require(role is not None, 'undeclared calibration anchor')
        rated = results['clones'][cid]
        require(all(rated.get(key) == clone.get(key) for key in ('arm', 'run', 'labels')),
                'results clone identity differs from mapping')
        reference(pool['patches'][cid], containing)
        require(pool['patches'][cid]['sha256'] == controls[role]['pooled_patch_sha256'], 'pooled patch identity mismatch')
        roles[cid] = role
    return roles


def pool_pairs(pool, containing, calibration_sha, study, study_path, expected):
    mapping = read(reference(pool['mapping'], containing))
    results = read(reference(pool['results'], containing))
    require(mapping['criterion_sha256'] == results['criterion_sha256'] == calibration_sha,
            'calibration criterion hash does not match pool/results')
    from experiments.orc_structural_search.qualification import pool_context
    context = pool_context(reference(pool['mapping'], containing).parent.parent)
    dispatch(study, study_path, context['runtime'], context['judges'])
    task = pool['task_id']
    require(task in expected and Path(mapping['task']).name == task, 'calibration pool task mismatch')
    judges = set(study['judges'])
    require(set(mapping['judges']) == judges, 'calibration mapping judges differ')
    observed_judges = results['judges']
    require(isinstance(observed_judges, list) and len(set(observed_judges)) == len(observed_judges) and
            set(observed_judges) <= judges, 'invalid calibration results judges')
    excluded = results['excluded_judges']
    require(isinstance(excluded, (dict, list)) and set(excluded) <= judges and not set(excluded) & set(observed_judges),
            'invalid excluded judges')
    check_rating_judges(results, set(observed_judges), judges)
    controls = study['measurement']['tasks'][task]['controls']
    roles = control_clones(pool, mapping, results, containing, controls)
    require(not mapping.get('runs'), 'candidate runs in calibration pool')
    return task, batch_pairs(mapping['batches'], results, roles, judges, excluded, study)


def batch_pairs(batches, results, roles, judges, excluded, study):
    seen, pairs = set(), []
    require(isinstance(batches, list) and batches, 'empty calibration batches')
    margin, _ = calibration(study['calibration'])
    for batch in batches:
        check_batch(batch, roles, seen)
        seen.update(batch)
        by_role = {roles[cid]: results['clones'][cid]['ratings'] for cid in batch}
        for judge in sorted(judges):
            rated = [by_role[role].get(judge) for role in ('upstream', 'stub')]
            observed = judge not in excluded and all(value is not None for value in rated)
            passed = observed and rating_total(rated[0]) - rating_total(rated[1]) >= margin
            pairs.append({'judge': judge, 'observed': observed, 'passed': passed})
    require(seen == set(roles), 'unbatched calibration clones')
    return pairs


def check_batch(batch, roles, seen):
    require(isinstance(batch, list) and len(batch) == 2 and len(set(batch)) == 2 and
            set(batch) <= set(roles), 'invalid calibration batch membership')
    require(not seen.intersection(batch) and {roles[cid] for cid in batch} == {'upstream', 'stub'},
            'duplicate or missing batch controls')


def validate_measure(measure, containing, study, study_path, tasks, packages, identity):
    criterion_path = reference(measure['criterion'], containing)
    criterion = read(criterion_path)
    require(criterion.get('purpose') == 'calibration' and criterion.get('calibration_kind') == 'measure',
            'measure evidence is not a calibration criterion')
    cap = criterion['budget']['call_cap']
    require(type(cap) is int and cap > 0 and not criterion.get('candidates'), 'calibration needs positive budget and no candidates')
    require(calibration(criterion['calibration']) == calibration(study['calibration']), 'calibration rules differ')
    require(measurement(criterion, criterion_path, tasks, packages) == identity, 'measurement identities differ')
    pools = measure['pools']
    require(isinstance(pools, list) and pools, 'missing calibration pools')
    pairs, identities = {name: [] for name in tasks}, set()
    for pool in pools:
        identity_key = pool['mapping']['sha256']
        require(identity_key not in identities, 'duplicate calibration pool')
        identities.add(identity_key)
        task, observed = pool_pairs(pool, containing, measure['criterion']['sha256'], study, study_path, tasks)
        pairs[task].extend(observed)
    return task_statistics(pairs, study)


def task_statistics(pairs, study):
    figures = {}
    for task, rows in pairs.items():
        require(rows and all(any(r['judge'] == j and r['observed'] for r in rows) for j in study['judges']),
                'every judge needs an observed control pair per task')
        failed = sum(not row['passed'] for row in rows)
        rate = failed / len(rows)
        require(rate <= calibration(study['calibration'])[1], 'measure calibration error_rate exceeded')
        figures[task] = {'pairs': len(rows), 'failing_pairs': failed, 'error_rate': rate}
    return figures
