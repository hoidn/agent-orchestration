"""Run the long-horizon seed candidates end to end against a scripted `claude`. No provider is called.

    PYTHONPATH=$PWD python experiments/long_horizon_seed/demo.py /tmp/lhs-tmp/demo [program [scenario]]

Without a program it runs the four candidates. The two programs under `variants/` run when named;
`roles_whole_run` needs a tree with change I1, named in `ORC_ROOT` (its orchestrator and tests are used).

Each scenario is the list of answers the scripted `claude` gives, one per call in order (the fake CLI of
`tests/agent_session_shims.py`, plus a `kill` answer that kills the orchestrator in the middle of the call).
The stand-in task: `src/m1.txt` and `src/m2.txt` must both hold `ok`; that is its visible check
(`dev-check.json`, run by the seed catalog's `dev_check.py`). Every scenario must end in DONE with exactly
the scripted number of calls, so a wrong branch in a program fails here. After a kill, `resume` must start no
step that the killed run had committed.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(os.environ.get("ORC_ROOT") or Path(__file__).resolve().parents[2]).resolve()
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from tests.agent_session_shims import FAKE_CLAUDE, closed_path  # noqa: E402
from tests.test_workflow_evaluated_agent_consumer_smoke import DRIVER  # noqa: E402  (no tmux server is started)

ANCHOR = 'if mode == "timeout":'
assert ANCHOR in FAKE_CLAUDE, "the fake claude changed; move the kill hook"
SHIM = FAKE_CLAUDE.replace(ANCHOR, 'if step.get("kill"):\n    os.kill(os.getppid(), 9); sys.exit(1)\n' + ANCHOR, 1)
CHECK = ("import pathlib, sys; bad = [n for n in ('m1', 'm2') if not pathlib.Path('src', n + '.txt').is_file() "
         "or pathlib.Path('src', n + '.txt').read_text() != 'ok']; print('failing: ' + ' '.join(bad) if bad else 'passed'); "
         "sys.exit(1 if bad else 0)")


def change(files):
    return {"result": {"summary": "s", "account": "a"}, "files": files}


def work(memory="", **files):
    """An implementer answer: writes src/<name>.txt and, as a later step would, rewrites the living documents."""
    docs = {"docs/log.md": "# Log\n" + memory, "docs/plan.md": "# Plan (progress noted)\n"} if memory else {}
    return change({**{f"src/{name}.txt": text for name, text in files.items()}, **docs})


def plan(*ids):
    milestones = [{"id": i, "goal": f"write src/{i.lower()}.txt", "targets": ["T" + i[1:]]} for i in ids]
    return {"result": {"doc": "docs/plan.md", "milestones": milestones}, "files": {"docs/plan.md": "# Plan\n" + " ".join(ids) + "\n"}}


GUIDES = change({"AGENTS.md": "# Guide\nCheck: python dev_check.py\n", "docs/index.md": "spec.md plan.md log.md notes/\n",
                 "docs/log.md": "# Log\n", "docs/notes/layout.md": "# Layout\n"})
SPEC = {"result": {"doc": "docs/spec.md", "targets": ["T1", "T2"]}, "files": {"docs/spec.md": "T1 m1 holds ok\nT2 m2 holds ok\n"}}
MET = {"result": {"variant": "MET", "evidence": ["read the files"]}}
NOT_MET = {"result": {"variant": "NOT_MET", "reasons": ["T2 does not hold: src/m2.txt"]}}
KILL = {"kill": True}
START = [GUIDES, SPEC, plan("M1", "M2")]
DESIGN = {"result": {"doc": "docs/design.md"}, "files": {"docs/design.md": "# Design\n"}}
REVISED = {"result": {"doc": "docs/design.md"}, "files": {"docs/design.md": "# Design (revised)\n"}}
BUILD = [plan("M1", "M2"), work(m1="ok", m2="ok"), MET]

FLAT = {
    "clean": START + [work(m1="ok", m2="ok"), MET],
    "check-fails-once": START + [work(m1="ok", m2="bad"), work(m2="ok"), MET],
    "review-rejects-once": START + [work(m1="ok", m2="ok"), NOT_MET, work(memory="round 2\n"), MET],
    "kill-and-resume": START + [work("round 1\n", m1="ok", m2="bad"), KILL, work(m2="ok"), MET],
}
MILESTONES = {  # per milestone: work, review; then the acceptance
    "clean": START + [work(m1="ok"), MET, work(m2="ok"), MET, MET],
    "check-fails-once": START + [work(m1="ok"), MET, work(m2="bad"), MET, plan("M3"), work(m2="ok"), MET, MET],
    "review-rejects-once": START + [work(m1="ok"), MET, work(m2="bad"), NOT_MET, work(m2="ok"), MET, MET],
    "kill-and-resume": START + [work("M1 done\n", m1="ok"), MET, KILL, work(m2="ok"), MET, MET],
    "kill-in-a-second-attempt": START + [work(m1="ok"), MET, work(m2="bad"), NOT_MET, KILL, work(m2="ok"), MET, MET],
}
DESIGNED = {  # guides, spec, design, design review; then plan, work, acceptance
    "clean": [GUIDES, SPEC, DESIGN, MET] + BUILD,
    "design-refused-once": [GUIDES, SPEC, DESIGN, NOT_MET, REVISED] + BUILD,
    "acceptance-refused-once": [GUIDES, SPEC, DESIGN, MET] + BUILD[:2] + [NOT_MET, work(memory="round 2\n"), MET],
    "kill-between-design-and-plan": [GUIDES, SPEC, DESIGN, MET, KILL] + BUILD,
}
PROGRAMS = {"staged": FLAT, "milestones": MILESTONES, "roles": MILESTONES, "designed": DESIGNED}
VARIANTS = {"roles_whole_run": MILESTONES, "roles_whole_run_cursor": MILESTONES}


def orchestrator(world, *argv):
    env = {"PATH": closed_path(world / "bin"), "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
           "HOME": str(world), "CLAUDE_CONFIG_DIR": str(world / "claude"),
           "AGENT_SHIM_PLAN": (world / "plan.json").read_text()}
    return subprocess.run([sys.executable, "-c", DRIVER, *argv], cwd=world / "repo", env=env, capture_output=True, text=True)


def steps(proc):
    return [line.split("  attempt")[0] for line in proc.stderr.splitlines() if line.startswith(("start ", "commit "))]


def sites(proc, event):
    return [line.split(None, 1)[1] for line in steps(proc) if line.startswith(event)]


def run(base, program, scenario):
    world, answers = base / f"{program}-{scenario}", (PROGRAMS | VARIANTS)[program][scenario]
    source = HERE / ("variants" if program in VARIANTS else "") / f"{program}.orc"
    shutil.rmtree(world, ignore_errors=True)
    (world / "repo").mkdir(parents=True)
    (world / "bin").mkdir()
    (world / "bin" / "claude").write_text(f"#!{sys.executable}\n" + SHIM)
    (world / "bin" / "claude").chmod(0o700)
    (world / "plan.json").write_text(json.dumps({"claude": answers}))
    repo = world / "repo"
    shutil.copy(ROOT / "experiments" / "orc_structural_search" / "seeds" / "dev_check.py", repo)
    (repo / "dev-check.json").write_text(json.dumps({"argv": [sys.executable, "-c", CHECK], "timeout_sec": 30}))
    (world / "inputs.json").write_text(json.dumps({"task": "make src/m1.txt and src/m2.txt hold ok", "intent": "both files hold ok",
                                                  "repo": str(repo), "effort": "medium",
                                                  **dict.fromkeys(("planner", "coder", "reviewer"), "claude-haiku-5-5")}))
    proc = orchestrator(world, "run", str(source), "--entry-workflow", f"{program}::run",
                        "--source-root", str(source.parent), "--source-root", str(HERE),
                        "--provider-externs-file", str(HERE / "providers.json"),
                        "--command-boundaries-file", str(HERE / "commands.json"), "--input-file", str(world / "inputs.json"))
    print(f"\n== {program} / {scenario}: run exit {proc.returncode}")
    print("\n".join(steps(proc)))
    committed = sites(proc, "commit")
    if KILL in answers:
        assert proc.returncode == -9, proc.stdout + proc.stderr
        (run_root,) = (repo / ".orchestrate" / "runs").iterdir()
        proc = orchestrator(world, "resume", run_root.name)
        print(f"-- resume exit {proc.returncode}; steps started again:")
        print("\n".join(steps(proc)))
        again = set(committed) & set(sites(proc, "start"))
        assert not again, f"dispatched twice: {sorted(again)}"
        committed += sites(proc, "commit")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    requests = [json.loads(line) for line in (repo / "requests.jsonl").read_text().splitlines()]
    sessions = len({request["session"] for request in requests})
    result = json.loads(proc.stdout.splitlines()[-1])
    print(f"-- result {json.dumps(result)}; {len(committed)} steps committed, {len(requests)} provider calls in {sessions} conversations")
    assert result["variant"] == "DONE" and len(requests) == len(answers) - answers.count(KILL), (result, len(requests))


if __name__ == "__main__":
    base, wanted = Path(sys.argv[1]), sys.argv[2:]
    for program in wanted[:1] or PROGRAMS:
        for scenario in wanted[1:2] or (PROGRAMS | VARIANTS)[program]:
            run(base, program, scenario)
