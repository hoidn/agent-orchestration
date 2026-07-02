import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

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


def _run_checks(workspace: Path, base_sha: str, *, checks: str = "workflows/examples/inputs/pilot_checks.json", iteration: int = 0) -> dict:
    _run_script(
        workspace,
        str(ROOT / CHECKS),
        "--check-commands-path", checks,
        "--base-sha", base_sha,
        "--iteration-dir", f"{STATE_ROOT}/iterations/{iteration}",
        "--output", f"{STATE_ROOT}/iterations/{iteration}/checks-result.json",
    )
    return json.loads((workspace / STATE_ROOT / "iterations" / str(iteration) / "checks-result.json").read_text(encoding="utf-8"))


def test_checks_green_with_commits_packages_diff(tmp_path):
    workspace = _init_workspace(tmp_path)
    base = _git(workspace, "rev-parse", "HEAD")
    (workspace / "hello.txt").write_text("hi\n", encoding="utf-8")
    _git(workspace, "add", "hello.txt")
    _git(workspace, "commit", "-qm", "add hello")
    result = _run_checks(workspace, base)
    assert result["verify_status"] == "GREEN"
    assert result["commits_landed"] == "true"
    package = (workspace / result["review_package_path"]).read_text(encoding="utf-8")
    assert "add hello" in package
    assert "hello.txt" in package


def test_checks_red_on_failing_command_still_exits_zero(tmp_path):
    workspace = _init_workspace(tmp_path)
    (workspace / "workflows/examples/inputs/red_checks.json").write_text(
        json.dumps(["python -c \"raise SystemExit(1)\""]) + "\n", encoding="utf-8"
    )
    base = _git(workspace, "rev-parse", "HEAD")
    result = _run_checks(workspace, base, checks="workflows/examples/inputs/red_checks.json")
    assert result["verify_status"] == "RED"
    assert result["commits_landed"] == "false"
    assert "exit 1" in (workspace / result["checks_log_path"]).read_text(encoding="utf-8")


def test_checks_fails_fast_on_invalid_checks_file(tmp_path):
    workspace = _init_workspace(tmp_path)
    (workspace / "workflows/examples/inputs/bad_checks.json").write_text("{}\n", encoding="utf-8")
    base = _git(workspace, "rev-parse", "HEAD")
    proc = _run_script(
        workspace,
        str(ROOT / CHECKS),
        "--check-commands-path", "workflows/examples/inputs/bad_checks.json",
        "--base-sha", base,
        "--iteration-dir", f"{STATE_ROOT}/iterations/0",
        "--output", f"{STATE_ROOT}/iterations/0/checks-result.json",
        check=False,
    )
    assert proc.returncode != 0


