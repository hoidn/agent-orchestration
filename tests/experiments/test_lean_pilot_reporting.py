from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import json
import os
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from orchestrator.experiments.contracts import (
    canonical_json_bytes,
    canonical_sha256,
    validate_record,
)


TREATMENTS = ("DIRECT", "COORDINATOR", "ORC")
COMPARISONS = ("DIRECT_VS_ORC", "COORDINATOR_VS_ORC")


@pytest.fixture(scope="module")
def reporting() -> ModuleType:
    return importlib.import_module("orchestrator.experiments.reporting")


def test_reporting_facade_and_private_owners_are_bounded_and_acyclic(
    reporting: ModuleType,
) -> None:
    package_root = Path(reporting.__file__).parent
    expected_private_modules = {
        "_reporting_metrics.py",
        "_reporting_render.py",
        "_reporting_reviews.py",
        "_reporting_sample_size.py",
        "_reporting_synthesis.py",
        "_reporting_types.py",
        "_reporting_validation.py",
    }
    private_paths = {
        path.name: path
        for path in package_root.glob("_reporting_*.py")
    }
    assert set(private_paths) == expected_private_modules
    assert reporting.__all__ == [
        "ExactSampleSizePlan",
        "ReviewBinding",
        "ReportingError",
        "UnblindingBinding",
        "assess_readiness",
        "build_pilot_summary",
        "exact_binomial_tail",
        "parse_canonical_decimal",
        "plan_exact_sample_size",
        "plan_sample_size",
        "load_attempt_records",
        "render_pilot_markdown",
    ]
    expected_owners = {
        "ExactSampleSizePlan": "_reporting_types",
        "ReviewBinding": "_reporting_types",
        "ReportingError": "_reporting_types",
        "UnblindingBinding": "_reporting_types",
        "assess_readiness": "_reporting_validation",
        "build_pilot_summary": "_reporting_synthesis",
        "exact_binomial_tail": "_reporting_sample_size",
        "parse_canonical_decimal": "_reporting_sample_size",
        "plan_exact_sample_size": "_reporting_sample_size",
        "plan_sample_size": "_reporting_sample_size",
        "load_attempt_records": "_reporting_validation",
        "render_pilot_markdown": "_reporting_render",
    }
    assert {
        name: getattr(reporting, name).__module__.rsplit(".", 1)[-1]
        for name in reporting.__all__
    } == expected_owners

    facade_path = Path(reporting.__file__)
    module_paths = {"reporting": facade_path, **private_paths}
    dependencies: dict[str, set[str]] = {}
    for name, path in module_paths.items():
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) <= 500
        tree = ast.parse(source)
        if name == "reporting":
            assert not any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                for node in tree.body
            )
        dependencies[name] = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.level == 1
            and isinstance(node.module, str)
            and node.module.startswith("_reporting_")
        }

    def visit(name: str, active: set[str], complete: set[str]) -> None:
        if name in complete:
            return
        assert name not in active, f"reporting import cycle at {name}"
        active.add(name)
        for dependency in dependencies[name]:
            visit(f"{dependency}.py", active, complete)
        active.remove(name)
        complete.add(name)

    complete: set[str] = set()
    for module_name in dependencies:
        visit(module_name, set(), complete)


def _digest(label: str) -> str:
    return f"sha256:{hashlib.sha256(label.encode()).hexdigest()}"


def _bundle_digest(
    manifest: list[dict[str, str]],
    paths: list[str],
) -> str:
    by_path = {entry["path"]: entry for entry in manifest}
    return canonical_sha256(
        [by_path[path] for path in sorted(paths, key=str.encode)]
    )


def _label_mapping(lock: dict[str, Any], block_id: str) -> dict[str, str]:
    seed = lock["randomization_seed"]
    ordered_treatments = sorted(
        TREATMENTS,
        key=lambda treatment: hashlib.sha256(
            f"{seed}\0{block_id}\0role\0{treatment}".encode()
        ).digest(),
    )
    labels = [
        "candidate-"
        + hashlib.sha256(
            f"{seed}\0{block_id}\0label\0{index}".encode()
        ).hexdigest()[:12]
        for index in range(len(TREATMENTS))
    ]
    return {
        treatment: label
        for label, treatment in zip(labels, ordered_treatments, strict=True)
    }


def _lock(*, reviewers: tuple[str, ...] = ("reviewer-1", "reviewer-2")) -> dict[str, Any]:
    manifest = [
        {"path": "tasks/A1.md", "sha256": _digest("task")},
        {"path": "provider.json", "sha256": _digest("provider")},
        {"path": "prompts.json", "sha256": _digest("prompts")},
        {"path": "commands.json", "sha256": _digest("commands")},
        {"path": "source.py", "sha256": _digest("source")},
        {"path": "review/rubric.md", "sha256": _digest("rubric")},
        {
            "path": "review/calibration-seal.json",
            "sha256": _digest("calibration"),
        },
        {
            "path": "evaluation/config.json",
            "sha256": _digest("evaluator-config"),
        },
        {
            "path": "evaluation/evaluator.py",
            "sha256": _digest("evaluator"),
        },
        {
            "path": "review/reviewer-command.json",
            "sha256": _digest("reviewer-command"),
        },
        {
            "path": "review/review-result.schema.json",
            "sha256": _digest("review-schema"),
        },
    ]
    treatments = []
    for treatment, bounds in (
        ("DIRECT", {"minimum": 1, "maximum": 1}),
        ("COORDINATOR", {"minimum": 3, "maximum": 9}),
        ("ORC", {"minimum": 3, "maximum": 9}),
    ):
        path = f"treatments/{treatment.lower()}.json"
        digest = _digest(f"{treatment}-command")
        manifest.append({"path": path, "sha256": digest})
        treatments.append(
            {
                "treatment_id": treatment,
                "source_asset_paths": [path, "source.py"],
                "source_digest": _bundle_digest(
                    manifest,
                    [path, "source.py"],
                ),
                "command_digest": digest,
                "command_config_path": path,
                "provider_call_bounds": bounds,
            }
        )
    evaluator_paths = [
        "evaluation/config.json",
        "evaluation/evaluator.py",
    ]
    reviewer_command_paths = [
        "review/reviewer-command.json",
        "review/review-result.schema.json",
    ]
    record = {
        "record_kind": "pilot_lock.v1",
        "pilot_id": "lean-pilot-test",
        "task": {
            "task_id": "A1",
            "source_path": "task.md",
            "profile_digest": _digest("pending-profile"),
            "brief_digest": _digest("task"),
        },
        "archive": {
            "repository_identity": "/source/repository",
            "repository_root": "/source/repository",
            "revision_identity": f"commit:{'1' * 40}",
            "source_subtree_path": "benchmark",
            "source_tree_identity": f"git-tree:{'2' * 40}",
            "archive_digest": _digest("archive"),
        },
        "provider_policy": {
            "family": "codex",
            "model": "gpt-test",
            "reasoning_effort": "high",
            "tool_policy": "workspace-write-no-network",
            "timeout_milliseconds": 900_000,
            "currency": "USD",
        },
        "review": {
            "reviewer_ids": list(reviewers),
            "disagreement_policy": "INDETERMINATE_ON_DISAGREEMENT",
            "selected_final_files": ["result.txt"],
            "permitted_check_evidence_names": [
                "check-stderr.txt",
                "check-stdout.txt",
                "hidden-evaluator.json",
            ],
            "rubric_path": "review/rubric.md",
            "rubric_digest": _digest("rubric"),
            "calibration_evidence_path": "review/calibration-seal.json",
            "calibration_evidence_digest": _digest("calibration"),
            "evaluator": {
                "config_path": "evaluation/config.json",
                "asset_paths": evaluator_paths,
                "bundle_digest": _bundle_digest(manifest, evaluator_paths),
            },
            "reviewer_command": {
                "config_path": "review/reviewer-command.json",
                "asset_paths": reviewer_command_paths,
                "bundle_digest": _bundle_digest(
                    manifest,
                    reviewer_command_paths,
                ),
            },
        },
        "apparatus": {
            "control_root": "/control/root",
            "asset_manifest": manifest,
            "treatment_asset_paths": [
                row["path"]
                for row in manifest
                if not row["path"].startswith(("evaluation/", "review/"))
            ],
            "task_path": "tasks/A1.md",
            "provider_config_path": "provider.json",
            "prompt_config_path": "prompts.json",
            "command_config_path": "commands.json",
            "environment": {
                "identity": _digest("environment"),
                "allowed_keys": ["HOME", "PATH", "TMPDIR"],
                "credential_keys": [],
            },
            "visible_check": {
                "argv": ["python", "-m", "pytest", "-q"],
                "timeout_milliseconds": 120_000,
            },
            "product_projection_exclusions": [".git"],
            "maximum_start_skew_milliseconds": 500,
            "quiescence_grace_milliseconds": 2_000,
        },
        "randomization_seed": "seed",
        "evidence_root": "/evidence/root",
        "valid_block_count": 3,
        "max_live_attempt_count": 5,
        "smoke_id": "smoke",
        "live_attempt_ids": ["live-1", "live-2", "live-3", "live-4", "live-5"],
        "claim_level": "exploratory_controlled_task",
        "treatments": treatments,
    }
    record["task"]["profile_digest"] = canonical_sha256(
        {
            "profile_version": "lean-pilot-task-profile.v1",
            "task_id": record["task"]["task_id"],
            "source_path": record["task"]["source_path"],
            "brief_digest": record["task"]["brief_digest"],
            "archive_digest": record["archive"]["archive_digest"],
            "selected_final_files": record["review"]["selected_final_files"],
            "permitted_check_evidence_names": record["review"][
                "permitted_check_evidence_names"
            ],
            "visible_check": record["apparatus"]["visible_check"],
            "product_projection_exclusions": record["apparatus"][
                "product_projection_exclusions"
            ],
            "evaluator_bundle_digest": record["review"]["evaluator"][
                "bundle_digest"
            ],
        }
    )
    return record


