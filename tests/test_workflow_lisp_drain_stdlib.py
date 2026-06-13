import json
from pathlib import Path
import re
import shutil

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.executable_ir import validate_executable_workflow
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.lowering import _managed_write_root_bindings, _observed_statement_families
from orchestrator.workflow_lisp.reader import read_sexpr_file, read_sexpr_text
from orchestrator.workflow_lisp.stdlib_contracts import STDLIB_LOWERING_CONTRACTS_BY_FORM
from orchestrator.workflow_lisp.syntax import SyntaxNode, build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.wcc.route import LoweringRoute
from orchestrator.workflow_lisp.workflows import ExternEnvironment
from orchestrator.workflow_lisp.workflows import (
    CertifiedAdapterBinding,
    build_command_boundary_environment,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)
from tests.workflow_bundle_helpers import bundle_context_dict


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_DRAIN_FIXTURE = FIXTURES / "valid" / "drain_stdlib_backlog_drain.orc"
VALID_STDLIB_DRAIN_FIXTURE = FIXTURES / "valid" / "drain_stdlib_backlog_drain_stdlib.orc"
INVALID_SIGNATURE_FIXTURE = FIXTURES / "invalid" / "backlog_drain_workflow_ref_signature_invalid.orc"
INVALID_UNION_BOUNDARY_FIXTURE = FIXTURES / "invalid" / "backlog_drain_union_call_boundary_invalid.orc"
INVALID_STDLIB_DRAIN_NON_SYMBOL_CALLEE_FIXTURE = (
    FIXTURES / "invalid" / "drain_stdlib_backlog_drain_non_symbol_callee.orc"
)
INVALID_STDLIB_DRAIN_VIEW_AUTHORITY_FIXTURE = (
    FIXTURES / "invalid" / "drain_stdlib_materialized_view_authority_invalid.orc"
)


def _build_syntax_module(path: Path):
    return build_syntax_module(read_sexpr_file(path))


def _compile_definition_module(path: Path):
    syntax_module = _build_syntax_module(path)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _expression_syntax(source: str) -> SyntaxNode:
    expr_tree = read_sexpr_text(source, source_path="inline_drain_stdlib.orc")
    assert len(expr_tree.items) == 1
    datum = expr_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_drain_stdlib.orc",
        form_path=("workflow-lisp", "drain-stdlib-test"),
    )


def _command_boundaries(*, gap_output_type_name: str = "GapDraftResult"):
    return build_command_boundary_environment(
        {
            "select_next_item": CertifiedAdapterBinding(
                name="select_next_item",
                stable_command=("python", "scripts/select_next_item.py"),
                input_contract={"type": "object"},
                output_type_name="SelectionResult",
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("select_next_item_ok",),
                negative_fixture_ids=("select_next_item_bad",),
            ),
            "execute_selected_item": CertifiedAdapterBinding(
                name="execute_selected_item",
                stable_command=("python", "scripts/execute_selected_item.py"),
                input_contract={"type": "object"},
                output_type_name="SelectedItemResult",
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("execute_selected_item_ok",),
                negative_fixture_ids=("execute_selected_item_bad",),
            ),
            "draft_gap_item": CertifiedAdapterBinding(
                name="draft_gap_item",
                stable_command=("python", "scripts/draft_gap_item.py"),
                input_contract={"type": "object"},
                output_type_name=gap_output_type_name,
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("draft_gap_item_ok",),
                negative_fixture_ids=("draft_gap_item_bad",),
            ),
        }
    )


def _typecheck_fixture(path: Path):
    module = _compile_definition_module(path)
    type_env = FrontendTypeEnvironment.from_module(module)
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    return typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        extern_environment=ExternEnvironment(bindings_by_name={}),
        command_boundary_environment=_command_boundaries(),
    )


def _compile(
    path: Path,
    *,
    tmp_path: Path,
    validate_shared: bool = False,
    lowering_route: LoweringRoute = LoweringRoute.LEGACY,
):
    return compile_stage3_module(
        path,
        command_boundaries=_command_boundaries().bindings_by_name,
        validate_shared=validate_shared,
        workspace_root=tmp_path,
        lowering_route=lowering_route,
    )


