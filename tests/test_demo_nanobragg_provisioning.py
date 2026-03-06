from __future__ import annotations

from pathlib import Path

from orchestrator.demo.provisioning import provision_trial
from tests.demo_helpers import init_git_seed_repo_from_example


ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "examples" / "demo_task_nanobragg_accumulation_port"
TASK_FILE = SEED / "docs" / "tasks" / "port_nanobragg_accumulation_to_pytorch.md"
WORKFLOW = ROOT / "workflows" / "examples" / "generic_task_plan_execute_review_loop.yaml"
WORKFLOW_PROMPTS = ROOT / "prompts" / "workflows"


def _tracked_visible_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def test_nanobragg_seed_provisions_clean_workspaces_with_staged_workflow_assets(tmp_path: Path):
    seed_repo, _commit = init_git_seed_repo_from_example(tmp_path=tmp_path, source_dir=SEED)
    experiment_root = tmp_path / "experiment"

    metadata = provision_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=TASK_FILE,
        workflow_path=WORKFLOW,
        workflow_prompts_dir=WORKFLOW_PROMPTS,
    )

    direct_workspace = Path(metadata["workspaces"]["direct_run"])
    workflow_workspace = Path(metadata["workspaces"]["workflow_run"])

    assert (direct_workspace / "state" / "task.md").is_file()
    assert (workflow_workspace / "state" / "task.md").is_file()
    assert (
        workflow_workspace / "workflows" / "examples" / WORKFLOW.name
    ).is_file()
    assert (
        workflow_workspace / "prompts" / "workflows" / "generic_task_loop" / "draft_plan.md"
    ).is_file()

    visible_files = _tracked_visible_files(direct_workspace)
    assert all("__pycache__" not in str(path) for path in visible_files)
    assert all(path.suffix != ".pyc" for path in visible_files)

    assert (direct_workspace / "src_c" / "nanoBragg.c").read_text().startswith("/*")
    assert (direct_workspace / "fixtures" / "visible" / "case_small.json").is_file()
