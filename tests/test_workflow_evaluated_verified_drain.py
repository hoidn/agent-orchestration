"""Public evaluated route for the canonical verified drain copied to target 2.35."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_invalidate import _cli, _tree_bytes
from tests.test_workflow_evaluated_providers import workspace_relative
from tests.test_workflow_evaluated_resume import _resume_cli
from tests.test_workflow_lisp_verified_iteration_drain import FORMER_LINEAGE_PATHS, _assert_two_captured_histories


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "workflows/library/verified_iteration_drain/drain.orc"
ASSETS = (
    SOURCE,
    "workflows/library/scripts/prepare_verified_iteration.py",
    "workflows/library/scripts/run_verified_iteration_checks.py",
    "workflows/library/scripts/record_verified_iteration.py",
    "workflows/library/prompts/verified_iteration_drain/work.md",
    "workflows/library/prompts/verified_iteration_drain/review_iteration.md",
    "workflows/library/prompts/verified_iteration_drain/review_done.md",
)
MANIFESTS = ROOT / "workflows/examples/inputs/workflow_lisp_migrations"
ENTRY = "verified_iteration_drain/drain::drain"
WORK = "artifacts/work/verified"
TARGET = "docs/design/verified-target.md"
EXTERNAL_EDIT = b"EXTERNAL LEDGER EDIT\n"
INPUTS = (
    "--input", f"target_design_path={TARGET}",
    "--input", "check_commands_path=workflows/checks.json",
    "--input", "drain_state_root=state/verified",
    "--input", f"artifact_work_root={WORK}",
    "--input", "worker_provider=codex",
    "--input", "reviewer_provider=claude",
)

SHIM = r'''import hashlib, json, os, re, subprocess, sys
from pathlib import Path
raw = sys.stdin.buffer.read()
files = {match.group(1).decode(): raw[match.end():match.end() + int(match.group(2))]
         for match in re.finditer(rb"=== File: (\S+) \((\d+)/\d+ bytes\) ===\n", raw)}
order = json.loads(next(value for key, value in files.items() if key.endswith("/work-order.json")))
history = order["ledger_input_path"]
reviewing = any(key.endswith("/review-package.md") for key in files)
role = ("iteration_review" if reviewing else "worker") if history in files else "done_review"
log = Path("requests.jsonl")
calls = [row for row in map(json.loads, log.read_text().splitlines()) if row["role"] == role] if log.exists() else []
plan = json.loads(os.environ["DRAIN_SHIM_PLAN"])
failing = role == "worker" and len(calls) + 1 in plan.get("fail_worker_calls", [])
decision = None if failing else plan[role][sum(1 for row in calls if row["decision"])]
with log.open("a", encoding="utf-8") as out:
    out.write(json.dumps({"role": role, "iteration": order["iteration"], "decision": decision,
        "prompt": hashlib.sha256(raw).hexdigest(), "bundle": os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"],
        "files": {key: hashlib.sha256(value).hexdigest() for key, value in files.items()},
        "history": [history, files[history].decode()] if history in files else None}) + "\n")
if failing:
    sys.exit(9)
if role == "worker":
    Path(order["worker_verdict_path"]).write_text(decision + "\n")
    Path(order["worker_note_path"]).write_text(f"worker iteration {order['iteration']}\n")
    if int(order["iteration"]) in plan.get("commit", []):
        progress = f"docs/design/progress-{order['iteration']}.txt"
        Path(progress).write_text("progress\n")
        subprocess.run(["git", "add", "--", progress], check=True)
        subprocess.run(["git", "commit", "-q", "-m", "Fixture progress"], check=True)
else:
    key = "review_decision_path" if role == "iteration_review" else "done_review_decision_path"
    Path(order[key]).write_text(decision + "\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(decision) + "\n")
'''

STOP_AFTER_COMMIT = r'''import os, sys
from orchestrator.cli import main
from orchestrator.workflow.evaluated import runtime
append = runtime.append_record
def stop(path, record, **kwargs):
    entry = append(path, record, **kwargs)
    if record["record"] == "committed" and os.environ["STOP_AFTER_COMMIT"] in record["identity"]:
        os._exit(75)
    return entry
runtime.append_record = stop
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fixture(root: Path, monkeypatch, plan: dict[str, object]) -> list[str]:
    for relpath in ASSETS:
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relpath, root / relpath)
    source = (ROOT / SOURCE).read_text(encoding="utf-8")
    assert source.count('(:target-dsl "2.15")') == 1
    (root / SOURCE).write_text(source.replace('(:target-dsl "2.15")', '(:target-dsl "2.35")'), encoding="utf-8")
    (root / TARGET).parent.mkdir(parents=True)
    (root / TARGET).write_text("TARGET_BEFORE\n", encoding="utf-8")
    (root / "workflows/checks.json").write_text(json.dumps(["python -c 'raise SystemExit(0)'"]), encoding="utf-8")
    for argv in (["init", "-q"], ["config", "user.name", "Drain Fixture"],
                 ["config", "user.email", "drain-fixture@example.invalid"],
                 ["add", "--", "workflows", "docs"], ["commit", "-q", "-m", "Seed drain fixture"]):
        subprocess.run(["git", *argv], cwd=root, check=True)
    (root / "manifests").mkdir()
    commands = json.loads((MANIFESTS / "verified_iteration_drain.commands.json").read_text(encoding="utf-8"))
    for row in commands.values():
        row["closure"] = [row["stable_command"][1]]
    (root / "manifests/commands.json").write_text(json.dumps(commands), encoding="utf-8")
    for kind in ("providers", "prompts"):
        shutil.copyfile(MANIFESTS / f"verified_iteration_drain.{kind}.json", root / f"manifests/{kind}.json")
    (root / "bin").mkdir()
    for name in ("codex", "claude"):
        (root / "bin" / name).write_text(f"#!{sys.executable}\n" + SHIM, encoding="utf-8")
        (root / "bin" / name).chmod(0o700)
    monkeypatch.setenv("PATH", str(root / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("DRAIN_SHIM_PLAN", json.dumps(plan))
    return [str(root / SOURCE), "--entry-workflow", ENTRY, "--source-root", str(root / "workflows/library"),
            "--provider-externs-file", str(root / "manifests/providers.json"),
            "--prompt-externs-file", str(root / "manifests/prompts.json"),
            "--command-boundaries-file", str(root / "manifests/commands.json")]


def _memo(root: Path):
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    snapshot = read_memo(run_root / "memo.jsonl", site_classes(load_run_authority(run_root).program))
    return run_root, [entry.data for entry in snapshot.entries], snapshot


def _requests(root: Path) -> list[dict]:
    return [json.loads(row) for row in (root / "requests.jsonl").read_text(encoding="utf-8").splitlines()]


def _lineage(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for base in ("state/verified", WORK)
                  for path in (root / base).rglob("*") if path.is_file())


def _attempts(rows: list[dict], identity: str) -> list[int]:
    return [row["attempt"] for row in rows if row["record"] == "started" and row["identity"] == identity]


def _assert_read_lineage(snapshot, commit: dict, path: str, raw: bytes) -> None:
    (prepared,) = [identity for identity in commit["depends_on"] if identity.endswith(" / prepared")
                   and commit["identity"].startswith(identity.removesuffix("prepared"))]
    assert snapshot.active_commits[prepared].data["value"]["ledger_input_path"] == path
    assert commit["input_parts"][f"dependency:{path}"] == "sha256:" + _sha(raw)


def _history_reads(root: Path, run_root: Path, snapshot) -> list[tuple[str, bytes] | None]:
    """Check each provider's actual history read against its file, commit digest and Prepare value."""
    commits = {os.path.relpath(run_root / entry.data["result_path"], root): entry.data
               for entry in snapshot.entries if entry.data["record"] == "committed"}
    reads = []
    for request in _requests(root):
        assert os.path.isabs(request["bundle"])
        if request["history"] is None:
            reads.append(None)
            continue
        path, raw = request["history"][0], request["history"][1].encode("utf-8")
        assert path == f"{WORK}/ledger-inputs/{_sha(raw)}.md" and (root / path).read_bytes() == raw
        commit = commits.get(workspace_relative(request["bundle"], root))
        assert (commit is None) == (request["decision"] is None)
        if commit is not None:
            _assert_read_lineage(snapshot, commit, path, raw)
        reads.append((path, raw))
    return reads


