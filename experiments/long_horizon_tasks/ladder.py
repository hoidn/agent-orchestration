"""The long-horizon launcher (plan docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md, Task 5).

Usage (from the repository root, or a detached checkout of the frozen commit for a live launch):
  python -I experiments/long_horizon_tasks/ladder.py plan       the schedule, in the order it runs
  python -I experiments/long_horizon_tasks/ladder.py launch [--dry-run]
                                                                 run the tranche until it ends, waits for a
                                                                 person (printed) or stops; --dry-run: every
                                                                 refusal, nothing started
  python -I experiments/long_horizon_tasks/ladder.py status [--export FILE]
                                                                 starts, money, gates, the passthrough's command;
                                                                 FILE: the readout's record (slot_record.py)
  python -I experiments/long_horizon_tasks/ladder.py ruling ATTEMPT --row N --date YYYY-MM-DD
                                                                 a start paused under D5 row 16 gets the row of
                                                                 the ledger's `| date | Ruling | ATTEMPT row N |`
  python -I experiments/long_horizon_tasks/ladder.py resume [--clears THRESHOLD --date YYYY-MM-DD]
                                                                 resume a pause or a stop (D7.7 thresholds: below)
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
  end.json        how the tranche ended: the schedule done, the ceiling or the 240 starts
A pause or a stop (passthrough/tranche.jsonl) holds until a person runs `ladder.py resume` after the ledger row D5
asks for; a D7.7 threshold over its bound needs `resume --clears <threshold> --date <its Ruling row's date>`. The ledger rows the schedule waits for: `| <date> | Smoke read | <label> pass |` (or
`fail`: a stop), `| <date> | Pilot read | <label> ... |`, `| <date> | Round 1 read | <label> ... |`.
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
import threading
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
slot_record = _kit("slot_record")  # the one layout of the export, and the closed list of the launcher's stops


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


CREDENTIAL_VARS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")  # Task 8 m8


def mode_refusal(env):
    """Why this environment may not run the launcher at all, or None. A credential variable is named, never its
    value."""
    if env.get("LH_TOKEN_FILE"):
        return "LH_TOKEN_FILE is set: the token file is named only to the passthrough, never to the launcher"
    held = [name for name in CREDENTIAL_VARS if name in env]
    if held:
        return f"{', '.join(held)} in the launcher's environment: the launcher and its children hold no credential"
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
    if ladder["schedule"]["order"]["hash"] != ORDER_HASH:
        return f"the criterion's schedule.order.hash is not the launcher's ({ORDER_HASH})"
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
    reason = _criterion_refusal(ladder) or allowlist_refusal(ladder) or socket_refusal(ctx, ladder)
    reason = reason or harness_refusal(ctx, ladder)
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
    """The passthrough's slots file: every open attempt's fake token and cap, each on its own socket (Task 5,
    connections); the total is the ceiling less the live probe's usage."""
    slots = {a["id"]: {"token": a["token"], "cap_usd": a["cap_usd"], "cap_requests": None, "own_socket": True}
             for a in attempts(root) if a["settled"] is None}
    total = round(ladder["ceiling"]["total_usd"] - prior, 6)
    _write_json(root / "passthrough" / "slots.json", {"total_usd": total, "total_requests": None, "slots": slots})


def _next_index(root):
    """One more than every index claimed so far, under slots/ and refused/ (a refused launch keeps its index, so an
    index is never reused; Task 8 part A M4)."""
    names = [p.name for d in (root / "slots", root / "refused") if d.is_dir() for p in d.iterdir()]
    return 1 + max((int(n[:3]) for n in names if n[:3].isdigit()), default=0)


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
        index = _next_index(root)
        name = f"{index:03d}-r{entry['round']}-{entry['task']}-{entry['effort']}"
        (root / "slots" / name).mkdir(mode=0o700)  # the claim: a second claimant fails here
        attempt = {**entry, "id": name, "index": index, "cap_usd": cap(ladder, entry["task"]),
                   "reservation_usd": reservation, "token": "lh-fake-slot-" + os.urandom(16).hex(),
                   "launcher": {"pid": os.getpid(), "start": process_start(os.getpid())}, "opened": time.time(),
                   "label": this_label()}
        _write_json(root / "slots" / name / "slot.json", attempt)
        _slots_file(root, ladder, prior)
    return attempt


def settle(root, attempt, record, ladder=None, prior=0.0):
    """Close the attempt: its settlement replaces its reservation, and its fake token leaves the slots file. The
    settled record."""
    ladder = ladder or _read_json(KIT / "ladder.json")
    record = {**record, "closed": time.time()}
    with _Lock(root):
        _write_json(root / "slots" / attempt["id"] / "settled.json", record)
        _slots_file(root, ladder, prior)
    return record


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
# A stop the launcher finds in an attempt makes its class `stop` whatever row its ending matches, and it is never
# scored (coordinator ruling). Its cause is one of slot_record.LAUNCHER_STOPS, the one closed list; the export is
# checked against it. REFUSED_AT_LAUNCH is no record's cause: a refused launch is no start (Attempt.refused).
TOKEN_MATCH = "a match of token_scan.py"
TOKEN_INCOMPLETE = "an incomplete scan of token_scan.py"
RUNTIME_MATCH = "a match of the runtime check in the attempt's containers"
RUNTIME_INCOMPLETE = "an incomplete scan of the runtime check in the attempt's containers"
REFUSED_AT_LAUNCH = "refused at launch"
SMOKE_FAILED = "a failed smoke check"  # the smoke's start, when a person's Smoke read row says fail (D7.1)


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
            "api_retry": None if session is None else session["n_api_retry"], "minutes": session_minutes(trial),
            "graded": graded(trial, ladder, attempt["task"]), "load_refused": _load_refused(window, ladder),
            "slot_rows": [r for r in window if r.get("slot") == attempt["id"]]}


def _load_refused(window, ladder):
    """Whether the attempt's window holds a refusal under load or timing (refusal.load_reasons), read as D5 row 15
    reads it: from the tranche's rows, since a connection refused at the cap is logged before any slot is known."""
    reasons = set(ladder["refusal"]["load_reasons"].values())
    return any(r.get("refused") in reasons for r in window)


def session_minutes(trial):
    """The session's length from the harness's agent phase; 0 when the agent never started (no session), None
    when the harness left no record of it or of its end (a missing figure is never written as zero)."""
    result = _result_json(trial)
    if result is None:
        return None
    agent = result.get("agent_execution") or {}
    start, end = _epoch(agent.get("started_at")), _epoch(agent.get("finished_at"))
    if start is None:
        return 0.0
    return round((end - start) / 60, 3) if end is not None else None


def graded(trial, ladder, task):
    """{"passed", "total"} sub-tests where the verifier reports them (D6; enters no rule), else None. Open ruling:
    readout.graded_outcome.verifiers (pending) is read as {task: "ctrf"}, the report at verifier/ctrf.json."""
    path = trial / "verifier" / "ctrf.json" if trial else None
    if (ladder["readout"]["graded_outcome"]["verifiers"] or {}).get(task) != "ctrf" or not (path and path.is_file()):
        return None
    summary = _read_json(path)["results"]["summary"]
    return {"passed": summary["passed"], "total": summary["tests"]}


def _observed(cls, row, trial):
    """An observation's reward: the verifier's, 0 when it gave none (D5), except after a normal ending, which is
    regraded first. Any other class's reward is never read (a cut's above all)."""
    if cls != "observation":
        return None
    reward = _reward(trial)
    return 0.0 if reward is None and row != 5 else reward


