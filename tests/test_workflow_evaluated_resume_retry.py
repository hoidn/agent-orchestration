from __future__ import annotations

import json
import importlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import pytest

from tests.test_workflow_evaluated_providers import _fixture, _requests
from tests.test_workflow_evaluated_resume import _resume_cli, _snapshot
from tests.test_workflow_evaluated_providers import SOURCE


def _public_env() -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _resume_with_package(root: Path, run_id: str, package_parent: Path) -> subprocess.CompletedProcess[str]:
    env = _public_env()
    env["PYTHONPATH"] = str(package_parent)
    return subprocess.run(
        [sys.executable, "-m", "orchestrator", "resume", run_id],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _start_and_kill(argv: list[str], *, root: Path, env: dict[str, str], marker: Path) -> None:
    process = subprocess.Popen(
        argv,
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if marker.exists():
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise AssertionError(
                    f"run exited before kill ({process.returncode}): "
                    f"{stdout.decode(errors='replace')} {stderr.decode(errors='replace')}"
                )
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"run exited before marker ({process.returncode}): "
                f"{stdout.decode(errors='replace')} {stderr.decode(errors='replace')}"
            )
        time.sleep(0.02)
    os.killpg(process.pid, signal.SIGKILL)
    process.communicate(timeout=5)
    raise AssertionError(f"run did not reach marker: {marker}")


def _run_root(root: Path) -> Path:
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    return run_root


def _start_pending_command_retry(tmp_path: Path, pending_shape: str, must_not_repeat: bool):
    source = tmp_path / "retry.orc"
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule retry) (export run)
          (defworkflow run () -> Int
            (command-result emit :argv ("python" "probe.py") :returns Int)))''',
        encoding="utf-8",
    )
    package = tmp_path / "support"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    helper = package / "normalize.py"
    helper.write_text("def value():\n    return 5\n", encoding="utf-8")
    original_helper = helper.read_bytes()
    (tmp_path / "probe.py").write_text(
        "import os, time\nfrom pathlib import Path\nfrom support.normalize import value\n"
        "target = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])\n"
        "if target.parent.name == 'attempt-1': Path('support/normalize.py').write_text('def value():\\n    return 6\\n', encoding='utf-8')\n"
        "target.write_text(str(value()), encoding='utf-8')\n"
        "with Path('dispatches.txt').open('a', encoding='utf-8') as out: out.write(target.parent.name + '\\n')\n"
        "if target.parent.name == 'attempt-1': time.sleep(60)\n",
        encoding="utf-8",
    )
    boundary_file = tmp_path / "commands.json"
    boundary_file.write_text(
        json.dumps({"emit": {
            "stable_command": ["python", "probe.py"],
            "closure": ["probe.py", "support/__init__.py", "support/normalize.py"],
            "must_not_repeat": must_not_repeat,
        }}),
        encoding="utf-8",
    )
    # A marker-based process kill leaves a durable started row and a valid result orphan.
    argv = [sys.executable, "-m", "orchestrator", "run", str(source),
            "--command-boundaries-file", str(boundary_file)]
    _start_and_kill(argv, root=tmp_path, env=_public_env(), marker=tmp_path / "dispatches.txt")
    run_root = _run_root(tmp_path)
    attempt_one = next(run_root.glob("effects/*/attempt-1"))
    assert (attempt_one / "result.json").read_text(encoding="utf-8") == "5"
    assert helper.read_bytes() != original_helper

    memo = run_root / "memo.jsonl"
    with memo.open("ab") as stream:
        stream.write(b'{"record":"partial"')
    (run_root / "state.json").write_text('{"status":"stale"}', encoding="utf-8")
    if pending_shape == "no-directory":
        import shutil
        shutil.rmtree(attempt_one)
    orphan_evidence = (
        {path.name: path.read_bytes() for path in attempt_one.iterdir()}
        if attempt_one.exists() else {}
    )
    before = _snapshot(tmp_path / ".orchestrate")
    return run_root, memo, attempt_one, helper, original_helper, orphan_evidence, before


def _assert_changed_command_is_refused(tmp_path, state):
    run_root, _memo, _attempt_one, helper, original_helper, _orphan_evidence, before = state
    refused = _resume_cli(tmp_path, run_root.name)

    assert refused.returncode == 2, refused.stderr
    assert "effect_input_diverged" in refused.stderr
    assert _snapshot(tmp_path / ".orchestrate") == before
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["attempt-1"]
    helper.write_bytes(original_helper)


def _assert_must_not_repeat_refusal(tmp_path, run_root, before):
    resumed = _resume_cli(tmp_path, run_root.name)
    assert resumed.returncode == 2, resumed.stderr
    assert "lexical_restore_pending_effect_unsafe" in resumed.stderr
    assert _snapshot(tmp_path / ".orchestrate") == before
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["attempt-1"]
    assert not list(run_root.glob("effects/*/attempt-2"))


def _assert_retryable_command_succeeds(tmp_path, run_root, memo, attempt_one, orphan_evidence):
    resumed = _resume_cli(tmp_path, run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == [
        "attempt-1", "attempt-2"
    ]
    rows = [json.loads(line) for line in memo.read_text(encoding="utf-8").splitlines()]
    starts = [row for row in rows if row["record"] == "started"]
    assert [row["attempt"] for row in starts] == [1, 2]
    assert rows[-1]["outcome"] == "completed"
    if orphan_evidence:
        assert {path.name: path.read_bytes() for path in attempt_one.iterdir()} == orphan_evidence


def _assert_command_retry_outcome(tmp_path, state, must_not_repeat):
    run_root, memo, attempt_one, _helper, _original_helper, orphan_evidence, before = state
    if must_not_repeat:
        _assert_must_not_repeat_refusal(tmp_path, run_root, before)
        return
    _assert_retryable_command_succeeds(tmp_path, run_root, memo, attempt_one, orphan_evidence)


@pytest.mark.parametrize("pending_shape", ["orphan-result", "no-directory"])
@pytest.mark.parametrize("must_not_repeat", [False, True], ids=["retryable", "must-not-repeat"])
def test_public_pending_command_preflights_package_helper_before_repair_or_retry(
    tmp_path: Path, pending_shape: str, must_not_repeat: bool,
) -> None:
    state = _start_pending_command_retry(tmp_path, pending_shape, must_not_repeat)
    _assert_changed_command_is_refused(tmp_path, state)
    _assert_command_retry_outcome(tmp_path, state, must_not_repeat)


def test_public_pending_certified_package_helper_preflights_and_retries_from_copy(
    tmp_path: Path,
) -> None:
    package_parent = tmp_path / "vendor"
    package_copy = package_parent / "orchestrator"
    shutil.copytree(
        Path(importlib.import_module("orchestrator").__file__).resolve().parent,
        package_copy,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    adapter = package_copy / "workflow_lisp" / "adapters" / "validate_review_findings_v1.py"
    original_adapter = adapter.read_text(encoding="utf-8")
    original_emit = """        return emit_structured_result(
            {
                "schema_version": schema_version,
                "items_path": items_path.as_posix(),
            }
        )"""
    blocked_emit = """        emitted = emit_structured_result(
            {
                "schema_version": schema_version,
                "items_path": items_path.as_posix(),
            }
        )
        import os, time
        target = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        with Path("dispatches.txt").open("a", encoding="utf-8") as stream:
            stream.write(target.parent.name + "\\n")
        if target.parent.name == "attempt-1": time.sleep(60)
        return emitted"""
    assert original_adapter.count(original_emit) == 1
    adapter.write_text(original_adapter.replace(original_emit, blocked_emit), encoding="utf-8")

    source = tmp_path / "package-retry.orc"
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule package-retry) (export run)
          (defpath ReviewFindingsJsonPath :kind relpath :under "artifacts/work" :must-exist true)
          (defrecord ReviewFindings (schema_version String) (items_path ReviewFindingsJsonPath))
          (defworkflow run ((items ReviewFindingsJsonPath)) -> ReviewFindings
            (command-result validate_review_findings_v1
              :argv ("python" "-m" "orchestrator.workflow_lisp.adapters.validate_review_findings_v1" items)
              :returns ReviewFindings)))''',
        encoding="utf-8",
    )
    artifacts = tmp_path / "artifacts" / "work"
    artifacts.mkdir(parents=True)
    (artifacts / "carrier.json").write_text(
        json.dumps({"schema_version": "ReviewFindings.v1", "items_path": "artifacts/work/findings.json"}),
        encoding="utf-8",
    )
    (artifacts / "findings.json").write_text('{"items": []}', encoding="utf-8")
    env = _public_env()
    env["PYTHONPATH"] = str(package_parent)
    _start_and_kill(
        [sys.executable, "-m", "orchestrator", "run", str(source),
         "--input", "items=artifacts/work/carrier.json"],
        root=tmp_path,
        env=env,
        marker=tmp_path / "dispatches.txt",
    )
    run_root = _run_root(tmp_path)
    attempt_one = next(run_root.glob("effects/*/attempt-1"))
    original_attempt = {path.name: path.read_bytes() for path in attempt_one.iterdir()}
    common_helper = package_copy / "workflow_lisp" / "adapters" / "reusable_phase_state_common.py"
    helper_before = common_helper.read_bytes()
    common_helper.write_bytes(helper_before + b"\n# temporary copied-package mutation\n")
    before = _snapshot(tmp_path / ".orchestrate")

    refused = _resume_with_package(tmp_path, run_root.name, package_parent)

    assert refused.returncode == 2, refused.stderr
    assert "effect_input_diverged" in refused.stderr
    assert _snapshot(tmp_path / ".orchestrate") == before
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["attempt-1"]
    common_helper.write_bytes(helper_before)

    resumed = _resume_with_package(tmp_path, run_root.name, package_parent)

    assert resumed.returncode == 0, resumed.stderr
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == [
        "attempt-1", "attempt-2"
    ]
    assert {path.name: path.read_bytes() for path in attempt_one.iterdir()} == original_attempt


