"""Tests for Workflow Lisp observability-derived terminal summaries."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.consumer_rendering_census import (
    CONSUMER_RENDERING_CENSUS_SCHEMA_VERSION,
)

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


def _checks_report_pair_row_ids() -> tuple[str, str]:
    return (
        "c0.implementation_phase_materialized_return_checks_report",
        "c0.implementation_phase_materialized_return_checks_report_compiled_boundary",
    )


def _checks_report_workflow_surface() -> str:
    return "lisp_frontend_design_delta/implementation_phase::implementation-phase"


def _checks_report_old_writer_suffix() -> str:
    return "__materialize_view__blocked_implementation_checks_report"


def _legacy_checks_report_payload() -> dict[str, object]:
    return {
        "status": "BLOCKED",
        "progress_report": "artifacts/work/progress_report.md",
        "blocker_class": "unrecoverable_after_fix_attempt",
    }


def _replacement_typed_summary_fragment() -> dict[str, object]:
    return {
        "status": "BLOCKED",
        "progress_report": "artifacts/work/progress_report.md",
        "blocker_class": "unrecoverable_after_fix_attempt",
    }


def _write_old_writer_pair_manifest(
    tmp_path: Path,
    module,
    *,
    legacy_payload_path: Path | None = None,
    replacement_payload: dict[str, object] | None = None,
    pair_overrides: dict[str, object] | None = None,
) -> Path:
    legacy_payload = _legacy_checks_report_payload()
    replacement_payload = (
        _replacement_typed_summary_fragment()
        if replacement_payload is None
        else replacement_payload
    )
    if legacy_payload_path is None:
        legacy_payload_path = _write_json(
            tmp_path / "checked" / "legacy_writer_payload.json",
            legacy_payload,
        )
    primary_row_id, mirror_row_id = _checks_report_pair_row_ids()
    pair_payload = {
        "primary_row_id": primary_row_id,
        "mirror_row_id": mirror_row_id,
        "workflow_surface": _checks_report_workflow_surface(),
        "comparison_inputs": {
            "old_writer_payload": legacy_payload,
            "replacement_typed_summary_payload": replacement_payload,
        },
        "old_writer": {
            "step_id_suffix": _checks_report_old_writer_suffix(),
            "renderer_id": "canonical-json",
            "renderer_version": 1,
            "payload_source": "comparison_inputs.old_writer_payload",
        },
        "replacement": {
            "evidence_kind": "old_writer_comparison",
            "authority_surface": "workflow_lisp_observability_summary.v1",
            "authority_path": "RUN_ROOT/summaries/typed-terminal-summary.json",
            "contract_profile": "terminal_value",
            "payload_source": "comparison_inputs.replacement_typed_summary_payload",
            "comparison_digest_kind": "sha256",
            "typed_summary_digest": module._sha256_json(replacement_payload),
            "old_writer_payload_digest": module._sha256_json(legacy_payload),
        },
        "status": "live_old_writer",
        "source_evidence": [
            {
                "kind": "legacy_writer_payload_source",
                "side": "old_writer_payload",
                "authority_lane": "design_delta_migration_inputs",
                "path": str(legacy_payload_path),
                "payload_pointer": "$",
            },
            {
                "kind": "typed_summary_contract",
                "side": "replacement_typed_summary_payload",
                "authority_surface": "workflow_lisp_observability_summary.v1",
                "path": "RUN_ROOT/summaries/typed-terminal-summary.json",
                "contract_profile": "terminal_value",
            },
        ],
    }
    if pair_overrides:
        pair_payload.update(pair_overrides)
    payload = {
        "schema_version": "workflow_lisp_observability_old_writer_comparisons.v1",
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "row_pairs": [pair_payload],
    }
    return _write_json(tmp_path / "checked" / "old_writer_pairs.json", payload)


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


def test_old_writer_contract_evidence_is_not_required_for_timed_observability_rows() -> None:
    module = _module()
    rows = {
        row["row_id"]: row
        for row in json.loads(_manifest_path().read_text(encoding="utf-8"))["rows"]
    }

    assert module.row_requires_old_writer_contract_evidence(
        rows["c0.drain_summary_report_target_final_summary_view"]
    )
    assert not module.row_requires_old_writer_contract_evidence(
        rows["c0.implementation_phase_materialized_return_checks_report"]
    )


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


def test_load_old_writer_pair_manifest_accepts_linked_checks_report_rows(tmp_path: Path) -> None:
    module = _module()
    manifest_path = _write_old_writer_pair_manifest(tmp_path, module)

    payload = module.load_old_writer_pair_manifest(
        manifest_path,
        consumer_rendering_manifest_path=_manifest_path(),
    )

    row_pair = payload["row_pairs"][0]
    assert row_pair["primary_row_id"] == _checks_report_pair_row_ids()[0]
    assert row_pair["mirror_row_id"] == _checks_report_pair_row_ids()[1]
    assert row_pair["old_writer"]["step_id_suffix"] == _checks_report_old_writer_suffix()
    assert (
        row_pair["replacement"]["typed_summary_digest"]
        == module._sha256_json(_replacement_typed_summary_fragment())
    )


def test_load_old_writer_pair_manifest_resolves_legacy_payload_path_relative_to_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    manifest_path = _write_old_writer_pair_manifest(tmp_path, module)
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    legacy_payload_path = Path(
        manifest_payload["row_pairs"][0]["source_evidence"][0]["path"]
    )
    manifest_payload["row_pairs"][0]["source_evidence"][0]["path"] = str(
        legacy_payload_path.relative_to(manifest_path.parent)
    )
    _write_json(manifest_path, manifest_payload)

    monkeypatch.chdir("/tmp")

    payload = module.load_old_writer_pair_manifest(
        manifest_path,
        consumer_rendering_manifest_path=_manifest_path(),
    )

    assert payload["row_pairs"][0]["comparison_inputs"]["old_writer_payload"] == (
        _legacy_checks_report_payload()
    )


def test_load_old_writer_pair_manifest_rejects_self_authenticated_legacy_payload_source(
    tmp_path: Path,
) -> None:
    module = _module()
    manifest_path = _write_old_writer_pair_manifest(tmp_path, module)
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_payload["row_pairs"][0]["source_evidence"][0]["path"] = str(manifest_path)
    _write_json(manifest_path, manifest_payload)

    with pytest.raises(ValueError, match="observability_summary_old_writer_used_as_state"):
        module.load_old_writer_pair_manifest(
            manifest_path,
            consumer_rendering_manifest_path=_manifest_path(),
        )


def test_load_old_writer_pair_manifest_rejects_fabricated_selected_item_payload_shape(
    tmp_path: Path,
) -> None:
    module = _module()
    fabricated_payload = {
        "report_kind": "checks",
        "selected_item": "docs/design/example.md",
        "status": "BLOCKED",
    }
    manifest_path = _write_old_writer_pair_manifest(
        tmp_path,
        module,
        replacement_payload={
            "status": "BLOCKED",
            "selected_item": "docs/design/example.md",
        },
        pair_overrides={
            "comparison_inputs": {
                "old_writer_payload": fabricated_payload,
                "replacement_typed_summary_payload": {
                    "status": "BLOCKED",
                    "selected_item": "docs/design/example.md",
                },
            },
            "replacement": {
                "evidence_kind": "old_writer_comparison",
                "authority_surface": "workflow_lisp_observability_summary.v1",
                "authority_path": "RUN_ROOT/summaries/typed-terminal-summary.json",
                "contract_profile": "terminal_value",
                "payload_source": "comparison_inputs.replacement_typed_summary_payload",
                "comparison_digest_kind": "sha256",
                "typed_summary_digest": module._sha256_json(
                    {
                        "status": "BLOCKED",
                        "selected_item": "docs/design/example.md",
                    }
                ),
                "old_writer_payload_digest": module._sha256_json(fabricated_payload),
            },
        },
    )
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    legacy_payload_path = Path(
        manifest_payload["row_pairs"][0]["source_evidence"][0]["path"]
    )
    _write_json(legacy_payload_path, fabricated_payload)

    with pytest.raises(ValueError, match="observability_summary_old_writer_evidence_stale"):
        module.load_old_writer_pair_manifest(
            manifest_path,
            consumer_rendering_manifest_path=_manifest_path(),
        )


def test_load_old_writer_pair_manifest_rejects_missing_comparison_digest_fields(
    tmp_path: Path,
) -> None:
    module = _module()
    manifest_path = _write_old_writer_pair_manifest(
        tmp_path,
        module,
        pair_overrides={"replacement": {"evidence_kind": "old_writer_comparison"}},
    )

    with pytest.raises(ValueError, match="observability_summary_old_writer_evidence_stale"):
        module.load_old_writer_pair_manifest(
            manifest_path,
            consumer_rendering_manifest_path=_manifest_path(),
        )


def test_load_old_writer_pair_manifest_rejects_missing_compiled_boundary_mirror(
    tmp_path: Path,
) -> None:
    module = _module()
    manifest_path = _write_old_writer_pair_manifest(
        tmp_path,
        module,
        pair_overrides={"mirror_row_id": ""},
    )

    with pytest.raises(ValueError, match="observability_summary_old_writer_mirror_missing"):
        module.load_old_writer_pair_manifest(
            manifest_path,
            consumer_rendering_manifest_path=_manifest_path(),
        )


def test_load_old_writer_pair_manifest_rejects_stale_writer_suffix(tmp_path: Path) -> None:
    module = _module()
    stale_old_writer = copy.deepcopy(
        _write_old_writer_pair_manifest(tmp_path, module)
    )
    manifest_payload = json.loads(Path(stale_old_writer).read_text(encoding="utf-8"))
    manifest_payload["row_pairs"][0]["old_writer"]["step_id_suffix"] = "__stale_suffix"
    _write_json(stale_old_writer, manifest_payload)

    with pytest.raises(ValueError, match="observability_summary_old_writer_evidence_stale"):
        module.load_old_writer_pair_manifest(
            stale_old_writer,
            consumer_rendering_manifest_path=_manifest_path(),
        )


def test_load_old_writer_pair_manifest_rejects_inline_payload_drift_from_authoritative_source(
    tmp_path: Path,
) -> None:
    module = _module()
    legacy_payload_path = _write_json(
        tmp_path / "checked" / "legacy_writer_payload.json",
        _legacy_checks_report_payload(),
    )
    manifest_path = _write_old_writer_pair_manifest(
        tmp_path,
        module,
        legacy_payload_path=legacy_payload_path,
    )
    _write_json(
        legacy_payload_path,
        {
            "status": "APPROVED",
            "progress_report": "artifacts/work/progress_report.md",
            "blocker_class": "unrecoverable_after_fix_attempt",
        },
    )

    with pytest.raises(ValueError, match="observability_summary_old_writer_evidence_stale"):
        module.load_old_writer_pair_manifest(
            manifest_path,
            consumer_rendering_manifest_path=_manifest_path(),
        )


def test_build_observability_pair_report_selects_primary_and_mirror_together(
    tmp_path: Path,
) -> None:
    module = _module()
    manifest_path = _write_old_writer_pair_manifest(tmp_path, module)
    pair_manifest = module.load_old_writer_pair_manifest(
        manifest_path,
        consumer_rendering_manifest_path=_manifest_path(),
    )
    consumer_manifest = json.loads(_manifest_path().read_text(encoding="utf-8"))
    report = module.build_observability_pair_report(
        consumer_rendering_census=consumer_manifest,
        pair_manifest=pair_manifest,
        materialize_view_effects=[],
    )

    assert report["status"] == "pass"
    assert report["selected_c0_row_ids"] == list(_checks_report_pair_row_ids())


def test_build_observability_pair_report_rejects_progress_report_path_drift(
    tmp_path: Path,
) -> None:
    module = _module()
    manifest_path = _write_old_writer_pair_manifest(
        tmp_path,
        module,
        replacement_payload={
            "status": "BLOCKED",
            "progress_report": "artifacts/work/changed_progress_report.md",
            "blocker_class": "unrecoverable_after_fix_attempt",
        },
    )
    pair_manifest = module.load_old_writer_pair_manifest(
        manifest_path,
        consumer_rendering_manifest_path=_manifest_path(),
    )
    consumer_manifest = json.loads(_manifest_path().read_text(encoding="utf-8"))

    report = module.build_observability_pair_report(
        consumer_rendering_census=consumer_manifest,
        pair_manifest=pair_manifest,
        materialize_view_effects=[],
    )

    assert report["status"] == "fail"
    assert report["selected_c0_row_ids"] == []
    assert {
        diagnostic["code"]
        for diagnostic in report["diagnostics"]["errors"]
    } == {"observability_summary_old_writer_evidence_stale"}
    assert report["pair_results"][0]["status"] == "fail"
    assert report["pair_results"][0]["comparison_status"] == "mismatch"


def test_build_observability_pair_report_rejects_blocker_class_drift(
    tmp_path: Path,
) -> None:
    module = _module()
    manifest_path = _write_old_writer_pair_manifest(
        tmp_path,
        module,
        replacement_payload={
            "status": "BLOCKED",
            "progress_report": "artifacts/work/progress_report.md",
            "blocker_class": "missing_resource",
        },
    )
    pair_manifest = module.load_old_writer_pair_manifest(
        manifest_path,
        consumer_rendering_manifest_path=_manifest_path(),
    )
    consumer_manifest = json.loads(_manifest_path().read_text(encoding="utf-8"))

    report = module.build_observability_pair_report(
        consumer_rendering_census=consumer_manifest,
        pair_manifest=pair_manifest,
        materialize_view_effects=[],
    )

    assert report["status"] == "fail"
    assert report["selected_c0_row_ids"] == []
    assert {
        diagnostic["code"]
        for diagnostic in report["diagnostics"]["errors"]
    } == {"observability_summary_old_writer_evidence_stale"}
    assert report["pair_results"][0]["status"] == "fail"
    assert report["pair_results"][0]["comparison_status"] == "mismatch"


def test_build_observability_pair_report_rejects_accepted_absence_while_writer_effect_live(
    tmp_path: Path,
) -> None:
    module = _module()
    manifest_path = _write_old_writer_pair_manifest(tmp_path, module)
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_payload["row_pairs"][0]["replacement"]["evidence_kind"] = "accepted_absence"
    manifest_payload["row_pairs"][0]["replacement"]["accepted_absence_reason"] = (
        "old writer retired"
    )
    manifest_payload["row_pairs"][0]["status"] = "retired_to_observability"
    _write_json(manifest_path, manifest_payload)
    pair_manifest = module.load_old_writer_pair_manifest(
        manifest_path,
        consumer_rendering_manifest_path=_manifest_path(),
    )
    consumer_manifest = json.loads(_manifest_path().read_text(encoding="utf-8"))

    report = module.build_observability_pair_report(
        consumer_rendering_census=consumer_manifest,
        pair_manifest=pair_manifest,
        materialize_view_effects=[
            {
                "authority_class": "materialized_view",
                "step_id": (
                    "implementation_phase"
                    ".__materialize_view__blocked_implementation_checks_report"
                ),
                "workflow_surface": _checks_report_workflow_surface(),
            }
        ],
    )

    assert report["status"] == "fail"
    assert report["selected_c0_row_ids"] == []
    assert {
        diagnostic["code"]
        for diagnostic in report["diagnostics"]["errors"]
    } == {"observability_summary_old_writer_effect_still_live"}
    assert report["pair_results"][0]["status"] == "fail"
    assert report["pair_results"][0]["old_writer_effect_live"] is True


def test_observability_summary_retains_consumer_census_schema_kernel() -> None:
    assert (
        CONSUMER_RENDERING_CENSUS_SCHEMA_VERSION
        == "workflow_lisp_consumer_rendering_census.v1"
    )
