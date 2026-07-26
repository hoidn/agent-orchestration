"""Run the Workflow Lisp language server over frame-clean stdio."""

from __future__ import annotations

import sys

from .server import create_server


def main() -> None:
    """Reserve the original binary stdout exclusively for protocol frames."""

    transport_stdin = sys.stdin.buffer
    transport_stdout = sys.stdout.buffer
    ordinary_stdout = sys.stdout
    try:
        sys.stdout = sys.stderr
        create_server().start_io(
            stdin=transport_stdin,
            stdout=transport_stdout,
        )
    finally:
        sys.stdout = ordinary_stdout


if __name__ == "__main__":
    main()
