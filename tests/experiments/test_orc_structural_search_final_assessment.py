"""Final-study authorization and verified V2 pool joins; synthetic evidence, no providers."""
import copy
import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.orc_structural_search import adaptive, campaign, records, readout, readout_join
from tests.experiments.qualification_support import qualified_v2, sha, write
from tests.experiments.test_orc_structural_search_campaign_loop import (  # noqa: F401
    setup, scorer, cli_args, world, synthetic_receipts, sandboxed)


def pool(q, evidence, pools, task, specs, *, split='adaptive', generation=0):
    """Create frozen synthetic harness artifacts, retaining real read_pool/V2 verification."""
    evidence.mkdir(parents=True, exist_ok=True)
    log = evidence / 'log.jsonl'
    runs, clones = [], {}
    for cid, rep, value, seed in specs:
        eid = f'{split}-{cid}-{task.name}-{rep}'
        directory = evidence.parent / 'W' / 'records' / eid
        (directory / 'calls/1').mkdir(parents=True, exist_ok=True)
        write(directory / 'record.json', {'tree': str(directory), 'created_at': 0,
              'scan': {'hits': [], 'verdict': None, 'calls': 1}})
        records.append_record(log, {'kind': 'evaluation', 'mode': 'catalog' if seed else 'campaign',
            'seed': seed, 'evaluation_id': eid, 'run_id': eid, 'candidate_id': cid, 'candidate_root': str(directory),
            'task_id': task.name, 'replicate': rep, 'outcome': 'completed', 'records_dir': str(directory),
            'criterion_sha256': sha(q.criterion), 'split': split, 'generation': generation,
            'provider_calls': 1, 'wall_clock_sec': 30, 'receipt_usage': [{'call_id': '1', 'status': 'complete',
                'provider': 'codex', 'usage': [{'model': 'gpt-5.6-terra',
                    'provenance': {'complete_native_transcript': True, 'session_sha256': 'sha256:' + 'a' * 64,
                                   'model_source': 'turn_context.model'},
                    'charge_tokens': {'input': 100, 'output': 100, 'cache_read': 0, 'cache_write': 0}}]}]})
        runs.append({'run': str(directory), 'arm': eid, 'value': value, 'hidden_value': .5,
                     'calls': 1, 'wall_clock_sec': 30})
        clones[eid] = {'arm': eid, 'run': str(directory), 'labels': ['final']}
    directory = pools / f'gen-{generation}' / task.name
    judge_records = directory / 'records/judges' / q.judges[0]
    (judge_records / 'calls').mkdir(parents=True, exist_ok=True)
    write(judge_records / 'record.json', {'kind': 'judge', 'records_dir': str(judge_records),
          'tree': str(judge_records), 'created_at': 0, 'provider_calls': 0, 'receipt_usage': []})
    write(judge_records / 'scan.json', {'hits': [], 'verdict': None, 'calls': 0})
    mapping = {'runtime': str(q.runtime), 'task': str(task), 'criterion_sha256': sha(q.criterion),
        'judges': {q.judges[0]: {'providers': str(q.bindings), 'dir': 'tree'}}, 'created_at': 0, 'batches': [{}], 'clones': clones,
        'runs': {run['run']: {key: value for key, value in run.items() if key != 'run'} | {'selected': 'final'}
                 for run in runs},
        'rubric': json.loads(q.criterion.read_text())['rubric']}
    write(directory / 'records/mapping.json', mapping)
    write(directory / f'records/score-inputs-{q.judges[0]}.json',
          {'judge_model': q.judges[0], 'criterion_sha256': sha(q.criterion)})
    anchors = [{'judge': q.judges[0], 'batch': 0, 'anchor': f'{task.name}-{role}', 'total': total}
               for role, total in [('upstream', 8), ('partial', 5), ('mutant', 5), ('stub', 0)]]
    results = write(directory / 'records/results.json', {'criterion_sha256': sha(q.criterion),
        'runs': runs, 'judges': q.judges, 'anchors': anchors, 'agreement': {}, 'excluded_judges': {},
        'clones': {eid: info | {'score': runs[index]['value'], 'hidden': .5}
                   for index, (eid, info) in enumerate(clones.items())}})
    records.append_record(log, {'kind': 'judging', 'generation': generation, 'task': task.name,
                               'pool': str(directory), 'results': str(results)})
    write(evidence / 'calls.json', [{'kind': 'evaluation', 'key': 'synthetic', 'planned': len(specs), 'calls': len(specs)}])
    return results


