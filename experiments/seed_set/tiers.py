"""Build the seed-set difficulty ladder's task packages and their manifest (plan
`docs/plans/2026-11-11-seed-set-calibration-plan.md`, "Difficulty ladder", "Check-withheld form" and "If the
whole ladder misses"). `ladder.py` holds the probe's rules; this module builds the tasks they choose from.

Tiers differ by design; every task is a natural change from this repository with its own tests, admitted by
`build_tasks` (statement, screening, split, leak, provider guard, oracle in both forms, leak audit). Sizes
count files and added plus deleted lines under `orchestrator/` (`tier_of`, first match wins):

| Tier | Definition | Statement (`tier_statement`) | Forms |
| T5 | a `feat` commit, or a run (`topic_runs`), adding 300-999 source lines | message; for a run its subjects | withheld |
| T6 | a run adding 1,000-3,000 source lines | the run's subjects in order | withheld |
| T4 | 6-15 files or 200-600 lines (at most 15 files and 600 lines) | message | both |
| T1 | one file, at most 20 lines | message plus "The change is in <file>." | both |
| T2 | at most two files and 60 lines | short commit message plus the names of the files to change (a body-less one under 80 characters; recorded deviation from the plan, coordinator ruling on review2 M8: with the message alone every T2 statement falls under the 80-character floor) | both |
| T3 | the tasks of the first build (`tasks.jsonl`), unchanged; one failing the leak audit gets `rejected` | message | both |
| T0 | a variant of each T1 package whose statement also quotes the visible check's failing `E` lines, identical in all five oracle base runs | | in-tree |

A run is a maximal sequence of two or more consecutive first-parent non-merge commits whose subjects share one
conventional scope (`type(scope):`), at least one of them a `feat`; it is squashed: the base is the first
commit's parent, the reference the last commit. A single commit inside such a run is not a T5 candidate.
T1 and T2 take fix-worded commits first and drop that filter once if fewer than `CAP` are admitted; T4 to T6
never use it. Each tier is evaluated in seed order until `CAP` are admitted; at most two tasks of a tier share
a source file. A rejection recorded by an earlier build that does not depend on the statement (screening,
split, oracle, provider guard) is carried, never re-run; a task that passed then and fails such a check now is
rejected as "outcome differs from an earlier build". The first four tasks of each tier in seed order are its
probe tasks.

Outputs: `tasks/<id>/` (in-tree), `tasks/<id>-withheld/`, `tasks/<id>-t0/`; `tasks.jsonl` (one row per task,
with tier, form and both forms' sha256; `verify` rechecks them); `ladder_screening.jsonl` (every commit and run
considered, its tier and reason, and wall times). `rebuild --tier T` evaluates one tier again and replaces only
its packages, rows and screening records (a T2 rebuild moves the smoke to the new T2's first task that is not a
probe task, ruling 1). Depends on `build_tasks`, `forms` and git.
"""

import argparse
import json
import os
import re
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from experiments.seed_set import anchors, build_tasks as b, forms, leak_audit

CAP, PROBE = 12, 4
T5_ADDED, T6_ADDED = (300, 999), (1000, 3000)
FEATURE = re.compile(r"^feat(\([^)]*\))?!?:")
SCOPE = re.compile(r"^\w+\(([^)]+)\)!?:")
ORDER = ("T1", "T2", "T4", "T5", "T6")
WITHHELD_ONLY = ("T5", "T6")
PASSED = (None, "admitted", "source file already in two admitted tasks", "beyond the 40-task cap", "beyond the tier's cap",
          "not evaluated: tier full")  # the last two: a ladder screening read as prior
NEW_CHECKS = ("check-withheld form", "tests attempt a provider call", "leak audit")
CHUNK = 6


