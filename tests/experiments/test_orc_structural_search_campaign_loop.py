"""C1 controller through real compilation, execution, qualification and blind joins; no providers."""
import json
import os
import shutil
import copy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.orc_structural_search import adaptive, campaign, judging
from experiments.orc_structural_search.records import read_records
from tests.experiments.orc_structural_search_support import world, synthetic_receipts  # noqa: F401
from tests.experiments.test_orc_structural_search_driver import sandboxed, CONFIG, ANSWERS  # noqa: F401
from tests.experiments.qualification_support import qualified_v2, sha, write
from tests.experiments.test_orc_structural_search_adaptive import UPSTREAM

TERRA = 'gpt-5.6-terra'


def require_controller():
    assert callable(getattr(adaptive, 'run_campaign', None)), 'C1 run_campaign controller is missing'


def scorer(log, invalid=False):
    from tests.experiments.compare_harness_support import write_memo
    def score(pool, judge, script='score'):
        (pool / 'records/judges' / judge / 'calls').mkdir(parents=True, exist_ok=True)
        mapping = json.loads((pool / 'records/mapping.json').read_text())
        inputs = json.loads((pool / 'records' / f'score-inputs-{judge}.json').read_text())
        roots = {str(Path(row['records_dir']).resolve()): row['candidate_root']
                 for row in read_records(log) if row['kind'] == 'evaluation'}
        criteria = mapping['rubric']['criteria']
        def rating(path):
            clone = mapping['clones'][Path(path).name]
            if clone['arm'] == 'anchor':
                role = clone['labels'][0].rsplit('-', 1)[-1]
                value = {'upstream': 8, 'partial': 5, 'mutant': 5, 'stub': 0}[role]
                if invalid and pool.parent.name == 'gen-1' and role == 'upstream':
                    value = 0
            else:
                source = ''.join(p.read_text() for p in Path(roots[clone['run']]).glob('*.orc'))
                value = 7 if 'check-c' in source else 5
            return {'clone': path, 'reason': 'synthetic', **{
                key: f'S{min(2, max(0, value - index * 2))}' for index, key in enumerate(criteria)}}
        state = pool / 'judges' / mapping['judges'][judge]['dir'] / 'state'
        (state / 'r1').mkdir(parents=True, exist_ok=True)
        (state / 'r1/run.json').write_text(json.dumps({'bound_inputs': inputs}))
        write_memo({'state_root': state}, [], [[rating(path) for path in batch['clones']]
                                              for batch in inputs['batches']])
    return score


