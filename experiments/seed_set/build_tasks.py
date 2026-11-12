"""Build the seed-set task packages (plan `docs/plans/2026-11-11-seed-set-calibration-plan.md`, Step 1b).

Provider-free, mechanical, from this repository's history. Rules, in order:
1. Mine (`mine`): non-merge commits reachable from `TIP`, author and committer dates >= `FLOOR`, no revert
   (made or suffered), fix-worded (`FIX_WORDS`; dropped once if under 20 are admitted), a changed
   `tests/**/test_*.py`, no deletion under `tests/`, 1-5 files and <= 200 lines under `orchestrator/`, one
   commit per `git patch-id --stable` (oldest kept), a parent ignoring `.orchestrate/`; ordered by `rank`.
2. Screen (`evaluate`): the fix's touched test files once on the parent (fix tests overlaid) and once on the
   fix, in `git archive` trees. Fail-to-pass: a function new in the fix, all instances passing or skipping
   (one passing) on the fix, some instance failing or uncollected on the parent. >= 2 needed; the first by
   `rank(node id)` is visible, the rest hidden.
3. Package (`write_package`, the layout of `experiments/compare/README.md`): `seed/` = the fix's `tests/`
   files minus hidden functions (`ast` line ranges) plus `dev-check.json`; `hidden/` = the fix's versions;
   `hidden_tests.txt` = hidden functions and touched test files; empty `anchors/<id>-base.diff`;
   `anchors/<id>-upstream.diff` = the fix without `tests/`; `intent.txt` = subject and body without
   `Co-Authored-By`/`Signed-off-by`; `task.txt` adds the visible check and the hands-off rule.
4. Leaks: a hidden name (whole word) in the statement or the seeded tree, a statement under 80 characters,
   or one repeating a 20+ character line the fix adds outside `tests/`.
5. Provider guard: fresh no-provider stubs first on `PATH` for every run; any logged line rejects the
   candidate ("tests attempt a provider call", argv in `note`).
6. Oracle (`oracle`), on `repos.build_candidate` and `summarize.hidden_failures`, `RUNS` times per side:
   base fails the visible check and every hidden function; with the upstream anchor applied the visible
   check passes and no hidden node fails, each hidden evaluation under `HIDDEN_LIMIT_SEC`. First deviation
   rejects (no retries); `--prior` rejects an outcome that differs from an earlier build's `rows.jsonl`.
7. Admit (`admit`), rank order: skip one whose `orchestrator/` file two admitted tasks already change; stop
   at `MAX_TASKS`; the first `DRAWN` are drawn, the rest reserve.

Outputs: `tasks/<id>/`; `tasks.jsonl` (deterministic, package sha256s; `verify` rechecks them);
`screening.jsonl` (every commit, its reason, wall times). Depends on git, `experiments.compare.repos` and
`.summarize`, pytest in `sys.executable`, the guard first on `PATH` (checked). Work trees under `--work` are
deleted after each evaluation; the run stops under 20 GB free on `/` or `/home`.
"""

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from experiments.compare import repos, summarize

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TIP = "4a9dd007ec4932f2f918ae4d268f72af45408226"  # the plan's commit; history is mined from here
SEED = "seed-set-2026-11-11"
FLOOR = "2026-07-01"
FIX_WORDS = re.compile(r"\b(fix(es|ed)?|bug|regression|crash|incorrect|wrong)\b", re.I)
TRAILER = re.compile(r"^(co-authored-by|signed-off-by):", re.I)
TEST_FILE = re.compile(r"^tests/(.+/)?test_[^/]*\.py$")
MAX_SOURCE_FILES, MAX_SOURCE_LINES = 5, 200
RUNS, HIDDEN_LIMIT_SEC, RUN_TIMEOUT_SEC = 5, 120, 600
MIN_TEXT, MIN_LEAK_LINE = 80, 20
MAX_TASKS, DRAWN, MAX_SHARE = 40, 20, 2
MIN_FREE = 20 * 2**30
GUARD = ROOT / "experiments/thread_m/no_provider"
BASE_PATH = os.environ.get("PATH", "")
DIFF = ("--full-index", "--diff-algorithm=myers", "--no-renames", *repos.DIFF_FLAGS)


def rank(key):
    return hashlib.sha256(f"{SEED}|{key}".encode()).hexdigest()


