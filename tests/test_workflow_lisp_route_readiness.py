from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from orchestrator.workflow_lisp.migration_parity import (
    load_parity_targets,
    validate_parity_targets_against_route_readiness,
)
from orchestrator.workflow_lisp.route_readiness import (
    ROUTE_READINESS_SCHEMA_VERSION,
    RouteReadinessError,
    compile_registered_route_case,
    discover_required_orc_surfaces,
    load_route_readiness_registry,
    registry_entry_for_path,
    validate_migration_targets_against_route_readiness,
    validate_route_readiness_registry,
)
from orchestrator.workflow_lisp.wcc.route import DEFAULT_LOWERING_ROUTE


REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "docs" / "workflow_lisp_route_readiness_registry.json"
PARITY_TARGETS_PATH = (
    REPO_ROOT / "workflows" / "examples" / "inputs" / "workflow_lisp_migrations" / "parity_targets.json"
)
HISTORICAL_DESIGN_DELTA_REPORT_PATH = (
    REPO_ROOT
    / "artifacts"
    / "work"
    / "review-parity-check"
    / "design_delta_parent_drain.json"
)

INITIAL_REQUIRED_PATHS = {
    "workflows/examples/cycle_guard_demo.orc",
    "workflows/examples/design_plan_impl_review_stack_v2_call.orc",
    "workflows/examples/effectful_let_star_normalization.orc",
    "workflows/examples/effectful_match_arm_normalization.orc",
    "workflows/examples/kiss_backlog_item.orc",
    "workflows/examples/review_revise_design_docs.orc",
    "workflows/examples/review_revise_parametric_design_docs.orc",
    "workflows/examples/same_file_record_call_binding.orc",
    "workflows/examples/with_phase_composed_binding.orc",
    "workflows/library/lisp_frontend_design_delta/design_gap_architect.orc",
    "workflows/library/lisp_frontend_design_delta/bootstrap.orc",
    "workflows/library/lisp_frontend_design_delta/drain.orc",
    "workflows/library/lisp_frontend_design_delta/implementation_phase.orc",
    "workflows/library/lisp_frontend_design_delta/plan_phase.orc",
    "workflows/library/lisp_frontend_design_delta/selector.orc",
    "workflows/library/lisp_frontend_design_delta/types.orc",
    "workflows/library/lisp_frontend_design_delta/work_item.orc",
    "tests/fixtures/workflow_lisp/characterization/sources/design_delta_union_match_projection.orc",
    "tests/fixtures/workflow_lisp/characterization/sources/wcc_ifexpr_loop_body.orc",
    "tests/fixtures/workflow_lisp/characterization/sources/wcc_ifexpr_non_tail_binding.orc",
    "tests/fixtures/workflow_lisp/characterization/sources/wcc_ifexpr_tail.orc",
    "tests/fixtures/workflow_lisp/characterization/sources/wcc_m2_straight_line_effects.orc",
    "tests/fixtures/workflow_lisp/characterization/sources/wcc_m3_branch_local_ref_leak.orc",
    "tests/fixtures/workflow_lisp/characterization/sources/wcc_m3_nested_join_inside_arm.orc",
    "tests/fixtures/workflow_lisp/characterization/sources/wcc_m3_nested_non_tail_match.orc",
    "tests/fixtures/workflow_lisp/characterization/sources/wcc_m4_implementation_phase_full_fixture.orc",
    "tests/fixtures/workflow_lisp/characterization/sources/wcc_m4_loop_under_case.orc",
    "tests/fixtures/workflow_lisp/valid/design_delta_nested_branch_scope_collision.orc",
    "tests/fixtures/workflow_lisp/valid/design_delta_nested_implementation_phase.orc",
    "tests/fixtures/workflow_lisp/valid/design_delta_nested_imported_branch_effects.orc",
    "tests/fixtures/workflow_lisp/valid/design_delta_nested_same_file_call_local_record.orc",
    "tests/fixtures/workflow_lisp/valid/design_delta_parent_calls_implementation_phase.orc",
    "tests/fixtures/workflow_lisp/valid/design_delta_parent_calls_work_item.orc",
    "tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/implementation_phase.orc",
    "tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/plan_phase.orc",
    "tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/types.orc",
    "tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/work_item.orc",
}


