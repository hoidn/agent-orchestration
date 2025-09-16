"""Tests for dependency injection (AT-28-35)."""

import tempfile
import pytest
from pathlib import Path

from orchestrator.deps.injector import DependencyInjector, InjectionResult


class TestDependencyInjection:
    """Test dependency injection into prompts."""
    
    def test_at28_basic_injection(self):
        """AT-28: Basic injection with inject: true."""
        with tempfile.TemporaryDirectory() as workspace:
            injector = DependencyInjector(workspace)
            
            prompt = "Please implement this feature."
            files = ['artifacts/spec.md', 'docs/requirements.txt']
            inject_config = True  # Shorthand
            
            result = injector.inject(prompt, files, inject_config)
            
            # Should prepend list of files with default instruction
            assert "The following required files are available:" in result.modified_prompt
            assert "- artifacts/spec.md" in result.modified_prompt
            assert "- docs/requirements.txt" in result.modified_prompt
            assert "Please implement this feature." in result.modified_prompt
            assert not result.was_truncated
            
    def test_at29_list_mode_injection(self):
        """AT-29: List mode injection lists all file paths."""
        with tempfile.TemporaryDirectory() as workspace:
            injector = DependencyInjector(workspace)
            
            prompt = "Original prompt content."
            files = ['file1.txt', 'file2.txt', 'dir/file3.txt']
            inject_config = {
                'mode': 'list',
                'position': 'prepend'
            }
            
            result = injector.inject(prompt, files, inject_config)
            
            # Check list format
            lines = result.modified_prompt.split('\n')
            assert "The following required files are available:" in lines[0]
            assert "  - file1.txt" in result.modified_prompt
            assert "  - file2.txt" in result.modified_prompt
            assert "  - dir/file3.txt" in result.modified_prompt
            
    def test_at30_content_mode_injection(self):
        """AT-30: Content mode includes file contents."""
        with tempfile.TemporaryDirectory() as workspace:
            # Create test files with content
            Path(workspace, 'file1.txt').write_text('Content of file 1')
            Path(workspace, 'file2.txt').write_text('Content of file 2')
            
            injector = DependencyInjector(workspace)
            
            prompt = "Process these files."
            files = ['file1.txt', 'file2.txt']
            inject_config = {
                'mode': 'content',
                'position': 'prepend'
            }
            
            result = injector.inject(prompt, files, inject_config)
            
            # Check content format
            assert "=== File: file1.txt" in result.modified_prompt
            assert "Content of file 1" in result.modified_prompt
            assert "=== File: file2.txt" in result.modified_prompt
            assert "Content of file 2" in result.modified_prompt
            assert "bytes) ===" in result.modified_prompt  # Size info
            
    def test_at31_custom_instruction(self):
        """AT-31: Custom instruction overrides default."""
        with tempfile.TemporaryDirectory() as workspace:
            injector = DependencyInjector(workspace)
            
            prompt = "Main prompt."
            files = ['spec.md']
            inject_config = {
                'mode': 'list',
                'instruction': 'Review these architecture documents:'
            }
            
            result = injector.inject(prompt, files, inject_config)
            
            assert "Review these architecture documents:" in result.modified_prompt
            assert "The following required files" not in result.modified_prompt
            
    def test_at32_append_position(self):
        """AT-32: Append position places injection after prompt."""
        with tempfile.TemporaryDirectory() as workspace:
            injector = DependencyInjector(workspace)
            
            prompt = "First part of prompt."
            files = ['appended.txt']
            inject_config = {
                'mode': 'list',
                'position': 'append'
            }
            
            result = injector.inject(prompt, files, inject_config)
            
            # Prompt should come first, then injection
            lines = result.modified_prompt.split('\n')
            assert lines[0] == "First part of prompt."
            # Injection comes after a blank line
            assert "The following required files are available:" in result.modified_prompt
            assert result.modified_prompt.index("First part") < result.modified_prompt.index("following required")
            
    def test_at33_pattern_injection(self):
        """AT-33: Patterns resolve to full list before injection.
        
        Note: This test validates the injector can handle
        multiple files from glob expansion.
        """
        with tempfile.TemporaryDirectory() as workspace:
            injector = DependencyInjector(workspace)
            
            # Files that would come from glob expansion
            files = ['doc1.md', 'doc2.md', 'doc3.md']
            inject_config = True
            
            result = injector.inject("", files, inject_config)
            
            # All files should be listed
            assert "- doc1.md" in result.modified_prompt
            assert "- doc2.md" in result.modified_prompt
            assert "- doc3.md" in result.modified_prompt
            
    def test_at34_optional_file_injection(self):
        """AT-34: Missing optional files are omitted from injection.
        
        Note: The resolver handles filtering, injector just
        processes the files it's given.
        """
        with tempfile.TemporaryDirectory() as workspace:
            injector = DependencyInjector(workspace)
            
            # Only existing files passed to injector
            files = ['exists1.txt', 'exists2.txt']
            inject_config = True
            
            result = injector.inject("", files, inject_config, is_required=False)
            
            # Should use 'optional' in instruction
            assert "optional files are available" in result.modified_prompt
            assert "- exists1.txt" in result.modified_prompt
            assert "- exists2.txt" in result.modified_prompt
            
    def test_at35_no_injection_default(self):
        """AT-35: Without inject config, prompt is unchanged."""
        with tempfile.TemporaryDirectory() as workspace:
            injector = DependencyInjector(workspace)
            
            original_prompt = "This is the original prompt content."
            files = ['file1.txt', 'file2.txt']
            
            # No injection config
            result = injector.inject(original_prompt, files, None)
            assert result.modified_prompt == original_prompt
            
            # inject: false
            result = injector.inject(original_prompt, files, False)
            assert result.modified_prompt == original_prompt
            
            # mode: none
            result = injector.inject(original_prompt, files, {'mode': 'none'})
            assert result.modified_prompt == original_prompt
            
    def test_content_mode_truncation(self):
        """Content mode truncates at size limit."""
        with tempfile.TemporaryDirectory() as workspace:
            # Create large file
            large_content = "x" * (300 * 1024)  # 300KB
            Path(workspace, 'large.txt').write_text(large_content)
            
            injector = DependencyInjector(workspace)
            
            files = ['large.txt']
            inject_config = {
                'mode': 'content'
            }
            
            result = injector.inject("", files, inject_config)
            
            assert result.was_truncated
            assert result.truncation_details is not None
            assert "truncated" in result.modified_prompt
            assert result.truncation_details['truncation_details']['files_truncated'] == 1
            
    def test_list_mode_truncation(self):
        """List mode truncates when too many files."""
        with tempfile.TemporaryDirectory() as workspace:
            injector = DependencyInjector(workspace)
            
            # Create many files with long paths
            files = [f"very/long/path/to/file/number_{i:04d}/document.txt" for i in range(10000)]
            inject_config = {'mode': 'list'}
            
            result = injector.inject("", files, inject_config)
            
            assert result.was_truncated
            assert "files omitted due to size limit" in result.modified_prompt
            
    def test_empty_prompt_injection(self):
        """Injection works with empty prompt."""
        with tempfile.TemporaryDirectory() as workspace:
            injector = DependencyInjector(workspace)
            
            files = ['file.txt']
            inject_config = True
            
            result = injector.inject("", files, inject_config)
            
            # Should just have the injection content
            assert "The following required files are available:" in result.modified_prompt
            assert "- file.txt" in result.modified_prompt
