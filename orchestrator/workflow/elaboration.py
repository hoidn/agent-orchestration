"""Raw authored workflow mapping to immutable surface AST elaboration."""

from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from .identity import assign_finalization_step_ids, assign_step_ids
from .conditions import parse_legacy_condition
from .predicates import TYPED_PREDICATE_OPERATOR_KEYS, parse_typed_predicate
from .references import SurfaceRefScopeCatalog, parse_surface_ref
from .statements import (
    branch_token,
    finally_block_token,
    is_if_statement,
    is_match_statement,
    is_repeat_until_statement,
    match_case_token,
    STRUCTURED_FINALLY_VERSION,
    normalize_branch_block,
    normalize_finally_block,
    normalize_match_case_block,
    normalize_repeat_until_block,
)
from .surface_ast import (
    ImportedWorkflowMetadata,
    PrivateExecContextBinding,
    SurfaceBranchBlock,
    SurfaceContract,
    SurfaceFinallyBlock,
    SurfaceManagedJobsConfig,
    SurfaceManagedJobsRoutes,
    SurfaceMatchCaseBlock,
    SurfaceOnConfig,
    SurfaceOnHandler,
    SurfaceRepeatUntilBlock,
    SurfaceStep,
    SurfaceStepCommonConfig,
    SurfaceStepKind,
    SurfaceWorkflow,
    WorkflowProvenance,
    freeze_mapping,
    freeze_value,
)
from .state_layout import GeneratedPathAllocation


class SurfaceWorkflowValidationBackend(Protocol):
    """Validation hooks used during the surface elaboration phase."""

    def error_count(self) -> int: ...
    def add_error(self, message: str) -> None: ...
    def version_at_least(self, version: str, minimum: str) -> bool: ...
    def validate_top_level(self, workflow: dict[str, Any], version: str) -> None: ...
    def build_finalization_catalog_steps(self, finalization: dict[str, Any] | None) -> list[dict[str, Any]]: ...
    def build_root_ref_catalog(self, steps: list[dict[str, Any]], artifacts: Any) -> dict[str, Any]: ...
    def validate_steps(
        self,
        steps: list[Any],
        version: str,
        artifacts_registry: Any,
        *,
        root_catalog: dict[str, Any],
    ) -> None: ...
    def validate_finally_block(
        self,
        finalization: dict[str, Any] | None,
        version: str,
        artifacts_registry: Any,
        root_catalog: dict[str, Any],
    ) -> None: ...
    def validate_dataflow_cross_references(self, steps: list[dict[str, Any]], artifacts: Any) -> None: ...
    def validate_workflow_outputs(
        self,
        outputs: Any,
        version: str,
        root_catalog: dict[str, Any],
    ) -> None: ...
    def validate_goto_targets(self, workflow: dict[str, Any]) -> None: ...
    def analyze_reusable_write_roots(self, workflow: dict[str, Any]) -> tuple[set[str], list[str]]: ...
    def validate_call_write_root_collisions(self, steps: Any, finally_block: Any) -> None: ...


