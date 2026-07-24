from dataclasses import replace
from pathlib import Path

import pytest

import orchestrator.workflow_lisp.compiler as compiler_module
import orchestrator.workflow_lisp.effects as effect_module
import orchestrator.workflow_lisp.expressions as expression_module
import orchestrator.workflow_lisp.functions as function_module
import orchestrator.workflow_lisp.lowering as lowering_module
import orchestrator.workflow_lisp.macros as workflow_lisp_macros
import orchestrator.workflow_lisp.wcc.elaborate as wcc_elaborate_module
import orchestrator.workflow_lisp.wcc.model as wcc_model
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
    build_command_boundary_environment,
    build_extern_environment,
    build_workflow_catalog,
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


def _typed_live_provider_wcc_context(
    tmp_path: Path,
    *forms: str,
):
    source = _module_source("2.16", *forms)
    path = _write_module(
        tmp_path / "live_provider_wcc_probe.orc",
        source,
    )
    syntax_module = build_syntax_module(
        read_sexpr_text(source, source_path=str(path))
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(
        module,
        workflow_defs,
        type_env,
    )
    procedure_catalog = build_procedure_catalog(
        procedure_defs,
        type_env=type_env,
    )
    typed_procedures, typed_workflows, procedure_catalog = (
        compiler_module._infer_stage3_effect_summaries(
            procedure_defs,
            module=module,
            workflow_defs=workflow_defs,
            type_env=type_env,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            extern_environment=_live_provider_extern_environment(),
            command_boundary_environment=build_command_boundary_environment(
                {}
            ),
        )
    )
    procedure_type_envs = {
        procedure.definition.name: type_env
        for procedure in typed_procedures
    }
    resolved_procedures_by_name = lowering_module._resolve_procedure_lowering(
        typed_procedures,
        typed_workflows=typed_workflows,
        workflow_path=path,
        type_env=type_env,
        procedure_type_envs=procedure_type_envs,
    )
    return {
        "path": path,
        "source": source,
        "type_env": type_env,
        "typed_workflow": typed_workflows[0],
        "resolved_procedures_by_name": resolved_procedures_by_name,
        "procedure_type_envs": procedure_type_envs,
        "workflow_return_types": {
            workflow.definition.name: workflow.signature.return_type_ref
            for workflow in typed_workflows
        },
        "procedure_return_types": {
            name: procedure.signature.return_type_ref
            for name, procedure in resolved_procedures_by_name.items()
        },
    }


def _elaborate_live_provider_wcc(context):
    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    assert isinstance(body, wcc_model.WccLet)
    assert isinstance(body.bound_value, wcc_model.WccProviderSupervision)
    return body.bound_value


def _linear_wcc_lets(body) -> list[wcc_model.WccLet]:
    lets: list[wcc_model.WccLet] = []
    current = body
    while isinstance(current, wcc_model.WccLet):
        lets.append(current)
        current = current.body
    return lets


def _resolve_wcc_linear_alias(
    value,
    bindings: dict[str, object],
):
    seen: set[str] = set()
    current = value
    while (
        isinstance(current, wcc_model.WccNameAtom)
        and current.name in bindings
        and current.name not in seen
    ):
        seen.add(current.name)
        current = bindings[current.name]
    return current


def _resolved_wcc_linear_bindings(
    lets: list[wcc_model.WccLet],
) -> dict[str, object]:
    bindings: dict[str, object] = {}
    for item in lets:
        if isinstance(
            item.bound_value,
            (wcc_model.WccLiteralAtom, wcc_model.WccNameAtom),
        ):
            bindings[item.bound_name] = _resolve_wcc_linear_alias(
                item.bound_value,
                bindings,
            )
    return bindings


def test_wcc_elaborates_direct_live_provider_members_as_two_closed_regions(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () :returns String)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )

    group_type = getattr(wcc_model, "WccProviderSupervision")
    member_type = getattr(wcc_model, "WccProviderSupervisionMember")
    assert isinstance(body, wcc_model.WccLet)
    group = body.bound_value
    assert isinstance(group, group_type)
    assert len(group.members) == 2
    assert all(isinstance(member, member_type) for member in group.members)
    assert all("WccCall" not in repr(member) for member in group.members)
    assert all(repr(member).count("WccPerform") == 1 for member in group.members)
    assert all(member.provider_binding_name for member in group.members)
    binding_sources = [
        context["source"][
            member.binding_metadata.source_span.start.offset :
            member.binding_metadata.source_span.end.offset
        ]
        for member in group.members
    ]
    assert binding_sources[0].startswith("(worker ")
    assert binding_sources[1].startswith("(supervisor ")
    observation_source = context["source"][
        group.observation_metadata.source_span.start.offset :
        group.observation_metadata.source_span.end.offset
    ]
    assert observation_source == ":observes worker"
    ownership_ids = {
        group.metadata.node_id,
        group.observation_metadata.node_id,
        *(member.binding_metadata.node_id for member in group.members),
    }
    assert len(ownership_ids) == 4


def test_wcc_closes_nested_explicit_inline_live_provider_members(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc worker-leaf () -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () :returns String))"
        ),
        (
            "(defproc worker-outer () -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(worker-leaf))"
        ),
        (
            "(defproc supervisor-leaf () "
            "-> ProviderSteeringDirective "
            ":effects ((uses-provider providers.supervisor)) "
            ":lowering inline "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective))"
        ),
        (
            "(defproc supervisor-outer () "
            "-> ProviderSteeringDirective "
            ":effects ((uses-provider providers.supervisor)) "
            ":lowering inline "
            "(supervisor-leaf))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker (worker-outer)) "
            "(supervisor (supervisor-outer) "
            ":observes worker)) "
            "worker))"
        ),
    )
    closed_body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    assert isinstance(closed_body, wcc_model.WccLet)
    closed_group = closed_body.bound_value

    assert isinstance(
        closed_group,
        getattr(wcc_model, "WccProviderSupervision"),
    )
    assert "WccCall" not in repr(closed_group)
    assert repr(closed_group).count("WccPerform") == 2
    assert all(
        member.provider_binding_name is not None
        for member in closed_group.members
    )


