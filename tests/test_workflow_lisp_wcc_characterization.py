from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.workflow_lisp_characterization import (
    CHARACTERIZATION_MANIFEST_PATH,
    build_behavior_observation,
    build_structural_snapshot,
    build_structural_snapshot_metadata,
    compare_structural_snapshots,
    load_characterization_cases,
)
from orchestrator.workflow_lisp.wcc.route import LoweringRoute


M5_ROUTE_FLIP_CASE_IDS = (
    "value_only_minimal_module",
    "straight_line_provider_phase",
    "wcc_m2_straight_line_effects",
    "proc_ref_bind_proc_forwarding",
    "top_level_match_attempt",
    "top_level_loop_recur",
    "stdlib_review_revise_loop",
    "wcc_m4_loop_under_case",
    "wcc_m4_implementation_phase_full_fixture",
    "module_graph_imported_bundle_mix",
    "design_delta_union_match_projection",
    "wcc_m3_nested_non_tail_match",
    "wcc_ifexpr_tail",
    "wcc_ifexpr_non_tail_binding",
    "wcc_ifexpr_loop_body",
)
WCC_IFEXPR_CASE_IDS = (
    "wcc_ifexpr_tail",
    "wcc_ifexpr_non_tail_binding",
    "wcc_ifexpr_loop_body",
)
BEHAVIOR_CASE_IDS = (
    "straight_line_provider_phase",
    "top_level_match_attempt",
    "top_level_loop_recur",
    "stdlib_review_revise_loop",
    "wcc_m4_implementation_phase_full_fixture",
)


def _characterization_cases_for_ids(case_ids: tuple[str, ...]):
    cases_by_id = {
        case.case_id: case
        for case in load_characterization_cases()
    }
    return tuple(cases_by_id[case_id] for case_id in case_ids)


def _allowed_m5_diagnostics(case_id: str) -> set[str]:
    if case_id == "wcc_m4_loop_under_case":
        return {"variant_output_without_variant_specific_fields"}
    return set()


def _walk_steps(steps: list[dict[str, object]]):
    for step in steps:
        yield step
        match_block = step.get("match")
        if isinstance(match_block, dict):
            for case_payload in match_block.get("cases", {}).values():
                if isinstance(case_payload, dict):
                    yield from _walk_steps(case_payload.get("steps", []))
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            yield from _walk_steps(repeat_until.get("steps", []))
        then_block = step.get("then")
        if isinstance(then_block, dict):
            yield from _walk_steps(then_block.get("steps", []))
        else_block = step.get("else")
        if isinstance(else_block, dict):
            yield from _walk_steps(else_block.get("steps", []))


def _has_authored_if_step(snapshot: dict[str, object]) -> bool:
    for workflow in snapshot["lowered_workflows"]:
        authored_mapping = workflow["authored_mapping"]
        for step in _walk_steps(authored_mapping.get("steps", [])):
            if "if" in step:
                return True
            pure_projection = step.get("pure_projection")
            if (
                isinstance(pure_projection, dict)
                and pure_projection.get("payload", {}).get("expr", {}).get("kind") == "if"
            ):
                return True
    return False


def test_manifest_covers_required_m0_tags() -> None:
    cases = load_characterization_cases()

    assert CHARACTERIZATION_MANIFEST_PATH.is_file()
    assert {tag for case in cases for tag in case.tags} == {
        "value_only",
        "straight_line",
        "match",
        "loop",
        "review_loop",
        "module_graph",
        "design_delta_leaf",
        "ifexpr",
    }


def test_manifest_tags_are_present_exactly_once() -> None:
    cases = load_characterization_cases()
    tag_counts: dict[str, int] = {}
    for case in cases:
        for tag in case.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    assert tag_counts["value_only"] == 1
    assert tag_counts["straight_line"] == 3
    assert tag_counts["match"] == 4
    assert tag_counts["loop"] == 3
    assert tag_counts["review_loop"] == 2
    assert tag_counts["module_graph"] == 1
    assert tag_counts["design_delta_leaf"] == 1
    assert tag_counts["ifexpr"] == 3


