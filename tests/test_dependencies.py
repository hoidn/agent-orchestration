"""Unit tests for dependency resolution (AT-22-27)"""

import os
import tempfile
import unittest
from pathlib import Path

from orchestrator.deps import DependencyResolver, DependencyError, ResolvedDependencies
from orchestrator.workflow.substitution import SubstitutionContext, substitute_value


class TestDependencyResolution(unittest.TestCase):
    """Test dependency resolution per specs/dependencies.md"""

    def setUp(self):
        """Create temporary workspace with test files"""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)

        # Create test directory structure
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "main.py").write_text("# main code")
        (self.workspace / "src" / "utils.py").write_text("# utils code")
        (self.workspace / "src" / "test.py").write_text("# test code")

        (self.workspace / "docs").mkdir()
        (self.workspace / "docs" / "readme.md").write_text("# README")
        (self.workspace / "docs" / "api.md").write_text("# API")

        (self.workspace / "artifacts").mkdir()
        (self.workspace / "artifacts" / "build.log").write_text("build output")

        # Create a hidden file to test dotfile behavior
        (self.workspace / ".hidden").write_text("hidden file")

        self.resolver = DependencyResolver(str(self.workspace))

    def tearDown(self):
        """Clean up temporary files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # AT-22: Dependency Validation - missing required fails with exit 2
    def test_acceptance_at22_missing_required_dependency(self):
        """AT-22: Missing required dependency causes error"""
        with self.assertRaises(DependencyError) as cm:
            self.resolver.resolve(
                required=["nonexistent/*.txt"],
                optional=[]
            )

        self.assertIn("nonexistent/*.txt", str(cm.exception))
        self.assertEqual(cm.exception.missing_patterns, ["nonexistent/*.txt"])

    # AT-23: Dependency Patterns - POSIX glob matching
    def test_acceptance_at23_posix_glob_matching(self):
        """AT-23: POSIX glob patterns work correctly"""
        # Test various glob patterns
        result = self.resolver.resolve(
            required=["src/*.py"],
            optional=["docs/*.md"]
        )

        # Check required files found
        self.assertEqual(len(result.required), 3)
        self.assertIn("src/main.py", result.required)
        self.assertIn("src/utils.py", result.required)
        self.assertIn("src/test.py", result.required)

        # Check optional files found
        self.assertEqual(len(result.optional), 2)
        self.assertIn("docs/readme.md", result.optional)
        self.assertIn("docs/api.md", result.optional)

        # Check deterministic ordering
        self.assertEqual(result.required, sorted(result.required))
        self.assertEqual(result.optional, sorted(result.optional))

    # AT-24: Variable in Dependencies - substitution before validation
    def test_acceptance_at24_variable_substitution_in_dependencies(self):
        """AT-24: Variables are substituted in dependency patterns"""
        # Create substitution context
        context = SubstitutionContext(
            run={"id": "test-run"},
            context={"module": "src"},
            steps={},
            loop=None,
            item=None
        )

        # Test substitution in patterns
        patterns = ["${context.module}/*.py"]
        substituted = [substitute_value(p, context) for p in patterns]

        self.assertEqual(substituted[0], "src/*.py")

        # Resolve with substituted patterns
        result = self.resolver.resolve(required=substituted)
        self.assertEqual(len(result.required), 3)
        self.assertIn("src/main.py", result.required)

    # AT-25: Loop Dependencies - re-evaluated each iteration
    def test_acceptance_at25_loop_dependency_reevaluation(self):
        """AT-25: Dependencies are re-evaluated in each loop iteration"""
        # Create files for different iterations
        (self.workspace / "iter_0.txt").write_text("iteration 0")
        (self.workspace / "iter_1.txt").write_text("iteration 1")
        (self.workspace / "iter_2.txt").write_text("iteration 2")

        # Simulate loop iterations
        for i in range(3):
            context = SubstitutionContext(
                run={"id": "test-run"},
                context={},
                steps={},
                loop={"index": i, "total": 3},
                item=f"item_{i}"
            )

            # Pattern with loop variable
            pattern = substitute_value("iter_${loop.index}.txt", context)
            self.assertEqual(pattern, f"iter_{i}.txt")

            # Resolve for this iteration
            result = self.resolver.resolve(required=[pattern])
            self.assertEqual(len(result.required), 1)
            self.assertEqual(result.required[0], f"iter_{i}.txt")

    # AT-26: Optional Dependencies - missing optional omitted without error
    def test_acceptance_at26_optional_dependencies(self):
        """AT-26: Missing optional dependencies don't cause errors"""
        result = self.resolver.resolve(
            required=["src/*.py"],
            optional=["nonexistent/*.txt", "missing/*.md"]
        )

        # Required files found
        self.assertEqual(len(result.required), 3)

        # Optional patterns recorded as missing but no error
        self.assertEqual(len(result.optional), 0)
        self.assertEqual(len(result.missing_optional), 2)
        self.assertIn("nonexistent/*.txt", result.missing_optional)
        self.assertIn("missing/*.md", result.missing_optional)

        # All files list contains only required
        self.assertEqual(len(result.all_files), 3)

    # AT-27: Dependency Error Handler - on.failure catches validation failures
    def test_acceptance_at27_dependency_error_context(self):
        """AT-27: Dependency errors have proper context for error handlers"""
        try:
            self.resolver.resolve(
                required=["missing1/*.txt", "missing2/*.md"],
                optional=[]
            )
            self.fail("Should have raised DependencyError")
        except DependencyError as e:
            # Check error has multiple missing patterns
            self.assertEqual(len(e.missing_patterns), 2)
            self.assertIn("missing1/*.txt", e.missing_patterns)
            self.assertIn("missing2/*.md", e.missing_patterns)

    # Additional tests for path safety and glob behavior

    def test_absolute_path_rejected(self):
        """Absolute paths are rejected per specs/security.md#path-safety"""
        with self.assertRaises(ValueError) as cm:
            self.resolver.resolve(required=["/absolute/path/*.txt"])

        self.assertIn("Absolute paths not allowed", str(cm.exception))

    def test_parent_escape_rejected(self):
        """Parent directory traversal is rejected"""
        with self.assertRaises(ValueError) as cm:
            self.resolver.resolve(required=["../escape/*.txt"])

        self.assertIn("Parent directory traversal not allowed", str(cm.exception))

    def test_dotfiles_not_matched_by_star(self):
        """Dotfiles are not matched by * pattern (POSIX behavior)"""
        result = self.resolver.resolve(required=["*"])

        # Should match regular files but not .hidden
        self.assertNotIn(".hidden", result.required)

    def test_dotfiles_matched_explicitly(self):
        """Dotfiles are matched when explicitly specified"""
        result = self.resolver.resolve(required=[".hidden"])

        self.assertEqual(len(result.required), 1)
        self.assertIn(".hidden", result.required)

    def test_empty_patterns(self):
        """Empty pattern lists work correctly"""
        result = self.resolver.resolve(required=[], optional=[])

        self.assertEqual(len(result.required), 0)
        self.assertEqual(len(result.optional), 0)
        self.assertEqual(len(result.all_files), 0)

    def test_deterministic_ordering(self):
        """Files are returned in deterministic lexicographic order"""
        result = self.resolver.resolve(
            required=["src/*.py", "docs/*.md"],
            optional=["artifacts/*.log"]
        )

        # Check all_files is sorted
        self.assertEqual(result.all_files, sorted(result.all_files))

        # Check order is stable across multiple resolutions
        result2 = self.resolver.resolve(
            required=["src/*.py", "docs/*.md"],
            optional=["artifacts/*.log"]
        )
        self.assertEqual(result.all_files, result2.all_files)

    def test_duplicate_removal(self):
        """Duplicate files are removed while preserving order"""
        # Create overlapping patterns
        result = self.resolver.resolve(
            required=["src/*.py", "src/main.py"],
            optional=["src/utils.py"]
        )

        # Check no duplicates in all_files
        self.assertEqual(len(result.all_files), len(set(result.all_files)))

        # Check files appear only once
        self.assertEqual(result.all_files.count("src/main.py"), 1)
        self.assertEqual(result.all_files.count("src/utils.py"), 1)

    def test_symlink_escape_detection(self):
        """Symlinks that escape workspace are filtered out"""
        # Create a regular file first to ensure we have at least one match
        (self.workspace / "regular.txt").write_text("regular content")

        # Create a symlink that points outside workspace
        outside_file = Path(tempfile.gettempdir()) / "outside.txt"
        outside_file.write_text("outside content")

        symlink_path = self.workspace / "escape_link.txt"
        symlink_path.symlink_to(outside_file)

        # Pattern should match regular.txt but not escape_link.txt
        result = self.resolver.resolve(required=["*.txt"])

        # Regular file should be found
        self.assertIn("regular.txt", result.required)
        # The symlink exists but should be filtered out
        self.assertNotIn("escape_link.txt", result.required)

        # Clean up
        outside_file.unlink()


