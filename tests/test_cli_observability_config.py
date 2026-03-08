"""Tests for runtime observability configuration (CLI/state, no DSL)."""

import hashlib
import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import build_observability_config, run_workflow
from orchestrator.cli.main import create_parser
from orchestrator.state import StateManager


def _base_run_args(workflow_path: Path) -> Namespace:
    return Namespace(
        workflow=str(workflow_path),
        context=None,
        context_file=None,
        clean_processed=False,
        archive_processed=None,
        debug=False,
        stream_output=False,
        dry_run=False,
        backup_state=False,
        state_dir=None,
        on_error='stop',
        max_retries=0,
        retry_delay=1000,
        quiet=False,
        verbose=False,
        log_level='info',
        step_summaries=False,
        summary_mode=None,
        summary_provider='claude_sonnet_summary',
        summary_timeout_sec=120,
        summary_max_input_chars=12000,
    )


def test_parser_accepts_summary_flags():
    parser = create_parser()
    args = parser.parse_args(
        [
            'run',
            'workflow.yaml',
            '--step-summaries',
            '--summary-mode',
            'sync',
            '--summary-provider',
            'claude_custom',
            '--summary-timeout-sec',
            '45',
            '--summary-max-input-chars',
            '2048',
        ]
    )

    assert args.step_summaries is True
    assert args.summary_mode == 'sync'
    assert args.summary_provider == 'claude_custom'
    assert args.summary_timeout_sec == 45
    assert args.summary_max_input_chars == 2048


def test_parser_accepts_stream_output_on_run_and_resume():
    parser = create_parser()

    run_args = parser.parse_args(
        [
            'run',
            'workflow.yaml',
            '--stream-output',
        ]
    )
    resume_args = parser.parse_args(
        [
            'resume',
            'run-123',
            '--stream-output',
        ]
    )
    run_default_args = parser.parse_args(['run', 'workflow.yaml'])

    assert run_args.stream_output is True
    assert resume_args.stream_output is True
    assert run_default_args.stream_output is False


def test_parser_accepts_state_dir_on_run_and_resume():
    parser = create_parser()

    run_args = parser.parse_args(
        [
            'run',
            'workflow.yaml',
            '--state-dir',
            '/tmp/custom-runs',
        ]
    )
    resume_args = parser.parse_args(
        [
            'resume',
            'run-123',
            '--state-dir',
            '/tmp/custom-runs',
        ]
    )

    assert run_args.state_dir == '/tmp/custom-runs'
    assert resume_args.state_dir == '/tmp/custom-runs'


def test_build_observability_config_defaults_to_async_when_enabled():
    args = _base_run_args(Path('workflow.yaml'))
    args.step_summaries = True

    config = build_observability_config(args)

    assert config is not None
    assert config['step_summaries']['enabled'] is True
    assert config['step_summaries']['mode'] == 'async'


def test_build_observability_config_mode_enables_summaries():
    args = _base_run_args(Path('workflow.yaml'))
    args.summary_mode = 'sync'

    config = build_observability_config(args)

    assert config is not None
    assert config['step_summaries']['enabled'] is True
    assert config['step_summaries']['mode'] == 'sync'


@patch('orchestrator.cli.commands.run.WorkflowExecutor')
@patch('orchestrator.cli.commands.run.StateManager')
@patch('orchestrator.cli.commands.run.WorkflowLoader')
def test_run_workflow_persists_observability_runtime_config(mock_loader, mock_state, mock_executor, tmp_path, monkeypatch):
    workflow_file = tmp_path / 'workflow.yaml'
    workflow_file.write_text('version: "1.3"\nname: test\nsteps: []\n')
    monkeypatch.chdir(tmp_path)

    mock_loader.return_value.load.return_value = {
        'version': '1.3',
        'name': 'test',
        'steps': [],
        'context': {},
    }

    state_inst = MagicMock()
    state_inst.logs_dir = tmp_path / '.orchestrate' / 'runs' / 'test-run' / 'logs'
    state_inst.initialize.return_value = MagicMock(run_id='test-run')
    mock_state.return_value = state_inst

    exec_inst = MagicMock()
    exec_inst.execute.return_value = True
    mock_executor.return_value = exec_inst

    args = _base_run_args(workflow_file)
    args.step_summaries = True

    result = run_workflow(args)

    assert result == 0

    init_kwargs = state_inst.initialize.call_args.kwargs
    assert init_kwargs['observability']['step_summaries']['mode'] == 'async'
    assert init_kwargs['observability']['step_summaries']['provider'] == 'claude_sonnet_summary'

    exec_kwargs = mock_executor.call_args.kwargs
    assert exec_kwargs['observability']['step_summaries']['mode'] == 'async'


