"""Summarize a scored pool: ratings joined by position, per-run values, measures, agreement, anchors, verdict.

  summarize.py --pool P --criterion C [--python PY]

Reads P/records/mapping.json (prepare.py pool) and, for every judge it lists, the one scoring run of
experiments/compare/score.orc in that judge's state directory P/judges/<dir>/state/<run_id>/
(run.json and memo.jsonl). Refuses unless every listed judge has exactly one completed scoring run
that bound the criterion file's SHA-256 and the judge's model, and every batch's ratings line up with
its clones. When the task package has hidden/ and hidden_tests.txt, runs each listed node id in a
copy of every clone without .git, with hidden/ copied over it and PYTHONPATH at the copy.
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

SCORES = {"S0": 0, "S1": 1, "S2": 2}  # score.orc's Score enumeration
CRITERIA = ("root_cause", "scope", "generality", "layering")
OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt}
NODE_TIMEOUT_SEC = 1800  # a hidden test that hangs counts as failed


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
    rows = [json.loads(line) for line in (run / "memo.jsonl").read_text().split("\n")[:-1]]
    if not rows or rows[-1]["record"] != "terminal" or rows[-1]["outcome"] != "completed":
        raise SystemExit(f"{run}: scoring run of judge {judge} has not completed")
    return run, bound["batches"], rows[-1]["value"]


def join(run, batches, value, members):
    """clone id -> rating with integer scores, joined by position; refuse any batch that does not line up."""
    if len(batches) != len(members) or len(value) != len(members):
        raise SystemExit(f"{run}: {len(batches)} batches bound, {len(value)} rated, {len(members)} pooled")
    joined = {}
    for index, (batch, ratings, ids) in enumerate(zip(batches, value, members)):
        listed = batch["clones"]
        if sorted(Path(c).name for c in listed) != sorted(ids):
            raise SystemExit(f"{run}: batch {index} lists other clones than the pool's batch {index}")
        if len(ratings) != len(listed):
            raise SystemExit(f"{run}: batch {index} has {len(ratings)} ratings for {len(listed)} clones")
        for position, (path, rating) in enumerate(zip(listed, ratings)):
            if rating["clone"] not in (path, Path(path).name):
                raise SystemExit(f"{run}: batch {index} position {position} copies back {rating['clone']!r} "
                                 f"but lists {path}")
            joined[Path(path).name] = {c: SCORES[rating[c]] for c in CRITERIA} | {"reason": rating["reason"]}
    return joined


def passes(work, node, python):
    try:
        done = subprocess.run([python, "-m", "pytest", "-q", "-p", "no:cacheprovider", node], cwd=work,
                              env={**os.environ, "PYTHONPATH": str(work)}, capture_output=True,
                              timeout=NODE_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def hidden_fraction(clone, task, python):
    """Passed / listed hidden node ids, run in a copy of the clone (no .git) with hidden/ copied over it."""
    nodes = [line.strip() for line in (task / "hidden_tests.txt").read_text().splitlines() if line.strip()]
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / clone.name
        shutil.copytree(clone, work, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        shutil.copytree(task / "hidden", work, dirs_exist_ok=True)
        return sum(passes(work, node, python) for node in nodes) / len(nodes)


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
    return values


def run_rows(mapping, clone_scores, clone_hidden):
    labels = {}
    for cid, clone in mapping["clones"].items():
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
    for key in ("paired_gain", "group_gain"):
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


def agreement(ratings):
    """Exact agreement of all judges per criterion, over the clones."""
    judges = sorted(ratings)
    if len(judges) < 2:
        return {}
    ids = sorted(ratings[judges[0]])
    return {c: {"agree": sum(len({ratings[j][i][c] for j in judges}) == 1 for i in ids), "of": len(ids)}
            for c in CRITERIA}


def anchor_scores(mapping, totals):
    return [{"batch": index, "anchor": mapping["clones"][cid]["labels"][0], "judge": judge,
             "total": totals[judge][cid]}
            for index, batch in enumerate(mapping["batches"]) for cid in batch
            if mapping["clones"][cid]["arm"] == "anchor" for judge in sorted(totals)]


def verdict(criterion, m):
    return {kind: [{**entry, "observed": m.get(entry["measure"]),
                    "met": None if entry["measure"] not in m else OPS[entry["op"]](m[entry["measure"]], entry["value"])}
                   for entry in criterion.get(kind, [])] for kind in ("primary", "secondary")}


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
    lines = [f"Criterion sha256 `{results['criterion_sha256']}`; judges: {', '.join(results['judges'])}.", ""]
    lines += run_table(results["runs"]) + ["", "Measures:"]
    lines += [f"- {k}: {fmt(v)}" for k, v in results["measures"].items()] + ["", "Verdict:"]
    lines += [f"- {kind}: {e['measure']} {e['op']} {e['value']}: observed {fmt(e['observed'])}, met {e['met']}"
              for kind, entries in results["verdict"].items() for e in entries] + ["", "Agreement (all judges equal):"]
    lines += [f"- {c}: {a['agree']}/{a['of']}" for c, a in results["agreement"].items()] + ["", "Anchors:"]
    lines += [f"- batch {a['batch']}, {a['anchor']}, {a['judge']}: {a['total']}" for a in results["anchors"]]
    lines += ["", "Scan verdicts:"] + [
        f"- {r['arm']}/{Path(r['run']).name}: {r['scan_hits']} hits, "
        f"{r['verdict']['verdict']}: {r['verdict']['reason']}"
        for r in results["runs"] if r["verdict"]]
    return "\n".join(lines) + "\n"


def summarize(pool, criterion, python=sys.executable):
    pool = Path(pool).resolve()
    mapping = json.loads((pool / "records" / "mapping.json").read_text())
    sha = hashlib.sha256(Path(criterion).read_bytes()).hexdigest()
    ratings = {judge: join(*scoring_run(pool, judge, info, sha), mapping["batches"])
               for judge, info in mapping["judges"].items()}
    totals = {judge: {cid: sum(r[c] for c in CRITERIA) for cid, r in rated.items()} for judge, rated in ratings.items()}
    clone_scores = {cid: mean(totals[judge][cid] for judge in totals) for cid in mapping["clones"]}
    task = Path(mapping["task"])
    clone_hidden = {}
    if (task / "hidden").is_dir() and (task / "hidden_tests.txt").is_file():
        clone_hidden = {cid: hidden_fraction(pool / "clones" / cid, task, python) for cid in mapping["clones"]}
    rows = run_rows(mapping, clone_scores, clone_hidden)
    m = measures(rows)
    results = {
        "criterion_sha256": sha, "judges": sorted(ratings), "runs": rows, "measures": m,
        "verdict": verdict(json.loads(Path(criterion).read_text()), m), "agreement": agreement(ratings),
        "anchors": anchor_scores(mapping, totals),
        "clones": {cid: {**clone, "score": clone_scores[cid], "hidden": clone_hidden.get(cid),
                         "ratings": {j: ratings[j][cid] for j in sorted(ratings)}}
                   for cid, clone in mapping["clones"].items()},
    }
    (pool / "records" / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    (pool / "records" / "results.md").write_text(markdown(results))
    print(markdown(results), end="")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--criterion", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable, help="interpreter for hidden acceptance tests")
    args = parser.parse_args(argv)
    summarize(args.pool, args.criterion, args.python)


if __name__ == "__main__":
    main()
