"""The wrapper around the reviewed launcher (family plan docs/plans/2026-11-15-mle-bench-family-plan.md, M4, M5,
Task 5).

Usage (from the repository root, or a detached checkout of the frozen commit for a live launch):
  python -I experiments/mle_bench_tasks/screen.py <tranche> plan | launch [--dry-run] | status [--export FILE]
                                                  | ruling ... | resume ... | allowance ...
      the launcher's own command (experiments/long_horizon_tasks/ladder.py), run on the tranche
  python -I experiments/mle_bench_tasks/screen.py <tranche> manifest write [--freeze] | check
      the tranche's manifest, manifests/<tranche>.json, by the reviewed manifest.py; --freeze is refused (exit 2,
      nothing written) while the tranche's ladder.json is not ready to freeze

The wrapper loads ladder.py by its path as a private module and sets M4's names in it: KIT (the tranche's directory),
PLAN (the tranche's own ledger file), EFFORTS (`medium` for the screen), PACKAGES (`packages`), Ctx (a subclass whose
live state root is ~/.local/state/mle-bench/<tranche>) and manifest (a second private load of the reviewed
manifest.py with KIT, MANIFEST, NOT_COVERED and EXTERNAL set, made by make_criterion.manifest_module). It gives the
launcher LH=~/mle-cache. It replaces or wraps no function of either module.

Its own refusals (exit 3, `screen.py: refused: <reason>`), each before the launcher is entered: a tranche outside
the kit's list or not generated; LH naming another cache than ~/mle-cache, or ~/mle-cache resolving into the
ladder's ~/lh-cache. At launch: an image reference of tasks.json not pinned by digest, or a competition without a
passing withholding result for its agent image; at launch and resume: an uncommitted change under
experiments/mle_bench_tasks. At launch: free disk on a file system under host.disk_plan.launch_room_gb; for a GPU
tranche, a process holding memory on the card (or nvidia-smi failing). For a live launch or resume: a passthrough
answering on the ladder's, the live probe's or another tranche's socket; the ladder's launcher lock or this line's
lock (~/.local/state/mle-bench/launcher.lock) held. Both locks are then held until the launcher returns. While a
GPU tranche's launcher runs, the processes on the card are recorded once a minute into <state>/screen/gpu.jsonl.
A rehearsal (LH_REHEARSAL) takes neither lock.
"""

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path

KIT = Path(__file__).resolve().parent
LADDER_KIT = KIT.parent / "long_horizon_tasks"
TRANCHES = KIT / "tranches"
COMMANDS = ("plan", "launch", "status", "ruling", "resume", "allowance")
SCREEN_EFFORTS = ("medium",)
GPU_QUERY = ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"]
GPU_EVERY_S = 60


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path):
    return json.loads(Path(path).read_text())


make_criterion = _load("mle_screen_make_criterion", KIT / "make_criterion.py")
wrap = _load("mle_screen_wrap", KIT / "wrap.py")
FIELDS = make_criterion.FIELDS


class Refused(Exception):
    """The wrapper refuses: the launcher was not entered. The message names the reason and never a secret."""


# ---- the replaced names (M4) ---------------------------------------------------------------------------------


def tranche_manifest(tranche):
    """The reviewed manifest.py, privately loaded with M4's four names set for the tranche."""
    return make_criterion.manifest_module(tranche)


def launcher(tranche):
    """The reviewed ladder.py, privately loaded with M4's six names set for the tranche."""
    lad = _load(f"mle_screen_ladder_{tranche}", LADDER_KIT / "ladder.py")

    class Ctx(lad.Ctx):
        """The launcher's context with this tranche's live state root; a rehearsal's is LH_REHEARSAL/state."""

        def __init__(self, env):
            super().__init__(env)
            if self.live:
                self.root = self.home / ".local" / "state" / "mle-bench" / tranche

    lad.KIT, lad.PLAN = TRANCHES / tranche, FIELDS["ledger"].format(tranche=tranche)
    if FIELDS["tranches"][tranche]["stage"] != "placement":
        lad.EFFORTS = SCREEN_EFFORTS
    lad.PACKAGES, lad.Ctx, lad.manifest = "packages", Ctx, tranche_manifest(tranche)
    return lad


# ---- the wrapper's refusals ----------------------------------------------------------------------------------


def tranche_refusal(tranche):
    if tranche not in FIELDS["tranches"]:
        return f"{tranche} is not a tranche of the kit ({', '.join(FIELDS['tranches'])})"
    if not (TRANCHES / tranche / "ladder.json").is_file():
        return f"{tranche} has no tranche directory under {TRANCHES}"
    return None


def _home(env):
    return Path(env.get("HOME") or os.path.expanduser("~"))


