"""Verify the harness's clone-ID lineage before exposing its run values."""
import json
from statistics import mean
from pathlib import Path

from experiments.compare import pool, summarize
from experiments.orc_structural_search.qualification_family import validate_scan
from experiments.orc_structural_search import pricing

CLONE_KEYS = ('run', 'arm', 'labels')
RUN_KEYS = ('arm', 'value', 'hidden_value', 'calls', 'wall_clock_sec')


def validate_clones(mapping, results):
    clones = results['clones']
    if set(mapping['clones']) != set(clones):
        raise ValueError('harness clone IDs differ between mapping and results')
    for cid, source in mapping['clones'].items():
        if clones[cid].get('score') is not None and not pricing.number(clones[cid].get('score')):
            raise ValueError('harness clone score must be finite or excluded')
        if any(source.get(key) != clones[cid].get(key) for key in CLONE_KEYS):
            raise ValueError(f'harness clone lineage differs for {cid}')
    return clones


def verified_runs(mapping, results):
    clones = validate_clones(mapping, results)
    scores = {cid: clone['score'] for cid, clone in clones.items()}
    hidden = {cid: clone['hidden'] for cid, clone in clones.items() if clone.get('hidden') is not None}
    expected = summarize.run_rows(mapping, scores, hidden)
    verify_summaries(expected, results['runs'])
    return {run['arm']: sorted(cid for cid, clone in clones.items() if clone['run'] == run['run']) for run in expected}


def verify_summaries(expected, runs):
    observed = {run['run']: run for run in runs}
    if len(observed) != len(runs) or set(observed) != {run['run'] for run in expected}:
        raise ValueError('harness run identities differ from clone join')
    for run in expected:
        if any(run.get(key) != observed[run['run']].get(key) for key in RUN_KEYS):
            raise ValueError(f'harness run value or cost differs from clone join: {run["run"]}')


def clone_ids(results_path, pool_path, results):
    try:
        mapping = json.loads((Path(pool_path) / 'records/mapping.json').read_text())
        return verified_runs(mapping, results)
    except (KeyError, TypeError, OSError) as error:
        raise ValueError(f'{results_path}: malformed harness clone lineage: {error}') from error


def episode_exclusion(records, row):
    """Typed scan evidence covers the actual episode calls; pending/malformed never becomes clean."""
    metadata = json.loads((records / 'record.json').read_text())
    scan = metadata.get('scan')
    if not isinstance(scan, dict) or not isinstance(scan.get('hits'), list) or type(scan.get('calls')) is not int:
        raise ValueError(f'episode {row["episode_id"]} was not scanned with valid evidence')
    validate_scan(scan)
    calls = row.get('provider_calls')
    if type(calls) is not int or calls != scan['calls']:
        raise ValueError('episode scan does not cover recorded calls')
    if (records / 'calls').exists() and len(list((records / 'calls').iterdir())) != calls:
        raise ValueError('episode scan does not cover actual call files')
    try:
        return pool.exclusion(scan, calls, str(records)) is not None
    except SystemExit as error:
        raise ValueError(str(error)) from error


def calibrated_pool(results, log, criterion):
    from experiments.orc_structural_search.scoring import read_pool
    joined = read_pool(Path(results), Path(log), Path(criterion))
    mapping = json.loads((Path(results).parent / 'mapping.json').read_text())
    frozen = json.loads(Path(criterion).read_text())
    checked = summarize.calibration(json.loads(Path(results).read_text()), mapping,
                                    frozen | {'purpose': 'calibration'})
    if not checked or not checked['passed']:
        raise ValueError(f'current pool calibration failed: {results}')
    return joined | {'calibration': checked, 'proof_sha256': frozen['qualification']['sha256']}


def logged_pools(evidence, pools_root, criterion):
    from experiments.orc_structural_search.records import read_records
    found = {}
    for row in read_records(Path(evidence) / 'log.jsonl'):
        if row['kind'] != 'judging':
            continue
        directory, results = Path(row['pool']).resolve(), Path(row['results']).resolve()
        if not directory.is_relative_to(Path(pools_root).resolve()) or results != directory / 'records/results.json':
            raise ValueError('judging results are outside their authorized pool roots')
        joined = calibrated_pool(results, Path(evidence) / 'log.jsonl', criterion)
        if row['task'] != joined['task']:
            raise ValueError('judging task differs from its pool')
        found[str(results)] = joined
    return list(found.values())



