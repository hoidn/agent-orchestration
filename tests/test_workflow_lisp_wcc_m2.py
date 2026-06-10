from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, PrimitiveTypeRef
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow
from orchestrator.workflow_lisp.wcc.model import (
    WccCall,
    WccHalt,
    WccIdentityFactory,
    WccInject,
    WccLet,
    WccLiteralAtom,
    WccNameAtom,
    WccPerform,
    WccRecordAtom,
)
from orchestrator.workflow_lisp.wcc.route import LoweringRoute, normalize_lowering_route


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
VALID_FIXTURES = FIXTURES / "valid"
MODULE_FIXTURES = FIXTURES / "modules" / "valid"
CHARACTERIZATION_FIXTURES = FIXTURES / "characterization" / "sources"


def _assert_wcc_route_unsupported(excinfo: pytest.ExceptionInfo[LispFrontendCompileError]) -> None:
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "wcc_lowering_route_unsupported"
    assert diagnostic.phase == "lowering"


def _compile_fixture(path: Path, *, tmp_path: Path):
    compile_kwargs: dict[str, object] = {}
    if path == CHARACTERIZATION_FIXTURES / "wcc_m2_straight_line_effects.orc":
        compile_kwargs["provider_externs"] = {"providers.execute": "fake"}
        compile_kwargs["prompt_externs"] = {"prompts.implementation.execute": "prompts/implementation/execute.md"}
        compile_kwargs["command_boundaries"] = {
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
        }
    elif path == VALID_FIXTURES / "proc_ref_bind_proc_forwarding.orc":
        compile_kwargs["command_boundaries"] = {
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
        }
    result = compile_stage3_module(
        path,
        validate_shared=False,
        workspace_root=tmp_path,
        **compile_kwargs,
    )
    type_env = FrontendTypeEnvironment.from_module(result.module)
    workflows = {workflow.definition.name: workflow for workflow in result.typed_workflows}
    workflow_return_types = {
        workflow.definition.name: workflow.signature.return_type_ref
        for workflow in result.typed_workflows
    }
    procedure_return_types = {
        procedure.definition.name: procedure.signature.return_type_ref
        for procedure in result.typed_procedures
    }
    return type_env, workflows, workflow_return_types, procedure_return_types


def _write_with_phase_command_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "with_phase_command_result.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defworkflow orchestrate",
                "    ((phase-ctx PhaseCtx)",
                "     (report_path WorkReport))",
                "    -> ChecksResult",
                "    (with-phase phase-ctx implementation",
                "      (command-result run_checks",
                '        :argv ("python" "scripts/run_checks.py" report_path)',
                "        :returns ChecksResult))))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return fixture


def _write_with_phase_provider_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "with_phase_provider_result.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow orchestrate",
                "    ((phase-ctx PhaseCtx)",
                "     (input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (with-phase phase-ctx implementation",
                "      (provider-result providers.execute",
                "        :prompt prompts.implementation.execute",
                "        :inputs (input report_path)",
                "        :returns ImplementationSummary))))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return fixture