def _compile_linked_stdlib_fixture(
    path: Path,
    *,
    tmp_path: Path,
    validation_profile: str | None = None,
    validate_shared: bool = False,
):
    source = path.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None, f"fixture is missing defmodule: {path}"
    resolved_module_name = module_match.group(1)
    module_path = (tmp_path / Path(*resolved_module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    compile_kwargs: dict[str, object] = {
        "source_roots": (tmp_path,),
        "command_boundaries": _command_boundaries(gap_output_type_name="GapResult").bindings_by_name,
        "workspace_root": tmp_path,
    }
    if validation_profile is not None:
        compile_kwargs["validation_profile"] = validation_profile
    else:
        compile_kwargs["validate_shared"] = validate_shared
    return module_path, compile_stage3_entrypoint(module_path, **compile_kwargs)


def _bound_runtime_inputs(bundle, workspace: Path, inputs: dict[str, object]) -> dict[str, object]:
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    public_inputs = {
        input_name: contract
        for input_name, contract in runtime_inputs.items()
        if not input_name.startswith("__write_root__")
    }
    return bind_workflow_inputs(public_inputs, inputs, workspace)


def _execute_bundle(bundle, *, workflow_path: Path, workspace: Path, inputs: dict[str, object], run_id: str):
    _seed_native_resource_states(bundle, workspace)
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_bound_runtime_inputs(bundle, workspace, inputs),
    )
    for relpath in ("scripts", "state", "artifacts"):
        source = workspace / relpath
        if source.exists():
            shutil.copytree(source, state_manager.run_root / relpath, dirs_exist_ok=True)
    return WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute(on_error="stop")


def _record_gap_drafter_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "drain_gap_record.orc"
    path.write_text(
        VALID_DRAIN_FIXTURE.read_text(encoding="utf-8").replace(
            "  (defunion GapDraftResult\n"
            "    (CONTINUE\n"
            "      (run-state StateExisting))\n"
            "    (BLOCKED\n"
            "      (progress-report-path WorkReport)\n"
            "      (blocker-class BlockerClass)))",
            "  (defrecord GapDraftResult\n"
            "    (run-state StateExisting))",
            1,
        ),
        encoding="utf-8",
    )
    return path


def _default_state_value(type_payload: dict[str, object]) -> object:
    kind = type_payload.get("kind")
    if kind == "primitive":
        primitive_name = type_payload.get("name")
        if primitive_name == "String":
            return ""
        if primitive_name == "Bool":
            return False
        if primitive_name == "Int":
            return 0
    if kind == "record":
        return {
            str(field["name"]): _default_state_value(dict(field["type"]))
            for field in type_payload.get("fields", ())
        }
    if kind == "path":
        name = str(type_payload.get("name", ""))
        if "Report" in name or "report" in name:
            return "artifacts/work/seed-report.md"
        return "state/seed-state.json"
    if kind == "enum":
        allowed = tuple(type_payload.get("allowed", ()))
        assert allowed
        return allowed[0]
    raise AssertionError(f"unsupported test seed type: {type_payload!r}")


def _iter_surface_steps(steps):
    for step in steps or ():
        yield step
        for branch_step in step.then_branch or ():
            yield from _iter_surface_steps((branch_step,))
        for branch_step in step.else_branch or ():
            yield from _iter_surface_steps((branch_step,))
        for branch_step in step.for_each_steps or ():
            yield from _iter_surface_steps((branch_step,))
        for case in step.match_cases.values():
            yield from _iter_surface_steps(case.steps)


def _seed_native_resource_states(bundle, workspace: Path) -> None:
    for step in _iter_surface_steps(bundle.surface.steps):
        declaration = step.resource_transition.get("declaration")
        resource = step.resource_transition.get("resource")
        if declaration is None or resource is None:
            continue
        if declaration.resource.backing.kind != "native":
            continue
        state_path = workspace / str(resource["state_path"])
        if state_path.exists():
            continue
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "transition_schema_version": 1,
                    "resource_id": resource["resource_id"],
                    "resource_kind": resource["resource_kind"],
                    "state_version": "native:0:seed",
                    "state": _default_state_value(dict(declaration.resource.state_type)),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def _write_drain_runtime_scripts(
    workspace: Path,
    *,
    selection_payload: dict[str, object],
    run_item_payload: dict[str, object] | None = None,
    gap_payload: dict[str, object] | None = None,
) -> None:
    scripts_dir = workspace / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    def _write_script(name: str, payload: dict[str, object], relpaths: tuple[str, ...]) -> None:
        lines = [
            "import json",
            "import os",
            "from pathlib import Path",
            "",
        ]
        for relpath in relpaths:
            lines.extend(
                [
                    f"path = Path({relpath!r})",
                    "if path.suffix:",
                    "    path.parent.mkdir(parents=True, exist_ok=True)",
                    "    path.write_text('generated\\n', encoding='utf-8')",
                    "else:",
                    "    path.mkdir(parents=True, exist_ok=True)",
                    "",
                ]
            )
        lines.extend(
            [
                'bundle_path = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])',
                "bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                f"payload = {payload!r}",
                "bundle_path.write_text(json.dumps(payload) + '\\n', encoding='utf-8')",
            ]
        )
        (scripts_dir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    _write_script(
        "select_next_item.py",
        selection_payload,
        tuple(
            path
            for path in (
                selection_payload.get("run-state"),
                ((selection_payload.get("selection") or {}) if isinstance(selection_payload.get("selection"), dict) else {}).get(
                    "item-state-root"
                ),
            )
            if isinstance(path, str)
        ),
    )
    _write_script(
        "execute_selected_item.py",
        run_item_payload or {"variant": "CONTINUE", "summary-path": "artifacts/work/item-complete.md", "run-state": "state/items/item-1/final.json"},
        tuple(
            path
            for path in (
                (run_item_payload or {}).get("summary-path"),
                (run_item_payload or {}).get("run-state"),
            )
            if isinstance(path, str)
        ),
    )
    _write_script(
        "draft_gap_item.py",
        gap_payload or {"variant": "CONTINUE", "run-state": "state/gaps/gap-1/continued.json"},
        tuple(
            path
            for path in (
                (gap_payload or {}).get("progress-report-path"),
                (gap_payload or {}).get("run-state"),
            )
            if isinstance(path, str)
        ),
    )


def _compile_imported_selector_bundle(tmp_path: Path):
    path = tmp_path / "imported_selector_bundle.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath StateExisting",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist true)",
                "  (defpath StateFile",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist false)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord DrainCtx",
                "    (run RunCtx)",
                "    (state-root Path.state-root)",
                "    (manifest StateExisting)",
                "    (ledger StateFile))",
                "  (defrecord SelectionPayload",
                "    (item-id String)",
                "    (item-state-root StateFile))",
                "  (defrecord GapPayload",
                "    (gap-id String))",
                "  (defunion SelectionResult",
                "    (EMPTY",
                "      (run-state StateExisting))",
                "    (GAP",
                "      (gap GapPayload))",
                "    (SELECTED",
                "      (selection SelectionPayload)))",
                "  (defworkflow selector-run",
                "    ((ctx DrainCtx))",
                "    -> SelectionResult",
                "    (provider-result providers.selector",
                "      :prompt prompts.selector",
                "      :inputs (ctx.manifest)",
                "      :returns SelectionResult))",
                ")",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        provider_externs={"providers.selector": "imported-selector-provider"},
        prompt_externs={"prompts.selector": "prompts/imported-selector.md"},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.WCC_M4,
    )
    return result.validated_bundles["selector-run"]


