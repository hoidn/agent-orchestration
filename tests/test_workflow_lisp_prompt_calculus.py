"""Focused acceptance tests for the target-2.20 prompt declaration core."""

from dataclasses import FrozenInstanceError

import pytest

import orchestrator.workflow_lisp as workflow_lisp
import orchestrator.workflow_lisp.form_registry as form_registry
import orchestrator.workflow_lisp.syntax as syntax
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_text


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
    assert not syntax.target_dsl_supports_prompt_calculus("2.19")
    assert syntax.target_dsl_supports_prompt_calculus("2.20")

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
