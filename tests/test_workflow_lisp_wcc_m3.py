from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, PrimitiveTypeRef
from orchestrator.workflow_lisp.wcc.analysis import analyze_wcc_body
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
from orchestrator.workflow_lisp.wcc.model import (
    WCC_M4_ROUTE_SCHEMA_VERSION,
    WccCase,
    WccCaseArm,
    WccHalt,
    WccIdentityFactory,
    WccInject,
    WccJoin,
    WccJoinParam,
    WccJump,
    WccLet,
    WccLiteralAtom,
    WccNameAtom,
    WccRecordAtom,
)



REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
VALID_FIXTURES = FIXTURES / "valid"
MODULE_FIXTURES = FIXTURES / "modules" / "valid"
CHARACTERIZATION_FIXTURES = FIXTURES / "current_wcc"






def _compile_fixture(path: Path, *, tmp_path: Path):
    result = compile_stage3_module(
        path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,

    )
    type_env = result.typed_program.module_type_envs[result.typed_program.entry_module]
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









@pytest.mark.parametrize(
    "fixture_path",
    (
        CHARACTERIZATION_FIXTURES / "design_delta_union_match_projection.orc",
        CHARACTERIZATION_FIXTURES / "wcc_m3_nested_non_tail_match.orc",
        CHARACTERIZATION_FIXTURES / "wcc_m3_nested_join_inside_arm.orc",
    ),
)
def test_wcc_m3_route_compiles_supported_match_shapes(
    tmp_path: Path,
    fixture_path: Path,
) -> None:
    result = compile_stage3_module(
        fixture_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,

    )

    assert result.typed_workflows






def test_wcc_m3_route_compiles_match_over_provider_result_subject(tmp_path: Path) -> None:
    module_path = tmp_path / "provider_subject_match_probe.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule provider_subject_match_probe)",
                "  (export summarize)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defunion ImplementationAttempt",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow summarize",
                "    ((report WorkReport))",
                "    -> ImplementationSummary",
                "    (match (provider-result providers.execute",
                "             :prompt prompts.implementation.execute",
                "             :inputs (report)",
                "             :returns ImplementationAttempt)",
                "      ((COMPLETED completed)",
                "       (record ImplementationSummary",
                "         :report completed.execution_report))",
                "      ((BLOCKED blocked)",
                "       (record ImplementationSummary",
                "         :report blocked.progress_report)))))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,

    )

    assert result.typed_workflows


def test_wcc_m3_route_compiles_provider_input_match(tmp_path: Path) -> None:
    module_path = tmp_path / "provider_input_match_probe.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule provider_input_match_probe)",
                "  (export summarize)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defunion ImplementationAttempt",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)))",
                "  (defunion ReviewDecision",
                "    (APPROVED",
                "      (execution_report WorkReport))",
                "    (REVISE",
                "      (progress_report WorkReport)))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow summarize",
                "    ((report WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report)",
                "               :returns ImplementationAttempt))",
                "           (review",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs",
                "                 (report",
                "                  (match attempt",
                "                    ((COMPLETED completed)",
                "                     completed.execution_report)",
                "                    ((BLOCKED blocked)",
                "                     blocked.progress_report)))",
                "               :returns ReviewDecision)))",
                "      (match review",
                "        ((APPROVED approved)",
                "         (record ImplementationSummary",
                "           :report approved.execution_report))",
                "        ((REVISE revise)",
                "         (record ImplementationSummary",
                "           :report revise.progress_report))))))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,

    )

    assert result.typed_workflows


def test_wcc_m3_route_rejects_actual_branch_local_ref_leakage(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            CHARACTERIZATION_FIXTURES / "wcc_m3_branch_local_ref_leak.orc",
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path,

        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "name_unknown"
    assert "completed" in diagnostic.message


def test_wcc_m3_route_compiles_record_field_match(tmp_path: Path) -> None:
    module_path = tmp_path / "record_field_match_probe.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule record_field_match_probe)",
                "  (export summarize)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defunion ImplementationAttempt",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow summarize",
                "    ((report WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report)",
                "               :returns ImplementationAttempt)))",
                "      (record ImplementationSummary",
                "        :report (match attempt",
                "                  ((COMPLETED completed)",
                "                   completed.execution_report)",
                "                  ((BLOCKED blocked)",
                "                   blocked.progress_report))))))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,

    )

    assert result.typed_workflows


def test_wcc_m3_route_compiles_let_bound_record_field_match(tmp_path: Path) -> None:
    module_path = tmp_path / "let_bound_record_field_match_probe.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule let_bound_record_field_match_probe)",
                "  (export summarize)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defunion ImplementationAttempt",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow summarize",
                "    ((report WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report)",
                "               :returns ImplementationAttempt))",
                "           (summary",
                "             (record ImplementationSummary",
                "               :report (match attempt",
                "                         ((COMPLETED completed)",
                "                          completed.execution_report)",
                "                         ((BLOCKED blocked)",
                "                          blocked.progress_report)))))",
                "      summary)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,

    )

    assert result.typed_workflows


