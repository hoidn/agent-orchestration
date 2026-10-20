"""Recompute the frozen R55 or narrow oracle family qualification from raw evidence."""

import re
import shlex
from pathlib import Path
from statistics import mean

from experiments.compare import pool, prepare
from experiments.orc_structural_search.qualification_lineage import validate_membership
from experiments.orc_structural_search.qualification_io import (
    digest, hash_value, names, read, reference, require)

R55 = '9faa4c01d0e3f231278f85d809a3e0d3bb3f64813cd59afba690089afd355f46'


def completed(ref, containing, arm):
    path = reference(ref, containing)
    record = read(path)
    require(record.get('arm') == arm and record.get('outcome') == 'completed', f'incomplete {arm} sample')
    require(type(record.get('calls')) is int and record['calls'] == 1, f'{arm} must record one call')
    scan = record['scan']
    require(isinstance(scan.get('hits'), list) and type(scan.get('calls')) is int, 'malformed scan')
    validate_scan(scan)
    require(pool.exclusion(scan, record['calls'], str(path)) is None, 'excluded difficulty sample')
    original = Path(record['records'])
    require(original.is_absolute() and re.fullmatch(r'run-[1-9][0-9]*', original.name), 'invalid original run identity')
    require(original.parent.name == arm, 'original run arm mismatch')
    if (original / 'calls').exists():
        require(len(list((original / 'calls').iterdir())) == record['calls'], 'scan does not cover original calls')
    return record, original


def validate_scan(scan):
    verdict = scan.get('verdict')
    require(all(isinstance(hit, dict) and isinstance(hit.get('pattern'), str) for hit in scan['hits']),
            'malformed scan hits')
    if verdict is not None:
        require(isinstance(verdict, dict) and verdict.get('verdict') in ('cleared', 'contaminated') and
                isinstance(verdict.get('reason'), str) and bool(verdict['reason']), 'malformed scan verdict')


def review_blockers(record):
    review = record['review']
    require(isinstance(review, dict), 'missing recorded review value')
    variant = review.get('variant')
    require(variant in ('REQUEST_CHANGES', 'WRONG_APPROACH', 'APPROVE', 'NEEDS_HUMAN'), 'unknown review variant')
    if variant == 'REQUEST_CHANGES':
        findings = review.get('findings')
        require(isinstance(findings, list) and all(isinstance(x, str) for x in findings), 'invalid review findings')
    elif 'findings' in review:
        require(isinstance(review['findings'], list) and all(isinstance(x, str) for x in review['findings']),
                'invalid review findings')
    return prepare.blockers(review)


def review_sample(sample, containing, task, identities):
    direct, original = completed(sample['direct_record'], containing, 'direct_task')
    require(str(original) not in identities, 'duplicate run identity')
    identities.add(str(original))
    require(Path(direct['task']).name == task.name, 'difficulty sample task mismatch')
    inputs = read(reference(sample['direct_inputs'], containing))
    require((inputs.get('model'), inputs.get('effort')) == ('gpt-6.1-sol', 'high'), 'wrong frozen control inputs')
    require(inputs.get('task') == (task / 'task.txt').read_text(), 'control task input mismatch')
    patch = reference(sample['patch'], containing)
    final = direct['patches']['final']
    require(isinstance(final, str) and not Path(final).is_absolute() and '..' not in Path(final).parts,
            'invalid final patch path')
    if not patch.stat().st_size:
        require(sample.get('review_record') is None, 'empty diff must not have a review')
        return 1, (Path(direct['task']).name, direct['base'], direct['compare_base']), original
    review, review_original = completed(sample['review_record'], containing, 'review_once')
    require(str(review_original) not in identities,
            'review order or duplicate run identity')
    identities.add(str(review_original))
    require((review['task'], review['base'], review['compare_base']) ==
            (direct['task'], direct['base'], direct['compare_base']), 'review task/base mismatch')
    applied = review['applied']
    require(applied['sha256'] == sample['patch']['sha256'] and
            Path(applied['path']) == original / final, 'review is not paired with original final diff')
    return review_blockers(review), (Path(direct['task']).name, direct['base'], direct['compare_base']), original


def r55_task(evidence, containing, task, package):
    require(evidence['package_sha256'] == package, 'family package hash mismatch')
    samples = evidence['samples']
    require(isinstance(samples, list) and len(samples) in (2, 3), 'R55 needs exactly two or three samples')
    identities = set()
    values = [review_sample(sample, containing, task, identities) for sample in samples]
    validate_membership(evidence, containing, task, package, [original for _, _, original in values])
    require(len({context for _, context, _ in values}) == 1, 'difficulty samples disagree on task/base')
    base = (task / 'base_commit').read_text().strip()
    require(values[0][1][1].startswith(base), 'difficulty sample base is not task base')
    blockers = [value for value, _, _ in values]
    initial = mean(blockers[:2])
    require(initial >= 1, 'family difficulty below threshold')
    expected = 3 if initial < 1.5 else 2
    require(len(blockers) == expected, 'R55 borderline requires exactly third sample; extra samples are selective')
    require(mean(blockers) >= 1, 'family difficulty below threshold')
    return {'blockers': blockers, 'mean_blockers': mean(blockers)}


