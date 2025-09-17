"""Dependency resolution with glob matching and validation."""

import glob
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


@dataclass
class DependencyResolution:
    """Results of dependency resolution."""
    required_files: List[str]
    optional_files: List[str]
    missing_required: List[str]
    patterns_used: Dict[str, List[str]]  # pattern -> matched files

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
                patterns_used={}
            )
            
        variables = variables or {}
        
        # Process required dependencies
        required_patterns = depends_on.get('required', [])
        required_files, required_patterns_used, missing_required = self._resolve_patterns(
            required_patterns, 
            variables, 
            required=True
        )
        
        # Process optional dependencies  
        optional_patterns = depends_on.get('optional', [])
        optional_files, optional_patterns_used, _ = self._resolve_patterns(
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
            patterns_used=patterns_used
        )
        
    def _resolve_patterns(
        self, 
        patterns: List[str], 
        variables: Dict[str, str],
        required: bool
    ) -> Tuple[List[str], Dict[str, List[str]], List[str]]:
        """Resolve glob patterns to file paths.
        
        Args:
            patterns: List of glob patterns (may contain variables)
            variables: Variables for substitution
            required: Whether these are required dependencies
            
        Returns:
            Tuple of (matched_files, patterns_used_dict, missing_patterns)
        """
        all_files = []
        patterns_used = {}
        missing_patterns = []
        
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
                    relative_matches.append(str(rel_path))
                except ValueError:
                    # Path is outside workspace - shouldn't happen due to check above
                    raise ValueError(
                        f"Path safety violation: resolved path '{match_path}' outside workspace"
                    )
            
            # Sort for deterministic lexicographic ordering
            relative_matches.sort()
            
            if relative_matches:
                all_files.extend(relative_matches)
                patterns_used[expanded_pattern] = relative_matches
            elif required:
                missing_patterns.append(expanded_pattern)
                
        # Remove duplicates while preserving order
        seen = set()
        unique_files = []
        for f in all_files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)
                
        return unique_files, patterns_used, missing_patterns
        
    def _substitute_variables(self, pattern: str, variables: Dict[str, str]) -> str:
        """Substitute variables in pattern.
        
        Args:
            pattern: Pattern potentially containing ${var} references
            variables: Variable values
            
        Returns:
            Pattern with variables substituted
        """
        # Simple variable substitution - in real implementation would use
        # the same substitution logic as the rest of the system
        result = pattern
        for key, value in variables.items():
            result = result.replace(f"${{{key}}}", value)
        return result
        
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
