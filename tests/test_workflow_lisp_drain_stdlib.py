import json
from pathlib import Path
import re
import shutil

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.executable_ir import validate_executable_workflow
from orchestrator.workflow.loaded_bundle import workflow_boundary_projection, workflow_runtime_input_contracts
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
from orchestrator.workflow_lisp.workflows import ExternEnvironment, PromptExtern
from orchestrator.workflow_lisp.workflows import (
    CertifiedAdapterBinding,
    build_command_boundary_environment,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)
from tests.workflow_bundle_helpers import bundle_context_dict


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_DRAIN_FIXTURE = FIXTURES / "valid" / "drain_stdlib_backlog_drain.orc"
VALID_STDLIB_CALLABLE_BOUNDARY_FIXTURE = (
    FIXTURES / "valid" / "drain_stdlib_backlog_drain_callable_boundary.orc"
)
VALID_STDLIB_PARENT_TERMINAL_REPROJECTION_FIXTURE = (
    FIXTURES / "valid" / "drain_stdlib_backlog_drain_parent_terminal_reprojection.orc"
)
VALID_STDLIB_BRANCH_LOCAL_TERMINAL_CONTRACT_ALIGNMENT_FIXTURE = (
    FIXTURES / "valid" / "drain_stdlib_backlog_drain_branch_local_terminal_contract_alignment.orc"
)
VALID_STDLIB_CALLABLE_BOUNDARY_RICH_GAP_FIXTURE = (
    FIXTURES / "valid" / "drain_stdlib_backlog_drain_callable_boundary_rich_gap_payload.orc"
)
INVALID_SIGNATURE_FIXTURE = FIXTURES / "invalid" / "backlog_drain_workflow_ref_signature_invalid.orc"
INVALID_SELECTOR_BLOCKED_REASON_MISSING_FIXTURE = (
    FIXTURES / "invalid" / "backlog_drain_selector_blocked_reason_missing_invalid.orc"
)
INVALID_SELECTOR_BLOCKED_EXTRA_STATE_FIELD_FIXTURE = (
    FIXTURES / "invalid" / "backlog_drain_selector_blocked_extra_state_field_invalid.orc"
)
INVALID_UNION_BOUNDARY_FIXTURE = FIXTURES / "invalid" / "backlog_drain_union_call_boundary_invalid.orc"
INVALID_GAP_DRAFTER_NON_RECORD_PAYLOAD_FIXTURE = (
    FIXTURES / "invalid" / "backlog_drain_gap_drafter_non_record_payload_invalid.orc"
)
INVALID_STDLIB_DRAIN_NON_SYMBOL_CALLEE_FIXTURE = (
    FIXTURES / "invalid" / "drain_stdlib_backlog_drain_non_symbol_callee.orc"
)
INVALID_STDLIB_DRAIN_VIEW_AUTHORITY_FIXTURE = (
    FIXTURES / "invalid" / "drain_stdlib_materialized_view_authority_invalid.orc"
)
INVALID_HIDDEN_COMPATIBILITY_BRIDGE_PUBLIC_RUN_ITEM_FIXTURE = (
    FIXTURES
    / "invalid"
    / "backlog_drain_hidden_compatibility_bridge_public_run_item_invalid.orc"
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


def _command_boundaries(
    *,
    gap_output_type_name: str = "GapDraftResult",
):
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


def _custom_union_command_boundaries():
    return build_command_boundary_environment(
        {
            "select_next_item": CertifiedAdapterBinding(
                name="select_next_item",
                stable_command=("python", "scripts/select_next_item.py"),
                input_contract={"type": "object"},
                output_type_name="CustomSelectionResult",
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
                output_type_name="CustomSelectedItemResult",
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
                output_type_name="CustomGapDraftResult",
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
    lowering_route: LoweringRoute | None = None,
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
    if lowering_route is not None:
        compile_kwargs["lowering_route"] = lowering_route
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
            "    (CONTINUE)\n"
            "    (BLOCKED\n"
            "      (progress-report-path WorkReport)\n"
            "      (blocker-class BlockerClass)))",
            "  (defrecord GapDraftResult\n"
            "    (gap-id String))",
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
    selection_payload: dict[str, object] | list[dict[str, object]],
    run_item_payload: dict[str, object] | list[dict[str, object]] | None = None,
    gap_payload: dict[str, object] | list[dict[str, object]] | None = None,
) -> None:
    scripts_dir = workspace / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    def _normalize_payloads(
        payload_or_payloads: dict[str, object] | list[dict[str, object]] | None,
        *,
        default: dict[str, object],
    ) -> list[dict[str, object]]:
        if payload_or_payloads is None:
            return [default]
        if isinstance(payload_or_payloads, list):
            return payload_or_payloads
        return [payload_or_payloads]

    def _collect_relpaths(value: object) -> tuple[str, ...]:
        relpaths: list[str] = []

        def _visit(item: object) -> None:
            if isinstance(item, dict):
                for nested in item.values():
                    _visit(nested)
                return
            if isinstance(item, list):
                for nested in item:
                    _visit(nested)
                return
            if isinstance(item, str) and (item.startswith("state/") or item.startswith("artifacts/")):
                relpaths.append(item)

        _visit(value)
        return tuple(dict.fromkeys(relpaths))

    def _write_script(name: str, payloads: list[dict[str, object]], relpaths: tuple[str, ...]) -> None:
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
                f"payloads = {payloads!r}",
                f"count_path = Path(__file__).with_name({name!r} + '.count')",
                "if count_path.exists():",
                "    index = int(count_path.read_text(encoding='utf-8'))",
                "else:",
                "    index = 0",
                "if index >= len(payloads):",
                "    raise SystemExit(f'unexpected call count for script: {index + 1}')",
                "payload = payloads[index]",
                "count_path.write_text(str(index + 1), encoding='utf-8')",
                "bundle_path.write_text(json.dumps(payload) + '\\n', encoding='utf-8')",
            ]
        )
        (scripts_dir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    selection_payloads = _normalize_payloads(
        selection_payload,
        default={"variant": "EMPTY"},
    )
    run_item_payloads = _normalize_payloads(
        run_item_payload,
        default={
            "variant": "CONTINUE",
            "summary-path": "artifacts/work/item-complete.md",
        },
    )
    gap_payloads = _normalize_payloads(
        gap_payload,
        default={"variant": "CONTINUE"},
    )

    _write_script(
        "select_next_item.py",
        selection_payloads,
        _collect_relpaths(selection_payloads),
    )
    _write_script(
        "execute_selected_item.py",
        run_item_payloads,
        _collect_relpaths(run_item_payloads),
    )
    _write_script(
        "draft_gap_item.py",
        gap_payloads,
        _collect_relpaths(gap_payloads),
    )


def _child_backlog_drain_workflow(result):
    lowered_workflows = getattr(result, "lowered_workflows", None)
    if lowered_workflows is None:
        lowered_workflows = result.entry_result.lowered_workflows
    return next(
        workflow
        for workflow in lowered_workflows
        if workflow.typed_workflow.definition.name == "std/drain::backlog-drain"
    )


def _parent_backlog_drain_loop_step(parent):
    """Return the parent's inline generic backlog-drain repeat_until step.

    Generic route: the macro expands to backlog-drain-proc + settle-drain-terminal,
    lowered inline into the caller; there is no std/drain::backlog-drain child.
    """
    loop_steps = [step for step in parent.authored_mapping["steps"] if "repeat_until" in step]
    assert len(loop_steps) == 1
    return loop_steps[0]


def _assert_parent_uses_generic_shared_terminal_lane(parent) -> None:
    """Assert the generic settle-drain-terminal lane lowered into the parent.

    Ports every intrinsic-route `_assert_child_backlog_drain_uses_shared_terminal_lane`
    check onto the generic route's lowered shape: per-terminal-case transition +
    summary materialization (consume-drain-terminal-effects) and the finalize
    projection (finalize-drain-terminal), both matching on the loop's terminal
    variant, with exact per-case request-binding refs, has_blocker flags,
    run-state absence, finalize artifact sourcing, and lane lineage.
    """
    loop_step = _parent_backlog_drain_loop_step(parent)
    assert loop_step["name"].endswith("__loop")
    loop_result_ref = (
        f"root.steps.{loop_step['name'][: -len('__loop')]}__result.artifacts."
    )
    consume_step = next(
        step
        for step in parent.authored_mapping["steps"]
        if "consume-drain-terminal-effects" in step.get("name", "")
    )
    finalize_step = next(
        step
        for step in parent.authored_mapping["steps"]
        if "finalize-drain-terminal" in step.get("name", "")
    )
    for match_step in (consume_step, finalize_step):
        assert tuple(match_step["match"]["cases"]) == (
            "EMPTY",
            "COMPLETED",
            "BLOCKED",
            "EXHAUSTED",
        )
        assert match_step["match"]["ref"] == f"{loop_result_ref}return__variant"
    recorded_variants = {
        "EMPTY": "EMPTY",
        "COMPLETED": "COMPLETED",
        "BLOCKED": "BLOCKED",
        "EXHAUSTED": "BLOCKED",
    }
    for case_name in ("EMPTY", "COMPLETED", "BLOCKED", "EXHAUSTED"):
        case_steps = consume_step["match"]["cases"][case_name]["steps"]
        transition_step = next(step for step in case_steps if "resource_transition" in step)
        summary_step = next(step for step in case_steps if "materialize_view" in step)
        case_step_names = [step["name"] for step in case_steps]
        assert case_step_names.index(transition_step["name"]) < case_step_names.index(
            summary_step["name"]
        )
        request_bindings = transition_step["resource_transition"]["request_bindings"]
        assert request_bindings["variant"] == recorded_variants[case_name]
        assert request_bindings["items_processed"] == {
            "ref": f"{loop_result_ref}return__items_processed"
        }
        assert request_bindings["progress_report_path"] == {
            "ref": f"{loop_result_ref}return__progress_report_path"
        }
        assert "run_state" not in request_bindings
        if case_name in ("BLOCKED", "EXHAUSTED"):
            assert request_bindings["has_blocker"] is True
            assert request_bindings["blocker_class"] == {
                "ref": f"{loop_result_ref}return__blocker_class"
            }
        else:
            assert request_bindings["has_blocker"] is False
            assert request_bindings["blocker_class"] == "missing_resource"
        finalize_case_steps = finalize_step["match"]["cases"][case_name]["steps"]
        result_step = next(
            step for step in finalize_case_steps if "materialize_artifacts" in step
        )
        result_values = result_step["materialize_artifacts"]["values"]
        assert all(value["name"] != "return__run-state" for value in result_values)
        variant_value = next(
            value for value in result_values if value["name"] == "return__variant"
        )
        assert variant_value["source"] == {"literal": recorded_variants[case_name]}
        if case_name in ("BLOCKED", "EXHAUSTED"):
            progress_value = next(
                value
                for value in result_values
                if value["name"] == "return__progress-report-path"
            )
            assert progress_value["source"] == {
                "ref": f"{loop_result_ref}return__progress_report_path"
            }
            blocker_value = next(
                value
                for value in result_values
                if value["name"] == "return__blocker-class"
            )
            assert blocker_value["source"] == {
                "ref": f"{loop_result_ref}return__blocker_class"
            }
        if case_name == "COMPLETED":
            items_value = next(
                value
                for value in result_values
                if value["name"] == "return__items-processed"
            )
            assert items_value["source"] == {
                "ref": f"{loop_result_ref}return__items_processed"
            }
    hidden_inputs = set(parent.origin_map.internal_input_spans)
    assert any(
        "consume_drain_terminal_effects" in input_name
        and input_name.endswith("__outcome__result_bundle")
        for input_name in hidden_inputs
    )
    generated_paths = set(parent.origin_map.generated_path_spans)
    assert any(
        path.endswith("record-drain-outcome-audit.jsonl") for path in generated_paths
    )
    assert "state/drain-run-state.json" not in repr(parent.authored_mapping)


def _parent_settle_terminal_result_ref(parent, artifact: str) -> str:
    parent_name = parent.typed_workflow.definition.name
    return (
        f"root.steps.{parent_name}"
        "__std/drain::settle-drain-terminal_1__std/drain::finalize-drain-terminal_1__match_terminal."
        f"artifacts.{artifact}"
    )


def _drain_transition_audit_rows(workspace: Path) -> list[dict[str, object]]:
    audit_paths = sorted((workspace / "state" / "workflow_lisp").rglob("*-record-drain-outcome.jsonl"))
    rows: list[dict[str, object]] = []
    for audit_path in audit_paths:
        rows.extend(
            json.loads(line)
            for line in audit_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return rows


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
                "    (EMPTY)",
                "    (GAP",
                "      (gap GapPayload))",
                "    (SELECTED",
                "      (selection SelectionPayload))",
                "    (BLOCKED",
                "      (reason String)))",
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
        if_block = step.get("if")
        if isinstance(if_block, dict):
            then_block = step.get("then")
            else_block = step.get("else")
            if isinstance(then_block, dict):
                yield from _iter_nested_steps(then_block.get("steps"))
            if isinstance(else_block, dict):
                yield from _iter_nested_steps(else_block.get("steps"))
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


def _assert_child_backlog_drain_uses_shared_terminal_lane(child) -> None:
    authored = child.authored_mapping
    child_name = child.typed_workflow.definition.name
    normalize_step = next(
        step for step in authored["steps"] if step.get("name") == "std/drain::backlog-drain__normalize_result"
    )

    assert normalize_step["match"]["ref"] == (
        f"root.steps.{child_name}__terminal_carrier.artifacts.terminal__variant"
    )
    assert tuple(normalize_step["match"]["cases"]) == (
        "EMPTY",
        "COMPLETED",
        "BLOCKED",
        "EXHAUSTED",
    )
    for case_name in ("EMPTY", "COMPLETED", "BLOCKED", "EXHAUSTED"):
        case_steps = normalize_step["match"]["cases"][case_name]["steps"]
        transition_step = next(step for step in case_steps if "resource_transition" in step)
        summary_step = next(step for step in case_steps if "materialize_view" in step)
        result_step = next(step for step in case_steps if "materialize_artifacts" in step)
        case_step_names = [step["name"] for step in case_steps]
        assert "shared_drain_result" in transition_step["name"]
        assert result_step["name"] == f"{transition_step['name']}__result"
        assert summary_step["name"] == f"{transition_step['name']}__summary"
        assert case_step_names.index(result_step["name"]) < case_step_names.index(transition_step["name"])
        assert case_step_names.index(result_step["name"]) < case_step_names.index(summary_step["name"])
        request_bindings = transition_step["resource_transition"]["request_bindings"]
        assert request_bindings["variant"] in ("EMPTY", "COMPLETED", "BLOCKED")
        assert request_bindings["items_processed"] == {
            "ref": (
                f"root.steps.{child_name}__terminal_carrier.artifacts."
                "terminal__items-processed"
            )
        }
        assert "run_state" not in request_bindings
        assert request_bindings["progress_report_path"] == {
            "ref": (
                f"root.steps.{child_name}__terminal_carrier.artifacts."
                "terminal__progress-report-path"
            )
        }
        assert request_bindings["blocker_class"] == {
            "ref": (
                f"root.steps.{child_name}__terminal_carrier.artifacts."
                "terminal__blocker-class"
            )
        }
        if case_name in ("BLOCKED", "EXHAUSTED"):
            assert request_bindings["has_blocker"] is True
        else:
            assert request_bindings["has_blocker"] is False
        progress_field = next(
            value
            for value in result_step["materialize_artifacts"]["values"]
            if value["name"] == "return__progress-report-path"
        )
        assert all(
            value["name"] != "return__run-state"
            for value in result_step["materialize_artifacts"]["values"]
        )
        assert progress_field["source"] == {
            "ref": (
                f"root.steps.{child_name}__terminal_carrier.artifacts."
                "terminal__progress-report-path"
            )
        }
    hidden_inputs = set(child.origin_map.internal_input_spans)
    assert any("shared_drain_result" in input_name for input_name in hidden_inputs)
    generated_paths = set(child.origin_map.generated_path_spans)
    assert any(path.endswith("shared-drain-result-record-drain-outcome.jsonl") for path in generated_paths)
    assert "state/drain-run-state.json" not in repr(authored)


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


@pytest.mark.parametrize(
    "entry_workflow",
    (
        None,
        "entry",
        "private_exec_context/drain_ctx::entry",
    ),
)
def test_promoted_entry_DrainCtx_hidden_binding_reports_unsupported_private_exec_bootstrap(
    tmp_path: Path,
    entry_workflow: str | None,
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
            entry_workflow=entry_workflow,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "private_exec_context_bootstrap_unsupported"
    assert "DrainCtx" in diagnostic.message


def test_workflow_ref_resolution_rejects_signature_mismatch() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_SIGNATURE_FIXTURE)

    assert excinfo.value.diagnostics[0].code == "workflow_call_signature_erased"


def test_workflow_ref_resolution_rejects_selector_empty_extra_fields(tmp_path: Path) -> None:
    path = tmp_path / "selector_empty_extra_fields.orc"
    path.write_text(
        VALID_DRAIN_FIXTURE.read_text(encoding="utf-8").replace(
            "    (EMPTY)",
            "    (EMPTY\n      (extra StateExisting))",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    assert excinfo.value.diagnostics[0].code == "workflow_call_signature_erased"


def test_workflow_ref_resolution_accepts_selector_empty_without_fields(tmp_path: Path) -> None:
    path = tmp_path / "selector_empty_run_state_omission.orc"
    path.write_text(VALID_DRAIN_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    _typecheck_fixture(path)


def test_workflow_ref_resolution_allows_imported_family_owned_selection_result_empty_without_run_state(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "pkg"
    package_dir.mkdir(parents=True)
    (package_dir / "types.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pkg/types)",
                "  (import std/resource :only (BlockerClass WorkReport StateExisting))",
                "  (export StateFile RunCtx DrainCtx ItemCtx SelectionPayload GapPayload",
                "          SelectionResult SelectedItemResult GapDraftResult DrainResult)",
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
                "  (defunion SelectionResult",
                "    (EMPTY)",
                "    (GAP",
                "      (gap GapPayload))",
                "    (SELECTED",
                "      (selection SelectionPayload))",
                "    (BLOCKED",
                "      (reason String)))",
                "  (defunion SelectedItemResult",
                "    (CONTINUE",
                "      (summary-path WorkReport))",
                "    (BLOCKED",
                "      (summary-path WorkReport)",
                "      (blocker-class BlockerClass)))",
                "  (defunion GapDraftResult",
                "    (CONTINUE)",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass)))",
                "  (defunion DrainResult",
                "    (EMPTY)",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass))",
                "    (COMPLETED",
                "      (items-processed Int))))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "handlers.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pkg/handlers)",
                "  (import std/resource :only (BlockerClass WorkReport StateExisting))",
                "  (import pkg/types :only (DrainCtx GapDraftResult GapPayload ItemCtx",
                "                            SelectedItemResult SelectionPayload SelectionResult))",
                "  (export selector-run run-selected-item gap-draft)",
                "  (defworkflow selector-run",
                "    ((ctx DrainCtx))",
                "    -> SelectionResult",
                "    (command-result select_next_item",
                '      :argv ("python" "scripts/select_next_item.py" ctx.manifest)',
                "      :returns SelectionResult))",
                "  (defworkflow run-selected-item",
                "    ((item-ctx ItemCtx)",
                "     (selection SelectionPayload))",
                "    -> SelectedItemResult",
                "    (command-result execute_selected_item",
                '      :argv ("python" "scripts/execute_selected_item.py" selection.item-id)',
                "      :returns SelectedItemResult))",
                "  (defworkflow gap-draft",
                "    ((ctx DrainCtx)",
                "     (gap GapPayload))",
                "    -> GapDraftResult",
                "    (command-result draft_gap_item",
                '      :argv ("python" "scripts/draft_gap_item.py" gap.gap-id)',
                "      :returns GapDraftResult)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    entry_path = package_dir / "entry.orc"
    entry_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pkg/entry)",
                "  (import std/resource :only (BlockerClass WorkReport StateExisting))",
                "  (import pkg/types :only (DrainCtx DrainResult))",
                "  (import pkg/handlers :only (selector-run run-selected-item gap-draft))",
                "  (export drain)",
                "  (defworkflow drain",
                "    ((ctx DrainCtx)",
                "     (max-iterations Int))",
                "    -> DrainResult",
                "    (backlog-drain pkg",
                "      :ctx ctx",
                "      :selector selector-run",
                "      :run-item run-selected-item",
                "      :gap-drafter gap-draft",
                "      :max-iterations 4)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        entry_path,
        source_roots=(tmp_path,),
        command_boundaries=_command_boundaries().bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path,
        entry_workflow="drain",
    )

    assert "pkg/entry" in result.compiled_results_by_name


