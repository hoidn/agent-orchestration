Review the Lisp frontend implementation against the approved plan and consumed
design docs.

In the verification section, note whether relevant project-native lint/static
checks were run. Distinguish correctness-relevant findings from pre-existing or
cleanup-only lint noise.

If you approve the implementation, stage and commit only the changes that belong
to this approved implementation before writing `APPROVE`. Leave unrelated
pre-existing changes unstaged, and record the commit hash in the review report.

Write the review report to the relpath recorded in
`implementation_review_report_path.txt` and write `APPROVE` or `REVISE` to
`implementation_review_decision.txt`.