def _base_entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "surface_id": "workflows.examples.effectful_match_arm_normalization",
        "path": "workflows/examples/effectful_match_arm_normalization.orc",
        "surface_kind": "workflow_example",
        "route_label": "wcc_default",
        "readiness_label": "leaf_runtime_candidate",
        "lowering_route": DEFAULT_LOWERING_ROUTE.value,
        "lowering_schema_version": 2,
        "copy_safety": "preferred_current_guidance",
        "evidence": [
            "tests/test_workflow_lisp_examples.py::test_effectful_match_arm_normalization_orc_compiles_with_shared_validation"
        ],
    }
    entry.update(overrides)
    return entry


def _write_registry(tmp_path: Path, surfaces: list[dict[str, object]]) -> Path:
    registry_path = tmp_path / "route_readiness.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": ROUTE_READINESS_SCHEMA_VERSION,
                "updated": "2026-06-10",
                "surfaces": surfaces,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return registry_path


def _codes(validation) -> set[str]:
    return {issue.code for issue in validation.issues}


def _evidence_codes(validation) -> set[str]:
    return {
        issue.code
        for issue in validation.issues
        if issue.field == "evidence"
    }


def test_checked_in_registry_loads_and_validates() -> None:
    registry = load_route_readiness_registry(REGISTRY_PATH)
    validation = validate_route_readiness_registry(registry, REPO_ROOT)

    assert registry.schema_version == ROUTE_READINESS_SCHEMA_VERSION
    assert validation.overall_pass is True
    assert validation.issues == ()


def test_discover_required_orc_surfaces_includes_initial_required_paths() -> None:
    required = discover_required_orc_surfaces(REPO_ROOT)

    assert INITIAL_REQUIRED_PATHS.issubset(required)


def test_missing_registry_coverage_emits_stable_code(tmp_path: Path) -> None:
    registry = load_route_readiness_registry(_write_registry(tmp_path, []))
    validation = validate_route_readiness_registry(registry, REPO_ROOT)

    assert "route_readiness_surface_missing" in _codes(validation)


def test_invalid_labels_and_unknown_route_emit_stable_codes(tmp_path: Path) -> None:
    cases = [
        ("surface_kind", "unknown_kind", "route_readiness_label_invalid"),
        ("route_label", "unknown_label", "route_readiness_label_invalid"),
        ("readiness_label", "unknown_readiness", "route_readiness_label_invalid"),
        ("lowering_route", "wcc_m99", "route_readiness_route_unknown"),
    ]
    for field_name, value, expected_code in cases:
        registry = load_route_readiness_registry(
            _write_registry(tmp_path, [_base_entry(**{field_name: value})])
        )
        validation = validate_route_readiness_registry(registry, REPO_ROOT)
        assert expected_code in _codes(validation)


def test_route_schema_default_and_stale_rules_emit_stable_codes(tmp_path: Path) -> None:
    cases = [
        (_base_entry(lowering_route="legacy", lowering_schema_version=2), "route_readiness_schema_mismatch"),
        (_base_entry(lowering_route="legacy", route_label="wcc_default"), "route_readiness_default_route_mismatch"),
        (
            _base_entry(
                route_label="stale_needs_update",
                lowering_route="wcc_m4",
                lowering_schema_version=2,
                copy_safety="not_current_guidance",
            ),
            "route_readiness_stale_surface_without_owner",
        ),
    ]
    for entry, expected_code in cases:
        registry = load_route_readiness_registry(_write_registry(tmp_path, [entry]))
        validation = validate_route_readiness_registry(registry, REPO_ROOT)
        assert expected_code in _codes(validation)


def test_self_referential_registry_evidence_is_rejected(tmp_path: Path) -> None:
    registry = load_route_readiness_registry(
        _write_registry(
            tmp_path,
            [
                _base_entry(
                    evidence=["python -m pytest tests/test_workflow_lisp_route_readiness.py -q"]
                )
            ],
        )
    )
    validation = validate_route_readiness_registry(registry, REPO_ROOT)

    assert "route_readiness_evidence_self_referential" in _codes(validation)


