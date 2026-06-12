from dataclasses import FrozenInstanceError
import importlib
from pathlib import Path

import pytest

from orchestrator.exceptions import ValidationError, ValidationSubjectRef, WorkflowValidationError
from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import compile_stage1_module
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint as _compile_stage3_entrypoint
from orchestrator.workflow_lisp.compiler import compile_stage3_module as _compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
    render_diagnostic,
    render_diagnostics,
    with_diagnostic_metadata,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
MODULE_FIXTURES = FIXTURES / "modules"
INVALID_IF_NOT_BOOL_FIXTURE = FIXTURES / "invalid" / "if_condition_not_bool.orc"
INVALID_IF_EFFECTFUL_FIXTURE = FIXTURES / "invalid" / "if_condition_effectful.orc"
INVALID_IF_NOT_PROJECTABLE_FIXTURE = FIXTURES / "invalid" / "if_condition_not_projectable.orc"
INVALID_PURE_EXPR_OPERATOR_UNSUPPORTED_FIXTURE = FIXTURES / "invalid" / "pure_expr_operator_unsupported.orc"
INVALID_PURE_EXPR_UNION_EQUALITY_FIXTURE = FIXTURES / "invalid" / "pure_expr_union_equality.orc"
INVALID_PURE_EXPR_FLOAT_EQUALITY_FIXTURE = FIXTURES / "invalid" / "pure_expr_float_equality.orc"
INVALID_PURE_EXPR_PATH_STRING_CONCAT_FIXTURE = FIXTURES / "invalid" / "pure_expr_path_string_concat.orc"
INVALID_PURE_EXPR_OPTIONAL_ACCESS_FIXTURE = FIXTURES / "invalid" / "pure_expr_optional_access_unproved.orc"
INVALID_PURE_EXPR_COMPUTED_IF_VARIANT_REF_FIXTURE = (
    FIXTURES / "invalid" / "pure_expr_computed_if_variant_ref_unproved.orc"
)
PURE_EXPR_HELPER_DIAGNOSTIC_FIXTURES = frozenset(
    {
        INVALID_PURE_EXPR_UNION_EQUALITY_FIXTURE,
        INVALID_PURE_EXPR_FLOAT_EQUALITY_FIXTURE,
        INVALID_PURE_EXPR_OPTIONAL_ACCESS_FIXTURE,
        INVALID_PURE_EXPR_COMPUTED_IF_VARIANT_REF_FIXTURE,
    }
)
TRANSITION_DIAGNOSTIC_FIXTURES = (
    (
        FIXTURES / "invalid" / "resource_transition_unknown_transition.orc",
        "transition_unknown",
    ),
    (
        FIXTURES / "invalid" / "resource_transition_resource_kind_mismatch.orc",
        "transition_resource_kind_mismatch",
    ),
    (
        FIXTURES / "invalid" / "resource_transition_undeclared_update_target.orc",
        "transition_update_target_unknown",
    ),
)


def _compiler_module():
    return importlib.import_module("orchestrator.workflow_lisp.compiler")


def compile_stage3_entrypoint(*args, **kwargs):
    kwargs.setdefault("lowering_route", "legacy")
    return _compile_stage3_entrypoint(*args, **kwargs)


def compile_stage3_module(*args, **kwargs):
    kwargs.setdefault("lowering_route", "legacy")
    return _compile_stage3_module(*args, **kwargs)


def test_render_diagnostic_includes_location_and_form_path() -> None:
    start = SourcePosition(
        path="tests/fixtures/workflow_lisp/invalid/example.orc",
        line=3,
        column=5,
        offset=18,
    )
    end = SourcePosition(
        path="tests/fixtures/workflow_lisp/invalid/example.orc",
        line=3,
        column=14,
        offset=27,
    )
    span = SourceSpan(start=start, end=end)
    diagnostic = LispFrontendDiagnostic(
        code="frontend_parse_error",
        message="unexpected closing parenthesis",
        span=span,
        form_path=("workflow-lisp", "defrecord", "ChecksResult"),
        notes=("while reading field list",),
    )

    rendered = render_diagnostic(diagnostic)

    assert "tests/fixtures/workflow_lisp/invalid/example.orc:3:5" in rendered
    assert "[frontend_parse_error]" in rendered
    assert "unexpected closing parenthesis" in rendered
    assert "workflow-lisp > defrecord > ChecksResult" in rendered
    assert "while reading field list" in rendered
    assert render_diagnostics((diagnostic,)) == rendered

    with pytest.raises(FrozenInstanceError):
        diagnostic.message = "mutated"


def test_frontend_compile_error_exposes_diagnostics_tuple() -> None:
    span = SourceSpan(
        start=SourcePosition(path="module.orc", line=1, column=1, offset=0),
        end=SourcePosition(path="module.orc", line=1, column=6, offset=5),
    )
    diagnostics = (
        LispFrontendDiagnostic(
            code="definition_duplicate",
            message="duplicate definition `Thing`",
            span=span,
        ),
        LispFrontendDiagnostic(
            code="type_unknown",
            message="unknown type `Missing`",
            span=span,
        ),
    )

    error = LispFrontendCompileError(diagnostics)

    assert error.diagnostics == diagnostics
    assert isinstance(error.diagnostics, tuple)
    assert "[definition_duplicate]" in str(error)
    assert "[type_unknown]" in str(error)


def test_serialize_diagnostic_includes_phase_location_and_notes() -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")
    serialize_diagnostics = getattr(diagnostics_module, "serialize_diagnostics")

    span = SourceSpan(
        start=SourcePosition(
            path="tests/fixtures/workflow_lisp/invalid/example.orc",
            line=8,
            column=3,
            offset=42,
        ),
        end=SourcePosition(
            path="tests/fixtures/workflow_lisp/invalid/example.orc",
            line=8,
            column=17,
            offset=56,
        ),
    )
    diagnostic = LispFrontendDiagnostic(
        code="entry_workflow_required",
        message="`--entry-workflow` is required when more than one workflow is exported",
        span=span,
        form_path=("workflow-lisp", "defworkflow", "beta"),
        notes=("select one exported workflow explicitly",),
        phase="cli_request",
    )

    payload = serialize_diagnostic(diagnostic)

    assert payload["code"] == "entry_workflow_required"
    assert payload["severity"] == "error"
    assert payload["path"] == "tests/fixtures/workflow_lisp/invalid/example.orc"
    assert payload["line"] == 8
    assert payload["column"] == 3
    assert payload["form_path"] == ["workflow-lisp", "defworkflow", "beta"]
    assert payload["notes"] == ["select one exported workflow explicitly"]
    assert payload["phase"] == "cli_request"
    assert serialize_diagnostics((diagnostic,)) == [payload]


