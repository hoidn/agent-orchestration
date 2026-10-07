"""Provider memo reuse, retry, order and content evidence through real performers."""

from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
import inspect
from pathlib import Path
import json
import os

import pytest

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.workflow.evaluated import effect_inputs
from orchestrator.workflow.evaluated import runtime
from orchestrator.workflow.evaluated import attempts
from orchestrator.workflow.evaluated.authority import load_run_authority, publish_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from tests.test_workflow_evaluated_providers import (
    SOURCE, _assert_cli_resume_refusal, _assert_retry_request_parity, _cache_snapshot,
    _cli, _fixture, _orchestrate_snapshot, _requests, _spy_provider_prepare,
)


class _Interrupted(BaseException):
    pass


@contextmanager
def _run(root, monkeypatch, source=SOURCE, *, prompt_kind="asset_file", inputs=None):
    fixture = _fixture(root, source, prompt_kind=prompt_kind)
    built = build_closed_program_bundle(fixture[3])
    monkeypatch.setenv("PATH", str(root / "bin") + os.pathsep + os.environ["PATH"])
    with publish_run_authority(root / ".state" / "run-1", built.program,
        run_id="run-1", workflow_file="main.orc", workflow_checksum="sha256:" + sha256(source.encode()).hexdigest(),
        resume_request={"source_roots": [], "entry_workflow": None,
            "provider_externs_path": None, "prompt_externs_path": None,
            "imported_workflow_bundles_path": None, "command_boundaries_path": None,
            "input_file": None, "input_overrides": {}},
        bound_inputs=inputs or {"message": "typed input"}) as authority:
        yield built, authority


def _execute(root, built, authority, *, inputs=None):
    return runtime.execute_pure_run(authority, inputs or {"message": "typed input"},
        run_id="run-1", workspace=root, provider_io=built.provider_io)


def _snapshot(built, authority):
    return read_memo(authority.memo_path, site_classes(built.program))


def _interrupt_after_commit(root, built, authority, monkeypatch, *, inputs=None):
    original = runtime.append_record

    def stop(path, record, **kwargs):
        entry = original(path, record, **kwargs)
        if record["record"] == "committed":
            raise _Interrupted()
        return entry

    with monkeypatch.context() as patched:
        patched.setattr(runtime, "append_record", stop)
        with pytest.raises(_Interrupted):
            _execute(root, built, authority, inputs=inputs)


def test_provider_started_is_synced_before_mkdir_and_single_preparation(tmp_path, monkeypatch):
    order = []
    with _run(tmp_path, monkeypatch) as (built, authority):
        real_sync, real_mkdir = os.fsync, WorkspaceFiles.mkdir_exclusive
        real_prepare, real_execute = ProviderExecutor.prepare_invocation, ProviderExecutor.execute

        def sync(fd):
            real_sync(fd)
            if os.readlink(f"/proc/self/fd/{fd}") == str(authority.memo_path):
                order.append("memo-fsync")

        def mkdir(owner, path):
            assert _snapshot(built, authority).pending_starts
            assert not (owner.workspace / path).exists()
            order.append("mkdir")
            return real_mkdir(owner, path)

        def prepare(executor, *args, **kwargs):
            assert executor.provider_observation_enabled is False
            assert kwargs["context"] == {}
            order.append("prepare")
            return real_prepare(executor, *args, **kwargs)

        def execute(executor, *args, **kwargs):
            order.append("execute")
            return real_execute(executor, *args, **kwargs)

        monkeypatch.setattr(os, "fsync", sync)
        monkeypatch.setattr(WorkspaceFiles, "mkdir_exclusive", mkdir)
        monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare)
        monkeypatch.setattr(ProviderExecutor, "execute", execute)
        assert _execute(tmp_path, built, authority) == (0, {"ok": True})
        assert order[:4] == ["memo-fsync", "mkdir", "prepare", "execute"]
        assert order.count("prepare") == order.count("execute") == 1
        assert len(list(authority.run_root.glob("effects/*/attempt-*"))) == 1


