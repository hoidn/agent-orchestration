"""Seed-set task packages: mining, screening, packaging and the oracle (plan
`docs/plans/2026-11-11-seed-set-calibration-plan.md`, Step 1b and "Difficulty ladder"); `ladder.py` drives
them tier by tier and owns the manifest. Provider-free and mechanical. Rules, in order:
1. Mine (`mine`): non-merge commits reachable from `TIP`, author and committer dates >= `FLOOR`, no revert
   (made or suffered), fix-worded (`FIX_WORDS`) unless dropped, a changed `tests/**/test_*.py`, no deletion
   under `tests/`, 1-5 files and <= 200 lines under `orchestrator/` unless `limits` says otherwise, one
   commit per `git patch-id --stable` (oldest kept), a parent ignoring `.orchestrate/`; ordered by `rank`.
2. Statement (`statement_reason`, before any test runs): at least 80 characters, repeating no 20+ character
   line the change adds outside `tests/`. A candidate may carry its own `statement` (the ladder's tiers).
3. Screen (`_evaluate`): the change's touched test files once on the parent (its tests overlaid) and once
   on the change, in `git archive` trees. Fail-to-pass: a function new in the change, all instances passing
   or skipping (one passing) on it, some instance failing or uncollected on the parent. >= 2 needed; the
   first by `rank(node id)` is visible, the rest hidden.
4. Package (`write_package`, the layout of `experiments/compare/README.md`): `seed/` = the change's
   `tests/` files minus hidden functions (`ast` line ranges) plus `dev-check.json`; `hidden/` = the
   change's versions; `hidden_tests.txt` = hidden functions and touched test files; empty
   `anchors/<id>-base.diff`; `anchors/<id>-upstream.diff` = the change without `tests/`; `intent.txt` = the
   statement; `task.txt` adds the visible check and the hands-off rule.
5. Leaks: a hidden name (whole word) in the statement or the seeded tree.
6. Provider guard (`sandboxed`): fresh no-provider stubs first on `PATH` for every run; any logged line
   rejects the candidate ("tests attempt a provider call", argv in `note`).
7. Oracle (`oracle`), on `repos.build_candidate` and `summarize.hidden_failures`, `RUNS` times per side:
   base fails the visible check and every hidden function; with the upstream anchor applied the visible
   check passes and no hidden node fails, each hidden evaluation under `HIDDEN_LIMIT_SEC`. First deviation
   rejects (no retries). With `withheld`, the check-withheld form (`forms.py`) must pass it too, and its
   check must leave the clone exactly as it was.
8. Admit (`admit`), rank order: skip one whose `orchestrator/` file two admitted tasks already change; stop
   at the cap.

Depends on git, `experiments.compare.repos` and `.summarize`, pytest in `sys.executable`. Work trees under
`work` are deleted after each evaluation; evaluation stops under 20 GB free on `/` or `/home`.
"""

import ast
import contextlib
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


def mine(repo=ROOT, tip=TIP, fix_wording=True, limits=(MAX_SOURCE_FILES, MAX_SOURCE_LINES)):
    """([candidate dict], [reject dict]); candidates in rank order. Local git only. `limits`: (files, lines)
    under `orchestrator/`, or None for no size rule (the ladder assigns sizes to tiers)."""
    log = git("log", "--no-merges", f"--since={FLOOR}", "--reverse", "--no-renames", "--numstat",
              "--format=%x00%H%x01%P%x01%aI%x01%cI%x01%B%x02", tip, repo=repo)
    reverted = set(re.findall(r"This reverts commit ([0-9a-f]{40})", git("log", "--format=%B", tip, repo=repo)))
    seen_patch, kept, rejects = {}, [], []
    for chunk in log.split("\x00")[1:]:
        head, _, stat = chunk.partition("\x02")
        sha, parents, adate, cdate, message = head.split("\x01", 4)
        files = [(p, int(a) if a != "-" else 0, int(d) if d != "-" else 0)
                 for a, d, p in (line.split("\t", 2) for line in stat.strip().splitlines())]
        reason = screen_commit(repo, sha, adate, cdate, message, files, reverted, fix_wording, limits)
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
        kept.append({"repo": str(repo), "id": sha[:10], "commit": sha, "parent": parents.split()[0], "rank": rank(sha),
                     "subject": message.splitlines()[0], "message": message,
                     "tests": sorted(p for p, _, _ in files if p.startswith("tests/")),
                     "source_files": sorted(p for p, _, _ in source),
                     "source_lines": sum(a + d for _, a, d in source), "source_added": sum(a for _, a, _ in source),
                     "nontest_lines": sum(a + d for p, a, d in files if not p.startswith("tests/"))})
    return sorted(kept, key=lambda c: c["rank"]), rejects


