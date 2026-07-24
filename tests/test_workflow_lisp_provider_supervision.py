from dataclasses import replace
from pathlib import Path

import pytest

import orchestrator.workflow_lisp.effects as effect_module
import orchestrator.workflow_lisp.expressions as expression_module
import orchestrator.workflow_lisp.functions as function_module
import orchestrator.workflow_lisp.macros as workflow_lisp_macros
from orchestrator.workflow.validation import (
    WorkflowBoundaryValidationPolicy,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationOptions,
    validate_workflow_mapping,
)
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
    compile_stage1_entrypoint,
    compile_stage1_module,
)
from orchestrator.workflow_lisp.contracts import (
    derive_prompt_guided_structured_result_contract,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.expression_traversal import iter_child_exprs
from orchestrator.workflow_lisp.form_registry import (
    FormKind,
    get_form_spec,
    reserved_macro_names,
)
from orchestrator.workflow_lisp.procedures import (
    build_procedure_catalog,
    elaborate_procedure_definitions,
)
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.result_guidance import ResultGuidance
from orchestrator.workflow_lisp.syntax import SyntaxNode, build_syntax_module
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    PrimitiveTypeRef,
    RecordTypeRef,
    UnionTypeRef,
    type_refs_compatible,
)
from orchestrator.workflow_lisp.typecheck import typecheck_expression
from orchestrator.workflow_lisp.workflows import (
    build_extern_environment,
    elaborate_workflow_definitions,
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


def _type_environment(target_dsl: str, *forms: str) -> FrontendTypeEnvironment:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(target_dsl, *forms),
            source_path=f"directive_{target_dsl.replace('.', '_')}.orc",
        )
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )
    _validate_definition_module(module)
    return FrontendTypeEnvironment.from_module(module)


def _expression(source: str) -> SyntaxNode:
    parsed = read_sexpr_text(source, source_path="directive_expression.orc")
    assert len(parsed.items) == 1
    datum = parsed.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="directive_expression.orc",
        form_path=("workflow-lisp", "provider-supervision-directive"),
    )


def _write_module(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


@pytest.mark.parametrize("target_dsl", ("2.15", "2.16"))
def test_target_dsl_version_accepts_provider_supervision_version(
    target_dsl: str,
) -> None:
    module = build_syntax_module(
        read_sexpr_text(
            _module_source(target_dsl, "(defenum Approval APPROVE)"),
            source_path=f"target_{target_dsl.replace('.', '_')}.orc",
        )
    )

    assert module.target_dsl_version == target_dsl


@pytest.mark.parametrize("target_dsl", ("2.15", "2.16"))
def test_shared_validator_accepts_provider_supervision_target_version(
    tmp_path: Path,
    target_dsl: str,
) -> None:
    result = validate_workflow_mapping(
        WorkflowMappingBuildRequest(
            authored_mapping={
                "version": target_dsl,
                "name": "target-version",
                "steps": [{"name": "Done", "command": ["echo", "done"]}],
            },
            workflow_path=tmp_path / "target-version.orc",
            frontend_kind="workflow_lisp",
        ),
        options=WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE,
        ),
    )

    assert result.errors == ()
    assert result.bundle is not None
    assert result.bundle.surface.version == target_dsl


def test_target_216_installs_exact_provider_steering_directive_union() -> None:
    type_env = _type_environment("2.16")
    probe = _expression('"probe"')

    directive = type_env.resolve_type(
        "ProviderSteeringDirective",
        span=probe.span,
        form_path=probe.form_path,
    )

    assert isinstance(directive, UnionTypeRef)
    assert directive.name == "ProviderSteeringDirective"
    assert [variant.name for variant in directive.definition.variants] == [
        "CONTINUE",
        "STEER",
    ]
    assert directive.definition.variants[0].fields == ()
    assert [
        (field.name, field.type_name, field.guidance)
        for field in directive.definition.variants[1].fields
    ] == [
        (
            "guidance",
            "String",
            ResultGuidance(
                description=(
                    "Corrective guidance for the replacement "
                    "provider-session turn."
                )
            ),
        )
    ]
    assert directive.variant_field_types["CONTINUE"] == {}
    assert isinstance(
        directive.variant_field_types["STEER"]["guidance"],
        PrimitiveTypeRef,
    )
    assert directive.variant_field_types["STEER"]["guidance"].name == "String"


