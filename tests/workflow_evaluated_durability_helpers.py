"""Bounded persistence model for evaluated run publication.

A launcher wraps the real os-level operations of one public CLI process. Each
mkdir, create, write, truncate, rename, unlink and fsync on a path under the
test workspace is recorded with the whole workspace tree before and after it.
The parent derives, for every boundary between two recorded operations, two
recovered images: the visible tree (every unsynchronized change survived) and
the durable tree (only file bytes captured by a file fsync and directory
entries captured by a directory fsync survived; the pre-run workspace is the
durable base). Dispatches are counted in a log outside the workspace, so their
absence is provable even when the image loses every run file. This models lost
page-cache writes; it is not a SIGKILL test and not a claim about every disk.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys


RECORDER = r'''
import base64, builtins, json, os, shutil

WORKSPACE = os.path.realpath(os.environ["DURABILITY_WORKSPACE"])
TRACE = os.environ["DURABILITY_TRACE"]
DISPATCH = os.environ["DURABILITY_DISPATCH_LOG"]
FAIL_FSYNC = int(os.environ.get("DURABILITY_FAIL_FSYNC", "0"))
REAL = {name: getattr(os, name) for name in (
    "mkdir", "open", "write", "fsync", "replace", "rename", "unlink", "rmdir", "ftruncate")}
REAL_COPY = shutil.copyfileobj
state = {"busy": False, "done": False, "fsyncs": 0}


def inside(path):
    return path == WORKSPACE or path.startswith(WORKSPACE + os.sep)


def fd_target(fd):
    try:
        return os.readlink(f"/proc/self/fd/{fd}")
    except OSError:
        return ""


def target(path, dir_fd=None):
    path = os.fsdecode(path)
    if dir_fd is not None and not os.path.isabs(path):
        return os.path.join(fd_target(dir_fd), path)
    return os.path.abspath(path)


def dispatched():
    try:
        with builtins.open(DISPATCH, "rb") as stream:
            return stream.read().count(b"\n")
    except FileNotFoundError:
        return 0


def tree():
    rows = {".": ["dir", os.lstat(WORKSPACE).st_ino, None]}
    for current, dirs, files in os.walk(WORKSPACE):
        for name in sorted(dirs + files):
            path = os.path.join(current, name)
            rel = os.path.relpath(path, WORKSPACE)
            ino = os.lstat(path).st_ino
            if os.path.islink(path):
                rows[rel] = ["symlink", ino, os.readlink(path)]
            elif os.path.isdir(path):
                rows[rel] = ["dir", ino, None]
            else:
                with builtins.open(path, "rb") as stream:
                    rows[rel] = ["file", ino, base64.b64encode(stream.read()).decode()]
    return rows


def log(row):
    with builtins.open(TRACE, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")


def traced(op, path, call, **extra):
    if state["busy"] or state["done"] or not inside(path):
        return call()
    state["busy"] = True
    try:
        before = {"dispatched": dispatched(), "tree": tree()}
        if before["dispatched"]:
            state["done"] = True
            log({"op": "dispatch-observed", "path": None, "before": before})
            return call()
        row = {"op": op, "path": os.path.relpath(path, WORKSPACE), "before": before, **extra}
        try:
            result = call()
        except OSError as exc:
            log({**row, "error": str(exc)})
            raise
        log({**row, "after": {"dispatched": dispatched(), "tree": tree()}})
        return result
    finally:
        state["busy"] = False


def mkdir(path, mode=0o777, *, dir_fd=None):
    return traced("mkdir", target(path, dir_fd), lambda: REAL["mkdir"](path, mode, dir_fd=dir_fd))


def open_(path, flags, mode=0o777, *, dir_fd=None):
    destination = target(path, dir_fd)
    call = lambda: REAL["open"](path, flags, mode, dir_fd=dir_fd)
    exists = os.path.lexists(destination)
    if flags & os.O_CREAT and not exists:
        return traced("create", destination, call)
    if flags & os.O_TRUNC and exists:
        return traced("truncate", destination, call)
    return call()


def write(fd, data):
    return traced("write", fd_target(fd), lambda: REAL["write"](fd, data), size=len(data))


def injected_failure():
    raise OSError(5, "injected fsync failure")


def fsync(fd):
    path = fd_target(fd)
    call = lambda: REAL["fsync"](fd)
    if inside(path) and not state["busy"] and not state["done"]:
        state["fsyncs"] += 1
        if state["fsyncs"] == FAIL_FSYNC:
            call = injected_failure
    kind = "dir" if os.path.isdir(path) else "file"
    return traced("fsync", path, call, kind=kind, ino=os.fstat(fd).st_ino)


def replace(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
    source = os.path.relpath(target(src, src_dir_fd), WORKSPACE)
    call = lambda: REAL["replace"](src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
    return traced("rename", target(dst, dst_dir_fd), call, source=source)


def rename(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
    source = os.path.relpath(target(src, src_dir_fd), WORKSPACE)
    call = lambda: REAL["rename"](src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
    return traced("rename", target(dst, dst_dir_fd), call, source=source)


def unlink(path, *, dir_fd=None):
    return traced("unlink", target(path, dir_fd), lambda: REAL["unlink"](path, dir_fd=dir_fd))


def rmdir(path, *, dir_fd=None):
    return traced("rmdir", target(path, dir_fd), lambda: REAL["rmdir"](path, dir_fd=dir_fd))


def ftruncate(fd, length):
    return traced("truncate", fd_target(fd), lambda: REAL["ftruncate"](fd, length))


def copyfileobj(source, destination, length=0):
    try:
        path = fd_target(destination.fileno())
    except (AttributeError, OSError, ValueError):
        return REAL_COPY(source, destination, length)

    def call():
        REAL_COPY(source, destination, length)
        destination.flush()
    return traced("write", path, call)


os.mkdir, os.open, os.write, os.fsync = mkdir, open_, write, fsync
os.replace, os.rename, os.unlink, os.rmdir, os.ftruncate = replace, rename, unlink, rmdir, ftruncate
shutil.copyfileobj = copyfileobj
from orchestrator.cli import main
raise SystemExit(main())
'''

PROBE = '''\
import os
from pathlib import Path
log = Path.cwd().parent / (Path.cwd().name + ".dispatches")
with log.open("a", encoding="utf-8") as stream:
    stream.write("first\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("5", encoding="utf-8")
'''

SOURCE = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defworkflow run () -> Int
    (command-result first :argv ("python" "probe.py") :returns Int)))
'''


def write_workspace(workspace: Path) -> list[str]:
    """Write the one-command program and return its public run arguments."""
    workspace.mkdir(parents=True)
    (workspace / "main.orc").write_text(SOURCE, encoding="utf-8")
    (workspace / "probe.py").write_text(PROBE, encoding="utf-8")
    (workspace / "commands.json").write_text(json.dumps({
        "first": {"stable_command": ["python", "probe.py"], "closure": ["probe.py"]},
    }), encoding="utf-8")
    return ["run", "main.orc", "--command-boundaries-file", "commands.json"]


def dispatch_log(workspace: Path) -> Path:
    return workspace.parent / f"{workspace.name}.dispatches"


def dispatches(workspace: Path) -> int:
    log = dispatch_log(workspace)
    return log.read_text(encoding="utf-8").count("\n") if log.exists() else 0


def cli_env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1]), "PYTHONDONTWRITEBYTECODE": "1"}


def record_public_run(workspace: Path, control: Path, argv: list[str], *, fail_fsync: int = 0):
    """Run the public CLI under the recorder; return the process and its operation trace."""
    control.mkdir(parents=True, exist_ok=True)
    launcher, trace = control / "recorder.py", control / f"trace-{fail_fsync}.jsonl"
    launcher.write_text(RECORDER, encoding="utf-8")
    env = {**cli_env(), "DURABILITY_WORKSPACE": str(workspace), "DURABILITY_TRACE": str(trace),
           "DURABILITY_DISPATCH_LOG": str(dispatch_log(workspace)), "DURABILITY_FAIL_FSYNC": str(fail_fsync)}
    result = subprocess.run([sys.executable, str(launcher), *argv], cwd=workspace, env=env,
                            capture_output=True, text=True, check=False, timeout=120)
    rows = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()] if trace.exists() else []
    return result, rows


def _decoded(raw: dict[str, list]) -> dict[str, tuple[str, bytes | str | None]]:
    tree = {}
    for rel, (kind, _ino, payload) in raw.items():
        if rel != ".":
            tree[rel] = (kind, base64.b64decode(payload) if kind == "file" else payload)
    return tree


def _parent(rel: str) -> str:
    return PurePosixPath(rel).parent.as_posix()


class DurableState:
    """Inode-level durable contents and directory entries, starting from a durable base."""

    def __init__(self, base: dict[str, list]) -> None:
        self.root = base["."][1]
        self.kinds: dict[int, str] = {}
        self.payloads: dict[int, bytes | str] = {}
        self.entries: dict[int, dict[str, int]] = {}
        self._learn(base)
        for rel, (kind, ino, _payload) in base.items():
            if rel != ".":
                self.entries.setdefault(base[_parent(rel)][1], {})[PurePosixPath(rel).name] = ino
            if kind == "file":
                self.payloads[ino] = base64.b64decode(base[rel][2])

    def _learn(self, tree: dict[str, list]) -> None:
        for kind, ino, payload in tree.values():
            self.kinds.setdefault(ino, kind)
            if kind == "symlink":
                self.payloads[ino] = payload

    def sync(self, op: dict) -> None:
        tree = op["after"]["tree"]
        self._learn(tree)
        (rel,) = [rel for rel, row in tree.items() if row[1] == op["ino"]]
        if op["kind"] == "dir":
            self.entries[op["ino"]] = {
                PurePosixPath(child).name: row[1] for child, row in tree.items()
                if child != "." and _parent(child) == rel
            }
        else:
            self.payloads[op["ino"]] = base64.b64decode(tree[rel][2])

    def image(self) -> dict[str, tuple[str, bytes | str | None]]:
        image: dict[str, tuple[str, bytes | str | None]] = {}
        pending = [(self.root, "")]
        while pending:
            directory, prefix = pending.pop()
            for name, ino in self.entries.get(directory, {}).items():
                rel, kind = prefix + name, self.kinds[ino]
                if kind == "dir":
                    image[rel] = ("dir", None)
                    pending.append((ino, rel + "/"))
                else:
                    image[rel] = (kind, self.payloads.get(ino, b""))
        return dict(sorted(image.items()))


@dataclass(frozen=True)
class CrashPoint:
    label: str
    dispatched: int
    visible: dict
    durable: dict


def crash_points(trace: list[dict]) -> list[CrashPoint]:
    """Every boundary before and after each recorded operation, through the first dispatch."""
    assert trace and trace[-1]["op"] == "dispatch-observed", "trace did not reach the first dispatch"
    durable = DurableState(trace[0]["before"]["tree"])
    points = []
    for index, op in enumerate(trace):
        name = f"{index:03d}-{op['op']}-{op.get('kind', '')}:{op['path']}"
        points.append(CrashPoint(f"before {name}", op["before"]["dispatched"],
                                 _decoded(op["before"]["tree"]), durable.image()))
        if "error" in op or op["op"] == "dispatch-observed":
            continue
        if op["op"] == "fsync":
            durable.sync(op)
        points.append(CrashPoint(f"after {name}", op["after"]["dispatched"],
                                 _decoded(op["after"]["tree"]), durable.image()))
    return points


def image_digest(image: dict) -> str:
    digest = hashlib.sha256()
    for rel, (kind, payload) in sorted(image.items()):
        data = payload if isinstance(payload, bytes) else str(payload).encode()
        digest.update(json.dumps([rel, kind]).encode() + hashlib.sha256(data).digest())
    return digest.hexdigest()


def materialize(image: dict, workspace: Path) -> None:
    workspace.mkdir(parents=True)
    for rel, (kind, payload) in image.items():
        path = workspace / rel
        if kind == "dir":
            path.mkdir(parents=True, exist_ok=True)
        elif kind == "symlink":
            path.symlink_to(payload)
        else:
            path.write_bytes(payload)


def operation_counts(trace: list[dict]) -> dict[str, int]:
    """Count recorded operations by kind; failed calls are counted under their own key."""
    counts: dict[str, int] = {}
    for op in trace:
        key = op["op"] + (f"-{op['kind']}" if "kind" in op else "") + ("-error" if "error" in op else "")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
