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
import time
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


# ---- the reader of ladder.json's pattern language (classification.fields and .tests; D5) -------------------
# The one reader: the criterion's tests (test_long_horizon_ladder.py) import it from here. A session is a fixture's
# shape (fixtures/*.json, as cut_fixture.py writes it) with `_log`, the passthrough's log as log_view reads it. The
# launcher builds the same shape from a harness trial (session_of), keeping every event of the stream, and leaves
# `harness_exception` out when the harness wrote no result: then the field `harness` is absent (D5 row 4).

MISSING = object()


def result_event(fx):
    found = [e for e in fx.get("stream_tail") or [] if e.get("type") == "result"]
    return found[-1] if found else MISSING


def stream_of(fx, kind):
    return [e for e in fx.get("stream_tail") or [] if e.get("type") == kind]


STREAM = {"events": lambda fx: fx["n_events"], "api_retry": lambda fx: fx["n_api_retry"],
          "system_subtypes": lambda fx: [e.get("subtype") for e in stream_of(fx, "system")],
          "rate_limit": lambda fx: [e["rate_limit_info"] for e in stream_of(fx, "rate_limit_event")]}
HARNESS = {"exception": "harness_exception", "message": "exception_message"}


def field(fx, name):
    """The value a rule's field names in a session, or MISSING (an unknown field is MISSING everywhere)."""
    head, _, key = name.partition(".")
    if head == "result":
        result = result_event(fx)
        return result if not key or result is MISSING else result.get(key, MISSING)
    if head == "harness":
        if "harness_exception" not in fx:  # the harness wrote no result
            return MISSING
        return fx if not key else fx.get(HARNESS.get(key), MISSING)
    if head == "passthrough":
        return fx.get("_log", {}).get(key, MISSING)
    return STREAM[key](fx) if head == "stream" and key in STREAM else MISSING


def like(pattern, value):
    if isinstance(pattern, dict):
        return isinstance(value, dict) and all(k in value and like(p, value[k]) for k, p in pattern.items())
    return pattern == "*" or pattern == value


OPS = {"absent": lambda arg, v: (v is MISSING) == arg, "null": lambda arg, v: (v is None) == arg,
       "in": lambda arg, v: v is not MISSING and v in arg, "not_in": lambda arg, v: v is MISSING or v not in arg,
       "contains": lambda arg, v: isinstance(v, str) and arg in v,
       "lacks": lambda arg, v: isinstance(v, str) and arg not in v,
       "some": lambda arg, v: isinstance(v, list) and any(like(arg, x) for x in v),
       "none": lambda arg, v: isinstance(v, list) and not any(like(arg, x) for x in v)}


def holds(test, value):
    if isinstance(test, dict) and len(test) == 1 and next(iter(test)) in OPS:
        (op, arg), = test.items()
        return OPS[op](arg, value)
    return value is not MISSING and value == test


def alts(row):
    return [] if row["match"] == "otherwise" else row["match"]


def matches(row, session):
    return any(all(holds(t, field(session, f)) for f, t in alt.items()) for alt in alts(row)) or not alts(row)


def classify(session, ladder, order=None):
    """The D5 row of a session: the rows tried in the criterion's order, the first match deciding."""
    rows = {row["row"]: row for row in ladder["classification"]["rows"]}
    return next(n for n in order or ladder["classification"]["order"] if matches(rows[n], session))


OWN_STOPS = {"paid extra usage": lambda row: row.get("passed_on") is False,  # classification.own_stops
             "token in a log row": lambda row: "withheld" in row,
             "response model": lambda row: row.get("response_model") not in (None, MODEL)}


def log_view(rows, ended_at=None, slot=None):
    """The passthrough's log as the rules read it (classification.fields): the slot's rows (`slot`, or every row
    naming a slot when none is given); those timed before the session's ending (every one when no ending was
    recorded); the tranche's rows; the stops the slot's rows show."""
    own = [row for row in rows if (row.get("slot") == slot if slot else row.get("slot"))]
    return {"requests": own, "tranche_requests": rows,
            "requests_before_ending": [row for row in own if ended_at is None or row["time"] < ended_at],
            "own_stops": [cause for cause, shows in OWN_STOPS.items() if any(map(shows, own))]}


# ---- state and money (D4: reservation, settlement, the ceiling) ---------------------------------------------

price_check = _kit("price_check")
RULE = price_check.load_rule()
sys.path.insert(0, str(ROOT))
from orchestrator.providers import pricing, usage  # noqa: E402  (the package's usage reader and price table)

TABLE = pricing.load_price_table(ROOT / "orchestrator" / "providers" / "price_table.json")
STREAM_JSON = "claude_stream_json_stdout"  # usage.py's metadata mode for the CLI's stream


class Full:
    """A start that cannot be made now: `reason` is "240 starts" or "does not fit"."""

    def __init__(self, reason):
        self.reason = reason


def ensure_state(root):
    """The state root, its passthrough and relay directories (mode 700) and an empty slots file."""
    for path in (root, root / "passthrough", root / "relay", root / "slots"):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not (root / "passthrough" / "slots.json").exists():
        _write_json(root / "passthrough" / "slots.json", {"total_usd": 200.0, "total_requests": None, "slots": {}})


