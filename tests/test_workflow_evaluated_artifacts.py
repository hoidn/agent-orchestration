"""Public watchdog artifact handoff at 2.35: produced files, declared read, publication and freshness.

The watchdog's probe writes the watch bundle and the evidence bundle, the selected repair
provider reads the watch bundle through its required prompt dependency, and the publisher
writes the watchdog result. Every run goes through public compile, run and CLI resume;
the target is a real evaluated run in another workspace.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.workflow.evaluated import effect_inputs
from orchestrator.workflow.evaluated import runtime
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_consumers import EVIDENCE, PROBE, REPAIR, REPAIRED, REPAIR_OUTPUT
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.test_workflow_evaluated_providers import _spy_provider_prepare
from tests.test_workflow_evaluated_resume import _resume_cli
from tests.workflow_evaluated_artifact_helpers import (
    COMPAT, PACKAGE, PUBLISHED, REPORT, WATCH, WATCH_PART, attempt_files, counts,
    dependency_block, field_type, rows, run_argv, stop_after_start, watchdog_workspace,
)
from tests.workflow_evaluated_consumer_sources import (
    BUNDLE, SITE, checked_run, requests, resume_to_completion, sha256, stop_after,
)
from tests.workflow_evaluated_totality_helpers import assert_commit_bytes


PROVIDERS = {"codex": [REPAIR], "claude": [REPAIR]}
CASES = {  # target failed, repair_provider input, (tool, model) of the selected provider
    "clean": (False, "codex", None),
    "codex-repair": (True, "codex", ("codex", "gpt-5.4")),
    "claude-repair": (True, "claude_opus", ("claude", "opus")),
}
CLEAN_OUTPUT = {"watch_status": "COMPLETED", "repair_status": "NO_ACTION", "recovery_action": "NONE",
                "watchdog_result_path": PUBLISHED}


def _probe_value(target: str, failed: bool) -> dict:
    return {"watch_bundle_path": WATCH, "watch_status": "FAILED" if failed else "COMPLETED",
            "repair_required": "YES" if failed else "NO", "recommended_recovery": "RESUME" if failed else "NONE",
            "evidence_bundle_path": f"{EVIDENCE}/{target}-evidence.json", "repair_result_target_path": COMPAT}


def _assert_produced(root: Path, target: str, failed: bool) -> dict:
    """Paused after the probe commit: its typed result names two parseable files it wrote; nothing else ran."""
    authority, snapshot = checked_run(root)
    (entry,) = snapshot.active_commits.values()
    probe = entry.data
    assert [(row.data["record"], row.data["attempt"]) for row in snapshot.entries] == [("started", 1), ("committed", 1)]
    assert (probe["effect_class"], probe["identity"].endswith(" / watch"), probe["depends_on"]) == ("command", True, [])
    assert probe["value"] == _probe_value(target, failed)
    assert_commit_bytes(authority, entry)
    assert {tuple(json.loads(key)[:2]) for key in probe["implementation_files"]} == {
        ("workspace", PROBE), ("absolute", PACKAGE)}
    assert probe["result_path"] == f"effects/{sha256(probe['identity']).removeprefix('sha256:')}/attempt-1/result.json"
    assert [field_type(authority, "WatchProbe", name) for name in ("watch_bundle_path", "evidence_bundle_path")] == [
        {"kind": "path", "must_exist_target": True, "name": f"generic_run_watchdog/watchdog::{name}", "under": under}
        for name, under in (("ProducedStatePath", "state"), ("ProducedArtifactPath", "artifacts/work"))]
    watch = json.loads((root / WATCH).read_bytes())
    evidence = json.loads((root / probe["value"]["evidence_bundle_path"]).read_bytes())
    assert (watch["watch_bundle_path"], watch["evidence_bundle_path"], watch["target_run_id"]) == (
        WATCH, probe["value"]["evidence_bundle_path"], target)
    assert (evidence["target_run_id"], evidence["run_status"]) == (target, "failed" if failed else "completed")
    assert counts(root) == (1, 0, 0) and snapshot.terminal is None
    return probe


def _assert_request_reads_watch(root: Path, commit: dict, request: dict, attempt: dict, target: str) -> None:
    """The request carried the watch bundle's bytes, digested in the commit, and is this attempt's request."""
    watch = (root / WATCH).read_bytes()
    block = dependency_block(request["prompt"], WATCH)
    assert (block, commit["input_parts"][WATCH_PART]) == (watch, sha256(watch))
    assert json.loads(block)["target_run_id"] == target  # the target's own datum reaches the provider only here
    assert attempt["prompt.txt"] == request["prompt"].encode()
    assert commit["input_parts"]["prompt"] == sha256(attempt["prompt.txt"])
    destination = Path(request["cwd"], request["env"][BUNDLE]).resolve()  # relative or absolute spelling
    assert destination == (checked_run(root)[0].run_root / commit["result_path"]).resolve()
    assert request["env"][SITE] == sha256(commit["identity"])


def _assert_declared_read(root: Path, probe: dict, target: str, tool: str, model: str) -> dict:
    """Paused after the provider commit: it read the probe's watch bundle bytes and wrote its report."""
    authority, snapshot = checked_run(root)
    commit = snapshot.entries[-1].data
    (request,) = requests(root)
    attempt = attempt_files(authority, commit)
    assert (commit["record"], commit["effect_class"], commit["attempt"]) == ("committed", "provider", 1)
    assert (commit["depends_on"], commit["value"]) == ([probe["identity"]], REPAIRED)
    assert (request["tool"], model in request["argv"]) == (tool, True)
    _assert_request_reads_watch(root, commit, request, attempt, target)
    assert sorted(attempt) == ["prompt.txt", "result.json", "stderr.txt", "stdout.txt"]
    assert commit["result_digest"] == sha256(attempt["result.json"])
    assert field_type(authority, "ProviderRepairResult", "repair_report_path")["under"] == "artifacts/work"
    assert {path: (root / path).read_text() for path in (REPORT, COMPAT)} == REPAIR["files"]
    assert counts(root) == (1, 1, 0) and not snapshot.pending_starts and snapshot.terminal is None
    return commit


