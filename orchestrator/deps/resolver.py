"""Dependency resolution with glob matching and validation."""

import glob
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Iterable
from dataclasses import dataclass, field

from orchestrator.deps.content_snapshot import AuthoredDependencyRow
from orchestrator.variables.substitution import VariableSubstitutor


@dataclass
class DependencyResolution:
    """Results of dependency resolution."""
    required_files: List[str]
    optional_files: List[str]
    missing_required: List[str]
    patterns_used: Dict[str, List[str]]  # pattern -> matched files
    classified_rows: tuple[AuthoredDependencyRow, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        """True if no required dependencies are missing."""
        return len(self.missing_required) == 0

    @property
    def files(self) -> List[str]:
        """All resolved files in deterministic lexicographic order."""
        return sorted(self.required_files + self.optional_files)

    @property
    def errors(self) -> List[str]:
        """List of missing required dependencies."""
        return self.missing_required
    

class DependencyResolver:
    """Resolves file dependencies with POSIX glob patterns."""
    
    def __init__(self, workspace: str):
        """Initialize resolver with workspace root.
        
        Args:
            workspace: Absolute path to workspace root
        """
        self.workspace = Path(workspace).resolve()
        
    def resolve(self, depends_on: Dict[str, Any], variables: Optional[Dict[str, str]] = None) -> DependencyResolution:
        """Resolve dependencies from depends_on config.
        
        Args:
            depends_on: Dependency config with required/optional lists
            variables: Variables for substitution in patterns
            
        Returns:
            DependencyResolution with matched files and validation results
            
        Raises:
            ValueError: If required files are missing (exit code 2)
        """
        if not depends_on:
            return DependencyResolution(
                required_files=[],
                optional_files=[],
                missing_required=[],
                patterns_used={},
                classified_rows=(),
            )
            
        variables = variables or {}
        
        # Process required dependencies
        required_patterns = depends_on.get('required', [])
        required_files, required_patterns_used, missing_required, required_rows = self._resolve_patterns(
            required_patterns, 
            variables, 
            required=True
        )
        
        # Process optional dependencies  
        optional_patterns = depends_on.get('optional', [])
        optional_files, optional_patterns_used, _, optional_rows = self._resolve_patterns(
            optional_patterns,
            variables,
            required=False
        )
        
        # Combine pattern tracking
        patterns_used = {**required_patterns_used, **optional_patterns_used}

        # Return resolution with validation state
        # Note: Caller (executor) checks is_valid and handles exit code 2
        return DependencyResolution(
            required_files=required_files,
            optional_files=optional_files,
            missing_required=missing_required,
            patterns_used=patterns_used,
            classified_rows=tuple(required_rows + optional_rows),
        )

    def resolve_exact(
        self,
        *,
        required: Iterable[tuple[str, str]] = (),
        optional: Iterable[tuple[str, str]] = (),
    ) -> DependencyResolution:
        """Resolve evaluated exact-path rows without invoking glob expansion."""

        required_files, missing_required, required_rows = self._resolve_exact_rows(
            required, role="required"
        )
        optional_files, _, optional_rows = self._resolve_exact_rows(
            optional, role="optional"
        )
        return DependencyResolution(
            required_files=required_files,
            optional_files=optional_files,
            missing_required=missing_required,
            patterns_used={},
            classified_rows=tuple(required_rows + optional_rows),
        )

    def _resolve_exact_rows(
        self,
        rows: Iterable[tuple[str, str]],
        *,
        role: str,
    ) -> tuple[List[str], List[str], List[AuthoredDependencyRow]]:
        resolved_files: List[str] = []
        missing: List[str] = []
        classified: List[AuthoredDependencyRow] = []

        for authored_index, row in enumerate(rows):
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValueError("exact dependency rows must be (binding_ref, relpath) tuples")
            binding_ref, evaluated_relpath = row
            if not isinstance(binding_ref, str) or not isinstance(evaluated_relpath, str):
                raise ValueError("exact dependency row values must be strings")
            if glob.has_magic(evaluated_relpath):
                raise ValueError(f"exact dependency path contains glob magic: {evaluated_relpath}")

            full_path = self.workspace / evaluated_relpath
            canonical_target: str | None = None
            if full_path.exists():
                canonical_target = full_path.resolve().relative_to(self.workspace).as_posix()
                if canonical_target not in resolved_files:
                    resolved_files.append(canonical_target)
            elif role == "required":
                missing.append(evaluated_relpath)

            classified.append(
                AuthoredDependencyRow(
                    role=role,
                    authored_index=authored_index,
                    binding_ref=binding_ref,
                    evaluated_relpath=evaluated_relpath,
                    canonical_target=canonical_target,
                )
            )

        return resolved_files, missing, classified
        
    def _resolve_patterns(
        self, 
        patterns: List[str], 
        variables: Dict[str, str],
        required: bool
    ) -> Tuple[List[str], Dict[str, List[str]], List[str], List[AuthoredDependencyRow]]:
        """Resolve glob patterns to file paths.
        
        Args:
            patterns: List of glob patterns (may contain variables)
            variables: Variables for substitution
            required: Whether these are required dependencies
            
        Returns:
            Tuple of (matched_files, patterns_used_dict, missing_patterns, classified_rows)
        """
        all_files = []
        patterns_used = {}
        missing_patterns = []
        classified_rows: List[AuthoredDependencyRow] = []
        role = "required" if required else "optional"
        
        for pattern in patterns:
            # Substitute variables in pattern
            expanded_pattern = self._substitute_variables(pattern, variables)
            
            # Validate path safety
            self._validate_path_safety(expanded_pattern)
            
            # Resolve pattern relative to workspace
            full_pattern = self.workspace / expanded_pattern
            
            # Use glob to match files (follows POSIX semantics)
            # Note: glob.glob follows symlinks by default
            matches = glob.glob(str(full_pattern), recursive=False)  # No ** support in v1.1
            
            # Convert back to relative paths and sort for deterministic ordering
            relative_matches = []
            classified_matches: List[tuple[str, str]] = []
            for match in matches:
                match_path = Path(match).resolve()
                
                # Check symlink doesn't escape workspace
                if not str(match_path).startswith(str(self.workspace)):
                    raise ValueError(
                        f"Path safety violation: symlink '{match}' escapes workspace"
                    )
                    
                # Store as relative path
                try:
                    rel_path = match_path.relative_to(self.workspace)
                    canonical_target = rel_path.as_posix()
                    lexical_relpath = Path(match).relative_to(self.workspace).as_posix()
                    relative_matches.append(canonical_target)
                    classified_matches.append((lexical_relpath, canonical_target))
                except ValueError:
                    # Path is outside workspace - shouldn't happen due to check above
                    raise ValueError(
                        f"Path safety violation: resolved path '{match_path}' outside workspace"
                    )
            
            # Sort for deterministic lexicographic ordering
            relative_matches.sort()
            classified_matches.sort()

            for lexical_relpath, canonical_target in classified_matches:
                classified_rows.append(
                    AuthoredDependencyRow(
                        role=role,
                        authored_index=len(classified_rows),
                        binding_ref=pattern,
                        evaluated_relpath=lexical_relpath,
                        canonical_target=canonical_target,
                    )
                )
            
            if relative_matches:
                all_files.extend(relative_matches)
                patterns_used[expanded_pattern] = relative_matches
            elif required:
                missing_patterns.append(expanded_pattern)
            if not relative_matches:
                classified_rows.append(
                    AuthoredDependencyRow(
                        role=role,
                        authored_index=len(classified_rows),
                        binding_ref=pattern,
                        evaluated_relpath=expanded_pattern,
                        canonical_target=None,
                    )
                )
                
        # Remove duplicates while preserving order
        seen = set()
        unique_files = []
        for f in all_files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)
                
        return unique_files, patterns_used, missing_patterns, classified_rows
        
    def _substitute_variables(self, pattern: str, variables: Dict[str, str]) -> str:
        """Substitute variables in pattern.
        
        Args:
            pattern: Pattern potentially containing ${var} references
            variables: Variable values
            
        Returns:
            Pattern with variables substituted
        """
        substitutor = VariableSubstitutor()
        try:
            return str(substitutor.substitute(pattern, variables))
        except ValueError:
            # Preserve the historical dependency behavior: unresolved variables
            # remain literal patterns and are reported as missing dependencies.
            return pattern
        
    def _validate_path_safety(self, path: str) -> None:
        """Validate path doesn't contain dangerous patterns.
        
        Args:
            path: Path to validate
            
        Raises:
            ValueError: If path is absolute or contains ..
        """
        # Check for absolute paths
        if os.path.isabs(path):
            raise ValueError(
                f"Path safety violation: absolute path not allowed: {path}"
            )
            
        # Check for parent directory traversal  
        if ".." in Path(path).parts:
            raise ValueError(
                f"Path safety violation: parent directory traversal not allowed: {path}"
            )
