"""Private deterministic Markdown rendering for pilot summaries."""

from __future__ import annotations

from collections.abc import Mapping

from ._reporting_validation import _validate_record


def render_pilot_markdown(summary: Mapping[str, object]) -> str:
    """Render a deterministic, deliberately claim-bounded Markdown view."""

    _validate_record(dict(summary), "pilot_summary.v1")

    def render_value(value: object) -> str:
        if value == "UNKNOWN":
            return "UNKNOWN"
        return f"{value['numerator']}/{value['denominator']}"  # type: ignore[index]

    lines = [
        "# Lean Pilot Evidence Summary",
        "",
        f"- Record kind: `{summary['record_kind']}`",
        f"- Summary ID: `{summary['summary_id']}`",
        f"- Pilot lock digest: `{summary['pilot_lock_digest']}`",
        f"- Status: `{summary['status']}`",
        f"- Valid blocks: {len(summary['valid_blocks'])}",  # type: ignore[arg-type]
        f"- Excluded attempts: {len(summary['excluded_block_references'])}",  # type: ignore[arg-type]
    ]
    if "terminal_reason_code" in summary:
        lines.append(f"- Terminal reason: `{summary['terminal_reason_code']}`")
    lines.extend(["", "## Valid Block Outcomes", ""])
    if not summary["valid_blocks"]:
        lines.append("- None.")
    for block in summary["valid_blocks"]:  # type: ignore[index]
        lines.append(f"- `{block['block_id']}` (`{block['block_attempt_digest']}`)")
        for outcome in block["method_outcomes"]:
            quality = outcome["product_quality_review"]
            quality_text = (
                quality
                if isinstance(quality, str)
                else (
                    f"{quality['outcome']}; review digests="
                    + ", ".join(quality["review_result_digests"])
                )
            )
            lines.append(
                f"  - {outcome['comparison']}: {outcome['method_outcome']} "
                f"({outcome['viability_case']}; quality={quality_text})"
            )
    lines.extend(["", "## Excluded Attempts", ""])
    if not summary["excluded_block_references"]:
        lines.append("- None.")
    for block in summary["excluded_block_references"]:  # type: ignore[index]
        lines.append(
            f"- `{block['block_id']}`: {block['status']} "
            f"(`{block['block_attempt_digest']}`)"
        )
    lines.extend(["", "## Comparison Counts", ""])
    for count in summary["comparison_counts"]:  # type: ignore[index]
        lines.append(
            f"- {count['comparison']}: A={count['a_win_count']}, "
            f"B={count['b_win_count']}, ties={count['tie_count']}, "
            f"indeterminate={count['indeterminate_count']}, "
            f"nonviable ties={count['tie_nonviable_count']}"
        )
    lines.extend(["", "## Treatment Statistics", ""])
    for statistic in summary["treatment_statistics"]:  # type: ignore[index]
        lifecycle = ", ".join(
            f"{key}={statistic['lifecycle_outcome_counts'][key]}"
            for key in sorted(statistic["lifecycle_outcome_counts"])
        )
        failures = ", ".join(
            f"{key}={statistic['failure_class_counts'][key]}"
            for key in sorted(statistic["failure_class_counts"])
        )
        lines.append(
            f"- {statistic['treatment_id']}: viable={statistic['viable_count']}, "
            f"nonviable={statistic['nonviable_count']}, "
            f"provider calls={statistic['provider_call_counts']}"
        )
        lines.append(f"  - Lifecycle outcomes: {lifecycle}")
        lines.append(f"  - Failure classes: {failures}")
    diagnostics = summary["review_diagnostics"]  # type: ignore[index]
    lines.extend(
        [
            "",
            "## Review Diagnostics",
            "",
            f"- Agreement count: {diagnostics['agreement_count']}",
            f"- Disagreement count: {diagnostics['disagreement_count']}",
            f"- Adjudication count: {diagnostics['adjudication_count']}",
            f"- Guess accuracy: {render_value(diagnostics['guess_accuracy'])}",
        ]
    )
    for block in diagnostics["blocks"]:
        lines.append(
            f"- `{block['block_id']}`: package `{block['package_id']}` "
            f"(`{block['package_manifest_digest']}`); "
            f"initial reviews agree={block['initial_reviews_agree']}; "
            f"disposition={block['disagreement_disposition']}"
        )
        for reference in block["initial_review_references"]:
            lines.append(
                f"  - Initial review `{reference['review_id']}` by "
                f"`{reference['reviewer_id']}`: "
                f"`{reference['review_result_digest']}` at "
                f"`{reference['review_path']}`"
            )
        if "adjudicator_review_reference" in block:
            reference = block["adjudicator_review_reference"]
            lines.append(
                f"  - Adjudicator review `{reference['review_id']}` by "
                f"`{reference['reviewer_id']}`: "
                f"`{reference['review_result_digest']}` at "
                f"`{reference['review_path']}`"
            )
    lines.append("- Guess confusion:")
    for cell in diagnostics["guess_confusion"]:
        lines.append(
            f"  - {cell['actual_treatment_id']} -> "
            f"{cell['guessed_treatment_id']}: {cell['count']}"
        )
    lines.extend(["", "## Hard-Contract Findings", ""])
    if not summary["hard_contract_findings"]:
        lines.append("- None recorded.")
    for finding in summary["hard_contract_findings"]:  # type: ignore[index]
        lines.append(
            f"- `{finding['block_id']}` / {finding['treatment_id']}: "
            f"{finding['finding_class']} -> {finding['disposition']}"
        )
        for reference in finding["evidence_references"]:
            lines.append(f"  - Evidence: `{reference}`")
    lines.extend(["", "## Exact Metrics", ""])
    for median in summary["medians"]:  # type: ignore[index]
        lines.append(
            f"- Median {median['metric']} / {median['treatment_id']}: "
            f"{render_value(median['value'])}"
        )
    for ratio in summary["ratios"]:  # type: ignore[index]
        lines.append(
            f"- Ratio {ratio['metric']} / "
            f"{ratio['numerator_treatment_id']}:{ratio['denominator_treatment_id']}: "
            f"{render_value(ratio['value'])}"
        )
    lines.extend(
        [
            "",
            "This report is exploratory controlled-task evidence only.",
            "",
        ]
    )
    return "\n".join(lines)