def test_target_below_216_does_not_install_provider_steering_directive() -> None:
    type_env = _type_environment("2.15")
    probe = _expression('"probe"')

    with pytest.raises(LispFrontendCompileError) as excinfo:
        type_env.resolve_type(
            "ProviderSteeringDirective",
            span=probe.span,
            form_path=probe.form_path,
        )

    assert excinfo.value.diagnostics[0].code == "type_unknown"


def test_provider_steering_directive_uses_ordinary_union_type_operations() -> None:
    type_env = _type_environment("2.16")
    probe = _expression('"probe"')
    directive = type_env.resolve_type(
        "ProviderSteeringDirective",
        span=probe.span,
        form_path=probe.form_path,
    )
    assert isinstance(directive, UnionTypeRef)

    continue_case = type_env.union_variant(
        directive,
        "CONTINUE",
        span=probe.span,
        form_path=probe.form_path,
    )
    steer_case = type_env.union_variant(
        directive,
        "STEER",
        span=probe.span,
        form_path=probe.form_path,
    )

    assert type_refs_compatible(directive, continue_case)
    assert type_refs_compatible(directive, steer_case)
    guidance_type = type_env.record_field(
        steer_case,
        "guidance",
        span=probe.span,
        form_path=probe.form_path,
    )
    assert isinstance(guidance_type, PrimitiveTypeRef)
    assert guidance_type.name == "String"


def test_provider_steering_directive_uses_ordinary_variant_and_match_typing() -> None:
    type_env = _type_environment("2.16")
    probe = _expression('"probe"')
    directive = type_env.resolve_type(
        "ProviderSteeringDirective",
        span=probe.span,
        form_path=probe.form_path,
    )

    typed_continue = typecheck_expression(
        elaborate_expression(
            _expression("(variant ProviderSteeringDirective CONTINUE)"),
            bound_names=frozenset(),
        ),
        type_env=type_env,
        value_env={},
    )
    typed_steer = typecheck_expression(
        elaborate_expression(
            _expression(
                '(variant ProviderSteeringDirective STEER :guidance "revise")'
            ),
            bound_names=frozenset(),
        ),
        type_env=type_env,
        value_env={},
    )
    typed_match = typecheck_expression(
        elaborate_expression(
            _expression(
                "(match directive "
                '((CONTINUE continued) "continue") '
                "((STEER steered) steered.guidance))"
            ),
            bound_names=frozenset({"directive"}),
        ),
        type_env=type_env,
        value_env={"directive": directive},
    )

    assert type_refs_compatible(directive, typed_continue.type_ref)
    assert type_refs_compatible(directive, typed_steer.type_ref)
    assert isinstance(typed_match.type_ref, PrimitiveTypeRef)
    assert typed_match.type_ref.name == "String"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            elaborate_expression(
                _expression(
                    '(match directive ((CONTINUE continued) "continue"))'
                ),
                bound_names=frozenset({"directive"}),
            ),
            type_env=type_env,
            value_env={"directive": directive},
        )

    assert excinfo.value.diagnostics[0].code == "union_match_non_exhaustive"