def screen_commit(repo, sha, adate, cdate, message, files, reverted, fix_wording, limits=(5, 200)):
    """The first mining rule `sha` breaks, or None."""
    source = [f for f in files if f[0].startswith("orchestrator/")]
    if min(adate[:10], cdate[:10]) < FLOOR:
        return "dated before the floor"
    if not source:
        return "no change under orchestrator/"
    if limits and (len(source) > limits[0] or sum(a + d for _, a, d in source) > limits[1]):
        return f"over {limits[0]} files or {limits[1]} lines under orchestrator/"
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


def added_lines(diff):
    """The stripped lines of 20+ characters a diff adds."""
    lines = {line[1:].strip() for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")}
    return [line for line in lines if len(line) >= MIN_LEAK_LINE]


def statement_reason(text, added):
    if len(text.strip()) < MIN_TEXT:
        return "statement under 80 characters"
    if any(line in text for line in added):
        return "statement repeats a line the fix adds"
    return None


def leak_reason(text, hidden_names, seeded_tree):
    if any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text) for n in hidden_names):
        return "statement names a hidden test"
    grep = subprocess.run(["grep", "-rlwF", "--exclude-dir=.git", *[a for n in hidden_names for a in ("-e", n)],
                           str(seeded_tree)], capture_output=True, text=True)
    if grep.stdout.strip():
        return "hidden function name in the seeded tree: " + grep.stdout.split()[0].replace(f"{seeded_tree}/", "")
    return None


def write_package(cand, visible, hidden, pkg):
    """Write the harness package for `cand` into `pkg`; return the hidden function names."""
    repo, sha, parent, tid = Path(cand["repo"]), cand["commit"], cand["parent"], pkg.name
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
    text = cand.get("statement") or statement(cand["message"])
    (pkg / "intent.txt").write_text(text)
    (pkg / "task.txt").write_text(
        f"{text}\nVisible check: `{' '.join(argv)}` (the command in `dev-check.json`). It fails now and "
        "should pass once the change is made. Leave `dev-check.json` and the existing tests unchanged; "
        "you may add new tests.\n")
    (pkg / "base_commit").write_text(parent + "\n")
    return sorted({n.split("::")[-1] for n in hidden})


def visible_passes(pkg, clone):
    """(passed, seconds, None, output): the in-tree visible check, run as an agent would, in the clone."""
    argv = json.loads((pkg / "seed/dev-check.json").read_text())["argv"]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    started = time.monotonic()
    try:
        done = subprocess.run(argv, cwd=clone, env=env, capture_output=True, text=True, timeout=RUN_TIMEOUT_SEC)
        ok, output = done.returncode == 0, done.stdout + done.stderr
    except subprocess.TimeoutExpired:
        ok, output = False, ""
    return ok, round(time.monotonic() - started, 1), None, output[-4000:]


