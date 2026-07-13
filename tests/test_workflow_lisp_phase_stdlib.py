from __future__ import annotations

import ast
import hashlib
import importlib
import json
import re
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

import orchestrator.workflow_lisp.compiler as workflow_lisp_compiler
from orchestrator.workflow_lisp.adapters import (
    load_canonical_phase_result,
    reusable_phase_state_common,
    validate_reusable_phase_state,
    write_reusable_phase_state_v1,
)
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _imported_type_refs,
    _augment_resume_command_boundaries,
    _validate_definition_module,
    compile_stage1_entrypoint,
    compile_stage3_entrypoint,
    compile_stage3_module,
)
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
from orchestrator.workflow_lisp.lowering import (
    _managed_write_root_bindings,
    _managed_write_root_requirements_for_callable,
    _observed_statement_families,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.stdlib_contracts import (
    STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME,
    STDLIB_LOWERING_CONTRACTS_BY_FORM,
)
from orchestrator.workflow_lisp.modules import build_import_scope
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, UnionTypeRef
from orchestrator.workflow_lisp.workflows import (
    CertifiedAdapterBinding,
    CommandBoundaryEnvironment,
    ExternEnvironment,
    ExternalToolBinding,
    PromptExtern,
    ProviderExtern,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)
import orchestrator.workflow.loaded_bundle as loaded_bundle_helpers


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_LIBRARY_ROOT = REPO_ROOT / "workflows" / "library"
STDLIB_MODULE_ROOT = REPO_ROOT / "orchestrator" / "workflow_lisp" / "stdlib_modules"


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


def _workflow_generated_path_allocations(bundle):
    helper = getattr(loaded_bundle_helpers, "workflow_generated_path_allocations")
    return helper(bundle)


def _allocation_field(allocation, field_name: str):
    if isinstance(allocation, dict):
        return allocation[field_name]
    return getattr(allocation, field_name)


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


def _plan_gate_structured_contract() -> dict[str, object]:
    return {
        "discriminant": {
            "name": "variant",
            "json_pointer": "/variant",
            "type": "enum",
            "allowed": ["APPROVED", "BLOCKED"],
        },
        "shared_fields": [
            {
                "name": "shared_report_path",
                "json_pointer": "/shared_report_path",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ],
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


def _reusable_state_sidecar_relpath(bundle_relpath: str) -> str:
    bundle_path = Path(bundle_relpath)
    if bundle_path.suffix:
        return bundle_path.with_suffix("").as_posix() + ".reusable_state.json"
    return bundle_path.as_posix() + ".reusable_state.json"


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


def _extern_environment() -> ExternEnvironment:
    return ExternEnvironment(
        bindings_by_name={
            "providers.execute": ProviderExtern(
                name="providers.execute",
                provider_id="fake-execute",
            ),
            "providers.review": ProviderExtern(
                name="providers.review",
                provider_id="fake-review",
            ),
            "providers.fix": ProviderExtern(
                name="providers.fix",
                provider_id="fake-fix",
            ),
            "prompts.implementation.execute": PromptExtern(
                name="prompts.implementation.execute",
                asset_file="prompts/implementation/execute.md",
            ),
            "prompts.implementation.review": PromptExtern(
                name="prompts.implementation.review",
                asset_file="prompts/implementation/review.md",
            ),
            "prompts.implementation.fix": PromptExtern(
                name="prompts.implementation.fix",
                asset_file="prompts/implementation/fix.md",
            ),
        }
    )


def _command_boundary_environment() -> CommandBoundaryEnvironment:
    return CommandBoundaryEnvironment(
        bindings_by_name={
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
        }
    )


def _local_workflow_name_matches(actual: str, expected: str) -> bool:
    return actual == expected or actual.endswith(f"::{expected}")


def _validated_bundle_by_local_name(result, expected: str):
    for name, bundle in result.validated_bundles.items():
        if _local_workflow_name_matches(name, expected):
            return bundle
    raise KeyError(expected)


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


def _compile_module_fixture(
    path: Path,
    *,
    tmp_path: Path,
    extra_source_roots: tuple[Path, ...] = (),
    validate_shared: bool = False,
):
    source = path.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None, f"fixture is missing defmodule: {path}"
    resolved_module_name = module_match.group(1)
    module_path = (tmp_path / Path(*resolved_module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    return compile_stage3_entrypoint(
        module_path,
        source_roots=(*extra_source_roots, tmp_path),
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
            "validate_review_findings_v1": STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME[
                "validate_review_findings_v1"
            ],
        },
        validate_shared=validate_shared,
        workspace_root=tmp_path,
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


def _iter_nested_steps(steps):
    for step in steps:
        yield step
        match_block = step.get("match")
        if isinstance(match_block, dict):
            for case in match_block.get("cases", {}).values():
                if isinstance(case, dict):
                    yield from _iter_nested_steps(case.get("steps", ()))
        repeat_block = step.get("repeat_until")
        if isinstance(repeat_block, dict):
            yield from _iter_nested_steps(repeat_block.get("steps", ()))
        conditional = step.get("if")
        if isinstance(conditional, dict):
            for branch_name in ("then", "else"):
                branch = step.get(branch_name)
                if isinstance(branch, dict):
                    yield from _iter_nested_steps(branch.get("steps", ()))


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _iter_nested_steps(steps):
    for step in steps:
        yield step
        match_block = step.get("match")
        if isinstance(match_block, dict):
            cases = match_block.get("cases", {})
            if isinstance(cases, dict):
                for case in cases.values():
                    case_steps = case.get("steps", [])
                    if isinstance(case_steps, list):
                        yield from _iter_nested_steps(case_steps)
        repeat_block = step.get("repeat_until")
        if isinstance(repeat_block, dict):
            nested_steps = repeat_block.get("steps", [])
            if isinstance(nested_steps, list):
                yield from _iter_nested_steps(nested_steps)


def _assert_contract_matches_observed_families(contract, *, steps) -> set[str]:
    observed = set(_observed_statement_families(steps))
    assert set(contract.required_statement_families).issubset(observed)
    for alternatives in contract.alternative_statement_family_sets:
        matches = observed.intersection(alternatives)
        assert len(matches) == 1
    return observed


def _assert_contract_source_map_expectations(
    contract,
    lowered,
    *,
    hidden_inputs: tuple[str, ...] = (),
    generated_paths: tuple[str, ...] = (),
) -> None:
    authored_steps = list(_iter_nested_steps(lowered.authored_mapping["steps"]))
    assert authored_steps
    for step in authored_steps:
        step_id = step.get("id")
        if isinstance(step_id, str):
            assert step_id in lowered.origin_map.step_spans
            assert lowered.origin_map.step_spans[step_id].origin_key
    if "high_level_form_origin" in contract.source_map_expectations:
        assert any(origin.form_path for origin in lowered.origin_map.step_spans.values())
    if "generated_hidden_input_span" in contract.source_map_expectations:
        for hidden_input in hidden_inputs:
            assert hidden_input in lowered.origin_map.internal_input_spans
    if "generated_hidden_path_span" in contract.source_map_expectations:
        for generated_path in generated_paths:
            assert generated_path in lowered.origin_map.generated_path_spans


def _lowered_workflow_by_name(result, workflow_name: str):
    return next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == workflow_name
    )


def _lowered_workflow_with_provider(result, provider_name: str):
    def _has_provider(step):
        if not isinstance(step, dict):
            return False
        if step.get("provider") == provider_name:
            return True
        if "repeat_until" in step and any(_has_provider(child) for child in step["repeat_until"].get("steps", [])):
            return True
        if "then" in step and any(_has_provider(child) for child in step["then"].get("steps", [])):
            return True
        match_cases = step.get("match", {}).get("cases", {})
        return any(_has_provider(child) for case in match_cases.values() for child in case.get("steps", []))

    return next(
        workflow
        for workflow in result.lowered_workflows
        if any(_has_provider(step) for step in workflow.authored_mapping["steps"])
    )


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


def test_lowering_run_provider_phase_derives_phase_bundle_path(tmp_path: Path) -> None:
    result = _compile(VALID_RUN_PROVIDER_FIXTURE, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if _local_workflow_name_matches(workflow.typed_workflow.definition.name, "run-provider-phase-demo")
    )
    provider_step = next(step for step in authored["steps"] if step.get("provider") == "fake-execute")

    assert provider_step["variant_output"]["path"].endswith("/phases/implementation/state.json")
    assert provider_step["variant_output"]["path"].startswith("${inputs.phase-ctx__state-root}")


def test_lowering_run_provider_phase_materializes_and_consumes_authored_inputs(tmp_path: Path) -> None:
    result = _compile(VALID_RUN_PROVIDER_FIXTURE, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if _local_workflow_name_matches(workflow.typed_workflow.definition.name, "run-provider-phase-demo")
    )
    materialize_step = next(step for step in authored["steps"] if "materialize_artifacts" in step)
    provider_step = next(step for step in authored["steps"] if step.get("provider") == "fake-execute")

    assert [value["name"] for value in materialize_step["materialize_artifacts"]["values"]] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]
    assert [consume["artifact"] for consume in provider_step["consumes"]] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]
    assert provider_step["prompt_consumes"] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]


def test_lowering_produce_one_of_uses_pre_snapshot_and_select_variant_output(tmp_path: Path) -> None:
    result = _compile(VALID_RUN_PROVIDER_FIXTURE, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if _local_workflow_name_matches(workflow.typed_workflow.definition.name, "produce-one-of-demo")
    )
    assert any("pre_snapshot" in step for step in authored["steps"])
    assert any("select_variant_output" in step for step in authored["steps"])


def test_lowering_phase_snapshot_effects_fixture_keeps_orchestrate_pre_snapshot(tmp_path: Path) -> None:
    result = _compile(VALID_PHASE_SNAPSHOT_EFFECTS_FIXTURE, tmp_path=tmp_path)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if _local_workflow_name_matches(workflow.typed_workflow.definition.name, "orchestrate")
    )

    assert any("pre_snapshot" in step for step in authored["steps"])


