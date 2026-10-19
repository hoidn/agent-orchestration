"""Comparison harness: candidates, run commands, collection, adjudicated contamination scan, scoring pool.

  prepare.py run --task T --arm A --root W --runtime RT [--candidates N] [--set NAME=VALUE ...] [--apply PATCH]
  prepare.py collect --run R
  prepare.py scan --run R --hash SOLUTION_COMMIT [--root NAME=PATH ...]
  prepare.py scan --run R --verdict contaminated|cleared --reason TEXT
  prepare.py scan --pool P --judge MODEL --hash SOLUTION_COMMIT   (and --verdict ... --reason ...)
  prepare.py pool --task T --criterion C --out P --judge MODEL[=PROVIDERS_JSON] [--judge ...] R [R ...]
  prepare.py verify-pool --pool P

`run` creates the records directory R = W/records/<arm>/run-<k>/ (record.json, inputs.json,
command.sh, resume.sh, calls/<n>/ from the shims, collected/<label>.diff) and the agents' tree
W/agents/<16 hex>/ (cand-<k>/ and tmp/). The orchestrator keeps the run's state in its default root
<cwd>/.orchestrate/runs (cwd: cand-1), so the result path each provider prompt names lies inside the
agent's workspace (R34; ignored by the task bases' .gitignore). best_of_n's cwd is the tree, its state
is <tree>/.orchestrate/best-of-n-runs, linked from every candidate's .orchestrate/ (R37). review_once
reviews a given patch (--apply, a collected R/collected/final.diff), applied uncommitted to its candidate.
Neither W nor the runtime may lie under the main checkout's path prefix, and `run` and `pool` refuse a
runtime with uncommitted changes to tracked files; record.json and mapping.json name its runtime_commit.
`collect` adds the outcome, call count, wall clock and patches to record.json (for review_once also the
review's blocker count and whether the reviewer changed the candidate; a generic-command run's from the
terminal.json its command writes in its one run directory under the state root); `scan` adds the hits and the
controller's verdict. `pool` creates P/clones/<id>/ (what judges read; P/clones is not listable),
P/judges/<16 hex>/ (one working and state directory per judge) and P/records/ (mapping.json,
patches/<id>.diff, score-inputs-<judge>.json, score-<judge>.sh, resume-<judge>.sh, judges/<judge>/
with the judge's calls and scan.json, later results.json and results.md).
Design: docs/design/orc_effectiveness_comparison_harness.md. Standard library only; needs git on PATH.
"""

import argparse
import json
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, replace
from pathlib import Path

try:
    from . import pool as pooling, scan as contamination  # imported as experiments.compare.prepare
    from .repos import (
        build_candidate, dump, git, guard, load,
        main_checkout, random_child, runtime_commit, sha256_file, shim_commands, shim_prefix, visible_in_sandbox,
    )
except ImportError:  # run as a script
    import pool as pooling
    import scan as contamination
    from repos import (
        build_candidate, dump, git, guard, load,
        main_checkout, random_child, runtime_commit, sha256_file, shim_commands, shim_prefix, visible_in_sandbox,
    )

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
    "review_once": ("experiments/compare/control/review_once.orc", "control/review_once::review-once",
                    "experiments/compare", "experiments/compare/control/review_once.providers.json",
                    ("repo", "intent", "account", "replies")),
}

# review_once's fixed inputs, frozen in the calibration criterion
REVIEW_ONCE_ACCOUNT = "No account was provided."
REVIEW_ONCE_REPLIES = "none"

# best_of_n's state directory, also linked from every candidate's .orchestrate/ so the workspace-relative
# result path resolves from the tree and from cand-k alike; an agent's own runs in cand-k stay in its runs/.
BEST_OF_N_STATE = "best-of-n-runs"


@dataclass(frozen=True)
class ArmSpec:
    """What an arm runs: an `.orc` source with its entry, source root, providers, typed input fields and
    optional command boundaries and state directory; or, with `command`, a generic command run behind the
    shims with R/inputs.json as its single argument. A spec may name a candidate root outside the runtime."""
    source: Path
    entry: str
    source_root: Path
    providers: Path
    inputs: tuple[str, ...]
    command_boundaries: Path | None = None
    state_dir: Path | None = None
    command: tuple[str, ...] | None = None


