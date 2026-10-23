"""The blind scoring pool (design D4, D6, D8; rulings R18, R20, R21, R22) and its integrity checks.

pool(task, criterion, out, judges, runs) builds P = out: P/clones/<id>/ applied-patch clones (what the
judges read; P/clones is traversable but not listable), P/judges/<16 hex>/ one working and state
directory per judge, and P/records/ with mapping.json (read by summarize.py and verify_pool only),
patches/<id>.diff, score-inputs-<judge>.json, score-<judge>.sh, resume-<judge>.sh and judges/<judge>/
(the judge's shim call records and scan.json). P and P/judges stay listable: the runtime opens every
ancestor of a judge's working and state directory with O_RDONLY. Judges run behind the shims like
agents. verify_pool(out) restores any clone a judge changed; scan_judge and adjudicate_judge are the
judge-side contamination scan and verdict. Standard library only.
"""

import json
import random
import re
import secrets
import time
import tempfile
from collections.abc import Mapping
from pathlib import Path

try:
    from . import scan as contamination
    from .repos import (
        HIDDEN_DIR, build_candidate, build_review_candidate, dump, git, guard, review_exclusions,
        load, main_checkout, patch_of, runtime_commit, sha256_file, shim_commands, visible_in_sandbox,
    )
except ImportError:
    import scan as contamination
    from repos import (
        HIDDEN_DIR, build_candidate, build_review_candidate, dump, git, guard, review_exclusions,
        load, main_checkout, patch_of, runtime_commit, sha256_file, shim_commands, visible_in_sandbox,
    )

STRIPPED = ("docs/design/", "artifacts/")  # D8: removed from every pooled patch
DEFAULT_RUBRIC = {"workflow": "score.orc", "entry": "score::score",
                  "criteria": ["root_cause", "scope", "generality", "layering"], "reference": None}
CONTROL_ROLES = ("upstream", "stub", "mutant")


def control_means(criterion):
    """Only the named prospective rule changes historical calibration semantics."""
    value = criterion if isinstance(criterion, Mapping) else load(criterion)
    rules = value.get("calibration", {})
    if "rule" not in rules:
        return False
    if (rules != {"rule": "control-means-v1", "margin": 1, "error_rate": 0}
            or type(rules.get("margin")) not in (int, float)
            or type(rules.get("error_rate")) not in (int, float)):
        raise SystemExit("unsupported calibration rule or control-means-v1 parameters")
    return True


def task_difficulty(criterion):
    """Only an explicit natural-solution calibration may omit package controls."""
    value = criterion if isinstance(criterion, Mapping) else load(criterion)
    if value.get("calibration_kind") != "task_difficulty":
        return False
    if (value.get("purpose") != "calibration" or value.get("anchors") != []
            or "calibration" in value or rubric(value)["reference"] is not None):
        raise SystemExit("task-difficulty calibration requires no anchors, reference or calibration block")
    return True


def anchor_paths(task, criterion=None):
    """Prospective pools contain their three declared controls; legacy pools keep every anchor."""
    task = Path(task)
    if criterion is not None and task_difficulty(criterion):
        return []
    if criterion is None or not control_means(criterion):
        return sorted((task / "anchors").glob("*.diff"))
    value = criterion if isinstance(criterion, Mapping) else load(criterion)
    roles = value["anchors"][task.name]
    if (set(roles) != set(CONTROL_ROLES) or not all(isinstance(label, str) and label
            and Path(label).name == label for label in roles.values()) or len(set(roles.values())) != 3):
        raise SystemExit("control-means-v1 requires exactly three distinct declared anchor roles")
    paths = [task / "anchors" / f"{roles[role]}.diff" for role in CONTROL_ROLES]
    if not all(path.is_file() for path in paths):
        raise SystemExit("missing declared control-means-v1 anchor patch")
    return paths


def rubric(criterion):
    """Historical rubric descriptions are metadata; only mappings select a workflow."""
    value = criterion if isinstance(criterion, Mapping) else load(criterion)
    selected = value.get("rubric", DEFAULT_RUBRIC)
    if isinstance(selected, str):
        return DEFAULT_RUBRIC
    if not isinstance(selected, Mapping):
        raise SystemExit("rubric must be a selector mapping or a historical description")
    return selected


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
    rest = [(path, rec, ["final"]) for arm, runs in usable.items()
            if arm not in ("direct_task", "best_of_n", "reviewed_change") for path, rec in runs
            if "final" in rec.get("patches", {})]
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
    return (Path(records or ".") / record["patches"][label]).read_bytes()


