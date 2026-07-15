from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import ctypes
from datetime import datetime
import errno
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
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
TRACKED_PLAN_PILOT_CURRENT_LIVE_SELECTOR = (
    "test_tracked_plan_phase_authorized_interrupted_run_recovery"
)
TRACKED_PLAN_PILOT_CLEAN_EVIDENCE = TRACKED_PLAN_PILOT_EVIDENCE / "evidence" / "clean_run.json"
TRACKED_PLAN_PILOT_RESUME_EVIDENCE = (
    TRACKED_PLAN_PILOT_EVIDENCE / "evidence" / "interruption_resume.json"
)
TRACKED_PLAN_PILOT_PRE_EDIT_SCAN = TRACKED_PLAN_PILOT_EVIDENCE / "pre_edit_known_store_scans.json"
TRACKED_PLAN_PILOT_EVIDENCE_INDEX = TRACKED_PLAN_PILOT_EVIDENCE / "evidence_index.json"
TRACKED_PLAN_PILOT_PRE_EDIT_SCAN_SHA256 = (
    "sha256:422e465bc1391fd2ea186490f39c59ff677f9cd9b1c502ba70f684d38b54f155"
)
TRACKED_PLAN_PILOT_FIRST_RECOVERY_AUTHORIZATION = (
    TRACKED_PLAN_PILOT_EVIDENCE
    / "attestations"
    / "task-3"
    / "interrupted-run-recovery-authorization.json"
)
TRACKED_PLAN_PILOT_FIRST_RECOVERY_AUTHORIZATION_SHA256 = (
    "sha256:bb0f3bb01ec3ef74b91186a9f227c0b6f41285549cdf176f827a7e8665a5fc0e"
)
TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION = (
    TRACKED_PLAN_PILOT_EVIDENCE
    / "attestations"
    / "task-3"
    / "fresh-child-resume-recovery-authorization.json"
)
TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION = (
    TRACKED_PLAN_PILOT_EVIDENCE
    / "attestations"
    / "task-3"
    / "artifact-parity-evidence-correction-authorization.json"
)
TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION_SHA256 = (
    "sha256:5dcec17ccd0ebef24f8b0025501df2acf8ac90517227a6161e9e32d26aa1963d"
)
TRACKED_PLAN_PILOT_GOVERNING_PRE_AMENDMENT_PLAN_SHA256 = (
    "sha256:cbbc25e296424da5c14c75f99a2b60880a43e79ea5a4ad891898e4bd1ee79737"
)
TRACKED_PLAN_PILOT_CLEAN_STATE_SHA256 = (
    "sha256:729ebd7b4670ee73b0f18fbd3566e2ea73e5e8f488ddf729212cbec77e34a73b"
)
TRACKED_PLAN_PILOT_CLEAN_TREE_SHA256 = (
    "sha256:1f71d1f87d5a00bc3210c9aa6ca868d052e213a64998749cbdc6e3d8bf81fd7d"
)
TRACKED_PLAN_PILOT_PRIOR_RECOVERY_INCIDENT = (
    TRACKED_PLAN_PILOT_EVIDENCE
    / "incidents"
    / "task-3-default-resume-not-restorable.json"
)
TRACKED_PLAN_PILOT_PRIOR_RECOVERY_INCIDENT_SHA256 = (
    "sha256:95c55a537da047b216bcf274456c400aa59590cfeb9020c2e36cff0d9bbf112f"
)
TRACKED_PLAN_PILOT_RECOVERY_INCIDENT = (
    TRACKED_PLAN_PILOT_EVIDENCE
    / "incidents"
    / "task-3-fresh-child-inherited-parent-resume.json"
)
TRACKED_PLAN_PILOT_RECOVERY_INCIDENT_SHA256 = (
    "sha256:ec5f762f0787568429cce130d20bae7653764e432bb42cc4df4a23f24734f806"
)
TRACKED_PLAN_PILOT_RECOVERY_COMMIT = "1cba48c8117370c89827fe19ecf73347725e95e2"
TRACKED_PLAN_PILOT_RECOVERY_COMMIT_TREE = "e2e44c23716d9b94d01ae0ca256b5a248778050e"
TRACKED_PLAN_PILOT_RECOVERY_PRIMARY_REVIEW_SHA256 = (
    "sha256:fd11c2f4f4c6765dc743b472811e2223f7a046e96ebddfe1a1c4081ce2b768f1"
)
TRACKED_PLAN_PILOT_RECOVERY_SECONDARY_REVIEW_SHA256 = (
    "sha256:9be776aa9ef0362aa581cd2ffdc4aabc7cc0a34211163e62537081acfa586f39"
)
_TRACKED_PLAN_PILOT_PENDING_HARNESS_BINDING = MappingProxyType(
    {
        "commit": "PENDING_POST_REVIEW_HARNESS_COMMIT",
        "commit_tree": "PENDING_POST_REVIEW_HARNESS_COMMIT_TREE",
        "primary_review_complete_candidate_sha256": "PENDING_PRIMARY_REVIEW_BINDING",
        "secondary_review_complete_candidate_sha256": "PENDING_SECONDARY_REVIEW_BINDING",
    }
)
_TRACKED_PLAN_PILOT_TEST_HARNESS_BINDING = MappingProxyType(
    {
        "commit": "1" * 40,
        "commit_tree": "2" * 40,
        "primary_review_complete_candidate_sha256": "sha256:" + "3" * 64,
        "secondary_review_complete_candidate_sha256": "sha256:" + "4" * 64,
    }
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

_TRACKED_PLAN_PILOT_COMMON_RETAINED_PROJECTION_KEYS = frozenset(
    {
        "evidence_status",
        "run_id",
        "run_root",
        "workflow_name",
        "workflow_outputs",
        "source",
        "run",
        "fresh_child_resume_recovery_authorization",
        "artifact_evidence_correction_authorization",
        "historical_clean_artifact_bytes_retained",
        "historical_clean_artifact_equality",
        "checkpoint_ids",
        "presentation_keys",
        "registered_workflows",
        "identity_comparison",
    }
)
_TRACKED_PLAN_PILOT_CLEAN_RETAINED_PROJECTION_KEYS = (
    _TRACKED_PLAN_PILOT_COMMON_RETAINED_PROJECTION_KEYS
    | frozenset({"schema", "status", "provider_roles", "artifact_contract"})
)
_TRACKED_PLAN_PILOT_INTERRUPTION_RETAINED_PROJECTION_KEYS = (
    _TRACKED_PLAN_PILOT_COMMON_RETAINED_PROJECTION_KEYS
    | frozenset(
        {
            "schema",
            "interruption",
            "resume",
            "comparison",
            "artifacts",
            "artifact_hash_provenance",
        }
    )
)
_TRACKED_PLAN_PILOT_RESUME_EVIDENCE_KEYS = frozenset(
    {
        "status",
        "reused_provider_roles",
        "executed_provider_roles",
        "provider_role_attempts",
    }
)


def _load_json(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json_with_sha256(path: Path) -> tuple[dict[str, object], str]:
    content = path.read_bytes()
    return (
        json.loads(content),
        f"sha256:{hashlib.sha256(content).hexdigest()}",
    )


def _tracked_plan_phase_live_recovery_enabled() -> bool:
    return os.environ.get(TRACKED_PLAN_PILOT_LIVE_ENV) == "1"


def _tracked_plan_phase_current_live_selector(function):
    function._tracked_plan_phase_current_live_selector = True
    return function


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


def _tracked_plan_phase_publication_destination_observation(
    *,
    targets: tuple[Path, Path] = (
        TRACKED_PLAN_PILOT_CLEAN_EVIDENCE,
        TRACKED_PLAN_PILOT_RESUME_EVIDENCE,
    ),
) -> dict[str, object]:
    final_directory = targets[0].parent
    publication_parent = final_directory.parent
    return {
        "targets": [
            {
                "path": target.as_posix(),
                "direct_child_name": target.name,
                "is_direct_child": (
                    target.parent == final_directory
                    and target == final_directory / target.name
                ),
            }
            for target in targets
        ],
        "final_directory": {
            "path": final_directory.as_posix(),
            "exists": final_directory.exists(),
            "is_symlink": final_directory.is_symlink(),
        },
        "publication_parent": {
            "path": publication_parent.as_posix(),
            "exists": publication_parent.exists(),
            "is_directory": publication_parent.is_dir(),
            "is_symlink": publication_parent.is_symlink(),
        },
    }


def _tracked_plan_phase_expected_publication_destination() -> dict[str, object]:
    final_directory = TRACKED_PLAN_PILOT_CLEAN_EVIDENCE.parent
    publication_parent = final_directory.parent
    return {
        "targets": [
            {
                "path": TRACKED_PLAN_PILOT_CLEAN_EVIDENCE.as_posix(),
                "direct_child_name": TRACKED_PLAN_PILOT_CLEAN_EVIDENCE.name,
                "is_direct_child": True,
            },
            {
                "path": TRACKED_PLAN_PILOT_RESUME_EVIDENCE.as_posix(),
                "direct_child_name": TRACKED_PLAN_PILOT_RESUME_EVIDENCE.name,
                "is_direct_child": True,
            },
        ],
        "final_directory": {
            "path": final_directory.as_posix(),
            "exists": False,
            "is_symlink": False,
        },
        "publication_parent": {
            "path": publication_parent.as_posix(),
            "exists": True,
            "is_directory": True,
            "is_symlink": False,
        },
    }


def _tracked_plan_phase_correction_authorization_fixture() -> dict[str, object]:
    timestamp = "2026-07-15T09:06:59-07:00"
    owner = {"name": "Ollie", "email": "ohoidn@stanford.edu"}
    return {
        "record_type": (
            "procedure_first_pilot_task3_artifact_parity_evidence_correction_authorization"
        ),
        "version": 1,
        "evidence_status": "owner_confirmed",
        "authorized_disposition": (
            "replace_unprovable_historical_clean_artifact_equality_with_"
            "deterministic_provider_contract_conformance"
        ),
        "owner": owner,
        "bindings": {
            "governing_plan": {
                "path": "docs/plans/2026-07-13-procedure-first-pilot-plan.md",
                "sha256": TRACKED_PLAN_PILOT_GOVERNING_PRE_AMENDMENT_PLAN_SHA256,
            },
            "recovery_authorization": {
                "path": TRACKED_PLAN_PILOT_FIRST_RECOVERY_AUTHORIZATION.relative_to(
                    REPO_ROOT
                ).as_posix(),
                "sha256": TRACKED_PLAN_PILOT_FIRST_RECOVERY_AUTHORIZATION_SHA256,
            },
            "clean_run": {
                "run_id": TRACKED_PLAN_PILOT_RUN_IDS[0],
                "state_sha256": TRACKED_PLAN_PILOT_CLEAN_STATE_SHA256,
                "tree_sha256": TRACKED_PLAN_PILOT_CLEAN_TREE_SHA256,
            },
        },
        "owner_confirmations": {
            "confirmed_at": timestamp,
            "statements": [
                "Historical clean-run artifact bytes or content digests were not retained.",
                (
                    "Historical clean artifact equality must be recorded as not_asserted, "
                    "never inferred."
                ),
                (
                    "Task 3 may instead require recovered bytes to match the content-addressed "
                    "deterministic provider fixture contract, with the clean checkpoints "
                    "binding all six provider roles, bundles, and artifact paths."
                ),
                (
                    "This does not weaken clean-run tree/state immutability, the exact two-run "
                    "restriction, same-ID recovery, legacy-root hold, or fail-closed resume "
                    "validation."
                ),
                "It authorizes no additional run, recreation, or resume.",
                "It does not attest Task 3, retirement validation, or pilot completion.",
            ],
        },
        "prepared_by": (
            "Claude Code session agent (Opus 4.8) — owner-directed verification and "
            "mechanical write"
        ),
        "prepared_at": timestamp,
        "owner_adoption": {
            "owner": owner,
            "adopted_at": timestamp,
            "provenance_statement": (
                "This record corrects an artifact-parity evidence standard, which is a "
                "substantive design judgment; unlike the mechanically-scoped recovery "
                "authorization, the owner Ollie personally made this decision. He was shown, "
                "in his interactive session, the exact tradeoff — that the deterministic "
                "content-addressed provider fixture contract proves recovered artifacts "
                "conform to the six digest-bound provider roles, bundles, and paths retained "
                "in the clean checkpoints, while byte-identity with the specific historical "
                "clean run cannot be proven because those artifact bytes were never retained "
                "and is therefore recorded not_asserted rather than inferred — and he "
                "explicitly chose to accept contract-conformance as the Task 3 artifact-parity "
                "standard. He directed his Claude Code session agent to record and adopt this "
                "authorization on that basis. The session agent independently re-verified the "
                "governing-plan, recovery-authorization, and clean-run state bindings against "
                "the on-disk files immediately before writing (the clean tree hash is as bound "
                "by the audited harness); the mechanical write was performed by that session "
                "agent at the owner's direction."
            ),
        },
        "claims_not_made": [
            (
                "This authorization changes only the Task 3 artifact-parity evidence form; it "
                "does not weaken clean-run immutability, the exact two-run restriction, same-ID "
                "recovery, the legacy-root hold, or fail-closed resume validation."
            ),
            (
                "It authorizes no additional run, recreation, resume, or any other run-root "
                "mutation."
            ),
            (
                "It does not attest that Task 3, retirement validation, or the broader pilot "
                "is complete."
            ),
            (
                "It does not assert historical clean-run artifact byte-equality; that is "
                "recorded not_asserted and must never be inferred from contract conformance."
            ),
        ],
    }


def _validate_tracked_plan_phase_correction_authorization(
    authorization: dict[str, object],
    authorization_sha256: str,
) -> None:
    expected = _tracked_plan_phase_correction_authorization_fixture()
    assert authorization_sha256 == TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION_SHA256, (
        "artifact evidence correction authorization SHA256 is not the exact adopted record"
    )
    assert authorization.get("record_type") == expected["record_type"], (
        "artifact evidence correction authorization record type is invalid"
    )
    assert authorization.get("version") == expected["version"]
    assert authorization.get("evidence_status") == expected["evidence_status"], (
        "artifact evidence correction authorization is not owner-confirmed"
    )
    assert authorization.get("authorized_disposition") == expected[
        "authorized_disposition"
    ], "artifact evidence correction disposition is invalid"
    assert authorization.get("owner") == expected["owner"], (
        "artifact evidence correction owner is invalid"
    )
    assert authorization.get("bindings") == expected["bindings"], (
        "artifact evidence correction digest bindings are invalid"
    )
    assert authorization.get("owner_confirmations") == expected["owner_confirmations"], (
        "artifact evidence correction statements or confirmation timestamp are stale"
    )
    assert authorization.get("prepared_by") == expected["prepared_by"], (
        "artifact evidence correction preparer is invalid"
    )
    assert authorization.get("prepared_at") == expected["prepared_at"], (
        "artifact evidence correction preparation timestamp is stale"
    )
    assert authorization.get("owner_adoption") == expected["owner_adoption"], (
        "artifact evidence correction personal-owner adoption or provenance is stale"
    )
    assert authorization.get("claims_not_made") == expected["claims_not_made"], (
        "artifact evidence correction claim boundaries are stale"
    )
    assert authorization == expected, (
        "artifact evidence correction authorization contains unexpected fields"
    )


def _tracked_plan_phase_correction_authorization_binding() -> dict[str, str]:
    return {
        "path": TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION.relative_to(
            REPO_ROOT
        ).as_posix(),
        "sha256": TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION_SHA256,
    }


def _tracked_plan_phase_recovery_authorization_binding(
    authorization_sha256: str,
) -> dict[str, str]:
    assert _is_sha256(authorization_sha256), "recovery authorization SHA256 is invalid"
    return {
        "path": TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION.relative_to(
            REPO_ROOT
        ).as_posix(),
        "sha256": authorization_sha256,
    }


def _validate_tracked_plan_phase_recovery_authorization_semantics(
    authorization: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    assert authorization.get("record_type") == (
        "procedure_first_pilot_task3_fresh_child_resume_recovery_authorization"
    )
    assert authorization.get("version") == 1
    assert authorization.get("evidence_status") == "owner_confirmed", (
        "recovery authorization is not owner-confirmed"
    )
    assert authorization.get("authorized_disposition") == (
        "replace_failed_interrupted_run_same_id_once_after_fresh_child_fix"
    ), "recovery authorization disposition is invalid"
    expected_owner = {"name": "Ollie", "email": "ohoidn@stanford.edu"}
    assert authorization.get("owner") == expected_owner
    assert set(authorization) == {
        "record_type",
        "version",
        "evidence_status",
        "authorized_disposition",
        "owner",
        "bindings",
        "authorization_scope",
        "owner_confirmations",
        "template_prepared_by",
        "prepared_by",
        "prepared_at",
        "owner_adoption",
        "claims_not_made",
    }, "recovery authorization contains unexpected fields"
    bindings = authorization.get("bindings")
    assert isinstance(bindings, dict)
    harness = bindings.get("second_recovery_harness")
    assert isinstance(harness, dict) and set(harness) == {
        "commit",
        "commit_tree",
        "primary_review_complete_candidate_sha256",
        "secondary_review_complete_candidate_sha256",
    }, "second recovery harness binding schema is invalid"
    assert isinstance(harness.get("commit"), str) and re.fullmatch(
        r"[0-9a-f]{40}", harness["commit"]
    ), "second recovery harness commit binding is invalid"
    assert isinstance(harness.get("commit_tree"), str) and re.fullmatch(
        r"[0-9a-f]{40}", harness["commit_tree"]
    ), "second recovery harness tree binding is invalid"
    assert _is_sha256(harness.get("primary_review_complete_candidate_sha256")), (
        "second recovery harness primary review binding is invalid"
    )
    assert _is_sha256(harness.get("secondary_review_complete_candidate_sha256")), (
        "second recovery harness secondary review binding is invalid"
    )
    assert bindings == _tracked_plan_phase_recovery_bindings_fixture(
        second_recovery_harness=harness
    ), "recovery authorization bindings are invalid"
    expected_fixture = _tracked_plan_phase_owner_confirmed_recovery_authorization_fixture(
        second_recovery_harness=harness
    )
    assert authorization.get("authorization_scope") == expected_fixture[
        "authorization_scope"
    ], "recovery authorization scope is invalid"
    confirmations = authorization.get("owner_confirmations")
    assert isinstance(confirmations, dict) and set(confirmations) == {
        "confirmed_at",
        "statements",
    }, "owner confirmation schema is invalid"
    assert confirmations.get("statements") == (
        _tracked_plan_phase_recovery_owner_statements_fixture()
    ), "owner confirmation statements are stale"
    _assert_tracked_plan_phase_genuine_authorization_timestamp(
        confirmations.get("confirmed_at"), "owner confirmation"
    )
    assert authorization.get("template_prepared_by") == (
        "Codex /root — non-owner template preparation only"
    )
    prepared_by = authorization.get("prepared_by")
    assert isinstance(prepared_by, str) and prepared_by.strip(), (
        "recovery authorization mechanical writer is missing"
    )
    _assert_tracked_plan_phase_genuine_authorization_timestamp(
        authorization.get("prepared_at"), "preparation"
    )
    owner_adoption = authorization.get("owner_adoption")
    assert isinstance(owner_adoption, dict) and set(owner_adoption) == {
        "owner",
        "adopted_at",
        "provenance_statement",
    }, "owner adoption schema is invalid"
    assert owner_adoption.get("owner") == expected_owner
    _assert_tracked_plan_phase_genuine_authorization_timestamp(
        owner_adoption.get("adopted_at"), "owner adoption"
    )
    provenance = owner_adoption.get("provenance_statement")
    assert isinstance(provenance, str) and len(provenance.strip()) >= 80, (
        "owner adoption provenance is missing or incomplete"
    )
    assert authorization.get("claims_not_made") == expected_fixture["claims_not_made"], (
        "recovery authorization claim boundaries are stale"
    )
    fix = bindings["generic_fresh_child_resume_fix"]
    assert fix["commit"] == TRACKED_PLAN_PILOT_RECOVERY_COMMIT
    assert fix["commit_tree"] == TRACKED_PLAN_PILOT_RECOVERY_COMMIT_TREE
    assert fix["primary_review_complete_candidate_sha256"] == (
        TRACKED_PLAN_PILOT_RECOVERY_PRIMARY_REVIEW_SHA256
    )
    assert fix["secondary_review_complete_candidate_sha256"] == (
        TRACKED_PLAN_PILOT_RECOVERY_SECONDARY_REVIEW_SHA256
    )
    return bindings, harness


def _validate_tracked_plan_phase_recovery_authorization_lifecycle(
    authorization: dict[str, object],
) -> str:
    evidence_status = authorization.get("evidence_status")
    if evidence_status == "owner_confirmed":
        _validate_tracked_plan_phase_recovery_authorization_semantics(authorization)
        return "owner_confirmed"

    assert evidence_status == "pending_owner_confirmation", (
        "recovery authorization lifecycle status is invalid"
    )
    expected_pending_keys = {
        "record_type",
        "version",
        "evidence_status",
        "authorized_disposition",
        "intended_owner",
        "bindings",
        "authorization_scope",
        "owner_action_required",
        "template_prepared_by",
        "claims_not_made",
    }
    assert set(authorization) == expected_pending_keys, (
        "pending recovery authorization contains unexpected fields"
    )
    bindings = authorization.get("bindings")
    assert isinstance(bindings, dict)
    harness = bindings.get("second_recovery_harness")
    expected_harness_keys = {
        "commit",
        "commit_tree",
        "primary_review_complete_candidate_sha256",
        "secondary_review_complete_candidate_sha256",
    }
    assert isinstance(harness, dict) and set(harness) == expected_harness_keys, (
        "pending second recovery harness binding schema is invalid"
    )
    is_unbound = harness == dict(_TRACKED_PLAN_PILOT_PENDING_HARNESS_BINDING)
    is_bound = bool(
        isinstance(harness.get("commit"), str)
        and re.fullmatch(r"[0-9a-f]{40}", harness["commit"])
        and isinstance(harness.get("commit_tree"), str)
        and re.fullmatch(r"[0-9a-f]{40}", harness["commit_tree"])
        and _is_sha256(harness.get("primary_review_complete_candidate_sha256"))
        and _is_sha256(harness.get("secondary_review_complete_candidate_sha256"))
    )
    assert is_unbound or is_bound, (
        "pending second recovery harness must be a complete placeholder or populated set"
    )
    expected = _tracked_plan_phase_pending_recovery_authorization_fixture(
        second_recovery_harness=harness
    )
    assert authorization == expected, (
        "pending recovery authorization differs from its exact lifecycle schema"
    )
    return "unbound_pending" if is_unbound else "bound_pending"


def _validate_tracked_plan_phase_recovery_preflight_contract(
    *,
    authorization: dict[str, object],
    authorization_sha256: str,
    correction_authorization: dict[str, object],
    correction_authorization_sha256: str,
    incident: dict[str, object],
    incident_sha256: str,
    observed_head_commit: str,
    observed_head_tree: str,
    observed_legacy_root: dict[str, object],
    observed_dedicated_root: dict[str, object],
    observed_run_ids: tuple[str, ...],
    observed_clean_run: dict[str, object],
    observed_failed_run: dict[str, object],
    observed_publication_destination: dict[str, object],
    retained_evidence_targets_present: tuple[str, ...],
    scratch_paths: tuple[str, ...],
    expected_legacy_scan: dict[str, object],
    observed_legacy_scan: dict[str, object],
    expected_dedicated_scan: dict[str, object],
    observed_dedicated_scan: dict[str, object],
) -> None:
    _validate_tracked_plan_phase_correction_authorization(
        correction_authorization,
        correction_authorization_sha256,
    )
    assert _is_sha256(authorization_sha256), "recovery authorization SHA256 is invalid"
    assert incident_sha256 == TRACKED_PLAN_PILOT_RECOVERY_INCIDENT_SHA256, (
        "recovery incident SHA256 is not the exact bound record"
    )
    bindings, harness = _validate_tracked_plan_phase_recovery_authorization_semantics(
        authorization
    )
    assert observed_head_commit == harness["commit"], (
        "observed recovery harness commit differs from authorization"
    )
    assert observed_head_tree == harness["commit_tree"], (
        "observed recovery harness tree differs from authorization"
    )

    expected_legacy_root = bindings.get("legacy_root")
    expected_dedicated_root = bindings.get("dedicated_root")
    assert observed_legacy_root == expected_legacy_root, "legacy root binding mismatch"
    assert observed_dedicated_root == expected_dedicated_root, "dedicated root binding mismatch"
    assert observed_run_ids == TRACKED_PLAN_PILOT_RUN_IDS, (
        "dedicated root does not contain the exact two run IDs"
    )
    assert isinstance(expected_dedicated_root, dict)
    assert tuple(expected_dedicated_root.get("top_level_run_ids", ())) == (
        TRACKED_PLAN_PILOT_RUN_IDS
    )

    assert observed_clean_run == bindings.get("clean_run"), "clean run binding mismatch"
    assert observed_failed_run == bindings.get("failed_interrupted_run"), (
        "failed interrupted run binding mismatch"
    )
    assert incident.get("incident_type") == "fresh_child_inherited_parent_resume_mode", (
        "recovery incident content is invalid"
    )
    assert incident.get("owner_acceptance") == "not_asserted", (
        "recovery incident owner boundary is invalid"
    )
    assert incident.get("execution", {}).get("live_recovery_authorization_consumed") is True, (
        "recovery incident does not record consumed first authorization"
    )
    assert incident.get("recovery_boundary", {}).get("prior_authorization_status") == (
        "consumed"
    )
    assert incident.get("recovery_boundary", {}).get("current_run_mutation_authorization") == (
        "none"
    )
    assert incident.get("post_failure_state", {}).get("protected_clean_run") == {
        **bindings["clean_run"],
        "preserved_byte_for_byte": True,
    }
    assert incident.get("post_failure_state", {}).get("failed_interrupted_run") == (
        bindings["failed_interrupted_run"]
    )
    assert observed_publication_destination == (
        _tracked_plan_phase_expected_publication_destination()
    ), "publication destination is not the exact safe atomic-publication layout"
    assert not retained_evidence_targets_present, (
        "retained evidence targets must be absent before recovery"
    )
    assert not scratch_paths, "top-level recovery scratch paths must be absent"
    assert _tracked_plan_pilot_scan_facts(observed_legacy_scan) == (
        _tracked_plan_pilot_scan_facts(expected_legacy_scan)
    ), "legacy scan differs from the bound pre-edit scan"
    assert observed_dedicated_scan.get("query_version") == expected_dedicated_scan.get(
        "query_version"
    )
    assert observed_dedicated_scan.get("retired_identities") == expected_dedicated_scan.get(
        "retired_identities"
    )
    assert observed_dedicated_scan.get("root") == TRACKED_PLAN_PILOT_RUN_ROOT.as_posix()
    assert observed_dedicated_scan.get("matches") in ((), []), (
        "dedicated root contains a queried old identity"
    )
    for key in ("terminal_run_count", "nonterminal_run_count", "call_frame_count", "consumer_count"):
        assert observed_dedicated_scan.get(key) == 0, (
            f"dedicated queried old identity {key} must be zero"
        )


def _validate_tracked_plan_phase_recovery_preflight(**arguments: object) -> None:
    actual_authorization, actual_authorization_sha256 = _load_json_with_sha256(
        TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION
    )
    assert arguments.get("authorization") == actual_authorization, (
        "preflight authorization is not the actual on-disk recovery authorization"
    )
    assert arguments.get("authorization_sha256") == actual_authorization_sha256, (
        "preflight digest is not the actual on-disk recovery authorization SHA256"
    )
    _validate_tracked_plan_phase_recovery_preflight_contract(**arguments)


def _assert_tracked_plan_phase_genuine_authorization_timestamp(
    value: object,
    label: str,
) -> None:
    assert isinstance(value, str) and value, f"{label} timestamp is missing"
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, f"{label} timestamp must include a UTC offset"


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


_TRACKED_PLAN_PILOT_PROVIDER_FIXTURE_CONTRACT = MappingProxyType(
    {
        "design.draft": MappingProxyType(
            {
                "artifacts": (("docs/plans/runtime-design.md", b"# Runtime Design\n"),),
                "bundle": MappingProxyType(
                    {"design_path": "docs/plans/runtime-design.md"}
                ),
            }
        ),
        "design.review": MappingProxyType(
            {
                "artifacts": (
                    ("artifacts/review/runtime-design-review.md", b"APPROVE\n"),
                ),
                "bundle": MappingProxyType(
                    {
                        "variant": "APPROVE",
                        "design_review_report_path": (
                            "artifacts/review/runtime-design-review.md"
                        ),
                        "design_review_decision": "APPROVE",
                    }
                ),
            }
        ),
        "plan.draft": MappingProxyType(
            {
                "artifacts": (("docs/plans/runtime-plan.md", b"# Runtime Plan\n"),),
                "bundle": MappingProxyType({"plan_path": "docs/plans/runtime-plan.md"}),
            }
        ),
        "plan.review": MappingProxyType(
            {
                "artifacts": (
                    ("artifacts/review/runtime-plan-review.md", b"APPROVE\n"),
                ),
                "bundle": MappingProxyType(
                    {
                        "variant": "APPROVE",
                        "plan_review_report_path": "artifacts/review/runtime-plan-review.md",
                        "plan_review_decision": "APPROVE",
                    }
                ),
            }
        ),
        "implementation.execute": MappingProxyType(
            {
                "artifacts": (
                    (
                        "artifacts/work/runtime-execution-report.md",
                        b"# Runtime Execution Report\n",
                    ),
                ),
                "bundle": MappingProxyType(
                    {
                        "execution_report_path": (
                            "artifacts/work/runtime-execution-report.md"
                        )
                    }
                ),
            }
        ),
        "implementation.review": MappingProxyType(
            {
                "artifacts": (
                    (
                        "artifacts/review/runtime-implementation-review.md",
                        b"APPROVE\n",
                    ),
                ),
                "bundle": MappingProxyType(
                    {
                        "variant": "APPROVE",
                        "implementation_review_report_path": (
                            "artifacts/review/runtime-implementation-review.md"
                        ),
                        "implementation_review_decision": "APPROVE",
                    }
                ),
            }
        ),
    }
)

_TRACKED_PLAN_PILOT_DESIGN_PROVIDER_BUNDLE_ROOT = (
    ".orchestrate/workflow_lisp/calls/"
    "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack/"
    "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack__"
    "design__call_examples/design_plan_impl_review_stack_v2_call::tracked-design-phase/"
    "examples/design_plan_impl_review_stack_v2_call::tracked-design-phase/"
)
_TRACKED_PLAN_PILOT_IMPLEMENTATION_PROVIDER_BUNDLE_ROOT = (
    ".orchestrate/workflow_lisp/calls/"
    "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack/"
    "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack__"
    "implementation__call_examples/design_plan_impl_review_stack_v2_call::"
    "design-plan-impl-implementation-phase/"
    "examples/design_plan_impl_review_stack_v2_call::"
    "design-plan-impl-implementation-phase/"
)
_TRACKED_PLAN_PILOT_PLAN_PROVIDER_BUNDLE_ROOT = (
    ".orchestrate/workflow_lisp/entry/tracked-plan-phase-clean-new-id/"
    "examples_design_plan_impl_review_stack_v2_call_design-plan-impl-review-stack/"
)
_TRACKED_PLAN_PILOT_CLEAN_PROVIDER_REFERENCES = MappingProxyType(
    {
        "design.draft": MappingProxyType(
            {
                "checkpoint_id": "ckpt:43abce9c43d12b57bd2d2266",
                "record_id": "record:640df3428c65ddc079f3f8eb",
                "bundle_path": (
                    _TRACKED_PLAN_PILOT_DESIGN_PROVIDER_BUNDLE_ROOT
                    + "__write_root__examples_design_plan_impl_review_stack_v2_call_"
                    "tracked_design_phase__draft__result_bundle.json"
                ),
            }
        ),
        "design.review": MappingProxyType(
            {
                "checkpoint_id": "ckpt:3de90f0bfcb727ca8962ed7b",
                "record_id": "record:2e608f51024cf7c8be67ff1a",
                "bundle_path": (
                    _TRACKED_PLAN_PILOT_DESIGN_PROVIDER_BUNDLE_ROOT
                    + "__write_root__examples_design_plan_impl_review_stack_v2_call_"
                    "tracked_design_phase__review__result_bundle.json"
                ),
            }
        ),
        "plan.draft": MappingProxyType(
            {
                "checkpoint_id": "ckpt:85bebe726bc9eed0e4ee7c63",
                "record_id": "record:2d4b5841fdad3c65377ea294",
                "bundle_path": (
                    _TRACKED_PLAN_PILOT_PLAN_PROVIDER_BUNDLE_ROOT
                    + "__write_root__examples_design_plan_impl_review_stack_v2_call_"
                    "design_plan_impl_review_stack__plan__example__757f470a2485287a.json"
                ),
            }
        ),
        "plan.review": MappingProxyType(
            {
                "checkpoint_id": "ckpt:da29481dd96843184de8136f",
                "record_id": "record:f05ec533e181a6634740afba",
                "bundle_path": (
                    _TRACKED_PLAN_PILOT_PLAN_PROVIDER_BUNDLE_ROOT
                    + "__write_root__examples_design_plan_impl_review_stack_v2_call_"
                    "design_plan_impl_review_stack__plan__example__fc00c8ae28da255e.json"
                ),
            }
        ),
        "implementation.execute": MappingProxyType(
            {
                "checkpoint_id": "ckpt:0e2af96f5ca6abedb4fa77a5",
                "record_id": "record:d41a3aa71d68ac870c5378af",
                "bundle_path": (
                    _TRACKED_PLAN_PILOT_IMPLEMENTATION_PROVIDER_BUNDLE_ROOT
                    + "__write_root__examples_design_plan_impl_review_stack_v2_call_"
                    "design_plan_impl_implementation_phase__attempt__result_bundle.json"
                ),
            }
        ),
        "implementation.review": MappingProxyType(
            {
                "checkpoint_id": "ckpt:0b7c450dcd18e4929565933c",
                "record_id": "record:a7ed6a1794617a47e47dd0cc",
                "bundle_path": (
                    _TRACKED_PLAN_PILOT_IMPLEMENTATION_PROVIDER_BUNDLE_ROOT
                    + "__write_root__examples_design_plan_impl_review_stack_v2_call_"
                    "design_plan_impl_implementation_phase__review__result_bundle.json"
                ),
            }
        ),
    }
)


def _tracked_plan_phase_projection_fixtures() -> tuple[dict[str, object], dict[str, object]]:
    roles = list(TRACKED_PLAN_PILOT_PROVIDER_ROLES)
    artifact_contract = _tracked_plan_phase_fixture_artifact_contract()
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
        "fresh_child_resume_recovery_authorization": (
            _tracked_plan_phase_recovery_authorization_binding(
                _sha256_path(TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION)
            )
        ),
        "artifact_evidence_correction_authorization": (
            _tracked_plan_phase_correction_authorization_binding()
        ),
        "historical_clean_artifact_bytes_retained": False,
        "historical_clean_artifact_equality": "not_asserted",
        "checkpoint_ids": list(TRACKED_PLAN_PILOT_NEW_CHECKPOINT_IDS),
        "presentation_keys": list(TRACKED_PLAN_PILOT_NEW_PRESENTATION_KEYS),
        "registered_workflows": list(TRACKED_PLAN_PILOT_REGISTERED_WORKFLOWS),
        "identity_comparison": identity_comparison,
    }
    clean = {
        "schema": "procedure_first_pilot_tracked_plan_clean_run.v1",
        **common,
        "fresh_child_resume_recovery_authorization": deepcopy(
            common["fresh_child_resume_recovery_authorization"]
        ),
        "run_id": TRACKED_PLAN_PILOT_RUN_IDS[0],
        "run": {
            "id": TRACKED_PLAN_PILOT_RUN_IDS[0],
            "relative_path": TRACKED_PLAN_PILOT_RUN_IDS[0],
            "tree_sha256": TRACKED_PLAN_PILOT_CLEAN_TREE_SHA256,
            "entry_count": 12,
        },
        "status": "completed",
        "provider_roles": roles,
        "artifact_contract": artifact_contract,
    }
    interruption = {
        "schema": "procedure_first_pilot_tracked_plan_interruption_resume.v1",
        **common,
        "fresh_child_resume_recovery_authorization": deepcopy(
            common["fresh_child_resume_recovery_authorization"]
        ),
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
            "recovered_artifacts_conform_to_deterministic_provider_contract": True,
            "historical_clean_artifact_equality": "not_asserted",
        },
        "artifacts": deepcopy(artifact_contract["artifacts"]),
        "artifact_hash_provenance": "observed_post_resume_workspace_files",
    }
    return clean, interruption


def _validate_tracked_plan_phase_retained_projection_contract(
    clean: dict[str, object],
    interruption: dict[str, object],
    *,
    expected_recovery_authorization_sha256: str | None = None,
) -> None:
    assert set(clean) == _TRACKED_PLAN_PILOT_CLEAN_RETAINED_PROJECTION_KEYS, (
        "clean retained projection top-level schema is invalid"
    )
    assert set(interruption) == (
        _TRACKED_PLAN_PILOT_INTERRUPTION_RETAINED_PROJECTION_KEYS
    ), "interruption retained projection top-level schema is invalid"

    def _reject_historical_equality_inference(value: object) -> None:
        if isinstance(value, dict):
            assert "artifacts_equal_to_clean" not in value, (
                "historical clean artifact equality must never be inferred"
            )
            for key, nested in value.items():
                if key != "historical_clean_artifact_equality":
                    normalized_key = key.lower()
                    assert not (
                        "historical_clean" in normalized_key
                        and (
                            "equal" in normalized_key
                            or "match" in normalized_key
                            or "same" in normalized_key
                        )
                    ), "historical clean artifact equality must never be inferred"
                if key == "historical_clean_artifact_equality":
                    assert nested == "not_asserted", (
                        "historical clean artifact equality must be not_asserted"
                    )
                _reject_historical_equality_inference(nested)
        elif isinstance(value, list):
            for nested in value:
                _reject_historical_equality_inference(nested)

    _reject_historical_equality_inference(clean)
    _reject_historical_equality_inference(interruption)
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
    expected_correction_binding = (
        _tracked_plan_phase_correction_authorization_binding()
    )
    if expected_recovery_authorization_sha256 is None:
        expected_recovery_authorization_sha256 = _sha256_path(
            TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION
        )
    assert clean.get("fresh_child_resume_recovery_authorization") == interruption.get(
        "fresh_child_resume_recovery_authorization"
    ), "retained projections must bind the same recovery authorization"
    for payload in (clean, interruption):
        recovery_binding = payload.get("fresh_child_resume_recovery_authorization")
        assert isinstance(recovery_binding, dict) and set(recovery_binding) == {
            "path",
            "sha256",
        }, "fresh-child resume recovery authorization binding is invalid"
        assert recovery_binding.get("path") == (
            TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION.relative_to(REPO_ROOT).as_posix()
        ), "fresh-child resume recovery authorization path is invalid"
        assert _is_sha256(recovery_binding.get("sha256")), (
            "fresh-child resume recovery authorization SHA256 is invalid"
        )
        assert recovery_binding.get("sha256") == (
            expected_recovery_authorization_sha256
        ), "retained projection does not bind the current recovery authorization"
        assert payload.get("artifact_evidence_correction_authorization") == (
            expected_correction_binding
        ), "artifact evidence correction authorization binding is missing or invalid"
        assert payload.get("historical_clean_artifact_bytes_retained") is False, (
            "historical clean artifact bytes must be recorded as not retained"
        )
        assert payload.get("historical_clean_artifact_equality") == "not_asserted", (
            "historical clean artifact equality must be not_asserted"
        )
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
        if run_id == TRACKED_PLAN_PILOT_RUN_IDS[0]:
            assert run["tree_sha256"] == TRACKED_PLAN_PILOT_CLEAN_TREE_SHA256, (
                "retained projection does not bind the authorized clean run tree"
            )
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
    assert set(resume_fact) == _TRACKED_PLAN_PILOT_RESUME_EVIDENCE_KEYS, (
        "resume evidence schema is invalid"
    )
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
    assert interruption.get("artifact_hash_provenance") == (
        "observed_post_resume_workspace_files"
    ), "resumed artifact hashes do not disclose observed-file provenance"
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
    artifact_contract = clean.get("artifact_contract")
    contract_artifacts = _validate_tracked_plan_phase_artifact_contract(
        artifact_contract
    )
    artifacts = interruption.get("artifacts")
    assert isinstance(artifacts, dict), "observed recovered artifact bindings are missing"
    assert set(artifacts) == set(expected_artifact_paths), "artifact role set is invalid"
    for role, expected_path in expected_artifact_paths.items():
        binding = artifacts[role]
        assert isinstance(binding, dict) and set(binding) == {"path", "sha256"}, (
            "artifact binding structure is invalid"
        )
        assert binding["path"] == expected_path, "artifact path binding is invalid"
        assert _is_sha256(binding["sha256"]), "artifact SHA256 binding is invalid"
    assert artifacts == contract_artifacts, (
        "recovered artifact bytes do not conform to the deterministic provider contract"
    )
    assert comparison.get("historical_clean_artifact_equality") == "not_asserted", (
        "comparison historical clean artifact equality must be not_asserted"
    )
    assert comparison.get("public_output_equal_to_clean") is True, (
        "comparison must retain truthful public-output equality"
    )
    assert comparison.get(
        "recovered_artifacts_conform_to_deterministic_provider_contract"
    ) is True, "comparison must require deterministic provider contract conformance"
    assert set(comparison) == {
        "public_output_equal_to_clean",
        "recovered_artifacts_conform_to_deterministic_provider_contract",
        "historical_clean_artifact_equality",
    }, "comparison structure is invalid"
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


def _validate_tracked_plan_phase_retained_projections(
    clean: dict[str, object],
    interruption: dict[str, object],
) -> None:
    actual_authorization, actual_authorization_sha256 = _load_json_with_sha256(
        TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION
    )
    _validate_tracked_plan_phase_retained_projection_contract(
        clean,
        interruption,
        expected_recovery_authorization_sha256=actual_authorization_sha256,
    )
    _validate_tracked_plan_phase_recovery_authorization_semantics(
        actual_authorization
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


def test_tracked_plan_phase_recovery_uses_the_second_authorization_path() -> None:
    assert TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION.relative_to(REPO_ROOT).as_posix() == (
        "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/"
        "task-3/fresh-child-resume-recovery-authorization.json"
    )


def test_tracked_plan_phase_actual_recovery_record_matches_its_lifecycle_contract() -> None:
    assert TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION.is_file()
    record = _load_json(TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION)

    lifecycle = _validate_tracked_plan_phase_recovery_authorization_lifecycle(record)
    assert lifecycle in {
        "unbound_pending",
        "bound_pending",
        "owner_confirmed",
    }
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    if lifecycle == "owner_confirmed":
        _validate_tracked_plan_phase_retained_projections(clean, interruption)
    else:
        with pytest.raises(AssertionError, match="owner-confirmed"):
            _validate_tracked_plan_phase_retained_projections(clean, interruption)


@pytest.mark.parametrize(
    ("harness", "expected_lifecycle"),
    (
        (_TRACKED_PLAN_PILOT_PENDING_HARNESS_BINDING, "unbound_pending"),
        (_TRACKED_PLAN_PILOT_TEST_HARNESS_BINDING, "bound_pending"),
    ),
)
def test_tracked_plan_phase_pure_pending_recovery_record_lifecycle_contracts(
    harness: Mapping[str, object],
    expected_lifecycle: str,
) -> None:
    pending = _tracked_plan_phase_pending_recovery_authorization_fixture(
        second_recovery_harness=harness
    )

    assert _validate_tracked_plan_phase_recovery_authorization_lifecycle(pending) == (
        expected_lifecycle
    )


def test_tracked_plan_phase_pure_owner_confirmed_recovery_record_lifecycle_contract(
) -> None:
    confirmed = _tracked_plan_phase_owner_confirmed_recovery_authorization_fixture()

    assert _validate_tracked_plan_phase_recovery_authorization_lifecycle(confirmed) == (
        "owner_confirmed"
    )


@pytest.mark.parametrize("binding_field", tuple(_TRACKED_PLAN_PILOT_TEST_HARNESS_BINDING))
def test_tracked_plan_phase_pending_recovery_record_rejects_mixed_harness_population(
    binding_field: str,
) -> None:
    mixed = dict(_TRACKED_PLAN_PILOT_PENDING_HARNESS_BINDING)
    mixed[binding_field] = _TRACKED_PLAN_PILOT_TEST_HARNESS_BINDING[binding_field]
    pending = _tracked_plan_phase_pending_recovery_authorization_fixture(
        second_recovery_harness=mixed
    )

    with pytest.raises(AssertionError, match="complete placeholder or populated set"):
        _validate_tracked_plan_phase_recovery_authorization_lifecycle(pending)


def test_tracked_plan_phase_pending_recovery_record_rejects_extra_fields() -> None:
    pending = _tracked_plan_phase_pending_recovery_authorization_fixture(
        second_recovery_harness=_TRACKED_PLAN_PILOT_TEST_HARNESS_BINDING
    )
    pending["unexpected"] = True

    with pytest.raises(AssertionError, match="unexpected fields"):
        _validate_tracked_plan_phase_recovery_authorization_lifecycle(pending)


def _tracked_plan_phase_recovery_authorization_scope_fixture() -> dict[str, object]:
    return {
        "permitted_operations_in_order": [
            (
                "Delete exactly the currently bound failed "
                "tracked-plan-phase-interrupted-new-id directory once and no other path."
            ),
            (
                "Recreate exactly tracked-plan-phase-interrupted-new-id once under the "
                "bound dedicated root; do not create any other run ID or run root."
            ),
            (
                "Interrupt that recreated same-ID run once immediately after the committed "
                "plan.draft provider boundary, without moving the interruption point."
            ),
            (
                "Resume exactly that recreated tracked-plan-phase-interrupted-new-id once "
                "using the landed fresh-child resume fix."
            ),
            (
                "Publish only the already-defined clean_run.json and interruption_resume.json "
                "retained projections atomically if and only if every required validation "
                "passes."
            ),
        ],
        "required_invariants": [
            (
                "tracked-plan-phase-clean-new-id remains byte-for-byte equal to its bound "
                "36-entry tree and state hashes before, during, and after recovery."
            ),
            "The dedicated root contains exactly the two bound top-level run IDs.",
            (
                "The legacy run root remains byte-for-byte equal to its bound 418108-entry "
                "tree."
            ),
            "The top-level design-plan scratch set remains empty.",
            (
                "Historical clean artifact equality remains not_asserted; deterministic "
                "provider-contract conformance is the only authorized artifact-parity claim."
            ),
        ],
        "forbidden_operations": [
            "Any third run or different replacement run ID.",
            "Any mutation of the protected clean run or legacy root.",
            "Any temporary orchestrator run root.",
            "Any workflow execution other than the enumerated same-ID recreation and resume.",
            "Any second deletion, recreation, interruption, resume, or publication attempt.",
            "Any publication other than the exact two retained projections.",
        ],
        "fail_closed_conditions": [
            "Any authorization, incident, fix, review, root, run, state, or evidence binding differs.",
            "The pending form has not been genuinely replaced and adopted by the owner.",
            "The failed interrupted path is absent, symlinked, not a directory, or changed.",
            "The clean run changes at any point.",
            "The dedicated root has any top-level entry other than the two bound run IDs.",
            "The recreated interruption is not the unchanged post-plan.draft committed boundary.",
            "Resume does not complete through the landed fresh-child resume fix.",
            "Any parity, artifact-lineage, lifecycle, checksum, scan, or publication validation fails.",
            "The operation would need another attempt for any reason.",
        ],
    }


def _tracked_plan_phase_recovery_owner_statements_fixture() -> list[str]:
    return [
        (
            "I acknowledge that the first recovery authorization was consumed exactly once "
            "by the failed recovery attempt and cannot be reused."
        ),
        (
            "I reviewed both bound incident records, the correction authorization, the "
            "landed generic fix commit and tree, both reviewed complete-candidate hashes, "
            "and every post-failure root and run binding in this record."
        ),
        (
            "I reviewed and bind the exact second-recovery harness commit and tree and "
            "its ordered primary and secondary reviewed complete-candidate SHA256 "
            "bindings in this record."
        ),
        (
            "I authorize only one deletion of the currently bound failed interrupted run, "
            "one recreation of the same ID, one interruption at the unchanged post-plan.draft "
            "boundary, and one resume of that same ID using the landed fix."
        ),
        (
            "I authorize atomic publication of only the already-defined two retained "
            "projections if and only if all validations pass."
        ),
        (
            "I require the protected clean run, the exact two run IDs, the legacy root, the "
            "absent evidence destination, and the empty scratch set to remain within their "
            "exact bound contract."
        ),
        (
            "I forbid any third run, temporary run root, other workflow execution, legacy-root "
            "mutation, moved interruption point, or further attempt, and require fail-closed "
            "termination on any mismatch or failure."
        ),
        (
            "I understand that this authorization does not attest Task 3, retirement "
            "validation, or pilot completion and does not change historical clean artifact "
            "equality from not_asserted."
        ),
    ]


def _tracked_plan_phase_recovery_bindings_fixture(
    *,
    second_recovery_harness: Mapping[str, object],
) -> dict[str, object]:
    return {
        "prior_incident": {
            "path": TRACKED_PLAN_PILOT_PRIOR_RECOVERY_INCIDENT.relative_to(
                REPO_ROOT
            ).as_posix(),
            "sha256": TRACKED_PLAN_PILOT_PRIOR_RECOVERY_INCIDENT_SHA256,
        },
        "failed_recovery_incident": {
            "path": TRACKED_PLAN_PILOT_RECOVERY_INCIDENT.relative_to(REPO_ROOT).as_posix(),
            "sha256": TRACKED_PLAN_PILOT_RECOVERY_INCIDENT_SHA256,
        },
        "consumed_first_recovery_authorization": {
            "path": TRACKED_PLAN_PILOT_FIRST_RECOVERY_AUTHORIZATION.relative_to(
                REPO_ROOT
            ).as_posix(),
            "sha256": TRACKED_PLAN_PILOT_FIRST_RECOVERY_AUTHORIZATION_SHA256,
            "disposition": "consumed_exactly_once",
        },
        "artifact_parity_evidence_correction_authorization": {
            "path": TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION.relative_to(
                REPO_ROOT
            ).as_posix(),
            "sha256": TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION_SHA256,
            "authorizes_run_mutation": False,
        },
        "generic_fresh_child_resume_fix": {
            "commit": TRACKED_PLAN_PILOT_RECOVERY_COMMIT,
            "commit_tree": TRACKED_PLAN_PILOT_RECOVERY_COMMIT_TREE,
            "subject": "Resume only persisted child call frames",
            "primary_review_complete_candidate_sha256": (
                TRACKED_PLAN_PILOT_RECOVERY_PRIMARY_REVIEW_SHA256
            ),
            "secondary_review_complete_candidate_sha256": (
                TRACKED_PLAN_PILOT_RECOVERY_SECONDARY_REVIEW_SHA256
            ),
        },
        "second_recovery_harness": dict(second_recovery_harness),
        "legacy_root": {
            "canonical_path": TRACKED_PLAN_PILOT_LEGACY_RUN_ROOT.as_posix(),
            "entry_count": 418108,
            "tree_sha256": (
                "sha256:0a4f6e4ce63731c7a219201356f78c1f1e015770e553a465531e7816f2cd40e8"
            ),
        },
        "dedicated_root": {
            "canonical_path": TRACKED_PLAN_PILOT_RUN_ROOT.as_posix(),
            "entry_count": 70,
            "tree_sha256": (
                "sha256:198d022c1878df3a86992d3fa8b968bbb537d23e70a31a31f8dfccb769344b1b"
            ),
            "top_level_run_ids": list(TRACKED_PLAN_PILOT_RUN_IDS),
        },
        "clean_run": {
            "run_id": TRACKED_PLAN_PILOT_RUN_IDS[0],
            "entry_count": 36,
            "tree_sha256": TRACKED_PLAN_PILOT_CLEAN_TREE_SHA256,
            "state_sha256": TRACKED_PLAN_PILOT_CLEAN_STATE_SHA256,
            "status": "completed",
            "error": None,
        },
        "failed_interrupted_run": {
            "run_id": TRACKED_PLAN_PILOT_RUN_IDS[1],
            "entry_count": 32,
            "tree_sha256": (
                "sha256:b13a9c972e01a96d7aeef355366acd0a9f2155b97475fe3590597ba61101297d"
            ),
            "state_sha256": (
                "sha256:6922d406e417b9b17df1e059610ebf372efab88819f8260a91d82d714d6ab0fb"
            ),
            "status": "failed",
            "error": None,
            "nested_call_failure": {
                "status": "failed",
                "error_type": "lexical_default_resume_invalid",
                "diagnostics": ["lexical_default_resume_prior_boundary_missing"],
            },
        },
        "retained_evidence_destination": {
            "path": TRACKED_PLAN_PILOT_CLEAN_EVIDENCE.parent.relative_to(
                REPO_ROOT
            ).as_posix(),
            "status": "absent",
        },
        "top_level_design_plan_scratch": {
            "path_pattern": "/tmp/design-plan-impl-stack-*",
            "matching_directories": [],
        },
        "historical_clean_artifact_equality": "not_asserted",
    }


def _tracked_plan_phase_recovery_confirmed_claims_fixture() -> list[str]:
    return [
        (
            "This authorization permits only the enumerated recovery and conditional "
            "atomic publication; it authorizes no other run-root or workflow mutation."
        ),
        "It does not attest Task 3, retirement validation, or pilot completion.",
        (
            "It does not assert historical clean artifact equality; that remains "
            "not_asserted under the retained correction authorization."
        ),
        (
            "The pending template, standing preparation direction, and test fixtures "
            "are not owner authorization or adoption."
        ),
    ]


def _tracked_plan_phase_pending_owner_action_fixture() -> dict[str, object]:
    return {
        "status": "not_reviewed_or_adopted",
        "instructions": (
            "This is a pending form, not authorization. The intended owner must review "
            "every fixed binding, scope item, confirmation statement, and claim boundary. "
            "Only the owner or an agent acting under the owner's explicit direction may "
            "replace this form with the exact owner-confirmed schema; preparation of this "
            "form is not adoption."
        ),
        "pre_adoption_sequence": [
            "Complete both ordered reviews against the exact pending recovery-harness candidate.",
            (
                "Commit the recovery harness, routed status documents, incident records, "
                "and immutable input records while this form remains pending and "
                "non-authorizing."
            ),
            (
                "Mechanically replace all four second_recovery_harness placeholders with "
                "the actual committed harness commit, commit tree, primary reviewed "
                "complete-candidate SHA256, and secondary reviewed complete-candidate "
                "SHA256; keep this form pending."
            ),
            (
                "Only after those exact bindings are populated may the intended owner "
                "review the whole record and explicitly adopt the owner-confirmed schema."
            ),
            (
                "After adoption, complete final exact owner-record verification and ordered "
                "reviews before any live recovery action."
            ),
        ],
        "required_replacements": [
            (
                "Replace all four second_recovery_harness placeholders mechanically with "
                "the actual post-review harness commit, commit tree, and ordered reviewed "
                "complete-candidate SHA256 bindings while evidence_status remains "
                "pending_owner_confirmation."
            ),
            "Replace evidence_status with owner_confirmed.",
            (
                "Replace authorized_disposition with "
                "replace_failed_interrupted_run_same_id_once_after_fresh_child_fix."
            ),
            "Replace intended_owner with owner using the same exact owner object.",
            (
                "Remove owner_action_required and add owner_confirmations with a genuine "
                "confirmed_at timestamp and the exact fixed statements below."
            ),
            (
                "Add prepared_by naming the actual mechanical writer and prepared_at with "
                "the genuine write timestamp."
            ),
            (
                "Add owner_adoption with the exact owner object, a genuine adopted_at "
                "timestamp, and a provenance_statement describing the owner's actual "
                "review, explicit adoption, and direction to the mechanical writer."
            ),
            (
                "Replace claims_not_made with the exact fixed confirmed-record claim "
                "boundaries below."
            ),
        ],
        "fixed_owner_confirmation_statements": (
            _tracked_plan_phase_recovery_owner_statements_fixture()
        ),
        "fixed_confirmed_claims_not_made": (
            _tracked_plan_phase_recovery_confirmed_claims_fixture()
        ),
    }


def _tracked_plan_phase_pending_claims_fixture() -> list[str]:
    return [
        (
            "This pending form is not owner authorization, owner confirmation, owner "
            "adoption, or owner provenance."
        ),
        (
            "It authorizes no deletion, recreation, interruption, resume, publication, "
            "workflow execution, or other mutation."
        ),
        "It does not attest Task 3, retirement validation, or pilot completion.",
        (
            "It does not assert historical clean artifact equality; that remains "
            "not_asserted under the retained correction authorization."
        ),
    ]


def _tracked_plan_phase_pending_recovery_authorization_fixture(
    *,
    second_recovery_harness: Mapping[str, object],
) -> dict[str, object]:
    return {
        "record_type": (
            "procedure_first_pilot_task3_fresh_child_resume_recovery_authorization"
        ),
        "version": 1,
        "evidence_status": "pending_owner_confirmation",
        "authorized_disposition": "pending_owner_decision",
        "intended_owner": {"name": "Ollie", "email": "ohoidn@stanford.edu"},
        "bindings": _tracked_plan_phase_recovery_bindings_fixture(
            second_recovery_harness=second_recovery_harness
        ),
        "authorization_scope": _tracked_plan_phase_recovery_authorization_scope_fixture(),
        "owner_action_required": _tracked_plan_phase_pending_owner_action_fixture(),
        "template_prepared_by": "Codex /root — non-owner template preparation only",
        "claims_not_made": _tracked_plan_phase_pending_claims_fixture(),
    }


def _tracked_plan_phase_owner_confirmed_recovery_authorization_fixture(
    *,
    second_recovery_harness: Mapping[str, object] = (
        _TRACKED_PLAN_PILOT_TEST_HARNESS_BINDING
    ),
) -> dict[str, object]:
    timestamp = "2026-07-15T12:34:56-07:00"
    owner = {"name": "Ollie", "email": "ohoidn@stanford.edu"}
    return {
        "record_type": (
            "procedure_first_pilot_task3_fresh_child_resume_recovery_authorization"
        ),
        "version": 1,
        "evidence_status": "owner_confirmed",
        "authorized_disposition": (
            "replace_failed_interrupted_run_same_id_once_after_fresh_child_fix"
        ),
        "owner": owner,
        "bindings": _tracked_plan_phase_recovery_bindings_fixture(
            second_recovery_harness=second_recovery_harness
        ),
        "authorization_scope": _tracked_plan_phase_recovery_authorization_scope_fixture(),
        "owner_confirmations": {
            "confirmed_at": timestamp,
            "statements": _tracked_plan_phase_recovery_owner_statements_fixture(),
        },
        "template_prepared_by": "Codex /root — non-owner template preparation only",
        "prepared_by": "TEST FIXTURE mechanical writer — not an owner record",
        "prepared_at": timestamp,
        "owner_adoption": {
            "owner": owner,
            "adopted_at": timestamp,
            "provenance_statement": (
                "TEST FIXTURE ONLY: the fixture owner reviewed the exact fixed scope and "
                "bindings, explicitly adopted every confirmation statement, and directed "
                "the named fixture writer to record this pure no-action test form."
            ),
        },
        "claims_not_made": _tracked_plan_phase_recovery_confirmed_claims_fixture(),
    }


def _tracked_plan_phase_recovery_preflight_fixture() -> dict[str, object]:
    authorization = _tracked_plan_phase_owner_confirmed_recovery_authorization_fixture()
    incident = _load_json(TRACKED_PLAN_PILOT_RECOVERY_INCIDENT)
    legacy_scan = _tracked_plan_phase_scan_fact_fixture()
    dedicated_scan = {
        **_tracked_plan_phase_scan_fact_fixture("2"),
        "root": TRACKED_PLAN_PILOT_RUN_ROOT.as_posix(),
        "retired_identities": ["old::identity"],
        "matches": [],
        "terminal_run_count": 0,
        "nonterminal_run_count": 0,
        "call_frame_count": 0,
        "consumer_count": 0,
    }
    bindings = authorization["bindings"]
    harness = bindings["second_recovery_harness"]
    return {
        "authorization": authorization,
        "authorization_sha256": "sha256:" + "a" * 64,
        "correction_authorization": (
            _tracked_plan_phase_correction_authorization_fixture()
        ),
        "correction_authorization_sha256": (
            TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION_SHA256
        ),
        "incident": incident,
        "incident_sha256": TRACKED_PLAN_PILOT_RECOVERY_INCIDENT_SHA256,
        "observed_head_commit": harness["commit"],
        "observed_head_tree": harness["commit_tree"],
        "observed_legacy_root": deepcopy(bindings["legacy_root"]),
        "observed_dedicated_root": deepcopy(bindings["dedicated_root"]),
        "observed_run_ids": tuple(bindings["dedicated_root"]["top_level_run_ids"]),
        "observed_clean_run": deepcopy(bindings["clean_run"]),
        "observed_failed_run": deepcopy(bindings["failed_interrupted_run"]),
        "observed_publication_destination": deepcopy(
            _tracked_plan_phase_expected_publication_destination()
        ),
        "retained_evidence_targets_present": (),
        "scratch_paths": (),
        "expected_legacy_scan": legacy_scan,
        "observed_legacy_scan": deepcopy(legacy_scan),
        "expected_dedicated_scan": dedicated_scan,
        "observed_dedicated_scan": deepcopy(dedicated_scan),
    }


def test_tracked_plan_phase_semantic_confirmed_fixture_satisfies_closed_record_contract_only(
) -> None:
    authorization = _tracked_plan_phase_owner_confirmed_recovery_authorization_fixture()

    with patch("shutil.rmtree", side_effect=AssertionError("deletion forbidden")), patch.object(
        StateManager,
        "__init__",
        side_effect=AssertionError("runtime forbidden"),
    ), patch.object(
        WorkflowExecutor,
        "__init__",
        side_effect=AssertionError("runtime forbidden"),
    ), patch.object(
        ProviderExecutor,
        "execute",
        side_effect=AssertionError("provider execution forbidden"),
    ):
        bindings, harness = (
            _validate_tracked_plan_phase_recovery_authorization_semantics(authorization)
        )

    assert bindings["second_recovery_harness"] == harness


def test_tracked_plan_phase_production_preflight_rejects_semantic_fixture_as_live_authority(
) -> None:
    arguments = _tracked_plan_phase_recovery_preflight_fixture()

    with pytest.raises(AssertionError, match="actual on-disk recovery authorization"):
        _validate_tracked_plan_phase_recovery_preflight(**arguments)


def test_tracked_plan_phase_production_preflight_rejects_digest_mismatch_before_semantics(
) -> None:
    arguments = _tracked_plan_phase_recovery_preflight_fixture()
    actual_digest = "sha256:" + "1" * 64
    arguments["authorization_sha256"] = "sha256:" + "2" * 64

    with patch(
        f"{__name__}._load_json_with_sha256",
        return_value=(arguments["authorization"], actual_digest),
    ), pytest.raises(
        AssertionError,
        match="actual on-disk recovery authorization SHA256",
    ):
        _validate_tracked_plan_phase_recovery_preflight(**arguments)


def test_tracked_plan_phase_recovery_preflight_contract_binds_observed_harness_head_and_tree(
) -> None:
    arguments = _tracked_plan_phase_recovery_preflight_fixture()
    harness = arguments["authorization"]["bindings"]["second_recovery_harness"]

    assert arguments["observed_head_commit"] == harness["commit"]
    assert arguments["observed_head_tree"] == harness["commit_tree"]
    _validate_tracked_plan_phase_recovery_preflight_contract(**arguments)


@pytest.mark.parametrize(
    "harness",
    (
        _TRACKED_PLAN_PILOT_PENDING_HARNESS_BINDING,
        _TRACKED_PLAN_PILOT_TEST_HARNESS_BINDING,
    ),
)
def test_tracked_plan_phase_pure_pending_authorization_rejects_preflight_before_actions(
    harness: Mapping[str, object],
) -> None:
    arguments = _tracked_plan_phase_recovery_preflight_fixture()
    pending = _tracked_plan_phase_pending_recovery_authorization_fixture(
        second_recovery_harness=harness
    )
    digest = "sha256:" + "5" * 64
    arguments["authorization"] = pending
    arguments["authorization_sha256"] = digest

    with patch(
        f"{__name__}._load_json_with_sha256",
        return_value=(pending, digest),
    ), patch("shutil.rmtree", side_effect=AssertionError("deletion forbidden")), patch.object(
        StateManager,
        "__init__",
        side_effect=AssertionError("runtime forbidden"),
    ), patch.object(
        WorkflowExecutor,
        "__init__",
        side_effect=AssertionError("runtime forbidden"),
    ), patch.object(
        ProviderExecutor,
        "execute",
        side_effect=AssertionError("provider execution forbidden"),
    ), pytest.raises(AssertionError, match="owner-confirmed"):
        _validate_tracked_plan_phase_recovery_preflight(**arguments)


def test_tracked_plan_phase_bound_pending_mechanical_population_is_valid_but_not_authority(
) -> None:
    bound_pending = _tracked_plan_phase_pending_recovery_authorization_fixture(
        second_recovery_harness=_TRACKED_PLAN_PILOT_PENDING_HARNESS_BINDING
    )
    bound_pending["bindings"]["second_recovery_harness"].update(
        _TRACKED_PLAN_PILOT_TEST_HARNESS_BINDING
    )
    assert bound_pending == _tracked_plan_phase_pending_recovery_authorization_fixture(
        second_recovery_harness=_TRACKED_PLAN_PILOT_TEST_HARNESS_BINDING
    )
    assert _validate_tracked_plan_phase_recovery_authorization_lifecycle(
        bound_pending
    ) == "bound_pending"

    arguments = _tracked_plan_phase_recovery_preflight_fixture()
    digest = "sha256:" + "6" * 64
    arguments["authorization"] = bound_pending
    arguments["authorization_sha256"] = digest
    with patch(
        f"{__name__}._load_json_with_sha256",
        return_value=(bound_pending, digest),
    ), pytest.raises(AssertionError, match="owner-confirmed"):
        _validate_tracked_plan_phase_recovery_preflight(**arguments)


def test_tracked_plan_phase_consumed_first_authorization_cannot_be_reused() -> None:
    arguments = _tracked_plan_phase_recovery_preflight_fixture()
    arguments["authorization"] = _load_json(
        TRACKED_PLAN_PILOT_FIRST_RECOVERY_AUTHORIZATION
    )
    arguments["authorization_sha256"] = _sha256_path(
        TRACKED_PLAN_PILOT_FIRST_RECOVERY_AUTHORIZATION
    )

    with patch("shutil.rmtree", side_effect=AssertionError("deletion forbidden")), patch.object(
        StateManager,
        "__init__",
        side_effect=AssertionError("runtime forbidden"),
    ), patch.object(
        WorkflowExecutor,
        "__init__",
        side_effect=AssertionError("runtime forbidden"),
    ), patch.object(
        ProviderExecutor,
        "execute",
        side_effect=AssertionError("provider execution forbidden"),
    ), pytest.raises(AssertionError):
        _validate_tracked_plan_phase_recovery_preflight(**arguments)


def test_tracked_plan_phase_failed_run_binding_extracts_nested_resume_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = TRACKED_PLAN_PILOT_RUN_IDS[1]
    run_path = tmp_path / run_id
    run_path.mkdir()
    state = {
        "status": "failed",
        "error": None,
        "call_frames": {
            "frame": {
                "status": "failed",
                "state": {
                    "status": "failed",
                    "error": {
                        "type": "lexical_default_resume_invalid",
                        "context": {
                            "diagnostics": [
                                "lexical_default_resume_prior_boundary_missing"
                            ]
                        },
                    },
                },
            }
        },
    }
    (run_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setitem(
        _tracked_plan_phase_observed_run_binding.__globals__,
        "TRACKED_PLAN_PILOT_RUN_ROOT",
        tmp_path,
    )

    binding = _tracked_plan_phase_observed_run_binding(
        run_id,
        include_failure_type=True,
    )

    assert binding["status"] == "failed"
    assert binding["error"] is None
    assert binding["nested_call_failure"] == {
        "status": "failed",
        "error_type": "lexical_default_resume_invalid",
        "diagnostics": ["lexical_default_resume_prior_boundary_missing"],
    }


def test_tracked_plan_phase_recovery_preflight_requires_exact_artifact_evidence_correction_authorization(
) -> None:
    arguments = _tracked_plan_phase_recovery_preflight_fixture()
    arguments.update(
        correction_authorization=_tracked_plan_phase_correction_authorization_fixture(),
        correction_authorization_sha256=(
            TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION_SHA256
        ),
    )

    _validate_tracked_plan_phase_recovery_preflight_contract(**arguments)


def test_tracked_plan_phase_retained_projection_uses_provider_contract_without_historical_equality(
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()

    assert "artifacts_equal_to_clean" not in interruption["comparison"]
    assert clean["historical_clean_artifact_bytes_retained"] is False
    assert clean["historical_clean_artifact_equality"] == "not_asserted"
    assert interruption["historical_clean_artifact_equality"] == "not_asserted"
    assert interruption["comparison"] == {
        "public_output_equal_to_clean": True,
        "recovered_artifacts_conform_to_deterministic_provider_contract": True,
        "historical_clean_artifact_equality": "not_asserted",
    }
    assert clean["artifact_contract"]["content_sha256"].startswith("sha256:")
    assert interruption["artifacts"] == clean["artifact_contract"]["artifacts"]

    _validate_tracked_plan_phase_retained_projection_contract(clean, interruption)


def test_tracked_plan_phase_retained_projections_bind_second_recovery_authorization() -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()

    for projection in (clean, interruption):
        assert projection["fresh_child_resume_recovery_authorization"] == {
            "path": TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION.relative_to(
                REPO_ROOT
            ).as_posix(),
            "sha256": _sha256_path(TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION),
        }
        assert projection["artifact_evidence_correction_authorization"] == (
            _tracked_plan_phase_correction_authorization_binding()
        )
        assert projection["historical_clean_artifact_equality"] == "not_asserted"


def test_tracked_plan_phase_retained_projections_reject_different_recovery_authorizations() -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    interruption["fresh_child_resume_recovery_authorization"]["sha256"] = (
        "sha256:" + "b" * 64
    )

    with pytest.raises(AssertionError, match="same recovery authorization"):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


def test_tracked_plan_phase_retained_projections_reject_same_noncurrent_recovery_authorization(
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    noncurrent_sha256 = "sha256:" + "f" * 64
    assert noncurrent_sha256 != _sha256_path(TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION)
    for projection in (clean, interruption):
        projection["fresh_child_resume_recovery_authorization"]["sha256"] = (
            noncurrent_sha256
        )

    with pytest.raises(AssertionError, match="current recovery authorization"):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


@pytest.mark.parametrize(
    "harness",
    (
        _TRACKED_PLAN_PILOT_PENDING_HARNESS_BINDING,
        _TRACKED_PLAN_PILOT_TEST_HARNESS_BINDING,
    ),
)
def test_tracked_plan_phase_retained_replay_rejects_pure_pending_authorization(
    harness: Mapping[str, object],
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    pending = _tracked_plan_phase_pending_recovery_authorization_fixture(
        second_recovery_harness=harness
    )
    digest = "sha256:" + "7" * 64
    for projection in (clean, interruption):
        projection["fresh_child_resume_recovery_authorization"]["sha256"] = digest

    with patch(
        f"{__name__}._load_json_with_sha256",
        return_value=(pending, digest),
    ), pytest.raises(AssertionError, match="owner-confirmed"):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


def test_tracked_plan_phase_current_task3_has_only_authorized_live_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert "test_tracked_plan_phase_exact_two_run_evidence" not in globals()
    assert TRACKED_PLAN_PILOT_CURRENT_LIVE_SELECTOR == (
        "test_tracked_plan_phase_authorized_interrupted_run_recovery"
    )
    tagged_selectors = {
        name
        for name, value in globals().items()
        if callable(value)
        and getattr(value, "_tracked_plan_phase_current_live_selector", False)
    }
    assert tagged_selectors == {TRACKED_PLAN_PILOT_CURRENT_LIVE_SELECTOR}

    monkeypatch.delenv(TRACKED_PLAN_PILOT_LIVE_ENV, raising=False)
    assert _tracked_plan_phase_live_recovery_enabled() is False
    monkeypatch.setenv(TRACKED_PLAN_PILOT_LIVE_ENV, "1")
    assert _tracked_plan_phase_live_recovery_enabled() is True


def test_tracked_plan_phase_correction_authorization_accepts_only_exact_owner_record(
) -> None:
    authorization = _tracked_plan_phase_correction_authorization_fixture()

    _validate_tracked_plan_phase_correction_authorization(
        authorization,
        TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION_SHA256,
    )


def test_tracked_plan_phase_correction_authorization_tracked_record_matches_exact_fixture(
) -> None:
    authorization = _load_json(TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION)

    assert authorization == _tracked_plan_phase_correction_authorization_fixture()
    _validate_tracked_plan_phase_correction_authorization(
        authorization,
        _sha256_path(TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION),
    )


def test_tracked_plan_phase_correction_authorization_rejects_wrong_record_digest(
) -> None:
    with pytest.raises(AssertionError, match="authorization SHA256"):
        _validate_tracked_plan_phase_correction_authorization(
            _tracked_plan_phase_correction_authorization_fixture(),
            "sha256:" + "0" * 64,
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda authorization: authorization.__setitem__(
                "evidence_status", "prepared_for_owner_confirmation"
            ),
            "owner-confirmed",
        ),
        (
            lambda authorization: authorization["bindings"]["clean_run"].__setitem__(
                "tree_sha256", "sha256:" + "0" * 64
            ),
            "digest bindings",
        ),
        (
            lambda authorization: authorization["owner_confirmations"][
                "statements"
            ].pop(),
            "statements",
        ),
        (
            lambda authorization: authorization["owner_adoption"].__setitem__(
                "adopted_at", "2026-07-15T09:07:00-07:00"
            ),
            "adoption",
        ),
        (
            lambda authorization: authorization["claims_not_made"].pop(),
            "claim boundaries",
        ),
    ],
)
def test_tracked_plan_phase_correction_authorization_rejects_stale_owner_record(
    mutate,
    message: str,
) -> None:
    authorization = _tracked_plan_phase_correction_authorization_fixture()
    mutate(authorization)

    with pytest.raises(AssertionError, match=message):
        _validate_tracked_plan_phase_correction_authorization(
            authorization,
            TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION_SHA256,
        )


@pytest.mark.parametrize("projection_name", ("clean", "interruption"))
def test_tracked_plan_phase_retained_projection_rejects_missing_correction_binding(
    projection_name: str,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    projection = clean if projection_name == "clean" else interruption
    projection.pop("artifact_evidence_correction_authorization")

    with pytest.raises(
        AssertionError,
        match="top-level schema|correction authorization binding",
    ):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


@pytest.mark.parametrize(
    "stale_value",
    (True, False, None, "equal", "not-asserted"),
)
@pytest.mark.parametrize(
    "location",
    ("clean", "interruption", "comparison"),
)
def test_tracked_plan_phase_retained_projection_rejects_stale_historical_equality(
    stale_value: object,
    location: str,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    target = interruption["comparison"] if location == "comparison" else (
        clean if location == "clean" else interruption
    )
    target["historical_clean_artifact_equality"] = stale_value

    with pytest.raises(AssertionError, match="historical clean artifact equality"):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


@pytest.mark.parametrize(
    "location",
    ("clean", "interruption", "comparison"),
)
def test_tracked_plan_phase_retained_projection_rejects_absent_historical_equality(
    location: str,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    target = interruption["comparison"] if location == "comparison" else (
        clean if location == "clean" else interruption
    )
    target.pop("historical_clean_artifact_equality")

    with pytest.raises(
        AssertionError,
        match="top-level schema|historical clean artifact equality|comparison",
    ):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


def test_tracked_plan_phase_retained_projection_rejects_equivalent_historical_equality_inference(
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    clean["historical_clean_artifacts_equal"] = True

    with pytest.raises(
        AssertionError,
        match="top-level schema|historical clean artifact equality",
    ):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


@pytest.mark.parametrize(
    "unknown_claim",
    (
        "clean_artifact_equality",
        "historical_artifact_equality",
        "recovered_artifacts_equal_to_clean",
        "same_as_clean_artifacts",
    ),
)
@pytest.mark.parametrize("projection_name", ("clean", "interruption"))
def test_tracked_plan_phase_retained_projection_rejects_unknown_top_level_equality_claims(
    unknown_claim: str,
    projection_name: str,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    projection = clean if projection_name == "clean" else interruption
    projection[unknown_claim] = True

    with pytest.raises(AssertionError, match="top-level schema"):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


@pytest.mark.parametrize(
    "unknown_claim",
    (
        "clean_artifact_equality",
        "historical_artifact_equality",
        "recovered_artifacts_equal_to_clean",
        "same_as_clean_artifacts",
    ),
)
def test_tracked_plan_phase_retained_projection_rejects_nested_resume_equality_claims(
    unknown_claim: str,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    interruption["resume"][unknown_claim] = True

    with pytest.raises(AssertionError, match="resume evidence schema"):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


@pytest.mark.parametrize(
    ("nested_object", "select"),
    [
        ("source", lambda clean, _interruption: clean["source"]),
        ("run", lambda clean, _interruption: clean["run"]),
        (
            "correction-binding",
            lambda clean, _interruption: clean[
                "artifact_evidence_correction_authorization"
            ],
        ),
        (
            "identity-comparison",
            lambda clean, _interruption: clean["identity_comparison"],
        ),
        (
            "artifact-contract",
            lambda clean, _interruption: clean["artifact_contract"],
        ),
        (
            "provider-evidence",
            lambda clean, _interruption: clean["artifact_contract"][
                "provider_evidence"
            ][0],
        ),
        (
            "structured-output-bundle",
            lambda clean, _interruption: clean["artifact_contract"][
                "provider_evidence"
            ][0]["structured_output_bundle"],
        ),
        (
            "provider-artifact",
            lambda clean, _interruption: clean["artifact_contract"][
                "provider_evidence"
            ][0]["artifacts"][0],
        ),
        (
            "aggregate-contract-artifact",
            lambda clean, _interruption: clean["artifact_contract"]["artifacts"][
                "design_path"
            ],
        ),
        (
            "interruption-facts",
            lambda _clean, interruption: interruption["interruption"],
        ),
        ("resume-facts", lambda _clean, interruption: interruption["resume"]),
        (
            "resume-attempts",
            lambda _clean, interruption: interruption["resume"][
                "provider_role_attempts"
            ],
        ),
        ("comparison", lambda _clean, interruption: interruption["comparison"]),
        (
            "observed-artifact",
            lambda _clean, interruption: interruption["artifacts"]["design_path"],
        ),
    ],
)
def test_tracked_plan_phase_retained_projection_rejects_unknown_fields_in_nested_evidence_objects(
    nested_object: str,
    select,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    selected = select(clean, interruption)
    selected["unexpected_evidence_claim"] = nested_object

    with pytest.raises(AssertionError):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


def _readdress_tracked_plan_phase_fixture_artifact_contract(
    artifact_contract: dict[str, object],
) -> None:
    body = {
        key: value
        for key, value in artifact_contract.items()
        if key != "content_sha256"
    }
    artifact_contract["content_sha256"] = _tracked_plan_phase_sha256_json(body)


def test_tracked_plan_phase_retained_projection_rejects_readdressed_arbitrary_bundle_path(
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    artifact_contract = clean["artifact_contract"]
    artifact_contract["provider_evidence"][0]["bundle_path"] = (
        "retained/arbitrary-but-unique.json"
    )
    _readdress_tracked_plan_phase_fixture_artifact_contract(artifact_contract)

    with pytest.raises(AssertionError, match="exact clean checkpoint provider reference"):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


@pytest.mark.parametrize("reference_field", ("checkpoint_id", "record_id", "bundle_path"))
@pytest.mark.parametrize("provider_index", (0, -1))
def test_tracked_plan_phase_retained_projection_rejects_readdressed_provider_reference_tamper(
    reference_field: str,
    provider_index: int,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    artifact_contract = clean["artifact_contract"]
    provider_row = artifact_contract["provider_evidence"][provider_index]
    assert reference_field in provider_row
    provider_row[reference_field] = f"tampered:{reference_field}:{provider_index}"
    _readdress_tracked_plan_phase_fixture_artifact_contract(artifact_contract)

    with pytest.raises(AssertionError, match="exact clean checkpoint provider reference"):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


def test_tracked_plan_phase_retained_checkpoint_loader_derives_path_identities(
    tmp_path: Path,
) -> None:
    records_root = tmp_path / "records"
    record_path = records_root / "ckpt:exact" / "record:exact.json"
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        json.dumps(
            {
                "checkpoint_id": "ckpt:exact",
                "record_id": "record:exact",
                "completed_effect_refs": [],
            }
        ),
        encoding="utf-8",
    )

    retained = _tracked_plan_phase_retained_checkpoint_record(
        record_path,
        records_root=records_root,
    )

    assert retained == {
        "record_path": "ckpt:exact/record:exact.json",
        "checkpoint_id": "ckpt:exact",
        "record_id": "record:exact",
        "payload": {
            "checkpoint_id": "ckpt:exact",
            "record_id": "record:exact",
            "completed_effect_refs": [],
        },
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda clean, _interruption: clean["artifact_contract"].__setitem__(
                "content_sha256", "sha256:" + "0" * 64
            ),
            "content address",
        ),
        (
            lambda _clean, interruption: interruption["comparison"].__setitem__(
                "recovered_artifacts_conform_to_deterministic_provider_contract", False
            ),
            "comparison",
        ),
    ],
)
def test_tracked_plan_phase_retained_projection_rejects_contract_or_conformance_mismatch(
    mutate,
    message: str,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    mutate(clean, interruption)

    with pytest.raises(AssertionError, match=message):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


def test_tracked_plan_phase_recovery_preflight_rejects_post_publication_destination_before_actions(
) -> None:
    arguments = _tracked_plan_phase_recovery_preflight_fixture()
    post_publication = deepcopy(_tracked_plan_phase_expected_publication_destination())
    post_publication["final_directory"]["exists"] = True
    arguments["observed_publication_destination"] = post_publication

    with patch("shutil.rmtree", side_effect=AssertionError("deletion forbidden")), patch.object(
        StateManager,
        "__init__",
        side_effect=AssertionError("runtime forbidden"),
    ), patch.object(
        WorkflowExecutor,
        "__init__",
        side_effect=AssertionError("runtime forbidden"),
    ), patch.object(
        ProviderExecutor,
        "execute",
        side_effect=AssertionError("provider execution forbidden"),
    ), pytest.raises(AssertionError, match="publication destination"):
        _validate_tracked_plan_phase_recovery_preflight_contract(**arguments)


@pytest.mark.parametrize("target_index", (0, 1))
@pytest.mark.parametrize(
    ("field", "wrong_value"),
    (
        ("path", "/wrong/evidence-target.json"),
        ("direct_child_name", "wrong-target.json"),
        ("is_direct_child", False),
    ),
)
def test_tracked_plan_phase_recovery_preflight_rejects_wrong_publication_target_in_both_directions(
    target_index: int,
    field: str,
    wrong_value: object,
) -> None:
    arguments = _tracked_plan_phase_recovery_preflight_fixture()
    destination = deepcopy(_tracked_plan_phase_expected_publication_destination())
    destination["targets"][target_index][field] = wrong_value
    arguments["observed_publication_destination"] = destination

    with pytest.raises(AssertionError, match="publication destination"):
        _validate_tracked_plan_phase_recovery_preflight_contract(**arguments)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda destination: destination["final_directory"].__setitem__(
            "path", "/wrong/final-evidence-directory"
        ),
        lambda destination: destination["final_directory"].__setitem__("exists", True),
        lambda destination: destination["final_directory"].__setitem__(
            "is_symlink", True
        ),
        lambda destination: destination["publication_parent"].__setitem__(
            "exists", False
        ),
        lambda destination: destination["publication_parent"].__setitem__(
            "is_directory", False
        ),
        lambda destination: destination["publication_parent"].__setitem__(
            "is_symlink", True
        ),
        lambda destination: destination["publication_parent"].__setitem__(
            "path", "/wrong/publication-parent"
        ),
    ),
)
def test_tracked_plan_phase_recovery_preflight_rejects_unsafe_publication_destination(
    mutate,
) -> None:
    arguments = _tracked_plan_phase_recovery_preflight_fixture()
    destination = deepcopy(_tracked_plan_phase_expected_publication_destination())
    mutate(destination)
    arguments["observed_publication_destination"] = destination

    with pytest.raises(AssertionError, match="publication destination"):
        _validate_tracked_plan_phase_recovery_preflight_contract(**arguments)


def test_tracked_plan_phase_publication_destination_observation_distinguishes_absent_empty_and_dangling_final_directory(
    tmp_path: Path,
) -> None:
    publication_parent = tmp_path / "publication"
    publication_parent.mkdir()
    final_directory = publication_parent / "evidence"
    targets = (final_directory / "clean.json", final_directory / "interruption.json")

    absent = _tracked_plan_phase_publication_destination_observation(targets=targets)
    final_directory.mkdir()
    empty = _tracked_plan_phase_publication_destination_observation(targets=targets)
    final_directory.rmdir()
    final_directory.symlink_to(publication_parent / "missing-directory", target_is_directory=True)
    dangling = _tracked_plan_phase_publication_destination_observation(targets=targets)

    assert absent["final_directory"] == {
        "path": final_directory.as_posix(),
        "exists": False,
        "is_symlink": False,
    }
    assert empty["final_directory"] == {
        "path": final_directory.as_posix(),
        "exists": True,
        "is_symlink": False,
    }
    assert dangling["final_directory"] == {
        "path": final_directory.as_posix(),
        "exists": False,
        "is_symlink": True,
    }


def test_tracked_plan_phase_publication_destination_observation_distinguishes_missing_file_and_symlinked_parent(
    tmp_path: Path,
) -> None:
    missing_parent = tmp_path / "missing-parent"
    missing_final = missing_parent / "evidence"
    missing = _tracked_plan_phase_publication_destination_observation(
        targets=(missing_final / "clean.json", missing_final / "interruption.json")
    )
    file_parent = tmp_path / "file-parent"
    file_parent.write_text("not a directory\n", encoding="utf-8")
    file_final = file_parent / "evidence"
    non_directory = _tracked_plan_phase_publication_destination_observation(
        targets=(file_final / "clean.json", file_final / "interruption.json")
    )
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    symlinked_parent = tmp_path / "symlinked-parent"
    symlinked_parent.symlink_to(real_parent, target_is_directory=True)
    symlinked_final = symlinked_parent / "evidence"
    symlinked = _tracked_plan_phase_publication_destination_observation(
        targets=(symlinked_final / "clean.json", symlinked_final / "interruption.json")
    )

    assert missing["publication_parent"] == {
        "path": missing_parent.as_posix(),
        "exists": False,
        "is_directory": False,
        "is_symlink": False,
    }
    assert non_directory["publication_parent"] == {
        "path": file_parent.as_posix(),
        "exists": True,
        "is_directory": False,
        "is_symlink": False,
    }
    assert symlinked["publication_parent"] == {
        "path": symlinked_parent.as_posix(),
        "exists": True,
        "is_directory": True,
        "is_symlink": True,
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda arguments: arguments["authorization"].__setitem__(
                "evidence_status", "template_pending"
            ),
            "owner-confirmed",
        ),
        (
            lambda arguments: arguments["authorization"].__setitem__(
                "authorized_disposition", "not_authorized"
            ),
            "disposition",
        ),
        (
            lambda arguments: arguments["authorization"]["owner_confirmations"].__setitem__(
                "confirmed_at", None
            ),
            "owner confirmation",
        ),
        (
            lambda arguments: arguments["authorization"]["owner_confirmations"][
                "statements"
            ].__setitem__(0, "stale confirmation"),
            "owner confirmation",
        ),
        (
            lambda arguments: arguments["authorization"]["owner_adoption"].__setitem__(
                "adopted_at", "2026-07-15T12:34:56"
            ),
            "owner adoption",
        ),
        (
            lambda arguments: arguments["authorization"]["owner_adoption"].__setitem__(
                "provenance_statement", "stale provenance"
            ),
            "owner adoption",
        ),
        (
            lambda arguments: arguments["authorization"]["claims_not_made"].__setitem__(
                0, "stale claim"
            ),
            "claim",
        ),
    ),
)
def test_tracked_plan_phase_recovery_preflight_rejects_unconfirmed_or_stale_authorization(
    mutate,
    message: str,
) -> None:
    arguments = _tracked_plan_phase_recovery_preflight_fixture()
    mutate(arguments)

    with pytest.raises(AssertionError, match=message):
        _validate_tracked_plan_phase_recovery_preflight_contract(**arguments)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda authorization: authorization.__setitem__("unexpected", True),
        lambda authorization: authorization["bindings"]["dedicated_root"].__setitem__(
            "unexpected", True
        ),
        lambda authorization: authorization["authorization_scope"].__setitem__(
            "unexpected", []
        ),
        lambda authorization: authorization["owner_confirmations"].__setitem__(
            "unexpected", True
        ),
        lambda authorization: authorization["owner_adoption"].__setitem__(
            "unexpected", True
        ),
    ),
)
def test_tracked_plan_phase_recovery_preflight_rejects_unknown_authorization_fields(
    mutate,
) -> None:
    arguments = _tracked_plan_phase_recovery_preflight_fixture()
    mutate(arguments["authorization"])

    with pytest.raises(AssertionError):
        _validate_tracked_plan_phase_recovery_preflight_contract(**arguments)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda authorization: authorization["bindings"].pop(
                "second_recovery_harness"
            ),
            "second recovery harness binding schema",
        ),
        (
            lambda authorization: authorization["bindings"][
                "second_recovery_harness"
            ].__setitem__("unexpected", True),
            "second recovery harness binding schema",
        ),
        (
            lambda authorization: authorization["bindings"][
                "second_recovery_harness"
            ].__setitem__("commit", "not-a-commit"),
            "second recovery harness commit binding",
        ),
        (
            lambda authorization: authorization["bindings"][
                "second_recovery_harness"
            ].__setitem__("commit_tree", "0" * 39),
            "second recovery harness tree binding",
        ),
        (
            lambda authorization: authorization["bindings"][
                "second_recovery_harness"
            ].__setitem__(
                "primary_review_complete_candidate_sha256", "not-a-sha256"
            ),
            "second recovery harness primary review binding",
        ),
        (
            lambda authorization: authorization["bindings"][
                "second_recovery_harness"
            ].__setitem__(
                "secondary_review_complete_candidate_sha256", "sha256:" + "0" * 63
            ),
            "second recovery harness secondary review binding",
        ),
    ),
)
def test_tracked_plan_phase_recovery_preflight_rejects_invalid_harness_binding(
    mutate,
    message: str,
) -> None:
    arguments = _tracked_plan_phase_recovery_preflight_fixture()
    mutate(arguments["authorization"])

    with pytest.raises(AssertionError, match=message):
        _validate_tracked_plan_phase_recovery_preflight_contract(**arguments)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda arguments: arguments.__setitem__(
                "authorization_sha256", "not-a-sha256"
            ),
            "authorization SHA256",
        ),
        (
            lambda arguments: arguments.__setitem__(
                "incident_sha256", "sha256:" + "0" * 64
            ),
            "incident SHA256",
        ),
        (
            lambda arguments: arguments["authorization"]["bindings"][
                "generic_fresh_child_resume_fix"
            ].__setitem__(
                "commit", "0" * 40
            ),
            "authorization bindings",
        ),
        (
            lambda arguments: arguments.__setitem__("observed_head_commit", "0" * 40),
            "recovery harness commit",
        ),
        (
            lambda arguments: arguments.__setitem__("observed_head_tree", "0" * 40),
            "recovery harness tree",
        ),
        (
            lambda arguments: arguments["observed_legacy_root"].__setitem__(
                "canonical_path", "/wrong/legacy/root"
            ),
            "legacy root",
        ),
        (
            lambda arguments: arguments["observed_dedicated_root"].__setitem__(
                "tree_sha256", "sha256:" + "0" * 64
            ),
            "dedicated root",
        ),
        (
            lambda arguments: arguments.__setitem__(
                "observed_run_ids", (TRACKED_PLAN_PILOT_RUN_IDS[0], "third-run")
            ),
            "exact two run IDs",
        ),
        (
            lambda arguments: arguments["observed_clean_run"].__setitem__(
                "tree_sha256", "sha256:" + "0" * 64
            ),
            "clean run",
        ),
        (
            lambda arguments: arguments["observed_clean_run"].__setitem__(
                "state_sha256", "sha256:" + "0" * 64
            ),
            "clean run",
        ),
        (
            lambda arguments: arguments["observed_clean_run"].__setitem__(
                "status", "failed"
            ),
            "clean run",
        ),
        (
            lambda arguments: arguments["observed_failed_run"].__setitem__(
                "tree_sha256", "sha256:" + "0" * 64
            ),
            "failed interrupted run",
        ),
        (
            lambda arguments: arguments["observed_failed_run"].__setitem__(
                "state_sha256", "sha256:" + "0" * 64
            ),
            "failed interrupted run",
        ),
        (
            lambda arguments: arguments["observed_failed_run"].__setitem__(
                "status", "running"
            ),
            "failed interrupted run",
        ),
        (
            lambda arguments: arguments["observed_failed_run"].__setitem__(
                "error", {"type": "unexpected"}
            ),
            "failed interrupted run",
        ),
        (
            lambda arguments: arguments["observed_failed_run"][
                "nested_call_failure"
            ].__setitem__(
                "error_type", "wrong_nested_error"
            ),
            "failed interrupted run",
        ),
        (
            lambda arguments: arguments["incident"].__setitem__(
                "incident_type", "wrong_incident"
            ),
            "recovery incident content",
        ),
        (
            lambda arguments: arguments.__setitem__(
                "retained_evidence_targets_present", ("clean_run.json",)
            ),
            "retained evidence targets",
        ),
        (
            lambda arguments: arguments.__setitem__(
                "scratch_paths", ("/tmp/design-plan-impl-stack-stale",)
            ),
            "scratch",
        ),
        (
            lambda arguments: arguments["observed_legacy_scan"].__setitem__(
                "normalized_scan_digest", "sha256:" + "0" * 64
            ),
            "legacy scan",
        ),
        (
            lambda arguments: arguments["observed_dedicated_scan"].__setitem__(
                "matches", [{"identity": "old::identity"}]
            ),
            "queried old identity",
        ),
    ),
)
def test_tracked_plan_phase_recovery_preflight_rejects_mismatched_bindings(
    mutate,
    message: str,
) -> None:
    arguments = _tracked_plan_phase_recovery_preflight_fixture()
    mutate(arguments)

    with pytest.raises(AssertionError, match=message):
        _validate_tracked_plan_phase_recovery_preflight_contract(**arguments)