def _write_json(path, doc):
    """Replace `path` whole (a reader never sees half a file)."""
    tmp = path.with_name(path.name + ".new")
    tmp.write_text(json.dumps(doc, indent=1) + "\n")
    os.replace(tmp, path)


class _Lock:
    """The one lock under which starts are counted, reserved and settled, shared by every launcher process."""

    def __init__(self, root):
        self.path = root / "money.lock"

    def __enter__(self):
        import fcntl
        self.fh = open(self.path, "a")
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        self.fh.close()


def process_start(pid):
    """A process's start time in clock ticks since boot (/proc/<pid>/stat field 22), or None when it is gone."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    return int(stat.rsplit(")", 1)[1].split()[19])


def attempts(root):
    """Every attempt: its slot.json with its settled.json, if any, under `settled`; in claim order."""
    found = []
    for path in sorted((root / "slots").iterdir()) if (root / "slots").is_dir() else []:
        if (path / "slot.json").is_file():
            settled = path / "settled.json"
            found.append({**_read_json(path / "slot.json"), "settled": _read_json(settled) if settled.is_file() else None})
    return found


def _counts(ladder, attempt):
    """(counts as a start, counts against the ceiling) for one attempt: open ones count fully."""
    if attempt["settled"] is None:
        return True, True
    cls = ladder["classification"]["classes"][attempt["settled"]["class"]]
    return bool(cls["starts"]), bool(cls["usd"])


def tally(root, ladder, prior):
    """(starts, committed USD, open attempts): committed is the live probe's usage + the settled cost of every
    start + every open reservation (D4)."""
    every = attempts(root)
    starts = sum(_counts(ladder, a)[0] for a in every)
    settled = sum(a["settled"]["usd"] for a in every if a["settled"] and _counts(ladder, a)[1])
    open_ = [a for a in every if a["settled"] is None]
    return starts, round(prior + settled + sum(a["reservation_usd"] for a in open_), 6), open_


def cap(ladder, task):
    return next(t["cap_usd"] for t in ladder["tasks"]["list"] if t["name"] == task)


def _slots_file(root, ladder, prior):
    """The passthrough's slots file: every open attempt's fake token and cap; the total is the ceiling less the
    live probe's usage."""
    slots = {a["id"]: {"token": a["token"], "cap_usd": a["cap_usd"], "cap_requests": None}
             for a in attempts(root) if a["settled"] is None}
    total = round(ladder["ceiling"]["total_usd"] - prior, 6)
    _write_json(root / "passthrough" / "slots.json", {"total_usd": total, "total_requests": None, "slots": slots})


def reserve(root, entry, ladder, prior):
    """Claim an attempt for `entry` (round, task, effort, kind) under the lock if it fits: the new attempt, or Full.
    Its directory is claimed by mkdir; its fake token goes into the slots file before the lock is let go."""
    reservation = round(cap(ladder, entry["task"]) + ladder["ceiling"]["reservation"]["margin_usd"], 2)
    with _Lock(root):
        starts, committed, _ = tally(root, ladder, prior)
        if starts >= ladder["ceiling"]["starts"]:
            return Full("240 starts")
        if round(committed + reservation, 6) > ladder["ceiling"]["total_usd"]:
            return Full("does not fit")
        index = len(list((root / "slots").iterdir())) + 1
        name = f"{index:03d}-r{entry['round']}-{entry['task']}-{entry['effort']}"
        (root / "slots" / name).mkdir(mode=0o700)  # the claim: a second claimant fails here
        attempt = {**entry, "id": name, "index": index, "cap_usd": cap(ladder, entry["task"]),
                   "reservation_usd": reservation, "token": "lh-fake-slot-" + os.urandom(16).hex(),
                   "launcher": {"pid": os.getpid(), "start": process_start(os.getpid())}, "opened": time.time()}
        _write_json(root / "slots" / name / "slot.json", attempt)
        _slots_file(root, ladder, prior)
    return attempt


def settle(root, attempt, record, ladder=None, prior=0.0):
    """Close the attempt: its settlement replaces its reservation, and its fake token leaves the slots file."""
    ladder = ladder or _read_json(KIT / "ladder.json")
    with _Lock(root):
        _write_json(root / "slots" / attempt["id"] / "settled.json", {**record, "closed": time.time()})
        _slots_file(root, ladder, prior)


def next_start(root, queue, ladder, prior):
    """("start", attempt) for the head of the queue, ("wait", why) or ("end", why). Only the head is ever tried: a
    slot that does not fit waits for the attempts in flight, and the launcher never skips ahead (D4, D7.4)."""
    if not queue:
        return "end", "the schedule is done"
    got = reserve(root, queue[0], ladder, prior)
    if isinstance(got, dict):
        return "start", got
    if got.reason == "240 starts":
        return "end", "240 starts"
    if tally(root, ladder, prior)[2]:
        return "wait", "the next slot's reservation does not fit while attempts are in flight"
    return "end", "nothing in flight and the next slot's reservation does not fit"


