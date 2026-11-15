"""Run the long-horizon seed candidates end to end against a scripted `claude`. No provider is called.

    PYTHONPATH=$PWD python experiments/long_horizon_seed/demo.py /tmp/lhs-tmp/demo [program [scenario]]

Without a program it runs the four candidates; for each it first prints the compiled program's digest and site keys.

Each scenario is what the run must show (its result, its committed steps) and the list of answers the scripted
`claude` gives, one per call in order (the fake CLI of `tests/agent_session_shims.py`, plus a `kill` answer that
kills the orchestrator in the middle of the call; the run is then resumed). The stand-in task: `src/m1.txt` and
`src/m2.txt` must both hold `ok`; that is its visible check (`dev-check.json`, run by the kit's
`dev_check.py`). `run` returns what happened and `expected` what the scenario declares; the two must be equal, so a
wrong branch in a program, a step dispatched twice after a kill, a call the script did not foresee, a later step that
is not given the guide the setup reported, or a socket directory left behind fails here.
`tests/experiments/test_long_horizon_seed.py` runs every scenario.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from orchestrator.contracts.closed_program.program import ClosedProgram  # noqa: E402
from orchestrator.workflow.evaluated.machine import site_classes  # noqa: E402
from tests.agent_session_shims import FAKE_CLAUDE, closed_path, shim_requests  # noqa: E402

# The orchestrator's command line with observation panes that do nothing: a killed run skips its cleanup and
# would leave a tmux server behind (`roles` has Agent Sessions, which open one). The manager's socket directory
# goes under TMPDIR, which `orchestrator` sets to the world, instead of /tmp.
DRIVER = '''import itertools, os, sys
from orchestrator.providers import observation
from orchestrator.workflow.evaluated import runtime
from orchestrator.cli import main
class NoPanes:
    panes, alive = itertools.count(), True
    def start_server(self, socket_path, session_name): pass
    def open_pane(self, socket_path, session_name, display_path): return f"%{next(self.panes)}"
    def pane_alive(self, socket_path, target): return True
    def server_alive(self, socket_path, session_name): return self.alive
    def close_pane(self, socket_path, target): pass
    def close_server(self, socket_path): self.alive = False
observation._SOCKET_TEMP_ROOT = os.environ["TMPDIR"]
runtime.observation_backend = NoPanes
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''
ANCHOR = 'if mode == "timeout":'
assert ANCHOR in FAKE_CLAUDE, "the fake claude changed; move the kill hook"
SHIM = FAKE_CLAUDE.replace(ANCHOR, 'if step.get("kill"):\n    os.kill(os.getppid(), 9); sys.exit(1)\n' + ANCHOR, 1)
CHECK = ("import pathlib, sys; bad = [n for n in ('m1', 'm2') if not pathlib.Path('src', n + '.txt').is_file() "
         "or pathlib.Path('src', n + '.txt').read_text() != 'ok']; print('failing: ' + ' '.join(bad) if bad else 'passed'); "
         "sys.exit(1 if bad else 0)")
INPUTS = {"task": "make src/m1.txt and src/m2.txt hold ok", "intent": "both files hold ok"}
DEV_CHECK = HERE / "dev_check.py"  # the script of the `dev-check` command, copied into each workspace
COMMAND = [sys.executable, "-c", CHECK]
SLEEPS = [sys.executable, "-c", "import time; time.sleep(30)"]
# dev-check.json per scenario; None: the workspace has none
CHECKS = {"check-times-out": {"argv": SLEEPS, "timeout_sec": 1}, "check-not-configured": None}
SOCKET = re.compile(r"tmux -S (\S+)/tmux\.sock")  # the socket directory in an Agent Sessions run's agent-view line


def change(files):
    return {"result": {"summary": "s", "account": "a"}, "files": files}


def work(memory="", **files):
    """An implementer answer: writes src/<name>.txt and, as a later step would, rewrites the living documents."""
    docs = {"docs/log.md": "# Log\n" + memory, "docs/plan.md": "# Plan (progress noted)\n"} if memory else {}
    return change({**{f"src/{name}.txt": text for name, text in files.items()}, **docs})


def plan(*ids):
    milestones = [{"id": i, "goal": f"write src/{i.lower()}.txt", "targets": ["T" + i[1:]]} for i in ids]
    return {"result": {"doc": "docs/plan.md", "milestones": milestones}, "files": {"docs/plan.md": "# Plan\n" + " ".join(ids) + "\n"}}


DOCS = {"docs/index.md": "spec.md plan.md log.md notes/\n", "docs/log.md": "# Log\n", "docs/notes/layout.md": "# Layout\n"}
SETUP = {"guide": "AGENTS.md", "index": "docs/index.md", "log": "docs/log.md"}
GUIDES = {"result": SETUP, "files": {"AGENTS.md": "# Guide\nCheck: python dev_check.py\n", **DOCS}}
NO_GUIDE = {"result": SETUP, "files": DOCS}  # the setup step reports a guide it did not write
ELSEWHERE = {"result": {**SETUP, "guide": "GUIDE.md"}, "files": {"GUIDE.md": "# Guide\n", **DOCS}}  # and no AGENTS.md
SPEC = {"result": {"doc": "docs/spec.md", "targets": ["T1", "T2"]}, "files": {"docs/spec.md": "T1 m1 holds ok\nT2 m2 holds ok\n"}}
MET = {"result": {"variant": "MET", "evidence": ["read the files"]}}
NOT_MET = {"result": {"variant": "NOT_MET", "reasons": ["T2 does not hold: src/m2.txt"]}}
KILL = {"kill": True}
START = [GUIDES, SPEC, plan("M1", "M2")]
DESIGN = {"result": {"doc": "docs/design.md"}, "files": {"docs/design.md": "# Design\n"}}
REVISED = {"result": {"doc": "docs/design.md"}, "files": {"docs/design.md": "# Design (revised)\n"}}
BUILD = [plan("M1", "M2"), work(m1="ok", m2="ok"), MET]
DONE = {"summary": "accepted", "variant": "DONE"}
REASONS = NOT_MET["result"]["reasons"]  # a refusal's reasons
FAILING = f"{' '.join(COMMAND)} exited 1\nfailing: m2\n"  # a failed check's excerpt: why it failed, then its output
TIMED_OUT, UNCONFIGURED = f"{' '.join(SLEEPS)} timed out after 1s\n", "dev-check.json missing\n"
NO_SETUP = ({"error": "provider_result_invalid", "at": "ready"}, 0, [NO_GUIDE])


def blocked(reason, *notes):
    """An exhausted loop's result: its reason and the notes it ended on."""
    return {"notes": list(notes), "reason": reason, "variant": "BLOCKED"}


