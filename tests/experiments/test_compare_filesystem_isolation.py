"""Positive filesystem grants with real Bubblewrap and inert provider executables."""

import json
import os
import shlex
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.experiments.compare_harness_support import call, git, skip_without_sandbox, start, world  # noqa: F401
from tests.experiments.orc_structural_search_support import world as structural_world  # noqa: F401
from tests.experiments.test_orc_structural_search_scoring import evaluations as structural_evaluations  # noqa: F401

skip_without_sandbox()


def test_agent_cannot_read_an_undeclared_checkout_or_peer_session(world):
    _, record = start(world, 'direct_task')
    foreign = world.outside / 'unlisted-checkout/source.txt'
    peer = world.outside / 'peer-home/.codex/sessions/foreign.jsonl'
    for path in (foreign, peer):
        path.parent.mkdir(parents=True)
        path.write_text('harmless foreign sentinel\n')
    script = '\n'.join([
        'printf own-candidate > own-marker',
        f'ln -s {shlex.quote(str(foreign))} escape-link',
        *[f'test ! -r {shlex.quote(str(path))} || exit 91' for path in (foreign, peer, Path('/etc/hostname'))],
        'test ! -r escape-link || exit 92',
        'test "$(cat own-marker)" = own-candidate',
    ])
    done = call(world, record, script, binary='codex')
    assert done.returncode == 0, done.stdout + done.stderr
    assert (Path(record['cwd']) / 'own-marker').read_text() == 'own-candidate'


def test_prepared_private_home_is_outside_candidate_and_records_and_stable_on_resume(world):
    records, record = start(world, 'direct_task')
    home = Path(record['sandbox']['home'])
    assert home.is_dir() and home.stat().st_mode & 0o777 == 0o700
    assert not home.is_relative_to(record['tree']) and not home.is_relative_to(records)
    assert (home / '.codex/config.toml').is_file()
    assert (home / '.codex/skills/tmux/SKILL.md').is_file()
    resume = (records / 'resume.sh').read_text()
    assert record['sandbox']['declaration'] in resume
    assert json.loads(Path(record['sandbox']['declaration']).read_text())['home'] == str(home)
    refreshed = home / '.codex/auth.json'
    refreshed.write_text('{"synthetic_refresh":2}\n')
    refreshed.chmod(0o600)
    done = call(world, record, 'test -r "$HOME/.codex/auth.json"', binary='codex')
    assert done.returncode == 0, done.stdout + done.stderr
    assert json.loads(refreshed.read_text()) == {'synthetic_refresh': 2}


def test_missing_new_home_lineage_refuses_instead_of_using_ambient_home(world):
    from experiments.compare import sandbox

    metadata = {'tree': str(world.outside / 'tree'), 'sandbox': {'home_path': str(world.outside / 'host-home')}}
    try:
        sandbox.session_home(metadata)
    except (ValueError, SystemExit) as error:
        assert 'home' in str(error).lower()
    else:
        raise AssertionError('new sandbox metadata without a private home was accepted')


def test_new_home_cannot_be_overridden_or_downgraded_to_historical_metadata(world):
    from experiments.compare import sandbox

    _, record = start(world, 'direct_task')
    expected = Path(record['sandbox']['home'])
    assert sandbox.session_home(record) == expected
    with pytest.raises(ValueError, match='cannot be overridden'):
        sandbox.session_home(record, world.outside / 'other-home')
    del record['sandbox']
    with pytest.raises(ValueError, match='lost.*lineage'):
        sandbox.session_home(record)


def test_historical_records_keep_the_explicit_original_home(tmp_path):
    from experiments.compare import sandbox

    original = tmp_path / 'recorded-original-home'
    assert sandbox.session_home({'tree': '/historical/tree'}, original) == original


