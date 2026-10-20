"""Qualification gates for structural operations; receipts authorize no calibration spend."""

import math
import os
import shlex
from pathlib import Path

from experiments.orc_structural_search.qualification_family import validate_family, validate_family_v2
from experiments.orc_structural_search.qualification_io import (
    calibration, digest, names, package_digest, read, reference, require)
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
    receipt_path = reference(frozen['qualification'], criterion)
    receipt = read(receipt_path)
    schema = receipt.get('schema')
    require(schema in ('orc-structural-qualification-v1', 'orc-structural-qualification-v2'),
            'unknown qualification schema')
    if schema == 'orc-structural-qualification-v2':
        validate_campaign_criterion(frozen, criterion)
        expanded = {**frozen, 'tasks': [*frozen['tasks'], frozen['validation_task'], frozen['sealed_task']]}
        paths = task_paths(expanded, criterion, runtime, tasks)
        packages = {name: package_digest(path) for name, path in paths.items()}
        from experiments.orc_structural_search.qualification_measure_v2 import validate_v2
        family = validate_family_v2(receipt['family'], receipt_path, paths, packages, frozen, criterion)
        measure = validate_v2(receipt['measure'], receipt_path, frozen, criterion, paths, packages, runtime, judges)
    else:
        require('accepted_measure' not in frozen, 'C1 requires qualification V2')
        paths = task_paths(frozen, criterion, runtime, tasks)
        packages = {name: package_digest(path) for name, path in paths.items()}
        calibration(frozen['calibration'])
        identity = measurement(frozen, criterion, paths, packages)
        dispatch(frozen, criterion, runtime, judges)
        family = validate_family(receipt['family'], receipt_path, paths, packages)
        measure = validate_measure(receipt['measure'], receipt_path, frozen, criterion, paths, packages, identity)
    result.update(qualification_sha256=frozen['qualification']['sha256'], family=family, measure=measure)
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
    roots = {receipt_path.parent, *family_roots(receipt, receipt_path),
             *control_roots(frozen, criterion)}
    if receipt['family']['kind'] == 'oracle-controls-v1':
        rule_path = reference(receipt['family']['rule'], receipt_path)
        roots.update((rule_path.parent, reference(read(rule_path)['oracle'], rule_path).parent))
    cal_path = reference(receipt['measure']['criterion'], receipt_path)
    roots.add(cal_path.parent)
    if 'measurement' in read(cal_path):
        roots.update(control_roots(read(cal_path), cal_path))
    roots.update(pool_roots(receipt, receipt_path))
    protected = [Path(p).resolve() for p in (*public_roots, *workspace_roots)]
    evaluator = frozen['measurement']['evaluator']
    protected += [reference(evaluator['score_workflow'], criterion)]
    protected += [reference(info['providers'], criterion) for info in evaluator['judges'].values()]
    evidence_privacy(receipt, receipt_path, roots, protected)
    if 'accepted_measure' in frozen:
        roots.update(reference(ref, criterion).parent for ref in
                     (*frozen['family_amendments'].values(), frozen['accepted_measure']['criterion']))
    return allowed_roots(roots, protected)


def evidence_privacy(receipt, receipt_path, roots, protected):
    rules = receipt['family'].get('rules') or {'v1': receipt['family']['rule']}
    for rule in rules.values():
        path = reference(rule, receipt_path)
        if rule['sha256'] in PUBLIC_RULE_HASHES:
            protected.append(path)
        else:
            roots.add(path.parent)
    for pool in receipt['measure']['pools']:
        if 'criterion' in pool:
            path = reference(pool['criterion'], receipt_path)
            roots.add(path.parent)
            if 'measurement' in read(path):
                roots.update(control_roots(read(path), path))


def allowed_roots(roots, protected):
    for root in roots:
        require(all(not public.is_relative_to(root) for public in protected),
                f'private evidence layout would mask public execution path: {root}')
    return tuple(sorted(root for root in roots if not any(root != other and root.is_relative_to(other) for other in roots)))


