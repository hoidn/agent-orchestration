"""Usage recorded beside every provider attempt, through `orchestrator run` with stand-in CLIs.

Built-in `claude*`/`codex*` templates stay plain; their `<name>_metered` variants print transport JSON,
whose usage lands in the attempt's `usage.json`. Nothing else in the run changes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.providers.registry import ProviderRegistry
from tests.workflow_evaluated_consumer_sources import PROGRAMS, install


ROOT = Path(__file__).resolve().parents[1]
SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defworkflow run ((message String)) -> Result
    (provider-result providers.review :prompt prompts.base
      :inputs (message) :model "MODEL" :effort "high" :returns Result)))'''

# One stand-in for `claude`, `codex` and `gemini`: with its CLI's structured-output flags it prints
# transport lines (fixed usage), else it prints the final message like the plain CLI.
STANDIN = r'''import json, os, sys
from pathlib import Path
argv, tool = sys.argv[1:], Path(sys.argv[0]).name
with open("argv.jsonl", "a", encoding="utf-8") as log:
    log.write(json.dumps({"tool": tool, "argv": argv}) + "\n")
messages = json.loads(os.environ.get("STANDIN_MESSAGES", '["the reply"]'))
mode = os.environ.get("STANDIN_MODE", "ok")
transport = ("stream-json" in argv) if tool == "claude" else ("--json" in argv) if tool == "codex" else False
def line(row):
    sys.stdout.write(json.dumps(row) + "\n")
if mode == "garbage":
    sys.stdout.write("not a transport line\n")
elif transport and tool == "claude":
    sid = "00000000-0000-4000-8000-000000000001"
    line({"type": "system", "subtype": "init", "session_id": sid})
    for n, text in enumerate(messages):
        line({"type": "assistant", "session_id": sid, "message": {"id": f"msg_{n}", "model": "claude-haiku-5-5",
              "content": [{"type": "text", "text": text}], "usage": {"input_tokens": 11, "output_tokens": 1,
              "cache_read_input_tokens": 5, "cache_creation_input_tokens": 3}}})
    line({"type": "result", "subtype": "success", "is_error": False, "result": messages[-1], "session_id": sid,
          "total_cost_usd": 0.25, "modelUsage": {"claude-haiku-5-5": {"inputTokens": 11, "outputTokens": 7,
          "cacheReadInputTokens": 5, "cacheCreationInputTokens": 3, "costUSD": 0.25}}})
elif transport:
    line({"type": "thread.started", "thread_id": "00000000-0000-4000-8000-000000000002"})
    line({"type": "turn.started"})
    for n, text in enumerate(messages):
        line({"type": "item.completed", "item": {"id": f"item_{n}", "type": "agent_message", "text": text}})
    line({"type": "turn.completed", "usage": {"input_tokens": 11, "cached_input_tokens": 5,
          "cache_write_input_tokens": 0, "output_tokens": 7, "reasoning_output_tokens": 0}})
else:
    sys.stdout.write(messages[-1] + "\n")
sys.stdout.flush()
if mode == "fail":
    sys.exit(3)
if mode != "no-result":
    Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('{"ok": true}', encoding="utf-8")
'''

CLAUDE_USAGE = {"status": "reported", "source": "result.modelUsage", "reported_cost_usd": 0.25, "rows": [
    {"model": "claude-haiku-5-5", "tokens": {"input": 11, "output": 7, "cache_read": 5, "cache_write": 3}}]}
CODEX_USAGE = {"status": "reported", "source": "turn.completed.usage", "reported_cost_usd": None, "rows": [
    {"model": "gpt-5.6-terra", "tokens": {"input": 6, "output": 7, "cache_read": 5, "cache_write": 0}}]}
PLAIN = sorted(name for name, template in ProviderRegistry()._builtin_providers.items()
               if template.command[0] in ("claude", "codex") and template.command_metadata_mode is None)


def _workspace(root: Path, template: str, model: str = "claude-haiku-5-5") -> Path:
    root.mkdir(parents=True)
    (root / "main.orc").write_text(SOURCE.replace("MODEL", model), encoding="utf-8")
    (root / "prompt.md").write_text("Answer.\n", encoding="utf-8")
    (root / "providers.json").write_text(json.dumps({"providers.review": template}), encoding="utf-8")
    (root / "prompts.json").write_text(json.dumps({"prompts.base": {"asset_file": "prompt.md"}}), encoding="utf-8")
    (root / "bin").mkdir()
    for tool in ("claude", "codex", "gemini"):
        (root / "bin" / tool).write_text(f"#!{sys.executable}\n" + STANDIN, encoding="utf-8")
        (root / "bin" / tool).chmod(0o700)
    return root


def _env(root: Path, **standin) -> dict:
    return {**os.environ, "PATH": str(root / "bin") + os.pathsep + os.environ["PATH"],
            "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
            **{f"STANDIN_{key.upper()}": value for key, value in standin.items()}}


def _orchestrator(root: Path, *argv: str, **standin) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "orchestrator", *argv], cwd=root, env=_env(root, **standin),
                          capture_output=True, text=True, check=False, timeout=120)


def _run(root: Path, *extra: str, **standin) -> subprocess.CompletedProcess[str]:
    return _orchestrator(root, "run", "main.orc", "--source-root", ".", "--provider-externs-file", "providers.json",
                         "--prompt-externs-file", "prompts.json", "--input", "message=hi", *extra, **standin)


def _attempts(root: Path) -> list[Path]:
    """Provider-call attempts (those holding a prompt), in path order."""
    return sorted(path.parent for path in root.glob(".orchestrate/runs/*/effects/*/attempt-*/prompt.txt"))


def _usage(attempt: Path) -> dict:
    return json.loads((attempt / "usage.json").read_text(encoding="utf-8"))


def _memo(root: Path) -> list[dict]:
    (memo,) = root.glob(".orchestrate/runs/*/memo.jsonl")
    return [json.loads(line) for line in memo.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("messages", [["the reply"], ["Looking at the file.", "the reply"]], ids=["one", "two"])
@pytest.mark.parametrize("template", PLAIN)
def test_unmetered_templates_keep_plain_stdout_and_terminal_text(tmp_path, template, messages):
    """Today's plain call: the CLI prints its final message and a newline; the run then prints the value."""
    root = _workspace(tmp_path / "w", template)
    result = _run(root, messages=json.dumps(messages))
    assert (result.returncode, result.stdout, (_attempts(root)[0] / "stdout.txt").read_text()) == (
        0, messages[-1] + "\n" + '{"ok":true}\n', messages[-1] + "\n"), result.stderr


