#!/usr/bin/env python3
"""Q5 isolated turn-delivery matrix for codex CLI inside tmux.

Measures which paste/keystroke sequences reliably commit a large pasted
turn in an idle codex composer, without the orchestrator. Each cell runs a
fresh codex TUI session (pre-trusted cwd, YOLO mode) inside a private tmux
server, delivers a payload with the production adapter's mechanics
(``load-buffer`` + ``paste-buffer`` + ``send-keys``), and detects success
via a filesystem sentinel the model is instructed to create. Pane captures
are archived per run for the report; pane interpretation here is
harness-only evidence and never a production input (the adapter's
declared-inputs boundary is unaffected).

The special ``KILL`` cell reproduces the coordinator close race: it starts
a long-running tool call, offers ``/exit`` + ENTER mid-call (exactly what
``_close_and_join`` does before flushing the submit receipt), and records
whether the tool call's process survives.

Usage:
  python scripts/q5_turn_delivery_matrix.py --workdir ~/.tmp/q5-debug2/exp \
      [--cells A,C,KILL] [--repeat 1] [--results DIR]

The workdir must be pre-trusted in ~/.codex/config.toml.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

CODEX_COMMAND = (
    "codex",
    "--model",
    "gpt-5.5",
    "--config",
    "model_reasoning_effort=low",
    "--dangerously-bypass-approvals-and-sandbox",
)
READY_MARKER = "Tip:"
READY_TIMEOUT_SEC = 30.0
SENTINEL_TIMEOUT_SEC = 90.0
KEY_NAMES = {"ENTER": "Enter", "C-M": "C-m", "KPENTER": "KPEnter"}


@dataclasses.dataclass(frozen=True)
class Cell:
    cell_id: str
    paste: str  # "bracketed" | "raw" | "literal"
    settle_sec: float
    keys: tuple[str, ...]
    payload_bytes: int
    trailing_newline: bool
    width: int = 80
    height: int = 24
    note: str = ""


CELLS: tuple[Cell, ...] = (
    Cell("A", "raw", 0.0, ("ENTER",), 2048, False, note="attempt-4 replica"),
    Cell("B", "raw", 0.25, ("ENTER", "ENTER"), 2048, False, note="V1 replica"),
    Cell("C", "bracketed", 1.0, ("ENTER", "ENTER"), 2048, False,
         note="V2 production replica"),
    Cell("D", "bracketed", 0.25, ("ENTER",), 2048, False),
    Cell("E", "bracketed", 0.0, ("ENTER",), 2048, False),
    Cell("F", "bracketed", 1.0, ("ENTER",), 2048, False),
    Cell("G", "raw", 1.0, ("ENTER", "ENTER"), 2048, False),
    Cell("H", "raw", 2.0, ("ENTER", "ENTER"), 2048, False),
    Cell("I", "bracketed", 1.0, ("C-M",), 2048, False),
    Cell("J", "bracketed", 1.0, ("KPENTER",), 2048, False),
    Cell("K", "literal", 0.5, ("ENTER",), 2048, False,
         note="send-keys -l chunked typing"),
    Cell("L", "bracketed", 1.0, ("ENTER", "ENTER"), 8192, False),
    Cell("M", "bracketed", 1.0, ("ENTER", "ENTER"), 512, False),
    Cell("N", "bracketed", 1.0, ("ENTER",), 2048, True),
    Cell("O", "raw", 0.0, ("ENTER",), 2048, True),
    Cell("S", "raw", 0.0, ("ENTER",), 512, False,
         note="small raw control"),
    Cell("X", "bracketed", 1.0, ("ENTER", "ENTER"), 2048, False,
         width=200, height=50, note="wide-pane variant"),
)


class Tmux:
    def __init__(self, socket_path: Path) -> None:
        self.socket_path = socket_path

    def run(
        self,
        *args: str,
        input_bytes: bytes | None = None,
        timeout: float = 10.0,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["tmux", "-S", str(self.socket_path), *args],
            input=input_bytes,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def capture(self, target: str) -> str:
        completed = self.run("capture-pane", "-p", "-J", "-t", target, "-S", "-400")
        return completed.stdout.decode("utf-8", errors="replace")

    def kill(self) -> None:
        self.run("kill-server")


def build_payload(cell: Cell, run_id: str, workdir: Path) -> str:
    ack = workdir / f"ack_{run_id}"
    frame = json.dumps(
        {
            "schema_version": "q5_matrix_probe.v1",
            "cell": cell.cell_id,
            "run": run_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    instruction = (
        "You are inside a keystroke-delivery test harness. "
        "Execute exactly one shell command now: "
        f"touch {ack}\n"
        "Then reply DONE and stop. Ignore the filler section below; it "
        "only pads this message to a target byte size."
    )
    body = frame + "\n\n" + instruction + "\n\nFILLER:\n"
    filler_line = (
        "lorem-ipsum filler line for payload padding; no action required.\n"
    )
    while len(body.encode("utf-8")) < cell.payload_bytes:
        body += filler_line
    body = body[: max(cell.payload_bytes, len(frame) + len(instruction) + 12)]
    # Never end mid-escape; trim to the last full line then normalize tail.
    if cell.trailing_newline:
        if not body.endswith("\n"):
            body += "\n"
    else:
        body = body.rstrip("\n")
    return body


def wait_for(predicate, timeout_sec: float, interval: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def start_codex(tmux: Tmux, cell: Cell, workdir: Path) -> bool:
    tmux.run(
        "new-session",
        "-d",
        "-s",
        "cell",
        "-x",
        str(cell.width),
        "-y",
        str(cell.height),
        "-c",
        str(workdir),
    )
    tmux.run("set-window-option", "-g", "remain-on-exit", "on")
    command = " ".join(CODEX_COMMAND)
    tmux.run("send-keys", "-t", "cell:0.0", "-l", "--", command)
    tmux.run("send-keys", "-t", "cell:0.0", "Enter")
    return wait_for(
        lambda: READY_MARKER in tmux.capture("cell:0.0"),
        READY_TIMEOUT_SEC,
    )


def deliver(tmux: Tmux, cell: Cell, payload: str) -> None:
    target = "cell:0.0"
    if cell.paste == "literal":
        chunk_size = 256
        for start in range(0, len(payload), chunk_size):
            chunk = payload[start : start + chunk_size]
            tmux.run("send-keys", "-t", target, "-l", "--", chunk)
            time.sleep(0.05)
    else:
        tmux.run(
            "load-buffer",
            "-b",
            "q5cell",
            "-",
            input_bytes=payload.encode("utf-8"),
        )
        paste_args = ["paste-buffer", "-d", "-b", "q5cell", "-t", target]
        if cell.paste == "bracketed":
            paste_args.insert(1, "-p")
        tmux.run(*paste_args)
    for key in cell.keys:
        time.sleep(cell.settle_sec)
        tmux.run("send-keys", "-t", target, KEY_NAMES[key.upper()])


def run_cell(
    cell: Cell,
    workdir: Path,
    results_dir: Path,
    attempt: int,
) -> dict[str, object]:
    run_id = f"{cell.cell_id}_{attempt}_{uuid.uuid4().hex[:6]}"
    socket_path = results_dir / f"tmux-{run_id}.sock"
    tmux = Tmux(socket_path)
    record: dict[str, object] = {
        "run_id": run_id,
        **dataclasses.asdict(cell),
        "attempt": attempt,
    }
    try:
        if not start_codex(tmux, cell, workdir):
            record["outcome"] = "codex_not_ready"
            record["capture_final"] = tmux.capture("cell:0.0")[-2000:]
            return record
        payload = build_payload(cell, run_id, workdir)
        record["payload_sha_len"] = len(payload.encode("utf-8"))
        started = time.monotonic()
        deliver(tmux, cell, payload)
        time.sleep(3.0)
        post_keys = tmux.capture("cell:0.0")
        (results_dir / f"pane-{run_id}-postkeys.txt").write_text(
            post_keys, encoding="utf-8"
        )
        ack = workdir / f"ack_{run_id}"
        submitted = wait_for(ack.exists, SENTINEL_TIMEOUT_SEC)
        elapsed = time.monotonic() - started
        final = tmux.capture("cell:0.0")
        (results_dir / f"pane-{run_id}-final.txt").write_text(
            final, encoding="utf-8"
        )
        record["outcome"] = "submitted" if submitted else "not_submitted"
        record["elapsed_sec"] = round(elapsed, 2)
        record["paste_placeholder_seen"] = "Pasted content" in (
            post_keys + final
        ) or "[Pasted Content" in (post_keys + final)
    finally:
        tmux.kill()
        socket_path.unlink(missing_ok=True)
    return record


def run_kill_cell(
    workdir: Path,
    results_dir: Path,
    attempt: int,
) -> dict[str, object]:
    """Reproduce the close race: /exit while a tool call is running."""

    run_id = f"KILL_{attempt}_{uuid.uuid4().hex[:6]}"
    socket_path = results_dir / f"tmux-{run_id}.sock"
    tmux = Tmux(socket_path)
    cell = Cell("KILL", "bracketed", 1.0, ("ENTER", "ENTER"), 0, False)
    start_marker = workdir / f"tool_start_{run_id}"
    done_marker = workdir / f"tool_done_{run_id}"
    record: dict[str, object] = {"run_id": run_id, "cell_id": "KILL",
                                 "attempt": attempt}
    try:
        if not start_codex(tmux, cell, workdir):
            record["outcome"] = "codex_not_ready"
            return record
        payload = (
            '{"schema_version":"q5_matrix_probe.v1","cell":"KILL"}\n\n'
            "You are inside a test harness. Execute exactly one shell "
            "command now (a single tool call):\n"
            f"touch {start_marker} && sleep 25 && touch {done_marker}\n"
            "Then reply DONE and stop."
        )
        tmux.run(
            "load-buffer", "-b", "q5cell", "-",
            input_bytes=payload.encode("utf-8"),
        )
        tmux.run("paste-buffer", "-p", "-d", "-b", "q5cell", "-t", "cell:0.0")
        time.sleep(1.0)
        tmux.run("send-keys", "-t", "cell:0.0", "Enter")
        time.sleep(1.0)
        tmux.run("send-keys", "-t", "cell:0.0", "Enter")
        if not wait_for(start_marker.exists, 60.0):
            record["outcome"] = "tool_never_started"
            record["capture_final"] = tmux.capture("cell:0.0")[-2000:]
            return record
        # Tool call is now running inside codex. Offer graceful close with
        # the production adapter's exact mechanics.
        tmux.run(
            "load-buffer", "-b", "q5cell", "-", input_bytes=b"/exit"
        )
        tmux.run("paste-buffer", "-p", "-d", "-b", "q5cell", "-t", "cell:0.0")
        time.sleep(1.0)
        tmux.run("send-keys", "-t", "cell:0.0", "Enter")
        time.sleep(1.0)
        tmux.run("send-keys", "-t", "cell:0.0", "Enter")
        exit_offered = time.monotonic()
        tool_survived = wait_for(done_marker.exists, 40.0)
        pane_dead = tmux.run(
            "display-message", "-p", "-t", "cell:0.0", "#{pane_dead}"
        ).stdout.decode().strip()
        final = tmux.capture("cell:0.0")
        (results_dir / f"pane-{run_id}-final.txt").write_text(
            final, encoding="utf-8"
        )
        record["outcome"] = (
            "tool_survived_exit" if tool_survived else "tool_killed_by_exit"
        )
        record["pane_dead_after_exit"] = pane_dead
        record["seconds_after_exit_offer"] = round(
            time.monotonic() - exit_offered, 2
        )
    finally:
        tmux.kill()
        socket_path.unlink(missing_ok=True)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--results", type=Path, default=None)
    parser.add_argument("--cells", type=str, default=None)
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    workdir = args.workdir.expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    results_dir = (
        args.results
        or workdir / f"results-{time.strftime('%Y%m%d-%H%M%S')}"
    )
    results_dir.mkdir(parents=True, exist_ok=True)
    if shutil.which("codex") is None or shutil.which("tmux") is None:
        print("codex and tmux are required", file=sys.stderr)
        return 2

    wanted = (
        {token.strip().upper() for token in args.cells.split(",")}
        if args.cells
        else None
    )
    records: list[dict[str, object]] = []
    jsonl = results_dir / "matrix.jsonl"
    for cell in CELLS:
        if wanted is not None and cell.cell_id.upper() not in wanted:
            continue
        for attempt in range(1, args.repeat + 1):
            record = run_cell(cell, workdir, results_dir, attempt)
            records.append(record)
            with jsonl.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
            print(
                f"[{record['run_id']}] {record.get('outcome')} "
                f"(paste={cell.paste} settle={cell.settle_sec} "
                f"keys={'+'.join(cell.keys)} bytes={cell.payload_bytes} "
                f"nl={cell.trailing_newline} {cell.width}x{cell.height})",
                flush=True,
            )
    if wanted is None or "KILL" in wanted:
        for attempt in range(1, args.repeat + 1):
            record = run_kill_cell(workdir, results_dir, attempt)
            records.append(record)
            with jsonl.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
            print(
                f"[{record['run_id']}] {record.get('outcome')}",
                flush=True,
            )
    print(f"results: {jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