def test_private_auth_is_copied_once_and_native_atomic_refresh_survives_next_call(world):
    source = world.empty_home / '.codex/auth.json'
    source.parent.mkdir()
    source.write_text('{"synthetic_generation":1}\n')
    source.chmod(0o600)
    _, record = start(world, 'direct_task')
    private = Path(record['sandbox']['home']) / '.codex/auth.json'
    assert private.read_bytes() == source.read_bytes()
    script = '''python3 - <<'PY'
import os
from pathlib import Path
path = Path.home() / '.codex/auth.json'
temporary = path.with_suffix('.refresh')
temporary.write_text('{"synthetic_generation":2}\\n')
temporary.chmod(0o600)
os.replace(temporary, path)
PY
'''
    done = call(world, record, script, binary='codex')
    assert done.returncode == 0, done.stdout + done.stderr
    source.write_text('{"synthetic_generation":3}\n')
    done = call(world, record, 'test -r "$HOME/.codex/auth.json"', binary='codex')
    assert done.returncode == 0, done.stdout + done.stderr
    assert json.loads(private.read_text()) == {'synthetic_generation': 2}
    assert private.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('invalid', ['missing', 'broad', 'environment'])
def test_invalid_declared_dependencies_refuse_before_the_fake_backend(world, invalid):
    _, record = start(world, 'direct_task')
    path = Path(record['sandbox']['declaration'])
    data = json.loads(path.read_text())
    if invalid == 'missing':
        data['codex'] = str(world.outside / 'missing-codex')
    elif invalid == 'broad':
        data['readonly']['/'] = '/'
    else:
        data['environment'].append('HOME')
    path.write_text(json.dumps(data))
    marker = Path(record['cwd']) / 'backend-executed'
    done = call(world, record, 'touch backend-executed', binary='codex')
    assert done.returncode == 70, done.stdout + done.stderr
    assert not marker.exists()
    assert (Path(record['records']) / 'calls/1/stderr.txt').read_text() == done.stderr


def test_judge_sees_only_exact_readonly_clones_with_usable_git_indexes(world):
    from experiments.compare import sandbox

    _, record = start(world, 'direct_task')
    pool = world.outside / 'pool'
    clones = [pool / 'clones' / name for name in ('anonymous', 'ungranted')]
    for clone in clones:
        clone.parent.mkdir(parents=True, exist_ok=True)
        git(world.main, 'clone', '-q', '--no-hardlinks', record['cwd'], str(clone))
        (clone / 'pkg/calc.py').write_text('VALUE = "anonymous diff"\n')
    (pool / 'records').mkdir()
    mapping = pool / 'records/mapping.json'
    mapping.write_text('{"private_model_identity":"fake-only"}\n')
    tree, records = pool / 'judges/unit', pool / 'records/judges/unit'
    (tree / 'tmp').mkdir(parents=True)
    records.mkdir(parents=True)
    native = sandbox.prepare_unit(tree, records, homes=pool / '.private-homes', clones=clones[:1])
    judge = {**record, 'cwd': str(tree), 'tree': str(tree), 'records': str(records), 'sandbox': native}
    index = (clones[0] / '.git/index').read_bytes()
    script = f'''python3 - <<'PY'
import subprocess
from pathlib import Path
clone = Path({str(clones[0])!r})
assert subprocess.check_output(['git', '-C', str(clone), 'diff', '--binary'])
assert subprocess.check_output(['git', '-C', str(clone), 'status', '--porcelain'])
assert not Path({str(clones[1] / 'pkg/calc.py')!r}).exists()
assert not Path({str(mapping)!r}).exists()
try:
    (clone / 'pkg/calc.py').write_text('forbidden')
except OSError:
    pass
else:
    raise AssertionError('judge clone is writable')
PY
'''
    done = call(world, judge, script, binary='codex')
    assert done.returncode == 0, done.stdout + done.stderr
    assert (clones[0] / '.git/index').read_bytes() == index
    assert (clones[0] / 'pkg/calc.py').read_text() == 'VALUE = "anonymous diff"\n'


