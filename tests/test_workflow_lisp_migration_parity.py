from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pytest


def _parity_module():
    return importlib.import_module("orchestrator.workflow_lisp.migration_parity")


_RETIRED_PARITY_MODULE_SYMBOLS = (
    "DESIGN_DELTA_G8_DELETION_EVIDENCE_SCHEMA_VERSION",
    "DESIGN_DELTA_G8_DELETED_MANIFEST_ROWS",
    "DESIGN_DELTA_G8_RESOURCE_TRANSITION_HELPERS",
    "DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS",
    "DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS",
    "_resource_transition_parity_evidence",
    "_runtime_audit_transition_parity_evidence",
    "_validated_design_delta_g8_deleted_rows",
)
_RETIRED_PARITY_IDENTIFIERS = frozenset(
    (*_RETIRED_PARITY_MODULE_SYMBOLS, "g8_deletion_evidence", "resource_transition_parity")
)
_RETIRED_PARITY_STRING_CONSTANTS = frozenset(
    {"g8_deletion_evidence", "resource_transition_parity"}
)


def _retired_parity_lane_references(source: str) -> set[str]:
    references: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        identifier: str | None = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            identifier = node.name
        elif isinstance(node, ast.arg):
            identifier = node.arg
        elif isinstance(node, ast.Name):
            identifier = node.id
        elif isinstance(node, ast.Attribute):
            identifier = node.attr
        elif isinstance(node, ast.keyword):
            identifier = node.arg
        if identifier in _RETIRED_PARITY_IDENTIFIERS:
            references.add(identifier)
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in _RETIRED_PARITY_STRING_CONSTANTS
        ):
            references.add(node.value)
    return references


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _sha256_json(payload: object) -> str:
    return _sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _valid_manifest_payload() -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_migration_parity_targets.v1",
        "targets": [
            {
                "workflow_family": "design_plan_impl_stack",
                "candidate": "workflows/examples/design_plan_impl_review_stack_v2_call.orc",
                "yaml_primary": "workflows/examples/design_plan_impl_review_stack_v2_call.yaml",
                "entry_workflow": "design-plan-impl-stack",
                "provider_externs_file": (
                    "workflows/examples/inputs/workflow_lisp_migrations/"
                    "design_plan_impl_stack.providers.json"
                ),
                "prompt_externs_file": (
                    "workflows/examples/inputs/workflow_lisp_migrations/"
                    "design_plan_impl_stack.prompts.json"
                ),
                "command_boundaries_file": (
                    "workflows/examples/inputs/workflow_lisp_migrations/"
                    "design_plan_impl_stack.commands.json"
                ),
                "baseline_characterization": {
                    "inputs": ["progress_report", "execution_report", "backlog_item"],
                    "outputs": ["execution_report", "implementation_state"],
                    "terminal_states": ["completed", "failed"],
                    "artifacts": ["execution_report.md", "implementation_state.json"],
                    "resume_behavior": ["resume reuses approved upstream artifacts"],
                },
                "accepted_differences": [
                    {
                        "id": "debug-yaml-derived-view",
                        "description": "Debug YAML remains a derived view only.",
                    }
                ],
                "deprecated_yaml_mechanics": [
                    {
                        "mechanic": "manual markdown parity summary",
                        "replacement": "machine-readable parity JSON report",
                    }
                ],
                "promotion_eligibility": {
                    "eligible_for_primary_surface": True,
                },
                "compile_artifacts": {
                    "required": ["core_workflow_ast", "semantic_ir", "source_map"],
                    "optional": ["expanded_debug_yaml"],
                },
                "evidence_commands": {
                    "compile": [
                        "python",
                        "-m",
                        "orchestrator",
                        "compile",
                        "workflows/examples/design_plan_impl_review_stack_v2_call.orc",
                        "--entry-workflow",
                        "design-plan-impl-stack",
                    ],
                    "dry_run": [
                        "python",
                        "-m",
                        "orchestrator",
                        "run",
                        "workflows/examples/design_plan_impl_review_stack_v2_call.orc",
                        "--dry-run",
                    ],
                    "smoke_or_integration": [
                        "python",
                        "-m",
                        "pytest",
                        "tests/test_workflow_lisp_key_migrations.py",
                        "-k",
                        "review_loop_parity_fixture",
                        "-q",
                    ],
                    "output_contract_parity": [
                        "python",
                        "-m",
                        "pytest",
                        "tests/test_workflow_lisp_key_migrations.py",
                        "-k",
                        "review_loop_parity_fixture",
                        "-q",
                    ],
                    "terminal_state_parity": [
                        "python",
                        "-m",
                        "pytest",
                        "tests/test_workflow_lisp_key_migrations.py",
                        "-k",
                        "review_loop_parity_fixture",
                        "-q",
                    ],
                    "artifact_parity": [
                        "python",
                        "-m",
                        "pytest",
                        "tests/test_workflow_lisp_key_migrations.py",
                        "-k",
                        "review_loop_parity_fixture",
                        "-q",
                    ],
                    "resume_parity": [
                        "python",
                        "-m",
                        "pytest",
                        "tests/test_workflow_lisp_key_migrations.py",
                        "-k",
                        "resume_or_start_plan_gate_reusable_state_parity_path",
                        "-q",
                    ],
                },
            }
        ],
    }


def _valid_report_payload(*, workflow_family: str = "design_plan_impl_stack") -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_migration_parity_report.v2",
        "workflow_family": workflow_family,
        "candidate": f"workflows/examples/{workflow_family}.orc",
        "yaml_primary": f"workflows/examples/{workflow_family}.yaml",
        "tool_version": "workflow_lisp_migration_parity.v2",
        "dsl_version": "2.14",
        "generated_at": "2026-06-02T00:00:00Z",
        "generated_by": ["python", "-m", "orchestrator", "migration-parity"],
        "report_path": (
            f"artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/{workflow_family}.json"
        ),
        "target_identity": {
            "targets_schema_version": "workflow_lisp_migration_parity_targets.v1",
            "target_manifest_path": "workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json",
            "target_manifest_sha256": "sha256:manifest",
            "target_index": 0,
            "workflow_family": workflow_family,
            "candidate_path": f"workflows/examples/{workflow_family}.orc",
            "candidate_sha256": "sha256:candidate",
            "yaml_primary_path": f"workflows/examples/{workflow_family}.yaml",
            "entry_workflow": "design-plan-impl-stack",
        },
        "evidence_freshness": {
            "generated_at": "2026-06-02T00:00:00Z",
            "compile_manifest_path": (
                "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/build/manifest.json"
            ),
            "compile_manifest_sha256": "sha256:compile-manifest",
            "compiled_workflow_checksum": "sha256:compiled-workflow",
            "required_artifacts": {
                "core_workflow_ast": {
                    "status": "pass",
                    "path": "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/build/core_workflow_ast.json",
                    "sha256": "sha256:core",
                },
                "semantic_ir": {
                    "status": "pass",
                    "path": "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/build/semantic_ir.json",
                    "sha256": "sha256:semantic",
                },
            },
            "evidence_refs": {
                role: {
                    "stdout": {
                        "path": (
                            "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/logs/"
                            f"{workflow_family}/{role}.stdout.log"
                        ),
                        "sha256": f"sha256:{role}-stdout",
                    },
                    "stderr": {
                        "path": (
                            "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/logs/"
                            f"{workflow_family}/{role}.stderr.log"
                        ),
                        "sha256": f"sha256:{role}-stderr",
                    },
                }
                for role in (
                    "compile",
                    "dry_run",
                    "smoke_or_integration",
                    "output_contract_parity",
                    "terminal_state_parity",
                    "artifact_parity",
                    "resume_parity",
                )
            },
        },
        "command_logs": {
            role: {
                "stdout": (
                    "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/logs/"
                    f"{workflow_family}/{role}.stdout.log"
                ),
                "stderr": (
                    "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/logs/"
                    f"{workflow_family}/{role}.stderr.log"
                ),
            }
            for role in (
                "compile",
                "dry_run",
                "smoke_or_integration",
                "output_contract_parity",
                "terminal_state_parity",
                "artifact_parity",
                "resume_parity",
            )
        },
        "accepted_differences": [
            {
                "id": "debug-yaml-derived-view",
                "description": "Debug YAML remains a derived view only.",
            }
        ],
        "deprecated_yaml_mechanics": [
            {
                "mechanic": "manual markdown parity summary",
                "replacement": "machine-readable parity JSON report",
            }
        ],
        "promotion_eligibility": {
            "eligible_for_primary_surface": True,
        },
        "compile_artifacts": {
            "required": {
                "core_workflow_ast": {
                    "status": "pass",
                    "path": "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/build/core_workflow_ast.json",
                },
                "semantic_ir": {
                    "status": "pass",
                    "path": "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/build/semantic_ir.json",
                },
            },
            "optional": {
                "expanded_debug_yaml": {
                    "status": "pass",
                    "path": "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/build/expanded.debug.yaml",
                }
            },
        },
        "evidence": {
            "compile": {
                "status": "pass",
                "argv": ["python", "-m", "orchestrator", "compile"],
                "exit_code": 0,
                "elapsed_seconds": 0.1,
            },
            "shared_validation": {
                "status": "pass",
            },
            "dry_run": {
                "status": "pass",
                "argv": ["python", "-m", "orchestrator", "run", "--dry-run"],
                "exit_code": 0,
                "elapsed_seconds": 0.1,
            },
            "smoke_or_integration": {
                "status": "pass",
                "argv": ["python", "-m", "pytest"],
                "exit_code": 0,
                "elapsed_seconds": 0.1,
            },
            "baseline_characterization": {
                "status": "pass",
                "inputs": ["progress_report", "execution_report", "backlog_item"],
                "outputs": ["execution_report", "implementation_state"],
                "terminal_states": ["completed", "failed"],
                "artifacts": ["execution_report.md", "implementation_state.json"],
                "resume_behavior": ["resume reuses approved upstream artifacts"],
            },
            "output_contract_parity": {
                "status": "pass",
                "argv": ["python", "-m", "pytest"],
                "exit_code": 0,
                "elapsed_seconds": 0.1,
            },
            "terminal_state_parity": {
                "status": "pass",
                "argv": ["python", "-m", "pytest"],
                "exit_code": 0,
                "elapsed_seconds": 0.1,
            },
            "artifact_parity": {
                "status": "pass",
                "argv": ["python", "-m", "pytest"],
                "exit_code": 0,
                "elapsed_seconds": 0.1,
            },
            "resume_parity": {
                "status": "pass",
                "argv": ["python", "-m", "pytest"],
                "exit_code": 0,
                "elapsed_seconds": 0.1,
            },
        },
        "non_regressive": True,
    }


def _design_delta_parent_runtime_audit_artifacts() -> list[dict[str, str]]:
    return [
        {
            "artifact_id": "drain_status_transition_audit",
            "path": (
                "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/"
                "runtime-audits/design_delta_parent_drain_transition_audit.jsonl"
            ),
            "transition_name": "lisp_frontend_design_delta/transitions::write-drain-status-runtime-native",
            "resource_kind": "drain-run-state",
        },
        {
            "artifact_id": "terminal_work_item_transition_audit",
            "path": (
                "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/"
                "runtime-audits/design_delta_parent_drain_transition_audit.jsonl"
            ),
            "transition_name": "lisp_frontend_design_delta/transitions::record-terminal-work-item",
            "resource_kind": "drain-run-state",
        },
        {
            "artifact_id": "blocked_recovery_transition_audit",
            "path": (
                "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/"
                "runtime-audits/design_delta_parent_drain_transition_audit.jsonl"
            ),
            "transition_name": "lisp_frontend_design_delta/transitions::record-blocked-recovery-outcome-stdlib",
            "resource_kind": "drain-run-state",
        },
    ]


def _design_delta_parent_target_entry(base_entry: dict[str, object]) -> dict[str, object]:
    target = json.loads(json.dumps(base_entry))
    target.update(
        {
            "workflow_family": "design_delta_parent_drain",
            "candidate": "workflows/library/lisp_frontend_design_delta/drain.orc",
            "yaml_primary": "workflows/examples/lisp_frontend_design_delta_drain.yaml",
            "entry_workflow": "lisp_frontend_design_delta/drain::drain",
            "provider_externs_file": (
                "workflows/examples/inputs/workflow_lisp_migrations/"
                "design_delta_parent_drain.providers.json"
            ),
            "prompt_externs_file": (
                "workflows/examples/inputs/workflow_lisp_migrations/"
                "design_delta_parent_drain.prompts.json"
            ),
            "command_boundaries_file": (
                "workflows/examples/inputs/workflow_lisp_migrations/"
                "design_delta_parent_drain.commands.json"
            ),
            "readiness_label": "parent_callable_candidate",
            "lowering_route": "wcc_m4",
            "lowering_schema_version": 2,
            "required_family_evidence_roles": [
                "parent_callable_compile",
                "parent_callable_smoke",
                "projection_retirement_parity",
                "view_retirement_parity",
                "public_private_boundary_parity",
                "boundary_artifact_justifications",
                "route_identity",
            ],
            "promotion_eligibility": {
                "eligible_for_primary_surface": False,
                "blocked_reason": (
                    "parent-family candidate only; YAML primary replacement requires "
                    "strict promotable family evidence"
                ),
            },
            "compile_artifacts": {
                "required": [
                    "core_workflow_ast",
                    "semantic_ir",
                    "source_map",
                    "workflow_boundary_projection",
                    "adapter_census",
                    "boundary_authority_report",
                    "value_flow_census_report",
                    "consumer_rendering_census_report",
                    "typed_prompt_input_report",
                    "entry_publication_report",
                    "compatibility_bridge_report",
                    "rendering_cleanup_report",
                    "transition_authoring_report",
                ],
                "optional": ["expanded_debug_yaml"],
            },
            "runtime_audit_artifacts": _design_delta_parent_runtime_audit_artifacts(),
            "family_evidence_artifacts": [
                {
                    "artifact_id": "projection_dual_run_report",
                    "path": (
                        "artifacts/work/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/"
                        "migration-parity/design_delta_parent_drain_projection_dual_run_report.json"
                    ),
                    "evidence_role": "projection_retirement_parity",
                    "schema_version": "workflow_lisp_projection_dual_run_report.v1",
                },
                {
                    "artifact_id": "view_dual_run_report",
                    "path": (
                        "artifacts/work/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/"
                        "migration-parity/design_delta_parent_drain_view_dual_run_report.json"
                    ),
                    "evidence_role": "view_retirement_parity",
                    "schema_version": "workflow_lisp_view_dual_run_report.v1",
                }
            ],
        }
    )
    return target


def _add_parent_family_evidence(
    report: dict[str, object],
    *,
    repo_root: Path,
    route: str = "wcc_m4",
) -> None:
    target_identity = report["target_identity"]
    target_identity.update(
        {
            "readiness_label": "parent_callable_candidate",
            "lowering_route": "wcc_m4",
            "lowering_schema_version": 2,
            "required_family_evidence_roles": [
                "parent_callable_compile",
                "parent_callable_smoke",
                "projection_retirement_parity",
                "view_retirement_parity",
                "public_private_boundary_parity",
                "boundary_artifact_justifications",
                "route_identity",
            ],
            "runtime_audit_artifacts": _design_delta_parent_runtime_audit_artifacts(),
            "family_evidence_artifacts": [
                {
                    "artifact_id": "projection_dual_run_report",
                    "path": (
                        "artifacts/work/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/"
                        "migration-parity/design_delta_parent_drain_projection_dual_run_report.json"
                    ),
                    "evidence_role": "projection_retirement_parity",
                    "schema_version": "workflow_lisp_projection_dual_run_report.v1",
                },
                {
                    "artifact_id": "view_dual_run_report",
                    "path": (
                        "artifacts/work/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/"
                        "migration-parity/design_delta_parent_drain_view_dual_run_report.json"
                    ),
                    "evidence_role": "view_retirement_parity",
                    "schema_version": "workflow_lisp_view_dual_run_report.v1",
                }
            ],
        }
    )
    report["route_identity"] = {
        "readiness_label": "parent_callable_candidate",
        "lowering_route": route,
        "lowering_schema_version": 2,
    }
    runtime_audit_artifacts = target_identity["runtime_audit_artifacts"]
    runtime_audit_path = repo_root / str(runtime_audit_artifacts[0]["path"])
    _write_text(runtime_audit_path, '{"transition":"write-drain-status"}\n')
    report["evidence_freshness"]["runtime_audit_artifacts"] = {
        str(artifact["artifact_id"]): {
            "path": str(artifact["path"]),
            "transition_name": str(artifact["transition_name"]),
            "resource_kind": str(artifact["resource_kind"]),
            "exists": True,
            "sha256": _sha256_file(runtime_audit_path),
        }
        for artifact in runtime_audit_artifacts
    }
    family_freshness: dict[str, object] = {}
    for artifact in target_identity["family_evidence_artifacts"]:
        family_evidence_path = repo_root / str(artifact["path"])
        artifact_id = str(artifact["artifact_id"])
        schema_version = str(artifact["schema_version"])
        if artifact["evidence_role"] == "projection_retirement_parity":
            payload = {
                "schema_version": schema_version,
                "artifact_id": artifact_id,
                "workflow_family": "design_delta_parent_drain",
                "overall_status": "pass",
                "all_passed": True,
                "adapters": {
                    "project_lisp_frontend_selector_action": {
                        "status": "pass",
                        "comparison_mapping_id": "selector_action_projection.v1",
                        "cases": [],
                    }
                },
            }
        else:
            payload = {
                "schema_version": schema_version,
                "artifact_id": artifact_id,
                "workflow_family": "design_delta_parent_drain",
                "overall_status": "pass",
                "all_passed": True,
                "adapters": {
                    "finalize_lisp_frontend_drain_summary": {
                        "status": "pass",
                        "comparison_mapping_id": "drain_summary_view.v1",
                        "cases": [],
                    }
                },
            }
        _write_json(family_evidence_path, payload)
        family_freshness[artifact_id] = {
            "path": str(artifact["path"]),
            "evidence_role": artifact["evidence_role"],
            "declared_schema_version": schema_version,
            "exists": True,
            "sha256": _sha256_file(family_evidence_path),
        }
    report["evidence_freshness"]["family_evidence_artifacts"] = family_freshness
    evidence = report["evidence"]
    for role in target_identity["required_family_evidence_roles"]:
        evidence[role] = {"status": "pass"}


