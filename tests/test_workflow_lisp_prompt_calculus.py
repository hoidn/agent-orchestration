"""Focused acceptance tests for the 2.20 prompt core and 2.21 output positions."""

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path

import pytest

from orchestrator.exceptions import WorkflowValidationError
import orchestrator.workflow_lisp as workflow_lisp
import orchestrator.workflow_lisp.compiler as workflow_lisp_compiler
import orchestrator.workflow_lisp.form_registry as form_registry
import orchestrator.workflow_lisp.lowering.pure_projection as pure_projection_lowering
import orchestrator.workflow_lisp.prompts as prompt_calculus
import orchestrator.workflow_lisp.syntax as syntax
from orchestrator.workflow.core_ast import workflow_core_ast_to_json
from orchestrator.workflow.executable_ir import (
    validate_executable_workflow,
    workflow_executable_ir_to_json,
)
from orchestrator.workflow.prompt_dependency_contract import (
    serialize_compiler_prompt_dependency_contract,
)
from orchestrator.workflow.prompt_fragment_contract import (
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
    CompilerPromptFragmentContract,
    CompilerPromptFragmentRenderedSlot,
    canonical_compiler_prompt_fragment_contract_json,
    serialize_compiler_prompt_fragment_rendered_slot,
)
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.definitions import (
    PathDef,
    RecordField,
    WorkflowLispModule,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import ProviderResultExpr, elaborate_expression
from orchestrator.workflow_lisp.modules import (
    build_import_scope,
    derive_export_surface,
)
from orchestrator.workflow_lisp.prompts import (
    PromptApplicationExpr,
    build_prompt_catalog,
    validate_compiled_prompt_fragment_identity,
)
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
)
from orchestrator.workflow_lisp.typecheck import typecheck_expression
from orchestrator.workflow_lisp.workflows import ExternEnvironment, ProviderExtern


def _compile_fragment_workflow(
    tmp_path: Path,
    *,
    lowering_route: str,
    target_dsl: str = "2.20",
):
    source_path = tmp_path / f"prompt_fragment_{lowering_route}.orc"
    source_path.write_text(
        _module_source(
            target_dsl,
            "(defmodule demo/prompt-fragment)",
            """
            (defpath DesignDocPath
              :kind relpath
              :under "docs/design"
              :must-exist true)
            """,
            """
            (defpath WorkReportPath
              :kind relpath
              :under "artifacts/work"
              :must-exist false)
            """,
            """
            (defprompt review
              (:fills
                (target_doc :doc DesignDocPath)
                (message :text)
                (score :value Int)
                (report_path :path WorkReportPath))
              -> Bool
              "Message={message}; score={score}; report={report_path}; again={message}")
            """,
            """
            (defworkflow run-review
              ((target_doc DesignDocPath)
               (message String)
               (score Int)
               (report_path WorkReportPath))
              -> Bool
              (provider-result providers.review
                :prompt
                  (review
                    :report_path report_path
                    :score score
                    :target_doc target_doc
                    :message message)))
            """,
        )
        + "\n",
        encoding="utf-8",
    )
    return workflow_lisp.compile_stage3_module(
        source_path,
        provider_externs={"providers.review": "test-provider"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=lowering_route,
    )


def _compile_zero_document_fragment_workflow(
    tmp_path: Path,
    *,
    lowering_route: str,
):
    source_path = tmp_path / f"zero_document_fragment_{lowering_route}.orc"
    source_path.write_text(
        _module_source(
            "2.20",
            "(defmodule demo/zero-document-fragment)",
            """
            (defprompt inspect
              (:fills
                (message :text)
                (payload :value Value))
              -> Bool
              "Message={message}; payload={payload}")
            """,
            """
            (defworkflow run-inspect
              ((message String)
               (payload Value))
              -> Bool
              (provider-result providers.review
                :prompt
                  (inspect
                    :payload payload
                    :message message)))
            """,
        )
        + "\n",
        encoding="utf-8",
    )
    return workflow_lisp.compile_stage3_module(
        source_path,
        provider_externs={"providers.review": "test-provider"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=lowering_route,
    )


def _module_source(target_dsl: str, *forms: str) -> str:
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            f'  (:target-dsl "{target_dsl}")',
            *(f"  {form}" for form in forms),
            ")",
        )
    )


def _parse_prompts(target_dsl: str, *forms: str):
    module = syntax.build_syntax_module(
        read_sexpr_text(
            _module_source(target_dsl, *forms),
            source_path="inline_prompt_calculus.orc",
        )
    )
    return workflow_lisp.elaborate_prompt_definitions(module)


def _diagnostic_code(
    excinfo: pytest.ExceptionInfo[LispFrontendCompileError],
) -> str:
    return excinfo.value.diagnostics[0].code


def test_prompt_calculus_target_gate_and_registry_are_target_aware() -> None:
    assert syntax.PROMPT_CALCULUS_MIN_TARGET_DSL_VERSION == "2.20"
    assert "2.20" in syntax.SUPPORTED_TARGET_DSL_VERSIONS
    assert "2.21" in syntax.SUPPORTED_TARGET_DSL_VERSIONS
    assert not syntax.target_dsl_supports_prompt_calculus("2.19")
    assert syntax.target_dsl_supports_prompt_calculus("2.20")
    assert syntax.target_dsl_supports_prompt_calculus("2.21")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _parse_prompts(
            "2.19",
            '(defprompt p (:fills (message :text)) "Message: {message}")',
        )
    assert _diagnostic_code(excinfo) == "prompt_calculus_requires_dsl_2_20"

    assert form_registry.get_form_spec(
        "defprompt",
        target_dsl_version="2.19",
    ) is None
    spec = form_registry.get_form_spec(
        "defprompt",
        target_dsl_version="2.20",
    )
    assert spec is not None
    assert spec.kind is form_registry.FormKind.TOP_LEVEL_DEFINITION
    assert spec.owner_module == "prompts"
    assert spec.admitted_top_level
    assert "defprompt" not in form_registry.reserved_macro_names()
    assert "defprompt" not in form_registry.admitted_top_level_heads()
    assert "defprompt" in form_registry.reserved_macro_names(
        target_dsl_version="2.20"
    )
    assert "defprompt" in form_registry.admitted_top_level_heads(
        target_dsl_version="2.20"
    )


def _source_owned_text(source: str, span) -> str:
    return source[span.start.offset : span.end.offset]


def _related_source_note(span) -> str:
    return (
        f"related source: {span.start.path}:"
        f"{span.start.line}:{span.start.column}"
    )