def _published(target: str, failed: bool) -> dict:
    probe = _probe_value(target, failed)
    repair = REPAIRED if failed else {"repair_status": "NO_ACTION", "fix_complexity": "NOT_APPLICABLE",
                                      "recovery_action": "NONE", "repair_report_path": "", "plan_path": "",
                                      "new_run_id": ""}
    return {"schema": "orchestrator_run_watchdog_result/v1", "watchdog_result_path": PUBLISHED,
            "target_run_id": target, **{key: probe[key] for key in (
                "watch_status", "repair_required", "recommended_recovery", "evidence_bundle_path")},
            **repair, "repair_result_path": COMPAT if failed else ""}


@pytest.mark.parametrize("case", CASES)
def test_public_watchdog_repair_links_producer_read_and_publication(tmp_path, monkeypatch, case):
    failed, provider, selected = CASES[case]
    root, frontend, target = watchdog_workspace(tmp_path, monkeypatch, PROVIDERS, failed=failed, provider=provider)
    stop_after(root, run_argv(frontend), " / watch")
    probe = _assert_produced(root, target, failed)
    chain = [probe]
    if selected:
        stop_after(root, ["resume", checked_run(root)[0].run_root.name], "invoke-repair")
        chain.append(_assert_declared_read(root, probe, target, *selected))

    route = resume_to_completion(root)

    *prefix, publisher = route.commits
    produced = {f"{EVIDENCE}/{target}-evidence.json", WATCH, PUBLISHED} | ({REPORT, COMPAT} if failed else set())
    assert (prefix, len(route.commits), set(route.started().values())) == (chain, len(chain) + 1, {1})
    assert [row.data["record"] for row in route.snapshot.entries] == ["started", "committed"] * len(route.commits) + [
        "terminal"]
    assert (publisher["effect_class"], publisher["identity"].endswith(" / #1")) == ("command", True)
    assert set(publisher["depends_on"]) == {data["identity"] for data in chain}
    assert route.value == (REPAIR_OUTPUT if failed else CLEAN_OUTPUT)
    assert json.loads((root / PUBLISHED).read_bytes()) == _published(target, failed)
    assert {path.relative_to(root).as_posix() for base in ("state/watchdog", EVIDENCE)
            for path in (root / base).rglob("*") if path.is_file()} == produced
    assert counts(root) == (1, len(chain) - 1, 1)


