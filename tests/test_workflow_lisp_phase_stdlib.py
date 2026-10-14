from __future__ import annotations

import ast
import hashlib
import importlib
import json
import re
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from orchestrator._common.io_atomic import (
    atomic_write_text as common_atomic_write_text,
)
import orchestrator.workflow_lisp.compiler as workflow_lisp_compiler
from orchestrator.workflow_lisp.adapters import (
    load_canonical_phase_result,
    reusable_phase_state_common,
    validate_reusable_phase_state,
    write_reusable_phase_state_v1,
)
from orchestrator.workflow_lisp.compiler import _definition_only_syntax_module, _imported_type_refs, _validate_definition_module, compile_stage1_entrypoint, compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.contracts import (
    derive_reusable_state_contract_metadata,
    is_review_findings_type,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import (
    GeneratedRelpathSeedExpr,
    LoopRecurExpr,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.modules import build_import_scope
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, UnionTypeRef
from orchestrator.workflow_lisp.workflows import CertifiedAdapterBinding, CommandBoundaryEnvironment, ExternalToolBinding, build_workflow_catalog, elaborate_workflow_definitions, typecheck_workflow_definitions


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_LIBRARY_ROOT = REPO_ROOT / "workflows" / "library"
STDLIB_MODULE_ROOT = REPO_ROOT / "orchestrator" / "workflow_lisp" / "stdlib_modules"


def test_reusable_result_bundle_delegates_exact_unframed_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "ORCHESTRATOR_OUTPUT_BUNDLE_PATH",
        "state/results/reusable.json",
    )
    writes: list[tuple[Path, str, dict[str, object]]] = []

    def tracking_write(path: Path, text: str, **kwargs) -> None:
        assert path.parent.is_dir()
        writes.append((path, text, kwargs))
        common_atomic_write_text(path, text, **kwargs)

    monkeypatch.setattr(
        reusable_phase_state_common,
        "atomic_write_text",
        tracking_write,
    )
    payload = {"status": "RÉSUMÉ", "count": 2}

    assert reusable_phase_state_common.emit_structured_result(payload) == 0

    assert writes == [
        (
            Path("state/results/reusable.json"),
            json.dumps(payload, sort_keys=True),
            {},
        )
    ]
    assert json.loads(capsys.readouterr().out) == payload


def _design_delta_provider_externs() -> dict[str, str]:
    return {
        "providers.implementation.execute": "fake-execute",
        "providers.implementation.review": "fake-review",
        "providers.implementation.fix": "fake-fix",
    }


def _design_delta_prompt_externs() -> dict[str, str]:
    return {
        "prompts.implementation.execute": "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/implement_plan.md",
        "prompts.implementation.review": "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/review_implementation.md",
        "prompts.implementation.fix": "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/fix_implementation.md",
    }


def _g0_retirement_metadata(
    *,
    name: str,
    retirement_class: str,
    retirement_label: str,
    replacement_surface: str,
) -> dict[str, object]:
    return {
        "retirement_class": retirement_class,
        "retirement_label": retirement_label,
        "replacement_surface": replacement_surface,
        "bridge_owner": "workflow-lisp",
        "expiry_condition": f"test-{name}-metadata",
        "evidence_refs": (f"{name}_evidence",),
    }


def _design_delta_command_boundaries() -> dict[str, ExternalToolBinding]:
    return {
        "run_neurips_backlog_checks": ExternalToolBinding(
            name="run_neurips_backlog_checks",
            stable_command=(
                "python",
                "workflows/library/scripts/run_neurips_backlog_checks.py",
            ),
            **_g0_retirement_metadata(
                name="run_neurips_backlog_checks",
                retirement_class="genuine_system",
                retirement_label="keep_certified_system",
                replacement_surface="bounded repo-local checks",
            ),
        ),
        "validate_review_findings_v1": ExternalToolBinding(
            name="validate_review_findings_v1",
            stable_command=(
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
            ),
            **_g0_retirement_metadata(
                name="validate_review_findings_v1",
                retirement_class="validation",
                retirement_label="keep_certified_system",
                replacement_surface="typed review findings validation",
            ),
        ),
    }
VALID_RUN_PROVIDER_FIXTURE = FIXTURES / "valid" / "phase_stdlib_run_provider_phase.orc"
VALID_PHASE_SNAPSHOT_EFFECTS_FIXTURE = FIXTURES / "valid" / "phase_snapshot_effects.orc"
VALID_POINTER_MATERIALIZATION_EFFECTS_FIXTURE = FIXTURES / "valid" / "pointer_materialization_effects.orc"
VALID_REVIEW_LOOP_FIXTURE = FIXTURES / "valid" / "phase_stdlib_review_loop.orc"
VALID_PHASE_SCOPE_STDLIB_FIXTURE = FIXTURES / "valid" / "phase_scope_stdlib_targets.orc"
VALID_RESUME_FIXTURE = FIXTURES / "valid" / "phase_stdlib_resume_or_start.orc"
VALID_RESUME_WRAPPER_FIXTURE = FIXTURES / "valid" / "phase_stdlib_resume_or_start_reusable_wrapper.orc"
VALID_NESTED_IMPLEMENTATION_PHASE_FIXTURE = FIXTURES / "valid" / "design_delta_nested_implementation_phase.orc"
VALID_NESTED_SAME_FILE_CALL_FIXTURE = (
    FIXTURES / "valid" / "design_delta_nested_same_file_call_local_record.orc"
)
VALID_NESTED_IMPORTED_BRANCH_EFFECTS_FIXTURE = (
    FIXTURES / "valid" / "design_delta_nested_imported_branch_effects.orc"
)
VALID_NESTED_BRANCH_SCOPE_COLLISION_FIXTURE = (
    FIXTURES / "valid" / "design_delta_nested_branch_scope_collision.orc"
)
INVALID_PHASE_CTX_FIXTURE = FIXTURES / "invalid" / "phase_ctx_contract_invalid.orc"
INVALID_LEGACY_BRIDGE_FIXTURE = FIXTURES / "invalid" / "phase_ctx_legacy_bridge_misuse.orc"
INVALID_PHASE_TARGET_FIXTURE = FIXTURES / "invalid" / "phase_target_unknown_generic.orc"
INVALID_REVIEW_LOOP_FIXTURE = FIXTURES / "invalid" / "review_loop_findings_contract_invalid.orc"
INVALID_REVIEW_LOOP_LEGACY_OPERANDS_FIXTURE = (
    FIXTURES / "invalid" / "review_loop_legacy_bridge_operands_invalid.orc"
)
INVALID_NESTED_INVALID_PROOF_USE_FIXTURE = (
    FIXTURES / "invalid" / "design_delta_nested_invalid_proof_use.orc"
)
INVALID_NESTED_BRANCH_REF_LEAK_FIXTURE = (
    FIXTURES / "invalid" / "design_delta_nested_branch_ref_leak.orc"
)
INVALID_NESTED_MISSING_PROJECTION_FIXTURE = (
    FIXTURES / "invalid" / "design_delta_nested_missing_projection.orc"
)
INVALID_NESTED_UNSUPPORTED_SHAPE_FIXTURE = (
    FIXTURES / "invalid" / "design_delta_nested_unsupported_shape.orc"
)
INVALID_RESUME_FIXTURE = FIXTURES / "invalid" / "resume_or_start_contract_invalid.orc"
INVALID_RESUME_POINTER_FIXTURE = FIXTURES / "invalid" / "resume_or_start_pointer_authority_invalid.orc"
INVALID_RESUME_RECORD_VALID_WHEN_FIXTURE = FIXTURES / "invalid" / "resume_or_start_record_valid_when_invalid.orc"
INVALID_UNCERTIFIED_RESUME_FIXTURE = FIXTURES / "invalid" / "resume_or_start_uncertified_adapter.orc"
DESIGN_DELTA_IMPLEMENTATION_PHASE_LIBRARY_MODULE = (
    WORKFLOW_LIBRARY_ROOT / "lisp_frontend_design_delta" / "implementation_phase.orc"
)
DESIGN_DELTA_TYPES_LIBRARY_MODULE = WORKFLOW_LIBRARY_ROOT / "lisp_frontend_design_delta" / "types.orc"


def _build_syntax_module(path: Path):
    return build_syntax_module(read_sexpr_file(path))






def _compile_definition_module(path: Path):
    syntax_module = _build_syntax_module(path)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _linked_module_type_environment_or_fail(linked, module_name: str):
    helper = getattr(importlib.import_module("orchestrator.workflow_lisp.compiler"), "_linked_module_type_environment", None)
    assert callable(helper), "_linked_module_type_environment is missing"
    return helper(linked, module_name)


def _write_module(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _rewrite_fixture(path: Path, *, replacements: tuple[tuple[str, str], ...], tmp_path: Path, filename: str) -> Path:
    source = path.read_text(encoding="utf-8")
    for old, new in replacements:
        assert old in source, f"fixture text not found: {old}"
        source = source.replace(old, new, 1)
    return _write_module(tmp_path / filename, source)


def _copy_design_delta_implementation_phase_graph(
    tmp_path: Path,
    *,
    std_phase_source: str | None = None,
) -> Path:
    _write_module(
        tmp_path / "lisp_frontend_design_delta" / "implementation_phase.orc",
        DESIGN_DELTA_IMPLEMENTATION_PHASE_LIBRARY_MODULE.read_text(encoding="utf-8"),
    )
    _write_module(
        tmp_path / "lisp_frontend_design_delta" / "types.orc",
        DESIGN_DELTA_TYPES_LIBRARY_MODULE.read_text(encoding="utf-8"),
    )
    _write_module(
        tmp_path / "std" / "context.orc",
        (STDLIB_MODULE_ROOT / "std" / "context.orc").read_text(encoding="utf-8"),
    )
    _write_module(
        tmp_path / "std" / "resource.orc",
        (STDLIB_MODULE_ROOT / "std" / "resource.orc").read_text(encoding="utf-8"),
    )
    _write_module(
        tmp_path / "std" / "phase.orc",
        std_phase_source
        if std_phase_source is not None
        else (STDLIB_MODULE_ROOT / "std" / "phase.orc").read_text(encoding="utf-8"),
    )
    return tmp_path / "lisp_frontend_design_delta" / "implementation_phase.orc"


def _write_payload_file(tmp_path: Path, filename: str, payload: dict[str, object]) -> str:
    path = tmp_path / filename
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path.as_posix()


def _structured_contract_fingerprint(
    *,
    structured_contract_kind: str,
    structured_contract: dict[str, object],
    return_type_name: str,
) -> str:
    digest = hashlib.sha256(
        json.dumps(structured_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"2.14:{return_type_name}:{structured_contract_kind}:{digest}"


def test_reusable_state_fingerprint_excludes_runtime_provenance(tmp_path: Path) -> None:
    types_path = _write_module(
        tmp_path / "reusable_state_provenance.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defunion Decision",
                "    (ACCEPTED",
                "      (report String))",
                "    (REJECTED",
                "      (report String))))",
            ]
        ),
    )
    syntax_module = _build_syntax_module(types_path)
    type_env = FrontendTypeEnvironment.from_module(_compile_definition_module(types_path))
    decision = type_env.resolve_type(
        "Decision",
        span=syntax_module.span,
        form_path=("workflow-lisp", "defunion", "Decision"),
    )

    assert isinstance(decision, UnionTypeRef)
    contract_kind, fingerprint, _, structured_contract = (
        derive_reusable_state_contract_metadata(
            decision,
            target_dsl_version="2.14",
            workflow_name="demo/module::entry",
            step_id="execute",
            span=syntax_module.span,
            form_path=("workflow-lisp", "defworkflow", "entry"),
        )
    )

    def strip_runtime_provenance(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: strip_runtime_provenance(item)
                for key, item in value.items()
                if key not in {
                    "source_map_subject",
                    "source_map_subjects_by_variant",
                }
            }
        if isinstance(value, list):
            return [strip_runtime_provenance(item) for item in value]
        return value

    [shared] = structured_contract["shared_fields"]
    assert set(shared["source_map_subjects_by_variant"]) == {
        "ACCEPTED",
        "REJECTED",
    }
    semantic_contract = strip_runtime_provenance(structured_contract)
    expected_digest = hashlib.sha256(
        json.dumps(semantic_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert contract_kind == "union"
    assert fingerprint == f"2.14:Decision:union:{expected_digest}"

    common_error: ValueError | None = None
    try:
        reusable_phase_state_common.validate_contract_fingerprint(
            target_dsl_version="2.14",
            return_type_name="Decision",
            structured_contract_kind=contract_kind,
            structured_contract=dict(structured_contract),
            expected_contract_fingerprint=fingerprint,
        )
    except ValueError as error:
        common_error = error
    loader_accepts = load_canonical_phase_result._validate_contract_fingerprint(
        target_dsl_version="2.14",
        return_type_name="Decision",
        structured_contract_kind=contract_kind,
        structured_contract=dict(structured_contract),
        expected_contract_fingerprint=fingerprint,
    )
    assert (common_error, loader_accepts) == (None, True)


def _checks_structured_contract() -> dict[str, object]:
    return {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }






def _resume_state_payload(
    *,
    bundle_relpath: str,
    return_type_name: str,
    structured_contract_kind: str,
    structured_contract: dict[str, object],
    artifact_requirements: dict[str, list[dict[str, object]]],
    reusable_variants: list[str],
    current_public_inputs: dict[str, object],
    producer_fingerprint_basis: dict[str, object] | None = None,
    summary_schema: str = "ReusablePhaseState.v1",
    summary_version: str = "v1",
) -> dict[str, object]:
    fingerprint = _structured_contract_fingerprint(
        structured_contract_kind=structured_contract_kind,
        structured_contract=structured_contract,
        return_type_name=return_type_name,
    )
    public_input_hash_basis = list(current_public_inputs)
    return {
        "bundle_path": bundle_relpath,
        "resume_from": bundle_relpath,
        "target_dsl_version": "2.14",
        "return_type_name": return_type_name,
        "structured_contract_kind": structured_contract_kind,
        "expected_contract_fingerprint": fingerprint,
        "structured_contract": structured_contract,
        "summary_schema": summary_schema,
        "summary_version": summary_version,
        "sidecar_suffix": ".reusable_state.json",
        "canonical_bundle_digest_field": "canonical_bundle_sha256",
        "reusable_variants": reusable_variants,
        "artifact_requirements": artifact_requirements,
        "public_input_hash_basis": public_input_hash_basis,
        "current_public_inputs": current_public_inputs,
        "producer_fingerprint_basis": producer_fingerprint_basis
        or {
            "workflow_name": "resume-test",
            "return_type_name": return_type_name,
            "structured_contract_kind": structured_contract_kind,
            "expected_contract_fingerprint": fingerprint,
            "target_dsl_version": "2.14",
            "compiler_version": "0.1.0",
            "reusable_variants": reusable_variants,
            "public_input_hash_basis": public_input_hash_basis,
            "source_file_digests": {"resume-test.orc": "abc123"},
            "provider_extern_bindings": {"providers.execute": "fake-execute"},
            "prompt_extern_bindings": {"prompts.implementation.execute": "prompts/implementation/execute.md"},
            "command_boundary_bindings": {"run_checks": {"kind": "external_tool", "stable_command": ["python", "scripts/run_checks.py"]}},
            "imported_workflow_fingerprints": {},
            "lowering_options": {"language_version": "0.1", "target_dsl_version": "2.14"},
            "compile_inputs_fingerprint": "compile-inputs-fingerprint",
        },
        "source_run_id": "test-run",
        "source_step_id": "resume-step",
        "source_call_frame_id": "root",
        "phase_id": "checks" if return_type_name == "ChecksResult" else "plan-gate",
        "created_at": "2026-06-02T00:00:00Z",
    }










def _typecheck_fixture(path: Path):
    return _compile(
        path,
        tmp_path=path.parent,
        validate_shared=False,
    ).typed_workflows


def _compile(
    path: Path,
    *,
    tmp_path: Path,
    validate_shared: bool = False,
    imported_workflow_bundles=None,
):
    return compile_stage3_module(
        path,
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
            "load_canonical_phase_result__ChecksResult": ExternalToolBinding(
                name="load_canonical_phase_result__ChecksResult",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
                ),
            ),
        },
        imported_workflow_bundles=imported_workflow_bundles,
        validate_shared=validate_shared,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )


def _compile_entrypoint(
    path: Path,
    *,
    tmp_path: Path,
    validate_shared: bool = False,
):
    return compile_stage3_entrypoint(
        path,
        source_roots=(path.parent,),
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
            "load_canonical_phase_result__ChecksResult": ExternalToolBinding(
                name="load_canonical_phase_result__ChecksResult",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
                ),
            ),
        },
        validate_shared=validate_shared,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )




def _walk_nodes(node):
    if is_dataclass(node):
        yield node
        for field in fields(node):
            yield from _walk_nodes(getattr(node, field.name))
        return
    if isinstance(node, tuple):
        for item in node:
            yield from _walk_nodes(item)
        return
    if isinstance(node, list):
        for item in node:
            yield from _walk_nodes(item)
        return
    if isinstance(node, dict):
        for item in node.values():
            yield from _walk_nodes(item)




def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code












def test_typecheck_accepts_generic_phase_ctx_for_phase_target(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_phase_target_ok.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReportTarget",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord ReportTargetOnly",
                "    (report_path WorkReportTarget))",
                "  (defworkflow generic-phase-target",
                "    ((phase-ctx PhaseCtx))",
                "    -> ReportTargetOnly",
                "    (with-phase phase-ctx implementation",
                "      (record ReportTargetOnly",
                "        :report_path (phase-target execution-report)))))",
            ]
        ),
    )

    typed = _typecheck_fixture(path)

    assert [workflow.definition.name for workflow in typed] == ["generic-phase-target"]


def test_typecheck_rejects_resume_state_adapter_authored_outside_resume_or_start(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "resume_state_adapter_outside_resume_or_start.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath StateFile",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist false)",
                "  (defrecord ChecksResult",
                "    (status String))",
                "  (defworkflow orchestrate",
                "    ((resume_state StateFile))",
                "    -> ChecksResult",
                "    (command-result load_resume_state",
                '      :argv ("python" "scripts/load_resume_state.py" resume_state)',
                "      :returns ChecksResult)))",
            ]
        ),
    )
    module = _compile_definition_module(path)
    type_env = FrontendTypeEnvironment.from_module(module)
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    command_boundary_environment = CommandBoundaryEnvironment(
        bindings_by_name={
            "load_resume_state": CertifiedAdapterBinding(
                name="load_resume_state",
                stable_command=("python", "scripts/load_resume_state.py"),
                input_contract={"type": "object"},
                output_type_name="ChecksResult",
                effects=("resume_state_reuse", "structured_result"),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("resume_state_reuse_ok",),
                negative_fixture_ids=("resume_state_reuse_bad",),
            ),
        }
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_workflow_definitions(
            workflow_defs,
            type_env=type_env,
            workflow_catalog=workflow_catalog,
            command_boundary_environment=command_boundary_environment,
        )

    _assert_diagnostic_code(excinfo, "recovery_gate_without_resume_or_start")


def test_run_provider_phase_accepts_generic_ctx_after_typechecking() -> None:
    typed = _typecheck_fixture(VALID_RUN_PROVIDER_FIXTURE)

    assert [workflow.definition.name.rsplit("::", 1)[-1] for workflow in typed] == [
        "run-provider-phase-demo",
        "produce-one-of-demo",
    ]


def test_typecheck_rejects_run_provider_phase_name_mismatch_with_active_phase(tmp_path: Path) -> None:
    path = _rewrite_fixture(
        VALID_RUN_PROVIDER_FIXTURE,
        replacements=(("run-provider-phase implementation", "run-provider-phase wrong-phase"),),
        tmp_path=tmp_path,
        filename=VALID_RUN_PROVIDER_FIXTURE.name,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    _assert_diagnostic_code(excinfo, "phase_scope_name_mismatch")


def test_typecheck_rejects_invalid_generic_phase_ctx_contract() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_PHASE_CTX_FIXTURE)

    _assert_diagnostic_code(excinfo, "phase_context_invalid")


def test_generic_stdlib_rejects_legacy_bridge() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_LEGACY_BRIDGE_FIXTURE)

    _assert_diagnostic_code(excinfo, "phase_ctx_legacy_bridge_invalid")