def tier_of(files, lines, added, subject, run=False):
    """The tier of a change by its source size and kind, or None when it fits none."""
    if run:
        return "T6" if T6_ADDED[0] <= added <= T6_ADDED[1] else "T5" if T5_ADDED[0] <= added <= T5_ADDED[1] else None
    if FEATURE.match(subject) and T5_ADDED[0] <= added <= T5_ADDED[1]:
        return "T5"
    if files <= 15 and lines <= 600 and (files >= 6 or lines >= 200):
        return "T4"
    if files == 1 and lines <= 20:
        return "T1"
    if files <= 2 and lines <= 60:
        return "T2"
    return "T3" if files <= 5 and lines <= 200 else None


def tier_statement(tier, cand):
    text = cand.get("statement") or b.statement(cand["message"])
    if tier == "T1":
        return text + f"\nThe change is in {cand['source_files'][0]}.\n"
    if tier == "T2" and len(text.strip()) < b.MIN_TEXT and "\n" not in text.strip():
        return text + f"\nThe change is in {' and '.join(cand['source_files'])}.\n"
    return text


def topic_runs(repo=b.ROOT, tip=b.TIP):
    """Maximal runs (lists of (sha, parent, author date, committer date, subject)) of >= 2 consecutive
    first-parent non-merge commits since FLOOR sharing one conventional scope, at least one a `feat`."""
    log = b.git("log", "--first-parent", f"--since={b.FLOOR}", "--reverse", "--format=%H%x01%P%x01%aI%x01%cI%x01%s",
                tip, repo=repo)
    groups, current, scope = [], [], None
    for line in log.splitlines():
        sha, parents, adate, cdate, subject = line.split("\x01", 4)
        found = SCOPE.match(subject)
        key = found.group(1) if found and len(parents.split()) == 1 else None
        if key is None or key != scope:
            groups.append(current)
            current = []
        if key:
            current.append((sha, parents, adate, cdate, subject))
        scope = key
    groups.append(current)
    return [g for g in groups if len(g) >= 2 and any(FEATURE.match(c[4]) for c in g)]


def numstat(repo, parent, last):
    return [(p, int(a) if a != "-" else 0, int(d) if d != "-" else 0) for a, d, p in
            (line.split("\t", 2) for line in b.git("diff", "--numstat", "--no-renames", parent, last,
                                                   repo=repo).splitlines())]


def run_candidate(repo, run):
    """(candidate dict, None) for a squashed run, or (None, reject reason)."""
    first, last, parent = run[0][0], run[-1][0], run[0][1]
    files = numstat(repo, parent, last)
    source = [f for f in files if f[0].startswith("orchestrator/")]
    added = sum(a for _, a, _ in source)
    if min(c[2][:10] for c in run) < b.FLOOR or min(c[3][:10] for c in run) < b.FLOOR:
        return None, "dated before the floor"
    if any(c[4].startswith("Revert") for c in run):
        return None, "revert or reverted"
    if not any(b.TEST_FILE.match(p) for p, _, _ in files):
        return None, "no tests/**/test_*.py change"
    if b.git("diff", "--no-renames", "--diff-filter=D", "--name-only", parent, last, "--", "tests", repo=repo):
        return None, "deletes a file under tests/"
    if ".orchestrate" not in b.show(repo, f"{parent}:.gitignore"):
        return None, "base does not ignore .orchestrate/"
    tier = tier_of(len(source), sum(a + d for _, a, d in source), added, run[0][4], run=True)
    if tier is None:
        return None, f"run adds {added} source lines, outside 300-3,000"
    rid = f"{first[:7]}-{last[:7]}"
    return {"repo": str(repo), "id": rid, "commit": last, "commits": [c[0] for c in run], "parent": parent,
            "rank": b.rank(rid), "subject": run[-1][4], "message": "\n".join(c[4] for c in run),
            "statement": "".join(c[4] + "\n" for c in run), "tier": tier,
            "tests": sorted(p for p, _, _ in files if p.startswith("tests/")),
            "source_files": sorted(p for p, _, _ in source), "source_lines": sum(a + d for _, a, d in source),
            "source_added": added, "nontest_lines": sum(a + d for p, a, d in files if not p.startswith("tests/"))
            }, None


def carried(row):
    """An earlier build's rejection that does not depend on the statement, or None."""
    reason = row.get("reason")
    if reason in PASSED or reason.startswith(("statement", "disk", "outcome differs")):
        return None
    return reason


