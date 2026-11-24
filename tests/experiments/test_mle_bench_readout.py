"""The MLE-bench screen readout (`experiments/mle_bench_tasks/screen_readout.py`; family plan M1, M7 to M9, Task 6).

The screen's fixtures are written by the launcher's own writer: each start's `slot.json` and `settled.json` sit in a
rehearsal state root under the launcher's attempt id, and `ladder.export` (a private load of the reviewed
`ladder.py`, with the wrapper's replaced name EFFORTS of plan M4) writes the export from them. The criteria are Task
4's: the committed stage-one `ladder.json` with its pending fields filled, and stage two by the generator's own
`_stage_two`. Rewards are written by the verifier's own `grade_submission.outcome`. The placement's export, at three
efforts, is built by the ladder's test helper (`long_horizon_record_support.export`), whose output loads through
`slot_record.load` as the launcher's must. Nothing runs an agent, a container or a provider call.
"""

import datetime
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from tests.experiments.long_horizon_record_support import ROOT, filled, with_values
from tests.experiments.long_horizon_record_support import export as lh_export

KIT = ROOT / "experiments" / "mle_bench_tasks"
LEADERBOARD = ROOT / "tests" / "experiments" / "fixtures" / "mle_bench" / "tiny-tabular" / "competition" / "leaderboard.csv"
ZONE = "America/Los_Angeles"
T0 = 1_795_000_000.0  # 2026-11-18 in ZONE


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


readout = _load(KIT / "screen_readout.py", "mle_screen_readout_tested")
verifier = _load(KIT / "verifier" / "grade_submission.py", "mle_grade_submission_for_readout")
generator = _load(KIT / "make_criterion.py", "mle_make_criterion_for_readout")
launcher = _load(ROOT / "experiments" / "long_horizon_tasks" / "ladder.py", "mle_ladder_for_readout")
launcher.EFFORTS = ("medium",)  # the wrapper's replaced name for the screen (plan M4)

FAMILY = json.loads((KIT / "family.json").read_text())
CPU = [c["name"] for c in FAMILY["candidates"] if c["class"] == "cpu"]  # leaf, textnorm-ru, birds
A, B, C = CPU
TERM = "a frozen term of the test"
TERM_SHA256 = hashlib.sha256(TERM.encode()).hexdigest()
TOKEN_KINDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")
ENDED = {"by": "schedule", "cause": None}
STOPPED = {"by": "stop", "cause": "a match of token_scan.py (ledger row 2026-11-20)"}
OPEN = "open"  # a start the launcher claimed and has not settled
INFRA = {"row": 4, "class": "infrastructure_failure"}
CUT = {"row": 10, "class": "cut"}
NO_REWARD = {"class": "infrastructure_failure", "regrade_case": 1}
CONTAMINATED = {"reward": 1.0, "contamination": {"hits": [{"term_sha256": TERM_SHA256}]}}
NOT_COUNTED = {"infrastructure failure": INFRA, "cut": CUT, "no reward after regrades": NO_REWARD}


def _filled(doc, qualified):
    """Task 4's criterion with every pending field filled, as the freeze leaves it."""
    values = {"usage_limits.vendor_headers_confirmed": {"x": 1}, "allowance_guard.utilisation_header": "x",
              "tasks.qualified": qualified, "tasks.load_sensitive": [], "tasks.withholding": {},
              "tasks.packages": {}, "readout.contamination_scan.terms": [TERM],
              "readout.contamination_scan.canary_exempt_tasks": [], "schedule.order.seed": 7,
              "readout.fall_bound.seed": 7}
    out = with_values(doc, {p["field"]: values[p["field"]] for p in doc["pending"]})
    out["filled"] = out["filled"] + [p | {"source": "a test"} for p in out["pending"]]
    out["pending"] = []
    return out


SCREEN = _filled(json.loads((KIT / "tranches" / "screen-cpu" / "ladder.json").read_text()), CPU)
PLACE = with_values(filled(), {"tasks.list": [{"name": name} for name in CPU]})


def _report(medal, score, valid=None, thresholds=None):
    """A grader report as the benchmark's grade_csv gives it, for a medal level (0 none to 3 gold)."""
    return {"score": score, "valid_submission": score is not None if valid is None else valid,
            "above_median": medal > 0, "gold_medal": medal == 3, "silver_medal": medal == 2,
            "bronze_medal": medal == 1, "is_lower_better": False} | (thresholds or {})


def _rewards(medal, score=0.8, valid=None, exception=False, thresholds=None):
    """The reward file the verifier writes for that report (Task 2's own function)."""
    return verifier.outcome(_report(medal, score, valid, thresholds), exception, LEADERBOARD)


def _write(path, rewards):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"verifier_result": None if rewards is None else {"rewards": rewards}}))


def _outcomes(outcome):
    if outcome == "-":
        return []
    if isinstance(outcome, list):
        return outcome
    return [outcome]


def _settled(fields):
    """The settled record of one start, in the keys the launcher's close writes and its export reads."""
    base = {"row": 5, "class": "observation", "reward": None, "usd": 1.0, "minutes": 30.0,
            "tokens": dict.fromkeys(TOKEN_KINDS, 10), "api_retry": 0, "graded": None, "contamination": {"hits": []}}
    return base | ({"reward": float(fields)} if isinstance(fields, int) else fields)


def _results(attempt, index, settled, files, regrades):
    if index in regrades:
        trial, regrade, n = regrades[index]
        _write(attempt / "jobs" / "job" / "trial" / "result.json", trial)
        _write(attempt / "regrade" / f"{attempt.name}-regrade-{n}" / "result.json", regrade)
    elif index in files:
        _write(attempt / "jobs" / "job" / "trial" / "result.json", files[index])
    elif settled["class"] == "observation" and settled["reward"] is not None:
        _write(attempt / "jobs" / "job" / "trial" / "result.json", _rewards(int(settled["reward"])))