def oracle_rule(rule, containing, task, package):
    oracle = reference(rule['oracle'], containing)
    checks = names(rule['checks'], 'oracle checks')
    frozen = rule['tasks'][task.name]
    require(frozen['package_sha256'] == package, 'oracle rule task package mismatch')
    controls = oracle_controls(frozen['controls'])
    return controls, checks, rule['oracle']['sha256']


def oracle_controls(controls):
    require(isinstance(controls, list) and len(controls) == 3, 'oracle rule needs exactly three controls')
    names([c['id'] for c in controls], 'oracle controls')
    hashes = [hash_value(c['submission_sha256']) for c in controls]
    require(len(set(hashes)) == 3, 'oracle submissions must be distinct')
    accepted = [c for c in controls if c['expected'] == 'accept']
    rejected = [c for c in controls if c['expected'] == 'reject']
    require(len(accepted) == 2 and len(rejected) == 1, 'oracle controls need two accept and one reject')
    validate_structure_classes(accepted)
    return {c['id']: c for c in controls}


def validate_structure_classes(accepted):
    classes = [c.get('structure_class') for c in accepted]
    require(all(isinstance(c, str) and c for c in classes) and len(set(classes)) == 2,
            'correct controls require distinct frozen structure classes')


def oracle_task(evidence, rule, containing, rule_path, task, package):
    require(evidence['package_sha256'] == package, 'oracle family package mismatch')
    frozen, checks, oracle_hash = oracle_rule(rule, rule_path, task, package)
    controls = evidence['controls']
    require(isinstance(controls, list) and names([c['id'] for c in controls], 'oracle controls') == set(frozen),
            'oracle controls differ from frozen rule')
    for control in controls:
        expected = frozen[control['id']]
        reference(control['submission'], containing)
        result = read(reference(control['result'], containing))
        require(control['submission']['sha256'] == expected['submission_sha256'], 'oracle submission mismatch')
        identity = (result['task_id'], result['package_sha256'], result['oracle_sha256'], result['submission_sha256'])
        require(identity == (task.name, package, oracle_hash, expected['submission_sha256']), 'oracle result identity mismatch')
        observed = result['checks']
        require(isinstance(observed, dict) and set(observed) == checks and
                all(type(value) is bool for value in observed.values()), 'invalid oracle check results')
        passed = all(observed.values())
        require(passed == (expected['expected'] == 'accept'), 'oracle control result fails frozen expectation')
    return {'controls': 3, 'accepted': 2, 'rejected': 1}


def validate_family(family, containing, tasks, packages):
    rule_path = reference(family['rule'], containing)
    rule = read(rule_path)
    require(isinstance(family['tasks'], dict) and set(tasks) <= set(family['tasks']), 'family omits study tasks')
    if family['kind'] == 'review-blockers-r55':
        require(family['rule']['sha256'] == R55, 'unsupported frozen R55 rule')
        return {name: r55_task(family['tasks'][name], containing, task, packages[name]) for name, task in tasks.items()}
    require(family['kind'] == 'oracle-controls-v1', 'unsupported family kind')
    return {name: oracle_task(family['tasks'][name], rule, containing, rule_path, task, packages[name])
            for name, task in tasks.items()}


def validate_family_v2(family, containing, tasks, packages, study, study_path):
    """Each package keeps the exact amendment and original runtime of its samples."""
    require(family['kind'] == 'review-blockers-r55', 'unsupported V2 family kind')
    require(set(family['tasks']) == set(tasks) and set(family['rules']) == set(packages.values()),
            'V2 family omits or duplicates study packages/rules')
    result = {}
    adaptive = {Path(path).name for path in study['tasks']}
    for name, task in tasks.items():
        rule_ref = family['rules'][packages[name]]
        amendment = 'amends_5' if name in adaptive else 'amends_6'
        require(rule_ref == study['family_amendments'][amendment], 'family rule differs from study amendment')
        rule_path = reference(rule_ref, containing)
        rule = read(rule_path)
        validate_amendment(rule, amendment, name, packages[name])
        result[name] = amended_task(family['tasks'][name], containing, task, packages[name], rule)
    return result


