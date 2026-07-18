"""Dependency injection into prompts."""

from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from orchestrator.deps.content_snapshot import (
    MAX_INJECTION_BYTES,
    AuthoredDependencyRow,
    DependencyContent,
    DependencyContentSnapshot,
    build_content_snapshot,
    render_content_snapshot,
)

# Size limits per spec
MAX_INJECTION_SIZE = MAX_INJECTION_BYTES


@dataclass 
class InjectionResult:
    """Results of dependency injection."""
    modified_prompt: str
    was_truncated: bool
    truncation_details: Optional[Dict[str, Any]] = None
    

class DependencyInjector:
    """Injects file dependencies into prompts."""
    
    def __init__(self, workspace: str):
        """Initialize injector with workspace root.
        
        Args:
            workspace: Absolute path to workspace root
        """
        self.workspace = Path(workspace).resolve()
        
    def inject(
        self,
        prompt: str,
        files: List[str],
        inject_config: Any,
        is_required: bool = True,
        *,
        content_snapshot: DependencyContentSnapshot | None = None,
    ) -> InjectionResult:
        """Inject files into prompt based on config.
        
        Args:
            prompt: Original prompt content
            files: List of resolved file paths (relative to workspace)
            inject_config: Injection config (bool or dict)
            is_required: Whether these are required dependencies
            
        Returns:
            InjectionResult with modified prompt and truncation info
        """
        # Handle no injection case
        if not inject_config or inject_config is False:
            return InjectionResult(
                modified_prompt=prompt,
                was_truncated=False
            )
            
        # Parse injection config
        if inject_config is True:
            # Shorthand: inject: true
            mode = 'list'
            position = 'prepend'
            instruction = self._get_default_instruction(mode, is_required)
        else:
            mode = inject_config.get('mode', 'list')
            position = inject_config.get('position', 'prepend')
            default_is_required = is_required
            if mode == 'content' and content_snapshot is not None:
                default_is_required = any(
                    row.role == "required" for row in content_snapshot.authored_rows
                )
            instruction = inject_config.get(
                'instruction',
                self._get_default_instruction(mode, default_is_required)
            )
            
        # Generate injection content based on mode
        if mode == 'list':
            injection_content, was_truncated, truncation_details = self._generate_list_injection(
                files, instruction
            )
        elif mode == 'content':
            injection_content, was_truncated, truncation_details = self._generate_content_injection(
                files,
                instruction,
                content_snapshot=content_snapshot,
                is_required=is_required,
            )
        elif mode == 'none':
            return InjectionResult(
                modified_prompt=prompt,
                was_truncated=False
            )
        else:
            raise ValueError(f"Invalid injection mode: {mode}")
            
        # Apply injection at specified position
        if position == 'prepend':
            modified_prompt = injection_content + "\n\n" + prompt if prompt else injection_content
        elif position == 'append':
            modified_prompt = prompt + "\n\n" + injection_content if prompt else injection_content
        else:
            raise ValueError(f"Invalid injection position: {position}")
            
        return InjectionResult(
            modified_prompt=modified_prompt,
            was_truncated=was_truncated,
            truncation_details=truncation_details
        )
        
    def _get_default_instruction(self, mode: str, is_required: bool) -> str:
        """Get default instruction text based on mode.
        
        Args:
            mode: Injection mode (list or content)
            is_required: Whether dependencies are required
            
        Returns:
            Default instruction text
        """
        dep_type = "required" if is_required else "optional"
        
        if mode == 'list':
            return f"The following {dep_type} files are available:"
        elif mode == 'content':
            return f"Content from {dep_type} dependencies:"
        else:
            return f"Dependencies ({dep_type}):"
            
    def _generate_list_injection(
        self, 
        files: List[str], 
        instruction: str
    ) -> Tuple[str, bool, Optional[Dict]]:
        """Generate list mode injection.
        
        Args:
            files: List of file paths
            instruction: Instruction text
            
        Returns:
            Tuple of (injection_content, was_truncated, truncation_details)
        """
        lines = [instruction]
        
        for file_path in files:
            lines.append(f"  - {file_path}")
            
        content = "\n".join(lines)
        
        # Check size limit
        if len(content.encode('utf-8')) > MAX_INJECTION_SIZE:
            # Truncate file list
            truncated_lines = [instruction]
            total_size = len(instruction.encode('utf-8'))
            files_shown = 0
            
            for file_path in files:
                line = f"  - {file_path}\n"
                line_size = len(line.encode('utf-8'))
                
                if total_size + line_size > MAX_INJECTION_SIZE:
                    break
                    
                truncated_lines.append(f"  - {file_path}")
                total_size += line_size
                files_shown += 1
                
            truncated_lines.append(f"  ... ({len(files) - files_shown} files omitted due to size limit)")
            
            return (
                "\n".join(truncated_lines),
                True,
                {
                    "total_files": len(files),
                    "files_shown": files_shown,
                    "files_omitted": len(files) - files_shown
                }
            )
            
        return content, False, None
        
    def _generate_content_injection(
        self,
        files: List[str],
        instruction: str,
        *,
        content_snapshot: DependencyContentSnapshot | None = None,
        is_required: bool = True,
    ) -> Tuple[str, bool, Optional[Dict]]:
        """Generate content mode injection.
        
        Args:
            files: List of file paths
            instruction: Instruction text
            
        Returns:
            Tuple of (injection_content, was_truncated, truncation_details)
        """
        snapshot = content_snapshot or self._snapshot_legacy_files(files, is_required=is_required)
        rendered = render_content_snapshot(snapshot, instruction=instruction)
        truncation_details = None
        if rendered.was_truncated:
            files_shown = sum(row.status != "omitted" for row in rendered.group_truncations)
            files_truncated = sum(row.status == "truncated" for row in rendered.group_truncations)
            files_omitted = sum(row.status == "omitted" for row in rendered.group_truncations)
            truncation_details = {
                "injection_truncated": True,
                "truncation_details": {
                    "total_size": sum(row.total_bytes for row in rendered.group_truncations),
                    "shown_size": sum(row.shown_bytes for row in rendered.group_truncations),
                    "files_shown": files_shown,
                    "files_truncated": files_truncated,
                    "files_omitted": files_omitted,
                },
            }
        return rendered.block.decode("utf-8"), rendered.was_truncated, truncation_details

    def _snapshot_legacy_files(
        self,
        files: List[str],
        *,
        is_required: bool,
    ) -> DependencyContentSnapshot:
        role = "required" if is_required else "optional"
        rows: list[AuthoredDependencyRow] = []
        payload_by_target: dict[str, DependencyContent] = {}

        for authored_index, file_path in enumerate(files):
            full_path = self.workspace / file_path
            canonical_target: str | None = None
            try:
                if full_path.exists():
                    normalized = full_path.read_text(encoding="utf-8").encode("utf-8")
                    canonical_target = full_path.resolve().relative_to(self.workspace).as_posix()
                    payload_by_target.setdefault(
                        canonical_target,
                        DependencyContent(canonical_target, normalized),
                    )
            except Exception:
                canonical_target = None

            rows.append(
                AuthoredDependencyRow(
                    role=role,
                    authored_index=authored_index,
                    binding_ref=file_path,
                    evaluated_relpath=file_path,
                    canonical_target=canonical_target,
                )
            )

        return build_content_snapshot(tuple(rows), tuple(payload_by_target.values()))
