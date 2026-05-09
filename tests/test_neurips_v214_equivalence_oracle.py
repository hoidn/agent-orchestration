from pathlib import Path

import pytest

from tests.golden_state import run_neurips_equivalence_observation


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/neurips_minimal"


@pytest.mark.parametrize(
    "scenario_name",
    [
        "completed",
        "blocked",
        "ambiguous",
        "missing_output",
        "fresh_plan",
        "recovered_plan",
        "selected_item_runtime",
    ],
)
def test_neurips_plan_gate_and_queue_oracles(tmp_path: Path, scenario_name: str) -> None:
    legacy_observation = run_neurips_equivalence_observation(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / f"{scenario_name}-legacy",
        scenario_name=scenario_name,
        stack="legacy",
    )
    v214_observation = run_neurips_equivalence_observation(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / f"{scenario_name}-v214",
        scenario_name=scenario_name,
        stack="v214",
    )

    assert legacy_observation["workflow_outputs"] == v214_observation["workflow_outputs"]
    assert legacy_observation["domain_state_summaries"] == v214_observation["domain_state_summaries"]
    assert legacy_observation["failure_classes"] == v214_observation["failure_classes"]
    assert legacy_observation == v214_observation
