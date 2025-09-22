"""Tests for CLI safety features (AT-11, AT-12, AT-16)."""

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
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


class TestCLISafety(TestCase):
    """Test CLI safety features."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.workspace = self.test_dir / 'workspace'
        self.workspace.mkdir()

        # Create workflow file
        self.workflow_file = self.workspace / 'workflow.yaml'
        self.workflow_file.write_text("""
version: "1.1"
name: test
steps:
  - name: test
    command: ["echo", "test"]
""")

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

    @patch('orchestrator.cli.commands.run.WorkflowExecutor')
    @patch('orchestrator.cli.commands.run.StateManager')
    @patch('orchestrator.cli.commands.run.WorkflowLoader')
    def test_run_workflow_with_clean_and_archive(self, mock_loader, mock_state, mock_executor):
        """Test full run workflow with clean and archive flags."""
        # Set up mocks
        mock_loader.return_value.load.return_value = {
            'version': '1.1',
            'name': 'test',
            'processed_dir': 'processed',
            'steps': []
        }

        mock_state_inst = MagicMock()
        mock_state_inst.create_run.return_value = {
            'run_id': 'test-run-123',
            'status': 'running'
        }
        mock_state.return_value = mock_state_inst

        mock_executor_inst = MagicMock()
        mock_executor_inst.execute.return_value = True
        mock_executor.return_value = mock_executor_inst

        # Set up arguments
        args = MagicMock()
        args.workflow = str(self.workflow_file)
        args.context = None
        args.context_file = None
        args.clean_processed = True
        args.archive_processed = 'archive.zip'
        args.dry_run = False
        args.debug = False
        args.quiet = False
        args.verbose = False
        args.log_level = 'info'
        args.backup_state = False
        args.state_dir = None
        args.on_error = 'stop'
        args.max_retries = 0
        args.retry_delay = 1000

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

    @patch('orchestrator.cli.commands.run.WorkflowLoader')
    def test_run_workflow_dry_run(self, mock_loader):
        """Test dry run mode."""
        mock_loader.return_value.load.return_value = {
            'version': '1.1',
            'name': 'test',
            'steps': []
        }

        args = MagicMock()
        args.workflow = str(self.workflow_file)
        args.context = None
        args.context_file = None
        args.clean_processed = True
        args.archive_processed = 'archive.zip'
        args.dry_run = True
        args.debug = False
        args.quiet = False
        args.verbose = False
        args.log_level = 'info'
        args.backup_state = False
        args.state_dir = None
        args.on_error = 'stop'
        args.max_retries = 0
        args.retry_delay = 1000

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