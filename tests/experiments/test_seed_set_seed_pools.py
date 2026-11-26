"""The seed evaluation's two judge batches per task (`study.seed_batches`) on hand-built usable runs. No harness,
no provider, no file."""

import pytest

from experiments.seed_set import study

ARMS = ["direct", "retry_until_check", "implement_check_repair", "implement_review_revise"]  # arms.json order
PLANNED = {"direct": 6, "retry_until_check": 2, "implement_check_repair": 3, "implement_review_revise": 3}


def usable(counts):
    """`pool.pool_runs`' usable shape: arm -> [(records path, record)], each record with a final patch."""
    return {arm: [(f"/runs/{arm}-{k}", {"arm": arm, "patches": {"final": f"{arm}-{k}.diff"}}) for k in range(n)]
            for arm, n in counts.items()}


def placed(batches):
    """Records path -> index of the batch holding it, for every member."""
    return {path: index for index, batch in enumerate(batches) for path, _, _ in batch}


def test_the_planned_fourteen_runs_give_seven_and_seven():
    assert [len(b) for b in study.seed_batches(usable(PLANNED), ARMS, 0)] == [7, 7]


def test_each_usable_run_is_dealt_once_as_its_final_patch():
    runs = usable(PLANNED)
    members = [m for batch in study.seed_batches(runs, ARMS, 0) for m in batch]
    assert sorted((path, labels) for path, _, labels in members) == sorted(
        (path, ["final"]) for rows in runs.values() for path, _ in rows)


def test_every_arm_alternates_between_the_batches():
    runs = usable(PLANNED)
    where = placed(study.seed_batches(runs, ARMS, 0))
    sequences = {arm: [where[path] for path, _ in rows] for arm, rows in runs.items()}
    assert all(s[1:] == [1 - i for i in s[:-1]] for s in sequences.values())


def three_run_arms_over(tasks):
    """Per three-run arm, its runs in batch 0 and batch 1 over consecutive tasks, each task's usable runs given."""
    counts = {arm: [0, 0] for arm in ("implement_check_repair", "implement_review_revise")}
    for index, runs in enumerate(tasks, start=4):
        where = placed(study.seed_batches(runs, ARMS, index))
        for arm, count in counts.items():
            for path, _ in runs[arm]:
                count[where[path]] += 1
    return counts


def test_over_two_consecutive_tasks_each_three_run_arm_has_three_runs_in_each_batch():
    counts = three_run_arms_over([usable(PLANNED), usable(PLANNED)])
    assert counts == {arm: [3, 3] for arm in counts}


def test_a_direct_run_missing_on_one_task_leaves_the_three_run_arms_balanced_over_the_pair():
    counts = three_run_arms_over([usable({**PLANNED, "direct": 5}), usable(PLANNED)])
    assert counts == {arm: [3, 3] for arm in counts}


def test_a_batch_above_eight_runs_is_refused():
    with pytest.raises(SystemExit, match="batch of 9"):
        study.seed_batches(usable({"direct": 9, "implement_check_repair": 7}), ARMS, 0)


def test_an_arm_alternates_within_a_task_whatever_the_task_index():
    runs = usable(PLANNED)
    where = placed(study.seed_batches(runs, ARMS, 1))
    assert [where[path] for path, _ in runs["direct"]] == [1, 0, 1, 0, 1, 0]


def test_sixteen_usable_runs_fill_both_batches_to_eight():
    assert [len(b) for b in study.seed_batches(usable({**PLANNED, "direct": 8}), ARMS, 0)] == [8, 8]


def test_seventeen_usable_runs_are_refused():
    with pytest.raises(SystemExit, match="17 usable runs"):
        study.seed_batches(usable({**PLANNED, "direct": 9}), ARMS, 0)


def test_one_usable_run_gives_one_batch():
    assert [len(b) for b in study.seed_batches(usable({"implement_review_revise": 1}), ARMS, 0)] == [1]


def test_a_run_without_a_final_patch_is_not_dealt():
    runs = usable({"direct": 2})
    runs["direct"][0][1]["patches"] = {}
    assert list(placed(study.seed_batches(runs, ARMS, 0))) == ["/runs/direct-1"]


def test_an_arm_outside_the_arm_order_is_refused():
    with pytest.raises(SystemExit, match="direct_sonnet"):
        study.seed_batches(usable({"direct": 1, "direct_sonnet": 1}), ARMS, 0)