def _iter_nested_steps(steps):
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        yield step
        repeat = step.get("repeat_until")
        if isinstance(repeat, dict):
            yield from _iter_nested_steps(repeat.get("steps"))
        match = step.get("match")
        if isinstance(match, dict):
            for case in (match.get("cases") or {}).values():
                if isinstance(case, dict):
                    yield from _iter_nested_steps(case.get("steps"))


def _assert_contract_matches_observed_families(contract, *, steps) -> set[str]:
    observed = set(_observed_statement_families(steps))
    assert set(contract.required_statement_families).issubset(observed)
    for alternatives in contract.alternative_statement_family_sets:
        matches = observed.intersection(alternatives)
        assert len(matches) == 1
    return observed


def test_elaborate_backlog_drain_expr() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(backlog-drain neurips "
            ":ctx ctx "
            ":selector selector-run "
            ":run-item run-selected-item "
            ":gap-drafter gap-draft "
            ":max-iterations max-iterations)"
        ),
        bound_names=frozenset({"ctx", "max-iterations"}),
    )

    assert type(expr).__name__ == "BacklogDrainExpr"


def test_workflow_ref_environment_accepts_same_file_backlog_refs() -> None:
    typed = _typecheck_fixture(VALID_DRAIN_FIXTURE)

    assert [workflow.definition.name for workflow in typed] == [
        "selector-run",
        "run-selected-item",
        "gap-draft",
        "drain",
    ]


def test_workflow_ref_environment_builds_noop_extern_rebinding_for_provider_free_workflows() -> None:
    typed = _typecheck_fixture(VALID_DRAIN_FIXTURE)

    assert typed[-1].definition.name == "drain"


def test_promoted_entry_DrainCtx_hidden_binding_reports_unsupported_private_exec_bootstrap(
    tmp_path: Path,
) -> None:
    path = tmp_path / "private_exec_context" / "drain_ctx.orc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule private_exec_context/drain_ctx)",
                "  (export entry selector-run)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defpath StateExisting",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist true)",
                "  (defpath StateFile",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist false)",
                "  (defrecord DrainCtx",
                "    (run RunCtx)",
                "    (state-root Path.state-root)",
                "    (manifest StateExisting)",
                "    (ledger StateFile))",
                "  (defrecord Result",
                "    (manifest StateExisting))",
                "  (defworkflow entry",
                "    ()",
                "    -> Result",
                "    (call selector-run))",
                "  (defworkflow selector-run",
                "    ((ctx DrainCtx))",
                "    -> Result",
                "    (record Result :manifest ctx.manifest))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            path,
            source_roots=(tmp_path,),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "private_exec_context_bootstrap_unsupported"
    assert "DrainCtx" in diagnostic.message


def test_workflow_ref_resolution_rejects_signature_mismatch() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_SIGNATURE_FIXTURE)

    assert excinfo.value.diagnostics[0].code == "workflow_call_signature_erased"


