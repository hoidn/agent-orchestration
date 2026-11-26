"""Seed-set programs (experiments/seed_set/programs/): each compiles at 2.40 and runs end to end through the public
CLI against a scripted `claude` and the real dev-check and reset-clone boundaries, in a clone built by the
comparison harness's `build_candidate`. No provider is called."""

import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

import pytest

from experiments.compare.repos import build_candidate, git
from experiments.seed_set import study
from experiments.seed_set.selection import COMMON_TYPES, MAX_PROGRAM_LINES, common_definitions, program_lines
from tests.agent_session_shims import closed_path

ROOT = Path(__file__).resolve().parents[2]
PROGRAMS = ROOT / "experiments" / "seed_set" / "programs"
ARMS = json.loads((PROGRAMS / "arms.json").read_text())
BOUNDARIES = ("dev_check.py", "reset_clone.py")
CHECK_TOKEN = "CHECK-OUTPUT-7f3a"  # printed by the visible check when it fails
FINDING = "FINDING-5c1e"
# The visible check passes when solution.txt holds "ok".
CHECK = ("import pathlib, sys; p = pathlib.Path('solution.txt'); ok = p.is_file() and p.read_text() == 'ok'; "
         f"print('passed' if ok else '{CHECK_TOKEN}'); sys.exit(0 if ok else 1)")
# The scripted claude: answers call k with entry k of $SEED_SET_SCRIPT, logs every call to $SEED_SET_CALLS
# (argv, prompt, whether solution.txt existed); an entry may write solution.txt, or kill the orchestrator.
SHIM = f"""#!{sys.executable} -I
import json, os, signal, sys
from pathlib import Path
prompt = sys.stdin.read()
log = Path(os.environ["SEED_SET_CALLS"])
index = len(log.read_text().splitlines()) if log.exists() else 0
entry = json.loads(Path(os.environ["SEED_SET_SCRIPT"]).read_text())[index]
with log.open("a") as out:
    out.write(json.dumps({{"argv": sys.argv[1:], "prompt": prompt, "solution": Path("solution.txt").exists()}}) + "\\n")
if entry.get("kill"):
    os.kill(os.getppid(), signal.SIGKILL)
    sys.exit(1)
if "write" in entry:
    Path("solution.txt").write_text(entry["write"])
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(entry["result"]))
"""


def change(write=None, summary="s"):
    entry = {"result": {"summary": summary, "account": "a"}}
    return entry if write is None else {**entry, "write": write}


APPROVE = {"result": {"variant": "APPROVE", "notes": []}}
REQUEST = {"result": {"variant": "REQUEST_CHANGES", "findings": [FINDING]}}
KILL = {"kill": True}


@pytest.fixture
def world(tmp_path):
    """A harness-built clone (base commit + "compare seed" commit holding dev-check.json) with the boundary
    scripts copied in and excluded from its patch, and the scripted claude first on PATH."""
    source, seed = tmp_path / "source", tmp_path / "seed"
    source.mkdir()
    seed.mkdir()
    git(source, "init", "-q")
    (source / ".gitignore").write_text(".orchestrate/\n")
    git(source, "add", ".gitignore")
    git(source, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base")
    (seed / "dev-check.json").write_text(json.dumps({"argv": [sys.executable, "-c", CHECK], "timeout_sec": 30}))
    repo = tmp_path / "repo"
    build_candidate(source, git(source, "rev-parse", "HEAD"), seed, repo)
    for name in BOUNDARIES:
        shutil.copyfile(PROGRAMS / name, repo / name)
    with (repo / ".git" / "info" / "exclude").open("a") as exclude:
        exclude.write("".join(f"/{name}\n" for name in BOUNDARIES))
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "claude").write_text(SHIM)
    (tmp_path / "bin" / "claude").chmod(0o700)
    return tmp_path


def cli(world, *args):
    env = {**os.environ, "PATH": closed_path(world / "bin"), "PYTHONPATH": str(ROOT),
           "PYTHONDONTWRITEBYTECODE": "1", "SEED_SET_CALLS": str(world / "calls.jsonl"),
           "SEED_SET_SCRIPT": str(world / "script.json")}
    return subprocess.run([sys.executable, "-B", "-m", "orchestrator", *args], cwd=world / "repo", env=env,
                          capture_output=True, text=True, timeout=300)


