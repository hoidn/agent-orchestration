"""Dependency resolution with glob pattern matching per specs/dependencies.md"""

import glob
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class ResolvedDependencies:
    """Result of dependency resolution"""
    required: List[str] = field(default_factory=list)  # Resolved required file paths
    optional: List[str] = field(default_factory=list)  # Resolved optional file paths
    all_files: List[str] = field(default_factory=list)  # All resolved files in order
    missing_required: List[str] = field(default_factory=list)  # Required patterns with no matches
    missing_optional: List[str] = field(default_factory=list)  # Optional patterns with no matches


class DependencyError(Exception):
    """Raised when required dependencies cannot be resolved"""
    def __init__(self, message: str, missing_patterns: List[str]):
        super().__init__(message)
        self.missing_patterns = missing_patterns


class DependencyResolver:
    """Resolves file dependencies using POSIX glob patterns"""

    def __init__(self, workspace_root: str):
        """
        Initialize resolver with workspace root.

        Args:
            workspace_root: Absolute path to workspace root
        """
        self.workspace_root = Path(workspace_root).resolve()

    def resolve(self,
                required: Optional[List[str]] = None,
                optional: Optional[List[str]] = None) -> ResolvedDependencies:
        """
        Resolve file dependencies using glob patterns.

        Args:
            required: List of required glob patterns (after substitution)
            optional: List of optional glob patterns (after substitution)

        Returns:
            ResolvedDependencies with all resolved file paths

        Raises:
            DependencyError: If any required pattern has no matches
            ValueError: If patterns contain path safety violations
        """
        result = ResolvedDependencies()

        # Process required patterns
        if required:
            for pattern in required:
                matches = self._resolve_pattern(pattern)
                if not matches:
                    result.missing_required.append(pattern)
                else:
                    result.required.extend(matches)

        # Process optional patterns
        if optional:
            for pattern in optional:
                matches = self._resolve_pattern(pattern)
                if not matches:
                    result.missing_optional.append(pattern)
                else:
                    result.optional.extend(matches)

        # Check for missing required dependencies
        if result.missing_required:
            patterns_str = ', '.join(f'"{p}"' for p in result.missing_required)
            raise DependencyError(
                f"Required dependencies not found: {patterns_str}",
                result.missing_required
            )

        # Combine all files in deterministic order (required first, then optional)
        # Remove duplicates while preserving order
        seen = set()
        for path in result.required + result.optional:
            if path not in seen:
                result.all_files.append(path)
                seen.add(path)

        # Sort for deterministic ordering per spec
        result.all_files.sort()
        result.required.sort()
        result.optional.sort()

        return result

    def _resolve_pattern(self, pattern: str) -> List[str]:
        """
        Resolve a single glob pattern to file paths.

        Args:
            pattern: Glob pattern (relative to workspace)

        Returns:
            List of resolved relative paths

        Raises:
            ValueError: If pattern violates path safety rules
        """
        # Path safety validation per specs/security.md#path-safety
        self._validate_path_safety(pattern)

        # Resolve pattern relative to workspace
        abs_pattern = self.workspace_root / pattern

        # Use glob to find matches
        # Note: glob.glob follows symlinks by default
        matches = glob.glob(str(abs_pattern), recursive=False)

        # Filter and convert to relative paths
        relative_paths = []
        for match_path in matches:
            abs_match = Path(match_path).resolve()

            # Check that resolved path is within workspace (symlink safety)
            if not self._is_within_workspace(abs_match):
                # Skip files that escape workspace via symlinks
                continue

            # Convert to relative path
            try:
                rel_path = abs_match.relative_to(self.workspace_root)
                relative_paths.append(str(rel_path))
            except ValueError:
                # Path is outside workspace - skip it
                continue

        return relative_paths

    def _validate_path_safety(self, pattern: str) -> None:
        """
        Validate that a pattern is safe per specs/security.md#path-safety.

        Args:
            pattern: Pattern to validate

        Raises:
            ValueError: If pattern violates safety rules
        """
        # Check for absolute paths
        if os.path.isabs(pattern):
            raise ValueError(f"Absolute paths not allowed in dependencies: {pattern}")

        # Check for parent directory traversal
        if '..' in pattern:
            raise ValueError(f"Parent directory traversal not allowed in dependencies: {pattern}")

    def _is_within_workspace(self, path: Path) -> bool:
        """
        Check if a resolved path is within the workspace.

        Args:
            path: Resolved absolute path

        Returns:
            True if path is within workspace, False otherwise
        """
        try:
            # Check if path is under workspace root
            path.relative_to(self.workspace_root)
            return True
        except ValueError:
            return False


def resolve_dependencies(workspace_root: str,
                         required: Optional[List[str]] = None,
                         optional: Optional[List[str]] = None) -> ResolvedDependencies:
    """
    Convenience function to resolve dependencies.

    Args:
        workspace_root: Absolute path to workspace root
        required: List of required glob patterns
        optional: List of optional glob patterns

    Returns:
        ResolvedDependencies with all resolved file paths

    Raises:
        DependencyError: If any required pattern has no matches
        ValueError: If patterns contain path safety violations
    """
    resolver = DependencyResolver(workspace_root)
    return resolver.resolve(required, optional)