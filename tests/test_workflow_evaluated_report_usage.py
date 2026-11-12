"""`orchestrator report` shows tokens and cost per provider step and for the run, read from `usage.json`.

Runs go through `orchestrator run` with the metering tests' stand-in CLIs: a `<name>_metered` template
reports fixed usage, a plain template records `unknown`. No provider is called.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.providers.pricing import load_price_table, priced
from tests.test_workflow_evaluated_provider_usage import (
    CLAUDE_USAGE, CODEX_USAGE, SOURCE, _attempts, _orchestrator, _workspace,
)
from tests.test_workflow_evaluated_provider_usage import _run as _run_one
from tests.test_workflow_evaluated_spend_cap import COMMAND, _run, _run_id

FIRST, SECOND, BUILD = "workflow:main::run / first", "workflow:main::run / second", "workflow:main::run / built"
STEPS = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defworkflow run ((message String)) -> Result
    (let* ((first (provider-result providers.first :prompt prompts.base
                    :inputs (message) :model "FIRST_MODEL" :effort "high" :returns Result))
           (built (command-result build :argv ("python" "command.py" message) :returns String))
           (second (provider-result providers.second :prompt prompts.base
                     :inputs (message built) :model "SECOND_MODEL" :effort "high" :returns Result)))
      second)))'''
TOKENS = CLAUDE_USAGE["rows"][0]["tokens"]
ONE_CALL = priced(CLAUDE_USAGE["rows"], load_price_table())     # the ordinary price, not the CLI's 0.25


def _steps_workspace(tmp_path: Path, first: str, second: str, model: str = "claude-haiku-5-5",
                     second_model: str | None = None) -> Path:
    root = _workspace(tmp_path / "w", first)
    (root / "main.orc").write_text(STEPS.replace("FIRST_MODEL", model).replace("SECOND_MODEL", second_model or model),
                                   encoding="utf-8")
    (root / "providers.json").write_text(json.dumps({"providers.first": first, "providers.second": second}),
                                         encoding="utf-8")
    (root / "command.py").write_text(COMMAND, encoding="utf-8")
    (root / "commands.json").write_text(json.dumps(
        {"build": {"stable_command": ["python", "command.py"], "closure": ["command.py"]}}), encoding="utf-8")
    return root


def _report(root: Path, *extra: str, fmt: str = "json"):
    result = _orchestrator(root, "report", "--format", fmt, *extra)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if fmt == "json" else result.stdout


def _usage_by_step(report: dict) -> dict:
    return {step["identity"]: step.get("usage") for step in report["steps"]}


def _times(tokens: dict, n: int) -> dict:
    return {key: value * n for key, value in tokens.items()}


def test_report_shows_tokens_per_provider_step_and_a_run_total(tmp_path):
    root = _steps_workspace(tmp_path, "claude_metered", "claude_metered")
    assert _run(root).returncode == 0
    report = _report(root)
    step = {"tokens": TOKENS, "cost_usd": pytest.approx(ONE_CALL), "attempts": 1, "unknown_attempts": 0,
            "partial": False}
    usage = _usage_by_step(report)
    assert (usage[FIRST], usage[SECOND]) == (step, step)
    total = report["run"]["usage"]
    assert {key: total[key] for key in step} == {**step, "tokens": _times(TOKENS, 2),
                                                 "cost_usd": pytest.approx(2 * ONE_CALL), "attempts": 2}
    markdown = _report(root, fmt="md")
    assert markdown.count(f"- usage: `input 11, output 7, cache_read 5, cache_write 3; cost_usd {ONE_CALL:.6g}; "
                          "attempts 1`") == 2
    assert f"- total: `input 22, output 14, cache_read 10, cache_write 6; cost_usd {2 * ONE_CALL:.6g}; " \
           "attempts 2`" in markdown


def test_unmetered_step_shows_unknown_and_marks_the_total_partial(tmp_path):
    root = _steps_workspace(tmp_path, "claude_metered", "claude")
    assert _run(root).returncode == 0
    report = _report(root)
    assert _usage_by_step(report)[SECOND] == {"tokens": None, "cost_usd": None, "attempts": 1,
                                              "unknown_attempts": 1, "partial": True}
    total = report["run"]["usage"]
    assert (total["tokens"], total["cost_usd"], total["unknown_attempts"], total["partial"]) == (
        TOKENS, pytest.approx(ONE_CALL), 1, True)
    markdown = _report(root, fmt="md")
    assert "- usage: `unknown; attempts 1, 1 unknown`" in markdown
    assert f"- total: `≥ input 11, output 7, cache_read 5, cache_write 3; cost_usd ≥ {ONE_CALL:.6g}; " \
           "attempts 2, 1 unknown`" in markdown
    assert "input 0" not in markdown


def test_incomplete_usage_marks_the_step_partial(tmp_path):
    root = _workspace(tmp_path / "w", "claude_metered")
    (root / "main.orc").write_text(SOURCE.replace("MODEL", "claude-haiku-5-5").replace(
        ':effort "high"', ':effort "high" :timeout-sec 2'), encoding="utf-8")
    assert _run_one(root, mode="hang").returncode == 1
    (usage,) = _usage_by_step(_report(root)).values()
    assert (usage["tokens"], usage["unknown_attempts"], usage["partial"]) == (
        {"input": 11, "output": 1, "cache_read": 5, "cache_write": 3}, 0, True)
    assert "- usage: `≥ input 11, output 1" in _report(root, fmt="md")


def test_retried_step_sums_every_attempt(tmp_path):
    root = _workspace(tmp_path / "w", "claude_metered")
    (root / "main.orc").write_text(SOURCE.replace("MODEL", "claude-haiku-5-5"), encoding="utf-8")
    assert _run_one(root, mode="fail").returncode == 1
    resumed = _orchestrator(root, "resume", _run_id(root))
    assert resumed.returncode == 0, resumed.stderr
    assert len(_attempts(root)) == 2
    (usage,) = _usage_by_step(_report(root)).values()
    assert usage == {"tokens": _times(TOKENS, 2), "cost_usd": pytest.approx(2 * ONE_CALL), "attempts": 2,
                     "unknown_attempts": 0, "partial": False}


def test_unpriced_model_shows_tokens_and_no_cost(tmp_path):
    """An unpriced attempt counts like an unknown one: the priced rest is summed and marked partial."""
    root = _steps_workspace(tmp_path, "codex_metered", "codex_metered", model="gpt-5.5", second_model="gpt-5.6-terra")
    assert _run(root).returncode == 0
    report = _report(root)
    codex = CODEX_USAGE["rows"][0]["tokens"]
    terra = priced([{"model": "gpt-5.6-terra", "tokens": codex}], load_price_table())
    first, total = _usage_by_step(report)[FIRST], report["run"]["usage"]
    assert (first["tokens"], first["cost_usd"], first["unknown_attempts"], first["partial"]) == (codex, None, 0, True)
    assert (total["tokens"], total["cost_usd"], total["unknown_attempts"], total["partial"]) == (
        _times(codex, 2), pytest.approx(terra), 0, True)
    markdown = _report(root, fmt="md")
    assert "- usage: `≥ input 6, output 7, cache_read 5, cache_write 0; cost_usd unknown; attempts 1`" in markdown
    assert f"- total: `≥ input 12, output 14, cache_read 10, cache_write 0; cost_usd ≥ {terra:.6g}; " \
           "attempts 2`" in markdown


def test_reported_cost_without_token_rows_is_a_partial_figure(tmp_path):
    """Claude's `result` line with an empty `modelUsage` and a cost: the cost counts, as the spend cap counts it."""
    root = _workspace(tmp_path / "w", "claude_metered")
    (root / "main.orc").write_text(SOURCE.replace("MODEL", "claude-haiku-5-5"), encoding="utf-8")
    assert _run_one(root).returncode == 0
    (attempt,) = _attempts(root)
    (attempt / "usage.json").write_text(json.dumps({**CLAUDE_USAGE, "rows": []}), encoding="utf-8")
    (usage,) = _usage_by_step(_report(root)).values()
    assert (usage["cost_usd"], usage["unknown_attempts"], usage["partial"]) == (0.25, 0, True)
    assert "- usage: `≥ input 0, output 0, cache_read 0, cache_write 0; cost_usd ≥ 0.25; attempts 1`" in _report(
        root, fmt="md")


