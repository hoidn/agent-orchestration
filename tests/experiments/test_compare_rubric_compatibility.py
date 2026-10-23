"""Historical descriptive rubric metadata does not select a different scoring workflow."""

import json
from collections import UserDict

import pytest

from experiments.compare import pool as pooling, repos, summarize
from experiments.orc_structural_search import qualification
from tests.experiments.compare_harness_support import REPO, drive, edit, world  # noqa: F401
from tests.experiments.qualification_support import qualified
from tests.experiments.test_compare_pool_summarize import REFERENCE_RUBRIC, score

PHASE2 = REPO / "experiments/orc_structural_search/criteria/phase2.json"
DESCRIPTION = repos.load(PHASE2)["rubric"]


@pytest.mark.parametrize("decoded", [False, True])
def test_actual_phase2_rubric_description_selects_historical_workflow(decoded):
    source = UserDict(repos.load(PHASE2)) if decoded else PHASE2
    assert pooling.rubric(source) == pooling.DEFAULT_RUBRIC


@pytest.mark.parametrize("selected", [None, [], 1, False])
def test_rubric_refuses_invalid_selector_types(selected):
    with pytest.raises(SystemExit, match="^rubric"):
        pooling.rubric({"rubric": selected})


def test_mapping_rubric_remains_a_selected_reference_workflow():
    assert pooling.rubric({"rubric": REFERENCE_RUBRIC}) == REFERENCE_RUBRIC


@pytest.mark.parametrize("mapping_description", [False, True])
def test_historical_description_pools_and_summarizes_with_historical_criteria(world, mapping_description):
    repos.dump(world.criterion, repos.load(world.criterion) | {"rubric": DESCRIPTION})
    run, _ = drive(world, "direct_task", [edit("$PWD", "a + b")], True)
    out = world.outside / "historical-description"
    mapping = pooling.pool(world.task, world.criterion, out, ["judge-a", "judge-b"], [run])
    assert mapping["rubric"] == pooling.DEFAULT_RUBRIC
    if mapping_description:
        mapping["rubric"] = DESCRIPTION
        repos.dump(out / "records/mapping.json", mapping)
        for judge, info in mapping["judges"].items():
            (out / "judges" / info["dir"] / "tmp").rmdir()
            (out / "records/judges" / judge / "sandbox.json").unlink()
            (out / "records/judges" / judge).rmdir()
        pooling.write_score_inputs(out, mapping, "add returns the sum", world.runtime)
    for judge in mapping["judges"]:
        inputs = repos.load(out / "records" / f"score-inputs-{judge}.json")
        assert all("reference" not in batch for batch in inputs["batches"])
        score(out, judge, mapping)
    results = summarize.summarize(out, world.criterion)
    assert set(results["agreement"]) == set(pooling.DEFAULT_RUBRIC["criteria"])
    assert results["runs"][0]["value"] == 4.5


def test_v1_dispatch_accepts_actual_phase2_description_with_qualified_evidence(tmp_path):
    evidence = qualified(tmp_path / "qualified")
    frozen = repos.load(evidence.criterion) | {"rubric": DESCRIPTION}
    repos.dump(evidence.criterion, frozen)
    assert qualification.validate(evidence.criterion, runtime=evidence.runtime, operation="quality")["mode"] == "quality"


def test_v1_dispatch_still_refuses_a_selected_reference_rubric(tmp_path):
    evidence = qualified(tmp_path / "qualified")
    frozen = repos.load(evidence.criterion) | {"rubric": REFERENCE_RUBRIC}
    repos.dump(evidence.criterion, frozen)
    with pytest.raises(ValueError, match="unsupported v1 rubric selection"):
        qualification.validate(evidence.criterion, runtime=evidence.runtime, operation="quality")
