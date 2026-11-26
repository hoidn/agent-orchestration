"""The qualification check of one competition (family plan M2, Task 7): the four controls and the ten lines. qualify.sh
runs it; it runs no container itself.

  python3 -I qualify.py controls <work dir>
      Run by qualify.sh inside the competition's verifier image, outside Harbor, with no network: the benchmark's own
      grader (the image's /tests/grade_submission.py, its one call into the benchmark) grades the answers and the
      controls. Reads <work>/answers.csv (the answers, or the gold submission) and <work>/sample.csv (the public sample
      submission); writes <work>/<control>.csv for each control built and <work>/controls.json (build_controls).
  python3 -I qualify.py record <label> <jobs dir> <outcomes.json>
      Adds the rewards Harbor read for the one trial under <jobs dir> to outcomes.json under <label> (record).
  python3 -I qualify.py lines <outcomes.json> <controls.json> [--floor F]
      Prints the ten lines (lines); exit 0 when every one is ok, else 1.
  python3 -I qualify.py overlay <package dir> <copy dir> <ladder.json>
      Copies a package with the agent phase's two network keys, by the reviewed launcher's own overlay() and
      allowlist() over the tranche's criterion (ladder.py, loaded by its path); prints the keys' digest.

A refusal prints "qualify.py: refused: <reason>" and exits 2.
"""

import argparse
import importlib.util
import json
import os
import random
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
LEGS = ("answers", "sample", "untouched")
CONTROLS = ("bronze-past", "bronze-short", "median-past", "median-short")
SEED = 0  # the seeded row order of the controls (plan M2)
# The reward file's keys as this run recorded them (Task 7: "the keys of the reward file are then held to what this
# run recorded"); verifier/grade_submission.py writes the first set for a scored submission, the second otherwise.
SCORED_KEYS = frozenset({"reward", "valid_submission", "above_median", "medal", "grader_exception", "score",
                         "percentile", "gold_threshold", "silver_threshold", "bronze_threshold", "median_threshold"})
UNSCORED_KEYS = SCORED_KEYS - {"score", "percentile"}
SHOWN = (("reward", "reward"), ("valid", "valid_submission"), ("medal", "medal"), ("above_median", "above_median"),
         ("score", "score"), ("percentile", "percentile"))


class Refused(Exception):
    """qualify.py refuses; the message names the input at fault."""


# ---- the controls (plan M2) ----------------------------------------------------------------------------------


def past(score, line, lower, strict):
    """Whether score is past line in the metric's direction: a medal is at or past its line, above the median is
    strictly past it (the benchmark's rule)."""
    if strict:
        return score < line if lower else score > line
    return score <= line if lower else score >= line


def bisect(score_of, holds, n):
    """(k - 1, k): the pair of row counts where holds() turns from true to false, by bisection over 0..n, given that
    it holds at 0 and not at n; None otherwise."""
    lo, hi = 0, n
    if not holds(score_of(lo)) or holds(score_of(hi)):
        return None
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if holds(score_of(mid)) else (lo, mid)
    return lo, hi


def replaced(answers, sample, order, k):
    """answers (a DataFrame) with the rows at order[:k] taken from sample, matched by the first column (the id)."""
    import numpy as np
    import pandas as pd
    key = answers.columns[0]
    other = sample.set_index(key).reindex(answers[key]).reset_index()[list(answers.columns)]
    mask = np.zeros(len(answers), bool)
    mask[list(order[:k])] = True
    return pd.DataFrame(np.where(mask[:, None], other.to_numpy(object), answers.to_numpy(object)),
                        columns=answers.columns)


def expected(score, lines, lower):
    """The class a score must get, written down before the control is run: reward 1 for a medal (past bronze)."""
    return {"reward": int(past(score, lines["bronze"], lower, False)),
            "above_median": int(past(score, lines["median"], lower, True))}