def test_manifest_behavior_contracts_are_complete() -> None:
    cases = load_characterization_cases()

    for case in cases:
        if case.evidence_mode == "structural_and_behavioral":
            assert case.golden_behavior is not None
            assert case.behavior_runtime is not None
            assert case.behavior_runtime.bound_inputs
        else:
            assert case.golden_behavior is None
            assert case.behavior_runtime is None


def test_m5_full_implementation_fixture_is_behavioral_gate() -> None:
    case = {
        case.case_id: case
        for case in load_characterization_cases()
    }["wcc_m4_implementation_phase_full_fixture"]

    assert case.evidence_mode == "structural_and_behavioral"
    assert case.golden_behavior is not None
    assert case.behavior_runtime is not None


def test_design_delta_case_uses_checked_in_characterization_source() -> None:
    cases = {case.case_id: case for case in load_characterization_cases()}
    case = cases["design_delta_union_match_projection"]

    assert case.source_path == Path(
        "tests/fixtures/workflow_lisp/characterization/sources/design_delta_union_match_projection.orc"
    )


def test_manifest_goldens_exist_and_match_evidence_mode() -> None:
    for case in load_characterization_cases():
        assert (Path.cwd() / case.golden_structural).is_file()
        if case.evidence_mode == "structural_and_behavioral":
            assert case.golden_behavior is not None
            assert (Path.cwd() / case.golden_behavior).is_file()
        else:
            assert case.golden_behavior is None


def test_manifest_declares_empty_rename_maps_for_m0_cases() -> None:
    for case in load_characterization_cases():
        assert set(case.declared_rename_map) == {"step_labels", "generated_input_names"}
        assert case.declared_rename_map["step_labels"] == {}
        assert case.declared_rename_map["generated_input_names"] == {}


def test_manifest_marks_only_expected_cases_for_dual_compile_routes() -> None:
    cases = {case.case_id: case for case in load_characterization_cases()}

    assert cases["value_only_minimal_module"].dual_compile_routes == ("legacy", "wcc_m1")
    assert cases["wcc_m2_straight_line_effects"].dual_compile_routes == ("legacy", "wcc_m2")
    assert cases["proc_ref_bind_proc_forwarding"].dual_compile_routes == ("legacy", "wcc_m2")
    assert cases["top_level_match_attempt"].dual_compile_routes == ("legacy", "wcc_m4")
    assert cases["design_delta_union_match_projection"].dual_compile_routes == ("legacy", "wcc_m3")
    assert cases["top_level_loop_recur"].dual_compile_routes == ("legacy", "wcc_m4")
    assert cases["stdlib_review_revise_loop"].dual_compile_routes == ("legacy", "wcc_m4")
    assert cases["wcc_m4_loop_under_case"].dual_compile_routes == ("wcc_m4",)
    assert cases["wcc_ifexpr_tail"].dual_compile_routes == ("legacy", "wcc_m4")
    assert cases["wcc_ifexpr_non_tail_binding"].dual_compile_routes == ("legacy", "wcc_m4")
    assert cases["wcc_ifexpr_loop_body"].dual_compile_routes == ("legacy", "wcc_m4")
    for case_id, case in cases.items():
        if case_id in {
            "value_only_minimal_module",
            "wcc_m2_straight_line_effects",
            "proc_ref_bind_proc_forwarding",
            "top_level_match_attempt",
            "design_delta_union_match_projection",
            "top_level_loop_recur",
            "stdlib_review_revise_loop",
            "wcc_m4_loop_under_case",
            "wcc_ifexpr_tail",
            "wcc_ifexpr_non_tail_binding",
            "wcc_ifexpr_loop_body",
        }:
            continue
        assert case.dual_compile_routes == ()


def test_retired_characterization_sources_are_not_active_wcc_evidence() -> None:
    active_sources = {case.source_path.as_posix() for case in load_characterization_cases()}
    retired_sources = {
        "tests/fixtures/workflow_lisp/characterization/sources/wcc_m3_branch_local_ref_leak.orc",
        "tests/fixtures/workflow_lisp/characterization/sources/wcc_m3_nested_join_inside_arm.orc",
    }

    assert retired_sources.isdisjoint(active_sources)
    for source in retired_sources:
        assert (Path(__file__).resolve().parent.parent / source).is_file()