def _calibrated_frontier(state):
    from experiments.orc_structural_search.pareto_readout import _supported_frontier
    trajectory = state.get('trajectory', [])
    ids, table = state.get('frontier', []), state.get('table', {})
    if not trajectory or not ids or any(cid not in table for cid in ids):
        raise ValueError('final assessment requires a persisted calibrated frontier')
    if (trajectory[-1].get('table'), trajectory[-1].get('frontier')) != (table, ids):
        raise ValueError('final assessment requires the persisted calibrated table')
    if len(_supported_frontier(state)) != len(ids):
        raise ValueError('final assessment requires a persisted calibrated supported frontier')

def terminal_checkpoint(store, campaign_id, criterion):
    from experiments.compare.repos import sha256_file
    from experiments.orc_structural_search.records import find_campaign, read_checkpoint, _checkpoint, read_records
    header, state = find_campaign(store, campaign_id), read_checkpoint(store, campaign_id)
    if not state or not state.get('stopped') or state['stopped'] == 'invalid_evidence':
        raise ValueError('final assessment requires a valid terminal campaign checkpoint')
    evidence = Path(header['roots']['evidence'])
    ledger = evidence / 'calls.json'
    entries = json.loads(ledger.read_text())
    if any(row['calls'] is None for row in entries) or len(entries) != state['ledger_index']:
        raise ValueError('final assessment refuses pending or unsettled ledger work')
    _calibrated_frontier(state)
    log = evidence / 'log.jsonl'
    if len(read_records(log)) != state['ingestion_position']:
        raise ValueError('final checkpoint has unaccounted log work')
    pools = logged_pools(evidence, header['roots']['pools'], criterion)
    return state, {'checkpoint_sha256': sha256_file(_checkpoint(store, campaign_id)[0]),
        'ledger_index': len(entries), 'ledger_sha256': sha256_file(ledger), 'log_sha256': sha256_file(log),
        'pools': {pool['results']: sha256_file(Path(pool['results'])) for pool in pools}}


def _warm_originals(store, header):
    from experiments.orc_structural_search import records
    originals = [store.index().trials[tid] for tid in header['warm_start']]
    owners = {trial['campaign_id'] for trial in originals}
    if len(owners) != 1 or any(trial['origin_trial_id'] is not None for trial in originals):
        raise ValueError('reference requires original shared warm-start trials')
    warm = records.find_campaign(store, owners.pop())
    if warm['policy'] != 'warm_start' or warm['context_key'] != header['context_key']:
        raise ValueError('reference warm-start owner differs from the campaign context')
    return warm, originals


def _reference_identity(evidence, frozen):
    from experiments.orc_structural_search import scoring, records
    raw = scoring.latest_evaluations(records.read_records(evidence / 'log.jsonl'))
    ids = {row['candidate_id'] for row in raw
           if row.get('mode') == 'catalog' and row.get('seed') == frozen['reference_seed']}
    if len(ids) != 1:
        raise ValueError('warm reference seed must name exactly one candidate')
    return ids.pop()


def _reference_summary(cid, values, originals, frozen):
    from experiments.orc_structural_search import scoring
    expected = {(Path(task).name, rep) for task in frozen['tasks']
                for rep in range(1, frozen['horizon']['warm_start']['replicates'] + 1)}
    _matched_rows(values, expected)
    trials = {row['evaluation_id']: row for row in originals}
    counted = [trials[row['evaluation_id']] for row in values]
    costs = [pricing.cost(row, frozen['price_table']) for row in counted]
    if not all(pricing.number(value) for value in costs):
        raise ValueError('warm reference cost is unavailable')
    return {'candidate_id': cid, 'quality': mean(scoring.primary_value(row) for row in values),
            'cost': mean(costs), 'trial_ids': sorted(row['trial_id'] for row in counted)}


def warm_reference(store, header, criterion):
    from experiments.orc_structural_search import records, scoring, selection
    frozen = json.loads(Path(criterion).read_text())
    warm, originals = _warm_originals(store, header)
    evidence = Path(warm['roots']['evidence'])
    cid = _reference_identity(evidence, frozen)
    pools = logged_pools(evidence, warm['roots']['pools'], criterion)
    raw = {row['evaluation_id']: row for row in scoring.latest_evaluations(records.read_records(evidence / 'log.jsonl'))}
    for pool in pools:
        selection.assessment_sequences(store, warm, pool | {'raw': raw})
    values = [row for pool in pools for row in pool['rows'] if row['candidate_id'] == cid]
    return _reference_summary(cid, values, originals, frozen)


