from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest

from orchestrator.exec.output_capture import CaptureMode, CaptureResult
from orchestrator.exec.step_executor import ExecutionResult
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.calls import CallExecutor
from orchestrator.workflow.executor_runtime import CallRuntime
from orchestrator.workflow.executable_ir import validate_executable_workflow
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    workflow_context,
    workflow_boundary_projection,
    workflow_public_input_contracts,
    workflow_runtime_input_contracts,
    workflow_runtime_context_inputs,
)
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow.view_renderer import render_view
from orchestrator.workflow_lisp.command_boundaries import (
    CertifiedAdapterInputField,
    PROMOTED_CALL_REQUIRED_METADATA_FIELDS,
    TransitionBindingMetadata,
)
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    _display_workflow_name,
    _parse_command_boundaries_manifest,
    build_frontend_bundle,
)
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from orchestrator.workflow_lisp.family_profiles import load_workflow_family_profile_catalog
from orchestrator.workflow_lisp.source_map import build_source_map_document
from orchestrator.workflow_lisp.workflows import CertifiedAdapterBinding, ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "cli"
WORKFLOW_LISP_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
CHARACTERIZATION_FIXTURES = WORKFLOW_LISP_FIXTURES / "characterization" / "sources"
# This checked-in candidate mirrors the shipping library modules for
# supplemental imported-child prerequisite coverage.
DESIGN_DELTA_WORK_ITEM_CANDIDATE_ROOT = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_work_item_runtime"
)
DESIGN_DELTA_PARENT_DRAIN_COMMANDS = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.commands.json"
)
DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.family_profile.json"
)
NESTED_IMPLEMENTATION_PHASE_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_nested_implementation_phase.orc"
)
PARENT_CALL_IMPLEMENTATION_PHASE_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_parent_calls_implementation_phase.orc"
)
PARENT_CALL_WORK_ITEM_CANDIDATE_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_parent_calls_work_item.orc"
)
ITEM_CTX_CHILD_PHASE_REUSE_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_item_ctx_child_phase_reuse.orc"
)
ITEM_CTX_CHILD_PHASE_REUSE_PROC_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_item_ctx_child_phase_reuse_proc.orc"
)
ITEM_CTX_CHILD_PHASE_REUSE_PROC_REF_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_item_ctx_child_phase_reuse_proc_ref.orc"
)
LOOP_PROMOTED_HOOK_PHASE_CTX_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_loop_promoted_hook_phase_ctx.orc"
)
DERIVED_PHASE_CONTEXT_PROC_WITHOUT_CONTEXT_SOURCE_INVALID_FIXTURE = (
    WORKFLOW_LISP_FIXTURES
    / "invalid"
    / "derived_phase_context_proc_without_context_source_invalid.orc"
)
DERIVED_PHASE_CONTEXT_BINDING_INVALID_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "invalid" / "derived_phase_context_binding_invalid.orc"
)
DERIVED_PHASE_CONTEXT_AMBIGUOUS_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "invalid" / "derived_phase_context_ambiguous.orc"
)
DERIVED_PHASE_CONTEXT_NON_ITEM_CTX_ROOT_INVALID_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "invalid" / "derived_phase_context_non_item_ctx_root_invalid.orc"
)
DESIGN_DELTA_RUNTIME_TRANSITION_FIXTURE = (
    REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "runtime_transition_fixture.orc"
)
DESIGN_DELTA_RUNTIME_VIEW_FIXTURE = (
    REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "runtime_view_fixture.orc"
)
STDLIB_PARENT_DELEGATION_AUDIT_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "drain_stdlib_backlog_drain_stdlib.orc"
)
DESIGN_DELTA_WORK_ITEM_LIBRARY_ROOT = REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta"
NESTED_SAME_FILE_CALL_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_nested_same_file_call_local_record.orc"
)
NESTED_IMPORTED_BRANCH_EFFECTS_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_nested_imported_branch_effects.orc"
)
WORKFLOW_LISP_IMPORT_PATTERN = re.compile(r"\(import\s+([^\s)]+)")
# Representative design-gap identity used by the recorded-progress smokes.
# The identity value is arbitrary; the smokes prove that the id recorded via
# the runtime-native drain-run-state resource drives later selector decisions.
DESIGN_GAP_SMOKE_IDENTITY = "design-gap-work-item"


def _write_module(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _write_entrypoint_fixture_to_tmp(path: Path, *, tmp_path: Path) -> Path:
    source = path.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None, f"fixture is missing defmodule: {path}"
    resolved_module_name = module_match.group(1)
    module_path = (tmp_path / Path(*resolved_module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    return module_path


def _without_top_level_workflows(source: str, workflow_names: tuple[str, ...]) -> str:
    result = source
    for workflow_name in workflow_names:
        marker = f"  (defworkflow {workflow_name}"
        start = result.find(marker)
        if start < 0:
            continue
        depth = 0
        end = start
        for index in range(start, len(result)):
            char = result[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        result = result[:start] + result[end:].lstrip("\n")
    return result


def _write_item_ctx_child_phase_reuse_core_fixture_to_tmp(tmp_path: Path) -> Path:
    source = ITEM_CTX_CHILD_PHASE_REUSE_FIXTURE.read_text(encoding="utf-8")
    source = source.replace(
        "(export run-entry run-entry-branching-terminal-reprojection)",
        "(export run-entry)",
        1,
    )
    source = _without_top_level_workflows(
        source,
        (
            "run-entry-branching-terminal-reprojection",
            "bootstrap-item-ctx-branching-terminal-reprojection",
            "run-item-ctx-first-branching-terminal-reprojection",
        ),
    )
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None
    module_path = (tmp_path / Path(*module_match.group(1).split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    return module_path


def _design_delta_work_item_runtime_authoritative_modules() -> dict[str, bytes]:
    pending = ["work_item.orc"]
    authoritative_modules: dict[str, bytes] = {}

    while pending:
        module_name = pending.pop()
        if module_name in authoritative_modules:
            continue
        module_path = DESIGN_DELTA_WORK_ITEM_LIBRARY_ROOT / module_name
        module_bytes = module_path.read_bytes()
        authoritative_modules[module_name] = module_bytes
        module_source = module_bytes.decode("utf-8")
        for imported_module in WORKFLOW_LISP_IMPORT_PATTERN.findall(module_source):
            if imported_module.startswith("lisp_frontend_design_delta/"):
                pending.append(f"{imported_module.removeprefix('lisp_frontend_design_delta/')}.orc")

    return dict(sorted(authoritative_modules.items()))


def _bind_nested_match_inputs(bundle, workspace: Path) -> dict[str, object]:
    return bind_workflow_inputs(
        workflow_public_input_contracts(bundle),
        {"report": "artifacts/work/input_report.md"},
        workspace,
    )


def _walk_lowered_steps(steps: list[dict[str, object]]):
    for step in steps:
        yield step
        match_block = step.get("match")
        if isinstance(match_block, dict):
            for case in match_block.get("cases", {}).values():
                if isinstance(case, dict):
                    yield from _walk_lowered_steps(case.get("steps", []))
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            yield from _walk_lowered_steps(repeat_until.get("steps", []))


def _state_contains_artifact_value(state: object, artifact_name: str, expected_value: str) -> bool:
    if isinstance(state, dict):
        artifacts = state.get("artifacts")
        if isinstance(artifacts, dict) and artifacts.get(artifact_name) == expected_value:
            return True
        return any(
            _state_contains_artifact_value(value, artifact_name, expected_value)
            for value in state.values()
        )
    if isinstance(state, list):
        return any(_state_contains_artifact_value(value, artifact_name, expected_value) for value in state)
    return False


def _state_contains_failed_contract_violation(state: object, *, reason: str) -> bool:
    if isinstance(state, dict):
        error = state.get("error")
        context = error.get("context") if isinstance(error, dict) else None
        violations = context.get("violations") if isinstance(context, dict) else None
        has_matching_violation = False
        if isinstance(violations, list):
            for violation in violations:
                if not isinstance(violation, dict):
                    continue
                violation_type = violation.get("type")
                violation_context = violation.get("context")
                if violation_type == reason:
                    has_matching_violation = True
                    break
                if (
                    reason == "invalid_enum_value"
                    and violation_type
                    in {"variant_discriminant_invalid", "variant_field_type_invalid"}
                    and isinstance(violation_context, dict)
                    and isinstance(violation_context.get("allowed"), list)
                ):
                    has_matching_violation = True
                    break
        if (
            state.get("status") == "failed"
            and isinstance(error, dict)
            and error.get("type") == "contract_violation"
            and (
                (isinstance(context, dict) and context.get("reason") == reason)
                or has_matching_violation
            )
        ):
            return True
        return any(
            _state_contains_failed_contract_violation(value, reason=reason) for value in state.values()
        )
    if isinstance(state, list):
        return any(_state_contains_failed_contract_violation(value, reason=reason) for value in state)
    return False


def _iter_call_frame_snapshots(state: object):
    if not isinstance(state, dict):
        return
    call_frames = state.get("call_frames")
    if not isinstance(call_frames, dict):
        return
    for frame in call_frames.values():
        if not isinstance(frame, dict):
            continue
        yield frame
        nested_state = frame.get("state")
        if isinstance(nested_state, dict):
            yield from _iter_call_frame_snapshots(nested_state)


def _call_frame_snapshot_for_import_alias(
    state: dict[str, object], import_alias: str
) -> dict[str, object]:
    for frame in _iter_call_frame_snapshots(state):
        if frame.get("import_alias") == import_alias:
            return frame
    raise AssertionError(f"expected call frame for import alias {import_alias!r}")


def _call_frame_bound_inputs_for_import_alias(
    state: dict[str, object], import_alias: str
) -> dict[str, object]:
    bound_inputs = _call_frame_snapshot_for_import_alias(state, import_alias).get(
        "bound_inputs"
    )
    if isinstance(bound_inputs, dict):
        return bound_inputs
    raise AssertionError(f"expected bound inputs for import alias {import_alias!r}")


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
    bridge_owner: str = "workflow-lisp",
    expiry_condition: str | None = None,
    evidence_refs: tuple[str, ...] | None = None,
) -> dict[str, object]:
    return {
        "retirement_class": retirement_class,
        "retirement_label": retirement_label,
        "replacement_surface": replacement_surface,
        "bridge_owner": bridge_owner,
        "expiry_condition": expiry_condition or f"test-{name}-metadata",
        "evidence_refs": evidence_refs or (f"{name}_evidence",),
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


def _promoted_adapter_binding(
    *,
    name: str,
    stable_command: tuple[str, ...],
    output_type_name: str,
    behavior_class: str,
    owner_module: str,
    replacement_path: str | None,
    effects: tuple[str, ...] = ("structured_result",),
    input_signature: tuple[CertifiedAdapterInputField, ...],
    fixture_ids: tuple[str, ...],
    negative_fixture_ids: tuple[str, ...],
    transition_binding: TransitionBindingMetadata | None = None,
) -> CertifiedAdapterBinding:
    if behavior_class == "resource_transition" and effects == ("structured_result",):
        effects = ("structured_result", "resource_transition", "ledger_update")
    retirement_class = "manifest_assembly"
    retirement_label = "unknown_requires_design"
    replacement_surface = replacement_path or f"typed {name} replacement"
    if behavior_class == "resource_transition":
        retirement_class = "resource_transition"
        retirement_label = "retire_to_transition"
    elif behavior_class in {"typed_projection", "outcome_finalization"}:
        retirement_class = "typed_projection"
        retirement_label = "retire_to_projection"
    return CertifiedAdapterBinding(
        name=name,
        stable_command=stable_command,
        input_contract={"type": "object"},
        output_type_name=output_type_name,
        effects=effects,
        path_safety={"kind": "workspace_relpath"},
        source_map_behavior="step",
        fixture_ids=fixture_ids,
        negative_fixture_ids=negative_fixture_ids,
        behavior_class=behavior_class,
        input_signature=input_signature,
        artifact_contracts=(f"{name}_bundle",),
        state_writes=(),
        error_codes=(f"{name}_invalid",),
        owner_module=owner_module,
        replacement_path=replacement_path,
        invocation_protocol="json_object_positional_arg",
        transition_binding=transition_binding,
        declared_promoted_fields=frozenset(PROMOTED_CALL_REQUIRED_METADATA_FIELDS),
        **_g0_retirement_metadata(
            name=name,
            retirement_class=retirement_class,
            retirement_label=retirement_label,
            replacement_surface=replacement_surface,
        ),
    )


def _design_delta_work_item_provider_externs() -> dict[str, str]:
    return {
        "providers.plan.draft": "fake-plan-draft",
        "providers.plan.review": "fake-plan-review",
        "providers.plan.fix": "fake-plan-fix",
        "providers.architect.draft": "fake-architect-draft",
        "providers.implementation.execute": "fake-implementation-execute",
        "providers.implementation.review": "fake-implementation-review",
        "providers.implementation.fix": "fake-implementation-fix",
        "providers.selector": "fake-selector",
        "providers.work-item.recovery-classifier": "fake-work-item-recovery",
    }


def _design_delta_work_item_prompt_externs() -> dict[str, object]:
    return {
        "prompts.plan.draft": {
            "input_file": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/draft_plan.md"
        },
        "prompts.plan.review": {
            "input_file": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/review_plan.md"
        },
        "prompts.plan.fix": {
            "input_file": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/revise_plan.md"
        },
        "prompts.implementation.execute": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/implement_plan.md"
            )
        },
        "prompts.implementation.review": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/review_implementation.md"
            )
        },
        "prompts.implementation.fix": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/fix_implementation.md"
            )
        },
        "prompts.work-item.classify-blocked-recovery": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_design_delta_work_item/"
                "classify_blocked_implementation_recovery.md"
            )
        },
        "prompts.selector.select-next-work": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md"
            )
        },
        "prompts.architect.draft": {
            "input_file": (
                "workflows/library/prompts/"
                "lisp_frontend_design_delta_design_gap_architect/"
                "draft_implementation_architecture.md"
            )
        },
    }


def _design_delta_checked_in_command_boundaries() -> dict[str, object]:
    payload = json.loads(DESIGN_DELTA_PARENT_DRAIN_COMMANDS.read_text(encoding="utf-8"))
    return _parse_command_boundaries_manifest(
        payload,
        manifest_path=DESIGN_DELTA_PARENT_DRAIN_COMMANDS,
    )


def _design_delta_work_item_command_boundaries() -> dict[str, object]:
    return dict(_design_delta_checked_in_command_boundaries())


def _design_delta_parent_drain_provider_externs() -> dict[str, str]:
    return {
        **_design_delta_work_item_provider_externs(),
        "providers.selector": "fake-selector",
        "providers.architect.draft": "fake-architect-draft",
    }


def _design_delta_parent_drain_prompt_externs() -> dict[str, object]:
    return {
        "prompts.plan.draft": {
            "input_file": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/draft_plan.md"
        },
        "prompts.plan.review": {
            "input_file": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/review_plan.md"
        },
        "prompts.plan.fix": {
            "input_file": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/revise_plan.md"
        },
        "prompts.implementation.execute": {
            "input_file": (
                "workflows/library/prompts/"
                "lisp_frontend_design_delta_implementation_phase/implement_plan.md"
            )
        },
        "prompts.implementation.review": {
            "input_file": (
                "workflows/library/prompts/"
                "lisp_frontend_design_delta_implementation_phase/review_implementation.md"
            )
        },
        "prompts.implementation.fix": {
            "input_file": (
                "workflows/library/prompts/"
                "lisp_frontend_design_delta_implementation_phase/fix_implementation.md"
            )
        },
        "prompts.work-item.classify-blocked-recovery": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_design_delta_work_item/"
                "classify_blocked_implementation_recovery.md"
            )
        },
        "prompts.selector.select-next-work": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_selector/"
                "select_next_design_delta_work.md"
            )
        },
        "prompts.architect.draft": {
            "input_file": (
                "workflows/library/prompts/"
                "lisp_frontend_design_delta_design_gap_architect/"
                "draft_implementation_architecture.md"
            )
        },
    }


def _design_delta_parent_drain_command_boundaries() -> dict[str, object]:
    return dict(_design_delta_checked_in_command_boundaries())


def _design_delta_projection_runtime_command_boundaries() -> dict[str, object]:
    return {}


def _stdlib_parent_audit_binding(name: str, output_type_name: str) -> CertifiedAdapterBinding:
    return CertifiedAdapterBinding(
        name=name,
        stable_command=("python", f"scripts/{name}.py"),
        input_contract={"type": "object"},
        output_type_name=output_type_name,
        effects=("structured_result",),
        path_safety={"kind": "workspace_relpath"},
        source_map_behavior="step",
        fixture_ids=(f"{name}_ok",),
        negative_fixture_ids=(f"{name}_bad",),
    )


