"""Dependency injection for composing prompts with file contents.

Implements specs/dependencies.md injection modes (v1.1.1).
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from orchestrator.workflow.types import DependsOnConfig, DependsOnInjection


# Default injection instruction
DEFAULT_INSTRUCTION = "The following files are available in the workspace:"

# Size cap for injection (~256 KiB)
INJECTION_SIZE_CAP = 256 * 1024


@dataclass
class InjectionResult:
    """Result of dependency injection."""
    injected_content: str
    truncated: bool = False
    total_bytes: int = 0
    shown_bytes: int = 0
    truncated_files: List[str] = None

    def __post_init__(self):
        if self.truncated_files is None:
            self.truncated_files = []


class DependencyInjector:
    """Handles dependency injection into prompts."""

    def __init__(self, workspace_root: str):
        """Initialize injector with workspace root.

        Args:
            workspace_root: Absolute path to workspace root
        """
        self.workspace_root = Path(workspace_root).resolve()

    def inject(
        self,
        prompt: str,
        resolved_files: List[str],
        inject_config: Union[bool, DependsOnInjection]
    ) -> InjectionResult:
        """Inject dependency information into prompt.

        Args:
            prompt: Original prompt content
            resolved_files: List of resolved file paths (relative to workspace)
            inject_config: Injection configuration (true for defaults or config object)

        Returns:
            InjectionResult with injected content and metadata
        """
        # Handle shorthand: inject: true
        if inject_config is True:
            config = DependsOnInjection(mode="list", position="prepend")
        elif isinstance(inject_config, DependsOnInjection):
            config = inject_config
        else:
            # No injection
            return InjectionResult(injected_content=prompt)

        # Skip if no files to inject
        if not resolved_files:
            return InjectionResult(injected_content=prompt)

        # Sort files for deterministic ordering
        sorted_files = sorted(resolved_files)

        # Build injection based on mode
        if config.mode == "list":
            injection = self._build_list_injection(sorted_files, config.instruction)
        elif config.mode == "content":
            injection = self._build_content_injection(sorted_files, config.instruction)
        else:  # mode == "none"
            return InjectionResult(injected_content=prompt)

        # Apply injection at specified position
        if config.position == "prepend":
            final_content = injection.injected_content + "\n\n" + prompt
        else:  # position == "append"
            final_content = prompt + "\n\n" + injection.injected_content

        # Update result with final content
        injection.injected_content = final_content
        return injection

    def _build_list_injection(
        self,
        files: List[str],
        instruction: Optional[str] = None
    ) -> InjectionResult:
        """Build list mode injection (AT-29).

        Args:
            files: Sorted list of file paths
            instruction: Optional custom instruction

        Returns:
            InjectionResult with list of files
        """
        # Use custom instruction or default
        inst = instruction if instruction is not None else DEFAULT_INSTRUCTION

        # Build bullet list
        lines = [inst]
        for file_path in files:
            lines.append(f"- {file_path}")

        content = "\n".join(lines)

        return InjectionResult(
            injected_content=content,
            total_bytes=len(content.encode('utf-8')),
            shown_bytes=len(content.encode('utf-8'))
        )

    def _build_content_injection(
        self,
        files: List[str],
        instruction: Optional[str] = None
    ) -> InjectionResult:
        """Build content mode injection (AT-30).

        Includes file contents with headers showing size information.
        Respects size cap of ~256 KiB.

        Args:
            files: Sorted list of file paths
            instruction: Optional custom instruction

        Returns:
            InjectionResult with file contents and truncation metadata
        """
        # Use custom instruction or default
        inst = instruction if instruction is not None else DEFAULT_INSTRUCTION

        # Start with instruction
        parts = [inst, ""]
        current_size = len(inst.encode('utf-8'))
        truncated = False
        truncated_files = []

        # Calculate total size of all files first
        total_size = current_size
        file_sizes = []
        for file_path in files:
            abs_path = self.workspace_root / file_path
            try:
                file_size = abs_path.stat().st_size
                file_sizes.append((file_path, file_size))
                total_size += file_size + 50  # Add estimate for headers
            except Exception:
                file_sizes.append((file_path, 0))

        # Now process files for content
        for file_path, _ in file_sizes:
            # Read file content
            abs_path = self.workspace_root / file_path

            try:
                # Get file size first
                file_size = abs_path.stat().st_size
                content = abs_path.read_text(encoding='utf-8')
                content_bytes = content.encode('utf-8')
                actual_size = len(content_bytes)
            except Exception as e:
                # Skip files that can't be read
                continue

            # Build header with size info
            header = f"=== File: {file_path} ({actual_size}/{file_size} bytes) ==="
            header_size = len(header.encode('utf-8'))

            # Check if adding this file would exceed cap
            if current_size + header_size + actual_size > INJECTION_SIZE_CAP:
                # Try to fit partial content
                remaining = INJECTION_SIZE_CAP - current_size - header_size

                if remaining > 100:  # Only include if we can show meaningful content
                    # Truncate content to fit
                    truncated_content = content_bytes[:remaining].decode('utf-8', errors='ignore')
                    shown_size = len(truncated_content.encode('utf-8'))
                    header = f"=== File: {file_path} ({shown_size}/{file_size} bytes) ==="

                    parts.append(header)
                    parts.append(truncated_content)
                    parts.append("")

                    current_size += header_size + shown_size
                    truncated = True
                    truncated_files.append(file_path)
                else:
                    # Skip this file entirely
                    truncated = True
                    truncated_files.append(file_path)

                # Stop processing more files
                break
            else:
                # Add full file content
                parts.append(header)
                parts.append(content)
                parts.append("")

                current_size += header_size + actual_size

        content = "\n".join(parts)

        return InjectionResult(
            injected_content=content,
            truncated=truncated,
            total_bytes=total_size,  # Total size of all files (before truncation)
            shown_bytes=current_size,  # Actual size injected (after truncation)
            truncated_files=truncated_files
        )