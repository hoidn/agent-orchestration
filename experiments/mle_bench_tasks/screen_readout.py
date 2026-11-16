"""The MLE-bench screen readout (plan docs/plans/2026-11-15-mle-bench-family-plan.md, M1, M7 to M9 and Task 6).

From one resource class's launcher exports, its stage one and, if it ran, its stage two (M9), and each attempt's
result file, to the screen's classes of M1 per competition; at the placement, the ladder's pooled label with the
count and the exact 90 and 95 percent intervals; and the line's priced usage per calendar day. It makes no claim
beyond those classes and counts.

Reused from the reviewed ladder kit, loaded by path and unchanged (`experiments/long_horizon_tasks/`):
  slot_record.load     reads and checks an export; decides each start's class and whether it is counted (an
                       observation, not excluded, no contamination hit) and its success (reward 1: here a medal)
  readout._criterion   refuses a final readout while a readout field is pending; a rehearsal takes stand-ins
  readout._listed      every start that enters no count with its reason, flags, cuts, refused connections
  readout._contaminated, readout._recorded, readout.interval (exact Clopper-Pearson, standard library, bisection
                       on the binomial tail)
  readout.compute      the whole placement readout of ladder D6; this module takes its pooled label and counts
New here: the screen's classes (M1), the graded outcomes read from the result file that gave the reward (M4), the
90 percent interval beside the ladder's 95, and the per-day usage from the passthrough's request logs (M9).

Inputs per stage: (criterion: the tranche's ladder.json as a dict, export: the launcher's export as a dict, state:
the tranche's state root). The state root holds `slots/<start:03d>-<slot>/` per attempt (the launcher's attempt id)
with the trial's `jobs/<job>/<trial>/result.json` and each regrade's `regrade/<attempt>-regrade-<n>/result.json`,
and `passthrough/requests.jsonl`, the passthrough's request log. Only the export's current label enters a count, as
in the ladder (D7.6); starts under an earlier label are counted apart.

Classes are computed from observations only (stage_class; coordinator's ruling on fix round 1). A competition has
a class as soon as no outcome of its missing observations could change it, and is "incomplete", with the number
missing, until then; one with no observation at all is "not screened", and one stage two did not fund "not funded".
The readout never reclassifies what the launcher exported: an observation whose reward no result file gives stays
an observation, is listed, and a class that would differ without such observations is marked. A stop withholds every
class the stopped stage would decide, and a stopped placement places nothing.

The day (M9): a request counts on the calendar day, in the zone given, on which the passthrough received it (its
request-log row's time). A final readout reads the criterion its label names (bound). Standard library only, so it
runs under `python -I` like the ladder's kit.
"""

import argparse
import datetime
import importlib.util
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

EXPERIMENTS = Path(__file__).resolve().parents[1]
LADDER_KIT = EXPERIMENTS / "long_horizon_tasks"
STAGE_SLOTS = 3  # attempts per competition in each stage of the screen (M1)
ABOVE, SURVIVES, UNDECIDED, LOW = "above the band", "survives", "undecided: awaits stage two", "excluded low"
NOT_SCREENED, NOT_FUNDED, INCOMPLETE = "not screened", "not funded", "incomplete"
WITHHELD = "withheld: the stage ended in a stop"
OUTCOMES = ("medal", "valid", "above_median", "score", "percentile", "grader_exception")
THRESHOLDS = ("bronze", "silver", "gold", "median")  # the reward file's <name>_threshold fields
DAY_RULE = ("a request counts on the calendar day, in the given time zone, on which the passthrough received it: "
            "its request-log row's time")
NO_RESULT_REASON = {0: "no result file gives this reward: the launcher records 0 for an observation whose two "
                       "regrades both ended in a verifier timeout (ladder.py `regraded`, regrade case 1)"}
NO_RULE = "no result file gives this reward, and the launcher has no rule that records it without one"
GRADER_EXCEPTION_NOTE = ("the benchmark's grader caught an error inside the competition's grade function: the "
                         "verifier's reward stands and is counted as written; a person rules on it")