def build_controls(answers_path, sample_path, grade, work):
    """Build the two pairs of controls, one row either side of the bronze line and of the median, from the answers
    with a share of rows replaced by the sample's in a seeded order. grade(path) -> the grader's report (score,
    is_lower_better, bronze_threshold, median_threshold). Writes <work>/<label>.csv; returns the record."""
    import pandas as pd
    answers, sample = pd.read_csv(answers_path), pd.read_csv(sample_path)
    key = answers.columns[0]
    if list(sample.columns) != list(answers.columns) or sorted(sample[key]) != sorted(answers[key]):
        raise Refused(f"{sample_path}: the sample's columns or ids are not the answers'")
    report = grade(answers_path)
    lower = bool(report["is_lower_better"])
    lines = {"bronze": report["bronze_threshold"], "median": report["median_threshold"]}
    order = list(range(len(answers)))
    random.Random(SEED).shuffle(order)
    scores = {}

    def score_of(k):
        if k not in scores:
            path = Path(work) / f"rows-{k}.csv"
            replaced(answers, sample, order, k).to_csv(path, index=False)
            scores[k] = grade(path)["score"]
            path.unlink()
        return scores[k]

    out = {"seed": SEED, "rows": len(answers), "lower_is_better": lower, "lines": lines, "controls": {},
           "margins": {}, "unbuilt": []}
    for line, strict in (("bronze", False), ("median", True)):
        pair = bisect(score_of, lambda s: s is not None and past(s, lines[line], lower, strict), len(answers))
        if pair is None:
            out["unbuilt"].append(line)
            continue
        for side, k in zip(("past", "short"), pair):
            replaced(answers, sample, order, k).to_csv(Path(work) / f"{line}-{side}.csv", index=False)
            out["controls"][f"{line}-{side}"] = {"rows_replaced": k, "score": score_of(k),
                                                 "expected": expected(score_of(k), lines, lower)}
        out["margins"][line] = abs(score_of(pair[0]) - score_of(pair[1]))
    return out


def _image_grader():
    """grade(path) -> report, by the verifier image's own call into the benchmark (Task 2's grade_submission)."""
    sys.path.insert(0, "/tests")
    import grade_submission as g
    work = Path(g.IN_IMAGE["MLE_GRADER_WORK"])
    work.mkdir(parents=True, exist_ok=True)
    os.chdir(work)  # the benchmark opens a cache where it runs
    cid, data, bench = (os.environ["MLE_COMPETITION_ID"], Path(os.environ.get("MLE_DATA_DIR", g.IN_IMAGE["MLE_DATA_DIR"])),
                        Path(g.IN_IMAGE["MLE_BENCHMARK_DIR"]))
    return lambda path: g.benchmark_report(Path(path), cid, data, bench)[0]


# ---- the ten lines -------------------------------------------------------------------------------------------


def _shown(r):
    return " ".join(f"{name}={r.get(key, '-')}" for name, key in SHOWN) if r is not None else "no reward"


def _written(r):
    if r is None:
        return "no reward written"
    if set(r) not in (SCORED_KEYS, UNSCORED_KEYS):
        return f"reward keys not as recorded: {sorted(set(r) ^ (SCORED_KEYS if 'score' in r else UNSCORED_KEYS))}"
    return None


def _leg(leg, r, floor):
    """Why a leg's run is not what M2 lists for it, or None."""
    if leg == "answers":
        return None if r["reward"] == 1 and r["medal"] == 3 else "needs reward 1 with gold"
    if leg == "untouched":
        return None if r["reward"] == 0 else "needs reward 0"
    if not (r["reward"] == 0 and r["valid_submission"] == 1 and "score" in r):
        return "needs reward 0, valid, with a score"
    return None if floor is None or r["score"] == floor else f"score is not the listed floor {floor}"


def _control(r, c):
    e = c["expected"]
    got = {"reward": r["reward"], "above_median": r["above_median"]}
    if r["valid_submission"] != 1 or got != e:
        return f"expected reward={e['reward']} above_median={e['above_median']}, valid"
    return None if r.get("score") == c["score"] else f"score is not the host's {c['score']}"


