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


args = sys.argv[1:]
if args[:1] == ["-I"]:
    args = args[1:]
if args[:1] == ["-c"]:
    run_code(args[1], args[2:])
else:
    sys.exit(f"stand-in python: unexpected {args[:2]}")
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