def load_prior(paths):
    """{sha10: earlier row}, later files taking precedence; rows of `screening.jsonl` or a `rows.jsonl`."""
    prior = {}
    for path in paths:
        for row in map(json.loads, Path(path).read_text().splitlines()):
            if row.get("stage") in ("evaluate", None) and "commit" in row:
                prior[row["commit"][:10]] = row
    return prior


def evaluate_tier(cands, rows, prior, work, workers, runs):
    """Evaluate `cands` (rank order) in chunks until CAP are admitted; (admitted, skipped)."""
    admitted, skipped = [], {}
    for start in range(0, len(cands), CHUNK):
        chunk = cands[start:start + CHUNK]
        for cand in chunk:
            earlier = prior.get(cand["id"]) if "commits" not in cand else None
            if earlier and carried(earlier) and cand["id"] not in rows:
                rows[cand["id"]] = {"id": cand["id"], "commit": cand["commit"], "stage": "carried",
                                    "reason": f"{carried(earlier)} (recorded by an earlier build)"}
        b.evaluate_all(chunk, rows, work, workers, runs, withheld=forms.withhold)
        for cand in chunk:
            earlier, row = prior.get(cand["id"]), rows[cand["id"]]
            if earlier and earlier.get("reason") in PASSED and carried(row) and row.get("stage") != "carried" \
                    and not row["reason"].startswith(NEW_CHECKS):
                rows[cand["id"]] = {**row, "reason": "outcome differs from an earlier build",
                                    "earlier_reason": earlier.get("reason")}
        admitted, skipped = b.admit(cands[:start + CHUNK], rows, cap=CAP, uses={})
        if len(admitted) >= CAP:
            break
    return admitted, skipped


def t0_variant(cand, row, out):
    """(T0 package id, None) for a T1 task, or (None, reason); the hint is the base runs' `E` lines."""
    seen = {tuple(forms.failure_lines(o, row["clone"])) for o in row["base_outputs"]}
    if len(seen) != 1 or not next(iter(seen)):
        return None, "the base runs' failure lines differ or are empty"
    tid = f"{cand['id']}-t0"
    b.remove(out / tid)
    intent = forms.hinted(out / cand["id"], out / tid, list(next(iter(seen))))
    added = b.added_lines(b.git("diff", *b.DIFF, cand["parent"], cand["commit"], "--", ".", ":(exclude)tests",
                                repo=Path(cand["repo"])))
    reason = b.statement_reason(intent, added) or b.leak_reason(intent, [n.split("::")[-1] for n in row["hidden"]],
                                                              out / tid / "seed")
    if reason:
        b.remove(out / tid)
        return None, reason
    return tid, None


def manifest_row(cand, row, tier, index, widened):
    tid = cand["id"]
    line = {"id": tid, "commit": cand["commit"], "base_commit": cand["parent"], "rank": cand["rank"],
            "set": "ladder", "tier": tier, "probe": index < PROBE, "subject": cand["subject"],
            "visible": row["visible"], "hidden": row["hidden"], "source_files": cand["source_files"],
            "source_lines": cand["source_lines"], "source_added": cand["source_added"],
            "nontest_lines": cand["nontest_lines"], "test_files": cand["tests"], "widened": widened,
            "form": "in_tree", "package_sha256": row["package_sha256"],
            "withheld_id": f"{tid}-withheld", "withheld_sha256": row["withheld_sha256"]}
    if "commits" in cand:
        line["commits"] = cand["commits"]
    if tier in WITHHELD_ONLY:
        line |= {"id": f"{tid}-withheld", "form": "withheld", "package_sha256": row["withheld_sha256"],
                 "withheld_id": None, "withheld_sha256": None}
    return line