def add_clone(out, task, ref, patch, entry, review_exclude=()):
    """Build one applied-patch clone under a random id; record its patch; return (id, mapping entry)."""
    cid = secrets.token_hex(4)
    clone = out / "clones" / cid
    kept, entry["stripped"] = strip(patch)
    base = ref["compare_base"]
    if review_exclude:
        if kept != patch:
            raise SystemExit("review environment requires the exact original patch, without D8 stripping")
        base = build_review_candidate(ref["runtime"], ref["base"], task / "seed", clone,
                                      base, review_exclude, patch)
        entry["review_base"] = base
    elif build_candidate(ref["runtime"], ref["base"], task / "seed", clone) != base:
        raise SystemExit(f"{clone}: seeded commit differs from the runs' {base}")
    if kept:
        git(clone, "apply", "--binary", "-", stdin=kept)
    recorded = patch_of(clone, base)
    if review_exclude and recorded != patch:
        raise SystemExit("review diff differs from the exact original patch")
    (out / "records" / "patches" / f"{cid}.diff").write_bytes(recorded)
    return cid, entry


def exclusion(scan, calls, adjudicate):
    """Why a scanned run or judge is excluded (Fable answers, or a contaminated verdict), or None. Refuses a scan that
    covers another number of calls than were made (a resume after it), and hits without a verdict (R20)."""
    if scan["calls"] != calls:
        raise SystemExit(f"the scan covers {scan['calls']} calls but {calls} were made: {adjudicate} --hash SOL")
    hits, verdict = scan["hits"], scan["verdict"]
    if contamination.model_policy(hits):
        return contamination.model_policy(hits)
    if hits and verdict is None:
        raise SystemExit(f"{len(hits)} scan hits and no verdict: {adjudicate} --verdict contaminated|cleared "
                         "--reason TEXT")
    return f"contaminated: {verdict['reason']}" if verdict and verdict["verdict"] == "contaminated" else None


def pool_runs(records):
    """Mapping rows for every run and the usable runs per arm; refuse a run not collected or not scanned."""
    rows, usable = {}, {}
    for path, rec in records.items():
        if "outcome" not in rec or "scan" not in rec:
            raise SystemExit(f"{path} has not been {'collected' if 'outcome' not in rec else 'scanned'}")
        excluded = exclusion(rec["scan"], rec["calls"], f"prepare.py scan --run {path}")
        rows[path] = {k: rec[k] for k in ROW_KEYS} | {
            "scan_hits": len(rec["scan"]["hits"]), "verdict": rec["scan"]["verdict"], "excluded": excluded}
        if rec["outcome"] == "completed" and not excluded:
            usable.setdefault(rec["arm"], []).append((path, rec))
    return rows, usable


def natural_intake(criterion):
    """A frozen amendment selects raw terminal snapshots uniformly, including delivery failures."""
    value = criterion if isinstance(criterion, Mapping) else load(criterion)
    rule = value.get("natural_attempt_intake")
    if rule is None:
        return False
    if rule != "terminal-single-call-patch-v1" or not task_difficulty(value):
        raise SystemExit("task-difficulty natural intake requires terminal-single-call-patch-v1")
    return True


