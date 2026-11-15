"""The long-horizon launcher (`experiments/long_horizon_tasks/ladder.py`; plan Task 5).

Everything runs against stand-ins: a stand-in harness (the harness venv's `python`, which replays recorded fixtures
and acts as a stand-in `podman`), the passthrough in rehearsal mode in front of `stub_api.py`, and a copy of the kit
in a temporary git repository where a test needs one. Every token is a string this module or the passthrough's
rehearsal switch makes; no request leaves the machine, no real CLI or harness runs, and no container is started.
(The criterion's own tests are `test_long_horizon_ladder.py`; this module is the launcher's.)
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
KIT = REPO / "experiments" / "long_horizon_tasks"
PLAN = "docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md"
WAIT = 120  # seconds; the machine is shared and heavily loaded


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ladder = _load("lh_ladder_launcher", KIT / "ladder.py")
TASKS = ("gsea-proteomics", "rs-archive-clone", "wal-recovery-ordering")  # the rehearsals' qualified stand-in


@pytest.fixture
def short():
    """A mode-700 directory with a short path (AF_UNIX paths stop at 108 bytes), removed at the end."""
    path = Path(tempfile.mkdtemp(prefix="lhl", dir="/tmp"))
    yield path
    for root, dirs, _ in os.walk(path):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o700)
    shutil.rmtree(path)


# ---- stand-ins: the cache, the harness's Python, the kit copy ---------------------------------------------------

STANDIN = r'''
"""The stand-in harness venv `python` (tests/experiments/test_long_horizon_launcher.py). `-I -c CODE ARGS` runs CODE
with a stand-in `harbor.publisher.packager` and the package versions of standin/versions.json."""
import hashlib, importlib.metadata, json, sys, types
from pathlib import Path

HERE = Path(__file__).resolve().parents[2] / "standin"


def content_hash(path):
    outer = hashlib.sha256()
    for f in sorted(p for p in Path(path).rglob("*") if p.is_file()):
        outer.update(f"{f.relative_to(path).as_posix()}\0{hashlib.sha256(f.read_bytes()).hexdigest()}\n".encode())
    return outer.hexdigest(), []


def run_code(code, args):
    versions = json.loads((HERE / "versions.json").read_text())
    importlib.metadata.version = lambda name: versions[name]
    packager = types.ModuleType("harbor.publisher.packager")
    packager.Packager = type("Packager", (), {"compute_content_hash": staticmethod(content_hash)})
    for name in ("harbor", "harbor.publisher"):
        sys.modules[name] = types.ModuleType(name)
    sys.modules["harbor.publisher.packager"] = packager
    sys.argv = ["-c", *args]
    exec(compile(code, "<stand-in -c>", "exec"), {"__name__": "__main__"})


def log_call(args):
    import os
    with open(HERE / "calls.jsonl", "a") as fh:
        fh.write(json.dumps({"argv": args, "env": dict(os.environ), "pid": os.getpid()}) + "\n")


def option(args, name):
    return args[args.index(name) + 1] if name in args else None


def regrade(args):
    """`harbor_patient.py trial regrade TRIAL -p TASK --env podman --trial-name NAME -o DIR`: the next outcome of
    standin/regrade.json for this source trial: a reward, or the exception the verifier ended with."""
    plan = json.loads((HERE / "regrade.json").read_text()) if (HERE / "regrade.json").exists() else {}
    outcomes = plan.get(Path(args[2]).name, [{"reward": 1.0}])
    done = sum(1 for line in (HERE / "calls.jsonl").read_text().splitlines()
               if json.loads(line)["argv"][1:4] == ["trial", "regrade", args[2]])
    outcome = outcomes[min(done, len(outcomes)) - 1]
    out = Path(option(args, "-o")) / option(args, "--trial-name")
    out.mkdir(parents=True)
    exc = {"exception_type": outcome["exception"], "exception_message": ""} if "exception" in outcome else None
    reward = {"rewards": {"reward": outcome["reward"]}} if "reward" in outcome else None
    (out / "result.json").write_text(json.dumps({"exception_info": exc, "verifier_result": reward}))


args = sys.argv[1:]
if args[:1] == ["-I"]:
    args = args[1:]
if args[:1] == ["-c"]:
    run_code(args[1], args[2:])
elif args[1:3] == ["trial", "regrade"]:
    log_call(args)
    regrade(args[1:])
else:
    sys.exit(f"stand-in python: unexpected {args[:2]}")
'''

PODMAN = r'''
"""The stand-in podman (test_long_horizon_launcher.py): containers and networks are JSON files under
standin/podman; every call is logged. A container's `stubborn` count is how many removals it survives."""
import json, sys
from pathlib import Path

STATE = Path(__file__).resolve().parents[2] / "standin" / "podman"
C, N = STATE / "containers", STATE / "networks"
args = sys.argv[1:]
with open(STATE / "calls.jsonl", "a") as fh:
    fh.write(json.dumps(args) + "\n")


def names(folder):
    return sorted(p.stem for p in folder.glob("*.json"))


def operands(rest):
    out, skip = [], False
    for arg in rest:
        if skip:
            skip = False
        elif arg in ("-t", "--time", "--format"):
            skip = True
        elif not arg.startswith("-"):
            out.append(arg)
    return out


def load(name):
    path = C / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


cmd, rest = args[0], args[1:]
if cmd == "ps":
    every = "-a" in rest
    print("\n".join(n for n in names(C) if every or load(n).get("running", True)))
elif cmd == "rm":
    for name in operands(rest):
        found = load(name)
        if found and found.get("stubborn", 0) > 0:
            found["stubborn"] -= 1
            (C / f"{name}.json").write_text(json.dumps(found))
        elif found:
            (C / f"{name}.json").unlink()
elif cmd == "network" and rest[0] == "ls":
    print("\n".join(names(N)))
elif cmd == "network" and rest[0] == "rm":
    for name in operands(rest[1:]):
        (N / f"{name}.json").unlink(missing_ok=True)
elif cmd == "inspect":
    print(json.dumps([{"Name": n, "Config": {"Env": load(n).get("env", [])}} for n in operands(rest) if load(n)]))
elif cmd == "logs":
    print((load(operands(rest)[0]) or {}).get("log", ""))
elif cmd == "exec":
    found = load(operands(rest)[0])
    if not found or not found.get("running", True):
        sys.exit(125)
    sys.stdout.write("\0".join(found.get("env", [])))
elif cmd == "export":
    sys.stdout.write((load(operands(rest)[0]) or {}).get("fs", ""))
else:
    sys.exit(f"stand-in podman: unexpected {args[:2]}")
