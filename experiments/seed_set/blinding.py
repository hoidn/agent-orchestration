"""Blinding checks on what the judges read (coordinator ruling 3, 2026-11-12), for `study.py`.

- `identity_tokens` / `scan_pool` (3b): before any judge call, every pooled candidate patch is scanned for text
  that names its arm: the model ids and the words `haiku` and `sonnet`, the arm names (bare `direct` aside: an
  ordinary word in this code; `direct.orc` and `direct::run` stand for it), the program files and entries, and
  the run's own identifiers (the work and pools roots, the private homes, each pooled run's records directory,
  agents' tree and orchestrator run ids). A token is matched case-insensitively as a whole word in the lines a
  patch adds and in its file headers; a token the task's own reference fix adds is left out, since every arm that
  solves the task writes it. The rule on a hit: the pool is refused before any judge call (a pool incident naming
  the clone, the token and the line); nothing is scrubbed, so judges always read the candidate's own patch.
- `judged_patches` (3c): the sha256 of each clone's patch read from the clone itself just before a judge starts;
  stored with that judge's facts, so the readout binds each rating to the patch that was judged and refuses one
  whose digest differs from the pooled patch (`gates.pool_records`).

Depends on: the pool's `records/mapping.json` and `records/patches/`, the run records' `record.json` and `state/`,
`experiments.compare.repos.patch_of` (git).
"""

import hashlib
import re
from pathlib import Path

from experiments.compare.repos import load, patch_of
from experiments.seed_set import spend

WORDS = ("haiku", "sonnet", "common.orc", ".private-homes")


def identity_tokens(study, arms, runs):
    """The text that would tell a judge which arm or run produced a patch."""
    tokens = {*spend.MODELS, *WORDS, str(study.work), str(study.pools)}
    for name, arm in arms.items():
        tokens |= {arm["source"], arm["entry"]} | ({name} if name != "direct" else set())
    for run in map(Path, runs):
        record = load(run / "record.json")
        tokens |= {str(run), record["tree"], Path(record["tree"]).name}
        tokens |= {path.name for path in (run / "state").glob("*")} if (run / "state").is_dir() else set()
    return sorted(tokens)


def _pattern(token):
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", re.I)


def added(patch):
    """The lines a patch adds, with its file headers."""
    return [line for line in patch.splitlines()
            if line.startswith("diff --git ") or (line.startswith("+") and not line.startswith("+++ /dev/null"))]


def scan_pool(out, task, tokens):
    """[{"clone", "token", "line"}] over the pool's candidate clones (anchors are the task's own patches)."""
    mapping = load(Path(out) / "records" / "mapping.json")
    upstream = "\n".join(added((Path(task) / "anchors" / f"{Path(task).name}-upstream.diff").read_text(
        errors="replace")))
    live = [(token, _pattern(token)) for token in tokens if not _pattern(token).search(upstream)]
    hits = []
    for cid, clone in mapping["clones"].items():
        if clone["arm"] == "anchor":
            continue
        for line in added((Path(out) / "records" / "patches" / f"{cid}.diff").read_text(errors="replace")):
            hits += [{"clone": cid, "token": token, "line": line[:200]} for token, found in live if found.search(line)]
    return hits


def judged_patches(out, mapping):
    """{clone id: sha256 of the clone's patch against the pool's base}, read from the clones."""
    return {cid: hashlib.sha256(patch_of(Path(out) / "clones" / cid, mapping["compare_base"])).hexdigest()
            for cid in mapping["clones"]}
