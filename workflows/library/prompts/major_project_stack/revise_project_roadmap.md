Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `project_brief`, `project_roadmap`, `tranche_manifest`, `roadmap_review_report`, and `open_findings` artifacts before acting.

Revise the project roadmap and tranche manifest to address unresolved in-scope findings.

Do not implement source changes, edit the broad project brief, or draft full designs or implementation plans for every tranche.

Keep the broad project brief immutable provenance. Preserve correct roadmap decisions that were not challenged. Update tranche ordering, prerequisites, generated tranche briefs, and manifest fields only where the review findings require it or where a directly related consistency fix is necessary.

If review findings concern a mismatch between the outcome requested by the brief and the roadmap's tranche scope, revise the roadmap to distinguish foundation or selected-subset work from acceptance-ready work. Add or repair user-workflow, system, integration, consumer, or other end-to-end acceptance gates; later tranches; deferred-work owners; return conditions; generated tranche briefs; and manifest consistency as needed.

If review findings concern repeated tranche shapes, cross-tranche family relationships, pilot/consolidation timing, or reuse boundaries, update the roadmap, generated tranche briefs, and manifest consistency as needed. Treat family relationships as roadmap hypotheses and checkpoints, not as implementation plans. Do not hardcode shared helpers unless the roadmap review specifically requires a prerequisite consolidation tranche.

When changing the manifest, keep it valid JSON and preserve the required field set for every tranche:
- `tranche_id`
- `title`
- `brief_path`
- `design_target_path`
- `design_review_report_target_path`
- `plan_target_path`
- `plan_review_report_target_path`
- `execution_report_target_path`
- `implementation_review_report_target_path`
- `item_summary_target_path`
- `prerequisites`
- `status`
- `design_depth`
- `completion_gate`

Use only the first-driver manifest values accepted by the deterministic validator: `status` may be `pending`, `blocked`, `done`, `completed`, or `approved`; `design_depth` may be `big` or `standard`; `completion_gate` must be `implementation_approved`.

For output contract relpath artifacts, read each recorded path from the pointer file and write the rich content to that target path. Leave pointer files as path-only files.
