"""Summarize a scored pool: ratings joined by position, per-run values, measures, agreement, anchors, verdict.

  summarize.py --pool P --criterion C [--python PY]

Reads P/records/mapping.json (prepare.py pool) and, for every judge it lists, the judge's scan
(P/records/judges/<judge>/scan.json) and its one scoring run of experiments/compare/score.orc in its
state directory P/judges/<dir>/state/<run_id>/ (run.json and memo.jsonl). Refuses a criterion whose
`judges` differ from the pool's. Refuses a judge that is not
scanned, whose scan predates calls, or whose hits have no verdict; leaves out a judge found
contaminated. Refuses unless every other judge has exactly one completed scoring run that bound the
criterion file's SHA-256 and the judge's model, whose provider starts pair one to one with the judge's
shim call records (prepare.paired_calls), and every batch's ratings line up with its clones.
When the task package has hidden/ and hidden_tests.txt, runs each listed node id in a copy of every
clone without .git, with hidden/ copied over it and PYTHONPATH at the copy; results.json gives each
clone's pass fraction (`hidden`) and failing node ids (`hidden_failed`).
Writes P/records/results.json and P/records/results.md and prints the latter. Standard library only.
"""

import argparse
import hashlib
import json
import operator
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from statistics import mean

try:
    from .pool import rubric
    from .prepare import paired_calls, read_memo  # imported as experiments.compare.summarize
    from .scan import model_policy
except ImportError:  # run as a script
    from pool import rubric
    from prepare import paired_calls, read_memo
    from scan import model_policy

SCORES = {"S0": 0, "S1": 1, "S2": 2}  # score.orc's Score enumeration
CRITERIA = ("root_cause", "scope", "generality", "layering")
OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt}
NODE_TIMEOUT_SEC = 1800  # a hidden test that hangs counts as failed


def criteria_of(mapping):
    return tuple(rubric(mapping)["criteria"])


def judge_exclusion(pool, judge):
    """Why the judge is left out (a contaminated verdict), or None; refuse an unscanned or unadjudicated judge."""
    records = pool / "records" / "judges" / judge
    command = f"prepare.py scan --pool {pool} --judge {judge}"
    if not (records / "scan.json").is_file():
        raise SystemExit(f"judge {judge} has not been scanned: {command} --hash SOL")
    scan, calls = json.loads((records / "scan.json").read_text()), len(list((records / "calls").glob("*")))
    if scan["calls"] != calls:
        raise SystemExit(f"judge {judge}: the scan covers {scan['calls']} calls but {calls} were made: "
                         f"{command} --hash SOL")
    if model_policy(scan["hits"]):
        return model_policy(scan["hits"])
    if scan["hits"] and scan["verdict"] is None:
        raise SystemExit(f"judge {judge} has {len(scan['hits'])} scan hits and no verdict: {command} "
                         "--verdict contaminated|cleared --reason TEXT")
    verdict = scan["verdict"] or {}
    return f"contaminated: {verdict['reason']}" if verdict.get("verdict") == "contaminated" else None


def scoring_run(pool, judge, info, sha):
    """(run dir, bound batches, terminal value) of the judge's one completed scoring run, or refuse."""
    state = pool / "judges" / info["dir"] / "state"
    headers = sorted(state.glob("*/run.json"))
    if len(headers) != 1:
        raise SystemExit(f"judge {judge}: expected one scoring run under {state}, found {len(headers)}")
    run, bound = headers[0].parent, json.loads(headers[0].read_text())["bound_inputs"]
    if bound["criterion_sha256"] != sha:
        raise SystemExit(f"{run}: bound criterion_sha256 {bound['criterion_sha256']} differs from the criterion "
                         f"file's {sha}")
    if bound["judge_model"] != judge:
        raise SystemExit(f"{run}: bound judge_model {bound['judge_model']!r} is not judge {judge!r}")
    rows = read_memo(run / "memo.jsonl")
    if not rows or rows[-1]["record"] != "terminal" or rows[-1]["outcome"] != "completed":
        raise SystemExit(f"{run}: scoring run of judge {judge} has not completed")
    paired_calls(pool / "records" / "judges" / judge, rows)  # a judge that bypassed the shims has no call records
    return run, bound["batches"], rows[-1]["value"]


