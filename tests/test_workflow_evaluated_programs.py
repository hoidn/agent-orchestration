"""Public compile, run and resume of the compact paired search against its Python reference."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytest.register_assert_rewrite("tests.workflow_evaluated_program_sources")  # named diffs in its checks

from tests.experiments.test_mlevolve_pair_fixture import BUDGETS, SCENARIOS  # noqa: E402
from tests.workflow_evaluated_program_sources import (  # noqa: E402
    AUDIT, PAIR, audit_fold, census, exercise, fresh_rows, growth_source, install, label_spans,
    occurrences, public_run, reference, selector_events, stock_source,
)
from tests.workflow_evaluated_totality_helpers import checked_run, compile_public  # noqa: E402


STOCK_BUDGETS = (2, 3, 4, 7, 12)
CAMPAIGN = [pytest.param(scenario, budget, id=f"{scenario['name']}-{budget}")
            for scenario in SCENARIOS for budget in BUDGETS]
GROWTH_CASES = [pytest.param(None, 12, id="stock-12"), pytest.param(None, 0, id="stock-0"),
                *(pytest.param(scenario, 12, id=f"{scenario['name']}-12") for scenario in SCENARIOS)]
NAMED = {scenario["name"]: scenario for scenario in SCENARIOS}


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parts(outcome, *, growth: bool) -> tuple[dict, dict]:
    """Named observed/expected parts; growth projects the base result and adds its audit."""
    if not growth:
        return outcome.observed(), outcome.wanted()
    observed = outcome.observed({key: outcome.actual[key] for key in outcome.expected})
    observed.update(audit={key: outcome.actual[key] for key in AUDIT}, keys=sorted(outcome.actual))
    wanted = {**outcome.wanted(), "audit": audit_fold(outcome.expected["trace"]),
              "keys": sorted([*outcome.expected, *AUDIT])}
    return observed, wanted


@pytest.mark.parametrize("budget", STOCK_BUDGETS)
def test_public_stock_search_matches_python_reference(tmp_path, monkeypatch, budget):
    observed, wanted = _parts(exercise(tmp_path, monkeypatch, stock_source(), budget), growth=False)

    assert observed == wanted


def test_campaign_has_72_unique_scenario_budget_cases():
    assert len({param.id for param in CAMPAIGN}) == len(CAMPAIGN) == 72


@pytest.mark.parametrize("scenario,budget", CAMPAIGN)
def test_public_search_matches_scenario(tmp_path, monkeypatch, scenario, budget):
    outcome = exercise(tmp_path, monkeypatch, stock_source(), budget, scenario, compile=False)

    observed, wanted = _parts(outcome, growth=False)
    assert observed == wanted


@pytest.mark.parametrize("growth,name", [(False, "repair_fails_then_succeeds"), (True, "every_candidate_invalid")],
                         ids=["stock-source-repair_fails_then_succeeds-12", "growth-every_candidate_invalid-12"])
def test_public_cli_resume_matches_python_reference(tmp_path, monkeypatch, growth, name):
    text = growth_source(stock_source())[0] if growth else stock_source()

    outcome = exercise(tmp_path, monkeypatch, text, 12, NAMED[name], cli=True)

    observed, wanted = _parts(outcome, growth=growth)
    assert observed == wanted


def test_growth_source_census_and_closed_selector_mapping(tmp_path):
    stock = stock_source()
    text, labels = growth_source(stock)
    files = install(tmp_path, text, None)
    compile_public(files)
    summary = json.loads((tmp_path / "compile.stdout").read_text(encoding="utf-8"))
    program = json.loads(Path(summary["artifact_paths"]["closed_program"]).read_text(encoding="utf-8"))
    spans = label_spans(text, files["source"], labels)
    selects, body_ifs = occurrences(program, "select", spans), occurrences(program, "if", spans)
    before, after = census(stock, "stock.orc")[0], census(text, str(files["source"]))[0]
    receipt = {"stock_sha256": _sha(stock), "growth_sha256": _sha(text),
               "original_sha256": _sha((PAIR / "search_compact.orc").read_text(encoding="utf-8")),
               "before": before, "after": after, "closed_select_occurrences": selects,
               "closed_body_if_occurrences": body_ifs}
    (tmp_path / "growth-census.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    assert {"before": before, "after": after, "labels": len(spans),
            "unmapped": [label for label, paths in selects.items() if not paths],
            "body_ifs": [label for label, paths in body_ifs.items() if paths]} == {
        "before": {"SearchState": 14, "SearchResult": 5, "result": 0, "branch-step": 18, "run-search": 9},
        "after": {"SearchState": 28, "SearchResult": 19, "result": 0, "branch-step": 32, "run-search": 22},
        "labels": 27, "unmapped": [], "body_ifs": []}


@pytest.mark.parametrize("scenario,budget", GROWTH_CASES)
def test_public_growth_matches_python_trace_and_audit_fold(tmp_path, monkeypatch, scenario, budget):
    text, _ = growth_source(stock_source())

    outcome = exercise(tmp_path, monkeypatch, text, budget, scenario)

    observed, wanted = _parts(outcome, growth=True)
    assert observed == wanted


def _witness(root, monkeypatch, text, labels, scenario, budget) -> dict:
    """Arms selected by the added `if`s in fresh evaluation, and post-seed counter changes."""
    files = install(root, text, scenario)
    spans = label_spans(text, files["source"], labels)
    monkeypatch.chdir(root)
    with selector_events(monkeypatch) as events:
        assert public_run(files, budget).exit_code == 0
    authority, snapshot = checked_run(root)
    value, expected = snapshot.terminal.data["value"], reference(scenario, budget)[0]
    final, seeds = {key: value[key] for key in AUDIT}, audit_fold(expected["trace"][:2])
    assert {"base": {key: value[key] for key in expected}, "audit": final} == {
        "base": expected, "audit": audit_fold(expected["trace"])}
    rows, lanes = fresh_rows(events, spans, authority.program.tree, expected["trace"])
    return {"fresh_arms": sorted({(row["label"], row["arm"]) for row in rows}),
            "post_seed_changes": {key: [seeds[key], final[key]] for key in AUDIT if final[key] != seeds[key]},
            "added_selector_events_by_lane": lanes, "fresh_events": rows}


def test_growth_selectors_take_both_arms_and_counters_change_after_seeds(tmp_path, monkeypatch):
    text, labels = growth_source(stock_source())

    receipt = {param.id: _witness(tmp_path / param.id, monkeypatch, text, labels, *param.values)
               for param in GROWTH_CASES}

    (tmp_path / "growth-witness.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    arms = {arm for case in receipt.values() for arm in case["fresh_arms"]}
    changed = {key for case in receipt.values() for key in case["post_seed_changes"]}
    assert {"arms": sorted(arms), "changed": sorted(changed)} == {
        "arms": sorted((label, arm) for label in labels for arm in (False, True)), "changed": sorted(AUDIT)}
