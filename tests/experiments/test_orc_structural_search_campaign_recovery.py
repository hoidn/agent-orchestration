"""Cold catalog admission and durable campaign recovery; scripted providers only."""
import shutil

import pytest

from experiments.orc_structural_search import qualification
from tests.experiments.orc_structural_search_support import world  # noqa: F401


@pytest.fixture
def catalog(world):
    source = world.runtime / 'experiments/orc_structural_search/seeds/capped'
    copied = world.tmp / 'copied-capped'
    shutil.copytree(source, copied)
    seeds = [copied / f'{name}.orc' for name in ('direct', 'implement_check_diagnose_repair')]
    validation, sealed = world.tmp / 'validation', world.tmp / 'sealed'
    frozen = {'budget': {'steps': {'P0': {'cap': 160}}}, 'envelope': {'concurrency': 1},
        'horizon': {'warm_start': {'seeds': [p.stem for p in seeds]}}, 'tasks': [str(world.task)],
        'validation_task': str(validation), 'sealed_task': str(sealed)}
    launch = {'runtime': world.runtime, 'call_cap': 160, 'concurrency': 1, 'holdouts': [validation, sealed]}
    return world, source, copied, seeds, frozen, launch


def check_catalog(data):
    world, _source, _copied, seeds, frozen, launch = data
    qualification.check_warm_inputs(frozen, seeds, [world.task], launch)


@pytest.mark.parametrize('name', ['direct.orc', 'common.orc', 'providers.json', 'commands.json', 'dev_check.py'])
def test_warm_seed_closure_is_bound_to_the_runtime_catalog_bytes(catalog, name):
    check_catalog(catalog)  # Copies of the versioned bytes remain admissible.
    path = catalog[2] / name
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='catalog'):
        check_catalog(catalog)


def test_untracked_runtime_files_cannot_redefine_the_canonical_catalog(catalog):
    (catalog[1] / 'unversioned.txt').write_text('not part of the frozen commit')
    with pytest.raises(ValueError, match='catalog'):
        check_catalog(catalog)

from experiments.orc_structural_search import adaptive, campaign, ledger
from experiments.orc_structural_search.records import read_records
from tests.experiments.test_orc_structural_search_campaign_loop import setup, episodes, scorer  # noqa: F401
from tests.experiments.test_orc_structural_search_driver import sandboxed  # noqa: F401
from tests.experiments.orc_structural_search_support import synthetic_receipts  # noqa: F401


@pytest.mark.parametrize('phase', ['pre-reserve', 'post-reserve', 'mid-copy', 'post-call', 'resettle', 'relog', 'recheckpoint', 'missing-calls'])
def test_episode_reservation_recovery_keeps_the_original_draw(sandboxed, setup, monkeypatch, phase):
    s = setup
    before = ledger.reserve
    workspace, append = adaptive.driver.episode_workspace, adaptive.driver.append_record
    captured = []
    def reserve(root, **kwargs):
        if kwargs['kind'] != 'episode':
            return before(root, **kwargs)
        captured.append(kwargs['key'])
        if phase == 'pre-reserve':
            raise KeyboardInterrupt
        slot = before(root, **kwargs)
        if phase in ('post-reserve', 'missing-calls'):
            raise KeyboardInterrupt
        return slot
    def copy(parent, tree, *args, **kwargs):
        if phase in ('mid-copy', 'resettle', 'relog', 'recheckpoint'):
            tree.mkdir(parents=True)
            (tree / 'partial').write_text('interrupted copy')
            raise KeyboardInterrupt
        return workspace(parent, tree, *args, **kwargs)
    def log(path, row):
        if phase == 'post-call' and row['kind'] == 'episode':
            raise KeyboardInterrupt
        return append(path, row)
    monkeypatch.setattr(ledger, 'reserve', reserve)
    monkeypatch.setattr(adaptive.driver, 'episode_workspace', copy)
    monkeypatch.setattr(adaptive.driver, 'append_record', log)
    with pytest.raises(KeyboardInterrupt):
        s.run('recovery')
    monkeypatch.setattr(ledger, 'reserve', before)
    monkeypatch.setattr(adaptive.driver, 'episode_workspace', workspace)
    monkeypatch.setattr(adaptive.driver, 'append_record', append)
    evidence = s.world.outside / 'recovery/E'
    if phase == 'missing-calls':
        shutil.rmtree(evidence / 'episodes' / captured[0] / 'calls')
        with pytest.raises(ValueError, match='calls'):
            s.run('recovery', continue_run=True)
        return
    if phase in ('resettle', 'relog', 'recheckpoint'):
        target, name = (ledger, 'settle_killed') if phase == 'resettle' else (adaptive, 'append_record') if phase == 'relog' else (campaign, 'write_checkpoint')
        original = getattr(target, name)
        def again(*args, **kwargs):
            result = original(*args, **kwargs)
            if phase == 'recheckpoint' and not episodes(s, 'recovery'):
                return result
            if phase != 'relog' or args[1]['kind'] == 'episode':
                raise KeyboardInterrupt
            return result
        monkeypatch.setattr(target, name, again)
        with pytest.raises(KeyboardInterrupt):
            s.run('recovery', continue_run=True)
        monkeypatch.setattr(target, name, original)
    result = s.run('recovery', continue_run=True)
    rows = episodes(s, 'recovery')
    assert rows[0]['episode_id'] == captured[0]
    assert rows[0]['outcome'] == ('accepted' if phase == 'pre-reserve' else 'incident'), rows[0]
    assert len({r['episode_id'] for r in rows}) == len(rows)
    reservations = [r for r in ledger._read(evidence / ledger.LEDGER) if r['kind'] == 'episode']
    assert len({r['key'] for r in reservations}) == len(reservations)
    assert result['stopped'] != 'invalid_evidence', result.get('stop_detail')