def elaborate_surface_workflow(
    workflow: Mapping[str, Any],
    *,
    workflow_path: Any,
    imported_bundles: Mapping[str, Any],
    generated_path_allocations: tuple[GeneratedPathAllocation, ...] = (),
    lexical_checkpoint_points: tuple[Mapping[str, Any], ...] = (),
    managed_write_root_inputs: tuple[str, ...] = (),
    runtime_context_inputs: tuple[str, ...] = (),
    private_exec_context_bindings: tuple[PrivateExecContextBinding, ...] = (),
    compatibility_bridge_inputs: tuple[str, ...] = (),
    validation_backend: SurfaceWorkflowValidationBackend | None = None,
    workflow_is_imported: bool = False,
    allow_generated_step_kinds: bool = False,
) -> SurfaceWorkflow | None:
    """Elaborate one validated authored workflow into the immutable surface AST."""
    validation_workflow = deepcopy(dict(workflow))
    surface_workflow = deepcopy(dict(workflow))
    version = str(surface_workflow.get("version", ""))
    managed_inputs = tuple(managed_write_root_inputs)
    runtime_inputs = tuple(runtime_context_inputs)

    if validation_backend is not None:
        validation_backend.validate_top_level(validation_workflow, version)

        steps = validation_workflow.get("steps", [])
        finalization_present = (
            validation_backend.version_at_least(version, STRUCTURED_FINALLY_VERSION)
            and "finally" in validation_workflow
        )
        normalized_finally = None
        finally_catalog_steps: list[dict[str, Any]] = []
        if finalization_present:
            normalized_finally = normalize_finally_block(validation_workflow.get("finally"))
            finally_catalog_steps = validation_backend.build_finalization_catalog_steps(normalized_finally)

        root_catalog: dict[str, Any] = {}
        if not steps:
            validation_backend.add_error("'steps' field is required and must not be empty")
        else:
            root_catalog = validation_backend.build_root_ref_catalog(
                list(steps) + finally_catalog_steps,
                validation_workflow.get("artifacts"),
            )
            validation_backend.validate_steps(
                steps,
                version,
                validation_workflow.get("artifacts"),
                root_catalog=root_catalog,
            )
            if finalization_present:
                validation_backend.validate_finally_block(
                    normalized_finally,
                    version,
                    validation_workflow.get("artifacts"),
                    root_catalog,
                )
            if version == "1.2":
                validation_backend.validate_dataflow_cross_references(
                    _collect_all_steps(steps),
                    validation_workflow.get("artifacts"),
                )

        if "outputs" in validation_workflow:
            validation_backend.validate_workflow_outputs(
                validation_workflow["outputs"],
                version,
                root_catalog,
            )

        validation_backend.validate_goto_targets(validation_workflow)

        if validation_backend.version_at_least(version, "2.5"):
            if workflow_is_imported:
                detected_inputs, detected_errors = validation_backend.analyze_reusable_write_roots(
                    validation_workflow
                )
                managed_inputs = tuple(sorted(detected_inputs))
                for message in detected_errors:
                    validation_backend.add_error(message)
            validation_backend.validate_call_write_root_collisions(
                steps,
                validation_workflow.get("finally"),
            )

        if not allow_generated_step_kinds:
            _validate_reserved_generated_step_kinds(
                validation_workflow.get("steps"),
                validation_backend=validation_backend,
            )
            _validate_reserved_generated_step_kinds(
                validation_workflow.get("finally"),
                validation_backend=validation_backend,
            )

        if validation_backend.error_count() > 0:
            return None

    steps = surface_workflow.get("steps")
    if isinstance(steps, list):
        assign_step_ids(steps)

    finalization = assign_finalization_step_ids(surface_workflow.get("finally"))
    root_step_names = _step_names(surface_workflow.get("steps"))
    imports = MappingProxyType(
        {
            alias: ImportedWorkflowMetadata(
                alias=alias,
                workflow_path=bundle.provenance.workflow_path,
                source_root=bundle.provenance.source_root,
                generated_path_allocations=bundle.provenance.generated_path_allocations,
                managed_write_root_inputs=bundle.provenance.managed_write_root_inputs,
                runtime_context_inputs=bundle.provenance.runtime_context_inputs,
                private_exec_context_bindings=bundle.provenance.private_exec_context_bindings,
                compatibility_bridge_inputs=bundle.provenance.compatibility_bridge_inputs,
                workflow_name=bundle.surface.name,
                output_names=tuple(bundle.surface.outputs),
            )
            for alias, bundle in imported_bundles.items()
        }
    )
    provenance = WorkflowProvenance(
        workflow_path=workflow_path,
        source_root=workflow_path.parent,
        generated_path_allocations=tuple(generated_path_allocations),
        lexical_checkpoint_points=tuple(lexical_checkpoint_points),
        managed_write_root_inputs=managed_inputs,
        runtime_context_inputs=runtime_inputs,
        private_exec_context_bindings=tuple(private_exec_context_bindings),
        compatibility_bridge_inputs=tuple(
            name for name in compatibility_bridge_inputs if isinstance(name, str)
        ),
        imported_aliases=tuple(imported_bundles.keys()),
    )

    return SurfaceWorkflow(
        version=version,
        name=workflow.get("name") if isinstance(workflow.get("name"), str) else None,
        steps=_elaborate_steps(
            surface_workflow.get("steps"),
            root_step_names=root_step_names,
            self_step_names=root_step_names,
            parent_step_names=(),
            allow_generated_step_kinds=allow_generated_step_kinds,
        ),
        provenance=provenance,
        strict_flow=surface_workflow.get("strict_flow") if isinstance(surface_workflow.get("strict_flow"), bool) else True,
        context=freeze_mapping(surface_workflow.get("context")),
        providers=freeze_mapping(surface_workflow.get("providers")),
        secrets=_string_tuple(surface_workflow.get("secrets")),
        inbox_dir=_optional_string(surface_workflow.get("inbox_dir")),
        processed_dir=_optional_string(surface_workflow.get("processed_dir")),
        failed_dir=_optional_string(surface_workflow.get("failed_dir")),
        task_extension=_optional_string(surface_workflow.get("task_extension")),
        max_transitions=surface_workflow.get("max_transitions") if isinstance(surface_workflow.get("max_transitions"), int) else None,
        artifacts=_parse_contracts(surface_workflow.get("artifacts"), SurfaceRefScopeCatalog(root_step_names=root_step_names)),
        inputs=_parse_contracts(surface_workflow.get("inputs"), SurfaceRefScopeCatalog(root_step_names=root_step_names)),
        outputs=_parse_contracts(surface_workflow.get("outputs"), SurfaceRefScopeCatalog(root_step_names=root_step_names)),
        imports=imports,
        finalization=_elaborate_finalization(
            finalization,
            root_step_names=root_step_names,
            allow_generated_step_kinds=allow_generated_step_kinds,
        ),
        result_guidance=(
            freeze_mapping(surface_workflow["result_guidance"])
            if isinstance(surface_workflow.get("result_guidance"), Mapping)
            else None
        ),
    )