def pool_roots(receipt, receipt_path):
    roots = set()
    for pool in receipt['measure']['pools']:
        mapping = reference(pool['mapping'], receipt_path)
        require(mapping.name == 'mapping.json' and mapping.parent.name == 'records', 'invalid calibration pool path')
        roots.add(mapping.parent.parent)
        roots.add(reference(pool['results'], receipt_path).parent)
        roots.update(reference(ref, receipt_path).parent for ref in pool['patches'].values())
    return roots


PUBLIC_RULE_HASHES = frozenset({
    '9faa4c01d0e3f231278f85d809a3e0d3bb3f64813cd59afba690089afd355f46',
    'c6cfb85a9b21268fcffb32209fa45974ca139743c3cc1cdb0444d04e7c37efc9',
})


def control_roots(frozen, containing):
    return {reference(control['source'], containing).parent
            for task in frozen['measurement']['tasks'].values() for control in task['controls'].values()}


def family_roots(receipt, receipt_path):
    roots = set()
    for evidence in receipt['family']['tasks'].values():
        for source in evidence.get('sources', []):
            path = reference(source, receipt_path)
            if source['sha256'] not in PUBLIC_RULE_HASHES:
                roots.add(path.parent)
        roots.update(sample_roots(evidence.get('samples', []), receipt_path))
        for attempt in evidence.get('attempts', []):
            path = reference(attempt['record'], receipt_path)
            roots.add(path.parent)
            roots.update(original_roots(read(path)))
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
                roots.update(original_roots(read(path)))
    return roots


def original_roots(record):
    roots = set()
    for field in ('records', 'tree', 'state_root'):
        if field not in record:
            continue
        require(isinstance(record[field], str) and bool(record[field]), 'malformed original evidence path')
        original = Path(record[field])
        require(original.is_absolute(), 'original evidence path must be absolute')
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


def scan_evidence(records, metadata):
    """Scan direct/resumed evaluation histories for private qualification paths."""
    from experiments.compare import scan
    from experiments.compare.repos import dump
    home = Path.home()
    patterns = {'qualification': '|'.join(scan.spelled(Path(p), home) + scan.BOUNDARY
                                         for p in metadata['qualification_private_roots'])}
    hits = scan.find_hits(Path(records), Path(metadata['tree']), metadata['created_at'], home, patterns)
    metadata['qualification_scan'] = {'hits': hits, 'calls': len(list((Path(records) / 'calls').glob('*')))}
    if hits:
        metadata.pop('scan', None)
    dump(Path(records) / 'record.json', metadata)
    return hits



FIELDS = frozenset('''purpose experiment plan tasks validation_task sealed_task base_commits judges
judge_bindings rubric accepted_measure anchors calibration anchor_spread_limit qualification
family_amendments measurement price_table models per_call_timeout_sec model_policy envelope quality_floor
 dominance_cost_tolerance final_choice support reference_seed archive reservoir exploration_fraction policies
revisit_key revisit_match_set futility horizon checkpoints stop_rules exposure endpoints power budget campaigns
context convergence_diagnostic collapse_threshold not_tested written_before_scoring'''.split())
ADMITTED = frozenset(('gpt-5.6-terra', 'claude-sonnet-5-5'))


def positive(value, label):
    require(type(value) in (int, float) and math.isfinite(value) and value > 0, f'invalid {label}')


def validate_campaign_criterion(frozen, containing):
    """Shared fail-closed C1 schema gate; no evidence or provider activity is prepared."""
    try:
        return campaign_criterion_shape(frozen, containing)
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError(f'qualification: missing or malformed C1 frozen field: {error}') from error


