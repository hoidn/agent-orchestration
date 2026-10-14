"""Target 2.34 registration for the evaluated execution and repetition reduction plans.

Registration only: 2.34 accepts and lowers exactly what 2.33 does. Later tasks of
`docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md` (Task 0) add
its surface; see `specs/versioning.md` (v2.34 additions).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow.run_ref import config as run_ref_config
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.workflow_evaluated_totality_helpers import _log, _public_run_files, _write_probe, _write_sources
from tests.workflow_evaluated_totality_helpers import _public_run
from tests.test_workflow_lisp_generic_unions_runtime import _compile
from tests.test_workflow_lisp_improve_stdlib import _hook_calls, _write_project
from tests.workflow_lisp_improve_stdlib_sources import REVISE_PROBE

PROGRAM = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/entry)
  (export run)
  (defrecord Candidate (title String) (score Int))
  (defproc revise-candidate
    ((candidate Candidate))
    -> Candidate
    :effects ((uses-command probe_revise))
    :lowering inline
    (command-result probe_revise
      :argv ("python" "PROBE_REVISE" candidate.title "tidy" "fb")
      :returns Candidate))
  (defworkflow run () -> Candidate
    (let* ((first (revise-candidate (record Candidate :title "seed" :score 0)))
           (second (revise-candidate first)))
      second)))
"""

ARTIFACT_FLAGS = (
    "--emit-executable-ir",
    "--emit-core-ast",
    "--emit-runtime-plan",
    "--emit-semantic-ir",
    "--emit-source-map",
    "--emit-debug-yaml",
)

# Each `*_MIN_TARGET_DSL_VERSION` gate in `syntax.py` and the public predicate that reads it.
GATE_PREDICATES = {
    "PROVIDER_SUPERVISION_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_provider_supervision,
    "PROVIDER_PEER_MESSAGING_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_provider_peer_messaging,
    "LIST_TRAVERSAL_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_list_traversal,
    "VALUE_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_value,
    "PROMPT_CALCULUS_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_prompt_calculus,
    "PROMPT_OUTPUT_POSITIONS_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_prompt_output_positions,
    "PROMPT_ATTEMPT_IDENTITY_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_prompt_attempt_identity,
    "PHASED_CONTRACT_DELIVERY_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_phased_contract_delivery,
    "RUN_REF_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_run_ref,
    "NESTED_STRUCTURAL_TRANSPORT_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_nested_structural_transport,
    "TRIAL_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_trial,
    "STRICT_BOOLEAN_CONTROL_FLOW_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_strict_boolean_control_flow,
    "SESSION_ARTIFACT_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_session_artifact,
    "UNION_PROMPT_INPUT_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_union_prompt_input,
    "RICH_LOOP_VALUES_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_rich_loop_values,
    "PURE_CALL_COMPOSITION_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_pure_call_composition,
    "PROVIDER_CONTEXT_VALUES_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_provider_context_values,
    "HUMAN_INPUT_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_human_input,
    "GENERIC_UNION_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_generic_unions,
    "FINITE_FLOAT_BOUNDARY_MIN_TARGET_DSL_VERSION": syntax.target_dsl_refuses_non_finite_floats,
}
# The gates of the surface that 2.34 adds, which 2.33 must not pass.
GATES_FROM_234 = {
    "NUMERIC_SURFACE_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_numeric_surface,
}
# The gate of the surface that 2.35 adds, which 2.34 must not pass.
GATES_FROM_EVALUATED_EXECUTION = {
    "EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION": syntax.target_dsl_uses_evaluated_execution,
}
GATES_FROM_PARALLEL_MAP = {
    "PARALLEL_MAP_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_parallel_map,
}


def _write_program(root: Path, target: str) -> dict[str, Path]:
    probes = {"probe_revise": _write_probe(root, "probe_revise", REVISE_PROBE)}
    source = PROGRAM.replace("TARGET", target).replace("PROBE_REVISE", probes["probe_revise"].as_posix())
    _write_sources(root, {"grt/entry.orc": source})
    return _public_run_files(root, probes)






@pytest.mark.parametrize(
    "registry",
    [
        pytest.param(syntax.SUPPORTED_TARGET_DSL_VERSIONS, id="frontend"),
        pytest.param(run_ref_config._SUPPORTED_TARGET_DSL_VERSIONS, id="run-ref-config"),
    ],
)
def test_target_234_is_registered(registry) -> None:
    assert "2.34" in registry










def test_target_238_is_refused_as_unsupported(tmp_path: Path) -> None:
    files = _write_program(tmp_path, "2.38")
    line = next(n for n, text in enumerate(files["source"].read_text().splitlines(), 1) if ":target-dsl" in text)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path)

    diagnostic = excinfo.value.diagnostics[0]
    assert (diagnostic.code, Path(diagnostic.span.start.path), diagnostic.span.start.line) == (
        "target_dsl_unsupported",
        files["source"],
        line,
    )


def test_every_min_target_gate_has_a_predicate_here() -> None:
    assert {name for name in vars(syntax) if name.endswith("_MIN_TARGET_DSL_VERSION")} == set(GATE_PREDICATES) | set(
        GATES_FROM_234
    ) | set(GATES_FROM_EVALUATED_EXECUTION) | set(GATES_FROM_PARALLEL_MAP)


@pytest.mark.parametrize("gate", sorted(GATE_PREDICATES))
def test_every_gate_that_233_passes_holds_at_234(gate: str) -> None:
    predicate = GATE_PREDICATES[gate]

    # A gate of the 2.34 surface is closed at 2.33.
    assert (predicate("2.33"), predicate("2.34")) == (getattr(syntax, gate) != "2.34", True)


@pytest.mark.parametrize("gate", sorted(GATES_FROM_234))
def test_every_gate_of_234_surface_is_closed_at_233(gate: str) -> None:
    predicate = GATES_FROM_234[gate]

    assert (vars(syntax)[gate], predicate("2.33"), predicate("2.34")) == ("2.34", False, True)


@pytest.mark.parametrize("gate", sorted(GATES_FROM_EVALUATED_EXECUTION))
def test_every_gate_of_235_surface_is_closed_at_234(gate: str) -> None:
    predicate = GATES_FROM_EVALUATED_EXECUTION[gate]

    assert (vars(syntax)[gate], predicate("2.34"), predicate("2.35")) == ("2.35", False, True)


def test_target_234_is_2_33_or_newer() -> None:
    assert syntax.target_dsl_is_2_33_or_newer("2.34")
