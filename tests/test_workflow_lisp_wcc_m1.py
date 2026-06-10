from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
    compile_stage1_module,
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, PrimitiveTypeRef, RecordTypeRef, UnionTypeRef
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
from orchestrator.workflow_lisp.wcc.model import (
    WccFieldAccessAtom,
    WccHalt,
    WccIdentityFactory,
    WccInject,
    WccLet,
    WccLiteralAtom,
    WccNameAtom,
    WccRecordAtom,
)
from orchestrator.workflow_lisp.workflows import (
    ExternalToolBinding,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
VALID_FIXTURES = FIXTURES / "valid"
MODULE_FIXTURES = FIXTURES / "modules" / "valid"
CLI_FIXTURES = FIXTURES / "cli"
TYPE_FIXTURE = VALID_FIXTURES / "type_definitions.orc"


def _test_span(path: str = "wcc_m1_test.orc") -> SourceSpan:
    start = SourcePosition(path=path, line=1, column=1, offset=0)
    end = SourcePosition(path=path, line=1, column=8, offset=7)
    return SourceSpan(start=start, end=end)


def _type_env() -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(compile_stage1_module(TYPE_FIXTURE))


def _record_type(type_name: str) -> RecordTypeRef:
    resolved = _type_env().resolve_type(type_name, span=_test_span(), form_path=("workflow-lisp", "wcc-test"))
    assert isinstance(resolved, RecordTypeRef)
    return resolved


def _union_type(type_name: str) -> UnionTypeRef:
    resolved = _type_env().resolve_type(type_name, span=_test_span(), form_path=("workflow-lisp", "wcc-test"))
    assert isinstance(resolved, UnionTypeRef)
    return resolved


def _fixture_type_env(path: Path) -> FrontendTypeEnvironment:
    syntax_module = build_syntax_module(read_sexpr_file(path))
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return FrontendTypeEnvironment.from_module(module)


def _typed_workflow(path: Path, workflow_name: str):
    syntax_module = build_syntax_module(read_sexpr_file(path))
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    typed_workflows = typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=build_workflow_catalog(module, workflow_defs, type_env),
    )
    return next(workflow for workflow in typed_workflows if workflow.definition.name == workflow_name)


def _load_imported_bundle_bindings(tmp_path: Path) -> dict[str, object]:
    build_module = importlib.import_module("orchestrator.workflow_lisp.build")
    bindings = build_module.load_imported_workflow_bundle_manifest(
        CLI_FIXTURES / "imported_workflow_bundles.json",
        workspace_root=tmp_path,
        source_roots=(MODULE_FIXTURES / "imported_bundle_mix",),
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        command_boundaries_path=CLI_FIXTURES / "commands.json",
    )
    return {binding.canonical_key: binding.bundle for binding in bindings}


def _assert_wcc_route_unsupported(excinfo: pytest.ExceptionInfo[LispFrontendCompileError]) -> None:
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "wcc_lowering_route_unsupported"
    assert diagnostic.phase == "lowering"


