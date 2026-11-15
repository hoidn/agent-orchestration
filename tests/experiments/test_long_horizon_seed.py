"""The long-horizon seeds (`experiments/long_horizon_seed/`) against a scripted `claude` on a closed `PATH`.

Each scenario of `demo.py` is one run of a seed through the command line: it must end with the declared result,
committed steps and provider calls; a killed run, once resumed, must start no step it had committed; every step after
the setup must be given the guide path the setup reported; and no run may leave a socket directory outside its world
(the Agent Sessions seed must name one, so that the check has something to look at). The seeds are frozen: the last
test recomputes every entry of `seeds.json`.
"""

import json

import pytest

from experiments.long_horizon_seed import demo, freeze

SCENARIOS = [(program, scenario) for program, scenarios in demo.PROGRAMS.items() for scenario in scenarios]


@pytest.mark.parametrize(("program", "scenario"), SCENARIOS, ids=lambda value: value)
def test_scenario_ends_as_declared(tmp_path, program, scenario):
    assert demo.run(tmp_path, program, scenario) == demo.expected(program, scenario)


@pytest.mark.parametrize("program", demo.PROGRAMS)
def test_digest_ignores_the_hash_seed_inputs_are_task_and_intent_and_each_step_has_its_own_last_label(tmp_path, program):
    first, second = demo.build(tmp_path, program, "0"), demo.build(tmp_path, program, "1")
    labels = [key.split(" / ")[-1] for key in demo.site_classes(first)]
    frozen = json.loads(freeze.RECORD.read_text())["seeds"][program]["program_digest"]
    assert (first.digest, frozen, [name for name, _ in first.tree["params"]], sorted(labels)) == (
        second.digest, first.digest, ["task", "intent"], sorted(set(labels)))


def test_the_seeds_are_as_frozen():
    assert freeze.differences() == [], freeze.FROZEN