def _log(state, rows):
    (state / "passthrough").mkdir(parents=True, exist_ok=True)
    (state / "passthrough" / "requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def _tranche(root, criterion, table, *, end=ENDED, files=None, regrades=None, extra_rows=()):
    """A tranche's (criterion, export path, state root): table maps a competition to the outcomes of its rounds; an
    outcome is 0 or 1 (an observation ending normally), "-" (no start), OPEN, a dict of settled fields, or a list of
    them (one slot's starts in order). The launcher's export writes the export from the records."""
    root.mkdir(mode=0o700, parents=True)
    (root / "manifest.json").write_text(json.dumps({"a manifest of": root.name}))
    launcher.manifest.MANIFEST = root / "manifest.json"  # each tranche its own label, as under the wrapper
    label, ctx = launcher.this_label(), launcher.Ctx({"LH_REHEARSAL": str(root / "rehearsal"), "HOME": str(root)})
    slots = {launcher.slot_id(entry): entry for entry in launcher.schedule(criterion)}
    index, rows = 0, []
    for task, outcomes in table.items():
        for number, outcome in enumerate(outcomes, 1):
            for fields in _outcomes(outcome):
                index += 1
                entry = slots[f"r{number}-{task}-medium"]
                attempt = ctx.root / "slots" / f"{index:03d}-{launcher.slot_id(entry)}"
                attempt.mkdir(parents=True)
                launcher._write_json(attempt / "slot.json", {**entry, "id": attempt.name, "index": index,
                                                              "label": label})
                if fields == OPEN:
                    continue
                settled = _settled(fields)
                launcher._write_json(attempt / "settled.json", settled)
                _results(attempt, index, settled, files or {}, regrades or {})
                rows.append({"time": T0 + index, "slot": attempt.name, "usd": settled["usd"]})
    if end:
        launcher._write_json(ctx.root / "end.json", end)
    _log(ctx.root, [*rows, *extra_rows])
    path = root / "export.json"
    path.write_text(json.dumps(launcher.export(ctx, criterion), indent=1))
    return criterion, path, ctx.root


def _two_criterion(stage_one, funded):
    """Stage two's criterion by Task 4's own generator, derived from stage one's export file."""
    criterion, path, _ = stage_one
    derivation = {"export_label": json.loads(path.read_text())["label"],
                  "export_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "funded": funded,
                  "not_funded": [], "ceiling_usd": 40.0}
    return _filled(generator._stage_two(criterion, derivation, "cpu", generator.FIELDS), funded)


def _stages(tmp_path, one, two=None, *, end_one=ENDED, end_two=ENDED, files_one=None, files_two=None):
    stage_one = _tranche(tmp_path / "one", SCREEN, one, end=end_one, files=files_one)
    if two is None:
        return stage_one, None
    return stage_one, _tranche(tmp_path / "two", _two_criterion(stage_one, list(two)), two, end=end_two,
                               files=files_two)


def _compute(tmp_path, one, two=None, *, no_stage_two=False, placement=None, end_one=ENDED, end_two=ENDED):
    stage_one, stage_two = _stages(tmp_path, one, two, end_one=end_one, end_two=end_two)
    placed = _placement(tmp_path, placement) if placement is not None else None
    return readout.compute(stage_one, stage_two, no_stage_two=no_stage_two, placement=placed,
                           time_zone=ZoneInfo(ZONE))


def _placement(tmp_path, table, end=ENDED):
    """The placement's (criterion, export path, state root), at three efforts, by the ladder's test helper."""
    doc, state = lh_export(table, end=end), tmp_path / "place"
    for start in doc["starts"]:
        attempt = state / "slots" / f"{start['start']:03d}-{start['slot']}"
        attempt.mkdir(parents=True)
        if start["reward"] is not None:
            _write(attempt / "jobs" / "job" / "trial" / "result.json", _rewards(int(start["reward"])))
    _log(state, [{"time": T0 + s["start"], "slot": s["slot"], "usd": s["usd"]} for s in doc["starts"]])
    path = state / "export.json"
    path.write_text(json.dumps(doc))
    return PLACE, path, state


def _class(result, name):
    return result["competitions"][name]["screen"]["class"]


def _code(call):
    with pytest.raises(readout.ReadoutError) as caught:
        call()
    return caught.value.code


# ---- 1. The class rule: one function over both stages' counts and open slots (fix round 2, ruling 1) ------------

S, AB, LO, UN = readout.SURVIVES, readout.ABOVE, readout.LOW, readout.UNDECIDED
IN, PE, NS, NF = readout.INCOMPLETE, readout.PENDING, readout.NOT_SCREENED, readout.NOT_FUNDED
# (stage-one medals, observations, open slots) -> (class, missing), stage two not yet given
STAGE_ONE_ALONE = {(0, 0, 0): (UN, None), (0, 0, 1): (PE, None), (0, 0, 2): (PE, None), (0, 0, 3): (PE, None),
                   (0, 1, 0): (UN, None), (0, 1, 1): (PE, None), (0, 1, 2): (PE, None), (1, 1, 0): (IN, 2),
                   (1, 1, 1): (PE, None), (1, 1, 2): (PE, None), (0, 2, 0): (UN, None), (0, 2, 1): (PE, None),
                   (1, 2, 0): (S, 0), (1, 2, 1): (S, 0), (2, 2, 0): (IN, 1), (2, 2, 1): (PE, None),
                   (0, 3, 0): (UN, None), (1, 3, 0): (S, 0), (2, 3, 0): (S, 0), (3, 3, 0): (AB, 0)}
# (stage-one observations with no medal, stage-two medals, stage-two observations, stage-two open slots)
OVER_BOTH_STAGES = {
    (0, 0, 0, 0): (NS, 6), (0, 0, 0, 1): (PE, None), (0, 0, 0, 2): (PE, None), (0, 0, 0, 3): (PE, None),
    (0, 0, 1, 0): (IN, 5), (0, 0, 1, 1): (PE, None), (0, 0, 1, 2): (PE, None), (0, 1, 1, 0): (S, 0),
    (0, 1, 1, 1): (S, 0), (0, 1, 1, 2): (S, 0), (0, 0, 2, 0): (IN, 4), (0, 0, 2, 1): (PE, None),
    (0, 1, 2, 0): (S, 0), (0, 1, 2, 1): (S, 0), (0, 2, 2, 0): (S, 0), (0, 2, 2, 1): (S, 0), (0, 0, 3, 0): (IN, 3),
    (0, 1, 3, 0): (S, 0), (0, 2, 3, 0): (S, 0), (0, 3, 3, 0): (S, 0),
    (1, 0, 0, 0): (IN, 5), (1, 0, 0, 1): (PE, None), (1, 0, 0, 2): (PE, None), (1, 0, 0, 3): (PE, None),
    (1, 0, 1, 0): (IN, 4), (1, 0, 1, 1): (PE, None), (1, 0, 1, 2): (PE, None), (1, 1, 1, 0): (S, 0),
    (1, 1, 1, 1): (S, 0), (1, 1, 1, 2): (S, 0), (1, 0, 2, 0): (IN, 3), (1, 0, 2, 1): (PE, None),
    (1, 1, 2, 0): (S, 0), (1, 1, 2, 1): (S, 0), (1, 2, 2, 0): (S, 0), (1, 2, 2, 1): (S, 0), (1, 0, 3, 0): (IN, 2),
    (1, 1, 3, 0): (S, 0), (1, 2, 3, 0): (S, 0), (1, 3, 3, 0): (S, 0),
    (2, 0, 0, 0): (IN, 4), (2, 0, 0, 1): (PE, None), (2, 0, 0, 2): (PE, None), (2, 0, 0, 3): (PE, None),
    (2, 0, 1, 0): (IN, 3), (2, 0, 1, 1): (PE, None), (2, 0, 1, 2): (PE, None), (2, 1, 1, 0): (S, 0),
    (2, 1, 1, 1): (S, 0), (2, 1, 1, 2): (S, 0), (2, 0, 2, 0): (IN, 2), (2, 0, 2, 1): (PE, None),
    (2, 1, 2, 0): (S, 0), (2, 1, 2, 1): (S, 0), (2, 2, 2, 0): (S, 0), (2, 2, 2, 1): (S, 0), (2, 0, 3, 0): (IN, 1),
    (2, 1, 3, 0): (S, 0), (2, 2, 3, 0): (S, 0), (2, 3, 3, 0): (S, 0),
    (3, 0, 0, 0): (IN, 3), (3, 0, 0, 1): (PE, None), (3, 0, 0, 2): (PE, None), (3, 0, 0, 3): (PE, None),
    (3, 0, 1, 0): (IN, 2), (3, 0, 1, 1): (PE, None), (3, 0, 1, 2): (PE, None), (3, 1, 1, 0): (S, 0),
    (3, 1, 1, 1): (S, 0), (3, 1, 1, 2): (S, 0), (3, 0, 2, 0): (IN, 1), (3, 0, 2, 1): (PE, None),
    (3, 1, 2, 0): (S, 0), (3, 1, 2, 1): (S, 0), (3, 2, 2, 0): (S, 0), (3, 2, 2, 1): (S, 0), (3, 0, 3, 0): (LO, 0),
    (3, 1, 3, 0): (S, 0), (3, 2, 3, 0): (S, 0), (3, 3, 3, 0): (S, 0)}


def test_the_tables_hold_every_reachable_combination():
    alone = {(k, n, o) for n in range(4) for k in range(n + 1) for o in range(4 - n)}
    both = {(n1, k, n, o) for n1 in range(4) for n in range(4) for k in range(n + 1) for o in range(4 - n)}
    assert (set(STAGE_ONE_ALONE), set(OVER_BOTH_STAGES)) == (alone, both)


@pytest.mark.parametrize("counts", sorted(STAGE_ONE_ALONE))
def test_stage_one_alone_gives_the_tables_class(counts):
    assert readout.screen_class(counts, None, None) == STAGE_ONE_ALONE[counts]


@pytest.mark.parametrize("counts", sorted(OVER_BOTH_STAGES))
def test_both_stages_together_give_the_tables_class(counts):
    observed, *two = counts
    assert readout.screen_class((0, observed, 0), tuple(two), True) == OVER_BOTH_STAGES[counts]


@pytest.mark.parametrize("observed", range(4))
def test_a_competition_stage_two_did_not_fund_is_not_funded(observed):
    assert readout.screen_class((0, observed, 0), None, False) == (NF, 6 - observed)


@pytest.mark.parametrize("rewards, expected", [([1, 1, 1], AB), ([1, 0, 0], S), ([0, 1, 1], S), ([0, 0, 0], UN),
                                               ([1, 0, "-"], S), ([1, 1, "-"], IN), ([0, 0, INFRA], UN)])
def test_stage_one_through_the_launchers_export(tmp_path, rewards, expected):
    assert _class(_compute(tmp_path, {A: rewards, B: [1, 0, 0]}), A) == expected


@pytest.mark.parametrize("one, two, expected", [([0, 0, 0], [0, 0, 1], S), ([0, 0, 0], [0, 0, 0], LO),
                                                ([0, 0, INFRA], [0, 0, 0], IN), ([0, 0, 0], [1, "-", "-"], S),
                                                ([0, 0, 0], [0, 0, "-"], IN), (["-", INFRA, "-"], [0, 0, 0], IN)])
def test_both_stages_through_the_launchers_export(tmp_path, one, two, expected):
    """Stage two funds every competition with no medal among stage one's observations, whatever their number."""
    result = _compute(tmp_path, {A: one, B: [0, 0, 0]}, {A: two, B: [0, 0, 0]})
    assert _class(result, A) == expected


def test_no_medal_in_five_observations_names_the_one_missing(tmp_path):
    screen = _compute(tmp_path, {A: [0, 0, INFRA], B: [0, 0, 0]}, {A: [0, 0, 0], B: [0, 0, 0]})["competitions"][A]["screen"]
    assert (screen["class"], screen["observations"], screen["missing"]) == (IN, 5, 1)


def test_open_slots_make_a_competition_pending_with_its_counts_so_far(tmp_path):
    screen = _compute(tmp_path, {A: [0, 0, OPEN], B: [1, 0, 0]}, end_one=None)["competitions"][A]["screen"]
    assert (screen["class"], screen["observations"], screen["open"]) == (PE, 2, 1)


def test_a_slot_whose_last_start_was_cut_is_open_while_the_tranche_runs(tmp_path):
    screen = _compute(tmp_path, {A: [0, 0, CUT], B: [1, 0, 0]}, end_one=None)["competitions"][A]["screen"]
    assert (screen["class"], screen["open"]) == (PE, 1)


def test_a_competition_with_no_observation_while_its_stage_runs_is_pending(tmp_path):
    assert _class(_compute(tmp_path, {A: ["-", "-", "-"], B: [1, 0, 0]}, end_one=None), A) == PE


def test_a_competition_stage_two_did_not_fund_says_so(tmp_path):
    result = _compute(tmp_path, {A: [0, 0, 0], B: [0, 0, 0], C: [0, 0, 0]}, {A: [0, 0, 1], B: [0, 0, 0]})
    assert (_class(result, A), _class(result, C)) == (S, NF)


def test_with_no_second_stage_every_undecided_competition_is_not_funded(tmp_path):
    result = _compute(tmp_path, {A: [0, 0, 0], B: [1, 0, 0]}, no_stage_two=True)
    assert (_class(result, A), _class(result, B)) == (NF, S)


# ---- 2. Only observations decide ---------------------------------------------------------------------------------

@pytest.mark.parametrize("kind", sorted(NOT_COUNTED))
def test_a_start_that_is_no_observation_never_turns_into_a_count(tmp_path, kind):
    screen = _compute(tmp_path, {A: [1, 1, NOT_COUNTED[kind]], B: [1, 0, 0]})["competitions"][A]["screen"]
    assert (screen["class"], screen["observations"], screen["medals"]) == (IN, 2, 2)


@pytest.mark.parametrize("kind", sorted(NOT_COUNTED))
def test_a_start_that_is_no_observation_is_listed_and_never_scored(tmp_path, kind):
    stage = _compute(tmp_path, {A: [0, 0, NOT_COUNTED[kind]], B: [1, 0, 0]})["competitions"][A]["stage_one"]
    listed = [e["start"] for e in stage["not_counted"]]
    assert (listed, [a["start"] for a in stage["attempts"]], all(e["reason"] for e in stage["not_counted"])) == (
        [3], [1, 2], True)


def test_a_contaminated_observation_is_listed_and_enters_no_count(tmp_path):
    stage = _compute(tmp_path, {A: [1, 1, CONTAMINATED], B: [1, 0, 0]})["competitions"][A]
    assert (stage["screen"]["class"], stage["stage_one"]["medals"],
            [e["start"] for e in stage["stage_one"]["not_counted"]]) == (IN, 2, [3])


def test_a_cut_is_counted_as_a_cut_and_its_rerun_slot_as_the_observation(tmp_path):
    stage = _compute(tmp_path, {A: [[CUT, 1], 1, 1], B: [1, 0, 0]})["competitions"][A]
    assert (stage["screen"]["class"], stage["stage_one"]["cuts"]) == (AB, 1)


def test_the_cost_of_a_competition_counts_every_start_cuts_and_failures_included(tmp_path):
    stage = _compute(tmp_path, {A: [[CUT, 0], INFRA, 1], B: [1, 0, 0]})["competitions"][A]["stage_one"]
    assert stage["usd"] == pytest.approx(4.0)


# ---- 3. The graded outcomes come from the result that gave the reward ---------------------------------------------

def _one(tmp_path, rewards, files=None, regrades=None):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: rewards, B: [1, 0, 0]}, files=files, regrades=regrades)
    return readout.compute(stage_one, time_zone=ZoneInfo(ZONE))