def _matched_rows(rows, expected):
    from experiments.orc_structural_search.scoring import primary_value
    keys = [(row['task'], row['replicate']) for row in rows]
    if len(keys) != len(set(keys)) or set(keys) != expected or any(primary_value(row) is None for row in rows):
        raise ValueError('assessment lacks exact valued task/replicate support')


def _authorized_evaluations(raw, roots, role, task, candidates):
    for row in raw:
        if (row.get('split'), row['task_id']) != (role, task) or row['candidate_id'] not in candidates:
            raise ValueError('evaluation is outside the authorized assessment split or candidate set')
        if not Path(row['records_dir']).resolve().is_relative_to(Path(roots['work_root']).resolve()):
            raise ValueError('assessment records are outside the authorized work root')


def _final_support(pool, task, candidates, replicates):
    expected = {(task, rep) for rep in range(1, replicates + 1)}
    if {row['candidate_id'] for row in pool['rows']} != candidates or pool['unpooled']:
        raise ValueError('assessment pool differs from the complete authorized candidate set')
    for cid in sorted(candidates):
        _matched_rows([row for row in pool['rows'] if row['candidate_id'] == cid], expected)



def _settled_assessment(roots, criterion, role):
    from experiments.orc_structural_search import ledger
    entries = json.loads((Path(roots['evidence_root']) / ledger.LEDGER).read_text())
    if any(type(row.get('calls')) is not int or row['calls'] < 0 for row in entries):
        raise ValueError('final assessment refuses unsettled ledger work')
    step = 'P3' if role == 'validation' else 'P4'
    if ledger.total(entries) > criterion['budget']['steps'][step]['cap']:
        raise ValueError('final assessment exceeds its frozen call cap')

def final_pool(store, authorization, *, role):
    from experiments.compare.repos import sha256_file
    from experiments.orc_structural_search import records, scoring
    criterion = Path(authorization['criterion_path'])
    if sha256_file(criterion) != authorization['criterion_sha256']:
        raise ValueError('assessment criterion differs from its authorization')
    roots = authorization['validation_roots'] if role == 'validation' else authorization['sealed_roots']
    task = Path(authorization[f'{role}_task']).name
    candidates = set(authorization['candidate_ids'])
    log = Path(roots['evidence_root']) / 'log.jsonl'
    if not log.is_file():
        raise ValueError('final assessment has no committed results log')
    rows = records.read_records(log)
    raw = [row for row in rows if row['kind'] == 'evaluation']
    _authorized_evaluations(raw, roots, role, task, candidates)
    pools = logged_pools(roots['evidence_root'], roots['pools_root'], criterion)
    if len(pools) != 1 or pools[0]['task'] != task:
        raise ValueError('assessment requires its one authorized task pool')
    pool = pools[0]
    _final_support(pool, task, candidates, authorization['replicates'])
    from experiments.orc_structural_search.adaptive import scan_work
    frozen = json.loads(criterion.read_text())
    _settled_assessment(roots, frozen, role)
    scan_work(Path(roots['evidence_root']), frozen)
    return pool | {'raw': {row['evaluation_id']: row for row in scoring.latest_evaluations(rows)},
        'log_sha256': sha256_file(log), 'results_sha256': sha256_file(Path(pool['results']))}


def _ingestion_authorization(store, campaign_id, evidence, role):
    key = 'validation_roots' if role == 'validation' else 'sealed_roots'
    authorizations = [row for row in store.rows('exposure') if row['role'] == role and key in row
                      and Path(row[key]['evidence_root']).resolve() == Path(evidence).resolve()]
    if len(authorizations) != 1 or authorizations[0]['campaign_id'] != campaign_id:
        raise ValueError('final ingestion requires its authorized original trial owner')
    authorization = authorizations[0]
    if role == 'sealed' and not any(row.get('exposure_seq') == authorization['seq'] and row['disposition'] == 'sealed_opened'
                                    for row in store.rows('disposition')):
        raise ValueError('sealed assessment requires committed opening authorization')
    return authorization


def authorize_final_ingestion(store, campaign_id, evidence, pools, evaluations):
    roles = {row.get('split') for row in evaluations}.intersection({'validation', 'sealed'})
    if not roles:
        return
    if len(roles) != 1:
        raise ValueError('final ingestion requires one assessment split')
    role = roles.pop()
    authorization = _ingestion_authorization(store, campaign_id, evidence, role)
    verified = final_pool(store, authorization, role=role)
    if [Path(path).resolve() for path in pools] != [Path(verified['results']).resolve()]:
        raise ValueError('final ingestion results differ from authorized pool')
