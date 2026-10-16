from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow.evaluated import values as runtime_values
from orchestrator.workflow_lisp.closed import command_templates
from tests.workflow_lisp_closed_program_helpers import build


@pytest.mark.parametrize(("body", "returns", "expected", "additions"), [
    ("(list/length (list/map ((item (list 3 1 2))) item))", "Int", 3, []),
    ("(list/map ((item (list (+ 1 10) (+ 2 20)))) (+ item 100))", "List[Int]",
     (111, 122), [[1, 10], [2, 20], [11, 100], [22, 100]]),
    ("(let* ((x 7)) (list/map ((item (list (+ x 1) (+ x 2)))) "
     "(let* ((x (+ item 10))) x)))", "List[Int]", (18, 19),
     [[7, 1], [7, 2], [8, 10], [9, 10]]),
], ids=["halt-body-block", "source-once-before-ordered-bodies", "body-local-shadowing"])
def test_map_prepares_source_and_binder_body_without_frontend_reentry(
    tmp_path: Path, monkeypatch, body, returns, expected, additions,
):
    def forbidden(*args, **kwargs):
        pytest.fail("prepared map re-entered frontend elaboration")

    monkeypatch.setattr(command_templates, "prepare_frontend_value", forbidden)
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/prepared_map) (export run)
      (defworkflow run () -> {returns} {body}))'''
    artifact = build(tmp_path, source).artifact()
    for path in tmp_path.rglob("*.orc"):
        path.unlink()
    restored = ClosedProgram.from_artifact(artifact)
    observed = []
    original = runtime_values.evaluate_pure_expr

    def trace(payload, *, resolved_bindings, **kwargs):
        if payload["expr"].get("operator") == "+":
            observed.append(list(resolved_bindings.values()))
        return original(payload, resolved_bindings=resolved_bindings, **kwargs)

    monkeypatch.setattr(runtime_values, "evaluate_pure_expr", trace)
    assert evaluate_closed_program(restored, {}).value == expected
    assert observed == additions

    def nodes(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from nodes(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                yield from nodes(child)

    maps = [node for node in nodes(restored.tree) if node.get("k") == "list_map"]
    assert maps and all(node["body"]["k"] == "block" for node in maps)
    if not additions:
        assert maps[0]["body"]["body"]["k"] == "halt"


def test_prepared_map_scopes_free_names_substitution_and_use_site_renaming(tmp_path):
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
    from orchestrator.workflow_lisp.wcc.analysis import _referenced_wcc_names
    from orchestrator.workflow_lisp.wcc.elaborate import _substitute_wcc_value
    from orchestrator.workflow_lisp.wcc.hygiene import _free_names, _renamed
    from orchestrator.workflow_lisp.wcc.model import WccHalt, WccListMap, WccLiteralAtom
    from orchestrator.workflow_lisp.wcc.use_site_scope import rename_capturing_binders
    from tests.test_workflow_lisp_closed_command_requests import _prepared_entry
    from tests.test_workflow_lisp_closed_command_transport import _walk_wcc
    from tests.workflow_lisp_closed_program_helpers import install

    path = install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/map_scope) (export run)
      (defworkflow run ((items List[Int]) (offset Int)) -> List[Int]
        (list/map ((item items)) (+ item offset))))''')
    typed = compile_typed_program(path, entry_workflow="cp/map_scope::run",
        source_roots=(tmp_path,), command_boundaries={}, workspace_root=tmp_path)
    body, _, _ = _prepared_entry(typed)
    (mapping,) = [node for node in _walk_wcc(body) if isinstance(node, WccListMap)]
    assert _free_names(mapping) == _referenced_wcc_names(mapping) == {"items", "offset"}
    renamed = _renamed(mapping, {"item": "outside", "items": "incoming", "offset": "shift"})
    assert _free_names(renamed) == {"incoming", "shift"}
    assert _free_names(renamed.body) == {"item", "shift"}
    literal = WccLiteralAtom(metadata=mapping.body_metadata, value=9, literal_kind="int")
    replaced = _substitute_wcc_value(mapping, {"item": literal, "offset": literal})
    assert _free_names(replaced) == {"items"}
    assert _free_names(replaced.body) == {"item"}
    scoped, _ = rename_capturing_binders(WccHalt(metadata=mapping.metadata, result=mapping),
        live=frozenset({"item"}))
    assert scoped.result.binder_name != "item"
    assert _free_names(scoped) == {"items", "offset"}
    assert _free_names(scoped.result.body) == {scoped.result.binder_name, "offset"}


def test_public_map_result_runs_and_completed_resume_preserves_the_command_commit(tmp_path):
    import json
    from tests.test_workflow_evaluated_cli import _run_cli
    from tests.test_workflow_evaluated_invalidate import _tree_bytes
    from tests.workflow_evaluated_recovery_helpers import resume
    from tests.workflow_evaluated_totality_helpers import checked_run
    from tests.workflow_lisp_closed_program_helpers import install

    path = install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/public_map) (export run)
      (defrecord Result (numbers List[Int]) (count Int))
      (defworkflow run () -> Result
        (let* ((numbers (list/map ((item (list 1 2 3))) (+ item 100)))
               (count (command-result inc :argv ("python" "probe.py" (list/length numbers)) :returns Int)))
          (record Result :numbers numbers :count count))))''')
    (tmp_path / "probe.py").write_text('''import os, sys
from pathlib import Path
with Path("dispatches.txt").open("a") as stream:
    stream.write("inc\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(sys.argv[1])
''')
    boundaries = tmp_path / "boundaries.json"
    boundaries.write_text(json.dumps({"inc": {"stable_command": ["python", "probe.py"], "closure": ["probe.py"]}}))
    result = _run_cli(tmp_path, str(path), "--command-boundaries-file", str(boundaries))
    assert result.returncode == 0, result.stderr
    authority, snapshot = checked_run(tmp_path)
    assert snapshot.terminal.data["value"] == {"numbers": [101, 102, 103], "count": 3}
    assert len(snapshot.active_commits) == 1
    before = _tree_bytes(authority.run_root)
    resumed = resume(tmp_path, authority.run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert _tree_bytes(authority.run_root) == before
    assert (tmp_path / "dispatches.txt").read_text().splitlines() == ["inc"]