def oracle(repo, pkg, clone, runs=RUNS, visible=visible_passes, hidden_runs=True):
    """(reject reason or None, wall times, the base runs' visible-check outputs); the package's check on the
    harness's seeded candidate. `visible(pkg, clone)` -> (passed, seconds, reject reason or None, output)."""
    hidden = [n for n in (pkg / "hidden_tests.txt").read_text().split() if "::" in n]
    nodes = (pkg / "hidden_tests.txt").read_text().split()
    seeded = repos.build_candidate(repo, (pkg / "base_commit").read_text().strip(), pkg / "seed", clone)
    times, outputs = {"visible_base": [], "hidden_base": [], "visible_fix": [], "hidden_fix": []}, []

    def hidden_run(key, check):
        started = time.monotonic()
        failed = summarize.hidden_failures(clone, pkg, check, sys.executable)
        times[key].append(round(time.monotonic() - started, 1))
        return failed
    for side in ("base", "fix"):
        if side == "fix":
            git("apply", "--binary", str(pkg / "anchors" / f"{pkg.name}-upstream.diff"), repo=clone)
            # the base runs' bytecode is keyed on source size and mtime in whole seconds: a same-size fix applied
            # within that second would run the base's code
            remove(Path(os.environ["PYTHONPYCACHEPREFIX"], *clone.resolve().parts[1:]))
        for i in range(runs):
            ok, sec, broken, output = visible(pkg, clone)
            times[f"visible_{side}"].append(sec)
            outputs += [output] if side == "base" else []
            if broken:
                return f"{broken} (run {i + 1})", times, outputs
            if ok != (side == "fix"):
                return f"visible check {'fails on the fix' if ok is False else 'passes on the base'} (run {i + 1})", times, outputs
            if not hidden_runs:
                continue
            if side == "base" and set(hidden_run("hidden_base", hidden)) != set(hidden):
                return f"a hidden function passes on the base (run {i + 1})", times, outputs
            if side == "fix" and hidden_run("hidden_fix", nodes):
                return f"a hidden node fails on the fix (run {i + 1})", times, outputs
            if side == "fix" and times["hidden_fix"][-1] >= HIDDEN_LIMIT_SEC:
                return f"hidden evaluation {times['hidden_fix'][-1]} s, over {HIDDEN_LIMIT_SEC} s", times, outputs
    if repos.git(clone, "rev-parse", "HEAD") != seeded:
        return "seeded commit moved during the check", times, outputs
    return None, times, outputs


@contextlib.contextmanager
def sandboxed(work, tid):
    """A fresh box `work/tid` with its own TMPDIR and no-provider stubs first on PATH; yields
    (box, provider attempts callable). The caller's environment is restored and the box removed after."""
    box = work / tid
    remove(box)
    saved = dict(os.environ)  # restored after: TMPDIR and PATH below name the box, which is removed
    os.environ.update(TMPDIR=str(box / "tmp"), PYTHONPYCACHEPREFIX=str(box / "pycache"))  # as host.guarded
    os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
    tempfile.tempdir = None  # a reused worker process caches the previous task's (deleted) TMPDIR
    (box / "tmp").mkdir(parents=True)
    shutil.copytree(GUARD, box / "guard/no_provider")  # its stubs log to box/guard/no-provider.log
    os.environ["PATH"] = f"{box / 'guard/no_provider'}:{BASE_PATH}"
    try:
        yield box, lambda: provider_attempts(box / "guard/no-provider.log")
    finally:
        remove(box)
        os.environ.clear()
        os.environ.update(saved)
        tempfile.tempdir = None


def guarded(result, attempts):
    """`result` rejected when the stubs logged a provider call."""
    if not attempts:
        return result
    return {**result, "reason": "tests attempt a provider call", "note": attempts,
            "reason_without_attempt": result.get("reason")}


def evaluate(cand, work, runs=RUNS, withheld=None):
    """Screen, package and check one candidate under `work`; the screening row (package in work/pkgs/<id>).
    With `withheld` (a function writing the check-withheld form, `forms.withhold`), a passing package's
    withheld form is also built in work/pkgs/<id>-withheld and must pass the same oracle."""
    tid = cand["id"]
    row = {"id": tid, "commit": cand["commit"], "stage": "evaluate"}
    if not free_ok():
        return {**row, "reason": "disk: under 20 GB free", "stop": True}
    with sandboxed(work, tid) as (box, attempts):
        result = _evaluate(cand, box, work / "pkgs" / tid, runs)
        if withheld and result.get("reason") is None:
            result |= check_withheld(Path(cand["repo"]), work / "pkgs" / tid, work / "pkgs" / f"{tid}-withheld",
                                     box / "withheld-clone", runs, withheld)
        if withheld and result.get("reason") is None:  # the ladder's packages also pass the leak audit
            from experiments.seed_set import leak_audit
            shipped = [f"{tid}-withheld"] if cand.get("withheld_only") else [tid, f"{tid}-withheld"]
            failed = [f"{form}: {check}: {why}" for form in shipped for check, why in
                      leak_audit.audit(work / "pkgs" / form, box, cand.get("commits") or [cand["commit"]],
                                       Path(cand["repo"]))]
            result |= {"reason": f"leak audit: {failed[0]}"} if failed else {}
        return {**row, **guarded(result, attempts())}


