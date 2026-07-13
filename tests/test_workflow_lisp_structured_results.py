import ast
import importlib
import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
    compile_stage3_module,
    compile_stage1_module,
)
from orchestrator.workflow_lisp.contracts import (
    derive_structured_result_contract,
    derive_workflow_signature_contracts,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    serialize_diagnostic,
)
from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.reader import read_sexpr_file, read_sexpr_text
from orchestrator.workflow_lisp import result_guidance as result_guidance_module
from orchestrator.workflow_lisp.result_guidance import ResultGuidance, ReturnSpec
from orchestrator.workflow_lisp.syntax import SyntaxNode, WorkflowLispSyntaxModule, build_syntax_module
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    PathTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    UnionTypeRef,
    WorkflowRefTypeRef,
)
from orchestrator.workflow_lisp.typecheck import typecheck_expression
from orchestrator.workflow_lisp.workflows import (
    CertifiedAdapterBinding,
    ExternEnvironment,
    ExternalToolBinding,
    PromptExtern,
    ProviderExtern,
    WorkflowSignature,
    _flattened_boundary_contracts,
    _normalize_boundary_contract_definition,
    build_command_boundary_environment,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
TYPE_FIXTURE = FIXTURES / "valid" / "type_definitions.orc"
PHASE_FIXTURE = FIXTURES / "valid" / "neurips_implementation_attempt.orc"
VALID_CERTIFIED_ADAPTER_FIXTURE = FIXTURES / "valid" / "certified_adapter_call.orc"
NATIVE_RETURNS_FIXTURE = FIXTURES / "valid" / "native_transportable_returns.orc"
NATIVE_RETURNS_INVALID_FIXTURE = FIXTURES / "invalid" / "native_return_type_not_transportable.orc"

NATIVE_RETURN_TYPE_NAMES = (
    "Bool",
    "Int",
    "Float",
    "String",
    "BlockerClass",
    "WorkReport",
    "Optional[Bool]",
    "List[Int]",
    "Map[String, Float]",
)


def _build_syntax_module(path: Path) -> WorkflowLispSyntaxModule:
    return build_syntax_module(read_sexpr_file(path))


def _build_type_env() -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(compile_stage1_module(TYPE_FIXTURE))


def _compile_definition_module(path: Path):
    syntax_module = _build_syntax_module(path)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def test_elaborate_record_and_union_payload_field_guidance(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "annotated_fields.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defrecord ReviewResult",
                '    (approved Bool :description "No blockers remain." :example true))',
                "  (defunion Decision",
                "    (Approved",
                '      (approved Bool :format-hint "JSON boolean." :example true))))',
            ]
        ),
    )

    module = _compile_definition_module(path)
    record_field = module.definitions[0].fields[0]
    union_field = module.definitions[1].variants[0].fields[0]

    assert record_field.guidance.description == "No blockers remain."
    assert record_field.guidance.example_expr.datum.value is True
    assert union_field.guidance.format_hint == "JSON boolean."
    assert union_field.guidance.example_expr.datum.value is True


def test_schema_include_preserves_field_guidance(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "schema_include_guidance.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defschema ReviewFields",
                '    (approved Bool :description "No blockers remain." :example true))',
                "  (defrecord ReviewResult",
                "    (:include ReviewFields)))",
            ]
        ),
    )

    module = _compile_definition_module(path)
    field = module.definitions[0].fields[0]

    assert field.guidance.description == "No blockers remain."
    assert field.guidance.example_expr.datum.value is True


def test_schema_include_guidance_does_not_override_duplicate_local_field(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "schema_include_guidance_duplicate.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defschema ReviewFields",
                '    (approved Bool :description "Included guidance."))',
                "  (defrecord ReviewResult",
                "    (:include ReviewFields)",
                '    (approved Bool :description "Local guidance.")))',
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_definition_module(path)

    assert excinfo.value.diagnostics[0].code == "record_field_duplicate"


@pytest.mark.parametrize(
    "field_source",
    [
        '(approved Bool :unknown "no")',
        '(approved Bool :description "one" :description "two")',
        '(approved Bool :description "")',
        '(approved Bool :format-hint "")',
    ],
)
def test_elaborate_field_rejects_invalid_guidance(tmp_path: Path, field_source: str) -> None:
    path = _write_module(
        tmp_path / "invalid_annotated_field.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                f"  (defrecord ReviewResult {field_source}))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError):
        _compile_definition_module(path)


def test_elaborate_rejects_enum_member_and_union_variant_guidance(tmp_path: Path) -> None:
    enum_path = _write_module(
        tmp_path / "annotated_enum_member.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                '  (defenum Decision (APPROVE :description "Approve.")))',
            ]
        ),
    )
    with pytest.raises(LispFrontendCompileError):
        _compile_definition_module(enum_path)

    union_path = _write_module(
        tmp_path / "annotated_union_variant.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defunion Decision",
                '    (Approved :description "Approve." (approved Bool))))',
            ]
        ),
    )
    with pytest.raises(LispFrontendCompileError):
        _compile_definition_module(union_path)


def _write_module(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _expression_syntax(source: str) -> SyntaxNode:
    parse_tree = read_sexpr_text(source, source_path="inline_structured_result.orc")
    assert len(parse_tree.items) == 1
    datum = parse_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_structured_result.orc",
        form_path=("workflow-lisp", "structured-result-test"),
    )


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


@pytest.mark.parametrize(
    ("type_name", "source", "expected"),
    [
        ("Bool", "true", True),
        ("Int", "(+ 1 2)", 3),
        ("Float", "0.91", 0.91),
        ("BlockerClass", "BlockerClass.missing_resource", "missing_resource"),
        ("Optional[Bool]", "true", True),
        ("WorkReport", '"artifacts/work/example.md"', "artifacts/work/example.md"),
        (
            "ChecksResult",
            '(record ChecksResult :status "ok" :report "artifacts/work/checks.md")',
            {"status": "ok", "report": "artifacts/work/checks.md"},
        ),
        (
            "ImplementationState",
            "(variant ImplementationState BLOCKED "
            ':progress_report "artifacts/work/progress.md" '
            ":blocker_class BlockerClass.missing_resource)",
            {
                "variant": "BLOCKED",
                "progress_report": "artifacts/work/progress.md",
                "blocker_class": "missing_resource",
            },
        ),
    ],
)
def test_guidance_example_validates_source_constant_families(
    type_name: str,
    source: str,
    expected: object,
) -> None:
    type_env = _build_type_env()
    syntax = _expression_syntax(source)
    type_ref = type_env.resolve_type(type_name, span=syntax.span, form_path=syntax.form_path)

    assert result_guidance_module.validate_result_guidance_example(
        ResultGuidance(example_expr=syntax),
        expected_type=type_ref,
        type_env=type_env,
    ) == expected


@pytest.mark.parametrize(
    ("type_name", "value", "expected"),
    [
        ("Optional[Bool]", None, None),
        ("List[Int]", [1, 2], [1, 2]),
        ("Map[String, Float]", {"clarity": 0.87}, {"clarity": 0.87}),
    ],
)
def test_guidance_example_validates_json_native_collection_constants(
    type_name: str,
    value: object,
    expected: object,
) -> None:
    type_env = _build_type_env()
    syntax = _expression_syntax("true")
    type_ref = type_env.resolve_type(type_name, span=syntax.span, form_path=syntax.form_path)

    assert result_guidance_module.validate_typed_guidance_constant(
        value,
        expected_type=type_ref,
        type_env=type_env,
        example_node=syntax,
    ) == expected


def test_guidance_path_example_does_not_require_existing_target(tmp_path: Path) -> None:
    type_env = _build_type_env()
    syntax = _expression_syntax('"artifacts/work/not-created.md"')
    path_type = type_env.resolve_type("WorkReport", span=syntax.span, form_path=syntax.form_path)

    assert not (tmp_path / "artifacts/work/not-created.md").exists()
    assert result_guidance_module.validate_result_guidance_example(
        ResultGuidance(example_expr=syntax),
        expected_type=path_type,
        type_env=type_env,
        workspace=tmp_path,
    ) == "artifacts/work/not-created.md"


