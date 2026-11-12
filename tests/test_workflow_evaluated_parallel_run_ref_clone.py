"""A parallel item's run-reference child keeps outer authority and runs in its own clone.

Phase 5 Task 3, the D2 coordinator exception: a path run reference keeps the outer workspace as its
`parent_workspace` (a typed path input is copied from there, never from the item directory) and its
child executes in its own clone workspace. A path-mode child is effect-free (a command in it refuses with
`trial_candidate_environment_not_admissible`), so what it can read is its program and its typed inputs.
Each item directory and the parent workspace hold a decoy `candidate.orc` that answers the opposite of the
committed candidate; every child must compile the committed candidate in its own clone below the
run-reference root and record its run there, on a fresh run and on a resume after a kill.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.workflow_evaluated_parallel_kill_helpers import Batch, child_launches, committed, item_of
from tests.workflow_evaluated_recovery_helpers import digest, resume


ITEMS = ("a", "b")
EXPECTED = {"a": True, "b": False}  # the committed candidate answers `(= item "a")`
DECOY = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule candidate) (export run)
  (defworkflow run ((item String)) -> Bool (= item "b")))
'''
INVOKE = '(defworkflow invoke ((repo String)) -> Bool (let* ((child CALL)) child.value))'
MAP = ('(list/map-effect ((repo (list "a" "b"))) :max 2 :parallel 2 :workspace repo '
       '(call invoke :repo repo))')


def _batch(root: Path) -> Batch:
    from tests.test_workflow_evaluated_run_ref import _public_fixture
    root.mkdir(parents=True)
    parent, source, refs = _public_fixture(root, parent_target="2.37", inputs="(item String)",
        call_inputs=":item repo", child_body='(= item "a")', definitions=lambda call: INVOKE.replace("CALL", call),
        body=lambda _call: f"(let* ((items {MAP})) (= (list/length items) 2))")
    batch = Batch(root, source=None, items=ITEMS, ws=parent,
                  run_args=(str(source), "--run-ref-root", str(refs)), refs=refs)
    for directory in (parent, *(parent / item for item in ITEMS)):
        (directory / "candidate.orc").write_text(DECOY)
    return batch


def _children(batch: Batch) -> list[tuple[str, Path, str]]:
    """(item, clone root, child run id) of every child request the run wrote."""
    requests = [json.loads(path.read_text()) for path in batch.refs.rglob("child-request.json")]
    return [(request["inputs"]["item"], Path(request["clone_root"]), request["child_run_id"]) for request in requests]


def _assert_children_ran_in_their_clones(batch: Batch) -> None:
    candidate = (batch.ws.parent / "candidate" / "candidate.orc").read_bytes()
    children = _children(batch)
    assert {item for item, _clone, _run in children} == set(ITEMS)
    assert len({clone for _item, clone, _run in children}) == len(children)
    for _item, clone, _run in children:
        assert clone.is_relative_to(batch.refs) and not clone.is_relative_to(batch.ws)
        assert (clone / "candidate.orc").read_bytes() == candidate
    _assert_last_child_recorded_its_run_in_its_clone(children)


def _assert_last_child_recorded_its_run_in_its_clone(children: list[tuple[str, Path, str]]) -> None:
    for item in ITEMS:
        *_, (_, clone, run_id) = [child for child in children if child[0] == item]
        assert (clone / ".orchestrate" / "runs" / run_id / "memo.jsonl").is_file()


def _assert_values(batch: Batch) -> None:
    snapshot = batch.snapshot()
    assert snapshot.terminal.data["value"] is True and not snapshot.unsettled_coordinators
    values = {item_of(row["identity"]): row["value"]["value"] for row in committed(snapshot)
              if row["effect_class"] == "run_ref"}
    assert values == EXPECTED


def _identity(root: Path, item: str) -> str:
    baseline = _batch(root)
    assert baseline.run().returncode == 0
    (identity,) = [row["identity"] for row in committed(baseline.snapshot()) if item_of(row["identity"]) == item]
    return identity


def test_parallel_run_ref_children_compile_in_their_own_clones_on_run(tmp_path):
    batch = _batch(tmp_path / "fresh")
    result = batch.run()
    assert result.returncode == 0, result.stdout + result.stderr
    _assert_values(batch)
    _assert_children_ran_in_their_clones(batch)


@pytest.mark.parametrize("window", ["W2", "W9"], ids=["start_reservation", "commit_before_settle"])
def test_parallel_run_ref_children_compile_in_their_own_clones_after_kill_and_resume(tmp_path, window):
    identity = _identity(tmp_path / "baseline", "b")
    batch = _batch(tmp_path / "killed")
    batch.kill((), window={"window": window, "identity": identity, "attempt": 1, "digest": digest(identity)})
    killed = batch.snapshot()
    assert killed.terminal is None
    if window == "W2":
        assert identity in killed.pending_starts
    else:
        assert [key for key, _attempt in killed.unsettled_coordinators] == [identity]
    resumed = resume(batch.ws, batch.run_root().name)
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    _assert_values(batch)
    _assert_children_ran_in_their_clones(batch)
    assert child_launches(batch) == len(ITEMS)  # one child per item: no committed child launches again


COMMON = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule common)
  (export WorkPath) (defpath WorkPath :kind relpath :under "artifacts" :must-exist true))'''
IMPORT = "(import common :only (WorkPath))"
INVOKE_PATH = ('(defworkflow invoke ((repo String) (payload WorkPath)) -> WorkPath '
               '(let* ((child CALL)) child.value))')
MAP_PATH = ('(list/map-effect ((repo (list "a" "b"))) :max 2 :parallel 2 :workspace repo '
            '(call invoke :repo repo :payload payload))')


def test_parallel_run_ref_children_copy_path_inputs_from_the_outer_workspace(tmp_path):
    """Each child's copy of a `WorkPath` input holds the outer workspace's bytes, not its item's."""
    from tests.test_workflow_evaluated_cli import _run_cli
    from tests.test_workflow_evaluated_run_ref import _add_common_source, _public_fixture
    parent, source, refs = _public_fixture(tmp_path, parent_target="2.37", imports=IMPORT, child_imports=IMPORT,
        parameters="(payload WorkPath)", inputs="(payload WorkPath)", call_inputs=":payload payload",
        child_body="payload", returns="WorkPath", definitions=lambda call: INVOKE_PATH.replace("CALL", call),
        body=lambda _call: f"(let* ((items {MAP_PATH})) (= (list/length items) 2))")
    _add_common_source(parent, source, tmp_path / "candidate", COMMON)
    for directory, text in ((parent, "outer"), (parent / "a", "item a"), (parent / "b", "item b")):
        (directory / "artifacts").mkdir(parents=True)
        (directory / "artifacts" / "seed.txt").write_text(text)
    result = _run_cli(parent, str(source), "--input", "payload=artifacts/seed.txt", "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stdout + result.stderr
    requests = [json.loads(path.read_text()) for path in refs.rglob("child-request.json")]
    assert len(requests) == len(ITEMS)
    copies = [(Path(request["clone_root"]) / request["inputs"]["payload"]).read_text() for request in requests]
    assert copies == ["outer"] * len(ITEMS)
