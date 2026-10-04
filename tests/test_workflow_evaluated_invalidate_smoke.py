"""Public compile/run/resume/invalidate/resume smoke for command and provider effects."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from tests.test_workflow_evaluated_providers import _fixture, _requests
from tests.test_workflow_evaluated_resume import _snapshot


SOURCE = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defworkflow run ((message String)) -> Result
    (let* ((built (command-result build :argv ("python" "command.py" message) :returns String))
           (review (provider-result providers.review :prompt prompts.base
             :inputs (message built) :model "chosen-model" :effort "low" :returns Result)))
      review)))
'''

COMMAND = '''\
import json
import os
import sys
from pathlib import Path

with Path("command-requests.jsonl").open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"argv": sys.argv[1:]}, ensure_ascii=False) + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
    json.dumps("command artifact ñ", ensure_ascii=False), encoding="utf-8"
)
'''


def _cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": str(root / "bin") + os.pathsep + os.environ["PATH"],
        "PYTHONPATH": str(Path(__file__).parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PROVIDER_SHIM_MODE": "success",
        "PROVIDER_SHIM_RESULT": '{"ok":true,"extra":7}',
    }
    return subprocess.run(
        [sys.executable, "-B", "-m", "orchestrator", *arguments],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _frontend_args(root: Path, fixture, boundaries: Path) -> list[str]:
    source, providers, prompts, _request = fixture
    return [
        str(source),
        "--entry-workflow", "main::run",
        "--source-root", str(root),
        "--provider-externs-file", str(providers),
        "--prompt-externs-file", str(prompts),
        "--command-boundaries-file", str(boundaries),
    ]


def _orchestrate_snapshot(root: Path) -> dict[str, bytes | None]:
    return _snapshot(root / ".orchestrate")


def _build_snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        path: content for path, content in _orchestrate_snapshot(root).items()
        if path.startswith("build/")
    }


def _checked_effects(run_root: Path):
    authority = load_run_authority(run_root)
    classes = site_classes(authority.program)
    memo = read_memo(authority.memo_path, classes)
    effects = {
        effect_class: [
            (identity, commit)
            for identity, commit in memo.active_commits.items()
            if classes.get(identity) == effect_class
        ]
        for effect_class in ("command", "provider")
    }
    assert len(effects["command"]) == len(effects["provider"]) == 1
    return authority, memo, effects


def _attempt_files(run_root: Path, commit) -> dict[str, bytes]:
    attempt = run_root / Path(commit.data["result_path"]).parent
    return {path.name: path.read_bytes() for path in attempt.iterdir() if path.is_file()}


def _command_requests(root: Path) -> list[dict]:
    path = root / "command-requests.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _assert_dispatch_counts(root: Path, count: int) -> None:
    assert [row["argv"] for row in _command_requests(root)] == [["typed input"]] * count
    requests = _requests(root)
    assert len(requests) == count
    assert all("chosen-model" in request["argv"] for request in requests)
    assert all("model_reasoning_effort=low" in request["argv"] for request in requests)


def _assert_completed(memo) -> None:
    assert memo.terminal is not None
    assert memo.terminal.data["outcome"] == "completed"
    assert memo.terminal.data["value"] == {"ok": True}


def _prepare_smoke(root: Path) -> dict:
    fixture = _fixture(root, SOURCE)
    (root / "command.py").write_text(COMMAND, encoding="utf-8")
    boundaries = root / "commands.json"
    boundaries.write_text(json.dumps({
        "build": {"stable_command": ["python", "command.py"], "closure": ["command.py"]}
    }), encoding="utf-8")
    frontend = _frontend_args(root, fixture, boundaries)
    compiled = _cli(root, "compile", *frontend)
    assert compiled.returncode == 0, compiled.stderr
    closed_artifact = Path(json.loads(compiled.stdout)["artifact_paths"]["closed_program"])
    assert closed_artifact.is_file()
    return {
        "fixture": fixture, "frontend": frontend, "boundaries": boundaries,
        "closed_artifact": closed_artifact, "artifact_bytes": closed_artifact.read_bytes(),
        "build": _build_snapshot(root),
    }


def _run_and_capture(root: Path, state: dict) -> None:
    run_result = _cli(root, "run", *state["frontend"], "--input", "message=typed input")
    assert run_result.returncode == 0, run_result.stderr
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    authority, memo, effects = _checked_effects(run_root)
    command_identity, command_commit = effects["command"][0]
    provider_identity, provider_commit = effects["provider"][0]
    assert provider_commit.data["depends_on"] == [command_identity]
    _assert_completed(memo)
    _assert_dispatch_counts(root, 1)
    state.update({
        "run_root": run_root, "authority": authority, "memo": memo,
        "command_identity": command_identity, "command_commit": command_commit,
        "provider_identity": provider_identity, "provider_commit": provider_commit,
        "attempt_one": {
            command_identity: _attempt_files(run_root, command_commit),
            provider_identity: _attempt_files(run_root, provider_commit),
        },
        "authority_bytes": {
            name: (run_root / name).read_bytes()
            for name in ("run.json", "closed_program.json")
        },
    })
    assert _build_snapshot(root) == state["build"]


def _assert_completed_resume_is_readonly(root: Path, state: dict) -> None:
    run_root = state["run_root"]
    completed_snapshot = _orchestrate_snapshot(root)
    requests_before = (root / "requests.jsonl").read_bytes()
    commands_before = (root / "command-requests.jsonl").read_bytes()
    completed_resume = _cli(root, "resume", run_root.name)
    assert completed_resume.returncode == 0, completed_resume.stderr
    assert _orchestrate_snapshot(root) == completed_snapshot
    assert (root / "requests.jsonl").read_bytes() == requests_before
    assert (root / "command-requests.jsonl").read_bytes() == commands_before
    _assert_dispatch_counts(root, 1)
    state["requests_before_resume"] = requests_before
    state["commands_before_resume"] = commands_before


def _invalidate_command_once(root: Path, state: dict) -> None:
    run_root = state["run_root"]
    authority = state["authority"]
    command_identity = state["command_identity"]
    command_commit = state["command_commit"]
    memo_before = authority.memo_path.read_bytes()
    invalidated = _cli(root, "invalidate", run_root.name, command_identity)
    assert invalidated.returncode == 0, invalidated.stderr
    invalidation_row = json.loads(invalidated.stdout)
    after_invalidate = read_memo(authority.memo_path, site_classes(authority.program))
    rows = [entry.data for entry in after_invalidate.entries if entry.data["record"] == "invalidated"]
    assert rows == [invalidation_row]
    assert invalidation_row["from_commit"] == command_commit.offset
    assert authority.memo_path.read_bytes().startswith(memo_before)
    _assert_prior_evidence(root, state)
    state["inactive_snapshot"] = _orchestrate_snapshot(root)
    state["memo_after_invalidate"] = authority.memo_path.read_bytes()
    state["requests_after_invalidate"] = (root / "requests.jsonl").read_bytes()
    state["commands_after_invalidate"] = (root / "command-requests.jsonl").read_bytes()


def _assert_prior_evidence(root: Path, state: dict) -> None:
    run_root = state["run_root"]
    authority_bytes = state["authority_bytes"]
    assert _attempt_files(run_root, state["command_commit"]) == state["attempt_one"][state["command_identity"]]
    assert _attempt_files(run_root, state["provider_commit"]) == state["attempt_one"][state["provider_identity"]]
    assert {name: (run_root / name).read_bytes() for name in authority_bytes} == authority_bytes
    assert _build_snapshot(root) == state["build"]


def _assert_inactive_invalidation_is_readonly(root: Path, state: dict) -> None:
    run_root = state["run_root"]
    command_identity = state["command_identity"]
    inactive = _cli(root, "invalidate", run_root.name, command_identity)
    assert inactive.returncode == 2
    assert "invalidate_not_committed" in inactive.stderr
    assert _orchestrate_snapshot(root) == state["inactive_snapshot"]
    assert state["authority"].memo_path.read_bytes() == state["memo_after_invalidate"]
    assert (root / "requests.jsonl").read_bytes() == state["requests_after_invalidate"]
    assert (root / "command-requests.jsonl").read_bytes() == state["commands_after_invalidate"]
    _assert_dispatch_counts(root, 1)


def _resume_invalidated_suffix(root: Path, state: dict) -> None:
    run_root = state["run_root"]
    resumed = _cli(root, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    after_authority, after_memo, after_effects = _checked_effects(run_root)
    _assert_replayed_suffix(root, state, after_authority, after_memo, after_effects)


def _assert_replayed_suffix(root: Path, state: dict, authority, memo, effects) -> None:
    command_identity = state["command_identity"]
    provider_identity = state["provider_identity"]
    assert authority.program.digest == state["authority"].program.digest
    assert memo.active_commits[command_identity].data["attempt"] == 2
    assert memo.active_commits[provider_identity].data["attempt"] == 2
    assert memo.latest_starts[command_identity].data["attempt"] == 2
    assert memo.latest_starts[provider_identity].data["attempt"] == 2
    assert effects["command"][0][0] == command_identity
    assert effects["provider"][0][0] == provider_identity
    _assert_completed(memo)
    _assert_dispatch_counts(root, 2)
    _assert_prior_evidence(root, state)
    assert (root / "requests.jsonl").read_bytes().startswith(state["requests_before_resume"])
    assert (root / "command-requests.jsonl").read_bytes().startswith(state["commands_before_resume"])
    assert state["closed_artifact"].read_bytes() == state["artifact_bytes"]


def test_public_compile_run_resume_invalidate_resume_keeps_provider_command_evidence(tmp_path: Path) -> None:
    state = _prepare_smoke(tmp_path)
    _run_and_capture(tmp_path, state)
    _assert_completed_resume_is_readonly(tmp_path, state)
    _invalidate_command_once(tmp_path, state)
    _assert_inactive_invalidation_is_readonly(tmp_path, state)
    _resume_invalidated_suffix(tmp_path, state)