def _write_custom_backlog_drain_union_fixture(
    tmp_path: Path,
    *,
    selection_variants: list[str] | None = None,
    selected_item_variants: list[str] | None = None,
    gap_result_variants: list[str] | None = None,
    drain_result_variants: list[str] | None = None,
) -> Path:
    package_dir = tmp_path / "custom_pkg"
    package_dir.mkdir(parents=True)
    (package_dir / "types.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule custom_pkg/types)",
                "  (import std/resource :only (BlockerClass WorkReport StateExisting))",
                "  (export StateFile RunCtx DrainCtx ItemCtx SelectionPayload GapPayload",
                "          CustomSelectionResult CustomSelectedItemResult CustomGapDraftResult DrainResult)",
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
                "  (defunion CustomSelectionResult",
                *(selection_variants or [
                    "    (EMPTY)",
                    "    (GAP",
                    "      (gap GapPayload))",
                    "    (SELECTED",
                    "      (selection SelectionPayload))",
                    "    (BLOCKED",
                    "      (reason String)))",
                ]),
                "  (defunion CustomSelectedItemResult",
                *(selected_item_variants or [
                    "    (CONTINUE",
                    "      (summary-path WorkReport))",
                    "    (BLOCKED",
                    "      (summary-path WorkReport)",
                    "      (blocker-class BlockerClass)))",
                ]),
                "  (defunion CustomGapDraftResult",
                *(gap_result_variants or [
                    "    (CONTINUE)",
                    "    (BLOCKED",
                    "      (progress-report-path WorkReport)",
                    "      (blocker-class BlockerClass)))",
                ]),
                "  (defunion DrainResult",
                *(drain_result_variants or [
                    "    (EMPTY)",
                    "    (BLOCKED",
                    "      (progress-report-path WorkReport)",
                    "      (blocker-class BlockerClass))",
                    "    (COMPLETED",
                    "      (items-processed Int))))",
                ]),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "handlers.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule custom_pkg/handlers)",
                "  (import std/resource :only (BlockerClass WorkReport StateExisting))",
                "  (import custom_pkg/types :only (CustomGapDraftResult CustomSelectionResult",
                "                                   CustomSelectedItemResult DrainCtx GapPayload",
                "                                   ItemCtx SelectionPayload))",
                "  (export selector-run run-selected-item gap-draft)",
                "  (defworkflow selector-run",
                "    ((ctx DrainCtx))",
                "    -> CustomSelectionResult",
                "    (command-result select_next_item",
                '      :argv ("python" "scripts/select_next_item.py" ctx.manifest)',
                "      :returns CustomSelectionResult))",
                "  (defworkflow run-selected-item",
                "    ((item-ctx ItemCtx)",
                "     (selection SelectionPayload))",
                "    -> CustomSelectedItemResult",
                "    (command-result execute_selected_item",
                '      :argv ("python" "scripts/execute_selected_item.py" selection.item-id)',
                "      :returns CustomSelectedItemResult))",
                "  (defworkflow gap-draft",
                "    ((ctx DrainCtx)",
                "     (gap GapPayload))",
                "    -> CustomGapDraftResult",
                "    (command-result draft_gap_item",
                '      :argv ("python" "scripts/draft_gap_item.py" gap.gap-id)',
                "      :returns CustomGapDraftResult)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    entry_path = package_dir / "entry.orc"
    entry_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule custom_pkg/entry)",
                "  (import std/resource :only (BlockerClass WorkReport StateExisting))",
                "  (import custom_pkg/types :only (DrainCtx DrainResult))",
                "  (import custom_pkg/handlers :only (selector-run run-selected-item gap-draft))",
                "  (export drain)",
                "  (defworkflow drain",
                "    ((ctx DrainCtx)",
                "     (max-iterations Int))",
                "    -> DrainResult",
                "    (backlog-drain custom_pkg",
                "      :ctx ctx",
                "      :selector selector-run",
                "      :run-item run-selected-item",
                "      :gap-drafter gap-draft",
                "      :max-iterations 4)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return entry_path


