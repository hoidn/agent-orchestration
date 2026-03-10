"""Lower structured workflow statements and surface ASTs to executable forms."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .executable_ir import (
    BlockOutputAddress,
    CallBoundaryNode,
    CallOutputAddress,
    ExecutableContract,
    ExecutableNode,
    ExecutableNodeKind,
    ExecutableTransfer,
    ExecutableWorkflow,
    FinalizationStepNode,
    ForEachNode,
    IfBranchMarkerNode,
    IfJoinNode,
    LeafExecutableNode,
    LoopOutputAddress,
    MatchCaseMarkerNode,
    MatchJoinNode,
    NodeResultAddress,
    RepeatUntilFrameNode,
    WorkflowInputAddress,
    WorkflowRegion,
)
from .identity import assign_step_ids
from .predicates import TYPED_PREDICATE_OPERATOR_KEYS
from .references import SelfOutputReference, StructuredStepReference, WorkflowInputReference
from .state_projection import (
    CallBoundaryProjection,
    CompatibilityNodeProjection,
    IterationStepKeyProjection,
    WorkflowStateProjection,
)
from .statements import (
    branch_token,
    finally_block_token,
    is_if_statement,
    is_match_statement,
    match_case_token,
    normalize_match_case_block,
    normalize_branch_block,
    normalize_finally_block,
)
from .surface_ast import (
    SurfaceContract,
    SurfaceStep,
    SurfaceStepKind,
    SurfaceWorkflow,
)


def lower_structured_steps(
    steps: Iterable[Dict[str, Any]],
    *,
    local_step_prefix: str = "root.steps",
    parent_step_prefix: str = "root.steps",
) -> List[Dict[str, Any]]:
    """Lower top-level structured statements into flat executable steps."""
    lowered: List[Dict[str, Any]] = []
    for step in steps:
        if is_match_statement(step):
            lowered.extend(
                _lower_match_statement(
                    step,
                    local_step_prefix=local_step_prefix,
                    parent_step_prefix=parent_step_prefix,
                )
            )
            continue
        if not is_if_statement(step):
            lowered.append(step)
            continue
        lowered.extend(
            _lower_if_statement(
                step,
                local_step_prefix=local_step_prefix,
                parent_step_prefix=parent_step_prefix,
            )
        )
    return lowered


def lower_repeat_until_bodies(steps: Iterable[Dict[str, Any]]) -> None:
    """Lower structured statements inside repeat_until bodies into loop-local executable steps."""
    for step in steps:
        if not isinstance(step, dict):
            continue
        repeat_until = step.get("repeat_until")
        if not isinstance(repeat_until, dict):
            continue
        body_steps = repeat_until.get("steps")
        if isinstance(body_steps, list):
            repeat_until["steps"] = lower_structured_steps(
                body_steps,
                local_step_prefix="self.steps",
                parent_step_prefix="parent.steps",
            )


def lower_finalization_block(finally_block: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Lower a workflow finally block into stable executable top-level steps."""
    normalized = normalize_finally_block(finally_block)
    if normalized is None:
        return None

    block_steps = deepcopy(normalized.get("steps") or [])
    block_token = finally_block_token(normalized)
    assign_step_ids(
        block_steps,
        parent_step_id=f"root.finally.{block_token}",
    )
    prefix_top_level_step_names(block_steps, "finally")
    for step in block_steps:
        if isinstance(step, dict):
            step["workflow_finalization"] = {"block_id": block_token}
    return {
        "id": normalized.get("id"),
        "token": block_token,
        "steps": block_steps,
    }


def _lower_if_statement(
    step: Dict[str, Any],
    *,
    local_step_prefix: str,
    parent_step_prefix: str,
) -> List[Dict[str, Any]]:
    statement_name = step["name"]
    statement_step_id = step["step_id"]
    condition = deepcopy(step["if"])

    lowered: List[Dict[str, Any]] = []
    branch_metadata: Dict[str, Dict[str, Any]] = {}

    for branch_name in ("then", "else"):
        branch = normalize_branch_block(step.get(branch_name), branch_name)
        if branch is None:
            continue

        branch_steps = deepcopy(branch.get("steps") or [])
        branch_step_id = f"{statement_step_id}.{branch_token(branch_name, branch)}"
        assign_step_ids(branch_steps, parent_step_id=branch_step_id)
        local_name_map = {
            nested_step["name"]: f"{statement_name}.{branch_name}.{nested_step['name']}"
            for nested_step in branch_steps
            if isinstance(nested_step, dict) and isinstance(nested_step.get("name"), str)
        }
        marker_name = f"{statement_name}.{branch_name}"
        guard = {
            "condition": deepcopy(condition),
            "invert": branch_name == "else",
            "statement_name": statement_name,
            "branch_name": branch_name,
        }

        lowered.append(
            {
                "name": marker_name,
                "step_id": branch_step_id,
                "structured_if_branch": {
                    "statement_name": statement_name,
                    "branch_name": branch_name,
                },
                "structured_if_guard": deepcopy(guard),
            }
        )

        branch_step_names: List[str] = []
        for branch_step in branch_steps:
            if not isinstance(branch_step, dict):
                continue
            original_name = branch_step.get("name")
            lowered_name = local_name_map.get(original_name, original_name)
            if isinstance(lowered_name, str):
                branch_step["name"] = lowered_name
            branch_step["structured_if_guard"] = deepcopy(guard)
            _rewrite_step_structured_refs(
                branch_step,
                local_name_map,
                local_step_prefix=local_step_prefix,
                parent_step_prefix=parent_step_prefix,
            )
            branch_step_names.append(branch_step["name"])
            lowered.append(branch_step)

        outputs = deepcopy(branch.get("outputs") or {})
        _rewrite_output_refs(
            outputs,
            local_name_map,
            local_step_prefix=local_step_prefix,
            parent_step_prefix=parent_step_prefix,
        )
        branch_metadata[branch_name] = {
            "marker": marker_name,
            "step_id": branch_step_id,
            "steps": branch_step_names,
            "outputs": outputs,
        }

    lowered.append(
        {
            "name": statement_name,
            "step_id": statement_step_id,
            "structured_if_join": {
                "statement_name": statement_name,
                "branches": branch_metadata,
            },
        }
    )
    return lowered