@pytest.fixture
def setup(world, monkeypatch, synthetic_receipts, request):
    require_controller()
    validation, sealed = world.tmp / 'validation', world.tmp / 'sealed'
    tasks = [world.task]
    if getattr(request, 'param', None) == 'two_tasks':
        second = world.tmp / 'task-2'
        shutil.copytree(world.task, second)
        shutil.rmtree(second / 'anchors', ignore_errors=True)
        tasks.append(second)
    for task in (*tasks, validation, sealed):
        if task in (validation, sealed):
            shutil.copytree(world.task, task)
            (task / 'task.txt').write_text(task.name + ' task')
        (task / 'anchors').mkdir(exist_ok=True)
        for role in ('upstream', 'partial', 'mutant', 'stub'):
            (task / 'anchors' / f'{task.name}-{role}.diff').write_text(UPSTREAM if role != 'stub' else '')
    mutator = world.outside / 'mutator.py'
    from tests.experiments.orc_structural_search_support import MUTATOR_STEPPING_STONE
    mutator.write_text(MUTATOR_STEPPING_STONE)
    agent = ['codex', '--model', TERRA]
    executable = world.fakebin / 'codex'
    executable.write_text(executable.read_text().replace('prompt = sys.stdin.read()',
        'prompt = sys.stdin.read()\nif prompt.startswith("# Episode"):\n'
        '    exec(open(os.environ["SCRIPTED_MUTATOR_FILE"]).read())\n    sys.exit(0)'))
    q = qualified_v2(world.tmp / 'q', runtime=world.runtime, tasks=tasks, validation=validation,
        sealed=sealed, per_call_timeout_sec=5400,
        envelope={'episode': 120, 'evaluation': 600, 'per_call_timeout_sec': 5400,
                  'concurrency': 1, 'child_planned_maximum': 4, 'wall_clock_ceiling_h': 30})
    frozen = json.loads(q.criterion.read_text())
    # Evaluation envelope must admit the capped seeds' unchanged 5400-second call ceilings.
    frozen['envelope']['evaluation'] = 14400
    import shlex
    frozen['model_policy']['mutator'] = shlex.join(agent)
    frozen['horizon']['generations'] = 2
    for declaration in frozen['campaigns']:
        declaration['run_seed'] = 3
    frozen['budget']['steps'] = {key: {'planned': 80, 'cap': 160} for key in ('P0', 'P1', 'P2', 'P3', 'P4')}
    write(q.criterion, frozen)
    config = write(world.tmp / 'campaign-config.json', CONFIG | {
        'condition': 'module', 'models': {TERRA: ['medium', 'high']},
        'per_call_timeout_sec': 5400, 'criterion_sha256': sha(q.criterion)})
    seeds = Path(__file__).resolve().parents[2] / 'experiments/orc_structural_search/seeds/capped'
    env = {**os.environ, 'PATH': f'{world.fakebin}:{os.environ["PATH"]}', 'SCRIPTED_MUTATOR_FILE': str(mutator),
           'SCRIPTED_RESULTS_FILE': str(world.results)}
    world.results.write_text(json.dumps(ANSWERS))
    store = campaign.open_store(world.outside / 'S', writer=True)
    common = dict(criterion=q.criterion, store=store, seeds=[seeds / f'{name}.orc' for name in
        ('direct', 'implement_check_diagnose_repair')], adaptive_tasks=tasks,
        validation_task=validation, sealed_task=sealed, generations=2, episodes_per_generation=4,
        run_seed=3, agent_cmd=agent, runtime=world.runtime, env=env, timeout_sec=14400,
        solutions={task.name: world.solution for task in tasks}, call_cap=160, concurrency=1,
        judges=[f'{TERRA}={q.bindings}'])
    def run(root_label, policy='mixture', **overrides):
        roots = {key: world.outside / root_label / name for key, name in
                 [('work_root', 'W'), ('evidence_root', 'E'), ('pools_root', 'P')]}
        declaration = next(row for row in frozen['campaigns'] if row['policy'] == policy)
        return adaptive.run_campaign(config, **(common | roots | {'label': declaration['label'], 'policy': policy,
            'scorer': scorer(roots['evidence_root'] / 'log.jsonl')} | overrides))
    launch = {key: common[key] for key in ('runtime', 'env', 'timeout_sec', 'solutions', 'call_cap', 'concurrency')}
    launch.update(work_root=world.outside / 'warm/W', evidence_root=world.outside / 'warm/E',
                  pools_root=world.outside / 'warm/P', holdouts=[validation, sealed], agent_cmd=agent)
    warm = adaptive.warm_start(store, q.criterion, config, seeds=common['seeds'], adaptive_tasks=tasks,
        launch=launch, judge={'criterion': q.criterion, 'judges': common['judges'],
                             'scorer': scorer(launch['evidence_root'] / 'log.jsonl')})
    yield SimpleNamespace(world=world, q=q, config=config, frozen=frozen, store=store, common=common,
                          run=run, warm=warm, launch=launch, mutator=mutator)
    store.close()


def episodes(s, label):
    return [r for r in read_records(s.world.outside / label / 'E/log.jsonl') if r['kind'] == 'episode']


def test_check_campaign_refuses_an_unadmitted_model_a_legacy_condition_an_unknown_policy_and_a_missing_frozen_field(setup):
    s = setup
    with pytest.raises(ValueError, match='concurrency'):
        adaptive.warm_start(s.store, s.q.criterion, s.config, seeds=s.common['seeds'],
            adaptive_tasks=s.common['adaptive_tasks'], launch=s.launch | {'concurrency': 2},
            judge={'criterion': s.q.criterion, 'judges': s.common['judges']})
    base = json.loads(s.config.read_text())
    for key, value in [('models', {'unknown': ['medium']}), ('condition', 'topology-only'),
                       ('entry_workflow', 'other::run'), ('source_root', 'elsewhere'),
                       ('providers_file', 'other.json'), ('command_boundaries_file', None),
                       ('mutable_files', ['other.orc']), ('mutable_definitions', ['other']), ('interface', 'I2')]:
        write(s.config, base | {key: value})
        with pytest.raises(ValueError):
            adaptive.check_campaign(s.config, s.q.criterion, agent_cmd=s.common['agent_cmd'],
                timeout_sec=14400, policy='mixture', runtime=s.world.runtime)
    write(s.config, base)
    with pytest.raises(ValueError):
        adaptive.check_campaign(s.config, s.q.criterion, agent_cmd=s.common['agent_cmd'],
            timeout_sec=14400, policy='unknown', runtime=s.world.runtime)
    frozen = dict(s.frozen)
    del frozen['stop_rules']
    write(s.q.criterion, frozen)
    with pytest.raises(ValueError):
        adaptive.check_campaign(s.config, s.q.criterion, agent_cmd=s.common['agent_cmd'],
            timeout_sec=14400, policy='mixture', runtime=s.world.runtime)


