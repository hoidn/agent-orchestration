from __future__ import annotations

import hashlib
import importlib
import json
from datetime import date
from pathlib import Path

import pytest


def _parity_module():
    return importlib.import_module("orchestrator.workflow_lisp.migration_parity")


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
                "resource_transition_parity",
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
                    "g8_deletion_evidence",
                ],
                "optional": ["expanded_debug_yaml"],
            },
            "runtime_audit_artifacts": [
                {
                    "artifact_id": "drain_status_transition_audit",
                    "path": (
                        "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/"
                        "runtime-audits/design_delta_parent_drain_transition_audit.jsonl"
                    ),
                    "transition_name": "lisp_frontend_design_delta/transitions::write-drain-status",
                    "resource_kind": "drain-run-state",
                }
            ],
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
                "resource_transition_parity",
                "public_private_boundary_parity",
                "boundary_artifact_justifications",
                "route_identity",
            ],
            "runtime_audit_artifacts": [
                {
                    "artifact_id": "drain_status_transition_audit",
                    "path": (
                        "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/"
                        "runtime-audits/design_delta_parent_drain_transition_audit.jsonl"
                    ),
                    "transition_name": "lisp_frontend_design_delta/transitions::write-drain-status",
                    "resource_kind": "drain-run-state",
                }
            ],
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
    runtime_audit_path = repo_root / str(target_identity["runtime_audit_artifacts"][0]["path"])
    _write_text(runtime_audit_path, '{"transition":"write-drain-status"}\n')
    report["evidence_freshness"]["runtime_audit_artifacts"] = {
        "drain_status_transition_audit": {
            "path": str(target_identity["runtime_audit_artifacts"][0]["path"]),
            "transition_name": "lisp_frontend_design_delta/transitions::write-drain-status",
            "resource_kind": "drain-run-state",
            "exists": True,
            "sha256": _sha256_file(runtime_audit_path),
        }
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
                "resource_transition_parity",
                "public_private_boundary_parity",
                "boundary_artifact_justifications",
                "route_identity",
            ],
            "runtime_audit_artifacts": [
                {
                    "artifact_id": "drain_status_transition_audit",
                    "path": (
                        "artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/"
                        "runtime-audits/design_delta_parent_drain_transition_audit.jsonl"
                    ),
                    "transition_name": "lisp_frontend_design_delta/transitions::write-drain-status",
                    "resource_kind": "drain-run-state",
                }
            ],
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


def test_design_delta_parent_drain_resource_parity_rejects_deleted_helpers_still_present_in_manifest(
    tmp_path: Path,
) -> None:
    module = _parity_module()
    manifest_payload = _valid_manifest_payload()
    manifest_payload["targets"][0] = _design_delta_parent_target_entry(
        manifest_payload["targets"][0]
    )
    manifest_path = _write_json(tmp_path / "parity_targets.json", manifest_payload)
    target = module.load_parity_targets(manifest_path)[0]

    _write_json(
        tmp_path / target.command_boundaries_file,
        {
            "materialize_lisp_frontend_work_item_inputs": {
                "kind": "certified_adapter",
                "behavior_class": "structured_result",
                "input_signature": [{"name": "state_root", "type_name": "Path.state-root"}],
                "effects": ["structured_result"],
                "fixture_ids": ["ok"],
                "negative_fixture_ids": ["bad"],
                "owner_module": "lisp_frontend_design_delta/work_item",
                "replacement_path": "manifest-materialization bridge",
                "invocation_protocol": "json_object_positional_arg",
                "state_writes": [],
            },
            "record_terminal_work_item": {
                "kind": "certified_adapter",
            },
        },
    )

    evidence = module._resource_transition_parity_evidence(
        target=target,
        g8_deletion_evidence=_design_delta_g8_deletion_evidence_payload(),
        repo_root=tmp_path,
    )

    assert evidence["status"] == "fail"
    assert evidence["helpers"]["record_terminal_work_item"]["status"] == "fail"
    assert "still present" in " ".join(evidence["reasons"])