def elsewhere(scenario):
    """The scenario with a setup step that writes and reports its guide under another name."""
    result, steps, answers = scenario
    return result, steps, [ELSEWHERE, *answers[1:]]


# A refused acceptance, then rounds that fail the check until the round loop is exhausted: its notes keep both.
OPEN = [work(m1="ok", m2="ok"), NOT_MET, work(m2="bad"), work(), work()]

# scenario: (result, committed steps, answers)
FLAT = {
    "clean": (DONE, 6, START + [work(m1="ok", m2="ok"), MET]),
    "check-fails-once": (DONE, 8, START + [work(m1="ok", m2="bad"), work(m2="ok"), MET]),
    "review-rejects-once": (DONE, 9, START + [work(m1="ok", m2="ok"), NOT_MET, work(memory="round 2\n"), MET]),
    "kill-and-resume": (DONE, 8, START + [work("round 1\n", m1="ok", m2="bad"), KILL, work(m2="ok"), MET]),
    "refused-then-check-fails": (blocked("round limit reached", *REASONS, *3 * [FAILING]), 12, START + OPEN),
    "check-times-out": (blocked("round limit reached", *4 * [TIMED_OUT]), 11, START + 4 * [work()]),
    "check-not-configured": (blocked("round limit reached", *4 * [UNCONFIGURED]), 11, START + 4 * [work()]),
    "setup-incomplete": NO_SETUP,
}
FLAT["guide-under-another-name"] = elsewhere(FLAT["clean"])
DESIGNED = {  # guides, spec, design, at most two design reviews with a revision between; then plan, work, acceptance
    "clean": (DONE, 8, [GUIDES, SPEC, DESIGN, MET] + BUILD),
    "design-refused-once": (DONE, 10, [GUIDES, SPEC, DESIGN, NOT_MET, REVISED, MET] + BUILD),
    "design-never-accepted": (blocked("design round limit reached", *REASONS), 6, [GUIDES, SPEC, DESIGN, NOT_MET, REVISED, NOT_MET]),
    "acceptance-refused-once": (DONE, 11, [GUIDES, SPEC, DESIGN, MET] + BUILD[:2] + [NOT_MET, work(memory="round 2\n"), MET]),
    "kill-between-design-and-plan": (DONE, 8, [GUIDES, SPEC, DESIGN, MET, KILL] + BUILD),
    "refused-then-check-fails": (blocked("round limit reached", *REASONS, *3 * [FAILING]), 14,
                                 [GUIDES, SPEC, DESIGN, MET, plan("M1", "M2")] + OPEN),
    "setup-incomplete": NO_SETUP,
}
DESIGNED["guide-under-another-name"] = elsewhere(DESIGNED["clean"])
MILESTONES = {  # per milestone: work, review; then the acceptance
    "clean": (DONE, 11, START + [work(m1="ok"), MET, work(m2="ok"), MET, MET]),
    "check-fails-once": (DONE, 16, START + [work(m1="ok"), MET, work(m2="bad"), MET, plan("M3"), work(m2="ok"), MET, MET]),
    "review-rejects-once": (DONE, 14, START + [work(m1="ok"), MET, work(m2="bad"), NOT_MET, work(m2="ok"), MET, MET]),
    "kill-and-resume": (DONE, 11, START + [work("M1 done\n", m1="ok"), MET, KILL, work(m2="ok"), MET, MET]),
    "kill-in-a-second-attempt": (DONE, 14, START + [work(m1="ok"), MET, work(m2="bad"), NOT_MET, KILL, work(m2="ok"), MET, MET]),
    "setup-incomplete": NO_SETUP,
}
MILESTONES["guide-under-another-name"] = elsewhere(MILESTONES["clean"])


