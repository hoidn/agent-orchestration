"""Comparison harness: candidates, run commands, collection, adjudicated contamination scan, scoring pool.

  prepare.py run --task T --arm A --root W --runtime RT [--candidates N] [--set NAME=VALUE ...]
  prepare.py collect --run R
  prepare.py scan --run R --hash SOLUTION_COMMIT
  prepare.py scan --run R --verdict contaminated|cleared --reason TEXT
  prepare.py pool --task T --criterion C --out P --judge MODEL[=PROVIDERS_JSON] [--judge ...] R [R ...]
  prepare.py verify-pool --pool P

`run` creates the records directory R = W/records/<arm>/run-<k>/ (record.json, inputs.json,
command.sh, resume.sh, calls/<n>/ from the shims, state/ for the orchestrator, collected/<label>.diff)
and the agents' tree W/agents/<16 hex>/ (cand-<k>/ and tmp/); W/agents is traversable but not
listable. Neither W nor the runtime may lie under the main checkout's path prefix. `collect` adds the
outcome, call count, wall clock and patches to record.json; `scan` adds the hits and the controller's
verdict. `pool` creates P, P/clones/<id>/ (what judges read) and P/judges/<16 hex>/ (one working and
state directory per judge), none of them listable, and P/records/ (mapping.json, patches/<id>.diff,
score-inputs-<judge>.json, score-<judge>.sh, later results.json and results.md).
Design: docs/design/orc_effectiveness_comparison_harness.md. Standard library only; needs git on PATH.
"""

import argparse
import json
import shlex
import shutil
import sys
import time
from pathlib import Path

try:
    from . import pool as pooling, scan as contamination  # imported as experiments.compare.prepare
    from .repos import build_candidate, dump, git, guard, hidden_child, load, main_checkout, sha256_file
except ImportError:  # run as a script
    import pool as pooling
    import scan as contamination
    from repos import build_candidate, dump, git, guard, hidden_child, load, main_checkout, sha256_file

# arm: (source, entry workflow, source root, providers file, typed inputs); paths in the runtime checkout.
ARMS = {
    "best_of_n": ("experiments/orc_vs_single_call/workflows/best_of_n.orc", "best_of_n::best-of-n",
                  "experiments/orc_vs_single_call/workflows",
                  "experiments/orc_vs_single_call/workflows/best_of_n.providers.json",
                  ("task", "intent", "repos")),
    "reviewed_change": ("experiments/orc_vs_single_call/workflows/reviewed_change.orc",
                        "reviewed_change::reviewed-change", "experiments/orc_vs_single_call/workflows",
                        "experiments/orc_vs_single_call/workflows/reviewed_change.providers.json",
                        ("task", "intent", "repo")),
    "design_review_execute": ("workflows/examples/design_review_execute.orc", "design_review_execute::run",
                              "workflows/examples", "experiments/compare/providers/design_review_execute.json",
                              ("task", "planner_model", "reviewer_model")),
    "direct_task": ("experiments/compare/control/direct_task.orc", "control/direct_task::direct-task",
                    "experiments/compare", "experiments/compare/control/direct_task.providers.json",
                    ("task", "model", "effort")),
}


def next_run_dir(arm_dir):
    k = 1
    while True:
        try:
            (arm_dir / f"run-{k}").mkdir(parents=True)
            return arm_dir / f"run-{k}"
        except FileExistsError:
            k += 1


def arm_inputs(task, arm, candidates, sets):
    fields = ARMS[arm][4]
    extra = dict(item.split("=", 1) for item in sets)
    values = {"task": (task / "task.txt").read_text(), "intent": (task / "intent.txt").read_text(),
              "repos": [str(c) for c in candidates], "repo": str(candidates[0]), **extra}
    missing, unknown = [f for f in fields if f not in values], sorted(set(extra) - set(fields))
    if missing or unknown:
        raise SystemExit(f"{arm} takes {', '.join(fields)}: missing {missing}, not taken {unknown}")
    return {f: values[f] for f in fields}


def orchestrator_commands(arm, runtime, records, cwd, env):
    """The run command and the resume script, both with the shims first on PATH and state under records."""
    source, entry, source_root, providers, _ = ARMS[arm]
    prefix = (f"cd {shlex.quote(str(cwd))} && env "
              + " ".join(f"{k}={shlex.quote(str(v))}" for k, v in {"PYTHONPATH": runtime, **env}.items())
              + f' PATH={shlex.quote(str(runtime / "experiments/compare/shim"))}:"$PATH" ')
    python = [sys.executable, "-P", "-m", "orchestrator"]  # -P: a candidate's orchestrator/ must not shadow it
    state = ["--state-dir", str(records / "state")]
    run = shlex.join([*python, "run", str(runtime / source), "--entry-workflow", entry,
                      "--source-root", str(runtime / source_root), "--provider-externs-file", str(runtime / providers),
                      "--input-file", str(records / "inputs.json"), *state])
    return prefix + run, prefix + shlex.join([*python, "resume"]) + ' "$1" ' + shlex.join(state)


