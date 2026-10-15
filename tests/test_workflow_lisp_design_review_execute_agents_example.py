"""`design_review_execute_agents.orc`: the two-agent opt-in variant compiles with two allocations and four turns."""
from __future__ import annotations

import json, os, shlex, subprocess, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "workflows" / "examples" / "design_review_execute_agents.orc"
BASELINE = REPO_ROOT / "workflows" / "examples" / "design_review_execute.orc"


def test_documented_command_compiles_two_agents_and_four_turns() -> None:
    header = EXAMPLE.read_text(encoding="utf-8").split("python -m orchestrator compile", 1)[1].split("\n\n", 1)[0]
    argv = shlex.split("python -m orchestrator compile " + " ".join(line.strip(" ;\\") for line in header.splitlines()))
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, *argv[1:]], cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    built = json.loads(result.stdout)
    target = json.loads(Path(built["artifact_paths"]["closed_program"]).read_text(encoding="utf-8"))["target"]
    assert (built["entry_workflow"], built["sites"], target) == ("design_review_execute_agents::run", 6, "2.38")


def test_variant_keeps_the_baseline_declarations_models_effort_and_timeouts() -> None:
    variant, baseline = EXAMPLE.read_text(), BASELINE.read_text()
    for declaration in ("(defpath DraftDocPath", "(defpath DesignDocPath", "(defrecord Draft", "(defrecord Design", "(defrecord Feedback", "(defrecord Execution"):
        assert declaration in variant
    for prompt in ("draft-design", "review-design", "revise-design", "execute-design"):
        start = baseline.index(f"(defprompt {prompt}"); end = baseline.index("\n\n", start)
        assert baseline[start:end] in variant
    assert '(planner_model String :default "claude-fable-5-1")' in variant and '(reviewer_model String :default "gpt-6.1-sol")' in variant
    assert variant.count(":timeout-sec 3600") == 3 and ":timeout-sec 14400" in variant
    assert ':effort "high"' in variant