def campaign_criterion_shape(frozen, containing):
    """Validate frozen C1 shape; evidence validity remains qualification.validate's job."""
    require(FIELDS <= set(frozen), f'C1 missing frozen fields: {sorted(FIELDS - set(frozen))}')
    require(frozen['purpose'] == 'quality' and frozen['written_before_scoring'] is True,
            'C1 needs predeclared quality criterion')
    campaign_nested_fields(frozen)
    selected, models = campaign_models(frozen)
    accepted = frozen['accepted_measure']
    require(accepted['step'] in ('A', 'A_prime') and isinstance(accepted['approval'], str) and
            accepted['approval'].strip(), 'accepted measure requires step and owner approval')
    reference(accepted['criterion'], containing)
    require(set(frozen['family_amendments']) == {'amends_5', 'amends_6'}, 'C1 needs both family amendments')
    for value in frozen['family_amendments'].values():
        reference(value, containing)
    require(frozen['calibration'].get('margin') == 4 and frozen['calibration'].get('mutant_margin') == 2 and
            frozen['calibration'].get('error_rate') == 0 and frozen['anchor_spread_limit'] == 2,
            'C1 calibration rules differ')
    require(frozen['quality_floor'] == {'kind': 'above_stub'}, 'C1 requires above_stub quality floor')
    require(frozen['final_choice']['mean_cost'] == 'metered_USD', 'C1 requires metered USD cost axis')
    require(frozen['price_table']['currency'] == 'USD' and
            selected | set(models) <= set(frozen['price_table']['models']), 'missing model price table')
    from experiments.orc_structural_search import pricing
    pricing.validate(frozen['price_table'])
    for rates in frozen['price_table']['models'].values():
        require(set(pricing.FIELDS) <= set(rates), 'C1 needs all four model prices')
    campaign_parameters(frozen)
    return frozen


def campaign_models(frozen):
    selected = names(frozen['judges'], 'judges')
    policy = frozen['model_policy']
    allowed = names(policy['allowed'], 'allowed models')
    require(allowed <= ADMITTED and selected <= allowed, 'unadmitted C1 model')
    require(policy['all_roles'] is True and policy['fable'] == 'forbidden' and
            policy['codex_native_agents'] == 'disabled', 'invalid C1 model policy')
    require(policy['nested_claude'] in (None, 'disabled', 'forbidden', 'claude-sonnet-5-5'), 'unadmitted nested model')
    require(policy['nested_claude'] != 'forbidden' or not any('claude' in name for name in allowed),
            'forbidden Claude policy admits Claude')
    models = frozen['models']
    require(isinstance(models, dict) and models and set(models) <= allowed, 'unadmitted coder model')
    for efforts in models.values():
        require(names(efforts, 'model efforts') <= {'low', 'medium', 'high'}, 'unadmitted model effort')
    campaign_mutator(policy, allowed)
    require(set(frozen['judge_bindings']) == selected, 'judge bindings differ from judges')
    return selected, models


def campaign_parameters(frozen):
    require(frozen['policies'] == ['frontier_only', 'mixture'], 'invalid C1 policies')
    require(frozen['archive'] == {'size': 6, 'spread_rule': 'cheapest_highest_largest_gaps', 'scope': 'campaign'},
            'invalid C1 archive')
    require(frozen['reservoir'] == {'capacity': 4, 'admission': 'valued_non_frontier', 'eviction': 'fifo'},
            'invalid C1 reservoir')
    require(frozen['futility'] == {'consecutive': 4, 'counts': ['revisit', 'rejected', 'exhausted'],
                                 'resets': ['fresh'], 'ignored': ['incident']}, 'invalid C1 futility')
    require(frozen['exploration_fraction'] == .25 and frozen['dominance_cost_tolerance'] == .10,
            'invalid C1 exploration or tolerance')
    require(frozen['support'] == {'rule': 'every_adaptive_task', 'task_weights': 'equal', 'min_trials': 1},
            'invalid C1 support')
    campaign_limits(frozen)
    campaign_preregistration(frozen)
    positive(frozen['endpoints']['B_plan_usd'], 'B_plan_usd')
    rows = frozen['campaigns']
    require(isinstance(rows, list) and len(rows) == 2, 'C1 requires matched campaign pair')
    names([row['label'] for row in rows], 'campaign labels')
    require({row['policy'] for row in rows} == set(frozen['policies']) and
            rows[0]['run_seed'] == rows[1]['run_seed'], 'campaign policies or run seeds differ')


