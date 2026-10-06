"""Public freshness of artifact handoffs at 2.35: suffix invalidation, required result paths,
pure replay of committed paths, and the verified drain's command requests against the old route.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil

from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_invalidate import _cli, _tree_bytes
from tests.test_workflow_evaluated_invalidate_smoke import _attempt_files
from tests.test_workflow_evaluated_resume import _resume_cli
import tests.test_workflow_evaluated_verified_drain as drain
from tests.workflow_evaluated_artifact_helpers import attempt_files, rows, small_program
from tests.workflow_evaluated_consumer_sources import (
    EXEC_LOG, FUTURE, checked_run, jsonl, requests, sha256, stop_after,
)


def _log(root: Path, name: str) -> list:
    return jsonl(root / f"{name}.log")


# C8: invalidating the consumer reruns the whole later suffix ----------------------------

SUFFIX = '''  (defpath Note :kind relpath :under "artifacts" :must-exist true)
  (defrecord Verdict (ok Bool))
  (defrecord Out (ok Bool) (later String))
  (defworkflow run ((message String)) -> Out
    (let* ((note (command-result produce :argv ("python" "produce.py") :returns Note))
           (review (provider-result providers.review :prompt prompts.base :inputs (message)
                     :prompt-dependencies (:required (note)) :returns Verdict))
           (later (command-result later :argv ("python" "later.py" message) :returns String)))
      (record Out :ok review.ok :later later))))'''
NOTE_PART = "dependency:artifacts/note.md"


def _evidence(authority, entries) -> dict[str, dict[str, bytes]]:
    return {entry.data["identity"]: _attempt_files(authority.run_root, entry) for entry in entries}


def _assert_suffix_reran(root: Path, authority, entries: tuple, evidence: dict) -> None:
    """Only the canceled suffix ran again and read the current bytes; every attempt-1 file is intact."""
    _note, review, _later = entries
    _, after = checked_run(root)
    assert [[row["attempt"] for row in rows(root, "started", entry.data["identity"])] for entry in entries] == [
        [1], [1, 2], [1, 2]]
    assert after.active_commits[review.data["identity"]].data["input_parts"][NOTE_PART] == sha256("NOTE v2\n")
    assert after.terminal.data["value"] == {"ok": True, "later": "NOTE v2\n"}
    assert (len(_log(root, "produce")), len(_log(root, "later")), len(requests(root))) == (1, 2, 2)
    assert _evidence(authority, entries) == evidence


def test_public_invalidating_the_consumer_reruns_its_whole_later_suffix(tmp_path, monkeypatch):
    root = tmp_path / "suffix"
    frontend = small_program(root, monkeypatch, SUFFIX, {"codex": [{"result": {"ok": True}}] * 2})
    assert _run_cli(root, *frontend, "--input", "message=hi").returncode == 0
    authority, snapshot = checked_run(root)
    entries = note, review, later = tuple(snapshot.active_commits.values())
    evidence = _evidence(authority, entries)
    assert [entry.data["depends_on"] for entry in entries] == [[], [note.data["identity"]], []]  # later: no C9 edge
    assert review.data["input_parts"][NOTE_PART] == sha256("NOTE v1\n")
    (root / "artifacts/note.md").write_text("NOTE v2\n", encoding="utf-8")
    before = _tree_bytes(root)
    diverged = _resume_cli(root, authority.run_root.name)
    assert (diverged.returncode, f"[effect_input_diverged] {review.data['identity']}" in diverged.stderr) == (2, True)
    assert _tree_bytes(root) == before

    invalidated = _cli(root, "invalidate", authority.run_root.name, review.data["identity"])

    assert invalidated.returncode == 0, invalidated.stderr
    row = json.loads(invalidated.stdout)
    assert (row["record"], row["from_commit"], rows(root, "invalidated")) == ("invalidated", review.offset, [row])
    assert list(checked_run(root)[1].active_commits) == [note.data["identity"]]
    resumed = _resume_cli(root, authority.run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _assert_suffix_reran(root, authority, entries, evidence)
    before = _tree_bytes(root)
    assert _resume_cli(root, authority.run_root.name).returncode == 0 and _tree_bytes(root) == before


# Required result paths in an active union arm ------------------------------------------

UNION = '''  (defpath Report :kind relpath :under "artifacts" :must-exist true)
  (defunion Made (Done (report Report)) (Skip (reason String)))
  (defworkflow run ((message String)) -> String
    (let* ((made (provider-result providers.review :prompt prompts.base :inputs (message) :returns Made)))
      (command-result later :argv ("python" "later.py" message) :returns String))))'''


def test_public_provider_union_with_a_missing_active_path_fails_before_commit(tmp_path, monkeypatch):
    root = tmp_path / "union"
    payload = {"variant": "Done", "report": "artifacts/absent.md"}
    frontend = small_program(root, monkeypatch, UNION, {"codex": [{"result": payload}]})

    assert _run_cli(root, *frontend, "--input", "message=hi").returncode == 1

    authority, snapshot = checked_run(root)
    (start,) = rows(root, "started")
    (failure,) = rows(root, "failed")
    assert (start["identity"].endswith(" / made"), failure["code"], snapshot.active_commits) == (
        True, "provider_result_invalid", {})
    assert failure["violations"] == [{"type": "variant_field_type_invalid", "message": "relpath target does not exist",
                                      "context": {"json_pointer": "/report", "value": "artifacts/absent.md",
                                                  "variant": "Done", "path": "/".join((
                                                      ".orchestrate/runs", authority.run_root.name,
                                                      start["result_path"]))}}]
    assert (snapshot.terminal.data["outcome"], _log(root, "later"), len(requests(root))) == ("failed", [], 1)


# Pure replay of a committed path, and a new declared read of it ------------------------

PURE = '''  (defpath Report :kind relpath :under "artifacts" :must-exist true)
  (defpath ResultBundle :kind relpath :under ".orchestrate/runs" :must-exist false)
  (defrecord Out (report Report) (bundle ResultBundle))
  (defworkflow run ((message String)) -> Out
    (let* ((made (provider-result providers.review :prompt prompts.base :inputs (message) :returns Report)))
      (record Out :report made :bundle (provider-bundle-path made :as ResultBundle)))))'''
CONSUMER = '''  (defpath Report :kind relpath :under "artifacts" :must-exist true)
  (defrecord Verdict (ok Bool))
  (defworkflow run ((message String)) -> Verdict
    (let* ((made (provider-result providers.review :prompt prompts.base :inputs (message) :returns Report)))
      (provider-result providers.review :prompt prompts.base :inputs ()
        :prompt-dependencies (:required (made)) :returns Verdict))))'''
MADE = {"result": "artifacts/report.md", "files": {"artifacts/report.md": "REPORT\n"}}


def test_public_pure_replay_returns_a_committed_path_whose_referent_is_gone(tmp_path, monkeypatch):
    root = tmp_path / "pure"
    frontend = small_program(root, monkeypatch, PURE, {"codex": [MADE]})
    assert _run_cli(root, *frontend, "--input", "message=hi").returncode == 0
    authority, snapshot = checked_run(root)
    (commit,) = snapshot.active_commits.values()
    value = snapshot.terminal.data["value"]
    assert value == {"report": "artifacts/report.md",
                     "bundle": f".orchestrate/runs/{authority.run_root.name}/{commit.data['result_path']}"}
    (root / value["report"]).unlink()
    (root / value["bundle"]).unlink()
    before = _tree_bytes(root)

    resumes = [_resume_cli(root, authority.run_root.name) for _ in range(2)]
    report = _cli(root, "report", "--run-id", authority.run_root.name, "--format", "json")

    assert [result.returncode for result in (*resumes, report)] == [0, 0, 0], report.stderr
    assert json.loads(report.stdout)["run"]["workflow_outputs"] == value
    assert (_tree_bytes(root), len(requests(root)), [row["attempt"] for row in rows(root, "started")]) == (
        before, 1, [1])


def test_public_new_declared_read_of_a_deleted_committed_path_refuses(tmp_path, monkeypatch):
    root = tmp_path / "consumer"
    frontend = small_program(root, monkeypatch, CONSUMER, {"codex": [MADE, {"result": {"ok": True}}]})
    stop_after(root, ["run", *frontend, "--input", "message=hi"], " / made")
    authority, paused = checked_run(root)
    (producer,) = paused.active_commits.values()
    (root / "artifacts/report.md").unlink()

    refused = _resume_cli(root, authority.run_root.name)

    _, after = checked_run(root)
    assert (refused.returncode, "missing_required_dependency" in refused.stderr) == (1, True)
    assert (list(after.active_commits.values()), after.terminal.data["outcome"]) == ([producer], "failed")
    assert ([row["identity"] for row in rows(root, "started")], len(requests(root))) == ([producer.data["identity"]], 1)


# Verified drain: command requests on the old route and at 2.35 --------------------------

STATE, WORK = "state/verified", drain.WORK
SCRIPTS = {"prepared": drain.ASSETS[1], "checks": drain.ASSETS[2], "recorded": drain.ASSETS[3]}
FLAGS = {
    "prepared": ["--drain-state-root", "--artifact-work-root", "--target-design-path", "--check-commands-path",
                 "--iteration", "--output"],
    "checks": ["--check-commands-path", "--base-sha", "--iteration-dir", "--output"],
    "recorded": ["--iteration", "--base-sha", "--worker-verdict", "--review-decision", "--done-review-decision",
                 "--checks-result-path", "--review-decision-path", "--done-review-decision-path",
                 "--worker-verdict-path", "--worker-note-path", "--blocked-notes-dir", "--ledger-path",
                 "--statuses-path", "--stall-limit", "--summary-path", "--drain-status-path"],
}
SUMMARY = {"schema": "verified_iteration_drain_summary/v1", "drain_status": "DONE", "iterations": 2,
           "statuses": ["ACCEPTED", "DONE"], "accepted_count": 2, "blocked_notes": [],
           "last_note": "worker iteration 1"}


def _templated(name: str, iteration: int) -> dict[str, str]:
    """Expected path and iteration operands of one iteration: those the source renders from the
    `${inputs.drain_state_root}`, `${inputs.artifact_work_root}` and `${loop.index}` templates, plus the
    `--drain-state-root` and `--iteration` operands it passes as values."""
    directory = f"{STATE}/iterations/{iteration}"
    return {
        "prepared": {"--drain-state-root": STATE, "--iteration": str(iteration),
                     "--output": f"{directory}/work-order.json"},
        "checks": {"--iteration-dir": directory, "--output": f"{directory}/checks-result.json"},
        "recorded": {"--iteration": str(iteration), "--statuses-path": f"{STATE}/statuses.txt",
                     "--blocked-notes-dir": f"{WORK}/blocked", "--summary-path": f"{WORK}/drain-summary.json",
                     **{f"--{stem}-path": f"{directory}/{stem}.txt" for stem in (
                         "review-decision", "done-review-decision", "worker-verdict", "worker-note",
                         "drain-status")},
                     "--checks-result-path": f"{directory}/checks-result.json"},
    }[name]


def _drain_route(root: Path, monkeypatch, *, current: bool) -> dict[str, list[list[str]]]:
    """The continue-then-done drain on one route; the logged argv of each command, per command."""
    frontend = drain._fixture(root, monkeypatch, {"worker": ["CONTINUE", "DONE"], "iteration_review": ["APPROVE"],
                                                  "done_review": ["APPROVE"], "commit": [0]})
    for script in SCRIPTS.values():
        text = (root / script).read_text(encoding="utf-8")
        assert text.count(FUTURE) == 1
        (root / script).write_text(text.replace(FUTURE, FUTURE + EXEC_LOG), encoding="utf-8")
    if current:
        assert _cli(root, "compile", *frontend).returncode == 0
    else:
        source = root / drain.SOURCE
        source.write_text(source.read_text(encoding="utf-8").replace('"2.35"', '"2.15"'), encoding="utf-8")
        shutil.copyfile(drain.MANIFESTS / "verified_iteration_drain.commands.json", root / "manifests/commands.json")
    result = _run_cli(root, *frontend, *drain.INPUTS)
    assert result.returncode == 0, result.stderr
    return {name: jsonl(root / f"{script}.runs.jsonl") for name, script in SCRIPTS.items()}


def _assert_command_requests(name: str, argvs: list[list[str]], commits: list[dict]) -> None:
    """Operand order and the rendered templates of both iterations; the 2.35 commits bind that argv."""
    assert [argv[1::2] for argv in argvs] == [FLAGS[name]] * 2
    assert [{flag: value for flag, value in zip(argv[1::2], argv[2::2]) if flag in _templated(name, index)}
            for index, argv in enumerate(argvs)] == [_templated(name, index) for index in range(2)]
    assert [data["input_parts"]["argv"] for data in commits if data["identity"].endswith(f" / {name}")] == [
        canonical_sha256(["python", *argv]) for argv in argvs]


def test_public_drain_command_requests_match_the_old_route(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_DATE", "2026-01-01T00:00:00+00:00")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-01-01T00:00:00+00:00")
    old = _drain_route(tmp_path / "old", monkeypatch, current=False)
    new = _drain_route(tmp_path / "new", monkeypatch, current=True)
    authority, snapshot = checked_run(tmp_path / "new")
    commits = [entry.data for entry in sorted(snapshot.active_commits.values(), key=lambda entry: entry.offset)]

    assert old == new
    for name, argvs in new.items():
        _assert_command_requests(name, argvs, commits)
    old_requests, new_requests = ([(row["role"], row["iteration"], row["decision"], row["files"])
                                   for row in drain._requests(tmp_path / route)] for route in ("old", "new"))
    assert old_requests == new_requests  # dependency bytes per request; prompts differ by R3 only
    assert [row[:3] for row in new_requests] == [("worker", "0", "CONTINUE"), ("iteration_review", "0", "APPROVE"),
                                                 ("worker", "1", "DONE"), ("done_review", "1", "APPROVE")]
    assert [row["prompt"] for row in drain._requests(tmp_path / "new")] == [
        sha256(attempt_files(authority, data)["prompt.txt"]).removeprefix("sha256:")
        for data in commits if data["effect_class"] == "provider"]
    assert json.loads((tmp_path / "new" / WORK / "drain-summary.json").read_bytes()) == SUMMARY
    drain._assert_completed_resume_is_readonly(tmp_path / "new", authority.run_root)


def test_public_drain_work_retry_keeps_the_failed_attempt_files(tmp_path, monkeypatch):
    frontend = drain._fixture(tmp_path, monkeypatch, {"worker": ["DONE"], "done_review": ["APPROVE"],
                                                      "fail_worker_calls": [1]})
    assert _run_cli(tmp_path, *frontend, *drain.INPUTS).returncode == 1
    authority, _ = checked_run(tmp_path)
    (failed,) = rows(tmp_path, "failed")
    evidence = attempt_files(authority, rows(tmp_path, "started", failed["identity"])[0])

    resumed = _resume_cli(tmp_path, authority.run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    first, second = rows(tmp_path, "started", failed["identity"])
    assert (attempt_files(authority, first), sorted(evidence)) == (evidence, ["prompt.txt", "stderr.txt", "stdout.txt"])
    assert (second["attempt"], sorted(attempt_files(authority, second))) == (
        2, ["prompt.txt", "result.json", "stderr.txt", "stdout.txt"])
    assert [row["role"] for row in drain._requests(tmp_path)] == ["worker", "worker", "done_review"]
