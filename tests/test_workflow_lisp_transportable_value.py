import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import orchestrator.workflow_lisp.syntax as syntax
from orchestrator.dashboard.models import RunRecord, WorkspaceRecord
from orchestrator.dashboard.projection import RunProjector
from orchestrator.exceptions import WorkflowValidationError
from orchestrator.observability.report import build_status_snapshot
from orchestrator.workflow.dataflow import DataflowManager
from orchestrator.workflow.executable_ir import (
    ExecutableContract,
    ProviderSupervisionStepConfig,
)
from orchestrator.workflow.provider_supervision.contracts import (
    derive_result_bundle_contract,
    derive_result_contract_identity,
)
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    compile_stage1_module,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.contracts import (
    derive_structured_result_contract,
    derive_workflow_signature_contracts,
    is_transportable_result_type,
    structured_contract_semantic_digest,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.lexical_checkpoint_restore import (
    _binding_contract_matches_type_ref,
    _type_ref_for_contract,
    build_restore_metadata,
    capture_restore_payload,
    validate_restore_payload,
)
from orchestrator.workflow_lisp.lowering.phase_scope import (
    _surface_contract_from_structured_field as _phase_scope_surface_contract,
)
from orchestrator.workflow_lisp.lowering.phase_stdlib import (
    _surface_contract_from_structured_field as _phase_stdlib_surface_contract,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file, read_sexpr_text
from orchestrator.workflow_lisp.result_guidance import (
    ResultGuidance,
    parse_return_spec,
    validate_result_guidance_example,
)
from orchestrator.workflow_lisp.syntax import (
    SyntaxNode,
    build_syntax_module,
    ensure_syntax_datum,
)
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    WorkflowRefTypeRef,
    prelude_type_names_for_target,
    type_refs_compatible,
)
from orchestrator.workflow_lisp.typecheck import typecheck_expression
from orchestrator.workflow_lisp.typed_prompt_inputs import (
    normalize_typed_prompt_input_entry,
    render_typed_prompt_inputs,
)
from orchestrator.workflow_lisp.workflows import (
    ExternEnvironment,
    PromptExtern,
    ProviderExtern,
    WorkflowSignature,
)
from tests.workflow_fixture_loader import WorkflowLoader


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
TYPE_FIXTURE = FIXTURES / "valid" / "type_definitions.orc"
FORM_PATH = ("workflow-lisp", "transportable-value-test")
VALUE_TYPE = PrimitiveTypeRef(name="Value")


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


def _write_module(path: Path, target_dsl: str, *forms: str) -> Path:
    path.write_text(_module_source(target_dsl, *forms), encoding="utf-8")
    return path


def _expression(source: str) -> SyntaxNode:
    parsed = read_sexpr_text(
        source,
        source_path="inline_transportable_value.orc",
    )
    assert len(parsed.items) == 1
    datum = parsed.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_transportable_value.orc",
        form_path=FORM_PATH,
    )


def _type_environment() -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(
        compile_stage1_module(TYPE_FIXTURE)
    )


def _diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError]) -> str:
    return excinfo.value.diagnostics[0].code


def test_value_type_is_installed_only_from_target_219() -> None:
    assert syntax.VALUE_MIN_TARGET_DSL_VERSION == "2.19"
    assert not syntax.target_dsl_supports_value("2.18")
    assert syntax.target_dsl_supports_value("2.19")
    assert "Value" not in prelude_type_names_for_target("2.18")
    assert "Value" in prelude_type_names_for_target("2.19")

    module = build_syntax_module(
        read_sexpr_text(
            _module_source("2.19", "(defrecord Box (payload Value))"),
            source_path="target_219_value.orc",
        )
    )
    definition_module = elaborate_definition_module(
        _definition_only_syntax_module(module)
    )
    type_env = FrontendTypeEnvironment.from_module(definition_module)
    probe = _expression("true")

    assert type_env.resolve_type(
        "Value",
        span=probe.span,
        form_path=probe.form_path,
    ) == VALUE_TYPE