def test_design_delta_parent_drain_resource_parity_rejects_g8_evidence_missing_deleted_rows(
    tmp_path: Path,
) -> None:
    module = _parity_module()
    manifest_payload = _valid_manifest_payload()
    manifest_payload["targets"][0] = _design_delta_parent_target_entry(
        manifest_payload["targets"][0]
    )
    manifest_path = _write_json(tmp_path / "parity_targets.json", manifest_payload)
    target = module.load_parity_targets(manifest_path)[0]

    _write_json(
        tmp_path / target.command_boundaries_file,
        {
            "materialize_lisp_frontend_work_item_inputs": {
                "kind": "certified_adapter",
            },
        },
    )

    evidence = module._resource_transition_parity_evidence(
        target=target,
        g8_deletion_evidence=_design_delta_g8_deletion_evidence_payload(
            removed_manifest_rows=[
                "classify_lisp_frontend_work_item_terminal",
                "select_lisp_frontend_blocked_recovery_route",
                "record_terminal_work_item",
            ]
        ),
        repo_root=tmp_path,
    )

    assert evidence["status"] == "fail"
    assert "missing deleted rows" in " ".join(evidence["reasons"])


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
            "transition_name": "lisp_frontend_design_delta/transitions::write-drain-status",
            "resource_kind": "drain-run-state",
        },
    )


def test_design_delta_parent_drain_resource_transition_parity_fails_when_runtime_audit_artifact_is_missing(
    tmp_path: Path,
) -> None:
    module = _parity_module()
    payload = _valid_manifest_payload()
    payload["targets"][0] = _design_delta_parent_target_entry(payload["targets"][0])
    manifest_path = _write_json(tmp_path / "parity_targets.json", payload)
    target = module.load_parity_targets(manifest_path)[0]

    _write_json(
        tmp_path / target.command_boundaries_file,
        {
            "materialize_lisp_frontend_work_item_inputs": {
                "kind": "certified_adapter",
            },
        },
    )

    evidence = module._resource_transition_parity_evidence(
        target=target,
        g8_deletion_evidence=_design_delta_g8_deletion_evidence_payload(),
        repo_root=tmp_path,
    )

    assert evidence["status"] == "fail"
    assert evidence["runtime_audit"]["status"] == "fail"
    assert "missing" in evidence["runtime_audit"]["reason"]


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
    runtime_audit_artifact = target.runtime_audit_artifacts[0]
    _write_text(
        tmp_path / runtime_audit_artifact["path"],
        json.dumps(
            {
                "transition_name": runtime_audit_artifact["transition_name"],
                "resource_kind": runtime_audit_artifact["resource_kind"],
                "outcome_code": "committed",
            }
        )
        + "\n",
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
    targets = module.load_parity_targets(manifest_path)

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


def test_design_plan_impl_stack_manifest_uses_defaulted_dry_run_and_family_specific_evidence() -> None:
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

    expected_behavioral_selectors = {
        "smoke_or_integration": "design_plan_impl_stack_orc_runtime_smoke_executes_single_pass_stack",
        "output_contract_parity": "design_plan_impl_stack_orc_runtime_output_contract_matches_stack_outputs",
        "terminal_state_parity": (
            "design_plan_impl_stack_orc_runtime_completes_with_expected_terminal_state"
        ),
        "artifact_parity": "design_plan_impl_stack_orc_runtime_materializes_expected_artifacts",
    }
    for role, expected_selector in expected_behavioral_selectors.items():
        selector = " ".join(target["evidence_commands"][role])
        assert expected_selector in selector
        assert "design_plan_impl_stack_orc_compiles_with_phase_family_contracts" not in selector
        assert "review_loop_parity_fixture" not in selector

    resume_selector = " ".join(target["evidence_commands"]["resume_parity"])
    assert "resume_or_start_plan_gate_reusable_state_parity_path" in resume_selector


def test_design_delta_parent_drain_manifest_uses_explicit_dry_run_smoke_substitution() -> None:
    payload = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json"
        ).read_text(encoding="utf-8")
    )
    target = next(
        entry for entry in payload["targets"] if entry["workflow_family"] == "design_delta_parent_drain"
    )

    dry_run = target["evidence_commands"]["dry_run"]
    assert isinstance(dry_run, dict)
    assert "argv" not in dry_run
    waiver = dry_run["waiver"]
    assert waiver["targeted_evidence"] == ["smoke_or_integration", "parent_callable_smoke"]
    assert "fake-provider smokes" in waiver["justification"]


def test_design_delta_parent_drain_checked_in_command_boundary_metadata_matches_g8_deleted_manifest() -> None:
    payload = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json"
        ).read_text(encoding="utf-8")
    )

    assert payload["materialize_lisp_frontend_work_item_inputs"]["retirement_label"] == "keep_bridge"
    assert payload["materialize_lisp_frontend_work_item_inputs"].get("retirement_status") is None
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


