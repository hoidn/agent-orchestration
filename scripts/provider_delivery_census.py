"""Census of provider attempts and their result delivery across run state dirs.

Read-only. For each ``<state-dir>/<run_id>/memo.jsonl`` this pairs ``started``
rows with the ``committed`` or ``failed`` row of the same (identity, attempt),
keeps provider attempts (attempt directory holds ``prompt.txt``), and prints one
line per attempt followed by counts by (site, outcome) and a total.

Usage: python scripts/provider_delivery_census.py --state-dir DIR [...] [--head N]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def delivery_names() -> dict[str, str] | None:
    """Known ``delivery`` part digests, or None when the hash helper moved."""
    try:
        from orchestrator.workflow.run_ref.contracts import canonical_sha256
    except ImportError:
        return None
    return {canonical_sha256(name): name for name in ("legacy", "file/1")}


def delivery_name(parts: dict, names: dict[str, str] | None) -> str:
    digest = parts.get("delivery")
    if digest is None:
        return "legacy"
    if names is None:
        return "unknown"
    return names.get(digest, digest)


def read_memo(path: Path, run_id: str) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"{run_id}: memo.jsonl line {number} malformed ({exc}); skipped", file=sys.stderr)
    return rows


def outcome(end: dict | None) -> str:
    if end is None:
        return "open"
    if end.get("record") == "committed":
        return "committed"
    code = end.get("code")
    return "missing" if code == "provider_result_missing" else str(code)


def run_attempts(run_dir: Path, names: dict[str, str] | None, head: int):
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
            "delivery": delivery_name(row.get("input_parts") or {}, names),
            "stdout": " ".join(text.split())[:head],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state-dir", action="append", required=True, type=Path)
    parser.add_argument("--head", type=int, default=120)
    args = parser.parse_args(argv)
    names = delivery_names()
    counts: Counter[tuple[str, str]] = Counter()
    print("run\tsite\tattempt\toutcome\tdelivery\tstdout_head")
    for state_dir in args.state_dir:
        if not state_dir.is_dir():
            print(f"{state_dir}: not a directory; skipped", file=sys.stderr)
            continue
        for run_dir in sorted(p for p in state_dir.iterdir() if p.is_dir()):
            for item in run_attempts(run_dir, names, args.head):
                counts[(item["site"], item["outcome"])] += 1
                print("\t".join(str(item[key]) for key in
                                ("run", "site", "attempt", "outcome", "delivery", "stdout")))
    print("\nsite\toutcome\tcount")
    for (site, result), count in sorted(counts.items()):
        print(f"{site}\t{result}\t{count}")
    by_outcome = Counter()
    for (_, result), count in counts.items():
        by_outcome[result] += count
    detail = ", ".join(f"{result}={count}" for result, count in sorted(by_outcome.items()))
    print(f"total\t{sum(counts.values())}\t{detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
