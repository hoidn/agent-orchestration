"""The blind scoring pool (design D4, D6, D8; rulings R18, R20, R21) and its integrity check.

pool(task, criterion, out, judges, runs) builds P = out: P/clones/<id>/ applied-patch clones (what the
judges read; P/clones is traversable but not listable), P/judges/<16 hex>/ one working and state
directory per judge, and P/records/ with mapping.json (read by summarize.py and verify_pool only),
patches/<id>.diff, score-inputs-<judge>.json and score-<judge>.sh. P and P/judges stay listable: the
runtime opens every ancestor of a judge's working and state directory with O_RDONLY.
verify_pool(out) restores any clone whose HEAD or patch a judge changed. Standard library only.
"""

import random
import re
import secrets
import shlex
import sys
from pathlib import Path

try:
    from .repos import HIDDEN_DIR, build_candidate, dump, git, guard, load, patch_of, sha256_file
except ImportError:
    from repos import HIDDEN_DIR, build_candidate, dump, git, guard, load, patch_of, sha256_file

STRIPPED = ("docs/design/", "artifacts/")  # D8: removed from every pooled patch
ROW_KEYS = ("arm", "outcome", "failure", "calls", "wall_clock_sec", "selected", "variant")  # per run, in mapping.json


def sections(patch):
    """Split a git patch (bytes) into [((a path, b path), section)], one per file."""
    found = []
    for part in re.split(rb"(?m)^(?=diff --git )", patch):
        header = re.match(rb'diff --git "?a/(.*?)"? "?b/(.*?)"?\n', part)
        if part:
            found.append((header.groups() if header else (), part))
    return found


def strip(patch):
    """Remove D8 paths; return (kept patch, removed paths)."""
    kept, removed = [], []
    for paths, part in sections(patch):
        names = [p.decode(errors="replace") for p in paths]
        if any(n.startswith(STRIPPED) for n in names):
            removed.append(names[-1])
        else:
            kept.append(part)
    return b"".join(kept), removed


def compose(usable):
    """Batches per D4: one per best_of_n run (control patches spread over them), two stage batches for
    reviewed_change (a run with identical first and final patches pooled once), one batch for the rest.
    `usable` maps arm -> [(records path, record)]; a member is (records path, record, labels sharing one clone)."""
    rng = random.SystemRandom()
    controls = [(path, rec, ["final"]) for path, rec in usable.get("direct_task", [])]
    rng.shuffle(controls)
    batches = [[(path, rec, [Path(c).name]) for c in rec["candidates"]] for path, rec in usable.get("best_of_n", [])]
    for k, control in enumerate(controls if batches else []):
        batches[k % len(batches)].append(control)
    rest = [(path, rec, ["final"]) for path, rec in usable.get("design_review_execute", [])]
    rest += [] if batches else controls
    return batches + stage_batches(usable.get("reviewed_change", []), rng) + ([rest] if rest else [])


def stage_batches(runs, rng):
    stages = [[], []]
    for path, rec in runs:
        first, final = rng.sample((0, 1), 2)
        if strip(patch_bytes(path, rec, "first"))[0] == strip(patch_bytes(path, rec, "final"))[0]:
            stages[first].append((path, rec, ["first", "final"]))
        else:
            stages[first].append((path, rec, ["first"]))
            stages[final].append((path, rec, ["final"]))
    return [s for s in stages if s]


def patch_bytes(records, record, label):
    return (Path(records) / record["patches"][label]).read_bytes()


def add_clone(out, task, ref, patch, entry):
    """Build one applied-patch clone under a random id; record its patch; return (id, mapping entry)."""
    cid = secrets.token_hex(4)
    clone = out / "clones" / cid
    if build_candidate(ref["runtime"], ref["base"], task / "seed", clone) != ref["compare_base"]:
        raise SystemExit(f"{clone}: seeded commit differs from the runs' {ref['compare_base']}")
    kept, entry["stripped"] = strip(patch)
    if kept:
        git(clone, "apply", "--binary", "-", stdin=kept)
    (out / "records" / "patches" / f"{cid}.diff").write_bytes(patch_of(clone, ref["compare_base"]))
    return cid, entry


def exclusion(path, scan):
    """Why the run is excluded (a contaminated verdict), or None; refuse hits without a verdict (R20)."""
    hits, verdict = scan["hits"], scan["verdict"]
    if hits and verdict is None:
        raise SystemExit(f"{path} has {len(hits)} scan hits and no verdict: "
                         f"prepare.py scan --run {path} --verdict contaminated|cleared --reason TEXT")
    return f"contaminated: {verdict['reason']}" if verdict and verdict["verdict"] == "contaminated" else None


def pool_runs(records):
    """Mapping rows for every run and the usable runs per arm; refuse a run not collected or not scanned."""
    rows, usable = {}, {}
    for path, rec in records.items():
        if "outcome" not in rec or "scan" not in rec:
            raise SystemExit(f"{path} has not been {'collected' if 'outcome' not in rec else 'scanned'}")
        excluded = exclusion(path, rec["scan"])
        rows[path] = {k: rec[k] for k in ROW_KEYS} | {
            "scan_hits": len(rec["scan"]["hits"]), "verdict": rec["scan"]["verdict"], "excluded": excluded}
        if rec["outcome"] == "completed" and not excluded:
            usable.setdefault(rec["arm"], []).append((path, rec))
    return rows, usable