@pytest.mark.parametrize("type_name", ("Value", "Optional[Value]"))
def test_target_218_value_occurrence_reports_version_gate_at_authored_type(
    tmp_path: Path,
    type_name: str,
) -> None:
    path = _write_module(
        tmp_path / "target_218_value.orc",
        "2.18",
        f"(defworkflow probe ((payload {type_name})) -> Bool true)",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert _diagnostic_code(excinfo) == "value_type_requires_dsl_2_19"
    assert excinfo.value.diagnostics[0].span.start.line == 4


@pytest.mark.parametrize("target_dsl", ("2.18", "2.19"))
@pytest.mark.parametrize(
    "definition",
    (
        "(defrecord Value (payload Bool))",
        "(defunion Value (LEGACY))",
        "(defschema Value (payload Bool))",
    ),
)
def test_value_name_is_reserved_against_local_definitions_at_every_target(
    tmp_path: Path,
    target_dsl: str,
    definition: str,
) -> None:
    path = _write_module(
        tmp_path / f"local_value_shadow_{target_dsl}.orc",
        target_dsl,
        definition,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert _diagnostic_code(excinfo) == "prelude_type_name_reserved"


@pytest.mark.parametrize("target_dsl", ("2.18", "2.19"))
def test_value_name_is_reserved_against_imported_definitions_at_every_target(
    target_dsl: str,
) -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(target_dsl),
            source_path=f"imported_value_shadow_{target_dsl}.orc",
        )
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        FrontendTypeEnvironment.from_module(
            module,
            imported_type_refs={
                "Value": PrimitiveTypeRef(name="legacy/Value"),
            },
        )

    assert _diagnostic_code(excinfo) == "prelude_type_name_reserved"


def test_value_type_compatibility_is_exact_in_both_directions() -> None:
    type_env = _type_environment()
    probe = _expression("true")
    narrower_types = tuple(
        type_env.resolve_type(
            type_name,
            span=probe.span,
            form_path=probe.form_path,
        )
        for type_name in (
            "Bool",
            "WorkReport",
            "ChecksResult",
            "ImplementationState",
            "Optional[Bool]",
            "List[Int]",
            "Map[String, Float]",
        )
    )

    assert type_refs_compatible(VALUE_TYPE, VALUE_TYPE)
    for narrower_type in narrower_types:
        assert not type_refs_compatible(VALUE_TYPE, narrower_type)
        assert not type_refs_compatible(narrower_type, VALUE_TYPE)


@pytest.mark.parametrize(
    "narrower_type_name",
    (
        "Bool",
        "WorkReport",
        "ChecksResult",
        "ImplementationState",
        "Optional[Bool]",
        "List[Int]",
        "Map[String, Float]",
    ),
)
@pytest.mark.parametrize(
    ("then_name", "else_name"),
    (("value", "narrower"), ("narrower", "value")),
)
def test_ordinary_typechecking_rejects_value_narrower_flows_in_both_directions(
    narrower_type_name: str,
    then_name: str,
    else_name: str,
) -> None:
    type_env = _type_environment()
    probe = _expression("true")
    narrower_type = type_env.resolve_type(
        narrower_type_name,
        span=probe.span,
        form_path=probe.form_path,
    )
    expression = elaborate_expression(
        _expression(f"(if true {then_name} {else_name})"),
        bound_names=frozenset({"value", "narrower"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expression,
            type_env=type_env,
            value_env={
                "value": VALUE_TYPE,
                "narrower": narrower_type,
            },
        )

    assert _diagnostic_code(excinfo) == "type_mismatch"


@pytest.mark.parametrize(
    ("source", "expected_code"),
    (
        ("(if value true false)", "if_condition_not_bool"),
        ("(match value ((ONLY item) item))", "match_subject_not_union"),
        ("value.field", "record_field_unknown"),
        (
            "(provider-bundle-path value :as Path.state-root)",
            "provider_bundle_path_source_invalid",
        ),
        ("(+ value 1)", "pure_expr_operand_type_mismatch"),
        ("(list/length value)", "pure_expr_operand_type_mismatch"),
    ),
)
def test_value_operations_keep_the_existing_operation_owned_diagnostic(
    source: str,
    expected_code: str,
) -> None:
    type_env = _type_environment()
    expression = elaborate_expression(
        _expression(source),
        bound_names=frozenset({"value"}),
        target_dsl_version="2.18",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expression,
            type_env=type_env,
            value_env={"value": VALUE_TYPE},
        )

    assert _diagnostic_code(excinfo) == expected_code


def test_value_guidance_allows_text_but_rejects_example_before_evaluation() -> None:
    raw_return = ensure_syntax_datum(
        _expression(
            '(result Value :description "Return one JSON value." '
            ':format-hint "Write it at the document root.")'
        ).datum,
        module_path="inline_transportable_value.orc",
        form_path=FORM_PATH,
    )
    return_spec = parse_return_spec(
        raw_return,
        form_path=FORM_PATH,
        label="return type",
    )

    assert return_spec.type_name == "Value"
    assert return_spec.guidance is not None
    assert return_spec.guidance.description == "Return one JSON value."
    assert (
        return_spec.guidance.format_hint
        == "Write it at the document root."
    )

    deliberately_nonconstant_example = _expression("missing-runtime-name")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        validate_result_guidance_example(
            ResultGuidance(example_expr=deliberately_nonconstant_example),
            expected_type=VALUE_TYPE,
            type_env=_type_environment(),
        )

    assert _diagnostic_code(excinfo) == "value_guidance_example_unsupported"


def test_value_contract_derives_one_direct_root_output_bundle_field() -> None:
    contract = derive_structured_result_contract(
        VALUE_TYPE,
        workflow_name="value-provider",
        step_id="value_provider__result",
    )

    assert contract.contract_kind == "output_bundle"
    assert len(contract.payload["fields"]) == 1
    field = contract.payload["fields"][0]
    assert {
        "name": field["name"],
        "json_pointer": field["json_pointer"],
        "type": field["type"],
    } == {
        "name": "__result__",
        "json_pointer": "",
        "type": "value",
    }
    assert field["source_map_subject"]["subject_kind"] == "output_bundle_field"
    assert field["source_map_subject"]["subject_name"].endswith(
        "::root-result::__result__"
    )


def test_value_contract_derives_value_kind_at_workflow_boundary() -> None:
    probe = _expression("true")
    signature = WorkflowSignature(
        name="value-boundary",
        params=(("payload", VALUE_TYPE),),
        return_type_ref=VALUE_TYPE,
        span=probe.span,
        form_path=("workflow-lisp", "defworkflow", "value-boundary"),
    )

    inputs, outputs, projection = derive_workflow_signature_contracts(signature)

    assert inputs["payload"].definition == {
        "kind": "value",
        "type": "value",
    }
    assert outputs["__result__"].definition == {
        "kind": "value",
        "type": "value",
    }
    assert projection.return_kind == "root"


def test_value_contract_loader_requires_219_then_accepts_direct_root(
    tmp_path: Path,
) -> None:
    def workflow(version: str) -> dict:
        return {
            "version": version,
            "name": "value-contract-loader",
            "steps": [
                {
                    "name": "Produce",
                    "command": ["echo", "ok"],
                    "output_bundle": {
                        "path": "state/value.json",
                        "fields": [
                            {
                                "name": "__result__",
                                "json_pointer": "",
                                "type": "value",
                            }
                        ],
                    },
                }
            ],
        }

    loader = WorkflowLoader(tmp_path)
    with pytest.raises(WorkflowValidationError) as excinfo:
        loader.load_mapping(workflow("2.18"))
    assert any(
        "value_contract_requires_dsl_2_19" in error.message
        for error in excinfo.value.errors
    )

    loaded = loader.load_mapping(workflow("2.19"))
    assert loaded.surface.steps[0].common.output_bundle is not None


def test_value_contract_nested_descriptors_cover_collections_record_and_union() -> None:
    string_type = PrimitiveTypeRef(name="String")
    cases = (
        (VALUE_TYPE, {"type": "value"}),
        (
            OptionalTypeRef(name="Optional[Value]", item_type_ref=VALUE_TYPE),
            {"type": "optional", "item": {"type": "value"}},
        ),
        (
            ListTypeRef(name="List[Value]", item_type_ref=VALUE_TYPE),
            {"type": "list", "items": {"type": "value"}},
        ),
        (
            MapTypeRef(
                name="Map[String, Value]",
                key_type_ref=string_type,
                value_type_ref=VALUE_TYPE,
            ),
            {
                "type": "map",
                "keys": {"type": "string"},
                "values": {"type": "value"},
            },
        ),
    )
    for index, (type_ref, expected_descriptor) in enumerate(cases):
        contract = derive_structured_result_contract(
            type_ref,
            workflow_name="nested-value-contracts",
            step_id=f"nested_value__{index}",
        )
        field = contract.payload["fields"][0]
        assert {
            key: value
            for key, value in field.items()
            if key not in {"name", "json_pointer", "source_map_subject"}
        } == expected_descriptor

    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.19",
                "(defrecord ValueBox (payload Value))",
                "(defunion ValueChoice (KEEP (payload Value)) (DROP))",
            ),
            source_path="nested_value_contracts.orc",
        )
    )
    type_env = FrontendTypeEnvironment.from_module(
        elaborate_definition_module(
            _definition_only_syntax_module(syntax_module)
        )
    )
    probe = _expression("true")
    record_contract = derive_structured_result_contract(
        type_env.resolve_type(
            "ValueBox",
            span=probe.span,
            form_path=probe.form_path,
        ),
        workflow_name="nested-value-contracts",
        step_id="record_value",
    )
    union_contract = derive_structured_result_contract(
        type_env.resolve_type(
            "ValueChoice",
            span=probe.span,
            form_path=probe.form_path,
        ),
        workflow_name="nested-value-contracts",
        step_id="union_value",
    )

    assert record_contract.payload["fields"][0]["type"] == "value"
    assert (
        union_contract.payload["variants"]["KEEP"]["fields"][0]["type"]
        == "value"
    )