def _order(outcomes, lower):
    """Whether the percentiles of the scored legs and controls are in the order of their scores."""
    labels = [f"{leg}-{n}" for leg in ("answers", "sample") for n in (1, 2)] + [f"control-{c}" for c in CONTROLS]
    points = [(r["score"], r.get("percentile")) for r in map(outcomes.get, labels) if r and "score" in r]
    if any(p is None for _, p in points):
        return "a scored run has no percentile"
    sign = -1 if lower else 1
    wrong = any((sign * (s - t) > 0 and p < q) or (s == t and p != q) for s, p in points for t, q in points)
    return "percentiles not in the order of the scores" if wrong else None


def lines(outcomes, controls, floor):
    """The ten lines: each leg's two runs, then the four controls, each "<what>: ok|FAIL <fields>[; <why>]"."""
    out = []

    def line(what, fault, r, extra=""):
        out.append(f"{what}: {'FAIL' if fault else 'ok'} {_shown(r)}{extra}{'; ' + fault if fault else ''}")

    for leg in LEGS:
        first = outcomes.get(f"{leg}-1")
        for n in (1, 2):
            r = outcomes.get(f"{leg}-{n}")
            fault = _written(r) or _leg(leg, r, floor)
            if not fault and n == 2 and first is not None and r.get("score") != first.get("score"):
                fault = "score differs from run 1"
            line(f"{leg} {n}", fault, r)
    order = _order(outcomes, controls["lower_is_better"])
    for label in CONTROLS:
        r, c = outcomes.get(f"control-{label}"), controls["controls"].get(label)
        if c is None:
            line(f"control {label}", "not built: no pair straddles this line", r)
            continue
        line(f"control {label}", _written(r) or _control(r, c) or order, r,
             f" host_score={c['score']} rows_replaced={c['rows_replaced']}")
    return out


# ---- Harbor's record, the overlay ----------------------------------------------------------------------------


def record(label, jobs, path):
    """Add the rewards of the one trial under jobs (Harbor's <job>/<trial>/result.json) to the JSON file at path."""
    trials = sorted(Path(jobs).glob("*/*/result.json"))
    if len(trials) != 1:
        raise Refused(f"{jobs}: {len(trials)} trial records, not one")
    rewards = (json.loads(trials[0].read_text()).get("verifier_result") or {}).get("rewards")
    path = Path(path)
    recorded = json.loads(path.read_text()) if path.exists() else {}
    path.write_text(json.dumps(recorded | {label: rewards}, indent=1, sort_keys=True) + "\n")


def overlay(package, copy, criterion):
    """The launcher's overlay of the agent phase's network keys, with the tranche's allowlist; their digest."""
    spec = importlib.util.spec_from_file_location("mle_qualify_ladder", KIT.parent / "long_horizon_tasks" / "ladder.py")
    lad = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lad)
    return lad.overlay(Path(package), Path(copy), lad.allowlist(json.loads(Path(criterion).read_text())))


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="step", required=True)
    sub.add_parser("controls").add_argument("work", type=Path)
    q = sub.add_parser("record")
    for name in ("label", "jobs", "outcomes"):
        q.add_argument(name)
    q = sub.add_parser("lines")
    q.add_argument("outcomes", type=Path)
    q.add_argument("controls", type=Path)
    q.add_argument("--floor", type=float)
    q = sub.add_parser("overlay")
    for name in ("package", "copy", "criterion"):
        q.add_argument(name)
    a = p.parse_args(argv)
    try:
        if a.step == "controls":
            built = build_controls(a.work / "answers.csv", a.work / "sample.csv", _image_grader(), a.work)
            (a.work / "controls.json").write_text(json.dumps(built, indent=1, sort_keys=True) + "\n")
        elif a.step == "record":
            record(a.label, a.jobs, a.outcomes)
        elif a.step == "overlay":
            print(overlay(a.package, a.copy, a.criterion))
        else:
            shown = lines(json.loads(a.outcomes.read_text()), json.loads(a.controls.read_text()), a.floor)
            print("\n".join(shown))
            return 0 if all(": ok " in s for s in shown) else 1
    except Refused as e:
        print(f"qualify.py: refused: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
