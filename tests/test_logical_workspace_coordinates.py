from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from orchestrator.exec.step_executor import StepExecutor
from orchestrator.providers import (
    InputMode,
    ProviderExecutor,
    ProviderInvocation,
    ProviderRegistry,
)
from orchestrator.workflow.run_ref.runtime import (
    RunRefChildLaunch,
    RunRefRuntimeDependencies,
)
from orchestrator.workflow_lisp.adapters.reusable_phase_state_common import (
    emit_structured_result,
    logical_workspace_root,
)
from orchestrator.workflow_lisp.adapters.validate_review_findings_v1 import (
    main as validate_findings,
)


_ENV_PROBE = (
    "import os; print(os.environ.get('ORCHESTRATOR_WORKSPACE_ROOT', '<missing>'))"
)


def test_step_command_clears_untrusted_root_and_accepts_explicit_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = (tmp_path / "logical").resolve()
    root.mkdir()
    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", "/ambient/poison")
    executor = StepExecutor(tmp_path)

    cleared = executor.execute_command(
        "probe",
        [sys.executable, "-c", _ENV_PROBE],
        env={"ORCHESTRATOR_WORKSPACE_ROOT": "/authored/poison"},
    )
    empty = executor.execute_command(
        "probe",
        [sys.executable, "-c", _ENV_PROBE],
        env={"ORCHESTRATOR_WORKSPACE_ROOT": ""},
    )
    selected = executor.execute_command(
        "probe",
        [sys.executable, "-c", _ENV_PROBE],
        env={"ORCHESTRATOR_WORKSPACE_ROOT": "/authored/poison"},
        logical_workspace_root=root,
    )

    assert cleared.exit_code == 0
    assert cleared.capture_result.output.strip() == "<missing>"
    assert empty.exit_code == 0
    assert empty.capture_result.output.strip() == "<missing>"
    assert selected.exit_code == 0
    assert selected.capture_result.output.strip() == root.as_posix()


def test_provider_clears_untrusted_root_and_accepts_explicit_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = (tmp_path / "logical").resolve()
    root.mkdir()
    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", "/ambient/poison")
    executor = ProviderExecutor(tmp_path, ProviderRegistry())
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", _ENV_PROBE],
        input_mode=InputMode.ARGV,
        env={"ORCHESTRATOR_WORKSPACE_ROOT": "/authored/poison"},
    )

    cleared = executor.execute(
        invocation,
        execution_env_overlay={"ORCHESTRATOR_WORKSPACE_ROOT": "/overlay/poison"},
    )
    empty = executor.execute(
        invocation,
        execution_env_overlay={"ORCHESTRATOR_WORKSPACE_ROOT": ""},
    )
    selected = executor.execute(
        invocation,
        execution_env_overlay={"ORCHESTRATOR_WORKSPACE_ROOT": "/overlay/poison"},
        logical_workspace_root=root,
    )

    assert cleared.exit_code == 0
    assert cleared.stdout.decode().strip() == "<missing>"
    assert empty.exit_code == 0
    assert empty.stdout.decode().strip() == "<missing>"
    assert selected.exit_code == 0
    assert selected.stdout.decode().strip() == root.as_posix()


@pytest.mark.parametrize("executor_kind", ("command", "provider"))
def test_launchers_refuse_invalid_explicit_logical_roots(
    tmp_path: Path,
    executor_kind: str,
) -> None:
    if executor_kind == "command":
        def execute(root: Path) -> object:
            return StepExecutor(tmp_path).execute_command(
                "probe", [sys.executable, "-c", "pass"],
                logical_workspace_root=root,
            )
    else:
        provider = ProviderExecutor(tmp_path, ProviderRegistry())
        invocation = ProviderInvocation(
            command=[sys.executable, "-c", "pass"], input_mode=InputMode.ARGV
        )

        def execute(root: Path) -> object:
            return provider.execute(invocation, logical_workspace_root=root)

    with pytest.raises(ValueError, match="logical_workspace_root"):
        execute(Path("relative/root"))

    file_root = tmp_path / "file-root"
    file_root.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError, match="logical_workspace_root"):
        execute(file_root.resolve())


