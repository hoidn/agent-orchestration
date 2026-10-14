from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_module
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

    assert result.typed_workflows
