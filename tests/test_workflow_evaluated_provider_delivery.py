"""The contract block a new evaluated provider attempt renders, and the missing-result reply excerpt
(docs/design/provider_result_delivery.md)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from orchestrator.cli.main import main as cli_main
from orchestrator.providers.executor import ProviderExecutionResult
from orchestrator.providers.types import (
    InputMode,
    ProviderInvocation,
    ProviderSessionMetadataMode,
)
from orchestrator.workflow.evaluated.providers import (
    ProviderPerformerError,
    ResolvedProviderInput,
    launch_provider,
    provider_result,
)
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.contracts.prompt_contract import _RELPATH_GUIDANCE
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.contracts.closed_program.sites import _ast_nodes
from orchestrator.providers.executor import ProviderExecutor
from tests.test_workflow_evaluated_providers import SOURCE, _cli, _fixture, _public_snapshot, _requests
from tests.test_workflow_evaluated_resume_kills import _cli as _env_cli, _env


_REPLY = json.dumps("Here is the move:\n\n   " + "e2e4 " * 80)
_ROOT_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defworkflow run ((message String)) -> String
    (provider-result providers.review :prompt prompts.base
      :inputs () :returns String)))'''


def _provider_node(root, source):
    fixture = _fixture(root, source)
    program = build_closed_program_bundle(fixture[3]).program
    return next(node for node in _ast_nodes(program.tree["body"])
        if node.get("k") == "perform" and node.get("class") == "provider")


def _attempt_files(root):
    attempt_root = root / "effects" / "site" / "attempt-1"
    attempt_root.mkdir(parents=True)
    attempt_files = WorkspaceFiles(attempt_root)
    workspace_files = WorkspaceFiles(root)
    return attempt_files, workspace_files, "effects/site/attempt-1/result.json"


def _fake_executor(execution, *, metadata_mode, before_return=None):
    invocation = ProviderInvocation(
        command=["fake-provider"], input_mode=InputMode.STDIN,
        metadata_mode=metadata_mode,
    )

    class FakeExecutor:
        def prepare_invocation(self, **_kwargs):
            return invocation, None

        def execute(self, *_args, **_kwargs):
            if before_return is not None:
                before_return()
            return execution

    return FakeExecutor()


def _execution(normalized, *, raw=b'{"transport":"frame"}', stderr=b"transport stderr\n",
    exit_code=0, error=None):
    return ProviderExecutionResult(
        exit_code=exit_code, stdout=normalized or b"", stderr=stderr, duration_ms=1,
        error=error, raw_stdout=raw, normalized_stdout=normalized,
    )


def _launch_and_read(root, node, normalized, *, metadata_mode=None, execution=None,
    before_return=None):
    attempt_files, workspace_files, result_path = _attempt_files(root)
    executor = _fake_executor(
        execution or _execution(normalized), metadata_mode=metadata_mode,
        before_return=before_return,
    )
    resolved = ResolvedProviderInput("request bytes\n", {}, {}, [])
    launch_provider(node, resolved, "site", executor=executor,
        attempt_files=attempt_files, workspace_files=workspace_files,
        result_path=result_path)
    return provider_result(node, resolved, attempt_files, workspace_files, result_path), (
        attempt_files, workspace_files, result_path
    )


def test_successful_omp_materializes_normalized_root_json_for_existing_reader(tmp_path):
    node = _provider_node(tmp_path, _ROOT_SOURCE)

    (result, _owners) = _launch_and_read(
        tmp_path, node, b'"normalized final answer"',
        metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
    )

    value, digest = result
    assert value.json_value() == "normalized final answer"
    assert digest == "sha256:" + hashlib.sha256(b'"normalized final answer"').hexdigest()


def test_successful_omp_materializes_normalized_record_and_keeps_raw_evidence(tmp_path):
    node = _provider_node(tmp_path, SOURCE)
    normalized = b'{"ok":true}'
    raw = b'{"response":{"text":"raw OMP frame"}}'

    (result, (attempt_files, workspace_files, result_path)) = _launch_and_read(
        tmp_path, node, normalized,
        metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
        execution=_execution(normalized, raw=raw),
    )

    value, _digest = result
    assert value.json_value() == {"ok": True}
    assert attempt_files.read("result.json") == normalized
    assert attempt_files.read("stdout.txt") == raw
    assert attempt_files.read("stderr.txt") == b"transport stderr\n"


@pytest.mark.parametrize("normalized", [b"{bad JSON", b'{"ok":"wrong type"}'])
def test_omp_invalid_normalized_json_is_rejected_by_the_existing_reader(tmp_path, normalized):
    node = _provider_node(tmp_path, SOURCE)
    attempt_files, workspace_files, result_path = _attempt_files(tmp_path)
    resolved = ResolvedProviderInput("request bytes\n", {}, {}, [])
    launch_provider(node, resolved, "site",
        executor=_fake_executor(_execution(normalized),
            metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value),
        attempt_files=attempt_files, workspace_files=workspace_files,
        result_path=result_path)

    with pytest.raises(ProviderPerformerError) as caught:
        provider_result(node, resolved, attempt_files, workspace_files, result_path)

    assert caught.value.code == "provider_result_invalid"
    assert attempt_files.read("result.json") == normalized


@pytest.mark.parametrize(("exit_code", "error"), [(9, None), (0, {"type": "transport"})])
def test_failed_omp_execution_never_materializes_result_and_keeps_evidence(
    tmp_path, exit_code, error
):
    node = _provider_node(tmp_path, SOURCE)
    attempt_files, workspace_files, _result_path = _attempt_files(tmp_path)
    raw, stderr = b"raw frame", b"transport failure\n"
    execution = _execution(b'{"ok":true}', raw=raw, stderr=stderr,
        exit_code=exit_code, error=error)

    with pytest.raises(ProviderPerformerError) as caught:
        launch_provider(node, ResolvedProviderInput("request", {}, {}, []), "site",
            executor=_fake_executor(execution,
                metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value),
            attempt_files=attempt_files, workspace_files=workspace_files,
            result_path="effects/site/attempt-1/result.json")

    assert caught.value.code == "provider_exit_nonzero"
    assert not attempt_files.exists("result.json")
    assert attempt_files.read("stdout.txt") == raw
    assert attempt_files.read("stderr.txt") == stderr


@pytest.mark.parametrize("normalized", [None, b""])
def test_omp_missing_normalized_stdout_uses_missing_result_diagnostic(tmp_path, normalized):
    node = _provider_node(tmp_path, SOURCE)
    raw = b'{"ok":true}'
    with pytest.raises(ProviderPerformerError) as caught:
        _launch_and_read(tmp_path, node, normalized,
            metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
            execution=_execution(normalized, raw=raw))

    assert caught.value.code == "provider_result_missing"
    assert "reply began:" in str(caught.value)
    assert raw.decode() in str(caught.value)


@pytest.mark.parametrize("planted_kind", ["file", "symlink"])
def test_omp_refuses_planted_result_leaf_without_changing_it(tmp_path, planted_kind):
    node = _provider_node(tmp_path, SOURCE)
    attempt_files, workspace_files, _result_path = _attempt_files(tmp_path)
    planted = attempt_files.workspace / "result.json"
    target = tmp_path / "outside.json"
    target.write_bytes(b"outside target")
    original = b'{"ok":false}'
    if planted_kind == "file":
        planted.write_bytes(original)
    else:
        planted.symlink_to(target)

    with pytest.raises(FileExistsError):
        launch_provider(node, ResolvedProviderInput("request", {}, {}, []), "site",
            executor=_fake_executor(_execution(b'{"ok":true}'),
                metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value),
            attempt_files=attempt_files, workspace_files=workspace_files,
            result_path="effects/site/attempt-1/result.json")

    if planted_kind == "file":
        assert planted.read_bytes() == original
    else:
        assert planted.is_symlink() and planted.resolve() == target
        assert target.read_bytes() == b"outside target"


def test_ordinary_provider_normalized_stdout_alone_does_not_create_result(tmp_path):
    node = _provider_node(tmp_path, SOURCE)
    attempt_files, workspace_files, result_path = _attempt_files(tmp_path)
    resolved = ResolvedProviderInput("request", {}, {}, [])
    launch_provider(node, resolved, "site",
        executor=_fake_executor(_execution(b'{"ok":true}', raw=b"ordinary stdout"),
            metadata_mode=None),
        attempt_files=attempt_files, workspace_files=workspace_files,
        result_path=result_path)

    with pytest.raises(ProviderPerformerError) as caught:
        provider_result(node, resolved, attempt_files, workspace_files, result_path)

    assert caught.value.code == "provider_result_missing"
    assert not attempt_files.exists("result.json")


def test_public_evaluated_omp_run_commits_normalized_result_from_fake_transport(
    tmp_path, monkeypatch
):
    fixture = _fixture(tmp_path)
    source, providers, prompts, _request = fixture
    providers.write_text(json.dumps({"providers.review": "omp"}), encoding="utf-8")
    raw = b'{"response":{"text":"transport frame"}}'
    normalized = b'{"ok":true}'
    invocation = ProviderInvocation(
        command=["fake-provider"], input_mode=InputMode.STDIN,
        metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
    )

    def prepare(_executor, **_kwargs):
        return invocation, None

    def execute(_executor, actual_invocation, **_kwargs):
        assert actual_invocation is invocation
        return _execution(normalized, raw=raw)

    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare)
    monkeypatch.setattr(ProviderExecutor, "execute", execute)
    monkeypatch.chdir(tmp_path)

    result = cli_main(["run", str(source), "--source-root", str(source.parent),
        "--provider-externs-file", str(providers), "--prompt-externs-file", str(prompts),
        "--input", "message=typed input", "--quiet"])

    assert result == 0
    run_root, snapshot = _public_snapshot(tmp_path, fixture)
    started, committed = [entry.data for entry in snapshot.entries
        if entry.data["record"] in {"started", "committed"}]
    attempt = run_root / Path(committed["result_path"]).parent
    assert committed["value"] == {"ok": True}
    assert started["input_parts"] == committed["input_parts"]
    assert started["input_parts"]["delivery"] == canonical_sha256("legacy")
    assert attempt.joinpath("result.json").read_bytes() == normalized
    assert attempt.joinpath("stdout.txt").read_bytes() == raw
    assert attempt.joinpath("stderr.txt").read_bytes() == b"transport stderr\n"
    prompt = attempt.joinpath("prompt.txt").read_bytes()
    assert started["input_parts"]["prompt"] == "sha256:" + hashlib.sha256(prompt).hexdigest()


def test_public_evaluated_omp_missing_normalized_rejects_planted_result_and_records_failure(
    tmp_path, monkeypatch
):
    fixture = _fixture(tmp_path)
    source, providers, prompts, _request = fixture
    providers.write_text(json.dumps({"providers.review": "omp"}), encoding="utf-8")
    raw = b'{"response":{"text":"transport frame"}}'
    planted = b'{"ok":true}'
    invocation = ProviderInvocation(
        command=["fake-provider"], input_mode=InputMode.STDIN,
        metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
    )

    def prepare(_executor, **kwargs):
        invocation.env.update(kwargs["env"])
        return invocation, None

    def execute(_executor, _actual_invocation, **_kwargs):
        Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_bytes(planted)
        return _execution(None, raw=raw)

    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare)
    monkeypatch.setattr(ProviderExecutor, "execute", execute)
    monkeypatch.chdir(tmp_path)

    result = cli_main(["run", str(source), "--source-root", str(source.parent),
        "--provider-externs-file", str(providers), "--prompt-externs-file", str(prompts),
        "--input", "message=typed input", "--quiet"])

    assert result == 1
    run_root, snapshot = _public_snapshot(tmp_path, fixture)
    started, failed, terminal = [entry.data for entry in snapshot.entries]
    attempt = run_root / Path(started["result_path"]).parent
    assert failed["code"] == terminal["code"] == "provider_result_missing"
    assert failed["exit_info"] == {} and not snapshot.active_commits
    assert terminal["outcome"] == "failed"
    assert attempt.joinpath("result.json").read_bytes() == planted
    assert attempt.joinpath("stdout.txt").read_bytes() == raw
    assert attempt.joinpath("stderr.txt").read_bytes() == b"transport stderr\n"


def _contract_lines(prompt, result_path):
    lines = prompt.splitlines()
    format_at = next(index for index, line in enumerate(lines) if line.startswith("  format: ") or line == "{")
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
    assert commit.data["input_parts"]["delivery"] == canonical_sha256("file/2")


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


def test_public_file2_nested_guided_calls_compile_run_and_resume_without_dispatch(tmp_path):
    from tests.test_workflow_evaluated_resume import _snapshot

    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defpath Report :kind relpath :under "artifacts/review" :must-exist false)
      (defrecord Notes (notes String :description "call one leaf"))
      (defrecord Evidence (evidence Notes :description "call one ancestor") (report Report))
      (defunion Choice
        (YES (ok Bool :description "call two yes") (evidence Notes))
        (NO (ok Bool :description "call two no") (reason String)))
      (defworkflow run ((message String)) -> Choice
        (let* ((first (provider-result providers.review :prompt prompts.base :inputs ()
                       :returns (result Evidence :description "first own contract")))
               (second (provider-result providers.review :prompt prompts.base :inputs (first)
                        :returns (result Choice :description "second own contract"))))
          second)))'''
    fixture = _fixture(tmp_path, source)
    cli_source, providers, prompts, _request = fixture
    env = _env(tmp_path, provider=True)
    env['PROVIDER_SHIM_RESULTS'] = json.dumps([
        '{"evidence":{"notes":"observed"},"report":"artifacts/review/report.md"}',
        '{"variant":"NO","ok":false,"reason":"later"}',
    ])
    compiled = _env_cli(tmp_path, ['compile', str(cli_source), '--source-root', str(tmp_path),
        '--provider-externs-file', str(providers), '--prompt-externs-file', str(prompts)], env)
    assert compiled.returncode == 0, compiled.stderr
    completed = _env_cli(tmp_path, ['run', str(cli_source), '--source-root', str(tmp_path),
        '--provider-externs-file', str(providers), '--prompt-externs-file', str(prompts),
        '--input', 'message=typed input'], env)
    assert completed.returncode == 0, completed.stderr
    run_root, snapshot = _public_snapshot(tmp_path, fixture)
    commits = [entry.data for entry in snapshot.entries if entry.data['record'] == 'committed']
    assert len(commits) == 2
    assert {row['input_parts']['delivery'] for row in commits} == {canonical_sha256('file/2')}
    prompts = [(run_root / Path(row['result_path']).parent / 'prompt.txt').read_text() for row in commits]
    first, second = prompts
    assert '"evidence": {' in first and '"notes": <string>' in first and '"report": <relpath>' in first
    assert 'first own contract' in first and 'second own contract' not in first
    assert 'second own contract' in second and 'first own contract' not in second
    assert '"variant": "YES"' in second and '"variant": "NO"' in second
    assert commits[0]['value']['evidence'] == {'notes': 'observed'}
    assert commits[1]['value'] == {'variant': 'NO', 'ok': False, 'reason': 'later'}
    for row, prompt in zip(commits, prompts, strict=True):
        assert row['input_parts']['prompt'] == 'sha256:' + hashlib.sha256(prompt.encode()).hexdigest()
        assert prompt.count(os.path.relpath(run_root / row['result_path'], tmp_path)) == 1
    before = _snapshot(tmp_path / '.orchestrate')
    requests_before = (tmp_path / 'requests.jsonl').read_bytes()
    for _ in range(2):
        resumed = _env_cli(tmp_path, ['resume', run_root.name], env)
        assert resumed.returncode == 0, resumed.stderr
        assert _snapshot(tmp_path / '.orchestrate') == before
        assert (tmp_path / 'requests.jsonl').read_bytes() == requests_before