def test_typecheck_rejects_unknown_generic_phase_target() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_PHASE_TARGET_FIXTURE)

    _assert_diagnostic_code(excinfo, "phase_target_contract_unresolved")


















def test_reusable_phase_state_with_composed_with_phase_private_workflow_rejects_review_loop_boundary(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "reusable_composed_with_phase_review_loop.orc",
        "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.14")',
                    "  (defmodule reusable_composed_with_phase_review_loop)",
                    "  (import std/phase :only (ReviewDecision ReviewFindings ReviewLoopResult ReviewReportPath review-revise-loop with-phase))",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord CompletedSurface",
                "    (plan_path WorkReport))",
                "  (defrecord ReviewInputs",
                "    (report_path WorkReport)",
                "    (fix_prompt WorkReport))",
                "  (defrecord ReviewSurfaceResult",
                "    (report_path ReviewReportPath))",
                "  (defproc review-once",
                "    ((completed CompletedSurface)",
                "     (inputs ReviewInputs))",
                "    -> ReviewDecision",
                "    :effects ((uses-provider providers.review))",
                "    :lowering inline",
                "    (provider-result providers.review",
                "      :prompt prompts.implementation.review",
                "      :inputs (completed.plan_path inputs.report_path)",
                "      :returns ReviewDecision))",
                "  (defproc apply-fix",
                "    ((completed CompletedSurface)",
                "     (inputs ReviewInputs)",
                "     (findings ReviewFindings))",
                "    -> CompletedSurface",
                "    :effects ((uses-provider providers.fix))",
                "    :lowering inline",
                "    (provider-result providers.fix",
                "      :prompt prompts.implementation.fix",
                "      :inputs (completed.plan_path inputs.fix_prompt findings.items_path)",
                "      :returns CompletedSurface))",
                "  (defproc review-phase-helper",
                "    ((phase-ctx PhaseCtx)",
                "     (completed CompletedSurface)",
                "     (inputs ReviewInputs))",
                "    -> ReviewLoopResult",
                    "    :effects ((uses-provider providers.review) (uses-provider providers.fix) (uses-command validate_review_findings_v1))",
                "    :lowering private-workflow",
                "    (with-phase phase-ctx implementation-review",
                "      (review-revise-loop implementation-review",
                "        :ctx phase-ctx",
                "        :completed completed",
                "        :inputs inputs",
                "        :review (proc-ref review-once)",
                "        :fix (proc-ref apply-fix)",
                "        :max 3)))",
                "  (defworkflow run-review",
                "    ((phase-ctx PhaseCtx)",
                "     (completed CompletedSurface)",
                "     (inputs ReviewInputs))",
                "    -> ReviewSurfaceResult",
                "    (let* ((review (review-phase-helper phase-ctx completed inputs)))",
                "      (match review",
                "        ((APPROVED approved)",
                "         (record ReviewSurfaceResult",
                "           :report_path approved.review_report))",
                    "        ((BLOCKED blocked)",
                    "         (record ReviewSurfaceResult",
                    "           :report_path blocked.review_report))",
                "        ((EXHAUSTED exhausted)",
                "         (record ReviewSurfaceResult",
                "           :report_path exhausted.last_review_report))))))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            provider_externs={
                "providers.review": "fake-review",
                "providers.fix": "fake-fix",
            },
            prompt_externs={
                "prompts.implementation.review": "prompts/implementation/review.md",
                "prompts.implementation.fix": "prompts/implementation/fix.md",
            },
            validate_shared=True,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "proc_private_workflow_boundary_invalid")


def test_typecheck_rejects_invalid_review_loop_findings_contract() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_REVIEW_LOOP_FIXTURE)

    _assert_diagnostic_code(excinfo, "type_mismatch")


def test_typecheck_accepts_review_loop_result_contract_with_equivalent_findings_alias(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "phase_stdlib_review_loop_alias.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule phase_stdlib_review_loop_alias)",
                "  (import std/phase :as phase :only (ReviewFindings))",
                "  (defrecord WrappedFindings",
                "    (findings phase.ReviewFindings)))",
            ]
        ),
    )

    linked = compile_stage1_entrypoint(path, source_roots=(tmp_path,))
    entry_module = linked.compiled_modules_by_name["phase_stdlib_review_loop_alias"]
    phase_module, _, phase_env = _linked_module_type_environment_or_fail(linked, "std/phase")
    import_scope = build_import_scope(
        entry_module,
        export_surfaces_by_name=linked.graph.export_surfaces_by_name,
    )
    type_env = FrontendTypeEnvironment.from_module(
        entry_module,
        import_scope=import_scope,
        imported_type_refs=_imported_type_refs(
            import_scope,
            {
                "std/phase": {
                    "ReviewFindings": phase_env.resolve_type(
                        "ReviewFindings",
                        span=phase_module.span,
                        form_path=("workflow-lisp", "defrecord", "ReviewFindings"),
                    )
                }
            },
        ),
    )
    resolved = type_env.resolve_type(
        "phase.ReviewFindings",
        span=entry_module.span,
        form_path=("workflow-lisp", "defrecord", "WrappedFindings"),
    )

    assert is_review_findings_type(resolved)


def test_linked_builtin_std_phase_owner_lane_resolves_exported_review_loop_types(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "phase_stdlib_owner_lane.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule phase_stdlib_owner_lane)",
                "  (import std/phase :as phase :only (",
                "    ReviewDecision",
                "    ReviewFindings",
                "    ReviewFindingsJsonPath",
                "    ReviewLoopResult",
                "    PhaseScopeTargets",
                "  ))",
                "  (export LocalDecision LocalFindings LocalLoopResult LocalFindingsPath LocalTargets)",
                "  (defrecord LocalDecision",
                "    (decision phase.ReviewDecision))",
                "  (defrecord LocalFindings",
                "    (findings phase.ReviewFindings))",
                "  (defrecord LocalLoopResult",
                "    (result phase.ReviewLoopResult))",
                "  (defrecord LocalFindingsPath",
                "    (report phase.ReviewFindingsJsonPath))",
                "  (defrecord LocalTargets",
                "    (targets phase.PhaseScopeTargets)))",
            ]
        ),
    )

    linked = compile_stage1_entrypoint(path, source_roots=(tmp_path,))
    phase_module, phase_import_scope, phase_env = _linked_module_type_environment_or_fail(linked, "std/phase")

    assert "PhaseCtx" in phase_import_scope.unqualified_type_bindings
    for type_name in (
        "ReviewDecision",
        "ReviewFindings",
        "ReviewLoopResult",
        "ReviewFindingsJsonPath",
        "PhaseScopeTargets",
    ):
        resolved = phase_env.resolve_type(
            type_name,
            span=phase_module.span,
            form_path=("workflow-lisp", type_name),
        )
        assert resolved.name == type_name

    entry_module = linked.compiled_modules_by_name["phase_stdlib_owner_lane"]
    entry_import_scope = build_import_scope(
        entry_module,
        export_surfaces_by_name=linked.graph.export_surfaces_by_name,
    )
    entry_type_env = FrontendTypeEnvironment.from_module(
        entry_module,
        import_scope=entry_import_scope,
        imported_type_refs=_imported_type_refs(
            entry_import_scope,
            {
                "std/phase": {
                    type_name: phase_env.resolve_type(
                        type_name,
                        span=phase_module.span,
                        form_path=("workflow-lisp", type_name),
                    )
                    for type_name in (
                        "ReviewDecision",
                        "ReviewFindings",
                        "ReviewFindingsJsonPath",
                        "ReviewLoopResult",
                        "PhaseScopeTargets",
                    )
                }
            },
        ),
    )

    for qualified_name in (
        "phase.ReviewDecision",
        "phase.ReviewFindings",
        "phase.ReviewFindingsJsonPath",
        "phase.ReviewLoopResult",
        "phase.PhaseScopeTargets",
    ):
        resolved = entry_type_env.resolve_type(
            qualified_name,
            span=entry_module.span,
            form_path=("workflow-lisp", "defrecord"),
        )
        assert resolved.name == f"std/phase::{qualified_name.split('.', 1)[1]}"




