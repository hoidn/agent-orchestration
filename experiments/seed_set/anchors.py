"""Zero-spend anchor stability check (coordinator ruling, 2026-11-12): a task is usable only when its reference fix
scores 1.0 and its untouched base below 1.0 on the hidden set, with identical per-test outcomes, in every one of
`REPS` repetitions under the study's own scoring path.

The path is the study's: the pool's clone builder (`pool.build_batches`: random clone ids, random build order, the
seeded base, the anchor patches) and summarize's scorer (`summarize.hidden_acceptance`: a copy of each clone without
`.git`, `hidden/` over it, one pytest per hidden node, each bounded at the study's `host.HIDDEN_TEST_SEC`), each task
in its own process behind `host.guarded` (fresh no-provider stubs, an empty home), as `host.summarize` runs it,
`WIDTH` tasks at a time (the study's four). No model is called.

  python -m experiments.seed_set.anchors --work W [ID ...]   # default: every ladder and smoke package not yet
                                                             # recorded at its current hash and scoring path
                                                             # (resumable)

writes `anchor_stability.json` beside `tasks.jsonl`: per package its sha256, `stable`, the failing test ids per
repetition, the repetition counts, the load average seen and `scoring_path` (`scoring_path_hash()`: the kit's and the
harness's modules the run scored with, the Python version and the pytest version). An entry holds only for the
scoring path it was measured under (coordinator ruling, 2026-11-15): `tiers.verify` and the freeze require a stable
entry, at the current package hash and the current scoring path (the freeze: of the runtime's files), for every
package the study can draw, probe or smoke on, and name each package that lacks one as "not measured", "other scoring
path" or "unstable"; `tiers reject-unstable` rejects a task only on an entry unstable at the current hash and scoring
path, and skips (does not reject on) an entry measured under another.

Limit of the record: it shows stability only under the scoring path it was measured under. An entry written before
that code changed is refused as "other scoring path", and the default run measures it again. The freeze runs the
anchors on the frozen code, so its record carries the frozen code's scoring path.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from experiments.compare import repos
from experiments.seed_set import build_tasks as b, host, ladder

REPS, WIDTH = 3, 4
FILE = "anchor_stability.json"


def scoring_path_files(root=b.ROOT):
    """Every module directly in the kit and the harness under `root`: the files `scoring_path_hash` covers."""
    return [p for d in ("experiments/seed_set", "experiments/compare") for p in (root / d).glob("*.py")]


def scoring_path_hash(root=b.ROOT):
    """sha256 over (repository-relative path, sha256) of `scoring_path_files`, sorted, then this interpreter's
    `sys.version` and the installed pytest's version: the scoring path an anchors record was measured under."""
    # deliberately over-inclusive: any kit module edit invalidates the record; a re-run costs about an hour
    rows = sorted([p.relative_to(root).as_posix(), repos.sha256_file(p)] for p in scoring_path_files(root))
    rows += [["python", sys.version], ["pytest", importlib.metadata.version("pytest")]]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def score(task, out, runtime):
    """One repetition in this process: build the two anchors as a pool does, score them as summarize does;
    {anchor label: failing node ids}."""
    from experiments.compare import pool, summarize
    task, out, runtime = Path(task), Path(out), Path(runtime)
    base = repos.git(runtime, "rev-parse", "--verify", (task / "base_commit").read_text().strip() + "^{commit}")
    with tempfile.TemporaryDirectory() as tmp:
        compare_base = repos.build_candidate(runtime, base, task / "seed", Path(tmp) / "candidate")
    for directory in (out / "clones", out / "records" / "patches"):
        directory.mkdir(parents=True)
    ref = {"runtime": str(runtime), "base": base, "compare_base": compare_base}
    clones, _, _ = pool.build_batches(out, task, ref, [[]], {"reference": None})
    _, failed = summarize.hidden_acceptance(out, {"task": str(task), "clones": clones}, sys.executable,
                                            host.HIDDEN_TEST_SEC)
    return {clones[cid]["labels"][0]: sorted(f) for cid, f in failed.items()}


