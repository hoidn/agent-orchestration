"""Raw authored workflow mapping to immutable surface AST elaboration."""

from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType
from typing import Any, Mapping

from .identity import assign_finalization_step_ids, assign_step_ids
from .predicates import TYPED_PREDICATE_OPERATOR_KEYS, parse_typed_predicate
from .references import SurfaceRefScopeCatalog, parse_surface_ref
from .statements import (
    branch_token,
    finally_block_token,
    is_if_statement,
    is_match_statement,
    is_repeat_until_statement,
    match_case_token,
    normalize_branch_block,
    normalize_finally_block,
    normalize_match_case_block,
    normalize_repeat_until_block,
)
from .surface_ast import (
    ImportedWorkflowMetadata,
    SurfaceBranchBlock,
    SurfaceContract,
    SurfaceFinallyBlock,
    SurfaceMatchCaseBlock,
    SurfaceRepeatUntilBlock,
    SurfaceStep,
    SurfaceStepKind,
    SurfaceWorkflow,
    WorkflowProvenance,
    freeze_mapping,
    freeze_value,
)


def elaborate_surface_workflow(
    workflow: Mapping[str, Any],
    *,
    workflow_path: Any,
    imported_bundles: Mapping[str, Any],
    managed_write_root_inputs: tuple[str, ...] = (),
) -> SurfaceWorkflow:
    """Elaborate one validated authored workflow into the immutable surface AST."""
    mutable_workflow = deepcopy(dict(workflow))
    steps = mutable_workflow.get("steps")
    if isinstance(steps, list):
        assign_step_ids(steps)

    finalization = assign_finalization_step_ids(mutable_workflow.get("finally"))
    root_step_names = _step_names(mutable_workflow.get("steps"))
    imports = MappingProxyType(
        {
            alias: ImportedWorkflowMetadata(
                alias=alias,
                workflow_path=bundle.provenance.workflow_path,
                source_root=bundle.provenance.source_root,
                managed_write_root_inputs=bundle.provenance.managed_write_root_inputs,
                workflow_name=bundle.surface.name,
            )
            for alias, bundle in imported_bundles.items()
        }
    )
    provenance = WorkflowProvenance(
        workflow_path=workflow_path,
        source_root=workflow_path.parent,
        managed_write_root_inputs=managed_write_root_inputs,
        imported_aliases=tuple(imported_bundles.keys()),
    )

    return SurfaceWorkflow(
        version=str(workflow.get("version", "")),
        name=workflow.get("name") if isinstance(workflow.get("name"), str) else None,
        steps=_elaborate_steps(
            mutable_workflow.get("steps"),
            root_step_names=root_step_names,
            self_step_names=root_step_names,
            parent_step_names=(),
        ),
        provenance=provenance,
        artifacts=_parse_contracts(workflow.get("artifacts"), SurfaceRefScopeCatalog(root_step_names=root_step_names)),
        inputs=_parse_contracts(workflow.get("inputs"), SurfaceRefScopeCatalog(root_step_names=root_step_names)),
        outputs=_parse_contracts(workflow.get("outputs"), SurfaceRefScopeCatalog(root_step_names=root_step_names)),
        imports=imports,
        finalization=_elaborate_finalization(finalization, root_step_names=root_step_names),
        raw=freeze_mapping(workflow),
    )


def _elaborate_finalization(
    finalization: Any,
    *,
    root_step_names: tuple[str, ...],
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
        ),
        raw=freeze_mapping(finalization if isinstance(finalization, Mapping) else normalized),
    )


