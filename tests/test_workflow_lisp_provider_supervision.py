from pathlib import Path

import pytest

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
from orchestrator.workflow_lisp.procedures import elaborate_procedure_definitions
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.result_guidance import ResultGuidance
from orchestrator.workflow_lisp.syntax import SyntaxNode, build_syntax_module
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    PrimitiveTypeRef,
    UnionTypeRef,
    type_refs_compatible,
)
from orchestrator.workflow_lisp.typecheck import typecheck_expression


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