def _elaborate_finalization(
    finalization: Any,
    *,
    root_step_names: tuple[str, ...],
    allow_generated_step_kinds: bool,
) -> SurfaceFinallyBlock | None:
    normalized = normalize_finally_block(finalization)
    if normalized is None:
        return None
    steps = normalized.get("steps")
    if not isinstance(steps, list):
        return None
    token = finally_block_token(normalized)
    step_names = _step_names(steps)
    return SurfaceFinallyBlock(
        token=token,
        step_id=f"root.finally.{token}",
        steps=_elaborate_steps(
            steps,
            root_step_names=root_step_names,
            self_step_names=step_names,
            parent_step_names=(),
            allow_generated_step_kinds=allow_generated_step_kinds,
        ),
    )


def _elaborate_steps(
    steps: Any,
    *,
    root_step_names: tuple[str, ...],
    self_step_names: tuple[str, ...],
    parent_step_names: tuple[str, ...],
    allow_generated_step_kinds: bool,
) -> tuple[SurfaceStep, ...]:
    if not isinstance(steps, list):
        return ()
    return tuple(
        _elaborate_step(
            step,
            root_step_names=root_step_names,
            self_step_names=self_step_names,
            parent_step_names=parent_step_names,
            allow_generated_step_kinds=allow_generated_step_kinds,
        )
        for step in steps
        if isinstance(step, dict)
    )