def git(*args, repo=ROOT, raw=False):
    return repos.git(repo, *args, raw=raw)


def mine(repo=ROOT, tip=TIP, fix_wording=True):
    """([candidate dict], [reject dict]); candidates in rank order. Local git only."""
    log = git("log", "--no-merges", f"--since={FLOOR}", "--reverse", "--no-renames", "--numstat",
              "--format=%x00%H%x01%P%x01%aI%x01%cI%x01%B%x02", tip, repo=repo)
    reverted = set(re.findall(r"This reverts commit ([0-9a-f]{40})", git("log", "--format=%B", tip, repo=repo)))
    seen_patch, kept, rejects = {}, [], []
    for chunk in log.split("\x00")[1:]:
        head, _, stat = chunk.partition("\x02")
        sha, parents, adate, cdate, message = head.split("\x01", 4)
        files = [(p, int(a) if a != "-" else 0, int(d) if d != "-" else 0)
                 for a, d, p in (line.split("\t", 2) for line in stat.strip().splitlines())]
        reason = screen_commit(repo, sha, adate, cdate, message, files, reverted, fix_wording)
        if not reason:
            pid = patch_id(repo, sha)
            reason = f"same patch-id as {seen_patch[pid][:10]}" if pid in seen_patch else None
            seen_patch.setdefault(pid, sha)
        if not reason and ".orchestrate" not in show(repo, f"{parents.split()[0]}:.gitignore"):
            reason = "base does not ignore .orchestrate/"
        if reason:
            rejects.append({"commit": sha, "stage": "mine", "reason": reason})
            continue
        source = [f for f in files if f[0].startswith("orchestrator/")]
        kept.append({"repo": str(repo), "commit": sha, "parent": parents.split()[0], "rank": rank(sha),
                     "subject": message.splitlines()[0], "message": message,
                     "tests": sorted(p for p, _, _ in files if p.startswith("tests/")),
                     "source_files": sorted(p for p, _, _ in source),
                     "source_lines": sum(a + d for _, a, d in source),
                     "nontest_lines": sum(a + d for p, a, d in files if not p.startswith("tests/"))})
    return sorted(kept, key=lambda c: c["rank"]), rejects


def screen_commit(repo, sha, adate, cdate, message, files, reverted, fix_wording):
    """The first mining rule `sha` breaks, or None."""
    source = [f for f in files if f[0].startswith("orchestrator/")]
    if min(adate[:10], cdate[:10]) < FLOOR:
        return "dated before the floor"
    if not source:
        return "no change under orchestrator/"
    if len(source) > MAX_SOURCE_FILES or sum(a + d for _, a, d in source) > MAX_SOURCE_LINES:
        return "over 5 files or 200 lines under orchestrator/"
    if not any(TEST_FILE.match(p) for p, _, _ in files):
        return "no tests/**/test_*.py change"
    if message.startswith("Revert") or "This reverts commit" in message or sha in reverted:
        return "revert or reverted"
    if fix_wording and not FIX_WORDS.search(message):
        return "not fix-worded"
    if git("diff", "--no-renames", "--diff-filter=D", "--name-only", f"{sha}^", sha, "--", "tests", repo=repo):
        return "deletes a file under tests/"
    return None


def patch_id(repo, sha):
    diff = git("show", "--format=", "--no-renames", sha, repo=repo, raw=True)
    out = subprocess.run(["git", "-C", str(repo), "patch-id", "--stable"], input=diff,
                         capture_output=True, check=True).stdout.decode().split()
    return out[0] if out else f"empty:{sha}"


def statement(message):
    lines = [line.rstrip() for line in message.strip().splitlines() if not TRAILER.match(line)]
    return "\n".join(lines).strip() + "\n"


def test_functions(source):
    """{qualified name 'Class::func' or 'func': node} for every function in classes and the module."""
    found = {}

    def walk(body, prefix):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found[prefix + node.name] = node
            elif isinstance(node, ast.ClassDef):
                walk(node.body, f"{prefix}{node.name}::")
    try:
        walk(ast.parse(source).body, "")
    except SyntaxError:
        pass
    return found


def strip_functions(source, qualnames):
    """`source` without the named functions (decorators included), deleted by line range."""
    nodes = [node for name, node in test_functions(source).items() if name in qualnames]
    lines = source.splitlines(keepends=True)
    for node in sorted(nodes, key=lambda n: n.lineno, reverse=True):
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        del lines[start - 1:node.end_lineno]
    return "".join(lines)