def _write_imported_bundle_call_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "imported_bundle_call.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow orchestrate",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (call selector-run",
                "      :input input",
                "      :report_path report_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return fixture


def _write_proc_match_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "orchestrate_proc_match.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord CompletedAttempt",
                "    (execution_report WorkReport))",
                "  (defrecord BlockedAttempt",
                "    (progress_report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defunion ImplementationState",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)))",
                "  (defproc provider-attempt",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    :effects ((uses-provider providers.execute))",
                "    :lowering inline",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (input report_path)",
                "               :returns ImplementationState)))",
                "      (match attempt",
                "        ((COMPLETED completed)",
                "         (record ImplementationSummary",
                "           :report completed.execution_report))",
                "        ((BLOCKED blocked)",
                "         (record ImplementationSummary",
                "           :report blocked.progress_report)))))",
                "  (defworkflow orchestrate",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (provider-attempt input report_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return fixture


def _load_imported_bundle_bindings(tmp_path: Path) -> dict[str, object]:
    build_module = importlib.import_module("orchestrator.workflow_lisp.build")
    bindings = build_module.load_imported_workflow_bundle_manifest(
        FIXTURES / "cli" / "imported_workflow_bundles.json",
        workspace_root=tmp_path,
        source_roots=(MODULE_FIXTURES / "imported_bundle_mix",),
        provider_externs_path=FIXTURES / "cli" / "providers.json",
        prompt_externs_path=FIXTURES / "cli" / "prompts.json",
        command_boundaries_path=FIXTURES / "cli" / "commands.json",
    )
    return {binding.canonical_key: binding.bundle for binding in bindings}


@pytest.mark.parametrize("route_value", ("wcc_m2", LoweringRoute.WCC_M2))
def test_normalize_lowering_route_accepts_wcc_m2(route_value: str | LoweringRoute) -> None:
    assert normalize_lowering_route(route_value) is LoweringRoute.WCC_M2


def test_wcc_model_instantiates_effectful_nodes_with_stable_metadata() -> None:
    start = SourcePosition(path="wcc_m2_model.orc", line=1, column=1, offset=0)
    end = SourcePosition(path="wcc_m2_model.orc", line=1, column=8, offset=7)
    span = SourceSpan(start=start, end=end)
    scope = WccIdentityFactory(owner_name="demo::workflow", lexical_owner_chain=("workflow",))
    form_path = ("workflow-lisp", "defworkflow", "orchestrate")
    string_type = PrimitiveTypeRef(name="String")

    arg = WccNameAtom(
        metadata=scope.atom_metadata(
            role="name:report_path",
            type_ref=string_type,
            source_span=span,
            form_path=form_path,
        ),
        name="report_path",
    )
    perform = WccPerform(
        metadata=scope.value_metadata(
            role="perform:command_result",
            type_ref=string_type,
            source_span=span,
            form_path=form_path,
        ),
        perform_kind="command_result",
        target_name="run_checks",
        prompt_name=None,
        positional_args=(arg,),
        keyword_args=(),
        returns_type_name="ChecksResult",
    )
    call = WccCall(
        metadata=scope.value_metadata(
            role="call:%proc-ref-call.forward_runner",
            type_ref=string_type,
            source_span=span,
            form_path=form_path,
        ),
        callee_name="forward-runner",
        specialized_callee_name="%proc-ref-call.forward_runner.abc123",
        args=(arg,),
    )

    assert perform.perform_kind == "command_result"
    assert perform.target_name == "run_checks"
    assert perform.metadata.node_id.startswith("wcc-node:")
    assert call.specialized_callee_name.startswith("%proc-ref-call.forward_runner.")
    assert call.metadata.scope_id == scope.scope_id


def test_elaborate_preserves_effect_summaries_on_perform_nodes(tmp_path: Path) -> None:
    type_env, workflows, workflow_return_types, procedure_return_types = _compile_fixture(
        CHARACTERIZATION_FIXTURES / "wcc_m2_straight_line_effects.orc",
        tmp_path=tmp_path,
    )

    command_body = elaborate_typed_workflow(
        workflows["command-checks"],
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    assert isinstance(command_body, WccLet)
    assert isinstance(command_body.bound_value, WccPerform)
    assert command_body.bound_value.perform_kind == "command_result"
    assert command_body.bound_value.metadata.effect_summary == workflows["command-checks"].effect_summary
    assert isinstance(command_body.body, WccHalt)
    assert isinstance(command_body.body.result, WccNameAtom)
    assert command_body.body.result.name == command_body.bound_name

    provider_body = elaborate_typed_workflow(
        workflows["provider-attempt"],
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    assert isinstance(provider_body, WccLet)
    assert isinstance(provider_body.bound_value, WccPerform)
    assert provider_body.bound_value.perform_kind == "provider_result"
    assert provider_body.bound_value.target_name == "providers.execute"
    assert provider_body.bound_value.prompt_name == "prompts.implementation.execute"
    assert provider_body.bound_value.metadata.effect_summary == workflows["provider-attempt"].effect_summary

    orchestrate_body = elaborate_typed_workflow(
        workflows["orchestrate"],
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    assert isinstance(orchestrate_body, WccLet)
    assert isinstance(orchestrate_body.bound_value, WccPerform)
    assert orchestrate_body.bound_name == "checks"
    assert orchestrate_body.bound_value.perform_kind == "workflow_call"
    assert orchestrate_body.bound_value.target_name == "command-checks"
    assert isinstance(orchestrate_body.body, WccLet)
    assert isinstance(orchestrate_body.body.bound_value, WccPerform)
    assert orchestrate_body.body.bound_value.perform_kind == "workflow_call"
    assert orchestrate_body.body.bound_value.target_name == "provider-attempt"


def test_elaborate_preserves_specialized_procedure_identity_on_wcc_call(tmp_path: Path) -> None:
    type_env, workflows, workflow_return_types, procedure_return_types = _compile_fixture(
        VALID_FIXTURES / "proc_ref_bind_proc_forwarding.orc",
        tmp_path=tmp_path,
    )

    body = elaborate_typed_workflow(
        workflows["entry"],
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )

    assert isinstance(body, WccLet)
    assert isinstance(body.bound_value, WccCall)
    assert body.bound_value.callee_name == "forward-runner"
    assert body.bound_value.specialized_callee_name.startswith("%proc-ref-call.forward_runner.")
    assert len(body.bound_value.args) == 1
    assert isinstance(body.bound_value.args[0], WccNameAtom)
    assert body.bound_value.args[0].name == "input"
    assert body.bound_value.metadata.effect_summary == workflows["entry"].effect_summary


def test_elaborate_preserves_with_phase_lowering_context_on_supported_effect_body(tmp_path: Path) -> None:
    fixture = _write_with_phase_provider_fixture(tmp_path)
    result = compile_stage3_module(
        fixture,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
        },
        validate_shared=False,
        workspace_root=tmp_path / "workspace",
    )
    type_env = FrontendTypeEnvironment.from_module(result.module)
    workflow = next(iter(result.typed_workflows))
    workflow_return_types = {
        item.definition.name: item.signature.return_type_ref
        for item in result.typed_workflows
    }

    body = elaborate_typed_workflow(
        workflow,
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types={},
    )

    assert isinstance(body, WccLet)
    assert isinstance(body.bound_value, WccPerform)
    assert body.bound_value.perform_kind == "provider_result"
    assert body.bound_value.target_name == "providers.execute"
    assert body.bound_value.metadata.phase_scope is not None
    assert body.bound_value.metadata.phase_scope.phase_name == "implementation"


def test_defunctionalize_preserves_phase_scoped_provider_lowering(tmp_path: Path) -> None:
    fixture = _write_with_phase_provider_fixture(tmp_path)
    compile_kwargs = dict(
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path / "workspace",
    )

    legacy = compile_stage3_module(
        fixture,
        lowering_route="legacy",
        **compile_kwargs,
    )
    wcc_m2 = compile_stage3_module(
        fixture,
        lowering_route="wcc_m2",
        **compile_kwargs,
    )

    legacy_workflow = next(iter(legacy.lowered_workflows))
    wcc_workflow = next(iter(wcc_m2.lowered_workflows))
    legacy_steps = legacy_workflow.authored_mapping["steps"]
    wcc_steps = wcc_workflow.authored_mapping["steps"]

    assert [step["name"] for step in wcc_steps] == [step["name"] for step in legacy_steps]

    legacy_provider = next(step for step in legacy_steps if step["name"] == "orchestrate__result")
    wcc_provider = next(step for step in wcc_steps if step["name"] == "orchestrate__result")

    legacy_contract = legacy_provider["output_bundle"]
    wcc_contract = wcc_provider["output_bundle"]
    assert wcc_contract["path"] == legacy_contract["path"]
    assert wcc_provider.get("consumes") == legacy_provider.get("consumes")
    assert wcc_provider.get("prompt_consumes") == legacy_provider.get("prompt_consumes")


def test_anf_atomizes_effectful_args_and_halt_result() -> None:
    start = SourcePosition(path="wcc_m2_anf.orc", line=1, column=1, offset=0)
    end = SourcePosition(path="wcc_m2_anf.orc", line=1, column=8, offset=7)
    span = SourceSpan(start=start, end=end)
    scope = WccIdentityFactory(owner_name="demo::workflow", lexical_owner_chain=("workflow",))
    string_type = PrimitiveTypeRef(name="String")

    literal = WccLiteralAtom(
        metadata=scope.atom_metadata(
            role="literal:string",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow", "demo"),
        ),
        value="value",
        literal_kind="string",
    )
    record = WccRecordAtom(
        metadata=scope.atom_metadata(
            role="record:ChecksResult",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow", "demo"),
        ),
        type_name="ChecksResult",
        fields=(("status", literal), ("report", literal)),
    )
    call = WccCall(
        metadata=scope.value_metadata(
            role="call:%proc-ref-call.demo",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow", "demo"),
        ),
        callee_name="demo",
        specialized_callee_name="%proc-ref-call.demo",
        args=(record,),
    )
    inject = WccInject(
        metadata=scope.value_metadata(
            role="inject:COMPLETED",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow", "demo"),
        ),
        union_name="ImplementationState",
        variant_name="COMPLETED",
        fields=(("report", record),),
    )
    body = WccLet(
        metadata=scope.body_metadata(
            role="let:result",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow", "demo"),
        ),
        bound_name="result",
        bound_type_ref=string_type,
        bound_value=call,
        body=WccHalt(
            metadata=scope.body_metadata(
                role="halt:return",
                type_ref=string_type,
                source_span=span,
                form_path=("workflow-lisp", "defworkflow", "demo"),
            ),
            result=inject,
        ),
    )

    normalized = normalize_wcc_body_to_anf(body)

    assert isinstance(normalized, WccLet)
    assert normalized.bound_name.startswith("__wcc_anf_")
    assert isinstance(normalized.body, WccLet)
    assert isinstance(normalized.body.bound_value, WccCall)
    assert isinstance(normalized.body.bound_value.args[0], WccNameAtom)
    assert isinstance(normalized.body.body, WccLet)
    assert isinstance(normalized.body.body.body, WccHalt)
    assert isinstance(normalized.body.body.body.result, WccNameAtom)


def test_defunctionalize_preserves_step_order_for_straight_line_effects(tmp_path: Path) -> None:
    result = compile_stage3_module(
        CHARACTERIZATION_FIXTURES / "wcc_m2_straight_line_effects.orc",
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
        },
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m2",
    )

    steps_by_workflow = {
        workflow.typed_workflow.definition.name: [step.get("name") for step in workflow.authored_mapping["steps"]]
        for workflow in result.lowered_workflows
    }

    assert steps_by_workflow["command-checks"] == ["command-checks__run_checks"]
    assert steps_by_workflow["provider-attempt"] == ["provider-attempt__result"]
    assert steps_by_workflow["orchestrate"] == [
        "orchestrate__checks__call_command-checks",
        "orchestrate__call_provider-attempt",
    ]


def test_defunctionalize_preserves_specialized_procedure_step_order(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_FIXTURES / "proc_ref_bind_proc_forwarding.orc",
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
        },
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m2",
    )

    lowered = next(workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "entry")
    assert [step.get("name") for step in lowered.authored_mapping["steps"]] == [
        "entry__forward-runner_1__invoke-runner_1__runner_1__run_checks"
    ]


def test_wcc_m2_lowering_does_not_rebuild_frontend_effect_exprs_for_performs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("orchestrator.workflow_lisp.wcc.defunctionalize")
    original = module._frontend_expr_from_wcc_binding_value

    def guard(value):
        if isinstance(value, WccPerform):
            raise AssertionError("wcc_m2 should emit WccPerform bindings without rebuilding frontend expressions")
        return original(value)

    monkeypatch.setattr(module, "_frontend_expr_from_wcc_binding_value", guard)

    result = compile_stage3_module(
        CHARACTERIZATION_FIXTURES / "wcc_m2_straight_line_effects.orc",
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
        },
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m2",
    )

    assert result.lowered_workflows