def test_workflow_ref_resolution_rejects_selector_field_type_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "selector_field_type_mismatch.orc"
    path.write_text(
        VALID_DRAIN_FIXTURE.read_text(encoding="utf-8").replace(
            "    (EMPTY\n      (run-state StateExisting))",
            "    (EMPTY\n      (run-state WorkReport))",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    assert excinfo.value.diagnostics[0].code == "workflow_call_signature_erased"


def test_workflow_ref_union_call_boundary_projection_rejects_unproved_variant_access() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_UNION_BOUNDARY_FIXTURE)

    assert excinfo.value.diagnostics[0].code == "variant_ref_unproved"


def test_lowering_backlog_drain_uses_repeat_until_with_typed_accumulator(tmp_path: Path) -> None:
    result = _compile(VALID_DRAIN_FIXTURE, tmp_path=tmp_path)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "drain"
    )
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    body_steps = list(_iter_nested_steps(repeat_step["repeat_until"]["steps"]))
    call_targets = {step.get("call") for step in body_steps if isinstance(step.get("call"), str)}

    assert repeat_step["repeat_until"]["steps"]
    assert any(target and target.endswith("selector-run") for target in call_targets)
    assert any(target and target.endswith("run-selected-item") for target in call_targets)
    assert any(target and target.endswith("gap-draft") for target in call_targets)
    selector_call = next(step for step in body_steps if step.get("call", "").endswith("selector-run"))
    run_item_call = next(step for step in body_steps if step.get("call", "").endswith("run-selected-item"))
    gap_drafter_call = next(step for step in body_steps if step.get("call", "").endswith("gap-draft"))
    selector_bindings = _managed_write_root_bindings(
        caller_workflow_name="drain",
        call_step_name=selector_call["name"],
        callee_name="selector-run",
        managed_inputs=("__write_root__selector_run__select_next_item__result_bundle",),
        iteration_scope="${loop.index}",
    )
    run_item_bindings = _managed_write_root_bindings(
        caller_workflow_name="drain",
        call_step_name=run_item_call["name"],
        callee_name="run-selected-item",
        managed_inputs=("__write_root__run_selected_item__execute_selected_item__result_bundle",),
        iteration_scope="${loop.index}",
    )
    gap_drafter_bindings = _managed_write_root_bindings(
        caller_workflow_name="drain",
        call_step_name=gap_drafter_call["name"],
        callee_name="gap-draft",
        managed_inputs=("__write_root__gap_draft__draft_gap_item__result_bundle",),
        iteration_scope="${loop.index}",
    )

    assert selector_call["with"] == {
        "ctx__run__run-id": {"ref": "inputs.ctx__run__run-id"},
        "ctx__run__state-root": {"ref": "inputs.ctx__run__state-root"},
        "ctx__run__artifact-root": {"ref": "inputs.ctx__run__artifact-root"},
        "ctx__state-root": {"ref": "inputs.ctx__state-root"},
        "ctx__manifest": {"ref": "inputs.ctx__manifest"},
        "ctx__ledger": {"ref": "inputs.ctx__ledger"},
        "__write_root__selector_run__select_next_item__result_bundle": selector_bindings[
            "__write_root__selector_run__select_next_item__result_bundle"
        ],
    }
    assert run_item_call["with"] == {
        "item-ctx__run__run-id": {"ref": "inputs.ctx__run__run-id"},
        "item-ctx__run__state-root": {"ref": "inputs.ctx__run__state-root"},
        "item-ctx__run__artifact-root": {"ref": "inputs.ctx__run__artifact-root"},
        "item-ctx__item-id": {"ref": "self.steps.drain__selector.artifacts.return__selection__item-id"},
        "item-ctx__state-root": {"ref": "self.steps.drain__selector.artifacts.return__selection__item-state-root"},
        "item-ctx__artifact-root": {"ref": "inputs.ctx__run__artifact-root"},
        "item-ctx__ledger": {"ref": "inputs.ctx__ledger"},
        "selection__item-id": {"ref": "self.steps.drain__selector.artifacts.return__selection__item-id"},
        "selection__item-state-root": {"ref": "self.steps.drain__selector.artifacts.return__selection__item-state-root"},
        "__write_root__run_selected_item__execute_selected_item__result_bundle": run_item_bindings[
            "__write_root__run_selected_item__execute_selected_item__result_bundle"
        ],
    }
    assert gap_drafter_call["with"] == {
        "ctx__run__run-id": {"ref": "inputs.ctx__run__run-id"},
        "ctx__run__state-root": {"ref": "inputs.ctx__run__state-root"},
        "ctx__run__artifact-root": {"ref": "inputs.ctx__run__artifact-root"},
        "ctx__state-root": {"ref": "inputs.ctx__state-root"},
        "ctx__manifest": {"ref": "inputs.ctx__manifest"},
        "ctx__ledger": {"ref": "inputs.ctx__ledger"},
        "gap__gap-id": {"ref": "self.steps.drain__selector.artifacts.return__gap__gap-id"},
        "__write_root__gap_draft__draft_gap_item__result_bundle": gap_drafter_bindings[
            "__write_root__gap_draft__draft_gap_item__result_bundle"
        ],
    }
    assert repeat_step["repeat_until"]["condition"] == {
        "compare": {
            "left": {"ref": "self.outputs.acc__loop-status"},
            "op": "ne",
            "right": "CONTINUE",
        }
    }
    assert repeat_step["repeat_until"]["max_iterations"] == 4
    assert tuple(sorted(repeat_step["repeat_until"]["outputs"])) == (
        "acc__blocker-class",
        "acc__items-processed",
        "acc__loop-status",
        "acc__progress-report-path",
        "acc__run-state",
    )
    assert not any("resource_transition" in step for step in body_steps)
    assert not any("materialize_view" in step for step in body_steps)
    assert not any(
        step.get("command", [])[:3] == ["python", "-m", "orchestrator.workflow_lisp.adapters.normalize_drain_result"]
        for step in authored["steps"]
        if isinstance(step, dict)
    )


def test_compile_stage3_module_validates_imported_backlog_drain_through_frontend_surface(
    tmp_path: Path,
) -> None:
    _workflow_path, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_DRAIN_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=False,
    )

    drain = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::drain")
    )
    repeat_step = next(step for step in drain.authored_mapping["steps"] if "repeat_until" in step)

    assert repeat_step["repeat_until"]["max_iterations"] == 4


def test_command_result_contract_accepts_certified_adapter_backends_without_hiding_command_boundary(
    tmp_path: Path,
) -> None:
    result = _compile(VALID_DRAIN_FIXTURE, tmp_path=tmp_path)
    contract = STDLIB_LOWERING_CONTRACTS_BY_FORM["command-result"]
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-selected-item"
    )
    authored = lowered.authored_mapping
    command_step = next(
        step
        for step in _iter_nested_steps(authored["steps"])
        if step.get("command", [])[:2] == ["python", "scripts/execute_selected_item.py"]
    )

    assert contract.family == "structured_result_producer"
    assert set(contract.backend_kinds) == {"external_tool", "certified_adapter"}
    assert contract.required_statement_families == ("command_step",)
    assert contract.alternative_statement_family_sets == (("output_bundle", "variant_output"),)
    assert contract.delegated_statement_family_policy == "none"
    assert contract.state_root_policies == ("generated_hidden_bundle_input",)
    assert contract.authority_model == "validated_structured_result_bundle"
    assert contract.proof_model == "contract_validated_bundle"
    assert contract.source_map_expectations == (
        "high_level_form_origin",
        "generated_step_span",
        "generated_hidden_input_span",
        "generated_hidden_path_span",
        "adapter_command_step_origin",
    )
    assert isinstance(
        result.command_boundary_environment.bindings_by_name["execute_selected_item"],
        CertifiedAdapterBinding,
    )
    observed = _assert_contract_matches_observed_families(contract, steps=authored["steps"])
    assert observed.intersection({"output_bundle", "variant_output"}) == {"variant_output"}
    assert command_step["id"] in lowered.origin_map.step_spans
    assert lowered.origin_map.step_spans[command_step["id"]].origin_key
    hidden_input = command_step["variant_output"]["path"].removeprefix("${inputs.").removesuffix("}")
    assert hidden_input in lowered.origin_map.internal_input_spans
    assert command_step["variant_output"]["path"] in lowered.origin_map.generated_path_spans


