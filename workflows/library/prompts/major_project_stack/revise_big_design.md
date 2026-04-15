Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `tranche_brief`, `project_brief`, `project_roadmap`, `tranche_manifest`, `design`, `design_review_report`, and `open_findings` artifacts before acting.

Revise only the selected tranche design to address unresolved in-scope findings.

Do not implement the tranche, edit source files, edit tests, edit the project roadmap, or write the implementation plan.

Preserve the project roadmap unless the review finding identifies a necessary conflict. If the design must deviate from the roadmap, make the conflict explicit in the design and explain what upstream roadmap update is needed.

Keep resolved decisions stable. Reconcile carried-forward findings by either fixing them in the design or clearly explaining why they are no longer applicable.

If the tranche creates generated artifacts, helper scripts, validators, or curated data, ensure the revised design identifies which artifacts are maintained versus generated, the ownership/provenance assumptions, validation responsibility, and any stable paths or interfaces that are part of the tranche contract. Leave internal file layout and exact commands to the plan unless a concrete path or command is part of the contract. Justify any large hand-curated data stored inside executable code.

If the tranche introduces or changes a nontrivial subsystem, workflow, integration surface, automation, or durable artifact contract, ensure the revised design includes an architecture section that defines component boundaries, interfaces, invariants, failure modes, stable decisions downstream work may rely on without over-specifying plan-level mechanics, and test or review boundaries.

For the output contract's `design_path`, read the path recorded in that pointer file and write the revised design document there. Leave the pointer file as a path-only file.