def test_score_and_percentile_come_from_the_trial_when_the_trial_gave_the_reward(tmp_path):
    attempt = _one(tmp_path, [1, 0, 0])["competitions"][A]["stage_one"]["attempts"][0]
    expected = _rewards(1)
    assert (attempt["score"], attempt["percentile"], attempt["medal"], attempt["source"]) == (
        expected["score"], expected["percentile"], 1, "trial")


@pytest.mark.parametrize("trial, n", [(None, 1), (_rewards(0, 0.5), 1), (None, 2)],
                         ids=["case-1-regrade-1", "case-2-regrade-1", "case-1-regrade-2"])
def test_score_and_percentile_come_from_the_regrade_that_gave_the_reward(tmp_path, trial, n):
    regraded = _rewards(2, 0.9)
    attempt = _one(tmp_path, [1, 0, 0], regrades={1: (trial, regraded, n)})["competitions"][A]["stage_one"][
        "attempts"][0]
    assert (attempt["score"], attempt["percentile"], attempt["medal"], attempt["source"]) == (
        regraded["score"], regraded["percentile"], 2, f"regrade {n}")


def test_a_submission_with_no_score_has_no_score_or_percentile_and_counts_as_invalid(tmp_path):
    stage = _one(tmp_path, [0, 0, 1], files={1: _rewards(0, None)})["competitions"][A]["stage_one"]
    first = stage["attempts"][0]
    assert ((first["score"], first["percentile"], first["valid"]), stage["valid"], stage["invalid"]) == (
        (None, None, 0), 2, 1)