def test_lowering_pointer_materialization_effects_fixture_keeps_orchestrate_pointer_paths(tmp_path: Path) -> None:
    result = _compile(VALID_POINTER_MATERIALIZATION_EFFECTS_FIXTURE, tmp_path=tmp_path)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if _local_workflow_name_matches(workflow.typed_workflow.definition.name, "orchestrate")
    )
    materialize_step = next(step for step in authored["steps"] if "materialize_artifacts" in step)

    assert all(
        "pointer" in value and "path" in value["pointer"]
        for value in materialize_step["materialize_artifacts"]["values"]
    )


def test_lowering_produce_one_of_materializes_and_consumes_authored_inputs(tmp_path: Path) -> None:
    result = _compile(VALID_RUN_PROVIDER_FIXTURE, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if _local_workflow_name_matches(workflow.typed_workflow.definition.name, "produce-one-of-demo")
    )
    materialize_step = next(step for step in authored["steps"] if "materialize_artifacts" in step)
    provider_step = next(step for step in authored["steps"] if step.get("provider") == "fake-execute")

    assert [value["name"] for value in materialize_step["materialize_artifacts"]["values"]] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]
    assert [consume["artifact"] for consume in provider_step["consumes"]] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]
    assert provider_step["prompt_consumes"] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]


def test_shared_validation_accepts_run_provider_phase_and_produce_one_of(tmp_path: Path) -> None:
    result = _compile(
        VALID_RUN_PROVIDER_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    assert {
        workflow.typed_workflow.definition.name.rsplit("::", 1)[-1] for workflow in result.lowered_workflows
    } >= {"run-provider-phase-demo", "produce-one-of-demo"}


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


def test_linked_builtin_std_phase_owner_lane_compiles_design_delta_implementation_phase(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        DESIGN_DELTA_IMPLEMENTATION_PHASE_LIBRARY_MODULE,
        source_roots=(WORKFLOW_LIBRARY_ROOT,),
        provider_externs=_design_delta_provider_externs(),
        prompt_externs=_design_delta_prompt_externs(),
        command_boundaries=_design_delta_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered_names = {
        workflow.typed_workflow.definition.name
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }

    assert "lisp_frontend_design_delta/implementation_phase::implementation-phase" in lowered_names


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
        package_dir / "lowering" / "core.py",
        package_dir / "lowering" / "phase_scope.py",
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


def test_lowering_review_loop_carries_last_review_report_through_loop_outputs(tmp_path: Path) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::review-revise-loop-demo")
    )
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    loop_outputs = repeat_step["repeat_until"]["outputs"]
    on_exhausted = repeat_step["repeat_until"]["on_exhausted"]["outputs"]

    assert "state__last_review_report" in loop_outputs
    assert "result__last_review_report" in loop_outputs
    assert "result__last_review_report" not in on_exhausted
    assert repeat_step["repeat_until"]["steps"]

    body_steps = list(_iter_nested_steps(repeat_step["repeat_until"]["steps"]))
    assert any(
        isinstance(step.get("call"), str) and step["call"].endswith("::run-review.v1")
        for step in body_steps
    )
    assert any(
        isinstance(step.get("call"), str) and step["call"].endswith("::apply-fix.v1")
        for step in body_steps
    )
    assert any("match" in step for step in body_steps)
    assert any(
        any(step.get("provider") == provider for step in workflow.authored_mapping.get("steps", ()))
        for provider in ("fake-review", "fake-fix")
        for workflow in result.lowered_workflows
    )

    normalization_step = next(
        step
        for step in authored["steps"]
        if step.get("match", {}).get("ref", "").endswith(".artifacts.result__variant")
    )
    assert normalization_step["match"]["ref"].endswith(".artifacts.result__variant")
    assert set(normalization_step["match"]["cases"]) == {"APPROVED", "BLOCKED", "EXHAUSTED"}
    exhausted_case = normalization_step["match"]["cases"]["EXHAUSTED"]
    assert exhausted_case["outputs"]["return__last_review_report"]["from"]["ref"].endswith(
        "__loop.artifacts.state__last_review_report"
    )


def test_lowering_review_loop_materializes_and_consumes_authored_inputs(tmp_path: Path) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::review-revise-loop-demo")
    )
    materialize_step = next(step for step in authored["steps"] if "materialize_artifacts" in step)
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    body_steps = list(_iter_nested_steps(repeat_step["repeat_until"]["steps"]))
    review_call_step = next(
        step
        for step in body_steps
        if isinstance(step.get("call"), str) and step["call"].endswith("::run-review.v1")
    )
    review_workflow = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::run-review.v1")
    )
    fix_workflow = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::apply-fix.v1")
    )
    review_step = next(step for step in review_workflow["steps"] if step.get("provider") == "fake-review")
    fix_step = next(step for step in fix_workflow["steps"] if step.get("provider") == "fake-fix")

    seed_values = {
        value["name"]: value
        for value in materialize_step["materialize_artifacts"]["values"]
    }
    assert {
        "state__completed__execution_report_path",
        "state__inputs__design_review_prompt",
        "state__inputs__fix_plan_prompt",
        "state__last_review_report",
        "state__latest_findings__schema_version",
        "state__latest_findings__items_path",
    } <= set(seed_values)
    assert seed_values["state__last_review_report"]["source"] == {
        "literal": "artifacts/review/last-review-report.md"
    }
    assert seed_values["state__latest_findings__items_path"]["source"] == {
        "literal": "artifacts/work/review-findings-seed.json"
    }
    assert set(review_call_step["with"]) >= {
        "completed__execution_report_path",
        "inputs__design_review_prompt",
        "inputs__fix_plan_prompt",
    }
    assert review_step["asset_file"] == "prompts/implementation/review.md"
    assert fix_step["asset_file"] == "prompts/implementation/fix.md"