def test_provider_steering_directive_derives_exact_variant_output_contract() -> None:
    type_env = _type_environment("2.16")
    probe = _expression('"probe"')
    directive = type_env.resolve_type(
        "ProviderSteeringDirective",
        span=probe.span,
        form_path=probe.form_path,
    )

    contract = derive_prompt_guided_structured_result_contract(
        directive,
        workflow_name="supervision",
        step_id="supervise",
        type_env=type_env,
    )

    assert contract.contract_kind == "variant_output"
    assert contract.payload == {
        "path": (
            ".orchestrate/workflow_lisp/supervision/supervise/result.json"
        ),
        "discriminant": {
            "name": "variant",
            "json_pointer": "/variant",
            "type": "enum",
            "allowed": ["CONTINUE", "STEER"],
        },
        "shared_fields": [],
        "variants": {
            "CONTINUE": {"fields": []},
            "STEER": {
                "fields": [
                    {
                        "name": "guidance",
                        "json_pointer": "/guidance",
                        "type": "string",
                        "description": (
                            "Corrective guidance for the replacement "
                            "provider-session turn."
                        ),
                        "source_map_subject": {
                            "subject_kind": "variant_output_field",
                            "subject_name": (
                                "supervise::ProviderSteeringDirective"
                                "::STEER::guidance"
                            ),
                            "workflow_name": "supervision",
                        },
                    }
                ]
            },
        },
    }


@pytest.mark.parametrize(
    "authored_form",
    (
        "(defenum ProviderSteeringDirective OLD)",
        "(defpath ProviderSteeringDirective "
        ':kind relpath :under "state" :must-exist false)',
        "(defrecord ProviderSteeringDirective (value String))",
        "(defunion ProviderSteeringDirective (OLD))",
    ),
)
def test_target_216_rejects_authored_directive_type_shadowing(
    tmp_path: Path,
    authored_form: str,
) -> None:
    path = _write_module(
        tmp_path / "authored-shadow.orc",
        _module_source("2.16", authored_form),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(path)

    assert excinfo.value.diagnostics[0].code == "prelude_type_name_reserved"


def test_target_216_rejects_authored_directive_schema_shadowing(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "schema-shadow.orc",
        _module_source(
            "2.16",
            "(defschema ProviderSteeringDirective (value String))",
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(path)

    assert excinfo.value.diagnostics[0].code == "prelude_type_name_reserved"


def test_target_216_type_environment_rejects_bypassed_local_shadow() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.16",
                "(defunion ProviderSteeringDirective (LEGACY))",
            ),
            source_path="bypassed_local_shadow.orc",
        )
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        FrontendTypeEnvironment.from_module(module)

    assert excinfo.value.diagnostics[0].code == "prelude_type_name_reserved"


def test_target_216_type_environment_rejects_bypassed_import_shadow() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source("2.16"),
            source_path="bypassed_import_shadow.orc",
        )
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        FrontendTypeEnvironment.from_module(
            module,
            imported_type_refs={
                "ProviderSteeringDirective": PrimitiveTypeRef(
                    name="legacy/ProviderSteeringDirective"
                )
            },
        )

    assert excinfo.value.diagnostics[0].code == "prelude_type_name_reserved"


def test_target_below_216_keeps_authored_directive_type_meaning() -> None:
    type_env = _type_environment(
        "2.15",
        "(defunion ProviderSteeringDirective (LEGACY))",
    )
    probe = _expression('"probe"')

    directive = type_env.resolve_type(
        "ProviderSteeringDirective",
        span=probe.span,
        form_path=probe.form_path,
    )

    assert isinstance(directive, UnionTypeRef)
    assert [variant.name for variant in directive.definition.variants] == [
        "LEGACY"
    ]


def test_target_216_rejects_directive_type_parameter_shadowing() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.16",
                "(defproc identity "
                ":forall (ProviderSteeringDirective) "
                "((value ProviderSteeringDirective)) "
                "-> ProviderSteeringDirective "
                ":effects () :lowering inline value)",
            ),
            source_path="type_parameter_shadow.orc",
        )
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_procedure_definitions(syntax_module)

    assert excinfo.value.diagnostics[0].code == "prelude_type_name_reserved"


