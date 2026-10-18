"""The offline GP example: every grammar production compiles, an ill-typed individual is counted as rejected,
and a small (mu+lambda) run is elitist and moves away from the seed's structure (scripted world, no provider)."""

import json

import pytest

from experiments.orc_gp_example import grammar
from experiments.orc_gp_example.evolve import evaluate, evolve, orchestrator, prepare_workspace

EVERY_PRODUCTION = (
    tuple(("implement", m) for m in grammar.MODELS)  # before any plan: the plain implement prompt
    + tuple(("plan", m) for m in grammar.MODELS)
    + tuple(("implement", m) for m in grammar.MODELS)  # after a plan: the plan-reading implement prompt
    + tuple((kind, rounds, m) for kind in ("check_and_repair", "review_and_revise")
            for rounds in (1, grammar.MAX_ROUNDS) for m in grammar.MODELS))


def test_every_grammar_production_renders_a_compiling_module(tmp_path):
    prepare_workspace(tmp_path / "w", grammar.render(EVERY_PRODUCTION))
    assert orchestrator(tmp_path / "w", "compile").returncode == 0


def test_ill_typed_individual_is_recorded_as_rejected(tmp_path):
    record = evaluate((("ill_typed_implement", "claude-sonnet-5-5"),), tmp_path)
    assert (record["compile"], record["fitness"]) == ("rejected", None)


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    out = tmp_path_factory.mktemp("gp")
    evolve(out, population_size=4, generations=2, seed=0)
    return json.loads((out / "results.json").read_text())


def test_run_records_two_generations(results):
    assert len(results["generations"]) == 2


def test_every_individual_compiled(results):
    assert {i["compile"] for i in results["individuals"].values()} == {"accepted"}


def test_best_fitness_never_decreases(results):
    best = [g["best_fitness"] for g in [results["initial"], *results["generations"]]]
    assert best == sorted(best)


def test_best_individual_differs_structurally_from_seed(results):
    individuals = results["individuals"]
    best = individuals[results["generations"][-1]["population"][0]]
    assert best["skeleton"] != individuals[results["seed_individual"]]["skeleton"]