def close(ctx, root, attempt, ladder, prior, ended_at=None, extra=None):
    """Classify and settle an attempt whose containers are all gone; the slot closes and its token is retired.
    A stop is written to the tranche's events; a row-16 ending pauses the tranche for a ruling. `extra` is what
    the teardown found (its scans, the session's minutes); a stop in it was written when it was found."""
    judged = judge(root, attempt, ladder, ended_at)
    rows = judged.pop("slot_rows")
    money = settlement(root / "slots" / attempt["id"], rows, attempt["reservation_usd"])
    record = {**money, **judged, "tokens": _tokens(rows), **(extra or {})}
    if record["class"] != "observation":  # only an observation's reward is ever read
        record["reward"] = None
    if record["stop"] and "stop" not in (extra or {}):
        tranche_event(root, "stop", slot=attempt["id"], reason=record["stop"])
    elif record["class"] == "ruling":
        tranche_event(root, "pause", slot=attempt["id"], reason=f"D5 row {record['row']}")
    return settle(root, attempt, record, ladder, prior)


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
    command = harness_command(ctx, "trial", "regrade", str(trial), "-p", str(attempt_dir / "package" / attempt["task"]), "--env",
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
    record["regrade_case"] = case
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


def _finish_regrade(ctx, ladder, attempt, gate):
    """A settled attempt whose regrade a launcher death interrupted (its case is due and no regrade_case recorded;
    Task 8 part A M3): the regrade's containers removed, the partial regrade kept aside, then the regrade run. The
    record, or None."""
    settled = attempt["settled"]
    if "regrade_case" in settled or _case(ladder, attempt, settled) is None:
        return None
    attempt_dir = ctx.root / "slots" / attempt["id"]
    if not remove_containers(ctx, attempt_dir):
        tranche_event(ctx.root, "pause", slot=attempt["id"], reason="the regrade's containers were not removed")
        return None
    if (attempt_dir / "regrade").exists():
        (attempt_dir / "regrade").rename(attempt_dir / f"regrade-interrupted-{time.time_ns()}")
    return regraded(ctx, ladder, attempt, settled, gate)


def reconcile(ctx, ladder, prior, gate):
    """Attempts left open by a launcher that is gone (its pid and start time do not both match a live process):
    their harness is stopped if it is still the same process, and each is torn down as its own thread would have
    torn it down (tear_down: the scans, the stops already written for it, the regrades below the load `gate`)."""
    done = []
    for attempt in attempts(ctx.root):
        owner = attempt["launcher"]
        if alive(owner["pid"], owner["start"]):
            continue
        if attempt["settled"] is not None:
            done += [r for r in [_finish_regrade(ctx, ladder, attempt, gate)] if r]
            continue
        harness = attempt.get("harness")
        if harness:
            stop_group(harness["pid"], harness["start"])
        record = tear_down(ctx, ladder, attempt, prior, scan_terms(ctx, ladder, attempt["task"]), gate)
        done += [record] if record else []
    with _Lock(ctx.root):  # Task 8 m4: a launcher killed inside settle left a settled attempt's token in the file
        _slots_file(ctx.root, ladder, prior)
    return done


# ---- the starts gate: stops, pauses and usage limits (D4, D7.7), from the tranche's events ---------------------

REOPEN_S = 300  # usage_limits.reopen.after_reset_s


def _reset(event):
    """The reset a usage-limit answer named, as a number, or None: a value that is not one names no reset, and the
    gate then pauses for a person instead of failing (Task 8 m2)."""
    try:
        return float(event.get("reset"))
    except (TypeError, ValueError):
        return None


def _held(hold, event):
    """The hold after a stop, a pause, or a close_starts that is not a usage limit with a reset: a stop is never
    turned into anything else, and a pause only into a stop; a person's resume lifts either."""
    kind = event.get("event")
    if kind == "stop":
        return {"kind": "stop", "why": event.get("reason"), "threshold": event.get("threshold")}
    if hold is not None:
        return hold
    if kind == "pause":
        return {"kind": "pause", "why": event.get("reason")}
    return {"kind": "pause", "why": f"closed starts: {event.get('reason')} (no reset named)"}


def gate_state(events):
    """What the tranche's events leave: a stop or a pause (until a person's `resume`), a usage limit, or nothing.
    A limit with a reset is kept through every hold and every resume (Task 8 B1): a resume lifts a stop or a pause,
    never a limit, which closes starts until five minutes after its reset and then reopens by its own rule from
    `since` (the reopening, or a later resume)."""
    hold, until, resumed = None, None, None
    for event in events:
        kind = event.get("event")
        limit = kind == "close_starts" and event.get("reason") == "usage limit" and _reset(event) is not None
        if kind == "resume":
            hold, resumed = None, event.get("time")
        elif limit:
            until = max(until or 0.0, _reset(event) + REOPEN_S)
        elif kind in ("stop", "pause", "close_starts"):
            hold = _held(hold, event)
    if hold is not None:
        return hold
    if until is not None:
        return {"kind": "limit", "until": until, "since": max(until, resumed or 0.0)}
    return {"kind": None}


def _gate(open_, most, kind=None, why=None):
    return {"open": open_, "most": most, "kind": kind, "why": why}


UNANSWERED = "unanswered"  # the single start after a limit's reopening ended with no answer: a pause (Task 8 M1)


def _reopened(root, until, since):
    """After a limit's reopening: one start; the others once a session started since the reopening has a request
    answered (D4). A single start that ended with no answer is UNANSWERED: the loop pauses the tranche for a person,
    whose plain resume allows one more (Task 8 M1)."""
    every = attempts(root)
    after = {a["id"] for a in every if a["opened"] >= until}
    rows = _jsonl(root / "passthrough" / "requests.jsonl")
    if any(r.get("slot") in after and r.get("status") == 200 and r["time"] >= until for r in rows):
        return _gate(True, None)
    single = [a for a in every if a["opened"] >= since]
    if not single:
        return _gate(True, 1, None, "reopened after a usage limit: one start")
    if all(a["settled"] for a in single):
        return _gate(False, 0, UNANSWERED, "the single start after a usage limit's reset ended with no answer")
    return _gate(False, 0, "limit", "waiting for the first answer after a usage limit's reset")


def starts_gate(root, now):
    """Whether a start may be made now, and how many in flight at most (None: no limit of the gate's)."""
    state = gate_state(_jsonl(root / "passthrough" / "tranche.jsonl"))
    if state["kind"] in ("stop", "pause"):
        return _gate(False, 0, state["kind"], state["why"])
    if state["kind"] == "limit" and now < state["until"]:
        return _gate(False, 0, "limit", f"a usage limit: starts reopen at {state['until']:.0f}")
    return _reopened(root, state["until"], state["since"]) if state["kind"] == "limit" else _gate(True, None)


def limit_episodes(events):
    """The times of the usage-limit answers that each began a closing of starts (answers inside one count once). An
    answer that named no reset ends its episode at the resume that lifted its pause (Task 8 m1)."""
    episodes, until = [], None
    for event in events:
        if event.get("event") == "resume" and until == float("inf"):
            until = None
        if event.get("event") == "close_starts" and event.get("reason") == "usage limit":
            if until is None or event["time"] >= until:
                episodes.append(event["time"])
            reset = _reset(event)
            until = reset + REOPEN_S if reset is not None else float("inf")
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


# ---- D7.7's count thresholds: each lifted only by a clearing after a ledger ruling (coordinator ruling) ------

THRESHOLDS = {"infrastructure-failures": "stop", "pre-session-failures": "stop", "cuts": "pause",
              "load-refusals": "pause"}


def _rule(ladder, name):
    every = ladder["stops"]["stops"] + ladder["stops"]["pauses_for_a_ruling_or_an_input"]
    return next(e for e in every if e.get("stop", e.get("pause", "")).startswith(name))


def _after(root, name):
    """The settled attempts in the order they closed, after the last clearing of threshold `name`."""
    since = max((c["at"] for c in _jsonl(root / "clearings.jsonl") if c["threshold"] == name), default=float("-inf"))
    ended = sorted((a for a in attempts(root) if a["settled"]), key=lambda a: a["settled"]["closed"])
    return [a for a in ended if a["settled"]["closed"] > since]


def _share(every, ladder, cls, above, least):
    """"hits of starts" when the class's share of the counted starts is above `above` with at least `least` starts."""
    starts = [a for a in every if ladder["classification"]["classes"][a["settled"]["class"]]["starts"]]
    hits = sum(a["settled"]["class"] == cls for a in starts)
    return f"{hits} of {len(starts)} starts" if len(starts) >= least and hits > above * len(starts) else None


def _infrastructure(root, ladder):
    rule, every = _rule(ladder, "infrastructure failures"), _after(root, "infrastructure-failures")
    found = _share(every, ladder, "infrastructure_failure", rule["above_share_of_starts"], rule["from_starts"])
    # Open ruling: D7.7 states no minimum for the share at one level; the block's size (one start per effort) is used.
    at_level = (_share([a for a in every if a["effort"] == level], ladder, "infrastructure_failure",
                       rule["above_share_at_one_level"], len(EFFORTS)) for level in EFFORTS)
    return found or next((f"{why} at one level" for why in at_level if why), None)


def _pre_session(root, ladder):
    rule = _rule(ladder, "pre-session failures")
    classes, run, longest = [a["settled"]["class"] for a in _after(root, "pre-session-failures")], 0, 0
    for cls in classes:
        run = run + 1 if cls == "pre_session_failure" else 0
        longest = max(longest, run)
    if longest >= rule["in_a_row"]:
        return f"{longest} in a row"
    total = classes.count("pre_session_failure")
    return f"{total} in all" if total >= rule["in_all"] else None


def _cuts(root, ladder):
    rule = _rule(ladder, "cuts")
    return _share(_after(root, "cuts"), ladder, "cut", rule["above_share_of_starts"], rule["from_starts"])


def _load_refusals(root, ladder):
    rule = _rule(ladder, "attempts ended by a load refusal")
    n = sum(a["settled"]["row"] == 15 and bool(a["settled"].get("load_refused")) for a in _after(root, "load-refusals"))
    return f"{n} attempts ended by a load refusal" if n >= rule["count"] else None


COUNTS = {"infrastructure-failures": _infrastructure, "pre-session-failures": _pre_session, "cuts": _cuts,
          "load-refusals": _load_refusals}


def threshold_breaches(root, ladder):
    """{threshold: what it counted} for each D7.7 threshold over its bound, over the endings after its clearing."""
    return {name: why for name, count in COUNTS.items() if (why := count(root, ladder))}


def check_thresholds(root, ladder):
    """A threshold over its bound stops or pauses the tranche while the gate is open, and a stop also over a pause."""
    kind = gate_state(_jsonl(root / "passthrough" / "tranche.jsonl"))["kind"]
    for name, why in threshold_breaches(root, ladder).items():
        if kind in (None, "limit") or (THRESHOLDS[name] == "stop" and kind == "pause"):
            tranche_event(root, THRESHOLDS[name], reason=f"{name}: {why}", threshold=name)
            kind = THRESHOLDS[name]


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


# ---- the schedule (D7.1 to D7.4) ----------------------------------------------------------------------------

# Open ruling (the plan names a hash of seed, round, task and effort but not its form): this is the form.
ORDER_HASH = "sha256, as hexadecimal, of '<seed>:<round>:<task>:<effort>' in UTF-8; a block's key has an empty effort"
CONCURRENCY = {"smoke": "smoke", "pilot": "pilot", "round": "rounds"}  # host.concurrency, by the entry's kind


def _order(seed, rnd, task, effort=""):
    return hashlib.sha256(f"{seed}:{rnd}:{task}:{effort}".encode()).hexdigest()


def smoke_task(ladder):
    """gsea-proteomics, or the first qualified task in tasks.json order not on the load-sensitive list (D7.1)."""
    smoke, tasks = ladder["schedule"]["smoke"], qualified(ladder)
    if smoke["task"] in tasks:
        return smoke["task"]
    return next(t for t in tasks if t not in (ladder["tasks"]["load_sensitive"] or []))


def pilot_task(ladder):
    """rs-archive-clone, or the next dearest qualified task unchanged since 4.0.0 (D7.2)."""
    pilot, tasks = ladder["schedule"]["pilot"], qualified(ladder)
    return next(t for t in [pilot["task"], *pilot["fallback"]] if t in tasks)


def schedule(ladder):
    """Every slot in the order it starts: the smoke, the pilot's three efforts, then five rounds of blocks, one per
    qualified task, each its three efforts one after another, blocks and efforts ordered by the frozen seed (D7.3).
    The pilot's block is skipped in round 1 (its slots already run). Open ruling: the smoke is slot 1 of round 1,
    so its block is round 1's first, and its other two efforts run right after the pilot."""
    seed, smoke, pilot = ladder["schedule"]["order"]["seed"], smoke_task(ladder), pilot_task(ladder)

    def efforts(rnd, task):
        return sorted(EFFORTS, key=lambda e: _order(seed, rnd, task, e))

    first = [{"round": 1, "task": smoke, "effort": ladder["schedule"]["smoke"]["effort"], "kind": "smoke"}]
    first += [{"round": 1, "task": pilot, "effort": e, "kind": "pilot"} for e in efforts(1, pilot)]
    done, rounds = {_key(e) for e in first}, []
    for rnd in range(1, ladder["schedule"]["rounds"] + 1):
        tasks = sorted(qualified(ladder), key=lambda t: (not (rnd == 1 and t == smoke), _order(seed, rnd, t)))
        rounds += [{"round": rnd, "task": t, "effort": e, "kind": "round"} for t in tasks for e in efforts(rnd, t)
                   if (rnd, t, e) not in done]
    return first + rounds


def slot_id(entry):
    """A schedule slot's id, the readout's join key: r<round>-<task>-<effort>."""
    return f"r{entry['round']}-{entry['task']}-{entry['effort']}"


def _reads(text, what, labels):
    """What follows the label in each ledger row `what` that names one of `labels`."""
    return [(cell.split(" ", 1) + [""])[1] for cell in ledger_cells(text, what) if cell.split(" ", 1)[0] in labels]


def hold(head, text, labels):
    """Why the head of the queue waits for a person's ledger row, or None (D7.1, D7.2, D7.5): the pilot after a
    `Smoke read` row `<label> pass`, round 1 after a `Pilot read` row, later rounds after a `Round 1 read` row, each
    naming a label of `labels`; a last `Smoke read` row that does not say pass is a failed smoke."""
    if head["kind"] == "smoke":
        return None
    smoke = _reads(text, "Smoke read", labels)
    if not smoke:
        return "waiting for the smoke read"
    if not smoke[-1].startswith("pass"):
        return "a failed smoke"
    if head["kind"] == "pilot":
        return None
    if not _reads(text, "Pilot read", labels):
        return "waiting for the pilot's ledger row"
    if head["round"] > 1 and not _reads(text, "Round 1 read", labels):
        return "waiting for the round-one read"
    return None


def this_label():
    return hashlib.sha256(manifest.MANIFEST.read_bytes()).hexdigest()


def fail_smoke(root):
    """A Smoke read row that says fail: a person read the smoke's checks (D7.1). The smoke's start becomes a stop
    with the cause SMOKE_FAILED, never scored."""
    for a in attempts(root):
        if a["kind"] == "smoke" and a["settled"] and a["settled"]["class"] != "stop":
            with _Lock(root):
                _write_json(root / "slots" / a["id"] / "settled.json",
                            {**a["settled"], "class": "stop", "stop": SMOKE_FAILED, "reward": None})


def ledger_labels(ctx):
    """The ledger's text, and the labels its `Configuration label` rows name with this checkout's own."""
    text = ledger_text(ctx)
    found = [m.group(1) for m in map(LABEL_ROW.match, ledger_cells(text, "Configuration label")) if m]
    return text, found + [this_label()]


# ---- the host: load, disk, the task copy, the harness --------------------------------------------------------


def _host_file(ctx, name):
    path = ctx.rehearsal / "host" / name if ctx.rehearsal else None
    return path if path and path.is_file() else None


def load_open(ctx, ladder):
    """(open, (1-minute, 5-minute)): open when both load averages are at or below the gate (D2). A rehearsal may
    give a stand-in LH_REHEARSAL/host/loadavg."""
    path = _host_file(ctx, "loadavg") or Path("/proc/loadavg")
    one, five = map(float, path.read_text().split()[:2])
    gate = ladder["host"]["load_gate"]["at_or_below"]
    return one <= gate and five <= gate, (one, five)


def disk_paths(ctx):
    """The file systems the disk stop reads (host.disk_plan: / , where Podman stages each pull in /var/tmp, and the
    home directory, where it keeps its images), with the state and the cache."""
    return [p for p in (Path("/"), ctx.root, ctx.lh, ctx.home) if p.exists()]


def free_gb(ctx):
    """The least free space, in GB, of disk_paths; a rehearsal may give a stand-in LH_REHEARSAL/host/free_gb."""
    import shutil
    path = _host_file(ctx, "free_gb")
    if path:
        return float(path.read_text())
    return min(shutil.disk_usage(p).free for p in disk_paths(ctx)) / 1e9


def overlay_lines(hosts):
    """The two agent-phase keys of D1 and D3, as the oracle check writes them."""
    return 'network_mode = "allowlist"\nallowed_hosts = [' + ", ".join(f'"{h}"' for h in hosts) + "]"


def overlay_digest(hosts):
    return hashlib.sha256((overlay_lines(hosts) + "\n").encode()).hexdigest()


def overlay(package_dir, copy, hosts):
    """Copy the package with the two keys after its one [agent] line; removing them must give the package's
    task.toml back byte for byte (D1). Their digest."""
    import shutil
    text = (package_dir / "task.toml").read_text()
    lines = text.split("\n")
    if lines.count("[agent]") != 1:
        raise Refused(f"{package_dir}: not one [agent] table")
    shutil.copytree(package_dir, copy)
    keys = overlay_lines(hosts)
    at = lines.index("[agent]") + 1
    (copy / "task.toml").write_text("\n".join(lines[:at] + keys.split("\n") + lines[at:]))
    if (copy / "task.toml").read_text().replace("[agent]\n" + keys + "\n", "[agent]\n", 1) != text:
        raise Refused(f"{package_dir}: removing the two keys does not give the package's task.toml back")
    return overlay_digest(hosts)


def canary_term(package_dir, sha):
    """The canary's identifier, read from the package's task.toml at run time by its SHA-256 (D1, D6): the first
    line, or word of a line, whose SHA-256 is the criterion's; None when none is."""
    for line in (package_dir / "task.toml").read_text().splitlines():
        text = line.lstrip("#").strip()
        for candidate in [text, *text.split()]:
            if hashlib.sha256(candidate.encode()).hexdigest() == sha:
                return candidate
    return None


def attempt_command(ctx, ladder, attempt, package_copy):
    """The harness command of one attempt: the criterion's model, effort, CLI version, cap, deny list, output-token
    variable, relay base URL, zero retries, the task's own limits, the kept containers, under the CPU set."""
    a, h = ladder["attempt"], ladder["harness"]
    run = harness_command(
        ctx, "run", "--path", str(package_copy), "--agent", h["agent"], "-m", h["model_argument"], "--base-url",
        h["base_url"], "--skip-credential-checks", "--ak", f"version={a['cli_version']}",
        "--ak", f"disallowed_tools={','.join(a['deny_list'])}", "--ak", f"max_budget_usd={attempt['cap_usd']}",
        *[x for k, v in a["output_tokens_env"].items() for x in ("--ae", f"{k}={v}")], "--effort", attempt["effort"],
        "--agent-setup-timeout-multiplier", str(h["agent_setup_timeout_multiplier"]),
        "--agent-timeout-multiplier", str(h["agent_timeout"]["multiplier"]),
        "--verifier-timeout-multiplier", str(h["verifier_timeout"]["multiplier"]), "--max-retries", str(h["retries"]),
        "--ek", "keep_containers=true", "--env", "podman", "-n", str(h["runs_per_attempt"]),
        "--job-name", attempt["id"], "-o", str(ctx.root / "slots" / attempt["id"] / "jobs"), "-q", "-y",
        "--extra-docker-compose", str(ctx.lh / "logs" / "limits-compose.yaml"),
        "--extra-docker-compose", str(KIT / h["host_side"]["relay_compose"]))
    return ["taskset", "-c", ladder["host"]["cpu_set"], *run]


SOCKET_PATH_MAX = 107  # bytes of a unix socket's path (sun_path less its terminating NUL)
SOCKET_WAIT_S = 30  # seconds the passthrough has to open a new slot's socket (it reads the slots file every 0.25 s)


# Task 8 m6: the harness waits for `go` on its input, written once slot.json holds its pid; an end of input (the
# launcher died in between) ends it unrun, so no harness ever runs that reconcile cannot stop.
HOLD = ["/bin/sh", "-c", 'read -r go && [ "$go" = go ] && unset PWD OLDPWD SHLVL _ && exec "$@" </dev/null',
        "lh-hold"]  # the shell's own variables unset: the harness's environment stays exactly harness_env's


def relay_dir(ctx, attempt):
    """The attempt's own relay socket directory (LH_RELAY_SOCKET_DIR): the passthrough serves the slot there, on a
    socket of its own (Task 5, connections), and removes it when the slot is retired."""
    return ctx.root / "relay" / attempt["id"]


def socket_refusal(ctx, ladder):
    """A state root whose slots' socket paths would not fit a unix socket's path."""
    longest = max((f"999-{slot_id(e)}" for e in schedule(ladder)), key=len)
    path = relay_dir(ctx, {"id": longest}) / "passthrough.sock"
    return (f"the state's path is too long for a slot's socket ({len(str(path).encode())} bytes, at most "
            f"{SOCKET_PATH_MAX}): {ctx.root}") if len(str(path).encode()) > SOCKET_PATH_MAX else None


def own_socket(ctx, attempt):
    """Wait for the passthrough to answer on the attempt's own socket; Refused when it does not in time."""
    path = relay_dir(ctx, attempt) / "passthrough.sock"
    deadline = time.monotonic() + SOCKET_WAIT_S
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_UNIX) as probe:
            if path.exists() and probe.connect_ex(str(path)) == 0:
                return
        time.sleep(0.1)
    raise Refused("the passthrough opened no socket for the slot")


