"""State Manager for Multi-Agent Orchestrator.

Manages run state persistence, atomic writes, and recovery per specs/state.md.
"""

import json
import hashlib
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal
from dataclasses import dataclass, asdict, field
import random
import string


StateStatus = Literal["running", "completed", "failed"]
StepStatus = Literal["pending", "running", "completed", "failed", "skipped"]


@dataclass
class StepResult:
    """Result of a single step execution."""
    status: StepStatus
    exit_code: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    output: Optional[Any] = None
    truncated: bool = False
    lines: Optional[List[str]] = None
    json: Optional[Any] = None
    text: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
    debug: Optional[Dict[str, Any]] = None
    skipped: bool = False
    # Wait-for specific fields (AT-60)
    files: Optional[List[str]] = None
    wait_duration_ms: Optional[int] = None
    poll_count: Optional[int] = None
    timed_out: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict, omitting None values."""
        result = {}
        for k, v in asdict(self).items():
            if v is not None:
                result[k] = v
        return result


@dataclass
class ForEachState:
    """State tracking for for_each loops."""
    items: List[Any]
    completed_indices: List[int] = field(default_factory=list)
    current_index: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return asdict(self)


@dataclass
class RunState:
    """Complete run state matching specs/state.md schema."""
    schema_version: str
    run_id: str
    workflow_file: str
    workflow_checksum: str
    started_at: str
    updated_at: str
    status: StateStatus
    run_root: Optional[str] = None  # Path to .orchestrate/runs/<run_id>
    context: Dict[str, Any] = field(default_factory=dict)
    steps: Dict[str, Any] = field(default_factory=dict)
    for_each: Dict[str, ForEachState] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "workflow_file": self.workflow_file,
            "workflow_checksum": self.workflow_checksum,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "context": self.context,
            "steps": {},
            "for_each": {}
        }

        # Include run_root if set
        if self.run_root:
            result["run_root"] = self.run_root

        # Convert step results - type assert for type checker
        steps_dict: Dict[str, Any] = result["steps"]
        for name, value in self.steps.items():
            if isinstance(value, StepResult):
                steps_dict[name] = value.to_dict()
            else:
                steps_dict[name] = value

        # Convert for_each states - type assert for type checker
        for_each_dict: Dict[str, Any] = result["for_each"]
        for name, state in self.for_each.items():
            if isinstance(state, ForEachState):
                for_each_dict[name] = state.to_dict()
            else:
                for_each_dict[name] = state

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunState":
        """Create RunState from dict."""
        # Convert for_each entries to ForEachState objects
        for_each = {}
        if "for_each" in data:
            for name, state_dict in data["for_each"].items():
                for_each[name] = ForEachState(**state_dict)

        return cls(
            schema_version=data["schema_version"],
            run_id=data["run_id"],
            workflow_file=data["workflow_file"],
            workflow_checksum=data["workflow_checksum"],
            started_at=data["started_at"],
            updated_at=data["updated_at"],
            status=data["status"],
            run_root=data.get("run_root"),  # Optional, may not be present in older states
            context=data.get("context", {}),
            steps=data.get("steps", {}),
            for_each=for_each
        )


class StateManager:
    """Manages run state with atomic writes and recovery."""

    SCHEMA_VERSION = "1.1.1"

    def __init__(self, workspace: Path, run_id: Optional[str] = None,
                 backup_enabled: bool = False, debug: bool = False):
        """Initialize state manager.

        Args:
            workspace: Workspace root directory
            run_id: Optional run ID to use (generates one if not provided)
            backup_enabled: Enable state backups before each step
            debug: Debug mode (implies backup_enabled)
        """
        self.workspace = Path(workspace)
        self.backup_enabled = backup_enabled or debug
        self.debug = debug

        # Generate or use provided run_id
        if run_id:
            self.run_id = run_id
        else:
            self.run_id = self._generate_run_id()

        # Set up run directory
        self.run_root = self.workspace / ".orchestrate" / "runs" / self.run_id
        self.state_file = self.run_root / "state.json"
        self.logs_dir = self.run_root / "logs"

        # Track backup count for rotation
        self.backup_count = 0
        self.max_backups = 3

        # Current state (loaded or new)
        self.state: Optional[RunState] = None

    def _generate_run_id(self) -> str:
        """Generate run ID in format: YYYYMMDDTHHMMSSZ-<6char>."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"{timestamp}-{suffix}"

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return f"sha256:{sha256.hexdigest()}"

    def initialize(self, workflow_file: str, context: Optional[Dict[str, Any]] = None) -> RunState:
        """Initialize a new run state.

        Args:
            workflow_file: Path to workflow YAML file
            context: Optional initial context variables

        Returns:
            Initialized RunState
        """
        # Create run directory structure
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)

        # Calculate workflow checksum
        workflow_path = self.workspace / workflow_file
        if not workflow_path.exists():
            raise FileNotFoundError(f"Workflow file not found: {workflow_file}")

        workflow_checksum = self._calculate_checksum(workflow_path)

        # Create initial state
        now = datetime.now(timezone.utc).isoformat()
        self.state = RunState(
            schema_version=self.SCHEMA_VERSION,
            run_id=self.run_id,
            workflow_file=workflow_file,
            workflow_checksum=workflow_checksum,
            started_at=now,
            updated_at=now,
            status="running",
            run_root=str(self.run_root),  # Store run_root path
            context=context or {}
        )

        # Write initial state
        self._write_state()

        return self.state

    def load(self) -> RunState:
        """Load existing state from disk.

        Returns:
            Loaded RunState

        Raises:
            FileNotFoundError: If state file doesn't exist
            json.JSONDecodeError: If state file is corrupted
        """
        if not self.state_file.exists():
            raise FileNotFoundError(f"State file not found: {self.state_file}")

        with open(self.state_file, 'r') as f:
            data = json.load(f)

        self.state = RunState.from_dict(data)
        return self.state

    def _write_state(self):
        """Write state atomically (temp file + rename)."""
        if not self.state:
            raise RuntimeError("No state to write")

        # Update timestamp
        self.state.updated_at = datetime.now(timezone.utc).isoformat()

        # Write to temp file
        temp_file = self.state_file.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            json.dump(self.state.to_dict(), f, indent=2)

        # Atomic rename
        temp_file.replace(self.state_file)

    def backup_state(self, step_name: str):
        """Create a backup of current state before step execution.

        Args:
            step_name: Name of the step about to be executed
        """
        if not self.backup_enabled or not self.state_file.exists():
            return

        # Backup filename
        backup_file = self.state_file.parent / f"state.json.step_{step_name}.bak"

        # Copy current state to backup
        shutil.copy2(self.state_file, backup_file)

        # Rotate backups (keep last 3)
        self._rotate_backups()

    def _rotate_backups(self):
        """Keep only the last N backups."""
        backup_pattern = "state.json.step_*.bak"
        backups = sorted(self.state_file.parent.glob(backup_pattern))

        if len(backups) > self.max_backups:
            # Remove oldest backups
            for old_backup in backups[:-self.max_backups]:
                old_backup.unlink()

    def update_step(self, step_name: str, result: StepResult):
        """Update step result in state.

        Args:
            step_name: Name of the step
            result: Step execution result
        """
        if not self.state:
            raise RuntimeError("State not initialized")

        self.state.steps[step_name] = result
        self._write_state()

    def update_loop_step(self, loop_name: str, index: int, step_name: str, result: StepResult):
        """Update step result for loop iteration.

        Stores as steps.<LoopName>[i].<StepName> per specs/state.md.

        Args:
            loop_name: Name of the for_each loop
            index: Current iteration index
            step_name: Name of the step within the loop
            result: Step execution result
        """
        if not self.state:
            raise RuntimeError("State not initialized")

        # Format: steps.<LoopName>[i].<StepName>
        key = f"{loop_name}[{index}].{step_name}"
        self.state.steps[key] = result
        self._write_state()

    def update_loop_results(self, loop_name: str, loop_results: List[Dict[str, Any]]):
        """Update for_each loop results array.

        Stores the array of iteration results as steps.<LoopName> per specs.

        Args:
            loop_name: Name of the for_each loop
            loop_results: Array of iteration result dictionaries
        """
        if not self.state:
            raise RuntimeError("State not initialized")

        # Store the loop results array directly
        self.state.steps[loop_name] = loop_results
        self._write_state()

    def update_for_each(self, loop_name: str, state: ForEachState):
        """Update for_each loop state.

        Args:
            loop_name: Name of the for_each loop
            state: Current loop state
        """
        if not self.state:
            raise RuntimeError("State not initialized")

        self.state.for_each[loop_name] = state
        self._write_state()

    def update_status(self, status: StateStatus):
        """Update overall run status.

        Args:
            status: New run status
        """
        if not self.state:
            raise RuntimeError("State not initialized")

        self.state.status = status
        self._write_state()

    def get_step_result(self, step_name: str) -> Optional[StepResult]:
        """Get result of a specific step.

        Args:
            step_name: Name of the step

        Returns:
            Step result or None if not found
        """
        if not self.state:
            return None

        result = self.state.steps.get(step_name)
        if isinstance(result, dict):
            # Convert dict back to StepResult if needed
            return StepResult(**result)
        return result

    def validate_checksum(self, workflow_file: str) -> bool:
        """Validate workflow checksum matches state.

        Args:
            workflow_file: Path to workflow file

        Returns:
            True if checksum matches, False otherwise
        """
        if not self.state:
            return False

        workflow_path = self.workspace / workflow_file
        if not workflow_path.exists():
            return False

        current_checksum = self._calculate_checksum(workflow_path)
        return current_checksum == self.state.workflow_checksum

    def attempt_repair(self) -> bool:
        """Attempt to repair state from latest valid backup.

        Returns:
            True if repair successful, False otherwise
        """
        # Find available backups
        backup_pattern = "state.json.step_*.bak"
        backups = sorted(self.state_file.parent.glob(backup_pattern), reverse=True)

        for backup in backups:
            try:
                # Try to load backup
                with open(backup, 'r') as f:
                    data = json.load(f)

                # Validate it can be parsed
                state = RunState.from_dict(data)

                # Restore from backup
                shutil.copy2(backup, self.state_file)
                self.state = state

                return True

            except (json.JSONDecodeError, KeyError, TypeError):
                # This backup is also corrupted, try next
                continue

        return False