## 2026-06-30 lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery

- Prompt file: `workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md`
- Observed bad behavior: During run `20260630T182211Z-vbqa3m`, the Codex provider for `ClassifyBlockedImplementationRecovery` printed the correct JSON classification to stdout but did not write the required runtime-owned bundle file `state/workflow_lisp/calls/20260630T182211Z-vbqa3m/root.drain_lisp_frontend_work_1.lisp_frontend_drain_iteration.run_recovered_blocked_06c67b9a7bb4/lisp-frontend-design-delta-work-item-v214/de14bca20ef59f36.json/blocked-implementation-recovery.json`. The captured stderr shows it instead used `apply_patch` to create a sibling artifact at `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/drain/iterations/1/blocked-recovery-decision.json`.
- Root cause in prompt text: The prompt tells the provider to "Write one JSON bundle at the required output path" but does not explicitly require writing `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, forbid alternate artifact writes, or forbid workspace edits/tool use unrelated to that runtime-owned bundle.
- Proposed edit: Strengthen the prompt so it explicitly says to write exactly one JSON bundle to `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` when present, not to use `apply_patch` or create any other file, not to print substitute JSON to stdout as the result channel, and not to modify unrelated workspace files.
- Expected behavior change: The provider should either write the required bundle file or fail loudly, instead of mutating the workspace and leaving the runtime-owned bundle missing.
- Risk / tradeoff: Tighter prompt wording may reduce flexibility for Codex-authored summaries or conflict with other prompt families that currently rely on prose closeout after writing a bundle, so the wording should be reviewed before reuse elsewhere.

## 2026-07-01 lisp_frontend_design_delta_implementation_phase/review_implementation

- Prompt file: `workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/review_implementation.md`
- Observed bad behavior: During run `20260701T074952Z-r9irix`, implementation review correctly found a scoped selector-contract bug, then started blocking on unrelated transition-authoring failures in files last modified before the run started. The subsequent fix agent began debugging `work_item.orc` / transition provenance instead of staying on the selected selector-blocked carrier gap.
- Root cause in prompt text: The prompt says to distinguish pre-existing noise in verification, but it does not tell the reviewer to classify dirty-worktree failures outside the claimed/current scope as pre-existing drift unless the implementation report claims them, the plan assigns them, or the delivered behavior depends on them.
- Proposed edit: Add one sentence near the existing pre-existing-noise rule: "Do not block approval on failures caused only by pre-existing dirty-worktree changes outside the claimed/current implementation scope; record them as follow-up or pre-existing drift unless the delivered behavior depends on them."
- Expected behavior change: Review still rejects real current-scope bugs, but stops sending fix agents into unrelated dirty files from previous workflow slices.
- Risk / tradeoff: If an implementation silently relies on pre-existing dirty changes, the reviewer must still block; the wording needs to preserve that dependency exception.

## 2026-07-01 lisp_frontend_design_delta_plan_phase/review_plan

- Prompt file: `workflows/library/prompts/lisp_frontend_design_delta_plan_phase/review_plan.md`
- Observed bad behavior: During run `20260701T120603Z-x9a4dj`, plan review repeatedly rejected `workflow-lisp-design-delta-compatibility-carrier-retirement` by adding broader report/census/parity/stdlib verification selectors from generated `check_commands` and recovered context. The plan revisions increasingly focused on proving checked diagnostic artifacts rather than narrowing the implementation to the actual carrier-retirement behavior.
- Root cause in prompt text: The review prompt asks for plan correctness against the target, architecture, and work-item context, but does not tell the reviewer that generated check lists and diagnostic-report expectations are advisory unless they directly cover files/contracts the plan changes.
- Proposed edit: Add one short rule: "Treat generated check lists and diagnostic-report expectations as candidate checks, not fixed scope. Require them only when they directly exercise a file, public contract, or runtime behavior the plan changes; otherwise record them as optional follow-up."
- Expected behavior change: Plan review should still reject plans that miss checks for changed behavior, but should stop expanding bounded implementation slices into report/census/manifest refresh work.
- Risk / tradeoff: A reviewer could under-require broad regression checks for genuinely shared changes. Mitigate by keeping the direct dependency clause: shared files/contracts changed by the plan still require focused shared checks.

## 2026-07-01 lisp_frontend_selector/select_next_design_delta_work

- Prompt file: `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`
- Observed bad behavior: During run `20260701T134905Z-ia7ro7`, the selector saw a manifest with four eligible design gaps, reasoned only from "no eligible backlog items," inspected older run-state/design-gap files, and selected hidden work not present in the manifest. The deterministic publisher correctly rejected the selected `design_gap_id` as ineligible.
- Root cause in prompt text: The opening instruction says to read "active backlog items, and design-gap work graph," which leaves the provider free to treat historical run-state/design-gap directories as the selectable graph instead of treating the consumed selector manifest as the selectable existing work surface.
- Proposed edit: Replace that opening sentence with: "Read the consumed steering, target design, and selector manifest before acting. Existing selectable work is limited to rows in the manifest; use target-design reasoning only to propose a genuinely new bounded gap when no manifest row is the right next task."
- Expected behavior change: The selector should choose from `manifest.items` / `manifest.design_gaps` when existing eligible work is available, while still allowing new target-design gap discovery when the manifest lacks the right work.
- Risk / tradeoff: This reduces the selector's ability to recover from a bad manifest by searching historical artifacts. That is intentional; manifest construction and recovery routing should be deterministic workflow mechanics, not provider improvisation.

## 2026-07-06 lisp_frontend_design_delta_design_gap_architect

- Prompt file: `workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/draft_implementation_architecture.md` and `workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/revise_implementation_architecture.md`
- Observed bad behavior: Run `20260706T043621Z-6higvw` drafted an approved design-gap plan that embedded a generated run-scoped path under `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R40/...`; deterministic validation rejected the durable plan afterward.
- Root cause in prompt text: The prompts provide generated target/context paths as authoritative context, but do not clearly separate durable authored docs from run-scoped artifact references.
- Proposed edit: Replace any wording that can be read as requiring generated state paths in durable docs with: "Durable architecture and plan documents may name generated artifacts by role, but must not paste run-scoped `state/.../drain/iterations/...` or `state/workflow_lisp/calls/...` paths."
- Expected behavior change: Draft/revise agents should still use generated context files while writing reusable durable docs that pass the existing run-scoped-path validator.
- Risk / tradeoff: The prompt becomes stricter about copied evidence paths; if a check command truly needs a generated path, it should stay in generated `check_commands.json`, not in the durable plan body.