@pytest.fixture
def study(tmp_path):
    q = qualified_v2(tmp_path / 'q')
    frozen = json.loads(q.criterion.read_text())
    config = write(tmp_path / 'config.json', {'synthetic': 'bound configuration'})
    store = records.open_store(tmp_path / 'S', writer=True)
    roots = lambda name: {key: str(tmp_path / name / label) for key, label in
                         [('work', 'W'), ('evidence', 'E'), ('pools', 'P')]}
    def start(label, policy, warm=()):
        return campaign.start_campaign(store, label=label, context='ctx1:fixture', policy=policy,
            parameters={'criterion_sha256': sha(q.criterion), 'config_sha256': sha(config),
                        'runtime': str(q.runtime), 'runtime_commit': 'synthetic', 'criterion_path': str(q.criterion)},
            budget={}, seeds=['direct'], run_seed=1, warm_start=warm, declared_roles={}, roots=roots(label))
    warm = start('warm', 'warm_start')
    warm_header = records.find_campaign(store, warm)
    for cid in ('ref', 'child'):
        store.append({'kind': 'subject', 'candidate_id': cid, 'campaign_id': warm, 'parent': None,
            'source': str(tmp_path / cid), 'skeleton': cid, 'policies': [], 'idea_key': cid, 'descriptor': {}})
    results = pool(q, Path(warm_header['roots']['evidence']), Path(warm_header['roots']['pools']), q.tasks[0],
                   [('ref', 1, 5, 'direct'), ('ref', 2, 5, 'direct'), ('child', 1, 6, 'other'), ('child', 2, 6, 'other')])
    campaign.ingest(store, warm, 'ctx1:fixture', Path(warm_header['roots']['evidence']), [results], criterion=q.criterion)
    warm_ids = [r['trial_id'] for r in store.rows('trial')]
    ids = [start(row['label'], row['policy'], warm_ids) for row in frozen['campaigns']]
    table = {cid: {'candidate_id': cid, 'quality': quality, 'cost': .0014, 'above_floor': True,
                   'support': 'every_adaptive_task', 'provider_calls': 1, 'wall_clock_sec': 30}
             for cid, quality in [('ref', 5), ('child', 6)]}
    for cid in ids:
        header = records.find_campaign(store, cid)
        evidence = Path(header['roots']['evidence'])
        evidence.mkdir(parents=True)
        (evidence / 'log.jsonl').touch()
        write(evidence / 'calls.json', [])
        snapshot = {'generation': 0, 'completed_generation': 0, 'log_position': 0,
                    'table': table, 'frontier': ['child', 'ref'], 'reservoir': [], 'budget': {'metered_cost': 0}}
        records.write_checkpoint(store, cid, {'generation': 0, 'completed_generation': 0,
            'table': table, 'frontier': ['child', 'ref'], 'reservoir': [], 'rng_state': None,
            'ingestion_position': 0, 'ledger_index': 0, 'futility_streak': 0, 'budget': {},
            'stopped': 'futility', 'scheduled': [{'candidate_id': 'abandoned'}], 'trajectory': [snapshot]})
    launch = {key: tmp_path / 'validation-run' / name for key, name in
              [('work_root', 'W'), ('evidence_root', 'E'), ('pools_root', 'P')]}
    launch['sealed_roots'] = {key: tmp_path / 'sealed-run' / name for key, name in
                              [('work_root', 'W'), ('evidence_root', 'E'), ('pools_root', 'P')]}
    launch['config_path'] = config
    yield SimpleNamespace(q=q, frozen=frozen, store=store, ids=ids, launch=launch, tmp=tmp_path)
    store.close()


def manifest(s, **changes):
    return records.validation_manifest(s.store, s.ids, validation_task=s.q.validation, replicates=3,
        finalists=2, mean_cost_ceiling=.0056, launch=s.launch, criterion=s.q.criterion, **changes)


def test_final_resume_plans_new_roots_before_the_first_evaluation(tmp_path):
    from experiments.orc_structural_search import judging
    launch = {'evidence_root': tmp_path / 'E', 'pools_root': tmp_path / 'P', 'resume': True}
    planned = judging.planned_judging([object(), object()], -1, [tmp_path / 'validation'], 3,
                                     launch, {'judges': ['gpt-5.6-terra=bindings']}, [4])
    assert planned == 2 and not launch['evidence_root'].exists()