def test_tracked_plan_phase_aggregate_root_binding_matches_adopted_find_sha256sum_encoding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "aggregate-root"
    (root / "empty-directory").mkdir(parents=True)
    (root / "nested").mkdir()
    files = {
        root / "alpha.txt": b"alpha\n",
        root / "nested" / "zeta.txt": b"zeta\n",
    }
    for path, content in files.items():
        path.write_bytes(content)
    monkeypatch.setitem(
        _tracked_plan_phase_observed_root_binding.__globals__,
        "REPO_ROOT",
        tmp_path,
    )
    sha256sum_lines = b"".join(
        (
            f"{hashlib.sha256(content).hexdigest()}  "
            f"{path.relative_to(tmp_path).as_posix()}\n"
        ).encode("utf-8")
        for path, content in sorted(files.items(), key=lambda item: os.fsencode(item[0]))
    )

    assert _tracked_plan_phase_observed_root_binding(root) == {
        "canonical_path": root.as_posix(),
        "entry_count": 4,
        "tree_sha256": f"sha256:{hashlib.sha256(sha256sum_lines).hexdigest()}",
    }


def test_tracked_plan_phase_aggregate_root_binding_changes_only_digest_on_file_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "aggregate-root"
    root.mkdir()
    target = root / "bound.txt"
    target.write_text("before\n", encoding="utf-8")
    monkeypatch.setitem(
        _tracked_plan_phase_observed_root_binding.__globals__,
        "REPO_ROOT",
        tmp_path,
    )
    before = _tracked_plan_phase_observed_root_binding(root)

    target.write_text("after\n", encoding="utf-8")
    after = _tracked_plan_phase_observed_root_binding(root)

    assert before["entry_count"] == after["entry_count"] == 1
    assert before["tree_sha256"] != after["tree_sha256"]


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


