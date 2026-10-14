"""Comparison harness: candidate repositories, run commands, collection, contamination scan, scoring pool.

  prepare.py run --task T --arm A --root W --runtime R [--candidates N] [--set NAME=VALUE ...]
  prepare.py collect --run RUN
  prepare.py scan --run RUN --hash SOLUTION_COMMIT
  prepare.py pool --task T --criterion C --out D --judge MODEL [--judge MODEL ...] RUN [RUN ...]
  prepare.py verify-pool --pool D

A run directory W/<arm>/run-<k>/ holds cand-<k>/ (the candidate repositories), tmp/ (TMPDIR),
inputs.json, command.sh (the printed command), calls/<n>/ (written by shim/claude and shim/codex),
collected/<label>.diff and record.json: written by `run`; `collect` adds the outcome, call count,
wall clock and patches; `scan` adds the hits. A pool directory D holds clones/<id>/ (what judges see), patches/<id>.diff
(each clone's recorded patch), mapping.json (read by summarize.py and verify-pool only) and
score-inputs-<judge>.json. Design: docs/design/orc_effectiveness_comparison_harness.md.
Standard library only; needs git on PATH.
"""

import argparse
import hashlib
import json
import os
import random
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

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
STRIPPED = ("docs/design/", "artifacts/")  # D8: removed from every pooled patch
SEED_COMMIT = ("-c", "user.name=compare", "-c", "user.email=compare@example.invalid",
               "commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "compare seed")
SEED_DATES = {"GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000"}


def git(repo, *args, env=None, raw=False, stdin=None):
    """Run git in `repo`; return stdout (bytes when `raw`, else stripped text); fail with git's message."""
    done = subprocess.run(["git", "-C", str(repo), "-c", "core.hooksPath=/dev/null", *args],
                          input=stdin, capture_output=True, env={**os.environ, **(env or {})})
    if done.returncode:
        raise SystemExit(f"git {' '.join(args)} failed in {repo}: {done.stderr.decode(errors='replace').strip()}")
    return done.stdout if raw else done.stdout.decode().strip()


def load(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_candidate(source, base, seed, dest):
    """Check out `base` alone at `dest` (no remote, no other refs), commit `seed` onto it; return that commit."""
    dest.mkdir(parents=True)
    git(dest, "init", "-q")
    git(dest, "fetch", "-q", "--depth", "1", "--upload-pack",
        "git -c uploadpack.allowAnySHA1InWant=true upload-pack", str(source), base)
    git(dest, "checkout", "-q", "FETCH_HEAD")
    (dest / ".git" / "FETCH_HEAD").unlink()  # it names the source checkout
    if seed.is_dir():
        shutil.copytree(seed, dest, dirs_exist_ok=True)
    git(dest, "add", "-A", "-f", ".")
    git(dest, *SEED_COMMIT, env=SEED_DATES)
    return git(dest, "rev-parse", "HEAD")


def patch_of(repo, base):
    """The repository's changes against `base`, new files included, leaving new files intent-to-add."""
    git(repo, "add", "-A", "-N", ".")
    patch = git(repo, "diff", "--binary", base, raw=True)
    git(repo, "reset", "-q")
    git(repo, "add", "-A", "-N", ".")
    return patch


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


def run_arm(task, arm, root, runtime, candidates=None, sets=()):
    """Build the run's candidates and inputs.json, write record.json, print the command; return the run dir."""
    source, entry, source_root, providers, _ = ARMS[arm]
    count = candidates or (4 if arm == "best_of_n" else 1)
    if arm != "best_of_n" and count != 1:
        raise SystemExit(f"{arm} works in a single candidate, not {count}")
    task, runtime = task.resolve(), runtime.resolve()
    base = git(runtime, "rev-parse", "--verify", (task / "base_commit").read_text().strip() + "^{commit}")
    arm_inputs(task, arm, [Path("/")], sets)  # refuse bad --set values before building anything
    run = next_run_dir(root.resolve() / arm)
    cands = [run / f"cand-{k}" for k in range(1, count + 1)]
    seeded = {build_candidate(runtime, base, task / "seed", cand) for cand in cands}
    if len(seeded) != 1:
        raise SystemExit(f"candidates disagree on the seeded commit: {sorted(seeded)}")
    compare_base = seeded.pop()
    (run / "tmp").mkdir()
    dump(run / "inputs.json", arm_inputs(task, arm, cands, sets))
    cwd = run if arm == "best_of_n" else cands[0]  # -P below: the candidate's orchestrator/ must not shadow PYTHONPATH
    env = {"PYTHONPATH": runtime, "COMPARE_ROOT": run, "COMPARE_BASE": compare_base, "TMPDIR": run / "tmp"}
    command = (f"cd {shlex.quote(str(cwd))} && env "
               + " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env.items())
               + f' PATH={shlex.quote(str(runtime / "experiments/compare/shim"))}:"$PATH" '
               + shlex.join([sys.executable, "-P", "-m", "orchestrator", "run", str(runtime / source),
                             "--entry-workflow", entry, "--source-root", str(runtime / source_root),
                             "--provider-externs-file", str(runtime / providers),
                             "--input-file", str(run / "inputs.json")]))
    dump(run / "record.json", {
        "arm": arm, "task": str(task), "runtime": str(runtime), "base": base, "compare_base": compare_base,
        "candidates": [str(c) for c in cands], "cwd": str(cwd), "command": command, "created_at": time.time(),
    })
    (run / "command.sh").write_text(command + "\n")
    print(command)
    return run


def read_memo(memo):
    return [json.loads(line) for line in memo.read_text().split("\n")[:-1]]  # a final unterminated line is unwritten


def paired_calls(run, rows):
    """Map (identity, attempt) of each provider start to calls/<n>/, the n-th start to the n-th call."""
    starts = [r for r in rows if r["record"] == "started" and "prompt" in r["input_parts"]]
    calls = sorted((run / "calls").glob("*"), key=lambda p: int(p.name))
    if len(starts) != len(calls):
        raise SystemExit(f"{run}: {len(starts)} provider starts in the memo but {len(calls)} call directories "
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


def finished_memo(run):
    """The run's one orchestrator memo (run root for best_of_n, the candidate otherwise) and its rows."""
    memos = [*sorted(run.glob(".orchestrate/runs/*/memo.jsonl")),
             *sorted(run.glob("cand-*/.orchestrate/runs/*/memo.jsonl"))]
    if len(memos) != 1:
        raise SystemExit(f"{run}: expected one orchestrator run, found {len(memos)}")
    rows = read_memo(memos[0])
    if not rows or rows[-1]["record"] != "terminal":
        raise SystemExit(f"{memos[0]}: no terminal record; finish or resume the run first")
    return memos[0], rows


def copy_patches(run, picks):
    (run / "collected").mkdir(exist_ok=True)
    for label, (call, name) in picks.items():
        patch = call / f"patch-{name}.diff"
        if not patch.is_file():
            raise SystemExit(f"{patch} is missing: the run is invalid (shim not first on PATH?)")
        shutil.copyfile(patch, run / "collected" / f"{label}.diff")
    return {label: f"collected/{label}.diff" for label in picks}


def collect(run):
    """Pair the memo's provider effects with call directories and copy the comparator's patches."""
    run = run.resolve()
    record = load(run / "record.json")
    memo, rows = finished_memo(run)
    calls = paired_calls(run, rows)
    committed = [calls[(r["identity"], r["attempt"])] for r in rows
                 if r["record"] == "committed" and r["effect_class"] == "provider"]
    names = [Path(c).name for c in record["candidates"]]
    first_start = min((r["time"] for r in rows if r["record"] == "started"), default=memo.stat().st_mtime)
    record.update(outcome_of(record, rows[-1], names), patches={}, calls=len(calls),
                  wall_clock_sec=memo.stat().st_mtime - first_start)  # until the memo's last write
    if record["outcome"] == "completed":
        record["patches"] = copy_patches(run, comparator_patches(record["arm"], committed, names))
    dump(run / "record.json", record)
    return record


def bounded(path):
    return re.escape(str(path)) + r"(?![\w.-])"  # /x/main must not match /x/main-evidence


def claude_actions(row):
    content = (row.get("message") or {}).get("content")
    return [json.dumps(c["input"], ensure_ascii=False)
            for c in content or [] if isinstance(c, dict) and c.get("type") == "tool_use"]


def codex_actions(row):
    payload = row.get("payload") or {}
    if payload.get("type") not in ("function_call", "custom_tool_call", "local_shell_call"):
        return []
    return [json.dumps(payload.get("arguments") or payload.get("input") or payload.get("action"), ensure_ascii=False)]


def json_actions(path, actions):
    with path.open(errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
            except ValueError as error:
                raise SystemExit(f"{path}:{number}: not JSON ({error})")
            for text in actions(row):
                yield path, number, text


def codex_cwd(path):
    with path.open(errors="replace") as handle:
        return ((json.loads(handle.readline() or "{}").get("payload") or {}).get("cwd")) or ""


def scan_sources(run, record, home):
    """(file, line, text) of the shim's output records and the agents' structured actions for this run."""
    for path in sorted(run.glob("calls/*/std*.txt")):
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            yield path, number, line
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(run))
    for project in sorted((home / ".claude" / "projects").glob(slug + "*")):
        if project.name == slug or project.name.startswith(slug + "-"):
            for path in sorted(project.rglob("*.jsonl")):
                yield from json_actions(path, claude_actions)
    for path in sorted((home / ".codex" / "sessions").glob("*/*/*/rollout-*.jsonl")):
        if path.stat().st_mtime >= record["created_at"] and (codex_cwd(path) + "/").startswith(f"{run}/"):
            yield from json_actions(path, codex_actions)


def scan(run, solution, home=None):
    """D5 contamination scan; records and returns every hit with its file and line."""
    run = run.resolve()
    record = load(run / "record.json")
    common = Path(git(record["runtime"], "rev-parse", "--path-format=absolute", "--git-common-dir"))
    patterns = {"main checkout": bounded(common.parent), "frozen checkout": bounded(record["runtime"]),
                "github.com": r"github\.com", "gh": r"(?<![\w./-])gh\s", "git fetch": r"git\s+fetch",
                "solution hash": re.escape(solution[:7])}
    hits = [{"file": str(path), "line": number, "pattern": name, "text": text[:200]}
            for path, number, text in scan_sources(run, record, home or Path.home())
            for name, pattern in patterns.items() if re.search(pattern, text)]
    record["scan"] = {"solution": solution, "main": str(common.parent), "hits": hits}
    dump(run / "record.json", record)
    for hit in hits:
        print(f"{hit['file']}:{hit['line']}: {hit['pattern']}")
    return hits


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
    `usable` maps arm -> [(run path, record)]; each member is (run path, record, labels sharing one clone)."""
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


def patch_bytes(run, record, label):
    return (Path(run) / record["patches"][label]).read_bytes()


def add_clone(out, task, ref, patch, entry):
    """Build one applied-patch clone under a random id; record its patch; return the id."""
    cid = secrets.token_hex(4)
    clone = out / "clones" / cid
    if build_candidate(ref["runtime"], ref["base"], task / "seed", clone) != ref["compare_base"]:
        raise SystemExit(f"{clone}: seeded commit differs from the runs' {ref['compare_base']}")
    kept, entry["stripped"] = strip(patch)
    if kept:
        git(clone, "apply", "--binary", "-", stdin=kept)
    (out / "patches" / f"{cid}.diff").write_bytes(patch_of(clone, ref["compare_base"]))
    return cid, entry


def pool_runs(records):
    """Mapping rows for every run and the usable ones per arm; refuse unscanned or uncollected runs."""
    rows, usable = {}, {}
    for path, rec in records.items():
        if "outcome" not in rec or "scan" not in rec:
            raise SystemExit(f"{path} has not been {'collected' if 'outcome' not in rec else 'scanned'}")
        hits = rec["scan"]["hits"]
        excluded = f"contamination: {len(hits)} scan hits" if hits else None
        rows[path] = {k: rec[k] for k in ("arm", "outcome", "failure", "calls", "wall_clock_sec", "selected",
                                          "variant")} | {"excluded": excluded}
        if rec["outcome"] == "completed" and not excluded:
            usable.setdefault(rec["arm"], []).append((path, rec))
    return rows, usable


def pool(task, criterion, out, judges, runs):
    """Build the blind scoring pool, mapping.json and one scoring inputs file per judge."""
    task, out = task.resolve(), out.resolve()
    records = {str(Path(r).resolve()): load(Path(r) / "record.json") for r in runs}
    ref = next(iter(records.values()))
    if {(r["task"], r["compare_base"]) for r in records.values()} != {(str(task), ref["compare_base"])}:
        raise SystemExit("runs in one pool must share the task and the seeded commit")
    rows, usable = pool_runs(records)
    batches = compose(usable)
    if not batches:
        raise SystemExit("no completed, uncontaminated run to pool")
    (out / "clones").mkdir(parents=True)
    (out / "patches").mkdir()
    clones, members = {}, []
    anchors = sorted((task / "anchors").glob("*.diff"))
    for batch in batches:
        made = [add_clone(out, task, ref, patch_bytes(path, rec, labels[0]),
                          {"run": path, "arm": rec["arm"], "labels": labels}) for path, rec, labels in batch]
        made += [add_clone(out, task, ref, a.read_bytes(), {"run": None, "arm": "anchor", "labels": [a.stem]})
                 for a in anchors]
        clones.update(made)
        members.append([cid for cid, _ in made])
    mapping = {"task": str(task), "criterion_sha256": sha256_file(criterion), "compare_base": ref["compare_base"],
               "judges": judges, "runs": rows, "clones": clones, "batches": members}
    dump(out / "mapping.json", mapping)
    write_score_inputs(out, mapping, (task / "intent.txt").read_text())
    print(f"{len(clones)} clones in {len(members)} batches under {out / 'clones'}")
    return mapping


def write_score_inputs(out, mapping, intent):
    """score.orc inputs per judge: the same batches, each judge's clone order drawn at random."""
    rng = random.SystemRandom()
    for judge in mapping["judges"]:
        dump(out / f"score-inputs-{judge}.json", {
            "batches": [{"clones": [str(out / "clones" / cid) for cid in rng.sample(ids, len(ids))]}
                        for ids in mapping["batches"]],
            "intent": intent, "criterion_sha256": mapping["criterion_sha256"], "judge_model": judge})


def changed_paths(recorded, current):
    old, new = (dict((paths[-1] if paths else b"", part) for paths, part in sections(p)) for p in (recorded, current))
    return sorted(p.decode(errors="replace") for p in set(old) | set(new) if old.get(p) != new.get(p))


def verify_pool(out):
    """Restore every clone whose HEAD or patch differs from the one recorded when the pool was built."""
    mapping, out = load(out / "mapping.json"), out.resolve()
    base, changed = mapping["compare_base"], 0
    for cid in mapping["clones"]:
        clone, recorded = out / "clones" / cid, (out / "patches" / f"{cid}.diff").read_bytes()
        head, current = git(clone, "rev-parse", "HEAD"), patch_of(clone, base)
        if head == base and current == recorded:
            continue
        changed += 1
        print(f"{cid}: HEAD {head[:12]}, changed {', '.join(changed_paths(recorded, current)) or 'nothing'}")
        git(clone, "reset", "-q", "--hard", base)
        git(clone, "clean", "-q", "-f", "-d", "-x")
        if recorded:
            git(clone, "apply", "--binary", str(out / "patches" / f"{cid}.diff"))
        patch_of(clone, base)
    if changed:
        raise SystemExit(f"{changed} clone(s) differed from their recorded patch and were restored")
    print(f"{len(mapping['clones'])} clones match their recorded patches")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--task", type=Path, required=True)
    run.add_argument("--arm", choices=ARMS, required=True)
    run.add_argument("--root", type=Path, required=True)
    run.add_argument("--runtime", type=Path, required=True, help="frozen runtime checkout")
    run.add_argument("--candidates", type=int)
    run.add_argument("--set", action="append", default=[], metavar="NAME=VALUE", help="other typed input")
    sub.add_parser("collect").add_argument("--run", type=Path, required=True)
    scan_cmd = sub.add_parser("scan")
    scan_cmd.add_argument("--run", type=Path, required=True)
    scan_cmd.add_argument("--hash", required=True, help="the solution commit")
    pool_cmd = sub.add_parser("pool")
    for name in ("--task", "--criterion", "--out"):
        pool_cmd.add_argument(name, type=Path, required=True)
    pool_cmd.add_argument("--judge", action="append", required=True)
    pool_cmd.add_argument("runs", nargs="+", type=Path)
    sub.add_parser("verify-pool").add_argument("--pool", type=Path, required=True)
    a = parser.parse_args(argv)
    if a.command == "run":
        run_arm(a.task, a.arm, a.root, a.runtime, a.candidates, a.set)
    elif a.command == "collect":
        print(json.dumps(collect(a.run), indent=2))
    elif a.command == "scan":
        print(f"{len(scan(a.run, a.hash))} hits")
    elif a.command == "pool":
        pool(a.task, a.criterion, a.out, a.judge, a.runs)
    else:
        verify_pool(a.pool)


if __name__ == "__main__":
    main()