def test_wcc_m3_route_compiles_union_field_match(tmp_path: Path) -> None:
    module_path = tmp_path / "union_field_match_probe.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule union_field_match_probe)",
                "  (export summarize)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defunion ImplementationAttempt",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)))",
                "  (defunion SummaryResult",
                "    (DONE",
                "      (report WorkReport))",
                "    (STALLED",
                "      (progress_report WorkReport)))",
                "  (defworkflow summarize",
                "    ((report WorkReport))",
                "    -> SummaryResult",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report)",
                "               :returns ImplementationAttempt)))",
                "      (variant SummaryResult DONE",
                "        :report (match attempt",
                "                  ((COMPLETED completed)",
                "                   completed.execution_report)",
                "                  ((BLOCKED blocked)",
                "                   blocked.progress_report))))))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,

    )

    assert result.typed_workflows








def test_wcc_m3_model_instantiates_case_join_and_jump_nodes() -> None:
    start = SourcePosition(path="wcc_m3_model.orc", line=1, column=1, offset=0)
    end = SourcePosition(path="wcc_m3_model.orc", line=1, column=8, offset=7)
    span = SourceSpan(start=start, end=end)
    scope = WccIdentityFactory(
        owner_name="demo::workflow",
        lexical_owner_chain=("workflow",),
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    string_type = PrimitiveTypeRef(name="String")

    result_name = WccNameAtom(
        metadata=scope.atom_metadata(
            role="name:result",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow", "demo"),
        ),
        name="result",
    )
    jump = WccJump(
        metadata=scope.body_metadata(
            role="jump:result",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow", "demo"),
        ),
        join_name="join_result",
        args=(result_name,),
    )
    join = WccJoin(
        metadata=scope.body_metadata(
            role="join:result",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow", "demo"),
        ),
        join_name="join_result",
        params=(WccJoinParam(name="result", type_ref=string_type),),
        body=jump,
        continuation=WccHalt(
            metadata=scope.body_metadata(
                role="halt:return",
                type_ref=string_type,
                source_span=span,
                form_path=("workflow-lisp", "defworkflow", "demo"),
            ),
            result=result_name,
        ),
    )
    case = WccCase(
        metadata=scope.body_metadata(
            role="case:match",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow", "demo"),
        ),
        subject=result_name,
        arms=(
            WccCaseArm(
                variant_name="COMPLETED",
                binding_name="completed",
                binding_type_ref=string_type,
                body=jump,
            ),
        ),
    )

    assert case.subject.name == "result"
    assert join.params[0].name == "result"
    assert jump.join_name == join.join_name
    assert case.metadata.node_id.startswith("wcc-node:")
    assert join.metadata.scope_id == scope.scope_id


def test_elaborate_top_level_match_into_wcc_case(tmp_path: Path) -> None:
    type_env, workflows, workflow_return_types, procedure_return_types = _compile_fixture(
        CHARACTERIZATION_FIXTURES / "design_delta_union_match_projection.orc",
        tmp_path=tmp_path,
    )

    body = elaborate_typed_workflow_body(
        workflows["design_delta_union_match_projection::summarize"].typed_body,
        owner_name=workflows["design_delta_union_match_projection::summarize"].definition.name,
        value_env=dict(workflows["design_delta_union_match_projection::summarize"].signature.params),
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )

    assert isinstance(body, WccLet)
    assert body.bound_name == "attempt"
    assert isinstance(body.body, WccCase)
    assert body.body.subject.name == "attempt"
    assert [arm.variant_name for arm in body.body.arms] == ["COMPLETED", "BLOCKED"]
    assert isinstance(body.body.arms[0].body, WccHalt)


def test_elaborate_non_tail_nested_match_into_join_and_jump(tmp_path: Path) -> None:
    type_env, workflows, workflow_return_types, procedure_return_types = _compile_fixture(
        CHARACTERIZATION_FIXTURES / "wcc_m3_nested_non_tail_match.orc",
        tmp_path=tmp_path,
    )

    body = elaborate_typed_workflow_body(
        workflows["wcc_m3_nested_non_tail_match::summarize"].typed_body,
        owner_name=workflows["wcc_m3_nested_non_tail_match::summarize"].definition.name,
        value_env=dict(workflows["wcc_m3_nested_non_tail_match::summarize"].signature.params),
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )

    assert isinstance(body, WccLet)
    assert isinstance(body.body, WccLet)
    assert body.body.bound_name == "review"
    assert isinstance(body.body.body, WccJoin)
    assert body.body.body.params[0].name == "summary"
    assert isinstance(body.body.body.body, WccCase)
    completed_arm = body.body.body.body.arms[0]
    blocked_arm = body.body.body.body.arms[1]
    assert isinstance(completed_arm.body, WccCase)
    assert isinstance(completed_arm.body.arms[0].body, WccJump)
    assert isinstance(completed_arm.body.arms[1].body, WccJump)
    assert isinstance(blocked_arm.body, WccJump)
    assert isinstance(body.body.body.continuation, WccHalt)


def test_wcc_m3_anf_atomizes_case_subjects_and_join_args() -> None:
    start = SourcePosition(path="wcc_m3_anf.orc", line=1, column=1, offset=0)
    end = SourcePosition(path="wcc_m3_anf.orc", line=1, column=8, offset=7)
    span = SourceSpan(start=start, end=end)
    scope = WccIdentityFactory(
        owner_name="demo::workflow",
        lexical_owner_chain=("workflow",),
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )
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
            role="record:Summary",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow", "demo"),
        ),
        type_name="Summary",
        fields=(("report", literal),),
    )
    inject = WccInject(
        metadata=scope.body_metadata(
            role="inject:COMPLETED",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow", "demo"),
        ),
        union_name="ImplementationAttempt",
        variant_name="COMPLETED",
        fields=(("report", record),),
    )
    join = WccJoin(
        metadata=scope.body_metadata(
            role="join:result",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow", "demo"),
        ),
        join_name="join_result",
        params=(WccJoinParam(name="result", type_ref=string_type),),
        body=WccCase(
            metadata=scope.body_metadata(
                role="case:match",
                type_ref=string_type,
                source_span=span,
                form_path=("workflow-lisp", "defworkflow", "demo"),
            ),
            subject=inject,
            arms=(
                WccCaseArm(
                    variant_name="COMPLETED",
                    binding_name="completed",
                    binding_type_ref=string_type,
                    body=WccJump(
                        metadata=scope.body_metadata(
                            role="jump:result",
                            type_ref=string_type,
                            source_span=span,
                            form_path=("workflow-lisp", "defworkflow", "demo"),
                        ),
                        join_name="join_result",
                            args=(inject,),
                        ),
                    ),
                ),
        ),
        continuation=WccHalt(
            metadata=scope.body_metadata(
                role="halt:return",
                type_ref=string_type,
                source_span=span,
                form_path=("workflow-lisp", "defworkflow", "demo"),
            ),
            result=WccNameAtom(
                metadata=scope.atom_metadata(
                    role="name:result",
                    type_ref=string_type,
                    source_span=span,
                    form_path=("workflow-lisp", "defworkflow", "demo"),
                ),
                name="result",
            ),
        ),
    )

    normalized = normalize_wcc_body_to_anf(join)

    assert isinstance(normalized, WccJoin)
    assert isinstance(normalized.body, WccLet)
    assert isinstance(normalized.body.body, WccCase)
    assert isinstance(normalized.body.body.subject, WccNameAtom)
    assert isinstance(normalized.body.body.arms[0].body, WccLet)
    assert isinstance(normalized.body.body.arms[0].body.body, WccJump)
    assert isinstance(normalized.body.body.arms[0].body.body.args[0], WccNameAtom)


