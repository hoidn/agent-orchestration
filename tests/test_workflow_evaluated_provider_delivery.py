"""Versioned provider result delivery through the shared performer."""

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
    perform_provider,
)
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.contracts.prompt_contract import _RELPATH_GUIDANCE
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.closed.sites import _ast_nodes
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
    result = perform_provider(node, resolved, "site", executor=executor,
        attempt_files=attempt_files, workspace_files=workspace_files,
        result_path=result_path)
    return result, (
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
    with pytest.raises(ProviderPerformerError) as caught:
        _launch_and_read(tmp_path, node, normalized,
            metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value)
    assert caught.value.code == "provider_result_invalid"
    assert (tmp_path / "effects/site/attempt-1/result.json").read_bytes() == normalized


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
        perform_provider(node, ResolvedProviderInput("request", {}, {}, []), "site",
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
    assert raw.decode() not in str(caught.value)


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
        perform_provider(node, ResolvedProviderInput("request", {}, {}, []), "site",
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
    with pytest.raises(ProviderPerformerError) as caught:
        perform_provider(node, resolved, "site",
            executor=_fake_executor(_execution(b'{"ok":true}', raw=b"ordinary stdout"), metadata_mode=None),
            attempt_files=attempt_files, workspace_files=workspace_files, result_path=result_path)

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


@pytest.mark.parametrize(("name", "command_omp", "expected"), [
    ("local_transport", True, "legacy"),
    ("omp_looking_plain", False, "file/2"),
    ("mixed_command_and_session", False, "file/2"),
])
def test_fresh_delivery_matches_actual_prepared_command_variant(tmp_path, name, command_omp, expected):
    from dataclasses import replace
    from orchestrator.providers.registry import ProviderRegistry
    from orchestrator.providers.types import ProviderParams
    from orchestrator.workflow.evaluated.providers import current_provider_delivery_name

    registry = ProviderRegistry()
    template = replace(registry.get("omp"), name=name,
        command_metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value if command_omp else None)
    registry.register(template)
    executor = ProviderExecutor(tmp_path, registry)
    invocation, error = executor.prepare_invocation(name, ProviderParams(), {},
        prompt_content="request", session_request=None)
    assert error is None, error
    assert invocation.metadata_mode == template.command_metadata_mode
    assert current_provider_delivery_name(name, registry) == expected


@pytest.mark.parametrize("target", ["2.35", "3.0"])
@pytest.mark.parametrize("mode", ["success", "invalid", "misdirected", "nonzero"])
def test_public_subprocess_omp_shim_uses_authoritative_attempt(tmp_path, target, mode):
    import subprocess
    import sys
    from tests.test_provider_execution import _omp_stream_bytes

    source = SOURCE.replace('"2.35"', json.dumps(target)).replace(
        ':model "chosen-model" :effort "low" ', '')
    if target == "3.0":
        source = source.replace('(defmodule main)', '(:budget 1000) (defmodule main)').replace(':inputs (message) ', '')
    fixture = _fixture(tmp_path, source)
    fixture[1].write_text(json.dumps({"providers.review": "local_transport"}))
    payload = {'invalid': '{"ok":"wrong"}', 'misdirected': '"result saved elsewhere"'}.get(mode, '{"ok":true}')
    stream = _omp_stream_bytes().replace(b'"text":"OK"', b'"text":' + json.dumps(payload).encode())
    (tmp_path / "omp-frames.jsonl").write_bytes(stream)
    shim = tmp_path / "local-transport.py"
    shim.write_text("import os,sys\nfrom pathlib import Path\n"
        "assert 'ORCHESTRATOR_OUTPUT_BUNDLE_PATH' not in os.environ\n"
        "Path('transport-called').write_text('yes')\n"
        + ("Path('other-result.json').write_text('{\"ok\":true}')\n" if mode == "misdirected" else "")
        + "sys.stdout.buffer.write(Path('omp-frames.jsonl').read_bytes())\n"
        + ("sys.exit(9)\n" if mode == "nonzero" else ""))
    # Redirect only the physical local transport; the public CLI, preparation,
    # OMP parser, shared performer and strict result validators still execute.
    (tmp_path / "sitecustomize.py").write_text(
        "from dataclasses import replace\nimport sys\n"
        "from orchestrator.providers.registry import ProviderRegistry\n"
        "from orchestrator.providers.executor import ProviderExecutor\n"
        "from tests.test_provider_execution import _omp_expectation\n"
        "original_registry = ProviderRegistry._load_builtin_providers\n"
        "def templates(self):\n"
        "    providers = original_registry(self)\n"
        "    providers['local_transport'] = replace(providers['omp'], name='local_transport')\n"
        "    return providers\n"
        "ProviderRegistry._load_builtin_providers = templates\n"
        "original_prepare = ProviderExecutor.prepare_invocation\n"
        "def prepare(self, *args, **kwargs):\n"
        "    invocation, error = original_prepare(self, *args, **kwargs)\n"
        "    if invocation is not None:\n"
        + f"        invocation.command = [sys.executable, {str(shim)!r}]\n"
        "        invocation.omp_transport_expectation = _omp_expectation()\n"
        "        invocation.env.pop('ORCHESTRATOR_OUTPUT_BUNDLE_PATH', None)\n"
        "    return invocation, error\n"
        "ProviderExecutor.prepare_invocation = prepare\n")
    result = subprocess.run([sys.executable, "-m", "orchestrator", "run", str(fixture[0]),
        "--source-root", str(tmp_path), "--provider-externs-file", str(fixture[1]),
        "--prompt-externs-file", str(fixture[2]), "--input", "message=typed input"], cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path) + os.pathsep + str(Path(__file__).parents[1])},
        capture_output=True, text=True, timeout=45)
    assert (tmp_path / "transport-called").exists(), result.stderr
    assert result.returncode == (0 if mode == "success" else 1), result.stderr
    (run_root,) = (tmp_path / ".orchestrate/runs").iterdir()
    (attempt,) = run_root.glob("effects/*/attempt-1")
    assert attempt.joinpath("stdout.txt").read_bytes() == stream
    if mode == "nonzero":
        assert not attempt.joinpath("result.json").exists()
    else:
        assert attempt.joinpath("result.json").read_bytes() == payload.encode()
    assert list(run_root.rglob("result.json")) == ([] if mode == "nonzero" else [attempt / "result.json"])
    if mode == "misdirected":
        assert (tmp_path / "other-result.json").read_text() == '{"ok":true}'


@pytest.mark.parametrize("payload", [b'{"n":1,"extra":"PRIVATE"}', b'{"n":true}',
    b'{"n":1.0}', b'{"n":9223372036854775808}'])
def test_omp_materialization_preserves_strict_native_result_boundary(tmp_path, payload):
    from tests.test_workflow_dynamic_performers import _whole_value_contract

    node = _provider_node(tmp_path, SOURCE.replace("(ok Bool)", "(n Int)"))
    node["contract"] = _whole_value_contract(tmp_path, "(defrecord Result (n Int))", "Result")
    attempt_files, workspace_files, result_path = _attempt_files(tmp_path)
    try:
        with pytest.raises(ProviderPerformerError):
            perform_provider(node, ResolvedProviderInput("request", {}, {}, []), "site",
                executor=_fake_executor(_execution(payload),
                    metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value),
                attempt_files=attempt_files, workspace_files=workspace_files,
                result_path=result_path, native_result=True)
        assert attempt_files.read("result.json") == payload
        assert attempt_files.read("stdout.txt") == b'{"transport":"frame"}'
    finally:
        attempt_files.close()
        workspace_files.close()
