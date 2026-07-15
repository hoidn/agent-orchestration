from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import os
import tempfile
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import orchestrator.workflow.loaded_bundle as loaded_bundle_helpers
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    workflow_generated_path_allocations,
    workflow_input_contracts,
    workflow_managed_write_root_inputs,
)
from orchestrator.workflow.state_layout import render_generated_path_template
from orchestrator.workflow_lisp.adapters import (
    load_canonical_phase_result,
    validate_reusable_phase_state,
    write_reusable_phase_state_v1,
)
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.lints import LINT_PROFILE_STRICT
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / "workflows"
EXAMPLES = WORKFLOWS / "examples"
MIGRATION_INPUTS = EXAMPLES / "inputs" / "workflow_lisp_migrations"
LISP_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"
LISP_INVALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "invalid"
EXPERIMENT_CTX_FIXTURE = LISP_FIXTURES / "context_generalization_experiment_ctx.orc"
RUNCTX_ONLY_DRAIN_ENTRY_FIXTURE = LISP_FIXTURES / "context_generalization_runctx_only_drain_entry.orc"
STD_CONTEXT_IMPORT_FIXTURE = LISP_FIXTURES / "context_generalization_std_context_import.orc"
ANCHORLESS_STATE_PATH_FIXTURE = LISP_INVALID_FIXTURES / "context_generalization_anchorless_state_path.orc"
ROLELESS_BINDING_FIXTURE = LISP_INVALID_FIXTURES / "context_generalization_roleless_binding.orc"
TRACKED_PLAN_PILOT_EVIDENCE = (
    REPO_ROOT / "docs" / "plans" / "evidence" / "procedure-first-pilot" / "tracked-plan-phase"
)
TRACKED_PLAN_PILOT_WORKSPACE = (
    REPO_ROOT
    / ".orchestrate"
    / "procedure-first-pilot-evidence"
    / "tracked-plan-phase"
    / "workspace"
)
TRACKED_PLAN_PILOT_RUN_ROOT = TRACKED_PLAN_PILOT_WORKSPACE / ".orchestrate" / "runs"
TRACKED_PLAN_PILOT_LEGACY_RUN_ROOT = REPO_ROOT / ".orchestrate" / "runs"
TRACKED_PLAN_PILOT_RUN_IDS = (
    "tracked-plan-phase-clean-new-id",
    "tracked-plan-phase-interrupted-new-id",
)
TRACKED_PLAN_PILOT_PROVIDER_ROLES = (
    "design.draft",
    "design.review",
    "plan.draft",
    "plan.review",
    "implementation.execute",
    "implementation.review",
)
TRACKED_PLAN_PILOT_REGISTERED_WORKFLOWS = (
    "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-implementation-phase",
    "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack",
    "examples/design_plan_impl_review_stack_v2_call::tracked-design-phase",
)
TRACKED_PLAN_PILOT_NEW_CHECKPOINT_IDS = (
    "ckpt:65bda4f814bc721664c59a34",
    "ckpt:85bebe726bc9eed0e4ee7c63",
    "ckpt:da29481dd96843184de8136f",
    "ckpt:ecba9af744ae06ba202198fa",
)
_TRACKED_PLAN_PILOT_PUBLIC = (
    "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack"
)
_TRACKED_PLAN_PILOT_INLINE_BASE = (
    f"{_TRACKED_PLAN_PILOT_PUBLIC}__plan__"
    "examples/design_plan_impl_review_stack_v2_call::tracked-plan-phase_1"
)
TRACKED_PLAN_PILOT_NEW_PRESENTATION_KEYS = (
    f"{_TRACKED_PLAN_PILOT_PUBLIC}__design__call_"
    "examples/design_plan_impl_review_stack_v2_call::tracked-design-phase",
    f"{_TRACKED_PLAN_PILOT_PUBLIC}__implementation__call_"
    "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-implementation-phase",
    f"{_TRACKED_PLAN_PILOT_INLINE_BASE}__draft",
    f"{_TRACKED_PLAN_PILOT_INLINE_BASE}__match_review",
    f"{_TRACKED_PLAN_PILOT_INLINE_BASE}__match_review.APPROVE",
    f"{_TRACKED_PLAN_PILOT_INLINE_BASE}__match_review.APPROVE."
    f"{_TRACKED_PLAN_PILOT_INLINE_BASE}__match_review__approve__projection_anchor",
    f"{_TRACKED_PLAN_PILOT_INLINE_BASE}__match_review.REVISE",
    f"{_TRACKED_PLAN_PILOT_INLINE_BASE}__match_review.REVISE."
    f"{_TRACKED_PLAN_PILOT_INLINE_BASE}__match_review__revise__projection_anchor",
    f"{_TRACKED_PLAN_PILOT_INLINE_BASE}__review",
)
TRACKED_PLAN_PILOT_LIVE_ENV = "ORCHESTRATOR_RUN_LIVE_TRACKED_PLAN_PILOT_EVIDENCE"
TRACKED_PLAN_PILOT_CLEAN_EVIDENCE = TRACKED_PLAN_PILOT_EVIDENCE / "evidence" / "clean_run.json"
TRACKED_PLAN_PILOT_RESUME_EVIDENCE = (
    TRACKED_PLAN_PILOT_EVIDENCE / "evidence" / "interruption_resume.json"
)
TRACKED_PLAN_PILOT_PRE_EDIT_SCAN = TRACKED_PLAN_PILOT_EVIDENCE / "pre_edit_known_store_scans.json"
TRACKED_PLAN_PILOT_EVIDENCE_INDEX = TRACKED_PLAN_PILOT_EVIDENCE / "evidence_index.json"
TRACKED_PLAN_PILOT_PRE_EDIT_SCAN_SHA256 = (
    "sha256:422e465bc1391fd2ea186490f39c59ff677f9cd9b1c502ba70f684d38b54f155"
)

_TRACKED_PLAN_PILOT_SCAN_FACT_KEYS = (
    "query_version",
    "normalized_scan_digest",
    "terminal_run_count",
    "nonterminal_run_count",
    "store_terminal_run_count",
    "store_nonterminal_run_count",
    "call_frame_count",
    "consumer_count",
    "checkpoint_index_count",
    "checkpoint_record_count",
    "retained_manifest_count",
    "identity_metadata_count",
    "scanned_file_count",
)