def test_value_contract_transportability_keeps_nontransportable_types_and_refs_false() -> None:
    type_env = _type_environment()
    probe = _expression("true")
    checks_result = type_env.resolve_type(
        "ChecksResult",
        span=probe.span,
        form_path=probe.form_path,
    )
    nontransportable = (
        PrimitiveTypeRef(name="Json"),
        PrimitiveTypeRef(name="Provider"),
        PrimitiveTypeRef(name="Prompt"),
        ProcRefTypeRef(
            name="ProcRef[Value -> Value]",
            param_type_refs=(VALUE_TYPE,),
            return_type_ref=VALUE_TYPE,
        ),
        WorkflowRefTypeRef(
            name="WorkflowRef[Value -> ChecksResult]",
            param_type_refs=(VALUE_TYPE,),
            return_type_ref=checks_result,
        ),
    )

    assert all(
        is_transportable_result_type(type_ref) is False
        for type_ref in nontransportable
    )


def test_value_contract_loader_covers_all_surfaces_and_rejects_invalid_pairs(
    tmp_path: Path,
) -> None:
    def workflow(version: str) -> dict:
        return {
            "version": version,
            "name": "value-contract-surfaces",
            "inputs": {
                "payload": {"kind": "value", "type": "value"},
            },
            "outputs": {
                "result": {
                    "kind": "value",
                    "type": "value",
                    "from": {
                        "ref": "root.steps.Produce.artifacts.result",
                    },
                },
            },
            "artifacts": {
                "stored": {"kind": "value", "type": "value"},
            },
            "steps": [
                {
                    "name": "Produce",
                    "command": ["echo", "ok"],
                    "output_bundle": {
                        "path": "state/value.json",
                        "fields": [
                            {
                                "name": "result",
                                "json_pointer": "",
                                "type": "value",
                            }
                        ],
                    },
                },
            ],
        }

    loader = WorkflowLoader(tmp_path)
    with pytest.raises(WorkflowValidationError) as excinfo:
        loader.load_mapping(workflow("2.18"))
    assert any(
        "value_contract_requires_dsl_2_19" in error.message
        for error in excinfo.value.errors
    )

    loaded = loader.load_mapping(workflow("2.19"))
    assert loaded.surface.inputs["payload"].kind == "value"
    assert loaded.surface.outputs["result"].kind == "value"
    assert loaded.surface.artifacts["stored"].kind == "value"
    assert loaded.surface.steps[0].common.output_bundle is not None

    legacy = workflow("2.19")
    legacy["steps"][0].pop("output_bundle")
    legacy["steps"][0]["expected_outputs"] = [
        {
            "name": "result",
            "path": "state/value.json",
            "type": "value",
        }
    ]
    with pytest.raises(WorkflowValidationError) as excinfo:
        loader.load_mapping(legacy)
    assert any(
        "invalid expected_outputs type 'value'" in error.message
        for error in excinfo.value.errors
    )

    for kind, value_type, expected_fragments in (
        ("scalar", "value", ("kind 'scalar'",)),
        ("value", "string", ("kind 'value'", "type 'value'")),
    ):
        invalid = workflow("2.19")
        invalid["inputs"]["payload"] = {
            "kind": kind,
            "type": value_type,
        }
        with pytest.raises(WorkflowValidationError) as excinfo:
            loader.load_mapping(invalid)
        messages = tuple(error.message for error in excinfo.value.errors)
        assert any(
            all(fragment in message for fragment in expected_fragments)
            for message in messages
        ), messages

    invalid_allowed = workflow("2.19")
    invalid_allowed["inputs"]["payload"]["allowed"] = ["only"]
    with pytest.raises(WorkflowValidationError) as excinfo:
        loader.load_mapping(invalid_allowed)
    assert any(
        "kind 'value' forbids 'allowed'" in error.message
        for error in excinfo.value.errors
    )