@pytest.mark.parametrize('where', ['log', 'checkpoint'])
def test_judge_incident_resolution_replays_before_new_work(sandboxed, setup, monkeypatch, where):
    import subprocess
    from tests.experiments.orc_structural_search_support import MUTATOR_SAME_IDEA
    s = setup
    marker = "if '--same-idea-new-skeleton' in sys.argv:"
    s.mutator.write_text(MUTATOR_SAME_IDEA.replace(marker,
        "index = int(brief.splitlines()[0].split()[-1]) + 1\ncondition = '(or true ' + '(not ' * index + 'false' + ')' * index + ')'\n" + marker))
    dispatches = []
    def fail(pool, name, script='score'):
        dispatches.append(pool.parent.name)
        (pool / 'records/judges' / name / 'calls').mkdir(parents=True, exist_ok=True)
        raise subprocess.CalledProcessError(1, 'scripted judge')
    target, name = (adaptive, 'append_record') if where == 'log' else (campaign, 'write_checkpoint')
    original = getattr(target, name)
    def kill(*args, **kwargs):
        result = original(*args, **kwargs)
        row = args[1] if where == 'log' else args[2]
        if row.get('kind') == 'judge_incident' or row.get('judge_incidents') == 1:
            raise KeyboardInterrupt
        return result
    monkeypatch.setattr(target, name, kill)
    with pytest.raises(KeyboardInterrupt):
        s.run('durable-judges', scorer=fail)
    monkeypatch.setattr(target, name, original)
    result = s.run('durable-judges', scorer=fail, continue_run=True)
    assert result['stopped'] == 'judge_incidents' and result['judge_incidents'] == 2
    assert dispatches.count('gen-1') == dispatches.count('gen-2') == 2
    log = read_records(s.world.outside / 'durable-judges/E/log.jsonl')
    assert [r['judge_incidents'] for r in log if r['kind'] == 'judge_incident'] == [1, 2]


def test_calls_without_a_reservation_are_never_recounted_as_a_new_episode(tmp_path):
    key = 'sha256:unit'
    calls = tmp_path / 'episodes' / key / 'calls'
    calls.mkdir(parents=True)
    assert ledger.episode_reservation(tmp_path, key) is None  # interrupted empty initialization
    (calls / '1').mkdir()
    with pytest.raises(ValueError, match='without reservation'):
        ledger.episode_reservation(tmp_path, key)


def test_historical_driver_module_cli_runs_a_scripted_episode(sandboxed, setup):
    import shlex
    import subprocess
    import sys
    s = setup
    base = s.world.outside / 'legacy-cli'
    args = ['--config', str(s.config), '--criterion', str(s.q.criterion),
        '--seeds', str(s.common['seeds'][0]), '--tasks', str(s.world.task),
        '--work-root', str(base / 'W'), '--evidence', str(base / 'E'), '--episodes', '1',
        '--agent-cmd', shlex.join(s.common['agent_cmd']), '--runtime', str(s.world.runtime),
        '--eval-timeout-sec', '14400', '--solution', f'{s.world.task.name}={s.world.solution}',
        '--call-cap', '160', '--concurrency', '1', '--holdout', str(s.q.validation), '--holdout', str(s.q.sealed)]
    done = subprocess.run([sys.executable, '-m', 'experiments.orc_structural_search.driver', *args],
        env=s.common['env'], text=True, capture_output=True, timeout=180)
    assert done.returncode == 0, done.stdout + done.stderr
    rows = read_records(base / 'E/log.jsonl')
    mutations = [r for r in rows if r['kind'] == 'episode']
    assert len(mutations) == 1 and mutations[0]['outcome'] == 'accepted'
    assert (base / 'E/readout.json').is_file()


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


def test_resume_refuses_a_missing_append_only_log(tmp_path):
    from experiments.orc_structural_search.records import prepare_log
    with pytest.raises(ValueError, match='missing'):
        prepare_log(tmp_path, True)
    assert not (tmp_path / 'log.jsonl').exists()
