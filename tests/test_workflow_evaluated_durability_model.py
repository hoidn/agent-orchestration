"""Bounded persistence model for evaluated run authority.

These tests are distinct from the SIGKILL recovery tests. The recorder captures
the real public run's operations through its first dispatch; every boundary is
recovered twice, once with every unsynchronized change surviving and once with
all of them lost, and the public loader and resume run over each recovered
image with the original sources and a dispatch log kept outside the image.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.cli.main import main
from orchestrator.workflow.evaluated.authority import RunAuthorityError, load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.workflow_evaluated_durability_helpers import (
    cli_env, crash_points, dispatch_log, dispatches, image_digest, materialize,
    operation_counts, record_public_run, write_workspace,
)


TOPOLOGIES = ["new-ancestors", "preexisting-roots"]


def _template(root: Path, topology: str) -> tuple[Path, list[str]]:
    """A pristine workspace; the preexisting topology already holds a completed run."""
    workspace = root / "template" / "ws"
    argv = write_workspace(workspace)
    if topology == "preexisting-roots":
        prior = subprocess.run([sys.executable, "-m", "orchestrator", *argv], cwd=workspace,
                               env=cli_env(), capture_output=True, text=True, check=False, timeout=120)
        assert prior.returncode == 0, prior.stderr
        assert (workspace / ".orchestrate" / "runs").is_dir()
        dispatch_log(workspace).unlink()
    return workspace, argv


def _copy(template: Path, root: Path) -> Path:
    workspace = root / "ws"
    shutil.copytree(template, workspace, symlinks=True)
    return workspace


def _run_id(trace: list[dict]) -> str:
    (run_id,) = {
        op["path"].split("/")[2] for op in trace
        if op["op"] == "mkdir" and "error" not in op
        and op["path"].startswith(".orchestrate/runs/") and op["path"].count("/") == 2
    }
    return run_id


def _journal(workspace: Path, run_id: str) -> tuple[bool, list[dict], dict | None]:
    """Valid authority, started rows and terminal row as the public loader reads them."""
    try:
        authority = load_run_authority(workspace / ".orchestrate" / "runs" / run_id)
    except RunAuthorityError:
        return False, [], None
    memo = read_memo(authority.memo_path, site_classes(authority.program))
    starts = [entry.data for entry in memo.entries if entry.data["record"] == "started"]
    return True, starts, memo.terminal.data if memo.terminal else None


def _journal_lines(workspace: Path, run_id: str) -> int:
    memo = workspace / ".orchestrate" / "runs" / run_id / "memo.jsonl"
    return memo.read_bytes().count(b"\n") if memo.is_file() else 0


def _stable(workspace: Path, run_id: str) -> dict:
    """The whole image without the lock files that a public resume may create."""
    locks = {".orchestrate/workspace.lock", ".orchestrate/workspace.guard",
             f".orchestrate/runs/{run_id}/run.lock"}
    return {key: node for key, node in _tree_bytes(workspace).items() if key not in locks}


def _record(root: Path, topology: str):
    template, argv = _template(root, topology)
    workspace = _copy(template, root / "recorded")
    result, trace = record_public_run(workspace, root / "recorded" / "control", argv)
    assert result.returncode == 0, result.stderr
    run_id = _run_id(trace)
    _valid, _starts, terminal = _journal(workspace, run_id)
    assert terminal is not None and terminal["outcome"] == "completed"
    return template, argv, trace, run_id, terminal["value"]


@pytest.fixture
def public_resume(monkeypatch, capsys, caplog):
    def resume(workspace: Path, run_id: str) -> tuple[int, str]:
        caplog.clear()
        capsys.readouterr()
        with monkeypatch.context() as patch:
            patch.chdir(workspace)
            code = main(["resume", run_id])
        captured = capsys.readouterr()
        return code, captured.out + captured.err + caplog.text
    return resume


def _assert_dispatch_was_durable(workspace: Path, run_id: str, valid: bool, starts: list[dict]) -> None:
    assert valid and starts, "a dispatch happened without durable authority and started record"
    attempt = (workspace / ".orchestrate" / "runs" / run_id / starts[-1]["result_path"]).parent
    assert attempt.is_dir(), "a dispatch happened before its attempt directory was durable"


def _assert_resumed(workspace, run_id, starts, before, expected, code, output) -> None:
    assert code == 0, output
    _valid, after_starts, terminal = _journal(workspace, run_id)
    assert terminal == {"record": "terminal", "outcome": "completed", "value": expected}
    assert [row["attempt"] for row in after_starts] == list(range(1, len(starts) + 2))
    assert dispatches(workspace) == 1
    after = _stable(workspace, run_id)
    effects = f".orchestrate/runs/{run_id}/effects/"
    prior = {key: node for key, node in before.items() if key.startswith(effects)}
    assert {key: after.get(key) for key in prior} == prior


def _assert_refused(workspace, run_id, before, lines, code, output) -> str:
    assert code != 0, output
    assert dispatches(workspace) == 0
    assert _stable(workspace, run_id) == before
    if lines:
        assert "memo_inconsistent" in output, output
    return "refused memo_inconsistent" if "memo_inconsistent" in output else f"refused exit {code}"


def _check_image(image: dict, dispatched: int, workspace: Path, run_id: str, expected, resume) -> str:
    materialize(image, workspace)
    valid, starts, _terminal = _journal(workspace, run_id)
    lines = _journal_lines(workspace, run_id)
    if dispatched:
        _assert_dispatch_was_durable(workspace, run_id, valid, starts)
    assert valid or not lines, "journal records survived without valid authority"
    before = _stable(workspace, run_id)
    code, output = resume(workspace, run_id)
    if valid:
        _assert_resumed(workspace, run_id, starts, before, expected, code, output)
        return f"resumed after {len(starts)} durable start(s)"
    return _assert_refused(workspace, run_id, before, lines, code, output)


def _assert_model_separates_visibility(points, run_id: str) -> None:
    root = f".orchestrate/runs/{run_id}"

    def lags(rel: str) -> bool:
        return any(rel in point.visible and rel not in point.durable for point in points)

    assert lags(root) and lags(f"{root}/closed_program.json") and lags(f"{root}/run.json")
    memo = f"{root}/memo.jsonl"
    assert any(memo in point.durable and point.visible[memo] != point.durable[memo] for point in points)


def _assert_one_pending_run_root_change(points, run_id: str) -> None:
    """The two extremes cover every subset only while one run-root entry is unsynchronized."""
    prefix = f".orchestrate/runs/{run_id}/"
    for point in points:
        pending = {
            rel[len(prefix):].split("/")[0] for rel in point.visible.keys() | point.durable.keys()
            if rel.startswith(prefix) and point.visible.get(rel) != point.durable.get(rel)
        } - {"run.lock"}
        assert len(pending) <= 1, (
            f"{point.label}: unsynchronized run-root entries {sorted(pending)} are pending together; "
            "the all-survive/all-lost images no longer cover their subsets, so subsets must be enumerated"
        )


def _receipt(root: Path, topology: str, trace, points, cells, outcomes) -> None:
    summary: dict[str, int] = {}
    for outcome in outcomes.values():
        summary[outcome] = summary.get(outcome, 0) + 1
    (root / "model-receipt.json").write_text(json.dumps({
        "topology": topology, "operations": operation_counts(trace),
        "crash_points": len(points), "cells": len(cells), "distinct_images": len(outcomes),
        "image_outcomes": summary, "dispatch_point": points[-1].label, "cell_rows": cells,
    }, indent=1), encoding="utf-8")


@pytest.mark.parametrize("topology", TOPOLOGIES)
def test_authority_survives_loss_of_unsynced_writes(tmp_path, topology, public_resume):
    _template_root, _argv, trace, run_id, expected = _record(tmp_path, topology)
    points = crash_points(trace)
    succeeded = sum(1 for op in trace[:-1] if "error" not in op)
    assert len(points) == 2 * succeeded + (len(trace) - 1 - succeeded) + 1
    assert points[-1].dispatched == 1 and all(not point.dispatched for point in points[:-1])
    outcomes: dict[tuple[str, bool], str] = {}
    cells = []
    for point in points:
        for variant in ("visible", "durable"):
            image = getattr(point, variant)
            key = (image_digest(image), bool(point.dispatched))
            if key not in outcomes:
                workspace = tmp_path / "images" / f"{len(outcomes):03d}" / "ws"
                outcomes[key] = _check_image(image, point.dispatched, workspace, run_id, expected, public_resume)
            cells.append({"point": point.label, "variant": variant, "dispatched": point.dispatched,
                          "image": key[0][:16], "outcome": outcomes[key]})
    _receipt(tmp_path, topology, trace, points, cells, outcomes)
    _assert_model_separates_visibility(points, run_id)
    _assert_one_pending_run_root_change(points, run_id)
    assert outcomes[(image_digest(points[-1].durable), True)] == "resumed after 1 durable start(s)"


def _truncate_half(path: Path) -> None:
    path.write_bytes(path.read_bytes()[: path.stat().st_size // 2])


_LOSSES = {
    "header-missing": lambda root: (root / "run.json").unlink(),
    "program-missing": lambda root: (root / "closed_program.json").unlink(),
    "header-partial": lambda root: _truncate_half(root / "run.json"),
}


@pytest.mark.parametrize("topology", TOPOLOGIES)
def test_lost_authority_with_journal_refuses_without_reconstruction_or_launch(tmp_path, topology, public_resume):
    _template_root, _argv, trace, run_id, _expected = _record(tmp_path, topology)
    points = crash_points(trace)
    header = f".orchestrate/runs/{run_id}/run.json"
    published = next(point.durable for point in points if header in point.durable)
    cases = [(name, points[-1].durable, loss) for name, loss in _LOSSES.items()]
    cases.append(("header-partial-empty-journal", published, _LOSSES["header-partial"]))
    for name, image, loss in cases:
        workspace = tmp_path / "losses" / name / "ws"
        materialize(image, workspace)
        loss(workspace / ".orchestrate" / "runs" / run_id)
        lines = _journal_lines(workspace, run_id)
        assert bool(lines) == (name != "header-partial-empty-journal")
        before = _stable(workspace, run_id)
        code, output = public_resume(workspace, run_id)
        assert code == 2 and "memo_inconsistent" in output, (name, output)
        assert dispatches(workspace) == 0
        assert _stable(workspace, run_id) == before


def _assert_failed_sync(workspace: Path, result, failed_trace, expected_kind: str) -> None:
    (failure,) = [op for op in failed_trace if op["op"] == "fsync" and "error" in op]
    assert failure["kind"] == expected_kind
    assert result.returncode == 1, result.stderr
    assert "injected fsync failure" in result.stderr
    assert dispatches(workspace) == 0
    for run_root in (workspace / ".orchestrate" / "runs").iterdir():
        if _journal_lines(workspace, run_root.name):
            assert _journal(workspace, run_root.name)[0], "journal rows without valid authority"


_POST_PUBLICATION_CODE = re.compile(r"\[(memo_sync_failed|view_write_failed|effect_attempt_allocation_failed)\]")


def _assert_post_publication_code(workspace: Path, template: Path, result) -> bool:
    """Once the failed run's journal holds a record, its sync failure carries a named code."""
    prior = {path.name for path in (template / ".orchestrate" / "runs").glob("*")}
    failed = [path.name for path in (workspace / ".orchestrate" / "runs").iterdir() if path.name not in prior]
    if not any(_journal_lines(workspace, name) for name in failed):
        return False
    assert _POST_PUBLICATION_CODE.search(result.stderr), result.stderr
    return True


@pytest.mark.parametrize("topology", TOPOLOGIES)
def test_public_sync_failure_aborts_before_dispatch(tmp_path, topology):
    template, argv, trace, _run_id_value, _expected = _record(tmp_path, topology)
    syncs = [op for op in trace if op["op"] == "fsync"]
    assert syncs and all("error" not in op for op in syncs)
    named = 0
    for ordinal, synced in enumerate(syncs, start=1):
        case = tmp_path / f"fail-{ordinal:02d}"
        workspace = _copy(template, case)
        result, failed_trace = record_public_run(workspace, case / "control", argv, fail_fsync=ordinal)
        _assert_failed_sync(workspace, result, failed_trace, synced["kind"])
        named += _assert_post_publication_code(workspace, template, result)
    assert named, "no sync failure happened after the first journal record"
