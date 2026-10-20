"""Owner model cap: real guard/shim with scripted CLIs, never provider calls."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from experiments.compare import scan
from tests.experiments.compare_harness_support import REPO, call, skip_without_sandbox, start, world  # noqa: F401

SONNET = "claude-sonnet-5-5"
TERRA = "gpt-5.6-terra"
DISABLED = ["--disable", "multi_agent", "--disable", "multi_agent_v2",
            "--disable", "multi_agent_v2_dynamic_tools"]


@pytest.fixture
def guarded(tmp_path):
    guard, real = tmp_path / "guard", tmp_path / "real"
    guard.mkdir()
    real.mkdir()
    for name in ("claude", "codex"):
        shutil.copyfile(REPO / "experiments/compare/shim/model-guard", guard / name)
        (guard / name).chmod(0o755)
        (real / name).write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                                 "print(json.dumps({'args': sys.argv[1:], 'stdin': sys.stdin.read(),"
                                 " 'forced': os.getenv('CLAUDE_CODE_SUBAGENT_MODEL'),"
                                 " 'force': os.getenv('CLAUDE_CODE_SUBAGENT_MODEL_FORCE')}))\n"
                                 "sys.exit(3)\n")
        (real / name).chmod(0o755)

    def run(name, args=(), **env):
        return subprocess.run([str(guard / name), *args], input="prompt\n", text=True, capture_output=True,
                              env={**os.environ, "PATH": f"{guard}:{real}:{os.environ['PATH']}", **env})
    return run


@pytest.mark.parametrize("name,model,prefix", [("claude", SONNET, []), ("codex", TERRA, DISABLED)])
def test_guard_defaults_preserve_stdin_status_and_force_nested_policy(guarded, name, model, prefix):
    done = guarded(name, ["exec", "--json"])
    assert done.returncode == 3, done.stderr
    seen = json.loads(done.stdout)
    assert seen == {"args": [*prefix, "--model", model, "exec", "--json"], "stdin": "prompt\n",
                    "forced": SONNET, "force": "1"}


@pytest.mark.parametrize("name,args", [
    ("claude", ["--model", "claude-opus-5-5"]),
    ("claude", ["--model=unknown"]), ("claude", ["--model", "fable"]),
    ("claude", ["--model", SONNET, "--model=claude-opus-5-5"]),
    ("claude", ["--fallback-model", "claude-opus-5-5"]),
    ("claude", [f"--fallback-model={SONNET},claude-fable-5-1"]),
    ("claude", [f"--fallback-model={SONNET},"]),
    ("claude", ["--model"]), ("claude", ["--fallback-model="]),
    ("codex", ["--model", "gpt-6.1-sol"]), ("codex", ["--model=unknown"]),
    ("codex", ["-m", "gpt-6-sol"]), ("codex", ["-mgpt-6.1-sol"]),
    ("codex", ["--model", TERRA, "-m=gpt-6.1-sol"]),
    ("codex", ["--model"]), ("codex", ["--config", "model='gpt-6.1-sol'"]),
    ("codex", ["-cmodel_provider=other"]), ("codex", ["-c", 'profile="high"']),
    ("codex", ["--config=features.multi_agent=true"]),
    ("codex", ["-c", 'features={multi_agent_v2=true}']),
    ("codex", ["--config", 'model_reasoning_effort="high"\nmodel="gpt-6.1-sol"']),
    ("codex", ["--profile", "high"]), ("codex", ["-phigh"]),
    ("codex", ["--model-provider", "other"]),
    ("codex", ["--enable", "multi_agent"]),
    ("codex", ["--enable=multi_agent_v2"]),
    ("codex", ["--enable=multi_agent_v2_dynamic_tools"]),
    ("codex", ["--local-provider", "other"]), ("codex", ["--oss"]),
    ("codex", ["review"]), ("codex", ["exec", "review"]),
])
def test_guard_refuses_model_and_configuration_escape_before_cli(guarded, name, args):
    done = guarded(name, args, ORC_ALLOWED_CLAUDE_MODELS=f"{SONNET},claude-opus-5-5,fable")
    assert (done.returncode, done.stdout) == (2, ""), done.stderr


@pytest.mark.parametrize("args", [
    ["exec", "--model", TERRA, "--config", "model_reasoning_effort=high"],
    [f"-m{TERRA}", "-c", 'model_reasoning_effort="medium"'],
    [f"-m={TERRA}", '-cmodel_reasoning_effort="high"'],
    [f"--model={TERRA}", "--config=model_reasoning_effort=low"],
])
def test_codex_guard_keeps_explicit_model_and_effort_binding(guarded, args):
    done = guarded("codex", args)
    assert done.returncode == 3, done.stderr
    assert json.loads(done.stdout)["args"] == [*DISABLED, *args]


@pytest.mark.parametrize("forced", ["claude-opus-5-5", "fable", "unknown"])
def test_guard_rejects_forbidden_forced_subagent_request(guarded, forced):
    assert guarded("claude", CLAUDE_CODE_SUBAGENT_MODEL=forced).returncode == 2


def test_criterion_allowlist_can_narrow_but_never_raise_owner_cap(guarded):
    assert guarded("claude", ORC_ALLOWED_CLAUDE_MODELS="claude-opus-5-5").returncode == 2
    assert guarded("claude", ["--model", "claude-opus-5-5"],
                   ORC_ALLOWED_CLAUDE_MODELS="claude-opus-5-5").returncode == 2


@pytest.mark.parametrize("outer,inner", [("claude", "codex"), ("codex", "codex"), ("codex", "claude")])
def test_nested_path_cli_cannot_raise_model_cap(world, outer, inner):
    skip_without_sandbox()
    _, record = start(world, "direct_task")
    model = "gpt-6.1-sol" if inner == "codex" else "claude-opus-5-5"
    done = call(world, record, f'{inner} --model {model} </dev/null; echo nested-exit=$?', binary=outer)
    assert done.returncode == 0, done.stderr
    assert "nested-exit=2" in done.stdout
    assert (Path(record["tree"]) / ".model-guard/codex").is_file()


@pytest.mark.parametrize("provider,model,pattern", [
    ("claude", "claude-opus-5-5", "Forbidden model"),
    ("claude", "unknown", "Forbidden model"),
    ("claude", "claude-fable-5-1", "Fable model"),
    ("codex", "gpt-6.1-sol", "Forbidden model"),
    ("codex", "unknown", "Forbidden model"),
    ("codex", "fable", "Fable model"),
    ("claude", SONNET, None), ("codex", TERRA, None),
])
def test_scan_uses_actual_model_metadata_and_policy_cannot_be_cleared(tmp_path, provider, model, pattern):
    tree = tmp_path / "tree"
    home = tmp_path / "home"
    tree.mkdir()
    if provider == "claude":
        slug = "".join(c if c.isalnum() else "-" for c in str(tree))
        path = home / ".claude/projects" / slug / "s.jsonl"
        rows = [{"type": "assistant", "message": {"model": model}}]
    else:
        path = home / ".codex/sessions/2026/10/19/rollout-a.jsonl"
        rows = [{"type": "session_meta", "payload": {"cwd": str(tree)}},
                {"type": "turn_context", "payload": {"model": model}}]
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    hits = scan.find_hits(tmp_path / "calls", tree, 0, home, {})
    assert [hit["pattern"] for hit in hits] == ([pattern] if pattern else [])
    if pattern:
        with pytest.raises(SystemExit, match="cannot be cleared"):
            scan.refuse_clearing("cleared", hits, "run")


def test_scan_ignores_printed_high_model_names_and_unrelated_codex_sessions(tmp_path):
    tree = tmp_path / "tree"
    home = tmp_path / "home"
    path = home / ".codex/sessions/2026/10/19/rollout-a.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"type": "session_meta", "payload": {"cwd": str(tree)}}) + "\n" +
                    json.dumps({"type": "response_item", "payload": {"model": "gpt-6.1-sol", "text": "fable"}}))
    assert scan.find_hits(tmp_path / "calls", tree, 0, home, {}) == []
    path.write_text(json.dumps({"type": "session_meta", "payload": {"cwd": str(tmp_path / 'other')}}) + "\n" +
                    json.dumps({"type": "turn_context", "payload": {"model": "gpt-6.1-sol"}}))
    assert scan.find_hits(tmp_path / "calls", tree, 0, home, {}) == []


@pytest.mark.parametrize("model,succeeds", [(TERRA, True), ("gpt-6.1-sol", False)])
def test_public_orchestrator_cli_runs_scripted_provider_through_cap(world, model, succeeds):
    skip_without_sandbox()
    import sys
    from tests.experiments.compare_harness_support import SHIM
    from tests.experiments.orc_structural_search_support import SCRIPTED

    records, record = start(world, "direct_task")
    (world.fakebin / "codex").write_text(SCRIPTED)
    results = world.outside / "results.json"
    results.write_text(json.dumps([{"match": "", "result": True}]))
    inputs = world.outside / "inputs.json"
    inputs.write_text(json.dumps({"task": "Return true.", "model": model, "effort": "high"}))
    h = REPO / "experiments/compare"
    done = subprocess.run([
        sys.executable, "-P", "-m", "orchestrator", "run", str(h / "control/direct_task.orc"),
        "--entry-workflow", "control/direct_task::direct-task", "--source-root", str(h),
        "--provider-externs-file", str(h / "control/direct_task.providers.json"), "--input-file", str(inputs),
    ], cwd=record["cwd"], capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONPATH": str(REPO), "PATH": f"{SHIM}:{world.fakebin}:{os.environ['PATH']}",
             "SCRIPTED_RESULTS_FILE": str(results), "COMPARE_ROOT": str(records),
             "COMPARE_TREE": record["tree"], "COMPARE_BASE": record["compare_base"]})
    assert (done.returncode == 0) is succeeds, done.stdout + done.stderr
    captured = records / "calls/1"
    assert (captured / "prompt.txt").is_file()
    assert ((captured / "stderr.txt").read_text() == "") is succeeds


@pytest.mark.parametrize("name,model,prefix", [("claude", SONNET, []), ("codex", TERRA, DISABLED)])
def test_guard_preserves_literal_model_words_after_option_delimiter(guarded, name, model, prefix):
    args = ["--", "--model", "gpt-6.1-sol"]
    done = guarded(name, args)
    assert done.returncode == 3, done.stderr
    assert json.loads(done.stdout)["args"] == [*prefix, "--model", model, *args]