def test_warm_start_runs_once_per_context_and_both_campaigns_record_the_same_initial_evidence(setup):
    s = setup
    with pytest.raises(ValueError, match='warm'):
        adaptive.warm_start(s.store, s.q.criterion, s.config, seeds=s.common['seeds'],
            adaptive_tasks=s.common['adaptive_tasks'], launch=s.launch,
            judge={'criterion': s.q.criterion, 'judges': s.common['judges']})
    s.run('frontier', 'frontier_only', generations=0)
    s.run('mixture', generations=0)
    rows = [r for r in s.store.rows('campaign') if r['policy'] != campaign.WARM_START]
    assert rows[0]['warm_start'] == rows[1]['warm_start']
    assert rows[0]['budget']['warm_start'] == rows[1]['budget']['warm_start']
    assert len(s.store.rows('trial')) == 4


def test_stepping_stone_reaches_c_only_through_the_mixture_and_b_stays_off_the_frontier(sandboxed, setup):
    s = setup
    frontier, mixture = s.run('frontier', 'frontier_only'), s.run('mixture')
    assert max(r['quality'] for r in frontier['table'].values()) == 5
    assert max(r['quality'] for r in mixture['table'].values()) == 7
    c = next(r for r in episodes(s, 'mixture') if r.get('parent_source') == 'reservoir' and r['generation'] == 2)
    assert any(r['kind'] == 'evaluation' and r['candidate_id'] == c['parent_candidate_id']
               for r in read_records(s.world.outside / 'mixture/E/log.jsonl'))
    assert all(c['parent_candidate_id'] not in snapshot['frontier'] for snapshot in mixture['trajectory'])
    assert c['candidate_id'] in mixture['frontier']
    assert frontier['parameters']['horizon'] == mixture['parameters']['horizon']


def test_two_interleaved_campaigns_under_one_criterion_never_see_each_others_children(sandboxed, setup):
    s = setup
    first = s.run('frontier', 'frontier_only', generations=1)
    other = s.run('mixture', generations=1)
    first = s.run('frontier', 'frontier_only', continue_run=True)
    other = s.run('mixture', continue_run=True)
    mine = {r['candidate_id'] for r in episodes(s, 'frontier')}
    theirs = {r['candidate_id'] for r in episodes(s, 'mixture')} - mine
    assert not theirs.intersection(first['table'])
    for row in episodes(s, 'frontier'):
        assert not theirs.intersection(r['candidate_id'] for r in row['feedback']['evaluated_structures'])
    shared = {t['candidate_id'] for t in s.store.rows('trial') if t['campaign_id'] == s.warm['campaign_id']}
    assert all(first['table'][cid] == other['table'][cid] for cid in shared)


@pytest.mark.parametrize('deaf,expected', [(False, 2), (True, 1)])
def test_same_idea_children_are_revisits_that_are_logged_not_evaluated_and_futility_stops_the_deaf_mutator(sandboxed, setup, deaf, expected):
    s = setup
    from tests.experiments.orc_structural_search_support import MUTATOR_SAME_IDEA
    source = MUTATOR_SAME_IDEA.replace('import sys\n', "import sys\nsys.argv.append('--deaf')\n") if deaf else MUTATOR_SAME_IDEA
    s.mutator.write_text(source)
    result = s.run('same')
    rows = read_records(s.world.outside / 'same/E/log.jsonl')
    assert result['stopped'] == 'futility'
    assert sum(r['kind'] == 'revisit' for r in rows) >= 4
    evaluated = {r['candidate_id'] for r in rows if r['kind'] == 'evaluation'}
    assert len(evaluated) == expected