@pytest.mark.parametrize(
    (
        "selection_variants",
        "selected_item_variants",
        "gap_result_variants",
        "drain_result_variants",
    ),
    [
        (
            [
                "    (EMPTY",
                "      (run-state StateExisting))",
                "    (GAP",
                "      (gap GapPayload))",
                "    (SELECTED",
                "      (selection SelectionPayload))",
                "    (BLOCKED",
                "      (reason String)))",
            ],
            None,
            None,
            None,
        ),
        (
            None,
            [
                "    (CONTINUE",
                "      (summary-path WorkReport)",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (summary-path WorkReport)",
                "      (blocker-class BlockerClass)",
                "      (run-state StateExisting)))",
            ],
            None,
            None,
        ),
        (
            None,
            None,
            [
                "    (CONTINUE",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass)))",
            ],
            None,
        ),
        (
            None,
            None,
            None,
            [
                "    (EMPTY",
                "      (run-state StateExisting))",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass))",
                "    (COMPLETED",
                "      (items-processed Int)",
                "      (run-state StateExisting))))",
            ],
        ),
    ],
    ids=(
        "selector_empty_run_state",
        "selected_item_run_state",
        "gap_continue_run_state",
        "drain_result_run_state",
    ),
)
def test_workflow_ref_resolution_rejects_custom_union_run_state_carriers(
    tmp_path: Path,
    selection_variants: list[str] | None,
    selected_item_variants: list[str] | None,
    gap_result_variants: list[str] | None,
    drain_result_variants: list[str] | None,
) -> None:
    entry_path = _write_custom_backlog_drain_union_fixture(
        tmp_path,
        selection_variants=selection_variants,
        selected_item_variants=selected_item_variants,
        gap_result_variants=gap_result_variants,
        drain_result_variants=drain_result_variants,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            entry_path,
            source_roots=(tmp_path,),
            command_boundaries=_custom_union_command_boundaries().bindings_by_name,
            validate_shared=False,
            workspace_root=tmp_path,
            entry_workflow="drain",
        )

    assert excinfo.value.diagnostics[0].code == "workflow_call_signature_erased"


def test_workflow_ref_resolution_rejects_selector_blocked_reason_type_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "selector_blocked_reason_type_mismatch.orc"
    path.write_text(
        VALID_DRAIN_FIXTURE.read_text(encoding="utf-8").replace(
            "    (BLOCKED\n      (reason String)))",
            "    (BLOCKED\n      (reason Int)))",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    assert excinfo.value.diagnostics[0].code == "workflow_call_signature_erased"


def test_workflow_ref_resolution_rejects_selector_blocked_reason_omission() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_SELECTOR_BLOCKED_REASON_MISSING_FIXTURE)

    assert excinfo.value.diagnostics[0].code == "workflow_call_signature_erased"


def test_workflow_ref_resolution_rejects_selector_blocked_extra_state_field() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_SELECTOR_BLOCKED_EXTRA_STATE_FIELD_FIXTURE)

    assert excinfo.value.diagnostics[0].code == "workflow_call_signature_erased"


def test_workflow_ref_union_call_boundary_projection_rejects_unproved_variant_access() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_UNION_BOUNDARY_FIXTURE)

    assert excinfo.value.diagnostics[0].code == "variant_ref_unproved"


def test_workflow_ref_resolution_rejects_gap_drafter_non_record_payload(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_linked_stdlib_fixture(
            INVALID_GAP_DRAFTER_NON_RECORD_PAYLOAD_FIXTURE,
            tmp_path=tmp_path,
            lowering_route=LoweringRoute.WCC_M4,
            validate_shared=False,
        )

    assert excinfo.value.diagnostics[0].code == "workflow_call_signature_erased"


def test_lowering_backlog_drain_uses_repeat_until_with_typed_accumulator(tmp_path: Path) -> None:
    _workflow_path, entry_result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_CALLABLE_BOUNDARY_FIXTURE,
        tmp_path=tmp_path,
        lowering_route=LoweringRoute.WCC_M4,
        validate_shared=False,
    )
    parent = next(
        workflow
        for workflow in entry_result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::drain")
    )
    child = next(
        workflow
        for workflow in entry_result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == "std/drain::backlog-drain"
    )
    parent_call = next(
        step
        for step in _iter_nested_steps(parent.authored_mapping["steps"])
        if step.get("call") == "std/drain::backlog-drain"
    )
    authored = child.authored_mapping
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    body_steps = list(_iter_nested_steps(repeat_step["repeat_until"]["steps"]))
    call_targets = {step.get("call") for step in body_steps if isinstance(step.get("call"), str)}

    assert not any("repeat_until" in step for step in parent.authored_mapping["steps"])
    assert parent_call["id"] in parent.origin_map.step_spans
    assert repeat_step["repeat_until"]["steps"]
    assert any(target and target.endswith("selector-run") for target in call_targets)
    assert any(target and target.endswith("run-selected-item") for target in call_targets)
    assert any(target and target.endswith("gap-draft") for target in call_targets)
    selector_call = next(step for step in body_steps if step.get("call", "").endswith("selector-run"))
    run_item_call = next(step for step in body_steps if step.get("call", "").endswith("run-selected-item"))
    gap_drafter_call = next(step for step in body_steps if step.get("call", "").endswith("gap-draft"))
    selector_write_root_name = next(name for name in selector_call["with"] if name.startswith("__write_root__"))
    run_item_write_root_name = next(name for name in run_item_call["with"] if name.startswith("__write_root__"))
    gap_write_root_name = next(name for name in gap_drafter_call["with"] if name.startswith("__write_root__"))

    assert selector_call["with"] == {
        "ctx__run__run-id": {"ref": "inputs.ctx__run__run-id"},
        "ctx__run__state-root": {"ref": "inputs.ctx__run__state-root"},
        "ctx__run__artifact-root": {"ref": "inputs.ctx__run__artifact-root"},
        "ctx__state-root": {"ref": "inputs.ctx__state-root"},
        "ctx__manifest": {"ref": "inputs.ctx__manifest"},
        "ctx__ledger": {"ref": "inputs.ctx__ledger"},
        selector_write_root_name: {
            "ref": (
                "self.steps.std/drain::backlog-drain__selector__managed_write_roots.artifacts."
                f"{selector_write_root_name}"
            )
        },
    }
    assert run_item_call["with"] == {
        "item-ctx__run__run-id": {"ref": "inputs.ctx__run__run-id"},
        "item-ctx__run__state-root": {"ref": "inputs.ctx__run__state-root"},
        "item-ctx__run__artifact-root": {"ref": "inputs.ctx__run__artifact-root"},
        "item-ctx__item-id": {"ref": "self.steps.std/drain::backlog-drain__selector.artifacts.return__selection__item-id"},
        "item-ctx__state-root": {"ref": "self.steps.std/drain::backlog-drain__selector.artifacts.return__selection__item-state-root"},
        "item-ctx__artifact-root": {"ref": "inputs.ctx__run__artifact-root"},
        "item-ctx__ledger": {"ref": "inputs.ctx__ledger"},
        "selection__item-id": {"ref": "self.steps.std/drain::backlog-drain__selector.artifacts.return__selection__item-id"},
        "selection__item-state-root": {"ref": "self.steps.std/drain::backlog-drain__selector.artifacts.return__selection__item-state-root"},
        run_item_write_root_name: {
            "ref": (
                "self.steps.std/drain::backlog-drain__run_item__managed_write_roots.artifacts."
                f"{run_item_write_root_name}"
            )
        },
    }
    assert gap_drafter_call["with"] == {
        "ctx__run__run-id": {"ref": "inputs.ctx__run__run-id"},
        "ctx__run__state-root": {"ref": "inputs.ctx__run__state-root"},
        "ctx__run__artifact-root": {"ref": "inputs.ctx__run__artifact-root"},
        "ctx__state-root": {"ref": "inputs.ctx__state-root"},
        "ctx__manifest": {"ref": "inputs.ctx__manifest"},
        "ctx__ledger": {"ref": "inputs.ctx__ledger"},
        "gap__gap-id": {
            "ref": "self.steps.std/drain::backlog-drain__selector.artifacts.return__gap__gap-id"
        },
        gap_write_root_name: {
            "ref": (
                "self.steps.std/drain::backlog-drain__gap_drafter__managed_write_roots.artifacts."
                f"{gap_write_root_name}"
            )
        },
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
    )
    assert not any("resource_transition" in step for step in body_steps)
    assert not any("materialize_view" in step for step in body_steps)
    assert not any(
        step.get("command", [])[:3] == ["python", "-m", "orchestrator.workflow_lisp.adapters.normalize_drain_result"]
        for step in authored["steps"]
        if isinstance(step, dict)
    )