def arm_spec(arm, runtime):
    """The ARMS entry `arm` as a spec with paths in the runtime checkout."""
    source, entry, source_root, providers, inputs = ARMS[arm]
    return ArmSpec(runtime / source, entry, runtime / source_root, runtime / providers, inputs)


def resolved(spec):
    """The spec with absolute paths."""
    paths = {name: getattr(spec, name) and Path(getattr(spec, name)).resolve()
             for name in ("source", "source_root", "providers", "command_boundaries", "state_dir")}
    return replace(spec, **paths)


def refuse_paths(main, root, runtime, spec):
    """The runtime and the spec's files (a candidate root among them) outside the main checkout's prefix
    and the work root; the work root and the spec's state directory (agents write results there) outside
    the main checkout's prefix and visible in the shims' sandbox."""
    files = [p for p in (spec.source, spec.source_root, spec.providers, spec.command_boundaries) if p]
    state = [spec.state_dir] if spec.state_dir else []
    guard(main, root, runtime, *files, *state)
    if str(runtime).startswith(f"{root}/"):
        raise SystemExit(f"the runtime {runtime} lies inside the work root {root}, where agents work")
    for path in files:
        if str(path).startswith(f"{root}/"):
            raise SystemExit(f"the arm's {path} lies inside the work root {root}, where agents work")
    visible_in_sandbox(root, *state)


def next_run_dir(arm_dir):
    k = 1
    while True:
        try:
            (arm_dir / f"run-{k}").mkdir(parents=True)
            return arm_dir / f"run-{k}"
        except FileExistsError:
            k += 1


def arm_inputs(task, arm, candidates, sets, fields=None):
    fields = fields if fields is not None else ARMS[arm][4]
    extra = dict(item.split("=", 1) for item in sets)
    if arm == "review_once" and {"account", "replies"} & set(extra):
        raise SystemExit("review_once's account and replies are frozen by the calibration criterion; do not --set them")
    values = {"task": (task / "task.txt").read_text(), "intent": (task / "intent.txt").read_text(),
              "repos": [str(c) for c in candidates], "repo": str(candidates[0]),
              "account": REVIEW_ONCE_ACCOUNT, "replies": REVIEW_ONCE_REPLIES, **extra}
    missing, unknown = [f for f in fields if f not in values], sorted(set(extra) - set(fields))
    if missing or unknown:
        raise SystemExit(f"{arm} takes {', '.join(fields)}: missing {missing}, not taken {unknown}")
    return {f: values[f] for f in fields}


def require_ignored_state(cands):
    """Run state lives in the working directory; refuse candidates whose patch it would enter (R34)."""
    for cand in cands:
        if subprocess.run(["git", "-C", str(cand), "check-ignore", "-q", ".orchestrate/x"]).returncode:
            raise SystemExit(f"{cand} does not ignore .orchestrate/: run state would enter its patch; "
                             "seed a .gitignore")


def link_best_of_n_state(tree, cands):
    """best_of_n's state directory under the tree, linked from every candidate's .orchestrate/: candidates
    work in cand-k and resolve the tree-relative result path there (R37)."""
    for cand in cands:
        (cand / ".orchestrate").mkdir()
        (cand / ".orchestrate" / BEST_OF_N_STATE).symlink_to(Path("..", "..", ".orchestrate", BEST_OF_N_STATE))
    return tree / ".orchestrate" / BEST_OF_N_STATE


def patch_to_review(arm, apply):
    """review_once's --apply patch as an absolute path; refuse one for any other arm, and none for review_once."""
    if (arm == "review_once") != (apply is not None):
        raise SystemExit("review_once takes --apply <patch>, and no other arm does")
    return apply and Path(apply).resolve()


def apply_patch(records, tree, cand, patch):
    """Apply review_once's patch, unstripped and uncommitted, to its seeded candidate; return record.json's
    `applied` entry (the patch's path and hash), or nothing without a patch. A patch that does not apply
    leaves no run behind."""
    if not patch:
        return {}
    done = subprocess.run(["git", "-C", str(cand), "apply", "--binary", str(patch)], capture_output=True, text=True)
    if done.returncode:
        shutil.rmtree(tree)
        records.rmdir()
        raise SystemExit(f"{patch} does not apply to the seeded candidate: {done.stderr.strip()}")
    return {"applied": {"path": str(patch), "sha256": sha256_file(patch)}}