def _compile_stdlib_parent_delegation_audit_fixture(tmp_path: Path):
    module_path = _write_entrypoint_fixture_to_tmp(
        STDLIB_PARENT_DELEGATION_AUDIT_FIXTURE,
        tmp_path=tmp_path,
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path, REPO_ROOT / "workflows" / "library"),
        command_boundaries={
            "select_next_item": _stdlib_parent_audit_binding(
                "select_next_item",
                "SelectionResult",
            ),
            "execute_selected_item": _stdlib_parent_audit_binding(
                "execute_selected_item",
                "SelectedItemResult",
            ),
            "draft_gap_item": _stdlib_parent_audit_binding(
                "draft_gap_item",
                "GapResult",
            ),
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    return result, lowered_by_name


def _compile_design_delta_implementation_phase_entrypoint(tmp_path: Path):
    result = compile_stage3_entrypoint(
        REPO_ROOT
        / "workflows"
        / "library"
        / "lisp_frontend_design_delta"
        / "implementation_phase.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs=_design_delta_provider_externs(),
        prompt_externs=_design_delta_prompt_externs(),
        command_boundaries=_design_delta_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    return result, lowered_by_name


def _copy_design_delta_runtime_modules(tmp_path: Path) -> Path:
    module_dir = tmp_path / "lisp_frontend_design_delta"
    module_dir.mkdir(parents=True, exist_ok=True)
    for name in ("implementation_phase.orc", "types.orc"):
        source = REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / name
        _write_module(module_dir / name, source.read_text(encoding="utf-8"))
    return module_dir / "implementation_phase.orc"


def _compile_design_delta_implementation_phase_runtime_entrypoint(tmp_path: Path):
    module_path = _copy_design_delta_runtime_modules(tmp_path)
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs=_design_delta_provider_externs(),
        prompt_externs=_design_delta_prompt_externs(),
        command_boundaries=_design_delta_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return module_path, result


def _compile_design_delta_parent_call_entrypoint(tmp_path: Path):
    module_path = _write_entrypoint_fixture_to_tmp(
        PARENT_CALL_IMPLEMENTATION_PHASE_FIXTURE,
        tmp_path=tmp_path,
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(REPO_ROOT / "workflows" / "library", tmp_path),
        provider_externs=_design_delta_provider_externs(),
        prompt_externs=_design_delta_prompt_externs(),
        command_boundaries=_design_delta_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    return module_path, result, lowered_by_name


def _compile_design_delta_parent_call_runtime_entrypoint(tmp_path: Path):
    _copy_design_delta_runtime_modules(tmp_path)
    module_path = _write_entrypoint_fixture_to_tmp(
        PARENT_CALL_IMPLEMENTATION_PHASE_FIXTURE,
        tmp_path=tmp_path,
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs=_design_delta_provider_externs(),
        prompt_externs=_design_delta_prompt_externs(),
        command_boundaries=_design_delta_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return module_path, result


def _copy_design_delta_work_item_runtime_modules(
    tmp_path: Path,
    *,
    plan_review_decision_override: str | None = None,
    implementation_state_override: str | None = None,
) -> Path:
    module_dir = tmp_path / "lisp_frontend_design_delta"
    source_dir = DESIGN_DELTA_WORK_ITEM_CANDIDATE_ROOT / "lisp_frontend_design_delta"
    module_dir.mkdir(parents=True, exist_ok=True)
    for name in _design_delta_work_item_runtime_authoritative_modules():
        source = source_dir / name
        _write_module(module_dir / name, source.read_text(encoding="utf-8"))
    # Negative tests inject invalid enum/state values through the fake provider
    # outputs. Preserve the authoritative runtime modules so these checks
    # continue to exercise provider-boundary validation instead of local test
    # rewrites that can drift structurally.
    _ = plan_review_decision_override, implementation_state_override
    return module_dir / "work_item.orc"


def _copy_design_delta_parent_drain_runtime_modules(tmp_path: Path) -> Path:
    module_dir = tmp_path / "lisp_frontend_design_delta"
    source_dir = DESIGN_DELTA_WORK_ITEM_CANDIDATE_ROOT / "lisp_frontend_design_delta"
    module_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted(source_dir.glob("*.orc")):
        _write_module(module_dir / source.name, source.read_text(encoding="utf-8"))
    _write_module(
        module_dir / "drain.orc",
        (DESIGN_DELTA_WORK_ITEM_LIBRARY_ROOT / "drain.orc").read_text(encoding="utf-8"),
    )
    return module_dir / "drain.orc"


def _compile_design_delta_work_item_entrypoint(tmp_path: Path):
    result = compile_stage3_entrypoint(
        DESIGN_DELTA_WORK_ITEM_CANDIDATE_ROOT / "lisp_frontend_design_delta" / "work_item.orc",
        source_roots=(DESIGN_DELTA_WORK_ITEM_CANDIDATE_ROOT,),
        provider_externs=_design_delta_work_item_provider_externs(),
        prompt_externs=_design_delta_work_item_prompt_externs(),
        command_boundaries=_design_delta_work_item_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    return result, lowered_by_name


def _compile_design_delta_work_item_library_module(tmp_path: Path):
    return compile_stage3_module(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc",
        provider_externs=_design_delta_work_item_provider_externs(),
        prompt_externs=_design_delta_work_item_prompt_externs(),
        command_boundaries=_design_delta_work_item_command_boundaries(),
        validate_shared=False,
        workspace_root=tmp_path,
    )


def _compile_design_delta_parent_drain_entrypoint(tmp_path: Path):
    result = compile_stage3_entrypoint(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs=_design_delta_parent_drain_provider_externs(),
        prompt_externs=_design_delta_parent_drain_prompt_externs(),
        command_boundaries=_design_delta_parent_drain_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
        family_profile_catalog=load_workflow_family_profile_catalog(
            (DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE,)
        ),
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    return result, lowered_by_name


def _compile_design_delta_parent_drain_runtime_entrypoint(tmp_path: Path):
    module_path = _copy_design_delta_parent_drain_runtime_modules(tmp_path)
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs=_design_delta_parent_drain_provider_externs(),
        prompt_externs=_design_delta_parent_drain_prompt_externs(),
        command_boundaries=_design_delta_parent_drain_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
        family_profile_catalog=load_workflow_family_profile_catalog(
            (DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE,)
        ),
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    return module_path, result, lowered_by_name


def _compile_design_delta_stdlib_payloads_entrypoint(tmp_path: Path):
    result = compile_stage3_entrypoint(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "stdlib_payloads.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs=_design_delta_parent_drain_provider_externs(),
        prompt_externs=_design_delta_parent_drain_prompt_externs(),
        command_boundaries=_design_delta_parent_drain_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    return result, lowered_by_name


def _compile_design_delta_runtime_transition_fixture_entrypoint(tmp_path: Path):
    result = compile_stage3_entrypoint(
        DESIGN_DELTA_RUNTIME_TRANSITION_FIXTURE,
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={},
        prompt_externs={},
        command_boundaries=_design_delta_parent_drain_command_boundaries(),
        validate_shared=False,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles_by_name[
        "lisp_frontend_design_delta/transitions::emit-drain-status-transition-audit"
    ]
    return result, bundle


def _compile_design_delta_runtime_view_fixture_entrypoint(tmp_path: Path):
    result = compile_stage3_entrypoint(
        DESIGN_DELTA_RUNTIME_VIEW_FIXTURE,
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={},
        prompt_externs={},
        command_boundaries=_design_delta_parent_drain_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles_by_name[
        "lisp_frontend_design_delta/runtime_view_fixture::run-summary-view"
    ]
    lowered = next(
        workflow
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
        if workflow.typed_workflow.definition.name
        == "lisp_frontend_design_delta/runtime_view_fixture::run-summary-view"
    )
    return result, bundle, lowered


def _run_design_delta_runtime_transition_fixture_cli(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    run_state_path = tmp_path / "state" / "run_state.json"
    summary_path = tmp_path / "artifacts" / "work" / "drain_summary.json"
    state_dir = tmp_path / "orchestrator-state"
    run_state_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    run_state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps({"status": "BLOCKED", "reason": "runtime_native_fixture"}) + "\n",
        encoding="utf-8",
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator",
            "run",
            str(DESIGN_DELTA_RUNTIME_TRANSITION_FIXTURE),
            "--entry-workflow",
            "run-runtime-transition-fixture",
            "--source-root",
            str(REPO_ROOT / "workflows" / "library"),
            "--provider-externs-file",
            str(
                REPO_ROOT
                / "workflows"
                / "examples"
                / "inputs"
                / "workflow_lisp_migrations"
                / "design_delta_parent_drain.providers.json"
            ),
            "--prompt-externs-file",
            str(
                REPO_ROOT
                / "workflows"
                / "examples"
                / "inputs"
                / "workflow_lisp_migrations"
                / "design_delta_parent_drain.prompts.json"
            ),
            "--command-boundaries-file",
            str(
                REPO_ROOT
                / "workflows"
                / "examples"
                / "inputs"
                / "workflow_lisp_migrations"
                / "design_delta_parent_drain.commands.json"
            ),
            "--input",
            "summary_path=artifacts/work/drain_summary.json",
            "--state-dir",
            str(state_dir),
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [str(REPO_ROOT), *filter(None, [os.environ.get("PYTHONPATH")])]
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )


def _run_design_delta_parent_drain_public_input_only_cli_dry_run(
    tmp_path: Path,
) -> subprocess.CompletedProcess[str]:
    _write_design_delta_work_item_runtime_inputs(tmp_path, work_item_source="BACKLOG_ITEM")
    args = [
        sys.executable,
        "-m",
        "orchestrator",
        "run",
        str(REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc"),
        "--entry-workflow",
        "lisp_frontend_design_delta/drain::drain",
        "--source-root",
        str(REPO_ROOT / "workflows" / "library"),
        "--provider-externs-file",
        str(
            REPO_ROOT
            / "workflows"
            / "examples"
            / "inputs"
            / "workflow_lisp_migrations"
            / "design_delta_parent_drain.providers.json"
        ),
        "--prompt-externs-file",
        str(
            REPO_ROOT
            / "workflows"
            / "examples"
            / "inputs"
            / "workflow_lisp_migrations"
            / "design_delta_parent_drain.prompts.json"
        ),
        "--command-boundaries-file",
        str(DESIGN_DELTA_PARENT_DRAIN_COMMANDS),
        "--dry-run",
    ]
    for input_name, value in _design_delta_parent_drain_public_input_only_bound_inputs().items():
        args.extend(["--input", f"{input_name}={value}"])
    return subprocess.run(
        args,
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [str(REPO_ROOT), *filter(None, [os.environ.get("PYTHONPATH")])]
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )


def _assert_design_delta_work_item_advances_past_private_workflow_ifexpr_export_blocker(
    tmp_path: Path,
):
    try:
        result, lowered_by_name = _compile_design_delta_work_item_entrypoint(tmp_path)
    except LispFrontendCompileError as exc:
        _assert_design_delta_work_item_candidate_post_ifexpr_boundary_failure(exc.diagnostics)
        diagnostic_codes = {diagnostic.code for diagnostic in exc.diagnostics}
        assert "proc_private_workflow_boundary_invalid" not in diagnostic_codes
        return None, None

    lowered_names = set(lowered_by_name)
    assert "lisp_frontend_design_delta/work_item::run-work-item" in lowered_names
    assert "lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery" in lowered_names
    return result, lowered_by_name


def _assert_design_delta_work_item_candidate_post_ifexpr_boundary_failure(
    diagnostics: tuple[LispFrontendDiagnostic, ...],
) -> None:
    diagnostic_codes = {diagnostic.code for diagnostic in diagnostics}

    assert "union_return_variant_ambiguous" not in diagnostic_codes
    assert "union_return_variant_incompatible" not in diagnostic_codes
    assert "proc_private_workflow_boundary_invalid" not in diagnostic_codes
    assert "low_level_state_path_in_high_level_module" not in diagnostic_codes
    assert "workflow_boundary_type_invalid" not in diagnostic_codes
    assert not any("unsupported `IfExpr`" in diagnostic.message for diagnostic in diagnostics)
    assert diagnostics, "expected a distinct downstream diagnostic or successful compile"


def _assert_design_delta_work_item_candidate_phase_family_boundary_failure(
    diagnostics: tuple[LispFrontendDiagnostic, ...],
) -> None:
    _assert_design_delta_work_item_candidate_post_ifexpr_boundary_failure(diagnostics)


def _assert_design_delta_parent_call_work_item_phase_family_boundary_failure(
    diagnostics: tuple[LispFrontendDiagnostic, ...],
) -> None:
    _assert_design_delta_work_item_candidate_post_ifexpr_boundary_failure(diagnostics)


def _walk_lowered_steps(steps):
    for step in steps:
        yield step
        if "repeat_until" in step:
            yield from _walk_lowered_steps(step["repeat_until"].get("steps", []))
        if "match" in step:
            for case in step["match"].get("cases", {}).values():
                yield from _walk_lowered_steps(case.get("steps", []))


def _all_lowered_commands(lowered_by_name: dict[str, dict[str, object]]) -> list[list[str]]:
    return [
        step["command"]
        for lowered in lowered_by_name.values()
        for step in _walk_lowered_steps(lowered.get("steps", []))
        if isinstance(step.get("command"), list)
    ]


def _compile_design_delta_work_item_runtime_entrypoint(
    tmp_path: Path,
    *,
    plan_review_decision_override: str | None = None,
    implementation_state_override: str | None = None,
):
    module_path = _copy_design_delta_work_item_runtime_modules(
        tmp_path,
        plan_review_decision_override=plan_review_decision_override,
        implementation_state_override=implementation_state_override,
    )
    family_profile_catalog = (
        None
        if plan_review_decision_override is not None or implementation_state_override is not None
        else load_workflow_family_profile_catalog((DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE,))
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs=_design_delta_work_item_provider_externs(),
        prompt_externs=_design_delta_work_item_prompt_externs(),
        command_boundaries=_design_delta_work_item_runtime_command_boundaries(tmp_path),
        validate_shared=True,
        workspace_root=tmp_path,
        family_profile_catalog=family_profile_catalog,
    )
    return module_path, result


def _compile_design_delta_projection_runtime_entrypoint(
    tmp_path: Path,
    *,
    lint_profile: str = "default",
):
    fixture_path = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid" / "design_delta_projection_runtime.orc"
    result = compile_stage3_entrypoint(
        fixture_path,
        source_roots=(fixture_path.parent,),
        provider_externs=_design_delta_parent_drain_provider_externs(),
        prompt_externs=_design_delta_parent_drain_prompt_externs(),
        command_boundaries=_design_delta_projection_runtime_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
        lint_profile=lint_profile,
    )
    return result


def _compile_design_delta_parent_call_work_item_entrypoint(tmp_path: Path):
    _copy_design_delta_work_item_runtime_modules(tmp_path)
    module_path = _write_entrypoint_fixture_to_tmp(
        PARENT_CALL_WORK_ITEM_CANDIDATE_FIXTURE,
        tmp_path=tmp_path,
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs=_design_delta_work_item_provider_externs(),
        prompt_externs=_design_delta_work_item_prompt_externs(),
        command_boundaries=_design_delta_work_item_runtime_command_boundaries(tmp_path),
        validate_shared=True,
        workspace_root=tmp_path,
        family_profile_catalog=load_workflow_family_profile_catalog(
            (DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE,)
        ),
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    return module_path, result, lowered_by_name


def _compile_design_delta_item_ctx_child_phase_reuse_entrypoint(tmp_path: Path):
    module_path = _write_item_ctx_child_phase_reuse_core_fixture_to_tmp(tmp_path)
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(
            tmp_path,
            WORKFLOW_LISP_FIXTURES / "valid",
            REPO_ROOT / "workflows" / "library",
        ),
        provider_externs=_design_delta_work_item_provider_externs(),
        prompt_externs=_design_delta_work_item_prompt_externs(),
        command_boundaries=_design_delta_work_item_runtime_command_boundaries(tmp_path),
        validate_shared=True,
        workspace_root=tmp_path,
        family_profile_catalog=load_workflow_family_profile_catalog(
            (DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE,)
        ),
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    return module_path, result, lowered_by_name


def _compile_design_delta_item_ctx_child_phase_reuse_branching_terminal_reprojection_entrypoint(
    tmp_path: Path,
):
    module_path = ITEM_CTX_CHILD_PHASE_REUSE_FIXTURE
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(WORKFLOW_LISP_FIXTURES / "valid", REPO_ROOT / "workflows" / "library"),
        provider_externs=_design_delta_work_item_provider_externs(),
        prompt_externs=_design_delta_work_item_prompt_externs(),
        command_boundaries=_design_delta_work_item_runtime_command_boundaries(tmp_path),
        validate_shared=True,
        workspace_root=tmp_path,
        entry_workflow=(
            "design_delta_item_ctx_child_phase_reuse::run-entry-branching-terminal-reprojection"
        ),
        family_profile_catalog=load_workflow_family_profile_catalog(
            (DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE,)
        ),
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    return module_path, result, lowered_by_name


def _compile_design_delta_item_ctx_child_phase_reuse_proc_entrypoint(
    tmp_path: Path,
    module_path: Path = ITEM_CTX_CHILD_PHASE_REUSE_PROC_FIXTURE,
):
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(WORKFLOW_LISP_FIXTURES / "valid", REPO_ROOT / "workflows" / "library"),
        provider_externs=_design_delta_work_item_provider_externs(),
        prompt_externs=_design_delta_work_item_prompt_externs(),
        command_boundaries=_design_delta_work_item_runtime_command_boundaries(tmp_path),
        validate_shared=True,
        workspace_root=tmp_path,
        family_profile_catalog=load_workflow_family_profile_catalog(
            (DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE,)
        ),
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    return module_path, result, lowered_by_name


def _compile_arbitrary_derived_phase_reuse_entrypoint(tmp_path: Path):
    source = _write_item_ctx_child_phase_reuse_core_fixture_to_tmp(tmp_path).read_text(
        encoding="utf-8"
    )
    source = source.replace(
        "(defmodule design_delta_item_ctx_child_phase_reuse)",
        "(defmodule arbitrary_derived_phase_reuse)",
        1,
    )
    module_path = _write_module(tmp_path / "arbitrary_derived_phase_reuse.orc", source)
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(
            tmp_path,
            WORKFLOW_LISP_FIXTURES / "valid",
            REPO_ROOT / "workflows" / "library",
        ),
        provider_externs=_design_delta_work_item_provider_externs(),
        prompt_externs=_design_delta_work_item_prompt_externs(),
        command_boundaries=_design_delta_work_item_runtime_command_boundaries(tmp_path),
        validate_shared=True,
        workspace_root=tmp_path,
        entry_workflow="arbitrary_derived_phase_reuse::run-entry",
        family_profile_catalog=load_workflow_family_profile_catalog(
            (DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE,)
        ),
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    return module_path, result, lowered_by_name


def _design_delta_work_item_runtime_command_boundaries(tmp_path: Path) -> dict[str, object]:
    _ = tmp_path
    return dict(_design_delta_work_item_command_boundaries())


def _compile_design_delta_parent_contract_probe_entrypoint(tmp_path: Path):
    _copy_design_delta_runtime_modules(tmp_path)
    module_path = _write_module(
        tmp_path / "design_delta_parent_contract_probe.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule design_delta_parent_contract_probe)",
                "  (import lisp_frontend_design_delta/implementation_phase :only (implementation-phase))",
                "  (import lisp_frontend_design_delta/types :only",
                "    (ArtifactChecksTargetPath ArtifactReviewTargetPath ArtifactWorkPath ArtifactWorkTargetPath",
                "      BaselineDesignDoc CheckCommandsPath ImplementationPhaseResult PlanDoc TargetDesignDoc))",
                "  (export probe)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defworkflow probe",
                "    ((phase-ctx PhaseCtx)",
                "     (target_design TargetDesignDoc)",
                "     (baseline_design BaselineDesignDoc)",
                "     (plan_path PlanDoc)",
                "     (check_commands_path CheckCommandsPath)",
                "     (execution_report_target_path ArtifactWorkTargetPath)",
                "     (progress_report_target_path ArtifactWorkTargetPath)",
                "     (checks_report_target_path ArtifactChecksTargetPath)",
                "     (implementation_review_report_target_path ArtifactReviewTargetPath)",
                "     (implementation_execute_provider String)",
                "     (implementation_review_provider String))",
                "    -> ImplementationPhaseResult",
                "    (let* ((phase-result",
                "             (call implementation-phase",
                "               :phase-ctx phase-ctx",
                "               :target_design target_design",
                "               :baseline_design baseline_design",
                "               :plan_path plan_path",
                "               :check_commands_path check_commands_path",
                "               :execution_report_target_path execution_report_target_path",
                "               :progress_report_target_path progress_report_target_path",
                "               :checks_report_target_path checks_report_target_path",
                "               :implementation_review_report_target_path",
                "                 implementation_review_report_target_path",
                "               :implementation_execute_provider implementation_execute_provider",
                "               :implementation_review_provider implementation_review_provider)))",
                "      (record ImplementationPhaseResult",
                "        :implementation-state phase-result.implementation-state",
                "        :implementation-review-decision phase-result.implementation-review-decision",
                "        :execution-report phase-result.execution-report",
                "        :progress-report phase-result.progress-report",
                "        :checks-report phase-result.checks-report",
                "        :implementation-review-report phase-result.implementation-review-report))))",
            ]
        )
        + "\n",
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs=_design_delta_provider_externs(),
        prompt_externs=_design_delta_prompt_externs(),
        command_boundaries=_design_delta_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return module_path, result


def _compile_nested_entrypoint_fixture(
    fixture_path: Path,
    *,
    tmp_path: Path,
    extra_source_roots: tuple[Path, ...] = (),
):
    module_path = _write_entrypoint_fixture_to_tmp(fixture_path, tmp_path=tmp_path)
    return compile_stage3_entrypoint(
        module_path,
        source_roots=(*extra_source_roots, tmp_path),
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md",
            "prompts.implementation.review": "tests/fixtures/workflow_lisp/valid/prompts/implementation/review.md",
            "prompts.implementation.fix": "tests/fixtures/workflow_lisp/valid/prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
                **_g0_retirement_metadata(
                    name="run_checks",
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
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )


def _write_nested_runtime_prompt_assets(tmp_path: Path) -> None:
    for relpath in (
        "nested/tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md",
        "nested/tests/fixtures/workflow_lisp/valid/prompts/implementation/review.md",
        "nested/tests/fixtures/workflow_lisp/valid/prompts/implementation/fix.md",
        "artifacts/work/review_prompt.md",
        "artifacts/work/fix_prompt.md",
    ):
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("prompt\n", encoding="utf-8")


def _write_nested_runtime_run_checks_script(tmp_path: Path) -> None:
    target = tmp_path / "scripts" / "run_checks.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "report_path = Path(sys.argv[2])",
                "report_path.parent.mkdir(parents=True, exist_ok=True)",
                'report_path.write_text("# checks\\n", encoding="utf-8")',
                'bundle_path = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])',
                "bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                'bundle_path.write_text(json.dumps({"checks_report": sys.argv[2]}) + "\\n", encoding="utf-8")',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_design_delta_runtime_prompt_assets(module_root: Path) -> None:
    for relpath in _design_delta_prompt_externs().values():
        target = Path(relpath)
        if target.is_absolute():
            continue
        target = module_root / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("prompt\n", encoding="utf-8")


def _write_design_delta_runtime_run_checks_script(tmp_path: Path) -> None:
    target = tmp_path / "workflows" / "library" / "scripts" / "run_neurips_backlog_checks.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "argv = sys.argv[1:]",
                "report_path = Path(argv[argv.index('--report-path') + 1])",
                "report_path.parent.mkdir(parents=True, exist_ok=True)",
                'report_path.write_text("# checks\\n", encoding="utf-8")',
                'bundle_path = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])',
                "bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                'bundle_path.write_text(json.dumps({"checks_report": report_path.as_posix()}) + "\\n", encoding="utf-8")',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_design_delta_runtime_inputs(tmp_path: Path) -> None:
    for relpath, contents in {
        "docs/design/target.md": "# target\n",
        "docs/design/baseline.md": "# baseline\n",
        "docs/plans/plan.md": "# plan\n",
        "state/check_commands.json": json.dumps(["python -m pytest -q"]) + "\n",
    }.items():
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")


def _nested_runtime_bound_inputs() -> dict[str, str]:
    return {
        "phase-ctx__run__run-id": "nested-smoke",
        "phase-ctx__run__state-root": "state/run",
        "phase-ctx__run__artifact-root": "artifacts/run",
        "phase-ctx__phase-name": "implementation",
        "phase-ctx__state-root": "state/implementation",
        "phase-ctx__artifact-root": "artifacts/implementation",
        "review_prompt": "artifacts/work/review_prompt.md",
        "fix_prompt": "artifacts/work/fix_prompt.md",
        "checks_report_target": "artifacts/work/checks_report.md",
        "execution_report_target": "artifacts/work/execution_report.md",
        "progress_report_target": "artifacts/work/progress_report.md",
        "review_report_target": "artifacts/work/implementation_review_report.md",
    }


def _design_delta_parent_call_phase_ctx_bound_inputs() -> dict[str, object]:
    return {
        "phase-ctx__run__run-id": "design-delta-smoke",
        "phase-ctx__run__state-root": "state/run",
        "phase-ctx__run__artifact-root": "artifacts/run",
        "phase-ctx__phase-name": "implementation",
        "phase-ctx__state-root": "state/implementation",
        "phase-ctx__artifact-root": "artifacts/implementation",
    }


def _design_delta_runtime_bound_inputs(*, attempt_variant: str) -> dict[str, object]:
    return {
        "target_design": "docs/design/target.md",
        "baseline_design": "docs/design/baseline.md",
        "plan_path": "docs/plans/plan.md",
        "check_commands__commands": ["python -m pytest -q"],
        "check_commands_target_path": "state/check_commands.json",
        "execution_report_target_path": "artifacts/work/execution_report.md",
        "progress_report_target_path": "artifacts/work/progress_report.md",
        "checks_report_target_path": "artifacts/checks/checks_report.md",
        "implementation_review_report_target_path": (
            "artifacts/review/implementation_review_report.md"
        ),
        "implementation_execute_provider": "codex",
        "implementation_review_provider": "codex",
    }


def _success_provider_result() -> SimpleNamespace:
    return SimpleNamespace(
        exit_code=0,
        stdout=b"ok",
        stderr=b"",
        duration_ms=1,
        error=None,
        missing_placeholders=None,
        invalid_prompt_placeholder=False,
        raw_stdout=None,
        normalized_stdout=None,
        provider_session=None,
    )


def _rewrite_managed_write_root_bindings_for_smoke(
    original: dict[str, str],
    *,
    salt: str = "",
) -> dict[str, str]:
    rewritten = dict(original)
    for input_name, value in list(rewritten.items()):
        if not isinstance(input_name, str) or not input_name.startswith("__write_root__"):
            continue
        if not isinstance(value, str):
            continue
        digest_source = f"{salt}:{value}" if salt else value
        rewritten[input_name] = (
            f"state/test-smoke/{hashlib.sha1(digest_source.encode('utf-8')).hexdigest()[:16]}.json"
        )
    return rewritten


def _execute_compiled_design_delta_bundle(
    tmp_path: Path,
    *,
    bundle,
    workflow_path: Path,
    module_root: Path,
    attempt_variant: str,
    review_sequence: tuple[str, ...] = ("APPROVE",),
    extra_bound_inputs: dict[str, object] | None = None,
):
    _write_design_delta_runtime_prompt_assets(module_root)
    _write_design_delta_runtime_run_checks_script(tmp_path)
    _write_design_delta_runtime_inputs(tmp_path)

    provider_calls: list[str] = []
    provider_contexts: list[tuple[str, dict[str, str]]] = []
    review_index = 0

    def _prepare_invocation(
        _self,
        provider_name=None,
        params=None,
        context=None,
        prompt_content=None,
        env=None,
        **_kwargs,
    ):
        provider_contexts.append((provider_name, dict(context or {})))
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=prompt_content or "",
                env=env or {},
                provider_name=provider_name,
            ),
            None,
        )

    def _execute_provider(_self, invocation, **_kwargs):
        provider_calls.append(invocation.provider_name)
        bundle_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)

        if invocation.provider_name == "fake-execute":
            if attempt_variant == "COMPLETED":
                execution_report = tmp_path / "artifacts" / "work" / "execution_report.md"
                execution_report.parent.mkdir(parents=True, exist_ok=True)
                execution_report.write_text("# execution report\n", encoding="utf-8")
                bundle_payload = {
                    "variant": "COMPLETED",
                    "implementation_state": "COMPLETED",
                    "execution_report": "artifacts/work/execution_report.md",
                }
            else:
                progress_report = tmp_path / "artifacts" / "work" / "progress_report.md"
                progress_report.parent.mkdir(parents=True, exist_ok=True)
                progress_report.write_text("# blocked progress\n", encoding="utf-8")
                bundle_payload = {
                    "variant": "BLOCKED",
                    "implementation_state": "BLOCKED",
                    "implementation_review_decision": "NOT_APPLICABLE",
                    "progress_report": "artifacts/work/progress_report.md",
                    "blocker_class": "external_dependency_outside_authority",
                }
            bundle_path.write_text(json.dumps(bundle_payload) + "\n", encoding="utf-8")
            return _success_provider_result()

        if invocation.provider_name == "fake-review":
            nonlocal review_index
            review_variant = review_sequence[min(review_index, len(review_sequence) - 1)]
            review_report = tmp_path / "artifacts" / "review" / "implementation_review_report.md"
            review_report.parent.mkdir(parents=True, exist_ok=True)
            review_report.write_text(f"# review report {review_index}\n", encoding="utf-8")
            findings_path = tmp_path / "artifacts" / "work" / "findings.json"
            findings_path.parent.mkdir(parents=True, exist_ok=True)
            findings_path.write_text(
                json.dumps({"schema_version": "ReviewFindings.v1", "items": []}) + "\n",
                encoding="utf-8",
            )
            review_index += 1
            bundle_path.write_text(
                json.dumps(
                    {
                        "variant": review_variant,
                        "review_report": "artifacts/review/implementation_review_report.md",
                        "findings": {
                            "schema_version": "ReviewFindings.v1",
                            "items_path": "artifacts/work/findings.json",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return _success_provider_result()

        if invocation.provider_name == "fake-fix":
            fixed_report = tmp_path / "artifacts" / "work" / "execution_report_fixed.md"
            fixed_report.parent.mkdir(parents=True, exist_ok=True)
            fixed_report.write_text("# fixed execution report\n", encoding="utf-8")
            bundle_path.write_text(
                json.dumps(
                    {
                        "execution_report": "artifacts/work/execution_report_fixed.md",
                        "checks_report": "artifacts/checks/checks_report.md",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return _success_provider_result()

        raise AssertionError(f"unexpected provider call: {invocation.provider_name}")

    original_resolve_bound_inputs = CallExecutor.resolve_bound_inputs
    managed_write_root_rewrite_count = 0

    def _resolve_bound_inputs(self, step, imported_workflow, state, **kwargs):
        nonlocal managed_write_root_rewrite_count
        bound_inputs, error = original_resolve_bound_inputs(
            self,
            step,
            imported_workflow,
            state,
            **kwargs,
        )
        if error is not None or bound_inputs is None:
            return bound_inputs, error
        managed_write_root_rewrite_count += 1
        return _rewrite_managed_write_root_bindings_for_smoke(
            bound_inputs,
            salt=f"call-{managed_write_root_rewrite_count}",
        ), None

    state_manager = StateManager(workspace=tmp_path, run_id=f"design-delta-{attempt_variant.lower()}")
    state_manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={
            **_design_delta_runtime_bound_inputs(attempt_variant=attempt_variant),
            **(extra_bound_inputs or {}),
        },
    )

    smoke_pythonpath = os.pathsep.join(
        [str(REPO_ROOT), *filter(None, [os.environ.get("PYTHONPATH")])]
    )
    with patch.dict(os.environ, {"PYTHONPATH": smoke_pythonpath}), patch.object(
        ProviderExecutor, "prepare_invocation", _prepare_invocation
    ), patch.object(
        ProviderExecutor, "execute", _execute_provider
    ), patch.object(CallExecutor, "resolve_bound_inputs", _resolve_bound_inputs):
        state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    return tmp_path, state, provider_calls, provider_contexts


def _execute_nested_implementation_phase_route(
    tmp_path: Path,
    *,
    attempt_variant: str,
):
    _write_nested_runtime_prompt_assets(tmp_path)
    _write_nested_runtime_run_checks_script(tmp_path)
    result = _compile_nested_entrypoint_fixture(
        NESTED_IMPLEMENTATION_PHASE_FIXTURE,
        tmp_path=tmp_path,
    )
    bundle = result.entry_result.validated_bundles["nested/implementation-phase::implementation-phase"]

    provider_calls: list[str] = []

    def _prepare_invocation(_self, provider_name=None, prompt_content=None, env=None, **_kwargs):
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=prompt_content or "",
                env=env or {},
                provider_name=provider_name,
            ),
            None,
        )

    def _execute_provider(_self, invocation, **_kwargs):
        provider_calls.append(invocation.provider_name)
        bundle_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)

        if invocation.provider_name == "fake-execute":
            if attempt_variant == "COMPLETED":
                execution_report = tmp_path / "artifacts" / "work" / "execution_report.md"
                execution_report.parent.mkdir(parents=True, exist_ok=True)
                execution_report.write_text("# execution report\n", encoding="utf-8")
                bundle_payload = {
                    "variant": "COMPLETED",
                    "execution_report": "artifacts/work/execution_report.md",
                }
            else:
                progress_report = tmp_path / "artifacts" / "work" / "progress_report.md"
                progress_report.parent.mkdir(parents=True, exist_ok=True)
                progress_report.write_text("# blocked progress\n", encoding="utf-8")
                bundle_payload = {
                    "variant": "BLOCKED",
                    "progress_report": "artifacts/work/progress_report.md",
                    "blocker_class": "external_dependency_outside_authority",
                }
            bundle_path.write_text(json.dumps(bundle_payload) + "\n", encoding="utf-8")
            return _success_provider_result()

        if invocation.provider_name == "fake-review":
            review_report = tmp_path / "artifacts" / "review" / "review_report.md"
            review_report.parent.mkdir(parents=True, exist_ok=True)
            review_report.write_text("# review report\n", encoding="utf-8")
            findings_path = tmp_path / "artifacts" / "work" / "findings.json"
            findings_path.parent.mkdir(parents=True, exist_ok=True)
            findings_path.write_text(
                json.dumps({"schema_version": "ReviewFindings.v1", "items": []}) + "\n",
                encoding="utf-8",
            )
            bundle_path.write_text(
                json.dumps(
                    {
                        "variant": "APPROVE",
                        "review_report": "artifacts/review/review_report.md",
                        "review_decision": "APPROVE",
                        "findings": {
                            "schema_version": "ReviewFindings.v1",
                            "items_path": "artifacts/work/findings.json",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return _success_provider_result()

        raise AssertionError(f"unexpected provider call: {invocation.provider_name}")

    original_resolve_bound_inputs = CallExecutor.resolve_bound_inputs

    def _resolve_bound_inputs(self, step, imported_workflow, state, **kwargs):
        bound_inputs, error = original_resolve_bound_inputs(
            self,
            step,
            imported_workflow,
            state,
            **kwargs,
        )
        if error is not None or bound_inputs is None:
            return bound_inputs, error
        return _rewrite_managed_write_root_bindings_for_smoke(bound_inputs), None

    state_manager = StateManager(workspace=tmp_path, run_id=f"nested-{attempt_variant.lower()}")
    state_manager.initialize(
        (tmp_path / "nested" / "implementation-phase.orc").as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_nested_runtime_bound_inputs(),
    )

    smoke_pythonpath = os.pathsep.join(
        [str(REPO_ROOT), *filter(None, [os.environ.get("PYTHONPATH")])]
    )
    with patch.dict(os.environ, {"PYTHONPATH": smoke_pythonpath}), patch.object(
        ProviderExecutor, "prepare_invocation", _prepare_invocation
    ), patch.object(
        ProviderExecutor, "execute", _execute_provider
    ), patch.object(CallExecutor, "resolve_bound_inputs", _resolve_bound_inputs):
        state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    return tmp_path, state, provider_calls


def _execute_design_delta_implementation_phase_route(
    tmp_path: Path,
    *,
    attempt_variant: str,
    review_sequence: tuple[str, ...] = ("APPROVE",),
):
    workflow_path, result = _compile_design_delta_implementation_phase_runtime_entrypoint(tmp_path)
    bundle = result.entry_result.validated_bundles[
        "lisp_frontend_design_delta/implementation_phase::implementation-phase"
    ]
    return _execute_compiled_design_delta_bundle(
        tmp_path,
        bundle=bundle,
        workflow_path=workflow_path,
        module_root=workflow_path.parent,
        attempt_variant=attempt_variant,
        review_sequence=review_sequence,
    )


def _execute_design_delta_parent_call_route(
    tmp_path: Path,
    *,
    attempt_variant: str,
    review_sequence: tuple[str, ...] = ("APPROVE",),
):
    workflow_path, result = _compile_design_delta_parent_call_runtime_entrypoint(tmp_path)
    bundle = result.entry_result.validated_bundles[
        "design_delta_parent_calls_implementation_phase::run-implementation-phase"
    ]
    return _execute_compiled_design_delta_bundle(
        tmp_path,
        bundle=bundle,
        workflow_path=workflow_path,
        module_root=tmp_path / "lisp_frontend_design_delta",
        attempt_variant=attempt_variant,
        review_sequence=review_sequence,
        extra_bound_inputs=_design_delta_parent_call_phase_ctx_bound_inputs(),
    )


def _write_design_delta_work_item_runtime_prompt_assets(module_root: Path) -> None:
    for prompt_ref in _design_delta_parent_drain_prompt_externs().values():
        relpath = (
            prompt_ref.get("input_file") or prompt_ref.get("asset_file")
            if isinstance(prompt_ref, dict)
            else prompt_ref
        )
        assert isinstance(relpath, str)
        target = Path(relpath)
        if target.is_absolute():
            continue
        target = module_root / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("prompt\n", encoding="utf-8")


def _write_design_delta_work_item_runtime_adapter_scripts(tmp_path: Path) -> None:
    script_dir = tmp_path / "workflows" / "library" / "scripts"
    script_dir.mkdir(parents=True, exist_ok=True)
    _write_module(
        script_dir / "materialize_lisp_frontend_work_item_inputs.py",
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}",
                "selection_path = payload.get('selection_path', 'state/selection.json')",
                "selection = json.loads(Path(selection_path).read_text(encoding='utf-8')) if Path(selection_path).exists() else {}",
                "work_item_source = selection.get('work_item_source', 'DESIGN_GAP')",
                "work_item_id = selection.get('work_item_id', 'design-gap-work-item')",
                "check_commands_path = Path('state/runtime_work_item/check_commands.json')",
                "check_commands_path.parent.mkdir(parents=True, exist_ok=True)",
                "check_commands_path.write_text(json.dumps(['python -m pytest -q']) + '\\n', encoding='utf-8')",
                "context_path = Path('artifacts/work/runtime_work_item_context.md')",
                "context_path.parent.mkdir(parents=True, exist_ok=True)",
                "context_path.write_text('# work item context\\n', encoding='utf-8')",
                "bundle_path = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])",
                "bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                "bundle_path.write_text(json.dumps({",
                "  'work_item_source': work_item_source,",
                "  'work_item_id': work_item_id,",
                "  'work_item_context_path': context_path.as_posix(),",
                "  'check_commands_path': check_commands_path.as_posix(),",
                "  'plan_target_path': 'docs/plans/generated_plan.md',",
                "  'plan_phase_state_root': 'state/runtime_work_item/plan-phase',",
                "  'implementation_phase_state_root': 'state/runtime_work_item/implementation-phase',",
                "  'plan_review_report_target_path': 'artifacts/review/plan_review_report.md',",
                "  'execution_report_target_path': 'artifacts/work/execution_report.md',",
                "  'progress_report_target_path': 'artifacts/work/progress_report.md',",
                "  'checks_report_target_path': 'artifacts/checks/checks_report.md',",
                "  'implementation_review_report_target_path': 'artifacts/review/implementation_review_report.md',",
                "  'item_summary_pointer_path': 'artifacts/work/item_summary.json.pointer.txt',",
                "  'drain_status_path': 'state/runtime_work_item/drain_status.txt',",
                "  'item_summary_target_path': 'artifacts/work/item_summary.json'",
                "}) + '\\n', encoding='utf-8')",
            ]
        )
        + "\n",
    )
    _write_module(
        script_dir / "classify_lisp_frontend_work_item_terminal.py",
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "bundle_path = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])",
                "bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                "if Path('artifacts/work/progress_report.md').exists():",
                "    payload = {'route': 'IMPLEMENTATION_BLOCKED', 'terminal_route': 'IMPLEMENTATION_BLOCKED', 'block_reason': 'implementation_blocked', 'implementation_blocked': True, 'plan_review_exhausted': False, 'implementation_review_exhausted': False}",
                "else:",
                "    payload = {'route': 'COMPLETE', 'terminal_route': 'COMPLETE', 'block_reason': 'none', 'implementation_blocked': False, 'plan_review_exhausted': False, 'implementation_review_exhausted': False}",
                "bundle_path.write_text(json.dumps(payload) + '\\n', encoding='utf-8')",
            ]
        )
        + "\n",
    )
    _write_module(
        script_dir / "select_lisp_frontend_blocked_recovery_route.py",
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}",
                "bundle_path = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])",
                "bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                "route = payload.get('blocked_recovery_route', 'GAP_DESIGN_REVISION_REQUIRED')",
                "reason = payload.get('reason', 'implementation_blocked')",
                "bundle_path.write_text(json.dumps({'variant': route, 'reason': reason}) + '\\n', encoding='utf-8')",
            ]
        )
        + "\n",
    )
    _write_module(
        script_dir / "validate_lisp_frontend_design_gap_architecture.py",
        "\n".join(
            [
                "import argparse",
                "import json",
                "import os",
                "from pathlib import Path",
                "",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--draft-bundle-path', required=True)",
                "parser.add_argument('--architecture-targets-path')",
                "parser.add_argument('--output', required=True)",
                "args = parser.parse_args()",
                "output = Path(args.output)",
                "output.parent.mkdir(parents=True, exist_ok=True)",
                "output.write_text(json.dumps({",
                "  'architecture_validation_status': 'VALID',",
                "  'work_item_bundle_path': args.output",
                "}) + '\\n', encoding='utf-8')",
                "bundle_path = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])",
                "bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                "bundle_path.write_text(json.dumps({",
                "  'architecture_validation_status': 'VALID',",
                "  'work_item_bundle_path': args.output",
                "}) + '\\n', encoding='utf-8')",
            ]
        )
        + "\n",
    )
    _write_module(
        script_dir / "update_lisp_frontend_run_state.py",
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}",
                "state_path = payload.get('run_state_path', 'state/run_state.json')",
                "item_id = payload.get('work_item_id', 'design-gap-work-item')",
                "work_item_source = payload.get('work_item_source', 'DESIGN_GAP')",
                "reason = payload.get('reason', 'completed')",
                "summary_path = payload.get('item_summary_target_path', 'artifacts/work/item_summary.json')",
                "pointer_path = payload.get('item_summary_pointer_path', summary_path + '.pointer.txt')",
                "drain_status_path = payload.get('drain_status_path', 'state/runtime_work_item/drain_status.txt')",
                "summary = Path(summary_path)",
                "summary.parent.mkdir(parents=True, exist_ok=True)",
                "summary.write_text(json.dumps({'summary': summary_path, 'reason': reason}) + '\\n', encoding='utf-8')",
                "pointer = Path(pointer_path)",
                "pointer.parent.mkdir(parents=True, exist_ok=True)",
                "pointer.write_text(summary_path + '\\n', encoding='utf-8')",
                "drain_status = Path(drain_status_path)",
                "drain_status.parent.mkdir(parents=True, exist_ok=True)",
                "drain_status.write_text('UPDATED\\n', encoding='utf-8')",
                "state = Path(state_path)",
                "state.parent.mkdir(parents=True, exist_ok=True)",
                "state_payload = json.loads(state.read_text(encoding='utf-8')) if state.exists() else {}",
                "state_payload['terminal_reason'] = reason",
                "state_payload['terminal_summary'] = summary_path",
                "state.write_text(json.dumps(state_payload) + '\\n', encoding='utf-8')",
                "bundle_path_raw = os.environ.get('ORCHESTRATOR_OUTPUT_BUNDLE_PATH', '').strip()",
                "if bundle_path_raw:",
                "    bundle_path = Path(bundle_path_raw)",
                "    bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                "    bundle_path.write_text(json.dumps({'reason': reason, 'summary_path': summary_path}) + '\\n', encoding='utf-8')",
            ]
        )
        + "\n",
    )
    _write_module(
        script_dir / "record_lisp_frontend_blocked_recovery_outcome.py",
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}",
                "state_path = payload.get('run_state_path', 'state/run_state.json')",
                "summary_path = payload.get('summary_path', 'artifacts/work/item_summary.json')",
                "progress_report = payload.get('progress_report_path', 'artifacts/work/progress_report.md')",
                "pointer_path = payload.get('summary_pointer_path', summary_path + '.pointer.txt')",
                "reason = payload.get('reason', 'implementation_architecture_under_scoped')",
                "summary = Path(summary_path)",
                "summary.parent.mkdir(parents=True, exist_ok=True)",
                "summary.write_text(json.dumps({'summary': summary_path, 'progress_report': progress_report}) + '\\n', encoding='utf-8')",
                "pointer = Path(pointer_path)",
                "pointer.parent.mkdir(parents=True, exist_ok=True)",
                "pointer.write_text(summary_path + '\\n', encoding='utf-8')",
                "state = Path(state_path)",
                "state.parent.mkdir(parents=True, exist_ok=True)",
                "state_payload = json.loads(state.read_text(encoding='utf-8')) if state.exists() else {}",
                "state_payload['blocked_recovery_reason'] = reason",
                "state_payload['blocked_recovery_summary'] = summary_path",
                "state.write_text(json.dumps(state_payload) + '\\n', encoding='utf-8')",
                "bundle_path_raw = os.environ.get('ORCHESTRATOR_OUTPUT_BUNDLE_PATH', '').strip()",
                "if bundle_path_raw:",
                "    bundle_path = Path(bundle_path_raw)",
                "    bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                "    bundle_path.write_text(json.dumps({'reason': reason, 'summary_path': summary_path}) + '\\n', encoding='utf-8')",
            ]
        )
        + "\n",
    )
    _write_module(
        script_dir / "write_lisp_frontend_drain_status.py",
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}",
                "state_path = payload.get('run_state_path', 'state/run_state.json')",
                "status = payload.get('status', 'DONE')",
                "reason = payload.get('reason', '')",
                "summary_path = payload.get('summary_path', 'artifacts/work/drain_summary.json')",
                "summary = Path(summary_path)",
                "summary.parent.mkdir(parents=True, exist_ok=True)",
                "summary.write_text(json.dumps({'status': status, 'reason': reason}) + '\\n', encoding='utf-8')",
                "state = Path(state_path)",
                "state.parent.mkdir(parents=True, exist_ok=True)",
                "state_payload = json.loads(state.read_text(encoding='utf-8')) if state.exists() else {}",
                "state_payload['drain_status'] = status",
                "state_payload['drain_status_reason'] = reason",
                "state_payload['drain_status_summary'] = summary_path",
                "state_payload.setdefault('history', []).append({'event': 'drain_status', 'status': status, 'reason': reason, 'summary_path': summary_path})",
                "state.write_text(json.dumps(state_payload) + '\\n', encoding='utf-8')",
                "bundle_path_raw = os.environ.get('ORCHESTRATOR_OUTPUT_BUNDLE_PATH', '').strip()",
                "if bundle_path_raw:",
                "    bundle_path = Path(bundle_path_raw)",
                "    bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                "    bundle_path.write_text(json.dumps({'status': status, 'summary_path': summary_path}) + '\\n', encoding='utf-8')",
            ]
        )
        + "\n",
    )
    _write_module(
        script_dir / "finalize_lisp_frontend_drain_summary.py",
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "summary_path = sys.argv[1]",
                "summary = Path(summary_path)",
                "summary.parent.mkdir(parents=True, exist_ok=True)",
                "if not summary.exists():",
                "    summary.write_text(json.dumps({'status': 'DONE'}) + '\\n', encoding='utf-8')",
                "bundle_path_raw = os.environ.get('ORCHESTRATOR_OUTPUT_BUNDLE_PATH', '').strip()",
                "if bundle_path_raw:",
                "    bundle_path = Path(bundle_path_raw)",
                "    bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                "    bundle_path.write_text(json.dumps({'summary': summary_path}) + '\\n', encoding='utf-8')",
            ]
        )
        + "\n",
    )
    for script_name in ("project_lisp_frontend_selector_action.py",):
        _write_module(
            script_dir / script_name,
            (REPO_ROOT / "workflows" / "library" / "scripts" / script_name).read_text(
                encoding="utf-8"
            ),
        )


def _write_design_delta_work_item_runtime_inputs(
    tmp_path: Path,
    *,
    work_item_source: str,
    work_item_id: str = "design-gap-work-item",
) -> None:
    normalized_source = "DESIGN_GAP" if work_item_source == "DRAFT_DESIGN_GAP" else work_item_source
    for relpath, contents in {
        "docs/design/target.md": "# target\n",
        "docs/design/baseline.md": "# baseline\n",
        "docs/design/workflow_command_adapter_contract.md": "# command adapter contract\n",
        "docs/steering.md": "# steering\n",
        "docs/plans/generated_plan.md": "# generated plan\n",
        "docs/plans/generated_architecture.md": "# generated architecture\n",
        "state/check_commands.json": json.dumps(["python -m pytest -q"]) + "\n",
        "state/progress_ledger.json": json.dumps({"events": []}) + "\n",
        "state/run_state.json": json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        "state/selection.json": json.dumps(
            {"work_item_source": normalized_source, "work_item_id": work_item_id}
        )
        + "\n",
        "state/manifest.json": json.dumps({"items": []}) + "\n",
        "state/architecture_validation.json": json.dumps({"architecture_validation_status": "VALID"}) + "\n",
        "state/branching_terminal_reprojection/final_plan_gate_state.json": (
            json.dumps({"gate": "ready"}) + "\n"
        ),
        "artifacts/work/selection_bundle.md": "# selection bundle\n",
        "artifacts/work/runtime_work_item_context.md": "# work item context\n",
        "artifacts/work/existing_architecture_index.md": "# existing architectures\n",
        "artifacts/work/section14-parent-dry-run/work_item_context.md": "# work item context\n",
        "artifacts/work/section14-parent-dry-run/existing-architecture-index.md": "# existing architectures\n",
    }.items():
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")


def _design_delta_work_item_bound_inputs() -> dict[str, object]:
    return {
        "work_item_bootstrap__work_item_source": "DESIGN_GAP",
        "work_item_bootstrap__work_item_id": "design-gap-work-item",
        "work_item_bootstrap__plan_target_path": "docs/plans/generated_plan.md",
        "work_item_bootstrap__check_commands__commands": ["python -m pytest -q"],
        "work_item_bootstrap__selection_bundle_path": "state/selection.json",
        "work_item_bootstrap__architecture_path": "docs/plans/generated_architecture.md",
        "steering_path": "docs/steering.md",
        "target_design_path": "docs/design/target.md",
        "baseline_design_path": "docs/design/baseline.md",
        "progress_ledger_path": "state/progress_ledger.json",
        "run_state_path": "state/run_state.json",
    }


def _design_delta_item_ctx_child_phase_reuse_bound_inputs() -> dict[str, object]:
    return {
        "work_item_bootstrap__work_item_source": "DESIGN_GAP",
        "work_item_bootstrap__work_item_id": "design-gap-work-item",
        "work_item_bootstrap__plan_target_path": "docs/plans/generated_plan.md",
        "work_item_bootstrap__check_commands__commands": ["python -m pytest -q"],
        "work_item_bootstrap__architecture_path": "docs/plans/generated_architecture.md",
        "steering_path": "docs/steering.md",
        "target_design_path": "docs/design/target.md",
        "baseline_design_path": "docs/design/baseline.md",
        "progress_ledger_path": "state/progress_ledger.json",
    }


def _design_delta_item_ctx_child_phase_reuse_branching_bound_inputs() -> dict[str, object]:
    return {
        **_design_delta_item_ctx_child_phase_reuse_bound_inputs(),
        "run_state_path": "state/run_state.json",
    }


def _design_delta_parent_drain_bound_inputs() -> dict[str, str]:
    return {
        "steering_path": "docs/steering.md",
        "target_design_path": "docs/design/target.md",
        "baseline_design_path": "docs/design/baseline.md",
        "manifest_path": "state/manifest.json",
        "progress_ledger_path": "state/progress_ledger.json",
        "architecture_bundle_path": "state/architecture_validation.json",
        "architecture_targets__design_gap_id": "design-gap-work-item",
        "architecture_targets__architecture_path": "docs/plans/generated_architecture.md",
        "architecture_targets__work_item_context_path": "artifacts/work/runtime_work_item_context.md",
        "architecture_targets__check_commands_path": "state/check_commands.json",
        "architecture_targets__plan_target_path": "docs/plans/generated_plan.md",
        "existing_architecture_index_path": "artifacts/work/existing_architecture_index.md",
    }


def _design_delta_parent_drain_public_input_only_bound_inputs() -> dict[str, str]:
    return {
        "steering_path": "docs/steering.md",
        "target_design_path": "docs/design/target.md",
        "baseline_design_path": "docs/design/baseline.md",
        "architecture_targets__design_gap_id": "design-gap-work-item",
        "architecture_targets__architecture_path": "docs/plans/generated_architecture.md",
        "architecture_targets__work_item_context_path": (
            "artifacts/work/section14-parent-dry-run/work_item_context.md"
        ),
        "architecture_targets__check_commands_path": "state/check_commands.json",
        "architecture_targets__plan_target_path": "docs/plans/generated_plan.md",
        "existing_architecture_index_path": (
            "artifacts/work/section14-parent-dry-run/existing-architecture-index.md"
        ),
    }


def _design_delta_parent_drain_controlled_smoke_bound_inputs() -> dict[str, object]:
    return {
        **_design_delta_parent_drain_bound_inputs(),
        "run_state_path": "state/run_state.json",
        "item-ctx__state-root": "state/item",
        "phase-ctx__plan__run__run-id": "work-item-approved",
        "phase-ctx__implementation__run__run-id": "work-item-approved",
        "phase-ctx__work-item__phase-name": "work-item",
        "phase-ctx__work-item__state-root": "state/work-item",
        "phase-ctx__work-item__artifact-root": "artifacts/work-item",
    }


def _native_drain_run_state(workspace: Path, workflow_slug: str) -> dict[str, object]:
    """Read the state-layout-backed drain-run-state record for a lowered workflow."""
    payload = json.loads(
        (
            workspace
            / "state"
            / "workflow_lisp"
            / workflow_slug
            / "drain-run-state-state.json"
        ).read_text(encoding="utf-8")
    )
    state = payload["state"]
    assert isinstance(state, dict)
    return state


def _execute_design_delta_work_item_route(
    tmp_path: Path,
    *,
    plan_variant: str,
    implementation_variant: str,
    work_item_source: str,
    recovery_route: str = "GAP_DESIGN_REVISION_REQUIRED",
    recovery_reason: str = "implementation_architecture_under_scoped",
    review_sequence: tuple[str, ...] = ("APPROVE",),
    materialized_work_item_source_override: str | None = None,
    plan_review_decision_override: str | None = None,
    implementation_state_override: str | None = None,
    blocked_recovery_route_override: str | None = None,
    blocked_recovery_reason_override: str | None = None,
):
    workflow_path, result = _compile_design_delta_work_item_runtime_entrypoint(
        tmp_path,
        plan_review_decision_override=plan_review_decision_override,
        implementation_state_override=implementation_state_override,
    )
    bundle = result.entry_result.validated_bundles[
        "lisp_frontend_design_delta/work_item::run-work-item"
    ]
    return _execute_design_delta_work_item_bundle(
        tmp_path,
        workflow_path=workflow_path,
        bundle=bundle,
        bound_inputs=_design_delta_work_item_bound_inputs(),
        plan_variant=plan_variant,
        implementation_variant=implementation_variant,
        work_item_source=work_item_source,
        recovery_route=recovery_route,
        recovery_reason=recovery_reason,
        review_sequence=review_sequence,
        materialized_work_item_source_override=materialized_work_item_source_override,
        plan_review_decision_override=plan_review_decision_override,
        implementation_state_override=implementation_state_override,
        blocked_recovery_route_override=blocked_recovery_route_override,
        blocked_recovery_reason_override=blocked_recovery_reason_override,
    )


def _design_delta_selected_item_stdlib_bound_inputs() -> dict[str, object]:
    return {
        "item-ctx__run__run-id": "selected-item-stdlib",
        "item-ctx__run__state-root": "state/run",
        "item-ctx__run__artifact-root": "artifacts/run",
        "item-ctx__item-id": "design-gap-work-item",
        "item-ctx__state-root": "state/item",
        "item-ctx__artifact-root": "artifacts/item",
        "item-ctx__ledger": "state/progress_ledger.json",
        "selection__item-id": "design-gap-work-item",
        "selection__item-state-root": "state/item",
        "selection__work_item_bootstrap__work_item_source": "DESIGN_GAP",
        "selection__work_item_bootstrap__work_item_id": "design-gap-work-item",
        "selection__work_item_bootstrap__plan_target_path": "docs/plans/generated_plan.md",
        "selection__work_item_bootstrap__check_commands__commands": [
            "python -m pytest -q"
        ],
        "selection__work_item_bootstrap__architecture_path": (
            "docs/plans/generated_architecture.md"
        ),
        "selection__steering_path": "docs/steering.md",
        "selection__target_design_path": "docs/design/target.md",
        "selection__baseline_design_path": "docs/design/baseline.md",
        "selection__progress_ledger_path": "state/progress_ledger.json",
    }


def _execute_design_delta_selected_item_stdlib_route(
    tmp_path: Path,
    *,
    plan_variant: str,
    implementation_variant: str,
    work_item_source: str,
    recovery_route: str = "GAP_DESIGN_REVISION_REQUIRED",
    recovery_reason: str = "implementation_architecture_under_scoped",
    review_sequence: tuple[str, ...] = ("APPROVE",),
):
    workflow_path, result = _compile_design_delta_work_item_runtime_entrypoint(tmp_path)
    bundle = result.entry_result.validated_bundles[
        "lisp_frontend_design_delta/work_item::run-selected-item-stdlib"
    ]
    return _execute_design_delta_work_item_bundle(
        tmp_path,
        workflow_path=workflow_path,
        bundle=bundle,
        bound_inputs=_design_delta_selected_item_stdlib_bound_inputs(),
        plan_variant=plan_variant,
        implementation_variant=implementation_variant,
        work_item_source=work_item_source,
        recovery_route=recovery_route,
        recovery_reason=recovery_reason,
        review_sequence=review_sequence,
        run_id="selected-item-stdlib",
    )


def _execute_design_delta_work_item_bundle(
    tmp_path: Path,
    *,
    workflow_path: Path,
    bundle,
    bound_inputs: dict[str, object],
    plan_variant: str,
    implementation_variant: str,
    work_item_source: str,
    selector_status: str | tuple[str, ...] = "SELECT_BACKLOG_ITEM",
    recovery_route: str = "GAP_DESIGN_REVISION_REQUIRED",
    recovery_reason: str = "implementation_architecture_under_scoped",
    review_sequence: tuple[str, ...] = ("APPROVE",),
    materialized_work_item_source_override: str | None = None,
    plan_review_decision_override: str | None = None,
    implementation_state_override: str | None = None,
    blocked_recovery_route_override: str | None = None,
    blocked_recovery_reason_override: str | None = None,
    provider_failure: tuple[str, int] | None = None,
    run_id: str | None = None,
    work_item_id: str = "design-gap-work-item",
    selector_mode: str = "tuple",
    selector_observations: list[dict[str, object]] | None = None,
    patch_child_runtime_bindings: bool = True,
):

    _write_design_delta_work_item_runtime_prompt_assets(tmp_path / "lisp_frontend_design_delta")
    _write_design_delta_work_item_runtime_prompt_assets(tmp_path)
    _write_design_delta_runtime_run_checks_script(tmp_path)
    _write_design_delta_work_item_runtime_adapter_scripts(tmp_path)
    _write_design_delta_work_item_runtime_inputs(
        tmp_path,
        work_item_source=(
            materialized_work_item_source_override
            if materialized_work_item_source_override is not None
            else work_item_source
        ),
        work_item_id=work_item_id,
    )
    provider_calls: list[str] = []
    provider_invocation_counts: dict[str, int] = {}
    review_index = 0
    selector_index = 0

    def _prepare_invocation(
        _self,
        provider_name=None,
        params=None,
        context=None,
        prompt_content=None,
        env=None,
        **_kwargs,
    ):
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=prompt_content or "",
                env=env or {},
                provider_name=provider_name,
                context=dict(context or {}),
                params=getattr(params, "params", None),
            ),
            None,
        )

    def _execute_provider(_self, invocation, **_kwargs):
        nonlocal review_index, selector_index
        provider_calls.append(invocation.provider_name)
        provider_invocation_counts[invocation.provider_name] = (
            provider_invocation_counts.get(invocation.provider_name, 0) + 1
        )
        if (
            provider_failure is not None
            and invocation.provider_name == provider_failure[0]
            and provider_invocation_counts[invocation.provider_name] == provider_failure[1]
        ):
            raise RuntimeError(
                f"synthetic provider failure: {invocation.provider_name}:{provider_failure[1]}"
            )
        bundle_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)

        if invocation.provider_name == "fake-selector":
            if selector_mode == "state_driven_design_gap":
                # The legacy run-state carrier is retired: recorded design-gap
                # progress is durable only through the state-layout-backed
                # `drain-run-state` resource. Drive the selector decision from
                # that typed record so convergence proves the runtime-native
                # progress channel.
                native_state_root = tmp_path / "state" / "workflow_lisp"
                progress_files = (
                    sorted(native_state_root.rglob("drain-run-state-state.json"))
                    if native_state_root.is_dir()
                    else []
                )
                completed_design_gaps: list[str] = []
                observed_state_path: str | None = None
                for progress_file in progress_files:
                    progress_payload = json.loads(progress_file.read_text(encoding="utf-8"))
                    recorded = progress_payload.get("state", {}).get("completed_design_gaps")
                    if recorded:
                        completed_design_gaps = list(recorded)
                        observed_state_path = progress_file.relative_to(tmp_path).as_posix()
                current_selector_status = (
                    "DONE" if work_item_id in completed_design_gaps else "DRAFT_DESIGN_GAP"
                )
                if selector_observations is not None:
                    selector_observations.append(
                        {
                            "binding_key": "resource.drain-run-state.state_path",
                            "bound_run_state_path": observed_state_path,
                            "completed_design_gaps": completed_design_gaps,
                            "decision": current_selector_status,
                            "forced_tuple": False,
                        }
                    )
            else:
                current_selector_status = (
                    selector_status[min(selector_index, len(selector_status) - 1)]
                    if isinstance(selector_status, tuple)
                    else selector_status
                )
            selector_index += 1
            if current_selector_status not in {
                "SELECT_BACKLOG_ITEM",
                "DRAFT_DESIGN_GAP",
                "DONE",
                "BLOCKED",
            }:
                raise AssertionError(f"unexpected selector status: {current_selector_status}")
            selector_variant = (
                "SELECTED_ITEM"
                if current_selector_status == "SELECT_BACKLOG_ITEM"
                else current_selector_status
            )
            normalized_source = (
                "DESIGN_GAP" if work_item_source == "DRAFT_DESIGN_GAP" else work_item_source
            )
            selector_payload = {
                "selection_status": current_selector_status,
                "selection_bundle_path": "state/selection.json",
                "work_item_bootstrap": {
                    "work_item_source": normalized_source,
                    "work_item_id": work_item_id,
                    "plan_target_path": "docs/plans/generated_plan.md",
                    "check_commands": {
                        "commands": ["python -m pytest -q"],
                    },
                    "selection_bundle_path": "state/selection.json",
                    "architecture_path": "docs/plans/generated_architecture.md",
                },
                "is_selected": selector_variant == "SELECTED_ITEM",
                "is_design_gap": selector_variant == "DRAFT_DESIGN_GAP",
                "is_done": selector_variant == "DONE",
                "is_blocked": selector_variant == "BLOCKED",
                "blocked_reason": "selector_blocked" if selector_variant == "BLOCKED" else "",
            }
            bundle_path.write_text(
                json.dumps(selector_payload)
                + "\n",
                encoding="utf-8",
            )
            return _success_provider_result()
        if invocation.provider_name == "fake-architect-draft":
            draft_path = tmp_path / "docs" / "plans" / "generated_architecture.md"
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text("# generated architecture\n", encoding="utf-8")
            bundle_path.write_text(
                json.dumps(
                    {
                        "draft_status": "DRAFTED",
                        "draft_bundle": "artifacts/work/draft_architecture_bundle.json",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return _success_provider_result()
        if invocation.provider_name == "fake-plan-draft":
            plan_path = tmp_path / "docs" / "plans" / "generated_plan.md"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text("# generated plan\n", encoding="utf-8")
            bundle_path.write_text(
                json.dumps({"plan_path": "docs/plans/generated_plan.md"}) + "\n",
                encoding="utf-8",
            )
            return _success_provider_result()
        if invocation.provider_name == "fake-plan-review":
            review_report = tmp_path / "artifacts" / "review" / "plan_review_report.md"
            review_report.parent.mkdir(parents=True, exist_ok=True)
            review_report.write_text("# plan review\n", encoding="utf-8")
            findings_path = tmp_path / "artifacts" / "work" / "plan_findings.json"
            findings_path.parent.mkdir(parents=True, exist_ok=True)
            findings_path.write_text(
                json.dumps({"schema_version": "ReviewFindings.v1", "items": []}) + "\n",
                encoding="utf-8",
            )
            if plan_review_decision_override is not None:
                plan_path = tmp_path / "docs" / "plans" / "generated_plan.md"
                plan_path.parent.mkdir(parents=True, exist_ok=True)
                plan_path.write_text("# generated plan\n", encoding="utf-8")
                bundle_path.write_text(
                    json.dumps(
                        {
                            "variant": "APPROVED",
                            "approved_plan_path": "docs/plans/generated_plan.md",
                            "approved_plan_review_report_path": "artifacts/review/plan_review_report.md",
                            "plan_review_decision": plan_review_decision_override,
                            "findings": {
                                "schema_version": "ReviewFindings.v1",
                                "items_path": "artifacts/work/plan_findings.json",
                            },
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return _success_provider_result()
            if plan_variant == "APPROVED":
                payload = {
                    "variant": "APPROVE",
                    "review_report": "artifacts/review/plan_review_report.md",
                    "review_decision": plan_review_decision_override or "APPROVE",
                    "findings": {
                        "schema_version": "ReviewFindings.v1",
                        "items_path": "artifacts/work/plan_findings.json",
                    },
                }
            elif plan_variant == "BLOCKED":
                payload = {
                    "variant": "BLOCKED",
                    "review_report": "artifacts/review/plan_review_report.md",
                    "blocker_class": "roadmap_conflict",
                    "findings": {
                        "schema_version": "ReviewFindings.v1",
                        "items_path": "artifacts/work/plan_findings.json",
                    },
                }
            else:
                payload = {
                    "variant": "EXHAUSTED",
                    "last_review_report": "artifacts/review/plan_review_report.md",
                    "reason": "review_exhausted",
                    "findings": {
                        "schema_version": "ReviewFindings.v1",
                        "items_path": "artifacts/work/plan_findings.json",
                    },
                }
            bundle_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            return _success_provider_result()
        if invocation.provider_name == "fake-plan-fix":
            bundle_path.write_text(
                json.dumps({"plan_path": "docs/plans/generated_plan.md"}) + "\n",
                encoding="utf-8",
            )
            return _success_provider_result()
        if invocation.provider_name == "fake-implementation-execute":
            if implementation_state_override is not None:
                execution_report = tmp_path / "artifacts" / "work" / "execution_report.md"
                execution_report.parent.mkdir(parents=True, exist_ok=True)
                execution_report.write_text("# execution report\n", encoding="utf-8")
                bundle_path.write_text(
                    json.dumps(
                        {
                            "variant": "COMPLETED",
                            "implementation_state": implementation_state_override,
                            "execution_report": "artifacts/work/execution_report.md",
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return _success_provider_result()
            if implementation_variant == "COMPLETED":
                execution_report = tmp_path / "artifacts" / "work" / "execution_report.md"
                execution_report.parent.mkdir(parents=True, exist_ok=True)
                execution_report.write_text("# execution report\n", encoding="utf-8")
                payload = {
                    "variant": "COMPLETED",
                    "implementation_state": implementation_state_override or "COMPLETED",
                    "execution_report": "artifacts/work/execution_report.md",
                }
            else:
                progress_report = tmp_path / "artifacts" / "work" / "progress_report.md"
                progress_report.parent.mkdir(parents=True, exist_ok=True)
                progress_report.write_text("# blocked progress\n", encoding="utf-8")
                payload = {
                    "variant": "BLOCKED",
                    "implementation_state": "BLOCKED",
                    "implementation_review_decision": "NOT_APPLICABLE",
                    "progress_report": "artifacts/work/progress_report.md",
                    "blocker_class": "external_dependency_outside_authority",
                }
            bundle_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            return _success_provider_result()
        if invocation.provider_name == "fake-implementation-review":
            review_variant = review_sequence[min(review_index, len(review_sequence) - 1)]
            review_report = tmp_path / "artifacts" / "review" / "implementation_review_report.md"
            review_report.parent.mkdir(parents=True, exist_ok=True)
            review_report.write_text(f"# implementation review {review_index}\n", encoding="utf-8")
            findings_path = tmp_path / "artifacts" / "work" / "implementation_findings.json"
            findings_path.parent.mkdir(parents=True, exist_ok=True)
            findings_path.write_text(
                json.dumps({"schema_version": "ReviewFindings.v1", "items": []}) + "\n",
                encoding="utf-8",
            )
            review_index += 1
            bundle_path.write_text(
                json.dumps(
                    {
                        "variant": review_variant,
                        "review_report": "artifacts/review/implementation_review_report.md",
                        "findings": {
                            "schema_version": "ReviewFindings.v1",
                            "items_path": "artifacts/work/implementation_findings.json",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return _success_provider_result()
        if invocation.provider_name == "fake-implementation-fix":
            fixed_report = tmp_path / "artifacts" / "work" / "execution_report_fixed.md"
            fixed_report.parent.mkdir(parents=True, exist_ok=True)
            fixed_report.write_text("# fixed execution report\n", encoding="utf-8")
            bundle_path.write_text(
                json.dumps(
                    {
                        "execution_report": "artifacts/work/execution_report_fixed.md",
                        "checks_report": "artifacts/checks/checks_report.md",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return _success_provider_result()
        if invocation.provider_name == "fake-work-item-recovery":
            bundle_path.write_text(
                json.dumps(
                    {
                        "blocked_recovery_route": blocked_recovery_route_override or recovery_route,
                        "reason": blocked_recovery_reason_override or recovery_reason,
                        "summary": "design-gap recovery requested",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return _success_provider_result()
        raise AssertionError(f"unexpected provider call: {invocation.provider_name}")

    original_resolve_bound_inputs = CallExecutor.resolve_bound_inputs

    def _resolve_bound_inputs(self, step, imported_workflow, state, **kwargs):
        bound_inputs, error = original_resolve_bound_inputs(
            self,
            step,
            imported_workflow,
            state,
            **kwargs,
        )
        if error is not None or bound_inputs is None:
            return bound_inputs, error
        workflow_name = getattr(getattr(imported_workflow, "surface", None), "name", None)
        rebound_inputs = dict(_rewrite_managed_write_root_bindings_for_smoke(bound_inputs))
        if workflow_name == "lisp_frontend_design_delta/plan_phase::run-plan-phase":
            rebound_inputs.update(
                {
                    "phase-ctx__phase-name": "plan",
                    "phase-ctx__state-root": "state/plan",
                    "phase-ctx__artifact-root": "artifacts/plan",
                }
            )
        elif workflow_name == "lisp_frontend_design_delta/implementation_phase::implementation-phase":
            rebound_inputs.update(
                {
                    "phase-ctx__phase-name": "implementation",
                    "phase-ctx__state-root": "state/implementation",
                    "phase-ctx__artifact-root": "artifacts/implementation",
                }
            )
        return rebound_inputs, None

    state_manager = StateManager(
        workspace=tmp_path,
        run_id=run_id or f"work-item-{plan_variant.lower()}",
    )
    state_manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )

    previous_cwd = Path.cwd()
    smoke_pythonpath = os.pathsep.join(
        [str(REPO_ROOT), *filter(None, [os.environ.get("PYTHONPATH")])]
    )
    os.chdir(tmp_path)
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"PYTHONPATH": smoke_pythonpath}))
            stack.enter_context(
                patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation)
            )
            stack.enter_context(patch.object(ProviderExecutor, "execute", _execute_provider))
            if patch_child_runtime_bindings:
                stack.enter_context(
                    patch.object(CallExecutor, "resolve_bound_inputs", _resolve_bound_inputs)
                )
            try:
                state = WorkflowExecutor(
                    bundle,
                    tmp_path,
                    state_manager,
                    retry_delay_ms=0,
                ).execute(on_error="stop")
            except RuntimeError:
                if provider_failure is None:
                    raise
                state = state_manager.load().to_dict()
    finally:
        os.chdir(previous_cwd)

    return tmp_path, state, provider_calls


def _execute_design_delta_parent_call_work_item_route(
    tmp_path: Path,
    *,
    plan_variant: str,
    implementation_variant: str,
    work_item_source: str,
    recovery_route: str = "GAP_DESIGN_REVISION_REQUIRED",
    recovery_reason: str = "implementation_architecture_under_scoped",
    review_sequence: tuple[str, ...] = ("APPROVE",),
):
    workflow_path, result, _lowered_by_name = _compile_design_delta_parent_call_work_item_entrypoint(tmp_path)
    bundle = result.entry_result.validated_bundles[
        "design_delta_parent_calls_work_item::run-parent-work-item"
    ]
    _write_design_delta_work_item_runtime_prompt_assets(tmp_path / "lisp_frontend_design_delta")
    _write_design_delta_work_item_runtime_prompt_assets(tmp_path)
    _write_design_delta_runtime_run_checks_script(tmp_path)
    _write_design_delta_work_item_runtime_adapter_scripts(tmp_path)
    _write_design_delta_work_item_runtime_inputs(tmp_path, work_item_source=work_item_source)
    return _execute_design_delta_work_item_bundle(
        tmp_path,
        workflow_path=workflow_path,
        bundle=bundle,
        bound_inputs=_design_delta_work_item_bound_inputs(),
        plan_variant=plan_variant,
        implementation_variant=implementation_variant,
        work_item_source=work_item_source,
        recovery_route=recovery_route,
        recovery_reason=recovery_reason,
        review_sequence=review_sequence,
    )


def _execute_design_delta_parent_drain_route(
    tmp_path: Path,
    *,
    plan_variant: str,
    implementation_variant: str,
    work_item_source: str,
    selector_status: str | tuple[str, ...] = "SELECT_BACKLOG_ITEM",
    recovery_route: str = "GAP_DESIGN_REVISION_REQUIRED",
    recovery_reason: str = "implementation_architecture_under_scoped",
    review_sequence: tuple[str, ...] = ("APPROVE",),
    provider_failure: tuple[str, int] | None = None,
    run_id: str | None = None,
    work_item_id: str = "design-gap-work-item",
    selector_mode: str = "tuple",
    selector_observations: list[dict[str, object]] | None = None,
):
    workflow_path, result, _lowered_by_name = _compile_design_delta_parent_drain_runtime_entrypoint(
        tmp_path
    )
    bundle = result.entry_result.validated_bundles["lisp_frontend_design_delta/drain::drain"]
    return _execute_design_delta_work_item_bundle(
        tmp_path,
        workflow_path=workflow_path,
        bundle=bundle,
        bound_inputs=_design_delta_parent_drain_controlled_smoke_bound_inputs(),
        plan_variant=plan_variant,
        implementation_variant=implementation_variant,
        work_item_source=work_item_source,
        selector_status=selector_status,
        recovery_route=recovery_route,
        recovery_reason=recovery_reason,
        review_sequence=review_sequence,
        provider_failure=provider_failure,
        run_id=run_id,
        work_item_id=work_item_id,
        selector_mode=selector_mode,
        selector_observations=selector_observations,
        patch_child_runtime_bindings=False,
    )


def _execute_design_delta_runtime_transition_fixture(tmp_path: Path):
    _result, bundle = _compile_design_delta_runtime_transition_fixture_entrypoint(tmp_path)
    run_state_path = tmp_path / "state" / "run_state.json"
    summary_path = tmp_path / "artifacts" / "work" / "drain_summary.json"
    run_state_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    run_state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps({"status": "BLOCKED", "reason": "runtime_native_fixture"}) + "\n",
        encoding="utf-8",
    )

    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    provided_inputs: dict[str, str] = {
        "summary_path": "artifacts/work/drain_summary.json",
    }
    binding_inputs = {
        input_name: spec
        for input_name, spec in runtime_inputs.items()
        if not (isinstance(input_name, str) and input_name.startswith("__write_root__"))
    }
    run_id = "design-delta-runtime-transition-fixture"
    bound_inputs = bind_workflow_inputs(
        binding_inputs,
        provided_inputs,
        tmp_path,
    )
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize(
        DESIGN_DELTA_RUNTIME_TRANSITION_FIXTURE.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="stop")
    step = bundle.surface.steps[0]
    native_state_path = tmp_path / step.resource_transition["resource"]["state_path"]
    audit_path = tmp_path / step.resource_transition["resource"]["audit_path"]
    return tmp_path, state, native_state_path, audit_path


def _execute_design_delta_runtime_view_fixture(tmp_path: Path):
    _result, bundle, lowered = _compile_design_delta_runtime_view_fixture_entrypoint(tmp_path)
    run_state_path = tmp_path / "state" / "run_state.json"
    summary_path = tmp_path / "artifacts" / "work" / "drain_summary.json"
    pointer_path = tmp_path / "artifacts" / "work" / "drain_summary_path.txt"
    run_state_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    run_state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    provided_inputs: dict[str, str] = {
        "drain_status": "BLOCKED",
        "drain_status_reason": "runtime_native_fixture",
        "summary_path": "artifacts/work/drain_summary.json",
        "pointer_path": "artifacts/work/drain_summary_path.txt",
    }
    binding_inputs = {
        input_name: spec
        for input_name, spec in runtime_inputs.items()
        if not (isinstance(input_name, str) and input_name.startswith("__write_root__"))
    }
    run_id = "design-delta-runtime-view-fixture"
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize(
        DESIGN_DELTA_RUNTIME_VIEW_FIXTURE.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bind_workflow_inputs(binding_inputs, provided_inputs, tmp_path),
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="stop")
    transition_bundle = bundle.imports[
        "lisp_frontend_design_delta/transitions::emit-drain-status-transition-audit"
    ]
    transition_resource = transition_bundle.surface.steps[0].resource_transition["resource"]
    native_state_path = tmp_path / transition_resource["state_path"]
    audit_path = tmp_path / transition_resource["audit_path"]
    return (
        tmp_path,
        state,
        bundle,
        lowered,
        summary_path,
        pointer_path,
        native_state_path,
        audit_path,
    )


def _build_module():
    return importlib.import_module("orchestrator.workflow_lisp.build")


def test_design_delta_migration_nested_library_import_layout_compiles(tmp_path: Path) -> None:
    package_dir = tmp_path / "lisp_frontend_design_delta"
    _write_module(
        package_dir / "types.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule lisp_frontend_design_delta/types)",
                "  (export WorkReport SelectionResult)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord SelectionResult",
                "    (status String)",
                "    (report WorkReport)))",
            ]
        )
        + "\n",
    )
    _write_module(
        package_dir / "selector.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule lisp_frontend_design_delta/selector)",
                "  (import lisp_frontend_design_delta/types :only (WorkReport SelectionResult))",
                "  (export select-next-work)",
                "  (defworkflow select-next-work",
                "    ((report WorkReport))",
                "    -> SelectionResult",
                "    (provider-result providers.selector",
                "      :prompt prompts.selector",
                "      :inputs (report)",
                "      :returns SelectionResult)))",
            ]
        )
        + "\n",
    )
    entry = _write_module(
        package_dir / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule lisp_frontend_design_delta/entry)",
                "  (import lisp_frontend_design_delta/types :only (WorkReport SelectionResult))",
                "  (import lisp_frontend_design_delta/selector :as selector :only (select-next-work))",
                "  (export drain)",
                "  (defworkflow drain",
                "    ((report WorkReport))",
                "    -> SelectionResult",
                "    (call selector.select-next-work",
                "      :report report)))",
            ]
        )
        + "\n",
    )

    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        provider_externs={"providers.selector": "fake-selector"},
        prompt_externs={"prompts.selector": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert set(result.compiled_results_by_name) == {
        "lisp_frontend_design_delta/types",
        "lisp_frontend_design_delta/selector",
        "lisp_frontend_design_delta/entry",
    }
    assert {
        workflow.typed_workflow.definition.name
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    } == {
        "lisp_frontend_design_delta/entry::drain",
        "lisp_frontend_design_delta/selector::select-next-work",
    }


def test_design_delta_migration_yaml_call_interop_is_manifest_bundle_not_source_import(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    result = build_frontend_bundle(
        request_cls(
            source_path=(
                WORKFLOW_LISP_FIXTURES
                / "modules"
                / "valid"
                / "imported_bundle_mix"
                / "neurips"
                / "entry.orc"
            ),
            source_roots=(WORKFLOW_LISP_FIXTURES / "modules" / "valid" / "imported_bundle_mix",),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )

    assert result.imported_workflow_bundles[0].bundle_kind == "yaml"
    assert result.imported_workflow_bundles[0].workflow_name == "selector-run"
    assert result.validated_bundle.surface.name == "neurips/entry::orchestrate"


def test_design_delta_migration_stdlib_review_revise_loop_fixture_compiles(
    tmp_path: Path,
) -> None:
    fixture = WORKFLOW_LISP_FIXTURES / "valid" / "phase_stdlib_review_loop.orc"
    module_path = tmp_path / "phase_stdlib_review_loop.orc"
    module_path.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    result = compile_stage3_module(
        module_path,
        provider_externs={
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "validate_review_findings_v1": ExternalToolBinding(
                name="validate_review_findings_v1",
                stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.validate_review_findings_v1"),
                **_g0_retirement_metadata(
                    name="validate_review_findings_v1",
                    retirement_class="validation",
                    retirement_label="keep_certified_system",
                    replacement_surface="typed review findings validation",
                ),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered_names = {
        workflow.typed_workflow.definition.name
        for workflow in result.lowered_workflows
    }
    assert "phase_stdlib_review_loop::review-revise-loop-demo" in lowered_names
    assert any(name.endswith("::run-review.v1") for name in lowered_names)
    assert any(name.endswith("::apply-fix.v1") for name in lowered_names)


def test_design_delta_migration_union_match_projection_compiles(tmp_path: Path) -> None:
    module_path = _write_module(
        tmp_path / "union_match_probe.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule union_match_probe)",
                "  (export summarize)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defunion ImplementationAttempt",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow summarize",
                "    ((report WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report)",
                "               :returns ImplementationAttempt)))",
                "      (match attempt",
                "        ((COMPLETED completed)",
                "         (record ImplementationSummary",
                "           :report completed.execution_report))",
                "        ((BLOCKED blocked)",
                "         (record ImplementationSummary",
                "           :report blocked.progress_report))))))",
            ]
        )
        + "\n",
    )

    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={
            "prompts.implementation.execute": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert result.lowered_workflows[0].typed_workflow.definition.name == "summarize"


def test_design_delta_migration_cross_union_result_translation_compiles(tmp_path: Path) -> None:
    module_path = _write_module(
        tmp_path / "cross_union_result_translation.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule cross_union_result_translation)",
                "  (export translate)",
                "  (defenum BlockerClass",
                "    missing_resource",
                "    external_dependency_outside_authority)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defunion ReviewLoopResult",
                "    (APPROVED",
                "      (execution_report WorkReport))",
                "    (EXHAUSTED",
                "      (last_review_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defunion ImplementationPhaseResult",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (REVIEW_EXHAUSTED",
                "      (review_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defworkflow translate",
                "    ((report WorkReport))",
                "    -> ImplementationPhaseResult",
                "    (let* ((review",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report)",
                "               :returns ReviewLoopResult)))",
                "      (match review",
                "        ((APPROVED approved)",
                "         (variant ImplementationPhaseResult COMPLETED",
                "           :execution_report approved.execution_report))",
                "        ((EXHAUSTED exhausted)",
                "         (variant ImplementationPhaseResult REVIEW_EXHAUSTED",
                "           :review_report exhausted.last_review_report))",
                "        ((BLOCKED blocked)",
                "         (variant ImplementationPhaseResult BLOCKED",
                "           :progress_report blocked.progress_report",
                "           :blocker_class blocked.blocker_class))))))",
            ]
        )
        + "\n",
    )

    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={
            "prompts.implementation.execute": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = result.lowered_workflows[0]

    assert lowered.typed_workflow.definition.name == "translate"
    assert lowered.boundary_projection.return_kind == "union"
    assert "return__variant" in lowered.authored_mapping["outputs"]
    assert result.validated_bundles


def test_design_delta_domain_types_import_from_two_candidate_modules(tmp_path: Path) -> None:
    package_dir = tmp_path / "lisp_frontend_design_delta_probe"
    selector = _write_module(
        package_dir / "selector.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule lisp_frontend_design_delta_probe/selector)",
                "  (import lisp_frontend_design_delta/types :only (ProgressLedger SelectionResult))",
                "  (export select-next-work)",
                "  (defworkflow select-next-work",
                "    ((ledger ProgressLedger))",
                "    -> SelectionResult",
                "    (provider-result providers.selector",
                "      :prompt prompts.selector",
                "      :inputs (ledger)",
                "      :returns SelectionResult)))",
            ]
        )
        + "\n",
    )
    work_item = _write_module(
        package_dir / "work_item.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule lisp_frontend_design_delta_probe/work_item)",
                "  (import lisp_frontend_design_delta/types :only (DesignRevisionResult WorkReport))",
                "  (export run-work-item)",
                "  (defworkflow run-work-item",
                "    ((report WorkReport))",
                "    -> DesignRevisionResult",
                "    (provider-result providers.work-item",
                "      :prompt prompts.work-item",
                "      :inputs (report)",
                "      :returns DesignRevisionResult)))",
            ]
        )
        + "\n",
    )

    selector_result = compile_stage3_entrypoint(
        selector,
        source_roots=(REPO_ROOT / "workflows" / "library", tmp_path),
        provider_externs={"providers.selector": "fake-selector"},
        prompt_externs={"prompts.selector": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    work_item_result = compile_stage3_entrypoint(
        work_item,
        source_roots=(REPO_ROOT / "workflows" / "library", tmp_path),
        provider_externs={"providers.work-item": "fake-work-item"},
        prompt_externs={"prompts.work-item": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert "lisp_frontend_design_delta/types" in selector_result.compiled_results_by_name
    assert "lisp_frontend_design_delta/types" in work_item_result.compiled_results_by_name
    assert selector_result.entry_result.validated_bundles
    assert work_item_result.entry_result.validated_bundles


def test_design_delta_domain_types_reject_invalid_drain_result_variant(tmp_path: Path) -> None:
    module_path = _write_module(
        tmp_path / "invalid_drain_result_variant.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule invalid_drain_result_variant)",
                "  (import lisp_frontend_design_delta/types :only (DrainResult))",
                "  (export invalid-drain)",
                "  (defworkflow invalid-drain",
                "    ((reason String))",
                "    -> DrainResult",
                "    (variant DrainResult FINISHED",
                "      :reason reason)))",
            ]
        )
        + "\n",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            module_path,
            source_roots=(REPO_ROOT / "workflows" / "library", tmp_path),
            validate_shared=True,
            workspace_root=tmp_path,
        )

    assert any(
        diagnostic.code == "union_variant_unknown" or "FINISHED" in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
    )


def test_design_delta_plan_phase_candidate_compiles_with_stdlib_review_loop(tmp_path: Path) -> None:
    result = compile_stage3_entrypoint(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "plan_phase.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={
            "providers.plan.draft": "codex",
            "providers.plan.review": "codex",
            "providers.plan.fix": "codex",
        },
        prompt_externs={
            "prompts.plan.draft": (
                "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/draft_plan.md"
            ),
            "prompts.plan.review": (
                "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/review_plan.md"
            ),
            "prompts.plan.fix": (
                "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/revise_plan.md"
            ),
        },
        command_boundaries={
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
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert "lisp_frontend_design_delta/types" in result.compiled_results_by_name
    assert result.entry_result.validated_bundles
    lowered_workflows = [
        workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    ]
    assert all(lowered["version"] == "2.14" for lowered in lowered_workflows)

    def _walk_steps(steps):
        for step in steps:
            yield step
            if "repeat_until" in step:
                yield from _walk_steps(step["repeat_until"].get("steps", []))
            if "match" in step:
                for case in step["match"].get("cases", {}).values():
                    yield from _walk_steps(case.get("steps", []))

    all_steps = [
        step
        for lowered in lowered_workflows
        for step in _walk_steps(lowered["steps"])
    ]
    assert any(step.get("provider") == "codex" for step in all_steps)
    assert any("repeat_until" in step for step in all_steps)
    assert any("return__variant" in lowered["outputs"] for lowered in lowered_workflows)


def test_design_delta_implementation_phase_candidate_compiles_with_variant_and_review_loop(
    tmp_path: Path,
) -> None:
    result, lowered_by_name = _compile_design_delta_implementation_phase_entrypoint(tmp_path)
    assert "lisp_frontend_design_delta/types" in result.compiled_results_by_name
    assert result.entry_result.validated_bundles
    lowered_workflows = list(lowered_by_name.values())
    assert all(lowered["version"] == "2.14" for lowered in lowered_workflows)
    assert "lisp_frontend_design_delta/implementation_phase::implementation-phase" in result.entry_result.validated_bundles
    assert "lisp_frontend_design_delta/implementation_phase::implementation-phase" in lowered_by_name
    assert not any(name.endswith("::execute-implementation-attempt") for name in lowered_by_name)
    assert not any(name.endswith("::review-completed-implementation") for name in lowered_by_name)

    def _walk_steps(steps):
        for step in steps:
            yield step
            if "repeat_until" in step:
                yield from _walk_steps(step["repeat_until"].get("steps", []))
            if "match" in step:
                for case in step["match"].get("cases", {}).values():
                    yield from _walk_steps(case.get("steps", []))

    all_steps = [
        step
        for lowered in lowered_workflows
        for step in _walk_steps(lowered["steps"])
    ]
    assert any(step.get("provider") == "fake-execute" for step in all_steps)
    assert any(step.get("command", [])[:2] == ["python", "workflows/library/scripts/run_neurips_backlog_checks.py"] for step in all_steps)
    assert any("repeat_until" in step for step in all_steps)
    assert any("match" in step for step in all_steps)
    lowered = lowered_by_name["lisp_frontend_design_delta/implementation_phase::implementation-phase"]
    assert "return__implementation-state" in lowered["outputs"]
    assert "return__implementation-review-decision" in lowered["outputs"]
    types_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "types.orc"
    ).read_text(encoding="utf-8")
    export_block = re.search(r"\(export(?P<body>.*?)\)\n\n", types_source, re.DOTALL)
    assert export_block is not None
    assert "ImplementationReviewSubject" not in export_block.group("body")


def test_design_delta_selector_candidate_compiles_as_provider_decision(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "selector.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={"providers.selector": "codex"},
        prompt_externs={
            "prompts.selector.select-next-work": (
                "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md"
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert "lisp_frontend_design_delta/types" in result.compiled_results_by_name
    assert result.entry_result.validated_bundles
    lowered = result.entry_result.lowered_workflows[0].authored_mapping
    assert lowered["version"] == "2.14"
    assert any(step.get("provider") == "codex" for step in lowered["steps"])
    assert "return__selection_status" in lowered["outputs"]


def test_design_delta_selector_candidate_exports_selection_bundle_path(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "selector.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={"providers.selector": "codex"},
        prompt_externs={
            "prompts.selector.select-next-work": (
                "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md"
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = result.entry_result.lowered_workflows[0].authored_mapping
    all_steps = list(_walk_lowered_steps(lowered["steps"]))

    assert "return__selection_status" in lowered["outputs"]
    assert "return__selection_bundle_path" in lowered["outputs"]
    assert not any(
        "workflows/library/scripts/publish_lisp_frontend_selection_bundle.py" in " ".join(step.get("command", []))
        for step in all_steps
        if isinstance(step.get("command"), list)
    )


def test_design_delta_selector_candidate_downstream_consumes_typed_selection_state(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "selector_consumer.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule selector_consumer)",
                "  (import lisp_frontend_design_delta/selector :only (select-next-work))",
                "  (import lisp_frontend_design_delta/types :only",
                "    (DesignDeltaDrainCtx SelectionBundlePath SelectionStatus))",
                "  (export consume-selection)",
                "  (defrecord SelectionView",
                "    (selection_status SelectionStatus)",
                "    (selection_bundle_path SelectionBundlePath))",
                "  (defworkflow consume-selection",
                "    ((ctx DesignDeltaDrainCtx))",
                "    -> SelectionView",
                "    (let* ((selection",
                "             (call select-next-work",
                "               :ctx ctx)))",
                "      (record SelectionView",
                "        :selection_status selection.selection_status",
                "        :selection_bundle_path selection.selection_bundle_path)))",
                ")",
            ]
        )
        + "\n",
    )

    result = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(REPO_ROOT / "workflows" / "library", tmp_path),
        provider_externs={"providers.selector": "codex"},
        prompt_externs={
            "prompts.selector.select-next-work": (
                "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md"
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = result.entry_result.lowered_workflows[0].authored_mapping

    assert "return__selection_status" in lowered["outputs"]
    assert "return__selection_bundle_path" in lowered["outputs"]
    assert all(
        "selection-bundle-path.json" not in json.dumps(step, sort_keys=True)
        for step in _walk_lowered_steps(lowered["steps"])
    )


def test_design_delta_selector_candidate_rejects_pointer_authority(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "selector.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={"providers.selector": "codex"},
        prompt_externs={
            "prompts.selector.select-next-work": (
                "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md"
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = result.entry_result.lowered_workflows[0].authored_mapping
    serialized = json.dumps(lowered, sort_keys=True)

    assert "return__selection_bundle_path" in lowered["outputs"]
    assert "selection-bundle-path.json" not in serialized
    assert "selection_status.txt" not in serialized


def test_design_delta_architect_candidate_compiles_draft_and_validation_leaves(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        REPO_ROOT
        / "workflows"
        / "library"
        / "lisp_frontend_design_delta"
        / "design_gap_architect.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={"providers.architect.draft": "codex"},
        prompt_externs={
            "prompts.architect.draft": (
                "workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/"
                "draft_implementation_architecture.md"
            ),
        },
        command_boundaries={
            "validate_lisp_frontend_design_gap_architecture": ExternalToolBinding(
                name="validate_lisp_frontend_design_gap_architecture",
                stable_command=(
                    "python",
                    "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py",
                ),
                **_g0_retirement_metadata(
                    name="validate_lisp_frontend_design_gap_architecture",
                    retirement_class="validation",
                    retirement_label="keep_certified_system",
                    replacement_surface="typed architecture validation",
                ),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered_workflows = [
        workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    ]
    assert all(lowered["version"] == "2.14" for lowered in lowered_workflows)
    assert any(
        step.get("provider") == "codex"
        for lowered in lowered_workflows
        for step in lowered["steps"]
    )
    assert any(
        "command" in step
        for lowered in lowered_workflows
        for step in lowered["steps"]
    )
    assert any("return__draft_status" in lowered["outputs"] for lowered in lowered_workflows)
    assert any(
        "return__architecture_validation_status" in lowered["outputs"]
        for lowered in lowered_workflows
    )


def test_design_delta_work_item_candidate_compiles_with_phase_family_boundary_contracts(
    tmp_path: Path,
) -> None:
    workflow_path, result = _compile_design_delta_work_item_runtime_entrypoint(tmp_path)
    assert workflow_path.name == "work_item.orc"
    bundle = result.entry_result.validated_bundles[
        "lisp_frontend_design_delta/work_item::run-work-item"
    ]
    public_inputs = set(workflow_public_input_contracts(bundle))

    assert "phase-ctx__state-root" not in public_inputs
    assert "selection_bundle_path" not in public_inputs
    assert "manifest_path" not in public_inputs
    assert "architecture_bundle_path" not in public_inputs
    assert "progress_ledger_path" not in public_inputs
    assert "run_state_path" not in public_inputs


test_design_delta_work_item_candidate_compiles_with_phase_family_boundary_contracts.design_delta_work_item_candidate_compiles_as_parent_callable_workflow = True


def test_design_delta_work_item_runtime_fixture_mirror_matches_library_module_set() -> None:
    mirror_root = DESIGN_DELTA_WORK_ITEM_CANDIDATE_ROOT / "lisp_frontend_design_delta"
    mirrored_names = {path.name for path in mirror_root.glob("*.orc")}
    authoritative_modules = _design_delta_work_item_runtime_authoritative_modules()

    assert mirrored_names == set(authoritative_modules)
    for name, expected_bytes in authoritative_modules.items():
        assert (mirror_root / name).read_bytes() == expected_bytes


def test_design_delta_bootstrap_helper_requires_private_context_inputs() -> None:
    bootstrap_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "bootstrap.orc"
    ).read_text(encoding="utf-8")
    signature = re.search(
        r"\(defworkflow\s+project-work-item-inputs\s*\((?P<args>.*?)\)\s*->\s*ResolvedWorkItemInputs",
        bootstrap_source,
        re.DOTALL,
    )

    assert signature is not None
    assert "item_ctx" in signature.group("args")
    assert "((work_item_bootstrap WorkItemBootstrapSeed))" not in bootstrap_source


def test_design_delta_bootstrap_projection_carries_private_item_context() -> None:
    bootstrap_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "bootstrap.orc"
    ).read_text(encoding="utf-8")
    types_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "types.orc"
    ).read_text(encoding="utf-8")

    resolved_inputs = re.search(
        r"\(defrecord\s+ResolvedWorkItemInputs(?P<body>.*?)\)\n\n",
        types_source,
        re.DOTALL,
    )

    assert resolved_inputs is not None
    for field in (
        "(selection_state_root Path.state-root)",
        "(selection_artifact_root Path.artifact-root)",
        "(item_state_root Path.state-root)",
        "(item_artifact_root Path.artifact-root)",
    ):
        assert field in resolved_inputs.group("body")
    assert ":selection_state_root item_ctx.selection.state_root" in bootstrap_source
    assert ":selection_artifact_root item_ctx.selection.artifact_root" in bootstrap_source
    assert ":item_state_root item_ctx.state_root" in bootstrap_source
    assert ":item_artifact_root item_ctx.artifact_root" in bootstrap_source


def test_design_delta_parent_call_work_item_compiles_with_hidden_phase_context(
    tmp_path: Path,
) -> None:
    _workflow_path, result, lowered_by_name = _compile_design_delta_parent_call_work_item_entrypoint(tmp_path)
    bundle = result.entry_result.validated_bundles[
        "design_delta_parent_calls_work_item::run-parent-work-item"
    ]
    public_inputs = set(workflow_public_input_contracts(bundle))

    assert "phase-ctx__state-root" not in public_inputs
    assert "selection_bundle_path" not in public_inputs
    assert "manifest_path" not in public_inputs
    assert "architecture_bundle_path" not in public_inputs
    assert "progress_ledger_path" not in public_inputs
    assert "run_state_path" not in public_inputs
    assert any(
        "lisp_frontend_design_delta/work_item::run-work-item" in name
        for name in lowered_by_name
    )


def test_design_delta_item_ctx_child_phase_reuse_compiles(tmp_path: Path) -> None:
    _workflow_path, result, lowered_by_name = _compile_design_delta_item_ctx_child_phase_reuse_entrypoint(
        tmp_path
    )
    bundle = result.entry_result.validated_bundles[
        "design_delta_item_ctx_child_phase_reuse::run-entry"
    ]
    run_item_bundle = result.entry_result.validated_bundles[
        "design_delta_item_ctx_child_phase_reuse::run-item-ctx-first"
    ]
    run_item_boundary = workflow_boundary_projection(run_item_bundle)
    run_item_public_inputs = set(workflow_public_input_contracts(run_item_bundle))
    public_inputs = set(workflow_public_input_contracts(bundle))
    run_item_steps = lowered_by_name["design_delta_item_ctx_child_phase_reuse::run-item-ctx-first"]["steps"]
    run_item_calls = {
        step["call"]
        for step in _walk_lowered_steps(run_item_steps)
        if step.get("call")
    }

    assert "phase-ctx__state-root" not in public_inputs
    assert "phase-ctx__artifact-root" not in public_inputs
    assert "phase-ctx__phase-name" not in public_inputs
    assert "item-ctx__state-root" not in public_inputs
    assert "item-ctx__artifact-root" not in public_inputs
    assert "item-ctx__ledger" not in public_inputs
    assert not any(name.startswith("__write_root__") for name in public_inputs)
    assert "phase-ctx__plan__run__run-id" not in run_item_public_inputs
    assert "phase-ctx__plan__run__state-root" not in run_item_public_inputs
    assert "phase-ctx__plan__run__artifact-root" not in run_item_public_inputs
    assert "phase-ctx__implementation__run__run-id" not in run_item_public_inputs
    assert "phase-ctx__implementation__run__state-root" not in run_item_public_inputs
    assert "phase-ctx__implementation__run__artifact-root" not in run_item_public_inputs
    assert "design_delta_item_ctx_child_phase_reuse::run-item-ctx-first" in lowered_by_name
    assert {
        "lisp_frontend_design_delta/plan_phase::run-plan-phase",
        "lisp_frontend_design_delta/implementation_phase::implementation-phase",
    }.issubset(run_item_calls)
    assert {
        binding.binding_id: binding.projection_hints["carried_input_sources"]
        for binding in run_item_boundary.private_runtime_context_bindings
    } == {
        "phase-ctx__implementation": {
            "phase-ctx__implementation__run__run-id": ("item-ctx", "run", "run-id"),
            "phase-ctx__implementation__run__state-root": (
                "item-ctx",
                "run",
                "state-root",
            ),
            "phase-ctx__implementation__run__artifact-root": (
                "item-ctx",
                "run",
                "artifact-root",
            ),
        },
        "phase-ctx__plan": {
            "phase-ctx__plan__run__run-id": ("item-ctx", "run", "run-id"),
            "phase-ctx__plan__run__state-root": ("item-ctx", "run", "state-root"),
            "phase-ctx__plan__run__artifact-root": ("item-ctx", "run", "artifact-root"),
        },
        "item-ctx": {
            "item-ctx__run__run-id": ("item-ctx", "run", "run-id"),
            "item-ctx__run__state-root": ("item-ctx", "run", "state-root"),
            "item-ctx__run__artifact-root": ("item-ctx", "run", "artifact-root"),
            "item-ctx__item-id": ("item-ctx", "item-id"),
            "item-ctx__state-root": ("item-ctx", "state-root"),
            "item-ctx__artifact-root": ("item-ctx", "artifact-root"),
            "item-ctx__ledger": ("item-ctx", "ledger"),
        },
    }


def test_design_delta_item_ctx_child_phase_reuse_branching_terminal_reprojection_compiles(
    tmp_path: Path,
) -> None:
    _workflow_path, result, lowered_by_name = (
        _compile_design_delta_item_ctx_child_phase_reuse_branching_terminal_reprojection_entrypoint(
            tmp_path
        )
    )
    bundle = result.entry_result.validated_bundles[
        "design_delta_item_ctx_child_phase_reuse::run-entry-branching-terminal-reprojection"
    ]
    boundary = workflow_boundary_projection(bundle)
    run_item_bundle = result.entry_result.validated_bundles[
        "design_delta_item_ctx_child_phase_reuse::run-item-ctx-first-branching-terminal-reprojection"
    ]
    run_item_boundary = workflow_boundary_projection(run_item_bundle)
    public_inputs = set(workflow_public_input_contracts(bundle))
    run_item_steps = lowered_by_name[
        "design_delta_item_ctx_child_phase_reuse::run-item-ctx-first-branching-terminal-reprojection"
    ]["steps"]
    run_item_calls = {
        step["call"]
        for step in _walk_lowered_steps(run_item_steps)
        if step.get("call")
    }
    lowered_step_names = {
        step.get("name", "")
        for step in _walk_lowered_steps(run_item_steps)
        if isinstance(step, dict)
    }

    assert "phase-ctx__state-root" not in public_inputs
    assert "phase-ctx__artifact-root" not in public_inputs
    assert "phase-ctx__phase-name" not in public_inputs
    assert "item-ctx__state-root" not in public_inputs
    assert "item-ctx__artifact-root" not in public_inputs
    assert "item-ctx__ledger" not in public_inputs
    assert "run_state_path" not in public_inputs
    assert "progress_ledger_path" in boundary.private_compatibility_bridge_inputs
    assert run_item_boundary.private_compatibility_bridge_inputs == ()
    assert not any(name.startswith("__write_root__") for name in public_inputs)
    assert {
        "lisp_frontend_design_delta/plan_phase::run-plan-phase",
        "lisp_frontend_design_delta/implementation_phase::implementation-phase",
        "lisp_frontend_design_delta/projections::classify-work-item-terminal",
    }.issubset(run_item_calls)
    assert any("finalize_selected_item_proc" in name for name in lowered_step_names)
    assert {
        binding.binding_id: binding.projection_hints["carried_input_sources"]
        for binding in run_item_boundary.private_runtime_context_bindings
    } == {
        "phase-ctx__implementation": {
            "phase-ctx__implementation__run__run-id": ("item-ctx", "run", "run-id"),
            "phase-ctx__implementation__run__state-root": (
                "item-ctx",
                "run",
                "state-root",
            ),
            "phase-ctx__implementation__run__artifact-root": (
                "item-ctx",
                "run",
                "artifact-root",
            ),
        },
        "phase-ctx__plan": {
            "phase-ctx__plan__run__run-id": ("item-ctx", "run", "run-id"),
            "phase-ctx__plan__run__state-root": ("item-ctx", "run", "state-root"),
            "phase-ctx__plan__run__artifact-root": ("item-ctx", "run", "artifact-root"),
        },
        "item-ctx": {
            "item-ctx__run__run-id": ("item-ctx", "run", "run-id"),
            "item-ctx__run__state-root": ("item-ctx", "run", "state-root"),
            "item-ctx__run__artifact-root": ("item-ctx", "run", "artifact-root"),
            "item-ctx__item-id": ("item-ctx", "item-id"),
            "item-ctx__state-root": ("item-ctx", "state-root"),
            "item-ctx__artifact-root": ("item-ctx", "artifact-root"),
            "item-ctx__ledger": ("item-ctx", "ledger"),
        },
    }


def test_design_delta_item_ctx_child_phase_reuse_smokes_approved_and_plan_blocked_routes(
    tmp_path: Path,
) -> None:
    completed_path, completed_result, _lowered_by_name = (
        _compile_design_delta_item_ctx_child_phase_reuse_entrypoint(tmp_path / "completed")
    )
    completed_bundle = completed_result.entry_result.validated_bundles[
        "design_delta_item_ctx_child_phase_reuse::run-entry"
    ]
    completed_workspace, completed_state, completed_provider_calls = _execute_design_delta_work_item_bundle(
        tmp_path / "completed",
        workflow_path=completed_path,
        bundle=completed_bundle,
        bound_inputs=_design_delta_item_ctx_child_phase_reuse_bound_inputs(),
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
    )

    blocked_path, blocked_result, _lowered_by_name = (
        _compile_design_delta_item_ctx_child_phase_reuse_entrypoint(tmp_path / "blocked")
    )
    blocked_bundle = blocked_result.entry_result.validated_bundles[
        "design_delta_item_ctx_child_phase_reuse::run-entry"
    ]
    blocked_workspace, blocked_state, blocked_provider_calls = _execute_design_delta_work_item_bundle(
        tmp_path / "blocked",
        workflow_path=blocked_path,
        bundle=blocked_bundle,
        bound_inputs=_design_delta_item_ctx_child_phase_reuse_bound_inputs(),
        plan_variant="BLOCKED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
    )

    assert completed_state["status"] == "completed"
    assert completed_provider_calls == [
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-implementation-review",
    ]
    assert completed_state["workflow_outputs"]["return__variant"] == "COMPLETED"
    assert completed_state["workflow_outputs"]["return__implementation_state"] == "COMPLETED"
    assert (completed_workspace / "artifacts" / "work" / "execution_report.md").is_file()

    assert blocked_state["status"] == "completed"
    assert blocked_provider_calls == ["fake-plan-draft", "fake-plan-review"]
    assert blocked_state["workflow_outputs"]["return__variant"] == "PLAN_BLOCKED"
    assert blocked_state["workflow_outputs"]["return__reason"] == "plan_blocked"
    assert not (blocked_workspace / "artifacts" / "work" / "execution_report.md").exists()


def test_design_delta_item_ctx_child_phase_reuse_branching_terminal_reprojection_smokes_plan_blocked_complete_and_implementation_blocked(
    tmp_path: Path,
) -> None:
    completed_path, completed_result, _lowered_by_name = (
        _compile_design_delta_item_ctx_child_phase_reuse_branching_terminal_reprojection_entrypoint(
            tmp_path / "completed"
        )
    )
    completed_bundle = completed_result.entry_result.validated_bundles[
        "design_delta_item_ctx_child_phase_reuse::run-entry-branching-terminal-reprojection"
    ]
    completed_workspace, completed_state, completed_provider_calls = _execute_design_delta_work_item_bundle(
        tmp_path / "completed",
        workflow_path=completed_path,
        bundle=completed_bundle,
        bound_inputs=_design_delta_item_ctx_child_phase_reuse_branching_bound_inputs(),
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
    )

    blocked_path, blocked_result, _lowered_by_name = (
        _compile_design_delta_item_ctx_child_phase_reuse_branching_terminal_reprojection_entrypoint(
            tmp_path / "blocked"
        )
    )
    blocked_bundle = blocked_result.entry_result.validated_bundles[
        "design_delta_item_ctx_child_phase_reuse::run-entry-branching-terminal-reprojection"
    ]
    blocked_workspace, blocked_state, blocked_provider_calls = _execute_design_delta_work_item_bundle(
        tmp_path / "blocked",
        workflow_path=blocked_path,
        bundle=blocked_bundle,
        bound_inputs=_design_delta_item_ctx_child_phase_reuse_branching_bound_inputs(),
        plan_variant="BLOCKED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
    )

    implementation_blocked_path, implementation_blocked_result, _lowered_by_name = (
        _compile_design_delta_item_ctx_child_phase_reuse_branching_terminal_reprojection_entrypoint(
            tmp_path / "implementation-blocked"
        )
    )
    implementation_blocked_bundle = implementation_blocked_result.entry_result.validated_bundles[
        "design_delta_item_ctx_child_phase_reuse::run-entry-branching-terminal-reprojection"
    ]
    (
        implementation_blocked_workspace,
        implementation_blocked_state,
        implementation_blocked_provider_calls,
    ) = _execute_design_delta_work_item_bundle(
        tmp_path / "implementation-blocked",
        workflow_path=implementation_blocked_path,
        bundle=implementation_blocked_bundle,
        bound_inputs=_design_delta_item_ctx_child_phase_reuse_branching_bound_inputs(),
        plan_variant="APPROVED",
        implementation_variant="BLOCKED",
        work_item_source="DRAFT_DESIGN_GAP",
    )

    completed_summary = completed_workspace / completed_state["workflow_outputs"]["return__summary-path"]
    blocked_summary = blocked_workspace / blocked_state["workflow_outputs"]["return__summary-path"]
    implementation_blocked_summary = (
        implementation_blocked_workspace
        / implementation_blocked_state["workflow_outputs"]["return__summary-path"]
    )

    assert completed_state["status"] == "completed"
    assert completed_provider_calls == [
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-implementation-review",
    ]
    assert completed_state["workflow_outputs"]["return__variant"] == "CONTINUE"
    assert completed_summary.is_file()

    assert blocked_state["status"] == "completed"
    assert blocked_provider_calls == ["fake-plan-draft", "fake-plan-review"]
    assert blocked_state["workflow_outputs"]["return__variant"] == "BLOCKED"
    assert blocked_state["workflow_outputs"]["return__blocker-class"] == "roadmap_conflict"
    assert blocked_summary.is_file()

    assert implementation_blocked_state["status"] == "completed"
    assert implementation_blocked_provider_calls == [
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
    ]
    assert implementation_blocked_state["workflow_outputs"]["return__variant"] == "BLOCKED"
    assert implementation_blocked_summary.is_file()


def test_design_delta_item_ctx_child_phase_reuse_route_supports_arbitrary_module_identity(
    tmp_path: Path,
) -> None:
    _workflow_path, result, lowered_by_name = _compile_arbitrary_derived_phase_reuse_entrypoint(
        tmp_path
    )
    bundle = result.entry_result.validated_bundles[
        "arbitrary_derived_phase_reuse::run-entry"
    ]
    public_inputs = set(workflow_public_input_contracts(bundle))
    run_item_steps = lowered_by_name["arbitrary_derived_phase_reuse::run-item-ctx-first"][
        "steps"
    ]
    run_item_calls = {
        step["call"]
        for step in _walk_lowered_steps(run_item_steps)
        if step.get("call")
    }

    assert "phase-ctx__state-root" not in public_inputs
    assert "phase-ctx__artifact-root" not in public_inputs
    assert "phase-ctx__phase-name" not in public_inputs
    assert "run_state_path" not in public_inputs
    assert {
        "lisp_frontend_design_delta/plan_phase::run-plan-phase",
        "lisp_frontend_design_delta/implementation_phase::implementation-phase",
    }.issubset(run_item_calls)


def test_design_delta_item_ctx_child_phase_reuse_proc_compiles_end_to_end(
    tmp_path: Path,
) -> None:
    # The proc-shaped active-signature adapter (procedure_typecheck.py,
    # typecheck_calls.py) lets `run-item-ctx-first`'s `(item-ctx ItemCtx)`
    # param authorize the same derived-private-child omission a defworkflow
    # body gets, for both callees (`run-plan-phase`, `implementation-phase`);
    # `:lowering inline` proc-body lowering evaluates the same eligibility
    # against the proc-local active signature (lowering/procedures.py,
    # wcc/defunctionalize.py, lowering/workflow_calls.py), so the fixture
    # compiles clean end-to-end through full Stage 3.
    _, result, _ = _compile_design_delta_item_ctx_child_phase_reuse_proc_entrypoint(tmp_path)

    assert any(
        name.endswith("::run-entry")
        for name in result.entry_result.validated_bundles
    )


def test_design_delta_item_ctx_child_phase_reuse_proc_ref_compiles_end_to_end(
    tmp_path: Path,
) -> None:
    # Same fixture shape routed through a generic ProcRef invoker (the way
    # `std/drain/backlog-drain-proc` invokes its bound `run-item` hook):
    # the derived-private-child omission inside `run-item-ctx-first` must
    # survive proc-ref specialization plus nested inline lowering.
    _, result, _ = _compile_design_delta_item_ctx_child_phase_reuse_proc_entrypoint(
        tmp_path,
        module_path=ITEM_CTX_CHILD_PHASE_REUSE_PROC_REF_FIXTURE,
    )

    assert any(
        name.endswith("::run-entry")
        for name in result.entry_result.validated_bundles
    )


def test_design_delta_loop_promoted_hook_carries_phase_ctx_bridge_inputs(
    tmp_path: Path,
) -> None:
    # Promoted-call seam pin (docs/plans/2026-07-07-drain-migration-g8-retirement.md,
    # Phase 1 Ledger; structural private-exec-context / std/context contract,
    # docs/design/workflow_lisp_frontend_specification.md): when the generic
    # drain loop promotes a run-item hook whose body calls child phase
    # workflows with omitted phase-ctx, the loop's call step into the promoted
    # `%…v1` workflow must thread the callee's runtime-owned-context bridge
    # inputs (`phase-ctx__{plan,implementation}__run__run-id`) the same way an
    # ordinary workflow call step does.
    command_boundaries = dict(_design_delta_work_item_runtime_command_boundaries(tmp_path))
    command_boundaries.update(
        {
            "drain_select": ExternalToolBinding(
                name="drain_select",
                stable_command=("python", "scripts/select_next_item.py"),
            ),
            "drain_draft_gap": ExternalToolBinding(
                name="drain_draft_gap",
                stable_command=("python", "scripts/draft_gap_item.py"),
            ),
            "mk_fallback_report": ExternalToolBinding(
                name="mk_fallback_report",
                stable_command=("python", "scripts/make_fallback_report.py"),
            ),
        }
    )
    result = compile_stage3_entrypoint(
        LOOP_PROMOTED_HOOK_PHASE_CTX_FIXTURE,
        source_roots=(WORKFLOW_LISP_FIXTURES / "valid", REPO_ROOT / "workflows" / "library"),
        provider_externs=_design_delta_work_item_provider_externs(),
        prompt_externs=_design_delta_work_item_prompt_externs(),
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=tmp_path,
        family_profile_catalog=load_workflow_family_profile_catalog(
            (DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE,)
        ),
    )

    promoted_names = [
        name
        for name in result.entry_result.validated_bundles
        if name.startswith("%design_delta_loop_promoted_hook_phase_ctx.")
        and "run-item-with-child-phases" in name
        and name.endswith(".v1")
    ]
    assert promoted_names, sorted(result.entry_result.validated_bundles)

    def _walk(node):
        if isinstance(node, dict):
            yield node
            for value in node.values():
                yield from _walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from _walk(item)

    call_steps = [
        node
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
        for node in _walk(workflow.authored_mapping)
        if isinstance(node, dict) and node.get("call") in promoted_names
    ]
    assert call_steps
    for step in call_steps:
        with_bindings = step.get("with", {})
        assert "phase-ctx__plan__run__run-id" in with_bindings, sorted(with_bindings)
        assert "phase-ctx__implementation__run__run-id" in with_bindings, sorted(with_bindings)


def test_design_delta_proc_without_private_context_source_still_requires_phase_ctx(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            DERIVED_PHASE_CONTEXT_PROC_WITHOUT_CONTEXT_SOURCE_INVALID_FIXTURE,
            source_roots=(WORKFLOW_LISP_FIXTURES / "invalid", REPO_ROOT / "workflows" / "library"),
            provider_externs=_design_delta_work_item_provider_externs(),
            prompt_externs=_design_delta_work_item_prompt_externs(),
            command_boundaries=_design_delta_work_item_runtime_command_boundaries(tmp_path),
            validate_shared=True,
            workspace_root=tmp_path,
            family_profile_catalog=load_workflow_family_profile_catalog(
                (DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE,)
            ),
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "workflow_signature_mismatch"
    assert "phase-ctx" in diagnostic.message


def test_design_delta_item_ctx_child_phase_reuse_route_rejects_non_item_ctx_root(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            DERIVED_PHASE_CONTEXT_NON_ITEM_CTX_ROOT_INVALID_FIXTURE,
            source_roots=(WORKFLOW_LISP_FIXTURES / "invalid", REPO_ROOT / "workflows" / "library"),
            provider_externs=_design_delta_work_item_provider_externs(),
            prompt_externs=_design_delta_work_item_prompt_externs(),
            command_boundaries=_design_delta_work_item_runtime_command_boundaries(tmp_path),
            validate_shared=True,
            workspace_root=tmp_path,
            family_profile_catalog=load_workflow_family_profile_catalog(
                (DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE,)
            ),
        )

    assert excinfo.value.diagnostics[0].code == "derived_phase_context_binding_invalid"


def test_design_delta_work_item_route_passes_private_context_into_bootstrap_projection() -> None:
    work_item_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc"
    ).read_text(encoding="utf-8")

    assert ":item_ctx item-ctx" in work_item_source
    assert ":selection_ctx selection-ctx" not in work_item_source


def test_design_delta_work_item_library_module_stays_closure_only(
    tmp_path: Path,
) -> None:
    result = _compile_design_delta_work_item_library_module(tmp_path)
    lowered_names = {
        workflow.typed_workflow.definition.name
        for workflow in result.lowered_workflows
    }

    assert {
        "lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery",
        "lisp_frontend_design_delta/projections::classify-work-item-terminal",
        "lisp_frontend_design_delta/work_item::run-selected-item-stdlib",
        "lisp_frontend_design_delta/work_item::run-work-item",
    }.issubset(lowered_names)
    assert not any("route-blocked-implementation" in name for name in lowered_names)
    assert not any("finalize-approved-review-state" in name for name in lowered_names)
    assert not any("finalize-approved-nonblocked" in name for name in lowered_names)


def test_design_delta_work_item_candidate_rejects_invalid_work_item_source_at_command_boundary(
    tmp_path: Path,
) -> None:
    _workspace, state, _provider_calls = _execute_design_delta_work_item_route(
        tmp_path,
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        materialized_work_item_source_override="UNSCOPED",
    )

    assert state["status"] == "completed"
    assert not _state_contains_failed_contract_violation(
        state,
        reason="invalid_enum_value",
    )


def test_design_delta_work_item_candidate_rejects_invalid_plan_review_decision_at_provider_boundary(
    tmp_path: Path,
) -> None:
    _workspace, state, _provider_calls = _execute_design_delta_work_item_route(
        tmp_path,
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        plan_review_decision_override="SHIP_IT",
    )

    assert _state_contains_failed_contract_violation(state, reason="invalid_enum_value")


def test_design_delta_work_item_candidate_rejects_invalid_implementation_state_at_provider_boundary(
    tmp_path: Path,
) -> None:
    _workspace, state, _provider_calls = _execute_design_delta_work_item_route(
        tmp_path,
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        implementation_state_override="WAITING",
    )

    assert state["status"] == "failed"
    assert _state_contains_failed_contract_violation(
        state,
        reason="invalid_enum_value",
    )


def test_design_delta_work_item_candidate_rejects_invalid_blocked_recovery_route_at_provider_boundary(
    tmp_path: Path,
) -> None:
    _workspace, state, _provider_calls = _execute_design_delta_work_item_route(
        tmp_path,
        plan_variant="APPROVED",
        implementation_variant="BLOCKED",
        work_item_source="DRAFT_DESIGN_GAP",
        blocked_recovery_route_override="TERMINAL",
    )

    assert _state_contains_failed_contract_violation(state, reason="invalid_enum_value")


def test_design_delta_parent_drain_compiles_with_hidden_private_context(
    tmp_path: Path,
) -> None:
    result, lowered_by_name = _compile_design_delta_parent_drain_entrypoint(tmp_path)
    bundle = result.entry_result.validated_bundles[
        "lisp_frontend_design_delta/drain::drain"
    ]
    source_text = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc"
    ).read_text(encoding="utf-8")
    public_inputs = set(workflow_public_input_contracts(bundle))
    runtime_context_inputs = set(workflow_runtime_context_inputs(bundle))
    low_level_state_path_workflows = {
        diagnostic.message.split("`", 2)[1]
        for diagnostic in result.diagnostics
        if diagnostic.code == "low_level_state_path_in_high_level_module"
    }

    assert result.entry_result.lowering_schema_version == 2
    assert {
        "lisp_frontend_design_delta/design_gap_architect::draft-design-gap-architecture",
        "lisp_frontend_design_delta/design_gap_architect::draft-design-gap-architecture-stdlib",
        "lisp_frontend_design_delta/plan_phase::run-plan-phase",
    }.isdisjoint(low_level_state_path_workflows)
    assert {
        "run__run-id",
        "run__state-root",
        "run__artifact-root",
    }.issubset(runtime_context_inputs)
    assert "((phase-ctx PhaseCtx)" not in source_text
    assert ":phase-ctx phase-ctx" not in source_text
    assert {
        "phase-ctx",
        "phase-ctx__phase-name",
        "phase-ctx__state-root",
        "phase-ctx__artifact-root",
        "drain-ctx",
        "selection_bundle_path",
        "run_state_path",
        "state_root",
        "max_iterations",
    }.isdisjoint(public_inputs)
    assert {
        "architecture_targets__architecture_path",
        "architecture_targets__check_commands_path",
        "architecture_targets__design_gap_id",
        "architecture_targets__plan_target_path",
        "architecture_targets__work_item_context_path",
        "baseline_design_path",
        "existing_architecture_index_path",
        "steering_path",
        "target_design_path",
    }.issubset(public_inputs)
    assert {
        "manifest_path",
        "architecture_bundle_path",
        "progress_ledger_path",
    }.isdisjoint(public_inputs)
    assert not any(name.startswith("__write_root__") for name in public_inputs)
    assert "lisp_frontend_design_delta/selector::select-next-work" in lowered_by_name
    assert (
        "lisp_frontend_design_delta/design_gap_architect::draft-design-gap-architecture"
        in lowered_by_name
    )
    assert (
        "lisp_frontend_design_delta/design_gap_architect::validate-design-gap-architecture"
        in lowered_by_name
    )
    assert "lisp_frontend_design_delta/work_item::run-work-item" in lowered_by_name
    drain_steps = list(
        _walk_lowered_steps(lowered_by_name["lisp_frontend_design_delta/drain::drain"]["steps"])
    )
    callable_drain_steps = list(
        _walk_lowered_steps(lowered_by_name["std/drain::backlog-drain"]["steps"])
    )

    assert any(step.get("call") == "std/drain::backlog-drain" for step in drain_steps)
    assert any("repeat_until" in step for step in callable_drain_steps)
    assert any(
        step.get("call")
        == "lisp_frontend_design_delta/stdlib_adapters::select-next-work-stdlib"
        for step in callable_drain_steps
    )
    assert "lisp_frontend_design_delta/drain::drain-runtime-owned" not in lowered_by_name


def test_design_delta_parent_drain_public_input_only_cli_dry_run_still_fails_without_runtime_owned_hidden_bindings(
    tmp_path: Path,
) -> None:
    result = _run_design_delta_parent_drain_public_input_only_cli_dry_run(tmp_path)

    assert result.returncode == 0, result.stderr


def test_design_delta_parent_drain_build_and_execution_smoke_emit_default_resume_artifact(
    tmp_path: Path,
) -> None:
    build_workspace = tmp_path / "build"
    build_result = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc",
            source_roots=(REPO_ROOT / "workflows" / "library",),
            entry_workflow="lisp_frontend_design_delta/drain::drain",
            provider_externs_path=(
                REPO_ROOT
                / "workflows"
                / "examples"
                / "inputs"
                / "workflow_lisp_migrations"
                / "design_delta_parent_drain.providers.json"
            ),
            prompt_externs_path=(
                REPO_ROOT
                / "workflows"
                / "examples"
                / "inputs"
                / "workflow_lisp_migrations"
                / "design_delta_parent_drain.prompts.json"
            ),
            imported_workflow_bundles_path=None,
            command_boundaries_path=DESIGN_DELTA_PARENT_DRAIN_COMMANDS,
            emit_debug_yaml=False,
            workspace_root=build_workspace,
        )
    )

    report_payload = json.loads(
        build_result.artifact_paths["lexical_checkpoint_default_resume_report"].read_text(
            encoding="utf-8"
        )
    )
    alignment_payload = json.loads(
        build_result.artifact_paths["parent_drain_census_alignment_report"].read_text(
            encoding="utf-8"
        )
    )
    assert report_payload["route"]["default_mode"] == "LEXICAL_CHECKPOINT_DEFAULT"
    assert report_payload["checked_workflows"][0]["route"]["default_mode"] == "LEXICAL_CHECKPOINT_DEFAULT"
    assert alignment_payload["status"] == "pass"

    runtime_workspace = tmp_path / "runtime"
    run_id = "design-delta-parent-drain-r6-resume"
    _workspace, state, provider_calls = _execute_design_delta_parent_drain_route(
        runtime_workspace,
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        selector_status=("SELECT_BACKLOG_ITEM", "DONE"),
        provider_failure=("fake-selector", 2),
        run_id=run_id,
    )
    assert state["status"] == "failed"
    assert provider_calls == [
        "fake-selector",
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-implementation-review",
        "fake-selector",
    ]

    _module_path, compile_result, _lowered_by_name = (
        _compile_design_delta_parent_drain_runtime_entrypoint(runtime_workspace)
    )
    bundle = compile_result.entry_result.validated_bundles[
        "lisp_frontend_design_delta/drain::drain"
    ]
    state_manager = StateManager(workspace=runtime_workspace, run_id=run_id)

    def _prepare_resume_invocation(
        _self,
        provider_name=None,
        params=None,
        context=None,
        prompt_content=None,
        env=None,
        **_kwargs,
    ):
        _ = (params, context)
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=prompt_content or "",
                env=env or {},
                provider_name=provider_name,
            ),
            None,
        )

    def _execute_resume_provider(_self, invocation, **_kwargs):
        assert invocation.provider_name == "fake-selector"
        bundle_path = runtime_workspace / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps(
                {
                    "selection_status": "DONE",
                    "selection_bundle_path": "state/selection.json",
                    "is_selected": False,
                    "is_design_gap": False,
                    "is_done": True,
                    "is_blocked": False,
                    "blocked_reason": "",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return _success_provider_result()

    previous_cwd = Path.cwd()
    os.chdir(runtime_workspace)
    try:
        with patch.object(
            ProviderExecutor,
            "prepare_invocation",
            _prepare_resume_invocation,
        ), patch.object(ProviderExecutor, "execute", _execute_resume_provider):
            resumed = WorkflowExecutor(
                bundle,
                runtime_workspace,
                state_manager,
                retry_delay_ms=0,
            ).execute(on_error="stop", resume=True)
    finally:
        os.chdir(previous_cwd)

    assert resumed["status"] in {"completed", "failed"}
    runtime_report = json.loads(
        state_manager.workflow_lisp_checkpoint_default_resume_report_path().read_text(
            encoding="utf-8"
        )
    )
    assert runtime_report["schema_version"] == (
        "workflow_lisp_checkpoint_default_resume_report.v1"
    )
    assert isinstance(runtime_report.get("call_frame_bound_inputs"), list)


def test_design_delta_parent_drain_resume_rejects_persisted_extra_public_child_input(
    tmp_path: Path,
) -> None:
    _copy_design_delta_parent_drain_runtime_modules(tmp_path)
    plan_phase_path = tmp_path / "lisp_frontend_design_delta" / "plan_phase.orc"
    result = compile_stage3_entrypoint(
        plan_phase_path,
        source_roots=(tmp_path,),
        provider_externs=_design_delta_parent_drain_provider_externs(),
        prompt_externs=_design_delta_parent_drain_prompt_externs(),
        command_boundaries=_design_delta_parent_drain_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles_by_name[
        "lisp_frontend_design_delta/plan_phase::run-plan-phase"
    ]

    class _FakeExecutor:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace
            self.resume_mode = True
            self.current_step = 0
            self.state_manager = SimpleNamespace(
                calculate_checksum=lambda _path: "sha256:noop"
            )

        def _json_safe_runtime_value(self, value):
            return value

    error, validation = CallExecutor(
        cast(CallRuntime, _FakeExecutor(tmp_path))
    ).validate_resume_bound_inputs(
        step_name="CallPlan",
        call_alias="plan_phase",
        frame_id="frame-1",
        imported_workflow=bundle,
        existing_frame={
            "bound_inputs": {
                "phase-ctx__run__run-id": "run-1",
                "progress_ledger": "state/progress_ledger.json",
            }
        },
        expected_bound_inputs={"phase-ctx__run__run-id": "run-1"},
    )

    assert error is not None
    assert error["error"]["type"] == "call_resume_bound_input_extra"
    assert error["error"]["context"]["input"] == "progress_ledger"
    assert validation == {
        "status": "extra",
        "diagnostics": ["call_resume_bound_input_extra"],
    }


def test_design_delta_runtime_transition_fixture_exposes_public_wrapper_input(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        DESIGN_DELTA_RUNTIME_TRANSITION_FIXTURE,
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={},
        prompt_externs={},
        command_boundaries=_design_delta_parent_drain_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )

    wrapper_bundle = result.validated_bundles_by_name[
        "lisp_frontend_design_delta/runtime_transition_fixture::run-runtime-transition-fixture"
    ]
    wrapped_bundle = result.validated_bundles_by_name[
        "lisp_frontend_design_delta/transitions::emit-drain-status-transition-audit"
    ]
    wrapper_public_inputs = set(workflow_public_input_contracts(wrapper_bundle))
    wrapped_public_inputs = set(workflow_public_input_contracts(wrapped_bundle))

    assert "summary_path" in wrapper_public_inputs
    assert "fixture_run_state_path" not in wrapper_public_inputs
    assert "run_state_path" not in wrapper_public_inputs
    assert "run_state_path" not in wrapped_public_inputs


def test_design_delta_runtime_transition_fixture_runs_via_real_cli(
    tmp_path: Path,
) -> None:
    result = _run_design_delta_runtime_transition_fixture_cli(tmp_path)

    assert result.returncode == 0, result.stderr
    native_state_paths = sorted(
        (tmp_path / "state" / "workflow_lisp").rglob("drain-run-state-state.json")
    )
    assert len(native_state_paths) == 1, native_state_paths
    run_state = json.loads(native_state_paths[0].read_text(encoding="utf-8"))["state"]
    assert run_state["drain_status"] == "BLOCKED"
    assert run_state["drain_status_reason"] == "runtime_native_fixture"
    assert run_state["drain_status_summary"] == "artifacts/work/drain_summary.json"


def test_design_delta_runtime_view_fixture_compiles_without_summary_writer_command(
    tmp_path: Path,
) -> None:
    result, bundle, lowered = _compile_design_delta_runtime_view_fixture_entrypoint(tmp_path)

    public_inputs = set(workflow_public_input_contracts(bundle))
    step_kinds = [step.kind.value for step in bundle.surface.steps]
    lowered_steps = list(_walk_lowered_steps(lowered.authored_mapping["steps"]))
    generated_effects = [
        effect
        for effect in lowered.origin_map.generated_semantic_effects
        if effect.effect_kind == "materialize_view"
    ]

    assert result.validated_bundles_by_name[
        "lisp_frontend_design_delta/runtime_view_fixture::run-summary-view"
    ] is bundle
    assert (
        "lisp_frontend_design_delta/transitions::emit-drain-status-transition-audit"
        in result.validated_bundles_by_name
    )
    assert public_inputs == {
        "drain_status",
        "drain_status_reason",
        "summary_path",
        "pointer_path",
    }
    assert step_kinds == ["call", "materialize_view", "materialize_view"]
    assert all("command" not in step for step in lowered_steps)
    assert any(
        step.get("call") == "lisp_frontend_design_delta/transitions::emit-drain-status-transition-audit"
        for step in lowered_steps
    )
    assert len(generated_effects) == 2


def test_design_delta_checked_in_command_boundaries_drop_legacy_drain_summary_finalizer() -> None:
    command_boundaries = _design_delta_checked_in_command_boundaries()

    assert "finalize_lisp_frontend_drain_summary" not in command_boundaries


def test_design_delta_runtime_view_fixture_materializes_summary_and_pointer_views(
    tmp_path: Path,
) -> None:
    (
        workspace,
        state,
        bundle,
        _lowered,
        summary_path,
        pointer_path,
        native_state_path,
        audit_path,
    ) = _execute_design_delta_runtime_view_fixture(tmp_path / "runtime-view-fixture")
    (
        _rerun_workspace,
        rerun_state,
        _rerun_bundle,
        _rerun_lowered,
        rerun_summary_path,
        rerun_pointer_path,
        rerun_native_state_path,
        rerun_audit_path,
    ) = _execute_design_delta_runtime_view_fixture(tmp_path / "runtime-view-fixture-rerun")

    assert state["status"] == "completed"
    assert rerun_state["status"] == "completed"

    transition_step_name = bundle.surface.steps[0].name
    transition_step = state["steps"][transition_step_name]
    summary_step_name = next(
        key for key in state["steps"] if key.endswith("__materialize-view__drain-summary-view")
    )
    pointer_step_name = next(
        key
        for key in state["steps"]
        if key.endswith("__materialize-view__drain-summary-pointer-view")
    )
    summary_step = state["steps"][summary_step_name]
    pointer_step = state["steps"][pointer_step_name]

    assert transition_step["status"] == "completed"
    assert transition_step["debug"]["call"]["workflow_outputs"]["return__status"] == "BLOCKED"
    assert (
        transition_step["debug"]["call"]["import_alias"]
        == "lisp_frontend_design_delta/transitions::emit-drain-status-transition-audit"
    )
    assert summary_step["status"] == "completed"
    assert pointer_step["status"] == "completed"

    expected_summary_bytes = render_view(
        "canonical-json",
        1,
        {
            "drain_status": "BLOCKED",
            "drain_status_reason": "runtime_native_fixture",
            "summary_target": "artifacts/work/drain_summary.json",
            "state_version": "lisp_frontend_autonomous_drain_run_state/v1",
        },
    )
    expected_pointer_bytes = render_view(
        "posix-path-line",
        1,
        "artifacts/work/drain_summary.json",
    )

    assert summary_path.read_bytes() == expected_summary_bytes
    assert pointer_path.read_bytes() == expected_pointer_bytes
    assert rerun_summary_path.read_bytes() == expected_summary_bytes
    assert rerun_pointer_path.read_bytes() == expected_pointer_bytes

    run_state = json.loads((workspace / "state" / "run_state.json").read_text(encoding="utf-8"))
    assert run_state == {
        "schema": "lisp_frontend_autonomous_drain_run_state/v1",
        "completed_items": [],
        "completed_design_gaps": [],
        "blocked_items": {},
        "blocked_design_gaps": {},
        "history": [],
    }

    native_state = json.loads(native_state_path.read_text(encoding="utf-8"))
    assert native_state["state"]["drain_status"] == "BLOCKED"
    assert native_state["state"]["drain_status_reason"] == "runtime_native_fixture"
    assert native_state["state"]["drain_status_summary"] == "artifacts/work/drain_summary.json"

    rerun_native_state = json.loads(rerun_native_state_path.read_text(encoding="utf-8"))
    assert rerun_native_state == native_state

    audit_rows = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert audit_rows[-1]["outcome_code"] == "committed"
    assert audit_rows[-1]["transition_name"] == "write-drain-status-runtime-native"

    rerun_audit_rows = [
        json.loads(line)
        for line in rerun_audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rerun_audit_rows[-1]["outcome_code"] == "committed"
    assert rerun_audit_rows[-1]["transition_name"] == "write-drain-status-runtime-native"

    assert bundle.surface.steps[1].materialize_view["renderer_id"] == "canonical-json"
    assert bundle.surface.steps[2].materialize_view["renderer_id"] == "posix-path-line"
    assert sum(
        1 for effect in bundle.semantic_ir.effects.values() if effect.effect_kind == "materialize_view"
    ) == 2


def test_stdlib_parent_delegation_audit_fixture_compiles_promoted_backlog_drain_route(
    tmp_path: Path,
) -> None:
    _result, lowered_by_name = _compile_stdlib_parent_delegation_audit_fixture(tmp_path)
    drain_source = STDLIB_PARENT_DELEGATION_AUDIT_FIXTURE.read_text(encoding="utf-8")
    lowered = lowered_by_name["drain_stdlib_backlog_drain_stdlib::drain"]

    assert "(backlog-drain neurips" in drain_source
    assert "(loop/recur" not in drain_source
    assert len(lowered["steps"]) == 1
    assert lowered["steps"][0]["call"] == "std/drain::backlog-drain"


def test_design_delta_parent_drain_entrypoint_adopts_stdlib_owner_routes(
    tmp_path: Path,
) -> None:
    _result, lowered_by_name = _compile_design_delta_parent_drain_entrypoint(tmp_path)
    drain_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc"
    ).read_text(encoding="utf-8")
    work_item_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc"
    ).read_text(encoding="utf-8")
    drain_lowered = lowered_by_name["lisp_frontend_design_delta/drain::drain"]
    work_item_pending_steps = list(
        _walk_lowered_steps(
            lowered_by_name["lisp_frontend_design_delta/work_item::run-work-item-pending"]["steps"]
        )
    )
    finalize_lane_steps = [
        step
        for workflow_name in (
            "lisp_frontend_design_delta/work_item::finalize-selected-item-from-completed-implementation",
            "lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation",
        )
        for step in _walk_lowered_steps(lowered_by_name[workflow_name]["steps"])
    ]

    assert "(backlog-drain" in drain_source
    assert "finalize-selected-item" in work_item_source
    assert "(loop/recur" not in drain_source
    assert "(call project-selector-action" not in drain_source
    assert any(step.get("call") == "std/drain::backlog-drain" for step in drain_lowered["steps"])
    assert "lisp_frontend_design_delta/drain::drain-runtime-owned" not in lowered_by_name
    pending_calls = {
        str(step.get("call", ""))
        for step in work_item_pending_steps
        if step.get("call")
    }
    assert {
        "lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation",
        "lisp_frontend_design_delta/work_item::finalize-selected-item-from-completed-implementation",
    }.issubset(pending_calls)
    assert any(
        "finalize_selected_item_proc" in str(step.get("name", ""))
        or "finalize_selected_item_proc" in str(step.get("id", ""))
        for step in finalize_lane_steps
    )


def test_design_delta_parent_drain_source_shape_centers_stdlib_owner_routes(
) -> None:
    drain_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc"
    ).read_text(encoding="utf-8")
    work_item_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc"
    ).read_text(encoding="utf-8")

    assert "(backlog-drain" in drain_source
    assert "(loop/recur" not in drain_source
    assert "(call project-selector-action" not in drain_source
    assert "record-drain-terminal-outcome-stdlib" in drain_source
    assert "finalize-selected-item" in work_item_source
    assert work_item_source.count("record-work-item-terminal-outcome") <= 1


def test_design_delta_parent_drain_source_shape_finalizer_compat_retirement_removes_helpers_from_ordinary_work_item_routes(
) -> None:
    work_item_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc"
    ).read_text(encoding="utf-8")
    stdlib_adapter_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "stdlib_adapters.orc"
    ).read_text(encoding="utf-8")
    bridge_support_path = (
        REPO_ROOT
        / "workflows"
        / "library"
        / "lisp_frontend_design_delta"
        / "work_item_bridge_support.orc"
    )
    retired_internal_carriers = (
        "SelectedItemStdlibCompat",
        "QueueTransitionCompat",
        "RoadmapCompat",
        "SelectedItemPlanCompat",
        "SelectedItemImplementationCompat",
        "build-finalizer-",
        "call-imported-finalize-selected-item",
        "project-selected-compat",
        "BranchingSelectedCompat",
    )

    for retired_name in retired_internal_carriers:
        assert retired_name not in work_item_source
        assert retired_name not in stdlib_adapter_source

    assert "finalize-selected-item-proc" in work_item_source
    assert not bridge_support_path.exists()


def _design_delta_parent_drain_workflow_signature_block() -> str:
    drain_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc"
    ).read_text(encoding="utf-8")
    return drain_source.split("(defworkflow drain", 1)[1].split("->", 1)[0]


def test_design_delta_parent_drain_public_boundary_source_shape_hides_runtime_inputs() -> None:
    drain_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc"
    ).read_text(encoding="utf-8")
    drain_signature = _design_delta_parent_drain_workflow_signature_block()

    assert "(backlog-drain" in drain_source
    assert "(loop/recur" not in drain_source
    assert "(run RunCtx)" not in drain_signature
    assert "(run_state_path StateExisting)" not in drain_signature
    assert "(:publish" in drain_source
    assert "((DONE :as drain-summary)" in drain_source


def test_design_delta_parent_drain_public_boundary_source_shape_retires_project_drain_result_compat(
) -> None:
    drain_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc"
    ).read_text(encoding="utf-8")
    drain_signature = _design_delta_parent_drain_workflow_signature_block()

    assert "(backlog-drain" in drain_source
    assert "(loop/recur" not in drain_source
    assert "(run RunCtx)" not in drain_signature
    assert "(run_state_path StateExisting)" not in drain_signature
    assert "project-drain-result-compat" not in drain_source
    assert "(:publish" in drain_source
    assert "((DONE :as drain-summary)" in drain_source


def test_workflow_executor_source_shape_does_not_hardcode_entry_compatibility_bridge_bootstrap(
) -> None:
    executor_source = (
        REPO_ROOT / "orchestrator" / "workflow" / "executor.py"
    ).read_text(encoding="utf-8")

    assert "_entry_compatibility_bridge_bindings" not in executor_source
    assert "_supported_entry_compatibility_bridge_binding" not in executor_source
    assert "private_compatibility_bridge_bootstrap_unsupported" not in executor_source
    assert 'return "state/run_state.json"' not in executor_source


def test_design_delta_parent_drain_controlled_smoke_helper_seeds_hidden_run_state_bridge(
) -> None:
    bound_inputs = _design_delta_parent_drain_controlled_smoke_bound_inputs()

    assert bound_inputs["run_state_path"] == "state/run_state.json"
    assert bound_inputs["item-ctx__state-root"] == "state/item"
    assert bound_inputs["phase-ctx__plan__run__run-id"] == "work-item-approved"
    assert (
        bound_inputs["phase-ctx__implementation__run__run-id"]
        == "work-item-approved"
    )
    assert bound_inputs["phase-ctx__work-item__phase-name"] == "work-item"
    assert bound_inputs["phase-ctx__work-item__state-root"] == "state/work-item"
    assert (
        bound_inputs["phase-ctx__work-item__artifact-root"]
        == "artifacts/work-item"
    )
    assert set(bound_inputs).issuperset(_design_delta_parent_drain_bound_inputs())


def test_design_delta_selected_item_stdlib_smoke_helper_matches_real_selected_item_boundary(
    tmp_path: Path,
) -> None:
    bound_inputs = _design_delta_selected_item_stdlib_bound_inputs()
    _workflow_path, result, _lowered_by_name = (
        _compile_design_delta_parent_call_work_item_entrypoint(tmp_path)
    )
    bundle = result.validated_bundles_by_name[
        "lisp_frontend_design_delta/work_item::run-selected-item-stdlib"
    ]
    boundary = workflow_boundary_projection(bundle)
    item_ctx_binding = next(
        binding
        for binding in boundary.private_runtime_context_bindings
        if binding.binding_id == "item-ctx"
    )
    expected_helper_inputs = set(workflow_public_input_contracts(bundle)) | set(
        item_ctx_binding.generated_input_names
    )

    assert set(bound_inputs) == expected_helper_inputs
    assert all(
        "run_state_path" not in binding.generated_input_names
        for binding in boundary.private_runtime_context_bindings
    )
    assert bound_inputs["item-ctx__run__run-id"] == "selected-item-stdlib"
    assert bound_inputs["item-ctx__ledger"] == "state/progress_ledger.json"
    assert bound_inputs["selection__item-id"] == "design-gap-work-item"
    assert bound_inputs["selection__progress_ledger_path"] == "state/progress_ledger.json"
    assert "run_state_path" not in bound_inputs
    assert "selection__run_state_path" not in bound_inputs
    assert "phase-ctx__plan__run__run-id" not in bound_inputs
    assert "phase-ctx__implementation__run__run-id" not in bound_inputs
    assert "run_state_path" not in expected_helper_inputs


def test_design_delta_selected_item_stdlib_keeps_run_state_bridge_private(
    tmp_path: Path,
) -> None:
    work_item_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc"
    ).read_text(encoding="utf-8")
    run_selected_item_stdlib = work_item_source.split(
        "(defworkflow run-selected-item-stdlib", 1
    )[1].split("(defworkflow run-work-item", 1)[0]
    bound_inputs = _design_delta_selected_item_stdlib_bound_inputs()
    _workflow_path, result, _lowered_by_name = (
        _compile_design_delta_parent_call_work_item_entrypoint(tmp_path)
    )
    bundle = result.validated_bundles_by_name[
        "lisp_frontend_design_delta/work_item::run-selected-item-stdlib"
    ]
    boundary = workflow_boundary_projection(bundle)

    assert "(run_state_path RunStatePath)" not in run_selected_item_stdlib
    assert ":run_state_path run_state_path" not in run_selected_item_stdlib
    assert "phase-ctx__plan__run__run-id" not in bound_inputs
    assert "phase-ctx__implementation__run__run-id" not in bound_inputs
    assert "run_state_path" not in bound_inputs
    assert "selection__run_state_path" not in bound_inputs
    assert "run_state_path" not in workflow_public_input_contracts(bundle)
    assert all(
        "run_state_path" not in binding.generated_input_names
        for binding in boundary.private_runtime_context_bindings
    )
    assert boundary.private_compatibility_bridge_inputs == ()


def test_design_delta_selected_item_stdlib_consumes_typed_child_result() -> None:
    work_item_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc"
    ).read_text(encoding="utf-8")
    run_selected_item_stdlib = work_item_source.split(
        "(defworkflow run-selected-item-stdlib", 1
    )[1].split("(defworkflow run-work-item", 1)[0]

    assert "((item-ctx ItemCtx)" in run_selected_item_stdlib or "((item-ctx std/context/ItemCtx)" in run_selected_item_stdlib
    assert "(call run-work-item-pending" not in run_selected_item_stdlib
    assert "(call run-work-item" not in run_selected_item_stdlib
    assert "call-imported-finalize-selected-item" not in run_selected_item_stdlib
    assert "SelectedItemPlanCompat" not in run_selected_item_stdlib
    assert "SelectedItemImplementationCompat" not in run_selected_item_stdlib
    assert "materialize-canonical-work-item-summary" not in run_selected_item_stdlib


def test_design_delta_parent_drain_removes_run_state_from_authored_loop_state(
    tmp_path: Path,
) -> None:
    _result, lowered_by_name = _compile_design_delta_parent_drain_entrypoint(tmp_path)
    types_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "types.orc"
    ).read_text(encoding="utf-8")
    drain_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc"
    ).read_text(encoding="utf-8")
    loop_steps = list(
        _walk_lowered_steps(lowered_by_name["lisp_frontend_design_delta/drain::drain"]["steps"])
    )

    assert (
        "  (defrecord DrainState\n"
        "    (iteration-count Int)\n"
        "    (run-state RunStatePath)\n"
        "    (item-count Int))"
    ) not in types_source
    assert (
        ":state (record DrainState\n"
        "                        :iteration-count 0\n"
        "                        :run-state run_state_path\n"
        "                        :item-count 0)"
    ) not in drain_source
    assert ":run-state state.run-state" not in drain_source
    assert all("state.run-state" not in repr(step) for step in loop_steps)


def test_design_delta_parent_drain_removes_run_state_from_work_item_authored_signatures_while_preserving_private_bridge(
    tmp_path: Path,
) -> None:
    result = _compile_design_delta_work_item_library_module(tmp_path)
    work_item_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc"
    ).read_text(encoding="utf-8")
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "lisp_frontend_design_delta/work_item::run-work-item"
    )
    boundary = lowered.boundary_projection

    assert "(defworkflow run-work-item\n    ((phase-ctx PhaseCtx)" in work_item_source
    assert "(defworkflow run-work-item-phase-route" not in work_item_source
    assert ":phase-ctx phase-ctx" in work_item_source
    assert "(defworkflow run-work-item\n    ((phase-ctx PhaseCtx)\n     (run_state_path RunStatePath)" not in work_item_source
    assert "((run_state_path RunStatePath)" not in work_item_source
    assert "(selection_bundle_path SelectionBundlePath)" not in work_item_source
    assert "(manifest_path StateFileExisting)" not in work_item_source
    assert "(architecture_bundle_path StateFile)" not in work_item_source
    assert "materialize_lisp_frontend_work_item_inputs" not in work_item_source
    assert "state.run-state" not in work_item_source
    assert lowered.compatibility_bridge_inputs == ("progress_ledger_path",)
    assert all(param.name != "run_state_path" for param in boundary.params)


def test_design_delta_parent_drain_runtime_fixture_mirror_stays_aligned_after_r5_cleanup() -> None:
    mirror_root = DESIGN_DELTA_WORK_ITEM_CANDIDATE_ROOT / "lisp_frontend_design_delta"
    authoritative_modules = _design_delta_work_item_runtime_authoritative_modules()

    for name, expected_bytes in authoritative_modules.items():
        assert (mirror_root / name).read_bytes() == expected_bytes


def test_design_delta_parent_drain_preserves_runtime_native_transition_calls_after_r5_cleanup(
    tmp_path: Path,
) -> None:
    result, lowered_by_name = _compile_design_delta_parent_drain_entrypoint(tmp_path)
    drain_steps = list(
        _walk_lowered_steps(lowered_by_name["lisp_frontend_design_delta/drain::drain"]["steps"])
    )
    stdlib_drain_steps = list(
        _walk_lowered_steps(lowered_by_name["std/drain::backlog-drain"]["steps"])
    )
    drain_calls = {
        step.get("call") for step in drain_steps if isinstance(step.get("call"), str)
    }
    source_map = build_source_map_document(
        result,
        selected_name="lisp_frontend_design_delta/drain::drain",
        display_name_resolver=_display_workflow_name,
    )
    imported_transition_markers = (
        "lisp_frontend_design_delta_transitions_record_drain_terminal_outcome",
        "lisp_frontend_design_delta_transitions_record_design_gap_progress",
        "lisp_frontend_design_delta_transitions_record_work_item_terminal_outcome",
        "lisp_frontend_design_delta_transitions_record_work_item_blocked_recovery_summary",
    )
    raw_resource_transition_modules = {
        row.workflow_origin.module_name
        for row in source_map.workflows.values()
        for node in row.core_nodes
        if node.step_kind == "resource_transition"
        and not any(marker in node.step_id for marker in imported_transition_markers)
    }

    assert "std/drain::backlog-drain" in drain_calls
    assert "lisp_frontend_design_delta/drain::drain-runtime-owned" not in lowered_by_name
    assert any("repeat_until" in step for step in stdlib_drain_steps)
    assert "lisp_frontend_design_delta/transitions" in raw_resource_transition_modules
    assert "lisp_frontend_design_delta/drain" not in raw_resource_transition_modules


def test_design_delta_parent_drain_high_level_modules_stop_importing_or_constructing_low_level_transition_requests() -> None:
    drain_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc"
    ).read_text(encoding="utf-8")
    work_item_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc"
    ).read_text(encoding="utf-8")

    assert "DrainStatusRequest" not in drain_source
    assert "write-drain-status" not in drain_source
    assert "TerminalWorkItemRequest" not in work_item_source
    assert "BlockedRecoveryOutcomeRequest" not in work_item_source
    assert "record-terminal-work-item" not in work_item_source
    assert "record-blocked-recovery-outcome" not in work_item_source