def test_review_loop_seed_state_does_not_reuse_initial_report_as_findings_path(tmp_path: Path) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::review-revise-loop-demo")
    )
    seed_step = next(step for step in authored["steps"] if step["name"].endswith("__seed"))
    seed_values = {
        value["name"]: value
        for value in seed_step["materialize_artifacts"]["values"]
    }

    assert seed_values["state__latest_findings__items_path"]["source"] != {
        "ref": "inputs.completed__execution_report_path"
    }
    assert seed_values["state__latest_findings__items_path"]["source"] != seed_values["state__last_review_report"]["source"]


def test_review_loop_seed_state_uses_placeholder_for_noncanonical_completed_report_field(tmp_path: Path) -> None:
    path = _rewrite_fixture(
        VALID_REVIEW_LOOP_FIXTURE,
        replacements=(
            ("(execution_report_path WorkReport)", "(summary_report WorkReport)"),
            ("completed.execution_report_path", "completed.summary_report"),
            ("completed.execution_report_path", "completed.summary_report"),
        ),
        tmp_path=tmp_path,
        filename="phase_stdlib_review_loop.orc",
    )
    result = _compile(path, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::review-revise-loop-demo")
    )
    seed_step = next(step for step in authored["steps"] if step["name"].endswith("__seed"))
    seed_values = {
        value["name"]: value
        for value in seed_step["materialize_artifacts"]["values"]
    }

    assert seed_values["state__latest_findings__items_path"]["source"] == {
        "literal": "artifacts/work/review-findings-seed.json"
    }


def test_review_loop_seed_state_uses_review_report_placeholder_for_noncanonical_completed_report_field(
    tmp_path: Path,
) -> None:
    path = _rewrite_fixture(
        VALID_REVIEW_LOOP_FIXTURE,
        replacements=(
            ("(execution_report_path WorkReport)", "(summary_report WorkReport)"),
            ("completed.execution_report_path", "completed.summary_report"),
            ("completed.execution_report_path", "completed.summary_report"),
        ),
        tmp_path=tmp_path,
        filename="phase_stdlib_review_loop.orc",
    )
    result = _compile(path, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::review-revise-loop-demo")
    )
    seed_step = next(step for step in authored["steps"] if step["name"].endswith("__seed"))
    seed_values = {
        value["name"]: value
        for value in seed_step["materialize_artifacts"]["values"]
    }

    assert seed_values["state__last_review_report"]["source"] == {
        "literal": "artifacts/review/last-review-report.md"
    }


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


def test_review_loop_valid_fixture_preserves_review_report_and_findings_roots(tmp_path: Path) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::review-revise-loop-demo")
    )
    outputs = {
        field.generated_name: field.contract_definition
        for field in lowered.boundary_projection.flattened_outputs
    }

    assert outputs["return__review_report"]["under"] == "artifacts/review"
    assert outputs["return__last_review_report"]["under"] == "artifacts/review"
    assert "return__progress_report" not in outputs
    assert outputs["return__findings__items_path"]["under"] == "artifacts/work"


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


def test_authored_loop_state_review_findings_keeps_strict_relpath_contracts(
    tmp_path: Path,
) -> None:
    module_path = _write_module(
        tmp_path / "authored_loop_state_review_findings.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule authored_loop_state_review_findings)",
                "  (import std/phase :only (ReviewFindings ReviewFindingsJsonPath))",
                "  (defworkflow authored-loop-state-review-findings",
                "    ((items_path ReviewFindingsJsonPath))",
                "    -> ReviewFindings",
                "    (let* ((findings",
                "             (record ReviewFindings",
                '               :schema_version "ReviewFindings.v1"',
                "               :items_path items_path)))",
                "      (loop/recur",
                "        :max 2",
                "        :state (loop-state",
                "                 (latest_findings ReviewFindings findings)",
                "                 (done Bool false))",
                "        (fn (current)",
                "          (if current.done",
                "            (done current.latest_findings)",
                "            (continue (loop-state :like current :done true))))))))",
            ]
        )
        + "\n",
    )
    result = _compile(module_path, tmp_path=tmp_path, validate_shared=True)

    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::authored-loop-state-review-findings")
    )
    authored = lowered.authored_mapping
    seed_step = next(step for step in authored["steps"] if step["name"].endswith("__seed"))
    repeat_step = next(step for step in authored["steps"] if step["name"].endswith("__loop"))
    seed_values = {
        value["name"]: value
        for value in seed_step["materialize_artifacts"]["values"]
    }
    outputs = repeat_step["repeat_until"]["outputs"]

    assert seed_values["state__latest_findings__schema_version"]["source"] == {"literal": "ReviewFindings.v1"}
    assert seed_values["state__latest_findings__items_path"]["source"] == {"ref": "inputs.items_path"}
    assert "state__latest_findings__schema_version" in outputs
    assert outputs["state__latest_findings__items_path"]["must_exist_target"] is True
    assert outputs["state__latest_findings__items_path"]["under"] == "artifacts/work"

    current_state_step = next(
        step
        for step in repeat_step["repeat_until"]["steps"]
        if step["name"].endswith("__body__state")
    )
    carried_copy = next(
        nested_step
        for nested_step in current_state_step["then"]["steps"]
        if nested_step["name"].endswith("__use_carried_state")
    )
    carried_contract = next(
        value["contract"]
        for value in carried_copy["materialize_artifacts"]["values"]
        if value["name"] == "state__latest_findings__items_path"
    )
    carried_names = {
        value["name"]
        for value in carried_copy["materialize_artifacts"]["values"]
    }

    assert carried_contract["must_exist_target"] is True
    assert {
        "state__latest_findings__schema_version",
        "state__latest_findings__items_path",
    } <= carried_names
    assert any(
        name.endswith("state__latest_findings__items_path")
        for name in lowered.origin_map.generated_path_spans
    )
    assert any(
        origin.span.start.path.endswith("authored_loop_state_review_findings.orc")
        for origin in lowered.origin_map.generated_path_spans.values()
    )