def test_parent_terminal_reprojection_loop_call_generated_paths_fit_filesystem_segments(
    tmp_path: Path,
) -> None:
    _workflow_path, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_PARENT_TERMINAL_REPROJECTION_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )

    parent = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::drain")
    )
    loop_call_paths = [
        allocation.concrete_path_template
        for allocation in parent.generated_path_allocations
        if allocation.concrete_path_template.startswith(".orchestrate/workflow_lisp/calls/")
        or allocation.concrete_path_template.startswith(".orchestrate/workflow_lisp/call_bindings/")
    ]

    assert loop_call_paths
    for path in loop_call_paths:
        assert max(len(segment) for segment in path.split("/")) <= 255, path


def test_compile_stage3_module_preserves_imported_backlog_drain_as_callable_boundary(
    tmp_path: Path,
) -> None:
    _workflow_path, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_CALLABLE_BOUNDARY_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    drain = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::drain")
    )
    authored = drain.authored_mapping
    call_steps = [
        step
        for step in _iter_nested_steps(authored["steps"])
        if isinstance(step.get("call"), str)
    ]
    stdlib_call = next(step for step in call_steps if step.get("call") == "std/drain::backlog-drain")
    stdlib_boundary = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == "std/drain::backlog-drain"
    )
    repeat_step = next(step for step in stdlib_boundary.authored_mapping["steps"] if "repeat_until" in step)
    boundary_step_ids = {
        step_id
        for step in _iter_nested_steps(stdlib_boundary.authored_mapping["steps"])
        if isinstance((step_id := step.get("id")), str)
    }

    assert not any("repeat_until" in step for step in authored["steps"])
    assert stdlib_call["id"] in drain.origin_map.step_spans
    assert repeat_step["repeat_until"]["max_iterations"] == 4
    assert boundary_step_ids
    assert all(step_id in stdlib_boundary.origin_map.step_spans for step_id in boundary_step_ids)
    assert not boundary_step_ids.intersection(drain.origin_map.step_spans)


def test_callable_boundary_bundle_preserves_entry_ctx_hidden_binding_metadata(
    tmp_path: Path,
) -> None:
    _, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_CALLABLE_BOUNDARY_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )
    bundle = next(
        bundle
        for workflow_name, bundle in result.entry_result.validated_bundles.items()
        if workflow_name.endswith("::drain")
    )
    boundary = workflow_boundary_projection(bundle)

    assert len(boundary.private_runtime_context_bindings) == 1
    binding = boundary.private_runtime_context_bindings[0]
    assert binding.binding_id == "ctx"
    assert binding.source_param_name == "ctx"
    assert binding.context_family == "DrainCtx"
    assert binding.bridge_class == "imported_adapter_carried_context"
    assert binding.generated_input_names == (
        "ctx__run__run-id",
        "ctx__run__state-root",
        "ctx__run__artifact-root",
        "ctx__state-root",
        "ctx__manifest",
        "ctx__ledger",
    )
    assert binding.projection_hints == {
        "context_binding_schema_version": 1,
        "context_input_roles": {
            "ctx__run__run-id": "run_anchor:run-id",
            "ctx__run__state-root": "run_anchor:state-root",
            "ctx__run__artifact-root": "run_anchor:artifact-root",
        },
        "carried_input_sources": {
            "ctx__run__run-id": ("ctx", "run", "run-id"),
            "ctx__run__state-root": ("ctx", "run", "state-root"),
            "ctx__run__artifact-root": ("ctx", "run", "artifact-root"),
            "ctx__state-root": ("ctx", "state-root"),
            "ctx__manifest": ("ctx", "manifest"),
            "ctx__ledger": ("ctx", "ledger"),
        },
    }


def test_same_file_callable_boundary_preserves_generated_backlog_drain_owner_lane(
    tmp_path: Path,
) -> None:
    result = _compile(
        VALID_DRAIN_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
        lowering_route=LoweringRoute.WCC_M4,
    )

    parent = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "drain"
    )
    child = _child_backlog_drain_workflow(result)
    call_step = next(
        step
        for step in _iter_nested_steps(parent.authored_mapping["steps"])
        if step.get("call") == "std/drain::backlog-drain"
    )
    repeat_step = next(step for step in child.authored_mapping["steps"] if "repeat_until" in step)

    assert not any("repeat_until" in step for step in parent.authored_mapping["steps"])
    assert call_step["id"] in parent.origin_map.step_spans
    assert repeat_step["repeat_until"]["max_iterations"] == 4
    _assert_child_backlog_drain_uses_shared_terminal_lane(child)


def test_callable_boundary_fixture_uses_direct_helper_head() -> None:
    source = VALID_STDLIB_CALLABLE_BOUNDARY_FIXTURE.read_text(encoding="utf-8")

    assert "(backlog-drain-callable-boundary neurips" in source


def test_compile_stage3_module_preserves_parent_terminal_reprojection_over_imported_backlog_drain(
    tmp_path: Path,
) -> None:
    _workflow_path, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_PARENT_TERMINAL_REPROJECTION_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    parent = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::drain")
    )
    # Generic route: the backlog-drain proc and its settle-terminal lane lower
    # inline into the parent; no std/drain::backlog-drain child is synthesized.
    loop_step = _parent_backlog_drain_loop_step(parent)
    projection_step = next(
        step
        for step in parent.authored_mapping["steps"]
        if "project-parent-drain-result" in step.get("name", "")
    )

    assert parent.typed_workflow.signature.return_type_ref.name == "ParentTerminalResult"
    assert not any(
        workflow.typed_workflow.definition.name == "std/drain::backlog-drain"
        for workflow in result.entry_result.lowered_workflows
    )
    assert loop_step["repeat_until"]["max_iterations"] == 4
    assert loop_step["id"] in parent.origin_map.step_spans
    assert projection_step["match"]["ref"] == _parent_settle_terminal_result_ref(
        parent, "return__variant"
    )
    assert tuple(projection_step["match"]["cases"]) == ("EMPTY", "COMPLETED", "BLOCKED")
    _assert_parent_uses_generic_shared_terminal_lane(parent)


def test_parent_terminal_reprojection_preserves_imported_call_and_projection_provenance(
    tmp_path: Path,
) -> None:
    _workflow_path, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_PARENT_TERMINAL_REPROJECTION_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )

    parent = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::drain")
    )
    # Generic route: the imported loop and terminal lane live in the parent;
    # provenance must cover the loop step and the settle-terminal match steps.
    loop_step = _parent_backlog_drain_loop_step(parent)
    projection_step = next(
        step
        for step in parent.authored_mapping["steps"]
        if "project-parent-drain-result" in step.get("name", "")
    )
    case_steps = {
        case_name: projection_step["match"]["cases"][case_name]["steps"]
        for case_name in ("EMPTY", "COMPLETED", "BLOCKED")
    }
    imported_lane_step_ids = {
        step_id
        for step in parent.authored_mapping["steps"]
        if (
            "consume-drain-terminal-effects" in step.get("name", "")
            or "finalize-drain-terminal" in step.get("name", "")
        )
        and isinstance((step_id := step.get("id")), str)
    }
    imported_lane_step_ids.add(loop_step["id"])

    assert projection_step["id"] in parent.origin_map.step_spans
    assert parent.origin_map.step_spans[projection_step["id"]].origin_key
    for case_name, steps in case_steps.items():
        for step in steps:
            step_id = step.get("id")
            assert isinstance(step_id, str), case_name
            assert step_id in parent.origin_map.step_spans
            assert parent.origin_map.step_spans[step_id].origin_key
    assert imported_lane_step_ids
    assert all(step_id in parent.origin_map.step_spans for step_id in imported_lane_step_ids)
    assert all(
        parent.origin_map.step_spans[step_id].origin_key
        for step_id in imported_lane_step_ids
    )