def _elaborate_step(
    step: Mapping[str, Any],
    *,
    root_step_names: tuple[str, ...],
    self_step_names: tuple[str, ...],
    parent_step_names: tuple[str, ...],
    allow_generated_step_kinds: bool,
) -> SurfaceStep:
    catalog = SurfaceRefScopeCatalog(
        root_step_names=root_step_names,
        self_step_names=self_step_names,
        parent_step_names=parent_step_names,
    )
    kind = _surface_step_kind(step, allow_generated_step_kinds=allow_generated_step_kinds)
    call_bindings = {}
    references = []
    common = _parse_surface_common_config(step)

    when_predicate = _parse_predicate(step.get("when"), catalog)
    assert_predicate = _parse_predicate(step.get("assert"), catalog)

    if kind is SurfaceStepKind.CALL:
        bindings = step.get("with")
        if isinstance(bindings, Mapping):
            for input_name, bound_value in bindings.items():
                if isinstance(bound_value, Mapping) and set(bound_value.keys()) == {"ref"}:
                    parsed_ref = parse_surface_ref(bound_value["ref"], catalog)
                    call_bindings[str(input_name)] = parsed_ref
                    references.append(parsed_ref)
                else:
                    call_bindings[str(input_name)] = freeze_value(bound_value)

    if kind is SurfaceStepKind.IF:
        condition = parse_typed_predicate(step.get("if", {}), catalog)
        then_branch = _elaborate_branch(
            step.get("then"),
            branch_name="then",
            statement_step_id=str(step.get("step_id", "")),
            root_step_names=root_step_names,
            parent_step_names=self_step_names,
            allow_generated_step_kinds=allow_generated_step_kinds,
        )
        else_branch = _elaborate_branch(
            step.get("else"),
            branch_name="else",
            statement_step_id=str(step.get("step_id", "")),
            root_step_names=root_step_names,
            parent_step_names=self_step_names,
            allow_generated_step_kinds=allow_generated_step_kinds,
        )
        return SurfaceStep(
            name=str(step.get("name", "")),
            step_id=str(step.get("step_id", "")),
            kind=kind,
            authored_id=step.get("id") if isinstance(step.get("id"), str) else None,
            common=common,
            when_predicate=when_predicate,
            assert_predicate=assert_predicate,
            if_condition=condition,
            then_branch=then_branch,
            else_branch=else_branch,
        )

    if kind is SurfaceStepKind.MATCH:
        match = step.get("match")
        match_cases = {}
        if isinstance(match, Mapping):
            cases = match.get("cases")
            if isinstance(cases, Mapping):
                for case_name, authored_case in cases.items():
                    case_block = _elaborate_match_case(
                        authored_case,
                        case_name=str(case_name),
                        statement_step_id=str(step.get("step_id", "")),
                        root_step_names=root_step_names,
                        parent_step_names=self_step_names,
                        allow_generated_step_kinds=allow_generated_step_kinds,
                    )
                    if case_block is not None:
                        match_cases[str(case_name)] = case_block
        selector_ref = None
        if isinstance(match, Mapping) and isinstance(match.get("ref"), str):
            selector_ref = parse_surface_ref(match["ref"], catalog)
        return SurfaceStep(
            name=str(step.get("name", "")),
            step_id=str(step.get("step_id", "")),
            kind=kind,
            authored_id=step.get("id") if isinstance(step.get("id"), str) else None,
            when_predicate=when_predicate,
            match_ref=selector_ref,
            match_cases=MappingProxyType(match_cases),
        )

    if kind is SurfaceStepKind.REPEAT_UNTIL:
        repeat_until = _elaborate_repeat_until(
            step,
            root_step_names=root_step_names,
            parent_step_names=self_step_names,
            allow_generated_step_kinds=allow_generated_step_kinds,
        )
        return SurfaceStep(
            name=str(step.get("name", "")),
            step_id=str(step.get("step_id", "")),
            kind=kind,
            authored_id=step.get("id") if isinstance(step.get("id"), str) else None,
            common=common,
            when_predicate=when_predicate,
            repeat_until=repeat_until,
        )

    if kind is SurfaceStepKind.FOR_EACH:
        for_each = step.get("for_each")
        nested_steps = for_each.get("steps") if isinstance(for_each, Mapping) else None
        nested_names = _step_names(nested_steps)
        items_from = (
            for_each.get("items_from")
            if isinstance(for_each, Mapping) and isinstance(for_each.get("items_from"), str)
            else None
        )
        items = ()
        if isinstance(for_each, Mapping) and items_from is None:
            items = _frozen_sequence(for_each.get("items"))
        return SurfaceStep(
            name=str(step.get("name", "")),
            step_id=str(step.get("step_id", "")),
            kind=kind,
            authored_id=step.get("id") if isinstance(step.get("id"), str) else None,
            common=common,
            when_predicate=when_predicate,
            assert_predicate=assert_predicate,
            for_each_items=items,
            for_each_items_from=items_from,
            for_each_item_name=(
                for_each.get("as")
                if isinstance(for_each, Mapping) and isinstance(for_each.get("as"), str)
                else "item"
            ),
            for_each_steps=_elaborate_steps(
                nested_steps,
                root_step_names=root_step_names,
                self_step_names=nested_names,
                parent_step_names=self_step_names,
                allow_generated_step_kinds=allow_generated_step_kinds,
            ),
        )

    return SurfaceStep(
        name=str(step.get("name", "")),
        step_id=str(step.get("step_id", "")),
        kind=kind,
        authored_id=step.get("id") if isinstance(step.get("id"), str) else None,
        common=common,
        when_predicate=when_predicate,
        assert_predicate=assert_predicate,
        references=tuple(references),
        command=_frozen_command(step.get("command")) if kind is SurfaceStepKind.COMMAND else (),
        provider=step.get("provider") if kind is SurfaceStepKind.PROVIDER and isinstance(step.get("provider"), str) else None,
        provider_params=freeze_value(step["provider_params"]) if kind is SurfaceStepKind.PROVIDER and "provider_params" in step else None,
        provider_call_policy=(
            freeze_mapping(step["provider_call_policy"])
            if kind is SurfaceStepKind.PROVIDER and "provider_call_policy" in step
            else None
        ),
        managed_jobs=(
            _parse_surface_managed_jobs_config(step.get("managed_jobs"))
            if kind is SurfaceStepKind.PROVIDER
            else None
        ),
        adjudicated_provider=(
            freeze_mapping(step.get("adjudicated_provider"))
            if kind is SurfaceStepKind.ADJUDICATED_PROVIDER
            else freeze_mapping(None)
        ),
        input_file=(
            freeze_value(step["input_file"])
            if kind in {SurfaceStepKind.PROVIDER, SurfaceStepKind.ADJUDICATED_PROVIDER} and "input_file" in step
            else None
        ),
        asset_file=(
            freeze_value(step["asset_file"])
            if kind in {SurfaceStepKind.PROVIDER, SurfaceStepKind.ADJUDICATED_PROVIDER} and "asset_file" in step
            else None
        ),
        depends_on=(
            freeze_mapping(step.get("depends_on"))
            if kind in {SurfaceStepKind.PROVIDER, SurfaceStepKind.ADJUDICATED_PROVIDER}
            else freeze_mapping(None)
        ),
        asset_depends_on=(
            _frozen_sequence(step.get("asset_depends_on"))
            if kind in {SurfaceStepKind.PROVIDER, SurfaceStepKind.ADJUDICATED_PROVIDER}
            else ()
        ),
        inject_output_contract=(
            step.get("inject_output_contract")
            if kind in {SurfaceStepKind.PROVIDER, SurfaceStepKind.ADJUDICATED_PROVIDER}
            and isinstance(step.get("inject_output_contract"), bool)
            else None
        ),
        inject_consumes=(
            step.get("inject_consumes")
            if kind in {SurfaceStepKind.PROVIDER, SurfaceStepKind.ADJUDICATED_PROVIDER}
            and isinstance(step.get("inject_consumes"), bool)
            else None
        ),
        prompt_consumes=(
            _frozen_sequence(step["prompt_consumes"])
            if kind in {SurfaceStepKind.PROVIDER, SurfaceStepKind.ADJUDICATED_PROVIDER}
            and "prompt_consumes" in step
            else None
        ),
        typed_prompt_inputs=(
            _frozen_sequence(step.get("typed_prompt_inputs"))
            if kind is SurfaceStepKind.PROVIDER and "typed_prompt_inputs" in step
            else ()
        ),
        consumes_injection_position=(
            step.get("consumes_injection_position")
            if kind in {SurfaceStepKind.PROVIDER, SurfaceStepKind.ADJUDICATED_PROVIDER}
            and isinstance(step.get("consumes_injection_position"), str)
            else None
        ),
        wait_for=freeze_mapping(step.get("wait_for")) if kind is SurfaceStepKind.WAIT_FOR else freeze_mapping(None),
        set_scalar=freeze_mapping(step.get("set_scalar")) if kind is SurfaceStepKind.SET_SCALAR else freeze_mapping(None),
        resource_transition=(
            freeze_mapping(step.get("resource_transition"))
            if kind is SurfaceStepKind.RESOURCE_TRANSITION
            else freeze_mapping(None)
        ),
        pure_projection=(
            freeze_mapping(step.get("pure_projection"))
            if kind is SurfaceStepKind.PURE_PROJECTION
            else freeze_mapping(None)
        ),
        materialize_view=(
            freeze_mapping(step.get("materialize_view"))
            if kind is SurfaceStepKind.MATERIALIZE_VIEW
            else freeze_mapping(None)
        ),
        increment_scalar=(
            freeze_mapping(step.get("increment_scalar"))
            if kind is SurfaceStepKind.INCREMENT_SCALAR
            else freeze_mapping(None)
        ),
        materialize_artifacts=(
            freeze_mapping(step.get("materialize_artifacts"))
            if kind is SurfaceStepKind.MATERIALIZE_ARTIFACTS
            else freeze_mapping(None)
        ),
        select_variant_output=(
            freeze_mapping(step.get("select_variant_output"))
            if kind is SurfaceStepKind.SELECT_VARIANT_OUTPUT
            else freeze_mapping(None)
        ),
        call_alias=step.get("call") if kind is SurfaceStepKind.CALL and isinstance(step.get("call"), str) else None,
        call_bindings=MappingProxyType(call_bindings),
    )


