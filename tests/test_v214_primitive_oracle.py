import json
import shutil
from pathlib import Path

import pytest

from tests.golden_state import load_expected_observation, run_fixture_workflow


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/v214_primitives"


@pytest.mark.parametrize(
    ("scenario_name", "expected_name"),
    [
        ("completed", "completed.json"),
        ("blocked", "blocked.json"),
        ("both_reports", "both_reports.json"),
        ("neither_report", "neither_report.json"),
    ],
)
def test_implementation_outcome_oracles(tmp_path: Path, scenario_name: str, expected_name: str) -> None:
    observation = run_fixture_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / scenario_name,
        workflow_relpath="implementation_oracle/workflow.yaml",
        scenario_name=scenario_name,
    )

    assert observation == load_expected_observation(
        FIXTURE_ROOT / "implementation_oracle" / "expected" / expected_name
    )


@pytest.mark.parametrize(
    ("scenario_name", "expected_name"),
    [
        ("review_approve", "review_approve.json"),
        ("review_revise", "review_revise.json"),
    ],
)
def test_review_decision_oracles(tmp_path: Path, scenario_name: str, expected_name: str) -> None:
    observation = run_fixture_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / scenario_name,
        workflow_relpath="review_oracle/workflow.yaml",
        scenario_name=scenario_name,
    )

    assert observation == load_expected_observation(FIXTURE_ROOT / "review_oracle" / "expected" / expected_name)


def test_materialization_contract_oracles(tmp_path: Path) -> None:
    observation = run_fixture_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / "materialization",
        workflow_relpath="materialization_oracle/workflow.yaml",
        scenario_name="materialization_ok",
    )

    assert observation == load_expected_observation(
        FIXTURE_ROOT / "materialization_oracle" / "expected" / "materialization_ok.json"
    )


def test_invalid_bundle_no_commit_oracle(tmp_path: Path) -> None:
    observation = run_fixture_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / "invalid-bundle",
        workflow_relpath="invalid_bundle_oracle/workflow.yaml",
        scenario_name="invalid_bundle",
    )

    assert observation == load_expected_observation(
        FIXTURE_ROOT / "invalid_bundle_oracle" / "expected" / "invalid_bundle.json"
    )


def test_missing_required_target_materialization_failure(tmp_path: Path) -> None:
    observation = run_fixture_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / "missing-target",
        workflow_relpath="materialization_missing_target_oracle/workflow.yaml",
        scenario_name="missing_target",
    )

    assert observation == load_expected_observation(
        FIXTURE_ROOT
        / "materialization_missing_target_oracle"
        / "expected"
        / "missing_target.json"
    )