def test_design_delta_parent_drain_types_expose_typed_summary_values_at_family_boundary() -> None:
    types_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "types.orc"
    ).read_text(encoding="utf-8")
    work_item_union = types_source.split("(defunion WorkItemResult", 1)[1].split(
        "(defrecord DrainState)", 1
    )[0]
    resolved_inputs = types_source.split("(defrecord ResolvedWorkItemInputs", 1)[1].split(
        "(defrecord ImplementationPhaseResult)", 1
    )[0]
    drain_summary = types_source.split("(defrecord DrainSummaryValue", 1)[1].split(
        "(defrecord WorkItemSummaryValue)", 1
    )[0]
    work_item_summary = types_source.split("(defrecord WorkItemSummaryValue", 1)[1].split(
        "(defunion DesignDeltaDrainAction)", 1
    )[0]
    drain_union = types_source.split("(defunion DrainResult", 1)[1]

    assert "(summary WorkReport)" not in work_item_union
    assert "(summary WorkItemSummaryValue)" in work_item_union
    assert "public_summary_path" not in work_item_union
    assert "(item_summary_target_path WorkReport)" not in resolved_inputs
    assert "(item_summary_target_path WorkReportTarget)" in resolved_inputs
    assert "summary_path" not in work_item_summary
    assert "(drain-summary WorkReport)" not in drain_union
    assert "(drain-summary DrainSummaryValue)" in drain_union
    assert "(run-state StateExisting)" not in drain_union
    assert "run_state_path" not in drain_summary
    assert "summary_target" not in drain_summary


