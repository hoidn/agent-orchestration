Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read `project_brief`, `roadmap_change_request`, `updated_project_roadmap`, and `updated_tranche_manifest` before acting.

Review whether the roadmap revision addresses the requested program-level issue while preserving unaffected work. Use `APPROVE` when the revised roadmap and manifest are coherent, `REVISE` when the revision is fixable, and `BLOCK` when the request cannot be safely resolved from the available authority.

For the output contract's `roadmap_revision_report_path`, read the path recorded in that file and write a JSON review report to that current-checkout-relative path. Leave the pointer file containing only the path.
Write `APPROVE`, `REVISE`, or `BLOCK` to the `roadmap_revision_decision` path specified in the Output Contract.