def test_compile_stage3_module_defaults_to_legacy_route_for_unsupported_workflow(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_FIXTURES / "structured_results.orc",
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert result.lowered_workflows


def test_wcc_model_instantiates_representative_nodes_with_stable_metadata() -> None:
    scope = WccIdentityFactory(owner_name="demo::workflow", lexical_owner_chain=("workflow",))
    span = _test_span()
    form_path = ("workflow-lisp", "defworkflow", "orchestrate")
    record_type = _record_type("ChecksResult")
    union_type = _union_type("ImplementationState")
    string_type = PrimitiveTypeRef(name="String")

    literal = WccLiteralAtom(
        metadata=scope.atom_metadata(
            role="literal:status",
            type_ref=string_type,
            source_span=span,
            form_path=form_path,
        ),
        value="ready",
        literal_kind="string",
    )
    name = WccNameAtom(
        metadata=scope.atom_metadata(
            role="name:input",
            type_ref=record_type,
            source_span=span,
            form_path=form_path,
        ),
        name="input",
    )
    field = WccFieldAccessAtom(
        metadata=scope.atom_metadata(
            role="field:input.status",
            type_ref=string_type,
            source_span=span,
            form_path=form_path,
        ),
        base=name,
        fields=("status",),
    )
    record = WccRecordAtom(
        metadata=scope.atom_metadata(
            role="record:ChecksResult",
            type_ref=record_type,
            source_span=span,
            form_path=form_path,
        ),
        type_name="ChecksResult",
        fields=(("status", field), ("report", name)),
    )
    inject = WccInject(
        metadata=scope.value_metadata(
            role="inject:COMPLETED",
            type_ref=union_type,
            source_span=span,
            form_path=form_path,
        ),
        union_name="ImplementationState",
        variant_name="COMPLETED",
        fields=(("execution_report", name),),
    )
    halt = WccHalt(
        metadata=scope.body_metadata(
            role="halt:return",
            type_ref=union_type,
            source_span=span,
            form_path=form_path,
        ),
        result=record,
    )
    let = WccLet(
        metadata=scope.body_metadata(
            role="let:attempt",
            type_ref=union_type,
            source_span=span,
            form_path=form_path,
        ),
        bound_name="attempt",
        bound_type_ref=union_type,
        bound_value=inject,
        body=halt,
    )

    assert literal.metadata.effect_summary.direct_effects == frozenset()
    assert literal.metadata.proof_context == ()
    assert literal.metadata.allocation_requests == ()
    assert field.base.name == "input"
    assert record.fields[0][0] == "status"
    assert inject.variant_name == "COMPLETED"
    assert let.bound_name == "attempt"
    assert let.body.result.type_name == "ChecksResult"


def test_wcc_identity_factory_is_stable_for_same_semantic_inputs() -> None:
    span = _test_span()
    form_path = ("workflow-lisp", "defworkflow", "orchestrate")
    scope = WccIdentityFactory(owner_name="demo::workflow", lexical_owner_chain=("workflow",))
    string_type = PrimitiveTypeRef(name="String")

    left = scope.atom_metadata(
        role="literal:status",
        type_ref=string_type,
        source_span=span,
        form_path=form_path,
    )
    right = scope.atom_metadata(
        role="literal:status",
        type_ref=string_type,
        source_span=span,
        form_path=form_path,
    )
    generated = scope.child_scope("anf", authored_binding_name="attempt")
    generated_left = generated.atom_metadata(
        role="generated:tmp0",
        type_ref=string_type,
        source_span=span,
        form_path=form_path,
    )
    generated_right = generated.atom_metadata(
        role="generated:tmp0",
        type_ref=string_type,
        source_span=span,
        form_path=form_path,
    )

    assert left.node_id == right.node_id
    assert left.scope_id == right.scope_id
    assert generated.scope_id != scope.scope_id
    assert generated_left.node_id == generated_right.node_id


def test_elaboration_preserves_authored_let_order_variant_identity_and_provenance() -> None:
    fixture = VALID_FIXTURES / "wcc_m1_value_union_letstar.orc"
    typed_workflow = _typed_workflow(fixture, "value-union-letstar")

    elaborated = elaborate_typed_workflow_body(
        typed_workflow.typed_body,
        owner_name=typed_workflow.definition.name,
        type_env=_fixture_type_env(fixture),
        value_env=dict(typed_workflow.signature.params),
    )

    assert isinstance(elaborated, WccLet)
    assert elaborated.bound_name == "nested"
    assert isinstance(elaborated.body, WccLet)
    assert elaborated.body.bound_name == "execution-report"
    assert isinstance(elaborated.body.body, WccLet)
    assert elaborated.body.body.bound_name == "attempt"
    assert isinstance(elaborated.body.body.bound_value, WccInject)
    assert elaborated.body.body.bound_value.variant_name == "COMPLETED"
    assert elaborated.metadata.source_span.start.path.endswith("wcc_m1_value_union_letstar.orc")
    assert elaborated.metadata.form_path[:2] == ("workflow-lisp", "defworkflow")


@pytest.mark.parametrize(
    ("fixture_name", "workflow_name"),
    (("wcc_m1_value_union_letstar.orc", "value-union-letstar"),),
)
def test_elaboration_is_total_for_covered_positive_fixtures(fixture_name: str, workflow_name: str) -> None:
    fixture = VALID_FIXTURES / fixture_name
    typed_workflow = _typed_workflow(fixture, workflow_name)

    elaborated = elaborate_typed_workflow_body(
        typed_workflow.typed_body,
        owner_name=typed_workflow.definition.name,
        type_env=_fixture_type_env(fixture),
        value_env=dict(typed_workflow.signature.params),
    )

    assert isinstance(elaborated, WccLet | WccHalt)


def test_anf_normalization_atomizes_non_atomic_record_and_inject_fields() -> None:
    scope = WccIdentityFactory(owner_name="demo::workflow", lexical_owner_chain=("workflow",))
    span = _test_span("wcc_anf_record.orc")
    form_path = ("workflow-lisp", "defworkflow", "normalize-record")
    union_type = _union_type("ImplementationState")
    record_type = _record_type("NestedImplementationSummary")

    report = WccNameAtom(
        metadata=scope.atom_metadata(
            role="name:report_path",
            type_ref=PrimitiveTypeRef(name="PathRel"),
            source_span=span,
            form_path=form_path,
        ),
        name="report_path",
    )
    nested_inject = WccInject(
        metadata=scope.value_metadata(
            role="inject:inner",
            type_ref=union_type,
            source_span=span,
            form_path=form_path,
        ),
        union_name="ImplementationState",
        variant_name="COMPLETED",
        fields=(("execution_report", report),),
    )
    body = WccHalt(
        metadata=scope.body_metadata(
            role="halt:return",
            type_ref=record_type,
            source_span=span,
            form_path=form_path,
        ),
        result=WccRecordAtom(
            metadata=scope.atom_metadata(
                role="record:NestedImplementationSummary",
                type_ref=record_type,
                source_span=span,
                form_path=form_path,
            ),
            type_name="NestedImplementationSummary",
            fields=(("summary", nested_inject),),
        ),
    )

    normalized = normalize_wcc_body_to_anf(body)

    assert isinstance(normalized, WccLet)
    assert isinstance(normalized.body, WccHalt)
    assert isinstance(normalized.body.result, WccRecordAtom)
    assert isinstance(normalized.body.result.fields[0][1], WccNameAtom)


def test_anf_generated_temporaries_preserve_authored_provenance_and_halt_with_atom() -> None:
    scope = WccIdentityFactory(owner_name="demo::workflow", lexical_owner_chain=("workflow",))
    span = _test_span("wcc_anf_inject.orc")
    form_path = ("workflow-lisp", "defworkflow", "normalize-inject")
    union_type = _union_type("ImplementationState")

    report = WccNameAtom(
        metadata=scope.atom_metadata(
            role="name:report_path",
            type_ref=PrimitiveTypeRef(name="PathRel"),
            source_span=span,
            form_path=form_path,
        ),
        name="report_path",
    )
    inner_inject = WccInject(
        metadata=scope.value_metadata(
            role="inject:inner",
            type_ref=union_type,
            source_span=span,
            form_path=form_path,
        ),
        union_name="ImplementationState",
        variant_name="COMPLETED",
        fields=(("execution_report", report),),
    )
    outer_inject = WccInject(
        metadata=scope.value_metadata(
            role="inject:outer",
            type_ref=union_type,
            source_span=span,
            form_path=form_path,
        ),
        union_name="ImplementationState",
        variant_name="BLOCKED",
        fields=(("progress_report", inner_inject),),
    )

    normalized = normalize_wcc_body_to_anf(
        WccHalt(
            metadata=scope.body_metadata(
                role="halt:return",
                type_ref=union_type,
                source_span=span,
                form_path=form_path,
            ),
            result=outer_inject,
        )
    )

    assert isinstance(normalized, WccLet)
    assert normalized.metadata.source_span == inner_inject.metadata.source_span
    assert normalized.bound_name.startswith("__wcc_anf_")
    assert isinstance(normalized.body, WccLet)
    assert isinstance(normalized.body.body, WccHalt)
    assert isinstance(normalized.body.body.result, WccNameAtom)


def test_wcc_m1_route_compiles_pure_value_workflow_and_validates_shared_bundle(tmp_path: Path) -> None:
    fixture = VALID_FIXTURES / "wcc_m1_value_union_letstar.orc"

    result = compile_stage3_module(
        fixture,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m1",
    )

    workflow_name = "value-union-letstar"
    assert workflow_name in result.validated_bundles
    assert result.lowered_workflows


def test_compile_stage3_module_rejects_unsupported_wcc_m1_route_before_lowering(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            VALID_FIXTURES / "structured_results.orc",
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                ),
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="wcc_m1",
        )

    _assert_wcc_route_unsupported(excinfo)


