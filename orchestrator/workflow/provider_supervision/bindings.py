"""Immutable coordinator/member boundary records for provider supervision."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping

from orchestrator._common.canonical import compact_ascii_json_dumps
from orchestrator._common.io_atomic import atomic_write_bytes
from orchestrator._common.safe_tree import resolve_path_preserving_fd
from orchestrator._common.validation import nonempty_string as _nonempty
from ...contracts.output_contract import (
    OutputContractError,
    validate_output_bundle,
    validate_variant_output_bundle,
)
from ...providers.control import ProviderExecutionControl
from ...providers.types import (
    InputMode,
    ProviderInvocation,
    ProviderParams,
    ProviderSessionMode,
    ProviderSessionRequest,
)
from ...deps.content_snapshot import snapshot_content_dependencies
from ..prompt_dependency_evidence import (
    build_success_evidence,
    publish_evidence_file,
)
from ..provider_attempts import (
    ProviderAttemptScope,
    derive_provider_attempt_member_turn_scope,
    resolve_aggregate_run_owner,
)
from ..pure_expr import evaluate_pure_expr
from .contracts import (
    bind_member_result_contract as _bind_member_result_contract,
)

if TYPE_CHECKING:
    from ..executable_ir import (
        ExecutableContract,
        ProviderSupervisionMemberConfig,
        ProviderSupervisionStepConfig,
    )


_TURN_ROLES = frozenset(
    {"worker_fresh", "worker_resume", "supervisor_directive"}
)
PROVIDER_SUPERVISION_OBSERVATION_INJECTION_SCHEMA_VERSION = (
    "provider_supervision_observation_injection.v1"
)
PROVIDER_SUPERVISION_OBSERVATION_INJECTION_KIND = (
    "live_provider_observation_target"
)

@dataclass(frozen=True)
class ProviderSupervisionTurnBinding:
    """One realized member-turn identity and its two owned result locations."""

    member_id: str
    turn_role: str
    runtime_step_id: str
    evidence_path: Path
    provisional_bundle_path: Path

    def __post_init__(self) -> None:
        _nonempty(self.member_id, "turn.member_id")
        if self.turn_role not in _TURN_ROLES:
            raise ValueError("turn.turn_role is not a provider-supervision turn")
        _nonempty(self.runtime_step_id, "turn.runtime_step_id")
        if not isinstance(self.evidence_path, Path):
            raise TypeError("turn.evidence_path must be a Path")
        if not isinstance(self.provisional_bundle_path, Path):
            raise TypeError("turn.provisional_bundle_path must be a Path")
        if self.evidence_path == self.provisional_bundle_path:
            raise ValueError("turn evidence and provisional paths must differ")


@dataclass(frozen=True)
class ProviderSupervisionObservationBinding:
    """One pre-opened pane target retained through directive arbitration."""

    member_id: str
    turn_role: str
    socket_path: Path
    target: str
    handle: Any

    def __post_init__(self) -> None:
        _nonempty(self.member_id, "observation.member_id")
        if self.turn_role not in _TURN_ROLES:
            raise ValueError(
                "observation.turn_role is not a provider-supervision turn"
            )
        if not isinstance(self.socket_path, Path) or not self.socket_path.is_absolute():
            raise ValueError(
                "observation.socket_path must be an absolute Path"
            )
        _nonempty(self.target, "observation.target")


@dataclass(frozen=True)
class ProviderSupervisionObservationInjection:
    """Process-local structural prompt injection for the observation edge."""

    observer_member_id: str
    observed_member_id: str
    socket_path: str
    target: str
    schema_version: str = (
        PROVIDER_SUPERVISION_OBSERVATION_INJECTION_SCHEMA_VERSION
    )
    kind: str = PROVIDER_SUPERVISION_OBSERVATION_INJECTION_KIND

    def __post_init__(self) -> None:
        _nonempty(self.observer_member_id, "injection.observer_member_id")
        _nonempty(self.observed_member_id, "injection.observed_member_id")
        if self.observer_member_id == self.observed_member_id:
            raise ValueError("injection observer and observed members must differ")
        if (
            not isinstance(self.socket_path, str)
            or not self.socket_path
            or not Path(self.socket_path).is_absolute()
        ):
            raise ValueError(
                "injection.socket_path must be an absolute path string"
            )
        _nonempty(self.target, "injection.target")
        if (
            self.schema_version
            != PROVIDER_SUPERVISION_OBSERVATION_INJECTION_SCHEMA_VERSION
        ):
            raise ValueError("injection.schema_version is unsupported")
        if self.kind != PROVIDER_SUPERVISION_OBSERVATION_INJECTION_KIND:
            raise ValueError("injection.kind is unsupported")

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "observer_member_id": self.observer_member_id,
            "observed_member_id": self.observed_member_id,
            "socket_path": self.socket_path,
            "target": self.target,
        }


@dataclass(frozen=True)
class ProviderSupervisionAttemptBinding:
    """One serially allocated attempt and immutable prompt-snapshot identity."""

    scope_key: str
    ordinal: int
    snapshot_key: str

    def __post_init__(self) -> None:
        _nonempty(self.scope_key, "attempt.scope_key")
        if (
            isinstance(self.ordinal, bool)
            or not isinstance(self.ordinal, int)
            or self.ordinal <= 0
        ):
            raise ValueError("attempt.ordinal must be a positive integer")
        _nonempty(self.snapshot_key, "attempt.snapshot_key")


@dataclass(frozen=True)
class _FrozenSessionRequest:
    mode: ProviderSessionMode
    session_id: str | None
    publish_artifact: str | None
    session_id_from: str | None

    @classmethod
    def from_request(
        cls,
        request: ProviderSessionRequest | None,
    ) -> "_FrozenSessionRequest | None":
        if request is None:
            return None
        if not isinstance(request, ProviderSessionRequest):
            raise TypeError("invocation.session_request must be ProviderSessionRequest")
        return cls(
            mode=request.mode,
            session_id=request.session_id,
            publish_artifact=request.publish_artifact,
            session_id_from=request.session_id_from,
        )

    def materialize(self) -> ProviderSessionRequest:
        return ProviderSessionRequest(
            mode=self.mode,
            session_id=self.session_id,
            publish_artifact=self.publish_artifact,
            session_id_from=self.session_id_from,
        )


def _freeze_value(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {
                key: _freeze_value(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_value(item) for item in value)
    return value


def _thaw_value(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return {
            key: _thaw_value(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    if isinstance(value, frozenset):
        return {_thaw_value(item) for item in value}
    return value


@dataclass(frozen=True)
class ProviderSupervisionInvocationSnapshot:
    """Deeply detached immutable representation of a provider invocation."""

    command: tuple[str, ...]
    input_mode: InputMode
    prompt: str | None
    output_file: str | None
    env: MappingProxyType
    timeout_sec: int | None
    command_variant: str
    metadata_mode: str | None
    session_request: _FrozenSessionRequest | None
    terminate_process_tree: bool
    metadata: MappingProxyType
    turn_boundary_resume: bool
    provider_session_dir: str | None
    omp_transport_expectation: MappingProxyType | None

    @classmethod
    def from_invocation(
        cls,
        invocation: ProviderInvocation,
    ) -> "ProviderSupervisionInvocationSnapshot":
        if not isinstance(invocation, ProviderInvocation):
            raise TypeError("provider supervision requires ProviderInvocation")
        if any(not isinstance(token, str) for token in invocation.command):
            raise TypeError("invocation.command must contain only strings")
        frozen_env = _freeze_value(dict(invocation.env))
        frozen_metadata = _freeze_value(dict(invocation.metadata))
        assert isinstance(frozen_env, MappingProxyType)
        assert isinstance(frozen_metadata, MappingProxyType)
        frozen_expectation = None
        if invocation.omp_transport_expectation is not None:
            frozen = _freeze_value(
                dict(vars(invocation.omp_transport_expectation))
            )
            assert isinstance(frozen, MappingProxyType)
            frozen_expectation = frozen
        return cls(
            command=tuple(invocation.command),
            input_mode=invocation.input_mode,
            prompt=invocation.prompt,
            output_file=invocation.output_file,
            env=frozen_env,
            timeout_sec=invocation.timeout_sec,
            command_variant=invocation.command_variant,
            metadata_mode=invocation.metadata_mode,
            session_request=_FrozenSessionRequest.from_request(
                invocation.session_request
            ),
            terminate_process_tree=invocation.terminate_process_tree,
            metadata=frozen_metadata,
            turn_boundary_resume=invocation.turn_boundary_resume,
            provider_session_dir=invocation.provider_session_dir,
            omp_transport_expectation=frozen_expectation,
        )

    def materialize(self) -> ProviderInvocation:
        """Return a detached mutable invocation local to one member thread."""

        from orchestrator.providers.types import OmpTransportExpectation

        return ProviderInvocation(
            command=list(self.command),
            input_mode=self.input_mode,
            prompt=self.prompt,
            output_file=self.output_file,
            env=_thaw_value(self.env),
            timeout_sec=self.timeout_sec,
            command_variant=self.command_variant,
            metadata_mode=self.metadata_mode,
            session_request=(
                None
                if self.session_request is None
                else self.session_request.materialize()
            ),
            terminate_process_tree=self.terminate_process_tree,
            metadata=_thaw_value(self.metadata),
            turn_boundary_resume=self.turn_boundary_resume,
            provider_session_dir=self.provider_session_dir,
            omp_transport_expectation=(
                None
                if self.omp_transport_expectation is None
                else OmpTransportExpectation(
                    **_thaw_value(self.omp_transport_expectation)
                )
            ),
        )


@dataclass(frozen=True)
class ProviderSupervisionMemberRequest:
    """Frozen data handed to a member thread for low-level execution only."""

    member_id: str
    turn: ProviderSupervisionTurnBinding
    observation: ProviderSupervisionObservationBinding | None
    attempt: ProviderSupervisionAttemptBinding
    invocation: ProviderSupervisionInvocationSnapshot
    control: Any

    def __post_init__(self) -> None:
        _nonempty(self.member_id, "request.member_id")
        if self.member_id != self.turn.member_id:
            raise ValueError("request member contradicts its turn")
        if self.observation is None:
            if self.turn.turn_role != "worker_resume":
                raise ValueError(
                    "only worker_resume may omit its observation"
                )
        else:
            if self.member_id != self.observation.member_id:
                raise ValueError("request member contradicts its observation")
            if self.turn.turn_role != self.observation.turn_role:
                raise ValueError("request turn contradicts its observation")
        if not isinstance(
            self.invocation,
            ProviderSupervisionInvocationSnapshot,
        ):
            raise TypeError("request.invocation must be an immutable snapshot")
        if self.control is None:
            raise ValueError("request.control must be preallocated")
