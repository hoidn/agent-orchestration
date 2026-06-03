Take the role of a principal engineer with strong PL, compiler, and agentic
workflow architecture judgment.

Review the three design docs from the points of view of both
consistency/correctness and soundness of the architectural direction. The
designs may be considered implementation-ready only if they improve the
language's ergonomics and the long-term maintainability, extensibility, and
internal architecture of the implementation.

Read the target docs from the provided input paths:

- Workflow Lisp review/revise stdlib integration with parametric constraints.
- Workflow Lisp structural parametric constraints.
- Workflow Lisp compile-time parametric specialization.

Also read the provided checks report if present. Treat structured inputs and
artifact paths as authority; do not infer success from prose summaries alone.

Decide:

- APPROVE when the docs are mutually consistent, technically sound, and ready
  to guide implementation.
- REVISE when specific doc edits are required before implementation should
  proceed.
- BLOCKED only when the review cannot be completed from the available material
  or a prerequisite decision outside the docs is required.

For REVISE or BLOCKED, make findings concrete enough for a reviser to act
without another clarification pass.

The structured findings carrier must use the exact schema expected by the
workflow. Use `schema_version` exactly `ReviewFindings.v1`. The referenced
findings JSON artifact must be an object with a top-level `items` array. Do not
write `review_findings.v1`, `review-findings-v1`, or a top-level `findings`
array.