def _load_json(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_path(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _tracked_plan_pilot_scan_facts(payload: dict[str, object]) -> dict[str, object]:
    missing = [key for key in _TRACKED_PLAN_PILOT_SCAN_FACT_KEYS if key not in payload]
    assert not missing, f"legacy scan is missing required facts: {missing}"
    return {key: payload[key] for key in _TRACKED_PLAN_PILOT_SCAN_FACT_KEYS}


def _validate_tracked_plan_phase_preflight_projection(
    *,
    expected_run_root: str,
    observed_run_root: str,
    dedicated_run_ids: tuple[str, ...],
    scratch_paths: tuple[str, ...],
    expected_legacy_scan: dict[str, object],
    observed_legacy_scan: dict[str, object],
    expected_dedicated_scan: dict[str, object],
    observed_dedicated_scan: dict[str, object],
) -> None:
    assert observed_run_root == expected_run_root, "dedicated run root does not match the fixed root"
    assert not dedicated_run_ids, "dedicated run root must be empty"
    assert not scratch_paths, "top-level /tmp design-plan fixture must be absent"
    assert _tracked_plan_pilot_scan_facts(observed_legacy_scan) == _tracked_plan_pilot_scan_facts(
        expected_legacy_scan
    ), "legacy store facts changed from the bound pre-edit scan"
    assert _tracked_plan_pilot_scan_facts(
        observed_dedicated_scan
    ) == _tracked_plan_pilot_scan_facts(expected_dedicated_scan), (
        "dedicated store facts changed from the bound pre-edit scan"
    )


def _validate_tracked_plan_phase_postflight_projection(
    *,
    dedicated_run_ids: tuple[str, ...],
    scratch_paths: tuple[str, ...],
    expected_legacy_scan: dict[str, object],
    observed_legacy_scan: dict[str, object],
    expected_dedicated_scan: dict[str, object],
    observed_dedicated_scan: dict[str, object],
) -> None:
    assert tuple(sorted(dedicated_run_ids)) == tuple(sorted(TRACKED_PLAN_PILOT_RUN_IDS)), (
        "dedicated root must contain exactly the two approved run IDs"
    )
    assert not scratch_paths, "top-level /tmp design-plan fixture must be absent"
    assert _tracked_plan_pilot_scan_facts(observed_legacy_scan) == _tracked_plan_pilot_scan_facts(
        expected_legacy_scan
    ), "legacy store facts changed from the bound pre-edit scan"
    assert observed_dedicated_scan.get("query_version") == expected_dedicated_scan.get(
        "query_version"
    ), "dedicated store query version changed"
    assert observed_dedicated_scan.get("retired_identities") == expected_dedicated_scan.get(
        "retired_identities"
    ), "dedicated store query identity set changed"
    assert observed_dedicated_scan.get("root") == TRACKED_PLAN_PILOT_RUN_ROOT.as_posix()
    assert observed_dedicated_scan.get("matches") in ((), []), (
        "dedicated store contains a queried old identity"
    )
    for key in (
        "terminal_run_count",
        "nonterminal_run_count",
        "call_frame_count",
        "consumer_count",
    ):
        assert observed_dedicated_scan.get(key) == 0, (
            f"dedicated store match-scoped {key} must be zero"
        )
    assert observed_dedicated_scan.get("store_terminal_run_count") == 2
    assert observed_dedicated_scan.get("store_nonterminal_run_count") == 0


def _tracked_plan_phase_expected_outputs() -> dict[str, str]:
    return {
        "return__design_path": "docs/plans/runtime-design.md",
        "return__design_review_report_path": "artifacts/review/runtime-design-review.md",
        "return__design_review_decision": "APPROVE",
        "return__plan_path": "docs/plans/runtime-plan.md",
        "return__plan_review_report_path": "artifacts/review/runtime-plan-review.md",
        "return__plan_review_decision": "APPROVE",
        "return__execution_report_path": "artifacts/work/runtime-execution-report.md",
        "return__implementation_review_report_path": (
            "artifacts/review/runtime-implementation-review.md"
        ),
        "return__implementation_review_decision": "APPROVE",
    }


def _tracked_plan_phase_projection_fixtures() -> tuple[dict[str, object], dict[str, object]]:
    roles = list(TRACKED_PLAN_PILOT_PROVIDER_ROLES)
    artifacts = {
        name.removeprefix("return__"): {
            "path": value,
            "sha256": "sha256:" + "a" * 64,
        }
        for name, value in _tracked_plan_phase_expected_outputs().items()
        if name.endswith("_path")
    }
    baseline_path = REPO_ROOT / "tests" / "baselines" / "procedure_first" / "tracked_plan_phase.json"
    baseline = _load_json(baseline_path)
    old_runtime = baseline["runtime_contract"]
    identity_comparison = {
        "classification": "provisional_old_new_identity_characterization",
        "frozen_baseline_sha256": _sha256_path(baseline_path),
        "old_checkpoint_ids": sorted(
            row["checkpoint_id"] for row in old_runtime["lexical_checkpoints"]
        ),
        "new_checkpoint_ids": list(TRACKED_PLAN_PILOT_NEW_CHECKPOINT_IDS),
        "old_presentation_keys": sorted(
            {row["presentation_key"] for row in old_runtime["resume_checkpoints"]}
        ),
        "new_presentation_keys": list(TRACKED_PLAN_PILOT_NEW_PRESENTATION_KEYS),
        "approval_asserted": False,
    }
    common = {
        "evidence_status": "provisional_characterization",
        "run_root": TRACKED_PLAN_PILOT_RUN_ROOT.as_posix(),
        "workflow_name": (
            "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack"
        ),
        "workflow_outputs": _tracked_plan_phase_expected_outputs(),
        "source": {
            "path": "workflows/examples/design_plan_impl_review_stack_v2_call.orc",
            "sha256": _sha256_path(
                EXAMPLES / "design_plan_impl_review_stack_v2_call.orc"
            ),
        },
        "artifacts": artifacts,
        "checkpoint_ids": list(TRACKED_PLAN_PILOT_NEW_CHECKPOINT_IDS),
        "presentation_keys": list(TRACKED_PLAN_PILOT_NEW_PRESENTATION_KEYS),
        "registered_workflows": list(TRACKED_PLAN_PILOT_REGISTERED_WORKFLOWS),
        "identity_comparison": identity_comparison,
    }
    clean = {
        "schema": "procedure_first_pilot_tracked_plan_clean_run.v1",
        **common,
        "run_id": TRACKED_PLAN_PILOT_RUN_IDS[0],
        "run": {
            "id": TRACKED_PLAN_PILOT_RUN_IDS[0],
            "relative_path": TRACKED_PLAN_PILOT_RUN_IDS[0],
            "tree_sha256": "sha256:" + "b" * 64,
            "entry_count": 12,
        },
        "status": "completed",
        "provider_roles": roles,
    }
    interruption = {
        "schema": "procedure_first_pilot_tracked_plan_interruption_resume.v1",
        **common,
        "run_id": TRACKED_PLAN_PILOT_RUN_IDS[1],
        "run": {
            "id": TRACKED_PLAN_PILOT_RUN_IDS[1],
            "relative_path": TRACKED_PLAN_PILOT_RUN_IDS[1],
            "tree_sha256": "sha256:" + "c" * 64,
            "entry_count": 13,
        },
        "interruption": {
            "status": "process_interrupted",
            "persisted_status": "running",
            "interruption_point": "post_plan_draft_checkpoint_commit",
            "completed_provider_roles": roles[:3],
            "successful_provider_role_count": 3,
            "next_provider_role_not_attempted": "plan.review",
        },
        "resume": {
            "status": "completed",
            "reused_provider_roles": roles[:3],
            "executed_provider_roles": roles[3:],
            "provider_role_attempts": {
                role: 1 for role in roles
            },
        },
        "comparison": {
            "public_output_equal_to_clean": True,
            "artifacts_equal_to_clean": True,
        },
    }
    return clean, interruption


def _validate_tracked_plan_phase_retained_projections(
    clean: dict[str, object],
    interruption: dict[str, object],
) -> None:
    assert clean.get("schema") == "procedure_first_pilot_tracked_plan_clean_run.v1"
    assert interruption.get("schema") == (
        "procedure_first_pilot_tracked_plan_interruption_resume.v1"
    )
    assert clean.get("evidence_status") == "provisional_characterization"
    assert interruption.get("evidence_status") == "provisional_characterization"
    assert clean.get("run_id") == TRACKED_PLAN_PILOT_RUN_IDS[0], "clean run ID changed"
    assert interruption.get("run_id") == TRACKED_PLAN_PILOT_RUN_IDS[1], (
        "interrupted run ID changed"
    )
    assert clean.get("run_root") == TRACKED_PLAN_PILOT_RUN_ROOT.as_posix()
    assert interruption.get("run_root") == TRACKED_PLAN_PILOT_RUN_ROOT.as_posix()
    expected_source = {
        "path": "workflows/examples/design_plan_impl_review_stack_v2_call.orc",
        "sha256": _sha256_path(EXAMPLES / "design_plan_impl_review_stack_v2_call.orc"),
    }
    assert clean.get("source") == expected_source, "clean source binding is invalid"
    assert interruption.get("source") == expected_source, "interrupted source binding is invalid"
    for payload, run_id in zip(
        (clean, interruption), TRACKED_PLAN_PILOT_RUN_IDS, strict=True
    ):
        run = payload.get("run")
        assert isinstance(run, dict), "run tree binding is missing"
        assert set(run) == {"id", "relative_path", "tree_sha256", "entry_count"}, (
            "run tree binding structure is invalid"
        )
        assert run["id"] == run_id and run["relative_path"] == run_id, (
            "run tree identity/path is invalid"
        )
        assert _is_sha256(run["tree_sha256"]), "run tree SHA256 is invalid"
        assert isinstance(run["entry_count"], int) and run["entry_count"] > 0, (
            "run tree entry count is invalid"
        )
    assert clean.get("status") == "completed"
    assert clean.get("provider_roles") == list(TRACKED_PLAN_PILOT_PROVIDER_ROLES), (
        "clean provider roles are not the exact ordered six-role contract"
    )
    interruption_fact = interruption.get("interruption")
    resume_fact = interruption.get("resume")
    comparison = interruption.get("comparison")
    assert isinstance(interruption_fact, dict)
    assert isinstance(resume_fact, dict)
    assert isinstance(comparison, dict)
    expected_reused = ["design.draft", "design.review", "plan.draft"]
    assert interruption_fact == {
        "status": "process_interrupted",
        "persisted_status": "running",
        "interruption_point": "post_plan_draft_checkpoint_commit",
        "completed_provider_roles": expected_reused,
        "successful_provider_role_count": 3,
        "next_provider_role_not_attempted": "plan.review",
    }
    assert resume_fact.get("status") == "completed"
    assert resume_fact.get("reused_provider_roles") == expected_reused
    assert resume_fact.get("executed_provider_roles") == [
        "plan.review",
        "implementation.execute",
        "implementation.review",
    ]
    attempts = resume_fact.get("provider_role_attempts")
    assert isinstance(attempts, dict)
    assert attempts == {
        "design.draft": 1,
        "design.review": 1,
        "plan.draft": 1,
        "plan.review": 1,
        "implementation.execute": 1,
        "implementation.review": 1,
    }
    assert clean.get("workflow_outputs") == _tracked_plan_phase_expected_outputs()
    assert interruption.get("workflow_outputs") == clean.get("workflow_outputs")
    expected_artifact_paths = {
        name.removeprefix("return__"): path
        for name, path in _tracked_plan_phase_expected_outputs().items()
        if name.endswith("_path")
    }
    frozen_baseline = _load_json(
        REPO_ROOT / "tests" / "baselines" / "procedure_first" / "tracked_plan_phase.json"
    )
    frozen_runtime = frozen_baseline["runtime_contract"]
    expected_old_checkpoint_ids = sorted(
        row["checkpoint_id"] for row in frozen_runtime["lexical_checkpoints"]
    )
    expected_old_presentation_keys = sorted(
        {row["presentation_key"] for row in frozen_runtime["resume_checkpoints"]}
    )
    for payload in (clean, interruption):
        artifacts = payload.get("artifacts")
        assert isinstance(artifacts, dict), "artifact bindings are missing"
        assert set(artifacts) == set(expected_artifact_paths), "artifact role set is invalid"
        for role, expected_path in expected_artifact_paths.items():
            binding = artifacts[role]
            assert isinstance(binding, dict) and set(binding) == {"path", "sha256"}, (
                "artifact binding structure is invalid"
            )
            assert binding["path"] == expected_path, "artifact path binding is invalid"
            assert _is_sha256(binding["sha256"]), "artifact SHA256 binding is invalid"
    assert interruption.get("artifacts") == clean.get("artifacts"), (
        "artifact bindings differ between clean and resumed runs"
    )
    assert comparison == {
        "public_output_equal_to_clean": True,
        "artifacts_equal_to_clean": True,
    }
    for payload in (clean, interruption):
        assert payload.get("workflow_name") == (
            "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack"
        )
        checkpoint_ids = payload.get("checkpoint_ids")
        presentation_keys = payload.get("presentation_keys")
        registered = payload.get("registered_workflows")
        identity_comparison = payload.get("identity_comparison")
        assert isinstance(checkpoint_ids, list) and checkpoint_ids
        assert all(isinstance(value, str) and value for value in checkpoint_ids)
        assert checkpoint_ids == sorted(set(checkpoint_ids))
        assert isinstance(presentation_keys, list) and presentation_keys
        assert all(isinstance(value, str) and value for value in presentation_keys)
        assert presentation_keys == sorted(set(presentation_keys))
        assert isinstance(registered, list)
        assert registered == list(TRACKED_PLAN_PILOT_REGISTERED_WORKFLOWS), (
            "registered workflows are not the exact ordered public runtime set"
        )
        assert isinstance(identity_comparison, dict), "identity comparison is missing"
        assert set(identity_comparison) == {
            "classification",
            "frozen_baseline_sha256",
            "old_checkpoint_ids",
            "new_checkpoint_ids",
            "old_presentation_keys",
            "new_presentation_keys",
            "approval_asserted",
        }, "identity comparison structure is invalid"
        assert identity_comparison["classification"] == (
            "provisional_old_new_identity_characterization"
        ), "identity comparison classification is invalid"
        assert identity_comparison["frozen_baseline_sha256"] == _sha256_path(
            REPO_ROOT / "tests" / "baselines" / "procedure_first" / "tracked_plan_phase.json"
        ), "identity comparison baseline binding is invalid"
        assert identity_comparison["approval_asserted"] is False, (
            "identity comparison must not assert approval"
        )
        for key in (
            "old_checkpoint_ids",
            "new_checkpoint_ids",
            "old_presentation_keys",
            "new_presentation_keys",
        ):
            values = identity_comparison[key]
            assert isinstance(values, list) and values, "identity comparison rows are invalid"
            assert values == sorted(set(values)), "identity comparison rows are not canonical"
        assert identity_comparison["old_checkpoint_ids"] == expected_old_checkpoint_ids, (
            "old identity checkpoint rows differ from the frozen baseline"
        )
        assert identity_comparison["old_presentation_keys"] == expected_old_presentation_keys, (
            "old identity presentation rows differ from the frozen baseline"
        )
        assert identity_comparison["new_checkpoint_ids"] == list(
            TRACKED_PLAN_PILOT_NEW_CHECKPOINT_IDS
        ), "new checkpoint rows differ from the accepted no-run characterization"
        assert identity_comparison["new_presentation_keys"] == list(
            TRACKED_PLAN_PILOT_NEW_PRESENTATION_KEYS
        ), "new presentation rows differ from the accepted no-run characterization"
        assert identity_comparison["new_checkpoint_ids"] == checkpoint_ids
        assert identity_comparison["new_presentation_keys"] == presentation_keys
    assert interruption.get("identity_comparison") == clean.get("identity_comparison"), (
        "identity comparisons differ between run projections"
    )


def _workflow_short_name(name: str) -> str:
    return name.rsplit("::", 1)[-1]


def _workflow_public_input_contracts(bundle):
    helper = getattr(
        loaded_bundle_helpers,
        "workflow_public_input_contracts",
        loaded_bundle_helpers.workflow_input_contracts,
    )
    return helper(bundle)


def _workflow_runtime_context_inputs(bundle):
    helper = getattr(
        loaded_bundle_helpers,
        "workflow_runtime_context_inputs",
        lambda _: (),
    )
    return helper(bundle)


def _iter_nested_steps(steps):
    for step in steps:
        yield step
        match_block = step.get("match")
        if isinstance(match_block, dict):
            for case in match_block.get("cases", {}).values():
                if isinstance(case, dict):
                    yield from _iter_nested_steps(case.get("steps", []))
        repeat_block = step.get("repeat_until")
        if isinstance(repeat_block, dict):
            yield from _iter_nested_steps(repeat_block.get("steps", []))
            exhausted_block = repeat_block.get("on_exhausted")
            if isinstance(exhausted_block, dict):
                yield from _iter_nested_steps(exhausted_block.get("steps", []))
        then_block = step.get("then")
        if isinstance(then_block, dict):
            yield from _iter_nested_steps(then_block.get("steps", []))
        else_block = step.get("else")
        if isinstance(else_block, dict):
            yield from _iter_nested_steps(else_block.get("steps", []))


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


def test_cycle_guard_demo_orc_compiles_with_bounded_loop(tmp_path: Path) -> None:
    result = compile_stage3_module(
        EXAMPLES / "cycle_guard_demo.orc",
        command_boundaries={
            "emit_cycle_guard_summary": ExternalToolBinding(
                name="emit_cycle_guard_summary",
                stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for workflow in result.lowered_workflows
    }

    assert set(lowered) == {"cycle-guard-demo"}
    mapping = lowered["cycle-guard-demo"]
    assert mapping["version"] == "2.14"
    assert len(mapping["steps"]) == 1
    assert mapping["steps"][0]["command"][:2] == ["python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"]
    hidden_inputs = [name for name in mapping["inputs"] if name.startswith("__write_root__")]
    assert len(hidden_inputs) == 1
    assert mapping["outputs"]["return__terminal_status"]["type"] == "string"
    assert mapping["outputs"]["return__guard_cycles"]["type"] == "integer"


def test_cycle_guard_demo_orc_runtime_materializes_output_bundle(tmp_path: Path) -> None:
    result = compile_stage3_module(
        EXAMPLES / "cycle_guard_demo.orc",
        command_boundaries={
            "emit_cycle_guard_summary": ExternalToolBinding(
                name="emit_cycle_guard_summary",
                stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    bundle = result.validated_bundles["cycle-guard-demo"]
    hidden_inputs = workflow_managed_write_root_inputs(bundle)
    assert len(hidden_inputs) == 1
    assert hidden_inputs[0].endswith("__result_bundle")
    assert hidden_inputs[0] not in _workflow_public_input_contracts(bundle)

    adapter_source = REPO_ROOT / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest = tmp_path / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest.parent.mkdir(parents=True, exist_ok=True)
    adapter_dest.write_text(adapter_source.read_text(encoding="utf-8"), encoding="utf-8")

    output_bundle_relpath = (
        Path(".orchestrate")
        / "workflow_lisp"
        / "entry"
        / "cycle-guard-orc-runtime"
        / "cycle-guard-demo"
        / f"{hidden_inputs[0]}.json"
    )
    state_manager = StateManager(workspace=tmp_path, run_id="cycle-guard-orc-runtime")
    state_manager.initialize(
        (EXAMPLES / "cycle_guard_demo.orc").as_posix(),
        bound_inputs={
            "terminal_status": "FAILED_CLOSED_BY_GUARD",
            "guard_cycles": 2,
        },
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "completed"
    bundle_path = tmp_path / output_bundle_relpath
    assert bundle_path.is_file()
    assert json.loads(bundle_path.read_text(encoding="utf-8")) == {
        "terminal_status": "FAILED_CLOSED_BY_GUARD",
        "guard_cycles": 2,
    }


def test_cycle_guard_demo_orc_runtime_rejects_stdout_only_structured_command(tmp_path: Path) -> None:
    result = compile_stage3_module(
        EXAMPLES / "cycle_guard_demo.orc",
        command_boundaries={
            "emit_cycle_guard_summary": ExternalToolBinding(
                name="emit_cycle_guard_summary",
                stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    bundle = result.validated_bundles["cycle-guard-demo"]
    hidden_inputs = workflow_managed_write_root_inputs(bundle)
    assert len(hidden_inputs) == 1

    adapter_source = REPO_ROOT / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest = tmp_path / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest.parent.mkdir(parents=True, exist_ok=True)
    adapter_text = adapter_source.read_text(encoding="utf-8").replace(
        '\n    if bundle_path_raw:\n        bundle_path = Path(bundle_path_raw)\n        if bundle_path.is_absolute() or ".." in bundle_path.parts:\n            raise SystemExit("unsafe ORCHESTRATOR_OUTPUT_BUNDLE_PATH")\n        bundle_path.parent.mkdir(parents=True, exist_ok=True)\n        bundle_path.write_text(json.dumps(payload) + "\\n", encoding="utf-8")',
        "",
        1,
    )
    adapter_dest.write_text(adapter_text, encoding="utf-8")

    state_manager = StateManager(workspace=tmp_path, run_id="cycle-guard-orc-stdout-only")
    state_manager.initialize(
        (EXAMPLES / "cycle_guard_demo.orc").as_posix(),
        bound_inputs={
            "terminal_status": "FAILED_CLOSED_BY_GUARD",
            "guard_cycles": 2,
        },
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()
    step_state = state["steps"]["cycle-guard-demo__emit_cycle_guard_summary"]

    assert state["status"] == "failed"
    assert step_state["error"]["type"] == "contract_violation"
    assert step_state["error"]["context"]["violations"] == [
        {
            "context": {
                "path": (
                    ".orchestrate/workflow_lisp/entry/cycle-guard-orc-stdout-only/"
                    "cycle-guard-demo/"
                    f"{hidden_inputs[0]}.json"
                )
            },
            "message": "Expected output bundle file was not created",
            "type": "missing_bundle_file",
        }
    ]
    assert not (
        tmp_path
        / ".orchestrate"
        / "workflow_lisp"
        / "entry"
        / "cycle-guard-orc-stdout-only"
        / "cycle-guard-demo"
        / f"{hidden_inputs[0]}.json"
    ).exists()


def test_cycle_guard_demo_orc_rejects_user_override_of_runtime_owned_write_root(tmp_path: Path) -> None:
    result = compile_stage3_module(
        EXAMPLES / "cycle_guard_demo.orc",
        command_boundaries={
            "emit_cycle_guard_summary": ExternalToolBinding(
                name="emit_cycle_guard_summary",
                stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    bundle = result.validated_bundles["cycle-guard-demo"]
    hidden_input_name = workflow_managed_write_root_inputs(bundle)[0]

    adapter_source = REPO_ROOT / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest = tmp_path / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest.parent.mkdir(parents=True, exist_ok=True)
    adapter_dest.write_text(adapter_source.read_text(encoding="utf-8"), encoding="utf-8")

    state_manager = StateManager(workspace=tmp_path, run_id="cycle-guard-orc-override")
    state_manager.initialize(
        (EXAMPLES / "cycle_guard_demo.orc").as_posix(),
        bound_inputs={
            "terminal_status": "FAILED_CLOSED_BY_GUARD",
            "guard_cycles": 2,
            hidden_input_name: "state/user-owned-result.json",
        },
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "failed"
    assert state["error"]["type"] == "contract_violation"
    assert state["error"]["context"]["reason"] == "managed_write_root_override"
    assert state["error"]["context"]["input"] == hidden_input_name


def test_design_plan_impl_stack_orc_compiles_with_phase_family_contracts(tmp_path: Path) -> None:
    provider_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.providers.json")
    prompt_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json")

    result = compile_stage3_entrypoint(
        EXAMPLES / "design_plan_impl_review_stack_v2_call.orc",
        source_roots=(WORKFLOWS,),
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result

    lowered = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for workflow in result.lowered_workflows
    }

    lowered_by_short_name = {
        _workflow_short_name(name): mapping for name, mapping in lowered.items()
    }

    assert set(lowered_by_short_name) == {
        "tracked-design-phase",
        "design-plan-impl-implementation-phase",
        "design-plan-impl-review-stack",
    }

    assert lowered_by_short_name["tracked-design-phase"]["steps"][0]["provider"] == "codex"
    assert lowered_by_short_name["design-plan-impl-implementation-phase"]["steps"][0]["provider"] == "codex"

    stack_mapping = lowered_by_short_name["design-plan-impl-review-stack"]
    assert [
        step["provider"]
        for step in stack_mapping["steps"]
        if "tracked-plan-phase" in step["name"] and "provider" in step
    ] == ["codex", "codex"]

    stack_outputs = stack_mapping["outputs"]
    output_names = {name.removeprefix("return__") for name in stack_outputs}
    assert output_names == {
        "design_path",
        "design_review_report_path",
        "design_review_decision",
        "plan_path",
        "plan_review_report_path",
        "plan_review_decision",
        "execution_report_path",
        "implementation_review_report_path",
        "implementation_review_decision",
    }


def test_tracked_plan_phase_preflight_projection_rejects_a_nonempty_dedicated_root() -> None:
    with pytest.raises(AssertionError, match="dedicated run root must be empty"):
        _validate_tracked_plan_phase_preflight_projection(
            expected_run_root="/repo/.orchestrate/pilot/workspace/.orchestrate/runs",
            observed_run_root="/repo/.orchestrate/pilot/workspace/.orchestrate/runs",
            dedicated_run_ids=("unexpected",),
            scratch_paths=(),
            expected_legacy_scan={"normalized_scan_digest": "sha256:" + "1" * 64},
            observed_legacy_scan={"normalized_scan_digest": "sha256:" + "1" * 64},
            expected_dedicated_scan={"normalized_scan_digest": "sha256:" + "1" * 64},
            observed_dedicated_scan={"normalized_scan_digest": "sha256:" + "1" * 64},
        )


def _tracked_plan_phase_scan_fact_fixture(digest_character: str = "1") -> dict[str, object]:
    return {
        "query_version": "procedure-identity-store-query.v1",
        "normalized_scan_digest": "sha256:" + digest_character * 64,
        "terminal_run_count": 0,
        "nonterminal_run_count": 0,
        "store_terminal_run_count": 4074,
        "store_nonterminal_run_count": 90,
        "call_frame_count": 0,
        "consumer_count": 0,
        "checkpoint_index_count": 1,
        "checkpoint_record_count": 2,
        "retained_manifest_count": 3,
        "identity_metadata_count": 4,
        "scanned_file_count": 5,
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"observed_run_root": "/wrong/root"}, "fixed root"),
        ({"scratch_paths": ("/tmp/design-plan-impl-stack-leak",)}, "must be absent"),
        (
            {"observed_legacy_scan": _tracked_plan_phase_scan_fact_fixture("2")},
            "legacy store facts changed",
        ),
    ],
)
def test_tracked_plan_phase_preflight_projection_fails_closed(
    mutation: dict[str, object],
    message: str,
) -> None:
    scan = _tracked_plan_phase_scan_fact_fixture()
    arguments: dict[str, object] = {
        "expected_run_root": "/repo/.orchestrate/pilot/workspace/.orchestrate/runs",
        "observed_run_root": "/repo/.orchestrate/pilot/workspace/.orchestrate/runs",
        "dedicated_run_ids": (),
        "scratch_paths": (),
        "expected_legacy_scan": scan,
        "observed_legacy_scan": dict(scan),
        "expected_dedicated_scan": scan,
        "observed_dedicated_scan": dict(scan),
    }
    arguments.update(mutation)

    with pytest.raises(AssertionError, match=message):
        _validate_tracked_plan_phase_preflight_projection(**arguments)


def test_tracked_plan_phase_retained_projection_rejects_wrong_run_relationship() -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    interruption["run_id"] = "wrong-run"

    with pytest.raises(AssertionError, match="interrupted run ID"):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda clean: clean["source"].__setitem__("sha256", "sha256:" + "0" * 64), "source"),
        (lambda clean: clean["run"].__setitem__("tree_sha256", "not-a-digest"), "run tree"),
        (
            lambda clean: clean["artifacts"]["plan_path"].__setitem__(
                "path", "docs/plans/not-the-bound-plan.md"
            ),
            "artifact",
        ),
        (
            lambda clean: clean["identity_comparison"].__setitem__("approval_asserted", True),
            "identity comparison",
        ),
        (lambda clean: clean.__setitem__("provider_roles", []), "provider roles"),
        (lambda clean: clean.__setitem__("registered_workflows", []), "registered workflows"),
        (
            lambda clean: clean.__setitem__("registered_workflows", ["changed"]),
            "registered workflows",
        ),
        (
            lambda clean: clean["identity_comparison"].__setitem__(
                "old_checkpoint_ids", ["ckpt:changed"]
            ),
            "old identity",
        ),
        (
            lambda clean: clean["identity_comparison"].__setitem__(
                "new_checkpoint_ids", ["ckpt:changed"]
            ),
            "new checkpoint",
        ),
        (
            lambda clean: clean["identity_comparison"].__setitem__(
                "new_presentation_keys", ["changed"]
            ),
            "new presentation",
        ),
    ],
)
def test_tracked_plan_phase_retained_projection_rejects_bound_evidence_tampering(
    mutate,
    message: str,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    mutate(clean)

    with pytest.raises(AssertionError, match=message):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


def test_tracked_plan_phase_pair_publication_removes_singleton_after_second_replace_failure(
    tmp_path: Path,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    clean_target = tmp_path / "clean.json"
    interruption_target = tmp_path / "interruption.json"
    real_replace = os.replace
    replacements = {"count": 0}

    def fail_second_replace(source: Path, target: Path) -> None:
        replacements["count"] += 1
        if replacements["count"] == 2:
            raise OSError("injected second replace failure")
        real_replace(source, target)

    with patch("os.replace", side_effect=fail_second_replace), pytest.raises(
        OSError, match="injected second replace failure"
    ):
        _publish_tracked_plan_phase_evidence_pair_atomically(
            clean,
            interruption,
            targets=(clean_target, interruption_target),
        )

    assert not clean_target.exists()
    assert not interruption_target.exists()


def test_tracked_plan_phase_postflight_projection_rejects_a_third_run() -> None:
    scan = _tracked_plan_phase_scan_fact_fixture()

    with pytest.raises(AssertionError, match="exactly the two approved run IDs"):
        _validate_tracked_plan_phase_postflight_projection(
            dedicated_run_ids=(*TRACKED_PLAN_PILOT_RUN_IDS, "third-run"),
            scratch_paths=(),
            expected_legacy_scan=scan,
            observed_legacy_scan=dict(scan),
            expected_dedicated_scan=scan,
            observed_dedicated_scan={
                **scan,
                "root": TRACKED_PLAN_PILOT_RUN_ROOT.as_posix(),
                "retired_identities": ["old"],
                "matches": [],
                "store_terminal_run_count": 2,
                "store_nonterminal_run_count": 0,
            },
        )


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"gate": "0"}, "authorization gate"),
        ({"run_id": TRACKED_PLAN_PILOT_RUN_IDS[0], "resume": True}, "clean run cannot resume"),
        ({"run_exists": True}, "initial interrupted run directory must be absent"),
        ({"control": {"interrupt_after_role": "implementation.execute"}}, "plan.draft"),
    ],
)
def test_tracked_plan_phase_runtime_lifecycle_rejects_unauthorized_transitions(
    arguments: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "gate": "1",
        "run_id": TRACKED_PLAN_PILOT_RUN_IDS[1],
        "resume": False,
        "run_exists": False,
        "run_is_symlink": False,
        "persisted_status": None,
        "control": {"interrupt_after_role": "plan.draft"},
    }
    values.update(arguments)
    with pytest.raises(AssertionError, match=message):
        _validate_tracked_plan_phase_runtime_lifecycle(**values)


def test_tracked_plan_phase_runtime_lifecycle_accepts_only_bound_resume_state() -> None:
    _validate_tracked_plan_phase_runtime_lifecycle(
        gate="1",
        run_id=TRACKED_PLAN_PILOT_RUN_IDS[1],
        resume=True,
        run_exists=True,
        run_is_symlink=False,
        persisted_status="running",
        control={
            "interrupt_after_role": "plan.draft",
            "interruption_emitted": True,
            "checkpoint_hook_completed": True,
            "interruption_target_step_id": "root.plan_draft",
            "successful_roles": ["design.draft", "design.review", "plan.draft"],
            "attempts": {
                "design.draft": 1,
                "design.review": 1,
                "plan.draft": 1,
            },
        },
        expected_interruption_target_step_id="root.plan_draft",
    )


def test_post_persist_interruption_hook_delegates_before_raising_once_at_exact_target(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.lexical_checkpoints import (
        resolve_checkpoint_index_path,
    )

    target = SimpleNamespace(
        node_id="root.plan_draft",
        checkpoint_id="checkpoint:plan-draft",
        workflow_name="generic::workflow",
    )
    control: dict[str, object] = {"interrupt_after_role": "plan.draft"}
    record_path = tmp_path / "checkpoint-record.json"

    class FakeStateManager:
        workspace = tmp_path
        run_id = "no-run"

        def __init__(self) -> None:
            self.production_completed = False

        def load(self):
            return SimpleNamespace(
                steps={
                    "draft": {
                        "status": "completed",
                        "step_id": target.node_id,
                    }
                }
            )

        def read_runtime_sidecar_json(self, path):
            assert self.production_completed
            if Path(path) == resolve_checkpoint_index_path(
                state_manager=self,
                workflow_name=target.workflow_name,
                checkpoint_id=target.checkpoint_id,
            ):
                return {"records": [{"record_path": record_path.name}]}
            assert Path(path) == record_path
            return {"completed_effect_refs": [{"effect_kind": "provider"}]}

    manager = FakeStateManager()
    calls: list[str] = []

    def production_hook(*_args) -> None:
        calls.append("production")
        manager.production_completed = True

    hook = _tracked_plan_phase_one_shot_post_persist_interruption(
        production_hook,
        target_point=target,
        state_manager=manager,
        control=control,
    )
    hook({}, "other", object(), {"status": "completed", "step_id": "root.other"})
    with pytest.raises(_TrackedPlanPhaseProcessInterruption):
        hook({}, "draft", object(), {"status": "completed", "step_id": target.node_id})
    hook({}, "draft", object(), {"status": "completed", "step_id": target.node_id})

    assert calls == ["production", "production", "production"]
    assert control == {
        "interrupt_after_role": "plan.draft",
        "interruption_emitted": True,
        "checkpoint_hook_completed": True,
        "interruption_target_step_id": target.node_id,
    }


def _validate_tracked_plan_phase_runtime_lifecycle(
    *,
    gate: object,
    run_id: object,
    resume: object,
    run_exists: object,
    run_is_symlink: object,
    persisted_status: object,
    control: object,
    expected_interruption_target_step_id: object = None,
) -> None:
    assert gate == "1", "live runtime authorization gate must equal 1"
    assert isinstance(control, dict)
    if run_id == TRACKED_PLAN_PILOT_RUN_IDS[0]:
        assert resume is False, "clean run cannot resume"
        assert run_exists is False, "initial clean run directory must be absent"
        assert control == {}, "clean run control must be pristine"
        return
    assert run_id == TRACKED_PLAN_PILOT_RUN_IDS[1], "runtime run ID is not authorized"
    if resume is False:
        assert run_exists is False, "initial interrupted run directory must be absent"
        assert control == {"interrupt_after_role": "plan.draft"}, (
            "initial interrupted control must interrupt exactly after plan.draft once"
        )
        return
    assert resume is True
    assert run_exists is True, "interrupted resume run directory must exist"
    assert run_is_symlink is False, "interrupted resume run directory cannot be a symlink"
    assert persisted_status == "running", "interrupted resume requires persisted nonterminal state"
    assert control == {
        "interrupt_after_role": "plan.draft",
        "interruption_emitted": True,
        "checkpoint_hook_completed": True,
        "interruption_target_step_id": expected_interruption_target_step_id,
        "successful_roles": ["design.draft", "design.review", "plan.draft"],
        "attempts": {
            "design.draft": 1,
            "design.review": 1,
            "plan.draft": 1,
        },
    }, "interrupted resume control does not prove the bound first attempt"


class _TrackedPlanPhaseProcessInterruption(BaseException):
    """Test-only abrupt process stop after a committed checkpoint hook."""


def _tracked_plan_phase_one_shot_post_persist_interruption(
    production_hook,
    *,
    target_point: object,
    state_manager: object,
    control: dict[str, object],
):
    from orchestrator.workflow_lisp.lexical_checkpoints import (
        resolve_checkpoint_index_path,
    )

    target_step_id = getattr(target_point, "node_id", None)
    checkpoint_id = getattr(target_point, "checkpoint_id", None)
    workflow_name = getattr(target_point, "workflow_name", None)
    assert isinstance(target_step_id, str) and target_step_id
    assert isinstance(checkpoint_id, str) and checkpoint_id
    assert isinstance(workflow_name, str) and workflow_name

    def interrupt_after_production_hook(state, step_name, step, finalized) -> None:
        production_hook(state, step_name, step, finalized)
        if finalized.get("step_id") != target_step_id:
            return
        if control.get("interruption_emitted") is True:
            return
        assert finalized.get("status") == "completed"
        persisted_steps = getattr(state_manager.load(), "steps", {})
        persisted_matches = [
            value
            for value in persisted_steps.values()
            if isinstance(value, Mapping)
            and value.get("step_id") == target_step_id
            and value.get("status") == "completed"
        ]
        assert len(persisted_matches) == 1, "plan.draft result was not durably persisted"
        index_path = resolve_checkpoint_index_path(
            state_manager=state_manager,
            workflow_name=workflow_name,
            checkpoint_id=checkpoint_id,
        )
        index_payload = state_manager.read_runtime_sidecar_json(index_path)
        assert isinstance(index_payload, Mapping)
        records = index_payload.get("records")
        assert isinstance(records, list) and records
        latest = records[-1]
        assert isinstance(latest, Mapping)
        record_path = latest.get("record_path")
        assert isinstance(record_path, str) and record_path
        record = state_manager.read_runtime_sidecar_json(
            getattr(state_manager, "workspace") / record_path
        )
        assert isinstance(record, Mapping)
        completed_effect_refs = record.get("completed_effect_refs")
        assert isinstance(completed_effect_refs, list) and completed_effect_refs
        control["interruption_emitted"] = True
        control["checkpoint_hook_completed"] = True
        control["interruption_target_step_id"] = target_step_id
        raise _TrackedPlanPhaseProcessInterruption(
            "test-only interruption after plan.draft checkpoint commit"
        )

    return interrupt_after_production_hook


def _tracked_plan_phase_compiler_output_path_roles(
    compile_result: object,
    public_bundle: object,
    *,
    run_id: str,
) -> dict[str, str]:
    role_by_contract_fields = {
        frozenset(("design_path",)): "design.draft",
        frozenset(("design_review_report_path", "design_review_decision")): "design.review",
        frozenset(("plan_path",)): "plan.draft",
        frozenset(("plan_review_report_path", "plan_review_decision")): "plan.review",
        frozenset(("execution_report_path",)): "implementation.execute",
        frozenset(
            ("implementation_review_report_path", "implementation_review_decision")
        ): "implementation.review",
    }
    public_allocations = workflow_generated_path_allocations(public_bundle)
    output_path_roles: dict[str, str] = {}
    observed_roles: set[str] = set()
    for provider_bundle in compile_result.validated_bundles.values():
        for step in provider_bundle.surface.steps:
            if step.kind.value != "provider":
                continue
            contract = step.common.variant_output or step.common.output_bundle
            assert contract is not None
            fields = (
                contract.get("shared_fields", ())
                if step.common.variant_output is not None
                else contract.get("fields", ())
            )
            field_names = frozenset(field["name"] for field in fields)
            role = role_by_contract_fields.get(field_names)
            assert role is not None, f"unrecognized provider structured-output contract: {field_names}"
            assert role not in observed_roles, f"duplicate provider evidence role: {role}"
            observed_roles.add(role)
            path_template = contract["path"]
            match = re.fullmatch(r"\$\{inputs\.([^}]+)\}", path_template)
            assert match is not None, path_template
            generated_input_name = match.group(1)
            matching_allocations = {
                allocation.concrete_path_template: allocation
                for allocation in public_allocations
                if allocation.generated_input_name == generated_input_name
                and not allocation.concrete_path_template.startswith("${inputs.")
            }
            assert len(matching_allocations) == 1, generated_input_name
            rendered_path = render_generated_path_template(
                next(iter(matching_allocations.values())), run_id=run_id
            )
            assert rendered_path not in output_path_roles
            output_path_roles[rendered_path] = role
    assert observed_roles == set(role_by_contract_fields.values())
    assert len(output_path_roles) == 6
    return output_path_roles


def _tracked_plan_phase_checkpoint_point_for_provider_role(
    public_bundle: object,
    output_path_roles: Mapping[str, str],
    *,
    role: str,
    run_id: str,
) -> object:
    public_allocations = workflow_generated_path_allocations(public_bundle)
    candidates: list[object] = []
    for point in public_bundle.runtime_plan.lexical_checkpoint_points:
        if getattr(point, "point_kind", None) != "effect_boundary":
            continue
        details = getattr(point, "details", {})
        policy = details.get("effect_boundary", {}).get("policy", {})
        bundle_path_ref = (
            policy.get("evidence_requirements", {})
            .get("structured_output", {})
            .get("bundle_path_ref")
        )
        if not isinstance(bundle_path_ref, str) or not bundle_path_ref.startswith("inputs."):
            continue
        generated_input_name = bundle_path_ref.removeprefix("inputs.")
        allocations = [
            allocation
            for allocation in public_allocations
            if allocation.generated_input_name == generated_input_name
            and not allocation.concrete_path_template.startswith("${inputs.")
        ]
        assert len(allocations) == 1
        rendered_path = render_generated_path_template(allocations[0], run_id=run_id)
        if output_path_roles.get(rendered_path) == role:
            candidates.append(point)
    assert len(candidates) == 1, f"compiler did not derive one checkpoint for {role}"
    return candidates[0]


def _execute_design_plan_impl_stack_single_pass_runtime(
    workspace: Path,
    *,
    run_id: str,
    provider_control: dict[str, object],
    resume: bool = False,
) -> tuple[dict[str, object], dict[str, str], object]:
    assert workspace.resolve(strict=True) == TRACKED_PLAN_PILOT_WORKSPACE.resolve(strict=True)
    assert run_id in TRACKED_PLAN_PILOT_RUN_IDS, "runtime helper received an unapproved run ID"
    run_path = TRACKED_PLAN_PILOT_RUN_ROOT / run_id
    run_is_symlink = run_path.is_symlink()
    run_exists = run_path.exists() or run_is_symlink
    persisted_status: object = None
    if resume and run_exists and not run_is_symlink:
        persisted_state = _load_json(run_path / "state.json")
        persisted_status = persisted_state.get("status")
    _validate_tracked_plan_phase_runtime_lifecycle(
        gate=os.environ.get(TRACKED_PLAN_PILOT_LIVE_ENV),
        run_id=run_id,
        resume=resume,
        run_exists=run_exists,
        run_is_symlink=run_is_symlink,
        persisted_status=persisted_status,
        control=provider_control,
        expected_interruption_target_step_id=provider_control.get(
            "interruption_target_step_id"
        ),
    )
    workflow_relpath = Path("workflows/examples/design_plan_impl_review_stack_v2_call.orc")
    workflow_path = workspace / workflow_relpath
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_bytes((REPO_ROOT / workflow_relpath).read_bytes())

    provider_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.providers.json")
    prompt_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json")
    for prompt_relpath in prompt_externs.values():
        prompt_path = workspace / prompt_relpath
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_bytes((REPO_ROOT / prompt_relpath).read_bytes())

        nested_prompt_path = workflow_path.parent / prompt_relpath
        nested_prompt_path.parent.mkdir(parents=True, exist_ok=True)
        nested_prompt_path.write_bytes((REPO_ROOT / prompt_relpath).read_bytes())

    brief_relpath = "workflows/examples/inputs/major_project_brief.md"
    brief_path = workspace / brief_relpath
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_bytes((REPO_ROOT / brief_relpath).read_bytes())

    result = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(workspace / "workflows",),
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundaries={},
        validate_shared=True,
        workspace_root=workspace,
    ).entry_result
    bundle = result.validated_bundles[
        "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack"
    ]

    bound_inputs = {
        "brief_path": brief_relpath,
        "design_target_path": "docs/plans/runtime-design.md",
        "design_review_report_target_path": "artifacts/review/runtime-design-review.md",
        "plan_target_path": "docs/plans/runtime-plan.md",
        "plan_review_report_target_path": "artifacts/review/runtime-plan-review.md",
        "execution_report_target_path": "artifacts/work/runtime-execution-report.md",
        "implementation_review_report_target_path": "artifacts/review/runtime-implementation-review.md",
    }
    output_paths = {
        "design_path": bound_inputs["design_target_path"],
        "design_review_report_path": bound_inputs["design_review_report_target_path"],
        "plan_path": bound_inputs["plan_target_path"],
        "plan_review_report_path": bound_inputs["plan_review_report_target_path"],
        "execution_report_path": bound_inputs["execution_report_target_path"],
        "implementation_review_report_path": bound_inputs["implementation_review_report_target_path"],
    }

    state_manager = StateManager(workspace=workspace, run_id=run_id)
    if not resume:
        state_manager.initialize(
            workflow_relpath.as_posix(),
            context=bundle_context_dict(bundle),
            bound_inputs=bound_inputs,
        )

    provider_steps = {
        "design.draft": {
            "artifacts": [(output_paths["design_path"], "# Runtime Design\n")],
            "bundle": {
                "design_path": output_paths["design_path"],
            },
        },
        "design.review": {
            "artifacts": [(output_paths["design_review_report_path"], "APPROVE\n")],
            "bundle": {
                "variant": "APPROVE",
                "design_review_report_path": output_paths["design_review_report_path"],
                "design_review_decision": "APPROVE",
            },
        },
        "plan.draft": {
            "artifacts": [(output_paths["plan_path"], "# Runtime Plan\n")],
            "bundle": {
                "plan_path": output_paths["plan_path"],
            },
        },
        "plan.review": {
            "artifacts": [(output_paths["plan_review_report_path"], "APPROVE\n")],
            "bundle": {
                "variant": "APPROVE",
                "plan_review_report_path": output_paths["plan_review_report_path"],
                "plan_review_decision": "APPROVE",
            },
        },
        "implementation.execute": {
            "artifacts": [(output_paths["execution_report_path"], "# Runtime Execution Report\n")],
            "bundle": {
                "execution_report_path": output_paths["execution_report_path"],
            },
        },
        "implementation.review": {
            "artifacts": [(output_paths["implementation_review_report_path"], "APPROVE\n")],
            "bundle": {
                "variant": "APPROVE",
                "implementation_review_report_path": output_paths["implementation_review_report_path"],
                "implementation_review_decision": "APPROVE",
            },
        },
    }

    output_path_roles = _tracked_plan_phase_compiler_output_path_roles(
        result,
        bundle,
        run_id=run_id,
    )
    interruption_target = _tracked_plan_phase_checkpoint_point_for_provider_role(
        bundle,
        output_path_roles,
        role="plan.draft",
        run_id=run_id,
    )
    if resume:
        assert provider_control.get("interruption_target_step_id") == getattr(
            interruption_target, "node_id"
        ), "interrupted resume target is not the compiler-derived plan.draft boundary"

    def _prepare_invocation(
        _self,
        provider_name=None,
        prompt_content=None,
        env=None,
        **_kwargs,
    ):
        bundle_path = (env or {}).get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
        assert isinstance(bundle_path, str) and bundle_path
        role = output_path_roles.get(bundle_path)
        assert role is not None, f"runtime bundle path is not compiler-derived: {bundle_path}"
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=prompt_content or "",
                provider_name=provider_name,
                evidence_role=role,
                output_bundle_path=bundle_path,
            ),
            None,
        )

    def _write_bundle(bundle_path: Path, payload: dict[str, object]) -> None:
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _success():
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

    def _execute(_self, invocation, **_kwargs):
        role = getattr(invocation, "evidence_role")
        assert role in provider_steps
        attempts = provider_control.setdefault("attempts", {})
        assert isinstance(attempts, dict)
        attempts[role] = attempts.get(role, 0) + 1
        spec = provider_steps[role]
        for relpath, content in spec["artifacts"]:
            target = workspace / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        _write_bundle(workspace / getattr(invocation, "output_bundle_path"), spec["bundle"])
        successful_roles = provider_control.setdefault("successful_roles", [])
        assert isinstance(successful_roles, list)
        successful_roles.append(role)
        return _success()

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        executor = WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0)
        if provider_control.get("interrupt_after_role") == "plan.draft":
            production_hook = executor.outcome_recorder.post_persist_hook
            assert production_hook is not None
            executor.outcome_recorder.post_persist_hook = (
                _tracked_plan_phase_one_shot_post_persist_interruption(
                    production_hook,
                    target_point=interruption_target,
                    state_manager=state_manager,
                    control=provider_control,
                )
            )
        try:
            state = executor.execute(
                run_id=run_id if resume else None,
                resume=resume,
                on_error="stop",
            )
        except _TrackedPlanPhaseProcessInterruption:
            assert resume is False
            assert provider_control.get("interruption_emitted") is True
            state = state_manager.load().to_dict()

    return state, output_paths, SimpleNamespace(
        runtime_plan=bundle.runtime_plan,
        registered_workflows=tuple(sorted(result.validated_bundles)),
    )


def _tracked_plan_phase_scratch_paths() -> tuple[str, ...]:
    return tuple(
        path.as_posix()
        for path in sorted(Path("/tmp").glob("design-plan-impl-stack-*"))
        if path.is_dir()
    )


def _tracked_plan_phase_run_root_entries() -> tuple[str, ...]:
    entries = sorted(TRACKED_PLAN_PILOT_RUN_ROOT.iterdir(), key=lambda path: path.name)
    for entry in entries:
        assert not entry.is_symlink(), f"dedicated run-root entry is a symlink: {entry}"
        assert entry.is_dir(), f"dedicated run-root entry is not a directory: {entry}"
    return tuple(path.name for path in entries)


def _tracked_plan_phase_run_tree_projection(run_id: str) -> dict[str, object]:
    assert run_id in TRACKED_PLAN_PILOT_RUN_IDS
    run_path = TRACKED_PLAN_PILOT_RUN_ROOT / run_id
    assert run_path.is_dir() and not run_path.is_symlink()
    rows: list[tuple[str, str, str | None]] = []
    for current, directories, filenames in os.walk(run_path, followlinks=False):
        directories.sort()
        filenames.sort()
        current_path = Path(current)
        for name in (*directories, *filenames):
            path = current_path / name
            assert not path.is_symlink(), f"run tree contains a symlink: {path}"
            relative = path.relative_to(run_path).as_posix()
            if path.is_dir():
                rows.append((relative, "directory", None))
            else:
                assert path.is_file(), f"run tree contains unsupported entry: {path}"
                rows.append((relative, "file", _sha256_path(path)))
    canonical = json.dumps(
        sorted(rows), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return {
        "id": run_id,
        "relative_path": run_id,
        "tree_sha256": f"sha256:{hashlib.sha256(canonical).hexdigest()}",
        "entry_count": len(rows),
    }


def _assert_tracked_plan_phase_fixed_root() -> None:
    assert TRACKED_PLAN_PILOT_RUN_ROOT.exists() and TRACKED_PLAN_PILOT_RUN_ROOT.is_dir()
    assert not TRACKED_PLAN_PILOT_RUN_ROOT.is_symlink(), "dedicated run root cannot be a symlink"
    assert TRACKED_PLAN_PILOT_RUN_ROOT.resolve(strict=True) == (
        REPO_ROOT.resolve(strict=True)
        / ".orchestrate"
        / "procedure-first-pilot-evidence"
        / "tracked-plan-phase"
        / "workspace"
        / ".orchestrate"
        / "runs"
    )
    current = Path(TRACKED_PLAN_PILOT_RUN_ROOT.anchor)
    for part in TRACKED_PLAN_PILOT_RUN_ROOT.parts[1:]:
        current /= part
        assert not current.is_symlink(), f"dedicated run root has symlink component: {current}"


def _load_tracked_plan_phase_bound_pre_edit_scan(
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    assert _sha256_path(TRACKED_PLAN_PILOT_PRE_EDIT_SCAN) == TRACKED_PLAN_PILOT_PRE_EDIT_SCAN_SHA256
    evidence_index = _load_json(TRACKED_PLAN_PILOT_EVIDENCE_INDEX)
    indexed = evidence_index["artifacts"]["pre_edit_known_store_scans"]
    assert indexed == {
        "path": (
            "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/"
            "pre_edit_known_store_scans.json"
        ),
        "sha256": TRACKED_PLAN_PILOT_PRE_EDIT_SCAN_SHA256,
    }
    pre_edit = _load_json(TRACKED_PLAN_PILOT_PRE_EDIT_SCAN)
    assert pre_edit["schema"] == "procedure_first_pilot_pre_edit_known_store_scans.v1"
    root_scope = pre_edit["root_scope"]
    assert root_scope["legacy_repository_root"] == TRACKED_PLAN_PILOT_LEGACY_RUN_ROOT.as_posix()
    assert root_scope["dedicated_runtime_evidence_root"] == TRACKED_PLAN_PILOT_RUN_ROOT.as_posix()
    expected_legacy_scan = pre_edit["scans"]["legacy_repository_root"]["scanner_result"]
    expected_dedicated_scan = pre_edit["scans"]["dedicated_runtime_evidence_root"][
        "scanner_result"
    ]
    assert isinstance(expected_legacy_scan, dict)
    assert isinstance(expected_dedicated_scan, dict)
    return pre_edit, expected_legacy_scan, expected_dedicated_scan


def _scan_tracked_plan_phase_store(
    pre_edit: dict[str, object],
    root: Path,
) -> dict[str, object]:
    from orchestrator.workflow_lisp.procedure_identity_retirement import scan_known_state_store

    query = pre_edit["old_identity_query"]
    observed = scan_known_state_store(
        root,
        retired_identities=set(query["identities"]),
        query_version=query["query_version"],
    )
    assert isinstance(observed, dict)
    return observed


def _tracked_plan_phase_runtime_identity_projection(bundle: object) -> dict[str, object]:
    baseline = _load_json(
        REPO_ROOT / "tests" / "baselines" / "procedure_first" / "tracked_plan_phase.json"
    )
    old_runtime = baseline["runtime_contract"]
    runtime_plan = bundle.runtime_plan
    observed_checkpoint_ids = sorted(
        checkpoint.checkpoint_id for checkpoint in runtime_plan.lexical_checkpoint_points
    )
    observed_presentation_keys = sorted(
        {checkpoint.presentation_key for checkpoint in runtime_plan.resume_checkpoints}
    )
    return {
        "classification": "provisional_old_new_identity_characterization",
        "frozen_baseline_sha256": _sha256_path(
            REPO_ROOT / "tests" / "baselines" / "procedure_first" / "tracked_plan_phase.json"
        ),
        "old_checkpoint_ids": sorted(
            row["checkpoint_id"] for row in old_runtime["lexical_checkpoints"]
        ),
        "new_checkpoint_ids": observed_checkpoint_ids,
        "old_presentation_keys": sorted(
            {row["presentation_key"] for row in old_runtime["resume_checkpoints"]}
        ),
        "new_presentation_keys": observed_presentation_keys,
        "approval_asserted": False,
    }


def _tracked_plan_phase_artifact_projection(
    workspace: Path,
    output_paths: dict[str, str],
) -> dict[str, object]:
    artifacts: dict[str, object] = {}
    for name, relpath in sorted(output_paths.items()):
        path = workspace / relpath
        assert path.is_file(), relpath
        artifacts[name] = {"path": relpath, "sha256": _sha256_path(path)}
    return artifacts


def _tracked_plan_phase_common_run_projection(
    *,
    run_id: str,
    state: dict[str, object],
    output_paths: dict[str, str],
    bundle: object,
) -> dict[str, object]:
    identity_projection = _tracked_plan_phase_runtime_identity_projection(bundle)
    return {
        "evidence_status": "provisional_characterization",
        "run_id": run_id,
        "run_root": TRACKED_PLAN_PILOT_RUN_ROOT.as_posix(),
        "workflow_name": (
            "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack"
        ),
        "workflow_outputs": state["workflow_outputs"],
        "source": {
            "path": "workflows/examples/design_plan_impl_review_stack_v2_call.orc",
            "sha256": _sha256_path(
                EXAMPLES / "design_plan_impl_review_stack_v2_call.orc"
            ),
        },
        "run": _tracked_plan_phase_run_tree_projection(run_id),
        "artifacts": _tracked_plan_phase_artifact_projection(
            TRACKED_PLAN_PILOT_WORKSPACE,
            output_paths,
        ),
        "checkpoint_ids": identity_projection["new_checkpoint_ids"],
        "presentation_keys": identity_projection["new_presentation_keys"],
        "registered_workflows": list(bundle.registered_workflows),
        "identity_comparison": identity_projection,
    }


def _publish_tracked_plan_phase_evidence_pair_atomically(
    clean: dict[str, object],
    interruption: dict[str, object],
    *,
    targets: tuple[Path, Path] = (
        TRACKED_PLAN_PILOT_CLEAN_EVIDENCE,
        TRACKED_PLAN_PILOT_RESUME_EVIDENCE,
    ),
) -> None:
    _validate_tracked_plan_phase_retained_projections(clean, interruption)
    assert all(not target.exists() for target in targets), (
        "retained evidence targets must both be absent before publication"
    )
    target_payloads = tuple(zip(targets, (clean, interruption), strict=True))
    temporary_paths: list[Path] = []
    published_paths: list[Path] = []
    try:
        for target, payload in target_payloads:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
            assert not temporary.exists(), f"stale evidence staging file exists: {temporary}"
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary_paths.append(temporary)
        for temporary, (target, _payload) in zip(
            temporary_paths, target_payloads, strict=True
        ):
            os.replace(temporary, target)
            published_paths.append(target)
    except BaseException:
        for published in published_paths:
            published.unlink(missing_ok=True)
        raise
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)


@pytest.mark.skipif(
    os.environ.get(TRACKED_PLAN_PILOT_LIVE_ENV) != "1",
    reason="exact two-run pilot evidence is an explicit one-time owner-authorized gate",
)
def test_tracked_plan_phase_exact_two_run_evidence() -> None:
    _assert_tracked_plan_phase_fixed_root()
    assert not TRACKED_PLAN_PILOT_CLEAN_EVIDENCE.exists()
    assert not TRACKED_PLAN_PILOT_RESUME_EVIDENCE.exists()
    pre_edit, expected_legacy_scan, expected_dedicated_scan = (
        _load_tracked_plan_phase_bound_pre_edit_scan()
    )
    observed_preflight_scan = _scan_tracked_plan_phase_store(
        pre_edit, TRACKED_PLAN_PILOT_LEGACY_RUN_ROOT
    )
    observed_preflight_dedicated_scan = _scan_tracked_plan_phase_store(
        pre_edit, TRACKED_PLAN_PILOT_RUN_ROOT
    )
    _validate_tracked_plan_phase_preflight_projection(
        expected_run_root=TRACKED_PLAN_PILOT_RUN_ROOT.as_posix(),
        observed_run_root=TRACKED_PLAN_PILOT_RUN_ROOT.resolve(strict=True).as_posix(),
        dedicated_run_ids=_tracked_plan_phase_run_root_entries(),
        scratch_paths=_tracked_plan_phase_scratch_paths(),
        expected_legacy_scan=expected_legacy_scan,
        observed_legacy_scan=observed_preflight_scan,
        expected_dedicated_scan=expected_dedicated_scan,
        observed_dedicated_scan=observed_preflight_dedicated_scan,
    )

    clean_control: dict[str, object] = {}
    clean_state, output_paths, clean_bundle = _execute_design_plan_impl_stack_single_pass_runtime(
        TRACKED_PLAN_PILOT_WORKSPACE,
        run_id=TRACKED_PLAN_PILOT_RUN_IDS[0],
        provider_control=clean_control,
    )
    expected_roles = [
        "design.draft",
        "design.review",
        "plan.draft",
        "plan.review",
        "implementation.execute",
        "implementation.review",
    ]
    assert clean_state["status"] == "completed"
    assert clean_state.get("error") is None
    assert clean_state["workflow_outputs"] == _tracked_plan_phase_expected_outputs()
    assert clean_control == {
        "attempts": {role: 1 for role in expected_roles},
        "successful_roles": expected_roles,
    }
    clean_projection = {
        "schema": "procedure_first_pilot_tracked_plan_clean_run.v1",
        **_tracked_plan_phase_common_run_projection(
            run_id=TRACKED_PLAN_PILOT_RUN_IDS[0],
            state=clean_state,
            output_paths=output_paths,
            bundle=clean_bundle,
        ),
        "status": "completed",
        "provider_roles": expected_roles,
    }

    interruption_control: dict[str, object] = {
        "interrupt_after_role": "plan.draft"
    }
    interrupted_state, interrupted_paths, interrupted_bundle = (
        _execute_design_plan_impl_stack_single_pass_runtime(
            TRACKED_PLAN_PILOT_WORKSPACE,
            run_id=TRACKED_PLAN_PILOT_RUN_IDS[1],
            provider_control=interruption_control,
        )
    )
    assert interrupted_state["status"] == "running"
    assert interrupted_state.get("error") is None
    assert interruption_control["successful_roles"] == expected_roles[:3]
    assert interruption_control["attempts"] == {
        role: 1 for role in expected_roles[:3]
    }
    assert interruption_control["checkpoint_hook_completed"] is True
    assert interruption_control["interruption_emitted"] is True
    assert isinstance(interruption_control["interruption_target_step_id"], str)

    resumed_state, resumed_paths, resumed_bundle = _execute_design_plan_impl_stack_single_pass_runtime(
        TRACKED_PLAN_PILOT_WORKSPACE,
        run_id=TRACKED_PLAN_PILOT_RUN_IDS[1],
        provider_control=interruption_control,
        resume=True,
    )
    assert resumed_state["status"] == "completed"
    assert resumed_state.get("error") is None
    assert resumed_state["workflow_outputs"] == clean_state["workflow_outputs"]
    assert interrupted_paths == resumed_paths == output_paths
    assert interruption_control["successful_roles"] == expected_roles
    assert interruption_control["attempts"] == {
        "design.draft": 1,
        "design.review": 1,
        "plan.draft": 1,
        "plan.review": 1,
        "implementation.execute": 1,
        "implementation.review": 1,
    }
    interruption_projection = {
        "schema": "procedure_first_pilot_tracked_plan_interruption_resume.v1",
        **_tracked_plan_phase_common_run_projection(
            run_id=TRACKED_PLAN_PILOT_RUN_IDS[1],
            state=resumed_state,
            output_paths=resumed_paths,
            bundle=resumed_bundle,
        ),
        "interruption": {
            "status": "process_interrupted",
            "persisted_status": interrupted_state["status"],
            "interruption_point": "post_plan_draft_checkpoint_commit",
            "completed_provider_roles": expected_roles[:3],
            "successful_provider_role_count": 3,
            "next_provider_role_not_attempted": "plan.review",
        },
        "resume": {
            "status": "completed",
            "reused_provider_roles": expected_roles[:3],
            "executed_provider_roles": expected_roles[3:],
            "provider_role_attempts": interruption_control["attempts"],
        },
        "comparison": {
            "public_output_equal_to_clean": True,
            "artifacts_equal_to_clean": (
                _tracked_plan_phase_artifact_projection(
                    TRACKED_PLAN_PILOT_WORKSPACE,
                    resumed_paths,
                )
                == clean_projection["artifacts"]
            ),
        },
    }
    _validate_tracked_plan_phase_retained_projections(clean_projection, interruption_projection)

    observed_postflight_scan = _scan_tracked_plan_phase_store(
        pre_edit, TRACKED_PLAN_PILOT_LEGACY_RUN_ROOT
    )
    observed_postflight_dedicated_scan = _scan_tracked_plan_phase_store(
        pre_edit, TRACKED_PLAN_PILOT_RUN_ROOT
    )
    _validate_tracked_plan_phase_postflight_projection(
        dedicated_run_ids=_tracked_plan_phase_run_root_entries(),
        scratch_paths=_tracked_plan_phase_scratch_paths(),
        expected_legacy_scan=expected_legacy_scan,
        observed_legacy_scan=observed_postflight_scan,
        expected_dedicated_scan=expected_dedicated_scan,
        observed_dedicated_scan=observed_postflight_dedicated_scan,
    )
    _publish_tracked_plan_phase_evidence_pair_atomically(
        clean_projection,
        interruption_projection,
    )


@pytest.mark.skipif(
    not (
        TRACKED_PLAN_PILOT_CLEAN_EVIDENCE.exists()
        and TRACKED_PLAN_PILOT_RESUME_EVIDENCE.exists()
    ),
    reason="retained pilot evidence has not been published",
)
def test_tracked_plan_phase_retained_run_evidence_replays() -> None:
    with patch.object(StateManager, "__init__", side_effect=AssertionError("runtime forbidden")), patch.object(
        WorkflowExecutor,
        "__init__",
        side_effect=AssertionError("runtime forbidden"),
    ), patch(
        "orchestrator.workflow_lisp.procedure_identity_retirement.scan_known_state_store",
        side_effect=AssertionError("scanner forbidden"),
    ):
        clean = _load_json(TRACKED_PLAN_PILOT_CLEAN_EVIDENCE)
        interruption = _load_json(TRACKED_PLAN_PILOT_RESUME_EVIDENCE)
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


def test_design_plan_impl_stack_orc_retains_public_contract_without_a_runtime_run(
    tmp_path: Path,
) -> None:
    provider_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.providers.json")
    prompt_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json")
    with patch.object(StateManager, "__init__", side_effect=AssertionError("runtime forbidden")), patch.object(
        WorkflowExecutor,
        "__init__",
        side_effect=AssertionError("runtime forbidden"),
    ):
        result = compile_stage3_entrypoint(
            EXAMPLES / "design_plan_impl_review_stack_v2_call.orc",
            source_roots=(WORKFLOWS,),
            provider_externs=provider_externs,
            prompt_externs=prompt_externs,
            command_boundaries={},
            validate_shared=True,
            workspace_root=tmp_path,
        ).entry_result

    assert set(result.validated_bundles) == {
        "examples/design_plan_impl_review_stack_v2_call::tracked-design-phase",
        (
            "examples/design_plan_impl_review_stack_v2_call::"
            "design-plan-impl-implementation-phase"
        ),
        "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack",
    }
    baseline = _load_json(
        REPO_ROOT / "tests" / "baselines" / "procedure_first" / "tracked_plan_phase.json"
    )
    expected_public = baseline["public_contract"]
    module_name = "examples/design_plan_impl_review_stack_v2_call"
    assert result.module.module_name == module_name
    assert list(result.module.exports) == expected_public["exported_workflows"] == [
        "design-plan-impl-review-stack"
    ]
    public_bundle = result.validated_bundles[
        "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack"
    ]
    public_workflow = next(
        workflow
        for workflow in result.typed_workflows
        if workflow.definition.name
        == "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack"
    )

    def type_contract(type_ref) -> dict[str, object]:
        contract: dict[str, object] = {"type_name": type_ref.name}
        definition = getattr(type_ref, "definition", None)
        if definition is not None:
            for field_name in ("kind", "under", "must_exist"):
                if hasattr(definition, field_name):
                    contract[field_name] = getattr(definition, field_name)
        allowed_values = getattr(type_ref, "allowed_values", ())
        if allowed_values:
            contract["allowed_values"] = list(allowed_values)
        return contract

    signature = public_workflow.signature
    actual_inputs = [
        {
            "name": name,
            "default": signature.param_defaults.get(name),
            **type_contract(type_ref),
        }
        for name, type_ref in signature.params
    ]
    return_type = signature.return_type_ref
    actual_outputs = [
        {"name": field.name, **type_contract(return_type.field_types[field.name])}
        for field in return_type.definition.fields
    ]
    assert actual_inputs == expected_public["inputs"]
    assert actual_outputs == expected_public["outputs"]
    assert return_type.name == expected_public["return_type"] == "StackOutput"
    assert len(actual_inputs) == 7
    assert len(actual_outputs) == 9

    def field_projection(field) -> tuple[tuple[str, object], ...]:
        return tuple(
            (
                key,
                tuple(field[key])
                if isinstance(field[key], (list, tuple))
                else field[key],
            )
            for key in ("name", "json_pointer", "type", "under", "must_exist_target", "allowed")
            if key in field
        )

    def contract_projection(output_bundle, variant_output, publishes) -> tuple[object, ...]:
        if output_bundle is not None:
            body = ("output", tuple(field_projection(field) for field in output_bundle["fields"]))
        else:
            assert variant_output is not None
            body = (
                "variant",
                field_projection(variant_output["discriminant"]),
                tuple(field_projection(field) for field in variant_output["shared_fields"]),
                tuple(sorted(variant_output["variants"])),
            )
        return body, tuple(publishes)

    actual_artifact_contracts = sorted(
        contract_projection(step.common.output_bundle, step.common.variant_output, step.common.publishes)
        for bundle in result.validated_bundles.values()
        for step in bundle.surface.steps
        if step.kind.value == "provider"
    )
    expected_artifact_contracts = sorted(
        contract_projection(
            row["output_bundle_contract"], row["variant_output_contract"], row["publishes"]
        )
        for row in baseline["artifact_contracts"]
    )
    assert actual_artifact_contracts == expected_artifact_contracts
    actual_effects = sorted(
        tuple(
            sorted(
                {
                    "kind": type(effect).__name__,
                    "subject": ".".join(effect.subject),
                }.items()
            )
        )
        for effect in public_workflow.effect_summary.transitive_effects
        if not (
            type(effect).__name__ == "CallsWorkflowEffect"
            and ".".join(effect.subject) == f"{module_name}::tracked-plan-phase"
        )
    )
    expected_effects = sorted(
        tuple(
            sorted(
                {
                    **row,
                    "subject": row["subject"].replace("$module", module_name),
                }.items()
            )
        )
        for row in baseline["caller_visible_effects"]
    )
    assert actual_effects == expected_effects
    output_path_roles = _tracked_plan_phase_compiler_output_path_roles(
        result,
        public_bundle,
        run_id=TRACKED_PLAN_PILOT_RUN_IDS[0],
    )
    assert set(output_path_roles.values()) == {
        "design.draft",
        "design.review",
        "plan.draft",
        "plan.review",
        "implementation.execute",
        "implementation.review",
    }
    interruption_target = _tracked_plan_phase_checkpoint_point_for_provider_role(
        public_bundle,
        output_path_roles,
        role="plan.draft",
        run_id=TRACKED_PLAN_PILOT_RUN_IDS[0],
    )
    assert interruption_target.checkpoint_id in TRACKED_PLAN_PILOT_NEW_CHECKPOINT_IDS
    assert interruption_target.node_id in public_bundle.runtime_plan.ordered_node_ids
    identity_projection = _tracked_plan_phase_runtime_identity_projection(public_bundle)
    assert identity_projection["new_checkpoint_ids"] == list(
        TRACKED_PLAN_PILOT_NEW_CHECKPOINT_IDS
    )
    assert identity_projection["new_presentation_keys"] == list(
        TRACKED_PLAN_PILOT_NEW_PRESENTATION_KEYS
    )


def test_library_orc_variants_compile_independently(tmp_path: Path) -> None:
    provider_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.providers.json")
    prompt_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json")

    library_targets = [
        WORKFLOWS / "library" / "tracked_design_phase.orc",
        WORKFLOWS / "library" / "tracked_plan_phase.orc",
        WORKFLOWS / "library" / "design_plan_impl_implementation_phase.orc",
    ]

    expected = {
        "tracked_design_phase.orc": "tracked-design-phase",
        "tracked_plan_phase.orc": "tracked-plan-phase",
        "design_plan_impl_implementation_phase.orc": "design-plan-impl-implementation-phase",
    }

    for target in library_targets:
        result = compile_stage3_module(
            target,
            provider_externs=provider_externs,
            prompt_externs=prompt_externs,
            command_boundaries={},
            validate_shared=True,
            workspace_root=tmp_path,
        )
        lowered_names = {
            _workflow_short_name(workflow.typed_workflow.definition.name)
            for workflow in result.lowered_workflows
        }
        assert lowered_names == {expected[target.name]}


def test_promoted_entry_experiment_ctx_bootstraps_without_name_table_edits(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        EXPERIMENT_CTX_FIXTURE,
        source_roots=(LISP_FIXTURES,),
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result
    workflow_name = "context_generalization_experiment_ctx::entry"
    bundle = result.validated_bundles[workflow_name]
    binding = bundle.provenance.private_exec_context_bindings[0]
    public_inputs = set(_workflow_public_input_contracts(bundle))
    hidden_context_inputs = set(_workflow_runtime_context_inputs(bundle))

    assert public_inputs == set()
    assert hidden_context_inputs == {
        "ctx__run__run-id",
        "ctx__run__state-root",
        "ctx__run__artifact-root",
    }
    assert binding.context_family == "RunCtxAnchored"
    assert binding.projection_hints == {
        "context_binding_schema_version": 1,
        "context_input_roles": {
            "ctx__run__run-id": "run_anchor:run-id",
            "ctx__run__state-root": "run_anchor:state-root",
            "ctx__run__artifact-root": "run_anchor:artifact-root",
        },
    }

    state_manager = StateManager(workspace=tmp_path, run_id="experiment-ctx-run")
    state_manager.initialize(
        EXPERIMENT_CTX_FIXTURE.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={},
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__run_id": "experiment-ctx-run",
        "return__state_root": "state/run",
        "return__artifact_root": "artifacts/run",
    }


def test_promoted_entry_runctx_only_entry_constructs_drainctx_in_language(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        RUNCTX_ONLY_DRAIN_ENTRY_FIXTURE,
        source_roots=(LISP_FIXTURES,),
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result
    workflow_name = "context_generalization_runctx_only_drain_entry::entry"
    bundle = result.validated_bundles[workflow_name]
    hidden_context_inputs = set(_workflow_runtime_context_inputs(bundle))
    public_inputs = set(_workflow_public_input_contracts(bundle))

    assert hidden_context_inputs == {
        "run__run-id",
        "run__state-root",
        "run__artifact-root",
    }
    assert public_inputs == {"manifest", "ledger"}
    assert hidden_context_inputs.isdisjoint(public_inputs)

    manifest_path = tmp_path / "state" / "manifest.json"
    ledger_path = tmp_path / "state" / "ledger.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{}\n", encoding="utf-8")
    ledger_path.write_text("{}\n", encoding="utf-8")

    state_manager = StateManager(workspace=tmp_path, run_id="drain-run")
    state_manager.initialize(
        RUNCTX_ONLY_DRAIN_ENTRY_FIXTURE.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "manifest": "state/manifest.json",
            "ledger": "state/ledger.json",
        },
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__run_id": "drain-run",
        "return__state_root": "state/run",
        "return__manifest": "state/manifest.json",
        "return__ledger": "state/ledger.json",
    }


def test_std_context_imported_phase_ctx_supports_hidden_binding(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        STD_CONTEXT_IMPORT_FIXTURE,
        source_roots=(LISP_FIXTURES,),
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result
    workflow_name = "context_generalization_std_context_import::entry"
    bundle = result.validated_bundles[workflow_name]
    binding = bundle.provenance.private_exec_context_bindings[0]

    assert set(_workflow_public_input_contracts(bundle)) == set()
    assert set(_workflow_runtime_context_inputs(bundle)) == {
        "phase-ctx__run__run-id",
        "phase-ctx__run__state-root",
        "phase-ctx__run__artifact-root",
        "phase-ctx__phase-name",
        "phase-ctx__state-root",
        "phase-ctx__artifact-root",
    }
    assert binding.context_family == "PhaseCtx"

    state_manager = StateManager(workspace=tmp_path, run_id="std-context-phase")
    state_manager.initialize(
        STD_CONTEXT_IMPORT_FIXTURE.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={},
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__phase_name": "imported-phase",
        "return__state_root": "state/imported-phase",
    }


def test_context_generalization_anchorless_state_path_fixture_rejects_low_level_state_boundary(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            ANCHORLESS_STATE_PATH_FIXTURE,
            source_roots=(LISP_INVALID_FIXTURES,),
            command_boundaries={
                "emit_state_root": ExternalToolBinding(
                    name="emit_state_root",
                    stable_command=("python", "scripts/emit_state_root.py"),
                ),
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lint_profile=LINT_PROFILE_STRICT,
        )

    assert excinfo.value.diagnostics[0].code == "low_level_state_path_in_high_level_module"


def test_context_generalization_roleless_binding_fixture_reports_unsupported_bootstrap(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            ROLELESS_BINDING_FIXTURE,
            source_roots=(LISP_INVALID_FIXTURES,),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "private_exec_context_bootstrap_unsupported"
    assert "ctx__experiment-root" in diagnostic.message


def test_promoted_entry_resume_or_start_fixture_bootstraps_hidden_context(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    fixture = LISP_FIXTURES / "phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc"
    workspace = Path(tempfile.mkdtemp(prefix="orc-pe-", dir="/tmp"))
    monkeypatch.chdir(workspace)
    result = compile_stage3_entrypoint(
        fixture,
        source_roots=(LISP_FIXTURES,),
        command_boundaries={
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
        },
        validate_shared=True,
        workspace_root=workspace,
    ).entry_result
    bundle = result.validated_bundles[
        "phase_stdlib_resume_or_start_promoted_entry_bootstrap::promoted-entry-resume-plan-gate-wrapper"
    ]
    imported_resume_bundle = bundle.imports[
        "library/phase_stdlib_resume_or_start_promoted_entry_bootstrap_helper::resume-plan-gate-wrapper"
    ]
    validator_step = imported_resume_bundle.surface.steps[0]
    assert validator_step.command[:3] == (
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state",
    )
    validator_payload = json.loads(validator_step.command[-1])
    public_inputs = _workflow_public_input_contracts(bundle)
    assert set(public_inputs) == {
        "inputs__resume_from",
        "inputs__design",
        "inputs__plan",
        "inputs__report_path",
    }
    assert all("phase-ctx__" not in name for name in public_inputs)
    assert all("run-id" not in name for name in public_inputs)
    assert all("state-root" not in name for name in public_inputs)
    assert all("artifact-root" not in name for name in public_inputs)
    assert workflow_managed_write_root_inputs(bundle) == ()
    assert set(_workflow_runtime_context_inputs(bundle)) == {
        "phase-ctx__run__run-id",
        "phase-ctx__run__state-root",
        "phase-ctx__run__artifact-root",
        "phase-ctx__phase-name",
        "phase-ctx__state-root",
        "phase-ctx__artifact-root",
    }
    assert all(name not in public_inputs for name in _workflow_runtime_context_inputs(bundle))

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name
        == "phase_stdlib_resume_or_start_promoted_entry_bootstrap::promoted-entry-resume-plan-gate-wrapper"
    )
    call_step = next(step for step in authored["steps"] if step.get("call"))
    assert call_step["call"].endswith("::resume-plan-gate-wrapper")
    assert {
        name: call_step["with"][name]
        for name in (
            "phase-ctx__run__run-id",
            "phase-ctx__run__state-root",
            "phase-ctx__run__artifact-root",
            "phase-ctx__phase-name",
            "phase-ctx__state-root",
            "phase-ctx__artifact-root",
        )
    } == {
        "phase-ctx__run__run-id": {"ref": "inputs.phase-ctx__run__run-id"},
        "phase-ctx__run__state-root": {"ref": "inputs.phase-ctx__run__state-root"},
        "phase-ctx__run__artifact-root": {"ref": "inputs.phase-ctx__run__artifact-root"},
        "phase-ctx__phase-name": {"ref": "inputs.phase-ctx__phase-name"},
        "phase-ctx__state-root": {"ref": "inputs.phase-ctx__state-root"},
        "phase-ctx__artifact-root": {"ref": "inputs.phase-ctx__artifact-root"},
    }

    design_path = workspace / "docs" / "design" / "selected-item-design.md"
    plan_path = workspace / "docs" / "plans" / "selected-item-plan.md"
    report_path = workspace / "artifacts" / "work" / "selected-item-execution.md"
    for target in (design_path, plan_path, report_path):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("seed\n", encoding="utf-8")

    bundle_path = workspace / "state" / "selected-item" / "plan-gate.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(
        json.dumps(
            {
                "variant": "APPROVED",
                "report_path": "artifacts/work/selected-item-execution.md",
            }
        ),
        encoding="utf-8",
    )

    payload = {
        **validator_payload,
        "bundle_path": "state/selected-item/plan-gate.json",
        "resume_from": "state/selected-item/plan-gate.json",
        "current_public_inputs": {
            "phase-ctx__phase-name": "plan-gate-wrapper",
            "inputs__resume_from": "state/selected-item/plan-gate.json",
            "inputs__design": "docs/design/selected-item-design.md",
            "inputs__plan": "docs/plans/selected-item-plan.md",
            "inputs__report_path": "artifacts/work/selected-item-execution.md",
        },
        "source_run_id": "promoted-entry-bootstrap",
        "source_step_id": "resume-plan-gate-wrapper",
        "source_call_frame_id": "root",
        "phase_id": "plan-gate-wrapper",
        "created_at": "2026-06-03T00:00:00Z",
    }
    payload_path = workspace / "state" / "payloads" / "promoted_entry_plan_gate_wrapper.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    assert write_reusable_phase_state_v1.main(
        ["write_reusable_phase_state_v1", payload_path.as_posix()]
    ) == 0
    capsys.readouterr()
    assert validate_reusable_phase_state.main(
        ["validate_reusable_phase_state", payload_path.as_posix()]
    ) == 0
    reusable_payload = json.loads(capsys.readouterr().out)
    assert reusable_payload["variant"] == "REUSABLE"

    script_path = workspace / "scripts" / "resolve_plan_gate.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "report_path = Path(sys.argv[1])",
                "report_path.parent.mkdir(parents=True, exist_ok=True)",
                "report_path.write_text('approved\\n', encoding='utf-8')",
                "bundle_path = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])",
                "bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                "bundle_path.write_text(",
                "    json.dumps(",
                    "        {",
                    "            'variant': 'APPROVED',",
                    "            'shared_report_path': report_path.as_posix(),",
                    "        }",
                "    ) + '\\n',",
                "    encoding='utf-8',",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    state_manager = StateManager(workspace=workspace, run_id="promoted-entry-bootstrap")
    state_manager.initialize(
        fixture.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "inputs__resume_from": "state/selected-item/plan-gate.json",
            "inputs__design": "docs/design/selected-item-design.md",
            "inputs__plan": "docs/plans/selected-item-plan.md",
            "inputs__report_path": "artifacts/work/selected-item-execution.md",
        },
    )
    state = WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "completed"
    outputs = state["workflow_outputs"]
    assert outputs["return__report_path"] == "artifacts/work/selected-item-execution.md"
    assert report_path.read_text(encoding="utf-8") == "seed\n"


def test_public_phase_ctx_entry_inputs_do_not_require_hidden_context_provenance(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "public_phase_ctx.orc"
    workflow_path.write_text(
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
                "  (defrecord WorkflowOutput",
                "    (report_path WorkReportTarget))",
                "  (defworkflow entry",
                "    ((phase-ctx PhaseCtx)",
                "     (report-path WorkReportTarget))",
                "    -> WorkflowOutput",
                "    (record WorkflowOutput :report_path report-path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_module(
        workflow_path,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles["entry"]
    assert _workflow_runtime_context_inputs(bundle) == ()

    state_manager = StateManager(workspace=tmp_path, run_id="public-phase-ctx")
    state_manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "report-path": "artifacts/work/report.md",
            "phase-ctx__run__run-id": "user-run",
            "phase-ctx__run__state-root": "state/user",
            "phase-ctx__run__artifact-root": "artifacts/user",
            "phase-ctx__phase-name": "implementation",
            "phase-ctx__state-root": "state/phase",
            "phase-ctx__artifact-root": "artifacts/phase",
        },
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__report_path": "artifacts/work/report.md",
    }


def test_promoted_entry_hidden_context_override_fails(tmp_path: Path) -> None:
    fixture = LISP_FIXTURES / "phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc"
    result = compile_stage3_entrypoint(
        fixture,
        source_roots=(LISP_FIXTURES,),
        command_boundaries={
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result
    bundle = result.validated_bundles[
        "phase_stdlib_resume_or_start_promoted_entry_bootstrap::promoted-entry-resume-plan-gate-wrapper"
    ]
    hidden_context_inputs = set(_workflow_runtime_context_inputs(bundle))
    assert "phase-ctx__phase-name" in hidden_context_inputs

    state_manager = StateManager(workspace=tmp_path, run_id="promoted-entry-hidden-context-override")
    state_manager.initialize(
        fixture.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "inputs__resume_from": "state/selected-item/plan-gate.json",
            "inputs__design": "docs/design/selected-item-design.md",
            "inputs__plan": "docs/plans/selected-item-plan.md",
            "inputs__report_path": "artifacts/work/selected-item-execution.md",
            "phase-ctx__phase-name": "forged-phase-name",
        },
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "failed"
    assert state["error"]["type"] == "contract_violation"
    assert state["error"]["context"]["reason"] == "promoted_entry_hidden_context_override"
    assert state["error"]["context"]["input"] == "phase-ctx__phase-name"
    assert state["error"]["context"]["expected"] == "plan-gate-wrapper"


def test_promoted_entry_hidden_context_metadata_missing_fails(tmp_path: Path) -> None:
    fixture = LISP_FIXTURES / "phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc"
    result = compile_stage3_entrypoint(
        fixture,
        source_roots=(LISP_FIXTURES,),
        command_boundaries={
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result
    bundle = result.validated_bundles[
        "phase_stdlib_resume_or_start_promoted_entry_bootstrap::promoted-entry-resume-plan-gate-wrapper"
    ]
    hidden_context_inputs = set(_workflow_runtime_context_inputs(bundle))
    assert "phase-ctx__phase-name" in hidden_context_inputs

    broken_bundle = replace(
        bundle,
        provenance=replace(
            bundle.provenance,
            runtime_context_inputs=(),
            private_exec_context_bindings=(),
        ),
    )
    assert _workflow_runtime_context_inputs(broken_bundle) == ()
    assert hidden_context_inputs.issubset(workflow_input_contracts(broken_bundle))

    state_manager = StateManager(workspace=tmp_path, run_id="promoted-entry-hidden-context-metadata-missing")
    state_manager.initialize(
        fixture.as_posix(),
        context=bundle_context_dict(broken_bundle),
        bound_inputs={
            "inputs__resume_from": "state/selected-item/plan-gate.json",
            "inputs__design": "docs/design/selected-item-design.md",
            "inputs__plan": "docs/plans/selected-item-plan.md",
            "inputs__report_path": "artifacts/work/selected-item-execution.md",
        },
    )

    state = WorkflowExecutor(broken_bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "failed"
    assert state["error"]["type"] == "contract_violation"
    assert state["error"]["context"]["reason"] == "promoted_entry_hidden_context_metadata_missing"
    assert set(state["error"]["context"]["inputs"]) == hidden_context_inputs


def test_promoted_entry_hidden_context_metadata_rebinds_without_flattened_defaults(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "private_exec_context_phase_entry.orc"
    script_path = tmp_path / "scripts" / "emit_phase_result.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "_, label, phase_name = sys.argv",
                "bundle_path = os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']",
                "with open(bundle_path, 'w', encoding='utf-8') as handle:",
                "    json.dump({'label': label, 'phase_name': phase_name}, handle)",
                "    handle.write('\\n')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    workflow_path.write_text(
        "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.14")',
                    "  (defmodule private_exec_context_phase_entry)",
                    "  (import std/phase :only (with-phase))",
                    "  (export entry run-phase)",
                    "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord Result",
                "    (label String)",
                "    (phase_name String))",
                "  (defworkflow entry",
                "    ((label String))",
                "    -> Result",
                "    (call run-phase",
                "      :label label))",
                "  (defworkflow run-phase",
                "    ((phase-ctx PhaseCtx)",
                "     (label String))",
                "    -> Result",
                "    (with-phase phase-ctx plan-gate-wrapper",
                "      (command-result emit_phase_result",
                "        :argv (\"python\" \"scripts/emit_phase_result.py\" label phase-ctx.phase-name)",
                "        :returns Result)))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(tmp_path,),
        command_boundaries={
            "emit_phase_result": ExternalToolBinding(
                name="emit_phase_result",
                stable_command=("python", "scripts/emit_phase_result.py"),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result
    workflow_name = "private_exec_context_phase_entry::entry"
    bundle = result.validated_bundles[workflow_name]
    hidden_context_inputs = set(_workflow_runtime_context_inputs(bundle))
    assert hidden_context_inputs == {
        "phase-ctx__run__run-id",
        "phase-ctx__run__state-root",
        "phase-ctx__run__artifact-root",
        "phase-ctx__phase-name",
        "phase-ctx__state-root",
        "phase-ctx__artifact-root",
    }

    stripped_inputs = dict(bundle.surface.inputs)
    for input_name in hidden_context_inputs:
        contract = stripped_inputs[input_name]
        contract_definition = dict(contract.definition)
        contract_definition.pop("default", None)
        stripped_inputs[input_name] = replace(contract, definition=contract_definition)
    stripped_bundle = replace(
        bundle,
        surface=replace(bundle.surface, inputs=stripped_inputs),
    )
    legacy_binding = replace(
        bundle.provenance.private_exec_context_bindings[0],
        projection_hints={},
    )
    legacy_compatibility_bundle = replace(
        stripped_bundle,
        provenance=replace(
            bundle.provenance,
            private_exec_context_bindings=(legacy_binding,),
        ),
    )

    def _execute(candidate_bundle, *, run_id: str) -> dict[str, object]:
        state_manager = StateManager(workspace=tmp_path, run_id=run_id)
        state_manager.initialize(
            workflow_path.as_posix(),
            context=bundle_context_dict(candidate_bundle),
            bound_inputs={"label": "selected-item"},
        )
        return WorkflowExecutor(candidate_bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    original_state = _execute(bundle, run_id="promoted-entry-defaults")
    stripped_state = _execute(stripped_bundle, run_id="rid-123")
    legacy_compatibility_state = _execute(
        legacy_compatibility_bundle,
        run_id="rid-legacy-compat",
    )

    assert original_state["status"] == "completed"
    assert stripped_state["status"] == "failed"
    assert stripped_state["error"]["context"]["reason"] == "private_exec_context_bootstrap_unsupported"
    assert legacy_compatibility_state["status"] == "completed"
    assert original_state["workflow_outputs"] == {
        "return__label": "selected-item",
        "return__phase_name": "plan-gate-wrapper",
    }
    assert legacy_compatibility_state["workflow_outputs"] == original_state["workflow_outputs"]
    assert legacy_compatibility_state["bound_inputs"]["phase-ctx__run__run-id"] == "rid-legacy-compat"
    assert (
        legacy_compatibility_state["bound_inputs"]["phase-ctx__phase-name"]
        == original_state["bound_inputs"]["phase-ctx__phase-name"]
    )
    assert (
        legacy_compatibility_state["bound_inputs"]["phase-ctx__run__state-root"]
        == original_state["bound_inputs"]["phase-ctx__run__state-root"]
    )
    assert (
        legacy_compatibility_state["bound_inputs"]["phase-ctx__run__artifact-root"]
        == original_state["bound_inputs"]["phase-ctx__run__artifact-root"]
    )
    assert (
        legacy_compatibility_state["bound_inputs"]["phase-ctx__state-root"]
        == original_state["bound_inputs"]["phase-ctx__state-root"]
    )
    assert (
        legacy_compatibility_state["bound_inputs"]["phase-ctx__artifact-root"]
        == original_state["bound_inputs"]["phase-ctx__artifact-root"]
    )


@pytest.mark.parametrize("context_name", ["SelectionCtx", "RecoveryCtx"])
def test_promoted_entry_reserved_private_context_families_report_unsupported_bootstrap(
    tmp_path: Path,
    context_name: str,
) -> None:
    workflow_path = tmp_path / f"private_exec_context_{context_name.lower()}.orc"
    workflow_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                f"  (defmodule private_exec_context_{context_name.lower()})",
                "  (export entry use-context)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                f"  (defrecord {context_name}",
                "    (run RunCtx)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord Result",
                "    (state_root Path.state-root))",
                "  (defworkflow entry",
                "    ()",
                "    -> Result",
                "    (call use-context))",
                "  (defworkflow use-context",
                f"    ((ctx {context_name}))",
                "    -> Result",
                "    (record Result :state_root ctx.state-root))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception) as excinfo:
        compile_stage3_entrypoint(
            workflow_path,
            source_roots=(tmp_path,),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostics = getattr(excinfo.value, "diagnostics", ())
    assert diagnostics, "expected frontend diagnostics"
    diagnostic = diagnostics[0]
    assert diagnostic.code == "private_exec_context_bootstrap_unsupported"
    assert context_name in diagnostic.message


def test_resume_or_start_plan_gate_reusable_state_parity_path(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    design_path = tmp_path / "docs" / "design" / "selected-item-design.md"
    plan_path = tmp_path / "docs" / "plans" / "selected-item-plan.md"
    report_path = tmp_path / "artifacts" / "work" / "selected-item-execution.md"
    for target in (design_path, plan_path, report_path):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("seed\n", encoding="utf-8")

    bundle_path = tmp_path / "state" / "selected-item" / "plan-gate.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "variant": "APPROVED",
        "execution_report_path": "artifacts/work/selected-item-execution.md",
    }
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

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
        "bundle_path": "state/selected-item/plan-gate.json",
        "resume_from": "state/selected-item/plan-gate.json",
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
        "public_input_hash_basis": [
            "inputs__design",
            "inputs__plan",
            "inputs__report_path",
        ],
        "current_public_inputs": {
            "inputs__design": "docs/design/selected-item-design.md",
            "inputs__plan": "docs/plans/selected-item-plan.md",
            "inputs__report_path": "artifacts/work/selected-item-execution.md",
        },
        "producer_fingerprint_basis": {
            "workflow_name": "selected-item::plan-gate",
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
            "public_input_hash_basis": [
                "inputs__design",
                "inputs__plan",
                "inputs__report_path",
            ],
        },
        "source_run_id": "selected-item-run",
        "source_step_id": "plan-gate",
        "source_call_frame_id": "root",
        "phase_id": "plan-gate",
        "created_at": "2026-06-02T00:00:00Z",
    }
    payload_path = tmp_path / "state" / "payloads" / "selected_item_plan_gate.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    assert write_reusable_phase_state_v1.main(["write_reusable_phase_state_v1", payload_path.as_posix()]) == 0
    capsys.readouterr()

    reusable_exit = validate_reusable_phase_state.main(["validate_reusable_phase_state", payload_path.as_posix()])
    reusable_payload = json.loads(capsys.readouterr().out)
    assert reusable_exit == 0
    assert reusable_payload["variant"] == "REUSABLE"

    load_exit = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": reusable_payload["source_bundle_path"],
                    "target_dsl_version": "2.14",
                    "return_type_name": "PlanGateResult",
                    "expected_contract_fingerprint": payload["expected_contract_fingerprint"],
                    "structured_contract_kind": "union",
                    "structured_contract": structured_contract,
                    "source_bundle_sha256": reusable_payload["source_bundle_sha256"],
                }
            ),
        ]
    )
    loaded = json.loads(capsys.readouterr().out)
    assert load_exit == 0
    assert loaded == bundle

    stale_payload = dict(payload)
    stale_payload["current_public_inputs"] = {
        "inputs__design": "docs/design/selected-item-design-v2.md",
        "inputs__plan": "docs/plans/selected-item-plan.md",
        "inputs__report_path": "artifacts/work/selected-item-execution.md",
    }
    stale_payload_path = tmp_path / "state" / "payloads" / "selected_item_plan_gate_stale.json"
    stale_payload_path.write_text(json.dumps(stale_payload), encoding="utf-8")
    stale_exit = validate_reusable_phase_state.main(["validate_reusable_phase_state", stale_payload_path.as_posix()])
    stale_result = json.loads(capsys.readouterr().out)
    assert stale_exit == 0
    assert stale_result == {"variant": "STALE"}

    report_path.unlink()
    missing_exit = validate_reusable_phase_state.main(["validate_reusable_phase_state", payload_path.as_posix()])
    missing_result = json.loads(capsys.readouterr().out)
    assert missing_exit == 0
    assert missing_result == {"variant": "MISSING_ARTIFACT"}


def test_resume_or_start_plan_gate_reusable_state_parity_path_wrapper_union_contract(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "phase_stdlib_resume_or_start_reusable_wrapper.orc"
    fixture.write_text(
        (LISP_FIXTURES / "phase_stdlib_resume_or_start_reusable_wrapper.orc").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = compile_stage3_module(
        fixture,
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
        validate_shared=True,
        workspace_root=tmp_path,
    )
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if _workflow_short_name(workflow.typed_workflow.definition.name) == "resume-plan-gate-wrapper"
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
        if step.get("call") == "phase_stdlib_resume_or_start_reusable_wrapper::wrap-plan-gate"
    )

    assert call_step["call"] == "phase_stdlib_resume_or_start_reusable_wrapper::wrap-plan-gate"
    assert "load_canonical_phase_result__PlanGateWrapperResult" in result.command_boundary_environment.bindings_by_name
    assert "resume-plan-gate-wrapper" in {
        _workflow_short_name(workflow.typed_workflow.definition.name) for workflow in result.lowered_workflows
    }


def test_review_loop_parity_fixture_compiles_to_resume_safe_repeat_until_via_imported_stdlib_route(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "phase_stdlib_review_loop.orc"
    fixture.write_text(
        (LISP_FIXTURES / "phase_stdlib_review_loop.orc").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for relpath in (
        "prompts/implementation/review.md",
        "prompts/implementation/fix.md",
    ):
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("prompt\n", encoding="utf-8")
    result = compile_stage3_module(
        fixture,
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
    bundle = result.validated_bundles["phase_stdlib_review_loop::review-revise-loop-demo"]
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "phase_stdlib_review_loop::review-revise-loop-demo"
    )
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    seed_step = next(step for step in authored["steps"] if step["name"].endswith("__seed"))
    body_steps = repeat_step["repeat_until"]["steps"]
    seed_values = {
        value["name"]: value
        for value in seed_step["materialize_artifacts"]["values"]
    }

    nested_steps = list(_iter_nested_steps(body_steps))
    assert any(
        isinstance(step.get("call"), str) and step["call"].endswith("::run-review.v1")
        for step in nested_steps
    )
    assert any(
        isinstance(step.get("call"), str) and step["call"].endswith("::apply-fix.v1")
        for step in nested_steps
    )
    assert any(
        any(step.get("provider") == provider for step in workflow.authored_mapping.get("steps", ()))
        for provider in ("fake-review", "fake-fix")
        for workflow in result.lowered_workflows
    )
    assert authored["outputs"]["return__review_report"]["under"] == "artifacts/review"
    assert authored["outputs"]["return__last_review_report"]["under"] == "artifacts/review"
    assert authored["outputs"]["return__findings__items_path"]["under"] == "artifacts/work"
    assert seed_values["state__last_review_report"]["source"] == {
        "literal": "artifacts/review/last-review-report.md"
    }
    assert seed_values["state__latest_findings__items_path"]["source"] == {
        "literal": "artifacts/work/review-findings-seed.json"
    }

    frame_checkpoint = next(
        checkpoint
        for checkpoint in bundle.runtime_plan.resume_checkpoints
        if checkpoint.checkpoint_kind == "repeat_until_frame"
    )
    loop_node_id = next(
        node_id
        for node_id, projection in bundle.projection.repeat_until_nodes.items()
        if projection.frame_key == repeat_step["name"]
    )
    assert frame_checkpoint.presentation_key == repeat_step["name"]
    assert bundle.projection.repeat_until_frame_key(loop_node_id) == repeat_step["name"]
    assert frame_checkpoint.step_id.startswith("root.")


def test_review_loop_imported_stdlib_route_resumes_after_revise_checkpoint(tmp_path: Path) -> None:
    fixture = tmp_path / "phase_stdlib_review_loop.orc"
    fixture.write_text(
        (LISP_FIXTURES / "phase_stdlib_review_loop.orc").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for relpath in (
        "prompts/implementation/review.md",
        "prompts/implementation/fix.md",
        "artifacts/work/seed_execution_report.md",
        "artifacts/work/design_review_prompt.md",
        "artifacts/work/fix_plan_prompt.md",
        "artifacts/work/placeholder.txt",
        "artifacts/work/loop-placeholder.txt",
        "artifacts/review/placeholder.txt",
        "artifacts/review/loop-placeholder.txt",
    ):
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("seed\n", encoding="utf-8")

    result = compile_stage3_module(
        fixture,
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
    bundle = result.validated_bundles["phase_stdlib_review_loop::review-revise-loop-demo"]
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "phase_stdlib_review_loop::review-revise-loop-demo"
    )
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    loop_node_id = next(
        node_id
        for node_id, projection in bundle.projection.repeat_until_nodes.items()
        if projection.frame_key == repeat_step["name"]
    )
    frame_key = bundle.projection.repeat_until_frame_key(loop_node_id)

    run_id = "phase-stdlib-review-loop-resume"
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize(
        fixture.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "completed__execution_report_path": "artifacts/work/seed_execution_report.md",
            "inputs__design_review_prompt": "artifacts/work/design_review_prompt.md",
            "inputs__fix_plan_prompt": "artifacts/work/fix_plan_prompt.md",
        },
    )

    control = {"resume_mode": False, "review_calls": 0}

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _bundle_path_from_prompt(prompt: str) -> Path:
        match = re.search(r"(?m)^-?\s*path: (.+)$", prompt)
        assert match is not None, prompt
        return tmp_path / match.group(1).strip()

    def _write_bundle(bundle_path: Path, payload: dict[str, object]) -> None:
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _touch(relpath: str) -> None:
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("artifact\n", encoding="utf-8")

    def _write_findings(relpath: str) -> str:
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"items": []}, indent=2) + "\n", encoding="utf-8")
        return relpath

    def _success():
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

    def _failure(message: str):
        return SimpleNamespace(
            exit_code=1,
            stdout=b"",
            stderr=message.encode("utf-8"),
            duration_ms=1,
            error={"type": "execution_error", "message": message},
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    def _execute(_self, invocation, **_kwargs):
        prompt = getattr(invocation, "prompt", "")
        bundle_path = _bundle_path_from_prompt(prompt)
        if "## Variant Output Contract" not in prompt:
            _touch("artifacts/work/execution_report_revised.md")
            _write_bundle(
                bundle_path,
                {"execution_report_path": "artifacts/work/execution_report_revised.md"},
            )
            return _success()

        control["review_calls"] += 1
        if control["review_calls"] == 1:
            _touch("artifacts/review/review_round_1.md")
            _write_bundle(
                bundle_path,
                {
                    "variant": "REVISE",
                    "review_report": "artifacts/review/review_round_1.md",
                    "revise_review_report": "artifacts/review/review_round_1.md",
                    "findings": {
                        "schema_version": "ReviewFindings.v1",
                        "items_path": _write_findings("artifacts/work/review_round_1_findings.json"),
                    },
                },
            )
            return _success()
        if not control["resume_mode"]:
            return _failure("forced review interruption")
        _touch("artifacts/work/checks_report.md")
        _touch("artifacts/review/review_round_2.md")
        _write_bundle(
            bundle_path,
            {
                "variant": "APPROVE",
                "checks_report": "artifacts/work/checks_report.md",
                "review_report": "artifacts/review/review_round_2.md",
                "review_decision": "APPROVE",
                "findings": {
                    "schema_version": "ReviewFindings.v1",
                    "items_path": _write_findings("artifacts/work/review_round_2_findings.json"),
                },
            },
        )
        return _success()

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        first_run = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="stop")
        assert first_run["status"] == "failed"
        frame_result = first_run["steps"][repeat_step["name"]]
        assert frame_result["error"]["message"] == "repeat_until body step failed"
        assert frame_result["error"]["context"]["iteration"] == 1

        persisted = json.loads(
            (tmp_path / ".orchestrate" / "runs" / run_id / "state.json").read_text(encoding="utf-8")
        )
        assert persisted.get("error") is None
        assert persisted["repeat_until"][frame_key]["current_iteration"] == 1
        assert persisted["repeat_until"][frame_key]["completed_iterations"] == [0]
        assert frame_key in persisted["steps"]

        control["resume_mode"] = True
        resumed_state = WorkflowExecutor(
            bundle,
            tmp_path,
            StateManager(workspace=tmp_path, run_id=run_id),
            retry_delay_ms=0,
        ).execute(run_id=run_id, resume=True)

    assert resumed_state["status"] == "completed"
    assert resumed_state["repeat_until"][frame_key]["completed_iterations"] == [0, 1]
    assert frame_key in resumed_state["steps"]
