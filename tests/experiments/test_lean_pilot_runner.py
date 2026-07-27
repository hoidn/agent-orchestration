from __future__ import annotations

import ast
import hashlib
import importlib
import json
import os
import signal
import shutil
import subprocess
import sys
import threading
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, Callable

import pytest

from orchestrator.experiments import (
    _runner_apparatus as runner_apparatus,
    _runner_block as runner_block,
    _runner_execution as runner_execution,
    _runner_preflight as runner_preflight,
    _runner_types as runner_types,
    contracts,
    workspace,
)


ARM_PROGRAM = (
    Path(__file__).parent / "fixtures" / "lean_pilot" / "arm_program.py"
).resolve()


@pytest.fixture(scope="module")
def runner() -> ModuleType:
    return importlib.import_module("orchestrator.experiments.runner")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _write_asset(
    control_root: Path,
    relative_path: str,
    value: bytes | dict[str, Any],
) -> dict[str, str]:
    data = (
        value
        if isinstance(value, bytes)
        else json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    )
    path = control_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": relative_path, "sha256": _sha256(data)}


def _committed_repo(root: Path) -> tuple[Path, str, str]:
    repo = root / "source"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("lean pilot source\n", encoding="utf-8")
    _git(repo, "add", "--all")
    _git(
        repo,
        "-c",
        "user.name=Lean Pilot Test",
        "-c",
        "user.email=lean-pilot@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "fixture",
    )
    commit = _git(repo, "rev-parse", "HEAD")
    archive = workspace.materialize_git_archive(
        repo,
        commit,
        root / "archive-digest-probe",
    )
    return repo, commit, archive.digest


def _pilot_lock(
    root: Path,
    evidence_root: Path,
) -> dict[str, Any]:
    repo, commit, archive_digest = _committed_repo(root)
    control_root = (root / "controller").resolve()
    control_root.mkdir()
    environment_identity = _sha256(b"fixture-environment")

    manifest = [
        _write_asset(control_root, "tasks/A1.md", b"Implement the fixture.\n"),
        _write_asset(
            control_root,
            "config/provider.json",
            {"providers.review": "fixture-provider"},
        ),
        _write_asset(
            control_root,
            "config/prompts.json",
            {"prompts.review": "prompts/review.md"},
        ),
        _write_asset(
            control_root,
            "config/commands.json",
            {
                "record_approved": {
                    "kind": "external_tool",
                    "stable_command": ["true"],
                },
                "record_revise": {
                    "kind": "external_tool",
                    "stable_command": ["true"],
                },
            },
        ),
        _write_asset(
            control_root,
            "prompts/review.md",
            b"Return whether the fixture is approved.\n",
        ),
        _write_asset(
            control_root,
            "fixture.orc",
            (
                b'(workflow-lisp\n'
                b'  (:language "0.1")\n'
                b'  (:target-dsl "2.15")\n'
                b'  (defmodule fixture)\n'
                b'  (export decide)\n'
                b'  (defworkflow decide\n'
                b'    ()\n'
                b'    -> Bool\n'
                b'    (let* ((approved\n'
                b'             (provider-result providers.review\n'
                b'               :prompt prompts.review\n'
                b'               :inputs ()\n'
                b'               :returns Bool)))\n'
                b'      (if approved\n'
                b'        (command-result record_approved\n'
                b'          :argv ("true")\n'
                b'          :returns Bool)\n'
                b'        (command-result record_revise\n'
                b'          :argv ("true")\n'
                b'          :returns Bool)))))\n'
            ),
        ),
        _write_asset(
            control_root,
            "fixture/arm_program.py",
            ARM_PROGRAM.read_bytes(),
        ),
    ]
    command_assets: dict[str, dict[str, str]] = {}
    for treatment_id, call_count in (
        ("DIRECT", 1),
        ("COORDINATOR", 5),
        ("ORC", 5),
    ):
        relative_path = f"config/treatments/{treatment_id.lower()}.json"
        command_assets[treatment_id] = _write_asset(
            control_root,
            relative_path,
            {
                "argv": [
                    sys.executable,
                    "{apparatus_root}/fixture/arm_program.py",
                    "--mode",
                    "success",
                    "--result-file",
                    "{result_path}",
                    "--provider-call-count",
                    str(call_count),
                    "--apparatus-root",
                    "{apparatus_root}",
                    "--task-path",
                    "{task_path}",
                    "--provider-config",
                    "{provider_config}",
                    "--prompt-config",
                    "{prompt_config}",
                    "--command-config",
                    "{command_config}",
                ],
                "environment": {"PYTHONUNBUFFERED": "1"},
                "environment_identity": environment_identity,
                "timeout_milliseconds": 10_000,
            },
        )
        manifest.append(command_assets[treatment_id])

    task_digest = manifest[0]["sha256"]
    treatments = []
    for treatment_id, bounds in (
        ("DIRECT", {"minimum": 1, "maximum": 1}),
        ("COORDINATOR", {"minimum": 3, "maximum": 9}),
        ("ORC", {"minimum": 3, "maximum": 9}),
    ):
        command_asset = command_assets[treatment_id]
        treatments.append(
            {
                "treatment_id": treatment_id,
                "source_digest": _sha256(f"{treatment_id}-source".encode()),
                "command_digest": command_asset["sha256"],
                "command_config_path": command_asset["path"],
                "provider_call_bounds": bounds,
            }
        )

    return {
        "record_kind": "pilot_lock.v1",
        "pilot_id": "lean-pilot-runner-fixture",
        "task": {
            "task_id": "A1",
            "profile_digest": _sha256(b"task-profile"),
            "brief_digest": task_digest,
        },
        "archive": {
            "repository_identity": str(repo.resolve()),
            "revision_identity": f"commit:{commit}",
            "archive_digest": archive_digest,
        },
        "provider_policy": {
            "family": "fixture",
            "model": "fixture-model",
            "reasoning_effort": "none",
            "tool_policy": "workspace-only",
            "timeout_milliseconds": 10_000,
            "currency": "USD",
        },
        "review": {
            "reviewer_ids": ["fixture-reviewer-1", "fixture-reviewer-2"],
            "rubric_digest": _sha256(b"rubric"),
            "calibration_evidence_digest": _sha256(b"calibration"),
        },
        "apparatus": {
            "control_root": control_root.as_posix(),
            "asset_manifest": manifest,
            "task_path": "tasks/A1.md",
            "provider_config_path": "config/provider.json",
            "prompt_config_path": "config/prompts.json",
            "command_config_path": "config/commands.json",
            "environment": {
                "identity": environment_identity,
                "allowed_keys": [
                    "HOME",
                    "PYTHONUNBUFFERED",
                    "TMPDIR",
                ],
                "credential_keys": [],
            },
            "visible_check": {
                "argv": [sys.executable, "-c", "raise SystemExit(0)"],
                "timeout_milliseconds": 10_000,
            },
            "product_projection_exclusions": [".pilot/runtime"],
            "maximum_start_skew_milliseconds": 2_000,
            "quiescence_grace_milliseconds": 100,
        },
        "randomization_seed": "runner-fixture-seed",
        "evidence_root": evidence_root.resolve().as_posix(),
        "valid_block_count": 3,
        "max_live_attempt_count": 5,
        "smoke_id": "smoke-001",
        "live_attempt_ids": [
            "live-001",
            "live-002",
            "live-003",
            "live-004",
            "live-005",
        ],
        "claim_level": "exploratory_controlled_task",
        "treatments": treatments,
    }