def _elaborate_branch(
    branch: Any,
    *,
    branch_name: str,
    statement_step_id: str,
    root_step_names: tuple[str, ...],
    parent_step_names: tuple[str, ...],
    allow_generated_step_kinds: bool,
) -> SurfaceBranchBlock | None:
    normalized = normalize_branch_block(branch, branch_name)
    if normalized is None:
        return None
    steps = normalized.get("steps")
    if not isinstance(steps, list):
        return None
    token = branch_token(branch_name, normalized)
    branch_step_names = _step_names(steps)
    branch_catalog = SurfaceRefScopeCatalog(
        root_step_names=root_step_names,
        self_step_names=branch_step_names,
        parent_step_names=parent_step_names,
    )
    return SurfaceBranchBlock(
        branch_name=branch_name,
        token=token,
        step_id=f"{statement_step_id}.{token}",
        steps=_elaborate_steps(
            steps,
            root_step_names=root_step_names,
            self_step_names=branch_step_names,
            parent_step_names=parent_step_names,
            allow_generated_step_kinds=allow_generated_step_kinds,
        ),
        outputs=_parse_contracts(normalized.get("outputs"), branch_catalog),
    )


def _elaborate_match_case(
    case_block: Any,
    *,
    case_name: str,
    statement_step_id: str,
    root_step_names: tuple[str, ...],
    parent_step_names: tuple[str, ...],
    allow_generated_step_kinds: bool,
) -> SurfaceMatchCaseBlock | None:
    normalized = normalize_match_case_block(case_block, case_name)
    if normalized is None:
        return None
    steps = normalized.get("steps")
    if not isinstance(steps, list):
        return None
    token = match_case_token(case_name, normalized)
    case_step_names = _step_names(steps)
    case_catalog = SurfaceRefScopeCatalog(
        root_step_names=root_step_names,
        self_step_names=case_step_names,
        parent_step_names=parent_step_names,
    )
    return SurfaceMatchCaseBlock(
        case_name=case_name,
        token=token,
        step_id=f"{statement_step_id}.{token}",
        steps=_elaborate_steps(
            steps,
            root_step_names=root_step_names,
            self_step_names=case_step_names,
            parent_step_names=parent_step_names,
            allow_generated_step_kinds=allow_generated_step_kinds,
        ),
        outputs=_parse_contracts(normalized.get("outputs"), case_catalog),
    )