def test_wcc_m2_lowering_does_not_rebuild_frontend_effect_exprs_for_proc_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("orchestrator.workflow_lisp.wcc.defunctionalize")
    original = module._frontend_expr_from_wcc_binding_value

    def guard(value):
        if isinstance(value, WccCall):
            raise AssertionError("wcc_m2 should emit WccCall bindings without rebuilding frontend expressions")
        return original(value)

    monkeypatch.setattr(module, "_frontend_expr_from_wcc_binding_value", guard)

    result = compile_stage3_module(
        VALID_FIXTURES / "proc_ref_bind_proc_forwarding.orc",
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
        },
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m2",
    )

    assert result.lowered_workflows


@pytest.mark.parametrize(
    "fixture_path",
    (
        CHARACTERIZATION_FIXTURES / "wcc_m2_straight_line_effects.orc",
        VALID_FIXTURES / "proc_ref_bind_proc_forwarding.orc",
    ),
)
def test_wcc_m2_route_compiles_positive_fixtures(
    tmp_path: Path,
    fixture_path: Path,
) -> None:
    result = compile_stage3_module(
        fixture_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
        },
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m2",
    )

    assert result.lowered_workflows


@pytest.mark.parametrize(
    "fixture_path",
    (
        VALID_FIXTURES / "structured_results.orc",
        VALID_FIXTURES / "neurips_implementation_attempt.orc",
    ),
)
def test_wcc_m2_route_rejects_out_of_scope_m3_m4_real_fixtures(
    tmp_path: Path,
    fixture_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            fixture_path,
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                ),
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="wcc_m2",
        )

    _assert_wcc_route_unsupported(excinfo)


