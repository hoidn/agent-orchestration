"""Lower typed surface ASTs to executable IR and state projection forms."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional

from .executable_ir import (
    AdjudicatedProviderStepConfig,
    AssertStepConfig,
    BlockOutputAddress,
    CallBoundaryNode,
    CallStepConfig,
    CallOutputAddress,
    CommandStepConfig,
    ExecutableContract,
    ExecutableNode,
    ExecutableNodeKind,
    ExecutableStepConfig,
    ExecutableTransfer,
    ExecutableWorkflow,
    FinalizationStepNode,
    ForEachNode,
    ForEachStepConfig,
    IncrementScalarStepConfig,
    IfBranchMarkerNode,
    IfJoinNode,
    LeafExecutableNode,
    LoopOutputAddress,
    MatchCaseMarkerNode,
    MatchJoinNode,
    NodeResultAddress,
    ProviderStepConfig,
    RepeatUntilFrameNode,
    RepeatUntilStepConfig,
    SetScalarStepConfig,
    StepCommonConfig,
    WaitForStepConfig,
    WorkflowInputAddress,
    WorkflowRegion,
)
from .references import SelfOutputReference, StructuredStepReference, WorkflowInputReference
from .state_projection import (
    CallBoundaryProjection,
    CompatibilityStepDefinition,
    CompatibilityNodeProjection,
    IterationStepKeyProjection,
    StructuredSelectionProjection,
    WorkflowStateProjection,
)
from .statements import branch_token, match_case_token
from .surface_ast import (
    SurfaceContract,
    SurfaceOnConfig,
    SurfaceStep,
    SurfaceStepCommonConfig,
    SurfaceStepKind,
    SurfaceWorkflow,
    freeze_mapping,
    freeze_value,
)


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
        self.structured_if_branches: Dict[str, Mapping[str, StructuredSelectionProjection]] = {}
        self.structured_match_cases: Dict[str, Mapping[str, StructuredSelectionProjection]] = {}

    def register_node(
        self,
        *,
        node_id: str,
        step_id: str,
        presentation_key: str,
        region: WorkflowRegion,
        step_definition: CompatibilityStepDefinition,
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
            step_definition=step_definition,
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
        nested_step_id_suffixes = {
            nested_node_id: _iteration_step_id_suffix(node_id, nested_node_id)
            for nested_node_id in nested_presentation_keys
        }
        self.repeat_until_nodes[node_id] = IterationStepKeyProjection(
            node_id=node_id,
            frame_key=frame_key,
            nested_presentation_keys=MappingProxyType(dict(nested_presentation_keys)),
            nested_step_id_suffixes=MappingProxyType(dict(nested_step_id_suffixes)),
        )

    def register_for_each(
        self,
        node_id: str,
        frame_key: str,
        nested_presentation_keys: Mapping[str, str],
    ) -> None:
        nested_step_id_suffixes = {
            nested_node_id: _iteration_step_id_suffix(node_id, nested_node_id)
            for nested_node_id in nested_presentation_keys
        }
        self.for_each_nodes[node_id] = IterationStepKeyProjection(
            node_id=node_id,
            frame_key=frame_key,
            nested_presentation_keys=MappingProxyType(dict(nested_presentation_keys)),
            nested_step_id_suffixes=MappingProxyType(dict(nested_step_id_suffixes)),
        )

    def register_call_boundary(
        self,
        node_id: str,
        presentation_key: str,
        step_id: str,
        *,
        iteration_owner_node_id: Optional[str] = None,
    ) -> None:
        iteration_step_id_suffix = None
        if iteration_owner_node_id is not None:
            iteration_step_id_suffix = _iteration_step_id_suffix(iteration_owner_node_id, step_id)
        self.call_boundaries[node_id] = CallBoundaryProjection(
            node_id=node_id,
            presentation_key=presentation_key,
            step_id=step_id,
            iteration_owner_node_id=iteration_owner_node_id,
            iteration_step_id_suffix=iteration_step_id_suffix,
        )

    def register_structured_if(
        self,
        node_id: str,
        branches: Mapping[str, StructuredSelectionProjection],
    ) -> None:
        self.structured_if_branches[node_id] = MappingProxyType(dict(branches))

    def register_structured_match(
        self,
        node_id: str,
        cases: Mapping[str, StructuredSelectionProjection],
    ) -> None:
        self.structured_match_cases[node_id] = MappingProxyType(dict(cases))

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
            structured_if_branches=MappingProxyType(dict(self.structured_if_branches)),
            structured_match_cases=MappingProxyType(dict(self.structured_match_cases)),
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
        iteration_owner_node_id: Optional[str] = None,
    ) -> None:
        self.root_targets = root_targets
        self.self_targets = self_targets
        self.parent_targets = parent_targets
        self.current_loop_node_id = current_loop_node_id
        self.iteration_owner_node_id = (
            current_loop_node_id if iteration_owner_node_id is None else iteration_owner_node_id
        )


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

        finalization_entry_node_id = self.finalization_region[0] if self.finalization_region else None
        self._patch_linear_fallthrough(self.body_region, final_target=finalization_entry_node_id)
        self._patch_linear_fallthrough(self.finalization_region)

        executable = ExecutableWorkflow(
            version=self.surface.version,
            name=self.surface.name,
            provenance=self.surface.provenance,
            body_region=tuple(self.body_region),
            finalization_region=tuple(self.finalization_region),
            finalization_entry_node_id=finalization_entry_node_id,
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
                        definition=contract.definition,
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
            if step.kind is SurfaceStepKind.CALL:
                self.projection.register_call_boundary(
                    node.node_id,
                    node.presentation_name,
                    node.step_id,
                    iteration_owner_node_id=context.iteration_owner_node_id,
                )
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
            step_definition=_compatibility_step_definition(node),
            compatibility_index=compatibility_index,
            finalization_index=finalization_index,
        )
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
            "execution_config": _execution_config_for_step(step),
        }
        routed_transfers = _leaf_goto_transfers(step.common.on, context.root_targets)
        if step.kind is SurfaceStepKind.CALL:
            call_transfers = dict(routed_transfers)
            call_transfers["call_return"] = ExecutableTransfer(
                reason="call_return",
                target_node_id=None,
            )
            return CallBoundaryNode(
                **common,
                routed_transfers=MappingProxyType(call_transfers),
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
            iteration_owner_node_id=step.step_id,
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
            execution_config=_execution_config_for_step(step),
            routed_transfers=MappingProxyType(
                {
                    "loop_continue": ExecutableTransfer(
                        reason="loop_continue",
                        target_node_id=body_node_ids[0] if body_node_ids else None,
                    ),
                    "loop_exit": ExecutableTransfer(
                        reason="loop_exit",
                        target_node_id=None,
                    ),
                }
            ),
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
            iteration_owner_node_id=step.step_id,
        )
        body_node_ids = self._lower_linear_steps(
            step.for_each_steps,
            region=region,
            context=body_context,
            presentation_prefix=None,
            top_level_region=[],
        )
        self._patch_linear_fallthrough(body_node_ids, final_target=step.step_id)
        nested_keys = {node_id: self.nodes[node_id].presentation_name for node_id in body_node_ids}
        self.projection.register_for_each(step.step_id, presentation_name, nested_keys)
        return ForEachNode(
            node_id=step.step_id,
            step_id=step.step_id,
            presentation_name=presentation_name,
            kind=ExecutableNodeKind.FOR_EACH,
            region=region,
            lexical_scope=tuple(token for token in step.step_id.split(".") if token),
            execution_config=_execution_config_for_step(step),
            routed_transfers=MappingProxyType(
                {
                    "loop_continue": ExecutableTransfer(
                        reason="loop_continue",
                        target_node_id=body_node_ids[0] if body_node_ids else None,
                    ),
                    "loop_exit": ExecutableTransfer(
                        reason="loop_exit",
                        target_node_id=None,
                    ),
                }
            ),
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
        branch_projection: Dict[str, StructuredSelectionProjection] = {}

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
                iteration_owner_node_id=context.iteration_owner_node_id,
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
            branch_projection[branch_name] = StructuredSelectionProjection(
                marker_step_id=block.step_id,
                marker_presentation_key=marker_presentation,
                step_presentation_keys=tuple(
                    self.nodes[node_id].presentation_name
                    for node_id in branch_node_ids
                ),
            )
            marker = IfBranchMarkerNode(
                node_id=block.step_id,
                step_id=block.step_id,
                presentation_name=marker_presentation,
                kind=ExecutableNodeKind.IF_BRANCH_MARKER,
                region=region,
                lexical_scope=tuple(token for token in block.step_id.split(".") if token),
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
            statement_name=statement_presentation_name,
            branch_outputs=MappingProxyType(dict(branch_outputs)),
        )
        self._register_node(node=join, region=region, top_level_region=top_level_region)
        self.projection.register_structured_if(step.step_id, branch_projection)
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
        case_projection: Dict[str, StructuredSelectionProjection] = {}

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
                iteration_owner_node_id=context.iteration_owner_node_id,
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
            case_projection[case_name] = StructuredSelectionProjection(
                marker_step_id=block.step_id,
                marker_presentation_key=marker_presentation,
                step_presentation_keys=tuple(
                    self.nodes[node_id].presentation_name
                    for node_id in case_node_ids
                ),
            )
            marker = MatchCaseMarkerNode(
                node_id=block.step_id,
                step_id=block.step_id,
                presentation_name=marker_presentation,
                kind=ExecutableNodeKind.MATCH_CASE_MARKER,
                region=region,
                lexical_scope=tuple(token for token in block.step_id.split(".") if token),
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
            statement_name=statement_presentation_name,
            selector_address=selector_address,
            case_outputs=MappingProxyType(dict(case_outputs)),
        )
        self._register_node(node=join, region=region, top_level_region=top_level_region)
        self.projection.register_structured_match(step.step_id, case_projection)
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
            step_definition=_compatibility_step_definition(node),
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
            replacement = replace(node, fallthrough_node_id=next_node_id)
            if isinstance(replacement, CallBoundaryNode):
                routed = dict(replacement.routed_transfers)
                routed["call_return"] = replace(
                    routed["call_return"],
                    target_node_id=next_node_id,
                )
                replacement = replace(replacement, routed_transfers=MappingProxyType(routed))
            elif isinstance(replacement, (RepeatUntilFrameNode, ForEachNode)):
                routed = dict(replacement.routed_transfers)
                routed["loop_exit"] = replace(
                    routed["loop_exit"],
                    target_node_id=next_node_id,
                )
                replacement = replace(replacement, routed_transfers=MappingProxyType(routed))
            self.nodes[node_id] = replacement


def _qualified_presentation_name(prefix: Optional[str], name: str) -> str:
    return f"{prefix}.{name}" if prefix else name


def _leaf_node_kind(kind: SurfaceStepKind, region: WorkflowRegion) -> ExecutableNodeKind:
    if region is WorkflowRegion.FINALIZATION:
        return ExecutableNodeKind.FINALIZATION_STEP
    mapping = {
        SurfaceStepKind.COMMAND: ExecutableNodeKind.COMMAND,
        SurfaceStepKind.PROVIDER: ExecutableNodeKind.PROVIDER,
        SurfaceStepKind.ADJUDICATED_PROVIDER: ExecutableNodeKind.ADJUDICATED_PROVIDER,
        SurfaceStepKind.WAIT_FOR: ExecutableNodeKind.WAIT_FOR,
        SurfaceStepKind.ASSERT: ExecutableNodeKind.ASSERT,
        SurfaceStepKind.SET_SCALAR: ExecutableNodeKind.SET_SCALAR,
        SurfaceStepKind.INCREMENT_SCALAR: ExecutableNodeKind.INCREMENT_SCALAR,
        SurfaceStepKind.FOR_EACH: ExecutableNodeKind.FOR_EACH,
        SurfaceStepKind.CALL: ExecutableNodeKind.CALL_BOUNDARY,
    }
    return mapping[kind]


def _frozen_sequence(value: Any) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(freeze_value(item) for item in value)


def _surface_on_mapping(on: SurfaceOnConfig | None) -> Mapping[str, Any]:
    if on is None:
        return freeze_mapping(None)

    payload: dict[str, Any] = {}
    for handler_name in ("success", "failure", "always"):
        handler = getattr(on, handler_name)
        if handler is None or not isinstance(handler.goto, str):
            continue
        payload[handler_name] = {"goto": handler.goto}
    return freeze_mapping(payload)


def _common_execution_config(common: SurfaceStepCommonConfig) -> StepCommonConfig:
    return StepCommonConfig(
        on=_surface_on_mapping(common.on),
        consumes=common.consumes,
        consume_bundle=common.consume_bundle,
        publishes=common.publishes,
        expected_outputs=common.expected_outputs,
        output_bundle=common.output_bundle,
        persist_artifacts_in_state=common.persist_artifacts_in_state,
        provider_session=common.provider_session,
        max_visits=common.max_visits,
        retries=common.retries,
        env=common.env,
        secrets=common.secrets,
        timeout_sec=common.timeout_sec,
        output_capture=common.output_capture,
        output_file=common.output_file,
        allow_parse_error=common.allow_parse_error,
    )


def _execution_config_for_step(step: SurfaceStep) -> Optional[ExecutableStepConfig]:
    common = _common_execution_config(step.common)

    if step.kind is SurfaceStepKind.COMMAND:
        return CommandStepConfig(
            common=common,
            command=step.command,
        )
    if step.kind is SurfaceStepKind.PROVIDER:
        return ProviderStepConfig(
            common=common,
            provider=step.provider or "",
            provider_params=step.provider_params,
            input_file=step.input_file,
            asset_file=step.asset_file,
            depends_on=step.depends_on,
            asset_depends_on=step.asset_depends_on,
            inject_output_contract=step.inject_output_contract,
            inject_consumes=step.inject_consumes,
            prompt_consumes=step.prompt_consumes,
            consumes_injection_position=step.consumes_injection_position,
        )
    if step.kind is SurfaceStepKind.ADJUDICATED_PROVIDER:
        return AdjudicatedProviderStepConfig(
            common=common,
            adjudicated_provider=step.adjudicated_provider,
            input_file=step.input_file,
            asset_file=step.asset_file,
            depends_on=step.depends_on,
            asset_depends_on=step.asset_depends_on,
            inject_output_contract=step.inject_output_contract,
            inject_consumes=step.inject_consumes,
            prompt_consumes=step.prompt_consumes,
            consumes_injection_position=step.consumes_injection_position,
        )
    if step.kind is SurfaceStepKind.WAIT_FOR:
        return WaitForStepConfig(
            common=common,
            wait_for=step.wait_for,
        )
    if step.kind is SurfaceStepKind.ASSERT:
        return AssertStepConfig(common=common)
    if step.kind is SurfaceStepKind.SET_SCALAR:
        return SetScalarStepConfig(
            common=common,
            set_scalar=step.set_scalar,
        )
    if step.kind is SurfaceStepKind.INCREMENT_SCALAR:
        return IncrementScalarStepConfig(
            common=common,
            increment_scalar=step.increment_scalar,
        )
    if step.kind is SurfaceStepKind.CALL:
        return CallStepConfig(
            common=common,
            call=step.call_alias or "",
        )
    if step.kind is SurfaceStepKind.FOR_EACH:
        return ForEachStepConfig(
            common=common,
            items=step.for_each_items,
            items_from=step.for_each_items_from,
            item_name=step.for_each_item_name,
        )
    if step.kind is SurfaceStepKind.REPEAT_UNTIL and step.repeat_until is not None:
        return RepeatUntilStepConfig(
            common=common,
            body_id=step.repeat_until.token,
            max_iterations=(
                step.repeat_until.max_iterations
                if isinstance(step.repeat_until.max_iterations, int)
                else 0
            ),
        )
    return None


def _report_kind_for_node(node: ExecutableNode) -> str:
    kind_map = {
        ExecutableNodeKind.IF_BRANCH_MARKER: "structured_if_branch",
        ExecutableNodeKind.IF_JOIN: "structured_if_join",
        ExecutableNodeKind.MATCH_CASE_MARKER: "structured_match_case",
        ExecutableNodeKind.MATCH_JOIN: "structured_match_join",
        ExecutableNodeKind.REPEAT_UNTIL_FRAME: "repeat_until",
        ExecutableNodeKind.FOR_EACH: "for_each",
        ExecutableNodeKind.CALL_BOUNDARY: "call",
        ExecutableNodeKind.FINALIZATION_STEP: "finally",
        ExecutableNodeKind.PROVIDER: "provider",
        ExecutableNodeKind.ADJUDICATED_PROVIDER: "adjudicated_provider",
        ExecutableNodeKind.COMMAND: "command",
        ExecutableNodeKind.WAIT_FOR: "wait_for",
        ExecutableNodeKind.ASSERT: "assert",
        ExecutableNodeKind.SET_SCALAR: "set_scalar",
        ExecutableNodeKind.INCREMENT_SCALAR: "increment_scalar",
    }
    return kind_map.get(node.kind, "unknown")


def _compatibility_step_definition(node: ExecutableNode) -> CompatibilityStepDefinition:
    config = getattr(node, "execution_config", None)
    common = config.common if config is not None else None
    consumes = common.consumes if common is not None else ()
    expected_outputs = common.expected_outputs if common is not None else ()
    provider_session = common.provider_session if common is not None else None
    max_visits = common.max_visits if common is not None else None
    command = config.command if isinstance(config, CommandStepConfig) else None
    provider = config.provider if isinstance(config, ProviderStepConfig) else None
    return CompatibilityStepDefinition(
        report_kind=_report_kind_for_node(node),
        command=freeze_value(command) if command is not None else None,
        provider=provider if isinstance(provider, str) else None,
        consumes=tuple(freeze_value(item) for item in consumes)
        if isinstance(consumes, (list, tuple))
        else (),
        expected_outputs=tuple(freeze_value(item) for item in expected_outputs)
        if isinstance(expected_outputs, (list, tuple))
        else (),
        max_visits=max_visits if isinstance(max_visits, int) else None,
        provider_session_enabled=isinstance(provider_session, Mapping),
        provider_session_mode=(
            provider_session.get("mode")
            if isinstance(provider_session, Mapping)
            and isinstance(provider_session.get("mode"), str)
            else None
        ),
    )


def _iteration_step_id_suffix(loop_node_id: str, nested_step_id: str) -> str:
    prefix = f"{loop_node_id}."
    if nested_step_id.startswith(prefix):
        return nested_step_id[len(prefix):]
    if "." in nested_step_id:
        return nested_step_id.split(".", 1)[1]
    return nested_step_id


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


def _bind_goto_transfer(
    reason: str,
    goto_name: Any,
    root_targets: Mapping[str, _BindingTarget],
) -> Optional[ExecutableTransfer]:
    if not isinstance(goto_name, str):
        return None
    if goto_name == "_end":
        return ExecutableTransfer(
            reason=reason,
            target_node_id=None,
            counts_as_transition=False,
        )
    target = root_targets.get(goto_name)
    if target is None:
        return None
    return ExecutableTransfer(
        reason=reason,
        target_node_id=target.node_id,
        counts_as_transition=True,
    )


def _leaf_goto_transfers(
    on: SurfaceOnConfig | None,
    root_targets: Mapping[str, _BindingTarget],
) -> Mapping[str, ExecutableTransfer]:
    if on is None:
        return MappingProxyType({})

    routed_transfers: Dict[str, ExecutableTransfer] = {}
    for handler_name, transfer_key in (
        ("success", "on_success_goto"),
        ("failure", "on_failure_goto"),
        ("always", "on_always_goto"),
    ):
        handler = getattr(on, handler_name)
        transfer = _bind_goto_transfer(
            transfer_key,
            handler.goto if handler is not None else None,
            root_targets,
        )
        if transfer is not None:
            routed_transfers[transfer_key] = transfer

    return MappingProxyType(routed_transfers)


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
                definition=contract.definition,
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