def test_compile_stage3_module_supports_record_gap_drafter_returns(tmp_path: Path) -> None:
    result = _compile(_record_gap_drafter_fixture(tmp_path), tmp_path=tmp_path, validate_shared=True)

    drain = next(workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "drain")
    rendered = str(drain.authored_mapping)

    assert "drain__gap_drafter.artifacts.return__variant" not in rendered


def test_backlog_drain_contract_inventory_matches_promoted_stdlib_route(tmp_path: Path) -> None:
    _workflow_path, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_DRAIN_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )
    contract = STDLIB_LOWERING_CONTRACTS_BY_FORM["backlog-drain"]
    lowered = next(
        workflow for workflow in result.entry_result.lowered_workflows if workflow.typed_workflow.definition.name.endswith("::drain")
    )
    authored = lowered.authored_mapping
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    body_steps = list(_iter_nested_steps(repeat_step["repeat_until"]["steps"]))
    workflow_calls = [step for step in body_steps if isinstance(step.get("call"), str)]

    assert contract.family == "resource_finalize_drain"
    assert contract.backend_kinds == ("workflow_call", "runtime_native")
    assert contract.required_statement_families == (
        "repeat_until",
        "workflow_call",
        "match",
        "materialize_view",
        "output_bundle",
    )
    assert contract.alternative_statement_family_sets == ()
    assert contract.delegated_statement_family_policy == "none"
    assert contract.state_root_policies == (
        "generated_hidden_bundle_input",
        "managed_call_write_roots",
        "runtime_native_resource_state",
    )
    assert contract.authority_model == "typed_terminal_transition_and_materialized_summary"
    assert contract.proof_model == "dedicated_runtime_proof_with_typed_terminal_parity"
    assert contract.source_map_expectations == (
        "high_level_form_origin",
        "generated_step_span",
        "generated_hidden_input_span",
        "generated_hidden_path_span",
    )
    _assert_contract_matches_observed_families(contract, steps=authored["steps"])
    assert workflow_calls
    assert any(any(name.startswith("__write_root__") for name in step.get("with", {})) for step in workflow_calls)
    validate_executable_workflow(result.entry_result.validated_bundles["drain_stdlib_backlog_drain_stdlib::drain"].ir)
    for step in _iter_nested_steps(authored["steps"]):
        step_id = step.get("id")
        if isinstance(step_id, str):
            assert step_id in lowered.origin_map.step_spans
            assert lowered.origin_map.step_spans[step_id].origin_key


@pytest.mark.parametrize(
    ("selection_payload", "run_item_payload", "gap_payload", "expected_outputs"),
    (
        (
            {"variant": "EMPTY", "run-state": "state/empty-queue.json"},
            None,
            None,
            {
                "return__variant": "EMPTY",
                "return__run-state": "state/drain-run-state.json",
                "summary_path": "artifacts/work/drain-progress-report.md",
            },
        ),
        (
            {
                "variant": "SELECTED",
                "selection": {"item-id": "item-1", "item-state-root": "state/items/item-1"},
            },
            {
                "variant": "BLOCKED",
                "summary-path": "artifacts/work/item-blocked.md",
                "blocker-class": "roadmap_conflict",
                "run-state": "state/items/item-1/final.json",
            },
            None,
            {
                "return__variant": "BLOCKED",
                "return__progress-report-path": "artifacts/work/item-blocked.md",
                "return__blocker-class": "roadmap_conflict",
                "summary_path": "artifacts/work/item-blocked.md",
            },
        ),
        (
            {
                "variant": "SELECTED",
                "selection": {"item-id": "item-1", "item-state-root": "state/items/item-1"},
            },
            {
                "variant": "CONTINUE",
                "summary-path": "artifacts/work/item-complete.md",
                "run-state": "state/items/item-1/final.json",
            },
            None,
            {
                "return__variant": "COMPLETED",
                "return__items-processed": 1,
                "return__run-state": "state/items/item-1/final.json",
                "summary_path": "artifacts/work/item-complete.md",
            },
        ),
        (
            {"variant": "GAP", "gap": {"gap-id": "gap-1"}},
            None,
            {"variant": "CONTINUE", "run-state": "state/gaps/gap-1/continued.json"},
            {
                "return__variant": "BLOCKED",
                "return__progress-report-path": "artifacts/work/drain-progress-report.md",
                "return__blocker-class": "unrecoverable_after_fix_attempt",
                "summary_path": "artifacts/work/drain-progress-report.md",
            },
        ),
    ),
)
def test_stdlib_backlog_drain_executes_promoted_route_with_terminal_side_effects(
    tmp_path: Path,
    selection_payload: dict[str, object],
    run_item_payload: dict[str, object] | None,
    gap_payload: dict[str, object] | None,
    expected_outputs: dict[str, object],
) -> None:
    workflow_path, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_DRAIN_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )
    bundle = result.entry_result.validated_bundles["drain_stdlib_backlog_drain_stdlib::drain"]
    _write_drain_runtime_scripts(
        tmp_path,
        selection_payload=selection_payload,
        run_item_payload=run_item_payload,
        gap_payload=gap_payload,
    )

    manifest_path = tmp_path / "state" / "runtime" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{}\n", encoding="utf-8")
    initial_run_state = tmp_path / "state" / "drain-run-state.json"
    initial_run_state.parent.mkdir(parents=True, exist_ok=True)
    initial_run_state.write_text("{}\n", encoding="utf-8")
    summary_path = tmp_path / "artifacts" / "work" / "drain-progress-report.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("seed\n", encoding="utf-8")
    ledger_path = tmp_path / "state" / "runtime" / "ledger.json"
    ledger_path.write_text("[]\n", encoding="utf-8")

    state = _execute_bundle(
        bundle,
        workflow_path=workflow_path,
        workspace=tmp_path,
        run_id="drain-stdlib-runtime",
        inputs={
            "ctx__run__run-id": "drain-stdlib-runtime",
            "ctx__run__state-root": "state/runtime",
            "ctx__run__artifact-root": "artifacts/work",
            "ctx__state-root": "state/runtime",
            "ctx__manifest": "state/runtime/manifest.json",
            "ctx__ledger": "state/runtime/ledger.json",
            "max-iterations": 4,
        },
    )

    assert state["status"] == "completed"
    for key, value in expected_outputs.items():
        if key == "summary_path":
            continue
        assert state["workflow_outputs"][key] == value
    assert (tmp_path / expected_outputs["summary_path"]).is_file()
    assert sorted(tmp_path.rglob("*drain-run-state-state.json"))
    assert sorted(tmp_path.rglob("*record-drain-outcome-audit.jsonl"))


