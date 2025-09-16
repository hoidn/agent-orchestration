"""Tests for dependency injection (AT-28 through AT-35).

Tests the v1.1.1 dependency injection feature per specs/dependencies.md.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from orchestrator.deps import DependencyInjector, InjectionResult
from orchestrator.workflow.types import DependsOnInjection


class TestDependencyInjection:
    """Test dependency injection modes and configurations."""

    def test_acceptance_at30_content_mode_injection(self):
        """AT-30: Content mode injection includes file contents with truncation metadata.

        Requirements:
        - Content mode includes actual file contents
        - Each file has a header showing relative path and size info
        - Files are processed in lexicographic order
        - Truncation is handled gracefully
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create test files with specific content
            arch_dir = workspace / "artifacts" / "architect"
            arch_dir.mkdir(parents=True)

            # Create files in specific order to test sorting
            (arch_dir / "design.md").write_text("# System Design\n\nMicroservices architecture")
            (arch_dir / "api.md").write_text("# API Design\n\nRESTful endpoints")
            (arch_dir / "schema.md").write_text("# Database Schema\n\nPostgreSQL tables")

            # Initialize injector
            injector = DependencyInjector(str(workspace))

            # Original prompt
            prompt = "Please implement the system based on the architecture files."

            # Files to inject (will be sorted)
            files = [
                "artifacts/architect/schema.md",
                "artifacts/architect/design.md",
                "artifacts/architect/api.md"
            ]

            # Inject with content mode
            config = DependsOnInjection(mode="content", position="prepend")
            result = injector.inject(prompt, files, config)

            # Verify content includes file contents
            assert "System Design" in result.injected_content
            assert "Microservices architecture" in result.injected_content
            assert "API Design" in result.injected_content
            assert "RESTful endpoints" in result.injected_content
            assert "Database Schema" in result.injected_content
            assert "PostgreSQL tables" in result.injected_content

            # Verify headers with size info
            assert "=== File: artifacts/architect/api.md" in result.injected_content
            assert "bytes) ===" in result.injected_content

            # Verify files are in sorted order
            api_pos = result.injected_content.index("artifacts/architect/api.md")
            design_pos = result.injected_content.index("artifacts/architect/design.md")
            schema_pos = result.injected_content.index("artifacts/architect/schema.md")
            assert api_pos < design_pos < schema_pos  # Lexicographic order

            # Verify original prompt is included
            assert "Please implement the system" in result.injected_content

            # Verify no truncation for small files
            assert not result.truncated
            assert result.truncated_files == []

    def test_acceptance_at30_content_mode_truncation(self):
        """AT-30: Content mode handles truncation when exceeding size cap.

        Requirements:
        - Total injected content capped at ~256 KiB
        - Truncation metadata recorded
        - Partial content included when possible
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create a large file that will trigger truncation
            large_dir = workspace / "data"
            large_dir.mkdir()

            # Create content larger than 256 KiB
            large_content = "x" * (300 * 1024)  # 300 KiB
            (large_dir / "zz_large.txt").write_text(large_content)  # zz_ prefix ensures it comes last

            # Create a small file that should fit first
            (large_dir / "aa_small.txt").write_text("Small content")  # aa_ prefix ensures it comes first

            # Initialize injector
            injector = DependencyInjector(str(workspace))

            # Files to inject (will be sorted: aa_small.txt, zz_large.txt)
            files = ["data/zz_large.txt", "data/aa_small.txt"]

            # Inject with content mode
            config = DependsOnInjection(mode="content")
            result = injector.inject("Test prompt", files, config)

            # Verify truncation occurred
            assert result.truncated
            assert "data/zz_large.txt" in result.truncated_files

            # Verify small file was included fully (comes first in sorted order)
            assert "Small content" in result.injected_content

            # Verify size is within cap (with some margin for headers)
            content_size = len(result.injected_content.encode('utf-8'))
            assert content_size <= 260 * 1024  # Allow some overhead for headers

            # Verify truncation info shows partial content
            assert result.shown_bytes < result.total_bytes

    def test_acceptance_at31_custom_instruction(self):
        """AT-31: Custom instruction overrides default text.

        Requirements:
        - inject.instruction replaces default instruction
        - Works in both list and content modes
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create test file
            (workspace / "test.md").write_text("Test content")

            injector = DependencyInjector(str(workspace))

            # Test with custom instruction in list mode
            config = DependsOnInjection(
                mode="list",
                instruction="Review these critical files before proceeding:"
            )
            result = injector.inject("Prompt", ["test.md"], config)

            assert "Review these critical files before proceeding:" in result.injected_content
            assert "The following files are available" not in result.injected_content

            # Test with custom instruction in content mode
            config = DependsOnInjection(
                mode="content",
                instruction="Analyze the following source code:"
            )
            result = injector.inject("Prompt", ["test.md"], config)

            assert "Analyze the following source code:" in result.injected_content
            assert "The following files are available" not in result.injected_content

    def test_acceptance_at32_append_position(self):
        """AT-32: Append position places injection after prompt content.

        Requirements:
        - position: "append" places injection after prompt
        - Default is "prepend" which places before prompt
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create test file
            (workspace / "ref.txt").write_text("Reference material")

            injector = DependencyInjector(str(workspace))
            prompt = "Main prompt content here"

            # Test append position
            config = DependsOnInjection(mode="list", position="append")
            result = injector.inject(prompt, ["ref.txt"], config)

            # Verify prompt comes first, then injection
            prompt_pos = result.injected_content.index("Main prompt content")
            ref_pos = result.injected_content.index("ref.txt")
            assert prompt_pos < ref_pos

            # Test prepend position (default)
            config = DependsOnInjection(mode="list", position="prepend")
            result = injector.inject(prompt, ["ref.txt"], config)

            # Verify injection comes first, then prompt
            prompt_pos = result.injected_content.index("Main prompt content")
            ref_pos = result.injected_content.index("ref.txt")
            assert ref_pos < prompt_pos

    def test_acceptance_at29_list_mode_injection(self):
        """AT-29: List mode correctly lists all resolved file paths.

        Requirements:
        - List mode shows bullet list of file paths
        - Paths are relative to workspace
        - Files sorted lexicographically
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create test files
            (workspace / "b.txt").write_text("B")
            (workspace / "a.txt").write_text("A")
            (workspace / "c.txt").write_text("C")

            injector = DependencyInjector(str(workspace))

            # Test list mode
            config = DependsOnInjection(mode="list")
            result = injector.inject("Prompt", ["b.txt", "c.txt", "a.txt"], config)

            # Verify bullet list format
            assert "- a.txt" in result.injected_content
            assert "- b.txt" in result.injected_content
            assert "- c.txt" in result.injected_content

            # Verify sorted order
            a_pos = result.injected_content.index("- a.txt")
            b_pos = result.injected_content.index("- b.txt")
            c_pos = result.injected_content.index("- c.txt")
            assert a_pos < b_pos < c_pos

    def test_acceptance_at28_basic_injection(self):
        """AT-28: inject: true prepends default instruction + file list.

        Requirements:
        - Shorthand inject: true works
        - Uses default instruction
        - Prepends to prompt
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create test file
            (workspace / "doc.md").write_text("Documentation")

            injector = DependencyInjector(str(workspace))

            # Test shorthand inject: true
            result = injector.inject("User prompt", ["doc.md"], True)

            # Verify default instruction used
            assert "The following files are available in the workspace:" in result.injected_content

            # Verify file listed
            assert "- doc.md" in result.injected_content

            # Verify prepended (instruction before prompt)
            inst_pos = result.injected_content.index("The following files")
            prompt_pos = result.injected_content.index("User prompt")
            assert inst_pos < prompt_pos

    def test_acceptance_at35_no_injection_default(self):
        """AT-35: Without inject, prompt unchanged.

        Requirements:
        - When inject is None/False, prompt is returned as-is
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            injector = DependencyInjector(str(workspace))

            # Test with None (no injection)
            result = injector.inject("Original prompt", ["file.txt"], None)
            assert result.injected_content == "Original prompt"

            # Test with explicit DependsOnInjection(mode="none")
            config = DependsOnInjection(mode="none")
            result = injector.inject("Original prompt", ["file.txt"], config)
            assert result.injected_content == "Original prompt"

    def test_content_mode_header_format(self):
        """Test that content mode headers show correct byte counts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create file with known content
            content = "Hello, world!"  # 13 bytes
            (workspace / "test.txt").write_text(content)

            injector = DependencyInjector(str(workspace))
            config = DependsOnInjection(mode="content")
            result = injector.inject("", ["test.txt"], config)

            # Verify header format: === File: path (shown/total bytes) ===
            assert "=== File: test.txt (13/13 bytes) ===" in result.injected_content

    def test_empty_file_list(self):
        """Test injection with empty file list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            injector = DependencyInjector(tmpdir)

            # With empty list, prompt should be unchanged
            result = injector.inject("Test prompt", [], True)
            assert result.injected_content == "Test prompt"

            # Even with content mode
            config = DependsOnInjection(mode="content")
            result = injector.inject("Test prompt", [], config)
            assert result.injected_content == "Test prompt"