def _elaborate_repeat_until(
    step: Mapping[str, Any],
    *,
    root_step_names: tuple[str, ...],
    parent_step_names: tuple[str, ...],
    allow_generated_step_kinds: bool,
) -> SurfaceRepeatUntilBlock | None:
    block = normalize_repeat_until_block(step.get("repeat_until"))
    if block is None:
        return None
    steps = block.get("steps")
    if not isinstance(steps, list):
        return None
    token = str(block.get("id") or "repeat_until")
    output_specs = block.get("outputs") if isinstance(block.get("outputs"), Mapping) else {}
    on_exhausted = block.get("on_exhausted")
    on_exhausted_outputs = (
        on_exhausted.get("outputs")
        if isinstance(on_exhausted, Mapping) and isinstance(on_exhausted.get("outputs"), Mapping)
        else {}
    )
    body_step_names = _step_names(steps)
    body_catalog = SurfaceRefScopeCatalog(
        root_step_names=root_step_names,
        self_step_names=body_step_names,
        parent_step_names=parent_step_names,
        output_names=tuple(str(name) for name in output_specs.keys()),
    )
    return SurfaceRepeatUntilBlock(
        token=token,
        step_id=f"{step.get('step_id')}.{token}",
        steps=_elaborate_steps(
            steps,
            root_step_names=root_step_names,
            self_step_names=body_step_names,
            parent_step_names=parent_step_names,
            allow_generated_step_kinds=allow_generated_step_kinds,
        ),
        outputs=_parse_contracts(output_specs, body_catalog),
        condition=parse_typed_predicate(block.get("condition", {}), body_catalog),
        max_iterations=block.get("max_iterations") if isinstance(block.get("max_iterations"), int) else None,
        on_exhausted_outputs=freeze_value(on_exhausted_outputs),
    )


def _parse_predicate(node: Any, catalog: SurfaceRefScopeCatalog) -> Any:
    if not isinstance(node, Mapping):
        return None
    if not any(key in node for key in TYPED_PREDICATE_OPERATOR_KEYS):
        return parse_legacy_condition(dict(node))
    return parse_typed_predicate(dict(node), catalog)


def _parse_surface_common_config(step: Mapping[str, Any]) -> SurfaceStepCommonConfig:
    return SurfaceStepCommonConfig(
        on=_parse_surface_on_config(step.get("on")),
        consumes=_frozen_sequence(step.get("consumes")),
        consume_bundle=freeze_value(step["consume_bundle"]) if "consume_bundle" in step else None,
        publishes=_frozen_sequence(step.get("publishes")),
        expected_outputs=_frozen_sequence(step.get("expected_outputs")),
        output_bundle=freeze_value(step["output_bundle"]) if "output_bundle" in step else None,
        variant_output=freeze_value(step["variant_output"]) if "variant_output" in step else None,
        pre_snapshot=freeze_value(step["pre_snapshot"]) if "pre_snapshot" in step else None,
        requires_variant=freeze_value(step["requires_variant"]) if "requires_variant" in step else None,
        persist_artifacts_in_state=(
            step.get("persist_artifacts_in_state")
            if isinstance(step.get("persist_artifacts_in_state"), bool)
            else None
        ),
        provider_session=(
            freeze_mapping(step.get("provider_session"))
            if isinstance(step.get("provider_session"), Mapping)
            else None
        ),
        max_visits=step.get("max_visits") if isinstance(step.get("max_visits"), int) else None,
        retries=freeze_value(step["retries"]) if "retries" in step else None,
        env=freeze_mapping(step.get("env")) if isinstance(step.get("env"), Mapping) else None,
        secrets=_string_tuple(step.get("secrets")),
        timeout_sec=(
            step.get("timeout_sec")
            if isinstance(step.get("timeout_sec"), (int, float))
            else None
        ),
        output_capture=freeze_value(step["output_capture"]) if "output_capture" in step else None,
        output_file=freeze_value(step["output_file"]) if "output_file" in step else None,
        allow_parse_error=(
            step.get("allow_parse_error")
            if isinstance(step.get("allow_parse_error"), bool)
            else None
        ),
    )


