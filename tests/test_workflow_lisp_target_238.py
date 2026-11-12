"""Target 2.38 is registered as an additive evaluated target that gates agent sessions."""
from __future__ import annotations

from pathlib import Path


from orchestrator.workflow_lisp import syntax
from tests.test_workflow_lisp_target_233 import _compile_minimal_module

TARGET = "2.38"


def test_agent_sessions_gate_opens_at_238_and_keeps_earlier_gates() -> None:
    assert syntax.AGENT_SESSIONS_MIN_TARGET_DSL_VERSION == TARGET
    assert [syntax.target_dsl_supports_agent_sessions(t) for t in ("2.36", "2.37", "2.38")] == [False, False, True]
    assert syntax.target_dsl_supports_parallel_map("2.38") is True
    assert syntax.target_dsl_uses_evaluated_execution("2.38") is True
    assert syntax.PARALLEL_MAP_MIN_TARGET_DSL_VERSION == "2.37"


def test_module_targeting_238_compiles_with_no_new_forms(tmp_path: Path) -> None:
    assert _compile_minimal_module(tmp_path, TARGET).typed_program.target == TARGET
