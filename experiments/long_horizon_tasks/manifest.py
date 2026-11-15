"""The long-horizon kit's manifest: the SHA-256 of every file it covers. The manifest's own SHA-256 is the
configuration label of the plan's D7.

Covered: every file under experiments/long_horizon_tasks/ (ladder.json, tasks.json, the scripts, recordings.json, the
fixtures) except the names in NOT_COVERED; the price table the plan's D4 names by hash; and the criterion's test
module, which holds the reader of ladder.json's pattern language (in ladder.py, the launcher's) to the fixtures.
Not covered, and why (NOT_COVERED is also written into the manifest). Outside the repository, and so in no file here:
the allowance inputs and meter readings (the launcher's state; plan D4, D7), the raw recordings (recordings.json
holds their SHA-256), the task packages and images (tasks.json holds their digests), the token. The package code the
launcher reuses is bound by the runtime commit (LH_RUNTIME_COMMIT), not by the label.

Usage (from the repository root):
  python -I experiments/long_horizon_tasks/manifest.py write [--freeze]
      hashes the covered files into manifest.json and prints its SHA-256. With --freeze the manifest is marked
      frozen, which is refused (exit 2, nothing written) while ladder.json is not ready to freeze (freeze_gaps).
      A plain write over a frozen manifest is refused (exit 2): a frozen manifest is rewritten only by --freeze.
  python -I experiments/long_horizon_tasks/manifest.py check
      prints the recorded label and whether it is frozen; exit 1, naming each file, when a covered file changed,
      appeared or went since the manifest was written, or when a frozen manifest's ladder.json is not ready to freeze.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
ROOT = KIT.parents[1]
MANIFEST = KIT / "manifest.json"
EXTERNAL = ("orchestrator/providers/price_table.json", "tests/experiments/test_long_horizon_ladder.py")
NOT_COVERED = {
    "manifest.json": "the manifest itself: its SHA-256 is the label",
    "README.md": "prose that no code reads: a wording fix must not make a new label",
    "RECORDINGS.md": "prose that no code reads: a wording fix must not make a new label",
    "results/": "the readout's output, written after the freeze",
    "__pycache__/": "the interpreter's caches",
}
TYPES = {"array": list, "object": dict, "string": str, "scalar": (str, int)}


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


def _at(doc, field):
    for key in field.split("."):
        doc = doc.get(key) if isinstance(doc, dict) else None
    return doc


def _typed(value, kind):
    """Whether a filled value has its declared type: an empty string, a bool or an unknown type never does."""
    if kind == "sha256":
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    return kind in TYPES and isinstance(value, TYPES[kind]) and not isinstance(value, bool) and value != ""


def freeze_gaps(ladder):
    """Why ladder.json cannot be frozen: a pending entry, a null, or a filled field of the wrong type or no source."""
    gaps = [f"pending: {p['field']}" for p in ladder["pending"]] + [f"null: {n}" for n in nulls(ladder)]
    gaps += [f"filled, not a {e.get('type')}: {e['field']}" for e in ladder["filled"]
             if not _typed(_at(ladder, e["field"]), e.get("type"))]
    return gaps + [f"filled, no source: {e['field']}" for e in ladder["filled"] if not e.get("source")]


def _ladder_gaps():
    return freeze_gaps(json.loads((KIT / "ladder.json").read_text()))


def write(freeze):
    gaps = _ladder_gaps() if freeze else []
    if not freeze and MANIFEST.exists() and json.loads(MANIFEST.read_text())["frozen"]:
        gaps = ["a frozen manifest: rewrite it only with --freeze"]
    if gaps:
        print("manifest.py: not written;", *gaps, sep="\n  ", file=sys.stderr)
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
    gaps = _ladder_gaps() if recorded["frozen"] else []
    for gap in gaps:
        print(f"manifest.py: frozen, but ladder.json has {gap}", file=sys.stderr)
    return 1 if changed or gaps else 0


def main(argv):
    if argv in (["write"], ["write", "--freeze"]):
        return write(freeze=len(argv) == 2)
    if argv == ["check"]:
        return check()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
