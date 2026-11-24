"""The wrapper around the reviewed launcher (`experiments/mle_bench_tasks/screen.py`; family plan M4, M5, Task 5).

Everything runs on a copy of both kits in a temporary git repository: the fixture competition, packaged by wrap.py
under two names per class, the ladder's stand-in harness, stand-in podman and stub API
(`test_long_horizon_launcher.py`), a stand-in nvidia-smi, and the passthrough in its rehearsal mode. No token, no
real CLI, no container, no network. Live mode is exercised without the spend authorization: where a launcher refusal
needs it to be reached, the test calls the wrapped module's own check (the per-start `config_refusal`), as the
ladder's own tests do. The ladder's own launcher tests cannot be pointed at the wrapped module unedited: they run
`ladder.py` by its path in a copy of the ladder's kit, so the cases below are the ones that differ through the
wrapper.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from argparse import Namespace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
KIT = REPO / "experiments" / "mle_bench_tasks"
LADDER_KIT = REPO / "experiments" / "long_horizon_tasks"
TINY = REPO / "tests" / "experiments" / "fixtures" / "mle_bench" / "tiny-tabular"
WAIT = 120  # seconds; the machine is shared and heavily loaded
NAMES = {"cpu": ("tiny-a", "tiny-b"), "gpu": ("tiny-g", "tiny-h")}
PLAN = "docs/plans/2026-11-15-mle-bench-family-plan.md"
GIT_ID = ("-c", "user.name=t", "-c", "user.email=t@t")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LT = _load("mle_screen_launcher_tests", REPO / "tests" / "experiments" / "test_long_horizon_launcher.py")
wrap = _load("mle_screen_wrap", KIT / "wrap.py")


def ledger(tranche):
    return f"docs/plans/2026-11-15-mle-bench-ledger-{tranche}.md"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha_of(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def short():
    """A mode-700 directory with a short path (AF_UNIX paths stop at 108 bytes), removed at the end."""
    path = Path(tempfile.mkdtemp(prefix="mls", dir="/tmp"))
    yield path
    for root, dirs, _ in os.walk(path):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o700)
    shutil.rmtree(path)


NVIDIA = r'''
"""The stand-in nvidia-smi (test_mle_bench_screen.py): prints standin/gpu.txt; exits 9 when standin/gpu_fails exists."""
import sys
from pathlib import Path
STATE = Path(__file__).resolve().parents[2] / "standin"
if (STATE / "gpu_fails").exists():
    sys.exit(9)
print((STATE / "gpu.txt").read_text() if (STATE / "gpu.txt").exists() else "", end="")
'''


class Kit:
    """A copy of both kits in a temporary git repository (branch main), whose tranches hold the fixture under the
    names `names` and every field filled (or, with `filled=False`, nothing filled: tasks.json then holds the
    generator's placeholders); the stand-in harness under HOME/lh-cache, this line's cache HOME/mle-cache with its
    harness environment linked to it, the packages wrap.py built and the CPU class's host-side files."""

    def __init__(self, short, names=None, filled=True, edit=None):
        self.short, self.repo, self.home = short, short / "repo", short / "home"
        self.lh, self.cache, self.reh = self.home / "lh-cache", self.home / "mle-cache", short / "reh"
        self.kit, self.names = self.repo / "experiments" / "mle_bench_tasks", names or NAMES
        self._copy()
        self._harness()
        self.records = self._packages()
        self._generate(filled, edit)
        self.host_side("cpu")
        _git(self.repo, "init", "-q", "-b", "main")
        self.commit("kit")
        self.reh.mkdir(mode=0o700)
        (self.reh / "stand_ins.json").write_text(json.dumps({"schedule.order.seed": "s", "readout.fall_bound.seed": 1}))
        (self.reh / "host").mkdir()
        (self.reh / "host" / "loadavg").write_text("1.0 1.0 1.0 1/1 1\n")
        (self.reh / "host" / "free_gb").write_text("100")
        self._screen = None

    # ---- construction --------------------------------------------------------------------------------------

    def _copy(self):
        ignore = shutil.ignore_patterns("__pycache__", "results")
        shutil.copytree(LADDER_KIT, self.repo / "experiments" / "long_horizon_tasks", ignore=ignore)
        shutil.copytree(KIT, self.kit, ignore=ignore, symlinks=True)
        (self.repo / "orchestrator").symlink_to(REPO / "orchestrator")
        (self.repo / "experiments" / "thread_m").mkdir()
        (self.repo / "experiments" / "thread_m" / "no_provider").symlink_to(REPO / "experiments/thread_m/no_provider")
        (self.repo / "tests" / "experiments").mkdir(parents=True)
        shutil.copy(REPO / "tests/experiments/test_long_horizon_ladder.py", self.repo / "tests/experiments")
        (self.repo / ".gitignore").write_text("__pycache__/\n")
        (self.repo / "docs" / "plans").mkdir(parents=True)
        for path in [PLAN] + [ledger(t) for t in ("screen-cpu", "screen-cpu-2", "screen-gpu", "screen-gpu-2")]:
            (self.repo / path).write_text(f"# {path} (stand-in)\n\n| Date | Entry | Note |\n| --- | --- | --- |\n")
        if not (self.kit / "withhold_check.py").exists():  # Task 3's check, merged separately
            (self.kit / "withhold_check.py").write_text("# a stand-in for Task 3's withholding check\n")

    def _harness(self):
        """The ladder's stand-in harness venv `python`, stand-in podman and a stand-in nvidia-smi under
        HOME/lh-cache/hvenv/bin, linked from this line's cache as M4 lays it out; the ladder's host-side files
        under HOME/lh-cache/logs."""
        bin_ = self.lh / "hvenv" / "bin"
        bin_.mkdir(parents=True)
        for name, text in (("python", f"FIXTURES = {str(LADDER_KIT / 'fixtures')!r}\n{LT.STANDIN}"),
                           ("podman", LT.PODMAN), ("nvidia-smi", NVIDIA)):
            (bin_ / name).write_text(f"#!{sys.executable} -I\n{text}")
            (bin_ / name).chmod(0o700)
        for folder in ("containers", "networks"):
            (self.lh / "standin" / "podman" / folder).mkdir(parents=True)
        (self.lh / "standin" / "versions.json").write_text(json.dumps({"harbor": "0.25.0", "podman-compose": "1.6.0"}))
        side = json.loads((LADDER_KIT / "ladder.json").read_text())["harness"]["host_side"]
        (self.lh / "logs").mkdir()
        (self.lh / "logs" / "containers-override.conf").write_text(side["containers_override"]["content"])
        (self.lh / "logs" / "limits-compose.yaml").write_text(side["limits_compose"]["content"])
        for folder in ("logs", "packages"):
            (self.cache / folder).mkdir(parents=True)
        (self.cache / "recordings").mkdir(mode=0o700)  # Task 7's setup makes it (S1): the round read scans it
        (self.cache / "hvenv").symlink_to(self.lh / "hvenv")

    def _packages(self):
        """Each name's package, built by wrap.py from the fixture with images named by digest, in the cache."""
        records = {}
        for cls, names in self.names.items():
            for name in names:
                images = {w: f"localhost/mle-bench/{name}-{w}@sha256:" + _sha_of(f"{name}{w}")
                          for w in ("agent", "verifier")}
                out = self.short / "wrapped" / name
                made = wrap.packages(TINY / "competition", TINY.parent, out, name=name, cls=cls,
                                     agent_image=images["agent"], verifier_image=images["verifier"])
                shutil.copytree(out / "attempt", self.cache / "packages" / name / "x")
                records[name] = {"digest_4_1_0": made["digests"]["attempt"], "environment_image": images["agent"],
                                 "verifier_image": images["verifier"]}
        shutil.rmtree(self.short / "wrapped")
        return records

    def result(self, name):
        """A passing withholding result for `name`'s agent image, in Task 3's form."""
        return {"image": self.records[name]["environment_image"], "competition": "tiny-tabular", "verdict": "pass",
                "files_checked": 5, "inputs": {"private": "sha256:" + "1" * 64},
                "check_sha256": "sha256:" + _sha(self.kit / "withhold_check.py"), "exempted": []}

    def _values(self, cls):
        names = self.names[cls]
        values = {"tasks.qualified": list(names), "tasks.load_sensitive": [],
                  "tasks.withholding": {n: self.result(n) for n in names},
                  "tasks.packages": {n: self.records[n] for n in names},
                  "readout.contamination_scan.terms": ["stand-in-term"],
                  "readout.contamination_scan.canary_exempt_tasks": [], "schedule.order.seed": f"seed {cls}",
                  "readout.fall_bound.seed": 1}
        if cls == "gpu":
            values["tasks.weights"] = {"file": "experiments/mle_bench_tasks/weights.json", "sha256": "0" * 64}
        return values

    def _fill_ladder(self):
        """The ladder's own two pending fields, filled in the copy's ladder.json (the live probe fills them)."""
        path = self.repo / "experiments" / "long_horizon_tasks" / "ladder.json"
        doc = json.loads(path.read_text())
        values = {"usage_limits.vendor_headers_confirmed": {"stand-in": True},
                  "allowance_guard.utilisation_header": "none"}
        for entry in [e for e in doc["pending"] if e["field"] in values]:
            LT.ladder._set(doc, entry["field"], values[entry["field"]])
            doc["filled"].append({**entry, "source": "a test"})
        doc["pending"] = [e for e in doc["pending"] if e["field"] not in values]
        path.write_text(json.dumps(doc, indent=1))

    def _generate(self, filled, edit):
        """family.json and criterion_fields.json of the copy rewritten for the fixture, then the generator run."""
        family, fields = (json.loads((self.kit / f).read_text()) for f in ("family.json", "criterion_fields.json"))
        family["candidates"] = [{"order": i + 1, "name": n, "slug": "tiny-tabular", "class": c,
                                 "feasibility_rank": i + 1, "size_gb": {}}
                                for i, (c, n) in enumerate((c, n) for c, ns in self.names.items() for n in ns)]
        for cls, names in self.names.items():
            given = fields["classes"][cls]["set"]
            given.update({"schedule.smoke.task": names[0], "schedule.pilot.task": names[-1]})
            given["host.disk_plan"]["launch_room_gb"] = {"/": 0, "/home": 0}
            if filled:
                fields["filled"][fields["classes"][cls]["tranche"]] = {
                    f: {"value": v, "source": "a test"} for f, v in self._values(cls).items()}
        if filled:
            self._fill_ladder()
        if edit:
            edit(fields)
        for name, doc in (("family.json", family), ("criterion_fields.json", fields)):
            (self.kit / name).write_text(json.dumps(doc, indent=1) + "\n")
        subprocess.run([sys.executable, "-I", str(self.kit / "make_criterion.py"), "write"], cwd=self.repo,
                       capture_output=True, text=True, check=True, timeout=WAIT)

    def host_side(self, cls):
        """The class's two host-side files in this line's cache (a hand-over writes them)."""
        side = self.criterion(f"screen-{cls}")["harness"]["host_side"]
        (self.cache / "logs" / "containers-override.conf").write_text(side["containers_override"]["content"])
        (self.cache / "logs" / "limits-compose.yaml").write_text(side["limits_compose"]["content"])

    # ---- use -------------------------------------------------------------------------------------------------

    @property
    def screen(self):
        """The copy's screen.py, loaded in this process."""
        if self._screen is None:
            self._screen = _load(f"mle_screen_copy_{id(self)}", self.kit / "screen.py")
        return self._screen

    def criterion(self, tranche):
        return json.loads((self.kit / "tranches" / tranche / "ladder.json").read_text())

    def tasks(self, tranche):
        return json.loads((self.kit / "tranches" / tranche / "tasks.json").read_text())

    def write_tasks(self, tranche, doc):
        (self.kit / "tranches" / tranche / "tasks.json").write_text(json.dumps(doc, indent=1) + "\n")

    def commit(self, message):
        _git(self.repo, "add", "-A")
        _git(self.repo, *GIT_ID, "commit", "-q", "-m", message)

    def remanifest(self, tranche, message="edit"):
        """The tranche's manifest rewritten (unfrozen) after an edit, and both committed."""
        assert self.run(tranche, "manifest", "write")[0] == 0
        self.commit(message)

    def ledger_row(self, path, what, cell):
        """A row committed to a ledger file on main; the checkout stays where it is."""
        head = _git(self.repo, "rev-parse", "HEAD")
        _git(self.repo, "checkout", "-q", "main")
        with open(self.repo / path, "a") as fh:
            fh.write(f"| 2026-11-20 | {what} | {cell} |\n")
        _git(self.repo, *GIT_ID, "commit", "-q", "-am", what)
        _git(self.repo, "checkout", "-q", "--detach", head)

    def label(self, tranche):
        return _sha(self.kit / "manifests" / f"{tranche}.json")

    def freeze(self, tranche="screen-cpu"):
        """The tranche frozen through the wrapper, committed, labelled in its own ledger, and checked out detached."""
        code, out, err = self.run(tranche, "manifest", "write", "--freeze")
        assert code == 0, err
        self.commit("freeze")
        commit = _git(self.repo, "rev-parse", "HEAD")
        self.ledger_row(ledger(tranche), "Configuration label", f"{self.label(tranche)} {commit} first label")
        _git(self.repo, "checkout", "-q", "--detach", commit)
        return commit

    def env(self, live=False, **extra):
        return {"HOME": str(self.home), **({} if live else {"LH_REHEARSAL": str(self.reh)}), **extra}

    def run(self, *argv, env=None, timeout=WAIT):
        done = subprocess.run([sys.executable, "-I", str(self.kit / "screen.py"), *argv], cwd=self.repo,
                              env=self.env() if env is None else env, capture_output=True, text=True, timeout=timeout)
        return done.returncode, done.stdout, done.stderr

    def allowance(self, root):
        now = time.time()
        LT._allowance(root, {"kind": "inputs", "at": now - 120, "f_week": 10, "f_five": 10,
                             "hours": ["daily 00:00-24:00"], "closing_margin_h": 0},
                      {"kind": "reading", "at": now - 60, "weekly": 0, "five": 0, "weekly_reset": now + LT.DAY,
                       "five_reset": now + 3600},
                      {"kind": "figures", "at": now - 30, "weekly_usd_per_point": 50.0, "five_usd_per_point": 50.0,
                       "reservation_raise": 1.0})


@pytest.fixture
def kit(short):
    return Kit(short)


def _wrapper_refused(result):
    """(exit code, the wrapper's own reason or None): the wrapper prints `screen.py: refused: <reason>`. A reason of
    the wrapper's comes with no line of the launcher's: the wrapper refused before the launcher was entered."""
    code, _, err = result
    found = [line.split("screen.py: refused: ", 1)[1] for line in err.splitlines() if "screen.py: refused: " in line]
    assert not found or "ladder.py:" not in err, err
    return code, found[0] if found else None


def _launcher_refused(result):
    code, _, err = result
    found = [line.split("ladder.py: refused: ", 1)[1] for line in err.splitlines() if "ladder.py: refused: " in line]
    return code, found[0] if found else None


# ---- the replaced names (Task 5, first item) -----------------------------------------------------------------

EXPECTED = {"screen-cpu": {"ceiling": 50.0, "starts": 8, "smoke": "tiny-a"},
            "screen-gpu": {"ceiling": 150.0, "starts": 10, "smoke": "tiny-g"}}


@pytest.mark.parametrize("tranche", sorted(EXPECTED))
def test_the_wrapped_launcher_reads_this_tranche_s_criterion_ledger_state_root_label_and_packages(kit, tranche):
    """Each value differs between the ladder and the tranche, and between the two tranches."""
    lad = kit.screen.launcher(tranche)
    marker = f"a row only in {tranche}'s ledger"
    kit.ledger_row(ledger(tranche), "Note", marker)
    live = lad.Ctx({**kit.env(live=True), "LH": str(kit.cache)})
    ladder = lad.criterion(lad.Ctx({**kit.env(), "LH": str(kit.cache)}))
    want = EXPECTED[tranche]
    assert (ladder["ceiling"]["total_usd"], ladder["ceiling"]["starts"], lad.smoke_task(ladder), lad.EFFORTS,
            marker in lad.ledger_text(live), live.root, lad.this_label(), lad.package(live, "tiny-a"),
            lad.KIT / "ladder.json") == (
        want["ceiling"], want["starts"], want["smoke"], ("medium",), True,
        kit.home / ".local" / "state" / "mle-bench" / tranche, kit.label(tranche),
        kit.cache / "packages" / "tiny-a" / "x", kit.kit / "tranches" / tranche / "ladder.json")


def _runs_at_load(stmt):
    """The parts of a module-level statement that run when the module is loaded. The `if __name__ == "__main__"`
    block does not run in a private load."""
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return stmt.decorator_list + stmt.args.defaults + [d for d in stmt.args.kw_defaults if d]
    if isinstance(stmt, ast.If) and ast.unparse(stmt.test) == "__name__ == '__main__'":
        return []
    if isinstance(stmt, ast.ClassDef):
        return stmt.decorator_list + stmt.bases + [s for s in stmt.body if not isinstance(s, ast.FunctionDef)]
    return [stmt]


def _calls_at_load(path, names):
    """(statement, name) for every use of `names` that runs when the module at `path` is loaded: in a module-level
    statement, a decorator, a default, a base class, and in the body of every module function such a statement
    calls (transitively)."""
    tree = ast.parse(path.read_text())
    bodies = {s.name: s for s in tree.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def used(node, seen):
        found = {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        called = {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        for name in called & bodies.keys() - seen:
            found |= used(bodies[name], seen | {name})
        return found

    return [(ast.unparse(stmt).splitlines()[0], name) for stmt in tree.body for part in _runs_at_load(stmt)
            for name in sorted(used(part, set()) & names)]


def test_no_use_of_a_replaced_name_is_bound_when_either_module_is_loaded(kit):
    """The only load-time uses are these, each harmless: ROOT is the repository root whichever kit is named (the
    wrapper keeps it), and the three modules the launcher loads at import are the reviewed kit's own, bound by hash
    in the tranche's manifest; manifest.py's MANIFEST is replaced after the load."""
    ladder_uses = _calls_at_load(LADDER_KIT / "ladder.py", {"KIT", "PLAN", "EFFORTS", "PACKAGES", "Ctx", "manifest"})
    manifest_uses = _calls_at_load(LADDER_KIT / "manifest.py", {"KIT", "MANIFEST", "NOT_COVERED", "EXTERNAL"})
    lad = kit.screen.launcher("screen-cpu")
    reviewed = kit.repo / "experiments" / "long_horizon_tasks"
    assert (ladder_uses, manifest_uses, lad.ROOT, lad.manifest.ROOT, Path(lad.slot_record.__file__).parent,
            Path(lad.price_check.__file__).parent) == (
        [("ROOT = KIT.parents[1]", "KIT"), ("manifest = _kit('manifest')", "KIT"),
         ("slot_record = _kit('slot_record')", "KIT"), ("price_check = _kit('price_check')", "KIT")],
        [("ROOT = KIT.parents[1]", "KIT"), ("MANIFEST = KIT / 'manifest.json'", "KIT")],
        kit.repo, kit.repo, reviewed, reviewed)


class Rig:
    """A kit in rehearsal mode with its passthrough (rehearsal switch, in front of stub_api.py), allowance inputs,
    a reading and the pilot's figures; `launch()` runs `screen.py screen-cpu launch`."""

    def __init__(self, kit, plan=(), scenario="normal", stub_args=()):
        self.kit, self.root = kit, kit.reh / "state"
        shutil.move(kit.repo, kit.short / "main")  # D4: the checkout is a git worktree of the main repository
        _git(kit.short / "main", "worktree", "add", "-q", "--detach", str(kit.repo))
        (kit.home / ".claude" / "projects").mkdir(parents=True)  # D4's file set: the agents' transcripts
        LT.ladder.ensure_state(self.root)
        (kit.lh / "standin" / "plan.json").write_text(json.dumps(list(plan)))
        kit.allowance(self.root)
        self.procs = []
        stub = kit.short / "stub.sock"
        self._start([sys.executable, "-I", str(LADDER_KIT / "stub_api.py"), "--unix", str(stub), "--model",
                     LT.ladder.MODEL, "--scenario", scenario, "--log", str(kit.short / "stub.jsonl"), *stub_args],
                    kit.short / "stub.out")
        self._start([sys.executable, "-I", str(LADDER_KIT / "passthrough.py"), "--socket",
                     str(self.root / "relay" / "passthrough.sock"), "--state", str(self.root / "passthrough"),
                     "--slots", str(self.root / "passthrough" / "slots.json"), "--rehearsal", str(stub),
                     "--canary-out", str(kit.short / "canary")], self.root / "passthrough" / "output.log")

    def _start(self, argv, out):
        fh = open(out, "ab")
        proc = subprocess.Popen(argv, stdout=fh, stderr=fh)
        self.procs.append(proc)
        deadline = time.monotonic() + WAIT
        while b"listening" not in out.read_bytes() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        assert b"listening" in out.read_bytes(), out.read_text()

    def launch(self, timeout=WAIT * 3):
        return self.kit.run("screen-cpu", "launch", timeout=timeout)

    def ledger(self, what, cell):
        """A row of the rehearsal's ledger (LH_REHEARSAL/ledger.md), which a rehearsal reads in place of main's."""
        with open(self.kit.reh / "ledger.md", "a") as fh:
            fh.write(f"| 2026-11-20 | {what} | {cell} |\n")

    def attempts(self):
        return LT.ladder.attempts(self.root)

    def events(self):
        return LT.ladder._jsonl(self.root / "passthrough" / "tranche.jsonl")

    def close(self):
        for proc in self.procs:
            proc.terminate()
            proc.wait(timeout=WAIT)


@pytest.fixture
def rig(kit, short):
    made = []

    def make(**kwargs):
        made.append(Rig(kit, **kwargs))
        return made[-1]
    yield make
    for one in made:
        one.close()
    for line in subprocess.run(["pgrep", "-f", str(short)], capture_output=True, text=True).stdout.split():
        os.kill(int(line), 9)  # a stand-in "CLI" that outlived its test


def test_a_launch_through_the_wrapper_runs_the_smoke_on_this_line_s_files_and_never_reads_the_ladder_s_cache_logs(rig):
    """The rehearsal's smoke: this tranche's competition, effort and cap; this line's limits file, override and
    package; the ladder's ~/lh-cache/logs unreadable throughout."""
    r = rig(plan=[{}])
    kit = r.kit
    (kit.lh / "logs").chmod(0)
    try:
        code, out, err = r.launch()
    finally:
        (kit.lh / "logs").chmod(0o700)
    (call,) = LT._calls(kit.lh)
    argv, env = call["argv"], call["env"]
    (attempt,) = r.attempts()
    composes = [argv[i + 1] for i, a in enumerate(argv) if a == "--extra-docker-compose"]
    assert (code, "waiting for the smoke read" in out, argv[argv.index("--effort") + 1],
            "max_budget_usd=8.0" in argv, composes, env["CONTAINERS_CONF_OVERRIDE"],
            (attempt["task"], attempt["kind"], attempt["settled"]["class"])) == (
        0, True, "medium", True,
        [str(kit.cache / "logs" / "limits-compose.yaml"),
         str(kit.kit / "tranches" / "screen-cpu" / "relay-compose.yaml")],
        str(kit.cache / "logs" / "containers-override.conf"), ("tiny-a", "smoke", "observation")), err


def test_a_round_read_through_the_wrapper_scans_this_line_s_recordings_and_exits_0(rig):
    """S1: after round 1 (the smoke and the pilot of two competitions), the launcher's read of D4's whole file set,
    this line's ~/mle-cache/recordings included, is clean; the tranche then waits for the pilot's row."""
    r = rig(plan=[{}, {}])
    label = r.kit.label("screen-cpu")
    first = r.launch(timeout=WAIT * 5)
    r.ledger("Smoke read", f"{label} pass")
    code, out, err = r.launch(timeout=WAIT * 5)
    rounds = [(e["round"], e["exit"]) for e in r.events() if e["event"] == "round_scan"]
    assert (first[0], code, rounds, out.strip().splitlines()[-1], [a["kind"] for a in r.attempts()]) == (
        0, 0, [(1, 0)], "waiting for the pilot's ledger row", ["smoke", "pilot"]), err


# ---- the ledger per tranche (Task 5, second item; ruling B1) ---------------------------------------------------


def _reads(label):
    return [("Smoke read", f"{label} pass"), ("Pilot read", f"{label} read"), ("Round 1 read", f"{label} read")]


def test_a_tranche_is_held_at_its_pilot_although_another_tranche_s_ledger_and_the_plan_s_hold_passing_reads(kit):
    """The other ledgers' rows name this tranche's own label as well as theirs, so only the file read decides."""
    lad = kit.screen.launcher("screen-cpu")
    ctx = lad.Ctx({**kit.env(live=True), "LH": str(kit.cache)})
    mine, theirs = kit.label("screen-cpu"), kit.label("screen-gpu")
    kit.ledger_row(ledger("screen-cpu"), "Configuration label", f"{mine} {'0' * 40} this tranche")
    for path in (ledger("screen-gpu"), PLAN):
        kit.ledger_row(path, "Configuration label", f"{theirs} {'0' * 40} another tranche")
        for what, cell in _reads(theirs) + _reads(mine):
            kit.ledger_row(path, what, cell)
    heads = [{"kind": "pilot", "round": 1}, {"kind": "round", "round": 2}]
    held = [lad.hold(head, *lad.ledger_labels(ctx)) for head in heads]
    for what, cell in _reads(mine):
        kit.ledger_row(ledger("screen-cpu"), what, cell)
    released = [lad.hold(head, *lad.ledger_labels(ctx)) for head in heads]
    assert (held, released) == (["waiting for the smoke read"] * 2, [None, None])


def test_a_ruling_row_in_another_tranche_s_ledger_or_the_plan_s_lifts_no_stop_here(kit):
    lad = kit.screen.launcher("screen-cpu")
    ctx = lad.Ctx({**kit.env(live=True), "LH": str(kit.cache)})
    lad.ensure_state(ctx.root)
    lad.tranche_event(ctx.root, "stop", reason="a match of token_scan.py")
    args = Namespace(date="2026-11-20", clears=None)
    for path in (ledger("screen-gpu"), PLAN):
        kit.ledger_row(path, "Ruling", "resume: a match of token_scan.py: lifted")
    with pytest.raises(lad.Refused, match="no row yet for: a match of token_scan.py"):
        lad._stop_ruled(ctx, args)
    kit.ledger_row(ledger("screen-cpu"), "Ruling", "resume: a match of token_scan.py: lifted")
    assert lad._stop_ruled(ctx, args) is None


# ---- the launcher's refusals through the wrapper (Task 5, third item) -----------------------------------------


@pytest.mark.parametrize("edit,why", [
    (lambda d: d["attempt"].update(model="claude-sonnet-5-5"), "the criterion's model is not claude-haiku-5-5"),
    (lambda d: d["attempt"].update(efforts=["low", "medium"]), "the criterion's efforts are not medium")])
def test_another_model_or_effort_in_the_tranche_s_criterion_is_refused_by_the_launcher(kit, edit, why):
    doc = kit.criterion("screen-cpu")
    edit(doc)
    (kit.kit / "tranches" / "screen-cpu" / "ladder.json").write_text(json.dumps(doc, indent=1))
    kit.remanifest("screen-cpu")
    assert _launcher_refused(kit.run("screen-cpu", "launch")) == (3, why)


def test_a_package_whose_digest_differs_is_refused_by_the_launcher(kit):
    (kit.cache / "packages" / "tiny-b" / "x" / "instruction.md").write_text("changed\n")
    assert _launcher_refused(kit.run("screen-cpu", "launch")) == (
        3, "tiny-b: the package's digest is not its 4.1.0 digest")


def test_a_package_whose_image_differs_from_tasks_json_is_refused_by_the_launcher(kit):
    path = kit.cache / "packages" / "tiny-a" / "x" / "task.toml"
    path.write_text(path.read_text().replace("tiny-a-agent@sha256:", "tiny-a-other@sha256:"))
    doc = kit.tasks("screen-cpu")
    doc["tasks"][0]["digest_4_1_0"] = wrap.digest(path.parent)  # the digest made to match: only the image differs
    kit.write_tasks("screen-cpu", doc)
    kit.remanifest("screen-cpu")
    assert _launcher_refused(kit.run("screen-cpu", "launch")) == (
        3, "tiny-a: an image the package pins is not the one tasks.json pins")


@pytest.mark.parametrize("name", ["CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"])
def test_a_credential_in_the_environment_is_refused_by_the_launcher_naming_it_never_its_value(kit, name):
    value = "lh-test-" + os.urandom(16).hex()
    result = kit.run("screen-cpu", "launch", env=kit.env(**{name: value}))
    code, reason = _launcher_refused(result)
    assert (code, name in (reason or ""), value in result[1] + result[2]) == (3, True, False)


@pytest.mark.parametrize("var", ["LH_MANIFEST_SHA256", "LH_RUNTIME_COMMIT"])
def test_a_rehearsal_with_a_spend_variable_is_refused_by_the_launcher(kit, var):
    assert _launcher_refused(kit.run("screen-cpu", "launch", env=kit.env(**{var: "x"}))) == (
        3, f"a rehearsal with a spend variable set ({var})")


def test_no_allowance_inputs_is_refused_by_the_launcher(kit):
    code, reason = _launcher_refused(kit.run("screen-cpu", "launch"))
    assert (code, reason.startswith("no allowance inputs")) == (3, True)


def test_a_live_launch_without_authorization_passes_the_wrapper_and_is_refused_by_the_launcher(kit):
    kit.freeze()
    assert _launcher_refused(kit.run("screen-cpu", "launch", env=kit.env(live=True))) == (
        3, "no authorization: a live launch needs LH_SPEND_AUTHORIZED=yes (or LH_REHEARSAL=<dir>)")


LIVE_CHANGES = {
    "another label is the tranche ledger's current one":
        (lambda k: k.ledger_row(ledger("screen-cpu"), "Configuration label", f"{'a' * 64} {'0' * 40} later"),
         "is not the ledger's current configuration label"),
    "the label is only in another tranche's ledger":
        (lambda k: (shutil.copy(k.repo / ledger("screen-cpu"), k.short / "l"),
                    k.ledger_row(ledger("screen-gpu"), "Configuration label",
                                 _git(k.repo, "show", f"main:{ledger('screen-cpu')}").splitlines()[-1].split(" | ")[2]),
                    _drop_label(k)),
         "is not the ledger's current configuration label"),
    "the reviewed kit is dirty":
        (lambda k: (k.repo / "experiments" / "long_horizon_tasks" / "README.md").write_text("changed\n"),
         "the kit has uncommitted changes"),
    "a reviewed file changed":
        (lambda k: (k.repo / "experiments" / "long_horizon_tasks" / "slot_record.py").open("a").write("\n# x\n"),
         "the manifest does not match the kit: experiments/long_horizon_tasks/slot_record.py"),
}


def _drop_label(kit):
    """Remove the tranche's own Configuration label row from its ledger on main."""
    head = _git(kit.repo, "rev-parse", "HEAD")
    _git(kit.repo, "checkout", "-q", "main")
    path = kit.repo / ledger("screen-cpu")
    path.write_text("".join(line for line in path.read_text().splitlines(keepends=True)
                            if "Configuration label" not in line))
    _git(kit.repo, *GIT_ID, "commit", "-q", "-am", "drop")
    _git(kit.repo, "checkout", "-q", "--detach", head)


@pytest.mark.parametrize("change", sorted(LIVE_CHANGES))
def test_the_launcher_s_live_checks_hold_against_this_tranche_s_ledger_and_the_reviewed_kit(kit, change):
    """The per-start check of a live launch (config_refusal, which needs no authorization to run), on the wrapped
    launcher: clean before the change, refused after it."""
    kit.freeze()
    lad = kit.screen.launcher("screen-cpu")
    commit = _git(kit.repo, "rev-parse", "HEAD")
    ctx = lad.Ctx({**kit.env(live=True), "LH": str(kit.cache), "LH_MANIFEST_SHA256": kit.label("screen-cpu"),
                   "LH_RUNTIME_COMMIT": commit})
    ladder = lad.criterion(ctx)
    before = lad.config_refusal(ctx, lad.this_label(), ladder)
    make, why = LIVE_CHANGES[change]
    make(kit)
    after = lad.config_refusal(ctx, lad.this_label(), ladder)
    assert (before, why in (after or "")) == (None, True), after


# ---- the manifest over this kit (Task 5, fourth item; ruling M-a) -----------------------------------------------

KIT_CHANGES = {"an uncommitted edit to screen.py": lambda k: (k.kit / "screen.py").open("a").write("\n# x\n"),
               "a new file in the kit": lambda k: (k.kit / "verifier" / "extra.py").write_text("x = 1\n"),
               "a removed file of the kit": lambda k: (k.kit / "agent" / "validate_submission.py").unlink(),
               "an edit in the tranche's directory": lambda k: (k.kit / "tranches" / "screen-cpu" / "tasks.json")
               .open("a").write(" ")}


@pytest.mark.parametrize("change", sorted(KIT_CHANGES))
def test_a_change_to_this_kit_after_the_launch_stops_the_tranche_before_its_next_start(kit, change):
    lad = kit.screen.launcher("screen-cpu")
    ctx = lad.Ctx({**kit.env(), "LH": str(kit.cache)})
    ladder = lad.criterion(ctx)
    before = lad.config_refusal(ctx, lad.this_label(), ladder)
    KIT_CHANGES[change](kit)
    after = lad.config_refusal(ctx, lad.this_label(), ladder)
    assert (before, (after or "").startswith("the manifest does not match the kit")) == (None, True)


def test_the_wrapper_freezes_a_tranche_s_manifest_by_the_reviewed_module_and_the_launcher_accepts_it(kit):
    """Ruling M-a: the freeze reads the tranche's own ladder.json and writes, through a second private load of the
    reviewed manifest.py with M4's four names set, the files the launcher's load hashes."""
    code, out, err = kit.run("screen-cpu", "manifest", "write", "--freeze")
    written = json.loads((kit.kit / "manifests" / "screen-cpu.json").read_text())
    lad = kit.screen.launcher("screen-cpu")
    assert (code, out.strip(), written["frozen"], written["files"] == lad.manifest.files(),
            kit.screen.tranche_manifest("screen-cpu").files() == lad.manifest.files(),
            kit.run("screen-cpu", "manifest", "check")[0], lad._manifest_refusal(True)) == (
        0, kit.label("screen-cpu"), True, True, True, 0, None), err


def test_a_tranche_with_a_pending_field_is_not_frozen(short):
    kit = Kit(short, filled=False)
    before = (kit.kit / "manifests" / "screen-cpu.json").read_bytes()
    code, out, err = kit.run("screen-cpu", "manifest", "write", "--freeze")
    assert (code, "pending: tasks.packages" in err, (kit.kit / "manifests" / "screen-cpu.json").read_bytes()) == (
        2, True, before)


# ---- the wrapper's own refusals, each before the launcher is entered (Task 5, fifth item) ---------------------
# Without allowance inputs the launcher would refuse ("no allowance inputs"), so a reason of the wrapper's shows
# that the wrapper refused first; no launch below gives the launcher its inputs.


def _tag(kit):
    doc = kit.tasks("screen-cpu")
    doc["tasks"][1]["environment_image"] = "localhost/mle-bench/tiny-b-agent:latest"
    kit.write_tasks("screen-cpu", doc)


def _no_digest(kit):
    doc = kit.tasks("screen-cpu")
    doc["tasks"][0]["verifier_image"] = "localhost/mle-bench/tiny-a-verifier"
    kit.write_tasks("screen-cpu", doc)


def _result(kit, **change):
    doc = kit.tasks("screen-cpu")
    doc["tasks"][1]["withholding"] = {**doc["tasks"][1]["withholding"], **change}
    kit.write_tasks("screen-cpu", doc)


WITHHOLDING = {
    "absent": (lambda k: _result_none(k), "no withholding result"),
    "failed": (lambda k: _result(k, verdict="fail"), "did not pass"),
    "another digest": (lambda k: _result(k, image="localhost/mle-bench/tiny-b-agent@sha256:" + "e" * 64),
                       "names another image"),
    "another competition": (lambda k: _result(k, competition="leaf-classification"), "another competition"),
    "another version of the check": (lambda k: _result(k, check_sha256="sha256:" + "d" * 64),
                                     "another version of withhold_check.py"),
}


def _result_none(kit):
    doc = kit.tasks("screen-cpu")
    doc["tasks"][1]["withholding"] = None
    kit.write_tasks("screen-cpu", doc)


@pytest.mark.parametrize("case", sorted(WITHHOLDING))
def test_a_competition_without_a_passing_withholding_result_for_its_image_is_refused(kit, case):
    make, why = WITHHOLDING[case]
    make(kit)
    code, reason = _wrapper_refused(kit.run("screen-cpu", "launch"))
    assert (code, (reason or "").startswith("mle-bench/tiny-b: "), why in (reason or "")) == (3, True, True), reason


@pytest.mark.parametrize("make", [_tag, _no_digest])
def test_an_image_reference_with_a_tag_or_without_a_digest_is_refused(kit, make):
    make(kit)
    code, reason = _wrapper_refused(kit.run("screen-cpu", "launch"))
    assert (code, "not pinned by digest" in (reason or "")) == (3, True)


def _symlinked_cache(kit):
    shutil.rmtree(kit.cache)
    kit.cache.symlink_to(kit.lh)


def _linked(part):
    """The cache's `part` replaced by a link into the ladder's cache."""
    def make(kit):
        shutil.rmtree(kit.cache / part)
        (kit.lh / part).mkdir(exist_ok=True)
        (kit.cache / part).symlink_to(kit.lh / part)
    return make


def _one_qualified(kit):
    doc = kit.criterion("screen-cpu")
    doc["tasks"]["qualified"] = ["tiny-a"]
    (kit.kit / "tranches" / "screen-cpu" / "ladder.json").write_text(json.dumps(doc, indent=1))


WRAPPER_REFUSALS = {
    "a tranche outside the kit's list": (lambda k: None, ("screen-xyz", "launch"), {},
                                          "screen-xyz is not a tranche of the kit"),
    "a tranche not generated": (lambda k: None, ("place-cpu", "launch"), {}, "place-cpu has no tranche directory"),
    "LH naming the ladder's cache": (lambda k: None, ("screen-cpu", "launch"), {"LH": "<lh>"}, "this line's cache is"),
    "a cache that resolves to the ladder's": (_symlinked_cache, ("screen-cpu", "launch"), {},
                                              "resolves into the ladder's cache"),
    "the cache's logs in the ladder's": (_linked("logs"), ("screen-cpu", "launch"), {},
                                         "logs resolves into the ladder's cache"),
    "the cache's packages in the ladder's": (_linked("packages"), ("screen-cpu", "launch"), {},
                                             "packages resolves into the ladder's cache"),
    "no recordings directory in the cache": (lambda k: (k.cache / "recordings").rmdir(), ("screen-cpu", "launch"), {},
                                             "recordings is not a directory of this line's own"),
    "the cache's recordings a link": (_linked("recordings"), ("screen-cpu", "launch"), {},
                                      "recordings is not a directory of this line's own"),
    "one qualified competition": (_one_qualified, ("screen-cpu", "plan"), {}, "has 1 qualified competitions"),
    "an uncommitted change under the kit": (lambda k: (k.kit / "NOTES.md").write_text("x\n"), ("screen-cpu", "launch"),
                                            {}, "experiments/mle_bench_tasks has uncommitted changes"),
    "an uncommitted change under the kit, at resume": (lambda k: (k.kit / "NOTES.md").write_text("x\n"),
                                                       ("screen-cpu", "resume"), {},
                                                       "experiments/mle_bench_tasks has uncommitted changes"),
}


@pytest.mark.parametrize("case", sorted(WRAPPER_REFUSALS))
def test_the_wrapper_refuses_before_the_launcher_is_entered(kit, case):
    make, argv, extra, why = WRAPPER_REFUSALS[case]
    make(kit)
    extra = {k: str(kit.lh) if v == "<lh>" else v for k, v in extra.items()}
    code, reason = _wrapper_refused(kit.run(*argv, env=kit.env(**extra)))
    assert (code, why in (reason or "")) == (3, True), reason


@pytest.mark.parametrize("path", ["/", "/home"])
def test_free_disk_under_the_launch_condition_on_either_file_system_is_refused(short, path):
    def need(fields):
        fields["classes"]["cpu"]["set"]["host.disk_plan"]["launch_room_gb"] = {"/": 0, "/home": 0, path: 10 ** 9}
    kit = Kit(short, edit=need)
    code, reason = _wrapper_refused(kit.run("screen-cpu", "launch"))
    assert (code, f"free disk on {path} is" in (reason or "")) == (3, True)


@pytest.mark.parametrize("gpu", ["4242, python3, 512\n", None])
def test_a_gpu_tranche_is_refused_while_a_process_holds_memory_on_the_card_or_the_card_cannot_be_read(kit, gpu):
    if gpu is None:
        (kit.lh / "standin" / "gpu_fails").write_text("")
    else:
        (kit.lh / "standin" / "gpu.txt").write_text(gpu)
    code, reason = _wrapper_refused(kit.run("screen-gpu", "launch"))
    want = "a process holds memory on the GPU: 4242 python3" if gpu else "the GPU's processes cannot be read"
    assert (code, want in (reason or "")) == (3, True), reason


def test_a_gpu_tranche_with_an_idle_card_passes_the_wrapper(kit):
    """The control: nvidia-smi lists no process, and the launcher refuses for its own reason."""
    assert (_wrapper_refused(kit.run("screen-gpu", "launch"))[1], _launcher_refused(kit.run("screen-gpu", "launch"))[0]
            ) == (None, 3)


HOLDER = """import fcntl, os, sys, time
fh = open(sys.argv[1], "a+")
fcntl.flock(fh, fcntl.LOCK_EX)
fh.seek(0); fh.truncate(); fh.write(f"{os.getpid()}\\n"); fh.flush()
print("held", flush=True)
time.sleep(120)
"""

LISTENER = """import socket, sys, time
s = socket.socket(socket.AF_UNIX)
s.bind(sys.argv[1]); s.listen(8)
print("held", flush=True)
time.sleep(120)
"""


def _hold(script, path):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    proc = subprocess.Popen([sys.executable, "-c", script, str(path)], stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "held"
    return proc


LIVE_HOLDS = {
    "the ladder's launcher lock": (HOLDER, ".local/state/lh-ladder/launcher.lock", "another launcher holds"),
    "the line's lock": (HOLDER, ".local/state/mle-bench/launcher.lock", "another launcher holds"),
    "the ladder's passthrough": (LISTENER, ".local/state/lh-ladder/relay/passthrough.sock", "answers"),
    "the live probe's passthrough": (LISTENER, ".local/state/lh-probe/relay/passthrough.sock", "answers"),
    "another tranche's passthrough": (LISTENER, ".local/state/mle-bench/screen-gpu/relay/passthrough.sock", "answers"),
}


@pytest.mark.parametrize("command", ["launch", "resume"])
@pytest.mark.parametrize("hold", sorted(LIVE_HOLDS))
def test_a_live_launch_or_resume_is_refused_while_another_launcher_or_passthrough_holds_the_line(kit, hold, command):
    """Without the hold the launcher would refuse (no authorization, or the unfrozen criterion at resume)."""
    kit.freeze()
    script, rel, why = LIVE_HOLDS[hold]
    holder = _hold(script, kit.home / rel)
    try:
        code, reason = _wrapper_refused(kit.run("screen-cpu", command, env=kit.env(live=True)))
    finally:
        holder.kill()
        holder.wait()
    named = str(holder.pid) if script is HOLDER else str((kit.home / rel).parent.parent)
    assert (code, why in (reason or ""), named in (reason or "")) == (3, True, True), reason


@pytest.mark.parametrize("lock, refused", [(".local/state/lh-ladder/launcher.lock", True),
                                           (".local/state/mle-bench/launcher.lock", False)])
def test_a_rehearsal_takes_the_ladder_s_lock_and_not_the_line_s(kit, lock, refused):
    """A rehearsal never runs beside a ladder launcher (a paid ladder run); this line's lock is a live tranche's."""
    holder = _hold(HOLDER, kit.home / lock)
    try:
        result = kit.run("screen-cpu", "launch")
    finally:
        holder.kill()
        holder.wait()
    reason = _wrapper_refused(result)[1]
    assert (reason is not None and "another launcher holds" in reason,
            (_launcher_refused(result)[1] or "").startswith("no allowance inputs")) == (refused, not refused)


def test_a_one_competition_tranche_s_qualified_stand_in_is_refused_in_a_rehearsal(short):
    """M9-R1, while tasks.qualified is pending: the rehearsal's stand-in is the list the launcher would run."""
    kit = Kit(short, filled=False)
    (kit.reh / "stand_ins.json").write_text(json.dumps({"tasks.qualified": ["tiny-a"]}))
    code, reason = _wrapper_refused(kit.run("screen-cpu", "plan"))
    assert (code, "has 1 qualified competitions" in (reason or "")) == (3, True)


def test_while_this_line_s_launcher_runs_the_ladder_s_unmodified_launcher_is_refused_on_its_state_root(kit):
    """The wrapper's exclusive section (held for the launcher's whole life), and the ladder's own `resume`, which
    takes the reviewed lock on ~/.local/state/lh-ladder; once the section ends the lock is free again."""
    lad = kit.screen.launcher("screen-cpu")
    argv = [sys.executable, "-I", str(kit.repo / "experiments" / "long_horizon_tasks" / "ladder.py"), "resume"]
    env = {"HOME": str(kit.home)}
    with kit.screen.exclusive(lad, kit.home):
        during = subprocess.run(argv, cwd=kit.repo, env=env, capture_output=True, text=True, timeout=WAIT).stderr
    after = subprocess.run(argv, cwd=kit.repo, env=env, capture_output=True, text=True, timeout=WAIT).stderr
    ladder_root = kit.home / ".local" / "state" / "lh-ladder"
    assert (f"another launcher holds {ladder_root}" in during, "another launcher holds" in after) == (True, False)


# ---- the money and the schedule (Task 5, sixth item) -----------------------------------------------------------

RESERVE = """
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("screen", sys.argv[1])
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)
lad = screen.launcher("screen-cpu")
root, n = Path(sys.argv[2]), int(sys.argv[3])
entry = {"round": n, "task": ("tiny-a", "tiny-b")[n % 2], "effort": "medium", "kind": "round"}
got = lad.reserve(root, entry, json.loads((lad.KIT / "ladder.json").read_text()), 0.0)
print(json.dumps(got if isinstance(got, dict) else got.reason))
"""


def test_sixty_concurrent_launches_never_commit_more_than_the_tranche_s_ceiling(kit, short):
    """Each reservation is the cap of USD 8 and the margin of USD 1, so 5 fit in screen-cpu's USD 50 (the ladder's
    USD 200 would hold 22)."""
    root = short / "state"
    LT.ladder.ensure_state(root)
    procs = [subprocess.Popen([sys.executable, "-I", "-c", RESERVE, str(kit.kit / "screen.py"), str(root), str(n)],
                              cwd=kit.repo, stdout=subprocess.PIPE, text=True) for n in range(60)]
    results = [json.loads(proc.communicate(timeout=WAIT * 5)[0]) for proc in procs]
    starts, committed, open_ = LT.ladder.tally(root, kit.criterion("screen-cpu"), 0.0)
    assert (len([r for r in results if isinstance(r, dict)]), starts, committed, len(open_),
            {r for r in results if not isinstance(r, dict)}) == (5, 5, 45.0, 5, {"does not fit"})


def test_the_tranche_s_starts_cap_of_eight_refuses_a_ninth_start(kit, short):
    """Two competitions: 3 x 2 + 2 starts (M9); the ladder's own cap is 240. The launcher's reason keeps its
    literal wording."""
    lad = kit.screen.launcher("screen-cpu")
    root, ladder = short / "state", kit.criterion("screen-cpu")
    lad.ensure_state(root)
    for n in range(8):
        entry = {"round": n, "task": "tiny-a", "effort": "medium", "kind": "round"}
        lad.settle(root, lad.reserve(root, entry, ladder, 0.0), {"usd": 0.01, "class": "observation"}, ladder)
    head = {"round": 9, "task": "tiny-a", "effort": "medium", "kind": "round"}
    assert lad.next_start(root, [head], ladder, 0.0) == ("end", "240 starts")


def test_a_usage_limit_cuts_the_smoke_closes_starts_until_after_its_reset_and_its_slot_runs_again(rig):
    """The smoke's second turn meets the stub's usage limit, whose reset is 292 s ago: starts reopen 8 s later,
    the cut slot is the first start after it, and the tranche then waits for the smoke read."""
    usage_limit = str(LADDER_KIT / "fixtures" / "token-usage-limit-NonZeroAgentExitCodeError.json")
    r = rig(plan=[{"turn": 1, "fixture": usage_limit, "sleep": 1}, {}], scenario="usage_limit",
            stub_args=("--delay", "-292"))
    code, out, err = r.launch(timeout=WAIT * 5)
    every = sorted(r.attempts(), key=lambda a: a["opened"])
    (limit,) = [e for e in r.events() if e["event"] == "close_starts"]
    until = float(limit["reset"]) + LT.ladder.REOPEN_S
    assert (code, out.strip().splitlines()[-1], [a["settled"]["class"] for a in every], every[1].get("rerun_of"),
            {(a["round"], a["task"], a["effort"], a["kind"]) for a in every}, every[1]["opened"] >= until) == (
        0, "waiting for the smoke read", ["cut", "observation"], every[0]["id"], {(1, "tiny-a", "medium", "smoke")},
        True), err


def test_the_schedule_is_the_smoke_then_the_pilot_then_three_rounds_at_one_effort(kit):
    lines = [tuple(line.split()) for line in kit.run("screen-cpu", "plan")[1].splitlines()]
    assert (lines[:2], sorted(lines[2:])) == (
        [("r1-tiny-a-medium", "smoke"), ("r1-tiny-b-medium", "pilot")],
        [("r2-tiny-a-medium", "round"), ("r2-tiny-b-medium", "round"),
         ("r3-tiny-a-medium", "round"), ("r3-tiny-b-medium", "round")])


def _stage_two(kit, funded):
    """screen-cpu-2, made by the generator's own stage-two step from stage one's criterion, and committed."""
    mc = _load(f"mle_screen_mc_{id(kit)}", kit.kit / "make_criterion.py")
    derivation = {"export_label": "e" * 64, "export_sha256": "f" * 64, "no_medal": list(funded),
                  "funded": list(funded), "not_funded": [], "mean_usd_per_start": 3.0, "committed_usd": 20.0,
                  "live_probe_usd": 0.0, "k": len(funded), "ceiling_usd": 30.0}
    two = mc._stage_two(kit.criterion("screen-cpu"), derivation, "cpu", mc.FIELDS)
    mc.write_tranche(mc.TRANCHES / "screen-cpu-2", two, mc.tasks_json(two))
    mc.write_manifest("screen-cpu-2")
    kit.commit("stage two")


def test_a_stage_two_tranche_starts_with_its_own_smoke_and_pilot_and_reads_its_own_ledger(kit):
    _stage_two(kit, ["tiny-b", "tiny-a"])
    lines = [tuple(line.split()) for line in kit.run("screen-cpu-2", "plan")[1].splitlines()]
    assert (lines[:2], len(lines), kit.screen.launcher("screen-cpu-2").PLAN) == (
        [("r1-tiny-b-medium", "smoke"), ("r1-tiny-a-medium", "pilot")], 6, ledger("screen-cpu-2"))


# ---- the wrapper's own record of the GPU (M4 item 7, M5) ---------------------------------------------------------


def test_a_gpu_tranche_s_launch_through_the_wrapper_records_the_card_into_its_state(kit):
    """M4 item 7: the record runs while the launcher runs, here a launch the launcher refuses at once (no allowance
    inputs): its first row is written as it starts."""
    (kit.lh / "standin" / "gpu.txt").write_text("")
    result = kit.run("screen-gpu", "launch")
    rows = LT.ladder._jsonl(kit.reh / "state" / "screen" / "gpu.jsonl")
    assert (_launcher_refused(result)[0], [r["processes"] for r in rows]) == (3, [[]])


def test_the_gpu_s_processes_are_recorded_into_the_tranche_s_state(kit, short):
    (kit.lh / "standin" / "gpu.txt").write_text("4242, python3, 512\n")
    lad = kit.screen.launcher("screen-gpu")
    ctx = lad.Ctx({**kit.env(), "LH": str(kit.cache)})
    lad.ensure_state(ctx.root)
    kit.screen.record_gpu(lad, ctx)
    (row,) = LT.ladder._jsonl(ctx.root / "screen" / "gpu.jsonl")
    assert [(p["pid"], p["name"], p["mib"]) for p in row["processes"]] == [("4242", "python3", "512")]
