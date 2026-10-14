from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built_orchestrator_wheel(
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    source_root = tmp_path_factory.mktemp("orchestrator-wheel-source")
    wheel_root = tmp_path_factory.mktemp("orchestrator-wheel-output")
    shutil.copyfile(REPO_ROOT / "pyproject.toml", source_root / "pyproject.toml")
    shutil.copyfile(REPO_ROOT / "LICENSE.md", source_root / "LICENSE.md")
    shutil.copytree(
        REPO_ROOT / "orchestrator",
        source_root / "orchestrator",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    environment = {**os.environ, "PIP_NO_INDEX": "1"}
    built = subprocess.run(
        (
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_root),
            str(source_root),
        ),
        cwd=source_root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    [wheel] = tuple(wheel_root.glob("*.whl"))
    return wheel


@pytest.fixture(scope="module")
def installed_orchestrator_python(
    tmp_path_factory: pytest.TempPathFactory,
    built_orchestrator_wheel: Path,
) -> tuple[Path, Path]:
    environment_root = tmp_path_factory.mktemp("orchestrator-installed")
    created = subprocess.run(
        (
            sys.executable,
            "-m",
            "venv",
            "--system-site-packages",
            str(environment_root),
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    python = environment_root / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    install_environment = {
        **os.environ,
        "PIP_NO_INDEX": "1",
        "PYTHONPATH": "",
        "PYTHONNOUSERSITE": "1",
    }
    installed = subprocess.run(
        (
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            str(built_orchestrator_wheel),
        ),
        env=install_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert installed.returncode == 0, installed.stderr
    return environment_root.resolve(), python


def test_built_wheel_excludes_demo_packages_and_model_weights(
    built_orchestrator_wheel: Path,
) -> None:
    with zipfile.ZipFile(built_orchestrator_wheel) as archive:
        members = archive.namelist()
        assert "orchestrator/workflow_lisp/stdlib_modules/std/improve.orc" in members
        assert "orchestrator/workflow_lisp/stdlib_modules/w3/std/improve.orc" in members
    assert not any(member.startswith("orchestrator/demo/") for member in members)
    assert not any(member.endswith(".pt") for member in members)


def _workspace_snapshot(
    root: Path,
) -> dict[str, tuple[str, int, int, int, bytes | None]]:
    snapshot: dict[str, tuple[str, int, int, int, bytes | None]] = {}
    for path in (root, *root.rglob("*")):
        relative = "." if path == root else path.relative_to(root).as_posix()
        metadata = path.stat()
        kind = "directory" if path.is_dir() else "file"
        content = None if kind == "directory" else path.read_bytes()
        snapshot[relative] = (
            kind,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            content,
        )
    return snapshot


def test_installed_wheel_uses_alternate_source_and_lsp_keeps_evaluated_boundary(
    tmp_path: Path,
    built_orchestrator_wheel: Path,
    installed_orchestrator_python: tuple[Path, Path],
) -> None:
    from tests.test_workflow_lisp_lsp_cli_parity import (
        _write_std_improve_parity_workspace,
    )
    from tests.test_workflow_lisp_lsp_stdio import (
        _LspProcess,
        _initialize_request,
    )

    environment_root, python = installed_orchestrator_python
    environment = {
        **os.environ,
        "PYTHONPATH": "",
        "PYTHONNOUSERSITE": "1",
        "PYTHONHASHSEED": "0",
    }
    probe = subprocess.run(
        (
            str(python),
            "-P",
            "-c",
            "import json, pathlib, orchestrator; "
            "package = pathlib.Path(orchestrator.__file__).resolve().parent; "
            "print(json.dumps({'origin': str(pathlib.Path(orchestrator.__file__).resolve()), "
            "'package': str(package)}))",
        ),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    imported = json.loads(probe.stdout)
    origin = Path(imported["origin"]).resolve()
    package_root = Path(imported["package"]).resolve()
    assert origin.is_relative_to(environment_root)
    assert package_root == origin.parent

    legacy_relative = "orchestrator/workflow_lisp/stdlib_modules/std/improve.orc"
    alternate_relative = "orchestrator/workflow_lisp/stdlib_modules/w3/std/improve.orc"
    with zipfile.ZipFile(built_orchestrator_wheel) as archive:
        expected_legacy = archive.read(legacy_relative)
        expected_alternate = archive.read(alternate_relative)
    installed_legacy = package_root / "workflow_lisp/stdlib_modules/std/improve.orc"
    installed_alternate = package_root / "workflow_lisp/stdlib_modules/w3/std/improve.orc"
    assert installed_legacy.read_bytes() == expected_legacy
    assert installed_alternate.read_bytes() == expected_alternate

    observer_root = tmp_path / "installed-resolver-observer"
    observer_root.mkdir()
    (observer_root / "sitecustomize.py").write_text(
        '''import hashlib
import json
import os
from pathlib import Path

import orchestrator
from orchestrator.workflow_lisp import compiler

_origin = Path(orchestrator.__file__).resolve()
_package_root = _origin.parent
_install_root = Path(os.environ["ORCHESTRATOR_INSTALL_ROOT"]).resolve()
if not _origin.is_relative_to(_install_root):
    raise RuntimeError(f"unexpected orchestrator origin: {_origin}")
_resolve_module_graph = compiler.resolve_module_graph

def _observe_resolve_module_graph(
    path,
    *,
    source_roots=None,
    source_read_trace=None,
    standalone_entry_namespace=None,
):
    graph = _resolve_module_graph(
        path,
        source_roots=source_roots,
        source_read_trace=source_read_trace,
        standalone_entry_namespace=standalone_entry_namespace,
    )
    if source_read_trace is None:
        return graph
    selected = graph.modules_by_name["std/improve"]
    selected_path = selected.path.resolve()
    raw = source_read_trace.raw_bytes_by_path[selected_path]
    row = {
        "origin": str(_origin),
        "package_root": str(_package_root),
        "selected_path": str(selected_path),
        "selected_root": str(selected.source_root.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "source_read_paths": sorted(
            str(record.canonical_path.resolve())
            for record in source_read_trace.records
        ),
    }
    with Path(os.environ["ORCHESTRATOR_GRAPH_RECEIPT"]).open(
        "a", encoding="utf-8"
    ) as receipt:
        receipt.write(json.dumps(row, sort_keys=True) + "\\n")
    return graph

compiler.resolve_module_graph = _observe_resolve_module_graph
''',
        encoding="utf-8",
    )

    def observed_environment(receipt: Path) -> dict[str, str]:
        return {
            **environment,
            "PYTHONPATH": str(observer_root),
            "ORCHESTRATOR_INSTALL_ROOT": str(environment_root),
            "ORCHESTRATOR_GRAPH_RECEIPT": str(receipt),
        }

    workspace, entry_path, _caller_roots = _write_std_improve_parity_workspace(
        tmp_path / "installed-workspace",
        target="2.36",
    )
    cli_provenance = tmp_path / "installed-cli-provenance.jsonl"
    cli = subprocess.run(
        (
            str(python),
            "-P",
            "-m",
            "orchestrator",
            "compile",
            str(entry_path),
            "--entry-workflow",
            "run",
            "--diagnostics-json",
        ),
        cwd=workspace,
        env=observed_environment(cli_provenance),
        capture_output=True,
        text=True,
        check=False,
    )
    assert cli.returncode == 0, cli.stdout + cli.stderr

    expected_selected_path = installed_alternate.resolve()
    expected_selected_root = (
        package_root / "workflow_lisp/stdlib_modules/w3"
    ).resolve()
    expected_sha256 = hashlib.sha256(installed_alternate.read_bytes()).hexdigest()

    def assert_selected_source(receipt_path: Path) -> None:
        rows = [
            json.loads(line)
            for line in receipt_path.read_text(encoding="utf-8").splitlines()
        ]
        assert rows
        assert all(
            Path(row["origin"]).resolve().is_relative_to(environment_root)
            for row in rows
        )
        assert all(Path(row["package_root"]).resolve() == package_root for row in rows)
        assert all(
            Path(row["selected_path"]).resolve() == expected_selected_path
            and Path(row["selected_root"]).resolve() == expected_selected_root
            and row["sha256"] == expected_sha256
            and str(expected_selected_path) in row["source_read_paths"]
            for row in rows
        )

    assert_selected_source(cli_provenance)

    entry_path.write_text(
        entry_path.read_text(encoding="utf-8").replace(
            "\n      0)))", '\n      "wrong return type")))'
        ),
        encoding="utf-8",
    )
    before_lsp = _workspace_snapshot(workspace)
    lsp_provenance = tmp_path / "installed-lsp-provenance.jsonl"
    process = _LspProcess(
        workspace,
        server_command=(str(python), "-P", "-m", "orchestrator.lsp"),
        # The observer-only PYTHONPATH replaces _LspProcess's repository path.
        extra_environment=observed_environment(lsp_provenance),
    )
    try:
        process.send(
            _initialize_request(
                1,
                root_uri=workspace.as_uri(),
                initialization_options={
                    "entry_workflows": {str(entry_path): "run"},
                },
            )
        )
        process.read_until(lambda item: item.get("id") == 1)
        process.send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": entry_path.as_uri(),
                        "languageId": "workflow-lisp",
                        "version": 1,
                        "text": entry_path.read_text(encoding="utf-8"),
                    }
                },
            }
        )
        published, _observed = process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
                and item["params"]["uri"] == entry_path.as_uri()
            )
        )
        codes = tuple(
            diagnostic["code"]
            for diagnostic in published["params"]["diagnostics"]
        )
        assert codes == ("return_type_mismatch",)
        process.shutdown()
    finally:
        process.close()
    assert_selected_source(lsp_provenance)
    assert _workspace_snapshot(workspace) == before_lsp