# What Task 6 names and the inputs do not carry (coordinator's note 8): where each would have to come from.
NOT_IN_THE_INPUTS = {
    "installed packages": "dropped from Task 6 (coordinator's ruling on fix round 1): neither the export nor the "
                          "result file lists them; they would be parsed from each attempt's transcript",
    "processes holding the GPU": "the wrapper's once-a-minute record (plan M4, item 7) is Task 5's; its file and form "
                                 "are not yet written",
}


def _ladder(name):
    spec = importlib.util.spec_from_file_location(f"mle_lh_{name}", LADDER_KIT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ladder = _ladder("readout")
# The ladder's bound() keys each file it checks as f"{KIT_PATH}/{name}"; on this private load the prefix is the
# experiments directory, so that one manifest can bind this family's files and the ladder's (bound, below).
ladder.KIT_PATH = "experiments"
slot_record = ladder.slot_record  # the one loaded by the ladder's readout, so that its RecordError is one class
interval = ladder.interval


class ReadoutError(ValueError):
    """A rule or an input the readout refuses; the message names it."""


# ---- the result file that gave an attempt's reward ----------------------------------------------------------------

def outcomes(rewards):
    """The graded outcomes of the reward file the verifier writes (Task 2): the one place that knows its fields.
    score and percentile are absent when the grader gave no finite score, a valid submission included;
    grader_exception, absent from files written before it was added, reads as 0; a threshold the grader gave none
    for is absent and is not recorded (None)."""
    return {"medal": int(rewards["medal"]), "valid": int(rewards["valid_submission"]),
            "above_median": int(rewards["above_median"]), "score": rewards.get("score"),
            "percentile": rewards.get("percentile"), "grader_exception": int(rewards.get("grader_exception", 0)),
            "thresholds": {name: rewards.get(f"{name}_threshold") for name in THRESHOLDS}}


def _no_outcomes(start):
    """An observation that no result file backs: nothing graded, and the reason the reward stands as exported."""
    return dict.fromkeys(OUTCOMES) | {"thresholds": dict.fromkeys(THRESHOLDS),
                                      "reason": NO_RESULT_REASON.get(start["reward"], NO_RULE)}


def _rewards(path):
    """The reward file's fields as the harness put them in a result.json, or None."""
    if not path.is_file():
        return None
    return ((slot_record.read(path).get("verifier_result") or {}).get("rewards")) or None


def reward_source(state, start):
    """(rewards, source) of the result that gave the start's reward: the first regrade that gave one (the launcher
    stops at it), else the trial's own; (None, None) when none gave one."""
    attempt = state / "slots" / f"{start['start']:03d}-{start['slot']}"
    if not attempt.is_dir():
        raise ReadoutError(f"start {start['start']}: no attempt directory {attempt.name} under {state / 'slots'}")
    for n in (1, 2):
        rewards = _rewards(attempt / "regrade" / f"{attempt.name}-regrade-{n}" / "result.json")
        if rewards and rewards.get("reward") is not None:
            return rewards, f"regrade {n}"
    trials = sorted(p for p in (attempt / "jobs").glob("*/*") if p.is_dir())
    rewards = _rewards(trials[0] / "result.json") if trials else None
    return (rewards, "trial") if rewards and rewards.get("reward") is not None else (None, None)


def _attempt(start, state):
    """One observation with its graded outcomes; refused when the result file's reward is not the exported one."""
    rewards, source = reward_source(state, start)
    if rewards is not None and rewards["reward"] != start["reward"]:
        raise ReadoutError(f"start {start['start']}: the {source}'s result gives reward {rewards['reward']}, the "
                           f"export {start['reward']}")
    graded = outcomes(rewards) if rewards else _no_outcomes(start)
    return {"start": start["start"], "slot": start["slot"], "reward": start["reward"], "source": source,
            "ending": start["ending"], "flagged": start["flagged"], "usd": start["usd"],
            "minutes": start["minutes"]} | graded


# ---- one stage --------------------------------------------------------------------------------------------------

def _refused(starts):
    counts = {}
    for start in starts:
        for address, n in start["egress_refused"].items():
            counts[address] = counts.get(address, 0) + n
    return dict(sorted(counts.items()))


def _graded(attempts):
    """The counts of the graded outcomes over a stage's observations; an outcome not recorded counts in none."""
    return {"valid": sum(a["valid"] == 1 for a in attempts), "invalid": sum(a["valid"] == 0 for a in attempts),
            "valid_not_scored": sum(a["valid"] == 1 and a["score"] is None for a in attempts),
            "above_median": sum(a["above_median"] == 1 for a in attempts),
            "outcomes_not_recorded": sum(a["source"] is None for a in attempts),
            "grader_exception": sum(a["grader_exception"] == 1 for a in attempts),
            "grader_exceptions": [a | {"note": GRADER_EXCEPTION_NOTE} for a in attempts if a["grader_exception"] == 1]}


def _unbacked(attempts):
    """The observations whose reward no result file gives: listed, with the launcher's reason, for a ruling."""
    listed = [a for a in attempts if a["source"] is None]
    return {"reward_without_result": len(listed), "rewards_without_result": listed,
            "medals_without_result": sum(a["reward"] == 1 for a in listed)}


def _spent(own, observed, classes):
    """Cost of every start that counts as one (cuts and failures included), minutes over observations, cuts."""
    minutes, left = ladder._recorded([s["minutes"] for s in observed])
    return {"usd": sum(s["usd"] for s in own if classes[s["class"]]["starts"]), "mean_minutes": minutes,
            "minutes_not_recorded": left, "cuts": sum(s["class"] == "cut" for s in own)}


def _competition(name, current, listed, state, classes):
    """A competition's figures in one stage: its observations, medals and graded outcomes, cost, minutes, cuts,
    flags and refused connections, and every start that entered no count with its reason."""
    own = [s for s in current if s["task"] == name]
    observed = [s for s in own if s["counted"]]
    if len(observed) > STAGE_SLOTS:
        raise ReadoutError(f"{name}: {len(observed)} observations in one stage, more than its {STAGE_SLOTS} slots")
    attempts = [_attempt(s, state) for s in observed]
    return {"observations": len(observed), "medals": sum(s["success"] for s in observed), "attempts": attempts,
            "flagged": sum(s["flagged"] for s in observed), "egress_refused": _refused(own),
            "not_counted": [e for e in listed["exclusions"] if e["task"] == name]} | _graded(attempts) | _spent(
                own, observed, classes) | _unbacked(attempts)


def stage(criterion, export, state, standins=None):
    """One stage's readout: per competition of its schedule, its figures (_competition)."""
    criterion, rehearsal = ladder._criterion(criterion, standins)
    efforts = criterion["attempt"]["efforts"]
    if len(efforts) != 1:
        raise ReadoutError(f"a stage of the screen runs at one effort; this criterion has {efforts}")
    starts = slot_record.load(export, criterion)
    current = [s for s in starts if s["label"] == export["label"]]
    listed = ladder._listed(current, efforts, criterion) | {"contaminated": ladder._contaminated(starts, criterion)}
    scheduled = {slot["task"] for slot in export["slots"]}
    names = [task["name"] for task in criterion["tasks"]["list"] if task["name"] in scheduled]
    classes = criterion["classification"]["classes"]
    return {"rehearsal": rehearsal, "label": export["label"], "end": export["end"], "open": len(export["open"]),
            "earlier_label_starts": len(starts) - len(current), "listed": listed,
            "competitions": {n: _competition(n, current, listed, Path(state), classes) for n in names}}


def _stopped(result):
    return result["end"] is not None and result["end"]["by"] == "stop"


# ---- the screen's classes (M1) ------------------------------------------------------------------------------------

def stage_class(stage, medals, observations, slots=STAGE_SLOTS):
    """(class, missing) of one stage of M1, from its medals among its observations of its slots: a class as soon as
    no outcome of the missing observations could change it, else "incomplete" with the number missing. Stage one:
    any medal beside a non-medal survives; every slot a medal is above the band; no medal in all its slots goes to
    stage two. Stage two (after no medal in stage one): any medal survives at once; no medal in all its slots, six
    observations over both stages, is excluded low."""
    missing = slots - observations
    if stage == "two" and medals >= 1 or stage == "one" and 1 <= medals < observations:
        return SURVIVES, 0
    if missing:
        return INCOMPLETE, missing
    if stage == "two":
        return LOW, 0
    return (ABOVE if medals == slots else UNDECIDED), 0


def screen_class(one, two, funded):
    """(class, missing) of M1 over both stages. one and two are a stage's {"observations", "medals", "stopped"}; two
    is None when stage two did not run for the competition; funded is False when stage two did not fund it, None
    while that is not yet known."""
    if one["stopped"]:
        return WITHHELD, None
    if one["observations"] == 0:
        return NOT_SCREENED, STAGE_SLOTS
    cls, missing = stage_class("one", one["medals"], one["observations"])
    if cls != UNDECIDED:
        return cls, missing
    if funded is False:
        return NOT_FUNDED, STAGE_SLOTS
    if two is None:
        return UNDECIDED, STAGE_SLOTS
    if two["stopped"]:
        return WITHHELD, None
    return stage_class("two", two["medals"], two["observations"])


def _state(stage_result, name, backed=False):
    """A stage's counts for screen_class; backed leaves out the observations no result file backs."""
    figures = stage_result["competitions"][name]
    less = (figures["reward_without_result"], figures["medals_without_result"]) if backed else (0, 0)
    return {"observations": figures["observations"] - less[0], "medals": figures["medals"] - less[1],
            "stopped": _stopped(stage_result)}


def _check_stage_two(one, two):
    """Stage two follows stage one's end, and holds only competitions with no medal in three observations (M9)."""
    if one["end"] is None or _stopped(one):
        raise ReadoutError("stage two is read only after stage one has ended, and not after a stop")
    for name in two["competitions"]:
        figures = one["competitions"].get(name)
        if figures is None or (figures["observations"], figures["medals"]) != (STAGE_SLOTS, 0):
            raise ReadoutError(f"stage two holds {name}, which did not end stage one with no medal in "
                               f"{STAGE_SLOTS} observations")


def _screen(one, two, no_stage_two):
    """Per competition of stage one: its class, its counts over both stages and what is missing."""
    screened = {}
    for name in one["competitions"]:
        in_two = two is not None and name in two["competitions"]
        funded = in_two if two is not None else (False if no_stage_two else None)
        cls, missing = screen_class(_state(one, name), _state(two, name) if in_two else None, funded)
        backed, _ = screen_class(_state(one, name, True), _state(two, name, True) if in_two else None, funded)
        stages = [one] + ([two] if in_two else [])
        screened[name] = {"class": cls, "missing": missing, "rests_on_rewards_without_result": backed != cls,
                          "observations": sum(s["competitions"][name]["observations"] for s in stages),
                          "medals": sum(s["competitions"][name]["medals"] for s in stages)}
    return screened


# ---- the placement (ladder D6) ----------------------------------------------------------------------------------

def place(criterion, export, screened, standins=None):
    """The ladder's placement readout of the fresh attempts alone; the screen's counts printed beside, never pooled
    (M1). A stopped placement places nothing: no label."""
    result = ladder.compute(criterion, export, standins)
    placed = {}
    for name, task in result["tasks"].items():
        if screened.get(name, {}).get("class") != SURVIVES:
            raise ReadoutError(f"{name} is in the placement but did not survive the screen")
        pooled = task["pooled"]
        placed[name] = {"K": pooled["K"], "n": pooled["n"], "label": pooled.get("label"),
                        "interval_90": interval(pooled["K"], pooled["n"], 0.90),
                        "interval_95": interval(pooled["K"], pooled["n"], 0.95),
                        "cells": {e: {"k": c["k"], "n": c["n"]} for e, c in task["cells"].items()},
                        "screen": {key: screened[name][key] for key in ("observations", "medals")}}
    return {"label": result["label"], "end": result["end"], "open": result["open"], "competitions": placed}


# ---- priced usage per calendar day (M9, "The day") ----------------------------------------------------------------

def per_day(states, zone):
    """{date: priced USD} over every forwarded request of the stages' passthrough logs, each counted on the calendar
    day of its row's time in the given zone. A refusal carries no price and counts nowhere."""
    days = {}
    for state in states:
        log = Path(state) / "passthrough" / "requests.jsonl"
        if not log.is_file():
            raise ReadoutError(f"no request log {log}: the day's usage cannot be read")
        for line in log.read_text().splitlines():
            row = json.loads(line) if line.strip() else {}
            if row.get("usd") is not None:
                day = datetime.datetime.fromtimestamp(row["time"], zone).date().isoformat()
                days[day] = days.get(day, 0.0) + row["usd"]
    return {day: round(usd, 6) for day, usd in sorted(days.items())}


# ---- the readout ------------------------------------------------------------------------------------------------

def _stop(one, two, placed):
    for name, result in (("one", one), ("two", two), ("placement", placed)):
        if result is not None and _stopped(result):
            return {"stage": name, "cause": result["end"]["cause"]}
    return None


def compute(stage_one, stage_two=None, *, no_stage_two=False, placement=None, time_zone, standins=None):
    """The readout of one resource class. Each stage is (criterion, export, state root); no_stage_two says stage
    two was not funded at all (M9: k is zero). time_zone is the machine's zone, in which a request's day is read."""
    if stage_two is not None and no_stage_two:
        raise ReadoutError("a stage-two export and 'no stage two' exclude each other")
    one = stage(*stage_one, standins)
    two = stage(*stage_two, standins) if stage_two is not None else None
    if two is not None:
        _check_stage_two(one, two)
    screened = _screen(one, two, no_stage_two)
    placed = None if placement is None else place(placement[0], placement[1], screened, standins)
    states = [s[2] for s in (stage_one, stage_two, placement) if s is not None]
    return {"rehearsal": one["rehearsal"] or bool(two and two["rehearsal"]), "stop": _stop(one, two, placed),
            "stages": {"one": _summary(one), "two": _summary(two)}, "no_stage_two": no_stage_two,
            "competitions": _joined(screened, one, two), "placement": placed,
            "per_day_usd": per_day(states, time_zone), "time_zone": str(time_zone), "day_rule": DAY_RULE,
            "not_in_the_inputs": NOT_IN_THE_INPUTS}


def _summary(result):
    return result and {key: result[key] for key in ("label", "end", "open", "earlier_label_starts", "listed")}


def _joined(screened, one, two):
    """Per competition: its screen class and counts, beside each stage's own figures."""
    second = two["competitions"] if two else {}
    return {name: {"screen": screened[name], "stage_one": one["competitions"][name], "stage_two": second.get(name)}
            for name in screened}


def _cell(figures):
    return "-" if figures is None else f"{figures['medals']} of {figures['observations']}"


def _row(name, c):
    stages = [s for s in (c["stage_one"], c["stage_two"]) if s]
    valid, above = sum(s["valid"] for s in stages), sum(s["above_median"] for s in stages)
    usd, cuts = sum(s["usd"] for s in stages), sum(s["cuts"] for s in stages)
    missing = f" ({c['screen']['missing']} missing)" if c["screen"]["missing"] else ""
    return (f"{name:<12}  {_cell(c['stage_one']):<9}  {_cell(c['stage_two']):<9}  {valid:>5}  {above:>7}  "
            f"{usd:>8.2f}  {cuts:>4}  {c['screen']['class']}{missing}{_marks(c['screen'], stages)}")


def _marks(screen, stages):
    """The row's notes for a person's ruling: grader exceptions, rewards with no verifier result, and a class that
    would differ without those rewards."""
    caught, unbacked = (sum(s[key] for s in stages) for key in ("grader_exception", "reward_without_result"))
    notes = [f"{caught} grader exception(s), for a ruling"] * bool(caught) + [
        f"{unbacked} reward(s) without a verifier result, for a ruling"] * bool(unbacked) + [
        "the class rests on rewards without a verifier result"] * screen["rests_on_rewards_without_result"]
    return "".join(f"; {note}" for note in notes)


def _figure(value):
    return "not recorded" if value is None else f"{value:g}"


def _scores(c):
    """One line per observation: its score against the thresholds the reward file gives. Start numbers repeat from
    tranche to tranche, so each line names its stage."""
    attempts = [(stage, a) for stage in ("one", "two") if c[f"stage_{stage}"] for a in c[f"stage_{stage}"]["attempts"]]
    return [f"  stage {stage} start {a['start']}: score {'none' if a['score'] is None else _figure(a['score'])} "
            "against " + ", ".join(f"{name} {_figure(value)}" for name, value in a["thresholds"].items())
            for stage, a in attempts]


def _placed(name, p):
    low, high = (f"{100 * x:.1f}" for x in p["interval_90"])
    return f"placement {name}: {p['K']} of {p['n']} ({low}-{high}% at 90%), {p['label'] or 'no label'}"


def table(result):
    """The short plain-text table, from compute's result alone."""
    lines = [f"{'competition':<12}  {'stage one':<9}  {'stage two':<9}  {'valid':>5}  {'>median':>7}  "
             f"{'usd':>8}  {'cuts':>4}  class"]
    lines += [line for name, c in result["competitions"].items() for line in [_row(name, c), *_scores(c)]]
    lines += [_placed(name, p) for name, p in ((result["placement"] or {}).get("competitions") or {}).items()]
    lines += [f"day {day}: USD {usd:.2f} ({result['time_zone']})" for day, usd in result["per_day_usd"].items()]
    stop = result["stop"]
    return "\n".join(lines + ([f"stopped in stage {stop['stage']}: {stop['cause']}"] if stop else [])) + "\n"


def document(result):
    """The JSON document: sorted keys, so the same inputs give the same bytes."""
    return json.dumps(result, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def bound(criterion_path, manifest_path, label, root=EXPERIMENTS.parent):
    """A final readout reads the criterion its label names: the ladder's own bound() (the manifest frozen, its
    SHA-256 the label, each file the readout reads recorded in it as it is) over the tranche's criterion, this module
    and the two ladder modules it loads, keyed by their paths from the repository root (Task 4's manifests follow the
    ladder's format). None, or the ladder's ReadoutError naming what does not hold."""
    try:
        criterion = Path(criterion_path).resolve().relative_to((Path(root) / "experiments").resolve())
    except ValueError:
        raise ReadoutError(f"the criterion {criterion_path} is not under {Path(root) / 'experiments'}") from None
    files = {criterion.as_posix(): Path(criterion_path).read_bytes(),
             "mle_bench_tasks/screen_readout.py": Path(__file__).read_bytes()} | {
        f"long_horizon_tasks/{name}": (LADDER_KIT / name).read_bytes() for name in ("readout.py", "slot_record.py")}
    ladder.bound(files, Path(manifest_path).read_bytes(), label)


def _given(paths, final):
    """A stage's (criterion, export, state root) from its four paths; in a final readout, bound to its label."""
    if paths is None:
        return None
    export, state, criterion, manifest = (Path(p) for p in paths)
    doc = slot_record.read(export)
    if final:
        bound(criterion, manifest, doc["label"])
    return slot_record.read(criterion), doc, state


def main(argv):
    parser = argparse.ArgumentParser(description="The MLE-bench screen readout (plan M1, Task 6): prints a short "
                                     "table; with --json, writes the readout as one JSON document.")
    stage_args = {"nargs": 4, "metavar": ("EXPORT", "STATE", "CRITERION", "MANIFEST")}
    parser.add_argument("--stage-one", required=True, **stage_args,
                        help="stage one's export, state root, ladder.json and manifests/<tranche>.json")
    two = parser.add_mutually_exclusive_group()
    two.add_argument("--stage-two", **stage_args, help="stage two's four paths, as for --stage-one")
    two.add_argument("--no-stage-two", action="store_true", help="stage two was not funded (M9: k is zero)")
    parser.add_argument("--placement", **stage_args, help="the placement's four paths, as for --stage-one")
    parser.add_argument("--time-zone", required=True, help="this machine's IANA time zone, e.g. America/Los_Angeles")
    parser.add_argument("--rehearsal", metavar="STAND_INS", help="stand-ins for the pending readout fields")
    parser.add_argument("--json", metavar="PATH", help="where to write the JSON document")
    args = parser.parse_args(argv)
    try:
        final = args.rehearsal is None  # a rehearsal reads unfrozen criteria, as the ladder's does
        result = compute(_given(args.stage_one, final), _given(args.stage_two, final), no_stage_two=args.no_stage_two,
                         placement=_given(args.placement, final), time_zone=ZoneInfo(args.time_zone),
                         standins=slot_record.read(Path(args.rehearsal)) if args.rehearsal else None)
    except (ReadoutError, ladder.ReadoutError, slot_record.RecordError) as error:
        print(f"screen_readout.py: {error}", file=sys.stderr)
        return 2
    print(table(result), end="")
    if args.json:
        Path(args.json).write_text(document(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