def natural_attempt(records, receipt_path, expected_model):
    """Return an original mapping row and a read-only pooling view; never repair delivery artifacts."""
    try:
        from .prepare import finished_memo, outcome_of, paired_calls
    except ImportError:
        from prepare import finished_memo, outcome_of, paired_calls
    records, receipt_path = Path(records).resolve(), Path(receipt_path).resolve()
    record_path = records / "record.json"
    record = load(record_path)
    memo, rows = finished_memo(record["state_root"])
    terminal = rows[-1]
    if (terminal["outcome"] not in ("completed", "failed") or record.get("calls") != 1
            or len(record["candidates"]) != 1 or len(paired_calls(records, rows)) != 1
            or any(record.get(key) != value for key, value in outcome_of(record, terminal, []).items())):
        raise SystemExit("task-difficulty intake needs one original terminal attempt and one captured candidate")
    patch = records / "calls/1" / f"patch-{Path(record['candidates'][0]).name}.diff"
    if not patch.is_file():
        raise SystemExit("task-difficulty terminal attempt has no captured raw patch")
    mapped, _ = pool_runs({str(records): record})
    row = mapped[str(records)]
    if row["excluded"]:
        raise SystemExit("task-difficulty terminal attempt is excluded")
    receipt = load(receipt_path)
    receipts, natives = receipt.get("receipt_usage", []), receipt.get("native_session_paths", [])
    if (receipt.get("provider_calls") != 1 or len(receipts) != 1 or len(natives) != 1
            or receipts[0].get("provider") != "codex" or receipts[0].get("call_id") != "1"
            or receipts[0].get("status") != "complete" or not receipts[0].get("usage")):
        raise SystemExit("task-difficulty intake needs exactly one positive native Codex receipt")
    native = Path(natives[0]).resolve()
    native_rows = [json.loads(line) for line in native.read_text().splitlines()]
    contexts = [item["payload"] for item in native_rows if item.get("type") == "turn_context"]
    header = native_rows[0] if native_rows else {}
    if (header.get("type") != "session_meta"
            or not Path(header.get("payload", {}).get("cwd", "/missing")).is_relative_to(record["tree"])
            or not contexts or any(context.get("model") != expected_model or context.get("effort") != "high"
                                   for context in contexts)):
        raise SystemExit("task-difficulty native receipt belongs to another attempt or model")
    for usage in receipts[0]["usage"]:
        provenance, tokens = usage.get("provenance", {}), usage.get("charge_tokens", {})
        if (usage.get("model") != expected_model or provenance.get("model_source") != "turn_context.model"
                or provenance.get("complete_native_transcript") is not True
                or provenance.get("session_sha256") != "sha256:" + sha256_file(native)
                or not isinstance(tokens, dict) or not tokens
                or any(type(n) is not int or n < 0 for n in tokens.values()) or sum(tokens.values()) <= 0):
            raise SystemExit("task-difficulty intake has no positive exact-model receipt for this native snapshot")
    row["capture"] = {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in (
        ("record", record_path), ("memo", memo.resolve()), ("patch", patch), ("receipt", receipt_path), ("native", native))}
    return row, record | {"patches": {"final": str(patch)}}


def build_batches(out, task, ref, batches, rule, criterion=None, review_exclude=()):
    clones, members, references = {}, [], []
    anchors = anchor_paths(task, criterion)
    for batch in batches:
        made = [add_clone(out, task, ref, patch_bytes(path, rec, labels[0]),
                          {"run": path, "arm": rec["arm"], "labels": labels}, review_exclude) for path, rec, labels in batch]
        made += [add_clone(out, task, ref, a.read_bytes(), {"run": None, "arm": "anchor", "labels": [a.stem]}, review_exclude)
                 for a in anchors]
        clones.update(made)
        members.append([cid for cid, _ in made])
        if rule["reference"]:
            patch = task / "anchors" / f"{task.name}-{rule['reference']}.diff"
            cid, entry = add_clone(out, task, ref, patch.read_bytes(),
                                   {"run": None, "arm": "reference", "labels": ["reference"]}, review_exclude)
            clones[cid] = entry
            references.append(cid)
    return clones, members, references


def pool(task, criterion, out, judges, runs):
    """Build the blind scoring pool, mapping.json, and one scoring inputs file and command per judge."""
    task, out = task.resolve(), out.resolve()
    records = {str(Path(r).resolve()): load(Path(r) / "record.json") for r in runs}
    ref = next(iter(records.values()))
    if {(r["task"], r["compare_base"]) for r in records.values()} != {(str(task), ref["compare_base"])}:
        raise SystemExit("runs in one pool must share the task and the seeded commit")
    rows, usable = pool_runs(records)
    batches = compose(usable)
    if not batches:
        raise SystemExit("no completed, uncontaminated run to pool")
    return write_pool(task, criterion, out, judges, ref, rows, batches)