def test_C1_programmatic_judging_blocks_Claude_before_the_fake_backend(study, sandboxed, monkeypatch):
    import os
    import subprocess
    from experiments.orc_structural_search import judging
    from tests.experiments.compare_harness_support import OUTSIDE_SANDBOX_MOUNTS, REPO
    s = study
    results = validation_pool(s)
    destination = s.launch['pools_root'] / 'validation' / s.q.validation.name
    destination.parent.mkdir(parents=True)
    shutil.move(results.parent.parent, destination)
    log = s.launch['evidence_root'] / 'log.jsonl'
    log.write_text(''.join(json.dumps(row) + '\n' for row in records.read_records(log) if row['kind'] != 'judging'))
    OUTSIDE_SANDBOX_MOUNTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OUTSIDE_SANDBOX_MOUNTS) as directory:
        root = Path(directory)
        (root / 'tree/tmp').mkdir(parents=True)
        (root / 'bin').mkdir()
        marker = root / 'backend-executed'
        backend = root / 'bin/claude'
        backend.write_text('#!/bin/sh\ntouch "$CLAUDE_TEST_MARKER"\nexit 17\n')
        backend.chmod(0o755)
        statuses = []
        def fake_scorer(pool, name, script='score', *, env=None):
            done = subprocess.run([str(REPO / 'experiments/compare/shim/claude'), '-p'],
                input='synthetic prompt', text=True, capture_output=True,
                env={**(env or os.environ), 'PATH': f'{root / "bin"}:{os.defpath}',
                     'COMPARE_ROOT': str(root / 'records'), 'COMPARE_TREE': str(root / 'tree'),
                     'COMPARE_BASE': 'synthetic-unused', 'CLAUDE_TEST_MARKER': str(marker)})
            statuses.append(done.returncode)
            raise subprocess.CalledProcessError(done.returncode, 'synthetic scorer')
        monkeypatch.setattr(judging, 'run_judge', fake_scorer)
        with pytest.raises(judging.JudgeIncident):
            judging.judge_generation(s.launch['evidence_root'], -1, [s.q.validation], criterion=s.q.criterion,
                judges=[f'{s.q.judges[0]}={s.q.bindings}'], solutions={s.q.validation.name: 'unused'},
                call_cap=100, pool_root=s.launch['pools_root'], resume=True)
        assert not marker.exists() and statuses == [2, 2]

def test_validation_manifest_binds_the_exact_frozen_pair_and_is_idempotent(study):
    s = study
    row = manifest(s)
    assert row['campaign_ids'] == sorted(s.ids) and row['campaign_id'] == min(s.ids)
    assert row['reference_id'] == 'ref' and row['warm_reference_trial_ids']
    assert row['finalists'] == {cid: ['child', 'ref'] for cid in s.ids}
    assert row['sealed_roots'] == {key: str(value.resolve()) for key, value in s.launch['sealed_roots'].items()}
    assert manifest(s)['seq'] == row['seq']
    assert len(s.store.rows('exposure')) == 1
    with pytest.raises(ValueError, match='complete|frozen'):
        records.validation_manifest(s.store, s.ids[:1], validation_task=s.q.validation, replicates=3,
            finalists=2, mean_cost_ceiling=.0056, launch=s.launch, criterion=s.q.criterion)


@pytest.mark.parametrize('status', [None, 'invalid_evidence'])
def test_validation_refuses_nonfinal_or_invalid_campaigns_before_exposure(study, status):
    s = study
    state = records.read_checkpoint(s.store, s.ids[0])
    records.write_checkpoint(s.store, s.ids[0], state | {'stopped': status})
    with pytest.raises(ValueError, match='terminal|invalid'):
        manifest(s)
    assert s.store.rows('exposure') == []

def test_validation_refuses_pending_work_and_config_changes_before_exposure(study):
    s = study
    evidence = Path(records.find_campaign(s.store, s.ids[0])['roots']['evidence'])
    write(evidence / 'calls.json', [{'kind': 'episode', 'key': 'active', 'planned': 1, 'calls': None}])
    with pytest.raises(ValueError, match='pending|unsettled'):
        manifest(s)
    write(evidence / 'calls.json', [])
    s.launch['config_path'].write_text('{}')
    with pytest.raises(ValueError, match='config'):
        manifest(s)
    assert s.store.rows('exposure') == []