def test_target_below_216_keeps_directive_type_parameter_available() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.15",
                "(defproc identity "
                ":forall (ProviderSteeringDirective) "
                "((value ProviderSteeringDirective)) "
                "-> ProviderSteeringDirective "
                ":effects () :lowering inline value)",
            ),
            source_path="legacy_type_parameter.orc",
        )
    )

    definitions = elaborate_procedure_definitions(syntax_module)

    assert definitions[0].type_params[0].name == "ProviderSteeringDirective"


def _write_import_shadow_graph(
    tmp_path: Path,
    *,
    entry_import: str,
    support_target: str = "2.16",
    support_forms: tuple[str, ...] = ("(defenum External VALUE)",),
    support_exports: str = "External",
) -> Path:
    source_root = tmp_path / "modules"
    _write_module(
        source_root / "support.orc",
        _module_source(
            support_target,
            "(defmodule support)",
            f"(export {support_exports})",
            *support_forms,
        ),
    )
    return _write_module(
        source_root / "entry.orc",
        _module_source(
            "2.16",
            "(defmodule entry)",
            entry_import,
        ),
    )


def test_target_216_rejects_directive_import_alias_shadowing(
    tmp_path: Path,
) -> None:
    entry = _write_import_shadow_graph(
        tmp_path,
        entry_import=(
            "(import support :as ProviderSteeringDirective)"
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_entrypoint(entry, source_roots=(entry.parent,))

    assert excinfo.value.diagnostics[0].code == "prelude_type_name_reserved"


def test_target_216_rejects_unqualified_directive_import_shadowing(
    tmp_path: Path,
) -> None:
    entry = _write_import_shadow_graph(
        tmp_path,
        entry_import=(
            "(import support :only (ProviderSteeringDirective))"
        ),
        support_target="2.15",
        support_forms=(
            "(defunion ProviderSteeringDirective (LEGACY))",
        ),
        support_exports="ProviderSteeringDirective",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_entrypoint(entry, source_roots=(entry.parent,))

    assert excinfo.value.diagnostics[0].code == "prelude_type_name_reserved"


def test_target_216_allows_non_type_import_with_reserved_spelling(
    tmp_path: Path,
) -> None:
    entry = _write_import_shadow_graph(
        tmp_path,
        entry_import=(
            "(import support :only (ProviderSteeringDirective))"
        ),
        support_forms=(
            '(defun ProviderSteeringDirective () -> String "legacy")',
        ),
        support_exports="ProviderSteeringDirective",
    )

    result = compile_stage1_entrypoint(
        entry,
        source_roots=(entry.parent,),
    )

    assert result.entry_module.module_name == "entry"


def test_with_live_providers_elaborates_binding_edge_and_settlement_ast() -> None:
    expr = elaborate_expression(
        _expression(
            "(with-live-providers "
            '((worker "work") '
            '(supervisor "monitor" :observes worker)) '
            "worker)"
        ),
        bound_names=frozenset(),
    )

    node_type = getattr(expression_module, "WithLiveProvidersExpr")
    assert isinstance(expr, node_type)
    assert [binding.name for binding in expr.bindings] == [
        "worker",
        "supervisor",
    ]
    assert expr.bindings[0].observes is None
    assert expr.bindings[1].observes == "worker"
    assert expr.bindings[0].name_span.start.line == 1
    assert expr.bindings[1].observes_span.start.line == 1
    assert expr.bindings[1].observed_name_span.start.line == 1
    assert isinstance(expr.body, expression_module.NameExpr)
    assert expr.body.name == "worker"


def test_with_live_providers_traversal_preserves_authored_child_order() -> None:
    expr = elaborate_expression(
        _expression(
            "(with-live-providers "
            '((worker "work") '
            '(supervisor "monitor" :observes worker)) '
            "supervisor)"
        ),
        bound_names=frozenset(),
    )

    children = iter_child_exprs(expr)

    assert [
        child.value
        if isinstance(child, expression_module.LiteralExpr)
        else child.name
        for child in children
    ] == ["work", "monitor", "supervisor"]


def test_with_live_providers_has_static_non_macro_registry_route() -> None:
    spec = get_form_spec("with-live-providers")

    assert spec is not None
    assert spec.kind is FormKind.CORE_EFFECT
    assert spec.owner_module == "expressions"
    assert spec.elaboration_route == "with_live_providers"
    assert spec.feature_tags == frozenset({"provider_supervision"})
    assert spec.macro_bindable is False
    assert "with-live-providers" in reserved_macro_names()


@pytest.mark.parametrize(
    ("source", "expected_diagnostic", "expected_span_text"),
    (
        (
            "(with-live-providers "
            '((worker "work") '
            '(supervisor "monitor" :observes worker)))',
            "with_live_providers_arity_invalid",
            (
                "(with-live-providers "
                '((worker "work") '
                '(supervisor "monitor" :observes worker)))'
            ),
        ),
        (
            '(with-live-providers ((worker "work")) worker)',
            "with_live_providers_bindings_invalid",
            '((worker "work"))',
        ),
        (
            "(with-live-providers "
            '(worker (supervisor "monitor" :observes worker)) '
            "supervisor)",
            "with_live_providers_binding_invalid",
            "worker",
        ),
        (
            "(with-live-providers "
            '((worker "work") '
            '(worker "monitor" :observes worker)) '
            "worker)",
            "with_live_providers_binding_duplicate",
            "worker",
        ),
        (
            "(with-live-providers "
            '((worker "work") (supervisor "monitor")) '
            "worker)",
            "with_live_providers_observation_missing",
            '((worker "work") (supervisor "monitor"))',
        ),
        (
            "(with-live-providers "
            '((worker "work" :observes supervisor) '
            '(supervisor "monitor" :observes worker)) '
            "worker)",
            "with_live_providers_observation_duplicate",
            ":observes",
        ),
        (
            "(with-live-providers "
            '((worker "work") '
            '(supervisor "monitor" :observes other)) '
            "worker)",
            "with_live_providers_observed_peer_invalid",
            "other",
        ),
        (
            "(with-live-providers "
            '((worker "work") '
            '(supervisor "monitor" :observes supervisor)) '
            "worker)",
            "with_live_providers_observed_peer_invalid",
            "supervisor",
        ),
    ),
)
def test_live_providers_invalid_forms_report_specific_diagnostic_at_source(
    source: str,
    expected_diagnostic: str,
    expected_span_text: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression(source),
            bound_names=frozenset(),
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == expected_diagnostic
    assert diagnostic.span.start.path == "directive_expression.orc"
    assert (
        source[diagnostic.span.start.offset : diagnostic.span.end.offset]
        == expected_span_text
    )


def test_live_providers_invalid_observed_peer_type_blames_peer_token() -> None:
    source = (
        "(with-live-providers "
        '((worker "work") '
        '(supervisor "monitor" :observes "worker")) '
        "worker)"
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression(source),
            bound_names=frozenset(),
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "with_live_providers_binding_invalid"
    assert (
        source[diagnostic.span.start.offset : diagnostic.span.end.offset]
        == '"worker"'
    )


def test_live_providers_macro_hygiene_renames_binders_edge_and_body_together() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.16",
                "(defmacro define-live (name) "
                "(defworkflow name () -> String "
                "(with-live-providers "
                '((worker "work") '
                '(supervisor "monitor" :observes worker)) '
                "supervisor)))",
                "(define-live orchestrate)",
            ),
            source_path="live_provider_macro_hygiene.orc",
        )
    )
    catalog = workflow_lisp_macros.collect_macro_catalog(syntax_module)
    expanded = workflow_lisp_macros.expand_module_forms(
        syntax_module,
        catalog=catalog,
    )

    workflow = elaborate_workflow_definitions(expanded)[0]
    group = elaborate_expression(
        workflow.body,
        bound_names=frozenset(),
    )
    assert isinstance(group, expression_module.WithLiveProvidersExpr)
    worker, supervisor = group.bindings
    assert worker.name.startswith("%macro__define-live__m0001__")
    assert supervisor.name.startswith("%macro__define-live__m0001__")
    assert supervisor.observes == worker.name
    assert isinstance(group.body, expression_module.NameExpr)
    assert group.body.name == supervisor.name


def test_live_providers_form_head_is_reserved_against_macro_shadowing(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "live-provider-macro-shadow.orc",
        _module_source(
            "2.16",
            "(defmacro with-live-providers (value) value)",
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(path)

    assert excinfo.value.diagnostics[0].code == "macro_reserved_name"


def _live_provider_extern_environment():
    return build_extern_environment(
        provider_externs={
            "providers.worker": "worker-provider",
            "providers.supervisor": "supervisor-provider",
            "providers.body": "body-provider",
        },
        prompt_externs={
            "prompts.worker": "prompts/worker.md",
            "prompts.supervisor": "prompts/supervisor.md",
            "prompts.body": "prompts/body.md",
        },
    )


def _elaborate_live_provider_group(
    source: str,
    *,
    extra_bound_names: frozenset[str] = frozenset(),
):
    return elaborate_expression(
        _expression(source),
        bound_names=(
            frozenset(
                {
                    "providers.worker",
                    "providers.supervisor",
                    "providers.body",
                    "prompts.worker",
                    "prompts.supervisor",
                    "prompts.body",
                }
            )
            | extra_bound_names
        ),
    )


def test_type_environment_retains_target_dsl_for_feature_gates() -> None:
    assert _type_environment("2.15").target_dsl_version == "2.15"
    assert _type_environment("2.16").target_dsl_version == "2.16"


def test_live_providers_type_and_effect_summary_preserve_member_authority() -> None:
    type_env = _type_environment("2.16")
    expr = _elaborate_live_provider_group(
        "(with-live-providers "
        "((worker "
        "(provider-result providers.worker "
        ":prompt prompts.worker :inputs () :returns String)) "
        "(supervisor "
        "(provider-result providers.supervisor "
        ":prompt prompts.supervisor :inputs () "
        ":returns ProviderSteeringDirective) "
        ":observes worker)) "
        "worker)"
    )

    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={},
        extern_environment=_live_provider_extern_environment(),
    )

    assert isinstance(typed.type_ref, PrimitiveTypeRef)
    assert typed.type_ref.name == "String"
    live_effect_type = getattr(effect_module, "LiveSupervisionEffect")
    assert typed.effect_summary.direct_effects == frozenset(
        {
            effect_module.UsesProviderEffect(subject=("providers", "worker")),
            effect_module.UsesProviderEffect(
                subject=("providers", "supervisor")
            ),
            live_effect_type(supervisor="supervisor", worker="worker"),
        }
    )
    assert (
        typed.effect_summary.transitive_effects
        == typed.effect_summary.direct_effects
    )
    assert typed.effect_summary.procedure_edges == frozenset()


def test_live_providers_accepts_transportable_non_string_worker_and_binds_both_members() -> None:
    type_env = _type_environment(
        "2.16",
        (
            "(defrecord Supervised "
            "(work Bool) "
            "(directive ProviderSteeringDirective))"
        ),
    )
    expr = _elaborate_live_provider_group(
        "(with-live-providers "
        "((worker worker_value) "
        "(supervisor "
        "(variant ProviderSteeringDirective CONTINUE) "
        ":observes worker)) "
        "(record Supervised :work worker :directive supervisor))",
        extra_bound_names=frozenset({"worker_value"}),
    )

    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={"worker_value": PrimitiveTypeRef(name="Bool")},
    )

    assert isinstance(typed.type_ref, RecordTypeRef)
    assert typed.type_ref.definition.name == "Supervised"


def test_live_providers_target_215_rejects_known_form_at_type_gate() -> None:
    type_env = _type_environment("2.15")
    expr = _elaborate_live_provider_group(
        "(with-live-providers "
        '((worker "work") '
        '(supervisor "monitor" :observes worker)) '
        "worker)"
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={},
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "provider_supervision_target_dsl_unsupported"
    assert diagnostic.span == expr.span


def test_live_provider_members_do_not_see_sibling_bindings() -> None:
    type_env = _type_environment("2.16")
    expr = _elaborate_live_provider_group(
        "(with-live-providers "
        "((supervisor "
        "(variant ProviderSteeringDirective CONTINUE) "
        ":observes worker) "
        "(worker supervisor)) "
        "worker)"
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={},
        )

    assert excinfo.value.diagnostics[0].code == "name_unknown"


@pytest.mark.parametrize(
    ("malformation", "expected_diagnostic"),
    (
        ("missing_observer", "with_live_providers_observation_missing"),
        ("duplicate_observer", "with_live_providers_observation_duplicate"),
        ("unknown_peer", "with_live_providers_observed_peer_invalid"),
        ("duplicate_name", "with_live_providers_binding_duplicate"),
    ),
)
def test_live_provider_type_boundary_rejects_malformed_transformed_ast(
    malformation: str,
    expected_diagnostic: str,
) -> None:
    type_env = _type_environment("2.16")
    expr = _elaborate_live_provider_group(
        "(with-live-providers "
        "((worker worker_value) "
        "(supervisor "
        "(variant ProviderSteeringDirective CONTINUE) "
        ":observes worker)) "
        "worker)",
        extra_bound_names=frozenset({"worker_value"}),
    )
    worker, supervisor = expr.bindings
    if malformation == "missing_observer":
        bindings = (
            worker,
            replace(
                supervisor,
                observes=None,
                observes_span=None,
                observed_name_span=None,
            ),
        )
    elif malformation == "duplicate_observer":
        bindings = (
            replace(worker, observes=supervisor.name),
            supervisor,
        )
    elif malformation == "unknown_peer":
        bindings = (
            worker,
            replace(supervisor, observes="other"),
        )
    else:
        bindings = (
            worker,
            replace(supervisor, name=worker.name),
        )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            replace(expr, bindings=bindings),
            type_env=type_env,
            value_env={
                "worker_value": PrimitiveTypeRef(name="String"),
            },
        )

    assert excinfo.value.diagnostics[0].code == expected_diagnostic


def test_live_providers_requires_exact_full_directive_for_supervisor() -> None:
    type_env = _type_environment("2.16")
    probe = _expression('"probe"')
    directive = type_env.resolve_type(
        "ProviderSteeringDirective",
        span=probe.span,
        form_path=probe.form_path,
    )
    assert isinstance(directive, UnionTypeRef)
    continue_case = type_env.union_variant(
        directive,
        "CONTINUE",
        span=probe.span,
        form_path=probe.form_path,
    )
    expr = _elaborate_live_provider_group(
        "(with-live-providers "
        "((worker worker_value) "
        "(supervisor supervisor_value :observes worker)) "
        "worker)",
        extra_bound_names=frozenset(
            {"worker_value", "supervisor_value"}
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={
                "worker_value": PrimitiveTypeRef(name="String"),
                "supervisor_value": continue_case,
            },
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "provider_supervision_supervisor_type_invalid"
    )


def test_live_providers_rejects_nontransportable_worker_type() -> None:
    type_env = _type_environment("2.16")
    expr = _elaborate_live_provider_group(
        "(with-live-providers "
        "((worker opaque) "
        "(supervisor "
        "(variant ProviderSteeringDirective CONTINUE) "
        ":observes worker)) "
        "worker)",
        extra_bound_names=frozenset({"opaque"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={"opaque": PrimitiveTypeRef(name="Json")},
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "provider_supervision_worker_type_invalid"
    )


def test_live_providers_rejects_effectful_settlement_body() -> None:
    type_env = _type_environment("2.16")
    expr = _elaborate_live_provider_group(
        "(with-live-providers "
        "((worker worker_value) "
        "(supervisor "
        "(variant ProviderSteeringDirective CONTINUE) "
        ":observes worker)) "
        "(provider-result providers.body "
        ":prompt prompts.body :inputs () :returns String))",
        extra_bound_names=frozenset({"worker_value"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={
                "worker_value": PrimitiveTypeRef(name="String"),
            },
            extern_environment=_live_provider_extern_environment(),
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "provider_supervision_settlement_effectful"
    )


def test_live_providers_rejects_effect_free_procedure_edge_in_settlement() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.16",
                (
                    "(defproc settle () -> String "
                    ':effects () :lowering inline "done")'
                ),
            ),
            source_path="live_provider_settlement_procedure.orc",
        )
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    procedure_catalog = build_procedure_catalog(
        procedure_defs,
        type_env=type_env,
    )
    expr = elaborate_expression(
        _expression(
            "(with-live-providers "
            "((worker worker_value) "
            "(supervisor "
            "(variant ProviderSteeringDirective CONTINUE) "
            ":observes worker)) "
            "(settle))"
        ),
        bound_names=frozenset({"worker_value"}),
        procedure_names=frozenset({"settle"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={
                "worker_value": PrimitiveTypeRef(name="String"),
            },
            procedure_catalog=procedure_catalog,
            procedure_effects_by_name={
                "settle": effect_module.EMPTY_EFFECT_SUMMARY,
            },
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "provider_supervision_settlement_effectful"
    )


def _typed_identity_function():
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.16",
                "(defun identity ((value String)) -> String value)",
            ),
            source_path="live_provider_function_normalization.orc",
        )
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    definitions = function_module.elaborate_function_definitions(
        syntax_module
    )
    catalog = function_module.build_function_catalog(
        definitions,
        type_env=type_env,
    )
    typed = function_module.typecheck_function_definitions(
        definitions,
        type_env=type_env,
        function_catalog=catalog,
    )
    return typed[0]


def test_live_providers_helper_normalization_descends_into_members_and_body() -> None:
    identity = _typed_identity_function()
    expr = elaborate_expression(
        _expression(
            "(with-live-providers "
            '((worker (identity "work")) '
            "(supervisor "
            "(variant ProviderSteeringDirective CONTINUE) "
            ":observes worker)) "
            "(identity worker))"
        ),
        bound_names=frozenset(),
        function_names=frozenset({"identity"}),
    )

    normalized = function_module.normalize_function_calls(
        expr,
        typed_functions_by_name={"identity": identity},
    )

    assert isinstance(
        normalized.bindings[0].value_expr,
        expression_module.LetStarExpr,
    )
    assert isinstance(normalized.body, expression_module.LetStarExpr)
    assert "FunctionCallExpr" not in repr(normalized)


def test_live_providers_is_classified_as_effectful_in_pure_helpers() -> None:
    expr = _elaborate_live_provider_group(
        "(with-live-providers "
        '((worker "work") '
        "(supervisor "
        "(variant ProviderSteeringDirective CONTINUE) "
        ":observes worker)) "
        "worker)"
    )

    assert (
        function_module._find_purity_violation(expr)
        == "with-live-providers"
    )


def test_live_providers_rejects_pure_helper_position_with_public_diagnostic() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.16",
                (
                    "(defun invalid-helper () -> String "
                    "(with-live-providers "
                    '((worker "work") '
                    "(supervisor "
                    "(variant ProviderSteeringDirective CONTINUE) "
                    ":observes worker)) "
                    "worker))"
                ),
            ),
            source_path="live_provider_function_position.orc",
        )
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    definitions = function_module.elaborate_function_definitions(
        syntax_module
    )
    catalog = function_module.build_function_catalog(
        definitions,
        type_env=type_env,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        function_module.typecheck_function_definitions(
            definitions,
            type_env=type_env,
            function_catalog=catalog,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "pure_function_has_effect"
    assert diagnostic.span == definitions[0].body.span