def test_an_attempt_whose_grader_caught_an_error_is_listed_for_a_ruling_and_still_counted(tmp_path):
    result = _one(tmp_path, [1, 0, 0], files={1: _rewards(1, exception=True)})
    stage = result["competitions"][A]["stage_one"]
    assert ([a["start"] for a in stage["grader_exceptions"]], stage["grader_exception"], stage["medals"],
            _class(result, A)) == ([1], 1, 1, S)


def test_a_reward_file_without_the_grader_exception_field_reads_as_no_exception(tmp_path):
    rewards = {k: v for k, v in _rewards(1).items() if k != "grader_exception"}
    stage = _one(tmp_path, [1, 0, 0], files={1: rewards})["competitions"][A]["stage_one"]
    assert (stage["grader_exceptions"], stage["grader_exception"]) == ([], 0)


def test_a_valid_submission_with_no_score_is_counted_as_valid_not_scored(tmp_path):
    stage = _one(tmp_path, [1, 0, 0], files={2: _rewards(0, float("nan"), valid=True)})["competitions"][A][
        "stage_one"]
    second = stage["attempts"][1]
    assert ((second["valid"], second["score"], second["percentile"]), stage["valid"], stage["valid_not_scored"]) == (
        (1, None, None), 3, 1)


def test_the_above_median_count_is_read_from_the_result_files(tmp_path):
    assert _one(tmp_path, [1, 0, 1])["competitions"][A]["stage_one"]["above_median"] == 2


THRESHOLDS = {"bronze_threshold": 0.75, "silver_threshold": 0.85, "gold_threshold": 0.95, "median_threshold": 0.7}


def test_the_thresholds_are_read_from_the_reward_file_and_absent_ones_are_not_recorded(tmp_path):
    files = {1: _rewards(1, thresholds=THRESHOLDS)}
    attempts = _one(tmp_path, [1, 0, 0], files=files)["competitions"][A]["stage_one"]["attempts"]
    assert (attempts[0]["thresholds"], attempts[1]["thresholds"]) == (
        {"bronze": 0.75, "silver": 0.85, "gold": 0.95, "median": 0.7},
        {"bronze": None, "silver": None, "gold": None, "median": None})


@pytest.mark.parametrize("change, code", [({"reward": 0, "medal": 0}, "reward-mismatch"), ({"medal": 0}, "reward-medal"),
                                          ({"medal": None}, "reward-field")])
def test_a_reward_file_that_does_not_hold_together_is_refused(tmp_path, change, code):
    rewards = {k: v for k, v in (_rewards(1) | change).items() if v is not None}
    assert _code(lambda: _one(tmp_path, [1, 0, 0], files={1: rewards})) == code