def test_validation_manifest_exact_retry_refuses_changed_roots(study):
    s = study
    manifest(s)
    s.launch['sealed_roots']['work_root'] = s.tmp / 'changed-root'
    with pytest.raises(ValueError, match='manifest|retry'):
        manifest(s)

def test_final_pool_verification_requires_authorized_sets_and_current_calibration(study):
    s = study
    authorization = manifest(s)
    results = pool(s.q, s.launch['evidence_root'], s.launch['pools_root'], s.q.validation,
        [(cid, rep, 4 if cid == 'child' else 5, None) for cid in ('child', 'ref') for rep in (1, 2, 3)],
        split='validation', generation=-1)
    verified = readout_join.final_pool(s.store, authorization, role='validation')
    assert verified['results'] == str(results) and len(verified['rows']) == 6
    ledger = s.launch['evidence_root'] / 'calls.json'
    saved = ledger.read_text()
    write(ledger, [{'kind': 'judge', 'calls': None, 'planned': 1}])
    with pytest.raises(ValueError, match='unsettled'):
        readout_join.final_pool(s.store, authorization, role='validation')
    ledger.write_text(saved)
    bad = json.loads(results.read_text())
    bad['anchors'][0]['total'] = 0
    write(results, bad)
    with pytest.raises(ValueError, match='calibration'):
        readout_join.final_pool(s.store, authorization, role='validation')

def test_final_pool_refuses_argv_only_native_model_proof(study):
    s = study
    authorization = manifest(s)
    pool(s.q, s.launch['evidence_root'], s.launch['pools_root'], s.q.validation,
         [(cid, rep, 5, None) for cid in ('child', 'ref') for rep in (1, 2, 3)],
         split='validation', generation=-1)
    log = s.launch['evidence_root'] / 'log.jsonl'
    rows = records.read_records(log)
    rows[0]['receipt_usage'][0]['usage'][0]['provenance']['model_source'] = 'shim.argv'
    log.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    with pytest.raises(ValueError, match='actual model identity'):
        readout_join.final_pool(s.store, authorization, role='validation')
def test_freeze_open_and_partial_retry_use_verified_original_validation_trials(study, monkeypatch):
    s = study
    authorization = manifest(s)
    with pytest.raises(ValueError):
        campaign.freeze(s.store, s.ids, 'analysis freeze')
    with pytest.raises(ValueError, match='frozen'):
        campaign.open_sealed(s.store, s.ids, s.q.sealed)
    results = pool(s.q, s.launch['evidence_root'], s.launch['pools_root'], s.q.validation,
        [(cid, rep, 4 if cid == 'child' else 5, None) for cid in ('child', 'ref') for rep in (1, 2, 3)],
        split='validation', generation=-1)
    campaign.ingest(s.store, min(s.ids), 'ctx1:fixture', s.launch['evidence_root'], [results], criterion=s.q.criterion)
    original = s.store.append
    def interrupt(row):
        if row.get('disposition') == 'frozen' and len([r for r in s.store.rows('disposition') if r['disposition'] == 'frozen']) == 1:
            raise RuntimeError('interrupted append')
        return original(row)
    monkeypatch.setattr(s.store, 'append', interrupt)
    with pytest.raises(RuntimeError, match='interrupted'):
        campaign.freeze(s.store, s.ids, 'analysis freeze')
    monkeypatch.setattr(s.store, 'append', original)
    assert campaign.freeze(s.store, s.ids, 'analysis freeze') == 1
    frozen = [r for r in s.store.rows('disposition') if r['disposition'] == 'frozen']
    assert len(frozen) == 2 and {r['choice'] for r in frozen} == {'ref'}
    assert {r['validation_manifest_seq'] for r in frozen} == {authorization['seq']}
    def interrupt_open(row):
        if row.get('disposition') == 'sealed_opened':
            raise RuntimeError('interrupted open')
        return original(row)
    monkeypatch.setattr(s.store, 'append', interrupt_open)
    with pytest.raises(RuntimeError, match='interrupted open'):
        campaign.open_sealed(s.store, s.ids, s.q.sealed)
    monkeypatch.setattr(s.store, 'append', original)
    assert campaign.open_sealed(s.store, s.ids, s.q.sealed) > 0
    with pytest.raises(ValueError, match='already|second'):
        campaign.open_sealed(s.store, s.ids, s.q.sealed)
    assert len([r for r in s.store.rows('exposure') if r['role'] == 'sealed']) == 1
    assert {r['campaign_id'] for r in s.store.rows('trial') if r['split'] == 'validation'} == {min(s.ids)}

