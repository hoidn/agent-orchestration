"""Immutable workflow bindings for the provider peer-group coordinator."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Protocol, runtime_checkable
from uuid import uuid4

from ...contracts.output_contract import (
    OutputContractError,
    validate_output_bundle,
    validate_variant_output_bundle,
)
from ...deps.content_snapshot import snapshot_content_dependencies
from ...providers.interactive_terminal import (
    CloseOfferReceipt,
    FailedCleanupProof,
    InteractiveMemberHandle,
    InteractiveMemberInvocation,
    InteractiveTerminalStartOutcome,
    InteractiveTerminalTurnQueueAdapter,
    NaturalShutdownProof,
    OfferReceipt,
)
from ...providers.types import (
    INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION,
)
from ..executable_ir import (
    ProviderPeerGroupMemberConfig,
    ProviderPeerGroupStepConfig,
)
from ..prompt_dependency_evidence import (
    build_success_evidence,
    publish_evidence_file,
)
from ..provider_attempts import (
    derive_provider_peer_group_member_scope,
    resolve_aggregate_run_owner,
)
from ..provider_supervision.contracts import (
    bind_member_result_contract,
)
from ..pure_expr import (
    canonical_json_for_pure_value,
    evaluate_pure_expr,
)
from .models import (
    MAX_PEER_MESSAGE_BYTES,
    FrozenPeerMemberResult,
    PeerEndpointIdentity,
    PeerGroupRuntimeBinding,
    PeerGroupTerminalEvidence,
    PeerGroupVisitIdentity,
    PeerAttemptIdentity,
    PeerMemberRuntimeBinding,
    PeerSenderBinding,
)
from .paths import (
    RealizedPeerGroupPaths,
    RealizedPeerMemberPaths,
    derive_provider_peer_group_paths,
    preflight_provider_peer_group_paths,
    preflight_provider_peer_group_visit_root,
    realize_provider_peer_group_paths,
)
from .protocol import (
    ACTIVE_PEER_BINDING_ENV,
    encode_active_peer_binding,
)


PEER_DELIVERY_FRAME_HEADER = "ORCHESTRATOR_PROVIDER_PEER_MESSAGE_V1"
_PORTABLE_UNIX_SOCKET_PATH_MAX_BYTES = 103
_PEER_ENDPOINT_PATH_UNAVAILABLE = (
    "provider_peer_group_endpoint_path_unavailable"
)


def _provider_peer_endpoint_socket_path(
    endpoint_instance_id: str,
    *,
    candidate_roots: tuple[Path, ...] | None = None,
) -> Path:
    """Choose a writable endpoint path within the portable AF_UNIX budget."""

    endpoint_id = _nonempty(
        endpoint_instance_id,
        field="endpoint_instance_id",
    )
    if candidate_roots is None:
        roots = [Path(tempfile.gettempdir())]
        if os.name == "posix" and Path("/tmp") not in roots:
            roots.append(Path("/tmp"))
        candidate_roots = tuple(roots)

    filename = f"orchestrator-peer-{endpoint_id}.sock"
    for root in candidate_roots:
        candidate = root / filename
        if (
            root.is_dir()
            and os.access(root, os.W_OK | os.X_OK)
            and len(os.fsencode(candidate))
            <= _PORTABLE_UNIX_SOCKET_PATH_MAX_BYTES
        ):
            return candidate
    raise ValueError(_PEER_ENDPOINT_PATH_UNAVAILABLE)


def _nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _header_value(value: object, *, field: str) -> str:
    text = _nonempty(value, field=field)
    if "\r" in text or "\n" in text:
        raise ValueError(f"{field} must fit on one header line")
    return text


def _sha256(value: object, *, field: str) -> str:
    text = _nonempty(value, field=field)
    hexadecimal = text[7:] if text.startswith("sha256:") else ""
    if (
        len(hexadecimal) != 64
        or any(character not in "0123456789abcdef" for character in hexadecimal)
    ):
        raise ValueError(f"{field} must be a canonical sha256 digest")
    return text


@dataclass(frozen=True, slots=True)
class PeerDeliveryFrame:
    """Compiler-owned framing around one otherwise-verbatim peer message."""

    message_id: str
    sender_member_id: str
    content: str

    def __post_init__(self) -> None:
        _header_value(self.message_id, field="delivery_frame.message_id")
        _header_value(
            self.sender_member_id,
            field="delivery_frame.sender_member_id",
        )
        content = _nonempty(self.content, field="delivery_frame.content")
        try:
            encoded = content.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(
                "delivery_frame.content must be valid UTF-8"
            ) from exc
        if len(encoded) > MAX_PEER_MESSAGE_BYTES:
            raise ValueError(
                "delivery_frame.content exceeds 65,536 bytes"
            )

    def render(self) -> str:
        return (
            f"{PEER_DELIVERY_FRAME_HEADER}\n"
            f"message_id: {self.message_id}\n"
            f"sender_member_id: {self.sender_member_id}\n\n"
            f"{self.content}"
        )

    def render_bytes(self) -> bytes:
        return self.render().encode("utf-8", errors="strict")

    @property
    def rendered_byte_count(self) -> int:
        return len(self.render_bytes())

    @property
    def rendered_sha256(self) -> str:
        return "sha256:" + hashlib.sha256(self.render_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class PeerMemberAllocation:
    """One fully allocated member without mutable adapter resources."""

    runtime: PeerMemberRuntimeBinding
    realized_paths: RealizedPeerMemberPaths
    sender: PeerSenderBinding
    prompt_snapshot_sha256: str
    invocation: InteractiveMemberInvocation

    def __post_init__(self) -> None:
        if not isinstance(self.runtime, PeerMemberRuntimeBinding):
            raise TypeError("member allocation runtime binding is invalid")
        if not isinstance(self.realized_paths, RealizedPeerMemberPaths):
            raise TypeError("member allocation realized paths are invalid")
        if not isinstance(self.sender, PeerSenderBinding):
            raise TypeError("member allocation sender binding is invalid")
        if not isinstance(self.invocation, InteractiveMemberInvocation):
            raise TypeError("member allocation invocation is invalid")
        _sha256(
            self.prompt_snapshot_sha256,
            field="member_allocation.prompt_snapshot_sha256",
        )

        attempt = self.runtime.attempt
        if self.sender.attempt != attempt:
            raise ValueError("member allocation sender attempt does not match")
        if (
            self.realized_paths.member_id != attempt.member_id
            or self.realized_paths.attempt_ordinal
            != attempt.attempt_ordinal
        ):
            raise ValueError("member allocation realized paths do not match")
        if (
            self.invocation.member_id != attempt.member_id
            or self.invocation.attempt_scope_key
            != attempt.attempt_scope_key
            or self.invocation.attempt_ordinal
            != attempt.attempt_ordinal
        ):
            raise ValueError("member allocation invocation does not match")


@dataclass(frozen=True, slots=True)
class PeerGroupAllocation:
    """Closed authored-order allocation for one exact group visit."""

    runtime: PeerGroupRuntimeBinding
    realized_paths: RealizedPeerGroupPaths
    endpoint: PeerEndpointIdentity
    endpoint_socket_path: Path
    members: tuple[PeerMemberAllocation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.runtime, PeerGroupRuntimeBinding):
            raise TypeError("group allocation runtime binding is invalid")
        if not isinstance(self.realized_paths, RealizedPeerGroupPaths):
            raise TypeError("group allocation realized paths are invalid")
        if not isinstance(self.endpoint, PeerEndpointIdentity):
            raise TypeError("group allocation endpoint identity is invalid")
        if (
            not isinstance(self.endpoint_socket_path, Path)
            or not self.endpoint_socket_path.is_absolute()
            or ".." in self.endpoint_socket_path.parts
        ):
            raise ValueError(
                "group allocation endpoint_socket_path must be absolute"
            )
        if not isinstance(self.members, tuple) or any(
            not isinstance(member, PeerMemberAllocation)
            for member in self.members
        ):
            raise TypeError(
                "group allocation members must be an authored-order tuple"
            )
        if self.endpoint.group_visit != self.runtime.visit:
            raise ValueError("group allocation endpoint visit does not match")
        if len(self.members) != len(self.runtime.members):
            raise ValueError("group allocation member count does not match")

        runtime_ids = tuple(
            member.attempt.member_id for member in self.runtime.members
        )
        expected_plan = derive_provider_peer_group_paths(
            node_id=self.runtime.visit.node_id,
            member_ids=runtime_ids,
        )
        if tuple(member.paths for member in self.runtime.members) != (
            expected_plan.members
        ):
            raise ValueError("group allocation runtime paths do not match")
        expected_paths = realize_provider_peer_group_paths(
            run_root=self.realized_paths.visit_root.parents[3],
            plan=expected_plan,
            visit_count=self.runtime.visit.visit_count,
            attempt_ordinals={
                member.attempt.member_id: member.attempt.attempt_ordinal
                for member in self.runtime.members
            },
        )
        if self.realized_paths != expected_paths:
            raise ValueError("group allocation realized path set does not match")
        if tuple(member.runtime for member in self.members) != (
            self.runtime.members
        ) or tuple(member.realized_paths for member in self.members) != (
            self.realized_paths.members
        ):
            raise ValueError(
                "group allocation members do not preserve authored order"
            )
        if any(
            member.sender.endpoint_instance_id
            != self.endpoint.endpoint_instance_id
            for member in self.members
        ):
            raise ValueError("group allocation sender endpoint does not match")
        for values, field in (
            (
                tuple(member.sender.opaque_binding for member in self.members),
                "sender bindings",
            ),
            (
                tuple(member.invocation.invocation_id for member in self.members),
                "invocation ids",
            ),
            (
                tuple(
                    member.runtime.attempt.attempt_scope_key
                    for member in self.members
                ),
                "attempt scope keys",
            ),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"group allocation {field} must be unique")
        if self.endpoint_socket_path in self.realized_paths.leaf_paths():
            raise ValueError("group allocation endpoint collides with a leaf")


@dataclass(frozen=True, slots=True)
class PeerGroupReportableIdentity:
    """A complete group/attempt identity before member preparation."""

    runtime: PeerGroupRuntimeBinding
    realized_paths: RealizedPeerGroupPaths
    endpoint: PeerEndpointIdentity
    endpoint_socket_path: Path

    def __post_init__(self) -> None:
        if (
            not isinstance(self.runtime, PeerGroupRuntimeBinding)
            or not isinstance(self.realized_paths, RealizedPeerGroupPaths)
            or not isinstance(self.endpoint, PeerEndpointIdentity)
            or not isinstance(self.endpoint_socket_path, Path)
            or not self.endpoint_socket_path.is_absolute()
        ):
            raise TypeError("reportable group identity is invalid")
        if self.endpoint.group_visit != self.runtime.visit:
            raise ValueError("reportable group endpoint visit does not match")
        runtime_attempts = tuple(
            member.attempt for member in self.runtime.members
        )
        realized_attempts = tuple(
            (member.member_id, member.attempt_ordinal)
            for member in self.realized_paths.members
        )
        if tuple(
            (attempt.member_id, attempt.attempt_ordinal)
            for attempt in runtime_attempts
        ) != realized_attempts:
            raise ValueError(
                "reportable group member identities do not match paths"
            )


@runtime_checkable
class PeerInteractiveAdapter(Protocol):
    """The exact provider-neutral interactive operations used by a group."""

    def start(
        self,
        invocation: InteractiveMemberInvocation,
        *,
        deadline: float,
    ) -> InteractiveTerminalStartOutcome: ...

    def offer(
        self,
        handle: InteractiveMemberHandle,
        literal_message: str,
        *,
        deadline: float,
    ) -> OfferReceipt: ...

    def offer_close(
        self,
        handle: InteractiveMemberHandle,
        *,
        deadline: float,
    ) -> CloseOfferReceipt: ...

    def join(
        self, handle: InteractiveMemberHandle, deadline: float
    ) -> NaturalShutdownProof: ...

    def abort(
        self, handle: InteractiveMemberHandle, deadline: float
    ) -> FailedCleanupProof: ...


class ProviderPeerGroupCoordinatorBindings(Protocol):
    """Workflow-owned operations invoked only by the serial coordinator."""

    def assert_current_step(self) -> None: ...

    def allocate_group(self) -> PeerGroupAllocation: ...

    def reportable_group_identity(
        self,
    ) -> PeerGroupReportableIdentity | None: ...

    def create_adapter(
        self, member: PeerMemberAllocation
    ) -> PeerInteractiveAdapter: ...

    def validate_member_bundle(
        self, member: PeerMemberAllocation
    ) -> FrozenPeerMemberResult: ...

    def evaluate_settlement(
        self, *, resolved_bindings: Mapping[str, Any]
    ) -> Any: ...

    def validate_settlement(self, *, value: Any) -> Any: ...

    def finalize_success(
        self,
        *,
        settlement_value: Any,
        evidence: PeerGroupTerminalEvidence,
    ) -> dict[str, Any]: ...

    def finalize_failure(
        self,
        *,
        evidence: PeerGroupTerminalEvidence,
    ) -> dict[str, Any]: ...


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    return value


def _member_step(
    member: ProviderPeerGroupMemberConfig,
    *,
    runtime_step_id: str,
) -> dict[str, Any]:
    provider = member.provider_config
    step: dict[str, Any] = {
        "name": member.member_id,
        "step_id": runtime_step_id,
        "provider": provider.provider,
        "timeout_sec": member.timeout_sec,
    }
    for source in (provider.common.__dict__, provider.__dict__):
        for key, value in source.items():
            if key == "common" or value is None:
                continue
            thawed = _thaw(value)
            if thawed in ({}, [], ()):
                continue
            step[key] = thawed
    step["timeout_sec"] = member.timeout_sec
    return step


def _contract_descriptor(contract: Any) -> dict[str, Any]:
    definition = getattr(contract, "definition", None)
    if (
        not isinstance(definition, Mapping)
        or set(definition) != {"type"}
        or not isinstance(definition.get("type"), Mapping)
    ):
        raise ValueError("provider peer group result contract is invalid")
    return _thaw(definition["type"])


def _typed_contract_value(
    descriptor: Mapping[str, Any],
    value: Any,
) -> Any:
    return evaluate_pure_expr(
        {
            "pure_expr_schema_version": 1,
            "result_type": descriptor,
            "bindings": {"value": {"type": descriptor}},
            "expr": {"kind": "binding", "name": "value"},
        },
        resolved_bindings={"value": value},
    )


def _extract_path(value: Any, path: tuple[str, ...]) -> Any:
    current = value
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            raise ValueError(
                "provider peer settlement value is missing "
                + ".".join(path)
            )
        current = current[part]
    return current


def _project_artifacts(
    descriptor: Mapping[str, Any],
    value: Any,
) -> dict[str, Any]:
    kind = descriptor.get("kind")
    if kind not in {"record", "union"}:
        return {"__result__": value}
    if not isinstance(value, Mapping):
        raise ValueError("provider peer settlement must be a mapping")

    def flatten(
        fields: Any,
        prefix: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        if not isinstance(fields, list):
            raise ValueError("provider peer settlement fields are invalid")
        projected: dict[str, Any] = {}
        for field in fields:
            if not isinstance(field, Mapping):
                raise ValueError(
                    "provider peer settlement field is invalid"
                )
            name = field.get("name")
            field_type = field.get("type")
            if (
                not isinstance(name, str)
                or not name
                or not isinstance(field_type, Mapping)
            ):
                raise ValueError(
                    "provider peer settlement field is invalid"
                )
            path = (*prefix, name)
            if field_type.get("kind") == "record":
                projected.update(flatten(field_type.get("fields"), path))
            else:
                projected["__".join(path)] = _extract_path(value, path)
        return projected

    if kind == "record":
        return flatten(descriptor.get("fields"))
    variant = value.get("variant")
    variants = descriptor.get("variants")
    if not isinstance(variant, str) or not isinstance(variants, list):
        raise ValueError("provider peer settlement union is invalid")
    selected = next(
        (
            candidate
            for candidate in variants
            if isinstance(candidate, Mapping)
            and candidate.get("name") == variant
        ),
        None,
    )
    if selected is None:
        raise ValueError("provider peer settlement variant is invalid")
    return {"variant": variant, **flatten(selected.get("fields"))}


class WorkflowProviderPeerGroupBindings:
    """Concrete workflow-owned bridge for one exact peer-group visit."""

    def __init__(
        self,
        executor: Any,
        *,
        step: Any,
        state: dict[str, Any],
        config: ProviderPeerGroupStepConfig,
        step_name: str,
        runtime_step_id: str,
        visit_count: int,
    ) -> None:
        if not isinstance(config, ProviderPeerGroupStepConfig):
            raise TypeError("provider peer group config must be typed")
        if (
            not isinstance(step_name, str)
            or not step_name
            or not isinstance(runtime_step_id, str)
            or not runtime_step_id
            or isinstance(visit_count, bool)
            or not isinstance(visit_count, int)
            or visit_count <= 0
        ):
            raise ValueError("provider peer group execution identity is invalid")
        member_ids = tuple(member.member_id for member in config.members)
        if (
            config.node_id != runtime_step_id
            or config.paths
            != derive_provider_peer_group_paths(
                node_id=config.node_id,
                member_ids=member_ids,
            )
            or tuple(
                member.member_id
                for member in config.source_ownership.members
            )
            != member_ids
        ):
            raise ValueError(
                "provider peer group executable ownership changed"
            )
        self.executor = executor
        self.step = step
        self.state = state
        self.config = config
        self.step_name = step_name
        self.runtime_step_id = runtime_step_id
        self.visit_count = visit_count
        self._members = {
            member.member_id: member for member in config.members
        }
        self._contracts: dict[
            str,
            tuple[str, dict[str, Any], dict[str, Any]],
        ] = {}
        self._allocation: PeerGroupAllocation | None = None
        self._reportable_identity: PeerGroupReportableIdentity | None = None
        self._terminal_evidence_written = False

    def assert_current_step(self) -> None:
        current = self.executor.state_manager.load().current_step
        expected = {
            "name": self.step_name,
            "step_id": self.runtime_step_id,
            "visit_count": self.visit_count,
            "type": "provider_peer_group",
            "status": "running",
        }
        if not isinstance(current, Mapping) or any(
            current.get(key) != value for key, value in expected.items()
        ):
            raise ValueError(
                "provider peer group current_step was not published first"
            )

    def allocate_group(self) -> PeerGroupAllocation:
        if self._allocation is not None:
            raise ValueError("provider peer group is already allocated")
        self.assert_current_step()
        run_root = Path(self.executor.state_manager.run_root)
        preflight_provider_peer_group_visit_root(
            run_root=run_root,
            plan=self.config.paths,
            visit_count=self.visit_count,
        )
        base_scope = self.executor._provider_attempt_scope(
            step_name=self.step_name,
            runtime_step_id=self.runtime_step_id,
        )
        scopes = tuple(
            derive_provider_peer_group_member_scope(
                base_scope,
                member_id=member.member_id,
            )
            for member in self.config.members
        )
        ordinals = tuple(
            self.executor.state_manager.allocate_provider_attempt(scope)
            for scope in scopes
        )
        attempts = tuple(
            PeerAttemptIdentity(
                member_id=member.member_id,
                attempt_scope_key=scope.key,
                attempt_ordinal=ordinal,
            )
            for member, scope, ordinal in zip(
                self.config.members,
                scopes,
                ordinals,
            )
        )
        runtime_members = tuple(
            PeerMemberRuntimeBinding(
                attempt=attempt,
                timeout_sec=member.timeout_sec,
                paths=path,
            )
            for member, attempt, path in zip(
                self.config.members,
                attempts,
                self.config.paths.members,
            )
        )
        visit = PeerGroupVisitIdentity(
            run_id=self.executor.state_manager.run_id,
            step_name=self.step_name,
            node_id=self.config.node_id,
            visit_count=self.visit_count,
        )
        runtime = PeerGroupRuntimeBinding(
            visit=visit,
            members=runtime_members,
            messaging_policy=self.config.messaging_policy,
            max_steers=self.config.max_steers,
        )
        realized = realize_provider_peer_group_paths(
            run_root=run_root,
            plan=self.config.paths,
            visit_count=self.visit_count,
            attempt_ordinals={
                attempt.member_id: attempt.attempt_ordinal
                for attempt in attempts
            },
        )
        preflight_provider_peer_group_paths(realized)
        endpoint = PeerEndpointIdentity(
            group_visit=visit,
            endpoint_instance_id=uuid4().hex,
        )
        endpoint_socket_path = _provider_peer_endpoint_socket_path(
            endpoint.endpoint_instance_id
        )
        self._reportable_identity = PeerGroupReportableIdentity(
            runtime=runtime,
            realized_paths=realized,
            endpoint=endpoint,
            endpoint_socket_path=endpoint_socket_path,
        )
        senders = tuple(
            PeerSenderBinding(
                opaque_binding=uuid4().hex,
                attempt=attempt,
                endpoint_instance_id=endpoint.endpoint_instance_id,
            )
            for attempt in attempts
        )
        allocations = tuple(
            self._allocate_member(
                member=member,
                runtime=runtime_member,
                realized=realized_member,
                sender=sender,
                endpoint_socket_path=endpoint_socket_path,
                member_ids=tuple(self._members),
                scope=scope,
            )
            for member, runtime_member, realized_member, sender, scope in zip(
                self.config.members,
                runtime_members,
                realized.members,
                senders,
                scopes,
            )
        )
        allocation = PeerGroupAllocation(
            runtime=runtime,
            realized_paths=realized,
            endpoint=endpoint,
            endpoint_socket_path=endpoint_socket_path,
            members=allocations,
        )
        self._allocation = allocation
        return allocation

    def reportable_group_identity(
        self,
    ) -> PeerGroupReportableIdentity | None:
        return self._reportable_identity

    def _allocate_member(
        self,
        *,
        member: ProviderPeerGroupMemberConfig,
        runtime: PeerMemberRuntimeBinding,
        realized: RealizedPeerMemberPaths,
        sender: PeerSenderBinding,
        endpoint_socket_path: Path,
        member_ids: tuple[str, ...],
        scope: Any,
    ) -> PeerMemberAllocation:
        step = _member_step(
            member,
            runtime_step_id=scope.runtime_step_id,
        )
        contract_kind, prompt_contract, descriptor = (
            bind_member_result_contract(
                member,  # type: ignore[arg-type]
                path=str(realized.provisional_bundle_path),
            )
        )
        step.pop("output_bundle", None)
        step.pop("variant_output", None)
        step[contract_kind] = prompt_contract
        contract_step = dict(step)
        compiler_contract = (
            member.provider_config.compiler_prompt_dependency_contract
        )
        if compiler_contract is None:
            raise ValueError(
                "provider peer member has no prompt-dependency contract"
            )
        depends_on = step.get("depends_on")
        if not isinstance(depends_on, Mapping):
            raise ValueError(
                "provider peer member prompt dependencies are missing"
            )
        context_value = self.state.get("context")
        context = (
            {"context": context_value}
            if isinstance(context_value, dict) and context_value
            else {}
        )
        variables = self.executor._build_substitution_variables(
            context,
            self.state,
        )
        resolution = self.executor._resolve_typed_content_dependencies(
            contract=compiler_contract,
            depends_on=depends_on,
            variables=variables,
        )
        if not resolution.is_valid:
            raise ValueError(
                "provider peer member prompt dependencies are invalid"
            )
        snapshot = snapshot_content_dependencies(
            self.executor.workspace,
            resolution.classified_rows,
        )
        inject = depends_on.get("inject")
        if not isinstance(inject, Mapping):
            raise ValueError(
                "provider peer member prompt injection is invalid"
            )
        has_rows = bool(
            compiler_contract.required_binding_refs
            or compiler_contract.optional_binding_refs
        )
        instruction = (
            inject.get(
                "instruction",
                self.executor.dependency_injector._get_default_instruction(
                    "content",
                    bool(depends_on.get("required")),
                ),
            )
            if has_rows
            else ""
        )
        if not isinstance(instruction, str):
            raise ValueError(
                "provider peer member prompt instruction is invalid"
            )
        instruction_source = (
            "authored"
            if compiler_contract.instruction_utf8_sha256_or_null is not None
            else (
                "default_required"
                if compiler_contract.required_binding_refs
                else (
                    "default_optional"
                    if compiler_contract.optional_binding_refs
                    else "none"
                )
            )
        )
        base_step = dict(step)
        base_step.pop("depends_on", None)
        base_step["inject_consumes"] = False
        base_step["inject_output_contract"] = False
        base_contract_step = dict(contract_step)
        base_contract_step["inject_consumes"] = False
        base_contract_step["inject_output_contract"] = False
        prompt, error, _debug = (
            self.executor._compose_provider_attempt_for_step(
                base_step,
                context,
                self.state,
                output_contract_step=base_contract_step,
                runtime_step_id=scope.runtime_step_id,
            )
        )
        if error is not None or prompt is None:
            raise ValueError(
                f"provider peer prompt composition failed: {error!r}"
            )
        protocol_injection = (
            "\n\nProvider peer-group runtime contract:\n"
            "Call `orchestrator peer-ready` before peer operations. "
            "Use `orchestrator peer-send <target-binding> <message>`, "
            "`orchestrator peer-ack <message-id>`, and "
            "`orchestrator peer-finish` cooperatively. "
            f"Your member binding is {member.member_id!r}. "
            "Available peer target bindings are "
            + ", ".join(
                repr(candidate)
                for candidate in member_ids
                if candidate != member.member_id
            )
            + "."
        )
        composer = self.executor.prompt_composer

        def compose_final_prompt(rendered: Any) -> bytes:
            composed = composer.apply_rendered_content_dependency(
                prompt,
                rendered,
                position=compiler_contract.position.value,
            )
            resolved_consumes = self.state.get("_resolved_consumes", {})
            composed = composer.apply_consumes_prompt_injection(
                step,
                composed,
                resolved_consumes=(
                    resolved_consumes
                    if isinstance(resolved_consumes, dict)
                    else {}
                ),
                step_name=member.member_id,
                consume_identity=scope.runtime_step_id,
                uses_qualified_identities=(
                    self.executor._uses_qualified_identities()
                ),
            )
            composed += protocol_injection
            composed = composer.apply_output_contract_prompt_suffix(
                contract_step,
                composed,
            )
            return composed.encode("utf-8", errors="strict")

        ordinal = runtime.attempt.attempt_ordinal
        owner = resolve_aggregate_run_owner(
            self.executor.state_manager
        )
        run_state = owner.root_manager.state
        if run_state is None:
            raise ValueError(
                "provider peer root state is unavailable"
            )
        success = build_success_evidence(
            run_state=run_state,
            scope=scope,
            ordinal=ordinal,
            compiler_contract=compiler_contract,
            snapshot=snapshot,
            instruction=instruction,
            instruction_source=instruction_source,
            compose_final_prompt=compose_final_prompt,
        )
        publication = publish_evidence_file(
            self.executor.state_manager,
            scope,
            ordinal,
            success.evidence,
        )
        self._write_no_replace(
            realized.prompt_dependencies_path,
            publication.payload,
        )
        final_prompt = success.final_prompt.decode(
            "utf-8",
            errors="strict",
        )
        provider_context = self.executor._create_provider_context(
            context,
            self.state,
        )
        provider_name, provider_error = (
            self.executor._resolve_provider_name_for_step(
                step,
                provider_context,
            )
        )
        if provider_error is not None or provider_name is None:
            raise ValueError(
                "provider peer provider resolution failed: "
                f"{provider_error!r}"
            )
        env = dict(step.get("env") or {})
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in env.items()
        ):
            raise ValueError("provider peer member env is invalid")
        env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] = str(
            realized.provisional_bundle_path
        )
        env[ACTIVE_PEER_BINDING_ENV] = encode_active_peer_binding(
            socket_path=endpoint_socket_path,
            sender_binding=sender.opaque_binding,
        )
        raw_params = step.get("provider_params") or {}
        if not isinstance(raw_params, Mapping):
            raise ValueError("provider peer member params are invalid")
        raw_secrets = step.get("secrets") or []
        if not isinstance(raw_secrets, list) or any(
            not isinstance(secret, str) for secret in raw_secrets
        ):
            raise ValueError("provider peer member secrets are invalid")
        invocation, invocation_error = (
            self.executor.provider_executor.prepare_interactive_invocation(
                provider_name=provider_name,
                params=dict(raw_params),
                context=provider_context,
                prompt_content=final_prompt,
                invocation_id=uuid4().hex,
                member_id=member.member_id,
                attempt_scope_key=scope.key,
                attempt_ordinal=ordinal,
                cwd=Path(self.executor.workspace),
                env=env,
                secrets=list(raw_secrets),
                provider_call_policy=step.get("provider_call_policy"),
            )
        )
        if invocation_error is not None or invocation is None:
            raise ValueError(
                "provider peer invocation preparation failed: "
                f"{invocation_error!r}"
            )
        self._contracts[member.member_id] = (
            contract_kind,
            prompt_contract,
            descriptor,
        )
        return PeerMemberAllocation(
            runtime=runtime,
            realized_paths=realized,
            sender=sender,
            prompt_snapshot_sha256=publication.file_sha256,
            invocation=invocation,
        )

    def create_adapter(
        self,
        member: PeerMemberAllocation,
    ) -> PeerInteractiveAdapter:
        schema = member.invocation.support.schema_version
        if (
            schema
            != self.config.interactive_session_schema_version
            or schema
            != INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION
        ):
            raise ValueError(
                "provider peer interactive adapter schema is unsupported"
            )
        reportable = self._reportable_identity
        if reportable is None:
            raise ValueError(
                "provider peer group reportable identity is missing"
            )
        return InteractiveTerminalTurnQueueAdapter(
            member.realized_paths.evidence_path.parent
            / "interactive-terminal",
            socket_root=reportable.endpoint_socket_path.parent,
        )

    def validate_member_bundle(
        self,
        member: PeerMemberAllocation,
    ) -> FrozenPeerMemberResult:
        allocation = self._allocation
        member_id = member.runtime.attempt.member_id
        if (
            allocation is None
            or member not in allocation.members
            or self._members.get(member_id) is None
        ):
            raise ValueError("provider peer member allocation changed")
        contract = self._contracts.get(member_id)
        if contract is None:
            raise ValueError("provider peer member contract is missing")
        contract_kind, prompt_contract, descriptor = contract
        path = member.realized_paths.provisional_bundle_path
        try:
            exact_bytes = path.read_bytes()
            document = json.loads(exact_bytes.decode("utf-8"))
            validation_contract = dict(prompt_contract)
            validation_contract["path"] = path.relative_to(
                Path(self.executor.state_manager.run_root).resolve()
            ).as_posix()
            if contract_kind == "variant_output":
                validate_variant_output_bundle(
                    validation_contract,
                    workspace=Path(
                        self.executor.state_manager.run_root
                    ),
                )
            else:
                validate_output_bundle(
                    validation_contract,
                    workspace=Path(
                        self.executor.state_manager.run_root
                    ),
                )
            if path.read_bytes() != exact_bytes:
                raise ValueError(
                    "provider peer member bundle changed during validation"
                )
            value = _typed_contract_value(descriptor, document)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            OutputContractError,
        ) as exc:
            raise ValueError(
                "provider peer member bundle is invalid"
            ) from exc
        return FrozenPeerMemberResult.create(
            attempt=member.runtime.attempt,
            exact_bundle_bytes=exact_bytes,
            value=value,
        )

    def evaluate_settlement(
        self,
        *,
        resolved_bindings: Mapping[str, Any],
    ) -> Any:
        if tuple(resolved_bindings) != tuple(self._members):
            raise ValueError(
                "provider peer settlement bindings changed authored order"
            )
        return evaluate_pure_expr(
            self.config.settlement_payload,
            resolved_bindings=resolved_bindings,
        )

    def validate_settlement(self, *, value: Any) -> Any:
        validated = _typed_contract_value(
            _contract_descriptor(
                self.config.settlement_result_contract
            ),
            value,
        )
        canonical_json_for_pure_value(validated)
        return validated

    def finalize_success(
        self,
        *,
        settlement_value: Any,
        evidence: PeerGroupTerminalEvidence,
    ) -> dict[str, Any]:
        evidence_debug = self._publish_terminal_evidence(
            evidence,
            expected_outcome="completed",
        )
        descriptor = _contract_descriptor(
            self.config.settlement_result_contract
        )
        result = {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "artifacts": _project_artifacts(
                descriptor,
                settlement_value,
            ),
            "debug": {"provider_peer_group": evidence_debug},
        }
        return self.executor._finalize_provider_peer_group_settlement(
            self.step,
            self.state,
            step_name=self.step_name,
            result=result,
        )

    def finalize_failure(
        self,
        *,
        evidence: PeerGroupTerminalEvidence,
    ) -> dict[str, Any]:
        evidence_debug = self._publish_terminal_evidence(
            evidence,
            expected_outcome="failed",
        )
        failure = dict(evidence.failure or {})
        result = {
            "status": "failed",
            "exit_code": 2,
            "duration_ms": 0,
            "error": {
                "type": failure.get(
                    "code",
                    "provider_peer_group_failed",
                ),
                "message": failure.get(
                    "message",
                    "provider peer group failed",
                ),
            },
            "debug": {"provider_peer_group": evidence_debug},
        }
        return self.executor._finalize_provider_peer_group_settlement(
            self.step,
            self.state,
            step_name=self.step_name,
            result=result,
        )

    def _publish_terminal_evidence(
        self,
        evidence: PeerGroupTerminalEvidence,
        *,
        expected_outcome: str,
    ) -> dict[str, str]:
        identity = self._allocation or self._reportable_identity
        if (
            identity is None
            or self._terminal_evidence_written
            or not isinstance(evidence, PeerGroupTerminalEvidence)
            or evidence.outcome != expected_outcome
            or evidence.group_visit != identity.runtime.visit
            or tuple(member.attempt for member in evidence.members)
            != tuple(
                member.attempt for member in identity.runtime.members
            )
        ):
            raise ValueError(
                "provider peer terminal evidence identity changed"
            )
        for member_evidence, member_paths in zip(
            evidence.members,
            identity.realized_paths.members,
            strict=True,
        ):
            member_payload = json.dumps(
                member_evidence.to_dict(),
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
            self._write_no_replace(
                member_paths.evidence_path,
                member_payload,
            )
        path = identity.realized_paths.terminal_evidence_path
        payload = json.dumps(
            evidence.to_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        self._write_no_replace(path, payload)
        self._terminal_evidence_written = True
        relative = path.relative_to(
            Path(self.executor.state_manager.run_root).resolve()
        ).as_posix()
        return {
            "terminal_evidence_path": relative,
            "terminal_evidence_schema_version": evidence.schema_version,
            "outcome": evidence.outcome,
        }

    def _write_no_replace(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as sentinel:
                sentinel.flush()
                os.fsync(sentinel.fileno())
        except FileExistsError as exc:
            raise ValueError(
                f"provider peer evidence preimage exists: {path}"
            ) from exc
        self.executor._atomic_write_bytes(path, payload)
        try:
            observed = path.read_bytes()
        except OSError as exc:
            raise ValueError(
                "provider peer evidence publication is unreadable"
            ) from exc
        if observed != payload:
            raise ValueError(
                "provider peer evidence changed during publication"
            )


__all__ = [
    "PEER_DELIVERY_FRAME_HEADER",
    "PeerDeliveryFrame",
    "PeerGroupAllocation",
    "PeerGroupReportableIdentity",
    "PeerInteractiveAdapter",
    "PeerMemberAllocation",
    "ProviderPeerGroupCoordinatorBindings",
    "WorkflowProviderPeerGroupBindings",
]