def test_shared_validation_accepts_review_revise_loop(tmp_path: Path) -> None:
    result = _compile(
        VALID_REVIEW_LOOP_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    assert any(
        workflow.typed_workflow.definition.name.endswith("::review-revise-loop-demo")
        for workflow in result.lowered_workflows
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


def test_review_revise_loop_review_bundle_path_is_generated_write_root(tmp_path: Path) -> None:
    result = _compile(
        VALID_REVIEW_LOOP_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::run-review.v1")
    )
    authored = lowered.authored_mapping
    review_step = next(
        step
        for step in authored["steps"]
        if step.get("provider") == "fake-review"
    )
    review_path = review_step["variant_output"]["path"]
    hidden_input = review_path.removeprefix("${inputs.").removesuffix("}")

    assert review_path.startswith("${inputs.__write_root__")
    assert review_path.endswith("__result_bundle}")
    generated_inputs = {
        item.generated_name: item.reason
        for item in lowered.boundary_projection.generated_internal_inputs
    }
    assert hidden_input.startswith("__write_root__")
    assert hidden_input in authored["inputs"]
    assert generated_inputs[hidden_input] == "managed_write_root"


def test_resume_or_start_workflow_call_write_root_allocation_uses_call_frame_identity(tmp_path: Path) -> None:
    result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path, validate_shared=True)

    bundle = _validated_bundle_by_local_name(result, "resume-plan-gate")
    allocation = next(
        item
        for item in _workflow_generated_path_allocations(bundle)
        if _allocation_field(item, "semantic_role") == "reusable_call_write_root"
    )

    assert _allocation_field(allocation, "privacy") == "compatibility_view"
    assert _allocation_field(allocation, "resume_scope") == "call_frame"
    generated_input_name = _allocation_field(allocation, "generated_input_name")
    assert "plan_run" in generated_input_name
    assert generated_input_name.endswith("__resolve_plan_gate__result_bundle")
    assert _allocation_field(allocation, "concrete_path_template").startswith(
        ".orchestrate/workflow_lisp/calls/"
    )
    assert _allocation_field(allocation, "path_safety_policy") == "workspace_relative"
    assert "resume-plan-gate" in _allocation_field(allocation, "stable_identity")
    assert "plan-run" in _allocation_field(allocation, "stable_identity")
    assert "resolve_plan_gate" in _allocation_field(allocation, "stable_identity")


def test_run_provider_phase_generated_bundle_paths_use_allocator_metadata(tmp_path: Path) -> None:
    result = _compile(VALID_RUN_PROVIDER_FIXTURE, tmp_path=tmp_path, validate_shared=True)

    bundle = _validated_bundle_by_local_name(result, "run-provider-phase-demo")
    provider_bundle = next(
        item
        for item in _workflow_generated_path_allocations(bundle)
        if _allocation_field(item, "semantic_role") == "provider_result_bundle"
    )
    materialized_views = [
        item
        for item in _workflow_generated_path_allocations(bundle)
        if _allocation_field(item, "semantic_role") == "materialized_value_view"
    ]

    assert _allocation_field(provider_bundle, "privacy") == "private_generated"
    assert _allocation_field(provider_bundle, "resume_scope") == "step_visit"
    assert _allocation_field(provider_bundle, "concrete_path_template").startswith(
        "${inputs.phase-ctx__state-root}/phases/implementation/"
    )
    assert materialized_views
    assert all(
        _allocation_field(item, "path_safety_policy") == "workspace_relative"
        for item in materialized_views
    )


def test_review_revise_loop_generated_review_workflow_normalizes_union_outputs(tmp_path: Path) -> None:
    result = _compile(
        VALID_REVIEW_LOOP_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    parent_lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::review-revise-loop-demo")
    )
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::run-review.v1")
    )
    review_step = next(
        step
        for step in lowered.authored_mapping["steps"]
        if step.get("provider") == "fake-review"
    )
    normalization_step = next(
        step
        for step in parent_lowered.authored_mapping["steps"]
        if step.get("match", {}).get("ref", "").endswith(".artifacts.result__variant")
    )

    assert set(review_step["variant_output"]["variants"]) == {"APPROVE", "BLOCKED", "REVISE"}
    assert set(normalization_step["match"]["cases"]) == {"APPROVED", "BLOCKED", "EXHAUSTED"}
    assert normalization_step["match"]["ref"].endswith("__loop.artifacts.result__variant")


def test_review_revise_loop_repeat_body_parent_scoped_materialize_refs_target_loop_state(tmp_path: Path) -> None:
    result = _compile(
        VALID_REVIEW_LOOP_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::review-revise-loop-demo")
    )
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)

    state_call_refs: list[str] = []
    for step in _iter_nested_steps(repeat_step["repeat_until"]["steps"]):
        if not (isinstance(step.get("call"), str) and step["call"].endswith("::run-review.v1")):
            continue
        for binding in step.get("with", {}).values():
            ref = binding.get("ref") if isinstance(binding, dict) else None
            if isinstance(ref, str) and "__body__state.artifacts.state__" in ref:
                state_call_refs.append(ref)

    assert state_call_refs