def _rewrite_treatment_config(
    lock: dict[str, Any],
    treatment_id: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    treatment = next(
        item
        for item in lock["treatments"]
        if item["treatment_id"] == treatment_id
    )
    relative_path = treatment["command_config_path"]
    path = Path(lock["apparatus"]["control_root"]) / relative_path
    config = json.loads(path.read_text(encoding="utf-8"))
    mutate(config)
    data = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(data)
    digest = _sha256(data)
    treatment["command_digest"] = digest
    manifest_entry = next(
        item
        for item in lock["apparatus"]["asset_manifest"]
        if item["path"] == relative_path
    )
    manifest_entry["sha256"] = digest
    contracts.validate_record(lock)


def _rewrite_manifest_json(
    lock: dict[str, Any],
    relative_path: str,
    value: dict[str, Any],
) -> None:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    (Path(lock["apparatus"]["control_root"]) / relative_path).write_bytes(data)
    entry = next(
        item
        for item in lock["apparatus"]["asset_manifest"]
        if item["path"] == relative_path
    )
    entry["sha256"] = _sha256(data)
    contracts.validate_record(lock)


def _rewrite_all_treatment_configs(
    lock: dict[str, Any],
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    for treatment_id in ("DIRECT", "COORDINATOR", "ORC"):
        _rewrite_treatment_config(lock, treatment_id, mutate)


def _evidence_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _block_record_path(evidence_root: Path, block_id: str) -> Path:
    matches = []
    for path in evidence_root.rglob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if (
            isinstance(value, dict)
            and value.get("record_kind") == "block_attempt.v1"
            and value.get("block_id") == block_id
        ):
            matches.append(path)
    assert len(matches) == 1
    return matches[0]


def _fixture_events(evidence_root: Path, event: str) -> list[dict[str, Any]]:
    events = []
    for path in evidence_root.rglob("*"):
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line in lines:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("fixture_event") == event:
                events.append(value)
    return events


def _execution(record: dict[str, Any], treatment_id: str) -> dict[str, Any]:
    return next(
        item
        for item in record["treatment_executions"]
        if item["treatment_id"] == treatment_id
    )


def _configure_arm(
    lock: dict[str, Any],
    treatment_id: str,
    *,
    mode: str | None = None,
    provider_call_count: int | None = None,
    executable: str | None = None,
    timeout_milliseconds: int | None = None,
    wait_seconds: int | None = None,
    result_fault: str | None = None,
    terminal_outcome: str | None = None,
) -> None:
    def mutate(config: dict[str, Any]) -> None:
        argv = config["argv"]
        if mode is not None:
            argv[argv.index("--mode") + 1] = mode
        if provider_call_count is not None:
            argv[argv.index("--provider-call-count") + 1] = str(
                provider_call_count
            )
        if executable is not None:
            argv[0] = executable
        if timeout_milliseconds is not None:
            config["timeout_milliseconds"] = timeout_milliseconds
        if wait_seconds is not None:
            argv.extend(["--wait-seconds", str(wait_seconds)])
        if result_fault is not None:
            argv.extend(["--result-fault", result_fault])
        if terminal_outcome is not None:
            argv.extend(["--terminal-outcome", terminal_outcome])

    _rewrite_treatment_config(lock, treatment_id, mutate)


def _observe_atomic_records(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    observed: list[dict[str, Any]] = []
    real_replace = os.replace

    def replace(source: str | Path, destination: str | Path) -> None:
        data = Path(source).read_bytes()
        try:
            value = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError):
            value = None
        if isinstance(value, dict) and value.get("record_kind") == "block_attempt.v1":
            contracts.validate_record(value)
            observed.append(value)
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    return observed


def test_run_smoke_block_persists_three_frozen_treatments(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    work_root = tmp_path / "work"
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    contracts.validate_record(lock)

    attempt = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=work_root,
        evidence_root=evidence_root,
    )

    record = attempt.record
    contracts.validate_record(record)
    assert record["status"] == "VALID"
    executions = record["treatment_executions"]
    assert len(executions) == 3
    assert all(execution["product_frozen"] for execution in executions)
    assert {
        execution["treatment_id"]: execution["provider_call_count"]
        for execution in executions
    } == {"DIRECT": 1, "COORDINATOR": 5, "ORC": 5}


def test_run_smoke_block_needs_no_fixture_identity(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert record["attempt_class"] == "SMOKE"
    assert record["status"] == "VALID"


@pytest.mark.parametrize(
    "mutation",
    ["missing", "changed-bytes", "symlink"],
)
def test_manifest_asset_faults_reject_before_evidence_or_workspace(
    runner: ModuleType,
    tmp_path: Path,
    mutation: str,
) -> None:
    work_root = tmp_path / "work"
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    asset = (
        Path(lock["apparatus"]["control_root"])
        / lock["apparatus"]["provider_config_path"]
    )
    if mutation == "missing":
        asset.unlink()
    elif mutation == "changed-bytes":
        asset.write_bytes(asset.read_bytes() + b"\n")
    else:
        original = asset.read_bytes()
        outside = tmp_path / "outside-provider.json"
        outside.write_bytes(original)
        asset.unlink()
        asset.symlink_to(outside)

    with pytest.raises(ValueError):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=work_root,
            evidence_root=evidence_root,
        )

    assert not evidence_root.exists()
    assert not work_root.exists()


@pytest.mark.parametrize(
    "fault",
    [
        "unknown-field",
        "unknown-placeholder",
        "unallowed-environment-key",
        "environment-identity-mismatch",
    ],
)
def test_treatment_config_faults_reject_before_started(
    runner: ModuleType,
    tmp_path: Path,
    fault: str,
) -> None:
    work_root = tmp_path / "work"
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)

    def mutate(config: dict[str, Any]) -> None:
        if fault == "unknown-field":
            config["unexpected"] = True
        elif fault == "unknown-placeholder":
            config["argv"].append("{peer_workspace}")
        elif fault == "unallowed-environment-key":
            config["environment"]["UNLOCKED_VALUE"] = "present"
        else:
            config["environment_identity"] = _sha256(b"different-environment")

    _rewrite_treatment_config(lock, "DIRECT", mutate)

    with pytest.raises(ValueError):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=work_root,
            evidence_root=evidence_root,
        )

    assert not evidence_root.exists()
    assert not work_root.exists()