def test_tracked_plan_phase_retained_projection_rejects_different_valid_clean_tree_digest(
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    clean["run"]["tree_sha256"] = "sha256:" + "0" * 64

    with pytest.raises(AssertionError, match="authorized clean run tree"):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda clean: clean["source"].__setitem__("sha256", "sha256:" + "0" * 64), "source"),
        (lambda clean: clean["run"].__setitem__("tree_sha256", "not-a-digest"), "run tree"),
        (
            lambda clean: clean["artifact_contract"]["artifacts"]["plan_path"].__setitem__(
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


@pytest.mark.parametrize("projection_direction", ("clean", "interruption"))
def test_tracked_plan_phase_retained_projection_rejects_recovered_artifact_byte_tamper_in_both_directions(
    tmp_path: Path,
    projection_direction: str,
) -> None:
    state = {
        "status": "completed",
        "error": None,
        "workflow_outputs": _tracked_plan_phase_expected_outputs(),
    }
    records: list[dict[str, object]] = []
    bundle_payloads: dict[str, dict[str, object]] = {}
    output_paths: dict[str, str] = {}
    output_name_by_path = {
        path: name.removeprefix("return__")
        for name, path in _tracked_plan_phase_expected_outputs().items()
        if name.endswith("_path")
    }
    for role, specification in _TRACKED_PLAN_PILOT_PROVIDER_FIXTURE_CONTRACT.items():
        provider_reference = _TRACKED_PLAN_PILOT_CLEAN_PROVIDER_REFERENCES[role]
        checkpoint_id = provider_reference["checkpoint_id"]
        record_id = provider_reference["record_id"]
        bundle_path = provider_reference["bundle_path"]
        bundle = dict(specification["bundle"])
        payload_digest = _tracked_plan_phase_sha256_json(bundle)
        records.append(
            {
                "record_path": f"{checkpoint_id}/{record_id}.json",
                "checkpoint_id": checkpoint_id,
                "record_id": record_id,
                "payload": {
                    "checkpoint_id": checkpoint_id,
                    "record_id": record_id,
                    "completed_effect_refs": [
                        {
                            "effect_kind": "provider",
                            "status": "completed",
                            "evidence_kind": "structured_output_bundle",
                            "bundle_path": bundle_path,
                            "payload_digest": payload_digest,
                            "artifact_digest": payload_digest,
                        }
                    ],
                },
            }
        )
        bundle_payloads[bundle_path] = bundle
        for artifact_path, content in specification["artifacts"]:
            artifact = tmp_path / artifact_path
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(content)
            output_paths[output_name_by_path[artifact_path]] = artifact_path
    clean_artifact_contract = _tracked_plan_phase_reconstructed_clean_artifact_contract(
        state=state,
        state_sha256=TRACKED_PLAN_PILOT_CLEAN_STATE_SHA256,
        checkpoint_records=tuple(records),
        bundle_payloads=bundle_payloads,
    )
    recovered_before = _tracked_plan_phase_artifact_projection(tmp_path, output_paths)
    assert recovered_before == clean_artifact_contract["artifacts"]
    first_artifact = next(
        tmp_path / artifact_path
        for specification in _TRACKED_PLAN_PILOT_PROVIDER_FIXTURE_CONTRACT.values()
        for artifact_path, _content in specification["artifacts"]
    )
    first_artifact.write_bytes(b"tampered recovered bytes\n")
    recovered_after = _tracked_plan_phase_artifact_projection(tmp_path, output_paths)
    assert recovered_after != clean_artifact_contract["artifacts"]

    clean, interruption = _tracked_plan_phase_projection_fixtures()
    if projection_direction == "clean":
        clean["artifact_contract"]["artifacts"] = recovered_after
        contract_body = {
            key: value
            for key, value in clean["artifact_contract"].items()
            if key != "content_sha256"
        }
        clean["artifact_contract"]["content_sha256"] = (
            _tracked_plan_phase_sha256_json(contract_body)
        )
    else:
        interruption["artifacts"] = recovered_after

    with pytest.raises(AssertionError, match="artifact contract|recovered artifact"):
        _validate_tracked_plan_phase_retained_projections(clean, interruption)


def test_tracked_plan_phase_pair_publication_directory_rename_failure_is_invisible(
    tmp_path: Path,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    final_directory = tmp_path / "evidence"
    targets = (final_directory / "clean.json", final_directory / "interruption.json")

    with patch(
        f"{__name__}._tracked_plan_phase_rename_directory_noreplace",
        side_effect=OSError("injected directory commit failure"),
    ), pytest.raises(OSError, match="injected directory commit failure"):
        _publish_tracked_plan_phase_contract_fixture_pair_atomically(
            clean,
            interruption,
            targets=targets,
        )

    assert not final_directory.exists()
    assert not tuple(tmp_path.glob(".evidence.staging.*"))


@pytest.mark.parametrize("racing_destination", ("empty_directory", "dangling_symlink"))
def test_tracked_plan_phase_pair_publication_commit_race_never_clobbers_destination(
    tmp_path: Path,
    racing_destination: str,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    final_directory = tmp_path / "evidence"
    targets = (final_directory / "clean.json", final_directory / "interruption.json")
    dangling_target = tmp_path / "missing-destination"
    real_fsync_directory = _tracked_plan_phase_fsync_directory

    def _fsync_staging_then_create_racing_destination(path: Path) -> None:
        real_fsync_directory(path)
        if path.name.startswith(".evidence.staging."):
            if racing_destination == "empty_directory":
                final_directory.mkdir()
            else:
                final_directory.symlink_to(dangling_target, target_is_directory=True)

    with patch(
        f"{__name__}._tracked_plan_phase_fsync_directory",
        side_effect=_fsync_staging_then_create_racing_destination,
    ), pytest.raises(FileExistsError) as raised:
        _publish_tracked_plan_phase_contract_fixture_pair_atomically(
            clean,
            interruption,
            targets=targets,
        )

    assert raised.value.errno == errno.EEXIST
    assert not targets[0].exists() and not targets[1].exists()
    if racing_destination == "empty_directory":
        assert final_directory.is_dir() and not final_directory.is_symlink()
        assert not tuple(final_directory.iterdir())
    else:
        assert final_directory.is_symlink() and not final_directory.exists()
        assert final_directory.readlink() == dangling_target
    assert not tuple(tmp_path.glob(".evidence.staging.*"))


def test_tracked_plan_phase_noreplace_directory_rename_fails_closed_when_unavailable(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()

    with patch("ctypes.CDLL", return_value=SimpleNamespace()), pytest.raises(OSError) as raised:
        _tracked_plan_phase_rename_directory_noreplace(source, destination)

    assert raised.value.errno == errno.ENOSYS
    assert source.is_dir()
    assert not destination.exists() and not destination.is_symlink()


def test_tracked_plan_phase_pair_publication_commits_both_files_once(
    tmp_path: Path,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    final_directory = tmp_path / "evidence"
    targets = (final_directory / "clean.json", final_directory / "interruption.json")

    _publish_tracked_plan_phase_contract_fixture_pair_atomically(
        clean,
        interruption,
        targets=targets,
    )

    assert _load_json(targets[0]) == clean
    assert _load_json(targets[1]) == interruption
    assert not tuple(tmp_path.glob(".evidence.staging.*"))


@pytest.mark.parametrize("preexisting_file", (False, True))
def test_tracked_plan_phase_pair_publication_rejects_preexisting_final_directory(
    tmp_path: Path,
    preexisting_file: bool,
) -> None:
    clean, interruption = _tracked_plan_phase_projection_fixtures()
    final_directory = tmp_path / "evidence"
    final_directory.mkdir()
    if preexisting_file:
        (final_directory / "clean.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="final evidence directory must be absent"):
        _publish_tracked_plan_phase_contract_fixture_pair_atomically(
            clean,
            interruption,
            targets=(final_directory / "clean.json", final_directory / "interruption.json"),
        )

    assert final_directory.exists()
    assert tuple(final_directory.iterdir()) == (
        (final_directory / "clean.json",) if preexisting_file else ()
    )


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
        (
            {"run_id": TRACKED_PLAN_PILOT_RUN_IDS[0], "resume": False},
            "clean run is immutable input",
        ),
        (
            {"run_id": TRACKED_PLAN_PILOT_RUN_IDS[0], "resume": True},
            "clean run is immutable input",
        ),
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


@pytest.mark.parametrize("resume", (False, True))
def test_tracked_plan_phase_runtime_helper_rejects_clean_run_before_writes(
    resume: bool,
) -> None:
    with patch.object(Path, "write_bytes", side_effect=AssertionError("write forbidden")):
        with pytest.raises(AssertionError, match="clean run is immutable input"):
            _execute_design_plan_impl_stack_single_pass_runtime(
                TRACKED_PLAN_PILOT_WORKSPACE,
                run_id=TRACKED_PLAN_PILOT_RUN_IDS[0],
                provider_control={},
                resume=resume,
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
    assert run_id == TRACKED_PLAN_PILOT_RUN_IDS[1], (
        "clean run is immutable input; only the interrupted run ID is authorized"
    )
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
    assert run_id == TRACKED_PLAN_PILOT_RUN_IDS[1], (
        "runtime helper may only recreate or resume the interrupted run; clean run is "
        "immutable input"
    )
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
        assert role in _TRACKED_PLAN_PILOT_PROVIDER_FIXTURE_CONTRACT
        attempts = provider_control.setdefault("attempts", {})
        assert isinstance(attempts, dict)
        attempts[role] = attempts.get(role, 0) + 1
        spec = _TRACKED_PLAN_PILOT_PROVIDER_FIXTURE_CONTRACT[role]
        for relpath, content in spec["artifacts"]:
            target = workspace / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        _write_bundle(
            workspace / getattr(invocation, "output_bundle_path"),
            dict(spec["bundle"]),
        )
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


def _tracked_plan_phase_tree_facts(root: Path) -> dict[str, object]:
    assert root.is_dir() and not root.is_symlink()
    rows: list[tuple[str, str, str | None]] = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        directories.sort()
        filenames.sort()
        current_path = Path(current)
        for name in (*directories, *filenames):
            path = current_path / name
            assert not path.is_symlink(), f"run tree contains a symlink: {path}"
            relative = path.relative_to(root).as_posix()
            if path.is_dir():
                rows.append((relative, "directory", None))
            else:
                assert path.is_file(), f"run tree contains unsupported entry: {path}"
                rows.append((relative, "file", _sha256_path(path)))
    canonical = json.dumps(
        sorted(rows), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return {
        "tree_sha256": f"sha256:{hashlib.sha256(canonical).hexdigest()}",
        "entry_count": len(rows),
    }


def _tracked_plan_phase_run_tree_projection(run_id: str) -> dict[str, object]:
    assert run_id in TRACKED_PLAN_PILOT_RUN_IDS
    run_path = TRACKED_PLAN_PILOT_RUN_ROOT / run_id
    return {
        "id": run_id,
        "relative_path": run_id,
        **_tracked_plan_phase_tree_facts(run_path),
    }


def _tracked_plan_phase_aggregate_root_facts(root: Path) -> dict[str, object]:
    repository_root = REPO_ROOT.resolve(strict=True)
    assert root.is_dir() and not root.is_symlink()
    assert root.resolve(strict=True) == root
    assert root.is_relative_to(repository_root)
    entry_count = 0
    regular_files: list[Path] = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in (*directories, *filenames):
            path = current_path / name
            assert not path.is_symlink(), f"aggregate root contains a symlink: {path}"
            entry_count += 1
            if path.is_dir():
                continue
            assert path.is_file(), f"aggregate root contains unsupported entry: {path}"
            regular_files.append(path)
    sha256sum_lines = b"".join(
        hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii")
        + b"  "
        + os.fsencode(path.relative_to(repository_root).as_posix())
        + b"\n"
        for path in sorted(
            regular_files,
            key=lambda candidate: os.fsencode(
                candidate.relative_to(repository_root).as_posix()
            ),
        )
    )
    return {
        "tree_sha256": f"sha256:{hashlib.sha256(sha256sum_lines).hexdigest()}",
        "entry_count": entry_count,
    }


def _tracked_plan_phase_observed_root_binding(
    root: Path,
    *,
    include_run_ids: bool = False,
) -> dict[str, object]:
    assert root.resolve(strict=True) == root
    binding: dict[str, object] = {
        "canonical_path": root.as_posix(),
        **_tracked_plan_phase_aggregate_root_facts(root),
    }
    if include_run_ids:
        binding["top_level_run_ids"] = list(_tracked_plan_phase_run_root_entries())
    return binding


def _tracked_plan_phase_observed_run_binding(
    run_id: str,
    *,
    include_failure_type: bool,
    state: dict[str, object] | None = None,
) -> dict[str, object]:
    run_path = TRACKED_PLAN_PILOT_RUN_ROOT / run_id
    state_path = run_path / "state.json"
    if state is None:
        state = _load_json(state_path)
    tree = _tracked_plan_phase_run_tree_projection(run_id)
    binding: dict[str, object] = {
        "run_id": run_id,
        "entry_count": tree["entry_count"],
        "tree_sha256": tree["tree_sha256"],
        "state_sha256": _sha256_path(state_path),
        "status": state.get("status"),
        "error": state.get("error"),
    }
    if include_failure_type:
        call_frames = state.get("call_frames")
        assert isinstance(call_frames, dict)
        nested_failures: list[dict[str, object]] = []
        for call_frame in call_frames.values():
            if not isinstance(call_frame, dict) or call_frame.get("status") != "failed":
                continue
            child_state = call_frame.get("state")
            if not isinstance(child_state, dict) or child_state.get("status") != "failed":
                continue
            error = child_state.get("error")
            if not isinstance(error, dict):
                continue
            context = error.get("context")
            assert isinstance(context, dict)
            nested_failures.append(
                {
                    "status": "failed",
                    "error_type": error.get("type"),
                    "diagnostics": context.get("diagnostics"),
                }
            )
        assert len(nested_failures) == 1, (
            "failed interrupted run must contain exactly one nested call failure"
        )
        binding["nested_call_failure"] = nested_failures[0]
    return binding


def _tracked_plan_phase_git_object(revision: str) -> str:
    result = subprocess.run(
        ("git", "rev-parse", revision),
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


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


def _tracked_plan_phase_sha256_json(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _tracked_plan_phase_build_artifact_contract(
    *,
    clean_state_sha256: str,
    provider_evidence: list[dict[str, object]],
) -> dict[str, object]:
    artifacts: dict[str, dict[str, str]] = {}
    output_name_by_path = {
        path: name.removeprefix("return__")
        for name, path in _tracked_plan_phase_expected_outputs().items()
        if name.endswith("_path")
    }
    assert len(provider_evidence) == len(TRACKED_PLAN_PILOT_PROVIDER_ROLES), (
        "artifact contract must contain the exact six provider evidence rows"
    )
    for row, role in zip(
        provider_evidence,
        TRACKED_PLAN_PILOT_PROVIDER_ROLES,
        strict=True,
    ):
        expected_reference = _TRACKED_PLAN_PILOT_CLEAN_PROVIDER_REFERENCES[role]
        assert row.get("provider_role") == role
        assert {
            key: row.get(key)
            for key in ("checkpoint_id", "record_id", "bundle_path")
        } == dict(expected_reference), (
            "provider evidence does not match the exact clean checkpoint provider reference"
        )
        for artifact in row["artifacts"]:
            assert isinstance(artifact, dict)
            output_name = artifact["output_name"]
            artifacts[output_name] = {
                "path": artifact["path"],
                "sha256": artifact["sha256"],
            }
    assert set(artifacts) == set(output_name_by_path.values()), (
        "provider fixture contract does not reconstruct every public artifact"
    )
    body: dict[str, object] = {
        "schema": "procedure_first_pilot_deterministic_provider_artifact_contract.v1",
        "derivation": (
            "reconstructed_from_bound_completed_clean_state_and_six_"
            "digest_bound_checkpoint_provider_refs"
        ),
        "bound_clean_state_sha256": clean_state_sha256,
        "provider_evidence": provider_evidence,
        "artifacts": dict(sorted(artifacts.items())),
    }
    return {**body, "content_sha256": _tracked_plan_phase_sha256_json(body)}


def _tracked_plan_phase_fixture_artifact_contract() -> dict[str, object]:
    provider_evidence: list[dict[str, object]] = []
    output_name_by_path = {
        path: name.removeprefix("return__")
        for name, path in _tracked_plan_phase_expected_outputs().items()
        if name.endswith("_path")
    }
    for role in TRACKED_PLAN_PILOT_PROVIDER_ROLES:
        specification = _TRACKED_PLAN_PILOT_PROVIDER_FIXTURE_CONTRACT[role]
        provider_reference = _TRACKED_PLAN_PILOT_CLEAN_PROVIDER_REFERENCES[role]
        bundle = dict(specification["bundle"])
        payload_digest = _tracked_plan_phase_sha256_json(bundle)
        provider_evidence.append(
            {
                "provider_role": role,
                "checkpoint_id": provider_reference["checkpoint_id"],
                "record_id": provider_reference["record_id"],
                "bundle_path": provider_reference["bundle_path"],
                "payload_digest": payload_digest,
                "artifact_digest": payload_digest,
                "structured_output_bundle": bundle,
                "artifacts": [
                    {
                        "output_name": output_name_by_path[artifact_path],
                        "path": artifact_path,
                        "sha256": f"sha256:{hashlib.sha256(content).hexdigest()}",
                    }
                    for artifact_path, content in specification["artifacts"]
                ],
            }
        )
    return _tracked_plan_phase_build_artifact_contract(
        clean_state_sha256=TRACKED_PLAN_PILOT_CLEAN_STATE_SHA256,
        provider_evidence=provider_evidence,
    )


def _validate_tracked_plan_phase_artifact_contract(
    artifact_contract: object,
) -> dict[str, object]:
    assert isinstance(artifact_contract, dict), (
        "deterministic provider artifact contract is missing"
    )
    assert set(artifact_contract) == {
        "schema",
        "derivation",
        "bound_clean_state_sha256",
        "provider_evidence",
        "artifacts",
        "content_sha256",
    }, "deterministic provider artifact contract structure is invalid"
    body = {
        key: value
        for key, value in artifact_contract.items()
        if key != "content_sha256"
    }
    assert artifact_contract["content_sha256"] == _tracked_plan_phase_sha256_json(body), (
        "deterministic provider artifact contract content address is invalid"
    )
    assert artifact_contract["schema"] == (
        "procedure_first_pilot_deterministic_provider_artifact_contract.v1"
    )
    assert artifact_contract["derivation"] == (
        "reconstructed_from_bound_completed_clean_state_and_six_"
        "digest_bound_checkpoint_provider_refs"
    )
    assert artifact_contract["bound_clean_state_sha256"] == (
        TRACKED_PLAN_PILOT_CLEAN_STATE_SHA256
    ), "artifact contract does not bind the authorized completed clean state"
    provider_evidence = artifact_contract["provider_evidence"]
    assert isinstance(provider_evidence, list) and len(provider_evidence) == 6, (
        "artifact contract must retain exactly six checkpoint provider refs"
    )
    observed_bundle_paths: set[str] = set()
    expected_artifacts: dict[str, dict[str, str]] = {}
    output_name_by_path = {
        path: name.removeprefix("return__")
        for name, path in _tracked_plan_phase_expected_outputs().items()
        if name.endswith("_path")
    }
    for row, role in zip(
        provider_evidence,
        TRACKED_PLAN_PILOT_PROVIDER_ROLES,
        strict=True,
    ):
        assert isinstance(row, dict) and set(row) == {
            "provider_role",
            "checkpoint_id",
            "record_id",
            "bundle_path",
            "payload_digest",
            "artifact_digest",
            "structured_output_bundle",
            "artifacts",
        }, "artifact contract provider evidence structure is invalid"
        assert row["provider_role"] == role, (
            "artifact contract provider roles are not the exact ordered six-role contract"
        )
        expected_reference = _TRACKED_PLAN_PILOT_CLEAN_PROVIDER_REFERENCES[role]
        assert {
            key: row[key]
            for key in ("checkpoint_id", "record_id", "bundle_path")
        } == dict(expected_reference), (
            "artifact contract does not retain the exact clean checkpoint provider reference"
        )
        bundle_path = row["bundle_path"]
        assert isinstance(bundle_path, str) and bundle_path, (
            "artifact contract provider bundle path is invalid"
        )
        assert bundle_path not in observed_bundle_paths, (
            "artifact contract provider bundle paths are not unique"
        )
        observed_bundle_paths.add(bundle_path)
        expected_bundle = dict(_TRACKED_PLAN_PILOT_PROVIDER_FIXTURE_CONTRACT[role]["bundle"])
        assert row["structured_output_bundle"] == expected_bundle, (
            "artifact contract structured provider bundle is invalid"
        )
        expected_bundle_digest = _tracked_plan_phase_sha256_json(expected_bundle)
        assert row["payload_digest"] == expected_bundle_digest, (
            "artifact contract provider payload digest is invalid"
        )
        assert row["artifact_digest"] == expected_bundle_digest, (
            "artifact contract provider artifact digest is invalid"
        )
        expected_role_artifacts = [
            {
                "output_name": output_name_by_path[artifact_path],
                "path": artifact_path,
                "sha256": f"sha256:{hashlib.sha256(content).hexdigest()}",
            }
            for artifact_path, content in _TRACKED_PLAN_PILOT_PROVIDER_FIXTURE_CONTRACT[
                role
            ]["artifacts"]
        ]
        assert row["artifacts"] == expected_role_artifacts, (
            "artifact contract provider artifact paths or hashes are invalid"
        )
        for artifact in expected_role_artifacts:
            expected_artifacts[artifact["output_name"]] = {
                "path": artifact["path"],
                "sha256": artifact["sha256"],
            }
    expected_artifacts = dict(sorted(expected_artifacts.items()))
    assert artifact_contract["artifacts"] == expected_artifacts, (
        "artifact contract aggregate artifact projection is invalid"
    )
    return expected_artifacts


def _tracked_plan_phase_reconstructed_clean_artifact_contract(
    *,
    state: dict[str, object],
    state_sha256: str,
    checkpoint_records: tuple[dict[str, object], ...],
    bundle_payloads: Mapping[str, dict[str, object]],
) -> dict[str, object]:
    assert state_sha256 == TRACKED_PLAN_PILOT_CLEAN_STATE_SHA256, (
        "clean retained state SHA256 differs from the correction authorization"
    )
    assert state.get("status") == "completed", "clean retained state is not completed"
    assert state.get("error") is None, "clean retained state has an error"
    assert state.get("workflow_outputs") == _tracked_plan_phase_expected_outputs(), (
        "clean retained workflow outputs differ from the fixture contract"
    )

    provider_roles: set[str] = set()
    provider_evidence_by_role: dict[str, dict[str, object]] = {}
    for retained_record in checkpoint_records:
        assert set(retained_record) == {
            "record_path",
            "checkpoint_id",
            "record_id",
            "payload",
        }, "clean retained checkpoint record identity wrapper is invalid"
        checkpoint_id = retained_record["checkpoint_id"]
        record_id = retained_record["record_id"]
        assert retained_record["record_path"] == f"{checkpoint_id}/{record_id}.json", (
            "clean retained checkpoint record path identity is invalid"
        )
        record = retained_record["payload"]
        assert isinstance(record, dict), "clean retained checkpoint payload is invalid"
        assert record.get("checkpoint_id") == checkpoint_id, (
            "clean retained checkpoint payload identity differs from its record path"
        )
        assert record.get("record_id") == record_id, (
            "clean retained record payload identity differs from its record path"
        )
        effect_refs = record.get("completed_effect_refs", ())
        assert isinstance(effect_refs, list), "checkpoint completed effect refs are invalid"
        for effect_ref in effect_refs:
            assert isinstance(effect_ref, dict), "checkpoint completed effect ref is invalid"
            if effect_ref.get("effect_kind") != "provider":
                continue
            assert effect_ref.get("status") == "completed", (
                "clean checkpoint provider ref is not completed"
            )
            assert effect_ref.get("evidence_kind") == "structured_output_bundle", (
                "clean checkpoint provider ref lacks structured bundle evidence"
            )
            bundle_path = effect_ref.get("bundle_path")
            assert isinstance(bundle_path, str) and bundle_path in bundle_payloads, (
                "clean checkpoint provider bundle path is not retained"
            )
            payload = bundle_payloads[bundle_path]
            matching_roles = [
                role
                for role, specification in _TRACKED_PLAN_PILOT_PROVIDER_FIXTURE_CONTRACT.items()
                if payload == dict(specification["bundle"])
            ]
            assert len(matching_roles) == 1, (
                "clean checkpoint provider bundle does not uniquely match the fixture contract"
            )
            role = matching_roles[0]
            assert role not in provider_roles, (
                "clean checkpoint provider role appears more than once"
            )
            expected_reference = _TRACKED_PLAN_PILOT_CLEAN_PROVIDER_REFERENCES[role]
            assert {
                "checkpoint_id": checkpoint_id,
                "record_id": record_id,
                "bundle_path": bundle_path,
            } == dict(expected_reference), (
                "clean retained provider record does not match the exact authorized reference"
            )
            payload_digest = _tracked_plan_phase_sha256_json(payload)
            assert effect_ref.get("payload_digest") == payload_digest, (
                "clean checkpoint provider payload digest does not bind the retained bundle"
            )
            assert effect_ref.get("artifact_digest") == payload_digest, (
                "clean checkpoint provider artifact digest does not bind the retained bundle"
            )
            bundle_values = set(payload.values())
            for artifact_path, _content in _TRACKED_PLAN_PILOT_PROVIDER_FIXTURE_CONTRACT[
                role
            ]["artifacts"]:
                assert artifact_path in bundle_values, (
                    "clean checkpoint provider artifact path is not bound by its bundle"
                )
            provider_roles.add(role)
            output_name_by_path = {
                path: name.removeprefix("return__")
                for name, path in _tracked_plan_phase_expected_outputs().items()
                if name.endswith("_path")
            }
            provider_evidence_by_role[role] = {
                "provider_role": role,
                "checkpoint_id": checkpoint_id,
                "record_id": record_id,
                "bundle_path": bundle_path,
                "payload_digest": payload_digest,
                "artifact_digest": payload_digest,
                "structured_output_bundle": payload,
                "artifacts": [
                    {
                        "output_name": output_name_by_path[artifact_path],
                        "path": artifact_path,
                        "sha256": f"sha256:{hashlib.sha256(content).hexdigest()}",
                    }
                    for artifact_path, content in _TRACKED_PLAN_PILOT_PROVIDER_FIXTURE_CONTRACT[
                        role
                    ]["artifacts"]
                ],
            }

    assert provider_roles == set(_TRACKED_PLAN_PILOT_PROVIDER_FIXTURE_CONTRACT), (
        "clean checkpoint records do not retain the exact provider fixture contract"
    )
    return _tracked_plan_phase_build_artifact_contract(
        clean_state_sha256=state_sha256,
        provider_evidence=[
            provider_evidence_by_role[role]
            for role in TRACKED_PLAN_PILOT_PROVIDER_ROLES
        ],
    )


def _tracked_plan_phase_retained_checkpoint_record(
    path: Path,
    *,
    records_root: Path,
) -> dict[str, object]:
    retained: dict[str, object] = {
        "record_path": path.relative_to(records_root).as_posix(),
        "checkpoint_id": path.parent.name,
        "record_id": path.stem,
        "payload": _load_json(path),
    }
    payload = retained["payload"]
    assert isinstance(payload, dict)
    assert payload.get("checkpoint_id") == retained["checkpoint_id"], (
        "clean retained checkpoint payload identity differs from its record path"
    )
    assert payload.get("record_id") == retained["record_id"], (
        "clean retained record payload identity differs from its record path"
    )
    assert retained["record_path"] == (
        f"{retained['checkpoint_id']}/{retained['record_id']}.json"
    ), "clean retained checkpoint record path identity is invalid"
    return retained


def _tracked_plan_phase_retained_clean_provider_evidence(
    run_id: str,
) -> tuple[tuple[dict[str, object], ...], dict[str, dict[str, object]]]:
    records_root = (
        TRACKED_PLAN_PILOT_RUN_ROOT / run_id / "workflow_lisp" / "checkpoints" / "records"
    )
    record_paths = tuple(sorted(records_root.glob("*/*.json")))
    assert record_paths, "clean retained checkpoint records are missing"
    records: tuple[dict[str, object], ...] = tuple(
        _tracked_plan_phase_retained_checkpoint_record(
            path,
            records_root=records_root,
        )
        for path in record_paths
    )
    bundle_payloads: dict[str, dict[str, object]] = {}
    workspace_root = TRACKED_PLAN_PILOT_WORKSPACE.resolve(strict=True)
    for retained_record in records:
        payload = retained_record["payload"]
        assert isinstance(payload, dict)
        for effect_ref in payload.get("completed_effect_refs", ()):
            if effect_ref.get("effect_kind") != "provider":
                continue
            bundle_path = effect_ref.get("bundle_path")
            assert isinstance(bundle_path, str) and bundle_path
            bundle_file = TRACKED_PLAN_PILOT_WORKSPACE / bundle_path
            assert bundle_file.resolve(strict=True).is_relative_to(workspace_root), (
                "clean retained provider bundle escapes the pilot workspace"
            )
            payload = _load_json(bundle_file)
            assert isinstance(payload, dict), "clean retained provider bundle is not an object"
            bundle_payloads[bundle_path] = payload
    return records, bundle_payloads


def _tracked_plan_phase_common_run_projection(
    *,
    run_id: str,
    state: dict[str, object],
    bundle: object,
    recovery_authorization_sha256: str,
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
        "fresh_child_resume_recovery_authorization": (
            _tracked_plan_phase_recovery_authorization_binding(
                recovery_authorization_sha256
            )
        ),
        "artifact_evidence_correction_authorization": (
            _tracked_plan_phase_correction_authorization_binding()
        ),
        "historical_clean_artifact_bytes_retained": False,
        "historical_clean_artifact_equality": "not_asserted",
        "checkpoint_ids": identity_projection["new_checkpoint_ids"],
        "presentation_keys": identity_projection["new_presentation_keys"],
        "registered_workflows": list(bundle.registered_workflows),
        "identity_comparison": identity_projection,
    }


def _tracked_plan_phase_rename_directory_noreplace(
    source: Path,
    destination: Path,
) -> None:
    at_fdcwd = -100
    rename_noreplace = 1
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2")
    except (AttributeError, OSError) as unavailable:
        raise OSError(
            errno.ENOSYS,
            os.strerror(errno.ENOSYS),
            os.fspath(destination),
        ) from unavailable
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = renameat2(
        at_fdcwd,
        os.fsencode(source),
        at_fdcwd,
        os.fsencode(destination),
        rename_noreplace,
    )
    if result != 0:
        observed_errno = ctypes.get_errno()
        raise OSError(
            observed_errno,
            os.strerror(observed_errno),
            os.fspath(destination),
        )


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
    _publish_tracked_plan_phase_validated_evidence_pair_atomically(
        clean,
        interruption,
        targets=targets,
    )


def _publish_tracked_plan_phase_contract_fixture_pair_atomically(
    clean: dict[str, object],
    interruption: dict[str, object],
    *,
    targets: tuple[Path, Path],
) -> None:
    _validate_tracked_plan_phase_retained_projection_contract(clean, interruption)
    _publish_tracked_plan_phase_validated_evidence_pair_atomically(
        clean,
        interruption,
        targets=targets,
    )


def _publish_tracked_plan_phase_validated_evidence_pair_atomically(
    clean: dict[str, object],
    interruption: dict[str, object],
    *,
    targets: tuple[Path, Path] = (
        TRACKED_PLAN_PILOT_CLEAN_EVIDENCE,
        TRACKED_PLAN_PILOT_RESUME_EVIDENCE,
    ),
) -> None:
    assert len(set(targets)) == 2, "retained evidence targets must be distinct"
    final_directory = targets[0].parent
    assert all(target.parent == final_directory for target in targets), (
        "retained evidence targets must share one final evidence directory"
    )
    assert all(target == final_directory / target.name for target in targets), (
        "retained evidence targets must be direct children of the final directory"
    )
    assert not final_directory.exists() and not final_directory.is_symlink(), (
        "final evidence directory must be absent"
    )
    publication_parent = final_directory.parent
    assert publication_parent.is_dir() and not publication_parent.is_symlink(), (
        "evidence publication parent must be an existing nonsymlink directory"
    )
    staging_directory = Path(
        tempfile.mkdtemp(
            prefix=f".{final_directory.name}.staging.",
            dir=publication_parent,
        )
    )
    committed = False
    try:
        for target, payload in zip(targets, (clean, interruption), strict=True):
            staged_target = staging_directory / target.name
            with staged_target.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        _tracked_plan_phase_fsync_directory(staging_directory)
        _tracked_plan_phase_rename_directory_noreplace(
            staging_directory,
            final_directory,
        )
        committed = True
        _tracked_plan_phase_fsync_directory(publication_parent)
    finally:
        if not committed and staging_directory.exists():
            shutil.rmtree(staging_directory)


def _tracked_plan_phase_fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@pytest.mark.skipif(
    not _tracked_plan_phase_live_recovery_enabled(),
    reason="owner-confirmed interrupted-run recovery is an explicit one-time gate",
)
@_tracked_plan_phase_current_live_selector
def test_tracked_plan_phase_authorized_interrupted_run_recovery() -> None:
    assert _tracked_plan_phase_live_recovery_enabled(), (
        "authorized interrupted-run recovery requires the explicit live gate"
    )
    _assert_tracked_plan_phase_fixed_root()
    authorization = _load_json(TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION)
    recovery_authorization_sha256 = _sha256_path(
        TRACKED_PLAN_PILOT_RECOVERY_AUTHORIZATION
    )
    correction_authorization = _load_json(
        TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION
    )
    incident = _load_json(TRACKED_PLAN_PILOT_RECOVERY_INCIDENT)
    bindings = authorization["bindings"]
    assert isinstance(bindings, dict)
    pre_edit, expected_legacy_scan, expected_dedicated_scan = (
        _load_tracked_plan_phase_bound_pre_edit_scan()
    )
    observed_legacy_scan = _scan_tracked_plan_phase_store(
        pre_edit, TRACKED_PLAN_PILOT_LEGACY_RUN_ROOT
    )
    observed_dedicated_scan = _scan_tracked_plan_phase_store(
        pre_edit, TRACKED_PLAN_PILOT_RUN_ROOT
    )
    clean_state_path = TRACKED_PLAN_PILOT_RUN_ROOT / TRACKED_PLAN_PILOT_RUN_IDS[0] / "state.json"
    clean_state = _load_json(clean_state_path)
    assert clean_state.get("status") == "completed"
    assert clean_state.get("error") is None
    observed_clean_run = _tracked_plan_phase_observed_run_binding(
        TRACKED_PLAN_PILOT_RUN_IDS[0],
        include_failure_type=False,
        state=clean_state,
    )
    observed_failed_run = _tracked_plan_phase_observed_run_binding(
        TRACKED_PLAN_PILOT_RUN_IDS[1],
        include_failure_type=True,
    )
    retained_targets_present = tuple(
        target.relative_to(REPO_ROOT).as_posix()
        for target in (TRACKED_PLAN_PILOT_CLEAN_EVIDENCE, TRACKED_PLAN_PILOT_RESUME_EVIDENCE)
        if target.exists()
    )
    _validate_tracked_plan_phase_recovery_preflight(
        authorization=authorization,
        authorization_sha256=recovery_authorization_sha256,
        correction_authorization=correction_authorization,
        correction_authorization_sha256=_sha256_path(
            TRACKED_PLAN_PILOT_CORRECTION_AUTHORIZATION
        ),
        incident=incident,
        incident_sha256=_sha256_path(TRACKED_PLAN_PILOT_RECOVERY_INCIDENT),
        observed_head_commit=_tracked_plan_phase_git_object("HEAD"),
        observed_head_tree=_tracked_plan_phase_git_object("HEAD^{tree}"),
        observed_legacy_root=_tracked_plan_phase_observed_root_binding(
            TRACKED_PLAN_PILOT_LEGACY_RUN_ROOT
        ),
        observed_dedicated_root=_tracked_plan_phase_observed_root_binding(
            TRACKED_PLAN_PILOT_RUN_ROOT,
            include_run_ids=True,
        ),
        observed_run_ids=_tracked_plan_phase_run_root_entries(),
        observed_clean_run=observed_clean_run,
        observed_failed_run=observed_failed_run,
        observed_publication_destination=(
            _tracked_plan_phase_publication_destination_observation()
        ),
        retained_evidence_targets_present=retained_targets_present,
        scratch_paths=_tracked_plan_phase_scratch_paths(),
        expected_legacy_scan=expected_legacy_scan,
        observed_legacy_scan=observed_legacy_scan,
        expected_dedicated_scan=expected_dedicated_scan,
        observed_dedicated_scan=observed_dedicated_scan,
    )
    clean_records, clean_bundle_payloads = (
        _tracked_plan_phase_retained_clean_provider_evidence(TRACKED_PLAN_PILOT_RUN_IDS[0])
    )
    clean_artifact_contract = _tracked_plan_phase_reconstructed_clean_artifact_contract(
        state=clean_state,
        state_sha256=_sha256_path(clean_state_path),
        checkpoint_records=clean_records,
        bundle_payloads=clean_bundle_payloads,
    )

    failed_run_path = TRACKED_PLAN_PILOT_RUN_ROOT / TRACKED_PLAN_PILOT_RUN_IDS[1]
    assert failed_run_path == (
        TRACKED_PLAN_PILOT_RUN_ROOT / "tracked-plan-phase-interrupted-new-id"
    )
    assert failed_run_path.parent.resolve(strict=True) == (
        TRACKED_PLAN_PILOT_RUN_ROOT.resolve(strict=True)
    )
    assert failed_run_path.is_dir() and not failed_run_path.is_symlink(), (
        "authorized failed interrupted path must be a nonsymlink directory"
    )
    assert observed_failed_run == _tracked_plan_phase_observed_run_binding(
        TRACKED_PLAN_PILOT_RUN_IDS[1],
        include_failure_type=True,
    ), "failed interrupted run changed after preflight"
    shutil.rmtree(failed_run_path)
    assert not failed_run_path.exists() and not failed_run_path.is_symlink()
    assert observed_clean_run == _tracked_plan_phase_observed_run_binding(
        TRACKED_PLAN_PILOT_RUN_IDS[0],
        include_failure_type=False,
    ), "clean run changed immediately after failed-run deletion"

    expected_roles = list(TRACKED_PLAN_PILOT_PROVIDER_ROLES)
    interruption_control: dict[str, object] = {"interrupt_after_role": "plan.draft"}
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
    assert "plan.review" not in interruption_control["attempts"]
    assert _tracked_plan_phase_run_root_entries() == TRACKED_PLAN_PILOT_RUN_IDS
    assert observed_clean_run == _tracked_plan_phase_observed_run_binding(
        TRACKED_PLAN_PILOT_RUN_IDS[0],
        include_failure_type=False,
    ), "clean run changed during interrupted-run recreation"

    resumed_state, resumed_paths, resumed_bundle = (
        _execute_design_plan_impl_stack_single_pass_runtime(
            TRACKED_PLAN_PILOT_WORKSPACE,
            run_id=TRACKED_PLAN_PILOT_RUN_IDS[1],
            provider_control=interruption_control,
            resume=True,
        )
    )
    assert resumed_state["status"] == "completed"
    assert resumed_state.get("error") is None
    assert resumed_state["workflow_outputs"] == clean_state["workflow_outputs"]
    expected_output_paths = {
        name.removeprefix("return__"): path
        for name, path in _tracked_plan_phase_expected_outputs().items()
        if name.endswith("_path")
    }
    assert interrupted_paths == resumed_paths == expected_output_paths
    assert interruption_control["successful_roles"] == expected_roles
    assert interruption_control["attempts"] == {role: 1 for role in expected_roles}
    assert _tracked_plan_phase_run_root_entries() == TRACKED_PLAN_PILOT_RUN_IDS
    assert observed_clean_run == _tracked_plan_phase_observed_run_binding(
        TRACKED_PLAN_PILOT_RUN_IDS[0],
        include_failure_type=False,
    ), "clean run changed during interrupted-run resume"
    assert not _tracked_plan_phase_scratch_paths()

    default_resume_report = _load_json(
        failed_run_path / "workflow_lisp" / "checkpoints" / "default_resume_report.json"
    )
    assert default_resume_report.get("status") == "pass"
    assert default_resume_report.get("restore_decision") == "RESTORED"
    assert default_resume_report.get("selection_reason") == "validated_prior_boundary"
    checked_workflows = default_resume_report.get("checked_workflows")
    assert isinstance(checked_workflows, list) and len(checked_workflows) == 1
    checked_decision = checked_workflows[0].get("decision")
    assert isinstance(checked_decision, dict)
    assert checked_decision.get("restore_decision") == "RESTORED"
    assert checked_decision.get("selection_reason") == "validated_prior_boundary"

    clean_projection = {
        "schema": "procedure_first_pilot_tracked_plan_clean_run.v1",
        **_tracked_plan_phase_common_run_projection(
            run_id=TRACKED_PLAN_PILOT_RUN_IDS[0],
            state=clean_state,
            bundle=resumed_bundle,
            recovery_authorization_sha256=recovery_authorization_sha256,
        ),
        "status": "completed",
        "provider_roles": expected_roles,
        "artifact_contract": clean_artifact_contract,
    }
    recovered_artifacts = _tracked_plan_phase_artifact_projection(
        TRACKED_PLAN_PILOT_WORKSPACE,
        resumed_paths,
    )
    interruption_projection = {
        "schema": "procedure_first_pilot_tracked_plan_interruption_resume.v1",
        **_tracked_plan_phase_common_run_projection(
            run_id=TRACKED_PLAN_PILOT_RUN_IDS[1],
            state=resumed_state,
            bundle=resumed_bundle,
            recovery_authorization_sha256=recovery_authorization_sha256,
        ),
        "artifacts": recovered_artifacts,
        "artifact_hash_provenance": "observed_post_resume_workspace_files",
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
            "recovered_artifacts_conform_to_deterministic_provider_contract": (
                recovered_artifacts == clean_artifact_contract["artifacts"]
            ),
            "historical_clean_artifact_equality": "not_asserted",
        },
    }
    _validate_tracked_plan_phase_retained_projections(clean_projection, interruption_projection)

    observed_postflight_legacy_scan = _scan_tracked_plan_phase_store(
        pre_edit, TRACKED_PLAN_PILOT_LEGACY_RUN_ROOT
    )
    observed_postflight_dedicated_scan = _scan_tracked_plan_phase_store(
        pre_edit, TRACKED_PLAN_PILOT_RUN_ROOT
    )
    _validate_tracked_plan_phase_postflight_projection(
        dedicated_run_ids=_tracked_plan_phase_run_root_entries(),
        scratch_paths=_tracked_plan_phase_scratch_paths(),
        expected_legacy_scan=expected_legacy_scan,
        observed_legacy_scan=observed_postflight_legacy_scan,
        expected_dedicated_scan=expected_dedicated_scan,
        observed_dedicated_scan=observed_postflight_dedicated_scan,
    )
    assert _tracked_plan_phase_observed_root_binding(TRACKED_PLAN_PILOT_LEGACY_RUN_ROOT) == (
        bindings["legacy_root"]
    ), "legacy root changed during authorized recovery"
    assert observed_clean_run == _tracked_plan_phase_observed_run_binding(
        TRACKED_PLAN_PILOT_RUN_IDS[0],
        include_failure_type=False,
    ), "clean run changed before retained evidence publication"
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
