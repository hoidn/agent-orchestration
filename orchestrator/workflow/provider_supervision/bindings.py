"""Immutable coordinator/member boundary records for provider supervision."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping

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

if TYPE_CHECKING:
    from ..executable_ir import (
        ExecutableContract,
        ProviderSupervisionMemberConfig,
        ProviderSupervisionStepConfig,
    )


_INITIAL_TURN_ROLES = frozenset(
    {"worker_fresh", "supervisor_directive"}
)
PROVIDER_SUPERVISION_OBSERVATION_INJECTION_SCHEMA_VERSION = (
    "provider_supervision_observation_injection.v1"
)
PROVIDER_SUPERVISION_OBSERVATION_INJECTION_KIND = (
    "live_provider_observation_target"
)


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


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
        if self.turn_role not in _INITIAL_TURN_ROLES:
            raise ValueError("turn.turn_role is not an initial v1 turn")
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
        if self.turn_role not in _INITIAL_TURN_ROLES:
            raise ValueError("observation.turn_role is not an initial v1 turn")
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
        )

    def materialize(self) -> ProviderInvocation:
        """Return a detached mutable invocation local to one member thread."""

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
        )


@dataclass(frozen=True)
class ProviderSupervisionMemberRequest:
    """Frozen data handed to a member thread for low-level execution only."""

    member_id: str
    turn: ProviderSupervisionTurnBinding
    observation: ProviderSupervisionObservationBinding
    attempt: ProviderSupervisionAttemptBinding
    invocation: ProviderSupervisionInvocationSnapshot
    control: Any

    def __post_init__(self) -> None:
        _nonempty(self.member_id, "request.member_id")
        if self.member_id != self.turn.member_id:
            raise ValueError("request member contradicts its turn")
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


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    return value


def _descriptor(contract: ExecutableContract) -> dict[str, Any]:
    definition = contract.definition
    if not isinstance(definition, Mapping):
        raise ValueError("executable result contract definition is invalid")
    descriptor = definition.get("type")
    if not isinstance(descriptor, Mapping):
        raise ValueError("executable result contract type descriptor is missing")
    return _thaw(descriptor)


def _pointer(path: tuple[str, ...]) -> str:
    return "/" + "/".join(
        part.replace("~", "~0").replace("/", "~1")
        for part in path
    )


def _leaf_contract(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    kind = descriptor.get("kind")
    if kind == "primitive":
        names = {
            "String": "string",
            "Int": "integer",
            "Float": "float",
            "Bool": "bool",
        }
        name = descriptor.get("name")
        if name not in names:
            raise ValueError(f"unsupported primitive result type: {name!r}")
        return {"type": names[name]}
    if kind == "enum":
        allowed = descriptor.get("allowed")
        if (
            not isinstance(allowed, list)
            or not allowed
            or any(not isinstance(item, str) for item in allowed)
        ):
            raise ValueError("enum result descriptor is invalid")
        return {"type": "enum", "allowed": list(allowed)}
    if kind == "path":
        under = descriptor.get("under")
        must_exist = descriptor.get("must_exist_target")
        if not isinstance(under, str) or not isinstance(must_exist, bool):
            raise ValueError(
                "path result descriptor must preserve under and "
                "must_exist_target refinement metadata"
            )
        return {
            "type": "relpath",
            "under": under,
            "must_exist_target": must_exist,
        }
    if kind == "optional":
        return {
            "type": "optional",
            "item": _leaf_contract(_mapping(descriptor.get("item"), "optional.item")),
        }
    if kind == "list":
        return {
            "type": "list",
            "items": _leaf_contract(_mapping(descriptor.get("item"), "list.item")),
        }
    if kind == "map":
        key = _mapping(descriptor.get("key"), "map.key")
        if key.get("kind") != "primitive" or key.get("name") != "String":
            raise ValueError("transportable map result keys must be String")
        return {
            "type": "map",
            "keys": {"type": "string"},
            "values": _leaf_contract(
                _mapping(descriptor.get("value"), "map.value")
            ),
        }
    raise ValueError(f"unsupported leaf result descriptor kind: {kind!r}")


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a mapping")
    return value


def _fields(
    fields: Any,
    *,
    prefix: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    if not isinstance(fields, list):
        raise ValueError("result descriptor fields must be a list")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for field in fields:
        node = _mapping(field, "result descriptor field")
        name = node.get("name")
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("result descriptor field names must be unique")
        seen.add(name)
        descriptor = _mapping(node.get("type"), f"field {name}.type")
        path = (*prefix, name)
        if descriptor.get("kind") == "record":
            output.extend(_fields(descriptor.get("fields"), prefix=path))
            continue
        output.append(
            {
                "name": "__".join(path),
                "json_pointer": _pointer(path),
                **_leaf_contract(descriptor),
            }
        )
    return output


def _bundle_contract(
    contract: ExecutableContract,
    *,
    path: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Derive ordinary validator and prompt contracts for one typed result."""

    descriptor = _descriptor(contract)
    kind = descriptor.get("kind")
    if kind == "record":
        payload = {
            "path": path,
            "fields": _fields(descriptor.get("fields")),
        }
        return "output_bundle", payload, descriptor
    if kind == "union":
        variants = descriptor.get("variants")
        if not isinstance(variants, list) or not variants:
            raise ValueError("union result descriptor variants are invalid")
        variant_fields: dict[str, list[dict[str, Any]]] = {}
        for variant in variants:
            node = _mapping(variant, "union variant")
            name = node.get("name")
            if (
                not isinstance(name, str)
                or not name
                or name in variant_fields
            ):
                raise ValueError("union variant names must be unique")
            variant_fields[name] = _fields(node.get("fields"))

        common_keys: set[str] | None = None
        specs_by_variant: dict[str, dict[str, dict[str, Any]]] = {}
        for name, fields in variant_fields.items():
            indexed = {
                json.dumps(
                    field,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ): field
                for field in fields
            }
            specs_by_variant[name] = indexed
            common_keys = (
                set(indexed)
                if common_keys is None
                else common_keys & set(indexed)
            )
        shared_keys = common_keys or set()
        first_variant = next(iter(specs_by_variant.values()))
        shared_fields = [
            first_variant[key]
            for key in sorted(shared_keys)
        ]
        payload = {
            "path": path,
            "discriminant": {
                "name": "variant",
                "json_pointer": "/variant",
                "type": "enum",
                "allowed": list(variant_fields),
            },
            "shared_fields": shared_fields,
            "variants": {
                name: {
                    "fields": [
                        field
                        for key, field in indexed.items()
                        if key not in shared_keys
                    ]
                }
                for name, indexed in specs_by_variant.items()
            },
        }
        return "variant_output", payload, descriptor
    payload = {
        "path": path,
        "fields": [
            {
                "name": "__result__",
                "json_pointer": "",
                **_leaf_contract(descriptor),
            }
        ],
    }
    return "output_bundle", payload, descriptor


