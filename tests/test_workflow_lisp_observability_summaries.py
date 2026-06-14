"""Tests for Workflow Lisp observability-derived terminal summaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow.transition_contract import serialize_transition_audit_record


def _module():
    import importlib

    return importlib.import_module("orchestrator.workflow_lisp.observability_summaries")


def _manifest_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "workflows"
        / "examples"
        / "inputs"
        / "workflow_lisp_migrations"
        / "design_delta_parent_drain.consumer_rendering_census.json"
    )


def _terminal_value() -> dict[str, object]:
    return {
        "status": "BLOCKED",
        "selected_item": "docs/design/example.md",
        "blocker_class": "missing_resource",
        "reason": "fixture blocker",
        "diagnostics": [
            {
                "code": "fixture_warning",
                "message": "used for observability rendering tests",
            }
        ],
    }


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_audit(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(serialize_transition_audit_record(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _summary_inputs(tmp_path: Path) -> dict[str, object]:
    run_root = tmp_path / ".orchestrate" / "runs" / "run-c2"
    state = {
        "run_id": "run-c2",
        "status": "completed",
        "workflow_outputs": _terminal_value(),
    }
    audit_path = _write_audit(
        run_root / "runtime-audits" / "design-delta-transition-audit.jsonl",
        [
            {
                "transition_name": "record_selected_item_outcome",
                "resource_kind": "drain_status",
                "resource_id": "design-delta-parent-drain",
                "idempotency_key": "idem-1",
                "request_digest": "sha256:req",
                "outcome_code": "committed",
                "version": "3",
                "result": {"status": "BLOCKED", "selected_item": "docs/design/example.md"},
            }
        ],
    )
    legacy_path = _write_json(
        run_root / "artifacts" / "work" / "drain_summary.json",
        {
            "status": "BLOCKED",
            "selected_item": "docs/design/example.md",
            "blocker_class": "missing_resource",
        },
    )
    return {
        "run_root": run_root,
        "workflow_family": "lisp_frontend_design_delta_parent_drain",
        "workflow_surface": "lisp_frontend_design_delta/drain::drain",
        "state": state,
        "manifest_path": _manifest_path(),
        "audit_paths": [audit_path],
        "old_writer_paths": {"c0.drain_summary_report_target_final_summary_view": legacy_path},
    }


def test_select_observability_rows_uses_checked_c0_manifest() -> None:
    module = _module()

    rows = module.select_observability_rows(_manifest_path())
    row_ids = {row["row_id"] for row in rows}

    assert "c0.drain_summary_report_target_final_summary_view" in row_ids
    assert all(
        row["consumer_lane"] == "human_observability"
        or row["track_c_decision"] == "RETIRE_TO_OBSERVABILITY"
        for row in rows
    )


def test_select_observability_rows_can_scope_to_one_workflow_surface() -> None:
    module = _module()

    rows = module.select_observability_rows(
        _manifest_path(),
        workflow_surface="lisp_frontend_design_delta/drain::drain",
    )

    assert rows
    assert {
        row["workflow_surface"]
        for row in rows
    } == {"lisp_frontend_design_delta/drain::drain"}


def test_normalize_terminal_value_uses_workflow_outputs_and_stable_digest(tmp_path: Path) -> None:
    module = _module()

    normalized = module.normalize_terminal_value(_summary_inputs(tmp_path)["state"])

    assert normalized["source"] == "state.workflow_outputs"
    assert normalized["value"] == _terminal_value()
    assert normalized["digest"].startswith("sha256:")


def test_project_transition_audit_rows_collects_digest_and_rows(tmp_path: Path) -> None:
    module = _module()
    inputs = _summary_inputs(tmp_path)

    projected = module.project_transition_audit(inputs["audit_paths"])

    assert projected["status"] == "available"
    assert projected["row_count"] == 1
    assert projected["audit_files"][0]["digest"].startswith("sha256:")


def test_render_summary_outputs_required_json_and_markdown_fields(tmp_path: Path) -> None:
    module = _module()
    inputs = _summary_inputs(tmp_path)

    payload, markdown, index_entry, report = module.build_observability_summary(**inputs)

    assert payload["schema_id"] == "workflow_lisp_observability_summary.v1"
    assert payload["authority"] == "observability_only"
    assert payload["paths"]["json"] == "summaries/typed-terminal-summary.json"
    assert payload["paths"]["markdown"] == "summaries/typed-terminal-summary.md"
    assert report["schema_id"] == "workflow_lisp_observability_summary_report.v1"
    assert index_entry["kind"] == "typed_terminal"
    assert index_entry["authority"] == "observability_only"
    assert "observability-only" in markdown


def test_old_writer_comparison_payload_is_emitted_for_retirement_row(tmp_path: Path) -> None:
    module = _module()
    inputs = _summary_inputs(tmp_path)

    payload, _markdown, _index_entry, report = module.build_observability_summary(**inputs)

    comparisons = payload["old_writer_comparisons"]
    assert comparisons
    assert comparisons[0]["row_id"] == "c0.drain_summary_report_target_final_summary_view"
    assert comparisons[0]["status"] in {"match", "different"}
    assert report["status"] == "pass"


def test_normalize_terminal_value_uses_validated_projection_when_outputs_absent() -> None:
    module = _module()

    normalized = module.normalize_terminal_value(
        {"run_id": "run-c2", "status": "completed"},
        validated_terminal_projection=_terminal_value(),
    )

    assert normalized["source"] == "validated_terminal_projection"
    assert normalized["value"] == _terminal_value()
    assert normalized["digest"].startswith("sha256:")


def test_build_summary_rejects_missing_terminal_value(tmp_path: Path) -> None:
    module = _module()
    inputs = _summary_inputs(tmp_path)
    inputs["state"] = {"run_id": "run-c2", "status": "completed"}

    with pytest.raises(ValueError, match="observability_summary_terminal_value_missing"):
        module.build_observability_summary(**inputs)


def test_build_summary_rejects_malformed_terminal_value(tmp_path: Path) -> None:
    module = _module()
    inputs = _summary_inputs(tmp_path)
    inputs["state"] = {
        "run_id": "run-c2",
        "status": "completed",
        "workflow_outputs": {"bad": {1, 2, 3}},
    }

    with pytest.raises(ValueError, match="observability_summary_terminal_value_invalid"):
        module.build_observability_summary(**inputs)


def test_project_transition_audit_rejects_invalid_jsonl_rows(tmp_path: Path) -> None:
    module = _module()
    bad_path = tmp_path / ".orchestrate" / "runs" / "run-c2" / "runtime-audits" / "bad.jsonl"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="observability_summary_transition_audit_invalid"):
        module.project_transition_audit([bad_path])


def test_build_summary_reports_invalid_transition_audit_without_dropping_artifacts(tmp_path: Path) -> None:
    module = _module()
    inputs = _summary_inputs(tmp_path)
    bad_path = Path(inputs["audit_paths"][0])
    bad_path.write_text("{not-json}\n", encoding="utf-8")

    payload, markdown, index_entry, report = module.build_observability_summary(**inputs)

    assert payload["transition_audit"]["status"] == "invalid"
    assert report["status"] == "fail"
    assert "observability_summary_transition_audit_invalid" in {
        diagnostic["code"]
        for diagnostic in report["diagnostics"]["errors"]
    }
    assert index_entry["kind"] == "typed_terminal"
    assert "observability_summary_transition_audit_invalid" in markdown


def test_build_summary_rejects_summary_payload_as_semantic_authority(tmp_path: Path) -> None:
    module = _module()
    inputs = _summary_inputs(tmp_path)
    summary_path = inputs["run_root"] / "summaries" / "typed-terminal-summary.json"
    _write_json(summary_path, {"status": "completed"})
    inputs["state"] = {
        "run_id": "run-c2",
        "status": "completed",
        "workflow_outputs": {"summary_path": str(summary_path)},
    }

    with pytest.raises(ValueError, match="observability_summary_used_as_state"):
        module.build_observability_summary(**inputs)


def test_build_summary_requires_old_writer_comparison_for_retirement_rows(tmp_path: Path) -> None:
    module = _module()
    inputs = _summary_inputs(tmp_path)
    inputs["old_writer_paths"] = {}

    payload, _markdown, _index_entry, report = module.build_observability_summary(**inputs)

    assert payload["old_writer_comparisons"] == []
    assert report["status"] == "fail"
    assert "observability_summary_old_writer_comparison_missing" in {
        diagnostic["code"]
        for diagnostic in report["diagnostics"]["errors"]
    }


def test_build_summary_limits_retirement_comparisons_to_runtime_visible_rows(tmp_path: Path) -> None:
    module = _module()
    inputs = _summary_inputs(tmp_path)

    payload, _markdown, _index_entry, report = module.build_observability_summary(**inputs)

    assert len(payload["old_writer_comparisons"]) == 1
    assert payload["selected_c0_row_ids"] == [
        "c0.drain_summary_report_target_final_summary_view"
    ]
    assert report["status"] == "pass"
    assert report["diagnostics"]["errors"] == []