@pytest.mark.parametrize(
    ("role", "legacy_value"),
    [
        (
            "provider_config_path",
            {"credential_environment_keys": ["OPENAI_API_KEY"]},
        ),
        (
            "command_config_path",
            {"environment": {"PYTHONUNBUFFERED": "1"}},
        ),
    ],
)
def test_legacy_custom_role_manifest_shapes_reject_before_started(
    runner: ModuleType,
    tmp_path: Path,
    role: str,
    legacy_value: dict[str, Any],
) -> None:
    work_root = tmp_path / "work"
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    _rewrite_manifest_json(lock, lock["apparatus"][role], legacy_value)

    with pytest.raises(ValueError, match="standard Workflow Lisp"):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=work_root,
            evidence_root=evidence_root,
        )

    assert not evidence_root.exists()
    assert not work_root.exists()


def test_standard_asset_file_prompt_binding_is_accepted(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    _rewrite_manifest_json(
        lock,
        lock["apparatus"]["prompt_config_path"],
        {"prompts.review": {"asset_file": "prompts/review.md"}},
    )

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert record["status"] == "VALID"


def test_input_file_prompt_binding_rejects_before_started(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    work_root = tmp_path / "work"
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    _rewrite_manifest_json(
        lock,
        lock["apparatus"]["prompt_config_path"],
        {"prompts.review": {"input_file": "prompts/review.md"}},
    )

    with pytest.raises(ValueError, match="asset_file"):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=work_root,
            evidence_root=evidence_root,
        )

    assert not evidence_root.exists()
    assert not work_root.exists()


@pytest.mark.parametrize(
    ("fault", "expected"),
    [
        ("missing-launcher-key", "exact locked non-controller"),
        ("credential-overlap", "exact locked non-controller"),
        ("controller-key", "controller-owned"),
    ],
)
def test_treatment_environment_partition_rejects_before_started(
    runner: ModuleType,
    tmp_path: Path,
    fault: str,
    expected: str,
) -> None:
    work_root = tmp_path / "work"
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    if fault == "credential-overlap":
        secret_name = "LEAN_PILOT_TEST_SECRET"
        lock["apparatus"]["environment"]["allowed_keys"].append(secret_name)
        lock["apparatus"]["environment"]["credential_keys"] = [secret_name]

        def mutate(config: dict[str, Any]) -> None:
            config["environment"][secret_name] = "must-not-override"

    elif fault == "controller-key":

        def mutate(config: dict[str, Any]) -> None:
            config["environment"]["HOME"] = "/unlocked/home"

    else:

        def mutate(config: dict[str, Any]) -> None:
            del config["environment"]["PYTHONUNBUFFERED"]

    _rewrite_treatment_config(lock, "DIRECT", mutate)

    with pytest.raises(ValueError, match=expected):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=work_root,
            evidence_root=evidence_root,
        )

    assert not evidence_root.exists()
    assert not work_root.exists()


def test_empty_treatment_argv_rejects_before_started(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    work_root = tmp_path / "work"
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)

    def remove_command(config: dict[str, Any]) -> None:
        config["argv"] = []

    _rewrite_treatment_config(lock, "DIRECT", remove_command)

    with pytest.raises(ValueError, match="argv"):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=work_root,
            evidence_root=evidence_root,
        )

    assert not evidence_root.exists()
    assert not work_root.exists()


@pytest.mark.parametrize("required_key", ["HOME", "TMPDIR"])
def test_controller_owned_runtime_key_is_required_before_started(
    runner: ModuleType,
    tmp_path: Path,
    required_key: str,
) -> None:
    work_root = tmp_path / "work"
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    lock["apparatus"]["environment"]["allowed_keys"].remove(required_key)

    with pytest.raises(ValueError, match="missing_controller_environment_key"):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=work_root,
            evidence_root=evidence_root,
        )

    assert not evidence_root.exists()
    assert not work_root.exists()


