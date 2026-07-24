"""Tests for runtime observability configuration (CLI/state, no DSL)."""

import hashlib
import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import build_observability_config
from orchestrator.cli.main import create_parser
from orchestrator.state import StateManager
from tests.workflow_fixture_loader import WorkflowLoader


def _write_minimal_test_bundle(workflow_path: Path, *, version: str = "2.14"):
    workflow_content = json.dumps(
        {
            "version": version,
            "name": "test",
            "steps": [{"name": "Noop", "command": ["true"]}],
        }
    )
    workflow_path.write_text(workflow_content, encoding="utf-8")
    return WorkflowLoader(workflow_path.parent).load_bundle(workflow_path)


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
        summary_profile=None,
        live_agent_notes=False,
        live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000,
    )


def test_parser_accepts_summary_flags():
    parser = create_parser()
    args = parser.parse_args(
        [
            'run',
            'workflow.orc',
            '--step-summaries',
            '--summary-mode',
            'sync',
            '--summary-provider',
            'claude_custom',
            '--summary-timeout-sec',
            '45',
            '--summary-max-input-chars',
            '2048',
            '--summary-profile',
            'phase-performance',
            '--live-agent-notes',
            '--live-agent-note-provider',
            'claude_haiku_summary',
            '--live-agent-note-interval-sec',
            '7.5',
            '--live-agent-note-timeout-sec',
            '20',
            '--live-agent-note-max-tail-chars',
            '4096',
        ]
    )

    assert args.step_summaries is True
    assert args.summary_mode == 'sync'
    assert args.summary_provider == 'claude_custom'
    assert args.summary_timeout_sec == 45
    assert args.summary_max_input_chars == 2048
    assert args.summary_profile == 'phase-performance'
    assert args.live_agent_notes is True
    assert args.live_agent_note_provider == 'claude_haiku_summary'
    assert args.live_agent_note_interval_sec == 7.5
    assert args.live_agent_note_timeout_sec == 20
    assert args.live_agent_note_max_tail_chars == 4096