@pytest.mark.parametrize(
    (
        "selection_payload",
        "run_item_payload",
        "gap_payload",
        "max_iterations",
        "expected_outputs",
    ),
    (
        (
            {"variant": "EMPTY"},
            None,
            None,
            4,
            {
                "return__variant": "DONE",
                "return__items-processed": 0,
            },
        ),
        (
            [
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-1", "item-state-root": "state/items/item-1"},
                },
                {"variant": "EMPTY"},
            ],
            [
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-complete.md",
                }
            ],
            None,
            4,
            {
                "return__variant": "DONE",
                "return__items-processed": 1,
            },
        ),
        (
            {"variant": "BLOCKED", "reason": "selector_blocked"},
            None,
            None,
            4,
            {
                "return__variant": "BLOCKED",
                "return__progress-report-path": "artifacts/work/drain-progress-report.md",
                "return__blocker-class": "user_decision_required",
            },
        ),
        (
            [
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-1", "item-state-root": "state/items/item-1"},
                },
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-2", "item-state-root": "state/items/item-2"},
                },
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-3", "item-state-root": "state/items/item-3"},
                },
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-4", "item-state-root": "state/items/item-4"},
                },
            ],
            [
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-1-progress.md",
                },
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-2-progress.md",
                },
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-3-progress.md",
                },
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-4-progress.md",
                },
            ],
            None,
            4,
            {
                "return__variant": "BLOCKED",
                "return__progress-report-path": "artifacts/work/item-4-progress.md",
                "return__blocker-class": "unrecoverable_after_fix_attempt",
            },
        ),
    ),
)
def test_parent_terminal_reprojection_executes_projected_parent_outputs(
    tmp_path: Path,
    selection_payload: dict[str, object] | list[dict[str, object]],
    run_item_payload: dict[str, object] | list[dict[str, object]] | None,
    gap_payload: dict[str, object] | list[dict[str, object]] | None,
    max_iterations: int,
    expected_outputs: dict[str, object],
) -> None:
    workflow_path, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_PARENT_TERMINAL_REPROJECTION_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )
    bundle = next(
        bundle
        for workflow_name, bundle in result.entry_result.validated_bundles.items()
        if workflow_name.endswith("::drain")
    )
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
    placeholder_path = tmp_path / "artifacts" / "work" / "placeholder.txt"
    placeholder_path.write_text("seed\n", encoding="utf-8")
    ledger_path = tmp_path / "state" / "runtime" / "ledger.json"
    ledger_path.write_text("[]\n", encoding="utf-8")

    state = _execute_bundle(
        bundle,
        workflow_path=workflow_path,
        workspace=tmp_path,
        run_id="drain-parent-reprojection-runtime",
        inputs={
            "ctx__run__run-id": "drain-parent-reprojection-runtime",
            "ctx__run__state-root": "state/runtime",
            "ctx__run__artifact-root": "artifacts/work",
            "ctx__state-root": "state/runtime",
            "ctx__manifest": "state/runtime/manifest.json",
            "ctx__ledger": "state/runtime/ledger.json",
            "max-iterations": max_iterations,
        },
    )

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == expected_outputs


def test_compile_stage3_module_preserves_branch_local_terminal_contract_alignment_over_imported_backlog_drain(
    tmp_path: Path,
) -> None:
    _workflow_path, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_BRANCH_LOCAL_TERMINAL_CONTRACT_ALIGNMENT_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    parent = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::drain")
    )
    bundle = next(
        bundle
        for workflow_name, bundle in result.entry_result.validated_bundles.items()
        if workflow_name.endswith("::drain")
    )
    # Generic route: the backlog-drain proc and its settle-terminal lane lower
    # inline into the parent; no std/drain::backlog-drain child is synthesized.
    loop_step = _parent_backlog_drain_loop_step(parent)
    projection_step = next(
        step
        for step in parent.authored_mapping["steps"]
        if "project-parent-drain-result" in step.get("name", "")
    )
    blocked_step = projection_step["match"]["cases"]["BLOCKED"]["steps"][0]
    blocked_values = blocked_step["materialize_artifacts"]["values"]
    reason_value = next(value for value in blocked_values if value["name"] == "return__reason")

    assert parent.typed_workflow.signature.return_type_ref.name == "ParentTerminalResult"
    assert not any(
        workflow.typed_workflow.definition.name == "std/drain::backlog-drain"
        for workflow in result.entry_result.lowered_workflows
    )
    assert loop_step["id"] in parent.origin_map.step_spans
    assert projection_step["match"]["ref"] == _parent_settle_terminal_result_ref(
        parent, "return__variant"
    )
    assert tuple(projection_step["match"]["cases"]) == ("EMPTY", "COMPLETED", "BLOCKED")
    assert "return__blocker-class" not in parent.authored_mapping.get("outputs", {})
    assert "return__blocker-class" not in bundle.surface.outputs
    assert reason_value["source"] == {
        "ref": _parent_settle_terminal_result_ref(parent, "return__blocker-class")
    }
    _assert_parent_uses_generic_shared_terminal_lane(parent)


def test_branch_local_terminal_contract_alignment_preserves_imported_call_and_projection_provenance(
    tmp_path: Path,
) -> None:
    _workflow_path, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_BRANCH_LOCAL_TERMINAL_CONTRACT_ALIGNMENT_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )

    parent = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::drain")
    )
    # Generic route: the imported loop and terminal lane live in the parent;
    # provenance must cover the loop step and the settle-terminal match steps.
    loop_step = _parent_backlog_drain_loop_step(parent)
    projection_step = next(
        step
        for step in parent.authored_mapping["steps"]
        if "project-parent-drain-result" in step.get("name", "")
    )
    case_steps = {
        case_name: projection_step["match"]["cases"][case_name]["steps"]
        for case_name in ("EMPTY", "COMPLETED", "BLOCKED")
    }
    blocked_values = case_steps["BLOCKED"][0]["materialize_artifacts"]["values"]
    imported_lane_step_ids = {
        step_id
        for step in parent.authored_mapping["steps"]
        if (
            "consume-drain-terminal-effects" in step.get("name", "")
            or "finalize-drain-terminal" in step.get("name", "")
        )
        and isinstance((step_id := step.get("id")), str)
    }
    imported_lane_step_ids.add(loop_step["id"])

    assert projection_step["id"] in parent.origin_map.step_spans
    assert parent.origin_map.step_spans[projection_step["id"]].origin_key
    for case_name, steps in case_steps.items():
        for step in steps:
            step_id = step.get("id")
            assert isinstance(step_id, str), case_name
            assert step_id in parent.origin_map.step_spans
            assert parent.origin_map.step_spans[step_id].origin_key
    assert any(
        value["name"] == "return__reason"
        and value["source"]
        == {"ref": _parent_settle_terminal_result_ref(parent, "return__blocker-class")}
        for value in blocked_values
    )
    assert "return__blocker-class" not in parent.authored_mapping.get("outputs", {})
    assert imported_lane_step_ids
    assert all(step_id in parent.origin_map.step_spans for step_id in imported_lane_step_ids)
    assert all(
        parent.origin_map.step_spans[step_id].origin_key
        for step_id in imported_lane_step_ids
    )


@pytest.mark.parametrize(
    (
        "selection_payload",
        "run_item_payload",
        "gap_payload",
        "expected_outputs",
    ),
    (
        (
            {"variant": "EMPTY"},
            None,
            None,
            {
                "return__variant": "DONE",
                "return__items-processed": 0,
            },
        ),
        (
            {"variant": "BLOCKED", "reason": "selector_blocked"},
            None,
            None,
            {
                "return__variant": "BLOCKED",
                "return__progress-report-path": "artifacts/work/drain-progress-report.md",
                "return__reason": "user_decision_required",
            },
        ),
        (
            [
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-1", "item-state-root": "state/items/item-1"},
                },
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-2", "item-state-root": "state/items/item-2"},
                },
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-3", "item-state-root": "state/items/item-3"},
                },
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-4", "item-state-root": "state/items/item-4"},
                },
            ],
            [
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-1-progress.md",
                },
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-2-progress.md",
                },
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-3-progress.md",
                },
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-4-progress.md",
                },
            ],
            None,
            {
                "return__variant": "BLOCKED",
                "return__progress-report-path": "artifacts/work/item-4-progress.md",
                "return__reason": "unrecoverable_after_fix_attempt",
            },
        ),
    ),
)
def test_branch_local_terminal_contract_alignment_executes_parent_outputs_without_public_blocker_class(
    tmp_path: Path,
    selection_payload: dict[str, object] | list[dict[str, object]],
    run_item_payload: dict[str, object] | list[dict[str, object]] | None,
    gap_payload: dict[str, object] | list[dict[str, object]] | None,
    expected_outputs: dict[str, object],
) -> None:
    workflow_path, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_BRANCH_LOCAL_TERMINAL_CONTRACT_ALIGNMENT_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )
    bundle = next(
        bundle
        for workflow_name, bundle in result.entry_result.validated_bundles.items()
        if workflow_name.endswith("::drain")
    )
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
    placeholder_path = tmp_path / "artifacts" / "work" / "placeholder.txt"
    placeholder_path.write_text("seed\n", encoding="utf-8")
    ledger_path = tmp_path / "state" / "runtime" / "ledger.json"
    ledger_path.write_text("[]\n", encoding="utf-8")

    state = _execute_bundle(
        bundle,
        workflow_path=workflow_path,
        workspace=tmp_path,
        run_id="drain-branch-local-contract-alignment-runtime",
        inputs={
            "ctx__run__run-id": "drain-branch-local-contract-alignment-runtime",
            "ctx__run__state-root": "state/runtime",
            "ctx__run__artifact-root": "artifacts/work",
            "ctx__state-root": "state/runtime",
            "ctx__manifest": "state/runtime/manifest.json",
            "ctx__ledger": "state/runtime/ledger.json",
            "max-iterations": 4,
        },
    )

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == expected_outputs
    assert "return__blocker-class" not in state["workflow_outputs"]


