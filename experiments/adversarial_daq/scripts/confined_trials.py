#!/usr/bin/python3
"""Deployment boundary: native Codex tool permissions and offline bwrap trials."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CONDA = Path('/home/ollie/miniconda3')
NODE = Path('/home/ollie/.nvm/versions/node/v20.19.4')


def clean_environment(home):
    environment = {'HOME': str(home), 'LANG': 'C.UTF-8',
                   'PATH': f'{ROOT}/.venv/bin:{CONDA}/bin:/usr/bin:/bin',
                   'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    bundle = os.environ.get('ORCHESTRATOR_OUTPUT_BUNDLE_PATH')
    if bundle:
        resolved = Path(bundle).resolve()
        if not any(resolved.is_relative_to(ROOT / name) for name in ('artifacts', '.orchestrate')):
            raise ValueError('result channel must be inside artifacts or .orchestrate')
        environment['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'] = bundle
    return environment


def trial_command(argv):
    cwd = Path.cwd().resolve()
    if not cwd.is_relative_to(ROOT):
        raise ValueError('working directory must be inside the DAQ package')
    command = ['/usr/bin/bwrap', '--die-with-parent', '--new-session',
               '--unshare-user', '--unshare-pid', '--unshare-ipc', '--unshare-uts',
               '--unshare-net', '--disable-userns', '--cap-drop', 'ALL', '--clearenv']
    for path in ('/usr', '/bin', '/sbin', '/lib', '/lib64', str(CONDA)):
        command += ['--ro-bind', path, path]
    for path in ('/etc/resolv.conf', '/etc/hosts', '/etc/nsswitch.conf',
                 '/etc/gai.conf', '/etc/ld.so.cache', '/etc/ssl/certs'):
        if Path(path).exists():
            command += ['--ro-bind', path, path]
    command += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
                '--tmpfs', '/run', '--dir', '/tmp/home', '--ro-bind', str(ROOT), str(ROOT)]
    # Only generated artifacts and runtime result channels are host-writable.
    for name in ('artifacts', '.orchestrate'):
        path = ROOT / name
        if path.is_symlink() or not path.is_dir():
            raise ValueError('required writable directory is missing or a symlink: ' + name)
        command += ['--bind', str(path), str(path)]
    for name, value in clean_environment('/tmp/home').items():
        command += ['--setenv', name, value]
    return command + ['--chdir', str(cwd), '--', *argv]


def provider_configuration():
    auth = Path(os.environ['DAQ_CODEX_HOME']).resolve()
    if (not auth.is_dir() or auth.is_relative_to(ROOT)
            or auth.is_relative_to(Path('/home/ollie/.codex'))):
        raise ValueError('DAQ_CODEX_HOME must be a dedicated external directory, never host ~/.codex')
    auth_file = auth / 'auth.json'
    if auth_file.is_symlink() or not auth_file.is_file():
        raise ValueError('auth.json must be a regular non-symlink file')
    access = {':root': 'deny', ':minimal': 'read', str(ROOT): 'read',
              str(ROOT / 'artifacts'): 'write', str(ROOT / '.orchestrate'): 'write',
              str(CONDA): 'read', str(NODE): 'read', str(auth): 'deny'}
    filesystem = '{' + ','.join(json.dumps(k) + '=' + json.dumps(v) for k, v in access.items()) + '}'
    configuration = ['--config', 'default_permissions="daq"',
                     '--config', 'permissions.daq.filesystem=' + filesystem,
                     '--config', 'permissions.daq.network.enabled=false',
                     '--config', 'approval_policy="never"',
                     '--config', 'project_doc_max_bytes=0']
    for feature, value in (('multi_agent', 'false'), ('skip_host_skill_discovery', 'true'),
                           ('apps', 'false'), ('plugins', 'false'), ('shell_snapshot', 'false')):
        configuration += ['--config', f'features.{feature}={value}']
    temporary = ROOT / 'artifacts/launch/provider-tmp'
    for directory in (ROOT / 'artifacts', temporary.parent, temporary):
        if directory.is_symlink():
            raise ValueError('provider temporary directory must not traverse symlinks')
        directory.mkdir(exist_ok=True)
    environment = clean_environment(auth)
    environment.update(CODEX_HOME=str(auth), TMPDIR=str(temporary),
                       PATH=f'{NODE}/bin:' + environment['PATH'])
    return configuration, environment


def provider_main(argv):
    # The builtin provider registry assumes an unrestricted external boundary.
    argv = [arg for arg in argv if arg != '--dangerously-bypass-approvals-and-sandbox']
    configuration, environment = provider_configuration()
    if argv != ['--version']:
        if not argv or argv[0] != 'exec':
            raise ValueError('only codex exec and --version are admitted')
        for flag in ('--ignore-user-config', '--ignore-rules', '--skip-git-repo-check'):
            if flag not in argv:
                argv.append(flag)
        argv += configuration
    command = [str(NODE / 'bin/codex'), *argv]
    os.execve(command[0], command, environment)


if __name__ == '__main__':
    command = trial_command([str(ROOT / '.venv/bin/python'),
                             str(ROOT / 'scripts/run_trials.py'), *sys.argv[1:]])
    # Scrub bwrap's init process too: generated code can read /proc/1/environ.
    os.execve(command[0], command, {})
