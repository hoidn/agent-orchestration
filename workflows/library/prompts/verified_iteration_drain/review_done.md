Judge whether the consumed target design's acceptance criteria hold in the
current checkout.

Read the target design and verify each acceptance criterion directly against
the repository, running commands where a criterion is runnable. The ledger
and prior reports are context, not evidence.

Write `APPROVE` or `REJECT` to the file named by `done_review_decision_path`
in the consumed work order. When rejecting, append each unmet criterion and
the evidence for it to the file named by `review_findings_path`.