def test_provider_run_placeholder_fails_reserved_attempt_without_dispatch(tmp_path, monkeypatch):
    original = ProviderRegistry._load_builtin_providers

    def templates(registry):
        providers = original(registry)
        providers["codex"] = replace(providers["codex"], command=[*providers["codex"].command, "${run.id}"])
        return providers

    monkeypatch.setattr(ProviderRegistry, "_load_builtin_providers", templates)
    with _run(tmp_path, monkeypatch) as (built, authority):
        assert _execute(tmp_path, built, authority) == (1, None)
        snapshot = _snapshot(built, authority)
        started, failure, _terminal = [entry.data for entry in snapshot.entries]
        assert failure["record"] == "failed" and failure["attempt"] == started["attempt"] == 1
        assert failure["code"] == "provider_preparation_failed"
        assert "run.id" in json.dumps(failure["exit_info"])
        attempt = authority.run_root / Path(started["result_path"]).parent
        assert (attempt / "prompt.txt").is_file()
        assert (attempt / "stdout.txt").read_bytes() == (attempt / "stderr.txt").read_bytes() == b""
        assert not _requests(tmp_path)


def test_provider_commit_reuse_preserves_evidence_and_uses_stored_result_path(tmp_path, monkeypatch):
    with _run(tmp_path, monkeypatch) as (built, authority):
        _interrupt_after_commit(tmp_path, built, authority, monkeypatch)
        before = _snapshot(built, authority)
        (commit,) = before.active_commits.values()
        attempt = authority.run_root / Path(commit.data["result_path"]).parent
        evidence = {path.name: path.read_bytes() for path in attempt.iterdir()}
        (attempt / "result.json").unlink()
        monkeypatch.setattr(ProviderExecutor, "prepare_invocation", lambda *_a, **_k: pytest.fail("commit redispatch"))
        assert _execute(tmp_path, built, authority) == (0, {"ok": True})
        after = _snapshot(built, authority)
        assert after.active_commits == before.active_commits
        assert after.raw.startswith(before.raw)
        assert len(_requests(tmp_path)) == 1
        assert {path.name: path.read_bytes() for path in attempt.iterdir()} == {k:v for k,v in evidence.items() if k != "result.json"}


@pytest.mark.parametrize("change", ["source", "values", "source-missing"])
def test_provider_commit_divergence_is_readonly_before_next_attempt(tmp_path, monkeypatch, change):
    with _run(tmp_path, monkeypatch) as (built, authority):
        _interrupt_after_commit(tmp_path, built, authority, monkeypatch)
        before = authority.memo_path.read_bytes()
        if change == "source":
            (tmp_path / "prompt.md").write_text("new raw bytes\n")
        elif change == "source-missing":
            (tmp_path / "prompt.md").unlink()
        inputs = {"message": "changed input"} if change == "values" else None
        monkeypatch.setattr(ProviderExecutor, "prepare_invocation", lambda *_a, **_k: pytest.fail("diverged dispatch"))
        assert _execute(tmp_path, built, authority, inputs=inputs) == (1, None)
        assert authority.memo_path.read_bytes() == before
        assert len(list(authority.run_root.glob("effects/*/attempt-*"))) == 1
        assert len(_requests(tmp_path)) == 1


def test_provider_source_refusal_before_start_creates_no_attempt(tmp_path, monkeypatch):
    with _run(tmp_path, monkeypatch) as (built, authority):
        (tmp_path / "prompt.md").unlink()
        assert _execute(tmp_path, built, authority) == (1, None)
        snapshot = _snapshot(built, authority)
        assert not snapshot.latest_starts and not snapshot.pending_starts
        assert not (authority.run_root / "effects").exists()
        assert not _requests(tmp_path)


