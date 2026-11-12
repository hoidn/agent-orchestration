"""Terminal lines for `run` and `resume`: a view of the memo rows as they are appended.

Progress goes to stderr and the terminal value to stdout. Only the command line
enables the lines (`terminal_lines` on the parsed arguments); library callers
get a disabled reporter. The reporter reads nothing but the `stderr.txt` of an
attempt that failed. Nothing it does may fail the run: a write error turns off
that stream alone (and points a dead descriptor at /dev/null), and any other
error in the observer turns the reporter off.
The line grammar is owned by specs/cli.md ("Evaluated execution").
"""

from __future__ import annotations

import errno
import io
import json
import os
import shlex
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from orchestrator.cli.recovery import REFUSAL_CODES, recovery_lines, state_dir_flag

STDERR_TAIL_LINES = 10
_STDERR_TAIL_BYTES = 64 * 1024


def launcher() -> str:
    """The command prefix that reruns this program: the installed script, or this interpreter's module form."""
    if Path(sys.argv[0]).name != "__main__.py":
        return "orchestrator"
    return f"{shlex.quote(sys.executable) if sys.executable else 'python'} -m orchestrator"


class _LineEndTracker(io.RawIOBase):
    """Raw fd-1 writer that remembers whether the last byte written ended a line."""

    def __init__(self, fd: int) -> None:
        super().__init__()
        self.fd = fd
        self.ends_line = True

    def writable(self) -> bool:
        return True

    def fileno(self) -> int:
        return self.fd

    def write(self, data) -> int:
        written = os.write(self.fd, data)
        if written:
            self.ends_line = bytes(data[written - 1:written]) == b"\n"
        return written


_stdout_tracker: _LineEndTracker | None = None


def track_stdout() -> None:
    """Route the process stdout (text and `.buffer` writers alike) through a line-end tracker.

    Only the real process stdout is replaced, so an embedding caller's replacement is left alone.
    """
    global _stdout_tracker
    stdout = sys.stdout
    if stdout is None or stdout is not sys.__stdout__:
        return
    try:
        stdout.flush()
        tracker = _LineEndTracker(stdout.fileno())
        sys.stdout = io.TextIOWrapper(io.BufferedWriter(tracker), encoding=stdout.encoding,
                                      errors=stdout.errors, line_buffering=stdout.line_buffering)
    except (OSError, ValueError):
        return
    _stdout_tracker = tracker


def say(line: str) -> None:
    """One stderr line outside a reporter (dry run, default manifests); a missing or broken stderr drops it."""
    stream = sys.stderr
    if stream is None:
        return
    try:
        stream.write(line + "\n")
        stream.flush()
    except Exception as exc:
        _silence_if_dead(stream, exc)


_DEAD_DESCRIPTOR = {errno.EPIPE, errno.EBADF, errno.EIO}


def _silence_if_dead(stream, exc: Exception) -> None:
    """Point a dead stream's descriptor at /dev/null so the shutdown flush cannot fail; leave a live one alone."""
    if not (isinstance(exc, OSError) and exc.errno in _DEAD_DESCRIPTOR):
        return
    try:
        null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null, stream.fileno())
        os.close(null)
    except Exception:  # an unusual stream object: dropping our reference is all that is left
        pass


def _stderr_tail(lines: list[str]) -> list[str]:
    """The last lines; when the last Python traceback's exception line falls before them, it replaces the first, last.

    A multi-line exception message can push that line out of the tail, which then shows only the message's end.
    """
    tail = lines[-STDERR_TAIL_LINES:]
    headers = [index for index, line in enumerate(lines) if line.startswith("Traceback (most recent call last):")]
    if not headers:
        return tail
    exception = next((index for index in range(headers[-1] + 1, len(lines))
                      if lines[index][:1] not in {"", " ", "\t"}), None)
    if exception is None or exception >= len(lines) - len(tail):
        return tail
    return [*tail[1:], lines[exception]]