def candidates(repo, tip, t3_ids, record):
    """The ladder's candidates, rank order, each with its tier and statement; mining rows go to `record`."""
    cands, mined = b.mine(repo, tip, fix_wording=False, limits=None)
    record += mined
    run_cands, in_runs = [], set()
    for run in topic_runs(repo, tip):
        cand, reason = run_candidate(repo, run)
        record.append({"id": f"{run[0][0][:7]}-{run[-1][0][:7]}", "stage": "run", "commits": [c[0] for c in run],
                       "reason": reason or "candidate", "tier": cand and cand["tier"]})
        if cand:
            run_cands.append(cand)
            in_runs |= set(cand["commits"])
    for cand in cands:
        cand["tier"] = tier_of(len(cand["source_files"]), cand["source_lines"], cand["source_added"], cand["subject"])
    pool = [c for c in cands if c["id"] not in t3_ids and not (c["tier"] == "T5" and c["commit"] in in_runs)]
    for cand in pool:
        if cand["tier"] in (None, "T3"):
            record.append({"id": cand["id"], "stage": "mine", "tier": cand["tier"], "reason": (
                "fits no tier (over every bound)" if cand["tier"] is None else "T3 size; T3 is the first build's")})
        else:
            cand["statement"] = tier_statement(cand["tier"], cand)
    chosen = sorted([c for c in pool if c["tier"] in ORDER] + run_cands, key=lambda c: c["rank"])
    for cand in chosen:
        cand["withheld_only"] = cand["tier"] in WITHHELD_ONLY  # only that form is shipped and audited
    return chosen


def build(work, workers, runs, out=b.HERE, repo=b.ROOT, tip=b.TIP, prior=()):
    """Evaluate every tier, then write the packages, `tasks.jsonl` and `ladder_screening.jsonl` under `out`."""
    if not os.environ.get("PATH", "").startswith(str(b.GUARD)):
        raise SystemExit(f"put {b.GUARD} first on PATH")
    t3, record, rows = first_build_t3(out), [], {}
    pool = candidates(repo, tip, {r["id"] for r in t3}, record)
    by_tier = evaluate_tiers(pool, rows, load_prior(prior), work, workers, runs)
    t3_results = t3_withheld_checks(t3, work, workers, runs, out, repo)
    staged = out / "tasks_new"
    b.remove(staged)
    staged.mkdir()
    lines = stage_t3(t3, t3_results, staged, work, out, repo, record)
    for tier, evaluated in by_tier.items():
        record += stage_tier(tier, evaluated, rows, work, staged, lines)
    b.remove(out / "tasks")
    staged.rename(out / "tasks")
    (out / "tasks.jsonl").write_text("".join(json.dumps(line, sort_keys=True) + "\n" for line in lines))
    (out / "ladder_screening.jsonl").write_text("".join(json.dumps({"tip": tip, **r}, sort_keys=True) + "\n"
                                                        for r in record))
    verify(out)


def first_build_t3(out):
    """The first build's T3 rows of `out/tasks.jsonl`: its drawn rows and every other row of T3 size."""
    old = [json.loads(line) for line in (out / "tasks.jsonl").read_text().splitlines()]
    return [r for r in old if r.get("tier", "T3") == "T3" and (r["set"] == "drawn" or tier_of(
        len(r["source_files"]), r["source_lines"], 0, r["subject"]) == "T3")]


def evaluate_tiers(pool, rows, prior_rows, work, workers, runs):
    """{tier: (its candidates, admitted, skipped, widened)}; T1 and T2 take fix-worded commits first and drop that
    filter once when fewer than CAP are admitted."""
    by_tier = {}
    for tier in ORDER:
        tiered = [c for c in pool if c["tier"] == tier]
        worded = [c for c in tiered if b.FIX_WORDS.search(c["message"])] if tier in ("T1", "T2") else tiered
        admitted, skipped = evaluate_tier(worded, rows, prior_rows, work, workers, runs)
        widened = len(admitted) < CAP and worded is not tiered
        if widened:
            admitted, skipped = evaluate_tier(tiered, rows, prior_rows, work, workers, runs)
        by_tier[tier] = (tiered, admitted, skipped, widened)
    return by_tier


