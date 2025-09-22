"""Tests for dependency resolution and validation (AT-22-27)."""

import os
import tempfile
import pytest
from pathlib import Path

from orchestrator.deps.resolver import DependencyResolver, DependencyResolution


class TestDependencyResolution:
    """Test dependency resolution with glob patterns."""
    
    def test_at22_missing_required_dependencies_fails(self):
        """AT-22: Missing required dependencies fail with exit 2.

        Note: The resolver returns validation state, executor handles exit code.
        """
        with tempfile.TemporaryDirectory() as workspace:
            resolver = DependencyResolver(workspace)

            depends_on = {
                'required': ['missing_file.txt']
            }

            # Resolver returns resolution with validation state
            result = resolver.resolve(depends_on)

            # Check that validation fails
            assert not result.is_valid
            assert result.missing_required == ['missing_file.txt']
            assert result.errors == ['missing_file.txt']
            assert result.required_files == []
            
    def test_at23_posix_glob_matching(self):
        """AT-23: POSIX glob patterns match files correctly."""
        with tempfile.TemporaryDirectory() as workspace:
            # Create test files
            Path(workspace, 'doc1.md').touch()
            Path(workspace, 'doc2.md').touch()
            Path(workspace, 'test.txt').touch()
            Path(workspace, 'subdir').mkdir()
            Path(workspace, 'subdir', 'doc3.md').touch()
            
            resolver = DependencyResolver(workspace)
            
            depends_on = {
                'required': ['*.md', 'subdir/*.md']
            }
            
            result = resolver.resolve(depends_on)
            
            # Should match all .md files in specified locations
            assert sorted(result.required_files) == ['doc1.md', 'doc2.md', 'subdir/doc3.md']
            assert result.missing_required == []
            
    def test_at24_variable_substitution_in_dependencies(self):
        """AT-24: Variables are substituted before dependency validation."""
        with tempfile.TemporaryDirectory() as workspace:
            # Create test files
            Path(workspace, 'artifacts').mkdir()
            Path(workspace, 'artifacts', 'report.md').touch()
            
            resolver = DependencyResolver(workspace)
            
            depends_on = {
                'required': ['${artifact_dir}/report.md']
            }
            
            variables = {
                'artifact_dir': 'artifacts'
            }
            
            result = resolver.resolve(depends_on, variables)
            
            assert result.required_files == ['artifacts/report.md']
            assert result.missing_required == []
            
    def test_at25_loop_dependencies_reevaluation(self):
        """AT-25: Dependencies are re-evaluated each loop iteration.
        
        This test validates the resolver can be called multiple times
        with different variables (as would happen in a loop).
        """
        with tempfile.TemporaryDirectory() as workspace:
            # Create test files for different iterations
            Path(workspace, 'item1').mkdir()
            Path(workspace, 'item1', 'data.txt').touch()
            Path(workspace, 'item2').mkdir()
            Path(workspace, 'item2', 'data.txt').touch()
            
            resolver = DependencyResolver(workspace)
            
            # First iteration
            depends_on = {
                'required': ['${item}/data.txt']
            }
            
            result1 = resolver.resolve(depends_on, {'item': 'item1'})
            assert result1.required_files == ['item1/data.txt']
            
            # Second iteration - different variable value
            result2 = resolver.resolve(depends_on, {'item': 'item2'})
            assert result2.required_files == ['item2/data.txt']
            
    def test_at26_optional_dependencies_omitted(self):
        """AT-26: Missing optional dependencies are omitted without error."""
        with tempfile.TemporaryDirectory() as workspace:
            # Create only some files
            Path(workspace, 'exists.txt').touch()
            
            resolver = DependencyResolver(workspace)
            
            depends_on = {
                'required': ['exists.txt'],
                'optional': ['missing.txt', 'also_missing.txt']
            }
            
            # Should not raise error for missing optional files
            result = resolver.resolve(depends_on)
            
            assert result.required_files == ['exists.txt']
            assert result.optional_files == []
            assert result.missing_required == []
            
    def test_at26_mixed_optional_dependencies(self):
        """AT-26: Optional dependencies include only existing files."""
        with tempfile.TemporaryDirectory() as workspace:
            # Create some optional files
            Path(workspace, 'optional1.txt').touch()
            Path(workspace, 'optional3.txt').touch()
            
            resolver = DependencyResolver(workspace)
            
            depends_on = {
                'optional': ['optional1.txt', 'optional2.txt', 'optional3.txt']
            }
            
            result = resolver.resolve(depends_on)
            
            assert sorted(result.optional_files) == ['optional1.txt', 'optional3.txt']
            assert result.missing_required == []
            
    def test_at27_dependency_error_context(self):
        """AT-27: Dependency failures provide proper error context.

        The error handler (on.failure) can catch these with exit code 2.
        Note: The resolver returns validation state, executor handles exit code.
        """
        with tempfile.TemporaryDirectory() as workspace:
            resolver = DependencyResolver(workspace)

            depends_on = {
                'required': ['missing1.txt', 'missing2.txt']
            }

            # Resolver returns resolution with validation state
            result = resolver.resolve(depends_on)

            # Check that validation fails with proper error context
            assert not result.is_valid
            assert 'missing1.txt' in result.missing_required
            assert 'missing2.txt' in result.missing_required
            assert len(result.missing_required) == 2
            assert result.errors == result.missing_required
            
    def test_deterministic_ordering(self):
        """Files are returned in deterministic lexicographic order."""
        with tempfile.TemporaryDirectory() as workspace:
            # Create files in non-alphabetical order
            Path(workspace, 'zebra.txt').touch()
            Path(workspace, 'apple.txt').touch()
            Path(workspace, 'middle.txt').touch()
            
            resolver = DependencyResolver(workspace)
            
            depends_on = {
                'required': ['*.txt']
            }
            
            result = resolver.resolve(depends_on)
            
            # Should be in lexicographic order
            assert result.required_files == ['apple.txt', 'middle.txt', 'zebra.txt']
            
    def test_path_safety_absolute_path_rejected(self):
        """Absolute paths in dependencies are rejected."""
        with tempfile.TemporaryDirectory() as workspace:
            resolver = DependencyResolver(workspace)
            
            depends_on = {
                'required': ['/etc/passwd']
            }
            
            with pytest.raises(ValueError) as exc_info:
                resolver.resolve(depends_on)
            
            assert "Path safety violation" in str(exc_info.value)
            assert "absolute path" in str(exc_info.value)
            
    def test_path_safety_parent_traversal_rejected(self):
        """Parent directory traversal in dependencies is rejected."""
        with tempfile.TemporaryDirectory() as workspace:
            resolver = DependencyResolver(workspace)
            
            depends_on = {
                'required': ['../../../etc/passwd']
            }
            
            with pytest.raises(ValueError) as exc_info:
                resolver.resolve(depends_on)
            
            assert "Path safety violation" in str(exc_info.value)
            assert "parent directory traversal" in str(exc_info.value)
            
    def test_symlink_escape_rejected(self):
        """Symlinks that escape workspace are rejected."""
        with tempfile.TemporaryDirectory() as workspace:
            # Create a symlink that points outside workspace
            outside_dir = tempfile.mkdtemp()
            try:
                Path(outside_dir, 'secret.txt').touch()
                
                # Create symlink pointing outside
                link_path = Path(workspace, 'link.txt')
                link_path.symlink_to(Path(outside_dir, 'secret.txt'))
                
                resolver = DependencyResolver(workspace)
                
                depends_on = {
                    'required': ['link.txt']
                }
                
                with pytest.raises(ValueError) as exc_info:
                    resolver.resolve(depends_on)
                
                assert "Path safety violation" in str(exc_info.value)
                assert "escapes workspace" in str(exc_info.value)
                
            finally:
                # Cleanup
                Path(outside_dir, 'secret.txt').unlink()
                os.rmdir(outside_dir)
                
    def test_dotfiles_not_matched_by_default(self):
        """Dotfiles are not matched unless explicitly specified."""
        with tempfile.TemporaryDirectory() as workspace:
            # Create regular and dot files
            Path(workspace, 'normal.txt').touch()
            Path(workspace, '.hidden.txt').touch()
            
            resolver = DependencyResolver(workspace)
            
            # Wildcard should not match dotfiles
            depends_on = {
                'required': ['*.txt']
            }
            
            result = resolver.resolve(depends_on)
            assert result.required_files == ['normal.txt']
            
            # Explicit dotfile pattern should work
            depends_on = {
                'required': ['.hidden.txt']
            }
            
            result = resolver.resolve(depends_on)
            assert result.required_files == ['.hidden.txt']
            
    def test_pattern_tracking(self):
        """Patterns used are tracked in resolution results."""
        with tempfile.TemporaryDirectory() as workspace:
            Path(workspace, 'file1.md').touch()
            Path(workspace, 'file2.md').touch()
            Path(workspace, 'data.json').touch()
            
            resolver = DependencyResolver(workspace)
            
            depends_on = {
                'required': ['*.md'],
                'optional': ['*.json']
            }
            
            result = resolver.resolve(depends_on)
            
            assert '*.md' in result.patterns_used
            assert sorted(result.patterns_used['*.md']) == ['file1.md', 'file2.md']
            assert '*.json' in result.patterns_used
            assert result.patterns_used['*.json'] == ['data.json']