def candidate_count(arm, candidates, spec):
    """How many candidates the run works in; refuse a spec under a fixed arm's name, or several candidates for an
    arm that works in one."""
    if spec and arm in ARMS:
        raise SystemExit(f"{arm} names a fixed arm; run a spec under another name")
    count = candidates or (4 if arm == "best_of_n" else 1)
    if arm != "best_of_n" and count != 1:
        raise SystemExit(f"{arm} works in a single candidate, not {count}")
    return count


def write_commands(records, cwd, state, runtime, env, spec):
    """Write R/command.sh (and R/resume.sh for an .orc spec) run from `cwd` behind the shims; return the command."""
    if spec.command:  # nothing to resume: no resume.sh
        command = shim_prefix(cwd, runtime, env) + shlex.join([*spec.command, str(records / "inputs.json")])
    else:
        command, resume = shim_commands(
            cwd, runtime, env,
            [str(spec.source), "--entry-workflow", spec.entry, "--source-root", str(spec.source_root),
             "--provider-externs-file", str(spec.providers), "--input-file", str(records / "inputs.json")],
            state, spec.command_boundaries)
        (records / "resume.sh").write_text(resume + "\n")
    (records / "command.sh").write_text(command + "\n")
    return command


def run_arm(task, arm, root, runtime, candidates=None, sets=(), apply=None, spec=None):
    """Build the run's agents' tree and records directory, print the command; return the records directory.
    `spec` replaces the ARMS lookup (`arm` then only names W/records/<arm>/); its paths face the runtime's
    guards. A spec takes a name outside ARMS, whose special cases (best_of_n, review_once) it would meet."""
    count = candidate_count(arm, candidates, spec)
    patch = patch_to_review(arm, apply)
    task, runtime, root = task.resolve(), runtime.resolve(), root.resolve()
    spec = resolved(spec) if spec else arm_spec(arm, runtime)
    main = main_checkout(runtime)
    refuse_paths(main, root, runtime, spec)
    commit = runtime_commit(runtime)
    base = git(runtime, "rev-parse", "--verify", (task / "base_commit").read_text().strip() + "^{commit}")
    arm_inputs(task, arm, [Path("/")], sets, spec.inputs)  # refuse bad --set values before building anything
    records, tree = next_run_dir(root / "records" / arm), random_child(root / "agents")
    cands = [tree / f"cand-{k}" for k in range(1, count + 1)]
    seeded = {build_candidate(runtime, base, task / "seed", cand) for cand in cands}
    if len(seeded) != 1:
        raise SystemExit(f"candidates disagree on the seeded commit: {sorted(seeded)}")
    compare_base = seeded.pop()
    require_ignored_state(cands)
    applied = apply_patch(records, tree, cands[0], patch)
    (tree / "tmp").mkdir()
    dump(records / "inputs.json", arm_inputs(task, arm, cands, sets, spec.inputs))
    cwd, state = (tree, link_best_of_n_state(tree, cands)) if arm == "best_of_n" else (cands[0], spec.state_dir)
    env = {"COMPARE_ROOT": records, "COMPARE_TREE": tree, "COMPARE_BASE": compare_base, "TMPDIR": tree / "tmp"}
    command = write_commands(records, cwd, state, runtime, env, spec)
    dump(records / "record.json", {
        "arm": arm, "arm_kind": "generic-command" if spec.command else "orc",
        "task": str(task), "runtime": str(runtime), "runtime_commit": commit, "main": str(main),
        "base": base, "compare_base": compare_base, "records": str(records), "tree": str(tree),
        "candidates": [str(c) for c in cands], "cwd": str(cwd),
        "state_root": str(state or cwd / ".orchestrate" / "runs"), "command": command, "created_at": time.time(),
        **applied,
    })
    print(command if spec.command else f"{command}\n# resume after a stop: bash {records / 'resume.sh'} <run_id>")
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


def blockers(review):
    """Review blockers of one review_once call (calibration criterion): REQUEST_CHANGES counts its findings as
    returned, WRONG_APPROACH 1, APPROVE and NEEDS_HUMAN 0 (NEEDS_HUMAN shows in the recorded variant)."""
    if review["variant"] == "REQUEST_CHANGES":
        return len(review["findings"])
    return int(review["variant"] == "WRONG_APPROACH")