def test_wcc_closes_exact_proc_ref_specialized_live_provider_member(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc worker-leaf ((prompt-input String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (prompt-input) "
            ":returns String))"
        ),
        (
            "(defproc select-worker "
            "((runner ProcRef[() -> String])) -> String "
            ":effects () :lowering inline "
            "(runner))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker "
            "(let* ((runner "
            "(bind-proc (proc-ref worker-leaf) "
            ':prompt-input "compiler-bound"))) '
            "(select-worker runner))) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )
    specialized = next(
        procedure
        for procedure in context["resolved_procedures_by_name"].values()
        if procedure.specialization is not None
        and procedure.specialization.base_name == "select-worker"
        and procedure.specialization.proc_ref_bindings
    )
    runner = specialized.specialization.proc_ref_bindings["runner"]
    bound_leaf = context["resolved_procedures_by_name"][
        runner.call_target_name
    ]

    assert specialized.definition.name.startswith(
        "%proc-ref-call.select_worker."
    )
    assert specialized.signature.params == ()
    assert runner.procedure_name == "worker-leaf"
    assert runner.call_target_name.startswith("%proc-ref.worker_leaf.")
    assert tuple(argument.name for argument in runner.bound_args) == (
        "prompt-input",
    )
    assert bound_leaf.specialization is not None
    assert bound_leaf.specialization.base_name == "worker-leaf"
    assert tuple(bound_leaf.specialization.value_bindings) == (
        "prompt-input",
    )

    closed_group = _close_source_level_live_provider_group(context)
    worker = next(
        member
        for member in closed_group.members
        if member.binding_name == "worker"
    )
    assert "WccCall" not in repr(worker.normalized_body)
    assert repr(worker.normalized_body).count("WccPerform") == 1
    assert context["source"][
        worker.metadata.source_span.start.offset :
        worker.metadata.source_span.end.offset
    ].startswith(
        "(let* ((runner (bind-proc (proc-ref worker-leaf) "
    )
    provider_let = worker.normalized_body
    while (
        isinstance(provider_let, wcc_model.WccLet)
        and not isinstance(provider_let.bound_value, wcc_model.WccPerform)
    ):
        provider_let = provider_let.body
    assert isinstance(provider_let, wcc_model.WccLet)
    assert isinstance(provider_let.bound_value, wcc_model.WccPerform)
    assert [
        argument.value
        for argument in provider_let.bound_value.positional_args
        if isinstance(argument, wcc_model.WccLiteralAtom)
    ] == ["compiler-bound"]
    bound_argument = provider_let.bound_value.positional_args[0]
    assert context["source"][
        bound_argument.metadata.source_span.start.offset :
        bound_argument.metadata.source_span.end.offset
    ] == '"compiler-bound"'
    provider_metadata = provider_let.bound_value.metadata
    assert context["source"][
        provider_metadata.source_span.start.offset :
        provider_metadata.source_span.end.offset
    ].startswith("(provider-result providers.worker ")


def test_wcc_erases_direct_proc_ref_argument_before_closing_member(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc direct-worker-leaf () -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () :returns String))"
        ),
        (
            "(defproc select-direct-worker "
            "((runner ProcRef[() -> String])) -> String "
            ":effects () :lowering inline "
            "(runner))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker "
            "(select-direct-worker (proc-ref direct-worker-leaf))) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    assert isinstance(body, wcc_model.WccLet)
    group = body.bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    assert "WccCall" not in repr(worker.normalized_body)
    assert repr(worker.normalized_body).count("WccPerform") == 1


def test_wcc_closes_direct_member_call_through_outer_bind_proc(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc bound-worker-impl "
            "((prompt-input String) (runtime-input String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker "
            ":inputs (prompt-input runtime-input) "
            ":returns String))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(let* ((bound-worker "
            "(bind-proc (proc-ref bound-worker-impl) "
            ':prompt-input "compiler-bound"))) '
            "(with-live-providers "
            '((worker (bound-worker "runtime")) '
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker)))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    assert isinstance(body, wcc_model.WccLet)
    group = body.bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    assert "WccCall" not in repr(worker.normalized_body)
    assert repr(worker.normalized_body).count("WccPerform") == 1


