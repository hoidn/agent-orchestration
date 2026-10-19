"""The frozen three-arm readout criterion (criteria/three_arm.json): judges, their bindings, the type checker and
the subset rule are named before any score exists. No provider is called."""

import json

from tests.experiments.compare_harness_support import REPO

CRITERION = REPO / "experiments" / "orc_structural_search" / "criteria" / "three_arm.json"
FIELDS = {"experiment", "plan", "tasks", "base_commits", "judges", "judge_bindings", "anchors", "parents", "envelope",
          "type_checker", "collapse_threshold", "locality", "subset", "primary_measure", "budget", "model_policy",
          "written_before_scoring", "scoring_join"}


def test_three_arm_criterion_names_the_judges_type_checker_and_subset_rule():
    criterion = json.loads(CRITERION.read_text())
    assert (FIELDS - criterion.keys(), criterion["judges"], sorted(criterion["judge_bindings"]),
            [(REPO / path).is_file() for path in criterion["judge_bindings"].values()],
            criterion["type_checker"]["name"], criterion["subset"]["per_arm"], criterion["written_before_scoring"]) == (
        set(), ["claude-opus-5-5", "gpt-6.1-sol"], ["claude-opus-5-5", "gpt-6.1-sol"], [True, True], "pyright", 2,
        True)
