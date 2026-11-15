"""The long-horizon launcher (plan docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md, Task 5).

Usage (from the repository root, or a detached checkout of the frozen commit for a live launch):
  python -I experiments/long_horizon_tasks/ladder.py plan       the schedule, in the order it runs
  python -I experiments/long_horizon_tasks/ladder.py launch     run the tranche until it ends, waits or stops
  python -I experiments/long_horizon_tasks/ladder.py status     starts, money, slots, gates, the passthrough
  python -I experiments/long_horizon_tasks/ladder.py allowance (inputs|reading|figures) ...
                                                                 the owner's inputs and meter readings (D4)

A live launch needs LH_SPEND_AUTHORIZED=yes, LH_MANIFEST_SHA256 and LH_RUNTIME_COMMIT (both from the ledger's
current `Configuration label` row). A rehearsal needs LH_REHEARSAL=<dir> and refuses if a spend variable is set.
The token file is named only to the passthrough: the launcher refuses to run while LH_TOKEN_FILE is in its
environment, and builds the harness's environment from nothing, so neither holds a credential. LH names the
cache (default ~/lh-cache: hvenv/, logs/, tasks41/).

The criterion is ladder.json. A live launch refuses while the manifest is unfrozen or any field is pending; a
rehearsal takes a stand-in for every pending field from LH_REHEARSAL/stand_ins.json ({field: value}), and reads
its ledger from LH_REHEARSAL/ledger.md. A live launch reads the ledger as committed on `main`.

State lives outside the checkout: $HOME/.local/state/lh-ladder, or LH_REHEARSAL/state. In it:
  passthrough/    the passthrough's --state directory (mode 700); slots.json in it is the slots file the
                  launcher writes and the passthrough re-reads at every request
  relay/          the relay's socket directory (mode 700)
  slots/<id>/     one directory per attempt, claimed by mkdir: slot.json (the queue entry, its reservation, the
                  fake token, the launcher's pid and start time, the harness's), and later settled.json
  allowance.jsonl the owner's inputs, meter readings and the pilot's figures, appended (their history)
  money.lock      the one lock under which starts are counted, reserved and settled
The passthrough is started by a person with the token file; `status` prints its command line.
"""

import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import tomllib
from pathlib import Path

KIT = Path(__file__).resolve().parent
ROOT = KIT.parents[1]
PLAN = "docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md"
MODEL = "claude-haiku-5-5"  # the only model; the launcher refuses a criterion that names another
EFFORTS = ("low", "medium", "high")  # the only efforts
SPEND_VARS = ("LH_SPEND_AUTHORIZED", "LH_MANIFEST_SHA256", "LH_RUNTIME_COMMIT")
FAKE_TOKEN = re.compile(r"lh-fake-slot-[0-9a-f]{32}")  # credential.fake_token: the form Task 2a recorded
PACKAGES = "tasks41"  # $LH/tasks41/<task>/x: the 4.1.0 packages, fetched by digest (tasks.json)
HOST_NAMES = {"localhost", "host.containers.internal", "host.docker.internal", "gateway"}
VERSIONS = ("import importlib.metadata as m, json; "
            "print(json.dumps({'harbor': m.version('harbor'), 'podman_compose': m.version('podman-compose')}))")
DIGEST = ("import sys; from pathlib import Path; from harbor.publisher.packager import Packager; "
          "print(Packager.compute_content_hash(Path(sys.argv[1]))[0])")


class Refused(Exception):
    """The launcher refuses: nothing was started. The message names the reason and never a secret."""