def _assert_completed_resume_is_readonly(root: Path, run_root: Path) -> None:
    before = _tree_bytes(root)
    for _ in range(2):
        resumed = _resume_cli(root, run_root.name)
        assert resumed.returncode == 0, resumed.stderr
        assert _tree_bytes(root) == before


def test_public_drain_continue_then_done_reads_two_captured_histories(tmp_path, monkeypatch):
    frontend = _fixture(tmp_path, monkeypatch, {"worker": ["CONTINUE", "DONE"], "iteration_review": ["APPROVE"],
                                                "done_review": ["APPROVE"], "commit": [0]})
    compiled = _cli(tmp_path, "compile", *frontend)
    assert compiled.returncode == 0, compiled.stderr
    result = _run_cli(tmp_path, *frontend, *INPUTS)
    assert result.returncode == 0, result.stderr
    run_root, rows, snapshot = _memo(tmp_path)
    assert snapshot.terminal.data["value"] == {"drain_status": "DONE", "drain_summary_path": f"{WORK}/drain-summary.json"}
    assert [(row["role"], row["iteration"]) for row in _requests(tmp_path)] == [
        ("worker", "0"), ("iteration_review", "0"), ("worker", "1"), ("done_review", "1")]
    histories = _assert_two_captured_histories(tmp_path, _history_reads(tmp_path, run_root, snapshot))
    ledger = (tmp_path / WORK / "ledger.md").read_text(encoding="utf-8")
    assert [line.split(" | ")[:2] for line in ledger.splitlines() if line.startswith("iter ")] == [
        ["iter 0", "ACCEPTED"], ["iter 1", "DONE"]]
    assert _lineage(tmp_path) == sorted({*FORMER_LINEAGE_PATHS, *histories})
    assert len(_lineage(tmp_path)) == 21
    _assert_completed_resume_is_readonly(tmp_path, run_root)


