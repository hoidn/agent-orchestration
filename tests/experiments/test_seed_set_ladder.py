"""The difficulty ladder's pure rules: the flat probe's table, the bisection, the choice of the 20 calibration
tasks, and the detector of an agent running the visible test itself."""

import json

import pytest

from experiments.seed_set import ladder

TIERS = {"T0": 8, "T1": 12, "T2": 12, "T3": 12, "T4": 12, "T5": 8, "T6": 8}
ROWS = ([{"id": f"{t}-{k:02d}", "tier": t, "form": ladder.tier_form(t)[1]} for t, n in TIERS.items() for k in range(n)]
        + [{"id": f"{t}w-{k:02d}", "tier": t, "form": ladder.WITHHELD} for t in ("T1", "T2", "T3", "T4")
           for k in range(12)])
ALL = dict.fromkeys(ladder.LADDER, 8)


def counts(picked):
    found = {}
    for _, rung in picked:
        found[rung] = found.get(rung, 0) + 1
    return found


def test_probe_tasks_are_a_rungs_first_four_in_seed_order():
    assert (ladder.probe_tasks(ROWS, "T3"), ladder.probe_tasks(ROWS, "T3w")[0]) == (
        ["T3-00", "T3-01", "T3-02", "T3-03"], "T3w-00")


def test_one_tier_in_band_is_drawn_and_filled_from_the_adjacent_tier_nearer_two():
    results = {"T1": 4, "T2": 4, "T3": 2, "T4": 1, "T5": 0}
    answer = ladder.table(results)
    assert (answer, counts(ladder.choose(ROWS, answer, results, 0.0))) == ({"chosen": "T3"}, {"T3": 12, "T4": 8})


def test_a_chosen_tiers_tasks_come_in_seed_order():
    results = {"T1": 4, "T2": 4, "T3": 2, "T4": 0, "T5": 0}
    picked = ladder.choose(ROWS, ladder.table(results), results, 0.0)
    assert [t for t, _ in picked[:3]] == ["T3-00", "T3-01", "T3-02"]


def test_two_tiers_in_band_take_the_one_nearer_two_and_a_tie_the_harder():
    assert (ladder.table({"T1": 4, "T2": 3, "T3": 2, "T4": 1, "T5": 0}),
            ladder.table({"T1": 4, "T2": 3, "T3": 1, "T4": 0, "T5": 0})) == ({"chosen": "T3"}, {"chosen": "T3"})


def test_no_tier_in_band_takes_ten_and_ten_across_the_band():
    results = {"T1": 4, "T2": 4, "T3": 4, "T4": 0, "T5": 0}
    answer = ladder.table(results)
    assert (answer, counts(ladder.choose(ROWS, answer, results, 0.0))) == ({"split": ["T3", "T4"]},
                                                                           {"T3": 10, "T4": 10})


def test_the_agent_checking_itself_in_80_percent_of_runs_switches_to_the_withheld_form():
    results = {"T1": 4, "T2": 4, "T3": 2, "T4": 1, "T5": 0}
    answer = ladder.table(results)
    assert (counts(ladder.choose(ROWS, answer, results, 0.80)), counts(ladder.choose(ROWS, answer, results, 0.79))) == (
        {"T3w": 12, "T4w": 8}, {"T3": 12, "T4": 8})


def test_t5_chosen_keeps_its_form_and_its_in_tree_neighbour():
    results = {"T1": 4, "T2": 4, "T3": 4, "T4": 4, "T5": 2}
    answer = ladder.table(results)
    assert (answer, counts(ladder.choose(ROWS, answer, results, 1.0))) == ({"chosen": "T5"}, {"T5": 8, "T4": 12})


@pytest.mark.parametrize("results, miss", [({"T1": 4, "T2": 4, "T3": 3, "T4": 4, "T5": 3}, "all_easy"),
                                           ({"T1": 1, "T2": 0, "T3": 1, "T4": 0, "T5": 0}, "all_hard")])
def test_a_ladder_entirely_on_one_side_is_a_miss(results, miss):
    assert ladder.table(results) == {"miss": miss}


