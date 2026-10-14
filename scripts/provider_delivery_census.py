"""Census of provider attempts and their result delivery across run state dirs.

Read-only. For each ``<state-dir>/<run_id>/memo.jsonl`` this pairs ``started``
rows with the ``committed`` or ``failed`` row of the same (identity, attempt),
keeps provider attempts (attempt directory holds ``prompt.txt``), and prints one
line per attempt followed by counts by (site, delivery, outcome) and a total.

Usage: python scripts/provider_delivery_census.py --state-dir DIR [...] [--head N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

# Same bytes as orchestrator.workflow.run_ref.contracts.canonical_sha256 for a string.
DELIVERY_NAMES = {
    "sha256:" + hashlib.sha256(json.dumps(name).encode("utf-8")).hexdigest(): name
    for name in ("legacy", "file/1")
}


def delivery_name(parts: dict) -> str:
    digest = parts.get("delivery")
    return "legacy" if digest is None else DELIVERY_NAMES.get(digest, digest)


def read_memo(path: Path, run_id: str) -> list[dict]:
    rows = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"{run_id}: memo.jsonl line {number} malformed ({exc}); skipped", file=sys.stderr)
            continue
        if not isinstance(row, dict):
            print(f"{run_id}: memo.jsonl line {number} is not an object; skipped", file=sys.stderr)
            continue
        rows.append(row)
    return rows


def outcome(end: dict | None) -> str:
    if end is None:
        return "open"
    if end.get("record") == "committed":
        return "committed"
    code = end.get("code")
    return "missing" if code == "provider_result_missing" else str(code)


def run_attempts(run_dir: Path, head: int):
    memo = run_dir / "memo.jsonl"
    if not memo.is_file():
        return
    rows = read_memo(memo, run_dir.name)
    ends = {
        (row.get("identity"), row.get("attempt")): row
        for row in rows
        if row.get("record") in ("committed", "failed")
    }
    for row in rows:
        if row.get("record") != "started" or not row.get("result_path"):
            continue
        attempt_dir = run_dir / Path(row["result_path"]).parent
        if not (attempt_dir / "prompt.txt").is_file():
            continue
        stdout = attempt_dir / "stdout.txt"
        text = stdout.read_text(encoding="utf-8", errors="replace") if stdout.is_file() else ""
        yield {
            "run": run_dir.name,
            "site": str(row.get("identity", "")).split(" / ")[-1],
            "attempt": row.get("attempt"),
            "outcome": outcome(ends.get((row.get("identity"), row.get("attempt")))),
            "delivery": delivery_name(row.get("input_parts") or {}),
            "stdout": " ".join(text.split())[:head],
        }


def total_line(counts: Counter[tuple[str, str, str]]) -> str:
    by_delivery: dict[str, Counter[str]] = {}
    for (_, delivery, result), count in counts.items():
        by_delivery.setdefault(delivery, Counter())[result] += count
    parts = [
        f"{delivery}={sum(results.values())} ("
        + ", ".join(f"{result}={n}" for result, n in sorted(results.items())) + ")"
        for delivery, results in sorted(by_delivery.items())
    ]
    return f"total\t{sum(counts.values())}\t" + "; ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state-dir", action="append", required=True, type=Path)
    parser.add_argument("--head", type=int, default=120)
    args = parser.parse_args(argv)
    counts: Counter[tuple[str, str, str]] = Counter()
    print("run\tsite\tattempt\toutcome\tdelivery\tstdout_head")
    for state_dir in args.state_dir:
        if not state_dir.is_dir():
            print(f"{state_dir}: not a directory; skipped", file=sys.stderr)
            continue
        for run_dir in sorted(p for p in state_dir.iterdir() if p.is_dir()):
            for item in run_attempts(run_dir, args.head):
                counts[(item["site"], item["delivery"], item["outcome"])] += 1
                print("\t".join(str(item[key]) for key in
                                ("run", "site", "attempt", "outcome", "delivery", "stdout")))
    print("\nsite\tdelivery\toutcome\tcount")
    for (site, delivery, result), count in sorted(counts.items()):
        print(f"{site}\t{delivery}\t{result}\t{count}")
    print(total_line(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