def stage_t3(t3, results, staged, work, out, repo, record):
    """The first build's T3 rows staged with their check-withheld form (a failed form refuses the build) and
    leak-audited; their manifest lines. A failed audit is recorded as `rejected`; the packages stay unchanged."""
    lines = []
    for r, result in zip(t3, results):
        record.append({**result, "tier": "T3"})
        if result.get("reason"):
            raise SystemExit(f"{r['id']}: the check-withheld form failed: {result['reason']}")
        shutil.copytree(out / "tasks" / r["id"], staged / r["id"])
        shutil.copytree(work / "pkgs" / f"{r['id']}-withheld", staged / f"{r['id']}-withheld")
        failed = [f"{pid}: {check}: {why}" for pid in (r["id"], f"{r['id']}-withheld") for check, why in
                  leak_audit.audit(staged / pid, work, [r["commit"]], repo)]
        line = {**r, "tier": "T3", "form": "in_tree", "withheld_id": f"{r['id']}-withheld",
                "withheld_sha256": result["withheld_sha256"]}
        if failed:  # the first build's packages stay unchanged; the rejection is recorded, not applied by edit
            line["rejected"] = f"leak audit: {failed[0]}"
        record.append({"id": r["id"], "stage": "t3-audit", "tier": "T3", "reason": line.get("rejected", "clean")})
        line["probe"] = r["set"] == "drawn" and not failed and sum(x.get("probe", False) for x in lines) < PROBE
        lines.append(line)
    return lines


def stage_tier(tier, evaluated, rows, work, staged, lines):
    """Stage one tier's admitted packages (a withheld-only tier ships that form alone) and append their manifest
    lines, a T1 task's T0 variant after it; return the tier's screening records."""
    tiered, admitted, skipped, widened = evaluated
    record = []
    for index, cand in enumerate(admitted):
        row = rows[cand["id"]]
        for name in ([] if tier in WITHHELD_ONLY else [cand["id"]]) + [f"{cand['id']}-withheld"]:
            shutil.copytree(work / "pkgs" / name, staged / name)
        lines.append(manifest_row(cand, row, tier, index, widened))
        if tier == "T1":
            record.append(t0_line(cand, row, staged, lines))
    return record + tier_records(tier, tiered, {c["id"] for c in admitted}, skipped, rows)


def t0_line(cand, row, staged, lines):
    """Append a T1 task's T0 variant line after its own, when the variant is admitted; its screening record."""
    tid, reason = t0_variant(cand, row, staged)
    if tid:
        lines.append({**lines[-1], "id": tid, "tier": "T0", "variant_of": cand["id"],
                      "package_sha256": b.package_hash(staged / tid), "withheld_id": None, "withheld_sha256": None})
    return {"id": f"{cand['id']}-t0", "stage": "t0", "tier": "T0", "reason": reason or "admitted"}


def t3_withheld_checks(t3, work, workers, runs, out, repo):
    """The check-withheld form's result for each first-build T3 row, in order; finished checks are reused after a
    restart from `work/t3_withheld.jsonl`, never re-run."""
    cache = work / "t3_withheld.jsonl"
    done = {r["id"]: r for r in map(json.loads, cache.read_text().splitlines())} if cache.is_file() else {}
    todo = [r for r in t3 if r["id"] not in done]
    with ProcessPoolExecutor(max_workers=workers) as pool_:
        for result in pool_.map(b.withheld_only, [out / "tasks" / r["id"] for r in todo], [work] * len(todo),
                                [runs] * len(todo), [repo] * len(todo)):
            done[result["id"]] = result
            with cache.open("a") as handle:
                handle.write(json.dumps(result, sort_keys=True) + "\n")
    return [done[r["id"]] for r in t3]


def tier_records(tier, tiered, taken, skipped, rows):
    """The screening record of each of a tier's candidates: its row, reason and size."""
    found = []
    for cand in tiered:
        row = {k: v for k, v in rows.get(cand["id"], {}).items() if k not in ("base_outputs", "clone")}
        reason = skipped.get(cand["id"]) or row.get("reason") or (
            "admitted" if cand["id"] in taken else "beyond the tier's cap" if row else "not evaluated: tier full")
        found.append({**row, "id": cand["id"], "commit": cand["commit"], "tier": tier,
                      "stage": row.get("stage", "evaluate"), "rank": cand["rank"], "reason": reason,
                      "source_lines": cand["source_lines"], "source_files": len(cand["source_files"])})
    return found