def test_nested_implementation_phase_uses_ordinary_imported_review_revise_loop(
    tmp_path: Path,
) -> None:
    result = _compile_module_fixture(
        VALID_NESTED_IMPLEMENTATION_PHASE_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    lowered = next(
        workflow.authored_mapping
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == "nested/implementation-phase::implementation-phase"
    )
    assert any("match" in step for step in lowered["steps"])
    assert any(
        isinstance(step.get("call"), str) and step["call"].startswith("%")
        for step in _iter_nested_steps(lowered["steps"])
    )

    assert any("repeat_until" in step for step in _iter_nested_steps(lowered["steps"]))
    assert any(
        step.get("provider") == "fake-review"
        for workflow in result.entry_result.lowered_workflows
        for step in _iter_nested_steps(workflow.authored_mapping["steps"])
    )


def test_nested_same_file_call_with_local_record_compiles_under_branch(tmp_path: Path) -> None:
    result = _compile(
        VALID_NESTED_SAME_FILE_CALL_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    assert {
        workflow.typed_workflow.definition.name
        for workflow in result.lowered_workflows
    } == {"summarize-completed", "echo-helper", "entry"}


def test_nested_imported_procedure_with_provider_command_workflow_effects_compiles_under_branch(
    tmp_path: Path,
) -> None:
    result = _compile_module_fixture(
        VALID_NESTED_IMPORTED_BRANCH_EFFECTS_FIXTURE,
        tmp_path=tmp_path,
        extra_source_roots=(FIXTURES / "modules" / "valid" / "workflow_refs",),
        validate_shared=True,
    )

    nested_steps = list(
        _iter_nested_steps(
            [
                step
                for compiled in result.compiled_results_by_name.values()
                for workflow in compiled.lowered_workflows
                for step in workflow.authored_mapping.get("steps", ())
            ]
        )
    )

    assert any(step.get("provider") == "fake-execute" for step in nested_steps)
    assert any(
        isinstance(step.get("call"), str) and step["call"].endswith("echo-helper")
        for step in nested_steps
    )
    assert any(step.get("command", [])[:2] == ["python", "scripts/run_checks.py"] for step in nested_steps)


def test_branch_scoped_generated_step_ids_are_unique_across_repeated_branches_and_loop_iterations(
    tmp_path: Path,
) -> None:
    result = _compile(
        VALID_NESTED_BRANCH_SCOPE_COLLISION_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    lowered = next(workflow.authored_mapping for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "entry")
    step_ids = [step.get("id") for step in _iter_nested_steps(lowered["steps"]) if isinstance(step.get("id"), str)]
    assert len(step_ids) == len(set(step_ids))


def test_branch_scoped_generated_step_resume_identity_is_stable(tmp_path: Path) -> None:
    first_result = _compile(
        VALID_NESTED_BRANCH_SCOPE_COLLISION_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )
    second_result = _compile(
        VALID_NESTED_BRANCH_SCOPE_COLLISION_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    first_checkpoint_ids = tuple(first_result.validated_bundles["entry"].runtime_plan.resume_checkpoints)
    second_checkpoint_ids = tuple(second_result.validated_bundles["entry"].runtime_plan.resume_checkpoints)
    assert first_checkpoint_ids
    assert first_checkpoint_ids == second_checkpoint_ids


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


def test_lowering_resume_or_start_registers_generated_loader_binding(tmp_path: Path) -> None:
    result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path)

    bindings = result.command_boundary_environment.bindings_by_name

    assert isinstance(bindings["validate_reusable_phase_state"], CertifiedAdapterBinding)
    assert isinstance(bindings["write_reusable_phase_state_v1"], CertifiedAdapterBinding)
    assert isinstance(bindings["load_canonical_phase_result__ChecksResult"], CertifiedAdapterBinding)
    assert isinstance(bindings["load_canonical_phase_result__PlanGateResult"], CertifiedAdapterBinding)
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
    assert bindings["load_canonical_phase_result__PlanGateResult"].stable_command == (
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
    )


def test_resume_or_start_lowers_contract_fingerprint_and_loader_metadata(
    tmp_path: Path,
) -> None:
    result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path)
    authored_by_name = {
        workflow.typed_workflow.definition.name.rsplit("::", 1)[-1]: workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.rsplit("::", 1)[-1]
        in {"resume-record-phase", "resume-plan-gate"}
    }

    record_validator_payload = json.loads(authored_by_name["resume-record-phase"]["steps"][0]["command"][3])
    assert record_validator_payload["target_dsl_version"] == "2.14"
    assert record_validator_payload["return_type_name"] == "ChecksResult"
    assert record_validator_payload["structured_contract_kind"] == "record"
    assert record_validator_payload["expected_contract_fingerprint"].startswith("2.14:ChecksResult:record:")
    assert record_validator_payload["summary_schema"] == "ReusablePhaseState.v1"
    assert record_validator_payload["summary_version"] == "v1"
    assert record_validator_payload["sidecar_suffix"] == ".reusable_state.json"
    assert record_validator_payload["canonical_bundle_digest_field"] == "canonical_bundle_sha256"
    assert "inputs__report_path" in record_validator_payload["public_input_hash_basis"]
    assert "phase-ctx__run__run-id" not in record_validator_payload["public_input_hash_basis"]
    assert "phase-ctx__run__state-root" not in record_validator_payload["public_input_hash_basis"]
    assert "phase-ctx__run__artifact-root" not in record_validator_payload["public_input_hash_basis"]
    assert "phase-ctx__state-root" not in record_validator_payload["public_input_hash_basis"]
    assert "phase-ctx__artifact-root" not in record_validator_payload["public_input_hash_basis"]
    assert record_validator_payload["producer_fingerprint_basis"]["return_type_name"] == "ChecksResult"
    assert record_validator_payload["producer_fingerprint_basis"]["source_file_digests"]
    assert record_validator_payload["producer_fingerprint_basis"]["compile_inputs_fingerprint"]
    assert record_validator_payload["artifact_requirements"] == {
        "ChecksResult": [
            {
                "field_path": ["checks_report"],
                "under": "artifacts/work",
            }
        ]
    }
    record_loader_payload = json.loads(
        next(
            step["command"][3]
            for step in authored_by_name["resume-record-phase"]["steps"][1]["match"]["cases"]["REUSABLE"]["steps"]
            if step.get("command", [])[:3]
            == [
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
            ]
        )
    )
    assert record_loader_payload["target_dsl_version"] == "2.14"
    assert record_loader_payload["return_type_name"] == "ChecksResult"
    assert record_loader_payload["expected_contract_fingerprint"].startswith("2.14:ChecksResult:record:")
    record_writer_payload = json.loads(
        next(
            step["command"][3]
            for step in authored_by_name["resume-record-phase"]["steps"][1]["match"]["cases"]["START"]["steps"]
            if step.get("command", [])[:3]
            == [
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.write_reusable_phase_state_v1",
            ]
        )
    )
    assert record_writer_payload["summary_schema"] == "ReusablePhaseState.v1"
    assert record_writer_payload["summary_version"] == "v1"
    assert record_writer_payload["bundle_path"].startswith("${inputs.__write_root__")

    union_validator_payload = json.loads(authored_by_name["resume-plan-gate"]["steps"][0]["command"][3])
    assert union_validator_payload["target_dsl_version"] == "2.14"
    assert union_validator_payload["return_type_name"] == "PlanGateResult"
    assert union_validator_payload["structured_contract_kind"] == "union"
    assert union_validator_payload["expected_contract_fingerprint"].startswith("2.14:PlanGateResult:union:")
    assert union_validator_payload["summary_schema"] == "ReusablePhaseState.v1"
    assert union_validator_payload["producer_fingerprint_basis"]["return_type_name"] == "PlanGateResult"
    assert union_validator_payload["producer_fingerprint_basis"]["compile_inputs_fingerprint"]
    assert union_validator_payload["artifact_requirements"] == {
        "APPROVED": [
            {
                "field_path": ["shared_report_path"],
                "under": "artifacts/work",
            },
            {
                "field_path": ["execution_report_path"],
                "under": "artifacts/work",
            }
        ],
    }
    union_loader_payload = json.loads(
        next(
            step["command"][3]
            for step in authored_by_name["resume-plan-gate"]["steps"][1]["match"]["cases"]["REUSABLE"]["steps"]
            if step.get("command", [])[:3]
            == [
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
            ]
        )
    )
    assert union_loader_payload["target_dsl_version"] == "2.14"
    assert union_loader_payload["return_type_name"] == "PlanGateResult"
    assert union_loader_payload["expected_contract_fingerprint"].startswith("2.14:PlanGateResult:union:")
    union_writer_payload = json.loads(
        next(
            step["command"][3]
            for step in authored_by_name["resume-plan-gate"]["steps"][1]["match"]["cases"]["START"]["steps"]
            if step.get("command", [])[:3]
            == [
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.write_reusable_phase_state_v1",
            ]
        )
    )
    assert union_writer_payload["summary_schema"] == "ReusablePhaseState.v1"
    assert union_writer_payload["summary_version"] == "v1"
    assert union_writer_payload["phase_id"] == "plan-gate"


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


def test_resume_or_start_in_inline_defproc_registers_generated_adapters(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "resume_or_start_defproc.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defpath PhaseStateBundle",
                "    :kind relpath",
                '    :under "state"',
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
                "  (defrecord ResumeInputs",
                "    (resume_from PhaseStateBundle)",
                "    (report_path WorkReport))",
                "  (defrecord ChecksResult",
                "    (checks_report WorkReport))",
                "  (defproc resume-checks",
                "    ((phase-ctx PhaseCtx)",
                "     (inputs ResumeInputs))",
                "    -> ChecksResult",
                "    :effects ((uses-command run_checks) (uses-command validate_reusable_phase_state))",
                "    :lowering inline",
                "    (with-phase phase-ctx checks",
                "      (resume-or-start checks",
                "        :ctx phase-ctx",
                "        :resume-from inputs.resume_from",
                "        :start",
                "          (command-result run_checks",
                '            :argv ("python" "scripts/run_checks.py" inputs.report_path)',
                "            :returns ChecksResult)",
                "        :returns ChecksResult)))",
                "  (defworkflow orchestrate",
                "    ((phase-ctx PhaseCtx)",
                "     (inputs ResumeInputs))",
                "    -> ChecksResult",
                "    (resume-checks phase-ctx inputs)))",
            ]
        ),
    )

    result = compile_stage3_module(
        path,
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    bindings = result.command_boundary_environment.bindings_by_name
    assert isinstance(bindings["validate_reusable_phase_state"], CertifiedAdapterBinding)
    assert isinstance(bindings["load_canonical_phase_result__ChecksResult"], CertifiedAdapterBinding)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if _local_workflow_name_matches(workflow.typed_workflow.definition.name, "orchestrate")
    )
    assert authored["steps"][0]["command"][:3] == [
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state",
    ]