def test_guidance_example_type_mismatch_has_stable_source_mapped_diagnostic(tmp_path: Path) -> None:
    path = FIXTURES / "invalid" / "result_guidance_example_type_mismatch.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False, workspace_root=tmp_path)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "result_guidance_example_type_mismatch"
    assert diagnostic.message == "result guidance example does not match declared type `Bool`"
    assert diagnostic.span.start.path.endswith("result_guidance_example_type_mismatch.orc")
    assert diagnostic.span.start.line == 5


def test_guidance_example_effect_has_stable_source_mapped_diagnostic(tmp_path: Path) -> None:
    path = FIXTURES / "invalid" / "result_guidance_example_effectful.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False, workspace_root=tmp_path)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "result_guidance_example_not_constant"
    assert diagnostic.message == "result guidance example must be an effect-free compile-time constant"
    assert diagnostic.span.start.path.endswith("result_guidance_example_effectful.orc")
    assert diagnostic.span.start.line == 6


def test_guidance_example_rejects_runtime_binding_with_same_constant_diagnostic(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "result_guidance_example_binding.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defworkflow binding-example ((input Bool))",
                "    -> (result Bool :example input)",
                "    input))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False, workspace_root=tmp_path)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "result_guidance_example_not_constant"
    assert diagnostic.message == "result guidance example must be an effect-free compile-time constant"
    assert diagnostic.span.start.line == 5


def test_guidance_example_validates_annotated_record_fields_during_compile(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "result_guidance_field_mismatch.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                '  (defrecord ReviewResult (approved Bool :example "yes"))',
                "  (defworkflow review () -> Bool true))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False, workspace_root=tmp_path)

    assert excinfo.value.diagnostics[0].code == "result_guidance_example_type_mismatch"


def test_guidance_example_valid_module_compiles_through_stage3(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "result_guidance_examples_valid.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defrecord ReviewResult",
                '    (approved Bool :example true)',
                '    (score Float :example 0.91))',
                "  (defworkflow review ()",
                '    -> (result Bool :description "No blockers." :example (not false))',
                "    true))",
            ]
        ),
    )

    result = compile_stage3_module(path, validate_shared=False, workspace_root=tmp_path)

    assert result.typed_workflows[0].signature.return_type_ref == PrimitiveTypeRef(name="Bool")


def test_result_guidance_is_neutral_to_return_identity_and_runtime_validation() -> None:
    syntax = _expression_syntax("true")
    guided = ReturnSpec(
        type_name="Bool",
        guidance=ResultGuidance(description="No blockers.", example_expr=syntax),
        span=syntax.span,
    )
    plain = ReturnSpec(type_name="Bool", guidance=None, span=syntax.span)

    assert guided == plain
    assert hash(guided) == hash(plain)
    assert {guided: "same"}[plain] == "same"

    type_env = _build_type_env()
    bool_type = type_env.resolve_type("Bool", span=syntax.span, form_path=syntax.form_path)
    contract = derive_structured_result_contract(
        bool_type,
        workflow_name="identity-neutral",
        step_id="identity-neutral__result",
    )
    field_spec = dict(contract.payload["fields"][0])
    from orchestrator.contracts.output_contract import OutputContractError, validate_contract_value

    assert validate_contract_value(True, field_spec, workspace=Path.cwd()) is True
    with pytest.raises(OutputContractError):
        validate_contract_value("not-a-bool", field_spec, workspace=Path.cwd())


def test_field_guidance_is_neutral_to_type_specialization_and_contract_fingerprint() -> None:
    from orchestrator.workflow_lisp.contracts import _strip_contract_provenance_for_fingerprint
    from orchestrator.workflow_lisp.definitions import RecordDef, RecordField
    from orchestrator.workflow_lisp.procedures import parametric_specialization_name
    from orchestrator.workflow_lisp.type_env import type_refs_compatible

    syntax = _expression_syntax("true")
    plain_field = RecordField(name="approved", type_name="Bool", span=syntax.span)
    guided_field = RecordField(
        name="approved",
        type_name="Bool",
        span=syntax.span,
        guidance=ResultGuidance(description="No blockers.", example_expr=syntax),
    )
    plain_type = RecordTypeRef(
        name="ReviewResult",
        definition=RecordDef(name="ReviewResult", fields=(plain_field,), span=syntax.span),
        field_types={"approved": PrimitiveTypeRef(name="Bool")},
    )
    guided_type = RecordTypeRef(
        name="ReviewResult",
        definition=RecordDef(name="ReviewResult", fields=(guided_field,), span=syntax.span),
        field_types={"approved": PrimitiveTypeRef(name="Bool")},
    )

    assert plain_field == guided_field
    assert type_refs_compatible(plain_type, guided_type)
    assert parametric_specialization_name("identity", {"T": plain_type}) == parametric_specialization_name(
        "identity", {"T": guided_type}
    )
    plain_contract = derive_structured_result_contract(
        plain_type,
        workflow_name="identity-neutral",
        step_id="identity-neutral__record",
    )
    guided_contract = derive_structured_result_contract(
        guided_type,
        workflow_name="identity-neutral",
        step_id="identity-neutral__record",
    )
    assert _strip_contract_provenance_for_fingerprint(
        plain_contract.payload
    ) == _strip_contract_provenance_for_fingerprint(
        guided_contract.payload
    )


def test_guidance_example_validates_effect_boundary_occurrence(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "result_guidance_effect_boundary_mismatch.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defworkflow review () -> Bool",
                "    (provider-result providers.review",
                "      :prompt prompts.review",
                "      :inputs ()",
                '      :returns (result Bool :example "yes"))))',
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            provider_externs={"providers.review": "test-provider"},
            prompt_externs={"prompts.review": "prompts/review.md"},
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "result_guidance_example_type_mismatch"


def _strip_contract_source_metadata(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _strip_contract_source_metadata(item)
            for key, item in value.items()
            if key not in {
                "source_map_subject",
                "source_map_subjects_by_variant",
            }
        }
    if isinstance(value, list):
        return [_strip_contract_source_metadata(item) for item in value]
    return value


def _typecheck_top_level_names() -> set[str]:
    source_path = Path(importlib.import_module("orchestrator.workflow_lisp.typecheck").__file__)
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in module.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef))
    }


def test_effect_owner_split_moves_command_and_provider_typecheck_out_of_facade() -> None:
    package_dir = Path(importlib.import_module("orchestrator.workflow_lisp").__file__).resolve().parent
    dispatch_source = (package_dir / "typecheck_dispatch.py").read_text(encoding="utf-8")
    top_level_names = _typecheck_top_level_names()

    assert (package_dir / "typecheck_effects.py").is_file()
    assert "_typecheck_expected_extern_operand" not in top_level_names
    assert "_validate_command_argv" not in top_level_names
    assert "_validate_semantic_command_adapter_usage" not in top_level_names
    assert "_is_macro_introduced_effect" not in top_level_names
    assert "if isinstance(expr, ProviderResultExpr):" not in dispatch_source
    assert "if isinstance(expr, CommandResultExpr):" not in dispatch_source
    assert "typecheck_provider_result_expr(" in dispatch_source
    assert "typecheck_command_result_expr(" in dispatch_source
    assert "def _validate_command_argv(" not in dispatch_source
    assert "def _is_macro_introduced_effect(" not in dispatch_source


def _typecheck_fixture(path: Path, *, types_path: Path = TYPE_FIXTURE, **typecheck_kwargs):
    module = _compile_definition_module(types_path)
    type_env = FrontendTypeEnvironment.from_module(module)
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    return typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=build_workflow_catalog(
            module,
            workflow_defs,
            type_env,
        ),
        **typecheck_kwargs,
    )