def test_wcc_m2_route_rejects_same_file_module_graph_entrypoint_boundary(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            MODULE_FIXTURES / "callables" / "neurips" / "entry.orc",
            source_roots=(MODULE_FIXTURES / "callables",),
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                ),
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="wcc_m2",
        )

    _assert_wcc_route_unsupported(excinfo)


def test_wcc_m2_route_rejects_imported_bundle_mix_entrypoint_boundary(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            MODULE_FIXTURES / "imported_bundle_mix" / "neurips" / "entry.orc",
            source_roots=(MODULE_FIXTURES / "imported_bundle_mix",),
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            imported_workflow_bundles=_load_imported_bundle_bindings(tmp_path),
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                ),
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="wcc_m2",
        )

    _assert_wcc_route_unsupported(excinfo)


def test_wcc_m2_route_rejects_workflow_ref_calls_before_elaboration(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            VALID_FIXTURES / "workflow_refs_same_file.orc",
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                ),
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="wcc_m2",
        )

    _assert_wcc_route_unsupported(excinfo)
    assert "workflow-ref" in excinfo.value.diagnostics[0].message


def test_wcc_m2_route_rejects_imported_bundle_calls_before_elaboration(tmp_path: Path) -> None:
    fixture = _write_imported_bundle_call_fixture(tmp_path)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            fixture,
            imported_workflow_bundles=_load_imported_bundle_bindings(tmp_path),
            validate_shared=False,
            workspace_root=tmp_path / "workspace",
            lowering_route="wcc_m2",
        )

    _assert_wcc_route_unsupported(excinfo)
    assert "same-file direct workflow calls" in excinfo.value.diagnostics[0].message


def test_wcc_m2_route_rejects_unsupported_control_hidden_in_same_file_procedure(tmp_path: Path) -> None:
    fixture = _write_proc_match_fixture(tmp_path)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            fixture,
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path / "workspace",
            lowering_route="wcc_m2",
        )

    _assert_wcc_route_unsupported(excinfo)
    assert "bounded straight-line subset" in excinfo.value.diagnostics[0].message