def test_m5_route_flip_corpus_has_no_normal_exclusions() -> None:
    cases = load_characterization_cases()
    for case in cases:
        if case.historical_legacy_fixture:
            assert not case.route_flip_corpus
        else:
            assert case.route_flip_corpus, f"{case.case_id} is a normal corpus case and cannot be excluded from M5"


def test_characterization_parameter_id_groups_match_manifest_filters() -> None:
    cases = load_characterization_cases()

    assert tuple(
        case.case_id for case in cases if case.route_flip_corpus
    ) == M5_ROUTE_FLIP_CASE_IDS
    assert tuple(
        case.case_id for case in cases if "ifexpr" in case.tags
    ) == WCC_IFEXPR_CASE_IDS
    assert tuple(
        case.case_id
        for case in cases
        if case.evidence_mode == "structural_and_behavioral"
    ) == BEHAVIOR_CASE_IDS


@pytest.mark.parametrize(
    "case",
    _characterization_cases_for_ids(M5_ROUTE_FLIP_CASE_IDS),
    ids=M5_ROUTE_FLIP_CASE_IDS,
)
def test_m5_route_flip_corpus_compiles_under_wcc_candidate_route(tmp_path: Path, case) -> None:
    actual = build_structural_snapshot(case, tmp_path / case.case_id, lowering_route=LoweringRoute.WCC_M4)

    assert {diagnostic["code"] for diagnostic in actual["diagnostics"]} <= _allowed_m5_diagnostics(case.case_id)
    assert actual["workflow_names"] or actual["compiled_module_names"]


@pytest.mark.parametrize(
    "case",
    _characterization_cases_for_ids(M5_ROUTE_FLIP_CASE_IDS),
    ids=M5_ROUTE_FLIP_CASE_IDS,
)
def test_m5_route_flip_corpus_compiles_under_default_wcc_route(tmp_path: Path, case) -> None:
    actual = build_structural_snapshot(case, tmp_path / case.case_id, lowering_route=None)

    assert {diagnostic["code"] for diagnostic in actual["diagnostics"]} <= _allowed_m5_diagnostics(case.case_id)
    assert actual["workflow_names"] or actual["compiled_module_names"]


@pytest.mark.parametrize(
    "case",
    [
        case
        for case in load_characterization_cases()
        if case.case_id != "wcc_m3_nested_non_tail_match"
    ],
    ids=lambda case: case.case_id,
)
def test_characterization_structural_cases_match_golden(tmp_path: Path, case) -> None:
    lowering_route = (
        "wcc_m4"
        if case.case_id in {"wcc_m4_loop_under_case", "wcc_m4_implementation_phase_full_fixture"}
        or "ifexpr" in case.tags
        else "legacy"
    )
    actual = build_structural_snapshot(case, tmp_path, lowering_route=lowering_route)
    golden = json.loads((Path.cwd() / case.golden_structural).read_text(encoding="utf-8"))

    assert compare_structural_snapshots(actual, golden, case.declared_rename_map) == "identical"


def test_command_bearing_cases_declare_boundaries_and_module_graph_uses_import_manifest() -> None:
    cases = {case.case_id: case for case in load_characterization_cases()}

    straight_line = cases["wcc_m2_straight_line_effects"]
    assert straight_line.provider_externs == {"providers.execute": "fake"}
    assert straight_line.prompt_externs == {
        "prompts.implementation.execute": "prompts/implementation/execute.md"
    }
    assert straight_line.command_boundaries == {
        "run_checks": {
            "kind": "external_tool",
            "stable_command": ["python", "scripts/run_checks.py"],
        }
    }

    proc_ref = cases["proc_ref_bind_proc_forwarding"]
    assert proc_ref.provider_externs is None
    assert proc_ref.prompt_externs is None
    assert proc_ref.command_boundaries == {
        "run_checks": {
            "kind": "external_tool",
            "stable_command": ["python", "scripts/run_checks.py"],
        }
    }

    review_loop = cases["stdlib_review_revise_loop"]
    assert isinstance(review_loop.command_boundaries, dict)
    assert "validate_review_findings_v1" in review_loop.command_boundaries

    full_fixture = cases["wcc_m4_implementation_phase_full_fixture"]
    assert isinstance(full_fixture.command_boundaries, dict)
    assert "run_checks" in full_fixture.command_boundaries
    assert "validate_review_findings_v1" in full_fixture.command_boundaries

    module_graph = cases["module_graph_imported_bundle_mix"]
    assert module_graph.command_boundaries == Path("tests/fixtures/workflow_lisp/cli/commands.json")
    assert module_graph.imported_workflow_bundles_path == Path(
        "tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json"
    )