def test_prompt_output_position_target_gate_precedes_legacy_tail_errors() -> None:
    source = _module_source(
        "2.20",
        '(defprompt p (:fills (report :path :out :bad)) "{report}")',
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        module = syntax.build_syntax_module(
            read_sexpr_text(source, source_path="output_target_gate.orc")
        )
        workflow_lisp.elaborate_prompt_definitions(module)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "prompt_output_positions_require_dsl_2_21"
    assert _source_owned_text(source, diagnostic.span) == ":out"


def test_prompt_output_position_parses_closed_role_and_retains_out_span() -> None:
    source = _module_source(
        "2.21",
        '(defprompt p (:fills (report :path :out)) "{report}")',
    )
    module = syntax.build_syntax_module(
        read_sexpr_text(source, source_path="output_role.orc")
    )
    (prompt,) = workflow_lisp.elaborate_prompt_definitions(module)
    (slot,) = prompt.slots

    assert slot.kind is workflow_lisp.PromptSlotKind.PATH
    assert slot.output_role is prompt_calculus.PromptOutputRole.REQUIRED_STRING_FILE
    assert slot.output_role.value == "required_string_file"
    assert slot.output_role_span is not None
    assert _source_owned_text(source, slot.output_role_span) == ":out"
    assert slot.refinement_type_name is None


@pytest.mark.parametrize(
    ("slot", "owned_text"),
    (
        ("(report :out)", ":out"),
        ("(report :path :out :out)", ":out"),
        ("(report :path WorkReportPath :out)", ":out"),
        ("(report :path :out WorkReportPath Extra)", "(report :path :out WorkReportPath Extra)"),
    ),
)
def test_prompt_output_position_rejects_duplicate_misplaced_or_open_tail(
    slot: str,
    owned_text: str,
) -> None:
    source = _module_source(
        "2.21",
        f'(defprompt p (:fills {slot}) "{{report}}")',
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        module = syntax.build_syntax_module(
            read_sexpr_text(source, source_path="output_syntax.orc")
        )
        workflow_lisp.elaborate_prompt_definitions(module)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "prompt_output_position_syntax_invalid"
    if slot == "(report :path :out :out)":
        assert diagnostic.span.start.offset == source.rindex(":out")
    else:
        assert _source_owned_text(source, diagnostic.span) == owned_text


def test_prompt_output_position_syntax_and_kind_precede_q1_slot_checks() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _parse_prompts(
            "2.21",
            '(defprompt p (:fills (report :text :out :out)) "{report}")',
        )
    assert _diagnostic_code(excinfo) == "prompt_output_position_syntax_invalid"

    source = _module_source(
        "2.21",
        '(defprompt p (:fills (report :text :out)) "{report}")',
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        module = syntax.build_syntax_module(
            read_sexpr_text(source, source_path="output_kind.orc")
        )
        prompt_form = syntax.syntax_node_datum(module.forms[0])
        kind_span = prompt_form.items[2].items[1].items[1].span
        workflow_lisp.elaborate_prompt_definitions(module)
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "prompt_output_position_kind_invalid"
    assert _source_owned_text(source, diagnostic.span) == ":out"
    assert diagnostic.notes == (_related_source_note(kind_span),)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _parse_prompts(
            "2.21",
            """
            (defprompt p
              (:fills (report :path :out) (report :text))
              "{report}")
            """,
        )
    assert _diagnostic_code(excinfo) == "prompt_slot_duplicate"


def test_prompt_output_position_q1_placeholder_validation_precedes_q2_refinement() -> None:
    type_env = _output_position_type_env()
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _catalog(
            """
            (defprompt p
              (:fills (report :path :out ExistingReportPath))
              "No rendered output path")
            """,
            target_dsl="2.21",
            type_env=type_env,
        )
    assert _diagnostic_code(excinfo) == "prompt_placeholder_missing"

    source = _module_source(
        "2.21",
        """
        (defprompt p
          (:fills (report :path :out ExistingReportPath))
          "{report}")
        """,
    )
    module = syntax.build_syntax_module(
        read_sexpr_text(source, source_path="output_refinement.orc")
    )
    definitions = workflow_lisp.elaborate_prompt_definitions(module)
    output_role_span = definitions[0].slots[0].output_role_span
    assert output_role_span is not None
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_prompt_catalog(
            "demo/prompts",
            definitions,
            type_env=type_env,
        )
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "prompt_output_position_refinement_invalid"
    assert _source_owned_text(source, diagnostic.span) == "ExistingReportPath"
    assert diagnostic.notes == (_related_source_note(output_role_span),)


def test_prompt_output_position_preserves_q1_no_output_refinement_owner() -> None:
    source = _module_source(
        "2.20",
        '(defprompt review (:fills (report :path String)) "{report}")',
    )
    module = syntax.build_syntax_module(
        read_sexpr_text(
            source,
            source_path="q1_refinement_owner.orc",
        )
    )
    definitions = workflow_lisp.elaborate_prompt_definitions(module)
    slot = definitions[0].slots[0]

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_prompt_catalog(
            "demo/prompts",
            definitions,
            type_env=_empty_type_env(),
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "prompt_slot_refinement_invalid"
    assert diagnostic.message == (
        "refinement `String` is not admissible for `:path`"
    )
    assert diagnostic.span == slot.span
    assert _source_owned_text(source, diagnostic.span) == "(report :path String)"
    assert diagnostic.form_path == slot.form_path
    assert diagnostic.notes == ()


def test_prompt_output_position_defect_removal_exposes_each_next_frontend_phase(
    tmp_path: Path,
) -> None:
    type_env = _output_position_type_env()

    q1_refinement_source = _module_source(
        "2.21",
        """
        (defprompt review
          (:fills (report :path :out String))
          "{report}")
        """,
    )
    q1_module = syntax.build_syntax_module(
        read_sexpr_text(
            q1_refinement_source,
            source_path="output_precedence_q1_refinement.orc",
        )
    )
    q1_definitions = workflow_lisp.elaborate_prompt_definitions(q1_module)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_prompt_catalog(
            "demo/prompts",
            q1_definitions,
            type_env=type_env,
        )
    q1_refinement = excinfo.value.diagnostics[0]
    assert q1_refinement.code == "prompt_slot_refinement_invalid"
    assert _source_owned_text(
        q1_refinement_source,
        q1_refinement.span,
    ) == "String"
    assert q1_refinement.notes == ()

    q2_refinement_source = q1_refinement_source.replace(
        "String",
        "ExistingReportPath",
    )
    q2_module = syntax.build_syntax_module(
        read_sexpr_text(
            q2_refinement_source,
            source_path="output_precedence_q2_refinement.orc",
        )
    )
    q2_definitions = workflow_lisp.elaborate_prompt_definitions(q2_module)
    q2_output_span = q2_definitions[0].slots[0].output_role_span
    assert q2_output_span is not None
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_prompt_catalog(
            "demo/prompts",
            q2_definitions,
            type_env=type_env,
        )
    q2_refinement = excinfo.value.diagnostics[0]
    assert q2_refinement.code == "prompt_output_position_refinement_invalid"
    assert _source_owned_text(
        q2_refinement_source,
        q2_refinement.span,
    ) == "ExistingReportPath"
    assert q2_refinement.notes == (_related_source_note(q2_output_span),)

    source_root = tmp_path / "src"
    helper_path = source_root / "demo" / "prompts.orc"
    helper_path.parent.mkdir(parents=True)
    helper_source = _module_source(
        "2.21",
        "(defmodule demo/prompts)",
        "(export ReportPath review)",
        """
        (defpath ReportPath
          :kind relpath
          :under "artifacts/reports"
          :must-exist false)
        """,
        """
        (defprompt review
          (:fills (report :path :out ReportPath))
          "{report}")
        """,
    )
    helper_path.write_text(helper_source, encoding="utf-8")
    helper_module = syntax.build_syntax_module(
        read_sexpr_text(
            helper_source,
            source_path=str(helper_path),
        )
    )
    report_declaration = workflow_lisp.elaborate_prompt_definitions(
        helper_module
    )[0].slots[0]

    entry_path = source_root / "demo" / "entry_missing_export.orc"
    unresolved_prompt_source = _module_source(
        "2.21",
        "(defmodule demo/entry_missing_export)",
        "(import demo/prompts :as prompts :only (ReportPath absent))",
        """
        (defworkflow run-review ((report ReportPath)) -> Value
          (provider-result providers.review
            :prompt (review :unknown report)))
        """,
    )
    entry_path.write_text(unresolved_prompt_source, encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            entry_path,
            source_roots=(source_root,),
            provider_externs={"providers.review": "test-provider"},
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="legacy",
        )
    unresolved_prompt = excinfo.value.diagnostics[0]
    assert unresolved_prompt.code == "module_export_missing"
    assert _source_owned_text(
        unresolved_prompt_source,
        unresolved_prompt.span,
    ) == "(import demo/prompts :as prompts :only (ReportPath absent))"
    assert unresolved_prompt.notes == ()

    unknown_fill_source = unresolved_prompt_source.replace(
        "(ReportPath absent)",
        "(ReportPath review)",
    ).replace("demo/entry_missing_export", "demo/entry_unknown_fill")
    unknown_fill_path = source_root / "demo" / "entry_unknown_fill.orc"
    unknown_fill_path.write_text(unknown_fill_source, encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            unknown_fill_path,
            source_roots=(source_root,),
            provider_externs={"providers.review": "test-provider"},
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="legacy",
        )
    unknown_fill = excinfo.value.diagnostics[0]
    assert unknown_fill.code == "prompt_fill_unknown"
    assert _source_owned_text(
        unknown_fill_source,
        unknown_fill.span,
    ) == ":unknown"
    assert unknown_fill.notes == ()

    missing_fill_source = unknown_fill_source.replace(
        "(review :unknown report)",
        "(review)",
    ).replace("demo/entry_unknown_fill", "demo/entry_missing_fill")
    missing_fill_path = source_root / "demo" / "entry_missing_fill.orc"
    missing_fill_path.write_text(missing_fill_source, encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            missing_fill_path,
            source_roots=(source_root,),
            provider_externs={"providers.review": "test-provider"},
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="legacy",
        )
    missing_fill = excinfo.value.diagnostics[0]
    assert missing_fill.code == "prompt_slot_undischarged"
    assert _source_owned_text(
        missing_fill_source,
        missing_fill.span,
    ) == "(review)"
    assert missing_fill.notes == (_related_source_note(report_declaration.span),)


def test_prompt_output_position_definition_wide_target_and_syntax_precedence() -> None:
    below_target = _module_source(
        "2.20",
        """
        (defprompt review
          (:fills
            (earlier :blob)
            (report :path :out))
          "{report}")
        """,
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        module = syntax.build_syntax_module(
            read_sexpr_text(
                below_target,
                source_path="output_cross_slot_target.orc",
            )
        )
        workflow_lisp.elaborate_prompt_definitions(module)
    target_gate = excinfo.value.diagnostics[0]
    assert target_gate.code == "prompt_output_positions_require_dsl_2_21"
    assert _source_owned_text(below_target, target_gate.span) == ":out"

    competing_slots = (
        "(report :path :out :out)",
        "(report :path ReportPath :out)",
    )
    for index, later_slot in enumerate(competing_slots):
        source = _module_source(
            "2.21",
            f"""
            (defprompt review
              (:fills
                (earlier :text :out)
                {later_slot})
              "{{earlier}} {{report}}")
            """,
        )
        with pytest.raises(LispFrontendCompileError) as excinfo:
            module = syntax.build_syntax_module(
                read_sexpr_text(
                    source,
                    source_path=f"output_cross_slot_syntax_{index}.orc",
                )
            )
            workflow_lisp.elaborate_prompt_definitions(module)
        syntax_error = excinfo.value.diagnostics[0]
        assert syntax_error.code == "prompt_output_position_syntax_invalid"
        if index == 0:
            assert syntax_error.span.start.offset == source.rindex(":out")
        else:
            assert _source_owned_text(source, syntax_error.span) == ":out"

    kind_only = _module_source(
        "2.21",
        """
        (defprompt review
          (:fills
            (earlier :text :out)
            (report :path :out))
          "{earlier} {report}")
        """,
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        module = syntax.build_syntax_module(
            read_sexpr_text(
                kind_only,
                source_path="output_cross_slot_kind.orc",
            )
        )
        workflow_lisp.elaborate_prompt_definitions(module)
    kind_error = excinfo.value.diagnostics[0]
    assert kind_error.code == "prompt_output_position_kind_invalid"
    assert _source_owned_text(kind_only, kind_error.span) == ":out"


@pytest.mark.parametrize(
    ("later_slot", "template", "code", "owned_text"),
    (
        (
            "(report :path :out)",
            "{first} {report}",
            "prompt_slot_duplicate",
            "(report :path :out)",
        ),
        (
            "(later :blob)",
            "{first}",
            "prompt_slot_kind_unknown",
            ":blob",
        ),
        (
            "(later :text String)",
            "{first} {later}",
            "prompt_slot_refinement_invalid",
            "String",
        ),
        (
            "(later :text)",
            "{first}",
            "prompt_placeholder_missing",
            "(later :text)",
        ),
    ),
)
def test_prompt_output_position_all_q1_definition_checks_precede_q2_refinement(
    later_slot: str,
    template: str,
    code: str,
    owned_text: str,
) -> None:
    first_name = "report" if code == "prompt_slot_duplicate" else "first"
    source = _module_source(
        "2.21",
        f"""
        (defprompt review
          (:fills
            ({first_name} :path :out ExistingReportPath)
            {later_slot})
          "{template}")
        """,
    )
    module = syntax.build_syntax_module(
        read_sexpr_text(
            source,
            source_path=f"output_q1_before_q2_{code}.orc",
        )
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        definitions = workflow_lisp.elaborate_prompt_definitions(module)
        build_prompt_catalog(
            "demo/prompts",
            definitions,
            type_env=_output_position_type_env(),
        )
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == code
    assert _source_owned_text(source, diagnostic.span) == owned_text


def test_prompt_output_position_catalog_runs_all_q1_refinements_before_q2() -> None:
    source = _module_source(
        "2.21",
        """
        (defprompt review
          (:fills
            (report :path :out ExistingReportPath)
            (later :path String))
          "{report} {later}")
        """,
    )
    module = syntax.build_syntax_module(
        read_sexpr_text(
            source,
            source_path="output_catalog_phase_order.orc",
        )
    )
    definitions = workflow_lisp.elaborate_prompt_definitions(module)
    later_slot = definitions[0].slots[1]
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_prompt_catalog(
            "demo/prompts",
            definitions,
            type_env=_output_position_type_env(),
        )
    q1_refinement = excinfo.value.diagnostics[0]
    assert q1_refinement.code == "prompt_slot_refinement_invalid"
    assert q1_refinement.span == later_slot.span
    assert _source_owned_text(source, q1_refinement.span) == "(later :path String)"

    q2_only_source = source.replace(
        "\n            (later :path String)",
        "",
    ).replace(" {later}", "")
    q2_module = syntax.build_syntax_module(
        read_sexpr_text(
            q2_only_source,
            source_path="output_catalog_q2_only.orc",
        )
    )
    q2_definitions = workflow_lisp.elaborate_prompt_definitions(q2_module)
    q2_output_span = q2_definitions[0].slots[0].output_role_span
    assert q2_output_span is not None
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_prompt_catalog(
            "demo/prompts",
            q2_definitions,
            type_env=_output_position_type_env(),
        )
    q2_refinement = excinfo.value.diagnostics[0]
    assert q2_refinement.code == "prompt_output_position_refinement_invalid"
    assert _source_owned_text(
        q2_only_source,
        q2_refinement.span,
    ) == "ExistingReportPath"
    assert q2_refinement.notes == (_related_source_note(q2_output_span),)


def _cross_slot_output_application(
    *,
    second_declaration: str,
    application: str,
    second_type,
):
    type_env = _output_position_type_env()
    catalog = _catalog(
        (
            "(defprompt review "
            f"(:fills (report :path :out) {second_declaration}) "
            '"{report} {second}")'
        ),
        target_dsl="2.21",
        type_env=type_env,
    )
    expr = _elaborate_provider(
        f"(provider-result providers.review :prompt {application})",
        catalog=catalog,
        bound_names=frozenset(
            {"providers.review", "report", "second"}
        ),
        target_dsl="2.21",
    )
    span = expr.span
    existing_path = PathTypeRef(
        name="ExistingReportPath",
        definition=PathDef(
            name="ExistingReportPath",
            kind="relpath",
            under="artifacts/reports",
            must_exist=True,
            span=span,
        ),
    )
    return typecheck_expression(
        expr,
        type_env=type_env,
        value_env={
            "providers.review": PrimitiveTypeRef(name="Provider"),
            "report": existing_path,
            "second": second_type,
        },
        extern_environment=ExternEnvironment(
            bindings_by_name={
                "providers.review": ProviderExtern(
                    name="providers.review",
                    provider_id="test-provider",
                )
            }
        ),
        prompt_catalog=catalog,
    )


def test_prompt_output_position_application_q1_discharge_precedes_q2_fill() -> None:
    catalog = _catalog(
        """
        (defprompt review
          (:fills (report :path :out) (second :text))
          "{report} {second}")
        """,
        target_dsl="2.21",
    )
    unknown_application = "(review :report report :unknown second)"
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_provider(
            f"(provider-result providers.review :prompt {unknown_application})",
            catalog=catalog,
            bound_names=frozenset(
                {"providers.review", "report", "second"}
            ),
            target_dsl="2.21",
        )
    unknown = excinfo.value.diagnostics[0]
    assert unknown.code == "prompt_fill_unknown"
    assert _source_owned_text(
        _provider_wrapper_source(
            f"(provider-result providers.review :prompt {unknown_application})",
            target_dsl="2.21",
        ),
        unknown.span,
    ) == ":unknown"

    missing_application = "(review :report report)"
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_provider(
            f"(provider-result providers.review :prompt {missing_application})",
            catalog=catalog,
            bound_names=frozenset({"providers.review", "report"}),
            target_dsl="2.21",
        )
    missing = excinfo.value.diagnostics[0]
    assert missing.code == "prompt_slot_undischarged"
    assert _source_owned_text(
        _provider_wrapper_source(
            f"(provider-result providers.review :prompt {missing_application})",
            target_dsl="2.21",
        ),
        missing.span,
    ) == missing_application


@pytest.mark.parametrize(
    ("second_declaration", "second_type", "code"),
    (
        (
            "(second :text)",
            PrimitiveTypeRef(name="Int"),
            "prompt_slot_type_mismatch",
        ),
        (
            "(second :value)",
            OptionalTypeRef(
                name="Optional[String]",
                item_type_ref=PrimitiveTypeRef(name="String"),
            ),
            "prompt_fill_renderer_unsupported",
        ),
    ),
)
def test_prompt_output_position_application_runs_all_q1_types_before_q2_fill(
    second_declaration: str,
    second_type,
    code: str,
) -> None:
    application = "(review :report report :second second)"
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _cross_slot_output_application(
            second_declaration=second_declaration,
            application=application,
            second_type=second_type,
        )
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == code
    assert _source_owned_text(
        _provider_wrapper_source(
            f"(provider-result providers.review :prompt {application})",
            target_dsl="2.21",
        ),
        diagnostic.span,
    ) == "second"


def test_registered_form_heads_uses_the_same_target_filter_as_registry_views() -> None:
    ungated_heads = form_registry.registered_form_heads()
    target_219_heads = form_registry.registered_form_heads(
        target_dsl_version="2.19"
    )
    target_220_heads = form_registry.registered_form_heads(
        target_dsl_version="2.20"
    )

    assert target_219_heads == ungated_heads
    assert "defprompt" not in ungated_heads
    assert target_220_heads == tuple(sorted((*ungated_heads, "defprompt")))
    assert all(
        form_registry.get_form_spec(name) is not None
        for name in ungated_heads
    )
    assert all(
        form_registry.get_form_spec(
            name,
            target_dsl_version="2.20",
        )
        is not None
        for name in target_220_heads
    )
    assert form_registry.reserved_macro_names(
        target_dsl_version="2.20"
    ).issubset(target_220_heads)
    assert form_registry.admitted_top_level_heads(
        target_dsl_version="2.20"
    ).issubset(target_220_heads)


def test_defprompt_parses_immutable_slots_template_and_structured_return() -> None:
    (prompt,) = _parse_prompts(
        "2.20",
        """
        (defprompt review
          (:fills
            (target_doc :doc DesignDocPath)
            (focus :text)
            (payload :value ReviewPayload)
            (report_path :path WorkReportPath))
          -> (result Bool
               :description "Approve only complete work."
               :format-hint "JSON boolean."
               :example true)
          "Focus: {focus}; payload={payload}; report={report_path}; again={focus}; {{literal}}")
        """,
    )

    assert prompt.name == "review"
    assert tuple(slot.name for slot in prompt.slots) == (
        "target_doc",
        "focus",
        "payload",
        "report_path",
    )
    assert tuple(slot.kind for slot in prompt.slots) == (
        workflow_lisp.PromptSlotKind.DOC,
        workflow_lisp.PromptSlotKind.TEXT,
        workflow_lisp.PromptSlotKind.VALUE,
        workflow_lisp.PromptSlotKind.PATH,
    )
    assert tuple(slot.refinement_type_name for slot in prompt.slots) == (
        "DesignDocPath",
        None,
        "ReviewPayload",
        "WorkReportPath",
    )
    assert prompt.template.placeholder_names == (
        "focus",
        "payload",
        "report_path",
        "focus",
    )
    assert prompt.return_spec.type_name == "Bool"
    assert prompt.return_spec.guidance is not None
    assert prompt.return_spec.guidance.description == "Approve only complete work."
    assert prompt.return_spec.guidance.format_hint == "JSON boolean."
    assert prompt.return_spec.guidance.example_expr is not None

    with pytest.raises(FrozenInstanceError):
        prompt.name = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        prompt.slots[0].name = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        prompt.template.text = "changed"  # type: ignore[misc]


def test_defprompt_omitted_return_defaults_to_exact_value() -> None:
    (prompt,) = _parse_prompts(
        "2.20",
        '(defprompt echo (:fills (message :text)) "Message: {message}")',
    )

    assert prompt.return_spec.type_name == "Value"
    assert prompt.return_spec.guidance is None


@pytest.mark.parametrize(
    ("declaration", "code"),
    (
        ('(defprompt p "template")', "frontend_parse_error"),
        (
            '(defprompt p (:fill (message :text)) "{message}")',
            "frontend_parse_error",
        ),
        ("(defprompt p (:fills))", "frontend_parse_error"),
        (
            '(defprompt p (:fills) "first" "second")',
            "frontend_parse_error",
        ),
        (
            '(defprompt p (:fills) => Bool "template")',
            "frontend_parse_error",
        ),
        (
            '(defprompt p (:fills) -> 1 "template")',
            "result_guidance_invalid",
        ),
        ("(defprompt p (:fills) 42)", "frontend_parse_error"),
    ),
)
def test_defprompt_structural_errors_are_frontend_diagnostics(
    declaration: str,
    code: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _parse_prompts("2.20", declaration)

    assert _diagnostic_code(excinfo) == code
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.span.start.path == "inline_prompt_calculus.orc"
    assert diagnostic.form_path[:2] == ("workflow-lisp", "defprompt")


@pytest.mark.parametrize(
    ("slot", "code"),
    (
        ("(message :blob)", "prompt_slot_kind_unknown"),
        ("(message :text String)", "prompt_slot_refinement_invalid"),
        (
            "(message :value :out)",
            "prompt_output_positions_require_dsl_2_21",
        ),
    ),
)
def test_defprompt_rejects_invalid_slot_kind_or_refinement(
    slot: str,
    code: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _parse_prompts(
            "2.20",
            f'(defprompt p (:fills {slot}) "Message: {{message}}")',
        )

    assert _diagnostic_code(excinfo) == code


def test_defprompt_rejects_duplicate_slot_before_template_validation() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _parse_prompts(
            "2.20",
            """
            (defprompt p
              (:fills (message :text) (message :value String))
              "Malformed {")
            """,
        )

    assert _diagnostic_code(excinfo) == "prompt_slot_duplicate"


@pytest.mark.parametrize(
    "template",
    (
        "Message: {",
        "Message: }",
        "Message: {}",
        "Message: {bad.name}",
        "Message: { bad}",
        "Message: {message!r}",
        "Message: {message[0]}",
    ),
)
def test_defprompt_rejects_malformed_placeholder_syntax(template: str) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _parse_prompts(
            "2.20",
            f'(defprompt p (:fills (message :text)) "{template}")',
        )

    assert _diagnostic_code(excinfo) == "prompt_placeholder_syntax_invalid"


def test_defprompt_rejects_undeclared_placeholder_before_missing_slot() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _parse_prompts(
            "2.20",
            '(defprompt p (:fills (message :text)) "{unknown}")',
        )

    assert _diagnostic_code(excinfo) == "prompt_placeholder_undeclared"


def test_defprompt_requires_each_rendered_slot_in_template() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _parse_prompts(
            "2.20",
            '(defprompt p (:fills (message :text) (payload :value Row)) "{message}")',
        )

    assert _diagnostic_code(excinfo) == "prompt_placeholder_missing"
    assert excinfo.value.diagnostics[0].span.start.line == 4


def test_defprompt_forbids_document_placeholder() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _parse_prompts(
            "2.20",
            '(defprompt p (:fills (target :doc DesignDocPath)) "Read {target}")',
        )

    assert _diagnostic_code(excinfo) == "prompt_doc_placeholder_forbidden"


def test_defprompt_allows_document_only_template_without_placeholders() -> None:
    (prompt,) = _parse_prompts(
        "2.20",
        '(defprompt p (:fills (target :doc DesignDocPath)) "Review the injected document.")',
    )

    assert prompt.template.placeholder_names == ()
    assert prompt.return_spec.type_name == "Value"


def _empty_type_env(*, target_dsl: str = "2.20") -> FrontendTypeEnvironment:
    parsed = syntax.build_syntax_module(
        read_sexpr_text(
            _module_source(target_dsl),
            source_path="inline_prompt_types.orc",
        )
    )
    module = WorkflowLispModule(
        language_version=parsed.language_version,
        target_dsl_version=parsed.target_dsl_version,
        module_name="demo/prompts",
        imports=(),
        exports=(),
        definitions=(),
        schemas=(),
        span=parsed.span,
    )
    return FrontendTypeEnvironment.from_module(module)


def _output_position_type_env() -> FrontendTypeEnvironment:
    parsed = syntax.build_syntax_module(
        read_sexpr_text(
            _module_source("2.21"),
            source_path="inline_prompt_output_types.orc",
        )
    )
    definitions = (
        PathDef(
            name="ReportPath",
            kind="relpath",
            under="artifacts/reports",
            must_exist=False,
            span=parsed.span,
        ),
        PathDef(
            name="ExistingReportPath",
            kind="relpath",
            under="artifacts/reports",
            must_exist=True,
            span=parsed.span,
        ),
    )
    module = WorkflowLispModule(
        language_version=parsed.language_version,
        target_dsl_version=parsed.target_dsl_version,
        module_name="demo/prompts",
        imports=(),
        exports=(),
        definitions=definitions,
        schemas=(),
        span=parsed.span,
    )
    return FrontendTypeEnvironment.from_module(module)


def _catalog(
    *declarations: str,
    target_dsl: str = "2.20",
    type_env: FrontendTypeEnvironment | None = None,
):
    parsed = syntax.build_syntax_module(
        read_sexpr_text(
            _module_source(target_dsl, *declarations),
            source_path="inline_prompt_catalog.orc",
        )
    )
    definitions = workflow_lisp.elaborate_prompt_definitions(parsed)
    return build_prompt_catalog(
        "demo/prompts",
        definitions,
        type_env=type_env or _empty_type_env(target_dsl=target_dsl),
    )


def _elaborate_provider(
    source: str,
    *,
    catalog,
    bound_names=frozenset(),
    target_dsl: str = "2.20",
):
    parsed = syntax.build_syntax_module(
        read_sexpr_text(
            _provider_wrapper_source(source, target_dsl=target_dsl),
            source_path="inline_prompt_wrapper.orc",
        )
    )
    form = parsed.forms[-1]
    body_datum = syntax.syntax_node_datum(form).items[-1]
    return elaborate_expression(
        syntax.SyntaxNode(
            datum=body_datum,
            span=body_datum.span,
            module_path=form.module_path,
            form_path=form.form_path,
        ),
        bound_names=bound_names,
        prompt_catalog=catalog,
        target_dsl_version=target_dsl,
    )


def _provider_wrapper_source(
    application_source: str,
    *,
    target_dsl: str,
) -> str:
    return _module_source(
        target_dsl,
        f"(defworkflow ignored () -> Value {application_source})",
    )


def test_prompt_namespace_exports_and_imports_without_becoming_a_procedure() -> None:
    helper_syntax = syntax.build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.20",
                "(defmodule demo/helper)",
                "(export review)",
                '(defprompt review (:fills (message :text)) "Review {message}")',
                "(defproc review ((message String)) -> String message)",
            ),
            source_path="demo/helper.orc",
        )
    )
    surface = derive_export_surface(
        helper_syntax,
        procedure_names=("review",),
        prompt_names=("review",),
    )
    assert surface.prompts_by_name["review"].kind == "prompt"
    assert surface.procedures_by_name["review"].kind == "procedure"

    entry_syntax = syntax.build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.20",
                "(defmodule demo/entry)",
                "(import demo/helper :as helper :only (review))",
            ),
            source_path="demo/entry.orc",
        )
    )
    entry_module = WorkflowLispModule(
        language_version=entry_syntax.language_version,
        target_dsl_version=entry_syntax.target_dsl_version,
        module_name=entry_syntax.module_name,
        imports=entry_syntax.imports,
        exports=(),
        definitions=(),
        schemas=(),
        span=entry_syntax.span,
    )
    scope = build_import_scope(
        entry_module,
        export_surfaces_by_name={"demo/helper": surface},
    )
    assert scope.resolve_prompt_name(
        "review",
        span=entry_syntax.span,
        form_path=("workflow-lisp",),
    ) == "demo/helper::review"
    assert scope.resolve_prompt_name(
        "helper.review",
        span=entry_syntax.span,
        form_path=("workflow-lisp",),
    ) == "demo/helper::review"
    assert scope.resolve_procedure_name(
        "review",
        span=entry_syntax.span,
        form_path=("workflow-lisp",),
    ) == "demo/helper::review"


def test_duplicate_prompt_declarations_use_module_ownership_while_slots_precede() -> None:
    parsed = syntax.build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.20",
                '(defprompt review (:fills (message :text)) "Review {message}")',
                '(defprompt review (:fills (payload :value)) "Review {payload}")',
            ),
            source_path="duplicate_prompt_declarations.orc",
        )
    )
    definitions = workflow_lisp.elaborate_prompt_definitions(parsed)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_prompt_catalog(
            "demo/prompts",
            definitions,
            type_env=_empty_type_env(),
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "definition_duplicate"
    assert diagnostic.span == definitions[1].span
    assert diagnostic.form_path == definitions[1].form_path

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _catalog(
            """
            (defprompt review
              (:fills (message :text) (message :value))
              "Review {message}")
            """,
            '(defprompt review (:fills (payload :value)) "Review {payload}")',
        )
    assert _diagnostic_code(excinfo) == "prompt_slot_duplicate"


def test_prompt_imports_reject_ambiguous_and_missing_exports() -> None:
    surfaces = {}
    for module_name in ("demo/left", "demo/right"):
        module_syntax = syntax.build_syntax_module(
            read_sexpr_text(
                _module_source(
                    "2.20",
                    f"(defmodule {module_name})",
                    "(export review)",
                    '(defprompt review (:fills (message :text)) "Review {message}")',
                ),
                source_path=f"{module_name}.orc",
            )
        )
        surfaces[module_name] = derive_export_surface(
            module_syntax,
            prompt_names=("review",),
        )

    ambiguous_syntax = syntax.build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.20",
                "(defmodule demo/entry)",
                "(import demo/left :as left :only (review))",
                "(import demo/right :as right :only (review))",
            ),
            source_path="demo/entry.orc",
        )
    )
    ambiguous_module = WorkflowLispModule(
        language_version=ambiguous_syntax.language_version,
        target_dsl_version=ambiguous_syntax.target_dsl_version,
        module_name=ambiguous_syntax.module_name,
        imports=ambiguous_syntax.imports,
        exports=(),
        definitions=(),
        schemas=(),
        span=ambiguous_syntax.span,
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_import_scope(
            ambiguous_module,
            export_surfaces_by_name=surfaces,
        )
    assert _diagnostic_code(excinfo) == "module_import_ambiguous"

    missing_syntax = syntax.build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.20",
                "(defmodule demo/missing)",
                "(import demo/left :as left :only (absent))",
            ),
            source_path="demo/missing.orc",
        )
    )
    missing_module = WorkflowLispModule(
        language_version=missing_syntax.language_version,
        target_dsl_version=missing_syntax.target_dsl_version,
        module_name=missing_syntax.module_name,
        imports=missing_syntax.imports,
        exports=(),
        definitions=(),
        schemas=(),
        span=missing_syntax.span,
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_import_scope(
            missing_module,
            export_surfaces_by_name=surfaces,
        )
    assert _diagnostic_code(excinfo) == "module_export_missing"


def test_stage3_catalog_resolves_exported_prompt_imports(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    helper_path = source_root / "demo" / "helper.orc"
    helper_path.parent.mkdir(parents=True)
    helper_path.write_text(
        _module_source(
            "2.20",
            "(defmodule demo/helper)",
            "(export review)",
            '(defprompt review (:fills (message :text)) "Review {message}")',
        ),
        encoding="utf-8",
    )
    entry_path = source_root / "demo" / "entry.orc"
    entry_path.write_text(
        _module_source(
            "2.20",
            "(defmodule demo/entry)",
            "(import demo/helper :as helper :only (review))",
        ),
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        entry_path,
        source_roots=(source_root,),
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )

    prompt_catalog = result.entry_result.prompt_catalog
    assert prompt_catalog is not None
    assert prompt_catalog.resolve("review").qualified_name == "demo/helper::review"
    assert prompt_catalog.resolve("helper.review").qualified_name == "demo/helper::review"


@pytest.mark.parametrize("lowering_route", ("legacy", "wcc_m4"))
@pytest.mark.parametrize("linked", (False, True))
def test_real_stage3_prompt_application_reaches_typed_frontend_before_lowering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lowering_route: str,
    linked: bool,
) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    if linked:
        prompt_path = source_root / "demo" / "prompts.orc"
        prompt_path.parent.mkdir(parents=True)
        prompt_path.write_text(
            _module_source(
                "2.20",
                "(defmodule demo/prompts)",
                "(export review)",
                '(defprompt review (:fills (message :text)) -> Bool "Review {message}")',
            ),
            encoding="utf-8",
        )
        entry_path = source_root / "demo" / "entry.orc"
        entry_path.write_text(
            _module_source(
                "2.20",
                "(defmodule demo/entry)",
                "(import demo/prompts :as prompts :only (review))",
                """
                (defworkflow run-review
                  ((message String))
                  -> Bool
                  (provider-result providers.review
                    :prompt (review :message message)))
                """,
            ),
            encoding="utf-8",
        )
    else:
        entry_path = source_root / "prompt_frontend.orc"
        entry_path.write_text(
            _module_source(
                "2.20",
                '(defprompt review (:fills (message :text)) -> Bool "Review {message}")',
                """
                (defworkflow run-review
                  ((message String))
                  -> Bool
                  (provider-result providers.review
                    :prompt (review :message message)))
                """,
            ),
            encoding="utf-8",
        )

    class TypedFrontendReached(Exception):
        pass

    def capture_typed_frontend(**kwargs):
        typed_workflows = kwargs["typed_workflows"]
        if not typed_workflows:
            return ()
        typed_body = typed_workflows[0].typed_body
        assert typed_body.type_ref == PrimitiveTypeRef(name="Bool")
        assert isinstance(typed_body.expr, ProviderResultExpr)
        assert isinstance(typed_body.expr.prompt, PromptApplicationExpr)
        assert (
            typed_body.expr.prompt.compiled_prompt_fragment_identity
            is not None
        )
        raise TypedFrontendReached

    monkeypatch.setattr(
        workflow_lisp_compiler,
        "_lower_workflows_for_route",
        capture_typed_frontend,
    )
    with pytest.raises(TypedFrontendReached):
        if linked:
            compile_stage3_entrypoint(
                entry_path,
                source_roots=(source_root,),
                provider_externs={"providers.review": "test-provider"},
                validate_shared=False,
                workspace_root=tmp_path,
                lowering_route=lowering_route,
            )
        else:
            workflow_lisp.compile_stage3_module(
                entry_path,
                provider_externs={"providers.review": "test-provider"},
                validate_shared=False,
                workspace_root=tmp_path,
                lowering_route=lowering_route,
            )


def test_provider_prompt_application_is_fully_applied_and_prompt_owned() -> None:
    catalog = _catalog(
        """
        (defprompt review
          (:fills (message :text) (payload :value))
          -> (result Bool :description "Approve only complete work.")
          "Review {message}: {payload}")
        """
    )
    expr = _elaborate_provider(
        """
        (provider-result providers.review
          :prompt (review :payload payload :message message))
        """,
        catalog=catalog,
        bound_names=frozenset({"providers.review", "message", "payload"}),
    )
    assert isinstance(expr, ProviderResultExpr)
    assert isinstance(expr.prompt, PromptApplicationExpr)
    assert tuple(fill.name for fill in expr.prompt.fills) == ("message", "payload")
    assert expr.return_spec.type_name == "Bool"
    assert expr.inputs == ()
    assert expr.prompt_dependencies is None

    typed = typecheck_expression(
        expr,
        type_env=_empty_type_env(),
        value_env={
            "providers.review": PrimitiveTypeRef(name="Provider"),
            "message": PrimitiveTypeRef(name="String"),
            "payload": PrimitiveTypeRef(name="Json"),
        },
        extern_environment=ExternEnvironment(
            bindings_by_name={
                "providers.review": ProviderExtern(
                    name="providers.review",
                    provider_id="test-provider",
                )
            }
        ),
        prompt_catalog=catalog,
    )
    assert typed.type_ref == PrimitiveTypeRef(name="Bool")
    typed_prompt = typed.expr.prompt
    assert isinstance(typed_prompt, PromptApplicationExpr)
    assert typed_prompt.compiled_prompt_fragment_identity.startswith("sha256:")
    validate_compiled_prompt_fragment_identity(
        typed_prompt.compiled_prompt_fragment_identity,
        canonical_projection=typed_prompt.canonical_identity_projection,
    )


def test_prompt_application_requires_target_dsl_2_20() -> None:
    catalog = _catalog(
        '(defprompt review (:fills (message :text)) "Review {message}")'
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_provider(
            "(provider-result providers.review :prompt (review :message message))",
            catalog=catalog,
            bound_names=frozenset({"providers.review", "message"}),
            target_dsl="2.19",
        )

    assert _diagnostic_code(excinfo) == "prompt_calculus_requires_dsl_2_20"


def test_fragment_provider_result_uses_exact_default_value_type() -> None:
    catalog = _catalog(
        '(defprompt review (:fills (message :text)) "Review {message}")'
    )
    expr = _elaborate_provider(
        "(provider-result providers.review :prompt (review :message message))",
        catalog=catalog,
        bound_names=frozenset({"providers.review", "message"}),
    )

    typed = typecheck_expression(
        expr,
        type_env=_empty_type_env(),
        value_env={
            "providers.review": PrimitiveTypeRef(name="Provider"),
            "message": PrimitiveTypeRef(name="String"),
        },
        extern_environment=ExternEnvironment(
            bindings_by_name={
                "providers.review": ProviderExtern(
                    name="providers.review",
                    provider_id="test-provider",
                )
            }
        ),
        prompt_catalog=catalog,
    )

    assert typed.type_ref == PrimitiveTypeRef(name="Value")


@pytest.mark.parametrize(
    ("application", "code"),
    (
        (
            "(provider-result providers.review :prompt (review :message m :message m))",
            "prompt_fill_duplicate",
        ),
        (
            "(provider-result providers.review :prompt (review :unknown m :message m))",
            "prompt_fill_unknown",
        ),
        (
            "(provider-result providers.review :prompt (review))",
            "prompt_slot_undischarged",
        ),
        (
            "(provider-result providers.review :prompt (review :message m) :inputs (m))",
            "prompt_inputs_redeclaration_forbidden",
        ),
        (
            "(provider-result providers.review :prompt (review :message m) :prompt-dependencies (:required (m)))",
            "prompt_dependency_redeclaration_forbidden",
        ),
    ),
)
def test_prompt_application_closed_fill_and_redeclaration_refusals(
    application: str,
    code: str,
) -> None:
    catalog = _catalog(
        '(defprompt review (:fills (message :text)) "Review {message}")'
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_provider(
            application,
            catalog=catalog,
            bound_names=frozenset({"providers.review", "m"}),
        )
    assert _diagnostic_code(excinfo) == code


def test_prompt_output_position_missing_fill_and_caller_override_keep_q1_codes() -> None:
    catalog = _catalog(
        '(defprompt review (:fills (report :path :out)) "{report}")',
        target_dsl="2.21",
    )
    declaration = catalog.resolve("review").slots[0].declaration
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_provider(
            "(provider-result providers.review :prompt (review))",
            catalog=catalog,
            bound_names=frozenset({"providers.review"}),
            target_dsl="2.21",
        )
    missing = excinfo.value.diagnostics[0]
    assert missing.code == "prompt_slot_undischarged"
    assert missing.span.start.path == "inline_prompt_wrapper.orc"
    assert missing.notes == (_related_source_note(declaration.span),)

    override_application = """
        (provider-result providers.review
          :prompt (review :report report :out true))
        """
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_provider(
            override_application,
            catalog=catalog,
            bound_names=frozenset({"providers.review", "report"}),
            target_dsl="2.21",
        )
    override = excinfo.value.diagnostics[0]
    assert override.code == "prompt_fill_unknown"
    assert override.span.start.path == "inline_prompt_wrapper.orc"
    assert _source_owned_text(
        _provider_wrapper_source(
            override_application,
            target_dsl="2.21",
        ),
        override.span,
    ) == ":out"


_OUTPUT_POSITION_APPLICATION = """
        (provider-result providers.review
          :prompt (review :report report))
        """


def _typecheck_output_position(
    *,
    declaration: str,
    fill_type,
):
    type_env = _output_position_type_env()
    catalog = _catalog(
        declaration,
        target_dsl="2.21",
        type_env=type_env,
    )
    expr = _elaborate_provider(
        _OUTPUT_POSITION_APPLICATION,
        catalog=catalog,
        bound_names=frozenset({"providers.review", "report"}),
        target_dsl="2.21",
    )
    return typecheck_expression(
        expr,
        type_env=type_env,
        value_env={
            "providers.review": PrimitiveTypeRef(name="Provider"),
            "report": fill_type,
        },
        extern_environment=ExternEnvironment(
            bindings_by_name={
                "providers.review": ProviderExtern(
                    name="providers.review",
                    provider_id="test-provider",
                )
            }
        ),
        prompt_catalog=catalog,
    )


def test_prompt_output_position_fill_compatibility_follows_q1_type_checks() -> None:
    source_span = syntax.build_syntax_module(
        read_sexpr_text(
            _module_source("2.21"),
            source_path="output_fill_types.orc",
        )
    ).span
    output_path = PathTypeRef(
        name="ReportPath",
        definition=PathDef(
            name="ReportPath",
            kind="relpath",
            under="artifacts/reports",
            must_exist=False,
            span=source_span,
        ),
    )
    existing_path = PathTypeRef(
        name="ExistingReportPath",
        definition=PathDef(
            name="ExistingReportPath",
            kind="relpath",
            under="artifacts/reports",
            must_exist=True,
            span=source_span,
        ),
    )

    typed = _typecheck_output_position(
        declaration='(defprompt review (:fills (report :path :out ReportPath)) "{report}")',
        fill_type=output_path,
    )
    assert typed.expr.prompt.fills[0].renderer_id == "posix-path-line"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_output_position(
            declaration='(defprompt review (:fills (report :path :out)) "{report}")',
            fill_type=existing_path,
        )
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "prompt_output_position_fill_invalid"
    assert diagnostic.span.start.path == "inline_prompt_wrapper.orc"
    assert _source_owned_text(
        _provider_wrapper_source(
            _OUTPUT_POSITION_APPLICATION,
            target_dsl="2.21",
        ),
        diagnostic.span,
    ) == "report"
    assert diagnostic.notes == (
        _related_source_note(
            _catalog(
                '(defprompt review (:fills (report :path :out)) "{report}")',
                target_dsl="2.21",
            ).resolve("review").slots[0].declaration.span
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_output_position(
            declaration='(defprompt review (:fills (report :path :out ReportPath)) "{report}")',
            fill_type=existing_path,
        )
    assert _diagnostic_code(excinfo) == "prompt_slot_type_mismatch"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_output_position(
            declaration='(defprompt review (:fills (report :path :out)) "{report}")',
            fill_type=PrimitiveTypeRef(name="String"),
        )
    assert _diagnostic_code(excinfo) == "prompt_fill_renderer_unsupported"


def test_prompt_application_fill_name_errors_precede_redeclaration_errors() -> None:
    catalog = _catalog(
        '(defprompt review (:fills (message :text)) "Review {message}")'
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_provider(
            """
            (provider-result providers.review
              :prompt (review :unknown m)
              :returns Bool)
            """,
            catalog=catalog,
            bound_names=frozenset({"providers.review", "m"}),
        )
    assert _diagnostic_code(excinfo) == "prompt_fill_unknown"


def test_prompt_fill_type_errors_precede_return_redeclaration() -> None:
    catalog = _catalog(
        '(defprompt review (:fills (message :text)) "Review {message}")'
    )
    expr = _elaborate_provider(
        """
        (provider-result providers.review
          :prompt (review :message m)
          :returns Bool)
        """,
        catalog=catalog,
        bound_names=frozenset({"providers.review", "m"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_empty_type_env(),
            value_env={
                "providers.review": PrimitiveTypeRef(name="Provider"),
                "m": PrimitiveTypeRef(name="Int"),
            },
            extern_environment=ExternEnvironment(
                bindings_by_name={
                    "providers.review": ProviderExtern(
                        name="providers.review",
                        provider_id="test-provider",
                    )
                }
            ),
            prompt_catalog=catalog,
        )

    assert _diagnostic_code(excinfo) == "prompt_slot_type_mismatch"


def test_prompt_return_redeclaration_is_rejected_after_valid_fills() -> None:
    catalog = _catalog(
        '(defprompt review (:fills (message :text)) "Review {message}")'
    )
    expr = _elaborate_provider(
        """
        (provider-result providers.review
          :prompt (review :message m)
          :returns Bool)
        """,
        catalog=catalog,
        bound_names=frozenset({"providers.review", "m"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_empty_type_env(),
            value_env={
                "providers.review": PrimitiveTypeRef(name="Provider"),
                "m": PrimitiveTypeRef(name="String"),
            },
            extern_environment=ExternEnvironment(
                bindings_by_name={
                    "providers.review": ProviderExtern(
                        name="providers.review",
                        provider_id="test-provider",
                    )
                }
            ),
            prompt_catalog=catalog,
        )

    assert _diagnostic_code(excinfo) == "prompt_return_redeclaration_forbidden"


def test_prompt_name_coexists_with_lexical_procedure_and_proc_ref(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    entry_path = source_root / "demo" / "coexist.orc"
    entry_path.parent.mkdir(parents=True)
    entry_path.write_text(
        _module_source(
            "2.20",
            "(defmodule demo/coexist)",
            '(defprompt review (:fills (message :text)) "Review {message}")',
            """
            (defproc apply-runner
              ((runner ProcRef[String -> String]) (value String))
              -> String
              :effects ()
              :lowering inline
              (runner value))
            """,
            """
            (defproc review
              ((value String))
              -> String
              :effects ()
              :lowering inline
              value)
            """,
            """
            (defproc coexist
              ((review String))
              -> String
              :effects ()
              :lowering inline
              (let* ((from-call (review review))
                     (from-ref
                       (apply-runner (proc-ref review) from-call)))
                from-ref))
            """,
        ),
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        entry_path,
        source_roots=(source_root,),
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )

    assert {
        "demo/coexist::apply-runner",
        "demo/coexist::review",
        "demo/coexist::coexist",
    }.issubset({
        procedure.definition.name
        for procedure in result.entry_result.typed_procedures
    })


@pytest.mark.parametrize("prompt_operand", ("review", "(proc-ref review)"))
def test_prompt_value_or_proc_ref_attempt_is_rejected_in_prompt_position(
    prompt_operand: str,
) -> None:
    catalog = _catalog(
        '(defprompt review (:fills (message :text)) "Review {message}")'
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_provider(
            f"""
            (provider-result providers.review
              :prompt {prompt_operand}
              :inputs ()
              :returns Value)
            """,
            catalog=catalog,
            bound_names=frozenset({"providers.review"}),
        )
    assert _diagnostic_code(excinfo) == "prompt_partial_application_unsupported"


def test_nested_prompt_application_is_not_an_admitted_fill_identity() -> None:
    catalog = _catalog(
        '(defprompt inner (:fills (message :text)) "Inner {message}")',
        '(defprompt outer (:fills (payload :value)) "Outer {payload}")',
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_provider(
            """
            (provider-result providers.review
              :prompt (outer :payload (inner :message m)))
            """,
            catalog=catalog,
            bound_names=frozenset({"providers.review", "m"}),
        )
    assert _diagnostic_code(excinfo) == "prompt_fill_identity_unsupported"


@pytest.mark.parametrize(
    ("slot_kind", "value_type", "code"),
    (
        ("text", PrimitiveTypeRef(name="Int"), "prompt_slot_type_mismatch"),
        (
            "value",
            OptionalTypeRef(name="Optional[String]", item_type_ref=PrimitiveTypeRef(name="String")),
            "prompt_fill_renderer_unsupported",
        ),
        (
            "value",
            MapTypeRef(
                name="Map[String, String]",
                key_type_ref=PrimitiveTypeRef(name="String"),
                value_type_ref=PrimitiveTypeRef(name="String"),
            ),
            "prompt_fill_renderer_unsupported",
        ),
    ),
)
def test_prompt_fill_type_and_renderer_refusals(
    slot_kind: str,
    value_type,
    code: str,
) -> None:
    catalog = _catalog(
        f'(defprompt review (:fills (message :{slot_kind})) "Review {{message}}")'
    )
    expr = _elaborate_provider(
        "(provider-result providers.review :prompt (review :message m))",
        catalog=catalog,
        bound_names=frozenset({"providers.review", "m"}),
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_empty_type_env(),
            value_env={
                "providers.review": PrimitiveTypeRef(name="Provider"),
                "m": value_type,
            },
            extern_environment=ExternEnvironment(
                bindings_by_name={
                    "providers.review": ProviderExtern(
                        name="providers.review",
                        provider_id="test-provider",
                    )
                }
            ),
            prompt_catalog=catalog,
        )
    assert _diagnostic_code(excinfo) == code


def test_prompt_slot_refinements_only_narrow_admitted_renderer_types() -> None:
    catalog = _catalog(
        '(defprompt review (:fills (payload :value String)) "Review {payload}")'
    )
    expr = _elaborate_provider(
        "(provider-result providers.review :prompt (review :payload payload))",
        catalog=catalog,
        bound_names=frozenset({"providers.review", "payload"}),
    )
    externs = ExternEnvironment(
        bindings_by_name={
            "providers.review": ProviderExtern(
                name="providers.review",
                provider_id="test-provider",
            )
        }
    )
    typed = typecheck_expression(
        expr,
        type_env=_empty_type_env(),
        value_env={
            "providers.review": PrimitiveTypeRef(name="Provider"),
            "payload": PrimitiveTypeRef(name="String"),
        },
        extern_environment=externs,
        prompt_catalog=catalog,
    )
    assert typed.expr.prompt.fills[0].renderer_id == "canonical-json"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_empty_type_env(),
            value_env={
                "providers.review": PrimitiveTypeRef(name="Provider"),
                "payload": PrimitiveTypeRef(name="Int"),
            },
            extern_environment=externs,
            prompt_catalog=catalog,
        )
    assert _diagnostic_code(excinfo) == "prompt_slot_type_mismatch"


def test_prompt_doc_and_path_kinds_use_their_closed_path_contracts() -> None:
    catalog = _catalog(
        """
        (defprompt review
          (:fills (document :doc) (report :path))
          "Write the review to {report}")
        """
    )
    expr = _elaborate_provider(
        """
        (provider-result providers.review
          :prompt (review :document document :report report))
        """,
        catalog=catalog,
        bound_names=frozenset(
            {"providers.review", "document", "report"}
        ),
    )
    existing_relpath = PathTypeRef(
        name="ExistingDocPath",
        definition=PathDef(
            name="ExistingDocPath",
            kind="relpath",
            under=".",
            must_exist=True,
            span=expr.span,
        ),
    )
    output_path = PathTypeRef(
        name="ReportPath",
        definition=PathDef(
            name="ReportPath",
            kind="relpath",
            under="artifacts",
            must_exist=False,
            span=expr.span,
        ),
    )
    externs = ExternEnvironment(
        bindings_by_name={
            "providers.review": ProviderExtern(
                name="providers.review",
                provider_id="test-provider",
            )
        }
    )
    typed = typecheck_expression(
        expr,
        type_env=_empty_type_env(),
        value_env={
            "providers.review": PrimitiveTypeRef(name="Provider"),
            "document": existing_relpath,
            "report": output_path,
        },
        extern_environment=externs,
        prompt_catalog=catalog,
    )
    assert tuple(
        fill.renderer_id for fill in typed.expr.prompt.fills
    ) == ("required-document", "posix-path-line")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_empty_type_env(),
            value_env={
                "providers.review": PrimitiveTypeRef(name="Provider"),
                "document": output_path,
                "report": output_path,
            },
            extern_environment=externs,
            prompt_catalog=catalog,
        )
    assert _diagnostic_code(excinfo) == "prompt_slot_type_mismatch"


def test_closed_fill_identity_accepts_literal_name_and_field_path_but_not_call() -> None:
    catalog = _catalog(
        '(defprompt review (:fills (message :text)) "Review {message}")'
    )
    for fill in ('"literal"', "message", "request.message"):
        expr = _elaborate_provider(
            f"(provider-result providers.review :prompt (review :message {fill}))",
            catalog=catalog,
            bound_names=frozenset({"providers.review", "message", "request"}),
        )
        value_env = {
            "providers.review": PrimitiveTypeRef(name="Provider"),
            "message": PrimitiveTypeRef(name="String"),
        }
        if fill == "request.message":
            request_type = workflow_lisp.RecordTypeRef(
                name="Request",
                    definition=workflow_lisp.RecordDef(
                        name="Request",
                        fields=(
                            RecordField(
                                name="message",
                                type_name="String",
                                span=expr.span,
                            ),
                        ),
                    span=expr.span,
                ),
                field_types={"message": PrimitiveTypeRef(name="String")},
            )
            value_env["request"] = request_type
        typed = typecheck_expression(
            expr,
            type_env=_empty_type_env(),
            value_env=value_env,
            extern_environment=ExternEnvironment(
                bindings_by_name={
                    "providers.review": ProviderExtern(
                        name="providers.review",
                        provider_id="test-provider",
                    )
                }
            ),
            prompt_catalog=catalog,
        )
        assert typed.expr.prompt.compiled_prompt_fragment_identity.startswith("sha256:")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            _elaborate_provider(
                """
                (provider-result providers.review
                  :prompt (review :message (if true "a" "b")))
                """,
                catalog=catalog,
                bound_names=frozenset({"providers.review"}),
            ),
            type_env=_empty_type_env(),
            value_env={"providers.review": PrimitiveTypeRef(name="Provider")},
            extern_environment=ExternEnvironment(
                bindings_by_name={
                    "providers.review": ProviderExtern(
                        name="providers.review",
                        provider_id="test-provider",
                    )
                }
            ),
            prompt_catalog=catalog,
        )
    assert _diagnostic_code(excinfo) == "prompt_fill_identity_unsupported"


def test_compiled_prompt_identity_is_order_stable_and_change_sensitive() -> None:
    catalog = _catalog(
        '(defprompt review (:fills (left :text) (right :value)) "{left} {right}")'
    )

    def compile_identity(prompt_use: str) -> str:
        expr = _elaborate_provider(
            f"(provider-result providers.review :prompt {prompt_use})",
            catalog=catalog,
            bound_names=frozenset({"providers.review", "left", "right", "other"}),
        )
        typed = typecheck_expression(
            expr,
            type_env=_empty_type_env(),
            value_env={
                "providers.review": PrimitiveTypeRef(name="Provider"),
                "left": PrimitiveTypeRef(name="String"),
                "right": PrimitiveTypeRef(name="Int"),
                "other": PrimitiveTypeRef(name="Int"),
            },
            extern_environment=ExternEnvironment(
                bindings_by_name={
                    "providers.review": ProviderExtern(
                        name="providers.review",
                        provider_id="test-provider",
                    )
                }
            ),
            prompt_catalog=catalog,
        )
        return typed.expr.prompt.compiled_prompt_fragment_identity

    ordered = compile_identity("(review :left left :right right)")
    reordered = compile_identity("(review :right right :left left)")
    changed = compile_identity("(review :left left :right other)")
    assert ordered == reordered
    assert ordered != changed

    with pytest.raises(LispFrontendCompileError) as excinfo:
        validate_compiled_prompt_fragment_identity("sha256:ABC")
    assert _diagnostic_code(excinfo) == "compiled_prompt_fragment_identity_invalid"


_FROZEN_Q1_IDENTITY_BYTES = (
    b'{"fully_applied_bindings":[{"slot":"left","typed_expression_identity":'
    b'{"binding_path":["left"],"kind":"binding_path","static_type":{"kind":'
    b'"primitive","name":"String"}}},{"slot":"right","typed_expression_identity":'
    b'{"binding_path":["right"],"kind":"binding_path","static_type":{"kind":'
    b'"primitive","name":"Int"}}}],"referenced_declarations":[{"qualified_name":'
    b'"demo/prompts::review","return_spec":{"guidance":null,"type":{"kind":'
    b'"primitive","name":"Value"}},"slots":[{"kind":"text","name":"left",'
    b'"placeholder_policy":"required_repetition_allowed","refinement":null},'
    b'{"kind":"value","name":"right","placeholder_policy":'
    b'"required_repetition_allowed","refinement":null}],"template_utf8":'
    b'"{left} {right}"}],"schema_version":"compiled_prompt_fragment_identity.v1"}'
)
_FROZEN_Q1_IDENTITY = (
    "sha256:7f2688f6efd63e0bdf0d492f006086a4437dc5eb79893c3e78a37001704b132c"
)
_FROZEN_Q1_CARRIER_JSON = (
    '{"compiled_prompt_fragment_identity":"sha256:'
    'dd1b2a5365b0091c1012ecd5d768910f2fbf1a8c219d70fd46c92e0f5833014b",'
    '"rendered_slots":[{"kind":"text","name":"message",'
    '"placeholder_ordinals":[0,3],"renderer_id":"raw-utf8-string",'
    '"static_type":{"kind":"primitive","name":"String"},'
    '"value_source":{"binding":{"ref":"inputs.message"},'
    '"kind":"typed_binding_ref"}},{"kind":"value","name":"score",'
    '"placeholder_ordinals":[1],"renderer_id":"canonical-json",'
    '"static_type":{"kind":"primitive","name":"Int"},'
    '"value_source":{"binding":{"ref":"inputs.score"},'
    '"kind":"typed_binding_ref"}},{"kind":"path","name":"report_path",'
    '"placeholder_ordinals":[2],"renderer_id":"posix-path-line",'
    '"static_type":{"kind":"path","must_exist_target":false,'
    '"name":"WorkReportPath","under":"artifacts/work"},'
    '"value_source":{"binding":{"ref":"inputs.report_path"},'
    '"kind":"typed_binding_ref"}}],"schema_version":'
    '"compiler_prompt_fragment_contract.v1","template_utf8":'
    '"Message={message}; score={score}; report={report_path}; again={message}"}'
)


def _compile_q1_identity_at_target(target_dsl: str):
    catalog = _catalog(
        '(defprompt review (:fills (left :text) (right :value)) "{left} {right}")',
        target_dsl=target_dsl,
    )
    expr = _elaborate_provider(
        """
        (provider-result providers.review
          :prompt (review :left left :right right))
        """,
        catalog=catalog,
        bound_names=frozenset({"providers.review", "left", "right"}),
        target_dsl=target_dsl,
    )
    return typecheck_expression(
        expr,
        type_env=_empty_type_env(target_dsl=target_dsl),
        value_env={
            "providers.review": PrimitiveTypeRef(name="Provider"),
            "left": PrimitiveTypeRef(name="String"),
            "right": PrimitiveTypeRef(name="Int"),
        },
        extern_environment=ExternEnvironment(
            bindings_by_name={
                "providers.review": ProviderExtern(
                    name="providers.review",
                    provider_id="test-provider",
                )
            }
        ),
        prompt_catalog=catalog,
    ).expr.prompt


def test_q1_prompt_fragment_identity_and_carrier_bytes_are_frozen_across_target_2_21(
    tmp_path: Path,
) -> None:
    prompt_220 = _compile_q1_identity_at_target("2.20")
    prompt_221 = _compile_q1_identity_at_target("2.21")
    projection_bytes_220 = json.dumps(
        prompt_220.canonical_identity_projection,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    projection_bytes_221 = json.dumps(
        prompt_221.canonical_identity_projection,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    assert projection_bytes_220 == _FROZEN_Q1_IDENTITY_BYTES
    assert projection_bytes_221 == _FROZEN_Q1_IDENTITY_BYTES
    assert prompt_220.compiled_prompt_fragment_identity == _FROZEN_Q1_IDENTITY
    assert prompt_221.compiled_prompt_fragment_identity == _FROZEN_Q1_IDENTITY

    carrier_jsons = []
    for target_dsl in ("2.20", "2.21"):
        result = _compile_fragment_workflow(
            tmp_path,
            lowering_route="legacy",
            target_dsl=target_dsl,
        )
        bundle = result.validated_bundles["run-review"]
        provider_step = next(
            step
            for step in bundle.surface.steps
            if step.kind.value == "provider"
        )
        carrier_jsons.append(
            canonical_compiler_prompt_fragment_contract_json(
                provider_step.compiler_prompt_fragment_contract
            )
        )
    assert carrier_jsons == [
        _FROZEN_Q1_CARRIER_JSON,
        _FROZEN_Q1_CARRIER_JSON,
    ]


def test_q2_prompt_fragment_identity_adds_output_role_to_every_declaration_slot_only() -> None:
    type_env = _output_position_type_env()

    def compile_projection(*, output: bool):
        output_modifier = " :out" if output else ""
        catalog = _catalog(
            (
                "(defprompt review "
                "(:fills (message :text) "
                f"(report :path{output_modifier})) "
                '"{message} {report}")'
            ),
            target_dsl="2.21",
            type_env=type_env,
        )
        expr = _elaborate_provider(
            """
            (provider-result providers.review
              :prompt (review :message message :report report))
            """,
            catalog=catalog,
            bound_names=frozenset(
                {"providers.review", "message", "report"}
            ),
            target_dsl="2.21",
        )
        span = expr.span
        report_type = PathTypeRef(
            name="ReportPath",
            definition=PathDef(
                name="ReportPath",
                kind="relpath",
                under="artifacts/reports",
                must_exist=False,
                span=span,
            ),
        )
        typed = typecheck_expression(
            expr,
            type_env=type_env,
            value_env={
                "providers.review": PrimitiveTypeRef(name="Provider"),
                "message": PrimitiveTypeRef(name="String"),
                "report": report_type,
            },
            extern_environment=ExternEnvironment(
                bindings_by_name={
                    "providers.review": ProviderExtern(
                        name="providers.review",
                        provider_id="test-provider",
                    )
                }
            ),
            prompt_catalog=catalog,
        )
        return typed.expr.prompt.canonical_identity_projection

    v1 = compile_projection(output=False)
    v2 = compile_projection(output=True)
    assert v1["schema_version"] == "compiled_prompt_fragment_identity.v1"
    assert v2["schema_version"] == "compiled_prompt_fragment_identity.v2"
    assert [
        slot["output_role"]
        for slot in v2["referenced_declarations"][0]["slots"]
    ] == ["none", "required_string_file"]

    normalized_v2 = json.loads(json.dumps(v2))
    normalized_v2["schema_version"] = "compiled_prompt_fragment_identity.v1"
    for slot in normalized_v2["referenced_declarations"][0]["slots"]:
        del slot["output_role"]
    assert normalized_v2 == v1


@pytest.mark.parametrize("lowering_route", ("legacy", "wcc_m4"))
def test_fragment_application_lowers_through_both_routes_with_typed_carriers(
    tmp_path: Path,
    lowering_route: str,
) -> None:
    result = _compile_fragment_workflow(
        tmp_path,
        lowering_route=lowering_route,
    )
    bundle = result.validated_bundles["run-review"]
    provider_step = next(
        step
        for step in bundle.surface.steps
        if step.kind.value == "provider"
    )

    contract = provider_step.compiler_prompt_fragment_contract
    identity = provider_step.compiled_prompt_fragment_identity
    assert contract is not None
    assert identity is not None
    assert contract.compiled_prompt_fragment_identity == identity
    assert contract.template_utf8 == (
        "Message={message}; score={score}; report={report_path}; again={message}"
    )
    assert tuple(slot.name for slot in contract.rendered_slots) == (
        "message",
        "score",
        "report_path",
    )
    assert tuple(slot.kind for slot in contract.rendered_slots) == (
        "text",
        "value",
        "path",
    )
    assert tuple(slot.renderer_id for slot in contract.rendered_slots) == (
        "raw-utf8-string",
        "canonical-json",
        "posix-path-line",
    )
    assert tuple(slot.placeholder_ordinals for slot in contract.rendered_slots) == (
        (0, 3),
        (1,),
        (2,),
    )
    assert provider_step.depends_on == {
        "required": ("${inputs.target_doc}",),
        "optional": (),
        "inject": {
            "mode": "content",
            "position": "prepend",
        },
    }
    dependency_contract = provider_step.compiler_prompt_dependency_contract
    assert dependency_contract is not None
    assert dependency_contract.origin_kind.value == "workflow_lisp_prompt_fragment"
    assert dependency_contract.required_binding_refs == ("inputs.target_doc",)
    assert dependency_contract.optional_binding_refs == ()

    core_step = next(
        statement
        for statement in bundle.core_workflow_ast.body
        if statement.meta.step_kind == "provider"
    )
    assert core_step.compiler_prompt_fragment_contract == contract
    assert core_step.compiled_prompt_fragment_identity == identity
    executable_config = next(
        node.execution_config
        for node in bundle.ir.nodes.values()
        if getattr(node, "execution_config", None) is not None
        and hasattr(node.execution_config, "provider")
    )
    assert executable_config.compiler_prompt_fragment_contract == contract
    assert executable_config.compiled_prompt_fragment_identity == identity
    prompt_surface = next(
        iter(bundle.semantic_ir.prompt_surfaces.values())
    )
    assert prompt_surface.compiler_prompt_fragment_contract == contract
    assert prompt_surface.compiled_prompt_fragment_identity == identity
    (lineage,) = next(
        lowered.origin_map.prompt_dependency_lineages
        for lowered in result.lowered_workflows
        if lowered.typed_workflow.definition.name == "run-review"
    )
    assert provider_step.step_id.endswith(lineage.step_id)
    assert tuple(
        (row.role, row.authored_index, row.binding_ref)
        for row in lineage.rows
    ) == (("required", 0, "inputs.target_doc"),)
    assert lineage.position.value == "prepend"
    assert lineage.instruction is None


@pytest.mark.parametrize(
    ("descriptor", "renderer_id"),
    (
        ({"kind": "primitive", "name": "String"}, "raw-utf8-string"),
        ({"kind": "primitive", "name": "Int"}, "canonical-json"),
        ({"kind": "primitive", "name": "Float"}, "canonical-json"),
        ({"kind": "primitive", "name": "Bool"}, "canonical-json"),
        ({"kind": "primitive", "name": "Json"}, "canonical-json"),
        ({"kind": "primitive", "name": "Value"}, "canonical-json"),
        (
            {
                "kind": "enum",
                "name": "Decision",
                "allowed": ["APPROVE", "REJECT"],
            },
            "canonical-json",
        ),
        (
            {
                "kind": "path",
                "name": "ReportPath",
                "under": "artifacts/reports",
                "must_exist_target": False,
            },
            "posix-path-line",
        ),
        (
            {
                "kind": "record",
                "name": "Scorecard",
                "fields": [
                    {
                        "name": "score",
                        "type": {"kind": "primitive", "name": "Float"},
                    }
                ],
            },
            "canonical-json",
        ),
        (
            {
                "kind": "list",
                "item": {"kind": "primitive", "name": "Value"},
            },
            "canonical-json",
        ),
    ),
)
def test_fragment_static_types_use_shared_compiler_normalized_descriptor_owner(
    descriptor: dict[str, object],
    renderer_id: str,
) -> None:
    pure_projection_lowering.validate_compiler_normalized_type_descriptor(
        descriptor
    )
    slot = CompilerPromptFragmentRenderedSlot(
        name="value",
        kind=(
            "text"
            if renderer_id == "raw-utf8-string"
            else "path"
            if renderer_id == "posix-path-line"
            else "value"
        ),
        static_type=descriptor,
        renderer_id=renderer_id,
        value_source={
            "kind": "typed_binding_ref",
            "binding": {"ref": "inputs.value"},
        },
        placeholder_ordinals=(0,),
    )
    assert serialize_compiler_prompt_fragment_rendered_slot(slot)[
        "static_type"
    ] == descriptor


@pytest.mark.parametrize("lowering_route", ("legacy", "wcc_m4"))
def test_zero_document_fragment_lowers_validates_and_serializes_empty_dependencies(
    tmp_path: Path,
    lowering_route: str,
) -> None:
    result = _compile_zero_document_fragment_workflow(
        tmp_path,
        lowering_route=lowering_route,
    )
    bundle = result.validated_bundles["run-inspect"]
    surface = next(
        step for step in bundle.surface.steps if step.kind.value == "provider"
    )
    expected_depends_on = {
        "required": (),
        "optional": (),
        "inject": {"mode": "content", "position": "prepend"},
    }
    dependency_contract = surface.compiler_prompt_dependency_contract
    fragment_contract = surface.compiler_prompt_fragment_contract
    assert surface.depends_on == expected_depends_on
    assert dependency_contract is not None
    assert dependency_contract.origin_kind.value == "workflow_lisp_prompt_fragment"
    assert dependency_contract.required_binding_refs == ()
    assert dependency_contract.optional_binding_refs == ()
    assert fragment_contract is not None
    assert tuple(slot.name for slot in fragment_contract.rendered_slots) == (
        "message",
        "payload",
    )
    assert fragment_contract.rendered_slots[1].static_type == {
        "kind": "primitive",
        "name": "Value",
    }

    core = next(
        statement
        for statement in bundle.core_workflow_ast.body
        if statement.meta.step_kind == "provider"
    )
    executable = next(
        node.execution_config
        for node in bundle.ir.nodes.values()
        if getattr(node, "execution_config", None) is not None
        and hasattr(node.execution_config, "provider")
    )
    semantic = next(iter(bundle.semantic_ir.prompt_surfaces.values()))
    for carrier in (core, executable, semantic):
        assert carrier.compiler_prompt_dependency_contract == dependency_contract
        assert carrier.compiler_prompt_fragment_contract == fragment_contract
    assert core.depends_on == expected_depends_on
    assert executable.depends_on == expected_depends_on

    (lineage,) = next(
        lowered.origin_map.prompt_dependency_lineages
        for lowered in result.lowered_workflows
        if lowered.typed_workflow.definition.name == "run-inspect"
    )
    assert lineage.rows == ()
    assert lineage.position.value == "prepend"
    assert lineage.instruction is None

    expected_serialized_contract = (
        serialize_compiler_prompt_dependency_contract(dependency_contract)
    )

    def dependency_contract_rows(value):
        if isinstance(value, dict):
            rows = (
                [value["compiler_prompt_dependency_contract"]]
                if "compiler_prompt_dependency_contract" in value
                else []
            )
            return rows + [
                row
                for item in value.values()
                for row in dependency_contract_rows(item)
            ]
        if isinstance(value, list):
            return [
                row
                for item in value
                for row in dependency_contract_rows(item)
            ]
        return []

    for serialized_ir in (
        workflow_executable_ir_to_json(bundle.ir),
        workflow_semantic_ir_to_json(bundle.semantic_ir),
    ):
        assert dependency_contract_rows(serialized_ir) == [
            expected_serialized_contract
        ]


def test_fragment_carriers_fail_closed_on_missing_malformed_and_mismatched_identity(
    tmp_path: Path,
) -> None:
    result = _compile_fragment_workflow(tmp_path, lowering_route="legacy")
    bundle = result.validated_bundles["run-review"]
    surface = next(step for step in bundle.surface.steps if step.kind.value == "provider")
    core = next(
        statement
        for statement in bundle.core_workflow_ast.body
        if statement.meta.step_kind == "provider"
    )
    executable = next(
        node.execution_config
        for node in bundle.ir.nodes.values()
        if getattr(node, "execution_config", None) is not None
        and hasattr(node.execution_config, "provider")
    )
    semantic = next(iter(bundle.semantic_ir.prompt_surfaces.values()))

    for carrier in (surface, core, executable, semantic):
        with pytest.raises(
            ValueError,
            match="compiled_prompt_fragment_identity_missing",
        ):
            replace(carrier, compiled_prompt_fragment_identity=None)
        with pytest.raises(
            ValueError,
            match="compiled_prompt_fragment_identity_invalid",
        ):
            replace(carrier, compiled_prompt_fragment_identity="sha256:ABC")

        mismatched = replace(
            carrier.compiler_prompt_fragment_contract,
            compiled_prompt_fragment_identity=f"sha256:{'0' * 64}",
        )
        with pytest.raises(
            ValueError,
            match="compiled_prompt_fragment_identity_mismatch",
        ):
            replace(carrier, compiler_prompt_fragment_contract=mismatched)


def test_executable_fragment_validation_has_its_own_error_category(
    tmp_path: Path,
) -> None:
    result = _compile_fragment_workflow(tmp_path, lowering_route="legacy")
    bundle = result.validated_bundles["run-review"]
    provider_node = next(
        node
        for node in bundle.ir.nodes.values()
        if getattr(node, "execution_config", None) is not None
        and hasattr(node.execution_config, "provider")
    )
    invalid_config = replace(provider_node.execution_config)
    object.__setattr__(
        invalid_config,
        "compiled_prompt_fragment_identity",
        f"sha256:{'0' * 64}",
    )
    invalid_node = replace(
        provider_node,
        execution_config=invalid_config,
    )
    invalid_ir = replace(
        bundle.ir,
        nodes={
            **bundle.ir.nodes,
            invalid_node.node_id: invalid_node,
        },
    )

    with pytest.raises(
        WorkflowValidationError,
        match="provider prompt fragment contract is invalid",
    ):
        validate_executable_workflow(invalid_ir)


def test_fragment_contract_serialization_is_closed_and_route_deterministic(
    tmp_path: Path,
) -> None:
    first = _compile_fragment_workflow(tmp_path, lowering_route="legacy")
    second = _compile_fragment_workflow(tmp_path, lowering_route="wcc_m4")
    first_step = next(
        step
        for step in first.validated_bundles["run-review"].surface.steps
        if step.kind.value == "provider"
    )
    second_step = next(
        step
        for step in second.validated_bundles["run-review"].surface.steps
        if step.kind.value == "provider"
    )

    assert canonical_compiler_prompt_fragment_contract_json(
        first_step.compiler_prompt_fragment_contract
    ) == canonical_compiler_prompt_fragment_contract_json(
        second_step.compiler_prompt_fragment_contract
    )
    assert (
        first_step.compiled_prompt_fragment_identity
        == second_step.compiled_prompt_fragment_identity
    )
    assert first_step.common.output_bundle == second_step.common.output_bundle
    assert first_step.common.output_bundle["fields"][0]["type"] == "bool"
    assert first_step.common.output_bundle["fields"][0]["json_pointer"] == ""
    expected_typed_prompt_inputs = (
        {
            "schema_version": "workflow_lisp_typed_prompt_input.v1",
            "binding_name": "score",
            "renderer": {
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "accepted_shape": "any_pure_value",
            },
            "value_source": {
                "kind": "typed_binding_ref",
                "binding": {"ref": "inputs.score"},
            },
            "value_type_name": "Int",
            "source_map_origin_key": "run-review",
            "injection_order": 0,
        },
        {
            "schema_version": "workflow_lisp_typed_prompt_input.v1",
            "binding_name": "report_path",
            "renderer": {
                "renderer_id": "posix-path-line",
                "renderer_version": 1,
                "accepted_shape": "path_value",
            },
            "value_source": {
                "kind": "typed_binding_ref",
                "binding": {"ref": "inputs.report_path"},
            },
            "value_type_name": "WorkReportPath",
            "source_map_origin_key": "run-review",
            "injection_order": 1,
        },
    )
    assert first_step.typed_prompt_inputs == second_step.typed_prompt_inputs
    assert first_step.typed_prompt_inputs == expected_typed_prompt_inputs
    assert second_step.typed_prompt_inputs == expected_typed_prompt_inputs

    rendered_by_name = {
        slot.name: slot
        for slot in first_step.compiler_prompt_fragment_contract.rendered_slots
    }
    assert {
        name: slot.value_source
        for name, slot in rendered_by_name.items()
    } == {
        "message": {
            "kind": "typed_binding_ref",
            "binding": {"ref": "inputs.message"},
        },
        "score": {
            "kind": "typed_binding_ref",
            "binding": {"ref": "inputs.score"},
        },
        "report_path": {
            "kind": "typed_binding_ref",
            "binding": {"ref": "inputs.report_path"},
        },
    }
    assert tuple(
        entry["binding_name"]
        for entry in first_step.typed_prompt_inputs
    ) == ("score", "report_path")
    assert {
        entry["binding_name"]: entry["value_source"]
        for entry in first_step.typed_prompt_inputs
    } == {
        name: rendered_by_name[name].value_source
        for name in ("score", "report_path")
    }


def test_fragment_rendered_slot_deeply_freezes_constructor_inputs() -> None:
    static_type = {
        "kind": "list",
        "item": {"kind": "primitive", "name": "Int"},
    }
    value_source = {
        "kind": "typed_binding_ref",
        "binding": {"ref": "inputs.values"},
    }
    slot = CompilerPromptFragmentRenderedSlot(
        name="values",
        kind="value",
        static_type=static_type,
        renderer_id="canonical-json",
        value_source=value_source,
        placeholder_ordinals=(0,),
    )
    contract = CompilerPromptFragmentContract(
        schema_version=COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
        template_utf8="{values}",
        rendered_slots=(slot,),
        compiled_prompt_fragment_identity=f"sha256:{'1' * 64}",
    )
    before = canonical_compiler_prompt_fragment_contract_json(contract)

    static_type["item"]["name"] = "String"
    value_source["binding"]["ref"] = "inputs.changed"

    assert canonical_compiler_prompt_fragment_contract_json(contract) == before
    assert slot.static_type["item"]["name"] == "Int"
    assert slot.value_source["binding"]["ref"] == "inputs.values"
    with pytest.raises(TypeError):
        slot.static_type["item"]["name"] = "String"
    with pytest.raises(TypeError):
        slot.value_source["binding"]["ref"] = "inputs.changed"


@pytest.mark.parametrize(
    ("static_type", "value_source"),
    (
        (
            {"kind": "primitive", "name": "Int", "extra": True},
            {"kind": "typed_binding_ref", "binding": {"ref": "inputs.value"}},
        ),
        (
            {"kind": "list", "item": {"kind": "primitive", "name": "Int", "extra": True}},
            {"kind": "typed_binding_ref", "binding": {"ref": "inputs.value"}},
        ),
        (
            {"kind": "primitive", "name": "Int"},
            {
                "kind": "typed_binding_ref",
                "binding": {"ref": "inputs.value"},
                "extra": True,
            },
        ),
        (
            {"kind": "primitive", "name": "Int"},
            {
                "kind": "typed_binding_ref",
                "binding": {"ref": "inputs.value", "extra": True},
            },
        ),
        (
            {"kind": "primitive", "name": "Int"},
            {"kind": "other", "binding": {"ref": "inputs.value"}},
        ),
        (
            {"kind": "primitive", "name": "Int"},
            {"kind": "typed_binding_ref", "binding": {"ref": ""}},
        ),
    ),
)
def test_fragment_rendered_slot_rejects_open_or_invalid_nested_schemas(
    static_type: dict[str, object],
    value_source: dict[str, object],
) -> None:
    with pytest.raises(
        (TypeError, ValueError),
        match="compiler_prompt_fragment_contract_invalid",
    ):
        CompilerPromptFragmentRenderedSlot(
            name="value",
            kind="value",
            static_type=static_type,
            renderer_id="canonical-json",
            value_source=value_source,
            placeholder_ordinals=(0,),
        )


@pytest.mark.parametrize("lowering_route", ("legacy", "wcc_m4"))
def test_extern_prompt_build_artifacts_are_byte_neutral_at_target_2_20(
    tmp_path: Path,
    lowering_route: str,
) -> None:
    source_path = tmp_path / "extern_prompt.orc"

    def build_payload_bytes(target_dsl: str) -> tuple[bytes, bytes, bytes]:
        source_path.write_text(
            _module_source(
                target_dsl,
                """
                (defworkflow run-extern ((message String)) -> Bool
                  (provider-result providers.review
                    :prompt prompts.review
                    :inputs (message)
                    :returns Bool))
                """,
            )
            + "\n",
            encoding="utf-8",
        )
        result = workflow_lisp.compile_stage3_module(
            source_path,
            provider_externs={"providers.review": "test-provider"},
            prompt_externs={"prompts.review": "prompts/review.md"},
            validate_shared=True,
            workspace_root=tmp_path,
            lowering_route=lowering_route,
        )
        bundle = result.validated_bundles["run-extern"]

        def normalize_target(value):
            if isinstance(value, dict):
                return {
                    key: normalize_target(item)
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [normalize_target(item) for item in value]
            if value in {"2.19", "2.20"}:
                return "<target-dsl>"
            return value

        return tuple(
            json.dumps(
                normalize_target(payload),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            for payload in (
                workflow_core_ast_to_json(bundle.core_workflow_ast),
                workflow_executable_ir_to_json(bundle.ir),
                workflow_semantic_ir_to_json(bundle.semantic_ir),
            )
        )

    assert build_payload_bytes("2.20") == build_payload_bytes("2.19")