def _execution(
    treatment: str,
    block_number: int,
    *,
    lifecycle: str = "COMPLETED",
    product_frozen: bool = True,
    cost: object | None = None,
) -> dict[str, Any]:
    multiplier = {"DIRECT": 1, "COORDINATOR": 2, "ORC": 3}[treatment]
    call_count = {"DIRECT": 1, "COORDINATOR": 5, "ORC": 7}[treatment]
    record: dict[str, Any] = {
        "opaque_arm_label": f"arm-{treatment.lower()}-{block_number}",
        "treatment_id": treatment,
        "command_digest": _digest(f"{treatment}-command"),
        "lifecycle_outcome": lifecycle,
        "product_frozen": product_frozen,
        "provider_call_count": call_count,
        "elapsed_milliseconds": multiplier * block_number * 10,
        "evidence_references": [
            f"blocks/live-{block_number}/{treatment.lower()}/result.json"
        ],
        "token_counts": {"input": 10, "output": 5},
        "cost": (
            {
                "cost_microunits": multiplier * block_number * 100,
                "currency": "USD",
            }
            if cost is None
            else cost
        ),
    }
    if product_frozen:
        record["product_manifest_digest"] = _digest(
            f"product-{treatment}-{block_number}"
        )
    return record


def _attempt(
    lock: dict[str, Any],
    *,
    block_id: str,
    attempt_class: str,
    sequence_index: int,
    status: str = "VALID",
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "record_kind": "block_attempt.v1",
        "pilot_lock_digest": canonical_sha256(lock),
        "attempt_class": attempt_class,
        "sequence_index": sequence_index,
        "block_id": block_id,
        "status": status,
    }
    if status == "STARTED":
        record["treatment_executions"] = []
    elif status == "VALID":
        number = 1 if attempt_class == "SMOKE" else sequence_index + 1
        record["treatment_executions"] = [
            _execution(treatment, number) for treatment in TREATMENTS
        ]
    else:
        record["reason_code"] = f"{status}_FIXTURE"
        record["treatment_executions"] = []
    return record


def _review(
    lock: dict[str, Any],
    *,
    block_id: str,
    reviewer: str,
    outcomes: tuple[str, str],
    guesses: tuple[str, str, str],
) -> dict[str, Any]:
    mapping = _label_mapping(lock, block_id)
    labels = tuple(mapping[treatment] for treatment in TREATMENTS)
    return {
        "record_kind": "review_result.v1",
        "review_id": f"{block_id}-{reviewer}",
        "pilot_lock_digest": canonical_sha256(lock),
        "reviewer_id": reviewer,
        "session_id": f"session-{block_id}-{reviewer}",
        "review_class": "LIVE",
        "rubric_digest": lock["review"]["rubric_digest"],
        "candidates": [
            {
                "opaque_label": label,
                "evidence_citations": [f"packages/{block_id}/{label}/diff.patch"],
                "dimension_assessments": [
                    {
                        "dimension": dimension,
                        "assessment": "PASS",
                        "rationale": f"{dimension} is supported for {label}.",
                        "evidence_citations": [
                            f"packages/{block_id}/{label}/diff.patch"
                        ],
                    }
                    for dimension in (
                        "TASK_COMPLETENESS",
                        "BEHAVIORAL_CORRECTNESS",
                        "MAINTAINABILITY",
                        "SCOPE_CONTROL",
                        "EVIDENCE_QUALITY",
                    )
                ],
                "sealed_treatment_guess": guess,
            }
            for label, guess in zip(labels, guesses, strict=True)
        ],
        "pairwise_results": [
            {
                "candidate_a_label": mapping["DIRECT"],
                "candidate_b_label": mapping["ORC"],
                "outcome": outcomes[0],
                "rationale": "The cited evidence supports this comparison.",
                "evidence_citations": [f"packages/{block_id}/direct-orc.json"],
            },
            {
                "candidate_a_label": mapping["COORDINATOR"],
                "candidate_b_label": mapping["ORC"],
                "outcome": outcomes[1],
                "rationale": "The cited evidence supports this comparison.",
                "evidence_citations": [f"packages/{block_id}/coordinator-orc.json"],
            },
        ],
    }