def check(package, work, runtime=b.ROOT, reps=REPS):
    """`reps` guarded repetitions on one package; its stability entry."""
    runs = []
    for k in range(reps):
        out = Path(work) / f"{package.name}-{k}"
        done, attempts = host.guarded([sys.executable, "-m", "experiments.seed_set.anchors", "--one", str(package),
                                       str(out), str(runtime)])
        shutil.rmtree(out, ignore_errors=True)
        if attempts or done.returncode:
            runs.append({"error": (str(attempts) if attempts else done.stderr[-500:])})
            continue
        runs.append(json.loads(done.stdout.splitlines()[-1]) | {"load": os.getloadavg()[0]})
    return judge(package, runs)


def judge(package, runs):
    """Stable: every repetition scored, the reference passing all, the base failing some, outcomes identical."""
    reference, base = f"{package.name}-upstream", f"{package.name}-base"
    outcomes = [(r.get(reference), r.get(base)) for r in runs]
    stable = all("error" not in r for r in runs) and len(set(map(repr, outcomes))) == 1 and all(
        ref == [] and bool(bad) for ref, bad in outcomes)
    return {"sha256": b.package_hash(package), "stable": stable, "reps": len(runs),
            "reference_failing": sorted({t for r in runs for t in r.get(reference) or []}),
            "runs": runs}


def unstable_tests(entry):
    """The tests that make an entry unstable: those failing on the reference, and those whose outcome on either
    anchor changes across repetitions."""
    runs = [r for r in entry.get("runs", []) if "error" not in r]
    varying = {t for label in {k for r in runs for k in r if k != "load"}
               for t in set().union(*(r.get(label, []) for r in runs)) if any(t not in r.get(label, []) for r in runs)}
    return sorted(set(entry.get("reference_failing", [])) | varying)


def packages(rows):
    """Every package the study can draw, probe or smoke on: the ladder's (both forms) and the smoke's."""
    found = [p["id"] for p in ladder.packages(rows)]
    found += [pid for row in rows if row.get("set") == "smoke" for pid in (row["id"], row.get("withheld_id")) if pid]
    return list(dict.fromkeys(found))


def run(work, ids=None, out=b.HERE, width=WIDTH, root=b.ROOT):
    rows = [json.loads(line) for line in (out / "tasks.jsonl").read_text().splitlines()]
    path = out / FILE
    found = json.loads(path.read_text()) if path.is_file() else {}
    scoring_path = scoring_path_hash(root)
    # resumable: a package already recorded at its current hash and scoring path is not checked again unless named
    ids = ids or [pid for pid in packages(rows) if lacking(found.get(pid), out / "tasks" / pid, scoring_path)
                  in ("not measured", "other scoring path")]
    with ThreadPoolExecutor(width) as pool_:
        for pid, entry in zip(ids, pool_.map(lambda pid: check(out / "tasks" / pid, work), ids)):
            if (now := scoring_path_hash(root)) != scoring_path:  # a kit module was edited while this package ran
                pool_.shutdown(cancel_futures=True)
                raise SystemExit(f"the scoring path changed during the run ({scoring_path} at its start, {now} after "
                                 f"{pid}'s repetitions): no entry written for {pid}; run again on unchanged code")
            found[pid] = entry | {"scoring_path": scoring_path}
            print(pid, "stable" if entry["stable"] else f"UNSTABLE {entry['reference_failing']}",
                  [round(r.get("load", 0), 1) for r in entry["runs"]], flush=True)
            path.write_text(json.dumps(dict(sorted(found.items())), indent=1, sort_keys=True) + "\n")
    return found


def lacking(entry, package, scoring_path):
    """Why `entry` gives `package` no stable anchor ("not measured" at its current hash, "other scoring path",
    "unstable"), or None."""
    if not entry or entry["sha256"] != b.package_hash(package):
        return "not measured"
    if entry.get("scoring_path") != scoring_path:
        return "other scoring path"
    return None if entry["stable"] else "unstable"


def unstable(study_rows, stability, tasks_dir, root=b.ROOT):
    """The usable packages without a stable entry at their current hash and the scoring path of `root`'s files,
    each as "<id> (<why>)"."""
    scoring_path = scoring_path_hash(root)
    return [f"{pid} ({why})" for pid in packages(study_rows)
            if (why := lacking(stability.get(pid), tasks_dir / pid, scoring_path))]


if __name__ == "__main__":
    if sys.argv[1] == "--one":
        print(json.dumps(score(*sys.argv[2:5])))
        sys.exit()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("ids", nargs="*")
    args = parser.parse_args()
    run(args.work.resolve(), args.ids)
