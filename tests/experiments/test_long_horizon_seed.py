"""The long-horizon seeds (`experiments/long_horizon_seed/`) against a scripted `claude` on a closed `PATH`.

Each scenario of `demo.py` is one run of a seed through the command line: it must end with the declared result,
committed steps and provider calls, and a killed run, once resumed, must start no step it had committed.
"""

import pytest

from experiments.long_horizon_seed import demo

SCENARIOS = [(program, scenario) for program, scenarios in demo.PROGRAMS.items() for scenario in scenarios]


@pytest.mark.parametrize(("program", "scenario"), SCENARIOS, ids=lambda value: value)
def test_scenario_ends_as_declared(tmp_path, program, scenario):
    assert demo.run(tmp_path, program, scenario) == demo.expected(program, scenario)


@pytest.mark.parametrize("program", demo.PROGRAMS)
def test_digest_does_not_depend_on_the_hash_seed(tmp_path, program):
    assert demo.build(tmp_path, program, "0").digest == demo.build(tmp_path, program, "1").digest


@pytest.mark.parametrize("program", demo.PROGRAMS)
def test_inputs_are_the_task_and_the_intent(tmp_path, program):
    assert [name for name, _ in demo.build(tmp_path, program).tree["params"]] == ["task", "intent"]
