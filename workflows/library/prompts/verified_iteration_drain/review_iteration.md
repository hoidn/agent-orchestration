Review one iteration of work toward the consumed target design.

Read the consumed review package (commit list and diff), the target design,
and the ledger.

Approve only if the diff is correct, conforms to the target design, and does
not weaken verification: deleted or loosened checks and tests require
justification visible in the diff itself. Judge the outcome, not the
process; how the work was planned is not review scope.

Return `APPROVE` or `FINDINGS` as the typed provider result, and write the same
value to the compatibility file named by `review_decision_path` in the consumed
work order. When returning `FINDINGS`, write the concrete
findings to the file named by `review_findings_path`.
