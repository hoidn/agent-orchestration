from __future__ import annotations

import hashlib
import importlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.calls import CallExecutor
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_public_input_contracts
from orchestrator.workflow_lisp.command_boundaries import (
    CertifiedAdapterInputField,
    PROMOTED_CALL_REQUIRED_METADATA_FIELDS,
)
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import CertifiedAdapterBinding, ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "cli"
WORKFLOW_LISP_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
NESTED_IMPLEMENTATION_PHASE_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_nested_implementation_phase.orc"
)
PARENT_CALL_IMPLEMENTATION_PHASE_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_parent_calls_implementation_phase.orc"
)
NESTED_SAME_FILE_CALL_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_nested_same_file_call_local_record.orc"
)
NESTED_IMPORTED_BRANCH_EFFECTS_FIXTURE = (
    WORKFLOW_LISP_FIXTURES / "valid" / "design_delta_nested_imported_branch_effects.orc"
)


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


def _design_delta_command_boundaries() -> dict[str, ExternalToolBinding]:
    return {
        "run_neurips_backlog_checks": ExternalToolBinding(
            name="run_neurips_backlog_checks",
            stable_command=(
                "python",
                "workflows/library/scripts/run_neurips_backlog_checks.py",
            ),
        ),
        "validate_review_findings_v1": ExternalToolBinding(
            name="validate_review_findings_v1",
            stable_command=(
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
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
) -> CertifiedAdapterBinding:
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
        declared_promoted_fields=frozenset(PROMOTED_CALL_REQUIRED_METADATA_FIELDS),
    )


def _design_delta_work_item_provider_externs() -> dict[str, str]:
    return {
        "providers.plan.draft": "fake-plan-draft",
        "providers.plan.review": "fake-plan-review",
        "providers.plan.fix": "fake-plan-fix",
        "providers.implementation.execute": "fake-implementation-execute",
        "providers.implementation.review": "fake-implementation-review",
        "providers.implementation.fix": "fake-implementation-fix",
        "providers.work-item.recovery-classifier": "fake-work-item-recovery",
    }


def _design_delta_work_item_prompt_externs() -> dict[str, str]:
    return {
        "prompts.plan.draft": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/draft_plan.md",
        "prompts.plan.review": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/review_plan.md",
        "prompts.plan.fix": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/fix_plan.md",
        "prompts.implementation.execute": (
            "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/implement_plan.md"
        ),
        "prompts.implementation.review": (
            "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/review_implementation.md"
        ),
        "prompts.implementation.fix": (
            "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/fix_implementation.md"
        ),
        "prompts.work-item.classify-blocked-recovery": (
            "workflows/library/prompts/lisp_frontend_design_delta_work_item/"
            "classify_blocked_implementation_recovery.md"
        ),
    }


def _design_delta_work_item_command_boundaries() -> dict[str, object]:
    return {
        "run_neurips_backlog_checks": ExternalToolBinding(
            name="run_neurips_backlog_checks",
            stable_command=("python", "workflows/library/scripts/run_neurips_backlog_checks.py"),
        ),
        "validate_review_findings_v1": ExternalToolBinding(
            name="validate_review_findings_v1",
            stable_command=(
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
            ),
        ),
        "materialize_lisp_frontend_work_item_inputs": _promoted_adapter_binding(
            name="materialize_lisp_frontend_work_item_inputs",
            stable_command=("python", "workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py"),
            output_type_name="ResolvedWorkItemInputs",
            behavior_class="structured_result",
            owner_module="lisp_frontend_design_delta/work_item",
            replacement_path="SelectionCtx + ItemCtx private bootstrap + typed projection",
            input_signature=(
                CertifiedAdapterInputField(
                    name="selection_bundle_path",
                    type_name="SelectionBundlePath",
                    required=True,
                    transport_key="selection_path",
                ),
            ),
            fixture_ids=("design_delta_work_item_inputs_ok",),
            negative_fixture_ids=("design_delta_work_item_inputs_bad",),
        ),
        "classify_lisp_frontend_work_item_terminal": _promoted_adapter_binding(
            name="classify_lisp_frontend_work_item_terminal",
            stable_command=(
                "python",
                "workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py",
            ),
            output_type_name="WorkItemTerminalClassification",
            behavior_class="outcome_finalization",
            owner_module="lisp_frontend_design_delta/work_item",
            replacement_path="typed implementation terminal union",
            input_signature=(
                CertifiedAdapterInputField(
                    name="plan_review_decision",
                    type_name="String",
                    required=True,
                    transport_key="plan_review_decision",
                ),
                CertifiedAdapterInputField(
                    name="implementation_state",
                    type_name="String",
                    required=True,
                    transport_key="implementation_state",
                ),
                CertifiedAdapterInputField(
                    name="implementation_review_decision",
                    type_name="String",
                    required=True,
                    transport_key="implementation_review_decision",
                ),
                CertifiedAdapterInputField(
                    name="work_item_source",
                    type_name="String",
                    required=True,
                    transport_key="work_item_source",
                ),
            ),
            fixture_ids=("design_delta_work_item_terminal_ok",),
            negative_fixture_ids=("design_delta_work_item_terminal_bad",),
        ),
        "select_lisp_frontend_blocked_recovery_route": _promoted_adapter_binding(
            name="select_lisp_frontend_blocked_recovery_route",
            stable_command=(
                "python",
                "workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py",
            ),
            output_type_name="BlockedRecoveryDecision",
            behavior_class="outcome_finalization",
            owner_module="lisp_frontend_design_delta/work_item",
            replacement_path="typed BlockedRecoveryDecision normalization",
            input_signature=(
                CertifiedAdapterInputField(
                    name="terminal_route",
                    type_name="String",
                    required=True,
                    transport_key="terminal_route",
                ),
                CertifiedAdapterInputField(
                    name="work_item_source",
                    type_name="String",
                    required=True,
                    transport_key="work_item_source",
                ),
                CertifiedAdapterInputField(
                    name="blocked_recovery_route",
                    type_name="String",
                    required=True,
                    transport_key="blocked_recovery_route",
                ),
                CertifiedAdapterInputField(
                    name="reason",
                    type_name="String",
                    required=True,
                    transport_key="reason",
                ),
            ),
            fixture_ids=("design_delta_blocked_recovery_route_ok",),
            negative_fixture_ids=("design_delta_blocked_recovery_route_bad",),
        ),
        "record_terminal_work_item": ExternalToolBinding(
            name="record_terminal_work_item",
            stable_command=("python", "workflows/library/scripts/update_lisp_frontend_run_state.py"),
        ),
        "record_blocked_recovery_outcome": ExternalToolBinding(
            name="record_blocked_recovery_outcome",
            stable_command=(
                "python",
                "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
            ),
        ),
    }


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


def _compile_design_delta_work_item_entrypoint(tmp_path: Path):
    result = compile_stage3_entrypoint(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
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


def _assert_design_delta_work_item_advances_past_private_workflow_ifexpr_export_blocker(
    tmp_path: Path,
):
    try:
        result, lowered_by_name = _compile_design_delta_work_item_entrypoint(tmp_path)
    except LispFrontendCompileError as exc:
        diagnostic_codes = [diagnostic.code for diagnostic in exc.diagnostics]

        assert diagnostic_codes
        assert diagnostic_codes[0] in {
            "workflow_boundary_type_invalid",
            "low_level_state_path_in_high_level_module",
        }
        assert "proc_private_workflow_boundary_invalid" not in diagnostic_codes
        return None, None

    lowered_names = set(lowered_by_name)
    assert any("finalize-approved-review-state" in name for name in lowered_names)
    assert any("finalize-approved-nonblocked" in name for name in lowered_names)
    return result, lowered_by_name


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
                "     (implementation_review_report_target_path ArtifactReviewTargetPath))",
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
                "                 implementation_review_report_target_path)))",
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
            ),
            "validate_review_findings_v1": ExternalToolBinding(
                name="validate_review_findings_v1",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
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


def _design_delta_runtime_bound_inputs(*, attempt_variant: str) -> dict[str, str]:
    return {
        "phase-ctx__run__run-id": "design-delta-smoke",
        "phase-ctx__run__state-root": "state/run",
        "phase-ctx__run__artifact-root": "artifacts/run",
        "phase-ctx__phase-name": "implementation",
        "phase-ctx__state-root": "state/implementation",
        "phase-ctx__artifact-root": "artifacts/implementation",
        "target_design": "docs/design/target.md",
        "baseline_design": "docs/design/baseline.md",
        "plan_path": "docs/plans/plan.md",
        "check_commands_path": "state/check_commands.json",
        "execution_report_target_path": "artifacts/work/execution_report.md",
        "progress_report_target_path": "artifacts/work/progress_report.md",
        "checks_report_target_path": "artifacts/checks/checks_report.md",
        "implementation_review_report_target_path": (
            "artifacts/review/implementation_review_report.md"
        ),
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
) -> dict[str, str]:
    rewritten = dict(original)
    for input_name, value in list(rewritten.items()):
        if not isinstance(input_name, str) or not input_name.startswith("__write_root__"):
            continue
        if not isinstance(value, str):
            continue
        rewritten[input_name] = (
            f".orchestrate/test-smoke/{hashlib.sha1(value.encode('utf-8')).hexdigest()[:16]}.json"
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

    state_manager = StateManager(workspace=tmp_path, run_id=f"design-delta-{attempt_variant.lower()}")
    state_manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_design_delta_runtime_bound_inputs(attempt_variant=attempt_variant),
    )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
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

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
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
                "  (import lisp_frontend_design_delta/types :only (RunStatePath SelectionResult))",
                "  (export select-next-work)",
                "  (defworkflow select-next-work",
                "    ((run-state RunStatePath))",
                "    -> SelectionResult",
                "    (provider-result providers.selector",
                "      :prompt prompts.selector",
                "      :inputs (run-state)",
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
                "  (import lisp_frontend_design_delta/types :only (DrainResult RunStatePath))",
                "  (export invalid-drain)",
                "  (defworkflow invalid-drain",
                "    ((run-state RunStatePath))",
                "    -> DrainResult",
                "    (variant DrainResult FINISHED",
                "      :run-state run-state)))",
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
                "    (BaselineDesignDoc SelectionBundlePath SteeringDoc TargetDesignDoc WorkReport))",
                "  (export consume-selection)",
                "  (defrecord SelectionView",
                "    (selection_status String)",
                "    (selection_bundle_path SelectionBundlePath))",
                "  (defworkflow consume-selection",
                "    ((steering SteeringDoc)",
                "     (target_design TargetDesignDoc)",
                "     (baseline_design BaselineDesignDoc)",
                "     (manifest WorkReport)",
                "     (progress_ledger WorkReport)",
                "     (run_state WorkReport))",
                "    -> SelectionView",
                "    (let* ((selection",
                "             (call select-next-work",
                "               :steering steering",
                "               :target_design target_design",
                "               :baseline_design baseline_design",
                "               :manifest manifest",
                "               :progress_ledger progress_ledger",
                "               :run_state run_state)))",
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


def test_design_delta_work_item_candidate_compiles_as_parent_callable_workflow(
    tmp_path: Path,
) -> None:
    result, lowered_by_name = _assert_design_delta_work_item_advances_past_private_workflow_ifexpr_export_blocker(
        tmp_path
    )
    if result is None or lowered_by_name is None:
        return

    workflow_name = "lisp_frontend_design_delta/work_item::run-work-item"
    assert set(result.entry_result.validated_bundles) == {workflow_name}

    bundle = result.entry_result.validated_bundles[workflow_name]
    public_inputs = workflow_public_input_contracts(bundle)
    lowered = lowered_by_name[workflow_name]
    lowered_names = set(lowered_by_name)
    lowered_steps = list(_walk_lowered_steps(lowered["steps"]))
    assert set(public_inputs) == {
        "selection_bundle_path",
        "manifest_path",
        "architecture_bundle_path",
        "steering_path",
        "target_design_path",
        "baseline_design_path",
        "progress_ledger_path",
        "run_state_path",
        "implementation_execute_provider",
        "implementation_review_provider",
    }
    assert not any(name.endswith("classify-work-item-terminal") for name in lowered_names)
    assert not any(name.endswith("classify-blocked-implementation-recovery") for name in lowered_names)
    assert sum(1 for step in lowered_steps if step.get("call") == "run-plan-phase") == 1
    assert any(step.get("call") == "implementation-phase" for step in lowered_steps)
    assert any(
        step.get("provider") == "fake-work-item-recovery"
        for step in lowered_steps
    )
    assert any(
        "materialize_lisp_frontend_work_item_inputs.py" in " ".join(step.get("command", []))
        for step in lowered_steps
    )
    assert any(
        "classify_lisp_frontend_work_item_terminal.py" in " ".join(step.get("command", []))
        for step in lowered_steps
    )
    assert any(
        "select_lisp_frontend_blocked_recovery_route.py" in " ".join(step.get("command", []))
        for step in lowered_steps
    )
    assert any(
        step.get("match", {}).get("ref")
        for step in lowered_steps
        if isinstance(step.get("match"), dict)
    )


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
        "return__execution-report": "artifacts/work/execution_report.md",
        "return__progress-report": "artifacts/work/progress_report.md",
        "return__checks-report": "artifacts/checks/checks_report.md",
        "return__implementation-review-report": "artifacts/review/implementation_review_report.md",
    }
    assert (completed_workspace / "artifacts" / "checks" / "checks_report.md").is_file()
    assert (completed_workspace / "artifacts" / "review" / "implementation_review_report.md").is_file()
    assert not (completed_workspace / "artifacts" / "work" / "progress_report.md").exists()

    assert revised_state["status"] == "completed"
    assert revised_provider_calls == ["fake-execute", "fake-review", "fake-fix", "fake-review"]
    assert revised_state["workflow_outputs"] == {
        "return__implementation-state": "COMPLETED",
        "return__implementation-review-decision": "APPROVE",
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
    assert not (revised_workspace / "artifacts" / "work" / "progress_report.md").exists()

    assert blocked_state["status"] == "completed"
    assert blocked_provider_calls == ["fake-execute"]
    assert blocked_state["workflow_outputs"] == {
        "return__implementation-state": "BLOCKED",
        "return__implementation-review-decision": "NOT_APPLICABLE",
        "return__execution-report": "artifacts/work/execution_report.md",
        "return__progress-report": "artifacts/work/progress_report.md",
        "return__checks-report": "artifacts/checks/checks_report.md",
        "return__implementation-review-report": "artifacts/review/implementation_review_report.md",
    }
    assert (blocked_workspace / "artifacts" / "work" / "progress_report.md").is_file()
    assert not (blocked_workspace / "artifacts" / "work" / "execution_report.md").exists()
    assert not (blocked_workspace / "artifacts" / "checks" / "checks_report.md").exists()
    assert not (
        blocked_workspace / "artifacts" / "review" / "implementation_review_report.md"
    ).exists()


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
        "return__execution-report": "artifacts/work/execution_report.md",
        "return__progress-report": "artifacts/work/progress_report.md",
        "return__checks-report": "artifacts/checks/checks_report.md",
        "return__implementation-review-report": "artifacts/review/implementation_review_report.md",
    }
    assert (completed_workspace / "artifacts" / "checks" / "checks_report.md").is_file()
    assert (completed_workspace / "artifacts" / "review" / "implementation_review_report.md").is_file()
    assert not (completed_workspace / "artifacts" / "work" / "progress_report.md").exists()

    assert revised_state["status"] == "completed"
    assert revised_provider_calls == ["fake-execute", "fake-review", "fake-fix", "fake-review"]
    assert revised_state["workflow_outputs"] == {
        "return__implementation-state": "COMPLETED",
        "return__implementation-review-decision": "APPROVE",
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
    assert not (revised_workspace / "artifacts" / "work" / "progress_report.md").exists()

    assert blocked_state["status"] == "completed"
    assert blocked_provider_calls == ["fake-execute"]
    assert blocked_state["workflow_outputs"] == {
        "return__implementation-state": "BLOCKED",
        "return__implementation-review-decision": "NOT_APPLICABLE",
        "return__execution-report": "artifacts/work/execution_report.md",
        "return__progress-report": "artifacts/work/progress_report.md",
        "return__checks-report": "artifacts/checks/checks_report.md",
        "return__implementation-review-report": "artifacts/review/implementation_review_report.md",
    }
    assert (blocked_workspace / "artifacts" / "work" / "progress_report.md").is_file()
    assert not (blocked_workspace / "artifacts" / "work" / "execution_report.md").exists()
    assert not (blocked_workspace / "artifacts" / "checks" / "checks_report.md").exists()
    assert not (
        blocked_workspace / "artifacts" / "review" / "implementation_review_report.md"
    ).exists()


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