def test_registry_evidence_accepts_cli_command(tmp_path: Path) -> None:
    registry = load_route_readiness_registry(
        _write_registry(
            tmp_path,
            [
                _base_entry(
                    evidence=[
                        "python -m pytest tests/test_workflow_lisp_examples.py -q",
                        "git diff --check",
                    ]
                )
            ],
        )
    )

    validation = validate_route_readiness_registry(registry, REPO_ROOT)

    assert _evidence_codes(validation) == set()


def test_registry_evidence_accepts_diagnostic_name(tmp_path: Path) -> None:
    registry = load_route_readiness_registry(
        _write_registry(tmp_path, [_base_entry(evidence=["type_unknown"])])
    )

    validation = validate_route_readiness_registry(registry, REPO_ROOT)

    assert _evidence_codes(validation) == set()


def test_registry_evidence_accepts_existing_report_path(tmp_path: Path) -> None:
    registry = load_route_readiness_registry(
        _write_registry(
            tmp_path,
            [
                _base_entry(
                    evidence=[
                        "artifacts/work/review-parity-check/"
                        "design_delta_parent_drain.md"
                    ]
                )
            ],
        )
    )

    validation = validate_route_readiness_registry(registry, REPO_ROOT)

    assert _evidence_codes(validation) == set()


def test_registry_evidence_accepts_parameterized_pytest_node(tmp_path: Path) -> None:
    registry = load_route_readiness_registry(
        _write_registry(
            tmp_path,
            [
                _base_entry(
                    evidence=[
                        "tests/test_workflow_lisp_wcc_characterization.py::"
                        "test_m5_route_flip_corpus_compiles_under_default_wcc_route"
                        "[design_delta_union_match_projection]"
                    ]
                )
            ],
        )
    )

    validation = validate_route_readiness_registry(registry, REPO_ROOT)

    assert _evidence_codes(validation) == set()


def test_registry_evidence_accepts_parameterized_pytest_class_method(
    tmp_path: Path,
) -> None:
    evidence_module = tmp_path / "tests" / "test_evidence.py"
    evidence_module.parent.mkdir(parents=True)
    evidence_module.write_text(
        "class TestEvidence:\n"
        "    def test_case(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    registry = load_route_readiness_registry(
        _write_registry(
            tmp_path,
            [
                _base_entry(
                    evidence=[
                        "tests/test_evidence.py::TestEvidence::test_case[case-a]"
                    ]
                )
            ],
        )
    )

    validation = validate_route_readiness_registry(registry, tmp_path)

    assert _evidence_codes(validation) == set()


def test_registry_evidence_rejects_missing_pytest_file(tmp_path: Path) -> None:
    registry = load_route_readiness_registry(
        _write_registry(
            tmp_path,
            [
                _base_entry(
                    evidence=[
                        "tests/test_workflow_lisp_missing_evidence.py::test_missing"
                    ]
                )
            ],
        )
    )

    validation = validate_route_readiness_registry(registry, REPO_ROOT)

    assert "route_readiness_evidence_path_unknown" in _codes(validation)


def test_registry_evidence_rejects_missing_pytest_node(tmp_path: Path) -> None:
    registry = load_route_readiness_registry(
        _write_registry(
            tmp_path,
            [
                _base_entry(
                    evidence=[
                        "tests/test_workflow_lisp_examples.py::"
                        "test_route_readiness_node_does_not_exist"
                    ]
                )
            ],
        )
    )

    validation = validate_route_readiness_registry(registry, REPO_ROOT)

    assert "route_readiness_evidence_selector_unknown" in _evidence_codes(
        validation
    )


def test_registry_evidence_accepts_current_parity_target_selector(
    tmp_path: Path,
) -> None:
    registry = load_route_readiness_registry(
        _write_registry(
            tmp_path,
            [
                _base_entry(
                    evidence=[
                        "workflows/examples/inputs/workflow_lisp_migrations/"
                        "parity_targets.json::cycle_guard_demo"
                    ]
                )
            ],
        )
    )

    validation = validate_route_readiness_registry(registry, REPO_ROOT)

    assert _evidence_codes(validation) == set()


def test_registry_evidence_rejects_retired_parity_target_selector(
    tmp_path: Path,
) -> None:
    registry = load_route_readiness_registry(
        _write_registry(
            tmp_path,
            [
                _base_entry(
                    evidence=[
                        "workflows/examples/inputs/workflow_lisp_migrations/"
                        "parity_targets.json::design_delta_parent_drain"
                    ]
                )
            ],
        )
    )

    validation = validate_route_readiness_registry(registry, REPO_ROOT)

    assert "route_readiness_evidence_selector_unknown" in _codes(validation)


