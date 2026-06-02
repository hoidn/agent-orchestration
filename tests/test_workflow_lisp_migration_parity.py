from __future__ import annotations

import importlib
import json
from datetime import date
from pathlib import Path

import pytest


def _parity_module():
    return importlib.import_module("orchestrator.workflow_lisp.migration_parity")


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


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
        "schema_version": "workflow_lisp_migration_parity_report.v1",
        "workflow_family": workflow_family,
        "candidate": f"workflows/examples/{workflow_family}.orc",
        "yaml_primary": f"workflows/examples/{workflow_family}.yaml",
        "compiler_version": "workflow-lisp-test",
        "dsl_version": "2.14",
        "generated_at": "2026-06-02T00:00:00Z",
        "generated_by": ["python", "-m", "orchestrator", "migration-parity"],
        "report_path": (
            f"artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/{workflow_family}.json"
        ),
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


def test_render_parity_index_derives_primary_surface() -> None:
    module = _parity_module()
    report = _valid_report_payload()

    index = module.render_parity_index([report])

    assert index["schema_version"] == "workflow_lisp_migration_parity_index.v1"
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

    index = module.render_parity_index([report])

    assert index["targets"][0]["workflow_family"] == "cycle_guard_demo"
    assert index["targets"][0]["non_regressive"] is True
    assert index["targets"][0]["primary_surface"] == "yaml"


def test_rendered_parity_surfaces_do_not_publish_hidden_managed_write_root_inputs() -> None:
    module = _parity_module()
    report = _valid_report_payload()

    markdown = module.render_parity_markdown(report)
    index = module.render_parity_index([report])

    assert "__write_root__" not in markdown
    assert "__write_root__" not in json.dumps(index, sort_keys=True)