def harness_env(ctx, attempt):
    """The harness's whole environment: nothing inherited; the slot's fake token and the token-mode switch, the
    relay's socket directory and the containers override. No credential: the fake token is worth its slot's cap."""
    reason = token_refusal(attempt["token"])
    if reason:
        raise Refused(reason)
    return {**base_env(ctx), "CONTAINERS_CONF_OVERRIDE": str(ctx.lh / "logs" / "containers-override.conf"),
            "LH_RELAY_SOCKET_DIR": str(relay_dir(ctx, attempt)), "CLAUDE_FORCE_OAUTH": "1",
            "CLAUDE_CODE_OAUTH_TOKEN": attempt["token"]}


def passthrough_mode_refusal(ctx):
    """A passthrough whose recorded mode (fingerprint.json's, written at its start) is not this launch's: a
    rehearsal never runs against a live passthrough, nor a live launch against a rehearsal's (Task 8 M3)."""
    want = "live" if ctx.live else "rehearsal"
    path = ctx.root / "passthrough" / "fingerprint.json"
    mode = (_read_json(path) if path.is_file() else {}).get("mode")
    return None if mode == want else f"the passthrough records mode {mode or 'none'}, and this launch is {want}"


def passthrough_up(ctx):
    """Whether the passthrough answers on the socket the relay forwards to (a connection closed before a request
    line is dropped by it unlogged)."""
    with socket.socket(socket.AF_UNIX) as probe:
        probe.settimeout(10)
        return probe.connect_ex(str(ctx.root / "relay" / "passthrough.sock")) == 0