def _failed_work_cannot_be_invalidated(root: Path, frontend: list[str]) -> tuple[Path, str]:
    assert _run_cli(root, *frontend, *INPUTS).returncode != 0
    run_root, rows, _snapshot = _memo(root)
    (failure,) = [row for row in rows if row["record"] == "failed"]
    before = _tree_bytes(root)
    refused = _cli(root, "invalidate", run_root.name, failure["identity"])
    assert refused.returncode == 2 and "invalidate_not_committed" in refused.stderr
    assert _tree_bytes(root) == before
    return run_root, failure["identity"]


def test_public_work_retry_keeps_the_prepare_selected_history(tmp_path, monkeypatch):
    frontend = _fixture(tmp_path, monkeypatch, {"worker": ["DONE"], "done_review": ["APPROVE"],
                                                "fail_worker_calls": [1]})
    run_root, failed_work = _failed_work_cannot_be_invalidated(tmp_path, frontend)
    ledger = tmp_path / WORK / "ledger.md"
    ledger.write_bytes(ledger.read_bytes() + EXTERNAL_EDIT)
    (tmp_path / TARGET).write_text("TARGET_AFTER\n", encoding="utf-8")
    resumed = _resume_cli(tmp_path, run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    run_root, rows, snapshot = _memo(tmp_path)
    requests = _requests(tmp_path)
    assert [(row["role"], row["decision"]) for row in requests] == [
        ("worker", None), ("worker", "DONE"), ("done_review", "APPROVE")]
    assert _attempts(rows, failed_work) == [1, 2]
    first, retry, _done = _history_reads(tmp_path, run_root, snapshot)
    assert retry == first and EXTERNAL_EDIT not in retry[1]
    assert [row["files"][TARGET] for row in requests[:2]] == [_sha(b"TARGET_BEFORE\n"), _sha(b"TARGET_AFTER\n")]
    prior_prompt = (tmp_path / requests[0]["bundle"]).parent / "prompt.txt"
    assert _sha(prior_prompt.read_bytes()) == requests[0]["prompt"]
    assert ledger.read_bytes().startswith(first[1] + EXTERNAL_EDIT)
    _assert_completed_resume_is_readonly(tmp_path, run_root)


def test_public_completed_resume_refuses_a_changed_or_missing_captured_history(tmp_path, monkeypatch):
    frontend = _fixture(tmp_path, monkeypatch, {"worker": ["DONE"], "done_review": ["APPROVE"]})
    assert _run_cli(tmp_path, *frontend, *INPUTS).returncode == 0
    run_root, _rows, snapshot = _memo(tmp_path)
    (path, raw), _done = _history_reads(tmp_path, run_root, snapshot)
    copy = tmp_path / path
    for change in (lambda: copy.write_bytes(raw + b"tampered\n"), copy.unlink):
        change()
        before = _tree_bytes(tmp_path)
        refused = _resume_cli(tmp_path, run_root.name)
        assert refused.returncode == 2 and "effect_input_diverged" in refused.stderr
        assert _tree_bytes(tmp_path) == before
    copy.write_bytes(raw)
    _assert_completed_resume_is_readonly(tmp_path, run_root)


def _stopped_after_commit(root: Path, frontend: list[str], marker: str) -> tuple[Path, list[dict], int]:
    """Stop the public run abruptly right after the first commit whose identity contains marker."""
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", "STOP_AFTER_COMMIT": marker}
    stopped = subprocess.run([sys.executable, "-c", STOP_AFTER_COMMIT, "run", *frontend, *INPUTS],
                             cwd=root, env=env, capture_output=True, text=True, check=False)
    assert stopped.returncode == 75, stopped.stderr
    run_root, rows, snapshot = _memo(root)
    assert rows[-1]["record"] == "committed" and marker in rows[-1]["identity"]
    assert not snapshot.pending_starts and not snapshot.unsettled_coordinators and snapshot.terminal is None
    return run_root, rows, snapshot.active_commits[rows[-1]["identity"]].offset


def _invalidate(root: Path, run_root: Path, identity: str, offset: int) -> None:
    invalidated = _cli(root, "invalidate", run_root.name, identity)
    assert invalidated.returncode == 0, invalidated.stderr
    assert json.loads(invalidated.stdout)["from_commit"] == offset


@pytest.mark.parametrize("recapture", [False, True])
def test_public_prepare_boundary_resume_keeps_history_unless_prepare_is_invalidated(tmp_path, monkeypatch, recapture):
    frontend = _fixture(tmp_path, monkeypatch, {"worker": ["DONE"], "done_review": ["APPROVE"]})
    run_root, rows, offset = _stopped_after_commit(tmp_path, frontend, " / prepared")
    assert [(row["record"], row["identity"].rsplit(" / ", 1)[-1]) for row in rows] == [
        ("started", "prepared"), ("committed", "prepared")]
    assert not (tmp_path / "requests.jsonl").exists()
    prepared = rows[1]
    original = (tmp_path / prepared["value"]["ledger_input_path"]).read_bytes()
    ledger = tmp_path / WORK / "ledger.md"
    ledger.write_bytes(ledger.read_bytes() + EXTERNAL_EDIT)
    if recapture:
        _invalidate(tmp_path, run_root, prepared["identity"], offset)
    resumed = _resume_cli(tmp_path, run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    run_root, rows, snapshot = _memo(tmp_path)
    work_read, _done = _history_reads(tmp_path, run_root, snapshot)
    selected = original + EXTERNAL_EDIT if recapture else original
    assert (_attempts(rows, prepared["identity"]), work_read) == (
        [1, 2] if recapture else [1], (f"{WORK}/ledger-inputs/{_sha(selected)}.md", selected))
    assert (tmp_path / prepared["value"]["ledger_input_path"]).read_bytes() == original
    _assert_completed_resume_is_readonly(tmp_path, run_root)


def test_public_invalidating_committed_work_alone_keeps_prepare_and_its_history(tmp_path, monkeypatch):
    frontend = _fixture(tmp_path, monkeypatch, {"worker": ["DONE", "DONE"], "done_review": ["APPROVE"]})
    run_root, rows, offset = _stopped_after_commit(tmp_path, frontend, "::invoke-worker")
    work = rows[-1]
    (prepared,) = {row["identity"] for row in rows if row["identity"].endswith(" / prepared")}
    ledger = tmp_path / WORK / "ledger.md"
    ledger.write_bytes(ledger.read_bytes() + EXTERNAL_EDIT)
    _invalidate(tmp_path, run_root, work["identity"], offset)
    resumed = _resume_cli(tmp_path, run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    run_root, rows, snapshot = _memo(tmp_path)
    assert (_attempts(rows, prepared), _attempts(rows, work["identity"])) == ([1], [1, 2])
    first, retry, _done = _history_reads(tmp_path, run_root, snapshot)
    assert retry == first and EXTERNAL_EDIT not in retry[1]
    _assert_completed_resume_is_readonly(tmp_path, run_root)
