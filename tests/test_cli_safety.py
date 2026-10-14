import json
import os
import shutil
import tempfile
import zipfile
from unittest import TestCase
from unittest.mock import MagicMock
from orchestrator.cli.commands.run import (validate_clean_processed, clean_processed_directory, validate_archive_destination, archive_processed_directory, parse_context)


class TestCLISafety(TestCase):
    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.workspace = self.test_dir / 'workspace'
        self.workspace.mkdir()

        # Helper validation derives the workspace from this path.
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


"""Safety behavior of the public evaluated run command."""

from pathlib import Path

from orchestrator.cli.main import main
from tests.test_workflow_evaluated_cli import _build


def test_evaluated_run_does_not_apply_retired_processed_directory_flags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source, _program = _build(tmp_path)
    processed = tmp_path / "processed"
    processed.mkdir()
    marker = processed / "keep.txt"
    marker.write_text("preserve this file", encoding="utf-8")
    archive = tmp_path / "archive.zip"
    monkeypatch.chdir(tmp_path)

    exit_code = main([
        "run",
        str(source),
        "--input",
        "score=0.75",
        "--clean-processed",
        "--archive-processed",
        str(archive),
    ])

    assert exit_code == 0
    assert marker.read_text(encoding="utf-8") == "preserve this file"
    assert not archive.exists()