def campaign_mutator(policy, allowed):
    argv = shlex.split(policy['mutator'])
    flags = [argv[i + 1] for i, token in enumerate(argv[:-1]) if token in ('--model', '-m')]
    flags += [token.split('=', 1)[1] for token in argv if token.startswith('--model=')]
    require(len(flags) == 1 and flags[0] in allowed, 'mutator model is not admitted')


def campaign_nested_fields(frozen):
    required = {
        'horizon': {'generations', 'episodes_per_generation', 'adaptive_replicates', 'validation_replicates',
                    'sealed_replicates', 'finalists_per_campaign', 'warm_start'},
        'endpoints': {'cost_ceilings', 'quality_targets', 'budget_cuts', 'B_plan_usd', 'calls_cuts'},
        'final_choice': {'equivalence_tolerance', 'mean_cost', 'mean_cost_ceiling_rule', 'provider_calls'},
        'model_policy': {'allowed', 'all_roles', 'fable', 'nested_claude', 'codex_native_agents', 'mutator'}}
    for field, keys in required.items():
        require(isinstance(frozen[field], dict) and keys <= set(frozen[field]), f'C1 missing {field} fields')
    horizon = frozen['horizon']
    warm = horizon['warm_start']
    require({'seeds', 'replicates', 'smoke'} <= set(warm), 'C1 missing warm-start fields')
    for field in required['horizon'] - {'warm_start'}:
        require(type(horizon[field]) is int, f'C1 {field} must be integer')
        positive(horizon[field], field)
    require(warm == {'seeds': ['direct', 'implement_check_diagnose_repair'], 'replicates': 2,
                     'smoke': 'first evaluation'}, 'invalid C1 warm start')
    require(frozen['endpoints']['cost_ceilings'] == [1, 2, 4] and
            frozen['endpoints']['quality_targets'] == [.5, 1., 2.] and
            frozen['endpoints']['budget_cuts'] == [.5, .75, 1.] and
            frozen['endpoints']['calls_cuts'] == [39, 58, 77], 'invalid C1 endpoints')
    require(frozen['final_choice']['equivalence_tolerance'] == .5 and
            frozen['final_choice']['provider_calls'] == 'mean', 'invalid C1 final-choice rules')


def campaign_limits(frozen):
    envelope = frozen['envelope']
    caps = {'episode': 3600, 'evaluation': 14400, 'per_call_timeout_sec': 5400,
            'concurrency': 4, 'child_planned_maximum': 4, 'wall_clock_ceiling_h': 30}
    for field, cap in caps.items():
        positive(envelope[field], field)
        require(envelope[field] <= cap, f'C1 envelope {field} exceeds bound')
    for field in ('concurrency', 'child_planned_maximum', 'per_call_timeout_sec'):
        require(type(envelope[field]) is int, f'C1 envelope {field} must be integer')
    require(envelope['per_call_timeout_sec'] == frozen['per_call_timeout_sec'], 'timeout envelope differs')
    require(envelope['per_call_timeout_sec'] <= envelope['evaluation'],
            'seed per-call timeout exceeds evaluation envelope')
    horizon = frozen['horizon']
    require(horizon['generations'] <= 4 and horizon['episodes_per_generation'] <= 4, 'C1 horizon exceeds bound')
    expected = {'adaptive_replicates': 1, 'validation_replicates': 3, 'sealed_replicates': 3,
                'finalists_per_campaign': 2}
    require(all(horizon[field] == value for field, value in expected.items()), 'C1 replicates or finalists differ')
    require(type(horizon['warm_start']['replicates']) is int, 'warm-start count must be integer')
    require(frozen['final_choice']['mean_cost_ceiling_rule'] ==
            '4 x c_ref, resolved after P0 and passed as a readout argument', 'C1 final cost ceiling rule differs')