def _promoted_adapter_command_boundaries():
    return _parse_command_boundaries_manifest(
        {
            "normalize_result": {
                "kind": "certified_adapter",
                "stable_command": ["python", "scripts/normalize_result.py"],
                "input_contract": {"type": "object"},
                "output_type_name": "ImplementationSummary",
                "effects": ["structured_result"],
                "path_safety": {"kind": "workspace_relpath"},
                "source_map_behavior": "step",
                "fixture_ids": ["normalize_result_ok"],
                "negative_fixture_ids": ["normalize_result_bad"],
                "behavior_class": "structured_result",
                "input_signature": [
                    {
                        "name": "execution_report",
                        "type_name": "WorkReport",
                        "required": True,
                        "transport_key": "execution_report",
                    },
                    {
                        "name": "review_report",
                        "type_name": "WorkReport",
                        "required": True,
                        "transport_key": "review_report",
                    },
                ],
                "artifact_contracts": ["implementation_summary_report"],
                "state_writes": [],
                "error_codes": ["normalize_result_invalid_payload"],
                "owner_module": "std/phase",
                "replacement_path": None,
                "invocation_protocol": "json_object_positional_arg",
            }
        },
        manifest_path=None,
    )


def test_typecheck_workflow_definitions_validates_same_file_call_signatures() -> None:
    from orchestrator.workflow_lisp import (
        CertifiedAdapterBinding,
        CommandBoundaryEnvironment,
        ExternEnvironment,
        ExternalToolBinding,
        PromptExtern,
        ProviderExtern,
    )

    typed_workflows = _typecheck_fixture(
        FIXTURES / "valid" / "structured_results.orc",
        types_path=FIXTURES / "valid" / "structured_results.orc",
        extern_environment=ExternEnvironment(
            bindings_by_name={
                "providers.execute": ProviderExtern(
                    name="providers.execute",
                    provider_id="test-provider",
                ),
                "prompts.implementation.execute": PromptExtern(
                    name="prompts.implementation.execute",
                    asset_file="prompts/implementation/execute.md",
                ),
            }
        ),
        command_boundary_environment=CommandBoundaryEnvironment(
            bindings_by_name={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                ),
                "normalize_result": CertifiedAdapterBinding(
                    name="normalize_result",
                    stable_command=("python", "scripts/normalize_result.py"),
                    input_contract={"type": "object"},
                    output_type_name="ImplementationSummary",
                    effects=("structured_result",),
                    path_safety={"kind": "workspace_relpath"},
                    source_map_behavior="step",
                    fixture_ids=("normalize_result_ok",),
                    negative_fixture_ids=("normalize_result_bad",),
                ),
            }
        ),
    )

    assert [typed_workflow.definition.name for typed_workflow in typed_workflows] == [
        "command_checks",
        "provider_attempt",
        "orchestrate",
    ]
    assert isinstance(typed_workflows[0].signature.return_type_ref, RecordTypeRef)
    assert isinstance(typed_workflows[1].signature.return_type_ref, RecordTypeRef)
    assert typed_workflows[2].typed_body.type_ref == typed_workflows[1].signature.return_type_ref


def test_macro_emitted_command_result_respects_existing_command_boundary_rules() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            FIXTURES / "valid" / "macro_workflow_alias.orc",
            validate_shared=False,
        )

    assert excinfo.value.diagnostics[0].code in {
        "command_adapter_missing_contract",
        "command_result_argv_invalid",
        "provider_result_provider_invalid",
    }


def test_typecheck_workflow_definitions_rejects_unknown_callees(tmp_path: Path) -> None:
    missing_callee = _write_module(
        tmp_path / "unknown_callee_stage3.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow missing-helper",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (call helper",
                "      :input input",
                "      :report_path report_path)))",
            ]
        ),
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(missing_callee)

    _assert_diagnostic_code(excinfo, "workflow_call_unknown")


def test_derive_structured_result_contract_for_phase_translation_union_keeps_variant_fields() -> None:
    module = _compile_definition_module(PHASE_FIXTURE)
    type_env = FrontendTypeEnvironment.from_module(module)
    implementation_attempt = type_env.resolve_type(
        "ImplementationAttempt",
        span=_build_syntax_module(PHASE_FIXTURE).span,
        form_path=("workflow-lisp", "defunion", "ImplementationAttempt"),
    )

    assert isinstance(implementation_attempt, UnionTypeRef)
    contract = derive_structured_result_contract(
        implementation_attempt,
        workflow_name="run-implementation-attempt",
        step_id="run-implementation-attempt__attempt",
        span=_build_syntax_module(PHASE_FIXTURE).span,
        form_path=("workflow-lisp", "defworkflow", "run-implementation-attempt"),
    )

    assert contract.contract_kind == "variant_output"
    assert contract.payload["discriminant"]["name"] == "variant"
    assert _strip_contract_source_metadata(contract.payload["shared_fields"]) == [
        {
            "name": "implementation_state",
            "json_pointer": "/implementation_state",
            "type": "enum",
            "allowed": ["COMPLETED", "BLOCKED"],
        }
    ]
    assert _strip_contract_source_metadata(
        contract.payload["variants"]["COMPLETED"]["fields"]
    ) == [
        {
            "name": "execution_report_path",
            "json_pointer": "/execution_report_path",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
    ]
    assert _strip_contract_source_metadata(
        contract.payload["variants"]["BLOCKED"]["fields"]
    ) == [
        {
            "name": "progress_report_path",
            "json_pointer": "/progress_report_path",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
        {
            "name": "blocker_class",
            "json_pointer": "/blocker_class",
            "type": "enum",
            "allowed": [
                "missing_resource",
                "unavailable_hardware",
                "roadmap_conflict",
                "external_dependency_outside_authority",
                "user_decision_required",
                "unrecoverable_after_fix_attempt",
            ],
        },
    ]


def test_derive_structured_result_contract_adds_stable_field_subjects() -> None:
    module = _compile_definition_module(PHASE_FIXTURE)
    type_env = FrontendTypeEnvironment.from_module(module)
    implementation_attempt = type_env.resolve_type(
        "ImplementationAttempt",
        span=_build_syntax_module(PHASE_FIXTURE).span,
        form_path=("workflow-lisp", "defunion", "ImplementationAttempt"),
    )

    assert isinstance(implementation_attempt, UnionTypeRef)
    contract = derive_structured_result_contract(
        implementation_attempt,
        workflow_name="demo/module::entry",
        step_id="execute",
        span=_build_syntax_module(PHASE_FIXTURE).span,
        form_path=("workflow-lisp", "defworkflow", "entry"),
    )

    completed = contract.payload["variants"]["COMPLETED"]["fields"]
    blocked = contract.payload["variants"]["BLOCKED"]["fields"]
    assert completed[0]["source_map_subject"] == {
        "subject_kind": "variant_output_field",
        "subject_name": "execute::ImplementationAttempt::COMPLETED::execution_report_path",
        "workflow_name": "demo/module::entry",
    }
    assert blocked[0]["source_map_subject"]["subject_name"].startswith(
        "execute::ImplementationAttempt::BLOCKED::"
    )
    assert tuple(origin.subject_ref.subject_name for origin in contract.field_origins) == (
        "execute::ImplementationAttempt::COMPLETED::implementation_state",
        "execute::ImplementationAttempt::COMPLETED::execution_report_path",
        "execute::ImplementationAttempt::BLOCKED::implementation_state",
        "execute::ImplementationAttempt::BLOCKED::progress_report_path",
        "execute::ImplementationAttempt::BLOCKED::blocker_class",
    )


def test_derive_structured_result_contract_adds_distinct_shared_field_subjects(
    tmp_path: Path,
) -> None:
    types_path = _write_module(
        tmp_path / "shared_nested_union_fields.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord ReportEnvelope",
                "    (path String))",
                "  (defunion Decision",
                "    (ACCEPTED",
                "      (report String)",
                "      (details ReportEnvelope))",
                "    (REJECTED",
                "      (report String)",
                "      (details ReportEnvelope))))",
            ]
        ),
    )
    syntax_module = _build_syntax_module(types_path)
    type_env = FrontendTypeEnvironment.from_module(compile_stage1_module(types_path))
    decision = type_env.resolve_type(
        "Decision",
        span=syntax_module.span,
        form_path=("workflow-lisp", "defunion", "Decision"),
    )

    assert isinstance(decision, UnionTypeRef)
    contract = derive_structured_result_contract(
        decision,
        workflow_name="demo/module::entry",
        step_id="execute",
        span=syntax_module.span,
        form_path=("workflow-lisp", "defworkflow", "entry"),
    )

    shared_by_name = {
        field["name"]: field
        for field in contract.payload["shared_fields"]
    }
    shared = shared_by_name["report"]
    assert "source_map_subject" not in shared
    subjects = shared["source_map_subjects_by_variant"]
    assert set(subjects) == {"ACCEPTED", "REJECTED"}
    assert subjects["ACCEPTED"] != subjects["REJECTED"]
    assert subjects["ACCEPTED"]["subject_name"] == (
        "execute::Decision::ACCEPTED::report"
    )
    assert subjects["REJECTED"]["subject_name"] == (
        "execute::Decision::REJECTED::report"
    )

    nested_origins_by_variant = {
        origin.subject_ref.subject_name.split("::")[-2]: origin
        for origin in contract.field_origins
        if origin.subject_ref.subject_name.endswith("::details__path")
    }
    for variant in decision.definition.variants:
        nested_field = next(field for field in variant.fields if field.name == "details")
        origin = nested_origins_by_variant[variant.name]
        assert origin.span == nested_field.span
        assert origin.form_path == (
            "workflow-lisp",
            "defunion",
            "Decision",
            variant.name,
            "details",
        )


