from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys

import pytest

from orchestrator.exec.step_executor import StepExecutor
from tests.test_workflow_evaluated_commands import (
    _Owners,
    _checked_command,
    _command_api,
    _perform,
    owners,
)


def test_relative_pythonpath_shadow_parent_cannot_override_package_origin(
    owners: _Owners,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _command_api()
    module = "orchestrator.workflow.evaluated.values"
    node = _checked_command(
        owners.workspace_files.workspace,
        return_type="Int",
        stable_command=("python", "-m", module),
        closure=("workflow/evaluated/values.py",),
        origin="package:orchestrator",
    )
    workspace = owners.workspace_files.workspace
    shadow_package = workspace / "shadow" / "orchestrator"
    shadow_package.mkdir(parents=True)
    (shadow_package / "__init__.py").write_text("", encoding="utf-8")
    package_parent = Path(importlib.import_module("orchestrator").__file__).resolve().parent.parent
    (shadow_package / "workflow").symlink_to(
        package_parent / "orchestrator/workflow", target_is_directory=True
    )
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(("shadow", package_parent.as_posix())))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")

    with pytest.raises(api.CommandPerformerError) as excinfo:
        _perform(api, owners, node, [sys.executable, "-m", module])

    assert excinfo.value.code == "command_module_origin_mismatch"
    assert not owners.attempt_files.exists("stdout.txt")


@pytest.mark.parametrize(
    ("origin", "package_alias"),
    [("workspace", False), ("package:orchestrator", True)],
)
def test_package_guard_scope_accepts_symlink_alias_of_checked_installation(
    owners: _Owners,
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
    package_alias: bool,
) -> None:
    module = "orchestrator.workflow.evaluated.values"
    node = _checked_command(
        owners.workspace_files.workspace,
        return_type="Int",
        stable_command=("python", "-m", module),
        closure=(".",) if package_alias else (),
        origin=origin,
    )
    package_parent = Path(importlib.import_module("orchestrator").__file__).resolve().parent.parent
    paths = [package_parent.as_posix()]
    if package_alias:
        (owners.workspace_files.workspace / "package-alias").symlink_to(
            package_parent, target_is_directory=True
        )
        paths.insert(0, "package-alias")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(paths))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    reached: list[list[str]] = []

    class ReachedCommandDispatch(Exception):
        pass

    def dispatch(_executor, _step_name, command, **_kwargs):
        reached.append(list(command))
        raise ReachedCommandDispatch

    monkeypatch.setattr(StepExecutor, "execute_command", dispatch)

    with pytest.raises(ReachedCommandDispatch):
        _perform(_command_api(), owners, node, [sys.executable, "-m", module])

    assert reached == [[sys.executable, "-m", module]]
