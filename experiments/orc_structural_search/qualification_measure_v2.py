"""C1's control measurement, preserving each pool's frozen origin identity."""
import hashlib
from pathlib import Path

from experiments.compare import pool as harness, summarize
from experiments.compare.repos import runtime_commit
from experiments.orc_structural_search.qualification_io import digest, names, read, reference, require, same_reference

ROLES = frozenset(('upstream', 'stub', 'partial', 'mutant'))


def control_roles(criterion):
    return frozenset(harness.CONTROL_ROLES) if harness.control_means(criterion) else ROLES


def binding_path(info, containing, runtime):
    require(isinstance(info, dict) and set(info) == {'providers', 'providers_sha256', 'effort', 'timeout_sec'},
            'V2 judge binding must freeze providers, hash, effort and timeout')
    require(info['effort'] == 'high' and type(info['timeout_sec']) is int and info['timeout_sec'] > 0,
            'invalid V2 judge effort/timeout')
    path = Path(runtime) / info['providers']
    reference({'file': str(path), 'sha256': info['providers_sha256']}, containing)
    return path


def dispatch(criterion, containing, runtime, judges=None):
    require(runtime is not None, 'actual V2 scoring runtime required')
    rule = harness.rubric(criterion)
    require(isinstance(rule, dict) and set(rule) == {'workflow', 'entry', 'criteria', 'reference'}, 'invalid V2 rubric')
    require(len(names(rule['criteria'], 'rubric criteria')) == 4, 'V2 needs four rubric components')
    require(rule['reference'] in (None, 'upstream'), 'unsupported disclosed reference')
    workflow = Path(runtime) / 'experiments/compare' / rule['workflow']
    require(Path(rule['workflow']).name == rule['workflow'], 'invalid rubric workflow path')
    if 'workflow_sha256' in criterion:
        require(digest(workflow) == criterion['workflow_sha256'], 'origin rubric workflow differs')
    else:
        expected = criterion['measurement']['evaluator']['score_workflow']
        reference(expected, containing)
        require(digest(workflow) == expected['sha256'], 'runtime rubric workflow differs')
    declared = names(criterion['judges'], 'judges')
    require(set(criterion['judge_bindings']) == declared, 'judge binding identities differ')
    expected = {name: binding_path(info, containing, runtime) for name, info in criterion['judge_bindings'].items()}
    for name, path in expected.items():
        provider = 'codex_unrestricted_workspace' if name == 'gpt-5.6-terra' else 'claude_unrestricted_workspace'
        require(read(path) == {'providers.judge': provider}, 'judge model/provider policy differs')
    selected = {}
    for spec in judges if judges is not None else [f'{name}={path}' for name, path in expected.items()]:
        name, separator, raw = spec.partition('=')
        require(separator and name not in selected, 'V2 needs explicit unique MODEL=PATH bindings')
        selected[name] = Path(raw)
    require(set(selected) == declared, 'actual judges differ from frozen V2 judges')
    for name, path in selected.items():
        require(digest(path) == digest(expected[name]), 'actual judge provider binding differs')
    return workflow


def measurement(study, containing, tasks, packages):
    roles = control_roles(study)
    block = study['measurement']
    require(set(block) == {'evaluator', 'tasks'} and set(block['tasks']) == set(tasks),
            'V2 measurement tasks differ from all study packages')
    require(set(study['anchors']) == set(tasks) and set(study['base_commits']) == set(tasks),
            'V2 anchors/base commits omit study packages')
    evaluator = block['evaluator']
    require(set(evaluator) == {'score_workflow', 'judges'} and set(evaluator['judges']) == set(study['judges']),
            'V2 evaluator judges differ')
    reference(evaluator['score_workflow'], containing)
    for name, info in evaluator['judges'].items():
        reference(info['providers'], containing)
        binding = study['judge_bindings'][name]
        require(info['effort'] == binding['effort'] and info['providers']['sha256'] == binding['providers_sha256'],
                'V2 measurement binding differs')
    for name, path in tasks.items():
        require(study['base_commits'][name] == (path / 'base_commit').read_text().strip(), 'study base differs')
        info = block['tasks'][name]
        require(info['package_sha256'] == packages[name] and set(info['controls']) == roles,
                'V2 measurement package or roles differ')
        require(study['anchors'][name] == {role: c['label'] for role, c in info['controls'].items()},
                'V2 anchor labels differ from measurement')
        names(list(study['anchors'][name].values()), 'control labels')
        for control in info['controls'].values():
            source = reference(control['source'], containing)
            anchor = path / 'anchors' / f"{control['label']}.diff"
            require(digest(anchor) == digest(source), 'V2 control differs from task anchor')
            require(hashlib.sha256(harness.strip(source.read_bytes())[0]).hexdigest() ==
                    control['pooled_patch_sha256'], 'V2 pooled control digest differs')