def _case(
    reporting: ModuleType,
    *,
    reviewer_ids: tuple[str, ...] = ("reviewer-1", "reviewer-2"),
    disagree: bool = False,
    include_adjudicator: bool = False,
) -> dict[str, Any]:
    lock = _lock(reviewers=reviewer_ids)
    attempts = [
        _attempt(
            lock,
            block_id="smoke",
            attempt_class="SMOKE",
            sequence_index=0,
        )
    ]
    outcomes = (("A", "B"), ("TIE", "INDETERMINATE"), ("B", "A"))
    reviews: list[dict[str, Any]] = []
    review_bindings: list[object] = []
    unblinding: list[object] = []
    for index, block_id in enumerate(lock["live_attempt_ids"][:3]):
        attempts.append(
            _attempt(
                lock,
                block_id=block_id,
                attempt_class="LIVE",
                sequence_index=index,
            )
        )
        package_digest = _digest(f"package-{block_id}")
        for treatment, label in zip(
            TREATMENTS,
            (
                _label_mapping(lock, block_id)[treatment]
                for treatment in TREATMENTS
            ),
            strict=True,
        ):
            unblinding.append(
                reporting.UnblindingBinding(
                    block_id=block_id,
                    package_id=block_id,
                    package_manifest_digest=package_digest,
                    opaque_label=label,
                    treatment_id=treatment,
                )
            )
        for reviewer_index, reviewer in enumerate(reviewer_ids[:2]):
            reviewer_outcomes = outcomes[index]
            if disagree and index == 0 and reviewer_index == 1:
                reviewer_outcomes = ("B", "B")
            guesses = TREATMENTS if reviewer_index == 0 else ("UNKNOWN",) * 3
            review = _review(
                lock,
                block_id=block_id,
                reviewer=reviewer,
                outcomes=reviewer_outcomes,
                guesses=guesses,
            )
            reviews.append(review)
            review_bindings.append(
                reporting.ReviewBinding(
                    block_id=block_id,
                    package_id=block_id,
                    package_manifest_digest=package_digest,
                    review_id=review["review_id"],
                    review_result_digest=canonical_sha256(review),
                    review_path=f"reviews/{review['review_id']}.json",
                    reviewer_id=reviewer,
                    reviewer_role="INITIAL",
                )
            )
        if index == 0 and include_adjudicator:
            reviewer = reviewer_ids[2]
            review = _review(
                lock,
                block_id=block_id,
                reviewer=reviewer,
                outcomes=outcomes[index],
                guesses=("UNKNOWN",) * 3,
            )
            reviews.append(review)
            review_bindings.append(
                reporting.ReviewBinding(
                    block_id=block_id,
                    package_id=block_id,
                    package_manifest_digest=package_digest,
                    review_id=review["review_id"],
                    review_result_digest=canonical_sha256(review),
                    review_path=f"reviews/{review['review_id']}.json",
                    reviewer_id=reviewer,
                    reviewer_role="ADJUDICATOR",
                )
            )
    return {
        "lock": lock,
        "block_attempts": attempts,
        "reviews": reviews,
        "sealed_review_bindings": review_bindings,
        "unblinding": unblinding,
    }


def _summary(reporting: ModuleType, **case_overrides: object) -> dict[str, Any]:
    case = _case(reporting)
    case.update(case_overrides)
    return reporting.build_pilot_summary(**case)


