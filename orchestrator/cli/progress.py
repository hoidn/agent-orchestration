"""Terminal lines for `run` and `resume`: a view of the memo rows as they are appended.

Progress goes to stderr and the terminal value to stdout. The reporter reads
nothing but the `stderr.txt` of an attempt that failed; a write error on the
terminal turns it off and never fails the run. The line grammar is owned by
specs/cli.md ("Evaluated execution").
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, TextIO

from orchestrator.cli.recovery import REFUSAL_CODES, recovery_lines, state_dir_flag

STDERR_TAIL_LINES = 10


def launcher() -> str:
    """The command prefix that reruns this program: the installed script or the module form."""
    return "python -m orchestrator" if Path(sys.argv[0]).name == "__main__.py" else "orchestrator"


class TerminalReporter:
    """Print the run line, effect rows, the failure block, the resume line and the result."""

    def __init__(self, run_id: str, run_root: Path, *, quiet: bool, state_dir: str | None,
                 err: TextIO | None = None, out: TextIO | None = None) -> None:
        self.run_id = run_id
        self.run_root = Path(run_root)
        self.quiet = quiet
        self.state_dir = state_dir
        self.err = sys.stderr if err is None else err
        self.out = sys.stdout if out is None else out
        self.launcher = launcher()
        self._attempt_dirs: dict[str, str] = {}
        self._off = False
        self.error_code: str | None = None
        self._announce_pending = False

    def _write(self, stream: TextIO, *lines: str) -> None:
        if self._off:
            return
        try:
            for line in lines:
                stream.write(line + "\n")
            stream.flush()
        except (OSError, ValueError):
            self._off = True

    def _progress(self, line: str) -> None:
        if not self.quiet:
            self._write(self.err, line)

    def announce(self, *, lazy: bool = False) -> None:
        """The run line; `lazy` defers it to the first effect row or failure, so a refusal's line stays first."""
        self._announce_pending = lazy
        if not lazy:
            self._progress(f"run     {self.run_id}  {self.run_root}")

    def _announce_now(self) -> None:
        if self._announce_pending:
            self.announce()

    def record(self, row: Mapping[str, Any]) -> None:
        """The memo observer: one call per appended row."""
        kind = row.get("record")
        if kind in {"started", "committed", "failed"}:
            self._announce_now()
        if kind == "started":
            self._attempt_dirs[row["identity"]] = str(Path(row["result_path"]).parent)
            self._progress(f"start   {row['identity']}  attempt {row['attempt']}")
        elif kind == "committed":
            self._progress(f"commit  {row['identity']}  attempt {row['attempt']}")
        elif kind == "failed":
            self._write(self.err, *self._failure_block(row))

    def _failure_block(self, row: Mapping[str, Any]) -> list[str]:
        lines = [f"failed  {row['identity']}  attempt {row['attempt']}  [{row.get('code')}]"]
        attempt_dir = self._attempt_dirs.get(row["identity"])
        stderr_path = None if attempt_dir is None else self.run_root / attempt_dir / "stderr.txt"
        if stderr_path is None or not stderr_path.is_file():
            return lines
        lines.append(f"        stderr: {stderr_path}")
        try:
            tail = stderr_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return lines
        return lines + [f"        | {line}" for line in tail[-STDERR_TAIL_LINES:]]

    def error(self, exc: Exception, *, header: Mapping[str, Any] | None = None, stored_program: Any = None) -> None:
        """Recovery lines after a refusal's (or failure's) logged `[code] message` line."""
        self.error_code = getattr(exc, "code", "resume_preflight_failed")
        self._write(self.err, *recovery_lines(exc, run_id=self.run_id, launcher=self.launcher, state_dir=self.state_dir,
                                              header=header, stored_program=stored_program))

    def resumable(self, exit_code: int) -> bool:
        """Whether `resume` continues: not after a refusal, whose recovery lines say what does."""
        if self.error_code is None:
            return True
        return exit_code == 1 and self.error_code not in REFUSAL_CODES

    def run_failed(self) -> None:
        self._announce_now()
        self._write(self.err, f"resume  {self.launcher} resume {self.run_id}{state_dir_flag(self.state_dir)}")

    def waiting(self, identities: Iterable[str]) -> None:
        self._announce_now()
        command = f"{self.launcher} input get {self.run_id}{state_dir_flag(self.state_dir)}"
        self._write(self.err, *(f"waiting {identity}  {command}" for identity in identities))

    def result(self, value: Any) -> None:
        self._write(self.out, json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
