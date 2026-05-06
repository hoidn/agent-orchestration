# Major-Project Review Path Ownership Fix Plan

Goal: remove provider-owned review-report pointer mutation from the major-project roadmap and big-design review phases so a malformed relpath cannot turn an ordinary `REVISE` cycle into a hard workflow failure.

Scope:
- `workflows/library/tracked_big_design_phase.yaml`
- `workflows/library/major_project_roadmap_phase.yaml`
- `workflows/library/prompts/major_project_stack/review_big_design.md`
- `workflows/library/prompts/major_project_stack/review_project_roadmap.md`
- `tests/test_major_project_workflows.py`

Plan:
1. Add failing runtime regression coverage for a provider that corrupts the review-report pointer file while still writing a valid review artifact to the canonical target path.
2. Change the review prompts to consume concrete target-path guidance rather than pointer-file guidance.
3. Add deterministic post-review publication steps in the roadmap and big-design phases that:
   - reassert the canonical review-report pointer from workflow inputs
   - validate the canonical review artifact exists and is parseable JSON
   - publish the review artifact and decision/count outputs for downstream routing
4. Route review decisions from the deterministic publication step instead of directly from the provider step.
5. Run the narrow major-project workflow tests and an orchestrator dry-run smoke check.