def _parse_surface_on_config(node: Any) -> SurfaceOnConfig | None:
    if not isinstance(node, Mapping):
        return None
    success = _parse_surface_on_handler(node.get("success"))
    failure = _parse_surface_on_handler(node.get("failure"))
    always = _parse_surface_on_handler(node.get("always"))
    if success is None and failure is None and always is None:
        return None
    return SurfaceOnConfig(success=success, failure=failure, always=always)


def _parse_surface_on_handler(node: Any) -> SurfaceOnHandler | None:
    if not isinstance(node, Mapping):
        return None
    goto = node.get("goto")
    if not isinstance(goto, str):
        return None
    return SurfaceOnHandler(goto=goto)


def _parse_surface_managed_jobs_config(node: Any) -> SurfaceManagedJobsConfig | None:
    if not isinstance(node, Mapping):
        return None
    routes = node.get("on")
    if not isinstance(routes, Mapping):
        return None
    policy = node.get("policy")
    watch_roots = node.get("watch_roots")
    backend = node.get("backend")
    poll_budget_sec = node.get("poll_budget_sec")
    route_values = {
        name: routes.get(name)
        for name in ("complete", "failed", "invalid", "outstanding")
    }
    if (
        not isinstance(policy, str)
        or not isinstance(watch_roots, (list, tuple))
        or not all(isinstance(item, str) for item in watch_roots)
        or not isinstance(backend, str)
        or type(poll_budget_sec) is not int
        or not all(isinstance(value, str) for value in route_values.values())
    ):
        return None
    return SurfaceManagedJobsConfig(
        policy=policy,
        watch_roots=tuple(watch_roots),
        backend=backend,
        poll_budget_sec=poll_budget_sec,
        on=SurfaceManagedJobsRoutes(
            complete=route_values["complete"],
            failed=route_values["failed"],
            invalid=route_values["invalid"],
            outstanding=route_values["outstanding"],
        ),
    )


def _parse_contracts(
    specs: Any,
    catalog: SurfaceRefScopeCatalog,
) -> Mapping[str, SurfaceContract]:
    if not isinstance(specs, Mapping):
        return MappingProxyType({})

    contracts = {}
    for name, spec in specs.items():
        if not isinstance(name, str) or not isinstance(spec, Mapping):
            continue
        binding = spec.get("from")
        from_ref = None
        if isinstance(binding, Mapping) and isinstance(binding.get("ref"), str):
            from_ref = parse_surface_ref(binding["ref"], catalog)
        contracts[name] = SurfaceContract(
            name=name,
            kind=spec.get("kind") if isinstance(spec.get("kind"), str) else None,
            value_type=spec.get("type") if isinstance(spec.get("type"), str) else None,
            definition=freeze_mapping(spec),
            from_ref=from_ref,
        )
    return MappingProxyType(contracts)


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _frozen_sequence(value: Any) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(freeze_value(item) for item in value)


def _frozen_command(value: Any) -> Any:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(freeze_value(item) for item in value)
    return ()


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _step_names(steps: Any) -> tuple[str, ...]:
    if not isinstance(steps, list):
        return ()
    return tuple(
        step["name"]
        for step in steps
        if isinstance(step, Mapping) and isinstance(step.get("name"), str)
    )


def _collect_all_steps(steps: list[Any]) -> list[dict[str, Any]]:
    """Collect authored steps across nested control-flow blocks for validation hooks."""
    collected: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        collected.append(step)
        if is_if_statement(step):
            for branch_name in ("then", "else"):
                branch = normalize_branch_block(step.get(branch_name), branch_name)
                nested = branch.get("steps") if isinstance(branch, dict) else None
                if isinstance(nested, list):
                    collected.extend(_collect_all_steps(nested))
        if is_match_statement(step):
            match = step.get("match")
            cases = match.get("cases") if isinstance(match, dict) else None
            if isinstance(cases, dict):
                for case_name, authored_case in cases.items():
                    case_block = normalize_match_case_block(authored_case, str(case_name))
                    nested = case_block.get("steps") if isinstance(case_block, dict) else None
                    if isinstance(nested, list):
                        collected.extend(_collect_all_steps(nested))
        for_each = step.get("for_each")
        if isinstance(for_each, dict):
            nested = for_each.get("steps")
            if isinstance(nested, list):
                collected.extend(_collect_all_steps(nested))
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            nested = repeat_until.get("steps")
            if isinstance(nested, list):
                collected.extend(_collect_all_steps(nested))
    return collected


