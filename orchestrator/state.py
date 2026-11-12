"""State Manager for Multi-Agent Orchestrator.

Manages run state persistence, atomic writes, and recovery per specs/state.md.
"""

import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal, Mapping
from dataclasses import dataclass, asdict, field
import random
import string
from contextlib import contextmanager

from ._common.io_atomic import (
    atomic_write_text,
    atomic_write_text_at,
)


StateStatus = Literal["running", "suspended", "completed", "failed"]
EvaluatedStateStatus = Literal["running", "settling", "interrupted", "suspended", "completed", "failed"]
StepStatus = Literal["pending", "running", "completed", "failed", "skipped"]


DERIVED_PURE_REPLAY_PROFILE = 'derived_pure_replay.v1'


@dataclass
class StepResult:
    """Result of a single step execution."""
    status: StepStatus
    name: Optional[str] = None
    step_id: Optional[str] = None
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
    artifacts: Optional[Dict[str, Any]] = None
    snapshots: Optional[Dict[str, Any]] = None
    adjudication: Optional[Dict[str, Any]] = None
    managed_jobs: Optional[Dict[str, Any]] = None
    skipped: bool = False
    # Wait-for specific fields (AT-60)
    files: Optional[List[str]] = None
    wait_duration_ms: Optional[int] = None
    poll_count: Optional[int] = None
    timed_out: Optional[bool] = None
    outcome: Optional[Dict[str, Any]] = None
    visit_count: Optional[int] = None
    run_ref: Optional[Dict[str, Any]] = None
    trial: Optional[Dict[str, Any]] = None

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
    status: StateStatus | EvaluatedStateStatus
    result_persistence_profile: Optional[str] = None
    run_root: Optional[str] = None  # Path to .orchestrate/runs/<run_id>
    run_ref_root: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    bound_inputs: Dict[str, Any] = field(default_factory=dict)
    workflow_outputs: Any = field(default_factory=dict)
    finalization: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None
    observability: Optional[Dict[str, Any]] = None
    runtime_observability: Optional[Dict[str, Any]] = None
    current_step: Optional[Dict[str, Any]] = None
    memo_offset: Optional[int] = None
    next_effect: Optional[str] = None
    pending_host_input: Optional[Dict[str, Any]] = None
    steps: Dict[str, Any] = field(default_factory=dict)
    for_each: Dict[str, ForEachState] = field(default_factory=dict)
    repeat_until: Dict[str, Any] = field(default_factory=dict)
    call_frames: Dict[str, Any] = field(default_factory=dict)
    artifact_versions: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    artifact_consumes: Dict[str, Dict[str, int]] = field(default_factory=dict)
    private_artifact_versions: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    private_artifact_consumes: Dict[str, Dict[str, int]] = field(default_factory=dict)
    transition_count: int = 0
    step_visits: Dict[str, int] = field(default_factory=dict)
    provider_attempt_allocations: Dict[str, Any] = field(default_factory=dict)
    human_input: Optional[Dict[str, Any]] = None
    resume_diagnostics: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.result_persistence_profile is None:
            return
        from .workflow.evaluated.authority import PROFILE, SCHEMA_VERSION
        if self.result_persistence_profile == PROFILE:
            if self.schema_version != SCHEMA_VERSION:
                raise ValueError("evaluated state schema is unsupported")
            if self.status not in {"running", "settling", "interrupted", "suspended", "completed", "failed"}:
                raise ValueError("evaluated state status is unsupported")
            if (self.status == "suspended") != (self.pending_host_input is not None):
                raise ValueError("evaluated suspended state is inconsistent")
            if type(self.memo_offset) is not int or self.memo_offset < 0:
                raise ValueError("evaluated memo offset is invalid")
            return

        if self.result_persistence_profile != DERIVED_PURE_REPLAY_PROFILE:
            raise ValueError("result persistence profile is unsupported")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the selected persistence profile."""
        from .workflow.evaluated.authority import PROFILE
        if self.result_persistence_profile == PROFILE:
            return self._evaluated_dict()
        return self._legacy_dict()

    def _legacy_dict(self) -> Dict[str, Any]:
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
            "bound_inputs": self.bound_inputs,
            "workflow_outputs": self.workflow_outputs,
            "finalization": self.finalization,
            "steps": {},
            "for_each": {},
            "repeat_until": self.repeat_until,
            "call_frames": self.call_frames,
            "artifact_versions": self.artifact_versions,
            "artifact_consumes": self.artifact_consumes,
            "private_artifact_versions": self.private_artifact_versions,
            "private_artifact_consumes": self.private_artifact_consumes,
            "transition_count": self.transition_count,
            "step_visits": self.step_visits,
        }

        # Include run_root if set
        if self.run_root:
            result["run_root"] = self.run_root
        if self.run_ref_root is not None:
            result["run_ref_root"] = self.run_ref_root
        if self.result_persistence_profile is not None:
            result[
                "result_persistence_profile"
            ] = self.result_persistence_profile
        if self.observability is not None:
            result["observability"] = self.observability
        if self.runtime_observability is not None:
            result["runtime_observability"] = self.runtime_observability
        if self.error is not None:
            result["error"] = self.error
        if self.current_step is not None:
            result["current_step"] = self.current_step
        if self.provider_attempt_allocations:
            result["provider_attempt_allocations"] = self.provider_attempt_allocations
        if self.resume_diagnostics:
            result["resume_diagnostics"] = deepcopy(self.resume_diagnostics)
        if self.human_input is not None:
            from .workflow.human_input import validate_human_input_record

            validate_human_input_record(self.human_input)
            result["human_input"] = deepcopy(self.human_input)

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

    def _evaluated_dict(self) -> Dict[str, Any]:
        result = {key: getattr(self, key) for key in (
            "schema_version", "result_persistence_profile", "run_id", "workflow_file",
            "workflow_checksum", "started_at", "updated_at", "status", "bound_inputs",
            "workflow_outputs", "error", "current_step", "next_effect", "memo_offset",
        )}
        result["steps"] = {name: value.to_dict() if isinstance(value, StepResult) else value
                           for name, value in self.steps.items()}
        if self.pending_host_input is not None:
            result["pending_host_input"] = self.pending_host_input
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunState":
        """Load the selected profile before legacy schema and status handling."""
        from .workflow.evaluated.authority import PROFILE
        if data.get("result_persistence_profile") == PROFILE:
            return cls._from_evaluated_dict(data)
        return cls._from_legacy_dict(data)

    @classmethod
    def _from_legacy_dict(cls, data: Dict[str, Any]) -> "RunState":
        """Create RunState from dict."""
        result_persistence_profile = data.get("result_persistence_profile")
        if "result_persistence_profile" in data:
            if result_persistence_profile != DERIVED_PURE_REPLAY_PROFILE:
                raise ValueError(
                    "result persistence profile is unsupported"
                )

        # Convert for_each entries to ForEachState objects
        for_each = {}
        if "for_each" in data:
            for name, state_dict in data["for_each"].items():
                for_each[name] = ForEachState(**state_dict)

        provider_attempt_allocations = data.get("provider_attempt_allocations", {})
        resume_diagnostics = data.get("resume_diagnostics", [])
        if (
            not isinstance(resume_diagnostics, list)
            or any(
                not isinstance(item, Mapping)
                or not isinstance(item.get("diagnostic"), str)
                or not item.get("diagnostic")
                for item in resume_diagnostics
            )
        ):
            raise ValueError("resume diagnostic state is invalid")
        human_input = data.get("human_input")
        if human_input is not None:
            from .workflow.human_input import validate_human_input_record

            human_input = validate_human_input_record(human_input)
        if "provider_attempt_allocations" in data:
            if (
                not isinstance(provider_attempt_allocations, Mapping)
                or not provider_attempt_allocations
            ):
                raise ValueError(
                    "provider attempt allocation state must be omitted when empty"
                )
            from .workflow.provider_attempts import validate_provider_attempt_allocations

            try:
                provider_attempt_allocations = validate_provider_attempt_allocations(
                    provider_attempt_allocations
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("provider attempt allocation state is invalid") from exc

        return cls(
            schema_version=data["schema_version"],
            run_id=data["run_id"],
            workflow_file=data["workflow_file"],
            workflow_checksum=data["workflow_checksum"],
            started_at=data["started_at"],
            updated_at=data["updated_at"],
            status=data["status"],
            result_persistence_profile=result_persistence_profile,
            run_root=data.get("run_root"),  # Optional, may not be present in older states
            run_ref_root=data.get("run_ref_root"),
            context=data.get("context", {}),
            bound_inputs=data.get("bound_inputs", {}),
            workflow_outputs=data.get("workflow_outputs", {}),
            finalization=data.get("finalization", {}),
            error=data.get("error"),
            observability=data.get("observability"),
            runtime_observability=data.get("runtime_observability"),
            current_step=data.get("current_step"),
            steps=data.get("steps", {}),
            for_each=for_each,
            repeat_until=data.get("repeat_until", {}),
            call_frames=data.get("call_frames", {}),
            artifact_versions=data.get("artifact_versions", {}),
            artifact_consumes=data.get("artifact_consumes", {}),
            private_artifact_versions=data.get("private_artifact_versions", {}),
            private_artifact_consumes=data.get("private_artifact_consumes", {}),
            transition_count=data.get("transition_count", 0),
            step_visits=data.get("step_visits", {}),
            provider_attempt_allocations=provider_attempt_allocations,
            resume_diagnostics=deepcopy(resume_diagnostics),
            human_input=deepcopy(human_input),
        )

    @classmethod
    def _from_evaluated_dict(cls, data: Dict[str, Any]) -> "RunState":
        required = {key: data[key] for key in (
            "schema_version", "result_persistence_profile", "run_id", "workflow_file",
            "workflow_checksum", "started_at", "updated_at", "status", "memo_offset",
        )}
        optional = {key: data.get(key) for key in (
            "workflow_outputs", "error", "current_step", "next_effect", "pending_host_input",
        )}
        return cls(**required, **optional, bound_inputs=data.get("bound_inputs", {}),
                   steps=data.get("steps", {}))


class StateManager:
    """Manages run state with atomic writes and recovery."""

    SCHEMA_VERSION = "2.1"

    def __init__(
        self,
        workspace: Path,
        run_id: Optional[str] = None,
        state_dir: Optional[Path] = None,
    ):
        """Initialize state manager.

        Args:
            workspace: Workspace root directory
            run_id: Optional run ID to use (generates one if not provided)
            state_dir: Optional override for the runs root directory
        """
        self.workspace = Path(workspace).resolve()

        # Generate or use provided run_id
        if run_id:
            self.run_id = run_id
        else:
            self.run_id = self._generate_run_id()

        # Set up run directory
        self.runs_root = (
            Path(state_dir).resolve()
            if state_dir is not None
            else self.workspace / ".orchestrate" / "runs"
        )
        self.run_root = self.runs_root / self.run_id
        self._run_root_fd: int | None = None
        self.state_file = self.run_root / "state.json"
        self.logs_dir = self.run_root / "logs"

        # Current state (loaded or new)
        self.state: Optional[RunState] = None
        self._lock = threading.RLock()

    @property
    def io_run_root(self) -> Path:
        """Filesystem authority used for run-owned reads and writes."""
        if self._run_root_fd is None:
            return self.run_root
        return Path(f"/proc/self/fd/{self._run_root_fd}")

    def _retain_run_root_fd(self, run_root_fd: int) -> None:
        if self._run_root_fd is None:
            self._run_root_fd = os.dup(run_root_fd)
        else:
            retained = os.fstat(self._run_root_fd)
            supplied = os.fstat(run_root_fd)
            if (retained.st_dev, retained.st_ino) != (
                supplied.st_dev,
                supplied.st_ino,
            ):
                raise ValueError("run root descriptor authority changed")
        self.state_file = self.io_run_root / "state.json"
        self.logs_dir = self.io_run_root / "logs"

    def close(self) -> None:
        """Release retained run-root authority; safe to repeat."""
        if self._run_root_fd is not None:
            os.close(self._run_root_fd)
            self._run_root_fd = None
            self.state_file = self.run_root / "state.json"
            self.logs_dir = self.run_root / "logs"

    @contextmanager
    def _state_mutation(self):
        """Hold the ordinary in-process state mutation lock."""

        with self._lock:
            yield

    def _read_state_from_disk(self) -> RunState:
        """Read and validate state without changing the manager's current object."""
        from .workflow.evaluated.views import has_evaluated_authority, load_evaluated_view
        from .workflow.workspace_files import WorkspaceFiles
        run_files = (WorkspaceFiles(self.run_root, root_fd=self._run_root_fd)
                     if self._run_root_fd is not None else None)
        if has_evaluated_authority(self.io_run_root, run_files=run_files):
            return RunState.from_dict(load_evaluated_view(self.run_root, run_files=run_files))
        with open(self.state_file, "r", encoding="utf-8") as state_stream:
            payload = json.load(state_stream)
        if not isinstance(payload, dict):
            raise ValueError("State file must decode to an object")
        return RunState.from_dict(payload)

    @contextmanager
    def state_transaction(self):
        """Mutate and persist root state under the ordinary in-process lock."""

        with self._state_mutation():
            if self.state is None:
                raise RuntimeError("State not initialized")
            try:
                yield self.state
                self._write_state()
            except BaseException:
                if self.state_file.exists():
                    self.state = self._read_state_from_disk()
                raise

    def allocate_provider_attempt(
        self,
        scope: Any,
        *,
        prompt_fragment_identity_schema_version: str | None = None,
        _origin_manager: Any | None = None,
    ) -> int:
        """Allocate and persist one root-owned provider attempt ordinal."""

        from .workflow.provider_attempts import (
            PROMPT_FRAGMENT_IDENTITY_SCHEMA_VERSIONS,
            ProviderAttemptScope,
            resolve_aggregate_run_owner,
            validate_provider_attempt_allocations,
            validate_provider_attempt_scope,
        )

        if not isinstance(scope, ProviderAttemptScope):
            raise TypeError("ProviderAttemptScope required")
        if (
            prompt_fragment_identity_schema_version is not None
            and (
                not isinstance(
                    prompt_fragment_identity_schema_version,
                    str,
                )
                or prompt_fragment_identity_schema_version
                not in PROMPT_FRAGMENT_IDENTITY_SCHEMA_VERSIONS
            )
        ):
            raise ValueError(
                "provider attempt prompt fragment identity schema authority "
                "is invalid"
            )
        origin_manager = self if _origin_manager is None else _origin_manager
        owner = resolve_aggregate_run_owner(origin_manager)
        if owner.root_manager is not self:
            raise ValueError(
                "provider attempt allocation must execute on aggregate root"
            )
        try:
            with self.state_transaction() as transaction_state:
                owner = resolve_aggregate_run_owner(origin_manager)
                validate_provider_attempt_scope(scope, owner)
                allocations = validate_provider_attempt_allocations(
                    transaction_state.provider_attempt_allocations
                )
                entry = allocations.get(scope.key)
                if entry is None:
                    ordinal = 1
                    entry = {
                        "scope": scope.to_dict(),
                        "last_allocated_ordinal": ordinal,
                    }
                    if prompt_fragment_identity_schema_version is not None:
                        entry[
                            "prompt_fragment_identity_schema_version"
                        ] = prompt_fragment_identity_schema_version
                    allocations[scope.key] = entry
                else:
                    retained_schema_version = entry.get(
                        "prompt_fragment_identity_schema_version"
                    )
                    if retained_schema_version is None:
                        if prompt_fragment_identity_schema_version is not None:
                            raise ValueError(
                                "legacy provider attempt scope cannot acquire "
                                "prompt fragment identity schema authority"
                            )
                    elif (
                        prompt_fragment_identity_schema_version
                        != retained_schema_version
                    ):
                        raise ValueError(
                            "provider attempt prompt fragment identity schema "
                            "authority conflicts with the bound scope"
                        )
                    ordinal = entry["last_allocated_ordinal"] + 1
                    entry["last_allocated_ordinal"] = ordinal
                transaction_state.provider_attempt_allocations = allocations
        except BaseException:
            if self.state_file.exists():
                with self._lock:
                    self.state = self._read_state_from_disk()
            raise
        return ordinal

    @staticmethod
    def new_run_id() -> str:
        """Generate/allocate a fresh run id in the current format (Task 8 seam).

        Public so prompt-run can allocate an id without constructing a
        StateManager (which would generate and discard one); reservation of
        the id's run root is ``create_run_root``'s job, not this method's.
        """
        return StateManager._generate_run_id()

    @staticmethod
    def _generate_run_id() -> str:
        """Generate run ID in format: YYYYMMDDTHHMMSSZ-<6char>."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"{timestamp}-{suffix}"

    def load(self) -> RunState:
        """Load existing state from disk.

        Returns:
            Loaded RunState

        Raises:
            FileNotFoundError: If state file doesn't exist
            json.JSONDecodeError: If state file is corrupted
        """
        with self._lock:
            self.state = self._read_state_from_disk()
            return self.state

    def _write_state(self, *, run_root_fd: int | None = None):
        """Write state atomically (temp file + rename)."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("No state to write")

            # Update timestamp
            self.state.updated_at = datetime.now(timezone.utc).isoformat()
            payload = json.dumps(self.state.to_dict(), indent=2)
            if run_root_fd is None:
                atomic_write_text(self.state_file, payload)
            else:
                atomic_write_text_at(run_root_fd, "state.json", payload)

