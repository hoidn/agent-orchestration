"""Pure, read-only projection of persisted provider judgment authorities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.dashboard.compiled_workflow import (
    PersistedCompiledWorkflowError,
    load_persisted_compiled_workflow_surface,
    traverse_persisted_compiled_workflow_call_frames,
)
from orchestrator.workflow.persisted_surface import (
    PersistedSurfaceStep,
    PersistedWorkflowSurfaceNode,
    canonical_persisted_surface_bytes,
    persisted_surface_sha256,
)
from orchestrator.workflow.provider_attempts import ProviderAttemptScope
from orchestrator.workflow.surface_ast import SurfaceStepKind


JUDGMENT_RESULT_CONTRACT_MISMATCH = "judgment_result_contract_mismatch"
JUDGMENT_RESULT_COORDINATE_INVALID = "judgment_result_coordinate_invalid"


class JudgmentResultContractError(ValueError):
    """A persisted result contract or its runtime coordinate fails closed."""

    def __init__(self, code: str, message: str) -> None:
        if code not in {
            JUDGMENT_RESULT_CONTRACT_MISMATCH,
            JUDGMENT_RESULT_COORDINATE_INVALID,
        }:
            raise ValueError("judgment result contract error code is invalid")
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ResolvedPersistedResultContract:
    """One exact compiler-persisted result contract at a runtime coordinate."""

    workflow_name: str
    persisted_step_id: str
    contract_kind: str
    declared_shape: str
    contract: Mapping[str, Any]
    contract_sha256: str


def resolve_persisted_result_contract(
    *,
    workspace_root: Path,
    state: Mapping[str, Any],
    scope: ProviderAttemptScope,
) -> ResolvedPersistedResultContract:
    """Resolve one provider result contract without source or bundle access."""

    if not isinstance(state, Mapping) or not isinstance(
        scope, ProviderAttemptScope
    ):
        _coordinate_failure("result-contract scope or run state is invalid")
    workspace = _workspace(workspace_root)
    workflow_file = state.get("workflow_file")
    run_id = state.get("run_id")
    if (
        not isinstance(workflow_file, str)
        or not workflow_file
        or not isinstance(run_id, str)
        or not run_id
        or run_id != scope.run_id
    ):
        _coordinate_failure("result-contract root run identity is invalid")
    if _lexical_workspace_path(
        workspace,
        workflow_file,
    ) != _lexical_workspace_path(
        workspace,
        scope.resume_scope.root_workflow_file,
    ):
        _coordinate_failure(
            "result-contract scope root workflow does not match run state"
        )

    try:
        graph = load_persisted_compiled_workflow_surface(
            workspace_root=workspace,
            workflow_path=Path(workflow_file),
            state=state,
        )
    except PersistedCompiledWorkflowError as exc:
        if exc.reason == "coordinate":
            _coordinate_failure(str(exc))
        _contract_failure(str(exc))
    try:
        reached = traverse_persisted_compiled_workflow_call_frames(
            graph,
            state=state,
            call_frame_ids=scope.resume_scope.call_frame_ids,
        )
    except PersistedCompiledWorkflowError as exc:
        _coordinate_failure(str(exc))

    step = _resolve_coordinate_step(reached.node, reached.state, scope)
    contract_kind, declared_shape, contract = _result_contract(step)
    try:
        digest = persisted_surface_sha256(
            canonical_persisted_surface_bytes(
                {contract_kind: _thaw(contract)}
            )
        )
    except (TypeError, ValueError):
        _contract_failure("persisted result contract is not canonical JSON")
    return ResolvedPersistedResultContract(
        workflow_name=reached.node.workflow_name,
        persisted_step_id=step.step_id,
        contract_kind=contract_kind,
        declared_shape=declared_shape,
        contract=contract,
        contract_sha256=digest,
    )


def _resolve_coordinate_step(
    node: PersistedWorkflowSurfaceNode,
    reached_state: Mapping[str, Any],
    scope: ProviderAttemptScope,
) -> PersistedSurfaceStep:
    all_steps = tuple(_walk_node_steps(node))
    loop = scope.loop_iteration
    if loop is None:
        if scope.enclosing_step.step_id != scope.runtime_step_id:
            _coordinate_failure(
                "non-loop result coordinate has contradictory step identities"
            )
        matches = tuple(
            step
            for step in all_steps
            if step.step_id == scope.runtime_step_id
        )
        if len(matches) != 1:
            _coordinate_failure(
                "result coordinate does not select one persisted step"
            )
        selected = matches[0]
    else:
        if scope.enclosing_step.step_id != loop.loop_step_id:
            _coordinate_failure(
                "loop result coordinate has contradictory owner identities"
            )
        owners = tuple(
            step
            for step in all_steps
            if step.step_id == loop.loop_step_id
            and _step_loop_kind(step) == loop.kind
        )
        if len(owners) != 1:
            _coordinate_failure(
                "loop result coordinate does not select one persisted owner"
            )
        owner = owners[0]
        if scope.enclosing_step.step_name != owner.name:
            _coordinate_failure(
                "loop result coordinate has contradictory owner name"
            )
        descendants = tuple(_walk_loop_steps(owner, loop.kind))
        matches = tuple(
            step
            for step in descendants
            if _runtime_iteration_step_id(
                loop.loop_step_id,
                loop.iteration,
                step.step_id,
            )
            == scope.runtime_step_id
        )
        if len(matches) != 1:
            _coordinate_failure(
                "loop result coordinate does not select one persisted step"
            )
        selected = matches[0]

    if selected.kind is not SurfaceStepKind.PROVIDER:
        _contract_failure(
            "persisted result coordinate does not select a provider contract"
        )
    if loop is None and scope.enclosing_step.step_name != selected.name:
        _coordinate_failure(
            "result coordinate has contradictory persisted step name"
        )
    visits = reached_state.get("step_visits")
    observed_visit = (
        visits.get(scope.enclosing_step.step_name)
        if isinstance(visits, Mapping)
        else None
    )
    if observed_visit != scope.enclosing_step.visit_count:
        _coordinate_failure(
            "result coordinate visit does not match persisted run state"
        )
    return selected


def _walk_node_steps(
    node: PersistedWorkflowSurfaceNode,
) -> Sequence[PersistedSurfaceStep]:
    return tuple(
        step
        for root in (*node.steps, *node.finalization_steps)
        for step in _walk_step(root)
    )


def _walk_step(step: PersistedSurfaceStep) -> Sequence[PersistedSurfaceStep]:
    nested: list[PersistedSurfaceStep] = [
        *step.for_each_steps,
        *step.then_steps,
        *step.else_steps,
    ]
    for case_steps in step.match_cases.values():
        nested.extend(case_steps)
    if step.repeat_until is not None:
        nested.extend(step.repeat_until.steps)
    return (
        step,
        *(
            descendant
            for child in nested
            for descendant in _walk_step(child)
        ),
    )


def _walk_loop_steps(
    owner: PersistedSurfaceStep,
    kind: str,
) -> Sequence[PersistedSurfaceStep]:
    if kind == "for_each":
        roots = owner.for_each_steps
    elif kind == "repeat_until" and owner.repeat_until is not None:
        roots = owner.repeat_until.steps
    else:
        _coordinate_failure("persisted loop owner kind is contradictory")
    return tuple(
        descendant
        for root in roots
        for descendant in _walk_step(root)
    )


def _step_loop_kind(step: PersistedSurfaceStep) -> str | None:
    has_for_each = bool(step.for_each_steps)
    has_repeat = step.repeat_until is not None
    if has_for_each == has_repeat:
        return None
    return "for_each" if has_for_each else "repeat_until"


def _runtime_iteration_step_id(
    loop_step_id: str,
    iteration: int,
    persisted_step_id: str,
) -> str:
    prefix = f"{loop_step_id}."
    if not persisted_step_id.startswith(prefix):
        _coordinate_failure(
            "persisted loop descendant is outside its owner identity"
        )
    suffix = persisted_step_id[len(prefix) :]
    if not suffix:
        _coordinate_failure("persisted loop descendant identity is invalid")
    return f"{loop_step_id}#{iteration}.{suffix}"


def _result_contract(
    step: PersistedSurfaceStep,
) -> tuple[str, str, Mapping[str, Any]]:
    output_bundle = step.common.output_bundle
    variant_output = step.common.variant_output
    output_present = output_bundle is not None
    variant_present = variant_output is not None
    if output_present == variant_present:
        _contract_failure(
            "persisted provider step must contain exactly one result contract"
        )
    if variant_present:
        if not isinstance(variant_output, Mapping):
            _contract_failure("persisted variant result contract is malformed")
        _validate_variant_contract(variant_output)
        return "variant_output", "union_value", variant_output
    if not isinstance(output_bundle, Mapping):
        _contract_failure("persisted output result contract is malformed")
    declared_shape = _validate_output_contract(output_bundle)
    return "output_bundle", declared_shape, output_bundle


def _validate_output_contract(contract: Mapping[str, Any]) -> str:
    path = contract.get("path")
    fields = contract.get("fields")
    if (
        not isinstance(path, str)
        or not path
        or not isinstance(fields, tuple)
        or not fields
    ):
        _contract_failure("persisted output result contract is malformed")
    names: set[str] = set()
    pointers: set[str] = set()
    root_fields = 0
    for field in fields:
        name, pointer = _validated_contract_field(field)
        if name in names or pointer in pointers:
            _contract_failure(
                "persisted output result fields are ambiguous"
            )
        names.add(name)
        pointers.add(pointer)
        root_fields += pointer == ""
    if root_fields:
        if (
            len(fields) != 1
            or fields[0].get("name") != "__result__"
            or fields[0].get("json_pointer") != ""
        ):
            _contract_failure(
                "persisted output result contract mixes root and record fields"
            )
        return "root_value"
    return "record_value"


def _validate_variant_contract(contract: Mapping[str, Any]) -> None:
    path = contract.get("path")
    discriminant = contract.get("discriminant")
    shared_fields = contract.get("shared_fields")
    variants = contract.get("variants")
    if (
        not isinstance(path, str)
        or not path
        or not isinstance(discriminant, Mapping)
        or not isinstance(shared_fields, tuple)
        or not isinstance(variants, Mapping)
        or not variants
        or not all(
            isinstance(name, str)
            and name
            and isinstance(payload, Mapping)
            for name, payload in variants.items()
        )
    ):
        _contract_failure("persisted variant result contract is malformed")
    discriminant_name = discriminant.get("name")
    discriminant_pointer = discriminant.get("json_pointer")
    allowed = discriminant.get("allowed")
    if (
        not isinstance(discriminant_name, str)
        or not discriminant_name
        or not isinstance(discriminant_pointer, str)
        or not discriminant_pointer.startswith("/")
        or discriminant.get("type") != "enum"
        or not isinstance(allowed, tuple)
        or not allowed
        or any(not isinstance(item, str) or not item for item in allowed)
        or len(set(allowed)) != len(allowed)
        or tuple(variants) != allowed
    ):
        _contract_failure(
            "persisted variant discriminant contract is malformed"
        )
    names = {discriminant_name}
    pointers = {discriminant_pointer}
    for field in shared_fields:
        name, pointer = _validated_contract_field(field)
        if name in names or pointer in pointers:
            _contract_failure(
                "persisted variant result fields are ambiguous"
            )
        names.add(name)
        pointers.add(pointer)
    for payload in variants.values():
        fields = payload.get("fields")
        if not isinstance(fields, tuple):
            _contract_failure(
                "persisted variant result fields are malformed"
            )
        variant_names = set(names)
        variant_pointers = set(pointers)
        for field in fields:
            name, pointer = _validated_contract_field(field)
            if name in variant_names or pointer in variant_pointers:
                _contract_failure(
                    "persisted variant result fields are ambiguous"
                )
            variant_names.add(name)
            variant_pointers.add(pointer)


def _validated_contract_field(
    field: Any,
) -> tuple[str, str]:
    if not isinstance(field, Mapping):
        _contract_failure("persisted result field is malformed")
    name = field.get("name")
    pointer = field.get("json_pointer")
    value_type = field.get("type")
    if (
        not isinstance(name, str)
        or not name
        or not isinstance(pointer, str)
        or (pointer and not pointer.startswith("/"))
        or not isinstance(value_type, str)
        or not value_type
    ):
        _contract_failure("persisted result field is malformed")
    return name, pointer


def _workspace(path: Path) -> Path:
    try:
        workspace = Path(path).resolve(strict=True)
    except (OSError, RuntimeError, TypeError):
        _coordinate_failure("judgment workspace root is missing or invalid")
    if not workspace.is_dir():
        _coordinate_failure("judgment workspace root is not a directory")
    return workspace


def _lexical_workspace_path(workspace: Path, raw: str) -> Path:
    candidate = Path(raw)
    candidate = candidate if candidate.is_absolute() else workspace / candidate
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(workspace)
    except (OSError, RuntimeError, ValueError):
        _coordinate_failure(
            "result-contract workflow path is outside the workspace"
        )
    return resolved


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _contract_failure(message: str) -> None:
    raise JudgmentResultContractError(
        JUDGMENT_RESULT_CONTRACT_MISMATCH,
        message,
    )


def _coordinate_failure(message: str) -> None:
    raise JudgmentResultContractError(
        JUDGMENT_RESULT_COORDINATE_INVALID,
        message,
    )
