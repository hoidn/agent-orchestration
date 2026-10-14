from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow.provider_phased_delivery.protocol import (
    diagnostic_from_dict,
)
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    serialize_diagnostic,
)
from orchestrator.workflow_lisp.expressions import LiteralExpr, ProviderResultExpr
from orchestrator.workflow_lisp.prompts import PromptApplicationExpr


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = (
    REPO_ROOT
    / "tests/fixtures/workflow_lisp/phased_contract_delivery/phased.orc"
)


def _compile(*, route: str = "wcc_m4"):
    return compile_stage3_module(
        SOURCE.relative_to(REPO_ROOT),
        entry_workflow="phased-review",
        provider_externs={"providers.review": "test-provider"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=REPO_ROOT,
        lowering_route=route,
    )


def _compile_composed():
    source = SOURCE.with_name("composed.orc")
    return compile_stage3_module(
        source.relative_to(REPO_ROOT),
        entry_workflow="composed-review",
        provider_externs={"providers.review": "test-provider"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=REPO_ROOT,
        lowering_route="wcc_m4",
    )


def _compile_source(tmp_path: Path, *, target: str, sections: str):
    source = tmp_path / "policy.orc"
    source.write_text(
        f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target}")
  (defmodule phased_policy)
  (export check)
  (defrecord Result (approved Bool))
  (defprompt review-prompt
    (:fills (subject :text))
    -> Result
    "Review {{subject}}")
  (defworkflow check ((subject String)) -> Result
    (provider-result providers.review
      :prompt (review-prompt :subject subject)
      {sections})))
""",
        encoding="utf-8",
    )
    return compile_stage3_module(
        source,
        entry_workflow="check",
        provider_externs={"providers.review": "test-provider"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )


@pytest.mark.parametrize("route", ("legacy", "wcc_m2", "wcc_m3", "wcc_m4"))
def test_phased_policy_defaults_and_identity_stay_paired_through_carriers(
    route: str,
) -> None:
    result = _compile(route=route)
    typed_expr = result.typed_workflows[0].typed_body.expr
    assert isinstance(typed_expr, ProviderResultExpr)
    assert isinstance(typed_expr.delivery, LiteralExpr)
    assert typed_expr.delivery.literal_kind == "string"
    assert typed_expr.delivery.value == "phased"
    assert isinstance(typed_expr.materialization_attempts, LiteralExpr)
    assert typed_expr.materialization_attempts.value == 2
    assert isinstance(typed_expr.prompt, PromptApplicationExpr)
    assert (
        typed_expr.prompt.prompt_attempt_identity_version
        == "workflow_prompt_attempt_identity.v2"
    )

    expected_policy = {
        "delivery": "phased",
        "materialization_attempts": 2,
    }


def test_explicit_composed_keeps_typed_identity_v1_without_default_attempts(
) -> None:
    result = _compile_composed()
    typed_expr = result.typed_workflows[0].typed_body.expr
    assert isinstance(typed_expr, ProviderResultExpr)
    assert isinstance(typed_expr.delivery, LiteralExpr)
    assert typed_expr.delivery.literal_kind == "string"
    assert typed_expr.delivery.value == "composed"
    assert typed_expr.materialization_attempts is None
    assert isinstance(typed_expr.prompt, PromptApplicationExpr)
    assert (
        typed_expr.prompt.prompt_attempt_identity_version
        == "workflow_prompt_attempt_identity.v1"
    )






@pytest.mark.parametrize(
    (
        "target",
        "sections",
        "code",
        "reason",
        "canonical_value",
        "primary_owner",
    ),
    (
        (
            "2.22",
            ":delivery :phased",
            "provider_phased_delivery_requires_dsl_2_23",
            "target_below_2_23",
            "2.22",
            "delivery_keyword",
        ),
        (
            "2.23",
            ":delivery true",
            "provider_phased_delivery_policy_invalid",
            "delivery_type_invalid",
            None,
            "delivery_keyword",
        ),
        (
            "2.23",
            ":delivery :unknown",
            "provider_phased_delivery_policy_invalid",
            "delivery_enum_invalid",
            None,
            "delivery_keyword",
        ),
        (
            "2.23",
            ":materialization-attempts 2",
            "provider_phased_delivery_policy_invalid",
            "attempts_pairing_invalid",
            None,
            "materialization_attempts_keyword",
        ),
        (
            "2.23",
            ":delivery :composed :materialization-attempts 2",
            "provider_phased_delivery_policy_invalid",
            "attempts_pairing_invalid",
            None,
            "materialization_attempts_keyword",
        ),
        (
            "2.23",
            ":delivery :phased :materialization-attempts true",
            "provider_phased_delivery_policy_invalid",
            "attempts_type_invalid",
            None,
            "materialization_attempts_keyword",
        ),
        (
            "2.23",
            ":delivery :phased :materialization-attempts 0",
            "provider_phased_delivery_policy_invalid",
            "attempts_out_of_range",
            0,
            "materialization_attempts_keyword",
        ),
        (
            "2.23",
            ":delivery :phased :materialization-attempts 4",
            "provider_phased_delivery_policy_invalid",
            "attempts_out_of_range",
            4,
            "materialization_attempts_keyword",
        ),
    ),
)
def test_phased_policy_rejects_target_pairing_boolean_and_range_errors(
    tmp_path: Path,
    target: str,
    sections: str,
    code: str,
    reason: str,
    canonical_value: str | int | None,
    primary_owner: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as exc_info:
        _compile_source(
            tmp_path,
            target=target,
            sections=sections,
        )

    diagnostic = exc_info.value.diagnostics[0]
    assert diagnostic.code == code
    if reason == "attempts_out_of_range":
        assert f"value={canonical_value}" in diagnostic.message
        assert "minimum=1" in diagnostic.message
        assert "maximum=3" in diagnostic.message
    assert diagnostic.span.start.path.endswith("policy.orc")
    assert diagnostic.span.start.line == 14
    serialized = serialize_diagnostic(diagnostic)
    exact = serialized["phased_delivery_diagnostic"]
    assert isinstance(exact, dict)
    assert diagnostic_from_dict(exact).reason == reason
    assert tuple(exact) == (
        "schema_version",
        "code",
        "reason",
        "rejected_value",
        "primary_source",
        "related_sources",
    )
    assert exact["schema_version"] == (
        "provider_phased_delivery_diagnostic.v1"
    )
    assert exact["code"] == code
    assert exact["reason"] == reason
    assert exact["rejected_value"]["canonical_value"] == canonical_value
    assert exact["rejected_value"]["summary"] == reason
    assert exact["primary_source"]["owner"] == primary_owner
    assert exact["primary_source"]["kind"] == "authored_span"
    assert exact["primary_source"]["path"].endswith("policy.orc")
    assert [source["owner"] for source in exact["related_sources"]] == [
        "provider_application"
    ]
    assert exact["related_sources"][0]["kind"] == "authored_span"


def test_phased_fragment_requires_non_empty_generated_contract_suffix(
    tmp_path: Path,
) -> None:
    source = tmp_path / "empty-result.orc"
    source.write_text(
        SOURCE.read_text(encoding="utf-8").replace(
            "(defrecord PhasedReviewResult\n    (approved Bool))",
            "(defrecord PhasedReviewResult)",
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as exc_info:
        compile_stage3_module(
            source,
            entry_workflow="phased-review",
            provider_externs={"providers.review": "test-provider"},
            prompt_externs={},
            validate_shared=True,
            workspace_root=tmp_path,
            lowering_route="wcc_m4",
        )

    diagnostic = exc_info.value.diagnostics[0]
    assert diagnostic.code == "provider_phased_delivery_policy_invalid"
    assert "contract_suffix_required" in diagnostic.message
    assert diagnostic.span.start.path.endswith("empty-result.orc")
    exact = serialize_diagnostic(diagnostic)["phased_delivery_diagnostic"]
    assert isinstance(exact, dict)
    assert diagnostic_from_dict(exact).reason == "contract_suffix_required"
    assert exact["primary_source"]["owner"] == "result_contract_suffix"
    assert [source["owner"] for source in exact["related_sources"]] == [
        "provider_application"
    ]


def test_phased_delivery_rejects_extern_prompt_without_fragment_contract(
    tmp_path: Path,
) -> None:
    source = tmp_path / "extern-prompt.orc"
    source.write_text(
        """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.23")
  (defmodule phased_extern)
  (export review)
  (defworkflow review ((subject String)) -> Bool
    (provider-result providers.review
      :prompt prompts.review
      :inputs (subject)
      :returns Bool
      :delivery :phased)))
""",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as exc_info:
        compile_stage3_module(
            source,
            entry_workflow="review",
            provider_externs={"providers.review": "test-provider"},
            prompt_externs={"prompts.review": "prompts/review.md"},
            validate_shared=True,
            workspace_root=tmp_path,
            lowering_route="wcc_m4",
        )

    diagnostic = exc_info.value.diagnostics[0]
    assert diagnostic.code == "provider_phased_delivery_policy_invalid"
    assert "requires a fragment-backed prompt" in diagnostic.message
    assert diagnostic.span.start.path.endswith("extern-prompt.orc")
    exact = serialize_diagnostic(diagnostic)["phased_delivery_diagnostic"]
    assert isinstance(exact, dict)
    assert diagnostic_from_dict(exact).reason == (
        "fragment_application_required"
    )
    assert exact["primary_source"]["owner"] == "fragment_contract"
    assert [source["owner"] for source in exact["related_sources"]] == [
        "provider_application"
    ]