def _extract_path(value: Any, path: tuple[str, ...]) -> Any:
    current = value
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            raise ValueError(f"settlement value is missing field {'.'.join(path)}")
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
        raise ValueError("structured settlement value must be a mapping")

    def flatten(
        fields: Any,
        prefix: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        if not isinstance(fields, list):
            raise ValueError("settlement descriptor fields are invalid")
        projected: dict[str, Any] = {}
        for field in fields:
            node = _mapping(field, "settlement field")
            name = node.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError("settlement field name is invalid")
            path = (*prefix, name)
            field_type = _mapping(node.get("type"), "settlement field type")
            if field_type.get("kind") == "record":
                projected.update(flatten(field_type.get("fields"), path))
            else:
                projected["__".join(path)] = _extract_path(value, path)
        return projected

    if kind == "record":
        return flatten(descriptor.get("fields"))
    variant = value.get("variant")
    if not isinstance(variant, str):
        raise ValueError("union settlement value is missing variant")
    variants = descriptor.get("variants")
    if not isinstance(variants, list):
        raise ValueError("union settlement descriptor is invalid")
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
        raise ValueError("union settlement variant is invalid")
    return {"variant": variant, **flatten(selected.get("fields"))}


def _provider_member_step(
    member: ProviderSupervisionMemberConfig,
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


class WorkflowProviderSupervisionBindings:
    """Concrete serial bridge from the coordinator to ``WorkflowExecutor``."""

    def __init__(
        self,
        executor: Any,
        *,
        step: Any,
        state: dict[str, Any],
        config: ProviderSupervisionStepConfig,
        step_name: str,
        runtime_step_id: str,
    ) -> None:
        self.executor = executor
        self.step = step
        self.state = state
        self.config = config
        self.step_name = step_name
        self.runtime_step_id = runtime_step_id
        self._scopes: dict[str, ProviderAttemptScope] = {}
        self._members: dict[str, ProviderSupervisionMemberConfig] = {
            "worker_fresh": config.worker,
            "supervisor_directive": config.supervisor,
        }
        self._steps: dict[str, dict[str, Any]] = {}
        self._contracts: dict[
            str,
            tuple[str, dict[str, Any], dict[str, Any]],
        ] = {}
        self._prompt_injections: dict[str, dict[str, str] | None] = {}
        self._pending_prompts: dict[str, dict[str, Any]] = {}
        self._final_prompts: dict[str, str] = {}

    def assert_current_step(
        self,
        *,
        step_name: str,
        node_id: str,
        visit_count: int,
    ) -> None:
        current = self.executor.state_manager.load().current_step
        expected = {
            "name": step_name,
            "step_id": node_id,
            "visit_count": visit_count,
            "type": "provider_supervision",
            "status": "running",
        }
        if not isinstance(current, Mapping) or any(
            current.get(key) != value
            for key, value in expected.items()
        ):
            raise ValueError(
                "provider supervision current_step was not published first"
            )

    def derive_turn_bindings(
        self,
        *,
        config: ProviderSupervisionStepConfig,
        visit_count: int,
    ) -> dict[str, ProviderSupervisionTurnBinding]:
        if config is not self.config:
            raise ValueError("provider supervision config changed")
        base_scope = self.executor._provider_attempt_scope(
            step_name=self.step_name,
            runtime_step_id=self.runtime_step_id,
        )
        path_specs = {
            "worker_fresh": config.paths.worker_fresh,
            "supervisor_directive": config.paths.supervisor_directive,
        }
        turns: dict[str, ProviderSupervisionTurnBinding] = {}
        run_root = Path(self.executor.state_manager.run_root).resolve()
        for role, path_spec in path_specs.items():
            scope = derive_provider_attempt_member_turn_scope(
                base_scope,
                member_id=path_spec.member_id,
                turn_ordinal=0,
            )
            self._scopes[role] = scope
            evidence_path = self._realize_path(
                run_root,
                path_spec.evidence_relpath,
                visit_count,
            )
            bundle_path = self._realize_path(
                run_root,
                path_spec.provisional_bundle_relpath,
                visit_count,
            )
            for path in (evidence_path, bundle_path):
                if path.exists():
                    raise ValueError(
                        "provider supervision provisional path preimage exists"
                    )
                path.parent.mkdir(parents=True, exist_ok=True)
            turns[role] = ProviderSupervisionTurnBinding(
                member_id=path_spec.member_id,
                turn_role=role,
                runtime_step_id=scope.runtime_step_id,
                evidence_path=evidence_path,
                provisional_bundle_path=bundle_path,
            )
        return turns

    @staticmethod
    def _realize_path(
        run_root: Path,
        template: str,
        visit_count: int,
    ) -> Path:
        if template.count("{visit}") != 1:
            raise ValueError("provider supervision path template is invalid")
        relative = Path(template.replace("{visit}", str(visit_count)))
        candidate = (run_root / relative).resolve()
        if candidate == run_root or run_root not in candidate.parents:
            raise ValueError("provider supervision path escapes run root")
        return candidate

    def open_observation(
        self,
        turn: ProviderSupervisionTurnBinding,
    ) -> ProviderSupervisionObservationBinding:
        manager = self.executor.provider_observation_manager
        if manager is None:
            manager = self.executor._require_provider_supervision_observation_manager()
        invocation_id = manager.next_invocation_id()
        handle = manager.open_observation(
            invocation_id=invocation_id,
            member_id=turn.member_id,
            turn_id=turn.turn_role,
        )
        return ProviderSupervisionObservationBinding(
            member_id=turn.member_id,
            turn_role=turn.turn_role,
            socket_path=Path(handle.socket_path),
            target=handle.target,
            handle=handle,
        )

    def compose_prompt(
        self,
        *,
        member: ProviderSupervisionMemberConfig,
        turn: ProviderSupervisionTurnBinding,
        observation_injection: ProviderSupervisionObservationInjection | None,
    ) -> str:
        role = turn.turn_role
        expected_member = self._members.get(role)
        if expected_member is not member:
            raise ValueError("provider supervision member binding changed")
        member_step = _provider_member_step(
            member,
            runtime_step_id=turn.runtime_step_id,
        )
        prompt_contract_path = str(turn.provisional_bundle_path)
        contract_kind, prompt_contract, descriptor = _bundle_contract(
            member.result_contract,
            path=prompt_contract_path,
        )
        contract_step = dict(member_step)
        contract_step[contract_kind] = prompt_contract
        compiler_contract = (
            member.provider_config.compiler_prompt_dependency_contract
        )
        if compiler_contract is None:
            raise ValueError(
                "provider supervision member has no compiler "
                "prompt-dependency contract"
            )
        depends_on = member_step.get("depends_on")
        if not isinstance(depends_on, Mapping):
            raise ValueError(
                "provider supervision prompt dependencies are missing"
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
                "provider supervision prompt dependencies are invalid"
            )
        snapshot = snapshot_content_dependencies(
            self.executor.workspace,
            resolution.classified_rows,
        )
        inject = depends_on.get("inject")
        if not isinstance(inject, Mapping):
            raise ValueError(
                "provider supervision prompt dependency injection is invalid"
            )
        instruction = inject.get(
            "instruction",
            self.executor.dependency_injector._get_default_instruction(
                "content",
                bool(depends_on.get("required")),
            ),
        )
        if not isinstance(instruction, str):
            raise ValueError(
                "provider supervision prompt dependency instruction is invalid"
            )
        instruction_source = (
            "authored"
            if compiler_contract.instruction_utf8_sha256_or_null is not None
            else (
                "default_required"
                if compiler_contract.required_binding_refs
                else "default_optional"
            )
        )
        base_step = dict(member_step)
        base_step.pop("depends_on", None)
        base_step["inject_consumes"] = False
        base_step["inject_output_contract"] = False
        base_contract_step = dict(contract_step)
        base_contract_step["inject_consumes"] = False
        base_contract_step["inject_output_contract"] = False
        prompt, error, _debug = self.executor._compose_provider_attempt_for_step(
            base_step,
            context,
            self.state,
            output_contract_step=base_contract_step,
            runtime_step_id=turn.runtime_step_id,
        )
        if error is not None or prompt is None:
            raise ValueError(
                f"provider supervision prompt composition failed: {error!r}"
            )
        injection_payload: dict[str, str] | None = None
        if observation_injection is not None:
            injection_payload = observation_injection.to_dict()
        self._steps[role] = member_step
        self._contracts[role] = (
            contract_kind,
            prompt_contract,
            descriptor,
        )
        self._prompt_injections[role] = injection_payload
        self._pending_prompts[role] = {
            "base_prompt": prompt,
            "compiler_contract": compiler_contract,
            "snapshot": snapshot,
            "instruction": instruction,
            "instruction_source": instruction_source,
            "position": compiler_contract.position.value,
            "contract_step": contract_step,
            "context": context,
            "observation_injection": injection_payload,
        }
        return prompt

    def allocate_attempt(
        self,
        *,
        turn: ProviderSupervisionTurnBinding,
        prompt: str,
    ) -> ProviderSupervisionAttemptBinding:
        scope = self._scopes.get(turn.turn_role)
        if scope is None or scope.runtime_step_id != turn.runtime_step_id:
            raise ValueError("provider supervision attempt scope is missing")
        pending = self._pending_prompts.get(turn.turn_role)
        if pending is None or pending["base_prompt"] != prompt:
            raise ValueError(
                "provider supervision pending prompt binding is missing"
            )
        ordinal = self.executor.state_manager.allocate_provider_attempt(scope)
        owner = resolve_aggregate_run_owner(self.executor.state_manager)
        composer = self.executor.prompt_composer

        def compose_final_prompt(rendered: Any) -> bytes:
            composed = composer.apply_rendered_content_dependency(
                pending["base_prompt"],
                rendered,
                position=pending["position"],
            )
            resolved_consumes = self.state.get("_resolved_consumes", {})
            composed = composer.apply_consumes_prompt_injection(
                self._steps[turn.turn_role],
                composed,
                resolved_consumes=(
                    resolved_consumes
                    if isinstance(resolved_consumes, dict)
                    else {}
                ),
                step_name=turn.member_id,
                consume_identity=turn.runtime_step_id,
                uses_qualified_identities=(
                    self.executor._uses_qualified_identities()
                ),
            )
            injection_payload = pending["observation_injection"]
            if injection_payload is not None:
                composed = (
                    composed
                    + "\n\n"
                    + "Runtime live-provider observation target:\n"
                    + json.dumps(
                        injection_payload,
                        ensure_ascii=True,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
            composed = composer.apply_output_contract_prompt_suffix(
                pending["contract_step"],
                composed,
            )
            return composed.encode("utf-8", errors="strict")

        success = build_success_evidence(
            run_state=owner.root_manager.state,
            scope=scope,
            ordinal=ordinal,
            compiler_contract=pending["compiler_contract"],
            snapshot=pending["snapshot"],
            instruction=pending["instruction"],
            instruction_source=pending["instruction_source"],
            compose_final_prompt=compose_final_prompt,
        )
        publication = publish_evidence_file(
            self.executor.state_manager,
            scope,
            ordinal,
            success.evidence,
        )
        self.executor._atomic_write_bytes(
            turn.evidence_path,
            publication.payload,
        )
        final_prompt = success.final_prompt.decode("utf-8", errors="strict")
        self._final_prompts[turn.turn_role] = final_prompt
        return ProviderSupervisionAttemptBinding(
            scope_key=scope.key,
            ordinal=ordinal,
            snapshot_key=publication.file_sha256,
        )

    def prepare_invocation(
        self,
        *,
        member: ProviderSupervisionMemberConfig,
        turn: ProviderSupervisionTurnBinding,
        prompt: str,
    ) -> ProviderInvocation:
        step = self._steps.get(turn.turn_role)
        if step is None:
            raise ValueError("provider supervision member step is missing")
        final_prompt = self._final_prompts.get(turn.turn_role)
        pending = self._pending_prompts.get(turn.turn_role)
        if (
            final_prompt is None
            or pending is None
            or pending["base_prompt"] != prompt
        ):
            raise ValueError(
                "provider supervision immutable prompt snapshot is missing"
            )
        context_value = self.state.get("context")
        context = (
            {"context": context_value}
            if isinstance(context_value, dict) and context_value
            else {}
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
                f"provider supervision provider resolution failed: "
                f"{provider_error!r}"
            )
        env = dict(step.get("env") or {})
        env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] = str(
            turn.provisional_bundle_path
        )
        session_request = (
            ProviderSessionRequest(mode=ProviderSessionMode.FRESH)
            if turn.turn_role == "worker_fresh"
            else None
        )
        invocation, error = self.executor.provider_executor.prepare_invocation(
            provider_name=provider_name,
            params=ProviderParams(
                params=step.get("provider_params", {}),
                input_file=step.get("input_file"),
                output_file=step.get("output_file"),
            ),
            context=provider_context,
            prompt_content=final_prompt,
            session_request=session_request,
            env=env,
            secrets=step.get("secrets"),
            timeout_sec=member.timeout_sec,
            provider_call_policy=step.get("provider_call_policy"),
        )
        if error is not None or invocation is None:
            raise ValueError(
                f"provider supervision invocation preparation failed: {error!r}"
            )
        metadata = dict(invocation.metadata)
        metadata["provider_supervision"] = {
            "member_id": turn.member_id,
            "turn_role": turn.turn_role,
            "attempt_scope_key": self._scopes[turn.turn_role].key,
            "observation_injection": self._prompt_injections.get(
                turn.turn_role
            ),
        }
        invocation.metadata = metadata
        return invocation

    def create_control(
        self,
        turn: ProviderSupervisionTurnBinding,
    ) -> ProviderExecutionControl:
        if turn.turn_role not in self._scopes:
            raise ValueError("provider supervision control turn is unknown")
        return ProviderExecutionControl()

    def execute_member(
        self,
        request: ProviderSupervisionMemberRequest,
    ) -> Any:
        return self.executor.provider_executor.execute(
            request.invocation.materialize(),
            cwd=self.executor.workspace,
            stream_output=(
                self.executor.debug
                or self.executor.stream_output
            ),
            control=request.control,
            observation_handle=request.observation.handle,
        )

    def observation_is_healthy(
        self,
        observation: ProviderSupervisionObservationBinding,
    ) -> bool:
        return bool(observation.handle.check_health())

    def validate_member_bundle(
        self,
        request: ProviderSupervisionMemberRequest,
    ) -> Any:
        contract = self._contracts.get(request.turn.turn_role)
        if contract is None:
            raise ValueError("provider supervision member contract is missing")
        contract_kind, prompt_contract, descriptor = contract
        validation_contract = dict(prompt_contract)
        validation_contract["path"] = (
            request.turn.provisional_bundle_path.relative_to(
                Path(self.executor.state_manager.run_root).resolve()
            ).as_posix()
        )
        run_root = Path(self.executor.state_manager.run_root)
        try:
            if contract_kind == "variant_output":
                validate_variant_output_bundle(
                    validation_contract,
                    workspace=run_root,
                )
            else:
                artifacts = validate_output_bundle(
                    validation_contract,
                    workspace=run_root,
                )
                if descriptor.get("kind") not in {"record", "union"}:
                    return artifacts["__result__"]
        except OutputContractError as exc:
            raise ValueError(
                "provider supervision member bundle is invalid"
            ) from exc
        try:
            return json.loads(
                request.turn.provisional_bundle_path.read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                "provider supervision validated bundle could not be read"
            ) from exc

    def evaluate_settlement(
        self,
        *,
        config: ProviderSupervisionStepConfig,
        resolved_bindings: dict[str, Any],
    ) -> Any:
        return evaluate_pure_expr(
            config.settlement_payload,
            resolved_bindings=resolved_bindings,
        )

    def validate_settlement(
        self,
        *,
        config: ProviderSupervisionStepConfig,
        value: Any,
    ) -> Any:
        # ``evaluate_pure_expr`` validates and coerces its result against the
        # declared result_type. Executable-IR validation already proves that
        # descriptor equals this settlement contract.
        del config
        return value

    def finalize_settlement(
        self,
        *,
        config: ProviderSupervisionStepConfig,
        selected_request: ProviderSupervisionMemberRequest,
        directive_request: ProviderSupervisionMemberRequest,
        selected_value: Any,
        directive_value: Any,
        settlement_value: Any,
    ) -> dict[str, Any]:
        result_descriptor = _descriptor(config.settlement_result_contract)
        result = {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "artifacts": _project_artifacts(
                result_descriptor,
                settlement_value,
            ),
            "debug": {
                "provider_supervision": {
                    "selected_attempt": {
                        "scope_key": selected_request.attempt.scope_key,
                        "ordinal": selected_request.attempt.ordinal,
                    },
                    "directive_attempt": {
                        "scope_key": directive_request.attempt.scope_key,
                        "ordinal": directive_request.attempt.ordinal,
                    },
                }
            },
        }
        return self.executor._finalize_provider_supervision_settlement(
            self.step,
            self.state,
            step_name=self.step_name,
            result=result,
        )

    def close_observation(
        self,
        observation: ProviderSupervisionObservationBinding,
    ) -> None:
        observation.handle.finalize()

    def failure_result(
        self,
        *,
        code: str,
        message: str,
    ) -> dict[str, Any]:
        result = {
            "status": "failed",
            "exit_code": 2,
            "duration_ms": 0,
            "error": {
                "type": code,
                "message": message,
            },
        }
        return self.executor._finalize_provider_supervision_settlement(
            self.step,
            self.state,
            step_name=self.step_name,
            result=result,
        )