def test_pending_retry_recaptures_provider_c6_without_command_baseline_pin(tmp_path, monkeypatch):
    with _run(tmp_path, monkeypatch) as (built, authority):
        def stop(_owner, _path):
            raise _Interrupted()

        with monkeypatch.context() as patched:
            patched.setattr(WorkspaceFiles, "mkdir_exclusive", stop)
            with pytest.raises(_Interrupted):
                _execute(tmp_path, built, authority)
        baseline = authority.memo_path.read_bytes()
        (tmp_path / "prompt.md").unlink()
        assert _execute(tmp_path, built, authority) == (1, None)
        assert authority.memo_path.read_bytes() == baseline
        (tmp_path / "prompt.md").write_text("new C6 bytes\n")
        assert _execute(tmp_path, built, authority) == (0, {"ok": True})
        starts = [entry.data for entry in _snapshot(built, authority).entries if entry.data["record"] == "started"]
        assert [row["attempt"] for row in starts] == [1, 2]
        assert starts[0]["input_parts"] != starts[1]["input_parts"]
        assert len(_requests(tmp_path)) == 1


def test_failed_provider_retry_keeps_earlier_attempt_streams(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_SHIM_MODE", "nonzero")
    with _run(tmp_path, monkeypatch) as (built, authority):
        assert _execute(tmp_path, built, authority) == (1, None)
        (first,) = authority.run_root.glob("effects/*/attempt-1")
        prior = {path.name: path.read_bytes() for path in first.iterdir()}
        monkeypatch.setenv("PROVIDER_SHIM_MODE", "success")
        assert _execute(tmp_path, built, authority) == (0, {"ok": True})
        assert {path.name: path.read_bytes() for path in first.iterdir()} == prior
        assert len(_requests(tmp_path)) == 2
        assert len(list(authority.run_root.glob("effects/*/attempt-*"))) == 2


def test_public_failed_provider_retry_uses_next_attempt_and_preserves_evidence(tmp_path, monkeypatch):
    state = _capture_public_failed_provider(tmp_path)
    from tests.test_workflow_evaluated_resume import _resume_cli

    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("PROVIDER_SHIM_MODE", "success")
    monkeypatch.setenv("PROVIDER_SHIM_RESULT", '{"ok":true,"extra":7}')
    resumed = _resume_cli(tmp_path, state["run_root"].name)
    assert resumed.returncode == 0, resumed.stderr
    after = read_memo(state["authority"].memo_path, site_classes(state["authority"].program))
    _assert_failed_retry_requests(tmp_path, state, after)
    _assert_failed_retry_journal(state, after)
    _assert_failed_retry_preservation(tmp_path, state)


def _capture_public_failed_provider(root):
    fixture = _fixture(root)
    failed = _cli(root, fixture, mode="nonzero")
    assert failed.returncode == 1, failed.stderr
    assert len(_requests(root)) == 1
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    before = read_memo(authority.memo_path, site_classes(authority.program))
    started, failure, terminal = [entry.data for entry in before.entries]
    assert [started["record"], failure["record"], terminal["record"]] == ["started", "failed", "terminal"]
    assert terminal["outcome"] == "failed"
    attempt_one = run_root / Path(started["result_path"]).parent
    return {
        "run_root": run_root, "authority": authority,
        "attempt_one": attempt_one,
        "old_evidence": {path.name: path.read_bytes() for path in attempt_one.iterdir()},
        "header": (run_root / "run.json").read_bytes(),
        "artifact": (run_root / "closed_program.json").read_bytes(),
        "cache": _cache_snapshot(root),
        "requests": (root / "requests.jsonl").read_bytes(),
    }


def _assert_failed_retry_requests(root, state, after):
    request_bytes = (root / "requests.jsonl").read_bytes()
    assert request_bytes.startswith(state["requests"])
    requests = _requests(root)
    assert len(requests) == 2
    _assert_retry_request_parity(state["authority"].program, requests[1], requests[0])


def _assert_failed_retry_journal(state, after):
    starts = [entry.data for entry in after.entries if entry.data["record"] == "started"]
    assert [row["attempt"] for row in starts] == [1, 2]
    assert _parts_except_prompt(starts[0]["input_parts"]) == _parts_except_prompt(starts[1]["input_parts"])
    for start in starts:
        _assert_attempt_prompt_part(state["run_root"], start)
    assert after.terminal.data["outcome"] == "completed"


def _parts_except_prompt(parts):
    return {key: value for key, value in parts.items() if key != "prompt"}


def _assert_attempt_prompt_part(run_root, start):
    attempt = run_root / Path(start["result_path"]).parent
    prompt_digest = "sha256:" + sha256((attempt / "prompt.txt").read_bytes()).hexdigest()
    assert start["input_parts"]["prompt"] == prompt_digest


def _assert_failed_retry_preservation(root, state):
    run_root = state["run_root"]
    attempt_one = state["attempt_one"]
    assert {path.name: path.read_bytes() for path in attempt_one.iterdir()} == state["old_evidence"]
    assert (run_root / "run.json").read_bytes() == state["header"]
    assert (run_root / "closed_program.json").read_bytes() == state["artifact"]
    assert _cache_snapshot(root) == state["cache"]


@pytest.mark.parametrize("input_uses_model", [False, True])
def test_provider_c9_includes_dynamic_policy_without_input_masking(tmp_path, monkeypatch, input_uses_model):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule main) (export run)
      (defproc ask ((model String)) -> String
        :effects ((uses-provider providers.review)) :lowering private-workflow
        (provider-result providers.review :prompt prompts.base :inputs (model) :model model :returns String))
      (defworkflow run ((message String)) -> String
        (let* ((chosen (provider-result providers.review :prompt prompts.base :inputs () :returns String)))
          (ask chosen))))'''
    if not input_uses_model:
        source = source.replace(':inputs (model)', ':inputs ("independent input")')
    monkeypatch.setenv("PROVIDER_SHIM_RESULT", '"chosen-model"')
    with _run(tmp_path, monkeypatch, source) as (built, authority):
        assert _execute(tmp_path, built, authority) == (0, "chosen-model")
        commits = list(_snapshot(built, authority).active_commits.values())
        assert commits[1].data["depends_on"] == [commits[0].data["identity"]]
        assert "chosen-model" in _requests(tmp_path)[1]["argv"]


def _raw_c6_fixture(root, source_case):
    source, inputs = SOURCE, {"message": "typed input"}
    target = root / "prompt.md"
    if source_case == "dependency-tail":
        source = source.replace('(defrecord Result', '(defpath Note :kind relpath :under "artifacts" :must-exist true) (defrecord Result')
        source = source.replace('((message String))', '((message String) (note Note))')
        source = source.replace(':inputs (message)', ':inputs (message) :prompt-dependencies (:required (note))')
        (root / "artifacts").mkdir()
        target = root / "artifacts" / "note.md"
        inputs["note"] = "artifacts/note.md"
    kind = "input_file" if source_case == "absent-empty" else "asset_file"
    return source, inputs, target, kind


def _write_raw_c6_variant(target, source_case, *, changed):
    if source_case == "normalized":
        target.write_bytes(b"SAME TEXT\n" if changed else b"SAME TEXT\r\n")
    elif source_case == "absent-empty":
        if changed:
            target.write_bytes(b"")
        else:
            target.unlink(missing_ok=True)
    else:
        from orchestrator.deps.content_snapshot import MAX_INJECTION_BYTES

        content = b"A" * (MAX_INJECTION_BYTES + 128) + b"X"
        if changed:
            content = target.read_bytes()[:-1] + b"Y"
        target.write_bytes(content)


@pytest.mark.parametrize("source_case", ["normalized", "absent-empty", "dependency-tail"])
def test_provider_raw_c6_changes_diverge_even_when_rendered_prompt_is_identical(tmp_path, monkeypatch, source_case):
    source, inputs, target, kind = _raw_c6_fixture(tmp_path, source_case)
    with _run(tmp_path, monkeypatch, source, prompt_kind=kind, inputs=inputs) as (built, authority):
        _write_raw_c6_variant(target, source_case, changed=False)
        _interrupt_after_commit(tmp_path, built, authority, monkeypatch, inputs=inputs)
        (commit,) = _snapshot(built, authority).active_commits.values()
        before = authority.memo_path.read_bytes()
        _write_raw_c6_variant(target, source_case, changed=True)
        captured = []
        real_reuse = effect_inputs._reuse_effect_commit

        def reuse(*args, **kwargs):
            captured.append(inspect.signature(real_reuse).bind(*args, **kwargs).arguments["parts"])
            return real_reuse(*args, **kwargs)

        monkeypatch.setattr(effect_inputs, "_reuse_effect_commit", reuse)
        assert _execute(tmp_path, built, authority, inputs=inputs) == (1, None)
        assert captured[0]["prompt"] == commit.data["input_parts"]["prompt"]
        assert captured[0] != commit.data["input_parts"]
        assert authority.memo_path.read_bytes() == before
        assert len(_requests(tmp_path)) == 1


@pytest.mark.parametrize("source_case", ["normalized", "absent-empty", "dependency-tail"])
def test_public_provider_raw_c6_changes_refuse_readonly_with_causal_parts(
    tmp_path, monkeypatch, caplog, source_case,
):
    source, inputs, target, kind = _raw_c6_fixture(tmp_path, source_case)
    fixture = _fixture(tmp_path, source, prompt_kind=kind)
    _write_raw_c6_variant(target, source_case, changed=False)
    extra = ("--input", "note=artifacts/note.md") if source_case == "dependency-tail" else ()
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    result = _cli(tmp_path, fixture, extra=extra)
    assert result.returncode == 0, result.stderr

    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    before_memo = read_memo(authority.memo_path, site_classes(authority.program))
    (commit,) = before_memo.active_commits.values()
    old_parts = commit.data["input_parts"]
    attempt = run_root / Path(commit.data["result_path"]).parent
    prompt_bytes = (attempt / "prompt.txt").read_bytes()
    raw_part = {
        "normalized": "source:asset_file:prompt.md",
        "absent-empty": "source:input_file:prompt.md",
        "dependency-tail": "dependency:artifacts/note.md",
    }[source_case]
    _write_raw_c6_variant(target, source_case, changed=True)
    before = _orchestrate_snapshot(tmp_path)
    memo_before = authority.memo_path.read_bytes()
    cache_before = _cache_snapshot(tmp_path)
    requests_before = (tmp_path / "requests.jsonl").read_bytes()
    _assert_cli_resume_refusal(
        tmp_path, run_root.name, before, requests_before, code=2,
        diagnostic="effect_input_diverged",
    )
    _assert_public_raw_c6_service_refusal(
        tmp_path, run_root.name, authority, before, memo_before, cache_before,
        requests_before, old_parts, raw_part, prompt_bytes, caplog, monkeypatch,
    )


def _assert_public_raw_c6_service_refusal(
    root, run_id, authority, before, memo_before, cache_before, requests_before,
    old_parts, raw_part, prompt_bytes, caplog, monkeypatch,
):
    from orchestrator.cli.commands.resume import resume_workflow

    captured = []
    real_reuse = effect_inputs._reuse_effect_commit

    def capture_reuse(*args, **kwargs):
        captured.append(dict(inspect.signature(real_reuse).bind(*args, **kwargs).arguments["parts"]))
        return real_reuse(*args, **kwargs)

    monkeypatch.chdir(root)
    monkeypatch.setattr(effect_inputs, "_reuse_effect_commit", capture_reuse)
    prepare_calls = _spy_provider_prepare(monkeypatch)
    assert resume_workflow(run_id) == 2
    assert "effect_input_diverged" in caplog.text
    assert prepare_calls == []
    assert len(captured) == 1
    _assert_raw_c6_parts(captured[0], old_parts, raw_part, prompt_bytes)
    assert authority.memo_path.read_bytes() == memo_before
    assert _orchestrate_snapshot(root) == before
    assert _cache_snapshot(root) == cache_before
    assert (root / "requests.jsonl").read_bytes() == requests_before


def _assert_raw_c6_parts(current, old, raw_part, prompt_bytes):
    assert current["prompt"] == old["prompt"] == "sha256:" + sha256(prompt_bytes).hexdigest()
    assert current[raw_part] != old[raw_part]


def test_supplied_staged_provider_selection_reaches_real_performer(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from tests.test_workflow_evaluated_provider_io import WREF, _checked, _stages, _typed

    _fixture(tmp_path)
    _, imports = _stages(tmp_path)
    imports["right"].provenance.workflow_path.with_name("prompt.md").write_text("TARGET RIGHT\n")
    checked, provider_io = _checked(_typed(tmp_path, WREF, imports))
    original = ProviderRegistry._load_builtin_providers

    def templates(registry):
        providers = original(registry)
        providers["provider-id"] = replace(providers["codex"], name="provider-id")
        return providers

    monkeypatch.setattr(ProviderRegistry, "_load_builtin_providers", templates)
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("PROVIDER_SHIM_RESULT", '{"n":7}')
    built = SimpleNamespace(program=checked, provider_io=provider_io)
    with publish_run_authority(tmp_path / ".state" / "run-1", checked, run_id="run-1",
        workflow_file="consumer/main.orc", workflow_checksum="sha256:" + sha256(WREF.encode()).hexdigest(),
        resume_request={"source_roots": [], "entry_workflow": None,
            "provider_externs_path": None, "prompt_externs_path": None,
            "imported_workflow_bundles_path": None, "command_boundaries_path": None,
            "input_file": None, "input_overrides": {}},
        bound_inputs={"input": {"n": 0}}) as authority:
        assert _execute(tmp_path, built, authority, inputs={"input": {"n": 0}}) == (0, {"n": 7})
        requests = _requests(tmp_path)
        assert [row["prompt"].splitlines()[0] for row in requests] == [
            "PARENT INLINE", "TARGET LEFT", "PARENT INLINE", "TARGET RIGHT"]
        assert len(_snapshot(built, authority).active_commits) == 4


def test_provider_committed_path_is_reused_without_filesystem_revalidation(tmp_path, monkeypatch):
    source = SOURCE.replace('(defrecord Result (ok Bool))',
        '(defpath Artifact :kind relpath :under "artifacts" :must-exist true)').replace('Result', 'Artifact')
    artifact = tmp_path / "artifacts" / "saved.txt"
    artifact.parent.mkdir()
    artifact.write_text("committed file")
    monkeypatch.setenv("PROVIDER_SHIM_RESULT", '"artifacts/saved.txt"')
    with _run(tmp_path, monkeypatch, source) as (built, authority):
        _interrupt_after_commit(tmp_path, built, authority, monkeypatch)
        (commit,) = _snapshot(built, authority).active_commits.values()
        evidence = {path: path.read_bytes() for path in authority.run_root.glob("effects/*/attempt-*/*")}
        artifact.unlink()
        monkeypatch.setattr(ProviderExecutor, "prepare_invocation", lambda *_a, **_k: pytest.fail("path redispatch"))
        assert _execute(tmp_path, built, authority) == (0, "artifacts/saved.txt")
        assert _snapshot(built, authority).active_commits[commit.data["identity"]] == commit
        assert {path: path.read_bytes() for path in evidence} == evidence
        assert len(_requests(tmp_path)) == 1


@pytest.mark.parametrize("operand_kind", ["input", "doc", "dependency"])
def test_provider_c9_keeps_selected_input_fill_and_dependency_lineage(tmp_path, monkeypatch, operand_kind):
    requests = {
        "input": ':prompt prompts.base :inputs (chosen) :returns Bool',
        "doc": ':prompt (document :note chosen)',
        "dependency": ':prompt prompts.base :inputs ("independent") :prompt-dependencies (:required (chosen)) :returns Bool',
    }
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule main) (export run)
      (defpath Note :kind relpath :under "artifacts" :must-exist true)
      (defprompt document (:fills (note :doc Note)) -> Bool "Review document")
      (defworkflow run ((message String)) -> Bool
        (let* ((chosen (provider-result providers.review :prompt prompts.base :inputs () :returns Note)))
          (provider-result providers.review {requests[operand_kind]}))))'''
    artifact = tmp_path / "artifacts" / "note.md"
    artifact.parent.mkdir()
    artifact.write_text("selected document")
    monkeypatch.setenv("PROVIDER_SHIM_RESULTS", json.dumps(['"artifacts/note.md"', 'true']))
    with _run(tmp_path, monkeypatch, source) as (built, authority):
        assert _execute(tmp_path, built, authority) == (0, True)
        first, second = _snapshot(built, authority).active_commits.values()
        assert second.data["depends_on"] == [first.data["identity"]]
        assert len(_requests(tmp_path)) == 2