def _add_parent_family_identity(report: dict[str, object]) -> None:
    report["target_identity"].update(
        {
            "readiness_label": "parent_callable_candidate",
            "lowering_route": "wcc_m4",
            "lowering_schema_version": 2,
            "required_family_evidence_roles": [
                "parent_callable_compile",
                "parent_callable_smoke",
                "projection_retirement_parity",
                "view_retirement_parity",
                "public_private_boundary_parity",
                "boundary_artifact_justifications",
                "route_identity",
            ],
            "runtime_audit_artifacts": _design_delta_parent_runtime_audit_artifacts(),
            "family_evidence_artifacts": [
                {
                    "artifact_id": "projection_dual_run_report",
                    "path": (
                        "artifacts/work/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/"
                        "migration-parity/design_delta_parent_drain_projection_dual_run_report.json"
                    ),
                    "evidence_role": "projection_retirement_parity",
                    "schema_version": "workflow_lisp_projection_dual_run_report.v1",
                },
                {
                    "artifact_id": "view_dual_run_report",
                    "path": (
                        "artifacts/work/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/"
                        "migration-parity/design_delta_parent_drain_view_dual_run_report.json"
                    ),
                    "evidence_role": "view_retirement_parity",
                    "schema_version": "workflow_lisp_view_dual_run_report.v1",
                }
            ],
        }
    )


def _set_report_path(report: dict[str, object], *, repo_root: Path, output_root: Path) -> dict[str, object]:
    updated = json.loads(json.dumps(report))
    report_path = output_root / f"{updated['workflow_family']}.json"
    updated["report_path"] = str(report_path.relative_to(repo_root))
    return updated


def _materialize_gate_report(
    tmp_path: Path,
    *,
    manifest_path: Path,
    target_entry: dict[str, object],
    target_index: int,
    output_root: Path,
) -> dict[str, object]:
    workflow_family = str(target_entry["workflow_family"])
    candidate_path = _write_text(
        tmp_path / str(target_entry["candidate"]),
        "(workflow-lisp\n  (:language \"0.1\"))\n",
    )
    yaml_path = _write_text(
        tmp_path / str(target_entry["yaml_primary"]),
        "steps: []\n",
    )

    logs_root = output_root / "logs" / workflow_family
    evidence_refs: dict[str, object] = {}
    command_logs: dict[str, object] = {}
    for role in (
        "compile",
        "dry_run",
        "smoke_or_integration",
        "output_contract_parity",
        "terminal_state_parity",
        "artifact_parity",
        "resume_parity",
    ):
        stdout_log = _write_text(logs_root / f"{role}.stdout.log", f"{workflow_family} {role} stdout\n")
        stderr_log = _write_text(logs_root / f"{role}.stderr.log", "")
        evidence_refs[role] = {
            "stdout": {
                "path": stdout_log.relative_to(tmp_path).as_posix(),
                "sha256": _sha256_file(stdout_log),
            },
            "stderr": {
                "path": stderr_log.relative_to(tmp_path).as_posix(),
                "sha256": _sha256_file(stderr_log),
            },
        }
        command_logs[role] = {
            "stdout": stdout_log.relative_to(tmp_path).as_posix(),
            "stderr": stderr_log.relative_to(tmp_path).as_posix(),
        }

    build_root = tmp_path / "artifacts" / "work" / "LISP-MIGRATE-KEY-WORKFLOWS" / "build" / workflow_family
    core_path = _write_text(build_root / "core_workflow_ast.json", "{\"kind\":\"core\"}\n")
    semantic_path = _write_text(build_root / "semantic_ir.json", "{\"kind\":\"semantic\"}\n")
    compile_manifest_path = build_root / "manifest.json"
    compile_manifest = {
        "shared_validation_status": "validated",
        "artifact_paths": {
            "core_workflow_ast": core_path.relative_to(tmp_path).as_posix(),
            "semantic_ir": semantic_path.relative_to(tmp_path).as_posix(),
        },
        "artifact_status": {
            "core_workflow_ast": "emitted",
            "semantic_ir": "emitted",
        },
        "compiled_workflow_checksum": f"sha256:compiled-workflow-{workflow_family}",
    }
    _write_json(compile_manifest_path, compile_manifest)

    report = _set_report_path(
        _valid_report_payload(workflow_family=workflow_family),
        repo_root=tmp_path,
        output_root=output_root,
    )
    report["candidate"] = str(target_entry["candidate"])
    report["yaml_primary"] = str(target_entry["yaml_primary"])
    report["command_logs"] = command_logs
    report["promotion_eligibility"] = json.loads(
        json.dumps(target_entry["promotion_eligibility"])
    )
    report["target_identity"] = {
        "targets_schema_version": "workflow_lisp_migration_parity_targets.v1",
        "target_manifest_path": manifest_path.relative_to(tmp_path).as_posix(),
        "target_manifest_sha256": _sha256_file(manifest_path),
        "target_index": target_index,
        "workflow_family": workflow_family,
        "candidate_path": candidate_path.relative_to(tmp_path).as_posix(),
        "candidate_sha256": _sha256_file(candidate_path),
        "yaml_primary_path": yaml_path.relative_to(tmp_path).as_posix(),
        "entry_workflow": str(target_entry["entry_workflow"]),
    }
    report["evidence_freshness"] = {
        "generated_at": str(report["generated_at"]),
        "compile_manifest_path": compile_manifest_path.relative_to(tmp_path).as_posix(),
        "compile_manifest_sha256": _sha256_file(compile_manifest_path),
        "compiled_workflow_checksum": compile_manifest["compiled_workflow_checksum"],
        "required_artifacts": {
            "core_workflow_ast": {
                "status": "pass",
                "path": core_path.relative_to(tmp_path).as_posix(),
                "sha256": _sha256_file(core_path),
            },
            "semantic_ir": {
                "status": "pass",
                "path": semantic_path.relative_to(tmp_path).as_posix(),
                "sha256": _sha256_file(semantic_path),
            },
        },
        "evidence_refs": evidence_refs,
    }
    report["compile_artifacts"] = {
        "required": {
            "core_workflow_ast": {
                "status": "pass",
                "path": core_path.relative_to(tmp_path).as_posix(),
            },
            "semantic_ir": {
                "status": "pass",
                "path": semantic_path.relative_to(tmp_path).as_posix(),
            },
        },
        "optional": {},
    }
    report["evidence"]["compile"]["manifest_path"] = compile_manifest_path.relative_to(tmp_path).as_posix()
    return report


def _strict_gate_fixture(tmp_path: Path) -> tuple[object, Path, object, Path, dict[str, object]]:
    module = _parity_module()
    manifest_payload = _valid_manifest_payload()
    manifest_path = _write_json(tmp_path / "parity_targets.json", manifest_payload)
    target = module.load_parity_targets(manifest_path)[0]
    output_root = tmp_path / "artifacts" / "work" / "LISP-MIGRATE-KEY-WORKFLOWS" / "parity"
    report = _materialize_gate_report(
        tmp_path,
        manifest_path=manifest_path,
        target_entry=manifest_payload["targets"][0],
        target_index=0,
        output_root=output_root,
    )
    return module, manifest_path, target, output_root, report


def test_load_parity_targets_rejects_authored_non_regressive(tmp_path: Path) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    payload["targets"][0]["non_regressive"] = False
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)

    with pytest.raises(ValueError, match="non_regressive"):
        module.load_parity_targets(manifest_path)


def test_load_parity_targets_rejects_duplicate_workflow_family(tmp_path: Path) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    payload["targets"].append(dict(payload["targets"][0]))
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)

    with pytest.raises(ValueError, match="workflow_family"):
        module.load_parity_targets(manifest_path)


def test_load_parity_targets_rejects_shell_string_commands(tmp_path: Path) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    payload["targets"][0]["evidence_commands"]["compile"] = "python -m orchestrator compile"
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)

    with pytest.raises(ValueError, match="argv"):
        module.load_parity_targets(manifest_path)


@pytest.mark.parametrize(
    "field_name",
    ["inputs", "outputs", "terminal_states", "artifacts", "resume_behavior"],
)
def test_load_parity_targets_rejects_missing_baseline_fields(
    tmp_path: Path,
    field_name: str,
) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    del payload["targets"][0]["baseline_characterization"][field_name]
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)

    with pytest.raises(ValueError, match=field_name):
        module.load_parity_targets(manifest_path)


def test_load_parity_targets_rejects_hidden_managed_write_root_input(tmp_path: Path) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    payload["targets"][0]["evidence_commands"]["dry_run"].extend(
        ["--input", "__write_root__design-plan=result.json"]
    )
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)

    with pytest.raises(ValueError, match="__write_root__"):
        module.load_parity_targets(manifest_path)


def test_load_parity_targets_hashes_the_manifest_file_not_each_target_row(tmp_path: Path) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    second_target = json.loads(json.dumps(payload["targets"][0]))
    second_target.update(
        {
            "workflow_family": "cycle_guard_demo",
            "candidate": "workflows/examples/cycle_guard_demo.orc",
            "yaml_primary": "workflows/examples/cycle_guard_demo.yaml",
            "entry_workflow": "cycle-guard-demo",
        }
    )
    payload["targets"].append(second_target)
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)

    initial_targets = module.load_parity_targets(manifest_path)
    initial_digest = initial_targets[0].target_manifest_sha256

    payload["targets"][1]["promotion_eligibility"]["blocked_reason"] = "mutated after first load"
    _write_json(manifest_path, payload)

    reloaded_targets = module.load_parity_targets(manifest_path)

    assert reloaded_targets[0].target_manifest_sha256 == _sha256_file(manifest_path)
    assert reloaded_targets[1].target_manifest_sha256 == _sha256_file(manifest_path)
    assert reloaded_targets[0].target_manifest_sha256 != initial_digest


def test_compute_non_regressive_requires_all_required_evidence() -> None:
    module = _parity_module()
    report = _valid_report_payload()
    del report["evidence"]["resume_parity"]

    assert module.compute_non_regressive(report, today=date(2026, 6, 2)) is False


def test_compute_non_regressive_rejects_expired_smoke_waiver() -> None:
    module = _parity_module()
    report = _valid_report_payload()
    report["evidence"]["smoke_or_integration"] = {
        "status": "waived",
        "waiver": {
            "owner": "workflow-lisp",
            "justification": "safe bounded CLI-only evidence",
            "expiry": "2026-06-01",
            "targeted_evidence": ["output_contract_parity"],
        },
    }

    assert module.compute_non_regressive(report, today=date(2026, 6, 2)) is False


def test_compute_non_regressive_accepts_targeted_dry_run_waiver_with_parent_smoke(tmp_path: Path) -> None:
    module = _parity_module()
    report = _valid_report_payload(workflow_family="design_delta_parent_drain")
    _add_parent_family_evidence(report, repo_root=tmp_path)
    report["evidence"]["dry_run"] = {
        "status": "waived",
        "waiver": {
            "owner": "workflow-lisp",
            "justification": "CLI dry-run is not runnable for this parent-family slice; fake-provider smokes are the bounded runtime evidence.",
            "expiry": "2026-07-01",
            "targeted_evidence": ["smoke_or_integration", "parent_callable_smoke"],
        },
    }

    assert module.compute_non_regressive(report, today=date(2026, 6, 2)) is True


def test_compute_non_regressive_rejects_dry_run_waiver_without_targeted_smoke(tmp_path: Path) -> None:
    module = _parity_module()
    report = _valid_report_payload(workflow_family="design_delta_parent_drain")
    _add_parent_family_evidence(report, repo_root=tmp_path)
    report["evidence"]["dry_run"] = {
        "status": "waived",
        "waiver": {
            "owner": "workflow-lisp",
            "justification": "Compile evidence is not a dry-run substitute.",
            "expiry": "2026-07-01",
            "targeted_evidence": ["compile"],
        },
    }

    assert module.compute_non_regressive(report, today=date(2026, 6, 2)) is False


def test_load_parity_targets_accepts_targeted_dry_run_waiver(tmp_path: Path) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    payload["targets"][0]["evidence_commands"]["dry_run"] = {
        "waiver": {
            "owner": "workflow-lisp",
            "justification": "CLI dry-run uses the fake-provider smoke substitute for this bounded slice.",
            "expiry": "2026-07-01",
            "targeted_evidence": ["smoke_or_integration"],
        }
    }
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)

    target = module.load_parity_targets(manifest_path)[0]

    assert target.evidence_commands["dry_run"].argv is None
    assert target.evidence_commands["dry_run"].waiver["targeted_evidence"] == [
        "smoke_or_integration"
    ]


def test_compute_non_regressive_requires_required_compile_artifacts() -> None:
    module = _parity_module()
    report = _valid_report_payload()
    report["compile_artifacts"]["required"]["semantic_ir"]["status"] = "missing"

    assert module.compute_non_regressive(report, today=date(2026, 6, 2)) is False


def test_compute_non_regressive_allows_optional_artifact_not_implemented() -> None:
    module = _parity_module()
    report = _valid_report_payload()
    report["compile_artifacts"]["optional"]["expanded_debug_yaml"]["status"] = "not_implemented"

    assert module.compute_non_regressive(report, today=date(2026, 6, 2)) is True


def test_design_delta_parent_drain_target_rejects_leaf_only_evidence_for_non_regressive() -> None:
    module = _parity_module()
    report = _valid_report_payload(workflow_family="design_delta_parent_drain")
    _add_parent_family_identity(report)

    assert module.compute_non_regressive(report, today=date(2026, 6, 2)) is False


def test_design_delta_parent_drain_requires_route_schema_identity(tmp_path: Path) -> None:
    module = _parity_module()
    report = _valid_report_payload(workflow_family="design_delta_parent_drain")
    _add_parent_family_evidence(report, repo_root=tmp_path, route="legacy")

    assert module.compute_non_regressive(report, today=date(2026, 6, 2)) is False


def test_design_delta_parent_loop_control_accepts_imported_stdlib_owner_route(
    tmp_path: Path,
) -> None:
    module = _parity_module()
    _, _, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = tmp_path / ".orchestrate" / "build" / "stdlib-owner"
    build_root.mkdir(parents=True)
    core_ast_path = build_root / "core_workflow_ast.json"
    _write_json(
        core_ast_path,
        {
            "schema_version": "workflow_lisp_core_workflow_ast.v1",
            "workflow_name": "lisp_frontend_design_delta/drain::drain",
            "body": [
                {
                    "kind": "call",
                    "call_alias": "lisp_frontend_design_delta/drain::build-drain-runtime-owned",
                },
                {
                    "kind": "call",
                    "call_alias": "std/drain::backlog-drain",
                },
                {"kind": "match"},
            ],
        },
    )

    reasons = module._parent_loop_control_reasons(
        target=target,
        compile_payload={"build_root": str(build_root)},
        build_manifest={"artifact_paths": {"core_workflow_ast": str(core_ast_path)}},
        repo_root=tmp_path,
    )

    assert reasons == []


def test_design_delta_parent_loop_control_accepts_promoted_hook_owner_route(
    tmp_path: Path,
) -> None:
    module = _parity_module()
    _, _, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = tmp_path / ".orchestrate" / "build" / "promoted-hook-owner"
    build_root.mkdir(parents=True)
    core_ast_path = build_root / "core_workflow_ast.json"
    _write_json(
        core_ast_path,
        {
            "schema_version": "workflow_lisp_core_workflow_ast.v1",
            "workflow_name": "lisp_frontend_design_delta/drain::drain",
            "body": [
                {
                    "kind": "repeat_until",
                    "statements": [
                        {
                            "kind": "call",
                            "call_alias": (
                                "%stdlib_adapters.lisp_frontend_design_delta/"
                                "stdlib_adapters::select-next-work-stdlib.v1"
                            ),
                        },
                        {
                            "kind": "call",
                            "call_alias": (
                                "%work_item.lisp_frontend_design_delta/"
                                "work_item::run-selected-item-stdlib.v1"
                            ),
                        },
                        {
                            "kind": "call",
                            "call_alias": (
                                "%stdlib_adapters.lisp_frontend_design_delta/"
                                "stdlib_adapters::draft-design-gap-stdlib.v1"
                            ),
                        },
                    ],
                }
            ],
        },
    )

    reasons = module._parent_loop_control_reasons(
        target=target,
        compile_payload={"build_root": str(build_root)},
        build_manifest={"artifact_paths": {"core_workflow_ast": str(core_ast_path)}},
        repo_root=tmp_path,
    )

    assert reasons == []