def test_compile_stage3_module_carries_rich_gap_payload_across_callable_boundary(
    tmp_path: Path,
) -> None:
    _workflow_path, entry_result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_CALLABLE_BOUNDARY_RICH_GAP_FIXTURE,
        tmp_path=tmp_path,
        lowering_route=LoweringRoute.WCC_M4,
        validate_shared=False,
    )
    child = next(
        workflow
        for workflow in entry_result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == "std/drain::backlog-drain"
    )
    repeat_step = next(step for step in child.authored_mapping["steps"] if "repeat_until" in step)
    body_steps = list(_iter_nested_steps(repeat_step["repeat_until"]["steps"]))
    gap_drafter_call = next(step for step in body_steps if step.get("call", "").endswith("gap-draft"))
    gap_write_root_name = next(
        name for name in gap_drafter_call["with"] if name.startswith("__write_root__")
    )

    assert gap_drafter_call["with"] == {
        "ctx__run__run-id": {"ref": "inputs.ctx__run__run-id"},
        "ctx__run__state-root": {"ref": "inputs.ctx__run__state-root"},
        "ctx__run__artifact-root": {"ref": "inputs.ctx__run__artifact-root"},
        "ctx__state-root": {"ref": "inputs.ctx__state-root"},
        "ctx__manifest": {"ref": "inputs.ctx__manifest"},
        "ctx__ledger": {"ref": "inputs.ctx__ledger"},
        "gap__work-item-id": {
            "ref": "self.steps.std/drain::backlog-drain__selector.artifacts.return__gap__work-item-id"
        },
        "gap__plan-target-path": {
            "ref": "self.steps.std/drain::backlog-drain__selector.artifacts.return__gap__plan-target-path"
        },
        "gap__architecture-path": {
            "ref": "self.steps.std/drain::backlog-drain__selector.artifacts.return__gap__architecture-path"
        },
        gap_write_root_name: {
            "ref": (
                "self.steps.std/drain::backlog-drain__gap_drafter__managed_write_roots.artifacts."
                f"{gap_write_root_name}"
            )
        },
    }
    assert "gap__gap-id" not in gap_drafter_call["with"]


def test_compile_stage3_module_keeps_callable_backlog_drain_specializations_isolated(
    tmp_path: Path,
) -> None:
    path = tmp_path / "multi_callable_backlog_drain.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule multi_callable_backlog_drain)",
                "  (import std/context :only (DrainCtx ItemCtx))",
                "  (import std/resource :only (BlockerClass SelectedItemResult))",
                "  (import std/drain :only",
                "    (GapPayload GapResult DrainResult SelectionPayload SelectionResult))",
                "  (defworkflow selector-a",
                "    ((ctx DrainCtx))",
                "    -> SelectionResult",
                "    (command-result select_next_item",
                '      :argv ("python" "scripts/select_next_item.py" ctx.manifest)',
                "      :returns SelectionResult))",
                "  (defworkflow run-selected-item-a",
                "    ((item-ctx ItemCtx)",
                "     (selection SelectionPayload))",
                "    -> SelectedItemResult",
                "    (command-result execute_selected_item",
                '      :argv ("python" "scripts/execute_selected_item.py" selection.item-id)',
                "      :returns SelectedItemResult))",
                "  (defworkflow gap-draft-a",
                "    ((ctx DrainCtx)",
                "     (gap GapPayload))",
                "    -> GapResult",
                "    (command-result draft_gap_item",
                '      :argv ("python" "scripts/draft_gap_item.py" gap.gap-id)',
                "      :returns GapResult))",
                "  (defworkflow selector-b",
                "    ((ctx DrainCtx))",
                "    -> SelectionResult",
                "    (command-result select_next_item",
                '      :argv ("python" "scripts/select_next_item.py" ctx.manifest)',
                "      :returns SelectionResult))",
                "  (defworkflow run-selected-item-b",
                "    ((item-ctx ItemCtx)",
                "     (selection SelectionPayload))",
                "    -> SelectedItemResult",
                "    (command-result execute_selected_item",
                '      :argv ("python" "scripts/execute_selected_item.py" selection.item-id)',
                "      :returns SelectedItemResult))",
                "  (defworkflow gap-draft-b",
                "    ((ctx DrainCtx)",
                "     (gap GapPayload))",
                "    -> GapResult",
                "    (command-result draft_gap_item",
                '      :argv ("python" "scripts/draft_gap_item.py" gap.gap-id)',
                "      :returns GapResult))",
                "  (defworkflow drain-a",
                "    ((ctx DrainCtx))",
                "    -> DrainResult",
                "    (backlog-drain-callable-boundary neurips",
                "      :ctx ctx",
                "      :selector selector-a",
                "      :run-item run-selected-item-a",
                "      :gap-drafter gap-draft-a",
                "      :max-iterations 1))",
                "  (defworkflow drain-b",
                "    ((ctx DrainCtx))",
                "    -> DrainResult",
                "    (backlog-drain-callable-boundary neurips",
                "      :ctx ctx",
                "      :selector selector-b",
                "      :run-item run-selected-item-b",
                "      :gap-drafter gap-draft-b",
                "      :max-iterations 4))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        command_boundaries=_command_boundaries(gap_output_type_name="GapResult").bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.WCC_M4,
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow
        for workflow in result.lowered_workflows
    }

    for workflow_name, selector_name, run_item_name, gap_name, expected_max in (
        ("multi_callable_backlog_drain::drain-a", "selector-a", "run-selected-item-a", "gap-draft-a", 1),
        ("multi_callable_backlog_drain::drain-b", "selector-b", "run-selected-item-b", "gap-draft-b", 4),
    ):
        parent = lowered_by_name[workflow_name]
        parent_call = next(
            step
            for step in _iter_nested_steps(parent.authored_mapping["steps"])
            if isinstance(step.get("call"), str)
        )
        child = lowered_by_name[parent_call["call"]]
        repeat_step = next(step for step in child.authored_mapping["steps"] if "repeat_until" in step)
        body_calls = {
            step.get("call")
            for step in _iter_nested_steps(repeat_step["repeat_until"]["steps"])
            if isinstance(step.get("call"), str)
        }

        assert repeat_step["repeat_until"]["max_iterations"] == expected_max
        assert any(target.endswith(selector_name) for target in body_calls)
        assert any(target.endswith(run_item_name) for target in body_calls)
        assert any(target.endswith(gap_name) for target in body_calls)


def test_compile_stage3_module_reuses_canonical_callable_backlog_drain_for_identical_specializations(
    tmp_path: Path,
) -> None:
    path = tmp_path / "identical_callable_backlog_drain.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule identical_callable_backlog_drain)",
                "  (import std/context :only (DrainCtx ItemCtx))",
                "  (import std/resource :only (BlockerClass SelectedItemResult))",
                "  (import std/drain :only",
                "    (GapPayload GapResult DrainResult SelectionPayload SelectionResult))",
                "  (defworkflow selector",
                "    ((ctx DrainCtx))",
                "    -> SelectionResult",
                "    (command-result select_next_item",
                '      :argv ("python" "scripts/select_next_item.py" ctx.manifest)',
                "      :returns SelectionResult))",
                "  (defworkflow run-selected-item",
                "    ((item-ctx ItemCtx)",
                "     (selection SelectionPayload))",
                "    -> SelectedItemResult",
                "    (command-result execute_selected_item",
                '      :argv ("python" "scripts/execute_selected_item.py" selection.item-id)',
                "      :returns SelectedItemResult))",
                "  (defworkflow gap-draft",
                "    ((ctx DrainCtx)",
                "     (gap GapPayload))",
                "    -> GapResult",
                "    (command-result draft_gap_item",
                '      :argv ("python" "scripts/draft_gap_item.py" gap.gap-id)',
                "      :returns GapResult))",
                "  (defworkflow drain-a",
                "    ((ctx DrainCtx))",
                "    -> DrainResult",
                "    (backlog-drain-callable-boundary neurips",
                "      :ctx ctx",
                "      :selector selector",
                "      :run-item run-selected-item",
                "      :gap-drafter gap-draft",
                "      :max-iterations 4))",
                "  (defworkflow drain-b",
                "    ((ctx DrainCtx))",
                "    -> DrainResult",
                "    (backlog-drain-callable-boundary neurips",
                "      :ctx ctx",
                "      :selector selector",
                "      :run-item run-selected-item",
                "      :gap-drafter gap-draft",
                "      :max-iterations 4))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        command_boundaries=_command_boundaries(gap_output_type_name="GapResult").bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.WCC_M4,
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow
        for workflow in result.lowered_workflows
    }

    parent_targets = []
    for workflow_name in (
        "identical_callable_backlog_drain::drain-a",
        "identical_callable_backlog_drain::drain-b",
    ):
        parent = lowered_by_name[workflow_name]
        parent_call = next(
            step
            for step in _iter_nested_steps(parent.authored_mapping["steps"])
            if isinstance(step.get("call"), str)
        )
        parent_targets.append(parent_call["call"])

    generated_children = sorted(
        workflow_name
        for workflow_name in lowered_by_name
        if workflow_name.startswith("std/drain::backlog-drain")
    )

    assert parent_targets == ["std/drain::backlog-drain", "std/drain::backlog-drain"]
    assert generated_children == ["std/drain::backlog-drain"]


def test_callable_backlog_drain_keeps_gap_drafter_boundary_narrow(tmp_path: Path) -> None:
    path = tmp_path / "callable_gap_drafter_boundary_scope.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule callable_gap_drafter_boundary_scope)",
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
                "    (gap-id String)",
                "    (gap-kind String))",
                "  (defunion SelectionResult",
                "    (EMPTY)",
                "    (GAP",
                "      (gap GapPayload))",
                "    (SELECTED",
                "      (selection SelectionPayload))",
                "    (BLOCKED",
                "      (reason String)))",
                "  (defunion SelectedItemResult",
                "    (CONTINUE",
                "      (summary-path WorkReport))",
                "    (BLOCKED",
                "      (summary-path WorkReport)",
                "      (blocker-class BlockerClass)))",
                "  (defunion GapDraftResult",
                "    (CONTINUE)",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass)))",
                "  (defunion DrainResult",
                "    (EMPTY)",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass))",
                "    (COMPLETED",
                "      (items-processed Int)))",
                "  (defworkflow selector-run",
                "    ((ctx DrainCtx))",
                "    -> SelectionResult",
                "    (command-result select_next_item",
                '      :argv ("python" "scripts/select_next_item.py" ctx.manifest)',
                "      :returns SelectionResult))",
                "  (defworkflow run-selected-item",
                "    ((item-ctx ItemCtx)",
                "     (selection SelectionPayload))",
                "    -> SelectedItemResult",
                "    (command-result execute_selected_item",
                '      :argv ("python" "scripts/execute_selected_item.py" selection.item-id)',
                "      :returns SelectedItemResult))",
                "  (defworkflow gap-draft",
                "    ((ctx DrainCtx)",
                "     (gap GapPayload))",
                "    -> GapDraftResult",
                "    (command-result draft_gap_item",
                '      :argv ("python" "scripts/draft_gap_item.py" gap.gap-id)',
                "      :returns GapDraftResult))",
                "  (defworkflow drain",
                "    ((ctx DrainCtx))",
                "    -> DrainResult",
                "    (backlog-drain-callable-boundary neurips",
                "      :ctx ctx",
                "      :selector selector-run",
                "      :run-item run-selected-item",
                "      :gap-drafter gap-draft",
                "      :max-iterations 4))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        command_boundaries=_command_boundaries(gap_output_type_name="GapDraftResult").bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.WCC_M4,
    )

    child = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "std/drain::backlog-drain"
    )
    gap_drafter_call = next(
        step
        for step in _iter_nested_steps(child.authored_mapping["steps"])
        if step.get("call") == "gap-draft"
    )

    assert gap_drafter_call["with"]["gap__gap-id"] == {
        "ref": "self.steps.std/drain::backlog-drain__selector.artifacts.return__gap__gap-id"
    }
    assert gap_drafter_call["with"]["gap__gap-kind"] == {
        "ref": "self.steps.std/drain::backlog-drain__selector.artifacts.return__gap__gap-kind"
    }
    assert sum(name.startswith("gap__") for name in gap_drafter_call["with"]) == 2


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
    result = _compile(
        _record_gap_drafter_fixture(tmp_path),
        tmp_path=tmp_path,
        validate_shared=True,
        lowering_route=LoweringRoute.WCC_M4,
    )

    drain = next(workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "drain")
    rendered = str(drain.authored_mapping)

    assert "drain__gap_drafter.artifacts.return__variant" not in rendered


