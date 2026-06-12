from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import WorkflowSignatureError, bind_workflow_inputs
from orchestrator.workflow.view_renderer import render_view, view_bytes_digest
from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_ROOT = REPO_ROOT / "workflows" / "library"
VECTORS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_view_dual_run_vectors.json"
)
REPORT_PATH = (
    REPO_ROOT
    / "artifacts"
    / "work"
    / "LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN"
    / "migration-parity"
    / "design_delta_parent_drain_view_dual_run_report.json"
)
COMMANDS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.commands.json"
)
RUNTIME_VIEW_FIXTURE = (
    REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "runtime_view_fixture.orc"
)
ADAPTER_SCRIPT = (
    REPO_ROOT / "workflows" / "library" / "scripts" / "finalize_lisp_frontend_drain_summary.py"
)
REPORT_SCHEMA_VERSION = "workflow_lisp_view_dual_run_report.v1"
EXPECTED_COMPARISON_MAPPING = "drain_summary_view.v1"


def _load_vectors() -> dict[str, Any]:
    return json.loads(VECTORS_PATH.read_text(encoding="utf-8"))


def _command_boundaries() -> dict[str, object]:
    return _parse_command_boundaries_manifest(
        json.loads(COMMANDS_PATH.read_text(encoding="utf-8")),
        manifest_path=COMMANDS_PATH,
    )


def _write_run_state(workspace: Path, run_state_document: dict[str, Any]) -> None:
    run_state_path = workspace / "state" / "run_state.json"
    run_state_path.parent.mkdir(parents=True, exist_ok=True)
    run_state_path.write_text(json.dumps(run_state_document, indent=2) + "\n", encoding="utf-8")


def _compile_replacement_bundle(workspace: Path):
    result = compile_stage3_entrypoint(
        RUNTIME_VIEW_FIXTURE,
        source_roots=(LIBRARY_ROOT,),
        provider_externs={},
        prompt_externs={},
        command_boundaries=_command_boundaries(),
        validate_shared=True,
        workspace_root=workspace,
    )
    return result.validated_bundles_by_name[
        "lisp_frontend_design_delta/runtime_view_fixture::run-summary-view"
    ]


def _run_incumbent(inputs: dict[str, Any], workspace: Path) -> dict[str, Any]:
    output_path = workspace / "artifacts" / "work" / "finalizer_bundle.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] = str(output_path)
    result = subprocess.run(
        ["python", str(ADAPTER_SCRIPT), json.dumps(inputs)],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "bundle": (
            json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else None
        ),
        "summary_path": workspace / str(inputs["summary_path"]),
        "legacy_pointer_path": workspace / "state" / "drain_summary_path.txt",
        "legacy_final_run_state_path": workspace / "state" / "final_run_state_path.txt",
    }