def test_final_trials_never_enter_adaptive_membership_estimates_recency_or_convergence(study):
    s = study
    owner = min(s.ids)
    original = s.store.index().trials[s.store.rows('trial')[0]['trial_id']]
    s.store.append(original | {'trial_id': 'final-secret', 'campaign_id': owner, 'candidate_id': 'secret',
                               'split': 'sealed', 'evaluation_id': 'final-secret'})
    s.store.append({'kind': 'subject', 'candidate_id': 'secret', 'campaign_id': owner, 'parent': 'ref',
        'source': 'secret', 'skeleton': 'secret', 'policies': [], 'idea_key': 'secret', 'descriptor': {},
        'structure': {'idea_key': 'secret'}})
    assert 'secret' not in campaign.campaign_candidates(s.store, owner)
    assert campaign.evidence(s.store, 'secret', 'ctx1:fixture', tasks=[s.q.tasks[0].name],
        price_table=s.frozen['price_table'], min_trials=1)['kind'] == 'unobserved'
    assert not campaign.evaluated_structures(s.store, owner, scheduled=[])
    assert campaign.convergence(s.store, owner)['shares'] == {}


def validation_pool(s):
    return pool(s.q, s.launch['evidence_root'], s.launch['pools_root'], s.q.validation,
        [(cid, rep, 4 if cid == 'child' else 5, None) for cid in ('child', 'ref') for rep in (1, 2, 3)],
        split='validation', generation=-1)

def test_final_ingestion_refuses_bad_current_controls_without_publishing_trials_or_assessments(study):
    s = study
    manifest(s)
    results = validation_pool(s)
    data = json.loads(results.read_text())
    data['anchors'][0]['total'] = 0
    write(results, data)
    before = copy.deepcopy(s.store.rows())
    with pytest.raises(ValueError, match='calibration'):
        campaign.ingest(s.store, min(s.ids), 'ctx1:fixture', s.launch['evidence_root'], [results], criterion=s.q.criterion)
    assert s.store.rows() == before

def test_final_ingestion_requires_the_authorized_owner_even_before_any_original_trial_exists(study):
    s = study
    manifest(s)
    results = validation_pool(s)
    with pytest.raises(ValueError, match='owner'):
        campaign.ingest(s.store, max(s.ids), 'ctx1:fixture', s.launch['evidence_root'], [results], criterion=s.q.criterion)

def test_freeze_refuses_changed_checkpoint_before_any_disposition(study):
    s = study
    manifest(s)
    results = validation_pool(s)
    campaign.ingest(s.store, min(s.ids), 'ctx1:fixture', s.launch['evidence_root'], [results], criterion=s.q.criterion)
    state = records.read_checkpoint(s.store, max(s.ids))
    records.write_checkpoint(s.store, max(s.ids), state | {'generation': 4})
    with pytest.raises(ValueError, match='changed'):
        campaign.freeze(s.store, s.ids, 'freeze')
    assert not s.store.rows('disposition')

def test_validation_requires_explicit_config_path_before_exposure(study):
    s = study
    with pytest.raises(ValueError, match='config_path'):
        adaptive.validate_campaign_finalists(s.store, s.ids, validation_task=s.q.validation,
            replicates=3, finalists=2, mean_cost_ceiling=.0056, launch={}, judge={'criterion': s.q.criterion})
    assert not s.store.rows('exposure')

def test_campaign_readout_uses_original_P0_without_later_context_observations(study):
    s = study
    original = s.store.rows('trial')[0]
    s.store.append(original | {'trial_id': 'later', 'campaign_id': s.ids[0], 'evaluation_id': 'later'})
    s.store.append({'kind': 'assessment', 'trial_id': 'later', 'results': 'later', 'clone_ids': [],
        'task': s.q.tasks[0].name, 'outcome': 'completed', 'value': 100, 'hidden': .5,
        'criterion_sha256': sha(s.q.criterion), 'proof_sha256': 'synthetic', 'split': 'adaptive'})

    report = readout.campaign_report(s.store, s.ids, criterion=s.q.criterion, ceiling=.0056)

    assert report['descriptive_only'] is True
    assert report['reference'] == {'candidate_id': 'ref', 'quality': 5, 'cost': .0014}
    assert len(report['campaigns']) == 2