def test_value_contract_fingerprint_preserves_literal_value_descriptor() -> None:
    value_contract = derive_structured_result_contract(
        VALUE_TYPE,
        workflow_name="value-fingerprint",
        step_id="fingerprint_result",
    )
    string_contract = derive_structured_result_contract(
        PrimitiveTypeRef(name="String"),
        workflow_name="value-fingerprint",
        step_id="fingerprint_result",
    )
    value_payload = {"fields": value_contract.payload["fields"]}
    string_payload = {"fields": string_contract.payload["fields"]}

    assert value_contract.payload["fields"][0]["type"] == "value"
    assert string_contract.payload["fields"][0]["type"] == "string"
    assert (
        structured_contract_semantic_digest(value_payload)
        != structured_contract_semantic_digest(string_payload)
    )


def test_value_contract_typechecks_provider_and_command_result_returns() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source("2.19"),
            source_path="value_effect_return_typecheck.orc",
        )
    )
    type_env = FrontendTypeEnvironment.from_module(
        elaborate_definition_module(
            _definition_only_syntax_module(syntax_module)
        )
    )
    extern_environment = ExternEnvironment(
        bindings_by_name={
            "providers.execute": ProviderExtern(
                name="providers.execute",
                provider_id="test-provider",
            ),
            "prompts.execute": PromptExtern(
                name="prompts.execute",
                asset_file="prompts/execute.md",
            ),
        }
    )
    cases = (
        (
            "(provider-result providers.execute "
            ":prompt prompts.execute :inputs (message) :returns Value)",
            frozenset({"providers.execute", "prompts.execute", "message"}),
        ),
        (
            '(command-result produce_value :argv ("echo" "ok") '
            ":returns Value)",
            frozenset(),
        ),
    )

    for source, bound_names in cases:
        expression = elaborate_expression(
            _expression(source),
            bound_names=bound_names,
            target_dsl_version="2.19",
        )
        typed = typecheck_expression(
            expression,
            type_env=type_env,
            value_env={
                "message": PrimitiveTypeRef(name="String"),
            },
            extern_environment=extern_environment,
        )
        assert typed.type_ref == VALUE_TYPE


