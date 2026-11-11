"""Paired local experiment runner. Evidence collection, NOT an OS security sandbox.

The suite is a cross-reviewed synthetic oracle supplied by the adversaries.
It cannot certify its own DAQ realism or hide secrets from arbitrary Python.
"""
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import subprocess
import sys
import time
import uuid

MODEL_ENV = frozenset({'DAQ_MODEL_BASE_URL', 'DAQ_MODEL_NAME', 'DAQ_MODEL_API_KEY',
                      'ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL',
                      'OPENAI_API_KEY', 'OPENAI_BASE_URL'})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def checked_path(root, relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError('path must be a nonempty string')
    p = PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or '\\' in relative or '.' == relative:
        raise ValueError('path outside submission: ' + relative)
    current = root
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('symlinks are not accepted: ' + relative)
    if not current.is_file() or not current.resolve().is_relative_to(root.resolve()):
        raise ValueError('missing regular source file: ' + relative)
    return current


def load(path):
    if path.stat().st_size > 4_000_000:
        raise ValueError('JSON exceeds evidence limit')
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError('duplicate JSON key: ' + k)
            result[k] = v
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))


def names(value, field, minimum=1):
    if (not isinstance(value, list) or not minimum <= len(value) <= 100
            or any(not isinstance(x, str) or not x for x in value)
            or len(set(value)) != len(value)):
        raise ValueError('invalid unique list: ' + field)
    return value


def validate_trial(value, arm, seed, contract):
    if (not isinstance(value, dict) or set(value) != {'arm', 'seed', 'cases'}
            or value['arm'] != arm or type(value['seed']) is not int or value['seed'] != seed):
        raise ValueError('trial identity/shape mismatch')
    rows = value['cases']
    if not isinstance(rows, list) or len(rows) != len(contract['cases']):
        raise ValueError('case coverage mismatch')
    if {r.get('id') for r in rows if isinstance(r, dict)} != set(contract['cases']):
        raise ValueError('case identity mismatch')
    for row in rows:
        if set(row) != {'id', 'checks', 'metrics'}:
            raise ValueError('case fields mismatch')
        if (not isinstance(row['checks'], dict) or set(row['checks']) != set(contract['checks'])
                or any(type(v) is not bool for v in row['checks'].values())):
            raise ValueError('checks must be complete strict booleans')
        if (not isinstance(row['metrics'], dict) or set(row['metrics']) != set(contract['metrics'])
                or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0
                       for v in row['metrics'].values())):
            raise ValueError('metrics must be complete finite nonnegative numbers')