def test_stdlib_backlog_drain_rejects_non_symbol_callee_on_imported_route(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_linked_stdlib_fixture(INVALID_STDLIB_DRAIN_NON_SYMBOL_CALLEE_FIXTURE, tmp_path=tmp_path)

    assert excinfo.value.diagnostics[0].code == "frontend_parse_error"


def test_stdlib_backlog_drain_view_authority_misuse_still_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_linked_stdlib_fixture(INVALID_STDLIB_DRAIN_VIEW_AUTHORITY_FIXTURE, tmp_path=tmp_path)

    assert excinfo.value.diagnostics[0].code == "type_mismatch"

def test_workflow_ref_provider_metadata_must_satisfy_callee_externs(tmp_path: Path) -> None:
    path = tmp_path / "provider_backlog_drain_invalid.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware",
                "    roadmap_conflict",
                "    external_dependency_outside_authority",
                "    user_decision_required",
                "    unrecoverable_after_fix_attempt)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defpath StateFile",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist false)",
                "  (defpath StateExisting",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist true)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord DrainCtx",
                "    (run RunCtx)",
                "    (state-root Path.state-root)",
                "    (manifest StateExisting)",
                "    (ledger StateFile))",
                "  (defrecord ItemCtx",
                "    (run RunCtx)",
                "    (item-id String)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root)",
                "    (ledger StateFile))",
                "  (defrecord SelectionPayload",
                "    (item-id String)",
                "    (item-state-root StateFile))",
                "  (defrecord GapPayload",
                "    (gap-id String))",
                "  (defrecord SelectorProviderBindings",
                "    (provider Provider))",
                "  (defrecord DrainProviders",
                "    (selector SelectorProviderBindings))",
                "  (defunion SelectionResult",
                "    (EMPTY",
                "      (run-state StateExisting))",
                "    (GAP",
                "      (gap GapPayload))",
                "    (SELECTED",
                "      (selection SelectionPayload)))",
                "  (defunion SelectedItemResult",
                "    (CONTINUE",
                "      (summary-path WorkReport)",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (summary-path WorkReport)",
                "      (blocker-class BlockerClass)",
                "      (run-state StateExisting)))",
                "  (defunion GapDraftResult",
                "    (CONTINUE",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass)))",
                "  (defunion DrainResult",
                "    (EMPTY",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass))",
                "    (COMPLETED",
                "      (items-processed Int)",
                "      (run-state StateExisting)))",
                "  (defworkflow selector-run",
                "    ((ctx DrainCtx))",
                "    -> SelectionResult",
                "    (provider-result providers.selector",
                "      :prompt prompts.selector",
                "      :inputs (ctx.manifest)",
                "      :returns SelectionResult))",
                "  (defworkflow run-selected-item",
                "    ((item-ctx ItemCtx)",
                "     (selection SelectionPayload))",
                "    -> SelectedItemResult",
                "    (command-result execute_selected_item",
                "      :argv (\"python\" \"scripts/execute_selected_item.py\" selection.item-id)",
                "      :returns SelectedItemResult))",
                "  (defworkflow gap-draft",
                "    ((ctx DrainCtx)",
                "     (gap GapPayload))",
                "    -> GapDraftResult",
                "    (command-result draft_gap_item",
                "      :argv (\"python\" \"scripts/draft_gap_item.py\" gap.gap-id)",
                "      :returns GapDraftResult))",
                "  (defworkflow drain",
                "    ((ctx DrainCtx)",
                "     (max-iterations Int))",
                "    -> DrainResult",
                "    (backlog-drain neurips",
                "      :ctx ctx",
                "      :selector selector-run",
                "      :run-item run-selected-item",
                "      :gap-drafter gap-draft",
                "      :providers (record DrainProviders",
                "                   :selector (record SelectorProviderBindings",
                "                               :provider providers.selector))",
                "      :max-iterations 4))",
                ")",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            provider_externs={"providers.selector": "selector-provider"},
            prompt_externs={"prompts.selector": "prompts/selector.md"},
            command_boundaries=_command_boundaries().bindings_by_name,
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.LEGACY,
        )

    assert excinfo.value.diagnostics[0].code == "backlog_drain_contract_invalid"


