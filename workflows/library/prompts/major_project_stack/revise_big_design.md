Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `tranche_brief`, `project_brief`, `project_roadmap`, `tranche_manifest`, `design`, `design_review_report`, and `open_findings` artifacts before acting.

Revise only the selected tranche design to address unresolved in-scope findings.

Do not implement the tranche, edit source files, edit tests, edit the project roadmap, or write the implementation plan.

Preserve the project roadmap unless the review finding identifies a necessary conflict. If the design must deviate from the roadmap, make the conflict explicit in the design and explain what upstream roadmap update is needed.

Keep resolved decisions stable. Reconcile carried-forward findings by either fixing them in the design or clearly explaining why they are no longer applicable.

For the output contract's `design_path`, read the path recorded in that pointer file and write the revised design document there. Leave the pointer file as a path-only file.