def planned(count):
    """A clean run of a plan of `count` milestones: at most eight of them are built, each accepted at once."""
    built = min(count, 8)
    answers = [GUIDES, SPEC, plan(*(f"M{i}" for i in range(1, count + 1))), work(m1="ok", m2="ok"), MET]
    return DONE, 5 + 3 * built, answers + (built - 1) * [work(), MET] + [MET]


def refused(*verdicts):
    """A plan of three milestones, each answered `MET` at once or `NOT_MET` in both attempts. Every milestone is
    still built and the round's check runs; then the run ends, without an acceptance."""
    answers = [GUIDES, SPEC, plan("M1", "M2", "M3")] + [a for v in verdicts for a in ([work(), v] if v is MET else 2 * [work(), v])]
    return blocked("milestone refused twice"), 4 + 3 * (len(answers) - 3) // 2, answers


MILESTONES["second-of-three-refused"] = refused(MET, NOT_MET, MET)
# `roles` takes these answers; opening a conversation is a step too: two for the run, two per milestone built
OPENED = {"check-fails-once": 8, "setup-incomplete": 2, "second-of-three-refused": 8}
ROLES = {name: (result, steps + OPENED.get(name, 6), answers) for name, (result, steps, answers) in MILESTONES.items()}
ROLES["plan-of-9"] = (DONE, planned(9)[1] + 18, planned(9)[2])  # the cut once with conversations
MILESTONES |= {f"plan-of-{count}": planned(count) for count in (3, 8, 9, 20, 50)}  # 9 and more: the calls of 8
MILESTONES |= {"last-of-three-refused": refused(MET, MET, NOT_MET), "no-milestone-met": refused(*3 * [NOT_MET]),
               "refused-then-check-fails": (blocked("acceptance round limit reached", *REASONS, FAILING), 13, [
                   GUIDES, SPEC, plan("M1"), *OPEN[:1], MET, NOT_MET, plan("M1"), OPEN[2], MET])}