def _design_delta_g8_deletion_evidence_payload(
    *,
    removed_manifest_rows: list[str] | None = None,
    removed_registry_heads: list[str] | None = None,
    imported_only_registry_heads: list[str] | None = None,
    status: str = "pass",
) -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_design_delta_g8_deletion_evidence.v1",
        "workflow_family": "design_delta_parent_drain",
        "removed_manifest_rows": removed_manifest_rows
        or [
            "classify_lisp_frontend_work_item_terminal",
            "select_lisp_frontend_blocked_recovery_route",
            "record_terminal_work_item",
            "record_blocked_recovery_outcome",
            "write_lisp_frontend_drain_status",
            "finalize_lisp_frontend_drain_summary",
        ],
        "removed_script_paths": [],
        "removed_python_symbols": [
            "_ALLOWED_CONTEXT_RECORD_TYPES",
            "_STRUCTURAL_CONTEXT_RECORD_NAMES",
            "record_name_lane_fallback",
            "name_lane_fallback_counts",
            "clear_name_lane_fallback_counts",
        ],
        "removed_registry_heads": removed_registry_heads
        or ["with-phase", "finalize-selected-item", "backlog-drain"],
        "retained_bridges": ["materialize_lisp_frontend_work_item_inputs"],
        "precondition_evidence_refs": ["design_delta_drain_summary_ok"],
        "grep_guards": ["rg -n \"TEMP_COMPILER_INTRINSIC\" orchestrator/workflow_lisp"],
        "verification_commands": [
            "python -m pytest tests/test_workflow_lisp_migration_parity.py -q"
        ],
        "line_count_delta": {"removed_manifest_row_count": 6},
        "hook_surface_delta": {
            "removed_registry_heads": removed_registry_heads
            or ["with-phase", "finalize-selected-item", "backlog-drain"],
            "imported_only_registry_heads": imported_only_registry_heads or ["with-phase"],
        },
        "adapter_surface_delta": {
            "removed_manifest_row_count": 6,
            "retained_bridges": ["materialize_lisp_frontend_work_item_inputs"],
        },
        "status": status,
    }


