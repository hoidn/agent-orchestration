"""Shared stand-ins and drivers for the PQ-1c kit tests (`tests/test_pq1c_kit.py`, `tests/test_pq1c_readout.py`).

The stand-in `claude` is the agent-session shim of `tests/agent_session_shims.py`. Its init event has the
shape of a real isolated session's (built-in plugins and agents only, `claude-haiku-5-5`), it keeps its
transcripts where the real CLI does, and its closing `result` line carries usage, as the metering stand-ins print, so the
variant's agent turns and the baseline's plain metered calls both record priced usage. It carries the
kit's stand-in marker line, logs every invocation (argv, cwd, the nesting marker, the rehearsal slots
claimed at that moment) to `invocations.log` beside itself, reads its plan from `plan.json` beside itself,
keeps its native store where the real CLI does (`~/.claude`), counts its plan steps per cell, leaves a stray
session folder when a file `stray` is beside it, a hook record in its transcript when a file `hooked` is, sleeps first when a file `slow` is beside it,
and, when a file `nest` is beside it, tries to start `claude` from its own PATH as an agent's shell would.
Every launch gets a closed PATH and a temporary HOME, so the slot ledger is temporary too.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from tests.agent_session_shims import FAKE_CLAUDE, closed_path

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "experiments" / "pq1c"
MODEL = "claude-haiku-5-5"
CELLS = ("variant-clean", "variant-resumed", "baseline-clean", "baseline-resumed")
NO_PROVIDER = REPO / "experiments" / "thread_m" / "no_provider"
WRAPPER_FLAGS = ["--setting-sources", "project", "--strict-mcp-config", "--disable-slash-commands",
                 "--max-budget-usd", "0.5"]
DOC, FINAL = "artifacts/design/wordcount.md", "docs/design/wordcount.md"
PLAN = {"claude": [
    {"result": {"doc": DOC}, "files": {DOC: "# draft\n"}},
    {"result": {"blocking": ["b1"], "notes": []}},
    {"result": {"doc": FINAL}, "files": {FINAL: "# final\n"}},
    {"result": {"summary": "done", "commits": ["abc"], "checks_run": ["pytest"], "left_undone": []}},
]}
# The designer's first call exits before anything is written: what a login or launch failure looks like.
FAILING_PLAN = {"claude": [{"mode": "nonzero-before-append"}]}

_RESULT = '"session_id": session, "result": "ok"}'
_USAGE = (', "total_cost_usd": 0.0042, "modelUsage": {"claude-haiku-5-5": {"inputTokens": 1000, "outputTokens": 200,'
          ' "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "costUSD": 0.0042}}')
_INIT = '"session_id": session, "model": "fake"}'
_STORE = 'Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "ws"'
assert FAKE_CLAUDE.count(_RESULT) == FAKE_CLAUDE.count(_INIT) == FAKE_CLAUDE.count(_STORE) == 1
BUILTIN_AGENTS = ["claude", "Explore", "general-purpose", "Plan", "statusline-setup"]
BUILTIN_PLUGINS = [{"name": name, "path": "builtin", "source": f"{name}@builtin"} for name in (
    "cc-plugin-agents-md", "cc-plugin-telemetry", "cc-plugin-privacy", "cc-plugin-plugin-authoring", "cc-plugin-easel")]
# The init event of an isolated session (`--setting-sources project --strict-mcp-config --disable-slash-commands`),
# in the structure a real 2.1.322 Haiku session on this host recorded; paths, ids and sockets left out.
INIT_FIELDS = {"tools": ["Bash", "Edit", "Read", "Write"], "mcp_servers": [], "model": MODEL,
               "permissionMode": "bypassPermissions", "slash_commands": [], "apiKeySource": "none",
               "claude_code_version": "0.0.0", "output_style": "default", "agents": BUILTIN_AGENTS, "skills": [],
               "plugins": BUILTIN_PLUGINS}
STANDIN = '''# pq1c-rehearsal-stand-in: makes no provider call
import json, os, subprocess, sys, time
from pathlib import Path
_here = Path(__file__).resolve().parent
_ledger = Path.home() / ".local" / "state" / "pq1c-rehearsal"
with (_here / "invocations.log").open("a") as _log:
    _log.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "in_cell": os.environ.get("PQ1C_IN_CELL"),
                           "claimed": sorted(p.parent.name for p in _ledger.glob("*/claimed"))}) + "\\n")
if sys.argv[1:] == ["--version"]:
    print("0.0.0 (pq1c stand-in)"); sys.exit(0)
if (_here / "slow").exists():
    time.sleep(4)
if (_here / "nest").exists() and not os.environ.get("PQ1C_STANDIN_NESTED"):     # one level only, guard or not
    _nested = subprocess.run(["claude", "-p", "--model", "claude-fable-5-1"], input="", capture_output=True, text=True,
                             env={**os.environ, "PQ1C_STANDIN_NESTED": "1"}, timeout=60)
    (_here / "nested.json").write_text(json.dumps({"exit": _nested.returncode}))
_project = Path.home() / ".claude" / "projects" / __import__("re").sub(r"[^A-Za-z0-9]", "-", os.getcwd())
if (_here / "stray").exists():          # what a nested call without session persistence leaves: a folder only
    (_project / str(__import__("uuid").uuid4()) / "tool-results").mkdir(parents=True, exist_ok=True)
if (_here / "hooked").exists():         # what a user hook that ran leaves in the session's transcript
    def _hook_record():
        for transcript in _project.glob("*.jsonl"):
            with transcript.open("a") as out:
                out.write(json.dumps({"type": "attachment", "attachment": {"type": "hook_success",
                                      "hookEvent": "SessionStart", "hookName": "SessionStart:startup"}}) + "\\n")
    __import__("atexit").register(_hook_record)
# The shim counts its plan steps beside argv[0]: count per cell (the cell's bin), not beside the stand-in.
sys.argv[0] = str(Path.cwd().parent / "bin" / "claude")
os.environ.setdefault("AGENT_SHIM_PLAN", (_here / "plan.json").read_text())
os.environ.setdefault("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))
''' + (FAKE_CLAUDE.replace(_RESULT, _RESULT[:-1] + _USAGE + "}")
   .replace(_INIT, '"session_id": session, **' + repr(INIT_FIELDS) + "}")
   # The real CLI keeps a workspace's transcripts under projects/<its path, non-alphanumerics replaced by ->.
   .replace(_STORE, 'Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / __import__("re").sub(r"[^A-Za-z0-9]", "-", os.getcwd())'))


def standins(tmp: Path, plan: dict = PLAN) -> Path:
    bin_dir = tmp / "standins"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "claude").write_text(f"#!{sys.executable}\n" + STANDIN, encoding="utf-8")
    (bin_dir / "claude").chmod(0o700)
    (bin_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    return bin_dir


def manifest_sha256(kit: Path = KIT) -> str:
    """What the operator takes from the plan's ledger; here, the kit's own manifest digest."""
    return hashlib.sha256((kit / "manifest.json").read_bytes()).hexdigest()


def _env(tmp: Path, *, kit: Path, rehearsal: bool, authorized: bool, path: tuple, extra: dict) -> dict:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH" and not key.startswith("PQ1C_")}
    env.update(HOME=str(tmp / "home"), PATH=closed_path(*path), PQ1C_PYTHON=sys.executable,
               PQ1C_MANIFEST_SHA256=manifest_sha256(kit))
    if rehearsal:
        env["PQ1C_REHEARSAL_STANDINS"] = str(tmp / "standins")
    if authorized:
        env["PQ1C_SPEND_AUTHORIZED"] = "yes"   # only ever with stand-ins or stubs on a closed PATH
    return {**env, **extra}


def launch(tmp: Path, cell: str, *, kit: Path = KIT, runtime: Path = REPO, rehearsal: bool = True,
           authorized: bool = False, path: tuple = (), background: bool = False, **extra: str):
    """`run_cell.sh RUNTIME CELL <tmp>/results`; a rehearsal unless `rehearsal=False`."""
    (tmp / "home").mkdir(exist_ok=True)
    argv = ["bash", str(kit / "run_cell.sh"), str(runtime), cell, str(tmp / "results")]
    env = {key: value for key, value in _env(tmp, kit=kit, rehearsal=rehearsal, authorized=authorized, path=path,
                                              extra=extra).items() if value is not None}
    if background:
        return subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return subprocess.run(argv, env=env, capture_output=True, text=True, timeout=600, check=False)


def rehearse(tmp: Path) -> Path:
    """The four cells, one after the other, with the stand-in; returns the results root."""
    standins(tmp)
    for cell in CELLS:
        launched = launch(tmp, cell)
        assert launched.returncode == 0, launched.stderr
    return tmp / "results"


def invocations(tmp: Path) -> list[dict]:
    log = tmp / "standins" / "invocations.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def paid_calls(tmp: Path) -> list[dict]:
    """Stand-in invocations that would have been paid calls (everything but `--version`)."""
    return [call for call in invocations(tmp) if call["argv"] != ["--version"]]


def ledger(tmp: Path) -> Path:
    return tmp / "home" / ".local" / "state" / "pq1c-rehearsal"


def refused(launched: subprocess.CompletedProcess[str], gate: str) -> bool:
    """Refused (exit 3) by `gate`, the cause the refusal names."""
    return launched.returncode == 3 and gate in launched.stderr


def nothing_launched(tmp: Path) -> bool:
    """No paid call, no slot, no cell and no temporary debris in the results root."""
    slots = list(ledger(tmp).iterdir()) if ledger(tmp).exists() else []
    results = tmp / "results"
    left = [path.name for path in results.iterdir() if path.name != "fixture.git"] if results.exists() else []
    return paid_calls(tmp) == [] and slots == [] and left == []


def readout_module():
    """`experiments/pq1c/readout.py` as a module, without writing bytecode into the kit."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("pq1c_readout", KIT / "readout.py")
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode, before = True, sys.dont_write_bytecode
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = before
    return module


def readout(results: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", str(KIT / "readout.py"), str(results), *extra],
                          capture_output=True, text=True, timeout=120, check=False,
                          env={**os.environ, "PATH": closed_path()})


def outcome(results: Path) -> dict:
    shown = readout(results)
    assert shown.returncode == 0, shown.stderr
    return json.loads(shown.stdout)


def copy_cells(source: Path, target: Path, *names: str) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copytree(source / name, target / name, symlinks=True)


def edit_json(path: Path, edit) -> None:
    value = json.loads(path.read_text())
    edit(value)
    path.write_text(json.dumps(value))
