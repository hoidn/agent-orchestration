from __future__ import annotations

import importlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


def _closure_module():
    spec = importlib.util.find_spec("orchestrator.workflow.evaluated.closure")
    assert spec is not None, "evaluated closure evidence helpers are missing"
    return importlib.import_module("orchestrator.workflow.evaluated.closure")


def test_command_evidence_tracks_bytes_without_tracking_mtime(tmp_path: Path) -> None:
    module = _closure_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = workspace / "tool.py"
    tool.write_bytes(b"print(1)\n")

    original = module.resolve_command_evidence(
        ["python", "tool.py"], [], workspace_root=workspace
    )
    os.utime(tool, ns=(tool.stat().st_atime_ns, tool.stat().st_mtime_ns + 5_000_000))
    same_bytes = module.resolve_command_evidence(
        ["python", "tool.py"], [], workspace_root=workspace
    )
    assert original == same_bytes

    tool.write_bytes(b"print(2)\n")
    changed_bytes = module.resolve_command_evidence(
        ["python", "tool.py"], [], workspace_root=workspace
    )
    assert original != changed_bytes


def _evidence_paths(evidence: dict[str, object]) -> set[str]:
    return {json.loads(key)[1] for key in evidence}


def test_automatic_selection_uses_workspace_spellings_and_existing_endpoints(
    tmp_path: Path,
) -> None:
    module = _closure_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in ("python", "module.py", "--config", "literal", "data"):
        (workspace / name).write_text(name)
    evidence = module.resolve_command_evidence(
        ["python", "module.py", "--config", "literal", "data"],
        [],
        workspace_root=workspace,
    )
    assert _evidence_paths(evidence) == {"module.py", "--config", "literal", "data"}
    bare_prior = module.resolve_command_evidence(
        ["python"], [{"base": "workspace", "path": "python"}], workspace_root=workspace
    )
    prior_row = next(iter(bare_prior.values()))
    codec = importlib.import_module("orchestrator.workflow.evaluated.closure_evidence")
    forged_position_zero = {
        codec.command_evidence_key("workspace", "python", 0): prior_row,
    }
    with pytest.raises(ValueError, match=r"bare argv\[0\]"):
        module.resolve_command_evidence(
            ["python"], [], workspace_root=workspace, prior=forged_position_zero
        )

    missing = module.resolve_command_evidence(
        ["python", "probe.py"], [], workspace_root=workspace
    )
    assert missing == {}
    with pytest.raises(module.ClosureEvidenceError):
        module.resolve_command_evidence(
            ["python", "probe.py"],
            [{"base": "workspace", "path": "probe.py"}],
            workspace_root=workspace,
        )
    (workspace / "probe.py").write_text("now present")
    assert module.resolve_command_evidence(
        ["python", "probe.py"], [], workspace_root=workspace
    ) != missing


def test_workspace_executable_path_is_mandatory_even_when_missing(tmp_path: Path) -> None:
    module = _closure_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(module.ClosureEvidenceError):
        module.resolve_command_evidence(["bin/tool"], [], workspace_root=workspace)
    with pytest.raises(module.ClosureEvidenceError):
        module.resolve_command_evidence(
            [str(workspace / "missing-tool")], [], workspace_root=workspace
        )


def test_automatic_lookup_preserves_trailing_dot_semantics(tmp_path: Path) -> None:
    module = _closure_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "plain-file").write_text("x")
    evidence = module.resolve_command_evidence(
        ["python", "plain-file/."], [], workspace_root=workspace
    )
    assert evidence == {}
    prior = module.resolve_command_evidence(
        ["python", "plain-file"], [], workspace_root=workspace
    )
    with pytest.raises(module.ClosureEvidenceError):
        module.resolve_command_evidence(
            ["python", "plain-file/."], [], workspace_root=workspace, prior=prior
        )

    (workspace / "bin").mkdir()
    (workspace / "bin" / "tool").write_text("#!/bin/sh\n")
    with pytest.raises(module.ClosureEvidenceError):
        module.resolve_command_evidence(
            ["bin/tool/."], [], workspace_root=workspace
        )