class TestVariableSubstitution(unittest.TestCase):
    """Test variable substitution per specs/variables.md"""

    def test_env_namespace_rejected(self):
        """${env.*} namespace is rejected"""
        context = SubstitutionContext(
            run={"id": "test"},
            context={},
            steps={},
        )

        with self.assertRaises(ValueError) as cm:
            substitute_value("${env.HOME}/path", context)

        self.assertIn("Environment namespace not allowed", str(cm.exception))
        self.assertIn("env.HOME", str(cm.exception))

    def test_undefined_variable_error(self):
        """Undefined variables cause errors"""
        context = SubstitutionContext(
            run={"id": "test"},
            context={},
            steps={},
        )

        with self.assertRaises(ValueError) as cm:
            substitute_value("${context.undefined}", context)

        self.assertIn("Undefined variable", str(cm.exception))
        self.assertIn("context.undefined", str(cm.exception))

    def test_escape_sequences(self):
        """$$ and $${ escape sequences work"""
        context = SubstitutionContext(
            run={"id": "test"},
            context={"key": "value"},
            steps={},
        )

        # Test $$ -> $
        result = substitute_value("Price: $$100", context)
        self.assertEqual(result, "Price: $100")

        # Test $${ -> ${
        result = substitute_value("Literal: $${variable}", context)
        self.assertEqual(result, "Literal: ${variable}")

        # Test combination with real variable
        result = substitute_value("$$100 and ${context.key}", context)
        self.assertEqual(result, "$100 and value")

    def test_nested_step_navigation(self):
        """Steps with nested JSON can be navigated"""
        context = SubstitutionContext(
            run={"id": "test"},
            context={},
            steps={
                "Parse": {
                    "exit_code": 0,
                    "json": {
                        "files": ["a.txt", "b.txt"],
                        "config": {
                            "enabled": True
                        }
                    }
                }
            },
        )

        # Navigate to nested array
        result = substitute_value("${steps.Parse.json.files}", context)
        self.assertEqual(result, "['a.txt', 'b.txt']")

        # Navigate to nested object field
        result = substitute_value("${steps.Parse.json.config.enabled}", context)
        self.assertEqual(result, "True")


if __name__ == '__main__':
    unittest.main()