def split(groups):
    """(visible node, [hidden nodes]) from fail-to-pass function node ids, by rank."""
    ordered = sorted(groups, key=rank)
    return ordered[0], ordered[1:]


def package_hash(package):
    """sha256 over every file's relative path and content sha256, sorted by path."""
    rows = sorted(f"{p.relative_to(package).as_posix()}\0{repos.sha256_file(p)}\n"
                  for p in package.rglob("*") if p.is_file())
    return hashlib.sha256("".join(rows).encode()).hexdigest()


def outcomes(xml_path, files):
    """{node id: 'pass'|'skip'|'fail'} from a pytest JUnit file over `files`."""
    if not xml_path.is_file():
        return {}
    dotted = sorted(((f[:-3].replace("/", "."), f) for f in files), key=lambda x: -len(x[0]))
    result = {}
    for case in ET.parse(xml_path).iter("testcase"):
        cls, name = case.get("classname", ""), case.get("name", "")
        for mod, path in dotted:
            if cls == mod or cls.startswith(mod + "."):
                parts = [path, *filter(None, cls[len(mod) + 1:].split(".")), name]
                kind = ("fail" if case.find("failure") is not None or case.find("error") is not None
                        else "skip" if case.find("skipped") is not None else "pass")
                result["::".join(parts)] = kind
                break
    return result


def run_tests(tree, files, junit):
    started = time.monotonic()
    try:
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}",
                        *files], cwd=tree, env={**os.environ, "PYTHONPATH": str(tree)},
                       capture_output=True, timeout=RUN_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return None, time.monotonic() - started
    return outcomes(junit, files), time.monotonic() - started


def fail_to_pass(base, fixed, new_functions):
    """Node ids of new functions failing on the parent and passing on the fix (parameters grouped)."""
    groups = {}
    for node, kind in fixed.items():
        groups.setdefault(node.split("[")[0], []).append((kind, base.get(node, "fail")))
    return sorted(g for g, rows in groups.items() if g.split("::", 1)[1] in new_functions.get(g.split("::")[0], ())
                  and all(k in ("pass", "skip") for k, _ in rows) and any(k == "pass" for k, _ in rows)
                  and any(b == "fail" for _, b in rows))


def archive(repo, commit, dest, paths=()):
    dest.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(["git", "-C", str(repo), "archive", commit, *paths], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=tar, check=True)


def remove(path):
    if path.exists():
        subprocess.run(["chmod", "-R", "u+rwx", str(path)], check=False)
        shutil.rmtree(path)


def free_ok():
    return all(shutil.disk_usage(p).free >= MIN_FREE for p in ("/", "/home"))


def leak_reason(text, hidden_names, added_lines, seeded_tree):
    if len(text.strip()) < MIN_TEXT:
        return "statement under 80 characters"
    if any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text) for n in hidden_names):
        return "statement names a hidden test"
    if any(line in text for line in added_lines):
        return "statement repeats a line the fix adds"
    grep = subprocess.run(["grep", "-rlwF", "--exclude-dir=.git", *[a for n in hidden_names for a in ("-e", n)],
                           str(seeded_tree)], capture_output=True, text=True)
    if grep.stdout.strip():
        return "hidden function name in the seeded tree: " + grep.stdout.split()[0].replace(f"{seeded_tree}/", "")
    return None


