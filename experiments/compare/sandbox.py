"""Comparison-only positive mounts and persistent native-session homes.

COMPARE_SANDBOX names a concrete controller-owned dependency declaration while
preparing, and the resulting unit declaration while launching. It never enters
the native environment. No host-root fallback or PATH-directory grants exist.
"""

import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

GUEST_HOME = Path('/home/compare')
CATALOG = Path(__file__).with_name('codex-models-0.163.0.json')
TMUX_FILES = ('SKILL.md', 'agents/openai.yaml', 'scripts/find-sessions.sh', 'scripts/wait-for-text.sh')
PROTECTED = frozenset(('HOME', 'CODEX_HOME', 'PATH', 'PYTHONPATH', 'OLDPWD', 'BASH_ENV', 'ENV',
    'SSH_AUTH_SOCK', 'TMUX', 'CLAUDE_CONFIG_DIR', 'CLAUDE_CODE_OAUTH_TOKEN_FILE',
    'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN'))
AUTH = {'codex': ('OPENAI_API_KEY',), 'claude': ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN')}
POLICY = ('ORC_ALLOWED_CODEX_MODELS', 'ORC_ALLOWED_CLAUDE_MODELS', 'ORC_SINGLE_CALL_CLI_STATE',
          'CLAUDE_CODE_SUBAGENT_MODEL', 'CLAUDE_CODE_SUBAGENT_MODEL_FORCE')
CLAUDE_BINDING = '/.compare-claude-model'  # the model guard's read-only Claude binding (shim/model-guard)
SONNET, HAIKU = 'claude-sonnet-5-5', 'claude-haiku-5-5'
CLAUDE_MODELS = (SONNET, HAIKU)  # a unit's one bound Claude model is one of these exact IDs
# Every Claude process in a unit's sandbox, an agent's or a judge's session or a CLI the agent starts itself, runs
# under these managed settings (CLAUDE_MANAGED, mounted read-only from memory, never read back from the writable
# home; above user, project, local and --settings values) and this environment. Keys as documented for CLI 2.1.330
# (code.claude.com/docs/en/managed-settings, /settings, /mcp#disable-claude-ai-connectors, /permissions,
# /env-vars). They keep out the account's claude.ai connectors, skills and plugins and any MCP or Artifact tool,
# turn auto memory and scheduled tasks off, and remove the tools that start other agents or sessions, act on the
# account, or wake a session after its answer, with the background runs of Bash, so that one call is one
# session. Which tools to remove is a policy: change it here.
CLAUDE_MANAGED = '/etc/claude-code/managed-settings.json'
CLAUDE_ENV = {"ENABLE_CLAUDEAI_MCP_SERVERS": "false", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
              "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "CLAUDE_CODE_DISABLE_CRON": "1"}
# CLAUDE_ENV is also the managed `env`, so a session's own ~/.claude/settings.json `env` cannot override it for the
# next call of a multi-call arm; allowManagedMcpServersOnly keeps out an MCP server a session plants in its home.
CLAUDE_SETTINGS = {
    "env": CLAUDE_ENV, "allowManagedMcpServersOnly": True,
    "disableClaudeAiConnectors": True, "syncClaudeAiSkills": False, "syncClaudeAiPlugins": False,
    "autoMemoryEnabled": False, "enableArtifact": False,
    "permissions": {"deny": ["mcp__*", "ListMcpResourcesTool", "ReadMcpResourceTool", "ReadMcpResourceDirTool",
                             "Artifact", "ArtifactCheck", "ArtifactComments", "ArtifactData", "Agent", "Task",
                             "Workflow", "SendMessage", "ListAgents", "RemoteTrigger", "PushNotification",
                             "DesignSync", "Monitor", "CronCreate", "CronDelete", "CronList", "ScheduleWakeup"]}}
# The tools a clean session's init event may list: the 25 built-in tools of CLI 2.1.327's first init event in the
# study's first paid run (tests/experiments/fixtures/seed_set/claude-2.1.327-direct-stream.jsonl), less the
# denied ones. Any other tool is an isolation breach (seed_set.units.isolation_breach), so a CLI update that adds a
# built-in tool shows as an incident until the list is renewed with the CLI pin at the next freeze (intended).
CLAUDE_TOOLS = frozenset(('Bash', 'Edit', 'EnterWorktree', 'ExitWorktree', 'NotebookEdit', 'Read', 'ReportFindings',
                          'Skill', 'TaskStop', 'ToolSearch', 'WebFetch', 'WebSearch', 'Write'))
BROAD = frozenset(('/', '/home', '/root', '/etc', '/mnt', '/srv', '/opt', '/run', '/var', '/tmp'))
DEPENDENCY_FIELDS = frozenset(('codex', 'claude', 'readonly', 'path', 'environment', 'catalog', 'skills'))
UNIT_FIELDS = frozenset(('tree', 'records', 'home', 'home_path', 'clones', 'providers', 'result_root', 'claude_model'))


def _read(path):
    return json.loads(Path(path).read_text())


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def _absolute(value):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or str(path) != os.path.normpath(path):
        raise ValueError(f'sandbox path must be normalized and absolute: {path}')
    return path


def _role(name, environment):
    # Resolve named executables, never grant the directories searched to find them.
    path = os.pathsep.join(part for part in environment.get('PATH', os.defpath).split(os.pathsep)
                          if not (Path(part) / 'model-guard').is_file() and Path(part).name != '.model-guard')
    found = shutil.which(name, path=path)
    return str(Path(found).resolve()) if found else None


def dependencies(environment=None):
    """Concrete dependencies for preparation; an explicit declaration replaces discovery."""
    environment = os.environ if environment is None else environment
    if environment.get('COMPARE_SANDBOX'):
        result = _read(environment['COMPARE_SANDBOX'])
        if not isinstance(result, dict) or set(result) - DEPENDENCY_FIELDS:
            raise ValueError('sandbox dependency declaration has unsupported fields')
        return result
    readonly = {str(p): str(p.resolve(strict=True)) for p in map(Path, (
        '/usr', '/etc/ld.so.cache', '/etc/hosts', '/etc/nsswitch.conf', '/etc/passwd', '/etc/group',
        '/etc/ssl/certs', '/etc/ssl/openssl.cnf', '/etc/resolv.conf')) if p.exists()}
    prefix = Path(sys.prefix).resolve()
    for path in (prefix / 'bin', prefix / 'lib'):
        if path.exists() and not path.is_relative_to('/usr'):
            readonly[str(path)] = str(path.resolve(strict=True))
    codex, claude, node = (_role(name, environment) for name in ('codex', 'claude', 'node'))
    if codex:
        package = Path(codex).parent.parent
        metadata = package / 'package.json'
        if metadata.is_file() and _read(metadata).get('name') == '@openai/codex':
            if _read(metadata).get('version') != '0.163.0':
                raise ValueError('the default public catalog requires Codex 0.163.0; declare reviewed dependencies')
            readonly[str(package)] = str(package)
    if node:
        readonly[node] = node
    source_home = Path(environment.get('HOME') or Path.home())
    skill = Path(environment.get('CODEX_HOME') or source_home / '.codex') / 'skills/tmux'
    return {'codex': codex, 'claude': claude, 'readonly': readonly,
            'path': [*([] if not node else [str(Path(node).parent)]), str(prefix / 'bin'), '/usr/bin', '/bin'],
            'environment': ['LANG', 'LC_ALL', 'TERM', 'COLORTERM', 'TZ',
                            'PYTHONDONTWRITEBYTECODE', 'DISABLE_AUTOUPDATER'],
            'catalog': str(CATALOG), 'skills': [str(skill)] if skill.is_dir() else []}


def _validate_dependencies(data):
    if not isinstance(data, dict) or set(data) - DEPENDENCY_FIELDS - UNIT_FIELDS:
        raise ValueError('sandbox unit declaration has unsupported fields')
    if not isinstance(data.get('readonly'), dict) or not isinstance(data.get('path'), list):
        raise ValueError('sandbox requires concrete readonly mounts and a PATH list')
    for field in ('environment', 'skills'):
        if not isinstance(data.get(field, []), list) or any(not isinstance(value, str) for value in data.get(field, [])):
            raise ValueError(f'sandbox {field} must be a list of names or paths')
    for destination, source in data['readonly'].items():
        dest, src = _absolute(destination), _absolute(source)
        if str(dest) in BROAD or str(src) in BROAD or dest == GUEST_HOME:
            raise ValueError(f'broad sandbox dependency refused: {dest}')
        if not src.exists() or src.resolve() != src:
            raise ValueError(f'missing or escaping sandbox dependency: {src}')
    for value in data['path']:
        _absolute(value)
    for name in data.get('environment', []):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) or name in PROTECTED or name.startswith(('COMPARE_', 'ORC_', 'ORCHESTRATOR_')):
            raise ValueError(f'launcher-controlled sandbox environment name: {name}')
    for name in ('codex', 'claude'):
        if data.get(name):
            binary = _absolute(data[name])
            if not binary.is_file() or binary.resolve() != binary or not os.access(binary, os.X_OK):
                raise ValueError(f'missing or escaping declared {name} executable: {binary}')
    catalog = _absolute(data['catalog'])
    value = _read(catalog)
    if set(value) != {'models'} or not isinstance(value['models'], list):
        raise ValueError('sandbox catalog must be a public models-only export, without account identity')


def _providers(source, data, environment):
    selected = {name for name in ('codex', 'claude') if data.get(name)}
    if source and Path(source).is_file():
        profiles = _read(source).values()
        selected &= {name for name in selected if any(isinstance(profile, str) and (
            profile == name or profile.startswith(name + '_')) for profile in profiles)}
    if environment.get('COMPARE_CLAUDE_MODELS') == '':
        selected.discard('claude')
    return sorted(selected)


def claude_binding(opt_in):
    """The one Claude model an opt-in (COMPARE_CLAUDE_MODELS) binds: Haiku only for its exact ID, else Sonnet."""
    return HAIKU if opt_in == HAIKU else SONNET


def _bound_claude(model):
    if model not in CLAUDE_MODELS:
        raise ValueError(f"Claude binding {model!r} is outside the owner's exact Sonnet/Haiku IDs")
    return model


def prepare_unit(tree, records, *, homes, clones=(), providers=None, environment=None, result_root=None,
                 claude_model=SONNET):
    """Create one home once; its declaration/marker bind launch, resume and receipt discovery. The declaration
    fixes the unit's one Claude model; a launch environment can only narrow it."""
    _bound_claude(claude_model)
    environment = os.environ if environment is None else environment
    tree, records, homes = (Path(p).resolve() for p in (tree, records, homes))
    declaration = records / 'sandbox.json'
    if declaration.exists() or declaration.is_symlink():
        raise ValueError('sandbox unit already prepared; resume its recorded declaration')
    data = dependencies(environment)
    _validate_dependencies(data)
    if homes.is_relative_to(tree) or homes.is_relative_to(records):
        raise ValueError('private homes must stay outside candidate and public records trees')
    homes.mkdir(parents=True, exist_ok=True, mode=0o700)
    homes.chmod(0o700)
    home = homes / secrets.token_hex(16)
    home.mkdir(mode=0o700)
    native = home / '.codex'
    native.mkdir(mode=0o700)
    shutil.copyfile(data['catalog'], native / 'public-models.json')
    (native / 'config.toml').write_text('cli_auth_credentials_store = "file"\n'
        f'model_catalog_json = {json.dumps(str(GUEST_HOME / ".codex/public-models.json"))}\n'
        '[features]\napps = false\nhooks = false\nplugins = false\nrecommended_plugins = false\n'
        'api_key_model_discovery = false\n')
    for skill in map(Path, data.get('skills', [])):
        if skill.name != 'tmux' or any(p.is_symlink() for p in skill.rglob('*')) or sorted(
                str(p.relative_to(skill)) for p in skill.rglob('*') if p.is_file()) != sorted(TMUX_FILES):
            raise ValueError('only the exact audited public tmux skill directory is admitted')
        shutil.copytree(skill, native / 'skills/tmux')
    selected = _providers(providers, data, environment)
    bin_dir = home / '.compare-bin'
    bin_dir.mkdir()
    for provider in selected:
        (bin_dir / provider).symlink_to(data[provider])
    source_home = Path(environment.get('HOME') or Path.home())
    credentials = {'codex': (Path(environment.get('CODEX_HOME') or source_home / '.codex') / 'auth.json', native / 'auth.json'),
                   'claude': (Path(environment.get('CLAUDE_CONFIG_DIR') or source_home / '.claude') / '.credentials.json',
                              home / '.claude/.credentials.json')}
    for name in selected:
        source, destination = credentials[name]
        if source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(source, destination)
            destination.chmod(0o600)
    if 'claude' in selected:
        (home / '.claude.json').write_text('{"hasCompletedOnboarding":true}\n')
    data.update(tree=str(tree), records=str(records), home=str(home), home_path=str(GUEST_HOME),
                clones=[str(Path(p).resolve()) for p in clones], providers=selected,
                result_root=str(Path(result_root).resolve() if result_root else tree), claude_model=claude_model)
    _write(declaration, data)
    metadata = {'home': str(home), 'home_path': str(GUEST_HOME), 'declaration': str(declaration)}
    _write(home / '.compare-unit.json', {**metadata, 'tree': str(tree)})
    return metadata


def session_home(metadata, requested=None):
    """New units use their bound backing; records without new lineage keep historical semantics."""
    if 'sandbox' not in metadata:
        records = metadata.get('records') or metadata.get('records_dir')
        if 'COMPARE_SANDBOX=' in metadata.get('command', '') or records and (Path(records) / 'sandbox.json').exists():
            raise ValueError('new sandbox record lost its private home lineage')
        return Path(requested) if requested is not None else Path.home()
    info = metadata['sandbox']
    if not isinstance(info, dict) or set(info) != {'home', 'home_path', 'declaration'}:
        raise ValueError('incomplete sandbox private home lineage')
    home, guest, declaration = (_absolute(info[name]) for name in ('home', 'home_path', 'declaration'))
    data = _read(declaration)
    expected = {**info, 'tree': metadata['tree']}
    if not home.is_dir() or guest != GUEST_HOME or _read(home / '.compare-unit.json') != expected or any(
            data.get(key) != value for key, value in expected.items() if key != 'declaration'):
        raise ValueError('inconsistent sandbox private home lineage')
    if requested is not None and Path(requested).resolve() != home:
        raise ValueError('a recorded sandbox private home cannot be overridden')
    return home


def _publication_parent(result, descriptor):
    expected, actual = os.fstat(descriptor), result.parent.stat(follow_symlinks=False)
    if result.parent.resolve() != result.parent or (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
        raise ValueError('prepared result parent changed before publication')
    try:
        os.stat(result.name, dir_fd=descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ValueError('prepared result destination already exists')


def _result_grant(data, environment, tree):
    value = environment.get('ORCHESTRATOR_OUTPUT_BUNDLE_PATH')
    if not value:
        return None, None, None, None
    result = _absolute(value)
    if result.is_relative_to(tree):
        return result, None, None, None
    root = _absolute(data['result_root'])
    if result.name != 'result.json' or result.parent.resolve() != result.parent or not result.parent.is_relative_to(root):
        raise ValueError('result destination lacks an exact prepared delivery grant')
    protected = [tree, GUEST_HOME, Path(data['home']), *map(Path, data['readonly']), *map(Path, data['clones'])]
    if any(result.parent.is_relative_to(path) or path.is_relative_to(result.parent) for path in protected):
        raise ValueError('external result workspace overlaps a prepared tree, home, clone or dependency')
    parent = os.open(result.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        _publication_parent(result, parent)
        staging = Path(tempfile.mkdtemp(prefix='.compare-result-', dir=tree / 'tmp'))
        staged = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except BaseException:
        os.close(parent)
        raise
    return result, parent, staged, staging


def _publish_result(result, parent, staged):
    try:
        source = os.open(result.name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=staged)
    except FileNotFoundError:
        _publication_parent(result, parent)
        return
    with os.fdopen(source, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('staged result must be a regular file')
        _publication_parent(result, parent)
        temporary = '.compare-publish-' + secrets.token_hex(16)
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
        try:
            with os.fdopen(descriptor, 'wb') as target:
                shutil.copyfileobj(stream, target)
            _publication_parent(result, parent)
            os.link(temporary, result.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        finally:
            os.unlink(temporary, dir_fd=parent)


def _pipe(text):
    """A pipe's read end holding `text`, for bubblewrap's --ro-bind-data (a file nothing in the sandbox can write)."""
    reader, writer = os.pipe()
    try:
        os.write(writer, text.encode())
    except BaseException:
        os.close(reader)
        raise
    finally:
        os.close(writer)
    return reader


def launch(name, argv, environment=None, *, call=None):
    """Run the guarded native CLI inside its prepared positive mount boundary."""
    environment = os.environ if environment is None else environment
    pointer = environment.get('COMPARE_SANDBOX')
    if not pointer:
        raise ValueError('COMPARE_SANDBOX must name the prepared unit declaration')
    data = _read(pointer)
    _validate_dependencies(data)
    claude_model = _bound_claude(data.get('claude_model', SONNET))  # units declared before the field: Sonnet
    tree, records = Path(data['tree']), Path(data['records'])
    info = {'home': data['home'], 'home_path': data['home_path'], 'declaration': pointer}
    home = session_home({'tree': str(tree), 'sandbox': info})
    if str(tree) != environment.get('COMPARE_TREE') or str(records) != environment.get('COMPARE_ROOT'):
        raise ValueError('sandbox declaration belongs to another capture unit')
    if call is not None:
        call = _absolute(str(call))
        if call.parent != records / 'calls' or not call.name.isdecimal() or call.resolve() != call:
            raise ValueError('sandbox call evidence must stay in its exact controller capture directory')
    denied = records / 'claude-denied'
    if environment.get('COMPARE_CLAUDE_MODELS') == '' and 'claude' in data['providers'] and not (
            denied.exists() or denied.is_symlink()):
        with denied.open('x') as marker:
            marker.write('Claude permanently disabled for this prepared unit.\n')
    no_claude = 'claude' not in data['providers'] or denied.exists() or denied.is_symlink()
    if name == 'claude' and no_claude:
        print('sandbox: Claude is forbidden by the declared model policy', file=sys.stderr)
        return 2
    if name not in data['providers']:
        raise ValueError(f'{name} state was not prepared for this unit')
    current = Path.cwd().resolve()
    if not current.is_relative_to(tree):
        raise ValueError('native cwd must stay in its prepared unit tree')
    try:
        result, parent, staged, staging = _result_grant(data, environment, tree)
    except (OSError, ValueError) as error:
        if call is not None:
            _write(call / 'publication-error.json', {'native_exit': None, 'error': str(error)})
        raise
    binding = managed = None
    try:
        # --disable-userns: no nested user namespace, so the candidate cannot mount over the binding or the guard
        # whatever the host's user-namespace policy (bubblewrap >= 0.8).
        args = ['bwrap', '--die-with-parent', '--new-session', '--unshare-user', '--disable-userns',
                '--unshare-pid', '--unshare-ipc', '--unshare-uts',
                '--clearenv', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/var/tmp',
                '--bind', str(home), str(GUEST_HOME)]
        mounts = dict(data['readonly'])
        for provider in data['providers']:
            if provider != 'claude' or not no_claude:
                mounts[data[provider]] = data[provider]
        for destination, source in mounts.items():
            dest = Path(destination)
            if dest == tree or dest.is_relative_to(tree) or tree.is_relative_to(dest) or dest == GUEST_HOME:
                raise ValueError('dependency mount overlaps writable unit tree/home')
            args += ['--ro-bind', source, destination]
        for name_ in ('bin', 'sbin', 'lib', 'lib64'):
            path = Path('/' + name_)
            if path.is_symlink():
                target = path.resolve()
                if not target.is_relative_to('/usr'):
                    raise ValueError('OS alias escapes the declared /usr installation')
                args += ['--symlink', str(target), str(path)]
            elif path.exists():
                args += ['--ro-bind', str(path), str(path)]
        args += ['--bind', str(tree), str(tree), '--bind', str(tree / 'tmp'), '/tmp']
        # The candidate can neither edit the guard nor rebind the declared Claude model.
        binding = _pipe(claude_model)
        args += ['--ro-bind', str(tree / '.model-guard'), str(tree / '.model-guard'),
                 '--ro-bind-data', str(binding), CLAUDE_BINDING]
        if staging is not None:
            args += ['--bind-fd', str(staged), str(result.parent)]
        for value in data['clones']:
            clone = _absolute(value)
            if not clone.is_dir() or clone.resolve() != clone or clone.parent.name != 'clones':
                raise ValueError('missing or escaping exact judge clone grant')
            args += ['--ro-bind', str(clone), str(clone)]
        if no_claude:
            args += ['--tmpfs', str(GUEST_HOME / '.claude'), '--ro-bind', '/dev/null', str(GUEST_HOME / '.claude.json')]
            if data.get('claude'):
                args += ['--ro-bind', '/dev/null', data['claude']]
        else:
            managed = _pipe(json.dumps(CLAUDE_SETTINGS))
            args += ['--ro-bind-data', str(managed), CLAUDE_MANAGED]
        for name_ in ('.bashrc', '.profile', '.bash_profile', '.bash_login'):
            args += ['--ro-bind', '/dev/null', str(GUEST_HOME / name_)]
        native_env = {key: environment[key] for key in data.get('environment', []) if key in environment}
        native_env.update(HOME=str(GUEST_HOME), CODEX_HOME=str(GUEST_HOME / '.codex'), TMPDIR='/tmp',
            PATH=os.pathsep.join([str(tree / '.model-guard'), str(GUEST_HOME / '.compare-bin'), *data['path']]),
            GIT_OPTIONAL_LOCKS='0')
        native_env.update({key: environment[key] for key in POLICY if key in environment})
        if no_claude:
            native_env['ORC_ALLOWED_CLAUDE_MODELS'] = ''
        else:
            native_env.update(CLAUDE_ENV)
        for provider in data['providers']:
            if provider != 'claude' or not no_claude:
                native_env.update({key: environment[key] for key in AUTH[provider] if key in environment})
        if environment.get('ORCHESTRATOR_WORKSPACE_ROOT'):
            workspace = Path(environment['ORCHESTRATOR_WORKSPACE_ROOT']).resolve()
            if not workspace.is_relative_to(tree) or result is None:
                raise ValueError('launch-workspace delivery lacks a prepared writable unit grant')
            native_env.update({key: environment[key] for key in ('ORCHESTRATOR_WORKSPACE_ROOT',
                'ORCHESTRATOR_OUTPUT_BUNDLE_PATH', 'ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY') if key in environment})
        for key, value in native_env.items():
            args += ['--setenv', key, value]
        args += ['--chdir', str(current), '--', str(tree / '.model-guard' / name), *argv]
        if staging is not None:
            if call is None:
                raise ValueError('external result publication requires its exact call evidence directory')
            with (call / 'publication-error.json').open('x') as pending:
                json.dump({'pending': True, 'native_exit': None}, pending)
        status = subprocess.run(args, env=environment, close_fds=True,
                                pass_fds=tuple(fd for fd in (staged, binding, managed) if fd is not None)).returncode
        if staging is not None:
            _write(call / 'native-exit.json', {'native_exit': status})
        if staging is not None:
            try:
                _publish_result(result, parent, staged)
                os.close(parent)
                parent = None
                os.close(staged)
                staged = None
                (call / 'publication-error.json').unlink()
            except (OSError, ValueError) as error:
                try:
                    _write(call / 'publication-error.json', {'native_exit': status, 'publication_error': str(error)})
                except OSError:
                    pass  # The existing pending/malformed marker still refuses every intake path.
                print(f'sandbox: result publication failed (native exit {status}): {error}', file=sys.stderr)
                return 70
        return status
    finally:
        for descriptor in (parent, staged, binding, managed):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass


if __name__ == '__main__':
    try:
        raise SystemExit(launch(sys.argv[2], sys.argv[3:], call=sys.argv[1]))
    except (KeyError, OSError, ValueError, TypeError) as error:
        print(f'sandbox: {error}', file=sys.stderr)
        raise SystemExit(70)