def test_an_observation_with_no_attempt_directory_is_refused(tmp_path):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [1, 0, 0], B: [1, 0, 0]})
    shutil.rmtree(stage_one[2] / "slots" / f"001-{json.loads(stage_one[1].read_text())['starts'][0]['slot']}")
    assert _code(lambda: readout.compute(stage_one, time_zone=ZoneInfo(ZONE))) == "no-attempt-directory"


# ---- 4. Rewards without a verifier result (fix round 1, ruling 2) --------------------------------------------------

def test_an_observation_whose_reward_has_no_verifier_result_stays_counted_and_is_listed(tmp_path):
    result = _one(tmp_path, [1, 0, 0], files={3: None})
    stage = result["competitions"][A]["stage_one"]
    listed = stage["rewards_without_result"]
    assert ((stage["observations"], stage["medals"], _class(result, A)), [e["start"] for e in listed],
            stage["reward_without_result"], bool(listed[0]["reason"])) == ((3, 1, S), [3], 1, True)


@pytest.mark.parametrize("rewards, unbacked, marked", [([1, 0, 0], 3, False), ([1, 0, 0], 1, True),
                                                        ([0, 0, 0], 3, False)],
                         ids=["a-zero-it-holds-without", "the-medal-it-rests-on", "a-zero-of-undecided"])
def test_a_class_that_rests_on_a_reward_without_a_verifier_result_is_marked(tmp_path, rewards, unbacked, marked):
    screen = _one(tmp_path, rewards, files={unbacked: None})["competitions"][A]["screen"]
    assert screen["rests_on_rewards_without_result"] is marked


# ---- 5. The stages are identified, not assumed (fix round 2, ruling 2) ---------------------------------------------

def test_stage_two_holding_a_competition_with_a_stage_one_medal_is_refused(tmp_path):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [1, 0, 0], B: [0, 0, 0]})
    stage_two = _tranche(tmp_path / "two", _two_criterion(stage_one, [A, B]), {A: [0, 0, 0], B: [0, 0, 0]})
    assert _code(lambda: readout.compute(stage_one, stage_two, time_zone=ZoneInfo(ZONE))) == "stage-two-medal"


@pytest.mark.parametrize("end, open_", [(None, False), (STOPPED, False), (ENDED, True)],
                         ids=["stage-one-running", "stage-one-stopped", "an-attempt-open"])
def test_stage_two_before_stage_one_has_settled_is_refused(tmp_path, end, open_):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [0, 0, OPEN if open_ else 0], B: [0, 0, 0]}, end=end)
    stage_two = _tranche(tmp_path / "two", _two_criterion(stage_one, [A, B]), {A: [0, 0, 0], B: [0, 0, 0]})
    assert _code(lambda: readout.compute(stage_one, stage_two, time_zone=ZoneInfo(ZONE))) == "stage-two-early"


def test_the_same_export_given_as_both_stages_is_refused(tmp_path):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [0, 0, 0], B: [0, 0, 0]})
    assert _code(lambda: readout.compute(stage_one, stage_one, time_zone=ZoneInfo(ZONE))) == "stage-number"


@pytest.mark.parametrize("field, value, code", [("stage.stage", 1, "stage-number"),
                                                ("stage.derived_from.export_label", "0" * 64, "derived-from"),
                                                ("stage.derived_from.export_sha256", "0" * 64, "derived-from"),
                                                ("stage.class", "gpu", "stage-class")])
def test_a_stage_two_not_derived_from_this_stage_one_is_refused(tmp_path, field, value, code):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [0, 0, 0], B: [0, 0, 0]})
    criterion = with_values(_two_criterion(stage_one, [A, B]), {field: value})
    stage_two = _tranche(tmp_path / "two", criterion, {A: [0, 0, 0], B: [0, 0, 0]})
    assert _code(lambda: readout.compute(stage_one, stage_two, time_zone=ZoneInfo(ZONE))) == code


def test_a_first_stage_that_is_a_stage_two_is_refused(tmp_path):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [0, 0, 0], B: [0, 0, 0]})
    stage_two = _tranche(tmp_path / "two", _two_criterion(stage_one, [A, B]), {A: [0, 0, 0], B: [0, 0, 0]})
    assert _code(lambda: readout.compute(stage_two, time_zone=ZoneInfo(ZONE))) == "stage-number"


def test_two_stages_in_one_state_root_are_refused(tmp_path):
    stage_one, stage_two = _stages(tmp_path, {A: [0, 0, 0], B: [0, 0, 0]}, {A: [0, 0, 0], B: [0, 0, 0]})
    shared = stage_two[:2] + (stage_one[2],)
    assert _code(lambda: readout.compute(stage_one, shared, time_zone=ZoneInfo(ZONE))) == "same-state"


def test_no_stage_two_is_refused_while_stage_one_has_open_slots(tmp_path):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [0, 0, OPEN], B: [0, 0, 0]}, end=None)
    assert _code(lambda: readout.compute(stage_one, no_stage_two=True, time_zone=ZoneInfo(ZONE))) == (
        "no-stage-two-early")


def test_an_export_with_no_scheduled_competition_is_refused(tmp_path):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [1, 0, 0], B: [1, 0, 0]})
    doc = json.loads(stage_one[1].read_text())
    stage_one[1].write_text(json.dumps(doc | {"slots": [], "starts": [], "open": []}))
    assert _code(lambda: readout.compute(stage_one, time_zone=ZoneInfo(ZONE))) == "empty-stage"


def test_a_screen_criterion_with_more_than_one_effort_is_refused(tmp_path):
    stage_one = _placement(tmp_path, {A: {"low": [1, 0, 0]}})
    criterion = with_values(SCREEN, {"attempt.efforts": ["low", "medium"]})
    assert _code(lambda: readout.compute((criterion, *stage_one[1:]), time_zone=ZoneInfo(ZONE))) == "effort"


def test_a_screen_criterion_with_another_number_of_rounds_is_refused(tmp_path):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [1, 0, 0], B: [1, 0, 0]})
    criterion = with_values(SCREEN, {"schedule.rounds": 4})
    assert _code(lambda: readout.compute((criterion, *stage_one[1:]), time_zone=ZoneInfo(ZONE))) == "rounds"


# ---- 6. The placement: the ladder's pooled label once decided, never pooled with the screen ------------------------

