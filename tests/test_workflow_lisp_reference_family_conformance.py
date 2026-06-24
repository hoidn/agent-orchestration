from __future__ import annotations

import copy
import importlib
import json
import shutil
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_STATE_PATH = (
    REPO_ROOT
    / "state"
    / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
    / "drain"
    / "run_state.json"
)
DRAIN_SUMMARY_PATH = (
    REPO_ROOT
    / "artifacts"
    / "work"
    / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
    / "drain-summary.json"
)
DESIGN_GAP_SUMMARY_ROOT = (
    REPO_ROOT
    / "artifacts"
    / "work"
    / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
    / "design-gaps"
)
IMPLEMENTATION_ARCHITECTURE_ROOT = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
    / "design-gaps"
)
ARCHITECTURE_INDEX_PATH = (
    REPO_ROOT
    / "state"
    / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
    / "drain"
    / "iterations"
    / "10"
    / "design-gap-architect"
    / "existing-architecture-index.md"
)
TARGET_DESIGN_PATH = (
    REPO_ROOT / "docs" / "design" / "workflow_lisp_runtime_native_drain_authoring.md"
)
PARITY_TARGETS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "parity_targets.json"
)
PARITY_REPORT_JSON_PATH = (
    REPO_ROOT
    / "artifacts"
    / "work"
    / "review-parity-check"
    / "design_delta_parent_drain.json"
)
PARITY_REPORT_MARKDOWN_PATH = (
    REPO_ROOT
    / "artifacts"
    / "work"
    / "review-parity-check"
    / "design_delta_parent_drain.md"
)
PARITY_INDEX_PATH = (
    REPO_ROOT / "artifacts" / "work" / "review-parity-check" / "index.json"
)
BOUNDARY_AUTHORITY_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.boundary_authority.json"
)
COMMAND_BOUNDARIES_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.commands.json"
)
VALUE_FLOW_CENSUS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.value_flow_census.json"
)
CONSUMER_RENDERING_CENSUS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.consumer_rendering_census.json"
)
COMPATIBILITY_BRIDGES_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.compatibility_bridges.json"
)
RENDERING_CLEANUP_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.rendering_cleanup.json"
)
RENDERING_ERGONOMICS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.rendering_ergonomics.json"
)
TRANSITION_AUTHORING_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.transition_authoring.json"
)
RESUME_PLUMBING_RETIREMENT_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.resume_plumbing_retirement.json"
)
OBSERVABILITY_OLD_WRITER_COMPARISONS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.observability_old_writer_comparisons.json"
)
LIVE_MISSING_GAP_IDS = [
    "workflow-lisp-runtime-native-drain-consumed-artifact-prompt-rendering-modes",
    "workflow-lisp-runtime-native-drain-high-level-boundary-state-path-retirement",
    "workflow-lisp-runtime-native-drain-shared-hidden-carried-compatibility-bridge-prompt-request-rendering",
    "workflow-lisp-runtime-native-drain-stdlib-selected-item-contract-without-item-state-root",
]


def _reference_family_module():
    return importlib.import_module(
        "orchestrator.workflow_lisp.reference_family_conformance"
    )


