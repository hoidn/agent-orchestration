"""Observers around real public CLI calls, shared by E1 and external K4 tests."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from dataclasses import dataclass
import base64
from orchestrator.workflow.run_ref import wire
from orchestrator.workflow.run_ref.contracts import canonical_sha256, compute_compiler_runtime_identity
from orchestrator.workflow.run_ref.config import PathProgram, ReferenceBinding, RunRefInput, build_run_ref_static_config, encode_run_ref_static_config
from orchestrator.workflow.run_ref.result_contract import RUN_REF_RESULT_CONTRACT_SCHEMA, _accounting_descriptor, _workspace_delta_descriptor
from orchestrator.workflow.run_ref.source import MaterializedSource, SourceRequest, materialize_source
from orchestrator.workflow.executable_ir import RunRefStepConfig, StepCommonConfig

_PATH_SITE = "71d55760c27a0d51" + "0" * 48
_STRING_DESCRIPTOR = {"kind": "primitive", "name": "String"}



_CONTROL_RUNNER = r"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from orchestrator._common.io_atomic import durable_atomic_write
from orchestrator.workflow.evaluated import run_ref as evaluated_run_ref
from orchestrator.workflow.evaluated import runtime as evaluated_runtime
from orchestrator.workflow.run_ref import runtime as run_ref_runtime

control = Path(os.environ["TASK9G_CONTROL"])
gate = os.environ.get("TASK9G_GATE", "")

def append_log(name, record):
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with (control / name).open("ab", buffering=0) as stream:
        stream.write(payload)
        os.fsync(stream.fileno())

append_log("processes.jsonl", {
    "pid": os.getpid(), "pgid": os.getpgrp(),
    "argv": ["orchestrator", *sys.argv[1:]],
})

def pause_at_marker(record):
    record["runner_pid"] = os.getpid()
    record["runner_pgid"] = os.getpgrp()
    durable_atomic_write(control / "marker.json",
                         json.dumps(record, sort_keys=True, separators=(",", ":")).encode())
    while True:
        time.sleep(1)

real_popen = subprocess.Popen
launch_number = 0

def record_popen(*args, **kwargs):
    global launch_number
    process = real_popen(*args, **kwargs)
    command = args[0] if args else kwargs["args"]
    argv = [str(token) for token in command] if not isinstance(command, str) else [command]
    try:
        pgid = os.getpgid(process.pid)
    except ProcessLookupError:
        pgid = None
    append_log("processes.jsonl", {
        "pid": process.pid, "pgid": pgid, "runner_pgid": os.getpgrp(), "argv": argv,
    })
    if "--path-request" in argv:
        launch_number += 1
        request_path = Path(argv[argv.index("--path-request") + 1])
        request_bytes = request_path.read_bytes()
        request = json.loads(request_bytes)
        append_log("launches.jsonl", {
            "number": launch_number,
            "pid": process.pid,
            "pgid": pgid,
            "runner_pgid": os.getpgrp(),
            "argv": argv,
            "request_path": str(request_path),
            "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
            "child_run_id": request["child_run_id"],
            "parent_authority": request["parent_authority"],
        })
    return process

subprocess.Popen = record_popen

real_persist = run_ref_runtime.persist_run_ref_lifecycle_event
pending_count = 0

def record_lifecycle(request, event):
    global pending_count
    acknowledgement = real_persist(request, event)
    if event.stage == "completed_pending_parent_commit":
        pending_count += 1
        append_log("lifecycle.jsonl", {
            "count": pending_count,
            "stage": event.stage,
            "identity": request.parent_identity,
            "parent_attempt": request.parent_attempt,
            "attempt_ordinal": event.attempt_ordinal,
            "visit": event.visit.record,
            "event_digest": event.event_digest,
        })
        if gate == "pending" and pending_count == 2:
            pause_at_marker({
                "gap": gate,
                "identity": request.parent_identity,
                "parent_attempt": request.parent_attempt,
                "attempt_ordinal": event.attempt_ordinal,
                "visit": event.visit.record,
                "event_digest": event.event_digest,
            })
    return acknowledgement

run_ref_runtime.persist_run_ref_lifecycle_event = record_lifecycle

real_append = evaluated_runtime.append_record
run_ref_commits = 0

def record_append(*args, **kwargs):
    global run_ref_commits
    record = args[1] if len(args) > 1 else kwargs["record"]
    entry = real_append(*args, **kwargs)
    if record.get("record") == "committed" and record.get("effect_class") == "run_ref":
        run_ref_commits += 1
        append_log("memo.jsonl", {
            "count": run_ref_commits,
            "identity": record["identity"],
            "attempt": record["attempt"],
            "proof": record["proof"],
        })
        if gate == "memo" and run_ref_commits == 2:
            pause_at_marker({
                "gap": gate,
                "identity": record["identity"],
                "parent_attempt": record["attempt"],
                "attempt_ordinal": record["proof"]["settled_result"]["attempt_ordinal"],
                "visit": record["proof"]["settled_result"]["visit"],
            })
    return entry

evaluated_runtime.append_record = record_append

real_finalize = evaluated_run_ref.finalize_run_ref_parent_commit

def record_finalize(request, *args, **kwargs):
    result = real_finalize(request, *args, **kwargs)
    append_log("finalize.jsonl", {
        "identity": request.parent_identity,
        "parent_attempt": request.parent_attempt,
        "visit": request.visit.record,
    })
    return result

evaluated_run_ref.finalize_run_ref_parent_commit = record_finalize

real_recover = evaluated_run_ref.recover_run_ref_settlement

def record_recover(request, *args, **kwargs):
    result = real_recover(request, *args, **kwargs)
    append_log("reconcile.jsonl", {
        "identity": request.parent_identity,
        "parent_attempt": request.parent_attempt,
        "visit": request.visit.record,
        "reconcile_pending": kwargs["reconcile_pending"],
    })
    return result

evaluated_run_ref.recover_run_ref_settlement = record_recover

from orchestrator.cli import main
raise SystemExit(main())
"""