def _write_design_delta_g0_build_manifest(
    tmp_path: Path,
    *,
    include_adapter_census: bool = True,
    include_boundary_authority_report: bool = True,
    include_value_flow_census_report: bool = True,
    include_g8_deletion_evidence: bool = True,
    g8_removed_manifest_rows: list[str] | None = None,
    boundary_unclassified: list[str] | None = None,
    boundary_public_leaks: list[str] | None = None,
    value_flow_workflow_surfaces: list[str] | None = None,
    value_flow_missing_rows: list[dict[str, object]] | None = None,
    value_flow_stale_rows: list[dict[str, object]] | None = None,
    value_flow_invalid_rows: list[dict[str, object]] | None = None,
    value_flow_status: str = "pass",
) -> Path:
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
    for artifact_name in ("semantic_ir", "source_map"):
        _write_json(build_root / f"{artifact_name}.json", {})
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
                    "workflows/examples/inputs/workflow_lisp_migrations/"
                    "design_delta_parent_drain.value_flow_census.json"
                ),
                "checked_census_fingerprint": "sha256:value-flow-census",
                "required_source_kinds": [
                    "public_input",
                    "command_adapter_input",
                    "pointer_path",
                    "generated_path",
                ],
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
                    for workflow_surface in (
                        value_flow_workflow_surfaces
                        or ["lisp_frontend_design_delta/drain::drain"]
                    )
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
    if include_g8_deletion_evidence:
        _write_json(
            build_root / "g8_deletion_evidence.json",
            _design_delta_g8_deletion_evidence_payload(
                removed_manifest_rows=g8_removed_manifest_rows,
            ),
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
    if include_g8_deletion_evidence:
        artifact_paths["g8_deletion_evidence"] = str(build_root / "g8_deletion_evidence.json")
        artifact_status["g8_deletion_evidence"] = "emitted"
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
    assert report["g8_deletion_evidence"]["workflow_family"] == "design_delta_parent_drain"
    assert report["compile_artifacts"]["required"]["adapter_census"]["status"] == "pass"
    assert report["compile_artifacts"]["required"]["boundary_authority_report"]["status"] == "pass"
    assert report["compile_artifacts"]["required"]["value_flow_census_report"]["status"] == "pass"
    assert report["compile_artifacts"]["required"]["g8_deletion_evidence"]["status"] == "pass"


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


def test_run_parity_target_fails_view_retirement_parity_when_g8_evidence_omits_finalizer_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        g8_removed_manifest_rows=[
            "classify_lisp_frontend_work_item_terminal",
            "select_lisp_frontend_blocked_recovery_route",
            "record_terminal_work_item",
            "record_blocked_recovery_outcome",
            "write_lisp_frontend_drain_status",
        ],
    )
    _write_json(
        tmp_path
        / "artifacts/work/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/migration-parity/design_delta_parent_drain_view_dual_run_report.json",
        {
            "schema_version": "workflow_lisp_view_dual_run_report.v1",
            "artifact_id": "view_dual_run_report",
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
        },
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    evidence = report["evidence"]["view_retirement_parity"]
    assert evidence["status"] == "fail"
    assert "deleted finalizer row" in " ".join(evidence.get("reasons", []))


def test_run_parity_target_fails_when_g8_evidence_does_not_require_imported_only_with_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    _write_json(
        tmp_path / str(target.command_boundaries_file),
        {
            "materialize_lisp_frontend_work_item_inputs": {
                "kind": "certified_adapter",
            }
        },
    )
    build_root = _write_design_delta_g0_build_manifest(tmp_path)
    _write_json(
        build_root / "g8_deletion_evidence.json",
        _design_delta_g8_deletion_evidence_payload(
            removed_registry_heads=["finalize-selected-item", "backlog-drain"],
            imported_only_registry_heads=[],
        ),
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    evidence = report["evidence"]["resource_transition_parity"]
    assert evidence["status"] == "fail"
    assert "with-phase" in " ".join(evidence.get("reasons", []))


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


def test_design_delta_parent_drain_resource_transition_parity_ignores_retirement_lane(
    tmp_path: Path,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    runtime_audit_artifact = target.runtime_audit_artifacts[0]
    _write_text(
        tmp_path / runtime_audit_artifact["path"],
        json.dumps(
            {
                "transition_name": runtime_audit_artifact["transition_name"],
                "resource_kind": runtime_audit_artifact["resource_kind"],
                "outcome_code": "committed",
            }
        )
        + "\n",
    )
    _write_json(
        tmp_path / str(target.command_boundaries_file),
        {
            "materialize_lisp_frontend_work_item_inputs": {
                "kind": "certified_adapter",
                "stable_command": ["python", "materialize.py"],
                "behavior_class": "structured_result",
                "input_signature": [{"name": "state_root", "type_name": "Path.state-root"}],
                "effects": ["structured_result"],
                "fixture_ids": ["materialize_ok"],
                "negative_fixture_ids": ["materialize_bad"],
                "owner_module": "lisp_frontend_design_delta/work_item",
                "replacement_path": "manifest-materialization bridge",
                "invocation_protocol": "json_object_positional_arg",
                "state_writes": [],
            },
        },
    )

    evidence = module._resource_transition_parity_evidence(
        target=target,
        g8_deletion_evidence=_design_delta_g8_deletion_evidence_payload(),
        repo_root=tmp_path,
    )

    assert evidence["status"] == "pass"


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


def test_run_parity_target_fails_cleanly_when_g8_deletion_evidence_artifact_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, manifest_path, target = _design_delta_parent_target_fixture(tmp_path)
    _write_json(
        tmp_path / str(target.command_boundaries_file),
        {
            "materialize_lisp_frontend_work_item_inputs": {
                "kind": "certified_adapter",
            }
        },
    )
    build_root = _write_design_delta_g0_build_manifest(
        tmp_path,
        include_g8_deletion_evidence=False,
    )
    _install_fake_run_command(module, monkeypatch, build_root=build_root)

    report = module.run_parity_target(
        target,
        output_root=tmp_path / "parity",
        repo_root=tmp_path,
        today=date(2026, 6, 2),
    )

    assert report["compile_artifacts"]["required"]["g8_deletion_evidence"]["status"] == "missing"
    assert report["evidence"]["resource_transition_parity"]["status"] == "fail"
    assert "g8_deletion_evidence" in " ".join(
        report["evidence"]["resource_transition_parity"].get("reasons", [])
    )


def test_design_delta_parent_drain_target_requires_g0_compile_artifacts() -> None:
    payload = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json"
        ).read_text(encoding="utf-8")
    )
    target = next(
        entry for entry in payload["targets"] if entry["workflow_family"] == "design_delta_parent_drain"
    )

    assert "adapter_census" in target["compile_artifacts"]["required"]
    assert "boundary_authority_report" in target["compile_artifacts"]["required"]
    assert "value_flow_census_report" in target["compile_artifacts"]["required"]
    assert "g8_deletion_evidence" in target["compile_artifacts"]["required"]


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
    assert artifact_reasons["g8_deletion_evidence"]["reason"] == "parity_comparison"
    assert artifact_reasons["g8_deletion_evidence"]["parity_constrained"] is True