'''


def _content_hash(path):
    """The stand-in Packager's digest (Harbor's construction, over every file under `path`)."""
    outer = hashlib.sha256()
    for f in sorted(p for p in Path(path).rglob("*") if p.is_file()):
        outer.update(f"{f.relative_to(path).as_posix()}\0{hashlib.sha256(f.read_bytes()).hexdigest()}\n".encode())
    return "sha256:" + outer.hexdigest()


def _task_toml(record):
    return (f'[task]\nname = "{record["name"]}"\n\n[verifier]\ntimeout_sec = 300.0\n\n[verifier.environment]\n'
            f'docker_image = "{record["verifier_image"]}"\n[agent]\ntimeout_sec = 28800.0\n\n[environment]\n'
            f'docker_image = "{record["environment_image"]}"\n')


def _cache(short, records):
    """$LH: the stand-in harness venv, the host-side overrides of the criterion, and a stand-in package per task."""
    lh = short / "lh"
    (lh / "hvenv" / "bin").mkdir(parents=True)
    (lh / "standin").mkdir()
    python = lh / "hvenv" / "bin" / "python"
    python.write_text(f"#!{sys.executable} -I\n{STANDIN}")
    python.chmod(0o700)
    (lh / "standin" / "versions.json").write_text(json.dumps({"harbor": "0.25.0", "podman-compose": "1.6.0"}))
    podman = lh / "hvenv" / "bin" / "podman"
    podman.write_text(f"#!{sys.executable} -I\n{PODMAN}")
    podman.chmod(0o700)
    for folder in ("containers", "networks"):
        (lh / "standin" / "podman" / folder).mkdir(parents=True)
    side = json.loads((KIT / "ladder.json").read_text())["harness"]["host_side"]
    (lh / "logs").mkdir()
    (lh / "logs" / "containers-override.conf").write_text(side["containers_override"]["content"])
    (lh / "logs" / "limits-compose.yaml").write_text(side["limits_compose"]["content"])
    for record in records:
        x = lh / "tasks41" / record["name"].rsplit("/", 1)[-1] / "x"
        (x / "environment").mkdir(parents=True)
        (x / "task.toml").write_text(_task_toml(record))
        (x / "instruction.md").write_text("A stand-in task.\n")
        (x / "environment" / "Dockerfile").write_text("FROM scratch\n")
    return lh


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def _manifest(repo, *args):
    return subprocess.run([sys.executable, "-I", str(repo / "experiments/long_horizon_tasks/manifest.py"), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


STAND_INS = {"tasks.qualified": list(TASKS), "tasks.load_sensitive": ["wal-recovery-ordering"],
             "tasks.overlay_digests": {}, "tasks.extra_hosts": {}, "tasks.withholding": {"all": "withheld"},
             "network.agent_phase.allowed_hosts": ["relay", "pypi.org", "files.pythonhosted.org"],
             "host.cpu_set": "0-23", "host.disk_plan": {"keep": "all"},
             "usage_limits.vendor_headers_confirmed": {"stand-in": True}, "allowance_guard.utilisation_header": "none",
             "readout.contamination_scan.terms": ["stand-in-term"], "readout.contamination_scan.canary_sha256": "0" * 64,
             "readout.graded_outcome.verifiers": {"stand-in": True}, "schedule.order.seed": "stand-in seed",
             "schedule.order.hash": "stand-in", "readout.fall_bound.seed": 1}


def _filled(doc, values):
    """`doc` with every pending field set to its value in `values` and moved to `filled` (a test's freeze)."""
    for entry in doc["pending"]:
        ladder._set(doc, entry["field"], values[entry["field"]])
    doc["filled"] += [{**e, "source": "a test"} for e in doc["pending"]]
    doc["pending"] = []
    return doc


class Kit:
    """A copy of the kit in a temporary git repository (branch main), with a stand-in cache whose packages are the
    ones its tasks.json names; `freeze()` makes it a live checkout: frozen, labelled in the ledger, detached."""

    def __init__(self, short, edit=None):
        self.repo, self.short = short / "repo", short
        kit = self.repo / "experiments" / "long_horizon_tasks"
        shutil.copytree(KIT, kit, ignore=shutil.ignore_patterns("__pycache__", "results"))
        (self.repo / "orchestrator").symlink_to(REPO / "orchestrator")
        (self.repo / "experiments" / "thread_m").mkdir()
        (self.repo / "experiments" / "thread_m" / "no_provider").symlink_to(REPO / "experiments/thread_m/no_provider")
        (self.repo / "tests" / "experiments").mkdir(parents=True)
        shutil.copy(REPO / "tests/experiments/test_long_horizon_ladder.py", self.repo / "tests/experiments")
        (self.repo / ".gitignore").write_text("__pycache__/\n")
        (self.repo / PLAN).parent.mkdir(parents=True)
        (self.repo / PLAN).write_text("# Plan (stand-in)\n\n## Ledger\n\n| Date | Entry |\n| --- | --- |\n")
        self.kit, self.label, self.commit = kit, None, None
        tasks = json.loads((kit / "tasks.json").read_text())
        self.lh = _cache(short, tasks["tasks"])
        for record in tasks["tasks"]:
            record["digest_4_1_0"] = _content_hash(self.lh / "tasks41" / record["name"].rsplit("/", 1)[-1] / "x")
        (kit / "tasks.json").write_text(json.dumps(tasks, indent=1) + "\n")
        if edit:
            doc = json.loads((kit / "ladder.json").read_text())
            edit(doc)
            (kit / "ladder.json").write_text(json.dumps(doc, indent=1))
        _manifest(self.repo, "write")
        for args in (("init", "-q", "-b", "main"), ("add", "-A"),
                     ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "kit")):
            _git(self.repo, *args)
        self.ladder = _load(f"lh_ladder_copy_{id(self)}", kit / "ladder.py")
        self.reh = short / "reh"
        self.reh.mkdir(mode=0o700)
        (self.reh / "stand_ins.json").write_text(json.dumps(STAND_INS))

    def freeze(self, label_row=True):
        doc = _filled(json.loads((self.kit / "ladder.json").read_text()), STAND_INS)
        (self.kit / "ladder.json").write_text(json.dumps(doc, indent=1))
        _manifest(self.repo, "write", "--freeze")
        _git(self.repo, "add", "-A")
        _git(self.repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "freeze")
        self.commit = _git(self.repo, "rev-parse", "HEAD")
        self.label = hashlib.sha256((self.kit / "manifest.json").read_bytes()).hexdigest()
        if label_row:
            self.ledger_row("Configuration label", f"{self.label} {self.commit} first label")
        _git(self.repo, "checkout", "-q", "--detach", self.commit)

    def ledger_row(self, what, cell):
        """A row committed to the ledger on main (the checkout stays where it is)."""
        head = _git(self.repo, "rev-parse", "HEAD")
        _git(self.repo, "checkout", "-q", "main")
        with open(self.repo / PLAN, "a") as fh:
            fh.write(f"| 2026-11-20 | {what} | {cell} |\n")
        _git(self.repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-am", what)
        _git(self.repo, "checkout", "-q", "--detach", head)

    def env(self, live=False, **extra):
        base = {"HOME": str(self.short / "home"), "LH": str(self.lh)}
        mode = ({"LH_SPEND_AUTHORIZED": "yes", "LH_MANIFEST_SHA256": self.label, "LH_RUNTIME_COMMIT": self.commit}
                if live else {"LH_REHEARSAL": str(self.reh)})
        return {**base, **mode, **extra}

    def allowance_inputs(self, env):
        root = self.short / "home" / ".local/state/lh-ladder" if "LH_SPEND_AUTHORIZED" in env else self.reh / "state"
        root.mkdir(parents=True, exist_ok=True)
        with open(root / "allowance.jsonl", "a") as fh:
            fh.write(json.dumps({"kind": "inputs", "at": 0, "f_week": 30, "f_five": 30,
                                 "hours": ["daily 00:00-24:00"]}) + "\n")

    def launch(self, env):
        """`ladder.py launch` run from the copy as its own process; (exit code, stderr)."""
        done = subprocess.run([sys.executable, "-I", str(self.kit / "ladder.py"), "launch"], cwd=self.repo,
                              env=env, capture_output=True, text=True, timeout=WAIT)
        return done.returncode, done.stderr


def _refused(kit, env):
    code, err = kit.launch(env)
    return code, err.split("refused: ", 1)[-1].strip()


# ---- Refusals (Task 5, first checkbox) -------------------------------------------------------------------------


@pytest.fixture
def live_kit(short):
    kit = Kit(short)
    kit.freeze()
    return kit


def test_a_live_launch_with_every_input_right_passes_the_preflight(live_kit):
    """The control for the refusals below: a frozen, labelled, clean, detached checkout with allowance inputs."""
    env = live_kit.env(live=True)
    live_kit.allowance_inputs(env)
    assert live_kit.launch(env) == (0, "")


@pytest.mark.parametrize("unset,value", [("LH_SPEND_AUTHORIZED", None), ("LH_SPEND_AUTHORIZED", "y")])
def test_a_live_launch_without_authorization_is_refused(live_kit, unset, value):
    env = {k: v for k, v in live_kit.env(live=True).items() if k != unset}
    if value:
        env[unset] = value
    assert _refused(live_kit, env)[0] == 3 and "no authorization" in _refused(live_kit, env)[1]


@pytest.mark.parametrize("var", ["LH_MANIFEST_SHA256", "LH_RUNTIME_COMMIT"])
def test_a_manifest_or_runtime_commit_other_than_the_ledgers_is_refused(live_kit, var):
    env = live_kit.env(live=True, **{var: "0" * (64 if var == "LH_MANIFEST_SHA256" else 40)})
    live_kit.allowance_inputs(env)
    assert _refused(live_kit, env)[0] == 3


def test_a_manifest_hash_that_is_not_the_ledgers_current_label_is_refused(live_kit):
    live_kit.ledger_row("Configuration label", f"{'a' * 64} {live_kit.commit} a later label")
    env = live_kit.env(live=True)
    live_kit.allowance_inputs(env)
    code, reason = _refused(live_kit, env)
    assert (code, "not the ledger's current configuration label" in reason) == (3, True)


def test_a_checkout_on_a_branch_is_refused(live_kit):
    _git(live_kit.repo, "checkout", "-q", "-B", "elsewhere", live_kit.commit)
    env = live_kit.env(live=True)
    live_kit.allowance_inputs(env)
    assert "detached checkout" in _refused(live_kit, env)[1]


def test_a_dirty_kit_is_refused(live_kit):
    (live_kit.kit / "README.md").write_text("changed\n")  # not covered by the manifest: only git sees it
    env = live_kit.env(live=True)
    live_kit.allowance_inputs(env)
    assert _refused(live_kit, env) == (3, "the kit has uncommitted changes")


def test_a_live_launch_of_an_unfrozen_manifest_is_refused(short):
    kit = Kit(short)
    env = {**kit.env(live=True, LH_MANIFEST_SHA256="0" * 64, LH_RUNTIME_COMMIT="0" * 40)}
    assert _refused(kit, env) == (3, "the manifest is not frozen")


def test_a_kit_file_changed_since_the_manifest_was_written_is_refused(short):
    kit = Kit(short)
    (kit.kit / "tasks.json").write_text((kit.kit / "tasks.json").read_text() + " ")
    assert _refused(kit, kit.env())[1].startswith("the manifest does not match the kit")


@pytest.mark.parametrize("edit,why", [
    (lambda d: d["attempt"].update(model="claude-sonnet-5-5"), "model"),
    (lambda d: d["attempt"].update(efforts=["low", "medium", "high", "max"]), "efforts"),
    (lambda d: d["harness"].update(model_argument="anthropic/claude-opus-5-5"), "model")])
def test_a_model_or_effort_outside_the_criterion_is_refused(short, edit, why):
    kit = Kit(short, edit=edit)
    env = kit.env()
    kit.allowance_inputs(env)
    assert why in _refused(kit, env)[1]


def test_a_task_whose_package_differs_from_its_digest_is_refused(short):
    kit = Kit(short)
    (kit.lh / "tasks41" / "rs-archive-clone" / "x" / "instruction.md").write_text("changed\n")
    env = kit.env()
    kit.allowance_inputs(env)
    assert _refused(kit, env) == (3, "rs-archive-clone: the package's digest is not its 4.1.0 digest")


def test_a_task_whose_pinned_image_differs_is_refused(short):
    kit = Kit(short)
    path = kit.lh / "tasks41" / "gsea-proteomics" / "x" / "task.toml"
    path.write_text(path.read_text().replace("@sha256:e4", "@sha256:f4"))
    tasks = json.loads((kit.kit / "tasks.json").read_text())  # the digest made to match: only the image differs
    for record in tasks["tasks"]:
        if record["name"].endswith("/gsea-proteomics"):
            record["digest_4_1_0"] = _content_hash(path.parent)
    (kit.kit / "tasks.json").write_text(json.dumps(tasks, indent=1) + "\n")
    _manifest(kit.repo, "write")
    env = kit.env()
    kit.allowance_inputs(env)
    assert _refused(kit, env) == (3, "gsea-proteomics: an image the package pins is not the one tasks.json pins")


def test_a_package_that_already_sets_an_agent_network_key_is_refused(short):
    kit = Kit(short)
    path = kit.lh / "tasks41" / "wal-recovery-ordering" / "x" / "task.toml"
    path.write_text(path.read_text().replace("[agent]\n", '[agent]\nnetwork_mode = "public"\n'))
    tasks = json.loads((kit.kit / "tasks.json").read_text())
    for record in tasks["tasks"]:
        if record["name"].endswith("/wal-recovery-ordering"):
            record["digest_4_1_0"] = _content_hash(path.parent)
    (kit.kit / "tasks.json").write_text(json.dumps(tasks, indent=1) + "\n")
    _manifest(kit.repo, "write")
    env = kit.env()
    kit.allowance_inputs(env)
    assert "already sets an agent-phase network key" in _refused(kit, env)[1]


def test_another_harness_environment_is_refused(short):
    kit = Kit(short)
    (kit.lh / "standin" / "versions.json").write_text(json.dumps({"harbor": "0.26.0", "podman-compose": "1.6.0"}))
    env = kit.env()
    kit.allowance_inputs(env)
    assert _refused(kit, env)[1].startswith("the harness environment is not")


@pytest.mark.parametrize("override", ["containers-override.conf", "limits-compose.yaml"])
@pytest.mark.parametrize("change", ["missing", "changed"])
def test_a_missing_or_changed_host_side_override_is_refused(short, override, change):
    kit = Kit(short)
    path = kit.lh / "logs" / override
    path.unlink() if change == "missing" else path.write_text(path.read_text() + "# more\n")
    env = kit.env()
    kit.allowance_inputs(env)
    assert _refused(kit, env) == (3, f"the host-side override {path} is missing or not the criterion's")


@pytest.mark.parametrize("host", ["10.0.2.2", "127.0.0.1", "::1", "localhost", "host.containers.internal",
                                  "pypi.org:443", "<hostname>"])
def test_an_allowlist_that_names_an_address_of_the_host_is_refused(short, host):
    host = os.uname().nodename if host == "<hostname>" else host
    kit = Kit(short)
    stand_ins = {**STAND_INS, "network.agent_phase.allowed_hosts": ["relay", "pypi.org", host]}
    (kit.reh / "stand_ins.json").write_text(json.dumps(stand_ins))
    env = kit.env()
    kit.allowance_inputs(env)
    assert _refused(kit, env)[1].startswith("the allowlist names an address of the host")


def test_a_task_s_extra_host_that_names_the_host_is_refused(short):
    kit = Kit(short)
    (kit.reh / "stand_ins.json").write_text(json.dumps({**STAND_INS, "tasks.extra_hosts": {"gsea-proteomics": ["10.89.0.1"]}}))
    env = kit.env()
    kit.allowance_inputs(env)
    assert _refused(kit, env)[1].startswith("the allowlist names an address of the host")


@pytest.mark.parametrize("var", ladder.SPEND_VARS)
def test_a_rehearsal_with_a_spend_variable_is_refused(short, var):
    kit = Kit(short)
    env = kit.env(**{var: "yes"})
    assert _refused(kit, env) == (3, f"a rehearsal with a spend variable set ({var})")


def test_the_launcher_refuses_to_hold_the_token_file_s_name(short):
    kit = Kit(short)
    assert _refused(kit, kit.env(LH_TOKEN_FILE="/somewhere/token"))[1].startswith("LH_TOKEN_FILE is set")


def test_a_rehearsal_without_a_stand_in_for_a_pending_field_is_refused(short):
    kit = Kit(short)
    (kit.reh / "stand_ins.json").write_text(json.dumps({k: v for k, v in STAND_INS.items() if k != "host.cpu_set"}))
    assert _refused(kit, kit.env())[1].endswith("for the pending field host.cpu_set")


def test_no_allowance_inputs_is_refused(short):
    kit = Kit(short)
    assert _refused(kit, kit.env())[1].startswith("no allowance inputs")


def test_a_rehearsal_with_every_input_right_passes_the_preflight(short):
    kit = Kit(short)
    env = kit.env()
    kit.allowance_inputs(env)
    assert kit.launch(env) == (0, "")


@pytest.mark.parametrize("token", ["", "lh-fake-slot-", "lh-fake-slot-" + "g" * 32, "real-looking-token",
                                   "lh-fake-slot-" + "0" * 31])
def test_a_slot_without_a_fake_token_in_the_launcher_s_form_is_refused(token):
    assert ladder.token_refusal(token) == "a slot without a fake token in the launcher's form"


def test_the_launcher_s_fake_token_form_is_accepted_and_an_empty_one_ends_before_the_session():
    """What the refusal prevents: with an empty token the harness ends before any stream, naming the switch."""
    empty = json.loads((KIT / "fixtures" / "token-forced-empty-RuntimeError.json").read_text())
    assert (ladder.token_refusal("lh-fake-slot-" + "0a" * 16), empty["n_events"],
            "CLAUDE_FORCE_OAUTH" in empty["exception_message"]) == (None, 0, True)


# ---- Money (Task 5, second checkbox) ---------------------------------------------------------------------------

CRITERION = json.loads((KIT / "ladder.json").read_text())


def _entry(task="wal-recovery-ordering", effort="low", rnd=1, kind="round"):
    return {"round": rnd, "task": task, "effort": effort, "kind": kind}


def _root(short):
    root = short / "state"
    ladder.ensure_state(root)
    return root


RESERVE = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lh_ladder", sys.argv[1])
ladder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ladder)
root, n = ladder.Path(sys.argv[2]), int(sys.argv[3])
entry = {"round": n, "task": "wal-recovery-ordering", "effort": ("low", "medium", "high")[n % 3], "kind": "round"}
got = ladder.reserve(root, entry, json.loads((ladder.KIT / "ladder.json").read_text()), 0.0)
print(json.dumps(got if isinstance(got, dict) else got.reason))
"""


def test_sixty_concurrent_launches_never_commit_more_than_the_ceiling(short):
    """Sixty launcher processes reserve at once; each reservation is wal-recovery-ordering's cap plus the margin,
    USD 4.00, so exactly 50 fit in USD 200."""
    root = _root(short)
    procs = [subprocess.Popen([sys.executable, "-I", "-c", RESERVE, str(KIT / "ladder.py"), str(root), str(n)],
                              stdout=subprocess.PIPE, text=True) for n in range(60)]
    results = [json.loads(proc.communicate(timeout=WAIT * 3)[0]) for proc in procs]
    starts, committed, open_ = ladder.tally(root, CRITERION, 0.0)
    slots = json.loads((root / "passthrough" / "slots.json").read_text())
    reserved = [r for r in results if isinstance(r, dict)]
    assert (len(reserved), starts, committed, len(open_), len({r["id"] for r in reserved}),
            len(set(slots["slots"])), {r for r in results if not isinstance(r, dict)}) == (
        50, 50, 200.0, 50, 50, 50, {"does not fit"})


def test_a_slot_that_does_not_fit_waits_and_a_cheaper_one_behind_it_is_never_started(short):
    root = _root(short)
    held = ladder.reserve(root, _entry("vf2-speedup-networkx"), CRITERION, 170.0)  # 18.37 of the 30 left
    queue = [_entry("rs-archive-clone"), _entry("wal-recovery-ordering")]  # 23.92 does not fit, 4.00 would
    waiting = ladder.next_start(root, queue, CRITERION, 170.0)
    ladder.settle(root, held, {"usd": 18.37, "class": "observation"})
    ended = ladder.next_start(root, queue, CRITERION, 170.0)
    starts, _, open_ = ladder.tally(root, CRITERION, 170.0)
    assert (waiting[0], ended[0], ended[1], starts, open_) == (
        "wait", "end", "nothing in flight and the next slot's reservation does not fit", 1, [])


def test_the_head_of_the_queue_starts_when_it_fits(short):
    root = _root(short)
    action, attempt = ladder.next_start(root, [_entry("rs-archive-clone")], CRITERION, 0.0)
    record = json.loads((root / "slots" / attempt["id"] / "slot.json").read_text())
    assert (action, record["reservation_usd"], record["cap_usd"], bool(ladder.FAKE_TOKEN.fullmatch(record["token"])),
            record["launcher"]["pid"], record["launcher"]["start"] == ladder.process_start(os.getpid())) == (
        "start", 23.92, 22.92, True, os.getpid(), True)


@pytest.mark.parametrize("kind", ["round", "rerun after a cut"])
def test_start_241_is_refused(short, kind):
    root = _root(short)
    for n in range(240):
        ladder.settle(root, ladder.reserve(root, _entry(rnd=n), CRITERION, 0.0), {"usd": 0.01, "class": "observation"})
    head = {**_entry(), "rerun_of": "001"} if kind != "round" else _entry()
    assert ladder.next_start(root, [head], CRITERION, 0.0) == ("end", "240 starts")


def test_a_pre_session_failure_counts_against_neither_the_starts_nor_the_ceiling(short):
    root = _root(short)
    ladder.settle(root, ladder.reserve(root, _entry(), CRITERION, 0.0), {"usd": 0.0, "class": "pre_session_failure"})
    ladder.settle(root, ladder.reserve(root, _entry(), CRITERION, 0.0), {"usd": 0.5, "class": "cut"})
    starts, committed, _ = ladder.tally(root, CRITERION, 0.0)
    assert (starts, committed) == (1, 0.5)


def test_a_settled_slot_leaves_the_slots_file_and_its_token_is_retired(short):
    root = _root(short)
    one, two = (ladder.reserve(root, _entry(rnd=n), CRITERION, 0.0) for n in (1, 2))
    ladder.settle(root, one, {"usd": 0.1, "class": "observation"})
    slots = json.loads((root / "passthrough" / "slots.json").read_text())
    assert ({name: s["token"] for name, s in slots["slots"].items()}, slots["total_usd"]) == (
        {two["id"]: two["token"]}, 200.0)


def test_the_live_probe_s_priced_usage_is_settled_into_committed_and_off_the_passthrough_s_total(short):
    root = _root(short)
    attempt = ladder.reserve(root, _entry(), CRITERION, 0.37)
    slots = json.loads((root / "passthrough" / "slots.json").read_text())
    assert (ladder.tally(root, CRITERION, 0.37)[1], slots["total_usd"], attempt["reservation_usd"]) == (
        4.37, 199.63, 4.0)


def test_a_live_launch_without_the_live_probe_s_request_log_is_refused(short):
    ctx = ladder.Ctx({"HOME": str(short), "LH_SPEND_AUTHORIZED": "yes"})
    with pytest.raises(ladder.Refused, match="live probe"):
        ladder.prior_usd(ctx)


def test_the_live_probe_s_usage_is_read_from_its_request_log(short):
    log = short / ".local/state/lh-probe/passthrough/requests.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("".join(json.dumps(r) + "\n" for r in [{"slot": "probe-low", "usd": 0.01},
                                                         {"slot": None, "status": 403, "refused": "x"},
                                                         {"slot": "probe-medium", "usd": 0.02}]))
    assert round(ladder.prior_usd(ladder.Ctx({"HOME": str(short), "LH_SPEND_AUTHORIZED": "yes"})), 9) == 0.03


# Settlement: the largest of four figures (D4).

def _usage(inp, out, read=0, write=0):
    return {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read,
            "cache_creation_input_tokens": write}


def _trial(attempt_dir, result=None, session=None, stream_extra=()):
    """A harness trial in the attempt's job directory: its stream (the last line `result`) and session file."""
    trial = attempt_dir / "jobs" / attempt_dir.name / "wal-recovery-ordering__abcdefg"
    (trial / "agent" / "sessions" / "projects" / "-app").mkdir(parents=True)
    lines = [{"type": "system", "subtype": "init"}, *stream_extra] + ([{"type": "result", **result}] if result else [])
    (trial / "agent" / "claude-code.txt").write_text("".join(json.dumps(e) + "\n" for e in lines))
    if session is not None:
        (trial / "agent" / "sessions" / "projects" / "-app" / "s.jsonl").write_text(
            "".join((s if isinstance(s, str) else json.dumps(s)) + "\n" for s in session))
    return trial


def _assistant(mid, usage):
    return {"type": "assistant", "message": {"id": mid, "model": "claude-haiku-5-5", "usage": usage}}


def _model_usage(inp, out):
    return {"claude-haiku-5-5": {"inputTokens": inp, "outputTokens": out, "cacheReadInputTokens": 0,
                                 "cacheCreationInputTokens": 0}}


PRICE = ladder.price_check.price


def _figures_case(short, which):
    """Four figures, each made the largest in turn: (attempt dir, rows, the figure that must settle)."""
    root = _root(short)
    attempt = ladder.reserve(root, _entry(), CRITERION, 0.0)
    big = {"meter": 0, "session": 0, "result": 0, "model_usage": 0, which: 1}
    session = [_assistant("m1", _usage(1000 + 9000 * big["session"], 100))]
    result = {"total_cost_usd": 0.0002 + 0.01 * big["result"], "modelUsage": _model_usage(1000 + 50_000 * big["model_usage"], 100),
              "usage": _usage(10 ** 9, 10 ** 9)}  # never read: it would dwarf every figure
    _trial(root / "slots" / attempt["id"], result, session)
    rows = [{"slot": attempt["id"], "status": 200, "usd": 0.00015 + 0.02 * big["meter"]}]
    want = {"meter": rows[0]["usd"], "session": PRICE(session[0]["message"]["usage"], ladder.RULE),
            "result": result["total_cost_usd"], "model_usage": (1000 + 50_000) * 0.10 / 1e6 + 100 * 0.50 / 1e6}
    return root / "slots" / attempt["id"], rows, want[which]


@pytest.mark.parametrize("which", ["meter", "session", "result", "model_usage"])
def test_settlement_takes_the_largest_of_four_figures_and_never_reads_the_result_s_usage(short, which):
    attempt_dir, rows, want = _figures_case(short, which)
    settled = ladder.settlement(attempt_dir, rows, 4.0)
    assert (round(settled["usd"], 12), settled["unreadable"]) == (round(want, 12), [])


def test_settlement_counts_a_message_id_once(short):
    root = _root(short)
    attempt = ladder.reserve(root, _entry(), CRITERION, 0.0)
    one = _assistant("m1", _usage(5000, 500))
    _trial(root / "slots" / attempt["id"], {"total_cost_usd": 0.0}, [one, one, one, _assistant("m2", _usage(10, 1))])
    settled = ladder.settlement(root / "slots" / attempt["id"], [], 4.0)
    assert settled["figures"]["session"] == pytest.approx(PRICE(_usage(5000, 500), ladder.RULE)
                                                          + PRICE(_usage(10, 1), ladder.RULE), rel=1e-12)


@pytest.mark.parametrize("broken", ["session line", "stream line", "passthrough row"])
def test_unreadable_usage_settles_at_the_full_reservation(short, broken):
    root = _root(short)
    attempt = ladder.reserve(root, _entry(), CRITERION, 0.0)
    session = [_assistant("m1", _usage(10, 1))] + (["{not json"] if broken == "session line" else [])
    trial = _trial(root / "slots" / attempt["id"], {"total_cost_usd": 0.0001}, session)
    if broken == "stream line":
        with open(trial / "agent" / "claude-code.txt", "a") as fh:
            fh.write("{not json\n{\"type\": \"x\"}\n")
    rows = [{"slot": attempt["id"], "status": 200, "usd": "unpriced" if broken == "passthrough row" else 0.0001}]
    settled = ladder.settlement(root / "slots" / attempt["id"], rows, attempt["reservation_usd"])
    assert (settled["usd"], bool(settled["unreadable"])) == (4.0, True)


def test_a_session_with_no_trial_is_settled_by_the_meter_alone(short):
    """A timeout kill or a dead launcher leaves no result event; figure 1 settles it (D4)."""
    root = _root(short)
    attempt = ladder.reserve(root, _entry(), CRITERION, 0.0)
    rows = [{"slot": attempt["id"], "status": 200, "usd": 0.25}, {"slot": attempt["id"], "status": 403, "refused": "x"}]
    assert ladder.settlement(root / "slots" / attempt["id"], rows, 4.0) == {
        "usd": 0.25, "figures": {"meter": 0.25, "session": None, "result": None, "model_usage": None}, "unreadable": []}


# ---- Classification (Task 5, third checkbox) -------------------------------------------------------------------

criterion_tests = _load("lh_criterion_tests", REPO / "tests" / "experiments" / "test_long_horizon_ladder.py")


def _replay(fx, trial, started="2026-11-20T10:00:00Z", finished="2026-11-20T10:30:00Z"):
    """A harness trial as Harbor writes it, from a cut fixture: result.json (absent for no harness result) and the
    stream with the fixture's init event, its count of events and of api_retry events, and its last events."""
    (trial / "agent").mkdir(parents=True, exist_ok=True)
    exc = fx.get("harness_exception")
    info = {"exception_type": exc, "exception_message": fx.get("exception_message") or ""} if exc else None
    (trial / "result.json").write_text(json.dumps({
        "exception_info": info, "agent_result": fx.get("agent_result"), "verifier_result": fx.get("verifier_result"),
        "agent_execution": {"started_at": started, "finished_at": finished}}))
    if fx["n_events"]:
        tail = fx["stream_tail"]
        head = [fx["init"]] if fx.get("init") and fx["init"] not in tail else []
        retries = fx["n_api_retry"] - sum(e.get("subtype") == "api_retry" for e in head + tail)
        filler = max(fx["n_events"] - len(head) - len(tail) - retries, 0)
        events = head + [{"type": "system", "subtype": "api_retry"}] * retries + [{"type": "user"}] * filler + tail
        (trial / "agent" / "claude-code.txt").write_text("".join(json.dumps(e) + "\n" for e in events))
    return trial


def _attempt_dir(short, name="001-r1-wal-recovery-ordering-low"):
    path = short / "state" / "slots" / name
    path.mkdir(parents=True)
    return path


def _launcher_session(short, fixture, rows, ended_at):
    attempt_dir = _attempt_dir(short)
    _replay(json.loads((KIT / "fixtures" / f"{fixture}.json").read_text()) if isinstance(fixture, str) else fixture,
            attempt_dir / "jobs" / attempt_dir.name / "wal-recovery-ordering__abcdefg")
    return ladder.session_of(attempt_dir, rows, ended_at, "s")


def test_every_fixture_read_from_a_harness_trial_is_classified_into_its_row_by_the_shared_reader(short):
    """The launcher's own path: each session fixture replayed into a harness trial directory and read back by
    session_of, with the criterion's stand-in passthrough rows, lands in the row that cites it or that its name says
    (the criterion test's expectation, test_long_horizon_ladder.py)."""
    cited = {f: row["row"] for row in CRITERION["classification"]["rows"] for f in row["fixtures"]}
    got, want = {}, {}
    for n, name in enumerate(criterion_tests.SESSIONS):
        fx = criterion_tests._fixture(name)
        rows = criterion_tests._session_rows(fx)
        attempt_dir = _attempt_dir(short, f"{n:03d}")
        _replay(fx, attempt_dir / "jobs" / "j" / "t__abcdefg")
        got[name] = ladder.classify(ladder.session_of(attempt_dir, rows, len(rows), "s"), CRITERION)
        want[name] = cited.get(name, criterion_tests._named_row(name))
    assert (len(got), {n: (got[n], want[n]) for n in got if got[n] != want[n]}) == (73, {})


def test_endings_that_share_a_harness_class_are_told_apart(short):
    rows_by_class = {}
    for n, name in enumerate(criterion_tests.SESSIONS):
        fx = criterion_tests._fixture(name)
        rows = criterion_tests._session_rows(fx)
        attempt_dir = _attempt_dir(short, f"{n:03d}")
        _replay(fx, attempt_dir / "jobs" / "j" / "t__abcdefg")
        row = ladder.classify(ladder.session_of(attempt_dir, rows, len(rows), "s"), CRITERION)
        rows_by_class.setdefault(fx["harness_exception"], set()).add(row)
    assert (rows_by_class["UnknownApiError"] >= {11, 12, 13, 14, 15},
            rows_by_class["NonZeroAgentExitCodeError"] >= {6, 7, 10}) == (True, True)


SIGNAL_1 = {"anthropic-ratelimit-unified-status": "rejected"}


@pytest.mark.parametrize("fixture", ["token-three-tools-normal-end", "stub-budget-stop-NonZeroAgentExitCodeError",
                                     "stub-refusal-AgentSafetyRefusalError", "passthrough-cap-UnknownApiError"])
def test_a_slot_whose_log_holds_signal_1_before_the_ending_is_cut_whatever_the_cli_s_result_says(short, fixture):
    rows = [{"time": 1, "slot": "s", "status": 429, "headers": SIGNAL_1},
            {"time": 2, "slot": "s", "status": 403, "refused": "slot cap reached"}]
    row = ladder.classify(_launcher_session(short, fixture, rows, 5), CRITERION)
    assert (row, CRITERION["classification"]["rows"][row - 1]["class"]) == (10, "cut")


def test_a_usage_limit_met_only_after_the_ending_leaves_a_time_limit_session_in_its_own_row(short):
    rows = [{"time": 1, "slot": "s", "status": 200}, {"time": 9, "slot": "s", "status": 429, "headers": SIGNAL_1}]
    assert ladder.classify(_launcher_session(short, "stub-timeout-AgentTimeoutError", rows, 5), CRITERION) == 3


def test_a_session_with_signal_2_alone_pauses(short):
    rows = [{"time": 1, "slot": "s", "status": 429}]  # the CLI says usage limit; the vendor's answer does not
    assert ladder.classify(_launcher_session(short, "token-usage-limit-NonZeroAgentExitCodeError", rows, 5),
                           CRITERION) == 16


def test_a_session_whose_stream_cannot_be_read_pauses_rather_than_reading_as_before_a_session(short):
    attempt_dir = _attempt_dir(short)
    trial = _replay(criterion_tests._fixture("token-three-tools-normal-end"), attempt_dir / "jobs" / "j" / "t__a")
    with open(trial / "agent" / "claude-code.txt", "a") as fh:
        fh.write("{cut\n{}\n")
    assert ladder.session_of(attempt_dir, [], None, "s") is None


# Closing an attempt: its row, class, reward and what happens to its slot.

def _state(short):
    root = short / "state"
    ladder.ensure_state(root)
    return root


def _ctx(short, lh=None):
    reh = short / "reh"
    reh.mkdir(exist_ok=True)
    return ladder.Ctx({"HOME": str(short / "home"), "LH": str(lh or short / "lh"), "LH_REHEARSAL": str(reh)})


def _closed(short, fixture, rows, entry=None, reward=None):
    """Reserve an attempt, replay `fixture` as its trial, log `rows` for its slot and close it."""
    ctx = _ctx(short)
    root = ctx.root
    ladder.ensure_state(root)
    attempt = ladder.reserve(root, entry or _entry(), CRITERION, 0.0)
    fx = json.loads((KIT / "fixtures" / f"{fixture}.json").read_text())
    if reward is not None:
        fx = {**fx, "verifier_result": {"rewards": {"reward": reward}}}
    _replay(fx, root / "slots" / attempt["id"] / "jobs" / attempt["id"] / "wal-recovery-ordering__abcdefg")
    now = attempt["opened"]
    with open(root / "passthrough" / "requests.jsonl", "a") as fh:
        for i, row in enumerate(rows):
            fh.write(json.dumps({"time": now + 0.001 * (i + 1), "slot": attempt["id"], **row}) + "\n")
    record = ladder.close(ctx, root, attempt, CRITERION, 0.0, ended_at=now + 1)
    return root, attempt, record


def test_a_cut_slot_is_run_again_at_the_head_of_the_queue_as_a_new_counted_start_and_its_reward_is_never_read(short):
    first, second = _entry(rnd=1), _entry(rnd=2)
    root, attempt, record = _closed(short, "token-three-tools-normal-end",
                                    [{"status": 429, "headers": SIGNAL_1, "usd": 0.01}], entry=second, reward=1.0)
    queue = ladder.queue(root, [first, second])
    starts, committed, _ = ladder.tally(root, CRITERION, 0.0)
    assert ((record["row"], record["class"], record["reward"]), queue[0]["round"], queue[0]["rerun_of"],
            [e["round"] for e in queue], starts, committed) == (
        (10, "cut", None), 2, attempt["id"], [2, 1], 1, 0.01)


@pytest.mark.parametrize("fixture,rows,cls", [
    ("token-three-tools-normal-end", [], "observation"),
    ("stub-budget-stop-NonZeroAgentExitCodeError", [], "observation"),
    ("stub-overloaded-UnknownApiError", [], "infrastructure_failure"),
    ("passthrough-model-UnknownApiError", [{"status": 403, "refused": "model not allowed"}], "stop"),
    ("token-usage-limit-NonZeroAgentExitCodeError", [{"status": 429}], "ruling")])  # signal 2 alone: row 16
def test_a_slot_whose_session_ended_in_any_other_way_is_never_launched_again(short, fixture, rows, cls):
    root, _, record = _closed(short, fixture, rows, reward=0.0)
    assert (record["class"], ladder.queue(root, [_entry()])) == (cls, [])


def test_an_observation_takes_the_verifier_s_reward_and_zero_when_the_verifier_gives_none(short):
    (short / "a").mkdir()
    (short / "b").mkdir()
    _, _, with_reward = _closed(short / "a", "stub-budget-stop-NonZeroAgentExitCodeError", [], reward=1.0)
    _, _, without = _closed(short / "b", "stub-timeout-AgentTimeoutError", [])
    assert (with_reward["reward"], with_reward["flagged"], without["row"], without["reward"]) == (1.0, True, 3, 0.0)


def test_a_stop_row_stops_the_tranche_and_a_row_16_ending_pauses_it(short):
    (short / "a").mkdir()
    (short / "b").mkdir()
    stop_root, stopped, _ = _closed(short / "a", "passthrough-model-UnknownApiError",
                                    [{"status": 403, "refused": "model not allowed"}])
    pause_root, paused, _ = _closed(short / "b", "token-usage-limit-NonZeroAgentExitCodeError", [{"status": 429}])
    events = [ladder._jsonl(root / "passthrough" / "tranche.jsonl")[-1] for root in (stop_root, pause_root)]
    assert [(e["event"], e["slot"], e["reason"]) for e in events] == [
        ("stop", stopped["id"], "D5 row 13"), ("pause", paused["id"], "D5 row 16")]


def test_a_pre_session_failure_is_relaunched_at_most_twice_and_the_slot_is_lost_after_the_third(short):
    ctx = _ctx(short)
    root = ctx.root
    ladder.ensure_state(root)
    fx = criterion_tests._fixture("pre-session-agent-install-RuntimeError")
    seen = []
    for _ in range(3):
        head = ladder.queue(root, [_entry()])
        seen.append([e.get("rerun_of") for e in head])
        attempt = ladder.reserve(root, head[0], CRITERION, 0.0)
        _replay(fx, root / "slots" / attempt["id"] / "jobs" / attempt["id"] / "wal-recovery-ordering__abcdefg")
        ladder.close(ctx, root, attempt, CRITERION, 0.0)
    ids = [a["id"] for a in ladder.attempts(root)]
    assert (seen, ladder.queue(root, [_entry()]), ladder.lost(root, [_entry()]), ladder.tally(root, CRITERION, 0.0)[:2]) == (
        [[None], [ids[0]], [ids[1]]], [], [_entry()], (0, 0.0))


def test_the_launcher_stops_the_tranche_at_an_init_event_with_another_tool_list_version_or_credential_source(short):
    fx = criterion_tests._fixture("token-three-tools-normal-end")
    bad = [{**fx, "init": {**fx["init"], "tools": ["Bash", "Edit", "Read", "Write"]}},
           {**fx, "init": {**fx["init"], "claude_code_version": "2.1.312"}},
           {**fx, "init": {**fx["init"], "apiKeySource": "ANTHROPIC_API_KEY"}}, fx]
    reasons = []
    for n, case in enumerate(bad):
        attempt_dir = _attempt_dir(short, f"{n:03d}")
        _replay(case, attempt_dir / "jobs" / "j" / "t__abcdefg")
        reasons.append(ladder.init_stop(ladder.stream_events(ladder.trial_dir(attempt_dir)), CRITERION))
    assert reasons == ["an init event with another tool list", "an init event with another CLI version",
                       "an init event with another credential source", None]


def test_a_subagent_file_is_a_stop(short):
    attempt_dir = _attempt_dir(short)
    trial = _replay(criterion_tests._fixture("token-three-tools-normal-end"), attempt_dir / "jobs" / "j" / "t__a")
    sub = trial / "agent" / "sessions" / "projects" / "-app" / "sess" / "subagents"
    sub.mkdir(parents=True)
    before = ladder.subagent_files(trial)
    (sub / "agent-1.jsonl").write_text("{}\n")
    assert (before, [p.name for p in ladder.subagent_files(trial)]) == ([], ["agent-1.jsonl"])


# Regrade (D5): verifier only, no model call.

def _calls(lh):
    path = lh / "standin" / "calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.mark.parametrize("outcomes,want", [
    ([{"reward": 1.0}], ("observation", 1.0, 1)),
    ([{"exception": "RewardFileNotFoundError"}, {"reward": 0.0}], ("observation", 0.0, 2)),
    ([{"exception": "VerifierTimeoutError"}, {"exception": "VerifierTimeoutError"}], ("observation", 0.0, 2)),
    ([{"exception": "RewardFileNotFoundError"}, {"exception": "RewardFileNotFoundError"}],
     ("infrastructure_failure", None, 2))])
def test_no_reward_after_a_normal_ending_is_regraded_twice_at_most_and_a_regrade_never_starts_the_agent(
        short, outcomes, want):
    lh = _cache(short, json.loads((KIT / "tasks.json").read_text())["tasks"])
    (lh / "standin" / "regrade.json").write_text(json.dumps({"wal-recovery-ordering__abcdefg": outcomes}))
    root, attempt, record = _closed(short, "token-three-tools-normal-end", [])
    ctx = _ctx(short, lh)
    record = ladder.regraded(ctx, CRITERION, attempt, record, gate=lambda: True)
    calls = _calls(lh)
    agent_args = {"run", "--agent", "-m", "--ak", "--ae", "--effort", "--base-url"}
    assert ((record["class"], record["reward"], len(calls)),
            {c["argv"][1] + " " + c["argv"][2] for c in calls}, [agent_args & set(c["argv"]) for c in calls],
            [k for c in calls for k in c["env"] if k.startswith(("CLAUDE", "LH_", "ANTHROPIC"))]) == (
        want, {"trial regrade"}, [set()] * len(calls), [])


def test_a_load_sensitive_task_s_zero_under_load_is_regraded_once_below_the_gate(short):
    lh = _cache(short, json.loads((KIT / "tasks.json").read_text())["tasks"])
    (lh / "standin" / "regrade.json").write_text(json.dumps({"wal-recovery-ordering__abcdefg": [{"reward": 1.0}]}))
    criterion = {**CRITERION, "tasks": {**CRITERION["tasks"], "load_sensitive": ["wal-recovery-ordering"]}}
    root, attempt, record = _closed(short, "stub-budget-stop-NonZeroAgentExitCodeError", [], reward=0.0)
    quiet = ladder.regraded(_ctx(short, lh), criterion, attempt, {**record, "verifier_load_above_gate": False},
                            gate=lambda: True)
    loud = ladder.regraded(_ctx(short, lh), criterion, attempt, {**record, "verifier_load_above_gate": True},
                           gate=lambda: True)
    assert ((quiet["reward"], loud["reward"], loud["regrades"]), len(_calls(lh))) == ((0.0, 1.0, 1), 1)


# Reconcile: only a dead launcher's attempts are stopped and removed.

def _container(lh, name, **fields):
    (lh / "standin" / "podman" / "containers" / f"{name}.json").write_text(json.dumps({"running": True, **fields}))


def _containers(lh):
    return sorted(p.stem for p in (lh / "standin" / "podman" / "containers").glob("*.json"))


def test_reconcile_stops_only_the_containers_of_a_dead_launcher_whose_pid_and_start_time_both_match(short):
    lh = _cache(short, json.loads((KIT / "tasks.json").read_text())["tasks"])
    ctx = _ctx(short, lh)
    root = ctx.root
    ladder.ensure_state(root)
    me, start = os.getpid(), ladder.process_start(os.getpid())
    sleepers = [subprocess.Popen(["sleep", "300"], start_new_session=True) for _ in range(2)]
    owners = {"alive": (me, start), "pid reused": (me, start + 1), "gone": (2 ** 22 + 7, 1)}
    harness = {"alive": None, "pid reused": (sleepers[0].pid, ladder.process_start(sleepers[0].pid)),
               "gone": (sleepers[1].pid, ladder.process_start(sleepers[1].pid) + 1)}  # the second: a reused pid
    for n, (name, owner) in enumerate(owners.items()):
        attempt = ladder.reserve(root, _entry(rnd=n), CRITERION, 0.0)
        record = {**attempt, "launcher": {"pid": owner[0], "start": owner[1]}}
        if harness[name]:
            record["harness"] = {"pid": harness[name][0], "start": harness[name][1]}
        ladder._write_json(root / "slots" / attempt["id"] / "slot.json", record)
        trial = root / "slots" / attempt["id"] / "jobs" / attempt["id"] / f"Trial{n}__abcdefg"
        trial.mkdir(parents=True)
        _container(lh, f"trial{n}__abcdefg__env_main_1")
    ladder.reconcile(ctx, CRITERION, 0.0)
    states = [s.poll() for s in sleepers]
    for s in sleepers:
        s.kill()
        s.wait()
    settled = {a["id"].split("-", 1)[0]: a["settled"] and a["settled"]["class"] for a in ladder.attempts(root)}
    assert (_containers(lh), settled, states[0] is not None, states[1]) == (
        ["trial0__abcdefg__env_main_1"], {"001": None, "002": "infrastructure_failure", "003": "infrastructure_failure"},
        True, None)


# ---- Allowance (Task 5, fourth checkbox) -----------------------------------------------------------------------

def _events_file(root, *events):
    with open(root / "passthrough" / "tranche.jsonl", "a") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")


def _limit(at, reset):
    return {"time": at, "event": "close_starts", "slot": "x", "status": 429, "reason": "usage limit", "reset": reset}


def test_a_limit_answer_closes_all_starts_and_they_reopen_five_minutes_after_its_reset_with_one_start(short):
    root = _state(short)
    _events_file(root, _limit(900.0, "1000"))
    before, at_reset = ladder.starts_gate(root, 1299.0), ladder.starts_gate(root, 1301.0)
    attempt = ladder.reserve(root, _entry(), CRITERION, 0.0)
    record = {**attempt, "opened": 1302.0}
    ladder._write_json(root / "slots" / attempt["id"] / "slot.json", record)
    unanswered = ladder.starts_gate(root, 1305.0)
    with open(root / "passthrough" / "requests.jsonl", "a") as fh:
        fh.write(json.dumps({"time": 1310.0, "slot": attempt["id"], "status": 200, "usd": 0.001}) + "\n")
    answered = ladder.starts_gate(root, 1311.0)
    assert [(g["open"], g["most"]) for g in (before, at_reset, unanswered, answered)] == [
        (False, 0), (True, 1), (False, 0), (True, None)]


@pytest.mark.parametrize("event", [_limit(900.0, None),
                                   {"time": 900.0, "event": "close_starts", "reason": "vendor 429", "reset": None},
                                   {"time": 900.0, "event": "close_starts", "reason": "passthrough down", "reset": None},
                                   {"time": 900.0, "event": "close_starts", "reason": "usage incomplete", "reset": None}])
def test_an_answer_with_no_reset_pauses_until_a_person_resumes(short, event):
    root = _state(short)
    _events_file(root, event)
    paused = ladder.starts_gate(root, 10 ** 9)
    _events_file(root, {"time": 1000.0, "event": "resume", "by": "a test"})
    assert ((paused["open"], paused["kind"]), ladder.starts_gate(root, 10 ** 9)["open"]) == ((False, "pause"), True)


def test_three_limit_answers_in_a_row_stop_the_tranche_and_an_observation_between_them_resets_the_count(short):
    (short / "a").mkdir()
    (short / "b").mkdir()
    roots = [_state(short / "a"), _state(short / "b")]
    for root in roots:  # three limits, each reopened before the next; a second answer inside one counts once
        _events_file(root, _limit(100.0, "200"), _limit(101.0, "200"), _limit(600.0, "700"))
    attempt = ladder.reserve(roots[1], _entry(), CRITERION, 0.0)
    ladder._write_json(roots[1] / "slots" / attempt["id"] / "slot.json", {**attempt, "opened": 640.0})
    ladder._write_json(roots[1] / "slots" / attempt["id"] / "settled.json",
                       {"class": "observation", "usd": 0.1, "closed": 650.0})
    for root in roots:
        _events_file(root, _limit(1100.0, "1200"))
        ladder.check_limits(root, CRITERION, now=1150.0)
    gates = [ladder.starts_gate(root, 10 ** 9) for root in roots]
    assert ([(g["open"], g["kind"]) for g in gates], gates[0]["why"]) == (
        [(False, "stop"), (True, None)], "three usage-limit answers in a row with no observation between them")


def test_a_sign_of_paid_extra_usage_in_a_session_s_stream_stops_the_tranche(short):
    paid = criterion_tests._fixture("token-paid-extra-usage-normal-end")
    clean = criterion_tests._fixture("token-three-tools-normal-end")
    reasons = [ladder.stream_stop(e) for fx in (paid, clean) for e in fx["stream_tail"] + [fx["init"]]]
    root, attempt, record = _closed(short, "token-paid-extra-usage-normal-end", [])
    assert ([r for r in reasons if r], record["class"], ladder.starts_gate(root, 10 ** 9)["kind"]) == (
        ["a sign of paid extra usage in the session's stream"], "stop", "stop")


# The guard reads the owner's meter.

DAY = 24 * 3600


def _local(text):
    """Epoch seconds of a local time 'YYYY-MM-DD HH:MM' (the owner's hours are local)."""
    import datetime
    return datetime.datetime.strptime(text, "%Y-%m-%d %H:%M").astimezone().timestamp()


def _allowance(root, *rows):
    with open(root / "allowance.jsonl", "a") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


INPUTS = {"kind": "inputs", "at": 0, "f_week": 30, "f_five": 20, "hours": ["mon-fri 09:00-18:00"],
          "closing_margin_h": 2}
FIGURES = {"kind": "figures", "at": 0, "weekly_usd_per_point": 2.0, "five_usd_per_point": 0.5,
           "reservation_raise": 1.0}


def _reading(at, weekly=10, five=5, weekly_reset=None, five_reset=None):
    return {"kind": "reading", "at": at, "weekly": weekly, "five": five,
            "weekly_reset": weekly_reset or at + 5 * DAY, "five_reset": five_reset or at + 4 * 3600}


WED_10 = "2026-11-18 10:00"  # a Wednesday


def _guard(root, now, entry=None):
    return ladder.guard(root, CRITERION, entry or _entry("wal-recovery-ordering"), _local(now) if isinstance(now, str) else now)


def test_no_start_in_a_window_that_has_no_meter_reading(short):
    root = _state(short)
    _allowance(root, INPUTS, FIGURES, _reading(_local("2026-11-17 08:00")))  # Tuesday's window, not Wednesday's
    stale, = [_guard(root, WED_10)]
    _allowance(root, _reading(_local("2026-11-18 08:30")))
    assert (stale[:2], _guard(root, WED_10)[0]) == ((False, "no meter reading for this window"), True)


def test_a_reading_taken_inside_the_window_counts_for_it_and_one_past_its_weekly_reset_does_not(short):
    root = _state(short)
    _allowance(root, INPUTS, FIGURES, _reading(_local("2026-11-18 09:30"), weekly_reset=_local("2026-11-18 11:00")))
    assert (_guard(root, WED_10)[0], _guard(root, "2026-11-18 11:30")[:2]) == (
        True, (False, "no meter reading for this window"))


def test_no_start_outside_the_owner_s_hours_or_in_a_window_s_closing_margin(short):
    root = _state(short)
    _allowance(root, INPUTS, FIGURES, _reading(_local("2026-11-18 08:00")), _reading(_local("2026-11-21 08:00")))
    assert [_guard(root, t)[:2] for t in ("2026-11-18 08:59", "2026-11-18 16:01", "2026-11-18 15:59",
                                          "2026-11-21 10:00")] == [
        (False, "outside the owner's hours"), (False, "in the window's closing margin"), (True, None),
        (False, "outside the owner's hours")]


@pytest.mark.parametrize("reading,figures,want", [
    ({"weekly": 10, "five": 5}, FIGURES, (120.0, 37.5)),
    ({"weekly": 80, "five": 90}, FIGURES, (0.0, 0.0)),
    ({"weekly": 10, "five": 5}, {**FIGURES, "five_usd_per_point": None}, (120.0, None))])
def test_the_budgets_are_computed_from_the_reading_and_floored_at_zero(reading, figures, want):
    assert ladder.budgets(INPUTS, reading, figures) == want


def test_a_window_whose_weekly_reading_is_at_or_above_the_skip_threshold_is_skipped_and_reported(short):
    (short / "a").mkdir()
    (short / "b").mkdir()
    at, below = _state(short / "a"), _state(short / "b")
    _allowance(at, INPUTS, FIGURES, _reading(_local("2026-11-18 08:00"), weekly=65))  # 100 - 30 - 5
    _allowance(below, INPUTS, FIGURES, _reading(_local("2026-11-18 08:00"), weekly=64))
    assert (_guard(at, WED_10), _guard(below, WED_10)[0]) == (
        (False, "window skipped: the weekly reading 65 leaves fewer than 5 points above F-week 30", None), True)


def test_starts_wait_for_the_five_hour_reset_when_its_reading_is_at_or_above_its_threshold(short):
    root = _state(short)
    _allowance(root, INPUTS, FIGURES,
               _reading(_local("2026-11-18 08:00"), five=75, five_reset=_local("2026-11-18 12:00")))
    assert (_guard(root, WED_10)[:2], _guard(root, "2026-11-18 12:01")[0]) == (
        (False, "waiting for the five-hour meter's reset"), True)


def _spent(root, at, usd):
    with open(root / "passthrough" / "requests.jsonl", "a") as fh:
        fh.write(json.dumps({"time": at, "slot": "earlier", "status": 200, "usd": usd}) + "\n")


def test_no_start_when_the_weekly_budget_does_not_hold_the_guard_s_reservation_of_every_open_slot_and_this_one(short):
    """Weekly budget (100 - 30 - 10) x 2.00 = 120.00. Open: rs-archive-clone (22.92 / 3 = 7.64); this one:
    wal-recovery-ordering (1.00). Usage since the reading 111.36 + 8.64 = 120.00 fits; one cent more does not."""
    (short / "a").mkdir()
    (short / "b").mkdir()
    results = []
    for root, usd in ((_state(short / "a"), 111.36), (_state(short / "b"), 111.37)):
        _allowance(root, INPUTS, {**FIGURES, "five_usd_per_point": 100.0}, _reading(_local("2026-11-18 08:00")))
        _spent(root, _local("2026-11-18 08:30"), usd)
        _spent(root, _local("2026-11-18 07:30"), 50.0)  # before the reading: not counted
        ladder.reserve(root, _entry("rs-archive-clone"), CRITERION, 0.0)
        results.append(_guard(root, WED_10)[:2])
    assert results == [(True, None), (False, "the weekly budget does not hold the guard's reservations")]


def test_no_start_when_the_five_hour_budget_does_not_hold_them(short):
    """Five-hour budget (100 - 20 - 5) x 0.50 = 37.50; usage 36.50 since the reading + 1.00 fits, 36.51 does not."""
    (short / "a").mkdir()
    (short / "b").mkdir()
    results = []
    for root, usd in ((_state(short / "a"), 36.50), (_state(short / "b"), 36.51)):
        _allowance(root, INPUTS, FIGURES, _reading(_local("2026-11-18 08:00")))
        _spent(root, _local("2026-11-18 08:30"), usd)
        results.append(_guard(root, WED_10)[:2])
    assert results == [(True, None), (False, "the five-hour budget does not hold the guard's reservations")]


def test_after_the_five_hour_reset_the_last_five_hours_of_usage_stay_within_the_owner_s_share(short):
    """No reading for the new five-hour window: usage in the last five hours + reservations <= (100 - 20) x 0.50."""
    root = _state(short)
    _allowance(root, INPUTS, FIGURES, _reading(_local("2026-11-18 08:00"), five_reset=_local("2026-11-18 09:00")))
    _spent(root, _local("2026-11-18 09:30"), 38.5)
    fits = _guard(root, WED_10)[:2]
    _spent(root, _local("2026-11-18 09:40"), 0.51)  # 38.50 + 0.51 + 1.00 > 40.00
    assert (fits, _guard(root, WED_10)[:2]) == (
        (True, None), (False, "the last five hours' usage does not leave room for the guard's reservations"))


def test_the_guard_s_reservation_is_a_third_of_the_cap_raised_by_the_pilot_s_ratio(short):
    root = _state(short)
    _allowance(root, INPUTS, {**FIGURES, "reservation_raise": 1.5})
    assert (ladder.guard_reservation(CRITERION, "rs-archive-clone", ladder.allowance_state(root)["figures"]),
            ladder.guard_reservation(CRITERION, "gsea-proteomics", ladder.allowance_state(root)["figures"])) == (
        pytest.approx(7.64 * 1.5), pytest.approx(1.5))


def test_without_a_five_hour_figure_two_attempts_run_at_a_time(short):
    root = _state(short)
    _allowance(root, INPUTS, {**FIGURES, "five_usd_per_point": None}, _reading(_local("2026-11-18 08:00")))
    assert _guard(root, WED_10) == (True, None, 2)


def test_before_the_pilot_s_figures_only_the_smoke_and_the_pilot_may_start(short):
    root = _state(short)
    _allowance(root, INPUTS, _reading(_local("2026-11-18 08:00")))
    assert [_guard(root, WED_10, _entry(kind=kind))[:2] for kind in ("smoke", "pilot", "round")] == [
        (True, None), (True, None), (False, "the pilot's figures are not entered")]


@pytest.mark.parametrize("value,want", [("69", True), ("70", False)])
def test_a_utilisation_header_closes_starts_at_or_above_100_minus_f(short, value, want):
    root = _state(short)
    criterion = json.loads(json.dumps(CRITERION))
    criterion["allowance_guard"]["utilisation_header"] = "anthropic-ratelimit-unified-utilization"
    _allowance(root, INPUTS, FIGURES, _reading(_local("2026-11-18 08:00")))
    with open(root / "passthrough" / "requests.jsonl", "a") as fh:
        fh.write(json.dumps({"time": 1.0, "slot": "x", "status": 200, "usd": 0.0,
                             "headers": {"anthropic-ratelimit-unified-utilization": value}}) + "\n")
    assert ladder.guard(root, criterion, _entry(), _local(WED_10))[0] is want


def test_a_reading_or_a_change_of_the_allowance_inputs_is_recorded_and_leaves_the_manifest_hash_alone(short):
    kit = Kit(short)
    before = (kit.kit / "manifest.json").read_bytes()
    runs = [["allowance", "inputs", "--f-week", "30", "--f-five", "20", "--hours", "mon-fri 09:00-18:00",
             "--closing-margin-h", "2"],
            ["allowance", "inputs", "--f-week", "25", "--f-five", "20", "--hours", "daily 08:00-20:00",
             "--closing-margin-h", "3"],
            ["allowance", "reading", "--weekly", "12", "--weekly-reset", "2026-11-23T09:00", "--five", "4",
             "--five-reset", "2026-11-18T14:00", "--at", "2026-11-18T08:30"],
            ["allowance", "figures", "--weekly-usd-per-point", "2.5", "--five-usd-per-point", "0.6",
             "--reservation-raise", "1.2"]]
    codes = [subprocess.run([sys.executable, "-I", str(kit.kit / "ladder.py"), *argv], cwd=kit.repo, env=kit.env(),
                            capture_output=True, text=True, timeout=WAIT).returncode for argv in runs]
    rows = ladder._jsonl(kit.reh / "state" / "allowance.jsonl")
    check = subprocess.run([sys.executable, "-I", str(kit.kit / "manifest.py"), "check"], capture_output=True,
                           text=True, timeout=WAIT)
    assert (codes, [r["kind"] for r in rows], [r.get("f_week") for r in rows[:2]], rows[2]["weekly"],
            (kit.kit / "manifest.json").read_bytes() == before, check.returncode, _git(kit.repo, "status", "--porcelain")) == (
        [0, 0, 0, 0], ["inputs", "inputs", "reading", "figures"], [30, 25], 12, True, 0, "")


@pytest.mark.parametrize("argv", [["inputs", "--f-week", "130", "--f-five", "20", "--hours", "daily 08:00-20:00",
                                   "--closing-margin-h", "2"],
                                  ["inputs", "--f-week", "30", "--f-five", "20", "--hours", "someday 08:00-20:00",
                                   "--closing-margin-h", "2"],
                                  ["reading", "--weekly", "12", "--weekly-reset", "tomorrow", "--five", "4",
                                   "--five-reset", "2026-11-18T14:00"]])
def test_a_malformed_allowance_entry_is_refused_and_not_recorded(short, argv):
    reh = short / "reh"
    reh.mkdir()
    code = ladder.main(["allowance", *argv], {"HOME": str(short), "LH_REHEARSAL": str(reh)})
    assert (code, (reh / "state" / "allowance.jsonl").exists()) == (2, False)