def test_required_lint_registry_contains_active_and_reserved_policy_metadata() -> None:
    lints_module = importlib.import_module("orchestrator.workflow_lisp.lints")
    registry = getattr(lints_module, "REQUIRED_LINT_REGISTRY")
    serialize_required_lint_registry = getattr(
        lints_module,
        "serialize_required_lint_registry",
    )

    expected_active = {
        "low_level_state_path_in_high_level_module": ("contract", "frontend", "warn", "error", "active"),
        "semantic_field_extracted_from_report": ("authority", "frontend", "error", "error", "active"),
        "markdown_report_used_as_state": ("authority", "frontend", "error", "error", "active"),
        "variant_output_without_variant_specific_fields": ("contract", "frontend", "warn", "error", "active"),
        "pointer_used_as_semantic_authority": ("authority", "frontend", "error", "error", "active"),
        "resource_move_without_transition": ("authority", "frontend", "error", "error", "active"),
        "recovery_gate_without_resume_or_start": ("authority", "frontend", "error", "error", "active"),
        "workflow_call_signature_erased": ("reference", "frontend", "error", "error", "active"),
        "macro_hidden_effect": ("effect", "frontend", "error", "error", "active"),
        "command_adapter_missing_contract": ("authority", "frontend", "error", "error", "active"),
        "inline_python_command_in_workflow": ("authority", "frontend", "error", "error", "active"),
        "inline_shell_command_in_workflow": ("authority", "frontend", "error", "error", "active"),
        "legacy_adapter_missing_fixture": ("authority", "frontend", "error", "error", "active"),
    }
    expected_reserved = {
        "manual_snapshot_name_in_high_level_module": ("contract", "frontend", "warn", "error", "reserved"),
        "manual_candidate_path_in_high_level_module": ("contract", "frontend", "warn", "error", "reserved"),
        "line_prefix_extractor_in_workflow": ("authority", "frontend", "error", "error", "reserved"),
        "manual_when_requires_variant_pair": ("proof", "frontend", "warn", "error", "reserved"),
        "string_status_gate_without_union_match": ("authority", "frontend", "error", "error", "reserved"),
        "inline_json_state_rewrite": ("authority", "frontend", "error", "error", "reserved"),
        "inline_pointer_write": ("authority", "frontend", "error", "error", "reserved"),
        "inline_subprocess_nested_command": ("authority", "frontend", "error", "error", "reserved"),
    }

    assert set(registry) == set(expected_active) | set(expected_reserved)

    for code, (
        expected_pass,
        expected_authority_layer,
        expected_default,
        expected_strict,
        expected_surface_status,
    ) in {**expected_active, **expected_reserved}.items():
        rule = registry[code]
        assert rule.code == code
        assert rule.owning_pass == expected_pass
        assert rule.authority_layer == expected_authority_layer
        assert rule.default_severity == expected_default
        assert rule.strict_severity == expected_strict
        assert rule.surface_status == expected_surface_status

    serialized = {
        entry["code"]: entry
        for entry in serialize_required_lint_registry()
    }
    for code, (
        expected_pass,
        expected_authority_layer,
        expected_default,
        expected_strict,
        expected_surface_status,
    ) in expected_reserved.items():
        assert serialized[code] == {
            "code": code,
            "owning_pass": expected_pass,
            "authority_layer": expected_authority_layer,
            "default_severity": expected_default,
            "strict_severity": expected_strict,
            "surface_status": expected_surface_status,
        }


def test_serialize_diagnostic_includes_diagnostic_kind_for_required_lints_and_validation() -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")

    span = SourceSpan(
        start=SourcePosition(
            path="tests/fixtures/workflow_lisp/valid/example.orc",
            line=12,
            column=5,
            offset=80,
        ),
        end=SourcePosition(
            path="tests/fixtures/workflow_lisp/valid/example.orc",
            line=12,
            column=19,
            offset=94,
        ),
    )

    lint_payload = serialize_diagnostic(
        LispFrontendDiagnostic(
            code="command_adapter_missing_contract",
            message="missing command adapter contract metadata",
            span=span,
        )
    )
    validation_payload = serialize_diagnostic(
        LispFrontendDiagnostic(
            code="workflow_call_unknown",
            message="unknown workflow `missing`",
            span=span,
        )
    )

    assert lint_payload["diagnostic_kind"] == "required_lint"
    assert lint_payload["severity"] == "error"
    assert lint_payload["validation_pass"] == "authority"
    assert lint_payload["authority_layer"] == "frontend"

    assert validation_payload["diagnostic_kind"] == "validation"
    assert validation_payload["severity"] == "error"
    assert validation_payload["validation_pass"] == "type"
    assert validation_payload["authority_layer"] == "frontend"


@pytest.mark.parametrize(
    ("code", "expected_phase", "expected_validation_pass", "expected_authority_layer"),
    [
        (
            "command_adapter_missing_contract",
            "lowering",
            "authority",
            "frontend",
        ),
        (
            "source_map_validation_ref_missing",
            "source_map",
            "source_map",
            "frontend",
        ),
        (
            "workflow_call_version_mismatch",
            "shared_validation",
            "shared_validation",
            "shared_validation",
        ),
        (
            "stdlib_special_form_disallowed",
            "typecheck",
            "contract",
            "frontend",
        ),
        (
            "review_loop_special_lowerer_used",
            "lowering",
            "lowering_surface",
            "frontend",
        ),
    ],
)
def test_serialize_diagnostic_infers_validation_metadata_from_code(
    code: str,
    expected_phase: str,
    expected_validation_pass: str,
    expected_authority_layer: str,
) -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")

    span = SourceSpan(
        start=SourcePosition(
            path="tests/fixtures/workflow_lisp/invalid/example.orc",
            line=12,
            column=7,
            offset=84,
        ),
        end=SourcePosition(
            path="tests/fixtures/workflow_lisp/invalid/example.orc",
            line=12,
            column=19,
            offset=96,
        ),
    )
    diagnostic = LispFrontendDiagnostic(
        code=code,
        message="deterministic metadata test",
        span=span,
        form_path=("workflow-lisp", "defworkflow", "orchestrate"),
        notes=("preserve notes",),
    )

    payload = serialize_diagnostic(diagnostic)

    assert payload["code"] == code
    assert payload["path"] == "tests/fixtures/workflow_lisp/invalid/example.orc"
    assert payload["line"] == 12
    assert payload["column"] == 7
    assert payload["form_path"] == ["workflow-lisp", "defworkflow", "orchestrate"]
    assert payload["notes"] == ["preserve notes"]
    assert payload["phase"] == expected_phase
    assert payload["validation_pass"] == expected_validation_pass
    assert payload["authority_layer"] == expected_authority_layer


