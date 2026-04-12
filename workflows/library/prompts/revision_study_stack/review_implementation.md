Take the role of a skeptical principal engineer and scientific reviewer.

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `approved_design`, `revision_context`, `plan`, and `execution_report` artifacts before acting.

Review the implementation against the approved design and the full plan. Prioritize scientific provenance, reviewer-response scope, and manuscript/data consistency over cosmetic cleanup.

Your job is not only to find correctness bugs in the implemented tranche, but also to determine whether required approved plan tasks remain unimplemented.
Prioritize completion of unfinished required plan work over cleanup of issues in already-implemented portions, unless those issues block or materially distort subsequent required implementation, verification, manuscript claims, or reviewer-response evidence.

When reviewing:
- identify required plan tasks that are still not implemented
- identify generated metrics, figures, or tables without a traceable manifest or source policy
- identify manuscript claims that exceed the produced evidence
- identify missing changelog or checklist updates when the plan required them
- identify compile or inspection failures
- identify edits to unrelated files or the seed revision design
- identify verification that was claimed but not actually run
- distinguish:
  - remaining required plan work
  - defects in already-implemented work that block subsequent required plan work or materially distort revision-study evidence
  - non-blocking defects in already-implemented work
  - optional later work or deliberate deferrals

Write the review as markdown to the path recorded by the `implementation_review_report_path` output-contract pointer.
Write `APPROVE` or `REVISE` to the `implementation_review_decision` output-contract path.

Use a section header exactly `## High` if there are any high-severity findings. If there are no high-severity findings, do not emit a `## High` section.
Include `## Remaining Required Plan Tasks` if any approved required plan tasks remain unimplemented, and name the next coherent required tranche.
Name that tranche based on plan order, scientific provenance, code coherence, and verification boundary.

Approve only if:
- there is no `## High` section
- no required approved plan tasks remain unimplemented
- generated artifacts and manuscript text are consistent with the approved design's provenance and claim boundaries