FIFTEEN_NONE = {"low": [0] * 5, "medium": [0] * 5, "high": [0] * 5}
THREE_OF_FIFTEEN = {"low": [1, 0, 0, 0, 0], "medium": [1, 0, 0, 0, 0], "high": [1, 0, 0, 0, 0]}


def test_the_screens_attempts_are_never_pooled_into_the_placement_count(tmp_path):
    placed = _compute(tmp_path, {A: [1, 1, 0], B: [1, 0, 0]}, placement={A: FIFTEEN_NONE})["placement"][
        "competitions"][A]
    assert ((placed["K"], placed["n"], placed["label"]), (placed["screen"]["medals"], placed["screen"]["observations"])
            ) == ((0, 15, "floor"), (2, 3))


def test_the_placement_gives_the_ladders_label_and_both_exact_intervals(tmp_path):
    placed = _compute(tmp_path, {A: [1, 0, 0], B: [1, 0, 0]}, placement={A: THREE_OF_FIFTEEN})["placement"][
        "competitions"][A]
    assert ((placed["K"], placed["n"], placed["label"], placed["reported_as"]),
            [round(100 * x, 1) for x in placed["interval_90"]], [round(100 * x, 1) for x in placed["interval_95"]]) == (
        (3, 15, "screened in", readout.IN_THE_BAND), [5.7, 44.0], [4.3, 48.1])


def _placed(tmp_path, table):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [1, 0, 0], B: [1, 0, 0]})
    placed = _placement(tmp_path, table, end=None)
    return readout.compute(stage_one, placement=placed, time_zone=ZoneInfo(ZONE))["placement"]["competitions"][A]


def test_a_placement_four_of_twelve_with_three_open_is_in_progress(tmp_path):
    placed = _placed(tmp_path, {A: {"low": [1, 1, 0, 0, "-"], "medium": [1, 0, 0, 0, "-"], "high": [1, 0, 0, 0, "-"]}})
    assert (placed["status"], placed["label"], placed["K"], placed["n"], placed["open"]) == (
        readout.IN_PROGRESS, None, 4, 12, 3)


def test_a_placement_no_open_outcome_could_change_is_labelled(tmp_path):
    placed = _placed(tmp_path, {A: {"low": [1, 1, 1, 0, "-"], "medium": [1, 1, 0, 0, "-"], "high": [1, 0, 0, 0, "-"]}})
    assert (placed["status"], placed["label"], placed["open"]) == ("decided", "above the band", 3)


def test_an_open_placement_slot_that_may_end_with_no_observation_keeps_it_in_progress(tmp_path):
    """Every outcome that adds an observation keeps 1 to 5 of 15 in the band; a high slot lost leaves high at three,
    under the ladder's four per effort, which is not screened."""
    placed = _placed(tmp_path, {A: {"low": [0, 0, 0, 0, "-"], "medium": [0, 0, 0, 0, "-"], "high": [1, 0, 0, "-", "-"]}})
    assert (placed["status"], placed["open"]) == (readout.IN_PROGRESS, 4)


def test_a_competition_that_did_not_survive_the_screen_is_not_placed(tmp_path):
    assert _code(lambda: _compute(tmp_path, {A: [1, 1, 1], B: [1, 0, 0]}, placement={A: FIFTEEN_NONE})) == (
        "not-survivor")


# ---- 7. The exact intervals ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("k, expected", [(1, (0.3, 27.9)), (2, (2.4, 36.3)), (3, (5.7, 44.0)), (4, (9.7, 51.1)),
                                         (5, (14.2, 57.7))])
def test_the_90_percent_intervals_of_1_to_5_of_fifteen_are_m1s(k, expected):
    assert tuple(round(100 * x, 1) for x in readout.interval(k, 15, 0.90)) == expected


@pytest.mark.parametrize("n", [1, 3, 6, 15])
@pytest.mark.parametrize("level", [0.90, 0.95])
def test_at_the_edges_the_interval_has_its_closed_form(n, level):
    tail = (1 - level) / 2
    none, every = readout.interval(0, n, level), readout.interval(n, n, level)
    assert none == pytest.approx((0.0, 1 - tail ** (1 / n)), abs=1e-12) and every == pytest.approx(
        (tail ** (1 / n), 1.0), abs=1e-12)


# ---- 8. Metered usage per calendar day, beside the settled total (M9, "The day") ----------------------------------

def _at(*fields):
    return datetime.datetime(*fields, tzinfo=ZoneInfo(ZONE)).timestamp()


def _logged(tmp_path, rows):
    _log(tmp_path, rows)
    return readout.per_day([tmp_path], ZoneInfo(ZONE))


def test_a_request_received_after_midnight_counts_on_the_later_day(tmp_path):
    rows = [{"time": _at(2026, 11, 20, 23, 59, 59), "slot": "x", "usd": 1.25},
            {"time": _at(2026, 11, 21, 0, 0, 1), "slot": "x", "usd": 2.5},
            {"time": _at(2026, 11, 21, 0, 0, 2), "slot": None, "status": 403, "refused": "slot cap reached"}]
    assert _logged(tmp_path, rows) == {"2026-11-20": 1.25, "2026-11-21": 2.5}


@pytest.mark.parametrize("line", ['{"time": 1795000000, "usd": NaN}', '{"time": 1795000000, "usd": -1}',
                                  '{"time": 1795000000, "usd": "1"}', '{"usd": 1}', '{"time": true, "usd": 1}',
                                  '{"time": 1795000000, "usd": 1', '[1]', '{"time": 1, "time": 2, "usd": 1}',
                                  '{"time": 1795000000, "usd": 1, "slot_usd": Infinity}'],
                         ids=["nan", "negative", "string", "no-time", "bool-time", "broken", "not-an-object",
                              "repeated-key", "infinity-elsewhere"])
def test_a_malformed_request_log_row_is_a_refusal_that_names_the_row(tmp_path, line):
    (tmp_path / "passthrough").mkdir()
    (tmp_path / "passthrough" / "requests.jsonl").write_text('{"time": 1795000000, "usd": 1}\n' + line + "\n")
    with pytest.raises(readout.ReadoutError) as caught:
        readout.per_day([tmp_path], ZoneInfo(ZONE))
    assert (caught.value.code, caught.value.where) == ("request-log", f"{tmp_path / 'passthrough' / 'requests.jsonl'}:2")


def test_the_per_day_total_sums_every_stage_s_request_log(tmp_path):
    result = _compute(tmp_path, {A: [0, 0, 0], B: [0, 0, 0]}, {A: [0, 0, 1], B: [0, 0, 0]})
    assert sum(result["per_day_usd"].values()) == pytest.approx(12.0)