def test_evidence_union_requires_prior_paths_but_omits_unselected_history(
    tmp_path: Path,
) -> None:
    module = _closure_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    old_path = workspace / "old.py"
    old_path.write_bytes(b"old")
    prior = module.resolve_command_evidence(
        ["python", "old.py"], [], workspace_root=workspace
    )
    old_path.unlink()
    with pytest.raises(module.ClosureEvidenceError):
        module.resolve_command_evidence(
            ["python", "old.py"], [], workspace_root=workspace, prior=prior
        )

    old_path.write_bytes(b"new")
    # An invalidated committed start is omitted by its caller, so authorized
    # re-execution observes the current bytes without pinning old history.
    fresh = module.resolve_command_evidence(
        ["python", "old.py"], [], workspace_root=workspace
    )
    assert fresh != prior
    # A newer pending start is supplied and must still be compared by the caller.
    assert module.resolve_command_evidence(
        ["python", "old.py"], [], workspace_root=workspace, prior=prior
    ) != prior
    assert module.resolve_command_evidence(
        ["python", "old.py"], [], workspace_root=workspace, prior=fresh
    ) == fresh


def test_directory_digest_includes_dotfiles_and_file_overlap_but_not_bytecode(
    tmp_path: Path,
) -> None:
    module = _closure_module()
    workspace = tmp_path / "workspace"
    tree = workspace / "tree"
    (tree / "__pycache__").mkdir(parents=True)
    (tree / "pkg" / "__pycache__").mkdir(parents=True)
    (tree / "code.py").write_bytes(b"code")
    (tree / "__init__.py").write_bytes(b"init")
    (tree / ".hidden").write_bytes(b"hidden")
    (tree / "__pycache__" / "code.pyc").write_bytes(b"cache")
    (tree / "pkg" / "__pycache__" / "code.pyc").write_bytes(b"cache")
    closure = [
        {"base": "workspace", "path": "tree"},
        {"base": "workspace", "path": "tree/code.py"},
    ]
    evidence = module.resolve_command_evidence(
        ["python"], closure, workspace_root=workspace,
    )
    assert len(evidence) == 2
    before_empty = evidence
    (tree / "ordinary-empty").mkdir()
    assert module.resolve_command_evidence(
        ["python"], closure, workspace_root=workspace,
    ) == before_empty
    (tree / "ordinary-empty").rmdir()
    assert module.resolve_command_evidence(
        ["python"], closure, workspace_root=workspace
    ) == before_empty
    aliased_tree = workspace / "tree-alias"
    aliased_tree.symlink_to(tree, target_is_directory=True)
    alias_closure = [{"base": "workspace", "path": "tree-alias"}]
    alias_before_empty = module.resolve_command_evidence(
        ["python"], alias_closure, workspace_root=workspace
    )
    (tree / "ordinary-empty").mkdir()
    assert module.resolve_command_evidence(
        ["python"], alias_closure, workspace_root=workspace
    ) == alias_before_empty
    (tree / "ordinary-empty").rmdir()
    explicit_cache = [{"base": "workspace", "path": "tree/__pycache__/code.pyc"}]
    explicit_before = module.resolve_command_evidence(
        ["python"], explicit_cache, workspace_root=workspace
    )
    (tree / "__pycache__" / "code.pyc").write_bytes(b"changed cache")
    assert module.resolve_command_evidence(
        ["python"], closure, workspace_root=workspace
    ) == before_empty
    assert module.resolve_command_evidence(
        ["python"], explicit_cache, workspace_root=workspace
    ) != explicit_before
    (tree / "pkg" / "__pycache__" / "code.pyc").write_bytes(b"changed nested cache")
    assert module.resolve_command_evidence(
        ["python"], closure, workspace_root=workspace
    ) == before_empty
    (tree / "__init__.py").write_bytes(b"changed init")
    assert module.resolve_command_evidence(
        ["python"], closure, workspace_root=workspace
    ) != before_empty
    (tree / "__init__.py").write_bytes(b"init")
    (tree / "__pycache__" / "code.pyc").write_bytes(b"cache")
    (tree / ".hidden").write_bytes(b"changed dotfile")
    assert module.resolve_command_evidence(
        ["python"], closure, workspace_root=workspace
    ) != before_empty


