"""Explicit no-Claude bindings isolate installed CLIs and credentials; no real providers."""
import json
import os
import shlex
import sys
from pathlib import Path

import pytest

from tests.experiments.compare_harness_support import (
    call, configure_test_sandbox, skip_without_sandbox, start, world,
)  # noqa: F401

skip_without_sandbox()


def install_fake_claude(world, monkeypatch):
    install = world.outside / 'isolated-claude'
    install.mkdir(parents=True)
    config = world.outside / 'fake-claude-config'
    config.mkdir()
    (config / '.credentials.json').write_text('fake credentials')
    for name in ('claude', 'older'):
        binary = install / name
        binary.write_text('#!/bin/sh\ntouch /tmp/claude-called\nexit 0\n')
        binary.chmod(0o755)
    marker = Path('/tmp/claude-called')
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(config))
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'fake-key')
    monkeypatch.setenv('ANTHROPIC_AUTH_TOKEN', 'fake-token')
    monkeypatch.setenv('CLAUDE_CODE_OAUTH_TOKEN', 'fake-oauth')
    return install, marker


@pytest.mark.parametrize('no_claude', [False, True])
def test_no_claude_survives_descendant_path_and_environment_reset(world, monkeypatch, no_claude):
    install, marker = install_fake_claude(world, monkeypatch)
    fake = world.fakebin / 'claude'
    fake.write_text('#!/bin/sh\ntouch /tmp/claude-called\nexit 0\n')
    fake.chmod(0o755)
    # Every executable here is a fake. Even a failing assertion cannot spend provider calls.
    if no_claude:
        monkeypatch.setenv('COMPARE_CLAUDE_MODELS', '')
    else:
        monkeypatch.delenv('COMPARE_CLAUDE_MODELS', raising=False)
        configure_test_sandbox(world, monkeypatch, readonly_files=(install / 'claude', install / 'older'),
                               path_entries=(install,))
    _, record = start(world, 'direct_task')
    home = Path(record['sandbox']['home'])
    program = f'''
import json, os, pathlib, subprocess
commands = [['claude', '-p'], [{str(install / 'claude')!r}, '-p'],
            [{str(install / 'older')!r}, '-p'], [{str(fake)!r}, '-p']]
results = []
for command in commands:
    try:
        code = subprocess.run(command, input='Say OK only.\\n', text=True,
                              env={{'PATH': {str(install)!r} + ':/usr/bin:/bin',
                                   'HOME': '/home/compare'}}, capture_output=True).returncode
    except OSError:
        code = 126
    results.append(code)
print(json.dumps({{'codes': results,
                  'auth_visible': [pathlib.Path(p).is_file() for p in
                                   {['/home/compare/.claude/.credentials.json', '/home/compare/.claude.json', str(world.outside / 'fake-claude-config/.credentials.json')]!r}],
                  'token_present': [bool(os.environ.get(k)) for k in
                                    ['ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN']]}}))
'''
    done = call(world, record, f'{shlex.quote(sys.executable)} -c {shlex.quote(program)}', binary='codex')
    assert done.returncode == 0, done.stderr
    result = json.loads(done.stdout.splitlines()[-1])
    if no_claude:
        assert all(code != 0 for code in result['codes'])
        assert result['auth_visible'] == [False] * 3
        assert result['token_present'] == [False] * 3
        assert not (Path(record['tree']) / 'tmp/claude-called').exists()
    else:
        assert result['codes'] == [0] * 4
        assert result['auth_visible'] == [True, True, False]
        assert result['token_present'] == [True] * 3
        assert (Path(record['tree']) / 'tmp/claude-called').exists()
    route = call(world, record, 'true', binary='claude')
    assert route.returncode == (2 if no_claude else 0)



@pytest.mark.parametrize('shell_mode', ['-ic', '-lic'])
def test_no_claude_interactive_shell_keeps_codex_model_guard(world, monkeypatch, shell_mode):
    install, _ = install_fake_claude(world, monkeypatch)
    monkeypatch.setenv('COMPARE_CLAUDE_MODELS', '')
    configure_test_sandbox(world, monkeypatch, readonly_files=(install / 'claude', install / 'older'),
                           path_entries=(install,))
    (world.fakebin / 'codex').write_text('#!/bin/bash\n'
        'if [[ "$*" == *gpt-6.1-sol* ]]; then echo BYPASSED; exit 0; fi\n'
        'exec /bin/bash -c "$(cat)"\n')
    (world.fakebin / 'codex').chmod(0o755)
    _, record = start(world, 'direct_task')
    home = Path(record['sandbox']['home'])
    (home / '.bashrc').write_text(f'export PATH={shlex.quote(str(world.fakebin))}:/usr/bin:/bin\n')
    (home / '.bash_profile').write_text('. "$HOME/.bashrc"\n')
    nested = 'codex --model gpt-6.1-sol exec </dev/null; echo nested-exit=$?'
    script = (f'/bin/bash {shell_mode} {shlex.quote(nested)}; '
              'echo bash-env=${BASH_ENV-unset}; echo shell-env=${ENV-unset}')
    done = call(world, record, script, binary='codex')
    assert done.returncode == 0, done.stderr
    assert 'nested-exit=2' in done.stdout
    assert 'BYPASSED' not in done.stdout
    assert 'bash-env=unset' in done.stdout and 'shell-env=unset' in done.stdout