def test_value_contract_compiles_inline_procedure_workflow_call_and_public_pass_through(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "value_pass_through.orc",
        "2.19",
        "(defmodule value-pass-through)",
        "(export entry)",
        (
            "(defproc pass-value ((payload Value)) -> Value "
            ":effects () :lowering inline payload)"
        ),
        "(defworkflow child ((payload Value)) -> Value (pass-value payload))",
        (
            "(defworkflow entry ((payload Value)) -> Value "
            "(call child :payload payload))"
        ),
    )

    result = compile_stage3_module(
        path,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )
    entry = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "entry"
    )

    assert entry.authored_mapping["inputs"]["payload"]["kind"] == "value"
    assert entry.authored_mapping["inputs"]["payload"]["type"] == "value"
    assert entry.authored_mapping["outputs"]["__result__"]["kind"] == "value"
    assert entry.authored_mapping["outputs"]["__result__"]["type"] == "value"
    assert "entry" in result.validated_bundles


@pytest.mark.parametrize(
    ("descriptor", "example"),
    (
        ({"type": "value"}, {"answer": True}),
        (
            {"type": "optional", "item": {"type": "value"}},
            {"answer": True},
        ),
    ),
    ids=("direct", "nested-optional"),
)
def test_value_contract_loader_rejects_field_guidance_examples_before_schema_validation(
    tmp_path: Path,
    descriptor: dict,
    example: object,
) -> None:
    workflow = {
        "version": "2.19",
        "name": "value-guidance-example-loader",
        "steps": [
            {
                "name": "Produce",
                "command": ["echo", "ok"],
                "output_bundle": {
                    "path": "state/value.json",
                    "fields": [
                        {
                            "name": "__result__",
                            "json_pointer": "",
                            **descriptor,
                            "example": example,
                        }
                    ],
                },
            }
        ],
    }

    with pytest.raises(WorkflowValidationError) as excinfo:
        WorkflowLoader(tmp_path).load_mapping(workflow)

    messages = tuple(error.message for error in excinfo.value.errors)
    assert any(
        "value_guidance_example_unsupported" in message
        for message in messages
    )
    assert not any(
        "is invalid for the field schema" in message
        for message in messages
    )


@pytest.mark.parametrize(
    ("forbidden_key", "forbidden_value"),
    (
        ("allowed", ["only"]),
        ("under", "state"),
        ("must_exist_target", True),
        ("item", {"type": "string"}),
        ("items", {"type": "string"}),
        ("keys", {"type": "string"}),
        ("values", {"type": "string"}),
    ),
)
def test_value_contract_loader_rejects_every_narrower_schema_key(
    tmp_path: Path,
    forbidden_key: str,
    forbidden_value: object,
) -> None:
    workflow = {
        "version": "2.19",
        "name": "value-forbidden-schema-key",
        "steps": [
            {
                "name": "Produce",
                "command": ["echo", "ok"],
                "output_bundle": {
                    "path": "state/value.json",
                    "fields": [
                        {
                            "name": "__result__",
                            "json_pointer": "",
                            "type": "value",
                            forbidden_key: forbidden_value,
                        }
                    ],
                },
            }
        ],
    }

    with pytest.raises(WorkflowValidationError) as excinfo:
        WorkflowLoader(tmp_path).load_mapping(workflow)

    assert any(
        f"type 'value' forbids '{forbidden_key}'" in error.message
        for error in excinfo.value.errors
    )


def _compile_value_runtime_surfaces(tmp_path: Path):
    path = _write_module(
        tmp_path / "value_runtime_surfaces.orc",
        "2.19",
        "(defmodule value-runtime-surfaces)",
        "(export entry)",
        (
            "(defworkflow entry ((payload Value)) -> Value "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs (payload) :returns Value))"
        ),
    )
    prompt_path = tmp_path / "prompts" / "worker.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("Return one value.\n", encoding="utf-8")

    return compile_stage3_module(
        path,
        entry_workflow="entry",
        provider_externs={"providers.worker": "test-provider"},
        prompt_externs={"prompts.worker": "prompts/worker.md"},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )


def test_transportable_value_kind_compiler_surfaces_retain_declared_contract(
    tmp_path: Path,
) -> None:
    result = _compile_value_runtime_surfaces(tmp_path)
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "entry"
    )
    bundle = result.validated_bundles["entry"]
    node = next(iter(bundle.ir.nodes.values()))

    assert lowered.authored_mapping["inputs"]["payload"] == {
        "kind": "value",
        "type": "value",
    }
    assert lowered.authored_mapping["outputs"]["__result__"]["kind"] == "value"
    assert lowered.authored_mapping["outputs"]["__result__"]["type"] == "value"
    assert bundle.surface.inputs["payload"].definition == {
        "kind": "value",
        "type": "value",
    }
    assert bundle.surface.outputs["__result__"].definition == {
        "kind": "value",
        "type": "value",
        "from": {"ref": "root.steps.entry__result.artifacts.__result__"},
    }
    assert node.execution_config.common.output_bundle["fields"][0]["type"] == "value"
    assert bundle.runtime_plan.schema_version == "workflow_runtime_plan.v1"
    runtime_result = next(
        artifact
        for artifact in bundle.runtime_plan.artifacts
        if artifact.contract_name == "__result__"
    )
    assert runtime_result.contract_kind == "value"
    assert bundle.semantic_ir.schema_version == "workflow_semantic_ir.v1"
    semantic_workflow = bundle.semantic_ir.workflows["entry"]
    input_contract = bundle.semantic_ir.contracts[
        semantic_workflow.input_contract_ids["payload"]
    ]
    input_type = bundle.semantic_ir.types[input_contract.type_id]
    output_contract = bundle.semantic_ir.contracts[
        semantic_workflow.output_contract_ids["__result__"]
    ]
    output_type = bundle.semantic_ir.types[output_contract.type_id]
    assert (
        input_contract.contract_kind,
        input_contract.value_type,
        dict(input_contract.definition),
    ) == ("value", "value", {"kind": "value", "type": "value"})
    assert (
        input_type.type_kind,
        input_type.value_type,
        dict(input_type.definition),
    ) == ("value", "value", {"kind": "value", "type": "value"})
    assert (
        output_contract.contract_kind,
        output_contract.value_type,
        dict(output_contract.definition),
    ) == (
        "value",
        "value",
        {
            "kind": "value",
            "type": "value",
            "from": {"ref": "root.steps.entry__result.artifacts.__result__"},
        },
    )
    assert (
        output_type.type_kind,
        output_type.value_type,
        dict(output_type.definition),
    ) == (
        "value",
        "value",
        {
            "kind": "value",
            "type": "value",
            "from": {"ref": "root.steps.entry__result.artifacts.__result__"},
        },
    )


def _transportable_value_dataflow_manager(
    tmp_path: Path,
    violations: list[tuple[str, dict]],
) -> DataflowManager:
    return DataflowManager(
        workspace=tmp_path,
        artifact_registry={
            "payload": {
                "kind": "value",
                "type": "value",
            }
        },
        workflow_version="2.19",
        uses_qualified_identities=lambda: True,
        workflow_version_at_least=lambda version: True,
        step_id_resolver=lambda step: str(step.get("step_id", "root.consume")),
        contract_violation_result=lambda message, context: (
            violations.append((message, context))
            or {"exit_code": 1, "error": context}
        ),
        persist_state=lambda state: None,
        substitute_path_template=lambda *args, **kwargs: (None, None),
        resolve_workspace_path=lambda relpath: tmp_path / relpath,
        current_step_index=lambda: 0,
    )


def test_transportable_value_dataflow_validates_and_preserves_opaque_payload(
    tmp_path: Path,
) -> None:
    payload = {
        "approved": True,
        "items": [None, 3, "three", {"nested": [1.5, False]}],
    }
    violations: list[tuple[str, dict]] = []
    manager = _transportable_value_dataflow_manager(tmp_path, violations)
    state = {
        "artifact_versions": {
            "payload": [
                {
                    "version": 1,
                    "producer": "root.produce",
                    "value": payload,
                }
            ]
        }
    }
    step = {
        "step_id": "root.consume",
        "consumes": [
            {
                "artifact": "payload",
                "producers": ["root.produce"],
                "freshness": "any",
            }
        ],
    }

    assert manager.enforce_consumes_contract(step, "Consume", state) is None
    assert state["_resolved_consumes"]["root.consume"]["payload"] == payload
    assert state["_resolved_consumes"]["root.consume"]["payload"] is payload
    assert violations == []

    invalid_state = {
        "artifact_versions": {
            "payload": [
                {
                    "version": 2,
                    "producer": "root.produce",
                    "value": {"bad": (1, 2)},
                }
            ]
        }
    }
    violation = manager.enforce_consumes_contract(
        step,
        "Consume",
        invalid_state,
    )

    assert violation is not None
    assert violations[-1][1]["reason"] == "invalid_selected_value"
    assert (
        violations[-1][1]["violations"][0]["context"]["value_path"]
        == "/bad"
    )


def test_transportable_value_dataflow_validates_publications_through_shared_contract(
    tmp_path: Path,
) -> None:
    payload = {"approved": True, "items": [None, 3, "three"]}
    violations: list[tuple[str, dict]] = []
    manager = _transportable_value_dataflow_manager(tmp_path, violations)
    step = {
        "step_id": "root.produce",
        "publishes": [{"artifact": "payload", "from": "result"}],
    }
    state: dict = {}

    assert (
        manager.record_published_artifacts(
            step,
            "Produce",
            {"exit_code": 0, "artifacts": {"result": payload}},
            state,
        )
        is None
    )
    assert state["artifact_versions"]["payload"][0]["value"] == payload
    assert state["artifact_versions"]["payload"][0]["value"] is payload
    assert violations == []

    invalid_state: dict = {}
    violation = manager.record_published_artifacts(
        step,
        "Produce",
        {"exit_code": 0, "artifacts": {"result": {"bad": (1, 2)}}},
        invalid_state,
    )

    assert violation is not None
    assert violations[-1][1]["reason"] == "invalid_selected_value"
    assert (
        violations[-1][1]["violations"][0]["context"]["value_path"]
        == "/bad"
    )
    assert invalid_state.get("artifact_versions", {}).get("payload") is None