def test_backlog_drain_contract_inventory_matches_promoted_stdlib_route(tmp_path: Path) -> None:
    _workflow_path, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_CALLABLE_BOUNDARY_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )
    contract = STDLIB_LOWERING_CONTRACTS_BY_FORM["backlog-drain"]
    parent = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::drain")
    )
    lowered = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == "std/drain::backlog-drain"
    )
    authored = lowered.authored_mapping
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    body_steps = list(_iter_nested_steps(repeat_step["repeat_until"]["steps"]))
    workflow_calls = [step for step in body_steps if isinstance(step.get("call"), str)]
    parent_call = next(
        step
        for step in _iter_nested_steps(parent.authored_mapping["steps"])
        if step.get("call") == "std/drain::backlog-drain"
    )
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
    normalize_step = next(
        step for step in authored["steps"] if step.get("name") == "std/drain::backlog-drain__normalize_result"
    )
    _assert_contract_matches_observed_families(contract, steps=authored["steps"])
    assert not any("repeat_until" in step for step in parent.authored_mapping["steps"])
    assert parent_call["id"] in parent.origin_map.step_spans
    assert workflow_calls
    assert any(any(name.startswith("__write_root__") for name in step.get("with", {})) for step in workflow_calls)
    _assert_child_backlog_drain_uses_shared_terminal_lane(lowered)
    validate_executable_workflow(
        next(
            bundle.ir
            for workflow_name, bundle in result.entry_result.validated_bundles.items()
            if workflow_name.endswith("::drain")
        )
    )
    for step in _iter_nested_steps(authored["steps"]):
        step_id = step.get("id")
        if isinstance(step_id, str):
            assert step_id in lowered.origin_map.step_spans
            assert lowered.origin_map.step_spans[step_id].origin_key


def test_backlog_drain_target_contract_exposes_selector_blocked_variant() -> None:
    source = (
        REPO_ROOT / "orchestrator" / "workflow_lisp" / "stdlib_modules" / "std" / "drain.orc"
    ).read_text(encoding="utf-8")
    selection_union = source.split("(defunion SelectionResult", 1)[1].split(
        "(defunion GapResult", 1
    )[0]
    gap_union = source.split("(defunion GapResult", 1)[1].split("(defunion DrainResult", 1)[0]

    assert "(EMPTY)" in selection_union
    assert "(GAP" in selection_union
    assert "(SELECTED" in selection_union
    assert """(BLOCKED
      (reason String))""" in selection_union
    assert "(run-state StateExisting)" not in selection_union
    assert "(CONTINUE)" in gap_union
    assert """(BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass))""" in gap_union
    assert "(run-state StateExisting)" not in gap_union


def test_backlog_drain_target_contract_separates_terminal_value_from_effect_consumers() -> None:
    source = (
        REPO_ROOT / "orchestrator" / "workflow_lisp" / "stdlib_modules" / "std" / "drain.orc"
    ).read_text(encoding="utf-8")
    finalize_section = source.split("(defproc finalize-drain-terminal", 1)[1].split(
        "(defproc consume-drain-terminal-effects", 1
    )[0]

    assert "(defproc consume-drain-terminal-effects" in source
    assert "resource-transition" not in finalize_section
    assert "materialize-view" not in finalize_section


def test_backlog_drain_target_contract_routes_default_imported_surface_through_callable_child(
    tmp_path: Path,
) -> None:
    result = _compile(
        VALID_DRAIN_FIXTURE,
        tmp_path=tmp_path,
        lowering_route=LoweringRoute.WCC_M4,
    )
    parent = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "drain"
    )
    child = _child_backlog_drain_workflow(result)
    call_step = next(
        step
        for step in _iter_nested_steps(parent.authored_mapping["steps"])
        if step.get("call") == "std/drain::backlog-drain"
    )

    assert len(parent.authored_mapping["steps"]) == 1
    assert call_step["id"] in parent.origin_map.step_spans
    assert any("repeat_until" in step for step in child.authored_mapping["steps"])
    _assert_child_backlog_drain_uses_shared_terminal_lane(child)


def test_backlog_drain_target_contract_removes_run_state_from_public_stdlib_shapes() -> None:
    source = (
        REPO_ROOT / "orchestrator" / "workflow_lisp" / "stdlib_modules" / "std" / "drain.orc"
    ).read_text(encoding="utf-8")
    drain_result_union = source.split("(defunion DrainResult", 1)[1].split(
        "(defenum DrainTerminalKind", 1
    )[0]
    drain_loop_terminal_union = source.split("(defunion DrainLoopTerminal", 1)[1].split(
        "(defrecord DrainLoopState", 1
    )[0]
    drain_loop_state_record = source.split("(defrecord DrainLoopState", 1)[1].split(
        "(defrecord DrainOutcomeState", 1
    )[0]
    helper_section = source.split("(defproc empty-drain-result-proc", 1)[1].split(
        "(defproc consume-drain-terminal-effects", 1
    )[0]

    assert "(run-state StateExisting)" not in drain_result_union
    assert "(run_state StateExisting)" not in drain_loop_terminal_union
    assert "(run-state StateExisting)" not in drain_loop_state_record
    assert "(run-state StateExisting)" not in helper_section
    assert "(run_state StateExisting)" not in helper_section


def test_legacy_backlog_drain_keeps_repeat_until_in_parent(tmp_path: Path) -> None:
    result = _compile(
        VALID_DRAIN_FIXTURE,
        tmp_path=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )
    parent = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "drain"
    )

    assert any("repeat_until" in step for step in parent.authored_mapping["steps"])
    assert not any(
        workflow.typed_workflow.definition.name == "std/drain::backlog-drain"
        for workflow in result.lowered_workflows
    )


def test_lowering_backlog_drain_pins_selector_blocked_compatibility_blocker_class(
    tmp_path: Path,
) -> None:
    result = _compile(
        VALID_DRAIN_FIXTURE,
        tmp_path=tmp_path,
        lowering_route=LoweringRoute.WCC_M4,
    )
    parent = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "drain"
    )
    parent_call = next(
        step
        for step in _iter_nested_steps(parent.authored_mapping["steps"])
        if step.get("call") == "std/drain::backlog-drain"
    )
    child = _child_backlog_drain_workflow(result)
    repeat_step = next(
        step for step in child.authored_mapping["steps"] if "repeat_until" in step
    )
    body_steps = list(_iter_nested_steps(repeat_step["repeat_until"]["steps"]))
    selector_blocked_marker = next(
        step for step in body_steps if step.get("name") == "MarkSelectorBlocked"
    )
    blocker_value = next(
        value
        for value in selector_blocked_marker["materialize_artifacts"]["values"]
        if value["name"] == "acc__blocker-class"
    )

    assert parent_call["call"] == "std/drain::backlog-drain"
    assert blocker_value["source"] == {"literal": "user_decision_required"}


@pytest.mark.parametrize(
    (
        "selection_payload",
        "run_item_payload",
        "gap_payload",
        "max_iterations",
        "expected_outputs",
    ),
    (
        (
            {"variant": "EMPTY", "run-state": "state/empty-queue.json"},
            None,
            None,
            4,
            {
                "return__variant": "EMPTY",
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
            },
            None,
            4,
            {
                "return__variant": "BLOCKED",
                "return__progress-report-path": "artifacts/work/item-blocked.md",
                "return__blocker-class": "roadmap_conflict",
                "summary_path": "artifacts/work/item-blocked.md",
            },
        ),
        (
            [
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-1", "item-state-root": "state/items/item-1"},
                },
                {"variant": "EMPTY", "run-state": "state/items/item-1/post-run.json"},
            ],
            [
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-complete.md",
                }
            ],
            None,
            4,
            {
                "return__variant": "COMPLETED",
                "return__items-processed": 1,
                "summary_path": "artifacts/work/item-complete.md",
            },
        ),
        (
            [
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-1", "item-state-root": "state/items/item-1"},
                },
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-2", "item-state-root": "state/items/item-2"},
                },
                {"variant": "EMPTY", "run-state": "state/items/item-2/post-run.json"},
            ],
            [
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-1-complete.md",
                },
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-2-complete.md",
                },
            ],
            None,
            4,
            {
                "return__variant": "COMPLETED",
                "return__items-processed": 2,
                "summary_path": "artifacts/work/item-2-complete.md",
            },
        ),
        (
            {
                "variant": "BLOCKED",
                "reason": "selector_blocked",
            },
            None,
            None,
            4,
            {
                "return__variant": "BLOCKED",
                "return__blocker-class": "user_decision_required",
                "summary_path": "artifacts/work/drain-progress-report.md",
            },
        ),
        (
            [
                {"variant": "GAP", "gap": {"gap-id": "gap-1"}},
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-1", "item-state-root": "state/items/item-1"},
                },
                {"variant": "EMPTY", "run-state": "state/items/item-1/post-gap.json"},
            ],
            [
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-after-gap.md",
                }
            ],
            [{"variant": "CONTINUE"}],
            4,
            {
                "return__variant": "COMPLETED",
                "return__items-processed": 1,
                "summary_path": "artifacts/work/item-after-gap.md",
            },
        ),
        (
            [
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-1", "item-state-root": "state/items/item-1"},
                },
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-2", "item-state-root": "state/items/item-2"},
                },
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-3", "item-state-root": "state/items/item-3"},
                },
                {
                    "variant": "SELECTED",
                    "selection": {"item-id": "item-4", "item-state-root": "state/items/item-4"},
                },
            ],
            [
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-1-progress.md",
                },
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-2-progress.md",
                },
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-3-progress.md",
                },
                {
                    "variant": "CONTINUE",
                    "summary-path": "artifacts/work/item-4-progress.md",
                },
            ],
            None,
            4,
            {
                "return__variant": "BLOCKED",
                "return__blocker-class": "unrecoverable_after_fix_attempt",
                "summary_path": "artifacts/work/item-4-progress.md",
            },
        ),
    ),
)
def test_stdlib_backlog_drain_executes_promoted_route_with_terminal_side_effects(
    tmp_path: Path,
    selection_payload: dict[str, object] | list[dict[str, object]],
    run_item_payload: dict[str, object] | list[dict[str, object]] | None,
    gap_payload: dict[str, object] | list[dict[str, object]] | None,
    max_iterations: int,
    expected_outputs: dict[str, object],
) -> None:
    workflow_path, result = _compile_linked_stdlib_fixture(
        VALID_STDLIB_CALLABLE_BOUNDARY_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )
    bundle = next(
        bundle
        for workflow_name, bundle in result.entry_result.validated_bundles.items()
        if workflow_name.endswith("::drain")
    )
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
            "max-iterations": max_iterations,
        },
    )

    assert state["status"] == "completed"
    for key, value in expected_outputs.items():
        if key == "summary_path":
            continue
        assert state["workflow_outputs"][key] == value
    assert (tmp_path / expected_outputs["summary_path"]).is_file()
    assert sorted((tmp_path / "state" / "workflow_lisp").rglob("*-drain-run-state.json"))
    assert sorted((tmp_path / "state" / "workflow_lisp").rglob("*-record-drain-outcome.jsonl"))
    audit_rows = _drain_transition_audit_rows(tmp_path)
    assert audit_rows
    committed_row = next(row for row in reversed(audit_rows) if row["outcome_code"] == "committed")
    assert "run_state" not in committed_row["result"]
    assert "run_state" not in committed_row["projection"]