def test_compile_stage3_module_rebinds_imported_selector_provider_metadata(tmp_path: Path) -> None:
    imported_selector = _compile_imported_selector_bundle(tmp_path)
    path = tmp_path / "imported_backlog_drain.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware",
                "    roadmap_conflict",
                "    external_dependency_outside_authority",
                "    user_decision_required",
                "    unrecoverable_after_fix_attempt)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defpath StateFile",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist false)",
                "  (defpath StateExisting",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist true)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord DrainCtx",
                "    (run RunCtx)",
                "    (state-root Path.state-root)",
                "    (manifest StateExisting)",
                "    (ledger StateFile))",
                "  (defrecord ItemCtx",
                "    (run RunCtx)",
                "    (item-id String)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root)",
                "    (ledger StateFile))",
                "  (defrecord SelectionPayload",
                "    (item-id String)",
                "    (item-state-root StateFile))",
                "  (defrecord GapPayload",
                "    (gap-id String))",
                "  (defrecord SelectorProviderBindings",
                "    (provider Provider)",
                "    (prompt Prompt))",
                "  (defrecord DrainProviders",
                "    (selector SelectorProviderBindings))",
                "  (defunion SelectionResult",
                "    (EMPTY",
                "      (run-state StateExisting))",
                "    (GAP",
                "      (gap GapPayload))",
                "    (SELECTED",
                "      (selection SelectionPayload)))",
                "  (defunion SelectedItemResult",
                "    (CONTINUE",
                "      (summary-path WorkReport)",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (summary-path WorkReport)",
                "      (blocker-class BlockerClass)",
                "      (run-state StateExisting)))",
                "  (defunion GapDraftResult",
                "    (CONTINUE",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass)))",
                "  (defunion DrainResult",
                "    (EMPTY",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass))",
                "    (COMPLETED",
                "      (items-processed Int)",
                "      (run-state StateExisting)))",
                "  (defworkflow run-selected-item",
                "    ((item-ctx ItemCtx)",
                "     (selection SelectionPayload))",
                "    -> SelectedItemResult",
                "    (command-result execute_selected_item",
                "      :argv (\"python\" \"scripts/execute_selected_item.py\" selection.item-id)",
                "      :returns SelectedItemResult))",
                "  (defworkflow gap-draft",
                "    ((ctx DrainCtx)",
                "     (gap GapPayload))",
                "    -> GapDraftResult",
                "    (command-result draft_gap_item",
                "      :argv (\"python\" \"scripts/draft_gap_item.py\" gap.gap-id)",
                "      :returns GapDraftResult))",
                "  (defworkflow drain",
                "    ((ctx DrainCtx)",
                "     (max-iterations Int))",
                "    -> DrainResult",
                "    (backlog-drain neurips",
                "      :ctx ctx",
                "      :selector selector-run",
                "      :run-item run-selected-item",
                "      :gap-drafter gap-draft",
                "      :providers (record DrainProviders",
                "                   :selector (record SelectorProviderBindings",
                "                               :provider providers.selector",
                "                               :prompt prompts.selector))",
                "      :max-iterations 4))",
                ")",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        provider_externs={"providers.selector": "main-selector-provider"},
        prompt_externs={"prompts.selector": "prompts/main-selector.md"},
        command_boundaries=_command_boundaries().bindings_by_name,
        imported_workflow_bundles={"selector-run": imported_selector},
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )

    drain = next(workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "drain")
    repeat_step = next(step for step in drain.authored_mapping["steps"] if "repeat_until" in step)
    selector_call = repeat_step["repeat_until"]["steps"][0]

    assert selector_call["call"] != "selector-run"
    assert selector_call["call"].startswith("selector-run__selector")


def test_compile_stage3_module_rejects_ambiguous_imported_selector_boundary_types(tmp_path: Path) -> None:
    imported_selector = _compile_imported_selector_bundle(tmp_path)

    def _module_source(*, first_label: str, second_label: str) -> str:
        return "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware",
                "    roadmap_conflict",
                "    external_dependency_outside_authority",
                "    user_decision_required",
                "    unrecoverable_after_fix_attempt)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defpath StateFile",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist false)",
                "  (defpath StateExisting",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist true)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord DrainCtx",
                "    (run RunCtx)",
                "    (state-root Path.state-root)",
                "    (manifest StateExisting)",
                "    (ledger StateFile))",
                "  (defrecord ItemCtx",
                "    (run RunCtx)",
                "    (item-id String)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root)",
                "    (ledger StateFile))",
                f"  (defrecord SelectionPayload{first_label}",
                "    (item-id String)",
                "    (item-state-root StateFile))",
                f"  (defrecord GapPayload{first_label}",
                "    (gap-id String))",
                f"  (defunion SelectionResult{first_label}",
                "    (EMPTY",
                "      (run-state StateExisting))",
                "    (GAP",
                f"      (gap GapPayload{first_label}))",
                "    (SELECTED",
                f"      (selection SelectionPayload{first_label})))",
                f"  (defrecord SelectionPayload{second_label}",
                "    (item-id String)",
                "    (item-state-root StateFile))",
                f"  (defrecord GapPayload{second_label}",
                "    (gap-id String))",
                f"  (defunion SelectionResult{second_label}",
                "    (EMPTY",
                "      (run-state StateExisting))",
                "    (GAP",
                f"      (gap GapPayload{second_label}))",
                "    (SELECTED",
                f"      (selection SelectionPayload{second_label})))",
                "  (defunion SelectedItemResult",
                "    (CONTINUE",
                "      (summary-path WorkReport)",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (summary-path WorkReport)",
                "      (blocker-class BlockerClass)",
                "      (run-state StateExisting)))",
                "  (defunion GapDraftResult",
                "    (CONTINUE",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass)))",
                "  (defunion DrainResult",
                "    (EMPTY",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass))",
                "    (COMPLETED",
                "      (items-processed Int)",
                "      (run-state StateExisting)))",
                "  (defworkflow run-selected-item",
                "    ((item-ctx ItemCtx)",
                f"     (selection SelectionPayload{second_label}))",
                "    -> SelectedItemResult",
                "    (command-result execute_selected_item",
                '      :argv ("python" "scripts/execute_selected_item.py" selection.item-id)',
                "      :returns SelectedItemResult))",
                "  (defworkflow gap-draft",
                "    ((ctx DrainCtx)",
                f"     (gap GapPayload{second_label}))",
                "    -> GapDraftResult",
                "    (command-result draft_gap_item",
                '      :argv ("python" "scripts/draft_gap_item.py" gap.gap-id)',
                "      :returns GapDraftResult))",
                "  (defworkflow drain",
                "    ((ctx DrainCtx)",
                "     (max-iterations Int))",
                "    -> DrainResult",
                "    (backlog-drain neurips",
                "      :ctx ctx",
                "      :selector selector-run",
                "      :run-item run-selected-item",
                "      :gap-drafter gap-draft",
                "      :max-iterations 4))",
                ")",
            ]
        )

    for first_label, second_label in (("A", "B"), ("B", "A")):
        path = tmp_path / f"ambiguous_imported_selector_{first_label}{second_label}.orc"
        path.write_text(_module_source(first_label=first_label, second_label=second_label), encoding="utf-8")

        with pytest.raises(LispFrontendCompileError) as excinfo:
            compile_stage3_module(
                path,
                command_boundaries=_command_boundaries().bindings_by_name,
                imported_workflow_bundles={"selector-run": imported_selector},
                validate_shared=False,
                workspace_root=tmp_path,
                lowering_route=LoweringRoute.LEGACY,
            )

        diagnostic = excinfo.value.diagnostics[0]
        assert diagnostic.code == "workflow_call_signature_erased"
        assert "ambiguous" in diagnostic.message