def test_a_child_above_the_planned_maximum_ceiling_is_rejected_and_never_evaluated(sandboxed, setup):
    s = setup
    s.mutator.write_text(s.mutator.read_text().replace('range(2)', 'range(5)'))
    result = s.run('ceiling')
    rows = read_records(s.world.outside / 'ceiling/E/log.jsonl')
    assert any(r.get('reason') == 'planned_maximum_exceeded' for r in rows)
    assert not any(r['kind'] == 'evaluation' for r in rows)


def test_resume_continues_the_same_draws_and_adds_no_trial(sandboxed, setup):
    s = setup
    s.run('resume', generations=1)
    original_trials = {r['trial_id'] for r in s.store.rows('trial')}
    before = len(original_trials)
    result = s.run('resume', continue_run=True)
    count = len(s.store.rows('trial'))
    again = s.run('resume', continue_run=True)
    assert count > before and len(s.store.rows('trial')) == count
    assert result['frontier'] == again['frontier']
    assert result['ingestion_position'] > 0
    assert original_trials <= {r['trial_id'] for r in s.store.rows('trial')}
    other = campaign.open_store(s.world.outside / 'uninterrupted-S', writer=True)
    launch = s.launch | {'work_root': s.world.outside / 'uninterrupted-warm/W',
        'evidence_root': s.world.outside / 'uninterrupted-warm/E', 'pools_root': s.world.outside / 'uninterrupted-warm/P'}
    try:
        adaptive.warm_start(other, s.q.criterion, s.config, seeds=s.common['seeds'], adaptive_tasks=s.common['adaptive_tasks'],
            launch=launch, judge={'criterion': s.q.criterion, 'judges': s.common['judges'],
                'scorer': scorer(launch['evidence_root'] / 'log.jsonl')})
        s.run('uninterrupted', store=other)
    finally:
        other.close()
    logs = [read_records(s.world.outside / name / 'E/log.jsonl') for name in ('resume', 'uninterrupted')]
    decisions = [[(r['parent_candidate_id'], r['parent_source']) for r in rows if r['kind'] == 'parent_decision'] for rows in logs]
    assert decisions[0] == decisions[1]
    assert {r['evaluation_id'] for r in logs[0] if r['kind'] == 'evaluation'} == {
        r['evaluation_id'] for r in logs[1] if r['kind'] == 'evaluation'}
    with pytest.raises(ValueError):
        s.run('resume', continue_run=True, run_seed=99)


@pytest.mark.parametrize('before_checkpoint', [False, True])
def test_mid_generation_kill_resumes_without_repeating_settled_work(sandboxed, setup, monkeypatch, before_checkpoint):
    s = setup
    original = campaign.write_checkpoint
    def kill(store, cid, state):
        rows = read_records(s.world.outside / 'kill/E/log.jsonl')
        should_kill = state.get('generation') == 1 and sum(r['kind'] == 'episode' for r in rows) == (1 if before_checkpoint else 2) and any(
                r['kind'] == 'evaluation' for r in rows)
        if should_kill and before_checkpoint:
            raise KeyboardInterrupt
        path = original(store, cid, state)
        if should_kill:
            raise KeyboardInterrupt
        return path
    monkeypatch.setattr(campaign, 'write_checkpoint', kill)
    with pytest.raises(KeyboardInterrupt):
        s.run('kill')
    rows = read_records(s.world.outside / 'kill/E/log.jsonl')
    settled = {r['evaluation_id'] for r in rows if r['kind'] == 'evaluation'}
    decisions = [r for r in rows if r['kind'] == 'parent_decision']
    assert len([r for r in rows if r['kind'] == 'episode']) == (1 if before_checkpoint else 2) and len(settled) == 1
    monkeypatch.setattr(campaign, 'write_checkpoint', original)
    result = s.run('kill', continue_run=True)
    rows = read_records(s.world.outside / 'kill/E/log.jsonl')
    assert all(sum(r.get('evaluation_id') == eid for r in rows) == 1 for eid in settled)
    assert [r for r in rows if r['kind'] == 'parent_decision'][:len(decisions)] == decisions
    assert [r['episode_index'] for r in rows if r['kind'] == 'episode'] == list(range(len(episodes(s, 'kill'))))
    assert result['stopped'] in ('horizon', 'futility')