@pytest.mark.parametrize(
    ("code", "expected_phase", "expected_validation_pass"),
    [
        ("runtime_closure_not_enabled", "typecheck", "type"),
        ("closure_family_unknown", "typecheck", "type"),
        ("closure_resume_bundle_mismatch", "executable", "executable"),
        ("closure_resume_code_mismatch", "executable", "executable"),
        ("closure_source_map_missing", "source_map", "source_map"),
    ],
)
def test_serialize_diagnostic_infers_runtime_closure_metadata(
    code: str,
    expected_phase: str,
    expected_validation_pass: str,
) -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")

    span = SourceSpan(
        start=SourcePosition(
            path="tests/fixtures/workflow_lisp/design/runtime_closure_fixtures.orc",
            line=21,
            column=9,
            offset=120,
        ),
        end=SourcePosition(
            path="tests/fixtures/workflow_lisp/design/runtime_closure_fixtures.orc",
            line=21,
            column=21,
            offset=132,
        ),
    )
    payload = serialize_diagnostic(
        LispFrontendDiagnostic(
            code=code,
            message="runtime closure metadata test",
            span=span,
        )
    )

    assert payload["phase"] == expected_phase
    assert payload["validation_pass"] == expected_validation_pass
    assert payload["authority_layer"] == "frontend"


def test_run_validation_pipeline_continues_after_warning_required_lint_default_profile() -> None:
    validation_module = importlib.import_module("orchestrator.workflow_lisp.validation")
    pipeline_state_cls = getattr(validation_module, "ValidationPipelineState")
    pipeline_pass_cls = getattr(validation_module, "ValidationPipelinePass")
    run_validation_pipeline = getattr(validation_module, "run_validation_pipeline")

    span = SourceSpan(
        start=SourcePosition(path="pipeline.orc", line=1, column=1, offset=0),
        end=SourcePosition(path="pipeline.orc", line=1, column=8, offset=7),
    )
    call_order: list[str] = []

    def mark(name: str):
        def runner(state):
            call_order.append(name)
            return state

        return runner

    def warn_contract(state):
        del state
        call_order.append("contract")
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="low_level_state_path_in_high_level_module",
                    message="manual state path authoring should use derived context paths",
                    span=span,
                ),
            )
        )

    _, results = run_validation_pipeline(
        pipeline_state_cls(),
        (
            pipeline_pass_cls(pass_id="parse", runner=mark("parse")),
            pipeline_pass_cls(pass_id="contract", runner=warn_contract),
            pipeline_pass_cls(pass_id="executable", runner=mark("executable")),
        ),
        lint_profile="default",
    )

    assert call_order == ["parse", "contract", "executable"]
    assert [result.pass_id for result in results] == ["parse", "contract", "executable"]
    assert results[1].blocking is False
    assert results[1].diagnostics[0].code == "low_level_state_path_in_high_level_module"


def test_raise_pipeline_diagnostics_escalates_warning_required_lints_in_strict_profile() -> None:
    validation_module = importlib.import_module("orchestrator.workflow_lisp.validation")
    result_cls = getattr(validation_module, "ValidationPassResult")
    raise_pipeline_diagnostics = getattr(validation_module, "raise_pipeline_diagnostics")

    span = SourceSpan(
        start=SourcePosition(path="pipeline.orc", line=1, column=1, offset=0),
        end=SourcePosition(path="pipeline.orc", line=1, column=8, offset=7),
    )
    warning_result = result_cls(
        pass_id="contract",
        authority_layer="frontend",
        blocking=False,
        diagnostics=(
            LispFrontendDiagnostic(
                code="variant_output_without_variant_specific_fields",
                message="union return contract has no variant-specific fields",
                span=span,
            ),
        ),
        artifact_ready=True,
    )
    validation_result = result_cls(
        pass_id="type",
        authority_layer="frontend",
        blocking=True,
        diagnostics=(
            LispFrontendDiagnostic(
                code="workflow_call_unknown",
                message="unknown workflow `missing`",
                span=span,
            ),
        ),
        artifact_ready=False,
    )

    raise_pipeline_diagnostics((warning_result,), lint_profile="default")

    with pytest.raises(LispFrontendCompileError):
        raise_pipeline_diagnostics((warning_result,), lint_profile="strict")

    with pytest.raises(LispFrontendCompileError):
        raise_pipeline_diagnostics((validation_result,), lint_profile="default")


def test_run_validation_pipeline_stops_after_blocking_pass() -> None:
    validation_module = importlib.import_module("orchestrator.workflow_lisp.validation")
    pipeline_state_cls = getattr(validation_module, "ValidationPipelineState")
    pipeline_pass_cls = getattr(validation_module, "ValidationPipelinePass")
    run_validation_pipeline = getattr(validation_module, "run_validation_pipeline")

    span = SourceSpan(
        start=SourcePosition(path="pipeline.orc", line=1, column=1, offset=0),
        end=SourcePosition(path="pipeline.orc", line=1, column=8, offset=7),
    )
    call_order: list[str] = []

    def mark(name: str):
        def runner(state):
            call_order.append(name)
            return state

        return runner

    def fail_authority(state):
        del state
        call_order.append("authority")
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="command_adapter_missing_contract",
                    message="missing contract metadata",
                    span=span,
                ),
            )
        )

    _, results = run_validation_pipeline(
        pipeline_state_cls(),
        (
            pipeline_pass_cls(pass_id="parse", runner=mark("parse")),
            pipeline_pass_cls(pass_id="module", runner=mark("module")),
            pipeline_pass_cls(pass_id="authority", runner=fail_authority),
            pipeline_pass_cls(pass_id="shared_validation", runner=mark("shared_validation")),
        ),
    )

    assert call_order == ["parse", "module", "authority"]
    assert [result.pass_id for result in results] == ["parse", "module", "authority"]
    assert results[-1].blocking is True
    assert results[-1].diagnostics[0].validation_pass == "authority"
    assert results[-1].diagnostics[0].authority_layer == "frontend"