def join(run, batches, value, members, criteria=CRITERIA, references=()):
    """clone id -> rating with integer scores, joined by position; refuse any batch that does not line up."""
    if len(batches) != len(members) or len(value) != len(members):
        raise SystemExit(f"{run}: {len(batches)} batches bound, {len(value)} rated, {len(members)} pooled")
    joined = {}
    for index, (batch, ratings, ids) in enumerate(zip(batches, value, members)):
        if references and batch.get("reference") != references[index]:
            raise SystemExit(f"{run}: batch {index} binds another reference than the pool")
        listed = batch["clones"]
        if sorted(Path(c).name for c in listed) != sorted(ids):
            raise SystemExit(f"{run}: batch {index} lists other clones than the pool's batch {index}")
        if len(ratings) != len(listed):
            raise SystemExit(f"{run}: batch {index} has {len(ratings)} ratings for {len(listed)} clones")
        for position, (path, rating) in enumerate(zip(listed, ratings)):
            if rating["clone"] not in (path, Path(path).name):
                raise SystemExit(f"{run}: batch {index} position {position} copies back {rating['clone']!r} "
                                 f"but lists {path}")
            joined[Path(path).name] = {c: SCORES[rating[c]] for c in criteria} | {"reason": rating["reason"]}
    return joined