def _surface_step_kind(
    step: Mapping[str, Any],
    *,
    allow_generated_step_kinds: bool,
) -> SurfaceStepKind:
    if is_if_statement(step):
        return SurfaceStepKind.IF
    if is_match_statement(step):
        return SurfaceStepKind.MATCH
    if is_repeat_until_statement(step):
        return SurfaceStepKind.REPEAT_UNTIL
    if "for_each" in step:
        return SurfaceStepKind.FOR_EACH
    if "call" in step:
        return SurfaceStepKind.CALL
    if "adjudicated_provider" in step:
        return SurfaceStepKind.ADJUDICATED_PROVIDER
    if "provider" in step:
        return SurfaceStepKind.PROVIDER
    if "command" in step:
        return SurfaceStepKind.COMMAND
    if "wait_for" in step:
        return SurfaceStepKind.WAIT_FOR
    if "assert" in step:
        return SurfaceStepKind.ASSERT
    if "set_scalar" in step:
        return SurfaceStepKind.SET_SCALAR
    if "resource_transition" in step:
        if not allow_generated_step_kinds:
            raise ValueError("resource_transition is compiler-generated only and cannot appear in authored workflows")
        return SurfaceStepKind.RESOURCE_TRANSITION
    if "pure_projection" in step:
        if not allow_generated_step_kinds:
            raise ValueError("pure_projection is compiler-generated only and cannot appear in authored workflows")
        return SurfaceStepKind.PURE_PROJECTION
    if "materialize_view" in step:
        if not allow_generated_step_kinds:
            raise ValueError("materialize_view is compiler-generated only and cannot appear in authored workflows")
        return SurfaceStepKind.MATERIALIZE_VIEW
    if "increment_scalar" in step:
        return SurfaceStepKind.INCREMENT_SCALAR
    if "materialize_artifacts" in step:
        return SurfaceStepKind.MATERIALIZE_ARTIFACTS
    if "select_variant_output" in step:
        return SurfaceStepKind.SELECT_VARIANT_OUTPUT
    raise ValueError(f"Unsupported surface step shape for '{step.get('name', '<unnamed>')}'")


def _validate_reserved_generated_step_kinds(
    node: Any,
    *,
    validation_backend: SurfaceWorkflowValidationBackend,
) -> None:
    def visit_steps(steps: Any) -> None:
        if not isinstance(steps, list):
            return
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            step_name = step.get("name", "<unnamed>")
            if "pure_projection" in step:
                validation_backend.add_error(
                    f"Step '{step_name}': pure_projection is compiler-generated only and cannot appear in authored workflows"
                )
            if "materialize_view" in step:
                validation_backend.add_error(
                    f"Step '{step_name}': materialize_view is compiler-generated only and cannot appear in authored workflows"
                )
            if "resource_transition" in step:
                validation_backend.add_error(
                    f"Step '{step_name}': resource_transition is compiler-generated only and cannot appear in authored workflows"
                )
            if is_if_statement(step):
                visit_block(step.get("then"), "then")
                visit_block(step.get("else"), "else")
            if is_match_statement(step):
                match_node = step.get("match")
                cases = match_node.get("cases") if isinstance(match_node, Mapping) else None
                if isinstance(cases, Mapping):
                    for case_name, authored_case in cases.items():
                        visit_block(authored_case, str(case_name))
            repeat_until = normalize_repeat_until_block(step.get("repeat_until"))
            if isinstance(repeat_until, Mapping):
                visit_steps(repeat_until.get("steps"))
            for_each = step.get("for_each")
            if isinstance(for_each, Mapping):
                visit_steps(for_each.get("steps"))

    def visit_block(block: Any, branch_name: str) -> None:
        normalized = normalize_branch_block(block, branch_name)
        if isinstance(normalized, Mapping):
            visit_steps(normalized.get("steps"))
            return
        case_block = normalize_match_case_block(block, branch_name)
        if isinstance(case_block, Mapping):
            visit_steps(case_block.get("steps"))
            return
        final_block = normalize_finally_block(block)
        if isinstance(final_block, Mapping):
            visit_steps(final_block.get("steps"))

    visit_block(node, "finally")
    visit_steps(node)