def prior_usd(ctx):
    """The live probe's priced usage (D4: settled into committed before the first attempt), from its request log.
    In a rehearsal, LH_REHEARSAL/probe/requests.jsonl stands in for it, and none means none."""
    log = (ctx.rehearsal / "probe" if ctx.rehearsal else ctx.home / ".local/state/lh-probe/passthrough") / "requests.jsonl"
    if ctx.live and not log.is_file():
        raise Refused(f"the live probe's priced usage cannot be read: no {log}")
    return sum(row.get("usd") or 0.0 for row in _jsonl(log))


def trial_dir(attempt_dir):
    """The harness's trial directory of an attempt (jobs/<job>/<trial>/), or None."""
    found = sorted(p for p in (attempt_dir / "jobs").glob("*/*") if p.is_dir())
    return found[0] if found else None


def stream_events(trial):
    """The agent's stream (agent/claude-code.txt) as events; ValueError on a line that is not one."""
    path = trial / "agent" / "claude-code.txt" if trial else None
    if path is None or not path.is_file():
        return []
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def last_result(events):
    found = [e for e in events if isinstance(e, dict) and e.get("type") == "result"]
    return found[-1] if found else None


def _meter(rows):
    """Figure 1: the passthrough's meter, the priced usage of the slot's forwarded requests."""
    forwarded = [row for row in rows if "refused" not in row]
    if any(not isinstance(row.get("usd") or 0.0, (int, float)) for row in forwarded):
        raise ValueError("a meter row without a price")
    return sum(row.get("usd") or 0.0 for row in forwarded)


def _session(trial):
    """Figure 2: the session file's rows priced by the rule, one row per message id."""
    return sum(price_check.price(u, RULE) for u in price_check.requests(trial)) if trial else None


def _model_usage(trial):
    """Figure 4: the result's modelUsage at the base rates, by the package's usage reader and price table."""
    path = trial / "agent" / "claude-code.txt" if trial else None
    if path is None or not path.is_file():
        return None
    read = usage.usage_from_stdout(STREAM_JSON, path.read_bytes(), model=MODEL)
    if read.get("status") != "reported":
        if read.get("reason") == "malformed":
            raise ValueError("the stream is malformed")
        return None
    return pricing.priced(read["rows"], TABLE) if read["source"] == "result.modelUsage" else None


def settlement(attempt_dir, rows, reservation):
    """The largest of the four figures of D4; the result's `usage` and the stream events' usage are never read.
    A figure that cannot be read settles the attempt at its full reservation."""
    trial, figures, unreadable = trial_dir(attempt_dir), {}, []
    readers = {"meter": lambda: _meter(rows), "session": lambda: _session(trial),
               "result": lambda: (last_result(stream_events(trial)) or {}).get("total_cost_usd"),
               "model_usage": lambda: _model_usage(trial)}
    for name, read in readers.items():
        try:
            figures[name] = read()
        except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:  # unreadable, never zero
            figures[name], unreadable = None, unreadable + [f"{name}: {type(exc).__name__}"]
    known = [v for v in figures.values() if isinstance(v, (int, float))]
    usd = reservation if unreadable else max(known, default=0.0)
    return {"usd": usd, "figures": figures, "unreadable": unreadable}


# ---- classification of an ended attempt (D5) ------------------------------------------------------------------

FINAL = {"observation", "infrastructure_failure", "stop", "ruling"}  # classes whose slot is never run again


def tranche_event(root, kind, **fields):
    """An event in the passthrough's tranche.jsonl: the launcher writes `stop` (the passthrough then refuses every
    request), `pause` and `reopen`; only a person writes `resume`."""
    with open(root / "passthrough" / "tranche.jsonl", "a") as fh:
        fh.write(json.dumps({"time": time.time(), "event": kind, **fields}) + "\n")


def _result_json(trial):
    path = trial / "result.json" if trial else None
    return _read_json(path) if path and path.is_file() else None


def session_of(attempt_dir, rows, ended_at, slot):
    """The attempt as the reader reads a fixture: the harness's exception (left out when it wrote no result), every
    event of the stream, and the passthrough's rows (log_view). None when the stream cannot be read: such a session
    is not read as one that never started."""
    trial = trial_dir(attempt_dir)
    try:
        events = stream_events(trial)
    except ValueError:
        return None
    fx = {"n_events": len(events), "n_api_retry": sum(e.get("subtype") == "api_retry" for e in events),
          "stream_tail": events, "_log": log_view(rows, ended_at, slot)}
    result = _result_json(trial)
    if result is not None:
        exc = result.get("exception_info") or {}
        fx.update(harness_exception=exc.get("exception_type"), exception_message=exc.get("exception_message"))
    return fx


def _epoch(stamp):
    import datetime
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() if stamp else None


def ending_time(attempt, trial):
    """The session's ending: when the launcher saw the stream's result event, else when the harness's agent phase
    ended (a time limit), else None (every row of the slot then counts as before it; coordinator ruling N1)."""
    if attempt.get("result_seen_at"):
        return attempt["result_seen_at"]
    result = _result_json(trial) or {}
    return _epoch((result.get("agent_execution") or {}).get("finished_at"))


def init_stop(events, ladder):
    """The stop an init event other than the criterion's makes (D2, D7.7), or None."""
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), None)
    want = ladder["attempt"]["init_event"]
    for key, what in (("tools", "tool list"), ("claude_code_version", "CLI version"), ("apiKeySource", "credential source")):
        if init is not None and init.get(key) != want[key]:
            return f"an init event with another {what}"
    return None