def passes(work, node, python):
    try:
        done = subprocess.run([python, "-m", "pytest", "-q", "-p", "no:cacheprovider", node], cwd=work,
                              env={**os.environ, "PYTHONPATH": str(work)}, capture_output=True,
                              timeout=NODE_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def hidden_failures(clone, task, nodes, python):
    """The hidden node ids that fail, run in a copy of the clone (no .git) with hidden/ copied over it."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / clone.name
        shutil.copytree(clone, work, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        shutil.copytree(task / "hidden", work, dirs_exist_ok=True)
        return [node for node in nodes if not passes(work, node, python)]


def run_values(arm, selected, scores, hidden):
    """The run's treatment value and its gains against the arm's in-run comparators."""
    if not scores:
        return {"value": None}
    if arm == "best_of_n":
        group = mean(v for k, v in scores.items() if k.startswith("cand-"))
        return {"value": scores[selected], "hidden_value": hidden.get(selected),
                "paired_gain": scores[selected] - scores["cand-1"], "group_gain": scores[selected] - group}
    values = {"value": scores["final"], "hidden_value": hidden.get("final")}
    if arm == "reviewed_change":
        values["paired_gain"] = scores["final"] - scores["first"]
        if {"first", "final"} <= hidden.keys():
            values["hidden_paired_gain"] = hidden["final"] - hidden["first"]
    return values


def run_rows(mapping, clone_scores, clone_hidden):
    labels = {}
    for cid, clone in mapping["clones"].items():
        if clone["arm"] == "reference":
            continue
        for label in clone["labels"]:
            labels.setdefault(clone["run"], {})[label] = cid
    rows = []
    for run, info in mapping["runs"].items():
        mine = labels.get(run, {})
        scores = {label: clone_scores[cid] for label, cid in mine.items()}
        hidden = {label: clone_hidden[cid] for label, cid in mine.items() if cid in clone_hidden}
        rows.append({"run": run, **info, "scores": scores, "hidden": hidden,
                     **run_values(info["arm"], info["selected"], scores, hidden)})
    return rows


def arm_measures(arm, done):
    m = {f"{arm}.runs": len(done), f"{arm}.mean": mean(r["value"] for r in done),
         f"{arm}.calls_mean": mean(r["calls"] for r in done),
         f"{arm}.wall_clock_mean": mean(r["wall_clock_sec"] for r in done)}
    hidden = [r["hidden_value"] for r in done if r.get("hidden_value") is not None]
    if hidden:
        m[f"{arm}.hidden_mean"] = mean(hidden)
    return m | gain_measures(arm, done)


def gain_measures(arm, done):
    m = {}
    for key in ("paired_gain", "group_gain", "hidden_paired_gain"):
        gains = [r[key] for r in done if key in r]
        if gains:
            m |= {f"{arm}.{key}_mean": mean(gains), f"{arm}.{key}_runs_positive": sum(g > 0 for g in gains),
                  f"{arm}.{key}_runs_negative": sum(g < 0 for g in gains)}
    return m


def measures(rows):
    """Named measures a criterion can reference; failed and excluded runs carry no value and are left out.
    `<arm>.minus_control` and `<arm>.hidden_minus_control` compare an arm's mean with direct_task's."""
    m, arms = {}, sorted({r["arm"] for r in rows})
    for arm in arms:
        done = [r for r in rows if r["arm"] == arm and r["value"] is not None]
        if done:
            m |= arm_measures(arm, done)
    return m | {f"{arm}.{name}": m[f"{arm}.{key}"] - m[f"direct_task.{key}"]
                for arm in arms if arm != "direct_task"
                for key, name in (("mean", "minus_control"), ("hidden_mean", "hidden_minus_control"))
                if f"{arm}.{key}" in m and f"direct_task.{key}" in m}


def agreement(ratings, criteria=CRITERIA):
    """Exact agreement of all judges per criterion, over the clones."""
    judges = sorted(ratings)
    if len(judges) < 2:
        return {}
    ids = sorted(ratings[judges[0]])
    return {c: {"agree": sum(len({ratings[j][i][c] for j in judges}) == 1 for i in ids), "of": len(ids)}
            for c in criteria}


def anchor_scores(mapping, totals):
    return [{"batch": index, "anchor": mapping["clones"][cid]["labels"][0], "judge": judge,
             "total": totals[judge][cid]}
            for index, batch in enumerate(mapping["batches"]) for cid in batch
            if mapping["clones"][cid]["arm"] == "anchor" for judge in sorted(totals)]


def verdict(criterion, m):
    return {kind: [{**entry, "observed": m.get(entry["measure"]),
                    "met": None if entry["measure"] not in m else OPS[entry["op"]](m[entry["measure"]], entry["value"])}
                   for entry in criterion.get(kind, [])] for kind in ("primary", "secondary")}


def anchor_spreads(anchors, judges, names):
    grouped = {(judge, name): [] for judge in judges for name in names}
    for row in anchors:
        key = row["judge"], row["anchor"]
        if key in grouped and type(row.get("total")) in (int, float):
            grouped[key].append(row["total"])
    return {judge: {name: max(values) - min(values) if (values := grouped[judge, name]) else None
                    for name in names} for judge in judges}


def spread_passes(spread, limit):
    return bool(spread) and all(value is not None and value <= limit
                                for names in spread.values() for value in names.values())


def calibration(results, mapping, criterion):
    """Judge every declared judge/batch pair, with absent controls counting as failures."""
    if criterion.get("purpose") != "calibration" or "calibration" not in criterion:
        return None
    rules, roles = criterion["calibration"], criterion["anchors"][Path(mapping["task"]).name]
    totals = {(row["judge"], row["batch"], row["anchor"]): row.get("total") for row in results["anchors"]}
    pairs = []
    eligible = set(results["judges"]) - set(results.get("excluded_judges", {}))
    for judge in criterion["judges"]:
        usable = judge in eligible
        for batch in range(len(mapping["batches"])):
            pairs.append(calibration_pair(judge, batch, totals, roles, rules, usable))
    failures = {f"{rule}_failing": mean(not row[rule] for row in pairs) if pairs else 1
                for rule in ("p1", "p2", "p3")}
    spread = anchor_spreads(results["anchors"], criterion["judges"], roles.values())
    return {"pairs": pairs, **failures, "anchor_spread": spread,
            "passed": bool(pairs) and all(value <= rules["error_rate"] for value in failures.values())
            and spread_passes(spread, criterion["anchor_spread_limit"])}


def calibration_pair(judge, batch, totals, roles, rules, usable):
    scores = {role: totals.get((judge, batch, roles[role])) if usable else None
              for role in ("upstream", "stub", "partial", "mutant")}
    complete = all(type(value) in (int, float) and 0 <= value <= 8 for value in scores.values())
    up, stub, partial, mutant = (scores[role] for role in ("upstream", "stub", "partial", "mutant"))
    return {"judge": judge, "batch": batch, **scores,
            "p1": complete and up - stub >= rules["margin"],
            "p2": complete and stub < partial < up,
            "p3": complete and up - mutant >= rules["mutant_margin"]}


def calibration_over(results_paths, criterion):
    """Combine the supplied accepted baseline and later pools, retaining their actual identities."""
    frozen = json.loads(Path(criterion).read_text())
    sha = hashlib.sha256(Path(criterion).read_bytes()).hexdigest()
    pools = {str(Path(path).resolve()): json.loads(Path(path).read_text()) for path in results_paths}
    if not pools or any(pool["criterion_sha256"] != sha for pool in pools.values()):
        raise SystemExit("calibration-over requires pools under the supplied criterion")
    tasks = {Path(pool["task"]).name for pool in pools.values()}
    if len(tasks) != 1:
        raise SystemExit("calibration-over pools must describe one task")
    roles = frozen["anchors"][tasks.pop()]
    anchors = [row for pool in pools.values() for row in pool["anchors"]]
    spread = anchor_spreads(anchors, frozen["judges"], roles.values())
    passed = {path: pool.get("calibration", {}).get("passed") is True for path, pool in pools.items()}
    return {"pools": passed, "anchor_spread": spread,
            "passed": all(passed.values()) and spread_passes(spread, frozen["anchor_spread_limit"])}


def fmt(value):
    return "" if value is None else (f"{value:.2f}" if isinstance(value, float) else str(value))


def run_table(rows):
    lines = ["| run | outcome | value | paired gain | group gain | hidden | calls | wall clock s | scan hits | "
             "verdict | excluded or failure |", "|" + " --- |" * 11]
    for r in rows:
        reason = r["excluded"] or (r["failure"] or {}).get("code")
        lines.append(f"| {r['arm']}/{Path(r['run']).name} | {r['outcome']} | {fmt(r['value'])} | "
                     f"{fmt(r.get('paired_gain'))} | {fmt(r.get('group_gain'))} | {fmt(r.get('hidden_value'))} | "
                     f"{fmt(r['calls'])} | {fmt(round(r['wall_clock_sec']))} | {r['scan_hits']} | "
                     f"{fmt((r['verdict'] or {}).get('verdict'))} | {fmt(reason)} |")
    return lines


def markdown(results):
    """results.md: runs, measures, verdict per criterion entry, agreement, anchors, scan verdicts."""
    lines = [f"Criterion sha256 `{results['criterion_sha256']}`; judges: {', '.join(results['judges'])}."]
    lines += [f"Judge {j} left out, {reason}." for j, reason in results["excluded_judges"].items()] + [""]
    lines += run_table(results["runs"]) + ["", "Measures:"]
    lines += [f"- {k}: {fmt(v)}" for k, v in results["measures"].items()] + ["", "Verdict:"]
    lines += [f"- {kind}: {e['measure']} {e['op']} {e['value']}: observed {fmt(e['observed'])}, met {e['met']}"
              for kind, entries in results["verdict"].items() for e in entries] + ["", "Agreement (all judges equal):"]
    lines += [f"- {c}: {a['agree']}/{a['of']}" for c, a in results["agreement"].items()] + ["", "Anchors:"]
    lines += [f"- batch {a['batch']}, {a['anchor']}, {a['judge']}: {a['total']}" for a in results["anchors"]]
    if results.get("calibration") is not None:
        lines += ["", "Calibration:", json.dumps(results["calibration"], sort_keys=True)]
    lines += ["", "Scan verdicts:"] + [
        f"- {r['arm']}/{Path(r['run']).name}: {r['scan_hits']} hits, "
        f"{r['verdict']['verdict']}: {r['verdict']['reason']}"
        for r in results["runs"] if r["verdict"]]
    return "\n".join(lines) + "\n"


def reference_paths(pool, mapping):
    """Reference-selected pools require one valid disclosed clone per batch before any judge join."""
    if not rubric(mapping)["reference"]:
        return []
    refs = mapping.get("references")
    if not isinstance(refs, list) or len(refs) != len(mapping["batches"]):
        raise SystemExit("reference metadata must name exactly one reference per batch")
    blind = {cid for batch in mapping["batches"] for cid in batch}
    for cid in refs:
        if not isinstance(cid, str):
            raise SystemExit("reference metadata names an unknown clone")
        if mapping["clones"].get(cid, {}).get("arm") != "reference" or cid in blind:
            raise SystemExit("reference metadata must name disclosed clones outside every blind batch")
    if len(set(refs)) != len(refs):
        raise SystemExit("reference metadata repeats a clone across batches")
    return [str(pool / "clones" / cid) for cid in refs]


def judged_ratings(pool, mapping, sha):
    """(left-out judges with reasons, ratings by judge of every other listed judge)."""
    references = reference_paths(pool, mapping)
    excluded = {judge: reason for judge in mapping["judges"] if (reason := judge_exclusion(pool, judge))}
    ratings = {judge: join(*scoring_run(pool, judge, info, sha), mapping["batches"], criteria_of(mapping), references)
               for judge, info in mapping["judges"].items() if judge not in excluded}
    if not ratings:
        raise SystemExit(f"every judge is excluded: {excluded}")
    return excluded, ratings


def hidden_acceptance(pool, mapping, python):
    """({clone id: passed fraction}, {clone id: failing node ids}); both empty without hidden acceptance."""
    task = Path(mapping["task"])
    if not ((task / "hidden").is_dir() and (task / "hidden_tests.txt").is_file()):
        return {}, {}
    nodes = [line.strip() for line in (task / "hidden_tests.txt").read_text().splitlines() if line.strip()]
    failed = {cid: hidden_failures(pool / "clones" / cid, task, nodes, python) for cid, clone in mapping["clones"].items()
              if clone["arm"] != "reference"}
    return {cid: (len(nodes) - len(f)) / len(nodes) for cid, f in failed.items()}, failed


def score_values(mapping, ratings):
    criteria = criteria_of(mapping)
    totals = {judge: {cid: sum(r[c] for c in criteria) for cid, r in rated.items()} for judge, rated in ratings.items()}
    clone_scores = {cid: mean(totals[judge][cid] for judge in totals) for cid, clone in mapping["clones"].items()
                    if clone["arm"] != "reference"}
    return totals, clone_scores


def summarize(pool, criterion, python=sys.executable):
    pool = Path(pool).resolve()
    mapping = json.loads((pool / "records" / "mapping.json").read_text())
    sha = hashlib.sha256(Path(criterion).read_bytes()).hexdigest()
    frozen = json.loads(Path(criterion).read_text())
    if sorted(frozen["judges"]) != sorted(mapping["judges"]):
        raise SystemExit(f"the criterion names judges {sorted(frozen['judges'])} "
                         f"but the pool has {sorted(mapping['judges'])}")
    if rubric(frozen) != rubric(mapping):
        raise SystemExit("the criterion rubric differs from the pool rubric")
    criteria = criteria_of(mapping)
    excluded, ratings = judged_ratings(pool, mapping, sha)
    totals, clone_scores = score_values(mapping, ratings)
    clone_hidden, hidden_failed = hidden_acceptance(pool, mapping, python)
    rows = run_rows(mapping, clone_scores, clone_hidden)
    m = measures(rows)
    results = {
        "task": mapping["task"], "criterion_sha256": sha, "judges": sorted(ratings), "excluded_judges": excluded, "runs": rows,
        "measures": m,
        "verdict": verdict(frozen, m), "agreement": agreement(ratings, criteria),
        "anchors": anchor_scores(mapping, totals),
        "clones": {cid: {**clone, "score": clone_scores.get(cid), "hidden": clone_hidden.get(cid),
                         "hidden_failed": hidden_failed.get(cid),
                         "ratings": {j: ratings[j][cid] for j in sorted(ratings) if cid in ratings[j]}}
                   for cid, clone in mapping["clones"].items()},
    }
    if (observed := calibration(results, mapping, frozen)) is not None:
        results["calibration"] = observed
    (pool / "records" / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    (pool / "records" / "results.md").write_text(markdown(results))
    print(markdown(results), end="")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pool", type=Path)
    mode.add_argument("--calibration-over", type=Path, nargs="+")
    parser.add_argument("--criterion", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable, help="interpreter for hidden acceptance tests")
    args = parser.parse_args(argv)
    if args.calibration_over:
        print(json.dumps(calibration_over(args.calibration_over, args.criterion), indent=2))
    else:
        summarize(args.pool, args.criterion, args.python)


if __name__ == "__main__":
    main()