# Retry, missing and changed dependency bytes ------------------------------------------

FAILING = {"exit": 1, "merge": {WATCH: {"fixture_dependency_version": "after-first-attempt"}}}


def _assert_two_attempts(authority, starts: list[dict], failure: dict, first_evidence: dict) -> None:
    """Attempt 1 failed and kept the files it wrote; attempt 2 has its own directory beside it."""
    first, second = starts
    assert (failure["attempt"], failure["code"]) == (1, "provider_exit_nonzero")
    assert [Path(row["result_path"]).parent.name for row in starts] == ["attempt-1", "attempt-2"]
    assert len({Path(row["result_path"]).parent.parent for row in starts}) == 1
    assert attempt_files(authority, first) == first_evidence
    assert sorted(first_evidence) == ["prompt.txt", "stderr.txt", "stdout.txt"]
    assert sorted(attempt_files(authority, second)) == ["prompt.txt", "result.json", "stderr.txt", "stdout.txt"]
    assert [row["input_parts"]["prompt"] for row in starts] == [
        sha256(attempt_files(authority, row)["prompt.txt"]) for row in starts]


def test_public_watchdog_retry_captures_changed_watch_bundle_in_attempt_two(tmp_path, monkeypatch):
    root, frontend, _target = watchdog_workspace(tmp_path, monkeypatch, {"codex": [FAILING, REPAIR]})
    assert _run_cli(root, *run_argv(frontend)[1:]).returncode == 1
    authority, _ = checked_run(root)
    (failure,) = rows(root, "failed")
    first_evidence = attempt_files(authority, rows(root, "started", "invoke-repair")[0])
    stop_after(root, ["resume", authority.run_root.name], "invoke-repair")
    assert counts(root) == (1, 2, 0)

    route = resume_to_completion(root)

    starts = rows(root, "started", "invoke-repair")
    _assert_two_attempts(authority, starts, failure, first_evidence)
    first, second = (row["input_parts"] for row in starts)
    old, new = (dependency_block(request["prompt"], WATCH) for request in route.requests)
    assert (first[WATCH_PART], second[WATCH_PART], new) == (sha256(old), sha256(new), (root / WATCH).read_bytes())
    assert json.loads(new) == {**json.loads(old), "fixture_dependency_version": "after-first-attempt"}
    assert {key for key in first if first[key] != second[key]} == {WATCH_PART, "prompt"}
    (commit,) = rows(root, "committed", "invoke-repair")
    assert (commit["attempt"], commit["value"], commit["input_parts"]) == (2, REPAIRED, second)
    assert counts(root) == (1, 2, 1) and route.value == REPAIR_OUTPUT


def test_public_missing_watch_bundle_refuses_pending_provider_before_any_write(tmp_path, monkeypatch):
    root, frontend, _target = watchdog_workspace(tmp_path, monkeypatch, {"codex": [REPAIR]})
    stop_after_start(root, run_argv(frontend), "invoke-repair")
    authority, pending = checked_run(root)
    assert [row.data["record"] for row in pending.entries] == ["started", "committed", "started"]
    assert list(pending.pending_starts) == [rows(root, "started", "invoke-repair")[0]["identity"]]
    watch = root / WATCH
    original = watch.read_bytes()
    watch.unlink()
    before = _tree_bytes(root)

    refused = _resume_cli(root, authority.run_root.name)
    monkeypatch.chdir(root)
    preparations = _spy_provider_prepare(monkeypatch)
    service = resume_workflow(authority.run_root.name)

    assert (refused.returncode, service, "missing_required_dependency" in refused.stderr) == (2, 2, True)
    assert (_tree_bytes(root), preparations, counts(root)) == (before, [], (1, 0, 0))
    replacement = (json.dumps({**json.loads(original), "restored": "different bytes"}, indent=2) + "\n").encode()
    assert replacement != original
    watch.write_bytes(replacement)
    route = resume_to_completion(root)
    (commit,) = [data for data in route.commits if data["effect_class"] == "provider"]
    assert [row["attempt"] for row in rows(root, "started", "invoke-repair")] == [1, 2]
    assert (commit["attempt"], commit["input_parts"][WATCH_PART]) == (2, sha256(replacement))
    assert counts(root) == (1, 1, 1) and route.value == REPAIR_OUTPUT