def test_the_metered_figure_is_printed_beside_the_settled_total(tmp_path):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [1, 0, 0], B: [1, 0, 0]})
    meter = readout.compute(stage_one, time_zone=ZoneInfo(ZONE))["meter"]["one"]
    assert (meter["metered_usd"], meter["settled_usd"], meter["difference_usd"], meter["warning"]) == (
        6.0, 6.0, 0.0, False)


def test_a_metered_figure_off_the_settled_total_by_more_than_the_tolerance_is_a_warning(tmp_path):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [1, 0, 0], B: [1, 0, 0]},
                         extra_rows=[{"time": T0 + 99, "slot": "x", "usd": 0.5}])
    result = readout.compute(stage_one, time_zone=ZoneInfo(ZONE))
    warnings = [line for line in readout.table(result).splitlines() if line.startswith(readout.WARNING)]
    assert (result["meter"]["one"]["difference_usd"], result["meter"]["one"]["warning"], len(warnings)) == (
        0.5, True, 1)


def test_the_document_states_the_day_rule(tmp_path):
    assert _compute(tmp_path, {A: [1, 0, 0], B: [1, 0, 0]})["day_rule"] == readout.DAY_RULE


# ---- 9. A stop places nothing ------------------------------------------------------------------------------------

def test_a_stage_one_stop_classes_nothing_and_names_the_rule(tmp_path):
    result = _compute(tmp_path, {A: [1, 1, 1], B: [1, 0, 0]}, end_one=STOPPED)
    assert ({_class(result, A), _class(result, B)}, result["stop"]) == (
        {readout.WITHHELD}, {"stage": "one", "cause": STOPPED["cause"]})


def test_a_stage_two_stop_classes_nothing_of_stage_two(tmp_path):
    result = _compute(tmp_path, {A: [0, 0, 0], B: [0, 0, 0], C: [1, 0, 0]}, {A: [0, 1, 0], B: [0, 0, 0]},
                      end_two=STOPPED)
    assert (_class(result, A), _class(result, C), result["stop"]["stage"]) == (readout.WITHHELD, S, "two")


def test_a_placement_stop_places_nothing(tmp_path):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [1, 0, 0], B: [1, 0, 0]})
    placed = _placement(tmp_path, {A: THREE_OF_FIFTEEN}, end=STOPPED)
    result = readout.compute(stage_one, no_stage_two=True, placement=placed, time_zone=ZoneInfo(ZONE))
    assert (result["placement"]["competitions"][A]["label"], result["placement"]["competitions"][A]["status"],
            result["stop"]["stage"]) == (None, "stopped", "placement")


# ---- 10. A final readout reads the criterion of its label (the ladder's bound, with this family's paths) ------------

def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _manifested(root, frozen=True, change=None):
    """A tranche's criterion under root, as Task 4 places it, and a manifest in the ladder's format over it."""
    criterion = root / "experiments" / "mle_bench_tasks" / "tranches" / "screen-cpu" / "ladder.json"
    criterion.parent.mkdir(parents=True)
    criterion.write_text(json.dumps(SCREEN))
    files = {"experiments/mle_bench_tasks/tranches/screen-cpu/ladder.json": _sha(criterion.read_bytes())} | {
        f"experiments/{rel}": _sha((ROOT / "experiments" / rel).read_bytes())
        for rel in ("mle_bench_tasks/screen_readout.py", "long_horizon_tasks/readout.py",
                    "long_horizon_tasks/slot_record.py")}
    manifest = root / "manifest.json"
    manifest.write_bytes(json.dumps({"frozen": frozen, "not_covered": {}, "files": files}).encode())
    if change:
        criterion.write_text(json.dumps(with_values(SCREEN, change)))
    return criterion, manifest, _sha(manifest.read_bytes())


def test_a_final_readout_accepts_the_criterion_its_label_names(tmp_path):
    criterion, manifest, label = _manifested(tmp_path)
    assert readout.bound(criterion, manifest, label, root=tmp_path) is None


@pytest.mark.parametrize("case", ["not frozen", "another label", "a changed criterion", "outside the repository"])
def test_a_final_readout_refuses_a_criterion_its_label_does_not_name(tmp_path, case):
    criterion, manifest, label = _manifested(tmp_path / "repo", frozen=case != "not frozen",
                                             change={"attempt.model": "x"} if case == "a changed criterion" else None)
    root = tmp_path / "elsewhere" if case == "outside the repository" else tmp_path / "repo"
    label = "0" * 64 if case == "another label" else label
    assert _code(lambda: readout.bound(criterion, manifest, label, root=root)) == "label-binding"


# ---- 11. Output: one JSON document and a short table, deterministic; a rehearsal says so -------------------------

def _cli_args(stages):
    args = []
    for flag, (criterion, export, state) in stages:
        (state / "ladder.json").write_text(json.dumps(criterion))
        (state / "manifest.json").write_text(json.dumps({"frozen": False, "not_covered": {}, "files": {}}))
        args += [flag, str(export), str(state), str(state / "ladder.json"), str(state / "manifest.json")]
    return args


def _run(args):
    return subprocess.run([sys.executable, "-I", str(KIT / "screen_readout.py"), *args], capture_output=True,
                          text=True)


def test_the_command_writes_the_same_json_and_table_twice(tmp_path):
    stage_one, stage_two = _stages(tmp_path, {A: [1, 0, 0], B: [0, 0, 0], C: [0, 0, 0]}, {B: [0, 0, 1], C: [0, 0, 0]})
    args = _cli_args((("--stage-one", stage_one), ("--stage-two", stage_two)))
    (tmp_path / "stand-ins.json").write_text("{}")
    runs = []
    for out in ("a.json", "b.json"):
        done = _run([*args, "--time-zone", ZONE, "--rehearsal", str(tmp_path / "stand-ins.json"),
                     "--json", str(tmp_path / out)])
        runs.append((done.returncode, done.stdout, (tmp_path / out).read_bytes()))
    document = json.loads(runs[0][2])
    assert (runs[0] == runs[1], runs[0][0], [document["competitions"][n]["screen"]["class"] for n in CPU]) == (
        True, 0, [S, S, LO])


def test_a_rehearsal_says_so_in_the_document_and_on_the_tables_first_and_last_lines(tmp_path):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [1, 0, 0], B: [1, 0, 0]})
    result = readout.compute(stage_one, time_zone=ZoneInfo(ZONE), standins={})
    lines = readout.table(result).splitlines()
    assert (result["rehearsal"], lines[0], lines[-1]) == (True, readout.REHEARSAL_LINE, readout.REHEARSAL_LINE)


