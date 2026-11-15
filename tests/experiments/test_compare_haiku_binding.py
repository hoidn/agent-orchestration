"""Haiku binding: the real guard, shims, sandbox and scan with scripted CLIs, never provider calls.

A unit's one Claude model is fixed when it is prepared (sandbox.json); the launch environment can only
narrow it. Inside the sandbox the binding file and the guard directory are read-only to the candidate.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from experiments.compare import pool, prepare, sandbox, scan
from tests.agent_session_shims import closed_path
from tests.experiments.compare_harness_support import SHIM, call, skip_without_sandbox, start, world  # noqa: F401
from tests.experiments.test_compare_model_cap import DISABLED, guarded  # noqa: F401

SONNET, HAIKU = "claude-sonnet-5-5", "claude-haiku-5-5"
PROBE = ("printf 'binding=%s\\n' \"$(cat /.compare-claude-model)\"; echo pin=$CLAUDE_CODE_SUBAGENT_MODEL; "
         f"claude --model {HAIKU} </dev/null; echo haiku=$?; claude --model {SONNET} </dev/null; echo sonnet=$?")


def lines(stdout):
    return [line for line in stdout.splitlines() if "=" in line and not line.startswith("PYTHONPATH=")]


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


def confined_guard(tmp_path, binding, name, args, **env):
    """Run the real guard as `name` in a minimal bubblewrap root whose binding file holds `binding`."""
    guard, real = tmp_path / "guard", tmp_path / "real"
    for directory in (guard, real):
        directory.mkdir(exist_ok=True)
    shutil.copyfile(Path(sandbox.__file__).with_name("shim") / "model-guard", guard / name)
    (real / name).write_text('#!/bin/sh\necho "ran=$* forced=$CLAUDE_CODE_SUBAGENT_MODEL"\nexit 3\n')
    for path in (guard / name, real / name):
        path.chmod(0o755)
    reader, writer = os.pipe()
    os.write(writer, binding.encode())
    os.close(writer)
    root = []
    for part in ("bin", "sbin", "lib", "lib64"):
        path = Path("/" + part)
        root += (["--symlink", str(path.resolve()), str(path)] if path.is_symlink()
                 else ["--ro-bind", str(path), str(path)] if path.exists() else [])
    command = ["bwrap", "--die-with-parent", "--unshare-pid", "--clearenv", "--proc", "/proc", "--dev", "/dev",
               "--ro-bind", "/usr", "/usr", *root, "--ro-bind", str(guard), str(guard),
               "--ro-bind", str(real), str(real), "--ro-bind-data", str(reader), "/.compare-claude-model",
               "--setenv", "PATH", f"{guard}:{real}:/usr/bin",
               *[part for key, value in env.items() for part in ("--setenv", key, value)],
               "--", str(guard / name), *args]
    try:
        return subprocess.run(command, capture_output=True, text=True, pass_fds=(reader,))
    finally:
        os.close(reader)


@pytest.mark.parametrize("binding", ["", "claude-opus-5-5", "claude-fable-5-1", f" {SONNET}", f"{SONNET} ",
                                     f"{SONNET}\n{HAIKU}", f"{HAIKU}-preview", "claude-haiku"])
@pytest.mark.parametrize("name", ["claude", "codex"])
def test_a_malformed_binding_file_refuses_both_cli_names(tmp_path, binding, name):
    skip_without_sandbox()
    done = confined_guard(tmp_path, binding, name, [], ORC_ALLOWED_CLAUDE_MODELS=HAIKU)
    assert (done.returncode, "ran=" in done.stdout) == (2, False), done.stdout + done.stderr


@pytest.mark.parametrize("binding,model,status", [
    (HAIKU, HAIKU, 3), (f"{HAIKU}\n", HAIKU, 3), (SONNET, HAIKU, 2), (HAIKU, SONNET, 2)])
def test_the_binding_file_and_not_the_opt_in_decides_the_bound_model(tmp_path, binding, model, status):
    skip_without_sandbox()
    done = confined_guard(tmp_path, binding, "claude", ["--model", model],
                          ORC_ALLOWED_CLAUDE_MODELS=f"{SONNET},{HAIKU}")
    assert done.returncode == status, done.stdout + done.stderr


def test_haiku_run_binds_its_shim_and_nested_calls_cannot_change_the_binding(world, monkeypatch):
    skip_without_sandbox()
    monkeypatch.setenv("COMPARE_CLAUDE_MODELS", HAIKU)
    records, record = start(world, "direct_task")
    for script in ("command.sh", "resume.sh"):
        assert f"COMPARE_CLAUDE_MODELS={HAIKU}" in (records / script).read_text()
    done = call(world, record, PROBE + "; "
                f"env -u ORC_ALLOWED_CLAUDE_MODELS CLAUDE_CODE_SUBAGENT_MODEL={SONNET} claude --model {SONNET}"
                " </dev/null; echo dropped=$?", args=("--model", HAIKU, "-p"))
    assert done.returncode == 0, done.stderr
    assert lines(done.stdout) == [f"binding={HAIKU}", f"pin={HAIKU}", "haiku=0", "sonnet=2", "dropped=2"]


def test_a_list_opt_in_binds_sonnet_and_never_admits_haiku(world, monkeypatch):
    skip_without_sandbox()
    monkeypatch.setenv("COMPARE_CLAUDE_MODELS", f"{SONNET},{HAIKU}")
    records, record = start(world, "direct_task")
    assert (record["claude_model"], json.loads((records / "sandbox.json").read_text())["claude_model"]) == (
        SONNET, SONNET)
    done = call(world, record, PROBE, binary="codex")
    assert done.returncode == 0, done.stderr
    assert lines(done.stdout) == [f"binding={SONNET}", f"pin={SONNET}", "haiku=2", "sonnet=0"]


def scripted_runtime(world):
    """After preparation: the frozen runtime's orchestrator makes one codex call through the shims its scripts
    put first on PATH (the toy runtime links the real ones), running PROBE."""
    (world.runtime / "experiments/compare").mkdir(parents=True)
    (world.runtime / "experiments/compare/shim").symlink_to(SHIM)
    (world.runtime / "orchestrator/__main__.py").write_text(
        "import subprocess, sys\n"
        f"done = subprocess.run(['codex', 'exec'], input={PROBE!r}, text=True, capture_output=True)\n"
        "print(done.stdout + done.stderr)\nsys.exit(done.returncode)\n")


def run_script(records, script, ambient):
    env = {key: value for key, value in os.environ.items() if key != "COMPARE_CLAUDE_MODELS"}
    env |= {"PATH": closed_path()} | ({} if ambient is None else {"COMPARE_CLAUDE_MODELS": ambient})
    return subprocess.run(["bash", str(records / script), *(["R1"] if script == "resume.sh" else [])],
                          capture_output=True, text=True, env=env, timeout=60)


@pytest.mark.parametrize("script", ["command.sh", "resume.sh"])
def test_an_ambient_haiku_opt_in_cannot_rebind_a_sonnet_unit_through_its_scripts(world, script):
    skip_without_sandbox()
    records, record = start(world, "direct_task")
    scripted_runtime(world)
    done = run_script(records, script, HAIKU)
    assert done.returncode == 0, done.stdout + done.stderr
    # the ambient opt-in narrows: Sonnet stays bound and Haiku stays refused, so nothing runs on Haiku
    assert (record["claude_model"], lines(done.stdout)) == (
        SONNET, [f"binding={SONNET}", f"pin={SONNET}", "haiku=2", "sonnet=2"])


@pytest.mark.parametrize("script", ["command.sh", "resume.sh"])
@pytest.mark.parametrize("ambient", [None, SONNET, ""])
def test_a_haiku_unit_stays_haiku_whatever_shell_launches_its_scripts(world, monkeypatch, script, ambient):
    skip_without_sandbox()
    monkeypatch.setenv("COMPARE_CLAUDE_MODELS", HAIKU)
    records, record = start(world, "direct_task")
    scripted_runtime(world)
    done = run_script(records, script, ambient)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (record["claude_model"], lines(done.stdout)) == (
        HAIKU, [f"binding={HAIKU}", f"pin={HAIKU}", "haiku=0", "sonnet=2"])


@pytest.mark.parametrize("ambient", [None, SONNET, ""])
def test_a_haiku_unit_launched_without_its_opt_in_refuses_every_claude_model(world, monkeypatch, ambient):
    skip_without_sandbox()
    monkeypatch.setenv("COMPARE_CLAUDE_MODELS", HAIKU)
    _, record = start(world, "direct_task")
    if ambient is None:
        monkeypatch.delenv("COMPARE_CLAUDE_MODELS")
    else:
        monkeypatch.setenv("COMPARE_CLAUDE_MODELS", ambient)
    for model in (HAIKU, SONNET):
        assert call(world, record, "true", args=("--model", model, "-p")).returncode == 2


def test_a_candidate_cannot_rebind_or_replace_the_binding_or_the_guard(world):
    skip_without_sandbox()
    _, record = start(world, "direct_task")
    assert call(world, record, "true", args=("--model", HAIKU, "-p")).returncode == 2
    guard, tree = Path(record["tree"]) / ".model-guard", record["tree"]
    attempts = {
        "widened": f"ORC_ALLOWED_CLAUDE_MODELS={HAIKU} CLAUDE_CODE_SUBAGENT_MODEL={HAIKU} claude --model {HAIKU}"
                   " </dev/null",
        "overwritten": f"printf {HAIKU} > /.compare-claude-model", "moved": "mv /.compare-claude-model /moved",
        "deleted": "rm -f /.compare-claude-model", "edited": f"printf '#!/bin/sh\\n' > {guard}/claude",
        "linked": f"ln -sf /bin/true {guard}/claude", "renamed": f"mv {guard} {tree}/guard-moved",
        # no nested user namespace on any host, so nothing can be mounted over the binding or the guard
        "removed": f"rm -rf {guard}", "nested namespace": "unshare -U true",
    }
    script = "; ".join(f"({command}) >/dev/null 2>&1; echo '{name}='$?" for name, command in attempts.items())
    done = call(world, record, script + "; printf 'binding=%s\\n' \"$(cat /.compare-claude-model)\"")
    assert done.returncode == 0, done.stderr
    results = dict(line.split("=", 1) for line in lines(done.stdout))
    assert ([name for name in attempts if results[name] == "0"], results["binding"]) == ([], SONNET)
    assert sorted(path.name for path in guard.iterdir()) == ["claude", "codex"]


def test_a_unit_declaration_binding_outside_the_cap_refuses_the_launch(world):
    skip_without_sandbox()
    records, record = start(world, "direct_task")
    declaration = records / "sandbox.json"
    declaration.write_text(json.dumps(json.loads(declaration.read_text()) | {"claude_model": "claude-opus-5-5"}))
    done = call(world, record, "echo ran")
    assert (done.returncode, "ran" in done.stdout) == (70, False), done.stdout + done.stderr


@pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-fable-5-1", f"{HAIKU}-preview", ""])
def test_prepare_unit_refuses_a_claude_binding_outside_the_cap(world, model):
    with pytest.raises(ValueError, match="Claude"):
        sandbox.prepare_unit(world.outside / "tree", world.outside / "records", homes=world.outside / "homes",
                             claude_model=model)


@pytest.mark.parametrize("expected,model,pattern", [
    (HAIKU, SONNET, "Forbidden model"), (HAIKU, "claude-fable-5-1", "Fable model"),
    (HAIKU, HAIKU, None), (None, HAIKU, "Forbidden model"),
])
def test_scan_flags_any_claude_answer_other_than_the_bound_model(tmp_path, expected, model, pattern):
    tree, home = tmp_path / "tree", tmp_path / "home"
    tree.mkdir()
    claude_session(home, tree, model)
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
    monkeypatch.setenv("COMPARE_CLAUDE_MODELS", HAIKU)
    records, record = start(world, "direct_task")
    claude_session(record["sandbox"]["home"], record["tree"], HAIKU)
    assert prepare.scan(records, world.solution) == []
    claude_session(record["sandbox"]["home"], record["tree"], SONNET)
    assert [hit["pattern"] for hit in prepare.scan(records, world.solution)] == ["Forbidden model"]
    with pytest.raises(SystemExit, match="cannot be cleared"):
        prepare.adjudicate(records, "cleared", "a probe")


@pytest.mark.parametrize("judge,other", [(HAIKU, SONNET), (SONNET, HAIKU)])
def test_a_claude_judge_is_bound_to_its_own_model_and_any_other_answer_is_non_clearable(
        world, monkeypatch, judge, other):
    monkeypatch.setenv("COMPARE_CLAUDE_MODELS", HAIKU if judge == SONNET else SONNET)  # ambient never decides
    out = world.outside / "pool"
    (out / "records").mkdir(parents=True)
    bindings = world.outside / "score-claude.json"
    bindings.write_text(json.dumps({"providers.judge": "claude_unrestricted_workspace"}))
    mapping = {"judges": {judge: {"dir": "judge", "providers": str(bindings)}}, "batches": [["a", "b"]],
               "criterion_sha256": "frozen", "compare_base": "base", "runs": {}, "main": "/main",
               "runtime": "/runtime", "created_at": 0}
    (out / "records/mapping.json").write_text(json.dumps(mapping))
    pool.write_score_inputs(out, mapping, "intent", world.runtime)
    assert (f"COMPARE_CLAUDE_MODELS={judge}" in (out / "records" / f"score-{judge}.sh").read_text(),
            json.loads((out / f"records/judges/{judge}/sandbox.json").read_text())["claude_model"]) == (True, judge)
    home = mapping["judges"][judge]["sandbox"]["home"]
    claude_session(home, out / "judges/judge", judge)
    assert pool.scan_judge(out, judge, "f" * 40) == []
    claude_session(home, out / "judges/judge", other)
    assert [hit["pattern"] for hit in pool.scan_judge(out, judge, "f" * 40)] == ["Forbidden model"]
    with pytest.raises(SystemExit, match="cannot be cleared"):
        pool.adjudicate_judge(out, judge, "cleared", "a probe")