def test_wcc_retains_value_specialization_argument_to_nested_procedure(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc value-worker-leaf ((input String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (input) :returns String))"
        ),
        (
            "(defproc value-worker-wrapper ((fixed String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(value-worker-leaf fixed))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(let* ((bound-worker "
            "(bind-proc (proc-ref value-worker-wrapper) "
            ':fixed "retained"))) '
            "(with-live-providers "
            "((worker (bound-worker)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker)))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    assert isinstance(body, wcc_model.WccLet)
    group = body.bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    provider_let = worker.normalized_body
    while (
        isinstance(provider_let, wcc_model.WccLet)
        and not isinstance(provider_let.bound_value, wcc_model.WccPerform)
    ):
        provider_let = provider_let.body
    assert isinstance(provider_let, wcc_model.WccLet)
    assert isinstance(provider_let.bound_value, wcc_model.WccPerform)
    assert [
        argument.value
        for argument in provider_let.bound_value.positional_args
        if isinstance(argument, wcc_model.WccLiteralAtom)
    ] == ["retained"]


def test_wcc_substitutes_nested_value_capture_from_outer_inline_call(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc captured-worker-leaf ((input String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (input) :returns String))"
        ),
        (
            "(defproc captured-worker-wrapper ((fixed String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(captured-worker-leaf fixed))"
        ),
        (
            "(defproc capture-worker ((runtime-input String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(let* ((bound-worker "
            "(bind-proc (proc-ref captured-worker-wrapper) "
            ":fixed runtime-input))) "
            "(bound-worker)))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            '((worker (capture-worker "captured")) '
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    assert isinstance(body, wcc_model.WccLet)
    group = body.bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    assert "runtime-input" not in repr(worker.normalized_body)
    assert "fixed" not in repr(worker.normalized_body)
    assert "value='captured'" in repr(worker.normalized_body)


def test_wcc_value_capture_is_alpha_safe_against_residual_parameter(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc collision-worker-target "
            "((fixed String) (input String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (fixed input) "
            ":returns String))"
        ),
        (
            "(defproc collision-worker-wrapper "
            "((input String) (runtime-input String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(let* ((bound-worker "
            "(bind-proc (proc-ref collision-worker-target) "
            ":fixed input))) "
            "(bound-worker runtime-input)))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker "
            '(collision-worker-wrapper "captured" "runtime")) '
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    assert isinstance(body, wcc_model.WccLet)
    group = body.bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    member_lets = _linear_wcc_lets(worker.normalized_body)
    provider_index = next(
        index
        for index, item in enumerate(member_lets)
        if isinstance(item.bound_value, wcc_model.WccPerform)
    )
    provider_let = member_lets[provider_index]
    assert isinstance(provider_let.bound_value, wcc_model.WccPerform)
    bindings = _resolved_wcc_linear_bindings(
        member_lets[:provider_index]
    )
    assert [
        resolved.value
        for argument in provider_let.bound_value.positional_args
        if isinstance(
            (
                resolved := _resolve_wcc_linear_alias(
                    argument,
                    bindings,
                )
            ),
            wcc_model.WccLiteralAtom,
        )
    ] == ["captured", "runtime"]


def test_wcc_substitutes_workflow_input_capture_from_bound_proc(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc workflow-capture-target "
            "((prompt-input String) (runtime-input String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker "
            ":inputs (prompt-input runtime-input) "
            ":returns String))"
        ),
        (
            "(defworkflow orchestrate ((captured String)) -> String "
            "(let* ((bound-worker "
            "(bind-proc (proc-ref workflow-capture-target) "
            ":prompt-input captured))) "
            "(with-live-providers "
            '((worker (bound-worker "runtime")) '
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker)))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    root_lets = _linear_wcc_lets(body)
    group_index = next(
        index
        for index, item in enumerate(root_lets)
        if isinstance(
            item.bound_value,
            wcc_model.WccProviderSupervision,
        )
    )
    group = root_lets[group_index].bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    provider_let = worker.normalized_body
    while (
        isinstance(provider_let, wcc_model.WccLet)
        and not isinstance(provider_let.bound_value, wcc_model.WccPerform)
    ):
        provider_let = provider_let.body
    assert isinstance(provider_let, wcc_model.WccLet)
    assert isinstance(provider_let.bound_value, wcc_model.WccPerform)
    root_bindings = _resolved_wcc_linear_bindings(
        root_lets[:group_index]
    )
    resolved_args = [
        _resolve_wcc_linear_alias(argument, root_bindings)
        for argument in provider_let.bound_value.positional_args
    ]
    assert [
        (
            argument.name
            if isinstance(argument, wcc_model.WccNameAtom)
            else argument.value
        )
        for argument in resolved_args
    ] == ["captured", "runtime"]
    assert "__wcc_supervision_capture_" not in repr(
        worker.normalized_body
    )


def test_wcc_preserves_direct_bind_proc_argument_capture_identity(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc direct-capture-leaf "
            "((fixed String) (runtime String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (fixed runtime) "
            ":returns String))"
        ),
        (
            "(defproc direct-capture-select "
            "((runner ProcRef[(String) -> String])) -> String "
            ":effects () :lowering inline "
            '(let* ((captured "shadowed")) (runner captured)))'
        ),
        (
            "(defworkflow orchestrate ((captured String)) -> String "
            "(with-live-providers "
            "((worker "
            "(direct-capture-select "
            "(bind-proc (proc-ref direct-capture-leaf) "
            ":fixed captured))) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    assert isinstance(body, wcc_model.WccLet)
    group = body.bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    member_lets = _linear_wcc_lets(worker.normalized_body)
    provider_index = next(
        index
        for index, item in enumerate(member_lets)
        if isinstance(item.bound_value, wcc_model.WccPerform)
    )
    provider_let = member_lets[provider_index]
    assert isinstance(provider_let.bound_value, wcc_model.WccPerform)
    provider_arg = provider_let.bound_value.positional_args[0]
    resolved_arg = _resolve_wcc_linear_alias(
        provider_arg,
        _resolved_wcc_linear_bindings(
            member_lets[:provider_index]
        ),
    )
    assert isinstance(resolved_arg, wcc_model.WccNameAtom)
    assert resolved_arg.name == "captured"
    assert "WccCall" not in repr(worker.normalized_body)


def test_wcc_inherits_sequential_bind_proc_capture_identities_through_alias(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc sequential-capture-leaf "
            "((first String) (second String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (first second) "
            ":returns String))"
        ),
        (
            "(defworkflow orchestrate "
            "((one String) (two String)) -> String "
            "(let* ((partial "
            "(bind-proc (proc-ref sequential-capture-leaf) "
            ":first one)) "
            "(alias partial) "
            "(complete (bind-proc alias :second two))) "
            "(with-live-providers "
            "((worker (complete)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker)))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    root_lets = _linear_wcc_lets(body)
    group_index = next(
        index
        for index, item in enumerate(root_lets)
        if isinstance(
            item.bound_value,
            wcc_model.WccProviderSupervision,
        )
    )
    group = root_lets[group_index].bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    member_lets = _linear_wcc_lets(worker.normalized_body)
    provider_let = next(
        item
        for item in member_lets
        if isinstance(item.bound_value, wcc_model.WccPerform)
    )
    assert isinstance(provider_let.bound_value, wcc_model.WccPerform)
    root_bindings = _resolved_wcc_linear_bindings(
        root_lets[:group_index]
    )
    resolved_args = [
        _resolve_wcc_linear_alias(argument, root_bindings)
        for argument in provider_let.bound_value.positional_args
    ]
    assert [
        argument.name
        for argument in resolved_args
        if isinstance(argument, wcc_model.WccNameAtom)
    ] == ["one", "two"]


def test_wcc_runtime_shadow_masks_outer_compile_time_proc_ref(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc unused-shadow-leaf () -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () "
            ":returns String))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(let* ((runner (proc-ref unused-shadow-leaf))) "
            '(let* ((runner "runtime")) '
            "(with-live-providers "
            "((worker "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (runner) "
            ":returns String)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    root_lets = _linear_wcc_lets(body)
    group_index = next(
        index
        for index, item in enumerate(root_lets)
        if isinstance(
            item.bound_value,
            wcc_model.WccProviderSupervision,
        )
    )
    group = root_lets[group_index].bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    provider_let = next(
        item
        for item in _linear_wcc_lets(worker.normalized_body)
        if isinstance(item.bound_value, wcc_model.WccPerform)
    )
    assert isinstance(provider_let.bound_value, wcc_model.WccPerform)
    (provider_arg,) = provider_let.bound_value.positional_args
    resolved_arg = _resolve_wcc_linear_alias(
        provider_arg,
        _resolved_wcc_linear_bindings(
            root_lets[:group_index]
        ),
    )
    assert isinstance(resolved_arg, wcc_model.WccLiteralAtom)
    assert resolved_arg.value == "runtime"


def test_wcc_routes_same_target_captures_by_proc_ref_parameter(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc shared-capture-leaf ((fixed String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (fixed) "
            ":returns String))"
        ),
        (
            "(defproc choose-first-capture "
            "((first ProcRef[() -> String]) "
            "(unused ProcRef[() -> String])) -> String "
            ":effects () :lowering inline (first))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            '(let* ((x "original") '
            "(first (bind-proc (proc-ref shared-capture-leaf) "
            ":fixed x))) "
            '(let* ((x "shadow") '
            "(second (bind-proc (proc-ref shared-capture-leaf) "
            ":fixed x))) "
            "(with-live-providers "
            "((worker (choose-first-capture first second)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    root_lets = _linear_wcc_lets(body)
    group_index = next(
        index
        for index, item in enumerate(root_lets)
        if isinstance(
            item.bound_value,
            wcc_model.WccProviderSupervision,
        )
    )
    group = root_lets[group_index].bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    provider_let = next(
        item
        for item in _linear_wcc_lets(worker.normalized_body)
        if isinstance(item.bound_value, wcc_model.WccPerform)
    )
    assert isinstance(provider_let.bound_value, wcc_model.WccPerform)
    (provider_arg,) = provider_let.bound_value.positional_args
    resolved_arg = _resolve_wcc_linear_alias(
        provider_arg,
        _resolved_wcc_linear_bindings(
            root_lets[:group_index]
        ),
    )
    assert isinstance(resolved_arg, wcc_model.WccLiteralAtom)
    assert resolved_arg.value == "original"


def test_wcc_forwards_bound_proc_alias_with_capture_identity(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc alias-capture-leaf ((fixed String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (fixed) "
            ":returns String))"
        ),
        (
            "(defproc select-alias-capture "
            "((runner ProcRef[() -> String])) -> String "
            ":effects () :lowering inline (runner))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            '(let* ((captured "original") '
            "(runner (bind-proc (proc-ref alias-capture-leaf) "
            ":fixed captured)) "
            "(alias runner)) "
            '(let* ((captured "shadowed")) '
            "(with-live-providers "
            "((worker (select-alias-capture alias)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    root_lets = _linear_wcc_lets(body)
    group_index = next(
        index
        for index, item in enumerate(root_lets)
        if isinstance(
            item.bound_value,
            wcc_model.WccProviderSupervision,
        )
    )
    group = root_lets[group_index].bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    provider_let = next(
        item
        for item in _linear_wcc_lets(worker.normalized_body)
        if isinstance(item.bound_value, wcc_model.WccPerform)
    )
    assert isinstance(provider_let.bound_value, wcc_model.WccPerform)
    (provider_arg,) = provider_let.bound_value.positional_args
    resolved_arg = _resolve_wcc_linear_alias(
        provider_arg,
        _resolved_wcc_linear_bindings(
            root_lets[:group_index]
        ),
    )
    assert isinstance(resolved_arg, wcc_model.WccLiteralAtom)
    assert resolved_arg.value == "original"


def test_wcc_forwards_proc_ref_alias_inside_inlined_callee(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc inner-alias-leaf ((fixed String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (fixed) "
            ":returns String))"
        ),
        (
            "(defproc inner-alias-select "
            "((runner ProcRef[() -> String])) -> String "
            ":effects () :lowering inline "
            "(let* ((alias runner)) (alias)))"
        ),
        (
            "(defworkflow orchestrate ((captured String)) -> String "
            "(let* ((runner "
            "(bind-proc (proc-ref inner-alias-leaf) "
            ":fixed captured))) "
            "(with-live-providers "
            "((worker (inner-alias-select runner)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker)))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    root_lets = _linear_wcc_lets(body)
    group_index = next(
        index
        for index, item in enumerate(root_lets)
        if isinstance(
            item.bound_value,
            wcc_model.WccProviderSupervision,
        )
    )
    group = root_lets[group_index].bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    provider_let = next(
        item
        for item in _linear_wcc_lets(worker.normalized_body)
        if isinstance(item.bound_value, wcc_model.WccPerform)
    )
    assert isinstance(provider_let.bound_value, wcc_model.WccPerform)
    (provider_arg,) = provider_let.bound_value.positional_args
    resolved_arg = _resolve_wcc_linear_alias(
        provider_arg,
        _resolved_wcc_linear_bindings(
            root_lets[:group_index]
        ),
    )
    assert isinstance(resolved_arg, wcc_model.WccNameAtom)
    assert resolved_arg.name == "captured"


def test_wcc_local_proc_ref_shadow_masks_deferred_capture_owner(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc shadow-owner-leaf ((fixed String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (fixed) "
            ":returns String))"
        ),
        (
            "(defproc shadow-owner-select "
            "((runner ProcRef[() -> String])) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            '(let* ((x "local") '
            "(runner (bind-proc (proc-ref shadow-owner-leaf) "
            ":fixed x))) "
            "(runner)))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            '(let* ((x "original") '
            "(runner (bind-proc (proc-ref shadow-owner-leaf) "
            ":fixed x))) "
            "(with-live-providers "
            "((worker (shadow-owner-select runner)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker)))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    root_lets = _linear_wcc_lets(body)
    group_index = next(
        index
        for index, item in enumerate(root_lets)
        if isinstance(
            item.bound_value,
            wcc_model.WccProviderSupervision,
        )
    )
    group = root_lets[group_index].bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    member_lets = _linear_wcc_lets(worker.normalized_body)
    provider_index = next(
        index
        for index, item in enumerate(member_lets)
        if isinstance(item.bound_value, wcc_model.WccPerform)
    )
    provider_let = member_lets[provider_index]
    assert isinstance(provider_let.bound_value, wcc_model.WccPerform)
    (provider_arg,) = provider_let.bound_value.positional_args
    bindings = _resolved_wcc_linear_bindings(
        root_lets[:group_index]
    )
    bindings.update(
        _resolved_wcc_linear_bindings(
            member_lets[:provider_index]
        )
    )
    resolved_arg = _resolve_wcc_linear_alias(
        provider_arg,
        bindings,
    )
    assert isinstance(resolved_arg, wcc_model.WccLiteralAtom)
    assert resolved_arg.value == "local"


def test_wcc_erases_let_bound_proc_ref_literal_alias(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc literal-alias-leaf () -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () "
            ":returns String))"
        ),
        (
            "(defproc select-literal-alias "
            "((runner ProcRef[() -> String])) -> String "
            ":effects () :lowering inline (runner))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(let* ((runner (proc-ref literal-alias-leaf)) "
            "(alias runner)) "
            "(with-live-providers "
            "((worker (select-literal-alias alias)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker)))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    assert isinstance(body, wcc_model.WccLet)
    group = body.bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    assert "WccCall" not in repr(worker.normalized_body)
    assert repr(worker.normalized_body).count("WccPerform") == 1


def test_wcc_bound_proc_capture_keeps_bind_site_identity_when_shadowed(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc shadow-capture-target ((fixed String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (fixed) "
            ":returns String))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            '(let* ((captured "original") '
            "(bound-worker "
            "(bind-proc (proc-ref shadow-capture-target) "
            ":fixed captured))) "
            '(let* ((captured "shadowed")) '
            "(with-live-providers "
            "((worker (bound-worker)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    lets: list[wcc_model.WccLet] = []
    current = body
    while isinstance(current, wcc_model.WccLet):
        lets.append(current)
        current = current.body
    group_let = next(
        item
        for item in lets
        if isinstance(item.bound_value, wcc_model.WccProviderSupervision)
    )
    group = group_let.bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    provider_let = worker.normalized_body
    while (
        isinstance(provider_let, wcc_model.WccLet)
        and not isinstance(provider_let.bound_value, wcc_model.WccPerform)
    ):
        provider_let = provider_let.body
    assert isinstance(provider_let, wcc_model.WccLet)
    assert isinstance(provider_let.bound_value, wcc_model.WccPerform)
    (provider_arg,) = provider_let.bound_value.positional_args
    assert isinstance(provider_arg, wcc_model.WccNameAtom)
    capture_let = next(
        item for item in lets
        if item.bound_name == provider_arg.name
    )
    assert isinstance(capture_let.bound_value, wcc_model.WccNameAtom)
    assert capture_let.bound_value.name == "captured"
    assert lets.index(capture_let) < max(
        index
        for index, item in enumerate(lets)
        if item.bound_name == "captured"
    )
    group_index = lets.index(group_let)
    resolved_provider_arg = _resolve_wcc_linear_alias(
        provider_arg,
        _resolved_wcc_linear_bindings(lets[:group_index]),
    )
    assert isinstance(
        resolved_provider_arg,
        wcc_model.WccLiteralAtom,
    )
    assert resolved_provider_arg.value == "original"


@pytest.mark.parametrize(
    ("condition_expr", "expected_value"),
    (
        ("true", "selected"),
        ("false", "other"),
    ),
)
def test_wcc_reduces_literal_condition_in_value_specialization(
    tmp_path: Path,
    condition_expr: str,
    expected_value: str,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc conditional-worker ((fixed String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (fixed) :returns String))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(let* ((bound-worker "
            "(bind-proc (proc-ref conditional-worker) "
            ":fixed "
            f'(let* ((choose {condition_expr})) '
            '(if choose "selected" "other"))))) '
            "(with-live-providers "
            "((worker (bound-worker)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker)))"
        ),
    )

    body = wcc_elaborate_module.elaborate_typed_workflow(
        context["typed_workflow"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    assert isinstance(body, wcc_model.WccLet)
    group = body.bound_value
    assert isinstance(group, wcc_model.WccProviderSupervision)
    worker = next(
        member
        for member in group.members
        if member.binding_name == "worker"
    )
    assert f"value='{expected_value}'" in repr(worker.normalized_body)
    assert "WccOpaqueFrontendValue" not in repr(worker.normalized_body)


def test_wcc_rejects_unresolved_condition_in_value_specialization(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc unresolved-conditional-worker "
            "((fixed String)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (fixed) :returns String))"
        ),
        (
            "(defworkflow orchestrate ((flag Bool)) -> String "
            "(let* ((bound-worker "
            "(bind-proc (proc-ref unresolved-conditional-worker) "
            ':fixed (if flag "selected" "other")))) '
            "(with-live-providers "
            "((worker (bound-worker)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker)))"
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        wcc_elaborate_module.elaborate_typed_workflow(
            context["typed_workflow"],
            type_env=context["type_env"],
            workflow_return_types=context["workflow_return_types"],
            procedure_return_types=context["procedure_return_types"],
            resolved_procedures_by_name=context[
                "resolved_procedures_by_name"
            ],
            procedure_type_envs=context["procedure_type_envs"],
            route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
        )

    diagnostics = excinfo.value.diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "provider_supervision_member_ineligible",
        "provider_supervision_member_disqualifying_form",
    ]
    assert _diagnostic_source(context, diagnostics[0]) == "(bound-worker)"
    assert _diagnostic_source(context, diagnostics[1]).startswith(
        '(if flag "selected" "other")'
    )


def test_wcc_rejects_specialized_workflow_ref_member_as_workflow_boundary(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        "(defrecord WorkflowWorkerResult (value String))",
        (
            "(defproc select-workflow-worker "
            "((runner WorkflowRef[String -> WorkflowWorkerResult]) "
            "(input String)) "
            "-> WorkflowWorkerResult "
            ":effects ((calls-workflow runner)) "
            ":lowering inline "
            "(call runner :input input))"
        ),
        (
            "(defworkflow orchestrate () -> WorkflowWorkerResult "
            "(with-live-providers "
            "((worker "
            "(select-workflow-worker "
            '(workflow-ref workflow-worker) "input")) '
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
        (
            "(defworkflow workflow-worker ((input String)) "
            "-> WorkflowWorkerResult "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (input) "
            ":returns WorkflowWorkerResult))"
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        wcc_elaborate_module.elaborate_typed_workflow(
            context["typed_workflow"],
            type_env=context["type_env"],
            workflow_return_types=context["workflow_return_types"],
            procedure_return_types=context["procedure_return_types"],
            resolved_procedures_by_name=context[
                "resolved_procedures_by_name"
            ],
            procedure_type_envs=context["procedure_type_envs"],
            route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
        )

    diagnostics = excinfo.value.diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "provider_supervision_member_ineligible",
        "provider_supervision_member_disqualifying_form",
    ]
    assert _diagnostic_source(context, diagnostics[0]).startswith(
        "(select-workflow-worker "
    )
    assert _diagnostic_source(context, diagnostics[1]).startswith(
        "(call runner "
    )


def test_wcc_rejects_let_bound_workflow_ref_as_workflow_boundary(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        "(defrecord WorkflowAliasResult (value String))",
        (
            "(defproc select-workflow-alias "
            "((runner WorkflowRef[String -> WorkflowAliasResult]) "
            "(input String)) "
            "-> WorkflowAliasResult "
            ":effects ((calls-workflow runner)) "
            ":lowering inline "
            "(call runner :input input))"
        ),
        (
            "(defworkflow orchestrate () -> WorkflowAliasResult "
            "(let* ((runner (workflow-ref workflow-alias-worker))) "
            "(with-live-providers "
            "((worker "
            '(select-workflow-alias runner "input")) '
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker)))"
        ),
        (
            "(defworkflow workflow-alias-worker ((input String)) "
            "-> WorkflowAliasResult "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (input) "
            ":returns WorkflowAliasResult))"
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        wcc_elaborate_module.elaborate_typed_workflow(
            context["typed_workflow"],
            type_env=context["type_env"],
            workflow_return_types=context["workflow_return_types"],
            procedure_return_types=context["procedure_return_types"],
            resolved_procedures_by_name=context[
                "resolved_procedures_by_name"
            ],
            procedure_type_envs=context["procedure_type_envs"],
            route_schema_version=wcc_model.WCC_M4_ROUTE_SCHEMA_VERSION,
        )

    diagnostics = excinfo.value.diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "provider_supervision_member_ineligible",
        "provider_supervision_member_disqualifying_form",
    ]
    assert _diagnostic_source(context, diagnostics[0]).startswith(
        "(select-workflow-alias "
    )
    assert _diagnostic_source(context, diagnostics[1]).startswith(
        "(call runner "
    )


def test_wcc_rejects_nonidentity_supervisor_result_projection(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc projected-supervisor () "
            "-> ProviderSteeringDirective "
            ":effects ((uses-provider providers.supervisor)) "
            ":lowering inline "
            "(let* ((guidance "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns String))) "
            "(variant ProviderSteeringDirective STEER "
            ":guidance guidance)))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () :returns String)) "
            "(supervisor (projected-supervisor) "
            ":observes worker)) "
            "worker))"
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _close_source_level_live_provider_group(context)

    diagnostics = excinfo.value.diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "provider_supervision_member_ineligible",
        "provider_supervision_member_disqualifying_form",
    ]
    assert _diagnostic_source(context, diagnostics[0]) == (
        "(projected-supervisor)"
    )
    assert _diagnostic_source(context, diagnostics[1]).startswith(
        "(variant ProviderSteeringDirective STEER "
    )


def test_wcc_closure_rejects_missing_exact_specialized_callee_key(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc worker-inline () -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () :returns String))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker (worker-inline)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )
    raw_group = _elaborate_live_provider_wcc(context)
    worker_member = raw_group.members[0]
    worker_body = worker_member.normalized_body
    assert isinstance(worker_body, wcc_model.WccLet)
    assert isinstance(worker_body.bound_value, wcc_model.WccCall)
    tampered_call = replace(
        worker_body.bound_value,
        specialized_callee_name="%missing.specialization",
    )
    tampered_group = replace(
        raw_group,
        members=(
            replace(
                worker_member,
                normalized_body=replace(
                    worker_body,
                    bound_value=tampered_call,
                ),
            ),
            *raw_group.members[1:],
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        wcc_elaborate_module.close_wcc_provider_supervision_members(
            tampered_group,
            resolved_procedures_by_name=context[
                "resolved_procedures_by_name"
            ],
            procedure_type_envs=context["procedure_type_envs"],
            type_env=context["type_env"],
            workflow_return_types=context["workflow_return_types"],
            procedure_return_types=context["procedure_return_types"],
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "provider_supervision_member_ineligible"
    assert diagnostic.span == worker_member.metadata.source_span


def test_wcc_recursive_inline_invocations_have_distinct_names_and_node_ids(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc pure-leaf ((value String)) -> String "
            ":effects () :lowering inline "
            "(let* ((copy value)) copy))"
        ),
        (
            "(defproc pure-outer ((value String)) -> String "
            ":effects () :lowering inline "
            "(pure-leaf value))"
        ),
        (
            "(defproc worker-procedure () -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(let* ((left (pure-outer \"left\")) "
            "(right (pure-outer \"right\"))) "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (left right) "
            ":returns String)))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker (worker-procedure)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )

    closed_group = _close_source_level_live_provider_group(context)
    worker = next(
        member
        for member in closed_group.members
        if member.binding_name == "worker"
    )
    structural_nodes = []
    current = worker.normalized_body
    while isinstance(current, wcc_model.WccLet):
        structural_nodes.append(current)
        current = current.body
    assert isinstance(current, wcc_model.WccHalt)
    structural_nodes.append(current)

    bound_names = [
        node.bound_name
        for node in structural_nodes
        if isinstance(node, wcc_model.WccLet)
    ]
    assert len(bound_names) == len(set(bound_names))
    node_ids = [node.metadata.node_id for node in structural_nodes]
    assert len(node_ids) == len(set(node_ids))

    leaf_copies = [
        node
        for node in structural_nodes
        if isinstance(node, wcc_model.WccLet)
        and node.bound_name.endswith("__copy")
    ]
    assert len(leaf_copies) == 2
    assert (
        leaf_copies[0].metadata.source_span
        == leaf_copies[1].metadata.source_span
    )


def test_wcc_rejects_authored_auto_lowering_live_provider_member_at_call_site(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc auto-worker () -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering auto "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () :returns String))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker (auto-worker)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )
    auto_worker = context["resolved_procedures_by_name"]["auto-worker"]
    assert auto_worker.definition.requested_lowering_mode.value == "auto"
    assert auto_worker.resolved_lowering_mode.value == "inline"
    raw_group = _elaborate_live_provider_wcc(context)
    close_members = getattr(
        wcc_elaborate_module,
        "close_wcc_provider_supervision_members",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        close_members(
            raw_group,
            resolved_procedures_by_name=context[
                "resolved_procedures_by_name"
            ],
            procedure_type_envs=context["procedure_type_envs"],
            type_env=context["type_env"],
            procedure_return_types=context["procedure_return_types"],
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "provider_supervision_member_ineligible"
    assert diagnostic.span.start.path == str(context["path"])
    assert (
        context["source"][
            diagnostic.span.start.offset : diagnostic.span.end.offset
        ]
        == "(auto-worker)"
    )


def _close_source_level_live_provider_group(context):
    raw_group = _elaborate_live_provider_wcc(context)
    return wcc_elaborate_module.close_wcc_provider_supervision_members(
        raw_group,
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
    )


def _diagnostic_source(context, diagnostic) -> str:
    return context["source"][
        diagnostic.span.start.offset : diagnostic.span.end.offset
    ]


def test_wcc_rejects_authored_workflow_call_live_provider_member_at_call_site(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker (call worker-workflow)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
        (
            "(defworkflow worker-workflow () -> String "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () :returns String))"
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _close_source_level_live_provider_group(context)

    diagnostics = excinfo.value.diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "provider_supervision_member_ineligible"
    ]
    assert diagnostics[0].span.start.path == str(context["path"])
    assert _diagnostic_source(context, diagnostics[0]) == (
        "(call worker-workflow)"
    )


def test_wcc_rejects_explicit_private_workflow_provider_member_at_call_site(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        "(defrecord WorkerResult (value String))",
        (
            "(defproc private-worker () -> WorkerResult "
            ":effects ((uses-provider providers.worker)) "
            ":lowering private-workflow "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () :returns WorkerResult))"
        ),
        (
            "(defworkflow orchestrate () -> WorkerResult "
            "(with-live-providers "
            "((worker (private-worker)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )
    private_worker = context["resolved_procedures_by_name"][
        "private-worker"
    ]
    assert private_worker.resolved_lowering_mode.value == "private-workflow"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _close_source_level_live_provider_group(context)

    diagnostics = excinfo.value.diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "provider_supervision_member_ineligible",
        "provider_supervision_member_disqualifying_form",
    ]
    assert _diagnostic_source(context, diagnostics[0]) == "(private-worker)"
    assert _diagnostic_source(context, diagnostics[1]).startswith(
        "(defproc private-worker "
    )


def test_wcc_rejects_control_bearing_inline_provider_member_at_call_site(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc branching-worker ((ready Bool)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(if ready "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () :returns String) "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () :returns String)))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker (branching-worker true)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _close_source_level_live_provider_group(context)

    diagnostics = excinfo.value.diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "provider_supervision_member_ineligible",
        "provider_supervision_member_disqualifying_form",
    ]
    assert _diagnostic_source(context, diagnostics[0]) == (
        "(branching-worker true)"
    )
    assert _diagnostic_source(context, diagnostics[1]).startswith(
        "(if ready "
    )


def test_wcc_rejects_case_bearing_inline_provider_member_at_call_site(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc case-worker "
            "((directive ProviderSteeringDirective)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(match directive "
            "((CONTINUE continued) "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () :returns String)) "
            "((STEER steered) "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (steered.guidance) "
            ":returns String))))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker "
            "(case-worker "
            "(variant ProviderSteeringDirective CONTINUE))) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _close_source_level_live_provider_group(context)

    diagnostics = excinfo.value.diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "provider_supervision_member_ineligible",
        "provider_supervision_member_disqualifying_form",
    ]
    assert _diagnostic_source(context, diagnostics[0]).startswith(
        "(case-worker "
    )
    assert _diagnostic_source(context, diagnostics[1]).startswith(
        "(match directive "
    )


def test_wcc_rejects_pure_if_feeding_inline_provider_member_at_call_site(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc branching-input-worker ((ready Bool)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(let* ((prompt-input (if ready \"ready\" \"not-ready\"))) "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (prompt-input) "
            ":returns String)))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker (branching-input-worker true)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _close_source_level_live_provider_group(context)

    diagnostics = excinfo.value.diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "provider_supervision_member_ineligible",
        "provider_supervision_member_disqualifying_form",
    ]
    assert _diagnostic_source(context, diagnostics[0]) == (
        "(branching-input-worker true)"
    )
    assert _diagnostic_source(context, diagnostics[1]).startswith(
        '(if ready "ready" "not-ready")'
    )


def test_wcc_rejects_nested_pure_if_feeding_inline_provider_member(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        "(defrecord PromptInput (value String))",
        (
            "(defproc nested-branching-worker ((ready Bool)) -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(let* ((prompt-input "
            "(record PromptInput "
            ":value (if ready \"ready\" \"not-ready\")))) "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (prompt-input) "
            ":returns String)))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker (nested-branching-worker true)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _close_source_level_live_provider_group(context)

    diagnostics = excinfo.value.diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "provider_supervision_member_ineligible",
        "provider_supervision_member_disqualifying_form",
    ]
    assert _diagnostic_source(context, diagnostics[0]) == (
        "(nested-branching-worker true)"
    )
    assert _diagnostic_source(context, diagnostics[1]).startswith(
        '(if ready "ready" "not-ready")'
    )


def test_wcc_rejects_loop_bearing_inline_provider_member_at_call_site(
    tmp_path: Path,
) -> None:
    context = _typed_live_provider_wcc_context(
        tmp_path,
        (
            "(defproc looping-worker () -> String "
            ":effects ((uses-provider providers.worker)) "
            ":lowering inline "
            "(let* ((result "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () :returns String))) "
            "(loop/recur :max 1 :state result "
            "(fn (state) (done state)))))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker (looping-worker)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _close_source_level_live_provider_group(context)

    diagnostics = excinfo.value.diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "provider_supervision_member_ineligible",
        "provider_supervision_member_disqualifying_form",
    ]
    assert _diagnostic_source(context, diagnostics[0]) == "(looping-worker)"
    assert _diagnostic_source(context, diagnostics[1]).startswith(
        "(loop/recur "
    )


def test_recursive_live_provider_member_is_rejected_by_procedure_cycle_gate(
    tmp_path: Path,
) -> None:
    recursive_procedure = (
        "(defproc recursive-worker () -> String "
        ":effects ((uses-provider providers.worker)) "
        ":lowering inline "
        "(recursive-worker))"
    )
    orchestrate_workflow = (
        "(defworkflow orchestrate () -> String "
        "(with-live-providers "
        "((worker (recursive-worker)) "
        "(supervisor "
        "(provider-result providers.supervisor "
        ":prompt prompts.supervisor :inputs () "
        ":returns ProviderSteeringDirective) "
        ":observes worker)) "
        "worker))"
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typed_live_provider_wcc_context(
            tmp_path,
            recursive_procedure,
            orchestrate_workflow,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "proc_lowering_cycle"
    source = _module_source(
        "2.16",
        recursive_procedure,
        orchestrate_workflow,
    )
    assert (
        source[diagnostic.span.start.offset : diagnostic.span.end.offset]
        == "(recursive-worker)"
    )