def _elaborate_steps(
    steps: Any,
    *,
    root_step_names: tuple[str, ...],
    self_step_names: tuple[str, ...],
    parent_step_names: tuple[str, ...],
) -> tuple[SurfaceStep, ...]:
    if not isinstance(steps, list):
        return ()
    return tuple(
        _elaborate_step(
            step,
            root_step_names=root_step_names,
            self_step_names=self_step_names,
            parent_step_names=parent_step_names,
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
) -> SurfaceStep:
    catalog = SurfaceRefScopeCatalog(
        root_step_names=root_step_names,
        self_step_names=self_step_names,
        parent_step_names=parent_step_names,
    )
    kind = _surface_step_kind(step)
    call_bindings = {}
    references = []

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
        )
        else_branch = _elaborate_branch(
            step.get("else"),
            branch_name="else",
            statement_step_id=str(step.get("step_id", "")),
            root_step_names=root_step_names,
            parent_step_names=self_step_names,
        )
        return SurfaceStep(
            name=str(step.get("name", "")),
            step_id=str(step.get("step_id", "")),
            kind=kind,
            authored_id=step.get("id") if isinstance(step.get("id"), str) else None,
            raw=freeze_mapping(step),
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
            raw=freeze_mapping(step),
            match_ref=selector_ref,
            match_cases=MappingProxyType(match_cases),
        )

    if kind is SurfaceStepKind.REPEAT_UNTIL:
        repeat_until = _elaborate_repeat_until(
            step,
            root_step_names=root_step_names,
            parent_step_names=self_step_names,
        )
        return SurfaceStep(
            name=str(step.get("name", "")),
            step_id=str(step.get("step_id", "")),
            kind=kind,
            authored_id=step.get("id") if isinstance(step.get("id"), str) else None,
            raw=freeze_mapping(step),
            repeat_until=repeat_until,
        )

    if kind is SurfaceStepKind.FOR_EACH:
        for_each = step.get("for_each")
        nested_steps = for_each.get("steps") if isinstance(for_each, Mapping) else None
        nested_names = _step_names(nested_steps)
        return SurfaceStep(
            name=str(step.get("name", "")),
            step_id=str(step.get("step_id", "")),
            kind=kind,
            authored_id=step.get("id") if isinstance(step.get("id"), str) else None,
            raw=freeze_mapping(step),
            when_predicate=when_predicate,
            assert_predicate=assert_predicate,
            for_each_steps=_elaborate_steps(
                nested_steps,
                root_step_names=root_step_names,
                self_step_names=nested_names,
                parent_step_names=self_step_names,
            ),
        )

    return SurfaceStep(
        name=str(step.get("name", "")),
        step_id=str(step.get("step_id", "")),
        kind=kind,
        authored_id=step.get("id") if isinstance(step.get("id"), str) else None,
        raw=freeze_mapping(step),
        when_predicate=when_predicate,
        assert_predicate=assert_predicate,
        references=tuple(references),
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
        ),
        outputs=_parse_contracts(normalized.get("outputs"), branch_catalog),
        raw=freeze_mapping(branch if isinstance(branch, Mapping) else normalized),
    )


def _elaborate_match_case(
    case_block: Any,
    *,
    case_name: str,
    statement_step_id: str,
    root_step_names: tuple[str, ...],
    parent_step_names: tuple[str, ...],
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
        ),
        outputs=_parse_contracts(normalized.get("outputs"), case_catalog),
        raw=freeze_mapping(case_block if isinstance(case_block, Mapping) else normalized),
    )


def _elaborate_repeat_until(
    step: Mapping[str, Any],
    *,
    root_step_names: tuple[str, ...],
    parent_step_names: tuple[str, ...],
) -> SurfaceRepeatUntilBlock | None:
    block = normalize_repeat_until_block(step.get("repeat_until"))
    if block is None:
        return None
    steps = block.get("steps")
    if not isinstance(steps, list):
        return None
    token = str(block.get("id") or "repeat_until")
    output_specs = block.get("outputs") if isinstance(block.get("outputs"), Mapping) else {}
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
        ),
        outputs=_parse_contracts(output_specs, body_catalog),
        condition=parse_typed_predicate(block.get("condition", {}), body_catalog),
        max_iterations=block.get("max_iterations") if isinstance(block.get("max_iterations"), int) else None,
        raw=freeze_mapping(block),
    )


def _parse_predicate(node: Any, catalog: SurfaceRefScopeCatalog) -> Any:
    if not isinstance(node, Mapping):
        return None
    if not any(key in node for key in TYPED_PREDICATE_OPERATOR_KEYS):
        return None
    return parse_typed_predicate(dict(node), catalog)


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
            raw=freeze_mapping(spec),
            from_ref=from_ref,
        )
    return MappingProxyType(contracts)


def _step_names(steps: Any) -> tuple[str, ...]:
    if not isinstance(steps, list):
        return ()
    return tuple(
        step["name"]
        for step in steps
        if isinstance(step, Mapping) and isinstance(step.get("name"), str)
    )


def _surface_step_kind(step: Mapping[str, Any]) -> SurfaceStepKind:
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
    if "increment_scalar" in step:
        return SurfaceStepKind.INCREMENT_SCALAR
    raise ValueError(f"Unsupported surface step shape for '{step.get('name', '<unnamed>')}'")
