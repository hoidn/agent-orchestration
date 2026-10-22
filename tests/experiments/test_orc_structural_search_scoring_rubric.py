"""Selected rubric and shared-writer structural boundaries, with no provider calls."""

import json

import pytest

from experiments.compare import pool as pooling
from tests.experiments.compare_harness_support import REPO, world  # noqa: F401
from tests.experiments.test_orc_structural_search_scoring import evaluations  # noqa: F401


def test_shared_writer_preserves_validated_qualification(evaluations, world, monkeypatch):
    from experiments.orc_structural_search import scoring
    out, mapping, runs, _, criterion = evaluations
    written = []
    original = pooling.write_pool
    def observed(*args, **kwargs):
        written.append(kwargs["qualification"])
        return original(*args, **kwargs)
    monkeypatch.setattr(pooling, "write_pool", observed)
    records = {str(path): json.loads((path / "record.json").read_text()) for path in runs.values()}
    scoring.build_pool(world.task, criterion, out.with_name("shared-pool"),
                       ["judge-a", f"judge-b={REPO / 'experiments/compare/providers/score_codex.json'}"],
                       records, key=lambda row: row[0])
    assert written == [mapping["qualification"]]
    assert json.loads((out.with_name("shared-pool") / "records/mapping.json").read_text())["qualification"] == written[0]


@pytest.mark.parametrize("reference", [False, True])
def test_shared_writer_refuses_unqualified_structural_pool_before_creating_it(world, reference):
    from experiments.orc_structural_search.scoring import build_pool
    criterion = json.loads(world.criterion.read_text())
    if reference:
        criterion["rubric"] = {"workflow": "score_ref.orc", "entry": "score_ref::score",
                               "criteria": ["completeness", "correctness", "scope", "layering"], "reference": "upstream"}
    world.criterion.write_text(json.dumps(criterion))
    out = world.outside / "unqualified"
    with pytest.raises(ValueError, match="qualification|purpose|criterion"):
        build_pool(world.task, world.criterion, out, ["judge-a"], {"run": {"runtime": str(world.runtime)}}, key=str)
    assert not out.exists()


def test_reference_rubric_planned_judged_uses_each_tasks_capacity(world):
    from experiments.orc_structural_search.adaptive import planned_judged
    from experiments.orc_structural_search.scoring import fillers_per_batch
    for name in ("partial", "mutant"):
        (world.task / f"anchors/{name}.diff").write_text("")
    rule = {"reference": "upstream"}
    capacity = fillers_per_batch(world.task, rule)
    assert planned_judged([1] * 11, 2, 1, 2, capacities=[capacity, 8]) == 32


def test_shared_writer_refuses_reference_rubric_even_with_otherwise_valid_v1_evidence(evaluations, world):
    from experiments.orc_structural_search.scoring import build_pool
    _, _, runs, _, criterion = evaluations
    frozen = json.loads(criterion.read_text())
    frozen["rubric"] = {"workflow": "score_ref.orc", "entry": "score_ref::score",
                        "criteria": ["completeness", "correctness", "scope", "layering"], "reference": "upstream"}
    criterion.write_text(json.dumps(frozen))
    records = {str(path): json.loads((path / "record.json").read_text()) for path in runs.values()}
    out = world.outside / "v2-not-admitted"
    with pytest.raises(ValueError, match="rubric"):
        build_pool(world.task, criterion, out,
                   ["judge-a", f"judge-b={REPO / 'experiments/compare/providers/score_codex.json'}"],
                   records, key=lambda row: row[0])
    assert not out.exists()


def test_control_means_capacity_agrees_with_generation_and_judging_reservations(world):
    from experiments.orc_structural_search import judging, scoring
    from experiments.orc_structural_search.adaptive import planned_judged
    for role in ('stub', 'mutant', 'partial'):
        (world.task / f'anchors/{role}.diff').write_text('')
    criterion = {'calibration': {'rule': 'control-means-v1', 'margin': 1, 'error_rate': 0},
                 'anchors': {world.task.name: {'upstream': 'upstream', 'stub': 'stub', 'mutant': 'mutant'}}}
    capacity = scoring.fillers_per_batch(world.task, {'reference': None}, criterion)
    jobs = [object()] * 14
    batches = scoring.split_batches(jobs, key=lambda _: 0, size=capacity)
    assert capacity == 7
    assert [len(batch) for batch in batches] == [7, 7]
    evaluation_and_judging = planned_judged([1] * len(jobs), 1, 1, 2, capacities=[capacity])
    launch = {'evidence_root': world.tmp / 'evidence', 'pools_root': world.tmp / 'pools'}
    launch['evidence_root'].mkdir()
    reserved_judging = judging.planned_judging(jobs, 1, [world.task], 1, launch,
                                               {'judges': ['judge-a', 'judge-b']}, [capacity])
    assert reserved_judging == len(batches) * 2 == evaluation_and_judging - len(jobs)