def test_symlink_retarget_changes_evidence_even_when_bytes_match(tmp_path: Path) -> None:
    module = _closure_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in ("target-a", "target-b"):
        (workspace / name).write_bytes(b"same")
    alias = workspace / "alias"
    alias.symlink_to("target-a")
    before = module.resolve_command_evidence(
        ["python", "alias"], [], workspace_root=workspace
    )
    before_row = next(iter(before.values()))
    assert before_row["target"] == "target-a"
    alias.unlink()
    alias.symlink_to("target-b")
    after = module.resolve_command_evidence(
        ["python", "alias"], [], workspace_root=workspace
    )
    assert before != after
    assert next(iter(after.values()))["target"] == "target-b"

    outside_a, outside_b = tmp_path / "outside-a", tmp_path / "outside-b"
    outside_a.write_bytes(b"same")
    outside_b.write_bytes(b"same")
    alias.unlink()
    alias.symlink_to(outside_a)
    escaped_before = module.resolve_command_evidence(
        ["python", "alias"], [], workspace_root=workspace
    )
    assert next(iter(escaped_before.values()))["target"] == str(outside_a.resolve())
    alias.unlink()
    alias.symlink_to(outside_b)
    escaped_after = module.resolve_command_evidence(
        ["python", "alias"], [], workspace_root=workspace
    )
    assert escaped_before != escaped_after


def test_symlink_lookup_keeps_dotdot_after_intermediate_link(tmp_path: Path) -> None:
    module = _closure_module()
    workspace = tmp_path / "workspace"
    for parent in ("target-a", "target-b"):
        (workspace / parent / "nested").mkdir(parents=True)
        (workspace / parent / "script.py").write_bytes(b"same")
    alias = workspace / "alias"
    alias.symlink_to("target-a/nested")
    before = module.resolve_command_evidence(
        ["python", "alias/../script.py"], [], workspace_root=workspace
    )
    alias.unlink()
    alias.symlink_to("target-b/nested")
    after = module.resolve_command_evidence(
        ["python", "alias/../script.py"], [], workspace_root=workspace
    )
    assert before != after


def test_dangling_symlink_cycle_and_lookup_error_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _closure_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "dangling").symlink_to("missing")
    with pytest.raises(module.ClosureEvidenceError):
        module.resolve_command_evidence(
            ["python", "dangling"], [], workspace_root=workspace
        )

    (workspace / "cycle").symlink_to("cycle")
    with pytest.raises(module.ClosureEvidenceError):
        module.resolve_command_evidence(
            ["python"], [{"base": "workspace", "path": "cycle"}], workspace_root=workspace
        )

    (workspace / "dangling-parent").symlink_to("missing-parent", target_is_directory=True)
    assert module.resolve_command_evidence(
        ["python", "dangling-parent/child"], [], workspace_root=workspace
    ) == {}

    denied = workspace / "denied"
    denied.write_bytes(b"x")
    real_lstat = os.lstat

    def injected_lstat(path: str | os.PathLike[str], *args: object, **kwargs: object):
        if os.fspath(path) == str(denied):
            raise PermissionError("injected EACCES")
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(module.os, "lstat", injected_lstat)
    with pytest.raises(module.ClosureEvidenceError, match="injected EACCES"):
        module.resolve_command_evidence(
            ["python", "denied"], [], workspace_root=workspace
        )


def test_disjoint_destinations_are_rejected_before_any_path_is_created(tmp_path: Path) -> None:
    module = _closure_module()
    workspace = tmp_path / "workspace"
    code = workspace / "code"
    code.mkdir(parents=True)
    (code / "main.py").write_text("pass\n")
    output_alias = workspace / "output-alias"
    output_alias.symlink_to(code, target_is_directory=True)
    closure = [{"base": "workspace", "path": "code"}]
    baseline = module.resolve_command_evidence(
        ["python"], closure, workspace_root=workspace
    )
    destinations = [output_alias / "capture" / "stdout.txt"]
    with pytest.raises(module.ClosureEvidenceError):
        module.resolve_command_evidence(
            ["python"],
            closure,
            workspace_root=workspace,
            destinations=destinations,
        )
    assert not (code / "capture").exists()
    assert module.resolve_command_evidence(
        ["python"], closure, workspace_root=workspace
    ) == baseline
    assert (code / "main.py").read_text() == "pass\n"

    with pytest.raises(module.ClosureEvidenceError):
        module.resolve_command_evidence(
            ["python"],
            [{"base": "workspace", "path": "code/main.py"}],
            workspace_root=workspace,
            destinations=[code / "main.py"],
        )