def outcome_of(record, terminal, names):
    """outcome, failure, best_of_n's selected candidate, the variant of reviewed_change and review_once, and
    review_once's blockers, findings and whole review, from the terminal row."""
    out = {"outcome": terminal["outcome"], "failure": None, "selected": None, "variant": None}
    if terminal["outcome"] != "completed":
        failed = {"failure": {"code": terminal.get("code"), "message": terminal.get("message")}}
        return out | failed | ({"blockers": None} if record["arm"] == "review_once" else {})
    value = terminal["value"]
    if record["arm"] in ("reviewed_change", "review_once"):
        out["variant"] = value["variant"]
    if record["arm"] == "review_once":
        out |= {"blockers": blockers(value), "findings": value.get("findings", []), "review": value}
    if record["arm"] == "best_of_n":
        out["selected"] = next((n for n, c in zip(names, record["candidates"]) if value["winner"] in (c, n)), None)
        if out["selected"] is None:
            out |= {"outcome": "failed", "failure": {"code": "winner_unmatched", "message": value["winner"]}}
    return out


def finished_memo(state_root):
    """The run's one orchestrator memo under its state root and its rows; it must end in a terminal row."""
    memos = sorted(Path(state_root).glob("*/memo.jsonl"))
    if len(memos) != 1:
        raise SystemExit(f"{state_root}: expected one orchestrator run, found {len(memos)}")
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


def command_outcome(records, record):
    """A generic-command run's outcome, failure, call count and wall clock from the terminal.json of the one run
    directory under the state root that holds one (an orchestrator run the agent started there is not the run), whose
    `calls` must equal the shims' call directories; when completed, the last call's patch as `final`."""
    terminals = sorted(Path(record["state_root"]).glob("*/terminal.json"))
    if len(terminals) != 1:
        raise SystemExit(f"{record['state_root']}: expected one run directory with a terminal.json, found "
                         f"{[path.parent.name for path in terminals]}; finish the run first")
    terminal = load(terminals[0])
    calls = sorted((records / "calls").glob("*"), key=lambda p: int(p.name))
    if terminal["calls"] != len(calls):
        raise SystemExit(f"{records}: the terminal counts {terminal['calls']} provider calls but the shims recorded "
                         f"{len(calls)}: the run is invalid (shim not first on PATH?)")
    out = {"outcome": terminal["outcome"], "failure": terminal["failure"], "selected": None, "variant": None,
           "patches": {}, "calls": len(calls), "wall_clock_sec": terminal["finished_at"] - terminal["started_at"]}
    if out["outcome"] == "completed":
        if not calls:
            raise SystemExit(f"{records}: no call directories: the run is invalid (shim not first on PATH?)")
        out["patches"] = copy_patches(records, {"final": (calls[-1], Path(record["candidates"][0]).name)})
    return out


def collect(records):
    """Pair the memo's provider effects with call directories and copy the comparator's patches; a generic-command
    run is read from its terminal.json instead."""
    records = records.resolve()
    record = load(records / "record.json")
    if record.get("arm_kind") == "generic-command":
        record.update(command_outcome(records, record))
        dump(records / "record.json", record)
        return record
    memo, rows = finished_memo(record.get("state_root", records / "state"))  # R/state: prepared before R34
    calls = paired_calls(records, rows)
    committed = [calls[(r["identity"], r["attempt"])] for r in rows  # agent_turn: a native agent session's turn
                 if r["record"] == "committed" and r["effect_class"] in ("provider", "agent_turn")]
    names = [Path(c).name for c in record["candidates"]]
    first_start = min((r["time"] for r in rows if r["record"] == "started"), default=memo.stat().st_mtime)
    record.update(outcome_of(record, rows[-1], names), patches={}, calls=len(calls),
                  wall_clock_sec=memo.stat().st_mtime - first_start)  # until the memo's last write
    if record["outcome"] == "completed":
        record["patches"] = copy_patches(records, comparator_patches(record["arm"], committed, names))
    if record["arm"] == "review_once" and record["patches"]:  # the reviewer may change only ignored files
        # ponytail: byte comparison; a hand-written --apply patch (no `index` lines) reads as changed
        record["candidate_changed"] = sha256_file(records / record["patches"]["final"]) != record["applied"]["sha256"]
    dump(records / "record.json", record)
    return record