def write_pool(task, criterion, out, judges, ref, rows, batches, *, qualification=None, review_exclude=()):
    """Write either caller's pool, preserving its verified structural proof when supplied."""
    task, out = Path(task).resolve(), Path(out).resolve()
    review_exclude = review_exclusions(review_exclude)
    guard(Path(ref["main"]), out)
    visible_in_sandbox(out)
    commit, rule = runtime_commit(ref["runtime"]), rubric(criterion)
    overhead = len(anchor_paths(task, criterion)) + bool(rule["reference"])
    if not batches or any(len(batch) + overhead > 10 for batch in batches):
        raise SystemExit("a pool needs nonempty batches with at most ten repositories including anchors and reference")
    for directory in (out / "clones", out / "judges", out / "records" / "patches"):
        directory.mkdir(parents=True)
    clones, members, references = build_batches(out, task, ref, batches, rule, criterion, review_exclude)
    compare_base = ref["compare_base"]
    if review_exclude:
        bases = {entry.pop("review_base") for entry in clones.values()}
        if len(bases) != 1:
            raise SystemExit("review clones do not share one baseline")
        compare_base = bases.pop()
    default = Path(ref["runtime"]) / "experiments/compare/score.providers.json"
    mapping = {"task": str(task), "criterion_sha256": sha256_file(criterion), "compare_base": compare_base,
               "main": ref["main"], "runtime": ref["runtime"], "runtime_commit": commit, "created_at": time.time(),
               "judges": {name: {"dir": secrets.token_hex(8), "providers": str(Path(providers or default).resolve())}
                          for name, _, providers in (spec.partition("=") for spec in judges)},
               "runs": rows, "clones": clones, "batches": members, "rubric": rule}
    if references:
        mapping["references"] = references
    if qualification is not None:
        mapping["qualification"] = qualification
    if review_exclude:
        mapping["review"] = {"source_compare_base": ref["compare_base"], "excluded_paths": list(review_exclude)}
    dump(out / "records" / "mapping.json", mapping)
    write_score_inputs(out, mapping, (task / "intent.txt").read_text(), Path(ref["runtime"]))
    (out / "clones").chmod(HIDDEN_DIR)
    print(f"# {len(clones)} clones in {len(members)} batches; run the judges one after another, "
          f"each followed by: prepare.py verify-pool --pool {out}")
    return mapping


def applicable(runtime, base, seed, diffs):
    """Keep patches that apply to the seeded base; each check leaves that base unchanged."""
    kept = []
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "candidate"
        build_candidate(runtime, base, seed, clone)
        for diff in diffs:
            try:
                git(clone, "apply", "--check", str(Path(diff).resolve()))
            except SystemExit:
                continue
            kept.append(diff)
    return kept


def pool_from_diffs(task, criterion, out, judges, runtime, fillers, batches, per_batch, min_per_batch, filler_seed):
    """Deal applicable recorded patches without replacement into deterministic calibration batches."""
    task, runtime = Path(task).resolve(), Path(runtime).resolve()
    rule = rubric(criterion)
    capacity = 10 - len(anchor_paths(task, criterion)) - bool(rule["reference"])
    if not 1 <= batches <= 24 or not 1 <= min_per_batch <= per_batch <= capacity:
        raise SystemExit("invalid batch count or filler capacity/minimum")
    fillers = [Path(path).resolve() for path in fillers]
    if len({sha256_file(path) for path in fillers}) != len(fillers):
        raise SystemExit("calibration fillers must be distinct patches, without duplicates")
    runtime_commit(runtime)
    base = git(runtime, "rev-parse", "--verify", (task / "base_commit").read_text().strip() + "^{commit}")
    kept = applicable(runtime, base, task / "seed", fillers)
    for path in fillers:
        print(f"{'applicable' if path in kept else 'refused (does not apply)'}: {path}")
    members = diff_batches(kept, batches, per_batch, min_per_batch, filler_seed)
    with tempfile.TemporaryDirectory() as tmp:
        compare_base = build_candidate(runtime, base, task / "seed", Path(tmp) / "candidate")
    ref = {"main": str(main_checkout(runtime)), "runtime": str(runtime), "base": base, "compare_base": compare_base}
    return write_pool(task, criterion, out, judges, ref, {}, members)


def diff_batches(fillers, batches, per_batch, minimum, seed):
    random.Random(seed).shuffle(fillers)
    dealt = [fillers[:batches * per_batch][index::batches] for index in range(batches)]
    if any(len(batch) < minimum for batch in dealt):
        raise SystemExit("not enough applicable fillers to meet every batch minimum")
    return [[(None, {"arm": "filler", "patches": {path.stem: str(path)}}, [path.stem]) for path in batch]
            for batch in dealt]