def test_value_only_minimal_module_dual_compiles_identically_for_legacy_and_wcc_m1(tmp_path: Path) -> None:
    case = {case.case_id: case for case in load_characterization_cases()}["value_only_minimal_module"]
    golden = json.loads((Path.cwd() / case.golden_structural).read_text(encoding="utf-8"))

    legacy_workspace = tmp_path / "legacy"
    wcc_workspace = tmp_path / "wcc"
    legacy_actual = build_structural_snapshot(case, legacy_workspace, lowering_route="legacy")
    wcc_actual = build_structural_snapshot(case, wcc_workspace, lowering_route="wcc_m1")
    legacy_metadata = build_structural_snapshot_metadata(case, legacy_workspace, lowering_route="legacy")
    wcc_metadata = build_structural_snapshot_metadata(case, wcc_workspace, lowering_route="wcc_m1")

    assert legacy_metadata["lowering_route"] == "legacy"
    assert wcc_metadata["lowering_route"] == "wcc_m1"
    assert compare_structural_snapshots(legacy_actual, golden, case.declared_rename_map) == "identical"
    assert compare_structural_snapshots(wcc_actual, golden, case.declared_rename_map) == "identical"


@pytest.mark.parametrize(
    "case_id",
    ("wcc_m2_straight_line_effects", "proc_ref_bind_proc_forwarding"),
)
def test_wcc_m2_cases_dual_compile_identically_for_legacy_and_wcc_m2(tmp_path: Path, case_id: str) -> None:
    case = {case.case_id: case for case in load_characterization_cases()}[case_id]
    golden = json.loads((Path.cwd() / case.golden_structural).read_text(encoding="utf-8"))

    legacy_workspace = tmp_path / f"{case_id}.legacy"
    wcc_workspace = tmp_path / f"{case_id}.wcc_m2"
    legacy_actual = build_structural_snapshot(case, legacy_workspace, lowering_route="legacy")
    wcc_actual = build_structural_snapshot(case, wcc_workspace, lowering_route="wcc_m2")
    legacy_metadata = build_structural_snapshot_metadata(case, legacy_workspace, lowering_route="legacy")
    wcc_metadata = build_structural_snapshot_metadata(case, wcc_workspace, lowering_route="wcc_m2")

    assert legacy_metadata["lowering_route"] == "legacy"
    assert wcc_metadata["lowering_route"] == "wcc_m2"
    assert compare_structural_snapshots(legacy_actual, wcc_actual, case.declared_rename_map) == "identical"
    assert compare_structural_snapshots(wcc_actual, golden, case.declared_rename_map) == "identical"


@pytest.mark.parametrize(
    "case_id",
    ("design_delta_union_match_projection",),
)
def test_wcc_m3_match_cases_dual_compile_identically_for_legacy_and_wcc_m3(
    tmp_path: Path,
    case_id: str,
) -> None:
    case = {case.case_id: case for case in load_characterization_cases()}[case_id]
    golden = json.loads((Path.cwd() / case.golden_structural).read_text(encoding="utf-8"))

    legacy_workspace = tmp_path / f"{case_id}.legacy"
    wcc_workspace = tmp_path / f"{case_id}.wcc_m3"
    legacy_actual = build_structural_snapshot(case, legacy_workspace, lowering_route="legacy")
    wcc_actual = build_structural_snapshot(case, wcc_workspace, lowering_route="wcc_m3")
    legacy_metadata = build_structural_snapshot_metadata(case, legacy_workspace, lowering_route="legacy")
    wcc_metadata = build_structural_snapshot_metadata(case, wcc_workspace, lowering_route="wcc_m3")

    assert legacy_metadata["lowering_route"] == "legacy"
    assert wcc_metadata["lowering_route"] == "wcc_m3"
    assert compare_structural_snapshots(legacy_actual, wcc_actual, case.declared_rename_map) == "identical"
    assert compare_structural_snapshots(wcc_actual, golden, case.declared_rename_map) == "identical"