def _lower_match_statement(
    step: Dict[str, Any],
    *,
    local_step_prefix: str,
    parent_step_prefix: str,
) -> List[Dict[str, Any]]:
    statement_name = step["name"]
    statement_step_id = step["step_id"]
    match = deepcopy(step.get("match", {}))
    selector_ref = match.get("ref")
    cases = match.get("cases", {})

    lowered: List[Dict[str, Any]] = []
    case_metadata: Dict[str, Dict[str, Any]] = {}

    if not isinstance(cases, dict):
        cases = {}

    for case_name, authored_case in cases.items():
        case = normalize_match_case_block(authored_case, str(case_name))
        if case is None:
            continue

        case_steps = deepcopy(case.get("steps") or [])
        case_step_id = f"{statement_step_id}.{match_case_token(str(case_name), case)}"
        assign_step_ids(case_steps, parent_step_id=case_step_id)
        local_name_map = {
            nested_step["name"]: f"{statement_name}.{case_name}.{nested_step['name']}"
            for nested_step in case_steps
            if isinstance(nested_step, dict) and isinstance(nested_step.get("name"), str)
        }
        marker_name = f"{statement_name}.{case_name}"
        guard = {
            "condition": {
                "compare": {
                    "left": {"ref": selector_ref},
                    "op": "eq",
                    "right": case_name,
                }
            },
            "statement_name": statement_name,
            "case_name": case_name,
        }

        lowered.append(
            {
                "name": marker_name,
                "step_id": case_step_id,
                "structured_match_case": {
                    "statement_name": statement_name,
                    "case_name": case_name,
                },
                "structured_if_guard": deepcopy(guard),
            }
        )

        case_step_names: List[str] = []
        for case_step in case_steps:
            if not isinstance(case_step, dict):
                continue
            original_name = case_step.get("name")
            lowered_name = local_name_map.get(original_name, original_name)
            if isinstance(lowered_name, str):
                case_step["name"] = lowered_name
            case_step["structured_if_guard"] = deepcopy(guard)
            _rewrite_step_structured_refs(
                case_step,
                local_name_map,
                local_step_prefix=local_step_prefix,
                parent_step_prefix=parent_step_prefix,
            )
            case_step_names.append(case_step["name"])
            lowered.append(case_step)

        outputs = deepcopy(case.get("outputs") or {})
        _rewrite_output_refs(
            outputs,
            local_name_map,
            local_step_prefix=local_step_prefix,
            parent_step_prefix=parent_step_prefix,
        )
        case_metadata[str(case_name)] = {
            "marker": marker_name,
            "step_id": case_step_id,
            "steps": case_step_names,
            "outputs": outputs,
        }

    lowered.append(
        {
            "name": statement_name,
            "step_id": statement_step_id,
            "structured_match_join": {
                "statement_name": statement_name,
                "selector_ref": selector_ref,
                "cases": case_metadata,
            },
        }
    )
    return lowered


def _rewrite_step_structured_refs(
    step: Dict[str, Any],
    local_name_map: Dict[str, str],
    *,
    local_step_prefix: str,
    parent_step_prefix: str,
) -> None:
    """Rewrite branch-local structured refs on lowered executable steps."""
    for field_name in ("when", "assert"):
        if field_name in step:
            step[field_name] = _rewrite_condition_structured_refs(
                step[field_name],
                local_name_map,
                local_step_prefix=local_step_prefix,
                parent_step_prefix=parent_step_prefix,
            )
    for field_name in ("command", "input_file", "output_file", "provider_params"):
        if field_name in step:
            step[field_name] = _rewrite_legacy_step_variables(step[field_name], local_name_map)


def _rewrite_condition_structured_refs(
    node: Any,
    local_name_map: Dict[str, str],
    *,
    local_step_prefix: str,
    parent_step_prefix: str,
) -> Any:
    if not isinstance(node, dict):
        return _rewrite_legacy_step_variables(node, local_name_map)

    if any(key in node for key in TYPED_PREDICATE_OPERATOR_KEYS):
        return _rewrite_typed_predicate(
            node,
            local_name_map,
            local_step_prefix=local_step_prefix,
            parent_step_prefix=parent_step_prefix,
        )

    rewritten = deepcopy(node)
    if "equals" in rewritten and isinstance(rewritten["equals"], dict):
        equals = dict(rewritten["equals"])
        for side in ("left", "right"):
            value = equals.get(side)
            if isinstance(value, dict):
                equals[side] = _rewrite_typed_predicate(
                    value,
                    local_name_map,
                    local_step_prefix=local_step_prefix,
                    parent_step_prefix=parent_step_prefix,
                )
        rewritten["equals"] = equals
    return _rewrite_legacy_step_variables(rewritten, local_name_map)