def _json_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def _assert_no_child_resume(control: Path, child_run_ids: set[str]) -> None:
    calls = [row["argv"] for row in _json_lines(control / "processes.jsonl")]
    assert not [argv for argv in calls if "resume" in argv and any(
        child_id in arg for child_id in child_run_ids for arg in argv
    )]


def _environment(control: Path, gate: str | None) -> dict[str, str]:
    repo_root = Path(__file__).resolve().parents[1]
    return {
        **os.environ,
        "PYTHONPATH": str(repo_root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "TASK9G_CONTROL": str(control),
        "TASK9G_GATE": gate or "",
    }


def _start_cli(parent: Path, control: Path, arguments: list[str], *, gate: str | None = None):
    control.mkdir(parents=True, exist_ok=True)
    runner = control / "cli_with_run_ref_observer.py"
    if not runner.exists():
        runner.write_text(_CONTROL_RUNNER, encoding="utf-8")
    number = len(list(control.glob("stdout-*.log"))) + 1
    stdout_path = control / f"stdout-{number}.log"
    stderr_path = control / f"stderr-{number}.log"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            [sys.executable, str(runner), *arguments],
            cwd=parent,
            env=_environment(control, gate),
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
    pgid = os.getpgid(process.pid)
    assert pgid == process.pid
    return process, pgid, stdout_path, stderr_path


def _output(stdout_path: Path, stderr_path: Path) -> str:
    return (
        stdout_path.read_text(encoding="utf-8", errors="replace")
        + stderr_path.read_text(encoding="utf-8", errors="replace")
    )


def _kill_own_group(process: subprocess.Popen, pgid: int) -> None:
    assert pgid == process.pid
    if process.poll() is None:
        assert os.getpgid(process.pid) == pgid
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def _wait_for_marker(process, stdout_path: Path, stderr_path: Path, control: Path) -> dict:
    marker_path = control / "marker.json"
    deadline = time.monotonic() + 15
    while process.poll() is None and not marker_path.is_file() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not marker_path.is_file():
        _kill_own_group(process, process.pid)
        pytest.fail(f"runner missed the causal marker:\n{_output(stdout_path, stderr_path)}")
    marker = json.loads(marker_path.read_bytes())
    assert process.poll() is None, _output(stdout_path, stderr_path)
    assert marker["runner_pid"] == process.pid
    assert marker["runner_pgid"] == process.pid
    return marker


def _run_to_exit(parent: Path, control: Path, arguments: list[str]) -> str:
    process, pgid, stdout_path, stderr_path = _start_cli(parent, control, arguments)
    try:
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _kill_own_group(process, pgid)
            pytest.fail(f"public CLI timed out:\n{_output(stdout_path, stderr_path)}")
        output = _output(stdout_path, stderr_path)
        assert process.returncode == 0, output
        return output
    finally:
        _kill_own_group(process, pgid)


@dataclass(frozen=True)
class _PathFixture:
    materialized_source: MaterializedSource
    step_config: RunRefStepConfig
    child_run_id: str
    state_dir: Path
    request_path: Path


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", repo.as_posix(), *args),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _path_result_descriptor() -> dict[str, object]:
    envelope = {
        "kind": "record",
        "name": f"RunRefResult${_PATH_SITE[:16]}",
        "fields": [
            {"name": "value", "type": _STRING_DESCRIPTOR},
            {"name": "workspace_delta", "type": _workspace_delta_descriptor()},
            {"name": "accounting", "type": _accounting_descriptor()},
        ],
    }
    return {"schema": RUN_REF_RESULT_CONTRACT_SCHEMA, "envelope": envelope}


def _build_path_fixture(
    root: Path,
    *,
    body: str = "payload",
    case: str = "executes",
    target_dsl_version: str = "2.35",
) -> _PathFixture:
    repository = root / f"repository-{case}"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    (repository / "candidate.orc").write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                f'  (:target-dsl "{target_dsl_version}")',
                "  (defmodule candidate)",
                "  (export run)",
                "  (defworkflow run ((payload String)) -> String",
                f"    {body}))",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    _git(repository, "add", "candidate.orc")
    _git(
        repository,
        "-c",
        "user.name=Run Ref Child Test",
        "-c",
        "user.email=run-ref-child@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "fixture",
    )
    commit = _git(repository, "rev-parse", "HEAD")
    source = SourceRequest(locator=repository.resolve().as_uri(), commit=commit)
    run_ref_root = (root / f"run-ref-{case}").resolve()
    workspace = (
        run_ref_root / "runs" / "parent" / "step" / "1" / "workspace"
    ).resolve()
    materialized = materialize_source(
        source,
        run_ref_root=run_ref_root,
        workspace=workspace,
    )
    result_descriptor = _path_result_descriptor()
    static_config = build_run_ref_static_config(
        compiler_runtime_identity_digest=compute_compiler_runtime_identity().digest,
        site_digest=_PATH_SITE,
        source=source,
        program=PathProgram(
            path="candidate.orc",
            entry_name="run",
            return_refinement=_STRING_DESCRIPTOR,
        ),
        inputs=(
            RunRefInput(
                name="payload",
                type_descriptor=_STRING_DESCRIPTOR,
                binding=ReferenceBinding("inputs.payload"),
            ),
        ),
        result_descriptor=result_descriptor,
        result_digest=canonical_sha256(result_descriptor),
    )
    step_config = RunRefStepConfig(
        common=StepCommonConfig(),
        run_ref=static_config,
    )
    return _PathFixture(
        materialized_source=materialized,
        step_config=step_config,
        child_run_id=f"path-child-{case}",
        state_dir=workspace / ".orchestrate" / "runs",
        request_path=root / f"path-request-{case}.json",
    )


def _path_request(fixture: _PathFixture) -> dict[str, object]:
    static_config_bytes = encode_run_ref_static_config(
        fixture.step_config.run_ref
    )
    return {
        "schema_version": "run_ref_path_child_request.v1",
        "clone_root": fixture.materialized_source.workspace_path.as_posix(),
        "child_state_dir": fixture.state_dir.as_posix(),
        "child_run_id": fixture.child_run_id,
        "materialized_source": wire.materialized_source_record(
            fixture.materialized_source
        ),
        "run_ref_static_config_base64": base64.b64encode(
            static_config_bytes
        ).decode("ascii"),
        "expected_step_config_digest": fixture.step_config.step_config_digest,
        "inputs": {"payload": "mode2-child-input"},
        "test_control": None,
    }


def _commit_candidate(repository: Path, source: str) -> str:
    repository.mkdir()
    _git(repository, "init", "--quiet")
    (repository / "candidate.orc").write_text(source, encoding="utf-8")
    _git(repository, "add", "candidate.orc")
    _git(
        repository,
        "-c",
        "user.name=Run Ref E2E",
        "-c",
        "user.email=run-ref-e2e@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "candidate",
    )
    return _git(repository, "rev-parse", "HEAD")


def _assert_complete_evidence_manifest(
    attempt_root: Path,
    *,
    settlement: dict,
    mode: str,
) -> dict:
    manifest = json.loads(
        (attempt_root / "evidence-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == "run_ref_evidence_manifest.v1"
    assert manifest["mode"] == mode
    assert manifest["attempt_ordinal"] == settlement["attempt_ordinal"]
    assert manifest["child_run_id"] == settlement["child_run_id"]
    assert manifest["step_config_digest"] == settlement["step_config_digest"]
    assert manifest["child_terminal_state_digest"] == settlement[
        "child_terminal_state_digest"
    ]
    assert manifest["result_contract_digest"] == settlement[
        "result_contract_digest"
    ]
    assert manifest["result_payload_digest"] == settlement[
        "result_payload_digest"
    ]
    assert manifest["workspace_delta_digest"] == settlement[
        "workspace_delta_digest"
    ]
    assert manifest["accounting_digest"] == settlement["accounting_digest"]
    assert canonical_sha256(manifest) == settlement["evidence_manifest_digest"]
    assert set(manifest["paths"]) == {
        "accounting",
        "baseline",
        "child_request",
        "child_result",
        "child_state",
        "setup_evidence",
        "workspace",
        "workspace_delta",
    }
    assert all(Path(value).exists() for value in manifest["paths"].values())
    return manifest
