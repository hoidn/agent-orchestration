from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from orchestrator._common.safe_tree import SafeTreeError
from orchestrator.workflow.evaluated import interpreters
from orchestrator.workflow.evaluated import interpreters as interpreter_module
from orchestrator.workflow.evaluated.authority import RunAuthorityError, load_run_authority
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.sites import _ast_nodes
from tests.test_workflow_evaluated_authority import _publish


def test_path_symlink_is_pinned_once_and_resume_ignores_new_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_bin = tmp_path / "first-bin"
    second_bin = tmp_path / "second-bin"
    first_bin.mkdir()
    second_bin.mkdir()
    executable = first_bin / "python-real"
    executable.write_bytes(b"#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    link = first_bin / "python"
    link.symlink_to(executable.name)
    alternative = second_bin / "python"
    alternative.write_bytes(b"#!/bin/sh\nexit 1\n")
    alternative.chmod(0o755)

    real_which = shutil.which
    calls: list[str] = []

    def counted_which(command: str, **kwargs: object) -> str | None:
        calls.append(command)
        return real_which(command, **kwargs)

    monkeypatch.setattr(interpreters.shutil, "which", counted_which)
    pin = interpreters.pin_command_interpreter(["python", "probe.py"], path=str(first_bin))
    assert pin == {
        "path": str(link),
        "digest": "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest(),
    }
    assert calls == ["python"]

    monkeypatch.setenv("PATH", str(second_bin))
    assert interpreters.check_command_interpreter(pin) is None
    assert calls == ["python"]
    executable.write_bytes(b"#!/bin/sh\nexit 2\n")
    assert interpreters.check_command_interpreter(pin) == "interpreter_changed"
    link.unlink()
    with pytest.raises(interpreters.InterpreterError) as error:
        interpreters.check_command_interpreter(pin)
    assert error.value.code == "resume_interpreter_missing"


@pytest.mark.parametrize("relative_search_path", [False, True])
def test_path_dotdot_after_symlink_keeps_which_selection_and_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_search_path: bool,
) -> None:
    real_bin = tmp_path / "real" / "bin"
    real_bin.mkdir(parents=True)
    path_alias = tmp_path / "path-alias"
    path_alias.symlink_to("real/bin", target_is_directory=True)
    expected = tmp_path / "real" / "runner"
    expected.write_text("#!/bin/sh\nprintf 'expected\\n'\n")
    expected.chmod(0o755)
    wrong = tmp_path / "runner"
    wrong.write_text("#!/bin/sh\nprintf 'wrong\\n'\n")
    wrong.chmod(0o755)
    alternate = tmp_path / "alternate-bin"
    alternate.mkdir()
    (alternate / "runner").write_text("#!/bin/sh\nprintf 'alternate\\n'\n")
    (alternate / "runner").chmod(0o755)

    monkeypatch.chdir(tmp_path)
    search_path = "path-alias/.." if relative_search_path else str(path_alias) + "/.."
    real_which = shutil.which
    which_result = real_which("runner", path=search_path)
    assert which_result is not None
    expected_pin_path = (
        which_result if os.path.isabs(which_result)
        else os.path.join(os.getcwd(), which_result)
    )
    calls: list[tuple[str, str]] = []

    def counted_which(command: str, *, path: str | None = None) -> str | None:
        calls.append((command, path or ""))
        return real_which(command, path=path)

    monkeypatch.setattr(interpreters.shutil, "which", counted_which)
    pin = interpreters.pin_command_interpreter(["runner"], path=search_path)
    assert pin == {
        "path": expected_pin_path,
        "digest": "sha256:" + hashlib.sha256(expected.read_bytes()).hexdigest(),
    }
    assert calls == [("runner", search_path)]
    assert subprocess.check_output([pin["path"]], text=True).strip() == "expected"

    monkeypatch.setenv("PATH", str(alternate))
    assert interpreters.check_command_interpreter(pin) is None
    assert subprocess.check_output([pin["path"]], text=True).strip() == "expected"
    assert calls == [("runner", search_path)]


def test_only_a_bare_first_token_is_automatically_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_which(*args: object, **kwargs: object) -> None:
        raise AssertionError("PATH lookup is not expected for a slashed token")

    monkeypatch.setattr(interpreters.shutil, "which", unexpected_which)
    assert interpreters.pin_command_interpreter(["./python", "script.py"]) is None
    assert interpreters.pin_command_interpreter([str(tmp_path / "python")]) is None