# ---- the scans at teardown: the token's fingerprint, the runtime check, contamination ------------------------


def token_scan(ctx, *paths, stdin=None):
    """token_scan.py by the passthrough's fingerprint over `paths` (or `-` and a stream on `stdin`): its exit (0
    clean, 1 a match, 2 incomplete). Its output names paths and offsets only and is not kept."""
    command = [sys.executable, "-I", str(KIT / "token_scan.py"), "scan", "--fingerprint",
               str(ctx.root / "passthrough" / "fingerprint.json"), *map(str, paths)]
    return subprocess.run(command, stdin=stdin, capture_output=True, timeout=3 * 3600, check=False).returncode


def _scan_verdict(code, match, incomplete):
    """A scan's stop: a match, or a scan that could not finish (open ruling: read as a stop, since it cannot show
    that nothing leaked)."""
    return {1: match, 2: incomplete}.get(code)


def _worst(codes):
    """The scans' joint exit: a match anywhere (1) before an incomplete scan anywhere (2), else 0 (Task 8 B1)."""
    return 1 if 1 in codes else max(codes, default=0)


def _export_scan(ctx, name):
    """token_scan.py over a container's exported file system; a failed export is an incomplete scan."""
    exported = subprocess.Popen(["podman", "export", name], env=base_env(ctx), stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
    code = token_scan(ctx, "-", stdin=exported.stdout)
    exported.stdout.close()
    return 2 if exported.wait() != 0 and code == 0 else code


def _kept(ctx, attempt_dir, name):
    """Keep a container's inspected configuration, and an egress sidecar's log first: 0, or 2 when podman could not
    give one (Task 8 M2: a failed read, or an empty inspection, is never kept as an empty file and scanned clean)."""
    reads = ([("logs", attempt_dir / f"egress-{name}.log")] if "egress-control-sidecar" in name else []) + [
        ("inspect", attempt_dir / "containers" / f"{name}.inspect.json")]
    code = 0
    for verb, path in reads:
        done = podman(ctx, verb, name)
        if done.returncode != 0 or (verb == "inspect" and not done.stdout.strip()):
            code = 2
            continue
        path.write_bytes(done.stdout)
    return code


def had_session(attempt_dir):
    """Whether the attempt's trial holds the agent's stream: a session ran, so containers ran."""
    trial = trial_dir(attempt_dir)
    return trial is not None and (trial / "agent" / "claude-code.txt").is_file()


def runtime_check(ctx, attempt_dir, export):
    """D4's runtime check on the attempt's containers before they are removed: every container's inspected
    configuration and the process environments read while it ran; with `export`, the file system of every agent
    container (`*_main_1`) too. The egress sidecar's log is read to its end and kept first. The finding, or None:
    any finding in any container is the attempt's. A session with no container under the trial's prefix, or an
    export due with no agent container, is an incomplete scan, never clean (Task 8 B2); so are a container whose
    process environments no sample over the attempt read (M1) and a podman read that failed (M2)."""
    (attempt_dir / "containers").mkdir(exist_ok=True)
    names = container_names(ctx, prefixes(attempt_dir))
    codes = [_kept(ctx, attempt_dir, name) for name in names]
    sample_environ(ctx, attempt_dir, names)
    sampled = attempt_dir / "containers"  # M1: a container no sample over the attempt could read is unscanned
    codes += [2 for name in names if not (sampled / f"{name}.environ").is_file()]
    codes += [token_scan(ctx, attempt_dir / "containers")] if names else []  # no container: nothing to scan
    agents = [n for n in names if n.endswith("_main_1")]
    codes += [2] if _unfound(attempt_dir, names, agents, export) else []
    return _scan_verdict(_exports(ctx, agents if export else [], codes), RUNTIME_MATCH, RUNTIME_INCOMPLETE)


def _unfound(attempt_dir, names, agents, export):
    """B2: an attempt that had a session or containers, whose containers or (with an export due) agent container
    were not found."""
    return bool(names or had_session(attempt_dir)) and (not names or (export and not agents))


def _exports(ctx, agents, codes):
    """The joint exit of `codes` and each agent container's exported file system, scanned until a match."""
    for name in agents:
        if 1 in codes:
            break
        codes = codes + [_export_scan(ctx, name)]
    return _worst(codes)


def sample_environ(ctx, attempt_dir, names):
    """Each running container's process environments, kept as the distinct entries seen so far in
    containers/<name>.environ (one per NUL-ended entry). A container no exec has reached has no such file, which
    runtime_check reads as unscanned (Task 8 M1)."""
    for name in names:
        done = podman(ctx, "exec", name, "sh", "-c", "cat /proc/[0-9]*/environ 2>/dev/null; true", timeout=60)
        if done.returncode != 0:
            continue
        path = attempt_dir / "containers" / f"{name}.environ"
        seen = set(path.read_bytes().split(b"\0")) if path.is_file() else set()
        new = seen | set(done.stdout.split(b"\0"))
        if new != seen or not path.is_file():
            path.write_bytes(b"\0".join(sorted(new - {b""})) + b"\0")


def egress_refused(attempt_dir):
    """{address: count} of the connections the egress sidecar refused (D3): a session id with a `bypass` event,
    its address from that session's `dst`. Addresses only: the log names no host for a refusal."""
    refused = {}
    for path in sorted(attempt_dir.glob("egress-*.log")):
        sessions = {}
        for line in path.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("sid"):
                sessions.setdefault(event["sid"], []).append(event)
        for events in sessions.values():
            dst = next((e["dst"] for e in events if e.get("dst")), None)
            if dst and any(e.get("msg") == "bypass" for e in events):
                refused[dst] = refused.get(dst, 0) + 1
    return refused


def contamination(trial, terms, chunk=1 << 20):
    """The contamination scan (D6; coordinator ruling: the launcher's, at every teardown): the frozen terms over the
    agent's transcript (agent/) and its exported files (artifacts/). Each hit is the term's SHA-256, the file and
    the offset of its first occurrence there: never the term or the text around it."""
    wanted = [(t.encode(), hashlib.sha256(t.encode()).hexdigest()) for t in terms if t]
    keep = max((len(t) for t, _ in wanted), default=1) - 1
    hits, unreadable = [], []
    for top in ("agent", "artifacts"):
        for path in sorted(p for p in (trial / top).rglob("*") if p.is_file() and not p.is_symlink()):
            try:
                hits += _hits_in(path, trial, wanted, keep, chunk)
            except OSError:  # named here; token_scan.py reads the same file, and its incomplete scan is a stop
                unreadable.append(path.relative_to(trial).as_posix())
    return {"contaminated": bool(hits), "hits": hits, "unreadable": unreadable}


def _hits_in(path, trial, wanted, keep, chunk):
    """The first offset of each term in one file, read in chunks that overlap by one byte less than the longest
    term, so a term split across two chunks is found."""
    first, carry, base = {}, b"", 0
    with open(path, "rb") as fh:
        while data := fh.read(chunk):
            buf = carry + data
            for term, sha in wanted:
                at = buf.find(term)
                if at >= 0 and sha not in first:
                    first[sha] = base + at
            carry = buf[-keep:] if keep else b""
            base += len(buf) - len(carry)
    return [{"term_sha256": sha, "file": path.relative_to(trial).as_posix(), "offset": at}
            for sha, at in sorted(first.items(), key=lambda kv: kv[1])]


def contamination_stop(every, ladder):
    """Contaminated attempts on three tasks stop the tranche (D7.7); fewer are excluded observations (D6) and stop
    nothing."""
    tasks = {a["task"] for a in every if ((a.get("settled") or {}).get("contamination") or {}).get("contaminated")}
    most = next(s["on_tasks"] for s in ladder["stops"]["stops"] if s["stop"] == "contaminated attempts")
    return "contaminated attempts on three tasks" if len(tasks) >= most else None


def scan_terms(ctx, ladder, task):
    """The frozen terms and the task's canary identifier, read from its package by its SHA-256. A live launch
    refuses a package that holds no such canary; a rehearsal's stand-in SHA-256 may match none."""
    scan = ladder["readout"]["contamination_scan"]
    canary = canary_term(package(ctx, task), scan["canary_sha256"])
    if canary is None and ctx.live:
        raise Refused(f"{task}: the package holds no canary of the criterion's SHA-256")
    return list(scan["terms"]) + ([canary] if canary else [])


# ---- the tranche: the loop, an attempt's life, teardown -------------------------------------------------------

SAMPLE_S = 2.0  # seconds between two reads of the containers' process environments and of the load


def _write_slot(ctx, attempt):
    _write_json(ctx.root / "slots" / attempt["id"] / "slot.json", attempt)


class Attempt:
    """One attempt's life on the host, in its own thread: prepare, harness, follow, teardown, close, regrade."""

    def __init__(self, tranche, attempt):
        self.t, self.ctx, self.ladder, self.a = tranche, tranche.ctx, tranche.ladder, attempt
        self.dir = self.ctx.root / "slots" / attempt["id"]
        self.offset, self.stops, self.terms = 0, [], []

    def stop(self, reason, **detail):
        """A stop found in this attempt: written to the tranche's events at once, kept for its record."""
        if reason not in self.stops:
            self.stops.append(reason)
            tranche_event(self.ctx.root, "stop", slot=self.a["id"], reason=reason, **detail)

    def run(self):
        try:
            try:
                proc = self.start()
            except Refused as refused:
                self.refused(str(refused))
                return
            self.follow(proc)
            self.teardown()
        except Exception as exc:  # recorded, never lost: the tranche pauses for a person
            tranche_event(self.ctx.root, "pause", slot=self.a["id"],
                          reason=f"the launcher failed: {type(exc).__name__}: {exc}")
            self.salvage()
            raise

    def salvage(self):
        """After a failure (Task 8 m5): the harness stopped, then the teardown (scans, containers removed, token
        retired) unless the attempt is closed already. A failure of that teardown is recorded too, and reconcile
        closes the attempt at the next launch."""
        harness = self.a.get("harness")
        if harness:
            stop_group(harness["pid"], harness["start"])
        if (self.dir / "settled.json").exists():
            return
        try:
            self.teardown()
        except Exception as exc:  # recorded: the attempt stays open for reconcile
            tranche_event(self.ctx.root, "pause", slot=self.a["id"],
                          reason=f"its teardown failed too: {type(exc).__name__}: {exc}")

    def refused(self, why):
        """A launch refused before the harness ran is no start (coordinator ruling, Task 5): the tranche stops, the
        attempt leaves slots/ for refused/, where the launcher keeps it, and its fake token leaves the slots file."""
        self.stop(REFUSED_AT_LAUNCH, detail=why)
        kept = self.ctx.root / "refused"
        kept.mkdir(mode=0o700, exist_ok=True)
        with _Lock(self.ctx.root):
            self.dir.rename(kept / f"{self.a['id']}-{time.time_ns()}")
            _slots_file(self.ctx.root, self.ladder, self.t.prior)

    def start(self):
        task = self.a["task"]
        reason = task_refusal(self.ctx, self.ladder, task)
        if reason:
            raise Refused(reason)
        self.terms = scan_terms(self.ctx, self.ladder, task)
        copy = self.dir / "package" / task
        digest = overlay(package(self.ctx, task), copy, allowlist(self.ladder, task))
        if (self.ladder["tasks"]["overlay_digests"] or {}).get(task) != digest:
            raise Refused(f"{task}: the overlay's digest is not the criterion's")
        env = harness_env(self.ctx, self.a)
        own_socket(self.ctx, self.a)
        with open(self.dir / "harness.out", "ab") as out:
            proc = subprocess.Popen([*HOLD, *attempt_command(self.ctx, self.ladder, self.a, copy)], env=env,
                                    stdin=subprocess.PIPE, stdout=out, stderr=out, cwd=self.dir,
                                    start_new_session=True)
        self.a.update(harness={"pid": proc.pid, "start": process_start(proc.pid)}, overlay_digest=digest)
        _write_slot(self.ctx, self.a)
        proc.stdin.write(b"go\n")
        proc.stdin.close()
        return proc

    def follow(self, proc):
        """While the harness runs: the stream (a paid-usage sign or another init event stops the tranche; the
        result event's arrival is the session's ending), the containers' environments, the load, an interrupt."""
        last = 0.0
        while proc.poll() is None:
            self.read_stream()
            if time.monotonic() - last >= SAMPLE_S:
                self.sample()
                last = time.monotonic()
            if self.t.interrupt.is_set():
                stop_group(proc.pid, self.a["harness"]["start"])
            time.sleep(POLL_S)
        self.read_stream()

    def sample(self):
        (self.dir / "containers").mkdir(exist_ok=True)
        sample_environ(self.ctx, self.dir, container_names(self.ctx, prefixes(self.dir)))
        with open(self.dir / "load.jsonl", "a") as fh:
            fh.write(json.dumps({"time": time.time(), "load": load_open(self.ctx, self.ladder)[1]}) + "\n")

    def read_stream(self):
        trial = trial_dir(self.dir)
        path = trial / "agent" / "claude-code.txt" if trial else None
        if path is None or not path.is_file():
            return
        with open(path, "rb") as fh:
            fh.seek(self.offset)
            data = fh.read()
        whole = data[:data.rfind(b"\n") + 1]
        self.offset += len(whole)
        for line in whole.splitlines():
            self.on_event(line)

    def on_event(self, line):
        try:
            event = json.loads(line)
        except ValueError:
            return  # an unreadable line: the teardown's reading of the stream decides (row 16)
        if not isinstance(event, dict):
            return
        reason = stream_stop(event) or (init_stop([event], self.ladder) if event.get("subtype") == "init" else None)
        if reason:
            self.stop(reason)
        if event.get("type") == "result" and "result_seen_at" not in self.a:
            self.a["result_seen_at"] = time.time()
            _write_slot(self.ctx, self.a)

    def teardown(self):
        tear_down(self.ctx, self.ladder, self.a, self.t.prior, self.terms, self.t.wait_for_load)


def slot_stops(root, attempt_id):
    """The launcher's stops written for the slot (causes of slot_record.LAUNCHER_STOPS), first found first. The
    record's stop is the first, whoever closes the attempt: a launcher that died after writing one still leaves a
    stop for reconcile to close."""
    found = [e["reason"] for e in _jsonl(root / "passthrough" / "tranche.jsonl") if e.get("event") == "stop"
             and e.get("slot") == attempt_id and e.get("reason") in slot_record.LAUNCHER_STOPS]
    return list(dict.fromkeys(found))


def verifier_loaded(attempt_dir, trial, ladder):
    """Whether the load was above the gate while the verifier ran (D5, regrade case 2)."""
    verifier = (_result_json(trial) or {}).get("verifier") or {}
    start, end = _epoch(verifier.get("started_at")), _epoch(verifier.get("finished_at"))
    gate = ladder["host"]["load_gate"]["at_or_below"]
    samples = _jsonl(attempt_dir / "load.jsonl") if start and end else []
    return any(start <= s["time"] <= end and max(s["load"]) > gate for s in samples)


def tear_down(ctx, ladder, attempt, prior, terms, gate):
    """An ended attempt's teardown, by its own thread or by reconcile: the runtime check and token_scan.py (a
    finding is a stop, written at once), the contamination scan, then the containers removed by name; only then is
    the slot closed (as its first launcher stop, if any), its token retired, and the record regraded below the load
    `gate`. The record, or None when the containers stay (the tranche pauses)."""
    root, attempt_dir = ctx.root, ctx.root / "slots" / attempt["id"]
    trial = trial_dir(attempt_dir)
    found = runtime_check(ctx, attempt_dir, attempt["kind"] in ("smoke", "pilot") or not ctx.live)
    found = found or _scan_verdict(token_scan(ctx, attempt_dir), TOKEN_MATCH, TOKEN_INCOMPLETE)
    if found and found not in slot_stops(root, attempt["id"]):
        tranche_event(root, "stop", slot=attempt["id"], reason=found)
    scanned = contamination(trial, terms) if trial else {"contaminated": False, "hits": [], "unreadable": []}
    if not remove_containers(ctx, attempt_dir):
        tranche_event(root, "pause", slot=attempt["id"], reason="the attempt's containers were not removed")
        return None
    stops = slot_stops(root, attempt["id"])
    extra = {"contamination": scanned, "verifier_load_above_gate": verifier_loaded(attempt_dir, trial, ladder)}
    extra.update({"stop": stops[0], "class": "stop"} if stops else {})
    record = close(ctx, root, attempt, ladder, prior, extra=extra)
    return regraded(ctx, ladder, attempt, record, gate)


SELF_ENDING = ("limit",)  # a closed gate of these kinds reopens by itself: the launcher waits through it


class Tranche:
    """The launcher's loop: one start at a time from the head of the queue, while every gate allows it."""

    def __init__(self, ctx, ladder):
        self.ctx, self.ladder, self.root = ctx, ladder, ctx.root
        self.prior, self.plan = prior_usd(ctx), schedule(ladder)
        self.workers, self.interrupt, self.closed_since, self.started = {}, threading.Event(), None, False

    def run(self):
        """Until the tranche ends, or waits for a person with nothing in flight; why."""
        ensure_state(self.root)
        reconcile(self.ctx, self.ladder, self.prior, self.wait_for_load)
        while True:
            self.started = False
            why = self.step(time.time())
            if why:
                break
            if not self.started:
                time.sleep(POLL_S)
        for worker in list(self.workers.values()):
            worker.join()
        return why

    def stop(self, reason):
        if gate_state(_jsonl(self.root / "passthrough" / "tranche.jsonl"))["kind"] != "stop":
            tranche_event(self.root, "stop", reason=reason)

    def step(self, now):
        """One look at every gate; a start if they all allow one. Why the loop ends, or None."""
        self.workers = {k: w for k, w in self.workers.items() if w.is_alive()}
        self.host_stops()
        gate = starts_gate(self.root, now)
        if not gate["open"]:
            if gate["kind"] == UNANSWERED and not self.workers:  # Task 8 M1: a pause, never a silent wait
                tranche_event(self.root, "pause", reason=gate["why"])
            return None if self.workers or gate["kind"] in SELF_ENDING else f"{gate['kind']}: {gate['why']}"
        head, why = self.head()
        if head is None:
            return None if self.workers else why
        return self.try_start(head, gate, now)

    def host_stops(self):
        """Low disk stops the tranche and interrupts every running attempt; three limit answers in a row with no
        observation between them, and contaminated attempts on three tasks, stop it (D7.7)."""
        floor = self.ladder["host"]["disk_stop_free_gb"]
        if free_gb(self.ctx) < floor:
            self.interrupt.set()
            self.stop(f"free disk under {floor} GB")
        check_limits(self.root, self.ladder)
        check_thresholds(self.root, self.ladder)
        reason = contamination_stop(attempts(self.root), self.ladder)
        if reason:
            self.stop(reason)

    def head(self):
        """(the head of the queue, None), or (None, why nothing starts: the schedule is done, or a person's row is
        awaited). A failed smoke is written as a stop, which the gate then reads."""
        left = queue(self.root, self.plan)
        if not left:
            return None, self.end("schedule", "the schedule is done")
        why = hold(left[0], *ledger_labels(self.ctx))
        if why == "a failed smoke":
            fail_smoke(self.root)
            self.stop(why)
            return None, None
        return (left[0], None) if why is None else (None, why)

    def try_start(self, head, gate, now):
        if not passthrough_up(self.ctx):
            tranche_event(self.root, "pause", reason="the passthrough down")
            return None
        reason = passthrough_mode_refusal(self.ctx)
        if reason:
            self.stop(reason)
            return None
        if not self.load_ok(now):
            return None
        ok, _, most = guard(self.root, self.ladder, head, now)
        limits = [self.ladder["host"]["concurrency"][CONCURRENCY[head["kind"]]], gate["most"], most]
        if not ok or len(self.workers) >= min(n for n in limits if n is not None):
            return None
        action, got = next_start(self.root, queue(self.root, self.plan), self.ladder, self.prior)
        if action == "start":
            self.workers[got["id"]] = worker = threading.Thread(target=Attempt(self, got).run, name=got["id"])
            worker.start()
            self.started = True
            return None
        if action == "end" and not self.workers:
            return self.end("starts" if got == "240 starts" else "ceiling", got)
        return None

    def load_ok(self, now):
        """The load gate (D2): closed, it waits; closed for its whole wait with nothing in flight, it pauses."""
        if load_open(self.ctx, self.ladder)[0]:
            self.closed_since = None
            return True
        if self.workers or self.closed_since is None:
            self.closed_since = now
        elif now - self.closed_since >= self.ladder["host"]["load_wait"]["gate_closed_s"]:
            tranche_event(self.root, "pause", reason="the load wait: the gate stayed closed with nothing in flight")
        return False

    def wait_for_load(self):
        """A regrade's gate: wait until the load is at or below it; False when the tranche is interrupted first."""
        while not load_open(self.ctx, self.ladder)[0]:
            if self.interrupt.wait(POLL_S * 30):
                return False
        return True

    def end(self, by, cause):
        """The tranche's end, recorded once nothing is in flight: the schedule done, the ceiling, the 240."""
        if not self.workers:
            _write_json(self.root / "end.json", {"by": by, "cause": None, "why": cause})
        return cause

    def on_signal(self, *_):
        """SIGTERM or SIGINT: every attempt in flight is stopped and torn down, and the tranche pauses."""
        self.interrupt.set()
        tranche_event(self.root, "pause", reason="the launcher was signalled")


def launch(ctx, dry_run):
    import signal
    ladder = preflight(ctx)
    if dry_run:
        return 0
    tranche = Tranche(ctx, ladder)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, tranche.on_signal)
    print(tranche.run(), flush=True)
    return 0


