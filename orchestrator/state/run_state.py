"""Run state management with in-memory model and persistence."""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Literal
from dataclasses import dataclass, field, asdict
import secrets
import string


@dataclass
class StepState:
    """State of a single step execution."""
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    exit_code: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    output: Optional[Any] = None  # Can be text, lines[], or json object
    lines: Optional[List[str]] = None
    json: Optional[Dict[str, Any]] = None
    truncated: bool = False
    error: Optional[Dict[str, Any]] = None
    debug: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        result = {}
        for key, value in asdict(self).items():
            if value is not None:
                result[key] = value
        return result


@dataclass
class ForEachState:
    """State for a for-each loop."""
    items: List[Any]
    completed_indices: List[int] = field(default_factory=list)
    current_index: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class RunState:
    """Complete run state matching state.json schema v1.1.1."""
    schema_version: str = "1.1.1"
    run_id: str = ""
    workflow_file: str = ""
    workflow_checksum: str = ""
    started_at: str = ""
    updated_at: str = ""
    status: Literal["running", "completed", "failed"] = "running"
    context: Dict[str, Any] = field(default_factory=dict)
    steps: Dict[str, StepState] = field(default_factory=dict)
    for_each: Dict[str, ForEachState] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "workflow_file": self.workflow_file,
            "workflow_checksum": self.workflow_checksum,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "context": self.context,
            "steps": {name: step.to_dict() for name, step in self.steps.items()},
        }
        if self.for_each:
            result["for_each"] = {name: state.to_dict() for name, state in self.for_each.items()}
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RunState':
        """Create RunState from dictionary."""
        state = cls(
            schema_version=data.get("schema_version", "1.1.1"),
            run_id=data.get("run_id", ""),
            workflow_file=data.get("workflow_file", ""),
            workflow_checksum=data.get("workflow_checksum", ""),
            started_at=data.get("started_at", ""),
            updated_at=data.get("updated_at", ""),
            status=data.get("status", "running"),
            context=data.get("context", {}),
        )

        # Reconstruct steps
        for name, step_data in data.get("steps", {}).items():
            state.steps[name] = StepState(**step_data)

        # Reconstruct for_each states
        for name, loop_data in data.get("for_each", {}).items():
            state.for_each[name] = ForEachState(**loop_data)

        return state


class StateManager:
    """Manages run state creation, updates, and persistence."""

    def __init__(self, workspace_path: Path, run_id: Optional[str] = None,
                 backup_enabled: bool = False):
        """Initialize state manager.

        Args:
            workspace_path: Path to workspace root
            run_id: Optional existing run ID for resume
            backup_enabled: Whether to create backups before each step
        """
        self.workspace_path = workspace_path
        self.backup_enabled = backup_enabled
        self.run_id = run_id or self._generate_run_id()
        self.run_root = workspace_path / ".orchestrate" / "runs" / self.run_id
        self.state_file = self.run_root / "state.json"
        self.state: Optional[RunState] = None
        self._backup_count = 0
        self._max_backups = 3

    def _generate_run_id(self) -> str:
        """Generate run ID in format: YYYYMMDDTHHMMSSZ-<6char>."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
        return f"{timestamp}-{suffix}"

    def compute_workflow_checksum(self, workflow_path: Path) -> str:
        """Compute SHA256 checksum of workflow file."""
        with open(workflow_path, 'rb') as f:
            return f"sha256:{hashlib.sha256(f.read()).hexdigest()}"

    def initialize_run(self, workflow_file: str, workflow_path: Path,
                      context: Optional[Dict[str, Any]] = None) -> RunState:
        """Initialize a new run state.

        Args:
            workflow_file: Relative path to workflow file
            workflow_path: Absolute path to workflow file
            context: Optional initial context

        Returns:
            Initialized RunState
        """
        # Create run directory
        self.run_root.mkdir(parents=True, exist_ok=True)
        (self.run_root / "logs").mkdir(exist_ok=True)

        # Create initial state
        now = datetime.now(timezone.utc).isoformat()
        self.state = RunState(
            run_id=self.run_id,
            workflow_file=workflow_file,
            workflow_checksum=self.compute_workflow_checksum(workflow_path),
            started_at=now,
            updated_at=now,
            status="running",
            context=context or {}
        )

        # Save initial state
        self.save_state()
        return self.state

    def load_state(self) -> RunState:
        """Load existing state from file.

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

    def save_state(self, create_backup: bool = None):
        """Save current state to file atomically.

        Args:
            create_backup: Override backup setting for this save
        """
        if self.state is None:
            raise RuntimeError("No state to save")

        # Update timestamp
        self.state.updated_at = datetime.now(timezone.utc).isoformat()

        # Create backup if enabled
        if create_backup is None:
            create_backup = self.backup_enabled

        if create_backup and self.state_file.exists():
            self._create_backup()

        # Write atomically: temp file + rename
        temp_file = self.state_file.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            json.dump(self.state.to_dict(), f, indent=2)

        # Atomic rename
        temp_file.replace(self.state_file)

    def _create_backup(self):
        """Create a backup of current state file."""
        if not self.state_file.exists():
            return

        # Find next backup number
        step_name = "unknown"
        if self.state and self.state.steps:
            # Use the last step name for backup naming
            step_name = list(self.state.steps.keys())[-1] if self.state.steps else "init"

        backup_file = self.state_file.parent / f"state.json.step_{step_name}.bak"

        # Copy current state to backup
        import shutil
        shutil.copy2(self.state_file, backup_file)

        # Clean old backups (keep only last N)
        self._cleanup_old_backups()

    def _cleanup_old_backups(self):
        """Remove old backup files, keeping only the most recent N."""
        backup_files = sorted(
            self.state_file.parent.glob("state.json.step_*.bak"),
            key=lambda p: p.stat().st_mtime
        )

        # Remove oldest backups if we have too many
        while len(backup_files) > self._max_backups:
            backup_files[0].unlink()
            backup_files.pop(0)

    def update_step(self, step_name: str, step_state: StepState):
        """Update state for a specific step.

        Args:
            step_name: Name of the step
            step_state: New state for the step
        """
        if self.state is None:
            raise RuntimeError("State not initialized")

        self.state.steps[step_name] = step_state
        self.save_state()

    def update_status(self, status: Literal["running", "completed", "failed"]):
        """Update overall run status.

        Args:
            status: New status
        """
        if self.state is None:
            raise RuntimeError("State not initialized")

        self.state.status = status
        self.save_state()

    def validate_checksum(self, workflow_path: Path) -> bool:
        """Validate workflow checksum matches stored value.

        Args:
            workflow_path: Path to workflow file

        Returns:
            True if checksum matches, False otherwise
        """
        if self.state is None:
            raise RuntimeError("State not loaded")

        current_checksum = self.compute_workflow_checksum(workflow_path)
        return current_checksum == self.state.workflow_checksum

    def repair_from_backup(self) -> bool:
        """Attempt to repair state from most recent backup.

        Returns:
            True if repair succeeded, False otherwise
        """
        backup_files = sorted(
            self.state_file.parent.glob("state.json.step_*.bak"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        for backup_file in backup_files:
            try:
                with open(backup_file, 'r') as f:
                    data = json.load(f)
                self.state = RunState.from_dict(data)
                self.save_state(create_backup=False)
                return True
            except (json.JSONDecodeError, KeyError):
                continue

        return False