def test_bad_pins_and_missing_start_interpreters_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(interpreters.InterpreterError) as error:
        interpreters.pin_command_interpreter(["missing-python"], path=str(tmp_path))
    assert error.value.code == "command_interpreter_missing"

    with pytest.raises(ValueError, match="malformed"):
        interpreters.check_command_interpreter(
            {"path": "/bin/sh", "digest": "sha256:abc"}
        )

    blocked = tmp_path / "blocked-python"
    blocked.write_bytes(b"interpreter")
    real_access = interpreters.os.access
    monkeypatch.setattr(interpreters.shutil, "which", lambda *_args, **_kwargs: str(blocked))
    monkeypatch.setattr(
        interpreters.os, "access",
        lambda path, mode: False if os.fspath(path) == str(blocked) else real_access(path, mode),
    )
    with pytest.raises(interpreters.InterpreterError, match="not launchable"):
        interpreters.pin_command_interpreter(["blocked-python"])
    pin = {
        "path": str(blocked),
        "digest": "sha256:" + hashlib.sha256(blocked.read_bytes()).hexdigest(),
    }
    with pytest.raises(interpreters.InterpreterError) as resume_error:
        interpreters.check_command_interpreter(pin)
    assert resume_error.value.code == "resume_interpreter_missing"


def test_safe_tree_read_errors_become_interpreter_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "python"
    executable.write_bytes(b"#!/bin/sh\n")
    executable.chmod(0o755)

    def denied_hash(*_args: object, **_kwargs: object) -> str:
        raise SafeTreeError("injected safe-tree rejection")

    monkeypatch.setattr(interpreters.shutil, "which", lambda *_args, **_kwargs: str(executable))
    monkeypatch.setattr(interpreters, "hash_regular_file", denied_hash)
    with pytest.raises(interpreters.InterpreterError) as start_error:
        interpreters.pin_command_interpreter(["python"])
    assert start_error.value.code == "command_interpreter_missing"

    pin = {"path": str(executable), "digest": "sha256:" + "0" * 64}
    with pytest.raises(interpreters.InterpreterError) as resume_error:
        interpreters.check_command_interpreter(pin)
    assert resume_error.value.code == "resume_interpreter_missing"


_VALID_PIN = {"path": "/bin/python", "digest": "sha256:" + "0" * 64}


def _write_command_source(
    root: Path, *, entry_sites: tuple[tuple[str, tuple[str, ...]], ...],
    unreachable_sites: tuple[tuple[str, str, tuple[str, ...]], ...] = (),
) -> Path:
    assert entry_sites
    assert len(unreachable_sites) <= 1
    source = root / "authority" / "commands.orc"
    source.parent.mkdir(parents=True, exist_ok=True)
    entry_bindings = [
        f"(value_{index} (command-result {boundary} :argv "
        f"({' '.join(json.dumps(token) for token in command)}) :returns Int))"
        for index, (boundary, command) in enumerate(entry_sites)
    ]
    unreachable_source = "\n".join(
        f"(defproc {name} () -> Int :effects ((uses-command {boundary})) "
        f":lowering inline (command-result {boundary} :argv "
        f"({' '.join(json.dumps(token) for token in command)}) :returns Int))"
        for name, boundary, command in unreachable_sites
    )
    dormant_branch = (
        f"(if false ({unreachable_sites[0][0]}) value_{len(entry_sites) - 1})"
        if unreachable_sites
        else f"value_{len(entry_sites) - 1}"
    )

    source_parts = (
        '(workflow-lisp (:language "0.1") (:target-dsl "2.35")',
        "  (defmodule authority/commands) (export run)",
        unreachable_source,
        "  (defworkflow run () -> Int",
        f"    (let* ({' '.join(entry_bindings)}) {dormant_branch}))",
        ")",
    )
    source.write_text("\n".join(filter(None, source_parts)), encoding="utf-8")
    return source