def validate_amendment(rule, amendment, task, package):
    require(rule['purpose'] == 'family-calibration' and rule['written_before_scoring'] is True,
            'family rule must be frozen before scoring')
    require(rule['k'] == 2 and rule[amendment]['reviewer'] == 'gpt-5.6-terra', 'unsupported family rule')
    require(rule[amendment]['packages'][task] == package and
            rule['packages'][task]['package_sha256'] == package, 'amendment package mismatch')
    require(rule['runtime']['commit'] == rule[amendment]['implementation_commit'], 'amendment runtime differs')
    require(rule['runtime']['validity'] == 'exact implementation commit and package hashes',
            'unsupported amendment runtime validity')
    require(rule['single_call']['model'] == 'gpt-5.6-terra' and rule['single_call']['effort'] == 'high',
            'unsupported amended single call')
    from experiments.compare.repos import runtime_commit
    require(runtime_commit(Path(rule['runtime']['path'])) == rule['runtime']['commit'], 'family origin runtime changed')
    require(digest(Path(rule['runtime']['path']) / 'experiments/compare/control/review_once.orc') ==
            rule['review']['workflow_sha256'], 'frozen reviewer workflow differs')
    require(rule['review']['reviewer'].startswith('gpt-5.6-terra, high,'), 'unsupported amended reviewer')


def amended_sample(sample, containing, task, rule, identities):
    direct, original = completed(sample['direct_record'], containing, 'direct_task')
    require(str(original) not in identities, 'duplicate original sample')
    identities.add(str(original))
    origin_task = Path(rule['runtime']['path']) / rule['packages'][task.name]['path']
    from experiments.orc_structural_search.qualification_io import package_digest
    require(Path(direct['task']).resolve() == origin_task.resolve() and
            package_digest(origin_task) == rule['packages'][task.name]['package_sha256'], 'family origin task differs')
    require(direct['runtime_commit'] == rule['runtime']['commit'], 'family origin runtime differs')
    original_dispatch(direct, original, sample['direct_inputs'], containing, rule)
    inputs = read(reference(sample['direct_inputs'], containing))
    require((inputs['model'], inputs['effort']) == (rule['single_call']['model'], rule['single_call']['effort']),
            'amended direct model/effort differs')
    require(inputs['task'] == (task / 'task.txt').read_text(), 'family direct task input differs')
    final = Path(direct['patches']['final'])
    require(not final.is_absolute() and '..' not in final.parts, 'invalid original patch path')
    patch = reference(sample['patch'], containing)
    require((original / final).is_file() and hash_value(sample['patch']['sha256']) ==
            digest(original / final), 'original final patch differs')
    if not patch.stat().st_size:
        require(sample.get('review_record') is None and sample.get('review_inputs') is None,
                'empty patch cannot have review')
        return 1, (direct['base'], direct['compare_base']), original, None
    review, review_original = completed(sample['review_record'], containing, 'review_once')
    require(str(review_original) not in identities, 'duplicate original review')
    identities.add(str(review_original))
    require(review['runtime_commit'] == rule['runtime']['commit'], 'review origin runtime differs')
    require((review['task'], review['base'], review['compare_base']) ==
            (direct['task'], direct['base'], direct['compare_base']), 'review context differs')
    require(Path(review['applied']['path']) == original / final and
            review['applied']['sha256'] == sample['patch']['sha256'], 'review is not paired with original patch')
    original_dispatch(review, review_original, sample['review_inputs'], containing, rule)
    reviewer = read(reference(sample['review_inputs'], containing))
    require(reviewer['account'] == prepare.REVIEW_ONCE_ACCOUNT and reviewer['replies'] == prepare.REVIEW_ONCE_REPLIES,
            'review inputs differ from frozen account/replies')
    require(reviewer['repo'] == review['cwd'], 'review is aimed at another candidate repository')
    require(reviewer['intent'] == (task / 'intent.txt').read_text(), 'review intent differs')
    return review_blockers(review), (direct['base'], direct['compare_base']), original, review_original


def amended_task(evidence, containing, task, package, rule):
    require(evidence['package_sha256'] == package, 'family package differs')
    samples = evidence['samples']
    require(isinstance(samples, list) and len(samples) in (2, 3), 'amended family needs two or three samples')
    identities = set()
    values = [amended_sample(sample, containing, task, rule, identities) for sample in samples]
    originals = [row[2] for row in values]
    attempts = replacement_attempts(evidence, containing, task, rule, identities)
    amended_membership(evidence, containing, task, package, originals, attempts)
    require(len({row[1] for row in values}) == 1, 'family bases differ')
    require(values[0][1][0] == (task / 'base_commit').read_text().strip(), 'family base differs from task')
    require(len({sample['patch']['sha256'] for sample in samples}) == len(samples), 'duplicate family patches')
    original_membership(originals, [row[3] for row in values if row[3] is not None], attempts, task)
    blockers = [row[0] for row in values]
    initial = mean(blockers[:2])
    require(initial >= 1, 'family difficulty below threshold')
    require(len(samples) == (3 if initial < 1.5 else 2), 'borderline needs exactly third pair')
    require(mean(blockers) >= 1, 'family difficulty below threshold')
    return {'blockers': blockers, 'mean_blockers': mean(blockers), 'runtime_commit': rule['runtime']['commit']}