def campaign_preregistration(frozen):
    rules = {'horizon': True, 'futility': True, 'call_cap': True, 'quota_exhaustion': True,
             'wall_clock_ceiling': True,
             'invalid_evidence': ['calibration', 'unadjudicated_contamination', 'malformed_ingest'],
             'judge_incidents': 2, 'persistent_infrastructure': 3}
    require(frozen['stop_rules'] == rules, 'C1 requires every declared stop rule')
    for key in ('horizon', 'futility', 'call_cap', 'quota_exhaustion', 'wall_clock_ceiling'):
        require(frozen['stop_rules'][key] is True, f'C1 {key} stop rule must be enabled')
    for key in ('judge_incidents', 'persistent_infrastructure'):
        require(type(frozen['stop_rules'][key]) is int, f'C1 {key} stop count must be integer')
    require(isinstance(frozen['context'], dict) and isinstance(frozen['context']['evaluator_version'], str) and
            frozen['context']['evaluator_version'].strip(), 'C1 context requires evaluator_version')
    campaign_budget(frozen['budget'])
    campaign_power(frozen['power'])


def campaign_budget(budget):
    require(isinstance(budget, dict) and isinstance(budget['steps'], dict), 'C1 needs per-step budgets')
    require(set(budget['steps']) >= {'P0', 'P1', 'P2', 'P3', 'P4'}, 'C1 budget omits a planned stage')
    require(budget['cap_rule'] ==
            'settled calls + next batch planned maximum + one relaunch of largest unit; stop before cap',
            'C1 budget cap rule differs')
    for name, step in budget['steps'].items():
        require(isinstance(step, dict), f'C1 {name} budget must declare planned and cap')
        require(all(type(step[key]) is int and step[key] > 0 for key in ('planned', 'cap')),
                f'C1 {name} budget needs positive integer calls')
        require(step['planned'] <= step['cap'], f'C1 {name} planned calls exceed cap')


def campaign_power(power):
    require(isinstance(power, dict) and isinstance(power['assumptions'], str) and power['assumptions'].strip(),
            'C1 power requires declared assumptions')
    require(power['formula'] == 'delta = (z_(1-alpha/2) + z_(1-beta)) * sigma_c * sqrt(2 / R)',
            'C1 power formula differs')
    require(type(power['delta']) in (int, float) and power['delta'] == 1 and
            type(power['R']) is int and power['R'] == 1, 'C1 descriptive pilot requires delta=1 and R=1')
    bracket = power['bracket']
    require(isinstance(bracket, list) and len(bracket) == 2, 'C1 power needs a two-endpoint bracket')
    for value in bracket:
        positive(value, 'campaign SD bracket')
    require(bracket[0] < bracket[1], 'C1 power bracket must increase')
    require(power['statement'] == 'descriptive pilot; no policy claim', 'C1 power statement must remain descriptive')


def check_warm_inputs(frozen, seeds, tasks, launch):
    if launch['concurrency'] != frozen['envelope']['concurrency']:
        raise ValueError('warm concurrency differs from frozen acquisition')
    if launch['call_cap'] != frozen['budget']['steps']['P0']['cap'] or sorted(p.stem for p in seeds) != sorted(frozen['horizon']['warm_start']['seeds']):
        raise ValueError('warm start cap or seeds differ from frozen acquisition')
    runtime = launch['runtime']
    actual = {Path(t).resolve() for t in tasks}
    if actual != {(runtime / t).resolve() for t in frozen['tasks']}:
        raise ValueError('warm adaptive tasks differ from frozen packages')
    if {Path(t).resolve() for t in launch.get('holdouts', ())} != {(runtime / frozen[k]).resolve() for k in ('validation_task', 'sealed_task')}:
        raise ValueError('warm holdouts differ from frozen validation and sealed packages')
