"""Test-only: give a run a `rebased` record that no accepted plan writes (a chosen cut, a torn or invalid record, a
child journal), or one a reader test needs without running the planner. An edit a plan accepts is accepted with
the printed `resume RUN_ID --accept-changes=TOKEN` (Phase 3b T7).

`rebase` stores the program of the workspace's current source in the run root under its digest name and appends
the record with the exact keys of the design (Edit And Continue §4). The program is the one an ordinary `run` of
that source writes: the source is run, through the command line, in a copy of the workspace beside it, and that
run's `closed_program.json` is copied. The cut is the caller's choice; no planner is involved, so a test can also
write a record the reducer must refuse.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cli(workspace: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "orchestrator", *args], cwd=workspace, capture_output=True,
                          text=True, timeout=180, check=False,
                          env={**os.environ, **(env or {}), "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"})


def rows(run_root: Path) -> list[dict]:
    """Complete records only: a torn tail is not a record."""
    return [json.loads(line) for line in (run_root / "memo.jsonl").read_bytes().split(b"\n")[:-1]]


def offsets(run_root: Path) -> list[int]:
    """The byte offset of each complete record, in journal order."""
    lines, at, result = (run_root / "memo.jsonl").read_bytes().split(b"\n")[:-1], 0, []
    for line in lines:
        result.append(at)
        at += len(line) + 1
    return result


def offset_of(run_root: Path, record: str, name: str) -> int:
    """Offset of the last `record` row whose identity ends with ` / name`."""
    return [at for at, row in zip(offsets(run_root), rows(run_root))
            if row["record"] == record and row.get("identity", "").endswith(f" / {name}")][-1]


def store_program(run_root: Path, workspace: Path, run_args: list[str], env: dict[str, str] | None = None) -> str:
    """Store the program of `workspace`'s current source as `closed_program.<hex>.json`; return its digest."""
    copy = workspace.parent / f"{workspace.name}-edited-{len(list(workspace.parent.glob(workspace.name + '-edited-*')))}"
    shutil.copytree(workspace, copy, ignore=shutil.ignore_patterns(".orchestrate"))
    cli(copy, "run", *run_args, env=env)          # its outcome does not matter: the program is published first
    (edited,) = (copy / ".orchestrate" / "runs").iterdir()
    digest = json.loads((edited / "run.json").read_bytes())["program_digest"]
    target = run_root / f"closed_program.{digest.removeprefix('sha256:')}.json"
    if not target.exists():
        shutil.copyfile(edited / "closed_program.json", target)
        target.chmod(0o600)
    return digest


def append_rebased(run_root: Path, digest: str, cut: int | None) -> None:
    record = {"record": "rebased", "program_digest": digest, "from_offset": cut, "time": time.time()}
    with (run_root / "memo.jsonl").open("ab") as journal:
        journal.write(json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n")


def rebase(run_root: Path, workspace: Path, cut: int | None, run_args: list[str],
           env: dict[str, str] | None = None) -> str:
    """Store the workspace's current source for `run_root` and record it with the cut `cut`; return the digest."""
    digest = store_program(run_root, workspace, run_args, env)
    append_rebased(run_root, digest, cut)
    return digest


def tree(run_root: Path) -> dict[str, bytes]:
    return {path.relative_to(run_root).as_posix(): path.read_bytes() for path in sorted(run_root.rglob("*"))
            if path.is_file() and path.name != "run.lock"}