# ---- status, rulings and the export the readout reads (slot_record.py, the one layout) ---------------------

def _tokens(rows):
    """Tokens by kind over a slot's forwarded rows (the meter's usage; an answer with none, such as a 429, used
    none); each kind null, not recorded, when the meter could not read a 200's usage whole (its worst-case row)."""
    forwarded = [row for row in rows if "refused" not in row]
    if any(row.get("worst_case") for row in forwarded):
        return dict.fromkeys(slot_record.TOKEN_KINDS)
    totals = dict.fromkeys(slot_record.TOKEN_KINDS, 0)
    for u in (row.get("usage") or {} for row in forwarded):
        five, hour = price_check._writes({"cache_creation_input_tokens": 0, **u})
        for kind, value in zip(slot_record.TOKEN_KINDS, (u.get("input_tokens"), u.get("output_tokens"),
                                                          u.get("cache_read_input_tokens"), five, hour)):
            totals[kind] += value if isinstance(value, int) else 0
    return totals


def _export_class(settled, rows):
    """(class, stop_cause, excluded) as slot_record.py reads a start. Regrade case 1 that still gave no reward is
    an infrastructure failure (D5, ladder.json), marked "no reward after regrades"; case 2 that could not regrade
    is "indeterminate"; a stop on a stop row has no cause of its own (the row is it)."""
    if settled.get("regrade_case") == 1 and settled["class"] == "infrastructure_failure":
        return "infrastructure_failure", None, "no reward after regrades"
    cause = settled.get("stop") if settled["class"] == "stop" and rows[settled["row"]]["class"] != "stop" else None
    return settled["class"], cause, "indeterminate" if settled.get("indeterminate") else None


