"""A result file is absent before every command and provider call (plan Task 8).

Contract: `specs/io.md`, command and provider structured-bundle environment.
A call delivers its result as a JSON file at `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
A file left at that path by an earlier iteration, an earlier run or an
interrupted call is never read as the result of a new call: a call that writes
nothing fails with the existing `missing_bundle_file` contract violation.
Clearing the path never acts outside the workspace, and a path that cannot be
cleared fails the call before launch with `stale_bundle_removal_failed`.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.workflow.workspace_files import WorkspaceFiles


def test_a_stale_file_on_an_ordinary_nested_bundle_path_is_removed(tmp_path: Path) -> None:
    stale = tmp_path / "a" / "b" / "result.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")
    files = WorkspaceFiles(tmp_path)
    try:
        error = files.clear("a/b/result.json")
    finally:
        files.close()

    assert (error, stale.exists()) == (None, False)


def test_a_bundle_path_whose_last_component_is_a_link_removes_the_link_and_not_its_target(tmp_path: Path) -> None:
    target = tmp_path / "kept.json"
    target.write_text("kept", encoding="utf-8")
    link = tmp_path / "a" / "result.json"
    link.parent.mkdir()
    link.symlink_to(target)
    files = WorkspaceFiles(tmp_path)
    try:
        error = files.clear("a/result.json")
    finally:
        files.close()

    assert (error, link.is_symlink(), target.read_text(encoding="utf-8")) == (None, False, "kept")