def _start_pending_provider_c6(tmp_path: Path, monkeypatch, c6_failure: str):
    fixture = _fixture(tmp_path)
    source, providers, prompts, _request = fixture
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("PROVIDER_SHIM_MODE", "timeout")
    argv = [sys.executable, "-B", "-m", "orchestrator", "run", str(source),
            "--source-root", str(source.parent), "--provider-externs-file", str(providers),
            "--prompt-externs-file", str(prompts), "--input", "message=typed input"]
    _start_and_kill(argv, root=tmp_path, env=_public_env(), marker=tmp_path / "requests.jsonl")
    run_root = _run_root(tmp_path)
    memo = run_root / "memo.jsonl"
    with memo.open("ab") as stream:
        stream.write(b'{"record":"partial"')
    stale_view = run_root / "state.json"
    stale_view.write_text('{"status":"failed"}', encoding="utf-8")
    attempt_one = next(run_root.glob("effects/*/attempt-1"))
    original_evidence = {path.name: path.read_bytes() for path in attempt_one.iterdir()}
    before = _snapshot(tmp_path / ".orchestrate")
    prompt = tmp_path / "prompt.md"
    original_prompt = prompt.read_bytes()
    prompt.unlink()
    if c6_failure == "unreadable":
        prompt.symlink_to("prompt.md")
    return run_root, memo, attempt_one, prompt, original_prompt, original_evidence, stale_view, before


