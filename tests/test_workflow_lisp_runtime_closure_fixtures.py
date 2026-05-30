from __future__ import annotations

import importlib
from pathlib import Path

import pytest


FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "workflow_lisp" / "runtime_closure_disabled"
)


def _fixtures_module():
    return importlib.import_module(
        "orchestrator.workflow_lisp.runtime_closure_design_fixtures"
    )


def _load_cases():
    module = _fixtures_module()
    return module.load_runtime_closure_fixture_cases(FIXTURE_ROOT / "case_matrix.yaml")


def _case(fixture_id: str):
    cases = {case.fixture_id: case for case in _load_cases()}
    return cases[fixture_id]


def test_runtime_closure_fixture_matrix_contains_required_inventory() -> None:
    cases = {case.fixture_id: case for case in _load_cases()}

    assert set(cases) >= {
        "baseline-proc-ref-state",
        "disabled-authored-closure-value",
        "disabled-let-proc-runtime-closure",
        "disabled-direct-closure-invoke",
        "design-invoke-without-accepted-family",
        "design-invalid-accepted-code-id",
        "design-signature-mismatch",
        "design-provider-produced-code",
        "design-command-produced-code",
        "design-artifact-transport",
        "design-workflow-output-transport",
        "design-provider-role-capture",
        "design-mutable-state-capture",
        "design-capture-closure-value",
        "design-effect-bound-violation",
        "design-capability-bound-violation",
        "design-write-root-ambiguity",
        "design-resume-bundle-mismatch",
        "design-resume-code-mismatch",
        "design-source-map-missing",
    }
    assert cases["baseline-proc-ref-state"].validation_surface == "baseline_stage3_selector"
    assert (
        cases["baseline-proc-ref-state"].expected_stage3_selector
        == "tests/test_workflow_lisp_loop_recur.py::test_typecheck_loop_recur_rejects_proc_ref_state"
    )


def test_fixture_validator_rejects_baseline_owned_rows() -> None:
    module = _fixtures_module()
    baseline_case = _case("baseline-proc-ref-state")

    with pytest.raises(ValueError, match="baseline_stage3_selector"):
        module.validate_runtime_closure_fixture_case(baseline_case)


@pytest.mark.parametrize(
    ("fixture_id", "expected_code"),
    [
        ("disabled-authored-closure-value", "runtime_closure_not_enabled"),
        ("disabled-let-proc-runtime-closure", "runtime_closure_not_enabled"),
        ("disabled-direct-closure-invoke", "runtime_closure_not_enabled"),
        ("design-invoke-without-accepted-family", "closure_family_unknown"),
        ("design-invalid-accepted-code-id", "closure_code_id_invalid"),
        ("design-signature-mismatch", "closure_signature_invalid"),
        ("design-provider-produced-code", "closure_dynamic_code_forbidden"),
        ("design-command-produced-code", "closure_dynamic_code_forbidden"),
        ("design-artifact-transport", "closure_runtime_transport_forbidden"),
        ("design-workflow-output-transport", "closure_runtime_transport_forbidden"),
        ("design-provider-role-capture", "closure_provider_capture_forbidden"),
        ("design-mutable-state-capture", "closure_capture_mode_forbidden"),
        ("design-capture-closure-value", "closure_capture_schema_invalid"),
        ("design-effect-bound-violation", "closure_effect_bound_invalid"),
        ("design-capability-bound-violation", "closure_capability_bound_invalid"),
        ("design-write-root-ambiguity", "closure_write_root_ambiguous"),
        ("design-resume-bundle-mismatch", "closure_resume_bundle_mismatch"),
        ("design-resume-code-mismatch", "closure_resume_code_mismatch"),
        ("design-source-map-missing", "closure_source_map_missing"),
    ],
)
def test_fixture_validator_emits_expected_code(
    fixture_id: str,
    expected_code: str,
) -> None:
    module = _fixtures_module()

    diagnostic = module.validate_runtime_closure_fixture_case(_case(fixture_id))[0]

    assert diagnostic.code == expected_code


def test_invocation_fixture_cases_preserve_creation_and_invocation_locations() -> None:
    case = _case("design-invoke-without-accepted-family")

    assert case.creation_location is not None
    assert case.invocation_location is not None
    assert case.accepted_family_location is not None


def test_resume_and_source_map_cases_include_resume_validation_location() -> None:
    for fixture_id in (
        "design-resume-bundle-mismatch",
        "design-resume-code-mismatch",
        "design-source-map-missing",
    ):
        assert _case(fixture_id).resume_validation_location is not None


def test_fixture_loader_rejects_malformed_case_rows(tmp_path: Path) -> None:
    module = _fixtures_module()
    bad_fixture = tmp_path / "bad.yaml"
    bad_fixture.write_text("cases:\n  - fixture_id: broken\n", encoding="utf-8")

    with pytest.raises(ValueError, match="broken"):
        module.load_runtime_closure_fixture_cases(bad_fixture)
