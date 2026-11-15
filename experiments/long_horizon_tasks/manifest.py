"""The long-horizon kit's manifest: the SHA-256 of every file it covers. The manifest's own SHA-256 is the
configuration label of the plan's D7.

Covered: every file under experiments/long_horizon_tasks/ (ladder.json, tasks.json, the scripts, recordings.json, the
fixtures) except the names in NOT_COVERED, and the price table the plan's D4 names by hash.
Not covered, and why (NOT_COVERED is also written into the manifest). Outside the repository, and so in no file here:
the allowance inputs and meter readings (the launcher's state; plan D4, D7), the raw recordings (recordings.json
holds their SHA-256), the task packages and images (tasks.json holds their digests), the token.

Usage (from the repository root):
  python -I experiments/long_horizon_tasks/manifest.py write [--freeze]
      hashes the covered files into manifest.json and prints its SHA-256. With --freeze the manifest is marked
      frozen, which is refused (exit 2, nothing written) while ladder.json's `pending` is non-empty or it holds a null.
  python -I experiments/long_horizon_tasks/manifest.py check
      prints the recorded label and whether it is frozen; exit 1, naming each file, when a covered file changed,
      appeared or went since the manifest was written.
"""

import hashlib
import json
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
ROOT = KIT.parents[1]
MANIFEST = KIT / "manifest.json"
EXTERNAL = ("orchestrator/providers/price_table.json",)
NOT_COVERED = {
    "manifest.json": "the manifest itself: its SHA-256 is the label",
    "README.md": "prose that no code reads: a wording fix must not make a new label",
    "RECORDINGS.md": "prose that no code reads: a wording fix must not make a new label",
    "results/": "the readout's output, written after the freeze",
    "__pycache__/": "the interpreter's caches",
}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _covered(rel):
    return rel.parts[0] not in NOT_COVERED and f"{rel.parts[0]}/" not in NOT_COVERED and "__pycache__" not in rel.parts


def files():
    """Covered path (from the repository root) -> SHA-256."""
    kit = sorted(p for p in KIT.rglob("*") if p.is_file() and _covered(p.relative_to(KIT)))
    return {p.relative_to(ROOT).as_posix(): _sha(p) for p in kit} | {rel: _sha(ROOT / rel) for rel in EXTERNAL}


def nulls(obj, path=""):
    """The path of every null in a JSON value."""
    if obj is None:
        yield path
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from nulls(value, f"{path}.{key}" if path else key)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from nulls(value, f"{path}[{index}]")


def write(freeze):
    if freeze:
        ladder = json.loads((KIT / "ladder.json").read_text())
        gaps = [f"pending: {p['field']}" for p in ladder["pending"]] + [f"null: {n}" for n in nulls(ladder)]
        if gaps:
            print("manifest.py: not frozen; ladder.json still has", *gaps, sep="\n  ", file=sys.stderr)
            return 2
    MANIFEST.write_text(json.dumps({"frozen": freeze, "not_covered": NOT_COVERED, "files": files()}, indent=1) + "\n")
    print(_sha(MANIFEST))
    return 0


def check():
    recorded, now = json.loads(MANIFEST.read_text()), files()
    changed = sorted(path for path in recorded["files"].keys() | now.keys()
                     if recorded["files"].get(path) != now.get(path))
    print(_sha(MANIFEST), "frozen" if recorded["frozen"] else "not frozen")
    for path in changed:
        state = "new" if path not in recorded["files"] else "gone" if path not in now else "changed"
        print(f"manifest.py: {state}: {path}", file=sys.stderr)
    return 1 if changed else 0


def main(argv):
    if argv in (["write"], ["write", "--freeze"]):
        return write(freeze=len(argv) == 2)
    if argv == ["check"]:
        return check()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