def subagent_files(trial):
    """Session files below a session's own directory: a subagent's rows (`<session>/subagents/agent-*.jsonl`)."""
    projects = trial / "agent" / "sessions" / "projects" if trial else None
    if projects is None or not projects.is_dir():
        return []
    return sorted(p for p in projects.rglob("*.jsonl") if len(p.relative_to(projects).parts) > 2)


def _reward(trial):
    return (((_result_json(trial) or {}).get("verifier_result") or {}).get("rewards") or {}).get("reward")


def _launcher_stop(trial, ladder):
    """A stop of D7.7 the launcher sees in the attempt's own files, beyond the D5 rows (the follower acts on the
    paid-usage sign as the stream comes; this is the teardown's second look)."""
    try:
        events = stream_events(trial)
    except ValueError:
        events = []
    reason = init_stop(events, ladder) or next(filter(None, map(stream_stop, events)), None)
    return reason or ("a subagent file" if subagent_files(trial) else None)


def window_rows(root, attempt, closed):
    """The passthrough's rows of the whole tranche from the attempt's slot opening to its closing (D5's join)."""
    return [r for r in _jsonl(root / "passthrough" / "requests.jsonl") if attempt["opened"] <= r["time"] <= closed]


def judge(root, attempt, ladder, ended_at=None, closed=None):
    """Row, class and reward of an ended attempt, from its trial and the passthrough's rows in its window."""
    attempt_dir = root / "slots" / attempt["id"]
    trial, window = trial_dir(attempt_dir), window_rows(root, attempt, closed or time.time())
    ended_at = ended_at if ended_at is not None else ending_time(attempt, trial)
    session = session_of(attempt_dir, window, ended_at, attempt["id"])
    row = 16 if session is None else classify(session, ladder)
    spec = ladder["classification"]["rows"][row - 1]
    stop = _launcher_stop(trial, ladder)
    cls = "stop" if stop else spec["class"]
    return {"row": row, "class": cls, "flagged": spec.get("flagged", False), "reward": _observed(cls, row, trial),
            "stop": stop or (f"D5 row {row}" if cls == "stop" or spec.get("stop") else None),
            "slot_rows": [r for r in window if r.get("slot") == attempt["id"]]}


def _observed(cls, row, trial):
    """An observation's reward: the verifier's, 0 when it gave none (D5), except after a normal ending, which is
    regraded first. Any other class's reward is never read (a cut's above all)."""
    if cls != "observation":
        return None
    reward = _reward(trial)
    return 0.0 if reward is None and row != 5 else reward


def close(ctx, root, attempt, ladder, prior, ended_at=None):
    """Classify and settle an attempt whose containers are all gone; the slot closes and its token is retired.
    A stop is written to the tranche's events; a row-16 ending pauses the tranche for a ruling."""
    judged = judge(root, attempt, ladder, ended_at)
    money = settlement(root / "slots" / attempt["id"], judged.pop("slot_rows"), attempt["reservation_usd"])
    record = {**money, **judged}
    if record["stop"]:
        tranche_event(root, "stop", slot=attempt["id"], reason=record["stop"])
    elif record["class"] == "ruling":
        tranche_event(root, "pause", slot=attempt["id"], reason=f"D5 row {record['row']}")
    settle(root, attempt, record, ladder, prior)
    return record


def _key(entry):
    return entry["round"], entry["task"], entry["effort"]


def _by_key(root):
    found = {}
    for a in attempts(root):
        found.setdefault(_key(a), []).append(a)
    return found


def _settled_classes(mine):
    return [a["settled"]["class"] for a in mine if a["settled"]]


def lost(root, schedule):
    """The slots lost after their third pre-session failure (D5)."""
    by_key = _by_key(root)
    return [e for e in schedule if _settled_classes(by_key.get(_key(e), [])).count("pre_session_failure") >= 3
            and not set(_settled_classes(by_key[_key(e)])) & FINAL]


def queue(root, schedule):
    """What is left to start, in order: slots to run again (a cut, a pre-session failure before its third) at the
    head, in the order they ended; then the schedule's untried slots in its order. A slot in flight, ended in a
    final class, or lost is not in it."""
    by_key, heads, rest = _by_key(root), [], []
    for entry in schedule:
        mine = by_key.get(_key(entry), [])
        classes = _settled_classes(mine)
        if len(classes) < len(mine) or set(classes) & FINAL or classes.count("pre_session_failure") >= 3:
            continue
        if mine:
            heads.append((mine[-1]["settled"]["closed"], {**entry, "rerun_of": mine[-1]["id"]}))
        else:
            rest.append(entry)
    return [entry for _, entry in sorted(heads, key=lambda h: h[0])] + rest


# ---- regrade (D5: verifier only, no model call) -----------------------------------------------------------------


def harness_command(ctx, *args):
    """The harness through its wrapper (harbor_patient.py), run by the harness venv's Python."""
    return [str(ctx.lh / "hvenv" / "bin" / "python"), "-I", str(KIT / "harbor_patient.py"), *args]