def test_linked_builtin_std_phase_owner_lane_fails_closed_on_review_loop_result_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken_phase_source = (STDLIB_MODULE_ROOT / "std" / "phase.orc").read_text(encoding="utf-8").replace(
        "(defunion ReviewLoopResult",
        "(defunion BrokenReviewLoopResult",
        1,
    )
    entry_path = _copy_design_delta_implementation_phase_graph(
        tmp_path,
        std_phase_source=broken_phase_source,
    )
    monkeypatch.setattr(workflow_lisp_compiler, "_builtin_stdlib_source_root", lambda: tmp_path)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            entry_path,
            source_roots=(tmp_path,),
            provider_externs=_design_delta_provider_externs(),
            prompt_externs=_design_delta_prompt_externs(),
            command_boundaries=_design_delta_command_boundaries(),
            validate_shared=True,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code in {"type_unknown", "module_export_missing"}
    assert diagnostic.span.start.path.endswith("std/phase.orc")


def test_typecheck_rejects_non_alias_path_type_substitution(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "path_type_substitution_invalid.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule path_type_substitution_invalid)",
                "  (defpath ReportA",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defpath ReportB",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord Input",
                "    (report ReportA))",
                "  (defrecord Output",
                "    (report ReportB))",
                "  (defworkflow demo",
                "    ((input Input))",
                "    -> Output",
                "    (record Output",
                "      :report input.report)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    _assert_diagnostic_code(excinfo, "type_mismatch")


def test_typecheck_rejects_review_findings_json_path_substitution(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "review_findings_path_substitution_invalid.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule review_findings_path_substitution_invalid)",
                "  (import std/phase :as phase :only (ReviewFindingsJsonPath))",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord Input",
                "    (report WorkReport))",
                "  (defrecord Output",
                "    (report phase.ReviewFindingsJsonPath))",
                "  (defworkflow demo",
                "    ((input Input))",
                "    -> Output",
                "    (record Output",
                "      :report input.report)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    _assert_diagnostic_code(excinfo, "type_mismatch")


def test_typecheck_accepts_review_revise_loop_name_as_stdlib_macro_argument(tmp_path: Path) -> None:
    path = _rewrite_fixture(
        VALID_REVIEW_LOOP_FIXTURE,
        replacements=(("review-revise-loop implementation-review", "review-revise-loop wrong-loop"),),
        tmp_path=tmp_path,
        filename="phase_stdlib_review_loop.orc",
    )

    _typecheck_fixture(path)


def test_typecheck_rejects_review_revise_loop_without_imported_std_phase_surface(tmp_path: Path) -> None:
    path = _rewrite_fixture(
        VALID_REVIEW_LOOP_FIXTURE,
        replacements=(
            (
                "  (import std/phase :only (ReviewDecision ReviewFindings ReviewLoopResult review-revise-loop with-phase))\n",
                "  (import std/phase :only (ReviewDecision ReviewFindings ReviewLoopResult))\n",
            ),
        ),
        tmp_path=tmp_path,
        filename="phase_stdlib_review_loop.orc",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    _assert_diagnostic_code(excinfo, "stdlib_extension_missing_import_route")


def test_typecheck_rejects_review_revise_loop_legacy_bridge_operands(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            INVALID_REVIEW_LOOP_LEGACY_OPERANDS_FIXTURE,
            provider_externs={
                "providers.review": "fake-review",
                "providers.fix": "fake-fix",
            },
            prompt_externs={
                "prompts.implementation.review": "prompts/implementation/review.md",
                "prompts.implementation.fix": "prompts/implementation/fix.md",
            },
            validate_shared=False,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "type_mismatch")


def test_review_loop_specializes_to_ordinary_typed_forms(tmp_path: Path) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    surviving = [
        node
        for workflow in result.typed_workflows
        for node in _walk_nodes(workflow.typed_body.expr)
        if type(node).__name__ == "StdlibSpecializationExpr"
    ]
    surviving.extend(
        node
        for procedure in result.typed_procedures
        for node in _walk_nodes(procedure.typed_body.expr)
        if type(node).__name__ == "StdlibSpecializationExpr"
    )

    assert not surviving


def test_review_loop_entrypoint_smoke(tmp_path: Path) -> None:
    result = _compile_entrypoint(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    assert any(
        workflow.definition.name.endswith("::review-revise-loop-demo")
        for workflow in result.entry_result.typed_workflows
    )


def test_review_loop_compiles_without_bridge_controls(tmp_path: Path) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    assert any(
        workflow.definition.name.endswith("::review-revise-loop-demo")
        for workflow in result.typed_workflows
    )


def test_phase_stdlib_review_loop_is_owned_directly_in_std_phase_module(
    tmp_path: Path,
) -> None:
    stdlib_phase = (
        Path(importlib.import_module("orchestrator.workflow_lisp").__file__).resolve().parent
        / "stdlib_modules"
        / "std"
        / "phase.orc"
    )
    source = stdlib_phase.read_text(encoding="utf-8")
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    assert "(import std/phase_review_loop_support" not in source
    assert "std/phase_review_loop_support/run-review-revise-loop" not in source
    assert "(loop/recur" in source
    assert "validate_review_findings_v1" in source
    assert "Keep the helper proc exported until imported macro expansion can resolve" in source
    assert any(
        workflow.definition.name.endswith("::review-revise-loop-demo")
        for workflow in result.typed_workflows
    )
    assert not any(
        getattr(procedure.specialization, "base_name", "").endswith("review-revise-loop")
        for procedure in result.typed_procedures
        if procedure.specialization is not None
    )


def test_review_loop_bridge_support_module_is_retired() -> None:
    support_module = (
        Path(importlib.import_module("orchestrator.workflow_lisp").__file__).resolve().parent
        / "stdlib_modules"
        / "std"
        / "phase_review_loop_support.orc"
    )

    assert not support_module.exists()


def test_active_review_loop_owner_modules_do_not_reference_bridge_policy() -> None:
    package_dir = Path(importlib.import_module("orchestrator.workflow_lisp").__file__).resolve().parent
    owner_modules = (
        package_dir / "typecheck_dispatch.py",
        package_dir / "compiler.py",
        package_dir / "typecheck_context.py",
        package_dir / "procedure_typecheck.py",
        package_dir / "workflows.py",
    )

    for module_path in owner_modules:
        assert "review_loop_legacy_bridge_policy" not in module_path.read_text(encoding="utf-8")


def test_typecheck_accepts_generic_phase_scoped_provider_result_record(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_phase_provider_result.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule generic_phase_provider_result)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord ReviewSurfaceResult",
                "    (report_path WorkReport))",
                "  (defworkflow run-review",
                "    ((phase-ctx PhaseCtx))",
                "    -> ReviewSurfaceResult",
                "    (with-phase phase-ctx implementation-review",
                "      (provider-result providers.execute",
                "        :prompt prompts.implementation.execute",
                "        :inputs ()",
                "        :returns ReviewSurfaceResult))))",
            ]
        ),
    )

    result = _compile(path, tmp_path=tmp_path)

    assert any(workflow.definition.name.endswith("run-review") for workflow in result.typed_workflows)




def test_stdlib_form_phase_scope_fixture_compiles_through_builtin_stdlib_import(tmp_path: Path) -> None:
    source = VALID_PHASE_SCOPE_STDLIB_FIXTURE.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None
    module_path = (tmp_path / Path(*module_match.group(1).split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        command_boundaries={},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert "phase_scope_stdlib_targets::phase-scope-demo" in result.entry_result.workflow_catalog.signatures_by_name












def test_review_loop_seed_state_uses_distinct_generated_seed_roles(tmp_path: Path) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    roles = {
        node.seed_role
        for workflow in result.typed_workflows
        for node in _walk_nodes(workflow.typed_body.expr)
        if isinstance(node, GeneratedRelpathSeedExpr)
    }
    roles.update(
        node.seed_role
        for procedure in result.typed_procedures
        for node in _walk_nodes(procedure.typed_body.expr)
        if isinstance(node, GeneratedRelpathSeedExpr)
    )

    assert roles >= {
        "review_loop_last_review_report_seed",
        "review_loop_findings_items_path_seed",
    }




def test_review_loop_direct_route_populates_loop_recur_on_exhausted_result_expr(
    tmp_path: Path,
) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    loop_exprs = [
        node
        for owner in (*result.typed_workflows, *result.typed_procedures)
        for node in _walk_nodes(owner.typed_body.expr)
        if isinstance(node, LoopRecurExpr)
    ]

    assert loop_exprs
    assert loop_exprs[0].on_exhausted_result_expr is not None
    assert loop_exprs[0].on_exhausted_result_expr.span.start.path.endswith(
        "orchestrator/workflow_lisp/stdlib_modules/std/phase.orc"
    )






def test_review_loop_validator_binding_registers_only_when_review_loop_present(tmp_path: Path) -> None:
    review_loop_result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)
    resume_result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path)

    assert "validate_review_findings_v1" in review_loop_result.command_boundary_environment.bindings_by_name
    assert "validate_review_findings_v1" not in resume_result.command_boundary_environment.bindings_by_name


def test_review_loop_compiler_no_longer_uses_literal_review_loop_binding_scanner() -> None:
    compiler_path = Path(importlib.import_module("orchestrator.workflow_lisp.compiler").__file__)
    source = compiler_path.read_text(encoding="utf-8")

    assert "_workflow_contains_review_revise_loop" not in source
    assert "_augment_review_loop_command_boundaries" not in source
    assert "review_loop_public_surface" not in source
    assert "validate_review_findings_v1" not in source


def test_review_loop_typecheck_effects_avoids_review_loop_specific_validator_fallback() -> None:
    source = Path(importlib.import_module("orchestrator.workflow_lisp.typecheck_effects").__file__).read_text(
        encoding="utf-8"
    )

    assert 'expr.step_name == "validate_review_findings_v1"' not in source






















def test_nested_implementation_phase_rejects_branch_local_ref_leak(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(
            INVALID_NESTED_BRANCH_REF_LEAK_FIXTURE,
            tmp_path=tmp_path,
            validate_shared=True,
        )

    assert excinfo.value.diagnostics


def test_nested_implementation_phase_rejects_missing_projection(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(
            INVALID_NESTED_MISSING_PROJECTION_FIXTURE,
            tmp_path=tmp_path,
            validate_shared=True,
        )

    assert excinfo.value.diagnostics


def test_nested_control_rejects_unsupported_shape_before_invalid_lowering(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(
            INVALID_NESTED_UNSUPPORTED_SHAPE_FIXTURE,
            tmp_path=tmp_path,
            validate_shared=True,
        )

    assert excinfo.value.diagnostics


def test_nested_control_rejects_invalid_proof_use(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(
            INVALID_NESTED_INVALID_PROOF_USE_FIXTURE,
            tmp_path=tmp_path,
            validate_shared=True,
        )

    assert excinfo.value.diagnostics[0].code == "variant_ref_unproved"






def test_typecheck_resume_or_start_derives_summary_metadata_contract(tmp_path: Path) -> None:
    result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path)

    resume_exprs = [
        node
        for workflow in result.typed_workflows
        for node in _walk_nodes(workflow.typed_body)
        if type(node).__name__ == "ResumeOrStartExpr"
    ]

    assert {expr.resume_name for expr in resume_exprs} == {"checks", "plan-gate"}

    checks_spec = next(expr.validation_spec for expr in resume_exprs if expr.resume_name == "checks")
    assert checks_spec is not None
    assert checks_spec.summary_schema == "ReusablePhaseState.v1"
    assert checks_spec.summary_version == "v1"
    assert checks_spec.sidecar_suffix == ".reusable_state.json"
    assert checks_spec.canonical_bundle_digest_field == "canonical_bundle_sha256"
    assert checks_spec.writer_binding_name == "write_reusable_phase_state_v1"
    assert "phase-ctx__phase-name" in checks_spec.public_input_hash_basis
    assert "inputs__report_path" in checks_spec.public_input_hash_basis
    assert "phase-ctx__run__run-id" not in checks_spec.public_input_hash_basis
    assert "phase-ctx__run__state-root" not in checks_spec.public_input_hash_basis
    assert "phase-ctx__run__artifact-root" not in checks_spec.public_input_hash_basis
    assert "phase-ctx__state-root" not in checks_spec.public_input_hash_basis
    assert "phase-ctx__artifact-root" not in checks_spec.public_input_hash_basis
    assert not any(name.startswith("__write_root__") for name in checks_spec.public_input_hash_basis)
    assert checks_spec.producer_fingerprint_basis["target_dsl_version"] == "2.14"
    assert checks_spec.producer_fingerprint_basis["return_type_name"] == "ChecksResult"
    assert checks_spec.producer_fingerprint_basis["source_file_digests"]
    assert checks_spec.producer_fingerprint_basis["compile_inputs_fingerprint"]

    plan_gate_spec = next(expr.validation_spec for expr in resume_exprs if expr.resume_name == "plan-gate")
    assert plan_gate_spec is not None
    assert plan_gate_spec.summary_schema == "ReusablePhaseState.v1"
    assert plan_gate_spec.writer_binding_name == "write_reusable_phase_state_v1"
    assert plan_gate_spec.producer_fingerprint_basis["return_type_name"] == "PlanGateResult"
    assert plan_gate_spec.producer_fingerprint_basis["compile_inputs_fingerprint"]
    assert plan_gate_spec.artifact_requirements["APPROVED"][0].field_path == ("shared_report_path",)
    assert plan_gate_spec.artifact_requirements["APPROVED"][1].field_path == ("execution_report_path",)


def test_resume_or_start_hash_basis_uses_target_aware_nested_public_input_projection(
    tmp_path: Path,
) -> None:
    legacy_path = _rewrite_fixture(
        VALID_RESUME_FIXTURE,
        replacements=(('(:target-dsl "2.14")', '(:target-dsl "2.24")'),),
        tmp_path=tmp_path,
        filename="phase_stdlib_resume_or_start.orc",
    )
    legacy_result = _compile(legacy_path, tmp_path=tmp_path)
    legacy_spec = next(
        node.validation_spec
        for workflow in legacy_result.typed_workflows
        for node in _walk_nodes(workflow.typed_body)
        if type(node).__name__ == "ResumeOrStartExpr" and node.resume_name == "checks"
    )
    assert legacy_spec is not None
    assert "inputs__report_path" in legacy_spec.public_input_hash_basis
    assert legacy_spec.producer_fingerprint_basis["public_input_hash_basis"] == list(
        legacy_spec.public_input_hash_basis
    )

    nested_path = _rewrite_fixture(
        VALID_RESUME_FIXTURE,
        replacements=(
            ('(:target-dsl "2.14")', '(:target-dsl "2.25")'),
            (
                "  (defrecord ResumeInputs\n",
                "  (defrecord Measurement\n"
                "    (label String)\n"
                "    (count Int))\n"
                "  (defrecord ResumeInputs\n",
            ),
            (
                "    (report_path WorkReport))",
                "    (report_path WorkReport)\n"
                "    (measurements List[Measurement]))",
            ),
        ),
        tmp_path=tmp_path,
        filename="phase_stdlib_resume_or_start.orc",
    )
    nested_result = _compile(nested_path, tmp_path=tmp_path)
    nested_spec = next(
        node.validation_spec
        for workflow in nested_result.typed_workflows
        for node in _walk_nodes(workflow.typed_body)
        if type(node).__name__ == "ResumeOrStartExpr" and node.resume_name == "checks"
    )
    assert nested_spec is not None
    assert "inputs__measurements" in nested_spec.public_input_hash_basis
    assert nested_spec.producer_fingerprint_basis["public_input_hash_basis"] == list(
        nested_spec.public_input_hash_basis
    )


def test_resume_or_start_reserved_adapter_names_cannot_be_shadowed(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_RESUME_FIXTURE,
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
            "validate_reusable_phase_state": ExternalToolBinding(
                name="validate_reusable_phase_state",
                stable_command=("python", "scripts/not_certified_validator.py"),
            ),
            "write_reusable_phase_state_v1": ExternalToolBinding(
                name="write_reusable_phase_state_v1",
                stable_command=("python", "scripts/not_certified_writer.py"),
            ),
            "load_canonical_phase_result__ChecksResult": ExternalToolBinding(
                name="load_canonical_phase_result__ChecksResult",
                stable_command=("python", "scripts/not_certified_loader.py"),
            ),
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    bindings = result.command_boundary_environment.bindings_by_name

    assert isinstance(bindings["validate_reusable_phase_state"], CertifiedAdapterBinding)
    assert isinstance(bindings["write_reusable_phase_state_v1"], CertifiedAdapterBinding)
    assert isinstance(bindings["load_canonical_phase_result__ChecksResult"], CertifiedAdapterBinding)
    assert bindings["validate_reusable_phase_state"].stable_command == (
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state",
    )
    assert bindings["write_reusable_phase_state_v1"].stable_command == (
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.write_reusable_phase_state_v1",
    )
    assert bindings["load_canonical_phase_result__ChecksResult"].stable_command == (
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
    )


















def test_typecheck_rejects_resume_or_start_contract_invalid() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_RESUME_FIXTURE)

    assert excinfo.value.diagnostics[0].code in {
        "resume_or_start_contract_invalid",
        "recovery_gate_without_resume_or_start",
    }


def test_typecheck_rejects_resume_or_start_valid_when_for_record_return() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_RESUME_RECORD_VALID_WHEN_FIXTURE)

    _assert_diagnostic_code(excinfo, "resume_or_start_record_valid_when_invalid")


def test_typecheck_rejects_pointer_backed_resume_from() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_RESUME_POINTER_FIXTURE)

    _assert_diagnostic_code(excinfo, "resume_or_start_resume_path_invalid")


def test_typecheck_rejects_resume_or_start_name_mismatch_with_active_phase(tmp_path: Path) -> None:
    path = _rewrite_fixture(
        VALID_RESUME_FIXTURE,
        replacements=(("(resume-or-start checks", "(resume-or-start wrong-name"),),
        tmp_path=tmp_path,
        filename=VALID_RESUME_FIXTURE.name,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    _assert_diagnostic_code(excinfo, "phase_scope_name_mismatch")


def test_typecheck_rejects_resume_or_start_without_certified_adapter() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_UNCERTIFIED_RESUME_FIXTURE)

    assert excinfo.value.diagnostics[0].code in {
        "resume_or_start_contract_invalid",
        "recovery_gate_without_resume_or_start",
    }


def test_validate_reusable_phase_state_reuses_record_bundle_without_variant(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    expected_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    structured_contract = _checks_structured_contract()
    payload = _resume_state_payload(
        bundle_relpath="checks-state.json",
        return_type_name="ChecksResult",
        structured_contract_kind="record",
        structured_contract=structured_contract,
        artifact_requirements={
            "ChecksResult": [{"field_path": ["checks_report"], "under": "artifacts/work"}]
        },
        reusable_variants=[],
        current_public_inputs={"phase-ctx__phase-name": "checks", "inputs__report_path": "artifacts/work/checks-report.md"},
    )
    writer_payload_path = _write_payload_file(
        tmp_path,
        "write_reusable_state_ok.json",
        payload,
    )
    assert write_reusable_phase_state_v1.main(["write_reusable_phase_state_v1", writer_payload_path]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "OK",
        "bundle_path": "checks-state.json",
        "summary_path": "checks-state.reusable_state.json",
        "schema": "ReusablePhaseState.v1",
    }

    payload_path = _write_payload_file(tmp_path, "validate_ok.json", payload)

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out) == {
        "variant": "REUSABLE",
        "source_bundle_path": "checks-state.json",
        "source_bundle_sha256": expected_sha256,
    }


def test_write_reusable_phase_state_writes_sidecar_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    writes: list[tuple[Path, str, dict[str, object]]] = []

    def tracking_write(path: Path, text: str, **kwargs) -> None:
        assert path.parent.is_dir()
        writes.append((path, text, kwargs))
        common_atomic_write_text(path, text, **kwargs)

    monkeypatch.setattr(
        write_reusable_phase_state_v1,
        "atomic_write_text",
        tracking_write,
    )
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    payload_path = _write_payload_file(
        tmp_path,
        "write_summary.json",
        _resume_state_payload(
            bundle_relpath="checks-state.json",
            return_type_name="ChecksResult",
            structured_contract_kind="record",
            structured_contract=_checks_structured_contract(),
            artifact_requirements={
                "ChecksResult": [{"field_path": ["checks_report"], "under": "artifacts/work"}]
            },
            reusable_variants=[],
            current_public_inputs={"phase-ctx__phase-name": "checks", "inputs__report_path": "artifacts/work/checks-report.md"},
        ),
    )

    exit_code = write_reusable_phase_state_v1.main(["write_reusable_phase_state_v1", payload_path])
    response = json.loads(capsys.readouterr().out)
    sidecar_path = tmp_path / "checks-state.reusable_state.json"
    summary = json.loads(sidecar_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert response == {
        "status": "OK",
        "bundle_path": "checks-state.json",
        "summary_path": "checks-state.reusable_state.json",
        "schema": "ReusablePhaseState.v1",
    }
    assert sidecar_path.is_file()
    assert summary["schema"] == "ReusablePhaseState.v1"
    assert summary["summary_version"] == "v1"
    assert summary["result_type"] == "ChecksResult"
    assert summary["compatibility"] == {
        "dsl_version": "2.14",
        "state_schema_version": "v1",
        "reusable": True,
        "status": "REUSABLE",
    }
    assert summary["canonical_bundle_sha256"] == hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    assert summary["artifact_refs"] == [
        {
            "field_path": ["checks_report"],
            "relpath": "artifacts/work/checks-report.md",
            "under": "artifacts/work",
            "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        }
    ]
    assert writes == [
        (
            Path("checks-state.reusable_state.json"),
            json.dumps(summary, sort_keys=True),
            {},
        )
    ]


def test_write_reusable_phase_state_writes_declared_output_bundle_when_env_path_set(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "state/adapter-results/write_reusable_state.json")
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    payload_path = _write_payload_file(
        tmp_path,
        "write_summary_env.json",
        _resume_state_payload(
            bundle_relpath="checks-state.json",
            return_type_name="ChecksResult",
            structured_contract_kind="record",
            structured_contract=_checks_structured_contract(),
            artifact_requirements={
                "ChecksResult": [{"field_path": ["checks_report"], "under": "artifacts/work"}]
            },
            reusable_variants=[],
            current_public_inputs={"phase-ctx__phase-name": "checks", "inputs__report_path": "artifacts/work/checks-report.md"},
        ),
    )

    exit_code = write_reusable_phase_state_v1.main(["write_reusable_phase_state_v1", payload_path])
    stdout_payload = json.loads(capsys.readouterr().out)
    declared_bundle = tmp_path / "state" / "adapter-results" / "write_reusable_state.json"

    assert exit_code == 0
    assert declared_bundle.is_file()
    assert json.loads(declared_bundle.read_text(encoding="utf-8")) == stdout_payload


def test_validate_reusable_phase_state_writes_declared_variant_output_when_env_path_set(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    payload = _resume_state_payload(
        bundle_relpath="checks-state.json",
        return_type_name="ChecksResult",
        structured_contract_kind="record",
        structured_contract=_checks_structured_contract(),
        artifact_requirements={
            "ChecksResult": [{"field_path": ["checks_report"], "under": "artifacts/work"}]
        },
        reusable_variants=[],
        current_public_inputs={"phase-ctx__phase-name": "checks", "inputs__report_path": "artifacts/work/checks-report.md"},
    )
    writer_payload_path = _write_payload_file(tmp_path, "write_validate_env_state.json", payload)
    assert write_reusable_phase_state_v1.main(["write_reusable_phase_state_v1", writer_payload_path]) == 0
    capsys.readouterr()
    monkeypatch.setenv("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "state/adapter-results/validate_reusable_state.json")
    validate_payload_path = _write_payload_file(tmp_path, "validate_env_state.json", payload)

    exit_code = validate_reusable_phase_state.main(
        ["validate_reusable_phase_state", validate_payload_path]
    )
    stdout_payload = json.loads(capsys.readouterr().out)
    declared_bundle = tmp_path / "state" / "adapter-results" / "validate_reusable_state.json"

    assert exit_code == 0
    assert declared_bundle.is_file()
    assert json.loads(declared_bundle.read_text(encoding="utf-8")) == stdout_payload


def test_validate_reusable_phase_state_ignores_run_local_public_inputs_outside_hash_basis(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    payload = _resume_state_payload(
        bundle_relpath="checks-state.json",
        return_type_name="ChecksResult",
        structured_contract_kind="record",
        structured_contract=_checks_structured_contract(),
        artifact_requirements={
            "ChecksResult": [{"field_path": ["checks_report"], "under": "artifacts/work"}]
        },
        reusable_variants=[],
        current_public_inputs={
            "phase-ctx__phase-name": "checks",
            "inputs__report_path": "artifacts/work/checks-report.md",
            "phase-ctx__run__run-id": "run-1",
            "phase-ctx__run__state-root": "state/run-1",
            "phase-ctx__run__artifact-root": "artifacts/run-1",
            "phase-ctx__state-root": "state/checks/run-1",
            "phase-ctx__artifact-root": "artifacts/checks/run-1",
        },
    )
    payload["public_input_hash_basis"] = [
        "phase-ctx__phase-name",
        "inputs__report_path",
    ]
    writer_payload_path = _write_payload_file(tmp_path, "write_run_local_filtered_state.json", payload)
    assert write_reusable_phase_state_v1.main(["write_reusable_phase_state_v1", writer_payload_path]) == 0
    capsys.readouterr()

    validate_payload = dict(payload)
    validate_payload["current_public_inputs"] = {
        **payload["current_public_inputs"],
        "phase-ctx__run__run-id": "run-2",
        "phase-ctx__run__state-root": "state/run-2",
        "phase-ctx__run__artifact-root": "artifacts/run-2",
        "phase-ctx__state-root": "state/checks/run-2",
        "phase-ctx__artifact-root": "artifacts/checks/run-2",
    }
    validate_payload_path = _write_payload_file(tmp_path, "validate_run_local_filtered_state.json", validate_payload)

    exit_code = validate_reusable_phase_state.main(
        ["validate_reusable_phase_state", validate_payload_path]
    )
    payload_out = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload_out["variant"] == "REUSABLE"


def test_load_canonical_phase_result_writes_declared_output_bundle_when_env_path_set(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "state/adapter-results/load_canonical_phase_result.json")
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle = {"checks_report": "artifacts/work/checks-report.md"}
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract=structured_contract,
                        return_type_name="ChecksResult",
                    ),
                    "structured_contract_kind": "record",
                    "structured_contract": structured_contract,
                    "source_bundle_sha256": bundle_sha256,
                }
            ),
        ]
    )
    stdout_payload = json.loads(capsys.readouterr().out)
    declared_bundle = tmp_path / "state" / "adapter-results" / "load_canonical_phase_result.json"

    assert exit_code == 0
    assert declared_bundle.is_file()
    assert json.loads(declared_bundle.read_text(encoding="utf-8")) == stdout_payload


def test_validate_reusable_phase_state_classifies_bundle_without_sidecar_as_failed_prior_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    (tmp_path / "checks-state.json").write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    payload_path = _write_payload_file(
        tmp_path,
        "validate_failed_prior_state.json",
        _resume_state_payload(
            bundle_relpath="checks-state.json",
            return_type_name="ChecksResult",
            structured_contract_kind="record",
            structured_contract=_checks_structured_contract(),
            artifact_requirements={
                "ChecksResult": [{"field_path": ["checks_report"], "under": "artifacts/work"}]
            },
            reusable_variants=[],
            current_public_inputs={"phase-ctx__phase-name": "checks", "inputs__report_path": "artifacts/work/checks-report.md"},
        ),
    )

    exit_code = validate_reusable_phase_state.main(["validate_reusable_phase_state", payload_path])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {"variant": "FAILED_PRIOR_STATE"}


def test_validate_reusable_phase_state_classifies_stale_public_inputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    writer_payload = _resume_state_payload(
        bundle_relpath="checks-state.json",
        return_type_name="ChecksResult",
        structured_contract_kind="record",
        structured_contract=_checks_structured_contract(),
        artifact_requirements={
            "ChecksResult": [{"field_path": ["checks_report"], "under": "artifacts/work"}]
        },
        reusable_variants=[],
        current_public_inputs={"phase-ctx__phase-name": "checks", "inputs__report_path": "artifacts/work/checks-report.md"},
    )
    writer_payload_path = _write_payload_file(tmp_path, "write_stale_state.json", writer_payload)
    assert write_reusable_phase_state_v1.main(["write_reusable_phase_state_v1", writer_payload_path]) == 0
    capsys.readouterr()
    validate_payload = dict(writer_payload)
    validate_payload["current_public_inputs"] = {
        "phase-ctx__phase-name": "checks",
        "inputs__report_path": "artifacts/work/changed-report.md",
    }
    validate_payload_path = _write_payload_file(tmp_path, "validate_stale_state.json", validate_payload)

    exit_code = validate_reusable_phase_state.main(["validate_reusable_phase_state", validate_payload_path])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {"variant": "STALE"}


def test_validate_reusable_phase_state_classifies_schema_mismatch_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    (tmp_path / "checks-state.json").write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    sidecar_path = tmp_path / "checks-state.reusable_state.json"
    sidecar_path.write_text("{bad", encoding="utf-8")
    payload_path = _write_payload_file(
        tmp_path,
        "validate_schema_mismatch.json",
        _resume_state_payload(
            bundle_relpath="checks-state.json",
            return_type_name="ChecksResult",
            structured_contract_kind="record",
            structured_contract=_checks_structured_contract(),
            artifact_requirements={
                "ChecksResult": [{"field_path": ["checks_report"], "under": "artifacts/work"}]
            },
            reusable_variants=[],
            current_public_inputs={"phase-ctx__phase-name": "checks", "inputs__report_path": "artifacts/work/checks-report.md"},
        ),
    )

    exit_code = validate_reusable_phase_state.main(["validate_reusable_phase_state", payload_path])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {"variant": "SCHEMA_MISMATCH"}


def test_validate_reusable_phase_state_classifies_unsupported_version_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    writer_payload = _resume_state_payload(
        bundle_relpath="checks-state.json",
        return_type_name="ChecksResult",
        structured_contract_kind="record",
        structured_contract=_checks_structured_contract(),
        artifact_requirements={
            "ChecksResult": [{"field_path": ["checks_report"], "under": "artifacts/work"}]
        },
        reusable_variants=[],
        current_public_inputs={"phase-ctx__phase-name": "checks", "inputs__report_path": "artifacts/work/checks-report.md"},
    )
    writer_payload_path = _write_payload_file(tmp_path, "write_unsupported_state.json", writer_payload)
    assert write_reusable_phase_state_v1.main(["write_reusable_phase_state_v1", writer_payload_path]) == 0
    capsys.readouterr()
    sidecar_path = tmp_path / "checks-state.reusable_state.json"
    summary = json.loads(sidecar_path.read_text(encoding="utf-8"))
    summary["schema"] = "ReusablePhaseState.v9"
    sidecar_path.write_text(json.dumps(summary), encoding="utf-8")
    payload_path = _write_payload_file(tmp_path, "validate_unsupported_state.json", writer_payload)

    exit_code = validate_reusable_phase_state.main(["validate_reusable_phase_state", payload_path])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {"variant": "UNSUPPORTED_VERSION"}


def test_validate_reusable_phase_state_classifies_unsupported_compatibility_metadata(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    writer_payload = _resume_state_payload(
        bundle_relpath="checks-state.json",
        return_type_name="ChecksResult",
        structured_contract_kind="record",
        structured_contract=_checks_structured_contract(),
        artifact_requirements={
            "ChecksResult": [{"field_path": ["checks_report"], "under": "artifacts/work"}]
        },
        reusable_variants=[],
        current_public_inputs={"phase-ctx__phase-name": "checks", "inputs__report_path": "artifacts/work/checks-report.md"},
    )
    writer_payload_path = _write_payload_file(tmp_path, "write_incompatible_state.json", writer_payload)
    assert write_reusable_phase_state_v1.main(["write_reusable_phase_state_v1", writer_payload_path]) == 0
    capsys.readouterr()
    sidecar_path = tmp_path / "checks-state.reusable_state.json"
    summary = json.loads(sidecar_path.read_text(encoding="utf-8"))
    summary["compatibility"]["dsl_version"] = "2.99"
    sidecar_path.write_text(json.dumps(summary), encoding="utf-8")
    payload_path = _write_payload_file(tmp_path, "validate_incompatible_state.json", writer_payload)

    exit_code = validate_reusable_phase_state.main(["validate_reusable_phase_state", payload_path])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {"variant": "UNSUPPORTED_VERSION"}


def test_validate_reusable_phase_state_rejects_contract_fingerprint_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_mismatch.json",
        {
            "resume_from": "checks-state.json",
            "target_dsl_version": "2.14",
            "return_type_name": "ChecksResult",
            "structured_contract_kind": "record",
            "expected_contract_fingerprint": "2.14:ChecksResult:record:expected",
            "structured_contract": structured_contract,
            "reusable_variants": [],
            "artifact_requirements": {
                "ChecksResult": [
                    {"field_path": ["checks_report"], "under": "artifacts/work"}
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_contract_fingerprint_mismatch"}
    }


def test_validate_reusable_phase_state_rejects_contract_fingerprint_dsl_version_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_version_mismatch.json",
        {
            "resume_from": "checks-state.json",
            "target_dsl_version": "2.14",
            "return_type_name": "ChecksResult",
            "structured_contract_kind": "record",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="record",
                structured_contract=structured_contract,
                return_type_name="ChecksResult",
            ).replace("2.14:", "999.99:", 1),
            "structured_contract": structured_contract,
            "reusable_variants": [],
            "artifact_requirements": {
                "ChecksResult": [
                    {"field_path": ["checks_report"], "under": "artifacts/work"}
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_contract_fingerprint_mismatch"}
    }


def test_validate_reusable_phase_state_rejects_contract_fingerprint_return_type_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_return_type_mismatch.json",
        {
            "resume_from": "checks-state.json",
            "target_dsl_version": "2.14",
            "return_type_name": "ChecksResult",
            "structured_contract_kind": "record",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="record",
                structured_contract=structured_contract,
                return_type_name="ChecksResult",
            ).replace(":ChecksResult:", ":WrongType:", 1),
            "structured_contract": structured_contract,
            "reusable_variants": [],
            "artifact_requirements": {
                "ChecksResult": [
                    {"field_path": ["checks_report"], "under": "artifacts/work"}
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_contract_fingerprint_mismatch"}
    }


def test_validate_reusable_phase_state_rejects_pointer_file_authority(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pointer_path = tmp_path / "pointer.txt"
    pointer_path.write_text("state/phase.json\n", encoding="utf-8")
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_pointer.json",
        {
            "resume_from": "pointer.txt",
            "target_dsl_version": "2.14",
            "return_type_name": "ChecksResult",
            "structured_contract_kind": "record",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="record",
                structured_contract=structured_contract,
                return_type_name="ChecksResult",
            ),
            "structured_contract": structured_contract,
            "reusable_variants": [],
            "artifact_requirements": {
                "ChecksResult": [
                    {"field_path": ["checks_report"], "under": "artifacts/work"}
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {"error": {"type": "resume_state_contract_invalid"}}


def test_validate_reusable_phase_state_rejects_unsafe_required_artifact_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps(
            {
                "checks_report": "artifacts/../checks-report.md",
            }
        ),
        encoding="utf-8",
    )
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_unsafe.json",
        {
            "resume_from": "checks-state.json",
            "target_dsl_version": "2.14",
            "return_type_name": "ChecksResult",
            "structured_contract_kind": "record",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="record",
                structured_contract=structured_contract,
                return_type_name="ChecksResult",
            ),
            "structured_contract": structured_contract,
            "reusable_variants": [],
            "artifact_requirements": {
                "ChecksResult": [
                    {"field_path": ["checks_report"], "under": "artifacts/work"}
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {"error": {"type": "resume_state_contract_invalid"}}


def test_validate_reusable_phase_state_rejects_missing_required_artifact_for_reusable_union_variant(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    execution_report = tmp_path / "artifacts" / "work" / "execution.md"
    execution_report.parent.mkdir(parents=True, exist_ok=True)
    execution_report.write_text("execution", encoding="utf-8")
    bundle_path = tmp_path / "plan-gate-state.json"
    bundle_path.write_text(
        json.dumps(
            {
                "variant": "APPROVED",
                "execution_report_path": "artifacts/work/execution.md",
            }
        ),
        encoding="utf-8",
    )
    structured_contract = {
        "discriminant": {
            "name": "variant",
            "json_pointer": "/variant",
            "type": "enum",
            "allowed": ["APPROVED", "BLOCKED"],
        },
        "shared_fields": [],
        "variants": {
            "APPROVED": {
                "fields": [
                    {
                        "name": "execution_report_path",
                        "json_pointer": "/execution_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    }
                ]
            },
            "BLOCKED": {
                "fields": [
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
                        "type": "string",
                    },
                ]
            },
        },
    }
    payload = {
        "bundle_path": "plan-gate-state.json",
        "resume_from": "plan-gate-state.json",
        "target_dsl_version": "2.14",
        "return_type_name": "PlanGateResult",
        "structured_contract_kind": "union",
        "expected_contract_fingerprint": _structured_contract_fingerprint(
            structured_contract_kind="union",
            structured_contract=structured_contract,
            return_type_name="PlanGateResult",
        ),
        "structured_contract": structured_contract,
        "summary_schema": "ReusablePhaseState.v1",
        "summary_version": "v1",
        "sidecar_suffix": ".reusable_state.json",
        "canonical_bundle_digest_field": "canonical_bundle_sha256",
        "reusable_variants": ["APPROVED"],
        "artifact_requirements": {
            "APPROVED": [
                {
                    "field_path": ["execution_report_path"],
                    "under": "artifacts/work",
                }
            ]
        },
        "public_input_hash_basis": ["phase-ctx__phase-name"],
        "current_public_inputs": {"phase-ctx__phase-name": "plan-gate"},
        "producer_fingerprint_basis": {
            "workflow_name": "resume-test",
            "return_type_name": "PlanGateResult",
            "structured_contract_kind": "union",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="union",
                structured_contract=structured_contract,
                return_type_name="PlanGateResult",
            ),
            "target_dsl_version": "2.14",
            "compiler_version": "0.1.0",
            "reusable_variants": ["APPROVED"],
            "public_input_hash_basis": ["phase-ctx__phase-name"],
        },
        "source_run_id": "test-run",
        "source_step_id": "resume-step",
        "source_call_frame_id": "root",
        "phase_id": "plan-gate",
        "created_at": "2026-06-02T00:00:00Z",
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_union_missing_artifact.json",
        payload,
    )
    assert write_reusable_phase_state_v1.main(["write_reusable_phase_state_v1", payload_path]) == 0
    capsys.readouterr()
    execution_report.unlink()

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out) == {"variant": "MISSING_ARTIFACT"}


def _typecheck_top_level_names() -> set[str]:
    source_path = Path(importlib.import_module("orchestrator.workflow_lisp.typecheck").__file__)
    return _module_top_level_names(source_path)


def _module_top_level_names(source_path: Path) -> set[str]:
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in module.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef))
    }


def test_review_loop_owner_split_moves_stdlib_bridge_typing_out_of_typecheck_facade() -> None:
    package_dir = Path(importlib.import_module("orchestrator.workflow_lisp").__file__).resolve().parent
    stdlib_owner_path = package_dir / "phase_stdlib_typecheck.py"
    dispatch_top_level_names = _module_top_level_names(package_dir / "typecheck_dispatch.py")
    top_level_names = _typecheck_top_level_names()

    assert not stdlib_owner_path.exists()
    assert "_typecheck_stdlib_specialization_expr" not in top_level_names
    assert "_validate_review_loop_result_contract" not in top_level_names
    assert dispatch_top_level_names.isdisjoint(
        {
            "_phase_review_loop_result_contract_impl",
            "_phase_review_loop_typecheck_impl",
            "_specialize_phase_review_loop_request",
            "_review_loop_generated_prefix",
            "_review_loop_generated_procedure_name",
            "_generated_expr_span",
            "_initial_review_loop_report_expr",
        }
    )


def test_validate_reusable_phase_state_rejects_symlinked_external_bundle_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    external_root = tmp_path.parent / f"{tmp_path.name}_external"
    external_root.mkdir()
    bundle = {"checks_report": "artifacts/work/checks-report.md"}
    external_bundle_path = external_root / "checks-state.json"
    external_bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    bundle_link = tmp_path / "checks-state-link.json"
    bundle_link.symlink_to(external_bundle_path)
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_symlinked_external_bundle.json",
        {
            "resume_from": "checks-state-link.json",
            "target_dsl_version": "2.14",
            "return_type_name": "ChecksResult",
            "structured_contract_kind": "record",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="record",
                structured_contract=structured_contract,
                return_type_name="ChecksResult",
            ),
            "structured_contract": structured_contract,
            "reusable_variants": [],
            "artifact_requirements": {
                "ChecksResult": [
                    {"field_path": ["checks_report"], "under": "artifacts/work"}
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {"error": {"type": "resume_state_contract_invalid"}}


def test_load_canonical_phase_result_accepts_bundle_path_contract(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle = {"checks_report": "artifacts/work/checks-report.md"}
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract=structured_contract,
                        return_type_name="ChecksResult",
                    ),
                    "structured_contract_kind": "record",
                    "structured_contract": structured_contract,
                    "source_bundle_sha256": bundle_sha256,
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out) == bundle


def test_load_canonical_phase_result_keeps_bundle_bytes_after_path_replacement(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle = {"checks_report": "artifacts/work/checks-report.md"}
    bundle_bytes = json.dumps(bundle).encode("utf-8")
    bundle_path.write_bytes(bundle_bytes)
    external_root = tmp_path.parent / f"{tmp_path.name}_external"
    external_root.mkdir()
    external_bundle_path = external_root / "checks-state.json"
    external_bundle_path.write_text(
        json.dumps({"checks_report": "external-sentinel.md"}),
        encoding="utf-8",
    )
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    original_read = load_canonical_phase_result.WorkspaceFiles.read
    original_path_read_bytes = Path.read_bytes
    original_path_read_text = Path.read_text
    read_paths: list[Path] = []
    external_bundle_reads: list[Path] = []

    def replace_bundle_after_read(owner, path: str | Path) -> bytes:
        candidate = Path(path)
        read_paths.append(candidate)
        content = original_read(owner, path)
        if candidate == Path("checks-state.json"):
            bundle_path.unlink()
            bundle_path.symlink_to(external_bundle_path)
        return content

    def track_external_bundle_read(path: Path) -> None:
        if path.absolute() == bundle_path and path.is_symlink():
            external_bundle_reads.append(path)

    def tracked_path_read_bytes(path: Path) -> bytes:
        track_external_bundle_read(path)
        return original_path_read_bytes(path)

    def tracked_path_read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        track_external_bundle_read(path)
        return original_path_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(
        load_canonical_phase_result.WorkspaceFiles,
        "read",
        replace_bundle_after_read,
    )
    monkeypatch.setattr(Path, "read_bytes", tracked_path_read_bytes)
    monkeypatch.setattr(Path, "read_text", tracked_path_read_text)
    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract=structured_contract,
                        return_type_name="ChecksResult",
                    ),
                    "structured_contract_kind": "record",
                    "structured_contract": structured_contract,
                    "source_bundle_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out) == bundle
    assert bundle_path.is_symlink()
    assert read_paths == [Path("checks-state.json")]
    assert external_bundle_reads == []


def test_load_canonical_phase_result_rejects_digest_mismatch_before_emit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/checks-report.md"}),
        encoding="utf-8",
    )
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract=structured_contract,
                        return_type_name="ChecksResult",
                    ),
                    "structured_contract_kind": "record",
                    "structured_contract": structured_contract,
                    "source_bundle_sha256": "not-the-current-digest",
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_bundle_mutated_before_load"}
    }


def test_load_canonical_phase_result_rejects_contract_fingerprint_dsl_version_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle = {"checks_report": "artifacts/work/checks-report.md"}
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract=structured_contract,
                        return_type_name="ChecksResult",
                    ).replace("2.14:", "999.99:", 1),
                    "structured_contract_kind": "record",
                    "structured_contract": structured_contract,
                    "source_bundle_sha256": bundle_sha256,
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_contract_fingerprint_mismatch"}
    }


def test_load_canonical_phase_result_rejects_contract_fingerprint_return_type_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle = {"checks_report": "artifacts/work/checks-report.md"}
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract=structured_contract,
                        return_type_name="ChecksResult",
                    ).replace(":ChecksResult:", ":WrongType:", 1),
                    "structured_contract_kind": "record",
                    "structured_contract": structured_contract,
                    "source_bundle_sha256": bundle_sha256,
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_contract_fingerprint_mismatch"}
    }


def test_load_canonical_phase_result_rejects_unsafe_bundle_path_with_stable_error_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "../unsafe.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract={
                            "fields": [
                                {
                                    "name": "checks_report",
                                    "json_pointer": "/checks_report",
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": True,
                                }
                            ]
                        },
                        return_type_name="ChecksResult",
                    ),
                    "structured_contract_kind": "record",
                    "structured_contract": {
                        "fields": [
                            {
                                "name": "checks_report",
                                "json_pointer": "/checks_report",
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": True,
                            }
                        ]
                    },
                    "source_bundle_sha256": "unused",
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {"error": {"type": "resume_state_path_unsafe"}}


