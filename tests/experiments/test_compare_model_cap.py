"""Owner model cap: real guard/shim with scripted CLIs, never provider calls."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from experiments.compare import scan
from tests.experiments.compare_harness_support import (
    REPO, call, configure_test_sandbox, skip_without_sandbox, start, world,
)  # noqa: F401

SONNET = "claude-sonnet-5-5"
TERRA = "gpt-5.6-terra"
SOL = "gpt-6.1-sol"
DISABLED = ["--disable", "multi_agent", "--disable", "multi_agent_v2",
            "--disable", "multi_agent_v2_dynamic_tools", "-c", "agents.enabled=false"]


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
    assert seen == {"args": ["--model", model, "exec", *prefix, "--json"], "stdin": "prompt\n",
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
    ("codex", ["--config", "agents.enabled=true"]),
    ("codex", ["-cagents.enabled=true"]),
    ("codex", ["--config=agents.enabled=true"]),
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
    expected = ["exec", *DISABLED, *args[1:]] if args[0] == "exec" else [*DISABLED, *args]
    assert json.loads(done.stdout)["args"] == expected


def test_exact_sol_opt_in_preserves_native_agent_and_claude_bans(guarded):
    env = {'ORC_ALLOWED_CODEX_MODELS': SOL, 'ORC_ALLOWED_CLAUDE_MODELS': ''}
    selected = guarded('codex', ['exec', '--model', SOL, '--config', 'model_reasoning_effort=high'], **env)
    assert selected.returncode == 3, selected.stderr
    assert json.loads(selected.stdout)['args'] == ['exec', *DISABLED, '--model', SOL, '--config',
                                                   'model_reasoning_effort=high']
    assert guarded('codex', ['--model', TERRA], **env).returncode == 2
    assert guarded('claude', ['--model', SONNET], **env).returncode == 2
    for args in (['--model', SOL, '--enable', 'multi_agent'],
                 ['--model', SOL, '--config', 'agents.enabled=true'],
                 ['--model', SOL, '--model-provider', 'other']):
        assert guarded('codex', args, **env).returncode == 2


@pytest.mark.parametrize('model', ['gpt-6-sol', 'gpt-6.1-sol-preview', 'gpt-6.2-sol', 'unknown'])
def test_sol_opt_in_does_not_admit_unknown_or_other_higher_models(guarded, model):
    assert guarded('codex', ['--model', model], ORC_ALLOWED_CODEX_MODELS=model).returncode == 2


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
@pytest.mark.parametrize("no_claude", [False, True])
def test_public_orchestrator_cli_runs_scripted_provider_through_cap(world, monkeypatch, model, succeeds, no_claude):
    skip_without_sandbox()
    import sys
    from tests.experiments.compare_harness_support import SHIM
    from tests.experiments.orc_structural_search_support import SCRIPTED

    results = world.outside / "results.json"
    results.write_text(json.dumps([{"match": "", "result": True}]))
    inputs = world.outside / "inputs.json"
    inputs.write_text(json.dumps({"task": "Return true.", "model": model, "effort": "high"}))
    (world.fakebin / "codex").write_text(SCRIPTED)
    configure_test_sandbox(world, monkeypatch, readonly_files=(results,),
                           environment_names=("SCRIPTED_RESULTS_FILE",))
    if no_claude:
        monkeypatch.setenv("COMPARE_CLAUDE_MODELS", "")
    records, record = start(world, "direct_task")
    h = REPO / "experiments/compare"
    done = subprocess.run([
        sys.executable, "-P", "-m", "orchestrator", "run", str(h / "control/direct_task.orc"),
        "--entry-workflow", "control/direct_task::direct-task", "--source-root", str(h),
        "--provider-externs-file", str(h / "control/direct_task.providers.json"), "--input-file", str(inputs),
    ], cwd=record["cwd"], capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONPATH": str(REPO), "PATH": f"{SHIM}:{world.fakebin}:{os.environ['PATH']}",
             **({"COMPARE_CLAUDE_MODELS": ""} if no_claude else {}),
             "SCRIPTED_RESULTS_FILE": str(results), "COMPARE_ROOT": str(records),
             "COMPARE_TREE": record["tree"], "COMPARE_BASE": record["compare_base"],
             "COMPARE_SANDBOX": record["sandbox"]["declaration"]})
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


@pytest.mark.parametrize("name,args", [
    ("codex", ["cloud", "exec", "--env", "e", "query"]),
    ("codex", ["--remote", "http://server"]), ("codex", ["--remote=http://server"]),
    ("codex", ["--approve-for-me"]), ("codex", ["exec", "--approve-for-me"]),
    ("codex", ["remote-control"]), ("codex", ["dispatch"]), ("codex", ["queue", "s", "query"]),
    ("codex", ["exec", "resume", "s"]), ("codex", ["fork", "s"]),
    ("claude", ["--cloud", "query"]), ("claude", ["--cloud=query"]),
    ("claude", ["--environment", "e"]), ("claude", ["--environment=e"]),
    ("claude", ["--desktop"]), ("claude", ["ultrareview"]),
    ("claude", ["--remote-control"]), ("claude", ["--settings", "settings.json"]),
])
def test_guard_refuses_remote_and_independent_session_routes_before_cli(guarded, name, args):
    done = guarded(name, args)
    assert (done.returncode, done.stdout) == (2, ""), done.stderr


def test_guard_refuses_app_server_protocol_model_override_before_cli(guarded):
    done = guarded("codex", ["app-server"])
    assert (done.returncode, done.stdout) == (2, ""), done.stderr


@pytest.mark.parametrize("name,args", [
    ("claude", ["--model", f"{SONNET},{SONNET}"]),
    ("claude", [f"--model={SONNET},{SONNET}"]),
    ("codex", ["--model", f"{TERRA},{TERRA}"]),
    ("codex", [f"-m{TERRA},{TERRA}"]),
])
def test_primary_model_is_one_exact_id_never_a_model_list(guarded, name, args):
    done = guarded(name, args)
    assert (done.returncode, done.stdout) == (2, ""), done.stderr


@pytest.mark.parametrize("args,expected", [
    (["--model", TERRA, "exec", "--config", "model_reasoning_effort=high"],
     ["--model", TERRA, "exec", *DISABLED, "--config", "model_reasoning_effort=high"]),
    (["--cd", "exec", "--model", TERRA, "e", "--config", "model_reasoning_effort=high"],
     ["--cd", "exec", "--model", TERRA, "e", *DISABLED, "--config", "model_reasoning_effort=high"]),
    (["--cd", "exec", "ordinary prompt"],
     [*DISABLED, "--model", TERRA, "--cd", "exec", "ordinary prompt"]),
    (["ordinary prompt", "exec"], [*DISABLED, "--model", TERRA, "ordinary prompt", "exec"]),
    (["--", "exec"], [*DISABLED, "--model", TERRA, "--", "exec"]),
])
def test_codex_policy_uses_exec_scope_without_treating_values_or_prompts_as_commands(guarded, args, expected):
    done = guarded("codex", args)
    assert done.returncode == 3, done.stderr
    assert json.loads(done.stdout)["args"] == expected


HAIKU = "claude-haiku-5-5"


def test_haiku_opt_in_admits_exactly_haiku_and_pins_every_subagent_to_it(guarded):
    for name, args, expected in (("claude", ["--model", HAIKU, "-p"], ["--model", HAIKU, "-p"]),
                                 ("claude", ["-p"], ["--model", HAIKU, "-p"]),
                                 ("codex", ["exec"], ["exec", *DISABLED])):
        done = guarded(name, args, ORC_ALLOWED_CLAUDE_MODELS=HAIKU)
        assert done.returncode == 3, done.stderr
        seen = json.loads(done.stdout)
        assert (seen["args"][-len(expected):], seen["forced"], seen["force"]) == (expected, HAIKU, "1")


@pytest.mark.parametrize("allowed,args", [
    (None, ["--model", HAIKU]), (SONNET, ["--model", HAIKU]), ("", ["--model", HAIKU]),
    (f"{SONNET},{HAIKU}", ["--model", HAIKU]), (f"{HAIKU},claude-opus-5-5", ["--model", HAIKU]),
    (None, ["--fallback-model", HAIKU]),
    (HAIKU, ["--model", SONNET]), (HAIKU, ["--fallback-model", SONNET]),
    (HAIKU, ["--model", "claude-opus-5-5"]), (HAIKU, ["--model", "claude-fable-5-1"]),
    (HAIKU, ["--model", "fable"]), (HAIKU, ["--model", "unknown"]),
    (HAIKU, ["--model", f"{HAIKU}-preview"]), (HAIKU, ["--model", "claude-haiku"]),
    (HAIKU, ["--model", "claude-haiku-5"]), (HAIKU, ["--model", "haiku"]),
    (HAIKU, ["--model", f"{HAIKU},{HAIKU}"]), (HAIKU, [f"--fallback-model={HAIKU},claude-fable-5-1"]),
    (f"{HAIKU}-preview", ["--model", f"{HAIKU}-preview"]), ("claude-haiku", ["--model", "claude-haiku"]),
    ("claude-opus-5-5", ["--model", "claude-opus-5-5"]), ("claude-fable-5-1", ["--model", "claude-fable-5-1"]),
])
def test_guard_admits_haiku_by_exact_id_only_on_opt_in_and_nothing_else(guarded, allowed, args):
    env = {} if allowed is None else {"ORC_ALLOWED_CLAUDE_MODELS": allowed}
    done = guarded("claude", args, **env)
    assert (done.returncode, done.stdout) == (2, ""), done.stderr


@pytest.mark.parametrize("forced", [SONNET, "claude-opus-5-5", "claude-fable-5-1", "unknown"])
def test_haiku_bound_guard_rejects_any_other_forced_subagent_model(guarded, forced):
    assert guarded("claude", ["--model", HAIKU], ORC_ALLOWED_CLAUDE_MODELS=HAIKU,
                   CLAUDE_CODE_SUBAGENT_MODEL=forced).returncode == 2


def test_haiku_run_binds_its_shim_and_nested_calls_cannot_change_the_binding(world, monkeypatch):
    skip_without_sandbox()
    monkeypatch.setenv("COMPARE_CLAUDE_MODELS", HAIKU)
    records, record = start(world, "direct_task")
    for script in ("command.sh", "resume.sh"):
        assert f"COMPARE_CLAUDE_MODELS={HAIKU}" in (records / script).read_text()
    done = call(world, record, "echo pin=$CLAUDE_CODE_SUBAGENT_MODEL; "
                f"claude --model {HAIKU} </dev/null; echo haiku=$?; "
                f"claude --model {SONNET} </dev/null; echo sonnet=$?; "
                f"env -u ORC_ALLOWED_CLAUDE_MODELS CLAUDE_CODE_SUBAGENT_MODEL={SONNET} claude --model {SONNET}"
                " </dev/null; echo dropped=$?", args=("--model", HAIKU, "-p"))
    assert done.returncode == 0, done.stderr
    assert [line for line in done.stdout.splitlines() if "=" in line and "PYTHONPATH" not in line] == [
        f"pin={HAIKU}", "haiku=0", "sonnet=2", "dropped=2"]


def test_a_candidate_cannot_admit_haiku_from_inside_a_default_run(world):
    skip_without_sandbox()
    _, record = start(world, "direct_task")
    assert call(world, record, "true", args=("--model", HAIKU, "-p")).returncode == 2
    guard = Path(record["tree"]) / ".model-guard"
    done = call(world, record, f"ORC_ALLOWED_CLAUDE_MODELS={HAIKU} CLAUDE_CODE_SUBAGENT_MODEL={HAIKU} "
                f"claude --model {HAIKU} </dev/null; echo widened=$?; "
                f"(printf '#!/bin/sh\\n' > {guard}/claude) 2>/dev/null; echo edited=$?")
    assert done.returncode == 0, done.stderr
    assert ("widened=2" in done.stdout, "edited=0" in done.stdout) == (True, False), done.stdout


@pytest.mark.parametrize("expected,model,pattern", [
    (HAIKU, SONNET, "Forbidden model"), (HAIKU, "claude-fable-5-1", "Fable model"),
    (HAIKU, HAIKU, None), (None, HAIKU, "Forbidden model"),
])
def test_scan_flags_any_claude_answer_other_than_the_bound_model(tmp_path, expected, model, pattern):
    tree, home = tmp_path / "tree", tmp_path / "home"
    tree.mkdir()
    slug = "".join(c if c.isalnum() else "-" for c in str(tree))
    path = home / ".claude/projects" / slug / "s.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"type": "assistant", "message": {"model": model}}) + "\n")
    bound = {} if expected is None else {"expected_claude_model": expected}
    hits = scan.find_hits(tmp_path / "calls", tree, 0, home, {}, **bound)
    assert [hit["pattern"] for hit in hits] == ([pattern] if pattern else [])
    if pattern:
        with pytest.raises(SystemExit, match="cannot be cleared"):
            scan.refuse_clearing("cleared", hits, "run")


@pytest.mark.parametrize("expected", ["claude-opus-5-5", "claude-fable-5-1", "claude-haiku", "unknown"])
def test_scan_refuses_an_expected_claude_model_outside_the_cap(tmp_path, expected):
    with pytest.raises(SystemExit, match="Claude"):
        scan.find_hits(tmp_path / "calls", tmp_path, 0, tmp_path, {}, expected_claude_model=expected)


def claude_session(home, directory, model):
    slug = "".join(c if c.isalnum() else "-" for c in str(directory))
    path = Path(home) / ".claude/projects" / slug / f"{model}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "assistant", "message": {"model": model}}) + "\n")


def test_a_sonnet_answer_in_a_haiku_bound_run_is_a_non_clearable_hit(world, monkeypatch):
    from experiments.compare import prepare
    monkeypatch.setenv("COMPARE_CLAUDE_MODELS", HAIKU)
    records, record = start(world, "direct_task")
    claude_session(record["sandbox"]["home"], record["tree"], HAIKU)
    assert prepare.scan(records, world.solution) == []
    claude_session(record["sandbox"]["home"], record["tree"], SONNET)
    assert [hit["pattern"] for hit in prepare.scan(records, world.solution)] == ["Forbidden model"]
    with pytest.raises(SystemExit, match="cannot be cleared"):
        prepare.adjudicate(records, "cleared", "a probe")


@pytest.mark.parametrize("judge,other", [(HAIKU, SONNET), (SONNET, HAIKU)])
def test_a_claude_judge_is_bound_to_its_own_model_and_any_other_answer_is_non_clearable(world, judge, other):
    from experiments.compare import pool
    out = world.outside / "pool"
    (out / "records").mkdir(parents=True)
    bindings = world.outside / "score-claude.json"
    bindings.write_text(json.dumps({"providers.judge": "claude_unrestricted_workspace"}))
    mapping = {"judges": {judge: {"dir": "judge", "providers": str(bindings)}}, "batches": [["a", "b"]],
               "criterion_sha256": "frozen", "compare_base": "base", "runs": {}, "main": "/main",
               "runtime": "/runtime", "created_at": 0}
    (out / "records/mapping.json").write_text(json.dumps(mapping))
    pool.write_score_inputs(out, mapping, "intent", world.runtime)
    assert f"COMPARE_CLAUDE_MODELS={judge}" in (out / "records" / f"score-{judge}.sh").read_text()
    home = mapping["judges"][judge]["sandbox"]["home"]
    claude_session(home, out / "judges/judge", judge)
    assert pool.scan_judge(out, judge, "f" * 40) == []
    claude_session(home, out / "judges/judge", other)
    assert [hit["pattern"] for hit in pool.scan_judge(out, judge, "f" * 40)] == ["Forbidden model"]
    with pytest.raises(SystemExit, match="cannot be cleared"):
        pool.adjudicate_judge(out, judge, "cleared", "a probe")