def rebuild(tier, work, workers, runs, out=b.HERE, repo=b.ROOT, tip=b.TIP, prior=()):
    """Evaluate T2 or T4 again; replace its packages (both forms), its manifest rows and its
    screening records, keep every other tier as built. A T2 rebuild moves the smoke to its first non-probe task."""
    if not os.environ.get("PATH", "").startswith(str(b.GUARD)):
        raise SystemExit(f"put {b.GUARD} first on PATH")
    if tier not in ("T2", "T4"):
        raise SystemExit(f"rebuild takes T2 or T4, not {tier} (T1 carries T0; T3 is the first build's; T5 runs)")
    old = [json.loads(line) for line in (out / "tasks.jsonl").read_text().splitlines()]
    pool = [c for c in candidates(repo, tip, {r["id"] for r in old if r.get("tier") == "T3"}, []) if c["tier"] == tier]
    worded = [c for c in pool if b.FIX_WORDS.search(c["message"])] if tier == "T2" else pool
    rows = {}
    admitted, skipped = evaluate_tier(worded, rows, load_prior(prior), work, workers, runs)
    widened = len(admitted) < CAP and worded is not pool
    if widened:
        admitted, skipped = evaluate_tier(pool, rows, load_prior(prior), work, workers, runs)
    staged = out / "tasks_new"
    b.remove(staged)
    gone = {pid for r in old if r.get("tier") == tier for pid in (r["id"], r.get("withheld_id")) if pid}
    shutil.copytree(out / "tasks", staged, ignore=lambda d, names: [n for n in names if Path(d) == out / "tasks"
                                                                     and n in gone])
    lines = [r for r in old if r["id"] not in gone]
    for index, cand in enumerate(admitted):
        for name in (cand["id"], f"{cand['id']}-withheld"):
            shutil.copytree(work / "pkgs" / name, staged / name)
        line = manifest_row(cand, rows[cand["id"]], tier, index, widened)
        lines.append(line | ({"set": "smoke"} if tier == "T2" and index == PROBE else {}))
    b.remove(out / "tasks")
    staged.rename(out / "tasks")
    (out / "tasks.jsonl").write_text("".join(json.dumps(line, sort_keys=True) + "\n" for line in lines))
    screening = [json.loads(line) for line in (out / "ladder_screening.jsonl").read_text().splitlines()]
    kept = [r for r in screening if r.get("tier") != tier or r.get("stage") in ("mine", "run")]
    new = tier_records(tier, pool, {c["id"] for c in admitted}, skipped, rows)
    (out / "ladder_screening.jsonl").write_text("".join(json.dumps({"tip": tip, **r}, sort_keys=True) + "\n"
                                                        for r in kept + new))
    verify(out)


UNSTABLE = "anchor not stable under study conditions: "


def anchor_verdicts(row, stability, tasks_dir, scoring_path):
    """The row's packages (either form) with an entry in `stability`: [(id, entry)] of those unstable at their current
    hash and `scoring_path`, and the number measured at another hash or scoring path (`anchors.lacking`)."""
    why = {pid: anchors.lacking(stability[pid], tasks_dir / pid, scoring_path)
           for pid in (row["id"], row.get("withheld_id")) if pid in stability}
    return [(pid, stability[pid]) for pid, reason in why.items() if reason == "unstable"], sum(
        reason in ("not measured", "other scoring path") for reason in why.values())


