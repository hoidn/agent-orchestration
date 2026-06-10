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
    for artifact_name in ("core_workflow_ast", "semantic_ir", "source_map"):
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