class TerminalReporter:
    """Print the run line, effect rows, the failure block, the resume line and the result."""

    def __init__(self, run_id: str, run_root: Path, *, quiet: bool, state_dir: str | None,
                 enabled: bool = True) -> None:
        self.run_id = run_id
        self.run_root = Path(run_root)
        self.quiet = quiet
        self.state_dir = state_dir
        self.err = sys.stderr if enabled else None
        self.out = sys.stdout if enabled else None
        self.launcher = launcher()
        self._attempt_dirs: dict[str, str] = {}
        self.error_code: str | None = None
        self._announce_pending = False
        self._failure_shown = False

    def _write(self, name: str, *lines: str) -> None:
        stream = getattr(self, name)
        if stream is None:
            return
        try:
            for line in lines:
                stream.write(line + "\n")
            stream.flush()
        except Exception as exc:
            setattr(self, name, None)
            _silence_if_dead(stream, exc)

    def _progress(self, line: str) -> None:
        if not self.quiet:
            self._write("err", line)

    def announce(self, *, lazy: bool = False) -> None:
        """The run line; `lazy` defers it to the first effect row or failure, so a refusal's line stays first."""
        self._announce_pending = lazy
        if not lazy:
            self._progress(f"run     {self.run_id}  {self.run_root}")

    def _announce_now(self) -> None:
        if self._announce_pending:
            self.announce()

    def record(self, row: Mapping[str, Any]) -> None:
        """The memo observer, called after each durable append; nothing may escape from it."""
        try:
            self._record(row)
        except Exception:
            self.err = None  # the stdout result still prints

    def _record(self, row: Mapping[str, Any]) -> None:
        kind = row.get("record")
        if kind in {"started", "committed", "failed"}:
            self._announce_now()
        if kind == "started":
            self._attempt_dirs[row["identity"]] = str(Path(row["result_path"]).parent)
            self._progress(f"start   {row['identity']}  attempt {row['attempt']}")
        elif kind == "committed":
            self._progress(f"commit  {row['identity']}  attempt {row['attempt']}")
        elif kind == "failed":
            self._failure_shown = True
            self._write("err", *self._failure_block(row))

    def _failure_block(self, row: Mapping[str, Any]) -> list[str]:
        lines = [f"failed  {row['identity']}  attempt {row['attempt']}  [{row.get('code')}]"]
        attempt_dir = self._attempt_dirs.get(row["identity"])
        stderr_path = None if attempt_dir is None else self.run_root / attempt_dir / "stderr.txt"
        if stderr_path is None or not stderr_path.is_file():
            return lines
        with stderr_path.open("rb") as stream:
            stream.seek(max(0, stream.seek(0, os.SEEK_END) - _STDERR_TAIL_BYTES))
            tail = stream.read().decode("utf-8", errors="replace").splitlines()
        return [*lines, f"        stderr: {stderr_path}", *(f"        | {line}" for line in _stderr_tail(tail))]

    def error(self, exc: Exception, *, header: Mapping[str, Any] | None = None, stored_program: Any = None,
              snapshot: Any = None) -> None:
        """Recovery lines after a refusal's (or failure's) logged `[code] message` line."""
        try:
            self.error_code = getattr(exc, "code", "resume_preflight_failed")
            if self._failure_shown and self.error_code not in REFUSAL_CODES:
                return  # the failure block and the resume line already say what happened and what continues
            self._write("err", *recovery_lines(exc, run_id=self.run_id, launcher=self.launcher, state_dir=self.state_dir,
                                               header=header, stored_program=stored_program, snapshot=snapshot))
        except Exception:
            self.err = None

    def resumable(self, exit_code: int) -> bool:
        """Whether `resume` continues: not after a refusal, whose recovery lines say what does."""
        if self.error_code is None:
            return True
        return exit_code == 1 and self.error_code not in REFUSAL_CODES

    def run_failed(self) -> None:
        """The resume line; printed under `--quiet` too, since it is how a failed quiet run is found again."""
        self._announce_now()
        self._write("err", f"resume  {self.launcher} resume {self.run_id}{state_dir_flag(self.state_dir)}")

    def waiting(self, identities: Iterable[str]) -> None:
        self._announce_now()
        command = f"{self.launcher} input get {self.run_id}{state_dir_flag(self.state_dir)}"
        self._write("err", *(f"waiting {identity}  {command}" for identity in identities))

    def result(self, value: Any) -> None:
        """One line of compact JSON that starts a line of its own, after streamed output that did not end one.

        Characters the stream's encoding cannot write are JSON escapes, so the line stays valid JSON.
        """
        line = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        try:
            line.encode(getattr(self.out, "encoding", None) or "utf-8")
        except (UnicodeEncodeError, LookupError):
            line = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if self.out is not None and _stdout_tracker is not None:
            try:
                self.out.flush()
                if not _stdout_tracker.ends_line:
                    line = "\n" + line
            except Exception:
                pass  # the write below turns this stream off
        self._write("out", line)