def test_wcc_m3_scope_analysis_tracks_arm_bindings_and_join_live_outs(tmp_path: Path) -> None:
    type_env, workflows, workflow_return_types, procedure_return_types = _compile_fixture(
        CHARACTERIZATION_FIXTURES / "wcc_m3_nested_non_tail_match.orc",
        tmp_path=tmp_path,
    )

    body = elaborate_typed_workflow_body(
        workflows["wcc_m3_nested_non_tail_match::summarize"].typed_body,
        owner_name=workflows["wcc_m3_nested_non_tail_match::summarize"].definition.name,
        value_env=dict(workflows["wcc_m3_nested_non_tail_match::summarize"].signature.params),
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    analysis = analyze_wcc_body(normalize_wcc_body_to_anf(body))

    assert {arm.binding_name for arm in analysis.arm_scopes} >= {
        "completed",
        "approved",
        "revise",
        "blocked",
    }
    assert len(analysis.joins_by_name) == 1
    join_site = next(iter(analysis.joins_by_name.values()))
    assert join_site.live_out_names == ("summary",)
    assert "completed" not in join_site.live_out_names
    assert all(len(args) == len(join_site.params) for args in join_site.jump_args)


def test_wcc_m3_scope_analysis_tracks_nested_join_inside_outer_arm(tmp_path: Path) -> None:
    type_env, workflows, workflow_return_types, procedure_return_types = _compile_fixture(
        CHARACTERIZATION_FIXTURES / "wcc_m3_nested_join_inside_arm.orc",
        tmp_path=tmp_path,

    )

    body = elaborate_typed_workflow_body(
        workflows["wcc_m3_nested_join_inside_arm::summarize"].typed_body,
        owner_name=workflows["wcc_m3_nested_join_inside_arm::summarize"].definition.name,
        value_env=dict(workflows["wcc_m3_nested_join_inside_arm::summarize"].signature.params),
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    analysis = analyze_wcc_body(normalize_wcc_body_to_anf(body))

    assert len(analysis.joins_by_name) == 2
    assert sorted(site.live_out_names for site in analysis.joins_by_name.values()) == [
        ("approved_report",),
        ("summary",),
    ]
