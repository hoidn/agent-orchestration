"""Frozen R55 run membership, including the one declared cross-root continuation."""

import re
from pathlib import Path

from experiments.orc_structural_search.qualification_io import read, reference, require

CONTINUATION = 'c6cfb85a9b21268fcffb32209fa45974ca139743c3cc1cdb0444d04e7c37efc9'


def ordered(originals):
    require(len({path.parent for path in originals}) == 1, 'ambiguous original run roots')
    numbers = [int(path.name.removeprefix('run-')) for path in originals]
    require(numbers == list(range(numbers[0], numbers[0] + len(numbers))),
            'original sample order or ambiguous replacement history')


def source_runs(document):
    rows = document['single_calls']
    require(isinstance(rows, list) and len(rows) in (2, 3), 'ambiguous source run membership')
    runs = [row['run'] for row in rows]
    require(all(isinstance(run, str) and re.fullmatch(r'direct_task/run-[1-9][0-9]*', run) for run in runs),
            'unsupported source run identity')
    require(len(set(runs)) == len(runs), 'duplicate source run identity')
    return runs


def validate_membership(evidence, containing, task, package, originals):
    sources = evidence['sources']
    require(isinstance(sources, list) and sources, 'missing family provenance sources')
    documents = []
    for source in sources:
        document = read(reference(source, containing))
        require(isinstance(document, dict), 'unsupported family source format')
        documents.append((source, document))
    matching = [(source, doc) for source, doc in documents if doc.get('slug') == task.name]
    require(len(matching) == 1, 'expected one unambiguous rung membership source')
    source, document = matching[0]
    require(document['package_sha256'] == package, 'source task package mismatch')
    declared = source_runs(document)
    actual = [path.parent.name + '/' + path.name for path in originals]
    ordered(originals[:2])
    if actual == declared:
        ordered(originals)
        return
    continuations = [doc for ref, doc in documents if ref['sha256'] == CONTINUATION]
    require(len(originals) == 3 and len(continuations) == 1 and declared == actual[:2],
            'samples differ from complete source run membership')
    continuation(evidence['samples'], containing, source, continuations[0], task, package, originals[-1])


def continuation(samples, containing, source, rule, task, package, third):
    new, reused = rule['new_sample'], rule['reused_samples']['rung_1']
    require(new['slug'] == task.name and new['sample'] == 3 and new['package_sha256'].split()[0] == package,
            'continuation task/package mismatch')
    require(source['sha256'] == reused['summary']['sha256'], 'continuation reused source mismatch')
    prefix = reused['samples']
    require(len(prefix) == 2, 'unsupported continuation prefix')
    for sample, frozen in zip(samples[:2], prefix):
        hashes = (sample['direct_record']['sha256'], sample['patch']['sha256'], sample['review_record']['sha256'])
        expected = (frozen['record_sha256'], frozen['final_diff_sha256'], frozen['review_record_sha256'])
        require(hashes == expected, 'continuation reused raw evidence mismatch')
    records = Path(rule['work_root']) / 'records'
    require(third == records / 'direct_task/run-1', 'ambiguous continuation replacement identity')
    review = samples[-1]['review_record']
    if review is not None:
        recorded = read(reference(review, containing))
        require(Path(recorded['records']) == records / 'review_once/run-1', 'continuation review identity mismatch')