def test_preflight_assigns_distinct_controller_owned_runtime_roots(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    work_root = (tmp_path / "work").resolve()
    evidence_root = (tmp_path / "evidence").resolve()
    lock = _pilot_lock(tmp_path, evidence_root)

    preflight = runner_preflight._preflight(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=work_root,
        evidence_root=evidence_root,
    )

    homes = []
    temporary_roots = []
    for arm in preflight.arms:
        environment = dict(arm.command.environment)
        homes.append(environment["HOME"])
        temporary_roots.append(environment["TMPDIR"])
        assert environment["HOME"] == str(arm.command.runtime_root / "home")
        assert environment["TMPDIR"] == str(arm.command.runtime_root / "tmp")
    assert len(set(homes)) == 3
    assert len(set(temporary_roots)) == 3
    assert not evidence_root.exists()
    assert not work_root.exists()


def test_controller_runtime_keys_cannot_be_provider_credentials(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    work_root = tmp_path / "work"
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    lock["apparatus"]["environment"]["credential_keys"] = ["HOME"]

    with pytest.raises(ValueError, match="controller_environment_key"):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=work_root,
            evidence_root=evidence_root,
        )

    assert not evidence_root.exists()
    assert not work_root.exists()


def test_empty_locked_credential_list_remains_valid(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert record["status"] == "VALID"


@pytest.mark.parametrize(
    "root_relation",
    ["equal", "work-under-evidence", "evidence-under-work"],
)
def test_work_and_evidence_roots_must_be_disjoint_before_started(
    runner: ModuleType,
    tmp_path: Path,
    root_relation: str,
) -> None:
    shared = tmp_path / "shared"
    if root_relation == "equal":
        work_root = shared
        evidence_root = shared
    elif root_relation == "work-under-evidence":
        evidence_root = shared
        work_root = evidence_root / "candidate-work"
    else:
        work_root = shared
        evidence_root = work_root / "controller-evidence"
    lock = _pilot_lock(tmp_path, evidence_root)

    with pytest.raises(ValueError, match="disjoint"):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=work_root,
            evidence_root=evidence_root,
        )

    assert not evidence_root.exists()
    assert not work_root.exists()


@pytest.mark.parametrize("surface", ["argv", "environment"])
@pytest.mark.parametrize(
    "forbidden_kind",
    [
        "evidence-root",
        "attempt-path",
        "peer-workspace",
        "peer-runtime",
        "original-control-root",
        "logical-treatment-id",
        "randomization-seed",
        "peer-opaque-label",
    ],
)
def test_candidate_visible_controller_data_rejects_before_started(
    runner: ModuleType,
    tmp_path: Path,
    surface: str,
    forbidden_kind: str,
) -> None:
    work_root = (tmp_path / "work").resolve()
    evidence_root = (tmp_path / "evidence").resolve()
    lock = _pilot_lock(tmp_path, evidence_root)
    block_id = lock["smoke_id"]
    peer_label = runner_apparatus.opaque_label(
        lock["randomization_seed"],
        block_id,
        "COORDINATOR",
    )
    forbidden = {
        "evidence-root": str(evidence_root),
        "attempt-path": str(evidence_root / block_id / "block-attempt.json"),
        "peer-workspace": str(
            work_root / block_id / peer_label / "workspace"
        ),
        "peer-runtime": str(
            work_root / block_id / ".controller" / peer_label
        ),
        "original-control-root": lock["apparatus"]["control_root"],
        "logical-treatment-id": "COORDINATOR",
        "randomization-seed": lock["randomization_seed"],
        "peer-opaque-label": peer_label,
    }[forbidden_kind]

    if surface == "environment":
        lock["apparatus"]["environment"]["allowed_keys"].append(
            "VISIBILITY_PROBE"
        )

    def expose_controller_data(config: dict[str, Any]) -> None:
        if surface == "argv":
            config["argv"].append(f"--visibility-probe={forbidden}")
        else:
            config["environment"]["VISIBILITY_PROBE"] = (
                f"prefix:{forbidden}:suffix"
            )

    if surface == "argv":
        _rewrite_treatment_config(lock, "DIRECT", expose_controller_data)
    else:
        _rewrite_all_treatment_configs(lock, expose_controller_data)

    expected_message = (
        "control_root"
        if forbidden_kind == "original-control-root"
        else "candidate-visible"
    )
    with pytest.raises(ValueError, match=expected_message):
        runner.run_block(
            lock=lock,
            block_id=block_id,
            work_root=work_root,
            evidence_root=evidence_root,
        )

    assert not evidence_root.exists()
    assert not work_root.exists()


def test_candidate_visible_environment_key_cannot_name_a_treatment(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    work_root = tmp_path / "work"
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    lock["apparatus"]["environment"]["allowed_keys"].append("DIRECT_SECRET")

    def add_treatment_named_key(config: dict[str, Any]) -> None:
        config["environment"]["DIRECT_SECRET"] = "present"

    _rewrite_all_treatment_configs(lock, add_treatment_named_key)

    with pytest.raises(ValueError, match="candidate-visible"):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=work_root,
            evidence_root=evidence_root,
        )

    assert not evidence_root.exists()
    assert not work_root.exists()


def test_treatment_tokens_inside_larger_identifier_components_are_permitted(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    extra_environment = {
        "COORDINATORIAL_MODE": "coordinatorial",
        "DIRECTORY_MODE": "indirection",
        "ORCHESTRATOR_MODE": "orchestrator-runtime",
    }
    lock["apparatus"]["environment"]["allowed_keys"].extend(extra_environment)

    def add_extra_environment(config: dict[str, Any]) -> None:
        config["environment"].update(extra_environment)

    _rewrite_all_treatment_configs(lock, add_extra_environment)

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert record["status"] == "VALID"


def test_smoke_id_is_single_use(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    block_id = lock["smoke_id"]
    runner.run_block(
        lock=lock,
        block_id=block_id,
        work_root=tmp_path / "first-work",
        evidence_root=evidence_root,
    )
    before = _evidence_snapshot(evidence_root)
    reused_work_root = tmp_path / "reused-work"

    with pytest.raises(ValueError):
        runner.run_block(
            lock=lock,
            block_id=block_id,
            work_root=reused_work_root,
            evidence_root=evidence_root,
        )

    assert not reused_work_root.exists()
    assert _evidence_snapshot(evidence_root) == before


def test_live_attempt_ids_cannot_skip_the_locked_prefix(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    work_root = tmp_path / "work"
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)

    with pytest.raises(ValueError):
        runner.run_block(
            lock=lock,
            block_id="live-002",
            work_root=work_root,
            evidence_root=evidence_root,
        )

    assert not evidence_root.exists()
    assert not work_root.exists()


def test_started_live_attempt_is_not_reusable_but_advances_the_prefix(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    first = runner.run_block(
        lock=lock,
        block_id="live-001",
        work_root=tmp_path / "first-work",
        evidence_root=evidence_root,
    )
    started = dict(first.record)
    started["status"] = "STARTED"
    started["treatment_executions"] = []
    contracts.validate_record(started)
    _block_record_path(evidence_root, "live-001").write_bytes(
        contracts.canonical_json_bytes(started)
    )
    before_reuse = _evidence_snapshot(evidence_root)
    reused_work_root = tmp_path / "reused-work"

    with pytest.raises(ValueError):
        runner.run_block(
            lock=lock,
            block_id="live-001",
            work_root=reused_work_root,
            evidence_root=evidence_root,
        )

    assert not reused_work_root.exists()
    assert _evidence_snapshot(evidence_root) == before_reuse

    second = runner.run_block(
        lock=lock,
        block_id="live-002",
        work_root=tmp_path / "second-work",
        evidence_root=evidence_root,
    )
    assert second.record["status"] == "VALID"


def test_three_arms_release_together_with_closed_opaque_visibility(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret_name = "LEAN_PILOT_TEST_SECRET"
    secret_value = "fixture-secret-value-that-must-not-be-recorded"
    monkeypatch.setenv(secret_name, secret_value)
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    lock["apparatus"]["environment"]["allowed_keys"].append(secret_name)
    lock["apparatus"]["environment"]["credential_keys"] = [secret_name]

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    observations = _fixture_events(evidence_root, "started")
    assert len(observations) == 3
    starts = [item["started_monotonic_ns"] for item in observations]
    assert (max(starts) - min(starts)) / 1_000_000 <= (
        lock["apparatus"]["maximum_start_skew_milliseconds"]
    )

    workspaces = [Path(item["cwd"]) for item in observations]
    assert len(set(workspaces)) == 3
    assert len(
        {_execution(record, treatment)["product_manifest_digest"] for treatment in (
            "DIRECT",
            "COORDINATOR",
            "ORC",
        )}
    ) == 1
    assert len({item["source_sha256"] for item in observations}) == 1

    expected_environment = [
        {"name": name, "present": True}
        for name in sorted(lock["apparatus"]["environment"]["allowed_keys"])
    ]
    final_record = _block_record_path(evidence_root, lock["smoke_id"])
    result_paths = []
    for observation in observations:
        assert observation["environment_key_presence"] == expected_environment
        result_index = observation["argv"].index("--result-file") + 1
        result_paths.append(observation["argv"][result_index])
        visible = json.dumps(observation, sort_keys=True)
        assert str(evidence_root) not in visible
        assert str(final_record) not in visible
        assert all(
            treatment_id not in visible
            for treatment_id in ("DIRECT", "COORDINATOR", "ORC")
        )
        assert all(
            str(peer) not in visible
            for peer in workspaces
            if peer != Path(observation["cwd"])
        )
    assert len(set(result_paths)) == 3
    assert secret_value.encode() not in b"".join(
        path.read_bytes()
        for path in evidence_root.rglob("*")
        if path.is_file()
    )


def test_standard_externs_compile_from_staged_private_apparatus_only(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    work_root = tmp_path / "work"
    unrelated_cwd = tmp_path / "unrelated-cwd"
    unrelated_cwd.mkdir()
    lock = _pilot_lock(tmp_path, evidence_root)
    control_root = Path(lock["apparatus"]["control_root"])
    expected_assets = {
        entry["path"]: entry["sha256"]
        for entry in lock["apparatus"]["asset_manifest"]
    }
    real_atomic_record = runner_block._atomic_record
    removed_after_started = False

    def remove_original_after_started(
        path: Path,
        record: dict[str, Any],
    ) -> None:
        nonlocal removed_after_started
        real_atomic_record(path, record)
        if record["status"] == "STARTED" and not removed_after_started:
            shutil.rmtree(control_root)
            removed_after_started = True

    monkeypatch.chdir(unrelated_cwd)
    monkeypatch.setattr(
        runner_block,
        "_atomic_record",
        remove_original_after_started,
    )

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=work_root,
        evidence_root=evidence_root,
    ).record

    assert removed_after_started is True
    assert not control_root.exists()
    assert record["status"] == "VALID"
    observations = _fixture_events(evidence_root, "started")
    assert len(observations) == 3
    for observation in observations:
        visible = json.dumps(observation, sort_keys=True)
        assert control_root.as_posix() not in visible
        staged_root = Path(observation["apparatus_root"])
        assert staged_root.is_dir()
        staged_assets = {
            path.relative_to(staged_root).as_posix(): _sha256(path.read_bytes())
            for path in staged_root.rglob("*")
            if path.is_file()
        }
        assert staged_assets == expected_assets
        assert {
            role: details["path"]
            for role, details in observation["apparatus_assets"].items()
        } == {
            "task": lock["apparatus"]["task_path"],
            "provider_config": lock["apparatus"]["provider_config_path"],
            "prompt_config": lock["apparatus"]["prompt_config_path"],
            "command_config": lock["apparatus"]["command_config_path"],
        }

    staged_root = Path(observations[0]["apparatus_root"])
    compile_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator",
            "compile",
            str(staged_root / "fixture.orc"),
            "--source-root",
            str(staged_root),
            "--entry-workflow",
            "fixture::decide",
            "--provider-externs-file",
            str(staged_root / lock["apparatus"]["provider_config_path"]),
            "--prompt-externs-file",
            str(staged_root / lock["apparatus"]["prompt_config_path"]),
            "--command-boundaries-file",
            str(staged_root / lock["apparatus"]["command_config_path"]),
        ],
        cwd=unrelated_cwd,
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert compile_result.returncode == 0, compile_result.stderr


@pytest.mark.parametrize(
    ("treatment_id", "provider_call_count"),
    [("DIRECT", 2), ("COORDINATOR", 2), ("ORC", 10)],
)
def test_provider_call_bound_mismatch_is_a_protocol_outcome(
    runner: ModuleType,
    tmp_path: Path,
    treatment_id: str,
    provider_call_count: int,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    _configure_arm(
        lock,
        treatment_id,
        provider_call_count=provider_call_count,
    )

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert record["status"] == "VALID"
    assert _execution(record, treatment_id)["lifecycle_outcome"] == (
        "PROTOCOL_FAILURE"
    )
    assert all(
        _execution(record, peer)["lifecycle_outcome"] == "COMPLETED"
        for peer in {"DIRECT", "COORDINATOR", "ORC"} - {treatment_id}
    )


@pytest.mark.parametrize(
    "terminal_outcome",
    ["BLOCKED", "EXHAUSTED", "PROTOCOL_FAILURE"],
)
def test_valid_raw_result_semantic_terminal_is_preserved(
    runner: ModuleType,
    tmp_path: Path,
    terminal_outcome: str,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    _configure_arm(
        lock,
        "DIRECT",
        terminal_outcome=terminal_outcome,
    )

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert _execution(record, "DIRECT")["lifecycle_outcome"] == terminal_outcome


@pytest.mark.parametrize("fault", ["missing", "invalid"])
def test_raw_result_requires_valid_terminal_outcome(
    runner: ModuleType,
    tmp_path: Path,
    fault: str,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    if fault == "missing":
        _configure_arm(lock, "DIRECT", result_fault="missing-terminal")
    else:
        _configure_arm(
            lock,
            "DIRECT",
            terminal_outcome="NOT_A_TERMINAL",
        )

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert _execution(record, "DIRECT")["lifecycle_outcome"] == (
        "PROTOCOL_FAILURE"
    )


def test_transport_nonzero_precedes_raw_semantic_terminal(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    _configure_arm(
        lock,
        "DIRECT",
        mode="nonzero",
        terminal_outcome="BLOCKED",
    )

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert _execution(record, "DIRECT")["lifecycle_outcome"] == "NONZERO_EXIT"


@pytest.mark.parametrize("provider_call_count", [0, 2])
def test_provider_call_bounds_apply_to_noncompleted_terminal(
    runner: ModuleType,
    tmp_path: Path,
    provider_call_count: int,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    _configure_arm(
        lock,
        "DIRECT",
        provider_call_count=provider_call_count,
        terminal_outcome="BLOCKED",
    )

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert _execution(record, "DIRECT")["lifecycle_outcome"] == (
        "PROTOCOL_FAILURE"
    )


@pytest.mark.parametrize(
    ("treatment_id", "provider_call_count", "expected_outcome"),
    [
        ("COORDINATOR", 3, "BLOCKED"),
        ("ORC", 3, "BLOCKED"),
        ("COORDINATOR", 2, "PROTOCOL_FAILURE"),
        ("ORC", 2, "PROTOCOL_FAILURE"),
    ],
)
def test_multi_provider_bounds_apply_to_blocked_terminal(
    runner: ModuleType,
    tmp_path: Path,
    treatment_id: str,
    provider_call_count: int,
    expected_outcome: str,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    for treatment in lock["treatments"]:
        if treatment["treatment_id"] != "DIRECT":
            treatment["provider_call_bounds"]["minimum"] = 3
    _configure_arm(
        lock,
        treatment_id,
        provider_call_count=provider_call_count,
        terminal_outcome="BLOCKED",
    )

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert _execution(record, treatment_id)["lifecycle_outcome"] == (
        expected_outcome
    )


@pytest.mark.parametrize(
    ("fault", "expected_outcome"),
    [
        ("nonzero", "NONZERO_EXIT"),
        ("prelaunch-fail", "NONZERO_EXIT"),
        ("launch", "LAUNCH_FAILURE"),
    ],
)
def test_arm_process_fault_is_an_outcome_and_peers_finish(
    runner: ModuleType,
    tmp_path: Path,
    fault: str,
    expected_outcome: str,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    if fault in {"nonzero", "prelaunch-fail"}:
        _configure_arm(lock, "DIRECT", mode=fault)
    else:
        _configure_arm(
            lock,
            "DIRECT",
            executable="/nonexistent/lean-pilot-arm",
        )

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert record["status"] == "VALID"
    direct = _execution(record, "DIRECT")
    assert direct["lifecycle_outcome"] == expected_outcome
    if fault == "prelaunch-fail":
        stderr_reference = next(
            item
            for item in direct["evidence_references"]
            if item.endswith("/stderr.txt")
        )
        assert (evidence_root / stderr_reference).read_bytes() == b""
    assert _execution(record, "COORDINATOR")["lifecycle_outcome"] == "COMPLETED"
    assert _execution(record, "ORC")["lifecycle_outcome"] == "COMPLETED"


@pytest.mark.parametrize(
    ("mode", "expected_outcome"),
    [("timeout", "TIMEOUT"), ("spawn-child", "COMPLETED")],
)
def test_arm_process_group_is_quiescent_before_product_freeze(
    runner: ModuleType,
    tmp_path: Path,
    mode: str,
    expected_outcome: str,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    _configure_arm(
        lock,
        "DIRECT",
        mode=mode,
        timeout_milliseconds=100 if mode == "timeout" else 10_000,
        wait_seconds=30,
    )

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    direct = _execution(record, "DIRECT")
    direct_event = next(
        item
        for item in _fixture_events(evidence_root, "started")
        if "--provider-call-count" in item["argv"]
        and item["argv"][item["argv"].index("--provider-call-count") + 1] == "1"
    )
    with pytest.raises(ProcessLookupError):
        os.killpg(direct_event["process_group_id"], 0)
    assert direct["lifecycle_outcome"] == expected_outcome
    assert direct["product_frozen"] is True


def test_process_group_quiescence_fails_when_disappearance_cannot_be_proven(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    monkeypatch.setattr(
        runner_execution,
        "_process_group_exists",
        lambda process_group_id: process_group_id == process.pid,
    )

    try:
        assert runner_execution._terminate_process_group(process.pid, 10) is False
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)

    assert process.poll() is not None


def test_process_reap_timeout_is_not_ignored(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    real_wait = process.wait

    def clean_process_group(
        process_group_id: int,
        _grace_milliseconds: int,
    ) -> None:
        os.killpg(process_group_id, signal.SIGKILL)
        real_wait(timeout=5)

    def unprovable_wait(*, timeout: int) -> int:
        raise subprocess.TimeoutExpired(process.args, timeout)

    monkeypatch.setattr(
        runner_execution,
        "_terminate_process_group",
        clean_process_group,
    )
    monkeypatch.setattr(process, "wait", unprovable_wait)

    with pytest.raises(runner.RunnerError, match="reap"):
        runner_execution._quiesce_process(process, 10)

    assert process.poll() is not None


@pytest.mark.parametrize("cleanup_reported", [False, True])
@pytest.mark.parametrize("stage", ["provider", "check"])
def test_unproven_quiescence_preserves_started_before_product_freeze(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stage: str,
    cleanup_reported: bool,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    real_quiesce = runner_execution._quiesce_process
    real_freeze = workspace.freeze_product
    product_freezes: list[Path] = []

    def fail_selected_stage(
        process: subprocess.Popen[bytes],
        grace_milliseconds: int,
    ) -> None:
        real_quiesce(process, grace_milliseconds)
        is_provider = any(
            str(argument).endswith("/fixture/arm_program.py")
            for argument in process.args
        )
        if (stage == "provider" and is_provider) or (
            stage == "check" and not is_provider
        ):
            raise runner_types.QuiescenceError(
                f"{stage} process group remains visible"
            )

    def observe_freeze(
        root: Path,
        exclusions: tuple[PurePosixPath, ...],
    ) -> workspace.TreeManifest:
        if exclusions:
            product_freezes.append(root)
        return real_freeze(root, exclusions)

    monkeypatch.setattr(
        runner_execution,
        "_quiesce_process",
        fail_selected_stage,
    )
    monkeypatch.setattr(
        runner_execution,
        "_terminate_process_group",
        lambda _process_group_id, _grace_milliseconds: cleanup_reported,
    )
    monkeypatch.setattr(workspace, "freeze_product", observe_freeze)

    with pytest.raises(runner.RunnerError, match="process group"):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=tmp_path / "work",
            evidence_root=evidence_root,
        )

    persisted = contracts.load_record(
        _block_record_path(evidence_root, lock["smoke_id"]),
        expected_kind="block_attempt.v1",
    )
    assert persisted["status"] == "STARTED"
    assert persisted["treatment_executions"] == []
    assert product_freezes == []
    for event in _fixture_events(evidence_root, "started"):
        with pytest.raises(ProcessLookupError):
            os.killpg(event["process_group_id"], 0)


def test_locked_visible_check_failure_is_an_outcome_and_runtime_is_excluded(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    lock["apparatus"]["visible_check"]["argv"] = [
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            "p=Path('.pilot/runtime/check-ran'); "
            "p.parent.mkdir(parents=True, exist_ok=True); "
            "p.write_text('yes'); "
            "raise SystemExit(9)"
        ),
    ]
    contracts.validate_record(lock)

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert record["status"] == "VALID"
    assert all(
        execution["lifecycle_outcome"] == "CHECK_FAILURE"
        and execution["product_frozen"] is True
        for execution in record["treatment_executions"]
    )
    observations = _fixture_events(evidence_root, "started")
    runtime_values = {
        (Path(item["cwd"]) / ".pilot/runtime/volatile.txt").read_text(
            encoding="utf-8"
        )
        for item in observations
    }
    assert len(runtime_values) == 3
    assert all(
        (Path(item["cwd"]) / ".pilot/runtime/check-ran").read_text(
            encoding="utf-8"
        )
        == "yes"
        for item in observations
    )
    assert len(
        {
            execution["product_manifest_digest"]
            for execution in record["treatment_executions"]
        }
    ) == 1


def test_visible_check_failure_only_overrides_completed_semantic_terminal(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    _configure_arm(lock, "DIRECT", terminal_outcome="BLOCKED")
    lock["apparatus"]["visible_check"]["argv"] = [
        sys.executable,
        "-c",
        "raise SystemExit(9)",
    ]

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert _execution(record, "DIRECT")["lifecycle_outcome"] == "BLOCKED"
    assert _execution(record, "COORDINATOR")["lifecycle_outcome"] == (
        "CHECK_FAILURE"
    )
    assert _execution(record, "ORC")["lifecycle_outcome"] == "CHECK_FAILURE"


def test_unused_manifest_asset_is_still_verified_before_started(
    runner: ModuleType,
    tmp_path: Path,
) -> None:
    work_root = tmp_path / "work"
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    control_root = Path(lock["apparatus"]["control_root"])
    unused = _write_asset(
        control_root,
        "config/unused.json",
        {"purpose": "manifest coverage"},
    )
    lock["apparatus"]["asset_manifest"].append(unused)
    contracts.validate_record(lock)
    (control_root / unused["path"]).write_bytes(b"tampered")

    with pytest.raises(ValueError):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=work_root,
            evidence_root=evidence_root,
        )

    assert not evidence_root.exists()
    assert not work_root.exists()


@pytest.mark.parametrize(
    "result_fault",
    ["unknown", "duplicate", "missing", "wrong-type"],
)
def test_invalid_raw_result_is_strict_protocol_evidence(
    runner: ModuleType,
    tmp_path: Path,
    result_fault: str,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    _configure_arm(
        lock,
        "DIRECT",
        result_fault=result_fault,
    )

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    contracts.validate_record(record)
    assert record["status"] == "VALID"
    direct = _execution(record, "DIRECT")
    assert direct["lifecycle_outcome"] == "PROTOCOL_FAILURE"
    assert direct["provider_call_count"] == 0
    assert "unexpected" not in direct
    assert _execution(record, "COORDINATOR")["lifecycle_outcome"] == "COMPLETED"
    assert _execution(record, "ORC")["lifecycle_outcome"] == "COMPLETED"


@pytest.mark.parametrize("shared_fault", ["archive", "allocation"])
def test_shared_materialization_failure_atomically_invalidates_the_block(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shared_fault: str,
) -> None:
    evidence_root = tmp_path / "evidence"
    work_root = tmp_path / "work"
    lock = _pilot_lock(tmp_path, evidence_root)
    if shared_fault == "archive":
        shutil.rmtree(lock["archive"]["repository_identity"])
    else:
        work_root.write_text("not a directory", encoding="utf-8")
    observed = _observe_atomic_records(monkeypatch)

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=work_root,
        evidence_root=evidence_root,
    ).record

    assert [item["status"] for item in observed] == ["STARTED", "INVALID"]
    assert record["status"] == "INVALID"
    assert record.get("treatment_executions", []) == []
    assert _fixture_events(evidence_root, "started") == []
    contracts.validate_record(record)


def test_broken_launch_barrier_is_a_shared_invalidity(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    real_barrier = threading.Barrier
    observed = _observe_atomic_records(monkeypatch)

    def broken_barrier(parties: int) -> threading.Barrier:
        barrier = real_barrier(parties)
        barrier.abort()
        return barrier

    monkeypatch.setattr(runner_block.threading, "Barrier", broken_barrier)

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert [item["status"] for item in observed] == ["STARTED", "INVALID"]
    assert record["status"] == "INVALID"
    assert record["reason_code"] == "SHARED_LAUNCH_BARRIER_FAILED"
    assert record["treatment_executions"] == []
    assert _fixture_events(evidence_root, "started") == []
    contracts.validate_record(record)


def test_excessive_start_skew_is_a_shared_invalidity(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    real_run_arm = runner_execution._run_arm
    observed = _observe_atomic_records(monkeypatch)
    forced_launch_times = {
        "DIRECT": 0,
        "COORDINATOR": (
            lock["apparatus"]["maximum_start_skew_milliseconds"] + 1
        )
        * 1_000_000,
        "ORC": (
            lock["apparatus"]["maximum_start_skew_milliseconds"] + 1
        )
        * 1_000_000,
    }

    def run_with_forced_skew(**kwargs: Any) -> Any:
        execution = real_run_arm(**kwargs)
        arm = kwargs["arm"]
        with kwargs["launch_lock"]:
            kwargs["launch_times"][arm.command.opaque_arm_label] = (
                forced_launch_times[arm.command.treatment_id]
            )
        return execution

    monkeypatch.setattr(runner_execution, "_run_arm", run_with_forced_skew)

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert [item["status"] for item in observed] == ["STARTED", "INVALID"]
    assert record["status"] == "INVALID"
    assert record["reason_code"] == "SHARED_START_SKEW_EXCEEDED"
    assert record["treatment_executions"] == []
    contracts.validate_record(record)


def test_controller_exception_after_started_atomically_aborts(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    real_freeze = workspace.freeze_product
    freeze_calls = 0

    def fail_freeze(*args: object, **kwargs: object) -> object:
        nonlocal freeze_calls
        freeze_calls += 1
        if freeze_calls <= 3:
            return real_freeze(*args, **kwargs)
        raise RuntimeError("injected controller failure")

    monkeypatch.setattr(workspace, "freeze_product", fail_freeze)
    observed = _observe_atomic_records(monkeypatch)

    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    assert [item["status"] for item in observed] == ["STARTED", "ABORTED"]
    assert record["status"] == "ABORTED"
    contracts.validate_record(record)


def test_base_exception_preserves_complete_started_record(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class InjectedStop(BaseException):
        pass

    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)

    def stop_materialization(*_args: object, **_kwargs: object) -> object:
        raise InjectedStop

    monkeypatch.setattr(
        workspace,
        "materialize_git_archive",
        stop_materialization,
    )
    observed = _observe_atomic_records(monkeypatch)

    with pytest.raises(InjectedStop):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=tmp_path / "work",
            evidence_root=evidence_root,
        )

    assert [item["status"] for item in observed] == ["STARTED"]
    persisted = contracts.load_record(
        _block_record_path(evidence_root, lock["smoke_id"]),
        expected_kind="block_attempt.v1",
    )
    assert persisted["status"] == "STARTED"
    assert persisted.get("treatment_executions", []) == []


def test_worker_interruption_before_barrier_preserves_started_and_releases_peers(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class InjectedStop(BaseException):
        pass

    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    real_barrier = threading.Barrier
    real_write_evidence = runner_execution._write_evidence
    interrupted = False

    def bounded_barrier(parties: int) -> threading.Barrier:
        return real_barrier(parties, timeout=1)

    def interrupt_one_worker(path: Path, value: bytes | object) -> None:
        nonlocal interrupted
        if not interrupted and path.name == "environment.json":
            interrupted = True
            raise InjectedStop
        real_write_evidence(path, value)

    monkeypatch.setattr(runner_block.threading, "Barrier", bounded_barrier)
    monkeypatch.setattr(
        runner_execution,
        "_write_evidence",
        interrupt_one_worker,
    )

    with pytest.raises(InjectedStop):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=tmp_path / "work",
            evidence_root=evidence_root,
        )

    persisted = contracts.load_record(
        _block_record_path(evidence_root, lock["smoke_id"]),
        expected_kind="block_attempt.v1",
    )
    assert persisted["status"] == "STARTED"
    assert persisted.get("treatment_executions", []) == []


def test_atomic_installs_are_always_complete_valid_records(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    observed = _observe_atomic_records(monkeypatch)

    runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    )

    assert [item["status"] for item in observed] == ["STARTED", "VALID"]


def test_evidence_is_external_relative_and_freeze_uses_locked_exclusions(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    lock = _pilot_lock(tmp_path, evidence_root)
    expected_exclusions = tuple(
        PurePosixPath(path)
        for path in lock["apparatus"]["product_projection_exclusions"]
    )
    observed_exclusions: list[tuple[PurePosixPath, ...]] = []
    real_freeze = workspace.freeze_product
    freeze_calls = 0

    def observe_freeze(
        root: Path,
        excluded_roots: tuple[PurePosixPath, ...],
    ) -> object:
        nonlocal freeze_calls
        freeze_calls += 1
        if freeze_calls > 3:
            observed_exclusions.append(tuple(excluded_roots))
        return real_freeze(root, excluded_roots)

    monkeypatch.setattr(workspace, "freeze_product", observe_freeze)
    record = runner.run_block(
        lock=lock,
        block_id=lock["smoke_id"],
        work_root=tmp_path / "work",
        evidence_root=evidence_root,
    ).record

    workspaces = [
        Path(item["cwd"]).resolve()
        for item in _fixture_events(evidence_root, "started")
    ]
    assert observed_exclusions == [expected_exclusions] * 3
    for execution in record["treatment_executions"]:
        for reference in execution["evidence_references"]:
            relative = PurePosixPath(reference)
            assert not relative.is_absolute()
            assert ".." not in relative.parts
            evidence_path = evidence_root.joinpath(*relative.parts).resolve()
            assert evidence_path.is_file()
            assert all(
                not evidence_path.is_relative_to(candidate)
                for candidate in workspaces
            )


@pytest.mark.parametrize(
    "mismatch",
    ["implicit-repository", "raw-revision", "evidence-root"],
)
def test_source_and_evidence_identity_mismatch_rejects_before_allocation(
    runner: ModuleType,
    tmp_path: Path,
    mismatch: str,
) -> None:
    locked_evidence_root = tmp_path / "locked-evidence"
    supplied_evidence_root = locked_evidence_root
    work_root = tmp_path / "work"
    lock = _pilot_lock(tmp_path, locked_evidence_root)
    if mismatch == "implicit-repository":
        lock["archive"]["repository_identity"] = "."
    elif mismatch == "raw-revision":
        lock["archive"]["revision_identity"] = lock["archive"][
            "revision_identity"
        ].removeprefix("commit:")
    else:
        supplied_evidence_root = tmp_path / "different-evidence"
    contracts.validate_record(lock)

    with pytest.raises(ValueError):
        runner.run_block(
            lock=lock,
            block_id=lock["smoke_id"],
            work_root=work_root,
            evidence_root=supplied_evidence_root,
        )

    assert not work_root.exists()
    assert not locked_evidence_root.exists()
    assert not supplied_evidence_root.exists()


def _runner_source_paths(runner: ModuleType) -> tuple[Path, ...]:
    package = Path(runner.__file__).parent
    return (
        Path(runner.__file__),
        *tuple(sorted(package.glob("_runner_*.py"))),
    )


def test_runner_is_a_bounded_public_facade_over_private_modules(
    runner: ModuleType,
) -> None:
    expected_private_modules = {
        "_runner_apparatus.py",
        "_runner_block.py",
        "_runner_execution.py",
        "_runner_preflight.py",
        "_runner_types.py",
    }
    source_paths = _runner_source_paths(runner)

    assert {path.name for path in source_paths[1:]} == expected_private_modules
    assert len(source_paths[0].read_text(encoding="utf-8").splitlines()) <= 50
    assert all(
        len(path.read_text(encoding="utf-8").splitlines()) <= 475
        for path in source_paths[1:]
    )
    assert runner.__all__ == [
        "ArmCommand",
        "ArmExecution",
        "BlockAttempt",
        "RunnerError",
        "run_block",
    ]


def test_runner_modules_have_no_provider_isolation_import_or_shell_invocation(
    runner: ModuleType,
) -> None:
    for source_path in _runner_source_paths(runner):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.append(node.module or "")
        assert all(
            "provider_isolation" not in module
            and not module.startswith("orchestrator.providers.isolation")
            for module in imported_modules
        )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "system"
            ):
                pytest.fail(f"{source_path.name} must not invoke os.system")
            for keyword in node.keywords:
                if keyword.arg == "shell":
                    assert isinstance(keyword.value, ast.Constant)
                    assert keyword.value.value is False
