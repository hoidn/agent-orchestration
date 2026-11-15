"""The long-horizon seeds (`experiments/long_horizon_seed/`) against a scripted `claude` on a closed `PATH`.

Each scenario of `demo.py` is one run of a seed through the command line: it must end with the declared result,
committed steps and provider calls; a killed run, once resumed, must start no step it had committed; every step after
the setup must be given the guide path the setup reported; and no run may leave a socket directory outside its world
(the Agent Sessions seed must name one, so that the check has something to look at).
"""

import pytest

from experiments.long_horizon_seed import demo

SCENARIOS = [(program, scenario) for program, scenarios in demo.PROGRAMS.items() for scenario in scenarios]


@pytest.mark.parametrize(("program", "scenario"), SCENARIOS, ids=lambda value: value)
def test_scenario_ends_as_declared(tmp_path, program, scenario):
    assert demo.run(tmp_path, program, scenario) == demo.expected(program, scenario)


@pytest.mark.parametrize("program", demo.PROGRAMS)
def test_digest_ignores_the_hash_seed_and_the_inputs_are_the_task_and_the_intent(tmp_path, program):
    first, second = demo.build(tmp_path, program, "0"), demo.build(tmp_path, program, "1")
    assert (first.digest, [name for name, _ in first.tree["params"]]) == (second.digest, ["task", "intent"])