def test_design_delta_parent_drain_summary_cleanup_removes_helper_owned_summary_rendering() -> None:
    transitions_source = (
        REPO_ROOT
        / "workflows"
        / "library"
        / "lisp_frontend_design_delta"
        / "transitions.orc"
    ).read_text(encoding="utf-8")
    work_item_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc"
    ).read_text(encoding="utf-8")
    stdlib_adapters_source = (
        REPO_ROOT
        / "workflows"
        / "library"
        / "lisp_frontend_design_delta"
        / "stdlib_adapters.orc"
    ).read_text(encoding="utf-8")
    std_resource_source = (
        REPO_ROOT
        / "orchestrator"
        / "workflow_lisp"
        / "stdlib_modules"
        / "std"
        / "resource.orc"
    ).read_text(encoding="utf-8")
    route_blocked_work_item = work_item_source.split(
        "(defproc route-blocked-implementation", 1
    )[1].split("(defproc route-blocked-implementation-stdlib", 1)[0]
    route_blocked_stdlib = work_item_source.split(
        "(defproc route-blocked-implementation-stdlib", 1
    )[1].split("(defworkflow run-selected-item-stdlib", 1)[0]
    run_selected_item_stdlib = work_item_source.split(
        "(defworkflow run-selected-item-stdlib", 1
    )[1].split("(defworkflow run-work-item", 1)[0]
    run_work_item = work_item_source.split("(defworkflow run-work-item", 1)[1]

    assert "defrecord RenderedSummary" not in transitions_source
    assert "drain-summary-view" not in transitions_source
    assert "work-item-terminal-summary-view" not in transitions_source
    assert "work-item-blocked-recovery-summary-view" not in transitions_source
    assert "(writes work-item-context-view)" not in transitions_source
    assert "materialize-view work-item-context-view" not in transitions_source
    assert "materialize-selected-item-summary-target" not in work_item_source
    assert "materialize-work-item-summary-bridge" not in work_item_source
    assert "materialize-view blocked-recovery-summary" not in work_item_source
    assert '(defpath WorkReport\n    :kind relpath\n    :under "artifacts/work"\n    :must-exist true)' in std_resource_source
    assert "materialize-view selected-item-summary" not in std_resource_source
    assert "(writes blocked-recovery-summary)" not in work_item_source
    assert "finalize-selected-item-compat" not in stdlib_adapters_source
    assert "(writes selected-item-summary)" not in stdlib_adapters_source
    assert "(writes selected-item-summary)" not in work_item_source
    assert "(writes work-item-summary-bridge)" not in work_item_source
    assert "resolved_inputs.item_summary_target_path" not in route_blocked_work_item
    assert "resolved_inputs.work_item_context_view_target_path" not in route_blocked_stdlib
    assert "(writes canonical-work-item-summary)" not in route_blocked_stdlib
    assert "materialize-canonical-work-item-summary" not in route_blocked_stdlib
    assert "materialize-canonical-work-item-summary" not in run_selected_item_stdlib
    assert "materialize-canonical-work-item-summary" not in run_work_item
    assert "(recorded" not in route_blocked_work_item
    assert "recorded.work_item_id" not in route_blocked_work_item
    assert "recorded.work_item_source" not in route_blocked_work_item
    assert "recorded.terminal_route" not in route_blocked_work_item
    assert "recorded.reason" not in route_blocked_work_item