def _record(
    workspace: Path,
    *,
    iteration: int = 0,
    verify: str = "GREEN",
    commits: str = "false",
    verdict: str = "CONTINUE",
    review: str | None = None,
    done_review: str | None = None,
    blocked_note: bool = False,
    stall_limit: str = "3",
    seed_statuses: list[str] | None = None,
    check: bool = True,
) -> tuple[str, str] | subprocess.CompletedProcess[str]:
    iteration_dir = workspace / STATE_ROOT / "iterations" / str(iteration)
    iteration_dir.mkdir(parents=True, exist_ok=True)
    (iteration_dir / "checks-result.json").write_text(
        json.dumps(
            {
                "verify_status": verify,
                "commits_landed": commits,
                "head_sha": "h" * 40,
                "checks_log_path": f"{STATE_ROOT}/iterations/{iteration}/checks-log.txt",
                "review_package_path": f"{STATE_ROOT}/iterations/{iteration}/review-package.md",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (iteration_dir / "worker-verdict.txt").write_text(verdict + "\n", encoding="utf-8")
    (iteration_dir / "worker-note.txt").write_text("did a thing\n", encoding="utf-8")
    if review is not None:
        (iteration_dir / "review-decision.txt").write_text(review + "\n", encoding="utf-8")
    if done_review is not None:
        (iteration_dir / "done-review-decision.txt").write_text(done_review + "\n", encoding="utf-8")
    blocked_dir = workspace / WORK_ROOT / "blocked"
    blocked_dir.mkdir(parents=True, exist_ok=True)
    if blocked_note:
        (blocked_dir / "BLOCKED-env.md").write_text("need credentials\n", encoding="utf-8")
    (workspace / WORK_ROOT / "ledger.md").parent.mkdir(parents=True, exist_ok=True)
    statuses = workspace / STATE_ROOT / "statuses.txt"
    if seed_statuses:
        statuses.write_text("".join(token + "\n" for token in seed_statuses), encoding="utf-8")
    proc = _run_script(
        workspace,
        str(ROOT / RECORD),
        "--iteration", str(iteration),
        "--base-sha", "b" * 40,
        "--checks-result-path", f"{STATE_ROOT}/iterations/{iteration}/checks-result.json",
        "--review-decision-path", f"{STATE_ROOT}/iterations/{iteration}/review-decision.txt",
        "--done-review-decision-path", f"{STATE_ROOT}/iterations/{iteration}/done-review-decision.txt",
        "--worker-verdict-path", f"{STATE_ROOT}/iterations/{iteration}/worker-verdict.txt",
        "--worker-note-path", f"{STATE_ROOT}/iterations/{iteration}/worker-note.txt",
        "--blocked-notes-dir", f"{WORK_ROOT}/blocked",
        "--ledger-path", f"{WORK_ROOT}/ledger.md",
        "--statuses-path", f"{STATE_ROOT}/statuses.txt",
        "--stall-limit", stall_limit,
        "--summary-path", f"{WORK_ROOT}/drain-summary.json",
        "--drain-status-path", f"{STATE_ROOT}/iterations/{iteration}/drain-status.txt",
        check=check,
    )
    if not check:
        return proc
    tokens = statuses.read_text(encoding="utf-8").split()
    drain = (workspace / STATE_ROOT / "iterations" / str(iteration) / "drain-status.txt").read_text(encoding="utf-8").strip()
    return tokens[-1], drain


def test_record_accepted_iteration_continues(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, commits="true", review="APPROVE")
    assert (status, drain) == ("ACCEPTED", "CONTINUE")
    ledger = (workspace / WORK_ROOT / "ledger.md").read_text(encoding="utf-8")
    assert "ACCEPTED" in ledger and "did a thing" in ledger


def test_record_checks_red_takes_precedence_over_done(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, verify="RED", commits="true", verdict="DONE", done_review="APPROVE")
    assert (status, drain) == ("CHECKS_RED", "CONTINUE")


def test_record_review_findings_block_acceptance(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, commits="true", review="FINDINGS")
    assert (status, drain) == ("FINDINGS", "CONTINUE")


def test_record_done_requires_done_review_approval(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, commits="true", verdict="DONE", review="APPROVE", done_review="APPROVE")
    assert (status, drain) == ("DONE", "DONE")
    status, drain = _record(workspace, iteration=1, verdict="DONE", done_review="REJECT")
    assert (status, drain) == ("FINDINGS", "CONTINUE")


def test_record_done_claim_without_done_review_is_findings(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, verdict="DONE")
    assert (status, drain) == ("FINDINGS", "CONTINUE")


def test_record_done_with_skipped_review_and_no_commits(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, verdict="DONE", done_review="APPROVE")
    assert (status, drain) == ("DONE", "DONE")


def test_record_blocked_requires_a_note(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, verdict="BLOCKED_ON_USER", blocked_note=True)
    assert (status, drain) == ("BLOCKED_ON_USER", "BLOCKED_ON_USER")
    workspace2 = _init_workspace(tmp_path / "second")
    status, drain = _record(workspace2, verdict="BLOCKED_ON_USER")
    assert (status, drain) == ("NO_CHANGE", "CONTINUE")


def test_record_stall_after_consecutive_non_accepted(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, seed_statuses=["NO_CHANGE", "FINDINGS"], verify="RED")
    assert (status, drain) == ("CHECKS_RED", "STALLED")
    summary = json.loads((workspace / WORK_ROOT / "drain-summary.json").read_text(encoding="utf-8"))
    assert summary["drain_status"] == "STALLED"
    assert summary["statuses"] == ["NO_CHANGE", "FINDINGS", "CHECKS_RED"]


def test_record_accepted_interrupts_stall_window(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, seed_statuses=["NO_CHANGE", "ACCEPTED"], verify="RED")
    assert (status, drain) == ("CHECKS_RED", "CONTINUE")


def test_record_rejects_non_positive_stall_limit(tmp_path):
    workspace = _init_workspace(tmp_path)
    proc = _record(workspace, stall_limit="0", check=False)
    assert proc.returncode != 0


def test_record_is_idempotent_across_repeated_invocations(tmp_path):
    workspace = _init_workspace(tmp_path)
    status1, drain1 = _record(workspace, commits="true", review="APPROVE")
    status2, drain2 = _record(workspace, commits="true", review="APPROVE")
    assert (status1, drain1) == ("ACCEPTED", "CONTINUE")
    assert (status2, drain2) == ("ACCEPTED", "CONTINUE")
    ledger_lines = [
        line
        for line in (workspace / WORK_ROOT / "ledger.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("iter 0 | ")
    ]
    assert len(ledger_lines) == 1
    tokens = (workspace / STATE_ROOT / "statuses.txt").read_text(encoding="utf-8").split()
    assert tokens == ["ACCEPTED"]


def test_verified_iteration_drain_workflow_loads(tmp_path):
    loader = WorkflowLoader(ROOT)
    loader.load_bundle(ROOT / WORKFLOW)
    assert loader.error_count() == 0


def test_review_prompts_are_pinned_to_expected_steps():
    workflow = yaml.safe_load((ROOT / WORKFLOW).read_text(encoding="utf-8"))
    body_steps = workflow["steps"][0]["repeat_until"]["steps"]
    steps_by_name = {step["name"]: step for step in body_steps}
    assert (
        steps_by_name["ReviewIteration"]["input_file"]
        == "workflows/library/prompts/verified_iteration_drain/review_iteration.md"
    )
    assert (
        steps_by_name["ReviewDoneClaim"]["input_file"]
        == "workflows/library/prompts/verified_iteration_drain/review_done.md"
    )


def _copy_drain_runtime_files(workspace: Path) -> Path:
    for relpath in [
        WORKFLOW,
        PREPARE,
        CHECKS,
        RECORD,
        "workflows/library/scripts/write_lisp_frontend_relpath_value.py",
        "workflows/library/prompts/verified_iteration_drain/work.md",
        "workflows/library/prompts/verified_iteration_drain/review_iteration.md",
        "workflows/library/prompts/verified_iteration_drain/review_done.md",
    ]:
        dest = workspace / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text((ROOT / relpath).read_text(encoding="utf-8"), encoding="utf-8")
    _git(workspace, "add", "workflows")
    _git(workspace, "commit", "-qm", "add drain runtime files")
    return workspace / WORKFLOW


def _drain_inputs() -> dict:
    return {
        "target_design_path": "docs/design/pilot_target.md",
        "check_commands_path": "workflows/examples/inputs/pilot_checks.json",
        "stall_limit": "2",
    }


def _run_drain_with_providers(workspace: Path, provider_sequence) -> dict:
    workflow_path = workspace / WORKFLOW
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    bound_inputs = bind_workflow_inputs(workflow_input_contracts(workflow), _drain_inputs(), workspace)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(
        workflow_path.relative_to(workspace).as_posix(),
        _bundle_context_dict(workflow),
        bound_inputs=bound_inputs,
    )
    executor = WorkflowExecutor(workflow, workspace, state_manager)
    call_index = {"value": 0}

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **kwargs):
        assert call_index["value"] < len(provider_sequence), f"unexpected provider call: {kwargs.get('step_name')}"
        expected_step, writer = provider_sequence[call_index["value"]]
        actual_step = kwargs.get("step_name")
        if actual_step is not None:
            assert expected_step in str(actual_step), f"expected {expected_step}, got {actual_step}"
        call_index["value"] += 1
        writer(workspace)
        return SimpleNamespace(
            exit_code=0, stdout=b"ok", stderr=b"", duration_ms=1, error=None,
            missing_placeholders=None, invalid_prompt_placeholder=False,
            raw_stdout=None, normalized_stdout=None, provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute()
    assert call_index["value"] == len(provider_sequence)
    return state


def _latest_iteration_dir(workspace: Path) -> Path:
    iterations = sorted((workspace / STATE_ROOT / "iterations").iterdir(), key=lambda p: int(p.name))
    return iterations[-1]


def _worker_commits_and_claims_done(workspace: Path) -> None:
    (workspace / "hello.txt").write_text("hi\n", encoding="utf-8")
    _git(workspace, "add", "hello.txt")
    _git(workspace, "commit", "-qm", "add hello per target design")
    iteration_dir = _latest_iteration_dir(workspace)
    (iteration_dir / "worker-verdict.txt").write_text("DONE\n", encoding="utf-8")
    (iteration_dir / "worker-note.txt").write_text("created hello.txt\n", encoding="utf-8")


def _worker_makes_no_progress(workspace: Path) -> None:
    iteration_dir = _latest_iteration_dir(workspace)
    (iteration_dir / "worker-verdict.txt").write_text("CONTINUE\n", encoding="utf-8")
    (iteration_dir / "worker-note.txt").write_text("could not find a next step\n", encoding="utf-8")


def _worker_blocks_on_user(workspace: Path) -> None:
    blocked = workspace / WORK_ROOT / "blocked/BLOCKED-credentials.md"
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.write_text("Need the API token only the user holds.\n", encoding="utf-8")
    iteration_dir = _latest_iteration_dir(workspace)
    (iteration_dir / "worker-verdict.txt").write_text("BLOCKED_ON_USER\n", encoding="utf-8")
    (iteration_dir / "worker-note.txt").write_text("all remaining work needs the token\n", encoding="utf-8")


def _reviewer_approves_iteration(workspace: Path) -> None:
    (_latest_iteration_dir(workspace) / "review-decision.txt").write_text("APPROVE\n", encoding="utf-8")


def _reviewer_approves_done(workspace: Path) -> None:
    (_latest_iteration_dir(workspace) / "done-review-decision.txt").write_text("APPROVE\n", encoding="utf-8")


def test_drain_completes_in_one_verified_iteration(tmp_path):
    workspace = _init_workspace(tmp_path)
    _copy_drain_runtime_files(workspace)
    _run_drain_with_providers(
        workspace,
        [
            ("Work", _worker_commits_and_claims_done),
            ("ReviewIteration", _reviewer_approves_iteration),
            ("ReviewDoneClaim", _reviewer_approves_done),
        ],
    )
    summary = json.loads((workspace / WORK_ROOT / "drain-summary.json").read_text(encoding="utf-8"))
    assert summary["drain_status"] == "DONE"
    assert summary["statuses"] == ["DONE"]
    ledger = (workspace / WORK_ROOT / "ledger.md").read_text(encoding="utf-8")
    assert "DONE" in ledger and "created hello.txt" in ledger


def test_drain_stalls_after_consecutive_no_change_iterations(tmp_path):
    workspace = _init_workspace(tmp_path)
    _copy_drain_runtime_files(workspace)
    _run_drain_with_providers(
        workspace,
        [
            ("Work", _worker_makes_no_progress),
            ("Work", _worker_makes_no_progress),
        ],
    )
    summary = json.loads((workspace / WORK_ROOT / "drain-summary.json").read_text(encoding="utf-8"))
    assert summary["drain_status"] == "STALLED"
    assert summary["statuses"] == ["NO_CHANGE", "NO_CHANGE"]


def test_drain_exits_blocked_on_user_with_notes(tmp_path):
    workspace = _init_workspace(tmp_path)
    _copy_drain_runtime_files(workspace)
    _run_drain_with_providers(workspace, [("Work", _worker_blocks_on_user)])
    summary = json.loads((workspace / WORK_ROOT / "drain-summary.json").read_text(encoding="utf-8"))
    assert summary["drain_status"] == "BLOCKED_ON_USER"
    assert summary["blocked_notes"] == ["BLOCKED-credentials.md"]
