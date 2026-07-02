import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator.loader import WorkflowLoader
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_context, workflow_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from tests.test_lisp_frontend_autonomous_drain_runtime import _bundle_context_dict

ROOT = Path(__file__).resolve().parents[1]

PREPARE = "workflows/library/scripts/prepare_verified_iteration.py"
CHECKS = "workflows/library/scripts/run_verified_iteration_checks.py"
RECORD = "workflows/library/scripts/record_verified_iteration.py"
WORKFLOW = "workflows/examples/verified_iteration_drain.yaml"

STATE_ROOT = "state/VERIFIED-ITERATION-DRAIN"
WORK_ROOT = "artifacts/work/VERIFIED-ITERATION-DRAIN"


def _run_script(workspace: Path, *argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["python", *argv], cwd=workspace, text=True, capture_output=True, check=check)


def _git(workspace: Path, *argv: str) -> str:
    result = subprocess.run(["git", *argv], cwd=workspace, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def _init_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "docs/design").mkdir(parents=True)
    (workspace / "workflows/examples/inputs").mkdir(parents=True)
    (workspace / "docs/design/pilot_target.md").write_text(
        "# Pilot Target\n\nAcceptance: `hello.txt` exists at repo root.\n", encoding="utf-8"
    )
    (workspace / "workflows/examples/inputs/pilot_checks.json").write_text(
        json.dumps(["python -c \"print('ok')\""]) + "\n", encoding="utf-8"
    )
    _git(workspace, "init", "-q")
    _git(workspace, "config", "user.email", "test@test")
    _git(workspace, "config", "user.name", "test")
    _git(workspace, "add", "docs", "workflows")
    _git(workspace, "commit", "-qm", "seed")
    return workspace


def _prepare(workspace: Path, iteration: int = 0) -> dict:
    _run_script(
        workspace,
        str(ROOT / PREPARE),
        "--drain-state-root", STATE_ROOT,
        "--artifact-work-root", WORK_ROOT,
        "--target-design-path", "docs/design/pilot_target.md",
        "--check-commands-path", "workflows/examples/inputs/pilot_checks.json",
        "--iteration", str(iteration),
        "--output", f"{STATE_ROOT}/iterations/{iteration}/work-order.json",
    )
    return json.loads((workspace / STATE_ROOT / "iterations" / str(iteration) / "work-order.json").read_text(encoding="utf-8"))


def test_prepare_writes_work_order_and_scaffolding(tmp_path):
    workspace = _init_workspace(tmp_path)
    order = _prepare(workspace)
    assert order["base_sha"] == _git(workspace, "rev-parse", "HEAD")
    assert (workspace / order["ledger_path"]).is_file()
    assert (workspace / order["blocked_notes_dir"]).is_dir()
    assert order["previous_review_findings_path"] == ""
    assert order["worker_verdict_path"] == f"{STATE_ROOT}/iterations/0/worker-verdict.txt"
    assert order["review_decision_path"] == f"{STATE_ROOT}/iterations/0/review-decision.txt"


def test_prepare_names_previous_findings_when_present(tmp_path):
    workspace = _init_workspace(tmp_path)
    findings = workspace / STATE_ROOT / "iterations/0/review-findings.md"
    findings.parent.mkdir(parents=True)
    findings.write_text("finding\n", encoding="utf-8")
    order = _prepare(workspace, iteration=1)
    assert order["previous_review_findings_path"] == f"{STATE_ROOT}/iterations/0/review-findings.md"


def test_prepare_fails_fast_on_missing_target_design(tmp_path):
    workspace = _init_workspace(tmp_path)
    result = _run_script(
        workspace,
        str(ROOT / PREPARE),
        "--drain-state-root", STATE_ROOT,
        "--artifact-work-root", WORK_ROOT,
        "--target-design-path", "docs/design/absent.md",
        "--check-commands-path", "workflows/examples/inputs/pilot_checks.json",
        "--iteration", "0",
        "--output", f"{STATE_ROOT}/iterations/0/work-order.json",
        check=False,
    )
    assert result.returncode != 0
