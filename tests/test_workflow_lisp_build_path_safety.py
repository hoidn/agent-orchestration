from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from orchestrator.workflow_lisp import syntax


REPO_ROOT = Path(__file__).resolve().parent.parent
TARGETS = ("2.34", syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION)
BUILD_COMPONENTS = ("orchestrate", "build", "build_key")


def _write_workspace(root: Path, target: str) -> tuple[Path, Path]:
    source_root = root / "src"
    source_root.mkdir(parents=True)
    source = source_root / "probe.orc"
    source.write_text(
        f'(workflow-lisp (:language "0.1") (:target-dsl "{target}") '
        '(defmodule probe) (export run) (defworkflow run () -> Int 1))\n',
        encoding="utf-8",
    )
    return source, source_root


def _compile(
    workspace: Path,
    source: Path,
    source_root: Path,
    *,
    diagnostics_json: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(REPO_ROOT),
    }
    argv = [
        sys.executable,
        "-m",
        "orchestrator",
        "compile",
        str(source),
        "--source-root",
        str(source_root),
        "--entry-workflow",
        "probe::run",
    ]
    if diagnostics_json:
        argv.append("--diagnostics-json")
    return subprocess.run(
        argv,
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _build_key(workspace: Path, source: Path, source_root: Path) -> str:
    completed = _compile(workspace, source, source_root)
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    return summary["build_key"] if "build_key" in summary else summary["fingerprint"]


def _link_build_component(
    workspace: Path,
    component: str,
    destination: Path,
    build_key: str | None,
) -> None:
    orchestrate = workspace / ".orchestrate"
    if component == "orchestrate":
        link = orchestrate
    elif component == "build":
        orchestrate.mkdir()
        link = orchestrate / "build"
    else:
        assert build_key is not None
        (orchestrate / "build").mkdir(parents=True)
        link = orchestrate / "build" / build_key
    link.symlink_to(destination, target_is_directory=True)


def _assert_path_error(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == 2
    diagnostic = json.loads(completed.stdout)["diagnostics"][0]
    assert diagnostic["code"] == "workflow_lisp_build_path_escapes_workspace"


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("component", BUILD_COMPONENTS)
@pytest.mark.parametrize("dangling", (False, True))
def test_compile_rejects_build_root_symlinks_that_resolve_outside_workspace(
    tmp_path: Path, target: str, component: str, dangling: bool
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source, source_root = _write_workspace(workspace, target)
    key = (
        _build_key(workspace, source, source_root)
        if component == "build_key"
        else None
    )
    shutil.rmtree(workspace / ".orchestrate", ignore_errors=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    destination = outside / "dangling-target" if dangling else outside

    _link_build_component(workspace, component, destination, key)
    completed = _compile(workspace, source, source_root, diagnostics_json=True)

    _assert_path_error(completed)
    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert sorted(path.name for path in outside.iterdir()) == ["sentinel.txt"]
    if dangling:
        assert not destination.exists()


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("component", BUILD_COMPONENTS)
def test_compile_allows_build_root_symlinks_that_resolve_inside_workspace(
    tmp_path: Path, target: str, component: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source, source_root = _write_workspace(workspace, target)
    key = (
        _build_key(workspace, source, source_root)
        if component == "build_key"
        else None
    )
    shutil.rmtree(workspace / ".orchestrate", ignore_errors=True)
    destination = workspace / "managed-build-root"
    destination.mkdir()
    _link_build_component(workspace, component, destination, key)

    completed = _compile(workspace, source, source_root)

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert Path(summary["build_root"]).resolve().is_relative_to(workspace.resolve())
    assert all(
        Path(path).resolve().is_relative_to(workspace.resolve())
        for path in summary["artifact_paths"].values()
    )
    assert list(destination.rglob("*.json"))


@pytest.mark.parametrize("artifact", ("frontend_ast.json", "manifest.json"))
def test_legacy_compile_rejects_artifact_file_symlink_to_outside(
    tmp_path: Path, artifact: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source, source_root = _write_workspace(workspace, "2.34")
    key = _build_key(workspace, source, source_root)
    shutil.rmtree(workspace / ".orchestrate")
    build_root = workspace / ".orchestrate" / "build" / key
    build_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / artifact
    sentinel.write_text("unchanged", encoding="utf-8")
    (build_root / artifact).symlink_to(sentinel)

    completed = _compile(workspace, source, source_root, diagnostics_json=True)

    _assert_path_error(completed)
    assert sentinel.read_text(encoding="utf-8") == "unchanged"


def test_closed_compile_rejects_artifact_file_symlink_to_outside(
    tmp_path: Path,
) -> None:
    target = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source, source_root = _write_workspace(workspace, target)
    key = _build_key(workspace, source, source_root)
    shutil.rmtree(workspace / ".orchestrate")
    build_root = workspace / ".orchestrate" / "build" / key
    build_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "closed_program.json"
    sentinel.write_text("unchanged", encoding="utf-8")
    (build_root / "closed_program.json").symlink_to(sentinel)

    completed = _compile(workspace, source, source_root, diagnostics_json=True)

    _assert_path_error(completed)
    assert sentinel.read_text(encoding="utf-8") == "unchanged"


@pytest.mark.parametrize("manifest_name,entry_path", [("sub/imports.json", "../producer.orc"), ("imports.json", "sub/../producer.orc")])
def test_compiled_import_fd_manifest_preserves_relative_parent_components(
    tmp_path: Path, manifest_name: str, entry_path: str
) -> None:
    from orchestrator.workflow_lisp.build import FrontendBuildRequest
    from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
    (tmp_path / "sub").mkdir()
    for name in ("main", "producer"):
        (tmp_path / (name + ".orc")).write_text(
            f'(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
            f'(defmodule {name}) (export run) (defworkflow run () -> Int 7))'
        )
    manifest = tmp_path / manifest_name
    manifest.write_text(json.dumps({"unused": {"kind": "compiled", "path": entry_path}}))
    request = FrontendBuildRequest(source_path=tmp_path / "main.orc", source_roots=(tmp_path,),
                                   workspace_root=tmp_path, imported_workflow_bundles_path=manifest)
    ordinary = build_closed_program_bundle(request)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        from dataclasses import replace
        retained = build_closed_program_bundle(replace(
            request, imported_workflow_bundles_path=Path(f"/proc/self/fd/{fd}/{manifest_name}")
        ))
        assert retained.program.digest == ordinary.program.digest
    finally:
        os.close(fd)