CHANGES = {  # the cause the refusal names
    "crlf-raw-bytes": WATCH_PART,
    "missing": "missing_required_dependency",
    "unreadable": "unreadable_dependency",
}


def _parts_changed_on_service_resume(root: Path, monkeypatch, committed: dict) -> set[str]:
    """Input parts the readonly service resume resolves for the provider and finds different from its commit.

    Observed like `_assert_public_raw_c6_service_refusal`: the refusal writes nothing, so the parts it
    compared are visible only at the reuse comparison."""
    captured = []
    real = effect_inputs._reuse_effect_commit

    def capture(*args, **kwargs):
        captured.append(dict(inspect.signature(real).bind(*args, **kwargs).arguments["parts"]))
        return real(*args, **kwargs)

    monkeypatch.chdir(root)
    monkeypatch.setattr(effect_inputs, "_reuse_effect_commit", capture)
    assert resume_workflow(checked_run(root)[0].run_root.name) == 2
    *_probe, parts = captured
    return {name for name in {*parts, *committed} if parts.get(name) != committed.get(name)}


@pytest.mark.parametrize("change", CHANGES)
def test_public_changed_watch_bundle_after_provider_commit_refuses_readonly(tmp_path, monkeypatch, change):
    root, frontend, _target = watchdog_workspace(tmp_path, monkeypatch, {"codex": [REPAIR]})
    stop_after(root, run_argv(frontend), "invoke-repair")
    authority, _ = checked_run(root)
    (provider,) = rows(root, "committed", "invoke-repair")
    watch = root / WATCH
    original = watch.read_bytes()
    if change == "crlf-raw-bytes":
        watch.write_bytes(original.replace(b"\n", b"\r\n"))
    elif change == "missing":
        watch.unlink()
    before = _tree_bytes(root)  # taken before the file becomes unreadable; chmod changes no byte
    if change == "unreadable":
        watch.chmod(0)

    refused = _resume_cli(root, authority.run_root.name)

    if change == "unreadable":
        watch.chmod(0o644)
    diagnostic = f"[effect_input_diverged] {provider['identity']}"
    assert (refused.returncode, diagnostic in refused.stderr, CHANGES[change] in refused.stderr) == (2, True, True)
    if change == "crlf-raw-bytes":  # same rendered prompt: the raw dependency digest alone refuses
        assert _parts_changed_on_service_resume(root, monkeypatch, provider["input_parts"]) == {WATCH_PART}
    assert (_tree_bytes(root), counts(root)) == (before, (1, 1, 0))
    watch.write_bytes(original)
    route = resume_to_completion(root)
    assert (route.commits[1], counts(root), route.value) == (provider, (1, 1, 1), REPAIR_OUTPUT)


# Required result paths are validated before commit --------------------------------------

@pytest.mark.parametrize("report", [f"{EVIDENCE}/absent-report.md", WATCH], ids=["missing", "outside-root"])
def test_public_invalid_repair_report_path_fails_before_commit(tmp_path, monkeypatch, report):
    invalid = {"result": {**REPAIRED, "repair_report_path": report}}
    root, frontend, _target = watchdog_workspace(tmp_path, monkeypatch, {"codex": [invalid]})

    assert _run_cli(root, *run_argv(frontend)[1:]).returncode == 1

    authority, snapshot = checked_run(root)
    (failure,) = rows(root, "failed")
    (start,) = rows(root, "started", "invoke-repair")
    assert [row.data["record"] for row in snapshot.entries] == ["started", "committed", "started", "failed", "terminal"]
    assert (failure["identity"], failure["code"], snapshot.terminal.data["outcome"]) == (
        start["identity"], "provider_result_invalid", "failed")
    assert [(row["context"]["json_pointer"], row["context"]["value"]) for row in failure["violations"]] == [
        ("/repair_report_path", report)]
    assert (len(snapshot.active_commits), counts(root)) == (1, (1, 1, 0))
    assert not (root / PUBLISHED).exists() and "result.json" in attempt_files(authority, start)