def test_readout_result_arguments_have_no_score_authority_without_manifest(study):
    s = study
    forged = write(s.tmp / 'forged.json', {'choice': 'child', 'value': 100})
    with pytest.raises(ValueError, match='authorized|manifest'):
        readout.campaign_report(s.store, s.ids, criterion=s.q.criterion, ceiling=.0056,
                               validation_results=forged)

def test_public_readout_cli_uses_verified_store_and_leaves_it_unchanged(study, capsys):
    from tests.experiments.compare_harness_support import OUTSIDE_SANDBOX_MOUNTS
    s = study
    OUTSIDE_SANDBOX_MOUNTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OUTSIDE_SANDBOX_MOUNTS) as directory:
        destination = Path(directory) / 'S'
        shutil.copytree(s.store.root, destination)
        before = (destination / records.LOG).read_bytes()
        args = ['readout', '--store', str(destination), '--criterion', str(s.q.criterion), '--ceiling', '.0056']
        for cid in s.ids:
            args += ['--campaign', cid]
        campaign.main(args)
        report = json.loads(capsys.readouterr().out)
        assert report['reference']['candidate_id'] == 'ref' and report['descriptive_only'] is True
        assert (destination / records.LOG).read_bytes() == before

def test_sealed_ingestion_requires_committed_open_and_readout_reports_budget_once(study):
    s = study
    manifest(s)
    results = validation_pool(s)
    campaign.ingest(s.store, min(s.ids), 'ctx1:fixture', s.launch['evidence_root'], [results], criterion=s.q.criterion)
    campaign.freeze(s.store, s.ids, 'freeze')
    campaign.open_sealed(s.store, s.ids, s.q.sealed)
    roots = s.launch['sealed_roots']
    sealed = pool(s.q, roots['evidence_root'], roots['pools_root'], s.q.sealed,
                  [('ref', rep, 4, None) for rep in (1, 2, 3)], split='sealed', generation=-1)
    campaign.ingest(s.store, min(s.ids), 'ctx1:fixture', roots['evidence_root'], [sealed], criterion=s.q.criterion)

    report = readout.campaign_report(s.store, s.ids, criterion=s.q.criterion, ceiling=.0056,
                                   validation_results=results, sealed_results=sealed)

    for ids in (s.ids[:1], [*s.ids, s.ids[0]]):
        with pytest.raises(ValueError, match='complete.*manifest'):
            readout.campaign_report(s.store, ids, criterion=s.q.criterion, ceiling=.0056)
    assert report['descriptive_only'] is False
    for row in report['campaigns'].values():
        assert row['final_assessment']['validation']['choice'] == 'ref'
        assert row['final_assessment']['sealed']['choice']['quality'] == 4
    assert 'final_budget' in report and all('final_budget' not in row for row in report['campaigns'].values())
    assert len([row for row in s.store.rows('trial') if row['split'] == 'sealed']) == 3

def test_P0_reference_must_still_match_original_ingested_clone_assessments(study):
    s = study
    warm = next(row for row in s.store.rows('campaign') if row['policy'] == 'warm_start')
    judged = next(row for row in records.read_records(Path(warm['roots']['evidence']) / 'log.jsonl') if row['kind'] == 'judging')
    data = json.loads(Path(judged['results']).read_text())
    for row in data['runs']:
        if '-ref-' in row['arm']:
            row['value'] = 7
            data['clones'][row['arm']]['score'] = 7
    write(Path(judged['results']), data)
    with pytest.raises(ValueError, match='stored assessment'):
        manifest(s)

@pytest.mark.parametrize('mode', ['mismatched', 'empty', 'unsupported'])
def test_terminal_frontier_must_be_the_persisted_calibrated_snapshot_frontier(study, mode):
    s = study
    state = records.read_checkpoint(s.store, s.ids[0])
    state['frontier'] = [] if mode == 'empty' else ['ref']
    if mode != 'mismatched':
        state['trajectory'][-1].update(frontier=state['frontier'], table=state['table'])
    if mode == 'unsupported':
        state['table']['ref']['support'] = 'insufficient'
    records.write_checkpoint(s.store, s.ids[0], state)
    with pytest.raises(ValueError, match='persisted calibrated'):
        manifest(s)
    assert not s.store.rows('exposure')