def external_unit(world):
    from experiments.compare.prepare import ArmSpec, run_arm

    state = world.outside / 'controller-state'
    spec = ArmSpec(world.runtime / 'workflow.orc', 'fixture::run', world.runtime,
                   world.runtime / 'providers.json', ('task',), state_dir=state)
    records = run_arm(world.task, 'external-delivery', world.root, world.runtime, spec=spec)
    record = json.loads((records / 'record.json').read_text())
    result = state / 'run/attempt/result.json'
    result.parent.mkdir(parents=True)
    result.with_name('private-sibling').write_text('controller-only sentinel\n')
    return records, record, result


@pytest.mark.parametrize('delivery', ['missing', 'empty', 'malformed', 'atomic', 'hardlink'])
def test_external_delivery_preserves_missing_bytes_and_native_atomic_writes(world, monkeypatch, delivery):
    records, record, result = external_unit(world)
    monkeypatch.setenv('ORCHESTRATOR_OUTPUT_BUNDLE_PATH', str(result))
    monkeypatch.setenv('ORCHESTRATOR_WORKSPACE_ROOT', record['cwd'])
    payload = {'empty': b'', 'malformed': b'{broken', 'atomic': b'{"ok":true}', 'hardlink': b'linked bytes'}.get(delivery)
    script = f'''python3 - <<'PY'
import os
from pathlib import Path
result = Path({str(result)!r})
assert not result.with_name('private-sibling').exists()
for item in os.listdir('/proc/self/fd'):
    try:
        target = os.readlink('/proc/self/fd/' + item)
    except OSError:
        continue
    assert int(item) < 3, (item, target)
payload = {payload!r}
if payload is not None:
    if {delivery!r} in ('atomic', 'hardlink'):
        temporary = result.with_name('native-temporary')
        temporary.write_bytes(payload)
        if {delivery!r} == 'atomic':
            os.replace(temporary, result)
        else:
            os.link(temporary, result)
    else:
        result.write_bytes(payload)
PY
'''
    done = call(world, record, script, binary='codex')
    assert done.returncode == 0, done.stdout + done.stderr
    assert result.exists() is (payload is not None)
    if payload is not None:
        assert result.read_bytes() == payload
    assert not (records / 'calls/1/publication-error.json').exists()
    assert json.loads((records / 'calls/1/native-exit.json').read_text()) == {'native_exit': 0}


@pytest.mark.parametrize('kind', ['symlink', 'fifo', 'directory'])
def test_external_nonregular_results_are_apparatus_errors_with_original_native_exit(world, monkeypatch, kind):
    from experiments.compare import scan

    records, record, result = external_unit(world)
    monkeypatch.setenv('ORCHESTRATOR_OUTPUT_BUNDLE_PATH', str(result))
    script = f'''python3 - <<'PY'
import os
from pathlib import Path
p = Path({str(result)!r})
if {kind!r} == 'symlink':
    p.symlink_to('/dev/null')
elif {kind!r} == 'fifo':
    os.mkfifo(p)
else:
    p.mkdir()
PY
exit 7
'''
    done = call(world, record, script, binary='codex')
    assert done.returncode == 70, done.stdout + done.stderr
    assert not result.exists()
    marker = json.loads((records / 'calls/1/publication-error.json').read_text())
    assert marker['native_exit'] == 7 and marker['publication_error']
    with pytest.raises(SystemExit, match='publication'):
        scan.refuse_publication_errors(records)


def test_nonzero_native_exit_keeps_exact_external_result_evidence(world, monkeypatch):
    records, record, result = external_unit(world)
    monkeypatch.setenv('ORCHESTRATOR_OUTPUT_BUNDLE_PATH', str(result))
    done = call(world, record, f'printf original-result > {shlex.quote(str(result))}; exit 7', binary='codex')
    assert done.returncode == 7, done.stdout + done.stderr
    assert result.read_bytes() == b'original-result'
    assert json.loads((records / 'calls/1/native-exit.json').read_text())['native_exit'] == 7
    assert not (records / 'calls/1/publication-error.json').exists()