def test_workspace_dot_rejects_normal_run_destination_without_creating_it(
    tmp_path: Path,
) -> None:
    module = _closure_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_root = workspace / ".orchestrate" / "runs" / "run-1"
    with pytest.raises(module.ClosureEvidenceError):
        module.resolve_command_evidence(
            ["printf", "."],
            [],
            workspace_root=workspace,
            destinations=[run_root],
        )
    assert not run_root.exists()


def test_external_absolute_tokens_need_an_explicit_closure(tmp_path: Path) -> None:
    module = _closure_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"outside")
    command = ["python", str(outside)]
    assert module.resolve_command_evidence(command, [], workspace_root=workspace) == {}
    declared = module.resolve_command_evidence(
        command,
        [{"base": "absolute", "path": str(outside)}],
        workspace_root=workspace,
    )
    outside.write_bytes(b"changed")
    assert module.resolve_command_evidence(
        command,
        [{"base": "absolute", "path": str(outside)}],
        workspace_root=workspace,
    ) != declared

    executable = tmp_path / "external-tool"
    executable.write_bytes(b"#!/bin/sh\n")
    assert module.resolve_command_evidence(
        [str(executable)], [], workspace_root=workspace
    ) == {}
    explicit_executable = module.resolve_command_evidence(
        [str(executable)], [{"base": "absolute", "path": str(executable)}],
        workspace_root=workspace,
    )
    assert len(explicit_executable) == 1


def test_absolute_prefix_uses_lexical_workspace_root_but_targets_resolved_root(
    tmp_path: Path,
) -> None:
    module = _closure_module()
    physical = tmp_path / "physical-workspace"
    physical.mkdir()
    script = physical / "script.py"
    script.write_bytes(b"same")
    lexical = tmp_path / "workspace-alias"
    lexical.symlink_to(physical, target_is_directory=True)

    command = ["python", str(lexical / "script.py")]
    evidence = module.resolve_command_evidence(command, [], workspace_root=lexical)
    key = next(iter(evidence))
    assert json.loads(key) == ["workspace", "script.py", 1]
    assert evidence[key]["target"] == "script.py"
    assert command == ["python", str(lexical / "script.py")]
    assert module.resolve_command_evidence(
        ["python", str(script)], [], workspace_root=lexical
    ) == {}


def test_frontend_artifact_readback_feeds_command_evidence(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp.build import FrontendBuildRequest
    from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
    from orchestrator.workflow_lisp.closed.program import ClosedProgram

    source_root = tmp_path / "src"
    source = source_root / "example" / "entry.orc"
    source.parent.mkdir(parents=True)
    from orchestrator.workflow_lisp import syntax

    source.write_text(f'''(workflow-lisp (:language "0.1") (:target-dsl "{syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")
      (defmodule example/entry) (export run)
      (defworkflow run ((value Int)) -> Int
        (command-result fetch :argv ("python" "probe.py" value) :returns Int)))''')
    (tmp_path / "probe.py").write_text("print(1)\n")
    providers = tmp_path / "providers.json"
    prompts = tmp_path / "prompts.json"
    commands = tmp_path / "commands.json"
    providers.write_text("{}")
    prompts.write_text("{}")
    commands.write_text(json.dumps({"fetch": {
        "kind": "external_tool",
        "stable_command": ["python", "probe.py"],
        "closure": [],
    }}))
    result = build_closed_program_bundle(FrontendBuildRequest(
        source_path=source,
        source_roots=(source_root,),
        provider_externs_path=providers,
        prompt_externs_path=prompts,
        command_boundaries_path=commands,
        workspace_root=tmp_path,
    ))
    program = ClosedProgram.from_artifact(result.artifact_path.read_text())
    row = program.tree["configuration"]["commands"]["fetch"]
    evidence = _closure_module().resolve_command_evidence(
        row["stable_command"], row["closure"], workspace_root=tmp_path
    )
    assert len(evidence) == 1
    assert _evidence_paths(evidence) == {"probe.py"}