def cache_refusal(env):
    """LH naming another cache than this line's, or this line's resolving into the ladder's (M4, ruling M-b)."""
    cache, theirs = _home(env) / "mle-cache", (_home(env) / "lh-cache").resolve()
    if env.get("LH") and Path(env["LH"]) != cache:
        return f"this line's cache is {cache}, and LH names {env['LH']}"
    resolved = cache.resolve()
    if theirs == resolved or theirs in resolved.parents:
        return f"{cache} resolves to the ladder's cache {theirs}"
    return None


def image_refusal(tranche):
    """An image reference not pinned by digest, or no passing withholding result for the agent image (ruling B2)."""
    for task in _read(TRANCHES / tranche / "tasks.json")["tasks"]:
        name, result = task["name"], task["withholding"]
        for key in ("environment_image", "verifier_image"):
            if not (isinstance(task[key], str) and wrap.PINNED.fullmatch(task[key])):
                return f"{name}: the {key} {task[key]!r} is not pinned by digest"
        if not result:
            return f"{name}: no withholding result"
        if result.get("image") != task["environment_image"]:
            return f"{name}: the withholding result names another image ({result.get('image')})"
        if result.get("verdict") != "pass":
            return f"{name}: the withholding result did not pass"
    return None


def clean_refusal(lad):
    """Uncommitted changes under this kit, by the launcher's own git test (ruling M-a)."""
    dirty = lad._git("status", "--porcelain", "--", "experiments/mle_bench_tasks")
    return "experiments/mle_bench_tasks has uncommitted changes" if dirty is None or dirty else None


def disk_refusal(criterion):
    """Free disk under the launch condition on either file system (M9, ruling M-c)."""
    for path, need in criterion["host"]["disk_plan"]["launch_room_gb"].items():
        free = shutil.disk_usage(path).free / 1e9
        if free < need:
            return f"free disk on {path} is {free:.1f} GB, under the launch condition of {need} GB"
    return None