def build_batches(out, task, ref, batches):
    clones, members = {}, []
    anchors = sorted((task / "anchors").glob("*.diff"))
    for batch in batches:
        made = [add_clone(out, task, ref, patch_bytes(path, rec, labels[0]),
                          {"run": path, "arm": rec["arm"], "labels": labels}) for path, rec, labels in batch]
        made += [add_clone(out, task, ref, a.read_bytes(), {"run": None, "arm": "anchor", "labels": [a.stem]})
                 for a in anchors]
        clones.update(made)
        members.append([cid for cid, _ in made])
    return clones, members


def pool(task, criterion, out, judges, runs):
    """Build the blind scoring pool, mapping.json, and one scoring inputs file and command per judge."""
    task, out = task.resolve(), out.resolve()
    records = {str(Path(r).resolve()): load(Path(r) / "record.json") for r in runs}
    ref = next(iter(records.values()))
    if {(r["task"], r["compare_base"]) for r in records.values()} != {(str(task), ref["compare_base"])}:
        raise SystemExit("runs in one pool must share the task and the seeded commit")
    guard(Path(ref["main"]), out)
    rows, usable = pool_runs(records)
    batches = compose(usable)
    if not batches:
        raise SystemExit("no completed, uncontaminated run to pool")
    for directory in (out / "clones", out / "judges", out / "records" / "patches"):
        directory.mkdir(parents=True)
    clones, members = build_batches(out, task, ref, batches)
    default = Path(ref["runtime"]) / "experiments/compare/score.providers.json"
    mapping = {"task": str(task), "criterion_sha256": sha256_file(criterion), "compare_base": ref["compare_base"],
               "judges": {name: {"dir": secrets.token_hex(8), "providers": str(Path(providers or default).resolve())}
                          for name, _, providers in (spec.partition("=") for spec in judges)},
               "runs": rows, "clones": clones, "batches": members}
    dump(out / "records" / "mapping.json", mapping)
    write_score_inputs(out, mapping, (task / "intent.txt").read_text(), Path(ref["runtime"]))
    (out / "clones").chmod(HIDDEN_DIR)
    print(f"# {len(clones)} clones in {len(members)} batches; run the judges one after another, "
          f"each followed by: prepare.py verify-pool --pool {out}")
    return mapping


def write_score_inputs(out, mapping, intent, runtime):
    """Per judge: score.orc inputs with that judge's random clone order, a working and state directory
    of its own, and the command (also in records/score-<judge>.sh)."""
    rng = random.SystemRandom()
    for judge, info in mapping["judges"].items():
        inputs, home = out / "records" / f"score-inputs-{judge}.json", out / "judges" / info["dir"]
        dump(inputs, {"batches": [{"clones": [str(out / "clones" / cid) for cid in rng.sample(ids, len(ids))]}
                                  for ids in mapping["batches"]],
                      "intent": intent, "criterion_sha256": mapping["criterion_sha256"], "judge_model": judge})
        home.mkdir()
        command = f"cd {shlex.quote(str(home))} && env PYTHONPATH={shlex.quote(str(runtime))} " + shlex.join([
            sys.executable, "-P", "-m", "orchestrator", "run", str(runtime / "experiments/compare/score.orc"),
            "--entry-workflow", "score::score", "--source-root", str(runtime / "experiments/compare"),
            "--provider-externs-file", info["providers"], "--input-file", str(inputs),
            "--state-dir", str(home / "state")])
        (out / "records" / f"score-{judge}.sh").write_text(command + "\n")
        print(command)


def changed_paths(recorded, current):
    old, new = (dict((paths[-1] if paths else b"", part) for paths, part in sections(p)) for p in (recorded, current))
    return sorted(p.decode(errors="replace") for p in set(old) | set(new) if old.get(p) != new.get(p))


def verify_pool(out):
    """Restore every clone whose HEAD or patch differs from the one recorded when the pool was built."""
    out = out.resolve()
    mapping = load(out / "records" / "mapping.json")
    base, changed = mapping["compare_base"], 0
    for cid in mapping["clones"]:
        clone, recorded_file = out / "clones" / cid, out / "records" / "patches" / f"{cid}.diff"
        recorded = recorded_file.read_bytes()
        head, current = git(clone, "rev-parse", "HEAD"), patch_of(clone, base)
        if head == base and current == recorded:
            continue
        changed += 1
        print(f"{cid}: HEAD {head[:12]}, changed {', '.join(changed_paths(recorded, current)) or 'nothing'}")
        git(clone, "reset", "-q", "--hard", base)
        git(clone, "clean", "-q", "-f", "-d", "-x")
        if recorded:
            git(clone, "apply", "--binary", str(recorded_file))
        patch_of(clone, base)
    if changed:
        raise SystemExit(f"{changed} clone(s) differed from their recorded patch and were restored")
    print(f"{len(mapping['clones'])} clones match their recorded patches")