def test_a_generation_pool_failing_calibration_invalidates_its_assessments_and_stops_the_campaign(sandboxed, setup, monkeypatch):
    s = setup
    rebuilds, original = [], campaign.rebuild
    def rebuild(*args, **kwargs):
        rebuilds.append(kwargs['generation'])
        return original(*args, **kwargs)
    monkeypatch.setattr(campaign, 'rebuild', rebuild)
    result = s.run('invalid', scorer=scorer(s.world.outside / 'invalid/E/log.jsonl', invalid=True))
    assert rebuilds == [0]
    assert result['stopped'] == 'invalid_evidence'
    assert any(r['disposition'] == 'invalidated' for r in s.store.rows('disposition'))
    assert all(row['quality'] != 7 for row in result['table'].values())


def test_validation_and_sealed_tasks_are_holdouts_of_every_scan_and_in_no_brief_or_job(sandboxed, setup, monkeypatch):
    s = setup
    from experiments.compare import prepare
    seen, original = [], prepare.scan
    def trace(*args, **kwargs):
        seen.append(kwargs.get('roots', ()))
        return original(*args, **kwargs)
    monkeypatch.setattr(prepare, 'scan', trace)
    s.run('holdouts', generations=1)
    rows = read_records(s.world.outside / 'holdouts/E/log.jsonl')
    assert {r['task_id'] for r in rows if r['kind'] == 'evaluation'} == {s.world.task.name}
    assert all(str(s.q.validation) not in json.dumps(r.get('feedback')) for r in episodes(s, 'holdouts'))
    assert all(str(s.q.sealed) not in json.dumps(r.get('feedback')) for r in episodes(s, 'holdouts'))
    assert seen and all({s.q.validation, s.q.sealed} <= {Path(path) for _, path in roots} for roots in seen)


def test_the_store_root_is_masked_from_every_episode_and_scan_detected(sandboxed, setup):
    s = setup
    candidate = next((s.store.root / 'candidates').glob('*/direct.orc'))
    attempt = f'''from pathlib import Path
for name in [{str(s.store.root / 'evidence.jsonl')!r}, {str(candidate)!r}]:
    try:
        print('LEAK', Path(name).read_text())
    except OSError:
        print('MASKED')
print({str(s.store.root)!r})
'''
    s.mutator.write_text(attempt + s.mutator.read_text())
    result = s.run('masked', generations=1)
    assert result['stopped'] == 'invalid_evidence'
    for row in episodes(s, 'masked'):
        assert str(s.store.root) in row['hidden_roots']
        assert Path(row['records_dir']).is_dir()
        output = ''.join(p.read_text() for p in Path(row['records_dir']).glob('calls/*/stdout.txt'))
        assert 'MASKED' in output and 'LEAK' not in output
        record = json.loads((Path(row['records_dir']) / 'record.json').read_text())
        assert any(hit['pattern'] == 'archive' for hit in record['scan']['hits'])


def test_cap_refusal_and_wall_clock_ceiling_leave_the_log_checkpoint_and_store_consistent(sandboxed, setup):
    s = setup
    with pytest.raises(ValueError, match='cap|frozen'):
        s.run('cap', call_cap=1)
    result = s.run('clock', generations=0)
    state = campaign.read_checkpoint(s.store, result['campaign_id'])
    state['started_at'] = 0
    campaign.write_checkpoint(s.store, result['campaign_id'], state)
    result = s.run('clock', continue_run=True)
    assert result['stopped'] == 'wall_clock_ceiling'


def test_run_mode2_still_refuses_fresh_adaptive_work(tmp_path):
    from tests.experiments.test_orc_structural_search_adaptive import refused_mode2
    with pytest.raises(ValueError):
        refused_mode2(tmp_path)