def test_stored_assessment_qualification_provenance_is_verified(study):
    s = study
    assessment = s.store.rows('assessment')[0]
    assessment['proof_sha256'] = 'different qualification receipt'
    with pytest.raises(ValueError, match='provenance'):
        manifest(s)

def test_readout_refuses_changed_validation_log_after_freeze(study):
    s = study
    manifest(s)
    results = validation_pool(s)
    campaign.ingest(s.store, min(s.ids), 'ctx1:fixture', s.launch['evidence_root'], [results], criterion=s.q.criterion)
    campaign.freeze(s.store, s.ids, 'freeze')
    log = s.launch['evidence_root'] / 'log.jsonl'
    records.append_record(log, {'kind': 'unexpected-later-metadata'})
    with pytest.raises(ValueError, match='frozen disposition'):
        readout.campaign_report(s.store, s.ids, criterion=s.q.criterion, ceiling=.0056)

def test_public_cli_complete_study_lifecycle_uses_verified_v2_pools(sandboxed, setup, monkeypatch, capsys):
    """Scripted CLI lifecycle; synthetic controls and scores establish no live qualification."""
    import shlex
    from experiments.orc_structural_search import judging
    s = setup
    for key, value in s.common['env'].items():
        monkeypatch.setenv(key, value)
    scored = []
    def dispatch(directory, name, script='score', **kwargs):
        scored.append((str(directory), name, script))
        return scorer(directory.parents[2] / 'E/log.jsonl')(directory, name, script)
    monkeypatch.setattr(judging, 'run_judge', dispatch)
    store_path = s.world.outside / 'lifecycle-S'
    from tests.experiments.orc_structural_search_support import acquire_study, assess_sealed
    headers, ids, ceiling, checkpoint_bytes = acquire_study(s, store_path)
    validation, sealed = s.world.outside / 'lifecycle-validation', s.world.outside / 'lifecycle-sealed'
    validate = ['validate', '--store', str(store_path), '--config', str(s.config), '--criterion', str(s.q.criterion),
        '--runtime', str(s.world.runtime), '--validation-task', str(s.q.validation),
        '--work-root', str(validation / 'W'), '--evidence', str(validation / 'E'), '--pools-root', str(validation / 'P'),
        '--sealed-work-root', str(sealed / 'W'), '--sealed-evidence', str(sealed / 'E'), '--sealed-pools-root', str(sealed / 'P'),
        '--ceiling', str(ceiling), '--eval-timeout-sec', '14400', '--concurrency', '1', '--call-cap', '160',
        '--agent-cmd', shlex.join(s.common['agent_cmd']), '--solution', f'{s.q.validation.name}={s.world.solution}',
        '--judge', s.common['judges'][0]]
    campaigns = [item for cid in ids for item in ('--campaign', cid)]
    campaign.main([*validate, *campaigns])
    count = len(scored)
    campaign.main([*validate, *campaigns])
    assert len(scored) == count
    for declaration in s.frozen['campaigns']:
        args = ['run', *cli_args(s, 'lifecycle-' + declaration['policy'], store_path),
            '--label', declaration['label'], '--policy', declaration['policy'], '--generations', '2',
            '--episodes-per-generation', '4', '--run-seed', str(declaration['run_seed']), '--continue']
        with pytest.raises(ValueError, match='validation exposure'):
            campaign.main(args)
    campaign.main(['freeze', '--store', str(store_path), *campaigns, '--reason', 'synthetic analysis freeze'])
    campaign.main(['open-sealed', '--store', str(store_path), *campaigns, '--sealed-task', str(s.q.sealed)])
    validation_results, sealed_results = assess_sealed(s, store_path, ids, sealed, validation, headers, checkpoint_bytes)
    capsys.readouterr()
    campaign.main(['readout', '--store', str(store_path), '--criterion', str(s.q.criterion),
        *campaigns, '--ceiling', str(ceiling), '--validation-results', str(validation_results), '--sealed-results', str(sealed_results)])
    report = json.loads(capsys.readouterr().out)
    assert report['descriptive_only'] is False and report['final_budget']['calls'] > 0
    assert all(row['final_assessment']['sealed']['choice']['quality'] >= 0 for row in report['campaigns'].values())
