from __future__ import annotations

import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


def _codec():
    spec = importlib.util.find_spec("orchestrator.workflow.evaluated.closure_evidence")
    assert spec is not None, "evaluated closure evidence encoding is missing"
    return importlib.import_module("orchestrator.workflow.evaluated.closure_evidence")


def _closure_module():
    spec = importlib.util.find_spec("orchestrator.workflow.evaluated.closure")
    assert spec is not None, "evaluated closure evidence helpers are missing"
    return importlib.import_module("orchestrator.workflow.evaluated.closure")


def test_evidence_keys_are_fixed_canonical_tuples_and_maps_sort_by_identity() -> None:
    codec = _codec()
    declared = codec.command_evidence_key("workspace", "tree/../tool")
    token = codec.command_evidence_key("workspace", "tree/../tool", 2)
    assert json.loads(declared) == ["workspace", "tree/../tool", None]
    assert codec.parse_command_evidence_key(token) == ("workspace", "tree/../tool", 2)

    digest = "sha256:" + "a" * 64
    unsorted = {
        token: {"kind": "file", "digest": digest},
        declared: {"kind": "file", "digest": digest},
    }
    assert list(codec.validate_implementation_evidence(unsorted)) == sorted(unsorted)
    for position in (True, -1):
        with pytest.raises(ValueError, match="key is malformed"):
            codec.command_evidence_key("workspace", "tool", position)
    with pytest.raises(ValueError, match="canonical JSON"):
        codec.parse_command_evidence_key('[ "workspace", "tool", null ]')
    for base, path in (("workspace", "tool//file"), ("absolute", "relative")):
        with pytest.raises(ValueError, match="key is malformed"):
            codec.command_evidence_key(base, path)


def test_evidence_validator_enforces_exact_rows_digests_and_target_grammar() -> None:
    codec = _codec()
    digest = "sha256:" + "b" * 64
    key = codec.command_evidence_key("workspace", "tool")
    valid = {key: {"kind": "file", "digest": digest, "target": "resolved/tool"}}
    assert codec.validate_implementation_evidence(valid) == valid

    invalid_rows = [
        {"kind": "file", "digest": digest, "ignored": True},
        {"kind": "file", "digest": "sha256:bad"},
        {"kind": "file", "digest": digest, "target": "../escape"},
        {"kind": "file", "digest": digest, "target": "resolved//tool"},
        {"kind": "directory", "target": "resolved/empty"},
    ]
    for row in invalid_rows:
        with pytest.raises(ValueError):
            codec.validate_implementation_evidence({key: row})

    absolute_key = codec.command_evidence_key("absolute", "/outside/tool")
    with pytest.raises(ValueError, match="target is malformed"):
        codec.validate_implementation_evidence({
            absolute_key: {"kind": "file", "digest": digest, "target": "outside/tool"}
        })


def test_package_evidence_survives_relocation_and_binds_helper_and_link_target(
    tmp_path: Path,
) -> None:
    import orchestrator

    source_package = Path(orchestrator.__file__).resolve().parent
    packages = [tmp_path / name / "orchestrator" for name in ("one", "two")]
    for package in packages:
        shutil.copytree(source_package, package)
        (package / "closure-link").symlink_to("workflow_lisp/closed/program.py")

    def evidence(package: Path, workspace: Path) -> dict[str, dict[str, object]]:
        workspace.mkdir()
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json; from orchestrator.workflow.evaluated.closure import "
                "resolve_command_evidence; print(json.dumps(resolve_command_evidence("
                "[], [{'base':'package:orchestrator','path':'.'}, "
                "{'base':'package:orchestrator','path':'closure-link'}], "
                "workspace_root='.')))" ,
            ],
            cwd=workspace,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(package.parent),
            },
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    first = evidence(packages[0], tmp_path / "workspace-one")
    second = evidence(packages[1], tmp_path / "workspace-two")
    assert first == second
    link_key = next(key for key in first if json.loads(key)[1] == "closure-link")
    assert first[link_key]["target"] == (
        "package:orchestrator/workflow_lisp/closed/program.py"
    )
    helper = packages[1] / "workflow" / "evaluated" / "closure.py"
    helper.write_bytes(helper.read_bytes() + b"\n# changed package helper\n")
    assert evidence(packages[1], tmp_path / "workspace-three") != first


def test_directory_rows_bind_nested_empty_symlink_targets_without_ordinary_dirs(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.closed.program import canonical_digest

    module = _closure_module()
    workspace = tmp_path / "workspace"
    tree = workspace / "tree"
    tree.mkdir(parents=True)
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    target_a.mkdir()
    target_b.mkdir()
    link = tree / "empty"
    link.symlink_to("../../target-a", target_is_directory=True)
    (tree / "empty-again").symlink_to("../../target-a", target_is_directory=True)
    closure = [{"base": "workspace", "path": "tree"}]
    before = module.resolve_command_evidence(["python"], closure, workspace_root=workspace)
    key = next(iter(before))
    assert json.loads(key) == ["workspace", "tree", None]
    expected_a = [
        {"path": name, "kind": "directory", "target": str(target_a.resolve())}
        for name in ("empty", "empty-again")
    ]
    assert before[key]["digest"] == canonical_digest(expected_a)
    (target_a / "ordinary-empty").mkdir()
    with_ordinary_empty = module.resolve_command_evidence(
        ["python"], closure, workspace_root=workspace
    )
    assert with_ordinary_empty == before
    (target_a / "ordinary-empty").rmdir()
    root_alias = workspace / "tree-alias"
    root_alias.symlink_to(tree, target_is_directory=True)
    root_evidence = module.resolve_command_evidence(
        ["python"], [{"base": "workspace", "path": "tree-alias"}],
        workspace_root=workspace,
    )
    root_row = next(iter(root_evidence.values()))
    assert root_row["target"] == "tree"
    assert root_row["digest"] == before[key]["digest"]
    with pytest.raises(module.ClosureEvidenceError):
        module.resolve_command_evidence(
            ["python"], closure, workspace_root=workspace,
            destinations=[target_a / "new-output"],
        )
    assert not (target_a / "new-output").exists()
    link.unlink()
    link.symlink_to("../../target-b", target_is_directory=True)
    after = module.resolve_command_evidence(["python"], closure, workspace_root=workspace)
    assert before != after
    expected_b = [
        {"path": "empty", "kind": "directory", "target": str(target_b.resolve())},
        {"path": "empty-again", "kind": "directory", "target": str(target_a.resolve())},
    ]
    assert after[key]["digest"] == canonical_digest(expected_b)