@pytest.mark.parametrize('change', ['unknown', 'argv', 'missing', 'wrong-count'])
def test_actual_model_proof_requires_physical_coverage_and_native_turn_context(tmp_path, synthetic_receipts, change):
    from experiments.orc_structural_search.call_identity import require_campaign_models
    (tmp_path / 'calls/1').mkdir(parents=True)
    receipt = synthetic_receipts(tmp_path)
    row = {'records_dir': str(tmp_path), 'provider_calls': 1, **receipt}
    valid = copy.deepcopy(row)
    require_campaign_models(valid, [TERRA])
    usage = row['receipt_usage'][0]['usage'][0]
    if change == 'unknown':
        usage['model'] = 'unknown'
    elif change == 'argv':
        usage['provenance']['model_source'] = 'shim.argv'
    elif change == 'missing':
        usage['provenance'] = {}
    else:
        row.update(provider_calls=0, receipt_usage=[])
    with pytest.raises(ValueError, match='model identity'):
        require_campaign_models(row, [TERRA])


@pytest.mark.parametrize('quota,reason,attempts', [(True, 'quota_exhaustion', 4), (False, 'persistent_infrastructure', 3)])
def test_quota_and_three_consecutive_infrastructure_incidents_stop_without_child_evaluations(sandboxed, setup, monkeypatch, quota, reason, attempts):
    s = setup
    from experiments.orc_structural_search.quota import campaign_guard
    from tests.experiments.test_orc_structural_search_quota import FakeClock
    clock = FakeClock()
    monkeypatch.setattr(adaptive, 'campaign_guard', lambda state, save, lock:
        campaign_guard(state, save, lock, clock=lambda: clock.now, sleep=clock.sleep))
    s.mutator.write_text(('print("rate limit reached")\n' if quota else '') + 'raise SystemExit(1)\n')
    result = s.run('incident')
    assert result['stopped'] == reason
    assert len(episodes(s, 'incident')) == attempts
    assert len(clock.slept) == (3 if quota else 0)
    s.run('incident', continue_run=True)
    assert len(episodes(s, 'incident')) == attempts


def test_two_total_judge_incidents_stop_the_campaign_and_keep_saved_receipts(sandboxed, setup):
    s = setup
    from tests.experiments.orc_structural_search_support import MUTATOR_SAME_IDEA
    marker = "if '--same-idea-new-skeleton' in sys.argv:"
    source = MUTATOR_SAME_IDEA.replace(marker,
        "index = int(brief.splitlines()[0].split()[-1]) + 1\ncondition = '(or true ' + '(not ' * index + 'false' + ')' * index + ')'\n" + marker)
    s.mutator.write_text(source)
    def fail(pool, name, script='score'):
        (pool / 'records/judges' / name / 'calls').mkdir(parents=True, exist_ok=True)
        raise subprocess.CalledProcessError(1, 'scripted judge')
    result = s.run('judges', scorer=fail)
    assert result['stopped'] == 'judge_incidents' and result['judge_incidents'] == 2, result.get('stop_detail')
    assert len(list((s.world.outside / 'judges/P').glob('gen-*/task-1/records/judges/*/record.json'))) == 2


def cli_args(s, name, store):
    import shlex
    base = s.world.outside / name
    argv = []
    for key, value in {'config': s.config, 'criterion': s.q.criterion, 'store': store,
        'work-root': base / 'W', 'evidence': base / 'E', 'pools-root': base / 'P',
        'runtime': s.world.runtime, 'validation-task': s.q.validation, 'sealed-task': s.q.sealed,
        'agent-cmd': shlex.join(s.common['agent_cmd']), 'eval-timeout-sec': 14400,
        'call-cap': 160, 'concurrency': 1, 'solution': f'{s.world.task.name}={s.world.solution}',
        'judge': s.common['judges'][0]}.items():
        argv += ['--' + key, str(value)]
    return argv + ['--tasks', str(s.world.task), '--seeds', *map(str, s.common['seeds'])]


def test_public_cli_warm_start_and_run_use_real_qualification_runtime_and_clone_joins(sandboxed, setup, monkeypatch):
    s = setup
    for key, value in s.common['env'].items():
        monkeypatch.setenv(key, value)
    def dispatch(pool, name, script='score', **_kwargs):
        return scorer(pool.parents[2] / 'E/log.jsonl')(pool, name, script)
    monkeypatch.setattr(judging, 'run_judge', dispatch)
    store_path = s.world.outside / 'CLI-S'
    campaign.main(['warm-start', *cli_args(s, 'cli-warm', store_path)])
    campaign.main(['run', *cli_args(s, 'cli-run', store_path), '--label', 'c1-mixture', '--policy', 'mixture',
        '--generations', '1', '--episodes-per-generation', '4', '--run-seed', '3'])
    with_read = campaign.open_store(store_path, writer=False)
    try:
        own = next(r for r in with_read.rows('campaign') if r['policy'] == 'mixture')
        state = campaign.read_checkpoint(with_read, own['campaign_id'])
        assert state['completed_generation'] == 1 and state['trajectory'][0]['generation'] == 0
        assert own['budget']['warm_start']['metered_cost'] > 0
        assert with_read.rows('assessment') and all(r['clone_ids'] for r in with_read.rows('assessment'))
    finally:
        with_read.close()


