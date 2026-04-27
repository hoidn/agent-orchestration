Major-project escalation additions:
- Read the consumed `upstream_escalation_context` artifact and preserve its downstream evidence while revising.
- If the review evidence shows the current tranche cannot be repaired locally, say so plainly rather than papering over it.

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `tranche_brief`, `project_brief`, `project_roadmap`, `tranche_manifest`, `design`, `design_review_report`, and `open_findings` artifacts before acting.

Revise only the selected tranche design to address unresolved in-scope findings.

Do not implement the tranche, edit source files, edit tests, edit the project roadmap, or write the implementation plan.

Preserve the project roadmap unless the review finding identifies a necessary conflict. If the design must deviate from the roadmap, make the conflict explicit in the design and explain what upstream roadmap update is needed.

If review findings concern cross-tranche family fit, repeated work shapes, reuse boundaries, or prior-tranche refactoring, revise the selected design to make that decision explicit. The design may propose refactoring prior tranche-local work into shared helpers when the current tranche needs it, but it must preserve prior behavior and interfaces and require regression checks for that behavior.

Keep resolved decisions stable. Reconcile carried-forward findings by either fixing them in the design or clearly explaining why they are no longer applicable.

If the tranche creates or materially changes production code, stable APIs, maintained data or contracts, or externally consumed persistent artifacts, ensure the revised design identifies the stable locations, interfaces, provenance assumptions, and checks that belong in the tranche contract. Distinguish authored from derived outputs when both exist. Generated reports, projections, summaries, and review evidence are derived by default, not tranche-contract surfaces, unless a downstream consumer, external user, or stable gate depends on them directly. Define layout at the level needed to fix component ownership and stable locations; leave complete file lists, function-level structure, exact commands, and incidental generated outputs to the plan unless they are part of the contract. Justify any large hand-curated data stored inside executable code.

If the tranche introduces or changes a nontrivial subsystem, workflow, integration surface, automation, or stable consumed contract, ensure the revised design includes an architecture section that defines component boundaries, interfaces, invariants, failure modes, stable decisions downstream work may rely on without over-specifying plan-level mechanics, and test or review boundaries.

For the output contract's `design_path`, read the path recorded in that pointer file and write the revised design document there. Leave the pointer file as a path-only file.