def test_lowering_resume_or_start_emits_validator_and_branch_normalization(tmp_path: Path) -> None:
    result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path)

    by_name = {
        workflow.typed_workflow.definition.name.rsplit("::", 1)[-1]: workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.rsplit("::", 1)[-1]
        in {"resume-record-phase", "resume-plan-gate"}
    }

    record_workflow = by_name["resume-record-phase"]
    assert len(record_workflow["steps"]) == 2
    validator_step = record_workflow["steps"][0]
    assert validator_step["command"][:3] == [
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state",
    ]
    validator_payload = json.loads(validator_step["command"][3])
    assert validator_payload["structured_contract_kind"] == "record"
    assert validator_payload["expected_contract_fingerprint"].startswith("2.14:ChecksResult:record:")
    assert validator_payload["artifact_requirements"] == {
        "ChecksResult": [
            {
                "field_path": ["checks_report"],
                "under": "artifacts/work",
            }
        ]
    }
    assert validator_step["variant_output"]["variants"]["REUSABLE"]["fields"] == [
        {
            "name": "source_bundle_path",
            "json_pointer": "/source_bundle_path",
            "type": "relpath",
        },
        {
            "name": "source_bundle_sha256",
            "json_pointer": "/source_bundle_sha256",
            "type": "string",
        },
    ]
    branch_step = record_workflow["steps"][1]
    assert set(branch_step["match"]["cases"]) == {
        "REUSABLE",
        "START",
        "STALE",
        "MISSING_ARTIFACT",
        "FAILED_PRIOR_STATE",
    }
    reuse_steps = branch_step["match"]["cases"]["REUSABLE"]["steps"]
    start_steps = branch_step["match"]["cases"]["START"]["steps"]
    assert any(
        step.get("command", [])[:3]
        == [
            "python",
            "-m",
            "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
        ]
        for step in reuse_steps
    )
    assert any(step.get("command", [])[:2] == ["python", "scripts/run_checks.py"] for step in start_steps)
    assert any(
        step.get("command", [])[:3]
        == [
            "python",
            "-m",
            "orchestrator.workflow_lisp.adapters.write_reusable_phase_state_v1",
        ]
        for step in start_steps
    )

    plan_gate_workflow = by_name["resume-plan-gate"]
    assert len(plan_gate_workflow["steps"]) == 3
    validator_step = plan_gate_workflow["steps"][0]
    assert validator_step["command"][:3] == [
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state",
    ]
    validator_payload = json.loads(validator_step["command"][3])
    assert validator_payload["structured_contract_kind"] == "union"
    assert validator_payload["expected_contract_fingerprint"].startswith("2.14:PlanGateResult:union:")
    branch_step = next(
        step
        for step in plan_gate_workflow["steps"]
        if step.get("match", {}).get("ref")
        == f"root.steps.{validator_step['name']}.artifacts.variant"
    )
    assert set(branch_step["match"]["cases"]) == {
        "REUSABLE",
        "START",
        "STALE",
        "MISSING_ARTIFACT",
        "FAILED_PRIOR_STATE",
    }
    reuse_steps = branch_step["match"]["cases"]["REUSABLE"]["steps"]
    start_steps = branch_step["match"]["cases"]["START"]["steps"]
    assert any(
        step.get("command", [])[:3]
        == [
            "python",
            "-m",
            "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
        ]
        for step in reuse_steps
    )
    assert any(
        step.get("call") == "plan-run" or str(step.get("call", "")).endswith("::plan-run")
        for step in _iter_nested_steps(start_steps)
    )
    assert any(
        step.get("command", [])[:3]
        == [
            "python",
            "-m",
            "orchestrator.workflow_lisp.adapters.write_reusable_phase_state_v1",
        ]
        for step in _iter_nested_steps(start_steps)
    )