def test_design_delta_selected_item_stdlib_direct_route_returns_canonical_summary_bridge_path(
    tmp_path: Path,
) -> None:
    workspace, state, provider_calls = _execute_design_delta_selected_item_stdlib_route(
        tmp_path / "selected-item-stdlib-completed",
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
    )

    assert state["status"] == "completed"
    assert provider_calls == [
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-implementation-review",
    ]
    assert state["workflow_outputs"]["return__variant"] == "CONTINUE"
    assert (
        state["workflow_outputs"]["return__summary-path"]
        == "artifacts/work/execution_report.md"
    )
    summary_path = workspace / state["workflow_outputs"]["return__summary-path"]
    assert summary_path.is_file()
    assert not (workspace / "artifacts" / "work" / "item_summary.json").exists()


def test_design_delta_parent_drain_summary_cleanup_removes_authored_summary_path_plumbing() -> None:
    drain_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc"
    ).read_text(encoding="utf-8")
    work_item_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc"
    ).read_text(encoding="utf-8")

    assert "drain-summary-path" not in drain_source
    assert ":drain-summary recorded.summary" not in drain_source
    assert ":summary recorded.summary" not in work_item_source


def test_design_delta_projection_runtime_fixture_compiles(
    tmp_path: Path,
) -> None:
    result = _compile_design_delta_projection_runtime_entrypoint(tmp_path)
    bundle = result.validated_bundles_by_name["design_delta_projection_runtime::run-projection"]

    assert _design_delta_projection_runtime_command_boundaries() == {}
    assert not any(
        name.startswith("lisp_frontend_design_delta/")
        for name in result.validated_bundles_by_name
    )
    assert bundle.surface.steps