def _find(items: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    return next(item for item in items if item[key] == value)


def test_summary_reports_exact_comparison_treatment_and_review_diagnostics(
    reporting: ModuleType,
) -> None:
    summary = _summary(reporting)

    assert summary["status"] == "EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED"
    direct_orc = _find(
        summary["comparison_counts"], "comparison", "DIRECT_VS_ORC"
    )
    assert direct_orc == {
        "comparison": "DIRECT_VS_ORC",
        "a_win_count": 1,
        "b_win_count": 1,
        "tie_count": 1,
        "indeterminate_count": 0,
        "tie_nonviable_count": 0,
    }
    coordinator = _find(
        summary["treatment_statistics"], "treatment_id", "COORDINATOR"
    )
    assert coordinator["viable_count"] == 3
    assert coordinator["nonviable_count"] == 0
    assert coordinator["provider_call_counts"] == [5, 5, 5]
    assert coordinator["lifecycle_outcome_counts"]["COMPLETED"] == 3
    assert summary["review_diagnostics"]["agreement_count"] == 6
    assert summary["review_diagnostics"]["disagreement_count"] == 0
    assert summary["review_diagnostics"]["adjudication_count"] == 0
    assert summary["review_diagnostics"]["guess_accuracy"] == {
        "numerator": 1,
        "denominator": 2,
    }
    assert len(summary["review_diagnostics"]["blocks"]) == 3
    validate_record(summary)


def test_summary_uses_exact_medians_ratios_and_unknown_cost_propagation(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    direct = next(
        execution
        for execution in case["block_attempts"][2]["treatment_executions"]
        if execution["treatment_id"] == "DIRECT"
    )
    direct["cost"] = "UNKNOWN"

    summary = reporting.build_pilot_summary(**case)

    elapsed = {
        item["treatment_id"]: item["value"]
        for item in summary["medians"]
        if item["metric"] == "elapsed_milliseconds"
    }
    assert elapsed == {
        "DIRECT": {"numerator": 20, "denominator": 1},
        "COORDINATOR": {"numerator": 40, "denominator": 1},
        "ORC": {"numerator": 60, "denominator": 1},
    }
    ratios = {
        (item["metric"], item["denominator_treatment_id"]): item["value"]
        for item in summary["ratios"]
    }
    assert ratios[("elapsed_milliseconds", "DIRECT")] == {
        "numerator": 3,
        "denominator": 1,
    }
    assert ratios[("elapsed_milliseconds", "COORDINATOR")] == {
        "numerator": 3,
        "denominator": 2,
    }
    assert ratios[("cost_microunits", "DIRECT")] == "UNKNOWN"


def test_treatment_failure_remains_in_denominator_and_stats(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    failed = next(
        execution
        for execution in case["block_attempts"][1]["treatment_executions"]
        if execution["treatment_id"] == "ORC"
    )
    failed.update(lifecycle_outcome="TIMEOUT", product_frozen=False)
    failed.pop("product_manifest_digest")

    summary = reporting.build_pilot_summary(**case)

    assert len(summary["valid_blocks"]) == 3
    orc = _find(summary["treatment_statistics"], "treatment_id", "ORC")
    assert orc["viable_count"] == 2
    assert orc["nonviable_count"] == 1
    assert orc["failure_class_counts"]["TIMEOUT"] == 1
    block = _find(summary["valid_blocks"], "block_id", "live-1")
    assert all(
        item["method_outcome"] == "A_WIN"
        for item in block["method_outcomes"]
    )


def test_sole_viable_precedence_does_not_require_failed_candidate_review(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    failed = next(
        execution
        for execution in case["block_attempts"][1]["treatment_executions"]
        if execution["treatment_id"] == "ORC"
    )
    failed.update(lifecycle_outcome="NONZERO_EXIT", product_frozen=False)
    failed.pop("product_manifest_digest")
    block_reviews = [
        review for review in case["reviews"] if review["review_id"].startswith("live-1-")
    ]
    for review in block_reviews:
        review["candidates"] = review["candidates"][:2]
        review["pairwise_results"] = [
            {
                "candidate_a_label": _label_mapping(
                    case["lock"], "live-1"
                )["DIRECT"],
                "candidate_b_label": _label_mapping(
                    case["lock"], "live-1"
                )["COORDINATOR"],
                "outcome": "TIE",
                "rationale": "The cited evidence supports a tie.",
                "evidence_citations": ["packages/live-1/direct-coordinator.json"],
            }
        ]
    case["unblinding"] = [
        binding
        for binding in case["unblinding"]
        if not (
            binding.block_id == "live-1"
            and binding.treatment_id == "ORC"
        )
    ]
    case["sealed_review_bindings"] = [
        copy.replace(
            binding,
            review_result_digest=canonical_sha256(
                next(
                    review
                    for review in block_reviews
                    if review["review_id"] == binding.review_id
                )
            ),
        )
        if binding.block_id == "live-1"
        else binding
        for binding in case["sealed_review_bindings"]
    ]

    summary = reporting.build_pilot_summary(**case)

    block = _find(summary["valid_blocks"], "block_id", "live-1")
    assert [item["method_outcome"] for item in block["method_outcomes"]] == [
        "A_WIN",
        "A_WIN",
    ]
    assert all(
        item["product_quality_review"] == "NOT_APPLICABLE"
        for item in block["method_outcomes"]
    )


def test_two_nonviable_treatments_keep_review_separate_from_method_outcome(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    for treatment in ("DIRECT", "ORC"):
        execution = next(
            item
            for item in case["block_attempts"][1]["treatment_executions"]
            if item["treatment_id"] == treatment
        )
        execution["lifecycle_outcome"] = "CHECK_FAILURE"

    summary = reporting.build_pilot_summary(**case)

    block = _find(summary["valid_blocks"], "block_id", "live-1")
    outcome = _find(
        block["method_outcomes"], "comparison", "DIRECT_VS_ORC"
    )
    assert outcome["method_outcome"] == "TIE_NONVIABLE"
    assert outcome["product_quality_review"]["outcome"] == "A"


def test_treatment_guesses_cannot_change_sealed_method_judgments(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    before = reporting.build_pilot_summary(**case)
    for review in case["reviews"]:
        for candidate in review["candidates"]:
            candidate["sealed_treatment_guess"] = "UNKNOWN"
    case["sealed_review_bindings"] = [
        copy.replace(
            binding,
            review_result_digest=canonical_sha256(
                next(
                    review
                    for review in case["reviews"]
                    if review["review_id"] == binding.review_id
                )
            ),
        )
        for binding in case["sealed_review_bindings"]
    ]

    after = reporting.build_pilot_summary(**case)

    def _judgments(summary: dict[str, Any]) -> list[list[tuple[str, str, str]]]:
        return [
            [
                (
                    outcome["comparison"],
                    outcome["method_outcome"],
                    (
                        outcome["product_quality_review"]["outcome"]
                        if isinstance(outcome["product_quality_review"], dict)
                        else outcome["product_quality_review"]
                    ),
                )
                for outcome in block["method_outcomes"]
            ]
            for block in summary["valid_blocks"]
        ]

    assert _judgments(after) == _judgments(before)
    assert after["valid_blocks"] != before["valid_blocks"]
    assert after["comparison_counts"] == before["comparison_counts"]
    assert after["review_diagnostics"]["guess_accuracy"] == {
        "numerator": 0,
        "denominator": 1,
    }


@pytest.mark.parametrize("status", ["INVALID", "ABORTED", "STARTED"])
def test_excluded_attempts_are_adjacent_to_valid_denominator(
    reporting: ModuleType,
    status: str,
) -> None:
    case = _case(reporting)
    lock = case["lock"]
    excluded = _attempt(
        lock,
        block_id="live-1",
        attempt_class="LIVE",
        sequence_index=0,
        status=status,
    )
    case["block_attempts"] = [case["block_attempts"][0], excluded]
    for index, block_id in enumerate(lock["live_attempt_ids"][1:4], start=1):
        case["block_attempts"].append(
            _attempt(
                lock,
                block_id=block_id,
                attempt_class="LIVE",
                sequence_index=index,
            )
        )
    for review, binding, unblind in (
        (case["reviews"], case["sealed_review_bindings"], case["unblinding"]),
    ):
        del review[:]
        del binding[:]
        del unblind[:]
    regenerated = _case(reporting)
    for block_id in lock["live_attempt_ids"][1:4]:
        case["reviews"].extend(
            item
            for item in regenerated["reviews"]
            if item["review_id"].startswith(f"{block_id}-")
        )
        case["sealed_review_bindings"].extend(
            item
            for item in regenerated["sealed_review_bindings"]
            if item.block_id == block_id
        )
        case["unblinding"].extend(
            item
            for item in regenerated["unblinding"]
            if item.block_id == block_id
        )
    # Regenerate the review records against the unchanged lock and selected IDs.
    case["reviews"] = []
    case["sealed_review_bindings"] = []
    case["unblinding"] = []
    for block_id in lock["live_attempt_ids"][1:4]:
        package_digest = _digest(f"package-{block_id}")
        for treatment, label in zip(
            TREATMENTS,
            (
                _label_mapping(lock, block_id)[treatment]
                for treatment in TREATMENTS
            ),
            strict=True,
        ):
            case["unblinding"].append(
                reporting.UnblindingBinding(
                    block_id,
                    block_id,
                    package_digest,
                    label,
                    treatment,
                )
            )
        for reviewer in lock["review"]["reviewer_ids"]:
            record = _review(
                lock,
                block_id=block_id,
                reviewer=reviewer,
                outcomes=("A", "A"),
                guesses=("UNKNOWN",) * 3,
            )
            case["reviews"].append(record)
            case["sealed_review_bindings"].append(
                reporting.ReviewBinding(
                    block_id,
                    block_id,
                    package_digest,
                    record["review_id"],
                    canonical_sha256(record),
                    f"reviews/{record['review_id']}.json",
                    reviewer,
                    "INITIAL",
                )
            )

    summary = reporting.build_pilot_summary(**case)

    assert len(summary["valid_blocks"]) == 3
    assert summary["excluded_block_references"] == [
        {
            "block_id": "live-1",
            "block_attempt_digest": canonical_sha256(excluded),
            "status": status,
        }
    ]


def test_attempt_loader_requires_exact_contiguous_locked_paths(
    reporting: ModuleType,
    tmp_path: Path,
) -> None:
    lock = _lock()
    lock["evidence_root"] = tmp_path.as_posix()
    records = [
        _attempt(lock, block_id="smoke", attempt_class="SMOKE", sequence_index=0),
        *[
            _attempt(
                lock,
                block_id=block_id,
                attempt_class="LIVE",
                sequence_index=index,
            )
            for index, block_id in enumerate(lock["live_attempt_ids"][:3])
        ],
    ]
    for record in records:
        path = tmp_path / record["block_id"] / "block-attempt.json"
        path.parent.mkdir()
        path.write_bytes(canonical_json_bytes(record))

    assert reporting.load_attempt_records(lock=lock, evidence_root=tmp_path) == tuple(
        records
    )
    (tmp_path / "live-2" / "block-attempt.json").unlink()
    with pytest.raises(reporting.ReportingError, match="attempt_prefix_gap"):
        reporting.load_attempt_records(lock=lock, evidence_root=tmp_path)


def test_attempt_loader_rejects_selective_extension_after_third_valid(
    reporting: ModuleType,
    tmp_path: Path,
) -> None:
    lock = _lock()
    lock["evidence_root"] = tmp_path.as_posix()
    records = [
        _attempt(lock, block_id="smoke", attempt_class="SMOKE", sequence_index=0),
        *[
            _attempt(
                lock,
                block_id=block_id,
                attempt_class="LIVE",
                sequence_index=index,
            )
            for index, block_id in enumerate(lock["live_attempt_ids"][:4])
        ],
    ]
    for record in records:
        path = tmp_path / record["block_id"] / "block-attempt.json"
        path.parent.mkdir()
        path.write_bytes(canonical_json_bytes(record))

    with pytest.raises(reporting.ReportingError, match="attempt_after_denominator"):
        reporting.load_attempt_records(lock=lock, evidence_root=tmp_path)


def test_readiness_has_only_locked_terminal_states(reporting: ModuleType) -> None:
    lock = _lock()
    smoke_failed = _attempt(
        lock,
        block_id="smoke",
        attempt_class="SMOKE",
        sequence_index=0,
        status="INVALID",
    )
    assert reporting.assess_readiness(
        lock=lock, block_attempts=[smoke_failed]
    ) == "STOP_APPARATUS_NOT_VIABLE"

    attempts = [
        _attempt(lock, block_id="smoke", attempt_class="SMOKE", sequence_index=0)
    ]
    for index, block_id in enumerate(lock["live_attempt_ids"]):
        status = "VALID" if index < 2 else "ABORTED"
        attempts.append(
            _attempt(
                lock,
                block_id=block_id,
                attempt_class="LIVE",
                sequence_index=index,
                status=status,
            )
        )
    assert reporting.assess_readiness(
        lock=lock, block_attempts=attempts
    ) == "STOP_INSUFFICIENT_VALID_BLOCKS"

    complete = _case(reporting)["block_attempts"]
    assert reporting.assess_readiness(
        lock=_case(reporting)["lock"], block_attempts=complete
    ) == "EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_review_binding",
        "duplicate_review_binding",
        "review_digest",
        "absolute_review_path",
        "package_mismatch",
        "reviewer_mismatch",
        "review_lock_digest",
        "review_rubric_digest",
        "missing_unblinding",
        "duplicate_unblinding",
    ],
)
def test_summary_rejects_inexact_review_and_unblinding_coverage(
    reporting: ModuleType,
    mutation: str,
) -> None:
    case = _case(reporting)
    if mutation == "missing_review_binding":
        case["sealed_review_bindings"].pop()
    elif mutation == "duplicate_review_binding":
        case["sealed_review_bindings"].append(case["sealed_review_bindings"][0])
    elif mutation == "review_digest":
        case["sealed_review_bindings"][0] = copy.replace(
            case["sealed_review_bindings"][0],
            review_result_digest=_digest("wrong"),
        )
    elif mutation == "absolute_review_path":
        case["sealed_review_bindings"][0] = copy.replace(
            case["sealed_review_bindings"][0],
            review_path="/reviews/record.json",
        )
    elif mutation == "package_mismatch":
        case["sealed_review_bindings"][0] = copy.replace(
            case["sealed_review_bindings"][0],
            package_id="other",
        )
    elif mutation == "reviewer_mismatch":
        case["sealed_review_bindings"][0] = copy.replace(
            case["sealed_review_bindings"][0],
            reviewer_id="reviewer-2",
        )
    elif mutation == "review_lock_digest":
        case["reviews"][0]["pilot_lock_digest"] = _digest("wrong")
        case["sealed_review_bindings"][0] = copy.replace(
            case["sealed_review_bindings"][0],
            review_result_digest=canonical_sha256(case["reviews"][0]),
        )
    elif mutation == "review_rubric_digest":
        case["reviews"][0]["rubric_digest"] = _digest("wrong")
        case["sealed_review_bindings"][0] = copy.replace(
            case["sealed_review_bindings"][0],
            review_result_digest=canonical_sha256(case["reviews"][0]),
        )
    elif mutation == "missing_unblinding":
        case["unblinding"].pop()
    else:
        case["unblinding"].append(case["unblinding"][0])

    with pytest.raises(reporting.ReportingError):
        reporting.build_pilot_summary(**case)


def test_summary_rejects_a_live_provider_session_reused_across_reviews(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    repeated_session = case["reviews"][0]["session_id"]
    case["reviews"][1]["session_id"] = repeated_session
    changed_review_id = case["reviews"][1]["review_id"]
    case["sealed_review_bindings"] = [
        copy.replace(
            binding,
            review_result_digest=canonical_sha256(
                next(
                    review
                    for review in case["reviews"]
                    if review["review_id"] == changed_review_id
                )
            ),
        )
        if binding.review_id == changed_review_id
        else binding
        for binding in case["sealed_review_bindings"]
    ]

    with pytest.raises(reporting.ReportingError, match="review_session_reused"):
        reporting.build_pilot_summary(**case)


def test_summary_rejects_any_review_binding_for_the_smoke_package(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    review = copy.deepcopy(case["reviews"][0])
    review["review_id"] = "smoke-reviewer-1"
    review["session_id"] = "session-smoke-reviewer-1"
    case["reviews"].append(review)
    case["sealed_review_bindings"].append(
        reporting.ReviewBinding(
            block_id=case["lock"]["smoke_id"],
            package_id=case["lock"]["smoke_id"],
            package_manifest_digest=_digest("smoke-package"),
            review_id=review["review_id"],
            review_result_digest=canonical_sha256(review),
            review_path="reviews/smoke-reviewer-1.json",
            reviewer_id=review["reviewer_id"],
            reviewer_role="INITIAL",
        )
    )

    with pytest.raises(reporting.ReportingError, match="review_binding_invalid"):
        reporting.build_pilot_summary(**case)


def test_material_disagreement_uses_locked_indeterminate_policy(
    reporting: ModuleType,
) -> None:
    case = _case(reporting, disagree=True)
    unresolved = reporting.build_pilot_summary(**case)

    assert unresolved["review_diagnostics"]["disagreement_count"] == 1
    assert unresolved["review_diagnostics"]["adjudication_count"] == 0
    assert _find(
        unresolved["review_diagnostics"]["blocks"], "block_id", "live-1"
    )["disagreement_disposition"] == "INDETERMINATE"
    assert "adjudicator_review_reference" not in _find(
        unresolved["review_diagnostics"]["blocks"], "block_id", "live-1"
    )


def test_unlocked_adjudicator_review_is_rejected(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    review = _review(
        case["lock"],
        block_id="live-1",
        reviewer="reviewer-3",
        outcomes=("A", "B"),
        guesses=("UNKNOWN",) * 3,
    )
    package_digest = _digest("package-live-1")
    case["reviews"].append(review)
    case["sealed_review_bindings"].append(
        reporting.ReviewBinding(
            block_id="live-1",
            package_id="live-1",
            package_manifest_digest=package_digest,
            review_id=review["review_id"],
            review_result_digest=canonical_sha256(review),
            review_path=f"reviews/{review['review_id']}.json",
            reviewer_id="reviewer-3",
            reviewer_role="ADJUDICATOR",
        )
    )

    with pytest.raises(reporting.ReportingError, match="reviewer_coverage_invalid"):
        reporting.build_pilot_summary(**case)


def test_json_and_markdown_regenerate_deterministically(
    reporting: ModuleType,
) -> None:
    first = _summary(reporting)
    second = _summary(reporting)

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert reporting.render_pilot_markdown(first) == reporting.render_pilot_markdown(
        second
    )
    assert "general effectiveness" not in reporting.render_pilot_markdown(first)


def test_exact_binomial_known_vector(reporting: ModuleType) -> None:
    assert reporting.exact_binomial_tail(
        n=10,
        successes_at_least=9,
        rate=Fraction(1, 2),
    ) == Fraction(11, 1024)


def _plan(reporting: ModuleType, **overrides: object) -> object:
    values: dict[str, object] = {
        "null_rate": Fraction(1, 2),
        "target_rate": Fraction(4, 5),
        "alpha": Fraction(1, 20),
        "power": Fraction(4, 5),
        "max_tie_rate": Fraction(1, 5),
        "accrual_probability": Fraction(9, 10),
        "max_invalid_attempts": 2,
        "max_cost_ratio": Fraction(3, 2),
        "min_calls_per_block": 7,
        "max_calls_per_block": 19,
        "search_limit": 200,
    }
    values.update(overrides)
    return reporting.plan_sample_size(**values)


def test_sample_size_plan_is_exact_minimal_and_has_no_default_ten(
    reporting: ModuleType,
) -> None:
    plan = _plan(reporting)

    assert plan.required_non_tied_comparisons != 10
    assert plan.critical_win_count <= plan.required_non_tied_comparisons
    assert plan.fixed_valid_block_cap >= plan.required_non_tied_comparisons
    assert plan.terminal_shortfall_status == "INSUFFICIENT_EVIDENCE"
    assert plan.minimum_provider_calls_at_cap == (
        plan.fixed_valid_block_cap * 7
    )
    assert plan.maximum_provider_calls_at_cap == (
        plan.fixed_valid_block_cap * 19
    )
    previous_n = plan.required_non_tied_comparisons - 1
    if previous_n > 0:
        assert not any(
            reporting.exact_binomial_tail(
                n=previous_n,
                successes_at_least=critical,
                rate=Fraction(1, 2),
            )
            <= Fraction(1, 20)
            and reporting.exact_binomial_tail(
                n=previous_n,
                successes_at_least=critical,
                rate=Fraction(4, 5),
            )
            >= Fraction(4, 5)
            for critical in range(previous_n + 1)
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_rate": Fraction(1, 2)},
        {"null_rate": Fraction(-1, 10)},
        {"target_rate": Fraction(11, 10)},
        {"alpha": Fraction(0)},
        {"alpha": Fraction(1)},
        {"power": Fraction(0)},
        {"max_tie_rate": Fraction(1)},
        {"accrual_probability": Fraction(0)},
        {"max_invalid_attempts": -1},
        {"max_cost_ratio": Fraction(0)},
        {"min_calls_per_block": 0},
        {"min_calls_per_block": 20, "max_calls_per_block": 19},
        {"search_limit": 0},
    ],
)
def test_sample_size_rejects_invalid_domains(
    reporting: ModuleType,
    overrides: dict[str, object],
) -> None:
    with pytest.raises(reporting.ReportingError):
        _plan(reporting, **overrides)


def test_sample_size_search_exhaustion_is_explicit(reporting: ModuleType) -> None:
    with pytest.raises(reporting.ReportingError, match="sample_size_search_exhausted"):
        _plan(
            reporting,
            target_rate=Fraction(51, 100),
            power=Fraction(99, 100),
            search_limit=2,
        )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0", Fraction(0)),
        ("1", Fraction(1)),
        ("12", Fraction(12)),
        ("0.05", Fraction(1, 20)),
        ("1.25", Fraction(5, 4)),
    ],
)
def test_canonical_decimal_parser_is_exact(
    reporting: ModuleType,
    text: str,
    expected: Fraction,
) -> None:
    assert reporting.parse_canonical_decimal(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", ".5", "01", "1.0", "1.", "+1", "-1", "1e-2", "nan", " 1"],
)
def test_canonical_decimal_parser_rejects_noncanonical_text(
    reporting: ModuleType,
    text: str,
) -> None:
    with pytest.raises(reporting.ReportingError, match="decimal_noncanonical"):
        reporting.parse_canonical_decimal(text)


def test_sample_size_cli_requires_every_decision_parameter(
    reporting: ModuleType,
) -> None:
    del reporting
    cli = importlib.import_module("scripts.experiments.lean_pilot")
    required = {
        "--null-rate": "0.5",
        "--target-rate": "0.8",
        "--alpha": "0.05",
        "--power": "0.8",
        "--max-tie-rate": "0.2",
        "--accrual-probability": "0.9",
        "--max-invalid-attempts": "2",
        "--max-cost-ratio": "1.5",
        "--min-calls-per-block": "7",
        "--max-calls-per-block": "19",
        "--search-limit": "200",
    }
    complete = [
        "plan-sample-size",
        *(piece for pair in required.items() for piece in pair),
    ]
    assert cli._parser().parse_args(complete).search_limit == 200
    for omitted in required:
        argv = [
            "plan-sample-size",
            *(
                piece
                for key, value in required.items()
                if key != omitted
                for piece in (key, value)
            ),
        ]
        with pytest.raises(SystemExit):
            cli._parser().parse_args(argv)


def test_sample_size_cli_prints_canonical_fixed_plan(
    reporting: ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del reporting
    cli = importlib.import_module("scripts.experiments.lean_pilot")
    result = cli.main(
        [
            "plan-sample-size",
            "--null-rate",
            "0.5",
            "--target-rate",
            "0.8",
            "--alpha",
            "0.05",
            "--power",
            "0.8",
            "--max-tie-rate",
            "0.2",
            "--accrual-probability",
            "0.9",
            "--max-invalid-attempts",
            "2",
            "--max-cost-ratio",
            "1.5",
            "--min-calls-per-block",
            "7",
            "--max-calls-per-block",
            "19",
            "--search-limit",
            "200",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert output == canonical_json_bytes(json.loads(output)).decode() + "\n"
    assert json.loads(output)["terminal_shortfall_status"] == "INSUFFICIENT_EVIDENCE"


def _write_summary_cli_case(
    reporting: ModuleType,
    tmp_path: Path,
) -> tuple[dict[str, Any], list[str]]:
    case = _case(reporting)
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    case["lock"]["evidence_root"] = evidence_root.as_posix()
    lock_digest = canonical_sha256(case["lock"])
    for attempt in case["block_attempts"]:
        attempt["pilot_lock_digest"] = lock_digest
        path = evidence_root / attempt["block_id"] / "block-attempt.json"
        path.parent.mkdir()
        path.write_bytes(canonical_json_bytes(attempt))
    reviews_by_id = {}
    for review in case["reviews"]:
        review["pilot_lock_digest"] = lock_digest
        reviews_by_id[review["review_id"]] = review
    bindings = []
    for binding in case["sealed_review_bindings"]:
        review = reviews_by_id[binding.review_id]
        updated = copy.replace(
            binding,
            review_result_digest=canonical_sha256(review),
        )
        bindings.append(updated)
        path = evidence_root.joinpath(*Path(updated.review_path).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(review))
    review_bindings = tmp_path / "review-bindings.json"
    review_bindings.write_bytes(
        canonical_json_bytes([asdict(binding) for binding in bindings])
    )
    unblinding_bindings = tmp_path / "unblinding-bindings.json"
    unblinding_bindings.write_bytes(
        canonical_json_bytes(
            [asdict(binding) for binding in case["unblinding"]]
        )
    )
    lock_path = tmp_path / "pilot-lock.json"
    lock_path.write_bytes(canonical_json_bytes(case["lock"]))
    json_output = tmp_path / "pilot-summary.json"
    markdown_output = tmp_path / "pilot-summary.md"
    argv = [
        "summarize",
        "--lock",
        str(lock_path),
        "--evidence-root",
        str(evidence_root),
        "--review-bindings",
        str(review_bindings),
        "--unblinding-bindings",
        str(unblinding_bindings),
        "--json-output",
        str(json_output),
        "--markdown-output",
        str(markdown_output),
    ]
    return case, argv


def test_summarize_cli_loads_only_explicit_bound_evidence(
    reporting: ModuleType,
    tmp_path: Path,
) -> None:
    case, argv = _write_summary_cli_case(reporting, tmp_path)
    cli = importlib.import_module("scripts.experiments.lean_pilot")

    assert cli.main(argv) == 0

    summary = json.loads((tmp_path / "pilot-summary.json").read_bytes())
    assert summary["pilot_lock_digest"] == canonical_sha256(case["lock"])
    assert summary["status"] == "EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED"
    assert (tmp_path / "pilot-summary.md").read_text(encoding="utf-8") == (
        reporting.render_pilot_markdown(summary)
    )


def test_summarize_cli_rejects_review_path_escape(
    reporting: ModuleType,
    tmp_path: Path,
) -> None:
    _case, argv = _write_summary_cli_case(reporting, tmp_path)
    bindings_path = tmp_path / "review-bindings.json"
    bindings = json.loads(bindings_path.read_bytes())
    bindings[0]["review_path"] = "../outside.json"
    bindings_path.write_bytes(canonical_json_bytes(bindings))
    cli = importlib.import_module("scripts.experiments.lean_pilot")

    with pytest.raises(reporting.ReportingError, match="review_path_invalid"):
        cli.main(argv)


def test_apparatus_stop_with_zero_valid_blocks_is_truthfully_summarized(
    reporting: ModuleType,
) -> None:
    lock = _lock()
    smoke = _attempt(
        lock,
        block_id=lock["smoke_id"],
        attempt_class="SMOKE",
        sequence_index=0,
        status="INVALID",
    )

    summary = reporting.build_pilot_summary(
        lock=lock,
        block_attempts=[smoke],
        reviews=[],
        sealed_review_bindings=[],
        unblinding=[],
    )

    assert summary["status"] == "STOP_APPARATUS_NOT_VIABLE"
    assert summary["terminal_reason_code"] == "STOP_APPARATUS_NOT_VIABLE"
    assert summary["valid_blocks"] == []
    assert all(
        statistic["viable_count"] == statistic["nonviable_count"] == 0
        for statistic in summary["treatment_statistics"]
    )
    assert all(item["value"] == "UNKNOWN" for item in summary["medians"])
    assert all(item["value"] == "UNKNOWN" for item in summary["ratios"])


def test_direct_summary_builder_rejects_any_attempt_after_third_valid(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    case["block_attempts"].append(
        _attempt(
            case["lock"],
            block_id="live-4",
            attempt_class="LIVE",
            sequence_index=3,
            status="ABORTED",
        )
    )

    with pytest.raises(reporting.ReportingError, match="attempt_after_denominator"):
        reporting.build_pilot_summary(**case)


def test_failed_smoke_rejects_live_attempts(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    case["block_attempts"][0] = _attempt(
        case["lock"],
        block_id="smoke",
        attempt_class="SMOKE",
        sequence_index=0,
        status="INVALID",
    )

    with pytest.raises(
        reporting.ReportingError,
        match="live_attempt_after_failed_smoke",
    ):
        reporting.build_pilot_summary(**case)


def test_material_disagreement_may_remain_indeterminate_without_adjudicator(
    reporting: ModuleType,
) -> None:
    case = _case(reporting, disagree=True)

    summary = reporting.build_pilot_summary(**case)

    assert summary["review_diagnostics"]["disagreement_count"] == 1
    assert summary["review_diagnostics"]["adjudication_count"] == 0
    diagnostic = _find(
        summary["review_diagnostics"]["blocks"], "block_id", "live-1"
    )
    assert diagnostic["disagreement_disposition"] == "INDETERMINATE"
    assert "adjudicator_review_reference" not in diagnostic
    block = _find(summary["valid_blocks"], "block_id", "live-1")
    direct_orc = _find(
        block["method_outcomes"], "comparison", "DIRECT_VS_ORC"
    )
    assert direct_orc["method_outcome"] == "INDETERMINATE"
    assert len(direct_orc["product_quality_review"]["review_result_digests"]) == 2


def test_unblinding_must_match_controller_owned_attempt_assignment(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    direct = next(
        binding
        for binding in case["unblinding"]
        if binding.block_id == "live-1" and binding.treatment_id == "DIRECT"
    )
    orc = next(
        binding
        for binding in case["unblinding"]
        if binding.block_id == "live-1" and binding.treatment_id == "ORC"
    )
    case["unblinding"] = [
        (
            copy.replace(binding, treatment_id="ORC")
            if binding is direct
            else copy.replace(binding, treatment_id="DIRECT")
            if binding is orc
            else binding
        )
        for binding in case["unblinding"]
    ]

    with pytest.raises(
        reporting.ReportingError,
        match="unblinding_attempt_mismatch",
    ):
        reporting.build_pilot_summary(**case)


def test_summary_reports_token_usage_and_observed_hard_contract_dispositions(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    executions = case["block_attempts"][1]["treatment_executions"]
    direct = next(item for item in executions if item["treatment_id"] == "DIRECT")
    orc = next(item for item in executions if item["treatment_id"] == "ORC")
    direct["token_counts"] = "UNKNOWN"
    orc["lifecycle_outcome"] = "PROTOCOL_FAILURE"

    summary = reporting.build_pilot_summary(**case)

    medians = {
        (item["metric"], item["treatment_id"]): item["value"]
        for item in summary["medians"]
    }
    ratios = {
        (item["metric"], item["denominator_treatment_id"]): item["value"]
        for item in summary["ratios"]
    }
    assert medians[("input_tokens", "DIRECT")] == "UNKNOWN"
    assert medians[("output_tokens", "ORC")] == {
        "numerator": 5,
        "denominator": 1,
    }
    assert ratios[("input_tokens", "DIRECT")] == "UNKNOWN"
    assert summary["hard_contract_findings"] == [
        {
            "block_id": "live-1",
            "treatment_id": "ORC",
            "finding_class": "PROTOCOL_FAILURE",
            "disposition": "TREATMENT_OUTCOME_RETAINED",
            "evidence_references": orc["evidence_references"],
        }
    ]


def test_execution_cost_currency_must_match_lock(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    case["block_attempts"][1]["treatment_executions"][0]["cost"][
        "currency"
    ] = "EUR"

    with pytest.raises(reporting.ReportingError, match="cost_currency_mismatch"):
        reporting.build_pilot_summary(**case)


def test_nonviable_product_quality_requires_two_frozen_products(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    executions = case["block_attempts"][1]["treatment_executions"]
    for treatment in ("DIRECT", "ORC"):
        execution = next(
            item for item in executions if item["treatment_id"] == treatment
        )
        execution["lifecycle_outcome"] = "CHECK_FAILURE"
    direct = next(item for item in executions if item["treatment_id"] == "DIRECT")
    direct["product_frozen"] = False
    direct.pop("product_manifest_digest")

    with pytest.raises(
        reporting.ReportingError,
        match="review_outcome_unreviewable",
    ):
        reporting.build_pilot_summary(**case)


def test_two_reviewable_nonviable_products_require_pairwise_outcome(
    reporting: ModuleType,
) -> None:
    case = _case(reporting)
    for treatment in ("DIRECT", "ORC"):
        execution = next(
            item
            for item in case["block_attempts"][1]["treatment_executions"]
            if item["treatment_id"] == treatment
        )
        execution["lifecycle_outcome"] = "CHECK_FAILURE"
        assert execution["product_frozen"] is True
    direct_label = _label_mapping(case["lock"], "live-1")["DIRECT"]
    orc_label = _label_mapping(case["lock"], "live-1")["ORC"]
    for review in case["reviews"]:
        if not review["review_id"].startswith("live-1-"):
            continue
        review["pairwise_results"] = [
            result
            for result in review["pairwise_results"]
            if {
                result["candidate_a_label"],
                result["candidate_b_label"],
            }
            != {direct_label, orc_label}
        ]
    case["sealed_review_bindings"] = [
        copy.replace(
            binding,
            review_result_digest=canonical_sha256(
                next(
                    review
                    for review in case["reviews"]
                    if review["review_id"] == binding.review_id
                )
            ),
        )
        if binding.block_id == "live-1"
        else binding
        for binding in case["sealed_review_bindings"]
    ]

    with pytest.raises(reporting.ReportingError, match="review_outcome_missing"):
        reporting.build_pilot_summary(**case)


def test_markdown_renders_every_substantive_typed_summary_surface(
    reporting: ModuleType,
) -> None:
    case = _case(reporting, disagree=True)
    orc = next(
        execution
        for execution in case["block_attempts"][1]["treatment_executions"]
        if execution["treatment_id"] == "ORC"
    )
    orc["lifecycle_outcome"] = "PROTOCOL_FAILURE"
    summary = reporting.build_pilot_summary(**case)
    markdown = reporting.render_pilot_markdown(summary)

    for heading in (
        "## Valid Block Outcomes",
        "## Excluded Attempts",
        "## Comparison Counts",
        "## Treatment Statistics",
        "## Review Diagnostics",
        "## Hard-Contract Findings",
        "## Exact Metrics",
    ):
        assert heading in markdown
    assert "input_tokens" in markdown
    assert "guess accuracy" in markdown.lower()
    first_diagnostic = summary["review_diagnostics"]["blocks"][0]
    first_initial = first_diagnostic["initial_review_references"][0]
    reviewed_quality = summary["valid_blocks"][1]["method_outcomes"][0][
        "product_quality_review"
    ]
    sentinels = (
        first_diagnostic["package_id"],
        first_diagnostic["package_manifest_digest"],
        first_initial["review_id"],
        first_initial["reviewer_id"],
        first_initial["review_result_digest"],
        first_initial["review_path"],
        reviewed_quality["review_result_digests"][0],
        orc["evidence_references"][0],
        "PROTOCOL_FAILURE=1",
        "DIRECT -> DIRECT",
    )
    assert all(str(sentinel) in markdown for sentinel in sentinels)

    lock = _lock()
    smoke = _attempt(
        lock,
        block_id="smoke",
        attempt_class="SMOKE",
        sequence_index=0,
        status="INVALID",
    )
    stop = reporting.build_pilot_summary(
        lock=lock,
        block_attempts=[smoke],
        reviews=[],
        sealed_review_bindings=[],
        unblinding=[],
    )
    stop_markdown = reporting.render_pilot_markdown(stop)
    assert "Terminal reason: `STOP_APPARATUS_NOT_VIABLE`" in stop_markdown


def test_attempt_loader_rejects_symlinked_record(
    reporting: ModuleType,
    tmp_path: Path,
) -> None:
    lock = _lock()
    lock["evidence_root"] = tmp_path.as_posix()
    smoke = _attempt(
        lock,
        block_id="smoke",
        attempt_class="SMOKE",
        sequence_index=0,
    )
    smoke_path = tmp_path / "smoke" / "block-attempt.json"
    smoke_path.parent.mkdir()
    smoke_path.write_bytes(canonical_json_bytes(smoke))
    outside = tmp_path / "outside.json"
    live = _attempt(
        lock,
        block_id="live-1",
        attempt_class="LIVE",
        sequence_index=0,
    )
    outside.write_bytes(canonical_json_bytes(live))
    live_path = tmp_path / "live-1" / "block-attempt.json"
    live_path.parent.mkdir()
    live_path.symlink_to(outside)

    with pytest.raises(reporting.ReportingError, match="live_attempt_invalid"):
        reporting.load_attempt_records(lock=lock, evidence_root=tmp_path)


@pytest.mark.parametrize("node_kind", ["directory", "fifo"])
def test_attempt_loader_rejects_nonregular_record_nodes(
    reporting: ModuleType,
    tmp_path: Path,
    node_kind: str,
) -> None:
    lock = _lock()
    lock["evidence_root"] = tmp_path.as_posix()
    smoke = _attempt(
        lock,
        block_id="smoke",
        attempt_class="SMOKE",
        sequence_index=0,
    )
    smoke_path = tmp_path / "smoke" / "block-attempt.json"
    smoke_path.parent.mkdir()
    smoke_path.write_bytes(canonical_json_bytes(smoke))
    live_path = tmp_path / "live-1" / "block-attempt.json"
    live_path.parent.mkdir()
    if node_kind == "directory":
        live_path.mkdir()
    else:
        os.mkfifo(live_path)

    with pytest.raises(reporting.ReportingError, match="live_attempt_invalid"):
        reporting.load_attempt_records(lock=lock, evidence_root=tmp_path)


def test_summarize_cli_refuses_existing_or_overlapping_outputs(
    reporting: ModuleType,
    tmp_path: Path,
) -> None:
    _case_value, argv = _write_summary_cli_case(reporting, tmp_path)
    cli = importlib.import_module("scripts.experiments.lean_pilot")
    json_output = tmp_path / "pilot-summary.json"
    json_output.write_text("existing", encoding="utf-8")

    with pytest.raises(reporting.ReportingError, match="summary_output_exists"):
        cli.main(argv)
    assert json_output.read_text(encoding="utf-8") == "existing"

    json_output.unlink()
    overlap = tmp_path / "evidence" / "summary.json"
    argv[argv.index(str(json_output))] = str(overlap)
    with pytest.raises(reporting.ReportingError, match="summary_output_overlap"):
        cli.main(argv)
    assert not overlap.exists()


def test_summarize_cli_requires_distinct_canonical_nonsymlink_outputs(
    reporting: ModuleType,
    tmp_path: Path,
) -> None:
    _case_value, argv = _write_summary_cli_case(reporting, tmp_path)
    cli = importlib.import_module("scripts.experiments.lean_pilot")
    json_index = argv.index(str(tmp_path / "pilot-summary.json"))
    markdown_index = argv.index(str(tmp_path / "pilot-summary.md"))
    argv[markdown_index] = argv[json_index]
    with pytest.raises(reporting.ReportingError, match="summary_output_overlap"):
        cli.main(argv)

    case_root = tmp_path / "symlink-case"
    case_root.mkdir()
    _case_value, argv = _write_summary_cli_case(reporting, case_root)
    destination = case_root / "elsewhere.json"
    destination.write_text("preserve", encoding="utf-8")
    json_output = case_root / "pilot-summary.json"
    json_output.symlink_to(destination)
    with pytest.raises(reporting.ReportingError, match="summary_output"):
        cli.main(argv)
    assert destination.read_text(encoding="utf-8") == "preserve"


def test_atomic_summary_publication_leaves_no_partial_target(
    reporting: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del reporting
    cli = importlib.import_module("scripts.experiments.lean_pilot")
    output = tmp_path / "summary.json"

    def fail_link(_source: Path, _destination: Path) -> None:
        raise OSError("injected publication failure")

    monkeypatch.setattr(cli.os, "link", fail_link)
    with pytest.raises(cli.ReportingError, match="summary_output_invalid"):
        cli._publish_new_file(output, b"complete-payload")

    assert not output.exists()
    assert list(tmp_path.iterdir()) == []