def test_partial_warm_start_resumes_exact_original_trials_and_completed_warm_stays_closed(sandboxed, setup, monkeypatch):
    s = setup
    store = campaign.open_store(s.world.outside / 'partial-S', writer=True)
    launch = s.launch | {'work_root': s.world.outside / 'partial/W', 'evidence_root': s.world.outside / 'partial/E',
                         'pools_root': s.world.outside / 'partial/P'}
    judge = {'criterion': s.q.criterion, 'judges': s.common['judges'],
             'scorer': scorer(launch['evidence_root'] / 'log.jsonl')}
    original = campaign.write_checkpoint
    def kill(target, cid, state):
        path = original(target, cid, state)
        if target is store and state['ingestion_position']:
            raise KeyboardInterrupt
        return path
    monkeypatch.setattr(campaign, 'write_checkpoint', kill)
    try:
        with pytest.raises(KeyboardInterrupt):
            adaptive.warm_start(store, s.q.criterion, s.config, seeds=s.common['seeds'],
                adaptive_tasks=s.common['adaptive_tasks'], launch=launch, judge=judge)
        before = {t['trial_id'] for t in store.rows('trial')}
        monkeypatch.setattr(campaign, 'write_checkpoint', original)
        result = adaptive.warm_start(store, s.q.criterion, s.config, seeds=s.common['seeds'],
            adaptive_tasks=s.common['adaptive_tasks'], launch=launch | {'resume': True}, judge=judge)
        assert before <= {t['trial_id'] for t in store.rows('trial')} and len(store.rows('trial')) == 4
        assert campaign.read_checkpoint(store, result['campaign_id'])['stopped'] == 'complete'
        with pytest.raises(ValueError, match='incomplete'):
            adaptive.warm_start(store, s.q.criterion, s.config, seeds=s.common['seeds'],
                adaptive_tasks=s.common['adaptive_tasks'], launch=launch | {'resume': True}, judge=judge)
    finally:
        store.close()


def test_an_unlogged_paid_episode_is_recovered_without_repeating_its_draw(sandboxed, setup, monkeypatch):
    s = setup
    original = adaptive.driver.append_record
    paid = []
    def kill(path, row):
        if row['kind'] == 'episode':
            paid.append(row)
            raise KeyboardInterrupt
        return original(path, row)
    monkeypatch.setattr(adaptive.driver, 'append_record', kill)
    with pytest.raises(KeyboardInterrupt):
        s.run('unlogged')
    assert len(paid) == 1
    monkeypatch.setattr(adaptive.driver, 'append_record', original)
    result = s.run('unlogged', continue_run=True)
    rows = episodes(s, 'unlogged')
    assert rows[0]['episode_id'] == paid[0]['episode_id']
    assert rows[0]['outcome'] == 'incident' and rows[0]['provider_calls'] == paid[0]['provider_calls']
    assert len({r['episode_id'] for r in rows}) == len(rows)
    assert result['stopped'] != 'invalid_evidence', result.get('stop_detail')


def test_a_child_with_proven_zero_actual_calls_can_be_evaluated(sandboxed, setup):
    s = setup
    # A zero-call candidate still has a completed execution and an actual empty calls directory.
    from tests.experiments.orc_structural_search_support import MUTATOR_SAME_IDEA
    s.mutator.write_text(MUTATOR_SAME_IDEA.replace("condition = 'true'", "condition = 'false'"))
    result = s.run('zero')
    rows = read_records(s.world.outside / 'zero/E/log.jsonl')
    zero = [r for r in rows if r['kind'] == 'evaluation' and r['provider_calls'] == 0]
    assert zero and all(r['receipt_usage'] == [] and (Path(r['records_dir']) / 'calls').is_dir() for r in zero)
    assert result['stopped'] != 'invalid_evidence', result.get('stop_detail')