def gpu_processes(lad, ctx):
    """[(pid, name, MiB)] of the processes holding memory on the GPU, by nvidia-smi on the launcher's closed PATH."""
    try:
        done = subprocess.run(GPU_QUERY, capture_output=True, text=True, env=lad.base_env(ctx), timeout=60,
                              check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refused(f"the GPU's processes cannot be read: {type(exc).__name__}") from None
    if done.returncode != 0:
        raise Refused(f"the GPU's processes cannot be read: nvidia-smi exited {done.returncode}")
    return [tuple(part.strip() for part in line.split(",")) for line in done.stdout.splitlines() if line.strip()]


def is_gpu(criterion):
    return make_criterion.FAMILY["classes"][criterion["stage"]["class"]]["gpu"]


def gpu_refusal(lad, ctx, criterion):
    """For a GPU tranche, a process holding memory on the card (M5)."""
    if not is_gpu(criterion):
        return None
    held = gpu_processes(lad, ctx)
    if held:
        return "a process holds memory on the GPU: " + "; ".join(f"{p[0]} {p[1]} ({p[2]} MiB)" for p in held)
    return None


def passthrough_refusal(home, tranche):
    """A passthrough answering on the ladder's, the live probe's or another tranche's socket (M5)."""
    state = home / ".local" / "state"
    line = state / "mle-bench"
    roots = [state / "lh-ladder", state / "lh-probe"]
    roots += sorted(p for p in line.iterdir() if p.is_dir() and p.name != tranche) if line.is_dir() else []
    for sock in (root / "relay" / "passthrough.sock" for root in roots):
        with socket.socket(socket.AF_UNIX) as probe:
            probe.settimeout(10)
            if sock.exists() and probe.connect_ex(str(sock)) == 0:
                return f"a passthrough answers on {sock}: this line runs alone"
    return None


@contextmanager
def exclusive(lad, home):
    """The ladder's launcher lock and this line's lock, by the reviewed lock class, held together (M5)."""
    roots = [home / ".local" / "state" / "lh-ladder", home / ".local" / "state" / "mle-bench"]
    for root in roots:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with lad.OneLauncher(roots[0]), lad.OneLauncher(roots[1]):
            yield
    except lad.Refused as exc:
        raise Refused(str(exc)) from None


# ---- the GPU's record while the launcher runs (M4 item 7) ----------------------------------------------------


def record_gpu(lad, ctx):
    """One row of <state>/screen/gpu.jsonl: the time and the processes on the card, or why they cannot be read."""
    try:
        row = {"at": time.time(), "processes": [{"pid": p[0], "name": p[1], "mib": p[2]}
                                                for p in gpu_processes(lad, ctx)]}
    except Refused as exc:
        row = {"at": time.time(), "processes": None, "error": str(exc)}
    (ctx.root / "screen").mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(ctx.root / "screen" / "gpu.jsonl", "a") as fh:
        fh.write(json.dumps(row) + "\n")


@contextmanager
def gpu_recorder(lad, ctx):
    """Record the card once a minute until the block ends."""
    done = threading.Event()

    def loop():
        while True:
            record_gpu(lad, ctx)
            if done.wait(GPU_EVERY_S):
                return

    worker = threading.Thread(target=loop, name="gpu-record", daemon=True)
    worker.start()
    try:
        yield
    finally:
        done.set()
        worker.join()


# ---- the manifest command ------------------------------------------------------------------------------------


def manifest_freeze(tranche):
    """`manifest write --freeze`: the manifest marked frozen, refused while the tranche's ladder.json has a gap."""
    module = tranche_manifest(tranche)
    gaps = module.freeze_gaps(_read(TRANCHES / tranche / "ladder.json"))
    if gaps:
        print("screen.py: manifest not written;", *gaps, sep="\n  ", file=sys.stderr)
        return 2
    doc = {"frozen": True, "not_covered": module.NOT_COVERED, "files": module.files()}
    module.MANIFEST.write_text(json.dumps(doc, indent=1) + "\n")
    print(module._sha(module.MANIFEST))
    return 0


def manifest_check(tranche):
    """`manifest check`: the label and whether it is frozen; exit 1 naming each changed file, or, when frozen, each
    gap of the tranche's ladder.json."""
    module = tranche_manifest(tranche)
    recorded, now = _read(module.MANIFEST), module.files()
    changed = sorted(p for p in recorded["files"].keys() | now.keys() if recorded["files"].get(p) != now.get(p))
    gaps = module.freeze_gaps(_read(TRANCHES / tranche / "ladder.json")) if recorded["frozen"] else []
    print(module._sha(module.MANIFEST), "frozen" if recorded["frozen"] else "not frozen")
    for line in [f"changed: {p}" for p in changed] + [f"frozen, but ladder.json has {g}" for g in gaps]:
        print(f"screen.py: {line}", file=sys.stderr)
    return 1 if changed or gaps else 0


def manifest_command(tranche, args):
    if args == ["write"]:
        return tranche_manifest(tranche).write(False)
    if args == ["write", "--freeze"]:
        return manifest_freeze(tranche)
    if args == ["check"]:
        return manifest_check(tranche)
    print(__doc__, file=sys.stderr)
    return 2


# ---- the command line ----------------------------------------------------------------------------------------


def _first(*checks):
    """The first refusal of `checks` (called in order), raised."""
    for check in checks:
        reason = check()
        if reason:
            raise Refused(reason)


def before_launcher(lad, tranche, command, env):
    """The wrapper's refusals of a launch or a resume, in M4's order."""
    criterion, ctx = _read(TRANCHES / tranche / "ladder.json"), lad.Ctx(env)
    if command == "launch":
        _first(lambda: image_refusal(tranche))
    _first(lambda: clean_refusal(lad))
    if command == "launch":
        _first(lambda: disk_refusal(criterion), lambda: gpu_refusal(lad, ctx, criterion))
    if ctx.live:
        _first(lambda: passthrough_refusal(ctx.home, tranche))


def run(tranche, command, rest, env):
    """The launcher's command on the tranche, behind the wrapper's refusals, with both locks for a live launch or
    resume and the GPU's record while a GPU tranche's launch runs."""
    _first(lambda: cache_refusal(env))
    env = {**env, "LH": str(_home(env) / "mle-cache")}
    lad = launcher(tranche)
    if command in ("launch", "resume"):
        before_launcher(lad, tranche, command, env)
    ctx = lad.Ctx(env)
    locks = exclusive(lad, ctx.home) if ctx.live and command in ("launch", "resume") else nullcontext()
    starts = command == "launch" and "--dry-run" not in rest
    record = gpu_recorder(lad, ctx) if starts and is_gpu(_read(TRANCHES / tranche / "ladder.json")) else nullcontext()
    with locks, record:
        return lad.main([command, *rest], env)


def main(argv=None, env=None):
    argv = sys.argv[1:] if argv is None else argv
    env = dict(os.environ if env is None else env)
    if len(argv) < 2 or argv[1] not in (*COMMANDS, "manifest"):
        print(__doc__, file=sys.stderr)
        return 2
    tranche, command, rest = argv[0], argv[1], argv[2:]
    try:
        _first(lambda: tranche_refusal(tranche))
        if command == "manifest":
            return manifest_command(tranche, rest)
        return run(tranche, command, rest, env)
    except Refused as refused:
        print(f"screen.py: refused: {refused}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