def _rewrite_typed_predicate(
    node: Any,
    local_name_map: Dict[str, str],
    *,
    local_step_prefix: str,
    parent_step_prefix: str,
) -> Any:
    if not isinstance(node, dict):
        return node

    rewritten = deepcopy(node)

    if "artifact_bool" in rewritten and isinstance(rewritten["artifact_bool"], dict):
        ref = rewritten["artifact_bool"].get("ref")
        rewritten["artifact_bool"]["ref"] = _rewrite_structured_ref(
            ref,
            local_name_map,
            local_step_prefix=local_step_prefix,
            parent_step_prefix=parent_step_prefix,
        )
        return rewritten

    if "compare" in rewritten and isinstance(rewritten["compare"], dict):
        compare = dict(rewritten["compare"])
        for side in ("left", "right"):
            operand = compare.get(side)
            if isinstance(operand, dict) and "ref" in operand:
                compare[side] = {
                    "ref": _rewrite_structured_ref(
                        operand.get("ref"),
                        local_name_map,
                        local_step_prefix=local_step_prefix,
                        parent_step_prefix=parent_step_prefix,
                    )
                }
        rewritten["compare"] = compare
        return rewritten

    if "all_of" in rewritten and isinstance(rewritten["all_of"], list):
        rewritten["all_of"] = [
            _rewrite_typed_predicate(
                item,
                local_name_map,
                local_step_prefix=local_step_prefix,
                parent_step_prefix=parent_step_prefix,
            )
            for item in rewritten["all_of"]
        ]
        return rewritten

    if "any_of" in rewritten and isinstance(rewritten["any_of"], list):
        rewritten["any_of"] = [
            _rewrite_typed_predicate(
                item,
                local_name_map,
                local_step_prefix=local_step_prefix,
                parent_step_prefix=parent_step_prefix,
            )
            for item in rewritten["any_of"]
        ]
        return rewritten

    if "not" in rewritten:
        rewritten["not"] = _rewrite_typed_predicate(
            rewritten["not"],
            local_name_map,
            local_step_prefix=local_step_prefix,
            parent_step_prefix=parent_step_prefix,
        )
        return rewritten

    return rewritten


def _rewrite_output_refs(
    outputs: Dict[str, Any],
    local_name_map: Dict[str, str],
    *,
    local_step_prefix: str,
    parent_step_prefix: str,
) -> None:
    for spec in outputs.values():
        if not isinstance(spec, dict):
            continue
        binding = spec.get("from")
        if not isinstance(binding, dict) or "ref" not in binding:
            continue
        binding["ref"] = _rewrite_structured_ref(
            binding.get("ref"),
            local_name_map,
            local_step_prefix=local_step_prefix,
            parent_step_prefix=parent_step_prefix,
        )


def _rewrite_structured_ref(
    ref: Any,
    local_name_map: Dict[str, str],
    *,
    local_step_prefix: str,
    parent_step_prefix: str,
) -> Any:
    if not isinstance(ref, str):
        return ref
    if ref.startswith("parent.steps."):
        return f"{parent_step_prefix}.{ref[len('parent.steps.'):]}"
    if not ref.startswith("self.steps."):
        return ref

    remainder = ref[len("self.steps."):]
    for original_name in sorted(local_name_map.keys(), key=len, reverse=True):
        prefix = f"{original_name}."
        if not remainder.startswith(prefix):
            continue
        suffix = remainder[len(prefix):]
        return f"{local_step_prefix}.{local_name_map[original_name]}.{suffix}"
    return ref


def _rewrite_legacy_step_variables(value: Any, local_name_map: Dict[str, str]) -> Any:
    if isinstance(value, str):
        rewritten = value
        for original_name in sorted(local_name_map.keys(), key=len, reverse=True):
            rewritten = rewritten.replace(
                f"${{steps.{original_name}.",
                f"${{steps.{local_name_map[original_name]}.",
            )
        return rewritten
    if isinstance(value, list):
        return [_rewrite_legacy_step_variables(item, local_name_map) for item in value]
    if isinstance(value, dict):
        return {
            key: _rewrite_legacy_step_variables(item, local_name_map)
            for key, item in value.items()
        }
    return value


def prefix_top_level_step_names(steps: Iterable[Dict[str, Any]], prefix: str) -> None:
    """Prefix top-level presentation names while leaving nested loop names local."""
    for step in steps:
        if not isinstance(step, dict):
            continue
        name = step.get("name")
        if isinstance(name, str) and name:
            step["name"] = f"{prefix}.{name}"


class LoweringError(ValueError):
    """Raised when typed AST lowering cannot bind one executable node."""


class _BindingKind(str):
    LEAF = "leaf"
    BLOCK_OUTPUT = "block_output"
    LOOP_OUTPUT = "loop_output"
    CALL_OUTPUT = "call_output"