def run(world, arm, script):
    """Run `arm` as arms.json binds it; return (terminal value or None, provider calls, effect names)."""
    spec = ARMS[arm]
    (world / "script.json").write_text(json.dumps(script))
    inputs = world / "inputs.json"
    inputs.write_text(json.dumps({"task": "make the check pass", "intent": "the check passes",
                                  "repo": str(world / "repo"), "model": spec["model"], "effort": spec["effort"]}))
    proc = cli(world, "run", str(PROGRAMS / spec["source"]), "--entry-workflow", spec["entry"],
               "--source-root", str(PROGRAMS), "--provider-externs-file", str(PROGRAMS / "providers.json"),
               "--command-boundaries-file", str(PROGRAMS / "commands.json"), "--input-file", str(inputs))
    if any(entry.get("kill") for entry in script):
        assert proc.returncode == -signal.SIGKILL, proc.stdout + proc.stderr
        (run_root,) = (world / "repo" / ".orchestrate" / "runs").iterdir()
        proc = cli(world, "resume", run_root.name)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return terminal(world), calls(world)


def terminal(world):
    (run_root,) = (world / "repo" / ".orchestrate" / "runs").iterdir()
    rows = [json.loads(line) for line in (run_root / "memo.jsonl").read_text().splitlines()]
    (end,) = [row for row in rows if row["record"] == "terminal"]
    return end["value"]


def calls(world):
    return [json.loads(line) for line in (world / "calls.jsonl").read_text().splitlines()]


def sees_check_output(call):
    return CHECK_TOKEN in call["prompt"]


@pytest.mark.parametrize("arm", ["direct", "retry_until_check", "implement_check_repair", "implement_review_revise"])
def test_program_compiles_at_2_40(arm):
    spec = ARMS[arm]
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "orchestrator", "compile", str(PROGRAMS / spec["source"]),
         "--entry-workflow", spec["entry"], "--source-root", str(PROGRAMS),
         "--provider-externs-file", str(PROGRAMS / "providers.json"),
         "--command-boundaries-file", str(PROGRAMS / "commands.json"), "--diagnostics-json"],
        cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)}, capture_output=True, text=True)
    assert json.loads(proc.stdout)["status"] == "accepted", proc.stdout + proc.stderr


@pytest.mark.parametrize("arm", sorted(ARMS))
def test_every_arms_program_is_under_the_line_limit(arm):
    assert program_lines(PROGRAMS / ARMS[arm]["source"]) < MAX_PROGRAM_LINES


def test_common_defines_only_the_shared_result_types():
    assert common_definitions(PROGRAMS / "common.orc") == sorted(COMMON_TYPES)


def test_no_program_names_a_model():
    assert [p.name for p in PROGRAMS.glob("*.orc") if re.search(r'claude-|gpt-|:model "', p.read_text())] == []


def command_forms(text, head="command-result"):
    """Every `(<head> ...)` form of a program (a command step by default), parentheses balanced."""
    forms = []
    for start in [m.start() for m in re.finditer(rf"\({head}\b", text)]:
        depth = 0
        for end in range(start, len(text)):
            depth += {"(": 1, ")": -1}.get(text[end], 0)
            if depth == 0:
                forms.append(text[start:end + 1])
                break
    return forms


def test_no_command_step_has_a_timeout_below_the_checks_own():
    """The orchestrator SIGKILLs a command step at its timeout, which would leave a check-withheld test in the tree;
    dev_check.py applies dev-check.json's own timeout (600 s in every package) and restores the tree itself."""
    tasks = ROOT / "experiments" / "seed_set" / "tasks"
    own = {json.loads(path.read_text())["timeout_sec"] for path in tasks.glob("*/seed/dev-check.json")}
    forms = [form for path in sorted(PROGRAMS.glob("*.orc")) for form in command_forms(path.read_text())]
    limits = [int(m[1]) for form in forms if (m := re.search(r":timeout-sec\s+(\d+)", form))]
    assert (own, len(forms), [limit for limit in limits if limit < max(own)]) == ({600}, 3, [])


def test_every_provider_call_has_the_kits_call_limit():  # the launch guard and the login check use study.CALL_SEC
    forms = [form for path in sorted(PROGRAMS.glob("*.orc"))
             for form in command_forms(path.read_text(), "provider-result")]
    assert ({re.search(r":timeout-sec\s+(\d+)", form)[1] for form in forms}, len(forms)) == ({str(study.CALL_SEC)}, 7)