def origin_identity(origin, origin_path, study, containing, task, packages):
    require(origin['purpose'] == 'calibration', 'V2 evidence needs calibration origin')
    require(harness.rubric(origin) == harness.rubric(study), 'accepted rubric differs from study')
    require(origin['judges'] == study['judges'], 'origin judges differ from accepted study judges')
    means_rule = harness.control_means(study)
    require(harness.control_means(origin) == means_rule, 'origin calibration rule differs')
    if means_rule:
        require(origin['calibration'] == study['calibration'], 'origin calibration rules differ')
    else:
        for key in ('margin', 'mutant_margin', 'error_rate'):
            require(origin['calibration'][key] == study['calibration'][key], 'origin calibration rules differ')
    require(origin['price_table'] == study['price_table'], 'origin frozen price table differs')
    if not means_rule:
        require(origin['anchor_spread_limit'] == study['anchor_spread_limit'], 'origin spread rule differs')
    require(origin['anchors'][task] == study['anchors'][task], 'origin anchor roles differ')
    runtime = Path(origin['runtime']['path'])
    require(runtime_commit(runtime) == origin['runtime']['commit'], 'origin runtime commit differs')
    workflow = dispatch(origin, origin_path, runtime)
    require(digest(workflow) == study['measurement']['evaluator']['score_workflow']['sha256'],
            'origin workflow differs from study measurement')
    for name in study['judges']:
        require(origin['judge_bindings'][name]['providers_sha256'] ==
                study['judge_bindings'][name]['providers_sha256'] and
                origin['judge_bindings'][name]['effort'] == study['judge_bindings'][name]['effort'] and
                origin['judge_bindings'][name]['timeout_sec'] == study['judge_bindings'][name]['timeout_sec'],
                'origin judge binding differs')
    declared = {Path(raw).name for raw in origin['tasks']}
    require(task in declared, 'pool task absent from origin criterion')
    # Frozen measurement criteria identify packages by their declared runtime task roots.
    for raw in origin['tasks']:
        if Path(raw).name == task:
            from experiments.orc_structural_search.qualification_io import package_digest
            require(package_digest(runtime / raw) == packages[task], 'origin task package differs')


def clone_ratings(pool, mapping, results, containing, controls, criteria, judges):
    clones = mapping['clones']
    require(isinstance(clones, dict) and clones and set(clones) == set(results['clones']) == set(pool['patches']),
            'V2 clone/patch identities differ')
    totals, roles = {name: {} for name in judges}, {}
    for cid, clone in clones.items():
        rated = results['clones'][cid]
        require(all(clone.get(key) == rated.get(key) for key in ('arm', 'run', 'labels')), 'V2 clone lineage differs')
        reference(pool['patches'][cid], containing)
        if clone['arm'] == 'reference':
            require(not rated['ratings'] and clone['run'] is None and clone['labels'] == ['reference'],
                    'invalid or rated disclosed reference')
            require(pool['patches'][cid]['sha256'] == controls['upstream']['pooled_patch_sha256'],
                    'disclosed reference differs from verified upstream')
            continue
        require(clone['arm'] in ('anchor', 'filler') and clone['run'] is None, 'unexpected calibration clone')
        rating_totals(rated['ratings'], criteria, judges, totals, cid)
        if clone['arm'] == 'anchor':
            roles[cid] = anchor_role(clone, pool['patches'][cid], controls)
    return totals, roles


def rating_totals(ratings, criteria, judges, totals, cid):
    require(set(ratings) == set(judges), 'missing declared rating judge')
    for judge in judges:
        values = [ratings[judge][key] for key in criteria]
        require(all(type(value) is int and 0 <= value <= 2 for value in values), 'invalid raw rubric components')
        totals[judge][cid] = sum(values)


def anchor_role(clone, patch, controls):
    require(isinstance(clone['labels'], list) and len(clone['labels']) == 1, 'invalid anchor label')
    role = next((role for role, c in controls.items() if [c['label']] == clone['labels']), None)
    require(role is not None and patch['sha256'] == controls[role]['pooled_patch_sha256'], 'V2 control patch differs')
    return role


def check_batches(mapping, roles, origin, stage, pool_root):
    batches = mapping['batches']
    key = 'A2' if stage == 'A_prime' else stage
    require(isinstance(batches, list) and len(batches) == origin['batches'][key]['count'],
            'missing declared calibration batch')
    seen = blind_members(mapping, roles, control_roles(origin))
    refs = {cid for cid, clone in mapping['clones'].items() if clone['arm'] == 'reference'}
    if harness.rubric(mapping)['reference']:
        summarize.reference_paths(pool_root, mapping)
        require(set(mapping['references']) == refs, 'unaccounted disclosed reference')
    else:
        require(not refs and not mapping.get('references'), 'reference-free rubric refuses reference')
    require(seen | refs == set(mapping['clones']) and not seen & refs, 'unbatched clones or blind reference')


