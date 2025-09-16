"""Dependency injection into prompts."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

# Size limits per spec
MAX_INJECTION_SIZE = 256 * 1024  # ~256 KiB


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
        is_required: bool = True
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
            instruction = inject_config.get(
                'instruction', 
                self._get_default_instruction(mode, is_required)
            )
            
        # Generate injection content based on mode
        if mode == 'list':
            injection_content, was_truncated, truncation_details = self._generate_list_injection(
                files, instruction
            )
        elif mode == 'content':
            injection_content, was_truncated, truncation_details = self._generate_content_injection(
                files, instruction  
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
        instruction: str
    ) -> Tuple[str, bool, Optional[Dict]]:
        """Generate content mode injection.
        
        Args:
            files: List of file paths
            instruction: Instruction text
            
        Returns:
            Tuple of (injection_content, was_truncated, truncation_details)
        """
        sections = [instruction]
        total_size = len(instruction.encode('utf-8'))
        was_truncated = False
        files_shown = 0
        files_truncated = 0
        files_omitted = 0
        shown_size = 0
        original_total_size = 0
        
        for file_path in files:
            full_path = self.workspace / file_path
            
            # Skip if file doesn't exist (for optional dependencies)
            if not full_path.exists():
                continue
                
            try:
                # Read file content
                content = full_path.read_text(encoding='utf-8')
                file_size = len(content.encode('utf-8'))
                original_total_size += file_size
                
                # Create header
                header = f"\n=== File: {file_path} "
                
                # Check if we can fit the whole file
                header_size = len(header.encode('utf-8')) + 20  # Reserve space for size info
                
                if total_size + header_size + file_size > MAX_INJECTION_SIZE:
                    # Need to truncate or omit
                    remaining = MAX_INJECTION_SIZE - total_size - header_size
                    
                    if remaining < 100:  # Too small to be useful
                        files_omitted += 1
                        was_truncated = True
                        continue
                        
                    # Truncate file content
                    truncated_content = content.encode('utf-8')[:remaining].decode('utf-8', errors='ignore')
                    header += f"({len(truncated_content.encode('utf-8'))}/{file_size} bytes) ==="
                    sections.append(header)
                    sections.append(truncated_content)
                    sections.append("... (truncated)")
                    
                    files_shown += 1
                    files_truncated += 1
                    shown_size += len(truncated_content.encode('utf-8'))
                    total_size += header_size + len(truncated_content.encode('utf-8'))
                    was_truncated = True
                    break  # Hit size limit
                else:
                    # Include full file
                    header += f"({file_size}/{file_size} bytes) ==="
                    sections.append(header)
                    sections.append(content)
                    
                    files_shown += 1
                    shown_size += file_size
                    total_size += header_size + file_size
                    
            except Exception as e:
                # Skip files that can't be read
                continue
                
        # Add summary if truncated
        if was_truncated:
            sections.append(
                f"\n... Injection truncated at {MAX_INJECTION_SIZE} bytes. "
                f"Files: {files_shown} shown, {files_truncated} truncated, "
                f"{files_omitted} omitted."
            )
            
        truncation_details = None
        if was_truncated:
            truncation_details = {
                "injection_truncated": True,
                "truncation_details": {
                    "total_size": original_total_size,
                    "shown_size": shown_size,
                    "files_shown": files_shown,
                    "files_truncated": files_truncated,
                    "files_omitted": files_omitted
                }
            }
            
        return "\n".join(sections), was_truncated, truncation_details
