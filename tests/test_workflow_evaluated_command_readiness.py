from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.authority import (
    RunAuthorityError,
    load_run_authority,
)
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.closed.sites import _ast_nodes
from tests.test_workflow_evaluated_authority import _checked_command_program, _publish


def _without_argv_transport(program: ClosedProgram) -> ClosedProgram:
    tree = deepcopy(program.tree)
    bodies = [tree["body"], *(definition["body"] for definition in tree["definitions"].values())]
    for body in bodies:
        for node in _ast_nodes(body):
            if node.get("k") == "perform" and node.get("class") == "command":
                node.pop("argv_transport", None)
    return ClosedProgram.from_artifact(json.dumps(tree))


def test_compile_only_command_transport_refuses_before_authority_publication(tmp_path: Path) -> None:
    checked = _checked_command_program(
        tmp_path / "source",
        entry_sites=(("tool", ("python", "script.py")),),
    )
    compile_only = _without_argv_transport(checked)
    run_root = tmp_path / "runs" / "compile-only-command"

    with pytest.raises(RunAuthorityError) as excinfo:
        _publish(run_root, compile_only)

    assert excinfo.value.code == "command_transport_required"
    assert not run_root.exists()


def test_stored_authority_without_command_transport_is_inconsistent(tmp_path: Path) -> None:
    checked = _checked_command_program(
        tmp_path / "source",
        entry_sites=(("tool", ("python", "script.py")),),
    )
    run_root = tmp_path / "runs" / "stored-command-without-transport"
    _publish(run_root, checked)
    stored = _without_argv_transport(checked)
    (run_root / "closed_program.json").write_text(stored.artifact(), encoding="utf-8")
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header["program_digest"] = stored.digest
    header_path.write_bytes(canonical_json_bytes(header))
    before = {
        path.name: path.read_bytes()
        for path in (header_path, run_root / "closed_program.json", run_root / "memo.jsonl")
    }

    with pytest.raises(RunAuthorityError) as excinfo:
        load_run_authority(run_root)

    assert excinfo.value.code == "memo_inconsistent"
    assert before == {
        path.name: path.read_bytes()
        for path in (header_path, run_root / "closed_program.json", run_root / "memo.jsonl")
    }