@pytest.mark.parametrize(("template", "model", "expected"), [
    ("claude_metered", "claude-haiku-5-5", CLAUDE_USAGE), ("codex_metered", "gpt-5.6-terra", CODEX_USAGE)])
def test_provider_step_writes_usage_beside_its_stdout(tmp_path, template, model, expected):
    root = _workspace(tmp_path / "w", template, model)
    result = _run(root)
    assert result.returncode == 0, result.stderr
    (attempt,) = _attempts(root)
    assert (_usage(attempt), (attempt / "stdout.txt").is_file()) == (expected, True)


@pytest.mark.parametrize(("template", "model", "expected"), [
    ("claude_metered", "claude-haiku-5-5", CLAUDE_USAGE), ("codex_metered", "gpt-5.6-terra", CODEX_USAGE)])
def test_failed_attempt_keeps_the_usage_it_reported(tmp_path, template, model, expected):
    root = _workspace(tmp_path / "w", template, model)
    result = _run(root, mode="fail")
    assert result.returncode == 1, result.stderr
    assert [row["record"] for row in _memo(root)] == ["started", "failed", "terminal"]
    (attempt,) = _attempts(root)
    assert _usage(attempt) == expected


@pytest.mark.parametrize("template", ["claude", "codex"])
def test_template_without_transport_records_unknown(tmp_path, template):
    root = _workspace(tmp_path / "w", template)
    assert _run(root).returncode == 0
    (attempt,) = _attempts(root)
    assert _usage(attempt) == {"status": "unknown", "reason": "no_transport"}


@pytest.mark.parametrize("template", ["claude_metered", "codex_metered"])
def test_unreadable_transport_never_fails_a_call_that_wrote_its_result(tmp_path, template):
    root = _workspace(tmp_path / "w", template)
    result = _run(root, mode="garbage")
    assert (result.returncode, _memo(root)[-1]) == (0, {"record": "terminal", "outcome": "completed",
                                                        "value": {"ok": True}}), result.stderr
    (attempt,) = _attempts(root)
    assert _usage(attempt) == {"status": "unknown", "reason": "malformed"}


@pytest.mark.parametrize("template", ["claude_metered", "codex_metered"])
def test_terminal_shows_assistant_text_not_transport_lines(tmp_path, template):
    """Metered calls stream every assistant message the decoder sees, never the JSON lines."""
    root = _workspace(tmp_path / "w", template)
    result = _run(root, messages=json.dumps(["Looking at the file.", "the reply"]))
    assert (result.returncode, result.stdout) == (0, 'Looking at the file.the reply\n{"ok":true}\n'), result.stderr