@pytest.mark.parametrize('change', ['existing', 'parent', 'appeared-while-missing'])
def test_external_publication_refuses_changed_controller_authority(world, monkeypatch, change):
    records, record, result = external_unit(world)
    monkeypatch.setenv('ORCHESTRATOR_OUTPUT_BUNDLE_PATH', str(result))
    if change == 'existing':
        result.write_bytes(b'controller-existing')
        done = call(world, record, 'touch backend-executed', binary='codex')
        assert not (Path(record['cwd']) / 'backend-executed').exists()
    else:
        signal, release = (Path(record['cwd']) / name for name in ('backend-ready', 'release-backend'))
        script = f'''python3 - <<'PY'
import time
from pathlib import Path
Path('backend-ready').touch()
for _ in range(500):
    if Path('release-backend').exists():
        break
    time.sleep(.01)
else:
    raise AssertionError('controller never released fake backend')
if {change!r} == 'parent':
    Path({str(result)!r}).write_bytes(b'staged-native-output')
PY
'''
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(call, world, record, script, 'codex')
            for _ in range(500):
                if signal.exists() or future.done():
                    break
                time.sleep(.01)
            assert signal.exists(), future.result().stderr
            if change == 'parent':
                result.parent.rename(result.parent.with_name('original-parent'))
                result.parent.mkdir()
            result.write_bytes(b'controller-existing')
            release.touch()
            done = future.result(timeout=10)
    assert done.returncode == 70, done.stdout + done.stderr
    assert result.read_bytes() == b'controller-existing'
    assert (records / 'calls/1/publication-error.json').exists()


def test_external_result_parent_never_authorizes_external_native_cwd(world, monkeypatch):
    _, record, result = external_unit(world)
    monkeypatch.setenv('ORCHESTRATOR_OUTPUT_BUNDLE_PATH', str(result))
    done = call(world, {**record, 'cwd': str(result.parent)}, 'touch backend-executed', binary='codex')
    assert done.returncode == 70 and 'cwd' in done.stderr
    assert not result.with_name('backend-executed').exists()


@pytest.mark.parametrize('failure', ['initial-marker', 'remove-marker'])
def test_external_publication_marker_failures_cannot_become_natural_outcomes(world, monkeypatch, failure):
    from experiments.compare import sandbox, scan

    records, record, result = external_unit(world)
    call_dir = records / 'calls/1'
    call_dir.mkdir(parents=True)
    environment = {**os.environ, 'COMPARE_ROOT': str(records), 'COMPARE_TREE': record['tree'],
        'COMPARE_SANDBOX': record['sandbox']['declaration'], 'ORCHESTRATOR_OUTPUT_BUNDLE_PATH': str(result)}
    dispatched = []

    def native(args, **kwargs):
        dispatched.append(True)
        assert (call_dir / 'publication-error.json').is_file()
        descriptor = os.open('result.json', os.O_CREAT | os.O_WRONLY, 0o600, dir_fd=kwargs['pass_fds'][0])
        os.write(descriptor, b'published-exactly')
        os.close(descriptor)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sandbox.subprocess, 'run', native)
    monkeypatch.chdir(record['cwd'])
    if failure == 'initial-marker':
        original = Path.open

        def cannot_create(path, mode='r', *args, **kwargs):
            if path.name == 'publication-error.json' and mode == 'x':
                raise PermissionError('synthetic marker creation failure')
            return original(path, mode, *args, **kwargs)

        monkeypatch.setattr(Path, 'open', cannot_create)
        with pytest.raises(PermissionError, match='synthetic'):
            sandbox.launch('codex', ['exec'], environment, call=call_dir)
        assert not dispatched and not result.exists()
    else:
        original = Path.unlink

        def cannot_remove(path, *args, **kwargs):
            if path.name == 'publication-error.json':
                raise PermissionError('synthetic marker removal failure')
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, 'unlink', cannot_remove)
        assert sandbox.launch('codex', ['exec'], environment, call=call_dir) == 70
        assert result.read_bytes() == b'published-exactly'
        assert json.loads((call_dir / 'publication-error.json').read_text())['native_exit'] == 0
        with pytest.raises(SystemExit, match='publication'):
            scan.refuse_publication_errors(records)