def test_bisection_starts_at_the_middle_and_stops_in_band():
    assert (ladder.next_rung({}, ALL), ladder.next_rung({"T3": 2}, ALL)) == ({"probe": ["T3"]}, {"chosen": "T3"})


def test_bisection_three_steps_up():
    steps = [ladder.next_rung(r, ALL) for r in ({"T3": 4}, {"T3": 4, "T5": 4}, {"T3": 4, "T5": 4, "T6": 4})]
    assert steps == [{"probe": ["T5"]}, {"probe": ["T6"]}, {"miss": "all_easy"}]


def test_bisection_three_steps_down():
    steps = [ladder.next_rung(r, ALL) for r in ({"T3": 0}, {"T3": 0, "T1": 0}, {"T3": 0, "T1": 0, "T0": 0})]
    assert steps == [{"probe": ["T1"]}, {"probe": ["T0"]}, {"miss": "all_hard"}]


def test_bisection_adjacent_four_and_zero_split():
    assert (ladder.next_rung({"T3": 4, "T5": 0}, ALL), ladder.next_rung({"T3": 4, "T5": 0, "T4": 0}, ALL)) == (
        {"probe": ["T4"]}, {"split": ["T3", "T4"]})


def test_bisection_contradiction_probes_the_remaining_rungs_flat():
    assert ladder.next_rung({"T3": 0, "T5": 4}, ALL) == {"probe": ["T0", "T1", "T2", "T4", "T6"]}


def test_bisection_skips_a_rung_the_builder_could_not_fill():
    rungs = {**ALL, "T0": 0, "T3": 2, "T6": 0}  # T1, T2, T4, T5 remain: the middle is T2
    assert (ladder.next_rung({}, rungs), ladder.next_rung({"T2": 4}, rungs)) == ({"probe": ["T2"]},
                                                                               {"probe": ["T4"]})


def test_bisection_over_the_easy_extension_orders_withheld_rungs_by_tier():
    rungs = dict.fromkeys(ladder.EASY_EXTENSION, 12)
    assert ladder.next_rung({}, rungs) == {"probe": ["T3w"]}


TARGETS = ["tests/test_visible_add.py::test_visible"]


@pytest.mark.parametrize("command", [
    "cd /work && python -m pytest -q tests/test_visible_add.py",
    "pytest tests/test_visible_add.py::test_visible -x",
    "pytest -q tests/",  # the whole test directory
    "python3 -m pytest",
    "cd tests && pytest test_visible_add.py",
    "pytest 'tests/test_visible_*.py'",
    "python dev_check.py",
    "git diff && pytest -p no:cacheprovider tests",
])
def test_detector_sees_the_visible_test_run(command):
    assert ladder.ran_visible_test(command, TARGETS) is True


@pytest.mark.parametrize("command", [
    "pytest tests/test_other.py",
    "python -m pytest -k add tests/test_other.py",
    "pytest -p no:cacheprovider tests/test_other.py",
    "grep -n add tests/test_visible_add.py",
    "python -c 'import pkg.calc'",
])
def test_detector_ignores_other_commands(command):
    assert ladder.ran_visible_test(command, TARGETS) is False


def session(home, name, commands):
    path = home / ".claude" / "projects" / "-work-cand-1" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "running"}, {"type": "tool_use", "name": "Bash", "input": {"command": c}}]}}) + "\n"
        for c in commands) + "not json\n")


def test_self_check_reads_every_session_including_a_subagents(tmp_path):
    session(tmp_path / "a", "s.jsonl", ["ls", "pytest tests/test_other.py"])
    session(tmp_path / "b", "s.jsonl", ["ls"])
    session(tmp_path / "b", "s/subagents/agent-1.jsonl", ["python -m pytest tests"])
    assert (ladder.self_checked(tmp_path / "a", TARGETS), ladder.self_checked(tmp_path / "b", TARGETS)) == (
        False, True)


def test_visible_targets_come_from_the_packages_check(tmp_path):
    (tmp_path / "seed").mkdir()
    (tmp_path / "seed" / "dev-check.json").write_text(json.dumps({"argv": [
        "/usr/bin/python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_x.py::test_y"]}))
    assert ladder.visible_targets(tmp_path) == ["tests/test_x.py::test_y"]