def test_every_real_withheld_package_names_its_tests_for_the_check_and_keeps_none_in_its_seed():
    tasks = ROOT / "experiments" / "seed_set" / "tasks"
    found = {}
    for package in sorted(tasks.iterdir()):
        config = json.loads((package / "seed" / "dev-check.json").read_text())
        withheld = (package / "withheld").is_dir()
        found[package.name] = (withheld, bool(config.get("withheld")),
                               withheld and any((package / "seed").rglob("test_*.py")))
    assert {value for value in found.values()} == {(True, True, False), (False, False, False)}


def test_every_program_has_the_same_implementer_prompt():
    prompts = {re.search(r"\(defprompt implement-prompt.*?\"\)", p.read_text(), re.S).group(0)
               for p in PROGRAMS.glob("*.orc") if p.name != "common.orc"}
    assert len(prompts) == 1


def test_every_call_uses_the_bound_model_and_effort_on_the_metered_template(world):  # ruling R4
    run(world, "implement_review_revise", [change("ok"), REQUEST, change("ok")])
    def after(argv, flag):
        return argv[argv.index(flag) + 1]
    assert {tuple(after(call["argv"], flag) for flag in ("--model", "--effort", "--output-format"))
            for call in calls(world)} == {("claude-haiku-5-5", "medium", "stream-json")}


def test_direct_makes_one_call(world):
    value, made = run(world, "direct", [change("bad", summary="first")])
    assert (value, len(made)) == ({"variant": "DONE", "summary": "first"}, 1)


def test_retry_stops_at_the_first_pass(world):
    value, made = run(world, "retry_until_check", [change("ok", summary="first")])
    assert (value, len(made)) == ({"variant": "DONE", "summary": "first"}, 1)


def test_retry_after_a_failed_check_starts_from_the_seeded_tree(world):
    value, made = run(world, "retry_until_check", [change("bad"), change("ok", summary="second")])
    assert (value, [call["solution"] for call in made], [sees_check_output(c) for c in made]) == (
        {"variant": "DONE", "summary": "second"}, [False, False], [False, False])


def test_retry_gives_up_after_three_attempts(world):
    value, made = run(world, "retry_until_check", [change("bad")] * 3)
    assert (value["variant"], len(made)) == ("BLOCKED", 3)


def test_repair_is_skipped_when_the_check_passes(world):
    value, made = run(world, "implement_check_repair", [change("ok", summary="first")])
    assert (value, len(made)) == ({"variant": "DONE", "summary": "first"}, 1)


def test_repair_works_in_place_and_sees_the_check_output(world):
    value, made = run(world, "implement_check_repair", [change("bad"), change("ok", summary="repaired")])
    assert (value, [call["solution"] for call in made], [sees_check_output(c) for c in made]) == (
        {"variant": "DONE", "summary": "repaired"}, [False, True], [False, True])


def test_repair_gives_up_after_two_repairs(world):
    value, made = run(world, "implement_check_repair", [change("bad")] * 3)
    assert (value["variant"], len(made)) == ("BLOCKED", 3)


def test_approved_change_is_not_revised(world):
    value, made = run(world, "implement_review_revise", [change("ok", summary="first"), APPROVE])
    assert (value, len(made)) == ({"variant": "DONE", "summary": "first"}, 2)


def test_requested_changes_reach_one_revision(world):
    value, made = run(world, "implement_review_revise", [change("ok"), REQUEST, change("ok", summary="revised")])
    assert (value, [FINDING in call["prompt"] for call in made]) == (
        {"variant": "DONE", "summary": "revised"}, [False, False, True])


@pytest.mark.parametrize("arm, script, summary", [
    ("direct", [KILL, change("ok", summary="after")], "after"),
    ("retry_until_check", [change("bad"), KILL, change("ok", summary="after")], "after"),
    ("implement_check_repair", [change("bad"), KILL, change("ok", summary="after")], "after"),
    ("implement_review_revise", [change("ok"), REQUEST, KILL, change("ok", summary="after")], "after"),
])
def test_killed_run_resumes_without_repeating_a_committed_call(world, arm, script, summary):
    """The orchestrator is killed inside call k; on resume the calls before k are not made again."""
    value, made = run(world, arm, script)
    assert (value, len(made)) == ({"variant": "DONE", "summary": summary}, len(script))
