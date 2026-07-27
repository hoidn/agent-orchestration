"""Tests for CLI safety features (AT-11, AT-12, AT-16)."""

import json
import os
import shutil
import tempfile
import zipfile
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch, MagicMock

from orchestrator.cli.commands.run import (
    validate_clean_processed,
    clean_processed_directory,
    validate_archive_destination,
    archive_processed_directory,
    parse_context,
    run_workflow
)
from tests.workflow_fixture_loader import WorkflowLoader
from orchestrator.state import StateManager


DEFAULT_WORKFLOW_MAPPING = {
    'version': '1.1',
    'name': 'test',
    'steps': [{'name': 'test', 'command': ['echo', 'test']}],
}


def _state_manager_mock(workspace: Path) -> MagicMock:
    prototype = StateManager(workspace=workspace)
    manager = MagicMock(spec=prototype)
    manager.run_root = prototype.run_root
    manager.logs_dir = prototype.logs_dir
    manager.state = MagicMock()
    assert isinstance(manager, StateManager)
    return manager


def _run_args(workflow: Path, **overrides) -> Namespace:
    """Build a fully populated run_workflow Namespace, current CLI surface."""
    args = Namespace(
        workflow=str(workflow),
        context=None,
        context_file=None,
        input=None,
        input_file=None,
        clean_processed=False,
        archive_processed=None,
        dry_run=False,
        debug=False,
        quiet=False,
        verbose=False,
        log_level='info',
        backup_state=False,
        state_dir=None,
        on_error='stop',
        max_retries=0,
        retry_delay=1000,
        stream_output=False,
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
        entry_workflow=None,
        source_root=None,
        provider_externs_file=None,
        prompt_externs_file=None,
        imported_workflow_bundles_file=None,
        command_boundaries_file=None,
        emit_debug_yaml=False,
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


class TestCLISafety(TestCase):
    """Test CLI safety features."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.workspace = self.test_dir / 'workspace'
        self.workspace.mkdir()

        # Fresh runs require an .orc path; run_workflow's frontend build is
        # mocked in the tests below, so this placeholder is never compiled.
        self.workflow_file = self.workspace / 'workflow.orc'
        self.workflow_file.write_text("(workflow-lisp)\n")

        # Create processed directory
        self.processed_dir = self.workspace / 'processed'
        self.processed_dir.mkdir()

        # Create some files in processed
        (self.processed_dir / 'task1.txt').write_text('task 1')
        (self.processed_dir / 'subdir').mkdir()
        (self.processed_dir / 'subdir' / 'task2.txt').write_text('task 2')

        # Save original cwd
        self.original_cwd = Path.cwd()
        os.chdir(self.workspace)

    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def _stub_frontend_build(self, mock_build, mapping=None) -> SimpleNamespace:
        """Stand in for build_frontend_bundle with a fixture-loaded bundle."""
        bundle = WorkflowLoader(self.workspace).load_mapping(mapping or DEFAULT_WORKFLOW_MAPPING)
        mock_build.return_value = SimpleNamespace(
            validated_bundle=bundle,
            manifest=SimpleNamespace(lowering_schema_version=1),
        )
        return bundle

    def test_at11_clean_processed_empties_directory(self):
        """AT-11: Clean processed empties directory."""
        # Verify files exist
        self.assertTrue((self.processed_dir / 'task1.txt').exists())
        self.assertTrue((self.processed_dir / 'subdir' / 'task2.txt').exists())

        # Clean directory
        clean_processed_directory(self.processed_dir)

        # Directory should exist but be empty
        self.assertTrue(self.processed_dir.exists())
        self.assertEqual(list(self.processed_dir.iterdir()), [])

    def test_at11_clean_processed_handles_missing_directory(self):
        """AT-11: Clean processed handles missing directory gracefully."""
        missing_dir = self.workspace / 'missing'
        self.assertFalse(missing_dir.exists())

        # Should not raise error
        clean_processed_directory(missing_dir)

    def test_at12_archive_processed_creates_zip(self):
        """AT-12: Archive processed creates zip on success."""
        archive_dest = self.workspace / 'archive.zip'

        # Archive directory
        archive_processed_directory(self.processed_dir, archive_dest)

        # Verify archive created
        self.assertTrue(archive_dest.exists())

        # Verify archive contents
        with zipfile.ZipFile(archive_dest, 'r') as zf:
            names = zf.namelist()
            self.assertIn('processed/task1.txt', names)
            self.assertIn('processed/subdir/task2.txt', names)

            # Verify file content
            with zf.open('processed/task1.txt') as f:
                self.assertEqual(f.read().decode(), 'task 1')

    def test_at12_archive_processed_handles_empty_directory(self):
        """AT-12: Archive processed handles empty directory."""
        # Clean directory first
        clean_processed_directory(self.processed_dir)

        archive_dest = self.workspace / 'archive.zip'
        archive_processed_directory(self.processed_dir, archive_dest)

        # Archive should be created even for empty directory
        self.assertTrue(archive_dest.exists())

        with zipfile.ZipFile(archive_dest, 'r') as zf:
            self.assertEqual(len(zf.namelist()), 0)

    def test_at16_clean_processed_fails_outside_workspace(self):
        """AT-16: CLI Safety - clean fails if processed dir is outside WORKSPACE."""
        # Create directory outside workspace
        outside_dir = self.test_dir / 'outside'
        outside_dir.mkdir()

        # Should fail validation
        with self.assertRaises(ValueError) as ctx:
            validate_clean_processed(self.workflow_file, outside_dir)

        self.assertIn('outside WORKSPACE', str(ctx.exception))

    def test_at16_clean_processed_fails_for_workspace_root(self):
        """AT-16: CLI Safety - cannot clean workspace root."""
        # Should fail validation
        with self.assertRaises(ValueError) as ctx:
            validate_clean_processed(self.workflow_file, self.workspace)

        self.assertIn('cannot clean WORKSPACE root', str(ctx.exception))

    def test_at16_clean_processed_fails_for_parent_directory(self):
        """AT-16: CLI Safety - cannot clean parent of workspace."""
        # Should fail validation
        with self.assertRaises(ValueError) as ctx:
            validate_clean_processed(self.workflow_file, self.test_dir)

        self.assertIn('outside WORKSPACE', str(ctx.exception))

    def test_at16_clean_processed_allows_subdirectory(self):
        """AT-16: CLI Safety - allows cleaning subdirectory within workspace."""
        # Should pass validation
        validate_clean_processed(self.workflow_file, self.processed_dir)

    def test_archive_destination_validation_fails_inside_processed(self):
        """Archive destination cannot be inside processed directory."""
        archive_dest = self.processed_dir / 'archive.zip'

        with self.assertRaises(ValueError) as ctx:
            validate_archive_destination(self.processed_dir, archive_dest)

        self.assertIn('cannot be inside processed directory', str(ctx.exception))

    def test_archive_destination_validation_allows_outside_processed(self):
        """Archive destination allowed outside processed directory."""
        archive_dest = self.workspace / 'archive.zip'

        # Should pass validation
        validate_archive_destination(self.processed_dir, archive_dest)

    def test_parse_context_from_args(self):
        """Parse context from KEY=VALUE arguments."""
        args = MagicMock()
        args.context = ['key1=value1', 'key2=value2', 'key3=has=equals']
        args.context_file = None

        context = parse_context(args)

        self.assertEqual(context, {
            'key1': 'value1',
            'key2': 'value2',
            'key3': 'has=equals'
        })

    def test_parse_context_from_file(self):
        """Parse context from JSON file."""
        context_file = self.workspace / 'context.json'
        context_file.write_text(json.dumps({
            'key1': 'value1',
            'key2': 123,  # Should be converted to string
            'key3': True  # Should be converted to string
        }))

        args = MagicMock()
        args.context = None
        args.context_file = str(context_file)

        context = parse_context(args)

        self.assertEqual(context, {
            'key1': 'value1',
            'key2': '123',
            'key3': 'True'
        })

    def test_parse_context_combined(self):
        """Parse context from both args and file."""
        context_file = self.workspace / 'context.json'
        context_file.write_text(json.dumps({
            'file_key': 'file_value'
        }))

        args = MagicMock()
        args.context = ['arg_key=arg_value']
        args.context_file = str(context_file)

        context = parse_context(args)

        self.assertEqual(context, {
            'arg_key': 'arg_value',
            'file_key': 'file_value'
        })

    def test_parse_context_merges_workflow_defaults(self):
        """Workflow context defaults should be present without CLI inputs."""
        args = MagicMock()
        args.context = None
        args.context_file = None

        context = parse_context(args, workflow_context={
            'max_review_cycles': 3,
            'stage': 'A',
        })

        self.assertEqual(context, {
            'max_review_cycles': '3',
            'stage': 'A',
        })

    def test_parse_context_cli_overrides_workflow_defaults(self):
        """CLI/context-file values override workflow context defaults."""
        context_file = self.workspace / 'context.json'
        context_file.write_text(json.dumps({
            'stage': 'C'
        }))

        args = MagicMock()
        args.context = ['max_review_cycles=5']
        args.context_file = str(context_file)

        context = parse_context(args, workflow_context={
            'max_review_cycles': '3',
            'stage': 'A',
        })

        self.assertEqual(context, {
            'max_review_cycles': '5',
            'stage': 'C',
        })

    @patch('orchestrator.cli.commands.run.WorkflowExecutor')
    @patch('orchestrator.cli.commands.run.StateManager')
    @patch('orchestrator.cli.commands.run.build_frontend_bundle')
    def test_run_workflow_passes_state_dir_override_to_state_manager(self, mock_build, mock_state, mock_executor):
        """run_workflow should honor the documented --state-dir override."""
        self._stub_frontend_build(mock_build)

        mock_state_inst = _state_manager_mock(self.workspace)
        mock_state_inst.logs_dir = Path('/tmp/custom-runs') / 'test-run-123' / 'logs'
        mock_state_inst.initialize.return_value = MagicMock(run_id='test-run-123')
        mock_state.return_value = mock_state_inst

        mock_executor_inst = MagicMock()
        mock_executor_inst.execute.return_value = True
        mock_executor.return_value = mock_executor_inst

        args = _run_args(self.workflow_file, state_dir='/tmp/custom-runs')

        result = run_workflow(args)

        self.assertEqual(result, 0)
        state_kwargs = mock_state.call_args.kwargs
        self.assertEqual(state_kwargs['state_dir'], Path('/tmp/custom-runs').resolve())

    @patch('orchestrator.cli.commands.run.WorkflowExecutor')
    @patch('orchestrator.cli.commands.run.StateManager')
    @patch('orchestrator.cli.commands.run.build_frontend_bundle')
    def test_run_workflow_passes_merged_context_to_state(self, mock_build, mock_state, mock_executor):
        """run_workflow should initialize state with workflow context defaults plus CLI overrides."""
        self._stub_frontend_build(mock_build, {
            'version': '1.1',
            'name': 'test',
            'context': {
                'max_review_cycles': '3',
                'mode': 'default',
            },
            'steps': [{'name': 'test', 'command': ['bash', '-lc', 'true']}],
        })

        mock_state_inst = _state_manager_mock(self.workspace)
        mock_state_inst.initialize.return_value = MagicMock(run_id='test-run-123')
        mock_state.return_value = mock_state_inst

        mock_executor_inst = MagicMock()
        mock_executor_inst.execute.return_value = True
        mock_executor.return_value = mock_executor_inst

        args = _run_args(self.workflow_file, context=['mode=cli'])

        result = run_workflow(args)

        self.assertEqual(result, 0)
        call_args, _ = mock_state_inst.initialize.call_args
        self.assertEqual(call_args[1], {
            'max_review_cycles': '3',
            'mode': 'cli',
            'workflow_lisp': {'lowering_schema_version': 1},
        })

    @patch('orchestrator.cli.commands.run.WorkflowExecutor')
    @patch('orchestrator.cli.commands.run.StateManager')
    @patch('orchestrator.cli.commands.run.build_frontend_bundle')
    def test_run_workflow_passes_bound_inputs_to_state(self, mock_build, mock_state, mock_executor):
        """Workflow-signature runs should bind typed CLI inputs before state initialization."""
        self._stub_frontend_build(mock_build, {
            'version': '2.1',
            'name': 'signature-test',
            'inputs': {
                'max_cycles': {'kind': 'scalar', 'type': 'integer'},
            },
            'steps': [{'name': 'test', 'command': ['bash', '-lc', 'true']}],
        })

        mock_state_inst = _state_manager_mock(self.workspace)
        mock_state_inst.initialize.return_value = MagicMock(run_id='test-run-123')
        mock_state.return_value = mock_state_inst

        mock_executor_inst = MagicMock()
        mock_executor_inst.execute.return_value = True
        mock_executor.return_value = mock_executor_inst

        args = _run_args(self.workflow_file, input=['max_cycles=5'])

        result = run_workflow(args)

        self.assertEqual(result, 0)
        init_kwargs = mock_state_inst.initialize.call_args.kwargs
        self.assertEqual(init_kwargs['bound_inputs'], {'max_cycles': 5})

    @patch('orchestrator.cli.commands.run.WorkflowExecutor')
    @patch('orchestrator.cli.commands.run.StateManager')
    @patch('orchestrator.cli.commands.run.build_frontend_bundle')
    def test_run_workflow_uses_typed_bundle_context_and_inputs_without_legacy_adapter(
        self,
        mock_build,
        mock_state,
        mock_executor,
    ):
        self._stub_frontend_build(mock_build, {
            'version': '2.1',
            'name': 'typed-bundle-run',
            'context': {'max_review_cycles': '3'},
            'inputs': {
                'max_cycles': {'kind': 'scalar', 'type': 'integer'},
            },
            'steps': [{'name': 'Noop', 'command': ['bash', '-lc', 'true']}],
        })

        mock_state_inst = _state_manager_mock(self.workspace)
        mock_state_inst.logs_dir = self.workspace / '.orchestrate' / 'runs' / 'test-run-123' / 'logs'
        mock_state_inst.initialize.return_value = MagicMock(run_id='test-run-123')
        mock_state.return_value = mock_state_inst

        mock_executor_inst = MagicMock()
        mock_executor_inst.execute.return_value = True
        mock_executor.return_value = mock_executor_inst

        args = _run_args(self.workflow_file, input=['max_cycles=5'], context=['mode=cli'])

        result = run_workflow(args)

        self.assertEqual(result, 0)

    @patch('orchestrator.cli.commands.run.WorkflowExecutor')
    @patch('orchestrator.cli.commands.run.StateManager')
    @patch('orchestrator.cli.commands.run.build_frontend_bundle')
    def test_run_workflow_uses_surface_processed_dir_without_legacy_adapter(
        self,
        mock_build,
        mock_state,
        mock_executor,
    ):
        self._stub_frontend_build(mock_build, {
            'version': '2.1',
            'name': 'typed-bundle-run',
            'processed_dir': 'custom-processed',
            'steps': [{'name': 'Noop', 'command': ['bash', '-lc', 'true']}],
        })

        mock_state_inst = _state_manager_mock(self.workspace)
        mock_state_inst.logs_dir = self.workspace / '.orchestrate' / 'runs' / 'test-run-processed' / 'logs'
        mock_state_inst.initialize.return_value = MagicMock(run_id='test-run-processed')
        mock_state.return_value = mock_state_inst

        mock_executor_inst = MagicMock()
        mock_executor_inst.execute.return_value = True
        mock_executor.return_value = mock_executor_inst

        args = _run_args(self.workflow_file, clean_processed=True, dry_run=True)

        with patch('orchestrator.cli.commands.run.validate_clean_processed') as mock_validate:
            result = run_workflow(args)

        self.assertEqual(result, 0)
        self.assertEqual(
            mock_validate.call_args.args[1],
            self.workspace / 'custom-processed',
        )

    @patch('orchestrator.cli.commands.run.WorkflowExecutor')
    @patch('orchestrator.cli.commands.run.StateManager')
    @patch('orchestrator.cli.commands.run.build_frontend_bundle')
    def test_run_workflow_uses_typed_processed_dir_from_loaded_bundle(
        self,
        mock_build,
        mock_state,
        mock_executor,
    ):
        bundle = self._stub_frontend_build(mock_build, {
            'version': '2.1',
            'name': 'typed-bundle-run',
            'processed_dir': 'typed-processed',
            'steps': [{'name': 'Noop', 'command': ['bash', '-lc', 'true']}],
        })
        assert not hasattr(bundle.surface, "raw")

        mock_state_inst = _state_manager_mock(self.workspace)
        mock_state_inst.logs_dir = self.workspace / '.orchestrate' / 'runs' / 'test-run-processed' / 'logs'
        mock_state_inst.initialize.return_value = MagicMock(run_id='test-run-processed')
        mock_state.return_value = mock_state_inst

        mock_executor_inst = MagicMock()
        mock_executor_inst.execute.return_value = True
        mock_executor.return_value = mock_executor_inst

        args = _run_args(self.workflow_file, clean_processed=True, dry_run=True)

        with patch('orchestrator.cli.commands.run.validate_clean_processed') as mock_validate:
            result = run_workflow(args)

        self.assertEqual(result, 0)
        self.assertEqual(
            mock_validate.call_args.args[1],
            self.workspace / 'typed-processed',
        )

    @patch('orchestrator.cli.commands.run.WorkflowExecutor')
    @patch('orchestrator.cli.commands.run.StateManager')
    @patch('orchestrator.cli.commands.run.build_frontend_bundle')
    def test_run_workflow_passes_stream_output_to_executor(self, mock_build, mock_state, mock_executor):
        """run_workflow should pass a dedicated stream-output flag into the executor."""
        self._stub_frontend_build(mock_build)

        mock_state_inst = _state_manager_mock(self.workspace)
        mock_state_inst.logs_dir = self.workspace / '.orchestrate' / 'runs' / 'test-run-123' / 'logs'
        mock_state_inst.initialize.return_value = MagicMock(run_id='test-run-123')
        mock_state.return_value = mock_state_inst

        mock_executor_inst = MagicMock()
        mock_executor_inst.execute.return_value = True
        mock_executor.return_value = mock_executor_inst

        args = _run_args(self.workflow_file, stream_output=True)

        result = run_workflow(args)

        self.assertEqual(result, 0)
        exec_kwargs = mock_executor.call_args.kwargs
        self.assertEqual(exec_kwargs['stream_output'], True)

    @patch('orchestrator.cli.commands.run.WorkflowExecutor')
    @patch('orchestrator.cli.commands.run.StateManager')
    @patch('orchestrator.cli.commands.run.build_frontend_bundle')
    def test_run_workflow_with_clean_and_archive(self, mock_build, mock_state, mock_executor):
        """Test full run workflow with clean and archive flags."""
        # Set up mocks
        self._stub_frontend_build(mock_build)

        mock_state_inst = _state_manager_mock(self.workspace)
        mock_state_inst.initialize.return_value = MagicMock(run_id='test-run-123')
        mock_state.return_value = mock_state_inst

        mock_executor_inst = MagicMock()
        mock_executor_inst.execute.return_value = True
        mock_executor.return_value = mock_executor_inst

        # Set up arguments
        args = _run_args(self.workflow_file, clean_processed=True, archive_processed='archive.zip')

        # Run workflow
        result = run_workflow(args)

        # Should succeed
        self.assertEqual(result, 0)

        # Processed directory should be empty
        self.assertEqual(list(self.processed_dir.iterdir()), [])

        # Archive should be created
        archive_path = Path('archive.zip').resolve()
        self.assertTrue(archive_path.exists())

        # Clean up archive
        archive_path.unlink()

    @patch('orchestrator.cli.commands.run.WorkflowExecutor')
    @patch('orchestrator.cli.commands.run.StateManager')
    @patch('orchestrator.cli.commands.run.build_frontend_bundle')
    def test_run_workflow_returns_nonzero_for_failed_status(self, mock_build, mock_state, mock_executor):
        """run_workflow should return non-zero when executor reports failed run status."""
        self._stub_frontend_build(mock_build)

        mock_state_inst = _state_manager_mock(self.workspace)
        mock_state_inst.initialize.return_value = MagicMock(run_id='test-run-123')
        mock_state.return_value = mock_state_inst

        mock_executor_inst = MagicMock()
        mock_executor_inst.execute.return_value = {'status': 'failed'}
        mock_executor.return_value = mock_executor_inst

        args = _run_args(self.workflow_file, archive_processed='archive.zip')

        result = run_workflow(args)

        self.assertEqual(result, 1)
        self.assertFalse(Path('archive.zip').exists())

    @patch('orchestrator.cli.commands.run.build_frontend_bundle')
    def test_run_workflow_dry_run(self, mock_build):
        """Test dry run mode."""
        self._stub_frontend_build(mock_build)

        args = _run_args(
            self.workflow_file,
            clean_processed=True,
            archive_processed='archive.zip',
            dry_run=True,
        )

        # Create files that shouldn't be cleaned in dry run
        (self.processed_dir / 'should_remain.txt').write_text('test')

        # Run workflow in dry run mode
        result = run_workflow(args)

        # Should succeed
        self.assertEqual(result, 0)

        # Files should still exist (dry run doesn't actually clean)
        self.assertTrue((self.processed_dir / 'should_remain.txt').exists())

        # Archive should not be created (dry run)
        self.assertFalse(Path('archive.zip').exists())
