# Project Consistency Quality Pass Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` for bounded implementation tasks; the coordinator owns integration and independent review.

Status: complete. Corrections are integrated and reviewed; unresolved findings and broad-suite verification limits are recorded in the report. This is an audit and correction record, not a roadmap selector.

**Goal:** Reconcile current code, specs, routing, workflow contracts, and human/agent guidance without weakening validation, provenance, recovery, or approval gates.

**Approach:** Trace each confirmed contradiction to its durable owner, then correct stale dependent surfaces or the implementation that violates that contract. Preserve the existing dirty checkout and frozen historical evidence. This makes undocumented compatibility assumptions harder to retain; name their scope instead of silently treating them as current policy.

**Tools:** Existing Python/pytest, CLI validators and smoke checks, Markdown, and focused repository searches; no new audit framework.

## Authority and scope

Start at `docs/index.md`, `specs/index.md`, `docs/design/README.md`, and `docs/capability_status_matrix.md`. Runtime specs and explicit repository policy govern; accepted frontend component designs own frontend semantics. Catalogs route readers and do not create behavior or select new work. `docs/documentation_conventions.md` governs documentation hygiene.

Inventory the whole tracked/nonignored project, excluding temporary scratch output. Read-only scouts cover runtime/specs, workflows/prompts/automation, and human/agent guidance; the coordinator covers canonical routing, status, and integration. Historical plans and immutable reports remain evidence at their recorded revision, rather than targets for bulk rewriting. Existing ES edits, proposed research/effect-ledger work, and owner-adoption gates remain in place.

## Tasks

- [x] Snapshot initial file contents/status outside the repository and inventory the project.
- [x] Confirm and classify contradictions using the consistency-quality-pass labels; record owners and concept footprints.
- [x] Correct current entry points and guidance: `README.md`, `CLAUDE.md`, `tests/README.md`, `docs/documentation_conventions.md`, workflow/frontend catalogs, and stale canonical index/status entries. Update historical document headers only where current routing misrepresents them.
- [x] Reconcile CLI version/default claims with `specs/cli.md`, `specs/versioning.md`, `orchestrator/cli/`, and the existing summary timeout owner. Use a failing behavioral regression for any runtime fix; preserve explicit and persisted overrides.
- [x] Trace live Design Delta prompt targets and structured return contracts through `.orc` producers/consumers; correct verified prompt drift without resurrecting pointer-file state. Run rendered-request/contract or dataflow checks, not literal prompt-text assertions, plus a workflow smoke check.
- [x] Validate routing/link targets and machine-readable manifests with existing validators, then run the narrow relevant pytest selectors. If tests are added or renamed, collect their modules first. Broader tests use `pytest -q -n 16 --dist=worksteal` in tmux.
- [x] Obtain independent specification review, then quality review; inspect the final diff and fresh verification output personally.
- [x] Publish a discoverable report under `docs/reports/2026-09-08-project-consistency-quality-pass.md` with root causes, authority, old/new rules, files changed, verification, coverage limits, and remaining intentional distinctions.

## Initial findings and decision boundary

- `stale_duplicate` / `routing_mismatch`: completed Q/L and migration work still appears active in catalog entries.
- `label_driven_policy`: workflow age competes with registry-backed copy readiness.
- `semantic_conflict`: new-run summary defaults use 120 seconds while the CLI spec, summary service, and fresh resume configuration use 300.
- `stale_duplicate`: human/agent testing and authoring instructions retain retired paths and frontend behavior.
- `semantic_conflict`: live Design Delta prompts reference pointer files or a result bundle shape that differs from the typed request/return contract; trace before patching.
- The CLI spec advertises never-implemented environment defaults. Optional clarification received no answer before independent work completed; the stated working interpretation retains these names as planned, explicitly documents their current lack of effect and flag alternatives, and requires a retention/deletion contract before activation. Already marked optional/post-MVP commands and flags retain that distinction.

## Verification selection

Use existing owners after confirming selectors: `tests/test_cli_observability_config.py`, `tests/test_runtime_observability_cli.py`, `tests/test_cli_prompt_run_seam.py`, `tests/test_yaml_frontend_retirement.py`, `tests/test_workflow_lisp_route_readiness.py`, `tests/test_workflow_lisp_verification_gate.py`, `tests/test_workflow_lisp_drain_roadmap_routing.py`, and `tests/test_workflow_lisp_design_delta_smoke.py`. Add narrower prompt-contract/dataflow owners if necessary. Run the documented provider-free CLI workflow dry-run from the repository root. Record exact completed commands and outcomes in the report; do not claim exhaustive behavioral verification from a text sweep.
