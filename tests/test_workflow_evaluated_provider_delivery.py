"""The contract block a new evaluated provider attempt renders, and the missing-result reply excerpt
(docs/design/provider_result_delivery.md)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from orchestrator.contracts.prompt_contract import _RELPATH_GUIDANCE
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.test_workflow_evaluated_providers import _cli, _fixture, _public_snapshot, _requests
from tests.test_workflow_evaluated_resume_kills import _cli as _env_cli, _env


_REPLY = json.dumps("Here is the move:\n\n   " + "e2e4 " * 80)


def _contract_lines(prompt, result_path):
    lines = prompt.splitlines()
    format_at = next(index for index, line in enumerate(lines) if line.startswith("  format: "))
    assert lines.count("## Output Contract") == 1
    assert lines.count(f"- path: {result_path}") == 1
    assert lines.index("## Output Contract") < lines.index(f"- path: {result_path}") < format_at
    return lines


def test_public_provider_prompt_renders_the_file_delivery_contract_once(tmp_path):
    fixture = _fixture(tmp_path)
    assert _cli(tmp_path, fixture).returncode == 0
    run_root, snapshot = _public_snapshot(tmp_path, fixture)
    (commit,) = snapshot.active_commits.values()
    prompt = (run_root / Path(commit.data["result_path"]).parent / "prompt.txt").read_text()
    lines = _contract_lines(prompt, os.path.relpath(run_root / commit.data["result_path"], tmp_path))
    assert _RELPATH_GUIDANCE not in lines
    assert commit.data["input_parts"]["delivery"] == canonical_sha256("file/1")


def test_public_omp_provider_records_the_legacy_delivery_rendering(tmp_path):
    """omp children never receive the bundle path, so their attempts keep `legacy`. Preparation refuses the
    `effort` policy for omp, and a failing `omp` shim heads PATH, so the real omp can never launch."""
    fixture = _fixture(tmp_path)
    fixture[1].write_text(json.dumps({"providers.review": "omp"}), encoding="utf-8")
    omp = tmp_path / "bin" / "omp"
    omp.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
    omp.chmod(0o700)
    assert _cli(tmp_path, fixture).returncode == 1
    run_root, snapshot = _public_snapshot(tmp_path, fixture)
    started, failed = [entry.data for entry in snapshot.entries][:2]
    assert failed["code"] == "provider_preparation_failed" and not _requests(tmp_path)
    assert started["input_parts"]["delivery"] == canonical_sha256("legacy")
    prompt = (run_root / Path(started["result_path"]).parent / "prompt.txt").read_text()
    assert _RELPATH_GUIDANCE in _contract_lines(prompt, os.path.relpath(run_root / started["result_path"], tmp_path))


@pytest.mark.parametrize(("mode", "head"), [
    ("stdout-only", " ".join(f"complete stdout\n{_REPLY}".split())[:240]),
    ("nul", "I wrote it here [31mred [0m"),
    ("silent", None),
])
def test_public_missing_result_names_the_reply_head_and_resume_retries(tmp_path, mode, head):
    """Design scenario 2: the reply is diagnostic text only, with non-printable bytes (NUL, ANSI escapes)
    blanked; nothing commits, `report` reads the run and resume dispatches attempt 2."""
    fixture = _fixture(tmp_path)
    assert _cli(tmp_path, fixture, mode=mode, payload=_REPLY).returncode == 1
    run_root, snapshot = _public_snapshot(tmp_path, fixture)
    started, failed, terminal = [entry.data for entry in snapshot.entries]
    result_path = os.path.relpath(run_root / started["result_path"], tmp_path)
    assert failed["code"] == terminal["code"] == "provider_result_missing"
    assert failed["exit_info"] == {} and not snapshot.active_commits
    suffix = "" if head is None else f"; reply began: {head}"
    assert terminal["message"] == f"provider did not create {result_path}{suffix}"
    report = _env_cli(tmp_path, ["report", "--run-id", run_root.name, "--runs-root",
        str(run_root.parent), "--format", "json"], _env(tmp_path))
    assert report.returncode == 0, report.stderr
    assert json.loads(report.stdout)["run"]["error"]["message"] == terminal["message"]

    resumed = _env_cli(tmp_path, ["resume", run_root.name], _env(tmp_path, provider=True))

    assert resumed.returncode == 0, resumed.stderr
    after = _public_snapshot(tmp_path, fixture)[1]
    assert [entry.data["attempt"] for entry in after.entries if entry.data["record"] == "started"] == [1, 2]
    assert [commit.data["attempt"] for commit in after.active_commits.values()] == [2]
    assert len(_requests(tmp_path)) == 2