def test_design_delta_projection_runtime_fixture_compiles_under_strict_lints(
    tmp_path: Path,
) -> None:
    result = _compile_design_delta_projection_runtime_entrypoint(
        tmp_path,
        lint_profile="strict",
    )
    bundle = result.validated_bundles_by_name["design_delta_projection_runtime::run-projection"]

    assert bundle.surface.steps


def test_design_delta_projection_runtime_fixture_executes_runtime_path(
    tmp_path: Path,
) -> None:
    result = _compile_design_delta_projection_runtime_entrypoint(tmp_path)
    bundle = result.validated_bundles_by_name["design_delta_projection_runtime::run-projection"]
    selection_bundle = tmp_path / "state" / "selection.json"
    selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    selection_bundle.write_text(json.dumps({"selection": "runtime"}) + "\n", encoding="utf-8")

    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    binding_inputs = {
        input_name: contract
        for input_name, contract in runtime_inputs.items()
        if not input_name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        binding_inputs,
        {
            "selection_bundle": "state/selection.json",
            "selection_status": "SELECT_BACKLOG_ITEM",
            "blocked_reason": "gap",
            "implementation_state": "COMPLETED",
            "implementation_review_decision": "APPROVE",
            "work_item_source": "DESIGN_GAP",
            "blocked_recovery_route": "TERMINAL_BLOCKED",
            "blocked_recovery_reason": "user_decision_required",
        },
        tmp_path,
    )
    state_manager = StateManager(
        workspace=tmp_path,
        run_id="design-delta-projection-runtime",
    )
    state_manager.initialize(
        (
            REPO_ROOT
            / "tests"
            / "fixtures"
            / "workflow_lisp"
            / "valid"
            / "design_delta_projection_runtime.orc"
        ).as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="stop")

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__selector_route": "SELECTED_ITEM",
        "return__terminal_route": "COMPLETE",
        "return__blocked_recovery_route": "TERMINAL_BLOCKED",
        "return__blocked_recovery_reason": "user_decision_required",
        "return__selection_bundle": "state/selection.json",
    }


