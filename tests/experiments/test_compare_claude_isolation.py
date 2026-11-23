"""Every Claude session of a unit, a candidate's or either Claude judge's, starts with the isolation switches
(`sandbox.CLAUDE_SETTINGS` as the sandbox's read-only managed settings, `sandbox.CLAUDE_ENV` in its environment),
and nothing a session does to its home changes what the next launch mounts: the real shims and sandbox with a
scripted CLI, never a provider call."""

import json
from pathlib import Path

import pytest

from experiments.compare import pool, sandbox
from tests.experiments.compare_harness_support import call, skip_without_sandbox, start, world  # noqa: F401

PROBE = ("for name in " + " ".join(sandbox.CLAUDE_ENV) + "; do printf '%s=%s\\n' $name \"$(printenv $name)\"; done; "
         f"printf 'settings=%s\\n' \"$(tr -d '\\n ' < {sandbox.CLAUDE_MANAGED})\"; "
         f"(echo '{{}}' > {sandbox.CLAUDE_MANAGED}) 2>/dev/null; echo written=$?")
REPLACE = ("mv $HOME/.claude $HOME/.claude-old 2>/dev/null; mkdir -p $HOME/.claude/; "
           "echo '{\"disableClaudeAiConnectors\": false}' > $HOME/.claude/settings.json; echo replaced=$?")


def seen(done):
    assert done.returncode == 0, done.stdout + done.stderr
    found = dict(line.split("=", 1) for line in done.stdout.splitlines() if "=" in line)
    return {**{name: found[name] for name in sandbox.CLAUDE_ENV}, "settings": json.loads(found["settings"]),
            "written": found["written"]}


EXPECTED = {**sandbox.CLAUDE_ENV, "settings": sandbox.CLAUDE_SETTINGS, "written": "1"}


def test_a_candidates_claude_session_starts_isolated(world):
    skip_without_sandbox()
    _, record = start(world, "direct_task")
    assert seen(call(world, record, PROBE)) == EXPECTED


def test_a_session_that_replaces_its_homes_settings_does_not_change_what_the_next_launch_mounts(world):
    skip_without_sandbox()
    _, record = start(world, "direct_task")
    done = call(world, record, REPLACE)
    assert (done.returncode, "replaced=0" in done.stdout) == (0, True), done.stdout + done.stderr
    assert seen(call(world, record, PROBE)) == EXPECTED


@pytest.mark.parametrize("judge", sandbox.CLAUDE_MODELS)
def test_each_claude_judges_session_starts_isolated(world, monkeypatch, judge):
    skip_without_sandbox()
    monkeypatch.setenv("COMPARE_CLAUDE_MODELS", judge)
    out = world.outside / "pool"
    for directory in ("records", "clones/a", "clones/b"):
        (out / directory).mkdir(parents=True)
    bindings = world.outside / "score-claude.json"
    bindings.write_text(json.dumps({"providers.judge": "claude_unrestricted_workspace_metered"}))
    mapping = {"judges": {judge: {"dir": "judge", "providers": str(bindings)}}, "batches": [["a", "b"]],
               "criterion_sha256": "frozen", "compare_base": "base", "runs": {}, "main": "/main",
               "runtime": "/runtime", "created_at": 0}
    (out / "records/mapping.json").write_text(json.dumps(mapping))
    pool.write_score_inputs(out, mapping, "intent", world.runtime)
    declaration = mapping["judges"][judge]["sandbox"]["declaration"]
    unit = json.loads(Path(declaration).read_text())
    record = {"records": unit["records"], "tree": unit["tree"], "compare_base": "base", "cwd": unit["tree"],
              "sandbox": {"declaration": declaration}}
    assert seen(call(world, record, PROBE, args=("--model", judge, "-p"))) == EXPECTED