@pytest.mark.parametrize(
    "final_hook_alias",
    [
        None,
        "%stdlib_adapters.lisp_frontend_design_delta/stdlib_adapters::wrong-gap-hook.v1",
    ],
)
def test_design_delta_parent_loop_control_rejects_missing_or_wrong_promoted_hook(
    tmp_path: Path,
    final_hook_alias: str | None,
) -> None:
    module = _parity_module()
    _, _, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = tmp_path / ".orchestrate" / "build" / "invalid-promoted-hook-owner"
    build_root.mkdir(parents=True)
    core_ast_path = build_root / "core_workflow_ast.json"
    statements = [
        {
            "kind": "call",
            "call_alias": (
                "%stdlib_adapters.lisp_frontend_design_delta/"
                "stdlib_adapters::select-next-work-stdlib.v1"
            ),
        },
        {
            "kind": "call",
            "call_alias": (
                "%work_item.lisp_frontend_design_delta/"
                "work_item::run-selected-item-stdlib.v1"
            ),
        },
    ]
    if final_hook_alias is not None:
        statements.append({"kind": "call", "call_alias": final_hook_alias})
    _write_json(
        core_ast_path,
        {
            "schema_version": "workflow_lisp_core_workflow_ast.v1",
            "workflow_name": "lisp_frontend_design_delta/drain::drain",
            "body": [{"kind": "repeat_until", "statements": statements}],
        },
    )

    reasons = module._parent_loop_control_reasons(
        target=target,
        compile_payload={"build_root": str(build_root)},
        build_manifest={"artifact_paths": {"core_workflow_ast": str(core_ast_path)}},
        repo_root=tmp_path,
    )

    assert reasons == ["parent drain entrypoint does not own loop control"]


def test_design_delta_parent_loop_control_rejects_promoted_hooks_split_across_repeat_nodes(
    tmp_path: Path,
) -> None:
    module = _parity_module()
    _, _, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = tmp_path / ".orchestrate" / "build" / "split-promoted-hook-owner"
    build_root.mkdir(parents=True)
    core_ast_path = build_root / "core_workflow_ast.json"
    _write_json(
        core_ast_path,
        {
            "schema_version": "workflow_lisp_core_workflow_ast.v1",
            "workflow_name": "lisp_frontend_design_delta/drain::drain",
            "body": [
                {
                    "kind": "repeat_until",
                    "statements": [
                        {
                            "kind": "call",
                            "call_alias": (
                                "%stdlib_adapters.lisp_frontend_design_delta/"
                                "stdlib_adapters::select-next-work-stdlib.v1"
                            ),
                        },
                        {
                            "kind": "call",
                            "call_alias": (
                                "%work_item.lisp_frontend_design_delta/"
                                "work_item::run-selected-item-stdlib.v1"
                            ),
                        },
                    ],
                },
                {
                    "kind": "repeat_until",
                    "statements": [
                        {
                            "kind": "call",
                            "call_alias": (
                                "%stdlib_adapters.lisp_frontend_design_delta/"
                                "stdlib_adapters::draft-design-gap-stdlib.v1"
                            ),
                        },
                    ],
                },
            ],
        },
    )

    reasons = module._parent_loop_control_reasons(
        target=target,
        compile_payload={"build_root": str(build_root)},
        build_manifest={"artifact_paths": {"core_workflow_ast": str(core_ast_path)}},
        repo_root=tmp_path,
    )

    assert reasons == ["parent drain entrypoint does not own loop control"]


def test_design_delta_parent_loop_control_rejects_promoted_hooks_split_across_nested_repeats(
    tmp_path: Path,
) -> None:
    module = _parity_module()
    _, _, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = tmp_path / ".orchestrate" / "build" / "nested-promoted-hook-owner"
    build_root.mkdir(parents=True)
    core_ast_path = build_root / "core_workflow_ast.json"
    _write_json(
        core_ast_path,
        {
            "schema_version": "workflow_lisp_core_workflow_ast.v1",
            "workflow_name": "lisp_frontend_design_delta/drain::drain",
            "body": [
                {
                    "kind": "repeat_until",
                    "statements": [
                        {
                            "kind": "call",
                            "call_alias": (
                                "%stdlib_adapters.lisp_frontend_design_delta/"
                                "stdlib_adapters::select-next-work-stdlib.v1"
                            ),
                        },
                        {
                            "kind": "call",
                            "call_alias": (
                                "%work_item.lisp_frontend_design_delta/"
                                "work_item::run-selected-item-stdlib.v1"
                            ),
                        },
                        {
                            "kind": "repeat_until",
                            "statements": [
                                {
                                    "kind": "call",
                                    "call_alias": (
                                        "%stdlib_adapters.lisp_frontend_design_delta/"
                                        "stdlib_adapters::draft-design-gap-stdlib.v1"
                                    ),
                                }
                            ],
                        },
                    ],
                }
            ],
        },
    )

    reasons = module._parent_loop_control_reasons(
        target=target,
        compile_payload={"build_root": str(build_root)},
        build_manifest={"artifact_paths": {"core_workflow_ast": str(core_ast_path)}},
        repo_root=tmp_path,
    )

    assert reasons == ["parent drain entrypoint does not own loop control"]


def test_design_delta_parent_loop_control_rejects_legacy_selector_in_promoted_repeat(
    tmp_path: Path,
) -> None:
    module = _parity_module()
    _, _, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = tmp_path / ".orchestrate" / "build" / "legacy-promoted-hook-owner"
    build_root.mkdir(parents=True)
    core_ast_path = build_root / "core_workflow_ast.json"
    _write_json(
        core_ast_path,
        {
            "schema_version": "workflow_lisp_core_workflow_ast.v1",
            "workflow_name": "lisp_frontend_design_delta/drain::drain",
            "body": [
                {
                    "kind": "repeat_until",
                    "statements": [
                        {
                            "kind": "call",
                            "call_alias": (
                                "%stdlib_adapters.lisp_frontend_design_delta/"
                                "stdlib_adapters::select-next-work-stdlib.v1"
                            ),
                        },
                        {
                            "kind": "call",
                            "call_alias": (
                                "%work_item.lisp_frontend_design_delta/"
                                "work_item::run-selected-item-stdlib.v1"
                            ),
                        },
                        {
                            "kind": "call",
                            "call_alias": (
                                "%stdlib_adapters.lisp_frontend_design_delta/"
                                "stdlib_adapters::draft-design-gap-stdlib.v1"
                            ),
                        },
                        {
                            "kind": "call",
                            "call_alias": (
                                "lisp_frontend_design_delta/selector::select-next-action"
                            ),
                        },
                    ],
                }
            ],
        },
    )

    reasons = module._parent_loop_control_reasons(
        target=target,
        compile_payload={"build_root": str(build_root)},
        build_manifest={"artifact_paths": {"core_workflow_ast": str(core_ast_path)}},
        repo_root=tmp_path,
    )

    assert reasons == ["parent drain entrypoint does not own loop control"]


def test_load_parity_targets_preserves_runtime_audit_artifacts(tmp_path: Path) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    payload["targets"][0] = _design_delta_parent_target_entry(payload["targets"][0])
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)

    target = module.load_parity_targets(manifest_path)[0]

    assert target.runtime_audit_artifacts == (
        {
            "artifact_id": "drain_status_transition_audit",
            "path": (
                "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/"
                "runtime-audits/design_delta_parent_drain_transition_audit.jsonl"
            ),
            "transition_name": "lisp_frontend_design_delta/transitions::write-drain-status-runtime-native",
            "resource_kind": "drain-run-state",
        },
        {
            "artifact_id": "terminal_work_item_transition_audit",
            "path": (
                "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/"
                "runtime-audits/design_delta_parent_drain_transition_audit.jsonl"
            ),
            "transition_name": "lisp_frontend_design_delta/transitions::record-terminal-work-item",
            "resource_kind": "drain-run-state",
        },
        {
            "artifact_id": "blocked_recovery_transition_audit",
            "path": (
                "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/"
                "runtime-audits/design_delta_parent_drain_transition_audit.jsonl"
            ),
            "transition_name": "lisp_frontend_design_delta/transitions::record-blocked-recovery-outcome-stdlib",
            "resource_kind": "drain-run-state",
        },
    )


def test_design_delta_parent_drain_target_rejects_leaf_only_evidence_for_promotable(
    tmp_path: Path,
) -> None:
    module = _parity_module()
    manifest_payload = _valid_manifest_payload()
    manifest_payload["targets"][0] = _design_delta_parent_target_entry(
        manifest_payload["targets"][0]
    )
    manifest_path = _write_json(tmp_path / "parity_targets.json", manifest_payload)
    target = module.load_parity_targets(manifest_path)[0]
    output_root = tmp_path / "artifacts" / "work" / "parity"
    report = _materialize_gate_report(
        tmp_path,
        manifest_path=manifest_path,
        target_entry=manifest_payload["targets"][0],
        target_index=0,
        output_root=output_root,
    )
    report["promotion_eligibility"] = dict(target.promotion_eligibility)
    _add_parent_family_identity(report)
    report["non_regressive"] = False

    gate_row = module._validate_report_for_gate(
        report,
        target=target,
        targets_file=manifest_path,
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )
    gate = module.render_gate_evaluation(
        gate_rows=[gate_row],
        gate_mode="require_promotable",
        targets_file=manifest_path,
        selected_targets=["design_delta_parent_drain"],
        repo_root=tmp_path,
    )

    assert gate_row.non_regressive is False
    assert gate["overall_pass"] is False


def test_design_delta_parent_drain_non_regressive_still_not_promotable(
    tmp_path: Path,
) -> None:
    module = _parity_module()
    manifest_payload = _valid_manifest_payload()
    manifest_payload["targets"][0] = _design_delta_parent_target_entry(
        manifest_payload["targets"][0]
    )
    manifest_path = _write_json(tmp_path / "parity_targets.json", manifest_payload)
    target = module.load_parity_targets(manifest_path)[0]
    output_root = tmp_path / "artifacts" / "work" / "parity"
    report = _materialize_gate_report(
        tmp_path,
        manifest_path=manifest_path,
        target_entry=manifest_payload["targets"][0],
        target_index=0,
        output_root=output_root,
    )
    report["promotion_eligibility"] = dict(target.promotion_eligibility)
    _add_parent_family_evidence(report, repo_root=tmp_path)
    report["non_regressive"] = module.compute_non_regressive(
        report,
        today=date(2026, 6, 2),
    )

    gate_row = module._validate_report_for_gate(
        report,
        target=target,
        targets_file=manifest_path,
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )
    non_regressive_gate = module.render_gate_evaluation(
        gate_rows=[gate_row],
        gate_mode="require_non_regressive",
        targets_file=manifest_path,
        selected_targets=["design_delta_parent_drain"],
        repo_root=tmp_path,
    )
    promotable_gate = module.render_gate_evaluation(
        gate_rows=[gate_row],
        gate_mode="require_promotable",
        targets_file=manifest_path,
        selected_targets=["design_delta_parent_drain"],
        repo_root=tmp_path,
    )

    assert gate_row.non_regressive is True
    assert non_regressive_gate["overall_pass"] is True
    assert promotable_gate["overall_pass"] is False