def test_a_final_readout_carries_no_rehearsal_line(tmp_path):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [1, 0, 0], B: [1, 0, 0]})
    result = readout.compute(stage_one, time_zone=ZoneInfo(ZONE))
    assert (result["rehearsal"], readout.REHEARSAL_LINE in readout.table(result).splitlines()) == (False, False)


def test_the_command_binds_a_final_readout_to_its_label_and_a_rehearsal_not(tmp_path):
    """The stage's manifest is not frozen and its criterion lies outside the repository: a final readout is refused
    before anything is written; the same inputs as a rehearsal are read."""
    args = _cli_args((("--stage-one", _tranche(tmp_path / "one", SCREEN, {A: [1, 0, 0], B: [1, 0, 0]})),))
    (tmp_path / "stand-ins.json").write_text("{}")
    final = _run([*args, "--time-zone", ZONE, "--json", str(tmp_path / "final.json")])
    rehearsal = _run([*args, "--time-zone", ZONE, "--rehearsal", str(tmp_path / "stand-ins.json")])
    assert (final.returncode, (tmp_path / "final.json").exists(), rehearsal.returncode) == (2, False, 0)


@pytest.mark.parametrize("case", ["empty export", "unknown zone", "a path for a zone"])
def test_the_command_refuses_with_exit_2_never_a_traceback(tmp_path, case):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [1, 0, 0], B: [1, 0, 0]})
    if case == "empty export":
        doc = json.loads(stage_one[1].read_text())
        stage_one[1].write_text(json.dumps(doc | {"slots": [], "starts": [], "open": []}))
    (tmp_path / "stand-ins.json").write_text("{}")
    zone = {"unknown zone": "Nowhere/Zone", "a path for a zone": "../etc/passwd"}.get(case, ZONE)
    done = _run([*_cli_args((("--stage-one", stage_one),)), "--time-zone", zone, "--rehearsal",
                 str(tmp_path / "stand-ins.json")])
    assert (done.returncode, "Traceback" in done.stderr) == (2, False)


def _row(result, name):
    """The table row of a competition, split at its columns."""
    line = next(line for line in readout.table(result).splitlines() if line.startswith(f"{name} "))
    return dict(zip(readout.COLUMNS, (cell.strip() for cell in line.split("|"))))


def test_the_table_shows_the_counts_a_person_rules_on(tmp_path):
    result = _one(tmp_path, [0, 0, 0], files={1: _rewards(0, exception=True), 3: None})
    row = _row(result, A)
    assert (row["grader exceptions"], row["rewards without a verifier result"], row["class"]) == ("1", "1", UN)


def test_the_table_prints_each_score_against_the_thresholds(tmp_path):
    lines = readout.table(_one(tmp_path, [1, 0, 0], files={1: _rewards(1, thresholds=THRESHOLDS)})).splitlines()
    first, second = [[cell.strip() for cell in line.split("|")] for line in lines
                     if line.strip().startswith("stage one start") and line.split("|")[1].strip() == A][:2]
    assert (first[3:], second[3:]) == (["bronze 0.75", "silver 0.85", "gold 0.95", "median 0.7"],
                                       ["bronze not recorded", "silver not recorded", "gold not recorded",
                                        "median not recorded"])


def test_the_document_names_the_inputs_the_exports_do_not_carry(tmp_path):
    assert set(_compute(tmp_path, {A: [1, 0, 0], B: [1, 0, 0]})["not_in_the_inputs"]) == {"installed packages"}


# GPU rows, by the minute each stands for, against attempt windows [1000 i, 1000 i + 500] of starts 1 to 6 (M5):
# start 1 a process; start 2 none; start 3 unreadable; start 4 a process in the minute before it opened; start 5 a
# process after it closed; start 6 a process in a minute that ends before it opened.
GPU_ROWS = [(1100, [{"pid": "7", "name": "python3", "mib": "512"}]), (2100, []), (3100, None),
            (3970, [{"pid": "7", "name": "python3", "mib": "512"}]), (5600, [{"pid": "7", "name": "x", "mib": "1"}]),
            (5939, [{"pid": "7", "name": "x", "mib": "1"}])]


def _gpu_stage(tmp_path):
    stage_one = _tranche(tmp_path / "one", SCREEN, {A: [1, 0, 0], B: [0, 0, 0]})
    state = stage_one[2]
    for attempt in sorted((state / "slots").iterdir()):
        i = int(attempt.name[:3])
        for name, key, at in (("slot.json", "opened", 1000.0 * i), ("settled.json", "closed", 1000.0 * i + 500)):
            doc = json.loads((attempt / name).read_text())
            (attempt / name).write_text(json.dumps({**doc, key: at}))
    (state / "screen").mkdir()
    (state / "screen" / "gpu.jsonl").write_text("".join(json.dumps({"at": at, "processes": p}) + "\n"
                                                        for at, p in GPU_ROWS))
    return stage_one


def test_an_observation_during_which_the_gpu_record_lists_a_process_or_could_not_be_read_is_flagged(tmp_path):
    result = readout.compute(_gpu_stage(tmp_path), time_zone=ZoneInfo(ZONE))
    held = {a["start"]: a["gpu_held"] for c in result["competitions"].values()
            for a in c["stage_one"]["attempts"]}
    assert (held, {n: c["stage_one"]["gpu_held"] for n, c in result["competitions"].items()}) == (
        {1: [1100], 2: [], 3: [3100], 4: [3970], 5: [], 6: []}, {A: 2, B: 1, C: 0})


def test_the_table_marks_a_competition_whose_observations_the_gpu_record_flags(tmp_path):
    lines = readout.table(readout.compute(_gpu_stage(tmp_path), time_zone=ZoneInfo(ZONE))).splitlines()
    marks = {line.split("|")[0].strip(): line.split("|")[-1].strip() for line in lines[1:]
             if line.split("|")[0].strip() in (A, B)}
    assert marks == {A: readout.GPU_MARK.format(2), B: readout.GPU_MARK.format(1)}


def test_a_gpu_record_row_without_a_time_is_refused(tmp_path):
    stage_one = _gpu_stage(tmp_path)
    (stage_one[2] / "screen" / "gpu.jsonl").write_text('{"processes": []}\n')
    assert _code(lambda: readout.compute(stage_one, time_zone=ZoneInfo(ZONE))) == "gpu-record"
