"""The authoring-check kit works end to end without any provider call.

A scripted stand-in for the agent CLI writes a workflow; the kit builds the
"before" arm, launches sessions, checks them and reads them out. The
no-provider stubs sit on PATH behind the stand-in, so any real provider launch
would fail and be logged. The launcher's slot ledger lives under a temporary
HOME. Every test removes what it wrote, so no solution is left under /tmp.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "experiments" / "authoring_check"
NO_PROVIDER = REPO / "experiments" / "thread_m" / "no_provider"
MODEL = "claude-haiku-5-5"

HEADER = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule tally) (export run)
  (defrecord Tally (lines Int) (rounds Int))
  (defworkflow run ((file String) (target Int)) -> Tally
'''
COUNT = '(command-result count :argv ("sh" "count.sh" file) :returns Int)'
APPEND = '(command-result append :argv ("sh" "append.sh" file) :returns Bool)'
LOOP = '''    (loop/recur
      :max 8
      :state (record Tally :lines 0 :rounds 0)
      (fn (state)
        (let* ((lines {count}))
          (if {stop}
            (done (record Tally :lines lines :rounds state.rounds))
            (let* ((added {append}))
              (continue (record Tally :lines lines :rounds (+ state.rounds 1))))))))))
'''
COMMANDS = {
    "commands.json": json.dumps({
        "count": {"stable_command": ["sh", "count.sh"], "closure": ["count.sh", "line_count.sh"]},
        "append": {"stable_command": ["sh", "append.sh"], "closure": ["append.sh"]}}),
    "count.sh": 'sh line_count.sh "$1" > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"\n',
    "append.sh": 'echo more >> "$1"\necho true > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"\n',
}
CORRECT = {**COMMANDS, "tally.orc": HEADER + LOOP.format(
    count=COUNT, append=APPEND, stop="(or (>= lines target) (>= state.rounds 6))")}
# A real loop whose stop rule is a table of the three fixed cases; any other target exhausts the loop.
LOOKUP = {**COMMANDS, "tally.orc": HEADER + LOOP.format(
    count=COUNT, append=APPEND, stop="(= state.rounds (if (= target 5) 3 (if (= target 50) 6 (if (= target 3) 0 99))))")}
# The visible example's value with no command at all; wrong on every hidden case.
CONSTANT = {"commands.json": "{}", "tally.orc": HEADER + "    (record Tally :lines 5 :rounds 3)))\n"}
# One command that runs the whole loop in a shell script: right values, but not a workflow of rounds.
SINGLE_SCRIPT = {
    "commands.json": json.dumps({"all": {"stable_command": ["sh", "all.sh"], "closure": ["all.sh", "line_count.sh"]}}),
    "all.sh": 'r=0\nwhile :; do n=$(sh line_count.sh "$1")\n  if [ "$n" -ge "$2" ] || [ $r -ge 6 ]; then break; fi\n'
              '  echo x >> "$1"; r=$((r+1)); done\nprintf \'{"lines": %s, "rounds": %s}\' "$n" "$r" > '
              '"$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"\n',
    "tally.orc": HEADER + '    (command-result all :argv ("sh" "all.sh" file target) :returns Tally)))\n',
}

# Stand-in for the agent CLI. `--version` prints a version. Otherwise it logs its argv, cwd, environment and
# what `claude` and `codex` resolve to on its PATH to
# calls.jsonl beside itself, writes the solution in solution.json beside itself into its working directory,
# leaves a sleeping child behind when a file `linger` is beside it, and prints a stream-json transcript.
FAKE_AGENT = r'''import json, os, shutil, subprocess, sys
from pathlib import Path
here = Path(__file__).resolve().parent
if sys.argv[1:] == ["--version"]:
    print((here / "version").read_text().strip() if (here / "version").exists() else "9.9.9 (Claude Code)")
    sys.exit(0)
with (here / "calls.jsonl").open("a") as log:
    found = {cli: Path(shutil.which(cli)).read_text()[:300] if shutil.which(cli) else None for cli in ("claude", "codex")}
    log.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ), "found": found}) + "\n")
for name, text in json.loads((here / "solution.json").read_text()).items():
    Path(name).write_text(text)
if (here / "linger").exists():
    child = subprocess.Popen(["sleep", "300"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (here / "linger.pid").write_text(str(child.pid))
model = "claude-haiku-5-5"
events = [
    {"type": "system", "subtype": "init", "model": model},
    {"type": "assistant", "message": {"model": model, "content": [{"type": "tool_use", "id": "t1", "name": "Bash",
        "input": {"command": "orchestrator compile tally.orc --command-boundaries-file commands.json"}}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True}]}},
    {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.25,
     "usage": {"input_tokens": 100, "output_tokens": 20}, "modelUsage": {model: {}}},
]
print("\n".join(json.dumps(event) for event in events))
'''


def _load_readout():
    spec = importlib.util.spec_from_file_location("authoring_check_readout", KIT / "readout.py")
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode, before = True, sys.dont_write_bytecode  # no __pycache__ in the kit
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = before
    return module


readout = _load_readout()


@pytest.fixture(scope="module")
def arm_env(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("arm") / "before"
    env = {**os.environ, "PATH": os.pathsep.join([str(NO_PROVIDER), os.environ["PATH"]])}
    env.pop("PYTHONPATH", None)
    built = subprocess.run([sys.executable, str(KIT / "build_env.py"), "before", str(out)],
                           env=env, capture_output=True, text=True, timeout=600, check=False)
    assert built.returncode == 0, built.stderr
    yield out
    shutil.rmtree(out.parent, ignore_errors=True)


@pytest.fixture
def workspace(tmp_path) -> Path:
    fake = tmp_path / "fake-bin" / "claude"
    fake.parent.mkdir()
    fake.write_text(f"#!{sys.executable}\n" + FAKE_AGENT)
    fake.chmod(0o700)
    (tmp_path / "home").mkdir()
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


def _launch(tmp: Path, arm_env: Path, solution: dict, *, root: str = "sessions", authorized: bool = True,
            **extra: str) -> subprocess.CompletedProcess[str]:
    (tmp / "fake-bin" / "solution.json").write_text(json.dumps(solution))
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env.update(PATH=os.pathsep.join([str(tmp / "fake-bin"), str(NO_PROVIDER), os.environ["PATH"]]),
               HOME=str(tmp / "home"), CLAUDE_CODE_MESSAGING_TOKEN="canary", **extra)
    if authorized:
        env["AUTHORING_CHECK_SPEND_AUTHORIZED"] = "yes"
    return subprocess.run(["bash", str(KIT / "run_session.sh"), str(arm_env), str(tmp / root)],
                          env=env, capture_output=True, text=True, timeout=600, check=False)


def _agent_calls(tmp: Path) -> list[dict]:
    log = tmp / "fake-bin" / "calls.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def _check(arm_env: Path, tmp: Path, solution: dict) -> dict:
    directory = tmp / "solution"
    directory.mkdir()
    for name, text in solution.items():
        (directory / name).write_text(text)
    shutil.copy2(KIT / "line_count.sh", directory)
    env = {**os.environ, "PATH": os.pathsep.join([str(arm_env / "venv" / "bin"), str(NO_PROVIDER), os.environ["PATH"]])}
    env.pop("PYTHONPATH", None)
    checked = subprocess.run([sys.executable, str(KIT / "check.py"), str(directory)], env=env,
                             capture_output=True, text=True, timeout=600, check=False)
    return json.loads(checked.stdout)


def _cases(check: dict) -> dict[str, bool]:
    return {case["case"]: case["passed"] for case in check["cases"]}


def test_the_before_arm_installs_the_phase_base_with_the_drafting_guide(arm_env):
    facts = json.loads((arm_env / "env.json").read_text())
    assert facts["document"] == "docs/lisp_workflow_drafting_guide.md"
    assert Path(facts["orchestrator_module"]).is_relative_to(arm_env / "venv")


def test_check_passes_a_workflow_that_counts_and_appends_in_rounds(arm_env, workspace):
    assert _check(arm_env, workspace, CORRECT)["passed"] is True


def test_check_fails_a_single_script_that_does_the_whole_loop(arm_env, workspace):
    check = _check(arm_env, workspace, SINGLE_SCRIPT)
    assert (check["passed"], _cases(check)["visible"]) == (False, False)


def test_check_fails_a_lookup_table_of_the_fixed_cases_on_the_random_case(arm_env, workspace):
    assert _cases(_check(arm_env, workspace, LOOKUP)) == {
        "visible": True, "hidden_already_satisfied": True, "hidden_bound_reached": True, "hidden_random": False}


def test_check_fails_a_constant_workflow_on_every_case_even_where_the_value_matches(arm_env, workspace):
    check = _check(arm_env, workspace, CONSTANT)
    assert check["cases"][0]["outputs"] == check["cases"][0]["expected"]
    assert not any(_cases(check).values())


def test_the_launcher_refuses_without_spend_authorization(workspace, arm_env):
    refused = _launch(workspace, arm_env, CORRECT, authorized=False)
    assert refused.returncode == 3
    assert _agent_calls(workspace) == [] and not (workspace / "sessions").exists()


def test_the_launcher_binds_model_cap_tools_and_no_fallback(workspace, arm_env):
    assert _launch(workspace, arm_env, CORRECT).returncode == 0
    (call,) = _agent_calls(workspace)
    argv = call["argv"]
    bound = {argv[i]: argv[i + 1] for i in range(len(argv) - 1)
             if argv[i] in ("--model", "--max-budget-usd", "--tools", "--permission-mode", "--setting-sources")}
    assert bound == {"--model": MODEL, "--max-budget-usd": "2", "--tools": "Bash,Read,Write,Edit",
                     "--permission-mode": "bypassPermissions", "--setting-sources": "project"}
    assert {"--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"} <= set(argv)
    assert not any(arg.startswith("--fallback-model") or "fable" in arg.lower() for arg in argv)


def test_the_session_environment_is_an_allowlist_with_stubs_ahead_of_real_clis(workspace, arm_env):
    assert _launch(workspace, arm_env, CORRECT).returncode == 0
    (call,) = _agent_calls(workspace)
    env = call["env"]
    assert "CLAUDE_CODE_MESSAGING_TOKEN" not in env and "PYTHONPATH" not in env
    assert {env[key] for key in ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_SMALL_FAST_MODEL", "ANTHROPIC_MODEL",
                                 "ANTHROPIC_DEFAULT_FABLE_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL")} == {MODEL}
    assert {env[key] for key in ("CLAUDE_CODE_DISABLE_ADVISOR_TOOL", "CLAUDE_CODE_DISABLE_CLAUDE_MDS",
                                 "CLAUDE_CODE_DISABLE_AUTO_MEMORY", "DISABLE_AUTOUPDATER")} == {"1"}
    assert all("no provider calls" in (found or "") for found in call["found"].values())


def test_the_session_works_in_a_fresh_random_directory_moved_to_its_slot_afterwards(workspace, arm_env):
    assert _launch(workspace, arm_env, CORRECT).returncode == 0
    (call,) = _agent_calls(workspace)
    session = workspace / "sessions" / "before-1"
    assert not Path(call["cwd"]).is_relative_to(workspace) and not Path(call["cwd"]).exists()
    assert json.loads((session / "session.json").read_text())["work_during_session"] == call["cwd"]
    assert (session / "work" / "tally.orc").is_file()


def test_the_slot_ledger_outlives_the_sessions_root(workspace, arm_env):
    for n in (1, 2, 3):
        (workspace / "home" / ".local" / "state" / "authoring-check" / f"before-{n}").mkdir(parents=True)
    refused = _launch(workspace, arm_env, CORRECT, root="another-root")
    assert refused.returncode == 3 and _agent_calls(workspace) == []


def test_the_launcher_refuses_a_cli_version_other_than_the_first_sessions(workspace, arm_env):
    ledger = workspace / "home" / ".local" / "state" / "authoring-check"
    ledger.mkdir(parents=True)
    (ledger / "claude-version").write_text("0.0.1 (Claude Code)\n")
    refused = _launch(workspace, arm_env, CORRECT)
    assert refused.returncode == 3 and _agent_calls(workspace) == []


def test_the_launcher_kills_what_the_session_leaves_running(workspace, arm_env):
    (workspace / "fake-bin" / "linger").write_text("")
    assert _launch(workspace, arm_env, CORRECT).returncode == 0
    pid = int((workspace / "fake-bin" / "linger.pid").read_text())
    assert not Path(f"/proc/{pid}").exists() or "Z" in Path(f"/proc/{pid}/stat").read_text().split()[2]


def test_the_kit_passes_a_correct_session_and_fails_a_constant_one(workspace, arm_env):
    for solution in (CORRECT, CONSTANT):
        assert _launch(workspace, arm_env, solution).returncode == 0
    report = readout.readout(workspace / "sessions")
    sessions = {row["session"]: row for row in report["sessions"]}
    assert (sessions["before-1"]["fail_reasons"], sessions["before-2"]["fail_reasons"]) == ([], ["check_failed"])
    assert report["arms"]["before"]["ledger_charge_usd"] == 0.5


# Readout over hand-written sessions: one baseline that passes, and one change per fail reason.
WORK = "/tmp/ac-readouttest"


def _rows(model: str = MODEL, command: str = "orchestrator compile tally.orc", output: str = "ok") -> list[dict]:
    return [
        {"type": "system", "subtype": "init", "model": model},
        {"type": "assistant", "message": {"model": model, "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": command}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": output}]}},
        {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.25, "usage": {},
         "modelUsage": {model: {}}},
    ]


def _session(tmp: Path, rows: list[dict], **meta: object) -> Path:
    home = tmp / "home"
    directory = tmp / "sessions" / "before-1"
    directory.mkdir(parents=True)
    (directory / "session.json").write_text(json.dumps({
        "arm": "before", "model": MODEL, "checkout": str(home / "Documents" / "agent-orchestration"),
        "home": str(home), "sessions_root": str(tmp / "sessions"), "work_during_session": WORK,
        "started": 0, "ended": 10, "claude_exit": 0, "check_exit": 0, **meta}))
    (directory / "check.json").write_text('{"passed": true}')
    (directory / "transcript.jsonl").write_text("\n".join(json.dumps(row) for row in rows))
    return directory


def _reasons(tmp: Path) -> list[str]:
    return readout.readout(tmp / "sessions")["sessions"][0]["fail_reasons"]


def _nested_claude(tmp: Path) -> None:
    store = tmp / "home" / ".claude" / "projects" / WORK.replace("/", "-")
    store.mkdir(parents=True)
    (store / "s.jsonl").write_text("{}\n")


def _nested_codex(tmp: Path) -> None:
    store = tmp / "home" / ".codex" / "sessions" / "2026" / "11" / "11"
    store.mkdir(parents=True)
    (store / "rollout-1.jsonl").write_text(json.dumps({"payload": {"cwd": WORK}}) + "\n")


def _stub_called(tmp: Path) -> None:
    (tmp / "sessions" / "before-1" / "no-provider.log").write_text("claude -p\n")


def test_the_readout_passes_a_clean_session(tmp_path):
    _session(tmp_path, _rows())
    assert _reasons(tmp_path) == []


def test_the_readout_allows_the_cli_naming_its_own_saved_tool_output(tmp_path):
    saved = f"Output too large. Full output saved to: {{home}}/.claude/projects/{WORK.replace('/', '-')}/abc/tool-results/x.txt"
    rows = json.loads(json.dumps(_rows(command="cat GUIDE.md", output=saved)).replace("{home}", str(tmp_path / "home")))
    _session(tmp_path, rows)
    assert _reasons(tmp_path) == []


@pytest.mark.parametrize(("rows", "after", "meta", "reason"), [
    (_rows(command="claude -p 'write tally.orc'"), None, {}, "nested_cli"),
    (_rows(command="~/.local/bin/codex exec hi"), None, {}, "nested_cli"),
    (_rows(command="orchestrator run x --model claude-fable-5-1"), None, {}, "nested_cli"),
    (_rows(model="claude-haiku-4-5"), None, {}, "models_not_exactly_bound"),
    ([{**row, "model": "claude-fable-5-1"} if row["type"] == "system" else row for row in _rows()], None, {},
     "models_not_exactly_bound"),
    ([row for row in _rows() if row["type"] in ("user",)] + [{"type": "result", "subtype": "success",
      "total_cost_usd": 0.1, "modelUsage": {}}], None, {}, "models_not_exactly_bound"),
    (_rows(), _nested_claude, {}, "nested_session"),
    (_rows(), _nested_codex, {}, "nested_session"),
    (_rows(), _stub_called, {}, "provider_stub_called"),
    (_rows(command="ls ~/Documents/agent-orchestration/experiments"), None, {}, "checkout_read"),
    (_rows(command="cat ../../srv/agent-orchestration/x"), None, {"checkout": "/srv/agent-orchestration"},
     "checkout_read"),
    (_rows(command="find / -name '*.orc'", output="{home}/Documents/agent-orchestration/tests/x.orc"), None, {},
     "checkout_read"),
    (_rows(command="ls ..", output="{sessions}/before-1/check.json"), None, {}, "sessions_root_read"),
    (_rows(command="ls ~/.claude/projects"), None, {}, "other_sessions_read"),
    (_rows(), None, {"claude_exit": 124}, "wall_limit"),
    (_rows()[:-1], None, {}, "result_missing"),
])
def test_the_readout_fails_a_session_for_each_reason(tmp_path, rows, after, meta, reason):
    text = json.dumps(rows).replace("{home}", str(tmp_path / "home")).replace("{sessions}", str(tmp_path / "sessions"))
    _session(tmp_path, json.loads(text), **meta)
    if after:
        after(tmp_path)
    assert reason in _reasons(tmp_path)


def test_the_readout_charges_the_cap_for_a_session_without_a_cost_record(tmp_path):
    _session(tmp_path, _rows()[:-1])
    report = readout.readout(tmp_path / "sessions")
    assert report["sessions"][0]["cost_usd"] is None
    assert (report["arms"]["before"]["cost_unknown_sessions"], report["arms"]["before"]["ledger_charge_usd"]) == (1, 2.0)