def test_run_parity_target_records_selected_boundary_projection_split(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)
    target = module.load_parity_targets(manifest_path)[0]

    candidate_path = tmp_path / str(target.candidate)
    yaml_primary_path = tmp_path / str(target.yaml_primary)
    _write_text(candidate_path, "(workflow-lisp)\n")
    _write_text(yaml_primary_path, "steps: []\n")

    build_root = tmp_path / "build"
    build_root.mkdir(parents=True, exist_ok=True)
    _write_json(
        build_root / "core_workflow_ast.json",
        {
            "body": [
                {
                    "kind": "repeat_until",
                    "statements": [
                        {
                            "kind": "call",
                            "call_alias": "lisp_frontend_design_delta/selector::select-next-work",
                        },
                        {
                            "kind": "call",
                            "call_alias": "%drain.lisp_frontend_design_delta/drain::project-selector-action.v1",
                        },
                        {
                            "kind": "call",
                            "call_alias": "lisp_frontend_design_delta/work_item::run-work-item",
                        },
                        {
                            "kind": "call",
                            "call_alias": (
                                "lisp_frontend_design_delta/design_gap_architect::"
                                "draft-design-gap-architecture"
                            ),
                        },
                    ],
                }
            ]
        },
    )
    for artifact_name in ("semantic_ir", "source_map"):
        (build_root / f"{artifact_name}.json").write_text("{}", encoding="utf-8")
    (build_root / "workflow_boundary_projection.json").write_text(
        json.dumps(
            {
                "workflows": [
                    {
                        "workflow_name": "design_plan_impl_review_stack_v2_call::design-plan-impl-stack",
                        "display_name": "design-plan-impl-stack",
                        "boundary": {
                            "public_input_names": ["backlog_item", "execution_report", "progress_report"],
                            "private_runtime_context_bindings": [
                                {
                                    "binding_id": "phase-ctx",
                                    "source_param_name": "phase-ctx",
                                    "context_family": "PhaseCtx",
                                    "bridge_class": "runtime_owned_context",
                                    "generated_input_names": [
                                        "phase-ctx__phase-name",
                                        "phase-ctx__state-root",
                                    ],
                                }
                            ],
                            "private_managed_write_root_inputs": ["__write_root__selection_bundle"],
                            "private_compatibility_bridge_inputs": ["compatibility__legacy_state_root"],
                        },
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_json(
        build_root / "manifest.json",
        {
            "shared_validation_status": "validated",
            "compiled_workflow_checksum": "sha256:compiled-workflow",
            "artifact_paths": {
                "core_workflow_ast": str(build_root / "core_workflow_ast.json"),
                "semantic_ir": str(build_root / "semantic_ir.json"),
                "source_map": str(build_root / "source_map.json"),
                "workflow_boundary_projection": str(build_root / "workflow_boundary_projection.json"),
            },
            "artifact_status": {
                "core_workflow_ast": "emitted",
                "semantic_ir": "emitted",
                "source_map": "emitted",
                "workflow_boundary_projection": "emitted",
            },
        },
    )

    def _fake_run_command(
        command: object,
        *,
        role: str,
        repo_root: Path,
        stdout_log: Path,
        stderr_log: Path,
    ):
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        stderr_log.parent.mkdir(parents=True, exist_ok=True)
        stdout = json.dumps({"build_root": str(build_root)}) if role == "compile" else ""
        stdout_log.write_text(stdout, encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        return module.CommandOutcome(
            status="pass",
            argv=("python", role),
            exit_code=0,
            elapsed_seconds=0.01,
            stdout=stdout,
            stderr="",
        )

    monkeypatch.setattr(module, "_run_command", _fake_run_command)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["workflow_boundary_projection"] == {
        "workflow_name": "design_plan_impl_review_stack_v2_call::design-plan-impl-stack",
        "display_name": "design-plan-impl-stack",
        "public_input_names": ["backlog_item", "execution_report", "progress_report"],
        "private_runtime_context_bindings": [
            {
                "binding_id": "phase-ctx",
                "source_param_name": "phase-ctx",
                "context_family": "PhaseCtx",
                "bridge_class": "runtime_owned_context",
                "generated_input_names": [
                    "phase-ctx__phase-name",
                    "phase-ctx__state-root",
                ],
            }
        ],
        "private_managed_write_root_inputs": ["__write_root__selection_bundle"],
        "private_compatibility_bridge_inputs": ["compatibility__legacy_state_root"],
    }


def test_load_selected_workflow_boundary_projection_ignores_root_return_kind(
    tmp_path: Path,
) -> None:
    """`return_kind: "root"` (native-return wave 1) is additive and unread by
    the migration-parity boundary-projection loader: the extracted payload is
    identical to the equivalent record/union boundary row, with or without
    the new field present."""
    module = _parity_module()
    payload = _valid_manifest_payload()
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)
    target = module.load_parity_targets(manifest_path)[0]

    build_root = tmp_path / "build"
    build_root.mkdir(parents=True, exist_ok=True)
    boundary_row = {
        "workflow_name": target.entry_workflow,
        "display_name": "entry",
        "return_kind": "root",
        "boundary": {
            "public_input_names": ["report_path"],
            "private_runtime_context_bindings": [],
            "private_managed_write_root_inputs": [],
            "private_compatibility_bridge_inputs": [],
        },
    }
    (build_root / "workflow_boundary_projection.json").write_text(
        json.dumps({"workflows": [boundary_row]}), encoding="utf-8"
    )
    build_manifest = {
        "artifact_paths": {
            "workflow_boundary_projection": str(
                build_root / "workflow_boundary_projection.json"
            ),
        },
    }

    with_root_kind = module._load_selected_workflow_boundary_projection(
        target=target,
        build_manifest=build_manifest,
        build_root=build_root,
        repo_root=tmp_path,
    )

    del boundary_row["return_kind"]
    (build_root / "workflow_boundary_projection.json").write_text(
        json.dumps({"workflows": [boundary_row]}), encoding="utf-8"
    )
    without_root_kind = module._load_selected_workflow_boundary_projection(
        target=target,
        build_manifest=build_manifest,
        build_root=build_root,
        repo_root=tmp_path,
    )

    assert with_root_kind == without_root_kind
    assert with_root_kind == {
        "workflow_name": target.entry_workflow,
        "display_name": "entry",
        "public_input_names": ["report_path"],
        "private_runtime_context_bindings": [],
        "private_managed_write_root_inputs": [],
        "private_compatibility_bridge_inputs": [],
    }


def test_run_parity_target_records_parent_family_evidence_roles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    payload["targets"][0] = _design_delta_parent_target_entry(payload["targets"][0])
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)
    target = module.load_parity_targets(manifest_path)[0]

    _write_text(tmp_path / str(target.candidate), "(workflow-lisp)\n")
    _write_text(tmp_path / str(target.yaml_primary), "steps: []\n")
    checked_in_commands = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json"
        ).read_text(encoding="utf-8")
    )
    _write_json(tmp_path / str(target.command_boundaries_file), checked_in_commands)
    build_root = _write_design_delta_g0_build_manifest(tmp_path)
    runtime_audit_path = tmp_path / target.runtime_audit_artifacts[0]["path"]
    _write_text(
        runtime_audit_path,
        "".join(
            json.dumps(
                {
                    "transition_name": artifact["transition_name"],
                    "resource_kind": artifact["resource_kind"],
                    "outcome_code": "committed",
                }
            )
            + "\n"
            for artifact in target.runtime_audit_artifacts
        ),
    )
    for artifact in target.family_evidence_artifacts:
        payload = {
            "schema_version": artifact["schema_version"],
            "artifact_id": artifact["artifact_id"],
            "workflow_family": "design_delta_parent_drain",
            "overall_status": "pass",
            "all_passed": True,
            "adapters": (
                {
                    "project_lisp_frontend_selector_action": {
                        "status": "pass",
                        "comparison_mapping_id": "selector_action_projection.v1",
                        "cases": [],
                    }
                }
                if artifact["evidence_role"] == "projection_retirement_parity"
                else {
                    "finalize_lisp_frontend_drain_summary": {
                        "status": "pass",
                        "comparison_mapping_id": "drain_summary_view.v1",
                        "cases": [],
                    }
                }
            ),
        }
        _write_json(tmp_path / str(artifact["path"]), payload)

    def _fake_run_command(
        command: object,
        *,
        role: str,
        repo_root: Path,
        stdout_log: Path,
        stderr_log: Path,
    ):
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        stderr_log.parent.mkdir(parents=True, exist_ok=True)
        stdout = json.dumps({"build_root": str(build_root)}) if role == "compile" else ""
        stdout_log.write_text(stdout, encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        return module.CommandOutcome(
            status="pass",
            argv=("python", role),
            exit_code=0,
            elapsed_seconds=0.01,
            stdout=stdout,
            stderr="",
        )

    monkeypatch.setattr(module, "_run_command", _fake_run_command)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["route_identity"] == {
        "readiness_label": "parent_callable_candidate",
        "lowering_route": "wcc_m4",
        "lowering_schema_version": 2,
    }
    for role in target.required_family_evidence_roles:
        assert report["evidence"][role]["status"] == "pass"
    justifications = report["evidence"]["boundary_artifact_justifications"]
    assert justifications["boundary_justifications"] == [
        {
            "boundary_id": "lisp_frontend_design_delta/drain::drain",
            "reason": "public_boundary_identity",
            "parity_constrained": True,
            "readiness_label": "parent_callable_candidate",
            "route": "wcc_m4",
            "schema_version": 2,
        }
    ]
    artifact_reasons = {
        item["artifact_id"]: item
        for item in justifications["artifact_justifications"]
    }
    assert {
        "core_workflow_ast",
        "semantic_ir",
        "source_map",
        "workflow_boundary_projection",
    }.issubset(artifact_reasons)
    assert all(
        artifact_reasons[name]["reason"] == "parity_comparison"
        and artifact_reasons[name]["parity_constrained"] is True
        for name in (
            "core_workflow_ast",
            "semantic_ir",
            "source_map",
            "workflow_boundary_projection",
        )
    )
    assert report["non_regressive"] is True


def test_run_parity_target_rejects_dispatcher_only_parent_loop_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    payload["targets"][0] = _design_delta_parent_target_entry(payload["targets"][0])
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)
    target = module.load_parity_targets(manifest_path)[0]

    _write_text(tmp_path / str(target.candidate), "(workflow-lisp)\n")
    _write_text(tmp_path / str(target.yaml_primary), "steps: []\n")
    command_manifest = {
        helper: {
            "kind": "certified_adapter",
            "stable_command": ["python", f"{helper}.py"],
            "behavior_class": "resource_transition",
            "input_signature": [{"name": "run_state_path", "type_name": "RunStatePath"}],
            "effects": ["structured_result", "resource_transition", "ledger_update"],
            "fixture_ids": [f"{helper}_ok"],
            "negative_fixture_ids": [f"{helper}_bad"],
            "owner_module": "lisp_frontend_design_delta/drain",
            "replacement_path": "runtime-native transition",
            "invocation_protocol": "json_object_positional_arg",
            "state_writes": ["run_state_path"] if helper != "finalize_lisp_frontend_drain_summary" else [],
        }
        for helper in (
            "record_terminal_work_item",
            "record_blocked_recovery_outcome",
            "write_lisp_frontend_drain_status",
            "finalize_lisp_frontend_drain_summary",
        )
    }
    _write_json(tmp_path / str(target.command_boundaries_file), command_manifest)
    build_root = tmp_path / "build"
    build_root.mkdir(parents=True, exist_ok=True)
    _write_json(
        build_root / "core_workflow_ast.json",
        {
            "body": [
                {
                    "kind": "call",
                    "call_alias": "lisp_frontend_design_delta/drain::drain-loop-proof",
                },
                {
                    "kind": "call",
                    "call_alias": "lisp_frontend_design_delta/selector::select-next-action",
                },
            ]
        },
    )
    for artifact_name in ("semantic_ir", "source_map"):
        (build_root / f"{artifact_name}.json").write_text("{}", encoding="utf-8")
    (build_root / "workflow_boundary_projection.json").write_text(
        json.dumps(
            {
                "workflows": [
                    {
                        "workflow_name": "lisp_frontend_design_delta/drain::drain",
                        "display_name": "lisp_frontend_design_delta/drain::drain",
                        "boundary": {
                            "public_input_names": ["steering_path", "target_design_path"],
                            "private_runtime_context_bindings": [
                                {
                                    "binding_id": "phase-ctx",
                                    "source_param_name": "phase-ctx",
                                    "context_family": "PhaseCtx",
                                    "bridge_class": "runtime_owned_context",
                                    "generated_input_names": ["phase-ctx__run-id"],
                                }
                            ],
                            "private_managed_write_root_inputs": ["__write_root__drain_summary"],
                            "private_compatibility_bridge_inputs": ["manifest_path"],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _write_json(
        build_root / "manifest.json",
        {
            "shared_validation_status": "validated",
            "lowering_route": "wcc_m4",
            "lowering_schema_version": 2,
            "compiled_workflow_checksum": "sha256:compiled-workflow",
            "artifact_paths": {
                "core_workflow_ast": str(build_root / "core_workflow_ast.json"),
                "semantic_ir": str(build_root / "semantic_ir.json"),
                "source_map": str(build_root / "source_map.json"),
                "workflow_boundary_projection": str(build_root / "workflow_boundary_projection.json"),
            },
            "artifact_status": {
                "core_workflow_ast": "emitted",
                "semantic_ir": "emitted",
                "source_map": "emitted",
                "workflow_boundary_projection": "emitted",
            },
        },
    )

    def _fake_run_command(
        command: object,
        *,
        role: str,
        repo_root: Path,
        stdout_log: Path,
        stderr_log: Path,
    ):
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        stderr_log.parent.mkdir(parents=True, exist_ok=True)
        stdout = json.dumps({"build_root": str(build_root)}) if role == "compile" else ""
        stdout_log.write_text(stdout, encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        return module.CommandOutcome(
            status="pass",
            argv=("python", role),
            exit_code=0,
            elapsed_seconds=0.01,
            stdout=stdout,
            stderr="",
        )

    monkeypatch.setattr(module, "_run_command", _fake_run_command)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["evidence"]["parent_callable_compile"]["status"] == "fail"
    assert "parent drain entrypoint does not own loop control" in " ".join(
        report["evidence"]["parent_callable_compile"]["reasons"]
    )
    assert report["non_regressive"] is False


def test_run_parity_target_rejects_missing_parent_route_identity_from_compile_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    payload["targets"][0] = _design_delta_parent_target_entry(payload["targets"][0])
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)
    target = module.load_parity_targets(manifest_path)[0]

    _write_text(tmp_path / str(target.candidate), "(workflow-lisp)\n")
    _write_text(tmp_path / str(target.yaml_primary), "steps: []\n")
    command_manifest = {
        helper: {
            "kind": "certified_adapter",
            "stable_command": ["python", f"{helper}.py"],
            "behavior_class": "resource_transition",
            "input_signature": [{"name": "run_state_path", "type_name": "RunStatePath"}],
            "effects": ["structured_result", "resource_transition", "ledger_update"],
            "fixture_ids": [f"{helper}_ok"],
            "negative_fixture_ids": [f"{helper}_bad"],
            "owner_module": "lisp_frontend_design_delta/drain",
            "replacement_path": "runtime-native transition",
            "invocation_protocol": "json_object_positional_arg",
            "state_writes": ["run_state_path"] if helper != "finalize_lisp_frontend_drain_summary" else [],
        }
        for helper in (
            "record_terminal_work_item",
            "record_blocked_recovery_outcome",
            "write_lisp_frontend_drain_status",
            "finalize_lisp_frontend_drain_summary",
        )
    }
    _write_json(tmp_path / str(target.command_boundaries_file), command_manifest)
    build_root = tmp_path / "build"
    build_root.mkdir(parents=True, exist_ok=True)
    for artifact_name in ("core_workflow_ast", "semantic_ir", "source_map"):
        (build_root / f"{artifact_name}.json").write_text("{}", encoding="utf-8")
    (build_root / "workflow_boundary_projection.json").write_text(
        json.dumps(
            {
                "workflows": [
                    {
                        "workflow_name": "lisp_frontend_design_delta/drain::drain",
                        "display_name": "lisp_frontend_design_delta/drain::drain",
                        "boundary": {
                            "public_input_names": ["steering_path", "target_design_path"],
                            "private_runtime_context_bindings": [],
                            "private_managed_write_root_inputs": [],
                            "private_compatibility_bridge_inputs": [],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _write_json(
        build_root / "manifest.json",
        {
            "shared_validation_status": "validated",
            "lowering_schema_version": 2,
            "compiled_workflow_checksum": "sha256:compiled-workflow",
            "artifact_paths": {
                "core_workflow_ast": str(build_root / "core_workflow_ast.json"),
                "semantic_ir": str(build_root / "semantic_ir.json"),
                "source_map": str(build_root / "source_map.json"),
                "workflow_boundary_projection": str(build_root / "workflow_boundary_projection.json"),
            },
            "artifact_status": {
                "core_workflow_ast": "emitted",
                "semantic_ir": "emitted",
                "source_map": "emitted",
                "workflow_boundary_projection": "emitted",
            },
        },
    )

    def _fake_run_command(
        command: object,
        *,
        role: str,
        repo_root: Path,
        stdout_log: Path,
        stderr_log: Path,
    ):
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        stderr_log.parent.mkdir(parents=True, exist_ok=True)
        stdout = json.dumps({"build_root": str(build_root)}) if role == "compile" else ""
        stdout_log.write_text(stdout, encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        return module.CommandOutcome(
            status="pass",
            argv=("python", role),
            exit_code=0,
            elapsed_seconds=0.01,
            stdout=stdout,
            stderr="",
        )

    monkeypatch.setattr(module, "_run_command", _fake_run_command)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["route_identity"]["lowering_route"] is None
    assert report["evidence"]["route_identity"]["status"] == "fail"
    assert report["non_regressive"] is False


def test_render_parity_index_derives_primary_surface() -> None:
    module = _parity_module()
    report = _valid_report_payload()
    gate_row = module.ValidatedGateRow(
        workflow_family="design_plan_impl_stack",
        report=report,
        report_valid=True,
        evidence_complete=True,
        non_regressive=True,
        eligible_for_primary_surface=True,
        primary_surface="orc",
        reasons=tuple(),
        target_identity=report["target_identity"],
    )

    index = module.render_parity_index([gate_row])

    assert index["schema_version"] == "workflow_lisp_migration_parity_index.v2"
    assert index["targets"][0]["workflow_family"] == "design_plan_impl_stack"
    assert index["targets"][0]["non_regressive"] is True
    assert index["targets"][0]["primary_surface"] == "orc"


def test_render_parity_index_keeps_yaml_for_ineligible_target() -> None:
    module = _parity_module()
    report = _valid_report_payload(workflow_family="cycle_guard_demo")
    report["promotion_eligibility"] = {
        "eligible_for_primary_surface": False,
        "blocked_reason": "demo-only until native bounded-loop parity is designed",
    }
    gate_row = module.ValidatedGateRow(
        workflow_family="cycle_guard_demo",
        report=report,
        report_valid=True,
        evidence_complete=True,
        non_regressive=True,
        eligible_for_primary_surface=False,
        primary_surface="yaml",
        reasons=("eligible_for_primary_surface=false",),
        target_identity=report["target_identity"],
    )

    index = module.render_parity_index([gate_row])

    assert index["targets"][0]["workflow_family"] == "cycle_guard_demo"
    assert index["targets"][0]["non_regressive"] is True
    assert index["targets"][0]["primary_surface"] == "yaml"


def test_derive_primary_surface_keeps_yaml_for_non_promotable_non_regressive_target() -> None:
    module = _parity_module()

    assert (
        module.derive_primary_surface(
            non_regressive=True,
            eligible_for_primary_surface=False,
        )
        == "yaml"
    )


def test_rendered_parity_surfaces_do_not_publish_hidden_managed_write_root_inputs() -> None:
    module = _parity_module()
    report = _valid_report_payload()
    gate_row = module.ValidatedGateRow(
        workflow_family="design_plan_impl_stack",
        report=report,
        report_valid=True,
        evidence_complete=True,
        non_regressive=True,
        eligible_for_primary_surface=True,
        primary_surface="orc",
        reasons=tuple(),
        target_identity=report["target_identity"],
    )

    markdown = module.render_parity_markdown(report)
    index = module.render_parity_index([gate_row])

    assert "__write_root__" not in markdown
    assert "__write_root__" not in json.dumps(index, sort_keys=True)


def test_schema_version_mismatch_for_strict_gate(tmp_path: Path) -> None:
    module, manifest_path, target, _output_root, report = _strict_gate_fixture(tmp_path)
    report["schema_version"] = "workflow_lisp_migration_parity_report.v1"

    with pytest.raises(ValueError, match="schema_version"):
        module._validate_report_for_gate(
            report,
            target=target,
            targets_file=manifest_path,
            repo_root=tmp_path,
            today=date(2026, 6, 2),
        )


def test_report_with_primary_surface_field(tmp_path: Path) -> None:
    module, manifest_path, target, _output_root, report = _strict_gate_fixture(tmp_path)
    report["primary_surface"] = "orc"

    with pytest.raises(ValueError, match="primary_surface"):
        module._validate_report_for_gate(
            report,
            target=target,
            targets_file=manifest_path,
            repo_root=tmp_path,
            today=date(2026, 6, 2),
        )


def test_target_manifest_sha_mismatch(tmp_path: Path) -> None:
    module, manifest_path, target, _output_root, report = _strict_gate_fixture(tmp_path)
    report["target_identity"]["target_manifest_sha256"] = "sha256:stale-manifest"

    with pytest.raises(ValueError, match="target_manifest_sha256"):
        module._validate_report_for_gate(
            report,
            target=target,
            targets_file=manifest_path,
            repo_root=tmp_path,
            today=date(2026, 6, 2),
        )


def test_candidate_sha_mismatch(tmp_path: Path) -> None:
    module, manifest_path, target, _output_root, report = _strict_gate_fixture(tmp_path)
    report["target_identity"]["candidate_sha256"] = "sha256:stale-candidate"

    with pytest.raises(ValueError, match="candidate_sha256"):
        module._validate_report_for_gate(
            report,
            target=target,
            targets_file=manifest_path,
            repo_root=tmp_path,
            today=date(2026, 6, 2),
        )


def test_compile_manifest_sha_mismatch(tmp_path: Path) -> None:
    module, manifest_path, target, _output_root, report = _strict_gate_fixture(tmp_path)
    report["evidence_freshness"]["compile_manifest_sha256"] = "sha256:stale-compile-manifest"

    with pytest.raises(ValueError, match="compile_manifest_sha256"):
        module._validate_report_for_gate(
            report,
            target=target,
            targets_file=manifest_path,
            repo_root=tmp_path,
            today=date(2026, 6, 2),
        )


def test_non_regressive_recomputation_mismatch(tmp_path: Path) -> None:
    module, manifest_path, target, _output_root, report = _strict_gate_fixture(tmp_path)
    report["non_regressive"] = False

    with pytest.raises(ValueError, match="non_regressive"):
        module._validate_report_for_gate(
            report,
            target=target,
            targets_file=manifest_path,
            repo_root=tmp_path,
            today=date(2026, 6, 2),
        )


def test_missing_tool_version_for_strict_gate(tmp_path: Path) -> None:
    module, manifest_path, target, _output_root, report = _strict_gate_fixture(tmp_path)
    report.pop("tool_version")

    with pytest.raises(ValueError, match="tool_version"):
        module._validate_report_for_gate(
            report,
            target=target,
            targets_file=manifest_path,
            repo_root=tmp_path,
            today=date(2026, 6, 2),
        )


def test_target_identity_rejects_extra_keys(tmp_path: Path) -> None:
    module, manifest_path, target, _output_root, report = _strict_gate_fixture(tmp_path)
    report["target_identity"]["unexpected"] = "extra"

    with pytest.raises(ValueError, match="target_identity"):
        module._validate_report_for_gate(
            report,
            target=target,
            targets_file=manifest_path,
            repo_root=tmp_path,
            today=date(2026, 6, 2),
        )


def test_missing_required_evidence_marks_gate_row_incomplete(tmp_path: Path) -> None:
    module, manifest_path, target, _output_root, report = _strict_gate_fixture(tmp_path)
    del report["evidence"]["resume_parity"]
    report["non_regressive"] = False

    gate_row = module._validate_report_for_gate(
        report,
        target=target,
        targets_file=manifest_path,
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert gate_row.evidence_complete is False
    assert gate_row.non_regressive is False
    assert "missing required evidence role `resume_parity`" in gate_row.reasons


def test_non_passing_required_compile_artifact_marks_gate_row_incomplete(tmp_path: Path) -> None:
    module, manifest_path, target, _output_root, report = _strict_gate_fixture(tmp_path)
    report["compile_artifacts"]["required"]["semantic_ir"]["status"] = "missing"
    report["evidence_freshness"]["required_artifacts"]["semantic_ir"]["status"] = "missing"
    report["non_regressive"] = False

    gate_row = module._validate_report_for_gate(
        report,
        target=target,
        targets_file=manifest_path,
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert gate_row.evidence_complete is False
    assert gate_row.non_regressive is False
    assert "required compile artifact `semantic_ir` is not passing" in gate_row.reasons


def test_incomplete_evidence_keeps_view_primary_surface_but_not_gate_primary_surface(
    tmp_path: Path,
) -> None:
    module, manifest_path, target, _output_root, report = _strict_gate_fixture(tmp_path)
    del report["evidence_freshness"]["compile_manifest_sha256"]

    gate_row = module._validate_report_for_gate(
        report,
        target=target,
        targets_file=manifest_path,
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    markdown = module.render_parity_markdown(report)
    index = module.render_parity_index([gate_row])
    gate_evaluation = module.render_gate_evaluation(
        gate_rows=[gate_row],
        gate_mode="require_non_regressive",
        targets_file=manifest_path,
        selected_targets=[gate_row.workflow_family],
        repo_root=tmp_path,
    )

    assert gate_row.evidence_complete is False
    assert "- Primary surface: `orc`" in markdown
    assert index["targets"][0]["primary_surface"] == "orc"
    assert gate_evaluation["results"][0]["primary_surface"] is None


def test_gate_evaluation_distinguishes_non_regressive_from_promotable(tmp_path: Path) -> None:
    module, manifest_path, target, output_root, promotable_report = _strict_gate_fixture(tmp_path)
    promotable_row = module._validate_report_for_gate(
        promotable_report,
        target=target,
        targets_file=manifest_path,
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    non_promotable_report = json.loads(json.dumps(promotable_report))
    non_promotable_report["workflow_family"] = "cycle_guard_demo"
    non_promotable_report["candidate"] = "workflows/examples/cycle_guard_demo.orc"
    non_promotable_report["yaml_primary"] = "workflows/examples/cycle_guard_demo.yaml"
    non_promotable_report["report_path"] = (
        output_root / "cycle_guard_demo.json"
    ).relative_to(tmp_path).as_posix()
    non_promotable_report["promotion_eligibility"] = {
        "eligible_for_primary_surface": False,
        "blocked_reason": "demo-only until parity closes",
    }
    non_promotable_report["target_identity"] = {
        **dict(promotable_report["target_identity"]),
        "workflow_family": "cycle_guard_demo",
        "candidate_path": "workflows/examples/cycle_guard_demo.orc",
        "yaml_primary_path": "workflows/examples/cycle_guard_demo.yaml",
    }
    non_promotable_row = module.ValidatedGateRow(
        workflow_family="cycle_guard_demo",
        report=non_promotable_report,
        report_valid=True,
        evidence_complete=True,
        non_regressive=True,
        eligible_for_primary_surface=False,
        primary_surface="yaml",
        reasons=("eligible_for_primary_surface=false",),
        target_identity=non_promotable_report["target_identity"],
    )

    non_regressive_gate = module.render_gate_evaluation(
        gate_rows=[non_promotable_row, promotable_row],
        gate_mode="require_non_regressive",
        targets_file=manifest_path,
        selected_targets=["cycle_guard_demo", "design_plan_impl_stack"],
        repo_root=tmp_path,
    )
    promotable_gate = module.render_gate_evaluation(
        gate_rows=[non_promotable_row, promotable_row],
        gate_mode="require_promotable",
        targets_file=manifest_path,
        selected_targets=["cycle_guard_demo", "design_plan_impl_stack"],
        repo_root=tmp_path,
    )

    assert non_regressive_gate["overall_pass"] is True
    assert promotable_gate["overall_pass"] is False
    assert non_regressive_gate["results"][0]["primary_surface"] == "yaml"
    assert non_regressive_gate["results"][1]["primary_surface"] == "orc"


def test_gate_evaluation_strict_modes_only_gate_selected_targets(tmp_path: Path) -> None:
    module, manifest_path, target, output_root, promotable_report = _strict_gate_fixture(tmp_path)
    selected_row = module._validate_report_for_gate(
        promotable_report,
        target=target,
        targets_file=manifest_path,
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    unselected_report = json.loads(json.dumps(promotable_report))
    unselected_report["workflow_family"] = "cycle_guard_demo"
    unselected_report["candidate"] = "workflows/examples/cycle_guard_demo.orc"
    unselected_report["yaml_primary"] = "workflows/examples/cycle_guard_demo.yaml"
    unselected_report["report_path"] = (
        output_root / "cycle_guard_demo.json"
    ).relative_to(tmp_path).as_posix()
    unselected_report["promotion_eligibility"] = {
        "eligible_for_primary_surface": False,
        "blocked_reason": "demo-only until parity closes",
    }
    unselected_report["target_identity"] = {
        **dict(promotable_report["target_identity"]),
        "workflow_family": "cycle_guard_demo",
        "candidate_path": "workflows/examples/cycle_guard_demo.orc",
        "yaml_primary_path": "workflows/examples/cycle_guard_demo.yaml",
    }
    unselected_row = module.ValidatedGateRow(
        workflow_family="cycle_guard_demo",
        report=unselected_report,
        report_valid=True,
        evidence_complete=True,
        non_regressive=True,
        eligible_for_primary_surface=False,
        primary_surface="yaml",
        reasons=("eligible_for_primary_surface=false",),
        target_identity=unselected_report["target_identity"],
    )

    promotable_gate = module.render_gate_evaluation(
        gate_rows=[unselected_row, selected_row],
        gate_mode="require_promotable",
        targets_file=manifest_path,
        selected_targets=["design_plan_impl_stack"],
        repo_root=tmp_path,
    )
    non_regressive_gate = module.render_gate_evaluation(
        gate_rows=[unselected_row, selected_row],
        gate_mode="require_non_regressive",
        targets_file=manifest_path,
        selected_targets=["design_plan_impl_stack"],
        repo_root=tmp_path,
    )

    assert promotable_gate["overall_pass"] is True
    assert non_regressive_gate["overall_pass"] is True
    assert [row["workflow_family"] for row in promotable_gate["results"]] == [
        "cycle_guard_demo",
        "design_plan_impl_stack",
    ]
    assert promotable_gate["selected_target_identities"] == [
        dict(selected_row.target_identity)
    ]


def test_gate_evaluation_marks_stale_reused_report_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    second_target = json.loads(json.dumps(payload["targets"][0]))
    second_target.update(
        {
            "workflow_family": "cycle_guard_demo",
            "candidate": "workflows/examples/cycle_guard_demo.orc",
            "yaml_primary": "workflows/examples/cycle_guard_demo.yaml",
            "entry_workflow": "cycle-guard-demo",
        }
    )
    payload["targets"].append(second_target)
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)
    module.load_parity_targets(manifest_path)

    for target_entry in payload["targets"]:
        _write_text(tmp_path / str(target_entry["candidate"]), "(workflow-lisp)\n")
        _write_text(tmp_path / str(target_entry["yaml_primary"]), "steps: []\n")

    output_root = tmp_path / "parity"
    stale_report = _set_report_path(
        _valid_report_payload(workflow_family="cycle_guard_demo"),
        repo_root=tmp_path,
        output_root=output_root,
    )
    stale_report["target_identity"]["target_manifest_path"] = manifest_path.relative_to(tmp_path).as_posix()
    stale_report["target_identity"]["target_manifest_sha256"] = _sha256_file(manifest_path)
    stale_report["target_identity"]["target_index"] = 1
    stale_report["target_identity"]["workflow_family"] = "cycle_guard_demo"
    stale_report["target_identity"]["candidate_path"] = "workflows/examples/cycle_guard_demo.orc"
    stale_report["target_identity"]["candidate_sha256"] = "sha256:stale-candidate"
    stale_report["target_identity"]["yaml_primary_path"] = "workflows/examples/cycle_guard_demo.yaml"
    stale_report["target_identity"]["entry_workflow"] = "cycle-guard-demo"
    _write_json(output_root / "cycle_guard_demo.json", stale_report)

    refreshed_report = _set_report_path(
        _valid_report_payload(workflow_family="design_plan_impl_stack"),
        repo_root=tmp_path,
        output_root=output_root,
    )
    refreshed_report["target_identity"]["target_manifest_path"] = manifest_path.relative_to(tmp_path).as_posix()
    refreshed_report["target_identity"]["target_manifest_sha256"] = _sha256_file(manifest_path)
    refreshed_report["target_identity"]["candidate_path"] = payload["targets"][0]["candidate"]
    refreshed_report["target_identity"]["candidate_sha256"] = _sha256_file(
        tmp_path / str(payload["targets"][0]["candidate"])
    )
    refreshed_report["target_identity"]["yaml_primary_path"] = payload["targets"][0]["yaml_primary"]

    def _fake_run_parity_target(*args: object, **kwargs: object) -> dict[str, object]:
        return refreshed_report

    monkeypatch.setattr(module, "run_parity_target", _fake_run_parity_target)

    with pytest.raises(ValueError, match="candidate_sha256"):
        module.run_migration_parity(
            targets_file=manifest_path,
            output_root=output_root,
            selected_targets=["design_plan_impl_stack"],
            repo_root=tmp_path,
        )


def test_run_migration_parity_rejects_reused_report_with_missing_evidence_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    second_target = json.loads(json.dumps(payload["targets"][0]))
    second_target.update(
        {
            "workflow_family": "cycle_guard_demo",
            "candidate": "workflows/examples/cycle_guard_demo.orc",
            "yaml_primary": "workflows/examples/cycle_guard_demo.yaml",
            "entry_workflow": "cycle-guard-demo",
        }
    )
    payload["targets"].append(second_target)
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)

    output_root = tmp_path / "parity"
    reused_report = _materialize_gate_report(
        tmp_path,
        manifest_path=manifest_path,
        target_entry=payload["targets"][1],
        target_index=1,
        output_root=output_root,
    )
    _write_json(output_root / "cycle_guard_demo.json", reused_report)
    missing_log = tmp_path / str(reused_report["command_logs"]["dry_run"]["stdout"])
    missing_log.unlink()

    refreshed_report = _materialize_gate_report(
        tmp_path,
        manifest_path=manifest_path,
        target_entry=payload["targets"][0],
        target_index=0,
        output_root=output_root,
    )

    def _fake_run_parity_target(*args: object, **kwargs: object) -> dict[str, object]:
        return refreshed_report

    monkeypatch.setattr(module, "run_parity_target", _fake_run_parity_target)

    with pytest.raises(ValueError, match="missing stdout log for `dry_run`"):
        module.run_migration_parity(
            targets_file=manifest_path,
            output_root=output_root,
            selected_targets=["design_plan_impl_stack"],
            repo_root=tmp_path,
        )


def test_run_migration_parity_rejects_reused_report_missing_compiled_workflow_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    second_target = json.loads(json.dumps(payload["targets"][0]))
    second_target.update(
        {
            "workflow_family": "cycle_guard_demo",
            "candidate": "workflows/examples/cycle_guard_demo.orc",
            "yaml_primary": "workflows/examples/cycle_guard_demo.yaml",
            "entry_workflow": "cycle-guard-demo",
        }
    )
    payload["targets"].append(second_target)
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)

    output_root = tmp_path / "parity"
    reused_report = _materialize_gate_report(
        tmp_path,
        manifest_path=manifest_path,
        target_entry=payload["targets"][1],
        target_index=1,
        output_root=output_root,
    )
    del reused_report["evidence_freshness"]["compiled_workflow_checksum"]
    _write_json(output_root / "cycle_guard_demo.json", reused_report)

    refreshed_report = _materialize_gate_report(
        tmp_path,
        manifest_path=manifest_path,
        target_entry=payload["targets"][0],
        target_index=0,
        output_root=output_root,
    )

    def _fake_run_parity_target(*args: object, **kwargs: object) -> dict[str, object]:
        return refreshed_report

    monkeypatch.setattr(module, "run_parity_target", _fake_run_parity_target)

    with pytest.raises(ValueError, match="missing compiled_workflow_checksum"):
        module.run_migration_parity(
            targets_file=manifest_path,
            output_root=output_root,
            selected_targets=["design_plan_impl_stack"],
            repo_root=tmp_path,
        )


def test_render_parity_index_uses_validated_gate_rows(tmp_path: Path) -> None:
    module, manifest_path, target, _output_root, report = _strict_gate_fixture(tmp_path)
    gate_row = module._validate_report_for_gate(
        report,
        target=target,
        targets_file=manifest_path,
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    index = module.render_parity_index([gate_row])

    assert index["schema_version"] == "workflow_lisp_migration_parity_index.v2"
    assert index["targets"][0]["workflow_family"] == "design_plan_impl_stack"
    assert index["targets"][0]["report_valid"] is True
    assert index["targets"][0]["evidence_complete"] is True
    assert index["targets"][0]["primary_surface"] == "orc"


def test_render_parity_index_rejects_raw_reports() -> None:
    module = _parity_module()

    with pytest.raises(TypeError, match="ValidatedGateRow"):
        module.render_parity_index([_valid_report_payload()])


def test_run_migration_parity_preserves_unselected_targets_in_aggregate_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    second_target = json.loads(json.dumps(payload["targets"][0]))
    second_target.update(
        {
            "workflow_family": "cycle_guard_demo",
            "candidate": "workflows/examples/cycle_guard_demo.orc",
            "yaml_primary": "workflows/examples/cycle_guard_demo.yaml",
            "entry_workflow": "cycle-guard-demo",
        }
    )
    payload["targets"].append(second_target)
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)
    output_root = tmp_path / "parity"
    output_root.mkdir()
    existing_report = _materialize_gate_report(
        tmp_path,
        manifest_path=manifest_path,
        target_entry=payload["targets"][1],
        target_index=1,
        output_root=output_root,
    )
    _write_json(output_root / "cycle_guard_demo.json", existing_report)

    refreshed_report = _materialize_gate_report(
        tmp_path,
        manifest_path=manifest_path,
        target_entry=payload["targets"][0],
        target_index=0,
        output_root=output_root,
    )

    def _fake_run_parity_target(*args: object, **kwargs: object) -> dict[str, object]:
        return refreshed_report

    monkeypatch.setattr(module, "run_parity_target", _fake_run_parity_target)

    module.run_migration_parity(
        targets_file=manifest_path,
        output_root=output_root,
        selected_targets=["design_plan_impl_stack"],
        repo_root=tmp_path,
    )

    index = json.loads((output_root / "index.json").read_text(encoding="utf-8"))

    assert [row["workflow_family"] for row in index["targets"]] == [
        "cycle_guard_demo",
        "design_plan_impl_stack",
    ]


def test_design_plan_impl_stack_manifest_uses_defaulted_dry_run_and_procedure_first_evidence() -> None:
    payload = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json"
        ).read_text(encoding="utf-8")
    )
    target = next(
        entry for entry in payload["targets"] if entry["workflow_family"] == "design_plan_impl_stack"
    )

    dry_run_argv = target["evidence_commands"]["dry_run"]
    assert dry_run_argv.count("--input") == 7
    assert "brief_path=workflows/examples/inputs/major_project_brief.md" in dry_run_argv

    loop_entry = next(
        entry
        for entry in target["deprecated_yaml_mechanics"]
        if entry["mechanic"] == "full YAML review-revise loop with carried findings extraction"
    )
    assert loop_entry["replacement"] == (
        "family-specific .orc design_plan_impl_stack parity route with typed "
        "review decisions, validated artifacts, and reusable phase-state evidence"
    )
    stale = [
        entry
        for entry in target["deprecated_yaml_mechanics"]
        if entry["mechanic"] == "full YAML review-revise loop with carried findings extraction"
        and not entry.get("replacement")
        and not entry.get("waiver")
    ]
    assert not stale

    retained_run_command = [
        "python",
        "-m",
        "pytest",
        "tests/test_workflow_lisp_key_migrations.py",
        "-k",
        "tracked_plan_phase_retained_run_evidence_replays",
        "-q",
    ]
    for role in (
        "smoke_or_integration",
        "terminal_state_parity",
        "artifact_parity",
        "resume_parity",
    ):
        assert target["evidence_commands"][role] == retained_run_command

    assert target["evidence_commands"]["output_contract_parity"] == [
        "python",
        "-m",
        "pytest",
        "tests/test_workflow_lisp_key_migrations.py",
        "tests/test_workflow_lisp_procedure_first_migrations.py",
        "-k",
        (
            "tracked_plan_phase_retained_run_evidence_replays or "
            "tracked_plan_phase_contract_matches_frozen_pre_migration_baseline"
        ),
        "-q",
    ]

    assert target["baseline_characterization"]["resume_behavior"] == [
        (
            "same-ID post-plan-draft default resume restores the validated prior boundary, "
            "reuses design.draft, design.review, and plan.draft exactly once, and executes "
            "plan.review, implementation.execute, and implementation.review exactly once"
        )
    ]
    assert "resume-or-start reusable phase-state validation" not in json.dumps(target)


def test_checked_in_verified_parity_target_has_complete_promoted_contract() -> None:
    payload = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json"
        ).read_text(encoding="utf-8")
    )
    target = next(
        entry
        for entry in payload["targets"]
        if entry["workflow_family"] == "verified_iteration_drain"
    )

    assert target["candidate"] == "workflows/library/verified_iteration_drain/drain.orc"
    assert target["yaml_primary"] == "workflows/examples/verified_iteration_drain.yaml"
    assert target["entry_workflow"] == "verified_iteration_drain/drain::drain"
    assert target["promotion_eligibility"] == {
        "eligible_for_primary_surface": True,
    }
    assert target["readiness_label"] == "promotion_eligible"
    assert target["lowering_route"] == "wcc_m4"
    assert target["lowering_schema_version"] == 2
    assert "required_family_evidence_roles" not in target
    executable_roles = {
        "compile",
        "dry_run",
        "smoke_or_integration",
        "output_contract_parity",
        "terminal_state_parity",
        "artifact_parity",
        "resume_parity",
    }
    assert set(target["evidence_commands"]) == executable_roles
    assert len(executable_roles | {"shared_validation", "baseline_characterization"}) == 9
    assert target["baseline_characterization"]["inputs"] == [
        "target_design_path",
        "check_commands_path",
        "drain_state_root",
        "artifact_work_root",
        "stall_limit",
        "worker_provider",
        "worker_model",
        "worker_effort",
        "reviewer_provider",
        "reviewer_model",
        "reviewer_effort",
    ]
    assert target["baseline_characterization"]["outputs"] == [
        "drain_status",
        "drain_summary_path",
    ]
    assert target["provider_externs_file"].endswith("verified_iteration_drain.providers.json")
    assert target["prompt_externs_file"].endswith("verified_iteration_drain.prompts.json")
    assert target["command_boundaries_file"].endswith("verified_iteration_drain.commands.json")


def test_promoted_design_delta_target_is_retired_but_historical_report_is_preserved() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = (
        repo_root
        / "workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert [entry["workflow_family"] for entry in payload["targets"]] == [
        "cycle_guard_demo",
        "design_plan_impl_stack",
        "verified_iteration_drain",
    ]

    historical_report_root = repo_root / "artifacts/work/review-parity-check"
    expected_hashes = {
        "design_delta_parent_drain.json": (
            "sha256:26ba415a25334175430dcd98195fe97c500baef6fa26b02e6a221a9b499b86a4"
        ),
        "design_delta_parent_drain.md": (
            "sha256:f808a0ea319e9ad4ceb1471bff99c71b2c9bd60f99786498f783ffa29c3cd8ba"
        ),
    }
    for name, expected_hash in expected_hashes.items():
        assert _sha256_file(historical_report_root / name) == expected_hash

    historical_report = json.loads(
        (historical_report_root / "design_delta_parent_drain.json").read_text(
            encoding="utf-8"
        )
    )
    assert historical_report["workflow_family"] == "design_delta_parent_drain"
    assert historical_report["non_regressive"] is True
    assert historical_report["promotion_eligibility"] == {
        "eligible_for_primary_surface": True
    }
    assert historical_report["route_identity"]["readiness_label"] == (
        "promotion_eligible"
    )
    assert historical_report["route_identity"]["lowering_route"] == "wcc_m4"


def test_migration_parity_source_has_no_retired_design_delta_lane() -> None:
    module = _parity_module()
    source = inspect.getsource(module)

    assert [
        name for name in _RETIRED_PARITY_MODULE_SYMBOLS if hasattr(module, name)
    ] == []
    assert _retired_parity_lane_references(source) == set()


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        (
            'if "resource_transition_parity" == role:\n    wire_role()\n',
            "resource_transition_parity",
        ),
        (
            'match role:\n    case "resource_transition_parity":\n        wire_role()\n',
            "resource_transition_parity",
        ),
        (
            'roles = {"resource_transition_parity": wire_role}\n',
            "resource_transition_parity",
        ),
        (
            "def _resource_transition_parity_evidence():\n    pass\n",
            "_resource_transition_parity_evidence",
        ),
        ("def wire(g8_deletion_evidence):\n    pass\n", "g8_deletion_evidence"),
        ("g8_deletion_evidence = None\n", "g8_deletion_evidence"),
        (
            "retired = parity._validated_design_delta_g8_deleted_rows\n",
            "_validated_design_delta_g8_deleted_rows",
        ),
        ("wire(g8_deletion_evidence=None)\n", "g8_deletion_evidence"),
    ),
)
def test_retirement_guard_detects_structurally_equivalent_wiring(
    source: str,
    expected: str,
) -> None:
    assert _retired_parity_lane_references(source) == {expected}


def test_retired_design_delta_command_boundary_manifest_omits_deleted_helpers() -> None:
    payload = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json"
        ).read_text(encoding="utf-8")
    )

    assert (
        payload["materialize_lisp_frontend_work_item_inputs"]["retirement_label"]
        == "retire_to_projection"
    )
    assert (
        payload["materialize_lisp_frontend_work_item_inputs"]["retirement_status"]
        == "retired"
    )
    for binding_name in (
        "classify_lisp_frontend_work_item_terminal",
        "select_lisp_frontend_blocked_recovery_route",
        "record_terminal_work_item",
        "record_blocked_recovery_outcome",
        "write_lisp_frontend_drain_status",
        "finalize_lisp_frontend_drain_summary",
    ):
        assert binding_name not in payload


def _design_delta_parent_target_fixture(tmp_path: Path):
    module = _parity_module()
    payload = _valid_manifest_payload()
    payload["targets"][0] = _design_delta_parent_target_entry(payload["targets"][0])
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)
    target = module.load_parity_targets(manifest_path)[0]
    _write_text(tmp_path / str(target.candidate), "(workflow-lisp)\n")
    _write_text(tmp_path / str(target.yaml_primary), "steps: []\n")
    return module, manifest_path, target


def _design_delta_projection_dual_run_report_payload(
    *,
    adapters: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_projection_dual_run_report.v1",
        "artifact_id": "projection_dual_run_report",
        "workflow_family": "design_delta_parent_drain",
        "overall_status": "pass",
        "all_passed": True,
        "adapters": dict(adapters)
        if adapters is not None
        else {
            "project_lisp_frontend_selector_action": {
                "status": "pass",
                "comparison_mapping_id": "selector_action_projection.v1",
                "cases": [],
            }
        },
    }


def _write_design_delta_g0_build_manifest(
    tmp_path: Path,
    *,
    include_adapter_census: bool = True,
    include_boundary_authority_report: bool = True,
    include_value_flow_census_report: bool = True,
    include_consumer_rendering_census_report: bool = True,
    include_typed_prompt_input_report: bool = True,
    include_entry_publication_report: bool = True,
    include_compatibility_bridge_report: bool = True,
    include_rendering_cleanup_report: bool = True,
    include_transition_authoring_report: bool = True,
    source_map_command_boundaries: list[dict[str, object]] | None = None,
    boundary_unclassified: list[str] | None = None,
    boundary_public_leaks: list[str] | None = None,
    value_flow_workflow_surfaces: list[str] | None = None,
    value_flow_declared_workflow_surfaces: list[str] | None = None,
    value_flow_missing_rows: list[dict[str, object]] | None = None,
    value_flow_stale_rows: list[dict[str, object]] | None = None,
    value_flow_invalid_rows: list[dict[str, object]] | None = None,
    value_flow_status: str = "pass",
    consumer_rendering_status: str = "pass",
    typed_prompt_input_status: str = "pass",
    entry_publication_status: str = "pass",
    compatibility_bridge_status: str = "pass",
    rendering_cleanup_status: str = "pass",
) -> Path:
    build_root = tmp_path / "build"
    build_root.mkdir(parents=True, exist_ok=True)
    reported_value_flow_workflow_surfaces = value_flow_workflow_surfaces or [
        "lisp_frontend_design_delta/drain::drain"
    ]
    _write_json(
        build_root / "core_workflow_ast.json",
        {
            "body": [
                {
                    "kind": "repeat_until",
                    "statements": [
                        {
                            "kind": "call",
                            "call_alias": "lisp_frontend_design_delta/selector::select-next-work",
                        },
                        {
                            "kind": "call",
                            "call_alias": (
                                "%drain.lisp_frontend_design_delta/drain::project-selector-action.v1"
                            ),
                        },
                        {
                            "kind": "call",
                            "call_alias": "lisp_frontend_design_delta/work_item::run-work-item",
                        },
                        {
                            "kind": "call",
                            "call_alias": (
                                "lisp_frontend_design_delta/design_gap_architect::"
                                "draft-design-gap-architecture"
                            ),
                        },
                    ],
                }
            ]
        },
    )
    _write_json(build_root / "semantic_ir.json", {})
    _write_json(
        build_root / "source_map.json",
        {
            "workflows": {
                "lisp_frontend_design_delta/work_item::run-work-item": {
                    "command_boundaries": source_map_command_boundaries or [],
                }
            }
        },
    )
    _write_json(
        build_root / "workflow_boundary_projection.json",
        {
            "workflows": [
                {
                    "workflow_name": "lisp_frontend_design_delta/drain::drain",
                    "display_name": "lisp_frontend_design_delta/drain::drain",
                    "boundary": {
                        "public_input_names": ["baseline_design_path", "target_design_path"],
                        "private_runtime_context_bindings": [
                            {
                                "binding_id": "phase-ctx",
                                "source_param_name": "phase-ctx",
                                "context_family": "PhaseCtx",
                                "bridge_class": "runtime_owned_context",
                                "generated_input_names": ["phase-ctx__run__run-id"],
                            }
                        ],
                        "private_managed_write_root_inputs": ["__write_root__drain_summary"],
                        "private_compatibility_bridge_inputs": ["manifest_path"],
                    },
                }
            ]
        },
    )
    if include_adapter_census:
        _write_json(
            build_root / "adapter_census.json",
            {
                "workflow_family": "design_delta_parent_drain",
                "rows": [
                    {
                        "binding_name": "project_lisp_frontend_selector_action",
                        "behavior_class": "typed_projection",
                        "retirement_class": "projection_adapter",
                        "retirement_label": "retire_to_projection",
                        "retirement_status": "retired",
                        "liveness": "unreferenced",
                    },
                ],
            },
        )
    if include_boundary_authority_report:
        _write_json(
            build_root / "boundary_authority_report.json",
            {
                "workflow_family": "design_delta_parent_drain",
                "workflows": [
                    {
                        "workflow_name": "lisp_frontend_design_delta/drain::drain",
                        "public_authored": ["baseline_design_path", "target_design_path"],
                        "compatibility_bridge": ["manifest_path"],
                        "runtime_derived": ["phase-ctx__run__run-id"],
                        "generated_internal": ["__write_root__drain_summary"],
                        "materialized_view": [],
                        "public_artifact": ["drain_summary_target_path"],
                        "unclassified": boundary_unclassified or [],
                        "public_leaks": boundary_public_leaks or [],
                        "compiled_evidence": {
                            "workflow_boundary_projection": "workflow_boundary_projection.json",
                            "source_map": "source_map.json",
                        },
                    }
                ],
            },
        )
    if include_value_flow_census_report:
        _write_json(
            build_root / "value_flow_census_report.json",
            {
                "schema_version": "workflow_lisp_private_runtime_value_flow_census_report.v1",
                "workflow_family": "design_delta_parent_drain",
                "checked_census_path": (
                    "checked/value_flow_census.json"
                ),
                "checked_census_fingerprint": "sha256:value-flow-census",
                "required_source_kinds": [
                    "public_input",
                    "command_adapter_input",
                    "pointer_path",
                    "generated_path",
                ],
                "declared_workflow_surfaces": (
                    value_flow_declared_workflow_surfaces
                    or reported_value_flow_workflow_surfaces
                ),
                "workflow_rows": [
                    {
                        "workflow_surface": workflow_surface,
                        "rows": [
                            {
                                "row_id": f"{workflow_surface}.baseline_design_path",
                                "source_kind": "public_input",
                            }
                        ],
                    }
                    for workflow_surface in reported_value_flow_workflow_surfaces
                ],
                "missing_rows": value_flow_missing_rows or [],
                "stale_rows": value_flow_stale_rows or [],
                "invalid_rows": value_flow_invalid_rows or [],
                "extra_compiled_rows": [],
                "compiled_evidence": {
                    "workflow_boundary_projection": "workflow_boundary_projection.json",
                    "source_map": "source_map.json",
                    "command_boundaries": (
                        "workflows/examples/inputs/workflow_lisp_migrations/"
                        "design_delta_parent_drain.commands.json"
                    ),
                },
                "status": value_flow_status,
            },
        )
    if include_consumer_rendering_census_report:
        _write_json(
            build_root / "consumer_rendering_census_report.json",
            {
                "schema_version": "workflow_lisp_consumer_rendering_census_report.v1",
                "workflow_family": "design_delta_parent_drain",
                "checked_manifest": {
                    "path": "checked/consumer_rendering_census.json",
                    "sha256": "sha256:consumer-rendering-census",
                },
                "source_census": {
                    "path": "checked/value_flow_census.json",
                    "sha256": "sha256:value-flow-census",
                },
                "materialize_view_effect_rows": [
                    {
                        "u0_row_id": "drain.materialized.drain_summary",
                        "workflow_surface": "lisp_frontend_design_delta/drain::drain",
                    }
                ],
                "missing_rows": [],
                "stale_rows": [],
                "invalid_rows": [],
                "status": consumer_rendering_status,
            },
        )
    if include_typed_prompt_input_report:
        _write_json(
            build_root / "typed_prompt_input_report.json",
            {
                "schema_version": "workflow_lisp_typed_prompt_input_report.v1",
                "workflow_family": "design_delta_parent_drain",
                "checked_manifest": {
                    "path": "checked/consumer_rendering_census.json",
                    "sha256": "sha256:consumer-rendering-census",
                },
                "consumed_artifact_prompt_rows": [],
                "selected_rows": [
                    {
                        "workflow_surface": "lisp_frontend_design_delta/plan_phase::run-plan-phase",
                        "provider_step_id": "root.plan_phase__draft",
                        "c0_row_id": "c0.plan_phase_prompt_draft",
                        "u0_row_id": "plan_phase.prompt.draft",
                        "binding_names": ["steering", "target_design"],
                        "renderer": {
                            "renderer_id": "canonical-json",
                            "renderer_version": 1,
                            "accepted_shape": "any_pure_value",
                        },
                        "source_map_origin_keys": [
                            "lisp_frontend_design_delta/plan_phase::run-plan-phase"
                        ],
                    },
                    {
                        "workflow_surface": "lisp_frontend_design_delta/selector::select-next-work",
                        "provider_step_id": "root.selector__decision",
                        "c0_row_id": "c0.selector_prompt_select_next_work",
                        "u0_row_id": "selector.prompt.select_next_work",
                        "binding_names": ["terminal_states"],
                        "renderer": {
                            "renderer_id": "canonical-json",
                            "renderer_version": 1,
                            "accepted_shape": "any_pure_value",
                        },
                        "source_map_origin_keys": [
                            "lisp_frontend_design_delta/selector::select-next-work"
                        ],
                    },
                ],
                "missing_rows": [],
                "stale_rows": [],
                "invalid_rows": [],
                "status": typed_prompt_input_status,
            },
        )
    if include_entry_publication_report:
        _write_json(
            build_root / "entry_publication_report.json",
            {
                "schema_version": "workflow_lisp_entry_publication_report.v1",
                "workflow_family": "lisp_frontend_design_delta_parent_drain",
                "status": entry_publication_status,
                "selected_c0_rows": [
                    {"row_id": "c0.plan_phase_output_approved_plan_path"}
                ],
                "lowered_publications": [],
                "compatibility_reasons": [
                    {"row_id": "c0.plan_phase_output_approved_plan_path"}
                ],
            },
        )
    if include_compatibility_bridge_report:
        _write_json(
            build_root / "compatibility_bridge_report.json",
            {
                "schema_version": "workflow_lisp_compatibility_bridge_report.v1",
                "workflow_family": "design_delta_parent_drain",
                "selected_c0_rows": [
                    {"row_id": "c0.work_item_pointer_selection_bundle_path"},
                    {"row_id": "c0.work_item_command_selection_bundle_path"},
                ],
                "generated_bridges": [
                    {"c0_row_id": "c0.work_item_pointer_selection_bundle_path"}
                ],
                "blocked_bridges": [
                    {"c0_row_id": "c0.work_item_command_selection_bundle_path"}
                ],
                "retired_bridges": [],
                "orphan_bridge_files": [],
                "contract_isolation": {
                    "workflow_signature_unchanged": True,
                    "call_contract_unchanged": True,
                    "boundary_projection_public_inputs_unchanged": True,
                    "typed_steps_do_not_consume_bridge_views": True,
                },
                "diagnostics": [],
                "status": compatibility_bridge_status,
            },
        )
    if include_rendering_cleanup_report:
        _write_json(
            build_root / "rendering_cleanup_report.json",
            {
                "schema_version": "workflow_lisp_rendering_cleanup_report.v1",
                "workflow_family": "design_delta_parent_drain",
                "status": rendering_cleanup_status,
                "selected_rows": [
                    {"row_id": "c0.plan_phase_output_approved_plan_path"},
                    {"row_id": "c0.work_item_command_selection_bundle_path"},
                    {"row_id": "c0.drain_materialized_drain_summary"},
                ],
                "source_census": {
                    "path": "checked/value_flow_census.json",
                    "schema_version": "workflow_lisp_private_runtime_value_flow_census.v1",
                },
                "prerequisite_reports": {
                    "typed_prompt_input_report": {
                        "status": "pass",
                        "schema_version": "workflow_lisp_typed_prompt_input_report.v1",
                    },
                    "observability_summary_report": {
                        "status": "pass",
                        "schema_version": "workflow_lisp_observability_summary_report.v1",
                    },
                    "entry_publication_report": {
                        "status": "pass",
                        "schema_version": "workflow_lisp_entry_publication_report.v1",
                    },
                    "compatibility_bridge_report": {
                        "status": "pass",
                        "schema_version": "workflow_lisp_compatibility_bridge_report.v1",
                    },
                },
                "cleanup_decisions": [
                    {
                        "cleanup_id": "cleanup.c0.plan.phase.output.approved.plan.path",
                        "c0_row_id": "c0.plan_phase_output_approved_plan_path",
                        "u0_row_id": "plan.phase.output.approved_plan_path",
                        "previous_track_c_decision": "RETIRE_TO_ENTRY_PUBLICATION",
                        "cleanup_decision": "BLOCKED",
                        "durability_before": "durable_publication",
                        "durability_after": "durable_publication",
                        "replacement_evidence": {
                            "report_name": "entry_publication_report",
                            "report_schema_version": "workflow_lisp_entry_publication_report.v1",
                            "report_path": "",
                            "row_id": "c0.plan_phase_output_approved_plan_path",
                            "status": "pass",
                        },
                        "compiled_liveness": {
                            "old_body_materialize_view_unreferenced": True,
                            "old_public_output_unreferenced": False,
                            "old_bridge_unreferenced": True,
                        },
                        "source_cleanup": {
                            "allowed": False,
                            "expected_files": [
                                "workflows/library/lisp_frontend_design_delta/drain.orc"
                            ],
                        },
                        "notes": "",
                    },
                    {
                        "cleanup_id": "cleanup.c0.work.item.command.selection.bundle.path",
                        "c0_row_id": "c0.work_item_command_selection_bundle_path",
                        "u0_row_id": "work_item.command.selection_bundle_path",
                        "previous_track_c_decision": "BLOCKED",
                        "cleanup_decision": "KEPT_BLOCKED_COMPATIBILITY",
                        "durability_before": "durable_bridge",
                        "durability_after": "durable_bridge",
                        "replacement_evidence": {
                            "report_name": "compatibility_bridge_report",
                            "report_schema_version": "workflow_lisp_compatibility_bridge_report.v1",
                            "report_path": "",
                            "row_id": "c0.work_item_command_selection_bundle_path",
                            "status": "pass",
                        },
                        "compiled_liveness": {
                            "old_body_materialize_view_unreferenced": True,
                            "old_public_output_unreferenced": True,
                            "old_bridge_unreferenced": False,
                        },
                        "source_cleanup": {
                            "allowed": False,
                            "expected_files": [
                                "workflows/library/lisp_frontend_design_delta/work_item.orc"
                            ],
                        },
                        "blocked_by": {
                            "adapter": "materialize_lisp_frontend_work_item_inputs",
                            "reason": "certified adapter still consumes the bridge",
                        },
                        "notes": "",
                    },
                    {
                        "cleanup_id": "cleanup.c0.drain.materialized.drain.summary",
                        "c0_row_id": "c0.drain_materialized_drain_summary",
                        "u0_row_id": "drain.materialized.drain_summary",
                        "previous_track_c_decision": "KEEP_TIMED_PUBLICATION",
                        "cleanup_decision": "KEEP_TIMED_PUBLICATION",
                        "durability_before": "durable_timed_body",
                        "durability_after": "durable_timed_body",
                        "replacement_evidence": {
                            "report_name": "consumer_rendering_census",
                            "report_schema_version": "workflow_lisp_consumer_rendering_census.v1",
                            "report_path": "",
                            "row_id": "c0.drain_materialized_drain_summary",
                            "status": "pass",
                        },
                        "compiled_liveness": {
                            "old_body_materialize_view_unreferenced": False,
                            "old_public_output_unreferenced": True,
                            "old_bridge_unreferenced": True,
                        },
                        "source_cleanup": {
                            "allowed": False,
                            "expected_files": [
                                "workflows/library/lisp_frontend_design_delta/drain.orc"
                            ],
                        },
                        "timed_publication": {
                            "reason": "view must remain materialized before downstream consumers observe the timed summary path",
                            "materialize_view_step_ids": [
                                "root.__timed_view"
                            ],
                        },
                        "notes": "",
                    },
                ],
                "decision_counts": {
                    "KEEP_TIMED_PUBLICATION": 2,
                    "BLOCKED": 7,
                    "KEPT_BLOCKED_COMPATIBILITY": 1,
                },
                "blocked_row_ids": [
                    "c0.plan_phase_output_approved_plan_path",
                    "c0.work_item_command_selection_bundle_path",
                ],
                "surviving_body_materialization_row_ids": [
                    "c0.drain_materialized_drain_summary",
                    "c0.work_item_summary_summary_path",
                ],
                "durability_reconciliation": {
                    "prompt_rows_ephemeral": True,
                    "durable_publications_state_layout_allocated": True,
                    "durable_bridges_state_layout_allocated": True,
                    "body_materialize_views_timed_only": True,
                },
                "contract_isolation": {
                    "workflow_signature_unchanged": True,
                    "typed_steps_do_not_consume_views": True,
                    "prompt_views_not_published": True,
                    "observability_views_not_semantic_outputs": True,
                },
                "diagnostics": [],
            },
        )
    if include_transition_authoring_report:
        _write_json(
            build_root / "transition_authoring_report.json",
            {
                "schema_version": "workflow_lisp_transition_authoring_report.v1",
                "workflow_family": "design_delta_parent_drain",
                "status": "pass",
                "compiled_origins": [
                    {
                        "workflow_name": "lisp_frontend_design_delta/transitions::emit-drain-status-transition-audit",
                        "module_name": "lisp_frontend_design_delta/transitions",
                        "step_kind": "resource_transition",
                        "step_id": (
                            "lisp_frontend_design_delta_transitions_emit_drain_status_transition_audit"
                        ),
                        "classification": "low_level_library",
                        "matched_row_id": "low_level.emit_drain_status_transition_audit",
                    }
                ],
                "ordinary_body_violations": [],
                "extra_origins": [],
                "stale_allowed_origins": [],
                "invalid_allowed_origins": [],
                "source_shape_violations": [],
            },
        )
    artifact_paths = {
        "core_workflow_ast": str(build_root / "core_workflow_ast.json"),
        "semantic_ir": str(build_root / "semantic_ir.json"),
        "source_map": str(build_root / "source_map.json"),
        "workflow_boundary_projection": str(build_root / "workflow_boundary_projection.json"),
    }
    artifact_status = {
        "core_workflow_ast": "emitted",
        "semantic_ir": "emitted",
        "source_map": "emitted",
        "workflow_boundary_projection": "emitted",
    }
    if include_adapter_census:
        artifact_paths["adapter_census"] = str(build_root / "adapter_census.json")
        artifact_status["adapter_census"] = "emitted"
    if include_boundary_authority_report:
        artifact_paths["boundary_authority_report"] = str(
            build_root / "boundary_authority_report.json"
        )
        artifact_status["boundary_authority_report"] = "emitted"
    if include_value_flow_census_report:
        artifact_paths["value_flow_census_report"] = str(
            build_root / "value_flow_census_report.json"
        )
        artifact_status["value_flow_census_report"] = "emitted"
    if include_consumer_rendering_census_report:
        artifact_paths["consumer_rendering_census_report"] = str(
            build_root / "consumer_rendering_census_report.json"
        )
        artifact_status["consumer_rendering_census_report"] = "emitted"
    if include_typed_prompt_input_report:
        artifact_paths["typed_prompt_input_report"] = str(
            build_root / "typed_prompt_input_report.json"
        )
        artifact_status["typed_prompt_input_report"] = "emitted"
    if include_entry_publication_report:
        artifact_paths["entry_publication_report"] = str(
            build_root / "entry_publication_report.json"
        )
        artifact_status["entry_publication_report"] = "emitted"
    if include_compatibility_bridge_report:
        artifact_paths["compatibility_bridge_report"] = str(
            build_root / "compatibility_bridge_report.json"
        )
        artifact_status["compatibility_bridge_report"] = "emitted"
    if include_rendering_cleanup_report:
        artifact_paths["rendering_cleanup_report"] = str(
            build_root / "rendering_cleanup_report.json"
        )
        artifact_status["rendering_cleanup_report"] = "emitted"
    if include_transition_authoring_report:
        artifact_paths["transition_authoring_report"] = str(
            build_root / "transition_authoring_report.json"
        )
        artifact_status["transition_authoring_report"] = "emitted"
    _write_json(
        build_root / "manifest.json",
        {
            "shared_validation_status": "validated",
            "lowering_route": "wcc_m4",
            "lowering_schema_version": 2,
            "compiled_workflow_checksum": "sha256:compiled-workflow",
            "artifact_paths": artifact_paths,
            "artifact_status": artifact_status,
        },
    )
    return build_root


def _install_fake_run_command(
    module: object,
    monkeypatch: pytest.MonkeyPatch,
    *,
    build_root: Path,
) -> None:
    def _fake_run_command(
        command: object,
        *,
        role: str,
        repo_root: Path,
        stdout_log: Path,
        stderr_log: Path,
    ):
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        stderr_log.parent.mkdir(parents=True, exist_ok=True)
        stdout = json.dumps({"build_root": str(build_root)}) if role == "compile" else ""
        stdout_log.write_text(stdout, encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        return module.CommandOutcome(
            status="pass",
            argv=("python", role),
            exit_code=0,
            elapsed_seconds=0.01,
            stdout=stdout,
            stderr="",
        )

    monkeypatch.setattr(module, "_run_command", _fake_run_command)


def test_run_parity_target_loads_design_delta_g0_artifacts_into_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(tmp_path)
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["adapter_census"]["workflow_family"] == "design_delta_parent_drain"
    assert report["boundary_authority_report"]["workflow_family"] == "design_delta_parent_drain"
    assert report["value_flow_census_report"]["workflow_family"] == "design_delta_parent_drain"
    assert report["consumer_rendering_census_report"]["workflow_family"] == "design_delta_parent_drain"
    assert report["entry_publication_report"]["workflow_family"] == "lisp_frontend_design_delta_parent_drain"
    assert report["compatibility_bridge_report"]["workflow_family"] == "design_delta_parent_drain"
    assert report["rendering_cleanup_report"]["workflow_family"] == "design_delta_parent_drain"
    assert report["compile_artifacts"]["required"]["adapter_census"]["status"] == "pass"
    assert report["compile_artifacts"]["required"]["boundary_authority_report"]["status"] == "pass"
    assert report["compile_artifacts"]["required"]["value_flow_census_report"]["status"] == "pass"
    assert (
        report["compile_artifacts"]["required"]["consumer_rendering_census_report"]["status"]
        == "pass"
    )
    assert report["compile_artifacts"]["required"]["entry_publication_report"]["status"] == "pass"
    assert report["compile_artifacts"]["required"]["compatibility_bridge_report"]["status"] == "pass"
    assert report["compile_artifacts"]["required"]["rendering_cleanup_report"]["status"] == "pass"


def test_run_parity_target_recovers_compile_artifacts_after_reference_family_conformance_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    original_build_root = _write_design_delta_g0_build_manifest(tmp_path)
    build_root = tmp_path / ".orchestrate" / "build" / "recovered"

    def _fake_run_command(
        command: object,
        *,
        role: str,
        repo_root: Path,
        stdout_log: Path,
        stderr_log: Path,
    ):
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        stderr_log.parent.mkdir(parents=True, exist_ok=True)
        if role == "compile":
            build_root.mkdir(parents=True, exist_ok=True)
            for artifact_path in original_build_root.iterdir():
                destination = build_root / artifact_path.name
                destination.write_bytes(artifact_path.read_bytes())
            manifest_file = build_root / "manifest.json"
            manifest_payload = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest_payload["artifact_paths"] = {
                artifact_name: str(build_root / Path(path).name)
                for artifact_name, path in manifest_payload["artifact_paths"].items()
            }
            manifest_payload["source_path"] = str((tmp_path / target.candidate).resolve())
            manifest_payload["entry_workflow"] = target.entry_workflow
            manifest_payload["source_sha256"] = _sha256_file(tmp_path / str(target.candidate))
            manifest_file.write_text(
                json.dumps(manifest_payload, indent=2) + "\n",
                encoding="utf-8",
            )
            stdout = ""
            stderr = (
                "artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain-summary.json:1:1: "
                "[reference_family_conformance_invalid] design-delta reference-family conformance "
                "profile failed: reference_family_parity_report_invalid\n"
            )
            status = "fail"
            exit_code = 2
        else:
            stdout = ""
            stderr = ""
            status = "pass"
            exit_code = 0
        stdout_log.write_text(stdout, encoding="utf-8")
        stderr_log.write_text(stderr, encoding="utf-8")
        return module.CommandOutcome(
            status=status,
            argv=("python", role),
            exit_code=exit_code,
            elapsed_seconds=0.01,
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr(module, "_run_command", _fake_run_command)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["evidence"]["compile"]["status"] == "fail"
    assert report["evidence"]["compile"]["build_root"] == ".orchestrate/build/recovered"
    assert (
        report["evidence"]["compile"]["manifest_path"]
        == ".orchestrate/build/recovered/manifest.json"
    )
    assert (
        report["compile_artifacts"]["required"]["source_map"]["path"]
        == ".orchestrate/build/recovered/source_map.json"
    )
    assert (
        report["evidence_freshness"]["required_artifacts"]["source_map"]["path"]
        == ".orchestrate/build/recovered/source_map.json"
    )

    gate_row = module.validate_report_for_target(
        report,
        target=target,
        targets_file=manifest_path,
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert gate_row.report_valid is True


def test_run_parity_target_rejects_recovered_compile_artifacts_after_candidate_source_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    original_build_root = _write_design_delta_g0_build_manifest(tmp_path)
    candidate_path = tmp_path / str(target.candidate)
    build_root = tmp_path / ".orchestrate" / "build" / "recovered"
    build_root.mkdir(parents=True, exist_ok=True)
    for artifact_path in original_build_root.iterdir():
        destination = build_root / artifact_path.name
        destination.write_bytes(artifact_path.read_bytes())
    manifest_file = build_root / "manifest.json"
    manifest_payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_payload["artifact_paths"] = {
        artifact_name: str(build_root / Path(path).name)
        for artifact_name, path in manifest_payload["artifact_paths"].items()
    }
    manifest_payload["source_path"] = str(candidate_path.resolve())
    manifest_payload["entry_workflow"] = target.entry_workflow
    manifest_payload["source_sha256"] = _sha256_file(candidate_path)
    manifest_file.write_text(
        json.dumps(manifest_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_text(candidate_path, "(workflow-lisp)\n(changed-source)\n")

    def _fake_run_command(
        command: object,
        *,
        role: str,
        repo_root: Path,
        stdout_log: Path,
        stderr_log: Path,
    ):
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        stderr_log.parent.mkdir(parents=True, exist_ok=True)
        if role == "compile":
            stdout = ""
            stderr = (
                "artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain-summary.json:1:1: "
                "[reference_family_conformance_invalid] design-delta reference-family conformance "
                "profile failed: reference_family_parity_report_invalid\n"
            )
            status = "fail"
            exit_code = 2
        else:
            stdout = ""
            stderr = ""
            status = "pass"
            exit_code = 0
        stdout_log.write_text(stdout, encoding="utf-8")
        stderr_log.write_text(stderr, encoding="utf-8")
        return module.CommandOutcome(
            status=status,
            argv=("python", role),
            exit_code=exit_code,
            elapsed_seconds=0.01,
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr(module, "_run_command", _fake_run_command)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert "build_root" not in report["evidence"]["compile"]

    gate_row = module.validate_report_for_target(
        report,
        target=target,
        targets_file=manifest_path,
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert gate_row.report_valid is True
    assert gate_row.evidence_complete is False


def test_run_parity_target_rejects_recovered_compile_artifacts_after_command_boundary_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    original_build_root = _write_design_delta_g0_build_manifest(tmp_path)
    build_root = tmp_path / ".orchestrate" / "build" / "recovered"
    build_root.mkdir(parents=True, exist_ok=True)
    for artifact_path in original_build_root.iterdir():
        destination = build_root / artifact_path.name
        destination.write_bytes(artifact_path.read_bytes())
    manifest_file = build_root / "manifest.json"
    manifest_payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_payload["artifact_paths"] = {
        artifact_name: str(build_root / Path(path).name)
        for artifact_name, path in manifest_payload["artifact_paths"].items()
    }
    manifest_payload["source_path"] = str((tmp_path / target.candidate).resolve())
    manifest_payload["entry_workflow"] = target.entry_workflow
    manifest_payload["source_sha256"] = _sha256_file(tmp_path / str(target.candidate))
    manifest_file.write_text(
        json.dumps(manifest_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_json(
        tmp_path / str(target.command_boundaries_file),
        {
            "mutated_after_cached_build": {
                "kind": "certified_adapter",
                "behavior_class": "structured_result",
            }
        },
    )

    def _fake_run_command(
        command: object,
        *,
        role: str,
        repo_root: Path,
        stdout_log: Path,
        stderr_log: Path,
    ):
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        stderr_log.parent.mkdir(parents=True, exist_ok=True)
        if role == "compile":
            stdout = ""
            stderr = (
                "artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain-summary.json:1:1: "
                "[reference_family_conformance_invalid] design-delta reference-family conformance "
                "profile failed: reference_family_parity_report_invalid\n"
            )
            status = "fail"
            exit_code = 2
        else:
            stdout = ""
            stderr = ""
            status = "pass"
            exit_code = 0
        stdout_log.write_text(stdout, encoding="utf-8")
        stderr_log.write_text(stderr, encoding="utf-8")
        return module.CommandOutcome(
            status=status,
            argv=("python", role),
            exit_code=exit_code,
            elapsed_seconds=0.01,
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr(module, "_run_command", _fake_run_command)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert "build_root" not in report["evidence"]["compile"]

    gate_row = module.validate_report_for_target(
        report,
        target=target,
        targets_file=manifest_path,
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert gate_row.report_valid is True
    assert gate_row.evidence_complete is False


def test_run_parity_target_snapshots_compile_artifact_freshness_before_later_roles_mutate_build_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(tmp_path)
    source_map_path = build_root / "source_map.json"
    original_sha256 = _sha256_bytes(source_map_path.read_bytes())

    def _fake_run_command(
        command: object,
        *,
        role: str,
        repo_root: Path,
        stdout_log: Path,
        stderr_log: Path,
    ):
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        stderr_log.parent.mkdir(parents=True, exist_ok=True)
        if role == "compile":
            stdout = json.dumps({"build_root": str(build_root)})
        else:
            if role == "output_contract_parity":
                _write_json(
                    source_map_path,
                    {
                        "workflows": {
                            "lisp_frontend_design_delta/work_item::run-work-item": {
                                "command_boundaries": [
                                    {
                                        "command_name": "mutated_after_compile",
                                        "step_id": "mutated.after.compile",
                                    }
                                ]
                            }
                        }
                    },
                )
            stdout = ""
        stderr = ""
        stdout_log.write_text(stdout, encoding="utf-8")
        stderr_log.write_text(stderr, encoding="utf-8")
        return module.CommandOutcome(
            status="pass",
            argv=("python", role),
            exit_code=0,
            elapsed_seconds=0.01,
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr(module, "_run_command", _fake_run_command)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert (
        report["evidence_freshness"]["required_artifacts"]["source_map"]["sha256"]
        == original_sha256
    )
    assert _sha256_bytes(source_map_path.read_bytes()) != original_sha256

    gate_row = module.validate_report_for_target(
        report,
        target=target,
        targets_file=manifest_path,
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert gate_row.report_valid is True
    assert gate_row.evidence_complete is False
    assert (
        "required artifact `source_map` digest changed while compile manifest identity remained stable"
        in gate_row.reasons
    )


def test_run_parity_target_fails_when_c4_c5_reports_are_under_specified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(tmp_path)
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    compatibility_bridge_report_path = build_root / "compatibility_bridge_report.json"
    rendering_cleanup_report_path = build_root / "rendering_cleanup_report.json"
    compatibility_bridge_payload = json.loads(
        compatibility_bridge_report_path.read_text(encoding="utf-8")
    )
    rendering_cleanup_payload = json.loads(
        rendering_cleanup_report_path.read_text(encoding="utf-8")
    )
    compatibility_bridge_payload.pop("contract_isolation", None)
    rendering_cleanup_payload.pop("durability_reconciliation", None)
    rendering_cleanup_payload.pop("contract_isolation", None)
    rendering_cleanup_payload["cleanup_decisions"] = [
        {
            "c0_row_id": "c0.work_item_command_selection_bundle_path",
            "cleanup_decision": "KEPT_BLOCKED_COMPATIBILITY",
        }
    ]
    _write_json(compatibility_bridge_report_path, compatibility_bridge_payload)
    _write_json(rendering_cleanup_report_path, rendering_cleanup_payload)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["compile_artifacts"]["required"]["compatibility_bridge_report"][
        "status"
    ] == "fail"
    assert report["compile_artifacts"]["required"]["rendering_cleanup_report"][
        "status"
    ] == "fail"


def test_run_parity_target_fails_cleanly_when_consumer_rendering_census_report_artifact_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        include_consumer_rendering_census_report=False,
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert (
        report["compile_artifacts"]["required"]["consumer_rendering_census_report"]["status"]
        == "missing"
    )


def test_run_parity_target_fails_when_consumer_rendering_census_report_is_non_passing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        consumer_rendering_status="fail",
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert (
        report["compile_artifacts"]["required"]["consumer_rendering_census_report"]["status"]
        == "fail"
    )
    assert "prerequisite" in report["compile_artifacts"]["required"][
        "consumer_rendering_census_report"
    ]["reason"]


def test_run_parity_target_fails_cleanly_when_typed_prompt_input_report_artifact_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        include_typed_prompt_input_report=False,
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["compile_artifacts"]["required"]["typed_prompt_input_report"]["status"] == "missing"


def test_run_parity_target_fails_cleanly_when_compatibility_bridge_report_artifact_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        include_compatibility_bridge_report=False,
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["compile_artifacts"]["required"]["compatibility_bridge_report"]["status"] == "missing"


def test_run_parity_target_fails_when_compatibility_bridge_report_is_non_passing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        compatibility_bridge_status="fail",
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["compile_artifacts"]["required"]["compatibility_bridge_report"]["status"] == "fail"


def test_run_parity_target_fails_cleanly_when_rendering_cleanup_report_artifact_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        include_rendering_cleanup_report=False,
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["compile_artifacts"]["required"]["rendering_cleanup_report"]["status"] == "missing"


def test_run_parity_target_fails_when_rendering_cleanup_report_is_non_passing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        rendering_cleanup_status="fail",
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["compile_artifacts"]["required"]["rendering_cleanup_report"]["status"] == "fail"


def test_run_parity_target_fails_when_typed_prompt_input_report_is_non_passing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        typed_prompt_input_status="fail",
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["compile_artifacts"]["required"]["typed_prompt_input_report"]["status"] == "fail"


def test_design_delta_consume_prompt_report_stays_empty_until_authored_consumes_exist(
    tmp_path: Path,
) -> None:
    build_root = _write_design_delta_g0_build_manifest(tmp_path)
    payload = json.loads(
        (build_root / "typed_prompt_input_report.json").read_text(encoding="utf-8")
    )

    assert payload["consumed_artifact_prompt_rows"] == []


















def test_run_parity_target_fails_projection_retirement_parity_when_retired_adapter_is_still_live(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(tmp_path)
    _write_json(
        build_root / "adapter_census.json",
        {
            "workflow_family": "design_delta_parent_drain",
            "rows": [
                {
                    "binding_name": "project_lisp_frontend_selector_action",
                    "retirement_status": "retired",
                    "liveness": "live",
                }
            ],
        },
    )
    _write_json(
        tmp_path / str(target.family_evidence_artifacts[0]["path"]),
        {
            "schema_version": "workflow_lisp_projection_dual_run_report.v1",
            "artifact_id": "projection_dual_run_report",
            "workflow_family": "design_delta_parent_drain",
            "overall_status": "pass",
            "all_passed": True,
            "adapters": {
                "project_lisp_frontend_selector_action": {
                    "status": "pass",
                    "comparison_mapping_id": "selector_action_projection.v1",
                    "cases": [],
                }
            },
        },
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    evidence = report["evidence"]["projection_retirement_parity"]
    assert evidence["status"] == "fail"
    assert "still live" in " ".join(evidence.get("reasons", []))


def test_run_parity_target_passes_projection_retirement_parity_for_retained_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(tmp_path)
    _write_json(
        tmp_path / str(target.family_evidence_artifacts[0]["path"]),
        _design_delta_projection_dual_run_report_payload(
            adapters={
                "project_lisp_frontend_selector_action": {
                    "status": "pass",
                    "comparison_mapping_id": "selector_action_projection.v1",
                    "cases": [],
                }
            }
        ),
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 24),
    )

    evidence = report["evidence"]["projection_retirement_parity"]
    artifact = evidence["artifacts"]["projection_dual_run_report"]
    assert evidence["status"] == "pass"
    assert artifact["status"] == "pass"
    assert artifact["adapter_states"] == {
        "project_lisp_frontend_selector_action": {
            "status": "pass",
            "retirement_state": "retained_retired_unreferenced",
            "evidence_source": "adapter_census",
        }
    }


def test_run_parity_target_fails_boundary_parity_when_g0_report_has_unclassified_or_public_leaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        boundary_unclassified=["manifest_path"],
        boundary_public_leaks=["phase-ctx__run__run-id"],
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    evidence = report["evidence"]["public_private_boundary_parity"]
    assert evidence["status"] == "fail"
    assert "unclassified" in " ".join(evidence.get("reasons", []))
    assert "public" in " ".join(evidence.get("reasons", []))


def test_public_private_boundary_parity_allows_explicit_public_compatibility_inputs() -> None:
    module = _parity_module()
    workflow_boundary = {
        "workflow_name": "lisp_frontend_design_delta/drain::drain",
        "public_input_names": [
            "steering_path",
            "target_design_path",
            "baseline_design_path",
            "manifest_path",
            "progress_ledger_path",
            "architecture_bundle_path",
        ],
        "private_runtime_context_bindings": [],
        "private_managed_write_root_inputs": [],
        "private_compatibility_bridge_inputs": [],
    }
    boundary_authority_report = {
        "workflows": [
            {
                "workflow_name": "lisp_frontend_design_delta/drain::drain",
                "public_authored": [
                    "steering_path",
                    "target_design_path",
                    "baseline_design_path",
                    "manifest_path",
                    "progress_ledger_path",
                    "architecture_bundle_path",
                ],
                "unclassified": [],
                "public_leaks": [],
            }
        ]
    }

    evidence = module._public_private_boundary_parity_evidence(
        workflow_boundary,
        boundary_authority_report=boundary_authority_report,
    )

    assert evidence["status"] == "pass"


def test_design_delta_parent_drain_fails_boundary_parity_when_selected_workflow_row_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(tmp_path)
    boundary_report_path = build_root / "boundary_authority_report.json"
    payload = json.loads(boundary_report_path.read_text(encoding="utf-8"))
    payload["workflows"] = [
        {
            **payload["workflows"][0],
            "workflow_name": "lisp_frontend_design_delta/work_item::run-work-item",
        }
    ]
    _write_json(boundary_report_path, payload)
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    evidence = report["evidence"]["public_private_boundary_parity"]
    assert evidence["status"] == "fail"
    assert "selected workflow row" in evidence["reason"]


def test_run_parity_target_fails_cleanly_when_boundary_authority_report_artifact_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        include_boundary_authority_report=False,
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["compile_artifacts"]["required"]["boundary_authority_report"]["status"] == "missing"
    assert report["evidence"]["public_private_boundary_parity"]["status"] == "fail"
    assert "boundary_authority_report" in report["evidence"]["public_private_boundary_parity"]["reason"]


def test_run_parity_target_fails_cleanly_when_value_flow_census_report_artifact_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        include_value_flow_census_report=False,
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["compile_artifacts"]["required"]["value_flow_census_report"]["status"] == "missing"


def test_run_parity_target_fails_when_value_flow_census_report_omits_selected_workflow_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        value_flow_workflow_surfaces=["lisp_frontend_design_delta/work_item::run-work-item"],
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["compile_artifacts"]["required"]["value_flow_census_report"]["status"] == "fail"
    assert "selected workflow surface" in report["compile_artifacts"]["required"]["value_flow_census_report"]["reason"]


def test_run_parity_target_fails_when_value_flow_census_report_omits_non_entry_declared_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        value_flow_declared_workflow_surfaces=[
            "lisp_frontend_design_delta/drain::drain",
            "lisp_frontend_design_delta/plan_phase::run-plan-phase",
            "lisp_frontend_design_delta/work_item::run-work-item",
        ],
        value_flow_workflow_surfaces=[
            "lisp_frontend_design_delta/drain::drain",
            "lisp_frontend_design_delta/work_item::run-work-item",
        ],
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["compile_artifacts"]["required"]["value_flow_census_report"]["status"] == "fail"
    assert "declared workflow surface" in report["compile_artifacts"]["required"]["value_flow_census_report"]["reason"]


def test_run_parity_target_fails_when_value_flow_census_report_has_missing_or_stale_or_invalid_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        value_flow_missing_rows=[{"row_id": "drain.bridge.manifest_path"}],
        value_flow_stale_rows=[{"row_id": "drain.generated.stale_path"}],
        value_flow_invalid_rows=[{"row_id": "drain.pointer.selection_bundle_path"}],
        value_flow_status="fail",
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["compile_artifacts"]["required"]["value_flow_census_report"]["status"] == "fail"
    assert "missing_rows" in report["compile_artifacts"]["required"]["value_flow_census_report"]["reason"]
    assert "stale_rows" in report["compile_artifacts"]["required"]["value_flow_census_report"]["reason"]
    assert "invalid_rows" in report["compile_artifacts"]["required"]["value_flow_census_report"]["reason"]


def test_design_delta_parent_drain_boundary_artifact_justifications_mark_g0_artifacts_as_parity_comparison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(tmp_path)
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    artifact_reasons = {
        item["artifact_id"]: item
        for item in report["evidence"]["boundary_artifact_justifications"]["artifact_justifications"]
    }
    assert artifact_reasons["adapter_census"]["reason"] == "parity_comparison"
    assert artifact_reasons["adapter_census"]["parity_constrained"] is True
    assert artifact_reasons["boundary_authority_report"]["reason"] == "parity_comparison"
    assert artifact_reasons["boundary_authority_report"]["parity_constrained"] is True
    assert artifact_reasons["value_flow_census_report"]["reason"] == "parity_comparison"
    assert artifact_reasons["value_flow_census_report"]["parity_constrained"] is True
    assert artifact_reasons["consumer_rendering_census_report"]["reason"] == "prerequisite_compile_evidence"
    assert artifact_reasons["consumer_rendering_census_report"]["parity_constrained"] is True
    assert artifact_reasons["typed_prompt_input_report"]["reason"] == "prerequisite_compile_evidence"
    assert artifact_reasons["typed_prompt_input_report"]["parity_constrained"] is True
