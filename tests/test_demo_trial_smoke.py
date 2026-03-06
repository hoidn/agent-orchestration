from __future__ import annotations

import json
from pathlib import Path

from orchestrator.demo.evaluators.linear_classifier import evaluate_workspace
from orchestrator.demo.provisioning import provision_trial
from tests.demo_helpers import init_git_seed_repo_from_example, snapshot_tree
from tests.test_demo_linear_classifier_evaluator import PASSING_LIB_RS, _enable_fake_toolchain


ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "examples" / "demo_task_linear_classifier_port"
TASK_FILE = SEED / "docs" / "tasks" / "port_linear_classifier_to_rust.md"


def test_provisioned_workspace_smoke_eval_is_stable(tmp_path: Path, monkeypatch):
    seed_repo, _commit = init_git_seed_repo_from_example(
        tmp_path=tmp_path,
        source_dir=SEED,
    )
    experiment_root = tmp_path / "experiment"

    metadata = provision_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=TASK_FILE,
    )

    direct_workspace = Path(metadata["workspaces"]["direct_run"])
    workflow_workspace = Path(metadata["workspaces"]["workflow_run"])
    (direct_workspace / "rust" / "src" / "lib.rs").write_text(PASSING_LIB_RS)

    _enable_fake_toolchain(monkeypatch)
    before = snapshot_tree(direct_workspace)
    result = evaluate_workspace(direct_workspace)
    after = snapshot_tree(direct_workspace)

    assert (direct_workspace / "state" / "task.md").is_file()
    assert (workflow_workspace / "state" / "task.md").is_file()
    assert result["verdict"] == "PASS"
    assert result["failure_categories"] == []
    assert set(result) == {"verdict", "failure_categories", "summary", "soft_quality"}
    assert result["summary"]["hidden_tests_passed"] is True
    assert before == after

    persisted = json.loads((experiment_root / "trial-metadata.json").read_text())
    assert persisted["start_commit"] == metadata["start_commit"]