def test_stage3_validation_pipeline_reports_authority_as_blocking_pass(tmp_path: Path) -> None:
    compiler_module = _compiler_module()
    run_pipeline = getattr(compiler_module, "_run_stage3_validation_pipeline")

    _, results = run_pipeline(
        FIXTURES / "valid" / "structured_results.orc",
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        imported_workflow_bundles=None,
        command_boundaries=None,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert [result.pass_id for result in results] == [
        "parse",
        "module",
        "macro",
        "type",
        "effect",
        "reference",
        "contract",
        "proof",
        "authority",
    ]
    assert results[-1].blocking is True
    assert results[-1].diagnostics[0].code == "command_adapter_missing_contract"
    assert results[-1].diagnostics[0].validation_pass == "authority"


def test_stage3_validation_pipeline_preserves_source_map_metadata_from_shared_bridge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    compiler_module = _compiler_module()
    span = SourceSpan(
        start=SourcePosition(path="probe.orc", line=1, column=1, offset=0),
        end=SourcePosition(path="probe.orc", line=1, column=8, offset=7),
    )

    def fake_validate_lowered_workflows(*args, **kwargs):
        del args, kwargs
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="source_map_validation_ref_missing",
                    message="missing validation subject coverage",
                    span=span,
                    validation_pass="source_map",
                    authority_layer="frontend",
                ),
            )
        )

    monkeypatch.setattr(
        compiler_module,
        "validate_lowered_workflows",
        fake_validate_lowered_workflows,
    )

    _, results = compiler_module._run_stage3_validation_pipeline(
        FIXTURES / "valid" / "structured_results.orc",
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        imported_workflow_bundles=None,
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert results[-1].pass_id == "source_map"
    assert results[-1].diagnostics[0].validation_pass == "source_map"
    assert results[-1].diagnostics[0].authority_layer == "frontend"


def test_stage1_validation_pipeline_routes_module_compile_through_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiler_module = _compiler_module()
    original = compiler_module.run_validation_pipeline
    observed_pass_ids: list[tuple[str, ...]] = []

    def wrapped(*args, **kwargs):
        passes = kwargs.get("passes")
        if passes is None and len(args) >= 2:
            passes = args[1]
        observed_pass_ids.append(tuple(p.pass_id for p in passes))
        return original(*args, **kwargs)

    monkeypatch.setattr(compiler_module, "run_validation_pipeline", wrapped)

    compile_stage1_module(MODULE_FIXTURES / "valid" / "callables" / "neurips" / "types.orc")

    assert observed_pass_ids


def test_stage1_validation_pipeline_routes_entrypoint_compile_through_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiler_module = _compiler_module()
    original = compiler_module.run_validation_pipeline
    observed_pass_ids: list[tuple[str, ...]] = []

    def wrapped(*args, **kwargs):
        passes = kwargs.get("passes")
        if passes is None and len(args) >= 2:
            passes = args[1]
        observed_pass_ids.append(tuple(p.pass_id for p in passes))
        return original(*args, **kwargs)

    monkeypatch.setattr(compiler_module, "run_validation_pipeline", wrapped)

    compiler_module.compile_stage1_entrypoint(
        MODULE_FIXTURES / "valid" / "callables" / "neurips" / "entry.orc",
        source_roots=(MODULE_FIXTURES / "valid" / "callables",),
    )

    assert observed_pass_ids


def test_stage3_validation_pipeline_runs_source_map_and_executable_passes(tmp_path: Path) -> None:
    compiler_module = _compiler_module()

    _, results = compiler_module._run_stage3_validation_pipeline(
        FIXTURES / "valid" / "structured_results.orc",
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        imported_workflow_bundles=None,
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert [result.pass_id for result in results] == [
        "parse",
        "module",
        "macro",
        "type",
        "effect",
        "reference",
        "contract",
        "proof",
        "authority",
        "lowering_surface",
        "source_map",
        "shared_validation",
        "executable",
    ]


def test_compile_stage3_entrypoint_routes_through_validation_pipeline(tmp_path: Path) -> None:
    compiler_module = _compiler_module()
    run_pipeline = getattr(
        compiler_module,
        "_run_stage3_entrypoint_validation_pipeline",
        None,
    )
    assert callable(run_pipeline), "_run_stage3_entrypoint_validation_pipeline is missing"

    _, results = run_pipeline(
        MODULE_FIXTURES / "valid" / "callables" / "neurips" / "entry.orc",
        source_roots=(MODULE_FIXTURES / "valid" / "callables",),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md"
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert [result.pass_id for result in results] == [
        "parse",
        "module",
        "macro",
        "type",
        "effect",
        "reference",
        "contract",
        "proof",
        "authority",
        "lowering_surface",
        "source_map",
        "shared_validation",
        "executable",
    ]


@pytest.mark.parametrize(("path", "expected_code"), TRANSITION_DIAGNOSTIC_FIXTURES)
def test_declared_resource_transition_diagnostics_classify_as_typecheck_validation(
    path: Path,
    expected_code: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False)

    diagnostic = with_diagnostic_metadata(excinfo.value.diagnostics[0])
    assert diagnostic.code == expected_code
    assert diagnostic.phase == "typecheck"
    assert diagnostic.validation_pass == "type"
    assert diagnostic.authority_layer == "frontend"


def test_compile_stage3_entrypoint_runs_source_map_and_executable_checkpoints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    compiler_module = _compiler_module()
    original_build_source_map_document = compiler_module.build_source_map_document
    selected_workflow_validation_states: list[bool] = []

    def wrapped_build_source_map_document(*args, **kwargs):
        compile_result = args[0]
        selected_name = kwargs["selected_name"]
        selected_workflow_validation_states.append(
            selected_name in compile_result.validated_bundles_by_name
        )
        return original_build_source_map_document(*args, **kwargs)

    monkeypatch.setattr(
        compiler_module,
        "build_source_map_document",
        wrapped_build_source_map_document,
    )

    compile_stage3_entrypoint(
        MODULE_FIXTURES / "valid" / "callables" / "neurips" / "entry.orc",
        source_roots=(MODULE_FIXTURES / "valid" / "callables",),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md"
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert selected_workflow_validation_states == [False, True]


def test_compile_stage3_entrypoint_revalidates_executable_ir_before_linked_source_map(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    compiler_module = _compiler_module()
    original_build_source_map_document = compiler_module.build_source_map_document
    call_log: list[tuple[str, object]] = []

    def wrapped_build_source_map_document(*args, **kwargs):
        compile_result = args[0]
        selected_name = kwargs["selected_name"]
        call_log.append(
            (
                "source_map",
                selected_name in compile_result.validated_bundles_by_name,
            )
        )
        return original_build_source_map_document(*args, **kwargs)

    def wrapped_validate_executable_workflow(ir):
        call_log.append(("validate", ir.name))

    monkeypatch.setattr(
        compiler_module,
        "build_source_map_document",
        wrapped_build_source_map_document,
    )
    monkeypatch.setattr(
        compiler_module,
        "validate_executable_workflow",
        wrapped_validate_executable_workflow,
        raising=False,
    )

    compile_stage3_entrypoint(
        MODULE_FIXTURES / "valid" / "callables" / "neurips" / "entry.orc",
        source_roots=(MODULE_FIXTURES / "valid" / "callables",),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md"
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert call_log[0] == ("source_map", False)
    assert call_log[-1] == ("source_map", True)
    assert all(kind == "validate" for kind, _ in call_log[1:-1])
    assert {name for _, name in call_log[1:-1]} == {
        "neurips/helper::provider-attempt",
        "neurips/helper::secondary",
        "neurips/entry::orchestrate",
    }


def test_compile_stage3_module_reports_post_shared_validation_executable_ir_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    compiler_module = _compiler_module()
    baseline = compile_stage3_module(
        FIXTURES / "valid" / "structured_results.orc",
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )
    command_checks = next(
        workflow
        for workflow in baseline.lowered_workflows
        if workflow.typed_workflow.definition.name == "command_checks"
    )
    step_subject = next(
        binding.subject_ref.subject_name
        for binding in command_checks.origin_map.validation_subject_bindings
        if binding.subject_ref.subject_kind == "step_id"
    )

    def fail_executable_revalidation(ir):
        raise WorkflowValidationError(
            [
                ValidationError(
                    message=(
                        "executable_ir_invalid: "
                        f"node `{ir.name}` contains invalid executable bridge state"
                    ),
                    subject_refs=(
                        ValidationSubjectRef(
                            subject_kind="step_id",
                            subject_name=step_subject,
                            workflow_name=command_checks.typed_workflow.definition.name,
                        ),
                    ),
                )
            ]
        )

    monkeypatch.setattr(
        compiler_module,
        "validate_executable_workflow",
        fail_executable_revalidation,
        raising=False,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            FIXTURES / "valid" / "structured_results.orc",
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                )
            },
            validate_shared=True,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "executable_ir_invalid"
    assert diagnostic.phase == "executable"
    assert diagnostic.validation_pass == "executable"
    assert diagnostic.span.start.path.endswith("structured_results.orc")


def test_compile_stage3_entrypoint_reports_post_shared_validation_executable_ir_failures_for_linked_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    compiler_module = _compiler_module()
    imported_bundle_source = tmp_path / "selector_run.orc"
    imported_bundle_source.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow selector-run",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs (input report_path)",
                "      :returns ImplementationSummary)))",
            ]
        ),
        encoding="utf-8",
    )
    imported_bundle = compile_stage3_module(
        imported_bundle_source,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    ).validated_bundles["selector-run"]

    def fail_linked_helper_executable_revalidation(ir):
        if ir.name != "neurips/helper::provider-attempt":
            return
        raise WorkflowValidationError(
            [
                ValidationError(
                    message=(
                        "executable_ir_invalid: "
                        f"workflow `{ir.name}` contains invalid executable bridge state"
                    ),
                    subject_refs=(
                        ValidationSubjectRef(
                            subject_kind="workflow",
                            subject_name=ir.name,
                            workflow_name=ir.name,
                        ),
                    ),
                )
            ]
        )

    monkeypatch.setattr(
        compiler_module,
        "validate_executable_workflow",
        fail_linked_helper_executable_revalidation,
        raising=False,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            MODULE_FIXTURES / "valid" / "imported_bundle_mix" / "neurips" / "entry.orc",
            source_roots=(MODULE_FIXTURES / "valid" / "imported_bundle_mix",),
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={
                "prompts.implementation.execute": "prompts/implementation/execute.md"
            },
            imported_workflow_bundles={"selector-run": imported_bundle},
            validate_shared=True,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "executable_ir_invalid"
    assert diagnostic.phase == "executable"
    assert diagnostic.validation_pass == "executable"
    assert diagnostic.span.start.path.endswith("helper.orc")


def test_serialize_diagnostic_preserves_typecheck_phase_for_missing_imported_workflow_bundle() -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            MODULE_FIXTURES / "valid" / "imported_bundle_mix" / "neurips" / "entry.orc",
            source_roots=(MODULE_FIXTURES / "valid" / "imported_bundle_mix",),
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={
                "prompts.implementation.execute": "prompts/implementation/execute.md"
            },
            validate_shared=False,
        )

    payload = serialize_diagnostic(excinfo.value.diagnostics[0])

    assert payload["code"] == "workflow_call_unknown"
    assert payload["phase"] == "typecheck"


def test_serialize_diagnostic_preserves_lowering_phase_for_cyclic_workflow_calls(tmp_path: Path) -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")

    path = tmp_path / "cyclic_workflows.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord Out",
                "    (status String))",
                "  (defworkflow alpha",
                "    ()",
                "    -> Out",
                "    (call beta))",
                "  (defworkflow beta",
                "    ()",
                "    -> Out",
                "    (call alpha)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False)

    payload = serialize_diagnostic(excinfo.value.diagnostics[0])

    assert payload["code"] == "workflow_signature_mismatch"
    assert payload["phase"] == "lowering"


def test_serialize_diagnostic_classifies_missing_command_boundary_as_authority() -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            MODULE_FIXTURES / "valid" / "callables" / "neurips" / "entry.orc",
            source_roots=(MODULE_FIXTURES / "valid" / "callables",),
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={
                "prompts.implementation.execute": "prompts/implementation/execute.md"
            },
            validate_shared=False,
        )

    payload = serialize_diagnostic(excinfo.value.diagnostics[0])

    assert payload["code"] == "command_adapter_missing_contract"
    assert payload["phase"] == "lowering"
    assert payload["validation_pass"] == "authority"
    assert payload["authority_layer"] == "frontend"


def test_serialize_diagnostic_preserves_command_result_adapter_invalid_phase(tmp_path: Path) -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")

    path = tmp_path / "command_result_adapter_invalid.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow normalize",
                "    ((report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (command-result normalize_result",
                '      :argv ("python" "scripts/normalize_result.py" report_path)',
                "      :adapter normalize_result",
                "      :inputs ((execution_report report_path))",
                "      :returns ImplementationSummary)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False, workspace_root=tmp_path)

    payload = serialize_diagnostic(excinfo.value.diagnostics[0])

    assert payload["code"] == "command_result_adapter_invalid"
    assert payload["phase"] == "read"


def test_serialize_diagnostic_classifies_command_adapter_input_not_projectable(tmp_path: Path) -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")

    path = tmp_path / "command_adapter_not_projectable.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord Wrapper",
                "    (payload WorkReport))",
                "  (defrecord ApprovedResult",
                "    (review_report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow normalize",
                "    ((completed Wrapper)",
                "     (approved ApprovedResult))",
                "    -> ImplementationSummary",
                "    (command-result wrap_result",
                "      :adapter wrap_result",
                "      :inputs",
                "        ((completed completed)",
                "         (review_report approved.review_report))",
                "      :returns ImplementationSummary)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            command_boundaries=_parse_command_boundaries_manifest(
                {
                    "wrap_result": {
                        "kind": "certified_adapter",
                        "stable_command": ["python", "scripts/wrap_result.py"],
                        "input_contract": {"type": "object"},
                        "output_type_name": "ImplementationSummary",
                        "effects": ["structured_result"],
                        "path_safety": {"kind": "workspace_relpath"},
                        "source_map_behavior": "step",
                        "fixture_ids": ["wrap_result_ok"],
                        "negative_fixture_ids": ["wrap_result_bad"],
                        "behavior_class": "structured_result",
                        "input_signature": [
                            {
                                "name": "completed",
                                "type_name": "Wrapper",
                                "required": True,
                                "transport_key": "completed",
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
                        "error_codes": ["wrap_result_invalid_payload"],
                        "owner_module": "std/phase",
                        "replacement_path": None,
                        "invocation_protocol": "json_object_positional_arg",
                    }
                },
                manifest_path=None,
            ),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    payload = serialize_diagnostic(excinfo.value.diagnostics[0])

    assert payload["code"] == "command_adapter_input_not_projectable"
    assert payload["phase"] == "typecheck"


def test_compile_stage3_preserves_low_level_state_path_warning_without_aborting(tmp_path: Path) -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")

    path = tmp_path / "low_level_state_path_warning.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath StateFile",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist false)",
                "  (defrecord RawStateOutput",
                "    (state_file StateFile))",
                "  (defworkflow orchestrate",
                "    ((state_file StateFile))",
                "    -> RawStateOutput",
                "    (record RawStateOutput",
                "      :state_file state_file)))",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(path, validate_shared=False, workspace_root=tmp_path)

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "low_level_state_path_in_high_level_module",
    ]
    payload = serialize_diagnostic(result.diagnostics[0])
    assert payload["diagnostic_kind"] == "required_lint"
    assert payload["severity"] == "warn"
    assert payload["validation_pass"] == "contract"