def test_imported_top_level_match_attempt_dual_compiles_for_legacy_and_wcc_m4(
    tmp_path: Path,
) -> None:
    case = {case.case_id: case for case in load_characterization_cases()}["top_level_match_attempt"]

    legacy_workspace = tmp_path / "top_level_match_attempt.legacy"
    wcc_workspace = tmp_path / "top_level_match_attempt.wcc_m4"
    legacy_actual = build_structural_snapshot(case, legacy_workspace, lowering_route="legacy")
    wcc_actual = build_structural_snapshot(case, wcc_workspace, lowering_route="wcc_m4")
    legacy_metadata = build_structural_snapshot_metadata(case, legacy_workspace, lowering_route="legacy")
    wcc_metadata = build_structural_snapshot_metadata(case, wcc_workspace, lowering_route="wcc_m4")

    assert legacy_metadata["lowering_route"] == "legacy"
    assert wcc_metadata["lowering_route"] == "wcc_m4"
    assert _without_allocation_identity(legacy_actual) == _without_allocation_identity(wcc_actual)


def _without_allocation_identity(value):
    if isinstance(value, list):
        return [_without_allocation_identity(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _without_allocation_identity(item)
            for key, item in value.items()
            if key not in {"allocation_id", "stable_identity"}
        }
    return value


def test_wcc_m3_nested_match_characterization_case_matches_golden(tmp_path: Path) -> None:
    case = {case.case_id: case for case in load_characterization_cases()}["wcc_m3_nested_non_tail_match"]
    actual = build_structural_snapshot(case, tmp_path, lowering_route="wcc_m3")
    metadata = build_structural_snapshot_metadata(case, tmp_path, lowering_route="wcc_m3")
    golden = json.loads((Path.cwd() / case.golden_structural).read_text(encoding="utf-8"))

    assert metadata["lowering_route"] == "wcc_m3"
    assert compare_structural_snapshots(actual, golden, case.declared_rename_map) == "identical"


def test_wcc_m3_design_delta_union_projection_keeps_record_projection_output_contract(tmp_path: Path) -> None:
    case = {case.case_id: case for case in load_characterization_cases()}["design_delta_union_match_projection"]
    actual = build_structural_snapshot(case, tmp_path, lowering_route="wcc_m3")
    authored_mapping = actual["lowered_workflows"][0]["authored_mapping"]

    assert set(authored_mapping["outputs"]) == {"return__report"}
    assert "return__variant" not in authored_mapping["outputs"]
    assert set(authored_mapping["steps"][1]["match"]["cases"]) == {"COMPLETED", "BLOCKED"}


@pytest.mark.parametrize("case_id", ("top_level_loop_recur", "stdlib_review_revise_loop"))
def test_wcc_m4_loop_cases_dual_compile_for_legacy_and_wcc_m4(tmp_path: Path, case_id: str) -> None:
    case = {case.case_id: case for case in load_characterization_cases()}[case_id]

    legacy_actual = build_structural_snapshot(case, tmp_path / f"{case_id}.legacy", lowering_route="legacy")
    wcc_actual = build_structural_snapshot(case, tmp_path / f"{case_id}.wcc_m4", lowering_route="wcc_m4")

    assert legacy_actual["diagnostics"] == []
    assert wcc_actual["diagnostics"] == []
    assert legacy_actual["workflow_names"] == wcc_actual["workflow_names"]


@pytest.mark.parametrize("case_id", ("wcc_m4_loop_under_case", "wcc_m4_implementation_phase_full_fixture"))
def test_wcc_m4_nested_fixture_cases_compile_under_wcc_m4(tmp_path: Path, case_id: str) -> None:
    case = {case.case_id: case for case in load_characterization_cases()}[case_id]
    actual = build_structural_snapshot(case, tmp_path / case_id, lowering_route="wcc_m4")
    metadata = build_structural_snapshot_metadata(case, tmp_path / f"{case_id}.metadata", lowering_route="wcc_m4")

    assert metadata["lowering_route"] == "wcc_m4"
    allowed_diagnostics = (
        {"variant_output_without_variant_specific_fields"}
        if case_id == "wcc_m4_loop_under_case"
        else set()
    )
    assert {diagnostic["code"] for diagnostic in actual["diagnostics"]} <= allowed_diagnostics
    assert actual["workflow_names"]


@pytest.mark.parametrize(
    "case",
    _characterization_cases_for_ids(WCC_IFEXPR_CASE_IDS),
    ids=WCC_IFEXPR_CASE_IDS,
)
def test_wcc_ifexpr_cases_compile_under_wcc_m4_and_default_route(tmp_path: Path, case) -> None:
    wcc_actual = build_structural_snapshot(case, tmp_path / f"{case.case_id}.wcc_m4", lowering_route="wcc_m4")
    default_actual = build_structural_snapshot(case, tmp_path / f"{case.case_id}.default", lowering_route=None)

    assert wcc_actual["diagnostics"] == []
    assert default_actual["diagnostics"] == []
    assert _has_authored_if_step(wcc_actual)
    assert _has_authored_if_step(default_actual)


def test_wcc_ifexpr_non_tail_binding_uses_control_join_without_unsupported_rewrite(
    tmp_path: Path,
) -> None:
    case = {case.case_id: case for case in load_characterization_cases()}["wcc_ifexpr_non_tail_binding"]
    actual = build_structural_snapshot(case, tmp_path / case.case_id, lowering_route="wcc_m4")

    messages = [diagnostic["message"] for diagnostic in actual["diagnostics"]]
    assert not any("unsupported WCC control rewrite node: WccIf" in message for message in messages)
    assert actual["diagnostics"] == []


def test_wcc_ifexpr_loop_body_converts_without_unsupported_loop_node(
    tmp_path: Path,
) -> None:
    case = {case.case_id: case for case in load_characterization_cases()}["wcc_ifexpr_loop_body"]
    actual = build_structural_snapshot(case, tmp_path / case.case_id, lowering_route="wcc_m4")

    messages = [diagnostic["message"] for diagnostic in actual["diagnostics"]]
    assert not any("unsupported WCC loop body during defunctionalization: WccIf" in message for message in messages)
    assert actual["diagnostics"] == []


def test_compare_structural_snapshots_distinguishes_identity_rename_and_divergence() -> None:
    baseline = {
        "schema_version": "workflow_lisp.characterization.v1",
        "case_id": "synthetic",
        "workflow_names": ["demo"],
        "lowered_workflows": [
            {
                "workflow_name": "demo",
                "step_labels": ["step-a"],
                "generated_input_names": ["input-a"],
            }
        ],
        "validated_bundles": [
            {
                "workflow_name": "demo",
                "node_ids": ["node-a"],
            }
        ],
        "diagnostics": [],
    }
    renamed = {
        **baseline,
        "lowered_workflows": [
            {
                "workflow_name": "demo",
                "step_labels": ["step-b"],
                "generated_input_names": ["input-b"],
            }
        ],
    }
    divergent = {
        **baseline,
        "validated_bundles": [
            {
                "workflow_name": "demo",
                "node_ids": ["node-z"],
            }
        ],
    }
    rename_map = {
        "step_labels": {"step-b": "step-a"},
        "generated_input_names": {"input-b": "input-a"},
    }

    assert compare_structural_snapshots(baseline, baseline, {}) == "identical"
    assert compare_structural_snapshots(renamed, baseline, rename_map) == "rename_only"
    assert compare_structural_snapshots(divergent, baseline, rename_map) == "divergent"


@pytest.mark.parametrize(
    "case",
    _characterization_cases_for_ids(BEHAVIOR_CASE_IDS),
    ids=BEHAVIOR_CASE_IDS,
)
def test_characterization_behavior_cases_match_golden(tmp_path: Path, case) -> None:
    lowering_route = None if case.case_id == "wcc_m4_implementation_phase_full_fixture" else "legacy"
    actual = build_behavior_observation(case, tmp_path, lowering_route=lowering_route)
    golden = json.loads((Path.cwd() / case.golden_behavior).read_text(encoding="utf-8"))

    assert actual == golden
