"""Qualification gates for structural operations; receipts authorize no calibration spend."""

import os
from pathlib import Path

from experiments.orc_structural_search.qualification_family import validate_family
from experiments.orc_structural_search.qualification_io import (
    calibration, digest, package_digest, read, reference, require)
from experiments.orc_structural_search.qualification_measure import dispatch, measurement, validate_measure

OPERATIONS = ('launch', 'quality', 'readout')


def task_paths(frozen, criterion, runtime, supplied):
    declared = frozen.get('tasks')
    require(isinstance(declared, list) and declared, 'criterion needs task paths')
    paths = {}
    for raw in declared:
        require(isinstance(raw, str) and raw, 'invalid criterion task path')
        path = Path(raw)
        if not path.is_absolute():
            path = (Path(runtime) / path) if runtime is not None else Path(criterion).parent / path
        require(path.name not in paths, 'duplicate criterion task identity')
        paths[path.name] = path
    if supplied:
        require(len({Path(p).name for p in supplied}) == len(supplied), 'duplicate operation tasks')
        require({Path(p).name for p in supplied} <= set(paths), 'operation task absent from criterion')
        for path in supplied:
            paths[Path(path).name] = Path(path)
    return paths


def validate(criterion: Path | None, *, tasks=(), config_sha256=None, runtime: Path | None = None,
             judges=None, operation='launch', measure_free=False) -> dict:
    """Re-read and recompute qualification per operation. Only readout permits an explicit projection override."""
    try:
        return _validate(criterion, tasks, config_sha256, runtime, judges, operation, measure_free)
    except (KeyError, TypeError, IndexError, OSError, SystemExit) as error:
        raise ValueError(f'qualification: malformed or missing evidence: {error}') from error


def _validate(criterion, tasks, config_sha256, runtime, judges, operation, measure_free):
    require(operation in OPERATIONS, 'unknown qualification operation')
    require(not measure_free or operation == 'readout', 'measure_free override is readout-only')
    require(criterion is not None, 'explicit criterion required; missing is a failed quality gate')
    criterion = Path(criterion).resolve()
    frozen, sha = read(criterion), digest(criterion)
    purpose = frozen.get('purpose', 'quality')
    require(purpose in ('quality', 'measure-free', 'calibration'), 'unknown criterion purpose')
    require(purpose != 'calibration', 'structural operations reject calibration purpose')
    if operation == 'launch':
        require(config_sha256 == sha, 'configuration criterion_sha256 differs from criterion')
    mode = 'measure-free' if measure_free or purpose == 'measure-free' else 'quality'
    result = {'mode': mode, 'purpose': purpose, 'criterion_sha256': sha, 'qualification_sha256': None,
              'family': None, 'measure': None}
    if mode == 'measure-free':
        require(operation != 'quality', 'measure-free mode rejects judging and quality pooling')
        return result
    paths = task_paths(frozen, criterion, runtime, tasks)
    packages = {name: package_digest(path) for name, path in paths.items()}
    calibration(frozen['calibration'])
    identity = measurement(frozen, criterion, paths, packages)
    dispatch(frozen, criterion, runtime, judges)
    receipt_path = reference(frozen['qualification'], criterion)
    receipt = read(receipt_path)
    require(receipt.get('schema') == 'orc-structural-qualification-v1', 'unknown qualification schema')
    result.update(qualification_sha256=frozen['qualification']['sha256'],
                  family=validate_family(receipt['family'], receipt_path, paths, packages),
                  measure=validate_measure(receipt['measure'], receipt_path, frozen, criterion, paths, packages, identity))
    return result


def pool_context(pool: Path) -> dict:
    """Actual scoring runtime, task and bindings; validate model inputs before dispatch or quality readout."""
    mapping = read(Path(pool) / 'records/mapping.json')
    require(isinstance(mapping.get('runtime'), str) and bool(mapping['runtime']), 'pool lacks scoring runtime')
    specs = []
    for name, info in mapping['judges'].items():
        bound = read(Path(pool) / 'records' / f'score-inputs-{name}.json')
        require(bound.get('judge_model') == name and bound.get('criterion_sha256') == mapping['criterion_sha256'],
                'actual judge model/criterion input differs from pool')
        require(isinstance(info.get('providers'), str) and info['providers'], 'pool lacks actual provider binding')
        specs.append(f"{name}={info['providers']}")
    return {'runtime': Path(mapping['runtime']), 'tasks': [Path(mapping['task'])], 'judges': specs}


def private_roots(criterion: Path | None, *, public_roots=(), workspace_roots=()) -> tuple[Path, ...]:
    """Minimal typed private evidence parents; public execution paths cannot require broad masking."""
    if criterion is None:
        return ()
    criterion = Path(criterion).resolve()
    frozen = read(criterion)
    if frozen.get('purpose', 'quality') == 'measure-free':
        return ()
    receipt_path = reference(frozen['qualification'], criterion)
    receipt = read(receipt_path)
    roots = {receipt_path.parent, *family_roots(receipt, receipt_path)}
    cal_path = reference(receipt['measure']['criterion'], receipt_path)
    roots.add(cal_path.parent)
    for pool in receipt['measure']['pools']:
        mapping = reference(pool['mapping'], receipt_path)
        require(mapping.name == 'mapping.json' and mapping.parent.name == 'records', 'invalid calibration pool path')
        roots.add(mapping.parent.parent)
        roots.add(reference(pool['results'], receipt_path).parent)
        roots.update(reference(ref, receipt_path).parent for ref in pool['patches'].values())
    protected = [Path(p).resolve() for p in (*public_roots, *workspace_roots)]
    for root in roots:
        require(all(not public.is_relative_to(root) for public in protected),
                f'private evidence layout would mask public execution path: {root}')
    return tuple(sorted(root for root in roots if not any(root != other and root.is_relative_to(other) for other in roots)))


def family_roots(receipt, receipt_path):
    roots = set()
    for evidence in receipt['family']['tasks'].values():
        for source in evidence.get('sources', []):
            roots.add(reference(source, receipt_path).parent)
        roots.update(sample_roots(evidence.get('samples', []), receipt_path))
        for control in evidence.get('controls', []):
            roots.update(reference(control[key], receipt_path).parent for key in ('submission', 'result'))
    return roots


def sample_roots(samples, receipt_path):
    roots = set()
    for sample in samples:
        for kind, ref in sample.items():
            if ref is None:
                continue
            path = reference(ref, receipt_path)
            roots.add(path.parent)
            if kind.endswith('_record'):
                original = Path(read(path)['records'])
                require(original.is_absolute(), 'original records path must be absolute')
                if original.exists():
                    roots.add(original.resolve())
    return roots


def hidden_env(env, roots):
    """Extend the shims' existing path mask; controller data stays out of agent inputs."""
    result = dict(env)
    current = [p for p in result.get('COMPARE_HIDE', '').split(os.pathsep) if p]
    if roots:
        result['COMPARE_HIDE'] = os.pathsep.join(dict.fromkeys([*current, *map(str, roots)]))
    return result