def _assert_pending_provider_c6_refusal(tmp_path, state):
    run_root, _memo, _attempt_one, _prompt, _original_prompt, _evidence, _stale, before = state
    refused = _resume_cli(tmp_path, run_root.name)

    assert refused.returncode == 2, refused.stderr
    assert _snapshot(tmp_path / ".orchestrate") == before
    assert len(_requests(tmp_path)) == 1
    assert len(list(run_root.glob("effects/*/attempt-*"))) == 1


def _retry_changed_provider_c6(tmp_path, monkeypatch, state):
    run_root, memo, attempt_one, prompt, original_prompt, original_evidence, stale_view, _before = state
    prompt.unlink(missing_ok=True)
    prompt.write_bytes(original_prompt + b"changed but readable C6\n")
    monkeypatch.setenv("PROVIDER_SHIM_MODE", "success")
    resumed = _resume_cli(tmp_path, run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    assert len(_requests(tmp_path)) == 2
    rows = [json.loads(line) for line in memo.read_text(encoding="utf-8").splitlines()]
    starts = [row for row in rows if row["record"] == "started"]
    assert [row["attempt"] for row in starts] == [1, 2]
    assert starts[0]["input_parts"] != starts[1]["input_parts"]
    assert {path.name: path.read_bytes() for path in attempt_one.iterdir()} == original_evidence
    assert stale_view.read_text(encoding="utf-8") == '{"status":"failed"}'


@pytest.mark.parametrize("c6_failure", ["missing", "unreadable"])
def test_public_pending_provider_unreadable_c6_is_readonly_then_changed_c6_retries(
    tmp_path: Path, monkeypatch, c6_failure: str,
) -> None:
    state = _start_pending_provider_c6(tmp_path, monkeypatch, c6_failure)
    _assert_pending_provider_c6_refusal(tmp_path, state)
    _retry_changed_provider_c6(tmp_path, monkeypatch, state)


def _start_pending_required_dependency(tmp_path: Path, monkeypatch, dependency_failure: str):
    source = SOURCE.replace(
        "  (defrecord Result (ok Bool))",
        "  (defpath Note :kind relpath :under \"artifacts\" :must-exist false)\n  (defrecord Result (ok Bool))",
    ).replace("((message String))", "((message String) (note Note))")
    source = source.replace(
        ":inputs (message) :model",
        ":inputs (message) :prompt-dependencies (:required (note)) :model",
    )
    fixture = _fixture(tmp_path, source)
    dependency = tmp_path / "artifacts" / "note.md"
    dependency.parent.mkdir()
    dependency.write_text("initial required dependency\n", encoding="utf-8")
    source_path, providers, prompts, _request = fixture
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("PROVIDER_SHIM_MODE", "timeout")
    argv = [sys.executable, "-B", "-m", "orchestrator", "run", str(source_path),
            "--source-root", str(source_path.parent), "--provider-externs-file", str(providers),
            "--prompt-externs-file", str(prompts), "--input", "message=typed input",
            "--input", "note=artifacts/note.md"]
    _start_and_kill(argv, root=tmp_path, env=_public_env(), marker=tmp_path / "requests.jsonl")
    run_root = _run_root(tmp_path)
    memo = run_root / "memo.jsonl"
    with memo.open("ab") as stream:
        stream.write(b'{"record":"partial"')
    (run_root / "state.json").write_text('{"status":"stale"}', encoding="utf-8")
    attempt_one = next(run_root.glob("effects/*/attempt-1"))
    original_evidence = {path.name: path.read_bytes() for path in attempt_one.iterdir()}
    before = _snapshot(tmp_path / ".orchestrate")
    dependency.unlink()
    if dependency_failure == "unreadable":
        dependency.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PROVIDER_SHIM_MODE", "success")
    return run_root, memo, dependency, attempt_one, original_evidence, before


def _assert_required_dependency_refusal(tmp_path, monkeypatch, state):
    run_root, _memo, _dependency, _attempt_one, _evidence, before = state
    executor_calls = []
    from orchestrator.workflow.evaluated import runtime as runtime_module
    from orchestrator.cli.commands.resume import resume_workflow
    original_resolver = runtime_module.resolve_provider_input
    resolver_calls = []

    def forbidden_executor(*args, **kwargs):
        executor_calls.append((args, kwargs))
        raise AssertionError("readonly provider preflight constructed ProviderExecutor")

    def prove_dependency_c6(*args, **kwargs):
        resolver_calls.append((args, kwargs))
        return original_resolver(*args, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(runtime_module, "ProviderExecutor", forbidden_executor)
        patched.setattr(runtime_module, "resolve_provider_input", prove_dependency_c6)
        assert resume_workflow(run_root.name) == 2
    assert not executor_calls
    assert len(resolver_calls) == 1
    assert _snapshot(tmp_path / ".orchestrate") == before
    assert len(_requests(tmp_path)) == 1
    assert len(list(run_root.glob("effects/*/attempt-*"))) == 1


def _retry_with_changed_required_dependency(tmp_path, state):
    run_root, memo, dependency, attempt_one, original_evidence, _before = state
    if dependency.is_dir():
        dependency.rmdir()
    else:
        dependency.unlink(missing_ok=True)
    dependency.write_text("changed readable dependency\n", encoding="utf-8")
    from orchestrator.cli.commands.resume import resume_workflow

    assert resume_workflow(run_root.name) == 0
    rows = [json.loads(line) for line in memo.read_text(encoding="utf-8").splitlines()]
    starts = [row for row in rows if row["record"] == "started"]
    assert [row["attempt"] for row in starts] == [1, 2]
    assert starts[0]["input_parts"] != starts[1]["input_parts"]
    assert {path.name: path.read_bytes() for path in attempt_one.iterdir()} == original_evidence
    assert len(_requests(tmp_path)) == 2


@pytest.mark.parametrize("dependency_failure", ["missing", "unreadable"])
def test_pending_provider_required_dependency_c6_refuses_before_executor_then_retries(
    tmp_path: Path, monkeypatch, dependency_failure: str,
) -> None:
    state = _start_pending_required_dependency(tmp_path, monkeypatch, dependency_failure)
    _assert_required_dependency_refusal(tmp_path, monkeypatch, state)
    _retry_with_changed_required_dependency(tmp_path, state)