def test_typecheck_workflow_definitions_rejects_return_type_mismatches(tmp_path: Path) -> None:
    mismatch_path = _write_module(
        tmp_path / "return_type_mismatch.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow mismatch",
                "    ((report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" report_path)',
                "      :returns ChecksResult)))",
            ],
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(mismatch_path)

    _assert_diagnostic_code(excinfo, "return_type_mismatch")


def test_typecheck_provider_result_requires_record_or_union_return_types(tmp_path: Path) -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(provider-result providers.execute "
            ":prompt prompts.implementation.execute "
            ":inputs (input report_path) "
            ":returns Json)"
        ),
        bound_names=frozenset({"providers.execute", "prompts.implementation.execute", "input", "report_path"}),
    )
    with pytest.raises(LispFrontendCompileError) as bad_return:
        typecheck_expression(
            expr,
            type_env=_build_type_env(),
            value_env={
                "providers.execute": PrimitiveTypeRef(name="Provider"),
                "prompts.implementation.execute": PrimitiveTypeRef(name="Prompt"),
                "input": _build_type_env().resolve_type(
                    "ChecksResult",
                    span=expr.span,
                    form_path=expr.form_path,
                ),
                "report_path": _build_type_env().resolve_type(
                    "WorkReport",
                    span=expr.span,
                    form_path=expr.form_path,
                ),
            },
        )
    _assert_diagnostic_code(bad_return, "provider_result_return_type_invalid")

    invalid_provider_path = _write_module(
        tmp_path / "provider_operand_type_invalid.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow provider-attempt",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (provider-result input",
                "      :prompt report_path",
                "      :inputs (input report_path)",
                "      :returns ImplementationState)))",
            ],
        ),
    )

    with pytest.raises(LispFrontendCompileError) as invalid_operands:
        _typecheck_fixture(invalid_provider_path)

    assert invalid_operands.value.diagnostics[0].code in {"type_mismatch", "provider_result_provider_invalid"}


def test_typecheck_provider_result_rejects_missing_or_mismatched_externs(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp import ExternEnvironment, PromptExtern, ProviderExtern

    with pytest.raises(LispFrontendCompileError) as missing_externs:
        _typecheck_fixture(
            FIXTURES / "valid" / "structured_results.orc",
            types_path=FIXTURES / "valid" / "structured_results.orc",
            extern_environment=ExternEnvironment(bindings_by_name={}),
        )
    assert missing_externs.value.diagnostics[0].code == "provider_result_provider_invalid"

    missing_prompt_path = _write_module(
        tmp_path / "missing_prompt_extern.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow provider-attempt",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (input report_path)",
                "               :returns ImplementationState)))",
                "      (match attempt",
                "        ((COMPLETED completed)",
                '         (record ImplementationSummary :status "completed" :report completed.execution_report))',
                "        ((BLOCKED blocked)",
                '         (record ImplementationSummary :status "blocked" :report blocked.progress_report))))))',
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as missing_prompt:
        _typecheck_fixture(
            missing_prompt_path,
            extern_environment=ExternEnvironment(
                bindings_by_name={
                    "providers.execute": ProviderExtern(
                        name="providers.execute",
                        provider_id="test-provider",
                    ),
                }
            ),
        )
    assert missing_prompt.value.diagnostics[0].code == "provider_result_prompt_invalid"

    mismatch_path = _write_module(
        tmp_path / "mismatched_externs.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow provider-attempt",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (input report_path)",
                "               :returns ImplementationState)))",
                    "      (match attempt",
                    "        ((COMPLETED completed)",
                    '         (record ImplementationSummary :status "completed" :report completed.execution_report))',
                    "        ((BLOCKED blocked)",
                    '         (record ImplementationSummary :status "blocked" :report blocked.progress_report))))))',
                ]
            ),
        )

    with pytest.raises(LispFrontendCompileError) as mismatched_externs:
        _typecheck_fixture(
            mismatch_path,
            extern_environment=ExternEnvironment(
                bindings_by_name={
                    "providers.execute": PromptExtern(
                        name="providers.execute",
                        asset_file="prompts/implementation/execute.md",
                    ),
                    "prompts.implementation.execute": ProviderExtern(
                        name="prompts.implementation.execute",
                        provider_id="test-provider",
                    ),
                }
            ),
        )
    assert mismatched_externs.value.diagnostics[0].code == "provider_result_provider_invalid"


def test_typecheck_command_result_rejects_inline_shell_and_python_glue(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as bad_return:
        _typecheck_fixture(FIXTURES / "invalid" / "command_result_bad_return.orc")
    _assert_diagnostic_code(bad_return, "command_result_return_type_invalid")

    with pytest.raises(LispFrontendCompileError) as inline_python:
        _typecheck_fixture(FIXTURES / "invalid" / "inline_python_command_result.orc")
    _assert_diagnostic_code(inline_python, "inline_python_command_in_workflow")

    with pytest.raises(LispFrontendCompileError) as inline_shell:
        _typecheck_fixture(FIXTURES / "invalid" / "inline_shell_command_result.orc")
    _assert_diagnostic_code(inline_shell, "inline_shell_command_in_workflow")

    wrapped_shell = _write_module(
        tmp_path / "wrapped_shell_command_result.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow wrapped-shell",
                "    ((report_path WorkReport))",
                "    -> ChecksResult",
                "    (command-result wrapped_shell",
                '      :argv ("bash -lc" report_path)',
                "      :returns ChecksResult)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as wrapped_shell_error:
        _typecheck_fixture(
            wrapped_shell,
            command_boundary_environment=build_command_boundary_environment(
                {
                    "wrapped_shell": ExternalToolBinding(
                        name="wrapped_shell",
                        stable_command=("bash -lc",),
                    )
                }
            ),
        )
    _assert_diagnostic_code(wrapped_shell_error, "command_result_argv_invalid")

    for shell in ("bash", "sh"):
        split_shell = _write_module(
            tmp_path / f"{shell}_split_shell_command_result.orc",
            "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.14")',
                    "  (defworkflow wrapped-shell",
                    "    ((report_path WorkReport))",
                    "    -> ChecksResult",
                    "    (command-result wrapped_shell",
                    f'      :argv ("{shell}" "-lc" report_path)',
                    "      :returns ChecksResult)))",
                ]
            ),
        )

        with pytest.raises(LispFrontendCompileError) as split_shell_error:
            _typecheck_fixture(
                split_shell,
                command_boundary_environment=build_command_boundary_environment(
                    {
                        "wrapped_shell": ExternalToolBinding(
                            name="wrapped_shell",
                            stable_command=(shell, "-lc"),
                        )
                    }
                ),
            )
        _assert_diagnostic_code(split_shell_error, "inline_shell_command_in_workflow")