def test_compile_stage3_strict_lint_still_rejects_unrelated_public_state_path(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unrelated_public_state_path.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule unrelated_public_state_path)",
                "  (export orchestrate)",
                "  (defpath StateFile",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist false)",
                "  (defrecord RawStateOutput",
                "    (state_file StateFile))",
                "  (defworkflow orchestrate",
                "    ((state_file StateFile))",
                "    -> RawStateOutput",
                "    (record RawStateOutput",
                "      :state_file state_file)))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as exc_info:
        compile_stage3_module(
            path,
            validate_shared=False,
            lint_profile="strict",
            workspace_root=tmp_path,
        )

    assert "low_level_state_path_in_high_level_module" in {
        diagnostic.code for diagnostic in exc_info.value.diagnostics
    }


def test_compile_stage1_renders_unknown_type_diagnostic_with_field_location() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "unknown_type.orc")

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "unknown_type.orc:5:5" in rendered
    assert "[type_unknown]" in rendered
    assert "unknown type `MissingType`" in rendered
    assert "workflow-lisp > defrecord > ChecksResult" in rendered


def test_compile_stage1_renders_unsupported_target_dsl_diagnostic() -> None:
    parse_tree = read_sexpr_file(FIXTURES / "invalid" / "unsupported_target_dsl.orc")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_syntax_module(parse_tree)

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "unsupported_target_dsl.orc:3:16" in rendered
    assert "[target_dsl_unsupported]" in rendered
    assert "unsupported target DSL `2.15`" in rendered