def _kit(name):
    spec = importlib.util.spec_from_file_location(f"lh_ladder_{name}", KIT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manifest = _kit("manifest")


def _read_json(path):
    return json.loads(Path(path).read_text())


def _at(doc, field):
    for key in field.split("."):
        doc = doc[key]
    return doc


def _set(doc, field, value):
    *path, last = field.split(".")
    for key in path:
        doc = doc[key]
    doc[last] = value


# ---- the context: mode, state root, criterion, ledger -------------------------------------------------------


class Ctx:
    """Where this run's inputs and state are, read from the environment once."""

    def __init__(self, env):
        self.env = dict(env)
        reh = env.get("LH_REHEARSAL")
        self.rehearsal = Path(reh).resolve() if reh else None
        home = Path(env.get("HOME") or os.path.expanduser("~"))
        self.lh = Path(env.get("LH") or home / "lh-cache")
        self.home = home
        self.root = self.rehearsal / "state" if self.rehearsal else home / ".local" / "state" / "lh-ladder"

    @property
    def live(self):
        return self.rehearsal is None


def mode_refusal(env):
    """Why this environment may not run the launcher at all, or None."""
    if env.get("LH_TOKEN_FILE"):
        return "LH_TOKEN_FILE is set: the token file is named only to the passthrough, never to the launcher"
    if env.get("LH_REHEARSAL"):
        spend = [name for name in SPEND_VARS if env.get(name)]
        return f"a rehearsal with a spend variable set ({', '.join(spend)})" if spend else None
    if env.get("LH_SPEND_AUTHORIZED") != "yes":
        return "no authorization: a live launch needs LH_SPEND_AUTHORIZED=yes (or LH_REHEARSAL=<dir>)"
    return None


def ledger_cells(text, what):
    """The third cell of every ledger table row whose second cell is exactly `what`, in file order."""
    cells = []
    for line in text.splitlines():
        parts = line.split("|")
        if line.startswith("| ") and len(parts) >= 5 and parts[2].strip() == what:
            cells.append(parts[3].strip())
    return cells


LABEL_ROW = re.compile(r"([0-9a-f]{64}) ([0-9a-f]{40})(?:[ .]|$)")


def current_label(text):
    """(manifest SHA-256, runtime commit) of the ledger's last `Configuration label` row, or None."""
    found = [m.groups() for m in map(LABEL_ROW.match, ledger_cells(text, "Configuration label")) if m]
    return found[-1] if found else None


def _git(*args, cwd=ROOT):
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else None


def ledger_text(ctx):
    """The ledger: the plan as committed on `main` for a live launch; LH_REHEARSAL/ledger.md in a rehearsal."""
    if ctx.rehearsal:
        path = ctx.rehearsal / "ledger.md"
        return path.read_text() if path.is_file() else ""
    text = _git("show", f"main:{PLAN}")
    if text is None:
        raise Refused(f"the ledger cannot be read from main:{PLAN}")
    return text


def _manifest_refusal(live):
    recorded = _read_json(manifest.MANIFEST)
    changed = sorted(p for p in recorded["files"].keys() | manifest.files().keys()
                     if recorded["files"].get(p) != manifest.files().get(p))
    if changed:
        return f"the manifest does not match the kit: {', '.join(changed[:5])}"
    if live and not recorded["frozen"]:
        return "the manifest is not frozen"
    return None


def criterion(ctx):
    """ladder.json; live, with nothing pending; in a rehearsal, every pending field set to its stand-in."""
    ladder = _read_json(KIT / "ladder.json")
    if ctx.live:
        gaps = manifest.freeze_gaps(ladder)
        if gaps:
            raise Refused(f"the criterion is not ready to freeze: {gaps[0]}")
        return ladder
    path = ctx.rehearsal / "stand_ins.json"
    stand_ins = _read_json(path) if path.is_file() else {}
    missing = [p["field"] for p in ladder["pending"] if p["field"] not in stand_ins]
    if missing:
        raise Refused(f"no stand-in in {path} for the pending field {missing[0]}")
    for entry in ladder["pending"]:
        _set(ladder, entry["field"], stand_ins[entry["field"]])
    return ladder


def _live_refusal(ctx):
    """A live launch: the manifest and runtime commit the ledger names, the detached checkout, a clean kit."""
    sha = hashlib.sha256(manifest.MANIFEST.read_bytes()).hexdigest()
    if ctx.env.get("LH_MANIFEST_SHA256") != sha:
        return f"LH_MANIFEST_SHA256 is not this checkout's manifest {sha}"
    label = current_label(ledger_text(ctx))
    if label is None or label[0] != sha:
        return f"the manifest {sha} is not the ledger's current configuration label"
    head = _git("rev-parse", "HEAD")
    if ctx.env.get("LH_RUNTIME_COMMIT") != head or label[1] != head:
        return f"LH_RUNTIME_COMMIT and the ledger's runtime commit must both be this checkout's commit {head}"
    if _git("symbolic-ref", "-q", "HEAD") is not None:
        return "the launcher runs from a detached checkout of the frozen commit, not from a branch"
    dirty = _git("status", "--porcelain", "--", "experiments/long_horizon_tasks", "orchestrator")
    if dirty is None or dirty:
        return "the kit has uncommitted changes"
    return None


def _criterion_refusal(ladder):
    attempt = ladder["attempt"]
    if attempt["model"] != MODEL or ladder["harness"]["model_argument"] != f"anthropic/{MODEL}":
        return f"the criterion's model is not {MODEL}"
    if tuple(attempt["efforts"]) != EFFORTS:
        return f"the criterion's efforts are not {', '.join(EFFORTS)}"
    return None


def _host_names():
    names = set(HOST_NAMES)
    for name in (socket.gethostname(), socket.getfqdn()):
        names |= {name.lower(), name.lower().split(".")[0]}
    return names


def _address(entry):
    try:
        ipaddress.ip_address(entry.strip("[]"))
        return True
    except ValueError:
        return False


def allowlist(ladder, task=None):
    """The agent phase's hosts: the frozen list, then the task's extra hosts (D3)."""
    extra = (ladder["tasks"]["extra_hosts"] or {}).get(task) or [] if task else []
    return list(ladder["network"]["agent_phase"]["allowed_hosts"]) + list(extra)


def allowlist_refusal(ladder):
    """An entry that names the host (an address, a port, the host's own names): the host's address is never
    listed, because a listed address opens every port of it (D3)."""
    tasks = [t["name"] for t in ladder["tasks"]["list"]]
    hosts = {h for task in [None, *tasks] for h in allowlist(ladder, task)}
    names = _host_names()
    bad = sorted(h for h in hosts if _address(h) or ":" in h or h.lower() in names)
    return f"the allowlist names an address of the host: {', '.join(bad)}" if bad else None


def clean_path(ctx):
    """The PATH of every command the launcher runs: the provider guard first, then the harness's venv."""
    return os.pathsep.join([str(ROOT / "experiments" / "thread_m" / "no_provider"), str(ctx.lh / "hvenv" / "bin"),
                            "/usr/local/bin", "/usr/bin", "/bin"])


def base_env(ctx):
    """The environment every command starts from: nothing inherited but HOME and the runtime directory."""
    return {"HOME": str(ctx.home), "PATH": clean_path(ctx), "HARBOR_TELEMETRY": "0", "DO_NOT_TRACK": "1",
            "XDG_RUNTIME_DIR": ctx.env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"}


def venv_python(ctx, *args):
    """Run the harness venv's Python on `args`; its stdout, or Refused."""
    python = ctx.lh / "hvenv" / "bin" / "python"
    done = subprocess.run([str(python), "-I", *args], capture_output=True, text=True, env=base_env(ctx),
                          timeout=600, check=False)
    if done.returncode != 0:
        raise Refused(f"the harness's Python failed ({done.returncode}) on {args[0]}")
    return done.stdout.strip()


def harness_refusal(ctx, ladder):
    """Another harness environment, or a missing or changed host-side override (D1, D2)."""
    want = {"harbor": ladder["harness"]["harbor"], "podman_compose": ladder["harness"]["podman_compose"]}
    if json.loads(venv_python(ctx, "-c", VERSIONS)) != want:
        return f"the harness environment is not {want}"
    side = ladder["harness"]["host_side"]
    files = {ctx.lh / "logs" / "containers-override.conf": side["containers_override"]["content"],
             ctx.lh / "logs" / "limits-compose.yaml": side["limits_compose"]["content"]}
    for path, content in files.items():
        if not path.is_file() or path.read_text() != content:
            return f"the host-side override {path} is missing or not the criterion's"
    if not (KIT / side["wrapper"]).is_file() or not (KIT / side["relay_compose"]).is_file():
        return "the harness wrapper or the relay's compose file is missing"
    return None


def _task_record(ladder, task):
    tasks = _read_json(KIT / "tasks.json")["tasks"]
    return next(t for t in tasks if t["name"].rsplit("/", 1)[-1] == task)


def package(ctx, task):
    return ctx.lh / PACKAGES / task / "x"


def task_refusal(ctx, ladder, task):
    """A task whose package differs from its 4.1.0 digest, or whose pinned images differ from tasks.json (D1)."""
    record, path = _task_record(ladder, task), package(ctx, task)
    if not (path / "task.toml").is_file():
        return f"{task}: no package at {path}"
    if "sha256:" + venv_python(ctx, "-c", DIGEST, str(path)) != record["digest_4_1_0"]:
        return f"{task}: the package's digest is not its 4.1.0 digest"
    toml = tomllib.loads((path / "task.toml").read_text())
    images = (toml.get("environment", {}).get("docker_image"),
              toml.get("verifier", {}).get("environment", {}).get("docker_image"))
    if images != (record["environment_image"], record["verifier_image"]):
        return f"{task}: an image the package pins is not the one tasks.json pins"
    if set(toml.get("agent", {})) & set(ladder["network"]["overlay_keys"]):
        return f"{task}: the package already sets an agent-phase network key"
    return None


def qualified(ladder):
    """The qualified tasks, in tasks.json order."""
    names = [t["name"] for t in ladder["tasks"]["list"]]
    return [n for n in names if n in set(ladder["tasks"]["qualified"])]


def allowance_inputs(ctx):
    """The owner's last fixed inputs (F-week, F-five, hours), or None."""
    rows = [r for r in _jsonl(ctx.root / "allowance.jsonl") if r.get("kind") == "inputs"]
    return rows[-1] if rows else None


def _jsonl(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.is_file() else []


def preflight(ctx):
    """Every refusal of Task 5's first checkbox that holds before an attempt; the criterion, or Refused."""
    for check in (lambda: mode_refusal(ctx.env), lambda: _manifest_refusal(ctx.live),
                  lambda: _live_refusal(ctx) if ctx.live else None):
        reason = check()
        if reason:
            raise Refused(reason)
    ladder = criterion(ctx)
    reason = _criterion_refusal(ladder) or allowlist_refusal(ladder) or harness_refusal(ctx, ladder)
    reason = reason or next(filter(None, (task_refusal(ctx, ladder, t) for t in qualified(ladder))), None)
    if reason:
        raise Refused(reason)
    if allowance_inputs(ctx) is None:
        raise Refused("no allowance inputs: the owner's F-week, F-five and hours (`ladder.py allowance inputs`)")
    return ladder


def token_refusal(token):
    """A slot's fake token not in the launcher's form; an empty one would end before the session as a
    RuntimeError naming CLAUDE_FORCE_OAUTH (fixture token-forced-empty-RuntimeError)."""
    return None if isinstance(token, str) and FAKE_TOKEN.fullmatch(token) else "a slot without a fake token in the launcher's form"


# ---- the command line ---------------------------------------------------------------------------------------


def main(argv=None, env=None):
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "launch", "status"):
        sub.add_parser(name)
    args = parser.parse_args(argv)
    ctx = Ctx(env)
    try:
        if args.command == "launch":
            preflight(ctx)
            return 0
        reason = mode_refusal(env)
        if reason:
            raise Refused(reason)
        return 0
    except Refused as refused:
        print(f"ladder.py: refused: {refused}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