PROGRAMS = {"staged": FLAT, "designed": DESIGNED, "milestones": MILESTONES, "roles": ROLES}
FLAGS = ("--provider-externs-file", str(HERE / "providers.json"), "--command-boundaries-file", str(HERE / "commands.json"))


def expected(program, scenario):
    """What `run` must return for the scenario: every answer used once, no step started twice, every later step
    given the reported guide, no socket directory left, and one seen at all exactly where there are conversations."""
    result, steps, answers = PROGRAMS[program][scenario]
    return {"result": result, "steps": steps, "calls": len(answers) - answers.count(KILL), "restarted": [],
            "settings": [["claude-haiku-5-5", "medium"]], "unguided": [], "stray": [], "sockets": program == "roles"}


def orchestrator(world, *argv, hash_seed="0"):
    """The orchestrator's command line in the world's workspace; `claude` resolves to the world's script only, and
    temporary files (an Agent Sessions run makes a socket directory) stay in the world."""
    env = {"PATH": closed_path(world / "bin"), "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONHASHSEED": hash_seed, "HOME": str(world), "TMPDIR": str(world), "CLAUDE_CONFIG_DIR": str(world / "claude"),
           "AGENT_SHIM_PLAN": json.dumps({"claude": json.loads((world / "plan.json").read_text())})}
    return subprocess.run([sys.executable, "-c", DRIVER, *argv], cwd=world / "repo", env=env, capture_output=True, text=True)


def new_world(base, name, answers=()):
    world = base / name
    shutil.rmtree(world, ignore_errors=True)
    (world / "repo").mkdir(parents=True)
    (world / "bin").mkdir()
    (world / "bin" / "claude").write_text(f"#!{sys.executable}\n" + SHIM)
    (world / "bin" / "claude").chmod(0o700)
    (world / "plan.json").write_text(json.dumps(list(answers)))
    return world


def build(base, program, hash_seed="0"):
    """The seed's closed program, compiled by the command line under the given hash seed."""
    world = new_world(base, f"{program}-build-{hash_seed}")
    proc = orchestrator(world, "compile", str(HERE / f"{program}.orc"), "--entry-workflow", f"{program}::run",
                        "--source-root", str(HERE), *FLAGS, hash_seed=hash_seed)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return ClosedProgram.from_artifact(Path(json.loads(proc.stdout)["artifact_paths"]["closed_program"]).read_text())


def events(proc, event):
    """The identities the run printed as started (`start`), committed (`commit`) or `failed`, in order."""
    lines = [line.split("  attempt")[0] for line in proc.stderr.splitlines() if line.startswith(event + " ")]
    return [line.split(None, 1)[1] for line in lines]


def failure(proc):
    """A failed run's diagnostic code and the step it failed at, from its last `failed  <identity> ... [code]` line."""
    line = [line for line in proc.stderr.splitlines() if line.startswith("failed ")][-1]
    return {"error": line.rsplit("[", 1)[1].rstrip("]"), "at": events(proc, "failed")[-1].split(" / ")[-1]}