def test_double_preparation_never_creates_or_copies_another_private_home(world):
    from experiments.compare import sandbox

    records, record = start(world, 'direct_task')
    homes = Path(record['sandbox']['home']).parent
    before = sorted(homes.iterdir())
    with pytest.raises(ValueError, match='already prepared'):
        sandbox.prepare_unit(Path(record['tree']), records, homes=homes)
    assert sorted(homes.iterdir()) == before


def test_late_no_claude_restriction_survives_resume_without_the_environment_flag(world, monkeypatch):
    _, record = start(world, 'direct_task')
    (world.fakebin / 'claude').write_text('#!/bin/sh\nprintf called >> "$HOME/claude-starts"\n')
    allowed = call(world, record, 'claude --model claude-sonnet-5-5 -p </dev/null', binary='codex')
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    monkeypatch.setenv('COMPARE_CLAUDE_MODELS', '')
    script = 'claude --model claude-sonnet-5-5 -p </dev/null; test "$?" = 2'
    tightened = call(world, record, script, binary='codex')
    assert tightened.returncode == 0, tightened.stdout + tightened.stderr
    monkeypatch.delenv('COMPARE_CLAUDE_MODELS')
    resumed = call(world, record, script, binary='codex')
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    assert (Path(record['sandbox']['home']) / 'claude-starts').read_text() == 'called'


def test_late_restriction_write_failure_prevents_backend_dispatch(world, monkeypatch):
    from experiments.compare import sandbox

    records, record = start(world, 'direct_task')
    declaration = Path(record['sandbox']['declaration']).read_bytes()
    call_dir = records / 'calls/1'
    call_dir.mkdir(parents=True)
    environment = {**os.environ, 'COMPARE_ROOT': str(records), 'COMPARE_TREE': record['tree'],
        'COMPARE_SANDBOX': record['sandbox']['declaration'], 'COMPARE_CLAUDE_MODELS': ''}
    dispatched = []
    monkeypatch.setattr(sandbox.subprocess, 'run', lambda *args, **kwargs: dispatched.append(args))
    original = Path.open

    def cannot_restrict(path, mode='r', *args, **kwargs):
        if path.name == 'claude-denied' and mode == 'x':
            raise PermissionError('synthetic restriction persistence failure')
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', cannot_restrict)
    with pytest.raises(PermissionError, match='synthetic'):
        sandbox.launch('codex', ['exec'], environment, call=call_dir)
    assert not dispatched
    assert Path(record['sandbox']['declaration']).read_bytes() == declaration


@pytest.mark.parametrize('consumer', ['run', 'judge'])
def test_effective_preparation_environment_selects_private_auth_and_dependencies(world, consumer):
    from experiments.compare import pool, prepare

    source = world.outside / 'selected-controller-home'
    (source / '.codex').mkdir(parents=True)
    (source / '.claude').mkdir()
    (source / '.codex/auth.json').write_text('{"synthetic_auth":"selected-private-auth"}\n')
    (source / '.claude/.credentials.json').write_text('must not project Claude\n')
    dependencies = json.loads(Path(os.environ['COMPARE_SANDBOX']).read_text())
    dependencies['environment'].append('FAKE_SELECTED_ENVIRONMENT')
    pointer = world.outside / 'selected-dependencies.json'
    pointer.write_text(json.dumps(dependencies))
    environment = {**os.environ, 'HOME': str(source), 'CODEX_HOME': str(source / '.codex'),
        'COMPARE_SANDBOX': str(pointer), 'COMPARE_CLAUDE_MODELS': ''}
    if consumer == 'run':
        records = prepare.run_arm(world.task, 'direct_task', world.root, world.runtime,
            sets=('model=gpt-5.6-luna', 'effort=high'), environment=environment)
        metadata = json.loads((records / 'record.json').read_text())['sandbox']
    else:
        out = world.outside / 'selected-pool'
        (out / 'records').mkdir(parents=True)
        mapping = {'judges': {'judge-a': {'dir': 'anonymous', 'providers': str(world.runtime / 'providers.json')}},
                   'batches': [], 'criterion_sha256': 'synthetic-only', 'compare_base': world.base}
        pool.write_score_inputs(out, mapping, 'synthetic intent', world.runtime, environment=environment)
        metadata = mapping['judges']['judge-a']['sandbox']
    home = Path(metadata['home'])
    assert json.loads((home / '.codex/auth.json').read_text()) == {'synthetic_auth': 'selected-private-auth'}
    assert not (home / '.claude/.credentials.json').exists()
    snapshot = Path(metadata['declaration']).read_text()
    assert 'FAKE_SELECTED_ENVIRONMENT' in json.loads(snapshot)['environment']
    assert 'selected-private-auth' not in snapshot
    assert os.environ['HOME'] == str(world.empty_home)