def test_compile_stage3_module_rebinds_same_file_selector_provider_metadata(tmp_path: Path) -> None:
    path = tmp_path / "same_file_backlog_drain.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware",
                "    roadmap_conflict",
                "    external_dependency_outside_authority",
                "    user_decision_required",
                "    unrecoverable_after_fix_attempt)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defpath StateFile",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist false)",
                "  (defpath StateExisting",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist true)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord DrainCtx",
                "    (run RunCtx)",
                "    (state-root Path.state-root)",
                "    (manifest StateExisting)",
                "    (ledger StateFile))",
                "  (defrecord ItemCtx",
                "    (run RunCtx)",
                "    (item-id String)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root)",
                "    (ledger StateFile))",
                "  (defrecord SelectionPayload",
                "    (item-id String)",
                "    (item-state-root StateFile))",
                "  (defrecord GapPayload",
                "    (gap-id String))",
                "  (defrecord SelectorProviderBindings",
                "    (provider Provider)",
                "    (prompt Prompt))",
                "  (defrecord DrainProviders",
                "    (selector SelectorProviderBindings))",
                "  (defunion SelectionResult",
                "    (EMPTY",
                "      (run-state StateExisting))",
                "    (GAP",
                "      (gap GapPayload))",
                "    (SELECTED",
                "      (selection SelectionPayload)))",
                "  (defunion SelectedItemResult",
                "    (CONTINUE",
                "      (summary-path WorkReport)",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (summary-path WorkReport)",
                "      (blocker-class BlockerClass)",
                "      (run-state StateExisting)))",
                "  (defunion GapDraftResult",
                "    (CONTINUE",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass)))",
                "  (defunion DrainResult",
                "    (EMPTY",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass))",
                "    (COMPLETED",
                "      (items-processed Int)",
                "      (run-state StateExisting)))",
                "  (defworkflow selector-run",
                "    ((ctx DrainCtx))",
                "    -> SelectionResult",
                "    (provider-result providers.internal_selector",
                "      :prompt prompts.internal_selector",
                "      :inputs (ctx.manifest)",
                "      :returns SelectionResult))",
                "  (defworkflow run-selected-item",
                "    ((item-ctx ItemCtx)",
                "     (selection SelectionPayload))",
                "    -> SelectedItemResult",
                "    (command-result execute_selected_item",
                "      :argv (\"python\" \"scripts/execute_selected_item.py\" selection.item-id)",
                "      :returns SelectedItemResult))",
                "  (defworkflow gap-draft",
                "    ((ctx DrainCtx)",
                "     (gap GapPayload))",
                "    -> GapDraftResult",
                "    (command-result draft_gap_item",
                "      :argv (\"python\" \"scripts/draft_gap_item.py\" gap.gap-id)",
                "      :returns GapDraftResult))",
                "  (defworkflow drain",
                "    ((ctx DrainCtx)",
                "     (max-iterations Int))",
                "    -> DrainResult",
                "    (backlog-drain neurips",
                "      :ctx ctx",
                "      :selector selector-run",
                "      :run-item run-selected-item",
                "      :gap-drafter gap-draft",
                "      :providers (record DrainProviders",
                "                   :selector (record SelectorProviderBindings",
                "                               :provider providers.selector",
                "                               :prompt prompts.selector))",
                "      :max-iterations 4))",
                ")",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        provider_externs={
            "providers.internal_selector": "internal-selector-provider",
            "providers.selector": "main-selector-provider",
        },
        prompt_externs={
            "prompts.internal_selector": "prompts/internal-selector.md",
            "prompts.selector": "prompts/main-selector.md",
        },
        command_boundaries=_command_boundaries().bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )

    drain = next(workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "drain")
    repeat_step = next(step for step in drain.authored_mapping["steps"] if "repeat_until" in step)
    selector_call = repeat_step["repeat_until"]["steps"][0]

    assert selector_call["call"] != "selector-run"
    assert selector_call["call"].startswith("selector-run__selector")
    rebound_selector = next(
        workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == selector_call["call"]
    )
    provider_step = rebound_selector.authored_mapping["steps"][0]
    assert provider_step["provider"] == "main-selector-provider"
    assert provider_step["asset_file"] == "prompts/main-selector.md"
