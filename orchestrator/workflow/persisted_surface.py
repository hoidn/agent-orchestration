"""Versioned persisted typed workflow structure for read-only consumers.

This is deliberately narrower than :class:`LoadedWorkflowBundle`.  It records
the already validated surface structure needed by dashboards without claiming
to persist executable, semantic, or runtime-plan objects.  Adding fields is a
schema-evolution decision, not an invitation to recompile authored source.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.prompt_dependency_contract import (
    COMPILER_PROMPT_DEPENDENCY_CONTRACT_SCHEMA,
    CompilerPromptDependencyContract,
    PromptDependencyOriginKind,
    PromptDependencyPathInterpretation,
    PromptDependencyPosition,
    serialize_compiler_prompt_dependency_contract,
    validate_compiler_prompt_dependency_contract,
)
from orchestrator.workflow.prompt_fragment_contract import (
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2,
    CompilerPromptAttemptBindingPlan,
    CompilerPromptAttemptBindingPlanRow,
    CompilerPromptFragmentContract,
    CompilerPromptFragmentContractCarrier,
    CompilerPromptFragmentContractV2,
    CompilerPromptFragmentOutputPosition,
    CompilerPromptFragmentRenderedSlot,
    serialize_compiler_prompt_attempt_binding_plan,
    serialize_compiler_prompt_fragment_contract,
    validate_compiler_prompt_attempt_pair,
    validate_compiler_prompt_fragment_pair,
)
from orchestrator.workflow.surface_ast import SurfaceStep, SurfaceStepKind


PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA = "persisted_workflow_surface_graph.v1"
PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V2 = "persisted_workflow_surface_graph.v2"
PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V3 = "persisted_workflow_surface_graph.v3"
SUPPORTED_PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMAS = frozenset(
    {
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA,
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V2,
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V3,
    }
)
PERSISTED_WORKFLOW_SURFACE_FILENAME = "persisted_workflow_surface.json"


@dataclass(frozen=True)
class PersistedSurfaceCommon:
    publishes: tuple[Any, ...]
    consumes: tuple[Any, ...]
    expected_outputs: tuple[Any, ...]
    output_bundle: Any
    variant_output: Any


@dataclass(frozen=True)
class PersistedSurfaceRepeatUntil:
    max_iterations: int | None
    steps: tuple["PersistedSurfaceStep", ...]


@dataclass(frozen=True)
class PersistedSurfaceStep:
    name: str
    step_id: str
    kind: SurfaceStepKind
    authored_id: str | None
    call_alias: str | None
    input_file: Any
    asset_file: Any
    depends_on: Any
    asset_depends_on: tuple[Any, ...]
    adjudicated_provider: Any
    common: PersistedSurfaceCommon
    for_each_steps: tuple["PersistedSurfaceStep", ...]
    then_steps: tuple["PersistedSurfaceStep", ...]
    else_steps: tuple["PersistedSurfaceStep", ...]
    match_cases: Mapping[str, tuple["PersistedSurfaceStep", ...]]
    repeat_until: PersistedSurfaceRepeatUntil | None
    compiler_prompt_dependency_contract: CompilerPromptDependencyContract | None = None
    compiler_prompt_fragment_contract: CompilerPromptFragmentContractCarrier | None = None
    compiled_prompt_fragment_identity: str | None = None
    prompt_attempt_identity_version: str | None = None
    compiler_prompt_attempt_binding_plan: (
        CompilerPromptAttemptBindingPlan | None
    ) = None


@dataclass(frozen=True)
class PersistedWorkflowSurfaceNode:
    workflow_name: str
    version: str
    workflow_path: Path
    calls: Mapping[str, str]
    steps: tuple[PersistedSurfaceStep, ...]
    finalization_steps: tuple[PersistedSurfaceStep, ...]

    @property
    def name(self) -> str:
        return self.workflow_name


@dataclass(frozen=True)
class PersistedWorkflowSurfaceGraph:
    schema_version: str
    entry_workflow: str
    nodes: Mapping[str, PersistedWorkflowSurfaceNode]

    @property
    def entry_node(self) -> PersistedWorkflowSurfaceNode:
        return self.nodes[self.entry_workflow]

    def imported_node(
        self,
        node: PersistedWorkflowSurfaceNode,
        alias: str,
    ) -> PersistedWorkflowSurfaceNode | None:
        target = node.calls.get(alias)
        return self.nodes.get(target) if target is not None else None


def canonical_persisted_surface_bytes(value: Mapping[str, Any]) -> bytes:
    """Return the canonical wire bytes whose digest is persisted by the runtime."""

    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def persisted_surface_sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def serialize_persisted_workflow_surface_graph(
    entry_bundle: LoadedWorkflowBundle,
) -> dict[str, Any]:
    """Serialize the exact reachable validated surface/import graph.

    Nodes are keyed by canonical workflow name. Only imports selected by actual
    nested or finalization call steps are traversed. Repeated identical names
    deduplicate; a repeated name with a different canonical payload fails closed.
    """

    active: set[int] = set()
    completed_by_object: dict[int, str] = {}
    nodes: dict[str, dict[str, Any]] = {}

    def visit(bundle: LoadedWorkflowBundle) -> str:
        object_id = id(bundle)
        if object_id in active:
            raise ValueError("persisted workflow surface graph contains an import cycle")
        known_name = completed_by_object.get(object_id)
        if known_name is not None:
            return known_name

        active.add(object_id)
        try:
            used_aliases = _surface_call_aliases(bundle)
            calls: dict[str, str] = {}
            for alias in sorted(used_aliases):
                child = bundle.imports.get(alias)
                if child is None:
                    raise ValueError(
                        f"persisted workflow surface call alias {alias!r} has no imported bundle"
                    )
                calls[alias] = visit(child)
            node = {
                "workflow_name": bundle.surface.name,
                "version": bundle.surface.version,
                "workflow_path": str(bundle.surface.provenance.workflow_path),
                "calls": calls,
                "steps": [
                    _serialize_step(
                        step,
                        target_dsl_version=bundle.surface.version,
                    )
                    for step in bundle.surface.steps
                ],
                "finalization_steps": (
                    [
                        _serialize_step(
                            step,
                            target_dsl_version=bundle.surface.version,
                        )
                        for step in bundle.surface.finalization.steps
                    ]
                    if bundle.surface.finalization is not None
                    else []
                ),
            }
            workflow_name = node["workflow_name"]
            if not isinstance(workflow_name, str) or not workflow_name:
                raise ValueError("persisted workflow surface node must have a workflow name")
            existing = nodes.get(workflow_name)
            if existing is not None and existing != node:
                raise ValueError("persisted workflow surface workflow-name conflict")
            nodes[workflow_name] = node
            completed_by_object[object_id] = workflow_name
            return workflow_name
        finally:
            active.remove(object_id)

    resolved_entry_name = visit(entry_bundle)
    entry_workflow = entry_bundle.surface.name
    if not isinstance(entry_workflow, str) or not entry_workflow:
        raise ValueError("persisted workflow surface entry must have a workflow name")
    if resolved_entry_name != entry_workflow:
        raise ValueError("persisted workflow surface entry identity is inconsistent")
    schema_version = (
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V3
        if _serialized_nodes_contain_q3(nodes)
        else (
            PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V2
            if _serialized_nodes_contain_q2(nodes)
            else PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA
        )
    )
    return {
        "schema_version": schema_version,
        "entry_workflow": entry_workflow,
        "nodes": dict(sorted(nodes.items())),
    }


def decode_persisted_workflow_surface_graph(
    payload: bytes,
) -> PersistedWorkflowSurfaceGraph:
    """Strictly decode and validate one canonical persisted surface graph."""

    try:
        raw = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_closed_json_object,
            parse_constant=_reject_nonfinite_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"persisted workflow surface JSON is invalid: {exc}") from exc
    root = _mapping_with_keys(
        raw,
        {"schema_version", "entry_workflow", "nodes"},
        "persisted workflow surface graph",
    )
    schema_version = root["schema_version"]
    if schema_version not in SUPPORTED_PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMAS:
        raise ValueError("persisted workflow surface schema version is unsupported")
    entry_workflow = _non_empty_string(root["entry_workflow"], "entry workflow")
    raw_nodes = _mapping(root["nodes"], "persisted workflow surface nodes")
    if not raw_nodes:
        raise ValueError("persisted workflow surface graph has no nodes")

    nodes: dict[str, PersistedWorkflowSurfaceNode] = {}
    for raw_node_name, raw_node in raw_nodes.items():
        node_name = _non_empty_string(raw_node_name, "workflow node name")
        node_mapping = _mapping_with_keys(
            raw_node,
            {
                "workflow_name",
                "version",
                "workflow_path",
                "calls",
                "steps",
                "finalization_steps",
            },
            f"persisted workflow surface node {node_name}",
        )
        workflow_name = _non_empty_string(node_mapping["workflow_name"], "workflow name")
        if workflow_name != node_name:
            raise ValueError("persisted workflow surface node key/name mismatch")
        workflow_version = _non_empty_string(
            node_mapping["version"],
            "workflow version",
        )
        calls = _mapping(node_mapping["calls"], "workflow calls")
        parsed_calls = {
            _non_empty_string(alias, "call alias"): _non_empty_string(
                target, "call target"
            )
            for alias, target in calls.items()
        }
        raw_steps = _list(node_mapping["steps"], "workflow steps")
        nodes[node_name] = PersistedWorkflowSurfaceNode(
            workflow_name=workflow_name,
            version=workflow_version,
            workflow_path=Path(
                _non_empty_string(node_mapping["workflow_path"], "workflow path")
            ),
            calls=MappingProxyType(parsed_calls),
            steps=tuple(
                _decode_step(
                    step,
                    schema_version=schema_version,
                    target_dsl_version=workflow_version,
                )
                for step in raw_steps
            ),
            finalization_steps=tuple(
                _decode_step(
                    step,
                    schema_version=schema_version,
                    target_dsl_version=workflow_version,
                )
                for step in _list(
                    node_mapping["finalization_steps"], "workflow finalization steps"
                )
            ),
        )

    canonical = canonical_persisted_surface_bytes(root)
    if canonical != payload:
        raise ValueError("persisted workflow surface bytes are not canonical")
    if entry_workflow not in nodes:
        raise ValueError("persisted workflow surface entry node is missing")
    has_fragment_carriage = any(
        _persisted_steps_contain_q2((*node.steps, *node.finalization_steps))
        for node in nodes.values()
    )
    has_q3 = any(
        _persisted_steps_contain_q3((*node.steps, *node.finalization_steps))
        for node in nodes.values()
    )
    expected_schema = (
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V3
        if has_q3
        else (
            PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V2
            if has_fragment_carriage
            else PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA
        )
    )
    if schema_version != expected_schema:
        if (
            schema_version == PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V3
            or has_q3
        ):
            raise ValueError(
                "prompt_attempt_identity_version_mismatch: "
                "persisted graph schema does not match its Q3 carriage"
            )
        raise ValueError(
            "prompt_output_position_contract_mismatch: "
            "persisted graph schema does not match its v2 fragment carriage"
        )
    _validate_graph_reachability(entry_workflow, nodes)
    return PersistedWorkflowSurfaceGraph(
        schema_version=schema_version,
        entry_workflow=entry_workflow,
        nodes=MappingProxyType(nodes),
    )


def _serialize_step(
    step: SurfaceStep,
    *,
    target_dsl_version: str,
) -> dict[str, Any]:
    common = step.common
    if step.kind is not SurfaceStepKind.PROVIDER and (
        step.compiler_prompt_fragment_contract is not None
        or step.compiled_prompt_fragment_identity is not None
        or step.prompt_attempt_identity_version is not None
        or step.compiler_prompt_attempt_binding_plan is not None
    ):
        diagnostic = (
            "prompt_attempt_binding_plan_mismatch"
            if (
                step.prompt_attempt_identity_version is not None
                or step.compiler_prompt_attempt_binding_plan is not None
            )
            else "prompt_output_position_contract_mismatch"
        )
        raise ValueError(
            f"{diagnostic}: prompt carriage requires a provider step"
        )
    if (
        type(step.compiler_prompt_fragment_contract)
        is CompilerPromptFragmentContractV2
        and not _target_dsl_at_least(target_dsl_version, (2, 21))
    ):
        raise ValueError(
            "prompt_output_position_contract_mismatch: "
            "v2 fragment carriage requires target DSL 2.21"
        )
    validate_compiler_prompt_fragment_pair(
        step.compiler_prompt_fragment_contract,
        step.compiled_prompt_fragment_identity,
        common.expected_outputs,
    )
    validate_compiler_prompt_attempt_pair(
        step.prompt_attempt_identity_version,
        step.compiler_prompt_attempt_binding_plan,
        fragment_contract=step.compiler_prompt_fragment_contract,
        dependency_contract=step.compiler_prompt_dependency_contract,
        typed_prompt_inputs=step.typed_prompt_inputs,
        target_dsl_version=target_dsl_version,
    )
    payload = {
        "name": step.name,
        "step_id": step.step_id,
        "kind": step.kind.value,
        "authored_id": step.authored_id,
        "call_alias": step.call_alias,
        "input_file": _plain(step.input_file),
        "asset_file": _plain(step.asset_file),
        "depends_on": _plain(step.depends_on),
        "asset_depends_on": _plain(step.asset_depends_on),
        "adjudicated_provider": _plain(step.adjudicated_provider),
        "common": {
            "publishes": _plain(common.publishes),
            "consumes": _plain(common.consumes),
            "expected_outputs": _plain(common.expected_outputs),
            "output_bundle": _plain(common.output_bundle),
            "variant_output": _plain(common.variant_output),
        },
        "for_each_steps": [
            _serialize_step(
                child,
                target_dsl_version=target_dsl_version,
            )
            for child in step.for_each_steps
        ],
        "then_steps": (
            [
                _serialize_step(
                    child,
                    target_dsl_version=target_dsl_version,
                )
                for child in step.then_branch.steps
            ]
            if step.then_branch is not None
            else []
        ),
        "else_steps": (
            [
                _serialize_step(
                    child,
                    target_dsl_version=target_dsl_version,
                )
                for child in step.else_branch.steps
            ]
            if step.else_branch is not None
            else []
        ),
        "match_cases": {
            str(case_name): [
                _serialize_step(
                    child,
                    target_dsl_version=target_dsl_version,
                )
                for child in case.steps
            ]
            for case_name, case in sorted(step.match_cases.items())
        },
        "repeat_until": (
            {
                "max_iterations": step.repeat_until.max_iterations,
                "steps": [
                    _serialize_step(
                        child,
                        target_dsl_version=target_dsl_version,
                    )
                    for child in step.repeat_until.steps
                ],
            }
            if step.repeat_until is not None
            else None
        ),
    }
    if step.compiler_prompt_dependency_contract is not None:
        payload["compiler_prompt_dependency_contract"] = (
            serialize_compiler_prompt_dependency_contract(
                step.compiler_prompt_dependency_contract
            )
        )
    if step.prompt_attempt_identity_version is not None:
        assert step.compiler_prompt_fragment_contract is not None
        assert step.compiler_prompt_attempt_binding_plan is not None
        payload["compiler_prompt_fragment_contract"] = (
            serialize_compiler_prompt_fragment_contract(
                step.compiler_prompt_fragment_contract
            )
        )
        payload["compiled_prompt_fragment_identity"] = (
            step.compiled_prompt_fragment_identity
        )
        payload["prompt_attempt_identity_version"] = (
            step.prompt_attempt_identity_version
        )
        payload["compiler_prompt_attempt_binding_plan"] = (
            serialize_compiler_prompt_attempt_binding_plan(
                step.compiler_prompt_attempt_binding_plan
            )
        )
    elif type(step.compiler_prompt_fragment_contract) is CompilerPromptFragmentContractV2:
        payload["compiler_prompt_fragment_contract"] = (
            serialize_compiler_prompt_fragment_contract(
                step.compiler_prompt_fragment_contract
            )
        )
        payload["compiled_prompt_fragment_identity"] = (
            step.compiled_prompt_fragment_identity
        )
    return payload


def _serialized_nodes_contain_q2(nodes: Mapping[str, Any]) -> bool:
    def step_contains(step: Any) -> bool:
        if not isinstance(step, Mapping):
            return False
        if "compiler_prompt_fragment_contract" in step:
            return True
        nested_groups: list[Any] = [
            step.get("for_each_steps"),
            step.get("then_steps"),
            step.get("else_steps"),
        ]
        match_cases = step.get("match_cases")
        if isinstance(match_cases, Mapping):
            nested_groups.extend(match_cases.values())
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, Mapping):
            nested_groups.append(repeat_until.get("steps"))
        return any(
            isinstance(group, list)
            and any(step_contains(child) for child in group)
            for group in nested_groups
        )

    return any(
        isinstance(node, Mapping)
        and any(
            isinstance(steps, list)
            and any(step_contains(step) for step in steps)
            for steps in (
                node.get("steps"),
                node.get("finalization_steps"),
            )
        )
        for node in nodes.values()
    )


def _serialized_nodes_contain_q3(nodes: Mapping[str, Any]) -> bool:
    def step_contains(step: Any) -> bool:
        if not isinstance(step, Mapping):
            return False
        if (
            "prompt_attempt_identity_version" in step
            or "compiler_prompt_attempt_binding_plan" in step
        ):
            return True
        nested_groups: list[Any] = [
            step.get("for_each_steps"),
            step.get("then_steps"),
            step.get("else_steps"),
        ]
        match_cases = step.get("match_cases")
        if isinstance(match_cases, Mapping):
            nested_groups.extend(match_cases.values())
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, Mapping):
            nested_groups.append(repeat_until.get("steps"))
        return any(
            isinstance(group, list)
            and any(step_contains(child) for child in group)
            for group in nested_groups
        )

    return any(
        isinstance(node, Mapping)
        and any(
            isinstance(steps, list)
            and any(step_contains(step) for step in steps)
            for steps in (
                node.get("steps"),
                node.get("finalization_steps"),
            )
        )
        for node in nodes.values()
    )


def _persisted_steps_contain_q2(
    steps: tuple[PersistedSurfaceStep, ...],
) -> bool:
    for step in steps:
        if step.compiler_prompt_fragment_contract is not None:
            return True
        nested = (
            *step.for_each_steps,
            *step.then_steps,
            *step.else_steps,
            *(
                child
                for case_steps in step.match_cases.values()
                for child in case_steps
            ),
            *(
                ()
                if step.repeat_until is None
                else step.repeat_until.steps
            ),
        )
        if _persisted_steps_contain_q2(nested):
            return True
    return False


def _persisted_steps_contain_q3(
    steps: tuple[PersistedSurfaceStep, ...],
) -> bool:
    for step in steps:
        if (
            step.prompt_attempt_identity_version is not None
            or step.compiler_prompt_attempt_binding_plan is not None
        ):
            return True
        nested = (
            *step.for_each_steps,
            *step.then_steps,
            *step.else_steps,
            *(
                child
                for case_steps in step.match_cases.values()
                for child in case_steps
            ),
            *(
                ()
                if step.repeat_until is None
                else step.repeat_until.steps
            ),
        )
        if _persisted_steps_contain_q3(nested):
            return True
    return False


_STEP_KEYS = {
    "name",
    "step_id",
    "kind",
    "authored_id",
    "call_alias",
    "input_file",
    "asset_file",
    "depends_on",
    "asset_depends_on",
    "adjudicated_provider",
    "common",
    "for_each_steps",
    "then_steps",
    "else_steps",
    "match_cases",
    "repeat_until",
}
_OPTIONAL_STEP_KEYS = {"compiler_prompt_dependency_contract"}
_V2_OPTIONAL_STEP_KEYS = {
    *_OPTIONAL_STEP_KEYS,
    "compiler_prompt_fragment_contract",
    "compiled_prompt_fragment_identity",
}
_V3_OPTIONAL_STEP_KEYS = {
    *_V2_OPTIONAL_STEP_KEYS,
    "prompt_attempt_identity_version",
    "compiler_prompt_attempt_binding_plan",
}
_COMMON_KEYS = {
    "publishes",
    "consumes",
    "expected_outputs",
    "output_bundle",
    "variant_output",
}


def _target_dsl_at_least(
    value: str,
    minimum: tuple[int, ...],
) -> bool:
    try:
        parts = tuple(int(part) for part in value.split("."))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("persisted workflow target DSL version is invalid") from exc
    return parts >= minimum


def _optional_step_keys(
    *,
    schema_version: str,
    target_dsl_version: str,
    kind: SurfaceStepKind,
) -> set[str]:
    keys = set(_OPTIONAL_STEP_KEYS)
    if (
        kind is not SurfaceStepKind.PROVIDER
        or schema_version == PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA
    ):
        return keys
    if _target_dsl_at_least(target_dsl_version, (2, 21)):
        keys.update(_V2_OPTIONAL_STEP_KEYS)
    if (
        schema_version == PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V3
        and _target_dsl_at_least(target_dsl_version, (2, 22))
    ):
        keys.update(_V3_OPTIONAL_STEP_KEYS)
    return keys


def _decode_step(
    value: Any,
    *,
    schema_version: str,
    target_dsl_version: str,
) -> PersistedSurfaceStep:
    raw = _mapping(value, "persisted surface step")
    try:
        kind = SurfaceStepKind(_non_empty_string(raw["kind"], "step kind"))
    except (KeyError, ValueError) as exc:
        raise ValueError("persisted surface step kind is unsupported") from exc
    if (
        schema_version == PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA
        and {
            "compiler_prompt_fragment_contract",
            "compiled_prompt_fragment_identity",
        }
        & set(raw)
    ):
        raise ValueError(
            "prompt_output_position_contract_mismatch: "
            "persisted v1 graph cannot carry v2 fragment fields"
        )
    has_fragment_contract = "compiler_prompt_fragment_contract" in raw
    has_fragment_identity = "compiled_prompt_fragment_identity" in raw
    if has_fragment_contract != has_fragment_identity:
        raise ValueError(
            "prompt_output_position_contract_mismatch: "
            "persisted v2 fragment contract and identity must be paired"
        )
    has_q3_version = "prompt_attempt_identity_version" in raw
    has_q3_plan = "compiler_prompt_attempt_binding_plan" in raw
    if has_q3_version != has_q3_plan:
        if not has_q3_version:
            raise ValueError(
                "prompt_attempt_identity_version_missing: "
                "persisted Q3 version and binding plan must be paired"
            )
        raise ValueError(
            "prompt_attempt_binding_plan_missing: "
            "persisted Q3 version and binding plan must be paired"
        )
    optional_keys = _optional_step_keys(
        schema_version=schema_version,
        target_dsl_version=target_dsl_version,
        kind=kind,
    )
    if not _STEP_KEYS <= set(raw) or set(raw) - _STEP_KEYS - optional_keys:
        if (
            (has_q3_version or has_q3_plan)
            and not _target_dsl_at_least(target_dsl_version, (2, 22))
        ):
            raise ValueError(
                "prompt_attempt_identity_version_invalid: "
                "Q3 prompt carriage requires target DSL 2.22"
            )
        if (
            kind is not SurfaceStepKind.PROVIDER
            and {
                "prompt_attempt_identity_version",
                "compiler_prompt_attempt_binding_plan",
            }
            & set(raw)
        ):
            raise ValueError(
                "prompt_attempt_binding_plan_mismatch: "
                "Q3 prompt carriage requires a provider step"
            )
        raise ValueError("persisted surface step has unsupported or missing fields")
    common = _mapping_with_keys(raw["common"], _COMMON_KEYS, "step common metadata")
    match_cases = _mapping(raw["match_cases"], "step match cases")
    call_alias = _optional_string(raw["call_alias"], "call alias")
    for_each_steps = _list(raw["for_each_steps"], "for-each steps")
    then_steps = _list(raw["then_steps"], "then steps")
    else_steps = _list(raw["else_steps"], "else steps")
    repeat_raw = raw["repeat_until"]
    _validate_step_kind_shape(
        kind,
        call_alias=call_alias,
        for_each_steps=for_each_steps,
        then_steps=then_steps,
        else_steps=else_steps,
        match_cases=match_cases,
        repeat_raw=repeat_raw,
    )
    repeat_until = None
    if repeat_raw is not None:
        repeat = _mapping_with_keys(
            repeat_raw,
            {"max_iterations", "steps"},
            "repeat-until metadata",
        )
        max_iterations = repeat["max_iterations"]
        if max_iterations is not None and (
            not isinstance(max_iterations, int) or isinstance(max_iterations, bool)
        ):
            raise ValueError("repeat-until max_iterations must be an integer or null")
        repeat_until = PersistedSurfaceRepeatUntil(
            max_iterations=max_iterations,
            steps=tuple(
                _decode_step(
                    step,
                    schema_version=schema_version,
                    target_dsl_version=target_dsl_version,
                )
                for step in _list(repeat["steps"], "repeat-until steps")
            ),
        )
    decoded_fragment_identity = None
    if has_fragment_identity:
        try:
            decoded_fragment_identity = _non_empty_string(
                raw["compiled_prompt_fragment_identity"],
                "compiled prompt fragment identity",
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "prompt_output_position_contract_mismatch: "
                "persisted v2 fragment identity is invalid"
            ) from exc
    decoded_fragment_contract = None
    if has_fragment_contract:
        fragment_payload = _mapping(
            raw["compiler_prompt_fragment_contract"],
            "compiler prompt fragment contract",
        )
        fragment_schema = fragment_payload.get("schema_version")
        q3_fragment_carriage = (
            schema_version == PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V3
            and _target_dsl_at_least(target_dsl_version, (2, 22))
        )
        allowed_fragment_schemas = (
            {
                COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
                COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2,
            }
            if q3_fragment_carriage
            else {COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2}
        )
        if fragment_schema not in allowed_fragment_schemas:
            raise ValueError(
                "prompt_output_position_contract_mismatch: "
                "persisted fragment contract schema is not admitted here"
            )
        decoded_fragment_contract = (
            _decode_compiler_prompt_fragment_contract(fragment_payload)
        )
    decoded_q3_version = None
    if has_q3_version:
        try:
            decoded_q3_version = _non_empty_string(
                raw["prompt_attempt_identity_version"],
                "prompt attempt identity version",
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "prompt_attempt_identity_version_invalid: "
                "persisted Q3 identity version is invalid"
            ) from exc
    decoded_q3_plan = (
        _decode_compiler_prompt_attempt_binding_plan(
            raw["compiler_prompt_attempt_binding_plan"]
        )
        if has_q3_plan
        else None
    )
    decoded = PersistedSurfaceStep(
        name=_non_empty_string(raw["name"], "step name"),
        step_id=_non_empty_string(raw["step_id"], "step id"),
        kind=kind,
        authored_id=_optional_string(raw["authored_id"], "authored step id"),
        call_alias=call_alias,
        input_file=_freeze(raw["input_file"]),
        asset_file=_freeze(raw["asset_file"]),
        depends_on=_freeze(raw["depends_on"]),
        asset_depends_on=tuple(
            _freeze(item)
            for item in _list(raw["asset_depends_on"], "asset dependencies")
        ),
        adjudicated_provider=_freeze(raw["adjudicated_provider"]),
        common=PersistedSurfaceCommon(
            publishes=tuple(
                _freeze(item) for item in _list(common["publishes"], "publishes")
            ),
            consumes=tuple(
                _freeze(item) for item in _list(common["consumes"], "consumes")
            ),
            expected_outputs=tuple(
                _freeze(item)
                for item in _list(common["expected_outputs"], "expected outputs")
            ),
            output_bundle=_freeze(common["output_bundle"]),
            variant_output=_freeze(common["variant_output"]),
        ),
        for_each_steps=tuple(
            _decode_step(
                step,
                schema_version=schema_version,
                target_dsl_version=target_dsl_version,
            )
            for step in for_each_steps
        ),
        then_steps=tuple(
            _decode_step(
                step,
                schema_version=schema_version,
                target_dsl_version=target_dsl_version,
            )
            for step in then_steps
        ),
        else_steps=tuple(
            _decode_step(
                step,
                schema_version=schema_version,
                target_dsl_version=target_dsl_version,
            )
            for step in else_steps
        ),
        match_cases=MappingProxyType(
            {
                _non_empty_string(name, "match case name"): tuple(
                    _decode_step(
                        step,
                        schema_version=schema_version,
                        target_dsl_version=target_dsl_version,
                    )
                    for step in _list(steps, "match case steps")
                )
                for name, steps in match_cases.items()
            }
        ),
        repeat_until=repeat_until,
        compiler_prompt_dependency_contract=(
            _decode_compiler_prompt_dependency_contract(
                raw["compiler_prompt_dependency_contract"]
            )
            if "compiler_prompt_dependency_contract" in raw
            else None
        ),
        compiler_prompt_fragment_contract=decoded_fragment_contract,
        compiled_prompt_fragment_identity=decoded_fragment_identity,
        prompt_attempt_identity_version=decoded_q3_version,
        compiler_prompt_attempt_binding_plan=decoded_q3_plan,
    )
    validate_compiler_prompt_fragment_pair(
        decoded.compiler_prompt_fragment_contract,
        decoded.compiled_prompt_fragment_identity,
        decoded.common.expected_outputs,
    )
    _validate_persisted_prompt_attempt_pair(
        decoded.prompt_attempt_identity_version,
        decoded.compiler_prompt_attempt_binding_plan,
        fragment_contract=decoded.compiler_prompt_fragment_contract,
        dependency_contract=decoded.compiler_prompt_dependency_contract,
        target_dsl_version=target_dsl_version,
    )
    return decoded


def _validate_persisted_prompt_attempt_pair(
    identity_version: str | None,
    plan: CompilerPromptAttemptBindingPlan | None,
    *,
    fragment_contract: CompilerPromptFragmentContractCarrier | None,
    dependency_contract: CompilerPromptDependencyContract | None,
    target_dsl_version: str,
) -> None:
    typed_prompt_inputs = tuple(
        {
            "binding_name": row.slot_name,
            "renderer": row.renderer,
        }
        for row in (() if plan is None else plan.rows)
        if row.slot_kind in {"value", "path"}
    )
    validate_compiler_prompt_attempt_pair(
        identity_version,
        plan,
        fragment_contract=fragment_contract,
        dependency_contract=dependency_contract,
        typed_prompt_inputs=typed_prompt_inputs,
        target_dsl_version=target_dsl_version,
    )


_COMPILER_PROMPT_DEPENDENCY_CONTRACT_KEYS = {
    "schema",
    "origin_kind",
    "path_interpretation",
    "evidence_required",
    "source_origin_key",
    "source_workflow_sha256",
    "required_binding_refs",
    "optional_binding_refs",
    "position",
    "instruction_utf8_sha256_or_null",
    "normalized_contract_sha256",
}

_COMPILER_PROMPT_FRAGMENT_CONTRACT_V1_KEYS = {
    "schema_version",
    "template_utf8",
    "rendered_slots",
    "compiled_prompt_fragment_identity",
}
_COMPILER_PROMPT_FRAGMENT_CONTRACT_V2_KEYS = {
    "schema_version",
    "template_utf8",
    "rendered_slots",
    "output_positions",
    "compiled_prompt_fragment_identity",
}
_COMPILER_PROMPT_FRAGMENT_RENDERED_SLOT_KEYS = {
    "name",
    "kind",
    "static_type",
    "renderer_id",
    "value_source",
    "placeholder_ordinals",
}
_COMPILER_PROMPT_FRAGMENT_OUTPUT_POSITION_KEYS = {
    "slot_name",
    "output_role",
    "expected_output",
}
_COMPILER_PROMPT_ATTEMPT_BINDING_PLAN_KEYS = {
    "schema_version",
    "rows",
    "plan_sha256",
}
_COMPILER_PROMPT_ATTEMPT_BINDING_PLAN_ROW_KEYS = {
    "declaration_ordinal",
    "slot_name",
    "slot_kind",
    "refinement",
    "output_role",
    "delivery",
    "runtime_source",
    "renderer",
}


def _decode_compiler_prompt_fragment_contract(
    value: Any,
) -> CompilerPromptFragmentContractCarrier:
    raw = _mapping(value, "compiler prompt fragment contract")
    schema_version = raw.get("schema_version")
    if schema_version == COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA:
        return _decode_compiler_prompt_fragment_contract_v1(value)
    if schema_version == COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2:
        return _decode_compiler_prompt_fragment_contract_v2(value)
    raise ValueError(
        "prompt_output_position_contract_mismatch: "
        "persisted fragment contract schema is unsupported"
    )


def _decode_compiler_prompt_fragment_contract_v1(
    value: Any,
) -> CompilerPromptFragmentContract:
    try:
        raw = _mapping_with_keys(
            value,
            _COMPILER_PROMPT_FRAGMENT_CONTRACT_V1_KEYS,
            "compiler prompt fragment contract v1",
        )
        if raw["schema_version"] != COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA:
            raise ValueError("persisted fragment contract schema is not v1")
        rendered_slots = tuple(
            CompilerPromptFragmentRenderedSlot(
                name=_non_empty_string(slot["name"], "rendered slot name"),
                kind=_non_empty_string(slot["kind"], "rendered slot kind"),
                static_type=_mapping(
                    slot["static_type"],
                    "rendered slot static type",
                ),
                renderer_id=_non_empty_string(
                    slot["renderer_id"],
                    "rendered slot renderer",
                ),
                value_source=_mapping(
                    slot["value_source"],
                    "rendered slot value source",
                ),
                placeholder_ordinals=tuple(
                    _list(
                        slot["placeholder_ordinals"],
                        "rendered slot placeholder ordinals",
                    )
                ),
            )
            for slot in (
                _mapping_with_keys(
                    item,
                    _COMPILER_PROMPT_FRAGMENT_RENDERED_SLOT_KEYS,
                    "compiler prompt fragment rendered slot",
                )
                for item in _list(raw["rendered_slots"], "rendered slots")
            )
        )
        return CompilerPromptFragmentContract(
            schema_version=raw["schema_version"],
            template_utf8=raw["template_utf8"],
            rendered_slots=rendered_slots,
            compiled_prompt_fragment_identity=_non_empty_string(
                raw["compiled_prompt_fragment_identity"],
                "compiled prompt fragment identity",
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "prompt_output_position_contract_mismatch: "
            "persisted v1 fragment contract is invalid"
        ) from exc


def _decode_compiler_prompt_attempt_binding_plan(
    value: Any,
) -> CompilerPromptAttemptBindingPlan:
    try:
        raw = _mapping_with_keys(
            value,
            _COMPILER_PROMPT_ATTEMPT_BINDING_PLAN_KEYS,
            "compiler prompt attempt binding plan",
        )
        rows = tuple(
            CompilerPromptAttemptBindingPlanRow(
                declaration_ordinal=row["declaration_ordinal"],
                slot_name=_non_empty_string(
                    row["slot_name"],
                    "binding-plan slot name",
                ),
                slot_kind=_non_empty_string(
                    row["slot_kind"],
                    "binding-plan slot kind",
                ),
                refinement=(
                    None
                    if row["refinement"] is None
                    else _mapping(
                        row["refinement"],
                        "binding-plan refinement",
                    )
                ),
                output_role=_non_empty_string(
                    row["output_role"],
                    "binding-plan output role",
                ),
                delivery=_non_empty_string(
                    row["delivery"],
                    "binding-plan delivery",
                ),
                runtime_source=_mapping(
                    row["runtime_source"],
                    "binding-plan runtime source",
                ),
                renderer=(
                    None
                    if row["renderer"] is None
                    else _mapping(
                        row["renderer"],
                        "binding-plan renderer",
                    )
                ),
            )
            for row in (
                _mapping_with_keys(
                    item,
                    _COMPILER_PROMPT_ATTEMPT_BINDING_PLAN_ROW_KEYS,
                    "compiler prompt attempt binding-plan row",
                )
                for item in _list(raw["rows"], "binding-plan rows")
            )
        )
        return CompilerPromptAttemptBindingPlan(
            schema_version=_non_empty_string(
                raw["schema_version"],
                "binding-plan schema version",
            ),
            rows=rows,
            plan_sha256=_non_empty_string(
                raw["plan_sha256"],
                "binding-plan digest",
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "persisted binding plan is invalid"
        ) from exc


def _decode_compiler_prompt_fragment_contract_v2(
    value: Any,
) -> CompilerPromptFragmentContractV2:
    try:
        raw = _mapping_with_keys(
            value,
            _COMPILER_PROMPT_FRAGMENT_CONTRACT_V2_KEYS,
            "compiler prompt fragment contract v2",
        )
        if raw["schema_version"] != COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2:
            raise ValueError("persisted fragment contract schema is not v2")
        rendered_slots = tuple(
            CompilerPromptFragmentRenderedSlot(
                name=_non_empty_string(slot["name"], "rendered slot name"),
                kind=_non_empty_string(slot["kind"], "rendered slot kind"),
                static_type=_mapping(
                    slot["static_type"],
                    "rendered slot static type",
                ),
                renderer_id=_non_empty_string(
                    slot["renderer_id"],
                    "rendered slot renderer",
                ),
                value_source=_mapping(
                    slot["value_source"],
                    "rendered slot value source",
                ),
                placeholder_ordinals=tuple(
                    ordinal
                    for ordinal in _list(
                        slot["placeholder_ordinals"],
                        "rendered slot placeholder ordinals",
                    )
                ),
            )
            for slot in (
                _mapping_with_keys(
                    item,
                    _COMPILER_PROMPT_FRAGMENT_RENDERED_SLOT_KEYS,
                    "compiler prompt fragment rendered slot",
                )
                for item in _list(raw["rendered_slots"], "rendered slots")
            )
        )
        output_positions = tuple(
            CompilerPromptFragmentOutputPosition(
                slot_name=_non_empty_string(
                    row["slot_name"],
                    "output-position slot name",
                ),
                output_role=_non_empty_string(
                    row["output_role"],
                    "output-position role",
                ),
                expected_output=_mapping_with_keys(
                    row["expected_output"],
                    {"name", "path", "type", "required"},
                    "output-position expected output",
                ),
            )
            for row in (
                _mapping_with_keys(
                    item,
                    _COMPILER_PROMPT_FRAGMENT_OUTPUT_POSITION_KEYS,
                    "compiler prompt fragment output position",
                )
                for item in _list(
                    raw["output_positions"],
                    "output positions",
                )
            )
        )
        return CompilerPromptFragmentContractV2(
            schema_version=raw["schema_version"],
            template_utf8=raw["template_utf8"],
            rendered_slots=rendered_slots,
            output_positions=output_positions,
            compiled_prompt_fragment_identity=_non_empty_string(
                raw["compiled_prompt_fragment_identity"],
                "compiled prompt fragment identity",
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "prompt_output_position_contract_mismatch: "
            "persisted v2 fragment contract is invalid"
        ) from exc


def _decode_compiler_prompt_dependency_contract(
    value: Any,
) -> CompilerPromptDependencyContract:
    raw = _mapping_with_keys(
        value,
        _COMPILER_PROMPT_DEPENDENCY_CONTRACT_KEYS,
        "compiler prompt dependency contract",
    )
    try:
        contract = CompilerPromptDependencyContract(
            schema=_non_empty_string(raw["schema"], "compiler contract schema"),
            origin_kind=PromptDependencyOriginKind(
                _non_empty_string(raw["origin_kind"], "compiler contract origin kind")
            ),
            path_interpretation=PromptDependencyPathInterpretation(
                _non_empty_string(
                    raw["path_interpretation"],
                    "compiler contract path interpretation",
                )
            ),
            evidence_required=raw["evidence_required"],
            source_origin_key=_non_empty_string(
                raw["source_origin_key"], "compiler contract source origin"
            ),
            source_workflow_sha256=_non_empty_string(
                raw["source_workflow_sha256"], "compiler contract source digest"
            ),
            required_binding_refs=tuple(
                _non_empty_string(item, "required compiler binding ref")
                for item in _list(
                    raw["required_binding_refs"], "required compiler binding refs"
                )
            ),
            optional_binding_refs=tuple(
                _non_empty_string(item, "optional compiler binding ref")
                for item in _list(
                    raw["optional_binding_refs"], "optional compiler binding refs"
                )
            ),
            position=PromptDependencyPosition(
                _non_empty_string(raw["position"], "compiler contract position")
            ),
            instruction_utf8_sha256_or_null=(
                _non_empty_string(
                    raw["instruction_utf8_sha256_or_null"],
                    "compiler contract instruction digest",
                )
                if raw["instruction_utf8_sha256_or_null"] is not None
                else None
            ),
            normalized_contract_sha256=_non_empty_string(
                raw["normalized_contract_sha256"],
                "compiler contract normalized digest",
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("persisted compiler prompt dependency contract is invalid") from exc
    if contract.schema != COMPILER_PROMPT_DEPENDENCY_CONTRACT_SCHEMA:
        raise ValueError("persisted compiler prompt dependency contract schema is unsupported")
    return validate_compiler_prompt_dependency_contract(contract)


def _validate_step_kind_shape(
    kind: SurfaceStepKind,
    *,
    call_alias: str | None,
    for_each_steps: list[Any],
    then_steps: list[Any],
    else_steps: list[Any],
    match_cases: Mapping[str, Any],
    repeat_raw: Any,
) -> None:
    if (kind is SurfaceStepKind.CALL) != (call_alias is not None):
        raise ValueError("persisted surface step call alias mismatches step kind")
    structured_payloads = (
        (SurfaceStepKind.FOR_EACH, bool(for_each_steps), "for-each"),
        (SurfaceStepKind.IF, bool(then_steps or else_steps), "if branch"),
        (SurfaceStepKind.MATCH, bool(match_cases), "match case"),
    )
    for expected_kind, present, label in structured_payloads:
        if present and kind is not expected_kind:
            raise ValueError(
                f"persisted surface step {label} payload mismatches step kind"
            )
    if (kind is SurfaceStepKind.REPEAT_UNTIL) != (repeat_raw is not None):
        raise ValueError("persisted surface repeat-until payload mismatches step kind")


def _validate_graph_reachability(
    entry_workflow: str,
    nodes: Mapping[str, PersistedWorkflowSurfaceNode],
) -> None:
    active: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in active:
            raise ValueError("persisted workflow surface graph contains an import cycle")
        if node_id in visited:
            return
        node = nodes.get(node_id)
        if node is None:
            raise ValueError("persisted workflow surface import target is missing")
        active.add(node_id)
        actual_aliases = _persisted_step_call_aliases(
            (*node.steps, *node.finalization_steps)
        )
        if actual_aliases != set(node.calls):
            raise ValueError("persisted workflow surface call-edge table mismatches steps")
        for target in node.calls.values():
            visit(target)
        active.remove(node_id)
        visited.add(node_id)

    visit(entry_workflow)
    if visited != set(nodes):
        raise ValueError("persisted workflow surface graph contains unreachable nodes")


def _closed_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _reject_nonfinite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON numeric constant {value!r} is unsupported")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _mapping_with_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    mapping = _mapping(value, label)
    if set(mapping) != keys:
        raise ValueError(f"{label} has unsupported or missing fields")
    return mapping


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _optional_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, label)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _surface_call_aliases(bundle: LoadedWorkflowBundle) -> set[str]:
    steps = list(bundle.surface.steps)
    if bundle.surface.finalization is not None:
        steps.extend(bundle.surface.finalization.steps)
    aliases: set[str] = set()

    def visit(step: SurfaceStep) -> None:
        if step.call_alias:
            aliases.add(step.call_alias)
        for child in step.for_each_steps:
            visit(child)
        if step.then_branch is not None:
            for child in step.then_branch.steps:
                visit(child)
        if step.else_branch is not None:
            for child in step.else_branch.steps:
                visit(child)
        for case in step.match_cases.values():
            for child in case.steps:
                visit(child)
        if step.repeat_until is not None:
            for child in step.repeat_until.steps:
                visit(child)

    for step in steps:
        visit(step)
    return aliases


def _persisted_step_call_aliases(
    steps: tuple[PersistedSurfaceStep, ...],
) -> set[str]:
    aliases: set[str] = set()

    def visit(step: PersistedSurfaceStep) -> None:
        if step.call_alias:
            aliases.add(step.call_alias)
        for child in (
            *step.for_each_steps,
            *step.then_steps,
            *step.else_steps,
            *(child for case in step.match_cases.values() for child in case),
            *(step.repeat_until.steps if step.repeat_until is not None else ()),
        ):
            visit(child)

    for step in steps:
        visit(step)
    return aliases


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return _plain(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value