def test_transportable_value_checkpoint_identity_ignores_payload_shape(
    tmp_path: Path,
) -> None:
    bundle = _compile_value_runtime_surfaces(tmp_path).validated_bundles["entry"]
    contract = bundle.surface.inputs["payload"]
    restore = build_restore_metadata(
        binding_descriptors=(
            {
                "binding_name": "payload",
                "binding_kind": "let_binding",
                "type_ref": "Value",
                "source_map_origin_key": "origin:value",
                "value_document": {"ref": "root.inputs.payload"},
            },
        )
    )
    point = SimpleNamespace(
        details={"restore": restore},
        program_point_id="point:value",
        step_id="root.value",
        point_kind="pure_projection",
        origin_key="origin:value",
    )

    assert _binding_contract_matches_type_ref(contract, "Value")
    assert not _binding_contract_matches_type_ref(contract, "String")

    payloads = ({"old": [1, 2]}, ["new", {"shape": True}])
    records = []
    for payload in payloads:
        executor = SimpleNamespace(
            state_manager=SimpleNamespace(
                state=SimpleNamespace(to_dict=lambda: {}),
            ),
            _resolve_pure_projection_bindings=(
                lambda value_document, run_state, payload=payload: (payload, None)
            ),
        )
        record = capture_restore_payload(
            executor=executor,
            point=point,
            execution_index=1,
            loop_iteration=None,
            completed_effect_refs=(),
        )
        assert record is not None
        validate_restore_payload(record)
        records.append(record)

    first_binding = records[0]["bindings"][0]
    second_binding = records[1]["bindings"][0]
    assert records[0]["schema_version"] == records[1]["schema_version"]
    assert first_binding["type_ref"] == second_binding["type_ref"] == "Value"
    assert first_binding["schema_digest"] == second_binding["schema_digest"]
    assert first_binding["value"] == payloads[0]
    assert second_binding["value"] == payloads[1]
    assert first_binding["value_digest"] != second_binding["value_digest"]
    assert _type_ref_for_contract(contract, payloads[0]) == "Value"
    assert _type_ref_for_contract(contract, payloads[1]) == "Value"


def test_transportable_value_phase_surface_contract_helpers_preserve_value_kind() -> None:
    field = {"type": "value"}

    assert _phase_scope_surface_contract(field) == {
        "kind": "value",
        "type": "value",
    }
    assert _phase_stdlib_surface_contract(field) == {
        "kind": "value",
        "type": "value",
    }


@pytest.mark.parametrize(
    ("descriptor", "expected_field"),
    (
        (
            {"kind": "primitive", "name": "Value"},
            {"type": "value"},
        ),
        (
            {
                "kind": "optional",
                "item": {"kind": "primitive", "name": "Value"},
            },
            {"type": "optional", "item": {"type": "value"}},
        ),
        (
            {
                "kind": "list",
                "item": {"kind": "primitive", "name": "Value"},
            },
            {"type": "list", "items": {"type": "value"}},
        ),
        (
            {
                "kind": "map",
                "key": {"kind": "primitive", "name": "String"},
                "value": {"kind": "primitive", "name": "Value"},
            },
            {
                "type": "map",
                "keys": {"type": "string"},
                "values": {"type": "value"},
            },
        ),
    ),
)
def test_transportable_value_provider_supervision_derives_recursive_contracts(
    descriptor: dict,
    expected_field: dict,
) -> None:
    name, contract_kind, value_type = derive_result_contract_identity(descriptor)
    contract = ExecutableContract(
        name=name,
        kind=contract_kind,
        value_type=value_type,
        definition={"type": descriptor},
    )

    derived_kind, payload, derived_descriptor = derive_result_bundle_contract(
        contract,
        path="state/result.json",
    )

    assert derived_kind == "output_bundle"
    assert payload == {
        "path": "state/result.json",
        "fields": [
            {
                "name": "__result__",
                "json_pointer": "",
                **expected_field,
            }
        ],
    }
    assert derived_descriptor == descriptor
    if descriptor == {"kind": "primitive", "name": "Value"}:
        assert (contract.kind, contract.value_type) == ("scalar", "Value")
        assert _binding_contract_matches_type_ref(contract, "Value")
        assert not _binding_contract_matches_type_ref(contract, "String")
        assert _type_ref_for_contract(contract, {"shape": [1, None]}) == "Value"
        assert _type_ref_for_contract(contract, ["other", {"shape": True}]) == "Value"