def run_arm(task, arm, root, runtime, candidates=None, sets=()):
    """Build the run's agents' tree and records directory, print the command; return the records directory."""
    count = candidates or (4 if arm == "best_of_n" else 1)
    if arm != "best_of_n" and count != 1:
        raise SystemExit(f"{arm} works in a single candidate, not {count}")
    task, runtime, root = task.resolve(), runtime.resolve(), root.resolve()
    main = main_checkout(runtime)
    guard(main, root, runtime)
    base = git(runtime, "rev-parse", "--verify", (task / "base_commit").read_text().strip() + "^{commit}")
    arm_inputs(task, arm, [Path("/")], sets)  # refuse bad --set values before building anything
    records, tree = next_run_dir(root / "records" / arm), hidden_child(root / "agents")
    cands = [tree / f"cand-{k}" for k in range(1, count + 1)]
    seeded = {build_candidate(runtime, base, task / "seed", cand) for cand in cands}
    if len(seeded) != 1:
        raise SystemExit(f"candidates disagree on the seeded commit: {sorted(seeded)}")
    compare_base = seeded.pop()
    (tree / "tmp").mkdir()
    dump(records / "inputs.json", arm_inputs(task, arm, cands, sets))
    cwd = tree if arm == "best_of_n" else cands[0]
    command, resume = orchestrator_commands(arm, runtime, records, cwd, {
        "COMPARE_ROOT": records, "COMPARE_TREE": tree, "COMPARE_BASE": compare_base, "TMPDIR": tree / "tmp"})
    (records / "command.sh").write_text(command + "\n")
    (records / "resume.sh").write_text(resume + "\n")
    dump(records / "record.json", {
        "arm": arm, "task": str(task), "runtime": str(runtime), "main": str(main), "base": base,
        "compare_base": compare_base, "records": str(records), "tree": str(tree),
        "candidates": [str(c) for c in cands], "cwd": str(cwd), "command": command, "created_at": time.time(),
    })
    print(f"{command}\n# resume after a stop: bash {records / 'resume.sh'} <run_id>")
    return records


def read_memo(memo):
    return [json.loads(line) for line in memo.read_text().split("\n")[:-1]]  # a final unterminated line is unwritten


def paired_calls(records, rows):
    """Map (identity, attempt) of each provider start to calls/<n>/, the n-th start to the n-th call."""
    starts = [r for r in rows if r["record"] == "started" and "prompt" in r["input_parts"]]
    calls = sorted((records / "calls").glob("*"), key=lambda p: int(p.name))
    if len(starts) != len(calls):
        raise SystemExit(f"{records}: {len(starts)} provider starts in the memo but {len(calls)} call directories "
                         "(the shim was not first on PATH, or a provider never launched)")
    for row, call in zip(starts, calls):
        if "sha256:" + sha256_file(call / "prompt.txt") != row["input_parts"]["prompt"]:
            raise SystemExit(f"{call}: prompt differs from the memo's start {row['identity']} attempt {row['attempt']}")
    return {(r["identity"], r["attempt"]): call for r, call in zip(starts, calls)}


def comparator_patches(arm, committed, names):
    """label -> (call dir, candidate name): what the arm's comparator needs (design §Flow of one run)."""
    if arm == "best_of_n":
        return {name: (committed[k], name) for k, name in enumerate(names)}
    if arm == "reviewed_change":
        return {"first": (committed[0], names[0]), "final": (committed[-1], names[0])}
    return {"final": (committed[-1], names[0])}


def outcome_of(record, terminal, names):
    """outcome, failure, best_of_n's selected candidate and reviewed_change's variant from the terminal row."""
    out = {"outcome": terminal["outcome"], "failure": None, "selected": None, "variant": None}
    if terminal["outcome"] != "completed":
        return out | {"failure": {"code": terminal.get("code"), "message": terminal.get("message")}}
    value = terminal["value"]
    if record["arm"] == "reviewed_change":
        out["variant"] = value["variant"]
    if record["arm"] == "best_of_n":
        out["selected"] = next((n for n, c in zip(names, record["candidates"]) if value["winner"] in (c, n)), None)
        if out["selected"] is None:
            out |= {"outcome": "failed", "failure": {"code": "winner_unmatched", "message": value["winner"]}}
    return out


