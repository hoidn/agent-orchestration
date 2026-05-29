#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: emit_cycle_guard_summary.py <terminal_status> <guard_cycles>")
    terminal_status = sys.argv[1]
    guard_cycles = int(sys.argv[2])
    payload = {"terminal_status": terminal_status, "guard_cycles": guard_cycles}
    bundle_path_raw = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
    if bundle_path_raw:
        bundle_path = Path(bundle_path_raw)
        if bundle_path.is_absolute() or ".." in bundle_path.parts:
            raise SystemExit("unsafe ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    sys.stdout.write(json.dumps(payload) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