def test_shared_validation_accepts_resume_or_start(tmp_path: Path) -> None:
    result = _compile(
        VALID_RESUME_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    assert {
        workflow.typed_workflow.definition.name.rsplit("::", 1)[-1]
        for workflow in result.lowered_workflows
    } >= {"resume-record-phase", "resume-plan-gate"}


def test_phase_stdlib_contract_inventory_matches_lowering_families(tmp_path: Path) -> None:
    run_provider_result = _compile(VALID_RUN_PROVIDER_FIXTURE, tmp_path=tmp_path)
    review_loop_result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)
    resume_result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path)

    run_provider_by_name = {
        workflow.typed_workflow.definition.name.rsplit("::", 1)[-1]: workflow
        for workflow in run_provider_result.lowered_workflows
    }
    review_by_name = {
        workflow.typed_workflow.definition.name.rsplit("::", 1)[-1]: workflow
        for workflow in review_loop_result.lowered_workflows
    }
    resume_by_name = {
        workflow.typed_workflow.definition.name.rsplit("::", 1)[-1]: workflow
        for workflow in resume_result.lowered_workflows
    }

    run_provider_contract = STDLIB_LOWERING_CONTRACTS_BY_FORM["run-provider-phase"]
    assert run_provider_contract.family == "structured_result_producer"
    assert run_provider_contract.backend_kinds == ("provider",)
    assert run_provider_contract.required_statement_families == (
        "materialize_artifacts",
        "provider_step",
    )
    assert run_provider_contract.alternative_statement_family_sets == (("output_bundle", "variant_output"),)
    assert run_provider_contract.delegated_statement_family_policy == "none"
    assert run_provider_contract.state_root_policies == ("active_phase_bundle",)
    assert run_provider_contract.authority_model == "validated_structured_result_bundle"
    assert run_provider_contract.proof_model == "contract_validated_bundle"
    assert run_provider_contract.source_map_expectations == (
        "high_level_form_origin",
        "generated_step_span",
        "generated_hidden_path_span",
    )
    run_provider_lowered = run_provider_by_name["run-provider-phase-demo"]
    run_provider_authored = run_provider_lowered.authored_mapping
    run_provider_provider_step = next(
        step for step in run_provider_authored["steps"] if step.get("provider") == "fake-execute"
    )
    observed = _assert_contract_matches_observed_families(
        run_provider_contract,
        steps=run_provider_authored["steps"],
    )
    assert observed.intersection({"output_bundle", "variant_output"}) == {"variant_output"}
    _assert_contract_source_map_expectations(
        run_provider_contract,
        run_provider_lowered,
        generated_paths=(run_provider_provider_step["variant_output"]["path"],),
    )

    produce_one_of_contract = STDLIB_LOWERING_CONTRACTS_BY_FORM["produce-one-of"]
    assert produce_one_of_contract.family == "structured_result_producer"
    assert produce_one_of_contract.backend_kinds == ("provider",)
    assert produce_one_of_contract.required_statement_families == (
        "materialize_artifacts",
        "pre_snapshot",
        "provider_step",
        "select_variant_output",
        "match",
    )
    assert produce_one_of_contract.alternative_statement_family_sets == ()
    assert produce_one_of_contract.delegated_statement_family_policy == "none"
    assert produce_one_of_contract.state_root_policies == ("active_phase_bundle_plus_snapshot",)
    assert produce_one_of_contract.authority_model == "validated_selected_variant_bundle"
    assert produce_one_of_contract.proof_model == "snapshot_diff_variant_selection"
    assert produce_one_of_contract.source_map_expectations == (
        "high_level_form_origin",
        "generated_step_span",
        "generated_hidden_path_span",
    )
    produce_one_of_lowered = run_provider_by_name["produce-one-of-demo"]
    observed = _assert_contract_matches_observed_families(
        produce_one_of_contract,
        steps=produce_one_of_lowered.authored_mapping["steps"],
    )
    assert "variant_output" not in observed
    _assert_contract_source_map_expectations(
        produce_one_of_contract,
        produce_one_of_lowered,
        generated_paths=tuple(produce_one_of_lowered.origin_map.generated_path_spans),
    )

    review_loop_contract = STDLIB_LOWERING_CONTRACTS_BY_FORM["review-revise-loop"]
    assert review_loop_contract.family == "review_reuse_control"
    assert review_loop_contract.backend_kinds == ("provider", "certified_adapter")
    assert review_loop_contract.required_statement_families == (
        "repeat_until",
        "workflow_call",
        "command_step",
        "output_bundle",
        "match",
        "materialize_artifacts",
    )
    assert review_loop_contract.alternative_statement_family_sets == ()
    assert review_loop_contract.delegated_statement_family_policy == "none"
    assert review_loop_contract.state_root_policies == ("repeat_until_generated_bundle",)
    assert review_loop_contract.authority_model == "validated_repeat_until_route_bundle"
    assert review_loop_contract.proof_model == "typed_review_decision_routing"
    assert review_loop_contract.source_map_expectations == (
        "high_level_form_origin",
        "generated_step_span",
        "generated_hidden_input_span",
        "generated_hidden_path_span",
        "adapter_command_step_origin",
    )
    assert review_loop_contract.adapter_binding_names == ("validate_review_findings_v1",)
    review_loop_lowered = next(
        workflow
        for workflow in review_by_name.values()
        if workflow.typed_workflow.definition.name.endswith("::review-revise-loop-demo")
    )
    review_repeat_step = next(
        step for step in review_loop_lowered.authored_mapping["steps"] if "repeat_until" in step
    )
    review_workflow = next(
        workflow
        for workflow in review_by_name.values()
        if workflow.typed_workflow.definition.name.endswith("::run-review.v1")
    )
    review_step = next(
        step
        for step in review_workflow.authored_mapping["steps"]
        if step.get("provider") == "fake-review"
    )
    review_path = review_step["variant_output"]["path"]
    review_loop_adapter_step = next(
        step
        for step in _iter_nested_steps(review_repeat_step["repeat_until"]["steps"])
        if isinstance(step.get("command"), list)
        and "orchestrator.workflow_lisp.adapters.validate_review_findings_v1" in step["command"]
    )
    _assert_contract_matches_observed_families(
        review_loop_contract,
        steps=review_loop_lowered.authored_mapping["steps"],
    )
    _assert_contract_source_map_expectations(
        review_loop_contract,
        review_loop_lowered,
        generated_paths=(review_loop_adapter_step["output_bundle"]["path"],),
    )
    assert review_path in review_workflow.origin_map.generated_path_spans

    resume_contract = STDLIB_LOWERING_CONTRACTS_BY_FORM["resume-or-start"]
    assert resume_contract.family == "review_reuse_control"
    assert resume_contract.backend_kinds == ("certified_adapter",)
    assert resume_contract.required_statement_families == (
        "command_step",
        "variant_output",
        "match",
    )
    assert resume_contract.alternative_statement_family_sets == ()
    assert (
        resume_contract.delegated_statement_family_policy
        == "resume_start_branch_delegates_to_wrapped_expression"
    )
    assert resume_contract.state_root_policies == ("managed_reusable_boundary_inputs",)
    assert resume_contract.authority_model == "validated_reusable_state_boundary"
    assert resume_contract.proof_model == "reusable_state_validation_then_branch_normalization"
    assert resume_contract.source_map_expectations == (
        "high_level_form_origin",
        "generated_step_span",
        "generated_hidden_input_span",
        "generated_hidden_path_span",
        "adapter_command_step_origin",
    )
    assert resume_contract.adapter_binding_names == (
        "validate_reusable_phase_state",
        "write_reusable_phase_state_v1",
        "load_canonical_phase_result__<ReturnType>",
    )

    resume_record_lowered = resume_by_name["resume-record-phase"]
    resume_record_authored = resume_record_lowered.authored_mapping
    resume_record_validator = resume_record_authored["steps"][0]
    resume_record_path = resume_record_validator["variant_output"]["path"]
    resume_record_hidden_input = resume_record_path.removeprefix("${inputs.").removesuffix("}")
    _assert_contract_matches_observed_families(
        resume_contract,
        steps=resume_record_authored["steps"],
    )
    _assert_contract_source_map_expectations(
        resume_contract,
        resume_record_lowered,
        hidden_inputs=(resume_record_hidden_input,),
        generated_paths=(resume_record_path,),
    )
    record_start_steps = resume_record_authored["steps"][1]["match"]["cases"]["START"]["steps"]
    assert "command_step" in _observed_statement_families(record_start_steps)

    resume_plan_lowered = resume_by_name["resume-plan-gate"]
    resume_plan_authored = resume_plan_lowered.authored_mapping
    resume_plan_validator = resume_plan_authored["steps"][0]
    resume_plan_path = resume_plan_validator["variant_output"]["path"]
    resume_plan_hidden_input = resume_plan_path.removeprefix("${inputs.").removesuffix("}")
    _assert_contract_matches_observed_families(
        resume_contract,
        steps=resume_plan_authored["steps"],
    )
    _assert_contract_source_map_expectations(
        resume_contract,
        resume_plan_lowered,
        hidden_inputs=(resume_plan_hidden_input,),
        generated_paths=(resume_plan_path,),
    )
    plan_branch_step = next(
        step
        for step in resume_plan_authored["steps"]
        if step.get("match", {}).get("ref")
        == f"root.steps.{resume_plan_validator['name']}.artifacts.variant"
    )
    plan_start_steps = plan_branch_step["match"]["cases"]["START"]["steps"]
    assert "workflow_call" in _observed_statement_families(plan_start_steps)


def test_resume_or_start_workflow_call_uses_shared_managed_write_root_bundle_path(tmp_path: Path) -> None:
    result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path, validate_shared=True)
    lowered_workflow = next(
        workflow
        for workflow in result.lowered_workflows
        if _local_workflow_name_matches(workflow.typed_workflow.definition.name, "resume-plan-gate")
    )
    authored = lowered_workflow.authored_mapping
    lowered_plan_run = next(
        workflow
        for workflow in result.lowered_workflows
        if _local_workflow_name_matches(workflow.typed_workflow.definition.name, "plan-run")
    )
    validator_step = authored["steps"][0]
    branch_step = next(
        step
        for step in authored["steps"]
        if step.get("match", {}).get("ref")
        == f"root.steps.{validator_step['name']}.artifacts.variant"
    )
    start_steps = branch_step["match"]["cases"]["START"]["steps"]
    call_step = next(
        step
        for step in _iter_nested_steps(start_steps)
        if step.get("call") == "plan-run" or str(step.get("call", "")).endswith("::plan-run")
    )
    managed_inputs = _managed_write_root_requirements_for_callable(
        lowered_callee=lowered_plan_run,
        imported_bundle=None,
        span=lowered_plan_run.typed_workflow.definition.body.span,
        form_path=lowered_plan_run.typed_workflow.definition.body.form_path,
    )
    expected_bindings = _managed_write_root_bindings(
        caller_workflow_name=lowered_workflow.typed_workflow.definition.name,
        call_step_name=call_step["name"],
        callee_name=lowered_plan_run.typed_workflow.definition.name,
        managed_inputs=managed_inputs,
    )

    assert len(managed_inputs) == 1
    managed_input = managed_inputs[0]
    assert "plan_run" in managed_input
    assert managed_input.endswith("__resolve_plan_gate__result_bundle")
    assert call_step["with"][managed_input] == expected_bindings[managed_input]