@pytest.mark.parametrize('kind', ['pending', 'malformed', 'directory', 'fifo', 'broken-symlink'])
def test_any_publication_marker_is_nonadjudicable_for_every_intake_path(world, kind):
    from experiments.compare import prepare, scan

    records, record = start(world, 'direct_task')
    call_dir = records / 'calls/1'
    call_dir.mkdir(parents=True)
    marker = call_dir / 'publication-error.json'
    if kind == 'directory':
        marker.mkdir()
    elif kind == 'fifo':
        os.mkfifo(marker)
    elif kind == 'broken-symlink':
        marker.symlink_to(call_dir / 'missing-target')
    else:
        marker.write_text('{"pending":true}' if kind == 'pending' else '{broken')
    with pytest.raises(SystemExit, match='publication'):
        prepare.paired_calls(records, [])
    with pytest.raises(SystemExit, match='publication'):
        prepare.collect(records)
    with pytest.raises(SystemExit, match='publication'):
        scan.find_hits(records, Path(record['tree']), 0, Path(record['sandbox']['home']), {})


def selected_environment(world):
    source = world.outside / 'entrypoint-controller-home'
    (source / '.codex').mkdir(parents=True)
    (source / '.claude').mkdir()
    (source / '.codex/auth.json').write_text('{"synthetic":"entrypoint-auth"}\n')
    (source / '.claude/.credentials.json').write_text('{"synthetic":"entrypoint-auth"}\n')
    dependencies = json.loads(world.sandbox_config.read_text())
    dependencies['environment'].append('FAKE_ENTRYPOINT_ENVIRONMENT')
    pointer = world.outside / 'entrypoint-dependencies.json'
    pointer.write_text(json.dumps(dependencies))
    environment = {**os.environ, 'HOME': str(source), 'CODEX_HOME': str(source / '.codex'),
        'CLAUDE_CONFIG_DIR': str(source / '.claude'), 'COMPARE_SANDBOX': str(pointer),
        'PATH': f'{world.fakebin}:{os.environ["PATH"]}'}
    environment.pop('COMPARE_CLAUDE_MODELS', None)
    return environment


def assert_selected_private_projection(metadata):
    home = Path(metadata['home'])
    credentials = [path for path in (home / '.codex/auth.json', home / '.claude/.credentials.json') if path.exists()]
    assert credentials and all(json.loads(path.read_text()) == {'synthetic': 'entrypoint-auth'} for path in credentials)
    declaration = json.loads(Path(metadata['declaration']).read_text())
    assert 'FAKE_ENTRYPOINT_ENVIRONMENT' in declaration['environment']