@patch('orchestrator.cli.commands.resume.WorkflowExecutor')
@patch('orchestrator.cli.commands.resume.WorkflowLoader')
def test_resume_uses_persisted_observability_and_applies_override(mock_loader, mock_executor, tmp_path, monkeypatch):
    run_id = 'run-123'
    monkeypatch.chdir(tmp_path)

    workflow_path = tmp_path / 'workflow.yaml'
    workflow_content = 'version: "1.3"\nname: test\nsteps: []\n'
    workflow_path.write_text(workflow_content)
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    run_dir = tmp_path / '.orchestrate' / 'runs' / run_id
    run_dir.mkdir(parents=True)

    state = {
        'schema_version': StateManager.SCHEMA_VERSION,
        'run_id': run_id,
        'workflow_file': str(workflow_path),
        'workflow_checksum': checksum,
        'started_at': '2026-02-27T00:00:00+00:00',
        'updated_at': '2026-02-27T00:00:01+00:00',
        'status': 'running',
        'context': {},
        'steps': {},
        'observability': {
            'step_summaries': {
                'enabled': True,
                'mode': 'async',
                'provider': 'claude_sonnet_summary',
                'timeout_sec': 120,
                'max_input_chars': 12000,
                'best_effort': True,
            }
        },
    }
    (run_dir / 'state.json').write_text(json.dumps(state, indent=2))

    mock_loader.return_value.load.return_value = {
        'version': '1.3',
        'name': 'test',
        'steps': [],
        'context': {},
    }

    exec_inst = MagicMock()
    exec_inst.execute.return_value = {'status': 'completed'}
    mock_executor.return_value = exec_inst

    result = resume_workflow(
        run_id=run_id,
        summary_mode='sync',
    )

    assert result == 0
    exec_kwargs = mock_executor.call_args.kwargs
    assert exec_kwargs['observability']['step_summaries']['mode'] == 'sync'

    persisted = json.loads((run_dir / 'state.json').read_text())
    assert persisted['observability']['step_summaries']['mode'] == 'sync'


@patch('orchestrator.cli.commands.resume.WorkflowExecutor')
@patch('orchestrator.cli.commands.resume.WorkflowLoader')
def test_resume_workflow_passes_stream_output_to_executor(mock_loader, mock_executor, tmp_path, monkeypatch):
    run_id = 'run-123'
    monkeypatch.chdir(tmp_path)

    workflow_path = tmp_path / 'workflow.yaml'
    workflow_content = 'version: "1.3"\nname: test\nsteps: []\n'
    workflow_path.write_text(workflow_content)
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    run_dir = tmp_path / '.orchestrate' / 'runs' / run_id
    run_dir.mkdir(parents=True)
    (run_dir / 'state.json').write_text(
        json.dumps(
                {
                    'schema_version': StateManager.SCHEMA_VERSION,
                    'run_id': run_id,
                    'workflow_file': str(workflow_path),
                    'workflow_checksum': checksum,
                'started_at': '2026-02-27T00:00:00+00:00',
                'updated_at': '2026-02-27T00:00:01+00:00',
                'status': 'running',
                'context': {},
                'steps': {},
            },
            indent=2,
        )
    )

    mock_loader.return_value.load.return_value = {
        'version': '1.3',
        'name': 'test',
        'steps': [],
        'context': {},
    }

    exec_inst = MagicMock()
    exec_inst.execute.return_value = {'status': 'completed'}
    mock_executor.return_value = exec_inst

    result = resume_workflow(
        run_id=run_id,
        stream_output=True,
    )

    assert result == 0
    exec_kwargs = mock_executor.call_args.kwargs
    assert exec_kwargs['stream_output'] is True