def test_transportable_value_typed_prompt_rendering_is_canonical_and_opaque() -> None:
    entry = normalize_typed_prompt_input_entry(
        {
            "schema_version": "workflow_lisp_typed_prompt_input.v1",
            "binding_name": "payload",
            "renderer": {
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "accepted_shape": "any_pure_value",
            },
            "value_source": {
                "kind": "typed_binding_ref",
                "ref": "inputs.payload",
            },
            "value_type_name": "Value",
            "source_map_origin_key": "value-runtime-surfaces::entry",
            "injection_order": 0,
        }
    )
    payload = {
        "z": [None, False],
        "a": {"nested": 3},
    }

    rendered, evidence = render_typed_prompt_inputs(
        [entry],
        resolved_typed_values={"payload": payload},
        workflow_name="value-runtime-surfaces::entry",
        step_id="root.entry__result",
    )

    rendered_lines = rendered.splitlines()
    assert json.loads(rendered_lines[-1]) == payload
    assert len(evidence) == 1
    assert evidence[0]["schema_version"] == (
        "workflow_lisp_typed_prompt_input_evidence.v1"
    )
    assert evidence[0]["value_type_name"] == "Value"
    assert evidence[0]["renderer"]["accepted_shape"] == "any_pure_value"
    assert "rendered_bytes" not in evidence[0]


def test_transportable_value_state_report_and_dashboard_preserve_payload(
    tmp_path: Path,
) -> None:
    bundle = WorkflowLoader(tmp_path).load_mapping(
        {
            "version": "2.19",
            "name": "value-projection",
            "outputs": {
                "__result__": {
                    "kind": "value",
                    "type": "value",
                    "from": {
                        "ref": "root.steps.Produce.artifacts.__result__",
                    },
                }
            },
            "steps": [
                {
                    "name": "Produce",
                    "command": ["true"],
                    "output_bundle": {
                        "path": "state/value.json",
                        "fields": [
                            {
                                "name": "__result__",
                                "json_pointer": "",
                                "type": "value",
                            }
                        ],
                    },
                }
            ],
        }
    )
    [node_id] = bundle.projection.ordered_execution_node_ids()
    presentation_name = bundle.projection.entries_by_node_id[node_id].presentation_key
    payload = {
        "decision": "APPROVE",
        "metrics": {"correctness": 0.95},
        "attempt_ids": [1, 2],
        "owner": None,
    }
    state = {
        "run_id": "value-projection",
        "status": "completed",
        "steps": {
            presentation_name: {
                "status": "completed",
                "exit_code": 0,
                "artifacts": {"__result__": payload},
            }
        },
        "workflow_outputs": {"__result__": payload},
    }

    snapshot = build_status_snapshot(bundle, state, tmp_path)
    assert snapshot["steps"][0]["output"]["artifacts"]["__result__"] == payload
    assert snapshot["run"]["workflow_outputs"]["__result__"] == payload

    workspace = WorkspaceRecord(id="w0", root=tmp_path, label="workspace")
    run_root = tmp_path / ".orchestrate" / "runs" / "value-projection"
    run_root.mkdir(parents=True)
    detail = RunProjector().project_detail(
        RunRecord(
            workspace=workspace,
            run_dir_id="value-projection",
            run_root=run_root,
            state_path=run_root / "state.json",
            state=state,
            state_run_id="value-projection",
        )
    )
    assert detail.steps[0].artifacts["__result__"] == payload
    assert detail.workflow_outputs["__result__"] == payload
    assert detail.state["steps"][presentation_name]["artifacts"]["__result__"] == payload


def test_transportable_value_provider_supervision_consumes_generic_contract(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "value_supervision.orc",
        "2.19",
        "(defworkflow entry () -> Value "
        "(with-live-providers "
        "((worker "
        "(provider-result providers.worker "
        ":prompt prompts.worker :inputs () "
        ":timeout-sec 30 :returns Value)) "
        "(supervisor "
        "(provider-result providers.supervisor "
        ":prompt prompts.supervisor :inputs () "
        ":timeout-sec 20 :returns ProviderSteeringDirective) "
        ":observes worker)) "
        "worker))",
    )
    for prompt_name in ("worker", "supervisor"):
        prompt_path = tmp_path / "prompts" / f"{prompt_name}.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text("Prompt.\n", encoding="utf-8")

    result = compile_stage3_module(
        path,
        entry_workflow="entry",
        provider_externs={
            "providers.worker": "codex",
            "providers.supervisor": "supervisor-provider",
        },
        prompt_externs={
            "prompts.worker": "prompts/worker.md",
            "prompts.supervisor": "prompts/supervisor.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )
    bundle = result.validated_bundles["entry"]
    node = next(iter(bundle.ir.nodes.values()))

    assert isinstance(node.execution_config, ProviderSupervisionStepConfig)
    worker_contract = (
        node.execution_config.worker.provider_config.common.output_bundle
    )
    assert worker_contract["fields"][0]["json_pointer"] == ""
    assert worker_contract["fields"][0]["type"] == "value"
    assert bundle.surface.outputs["__result__"].definition["kind"] == "value"
    assert bundle.surface.outputs["__result__"].definition["type"] == "value"