def check_withheld(repo, pkg, out, clone, runs, withhold):
    """Build `pkg`'s check-withheld form at `out` and run the oracle on it; fields for the screening row."""
    from experiments.seed_set import forms
    remove(out)
    withhold(pkg, out)
    # hidden scoring overlays hidden/ (every seed test file) on a copy: inputs equal the in-tree form's
    reason, times, _ = oracle(repo, out, clone, runs, visible=forms.withheld_visible, hidden_runs=False)
    return {"reason": reason and f"check-withheld form: {reason}", "withheld_times": times,
            "withheld_sha256": None if reason else package_hash(out)}


def withheld_only(pkg, work, runs=RUNS, repo=ROOT):
    """The oracle on the check-withheld form of an existing in-tree package (the T3 tasks); a screening row."""
    from experiments.seed_set import forms
    tid = f"{pkg.name}-withheld"
    with sandboxed(work, tid) as (box, attempts):
        result = check_withheld(repo, pkg, work / "pkgs" / tid, box / "clone", runs, forms.withhold)
        return {"id": pkg.name, "stage": "withheld", **guarded(result, attempts())}  # audited by leak_audit.py


def provider_attempts(log):
    """The distinct argv lines (timestamp dropped) the no-provider stubs logged, in first-seen order."""
    lines = log.read_text().splitlines() if log.is_file() else []
    return list(dict.fromkeys(line.split(" ", 1)[1] for line in lines if " " in line))


def _evaluate(cand, box, pkg, runs):
    repo, sha, parent = Path(cand["repo"]), cand["commit"], cand["parent"]
    text = cand.get("statement") or statement(cand["message"])
    added = added_lines(git("diff", *DIFF, parent, sha, "--", ".", ":(exclude)tests", repo=repo))
    reason = statement_reason(text, added)
    if reason:
        return {"reason": reason}
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
    reason = leak_reason((pkg / "intent.txt").read_text(), names, box / "base")
    if reason:
        return {"reason": reason, "times": times, "visible": visible, "hidden": hidden}
    reason, oracle_times, outputs = oracle(repo, pkg, box / "clone", runs)
    return {"reason": reason, "times": {**times, **oracle_times}, "visible": visible, "hidden": hidden,
            "package_sha256": package_hash(pkg), "base_outputs": outputs, "clone": str(box / "clone")}


def show(repo, spec):
    """The file at `spec` ('commit:path'), or '' when absent."""
    done = subprocess.run(["git", "-C", str(repo), "show", spec], capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else ""


def admit(cands, rows, cap=MAX_TASKS, uses=None):
    """Rank-order admission: (admitted candidates, {id: skip reason}) under the share and size caps.
    `uses` counts each source file's admitted tasks so far (updated in place)."""
    admitted, skipped, uses = [], {}, {} if uses is None else uses
    for cand in cands:
        row = rows.get(cand["id"])
        if row is None or row.get("reason") or len(admitted) >= cap:
            continue
        if any(uses.get(f, 0) >= MAX_SHARE for f in cand["source_files"]):
            skipped[cand["id"]] = "source file already in two admitted tasks"
            continue
        for f in cand["source_files"]:
            uses[f] = uses.get(f, 0) + 1
        admitted.append(cand)
    return admitted, skipped


def evaluate_all(cands, rows, work, workers, runs, withheld=None):
    """Evaluate the candidates without a row (keyed by id), in rank order, `workers` at a time; stop on low disk.

    Every finished row is appended to `work/rows.jsonl` and reused after a restart, so an apparatus
    crash never re-runs (retries) a recorded evaluation."""
    log = work / "rows.jsonl"
    if log.is_file():
        rows.update((r["id"], r) for r in map(json.loads, log.read_text().splitlines()))
    todo = [c for c in cands if c["id"] not in rows]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for cand, row in zip(todo, pool.map(evaluate, todo, [work] * len(todo), [runs] * len(todo),
                                            [withheld] * len(todo))):
            rows[cand["id"]] = row
            print(f"{cand['id']} {row.get('reason') or 'PASS'} {row.get('times', {})}", flush=True)
            if row.get("stop"):
                pool.shutdown(cancel_futures=True)
                raise SystemExit("stopped: under 20 GB free on / or /home")
            with log.open("a") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