def _start_record(root, attempt, ladder):
    settled = attempt["settled"]
    rows = {row["row"]: row for row in ladder["classification"]["rows"]}
    cls, cause, excluded = _export_class(settled, rows)
    hits = (settled.get("contamination") or {}).get("hits") or []
    return {"slot": slot_id(attempt), "start": attempt["index"], "label": attempt["label"], "row": settled["row"],
            "class": cls, "stop_cause": cause, "reward": None if excluded == "no reward after regrades" else
            settled.get("reward"), "excluded": excluded, "contamination": sorted({h["term_sha256"] for h in hits}),
            "usd": settled["usd"], "minutes": settled.get("minutes"), "tokens": settled.get("tokens"),
            "api_retry": settled.get("api_retry"), "graded": settled.get("graded"),
            "egress_refused": egress_refused(root / "slots" / attempt["id"])}


def earlier_labels(text, label):
    """Each earlier label the ledger's `Configuration label` rows name, ended by the next such row (open ruling:
    the readout's `ended_by` is read as that row's text)."""
    found = [(m.group(1), cell) for cell in ledger_cells(text, "Configuration label") if (m := LABEL_ROW.match(cell))]
    ended = {}
    for (old, _), (_, cell) in zip(found, found[1:]):
        if old != label:
            ended.setdefault(old, cell)
    return [{"label": old, "ended_by": cell} for old, cell in ended.items()]