def test_stdlib_backlog_drain_rejects_non_symbol_callee_on_imported_route(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_linked_stdlib_fixture(INVALID_STDLIB_DRAIN_NON_SYMBOL_CALLEE_FIXTURE, tmp_path=tmp_path)

    assert excinfo.value.diagnostics[0].code == "frontend_parse_error"


def test_stdlib_backlog_drain_view_authority_misuse_still_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_linked_stdlib_fixture(INVALID_STDLIB_DRAIN_VIEW_AUTHORITY_FIXTURE, tmp_path=tmp_path)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "type_mismatch"
    assert "reason" in diagnostic.message


def test_compile_stage3_module_rejects_hidden_compatibility_bridge_public_run_item_fixture(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_linked_stdlib_fixture(
            INVALID_HIDDEN_COMPATIBILITY_BRIDGE_PUBLIC_RUN_ITEM_FIXTURE,
            tmp_path=tmp_path,
            validate_shared=True,
        )

    diagnostic = excinfo.value.diagnostics[0]
    # Generic route: the smuggled extra run_state_path parameter on the run-item
    # hook is rejected by the parametric proc-ref signature check at the macro
    # boundary (arity mismatch) instead of the intrinsic workflow-signature
    # comparison. The scenario stays impossible to author; the checker reports
    # the arity mismatch without naming the offending parameter.
    assert diagnostic.code == "proc_ref_signature_invalid"
    assert diagnostic.form_path == ("workflow-lisp", "defworkflow", "drain")
    assert "does not match parametric signature" in diagnostic.message

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
                "    (EMPTY)",
                "    (GAP",
                "      (gap GapPayload))",
                "    (SELECTED",
                "      (selection SelectionPayload))",
                "    (BLOCKED",
                "      (reason String)))",
                "  (defunion SelectedItemResult",
                "    (CONTINUE",
                "      (summary-path WorkReport))",
                "    (BLOCKED",
                "      (summary-path WorkReport)",
                "      (blocker-class BlockerClass)))",
                "  (defunion GapDraftResult",
                "    (CONTINUE)",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass)))",
                "  (defunion DrainResult",
                "    (EMPTY)",
                "    (BLOCKED",
                "      (progress-report-path WorkReport)",
                "      (blocker-class BlockerClass))",
                "    (COMPLETED",
                "      (items-processed Int)))",
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
    specialized = _specialize_imported_bundle_provider_metadata(
        imported_selector,
        provider_id="main-selector-provider",
        prompt_binding=PromptExtern(
            name="prompts.selector",
            asset_file="prompts/main-selector.md",
        ),
        alias="selector-run__selector_rebound",
    )

    assert specialized.surface.name == "selector-run__selector_rebound"
    surface_step = specialized.surface.steps[0]
    assert surface_step.provider == "main-selector-provider"
    assert surface_step.asset_file == "prompts/main-selector.md"
    ir_step = next(node.execution_config for node in specialized.ir.nodes.values())
    assert ir_step.provider == "main-selector-provider"
    assert ir_step.asset_file == "prompts/main-selector.md"


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
                "    (EMPTY)",
                "    (GAP",
                f"      (gap GapPayload{first_label}))",
                "    (SELECTED",
                f"      (selection SelectionPayload{first_label}))",
                "    (BLOCKED",
                "      (reason String)))",
                f"  (defrecord SelectionPayload{second_label}",
                "    (item-id String)",
                "    (item-state-root StateFile))",
                f"  (defrecord GapPayload{second_label}",
                "    (gap-id String))",
                f"  (defunion SelectionResult{second_label}",
                "    (EMPTY)",
                "    (GAP",
                f"      (gap GapPayload{second_label}))",
                "    (SELECTED",
                f"      (selection SelectionPayload{second_label}))",
                "    (BLOCKED",
                "      (reason String)))",
                "  (defunion SelectedItemResult",
                "    (CONTINUE",
                "      (summary-path WorkReport))",
                "    (BLOCKED",
                "      (summary-path WorkReport)",
                "      (blocker-class BlockerClass)))",
                "  (defunion GapDraftResult",
                "    (CONTINUE)",
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


def test_compile_stage3_module_rebinds_same_file_selector_provider_metadata_and_contract_field_alias_rekey(
    tmp_path: Path,
) -> None:
    path = tmp_path / "same_file_selector_rebind.orc"
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
                "      (status String))",
                "    (GAP",
                "      (gap GapPayload)",
                "      (status String))",
                "    (SELECTED",
                "      (selection SelectionPayload)",
                "      (status String))",
                "    (BLOCKED",
                "      (reason String)",
                "      (status String)))",
                "  (defworkflow selector-run",
                "    ((ctx DrainCtx))",
                "    -> SelectionResult",
                "    (provider-result providers.internal_selector",
                "      :prompt prompts.internal_selector",
                "      :inputs (ctx.manifest)",
                "      :returns SelectionResult))",
                ")",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        provider_externs={"providers.internal_selector": "internal-selector-provider"},
        prompt_externs={"prompts.internal_selector": "prompts/internal-selector.md"},
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.WCC_M4,
    )

    original = result.lowered_workflows[0]
    specialized = _specialize_same_file_lowered_workflow_provider_metadata(
        original,
        provider_id="main-selector-provider",
        prompt_binding=PromptExtern(
            name="prompts.selector",
            asset_file="prompts/main-selector.md",
        ),
        alias="selector-run__selector_rebound",
    )

    assert specialized.typed_workflow.definition.name == "selector-run__selector_rebound"
    provider_step = specialized.authored_mapping["steps"][0]
    assert provider_step["provider"] == "main-selector-provider"
    assert provider_step["asset_file"] == "prompts/main-selector.md"

    original_provider_step = original.authored_mapping["steps"][0]

    def subject_mappings(value: object) -> tuple[dict[str, object], ...]:
        if isinstance(value, list):
            return tuple(
                subject
                for item in value
                for subject in subject_mappings(item)
            )
        if not isinstance(value, dict):
            return ()
        subjects: list[dict[str, object]] = []
        singular = value.get("source_map_subject")
        if isinstance(singular, dict):
            subjects.append(singular)
        by_variant = value.get("source_map_subjects_by_variant")
        if isinstance(by_variant, dict):
            subjects.extend(
                subject
                for subject in by_variant.values()
                if isinstance(subject, dict)
            )
        subjects.extend(
            subject
            for key, item in value.items()
            if key not in {"source_map_subject", "source_map_subjects_by_variant"}
            for subject in subject_mappings(item)
        )
        return tuple(subjects)

    original_subjects = subject_mappings(original_provider_step["variant_output"])
    specialized_subjects = subject_mappings(provider_step["variant_output"])
    assert original_subjects
    assert "source_map_subject" in json.dumps(original_provider_step["variant_output"])
    assert "source_map_subjects_by_variant" in json.dumps(
        original_provider_step["variant_output"]
    )
    assert len(specialized_subjects) == len(original_subjects)
    assert [subject["subject_name"] for subject in specialized_subjects] == [
        subject["subject_name"] for subject in original_subjects
    ]
    assert {
        subject["workflow_name"] for subject in specialized_subjects
    } == {"selector-run__selector_rebound"}

    original_field_bindings = tuple(
        binding
        for binding in original.origin_map.validation_subject_bindings
        if binding.subject_ref.subject_kind == "variant_output_field"
    )
    specialized_field_bindings = tuple(
        binding
        for binding in specialized.origin_map.validation_subject_bindings
        if binding.subject_ref.subject_kind == "variant_output_field"
    )
    assert original_field_bindings
    assert len(specialized_field_bindings) == len(original_field_bindings)
    assert [
        binding.subject_ref.subject_name for binding in specialized_field_bindings
    ] == [binding.subject_ref.subject_name for binding in original_field_bindings]
    assert all(
        binding.subject_ref.workflow_name == "selector-run__selector_rebound"
        and binding.origin.origin_key.startswith(
            "selector-run__selector_rebound::variant_output_field::"
        )
        for binding in specialized_field_bindings
    )

    def without_subject_metadata(value: object) -> object:
        if isinstance(value, list):
            return [without_subject_metadata(item) for item in value]
        if isinstance(value, dict):
            return {
                key: without_subject_metadata(item)
                for key, item in value.items()
                if key not in {"source_map_subject", "source_map_subjects_by_variant"}
            }
        return value

    assert without_subject_metadata(provider_step["variant_output"]) == (
        without_subject_metadata(original_provider_step["variant_output"])
    )
