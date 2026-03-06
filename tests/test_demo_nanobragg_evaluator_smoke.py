from __future__ import annotations

from pathlib import Path

from orchestrator.demo.evaluators.nanobragg_accumulation import evaluate_workspace
from orchestrator.demo.provisioning import provision_trial
from tests.demo_helpers import init_git_seed_repo_from_example, snapshot_tree


ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "examples" / "demo_task_nanobragg_accumulation_port"
TASK_FILE = SEED / "docs" / "tasks" / "port_nanobragg_accumulation_to_pytorch.md"


def test_nanobragg_evaluator_smoke_is_read_only(tmp_path: Path):
    seed_repo, _commit = init_git_seed_repo_from_example(tmp_path=tmp_path, source_dir=SEED)
    experiment_root = tmp_path / "experiment"

    metadata = provision_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=TASK_FILE,
    )

    direct_workspace = Path(metadata["workspaces"]["direct_run"])
    before = snapshot_tree(direct_workspace)
    result = evaluate_workspace(direct_workspace)
    after = snapshot_tree(direct_workspace)

    assert set(result) == {"verdict", "failure_categories", "summary", "soft_quality"}
    assert result["verdict"] == "FAIL"
    assert "hidden_acceptance_failed" in result["failure_categories"]
    assert before == after
