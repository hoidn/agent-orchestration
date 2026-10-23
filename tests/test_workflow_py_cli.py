"""Public Python commands reuse retained generated Lisp for ordinary resume."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.test_workflow_py_frontend import APPROVAL, manifests


def cli(root, *arguments, env=None):
    return subprocess.run([sys.executable, '-B', '-m', 'orchestrator', *arguments], cwd=root,
        env={**os.environ, 'PYTHONPATH': str(Path(__file__).parents[1]),
            'PATH': str(root / 'bin') + os.pathsep + os.environ['PATH'], **(env or {})},
        capture_output=True, text=True, check=False)


def test_py_build_and_check_report_checked_bundle(tmp_path):
    source = tmp_path / 'author.py'
    source.write_text('from orchestrator.py import workflow\n@workflow(returns=str)\ndef run(value: str): return value\n')
    for command in ['check', 'build']:
        result = cli(tmp_path, 'py', command, str(source))
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert Path(report['source_path']).is_file()
        assert Path(report['source_map_path']).is_file()
        assert report['program_digest']
        assert report['build_key']
    assert not (tmp_path / '.orchestrate' / 'runs').exists()


def test_entry_selection_requires_exactly_one_export(tmp_path):
    source = tmp_path / 'author.py'
    source.write_text('from orchestrator.py import workflow\n@workflow(returns=str)\ndef first(): return "one"\n@workflow(returns=str)\ndef second(): return "two"\n')
    assert cli(tmp_path, 'py', 'check', str(source)).returncode == 2
    selected = cli(tmp_path, 'py', 'check', str(source), '--entry-workflow', 'second')
    assert selected.returncode == 0, selected.stderr
    assert json.loads(selected.stdout)['entry_workflow'] == 'second::second'
    assert cli(tmp_path, 'py', 'check', str(source), '--entry-workflow', 'missing').returncode == 2


def test_py_run_reuses_runtime_inputs_state_and_retained_source(tmp_path):
    source = tmp_path / 'author.py'
    source.write_text('from orchestrator.py import workflow, Prompt, Text, ask, HostReply\nprompt=Prompt(file="question.md", fills={"text":Text}, returns=str)\n@workflow(returns=HostReply[str])\ndef run(text: str): return ask(prompt(text=text), returns=str)\n')
    template = tmp_path / 'question.md'
    template.write_text('{text}')
    inputs = tmp_path / 'inputs.json'
    inputs.write_text('{"text":"question"}')
    state = tmp_path / 'custom-runs'
    result = cli(tmp_path, 'py', 'run', str(source), '--input-file', str(inputs), '--state-dir', str(state), '--quiet')
    assert result.returncode == 0, result.stderr
    run_root, = [p for p in state.iterdir() if p.is_dir()]
    header = json.loads((run_root / 'run.json').read_text())
    assert header['workflow_file'].endswith('.orc')
    assert '.orchestrate/generated/' in header['workflow_file']
    source.unlink()
    template.unlink()
    request = json.loads(cli(tmp_path, 'input', 'get', run_root.name, '--state-dir', str(state)).stdout)
    settled = cli(tmp_path, 'input', 'answer', run_root.name, request['request_id'], '--state-dir', str(state), '--by', 'tester', '--value', '"accepted"')
    assert settled.returncode == 0, settled.stderr
    resumed = cli(tmp_path, 'resume', run_root.name, '--state-dir', str(state))
    assert resumed.returncode == 0, resumed.stderr
    assert cli(tmp_path, 'resume', run_root.name, '--state-dir', str(state)).returncode == 0
    assert json.loads((run_root / 'state.json').read_text())['status'] == 'completed'


@pytest.mark.parametrize('source', ['from orchestrator.py import workflow\nraise RuntimeError("author import failed")\n',
    'from orchestrator.py import workflow\n@workflow(returns=str)\ndef run(value: str): return str(value)\n'])
def test_py_failure_is_located_and_creates_no_run(tmp_path, source):
    path = tmp_path / 'author.py'
    path.write_text(source)
    result = cli(tmp_path, 'py', 'check', str(path))
    assert result.returncode == 2
    assert 'author.py' in result.stderr
    assert not (tmp_path / '.orchestrate' / 'runs').exists()


def test_py_has_no_resume_and_run_still_requires_orc(tmp_path):
    source = tmp_path / 'author.py'
    source.write_text('raise RuntimeError("must not import")')
    assert cli(tmp_path, 'py', 'resume', str(source)).returncode == 2
    refused = cli(tmp_path, 'run', str(source))
    assert refused.returncode != 0
    assert 'must not import' not in refused.stderr


@pytest.mark.parametrize('mutation', ['changed', 'missing'])
def test_generated_source_mutation_refuses_ordinary_resume(tmp_path, mutation):
    source = tmp_path / 'author.py'
    source.write_text('from orchestrator.py import workflow, ask, HostReply\n@workflow(returns=HostReply[str])\ndef run(): return ask("question", returns=str)\n')
    started = cli(tmp_path, 'py', 'run', str(source), '--quiet')
    assert started.returncode == 0, started.stderr
    root, = (tmp_path / '.orchestrate' / 'runs').iterdir()
    header = json.loads((root / 'run.json').read_text())
    generated = tmp_path / header['workflow_file']
    if mutation == 'changed': generated.write_text(generated.read_text().replace('"question"', '"changed"'))
    else: generated.unlink()
    before = (root / 'memo.jsonl').read_bytes()
    request = json.loads(cli(tmp_path, 'input', 'get', root.name).stdout)
    settled = cli(tmp_path, 'input', 'answer', root.name, request['request_id'], '--by', 'tester', '--value', '"accepted"')
    assert settled.returncode == 2, settled.stderr
    assert 'Traceback' not in settled.stderr
    resumed = cli(tmp_path, 'resume', root.name)
    assert resumed.returncode == 2, resumed.stderr
    assert 'Traceback' not in resumed.stderr
    assert (root / 'memo.jsonl').read_bytes() == before


def test_runtime_doc_change_remains_semantic_replay_divergence(tmp_path):
    source = tmp_path / 'author.py'
    source.write_text('''from orchestrator.py import *
class Report(RelPath, under="inputs", must_exist=True): pass
question=Prompt(text="{text}", fills={"text":Text,"doc":Doc[Report]}, returns=str)
@workflow(returns=HostReply[str])
def run(report: Report): return ask(question(text="review",doc=report), returns=str)
''')
    (tmp_path / 'inputs').mkdir()
    document = tmp_path / 'inputs' / 'report.md'
    document.write_text('initial')
    started = cli(tmp_path, 'py', 'run', str(source), '--input', 'report=inputs/report.md', '--quiet')
    assert started.returncode == 0, started.stderr
    root, = (tmp_path / '.orchestrate' / 'runs').iterdir()
    request = json.loads(cli(tmp_path, 'input', 'get', root.name).stdout)
    document.write_text('changed')
    before = (root / 'memo.jsonl').read_bytes()
    settled = cli(tmp_path, 'input', 'answer', root.name, request['request_id'], '--by', 'tester', '--value', '"accepted"', '--accept-changed-evidence')
    assert settled.returncode == 2
    assert 'effect_input_diverged' in settled.stderr
    assert 'Traceback' not in settled.stderr
    resumed = cli(tmp_path, 'resume', root.name)
    assert resumed.returncode == 2
    assert 'effect_input_diverged' in resumed.stderr
    assert 'Traceback' not in resumed.stderr
    assert (root / 'memo.jsonl').read_bytes() == before


def test_source_map_is_not_resume_authority(tmp_path):
    source = tmp_path / 'author.py'
    source.write_text('from orchestrator.py import workflow, ask, HostReply\n@workflow(returns=HostReply[str])\ndef run(): return ask("question", returns=str)\n')
    assert cli(tmp_path, 'py', 'run', str(source), '--quiet').returncode == 0
    root, = (tmp_path / '.orchestrate' / 'runs').iterdir()
    header = json.loads((root / 'run.json').read_text())
    generated = tmp_path / header['workflow_file']
    (generated.parent / 'source_map.json').unlink()
    request = json.loads(cli(tmp_path, 'input', 'get', root.name).stdout)
    settled = cli(tmp_path, 'input', 'answer', root.name, request['request_id'], '--by', 'tester', '--value', '"accepted"')
    assert settled.returncode == 0, settled.stderr
    assert cli(tmp_path, 'resume', root.name).returncode == 0