def test_parser_accepts_stream_output_on_run_and_resume():
    parser = create_parser()

    run_args = parser.parse_args(
        [
            'run',
            'workflow.orc',
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
    run_default_args = parser.parse_args(['run', 'workflow.orc'])

    assert run_args.stream_output is True
    assert resume_args.stream_output is True
    assert run_default_args.stream_output is False


def test_parser_accepts_state_dir_on_run_and_resume():
    parser = create_parser()

    run_args = parser.parse_args(
        [
            'run',
            'workflow.orc',
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


def test_parser_defaults_retry_budget_on_run_and_resume():
    parser = create_parser()

    run_args = parser.parse_args(['run', 'workflow.orc'])
    resume_args = parser.parse_args(['resume', 'run-123'])

    assert run_args.max_retries == 1
    assert run_args.retry_delay == 1000
    assert resume_args.max_retries == 1
    assert resume_args.retry_delay == 1000


def test_parser_accepts_retry_flags_on_resume():
    parser = create_parser()

    args = parser.parse_args(
        [
            'resume',
            'run-123',
            '--max-retries',
            '4',
            '--retry-delay',
            '2500',
        ]
    )

    assert args.max_retries == 4
    assert args.retry_delay == 2500


def test_build_observability_config_defaults_to_async_when_enabled():
    args = _base_run_args(Path('workflow.orc'))
    args.step_summaries = True

    config = build_observability_config(args)

    assert config is not None
    assert config['step_summaries']['enabled'] is True
    assert config['step_summaries']['mode'] == 'async'


def test_build_observability_config_mode_enables_summaries():
    args = _base_run_args(Path('workflow.orc'))
    args.summary_mode = 'sync'

    config = build_observability_config(args)

    assert config is not None
    assert config['step_summaries']['enabled'] is True
    assert config['step_summaries']['mode'] == 'sync'


def test_build_observability_config_profile_enables_summaries():
    args = _base_run_args(Path('workflow.orc'))
    args.summary_profile = 'phase-performance'

    config = build_observability_config(args)

    assert config is not None
    assert config['step_summaries']['enabled'] is True
    assert config['step_summaries']['profile'] == 'phase-performance'


def test_build_observability_config_includes_live_agent_notes():
    args = _base_run_args(Path('workflow.orc'))
    args.live_agent_notes = True
    args.summary_provider = 'general_summary'
    args.live_agent_note_provider = 'cheap_summary'
    args.live_agent_note_interval_sec = 5.0
    args.live_agent_note_timeout_sec = 9
    args.live_agent_note_max_tail_chars = 1234

    config = build_observability_config(args)

    assert config is not None
    live_cfg = config['step_summaries']['live_agent_notes']
    assert live_cfg == {
        'enabled': True,
        'provider': 'cheap_summary',
        'interval_sec': 5.0,
        'timeout_sec': 9,
        'max_tail_chars': 1234,
        'source': 'tmux',
    }


def test_build_observability_config_defaults_live_agent_notes_to_haiku_provider():
    args = _base_run_args(Path('workflow.orc'))
    args.live_agent_notes = True

    config = build_observability_config(args)

    assert config is not None
    live_cfg = config['step_summaries']['live_agent_notes']
    assert live_cfg['provider'] == 'claude_haiku_summary'
    assert live_cfg['source'] == 'tmux'


@patch('orchestrator.cli.commands.resume.build_frontend_bundle', create=True)
@patch('orchestrator.cli.commands.resume.WorkflowExecutor')
def test_resume_workflow_reuses_orc_launch_metadata_from_monitor_process(
    mock_executor,
    mock_build_frontend_bundle,
    tmp_path,
    monkeypatch,
):
    run_id = 'run-orc'
    monkeypatch.chdir(tmp_path)

    workflow_path = tmp_path / 'workflow.orc'
    workflow_content = '(workflow-lisp (:language "0.1") (:target-dsl "2.14"))\n'
    workflow_path.write_text(workflow_content, encoding='utf-8')
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    source_root = tmp_path / 'src-root'
    providers = tmp_path / 'providers.json'
    prompts = tmp_path / 'prompts.json'
    imports = tmp_path / 'imports.json'
    commands = tmp_path / 'commands.json'
    source_root.mkdir()
    for path in (providers, prompts, imports, commands):
        path.write_text(r"""{}
""", encoding='utf-8')

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
        ),
        encoding='utf-8',
    )
    (run_dir / 'monitor_process.json').write_text(
        json.dumps(
            {
                'schema': 'orchestrator-monitor-process/v1',
                'pid': 12345,
                'started_at': '2026-02-27T00:00:00+00:00',
                'argv': [
                    'orchestrator',
                    'run',
                    str(workflow_path),
                    '--entry-workflow',
                    'selected-entry',
                    '--source-root',
                    str(source_root),
                    '--provider-externs-file',
                    str(providers),
                    '--prompt-externs-file',
                    str(prompts),
                    '--imported-workflow-bundles-file',
                    str(imports),
                    '--command-boundaries-file',
                    str(commands),
                ],
            },
            indent=2,
        ),
        encoding='utf-8',
    )

    workflow_bundle = _write_minimal_test_bundle(
        tmp_path / "orc_resume_audit_fixture.json",
    )
    mock_build_frontend_bundle.return_value = SimpleNamespace(
        validated_bundle=workflow_bundle,
        manifest=SimpleNamespace(lowering_schema_version=1),
    )
    exec_inst = MagicMock()
    exec_inst.execute.return_value = {'status': 'completed'}
    mock_executor.return_value = exec_inst

    result = resume_workflow(run_id=run_id)

    assert result == 0
    request = mock_build_frontend_bundle.call_args.args[0]
    assert request.source_path == workflow_path
    assert request.entry_workflow == 'selected-entry'
    assert request.source_roots == (source_root,)
    assert request.provider_externs_path == providers
    assert request.prompt_externs_path == prompts
    assert request.imported_workflow_bundles_path == imports
    assert request.command_boundaries_path == commands