def scan(records, solution, home=None, roots=(), others=()):
    """Record every contamination hit of the run (file, line, pattern, excerpt) and the number of calls the
    scan covers; any earlier verdict is dropped. `roots`: further (name, path) prefixes, such as a search's
    archive, lineage log and holdout roots. A state root outside the run's tree (a spec's state directory)
    adds its siblings, other runs' state, to the other trees; `others` names further other trees (directory
    names), such as other runs' state directories when this run keeps its state in its tree."""
    records, home = records.resolve(), home or Path.home()
    record = load(records / "record.json")
    others = [*contamination.siblings(record["tree"]), *others]
    state_root = Path(record.get("state_root", record["tree"]))
    if not state_root.is_relative_to(record["tree"]) and state_root.parent.is_dir():
        others += contamination.siblings(state_root)
    compiled = contamination.patterns(
        main=record["main"], runtime=record["runtime"], solution=solution, home=home, others=others,
        roots=[("records root", records.parents[1]), *((name, Path(path).resolve()) for name, path in roots)])
    hits = contamination.find_hits(records, record["tree"], record["created_at"], home, compiled)
    record["scan"] = {"solution": solution, "hits": hits, "verdict": None,
                      "calls": len(list((records / "calls").glob("*")))}
    dump(records / "record.json", record)
    for hit in hits:
        print(f"{hit['file']}:{hit['line']}: {hit['pattern']}: {hit['text']}")
    return hits


def adjudicate(records, verdict, reason):
    """Record the controller's verdict on a scanned run: contaminated (excluded from the pool) or cleared."""
    record = load(records / "record.json")
    if "scan" not in record:
        raise SystemExit(f"{records} has not been scanned")
    contamination.refuse_clearing(verdict, record["scan"]["hits"], records)
    record["scan"]["verdict"] = {"verdict": verdict, "reason": reason, "hits": len(record["scan"]["hits"])}
    dump(records / "record.json", record)


def scan_command(a):
    if bool(a.run) == bool(a.pool and a.judge) or (a.verdict and not a.reason):
        raise SystemExit("scan takes --run R or --pool P --judge MODEL, and --verdict needs --reason")
    if a.verdict:
        (adjudicate(a.run, a.verdict, a.reason) if a.run
         else pooling.adjudicate_judge(a.pool, a.judge, a.verdict, a.reason))
        return
    hits = scan(a.run, a.hash, roots=a.root) if a.run else pooling.scan_judge(a.pool, a.judge, a.hash)
    print(f"{len(hits)} hits; record a verdict with --verdict when there are any")


def named_root(text):
    name, sep, path = text.partition("=")
    if not (name and sep and path):
        raise argparse.ArgumentTypeError(f"expected NAME=PATH, not {text!r}")
    return name, Path(path)


def parser():
    top = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = top.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    for name in ("--task", "--root", "--runtime"):
        run.add_argument(name, type=Path, required=True)
    run.add_argument("--arm", choices=ARMS, required=True)
    run.add_argument("--candidates", type=int)
    run.add_argument("--set", action="append", default=[], metavar="NAME=VALUE", help="other typed input")
    run.add_argument("--apply", type=Path, help="review_once: the patch to review (a collected final.diff)")
    sub.add_parser("collect").add_argument("--run", type=Path, required=True, help="records directory")
    scan_cmd = sub.add_parser("scan", help="a run (--run R) or a pool's judge (--pool P --judge MODEL)")
    scan_cmd.add_argument("--run", type=Path, help="records directory")
    scan_cmd.add_argument("--pool", type=Path)
    scan_cmd.add_argument("--judge")
    action = scan_cmd.add_mutually_exclusive_group(required=True)
    action.add_argument("--hash", help="the solution commit: record every hit")
    action.add_argument("--verdict", choices=("contaminated", "cleared"), help="record the controller's verdict")
    scan_cmd.add_argument("--reason", help="why, with --verdict")
    scan_cmd.add_argument("--root", action="append", default=[], type=named_root, metavar="NAME=PATH",
                          help="with --run: a further prefix the scan counts as a hit named NAME (repeatable)")
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
        run_arm(a.task, a.arm, a.root, a.runtime, a.candidates, a.set, a.apply)
    elif a.command == "collect":
        print(json.dumps(collect(a.run), indent=2))
    elif a.command == "scan":
        scan_command(a)
    elif a.command == "pool":
        pooling.pool(a.task, a.criterion, a.out, a.judge, a.runs)
    else:
        pooling.verify_pool(a.pool)


if __name__ == "__main__":
    main()
