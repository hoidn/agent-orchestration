# Revision Study Workflow Draft Implementation Plan

Goal: Add a reusable design-plan-implementation workflow for paper revision studies where the initial seed is a human-authored revision design document.

Approach:
- Add a call-based workflow stack under `workflows/library/` so it can be invoked from another repository without `../library` import traversal.
- Keep the revision design seed read-only and publish a derived approved design under `artifacts/revision_studies/...`.
- Add revision-study-specific prompt assets under `workflows/library/prompts/revision_study_stack/`.
- Validate with dry-run checks from both this repo and `/home/ollie/Documents/ptychopinnpaper2`.

Files:
- Create `workflows/library/revision_study_design_plan_impl_stack.yaml`.
- Create `workflows/library/revision_study_design_phase.yaml`.
- Create `workflows/library/revision_study_plan_phase.yaml`.
- Create `workflows/library/revision_study_implementation_phase.yaml`.
- Create prompt files under `workflows/library/prompts/revision_study_stack/`.
- Update `workflows/README.md` and `prompts/README.md` if the draft validates.

Verification:
- Run a dry-run from `/home/ollie/Documents/agent-orchestration`.
- Run a dry-run from `/home/ollie/Documents/ptychopinnpaper2` against the external workflow path, using `revision_designs/fig5_ood_metrics_low_frequency_phase.md` as input.
- Run a prompt path existence check with `rg` or a short YAML parser if dry-run exposes path issues.