def write_score_inputs(out, mapping, intent, runtime):
    """Per judge: score.orc inputs with that judge's random clone order, a working and state directory of
    its own, and the command and resume script behind the shims (records/score-<judge>.sh, resume-<judge>.sh)."""
    rng, rule = random.SystemRandom(), rubric(mapping)
    for judge, info in mapping["judges"].items():
        inputs, home = out / "records" / f"score-inputs-{judge}.json", out / "judges" / info["dir"]
        batches = [{"clones": [str(out / "clones" / cid) for cid in rng.sample(ids, len(ids))]}
                   for ids in mapping["batches"]]
        for batch, cid in zip(batches, mapping.get("references", [])):
            batch["reference"] = str(out / "clones" / cid)
        dump(inputs, {"batches": batches, "intent": intent,
                      "criterion_sha256": mapping["criterion_sha256"], "judge_model": judge})
        (home / "tmp").mkdir(parents=True)  # the judge's /tmp inside the shims' sandbox
        (out / "records" / "judges" / judge).mkdir(parents=True)
        env = {"COMPARE_ROOT": out / "records" / "judges" / judge, "COMPARE_TREE": home,
               "COMPARE_BASE": mapping["compare_base"]}
        if judge in contamination.CODEX_MODELS:
            env["COMPARE_CODEX_MODELS"] = judge
        command, resume = shim_commands(
            home, runtime, env,
            [str(runtime / "experiments/compare" / rule["workflow"]), "--entry-workflow", rule["entry"],
             "--source-root", str(runtime / "experiments/compare"), "--provider-externs-file", info["providers"],
             "--input-file", str(inputs)], home / "state")
        (out / "records" / f"score-{judge}.sh").write_text(command + "\n")
        (out / "records" / f"resume-{judge}.sh").write_text(resume + "\n")
        print(command)


def scan_judge(out, judge, solution, home=None):
    """Record every contamination hit of a judge's calls and sessions in records/judges/<judge>/scan.json."""
    out, home = out.resolve(), home or Path.home()
    mapping = load(out / "records" / "mapping.json")
    workdir, calls_root = out / "judges" / mapping["judges"][judge]["dir"], out / "records" / "judges" / judge
    run_roots = sorted({str(Path(run).parents[1]) for run in mapping["runs"]})
    agent_roots = sorted({str(Path(run).parents[2] / "agents") for run in mapping["runs"]})
    compiled = contamination.patterns(
        main=mapping["main"], runtime=mapping["runtime"], solution=solution, home=home,
        others=contamination.siblings(workdir),
        roots=[("this pool's records", out / "records"), *(("run records", root) for root in run_roots),
               *(("agents' trees", root) for root in agent_roots)])
    compiled["judge ran tests"] = contamination.JUDGE_TESTS
    expected = judge if judge in contamination.CODEX_MODELS else "gpt-5.6-terra"
    hits = contamination.find_hits(calls_root, workdir, mapping["created_at"], home, compiled,
                                   expected_codex_model=expected)
    dump(calls_root / "scan.json", {"solution": solution, "hits": hits, "verdict": None,
                                    "calls": len(list((calls_root / "calls").glob("*")))})
    for hit in hits:
        print(f"{hit['file']}:{hit['line']}: {hit['pattern']}: {hit['text']}")
    return hits


def adjudicate_judge(out, judge, verdict, reason):
    path = out.resolve() / "records" / "judges" / judge / "scan.json"
    if not path.is_file():
        raise SystemExit(f"judge {judge} has not been scanned")
    scan = load(path)
    contamination.refuse_clearing(verdict, scan["hits"], f"judge {judge}")
    dump(path, scan | {"verdict": {"verdict": verdict, "reason": reason, "hits": len(scan["hits"])}})


def changed_paths(recorded, current):
    old, new = (dict((paths[-1] if paths else b"", part) for paths, part in sections(p)) for p in (recorded, current))
    return sorted(p.decode(errors="replace") for p in set(old) | set(new) if old.get(p) != new.get(p))


def verify_pool(out):
    """Restore every clone whose HEAD or patch differs from the one recorded when the pool was built, or
    that holds an ignored file (patches leave out ignored paths such as artifacts/ and .orchestrate/)."""
    out = out.resolve()
    mapping = load(out / "records" / "mapping.json")
    base, changed = mapping["compare_base"], 0
    for cid in mapping["clones"]:
        clone, recorded_file = out / "clones" / cid, out / "records" / "patches" / f"{cid}.diff"
        recorded = recorded_file.read_bytes()
        head, current = git(clone, "rev-parse", "HEAD"), patch_of(clone, base)
        ignored = [line[3:] for line in git(clone, "status", "--porcelain", "--ignored").splitlines()
                   if line.startswith("!! ")]
        if head == base and current == recorded and not ignored:
            continue
        changed += 1
        paths = changed_paths(recorded, current) + [f"{path} (ignored)" for path in ignored]
        print(f"{cid}: HEAD {head[:12]}, changed {', '.join(paths) or 'nothing'}")
        git(clone, "reset", "-q", "--hard", base)
        git(clone, "clean", "-q", "-f", "-d", "-x")
        if recorded:
            git(clone, "apply", "--binary", str(recorded_file))
        patch_of(clone, base)
    if changed:
        raise SystemExit(f"{changed} clone(s) differed from their recorded patch and were restored")
    print(f"{len(mapping['clones'])} clones match their recorded patches")