def test_compile_stage3_entrypoint_supports_explicit_legacy_route_for_module_graph(tmp_path: Path) -> None:
    result = compile_stage3_entrypoint(
        MODULE_FIXTURES / "callables" / "neurips" / "entry.orc",
        source_roots=(MODULE_FIXTURES / "callables",),
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
        },
        lowering_route="legacy",
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert result.entry_result.lowered_workflows


def test_compile_stage3_entrypoint_rejects_unsupported_wcc_m1_route_for_module_graph(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            MODULE_FIXTURES / "callables" / "neurips" / "entry.orc",
            source_roots=(MODULE_FIXTURES / "callables",),
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                ),
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="wcc_m1",
        )

    _assert_wcc_route_unsupported(excinfo)


@pytest.mark.parametrize(
    ("fixture_path", "compile_kwargs"),
    (
        (
            VALID_FIXTURES / "structured_results.orc",
            {
                "provider_externs": {"providers.execute": "fake"},
                "prompt_externs": {"prompts.implementation.execute": "prompts/implementation/execute.md"},
                "command_boundaries": {
                    "run_checks": ExternalToolBinding(
                        name="run_checks",
                        stable_command=("python", "scripts/run_checks.py"),
                    ),
                },
            },
        ),
        (
            FIXTURES / "characterization" / "sources" / "wcc_m2_straight_line_effects.orc",
            {
                "provider_externs": {"providers.execute": "fake"},
                "prompt_externs": {"prompts.implementation.execute": "prompts/implementation/execute.md"},
                "command_boundaries": {
                    "run_checks": ExternalToolBinding(
                        name="run_checks",
                        stable_command=("python", "scripts/run_checks.py"),
                    ),
                },
            },
        ),
        (
            VALID_FIXTURES / "proc_ref_bind_proc_forwarding.orc",
            {
                "command_boundaries": {
                    "run_checks": ExternalToolBinding(
                        name="run_checks",
                        stable_command=("python", "scripts/run_checks.py"),
                    ),
                },
            },
        ),
        (
            VALID_FIXTURES / "workflow_refs_same_file.orc",
            {
                "command_boundaries": {
                    "run_checks": ExternalToolBinding(
                        name="run_checks",
                        stable_command=("python", "scripts/run_checks.py"),
                    ),
                },
            },
        ),
        (
            VALID_FIXTURES / "neurips_implementation_attempt.orc",
            {
                "provider_externs": {"providers.execute": "fake"},
                "prompt_externs": {"prompts.implementation.execute": "prompts/implementation/execute.md"},
            },
        ),
        (
            VALID_FIXTURES / "loop_recur_minimal.orc",
            {
                "provider_externs": {"providers.execute": "fake"},
                "prompt_externs": {"prompts.implementation.execute": "prompts/implementation/execute.md"},
            },
        ),
        (
            VALID_FIXTURES / "phase_stdlib_review_loop.orc",
            {
                "provider_externs": {
                    "providers.review": "fake-review",
                    "providers.fix": "fake-fix",
                },
                "prompt_externs": {
                    "prompts.implementation.review": "prompts/implementation/review.md",
                    "prompts.implementation.fix": "prompts/implementation/fix.md",
                },
                "command_boundaries": {
                    "validate_review_findings_v1": ExternalToolBinding(
                        name="validate_review_findings_v1",
                        stable_command=(
                            "python",
                            "-m",
                            "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
                        ),
                    ),
                },
            },
        ),
    ),
)
def test_wcc_m1_route_rejects_unsupported_real_fixtures_before_lowering(
    tmp_path: Path,
    fixture_path: Path,
    compile_kwargs: dict[str, object],
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            fixture_path,
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="wcc_m1",
            **compile_kwargs,
        )

    _assert_wcc_route_unsupported(excinfo)


def test_wcc_m1_route_reaches_imported_bundle_mix_entrypoint_path_and_fails_early(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            MODULE_FIXTURES / "imported_bundle_mix" / "neurips" / "entry.orc",
            source_roots=(MODULE_FIXTURES / "imported_bundle_mix",),
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            imported_workflow_bundles=_load_imported_bundle_bindings(tmp_path),
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                ),
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="wcc_m1",
        )

    _assert_wcc_route_unsupported(excinfo)