def test_resume_or_start_imported_workflow_call_uses_shared_managed_write_root_bundle_path(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "resume_imports"
    _write_module(
        source_root / "resume" / "types.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule resume/types)",
                "  (export BlockerClass DesignDocPath PlanDocPath WorkReport PhaseStateBundle RunCtx PhaseCtx ResumeInputs PlanGateResult PlanGateSurfaceResult)",
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware",
                "    roadmap_conflict",
                "    external_dependency_outside_authority",
                "    user_decision_required",
                "    unrecoverable_after_fix_attempt)",
                "  (defpath DesignDocPath",
                '    :kind relpath',
                '    :under "docs/design"',
                "    :must-exist true)",
                "  (defpath PlanDocPath",
                '    :kind relpath',
                '    :under "docs/plans"',
                "    :must-exist true)",
                "  (defpath WorkReport",
                '    :kind relpath',
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defpath PhaseStateBundle",
                '    :kind relpath',
                '    :under "state"',
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
                "  (defrecord ResumeInputs",
                "    (resume_from PhaseStateBundle)",
                "    (design DesignDocPath)",
                "    (plan PlanDocPath)",
                "    (report_path WorkReport))",
                "  (defunion PlanGateResult",
                "    (APPROVED",
                "      (shared_report_path WorkReport)",
                "      (execution_report_path WorkReport))",
                "    (BLOCKED",
                "      (shared_report_path WorkReport)",
                "      (progress_report_path WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defrecord PlanGateSurfaceResult",
                "    (report_path WorkReport))",
                ")",
            ]
        )
        + "\n",
    )
    _write_module(
        source_root / "resume" / "helper.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule resume/helper)",
                "  (import resume/types :only (BlockerClass DesignDocPath PlanDocPath WorkReport PhaseStateBundle RunCtx PhaseCtx ResumeInputs PlanGateResult))",
                "  (export plan-run)",
                "  (defworkflow plan-run",
                "    ((phase-ctx PhaseCtx)",
                "     (inputs ResumeInputs))",
                "    -> PlanGateResult",
                "    (command-result resolve_plan_gate",
                '      :argv ("python" "scripts/resolve_plan_gate.py" inputs.report_path)',
                "      :returns PlanGateResult))",
                ")",
            ]
        )
        + "\n",
    )
    caller_source = _write_module(
        source_root / "resume" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule resume/entry)",
                "  (import resume/types :only (BlockerClass DesignDocPath PlanDocPath WorkReport PhaseStateBundle RunCtx PhaseCtx ResumeInputs PlanGateResult PlanGateSurfaceResult))",
                "  (import resume/helper :only (plan-run))",
                "  (export resume-plan-gate)",
                "  (defworkflow resume-plan-gate",
                "    ((phase-ctx PhaseCtx)",
                "     (inputs ResumeInputs))",
                "    -> PlanGateSurfaceResult",
                "    (with-phase phase-ctx plan-gate",
                "      (let* ((result",
                "               (resume-or-start plan-gate",
                "                 :ctx phase-ctx",
                "                 :resume-from inputs.resume_from",
                "                 :valid-when (APPROVED)",
                "                 :start",
                "                   (call plan-run",
                "                     :phase-ctx phase-ctx",
                "                     :inputs inputs)",
                "                 :returns PlanGateResult)))",
                "        (match result",
                "          ((APPROVED approved)",
                "           (record PlanGateSurfaceResult",
                "             :report_path approved.execution_report_path))",
                "          ((BLOCKED blocked)",
                "           (record PlanGateSurfaceResult",
                "             :report_path blocked.progress_report_path))))))",
                ")",
            ]
        )
        + "\n",
    )
    result = compile_stage3_entrypoint(
        caller_source,
        source_roots=(source_root,),
        validate_shared=True,
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
        workspace_root=tmp_path,
    )
    lowered_workflow = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == "resume/entry::resume-plan-gate"
    )
    authored = lowered_workflow.authored_mapping
    validator_step = authored["steps"][0]
    branch_step = next(
        step
        for step in authored["steps"]
        if step.get("match", {}).get("ref")
        == f"root.steps.{validator_step['name']}.artifacts.variant"
    )
    start_steps = branch_step["match"]["cases"]["START"]["steps"]
    call_step = next(
        step
        for step in _iter_nested_steps(start_steps)
        if step.get("call") == "resume/helper::plan-run"
    )
    managed_input_name = "__write_root__resume_helper_plan_run__resolve_plan_gate__result_bundle"

    assert "resume/helper::plan-run" in result.validated_bundles_by_name
    assert "resume/entry::resume-plan-gate" in result.validated_bundles_by_name
    assert "resume/helper::plan-run" in result.entry_result.workflow_catalog.signatures_by_name
    assert call_step["call"] == "resume/helper::plan-run"
    assert call_step["with"][managed_input_name] == (
        ".orchestrate/workflow_lisp/calls/resume/entry::resume-plan-gate/"
        "resume/entry::resume-plan-gate__result__start__call_resume/helper::plan-run/"
        "resume/helper::plan-run/__write_root__resume_helper_plan_run__resolve_plan_gate__result_bundle.json"
    )


def test_resume_or_start_supports_union_start_workflow_call(tmp_path: Path) -> None:
    result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path, validate_shared=True)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if _local_workflow_name_matches(workflow.typed_workflow.definition.name, "resume-plan-gate")
    )
    validator_step = authored["steps"][0]
    branch_step = next(
        step
        for step in authored["steps"]
        if step.get("match", {}).get("ref")
        == f"root.steps.{validator_step['name']}.artifacts.variant"
    )
    start_steps = branch_step["match"]["cases"]["START"]["steps"]

    assert any(
        step.get("call") == "plan-run" or str(step.get("call", "")).endswith("::plan-run")
        for step in _iter_nested_steps(start_steps)
    )


def test_resume_or_start_supports_reusable_wrapper_union_start_workflow_call(tmp_path: Path) -> None:
    result = _compile(VALID_RESUME_WRAPPER_FIXTURE, tmp_path=tmp_path, validate_shared=True)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if _local_workflow_name_matches(workflow.typed_workflow.definition.name, "resume-plan-gate-wrapper")
    )
    validator_step = authored["steps"][0]
    branch_step = next(
        step
        for step in authored["steps"]
        if step.get("match", {}).get("ref")
        == f"root.steps.{validator_step['name']}.artifacts.variant"
    )
    start_steps = branch_step["match"]["cases"]["START"]["steps"]

    assert any(
        step.get("call") == "wrap-plan-gate" or str(step.get("call", "")).endswith("::wrap-plan-gate")
        for step in _iter_nested_steps(start_steps)
    )
    assert "load_canonical_phase_result__PlanGateWrapperResult" in result.command_boundary_environment.bindings_by_name


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
