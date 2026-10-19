"""Structural-search seed catalog: every seed is an admitted 2.39 program with one entry contract."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr, StringAtom, SymbolAtom

ROOT = Path(__file__).resolve().parents[2]
SEEDS_DIR = ROOT / "experiments" / "orc_structural_search" / "seeds"
THREE_ARM_ORC = ROOT / "experiments" / "orc_structural_search" / "three_arm" / "orc"
SEEDS = ["direct", "plan_then_implement", "implement_review_revise", "best_of_n", "implement_check_diagnose_repair"]


def compile_seed(seed, directory=SEEDS_DIR):
    rel = directory.relative_to(ROOT)
    proc = subprocess.run(
        [sys.executable, "-P", "-m", "orchestrator", "compile", str(rel / f"{seed}.orc"),
         "--entry-workflow", f"{seed}::run", "--source-root", str(rel),
         "--provider-externs-file", str(rel / "providers.json"),
         "--command-boundaries-file", str(rel / "commands.json"), "--diagnostics-json"],
        cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)}, capture_output=True, text=True,
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"compile of {seed} printed no JSON; stdout={proc.stdout!r} stderr={proc.stderr!r}")


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


def test_the_rebound_direct_parent_compiles_with_the_codex_coder():
    source = (THREE_ARM_ORC / "direct.orc").read_text()
    providers = json.loads((THREE_ARM_ORC / "providers.json").read_text())
    assert (compile_seed("direct", THREE_ARM_ORC)["status"], providers["providers.coder"],
            re.findall(r':model "([^"]*)"', source), re.findall(r':effort "([^"]*)"', source)) == (
        "accepted", "codex_unrestricted_workspace", ["gpt-6.1-sol"], ["high"])


def test_no_seed_names_a_fable_model():
    roots = (SEEDS_DIR, THREE_ARM_ORC, THREE_ARM_ORC.parent / "python")
    for path in (p for root in roots for p in root.iterdir() if p.is_file()):
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


def test_dev_check_timeout_with_output_on_one_stream_writes_report(tmp_path):
    (tmp_path / "dev-check.json").write_text(json.dumps(
        {"argv": ["python", "-c", "import time; print('partial', flush=True); time.sleep(5)"], "timeout_sec": 1}))
    report = _run_dev_check(tmp_path)
    assert (report["passed"], report["failing"]) == (False, ["timeout after 1s"])


def test_dev_check_without_config_fails_closed(tmp_path):
    report = _run_dev_check(tmp_path)
    assert (report["passed"], report["failing"]) == (False, ["dev-check.json missing"])


def test_registry_lists_every_seed():
    readme = (ROOT / "workflows" / "README.md").read_text()
    missing = [seed for seed in SEEDS if f"experiments/orc_structural_search/seeds/{seed}.orc" not in readme]
    assert missing == []
