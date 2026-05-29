#!/usr/bin/env python3
import json
import sys


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: emit_cycle_guard_summary.py <terminal_status> <guard_cycles>")
    terminal_status = sys.argv[1]
    guard_cycles = int(sys.argv[2])
    sys.stdout.write(json.dumps({"terminal_status": terminal_status, "guard_cycles": guard_cycles}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