def test_typecheck_command_result_accepts_external_tool_and_certified_adapter_bindings(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp import (
        CertifiedAdapterBinding,
        CommandBoundaryEnvironment,
        ExternEnvironment,
        ExternalToolBinding,
        PromptExtern,
        ProviderExtern,
    )

    command_path = _write_module(
        tmp_path / "command_boundaries.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow run-checks",
                "    ((report_path WorkReport))",
                "    -> ChecksResult",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" report_path)',
                "      :returns ChecksResult))",
                "  (defworkflow normalize",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (command-result normalize_result",
                '      :argv ("python" "scripts/normalize_result.py" report_path)',
                "      :returns ImplementationSummary)))",
            ]
        ),
    )

    typed = _typecheck_fixture(
        command_path,
        extern_environment=ExternEnvironment(
            bindings_by_name={
                "providers.execute": ProviderExtern(name="providers.execute", provider_id="test-provider"),
                "prompts.implementation.execute": PromptExtern(
                    name="prompts.implementation.execute",
                    asset_file="prompts/implementation/execute.md",
                ),
            }
        ),
        command_boundary_environment=CommandBoundaryEnvironment(
            bindings_by_name={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                ),
                "normalize_result": CertifiedAdapterBinding(
                    name="normalize_result",
                    stable_command=("python", "scripts/normalize_result.py"),
                    input_contract={"type": "object"},
                    output_type_name="ImplementationSummary",
                    effects=("structured_result",),
                    path_safety={"kind": "workspace_relpath"},
                    source_map_behavior="step",
                    fixture_ids=("normalize_result_ok",),
                    negative_fixture_ids=("normalize_result_bad",),
                ),
            }
        ),
    )

    assert [workflow.definition.name for workflow in typed] == ["run-checks", "normalize"]


