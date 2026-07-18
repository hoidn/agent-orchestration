"""State Manager for Multi-Agent Orchestrator.

Manages run state persistence, atomic writes, and recovery per specs/state.md.
"""

import json
import hashlib
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal, Mapping
from dataclasses import dataclass, asdict, field
import random
import string
from contextlib import contextmanager, nullcontext

from .state_locking import (
    durable_atomic_write,
    exclusive_file_lock,
    provider_attempt_process_locks,
)


StateStatus = Literal["running", "completed", "failed"]
StepStatus = Literal["pending", "running", "completed", "failed", "skipped"]


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
    bound_inputs: Dict[str, Any] = field(default_factory=dict)
    workflow_outputs: Dict[str, Any] = field(default_factory=dict)
    finalization: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None
    observability: Optional[Dict[str, Any]] = None
    runtime_observability: Optional[Dict[str, Any]] = None
    current_step: Optional[Dict[str, Any]] = None
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

        provider_attempt_allocations = data.get("provider_attempt_allocations", {})
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
            run_root=data.get("run_root"),  # Optional, may not be present in older states
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
        )


class StateManager:
    """Manages run state with atomic writes and recovery."""

    SCHEMA_VERSION = "2.1"
    PROVIDER_ATTEMPT_REPAIR_BARRIER_NAME = ".provider-attempt-allocation-started"
    PROVIDER_ATTEMPT_REPAIR_BARRIER_BYTES = (
        b'{"schema_version":"provider_attempt_repair_barrier.v1"}\n'
    )

    def __init__(
        self,
        workspace: Path,
        run_id: Optional[str] = None,
        backup_enabled: bool = False,
        debug: bool = False,
        state_dir: Optional[Path] = None,
    ):
        """Initialize state manager.

        Args:
            workspace: Workspace root directory
            run_id: Optional run ID to use (generates one if not provided)
            backup_enabled: Enable state backups before each step
            debug: Debug mode (implies backup_enabled)
            state_dir: Optional override for the runs root directory
        """
        self.workspace = Path(workspace).resolve()
        self.backup_enabled = backup_enabled or debug
        self.debug = debug

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
        self.state_file = self.run_root / "state.json"
        self.logs_dir = self.run_root / "logs"

        # Track backup count for rotation
        self.backup_count = 0
        self.max_backups = 3

        # Current state (loaded or new)
        self.state: Optional[RunState] = None
        self._lock = threading.RLock()
        self._mutation_local = threading.local()
        self._durable_state_writes = False

    def enable_durable_state_writes(self) -> None:
        """Coordinate subsequent root-state writes across processes."""

        self._durable_state_writes = True

    @contextmanager
    def _state_mutation(
        self,
        *,
        reload_from_disk: bool = True,
        force_process_lock: bool = False,
    ):
        """Acquire process coordination before the root in-process lock.

        Public read-modify-write methods use the default authoritative reload
        before applying their mutation. ``_write_state`` disables that reload
        because its caller has already mutated the current state object.
        Allocator transitions retain their own explicit reload while holding
        both process locks and the root lock.
        """

        depth = getattr(self._mutation_local, "depth", 0)
        if depth:
            self._mutation_local.depth = depth + 1
            try:
                yield
            finally:
                self._mutation_local.depth = depth
            return
        process_lock = (
            exclusive_file_lock(self.run_root / ".state-mutation.lock")
            if self._durable_state_writes or force_process_lock
            else nullcontext()
        )
        with process_lock:
            with self._lock:
                if (
                    reload_from_disk
                    and self._durable_state_writes
                    and self.state is not None
                    and self.state_file.exists()
                ):
                    self._reload_state_for_coordinated_mutation()
                self._mutation_local.depth = depth + 1
                try:
                    yield
                finally:
                    self._mutation_local.depth = depth

    def _reload_state_for_coordinated_mutation(self) -> RunState:
        self.state = self._read_state_from_disk()
        return self.state

    def _read_state_from_disk(self) -> RunState:
        """Read and validate state without changing the manager's current object."""

        with open(self.state_file, "r", encoding="utf-8") as state_stream:
            payload = json.load(state_stream)
        if not isinstance(payload, dict):
            raise ValueError("State file must decode to an object")
        return RunState.from_dict(payload)

    @contextmanager
    def state_transaction(self):
        """Reload, mutate, and persist root state under one coordinated lock."""

        with self._state_mutation():
            if self.state is None:
                raise RuntimeError("State not initialized")
            try:
                yield self.state
            except BaseException:
                self._reload_state_for_coordinated_mutation()
                raise
            else:
                self._write_state()

    def _persist_state_durably(self) -> None:
        if self.state is None:
            raise RuntimeError("No state to write")
        self.state.updated_at = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(self.state.to_dict(), indent=2).encode("utf-8")
        durable_atomic_write(self.state_file, payload)

    def _ensure_provider_attempt_repair_barrier(self) -> None:
        """Durably record that backup repair can no longer prove allocator freshness."""

        barrier = self.run_root / self.PROVIDER_ATTEMPT_REPAIR_BARRIER_NAME
        if barrier.exists():
            if barrier.read_bytes() != self.PROVIDER_ATTEMPT_REPAIR_BARRIER_BYTES:
                raise ValueError("provider attempt repair barrier is invalid")
            return
        durable_atomic_write(
            barrier,
            self.PROVIDER_ATTEMPT_REPAIR_BARRIER_BYTES,
        )

    def allocate_provider_attempt(self, scope: Any) -> int:
        """Allocate and durably persist one root-owned provider attempt ordinal."""

        return self._allocate_provider_attempt_from(self, scope)

    def _allocate_provider_attempt_from(self, origin_manager: Any, scope: Any) -> int:
        from .workflow.provider_attempts import (
            ProviderAttemptScope,
            resolve_aggregate_run_owner,
            validate_provider_attempt_allocations,
            validate_provider_attempt_scope,
        )

        if not isinstance(scope, ProviderAttemptScope):
            raise TypeError("ProviderAttemptScope required")
        owner = resolve_aggregate_run_owner(origin_manager)
        if owner.root_manager is not self:
            return owner.root_manager._allocate_provider_attempt_from(origin_manager, scope)
        self.enable_durable_state_writes()
        with provider_attempt_process_locks(self.run_root):
            with self._lock:
                self._reload_state_for_coordinated_mutation()
                owner = resolve_aggregate_run_owner(origin_manager)
                validate_provider_attempt_scope(scope, owner)
                assert self.state is not None
                allocations = validate_provider_attempt_allocations(
                    self.state.provider_attempt_allocations
                )
                self._ensure_provider_attempt_repair_barrier()
                entry = allocations.get(scope.key)
                if entry is None:
                    ordinal = 1
                    entry = {
                        "scope": scope.to_dict(),
                        "last_allocated_ordinal": ordinal,
                        "events": [{"ordinal": ordinal, "event": "allocated"}],
                    }
                    allocations[scope.key] = entry
                else:
                    ordinal = entry["last_allocated_ordinal"] + 1
                    entry["last_allocated_ordinal"] = ordinal
                    entry["events"].append({"ordinal": ordinal, "event": "allocated"})
                self.state.provider_attempt_allocations = allocations
                self._persist_state_durably()
                return ordinal

    def record_provider_attempt_publication(
        self,
        scope: Any,
        ordinal: int,
        *,
        relative_path: str,
        file_sha256: str,
        record_kind: str,
    ) -> None:
        """Durably persist one closed publication event beside its allocation."""

        self._record_provider_attempt_publication_from(
            self,
            scope,
            ordinal,
            relative_path=relative_path,
            file_sha256=file_sha256,
            record_kind=record_kind,
        )

    def _record_provider_attempt_publication_from(
        self,
        origin_manager: Any,
        scope: Any,
        ordinal: int,
        *,
        relative_path: str,
        file_sha256: str,
        record_kind: str,
    ) -> None:
        from .workflow.provider_attempts import (
            ProviderAttemptScope,
            resolve_aggregate_run_owner,
            validate_provider_attempt_allocations,
            validate_provider_attempt_scope,
        )

        if not isinstance(scope, ProviderAttemptScope):
            raise TypeError("ProviderAttemptScope required")
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal <= 0:
            raise ValueError("provider attempt ordinal must be positive")
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError("publication relative_path must be non-empty")
        if (
            not isinstance(file_sha256, str)
            or len(file_sha256) != 71
            or not file_sha256.startswith("sha256:")
            or any(character not in "0123456789abcdef" for character in file_sha256[7:])
        ):
            raise ValueError("publication file_sha256 is invalid")
        if record_kind not in {"prompt_snapshot", "failure"}:
            raise ValueError("publication record_kind is invalid")
        owner = resolve_aggregate_run_owner(origin_manager)
        if owner.root_manager is not self:
            owner.root_manager._record_provider_attempt_publication_from(
                origin_manager,
                scope,
                ordinal,
                relative_path=relative_path,
                file_sha256=file_sha256,
                record_kind=record_kind,
            )
            return
        self.enable_durable_state_writes()
        with provider_attempt_process_locks(self.run_root):
            with self._lock:
                self._reload_state_for_coordinated_mutation()
                self._record_provider_attempt_publication_already_process_locked(
                    origin_manager,
                    scope,
                    ordinal,
                    relative_path=relative_path,
                    file_sha256=file_sha256,
                    record_kind=record_kind,
                )

    def _record_provider_attempt_publication_already_process_locked(
        self,
        origin_manager: Any,
        scope: Any,
        ordinal: int,
        *,
        relative_path: str,
        file_sha256: str,
        record_kind: str,
    ) -> None:
        """Persist a publication while the caller holds both process locks and RLock."""

        from .workflow.provider_attempts import validate_provider_attempt_allocations

        allocations, entry = (
            self._validate_provider_attempt_publication_already_process_locked(
                origin_manager, scope, ordinal
            )
        )
        allocated = {"ordinal": ordinal, "event": "allocated"}
        entry["events"].insert(
            entry["events"].index(allocated) + 1,
            {
                "ordinal": ordinal,
                "event": "evidence_published",
                "relative_path": relative_path,
                "file_sha256": file_sha256,
                "record_kind": record_kind,
            },
        )
        self.state.provider_attempt_allocations = validate_provider_attempt_allocations(
            allocations
        )
        self._persist_state_durably()

    def _validate_provider_attempt_publication_already_process_locked(
        self,
        origin_manager: Any,
        scope: Any,
        ordinal: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Validate publication eligibility while both process locks and RLock are held."""

        from .workflow.provider_attempts import (
            resolve_aggregate_run_owner,
            validate_provider_attempt_allocations,
            validate_provider_attempt_scope,
        )

        owner = resolve_aggregate_run_owner(origin_manager)
        if owner.root_manager is not self:
            raise ValueError("already-locked publication must execute on aggregate root")
        validate_provider_attempt_scope(scope, owner)
        assert self.state is not None
        allocations = validate_provider_attempt_allocations(
            self.state.provider_attempt_allocations
        )
        entry = allocations.get(scope.key)
        if entry is None:
            raise ValueError("provider attempt allocation is missing")
        allocated = {"ordinal": ordinal, "event": "allocated"}
        if allocated not in entry["events"]:
            raise ValueError("provider attempt allocation ordinal is missing")
        if any(
            event.get("ordinal") == ordinal
            and event.get("event") == "evidence_published"
            for event in entry["events"]
        ):
            raise ValueError("provider attempt evidence is already published")
        return allocations, entry

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

    def calculate_checksum(self, file_path: Path | str) -> str:
        """Calculate a SHA256 checksum for a workflow or artifact file."""
        return self._calculate_checksum(Path(file_path))

    def initialize(
        self,
        workflow_file: str,
        context: Optional[Dict[str, Any]] = None,
        bound_inputs: Optional[Dict[str, Any]] = None,
        observability: Optional[Dict[str, Any]] = None,
    ) -> RunState:
        """Initialize a new run state.

        Args:
            workflow_file: Path to workflow YAML file
            context: Optional initial context variables

        Returns:
            Initialized RunState
        """
        with self._state_mutation():
            # Create run directory structure
            self.run_root.mkdir(parents=True, exist_ok=True)
            self.logs_dir.mkdir(exist_ok=True)

            # Calculate workflow checksum
            workflow_path = self.workspace / workflow_file
            if not workflow_path.exists():
                raise FileNotFoundError(f"Workflow file not found: {workflow_file}")

            workflow_checksum = self.calculate_checksum(workflow_path)

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
                context=context or {},
                bound_inputs=bound_inputs or {},
                observability=observability,
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
        with self._lock:
            if not self.state_file.exists():
                raise FileNotFoundError(f"State file not found: {self.state_file}")

            with open(self.state_file, 'r') as f:
                data = json.load(f)

            self.state = RunState.from_dict(data)
            if self.state.provider_attempt_allocations:
                self.enable_durable_state_writes()
            return self.state

    def _write_state(self):
        """Write state atomically (temp file + rename)."""
        top_level_direct_write = getattr(self._mutation_local, "depth", 0) == 0
        with self._state_mutation(reload_from_disk=False):
            if not self.state:
                raise RuntimeError("No state to write")

            if (
                top_level_direct_write
                and self._durable_state_writes
                and self.state_file.exists()
            ):
                # Allocator projection is root-owned and may advance in another
                # process after a legacy direct caller mutates another field.
                # A blind direct commit may preserve its caller mutation, but it
                # must never roll this independently concurrent projection back.
                persisted_state = self._read_state_from_disk()
                self.state.provider_attempt_allocations = (
                    persisted_state.provider_attempt_allocations
                )

            # Update timestamp
            self.state.updated_at = datetime.now(timezone.utc).isoformat()

            if self._durable_state_writes:
                payload = json.dumps(self.state.to_dict(), indent=2).encode("utf-8")
                durable_atomic_write(self.state_file, payload)
            else:
                # Preserve the established unaffected-run serialization path.
                temp_file = self.state_file.with_suffix('.tmp')
                with open(temp_file, 'w') as f:
                    json.dump(self.state.to_dict(), f, indent=2)
                temp_file.replace(self.state_file)

    def _write_json_atomic(self, path: Path, payload: Dict[str, Any]) -> None:
        """Write an arbitrary JSON payload atomically."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = path.with_suffix(f"{path.suffix}.tmp")
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        temp_file.replace(path)

    def read_runtime_sidecar_json(self, path: Path | str) -> Optional[Dict[str, Any]]:
        """Read one runtime-sidecar JSON object when it exists."""
        with self._lock:
            resolved = Path(path)
            if not resolved.exists():
                return None
            with open(resolved, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            if not isinstance(payload, dict):
                raise ValueError(f"Runtime sidecar JSON must decode to an object: {resolved}")
            return payload

    def write_runtime_sidecar_json(self, path: Path | str, payload: Dict[str, Any]) -> None:
        """Atomically persist one runtime-sidecar JSON object."""
        with self._lock:
            self._write_json_atomic(Path(path), payload)

    def workflow_lisp_checkpoint_shadow_report_path(self) -> Path:
        """Return the canonical runtime shadow-report path for Workflow Lisp sidecars."""
        return self.run_root / "workflow_lisp" / "checkpoints" / "shadow_report.json"

    def workflow_lisp_checkpoint_restore_report_path(self) -> Path:
        """Return the canonical runtime restore-report path for Workflow Lisp sidecars."""
        return self.run_root / "workflow_lisp" / "checkpoints" / "restore_report.json"

    def workflow_lisp_checkpoint_default_resume_report_path(self) -> Path:
        """Return the canonical runtime default-resume report path for Workflow Lisp sidecars."""
        return self.run_root / "workflow_lisp" / "checkpoints" / "default_resume_report.json"

    def provider_session_paths(self, step_id: str, visit_count: int) -> tuple[Path, Path]:
        """Return the canonical metadata and transport-spool paths for one session visit."""
        safe_step_id = step_id.replace("/", "_")
        session_root = self.run_root / "provider_sessions"
        session_root.mkdir(parents=True, exist_ok=True)
        visit_key = f"{safe_step_id}__v{visit_count}"
        return (
            session_root / f"{visit_key}.json",
            session_root / f"{visit_key}.transport.log",
        )

    def initialize_provider_session_visit(
        self,
        *,
        provider_name: str,
        step_name: str,
        step_id: str,
        visit_count: int,
        mode: str,
    ) -> Dict[str, Any]:
        """Create the canonical metadata/spool artifacts before persisting current_step."""
        with self._lock:
            metadata_path, transport_spool_path = self.provider_session_paths(step_id, visit_count)
            transport_spool_path.write_text("", encoding='utf-8')
            now = datetime.now(timezone.utc).isoformat()
            metadata = {
                "run_id": self.run_id,
                "provider": provider_name,
                "step_name": step_name,
                "step_id": step_id,
                "visit_count": visit_count,
                "mode": mode,
                "step_status": "running",
                "publication_state": "pending",
                "session_id": None,
                "metadata_mode": None,
                "command_variant": None,
                "resolved_command": None,
                "started_at": now,
                "updated_at": now,
                "captured_transport_bytes": 0,
                "parser_summary": {},
                "transport_spool_path": str(transport_spool_path),
            }
            self._write_json_atomic(metadata_path, metadata)
            return {
                "metadata_path": str(metadata_path),
                "transport_spool_path": str(transport_spool_path),
            }

    def update_provider_session_metadata(
        self,
        metadata_path: Path | str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Atomically merge updates into one provider-session metadata record."""
        with self._lock:
            path = Path(metadata_path)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    payload = json.load(f)
            else:
                payload = {}
            payload.update(updates)
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write_json_atomic(path, payload)
            return payload

    def fail_run(
        self,
        error: Dict[str, Any],
        *,
        clear_current_step: bool = False,
        expected_step_id: Optional[str] = None,
        expected_visit_count: Optional[int] = None,
    ) -> None:
        """Persist a run-level failure, optionally clearing the matching current_step."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            self.state.status = "failed"
            self.state.error = error

            if clear_current_step and isinstance(self.state.current_step, dict):
                current_step = self.state.current_step
                if expected_step_id is not None and current_step.get("step_id") != expected_step_id:
                    self._write_state()
                    return
                if (
                    expected_visit_count is not None
                    and current_step.get("visit_count") != expected_visit_count
                ):
                    self._write_state()
                    return
                self.state.current_step = None
            elif isinstance(self.state.current_step, dict):
                self.state.current_step["status"] = "failed"
                self.state.current_step["failed_at"] = datetime.now(timezone.utc).isoformat()

            self._write_state()

    def _record_atomic_root_failure(self, error: Mapping[str, Any]) -> None:
        """Replace only the root failure envelope while preserving raw state."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            with open(self.state_file, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            if not isinstance(payload, dict):
                raise ValueError("State file must decode to an object")

            payload["status"] = "failed"
            payload["error"] = dict(error)
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            if self._durable_state_writes:
                durable_atomic_write(
                    self.state_file,
                    json.dumps(payload, indent=2).encode("utf-8"),
                )
            else:
                self._write_json_atomic(self.state_file, payload)
            self.state = RunState.from_dict(payload)

    def record_resume_projection_integrity_failure(
        self,
        error: Mapping[str, Any],
    ) -> None:
        """Atomically change only status, error, and updated_at."""
        self._record_atomic_root_failure(error)

    def record_workflow_checksum_mismatch(
        self,
        *,
        workflow_file: str | None,
        persisted_checksum: str | None,
        current_checksum: str | None,
        reason: str,
    ) -> None:
        """Atomically record the structured root checksum-mismatch envelope."""
        self._record_atomic_root_failure(
            {
                "type": "workflow_checksum_mismatch",
                "message": "Workflow has been modified since the run started",
                "context": {
                    "workflow_file": workflow_file,
                    "persisted_checksum": persisted_checksum,
                    "current_checksum": current_checksum,
                    "reason": reason,
                },
            }
        )

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
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            self.state.steps[step_name] = result
            if (
                self.state.current_step is not None
                and self.state.current_step.get("name") == step_name
            ):
                self.state.current_step = None
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
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            # Format: steps.<LoopName>[i].<StepName>
            key = f"{loop_name}[{index}].{step_name}"
            self.state.steps[key] = result
            self._write_state()

    def clear_loop_step(self, loop_name: str, index: int, step_name: str) -> None:
        """Remove one persisted loop-iteration step result."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            key = f"{loop_name}[{index}].{step_name}"
            self.state.steps.pop(key, None)
            self._write_state()

    def update_loop_results(self, loop_name: str, loop_results: List[Dict[str, Any]]):
        """Update for_each loop results array.

        Stores the array of iteration results as steps.<LoopName> per specs.

        Args:
            loop_name: Name of the for_each loop
            loop_results: Array of iteration result dictionaries
        """
        with self._state_mutation():
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
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            self.state.for_each[loop_name] = state
            self._write_state()

    def update_repeat_until_state(
        self,
        loop_name: str,
        progress: Dict[str, Any],
        frame_result: Optional[Dict[str, Any]] = None,
    ):
        """Persist repeat_until bookkeeping and optional loop-frame snapshot."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            self.state.repeat_until[loop_name] = progress
            if frame_result is not None:
                self.state.steps[loop_name] = frame_result
            self._write_state()

    def update_dataflow_state(
        self,
        artifact_versions: Dict[str, List[Dict[str, Any]]],
        artifact_consumes: Dict[str, Dict[str, int]],
        private_artifact_versions: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        private_artifact_consumes: Optional[Dict[str, Dict[str, int]]] = None,
    ):
        """Update v1.2 artifact dataflow state."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            self.state.artifact_versions = artifact_versions
            self.state.artifact_consumes = artifact_consumes
            if private_artifact_versions is not None:
                self.state.private_artifact_versions = private_artifact_versions
            if private_artifact_consumes is not None:
                self.state.private_artifact_consumes = private_artifact_consumes
            self._write_state()

    def finalize_step_with_dataflow(
        self,
        step_name: str,
        result: StepResult,
        *,
        artifact_versions: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        artifact_consumes: Optional[Dict[str, Dict[str, int]]] = None,
        private_artifact_versions: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        private_artifact_consumes: Optional[Dict[str, Dict[str, int]]] = None,
        expected_step_id: Optional[str] = None,
        expected_visit_count: Optional[int] = None,
    ):
        """Persist one step result plus dataflow changes in a single state write."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            self.state.steps[step_name] = result
            if artifact_versions is not None:
                self.state.artifact_versions = artifact_versions
            if artifact_consumes is not None:
                self.state.artifact_consumes = artifact_consumes
            if private_artifact_versions is not None:
                self.state.private_artifact_versions = private_artifact_versions
            if private_artifact_consumes is not None:
                self.state.private_artifact_consumes = private_artifact_consumes

            current_step = self.state.current_step
            if isinstance(current_step, dict) and current_step.get("name") == step_name:
                if expected_step_id is not None and current_step.get("step_id") != expected_step_id:
                    self._write_state()
                    return
                if (
                    expected_visit_count is not None
                    and current_step.get("visit_count") != expected_visit_count
                ):
                    self._write_state()
                    return
                self.state.current_step = None

            self._write_state()

    def update_call_frame(self, frame_id: str, frame_state: Dict[str, Any]):
        """Persist one call-frame snapshot in state.json."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            self.state.call_frames[frame_id] = frame_state
            self._write_state()

    def update_workflow_outputs(self, workflow_outputs: Dict[str, Any]):
        """Persist workflow-boundary exported outputs."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            self.state.workflow_outputs = workflow_outputs
            self._write_state()

    def update_bound_inputs(self, bound_inputs: Dict[str, Any]) -> None:
        """Persist workflow-boundary inputs in one coordinated transaction."""

        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")
            self.state.bound_inputs = dict(bound_inputs)
            self._write_state()

    def update_finalization_state(self, finalization: Dict[str, Any]):
        """Persist workflow finalization bookkeeping."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            self.state.finalization = finalization
            self._write_state()

    def update_run_error(self, error: Optional[Dict[str, Any]]):
        """Persist or clear run-level error metadata."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            self.state.error = error
            self._write_state()

    def update_control_flow_counters(
        self,
        transition_count: int,
        step_visits: Dict[str, int],
    ):
        """Persist cycle-guard counters in state.json."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            self.state.transition_count = transition_count
            self.state.step_visits = step_visits
            self._write_state()

    def update_status(self, status: StateStatus):
        """Update overall run status.

        Args:
            status: New run status
        """
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            self.state.status = status
            self._write_state()

    def start_step(
        self,
        step_name: str,
        step_index: int,
        step_type: str,
        step_id: Optional[str] = None,
        visit_count: Optional[int] = None,
    ):
        """Persist currently running step metadata."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            now = datetime.now(timezone.utc).isoformat()
            self.state.current_step = {
                "name": step_name,
                "index": step_index,
                "type": step_type,
                "status": "running",
                "started_at": now,
                "last_heartbeat_at": now,
            }
            if step_id:
                self.state.current_step["step_id"] = step_id
            if visit_count is not None:
                self.state.current_step["visit_count"] = visit_count
            self._write_state()

    def heartbeat_step(self, step_name: Optional[str] = None):
        """Refresh heartbeat timestamp for current running step."""
        with self._state_mutation():
            if not self.state or self.state.current_step is None:
                return

            if step_name and self.state.current_step.get("name") != step_name:
                return

            self.state.current_step["last_heartbeat_at"] = datetime.now(timezone.utc).isoformat()
            self._write_state()

    def clear_current_step(
        self,
        step_name: Optional[str] = None,
        *,
        preserve_managed_recovery: bool = False,
    ):
        """Clear current running step metadata."""
        with self._state_mutation():
            if not self.state or self.state.current_step is None:
                return

            if step_name and self.state.current_step.get("name") != step_name:
                return
            managed_jobs = self.state.current_step.get("managed_jobs")
            if (
                preserve_managed_recovery
                and isinstance(managed_jobs, dict)
                and managed_jobs.get("phase") == "recovery"
            ):
                return

            self.state.current_step = None
            self._write_state()

    def mark_current_step_recovery(
        self,
        *,
        step_name: str,
        step_index: Optional[int],
        step_type: str,
        step_id: Optional[str],
        visit_count: Optional[int],
        managed_jobs: Dict[str, Any],
    ) -> None:
        """Persist a resumable recovery phase for an otherwise settled step."""
        with self._state_mutation():
            if not self.state:
                raise RuntimeError("State not initialized")

            now = datetime.now(timezone.utc).isoformat()
            current_step: Dict[str, Any] = {
                "name": step_name,
                "index": step_index,
                "type": step_type,
                "status": "running",
                "started_at": now,
                "last_heartbeat_at": now,
                "managed_jobs": managed_jobs,
            }
            if step_id:
                current_step["step_id"] = step_id
            if visit_count is not None:
                current_step["visit_count"] = visit_count
            self.state.current_step = current_step
            self._write_state()

    def get_step_result(self, step_name: str) -> Optional[StepResult]:
        """Get result of a specific step.

        Args:
            step_name: Name of the step

        Returns:
            Step result or None if not found
        """
        with self._lock:
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

        current_checksum = self.calculate_checksum(workflow_path)
        return current_checksum == self.state.workflow_checksum

    def attempt_repair(self) -> bool:
        """Attempt to repair state from latest valid backup.

        Returns:
            True if repair successful, False otherwise
        """
        with self._state_mutation(
            reload_from_disk=False,
            force_process_lock=True,
        ):
            repair_barrier = (
                self.run_root / self.PROVIDER_ATTEMPT_REPAIR_BARRIER_NAME
            )
            legacy_aggregate_lock = (
                self.run_root
                / "workflow_lisp"
                / "prompt_dependencies"
                / ".aggregate.lock"
            )
            if repair_barrier.exists() or legacy_aggregate_lock.exists():
                return False

            backup_pattern = "state.json.step_*.bak"
            backups = sorted(self.state_file.parent.glob(backup_pattern), reverse=True)
            valid_backups: list[tuple[Path, RunState]] = []
            for backup in backups:
                try:
                    with open(backup, 'r') as f:
                        data = json.load(f)
                    state = RunState.from_dict(data)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
                if state.provider_attempt_allocations:
                    return False
                valid_backups.append((backup, state))

            if valid_backups:
                backup, state = valid_backups[0]
                if self._durable_state_writes:
                    durable_atomic_write(self.state_file, backup.read_bytes())
                else:
                    shutil.copy2(backup, self.state_file)
                self.state = state
                return True

        return False