def _end(root):
    if (root / "end.json").is_file():
        end = _read_json(root / "end.json")
        return {"by": end["by"], "cause": end["cause"]}
    state = gate_state(_jsonl(root / "passthrough" / "tranche.jsonl"))
    return {"by": "stop", "cause": state["why"]} if state["kind"] == "stop" else None


def allowance_used(root):
    """The weekly points the owner's readings show moved while the ladder ran (D6, cost; enters no rule): each
    rise between two readings of one weekly window, and after a weekly reset the next reading's points. Open
    ruling: the owner's own use in that span is in it too. None with fewer than two readings."""
    readings = sorted(allowance_state(root)["readings"], key=lambda r: r["at"])
    if len(readings) < 2:
        return None
    points = sum(b["weekly"] - (a["weekly"] if b["weekly_reset"] == a["weekly_reset"] else 0)
                 for a, b in zip(readings, readings[1:]))
    shown = "; ".join(f"Allowance reading {time.strftime('%Y-%m-%d %H:%M', time.localtime(r['at']))} weekly "
                      f"{r['weekly']}" for r in readings)
    return {"weekly_points": points, "readings": shown}


def export(ctx, ladder):
    """The record the readout reads, in slot_record.py's layout, from the state: every settled start (an attempt
    still open is not in it). Refused while a start awaits a ruling (D5 row 16), and when the record does not
    load through slot_record.py: the launcher never writes a record the readout would refuse."""
    every = [a for a in attempts(ctx.root) if a["settled"]]
    unruled = [a["id"] for a in every if a["settled"]["class"] == "ruling"]
    if unruled:
        raise Refused(f"the export waits for a ruling (D5 row 16) on {', '.join(unruled)}: `ladder.py ruling`")
    label = this_label()
    doc = {"label": label, "earlier_labels": earlier_labels(ledger_text(ctx), label), "end": _end(ctx.root),
           "slots": [{"slot": slot_id(e), "task": e["task"], "effort": e["effort"], "round": e["round"],
                      "pilot": e["kind"] == "pilot"} for e in schedule(ladder)],
           "starts": [_start_record(ctx.root, a, ladder) for a in every], "allowance": allowance_used(ctx.root)}
    try:
        slot_record.load(json.loads(json.dumps(doc)), ladder)
    except slot_record.RecordError as exc:
        raise Refused(f"the export does not fit slot_record.py: {exc}") from None
    return doc


