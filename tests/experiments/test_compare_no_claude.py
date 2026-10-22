"""Explicit no-Claude bindings isolate installed CLIs and credentials; no real providers."""
import json
import os
import shlex
import sys
from pathlib import Path

import pytest

from tests.experiments.compare_harness_support import call, skip_without_sandbox, start, world  # noqa: F401

skip_without_sandbox()


def install_fake_claude(world, monkeypatch):
    home = world.outside / 'isolated-home'
    install = home / '.local/share/claude/versions'
    install.mkdir(parents=True)
    marker = world.outside / 'claude-called'
    for name in ('current', 'older'):
        binary = install / name
        binary.write_text(f'#!/bin/sh\ntouch {shlex.quote(str(marker))}\nexit 0\n')
        binary.chmod(0o755)
    (home / '.local/bin').mkdir()
    (home / '.local/bin/claude').symlink_to(install / 'current')
    (home / '.claude').mkdir()
    (home / '.claude/.credentials.json').write_text('fake credentials')
    (home / '.claude.json').write_text('fake settings')
    custom = home / 'custom-claude-config'; custom.mkdir()
    (custom / 'credentials').write_text('fake custom credentials')
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(custom))
    monkeypatch.setenv('PATH', f"{home / '.local/bin'}:{os.environ['PATH']}")
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'fake-key')
    monkeypatch.setenv('ANTHROPIC_AUTH_TOKEN', 'fake-token')
    monkeypatch.setenv('CLAUDE_CODE_OAUTH_TOKEN', 'fake-oauth')
    return home, install, marker, custom


@pytest.mark.parametrize('no_claude', [False, True])
def test_no_claude_survives_descendant_path_and_environment_reset(world, monkeypatch, no_claude):
    home, install, marker, custom = install_fake_claude(world, monkeypatch)
    # Every executable here is a fake. Even a failing assertion cannot spend provider calls.
    fake = world.fakebin / 'claude'
    fake.write_text(f'#!/bin/sh\ntouch {shlex.quote(str(marker))}\nexit 0\n')
    fake.chmod(0o755)
    if no_claude:
        monkeypatch.setenv('COMPARE_CLAUDE_MODELS', '')
    else:
        monkeypatch.delenv('COMPARE_CLAUDE_MODELS', raising=False)
    _, record = start(world, 'direct_task')
    program = f'''
import json, os, pathlib, subprocess
commands = [['claude', '-p'], [{str(home / '.local/bin/claude')!r}, '-p'],
            [{str(install / 'older')!r}, '-p'], [{str(fake)!r}, '-p']]
results = []
for command in commands:
    try:
        code = subprocess.run(command, input='Say OK only.\\n', text=True,
                              env={{'PATH': {str(home / '.local/bin')!r} + ':/usr/bin:/bin',
                                   'HOME': {str(home)!r}}}, capture_output=True).returncode
    except OSError:
        code = 126
    results.append(code)
print(json.dumps({{'codes': results,
                  'auth_visible': [pathlib.Path(p).is_file() for p in
                                   {[str(home / '.claude/.credentials.json'), str(home / '.claude.json'), str(custom / 'credentials')]!r}],
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
        assert not marker.exists()
    else:
        assert result['codes'] == [0] * 4
        assert result['auth_visible'] == [True] * 3
        assert result['token_present'] == [True] * 3
        assert marker.exists()



@pytest.mark.parametrize('shell_mode', ['-ic', '-lic'])
def test_no_claude_interactive_shell_keeps_codex_model_guard(world, monkeypatch, shell_mode):
    home, _, _, _ = install_fake_claude(world, monkeypatch)
    monkeypatch.setenv('COMPARE_CLAUDE_MODELS', '')
    # Reproduce an interactive rc file displacing the inherited guard; no historical PATH claim.
    (home / '.bashrc').write_text(f'export PATH={shlex.quote(str(world.fakebin))}:/usr/bin:/bin\n')
    (home / '.bash_profile').write_text('. "$HOME/.bashrc"\n')
    bash_env = home / 'bash-env'
    bash_env.write_text(f'export PATH={shlex.quote(str(world.fakebin))}:/usr/bin:/bin\n')
    monkeypatch.setenv('BASH_ENV', str(bash_env))
    monkeypatch.setenv('ENV', str(bash_env))
    (world.fakebin / 'codex').write_text('#!/bin/bash\n'
        'if [[ "$*" == *gpt-6.1-sol* ]]; then echo BYPASSED; exit 0; fi\n'
        'exec /bin/bash -c "$(cat)"\n')
    (world.fakebin / 'codex').chmod(0o755)
    _, record = start(world, 'direct_task')
    nested = 'codex --model gpt-6.1-sol exec </dev/null; echo nested-exit=$?'
    script = (f'/bin/bash {shell_mode} {shlex.quote(nested)}; '
              'echo bash-env=${BASH_ENV-unset}; echo shell-env=${ENV-unset}')
    done = call(world, record, script, binary='codex')
    assert done.returncode == 0, done.stderr
    assert 'nested-exit=2' in done.stdout
    assert 'BYPASSED' not in done.stdout
    assert 'bash-env=unset' in done.stdout and 'shell-env=unset' in done.stdout