def test_compile_stage1_preserves_diagnostic_order(tmp_path: Path) -> None:
    path = tmp_path / "multiple_errors.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord ProblemRecord",
                "    (status MissingA)",
                "    (status MissingB))",
                "  (defrecord ProblemRecord",
                "    (report MissingC)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(path)

    diagnostics = excinfo.value.diagnostics

    assert [diagnostic.code for diagnostic in diagnostics] == [
        "definition_duplicate",
        "record_field_duplicate",
        "type_unknown",
        "type_unknown",
        "type_unknown",
    ]


def test_compile_stage1_renders_macro_expansion_notes_in_stable_order() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "macro_emits_invalid_form.orc")

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "[macro_emits_invalid_ast]" in rendered
    assert "expanded from macro `broken-workflow` call at" in rendered
    assert "macro definition at" in rendered


def test_compile_stage3_renders_macro_expansion_notes_for_downstream_command_errors(tmp_path: Path) -> None:
    path = tmp_path / "macro_command_result_missing_boundary.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (emit-command-workflow command_checks)",
                "  (defmacro emit-command-workflow (name)",
                "    (defworkflow name",
                "      ((report_path WorkReport))",
                "      -> ChecksResult",
                "      (command-result run_checks",
                '        :argv ("python" "scripts/run_checks.py" report_path)',
                "        :returns ChecksResult))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False)

    diagnostic = excinfo.value.diagnostics[0]
    rendered = render_diagnostic(diagnostic)

    assert diagnostic.code == "macro_hidden_effect"
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-command-workflow"
    assert "expanded from macro `emit-command-workflow` call at" in rendered
    assert "macro definition at" in rendered


def test_compile_stage3_reports_macro_emitted_malformed_letstar_as_frontend_diagnostic(tmp_path: Path) -> None:
    path = tmp_path / "macro_emits_malformed_letstar.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord Out",
                "    (value String))",
                "  (emit-broken-workflow broken)",
                "  (defmacro emit-broken-workflow (name)",
                "    (defworkflow name",
                "      ()",
                "      -> Out",
                "      (let*))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False)

    diagnostic = excinfo.value.diagnostics[0]
    rendered = render_diagnostic(diagnostic)

    assert diagnostic.code == "frontend_parse_error"
    assert diagnostic.message == "`let*` requires a binding list and one body"
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-broken-workflow"
    assert "expanded from macro `emit-broken-workflow` call at" in rendered


def test_compile_stage3_renders_macro_expansion_notes_for_downstream_name_unknown_errors(tmp_path: Path) -> None:
    path = tmp_path / "macro_record_missing_name.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord Out",
                "    (value String))",
                "  (emit-record-workflow broken)",
                "  (defmacro emit-record-workflow (name)",
                "    (defworkflow name",
                "      ()",
                "      -> Out",
                "      (record Out :value missing_name))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False)

    diagnostic = excinfo.value.diagnostics[0]
    rendered = render_diagnostic(diagnostic)

    assert diagnostic.code == "name_unknown"
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-record-workflow"
    assert "expanded from macro `emit-record-workflow` call at" in rendered
    assert "macro definition at" in rendered