def test_typecheck_command_result_rejects_missing_semantic_adapter_metadata(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp import CommandBoundaryEnvironment, ExternalToolBinding

    command_path = _write_module(
        tmp_path / "semantic_command_missing_adapter.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow normalize",
                "    ((report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (command-result normalize_result",
                '      :argv ("python" "scripts/normalize_result.py" report_path)',
                "      :returns ImplementationSummary)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(
            command_path,
            command_boundary_environment=CommandBoundaryEnvironment(
                bindings_by_name={
                    "run_checks": ExternalToolBinding(
                        name="run_checks",
                        stable_command=("python", "scripts/run_checks.py"),
                    )
                }
            ),
        )

    assert excinfo.value.diagnostics[0].code in {
        "name_unknown",
        "command_adapter_missing_contract",
        "command_result_argv_invalid",
    }


def test_typecheck_command_result_accepts_promoted_certified_adapter_bindings(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_CERTIFIED_ADAPTER_FIXTURE,
        command_boundaries=_promoted_adapter_command_boundaries(),
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert [workflow.definition.name for workflow in result.typed_workflows] == [
        "normalize-summary",
    ]


def test_command_adapter_missing_contract_serializes_as_authority_validation_pass(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp import CommandBoundaryEnvironment, ExternalToolBinding

    command_path = _write_module(
        tmp_path / "semantic_command_missing_adapter_authority.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow normalize",
                "    ((report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (command-result normalize_result",
                '      :argv ("python" "scripts/normalize_result.py" report_path)',
                "      :returns ImplementationSummary)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(
            command_path,
            command_boundary_environment=CommandBoundaryEnvironment(
                bindings_by_name={
                    "run_checks": ExternalToolBinding(
                        name="run_checks",
                        stable_command=("python", "scripts/run_checks.py"),
                    )
                }
            ),
        )

    payload = serialize_diagnostic(excinfo.value.diagnostics[0])
    assert payload["code"] in {
        "name_unknown",
        "command_adapter_missing_contract",
        "command_result_argv_invalid",
    }
    if payload["code"] == "command_adapter_missing_contract":
        assert payload["validation_pass"] == "authority"
        assert payload["authority_layer"] == "frontend"


@pytest.mark.parametrize(
    ("input_contract", "path_safety"),
    [
        ({}, {"kind": "workspace_relpath"}),
        ({"type": "object"}, {}),
    ],
)
def test_build_command_boundary_environment_rejects_incomplete_certified_adapter_metadata(
    input_contract: dict[str, object],
    path_safety: dict[str, object],
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_command_boundary_environment(
            {
                "normalize_result": CertifiedAdapterBinding(
                    name="normalize_result",
                    stable_command=("python", "scripts/normalize_result.py"),
                    input_contract=input_contract,
                    output_type_name="ImplementationSummary",
                    effects=("structured_result",),
                    path_safety=path_safety,
                    source_map_behavior="step",
                    fixture_ids=("normalize_result_ok",),
                    negative_fixture_ids=("normalize_result_bad",),
                )
            }
        )

    _assert_diagnostic_code(excinfo, "command_adapter_missing_contract")


def test_review_findings_certified_adapter_accepts_valid_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.workflow_lisp.adapters import validate_review_findings_v1

    findings_path = tmp_path / "artifacts" / "work" / "review_findings.json"
    findings_path.parent.mkdir(parents=True, exist_ok=True)
    findings_path.write_text(
        '{"items":[{"id":"finding-1","severity":"high","summary":"Broken contract","evidence":"details"}]}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = validate_review_findings_v1.main(
        [
            "validate_review_findings_v1",
            '{"schema_version":"ReviewFindings.v1","items_path":"artifacts/work/review_findings.json"}',
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == (
        '{"schema_version": "ReviewFindings.v1", "items_path": "artifacts/work/review_findings.json"}'
    )


def test_review_findings_certified_adapter_writes_max_length_bundle_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.workflow_lisp.adapters import validate_review_findings_v1

    findings_path = tmp_path / "artifacts" / "work" / "review_findings.json"
    findings_path.parent.mkdir(parents=True, exist_ok=True)
    findings_path.write_text('{"items":[]}', encoding="utf-8")
    bundle_name = f"{'a' * 247}.json"
    bundle_path = tmp_path / ".orchestrate" / "bundles" / bundle_name
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "ORCHESTRATOR_OUTPUT_BUNDLE_PATH",
        bundle_path.relative_to(tmp_path).as_posix(),
    )

    exit_code = validate_review_findings_v1.main(
        [
            "validate_review_findings_v1",
            "ReviewFindings.v1",
            "artifacts/work/review_findings.json",
        ]
    )

    assert exit_code == 0
    assert json.loads(bundle_path.read_text(encoding="utf-8")) == {
        "schema_version": "ReviewFindings.v1",
        "items_path": "artifacts/work/review_findings.json",
    }
    assert json.loads(capsys.readouterr().out) == {
        "schema_version": "ReviewFindings.v1",
        "items_path": "artifacts/work/review_findings.json",
    }


def test_review_findings_certified_adapter_rejects_pointer_authority_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.workflow_lisp.adapters import validate_review_findings_v1

    findings_path = tmp_path / "artifacts" / "work" / "review_findings.json"
    findings_path.parent.mkdir(parents=True, exist_ok=True)
    findings_path.write_text('"artifacts/work/other.json"', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = validate_review_findings_v1.main(
        [
            "validate_review_findings_v1",
            '{"schema_version":"ReviewFindings.v1","items_path":"artifacts/work/review_findings.json"}',
        ]
    )

    assert exit_code == 1
    assert '"review_findings_pointer_authority_forbidden"' in capsys.readouterr().out


def test_review_findings_certified_adapter_rejects_missing_top_level_items(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.workflow_lisp.adapters import validate_review_findings_v1

    findings_path = tmp_path / "artifacts" / "work" / "review_findings.json"
    findings_path.parent.mkdir(parents=True, exist_ok=True)
    findings_path.write_text('{"summary":"missing items"}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = validate_review_findings_v1.main(
        [
            "validate_review_findings_v1",
            '{"schema_version":"ReviewFindings.v1","items_path":"artifacts/work/review_findings.json"}',
        ]
    )

    assert exit_code == 1
    assert '"review_findings_bundle_schema_invalid"' in capsys.readouterr().out


def test_review_findings_certified_adapter_rejects_path_outside_artifacts_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.workflow_lisp.adapters import validate_review_findings_v1

    findings_path = tmp_path / "tmp" / "review_findings.json"
    findings_path.parent.mkdir(parents=True, exist_ok=True)
    findings_path.write_text('{"items":[]}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = validate_review_findings_v1.main(
        [
            "validate_review_findings_v1",
            '{"schema_version":"ReviewFindings.v1","items_path":"tmp/review_findings.json"}',
        ]
    )

    assert exit_code == 1
    assert '"review_findings_path_unsafe"' in capsys.readouterr().out


def test_review_findings_certified_adapter_rejects_symlinked_external_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.workflow_lisp.adapters import validate_review_findings_v1

    external_root = tmp_path.parent / f"{tmp_path.name}_external"
    external_root.mkdir()
    external_findings_path = external_root / "review_findings.json"
    external_findings_path.write_text('{"items":[]}', encoding="utf-8")
    findings_link = tmp_path / "artifacts" / "work" / "review_findings.json"
    findings_link.parent.mkdir(parents=True, exist_ok=True)
    findings_link.symlink_to(external_findings_path)
    monkeypatch.chdir(tmp_path)

    exit_code = validate_review_findings_v1.main(
        [
            "validate_review_findings_v1",
            '{"schema_version":"ReviewFindings.v1","items_path":"artifacts/work/review_findings.json"}',
        ]
    )

    assert exit_code == 1
    assert '"review_findings_path_unsafe"' in capsys.readouterr().out


def test_derive_structured_result_contract_builds_output_bundle_for_record_results() -> None:
    type_env = _build_type_env()
    checks_result = type_env.resolve_type(
        "ChecksResult",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(checks_result, RecordTypeRef)
    contract = derive_structured_result_contract(
        checks_result,
        workflow_name="command_checks",
        step_id="command_checks__run_checks",
    )

    assert contract.contract_kind == "output_bundle"
    assert contract.path == ".orchestrate/workflow_lisp/command_checks/command_checks__run_checks/result.json"
    assert contract.payload["fields"] == [
        {
            "name": "status",
            "json_pointer": "/status",
            "type": "string",
        },
        {
            "name": "report",
            "json_pointer": "/report",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
    ]


def test_derive_structured_result_contract_builds_variant_output_for_union_results() -> None:
    type_env = _build_type_env()
    implementation_state = type_env.resolve_type(
        "ImplementationState",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(implementation_state, UnionTypeRef)
    contract = derive_structured_result_contract(
        implementation_state,
        workflow_name="provider_attempt",
        step_id="provider_attempt__result",
    )

    assert contract.contract_kind == "variant_output"
    assert contract.payload["discriminant"] == {
        "name": "variant",
        "json_pointer": "/variant",
        "type": "enum",
        "allowed": ["COMPLETED", "BLOCKED"],
    }
    assert contract.payload["shared_fields"] == []
    assert _strip_contract_source_metadata(
        contract.payload["variants"]["COMPLETED"]["fields"]
    ) == [
        {
            "name": "execution_report",
            "json_pointer": "/execution_report",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        }
    ]
    assert _strip_contract_source_metadata(
        contract.payload["variants"]["BLOCKED"]["fields"][1]
    ) == {
        "name": "blocker_class",
        "json_pointer": "/blocker_class",
        "type": "enum",
        "allowed": [
            "missing_resource",
            "unavailable_hardware",
            "roadmap_conflict",
            "external_dependency_outside_authority",
            "user_decision_required",
            "unrecoverable_after_fix_attempt",
        ],
    }


def test_derive_structured_result_contract_keeps_repeated_union_fields_variant_scoped(
    tmp_path: Path,
) -> None:
    types_path = _write_module(
        tmp_path / "repeated_union_fields.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath AcceptedReport",
                "    :kind relpath",
                '    :under "artifacts/accepted"',
                "    :must-exist true)",
                "  (defpath RejectedReport",
                "    :kind relpath",
                '    :under "artifacts/rejected"',
                "    :must-exist true)",
                "  (defunion ReviewResult",
                "    (ACCEPTED",
                "      (report AcceptedReport))",
                "    (REJECTED",
                "      (report RejectedReport))))",
            ]
        ),
    )
    syntax_module = _build_syntax_module(types_path)
    type_env = FrontendTypeEnvironment.from_module(compile_stage1_module(types_path))
    review_result = type_env.resolve_type(
        "ReviewResult",
        span=syntax_module.span,
        form_path=("workflow-lisp", "defunion", "ReviewResult"),
    )

    assert isinstance(review_result, UnionTypeRef)
    contract = derive_structured_result_contract(
        review_result,
        workflow_name="review",
        step_id="review__result",
        span=syntax_module.span,
        form_path=("workflow-lisp", "defunion", "ReviewResult"),
    )

    assert contract.contract_kind == "variant_output"
    assert contract.payload["shared_fields"] == []
    assert _strip_contract_source_metadata(contract.payload["variants"]) == {
        "ACCEPTED": {
            "fields": [
                {
                    "name": "report",
                    "json_pointer": "/report",
                    "type": "relpath",
                    "under": "artifacts/accepted",
                    "must_exist_target": True,
                }
            ]
        },
        "REJECTED": {
            "fields": [
                {
                    "name": "report",
                    "json_pointer": "/report",
                    "type": "relpath",
                    "under": "artifacts/rejected",
                    "must_exist_target": True,
                }
            ]
        },
    }


def test_generated_bundle_paths_are_deterministic() -> None:
    type_env = _build_type_env()
    implementation_state = type_env.resolve_type(
        "ImplementationState",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(implementation_state, UnionTypeRef)
    first = derive_structured_result_contract(
        implementation_state,
        workflow_name="provider_attempt",
        step_id="provider_attempt__result",
    )
    second = derive_structured_result_contract(
        implementation_state,
        workflow_name="provider_attempt",
        step_id="provider_attempt__result",
    )

    assert first.path == second.path
    assert first.payload == second.payload


def test_workflow_signature_contract_flattening_records_origin_metadata() -> None:
    type_env = _build_type_env()
    implementation_summary = type_env.resolve_type(
        "ImplementationSummary",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(implementation_summary, RecordTypeRef)
    signature = WorkflowSignature(
        name="summarize_checks",
        params=(("input", implementation_summary),),
        return_type_ref=implementation_summary,
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "defworkflow", "summarize_checks"),
    )

    inputs, outputs, projection = derive_workflow_signature_contracts(signature)

    assert tuple(inputs) == ("input__status", "input__report")
    assert tuple(outputs) == ("return__status", "return__report")
    assert signature.params == (("input", implementation_summary),)
    assert signature.return_type_ref == implementation_summary
    assert projection.workflow_name == "summarize_checks"
    assert [param.name for param in projection.params] == ["input"]
    assert [param.type_kind for param in projection.params] == ["record"]
    assert projection.return_kind == "record"
    assert projection.generated_internal_inputs == ()
    assert [field.generated_name for field in projection.flattened_inputs] == [
        "input__status",
        "input__report",
    ]
    assert [field.generated_name for field in projection.flattened_outputs] == [
        "return__status",
        "return__report",
    ]
    assert projection.flattened_inputs[0].source_path == ("input", "status")
    assert projection.flattened_outputs[-1].source_path == ("return", "report")
    assert inputs["input__report"].definition == {
        "kind": "relpath",
        "type": "relpath",
        "under": "artifacts/work",
        "must_exist_target": True,
    }


def test_workflow_signature_contract_flattening_recurses_nested_records() -> None:
    module = compile_stage1_module(TYPE_FIXTURE)
    type_env = FrontendTypeEnvironment.from_module(module)
    nested_summary = type_env.resolve_type(
        "NestedImplementationSummary",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(nested_summary, RecordTypeRef)
    signature = WorkflowSignature(
        name="summarize_nested_checks",
        params=(("input", nested_summary),),
        return_type_ref=nested_summary,
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "defworkflow", "summarize_nested_checks"),
    )

    inputs, outputs, projection = derive_workflow_signature_contracts(signature)

    assert tuple(inputs) == ("input__summary__status", "input__summary__report")
    assert tuple(outputs) == ("return__summary__status", "return__summary__report")
    assert [field.generated_name for field in projection.flattened_inputs] == [
        "input__summary__status",
        "input__summary__report",
    ]
    assert [field.generated_name for field in projection.flattened_outputs] == [
        "return__summary__status",
        "return__summary__report",
    ]
    assert projection.flattened_inputs[0].source_path == ("input", "summary", "status")
    assert projection.flattened_outputs[-1].source_path == ("return", "summary", "report")


def test_workflow_signature_contract_flattening_rejects_projection_name_collisions(tmp_path: Path) -> None:
    types_path = _write_module(
        tmp_path / "projection_collision_types.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord Summary",
                "    (report WorkReport))",
                "  (defrecord CollisionInput",
                "    (summary Summary)",
                "    (summary__report WorkReport)))",
            ]
        ),
    )
    module = compile_stage1_module(types_path)
    type_env = FrontendTypeEnvironment.from_module(module)
    collision_input = type_env.resolve_type(
        "CollisionInput",
        span=_build_syntax_module(types_path).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(collision_input, RecordTypeRef)
    signature = WorkflowSignature(
        name="collision",
        params=(("input", collision_input),),
        return_type_ref=collision_input,
        span=_build_syntax_module(types_path).span,
        form_path=("workflow-lisp", "defworkflow", "collision"),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        derive_workflow_signature_contracts(signature)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "workflow_boundary_projection_collision"
    assert "input.summary.report" in diagnostic.message
    assert "input.summary__report" in diagnostic.message


def test_union_boundary_projection_flattens_workflow_return_variants() -> None:
    type_env = _build_type_env()
    implementation_state = type_env.resolve_type(
        "ImplementationState",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )
    work_report = type_env.resolve_type(
        "WorkReport",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(implementation_state, UnionTypeRef)
    signature = WorkflowSignature(
        name="provider_attempt",
        params=(("report_path", work_report),),
        return_type_ref=implementation_state,
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "defworkflow", "provider_attempt"),
    )

    _, outputs, projection = derive_workflow_signature_contracts(signature)

    assert projection.workflow_name == "provider_attempt"
    assert [param.name for param in projection.params] == ["report_path"]
    assert [param.type_kind for param in projection.params] == ["relpath"]
    assert projection.return_kind == "union"
    assert "return__variant" in outputs
    assert "return__execution_report" in outputs
    assert "return__progress_report" in outputs
    assert [field.generated_name for field in projection.flattened_outputs] == [
        "return__variant",
        "return__execution_report",
        "return__progress_report",
        "return__blocker_class",
    ]
    execution_report = outputs["return__execution_report"].definition
    assert {
        key: execution_report[key]
        for key in ("kind", "type", "under", "must_exist_target")
    } == {
        "kind": "relpath",
        "type": "relpath",
        "under": "artifacts/work",
        "must_exist_target": False,
    }
    assert execution_report["projection"]["field_role"] == "variant"
    assert execution_report["projection"]["active_variants"] == ["COMPLETED"]

    progress_report = outputs["return__progress_report"].definition
    assert {
        key: progress_report[key]
        for key in ("kind", "type", "under", "must_exist_target")
    } == {
        "kind": "relpath",
        "type": "relpath",
        "under": "artifacts/work",
        "must_exist_target": False,
    }
    assert progress_report["projection"]["field_role"] == "variant"
    assert progress_report["projection"]["active_variants"] == ["BLOCKED"]

    blocker_class = outputs["return__blocker_class"].definition
    assert {
        key: blocker_class[key]
        for key in ("kind", "type", "allowed")
    } == {
        "kind": "scalar",
        "type": "enum",
        "allowed": [
            "missing_resource",
            "unavailable_hardware",
            "roadmap_conflict",
            "external_dependency_outside_authority",
            "user_decision_required",
            "unrecoverable_after_fix_attempt",
        ],
    }
    assert blocker_class["projection"]["field_role"] == "variant"
    assert blocker_class["projection"]["active_variants"] == ["BLOCKED"]


def test_normalized_union_output_contracts_match_authored_boundary_shape() -> None:
    type_env = _build_type_env()
    syntax_module = _build_syntax_module(TYPE_FIXTURE)
    implementation_state = type_env.resolve_type(
        "ImplementationState",
        span=syntax_module.span,
        form_path=("workflow-lisp", "contract-test"),
    )
    work_report = type_env.resolve_type(
        "WorkReport",
        span=syntax_module.span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(implementation_state, UnionTypeRef)
    signature = WorkflowSignature(
        name="provider_attempt",
        params=(("report_path", work_report),),
        return_type_ref=implementation_state,
        span=syntax_module.span,
        form_path=("workflow-lisp", "defworkflow", "provider_attempt"),
    )

    _, outputs, _ = derive_workflow_signature_contracts(signature)

    assert _flattened_boundary_contracts(
        implementation_state,
        generated_name="return",
        span=syntax_module.span,
        form_path=signature.form_path,
    ) == {
        name: _normalize_boundary_contract_definition(contract.definition)
        for name, contract in outputs.items()
    }


@pytest.mark.parametrize(
    ("bad_type", "expected_code"),
    [
        ("Provider", "workflow_boundary_type_invalid"),
        ("Prompt", "workflow_boundary_type_invalid"),
        ("Json", "json_surface_unsupported"),
    ],
)
def test_build_workflow_catalog_rejects_unsupported_boundary_types_in_validated_contracts(
    tmp_path: Path,
    bad_type: str,
    expected_code: str,
) -> None:
    types_path = _write_module(
        tmp_path / f"boundary_types_{bad_type.lower()}.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord InvalidInput",
                f"    (value {bad_type})",
                "    (report WorkReport))",
                "  (defrecord InvalidOutput",
                f"    (value {bad_type})",
                "    (report WorkReport)))",
            ]
        ),
    )
    module = compile_stage1_module(types_path)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_path = _write_module(
        tmp_path / f"boundary_workflow_{bad_type.lower()}.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow summarize",
                "    ((input InvalidInput))",
                "    -> InvalidOutput",
                '    (record InvalidOutput :value "x" :report input.report)))',
            ]
        ),
    )
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(workflow_path))

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_workflow_catalog(module, workflow_defs, type_env)

    _assert_diagnostic_code(excinfo, expected_code)


def _native_returns_extern_environment() -> "ExternEnvironment":
    return ExternEnvironment(
        bindings_by_name={
            "providers.execute": ProviderExtern(
                name="providers.execute",
                provider_id="test-provider",
            ),
            "prompts.implementation.execute": PromptExtern(
                name="prompts.implementation.execute",
                asset_file="prompts/implementation/execute.md",
            ),
        }
    )


def _resolve_native_type(type_env: FrontendTypeEnvironment, type_name: str):
    return type_env.resolve_type(
        type_name,
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "native-returns-test"),
    )


def test_derive_structured_result_contract_builds_native_root_result_for_bool() -> None:
    workflow_name = "native-approval"
    step_id = "native_approval__flag"
    contract = derive_structured_result_contract(
        PrimitiveTypeRef(name="Bool"),
        workflow_name=workflow_name,
        step_id=step_id,
    )

    assert contract.contract_kind == "output_bundle"
    assert contract.payload["fields"] == [{
        "name": "__result__",
        "json_pointer": "",
        "type": "bool",
        "source_map_subject": {
            "subject_kind": "output_bundle_field",
            "subject_name": f"{step_id}::root-result::__result__",
            "workflow_name": workflow_name,
        },
    }]
    assert contract.result_shape == "root_value"
    assert contract.path == f".orchestrate/workflow_lisp/{workflow_name}/{step_id}/result.json"


@pytest.mark.parametrize(
    ("returns_type_name", "expected_definition"),
    [
        ("Int", {"type": "integer"}),
        ("Float", {"type": "float"}),
        ("String", {"type": "string"}),
        (
            "BlockerClass",
            {
                "type": "enum",
                "allowed": [
                    "missing_resource",
                    "unavailable_hardware",
                    "roadmap_conflict",
                    "external_dependency_outside_authority",
                    "user_decision_required",
                    "unrecoverable_after_fix_attempt",
                ],
            },
        ),
        (
            "WorkReport",
            {"type": "relpath", "under": "artifacts/work", "must_exist_target": True},
        ),
        ("Optional[Bool]", {"type": "optional", "item": {"type": "bool"}}),
        ("List[Int]", {"type": "list", "items": {"type": "integer"}}),
        (
            "Map[String, Float]",
            {"type": "map", "keys": {"type": "string"}, "values": {"type": "float"}},
        ),
    ],
)
def test_derive_structured_result_contract_native_root_covers_transportable_families(
    returns_type_name: str,
    expected_definition: dict,
) -> None:
    type_env = _build_type_env()
    contract = derive_structured_result_contract(
        _resolve_native_type(type_env, returns_type_name),
        workflow_name="native-root",
        step_id="native_root__result",
    )

    assert contract.contract_kind == "output_bundle"
    assert contract.result_shape == "root_value"
    assert contract.payload["fields"] == [{
        "name": "__result__",
        "json_pointer": "",
        **expected_definition,
        "source_map_subject": {
            "subject_kind": "output_bundle_field",
            "subject_name": "native_root__result::root-result::__result__",
            "workflow_name": "native-root",
        },
    }]


def test_result_shape_classifies_record_and_union_native_result_contracts() -> None:
    type_env = _build_type_env()
    record_contract = derive_structured_result_contract(
        _resolve_native_type(type_env, "ChecksResult"),
        workflow_name="command_checks",
        step_id="command_checks__run_checks",
    )
    union_contract = derive_structured_result_contract(
        _resolve_native_type(type_env, "ImplementationState"),
        workflow_name="provider_attempt",
        step_id="provider_attempt__result",
    )

    assert record_contract.result_shape == "record_value"
    assert union_contract.result_shape == "union_value"


@pytest.mark.parametrize(
    "type_name",
    [*NATIVE_RETURN_TYPE_NAMES, "ChecksResult", "ImplementationState"],
)
def test_is_transportable_result_type_accepts_native_transportable_families(type_name: str) -> None:
    from orchestrator.workflow_lisp.contracts import is_transportable_result_type

    type_env = _build_type_env()

    assert is_transportable_result_type(_resolve_native_type(type_env, type_name)) is True


@pytest.mark.parametrize(
    "type_name",
    [
        "Json",
        "Provider",
        "Prompt",
        "Optional[ImplementationState]",
        "List[ImplementationSummary]",
        "Map[String, ImplementationState]",
    ],
)
def test_is_transportable_result_type_rejects_non_transportable_types(type_name: str) -> None:
    from orchestrator.workflow_lisp.contracts import is_transportable_result_type

    type_env = _build_type_env()

    assert is_transportable_result_type(_resolve_native_type(type_env, type_name)) is False


def test_is_transportable_result_type_rejects_compile_time_reference_types() -> None:
    from orchestrator.workflow_lisp.contracts import is_transportable_result_type

    type_env = _build_type_env()
    checks_result = _resolve_native_type(type_env, "ChecksResult")
    proc_ref = ProcRefTypeRef(
        name="ProcRef",
        param_type_refs=(),
        return_type_ref=PrimitiveTypeRef(name="Bool"),
    )
    workflow_ref = WorkflowRefTypeRef(
        name="WorkflowRef",
        param_type_refs=(),
        return_type_ref=checks_result,
    )

    assert is_transportable_result_type(proc_ref) is False
    assert is_transportable_result_type(workflow_ref) is False


@pytest.mark.parametrize("returns_type_name", NATIVE_RETURN_TYPE_NAMES)
def test_typecheck_provider_result_accepts_native_transportable_returns(returns_type_name: str) -> None:
    type_env = _build_type_env()
    expr = elaborate_expression(
        _expression_syntax(
            "(provider-result providers.execute "
            ":prompt prompts.implementation.execute "
            ":inputs (report_path) "
            f":returns {returns_type_name})"
        ),
        bound_names=frozenset({"providers.execute", "prompts.implementation.execute", "report_path"}),
    )

    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={
            "report_path": type_env.resolve_type(
                "WorkReport",
                span=expr.span,
                form_path=expr.form_path,
            ),
        },
        extern_environment=_native_returns_extern_environment(),
    )

    assert typed.type_ref == type_env.resolve_type(
        returns_type_name,
        span=expr.span,
        form_path=expr.form_path,
    )


@pytest.mark.parametrize("returns_type_name", NATIVE_RETURN_TYPE_NAMES)
def test_typecheck_command_result_accepts_native_transportable_returns(returns_type_name: str) -> None:
    type_env = _build_type_env()
    expr = elaborate_expression(
        _expression_syntax(
            "(command-result native_step "
            ':argv ("python" "scripts/native_step.py" report_path) '
            f":returns {returns_type_name})"
        ),
        bound_names=frozenset({"report_path"}),
    )

    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={
            "report_path": type_env.resolve_type(
                "WorkReport",
                span=expr.span,
                form_path=expr.form_path,
            ),
        },
    )

    assert typed.type_ref == type_env.resolve_type(
        returns_type_name,
        span=expr.span,
        form_path=expr.form_path,
    )


@pytest.mark.parametrize(
    "returns_type_name",
    ["Provider", "Prompt", "Optional[ImplementationState]", "List[ImplementationSummary]"],
)
def test_typecheck_provider_result_rejects_non_transportable_native_returns(returns_type_name: str) -> None:
    type_env = _build_type_env()
    expr = elaborate_expression(
        _expression_syntax(
            "(provider-result providers.execute "
            ":prompt prompts.implementation.execute "
            ":inputs (report_path) "
            f":returns {returns_type_name})"
        ),
        bound_names=frozenset({"providers.execute", "prompts.implementation.execute", "report_path"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={
                "report_path": type_env.resolve_type(
                    "WorkReport",
                    span=expr.span,
                    form_path=expr.form_path,
                ),
            },
            extern_environment=_native_returns_extern_environment(),
        )

    _assert_diagnostic_code(excinfo, "provider_result_return_type_invalid")


@pytest.mark.parametrize(
    "returns_type_name",
    ["Json", "Map[String, ImplementationState]"],
)
def test_typecheck_command_result_rejects_non_transportable_native_returns(returns_type_name: str) -> None:
    type_env = _build_type_env()
    expr = elaborate_expression(
        _expression_syntax(
            "(command-result native_step "
            ':argv ("python" "scripts/native_step.py" report_path) '
            f":returns {returns_type_name})"
        ),
        bound_names=frozenset({"report_path"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={
                "report_path": type_env.resolve_type(
                    "WorkReport",
                    span=expr.span,
                    form_path=expr.form_path,
                ),
            },
        )

    _assert_diagnostic_code(excinfo, "command_result_return_type_invalid")


def test_native_transportable_returns_fixture_typechecks_with_root_return_signatures() -> None:
    typed_workflows = _typecheck_fixture(
        NATIVE_RETURNS_FIXTURE,
        types_path=NATIVE_RETURNS_FIXTURE,
        extern_environment=_native_returns_extern_environment(),
    )

    return_types = {
        typed.definition.name: typed.signature.return_type_ref for typed in typed_workflows
    }
    assert return_types["native-approval-flag"] == PrimitiveTypeRef(name="Bool")
    assert return_types["native-review-decision"].allowed_values == ("APPROVE", "REVISE")
    assert return_types["native-confidence-score"] == PrimitiveTypeRef(name="Float")
    assert return_types["native-finding-count"] == PrimitiveTypeRef(name="Int")
    assert return_types["native-summary-line"] == PrimitiveTypeRef(name="String")
    assert isinstance(return_types["native-report-location"], PathTypeRef)


def test_native_return_type_not_transportable_fixture_rejected() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(
            NATIVE_RETURNS_INVALID_FIXTURE,
            types_path=NATIVE_RETURNS_INVALID_FIXTURE,
            extern_environment=_native_returns_extern_environment(),
        )

    _assert_diagnostic_code(excinfo, "provider_result_return_type_invalid")
