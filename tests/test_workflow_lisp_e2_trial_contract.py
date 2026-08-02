"""Target-2.25 E2 normative admission and cross-spec trial contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_ROOT = REPO_ROOT / "specs"


def _ordinary_source(target: str) -> str:
    return f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target}")
  (defmodule e2_target_contract)
  (export Result)
  (defrecord Result
    (status String)))
"""


def _compile(tmp_path: Path, target: str):
    source = tmp_path / "e2_target_contract.orc"
    source.write_text(_ordinary_source(target), encoding="utf-8")
    return compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
    )


def _spec(name: str) -> str:
    return (SPECS_ROOT / name).read_text(encoding="utf-8")


def _between(document: str, start: str, end: str) -> str:
    start_index = document.index(start)
    return document[start_index : document.index(end, start_index)]


@pytest.mark.parametrize("target", ("2.24", "2.25"))
def test_ordinary_targets_through_2_25_compile_without_trial_behavior(
    tmp_path: Path,
    target: str,
) -> None:
    result = _compile(tmp_path, target)

    assert result.entry_result.module.target_dsl_version == target
    assert result.entry_result.lowered_workflows == ()
    assert result.validated_bundles_by_name == {}


def test_target_2_26_remains_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, "2.26")

    assert caught.value.diagnostics[0].code == "target_dsl_unsupported"


def test_dsl_and_version_specs_define_only_the_bounded_static_trial() -> None:
    dsl = _spec("dsl.md")
    versioning = _spec("versioning.md")
    index = _spec("index.md")
    trial = " ".join(
        _between(
            dsl,
            "  - Workflow Lisp bounded static trials (target 2.25):",
            "\n  - Workflow Lisp WCC child-call argument projection:",
        ).split()
    )
    version = " ".join(
        _between(
            versioning,
            "- v2.25 additions (Workflow Lisp bounded static trials)",
            "\n- DSL evolution rollout roadmap",
        ).split()
    )

    for marker in (
        "(trial",
        ":arms",
        ":run-ref",
        ":reps",
        ":max-concurrency",
        ":evaluation",
        ":budget",
        "2–16",
        "1–64",
        "256",
        "1–32",
        "TrialResult$<site-digest>",
        "TrialArmOutcome$<site-digest>",
        "Completed",
        "Failed",
        "TrialFailure",
        "TrialVerdictPath",
        "TrialStaticConfig.digest",
        "runtime request digest",
        "reuse_validated_trial_result",
        "maximum descriptor/value nesting depth is 64",
        "root depth 0",
        "first child at depth 65",
        "16,777,216 bytes inclusive",
        "direct-value normalization",
        'separators `(",", ":")`',
        "raw bundle or file bytes",
    ):
        assert marker in trial

    for code in (
        "trial_target_dsl_unsupported",
        "trial_arms_invalid",
        "trial_arm_result_mismatch",
        "trial_nested_unsupported",
        "trial_evaluation_contract_not_pure",
        "trial_evaluation_contract_invalid",
        "trial_evaluation_provider_unresolved",
        "trial_evaluation_rubric_unresolved",
        "trial_reps_invalid",
        "trial_concurrency_invalid",
        "trial_budget_invalid",
        "trial_packet_policy_invalid",
        "trial_packet_limit_invalid",
        "trial_blinding_policy_invalid",
        "trial_packet_citation_invalid",
    ):
        assert f"`{code}`" in trial

    assert "Targets through 2.24 remain byte-compatible" in version
    assert "run_trial_entry(" in version
    assert "orchestrate trial WORKFLOW --entry-workflow NAME" in version
    assert "raw executable configs" in version
    assert "not an OS sandbox" in version
    assert "| 2.25 |" in versioning
    assert index.startswith(
        "# Multi-Agent Orchestration — Master Spec (v1.1 through v2.25)"
    )
    assert "`trial` requires target `2.25`" in index

    current_contract = "\n".join((trial, version))
    for parked_name in (
        "ExecutionAdmissionPolicy",
        "ExecutionInstanceSpec",
        "RegisteredExecutionInstance",
        "registered execution handle",
        "registry rehash",
        "revocation service",
    ):
        assert parked_name not in current_contract


def test_provider_spec_closes_blinded_packets_scores_and_budgets() -> None:
    providers = _spec("providers.md")
    trial = " ".join(
        _between(
            providers,
            "- Workflow Lisp trial evaluator delivery (target 2.25)",
            "\n- Reusable-call provider boundary",
        ).split()
    )

    for marker in (
        "trial.evaluation_packet.v1",
        "trial.score.v1",
        "same_trust_boundary",
        "max_item_bytes",
        "max_packet_bytes",
        "task_spec",
        "validated_result",
        "workspace_delta",
        "check_results",
        "declared_artifacts",
        "failure_evidence",
        "treatment",
        "workflow source text",
        "authored workflow filenames",
        "normalized changed-file paths",
        "diff content",
        "declared-artifact relpaths",
        "proposer and candidate lineage",
        "completion order",
        ".orchestrate",
        "provider/model identity",
        "candidate_id",
        "opaque evaluation label",
        "citations",
        "exact packet",
        "authored-order",
        "median",
        "already running evaluator attempts finish and remain charged",
    ):
        assert marker in trial

    assert "select_candidate" not in trial
    assert "Source promotion" in trial
    assert "excluded" in trial


def test_state_spec_closes_single_writer_settlement_and_m2_persistence() -> None:
    state = _spec("state.md")
    trial = " ".join(
        _between(
            state,
            "## Target 2.25 Trial State, Settlement, And Replay",
            "\n## Workflow Lisp Typed Prompt-Input Evidence",
        ).split()
    )

    for marker in (
        "trial_event_ledger.v1",
        "`(arm, rep)`",
        "trial-scoped E1",
        "sole writer",
        "prepared E1 settlement",
        "cell settlement",
        "adjacent E1 `committed` transition",
        "frozen admitted evidence-set digest",
        "StepResult.trial",
        "reuse_validated_trial_result",
        "derived_pure_replay.v1",
        "exact value-free completion shell",
        "median",
        "ranking",
        "rendered packet",
        "no second derived-value cache",
        "no effect-identity memo key",
        "fresh ordinal",
    ):
        assert marker in trial

    assert '`schema_version: "2.1"`' in trial
    assert 'schema_version: "2.2"' not in trial


def test_observability_spec_exposes_only_bounded_trial_views() -> None:
    observability = _spec("observability.md")
    trial = " ".join(
        _between(
            observability,
            "## Target 2.25 Trial Observability",
            "\n## Workflow Lisp Judgment Views",
        ).split()
    )

    for marker in (
        "RUN_ROOT/trials/",
        "kind `trial`",
        "Authored arm IDs",
        "after the unblinded verdict join",
        "verdict digest",
        "budget counters",
        "value-free completion shell",
        "opaque-label map",
        "packet bodies",
        "score summaries",
        "current-only",
        "Ordinary non-trial runs",
        "zero trial sidecars",
    ):
        assert marker in trial

    assert "routing authority" not in trial
    assert "non-authoritative" in trial