def test_compile_stage3_preserves_macro_provenance_without_reclassifying_downstream_validation_failures(
    tmp_path: Path,
) -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")

    path = tmp_path / "macro_record_missing_name_serialized.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord Out",
                "    (value String))",
                "  (emit-record-workflow broken)",
                "  (defmacro emit-record-workflow (name)",
                "    (defworkflow name",
                "      ()",
                "      -> Out",
                "      (record Out :value missing_name))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False)

    diagnostic = excinfo.value.diagnostics[0]
    payload = serialize_diagnostic(diagnostic)
    rendered = render_diagnostic(diagnostic)

    assert diagnostic.code == "name_unknown"
    assert payload["code"] == "name_unknown"
    assert payload["validation_pass"] == "type"
    assert payload["authority_layer"] == "frontend"
    assert payload["expansion_stack"][0]["macro_name"] == "emit-record-workflow"
    assert "expanded from macro `emit-record-workflow` call at" in rendered
    assert "macro definition at" in rendered


def test_compile_stage3_renders_nested_macro_notes_for_hidden_command_effect(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            FIXTURES / "invalid" / "macro_nested_hidden_command_effect.orc",
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                )
            },
            validate_shared=False,
            workspace_root=tmp_path,
        )

    rendered = render_diagnostic(excinfo.value.diagnostics[0])
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "macro_hidden_effect"
    assert [frame.macro_name for frame in diagnostic.expansion_stack] == [
        "emit-command-wrapper",
        "emit-command-workflow",
    ]
    outer_call = "expanded from macro `emit-command-wrapper` call at"
    inner_call = "expanded from macro `emit-command-workflow` call at"
    definition_note = "macro definition at"
    assert rendered.count(outer_call) == 1
    assert rendered.count(inner_call) == 1
    assert rendered.count(definition_note) == 2
    outer_call_index = rendered.index(outer_call)
    outer_def_index = rendered.index(definition_note, outer_call_index)
    inner_call_index = rendered.index(inner_call, outer_def_index)
    inner_def_index = rendered.index(definition_note, inner_call_index)
    assert outer_call_index < outer_def_index < inner_call_index < inner_def_index


def test_compile_stage3_renders_nested_macro_notes_for_downstream_name_unknown(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            FIXTURES / "invalid" / "macro_nested_name_unknown.orc",
            validate_shared=False,
            workspace_root=tmp_path,
        )

    rendered = render_diagnostic(excinfo.value.diagnostics[0])
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "name_unknown"
    assert [frame.macro_name for frame in diagnostic.expansion_stack] == [
        "emit-record-wrapper",
        "emit-record-workflow",
    ]
    outer_call = "expanded from macro `emit-record-wrapper` call at"
    inner_call = "expanded from macro `emit-record-workflow` call at"
    definition_note = "macro definition at"
    assert rendered.count(outer_call) == 1
    assert rendered.count(inner_call) == 1
    assert rendered.count(definition_note) == 2
    outer_call_index = rendered.index(outer_call)
    outer_def_index = rendered.index(definition_note, outer_call_index)
    inner_call_index = rendered.index(inner_call, outer_def_index)
    inner_def_index = rendered.index(definition_note, inner_call_index)
    assert outer_call_index < outer_def_index < inner_call_index < inner_def_index


def test_compile_stage3_renders_procedure_provenance_notes_for_shared_validation_errors(tmp_path: Path) -> None:
    path = tmp_path / "procedure_validation_notes.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath EscapedReport",
                "    :kind relpath",
                '    :under "../escape"',
                "    :must-exist true)",
                "  (defrecord EscapedSummary",
                "    (report EscapedReport))",
                "  (defproc escaped-summary",
                "    ((report_path EscapedReport))",
                "    -> EscapedSummary",
                "    :effects ()",
                "    :lowering inline",
                "    (record EscapedSummary",
                "      :report report_path))",
                "  (defworkflow orchestrate",
                "    ((report_path EscapedReport))",
                "    -> EscapedSummary",
                "    (escaped-summary report_path)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=True, workspace_root=tmp_path)

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "procedure call site at" in rendered
    assert "procedure definition at" in rendered


def test_compile_stage3_renders_macro_expansion_notes_for_downstream_provider_parse_errors(tmp_path: Path) -> None:
    path = tmp_path / "macro_provider_result_invalid_inputs.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ImplementationState",
                "    (status String)",
                "    (report WorkReport))",
                "  (emit-provider-workflow provider_attempt)",
                "  (defmacro emit-provider-workflow (name)",
                "    (defworkflow name",
                "      ((input WorkReport)",
                "       (report_path WorkReport))",
                "      -> ImplementationState",
                "      (provider-result providers.execute",
                "        :prompt prompts.implementation.execute",
                "        :inputs report_path",
                "        :returns ImplementationState))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False)

    diagnostic = excinfo.value.diagnostics[0]
    rendered = render_diagnostic(diagnostic)

    assert diagnostic.code == "frontend_parse_error"
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-provider-workflow"
    assert "expanded from macro `emit-provider-workflow` call at" in rendered
    assert "macro definition at" in rendered


@pytest.mark.parametrize(
    ("provider_externs", "prompt_externs", "expected_code", "expected_message"),
    [
        (
            {},
            {"prompts.implementation.execute": "prompts/implementation/execute.md"},
            "provider_result_provider_invalid",
            "provider `providers.execute` is not a declared provider extern",
        ),
        (
            {"providers.execute": "test-provider"},
            {},
            "provider_result_prompt_invalid",
            "prompt `prompts.implementation.execute` is not a declared prompt extern",
        ),
    ],
)
def test_compile_stage3_renders_macro_expansion_notes_for_provider_extern_validation_errors(
    tmp_path: Path,
    provider_externs: dict[str, str],
    prompt_externs: dict[str, str],
    expected_code: str,
    expected_message: str,
) -> None:
    path = tmp_path / "macro_provider_result_missing_extern.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ImplementationState",
                "    (status String)",
                "    (report WorkReport))",
                "  (emit-provider-workflow provider_attempt)",
                "  (defmacro emit-provider-workflow (name)",
                "    (defworkflow name",
                "      ((input WorkReport)",
                "       (report_path WorkReport))",
                "      -> ImplementationState",
                "      (provider-result providers.execute",
                "        :prompt prompts.implementation.execute",
                "        :inputs (input report_path)",
                "        :returns ImplementationState))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            provider_externs=provider_externs,
            prompt_externs=prompt_externs,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    rendered = render_diagnostic(diagnostic)

    assert diagnostic.code == "macro_hidden_effect"
    assert "hidden provider effect" in diagnostic.message
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-provider-workflow"
    assert "expanded from macro `emit-provider-workflow` call at" in rendered
    assert "macro definition at" in rendered


def test_compile_stage1_entrypoint_renders_module_path_mismatch_diagnostic() -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage1_entrypoint", None)
    assert callable(compile_fn), "compile_stage1_entrypoint is missing"

    source_root = MODULE_FIXTURES / "invalid" / "path_mismatch"
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_fn(
            source_root / "neurips" / "bad.orc",
            source_roots=(source_root,),
        )

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "[module_path_mismatch]" in rendered
    assert "other/place" in rendered