def reject_unstable(rows, stability, tasks_dir):
    """The manifest with every row whose package (either form) is unstable in `stability`, at its current hash under
    `tasks_dir` and the current scoring path, rejected, naming the reference's failing tests; an entry measured at
    another hash or scoring path rejects nothing, and their number is printed. Each tier's probe flags then move to
    its next usable rows in seed order until it has four again, and a rejected smoke moves to the first usable T2
    task that is not a probe task (ruling 1). The draw refills by its own rules, since a rejected row is no
    package."""
    rows, scoring_path, skipped = [dict(row) for row in rows], anchors.scoring_path_hash(), 0
    for row in rows:
        failed, stale = anchor_verdicts(row, stability, tasks_dir, scoring_path)
        skipped += 0 if row.get("rejected") else stale
        if failed and not row.get("rejected"):
            row["rejected"] = UNSTABLE + "; ".join(
                (f"{pid}: " if pid != row["id"] else "") + ", ".join(anchors.unstable_tests(entry) or ["no repetition ran"])
                for pid, entry in failed)
            row["probe"] = False
    usable = [row for row in rows if not row.get("rejected") and row["set"] != "smoke"]
    for tier in dict.fromkeys(row["tier"] for row in usable):
        spare = [row for row in usable if row["tier"] == tier and not row.get("probe")]
        while sum(row.get("probe", False) for row in usable if row["tier"] == tier) < PROBE and spare:
            spare.pop(0)["probe"] = True
    for old in [row for row in rows if row["set"] == "smoke" and row.get("rejected")]:
        old["set"] = "rejected"
        next(row for row in usable if row["tier"] == "T2" and not row.get("probe"))["set"] = "smoke"
    if skipped:
        print(f"{skipped} anchors entries skipped, measured at another package hash or scoring path: the default "
              "run `python -m experiments.seed_set.anchors --work W` measures them")
    return rows


def verify(out=b.HERE):
    """Exit non-zero unless every listed package (both forms) hashes as recorded and none is unlisted."""
    lines = [json.loads(line) for line in (out / "tasks.jsonl").read_text().splitlines()]
    listed = {(line["id"], line["package_sha256"]) for line in lines}
    listed |= {(line["withheld_id"], line["withheld_sha256"]) for line in lines if line.get("withheld_id")}
    bad = sorted(pid for pid, digest in listed if b.package_hash(out / "tasks" / pid) != digest)
    extra = sorted({p.name for p in (out / "tasks").iterdir()} - {pid for pid, _ in listed})
    if bad or extra:
        raise SystemExit(f"changed: {bad}; unlisted: {extra}")
    stability = out / anchors.FILE
    if lost := anchors.unstable(lines, json.loads(stability.read_text()) if stability.is_file() else {}, out / "tasks"):
        raise SystemExit(f"{len(lost)} usable packages lack stable anchors under study conditions ({lost[:5]}): run "
                         "`python -m experiments.seed_set.anchors --work W` and reject what fails")
    print(f"{len(listed)} packages of {len(lines)} tasks verified; anchors stable under study conditions")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    cmd = sub.add_parser("build")
    again = sub.add_parser("rebuild")
    again.add_argument("--tier", required=True)
    for command in (cmd, again):
        command.add_argument("--work", type=Path, required=True)
        command.add_argument("--workers", type=int, default=3)
        command.add_argument("--runs", type=int, default=b.RUNS)
        command.add_argument("--prior", action="append", default=[],
                             help="screening.jsonl or rows.jsonl of an earlier build")
    sub.add_parser("verify")
    sub.add_parser("reject-unstable", help="reject the rows anchor_stability.json shows unstable, then verify")
    args = parser.parse_args()
    if args.cmd == "verify":
        verify()
    elif args.cmd == "reject-unstable":
        manifest = b.HERE / "tasks.jsonl"
        lines = reject_unstable([json.loads(line) for line in manifest.read_text().splitlines()],
                                json.loads((b.HERE / anchors.FILE).read_text()), b.HERE / "tasks")
        manifest.write_text("".join(json.dumps(line, sort_keys=True) + "\n" for line in lines))
        verify()
    elif args.cmd == "build":
        build(args.work.resolve(), args.workers, args.runs, prior=args.prior)
    else:
        rebuild(args.tier, args.work.resolve(), args.workers, args.runs, prior=args.prior)