class _ProjectionBuilder:
    def __init__(self) -> None:
        self.entries_by_node_id: Dict[str, CompatibilityNodeProjection] = {}
        self.node_id_by_compatibility_index: Dict[int, str] = {}
        self.compatibility_index_by_node_id: Dict[str, int] = {}
        self.presentation_key_by_node_id: Dict[str, str] = {}
        self.node_id_by_step_id: Dict[str, str] = {}
        self.finalization_node_id_by_index: Dict[int, str] = {}
        self.finalization_index_by_node_id: Dict[str, int] = {}
        self.repeat_until_nodes: Dict[str, IterationStepKeyProjection] = {}
        self.for_each_nodes: Dict[str, IterationStepKeyProjection] = {}
        self.call_boundaries: Dict[str, CallBoundaryProjection] = {}

    def register_node(
        self,
        *,
        node_id: str,
        step_id: str,
        presentation_key: str,
        region: WorkflowRegion,
        compatibility_index: Optional[int] = None,
        finalization_index: Optional[int] = None,
    ) -> None:
        self.entries_by_node_id[node_id] = CompatibilityNodeProjection(
            node_id=node_id,
            step_id=step_id,
            presentation_key=presentation_key,
            display_name=presentation_key,
            region=region,
            compatibility_index=compatibility_index,
            finalization_index=finalization_index,
        )
        self.presentation_key_by_node_id[node_id] = presentation_key
        self.node_id_by_step_id[step_id] = node_id
        if compatibility_index is not None:
            self.node_id_by_compatibility_index[compatibility_index] = node_id
            self.compatibility_index_by_node_id[node_id] = compatibility_index
        if finalization_index is not None:
            self.finalization_node_id_by_index[finalization_index] = node_id
            self.finalization_index_by_node_id[node_id] = finalization_index

    def register_repeat_until(
        self,
        node_id: str,
        frame_key: str,
        nested_presentation_keys: Mapping[str, str],
    ) -> None:
        self.repeat_until_nodes[node_id] = IterationStepKeyProjection(
            node_id=node_id,
            frame_key=frame_key,
            nested_presentation_keys=MappingProxyType(dict(nested_presentation_keys)),
        )

    def register_for_each(
        self,
        node_id: str,
        frame_key: str,
        nested_presentation_keys: Mapping[str, str],
    ) -> None:
        self.for_each_nodes[node_id] = IterationStepKeyProjection(
            node_id=node_id,
            frame_key=frame_key,
            nested_presentation_keys=MappingProxyType(dict(nested_presentation_keys)),
        )

    def register_call_boundary(self, node_id: str, presentation_key: str, step_id: str) -> None:
        self.call_boundaries[node_id] = CallBoundaryProjection(
            node_id=node_id,
            presentation_key=presentation_key,
            step_id=step_id,
        )

    def build(self) -> WorkflowStateProjection:
        return WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(dict(self.entries_by_node_id)),
            node_id_by_compatibility_index=MappingProxyType(dict(self.node_id_by_compatibility_index)),
            compatibility_index_by_node_id=MappingProxyType(dict(self.compatibility_index_by_node_id)),
            presentation_key_by_node_id=MappingProxyType(dict(self.presentation_key_by_node_id)),
            node_id_by_step_id=MappingProxyType(dict(self.node_id_by_step_id)),
            finalization_node_id_by_index=MappingProxyType(dict(self.finalization_node_id_by_index)),
            finalization_index_by_node_id=MappingProxyType(dict(self.finalization_index_by_node_id)),
            repeat_until_nodes=MappingProxyType(dict(self.repeat_until_nodes)),
            for_each_nodes=MappingProxyType(dict(self.for_each_nodes)),
            call_boundaries=MappingProxyType(dict(self.call_boundaries)),
        )


class _BindingTarget:
    def __init__(self, node_id: str, kind: _BindingKind) -> None:
        self.node_id = node_id
        self.kind = kind


class _BindingContext:
    def __init__(
        self,
        *,
        root_targets: Mapping[str, _BindingTarget],
        self_targets: Mapping[str, _BindingTarget],
        parent_targets: Mapping[str, _BindingTarget],
        current_loop_node_id: Optional[str] = None,
    ) -> None:
        self.root_targets = root_targets
        self.self_targets = self_targets
        self.parent_targets = parent_targets
        self.current_loop_node_id = current_loop_node_id


