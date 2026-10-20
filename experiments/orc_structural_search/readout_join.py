"""Verify the harness's clone-ID lineage before exposing its run values."""
import json
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