def write_package(cand, visible, hidden, pkg):
    """Write the harness package for `cand` into `pkg`; return the hidden function names."""
    repo, sha, parent, tid = Path(cand["repo"]), cand["commit"], cand["parent"], cand["commit"][:10]
    hidden_by_file = {}
    for node in hidden:
        path, qual = node.split("::", 1)
        hidden_by_file.setdefault(path, set()).add(qual)
    for path in cand["tests"]:
        content = git("show", f"{sha}:{path}", repo=repo, raw=True)
        (pkg / "hidden" / path).parent.mkdir(parents=True, exist_ok=True)
        (pkg / "hidden" / path).write_bytes(content)
        if path in hidden_by_file:
            content = strip_functions(content.decode(), hidden_by_file[path]).encode()
        (pkg / "seed" / path).parent.mkdir(parents=True, exist_ok=True)
        (pkg / "seed" / path).write_bytes(content)
    argv = ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", visible]
    (pkg / "seed/dev-check.json").write_text(json.dumps({"argv": argv, "timeout_sec": RUN_TIMEOUT_SEC}, indent=2) + "\n")
    touched = [p for p in cand["tests"] if TEST_FILE.match(p)]
    (pkg / "hidden_tests.txt").write_text("".join(f"{n}\n" for n in [*hidden, *touched]))
    (pkg / "anchors").mkdir()
    (pkg / "anchors" / f"{tid}-base.diff").write_bytes(b"")
    (pkg / "anchors" / f"{tid}-upstream.diff").write_bytes(
        git("diff", *DIFF, parent, sha, "--", ".", ":(exclude)tests", repo=repo, raw=True))
    text = statement(cand["message"])
    (pkg / "intent.txt").write_text(text)
    (pkg / "task.txt").write_text(
        f"{text}\nVisible check: `{' '.join(argv)}` (the command in `dev-check.json`). It fails now and "
        "should pass once the change is made. Leave `dev-check.json` and the existing tests unchanged; "
        "you may add new tests.\n")
    (pkg / "base_commit").write_text(parent + "\n")
    return sorted({n.split("::")[-1] for n in hidden})


def visible_passes(clone, argv):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    started = time.monotonic()
    try:
        ok = subprocess.run(argv, cwd=clone, env=env, capture_output=True, timeout=RUN_TIMEOUT_SEC).returncode == 0
    except subprocess.TimeoutExpired:
        ok = False
    return ok, round(time.monotonic() - started, 1)


def oracle(repo, pkg, clone, runs=RUNS):
    """(reject reason or None, wall times); the package's check on the harness's seeded candidate."""
    hidden = [n for n in (pkg / "hidden_tests.txt").read_text().split() if "::" in n]
    nodes = (pkg / "hidden_tests.txt").read_text().split()
    argv = json.loads((pkg / "seed/dev-check.json").read_text())["argv"]
    seeded = repos.build_candidate(repo, (pkg / "base_commit").read_text().strip(), pkg / "seed", clone)
    times = {"visible_base": [], "hidden_base": [], "visible_fix": [], "hidden_fix": []}

    def hidden_run(key, check):
        started = time.monotonic()
        failed = summarize.hidden_failures(clone, pkg, check, sys.executable)
        times[key].append(round(time.monotonic() - started, 1))
        return failed
    for side in ("base", "fix"):
        if side == "fix":
            git("apply", "--binary", str(pkg / "anchors" / f"{pkg.name}-upstream.diff"), repo=clone)
        for i in range(runs):
            ok, sec = visible_passes(clone, argv)
            times[f"visible_{side}"].append(sec)
            if ok != (side == "fix"):
                return f"visible check {'fails on the fix' if ok is False else 'passes on the base'} (run {i + 1})", times
            if side == "base" and set(hidden_run("hidden_base", hidden)) != set(hidden):
                return f"a hidden function passes on the base (run {i + 1})", times
            if side == "fix" and hidden_run("hidden_fix", nodes):
                return f"a hidden node fails on the fix (run {i + 1})", times
            if side == "fix" and times["hidden_fix"][-1] >= HIDDEN_LIMIT_SEC:
                return f"hidden evaluation {times['hidden_fix'][-1]} s, over {HIDDEN_LIMIT_SEC} s", times
    if repos.git(clone, "rev-parse", "HEAD") != seeded:
        return "seeded commit moved during the check", times
    return None, times


def evaluate(cand, work, runs=RUNS):
    """Screen, package and check one candidate under `work`; the screening row (package left in work/pkgs)."""
    tid = cand["commit"][:10]
    row = {"commit": cand["commit"], "stage": "evaluate"}
    if not free_ok():
        return {**row, "reason": "disk: under 20 GB free", "stop": True}
    box = work / tid
    remove(box)
    os.environ.update(TMPDIR=str(box / "tmp"), PYTHONDONTWRITEBYTECODE="1")
    tempfile.tempdir = None  # a reused worker process caches the previous task's (deleted) TMPDIR
    (box / "tmp").mkdir(parents=True)
    shutil.copytree(GUARD, box / "guard/no_provider")  # its stubs log to box/guard/no-provider.log
    os.environ["PATH"] = f"{box / 'guard/no_provider'}:{BASE_PATH}"
    try:
        result = _evaluate(cand, box, work / "pkgs" / tid, runs)
        attempts = provider_attempts(box / "guard/no-provider.log")
        if attempts:
            result = {**result, "reason": "tests attempt a provider call", "note": attempts,
                      "reason_without_attempt": result.get("reason")}
        return {**row, **result}
    finally:
        remove(box)