class _IRBuilder:
    def __init__(self, surface: SurfaceWorkflow) -> None:
        self.surface = surface
        self.nodes: Dict[str, ExecutableNode] = {}
        self.body_region: List[str] = []
        self.finalization_region: List[str] = []
        self.projection = _ProjectionBuilder()

    def build(self) -> tuple[ExecutableWorkflow, WorkflowStateProjection]:
        root_targets = _surface_binding_targets(self.surface.steps)
        self._lower_linear_steps(
            self.surface.steps,
            region=WorkflowRegion.BODY,
            context=_BindingContext(
                root_targets=root_targets,
                self_targets=root_targets,
                parent_targets={},
            ),
            presentation_prefix=None,
            top_level_region=self.body_region,
        )

        if self.surface.finalization is not None:
            final_targets = _surface_binding_targets(self.surface.finalization.steps)
            self._lower_linear_steps(
                self.surface.finalization.steps,
                region=WorkflowRegion.FINALIZATION,
                context=_BindingContext(
                    root_targets=root_targets,
                    self_targets=final_targets,
                    parent_targets={},
                ),
                presentation_prefix="finally",
                top_level_region=self.finalization_region,
            )

        self._patch_linear_fallthrough(self.body_region)
        self._patch_linear_fallthrough(self.finalization_region)

        executable = ExecutableWorkflow(
            version=self.surface.version,
            name=self.surface.name,
            provenance=self.surface.provenance,
            body_region=tuple(self.body_region),
            finalization_region=tuple(self.finalization_region),
            nodes=MappingProxyType(dict(self.nodes)),
            artifacts=_bind_contracts(
                self.surface.artifacts,
                _BindingContext(
                    root_targets=root_targets,
                    self_targets=root_targets,
                    parent_targets={},
                ),
            ),
            inputs=MappingProxyType(
                {
                    name: ExecutableContract(
                        name=contract.name,
                        kind=contract.kind,
                        value_type=contract.value_type,
                        raw=contract.raw,
                        source_address=None,
                    )
                    for name, contract in self.surface.inputs.items()
                }
            ),
            outputs=_bind_contracts(
                self.surface.outputs,
                _BindingContext(
                    root_targets=root_targets,
                    self_targets=root_targets,
                    parent_targets={},
                ),
            ),
        )
        return executable, self.projection.build()

    def _lower_linear_steps(
        self,
        steps: tuple[SurfaceStep, ...],
        *,
        region: WorkflowRegion,
        context: _BindingContext,
        presentation_prefix: Optional[str],
        top_level_region: List[str],
    ) -> List[str]:
        ordered: List[str] = []
        for step in steps:
            principal_name = _qualified_presentation_name(presentation_prefix, step.name)
            if step.kind is SurfaceStepKind.IF:
                ordered.extend(
                    self._lower_if_step(
                        step,
                        region=region,
                        context=context,
                        statement_presentation_name=principal_name,
                        top_level_region=top_level_region,
                    )
                )
                continue
            if step.kind is SurfaceStepKind.MATCH:
                ordered.extend(
                    self._lower_match_step(
                        step,
                        region=region,
                        context=context,
                        statement_presentation_name=principal_name,
                        top_level_region=top_level_region,
                    )
                )
                continue
            if step.kind is SurfaceStepKind.REPEAT_UNTIL:
                node = self._build_repeat_until_node(
                    step,
                    region=region,
                    context=context,
                    presentation_name=principal_name,
                )
                self._register_node(node=node, region=region, top_level_region=top_level_region)
                ordered.append(node.node_id)
                continue
            if step.kind is SurfaceStepKind.FOR_EACH:
                node = self._build_for_each_node(
                    step,
                    region=region,
                    context=context,
                    presentation_name=principal_name,
                )
                self._register_node(node=node, region=region, top_level_region=top_level_region)
                ordered.append(node.node_id)
                continue
            node = self._build_leaf_node(
                step,
                region=region,
                context=context,
                presentation_name=principal_name,
            )
            self._register_node(node=node, region=region, top_level_region=top_level_region)
            ordered.append(node.node_id)
        return ordered

    def _register_node(
        self,
        *,
        node: ExecutableNode,
        region: WorkflowRegion,
        top_level_region: List[str],
    ) -> None:
        self.nodes[node.node_id] = node
        compatibility_index = None
        finalization_index = None
        if region is WorkflowRegion.BODY and top_level_region is self.body_region:
            compatibility_index = len(self.body_region)
            self.body_region.append(node.node_id)
        elif region is WorkflowRegion.FINALIZATION and top_level_region is self.finalization_region:
            finalization_index = len(self.finalization_region)
            self.finalization_region.append(node.node_id)
        self.projection.register_node(
            node_id=node.node_id,
            step_id=node.step_id,
            presentation_key=node.presentation_name,
            region=region,
            compatibility_index=compatibility_index,
            finalization_index=finalization_index,
        )
        if isinstance(node, CallBoundaryNode):
            self.projection.register_call_boundary(node.node_id, node.presentation_name, node.step_id)

    def _build_leaf_node(
        self,
        step: SurfaceStep,
        *,
        region: WorkflowRegion,
        context: _BindingContext,
        presentation_name: str,
    ) -> ExecutableNode:
        leaf_kind = _leaf_node_kind(step.kind, region)
        common = {
            "node_id": step.step_id,
            "step_id": step.step_id,
            "presentation_name": presentation_name,
            "kind": leaf_kind,
            "region": region,
            "lexical_scope": tuple(token for token in step.step_id.split(".") if token),
            "raw": step.raw,
        }
        routed_transfers = _leaf_goto_transfers(step.raw, context.root_targets)
        if step.kind is SurfaceStepKind.CALL:
            return CallBoundaryNode(
                **common,
                routed_transfers=routed_transfers,
                call_alias=step.call_alias or "",
                bound_inputs=MappingProxyType(
                    {
                        name: _bind_literal_or_ref(value, context)
                        for name, value in step.call_bindings.items()
                    }
                ),
                bound_when_predicate=_bind_predicate(step.when_predicate, context),
                bound_assert_predicate=_bind_predicate(step.assert_predicate, context),
            )
        if region is WorkflowRegion.FINALIZATION:
            return FinalizationStepNode(
                **common,
                routed_transfers=routed_transfers,
                execution_kind=_leaf_node_kind(step.kind, WorkflowRegion.BODY),
                bound_when_predicate=_bind_predicate(step.when_predicate, context),
                bound_assert_predicate=_bind_predicate(step.assert_predicate, context),
            )
        return LeafExecutableNode(
            **common,
            routed_transfers=routed_transfers,
            bound_when_predicate=_bind_predicate(step.when_predicate, context),
            bound_assert_predicate=_bind_predicate(step.assert_predicate, context),
        )

    def _build_repeat_until_node(
        self,
        step: SurfaceStep,
        *,
        region: WorkflowRegion,
        context: _BindingContext,
        presentation_name: str,
    ) -> RepeatUntilFrameNode:
        if step.repeat_until is None:
            raise LoweringError(f"repeat_until step '{step.name}' is missing its body block")
        body_targets = _surface_binding_targets(step.repeat_until.steps)
        body_context = _BindingContext(
            root_targets=context.root_targets,
            self_targets=body_targets,
            parent_targets=context.self_targets,
            current_loop_node_id=step.step_id,
        )
        body_node_ids = self._lower_linear_steps(
            step.repeat_until.steps,
            region=region,
            context=body_context,
            presentation_prefix=None,
            top_level_region=[],
        )
        self._patch_linear_fallthrough(body_node_ids, final_target=step.step_id)
        nested_keys = {node_id: self.nodes[node_id].presentation_name for node_id in body_node_ids}
        self.projection.register_repeat_until(step.step_id, presentation_name, nested_keys)
        return RepeatUntilFrameNode(
            node_id=step.step_id,
            step_id=step.step_id,
            presentation_name=presentation_name,
            kind=ExecutableNodeKind.REPEAT_UNTIL_FRAME,
            region=region,
            lexical_scope=tuple(token for token in step.step_id.split(".") if token),
            raw=step.raw,
            body_node_ids=tuple(body_node_ids),
            body_entry_node_id=body_node_ids[0] if body_node_ids else None,
            condition=_bind_predicate(step.repeat_until.condition, body_context),
            max_iterations=step.repeat_until.max_iterations,
            output_contracts=_bind_contracts(step.repeat_until.outputs, body_context),
        )

    def _build_for_each_node(
        self,
        step: SurfaceStep,
        *,
        region: WorkflowRegion,
        context: _BindingContext,
        presentation_name: str,
    ) -> ForEachNode:
        body_targets = _surface_binding_targets(step.for_each_steps)
        body_context = _BindingContext(
            root_targets=context.root_targets,
            self_targets=body_targets,
            parent_targets=context.self_targets,
        )
        body_node_ids = self._lower_linear_steps(
            step.for_each_steps,
            region=region,
            context=body_context,
            presentation_prefix=None,
            top_level_region=[],
        )
        nested_keys = {node_id: self.nodes[node_id].presentation_name for node_id in body_node_ids}
        self.projection.register_for_each(step.step_id, presentation_name, nested_keys)
        return ForEachNode(
            node_id=step.step_id,
            step_id=step.step_id,
            presentation_name=presentation_name,
            kind=ExecutableNodeKind.FOR_EACH,
            region=region,
            lexical_scope=tuple(token for token in step.step_id.split(".") if token),
            raw=step.raw,
            body_node_ids=tuple(body_node_ids),
            body_entry_node_id=body_node_ids[0] if body_node_ids else None,
            bound_when_predicate=_bind_predicate(step.when_predicate, context),
            bound_assert_predicate=_bind_predicate(step.assert_predicate, context),
        )

    def _lower_if_step(
        self,
        step: SurfaceStep,
        *,
        region: WorkflowRegion,
        context: _BindingContext,
        statement_presentation_name: str,
        top_level_region: List[str],
    ) -> List[str]:
        ordered: List[str] = []
        join_node_id = step.step_id
        branch_specs = [
            ("then", step.then_branch, False),
            ("else", step.else_branch, True),
        ]
        next_marker_ids: Dict[str, Optional[str]] = {}
        present_branches = [name for name, block, _invert in branch_specs if block is not None]
        for idx, branch_name in enumerate(present_branches):
            next_marker_ids[branch_name] = None if idx == len(present_branches) - 1 else (
                step.then_branch.step_id if present_branches[idx + 1] == "then" and step.then_branch is not None else
                step.else_branch.step_id if present_branches[idx + 1] == "else" and step.else_branch is not None else
                None
            )
        branch_outputs: Dict[str, Mapping[str, ExecutableContract]] = {}

        for branch_name, block, invert_guard in branch_specs:
            if block is None:
                continue
            marker_presentation = f"{statement_presentation_name}.{branch_name}"
            branch_targets = _surface_binding_targets(block.steps)
            branch_context = _BindingContext(
                root_targets=context.root_targets,
                self_targets=branch_targets,
                parent_targets=context.self_targets,
                current_loop_node_id=context.current_loop_node_id,
            )
            branch_node_ids = self._lower_linear_steps(
                block.steps,
                region=region,
                context=branch_context,
                presentation_prefix=marker_presentation,
                top_level_region=[],
            )
            self._patch_linear_fallthrough(branch_node_ids, final_target=join_node_id)
            branch_outputs[branch_name] = _bind_contracts(block.outputs, branch_context)
            marker = IfBranchMarkerNode(
                node_id=block.step_id,
                step_id=block.step_id,
                presentation_name=marker_presentation,
                kind=ExecutableNodeKind.IF_BRANCH_MARKER,
                region=region,
                lexical_scope=tuple(token for token in block.step_id.split(".") if token),
                raw=block.raw,
                routed_transfers=MappingProxyType(
                    {
                        "branch_taken": ExecutableTransfer(
                            reason="branch_taken",
                            target_node_id=branch_node_ids[0] if branch_node_ids else join_node_id,
                        ),
                        "branch_skipped": ExecutableTransfer(
                            reason="branch_skipped",
                            target_node_id=next_marker_ids.get(branch_name) or join_node_id,
                        ),
                    }
                ),
                statement_name=statement_presentation_name,
                branch_name=branch_name,
                guard_condition=_bind_predicate(step.if_condition, context),
                invert_guard=invert_guard,
            )
            self._register_node(node=marker, region=region, top_level_region=top_level_region)
            ordered.append(marker.node_id)
            for node_id in branch_node_ids:
                self._register_existing_child(node_id=node_id, region=region, top_level_region=top_level_region)
                ordered.append(node_id)

        join = IfJoinNode(
            node_id=step.step_id,
            step_id=step.step_id,
            presentation_name=statement_presentation_name,
            kind=ExecutableNodeKind.IF_JOIN,
            region=region,
            lexical_scope=tuple(token for token in step.step_id.split(".") if token),
            raw=step.raw,
            statement_name=statement_presentation_name,
            branch_outputs=MappingProxyType(dict(branch_outputs)),
        )
        self._register_node(node=join, region=region, top_level_region=top_level_region)
        ordered.append(join.node_id)
        return ordered

    def _lower_match_step(
        self,
        step: SurfaceStep,
        *,
        region: WorkflowRegion,
        context: _BindingContext,
        statement_presentation_name: str,
        top_level_region: List[str],
    ) -> List[str]:
        ordered: List[str] = []
        join_node_id = step.step_id
        selector_address = _bind_surface_ref(step.match_ref, context)
        case_names = list(step.match_cases.keys())
        case_outputs: Dict[str, Mapping[str, ExecutableContract]] = {}

        for index, case_name in enumerate(case_names):
            block = step.match_cases[case_name]
            next_case_id = step.match_cases[case_names[index + 1]].step_id if index + 1 < len(case_names) else None
            marker_presentation = f"{statement_presentation_name}.{case_name}"
            case_targets = _surface_binding_targets(block.steps)
            case_context = _BindingContext(
                root_targets=context.root_targets,
                self_targets=case_targets,
                parent_targets=context.self_targets,
                current_loop_node_id=context.current_loop_node_id,
            )
            case_node_ids = self._lower_linear_steps(
                block.steps,
                region=region,
                context=case_context,
                presentation_prefix=marker_presentation,
                top_level_region=[],
            )
            self._patch_linear_fallthrough(case_node_ids, final_target=join_node_id)
            case_outputs[case_name] = _bind_contracts(block.outputs, case_context)
            marker = MatchCaseMarkerNode(
                node_id=block.step_id,
                step_id=block.step_id,
                presentation_name=marker_presentation,
                kind=ExecutableNodeKind.MATCH_CASE_MARKER,
                region=region,
                lexical_scope=tuple(token for token in block.step_id.split(".") if token),
                raw=block.raw,
                routed_transfers=MappingProxyType(
                    {
                        "case_selected": ExecutableTransfer(
                            reason="case_selected",
                            target_node_id=case_node_ids[0] if case_node_ids else join_node_id,
                        ),
                        "case_skipped": ExecutableTransfer(
                            reason="case_skipped",
                            target_node_id=next_case_id or join_node_id,
                        ),
                    }
                ),
                statement_name=statement_presentation_name,
                case_name=case_name,
                selector_address=selector_address,
            )
            self._register_node(node=marker, region=region, top_level_region=top_level_region)
            ordered.append(marker.node_id)
            for node_id in case_node_ids:
                self._register_existing_child(node_id=node_id, region=region, top_level_region=top_level_region)
                ordered.append(node_id)

        join = MatchJoinNode(
            node_id=step.step_id,
            step_id=step.step_id,
            presentation_name=statement_presentation_name,
            kind=ExecutableNodeKind.MATCH_JOIN,
            region=region,
            lexical_scope=tuple(token for token in step.step_id.split(".") if token),
            raw=step.raw,
            statement_name=statement_presentation_name,
            selector_address=selector_address,
            case_outputs=MappingProxyType(dict(case_outputs)),
        )
        self._register_node(node=join, region=region, top_level_region=top_level_region)
        ordered.append(join.node_id)
        return ordered

    def _register_existing_child(
        self,
        *,
        node_id: str,
        region: WorkflowRegion,
        top_level_region: List[str],
    ) -> None:
        node = self.nodes[node_id]
        compatibility_index = None
        finalization_index = None
        if region is WorkflowRegion.BODY and top_level_region is self.body_region:
            compatibility_index = len(self.body_region)
            self.body_region.append(node_id)
        elif region is WorkflowRegion.FINALIZATION and top_level_region is self.finalization_region:
            finalization_index = len(self.finalization_region)
            self.finalization_region.append(node_id)
        self.projection.register_node(
            node_id=node.node_id,
            step_id=node.step_id,
            presentation_key=node.presentation_name,
            region=region,
            compatibility_index=compatibility_index,
            finalization_index=finalization_index,
        )

    def _patch_linear_fallthrough(self, node_ids: List[str], final_target: Optional[str] = None) -> None:
        if not node_ids:
            return
        for index, node_id in enumerate(node_ids):
            next_node_id = node_ids[index + 1] if index + 1 < len(node_ids) else final_target
            node = self.nodes[node_id]
            if next_node_id is None:
                continue
            self.nodes[node_id] = replace(node, fallthrough_node_id=next_node_id)