def blind_members(mapping, roles, expected_roles=ROLES):
    seen = set()
    for batch in mapping['batches']:
        require(isinstance(batch, list) and batch and len(set(batch)) == len(batch), 'duplicate batch clone')
        require(not seen.intersection(batch) and set(batch) <= set(mapping['clones']), 'invalid batch membership')
        seen.update(batch)
        require(sorted(roles[cid] for cid in batch if cid in roles) == sorted(expected_roles),
                'each batch needs all declared controls exactly once')
    return seen


def pool_observation(pool, containing, study, study_path, tasks, packages):
    origin_path = reference(pool['criterion'], containing)
    origin = read(origin_path)
    task = pool['task_id']
    require(task in tasks, 'unknown calibration task')
    origin_identity(origin, origin_path, study, study_path, task, packages)
    mapping_path = reference(pool['mapping'], containing)
    require(mapping_path.name == 'mapping.json' and mapping_path.parent.name == 'records', 'invalid V2 pool path')
    mapping, results = read(mapping_path), read(reference(pool['results'], containing))
    require(mapping['criterion_sha256'] == results['criterion_sha256'] == pool['criterion']['sha256'],
            'origin criterion differs from mapping/results')
    origin_tasks = {Path(raw).name: Path(origin['runtime']['path']) / raw for raw in origin['tasks']}
    require(Path(mapping['task']).resolve() == origin_tasks[task].resolve(), 'pool task differs from origin')
    require(mapping['runtime_commit'] == origin['runtime']['commit'], 'pool origin runtime differs')
    require(Path(mapping['runtime']).resolve() == Path(origin['runtime']['path']).resolve(), 'pool runtime path differs')
    require(harness.rubric(mapping) == harness.rubric(study), 'pool rubric differs')
    from experiments.orc_structural_search.qualification import pool_context
    context = pool_context(mapping_path.parent.parent)
    dispatch(origin, origin_path, context['runtime'], context['judges'])
    judges = origin['judges']
    require(set(results['judges']) == set(judges) and len(results['judges']) == len(judges) and
            not results['excluded_judges'], 'missing or excluded calibration judge')
    controls = study['measurement']['tasks'][task]['controls']
    totals, roles = clone_ratings(pool, mapping, results, containing, controls, harness.rubric(study)['criteria'], judges)
    check_batches(mapping, roles, origin, pool['stage'], mapping_path.parent.parent)
    require(not mapping['runs'], 'calibration has candidate runs')
    anchors = summarize.anchor_scores(mapping, totals)
    recomputed = {'judges': list(judges), 'excluded_judges': {}, 'anchors': anchors}
    verdict = summarize.calibration(recomputed, mapping, {**study, 'purpose': 'calibration'})
    require(verdict['passed'], 'V2 control calibration failed (legacy P1/P2/P3 and spread when selected)')
    return task, verdict, anchors


def validate_v2(measure, containing, study, study_path, tasks, packages, runtime, judges):
    measurement(study, study_path, tasks, packages)
    dispatch(study, study_path, runtime, judges)
    same_reference(measure['criterion'], containing, study['accepted_measure']['criterion'], study_path)
    adaptive = {Path(path).name for path in study['tasks']}
    expected = {task: {study['accepted_measure']['step'], 'B2'} if task in adaptive else
                {'Q1' if task == Path(study['sealed_task']).name else 'Q2'} for task in tasks}
    seen, figures, anchors = set(), {task: [] for task in tasks}, {task: [] for task in tasks}
    stages = {task: set() for task in tasks}
    for pool in measure['pools']:
        key = (pool['task_id'], pool['stage'])
        require(key[0] in expected and key[1] in expected[key[0]], 'unexpected calibration task/stage')
        require(key not in seen, 'duplicate calibration task/stage')
        seen.add(key)
        if key[1] in ('A', 'A_prime'):
            same_reference(pool['criterion'], containing, measure['criterion'], containing)
        task, verdict, rows = pool_observation(pool, containing, study, study_path, tasks, packages)
        stages[task].add(key[1])
        figures[task].extend(verdict['pairs'])
        anchors[task].extend(rows)
    require(stages == expected, 'missing required baseline/B2/Q1/Q2 calibration pool')
    result = {}
    for task, rows in figures.items():
        spread = summarize.anchor_spreads(anchors[task], study['judges'], study['anchors'][task].values())
        if not harness.control_means(study):
            require(summarize.spread_passes(spread, study['anchor_spread_limit']), 'aggregate anchor spread exceeded')
        result[task] = {'pairs': len(rows), 'failing_pairs': 0, 'error_rate': 0, 'anchor_spread': spread}
    return result