def original_membership(directs, reviews, attempts, task):
    """All launches of this package must appear, including excluded replacements."""
    for arm, selected in (('direct_task', directs), ('review_once', reviews)):
        paths = [*selected, *(path for path, record in attempts if record['arm'] == arm)]
        if not paths:
            continue
        require(len({path.parent for path in paths}) == 1, 'ambiguous original run roots')
        launched = set()
        for path in paths[0].parent.glob('run-*'):
            record = read(path / 'record.json')
            if Path(record['task']).name == task.name:
                launched.add(path)
        require(launched == set(paths), 'original launched runs omitted or ambiguous replacement history')


def amended_membership(evidence, containing, task, package, originals, attempts):
    documents = [read(reference(source, containing)) for source in evidence['sources']]
    matching = [doc for doc in documents if doc.get('slug') == task.name]
    require(len(matching) == 1 and matching[0]['package_sha256'] == package, 'ambiguous family membership source')
    rows = matching[0]['single_calls']
    require(isinstance(rows, list) and rows, 'missing launched source runs')
    declared = [row['run'] for row in rows]
    paths = [*originals, *(path for path, record in attempts if record['arm'] == 'direct_task')]
    paths.sort(key=lambda p: int(p.name.removeprefix('run-')))
    require(len(set(declared)) == len(declared) and declared == ['direct_task/' + path.name for path in paths],
            'samples/attempts differ from complete source membership')
    require(originals == sorted(originals, key=lambda p: int(p.name.removeprefix('run-'))),
            'family samples out of launch order')


def replacement_attempts(evidence, containing, task, rule, identities):
    attempts, contaminated, failed_reviews = [], 0, 0
    selected = {sample[key]['sha256'] for sample in evidence['samples'] for key in ('direct_record', 'review_record')
                if sample.get(key) is not None}
    for attempt in evidence.get('attempts', []):
        path = reference(attempt['record'], containing)
        record = read(path)
        original = Path(record['records'])
        target = read(reference(attempt['replaced_by'], containing))
        require(attempt['replaced_by']['sha256'] in selected, 'replacement does not name selected original')
        require(str(original) not in identities, 'duplicate replacement original')
        identities.add(str(original))
        require(record['arm'] in ('direct_task', 'review_once') and record['arm'] == target['arm'], 'replacement arm differs')
        require((record['task'], record['base'], record['compare_base'], record['runtime_commit']) ==
                (target['task'], target['base'], target['compare_base'], rule['runtime']['commit']), 'replacement context differs')
        require(original.parent == Path(target['records']).parent and
                int(original.name.removeprefix('run-')) + 1 == int(Path(target['records']).name.removeprefix('run-')),
                'replacement is not next original run')
        require(read(original / 'record.json') == record, 'replacement original record differs')
        scan = record['scan']
        validate_scan(scan)
        require(type(record['calls']) is int and record['calls'] > 0, 'replacement needs metered calls')
        excluded = pool.exclusion(scan, record['calls'], str(path))
        if excluded is not None:
            contaminated += 1
        else:
            require(record['arm'] == 'review_once' and record['outcome'] == 'failed', 'failed direct sample cannot qualify')
            require(record['applied'] == target['applied'], 'review rerun must use same original patch')
            failed_reviews += 1
        attempts.append((original, record))
    require(contaminated <= 1 and failed_reviews <= 1, 'family replacement allowance exceeded')
    return attempts


def original_dispatch(record, original, inputs, containing, rule):
    runtime = Path(rule['runtime']['path'])
    require(Path(record['runtime']).resolve() == runtime.resolve(), 'family runtime path differs')
    source = runtime / 'experiments/compare/control' / f"{record['arm']}.orc"
    providers = source.with_suffix('.providers.json')
    expected = {'providers.reviewer': 'codex_unrestricted_workspace'} if record['arm'] == 'review_once' else {'providers.direct': 'codex'}
    require(read(providers) == expected, 'family provider binding differs')
    argv = shlex.split(record['command'])
    require(str(source) in argv and '--provider-externs-file' in argv and '--input-file' in argv,
            'original family dispatch missing workflow/provider/input provenance')
    require(argv[argv.index('--provider-externs-file') + 1] == str(providers) and
            argv[argv.index('--input-file') + 1] == str(original / 'inputs.json'), 'family dispatch differs')
    require(read(original / 'record.json') == record, 'original family record differs')
    reference(inputs, containing)
    require(digest(original / 'inputs.json') == inputs['sha256'], 'original family inputs differ')