def execute(source, destination, suite, arm, seed, timeout, contract, model_env):
    shutil.copytree(source, destination)
    # Isolated *initial state*, not a security boundary against arbitrary code.
    (destination / 'home').mkdir()
    env = {'PATH': os.environ.get('PATH', ''), 'HOME': str(destination / 'home'),
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONHASHSEED': str(seed % 4294967296), **model_env}
    output = destination / 'result.json'
    command = [sys.executable, suite, arm, str(seed), str(output)]
    start = time.monotonic()
    with (destination / 'stdout.txt').open('wb') as stdout, (destination / 'stderr.txt').open('wb') as stderr:
        process = subprocess.Popen(command, cwd=destination, env=env, stdout=stdout,
                                   stderr=stderr, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise ValueError(f'trial timeout: {arm}/{seed}')
        finally:
            # Do not let child jobs outlive a trial, even if the parent exits first.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    elapsed = time.monotonic() - start
    if code:
        raise ValueError(f'trial exit {code}: {arm}/{seed}')
    for original in source.rglob('*'):
        if original.is_file():
            copy = destination / original.relative_to(source)
            if copy.is_symlink() or not copy.is_file() or copy.read_bytes() != original.read_bytes():
                raise ValueError('trial changed frozen source: ' + str(original.relative_to(source)))
    value = load(checked_path(destination, 'result.json'))
    validate_trial(value, arm, seed, contract)
    return {**value, 'wall_seconds': elapsed, 'directory': destination.name}


def evaluate(root, proposal_path, challenge_path):
    root = Path(root).resolve()
    out = root / 'artifacts' / 'evidence' / uuid.uuid4().hex
    out.mkdir(parents=True)
    report = {'valid': False, 'errors': [], 'trials': [], 'sources': {}, 'totals': {}}
    try:
        forwarded = {name.strip() for name in os.environ.get('DAQ_TRIAL_ENV', '').split(',') if name.strip()}
        if not forwarded <= MODEL_ENV or any(not os.environ.get(name) for name in forwarded):
            raise ValueError('DAQ_TRIAL_ENV contains unapproved or unset model transport names')
        model_env = {name: os.environ[name] for name in forwarded}
        report['forwarded_environment_names'] = sorted(forwarded)
        for path in (proposal_path, challenge_path):
            if not isinstance(path, str) or not path.startswith('artifacts/'):
                raise ValueError('submission manifests must be under artifacts/')
        pp, cp = checked_path(root, proposal_path), checked_path(root, challenge_path)
        proposal, challenge = load(pp), load(cp)
        if not isinstance(proposal, dict) or not isinstance(challenge, dict):
            raise ValueError('manifest roots must be JSON objects')
        if proposal.get('version') != 1 or challenge.get('version') != 1:
            raise ValueError('unsupported manifest version')
        if challenge.get('proposal') != proposal_path:
            raise ValueError('challenge does not bind this proposal')
        case_ids = names(proposal['cases'], 'cases', 2)
        added = names(challenge.get('cases', []), 'challenge cases', 0)
        if set(case_ids) & set(added):
            raise ValueError('challenge cases collide with proposal')
        contract = {'cases': case_ids + added,
                    'checks': names(proposal['checks'], 'checks'),
                    'metrics': names(proposal['metrics'], 'metrics')}
        seeds = proposal['seeds']
        if (not isinstance(seeds, list) or not 3 <= len(seeds) <= 20
                or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds)
                or len(set(seeds)) != len(seeds)):
            raise ValueError('require 3..20 unique integer seeds')
        timeout = proposal['timeout_sec']
        if type(timeout) is not int or not 1 <= timeout <= 120:
            raise ValueError('timeout_sec must be 1..120')
        source = out / 'source'
        source.mkdir()
        # Store exact manifests outside executable source; never reread mutable originals.
        (out / 'proposal.json').write_bytes(pp.read_bytes())
        (out / 'challenge.json').write_bytes(cp.read_bytes())
        used = {'contract.json', 'result.json', 'stdout.txt', 'stderr.txt', 'home'}
        for manifest, base in ((proposal, pp.parent), (challenge, cp.parent)):
            for name in names(manifest['files'], 'files'):
                original = checked_path(base, name)
                normalized = PurePosixPath(name).as_posix()
                if normalized in used or PurePosixPath(normalized).parts[0] in used:
                    raise ValueError('source collision or reserved name: ' + name)
                used.add(normalized)
                data = original.read_bytes()
                if len(data) > 8_000_000:
                    raise ValueError('source file exceeds size limit')
                target = source / normalized
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                report['sources'][normalized] = hashlib.sha256(data).hexdigest()
        checked_path(source, proposal['suite'])
        (source / 'contract.json').write_text(json.dumps(contract, sort_keys=True))
        report['environment'] = {'python': sys.version, 'executable': sys.executable,
            'packages': sorted(f'{d.metadata["Name"]}=={d.version}' for d in importlib.metadata.distributions())}
        report['runner_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        report['proposal'] = proposal
        report['challenge'] = challenge
        report['contract'] = contract
        # Alternate order to reduce systematic order bias; every arm starts from a fresh copy.
        for index, seed in enumerate(seeds):
            for arm in (('orc', 'baseline') if index % 2 == 0 else ('baseline', 'orc')):
                trial = execute(source, out / f'{index}-{arm}', proposal['suite'], arm, seed, timeout, contract, model_env)
                report['trials'].append(trial)
        for arm in ('orc', 'baseline'):
            rows = [r for t in report['trials'] if t['arm'] == arm for r in t['cases']]
            totals = {m: sum(r['metrics'][m] for r in rows) for m in contract['metrics']}
            if any(not math.isfinite(v) for v in totals.values()):
                raise ValueError('aggregate metric overflow')
            report['totals'][arm] = {'failed_checks': sum(not v for r in rows for v in r['checks'].values()),
                'metrics': totals}
        report['valid'] = True
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
    report['artifact_hashes'] = {}
    for path in out.rglob('*'):
        if path.is_symlink():
            report['valid'] = False
            report['errors'].append('symlink in evidence: ' + path.relative_to(out).as_posix())
        elif path.is_file():
            report['artifact_hashes'][path.relative_to(out).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    # The evidence ID covers the measurements as well as source identity.
    report['experiment_digest'] = digest(report)
    path = out / 'report.json'
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return {'valid': report['valid'], 'report': path.relative_to(root).as_posix(),
            'digest': report['experiment_digest']}


def verify(root, report_path, expected_digest):
    """Recheck cooperative evidence integrity after the provider review turns."""
    try:
        root = Path(root).resolve()
        if not report_path.startswith('artifacts/evidence/'):
            return False
        path = checked_path(root, report_path)
        report = load(path)
        stored = report.pop('experiment_digest')
        if stored != expected_digest or digest(report) != expected_digest:
            return False
        return all(hashlib.sha256(checked_path(path.parent, name).read_bytes()).hexdigest() == sha
                   for name, sha in report['artifact_hashes'].items())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


if __name__ == '__main__':
    if sys.argv[1] == 'verify':
        result = verify(Path.cwd(), *sys.argv[2:])
    else:
        result = evaluate(Path.cwd(), *sys.argv[1:])
    # This is the runtime's typed command-result channel, not parsed stdout.
    Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text(json.dumps(result))
