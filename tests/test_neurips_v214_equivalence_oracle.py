from pathlib import Path

import pytest

from tests.golden_state import load_expected_observation, run_fixture_workflow, run_neurips_workspace_workflow


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/neurips_minimal"


@pytest.mark.parametrize(
    ("scenario_name", "expected_name"),
    [
        ("completed", "completed.json"),
        ("blocked", "blocked.json"),
        ("ambiguous", "ambiguous.json"),
        ("missing_output", "missing_output.json"),
        ("fresh_plan", "fresh_plan.json"),
        ("recovered_plan", "recovered_plan.json"),
        ("selected_item_runtime", "selected_item_runtime.json"),
    ],
)
def test_neurips_plan_gate_and_queue_oracles(
    tmp_path: Path, scenario_name: str, expected_name: str
) -> None:
    observation = run_neurips_workspace_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / scenario_name,
        workflow_relpath="workflows/examples/neurips_steered_backlog_drain.yaml",
        scenario_name=scenario_name,
    )

    assert observation == load_expected_observation(FIXTURE_ROOT / "expected" / expected_name)
