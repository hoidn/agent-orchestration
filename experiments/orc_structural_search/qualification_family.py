"""Recompute the frozen R55 or narrow oracle family qualification from raw evidence."""

import re
from pathlib import Path
from statistics import mean

from experiments.compare import pool, prepare
from experiments.orc_structural_search.qualification_io import (
    hash_value, names, read, reference, require)

R55 = '9faa4c01d0e3f231278f85d809a3e0d3bb3f64813cd59afba690089afd355f46'


def completed(ref, containing, arm):
    path = reference(ref, containing)
    record = read(path)
    require(record.get('arm') == arm and record.get('outcome') == 'completed', f'incomplete {arm} sample')
    require(type(record.get('calls')) is int and record['calls'] == 1, f'{arm} must record one call')
    scan = record['scan']
    require(isinstance(scan.get('hits'), list) and type(scan.get('calls')) is int, 'malformed scan')
    require(pool.exclusion(scan, record['calls'], str(path)) is None, 'excluded difficulty sample')
    original = Path(record['records'])
    require(original.is_absolute() and re.fullmatch(r'run-[1-9][0-9]*', original.name), 'invalid original run identity')
    require(original.parent.name == arm, 'original run arm mismatch')
    if (original / 'calls').exists():
        require(len(list((original / 'calls').iterdir())) == record['calls'], 'scan does not cover original calls')
    return record, original


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


def review_sample(sample, containing, task, index, identities):
    direct, original = completed(sample['direct_record'], containing, 'direct_task')
    require(original.name == f'run-{index}' and str(original) not in identities, 'sample order or duplicate run identity')
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
        return 1, (direct['task'], direct['base'], direct['compare_base'])
    review, review_original = completed(sample['review_record'], containing, 'review_once')
    require(str(review_original) not in identities,
            'review order or duplicate run identity')
    identities.add(str(review_original))
    require((review['task'], review['base'], review['compare_base']) ==
            (direct['task'], direct['base'], direct['compare_base']), 'review task/base mismatch')
    applied = review['applied']
    require(applied['sha256'] == sample['patch']['sha256'] and
            Path(applied['path']) == original / final, 'review is not paired with original final diff')
    return review_blockers(review), (direct['task'], direct['base'], direct['compare_base'])


def r55_task(evidence, containing, task, package):
    require(evidence['package_sha256'] == package, 'family package hash mismatch')
    sources = evidence['sources']
    require(isinstance(sources, list) and sources, 'missing family provenance sources')
    for source in sources:
        reference(source, containing)
    samples = evidence['samples']
    require(isinstance(samples, list) and len(samples) in (2, 3), 'R55 needs exactly two or three samples')
    identities = set()
    values = [review_sample(sample, containing, task, i, identities) for i, sample in enumerate(samples, 1)]
    require(len({context for _, context in values}) == 1, 'difficulty samples disagree on task/base')
    base = (task / 'base_commit').read_text().strip()
    require(values[0][1][1].startswith(base), 'difficulty sample base is not task base')
    blockers = [value for value, _ in values]
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
    controls = frozen['controls']
    require(isinstance(controls, list) and len(controls) == 3, 'oracle rule needs exactly three controls')
    ids = names([c['id'] for c in controls], 'oracle controls')
    hashes = [hash_value(c['submission_sha256']) for c in controls]
    require(len(set(hashes)) == 3, 'oracle submissions must be distinct')
    accepted = [c for c in controls if c['expected'] == 'accept']
    rejected = [c for c in controls if c['expected'] == 'reject']
    require(len(accepted) == 2 and len(rejected) == 1, 'oracle controls need two accept and one reject')
    classes = [c.get('structure_class') for c in accepted]
    require(all(isinstance(c, str) and c for c in classes) and len(set(classes)) == 2,
            'correct controls require distinct frozen structure classes')
    return {c['id']: c for c in controls}, checks, rule['oracle']['sha256']


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