def test_resume_refuses_a_missing_append_only_log(tmp_path):
    from experiments.orc_structural_search.records import prepare_log
    with pytest.raises(ValueError, match='missing'):
        prepare_log(tmp_path, True)
    assert not (tmp_path / 'log.jsonl').exists()


def test_unregistered_label_policy_seed_is_refused_before_any_campaign_effect(setup):
    s = setup
    before = (s.store.root / 'evidence.jsonl').read_bytes()
    for label, policy, seed in [('foreign', 'mixture', 3), ('c1-mixture', 'frontier_only', 3), ('c1-mixture', 'mixture', 99)]:
        with pytest.raises(ValueError, match='preregistered'):
            s.run('undeclared', policy, label=label, run_seed=seed, generations=0)
        assert not (s.world.outside / 'undeclared').exists()
        assert (s.store.root / 'evidence.jsonl').read_bytes() == before


def test_judge_retry_cannot_spend_past_the_last_available_call(sandboxed, setup):
    from experiments.orc_structural_search import scoring, ledger
    s = setup
    pool = scoring.pool_evaluations(s.launch['evidence_root'], s.world.task, out=s.world.outside / 'cap-P',
        judges=s.common['judges'], criterion=s.q.criterion, include=lambda row: True)
    evidence = s.world.outside / 'cap-E'
    evidence.mkdir()
    (evidence / ledger.LEDGER).write_text(json.dumps([{'kind': 'evaluation', 'key': 'prior', 'planned': 159, 'calls': 159}]))
    dispatches = []
    def failed(pool, name, script):
        dispatches.append(script)
        root = pool / 'records/judges' / name / 'calls'
        call = root / str(len(list(root.glob('*'))) + 1)
        call.mkdir(parents=True)
        (call / 'prompt.txt').write_text('scripted judge attempt')
        raise subprocess.CalledProcessError(1, 'scripted judge')
    with pytest.raises(ledger.CallCapExceeded):
        judging.score_pool(evidence, pool, 'last call', names=[TERRA], solution=s.world.solution,
            call_cap=160, scorer=failed, criterion=s.q.criterion, resume=True)
    assert dispatches == ['score']
    assert ledger.total(ledger._read(evidence / ledger.LEDGER)) == 160
    saved = json.loads((pool / 'records/judges' / TERRA / 'record.json').read_text())
    assert saved['provider_calls'] == 1 and len(saved['receipt_usage']) == 1


@pytest.mark.parametrize('setup', ['two_tasks'], indirect=True)
def test_bad_pool_stops_before_a_later_judge_incident_and_cannot_value_a_sibling(sandboxed, setup):
    s = setup
    calls = []
    underlying = scorer(s.world.outside / 'bad-first/E/log.jsonl', invalid=True)
    def score(pool, name, script='score'):
        calls.append(pool.name)
        if pool.name == 'task-2':
            (pool / 'records/judges' / name / 'calls').mkdir(parents=True, exist_ok=True)
            raise subprocess.CalledProcessError(1, 'scripted later judge incident')
        underlying(pool, name, script)
    result = s.run('bad-first', scorer=score, generations=1)
    assert result['stopped'] == 'invalid_evidence'
    assert calls == ['task-1']
    own = [r for r in s.store.rows('trial') if r['campaign_id'] == result['campaign_id']]
    assert own and not any(a['trial_id'] in {r['trial_id'] for r in own} for a in s.store.rows('assessment'))
    sibling = s.run('sibling', 'frontier_only', generations=0)
    subjects = campaign.campaign_candidates(s.store, result['campaign_id'])
    bad = subjects[own[0]['candidate_id']]
    from experiments.orc_structural_search.config import load_config
    adaptive.register(s.store, Path(bad['source']), adaptive.subject_config(bad, load_config(s.config)),
        s.world.runtime, sibling['campaign_id'], bad['parent'])
    observed = campaign.evidence(s.store, bad['candidate_id'], s.warm['context_key'],
        tasks=s.frozen['tasks'], price_table=s.frozen['price_table'], min_trials=1)
    assert observed['kind'] == 'unobserved'
    assert observed['disposed'] == sum(r['candidate_id'] == bad['candidate_id'] for r in own)