def _copy_json(path: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def _copy_tree(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination


def _owner_reports() -> dict[str, dict[str, object]]:
    report = {"workflow_family": "design_delta_parent_drain", "status": "pass"}
    return {
        "boundary_authority_report": {
            "workflow_family": "design_delta_parent_drain",
            "workflows": [{"workflow_name": "lisp_frontend_design_delta/drain::drain"}],
        },
        "compatibility_bridge_report": dict(report),
        "typed_prompt_input_report": dict(report),
        "rendering_cleanup_report": dict(report),
        "rendering_ergonomics_report": dict(report),
        "transition_authoring_report": dict(report),
        "resume_plumbing_retirement_report": dict(report),
        "observability_summary_report": dict(report),
        "parent_drain_census_alignment_report": dict(report),
    }


def _aligned_drain_summary_copy(tmp_path: Path) -> Path:
    payload = json.loads(DRAIN_SUMMARY_PATH.read_text(encoding="utf-8"))
    run_state = json.loads(RUN_STATE_PATH.read_text(encoding="utf-8"))
    payload["completed_design_gaps"] = list(run_state["completed_design_gaps"])
    summary_path = tmp_path / "drain-summary.json"
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return summary_path


def _reference_family_inputs(
    tmp_path: Path,
    *,
    drain_summary_path: Path | None = None,
    design_gap_summary_root: Path | None = None,
    architecture_index_path: Path | None = None,
    target_design_path: Path | None = None,
    parity_report_json_path: Path | None = None,
    parity_report_markdown_path: Path | None = None,
    parity_index_path: Path | None = None,
) -> dict[str, object]:
    return {
        "workflow_family": "design_delta_parent_drain",
        "run_state_path": RUN_STATE_PATH,
        "drain_summary_path": drain_summary_path or _aligned_drain_summary_copy(tmp_path),
        "design_gap_summary_root": design_gap_summary_root or DESIGN_GAP_SUMMARY_ROOT,
        "implementation_architecture_root": IMPLEMENTATION_ARCHITECTURE_ROOT,
        "architecture_index_path": architecture_index_path or ARCHITECTURE_INDEX_PATH,
        "target_design_path": target_design_path or TARGET_DESIGN_PATH,
        "parity_targets_path": PARITY_TARGETS_PATH,
        "parity_report_json_path": parity_report_json_path or PARITY_REPORT_JSON_PATH,
        "parity_report_markdown_path": parity_report_markdown_path
        or PARITY_REPORT_MARKDOWN_PATH,
        "parity_index_path": parity_index_path or PARITY_INDEX_PATH,
        "checked_manifest_paths": {
            "boundary_authority_manifest": BOUNDARY_AUTHORITY_PATH,
            "command_boundaries_manifest": COMMAND_BOUNDARIES_PATH,
            "value_flow_census": VALUE_FLOW_CENSUS_PATH,
            "consumer_rendering_census": CONSUMER_RENDERING_CENSUS_PATH,
            "compatibility_bridges_manifest": COMPATIBILITY_BRIDGES_PATH,
            "rendering_cleanup_manifest": RENDERING_CLEANUP_PATH,
            "rendering_ergonomics_manifest": RENDERING_ERGONOMICS_PATH,
            "transition_authoring_manifest": TRANSITION_AUTHORING_PATH,
            "resume_plumbing_retirement_manifest": RESUME_PLUMBING_RETIREMENT_PATH,
            "observability_old_writer_comparisons": OBSERVABILITY_OLD_WRITER_COMPARISONS_PATH,
        },
        "owner_reports": _owner_reports(),
        "repo_root": REPO_ROOT,
    }


def test_build_reference_family_conformance_profile_passes_for_aligned_fixture(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(tmp_path)
    )

    assert profile["schema_id"] == "workflow_lisp_reference_family_conformance_profile.v1"
    assert profile["profile_status"] == "pass"
    assert profile["completed_gap_reconciliation"]["missing_from_drain_summary"] == []
    assert profile["parity_surface_reconciliation"]["derived_primary_surface"] == "yaml"
    assert {row["input_id"] for row in profile["evidence_inputs"]} >= {
        "architecture_index",
        "target_design",
    }


def test_build_reference_family_conformance_profile_reports_known_four_gap_omission(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    summary_copy = _aligned_drain_summary_copy(tmp_path)
    payload = json.loads(summary_copy.read_text(encoding="utf-8"))
    payload["completed_design_gaps"] = [
        gap_id
        for gap_id in payload["completed_design_gaps"]
        if gap_id not in set(LIVE_MISSING_GAP_IDS)
    ]
    summary_copy.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(tmp_path, drain_summary_path=summary_copy)
    )

    assert profile["profile_status"] == "fail"
    assert profile["completed_gap_reconciliation"]["missing_from_drain_summary"] == LIVE_MISSING_GAP_IDS
    assert [
        diagnostic["code"] for diagnostic in profile["diagnostics"]
    ] == ["reference_family_completed_gap_summary_mismatch"]


def test_build_reference_family_conformance_profile_reports_missing_per_gap_summary_artifact(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    summary_root = _copy_tree(DESIGN_GAP_SUMMARY_ROOT, tmp_path / "design-gap-summaries")
    missing_gap_id = "workflow-lisp-runtime-native-drain-typed-provider-request-records"
    (summary_root / f"{missing_gap_id}-summary.json").unlink()

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(tmp_path, design_gap_summary_root=summary_root)
    )

    assert profile["profile_status"] == "fail"
    assert profile["completed_gap_reconciliation"]["missing_summary_artifacts"] == [
        missing_gap_id
    ]
    assert [
        diagnostic["code"] for diagnostic in profile["diagnostics"]
    ] == ["reference_family_completed_gap_artifact_missing"]


@pytest.mark.parametrize(
    ("missing_input_id", "architecture_index_path", "target_design_path"),
    [
        ("architecture_index", Path("/does/not/exist.md"), None),
        ("target_design", None, Path("/does/not/exist.md")),
    ],
)
def test_build_reference_family_conformance_profile_fails_closed_when_required_evidence_input_is_missing(
    tmp_path: Path,
    missing_input_id: str,
    architecture_index_path: Path | None,
    target_design_path: Path | None,
) -> None:
    module = _reference_family_module()

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(
            tmp_path,
            architecture_index_path=architecture_index_path,
            target_design_path=target_design_path,
        )
    )

    assert profile["profile_status"] == "fail"
    evidence_row = next(
        row for row in profile["evidence_inputs"] if row["input_id"] == missing_input_id
    )
    assert evidence_row["load_status"] == "missing"
    assert any(
        diagnostic["code"] == "reference_family_evidence_input_missing"
        and diagnostic["input_id"] == missing_input_id
        for diagnostic in profile["diagnostics"]
    )


def test_build_reference_family_conformance_profile_rejects_parity_surface_metadata_mismatch(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    markdown_path = _copy_json(
        PARITY_REPORT_MARKDOWN_PATH, tmp_path / "design_delta_parent_drain.md"
    )
    text = markdown_path.read_text(encoding="utf-8").replace(
        "- Primary surface: `yaml`",
        "- Primary surface: `orc`",
    )
    markdown_path.write_text(text, encoding="utf-8")

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(tmp_path, parity_report_markdown_path=markdown_path)
    )

    assert profile["profile_status"] == "fail"
    assert profile["parity_surface_reconciliation"]["derived_primary_surface"] == "yaml"
    assert profile["parity_surface_reconciliation"]["markdown_primary_surface"] == "orc"
    assert [
        diagnostic["code"] for diagnostic in profile["diagnostics"]
    ] == ["reference_family_parity_surface_mismatch"]


def test_build_reference_family_conformance_profile_rejects_malformed_parity_markdown_metadata(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    markdown_path = _copy_json(
        PARITY_REPORT_MARKDOWN_PATH, tmp_path / "design_delta_parent_drain.md"
    )
    text = markdown_path.read_text(encoding="utf-8").replace(
        "- Promotion eligible: `false`\n",
        "",
    )
    markdown_path.write_text(text, encoding="utf-8")

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(tmp_path, parity_report_markdown_path=markdown_path)
    )

    assert profile["profile_status"] == "fail"
    assert profile["parity_surface_reconciliation"]["status"] == "fail"
    assert (
        profile["parity_surface_reconciliation"]["eligible_for_primary_surface"] is None
    )
    assert [
        diagnostic["code"] for diagnostic in profile["diagnostics"]
    ] == ["reference_family_parity_report_invalid"]
    assert "missing metadata bullets: promotion_eligible" in profile["diagnostics"][0][
        "message"
    ]


def test_build_reference_family_conformance_profile_rejects_parity_report_that_fails_shared_gate_validation(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    json_path = _copy_json(
        PARITY_REPORT_JSON_PATH, tmp_path / "design_delta_parent_drain.json"
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    del payload["target_identity"]["required_family_evidence_roles"]
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(tmp_path, parity_report_json_path=json_path)
    )

    assert profile["profile_status"] == "fail"
    assert profile["parity_surface_reconciliation"]["status"] == "fail"
    assert profile["parity_surface_reconciliation"]["derived_primary_surface"] is None
    assert [
        diagnostic["code"] for diagnostic in profile["diagnostics"]
    ] == ["reference_family_parity_report_invalid"]


def test_build_reference_family_conformance_profile_requires_explicit_passing_owner_reports(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    owner_reports = copy.deepcopy(_owner_reports())
    owner_reports["typed_prompt_input_report"] = {}
    owner_reports["rendering_ergonomics_report"] = {}

    profile = module.build_reference_family_conformance_profile(
        **{
            **_reference_family_inputs(tmp_path),
            "owner_reports": owner_reports,
        }
    )

    assert profile["profile_status"] == "fail"
    surface_rows = {
        row["surface_id"]: row["status"] for row in profile["surface_rows"]
    }
    assert surface_rows["provider_inputs"] == "fail"
    assert surface_rows["provider_write_targets"] == "fail"
    assert [
        diagnostic["code"] for diagnostic in profile["diagnostics"]
    ] == ["reference_family_surface_incomplete"]


def test_build_reference_family_conformance_profile_derives_yaml_primary_for_non_promotable_report(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(tmp_path)
    )

    parity = profile["parity_surface_reconciliation"]

    assert parity["eligible_for_primary_surface"] is False
    assert parity["derived_primary_surface"] == "yaml"


def test_parse_parity_markdown_metadata_ignores_non_metadata_prose() -> None:
    module = _reference_family_module()
    text = """# Parity Report: design_delta_parent_drain

Intro prose that should not be parsed.
- Primary surface: `orc`

- Non-regressive: `true`
- Promotion eligible: `false`
- Primary surface: `yaml`

Trailing prose that should not be parsed either.
"""

    metadata = module.parse_parity_markdown_metadata(text)

    assert metadata == {
        "non_regressive": True,
        "promotion_eligible": False,
        "primary_surface": "yaml",
    }