@pytest.mark.parametrize('codex_only', [False, True])
def test_evaluation_entrypoint_prepares_from_its_effective_environment(structural_world, codex_only):
    from experiments.orc_structural_search.evaluation import evaluate
    from tests.experiments.orc_structural_search_support import launch_config, script
    from tests.experiments.test_orc_structural_search_evaluation import CHANGE, CONFIG

    env = selected_environment(structural_world)
    env['SCRIPTED_RESULTS_FILE'] = str(structural_world.results)
    script(structural_world, [CHANGE])
    config = CONFIG
    if codex_only:
        from dataclasses import replace
        config = replace(CONFIG, models={'gpt-5.6-terra': ['medium', 'high']})
        bindings = structural_world.candidate / 'providers.json'
        value = json.loads(bindings.read_text())
        value['providers.coder'] = 'codex_unrestricted_workspace'
        value['providers.judge'] = 'claude_unrestricted_workspace'
        direct = structural_world.candidate / 'direct.orc'
        direct.write_text(direct.read_text().replace('claude-sonnet-5-5', 'gpt-5.6-terra'))
        bindings.write_text(json.dumps(value))
    result = evaluate(structural_world.candidate, launch_config(structural_world, config),
        task_package=structural_world.task, work_root=structural_world.evidence, replicate=1,
        runtime=structural_world.runtime, env=env, timeout_sec=60, criterion=structural_world.criterion)
    metadata = json.loads((result.records_dir / 'record.json').read_text())
    assert_selected_private_projection(metadata['sandbox'])
    if codex_only:
        declaration = json.loads(Path(metadata['sandbox']['declaration']).read_text())
        assert declaration['providers'] == ['codex']
        assert metadata['allowed_claude_models'] == []
        assert not (Path(metadata['sandbox']['home']) / '.claude/.credentials.json').exists()
    assert result.outcome == 'completed', [(str(path.relative_to(result.records_dir)), path.read_text())
        for path in [result.records_dir / 'launch-0.log', *result.records_dir.glob('calls/*/stderr.txt')]]
    assert os.environ['HOME'] == str(structural_world.empty_home)


def test_judge_generation_prepares_from_its_effective_environment(world, structural_evaluations):
    from experiments.orc_structural_search import judging
    from tests.experiments.test_orc_structural_search_scoring import score

    _, mapping, _, log, criterion = structural_evaluations
    environment = selected_environment(world)
    observed = []

    def scorer(pool, judge, script='score'):
        current = json.loads((pool / 'records/mapping.json').read_text())
        assert_selected_private_projection(current['judges'][judge]['sandbox'])
        observed.append(judge)
        score(pool, current, judge, world.tmp / 'historical-home')

    judges = [name + '=' + info['providers'] for name, info in mapping['judges'].items()]
    rows = judging.judge_generation(log.parent, 0, [world.task], criterion=criterion,
        judges=judges, solutions={world.task.name: world.solution}, call_cap=10,
        pool_root=world.outside / 'entrypoint-pools', scorer=scorer,
        include=lambda row: row['evaluation_id'] in ('e1', 'e2'), env=environment)
    assert observed == list(mapping['judges']) and rows
    assert os.environ['HOME'] == str(world.empty_home)


def test_unknown_dependency_fields_never_create_a_home_or_publish_values(tmp_path):
    from experiments.compare import sandbox

    records, tree = tmp_path / 'records', tmp_path / 'tree'
    records.mkdir()
    tree.mkdir()
    fake = tmp_path / 'codex'
    fake.write_text('#!/bin/sh\nexit 1\n')
    fake.chmod(0o755)
    dependencies = sandbox.dependencies({'PATH': '', 'HOME': str(tmp_path / 'empty-source-home')})
    dependencies['codex'] = str(fake)
    dependencies['unexpected_private_value'] = 'FAKE_AUTH_CANARY'
    declaration = tmp_path / 'unrecognized-dependencies.json'
    declaration.write_text(json.dumps(dependencies))
    with pytest.raises(ValueError, match='unsupported fields') as error:
        sandbox.prepare_unit(tree, records, homes=tmp_path / 'homes',
            environment={'COMPARE_SANDBOX': str(declaration), 'HOME': str(tmp_path / 'empty-source-home')})
    assert not (tmp_path / 'homes').exists()
    assert not list(records.iterdir())
    assert 'FAKE_AUTH_CANARY' not in str(error.value)