def unguided(run_root, guide):
    """The steps after the setup whose prompt does not hold the guide path the setup reported (a value the program
    passes on, not the prompt's wording)."""
    rows = [json.loads(line) for line in (run_root / "memo.jsonl").read_text().splitlines()]
    prompts = {row["identity"].split(" / ")[-1]: run_root / Path(row["result_path"]).parent / "prompt.txt"
               for row in rows if row["record"] == "started"}
    return sorted(step for step, path in prompts.items() if step != "ready" and path.exists() and guide not in path.read_text())


def stray(world, proc):
    """The socket directories the process named that lie outside the world, or that it left behind although it ended
    by itself (a killed process cannot remove its own, which stays in the world)."""
    named = [Path(path) for path in SOCKET.findall(proc.stderr)]
    return [str(path) for path in named if world not in path.parents or (proc.returncode != -9 and path.exists())]


def run(base, program, scenario):
    """Run the scenario in a new world under `base`; returns what happened, in the shape of `expected`."""
    answers = PROGRAMS[program][scenario][2]
    world = new_world(base, f"{program}-{scenario}", answers)
    repo = world / "repo"
    shutil.copy(DEV_CHECK, repo / "dev_check.py")
    config = CHECKS.get(scenario, {"argv": COMMAND, "timeout_sec": 30})
    if config is not None:
        (repo / "dev-check.json").write_text(json.dumps(config))
    (world / "inputs.json").write_text(json.dumps(INPUTS))
    proc = orchestrator(world, "run", str(HERE / f"{program}.orc"), "--entry-workflow", f"{program}::run",
                        "--source-root", str(HERE), *FLAGS, "--input-file", str(world / "inputs.json"))
    print(f"\n== {program} / {scenario}: run exit {proc.returncode}")
    print("\n".join(line for line in proc.stderr.splitlines() if line.startswith(("start ", "commit "))))
    committed, restarted, left, sockets = events(proc, "commit"), [], stray(world, proc), bool(SOCKET.search(proc.stderr))
    (run_root,) = (repo / ".orchestrate" / "runs").iterdir()
    if KILL in answers:
        assert proc.returncode == -9, proc.stdout + proc.stderr
        proc = orchestrator(world, "resume", run_root.name)
        left += stray(world, proc)
        print(f"-- resume exit {proc.returncode}; steps started again:")
        print("\n".join(line for line in proc.stderr.splitlines() if line.startswith(("start ", "commit "))))
        restarted = sorted(set(committed) & set(events(proc, "start")))
        committed += events(proc, "commit")
    requests = shim_requests(repo)
    settings = {(r["argv"][r["argv"].index("--model") + 1], r["argv"][r["argv"].index("--effort") + 1]) for r in requests}
    result = json.loads(proc.stdout.splitlines()[-1]) if proc.returncode == 0 else failure(proc)
    print(f"-- result {json.dumps(result)}; {len(committed)} steps committed, {len(requests)} provider calls "
          f"in {len({r['session'] for r in requests})} conversations")
    return {"result": result, "steps": len(committed), "calls": len(requests), "restarted": restarted,
            "settings": sorted(map(list, settings)), "unguided": unguided(run_root, answers[0]["result"]["guide"]),
            "stray": sorted(set(left)), "sockets": sockets}


if __name__ == "__main__":
    base, wanted = Path(sys.argv[1]), sys.argv[2:]
    for program in wanted[:1] or PROGRAMS:
        closed = build(base, program)
        print(f"\n== {program}: {len((HERE / f'{program}.orc').read_text().splitlines())} lines, {closed.digest}, "
              f"inputs {[name for name, _ in closed.tree['params']]}")
        print("\n".join(f"   {kind:11} {key}" for key, kind in site_classes(closed).items()))
        for scenario in wanted[1:2] or PROGRAMS[program]:
            observed = run(base, program, scenario)
            assert observed == expected(program, scenario), (observed, expected(program, scenario))