def provider_attempts(log):
    """The distinct argv lines (timestamp dropped) the no-provider stubs logged, in first-seen order."""
    lines = log.read_text().splitlines() if log.is_file() else []
    return list(dict.fromkeys(line.split(" ", 1)[1] for line in lines if " " in line))


def _evaluate(cand, box, pkg, runs):
    repo, sha, parent = Path(cand["repo"]), cand["commit"], cand["parent"]
    touched = [p for p in cand["tests"] if TEST_FILE.match(p)]
    archive(repo, parent, box / "base")
    archive(repo, sha, box / "base", cand["tests"])
    archive(repo, sha, box / "fix")
    base, base_sec = run_tests(box / "base", touched, box / "base.xml")
    fixed, fix_sec = run_tests(box / "fix", touched, box / "fix.xml")
    times = {"screen_base": round(base_sec, 1), "screen_fix": round(fix_sec, 1)}
    if base is None or fixed is None:
        return {"reason": "screening run over 600 s", "times": times}
    new = {p: set(test_functions(show(repo, f"{sha}:{p}"))) - set(test_functions(show(repo, f"{parent}:{p}")))
           for p in touched}
    groups = fail_to_pass(base, fixed, new)
    if len(groups) < 2:
        return {"reason": f"{len(groups)} fail-to-pass function(s), need 2", "times": times, "f2p": groups}
    visible, hidden = split(groups)
    remove(pkg)
    names = write_package(cand, visible, hidden, pkg)
    shutil.copytree(pkg / "seed", box / "base", dirs_exist_ok=True)
    for path in [p for p in cand["tests"] if p.endswith(".py")]:
        try:
            ast.parse((pkg / "seed" / path).read_text())
        except SyntaxError:
            return {"reason": f"seed file {path} does not parse after deletion", "times": times}
    added = {line[1:].strip() for line in (pkg / "anchors" / f"{sha[:10]}-upstream.diff").read_text(
        errors="replace").splitlines() if line.startswith("+") and not line.startswith("+++")}
    reason = leak_reason((pkg / "intent.txt").read_text(), names,
                         [a for a in added if len(a) >= MIN_LEAK_LINE], box / "base")
    if reason:
        return {"reason": reason, "times": times, "visible": visible, "hidden": hidden}
    reason, oracle_times = oracle(repo, pkg, box / "clone", runs)
    return {"reason": reason, "times": {**times, **oracle_times}, "visible": visible, "hidden": hidden,
            "package_sha256": package_hash(pkg)}


