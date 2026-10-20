"""Zero-call ORC collection uses the actual workspace without touching its index."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.compare import prepare, repos


@pytest.fixture
def zero(tmp_path):
    candidate = tmp_path / 'candidate'
    candidate.mkdir()
    repos.git(candidate, 'init', '-q')
    (candidate / 'tracked.txt').write_text('base\n')
    repos.git(candidate, 'add', '.')
    repos.git(candidate, *repos.SEED_COMMIT)
    records = tmp_path / 'records'
    (records / 'calls').mkdir(parents=True)
    state = tmp_path / 'state/r1'
    state.mkdir(parents=True)
    (state / 'memo.jsonl').write_text(json.dumps({'record': 'terminal', 'outcome': 'completed', 'value': {}}) + '\n')
    record = {'arm': 'dynamic', 'arm_kind': 'orc', 'candidates': [str(candidate)],
              'compare_base': repos.git(candidate, 'rev-parse', 'HEAD'), 'state_root': str(state.parent)}
    repos.dump(records / 'record.json', record)
    return records, candidate, state


def test_zero_call_collection_preserves_real_index_and_captures_tracked_and_new_files(zero):
    records, candidate, _state = zero
    (candidate / 'tracked.txt').write_text('staged\n')
    repos.git(candidate, 'add', 'tracked.txt')
    subprocess.run([sys.executable, '-c',
        "from pathlib import Path; Path('tracked.txt').write_text('worktree\\n'); Path('new.txt').write_text('new file\\n')"],
        cwd=candidate, check=True)
    index = candidate / '.git/index'
    original = index.read_bytes()
    first = prepare.collect(records)
    patch = (records / first['patches']['final']).read_text()
    assert '+worktree' in patch and '+new file' in patch
    assert index.read_bytes() == original
    assert prepare.collect(records)['patches'] == first['patches']
    assert index.read_bytes() == original
    (candidate / 'new.txt').write_text('later\n')
    with pytest.raises(SystemExit, match='changed'):
        prepare.collect(records)
    assert index.read_bytes() == original


def test_zero_call_collection_rejects_missing_physical_calls_directory(zero):
    records, _candidate, _state = zero
    (records / 'calls').rmdir()
    with pytest.raises(SystemExit):
        prepare.collect(records)


def test_zero_call_collection_rejects_provider_starts_without_shim_calls(zero):
    records, _candidate, state = zero
    path = state / 'memo.jsonl'
    terminal = path.read_text()
    path.write_text(json.dumps({'record': 'started', 'input_parts': {'prompt': 'sha256:missing'}}) + '\n' + terminal)
    with pytest.raises(SystemExit, match='provider starts'):
        prepare.collect(records)


def test_generic_python_zero_call_collection_keeps_its_rejection(zero):
    records, _candidate, state = zero
    record = repos.load(records / 'record.json') | {'arm_kind': 'generic-command'}
    repos.dump(records / 'record.json', record)
    repos.dump(state / 'terminal.json', {'outcome': 'completed', 'failure': None, 'calls': 0,
                                       'started_at': 0, 'finished_at': 1})
    with pytest.raises(SystemExit, match='no call directories'):
        prepare.collect(records)
