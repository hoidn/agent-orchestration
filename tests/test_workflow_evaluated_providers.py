"""Portable provider requests use the evaluated attempt lifecycle."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.evaluated.providers import FILE_DELIVERY_NAME
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.contracts.prompt_contract import render_output_bundle_contract_block
from orchestrator.contracts.prompt_json_shape import render_json_shape_contract_block
from orchestrator.workflow.run_ref.contracts import canonical_sha256


SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defworkflow run ((message String)) -> Result
    (provider-result providers.review :prompt prompts.base
      :inputs (message) :model "chosen-model" :effort "low" :returns Result)))'''

SHIM = r'''import json, os, sys, time
from pathlib import Path
prompt = sys.stdin.buffer.read()
with Path("requests.jsonl").open("a", encoding="utf-8") as out:
    out.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(),
        "prompt": prompt.decode("utf-8"), "env": {key: os.environ.get(key)
        for key in ("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY")}}) + "\n")
mode = os.environ.get("PROVIDER_SHIM_MODE", "success")
if mode == "silent": sys.exit(0)
if mode == "nul": sys.stdout.buffer.write(b"I wrote it\x00 here \x1b[31mred\x1b[0m\n"); sys.exit(0)
if mode != "empty":
    sys.stdout.buffer.write(b"complete stdout\n"); sys.stdout.buffer.flush()
    sys.stderr.buffer.write(b"complete stderr\n"); sys.stderr.buffer.flush()
if mode == "timeout": time.sleep(10)
if mode == "nonzero": sys.exit(9)
result = os.environ.get("PROVIDER_SHIM_RESULT", '{"ok":true,"extra":7}').encode()
if "PROVIDER_SHIM_RESULTS" in os.environ:
    index = len(Path("requests.jsonl").read_text().splitlines()) - 1
    result = json.loads(os.environ["PROVIDER_SHIM_RESULTS"])[index].encode()
if mode == "stdout-only": sys.stdout.buffer.write(result); sys.exit(0)
target = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
if mode == "wrong-path": target = Path("other-result.json")
if mode == "invalid": result = b'{"ok":"not-bool"}'
if mode == "chdir":
    os.makedirs("candidates/alpha", exist_ok=True); os.chdir("candidates/alpha")
    target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(result)
'''


def _fixture(root: Path, source: str = SOURCE, *, prompt_kind: str = "asset_file", source_dir="."):
    workflow_root = root / source_dir
    workflow_root.mkdir(exist_ok=True)
    path = workflow_root / "main.orc"
    path.write_text(source, encoding="utf-8")
    (root / "prompt.md").write_text("ASSET SOURCE\n", encoding="utf-8")
    (workflow_root / "prompt.md").write_text("ASSET SOURCE\n", encoding="utf-8")
    providers = root / "providers.json"
    providers.write_text(json.dumps({"providers.review": "codex"}), encoding="utf-8")
    prompts = root / "prompts.json"
    prompts.write_text(json.dumps({"prompts.base": {prompt_kind: "prompt.md"}}), encoding="utf-8")
    binary = root / "bin" / "codex"
    binary.parent.mkdir()
    binary.write_text(f"#!{sys.executable}\n" + SHIM, encoding="utf-8")
    binary.chmod(0o700)
    request = FrontendBuildRequest(source_path=path, source_roots=(workflow_root,), workspace_root=root,
        provider_externs_path=providers, prompt_externs_path=prompts)
    return path, providers, prompts, request


def _cli(root: Path, fixture, *, mode="success", extra=(), payload='{"ok":true,"extra":7}'):
    source, providers, prompts, _request = fixture
    return subprocess.run([sys.executable, "-B", "-m", "orchestrator", "run", str(source),
        "--source-root", str(source.parent),
        "--provider-externs-file", str(providers), "--prompt-externs-file", str(prompts),
        "--input", "message=typed input", *extra], cwd=root,
        env={**os.environ, "PATH": str(root / "bin") + os.pathsep + os.environ["PATH"],
             "PYTHONPATH": str(Path(__file__).parents[1]), "PYTHONDONTWRITEBYTECODE": "1",
             "PROVIDER_SHIM_MODE": mode, "PROVIDER_SHIM_RESULT": payload},
        capture_output=True, text=True, check=False)


def _requests(root):
    path = root / "requests.jsonl"
    return [json.loads(row) for row in path.read_text().splitlines()] if path.exists() else []


def workspace_relative(value: str, workspace) -> str:
    """R2 in its command spelling: absolute values are relativized, relative ones pass through."""
    return os.path.relpath(value, workspace).replace(os.sep, "/") if os.path.isabs(value) else value


def _orchestrate_snapshot(root):
    from tests.test_workflow_evaluated_resume import _snapshot

    return _snapshot(root / ".orchestrate")


def _cache_snapshot(root):
    return {name: value for name, value in _orchestrate_snapshot(root).items() if name.startswith("build/")}


def _spy_provider_prepare(monkeypatch):
    calls = []
    prepare = ProviderExecutor.prepare_invocation

    def spy(executor, *args, **kwargs):
        calls.append((args, kwargs))
        return prepare(executor, *args, **kwargs)

    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", spy)
    return calls


def _assert_cli_resumes_unchanged(root, run_id, snapshot, request_bytes, count=1):
    from tests.test_workflow_evaluated_resume import _resume_cli

    for _ in range(count):
        result = _resume_cli(root, run_id)
        assert result.returncode == 0, result.stderr
        assert _orchestrate_snapshot(root) == snapshot
        assert (root / "requests.jsonl").read_bytes() == request_bytes


def _assert_cli_resume_refusal(root, run_id, snapshot, request_bytes, *, code, diagnostic):
    from tests.test_workflow_evaluated_resume import _resume_cli

    result = _resume_cli(root, run_id)
    assert result.returncode == code, result.stderr
    assert diagnostic in result.stderr
    assert _orchestrate_snapshot(root) == snapshot
    assert (root / "requests.jsonl").read_bytes() == request_bytes


def _public_snapshot(root, fixture):
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    program = build_closed_program_bundle(fixture[3]).program
    return run_root, read_memo(run_root / "memo.jsonl", site_classes(program))


def _assert_attempt_evidence(run_root, commit, request):
    attempt = run_root / Path(commit["result_path"]).parent
    assert (attempt / "prompt.txt").read_text() == request["prompt"]
    assert (attempt / "stdout.txt").read_bytes() == b"complete stdout\n"
    assert (attempt / "stderr.txt").read_bytes() == b"complete stderr\n"
    assert commit["result_digest"] == "sha256:" + hashlib.sha256((attempt / "result.json").read_bytes()).hexdigest()


def _assert_public_request_contract(root, run_root, commit, request):
    result_path = os.path.relpath(run_root / commit["result_path"], root)
    assert request["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] == os.path.join(root, result_path)
    assert request["env"]["ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY"] == (
        "sha256:" + hashlib.sha256(commit["identity"].encode()).hexdigest())
    assert request["cwd"] == str(root)
    assert "chosen-model" in request["argv"]
    assert "model_reasoning_effort=low" in request["argv"]


def test_public_provider_dispatches_once_and_commits_its_typed_result(tmp_path):
    fixture = _fixture(tmp_path)
    result = _cli(tmp_path, fixture)
    assert result.returncode == 0, result.stderr
    (request,) = _requests(tmp_path)
    run_root, snapshot = _public_snapshot(tmp_path, fixture)
    (started,) = [entry.data for entry in snapshot.entries if entry.data["record"] == "started"]
    (commit,) = [entry.data for entry in snapshot.entries if entry.data["record"] == "committed"]
    assert commit["value"] == {"ok": True}
    assert commit["effect_class"] == "provider"
    assert started["input_parts"] == commit["input_parts"]
    assert started["implementation_files"] == commit["implementation_files"] == {}
    _assert_public_request_contract(tmp_path, run_root, commit, request)
    _assert_attempt_evidence(run_root, commit, request)


def test_public_provider_that_changes_directory_still_writes_the_pinned_attempt(tmp_path):
    fixture = _fixture(tmp_path)
    result = _cli(tmp_path, fixture, mode="chdir")
    assert result.returncode == 0, result.stderr
    run_root, snapshot = _public_snapshot(tmp_path, fixture)
    (commit,) = snapshot.active_commits.values()
    (request,) = _requests(tmp_path)
    _assert_public_request_contract(tmp_path, run_root, commit.data, request)
    assert (run_root / commit.data["result_path"]).is_file()
    assert not (tmp_path / "candidates" / "alpha" / ".orchestrate").exists()
    assert request["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] not in request["prompt"]
    assert commit.data["input_parts"]["prompt"] == "sha256:" + hashlib.sha256(request["prompt"].encode()).hexdigest()


def test_public_completed_provider_resume_is_readonly_through_service_and_cli(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    result = _cli(tmp_path, fixture)
    assert result.returncode == 0, result.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    (commit,) = read_memo(authority.memo_path, site_classes(authority.program)).active_commits.values()
    (request,) = _requests(tmp_path)
    _assert_public_request_contract(tmp_path, run_root, commit.data, request)
    _assert_attempt_evidence(run_root, commit.data, request)
    assert commit.data["input_parts"]["delivery"] == canonical_sha256("file/2")
    from orchestrator.cli.commands.resume import resume_workflow

    monkeypatch.chdir(tmp_path)
    before = _orchestrate_snapshot(tmp_path)
    requests_before = (tmp_path / "requests.jsonl").read_bytes()
    prepare_calls = _spy_provider_prepare(monkeypatch)
    assert resume_workflow(run_root.name) == 0
    assert prepare_calls == []
    _assert_cli_resumes_unchanged(tmp_path, run_root.name, before, requests_before)


def _assert_failed_attempt(run_root, snapshot, mode):
    assert [entry.data["record"] for entry in snapshot.entries] == ["started", "failed", "terminal"]
    started, failed, terminal = [entry.data for entry in snapshot.entries]
    assert started["attempt"] == failed["attempt"] == 1
    assert terminal["outcome"] == "failed"
    _assert_failed_attempt_streams(run_root, started)
    if mode == "invalid":
        assert failed["code"] == "provider_result_invalid"
        assert failed["violations"]
    if mode == "timeout":
        assert failed["code"] == "provider_timeout"


def _assert_failed_attempt_streams(run_root, started):
    attempt = run_root / Path(started["result_path"]).parent
    assert (attempt / "prompt.txt").is_file()
    assert (attempt / "stdout.txt").read_bytes().startswith(b"complete stdout\n")
    assert (attempt / "stderr.txt").read_bytes() == b"complete stderr\n"


@pytest.mark.parametrize("mode", ["nonzero", "timeout", "invalid", "wrong-path", "stdout-only"])
def test_public_provider_failure_keeps_one_attempt_and_complete_streams(tmp_path, mode):
    source = SOURCE.replace(':effort "low"', ':effort "low" :timeout-sec 1') if mode == "timeout" else SOURCE
    fixture = _fixture(tmp_path, source)
    result = _cli(tmp_path, fixture, mode=mode, extra=("--max-retries", "4", "--retry-delay", "0"))
    assert result.returncode == 1, result.stderr
    assert len(_requests(tmp_path)) == 1
    run_root, snapshot = _public_snapshot(tmp_path, fixture)
    _assert_failed_attempt(run_root, snapshot, mode)


def test_public_provider_empty_streams_are_exclusive_attempt_evidence(tmp_path):
    fixture = _fixture(tmp_path)
    assert _cli(tmp_path, fixture, mode="empty").returncode == 0
    (request,) = _requests(tmp_path)
    attempt = (tmp_path / request["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).parent
    assert (attempt / "stdout.txt").read_bytes() == (attempt / "stderr.txt").read_bytes() == b""


@pytest.mark.parametrize(("declaration", "result_type", "payload", "expected"), [
    ("", "Bool", "false", False),
    ("(defrecord Empty)", "Empty", '{"extra":1}', {}),
    ("(defrecord Empty) (defrecord Box (empty Empty) (n Int))", "Box", '{"empty":{},"n":7,"extra":9}', {"empty": {}, "n": 7}),
    ("(defrecord Empty) (defrecord Box (empty Empty))", "Box", '{}', None),
    ("(defunion Choice (Ready (n Int)) (Skip (reason String)))", "Choice", '{"variant":"Ready","n":5,"other":"ignored"}', {"variant": "Ready", "n": 5}),
    ("(defunion Choice (Ready (n Int)) (Skip (reason String)))", "Choice", '{"variant":"Skip","reason":"later"}', {"variant": "Skip", "reason": "later"}),
    ("", "Float", "NaN", None),
    ('(defpath Artifact :kind relpath :under "artifacts" :must-exist true)', "Artifact", '"artifacts/missing.txt"', None),
])
def test_provider_result_uses_shared_checked_projection(tmp_path, declaration, result_type, payload, expected):
    source = SOURCE.replace("(defrecord Result (ok Bool))", declaration).replace("Result", result_type)
    fixture = _fixture(tmp_path, source)
    result = _cli(tmp_path, fixture, payload=payload)
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    snapshot = read_memo(run_root / "memo.jsonl", site_classes(build_closed_program_bundle(fixture[3]).program))
    assert result.returncode == (1 if expected is None else 0), result.stderr
    if expected is not None:
        assert snapshot.terminal.data["value"] == expected
    else:
        assert not snapshot.active_commits


@pytest.mark.parametrize("output_exists", [False, True])
def test_defprompt_output_position_is_validated_before_commit(tmp_path, output_exists):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defrecord Result (ok Bool))
      (defpath Report :kind relpath :under "artifacts" :must-exist false)
      (defprompt review (:fills (report :path :out Report)) -> Result "Report={report}")
      (defworkflow run ((message String) (report Report)) -> Result
        (provider-result providers.review :prompt (review :report report))))'''
    fixture = _fixture(tmp_path, source)
    if output_exists:
        (tmp_path / "artifacts").mkdir()
        (tmp_path / "artifacts" / "report.txt").write_text("report")
    result = _cli(tmp_path, fixture, extra=("--input", "report=artifacts/report.txt"))
    assert result.returncode == (0 if output_exists else 1), result.stderr
    assert len(_requests(tmp_path)) == 1


@pytest.mark.parametrize("source_kind", ["asset_file", "input_file"])
def test_complete_provider_request_preserves_preparation_and_dispatch_contract(tmp_path, monkeypatch, source_kind):
    from tests.test_workflow_evaluated_provider_lifecycle import _run, _execute

    with _run(tmp_path, monkeypatch, prompt_kind=source_kind) as (built, authority):
        observed = {}
        real_prepare, real_execute = ProviderExecutor.prepare_invocation, ProviderExecutor.execute

        def prepare(executor, *args, **kwargs):
            observed["prepare_args"], observed["prepare_kwargs"] = args, kwargs
            invocation, error = real_prepare(executor, *args, **kwargs)
            observed["invocation"] = invocation
            return invocation, error

        def execute(executor, *args, **kwargs):
            observed["execute_args"], observed["execute_kwargs"] = args, kwargs
            return real_execute(executor, *args, **kwargs)

        with patch("orchestrator.workflow.evaluated.prompts.render_json_shape_contract_block",
                   wraps=render_json_shape_contract_block) as render_shape, \
                patch.object(ProviderExecutor, "prepare_invocation", prepare), \
                patch.object(ProviderExecutor, "execute", execute):
            code, value = _execute(tmp_path, built, authority)
            assert code == 0 and value == {"ok": True}
        snapshot = read_memo(authority.memo_path, site_classes(built.program))
        (commit,) = snapshot.active_commits.values()
        current = observed["prepare_kwargs"]
        assert observed["prepare_args"] == ()
        assert current["params"].params == {}
        assert current["params"].input_file == ("prompt.md" if source_kind == "input_file" else None)
        assert current["params"].output_file is None
        bundle = current["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        assert current == {
            "provider_name": "codex", "params": current["params"], "context": {},
            "prompt_content": current["prompt_content"], "session_request": None,
            "env": {"ORCHESTRATOR_OUTPUT_BUNDLE_PATH": bundle}, "secrets": None,
            "timeout_sec": None, "provider_call_policy": {"model": "chosen-model", "effort": "low"},
            "provider_session_dir": None, "provider_session_identity": None,
        }
        assert os.path.isabs(bundle) and Path(bundle) == authority.run_root / commit.data["result_path"]
        node = next(row for row in built.program.tree["body"].values()
            if isinstance(row, dict) and row.get("class") == "provider")
        (rendered_contract, rendered_result, rendered_path), = [call.args for call in render_shape.call_args_list]
        assert rendered_contract == node["contract"] and rendered_result == node["result"]
        assert rendered_path == workspace_relative(bundle, tmp_path)
        assert commit.data["input_parts"]["delivery"] == canonical_sha256(FILE_DELIVERY_NAME)
        assert commit.data["input_parts"]["prompt"] == "sha256:" + hashlib.sha256(
            current["prompt_content"].encode()).hexdigest()
        assert current["prompt_content"].index("ASSET SOURCE") < current["prompt_content"].index("typed input")
        invocation = observed["invocation"]
        assert invocation.prompt == invocation.prepared_prompt == current["prompt_content"]
        assert invocation.env == {**os.environ, **current["env"]}
        assert invocation.command == ["codex", "exec", "--model", "chosen-model", "--config",
            "model_reasoning_effort=low", "--dangerously-bypass-approvals-and-sandbox"]
        assert invocation.input_mode == "stdin"
        assert invocation.output_file is invocation.session_request is invocation.provider_session_dir is None
        assert invocation.command_variant == "command" and invocation.turn_boundary_resume
        assert invocation.timeout_sec is invocation.metadata_mode is invocation.omp_transport_expectation is None
        assert invocation.metadata == {} and not invocation.terminate_process_tree
        assert invocation.inherited_fds == () and invocation.inherited_fd_authority is None
        policy = invocation.prepared_provider_policy
        assert (policy.provider_name, policy.model, policy.effort, policy.timeout_sec, policy.input_mode) == (
            "codex", "chosen-model", "low", None, "stdin")
        assert len(observed["execute_args"]) == 1 and observed["execute_args"][0] is invocation
        assert observed["execute_kwargs"] == {"cwd": tmp_path, "stream_output": False,
            "session_runtime": None, "execution_env_overlay": {
                "ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY": "sha256:" + hashlib.sha256(commit.data["identity"].encode()).hexdigest()}}
        (request,) = _requests(tmp_path)
        assert request["prompt"] == current["prompt_content"]
        assert request["cwd"] == str(tmp_path) and request["argv"] == invocation.command[1:]
        _assert_attempt_evidence(authority.run_root, commit.data, request)


def _assert_prompt_path_parity(node, current, previous, workspace, *, previous_delivery="legacy"):
    """The prompts differ only in the contract block: the flat route renders `legacy`, a new evaluated attempt `file/2`."""
    payload, key = node["contract"]["payload"], "ORCHESTRATOR_OUTPUT_BUNDLE_PATH"
    previous_path = workspace_relative(previous["env"][key], workspace)
    flat_block = (render_json_shape_contract_block(node["contract"], node["result"], previous_path)
        if previous_delivery == "file/2" else render_output_bundle_contract_block(
            {**payload, "path": previous_path}, delivery=previous_delivery))
    current_block = render_json_shape_contract_block(node["contract"], node["result"],
        workspace_relative(current["env"][key], workspace))
    assert flat_block in previous["prompt_content"]
    assert current["prompt_content"] == previous["prompt_content"].replace(flat_block, current_block, 1)
    return flat_block, current_block


def _assert_retry_request_parity(program, current, previous):
    assert current["argv"] == previous["argv"]
    assert set(current["env"]) == set(previous["env"])
    output_path = "ORCHESTRATOR_OUTPUT_BUNDLE_PATH"
    assert {key: value for key, value in current["env"].items() if key != output_path} == {
        key: value for key, value in previous["env"].items() if key != output_path}
    assert os.path.isabs(current["env"][output_path]) and os.path.isabs(previous["env"][output_path])
    (node,) = [row for row in program.tree["body"].values()
        if isinstance(row, dict) and row.get("class") == "provider"]
    _assert_prompt_path_parity(node,
        {"env": current["env"], "prompt_content": current["prompt"]},
        {"env": previous["env"], "prompt_content": previous["prompt"]}, current["cwd"], previous_delivery="file/2")


@pytest.mark.parametrize("document_kind", ["doc", "dependencies"])
def test_public_nested_provider_smoke_keeps_source_kind_and_document_evidence(tmp_path, document_kind):
    doc_call = '(provider-result providers.review :prompt (document :note note :message message))'
    dependency_clause = ':prompt-dependencies (:required (note))' if document_kind == "dependencies" else ""
    body = f'''(let* ((first (ask message "AUTHORED SUFFIX"))
        (second (provider-result providers.review :prompt prompts.workspace :inputs (message)
          {dependency_clause} :returns Bool))) {doc_call if document_kind == "doc" else "second"})'''
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule main) (export run)
      (defpath Note :kind relpath :under "artifacts" :must-exist true)
      (defprompt document (:fills (note :doc Note) (message :text)) -> Bool "Message={{message}}")
      (defproc ask ((name String) (name__2 String)) -> Bool
        :effects ((uses-provider providers.review)) :lowering private-workflow
        (provider-result providers.review :prompt prompts.base :inputs (name name name__2)
          :model "nested-model" :effort "low" :returns Bool))
      (defworkflow run ((message String) (note Note)) -> Bool {body}))'''
    fixture = _fixture(tmp_path, source, source_dir="source")
    (tmp_path / "prompt.md").write_text("WORKSPACE SOURCE\n")
    fixture[2].write_text(json.dumps({"prompts.base": {"asset_file": "prompt.md"},
        "prompts.workspace": {"input_file": "prompt.md"}}))
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "note.md").write_text("DOCUMENT BYTES\n")
    result = _cli(tmp_path, fixture, payload="true", extra=("--input", "note=artifacts/note.md"))
    assert result.returncode == 0, result.stderr
    requests = _requests(tmp_path)
    assert "nested-model" in requests[0]["argv"] and "model_reasoning_effort=low" in requests[0]["argv"]
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    program = authority.program
    commits = list(read_memo(authority.memo_path, site_classes(program)).active_commits.values())
    assert commits[0].data["input_parts"]["source:asset_file:prompt.md"] == "sha256:" + hashlib.sha256(b"ASSET SOURCE\n").hexdigest()
    assert commits[1].data["input_parts"]["source:input_file:prompt.md"] == "sha256:" + hashlib.sha256(b"WORKSPACE SOURCE\n").hexdigest()
    assert commits[-1].data["input_parts"]["dependency:artifacts/note.md"] == "sha256:" + hashlib.sha256(b"DOCUMENT BYTES\n").hexdigest()
    assert len(commits) == len(requests) == (3 if document_kind == "doc" else 2)
    _assert_public_nested_labels(program, requests[0], commits[0].data)
    for request, commit in zip(requests, commits, strict=True):
        assert request["env"]["ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY"] == "sha256:" + hashlib.sha256(commit.data["identity"].encode()).hexdigest()
    before = _orchestrate_snapshot(tmp_path)
    requests_before = (tmp_path / "requests.jsonl").read_bytes()
    _assert_cli_resumes_unchanged(tmp_path, run_root.name, before, requests_before, count=2)


def _assert_public_nested_labels(program, request, commit):
    from orchestrator.contracts.closed_program.sites import _ast_nodes

    (call,) = [node for node in _ast_nodes(program.tree["body"]) if node.get("k") == "call"]
    body = program.tree["definitions"][call["callee"]]["body"]
    (provider,) = [node for node in _ast_nodes(body) if node.get("class") == "provider"]
    assert [row[0] for row in provider["inputs"]] == ["name", "name__3", "name__2"]
    assert request["prompt"].count("typed input") == 2
    assert request["prompt"].count("AUTHORED SUFFIX") == 1
    assert commit["identity"] == " / ".join((program.tree["entry"], call["frame"], provider["site"]))


@pytest.mark.parametrize(("extra", "streamed"), [((), True), (("--quiet",), False)], ids=["default", "quiet"])
def test_provider_output_streams_to_the_terminal_unless_quiet(tmp_path, extra, streamed):
    """The provider's stdout/stderr reach the CLI's streams live by default; the attempt files are unchanged."""
    result = _cli(tmp_path, _fixture(tmp_path), extra=extra)
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    (stdout_file,) = run_root.glob("effects/*/attempt-1/stdout.txt")

    assert result.returncode == 0, result.stderr
    assert ("complete stdout\n" in result.stdout, "complete stderr\n" in result.stderr) == (streamed, streamed)
    assert stdout_file.read_bytes() == b"complete stdout\n"
