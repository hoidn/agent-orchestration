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

REPLAY = r'''
def replay(fx, trial, started="2026-11-20T10:00:00Z", finished="2026-11-20T10:30:00Z"):
    """A harness trial as Harbor writes it, from a cut fixture: result.json, and the stream with the fixture's init
    event, its count of events and of api_retry events, and its last events."""
    import json
    from pathlib import Path
    trial = Path(trial)
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
'''

STANDIN = REPLAY + r'''
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
    """The call and the environment it was given (/proc/self/environ: before Python's own locale coercion)."""
    import os
    given = Path("/proc/self/environ").read_bytes().split(b"\0")
    env = dict(e.decode().split("=", 1) for e in given if e)
    with open(HERE / "calls.jsonl", "a") as fh:
        fh.write(json.dumps({"argv": args, "env": env, "pid": os.getpid()}) + "\n")


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


BODY = {"model": "claude-haiku-5-5", "stream": False, "max_tokens": 1000, "output_config": {"effort": "low"},
        "tools": [{"name": "Bash", "input_schema": {"type": "object"}}], "messages": [{"role": "user", "content": "hi"}]}


def post(sock, token):
    """One request through the relay's socket, as the CLI sends it; its status, or the error's class."""
    import http.client, socket
    conn = http.client.HTTPConnection("relay", 8080, timeout=60)
    conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.sock.settimeout(60)
    try:
        conn.sock.connect(sock)
        conn.request("POST", "/v1/messages?beta=true", json.dumps(BODY), {
            "authorization": f"Bearer {token}", "content-type": "application/json",
            "anthropic-beta": "oauth-2025-04-20,extended-cache-ttl-2025-04-11"})
        resp = conn.getresponse()
        resp.read()
        return resp.status
    except OSError as exc:
        return type(exc).__name__
    finally:
        conn.close()


def note(what, **fields):
    import time
    with open(HERE / "notes.jsonl", "a") as fh:
        fh.write(json.dumps({"time": time.time(), "what": what, **fields}) + "\n")


def outlive(container, sock, token, most):
    """The CLI after the harness's time limit: it goes on sending requests until its container is gone."""
    import time
    for _ in range(most):
        if not container.exists():
            break
        note("after", status=post(sock, token))
        time.sleep(0.2)


def containers(trial, behaviour):
    """The trial's stand-in containers (agent and egress sidecar) and network, named as Harbor's compose names them."""
    project, folder = trial.name.lower() + "__env", HERE / "podman"
    sidecar = behaviour.get("egress", '{"sid": "a", "msg": "bypass"}\n{"sid": "a", "dst": "203.0.113.9:443"}')
    main = {"env": behaviour.get("container_env", ["PATH=/usr/bin"]), "fs": behaviour.get("container_fs", "a file\n")}
    main.update({"proc_env": behaviour["process_env"]} if "process_env" in behaviour else {})
    for name, extra in ((f"{project}_main_1", main),
                        (f"{project}_harbor-docker-egress-control-sidecar_1", {"log": sidecar})):
        (folder / "containers" / f"{name}.json").write_text(json.dumps({"running": True, "stubborn":
                                                                       behaviour.get("stubborn", 0), **extra}))
    (folder / "networks" / f"{project}_default.json").write_text("{}")
    return folder / "containers" / f"{project}_main_1.json"


def run(args):
    """`harbor_patient.py run ...`: the next behaviour of standin/plan.json, in call order."""
    import os, subprocess, time
    calls = [json.loads(line) for line in (HERE / "calls.jsonl").read_text().splitlines()]
    n = sum(1 for c in calls if c["argv"][1:2] == ["run"])
    plan = json.loads((HERE / "plan.json").read_text()) if (HERE / "plan.json").exists() else []
    behaviour = plan[n - 1] if n <= len(plan) else {}
    note("started", n=n, affinity=sorted(os.sched_getaffinity(0)), pgid=os.getpgid(0), pid=os.getpid())
    task = Path(option(args, "--path")).name
    trial = Path(option(args, "-o")) / option(args, "--job-name") / f"{task[:32]}__s{n:06d}"
    trial.mkdir(parents=True)
    container = containers(trial, behaviour)
    sock = os.path.join(os.environ["LH_RELAY_SOCKET_DIR"], "passthrough.sock")
    for _ in range(behaviour.get("requests", 1)):
        note("request", status=post(sock, os.environ["CLAUDE_CODE_OAUTH_TOKEN"]))
    if behaviour.get("child"):
        subprocess.Popen(["sleep", "600"])
        note("child")
    time.sleep(behaviour.get("sleep", 0))
    fx = json.loads(Path(behaviour.get("fixture", FIXTURES + "/token-three-tools-normal-end.json")).read_text())
    replay(fx, trial)
    if fx.get("verifier_result") is None and behaviour.get("reward", 1.0) is not None:  # the verifier ran after it
        result = json.loads((trial / "result.json").read_text())
        result["verifier_result"] = {"rewards": {"reward": behaviour.get("reward", 1.0)}}
        (trial / "result.json").write_text(json.dumps(result))
    for name, text in behaviour.get("write", {}).items():
        (trial / name).parent.mkdir(parents=True, exist_ok=True)
        (trial / name).write_text(text)
    for name in behaviour.get("unreadable", []):  # a file no scan can read (mode 000)
        (trial / name).parent.mkdir(parents=True, exist_ok=True)
        (trial / name).write_text("x")
        (trial / name).chmod(0)
    if behaviour.get("stop_containers"):  # the agent container has stopped by the teardown, as a real one has
        container.write_text(json.dumps({**json.loads(container.read_text()), "running": False}))
    if behaviour.get("after_requests"):
        subprocess.Popen([sys.executable, "-I", __file__, "--outlive", str(container), sock,
                          os.environ["CLAUDE_CODE_OAUTH_TOKEN"], str(behaviour["after_requests"])],
                         start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    note("ended", n=n)


args = sys.argv[1:]
if args[:1] == ["-I"]:
    args = args[1:]
if args[:1] == ["--outlive"]:
    outlive(Path(args[1]), args[2], args[3], int(args[4]))
elif args[:1] == ["-c"]:
    run_code(args[1], args[2:])
elif args[1:2] == ["run"]:
    log_call(args)
    run(args)
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
    if any((load(n) or {}).get("inspect_fails") for n in operands(rest)):
        sys.exit(125)
    print(json.dumps([{"Name": n, "Config": {"Env": load(n).get("env", [])}} for n in operands(rest) if load(n)]))
elif cmd == "logs":
    found = load(operands(rest)[0]) or {}
    if found.get("logs_fails"):
        sys.exit(125)
    print(found.get("log", ""))
elif cmd == "exec":
    found = load(operands(rest)[0])
    if not found or not found.get("running", True):
        sys.exit(125)
    if found.get("no_sh"):  # an image without sh
        sys.exit(127)
    sys.stdout.write("\0".join(found.get("proc_env", found.get("env", []))))
elif cmd == "export":
    found = load(operands(rest)[0]) or {}
    if "fs" in found and found["fs"] is None:  # a container whose file system cannot be exported
        sys.exit(125)
    sys.stdout.write(found.get("fs", ""))
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
    python.write_text(f"#!{sys.executable} -I\nFIXTURES = {str(KIT / 'fixtures')!r}\n{STANDIN}")
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
             "schedule.order.hash": ladder.ORDER_HASH, "readout.fall_bound.seed": 1}


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
        """`ladder.py launch --dry-run` (every refusal, nothing started) run from the copy; (exit code, stderr)."""
        done = subprocess.run([sys.executable, "-I", str(self.kit / "ladder.py"), "launch", "--dry-run"], cwd=self.repo,
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


@pytest.mark.parametrize("name", ["CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"])
def test_the_launcher_refuses_a_credential_in_its_own_environment_naming_it_never_its_value(short, name):
    """Task 8 m8: the launcher and its children never hold a credential, so it refuses to start."""
    kit = Kit(short)
    value = "lh-test-" + os.urandom(16).hex()
    code, reason = _refused(kit, kit.env(**{name: value}))
    assert (code, name in reason, value in reason) == (3, True, False)


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


_NS = {}
exec(compile(REPLAY, "<replay>", "exec"), _NS)
_replay = _NS["replay"]


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
    while time.time() <= now + 0.001 * (len(rows) + 1):  # the window ends at the close: every row is in it
        time.sleep(0.001)
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
    exported = ladder._start_record(root, {**attempt, "settled": record}, STANDING)  # the readout's reading of it
    assert ((record["class"], record["reward"], len(calls)),
            {c["argv"][1] + " " + c["argv"][2] for c in calls}, [agent_args & set(c["argv"]) for c in calls],
            [k for c in calls for k in c["env"] if k.startswith(("CLAUDE", "LH_", "ANTHROPIC"))],
            (exported["class"], exported["excluded"])) == (
        want, {"trial regrade"}, [set()] * len(calls), [],
        (want[0], "no reward after regrades" if want[0] == "infrastructure_failure" else None))


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
    _fingerprint(root, "lh-test-" + os.urandom(16).hex())
    ladder.reconcile(ctx, STANDING, 0.0, gate=lambda: True)  # the criterion a launch reads
    states = [s.poll() for s in sleepers]
    for s in sleepers:
        s.kill()
        s.wait()
    settled = {a["id"].split("-", 1)[0]: a["settled"] and a["settled"]["class"] for a in ladder.attempts(root)}
    assert (_containers(lh), settled, states[0] is not None, states[1]) == (
        ["trial0__abcdefg__env_main_1"], {"001": None, "002": "infrastructure_failure", "003": "infrastructure_failure"},
        True, None)


TOKEN_SCAN = _load("lh_token_scan_for_the_launcher", KIT / "token_scan.py")


def _fingerprint(root, token):
    """The passthrough's fingerprint of a generated stand-in token, written beside its log as it writes it."""
    (root / "passthrough" / "fingerprint.json").write_text(json.dumps(TOKEN_SCAN.fingerprint(token)))


def _orphan(short, lh):
    """A normal ending with reward 1 left open by a launcher that is gone (a pid no process has)."""
    ctx = _ctx(short, lh)
    ladder.ensure_state(ctx.root)
    attempt = ladder.reserve(ctx.root, _entry(), CRITERION, 0.0)
    attempt = {**attempt, "launcher": {"pid": 2 ** 22 + 7, "start": 1}}
    ladder._write_json(ctx.root / "slots" / attempt["id"] / "slot.json", attempt)
    fx = json.loads((KIT / "fixtures" / "token-three-tools-normal-end.json").read_text())
    trial = ctx.root / "slots" / attempt["id"] / "jobs" / attempt["id"] / "wal-recovery-ordering__abcdefg"
    _replay({**fx, "verifier_result": {"rewards": {"reward": 1.0}}}, trial)
    _container(lh, f"{trial.name.lower()}__env_main_1")  # the session's containers, still there
    return ctx, attempt, trial


@pytest.mark.parametrize("written, leaked, cause", [
    ("a subagent file", False, "a subagent file"), (None, True, "a match of token_scan.py")])
def test_reconcile_closes_a_dead_launcher_s_attempt_as_its_stop_never_as_a_scored_observation(
        short, written, leaked, cause):
    """A stop written before the launcher died, or one its teardown's scans find, makes the attempt a stop when
    reconcile closes it, exactly as the attempt's own teardown would have."""
    lh = _cache(short, json.loads((KIT / "tasks.json").read_text())["tasks"])
    ctx, attempt, trial = _orphan(short, lh)
    token = "lh-test-" + os.urandom(16).hex()
    _fingerprint(ctx.root, token)
    if written:
        ladder.tranche_event(ctx.root, "stop", slot=attempt["id"], reason=written)
    if leaked:
        (trial / "agent" / "kept.log").write_text(f"x {token} y")
    ladder.reconcile(ctx, STANDING, 0.0, gate=lambda: True)  # the criterion a launch reads
    settled = ladder.attempts(ctx.root)[0]["settled"]
    stops = [e["reason"] for e in _jsonl_events(ctx) if e["event"] == "stop"]
    assert ((settled["row"], settled["class"], settled["stop"], settled["reward"]), stops) == (
        (5, "stop", cause, None), [cause])


def test_reconcile_retires_the_token_of_an_attempt_settled_by_a_launcher_killed_inside_settle(short):
    """Task 8 m4: settled.json was written and the slots file not rewritten before the kill."""
    lh = _cache(short, json.loads((KIT / "tasks.json").read_text())["tasks"])
    ctx = _ctx(short, lh)
    ladder.ensure_state(ctx.root)
    attempt = ladder.reserve(ctx.root, _entry(), CRITERION, 0.0)
    ladder._write_json(ctx.root / "slots" / attempt["id"] / "settled.json", {"class": "observation", "usd": 0.1})
    before = json.loads((ctx.root / "passthrough" / "slots.json").read_text())["slots"]
    ladder.reconcile(ctx, STANDING, 0.0, gate=lambda: True)
    after = json.loads((ctx.root / "passthrough" / "slots.json").read_text())["slots"]
    assert (list(before), after) == ([attempt["id"]], {})


# The passthrough's mode (Task 8 M3): a rehearsal never runs against a live passthrough, nor the other way.

@pytest.mark.parametrize("live, mode, refused", [(False, "live", True), (True, "rehearsal", True),
                                                 (False, None, True), (False, "rehearsal", False),
                                                 (True, "live", False)])
def test_the_launcher_refuses_a_passthrough_whose_recorded_mode_is_not_its_own(short, live, mode, refused):
    env = {"HOME": str(short / "home")} | ({} if live else {"LH_REHEARSAL": str(short / "reh")})
    ctx = ladder.Ctx(env)
    ladder.ensure_state(ctx.root)
    (ctx.root / "passthrough" / "fingerprint.json").write_text(json.dumps({"salt": "00", "forms": []} | (
        {"mode": mode} if mode else {})))
    assert bool(ladder.passthrough_mode_refusal(ctx)) == refused


def test_a_rehearsal_against_a_live_passthrough_starts_no_attempt_and_stops_the_tranche(rig):
    r = rig()
    fingerprint = r.root / "passthrough" / "fingerprint.json"
    fingerprint.write_text(json.dumps({**json.loads(fingerprint.read_text()), "mode": "live"}))
    r.launch()
    stops = [e["reason"] for e in r.events() if e["event"] == "stop"]
    assert (r.calls(), r.attempts(), len(stops), "live" in stops[0]) == ([], [], 1, True)


def test_in_a_rehearsal_status_prints_the_passthrough_s_rehearsal_start_and_never_the_token_file(rig):
    r = rig()
    out = subprocess.run([sys.executable, "-I", str(r.kit.kit / "ladder.py"), "status"], cwd=r.kit.repo,
                         env=r.kit.env(), capture_output=True, text=True, timeout=WAIT).stdout
    assert ("--rehearsal" in out, "--canary-out" in out, "--token-file" in out, "token file" in out) == (
        True, True, False, False)


# The runtime check (Task 8 part B): any finding in any container is the attempt's; what it cannot read is
# an incomplete scan, never clean.

def _runtime(short, containers, session=True, export=True):
    """runtime_check on an attempt whose trial had a session (or not), with stand-in containers named
    `<trial>__<suffix>` and the fields `containers(token)` gives; its finding."""
    lh = _cache(short, json.loads((KIT / "tasks.json").read_text())["tasks"])
    ctx = _ctx(short, lh)
    ladder.ensure_state(ctx.root)
    token = "lh-test-" + os.urandom(16).hex()
    _fingerprint(ctx.root, token)
    attempt_dir = ctx.root / "slots" / "001"
    trial = attempt_dir / "jobs" / "001" / "wal__abcdefg"
    (trial / "agent").mkdir(parents=True)
    if session:
        (trial / "agent" / "claude-code.txt").write_text("{}\n")
    for suffix, fields in containers(token).items():
        _container(lh, f"wal__abcdefg__{suffix}", **fields)
    return ladder.runtime_check(ctx, attempt_dir, export)


MAIN, SIDECAR = "env_main_1", "env_harbor-docker-egress-control-sidecar_1"
INCOMPLETE = "an incomplete scan of the runtime check in the attempt's containers"
MATCH = "a match of the runtime check in the attempt's containers"


def test_a_clean_attempt_s_containers_pass_the_runtime_check(short):
    assert _runtime(short, lambda t: {MAIN: {"fs": "a file\n"}, SIDECAR: {"log": "{}"}}) is None


def test_a_match_in_one_container_s_file_system_is_never_replaced_by_a_later_container_s_clean_one(short):
    """B1: the trial's agent container and a verifier project's both end in _main_1; the first holds the token."""
    found = _runtime(short, lambda t: {MAIN: {"fs": f"x {t} y"}, "verifier__abc_main_1": {"fs": "clean\n"}})
    assert found == MATCH


@pytest.mark.parametrize("containers, session, want", [
    (lambda t: {}, True, INCOMPLETE),  # a session, and no container under the trial's prefix
    (lambda t: {"env_agent_1": {"fs": f"x {t} y"}}, True, INCOMPLETE),  # an export due, and no agent container
    (lambda t: {"env_agent_1": {}}, False, INCOMPLETE),
    (lambda t: {}, False, None)])  # no session and no container: nothing ran, nothing to scan
def test_a_runtime_check_that_finds_nothing_it_must_read_is_incomplete_never_clean(short, containers, session, want):
    """B2: an attempt with a session, or with containers, whose agent container is not found."""
    assert _runtime(short, containers, session=session) == want


def test_a_container_whose_process_environments_were_never_read_is_an_incomplete_scan(short):
    """M1: every `podman exec` failed (an image without sh), so no sample of its processes was ever scanned."""
    assert _runtime(short, lambda t: {MAIN: {"no_sh": True}, SIDECAR: {}}) == INCOMPLETE


@pytest.mark.parametrize("fields", [{MAIN: {"inspect_fails": True}, SIDECAR: {}},
                                    {MAIN: {}, SIDECAR: {"logs_fails": True}},
                                    {MAIN: {"fs": None}, SIDECAR: {}}])
def test_a_failed_podman_read_is_an_incomplete_scan_never_an_empty_file_scanned_clean(short, fields):
    """M2: `podman inspect`, `logs` or `export` exits non-zero."""
    assert _runtime(short, lambda t: fields) == INCOMPLETE


# The starts gate under a usage limit (Task 8 part A, B1, M1, m1, m2): a resume lifts a hold, never a limit.

def _gate_root(short, *events):
    root = short / "state"
    ladder.ensure_state(root)
    _events_file(root, *events)
    return root


def _sequence(now, order, reset):
    """The events named in `order`, one second apart and ending a second before `now`."""
    made = {"limit": {"event": "close_starts", "slot": "x", "status": 429, "reason": "usage limit", "reset": reset},
            "pause": {"event": "pause", "reason": "D5 row 16"}, "stop": {"event": "stop", "reason": "a subagent file"},
            "resume": {"event": "resume", "by": "a person"}}
    return [{"time": now - len(order) + i, **made[name]} for i, name in enumerate(order)]


@pytest.mark.parametrize("order", [("limit", "pause", "resume"), ("pause", "limit", "resume"),
                                   ("limit", "stop", "resume"), ("stop", "limit", "resume"),
                                   ("limit", "pause", "resume", "stop", "resume"),
                                   ("pause", "limit", "stop", "resume"), ("limit", "resume")])
def test_no_order_of_limit_pause_stop_and_resume_opens_a_start_before_the_limit_s_reset(short, order):
    now = time.time()
    gate = ladder.starts_gate(_gate_root(short, *_sequence(now, order, now + 3600)), now)
    assert (gate["open"], gate["kind"]) == (False, "limit")


def test_a_stop_holds_over_a_later_usage_limit_whose_reset_has_passed(short):
    """A request in flight answered 429 after a stop never turns the stop into a limit that reopens by itself."""
    now = time.time()
    gate = ladder.starts_gate(_gate_root(short, *_sequence(now, ("stop", "limit"), now - 3600)), now)
    assert (gate["open"], gate["kind"]) == (False, "stop")


def test_after_the_reset_a_resume_reopens_with_one_start(short):
    now = time.time()
    gate = ladder.starts_gate(_gate_root(short, *_sequence(now, ("limit", "pause", "resume"), now - 3600)), now)
    assert (gate["open"], gate["most"]) == (True, 1)


def test_a_single_start_after_a_reset_that_ends_with_no_answer_pauses_the_tranche_and_a_resume_allows_one_more(short):
    """M1: it never waits silently."""
    now = time.time()
    ctx = ladder.Ctx({"HOME": str(short / "home"), "LH_REHEARSAL": str(short / "reh")})
    ladder.ensure_state(ctx.root)
    _events_file(ctx.root, *_sequence(now, ("limit",), now - 3600))
    attempt = ladder.reserve(ctx.root, _entry(), STANDING, 0.0)
    ladder.settle(ctx.root, attempt, {"class": "pre_session_failure", "usd": 0.0, "row": 1}, STANDING)
    why = ladder.Tranche(ctx, STANDING).step(time.time())
    paused = [e["reason"] for e in _jsonl_events(ctx) if e["event"] == "pause"]
    _events_file(ctx.root, {"time": time.time(), "event": "resume", "by": "a person"})
    gate = ladder.starts_gate(ctx.root, time.time())
    assert (bool(why), len(paused), (gate["open"], gate["most"])) == (True, 1, (True, 1))


def test_a_limit_that_named_no_reset_does_not_swallow_the_next_limit_episode():
    """m1: four answers, the first naming no reset and lifted by a resume, are four episodes."""
    now = time.time()
    events = [{"time": now - 100000, "event": "close_starts", "reason": "usage limit", "reset": None},
              {"time": now - 90000, "event": "resume", "by": "a person"}] + [
        {"time": t, "event": "close_starts", "reason": "usage limit", "reset": t + 3600}
        for t in (now - 80000, now - 60000, now - 40000)]
    assert len(ladder.limit_episodes(events)) == 4


def test_a_reset_that_is_not_a_number_is_read_as_no_reset_named(short):
    """m2: the vendor header's form is unconfirmed; the gate pauses for a person, never raises."""
    now = time.time()
    root = _gate_root(short, {"time": now - 1, "event": "close_starts", "reason": "usage limit", "reset": "soon"})
    events = ladder._jsonl(root / "passthrough" / "tranche.jsonl")
    assert (ladder.starts_gate(root, now)["kind"], len(ladder.limit_episodes(events))) == ("pause", 1)


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


# ---- Host (Task 5, fifth checkbox): the tranche end to end against the stand-ins --------------------------------

HOSTS = ["relay", "pypi.org", "files.pythonhosted.org"]
NOW = None  # a rig's allowance is read at its own start


def _fast(doc):
    doc["host"]["load_wait"]["gate_closed_s"] = 4  # the two-hour load wait, shortened for the test


class Rig:
    """A kit copy in rehearsal mode with its passthrough (rehearsal switch, in front of stub_api.py), the stand-in
    harness and podman, allowance inputs, a reading and the pilot's figures; `launch()` runs `ladder.py launch`."""

    def __init__(self, short, plan=(), edit=_fast, stand_ins=None, figures=True, scenario="normal"):
        self.kit = kit = Kit(short, edit=edit)
        values = {**STAND_INS, "tasks.overlay_digests": {t: kit.ladder.overlay_digest(HOSTS) for t in TASKS},
                  "schedule.order.hash": kit.ladder.ORDER_HASH, **(stand_ins or {})}
        (kit.reh / "stand_ins.json").write_text(json.dumps(values))
        self.root, self.lh, self.short = kit.reh / "state", kit.lh, short
        kit.ladder.ensure_state(self.root)
        (kit.reh / "host").mkdir()
        (kit.reh / "host" / "loadavg").write_text("1.0 1.0 1.0 1/1 1\n")  # a quiet host, by stand-in
        (kit.reh / "host" / "free_gb").write_text("100")  # and room on its disk
        (self.lh / "standin" / "plan.json").write_text(json.dumps(list(plan)))
        now = time.time()
        rows = [{"kind": "inputs", "at": now - 120, "f_week": 10, "f_five": 10, "hours": ["daily 00:00-24:00"],
                 "closing_margin_h": 0},
                {"kind": "reading", "at": now - 60, "weekly": 0, "five": 0, "weekly_reset": now + DAY,
                 "five_reset": now + 3600}]
        rows += [{"kind": "figures", "at": now - 30, "weekly_usd_per_point": 50.0, "five_usd_per_point": 50.0,
                  "reservation_raise": 1.0}] if figures else []
        _allowance(self.root, *rows)
        self.procs = []
        stub = short / "stub.sock"
        self._start([sys.executable, "-I", str(KIT / "stub_api.py"), "--unix", str(stub), "--model", ladder.MODEL,
                     "--scenario", scenario, "--log", str(short / "stub.jsonl")], short / "stub.out")
        self.canary_file = short / "canary"
        self.passthrough = self._start(
            [sys.executable, "-I", str(KIT / "passthrough.py"), "--socket", str(self.root / "relay" / "passthrough.sock"),
             "--state", str(self.root / "passthrough"), "--slots", str(self.root / "passthrough" / "slots.json"),
             "--rehearsal", str(stub), "--canary-out", str(self.canary_file)],
            self.root / "passthrough" / "output.log")
        self.canary = self.canary_file.read_text().strip()
        self.label = hashlib.sha256((kit.kit / "manifest.json").read_bytes()).hexdigest()

    def _start(self, argv, out):
        fh = open(out, "ab")
        proc = subprocess.Popen(argv, stdout=fh, stderr=fh)
        self.procs.append(proc)
        deadline = time.monotonic() + WAIT
        while b"listening" not in out.read_bytes() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        assert b"listening" in out.read_bytes(), out.read_text()
        return proc

    def ledger(self, what, cell):
        with open(self.kit.reh / "ledger.md", "a") as fh:
            fh.write(f"| 2026-11-20 | {what} | {cell} |\n")

    def launch(self, timeout=WAIT * 3, **extra):
        env = self.kit.env(**extra)
        done = subprocess.run([sys.executable, "-I", str(self.kit.kit / "ladder.py"), "launch"], cwd=self.kit.repo,
                              env=env, capture_output=True, text=True, timeout=timeout)
        return done.returncode, done.stdout, done.stderr

    def start_launch(self):
        env = self.kit.env()
        return subprocess.Popen([sys.executable, "-I", str(self.kit.kit / "ladder.py"), "launch"], cwd=self.kit.repo,
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def attempts(self):
        return self.kit.ladder.attempts(self.root)

    def events(self):
        return ladder._jsonl(self.root / "passthrough" / "tranche.jsonl")

    def rows(self):
        return ladder._jsonl(self.root / "passthrough" / "requests.jsonl")

    def notes(self):
        return ladder._jsonl(self.lh / "standin" / "notes.jsonl")

    def calls(self):
        return _calls(self.lh)

    def podman_calls(self):
        return [json.loads(l) for l in (self.lh / "standin" / "podman" / "calls.jsonl").read_text().splitlines()]

    def close(self):
        for proc in self.procs:
            proc.terminate()
            proc.wait(timeout=WAIT)


@pytest.fixture
def rig(short):
    made = []

    def make(**kwargs):
        made.append(Rig(short, **kwargs))
        return made[-1]
    yield make
    for one in made:
        one.close()
    for line in subprocess.run(["pgrep", "-f", str(short)], capture_output=True, text=True).stdout.split():
        os.kill(int(line), 9)  # a stand-in "CLI" that outlived its test


import time  # noqa: E402  (used by the rig and the tests below)


def test_the_smoke_runs_end_to_end_and_the_tranche_then_waits_for_the_smoke_read(rig):
    r = rig()
    code, out, err = r.launch()
    (attempt,) = r.attempts()
    settled = attempt["settled"]
    assert (code, "waiting for the smoke read" in out, (attempt["task"], attempt["effort"], attempt["kind"]),
            settled["row"], settled["class"], settled["usd"] > 0, settled["figures"]["meter"] > 0,
            json.loads((r.root / "passthrough" / "slots.json").read_text())["slots"]) == (
        0, True, ("gsea-proteomics", "low", "smoke"), 5, "observation", True, True, {})


def test_the_harness_command_carries_the_criterion_s_configuration_and_runs_in_its_own_session(rig):
    r = rig()
    r.launch()
    (call,) = r.calls()
    argv, env = call["argv"], call["env"]
    started = next(n for n in r.notes() if n["what"] == "started")
    attempt = r.attempts()[0]
    want_flags = {"--agent": "claude-code", "-m": "anthropic/claude-haiku-5-5", "--base-url": "http://relay:8080",
                  "--effort": "low", "--max-retries": "0", "--agent-setup-timeout-multiplier": "3",
                  "--agent-timeout-multiplier": "1", "--verifier-timeout-multiplier": "1", "--env": "podman",
                  "--job-name": attempt["id"]}
    aks = [argv[i + 1] for i, a in enumerate(argv) if a == "--ak"]
    assert ({k: argv[argv.index(k) + 1] for k in want_flags}, sorted(aks),
            [argv[i + 1] for i, a in enumerate(argv) if a == "--ae"], "--skip-credential-checks" in argv,
            ["keep_containers=true"] == [argv[i + 1] for i, a in enumerate(argv) if a == "--ek"],
            argv[:2], {k: env[k] for k in ("CLAUDE_FORCE_OAUTH", "CLAUDE_CODE_OAUTH_TOKEN")},
            started["affinity"], started["pgid"] == started["pid"]) == (
        want_flags, sorted(["version=2.1.311", "disallowed_tools=" + ",".join(CRITERION["attempt"]["deny_list"]),
                            "max_budget_usd=3.0"]),
        ["CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000"], True, True,
        [str(r.kit.kit / "harbor_patient.py"), "run"], {"CLAUDE_FORCE_OAUTH": "1", "CLAUDE_CODE_OAUTH_TOKEN": attempt["token"]},
        list(range(24)), True)


def test_no_credential_is_in_any_file_environment_or_command_line(rig):
    """The passthrough's rehearsal canary stands for the real token: after an attempt it is in no file of the state,
    the stand-in harness's recorded command line and environment, or the cache; the harness had nothing else."""
    r = rig()
    r.launch()
    fingerprint = r.root / "passthrough" / "fingerprint.json"
    scan = subprocess.run([sys.executable, "-I", str(KIT / "token_scan.py"), "scan", "--fingerprint", str(fingerprint),
                           str(r.root), str(r.lh), str(r.kit.repo)], capture_output=True, text=True, timeout=WAIT)
    env = r.calls()[0]["env"]
    assert (scan.returncode, sorted(env), r.canary in json.dumps(r.calls())) == (
        0, sorted(["HOME", "PATH", "HARBOR_TELEMETRY", "DO_NOT_TRACK", "XDG_RUNTIME_DIR", "CONTAINERS_CONF_OVERRIDE",
                   "LH_RELAY_SOCKET_DIR", "CLAUDE_FORCE_OAUTH", "CLAUDE_CODE_OAUTH_TOKEN"]), False)


def test_each_attempt_s_relay_has_its_own_passthrough_socket_which_goes_when_its_slot_closes(rig):
    """Group 6 (connections): the slots file marks the slot own_socket, the harness's relay mounts the slot's own
    directory, and the passthrough removes the socket once the slot is retired."""
    r = rig(plan=[{}, {"sleep": 2}, {"sleep": 2}, {"sleep": 2}])
    r.launch()
    r.ledger("Smoke read", f"{r.label} pass")
    r.launch()
    dirs = [c["env"]["LH_RELAY_SOCKET_DIR"] for c in r.calls()]
    statuses = [n["status"] for n in r.notes() if n["what"] == "request"]
    deadline = time.monotonic() + WAIT
    while any(Path(d).exists() for d in dirs) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert (sorted(dirs), statuses, [Path(d).exists() for d in dirs]) == (
        sorted(str(r.root / "relay" / a["id"]) for a in r.attempts()), [200] * 4, [False] * 4)


def test_a_state_path_too_long_for_a_slot_s_socket_is_refused(short):
    kit = Kit(short)
    long = short / ("d" * 90)
    long.mkdir(mode=0o700)
    shutil.copy(kit.reh / "stand_ins.json", long / "stand_ins.json")
    env = kit.env(LH_REHEARSAL=str(long))
    kit.allowance_inputs(env)
    (long / "state").mkdir(exist_ok=True)
    shutil.copy(kit.reh / "state" / "allowance.jsonl", long / "state" / "allowance.jsonl")
    assert _refused(kit, env)[1].startswith("the state's path is too long for a slot's socket")


def test_the_egress_log_is_followed_out_and_kept_before_the_containers_are_removed(rig):
    r = rig(plan=[{"egress": '{"sid": "a", "msg": "bypass"}\n{"sid": "a", "dst": "198.51.100.7:443"}\n'
                             '{"sid": "b", "msg": "10.0.0.2:1 <-> relay:8080"}'}])
    r.launch()
    attempt_dir = r.root / "slots" / r.attempts()[0]["id"]
    calls = r.podman_calls()
    sidecar = next(c[1] for c in calls if c[0] == "logs")
    first_rm = next(i for i, c in enumerate(calls) if c[0] == "rm")
    kept = [p.read_text() for p in attempt_dir.glob("egress-*.log")]
    assert (calls.index(["logs", sidecar]) < first_rm, len(kept), "198.51.100.7:443" in kept[0],
            ladder.egress_refused(attempt_dir)) == (True, 1, True, {"198.51.100.7:443": 1})


def test_a_slot_closes_only_after_every_container_is_removed_and_the_cli_s_later_requests_are_metered_into_it(rig):
    """The stand-in CLI goes on sending requests after the harness ends, as the real one does after a time limit,
    until its container is gone; a container that survives two removals keeps the slot open meanwhile."""
    r = rig(plan=[{"fixture": str(KIT / "fixtures" / "stub-timeout-AgentTimeoutError.json"), "stubborn": 2,
                   "after_requests": 50}])
    r.launch()
    attempt = r.attempts()[0]
    after = [n["status"] for n in r.notes() if n["what"] == "after"]
    ended = next(n["time"] for n in r.notes() if n["what"] == "ended")
    slot_rows = [row for row in r.rows() if row["slot"] == attempt["id"]]
    rm_calls = [c for c in r.podman_calls() if c[0] == "rm"]
    assert (bool(after), set(after), [row for row in r.rows() if row.get("refused")],
            any(row["time"] > ended for row in slot_rows), len(rm_calls) >= 3, attempt["settled"]["row"],
            attempt["settled"]["figures"]["meter"] == pytest.approx(sum(row["usd"] for row in slot_rows))) == (
        True, {200}, [], True, True, 3, True)


def test_low_disk_stops_the_tranche_and_a_running_attempt_ends_within_seconds_leaving_nothing(rig):
    r = rig(plan=[{"sleep": 600, "child": True}])
    host = r.kit.reh / "host"
    proc = r.start_launch()
    deadline = time.monotonic() + WAIT
    while not any(n["what"] == "child" for n in r.notes()) and time.monotonic() < deadline:
        time.sleep(0.2)
    started = next(n for n in r.notes() if n["what"] == "started")
    (host / "free_gb").write_text("19")
    flipped = time.monotonic()
    out, err = proc.communicate(timeout=WAIT)
    took = time.monotonic() - flipped
    group = subprocess.run(["pgrep", "-g", str(started["pgid"])], capture_output=True, text=True).stdout.split()
    assert (proc.returncode, took < 60, group, _containers(r.lh), r.attempts()[0]["settled"] is not None,
            [e["reason"] for e in r.events() if e["event"] == "stop"]) == (
        0, True, [], [], True, ["free disk under 20 GB"])


def test_a_signal_to_the_launcher_ends_a_running_attempt_within_seconds_leaves_nothing_and_pauses(rig):
    r = rig(plan=[{"sleep": 600, "child": True}])
    proc = r.start_launch()
    deadline = time.monotonic() + WAIT
    while not any(n["what"] == "child" for n in r.notes()) and time.monotonic() < deadline:
        time.sleep(0.2)
    started = next(n for n in r.notes() if n["what"] == "started")
    proc.terminate()
    signalled = time.monotonic()
    proc.communicate(timeout=WAIT)
    took = time.monotonic() - signalled
    group = subprocess.run(["pgrep", "-g", str(started["pgid"])], capture_output=True, text=True).stdout.split()
    assert (proc.returncode, took < 60, group, _containers(r.lh), r.attempts()[0]["settled"] is not None,
            [e["reason"] for e in r.events() if e["event"] == "pause"]) == (
        0, True, [], [], True, ["the launcher was signalled"])


def test_the_harness_is_held_until_its_pid_is_recorded_and_never_runs_when_the_launcher_dies_first(short):
    """Task 8 m6: the launcher writes `go` after slot.json holds the harness's pid; an end of input (the launcher
    died between the two) ends the hold without running the harness."""
    ran = []
    for go in (b"", b"go\n"):
        mark = short / f"ran-{len(ran)}"
        held = subprocess.Popen([*ladder.HOLD, "touch", str(mark)], stdin=subprocess.PIPE)
        held.stdin.write(go)
        held.stdin.close()
        ran.append((held.wait(timeout=WAIT) == 0, mark.exists()))
    assert ran == [(False, False), (True, True)]


def test_a_failure_while_an_attempt_runs_stops_its_harness_and_tears_it_down_before_it_propagates(rig):
    """Task 8 m5: the run-time load sample fails mid-attempt (a load file that cannot be read as one)."""
    r = rig(plan=[{"sleep": 30}])
    proc = r.start_launch()
    deadline = time.monotonic() + WAIT
    while not any(n["what"] == "started" for n in r.notes()) and time.monotonic() < deadline:
        time.sleep(0.2)
    (r.kit.reh / "host" / "loadavg").write_text("not a load\n")
    proc.communicate(timeout=WAIT * 2)
    started = next(n for n in r.notes() if n["what"] == "started")
    group = subprocess.run(["pgrep", "-g", str(started["pgid"])], capture_output=True, text=True).stdout.split()
    slots = json.loads((r.root / "passthrough" / "slots.json").read_text())["slots"]
    failed = [e["reason"] for e in r.events() if e["event"] == "pause" and "the launcher failed" in e["reason"]]
    assert (group, r.attempts()[0]["settled"] is not None, slots, len(failed), _containers(r.lh)) == (
        [], True, {}, 1, [])


def test_a_passthrough_that_died_without_closing_starts_pauses_the_tranche(rig):
    r = rig()
    r.passthrough.kill()  # SIGKILL: it writes no close_starts, and its socket stays behind
    r.passthrough.wait(timeout=WAIT)
    code, out, err = r.launch()
    assert (code, r.attempts(), [e["reason"] for e in r.events() if e["event"] == "pause"]) == (
        0, [], ["the passthrough down"])


def test_an_overlay_whose_digest_is_not_the_criterion_s_stops_the_tranche_before_the_harness_runs(rig):
    """Coordinator ruling (Task 5): a launch refused before the harness ran is no start and is not exported; it
    stays in the launcher's own records (the stop event and the attempt kept under refused/), and its token is
    retired."""
    r = rig(stand_ins={"tasks.overlay_digests": {t: "0" * 64 for t in TASKS}})
    r.launch()
    slots = json.loads((r.root / "passthrough" / "slots.json").read_text())["slots"]
    assert ([e["reason"] for e in r.events() if e["event"] == "stop"], r.calls(), _containers(r.lh), r.attempts(),
            len(list((r.root / "refused").iterdir())), slots, _export(r)["starts"]) == (
        ["refused at launch"], [], [], [], 1, {}, [])


def test_the_disk_stop_reads_the_root_file_system_beside_the_state_the_cache_and_the_home(short):
    """ladder.json host.disk_plan: no start under 20 GB free on /home or / (Podman stages pulls in /var/tmp)."""
    ctx = _ctx(short)
    ladder.ensure_state(ctx.root)
    paths = ladder.disk_paths(ctx)
    assert (Path("/") in paths, ctx.root in paths, ladder.free_gb(ctx) == min(
        shutil.disk_usage(p).free for p in paths) / 1e9) == (True, True, True)


@pytest.mark.parametrize("load", ["30.0 30.0 30.0", "24.0 24.5 20.0", "24.5 24.0 20.0"])  # both, 5-min, 1-min above
def test_the_load_gate_waits_and_pauses_after_its_wait_with_nothing_in_flight(rig, load):
    r = rig()
    host = r.kit.reh / "host"
    (host / "loadavg").write_text(f"{load} 1/1 1\n")
    code, out, err = r.launch()
    assert (code, r.attempts(), [(e["event"], e["reason"]) for e in r.events() if e["event"] == "pause"]) == (
        0, [], [("pause", "the load wait: the gate stayed closed with nothing in flight")])


def test_the_load_gate_opens_when_the_load_falls_below_it(rig):
    r = rig()
    host = r.kit.reh / "host"
    (host / "loadavg").write_text("24.0 24.5 20.0 1/1 1\n")  # the 5-minute average is above 24
    proc = r.start_launch()
    time.sleep(2)
    waited = r.attempts()
    (host / "loadavg").write_text("23.0 24.0 30.0 1/1 1\n")  # both at or below the gate
    proc.communicate(timeout=WAIT * 3)
    assert (waited, len(r.attempts())) == ([], 1)


SLOT_RECORD = _load("lh_slot_record_for_the_launcher", KIT / "slot_record.py")  # by its path, as the readout reads


def _export(r):
    """`ladder.py status --export` of the rig's state, read back and loaded through slot_record.py by its path, as
    the readout does; the document."""
    path = r.kit.reh / "export.json"
    subprocess.run([sys.executable, "-I", str(r.kit.kit / "ladder.py"), "status", "--export", str(path)],
                   cwd=r.kit.repo, env=r.kit.env(), check=True, capture_output=True, timeout=WAIT)
    SLOT_RECORD.load(SLOT_RECORD.read(path), ladder.criterion(ladder.Ctx(r.kit.env())))
    return json.loads(path.read_text())


def test_a_match_of_the_token_scanner_at_teardown_stops_the_tranche_and_the_attempt_is_never_scored(rig):
    """The session ended normally (row 5) with reward 1; the launcher's stop makes it a stop, not a success."""
    r = rig()
    (r.lh / "standin" / "plan.json").write_text(json.dumps([{"write": {"agent/kept.log": f"x {r.canary} y"}}]))
    r.launch()
    stops = [e["reason"] for e in r.events() if e["event"] == "stop"]
    start = _export(r)["starts"][0]
    cause = "a match of token_scan.py"
    assert (stops, r.attempts()[0]["settled"]["class"], [start[k] for k in ("row", "class", "stop_cause", "reward")],
            cause in SLOT_RECORD.LAUNCHER_STOPS) == ([cause], "stop", [5, "stop", cause, None], True)


def test_the_runtime_check_scans_every_container_s_configuration_and_environment_and_a_match_stops_the_tranche(rig):
    r = rig()
    (r.lh / "standin" / "plan.json").write_text(json.dumps([{"container_env": ["PATH=/usr/bin", f"X={r.canary}"]}]))
    r.launch()
    stops = [e["reason"] for e in r.events() if e["event"] == "stop"]
    attempt_dir = r.root / "slots" / r.attempts()[0]["id"]
    kept = sorted(p.name for p in (attempt_dir / "containers").iterdir())
    assert (stops, sum(n.endswith(".inspect.json") for n in kept), sum(n.endswith(".environ") for n in kept)) == (
        ["a match of the runtime check in the attempt's containers"], 2, 2)


@pytest.mark.parametrize("behaviour, cause", [
    (lambda r: {"container_env": ["PATH=/usr/bin", f"X={r.canary}"]},
     "a match of the runtime check in the attempt's containers"),
    (lambda r: {"container_fs": None}, "an incomplete scan of the runtime check in the attempt's containers"),
    (lambda r: {"unreadable": ["verifier/blocked.bin"]}, "an incomplete scan of token_scan.py"),
    (lambda r: {"unreadable": ["agent/blocked.txt"]}, "an incomplete scan of token_scan.py")])
def test_a_teardown_scan_that_matches_or_cannot_finish_stops_the_tranche_and_exports_a_stop(rig, behaviour, cause):
    """The session ended normally (row 5) with reward 1; the stop makes it a stop with the cause slot_record.py
    accepts, never scored."""
    r = rig()
    (r.lh / "standin" / "plan.json").write_text(json.dumps([behaviour(r)]))
    r.launch()
    start = _export(r)["starts"][0]
    assert ([e["reason"] for e in r.events() if e["event"] == "stop"],
            [start[k] for k in ("row", "class", "stop_cause", "reward")]) == ([cause], [5, "stop", cause, None])


def test_the_process_environments_sampled_while_the_harness_runs_are_scanned_after_the_container_stopped(rig):
    """Task 8 m9: the token is in a process environment only (not the configuration), and the container has
    stopped by the teardown, so only the 2 s samples taken while the harness ran can show it."""
    r = rig()
    (r.lh / "standin" / "plan.json").write_text(json.dumps([{"process_env": ["PATH=/usr/bin", f"X={r.canary}"],
                                                             "sleep": 3, "stop_containers": True}]))
    r.launch()
    assert [e["reason"] for e in r.events() if e["event"] == "stop"] == [
        "a match of the runtime check in the attempt's containers"]


def test_a_launch_whose_slot_socket_never_opens_is_refused_before_the_harness_runs(rig):
    """Task 8 m9: the passthrough cannot open the slot's socket (a file is in its place), so the launcher's wait
    for it ends in a refused launch: no harness, no start."""
    r = rig()
    first = ladder.schedule(ladder.criterion(ladder.Ctx(r.kit.env())))[0]
    relay = r.root / "relay" / f"001-{ladder.slot_id(first)}"
    relay.mkdir(mode=0o700, parents=True)
    (relay / "passthrough.sock").write_text("not a socket")
    r.launch()
    assert ([e["reason"] for e in r.events() if e["event"] == "stop"], r.calls(), r.attempts()) == (
        ["refused at launch"], [], [])


@pytest.mark.parametrize("token", ["", None, "lh-fake-slot-xyz", "lh-fake-slot-" + "0" * 31])
def test_the_harness_never_starts_with_a_token_not_in_the_launcher_s_fake_form(short, token):
    """Task 8 m9: an empty token would end before the session, and any other is not the slot's."""
    with pytest.raises(ladder.Refused, match="fake token"):
        ladder.harness_env(_ctx(short), {"id": "001", "token": token})


def test_the_smoke_s_runtime_check_also_scans_the_agent_container_s_exported_file_system(rig):
    r = rig()
    (r.lh / "standin" / "plan.json").write_text(json.dumps([{"container_fs": f"etc/x {r.canary}\n"}]))
    r.launch()
    assert [e["reason"] for e in r.events() if e["event"] == "stop"] == [
        "a match of the runtime check in the attempt's containers"]


def test_after_the_smoke_read_the_pilot_s_block_runs_three_together_and_waits_for_the_pilot_s_row(rig):
    r = rig(plan=[{}, {"sleep": 2}, {"sleep": 2}, {"sleep": 2}])
    r.launch()
    r.ledger("Smoke read", f"{r.label} pass")
    code, out, err = r.launch()
    pilot = [a for a in r.attempts() if a["kind"] == "pilot"]
    starts = sorted(n["time"] for n in r.notes() if n["what"] == "started")[1:]
    assert (code, "waiting for the pilot's ledger row" in out, sorted(a["effort"] for a in pilot),
            {a["task"] for a in pilot}, starts[-1] - starts[0] < 2) == (
        0, True, ["high", "low", "medium"], {"rs-archive-clone"}, True)


def test_a_failed_smoke_stops_the_tranche_and_its_start_is_a_stop_never_scored(rig):
    """D7.1: a person reads the smoke's checks and writes the Smoke read row; on `fail` the launcher stops the tranche
    and gives the smoke's start the cause the readout reads, "a failed smoke check"."""
    r = rig()
    r.launch()
    r.ledger("Smoke read", f"{r.label} fail")
    code, out, err = r.launch()
    start = _export(r)["starts"][0]
    assert ([e["reason"] for e in r.events() if e["event"] == "stop"], len(r.attempts()),
            [start[k] for k in ("class", "stop_cause", "reward")]) == (
        ["a failed smoke"], 1, ["stop", "a failed smoke check", None])


# The schedule (D7.3, D7.4).

def _criterion(**values):
    doc = json.loads(json.dumps(CRITERION))
    for field, value in {**STAND_INS, "schedule.order.hash": ladder.ORDER_HASH, **values}.items():
        ladder._set(doc, field, value)
    return doc


ALL16 = [t["name"] for t in CRITERION["tasks"]["list"]]


def test_the_schedule_is_deterministic_begins_with_the_smoke_then_the_pilot_s_block_and_runs_in_blocks():
    one, again = (ladder.schedule(_criterion(**{"tasks.qualified": ALL16})) for _ in range(2))
    other = ladder.schedule(_criterion(**{"tasks.qualified": ALL16, "schedule.order.seed": "another seed"}))
    rounds = [e for e in one if e["kind"] == "round"]
    blocks = [[e for e in rounds if (e["round"], e["task"]) == key] for key in dict.fromkeys((e["round"], e["task"]) for e in rounds)]
    positions = [[rounds.index(e) for e in block] for block in blocks]
    assert (one == again, one != other, [(e["kind"], e["task"], e["effort"]) for e in one[:4]],
            [(e["round"], e["task"]) for e in one[4:6]], len(one),
            {len({(e["round"], e["task"], e["effort"]) for e in one})}, all(p == list(range(p[0], p[0] + len(p))) for p in positions),
            [e["round"] for e in rounds] == sorted(e["round"] for e in rounds)) == (
        True, True, [("smoke", "gsea-proteomics", "low")] + [("pilot", "rs-archive-clone", e) for e in
                                                            [x["effort"] for x in one[1:4]]],
        [(1, "gsea-proteomics")] * 2, 240, {240}, True, True)


def test_the_four_slots_already_run_are_skipped_and_only_qualified_tasks_have_blocks():
    plan = ladder.schedule(_criterion())
    keys = [(e["round"], e["task"], e["effort"]) for e in plan]
    assert (len(plan), len(set(keys)), {e["task"] for e in plan}, keys.count((1, "gsea-proteomics", "low")),
            sorted(e["effort"] for e in plan[1:4])) == (45, 45, set(TASKS), 1, ["high", "low", "medium"])


def test_cut_at_any_start_the_schedule_leaves_at_most_one_block_partial_and_no_task_more_than_a_block_behind():
    plan = ladder.schedule(_criterion(**{"tasks.qualified": ALL16}))
    worst = []
    for cut in range(len(plan) + 1):
        done = {}
        for e in plan[:cut]:
            done.setdefault(e["task"], {}).setdefault(e["round"], 0)
            done[e["task"]][e["round"]] += 1
        partial = sum(1 for rounds in done.values() for n in rounds.values() if n < 3)
        whole = [sum(1 for n in done.get(t, {}).values() if n == 3) for t in ALL16]
        worst.append((partial, max(whole) - min(whole)))
    assert (max(p for p, _ in worst[4:]), max(d for _, d in worst)) == (1, 1)


@pytest.mark.parametrize("head,rows,want", [
    ({"kind": "smoke", "round": 1}, [], None),
    ({"kind": "pilot", "round": 1}, [], "waiting for the smoke read"),
    ({"kind": "pilot", "round": 1}, [("Smoke read", "pass")], None),
    ({"kind": "round", "round": 1}, [("Smoke read", "pass")], "waiting for the pilot's ledger row"),
    ({"kind": "round", "round": 1}, [("Smoke read", "pass"), ("Pilot read", "")], None),
    ({"kind": "round", "round": 2}, [("Smoke read", "pass"), ("Pilot read", "")], "waiting for the round-one read"),
    ({"kind": "round", "round": 2}, [("Smoke read", "pass"), ("Pilot read", ""), ("Round 1 read", "")], None),
    ({"kind": "pilot", "round": 1}, [("Smoke read", "fail")], "a failed smoke")])
def test_the_schedule_waits_for_the_smoke_read_the_pilot_s_ledger_row_and_the_round_one_read(head, rows, want):
    label = "c" * 64
    text = "".join(f"| 2026-11-20 | {what} | {label} {cell} |\n" for what, cell in rows)
    assert ladder.hold(head, text, [label]) == want


def test_a_criterion_naming_another_order_hash_is_refused(short):
    kit = Kit(short)
    (kit.reh / "stand_ins.json").write_text(json.dumps({**STAND_INS, "schedule.order.hash": "md5"}))
    env = kit.env()
    kit.allowance_inputs(env)
    assert _refused(kit, env)[1].startswith("the criterion's schedule.order.hash is not the launcher's")


# The contamination scan (coordinator ruling): the frozen terms over the transcript and the exported files.

@pytest.mark.parametrize("hosts", [["relay"], HOSTS, HOSTS + ["registry.npmjs.org", "crates.io"]])
def test_the_launcher_s_overlay_copy_and_digest_are_the_oracle_check_s_byte_for_byte(short, hosts):
    """The oracle recorded each task's overlay digest with oracle_check.sh's overlay_task; the launcher checks the
    criterion's digests against its own, so both must build the same two lines."""
    package = short / "pkg"
    (package / "tests").mkdir(parents=True)
    (package / "task.toml").write_text('[task]\nname = "t"\n\n[agent]\ntimeout_sec = 28800.0\n\n[verifier]\n')
    (package / "tests" / "test.sh").write_text("#!/bin/bash\n")
    oracle = subprocess.run(["bash", "-c", 'source "$1" && shift && "$@"', "lh-test", str(KIT / "oracle_check.sh"),
                             "overlay_task", str(package), str(short / "oracle"), *hosts],
                            capture_output=True, text=True, timeout=WAIT, check=True)
    digest = ladder.overlay(package, short / "launcher", hosts)
    assert (digest, (short / "launcher" / "task.toml").read_bytes(), sorted(p.name for p in (short / "launcher").rglob("*"))) == (
        oracle.stdout.strip(), (short / "oracle" / "task.toml").read_bytes(),
        sorted(p.name for p in (short / "oracle").rglob("*")))


def test_the_contamination_scan_finds_a_term_in_the_transcript_and_in_an_exported_file_and_records_no_term(short):
    trial = short / "trial"
    (trial / "agent").mkdir(parents=True)
    (trial / "artifacts").mkdir()
    (trial / "agent" / "claude-code.txt").write_text("cd /x && cat secret-term-one/solve.sh\n")
    (trial / "artifacts" / "out.txt").write_text("nothing\nnothing then secret-term-two\n")
    (trial / "verifier").mkdir()
    (trial / "verifier" / "log.txt").write_text("secret-term-one\n")  # not the agent's: not scanned
    terms = ["secret-term-one", "secret-term-two", "absent-term"]
    found = ladder.contamination(trial, terms)
    sha = {t: hashlib.sha256(t.encode()).hexdigest() for t in terms}
    assert (found, any(t in json.dumps(found) for t in terms)) == (
        {"contaminated": True, "hits": [
            {"term_sha256": sha["secret-term-one"], "file": "agent/claude-code.txt", "offset": 13},
            {"term_sha256": sha["secret-term-two"], "file": "artifacts/out.txt", "offset": 21}], "unreadable": []},
        False)


def test_the_contamination_scan_finds_nothing_in_a_clean_trial(short):
    trial = short / "trial"
    (trial / "agent").mkdir(parents=True)
    (trial / "agent" / "claude-code.txt").write_text("all clean\n")
    assert ladder.contamination(trial, ["secret-term-one"]) == {"contaminated": False, "hits": [], "unreadable": []}


def test_a_file_the_contamination_scan_cannot_read_is_named_and_the_scan_goes_on(short):
    """token_scan.py reads the same file, and its incomplete scan stops the tranche; this scan names the file."""
    trial = short / "trial"
    (trial / "agent").mkdir(parents=True)
    (trial / "agent" / "a.txt").write_text("secret-term-one\n")
    (trial / "agent" / "b.txt").write_text("x")
    (trial / "agent" / "b.txt").chmod(0)
    found = ladder.contamination(trial, ["secret-term-one"])
    assert (found["contaminated"], found["unreadable"]) == (True, ["agent/b.txt"])


def test_the_contamination_scan_finds_a_term_split_across_a_chunk_boundary(short):
    trial = short / "trial"
    (trial / "agent").mkdir(parents=True)
    chunk = 64
    (trial / "agent" / "big.txt").write_bytes(b"x" * (chunk - 5) + b"secret-term-one" + b"y" * 200)
    found = ladder.contamination(trial, ["secret-term-one"], chunk=chunk)
    assert [(h["file"], h["offset"]) for h in found["hits"]] == [("agent/big.txt", chunk - 5)]


def test_the_canary_identifier_is_read_from_the_package_by_its_sha256(short):
    package = short / "x"
    package.mkdir()
    (package / "task.toml").write_text("# A HEADER LINE\n# made-up-canary 0f0e-11\n[task]\nname = \"t\"\n")
    assert (ladder.canary_term(package, hashlib.sha256(b"0f0e-11").hexdigest()),
            ladder.canary_term(package, "0" * 64)) == ("0f0e-11", None)


def test_a_contaminated_observation_is_recorded_unscored_and_three_tasks_with_one_of_any_class_stop_the_tranche(rig):
    r = rig(stand_ins={"readout.contamination_scan.terms": ["stand-in-term"]},
            plan=[{"write": {"agent/note.txt": "found stand-in-term here"}}])
    r.launch()
    (attempt,) = r.attempts()
    start = _export(r)["starts"][0]
    three = [{"task": t, "settled": {"class": c, "contamination": {"contaminated": True}}}
             for t, c in zip(TASKS, ("observation", "cut", "stop"))]
    loaded = SLOT_RECORD.load(SLOT_RECORD.read(r.kit.reh / "export.json"), ladder.criterion(ladder.Ctx(r.kit.env())))
    assert (attempt["settled"]["class"], start["excluded"], start["contamination"], loaded[0]["counted"],
            [e for e in r.events() if e["event"] == "stop"], ladder.contamination_stop(three[:2], CRITERION),
            ladder.contamination_stop(three, CRITERION)) == (
        "observation", None, [hashlib.sha256(b"stand-in-term").hexdigest()], False, [], None,
        "contaminated attempts on three tasks")


STANDING = _criterion()  # the criterion with the rehearsals' stand-ins, as the export reads it
SHA = hashlib.sha256(b"stand-in-term").hexdigest()


def _settled_start(short, **settled):
    """A start record as the export writes it, for one settled attempt (only the fields given differ)."""
    base = {"row": 5, "class": "observation", "reward": 1.0, "usd": 1.0, "stop": None, "minutes": 3.0,
            "tokens": dict.fromkeys(SLOT_RECORD.TOKEN_KINDS, 1), "api_retry": 0, "graded": None}
    (short / "slots" / "001").mkdir(parents=True, exist_ok=True)
    return ladder._start_record(short, {"id": "001", "index": 1, "label": "c" * 64, "round": 1, "task": "gsea-proteomics",
                                        "effort": "low", "settled": {**base, **settled}}, STANDING)


@pytest.mark.parametrize("cls,row", [("cut", 10), ("infrastructure_failure", 15), ("stop", 13)])
def test_a_contamination_hit_on_a_start_of_another_class_is_recorded_and_excludes_nothing(short, cls, row):
    start = _settled_start(short, row=row, **{"class": cls}, reward=None, stop="D5 row 13" if cls == "stop" else None,
                           contamination={"contaminated": True,
                                          "hits": [{"term_sha256": SHA, "file": "agent/x", "offset": 0}]})
    assert (start["class"], start["excluded"], start["contamination"]) == (cls, None, [SHA])


def test_a_stop_on_a_stop_row_has_no_cause_of_its_own_and_a_launcher_stop_on_another_row_names_its_cause(short):
    on_row = _settled_start(short, row=13, **{"class": "stop"}, reward=None, stop="D5 row 13")
    launcher = _settled_start(short, row=5, **{"class": "stop"}, reward=None, stop="a subagent file")
    assert [(s["class"], s["stop_cause"]) for s in (on_row, launcher)] == [("stop", None), ("stop", "a subagent file")]


def test_regrade_case_1_without_a_reward_is_exported_as_an_infrastructure_failure_and_case_2_as_indeterminate(short):
    """D5 and ladder.json (coordinator ruling, Task 5): still no reward file is an infrastructure failure."""
    case_1 = _settled_start(short, row=5, **{"class": "infrastructure_failure"}, reward=None, regrade_case=1)
    case_2 = _settled_start(short, row=6, reward=0.0, regrade_case=2, indeterminate=True)
    assert [(s["class"], s["excluded"], s["reward"]) for s in (case_1, case_2)] == [
        ("infrastructure_failure", "no reward after regrades", None), ("observation", "indeterminate", 0.0)]


def test_a_missing_figure_is_exported_as_missing_never_as_zero(short):
    nothing = dict.fromkeys(SLOT_RECORD.TOKEN_KINDS)
    start = _settled_start(short, minutes=None, tokens=nothing, api_retry=None)
    assert (start["minutes"], start["tokens"], start["api_retry"]) == (None, nothing, None)


def test_a_usage_the_meter_read_only_as_its_bound_is_exported_as_token_counts_not_recorded(short):
    """Coordinator ruling (Task 5): each token count may be null, not recorded; the export loads through
    slot_record.py with them so."""
    _closed(short, "token-three-tools-normal-end", [{"status": 200, "usage": None, "worst_case": True, "usd": 0.5}],
            reward=1.0)
    ctx = _ctx(short)
    (ctx.rehearsal / "stand_ins.json").write_text(json.dumps(STAND_INS))
    start = ladder.export(ctx, ladder.criterion(ctx))["starts"][0]
    assert (start["class"], start["tokens"]) == ("observation", dict.fromkeys(SLOT_RECORD.TOKEN_KINDS))


def test_tokens_are_missing_when_the_meter_read_a_usage_only_as_its_bound_and_zero_for_an_answer_with_none():
    usage = {"input_tokens": 3, "output_tokens": 2, "cache_read_input_tokens": 1, "cache_creation_input_tokens": 0}
    assert (ladder._tokens([{"status": 200, "usage": usage}, {"status": 429, "usage": None}, {"refused": "x"}]),
            ladder._tokens([{"status": 200, "usage": usage, "worst_case": True}]), ladder._tokens([])) == (
        {"input": 3, "output": 2, "cache_read": 1, "cache_write_5m": 0, "cache_write_1h": 0},
        dict.fromkeys(SLOT_RECORD.TOKEN_KINDS), dict.fromkeys(SLOT_RECORD.TOKEN_KINDS, 0))


@pytest.mark.parametrize("result,want", [
    (None, None), ({"agent_execution": None}, 0.0),
    ({"agent_execution": {"started_at": "2026-11-20T10:00:00Z", "finished_at": None}}, None),
    ({"agent_execution": {"started_at": "2026-11-20T10:00:00Z", "finished_at": "2026-11-20T10:45:00Z"}}, 45.0)])
def test_the_session_s_minutes_come_from_the_harness_and_are_missing_when_it_recorded_none(short, result, want):
    trial = short / "trial"
    trial.mkdir()
    if result is not None:
        (trial / "result.json").write_text(json.dumps(result))
    assert ladder.session_minutes(trial) == want


@pytest.mark.parametrize("named,want", [({"gsea-proteomics": "ctrf"}, {"passed": 7, "total": 9}), ({}, None)])
def test_graded_is_the_verifier_s_sub_tests_where_the_criterion_names_its_report(short, named, want):
    trial = short / "trial"
    (trial / "verifier").mkdir(parents=True)
    (trial / "verifier" / "ctrf.json").write_text(json.dumps({"results": {"summary": {"tests": 9, "passed": 7}}}))
    assert ladder.graded(trial, _criterion(**{"readout.graded_outcome.verifiers": named}), "gsea-proteomics") == want


def test_the_allowance_export_sums_the_weekly_points_the_owner_s_readings_show_moved(short):
    root = _state(short)
    _allowance(root, {"kind": "reading", "at": 1000.0, "weekly": 10, "weekly_reset": 5000.0, "five": 0, "five_reset": 0},
               {"kind": "reading", "at": 2000.0, "weekly": 14, "weekly_reset": 5000.0, "five": 0, "five_reset": 0},
               {"kind": "reading", "at": 6000.0, "weekly": 3, "weekly_reset": 9000.0, "five": 0, "five_reset": 0})
    one = short / "one"
    ladder.ensure_state(one)
    _allowance(one, {"kind": "reading", "at": 1000.0, "weekly": 10, "weekly_reset": 5000.0, "five": 0, "five_reset": 0})
    found = ladder.allowance_used(root)
    assert (found["weekly_points"], found["readings"].count("Allowance reading"), ladder.allowance_used(one)) == (
        7, 3, None)


def test_a_row_16_start_is_exported_only_under_the_row_the_ledger_s_ruling_names(short):
    root, attempt, record = _closed(short, "token-usage-limit-NonZeroAgentExitCodeError", [{"status": 429}])
    ctx = _ctx(short)
    (ctx.rehearsal / "stand_ins.json").write_text(json.dumps(STAND_INS))
    with pytest.raises(ladder.Refused) as waiting:
        ladder.export(ctx, ladder.criterion(ctx))
    argv = ["ruling", attempt["id"], "--row", "10", "--date", "2026-11-21"]
    unruled = ladder.main(argv, env=ctx.env)
    (ctx.rehearsal / "ledger.md").write_text(f"| 2026-11-21 | Ruling | {attempt['id']} row 10: a usage limit |\n")
    ruled = ladder.main(argv, env=ctx.env)
    start = ladder.export(ctx, ladder.criterion(ctx))["starts"][0]
    assert (record["class"], attempt["id"] in str(waiting.value), unruled, ruled, start["row"], start["class"],
            ladder.queue(root, ladder.schedule(STANDING))[0].get("rerun_of")) == (
        "ruling", True, 3, 0, 10, "cut", attempt["id"])


def test_the_launcher_refuses_to_write_an_export_the_readout_would_refuse(short):
    root, attempt, record = _closed(short, "token-three-tools-normal-end", [], reward=0.5)  # not 0, 1 or null
    ctx = _ctx(short)
    (ctx.rehearsal / "stand_ins.json").write_text(json.dumps(STAND_INS))
    with pytest.raises(ladder.Refused) as refused:
        ladder.export(ctx, ladder.criterion(ctx))
    assert str(refused.value).startswith("the export does not fit slot_record.py")


# D7.7's count thresholds (coordinator ruling): a stop or pause by one is lifted only by `ladder.py resume --clears`,
# after a ledger Ruling row; the cleared threshold then counts only the endings after its clearing.

def _ended(root, specs, at):
    """Settled attempts after any already there, one per (class, row, effort, load_refused), closing from `at` on."""
    start = len(list((root / "slots").iterdir()))
    for i, (cls, row, effort, load) in enumerate(specs, start + 1):
        folder = root / "slots" / f"{i:03d}-r1-gsea-proteomics-{effort}"
        folder.mkdir(mode=0o700)
        (folder / "slot.json").write_text(json.dumps({"id": folder.name, "index": i, "task": "gsea-proteomics",
                                                      "effort": effort, "round": 1, "kind": "round"}))
        (folder / "settled.json").write_text(json.dumps({"class": cls, "row": row, "closed": at + i,
                                                         "load_refused": load, "usd": 0.1}))


OBS, INFRA, CUT, PRE = ("observation", 5), ("infrastructure_failure", 4), ("cut", 10), ("pre_session_failure", 1)
EFFS = ("low", "medium", "high")


def _specs(cls_row, n, load=False):
    return [(*cls_row, EFFS[i % 3], load) for i in range(n)]


THRESHOLD_CASES = {  # name: (kind, endings that trip it)
    "infrastructure-failures": ("stop", _specs(OBS, 20) + _specs(INFRA, 3)),
    "infrastructure-failures at one level": ("stop", [(*OBS, "high", False)] * 2 + [(*INFRA, "high", False)]),
    "pre-session-failures": ("stop", _specs(PRE, 5)),
    "pre-session-failures in all": ("stop", [x for _ in range(24) for x in (_specs(OBS, 1)[0], _specs(PRE, 1)[0])]),
    "cuts": ("pause", _specs(OBS, 19) + _specs(CUT, 2)),
    "load-refusals": ("pause", _specs(("infrastructure_failure", 15), 3, load=True))}


def _threshold_rig(short):
    ctx = _ctx(short)
    ladder.ensure_state(ctx.root)
    (ctx.rehearsal / "stand_ins.json").write_text(json.dumps(STAND_INS))
    return ctx


@pytest.mark.parametrize("case", sorted(THRESHOLD_CASES))
def test_a_d77_threshold_trips_is_lifted_only_by_a_clearing_after_its_ruling_and_then_counts_new_endings(short, case):
    name, (kind, specs) = case.split(" ")[0], THRESHOLD_CASES[case]
    ctx = _threshold_rig(short)
    _ended(ctx.root, specs[:-1], time.time() - 600)
    below = ladder.threshold_breaches(ctx.root, STANDING)
    _ended(ctx.root, specs[-1:], time.time() - 300)
    ladder.check_thresholds(ctx.root, STANDING)
    ladder.check_thresholds(ctx.root, STANDING)  # a second look writes no second event
    tripped = [(e["event"], e["threshold"]) for e in _jsonl_events(ctx)]
    plain = ladder.main(["resume"], env=ctx.env)
    clearing = ["resume", "--clears", name, "--date", "2026-11-22"]
    unruled = ladder.main(clearing, env=ctx.env)
    (ctx.rehearsal / "ledger.md").write_text(f"| 2026-11-22 | Ruling | {name}: go on, the host was repaired |\n")
    cleared = ladder.main(clearing, env=ctx.env)
    after = ladder.threshold_breaches(ctx.root, STANDING)
    _ended(ctx.root, specs, time.time())  # the same endings again, after the clearing
    again = ladder.threshold_breaches(ctx.root, STANDING)
    record = ladder._jsonl(ctx.root / "clearings.jsonl")
    assert (name in below, tripped, plain, unruled, cleared, [e["event"] for e in _jsonl_events(ctx)][-1], after,
            name in again, [(r["threshold"], r["date"], bool(r["counts"])) for r in record]) == (
        False, [(kind, name)], 3, 3, 0, "resume", {}, True, [(name, "2026-11-22", True)])


@pytest.mark.parametrize("specs", [_specs(OBS, 8) + _specs(CUT, 2),  # 20% of cuts, but under 20 starts
                                   [(*INFRA, "high", False), (*OBS, "high", False)]])  # under a block at one level
def test_a_share_is_not_judged_before_its_minimum_of_starts(short, specs):
    ctx = _threshold_rig(short)
    _ended(ctx.root, specs, time.time() - 60)
    assert ladder.threshold_breaches(ctx.root, STANDING) == {}


def test_an_attempt_ended_by_a_load_refusal_is_marked_from_the_tranche_s_rows_as_row_15_reads_them():
    rows = [{"slot": None, "status": 403, "refused": "too many connections"}]  # at the cap: no slot known yet
    assert (ladder._load_refused(rows, STANDING), ladder._load_refused([{"slot": "a", "refused": "slot cap reached"}],
                                                                       STANDING)) == (True, False)


def test_the_launch_loop_stops_on_a_threshold_over_its_bound_before_any_start(rig):
    r = rig()
    _ended(r.root, _specs(PRE, 5), time.time() - 60)
    code, out, err = r.launch()
    assert (code, [(e["event"], e.get("threshold")) for e in r.events()], r.calls()) == (
        0, [("stop", "pre-session-failures")], [])


def test_a_plain_resume_is_recorded_when_no_threshold_is_over_its_bound(short):
    ctx = _threshold_rig(short)
    _ended(ctx.root, _specs(OBS, 3), time.time() - 60)
    assert (ladder.main(["resume"], env=ctx.env), [e["event"] for e in _jsonl_events(ctx)]) == (0, ["resume"])


def test_clearing_one_threshold_does_not_resume_while_another_is_over_its_bound(short):
    ctx = _threshold_rig(short)
    _ended(ctx.root, _specs(PRE, 5) + _specs(("infrastructure_failure", 15), 3, load=True), time.time() - 60)
    (ctx.rehearsal / "ledger.md").write_text("| 2026-11-22 | Ruling | load-refusals: the cap was raised |\n")
    code = ladder.main(["resume", "--clears", "load-refusals", "--date", "2026-11-22"], env=ctx.env)
    assert (code, ladder._jsonl(ctx.root / "clearings.jsonl"), _jsonl_events(ctx)) == (3, [], [])


def _jsonl_events(ctx):
    return ladder._jsonl(ctx.root / "passthrough" / "tranche.jsonl")


# The export the readout reads: slot_record.py (from feat/lh-readout), loaded by its path as the readout does.

def test_an_export_of_a_rehearsal_run_loads_through_slot_record(rig):
    r = rig()
    r.launch()
    now = time.time()  # the owner's second reading: the weekly meter moved two points since the rig's first
    _allowance(r.root, {"kind": "reading", "at": now, "weekly": 2, "five": 1, "weekly_reset": now + DAY,
                        "five_reset": now + 3600})
    doc = _export(r)  # read and loaded through slot_record.py by its path
    start = doc["starts"][0]
    assert (doc["label"], start["label"], sorted(start["tokens"]), start["api_retry"], start["minutes"],
            start["egress_refused"], sum(s["pilot"] for s in doc["slots"]), doc["allowance"]["weekly_points"]) == (
        r.label, r.label, sorted(SLOT_RECORD.TOKEN_KINDS), 0, 30.0, {"203.0.113.9:443": 1}, 3, 2)