def _regrade_once(ctx, ladder, attempt, n):
    """One verifier-only run of the attempt's trial; (reward or None, exception type or None)."""
    attempt_dir = ctx.root / "slots" / attempt["id"]
    trial, out = trial_dir(attempt_dir), attempt_dir / "regrade"
    command = harness_command(ctx, "trial", "regrade", str(trial), "-p", str(attempt_dir / "task"), "--env",
                              "podman", "--trial-name", f"regrade-{n}", "-o", str(out))
    env = {**base_env(ctx), "CONTAINERS_CONF_OVERRIDE": str(ctx.lh / "logs" / "containers-override.conf")}
    subprocess.run(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                   start_new_session=True)
    regraded = out / f"regrade-{n}"
    return _reward(regraded), ((_result_json(regraded) or {}).get("exception_info") or {}).get("exception_type")


def _case(ladder, attempt, record):
    """Which regrade case of D5 an attempt is in: 1 (no reward after a normal ending), 2 (a load-sensitive task's
    0 while the load was above the gate during verification), or None."""
    if record["class"] == "observation" and record["row"] == 5 and record["reward"] is None:
        return 1
    sensitive = attempt["task"] in (ladder["tasks"]["load_sensitive"] or [])
    if record["class"] == "observation" and record["reward"] == 0 and sensitive and record.get("verifier_load_above_gate"):
        return 2
    return None


def _regrades(ctx, ladder, attempt, record, most, gate):
    """Up to `most` regrades, each after the gate opens, until one gives a reward; (verifier timeouts, last reward).
    `record` takes the count and the reward."""
    timeouts, reward, record["regrades"] = 0, None, 0
    for n in range(1, most + 1):
        if not gate():
            break
        reward, exc = _regrade_once(ctx, ladder, attempt, n)
        record["regrades"], timeouts = n, timeouts + (exc == "VerifierTimeoutError")
        if reward is not None:
            record["reward"] = reward
            break
    return timeouts, reward


def regraded(ctx, ladder, attempt, record, gate):
    """The record after the regrades D5 calls for, each below the load gate (`gate` waits for it and says whether it
    opened); written to settled.json. Case 1: up to two; a reward then stands, a verifier timeout twice is 0, still
    none is an infrastructure failure. Case 2: one, whose reward stands (none: indeterminate)."""
    case, record = _case(ladder, attempt, record), dict(record)
    if case is None:
        return record
    timeouts, reward = _regrades(ctx, ladder, attempt, record, 2 if case == 1 else 1, gate)
    if case == 1 and record["reward"] is None:
        record["reward"], record["class"] = (0.0, "observation") if timeouts == 2 else (None, "infrastructure_failure")
    if case == 2 and record["regrades"] and record["reward"] == 0 and reward is None:
        record["indeterminate"] = True
    with _Lock(ctx.root):
        _write_json(ctx.root / "slots" / attempt["id"] / "settled.json", record)
    return record


# ---- containers and reconcile -------------------------------------------------------------------------------


def podman(ctx, *args, timeout=300):
    """A podman command with the launcher's clean environment; its CompletedProcess (stdout as bytes)."""
    return subprocess.run(["podman", *args], env=base_env(ctx), capture_output=True, timeout=timeout, check=False)


def prefixes(attempt_dir):
    """The name prefixes of every container and network the harness made for the attempt: its trial's compose
    projects (`<trial>__env`, `<trial>__verifier__…`) and its regrades', from the trial names (Harbor lower-cases)."""
    trials = [trial_dir(attempt_dir)] + sorted(p for p in (attempt_dir / "regrade").glob("*") if p.is_dir())
    return [t.name.lower() + "__" for t in trials if t]


def container_names(ctx, prefix_list):
    names = podman(ctx, "ps", "-a", "--format", "{{.Names}}").stdout.decode().split()
    return [n for n in names if any(n.startswith(p) for p in prefix_list)]


def remove_containers(ctx, attempt_dir, tries=10):
    """Remove the attempt's containers and networks by name; True once `podman ps -a` shows none of them."""
    found = prefixes(attempt_dir)
    for _ in range(tries):
        names = container_names(ctx, found)
        if not names:
            for net in podman(ctx, "network", "ls", "--format", "{{.Name}}").stdout.decode().split():
                if any(net.startswith(p) for p in found):
                    podman(ctx, "network", "rm", net)
            return True
        podman(ctx, "rm", "-f", "-t", "5", *names)
        time.sleep(POLL_S)
    return False


POLL_S = 1.0  # seconds between two looks at a process, a container list or the stream
STOP_GRACE_S = 120  # seconds the harness has after SIGTERM to take its trial down, before SIGKILL to its group