def test_run_without_provider_steps_has_no_usage(tmp_path):
    root = _steps_workspace(tmp_path, "claude_metered", "claude_metered")
    (root / "main.orc").write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defworkflow run ((message String)) -> String
    (command-result build :argv ("python" "command.py" message) :returns String)))''', encoding="utf-8")
    assert _run(root).returncode == 0
    assert ("usage" in _report(root)["run"], "## Usage" in _report(root, fmt="md")) == (False, False)


def test_report_json_never_prints_a_non_finite_cost(tmp_path):
    """Two attempts each priced at 1e308 USD sum past the float range: the cost is withheld, not `Infinity`."""
    root = _steps_workspace(tmp_path, "claude_metered", "claude_metered")
    assert _run(root).returncode == 0
    for attempt in _attempts(root):
        huge = {**CLAUDE_USAGE, "rows": [{"model": "claude-haiku-5-5", "tokens": {
            "input": 10 ** 308, "output": 0, "cache_read": 0, "cache_write": 0}}]}
        (attempt / "usage.json").write_text(json.dumps(huge), encoding="utf-8")
    own = {**load_price_table(), "tokens_per_unit": 1,
           "models": {"claude-haiku-5-5": {"input": 1, "output": 0, "cache_read": 0, "cache_write": 0}}}
    (tmp_path / "prices.json").write_text(json.dumps(own), encoding="utf-8")
    result = _orchestrator(root, "report", "--format", "json", "--price-table", str(tmp_path / "prices.json"))
    assert result.returncode == 0, result.stderr
    total = json.loads(result.stdout, parse_constant=lambda name: pytest.fail(f"report printed {name}"))["run"]["usage"]
    assert (total["cost_usd"], total["partial"]) == (None, True)


def test_report_names_the_price_table_source_and_date(tmp_path):
    root = _steps_workspace(tmp_path, "claude_metered", "claude_metered")
    assert _run(root).returncode == 0
    table = load_price_table()
    assert _report(root)["run"]["usage"]["price_table"] == {"source": table["source"], "date": table["date"]}
    assert f"- price_table: `{table['source']} ({table['date']})`" in _report(root, fmt="md")
    own = {**table, "source": "a test table", "date": "2020-01-02",
           "models": {"claude-haiku-5-5": {"input": 1, "output": 1, "cache_read": 1, "cache_write": 1}}}
    (tmp_path / "prices.json").write_text(json.dumps(own), encoding="utf-8")
    total = _report(root, "--price-table", str(tmp_path / "prices.json"))["run"]["usage"]
    assert (total["price_table"], total["cost_usd"]) == (
        {"source": "a test table", "date": "2020-01-02"}, pytest.approx(2 * 26 / 1e6))


def _table_text(**change) -> str:
    table = load_price_table()
    rates = {**table["models"]["claude-haiku-5-5"], **change.pop("rates", {})}
    return json.dumps({**table, **change, "models": {"claude-haiku-5-5": rates}})


@pytest.mark.parametrize("text", [
    "{", '{"currency": "EUR"}', "[]", _table_text(rates={"input": -1}),
    _table_text(rates={"output": 9e6}),                     # USD 9 per token
    _table_text(tokens_per_unit=1e-300),
    _table_text(rates={"input": 1}).replace('"input": 1,', '"input": NaN,', 1),
], ids=["not-json", "invalid", "not-an-object", "negative", "absurd-rate", "absurd-unit", "nan"])
def test_malformed_price_table_is_refused(tmp_path, text):
    root = _steps_workspace(tmp_path, "claude_metered", "claude_metered")
    assert _run(root).returncode == 0
    (tmp_path / "prices.json").write_text(text, encoding="utf-8")
    result = _orchestrator(root, "report", "--price-table", str(tmp_path / "prices.json"))
    assert (result.returncode, result.stdout, result.stderr.startswith("Error: price_table_invalid: "),
            "Traceback" in result.stderr) == (2, "", True, False), result.stderr


def test_command_steps_carry_no_usage(tmp_path):
    root = _steps_workspace(tmp_path, "claude_metered", "claude_metered")
    assert _run(root).returncode == 0
    report = _report(root)
    steps = {step["identity"]: step for step in report["steps"]}
    assert ("usage" in steps[FIRST], "usage" in steps[BUILD]) == (True, False)
    assert set(report) == {"run", "progress", "steps"}


def test_agent_turn_steps_carry_usage(tmp_path, monkeypatch):
    from tests.agent_session_shims import install_agent_shims
    from tests.test_workflow_evaluated_agent_turns import PLAN, fixture
    from tests.test_workflow_evaluated_invalidate import _cli

    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex",
                        claude_home=tmp_path / "claude", plan=PLAN)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 0
    report = _cli(tmp_path, "report", "--format", "json")
    assert report.returncode == 0, report.stderr
    turns = [step["usage"] for step in json.loads(report.stdout)["steps"] if step["kind"] == "agent_turn"]
    # The shims print transport without usage counters: every turn attempt is unknown, none zero.
    assert (len(turns), {(usage["tokens"], usage["unknown_attempts"]) for usage in turns}) == (4, {(None, 1)})