def ruling_rows(text, date, form):
    """The ledger's `| <date> | Ruling | ... |` rows whose third cell starts with the pattern `form`: a coordinator's
    ruling (`<attempt> row <N> ...` for a row-16 start, `<threshold>: <decision>` for a D7.7 threshold)."""
    return [line for line in text.splitlines() if line.startswith("| ")
            and [p.strip() for p in line.split("|")[1:3]] == [date, "Ruling"] and form.match(line.split("|")[3].strip())]


def record_ruling(ctx, args):
    """Give a start paused under D5 row 16 the row the coordinator ruled, once the ledger holds that ruling's row:
    its class is that row's, and the slot then follows that class (a cut runs again, any other ending never)."""
    ladder, path = criterion(ctx), ctx.root / "slots" / args.attempt / "settled.json"
    rows = {row["row"]: row for row in ladder["classification"]["rows"]}
    if not path.is_file():
        raise Refused(f"no settled attempt {args.attempt}")
    if rows.get(args.row, {"class": "ruling"})["class"] == "ruling":
        raise Refused(f"row {args.row} is not a row of D5 a ruling can give")
    if not ruling_rows(ledger_text(ctx), args.date, re.compile(rf"{re.escape(args.attempt)} row {args.row}(?!\d)")):
        raise Refused(f"no ledger row `| {args.date} | Ruling | {args.attempt} row {args.row} ... |`")
    with _Lock(ctx.root):
        settled = _read_json(path)
        if settled["class"] != "ruling":
            raise Refused(f"{args.attempt} awaits no ruling")
        cls = rows[args.row]["class"]
        reward = _observed(cls, args.row, trial_dir(ctx.root / "slots" / args.attempt))
        _write_json(path, {**settled, "row": args.row, "class": cls, "reward": reward,
                           "ruled": {"row": args.row, "date": args.date}})
    print(f"{args.attempt}: D5 row {args.row} ({cls}), by the ledger's ruling of {args.date}")
    return 0


def _stop_ruled(ctx, args):
    """A stop is lifted only after a coordinator's ledger row names its cause and the decision (D5; Task 8 part A
    M2): `| D | Ruling | resume: <cause>: <decision> |` and `resume --date D`, or, for a D7.7 threshold's stop, the
    `--clears` ruling of that threshold."""
    state = gate_state(_jsonl(ctx.root / "passthrough" / "tranche.jsonl"))
    if state["kind"] != "stop" or (args.clears and state.get("threshold") == args.clears):
        return
    form = re.compile(rf"resume:\s*{re.escape(state['why'] or '')}")
    if not (args.date and ruling_rows(ledger_text(ctx), args.date, form)):
        raise Refused(f"a stop is lifted only after the ledger row `| {args.date or '<date>'} | Ruling | resume: "
                      f"{state['why']}: <the decision> |`, then `resume --date <date>`")


def record_resume(ctx, args):
    """A person's resume of a pause or a stop, after the ledger row D5 asks for. Refused while a D7.7 threshold is
    over its bound; `--clears T --date D` clears T once the ledger holds `| D | Ruling | T: <decision> |`, recording
    the date and the counts then, and T counts only later endings; every other threshold keeps counting."""
    ladder = criterion(ctx)
    ensure_state(ctx.root)
    _stop_ruled(ctx, args)
    over = threshold_breaches(ctx.root, ladder)
    form = re.compile(rf"{re.escape(args.clears or '')}:\s*\S")
    if args.clears and not ruling_rows(ledger_text(ctx), args.date, form):
        raise Refused(f"no ledger row `| {args.date} | Ruling | {args.clears}: <the decision> |`")
    left = {name: why for name, why in over.items() if name != args.clears}
    if left:
        raise Refused("over its bound, cleared only by `resume --clears`: " + "; ".join(f"{k} ({v})" for k, v in left.items()))
    if args.clears:
        with open(ctx.root / "clearings.jsonl", "a") as fh:
            fh.write(json.dumps({"threshold": args.clears, "date": args.date, "at": time.time(),
                                 "counts": over.get(args.clears)}) + "\n")
    tranche_event(ctx.root, "resume", by="a person", clears=args.clears, date=args.date)
    print(f"resumed{f', {args.clears} cleared by the ruling of {args.date}' if args.clears else ''}")
    return 0


def passthrough_command(ctx):
    """The passthrough's start, as a person runs it: with the token file for a live launch; in a rehearsal, with the
    stand-in's socket and a canary it makes itself, never a token file (Task 8 M3)."""
    root = ctx.root
    credential = (f"--rehearsal <the stand-in API's socket> --canary-out {ctx.rehearsal / 'canary'}" if ctx.rehearsal
                  else "--token-file <the owner's token file>")
    return (f"env -i PATH=/usr/bin:/bin python3 -I {KIT / 'passthrough.py'} --socket {root / 'relay' / 'passthrough.sock'}"
            f" --state {root / 'passthrough'} --slots {root / 'passthrough' / 'slots.json'} {credential}"
            f" >> {root / 'passthrough' / 'output.log'} 2>&1")


def status(ctx, path=None):
    """Print the tranche's state and the passthrough's command line; with `path`, write the readout's record."""
    ladder = criterion(ctx)
    ensure_state(ctx.root)
    starts, committed, open_ = tally(ctx.root, ladder, prior_usd(ctx))
    gate = starts_gate(ctx.root, time.time())
    print(f"state {ctx.root}\nstarts {starts}, committed USD {committed:.2f}, in flight {len(open_)}")
    print(f"starts: {'open' if gate['open'] else 'closed'} {gate['kind'] or ''} {gate['why'] or ''}".rstrip())
    how = "in rehearsal mode" if ctx.rehearsal else "with the token file"
    print(f"passthrough: {'up' if passthrough_up(ctx) else 'down'}; a person starts it, {how}:")
    print(f"  {passthrough_command(ctx)}")
    if path:
        _write_json(Path(path).resolve(), export(ctx, ladder))
    return 0


def plan(ctx):
    for entry in schedule(criterion(ctx)):
        print(slot_id(entry), entry["kind"])
    return 0


# ---- the command line ---------------------------------------------------------------------------------------


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    sub.add_parser("launch").add_argument("--dry-run", action="store_true", help="every refusal; nothing started")
    sub.add_parser("status").add_argument("--export", metavar="FILE", help="write the readout's record")
    ruling = sub.add_parser("ruling", help="give a start paused under D5 row 16 the row the ledger's ruling names")
    ruling.add_argument("attempt")
    ruling.add_argument("--row", type=int, required=True)
    ruling.add_argument("--date", required=True, help="the date of the ledger's `Ruling` row")
    resume = sub.add_parser("resume", help="resume a pause or a stop; --clears a D7.7 threshold after its ruling")
    resume.add_argument("--clears", choices=sorted(THRESHOLDS))
    resume.add_argument("--date", help="the date of the ledger's `Ruling` row (with --clears)")
    _allowance_parser(sub)
    return parser.parse_args(argv)


def _run(ctx, args):
    if args.command == "launch":
        return launch(ctx, args.dry_run)
    reason = mode_refusal(ctx.env)
    if reason and not reason.startswith("no authorization"):  # only a launch needs the authorization
        raise Refused(reason)
    if args.command == "allowance":
        return record_allowance(ctx, args)
    if args.command == "ruling":
        return record_ruling(ctx, args)
    if args.command == "resume":
        if args.clears and not args.date:
            raise Refused("--clears needs the --date of its ledger row")
        return record_resume(ctx, args)
    return status(ctx, args.export) if args.command == "status" else plan(ctx)


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
