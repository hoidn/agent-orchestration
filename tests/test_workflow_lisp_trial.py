import pytest

from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.type_env import (
    PrimitiveTypeRef,
)


COMMIT_A = "0123456789abcdef0123456789abcdef01234567"
COMMIT_B = "89abcdef0123456789abcdef0123456789abcdef"


def _run_ref(*, child: str, commit: str, returns: str | None = None) -> str:
    returns_clause = "" if returns is None else f" :returns {returns}"
    return (
        "(run-ref "
        f':source (:repo "file:///workspace" :commit "{commit}") '
        f":program (:bundle {child}) :inputs (){returns_clause} "
        ":policy (:setup ()))"
    )


def _trial_source(*, arm_a: str | None = None, arm_b: str | None = None) -> str:
    arm_a = arm_a or _run_ref(child="first", commit=COMMIT_A)
    arm_b = arm_b or _run_ref(child="second", commit=COMMIT_B)
    return f"""
(trial
  :arms ((:id "direct" :run-ref {arm_a})
         (:id "orc" :run-ref {arm_b}))
  :reps 3
  :max-concurrency 4
  :evaluation
  (record
    :checks (list
      (record :id "correctness"
              :command (list "python" "-m" "pytest" "-q")
              :authority "correctness"
              :required true
              :timeout-ms 600000))
    :judgment
    (record :provider "scorer"
            :rubric-asset "rubrics/trial.md"
            :evidence-confidentiality "same_trust_boundary"
            :evidence-limits
            (record :max-item-bytes 65536
                    :max-packet-bytes 262144))
    :observation
    (record :include
            (list "task_spec" "validated_result" "workspace_delta"
                  "check_results" "declared_artifacts" "failure_evidence")
            :diff-cap-bytes 262144
            :reveal-provider-identity false)
    :aggregation
    (record :mode "independent_rubric"
            :rep-combine "median"
            :tie "authored_order")
    :success-rule
    (record :superior
            (record :min-abs-improvement 0.10 :max-cost-ratio 1.5)
            :non-inferior
            (record :min-cost-reduction 0.20)
            :count-failures-as-outcomes true))
  :budget
  (record :arm-timeout-ms 900000
          :trial-timeout-ms 3600000
          :max-evaluator-attempts 6
          :max-evaluator-concurrency 2))
"""


@pytest.mark.parametrize("target_dsl_version", ("2.35", "2.36"))
def test_full_compiler_keeps_non_trial_value_return_signature(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    target_dsl_version: str,
) -> None:
    from orchestrator.workflow_lisp import compiler as workflow_lisp_compiler

    source_path = tmp_path / "value_frontend.orc"
    source_path.write_text(
        f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target_dsl_version}")
  (defmodule value_frontend)
  (export passthrough)
  (defworkflow passthrough ((payload Value)) -> Value
    payload))
""",
        encoding="utf-8",
    )

    result = workflow_lisp_compiler.compile_stage3_module(
        source_path, entry_workflow="passthrough", workspace_root=tmp_path,
    )
    typed_entry = result.typed_program.workflows["value_frontend::passthrough"]
    assert typed_entry.signature.return_type_ref == PrimitiveTypeRef("Value")
    assert result.workflow_catalog.signatures_by_name["passthrough"].return_type_ref == PrimitiveTypeRef("Value")
