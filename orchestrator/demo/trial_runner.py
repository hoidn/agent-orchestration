"""Run one direct-vs-workflow demo trial and archive comparable results."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2
from typing import Any

from orchestrator.demo.provisioning import provision_trial


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_direct_command(
    prompt: str,
    *,
    provider: str = "claude",
    model: str = "claude-sonnet-4-6",
    effort: str = "medium",
) -> list[str]:
    if provider == "claude":
        return [
            "claude",
            "-p",
            prompt,
            "--dangerously-skip-permissions",
            "--model",
            model,
            "--effort",
            effort,
        ]
    if provider == "codex":
        return [
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--model",
            model,
            "--config",
            f"model_reasoning_effort={effort}",
            prompt,
        ]
    raise ValueError(f"Unsupported direct provider: {provider}")


def render_workflow_for_provider(workflow_path: Path, *, provider: str) -> None:
    content = workflow_path.read_text(encoding="utf-8")
    if provider == "claude":
        return
    if provider == "codex":
        rendered = content.replace("providers:\n  claude:\n", "providers:\n  codex:\n", 1)
        rendered = rendered.replace("provider: claude", "provider: codex")
        rendered = rendered.replace(
            '      [\n        "claude",\n        "-p",\n        "${PROMPT}",\n        "--dangerously-skip-permissions",\n        "--model",\n        "${model}",\n        "--effort",\n        "${effort}",\n      ]',
            '      [\n        "codex",\n        "exec",\n        "--dangerously-bypass-approvals-and-sandbox",\n        "--skip-git-repo-check",\n        "--model",\n        "${model}",\n        "--config",\n        "model_reasoning_effort=${reasoning_effort}",\n        "${PROMPT}",\n      ]',
            1,
        )
        rendered = rendered.replace("      effort: \"${context.workflow_effort}\"", "      reasoning_effort: \"${context.workflow_effort}\"", 1)
        workflow_path.write_text(rendered, encoding="utf-8")
        return
    raise ValueError(f"Unsupported workflow provider: {provider}")


def build_workflow_command(
    *,
    workflow_path: Path,
    repo_root: Path,
    model: str = "claude-sonnet-4-6",
    effort: str = "medium",
) -> list[str]:
    return [
        "env",
        f"PYTHONPATH={repo_root}",
        sys.executable,
        "-m",
        "orchestrator",
        "run",
        str(Path(workflow_path)),
        "--context",
        f"workflow_model={model}",
        "--context",
        f"workflow_effort={effort}",
    ]


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    archive_dir: Path,
    arm: str,
    timeout_sec: int | None = None,
    stream_output: bool = True,
) -> dict[str, Any]:
    arm_dir = archive_dir / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = arm_dir / "stdout.log"
    stderr_log = arm_dir / "stderr.log"
    started = time.time()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    _write_json(
        arm_dir / "process.json",
        {
            "backend": "subprocess",
            "command": command,
            "cwd": str(cwd),
            "pid": process.pid,
            "started_at": _now_iso(),
        },
    )
    _write_json(
        arm_dir / "heartbeat.json",
        {
            "timestamp": _now_iso(),
            "alive": True,
            "elapsed_sec": 0.0,
            "stdout_bytes": 0,
            "stderr_bytes": 0,
        },
    )
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    stdout_thread = threading.Thread(
        target=_stream_pipe,
        kwargs={
            "pipe": process.stdout,
            "log_path": stdout_log,
            "arm": arm,
            "stream_name": "stdout",
            "buffer": stdout_chunks,
            "emit_console": stream_output,
        },
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_stream_pipe,
        kwargs={
            "pipe": process.stderr,
            "log_path": stderr_log,
            "arm": arm,
            "stream_name": "stderr",
            "buffer": stderr_chunks,
            "emit_console": stream_output,
        },
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    try:
        process.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
        timeout_line = f"{arm} timed out after {timeout_sec} seconds\n"
        stderr_chunks.append(timeout_line)
        with stderr_log.open("a", encoding="utf-8") as handle:
            handle.write(timeout_line)
            handle.flush()
        if stream_output:
            print(f"[{arm}][stderr] {timeout_line.rstrip()}", flush=True)

    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)
    stdout = "".join(stdout_chunks)
    stderr = "".join(stderr_chunks)
    _write_json(
        arm_dir / "heartbeat.json",
        {
            "timestamp": _now_iso(),
            "alive": False,
            "elapsed_sec": max(0.0, time.time() - started),
            "stdout_bytes": len(stdout.encode("utf-8")),
            "stderr_bytes": len(stderr.encode("utf-8")),
        },
    )
    return {
        "command": command,
        "cwd": str(cwd),
        "exit_code": process.returncode,
        "duration_ms": int((time.time() - started) * 1000),
        "timed_out": timed_out,
        "timeout_sec": timeout_sec,
        "stdout": stdout,
        "stderr": stderr,
    }


def _run_git_capture(workspace: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def archive_workspace_metadata(*, archive_dir: Path, label: str, workspace: Path, command: list[str]) -> dict[str, Any]:
    metadata = {
        "label": label,
        "workspace": str(workspace),
        "command": command,
        "git_status_short": _run_git_capture(workspace, "status", "--short"),
        "git_head": _run_git_capture(workspace, "rev-parse", "HEAD"),
    }
    (archive_dir / f"{label}-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def _write_command_record(archive_dir: Path, name: str, command: list[str]) -> None:
    (archive_dir / f"{name}.json").write_text(
        json.dumps({"command": command}, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _append_event(archive_dir: Path, event: str, **details: Any) -> None:
    event_path = archive_dir / "runner-events.jsonl"
    payload = {"event": event, "timestamp": _now_iso(), **details}
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _write_runner_state(archive_dir: Path, payload: dict[str, Any]) -> None:
    payload = {**payload, "updated_at": _now_iso()}
    _write_json(archive_dir / "runner-state.json", payload)


def _write_partial_result(archive_dir: Path, payload: dict[str, Any]) -> None:
    _write_json(archive_dir / "partial-trial-result.json", payload)


def _emit_stream_to_console(*, arm: str, stream_name: str, content: str) -> None:
    for line in content.splitlines():
        print(f"[{arm}][{stream_name}] {line}", flush=True)


def _stream_pipe(
    *,
    pipe,
    log_path: Path,
    arm: str,
    stream_name: str,
    buffer: list[str],
    emit_console: bool,
) -> None:
    with log_path.open("w", encoding="utf-8") as handle:
        for line in iter(pipe.readline, ""):
            buffer.append(line)
            handle.write(line)
            handle.flush()
            if emit_console:
                print(f"[{arm}][{stream_name}] {line.rstrip()}", flush=True)
    pipe.close()


def _write_freeze_manifest(*, archive_dir: Path, arm: str, workspace: Path) -> None:
    freeze_dir = archive_dir / arm / "freeze"
    freeze_dir.mkdir(parents=True, exist_ok=True)
    (freeze_dir / "workspace-status.txt").write_text(
        _run_git_capture(workspace, "status", "--short") + "\n",
        encoding="utf-8",
    )
    (freeze_dir / "workspace-head.txt").write_text(
        _run_git_capture(workspace, "rev-parse", "HEAD") + "\n",
        encoding="utf-8",
    )
    entries = sorted(
        str(path.relative_to(workspace))
        for path in workspace.rglob("*")
        if path.is_file()
    )
    (freeze_dir / "tree.txt").write_text("\n".join(entries) + ("\n" if entries else ""), encoding="utf-8")


def _select_evaluator(*, seed_repo: Path, task_file: Path) -> list[str] | None:
    if task_file.name == "port_nanobragg_entrypoint_to_pytorch.md":
        return [sys.executable, str(_repo_root() / "scripts" / "demo" / "evaluate_nanobragg_entrypoint.py")]
    if seed_repo.name == "demo_task_nanobragg_entrypoint_port":
        return [sys.executable, str(_repo_root() / "scripts" / "demo" / "evaluate_nanobragg_entrypoint.py")]
    if task_file.name == "port_nanobragg_accumulation_to_pytorch.md":
        return [sys.executable, str(_repo_root() / "scripts" / "demo" / "evaluate_nanobragg_accumulation.py")]
    if seed_repo.name == "demo_task_nanobragg_accumulation_port":
        return [sys.executable, str(_repo_root() / "scripts" / "demo" / "evaluate_nanobragg_accumulation.py")]
    if task_file.name == "port_linear_classifier_to_rust.md":
        return [sys.executable, str(_repo_root() / "scripts" / "demo" / "evaluate_linear_classifier.py")]
    if seed_repo.name == "demo_task_linear_classifier_port":
        return [sys.executable, str(_repo_root() / "scripts" / "demo" / "evaluate_linear_classifier.py")]
    return None


def _run_evaluator(base_command: list[str], workspace: Path) -> dict[str, Any]:
    result = subprocess.run(
        [*base_command, str(workspace)],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {
            "verdict": "FAIL",
            "failure_categories": ["invalid_evaluator_output"],
            "summary": {
                "hidden_tests_passed": False,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            "soft_quality": {"score": 0.0, "findings": ["evaluator did not return JSON"]},
        }
    payload["process_exit_code"] = result.returncode
    return payload


def run_trial(
    *,
    seed_repo: Path,
    experiment_root: Path,
    task_file: Path,
    workflow_path: Path,
    direct_prompt: str,
    commitish: str = "HEAD",
    direct_timeout_sec: int | None = None,
    workflow_timeout_sec: int | None = None,
    stream_output: bool = True,
    direct_provider: str = "claude",
    direct_model: str = "claude-sonnet-4-6",
    direct_effort: str = "medium",
    workflow_provider: str = "claude",
    workflow_model: str = "claude-sonnet-4-6",
    workflow_effort: str = "medium",
) -> dict[str, Any]:
    started_at = _now_iso()
    metadata = provision_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
        workflow_path=workflow_path,
        workflow_prompts_dir=_repo_root() / "prompts" / "workflows",
        commitish=commitish,
    )
    archive_dir = experiment_root / "archive"
    _append_event(
        archive_dir,
        "trial_started",
        seed_repo=str(seed_repo),
        task_file=str(task_file),
        workflow_path=str(workflow_path),
    )
    workspaces = metadata["workspaces"]
    direct_workspace = Path(workspaces["direct_run"])
    workflow_workspace = Path(workspaces["workflow_run"])
    staged_workflow_path = Path("workflows") / "examples" / Path(workflow_path).name
    rendered_workflow_path = workflow_workspace / staged_workflow_path
    if not rendered_workflow_path.exists():
        rendered_workflow_path.parent.mkdir(parents=True, exist_ok=True)
        copy2(workflow_path, rendered_workflow_path)
    render_workflow_for_provider(rendered_workflow_path, provider=workflow_provider)

    state: dict[str, Any] = {
        "started_at": started_at,
        "status": "running",
        "mode": "serial",
        "start_commit": metadata["start_commit"],
        "seed_repo": str(seed_repo),
        "task_file": str(task_file),
        "workflow_path": str(workflow_path),
        "current_phase": "provisioned",
        "direct": {
            "status": "pending",
            "workspace": str(direct_workspace),
            "exit_code": None,
            "timed_out": False,
        },
        "workflow": {
            "status": "pending",
            "workspace": str(workflow_workspace),
            "exit_code": None,
            "timed_out": False,
        },
        "evaluation": {
            "status": "pending",
            "direct_verdict": None,
            "workflow_verdict": None,
        },
    }
    _append_event(archive_dir, "provisioning_completed", start_commit=metadata["start_commit"])
    _write_runner_state(archive_dir, state)

    direct_command = build_direct_command(
        direct_prompt,
        provider=direct_provider,
        model=direct_model,
        effort=direct_effort,
    )
    workflow_command = build_workflow_command(
        workflow_path=staged_workflow_path,
        repo_root=_repo_root(),
        model=workflow_model,
        effort=workflow_effort,
    )
    _write_command_record(archive_dir, "direct-command", direct_command)
    _write_command_record(archive_dir, "workflow-command", workflow_command)
    _write_partial_result(
        archive_dir,
        {
            "start_commit": metadata["start_commit"],
            "direct": {"workspace": str(direct_workspace), "command": direct_command, "execution": None},
            "workflow": {"workspace": str(workflow_workspace), "command": workflow_command, "execution": None},
        },
    )

    state["current_phase"] = "direct_execution"
    state["direct"]["status"] = "running"
    _append_event(archive_dir, "arm_started", arm="direct", command=direct_command)
    _write_runner_state(archive_dir, state)
    direct_execution = _run_command(
        direct_command,
        cwd=direct_workspace,
        archive_dir=archive_dir,
        arm="direct",
        timeout_sec=direct_timeout_sec,
        stream_output=stream_output,
    )
    state["direct"]["status"] = (
        "timed_out" if direct_execution["timed_out"] else ("succeeded" if direct_execution["exit_code"] == 0 else "failed")
    )
    state["direct"]["exit_code"] = direct_execution["exit_code"]
    state["direct"]["timed_out"] = direct_execution["timed_out"]
    if direct_execution["timed_out"]:
        _append_event(archive_dir, "arm_timeout", arm="direct", timeout_sec=direct_timeout_sec)
    _append_event(archive_dir, "arm_completed", arm="direct", exit_code=direct_execution["exit_code"])
    _write_partial_result(
        archive_dir,
        {
            "start_commit": metadata["start_commit"],
            "direct": {"workspace": str(direct_workspace), "command": direct_command, "execution": direct_execution},
            "workflow": {"workspace": str(workflow_workspace), "command": workflow_command, "execution": None},
        },
    )
    _write_runner_state(archive_dir, state)

    state["current_phase"] = "workflow_execution"
    state["workflow"]["status"] = "running"
    _append_event(archive_dir, "arm_started", arm="workflow", command=workflow_command)
    _write_runner_state(archive_dir, state)
    workflow_execution = _run_command(
        workflow_command,
        cwd=workflow_workspace,
        archive_dir=archive_dir,
        arm="workflow",
        timeout_sec=workflow_timeout_sec,
        stream_output=stream_output,
    )
    state["workflow"]["status"] = (
        "timed_out"
        if workflow_execution["timed_out"]
        else ("succeeded" if workflow_execution["exit_code"] == 0 else "failed")
    )
    state["workflow"]["exit_code"] = workflow_execution["exit_code"]
    state["workflow"]["timed_out"] = workflow_execution["timed_out"]
    if workflow_execution["timed_out"]:
        _append_event(archive_dir, "arm_timeout", arm="workflow", timeout_sec=workflow_timeout_sec)
    _append_event(archive_dir, "arm_completed", arm="workflow", exit_code=workflow_execution["exit_code"])
    _write_runner_state(archive_dir, state)

    direct_metadata = archive_workspace_metadata(
        archive_dir=archive_dir,
        label="direct-run",
        workspace=direct_workspace,
        command=direct_command,
    )
    _write_freeze_manifest(archive_dir=archive_dir, arm="direct", workspace=direct_workspace)
    workflow_metadata = archive_workspace_metadata(
        archive_dir=archive_dir,
        label="workflow-run",
        workspace=workflow_workspace,
        command=workflow_command,
    )
    _write_freeze_manifest(archive_dir=archive_dir, arm="workflow", workspace=workflow_workspace)

    evaluator_command = _select_evaluator(seed_repo=Path(seed_repo), task_file=Path(task_file))
    direct_evaluation = None
    workflow_evaluation = None
    if evaluator_command is not None:
        _write_json(
            archive_dir / "evaluator" / "status.json",
            {"status": "running", "command": [*evaluator_command]},
        )
        state["current_phase"] = "evaluation"
        state["evaluation"]["status"] = "running"
        _write_runner_state(archive_dir, state)
        direct_evaluation = _run_evaluator(evaluator_command, direct_workspace)
        workflow_evaluation = _run_evaluator(evaluator_command, workflow_workspace)
        _write_json(archive_dir / "evaluator" / "direct-result.json", direct_evaluation)
        _write_json(archive_dir / "evaluator" / "workflow-result.json", workflow_evaluation)
        _write_json(
            archive_dir / "evaluator" / "status.json",
            {
                "status": "completed",
                "command": [*evaluator_command],
                "direct_verdict": direct_evaluation.get("verdict"),
                "workflow_verdict": workflow_evaluation.get("verdict"),
            },
        )
        state["evaluation"]["status"] = "completed"
        state["evaluation"]["direct_verdict"] = direct_evaluation.get("verdict")
        state["evaluation"]["workflow_verdict"] = workflow_evaluation.get("verdict")
        _write_runner_state(archive_dir, state)

    result = {
        "seed_repo": str(seed_repo),
        "task_file": str(task_file),
        "start_commit": metadata["start_commit"],
        "workflow_path": str(workflow_path),
        "direct": {
            "workspace": str(direct_workspace),
            "command": direct_command,
            "execution": direct_execution,
            "metadata": direct_metadata,
            "evaluation": direct_evaluation,
        },
        "workflow": {
            "workspace": str(workflow_workspace),
            "command": workflow_command,
            "execution": workflow_execution,
            "metadata": workflow_metadata,
            "evaluation": workflow_evaluation,
        },
    }
    _write_partial_result(archive_dir, result)
    state["status"] = "completed"
    state["current_phase"] = "completed"
    _append_event(archive_dir, "trial_completed")
    _write_runner_state(archive_dir, state)
    (archive_dir / "trial-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one demo trial and archive the result.")
    parser.add_argument("--seed-repo", required=True, help="Path to the task seed repository.")
    parser.add_argument("--experiment-root", required=True, help="Path to the trial root directory.")
    parser.add_argument("--task-file", required=True, help="Path to the shared task markdown file.")
    parser.add_argument(
        "--workflow",
        default=str(_repo_root() / "workflows" / "examples" / "generic_task_plan_execute_review_loop.yaml"),
        help="Workflow YAML to run for the workflow arm.",
    )
    parser.add_argument(
        "--direct-prompt",
        default="Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.",
        help="Single prompt for the direct arm.",
    )
    parser.add_argument("--commitish", default="HEAD", help="Seed revision to provision. Defaults to HEAD.")
    parser.add_argument(
        "--direct-provider",
        default="claude",
        choices=["claude", "codex"],
        help="Provider family for the direct arm.",
    )
    parser.add_argument(
        "--direct-model",
        default="claude-sonnet-4-6",
        help="Model alias/name for the direct arm provider.",
    )
    parser.add_argument(
        "--direct-effort",
        default="medium",
        choices=["low", "medium", "high"],
        help="Reasoning/effort level for the direct arm provider.",
    )
    parser.add_argument(
        "--workflow-provider",
        default="claude",
        choices=["claude", "codex"],
        help="Provider family for workflow provider steps.",
    )
    parser.add_argument(
        "--workflow-model",
        default="claude-sonnet-4-6",
        help="Model alias/name for workflow provider steps.",
    )
    parser.add_argument(
        "--workflow-effort",
        default="medium",
        choices=["low", "medium", "high"],
        help="Reasoning/effort level for workflow provider steps.",
    )
    parser.add_argument("--direct-timeout-sec", type=int, default=None, help="Timeout for the direct arm.")
    parser.add_argument("--workflow-timeout-sec", type=int, default=None, help="Timeout for the workflow arm.")
    parser.add_argument(
        "--stream-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stream direct/workflow stdout and stderr to the console while preserving archive logs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = run_trial(
        seed_repo=Path(args.seed_repo),
        experiment_root=Path(args.experiment_root),
        task_file=Path(args.task_file),
        workflow_path=Path(args.workflow),
        direct_prompt=args.direct_prompt,
        commitish=args.commitish,
        direct_provider=args.direct_provider,
        direct_model=args.direct_model,
        direct_effort=args.direct_effort,
        workflow_provider=args.workflow_provider,
        workflow_model=args.workflow_model,
        workflow_effort=args.workflow_effort,
        direct_timeout_sec=args.direct_timeout_sec,
        workflow_timeout_sec=args.workflow_timeout_sec,
        stream_output=args.stream_output,
    )
    print(json.dumps(result, indent=2))
    direct_verdict = (result["direct"]["evaluation"] or {}).get("verdict")
    workflow_verdict = (result["workflow"]["evaluation"] or {}).get("verdict")
    if direct_verdict == "PASS" and workflow_verdict == "PASS":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