def finished_memo(records):
    """The run's one orchestrator memo under records/state and its rows; it must end in a terminal row."""
    memos = sorted((records / "state").glob("*/memo.jsonl"))
    if len(memos) != 1:
        raise SystemExit(f"{records}: expected one orchestrator run under state/, found {len(memos)}")
    rows = read_memo(memos[0])
    if not rows or rows[-1]["record"] != "terminal":
        raise SystemExit(f"{memos[0]}: no terminal record; finish or resume the run first")
    return memos[0], rows


def copy_patches(records, picks):
    (records / "collected").mkdir(exist_ok=True)
    for label, (call, name) in picks.items():
        patch = call / f"patch-{name}.diff"
        if not patch.is_file():
            raise SystemExit(f"{patch} is missing: the run is invalid (shim not first on PATH?)")
        shutil.copyfile(patch, records / "collected" / f"{label}.diff")
    return {label: f"collected/{label}.diff" for label in picks}


def collect(records):
    """Pair the memo's provider effects with call directories and copy the comparator's patches."""
    records = records.resolve()
    record = load(records / "record.json")
    memo, rows = finished_memo(records)
    calls = paired_calls(records, rows)
    committed = [calls[(r["identity"], r["attempt"])] for r in rows
                 if r["record"] == "committed" and r["effect_class"] == "provider"]
    names = [Path(c).name for c in record["candidates"]]
    first_start = min((r["time"] for r in rows if r["record"] == "started"), default=memo.stat().st_mtime)
    record.update(outcome_of(record, rows[-1], names), patches={}, calls=len(calls),
                  wall_clock_sec=memo.stat().st_mtime - first_start)  # until the memo's last write
    if record["outcome"] == "completed":
        record["patches"] = copy_patches(records, comparator_patches(record["arm"], committed, names))
    dump(records / "record.json", record)
    return record


def scan(records, solution, home=None):
    """Record every contamination hit of the run (file, line, pattern, excerpt); any earlier verdict is dropped."""
    records = records.resolve()
    record = load(records / "record.json")
    hits = contamination.find_hits(records, record["tree"], record["main"], record["runtime"], solution,
                                   record["created_at"], home or Path.home())
    record["scan"] = {"solution": solution, "hits": hits, "verdict": None}
    dump(records / "record.json", record)
    for hit in hits:
        print(f"{hit['file']}:{hit['line']}: {hit['pattern']}: {hit['text']}")
    return hits


def adjudicate(records, verdict, reason):
    """Record the controller's verdict on a scanned run: contaminated (excluded from the pool) or cleared."""
    record = load(records / "record.json")
    if "scan" not in record:
        raise SystemExit(f"{records} has not been scanned")
    record["scan"]["verdict"] = {"verdict": verdict, "reason": reason, "hits": len(record["scan"]["hits"])}
    dump(records / "record.json", record)


def parser():
    top = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = top.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    for name in ("--task", "--root", "--runtime"):
        run.add_argument(name, type=Path, required=True)
    run.add_argument("--arm", choices=ARMS, required=True)
    run.add_argument("--candidates", type=int)
    run.add_argument("--set", action="append", default=[], metavar="NAME=VALUE", help="other typed input")
    sub.add_parser("collect").add_argument("--run", type=Path, required=True, help="records directory")
    scan_cmd = sub.add_parser("scan")
    scan_cmd.add_argument("--run", type=Path, required=True, help="records directory")
    action = scan_cmd.add_mutually_exclusive_group(required=True)
    action.add_argument("--hash", help="the solution commit: record every hit")
    action.add_argument("--verdict", choices=("contaminated", "cleared"), help="record the controller's verdict")
    scan_cmd.add_argument("--reason", help="why, with --verdict")
    pool_cmd = sub.add_parser("pool")
    for name in ("--task", "--criterion", "--out"):
        pool_cmd.add_argument(name, type=Path, required=True)
    pool_cmd.add_argument("--judge", action="append", required=True, metavar="MODEL[=PROVIDERS_JSON]")
    pool_cmd.add_argument("runs", nargs="+", type=Path, help="records directories")
    sub.add_parser("verify-pool").add_argument("--pool", type=Path, required=True)
    return top


def main(argv=None):
    a = parser().parse_args(argv)
    if a.command == "run":
        run_arm(a.task, a.arm, a.root, a.runtime, a.candidates, a.set)
    elif a.command == "collect":
        print(json.dumps(collect(a.run), indent=2))
    elif a.command == "scan" and a.verdict:
        if not a.reason:
            raise SystemExit("--verdict needs --reason")
        adjudicate(a.run, a.verdict, a.reason)
    elif a.command == "scan":
        print(f"{len(scan(a.run, a.hash))} hits; record a verdict with --verdict when there are any")
    elif a.command == "pool":
        pooling.pool(a.task, a.criterion, a.out, a.judge, a.runs)
    else:
        pooling.verify_pool(a.pool)


if __name__ == "__main__":
    main()