@pytest.mark.parametrize('field', ['environment', 'skills'])
@pytest.mark.parametrize('value', [{'MY_TOKEN': 'FAKE_AUTH_CANARY'}, 'FAKE_AUTH_CANARY'])
def test_dependency_lists_reject_value_containers_before_private_preparation(tmp_path, field, value):
    from experiments.compare import sandbox

    records, tree = tmp_path / 'records', tmp_path / 'tree'
    records.mkdir()
    tree.mkdir()
    dependencies = sandbox.dependencies({'PATH': '', 'HOME': str(tmp_path / 'empty-source-home')})
    dependencies[field] = value
    declaration = tmp_path / 'private-value-container.json'
    declaration.write_text(json.dumps(dependencies))
    with pytest.raises(ValueError, match='must be a list') as error:
        sandbox.prepare_unit(tree, records, homes=tmp_path / 'homes',
            environment={'COMPARE_SANDBOX': str(declaration), 'HOME': str(tmp_path / 'empty-source-home')})
    assert not (tmp_path / 'homes').exists() and not list(records.iterdir())
    assert 'FAKE_AUTH_CANARY' not in str(error.value)


def test_extern_names_cannot_grant_an_unbound_provider_or_its_credentials(world):
    from experiments.compare import sandbox

    source = world.empty_home / '.claude/.credentials.json'
    source.parent.mkdir()
    source.write_text('{"synthetic":"unneeded-Claude-auth"}\n')
    bindings = world.outside / 'codex-binding.json'
    bindings.write_text('{"providers.claude_review":"codex"}\n')
    tree, records = world.outside / 'profile-unit/tree', world.outside / 'profile-unit/records'
    (tree / 'tmp').mkdir(parents=True)
    records.mkdir(parents=True)
    metadata = sandbox.prepare_unit(tree, records, homes=world.outside / 'profile-homes', providers=bindings)
    declaration = json.loads(Path(metadata['declaration']).read_text())
    assert declaration['providers'] == ['codex']
    assert not (Path(metadata['home']) / '.claude/.credentials.json').exists()


def test_codex_only_episode_models_never_prepare_claude_state(structural_world):
    from experiments.orc_structural_search.driver import archive, run_episode
    from tests.experiments.orc_structural_search_support import launch_config
    from tests.experiments.test_orc_structural_search_driver import config_of

    source = structural_world.empty_home / '.claude/.credentials.json'
    source.parent.mkdir()
    source.write_text('{"synthetic":"unneeded-Claude-auth"}\n')
    (structural_world.fakebin / 'codex').write_text('#!/bin/sh\ncat >/dev/null\nexit 0\n')
    evidence = structural_world.tmp / 'privacy-evidence'
    _, parent = archive(structural_world.candidate, evidence, structural_world.runtime)
    environment = {**os.environ, 'PATH': f'{structural_world.fakebin}:{os.environ["PATH"]}'}
    config = launch_config(structural_world, config_of(models={'gpt-5.6-terra': ['high']}))
    row = run_episode(parent, config, interface='I1', mode='unguided',
        agent_cmd=['codex', '--model', 'gpt-5.6-terra', 'exec', '-c', 'model_reasoning_effort=high', '-'],
        work_root=structural_world.outside / 'privacy-work', evidence_root=evidence,
        episode_index=0, runtime=structural_world.runtime, env=environment,
        solutions={structural_world.task.name: structural_world.solution}, call_cap=2, criterion=structural_world.criterion)
    assert row['agent_exit'] == 0
    metadata = json.loads((Path(row['records_dir']) / 'record.json').read_text())
    declaration = json.loads(Path(metadata['sandbox']['declaration']).read_text())
    assert declaration['providers'] == ['codex']
    assert not (Path(metadata['sandbox']['home']) / '.claude/.credentials.json').exists()
