#!/usr/bin/python3
"""Offline deployment checks; never starts a provider/model request."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


def main():
    import confined_trials as confinement
    assert confinement.ROOT == ROOT

    os.chdir(ROOT)
    env = dict(os.environ, DAQ_HOST_SECRET='must-not-reach-trials')
    with tempfile.TemporaryDirectory(prefix='confinement-', dir=ROOT / 'artifacts') as directory:
        folder = Path(directory)
        relative = folder.relative_to(ROOT)
        suite = folder / 'suite.py'
        suite.write_text('''import errno, json, os, socket, sys
from pathlib import Path
import orchestrator
assert 'DAQ_HOST_SECRET' not in os.environ
for process_env in Path('/proc').glob('[0-9]*/environ'):
    assert b'must-not-reach-trials' not in process_env.read_bytes(), str(process_env)
assert 'CODEX_HOME' not in os.environ
assert not Path('/run/daq-codex/auth.json').exists()
assert not Path('/home/ollie/.codex/auth.json').exists()
assert not Path('/home/ollie/Documents/agent-orchestration/docs/index.md').exists()
assert '/research/agent-orchestration-main/orchestrator/' in orchestrator.__file__
root = Path(__file__).resolve()
while root.name != 'adversarial_daq':
    root = root.parent
for target in (root / 'scripts/run_trials.py', root / '.venv/pyvenv.cfg',
               root / 'deployment/check_confinement.py'):
    try:
        with target.open('ab'):
            pass
    except OSError as exc:
        assert exc.errno in (errno.EROFS, errno.EACCES), exc
    else:
        raise AssertionError('host-shared code is writable: ' + str(target))
with socket.socket() as connection:
    connection.settimeout(0.2)
    assert connection.connect_ex(('192.0.2.1', 443)) == errno.ENETUNREACH
contract = json.loads(Path('contract.json').read_text())
value = {'arm': sys.argv[1], 'seed': int(sys.argv[2]), 'cases': [
    {'id': case, 'checks': {'isolated': True}, 'metrics': {'calls': 0}}
    for case in contract['cases']]}
Path(sys.argv[3]).write_text(json.dumps(value))
''')
        proposal = {'version': 1, 'suite': 'suite.py', 'files': ['suite.py'],
                    'cases': ['clean', 'fault'], 'checks': ['isolated'],
                    'metrics': ['calls'], 'seeds': [11, 23, 47], 'timeout_sec': 5}
        pp = relative / 'proposal.json'
        cp = relative / 'challenge.json'
        (ROOT / pp).write_text(json.dumps(proposal))
        (folder / 'baseline.py').write_text('# synthetic deployment control\n')
        (ROOT / cp).write_text(json.dumps({'version': 1, 'proposal': str(pp),
                                         'files': ['baseline.py'], 'cases': []}))
        bundle = folder / 'bundle.json'
        env['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'] = str(bundle)
        subprocess.run([str(ROOT / '.venv/bin/python'), str(ROOT / 'scripts/confined_trials.py'),
                        str(pp), str(cp)], env=env, check=True)
        result = json.loads(bundle.read_text())
        report_path = ROOT / result['report']
        report = json.loads(report_path.read_text())
        assert result['valid'], report['errors']
        assert len(report['trials']) == 6
        assert report['environment']['executable'] == str(ROOT / '.venv/bin/python')
        assert report['forwarded_environment_names'] == []
        subprocess.run([str(ROOT / '.venv/bin/python'), str(ROOT / 'scripts/confined_trials.py'),
                        'verify', result['report'], result['digest']], env=env, check=True)
        assert json.loads(bundle.read_text()) is True
        print('PASS: six paired trials, pinned runtime, readonly code, workspace writes, '
              'no host home/secret/auth, no trial network, typed result and evidence verification')
        print('Evidence: ' + str(report_path))

    with tempfile.TemporaryDirectory(prefix='daq-offline-auth-') as auth:
        Path(auth, 'auth.json').write_text('{}')
        env['DAQ_CODEX_HOME'] = auth
        subprocess.run([str(ROOT / 'deployment/bin/codex'), '--version'], env=env, check=True)
        registry = subprocess.run([str(ROOT / '.venv/bin/python'), '-c',
            'import json; from orchestrator.providers.registry import ProviderRegistry; '
            'print(json.dumps(ProviderRegistry().get("codex_unrestricted_workspace").command))'],
            capture_output=True, text=True, check=True)
        registry_argv = [arg.replace('${model}', 'gpt-6.1-sol').replace('${reasoning_effort}', 'high')
                         for arg in json.loads(registry.stdout)]
        previous = os.environ.get('DAQ_CODEX_HOME')
        os.environ['DAQ_CODEX_HOME'] = auth
        try:
            configuration, provider_env = confinement.provider_configuration()
            for flags in ([], ['--ignore-user-config', '--ignore-rules']):
                with patch.object(confinement.os, 'execve') as execute:
                    confinement.provider_main([*registry_argv[1:], *flags])
                argv = execute.call_args.args[1]
                for flag in ('--skip-git-repo-check', '--ignore-user-config', '--ignore-rules'):
                    assert argv.count(flag) == 1, argv
                parsed = subprocess.run([str(ROOT / 'deployment/bin/codex'), *registry_argv[1:],
                                         *flags, '--help'], env=env, capture_output=True, text=True)
                assert parsed.returncode == 0, parsed.stderr
            print('PASS: exact pinned registry argv and existing ignore flags occur once; parser accepts them')
        finally:
            if previous is None:
                del os.environ['DAQ_CODEX_HOME']
            else:
                os.environ['DAQ_CODEX_HOME'] = previous
        assert 'DAQ_HOST_SECRET' not in provider_env
        with tempfile.TemporaryDirectory(prefix='native-probe-', dir=ROOT / 'artifacts') as probe:
            program = f'''import errno, os, socket, tempfile
from pathlib import Path
assert 'DAQ_HOST_SECRET' not in os.environ
with tempfile.TemporaryDirectory() as temporary:
    assert Path(temporary).is_relative_to(Path(os.environ['TMPDIR']))
    Path(temporary, 'written').write_text('allowed')
for filename in ({str(Path(auth, 'auth.json'))!r},
                 '/home/ollie/Documents/agent-orchestration/docs/index.md'):
    try:
        Path(filename).read_bytes()
    except OSError as exc:
        assert exc.errno in (errno.EACCES, errno.EPERM, errno.ENOENT), exc
    else:
        raise AssertionError('host file readable: ' + filename)
try:
    with Path({str(ROOT / 'scripts/run_trials.py')!r}).open('ab'):
        pass
except OSError as exc:
    assert exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS), exc
else:
    raise AssertionError('host-shared code writable')
try:
    socket.socket(socket.AF_INET, socket.SOCK_STREAM)
except OSError as exc:
    assert exc.errno in (errno.EACCES, errno.EPERM), exc
else:
    raise AssertionError('provider tool networking enabled')
Path({str(Path(probe, 'written'))!r}).write_text('allowed')
'''
            subprocess.run([str(confinement.NODE / 'bin/codex'), 'sandbox',
                            '--permission-profile', 'daq', *configuration,
                            '--', '/usr/bin/python3', '-c', program],
                           env=provider_env, check=True)
            assert Path(probe, 'written').read_text() == 'allowed'
        print('PASS: native Codex tools deny network/auth/host reads/code writes; artifacts writable; '
              'no model request')


if __name__ == '__main__':
    main()