def _qualified_presentation_name(prefix: Optional[str], name: str) -> str:
    return f"{prefix}.{name}" if prefix else name


def _leaf_node_kind(kind: SurfaceStepKind, region: WorkflowRegion) -> ExecutableNodeKind:
    if region is WorkflowRegion.FINALIZATION:
        return ExecutableNodeKind.FINALIZATION_STEP
    mapping = {
        SurfaceStepKind.COMMAND: ExecutableNodeKind.COMMAND,
        SurfaceStepKind.PROVIDER: ExecutableNodeKind.PROVIDER,
        SurfaceStepKind.WAIT_FOR: ExecutableNodeKind.WAIT_FOR,
        SurfaceStepKind.ASSERT: ExecutableNodeKind.ASSERT,
        SurfaceStepKind.SET_SCALAR: ExecutableNodeKind.SET_SCALAR,
        SurfaceStepKind.INCREMENT_SCALAR: ExecutableNodeKind.INCREMENT_SCALAR,
        SurfaceStepKind.FOR_EACH: ExecutableNodeKind.FOR_EACH,
        SurfaceStepKind.CALL: ExecutableNodeKind.CALL_BOUNDARY,
    }
    return mapping[kind]


def _surface_binding_targets(steps: tuple[SurfaceStep, ...]) -> Mapping[str, _BindingTarget]:
    targets: Dict[str, _BindingTarget] = {}
    for step in steps:
        kind = _BindingKind.LEAF
        if step.kind is SurfaceStepKind.IF or step.kind is SurfaceStepKind.MATCH:
            kind = _BindingKind.BLOCK_OUTPUT
        elif step.kind is SurfaceStepKind.REPEAT_UNTIL:
            kind = _BindingKind.LOOP_OUTPUT
        elif step.kind is SurfaceStepKind.CALL:
            kind = _BindingKind.CALL_OUTPUT
        targets[step.name] = _BindingTarget(step.step_id, kind)
    return targets


