"""Focused acceptance tests for the target-2.20 prompt declaration core."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import orchestrator.workflow_lisp as workflow_lisp
import orchestrator.workflow_lisp.compiler as workflow_lisp_compiler
import orchestrator.workflow_lisp.form_registry as form_registry
import orchestrator.workflow_lisp.syntax as syntax
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
        ("(message :value :out)", "prompt_slot_refinement_invalid"),
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


def _catalog(*declarations: str):
    parsed = syntax.build_syntax_module(
        read_sexpr_text(
            _module_source("2.20", *declarations),
            source_path="inline_prompt_catalog.orc",
        )
    )
    definitions = workflow_lisp.elaborate_prompt_definitions(parsed)
    return build_prompt_catalog(
        "demo/prompts",
        definitions,
        type_env=_empty_type_env(),
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
            _module_source(
                target_dsl,
                f"(defworkflow ignored () -> Value {source})",
            ),
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