@pytest.mark.parametrize("template", ["claude_metered", "codex_metered"])
def test_missing_result_quotes_the_decoded_reply(tmp_path, template):
    root = _workspace(tmp_path / "w", template)
    assert _run(root, mode="no-result").returncode == 1
    terminal = _memo(root)[-1]
    assert terminal["code"] == "provider_result_missing" and "reply began: the reply" in terminal["message"]


STARTED = {"attempt", "identity", "implementation_files", "input_digest", "input_parts", "record", "result_path", "time"}
COMMITTED = {"attempt", "depends_on", "effect_class", "identity", "implementation_files", "input_digest",
             "input_parts", "record", "result_digest", "result_path", "time", "value"}
PARTS = {"declaration", "delivery", "dependency_rows", "params", "policy", "prompt", "source:asset_file:prompt.md",
         "values"}
# Recorded with `orchestrator compile` before usage.json existed (B1 commit c238e5cf).
DIGESTS = {"best_of_n": "sha256:991a8302be2705206e88f385fc4c82f3b43480b81a0770da0727255b7b0271a7",
           "reviewed_change": "sha256:fa8a2b27a827498bfdc3e1cfc373116f38dd3e5180db83430637c6c9d9be11c7",
           "design_review_execute_agents":
               "sha256:4eb2e5cfb2fa9eee9889b90ab6f4b8c171b4f53ed713d1276e9b7fb961f991a8"}


def test_memo_rows_and_program_digests_are_unchanged(tmp_path):
    root = _workspace(tmp_path / "w", "claude_metered")
    assert _run(root).returncode == 0
    started, committed, terminal = _memo(root)
    assert ((set(started), set(committed), set(terminal), set(started["input_parts"])) ==
            (STARTED, COMMITTED, {"outcome", "record", "value"}, PARTS))
    digests = {}
    for name in DIGESTS:
        workspace = tmp_path / name
        workspace.mkdir()
        compiled = _orchestrator(workspace, "compile", *install(workspace, PROGRAMS[name], {}))
        assert compiled.returncode == 0, compiled.stderr
        digests[name] = json.loads(compiled.stdout)["program_digest"]
    assert digests == DIGESTS


def _tree(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*"))
            if path.is_file() and path.name not in {"run.lock", "workspace.lock", "workspace.guard"}}


def test_run_completed_before_metering_resumes_as_a_no_op(tmp_path):
    root = _workspace(tmp_path / "w", "claude_metered")
    assert _run(root).returncode == 0
    (attempt,) = _attempts(root)
    (attempt / "usage.json").unlink()       # the run as it was recorded before this change
    before, calls = _tree(root / ".orchestrate"), (root / "argv.jsonl").read_bytes()
    (run_id,) = [path.name for path in (root / ".orchestrate" / "runs").iterdir()]
    resumed = _orchestrator(root, "resume", run_id)
    assert (resumed.returncode, _tree(root / ".orchestrate"), (root / "argv.jsonl").read_bytes()) == (
        0, before, calls), resumed.stderr


def test_agent_turn_attempts_write_usage(tmp_path, monkeypatch):
    from tests.agent_session_shims import install_agent_shims
    from tests.test_workflow_evaluated_agent_turns import PLAN, fixture
    from tests.test_workflow_evaluated_invalidate import _cli

    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex",
                        claude_home=tmp_path / "claude", plan=PLAN)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 0
    # The shims print transport without usage counters: four attempts, each `unknown`, none zero.
    assert [_usage(attempt)["status"] for attempt in _attempts(tmp_path)] == ["unknown"] * 4


def test_phased_attempt_records_no_transport(tmp_path):
    import tempfile
    import time
    from orchestrator.workflow.evaluated.phased_providers import EvaluatedPhasedBindings
    from tests.workflow_evaluated_phased_helpers import external_attempt

    attempt = external_attempt(tmp_path)
    with tempfile.TemporaryDirectory(prefix="p", dir="/tmp") as transport_root:
        bindings = EvaluatedPhasedBindings(attempt, deadline=time.monotonic() + 20, transport_root=Path(transport_root))
        bindings.preflight_candidates(bindings.compose_attempt(bindings.allocate_attempt(), deadline=bindings.deadline))
        bindings.candidates.close()
    assert json.loads(attempt.attempt_files.read("usage.json")) == {"status": "unknown", "reason": "no_transport"}