def test_load_canonical_phase_result_rejects_malformed_bundle_with_stable_error_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text("{bad", encoding="utf-8")
    actual_digest = hashlib.sha256(bundle_path.read_bytes()).hexdigest()

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract={
                            "fields": [
                                {
                                    "name": "checks_report",
                                    "json_pointer": "/checks_report",
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": True,
                                }
                            ]
                        },
                        return_type_name="ChecksResult",
                    ),
                    "structured_contract_kind": "record",
                    "structured_contract": {
                        "fields": [
                            {
                                "name": "checks_report",
                                "json_pointer": "/checks_report",
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": True,
                            }
                        ]
                    },
                    "source_bundle_sha256": actual_digest,
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_loader_schema_invalid"}
    }


def test_load_canonical_phase_result_rejects_symlinked_external_bundle_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    external_root = tmp_path.parent / f"{tmp_path.name}_external"
    external_root.mkdir()
    bundle = {"checks_report": "artifacts/work/checks-report.md"}
    external_bundle_path = external_root / "checks-state.json"
    external_bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    bundle_link = tmp_path / "checks-state-link.json"
    bundle_link.symlink_to(external_bundle_path)

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state-link.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract={
                            "fields": [
                                {
                                    "name": "checks_report",
                                    "json_pointer": "/checks_report",
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": True,
                                }
                            ]
                        },
                        return_type_name="ChecksResult",
                    ),
                    "structured_contract_kind": "record",
                    "structured_contract": {
                        "fields": [
                            {
                                "name": "checks_report",
                                "json_pointer": "/checks_report",
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": True,
                            }
                        ]
                    },
                    "source_bundle_sha256": hashlib.sha256(
                        bundle_link.read_bytes()
                    ).hexdigest(),
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {"error": {"type": "resume_state_path_unsafe"}}