def test_registry_evidence_does_not_infer_targets_from_arbitrary_json(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "reports" / "unrelated.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text(
        json.dumps(
            {
                "targets": [
                    {"workflow_family": "not_a_parity_manifest"}
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = load_route_readiness_registry(
        _write_registry(
            tmp_path,
            [
                _base_entry(
                    evidence=[
                        "reports/unrelated.json::not_a_parity_manifest"
                    ]
                )
            ],
        )
    )

    validation = validate_route_readiness_registry(registry, tmp_path)

    assert "route_readiness_evidence_selector_invalid" in _evidence_codes(
        validation
    )


def test_checked_in_registry_uses_proving_evidence_not_registry_self_validation() -> None:
    registry = load_route_readiness_registry(REGISTRY_PATH)

    assert all(
        "tests/test_workflow_lisp_route_readiness.py" not in evidence
        for entry in registry.surfaces
        for evidence in entry.evidence
    )


def test_checked_in_registry_omits_retired_design_delta_evidence() -> None:
    registry = load_route_readiness_registry(REGISTRY_PATH)
    evidence = {
        item
        for entry in registry.surfaces
        for item in entry.evidence
    }

    assert all(
        "test_workflow_lisp_design_delta_drain_migration_feasibility.py"
        not in item
        for item in evidence
    )
    assert (
        "workflows/examples/inputs/workflow_lisp_migrations/"
        "parity_targets.json::design_delta_parent_drain"
        not in evidence
    )


def test_duplicate_surface_id_and_path_fail_deterministically(tmp_path: Path) -> None:
    duplicate_id = _base_entry(path="workflows/examples/effectful_let_star_normalization.orc")
    duplicate_path = _base_entry(surface_id="workflows.examples.effectful_match_arm_normalization.copy")
    registry = load_route_readiness_registry(
        _write_registry(tmp_path, [_base_entry(), duplicate_id, duplicate_path])
    )
    validation = validate_route_readiness_registry(registry, REPO_ROOT)

    assert [issue.code for issue in validation.issues].count("route_readiness_duplicate_surface_id") == 1
    assert [issue.code for issue in validation.issues].count("route_readiness_duplicate_path") == 1


def test_registry_entry_for_path_returns_normalized_entry() -> None:
    registry = load_route_readiness_registry(REGISTRY_PATH)

    entry = registry_entry_for_path(registry, "workflows/examples/effectful_match_arm_normalization.orc")

    assert entry is not None
    assert entry.path == "workflows/examples/effectful_match_arm_normalization.orc"
    assert registry_entry_for_path(registry, "./unknown.orc") is None


def test_malformed_registry_raises_loader_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")

    try:
        load_route_readiness_registry(path)
    except RouteReadinessError as exc:
        assert "invalid JSON" in str(exc)
    else:
        raise AssertionError("expected RouteReadinessError")


def test_migration_target_identity_mismatch_codes(tmp_path: Path) -> None:
    targets = load_parity_targets(PARITY_TARGETS_PATH)
    target = next(
        target
        for target in targets
        if target.workflow_family == "design_plan_impl_stack"
    )
    target = replace(
        target,
        readiness_label="promotion_eligible",
        lowering_route="wcc_m4",
        lowering_schema_version=2,
        required_family_evidence_roles=("parent_callable_compile",),
    )
    entry = _base_entry(
        surface_id="workflows.library.lisp_frontend_design_delta.drain",
        path=target.candidate,
        surface_kind="migration_target",
        route_label="migration_candidate",
        readiness_label="leaf_compile_candidate",
        lowering_route="legacy",
        lowering_schema_version=1,
    )
    registry = load_route_readiness_registry(_write_registry(tmp_path, [entry]))

    issues = validate_migration_targets_against_route_readiness([target], registry, REPO_ROOT)

    assert {issue["code"] for issue in issues} == {"route_readiness_migration_target_mismatch"}


def test_current_parity_targets_and_checked_in_registry_agree() -> None:
    targets = load_parity_targets(PARITY_TARGETS_PATH)
    registry = load_route_readiness_registry(REGISTRY_PATH)

    issues = validate_migration_targets_against_route_readiness(targets, registry, REPO_ROOT)

    assert issues == []
    assert validate_parity_targets_against_route_readiness(targets, registry, REPO_ROOT) == []


def test_design_delta_parent_drain_historical_promotion_matches_registry() -> None:
    targets = load_parity_targets(PARITY_TARGETS_PATH)
    assert "design_delta_parent_drain" not in {
        target.workflow_family for target in targets
    }
    report = json.loads(
        HISTORICAL_DESIGN_DELTA_REPORT_PATH.read_text(encoding="utf-8")
    )
    registry = load_route_readiness_registry(REGISTRY_PATH)
    entry = registry_entry_for_path(registry, report["candidate"])

    assert entry is not None
    assert report["non_regressive"] is True
    assert report["promotion_eligibility"] == {
        "eligible_for_primary_surface": True
    }
    assert report["route_identity"]["readiness_label"] == "promotion_eligible"
    assert report["route_identity"]["lowering_route"] == "wcc_m4"
    assert entry.readiness_label == "promotion_eligible"
    assert entry.route_label == "wcc_default"
    assert entry.copy_safety == "preferred_current_guidance"
    assert entry.parity_constrained is True


def test_cli_route_readiness_check_valid_registry() -> None:
    registry = load_route_readiness_registry(REGISTRY_PATH)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator",
            "workflow-lisp-route-readiness",
            "--registry",
            str(REGISTRY_PATH),
            "--check",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    summary = json.loads(result.stdout)
    assert summary["overall_pass"] is True
    assert summary["issues"] == []
    assert summary["missing_required_surfaces"] == 0
    assert summary["surfaces_checked"] == len(registry.surfaces)
    assert summary["surfaces_checked"] > 0


def test_cli_route_readiness_check_invalid_and_malformed_registries(tmp_path: Path) -> None:
    invalid_registry = _write_registry(tmp_path, [])
    invalid = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator",
            "workflow-lisp-route-readiness",
            "--registry",
            str(invalid_registry),
            "--check",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert invalid.returncode == 1
    assert json.loads(invalid.stdout)["overall_pass"] is False

    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{", encoding="utf-8")
    malformed = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator",
            "workflow-lisp-route-readiness",
            "--registry",
            str(malformed_path),
            "--check",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert malformed.returncode == 2


def test_compile_registered_route_case_injects_route_and_checks_schema(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    class Result:
        lowering_schema_version = 2

    def fake_compile(source_path: Path, **kwargs):
        calls.append({"source_path": source_path, **kwargs})
        return Result()

    result, entry = compile_registered_route_case(
        "workflows.examples.effectful_match_arm_normalization",
        source_path=REPO_ROOT / "workflows/examples/effectful_match_arm_normalization.orc",
        repo_root=REPO_ROOT,
        compile_func=fake_compile,
        registry_path=REGISTRY_PATH,
        workspace_root=tmp_path,
    )

    assert isinstance(result, Result)
    assert entry.lowering_route == DEFAULT_LOWERING_ROUTE.value
    assert calls[0]["lowering_route"] == DEFAULT_LOWERING_ROUTE.value


def test_compile_registered_route_case_default_route_does_not_override(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    class EntryResult:
        lowering_schema_version = 2

    class Result:
        entry_result = EntryResult()

    def fake_compile(source_path: Path, **kwargs):
        calls.append({"source_path": source_path, **kwargs})
        return Result()

    compile_registered_route_case(
        "workflows.examples.effectful_match_arm_normalization",
        source_path=REPO_ROOT / "workflows/examples/effectful_match_arm_normalization.orc",
        repo_root=REPO_ROOT,
        default_route_check=True,
        compile_func=fake_compile,
        registry_path=REGISTRY_PATH,
        workspace_root=tmp_path,
    )

    assert "lowering_route" not in calls[0]


def test_docs_mention_route_readiness_registry_path() -> None:
    registry_relpath = "docs/workflow_lisp_route_readiness_registry.json"

    assert registry_relpath in (REPO_ROOT / "workflows" / "README.md").read_text(encoding="utf-8")
    assert registry_relpath in (REPO_ROOT / "docs" / "lisp_workflow_drafting_guide.md").read_text(
        encoding="utf-8"
    )