def test_child_launcher_clears_inherited_logical_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    request_path = tmp_path / "request.json"
    request_path.write_text("{}\n", encoding="utf-8")
    observed: dict[str, object] = {}

    def fake_run(_argv, **kwargs):
        observed.update(kwargs)
        return type("Completed", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", "/ambient/poison")
    monkeypatch.setattr(
        "orchestrator.workflow.run_ref.runtime.subprocess.run", fake_run
    )
    RunRefRuntimeDependencies().launch_child(
        RunRefChildLaunch(
            mode="bundle",
            request_path=request_path,
            request_document={},
            workspace=workspace,
            child_run_id="child",
        )
    )

    assert "ORCHESTRATOR_WORKSPACE_ROOT" not in observed["env"]


def test_adapter_uses_logical_root_for_relative_carriers_and_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = (tmp_path / "logical").resolve()
    other_cwd = (tmp_path / "attempt").resolve()
    (root / "artifacts" / "work").mkdir(parents=True)
    other_cwd.mkdir()
    (root / "artifacts" / "work" / "findings.json").write_text(
        json.dumps({"items": []}), encoding="utf-8"
    )
    carrier = {
        "schema_version": "ReviewFindings.v1",
        "items_path": "artifacts/work/findings.json",
    }
    (root / "carrier.json").write_text(json.dumps(carrier), encoding="utf-8")
    result_path = other_cwd / "result.json"
    monkeypatch.chdir(other_cwd)
    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", root.as_posix())
    monkeypatch.setenv("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", result_path.as_posix())

    assert logical_workspace_root() == root
    assert validate_findings(["validate", "carrier.json"]) == 0
    capsys.readouterr()
    assert json.loads(result_path.read_text(encoding="utf-8")) == carrier


def test_adapter_keeps_inline_json_and_absolute_carrier_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = (tmp_path / "logical").resolve()
    other_cwd = (tmp_path / "attempt").resolve()
    outside = (tmp_path / "outside").resolve()
    for directory in (root / "artifacts" / "work", other_cwd, outside):
        directory.mkdir(parents=True, exist_ok=True)
    findings_path = root / "artifacts" / "work" / "findings.json"
    findings_path.write_text('{"items": []}', encoding="utf-8")
    carrier = {
        "schema_version": "ReviewFindings.v1",
        "items_path": "artifacts/work/findings.json",
    }
    carrier_path = outside / "carrier.json"
    carrier_path.write_text(json.dumps(carrier), encoding="utf-8")
    monkeypatch.chdir(other_cwd)
    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", root.as_posix())

    for index, argument in enumerate((json.dumps(carrier), carrier_path.as_posix())):
        result_path = other_cwd / f"result-{index}.json"
        monkeypatch.setenv("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", result_path.as_posix())
        assert validate_findings(["validate", argument]) == 0
        capsys.readouterr()
        assert json.loads(result_path.read_text(encoding="utf-8")) == carrier


def test_inactive_json_looking_relative_carrier_is_loaded_as_a_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifacts = tmp_path / "artifacts" / "work"
    artifacts.mkdir(parents=True)
    for filename in ("inline.json", "loaded.json"):
        (artifacts / filename).write_text('{"items": []}', encoding="utf-8")
    argument = (
        '{"schema_version":"ReviewFindings.v1",'
        '"items_path":"artifacts\\u002fwork\\u002finline.json"}'
    )
    carrier_path = tmp_path / argument
    carrier_path.write_text(
        json.dumps(
            {
                "schema_version": "ReviewFindings.v1",
                "items_path": "artifacts/work/loaded.json",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ORCHESTRATOR_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "state/result.json")

    assert validate_findings(["validate", argument]) == 0
    capsys.readouterr()
    assert json.loads((tmp_path / "state" / "result.json").read_text()) == {
        "schema_version": "ReviewFindings.v1",
        "items_path": "artifacts/work/loaded.json",
    }


def test_active_adapter_requires_absolute_normalized_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path.resolve()
    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", root.as_posix())

    whitespace_path = root / "result.json "
    monkeypatch.setenv("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", whitespace_path.as_posix())
    assert emit_structured_result({"ok": True}) == 0
    assert json.loads(whitespace_path.read_text()) == {"ok": True}

    for output_path in (
        "artifacts/result.json",
        (root / "nested" / ".." / "result.json").as_posix(),
    ):
        monkeypatch.setenv("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", output_path)
        with pytest.raises(ValueError, match="resume_state_path_unsafe"):
            emit_structured_result({"ok": True})


def test_logical_root_and_review_artifact_paths_reject_invalid_or_escaping_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", "relative/root")
    with pytest.raises(ValueError, match="logical_workspace_root_invalid"):
        logical_workspace_root()
    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", " ")
    with pytest.raises(ValueError, match="logical_workspace_root_invalid"):
        logical_workspace_root()

    file_root = tmp_path / "file-root"
    file_root.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", file_root.as_posix())
    with pytest.raises(ValueError, match="logical_workspace_root_invalid"):
        logical_workspace_root()

    root = (tmp_path / "logical").resolve()
    other_cwd = (tmp_path / "attempt").resolve()
    root.mkdir()
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", root.as_posix())
    monkeypatch.setenv(
        "ORCHESTRATOR_OUTPUT_BUNDLE_PATH", (other_cwd / "result.json").as_posix()
    )
    unsafe = {
        "schema_version": "ReviewFindings.v1",
        "items_path": "artifacts/work/../../outside.json",
    }

    assert validate_findings(["validate", json.dumps(unsafe)]) == 1
    error = json.loads(capsys.readouterr().out)["error"]["type"]
    assert error == "review_findings_path_unsafe"


def test_review_items_path_rejects_symlink_escape_from_logical_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = (tmp_path / "logical").resolve()
    other_cwd = (tmp_path / "attempt").resolve()
    outside = (tmp_path / "outside").resolve()
    artifacts = root / "artifacts" / "work"
    artifacts.mkdir(parents=True)
    outside.mkdir()
    other_cwd.mkdir()
    (outside / "findings.json").write_text('{"items": []}', encoding="utf-8")
    (artifacts / "escape").symlink_to(outside, target_is_directory=True)
    payload = {
        "schema_version": "ReviewFindings.v1",
        "items_path": "artifacts/work/escape/findings.json",
    }
    monkeypatch.chdir(other_cwd)
    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", root.as_posix())
    monkeypatch.setenv(
        "ORCHESTRATOR_OUTPUT_BUNDLE_PATH", (other_cwd / "result.json").as_posix()
    )

    assert validate_findings(["validate", json.dumps(payload)]) == 1
    error = json.loads(capsys.readouterr().out)["error"]["type"]
    assert error == "review_findings_path_unsafe"


def test_inactive_adapter_keeps_workspace_relative_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ORCHESTRATOR_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "state/result.json ")

    assert emit_structured_result({"ok": True}) == 0
    assert json.loads((tmp_path / "state" / "result.json").read_text()) == {"ok": True}


def test_inactive_review_result_keeps_relative_path_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "artifacts" / "work" / "findings.json").write_text(
        '{"items": []}', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ORCHESTRATOR_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "state/result.json")

    payload = {
        "schema_version": "ReviewFindings.v1",
        "items_path": "artifacts/work/./findings.json",
    }
    assert validate_findings(["validate", json.dumps(payload)]) == 0
    capsys.readouterr()
    assert json.loads((tmp_path / "state" / "result.json").read_text()) == {
        "schema_version": "ReviewFindings.v1",
        "items_path": "artifacts/work/findings.json",
    }