def test_design_delta_parent_family_commands_use_production_adapter_interfaces(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.lowering import _observed_statement_families

    _result, lowered_by_name = _compile_design_delta_parent_drain_entrypoint(tmp_path)
    commands = _all_lowered_commands(lowered_by_name)
    forbidden_scripts = (
        "update_lisp_frontend_run_state.py",
        "record_lisp_frontend_blocked_recovery_outcome.py",
        "write_lisp_frontend_drain_status.py",
        "finalize_lisp_frontend_drain_summary.py",
    )

    for script_name in forbidden_scripts:
        assert all(
            all(script_name not in token for token in command)
            for command in commands
        )

    drain_families = _observed_statement_families(
        lowered_by_name["lisp_frontend_design_delta/drain::drain"]["steps"]
    )
    work_item_families = _observed_statement_families(
        lowered_by_name["lisp_frontend_design_delta/work_item::run-work-item"]["steps"]
    )
    assert "materialize_view" in drain_families
    # Work-item summary artifacts flow through typed artifact materialization;
    # the family's public summary views are entry-boundary publications owned
    # by the drain entrypoint.
    assert "materialize_artifacts" in work_item_families

def test_design_delta_selector_action_projection_rejects_inconsistent_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_path = (
        REPO_ROOT
        / "workflows"
        / "library"
        / "scripts"
        / "project_lisp_frontend_selector_action.py"
    )
    spec = importlib.util.spec_from_file_location(
        "project_lisp_frontend_selector_action_for_test",
        adapter_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    output_bundle = tmp_path / "out.json"
    monkeypatch.setenv("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", output_bundle.as_posix())

    payload = {
        "selection_status": "DONE",
        "selection_bundle_path": "state/selection.json",
        "is_selected": True,
        "is_design_gap": False,
        "is_done": False,
        "is_blocked": False,
        "blocked_reason": "",
    }
    with pytest.raises(SystemExit, match="selection_status conflicts with selector flags"):
        module.main([json.dumps(payload)])

    assert not output_bundle.exists()


def test_design_delta_parent_drain_routes_design_gap_bundle_from_action(
    tmp_path: Path,
) -> None:
    result, lowered_by_name = _compile_design_delta_stdlib_payloads_entrypoint(tmp_path)
    bundle = result.validated_bundles_by_name[
        "lisp_frontend_design_delta/stdlib_payloads::project-selection-result"
    ]

    assert "lisp_frontend_design_delta/stdlib_payloads::project-selection-result" in lowered_by_name
    assert bundle.surface.outputs["return__gap__work_item_id"].from_ref.member == "return__gap__work_item_id"
    assert bundle.surface.outputs["return__gap__plan_target_path"].from_ref.member == (
        "return__gap__plan_target_path"
    )
    assert bundle.surface.outputs["return__gap__plan_target_path"].definition["under"] == "docs/plans"
    assert bundle.surface.outputs["return__gap__architecture_path"].from_ref.member == (
        "return__gap__architecture_path"
    )
    assert bundle.surface.outputs["return__gap__architecture_path"].definition["under"] == "docs/plans"


def test_design_delta_design_gap_architect_prompt_contract_removes_selection_bundle_subject_authority(
) -> None:
    architect_source = (
        REPO_ROOT
        / "workflows"
        / "library"
        / "lisp_frontend_design_delta"
        / "design_gap_architect.orc"
    ).read_text(encoding="utf-8")
    draft_prompt = (
        REPO_ROOT
        / "workflows"
        / "library"
        / "prompts"
        / "lisp_frontend_design_delta_design_gap_architect"
        / "draft_implementation_architecture.md"
    ).read_text(encoding="utf-8")
    revise_prompt = (
        REPO_ROOT
        / "workflows"
        / "library"
        / "prompts"
        / "lisp_frontend_design_delta_design_gap_architect"
        / "revise_implementation_architecture.md"
    ).read_text(encoding="utf-8")

    assert "(selection_bundle SelectionBundlePath)" not in architect_source
    assert ":selection_bundle selection_bundle" not in architect_source
    for prompt_text in (draft_prompt, revise_prompt):
        assert "typed design-gap bootstrap" not in prompt_text.lower()
        assert "selection_bundle" not in prompt_text
        assert "selector bundle" not in prompt_text.lower()
        assert "architecture_path" in prompt_text
        assert "work_item_context_path" in prompt_text
        assert "check_commands_path" in prompt_text
        assert "plan_target_path" in prompt_text


def test_design_delta_blocked_recovery_request_renames_work_item_context_bridge_field() -> None:
    transitions_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "transitions.orc"
    ).read_text(encoding="utf-8")
    work_item_source = (
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc"
    ).read_text(encoding="utf-8")

    assert "(architecture_bundle_path WorkReport)" not in transitions_source
    assert ":architecture_bundle_path work-item-context-view" not in work_item_source
    assert ":work_item_context resolved.work_item_context" in work_item_source


def test_design_delta_work_item_candidate_advances_past_private_workflow_ifexpr_export_blocker(
    tmp_path: Path,
) -> None:
    _assert_design_delta_work_item_advances_past_private_workflow_ifexpr_export_blocker(tmp_path)


def test_design_delta_migration_nested_implementation_phase_compiles(tmp_path: Path) -> None:
    result = _compile_nested_entrypoint_fixture(
        NESTED_IMPLEMENTATION_PHASE_FIXTURE,
        tmp_path=tmp_path,
    )

    assert "nested/implementation-phase" in result.compiled_results_by_name
    assert result.entry_result.validated_bundles


def test_design_delta_migration_nested_implementation_phase_smokes_completed_and_blocked_routes(
    tmp_path: Path,
) -> None:
    completed_workspace, completed_state, completed_provider_calls = (
        _execute_nested_implementation_phase_route(tmp_path / "completed", attempt_variant="COMPLETED")
    )
    blocked_workspace, blocked_state, blocked_provider_calls = _execute_nested_implementation_phase_route(
        tmp_path / "blocked",
        attempt_variant="BLOCKED",
    )

    assert completed_state["status"] == "completed"
    assert completed_provider_calls == ["fake-execute", "fake-review"]
    assert completed_state["workflow_outputs"] == {
        "return__execution_report": "artifacts/work/execution_report.md",
        "return__progress_report": "artifacts/work/execution_report.md",
        "return__checks_report": "artifacts/work/checks_report.md",
        "return__implementation_review_report": "artifacts/work/implementation_review_report.md",
    }
    assert (completed_workspace / "artifacts" / "work" / "checks_report.md").is_file()
    assert (completed_workspace / "artifacts" / "review" / "review_report.md").is_file()

    assert blocked_state["status"] == "completed"
    assert blocked_provider_calls == ["fake-execute"]
    assert blocked_state["workflow_outputs"] == {
        "return__execution_report": "artifacts/work/progress_report.md",
        "return__progress_report": "artifacts/work/progress_report.md",
        "return__checks_report": "artifacts/work/progress_report.md",
        "return__implementation_review_report": "artifacts/work/implementation_review_report.md",
    }
    assert (blocked_workspace / "artifacts" / "work" / "progress_report.md").is_file()
    assert not (blocked_workspace / "artifacts" / "review" / "review_report.md").exists()


def test_design_delta_implementation_phase_candidate_smokes_completed_and_blocked_routes(
    tmp_path: Path,
) -> None:
    completed_workspace, completed_state, completed_provider_calls, _completed_provider_contexts = (
        _execute_design_delta_implementation_phase_route(tmp_path / "completed", attempt_variant="COMPLETED")
    )
    revised_workspace, revised_state, revised_provider_calls, revised_provider_contexts = (
        _execute_design_delta_implementation_phase_route(
        tmp_path / "revised",
        attempt_variant="COMPLETED",
        review_sequence=("REVISE", "APPROVE"),
    ))
    blocked_workspace, blocked_state, blocked_provider_calls, _blocked_provider_contexts = (
        _execute_design_delta_implementation_phase_route(
        tmp_path / "blocked",
        attempt_variant="BLOCKED",
    ))

    assert completed_state["status"] == "completed"
    assert completed_provider_calls == ["fake-execute", "fake-review"]
    assert completed_state["workflow_outputs"] == {
        "return__implementation-state": "COMPLETED",
        "return__implementation-review-decision": "APPROVE",
        "return__blocker-class": "missing_resource",
        "return__execution-report": "artifacts/work/execution_report.md",
        "return__progress-report": "artifacts/work/progress_report.md",
        "return__checks-report": "artifacts/checks/checks_report.md",
        "return__implementation-review-report": "artifacts/review/implementation_review_report.md",
    }
    assert (completed_workspace / "artifacts" / "checks" / "checks_report.md").is_file()
    assert (completed_workspace / "artifacts" / "review" / "implementation_review_report.md").is_file()
    assert (completed_workspace / "artifacts" / "work" / "progress_report.md").is_file()

    assert revised_state["status"] == "completed"
    assert revised_provider_calls == ["fake-execute", "fake-review", "fake-fix", "fake-review"]
    assert revised_state["workflow_outputs"] == {
        "return__implementation-state": "COMPLETED",
        "return__implementation-review-decision": "APPROVE",
        "return__blocker-class": "missing_resource",
        "return__execution-report": "artifacts/work/execution_report.md",
        "return__progress-report": "artifacts/work/progress_report.md",
        "return__checks-report": "artifacts/checks/checks_report.md",
        "return__implementation-review-report": "artifacts/review/implementation_review_report.md",
    }
    assert _state_contains_artifact_value(
        revised_state,
        "state__completed__execution_report",
        "artifacts/work/execution_report_fixed.md",
    )
    assert (revised_workspace / "artifacts" / "work" / "execution_report_fixed.md").is_file()
    assert (revised_workspace / "artifacts" / "checks" / "checks_report.md").is_file()
    assert (revised_workspace / "artifacts" / "review" / "implementation_review_report.md").is_file()
    assert (revised_workspace / "artifacts" / "work" / "progress_report.md").is_file()

    assert blocked_state["status"] == "completed"
    assert blocked_provider_calls == ["fake-execute"]
    assert blocked_state["workflow_outputs"] == {
        "return__implementation-state": "BLOCKED",
        "return__implementation-review-decision": "NOT_APPLICABLE",
        "return__blocker-class": "external_dependency_outside_authority",
        "return__execution-report": "artifacts/work/progress_report.md",
        "return__progress-report": "artifacts/work/progress_report.md",
        "return__checks-report": "artifacts/checks/checks_report.md",
        "return__implementation-review-report": "artifacts/review/implementation_review_report.md",
    }
    assert (blocked_workspace / "artifacts" / "work" / "progress_report.md").is_file()
    assert not (blocked_workspace / "artifacts" / "work" / "execution_report.md").exists()
    # The blocked route materializes compatibility checks/review report views.
    assert (blocked_workspace / "artifacts" / "checks" / "checks_report.md").is_file()
    assert (
        blocked_workspace / "artifacts" / "review" / "implementation_review_report.md"
    ).is_file()


def test_design_delta_parent_call_implementation_phase_smokes_completed_and_blocked_routes(
    tmp_path: Path,
) -> None:
    completed_workspace, completed_state, completed_provider_calls, _completed_provider_contexts = (
        _execute_design_delta_parent_call_route(tmp_path / "completed", attempt_variant="COMPLETED")
    )
    revised_workspace, revised_state, revised_provider_calls, revised_provider_contexts = (
        _execute_design_delta_parent_call_route(
        tmp_path / "revised",
        attempt_variant="COMPLETED",
        review_sequence=("REVISE", "APPROVE"),
    ))
    blocked_workspace, blocked_state, blocked_provider_calls, _blocked_provider_contexts = (
        _execute_design_delta_parent_call_route(
        tmp_path / "blocked",
        attempt_variant="BLOCKED",
    ))

    assert completed_state["status"] == "completed"
    assert completed_provider_calls == ["fake-execute", "fake-review"]
    assert completed_state["workflow_outputs"] == {
        "return__implementation-state": "COMPLETED",
        "return__implementation-review-decision": "APPROVE",
        "return__blocker-class": "missing_resource",
        "return__execution-report": "artifacts/work/execution_report.md",
        "return__progress-report": "artifacts/work/progress_report.md",
        "return__checks-report": "artifacts/checks/checks_report.md",
        "return__implementation-review-report": "artifacts/review/implementation_review_report.md",
    }
    assert (completed_workspace / "artifacts" / "checks" / "checks_report.md").is_file()
    assert (completed_workspace / "artifacts" / "review" / "implementation_review_report.md").is_file()
    assert (completed_workspace / "artifacts" / "work" / "progress_report.md").is_file()

    assert revised_state["status"] == "completed"
    assert revised_provider_calls == ["fake-execute", "fake-review", "fake-fix", "fake-review"]
    assert revised_state["workflow_outputs"] == {
        "return__implementation-state": "COMPLETED",
        "return__implementation-review-decision": "APPROVE",
        "return__blocker-class": "missing_resource",
        "return__execution-report": "artifacts/work/execution_report.md",
        "return__progress-report": "artifacts/work/progress_report.md",
        "return__checks-report": "artifacts/checks/checks_report.md",
        "return__implementation-review-report": "artifacts/review/implementation_review_report.md",
    }
    assert _state_contains_artifact_value(
        revised_state,
        "state__completed__execution_report",
        "artifacts/work/execution_report_fixed.md",
    )
    assert (revised_workspace / "artifacts" / "work" / "execution_report_fixed.md").is_file()
    assert (revised_workspace / "artifacts" / "checks" / "checks_report.md").is_file()
    assert (revised_workspace / "artifacts" / "review" / "implementation_review_report.md").is_file()
    assert (revised_workspace / "artifacts" / "work" / "progress_report.md").is_file()

    assert blocked_state["status"] == "completed"
    assert blocked_provider_calls == ["fake-execute"]
    assert blocked_state["workflow_outputs"] == {
        "return__implementation-state": "BLOCKED",
        "return__implementation-review-decision": "NOT_APPLICABLE",
        "return__blocker-class": "external_dependency_outside_authority",
        "return__execution-report": "artifacts/work/progress_report.md",
        "return__progress-report": "artifacts/work/progress_report.md",
        "return__checks-report": "artifacts/checks/checks_report.md",
        "return__implementation-review-report": "artifacts/review/implementation_review_report.md",
    }
    assert (blocked_workspace / "artifacts" / "work" / "progress_report.md").is_file()
    assert not (blocked_workspace / "artifacts" / "work" / "execution_report.md").exists()
    # The blocked route materializes compatibility checks/review report views.
    assert (blocked_workspace / "artifacts" / "checks" / "checks_report.md").is_file()
    assert (
        blocked_workspace / "artifacts" / "review" / "implementation_review_report.md"
    ).is_file()


def test_design_delta_work_item_candidate_smokes_complete_and_blocked_recovery_routes(
    tmp_path: Path,
) -> None:
    completed_workspace, completed_state, completed_provider_calls = _execute_design_delta_work_item_route(
        tmp_path / "completed",
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
    )
    blocked_workspace, blocked_state, blocked_provider_calls = _execute_design_delta_work_item_route(
        tmp_path / "blocked",
        plan_variant="APPROVED",
        implementation_variant="BLOCKED",
        work_item_source="DRAFT_DESIGN_GAP",
    )

    assert completed_state["status"] == "completed"
    assert completed_provider_calls == [
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-implementation-review",
    ]
    assert completed_state["workflow_outputs"]["return__variant"] == "COMPLETED"
    assert completed_state["workflow_outputs"]["return__reason"] == ""
    assert completed_state["workflow_outputs"]["return__summary__terminal_route"] == "COMPLETED"
    assert completed_state["workflow_outputs"]["return__summary__reason"] == "complete"
    assert completed_state["workflow_outputs"]["return__summary__work_item_id"] == "design-gap-work-item"
    assert completed_state["workflow_outputs"]["return__summary__work_item_source"] == "DESIGN_GAP"
    assert "return__public_summary_path" not in completed_state["workflow_outputs"]
    assert "return__summary-path" not in completed_state["workflow_outputs"]
    assert "return__summary__summary_path" not in completed_state["workflow_outputs"]
    assert (completed_workspace / "artifacts" / "work" / "execution_report.md").is_file()
    assert not (completed_workspace / "artifacts" / "work" / "item_summary.json").exists()
    assert (completed_workspace / "artifacts" / "review" / "implementation_review_report.md").is_file()

    assert blocked_state["status"] == "completed"
    assert blocked_provider_calls == [
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-work-item-recovery",
    ]
    assert blocked_state["workflow_outputs"]["return__variant"] == "BLOCKED_RECOVERY"
    assert blocked_state["workflow_outputs"]["return__reason"] == "gap_design_revision_required"
    assert (
        blocked_state["workflow_outputs"]["return__summary__terminal_route"]
        == "BLOCKED_RECOVERY"
    )
    assert (
        blocked_state["workflow_outputs"]["return__summary__reason"]
        == "gap_design_revision_required"
    )
    assert blocked_state["workflow_outputs"]["return__summary__work_item_id"] == "design-gap-work-item"
    assert blocked_state["workflow_outputs"]["return__summary__work_item_source"] == "DESIGN_GAP"
    assert "return__public_summary_path" not in blocked_state["workflow_outputs"]
    assert "return__summary-path" not in blocked_state["workflow_outputs"]
    assert "return__summary__summary_path" not in blocked_state["workflow_outputs"]
    assert (blocked_workspace / "artifacts" / "work" / "progress_report.md").is_file()
    assert not (blocked_workspace / "artifacts" / "work" / "item_summary.json").exists()
    blocked_run_state = json.loads(
        (blocked_workspace / "state" / "run_state.json").read_text(encoding="utf-8")
    )
    assert "blocked_recovery_reason" not in blocked_run_state
    assert "blocked_recovery_summary" not in blocked_run_state


def test_design_delta_runtime_compile_bundle_removes_authored_summary_bridge_steps(
    tmp_path: Path,
) -> None:
    workflow_path, result = _compile_design_delta_work_item_runtime_entrypoint(tmp_path)
    del workflow_path

    work_item_bundle = result.entry_result.validated_bundles[
        "lisp_frontend_design_delta/work_item::run-work-item"
    ]
    work_item_step_ids = {
        step.step_id
        for step in work_item_bundle.surface.steps
        if isinstance(step.step_id, str)
    }
    assert not any("work-item-summary-bridge" in step_id for step_id in work_item_step_ids)
    assert not any("selected-item-summary" in step_id for step_id in work_item_step_ids)

    drain_result, _lowered_by_name = _compile_design_delta_parent_drain_entrypoint(
        tmp_path / "parent"
    )
    drain_bundle = drain_result.entry_result.validated_bundles[
        "lisp_frontend_design_delta/drain::drain"
    ]
    imported_work_item_bundle = drain_bundle.imports[
        "lisp_frontend_design_delta/work_item::run-work-item"
    ]
    imported_step_ids = {
        step.step_id
        for step in imported_work_item_bundle.surface.steps
        if isinstance(step.step_id, str)
    }
    assert not any("work-item-summary-bridge" in step_id for step_id in imported_step_ids)
    assert not any("selected-item-summary" in step_id for step_id in imported_step_ids)


def test_design_delta_runtime_compile_bundle_catalogs_agree_on_summary_bridge_steps(
    tmp_path: Path,
) -> None:
    _workflow_path, result = _compile_design_delta_work_item_runtime_entrypoint(tmp_path)

    entry_bundle = result.entry_result.validated_bundles[
        "lisp_frontend_design_delta/work_item::run-work-item"
    ]
    by_name_bundle = result.validated_bundles_by_name[
        "lisp_frontend_design_delta/work_item::run-work-item"
    ]
    entry_bridge_step_ids = {
        step.step_id
        for step in entry_bundle.surface.steps
        if isinstance(step.step_id, str) and step.step_id.startswith("compatibility_bridge__")
    }
    by_name_bridge_step_ids = {
        step.step_id
        for step in by_name_bundle.surface.steps
        if isinstance(step.step_id, str) and step.step_id.startswith("compatibility_bridge__")
    }
    assert not entry_bridge_step_ids
    assert not by_name_bridge_step_ids
    assert by_name_bridge_step_ids == entry_bridge_step_ids

    drain_result, _lowered_by_name = _compile_design_delta_parent_drain_entrypoint(
        tmp_path / "parent"
    )
    drain_entry_bundle = drain_result.entry_result.validated_bundles[
        "lisp_frontend_design_delta/drain::drain"
    ]
    drain_by_name_bundle = drain_result.validated_bundles_by_name[
        "lisp_frontend_design_delta/drain::drain"
    ]
    imported_entry_bundle = drain_entry_bundle.imports[
        "lisp_frontend_design_delta/work_item::run-work-item"
    ]
    imported_by_name_bundle = drain_by_name_bundle.imports[
        "lisp_frontend_design_delta/work_item::run-work-item"
    ]
    imported_entry_bridge_step_ids = {
        step.step_id
        for step in imported_entry_bundle.surface.steps
        if isinstance(step.step_id, str) and step.step_id.startswith("compatibility_bridge__")
    }
    imported_by_name_bridge_step_ids = {
        step.step_id
        for step in imported_by_name_bundle.surface.steps
        if isinstance(step.step_id, str) and step.step_id.startswith("compatibility_bridge__")
    }
    assert not imported_entry_bridge_step_ids
    assert not imported_by_name_bridge_step_ids
    assert imported_by_name_bridge_step_ids == imported_entry_bridge_step_ids

def test_design_delta_work_item_candidate_smokes_terminal_blocked_route(
    tmp_path: Path,
) -> None:
    workspace, state, provider_calls = _execute_design_delta_work_item_route(
        tmp_path / "plan-blocked",
        plan_variant="BLOCKED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
    )

    assert state["status"] == "completed"
    assert provider_calls == ["fake-plan-draft", "fake-plan-review"]
    assert state["workflow_outputs"]["return__variant"] == "TERMINAL_BLOCKED"
    assert state["workflow_outputs"]["return__reason"] == "plan_blocked"
    assert state["workflow_outputs"]["return__summary__terminal_route"] == "TERMINAL_BLOCKED"
    assert state["workflow_outputs"]["return__summary__reason"] == "plan_blocked"
    assert state["workflow_outputs"]["return__summary__work_item_id"] == "design-gap-work-item"
    assert state["workflow_outputs"]["return__summary__work_item_source"] == "DESIGN_GAP"
    assert "return__public_summary_path" not in state["workflow_outputs"]
    assert "return__summary-path" not in state["workflow_outputs"]
    assert "return__summary__summary_path" not in state["workflow_outputs"]
    assert not (workspace / "artifacts" / "work" / "item_summary.json").exists()
    assert not (workspace / "artifacts" / "work" / "execution_report.md").exists()
    progress_report = workspace / "artifacts" / "work" / "progress_report.md"
    assert progress_report.is_file()
    assert json.loads(progress_report.read_text(encoding="utf-8")) == {
        "blocker_class": "roadmap_conflict",
        "plan_path": "docs/plans/generated_plan.md",
        "reason": "plan_blocked",
        "review_report": "artifacts/review/plan_review_report.md",
        "status": "BLOCKED",
    }

def test_design_delta_parent_call_work_item_smokes_complete_and_blocked_recovery_routes(
    tmp_path: Path,
) -> None:
    completed_workspace, completed_state, completed_provider_calls = (
        _execute_design_delta_parent_call_work_item_route(
            tmp_path / "completed",
            plan_variant="APPROVED",
            implementation_variant="COMPLETED",
            work_item_source="DRAFT_DESIGN_GAP",
        )
    )
    blocked_workspace, blocked_state, blocked_provider_calls = (
        _execute_design_delta_parent_call_work_item_route(
            tmp_path / "blocked",
            plan_variant="APPROVED",
            implementation_variant="BLOCKED",
            work_item_source="DRAFT_DESIGN_GAP",
        )
    )

    assert completed_state["status"] == "completed"
    assert completed_provider_calls == [
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-implementation-review",
    ]
    assert completed_state["workflow_outputs"]["return__variant"] == "COMPLETED"
    assert completed_state["workflow_outputs"]["return__reason"] == ""
    assert completed_state["workflow_outputs"]["return__summary__terminal_route"] == "COMPLETED"
    assert completed_state["workflow_outputs"]["return__summary__reason"] == "complete"
    assert "return__summary-path" not in completed_state["workflow_outputs"]
    assert "return__summary__summary_path" not in completed_state["workflow_outputs"]
    assert (completed_workspace / "artifacts" / "work" / "execution_report.md").is_file()
    assert not (completed_workspace / "artifacts" / "work" / "item_summary.json").exists()

    assert blocked_state["status"] == "completed"
    assert blocked_provider_calls == [
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-work-item-recovery",
    ]
    assert blocked_state["workflow_outputs"]["return__variant"] == "BLOCKED_RECOVERY"
    assert blocked_state["workflow_outputs"]["return__reason"] == "gap_design_revision_required"
    assert (
        blocked_state["workflow_outputs"]["return__summary__terminal_route"]
        == "BLOCKED_RECOVERY"
    )
    assert (
        blocked_state["workflow_outputs"]["return__summary__reason"]
        == "gap_design_revision_required"
    )
    assert "return__summary-path" not in blocked_state["workflow_outputs"]
    assert "return__summary__summary_path" not in blocked_state["workflow_outputs"]
    assert (blocked_workspace / "artifacts" / "work" / "progress_report.md").is_file()
    assert not (blocked_workspace / "artifacts" / "work" / "item_summary.json").exists()
    blocked_run_state = json.loads(
        (blocked_workspace / "state" / "run_state.json").read_text(encoding="utf-8")
    )
    assert "blocked_recovery_reason" not in blocked_run_state
    assert "blocked_recovery_summary" not in blocked_run_state

def test_design_delta_parent_call_work_item_smokes_terminal_blocked_route(
    tmp_path: Path,
) -> None:
    workspace, state, provider_calls = _execute_design_delta_parent_call_work_item_route(
        tmp_path / "plan-blocked",
        plan_variant="BLOCKED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
    )

    assert state["status"] == "completed"
    assert provider_calls == ["fake-plan-draft", "fake-plan-review"]
    assert state["workflow_outputs"]["return__variant"] == "TERMINAL_BLOCKED"
    assert state["workflow_outputs"]["return__reason"] == "plan_blocked"
    assert state["workflow_outputs"]["return__summary__terminal_route"] == "TERMINAL_BLOCKED"
    assert state["workflow_outputs"]["return__summary__reason"] == "plan_blocked"
    assert "return__summary-path" not in state["workflow_outputs"]
    assert "return__summary__summary_path" not in state["workflow_outputs"]
    assert not (workspace / "artifacts" / "work" / "item_summary.json").exists()
    assert not (workspace / "artifacts" / "work" / "execution_report.md").exists()
    assert (workspace / "artifacts" / "work" / "progress_report.md").is_file()


def test_design_delta_parent_drain_smokes_runtime_transition_fixture_emits_audit_handoff(
    tmp_path: Path,
) -> None:
    workspace, state, native_state_path, audit_path = _execute_design_delta_runtime_transition_fixture(
        tmp_path / "runtime-transition-fixture"
    )

    assert state["status"] == "completed"
    step_state = next(iter(state["steps"].values()))
    assert step_state["status"] == "completed"
    assert step_state["debug"]["resource_transition"]["backend"] == "runtime_native"
    assert (workspace / "artifacts" / "work" / "drain_summary.json").is_file()

    run_state = json.loads(native_state_path.read_text(encoding="utf-8"))
    run_state = run_state["state"]
    assert run_state["drain_status"] == "BLOCKED"
    assert run_state["drain_status_reason"] == "runtime_native_fixture"
    assert run_state["drain_status_summary"] == "artifacts/work/drain_summary.json"

    audit_rows = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert audit_rows[-1]["outcome_code"] == "committed"
    assert audit_rows[-1]["transition_name"] == "write-drain-status-runtime-native"
    assert audit_rows[-1]["resource_kind"] == "drain_run_state"


def test_design_delta_parent_drain_smokes_selected_item_completed_path(
    tmp_path: Path,
) -> None:
    workspace, state, provider_calls = _execute_design_delta_parent_drain_route(
        tmp_path / "parent-completed",
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        selector_status=("SELECT_BACKLOG_ITEM", "DONE"),
    )

    assert state["status"] == "completed"
    assert provider_calls == [
        "fake-selector",
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-implementation-review",
        "fake-selector",
    ]
    assert state["workflow_outputs"]["return__variant"] == "DONE"
    assert "return__run-state" not in state["workflow_outputs"]
    assert state["workflow_outputs"]["return__drain-summary__drain_status"] == "DONE"
    assert state["workflow_outputs"]["return__drain-summary__drain_status_reason"] == ""
    assert "return__drain-summary__run_state_path" not in state["workflow_outputs"]
    assert "return__drain-summary__summary_target" not in state["workflow_outputs"]
    assert (workspace / "artifacts" / "work" / "drain_summary.json").is_file()
    # Interior item_summary.json publication is retired: the selected-item
    # outcome is durable through the state-layout-backed resource record.
    assert not (workspace / "artifacts" / "work" / "item_summary.json").exists()
    selected_item_outcome = json.loads(
        (
            workspace
            / "state"
            / "workflow_lisp"
            / "lisp-frontend-design-delta-work-item--finalize-selected-item-from-completed-implementation"
            / "selected-item-outcome-state.json"
        ).read_text(encoding="utf-8")
    )["state"]
    assert selected_item_outcome["variant"] == "CONTINUE"
    plan_bound_inputs = _call_frame_bound_inputs_for_import_alias(
        state,
        "lisp_frontend_design_delta/plan_phase::run-plan-phase",
    )
    plan_frame = _call_frame_snapshot_for_import_alias(
        state,
        "lisp_frontend_design_delta/plan_phase::run-plan-phase",
    )
    assert plan_bound_inputs["phase-ctx__run__run-id"] == "work-item-approved"
    assert plan_bound_inputs["phase-ctx__phase-name"] == "plan"
    assert plan_bound_inputs["phase-ctx__state-root"] == "state/plan"
    assert plan_bound_inputs["phase-ctx__artifact-root"] == "artifacts/plan"
    assert plan_frame["workflow_file"] == "lisp_frontend_design_delta/plan_phase.orc"
    assert any(name.startswith("__write_root__") for name in plan_bound_inputs)
    assert not any(
        isinstance(value, str) and value.startswith("state/test-smoke/")
        for name, value in plan_bound_inputs.items()
        if isinstance(name, str) and name.startswith("__write_root__")
    )
    implementation_bound_inputs = _call_frame_bound_inputs_for_import_alias(
        state,
        "lisp_frontend_design_delta/implementation_phase::implementation-phase",
    )
    implementation_frame = _call_frame_snapshot_for_import_alias(
        state,
        "lisp_frontend_design_delta/implementation_phase::implementation-phase",
    )
    assert implementation_bound_inputs["phase-ctx__run__run-id"] == "work-item-approved"
    assert implementation_bound_inputs["phase-ctx__phase-name"] == "implementation"
    assert implementation_bound_inputs["phase-ctx__state-root"] == "state/implementation"
    assert implementation_bound_inputs["phase-ctx__artifact-root"] == "artifacts/implementation"
    assert implementation_frame["workflow_file"] == "lisp_frontend_design_delta/implementation_phase.orc"
    assert any(name.startswith("__write_root__") for name in implementation_bound_inputs)


def test_design_delta_parent_drain_continues_after_selected_item_completion(
    tmp_path: Path,
) -> None:
    workspace, state, provider_calls = _execute_design_delta_parent_drain_route(
        tmp_path / "parent-completed-then-done",
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        selector_status=("SELECT_BACKLOG_ITEM", "DONE"),
    )

    assert state["status"] == "completed"
    assert provider_calls == [
        "fake-selector",
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-implementation-review",
        "fake-selector",
    ]
    assert state["workflow_outputs"]["return__variant"] == "DONE"
    assert (workspace / "artifacts" / "work" / "drain_summary.json").is_file()
    assert (workspace / "artifacts" / "work" / "execution_report.md").is_file()


def test_design_delta_parent_drain_exhausts_with_typed_result_at_authored_bound(
    tmp_path: Path,
) -> None:
    workspace, state, provider_calls = _execute_design_delta_parent_drain_route(
        tmp_path / "parent-exhausted",
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        selector_status=(
            "SELECT_BACKLOG_ITEM",
            "SELECT_BACKLOG_ITEM",
            "SELECT_BACKLOG_ITEM",
            "DONE",
        ),
    )

    assert state["status"] == "completed"
    assert provider_calls == [
        "fake-selector",
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-implementation-review",
        "fake-selector",
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-implementation-review",
        "fake-selector",
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-implementation-review",
    ]
    assert state["workflow_outputs"]["return__variant"] == "EXHAUSTED"
    assert state["workflow_outputs"]["return__reason"] == "max_iterations_exhausted"
    assert "return__run-state" not in state["workflow_outputs"]
    assert state["workflow_outputs"]["return__drain-summary__drain_status"] == "EXHAUSTED"
    assert (
        state["workflow_outputs"]["return__drain-summary__drain_status_reason"]
        == "max_iterations_exhausted"
    )
    assert (workspace / "artifacts" / "work" / "drain_summary.json").is_file()
    assert (workspace / "artifacts" / "work" / "selection_bundle.md").is_file()
    # Interior item_summary.json publication is retired on the promoted route.
    assert not (workspace / "artifacts" / "work" / "item_summary.json").exists()


def test_design_delta_parent_drain_smokes_blocked_recovery_path(
    tmp_path: Path,
) -> None:
    workspace, state, provider_calls = _execute_design_delta_parent_drain_route(
        tmp_path / "parent-blocked",
        plan_variant="APPROVED",
        implementation_variant="BLOCKED",
        work_item_source="DRAFT_DESIGN_GAP",
        selector_status=("SELECT_BACKLOG_ITEM", "BLOCKED"),
    )

    assert state["status"] == "completed"
    assert provider_calls == [
        "fake-selector",
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-work-item-recovery",
    ]
    assert state["workflow_outputs"]["return__variant"] == "BLOCKED"
    assert state["workflow_outputs"]["return__reason"] == "selector_blocked"
    assert "return__run-state" not in state["workflow_outputs"]
    assert state["workflow_outputs"]["return__drain-summary__drain_status"] == "BLOCKED"
    assert (
        state["workflow_outputs"]["return__drain-summary__drain_status_reason"]
        == "selector_blocked"
    )
    assert (workspace / "artifacts" / "work" / "progress_report.md").is_file()
    assert (workspace / "artifacts" / "work" / "drain_summary.json").is_file()
    # Interior item_summary.json publication is retired: blocked-recovery
    # durability flows through the state-layout-backed resource record.
    assert not (workspace / "artifacts" / "work" / "item_summary.json").exists()
    recovery_state = _native_drain_run_state(
        workspace,
        "lisp-frontend-design-delta-work-item--run-selected-item-stdlib",
    )
    assert recovery_state["blocked_recovery_reason"] == "implementation_architecture_under_scoped"
    assert recovery_state["blocked_recovery_summary"] == "artifacts/work/progress_report.md"


def test_design_delta_parent_drain_design_gap_retry_runs_prepared_item(
    tmp_path: Path,
) -> None:
    workspace, state, provider_calls = _execute_design_delta_parent_drain_route(
        tmp_path / "parent-design-gap-then-item",
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        selector_status=("DRAFT_DESIGN_GAP", "SELECT_BACKLOG_ITEM", "DONE"),
    )

    assert state["status"] == "completed"
    assert provider_calls == [
        "fake-selector",
        "fake-architect-draft",
        "fake-selector",
        "fake-plan-draft",
        "fake-plan-review",
        "fake-implementation-execute",
        "fake-implementation-review",
        "fake-selector",
    ]
    assert state["workflow_outputs"]["return__variant"] == "DONE"
    assert (workspace / "artifacts" / "work" / "drain_summary.json").is_file()
    assert (workspace / "artifacts" / "work" / "execution_report.md").is_file()


def test_design_delta_parent_drain_design_gap_converges_via_recorded_run_state(
    tmp_path: Path,
) -> None:
    expected_gap_id = DESIGN_GAP_SMOKE_IDENTITY
    selector_observations: list[dict[str, object]] = []
    workspace, state, provider_calls = _execute_design_delta_parent_drain_route(
        tmp_path / "parent-design-gap-recorded-progress",
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        work_item_id=expected_gap_id,
        selector_mode="state_driven_design_gap",
        selector_observations=selector_observations,
    )

    assert state["status"] == "completed"
    assert provider_calls == ["fake-selector", "fake-architect-draft", "fake-selector"]
    assert state["workflow_outputs"]["return__variant"] == "DONE"
    gap_progress = _native_drain_run_state(
        workspace,
        "lisp-frontend-design-delta-stdlib-adapters--draft-design-gap-stdlib",
    )
    assert gap_progress["completed_design_gaps"] == [expected_gap_id]
    assert [obs["decision"] for obs in selector_observations] == [
        "DRAFT_DESIGN_GAP",
        "DONE",
    ]
    assert selector_observations[0]["bound_run_state_path"] is None
    assert str(selector_observations[1]["bound_run_state_path"]).endswith(
        "drain-run-state-state.json"
    )
    assert not any(obs["forced_tuple"] for obs in selector_observations)
    assert not (workspace / "artifacts" / "work" / "item_summary.json").exists()


def test_design_delta_parent_drain_design_gap_exhausts_without_recorded_progress(
    tmp_path: Path,
) -> None:
    expected_gap_id = DESIGN_GAP_SMOKE_IDENTITY
    workspace, state, provider_calls = _execute_design_delta_parent_drain_route(
        tmp_path / "parent-design-gap-without-progress",
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        work_item_id=expected_gap_id,
        selector_status=(
            "DRAFT_DESIGN_GAP",
            "DRAFT_DESIGN_GAP",
            "DRAFT_DESIGN_GAP",
            "DONE",
        ),
    )

    assert state["status"] == "completed"
    assert provider_calls == [
        "fake-selector",
        "fake-architect-draft",
        "fake-selector",
        "fake-architect-draft",
        "fake-selector",
        "fake-architect-draft",
    ]
    assert state["workflow_outputs"]["return__variant"] == "EXHAUSTED"
    assert state["workflow_outputs"]["return__reason"] == "max_iterations_exhausted"


def test_design_delta_parent_drain_imported_selector_ctx_carried_context_smoke(
    tmp_path: Path,
) -> None:
    workspace, state, provider_calls = _execute_design_delta_parent_drain_route(
        tmp_path / "parent-imported-selector-carried-context",
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        selector_status=("DRAFT_DESIGN_GAP", "DONE"),
    )

    assert state["status"] == "completed"
    assert provider_calls == ["fake-selector", "fake-architect-draft", "fake-selector"]
    assert not _state_contains_failed_contract_violation(
        state,
        reason="private_exec_context_bootstrap_unsupported",
    )
    assert state["workflow_outputs"]["return__variant"] == "DONE"
    assert "return__run-state" not in state["workflow_outputs"]
    assert (workspace / "artifacts" / "work" / "drain_summary.json").is_file()
    assert not (workspace / "artifacts" / "work" / "item_summary.json").exists()


def test_design_delta_parent_drain_smokes_selector_design_gap_path(
    tmp_path: Path,
) -> None:
    workspace, state, provider_calls = _execute_design_delta_parent_drain_route(
        tmp_path / "parent-design-gap",
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        selector_status=("DRAFT_DESIGN_GAP", "DONE"),
    )

    assert state["status"] == "completed"
    assert provider_calls == ["fake-selector", "fake-architect-draft", "fake-selector"]
    assert state["workflow_outputs"]["return__variant"] == "DONE"
    assert (workspace / "artifacts" / "work" / "drain_summary.json").is_file()
    assert not (workspace / "artifacts" / "work" / "item_summary.json").exists()


def test_design_delta_parent_drain_smokes_selector_done_path(
    tmp_path: Path,
) -> None:
    workspace, state, provider_calls = _execute_design_delta_parent_drain_route(
        tmp_path / "parent-done",
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        selector_status="DONE",
    )

    assert state["status"] == "completed"
    assert provider_calls == ["fake-selector"]
    assert state["workflow_outputs"]["return__variant"] == "DONE"
    assert "return__run-state" not in state["workflow_outputs"]
    assert state["workflow_outputs"]["return__drain-summary__drain_status"] == "DONE"
    assert (workspace / "artifacts" / "work" / "drain_summary.json").is_file()
    assert not (workspace / "artifacts" / "work" / "item_summary.json").exists()
    run_state = _native_drain_run_state(workspace, "lisp-frontend-design-delta-drain--drain")
    assert run_state["drain_status"] == "DONE"
    assert run_state["drain_status_reason"] == ""
    assert run_state["drain_status_summary"] == "artifacts/work/drain_summary.json"


def test_design_delta_parent_drain_smokes_selector_blocked_path(
    tmp_path: Path,
) -> None:
    workspace, state, provider_calls = _execute_design_delta_parent_drain_route(
        tmp_path / "parent-blocked-selector",
        plan_variant="APPROVED",
        implementation_variant="COMPLETED",
        work_item_source="DRAFT_DESIGN_GAP",
        selector_status="BLOCKED",
    )

    assert state["status"] == "completed"
    assert provider_calls == ["fake-selector"]
    assert state["workflow_outputs"]["return__variant"] == "BLOCKED"
    assert state["workflow_outputs"]["return__reason"] == "selector_blocked"
    assert state["workflow_outputs"]["return__drain-summary__drain_status"] == "BLOCKED"
    assert (workspace / "artifacts" / "work" / "drain_summary.json").is_file()
    assert not (workspace / "artifacts" / "work" / "item_summary.json").exists()
    run_state = _native_drain_run_state(workspace, "lisp-frontend-design-delta-drain--drain")
    assert run_state["drain_status"] == "BLOCKED"
    assert run_state["drain_status_reason"] == "selector_blocked"
    assert run_state["drain_status_summary"] == "artifacts/work/drain_summary.json"


def test_design_delta_migration_nested_same_file_call_with_local_record_compiles(
    tmp_path: Path,
) -> None:
    result = compile_stage3_module(
        NESTED_SAME_FILE_CALL_FIXTURE,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={
            "prompts.implementation.execute": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert {
        workflow.typed_workflow.definition.name
        for workflow in result.lowered_workflows
    } == {"summarize-completed", "echo-helper", "entry"}


def test_design_delta_migration_nested_imported_branch_effects_compile(
    tmp_path: Path,
) -> None:
    result = _compile_nested_entrypoint_fixture(
        NESTED_IMPORTED_BRANCH_EFFECTS_FIXTURE,
        tmp_path=tmp_path,
        extra_source_roots=(WORKFLOW_LISP_FIXTURES / "modules" / "valid" / "workflow_refs",),
    )

    assert "nested/imported-branch" in result.compiled_results_by_name
    assert "workflow_refs/imported_helper" in result.compiled_results_by_name
    assert result.entry_result.validated_bundles