def alive(pid, start):
    """Whether `pid` is the process that started at `start` (pid and start time both match) and not a zombie."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except OSError:
        return False
    return int(stat[19]) == start and stat[0] != "Z"


def stop_group(pid, start, grace=None):
    """SIGTERM to the process group of `pid` (the harness runs in its own session), then SIGKILL to the group after
    the grace; only while `pid` is still the process that started at `start`."""
    import signal
    for sig, wait in ((signal.SIGTERM, STOP_GRACE_S if grace is None else grace), (signal.SIGKILL, 30)):
        if not alive(pid, start):
            return True
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            return True
        deadline = time.monotonic() + wait
        while alive(pid, start) and time.monotonic() < deadline:
            time.sleep(0.2)
    return not alive(pid, start)


def reconcile(ctx, ladder, prior):
    """Attempts left open by a launcher that is gone (its pid and start time do not both match a live process):
    their harness is stopped if it is still the same process, their containers are removed, and they are closed."""
    done = []
    for attempt in [a for a in attempts(ctx.root) if a["settled"] is None]:
        owner = attempt["launcher"]
        if alive(owner["pid"], owner["start"]):
            continue
        harness = attempt.get("harness")
        if harness:
            stop_group(harness["pid"], harness["start"])
        if remove_containers(ctx, ctx.root / "slots" / attempt["id"]):
            done.append(close(ctx, ctx.root, attempt, ladder, prior))
    return done


# ---- the starts gate: stops, pauses and usage limits (D4, D7.7), from the tranche's events ---------------------

REOPEN_S = 300  # usage_limits.reopen.after_reset_s


def _closed_by(event, state):
    """The gate after a close_starts: a usage limit with a reset closes until five minutes after it; any other
    (a limit naming no reset, any other vendor 429, usage the meter could not read, the passthrough down) pauses
    for a person. A later limit inside an open episode keeps the later reopening."""
    if event.get("reason") == "usage limit" and event.get("reset"):
        until = float(event["reset"]) + REOPEN_S
        return {"kind": "limit", "until": max(until, state.get("until", 0)) if state["kind"] == "limit" else until}
    return {"kind": "pause", "why": f"closed starts: {event.get('reason')} (no reset named)"}


def gate_state(events):
    """What the tranche's events leave: a stop or a pause (until a person's `resume`), a usage limit, or nothing."""
    state = {"kind": None}
    for event in events:
        kind = event.get("event")
        if kind == "resume":
            state = {"kind": None}
        elif kind == "stop":
            state = {"kind": "stop", "why": event.get("reason")}
        elif state["kind"] in ("stop", "pause"):
            continue
        elif kind == "pause":
            state = {"kind": "pause", "why": event.get("reason")}
        elif kind == "close_starts":
            state = _closed_by(event, state)
    return state


def _gate(open_, most, kind=None, why=None):
    return {"open": open_, "most": most, "kind": kind, "why": why}


def _reopened(root, until):
    """After a limit's reopening: one start; the others once that session's first request is answered (D4)."""
    started = {a["id"] for a in attempts(root) if a["opened"] >= until}
    if not started:
        return _gate(True, 1, None, "reopened after a usage limit: one start")
    rows = _jsonl(root / "passthrough" / "requests.jsonl")
    if any(r.get("slot") in started and r.get("status") == 200 and r["time"] >= until for r in rows):
        return _gate(True, None)
    return _gate(False, 0, "limit", "waiting for the first answer after a usage limit's reset")


def starts_gate(root, now):
    """Whether a start may be made now, and how many in flight at most (None: no limit of the gate's)."""
    state = gate_state(_jsonl(root / "passthrough" / "tranche.jsonl"))
    if state["kind"] in ("stop", "pause"):
        return _gate(False, 0, state["kind"], state["why"])
    if state["kind"] == "limit" and now < state["until"]:
        return _gate(False, 0, "limit", f"a usage limit: starts reopen at {state['until']:.0f}")
    return _reopened(root, state["until"]) if state["kind"] == "limit" else _gate(True, None)


def limit_episodes(events):
    """The times of the usage-limit answers that each began a closing of starts (answers inside one count once)."""
    episodes, until = [], None
    for event in events:
        if event.get("event") == "close_starts" and event.get("reason") == "usage limit":
            if until is None or event["time"] >= until:
                episodes.append(event["time"])
            until = float(event["reset"]) + REOPEN_S if event.get("reset") else float("inf")
    return episodes


def check_limits(root, ladder, now=None):
    """Three usage-limit answers in a row with no observation between them stop the tranche (D7.7)."""
    events = _jsonl(root / "passthrough" / "tranche.jsonl")
    observed = [a["settled"]["closed"] for a in attempts(root) if a["settled"] and a["settled"]["class"] == "observation"]
    after = [t for t in limit_episodes(events) if t > max(observed, default=float("-inf"))]
    count = next(s["count"] for s in ladder["stops"]["stops"] if "usage-limit" in s["stop"])
    if len(after) >= count and gate_state(events)["kind"] != "stop":
        tranche_event(root, "stop", reason="three usage-limit answers in a row with no observation between them")


def stream_stop(event):
    """A rate_limit_event whose isUsingOverage is not false (D4, paid_usage.stream_stop), or None."""
    if event.get("type") == "rate_limit_event" and (event.get("rate_limit_info") or {}).get("isUsingOverage") is not False:
        return "a sign of paid extra usage in the session's stream"
    return None


# ---- the allowance guard (D4): the owner's inputs and meter readings --------------------------------------------

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
HOURS = re.compile(r"(daily|[a-z]{3}(?:-[a-z]{3})?(?:,[a-z]{3}(?:-[a-z]{3})?)*) (\d\d):(\d\d)-(\d\d):(\d\d)")


def _day_set(text):
    if text == "daily":
        return set(range(7))
    days = set()
    for part in text.split(","):
        first, _, last = part.partition("-")
        a, b = DAYS.index(first), DAYS.index(last or first)
        days |= set(range(a, b + 1))
    return days


def hours_spec(spec):
    """(weekdays, start minute, end minute) of one window spec, e.g. `mon-fri 09:00-18:00`, `daily 00:00-24:00`;
    ValueError otherwise. Local time; ponytail: a window that crosses a clock change is as long as its clock says."""
    found = HOURS.fullmatch(spec)
    if not found:
        raise ValueError(f"not an hours spec: {spec!r}")
    start, end = int(found[2]) * 60 + int(found[3]), int(found[4]) * 60 + int(found[5])
    if not 0 <= start < end <= 24 * 60:
        raise ValueError(f"not a window of one day: {spec!r}")
    return _day_set(found[1]), start, end


def _windows_on(day, hours):
    """The owner's windows on a local date, as (start, end) epoch seconds."""
    import datetime
    midnight = datetime.datetime.combine(day, datetime.time()).astimezone()
    found = []
    for spec in hours:
        days, start, end = hours_spec(spec)
        if day.weekday() in days:
            found.append(((midnight + datetime.timedelta(minutes=start)).timestamp(),
                          (midnight + datetime.timedelta(minutes=end)).timestamp()))
    return sorted(found)


def window_at(now, hours):
    """(start, end, previous end) of the owner's window holding `now`, or None; the previous end is that of the
    last window before it (a reading must be newer than it), within the week before."""
    import datetime
    today = datetime.datetime.fromtimestamp(now).date()
    windows = [w for n in range(8, -1, -1) for w in _windows_on(today - datetime.timedelta(days=n), hours)]
    for i, (start, end) in enumerate(windows):
        if start <= now < end:
            return start, end, max((e for _, e in windows[:i] if e <= start), default=float("-inf"))
    return None


def allowance_state(root):
    """The owner's last inputs, the last figures from the pilot, and every reading, from allowance.jsonl."""
    rows = _jsonl(root / "allowance.jsonl")
    last = {kind: next((r for r in reversed(rows) if r["kind"] == kind), None) for kind in ("inputs", "figures")}
    return {**last, "readings": [r for r in rows if r["kind"] == "reading"]}


def budgets(inputs, reading, figures):
    """(weekly, five-hour) budgets in priced USD: (100 - F - the reading) x the pilot's figure, floored at zero;
    the five-hour one None when the pilot gave no five-hour figure (D4)."""
    weekly = max(0, 100 - inputs["f_week"] - reading["weekly"]) * figures["weekly_usd_per_point"]
    five = figures.get("five_usd_per_point")
    return weekly, None if five is None else max(0, 100 - inputs["f_five"] - reading["five"]) * five


def guard_reservation(ladder, task, figures):
    """One third of the slot's cap (the public mean at max; 1.00 at the floor), raised by the pilot's ratio."""
    return cap(ladder, task) / 3 * ((figures or {}).get("reservation_raise") or 1.0)


def used_since(root, since):
    return sum(r.get("usd") or 0.0 for r in _jsonl(root / "passthrough" / "requests.jsonl") if r["time"] >= since)


def _reading_for(state, window, now):
    """The window's reading: the newest taken after the previous window ended, before its weekly meter reset."""
    fresh = [r for r in state["readings"] if window[2] <= r["at"] <= now and now < r["weekly_reset"]]
    return fresh[-1] if fresh else None


def _hours_refusal(state, now):
    inputs = state["inputs"]
    window = window_at(now, inputs["hours"])
    if window is None:
        return "outside the owner's hours", None
    margin = ((state["figures"] or {}).get("closing_margin_h") or inputs["closing_margin_h"]) * 3600
    if now + margin > window[1]:
        return "in the window's closing margin", None
    reading = _reading_for(state, window, now)
    if reading is None:
        return "no meter reading for this window", None
    skip = 100 - inputs["f_week"] - ALLOWANCE_SKIP
    if reading["weekly"] >= skip:
        return (f"window skipped: the weekly reading {reading['weekly']} leaves fewer than {ALLOWANCE_SKIP} points "
                f"above F-week {inputs['f_week']}"), None
    if now < reading["five_reset"] and reading["five"] >= 100 - inputs["f_five"] - ALLOWANCE_SKIP:
        return "waiting for the five-hour meter's reset", None
    return None, reading


ALLOWANCE_SKIP = 5  # allowance_guard.skip_margin_points


def _budget_refusal(root, ladder, state, reading, need, now):
    weekly, five = budgets(state["inputs"], reading, state["figures"])
    if round(used_since(root, reading["at"]) + need, 6) > round(weekly, 6):
        return "the weekly budget does not hold the guard's reservations"
    if five is not None and now < reading["five_reset"]:
        if round(used_since(root, reading["at"]) + need, 6) > round(five, 6):
            return "the five-hour budget does not hold the guard's reservations"
    elif five is not None:
        share = (100 - state["inputs"]["f_five"]) * state["figures"]["five_usd_per_point"]
        if round(used_since(root, now - 5 * 3600) + need, 6) > round(share, 6):
            return "the last five hours' usage does not leave room for the guard's reservations"
    return None


def _utilisation_refusal(root, ladder, inputs):
    """If the live probe names a header that reports the account's utilisation, its latest value at or above
    100 - F closes starts. Open ruling: which F, the header naming no window; the larger F is read (cautious)."""
    header = ladder["allowance_guard"]["utilisation_header"]
    if header in (None, "none"):
        return None
    values = [r["headers"][header] for r in _jsonl(root / "passthrough" / "requests.jsonl")
              if header in (r.get("headers") or {})]
    if values and float(values[-1]) >= 100 - max(inputs["f_week"], inputs["f_five"]):
        return f"the account's utilisation {values[-1]} is at or above the owner's share"
    return None


def guard(root, ladder, entry, now):
    """(start allowed, why not, at most this many in flight or None), by the owner's inputs and readings (D4).
    Before the pilot's figures only the smoke and the pilot may start, by the reading and the hours alone."""
    state = allowance_state(root)
    if state["inputs"] is None:
        return False, "no allowance inputs", None
    why, reading = _hours_refusal(state, now)
    if why:
        return False, why, None
    if state["figures"] is None:
        ok = entry["kind"] in ("smoke", "pilot")
        return ok, None if ok else "the pilot's figures are not entered", None
    open_ = [a for a in attempts(root) if a["settled"] is None]
    need = sum(guard_reservation(ladder, t, state["figures"]) for t in [a["task"] for a in open_] + [entry["task"]])
    why = _budget_refusal(root, ladder, state, reading, need, now) or _utilisation_refusal(root, ladder, state["inputs"])
    most = 2 if state["figures"].get("five_usd_per_point") is None else None
    return why is None, why, most


def _when(text):
    """Epoch seconds from an ISO 8601 time (local when it names no offset) or a number; ValueError otherwise."""
    import datetime
    try:
        return float(text)
    except ValueError:
        return datetime.datetime.fromisoformat(text).astimezone().timestamp()


def _points(text):
    value = float(text)
    if not 0 <= value <= 100:
        raise ValueError(f"{text} is not in 0 to 100 points")
    return value


def allowance_row(args, now):
    """The row `ladder.py allowance` appends; ValueError for an entry outside its form."""
    if args.what == "inputs":
        [hours_spec(spec) for spec in args.hours]
        return {"kind": "inputs", "at": now, "f_week": _points(args.f_week), "f_five": _points(args.f_five),
                "hours": args.hours, "closing_margin_h": float(args.closing_margin_h)}
    if args.what == "reading":
        return {"kind": "reading", "at": _when(args.at) if args.at else now, "weekly": _points(args.weekly),
                "weekly_reset": _when(args.weekly_reset), "five": _points(args.five), "five_reset": _when(args.five_reset)}
    five = None if args.five_usd_per_point is None else float(args.five_usd_per_point)
    return {"kind": "figures", "at": now, "weekly_usd_per_point": float(args.weekly_usd_per_point),
            "five_usd_per_point": five, "reservation_raise": float(args.reservation_raise),
            "closing_margin_h": None if args.closing_margin_h is None else float(args.closing_margin_h)}


def _allowance_parser(sub):
    allowance = sub.add_parser("allowance").add_subparsers(dest="what", required=True)
    inputs = allowance.add_parser("inputs")
    for flag in ("--f-week", "--f-five", "--closing-margin-h"):
        inputs.add_argument(flag, required=True)
    inputs.add_argument("--hours", action="append", required=True)
    reading = allowance.add_parser("reading")
    for flag in ("--weekly", "--weekly-reset", "--five", "--five-reset"):
        reading.add_argument(flag, required=True)
    reading.add_argument("--at")
    figures = allowance.add_parser("figures")
    figures.add_argument("--weekly-usd-per-point", required=True)
    figures.add_argument("--five-usd-per-point")
    figures.add_argument("--reservation-raise", default="1.0")
    figures.add_argument("--closing-margin-h")


def record_allowance(ctx, args):
    """Append one input, reading or figure to the state's history (never to the manifest) and print its ledger row."""
    try:
        row = allowance_row(args, time.time())
    except ValueError as exc:
        print(f"ladder.py: allowance: {exc}", file=sys.stderr)
        return 2
    ensure_state(ctx.root)
    with open(ctx.root / "allowance.jsonl", "a") as fh:
        fh.write(json.dumps(row) + "\n")
    shown = ", ".join(f"{k} {v}" for k, v in row.items() if k not in ("kind", "at"))
    print(f"| {time.strftime('%Y-%m-%d')} | Allowance {row['kind']} | {shown}; recorded in {ctx.root} |")
    return 0


# ---- the command line ---------------------------------------------------------------------------------------


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "launch", "status"):
        sub.add_parser(name)
    _allowance_parser(sub)
    return parser.parse_args(argv)


def _run(ctx, args):
    if args.command == "launch":
        preflight(ctx)
        return 0
    reason = mode_refusal(ctx.env)
    if reason and not reason.startswith("no authorization"):  # only a launch needs the authorization
        raise Refused(reason)
    if args.command == "allowance":
        return record_allowance(ctx, args)
    return 0


def main(argv=None, env=None):
    env = os.environ if env is None else env
    try:
        args = _parse(argv)
    except SystemExit as exc:  # argparse's own refusal of a malformed command line
        return exc.code
    try:
        return _run(Ctx(env), args)
    except Refused as refused:
        print(f"ladder.py: refused: {refused}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