def _leaf_goto_transfers(raw: Mapping[str, Any], root_targets: Mapping[str, _BindingTarget]) -> Mapping[str, ExecutableTransfer]:
    goto_name = raw.get("goto") if isinstance(raw, Mapping) else None
    if not isinstance(goto_name, str) or goto_name not in root_targets:
        return MappingProxyType({})
    return MappingProxyType(
        {
            "goto": ExecutableTransfer(
                reason="goto",
                target_node_id=root_targets[goto_name].node_id,
                counts_as_transition=True,
            )
        }
    )


def _bind_contracts(
    contracts: Mapping[str, SurfaceContract],
    context: _BindingContext,
) -> Mapping[str, ExecutableContract]:
    return MappingProxyType(
        {
            name: ExecutableContract(
                name=contract.name,
                kind=contract.kind,
                value_type=contract.value_type,
                raw=contract.raw,
                source_address=_bind_surface_ref(contract.from_ref, context),
            )
            for name, contract in contracts.items()
        }
    )


def _bind_literal_or_ref(value: Any, context: _BindingContext) -> Any:
    if isinstance(value, (WorkflowInputReference, StructuredStepReference, SelfOutputReference)):
        return _bind_surface_ref(value, context)
    return value


def _bind_surface_ref(ref: Any, context: _BindingContext) -> Any:
    if ref is None:
        return None
    if isinstance(ref, WorkflowInputReference):
        return WorkflowInputAddress(input_name=ref.input_name)
    if isinstance(ref, SelfOutputReference):
        if not context.current_loop_node_id:
            raise LoweringError(f"self.outputs ref '{ref.output_name}' is unavailable outside repeat_until")
        return LoopOutputAddress(
            node_id=context.current_loop_node_id,
            output_name=ref.output_name,
        )
    if isinstance(ref, StructuredStepReference):
        targets = {
            "root": context.root_targets,
            "self": context.self_targets,
            "parent": context.parent_targets,
        }.get(ref.scope)
        if targets is None or ref.step_name not in targets:
            raise LoweringError(
                f"Unable to bind ref for step '{ref.step_name}' in scope '{ref.scope}'"
            )
        target = targets[ref.step_name]
        if target.kind == _BindingKind.BLOCK_OUTPUT and ref.field == "artifacts" and ref.member:
            return BlockOutputAddress(node_id=target.node_id, output_name=ref.member)
        if target.kind == _BindingKind.LOOP_OUTPUT and ref.field == "artifacts" and ref.member:
            return LoopOutputAddress(node_id=target.node_id, output_name=ref.member)
        if target.kind == _BindingKind.CALL_OUTPUT and ref.field == "artifacts" and ref.member:
            return CallOutputAddress(node_id=target.node_id, output_name=ref.member)
        return NodeResultAddress(
            node_id=target.node_id,
            field=ref.field,
            member=ref.member,
        )
    return ref


def _bind_predicate(predicate: Any, context: _BindingContext) -> Any:
    if predicate is None:
        return None
    if hasattr(predicate, "ref"):
        return replace(predicate, ref=_bind_surface_ref(predicate.ref, context))
    if hasattr(predicate, "left") and hasattr(predicate, "right"):
        return replace(
            predicate,
            left=_bind_literal_or_ref(predicate.left, context),
            right=_bind_literal_or_ref(predicate.right, context),
        )
    if hasattr(predicate, "items"):
        return replace(
            predicate,
            items=tuple(_bind_predicate(item, context) for item in predicate.items),
        )
    if hasattr(predicate, "item"):
        return replace(
            predicate,
            item=_bind_predicate(predicate.item, context),
        )
    return predicate


def lower_surface_workflow(surface: SurfaceWorkflow) -> tuple[ExecutableWorkflow, WorkflowStateProjection]:
    """Lower the immutable authored surface AST into executable IR + compatibility projection."""
    return _IRBuilder(surface).build()
