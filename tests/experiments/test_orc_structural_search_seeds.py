"""Structural-search seed catalog: every seed is an admitted 2.39 program with one entry contract."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr, StringAtom, SymbolAtom

ROOT = Path(__file__).resolve().parents[2]
SEEDS_DIR = ROOT / "experiments" / "orc_structural_search" / "seeds"
SEEDS = ["direct", "plan_then_implement", "implement_review_revise", "best_of_n", "implement_check_diagnose_repair"]


def compile_seed(seed):
    rel = SEEDS_DIR.relative_to(ROOT)
    proc = subprocess.run(
        [sys.executable, "-P", "-m", "orchestrator", "compile", str(rel / f"{seed}.orc"),
         "--entry-workflow", f"{seed}::run", "--source-root", str(rel),
         "--provider-externs-file", str(rel / "providers.json"),
         "--command-boundaries-file", str(rel / "commands.json"), "--diagnostics-json"],
        cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)}, capture_output=True, text=True,
    )
    return json.loads(proc.stdout)


def _forms(seed):
    top = read_sexpr_text((SEEDS_DIR / f"{seed}.orc").read_text(), source_path=f"{seed}.orc")
    return top.items[0].items


def _render(expr):
    if isinstance(expr, ListExpr):
        return "(" + " ".join(_render(item) for item in expr.items) + ")"
    return expr.value


def read_header(seed):
    return {
        _render(form.items[0]): form.items[1].value
        for form in _forms(seed)
        if isinstance(form, ListExpr) and isinstance(form.items[0], KeywordAtom)
        and isinstance(form.items[1], StringAtom)
    }


def entry_signature(seed):
    (run,) = [
        form for form in _forms(seed)
        if isinstance(form, ListExpr) and _render(form.items[0]) == "defworkflow"
        and _render(form.items[1]) == "run"
    ]
    name, params, arrow, result = run.items[1:5]
    return f"{_render(name)} {_render(params)} {_render(arrow)} {_render(result)}"


@pytest.mark.parametrize("seed", SEEDS)
def test_seed_compiles_at_2_39_with_the_common_entry_contract(seed):
    out = compile_seed(seed)
    assert out["status"] == "accepted", out
    assert read_header(seed)[":target-dsl"] == "2.39"
    assert entry_signature(seed) == "run ((task String) (intent String) (repo String)) -> Outcome"


def test_no_seed_names_a_fable_model():
    for path in SEEDS_DIR.iterdir():
        assert "fable" not in path.read_text().lower(), path


def _run_dev_check(workspace):
    bundle = workspace / "bundle.json"
    subprocess.run(
        [sys.executable, str(SEEDS_DIR / "dev_check.py")], cwd=workspace, check=True,
        env={**os.environ, "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(bundle)},
    )
    return json.loads(bundle.read_text())


def test_dev_check_writes_typed_report(tmp_path):
    (tmp_path / "dev-check.json").write_text(json.dumps(
        {"argv": ["python", "-c", "import sys; print('x' * 9000); sys.exit(1)"], "timeout_sec": 30}))
    report = _run_dev_check(tmp_path)
    assert (report["passed"], len(report["excerpt"])) == (False, 4000)


def test_dev_check_passes_on_zero_exit(tmp_path):
    (tmp_path / "dev-check.json").write_text(json.dumps({"argv": ["python", "-c", "pass"], "timeout_sec": 30}))
    assert _run_dev_check(tmp_path)["passed"] is True


def test_dev_check_without_config_fails_closed(tmp_path):
    report = _run_dev_check(tmp_path)
    assert (report["passed"], report["failing"]) == (False, ["dev-check.json missing"])


def test_registry_lists_every_seed():
    readme = (ROOT / "workflows" / "README.md").read_text()
    missing = [seed for seed in SEEDS if f"experiments/orc_structural_search/seeds/{seed}.orc" not in readme]
    assert missing == []