def show(repo, spec):
    """The file at `spec` ('commit:path'), or '' when absent."""
    done = subprocess.run(["git", "-C", str(repo), "show", spec], capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else ""


def admit(cands, rows):
    """Rank-order admission: (admitted candidates, {sha: skip reason}) under the share and size caps."""
    admitted, skipped, uses = [], {}, {}
    for cand in cands:
        row = rows.get(cand["commit"])
        if row is None or row.get("reason") or len(admitted) >= MAX_TASKS:
            continue
        if any(uses.get(f, 0) >= MAX_SHARE for f in cand["source_files"]):
            skipped[cand["commit"]] = "source file already in two admitted tasks"
            continue
        for f in cand["source_files"]:
            uses[f] = uses.get(f, 0) + 1
        admitted.append(cand)
    return admitted, skipped


def evaluate_all(cands, rows, work, workers, runs):
    """Evaluate the candidates without a row, in rank order, `workers` at a time; stop on low disk.

    Every finished row is appended to `work/rows.jsonl` and reused after a restart, so an apparatus
    crash never re-runs (retries) a recorded evaluation."""
    log = work / "rows.jsonl"
    if log.is_file():
        rows.update((r["commit"], r) for r in map(json.loads, log.read_text().splitlines()))
    todo = [c for c in cands if c["commit"] not in rows]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for cand, row in zip(todo, pool.map(evaluate, todo, [work] * len(todo), [runs] * len(todo))):
            rows[cand["commit"]] = row
            print(f"{cand['commit'][:10]} {row.get('reason') or 'PASS'} {row.get('times', {})}", flush=True)
            if row.get("stop"):
                pool.shutdown(cancel_futures=True)
                raise SystemExit("stopped: under 20 GB free on / or /home")
            with log.open("a") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")


def disagree(rows, prior):
    """Reject a candidate whose pass/reject outcome differs from an earlier build's (flaky, never retried)."""
    for sha, old in prior.items():
        row = rows.get(sha)
        if row and row.get("reason") != "tests attempt a provider call" and (
                (old.get("reason") is None) != (row.get("reason") is None)):
            rows[sha] = {**row, "reason": "outcome differs from an earlier build", "earlier_reason": old.get("reason")}


def build(work, workers, runs, out=HERE, repo=ROOT, tip=TIP, prior=()):
    """Mine, evaluate, admit and write the packages, `tasks.jsonl` and `screening.jsonl` under `out`.

    `prior` names row logs of earlier builds; their outcomes are compared, not reused."""
    if not os.environ.get("PATH", "").startswith(str(GUARD)):
        raise SystemExit(f"put {GUARD} first on PATH")
    earlier = {r["commit"]: r for path in prior for r in map(json.loads, Path(path).read_text().splitlines())}
    rows = {}
    for widened in (False, True):  # the fix-wording filter is dropped once, when under DRAWN are admitted
        cands, mined = mine(repo, tip, fix_wording=not widened)
        evaluate_all(cands, rows, work, workers, runs)
        disagree(rows, earlier)
        admitted, skipped = admit(cands, rows)
        if len(admitted) >= DRAWN:
            break
    remove(out / "tasks")
    lines = []
    for i, cand in enumerate(admitted):
        tid, row = cand["commit"][:10], rows[cand["commit"]]
        shutil.copytree(work / "pkgs" / tid, out / "tasks" / tid)
        assert package_hash(out / "tasks" / tid) == row["package_sha256"]
        lines.append({"id": tid, "commit": cand["commit"], "base_commit": cand["parent"], "rank": cand["rank"],
                      "set": "drawn" if i < DRAWN else "reserve", "subject": cand["subject"],
                      "package_sha256": row["package_sha256"], "visible": row["visible"], "hidden": row["hidden"],
                      "source_files": cand["source_files"], "source_lines": cand["source_lines"],
                      "nontest_lines": cand["nontest_lines"], "test_files": cand["tests"]})
    (out / "tasks.jsonl").write_text("".join(json.dumps(line, sort_keys=True) + "\n" for line in lines))
    taken = {c["commit"] for c in admitted}
    screening = [*mined, *({**rows[c["commit"]], "rank": c["rank"], "reason": skipped.get(c["commit"])
                           or rows[c["commit"]].get("reason") or ("admitted" if c["commit"] in taken
                                                                  else "beyond the 40-task cap")}
                           for c in cands)]
    (out / "screening.jsonl").write_text("".join(json.dumps({"tip": tip, "widened": widened, **r}, sort_keys=True)
                                                 + "\n" for r in screening))
    print(f"admitted {len(admitted)} of {len(cands)} candidates; widened={widened}")


def verify(out=HERE):
    """Exit non-zero unless every listed package hashes as recorded and no other package exists."""
    lines = [json.loads(line) for line in (out / "tasks.jsonl").read_text().splitlines()]
    bad = [line["id"] for line in lines if package_hash(out / "tasks" / line["id"]) != line["package_sha256"]]
    extra = sorted({p.name for p in (out / "tasks").iterdir()} - {line["id"] for line in lines})
    if bad or extra:
        raise SystemExit(f"changed: {bad}; unlisted: {extra}")
    print(f"{len(lines)} packages verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--work", type=Path, required=True)
    b.add_argument("--workers", type=int, default=3)
    b.add_argument("--runs", type=int, default=RUNS)
    b.add_argument("--prior", action="append", default=[], help="rows.jsonl of an earlier build to compare")
    sub.add_parser("verify")
    args = parser.parse_args()
    build(args.work.resolve(), args.workers, args.runs, prior=args.prior) if args.cmd == "build" else verify()