def test_serialize_diagnostic_classifies_source_map_validation_errors() -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")

    diagnostic = LispFrontendDiagnostic(
        code="source_map_validation_ref_missing",
        message="validation subject `generated_input:missing_input` does not resolve to a declared origin",
        span=SourceSpan(
            start=SourcePosition(path="tests/fixtures/workflow_lisp/valid/example.orc", line=10, column=3, offset=0),
            end=SourcePosition(path="tests/fixtures/workflow_lisp/valid/example.orc", line=10, column=12, offset=0),
        ),
        form_path=("workflow-lisp", "defworkflow", "command_checks"),
    )

    payload = serialize_diagnostic(diagnostic)

    assert payload["code"] == "source_map_validation_ref_missing"
    assert payload["phase"] == "source_map"
    assert payload["validation_pass"] == "source_map"
    assert payload["authority_layer"] == "frontend"


def test_serialize_diagnostic_infers_semantic_ir_metadata_from_code() -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")

    diagnostic = LispFrontendDiagnostic(
        code="semantic_ir_invalid",
        message="semantic_ir_invalid: executable bridge references unknown node",
        span=SourceSpan(
            start=SourcePosition(path="tests/fixtures/workflow_lisp/valid/example.orc", line=12, column=3, offset=0),
            end=SourcePosition(path="tests/fixtures/workflow_lisp/valid/example.orc", line=12, column=18, offset=0),
        ),
        form_path=("workflow-lisp", "defworkflow", "command_checks"),
    )

    payload = serialize_diagnostic(diagnostic)

    assert payload["code"] == "semantic_ir_invalid"
    assert payload["phase"] == "semantic_ir"
    assert payload["validation_pass"] == "semantic_ir"
    assert payload["authority_layer"] == "shared"


def test_serialize_diagnostic_infers_executable_ir_metadata_from_code() -> None:
    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    serialize_diagnostic = getattr(diagnostics_module, "serialize_diagnostic")

    diagnostic = LispFrontendDiagnostic(
        code="executable_ir_invalid",
        message="executable_ir_invalid: executable node references unknown target",
        span=SourceSpan(
            start=SourcePosition(path="tests/fixtures/workflow_lisp/valid/example.orc", line=14, column=3, offset=0),
            end=SourcePosition(path="tests/fixtures/workflow_lisp/valid/example.orc", line=14, column=18, offset=0),
        ),
        form_path=("workflow-lisp", "defworkflow", "command_checks"),
    )

    payload = serialize_diagnostic(diagnostic)

    assert payload["code"] == "executable_ir_invalid"
    assert payload["phase"] == "executable"
    assert payload["validation_pass"] == "executable"
    assert payload["authority_layer"] == "frontend"


def test_semantic_ir_invalid_preserves_structured_subject_ref_bridge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")

    def fail_semantic_ir_validation(*args, **kwargs):
        del args, kwargs
        raise WorkflowValidationError(
            [
                ValidationError(
                    message="semantic_ir_invalid: executable bridge references unknown node `root.command_checks__run_checks`",
                    subject_refs=(
                        ValidationSubjectRef(
                            subject_kind="step_id",
                            subject_name="command_checks__run_checks",
                            workflow_name="command_checks",
                        ),
                    ),
                )
            ]
        )

    monkeypatch.setattr(
        semantic_ir_module,
        "validate_workflow_semantic_ir",
        fail_semantic_ir_validation,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            FIXTURES / "valid" / "structured_results.orc",
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                )
            },
            validate_shared=True,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "semantic_ir_invalid"
    assert diagnostic.validation_pass == "semantic_ir"
    assert diagnostic.authority_layer == "shared"
    assert diagnostic.span.start.path.endswith("structured_results.orc")
    assert diagnostic.form_path[-1] == "command_checks"


def test_semantic_ir_invalid_from_promoted_effect_validation_preserves_subject_bridge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")

    def fail_semantic_ir_validation(*args, **kwargs):
        del args, kwargs
        raise WorkflowValidationError(
            [
                ValidationError(
                    message="semantic_ir_invalid: promoted effect references unknown statement `orchestrate__attempt__prompt_inputs`",
                    subject_refs=(
                        ValidationSubjectRef(
                            subject_kind="step_id",
                            subject_name="orchestrate__attempt__prompt_inputs",
                            workflow_name="orchestrate",
                        ),
                    ),
                )
            ]
        )

    monkeypatch.setattr(
        semantic_ir_module,
        "validate_workflow_semantic_ir",
        fail_semantic_ir_validation,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            FIXTURES / "valid" / "phase_snapshot_effects.orc",
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=True,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "semantic_ir_invalid"
    assert diagnostic.validation_pass == "semantic_ir"
    assert diagnostic.authority_layer == "shared"
    assert diagnostic.span.start.path.endswith("phase_snapshot_effects.orc")
    assert diagnostic.form_path[-1] == "orchestrate"


@pytest.mark.parametrize(
    ("fixture_path", "expected_code"),
    [
        (INVALID_IF_NOT_BOOL_FIXTURE, "if_condition_not_bool"),
        (INVALID_IF_EFFECTFUL_FIXTURE, "if_condition_has_effect"),
        (INVALID_IF_NOT_PROJECTABLE_FIXTURE, "if_condition_not_projectable"),
        (INVALID_PURE_EXPR_OPERATOR_UNSUPPORTED_FIXTURE, "pure_expr_operator_unsupported"),
        (INVALID_PURE_EXPR_UNION_EQUALITY_FIXTURE, "pure_expr_union_equality_forbidden"),
        (INVALID_PURE_EXPR_FLOAT_EQUALITY_FIXTURE, "pure_expr_float_equality_forbidden"),
        (INVALID_PURE_EXPR_PATH_STRING_CONCAT_FIXTURE, "pure_expr_path_string_concat_forbidden"),
        (INVALID_PURE_EXPR_OPTIONAL_ACCESS_FIXTURE, "pure_expr_optional_access_unproved"),
        (INVALID_PURE_EXPR_COMPUTED_IF_VARIANT_REF_FIXTURE, "variant_ref_unproved"),
    ],
)
def test_rendered_diagnostic_reports_if_condition_not_bool(
    tmp_path: Path,
    fixture_path: Path,
    expected_code: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            fixture_path,
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                )
            },
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    rendered = render_diagnostic(diagnostic)

    assert diagnostic.code == expected_code
    assert f"[{expected_code}]" in rendered
    assert fixture_path.name in rendered
    if fixture_path in PURE_EXPR_HELPER_DIAGNOSTIC_FIXTURES:
        assert "workflow-lisp > defun" in rendered
    else:
        assert "workflow-lisp > defworkflow" in rendered