def _run_replacement_once(inputs: dict[str, Any], workspace: Path) -> dict[str, Any]:
    bundle = _compile_replacement_bundle(workspace)
    runtime_inputs = {
        input_name: contract
        for input_name, contract in workflow_runtime_input_contracts(bundle).items()
        if not input_name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(runtime_inputs, inputs, workspace)
    state_manager = StateManager(
        workspace=workspace,
        run_id=f"view-dual-run-{abs(hash(json.dumps(inputs, sort_keys=True)))}",
    )
    state_manager.initialize(
        RUNTIME_VIEW_FIXTURE.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    state = WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute(on_error="stop")
    assert state["status"] == "completed"
    summary_path = workspace / str(inputs["summary_path"])
    pointer_path = workspace / str(inputs["pointer_path"])
    return {
        "state": state,
        "summary_path": summary_path,
        "pointer_path": pointer_path,
        "summary_payload": json.loads(summary_path.read_text(encoding="utf-8")),
        "summary_bytes": summary_path.read_bytes(),
        "pointer_bytes": pointer_path.read_bytes(),
        "summary_view": state["steps"]["drain-summary-view"]["debug"]["materialize_view"],
        "pointer_view": state["steps"]["drain-summary-pointer-view"]["debug"]["materialize_view"],
        "workflow_outputs": state["workflow_outputs"],
    }


def _assert_positive_vector_matches(
    *,
    comparison_mapping_id: str,
    vector: dict[str, Any],
    incumbent: dict[str, Any],
    replacement_first: dict[str, Any],
    replacement_second: dict[str, Any],
) -> dict[str, Any]:
    assert comparison_mapping_id == EXPECTED_COMPARISON_MAPPING
    expected_typed_value = vector["expected_typed_value"]
    assert replacement_first["summary_payload"] == expected_typed_value
    assert replacement_second["summary_payload"] == expected_typed_value

    incumbent_summary = json.loads(incumbent["summary_path"].read_text(encoding="utf-8"))
    legacy_expectations = vector["legacy_state_expectations"]
    assert incumbent_summary["drain_status"] == expected_typed_value["drain_status"]
    assert incumbent_summary["run_state_path"] == expected_typed_value["run_state_path"]
    assert vector["incumbent_inputs"]["summary_path"] == expected_typed_value["summary_target"]
    assert incumbent_summary["completed_items"] == legacy_expectations["completed_items"]
    assert incumbent_summary["completed_design_gaps"] == legacy_expectations["completed_design_gaps"]
    assert incumbent_summary["blocked_items"] == legacy_expectations["blocked_items"]
    assert incumbent_summary["blocked_design_gaps"] == legacy_expectations["blocked_design_gaps"]
    assert incumbent_summary["history_count"] == legacy_expectations["history_count"]

    expected_summary_bytes = render_view("canonical-json", 1, expected_typed_value)
    assert replacement_first["summary_bytes"] == expected_summary_bytes
    assert replacement_second["summary_bytes"] == expected_summary_bytes

    expected_pointer_bytes = render_view("posix-path-line", 1, expected_typed_value["summary_target"])
    assert replacement_first["pointer_bytes"] == expected_pointer_bytes
    assert replacement_second["pointer_bytes"] == expected_pointer_bytes
    assert incumbent["legacy_pointer_path"].read_bytes() == expected_pointer_bytes
    assert incumbent["legacy_final_run_state_path"].read_text(encoding="utf-8").strip() == expected_typed_value[
        "run_state_path"
    ]

    summary_digest = view_bytes_digest(replacement_first["summary_bytes"])
    pointer_digest = view_bytes_digest(replacement_first["pointer_bytes"])
    assert summary_digest == replacement_first["summary_view"]["view_digest"]
    assert pointer_digest == replacement_first["pointer_view"]["view_digest"]
    assert summary_digest == replacement_second["summary_view"]["view_digest"]
    assert pointer_digest == replacement_second["pointer_view"]["view_digest"]

    return {
        "id": vector["id"],
        "status": "pass",
        "accepted_differences": vector["accepted_differences"],
        "expected_typed_value": expected_typed_value,
        "replacement_typed_value": replacement_first["summary_payload"],
        "legacy_shared_fields": {
            "drain_status": incumbent_summary["drain_status"],
            "run_state_path": incumbent_summary["run_state_path"],
            "summary_target": vector["incumbent_inputs"]["summary_path"],
        },
        "legacy_state_expectations": legacy_expectations,
        "compatibility_views": {
            "legacy_pointer_path": vector["compatibility_expectations"]["legacy_pointer_path"],
            "replacement_pointer_path": vector["compatibility_expectations"]["replacement_pointer_path"],
            "legacy_pointer_matches_replacement": True,
            "legacy_final_run_state_path": vector["compatibility_expectations"][
                "legacy_final_run_state_path"
            ],
            "legacy_final_run_state_value": incumbent["legacy_final_run_state_path"]
            .read_text(encoding="utf-8")
            .strip(),
        },
        "replacement_view_digests": {
            "summary": summary_digest,
            "pointer": pointer_digest,
        },
        "determinism": {
            "summary_bytes_match": replacement_first["summary_bytes"] == replacement_second["summary_bytes"],
            "pointer_bytes_match": replacement_first["pointer_bytes"] == replacement_second["pointer_bytes"],
            "summary_digest_match": replacement_first["summary_view"]["view_digest"]
            == replacement_second["summary_view"]["view_digest"],
            "pointer_digest_match": replacement_first["pointer_view"]["view_digest"]
            == replacement_second["pointer_view"]["view_digest"],
        },
    }


def _assert_negative_vector_matches(vector: dict[str, Any], workspace: Path) -> dict[str, Any]:
    incumbent = _run_incumbent(vector["incumbent_inputs"], workspace / "incumbent")
    assert incumbent["returncode"] != 0
    incumbent_error = (incumbent["stderr"] or incumbent["stdout"]).strip()
    assert vector["expected_failures"]["incumbent_substring"] in incumbent_error

    _write_run_state(workspace / "replacement", vector["run_state_document"])
    replacement_error: str | None = None
    try:
        _run_replacement_once(vector["replacement_inputs"], workspace / "replacement")
    except WorkflowSignatureError as exc:
        replacement_error = json.dumps(exc.error, sort_keys=True)
    assert replacement_error is not None
    assert vector["expected_failures"]["replacement_substring"] in replacement_error

    return {
        "id": vector["id"],
        "status": "pass",
        "accepted_differences": vector["accepted_differences"],
        "expected_failures": vector["expected_failures"],
        "incumbent_error": incumbent_error,
        "replacement_error": replacement_error,
    }


def _emit_dual_run_report(workspace: Path, *, report_path: Path = REPORT_PATH) -> dict[str, Any]:
    payload = _load_vectors()
    case_reports: list[dict[str, Any]] = []
    overall_pass = True
    for vector in payload["vectors"]:
        if vector["kind"] == "positive":
            incumbent_workspace = workspace / vector["id"] / "incumbent"
            replacement_workspace_a = workspace / vector["id"] / "replacement-a"
            replacement_workspace_b = workspace / vector["id"] / "replacement-b"
            for case_workspace in (incumbent_workspace, replacement_workspace_a, replacement_workspace_b):
                _write_run_state(case_workspace, vector["run_state_document"])
            incumbent = _run_incumbent(vector["incumbent_inputs"], incumbent_workspace)
            assert incumbent["returncode"] == 0, incumbent["stderr"] or incumbent["stdout"]
            replacement_first = _run_replacement_once(
                vector["replacement_inputs"],
                replacement_workspace_a,
            )
            replacement_second = _run_replacement_once(
                vector["replacement_inputs"],
                replacement_workspace_b,
            )
            case_reports.append(
                _assert_positive_vector_matches(
                    comparison_mapping_id=payload["comparison_mapping_id"],
                    vector=vector,
                    incumbent=incumbent,
                    replacement_first=replacement_first,
                    replacement_second=replacement_second,
                )
            )
            continue
        case_reports.append(_assert_negative_vector_matches(vector, workspace / vector["id"]))
    adapter_pass = all(case["status"] == "pass" for case in case_reports)
    overall_pass = overall_pass and adapter_pass
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "artifact_id": "view_dual_run_report",
        "workflow_family": payload["workflow_family"],
        "vectors_path": str(VECTORS_PATH.relative_to(REPO_ROOT)),
        "generated_at": datetime.now(UTC).isoformat(),
        "overall_status": "pass" if overall_pass else "fail",
        "all_passed": overall_pass,
        "adapters": {
            payload["adapter_name"]: {
                "status": "pass" if adapter_pass else "fail",
                "comparison_mapping_id": payload["comparison_mapping_id"],
                "cases": case_reports,
            }
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def test_view_dual_run_vectors_manifest_is_well_formed() -> None:
    payload = _load_vectors()

    assert payload["schema_version"] == "workflow_lisp_view_dual_run_vectors.v1"
    assert payload["workflow_family"] == "design_delta_parent_drain"
    assert payload["adapter_name"] == "finalize_lisp_frontend_drain_summary"
    assert payload["comparison_mapping_id"] == EXPECTED_COMPARISON_MAPPING
    assert payload["report_path"] == str(REPORT_PATH.relative_to(REPO_ROOT))
    assert [vector["id"] for vector in payload["vectors"]] == [
        "done_summary_view",
        "blocked_summary_view",
        "invalid_status_rejected",
    ]


def test_view_dual_run_emits_declared_report_and_passes_all_vectors(tmp_path: Path) -> None:
    report = _emit_dual_run_report(tmp_path)

    assert REPORT_PATH.is_file()
    assert report["schema_version"] == REPORT_SCHEMA_VERSION
    assert report["artifact_id"] == "view_dual_run_report"
    assert report["workflow_family"] == "design_delta_parent_drain"
    assert report["overall_status"] == "pass"
    assert report["all_passed"] is True
    assert set(report["adapters"]) == {"finalize_lisp_frontend_drain_summary"}


def test_view_dual_run_detects_expected_typed_value_mismatch(tmp_path: Path) -> None:
    payload = _load_vectors()
    vector = json.loads(json.dumps(payload["vectors"][0]))
    vector["expected_typed_value"]["drain_status_reason"] = "wrong"
    incumbent_workspace = tmp_path / "mismatch" / "incumbent"
    replacement_workspace_a = tmp_path / "mismatch" / "replacement-a"
    replacement_workspace_b = tmp_path / "mismatch" / "replacement-b"
    for case_workspace in (incumbent_workspace, replacement_workspace_a, replacement_workspace_b):
        _write_run_state(case_workspace, vector["run_state_document"])
    incumbent = _run_incumbent(vector["incumbent_inputs"], incumbent_workspace)
    replacement_first = _run_replacement_once(vector["replacement_inputs"], replacement_workspace_a)
    replacement_second = _run_replacement_once(vector["replacement_inputs"], replacement_workspace_b)

    with pytest.raises(AssertionError):
        _assert_positive_vector_matches(
            comparison_mapping_id=payload["comparison_mapping_id"],
            vector=vector,
            incumbent=incumbent,
            replacement_first=replacement_first,
            replacement_second=replacement_second,
        )


def test_view_dual_run_detects_mapping_mismatch(tmp_path: Path) -> None:
    payload = _load_vectors()
    vector = payload["vectors"][0]
    incumbent_workspace = tmp_path / "mapping" / "incumbent"
    replacement_workspace_a = tmp_path / "mapping" / "replacement-a"
    replacement_workspace_b = tmp_path / "mapping" / "replacement-b"
    for case_workspace in (incumbent_workspace, replacement_workspace_a, replacement_workspace_b):
        _write_run_state(case_workspace, vector["run_state_document"])
    incumbent = _run_incumbent(vector["incumbent_inputs"], incumbent_workspace)
    replacement_first = _run_replacement_once(vector["replacement_inputs"], replacement_workspace_a)
    replacement_second = _run_replacement_once(vector["replacement_inputs"], replacement_workspace_b)

    with pytest.raises(AssertionError):
        _assert_positive_vector_matches(
            comparison_mapping_id="wrong_mapping.v1",
            vector=vector,
            incumbent=incumbent,
            replacement_first=replacement_first,
            replacement_second=replacement_second,
        )