def _checked_command_program(
    root: Path,
    *,
    entry_sites: tuple[tuple[str, tuple[str, ...]], ...],
    unreachable_sites: tuple[tuple[str, str, tuple[str, ...]], ...] = (),
    unreferenced_bindings: tuple[tuple[str, tuple[str, ...]], ...] = (),
):
    """Compile command sites and assert the checked artifact contains them."""
    source = _write_command_source(
        root, entry_sites=entry_sites, unreachable_sites=unreachable_sites
    )
    all_bindings = [
        *entry_sites,
        *((boundary, command) for _name, boundary, command in unreachable_sites),
        *unreferenced_bindings,
    ]
    boundaries = {
        boundary: ExternalToolBinding(
            name=boundary,
            stable_command=command,
            closure=(),
        )
        for boundary, command in all_bindings
    }
    typed = compile_typed_program(
        source,
        entry_workflow="run",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries=boundaries,
    )
    program = build_closed_program(typed)
    bodies = [
        program.tree["body"],
        *(definition["body"] for definition in program.tree["definitions"].values()),
    ]
    emitted = Counter(
        tuple(node["command"])
        for body in bodies
        for node in _ast_nodes(body)
        if node.get("k") == "perform" and node.get("class") == "command"
    )
    assert emitted == Counter(
        command for _boundary, command in entry_sites
    ) + Counter(command for _name, _boundary, command in unreachable_sites)
    return program


def test_publish_pins_each_emitted_bare_interpreter_once_and_reads_shape_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = _checked_command_program(
        tmp_path / "source",
        entry_sites=(
            ("first", ("python", "first.py")),
            ("second", ("python", "second.py")),
            ("slashed", ("./local-command", "local.py")),
        ),
        unreachable_sites=(
            ("sleeping", "unreachable", ("unreachable", "sleeping.py")),
        ),
        unreferenced_bindings=(("configured_only", ("configured-only", "unused.py")),),
    )
    path = tmp_path / "bin"
    path.mkdir()
    executable_bytes = {
        "python": b"#!/bin/sh\nexit 0\n",
        "unreachable": b"#!/bin/sh\nexit 1\n",
    }
    expected = {}
    for name, contents in executable_bytes.items():
        executable = path / name
        executable.write_bytes(contents)
        executable.chmod(0o755)
        expected[name] = {
            "path": str(executable),
            "digest": "sha256:" + hashlib.sha256(contents).hexdigest(),
        }
    monkeypatch.setenv("PATH", str(path))
    real_which = interpreter_module.shutil.which
    calls: list[str] = []

    def counted_which(command: str, *, path: str | None = None) -> str | None:
        calls.append(command)
        return real_which(command, path=path)

    monkeypatch.setattr(interpreter_module.shutil, "which", counted_which)
    run_root = tmp_path / "runs" / "pinned-commands"

    _publish(run_root, program)
    for name in executable_bytes:
        (path / name).unlink()
    authority = load_run_authority(run_root)

    assert authority.header["interpreters"] == expected
    assert sorted(calls) == ["python", "unreachable"]


def test_missing_emitted_interpreter_fails_before_authority_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = _checked_command_program(
        tmp_path / "source",
        entry_sites=(("missing", ("not-installed-interpreter", "script.py")),),
    )
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    run_root = tmp_path / "runs" / "missing-interpreter"

    with pytest.raises(interpreter_module.InterpreterError) as excinfo:
        _publish(run_root, program)

    assert excinfo.value.code == "command_interpreter_missing"
    assert not run_root.exists()


@pytest.mark.parametrize("interpreter_pins", [
    {}, {"python": _VALID_PIN, "extra": _VALID_PIN}, [],
    {"python": {**_VALID_PIN, "extra": True}}, {"python": {**_VALID_PIN, "path": "bin/python"}},
    {"python": {**_VALID_PIN, "path": "/bin/python\x00alias"}},
    {"python": {**_VALID_PIN, "digest": "sha256:" + "A" * 64}},
])
def test_load_rejects_interpreter_pin_coverage_or_shape_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interpreter_pins: object
) -> None:
    program = _checked_command_program(
        tmp_path / "source",
        entry_sites=(("tool", ("python", "script.py")),),
    )
    path = tmp_path / "bin"
    path.mkdir()
    executable = path / "python"
    executable.write_bytes(b"#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(path))
    run_root = tmp_path / "runs" / "invalid-interpreter-map"
    _publish(run_root, program)

    header_path = run_root / "run.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header["interpreters"] = interpreter_pins
    header_path.write_text(json.dumps(header), encoding="utf-8")
    before = {
        path.name: path.read_bytes()
        for path in (header_path, run_root / "closed_program.json", run_root / "memo.jsonl")
    }

    with pytest.raises(RunAuthorityError):
        load_run_authority(run_root)

    assert before == {
        path.name: path.read_bytes()
        for path in (header_path, run_root / "closed_program.json", run_root / "memo.jsonl")
    }
