import json
from pathlib import Path

import pytest

import orchestrator.workflow_lisp.syntax as syntax
from orchestrator.observability.report import build_status_snapshot
from tests.fixtures.historical_observability_bundles import HISTORICAL_OBSERVABILITY_BUNDLES
from orchestrator.dashboard.models import RunRecord, WorkspaceRecord
from orchestrator.dashboard.projection import RunProjector
from orchestrator.workflow.executable_ir import ExecutableContract
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
from orchestrator.workflow_lisp.reader import read_sexpr_text
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
from orchestrator.workflow.typed_prompt_inputs import normalize_typed_prompt_input_entry, render_typed_prompt_inputs
from orchestrator.workflow_lisp.workflows import (
    ExternEnvironment,
    PromptExtern,
    ProviderExtern,
    WorkflowSignature,
)


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


def test_value_type_is_installed_for_current_source() -> None:
    assert "Value" in prelude_type_names_for_target("2.35")

    module = build_syntax_module(
        read_sexpr_text(
            _module_source("2.35", "(defrecord Box (payload Value))"),
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




@pytest.mark.parametrize("target_dsl", ("2.35", "2.36"))
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


@pytest.mark.parametrize("target_dsl", ("2.35", "2.36"))
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
            "(provider-bundle-path value :as BundlePath)",
            "provider_bundle_path_source_invalid",
        ),
        ("(+ value 1)", "pure_expr_operand_type_mismatch"),
        ("(list/length value)", "pure_expr_operand_type_mismatch"),
    ),
)
def test_value_operations_keep_the_existing_operation_owned_diagnostic(
    tmp_path: Path,
    source: str,
    expected_code: str,
) -> None:
    type_env = FrontendTypeEnvironment.from_module(compile_stage1_module(
        _write_module(
            tmp_path / "value_operation_types.orc",
            "2.35",
            '(defpath BundlePath :kind relpath :under ".orchestrate/runs" :must-exist true)',
        )
    ))
    expression = elaborate_expression(
        _expression(source),
        bound_names=frozenset({"value"}),
        target_dsl_version="2.35",
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
                "2.35",
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
            _module_source("2.35"),
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
            target_dsl_version="2.35",
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
        "2.35",
        "(defmodule value_pass_through)",
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

    )
    entry = result.typed_program.workflows["value_pass_through::entry"]
    assert dict(entry.signature.params)["payload"] == VALUE_TYPE
    assert entry.signature.return_type_ref == VALUE_TYPE
    assert "value_pass_through::child" in result.typed_program.workflows





















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


def test_transportable_value_report_and_dashboard_preserve_payload(
    tmp_path: Path,
) -> None:
    bundle = HISTORICAL_OBSERVABILITY_BUNDLES["obs-test"]
    [node_id, *_] = bundle.projection.ordered_execution_node_ids()
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
