# Agent-Orchestration Documentation Hub

This index provides a routing map of the repo documentation so you can quickly find the right contract, guide, catalog, or example.

Normative behavior lives in `specs/`.  
Informative guidance and mental models live in `docs/`.

## Fast Triage

| Need | Start Here | Why |
| --- | --- | --- |
| Understand the system at a high level | [Architecture Overview](architecture_overview.md) | Short conceptual front door before the fuller orchestration model. |
| Find normative runtime behavior | [Master Spec](../specs/index.md) | Specs win when docs disagree. |
| Check whether a workflow surface is implemented, partial, future, or legacy | [Capability Status Matrix](capability_status_matrix.md) | Status and copy-safety routing for common DSL and Workflow Lisp surfaces. |
| Check which suites count toward stdlib migration verification and which builtin stdlib modules are landed versus compatibility-only | [Workflow Lisp Verification Gate](workflow_lisp_g6_verification_gate.json) | Checked-in gate manifest for counted suites, builtin stdlib inventory, and routing metadata. |
| Review the retired YAML/YML workflow estate | [YAML Workflow Estate Triage](workflow_yaml_estate_triage.md) | Frozen historical projection of the content-addressed five-queue handoff; all queues are drained and the authored workflow estate is empty. |
| Check the current Workflow Lisp pure-expression, projection, materialized-view, resource-transition, or stdlib phase/drain surface | [Workflow Lisp Frontend Specification](design/workflow_lisp_frontend_specification.md) | Documents the closed operator set, computed-`if` proof boundary, generated `pure_projection` / `materialize_view` runtime surfaces, the declared/runtime-native `resource-transition` lane, and the `phase-scope` / `finalize-selected-item` / `backlog-drain` stdlib contract. |
| Author or audit bounded live provider coordination | [Workflow Lisp Provider Live Binding](design/workflow_lisp_provider_live_binding.md) and [Provider Peer Messaging](design/workflow_lisp_provider_peer_messaging.md) | The distinct target-2.16 one-worker/one-supervisor surface and target-2.17 static 2..8-member cooperative-peer surface are implemented. |
| Review the completed Stage-7 v1.1 implementation | [Provider Peer Messaging v1.1 Implementation Plan](plans/2026-07-24-provider-peer-messaging-v1.1-implementation-plan.md) | Historical execution evidence for exact attempt-bound ingress, append-before-offer ledgers, cooperative receipts, typed settlement, no forcing edge, and both ordered final reviews. |
| Check whether imported generic helpers can compose constrained `match`, imported transitions/resources, and `materialize-view` through ordinary specialization | [Capability Status Matrix](capability_status_matrix.md) | Routes to the landed G5A proof surface and its owning evidence lanes. |
| Choose a design doc | [Design Documentation Index](design/README.md) | Groups current contracts, migration guidance, frontend direction, and deferred work. |
| Author new workflows | [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md) | Preferred `.orc` authoring route, availability guidance, and typed-contract patterns. |
| Interpret historical YAML workflows | [Workflow Drafting Guide](workflow_drafting_guide.md) | Retired-frontend reference for translating historical YAML/YML semantics into `.orc`; authored YAML can no longer be run or resumed. |
| Start or adapt the current target-design / design-gap drain | [Design Delta drain `.orc`](../workflows/library/lisp_frontend_design_delta/drain.orc) | Promoted Workflow Lisp primary for the Design Delta family; the authored YAML family is archived and the historical promotion report remains preserved. |
| Keep new docs discoverable | [Documentation Conventions](documentation_conventions.md) | Status, authority, evidence, and copy-safety checklist. |
| Copy a workflow example | [Workflow Index](../workflows/README.md) | Catalog status and copy-safe run commands. |

## Clarifications ⚠️

These are the highest-impact terminology and contract confusions.

| Topic | Common Confusion | Correct Model | Reference |
| --- | --- | --- | --- |
| `depends_on` vs `consumes` | "They are redundant." | `depends_on` declares file dependencies and optional prompt injection; `consumes` is v1.2+ artifact producer/consumer lineage with typed preflight/freshness semantics. | [Dependencies](../specs/dependencies.md), [DSL](../specs/dsl.md) |
| Queue lifecycle | "Orchestrator auto-moves queue items." | Queue item movement is workflow-authored; orchestrator does not auto-move individual task files. | [Queues and Wait-For](../specs/queue.md) |
| Orchestration vs DSL | "DSL is the entire system." | DSL is the authored contract language; orchestration is DSL + runtime + queue conventions + operations policy. | [Orchestration Start Here](orchestration_start_here.md) |
| Rollback/checkpoint workflow safety | "Every workflow needs the same live-checkout git rules." | Only workflows with DSL-level git rollback/checkpoint behavior need special coexistence rules; author them explicitly, prefer recorded refs over ancestry shortcuts like `HEAD^`, and consider a dedicated run checkout. | [Orchestration Start Here](orchestration_start_here.md), [Workflow Drafting Guide](workflow_drafting_guide.md) |
| Docs vs specs precedence | "Any docs page is authoritative." | `specs/` are normative. `docs/` are explanatory. | [Master Spec](../specs/index.md) |
| Workflow authoring surfaces | "Workflow inputs, prompt files, dependencies, and artifacts are all the same kind of input." | Keep four surfaces separate: workflow boundary (`inputs`/`outputs`), runtime dependencies (`depends_on`/`consumes`), provider prompt sources (`input_file`/`asset_file`/`asset_depends_on`), and artifact storage or lineage (`artifacts`, `expected_outputs`, `output_bundle`, `publishes`). | [Workflow Drafting Guide](workflow_drafting_guide.md), [DSL](../specs/dsl.md), [Providers](../specs/providers.md) |
| Semantic authority | "Reports, pointer files, debug YAML, and typed state can all decide workflow meaning." | Structured state, artifact values, contracts, snapshots, and semantic IR are authority. Reports, pointer files, rendered plans, and debug YAML are views or representations unless a specific contract says otherwise. | [Workflow Language Design Principles](design/workflow_language_design_principles.md), [Workflow Drafting Guide](workflow_drafting_guide.md) |
| Migration promotion | "If a `.orc` workflow compiles and dry-runs, it can replace the YAML primary." | Promotion requires computed parity evidence for output contracts, terminal states, artifacts, resume/reuse behavior, accepted differences, and deprecated mechanics. | [Workflow Lisp Key Migration Parity Architecture](design/workflow_lisp_key_migration_parity_architecture.md), [Workflow Language Design Principles](design/workflow_language_design_principles.md), [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md) |
| Inline command glue | "Python and shell commands should either be banned entirely or accepted as normal workflow authoring." | Command steps are allowed for external tools and certified adapters. Hidden workflow semantics in inline Python/shell, ad hoc JSON rewrites, pointer-as-state, or report parsing are migration debt and need typed procedures, certified command adapters, or runtime-native effects. | [Workflow Command Adapter Contract](design/workflow_command_adapter_contract.md), [Workflow Drafting Guide](workflow_drafting_guide.md) |
| Adjudicated provider output | "The best candidate's stdout becomes the step output." | `adjudicated_provider` scores output-valid candidates, promotes only declared deterministic outputs, and suppresses candidate/evaluator stdout from normal step output state. | [Workflow Drafting Guide](workflow_drafting_guide.md), [DSL](../specs/dsl.md), [Step IO](../specs/io.md) |
| Managed provider jobs | "Managed training jobs should be encoded as manual guard and recovery command steps." | `managed_jobs` remains a v2.13 runtime modifier documented for historical lowered workflows: policy, watch roots, backend, poll budget, and managed outcome routes let runtime-owned guard, shim, audit, recovery, and resumable state replace hand-authored recovery glue. Runnable authoring starts in Workflow Lisp and must use an implemented `.orc` lowering surface. | [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md), [Historical Workflow Drafting Guide](workflow_drafting_guide.md), [DSL](../specs/dsl.md), [Providers](../specs/providers.md) |
| Structured result channel | "JSON printed to stdout counts as a provider/command structured result." | Results travel only as validated bundles at runtime-bound output locations (`output_bundle.path` / `variant_output.path`); wrong-path writes fail closed; stdout/stderr are observability evidence, never a result channel. The declared return type is the contract; the bound-path bundle is the sanctioned transport behind it. | [Workflow Lisp Runtime Migration Foundation](design/workflow_lisp_runtime_migration_foundation.md), [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md), [Step IO](../specs/io.md) |

---

## Reading Paths

Use these paths when you know the kind of work you are doing but not yet which
document owns the answer.

### When Changing Specs

- Start with [Master Spec](../specs/index.md).
- Read the relevant normative spec, usually [DSL](../specs/dsl.md),
  [Step IO](../specs/io.md), [State](../specs/state.md),
  [Providers](../specs/providers.md), or [Dependencies](../specs/dependencies.md).
- Check [Workflow Drafting Guide](workflow_drafting_guide.md) only for
  author-facing explanation and examples.
- If docs and specs disagree, specs win; update explanatory docs afterward.

### When Writing Or Revising Design Docs

- Start with [Design Template](templates/design_template.md).
- Read [Workflow Language Design Principles](design/workflow_language_design_principles.md).
- Read the closest existing design document before adding a new one.
- If the design changes discoverability, update this index.
- If the design introduces runtime or validation obligations, add or plan the
  corresponding `specs/` update.

### When Working On Workflow Lisp

- Start with [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md).
- Check the parent [Workflow Lisp Frontend Specification](design/workflow_lisp_frontend_specification.md).
- Use the component docs for current-checkout behavior: Semantic IR, Executable
  IR, Macro Surface, Stdlib Lowering, State Layout, and related frontend docs.
- If the question is specifically about pure computation or generated typed
  projection, or about generated runtime-native `resource-transition`, read the
  frontend specification first and then the Semantic IR / State Layout
  component docs for `pure_projection` / `materialize_view` /
  `resource_transition` visibility and bundle ownership.
- For promoted workflow migration, also read
  [Workflow Lisp Key Migration Parity Architecture](design/workflow_lisp_key_migration_parity_architecture.md).

### When Migrating YAML To `.orc`

- Start with [Workflow Lisp Key Migration Parity Architecture](design/workflow_lisp_key_migration_parity_architecture.md).
- Read [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md) and
  [Workflow Language Design Principles](design/workflow_language_design_principles.md).
- Check the relevant runtime specs for the behavior being preserved.
- Treat compile, validation, and dry-run as necessary evidence, not promotion.

### When Authoring Workflows

- Start with [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md).
- Check the [Capability Status Matrix](capability_status_matrix.md) and the
  route-readiness registry before selecting a form or copy-safe `.orc` example.
- Check [DSL](../specs/dsl.md), [Step IO](../specs/io.md), and
  [Providers](../specs/providers.md) for normative behavior.
- Use [Prompt Index](../prompts/README.md) when provider prompts are involved.
- Use [Workflow Drafting Guide](workflow_drafting_guide.md) only to interpret
  or translate historical YAML/YML source; the retired frontend cannot execute it.

### When Reviewing Plans Or Backlog Drains

- Start with [Work Definition Model](work_definition_model.md).
- Read the relevant work instructions under `docs/plans/`.
- For generated gap designs, use
  [Design Gap Architecture Template](templates/design_gap_implementation_architecture_template.md).
- Check the active design, backlog item, run evidence, and any generated
  summaries before changing status labels.

---

## Quick Start

### [README](../README.md) - Project Overview
**Description:** High-level project entrypoint with setup, CLI quickstart, version snapshot, and common commands.  
**Keywords:** setup, install, quickstart, cli  
**Use this when:** You are onboarding or need to run the orchestrator quickly.

### [Orchestration Start Here](orchestration_start_here.md)
**Description:** Conceptual foundation for the system and glossary of orchestration/workflow/runtime terminology, with a relationship diagram and a reminder that live-checkout git-safety rules are repo-local policy only for workflows with DSL-level git rollback/checkpoint behavior.
**Keywords:** concepts, glossary, orchestration, dsl, runtime, git
**Use this when:** You need a clean mental model before authoring workflows or debugging behavior.

### [Runtime Execution Lifecycle](runtime_execution_lifecycle.md)
**Description:** Step-by-step runtime timeline from workflow load/validation through step execution, contract enforcement, and termination.  
**Keywords:** runtime, execution, state, lifecycle, control-flow  
**Use this when:** You need to understand what the engine actually does during `run`/`resume`.

### [Workflow Monitoring](workflow_monitoring.md)
**Description:** Operational runbook for `orchestrator monitor`, including multi-workspace email notification setup, headless SMTP configuration, dry-run checks, and interpreting completed, failed, crashed, or stalled workflow emails.  
**Keywords:** monitor, email, notifications, headless, stalled, crashed  
**Use this when:** You want email alerts for workflow completion or failures across one or more repositories.

### [Workflow Drafting Guide](workflow_drafting_guide.md)
**Description:** Historical YAML/YML translation reference covering prompt/runtime/flow contract separation, deterministic handoff patterns, managed-provider job conventions, and special-case git rollback/checkpoint mechanics.
**Keywords:** retired-frontend, historical, yaml, migration, prompts, contracts, deterministic-handoff, managed-jobs, gates, git
**Use this when:** You are interpreting or translating historical YAML/YML source; use the Workflow Lisp guide for every runnable workflow.

### [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md)
**Description:** Lisp-first authoring guidance for `.orc` workflows, focused on typed procedures, structured results, semantic/executable authority boundaries, current contract navigation, and avoiding YAML-shaped Lisp.
**Keywords:** lisp-frontend, orc, workflow-authoring, typed-results, structured-state, contracts
**Use this when:** Drafting or reviewing high-level Workflow Lisp workflows, or migrating YAML workflows toward `.orc`.

### [Work Definition Model](work_definition_model.md)
**Description:** Plain model separating semantic invariants, procedural work instructions, bounded work items, workflow mechanics, and run evidence.
**Keywords:** work-definition, semantics, work-instructions, workflow-mechanics, evidence
**Use this when:** Deciding whether content belongs in specs/design docs, body-of-work instructions, work items, workflow source, or run artifacts.

### [Procedure-First Roadmap Execution Sequence](plans/2026-07-09-procedure-first-roadmap-execution-sequence.md)
**Description:** Completed governing cross-plan work order for the refactor, migration, YAML-retirement, provider-live-binding, list-traversal, and final `.orc` language-server stages. Its post-Stage-8 handoff remains historical; the separate 2026-07-26 selection act routes current work to the language-quality successor roadmap.
**Keywords:** workflow-lisp, roadmap, sequencing, parametric-types, procedure-first, refactoring, yaml-retirement
**Use this when:** Auditing the completed numbered stages or the provenance of the post-Stage-8 handoff. Do not use this historical roadmap or the parked evolution proposal to select current work.

### [Workflow Lisp Language Quality And Domain Semantics Roadmap](plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md)
**Description:** Active post-Stage-8 successor selected by the owner direction: Q0 implements the target-2.19 transportable `Value` prerequisite, followed by prompt core, output-position slots, role-separated prompt identity/diagnostics, and judgment views. E0 remains unselected and the evolution roadmap remains parked.
**Keywords:** workflow-lisp, active-roadmap, value, prompt-calculus, prompt-identity, judgments, principle-29
**Use this when:** Selecting or sequencing current post-Stage-8 language-quality work. Start with Q0 and do not select E0, parked evolution, or shelved parsimony candidates from this route.

### [Workflow Lisp Evolution Follow-On Roadmap](plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md)
**Description:** Parked, non-active E0-E5 historical proposal whose durable program-search boundaries were extracted; none of its tranches is selectable.
**Keywords:** workflow-lisp, evolution, variants, trials, genetic-search, prompt-evolution, roadmap
**Use this when:** Tracing the parked proposal only. Select current work from the [Workflow Lisp Language Quality And Domain Semantics Roadmap](plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md): E0 remains unselected and E4P is exclusively absorbed by successor Stage Q3.

### [Procedure-First Reuse Contract](design/workflow_lisp_procedure_first_reuse_contract.md)
**Description:** Accepted boundary and migration contract: workflows own durable public run/resume/invocation/publication identity, while typed procedures are the normal internal reuse unit with explicit lowering and caller-visible effects.
**Keywords:** workflow-lisp, procedures, workflows, reuse, effects, lowering, migration
**Use this when:** Deciding whether a reusable unit remains a workflow, becomes a procedure, or must wait for identity/effect evidence.

### [Procedure-Migration Identity Compatibility](design/workflow_lisp_procedure_migration_identity_compatibility.md)
**Description:** Accepted strict-default compatibility contract with a bounded, evidence-only internal identity-retirement class. Its generic prerequisites are implemented and exactly one reviewed internal pilot is complete; the exception remains narrow and is not a general compatibility route.
**Keywords:** procedure-first, migration, identity, checkpoint, resume, compatibility, retirement
**Use this when:** Deciding whether a procedure migration must preserve identities exactly, wait for a general atomic upgrader, or may enter reviewed internal identity retirement.

### [Procedure-Migration Identity Compatibility Prerequisites Plan](plans/2026-07-13-procedure-migration-identity-compatibility-plan.md)
**Description:** Completed and gated implementation plan for generic lowering-identity, inline checkpoint/provenance, retirement-evidence, and checksum-rejection prerequisites; its final pilot handoff is `f5adcb79`.
**Keywords:** procedure-first, prerequisites, lowering, checkpoint, provenance, checksum
**Use this when:** Reviewing the completed Stage-5 prerequisite gate or its handoff to the tracked-plan pilot; do not re-execute it.

### [Tracked-Plan Procedure-First Pilot](plans/2026-07-13-procedure-first-pilot-plan.md)
**Description:** Completed first reviewed-internal-identity-retirement pilot. Evidence landed at `63e03330`, `e6a85cb7`, `de522c76`, `f5dbac88`, `76205d4f`, and `0769e837`; holistic specification and quality reviews approved HEAD `0769e837`. It retains exactly two completed dedicated runs and does not claim general cross-source compatibility, family migration, promotion, or YAML retirement.
**Keywords:** procedure-first, pilot, tracked-plan, retirement, attestation, quiescence
**Use this when:** Reviewing the completed Stage-5 pilot gate, its exact source-edit boundary, or its narrow evidence-only claim limits; do not re-execute it.

### [Procedure Identity Store Match-Scoped Counts Plan](plans/2026-07-14-procedure-identity-store-match-scoped-counts-plan.md)
**Description:** Completed corrective prerequisite whose generic scanner and record-layer changes landed at `e43461f9` and `5f382401`: match-scoped nonterminal and query-derived old-consumer counts gate eligibility, while terminal matching counts and required whole-store totals remain evidence only. Its corrected pilot evidence and incident recovery are committed at `63e03330`.
**Keywords:** procedure-first, retirement, state-store, matching-counts, evidence
**Use this when:** Reviewing the corrected store-query semantics, completed pilot evidence regeneration, or recorded precommit incident recovery.

### [Resume Projection Integrity Hardening Design And Planning Plan](plans/2026-07-13-resume-projection-integrity-hardening-design-plan.md)
**Description:** Complete design/specification/planning and routing provenance: characterization landed at `1cd60767`, the accepted design at `52e2b05f`, the normative contract at `00135832`, and the reviewed implementation plan at `26a5d3db`; holistic routing reviews and fresh validation passed at closeout. None of these artifacts implements runtime hardening.
**Keywords:** resume, projection, integrity, procedure-first, design-plan, completed-planning
**Use this when:** Reviewing the completed design/specification/planning provenance and its handoff to runtime implementation; do not re-execute it.

### [Resume Projection Integrity Hardening Design](design/resume_projection_integrity_hardening.md)
**Description:** Accepted generic target design for checksum-compatible root and reached-callee projection-integrity auditing, failure envelopes, recursive ownership, optional-ID compatibility, and observability ordering.
**Keywords:** resume, projection, integrity, checksum, call-frame, accepted-design
**Use this when:** Resolving runtime architecture or contract questions while implementing or reviewing resume projection-integrity hardening.

### [Resume Projection Integrity Hardening Implementation Plan](plans/2026-07-13-resume-projection-integrity-hardening-implementation-plan.md)
**Description:** Completed TDD execution record for the accepted resume projection-integrity contract. Runtime implementation and reviewed acceptance evidence closed at `fdf1e06b`.
**Keywords:** resume, projection, integrity, implementation-plan, completed-runtime, tdd
**Use this when:** Reviewing the completed hardening implementation or its evidence; do not re-execute it as the live selector.

### [Procedure-First Migration Waves Implementation Plan](plans/2026-07-13-procedure-first-migration-waves-plan.md)
**Description:** Historical complete Stage-5 migration-wave record. Task 7 handed all 63 YAML legacy rows to Stage 6 at `7e6adc36`; Task 8 sealed the focused, routing, broad-baseline, and independent-review gates.
**Keywords:** procedure-first, migration-waves, completed, parity, inventory
**Use this when:** Reviewing the completed family-wave classifications, retention decisions, exact evidence, or Stage-6 handoff; do not re-execute it as the live selector.

### [User-Facing YAML Retirement Program](plans/2026-07-07-yaml-retirement-program.md)
**Description:** Completed Stage-6 retirement program. All five deletion/archive queues are drained, the authored YAML/YML workflow estate is empty, both `.orc` ports are promoted, fresh non-`.orc` execution rejects before state creation, the production YAML parser and PyYAML dependency are removed, and Task 7 passed its final comparison and review gates.
**Keywords:** yaml, yml, retirement, complete, deletion-first, orc
**Use this when:** Reviewing the completed deletion queues, ORC-only frontend contract, final baseline comparison, or Stage-6 review closure.

### [YAML-Retirement Task 2 Commit-Lineage Restart Design](plans/2026-07-22-yaml-retirement-task-2-commit-lineage-restart-design.md)
**Description:** Accepted corrective design for preserving an owner-adopted but uncommitted Task 2 attempt whose workspace predecessor was invalidated, restoring its tracked ledger, and restarting from a commit-aligned baseline without transferring the archived adoption.
**Keywords:** yaml, retirement, task-2, incident, lineage, archive, restart
**Use this when:** Reviewing the lifecycle-specific v2 archive/replay contract for the invalidated Task 2 attempt. It corrects that attempt only and does not alter YAML-retirement roadmap ordering.

### [YAML-Retirement Task 2 Commit-Lineage Restart Implementation Plan](plans/2026-07-22-yaml-retirement-task-2-commit-lineage-restart-implementation-plan.md)
**Description:** Active execution plan for reviewed implementation authority, exact incident/disposition capture, byte-preserving relocation, tracked-ledger restoration, and a fresh Task 2 attempt at the real HEAD.
**Keywords:** yaml, retirement, task-2, implementation, evidence, restart
**Use this when:** Executing or auditing the corrective recovery sequence for the owner-adopted uncommitted Task 2 attempt. It remains subordinate to the Stage-6 Task-6 plan and does not reorder the roadmap.

### [YAML-to-Workflow-Lisp Gap List](workflow_yaml_orc_gap_list.md)
**Description:** Completed Stage-6 Task-1 contract that governed the two promoted `.orc` ports and the owner-dispositioned holdout through their now-complete fail-closed gates; specification PASS and quality APPROVED.
**Keywords:** yaml, orc, retirement, gap-list, completed, provider-policy, parity
**Use this when:** Designing either retained `.orc` port, checking its still-binding provider/prompt/parity gates, or reviewing why the protected holdout remains owner-gated.

### [Workflow Lisp Provider Prompt Dependencies](plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-design.md)
**Description:** Implemented generic functional contract for typed required and optional exact relpaths on `provider-result`, deterministic bounded content injection, one immutable per-attempt snapshot, crash-durable attempt allocation, and content-free evidence. Runtime plan remains topology-only and evidence is non-authoritative. The retired YAML twins supplied historical parity evidence for the promoted `verified_iteration_drain` and `generic_run_watchdog` `.orc` routes before deletion.
**Keywords:** workflow-lisp, provider, prompt-dependencies, relpath, snapshot, retry, evidence
**Use this when:** Authoring or reviewing `.orc` provider calls that must receive workspace file contents, or auditing the completed survivor-family prompt-dependency parity proofs.

### [YAML Deprecation Surface Design](plans/2026-07-17-yaml-deprecation-surface-design.md)
**Description:** Historical Stage-6 Task-4 advisory design, superseded by Task 7's ORC-only rejection and parser removal. It records the transition boundary but is not current runtime behavior.
**Keywords:** yaml, deprecation, historical, warning, retired-frontend, task-4
**Use this when:** Reviewing the temporary advisory phase that preceded final YAML frontend retirement.

### [Tracked-Design Phase Identity-Retirement Plan](plans/2026-07-16-tracked-design-phase-identity-retirement-plan.md)
**Description:** Completed bounded eligibility decision for Migration Waves Task 2 Step 1. The generic scanner found 26 supported old-identity consumers in the retained pilot store, so the callee remains a workflow and its row is retained as `effect-adapter`; no source, YAML, remap, or cross-source-resume change occurred.
**Keywords:** procedure-first, migration-wave, tracked-design, identity-retirement, completed, eligibility-stop
**Use this when:** Reviewing why `tracked-design-phase` was retained or replaying its deterministic eligibility-stop evidence.

### [Stack Implementation Phase Identity-Retirement Plan](plans/2026-07-16-design-plan-impl-implementation-phase-identity-retirement-plan.md)
**Description:** Completed bounded eligibility decision for Migration Waves Task 2 Step 2. The generic scanner found 24 supported old-identity consumers in the retained pilot store, so the callee remains a workflow and its row is retained as `effect-adapter`; no source, run, YAML, remap, or cross-source-resume change occurred.
**Keywords:** procedure-first, migration-wave, implementation-phase, identity-retirement, completed, eligibility-stop
**Use this when:** Reviewing why `design-plan-impl-implementation-phase` was retained or replaying its deterministic eligibility-stop evidence.

### [Same-File Build-Checks Identity-Retirement Decision](plans/2026-07-16-same-file-build-checks-identity-retirement-plan.md)
**Description:** Completed bounded eligibility decision for Migration Waves Task 2 Step 3. The containing route is live/current guidance, so strict compatibility is mandatory and `build-checks` remains a workflow even though known-store scans found no matching consumers.
**Keywords:** procedure-first, migration-wave, build-checks, strict-compatibility, live-route, eligibility-stop
**Use this when:** Reviewing why the same-file helper was retained or why zero matching store consumers do not override the live-route gate.

### [Design Delta Exported-Workflow Retention Decision](plans/2026-07-16-design-delta-exported-workflow-retention-plan.md)
**Description:** Task 3 fail-closed decision retaining seven internal calls because their five unique callees are exported, CLI-selectable workflows that require strict identity compatibility; the five callees are recorded separately as public boundaries.
**Keywords:** procedure-first, design-delta, exported-workflow, public-boundary, strict-compatibility, eligibility-stop
**Use this when:** Reviewing why Task 3 performed no source migration or reconciling its seven retained calls and five public entries.

### [Design Delta Finalizer-Projection Checkpoint-Retention Decision](plans/2026-07-16-design-delta-finalizer-projection-checkpoint-retention-plan.md)
**Description:** Reviewed Task 5 strict-compatibility stop retaining four finalizer-projection calls because their hypothetical inline conversion removes four public-wrapper checkpoints and adds none; the four rows remain active effect adapters.
**Keywords:** procedure-first, design-delta, finalizer, checkpoint-identity, strict-compatibility, retained
**Use this when:** Reviewing the finalizer-projection retention evidence or its handoff to the later blocked recovery/finalization audit.

### [Design Delta Blocked-Recovery Lowering-Retention Decision](plans/2026-07-16-design-delta-blocked-recovery-lowering-retention-plan.md)
**Description:** Task 5 decision retaining the exported classifier under strict compatibility and five blocked-finalizer calls because their exact-path inline conversion is rejected with `pure_expr_operand_type_mismatch` before an executable exists.
**Keywords:** procedure-first, design-delta, blocked-recovery, compiler-diagnostic, fail-closed, retained
**Use this when:** Reviewing why the six rows remain effect adapters, why no checkpoint/runtime parity is claimed, or the handoff to phase orchestration.

### [Design Delta Phase-Orchestration Retention Decision](plans/2026-07-16-design-delta-phase-orchestration-retention-plan.md)
**Description:** Task 5 fail-closed decision retaining eight calls because four unique callees are compiled exported workflows, and retaining the private pending call because its compiling inline hypothetical removes one caller-owned workflow-call boundary checkpoint and adds twelve caller-owned inline checkpoints with different checkpoint/storage identities and a different generated presentation-path namespace.
**Keywords:** procedure-first, design-delta, phase-orchestration, public-boundary, checkpoint-identity, retained
**Use this when:** Reviewing why all nine phase-orchestration rows remain effect adapters or the historical handoff to completed finalization without a runtime-parity claim.

### [Design Delta Completed-Finalization Lowering-Retention Decision](plans/2026-07-16-design-delta-completed-finalization-lowering-retention-plan.md)
**Description:** Task 5 closeout retaining two private completed-finalization calls because the complete exact-path inline hypothetical fails shared validation with exactly two `workflow_boundary_type_invalid` blocker-class variant-proof diagnostics and produces no executable.
**Keywords:** procedure-first, design-delta, completed-finalization, shared-validation, compiler-diagnostic, retained
**Use this when:** Reviewing the final Task 5 retention proof, its unchanged-source boundary, or the handoff to Task 6 Step 1.

### [Design Delta Drain-Builder Checkpoint-Retention Decision](plans/2026-07-16-design-delta-drain-builder-checkpoint-retention-plan.md)
**Description:** Task 6 fail-closed decision retaining the sole private drain-builder call because its complete compiling inline hypothetical removes one caller-owned checkpoint and adds none, removes the builder bundle/call/state projection, and changes hidden `RunCtx` defaults without runtime or resume parity evidence.
**Keywords:** procedure-first, design-delta, drain-builder, checkpoint-identity, retained
**Use this when:** Reviewing why Task 6 performed no source/history migration before the completed Task 7 handoff and Task 8 closeout.

### [Procedure-First Reuse Inventory](plans/2026-07-13-procedure-first-reuse-inventory.md)
**Description:** Reviewed current inventory of 95 active internal authored call sites—0 procedure candidates, 32 effect adapters, and 63 legacy-retire sites—plus 13 separately recorded public entries and one append-only migrated-history row, with machine-readable provenance in the adjacent JSON file.
**Keywords:** procedure-first, inventory, migration, effect-adapter, legacy-retire, public-boundary
**Use this when:** Selecting a concrete migration family or checking why a call site is migrated, retained, or routed to YAML retirement.

**Component-plan routing:** The refactoring, drain/G8 retirement, Stage-4 design, native returns, typed guidance, resolved-effect substrate, identity prerequisites, [tracked-plan pilot](plans/2026-07-13-procedure-first-pilot-plan.md), and [resume projection-integrity hardening implementation](plans/2026-07-13-resume-projection-integrity-hardening-implementation-plan.md) are complete. The hardening design/specification/planning commits remain `1cd60767`, `52e2b05f`, `00135832`, and `26a5d3db`; runtime implementation and its reviewed gate closed at `fdf1e06b`. **The [procedure-first migration waves implementation plan](plans/2026-07-13-procedure-first-migration-waves-plan.md) is historical complete. Task 1 rebaselined at `4983afff` plus `fa16bcf0`; Task 2 completed at `daff694c`: Step 1's [tracked-design identity decision](plans/2026-07-16-tracked-design-phase-identity-retirement-plan.md) and Step 2's [implementation-phase identity decision](plans/2026-07-16-design-plan-impl-implementation-phase-identity-retirement-plan.md) retained 26- and 24-consumer boundaries, while Step 3's [same-file strict-compatibility decision](plans/2026-07-16-same-file-build-checks-identity-retirement-plan.md) retained the live route. Task 3's [exported-workflow retention decision](plans/2026-07-16-design-delta-exported-workflow-retention-plan.md) retained seven calls. Task 4 closed at `c9687539`, `26d9ecd0`, and `848ceb52`. Task 5 retained 4 + 6 + 9 + 2 = 21 calls under the [finalizer-projection](plans/2026-07-16-design-delta-finalizer-projection-checkpoint-retention-plan.md), [blocked-recovery](plans/2026-07-16-design-delta-blocked-recovery-lowering-retention-plan.md), [phase-orchestration](plans/2026-07-16-design-delta-phase-orchestration-retention-plan.md), and [completed-finalization](plans/2026-07-16-design-delta-completed-finalization-lowering-retention-plan.md) decisions. Task 6's [drain-builder checkpoint-retention decision](plans/2026-07-16-design-delta-drain-builder-checkpoint-retention-plan.md) retained the sole private builder call; Task 6 is complete. Task 7 handed all 63 legacy-retire rows to Stage 6 at `7e6adc36`. Task 8 sealed 565 passed/6 skipped focused, 36 passed routing, and 4992 passed/17 skipped with six established unrelated broad failures adjudicated as four digest-exact plus two logger-location-only; specification PASS and quality APPROVED closed the wave. The final inventory is 0 procedure candidates, 32 effect adapters, 63 legacy-retire rows, 13 public entries, and one history row, so procedure-first adoption is not universal.** Stage 6 YAML retirement Tasks 1-7 are complete: the ORC-only frontend, parser removal, 1,020-passed/5-skipped focused gate, fresh smoke, zero-new-failure scoped broad comparison, and ordered specification PASS/quality APPROVED reviews closed the stage at `d9baa120`. Its owner is the [YAML retirement program](plans/2026-07-07-yaml-retirement-program.md). [Provider live binding](design/workflow_lisp_provider_live_binding.md) v1 implementation landed through `4d4f05c7` and is complete through Task 15 and Gate S7-v1 under its reviewed [execution plan](plans/2026-07-23-provider-live-binding-implementation-plan.md); the separate target-2.17 [v1.1 peer-messaging design](design/workflow_lisp_provider_peer_messaging.md) and reviewed [implementation plan](plans/2026-07-24-provider-peer-messaging-v1.1-implementation-plan.md) are implemented through `b08c04a6`. Task 12's documentation, verification, and ordered `TASK12_FINAL_SPEC_APPROVED` / `TASK12_FINAL_QUALITY_APPROVED` reviews close Gate S7-v1.1 and Stage 7. The [pure list-traversal design](design/workflow_lisp_pure_list_traversal.md) and its reviewed [implementation plan](plans/2026-07-25-workflow-lisp-pure-list-traversal-implementation-plan.md) are implemented and complete for the exact target-2.18 bounded surface. The final [language-server design](design/workflow_lisp_language_server.md) and its reviewed nine-task [implementation plan](plans/2026-07-25-workflow-lisp-language-server-implementation-plan.md) are implemented; Stage 8 and the numbered roadmap are complete. The completed pilot remains one narrow evidence-only exception. The [Stage-0 activation plan](plans/2026-07-09-procedure-first-roadmap-activation-plan.md) is historical activation evidence.

**Current status:** Stages 6–8 and the selected target-2.18 list-traversal interstage are complete. Provider-supervision v1 closed Gate S7-v1 through `4d4f05c7`; cooperative peer messaging v1.1 closed Gate S7-v1.1 through `b08c04a6` plus Task 12's documentation, verification, and ordered `TASK12_FINAL_SPEC_APPROVED` / `TASK12_FINAL_QUALITY_APPROVED` reviews. The bounded structurally typed list surface is implemented under principle 29. Language-server v1 closed Gate S8 under its reviewed nine-task implementation plan. The numbered roadmap is historical; its post-Stage-8 handoff does not select successor work.

**Current procedure-first substrate:** Native returns, typed guidance, the resolved-effect substrate, identity prerequisites, match-scoped scanner/record support, one reviewed internal pilot, generic resume projection-integrity hardening, the bounded migration wave, provider-supervision v1, cooperative peer messaging v1.1, bounded target-2.18 list traversal, and language-server v1 are implemented and gated. The wave intentionally retains 32 effect adapters and therefore does not establish universal procedure-first conversion. Its 63 YAML legacy rows completed the Stage-6 deletion queues; no numbered roadmap stage remains active.

### [Workflow Lisp Autonomous Drain Work Instructions](plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md)
**Description:** Procedural prescriptions for the active Workflow Lisp autonomous drain body of work, including objective, source material, work order, constraints, documentation expectations, completion target, and out-of-scope boundaries.
**Keywords:** lisp-frontend, autonomous-drain, work-instructions, full-design, procedural-prescriptions
**Use this when:** Preparing or reviewing Workflow Lisp drain work that needs the upfront procedure separated from semantic specs and workflow mechanics.

### [Local Workflow Steering](steering.md)
**Description:** Local steering constraints for the DSL v2.14 materialization and variant-output backlog drain, including the released v2.14 runtime surface and current Phase 2 workflow-translation gate.
**Keywords:** steering, backlog-drain, dsl-v214, roadmap-gate
**Use this when:** Launching or reviewing the local NeurIPS-style workflow for DSL v2.14 materialization and variants.

### [Verified-Iteration Drain](design/verified_iteration_drain.md)
**Description:** Implemented verified-iteration drain whose promoted Workflow Lisp primary runs a single fused-session select/plan/implement/verify loop and treats the repo, git history, and check exit codes as sole authority. New launches use `workflows/library/verified_iteration_drain/drain.orc`; its retired YAML twin survives only in history and parity evidence.
**Keywords:** drain, workflow-lisp, repeat_until, repo-as-truth, verified-iteration
**Use this when:** Launching or adapting the promoted verified-iteration `.orc` loop alongside (not replacing) the `lisp_frontend_*` drain family.

### [Prompt Index](../prompts/README.md)
**Description:** Curated catalog of canonical prompt files, with recent workflow prompt families and superseded near-duplicates called out explicitly.
**Keywords:** prompts, catalog, canonical, review, plan, implementation
**Use this when:** You want to reuse or adapt an existing prompt instead of inventing one from scratch.

### [Design Template](templates/design_template.md)
**Description:** General design-document template for behavior changes, architecture decisions, migrations, operational designs, and boundary/spec clarifications.
**Keywords:** design, template, architecture, contracts, invariants, verification, migration
**Use this when:** Drafting or reviewing a design that needs explicit authority, contracts, dependencies, failure modes, usage/integration checks, documentation impact, and implementation handoff.

### [Design Gap Architecture Template](templates/design_gap_implementation_architecture_template.md)
**Description:** Narrow template for gap designs / implementation architectures that close one selected gap in an already accepted design without redefining system-wide contracts.
**Keywords:** design-gap, implementation-architecture, gap-design, template, bounded-slice, handoff
**Use this when:** Drafting or reviewing a generated `implementation_architecture.md` under `docs/plans/**/design-gaps/`; use the general design template for broader system/spec designs instead.

### [Workflow Language Design Principles](design/workflow_language_design_principles.md)
**Description:** Cross-frontend design principles for semantic authority, typed transitions, report/pointer boundaries, validation-before-commit, variant proof, effects, source maps, and future frontend requirements.
**Keywords:** workflow-language, semantics, authority, typed-transitions, frontend, lisp, ir
**Use this when:** Deciding whether a DSL feature, Lisp frontend form, macro, or workflow abstraction strengthens core semantics or merely shortens brittle authoring syntax.

### [Workflow Command Adapter Contract](design/workflow_command_adapter_contract.md)
**Description:** Design guidance for separating legitimate command steps and certified command adapters from hidden semantic inline Python/shell glue.
**Keywords:** command-adapter, inline-glue, workflow-language, semantic-authority, adapters, lints
**Use this when:** Auditing workflow command steps, extracting inline Python or shell, deciding whether a script should be a certified adapter, or planning runtime-native promotion.

### [Workflow Lisp MVP Comparison](workflow_lisp_mvp_comparison.md)
**Description:** README-style side-by-side comparison of the Workflow Lisp MVP `.orc` implementation-attempt slice against the equivalent v2.14 YAML slice, focused on whether the frontend removes real brittleness.
**Keywords:** lisp-frontend, mvp, comparison, yaml, orc, readability
**Use this when:** You want the quickest concrete answer to whether the Lisp frontend is an actual authoring improvement.

### [Workflow Lisp Unified Design for Unimplemented Surfaces](design/workflow_lisp_unified_frontend_design.md)
**Description:** Incremental future-target design for Workflow Lisp surfaces that are non-implemented, partial, or deferred, with explicit compile-time/runtime boundaries and acceptance gates.
**Keywords:** lisp-frontend, future-target, let-proc, effectful-composition, runtime-closures
**Use this when:** Selecting, designing, or reviewing the next missing Workflow Lisp frontend increment without treating the target as a replacement specification.

### [Workflow Lisp Frontend Specification](design/workflow_lisp_frontend_specification.md)
**Description:** Accepted baseline and umbrella contract for a typed procedural Lisp frontend that lowers to shared core workflow AST, validation, semantic IR, executable IR, and the existing runtime rather than YAML text, including the current closed pure-expression surface, generated `pure_projection`, `materialize_view`, declared `resource-transition`, structural private-exec-context / `std/context` contracts, target-2.16 bounded provider supervision, and target-2.17 cooperative provider peers.
**Keywords:** lisp-frontend, workflow-language, core-ast, semantic-ir, pure-expression, pure-projection, materialize-view, provider-supervision, defworkflow
**Use this when:** Reviewing the parent Workflow Lisp language contract or checking whether a scoped frontend delta preserves the baseline design.

### [Workflow Lisp Refactor Architecture](design/workflow_lisp_refactor_architecture.md)
**Description:** Behavior-preserving architecture guidance for reducing Workflow Lisp frontend maintainability debt, covering module boundaries, shared traversal, context objects, lowering splits, registries, and public API cleanup.
**Keywords:** lisp-frontend, refactor, architecture, maintainability, module-boundaries
**Use this when:** Planning or reviewing Workflow Lisp frontend refactors that must preserve `.orc` semantics, source maps, diagnostics, contracts, and runtime behavior.

### [Workflow Lisp Semantic Workflow IR](design/workflow_lisp_semantic_workflow_ir.md)
**Description:** Durable current-checkout contract for the shared Semantic IR layer, documenting `SemanticWorkflowIR` and `LoadedWorkflowBundle.semantic_ir` as the typed semantic authority surface while executable IR, runtime-plan, and debug/report projections remain distinct.
**Keywords:** lisp-frontend, semantic-ir, loadedworkflowbundle, contracts, source-map, authority
**Use this when:** Aligning docs, implementation, and tests around the current Semantic IR contract surface without reopening executable or runtime ownership.

### [Workflow Lisp Executable IR](design/workflow_lisp_executable_ir.md)
**Description:** Durable current-checkout contract for the shared executable Workflow Lisp layer, documenting `LoadedWorkflowBundle.ir` and `ExecutableWorkflow` as the validated executable authority, including the distinct composite `provider_supervision.v1` and `provider_peer_group.v1` nodes, while runtime-plan, semantic-IR, source-map, and debug-YAML surfaces remain derived views.
**Keywords:** lisp-frontend, executable-ir, loadedworkflowbundle, runtime-plan, semantic-ir, authority
**Use this when:** Aligning docs, implementation, and tests around the current executable contract surface without reopening runtime or frontend semantics.

### [Workflow Lisp Macro Surface Contract](design/workflow_lisp_macro_surface_contract.md)
**Description:** Bounded current-checkout contract for `defmacro`, covering implemented hygiene, imported lookup and precedence, validation ownership, and macro provenance obligations without promoting future macro features into current behavior.
**Keywords:** lisp-frontend, defmacro, macros, hygiene, import-resolution, source-map
**Use this when:** Aligning implementation, tests, and docs for the current Workflow Lisp macro surface rather than the broader future macro design.

### [Workflow Lisp Frontend MVP Specification](design/workflow_lisp_frontend_mvp_specification.md)
**Description:** Narrow MVP tranche for proving the Lisp frontend with typed records/unions, `provider-result`, `command-result`, `match`, source-span diagnostics, and one real v2.14 phase translation before adding user macros or the full procedural library.
**Keywords:** lisp-frontend, mvp, workflow-language, core-ast, typed-unions, match
**Use this when:** Planning the first implementable Lisp frontend tranche or deciding which parts of the full frontend specification are intentionally deferred.

### [Workflow Lisp Procedure References And Partial Application](design/workflow_lisp_proc_refs_partial_application.md)
**Description:** Accepted design delta and active implementation target for compile-time `ProcRef` and `bind-proc` partial application without runtime procedure values.
**Keywords:** lisp-frontend, procref, defproc, partial-application, higher-order
**Use this when:** Implementing, reviewing, or planning the focused ProcRef / partial-application extension to the Workflow Lisp frontend.

### [Workflow Lisp Local ProcRef Bindings](design/workflow_lisp_let_proc_local_proc_refs.md)
**Description:** Proposed follow-on design delta for `let-proc`, a compile-time lexical procedure-binding form that closure-converts to generated `defproc` plus existing `ProcRef` semantics.
**Keywords:** lisp-frontend, let-proc, procref, lexical-procedure, compile-time
**Use this when:** Reviewing local procedure authoring ergonomics without runtime closures or a second lowering path.

### [Workflow Lisp Provider Prompt Queue](design/workflow_lisp_provider_prompt_queue.md)
**Description:** Proposed design for a static `prompt-queue` grouping on provider invocation forms: one atomic runtime step drives N sequential turns against one persisted provider session, with step-level prompt injections on the first turn and the output contract plus result bundle on the final turn only.
**Keywords:** lisp-frontend, prompt-queue, provider-session, multi-turn, output-contract
**Use this when:** Reviewing or extending the multi-turn provider invocation direction; not implementable until the design is accepted and given an explicit roadmap slot.

### [Workflow Lisp Provider Live Binding](design/workflow_lisp_provider_live_binding.md)
**Description:** Stage 7 v1 contract, implemented through `4d4f05c7`, for default provider observation plus target-2.16 `with-live-providers`: exactly one worker and one supervisor run under a single-writer coordinator, and a validated `CONTINUE|STEER` union permits at most one fail-closed provider-session correction. The separately implemented additive v1.1 contract is owned by the peer-messaging design.
**Keywords:** lisp-frontend, live-binding, tmux-observation, provider-supervision, turn-boundary-resume, structured-concurrency
**Use this when:** Authoring or reviewing the exact shipped v1 surface. Same-turn and unrecorded raw-pane steering remain excluded.

### [Workflow Lisp Provider Peer Messaging](design/workflow_lisp_provider_peer_messaging.md)
**Description:** Implemented Stage-7 v1.1 additive contract for target-2.17 `with-live-provider-peers` and `provider_peer_group.v1`: static 2..8-member groups, exact attempt-bound runtime peer-ready/send/ack/finish, receiver-ledger-before-offer, cooperative natural close, typed bundles, and one atomic settlement with no forcing edge.
**Keywords:** lisp-frontend, provider-peer-messaging, turn-boundary-delivery, provider-peer-group, injected-message-ledger, structured-concurrency
**Use this when:** Authoring or auditing the exact shipped target-2.17 cooperative-peer surface. Do not infer it from target-2.16 supervision or from provider identity.

### [Provider Peer Messaging v1.1 Implementation Plan](plans/2026-07-24-provider-peer-messaging-v1.1-implementation-plan.md)
**Description:** Completed, independently reviewed Stage-7 v1.1 TDD evidence for the structural interactive capability, exact-attempt peer protocol and ledger, single-writer `provider_peer_group.v1` coordinator, target-2.17 frontend/projections, real-provider gates, and Gate S7-v1.1 closure.
**Keywords:** lisp-frontend, provider-peer-messaging, implementation-plan, tdd, runtime, target-2.17
**Use this when:** Auditing the completed Stage-7 v1.1 implementation and its target-2.16 non-regression evidence; it is historical, not the active selector.

### [Workflow Lisp Pure List Traversal](design/workflow_lisp_pure_list_traversal.md)
**Description:** Implemented target-2.18 contract for total list construction/traversal, pure `list/map`, bounded effectful `list/map-effect`, whole-list-contract-expressible loop state, and typed containment-safe `path/join-under`, with record/union list elements, ProcRef mapping, and broader effect bodies deferred.
**Keywords:** lisp-frontend, lists, traversal, mapping, loop-recur, path-containment, principle-29
**Use this when:** Authoring or auditing the exact implemented bounded surface and its deliberate exclusions.

### [Workflow Lisp Pure List Traversal Implementation Plan](plans/2026-07-25-workflow-lisp-pure-list-traversal-implementation-plan.md)
**Description:** Completed seven-task TDD record for target-2.18 dual-schema pure evaluation, list/path frontend forms, list-valued loop carriage, generic exhaustion diagnostics, effectful-map erasure, deterministic clean/resume evidence, and interstage closure.
**Keywords:** lisp-frontend, list-traversal, implementation-plan, target-2.18, pure-expr-schema-2, loop-resume
**Use this when:** Auditing the completed post-Stage-7 interstage and its reviewed implementation history.

### [Workflow Lisp Transportable `Value` Type](design/workflow_lisp_transportable_value_type.md)
**Description:** Accepted target-2.19 design for an opt-in, exact, opaque transport-contract top over strict JSON, with public `type: value` / `kind: value`, existing direct-root `__result__` carriage, no envelope, and no implicit conversion to or from narrower source types.
**Keywords:** lisp-frontend, value, json, transport, direct-root, principle-29, target-2.19
**Use this when:** Implementing or reviewing active successor Stage Q0. It is designed but not yet available for authoring; `Json` remains a distinct non-transportable type.

### [Workflow Lisp Prompt Calculus](design/workflow_lisp_prompt_calculus.md)
**Description:** Owner-selected typed compositional prompt direction covering `defprompt`, kind-based slots, prompt-carried results, output positions, prompt identity, and judgment views. The design still requires Q1 correction/review and is blocked on the target-2.19 `Value` prerequisite.
**Keywords:** lisp-frontend, prompts, defprompt, slots, prompt-identity, judgments, principle-29
**Use this when:** Reviewing the proposed prompt domain surface or preparing successor Stage Q1 after Q0 completes. Do not implement its stale partial-application or procedure-substitution claims before the required design correction.

### [Workflow Lisp Language Server](design/workflow_lisp_language_server.md)
**Description:** Implemented `.orc` LSP v1: a read-only stdio consumer of the production Stage-3 compiler, delivering clean-open/save diagnostics, exact direct-call go-to-definition, document symbols, and visibility/registry completion under one canonical workspace root.
**Keywords:** lisp-frontend, lsp, editor-tooling, diagnostics, go-to-definition, language-server
**Use this when:** Auditing the implemented compiler/tooling contract. For installation, client initialization, editing behavior, freshness, and v1 limits, use the [Workflow Lisp Language Server Setup](workflow_lisp_language_server_setup.md).

### [Workflow Lisp Language Server Setup](workflow_lisp_language_server_setup.md)
**Description:** Practical setup and operating guide for the implemented optional `.orc` language server, including installation, `python -m orchestrator.lsp`, one-root initialization, clean-save behavior, freshness/restart rules, closed navigation, and deliberate v1 limits.
**Keywords:** lisp-frontend, lsp, setup, editor, diagnostics, navigation
**Use this when:** Configuring a generic LSP client or understanding why a dirty, pending, failed, invalidated, or stale document returns no navigation answer.

### [Workflow Lisp Language Server Implementation Plan](plans/2026-07-25-workflow-lisp-language-server-implementation-plan.md)
**Description:** Completed reviewed nine-task Stage-8 TDD record for exact-byte source tracing, a read-only in-memory build seam, immutable single-root state, diagnostic parity, stdio/watcher transport, compiler-owned callee provenance, closed navigation, packaging, and end-to-end closure.
**Keywords:** lisp-frontend, lsp, implementation-plan, diagnostics, navigation, stage-8
**Use this when:** Auditing Stage-8 implementation order, evidence, and ordered reviews. It is no longer an active selector.

### [Workflow Lisp Parametric Type System](design/workflow_lisp_parametric_type_system.md)
**Description:** Single-owner design for the parametric type-system direction: generic `defproc` with `:forall`/`:where`, the structural-constraint vocabulary (including type-parameter constraint field types and subset semantics), the instantiate-then-typecheck specialization pipeline, diagnostics contract, and the permanent-primitive vs migration-destined form classification with the per-form migration test. Supersedes the two 2026-06-02 parametric drafts.
**Keywords:** lisp-frontend, parametric, type-system, structural-constraints, specialization, generics, form-migration, backlog-drain
**Use this when:** Designing, reviewing, or migrating generic `.orc` definitions over caller-specific records/unions, or deciding whether a compiler-known stdlib form should migrate onto the generic substrate.

### [Workflow Lisp Compile-Time Parametric Specialization](design/workflow_lisp_compile_time_parametric_specialization.md)
**Description:** Superseded 2026-06-02 draft (historical record) for compile-time parametric specialization; current contract lives in the Workflow Lisp Parametric Type System design.
**Keywords:** lisp-frontend, parametric, specialization, superseded
**Use this when:** Tracing the history of the parametric direction; do not use for current contracts.

### [Workflow Lisp Structural Parametric Constraints](design/workflow_lisp_structural_parametric_constraints.md)
**Description:** Superseded 2026-06-02 draft (historical record) for structural parametric constraints; current vocabulary is owned by the Workflow Lisp Parametric Type System design.
**Keywords:** lisp-frontend, structural-constraints, parametric, superseded
**Use this when:** Tracing the history of the constraint vocabulary; do not use for current contracts.

### [Workflow Lisp Review/Revise Stdlib Parametric Integration](design/workflow_lisp_review_revise_stdlib_parametric_integration.md)
**Description:** Companion target-delta history for the implemented stdlib-owned `review-revise-loop` route, including refactor prerequisites, generic `.orc` expansion, parametric constraints, loop-state prerequisites, bridge retirement rationale, and future extension questions. Current first-tranche behavior lives in the parent frontend specification.
**Keywords:** lisp-frontend, review-revise-loop, stdlib, parametric, bridge-retirement, loop-state
**Use this when:** Auditing why the review/revise loop moved out of compiler-special Python, reviewing remaining optional extensions, or tracing the design-gap sequence behind the current base-spec contract.

### [Workflow Lisp Runtime Closures Boundary](design/workflow_lisp_runtime_closures_boundary.md)
**Description:** Deferred runtime-semantics boundary for principled closures, including sealed closure families, checked dynamic invocation, typed captures, capabilities, source maps, and replay/resume constraints.
**Keywords:** lisp-frontend, closures, runtime-callable, executable-ir, replay, resume
**Use this when:** Evaluating future runtime closure pressure without weakening `ProcRef` or `let-proc`.

### [Lisp ProcRef Partial Application Work Instructions](plans/LISP-PROC-REFS-PARTIAL-APPLICATION/work_instructions.md)
**Description:** Procedural instructions for the focused ProcRef / `bind-proc` implementation tranche, separating the active delta target from the parent frontend baseline.
**Keywords:** lisp-frontend, procref, work-instructions, proc-ref-drain, procedural-prescriptions
**Use this when:** Launching or reviewing the focused ProcRef drain workflow.

### [Workflow Lisp Refactoring Backlog](plans/2026-05-23-workflow-lisp-refactoring-backlog.md)
**Description:** Refactoring backlog for reducing maintenance cost in `orchestrator/workflow_lisp/` while preserving the current compiler architecture, diagnostics, provenance, type safety, effect visibility, and lowering behavior.
**Keywords:** lisp-frontend, refactoring, compiler, typecheck, lowering, diagnostics
**Use this when:** Planning cleanup of the Workflow Lisp frontend implementation without mixing it with missing full-design feature work.

### [Workflow Lisp Refactoring And Retirement Plan Set](plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md)
**Description:** Completed/historical sequencing provenance for the 2026-07-07 Workflow Lisp cleanup and retirement program, including the dead-code/lowering, lowering-fork, typecheck, build split, executor decomposition, drain G8, and certification-retirement tranches.
**Keywords:** lisp-frontend, refactoring, lowering, typecheck, build, executor, drain-migration, historical-provenance
**Use this when:** Auditing the completed 2026-07-07 program or tracing its prerequisite history. The [Procedure-First Roadmap Execution Sequence](plans/2026-07-09-procedure-first-roadmap-execution-sequence.md) is also complete through Stage 8; its successor handoff is not a selector. Do not restart Phase 1.

### [Workflow Lisp Key Migration Parity Architecture](design/workflow_lisp_key_migration_parity_architecture.md)
**Description:** Draft architecture for closing the DSL/compiler/runtime parity gaps that block promoting key `.orc` workflow migrations over YAML primaries, including command-result bundles, review/revise loops, carried findings, reusable state, defaults, and promotion evidence.
**Keywords:** lisp-frontend, migration, parity, command-result, review-revise-loop, resume-or-start
**Use this when:** Planning or reviewing the system changes required before key YAML workflows can be replaced by `.orc` equivalents.

### [Workflow Lisp Runtime Migration Foundation](design/workflow_lisp_runtime_migration_foundation.md)
**Description:** Completed foundation target for Workflow Lisp promotion, covering command/provider structured-output authority, private lowered value transport, strict migration promotion gates, prompt extern source semantics, and generated state/path allocation.
**Keywords:** lisp-frontend, migration, parity, command-output, provider-output, private-values, statelayout, pathallocator, promotion-gate
**Use this when:** Auditing or extending the implemented runtime foundation beneath `.orc` promotion, especially structured-output binding, private value transport, strict parity gates, prompt externs, or generated path ownership.

### [Workflow Lisp Post-Foundation Composition And Stdlib Migration](design/workflow_lisp_post_foundation_composition_stdlib_migration.md)
**Description:** Active post-foundation roadmap after the runtime foundation, now consuming WCC as the accepted compiler substrate for nested-control composition and focused on remaining typed result translation, private executable context bridging, certified adapter/state-transition ownership, typed bundle-publication projection, entrypoint bootstrap/defaults, canonical `resume-or-start` validation, and parent-callable parity promotion.
**Keywords:** lisp-frontend, post-foundation, stdlib, composition, nested-control, private-context, certified-adapters, backlog-drain, parity

### [Workflow Lisp Generic Core, Expression Surface, And Adapter Retirement](design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md)
**Description:** Historical target design whose architectural contracts are now reflected in the Workflow Lisp frontend baseline: a generic runtime core (`RunCtx`, `Resource<TState>`, `Transition<TRequest, TResult>`), minimal total pure-expression surface, typed projection, materialized value views, runtime-native typed transitions, boundary authority classes, stdlib-owned domain contexts, and adapter-retirement policy.
**Keywords:** lisp-frontend, generic-core, expression-surface, pure-projection, transitions, materialized-views, adapter-retirement, boundary-classes, runtime-simplification
**Use this when:** Planning or reviewing the runtime ontology simplification, the pure-expression operator set, adapter retirement evidence, boundary authority classification, or stdlib migration of `with-phase` / `finalize-selected-item` / `backlog-drain`.

### [Workflow Lisp Private Runtime State And Consumer Value Flow](design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md)
**Description:** Governing umbrella for removing runtime/file plumbing from authored `.orc`. Track R's fail-closed default-resume prerequisite is implemented: node-local restore is primary and positive next-record absence permits only one fully validated unique-nearest prior boundary, never an automatic scan past an invalid nearest point. Broader resume-plumbing retirement and Track C consumer rendering remain target work. Typed values and resources remain semantic authority.
**Keywords:** lisp-frontend, resume, checkpoints, rendering, materialized-views, prompts, observability, publish-policy, compatibility-bridges, boundary-cleanup, values-before-artifacts
**Use this when:** Planning or reviewing the combined cleanup of resume-only and render-only path plumbing from Workflow Lisp workflows.

### [Workflow Lisp Runtime-Native Drain Authoring](design/workflow_lisp_runtime_native_drain_authoring.md)
**Description:** Concrete historical reference target / regression checklist for runtime-native drain authoring on a working Design Delta Drain `.orc` family: typed provider request records, private runtime context, consumer-side rendering, typed projections, resource transitions, and certified adapter boundaries. Its family-specific compile certification bundle is retired; current evidence comes from direct owner tests, route readiness, production compile/runtime checks, and the preserved historical promotion report.
**Keywords:** lisp-frontend, drain, runtime-native, typed-values, provider-inputs, private-context, consumer-rendering, resource-transitions, adapter-retirement
**Use this when:** Reviewing the concrete reference-family acceptance target or historical obligations for the Design Delta Drain `.orc` translation; use the drain-migration roadmap and route-readiness registry for current evidence.

### [Workflow Lisp Shared Owner-Lane Prerequisites](design/workflow_lisp_shared_owner_lane_prerequisites.md)
**Description:** Prerequisite ledger split out of the runtime-native drain authoring target: the shared parent-loop, phase-family boundary, and `std/phase` self-hosting capability contracts that gate imported stdlib adoption claims, each with a minimum contract, minimum behavior check, and adoption-claim rule, plus the former Section 9 numbering map.
**Keywords:** lisp-frontend, drain, stdlib-adoption, prerequisites, backlog-drain, gap-drafter, run-item, finalize-selected-item, phase-family, owner-lane
**Use this when:** Checking whether a shared owner-lane capability exists before claiming imported `std/drain`, `std/phase`, or `std/resource` adoption for a workflow family, or resolving a former Section 9.x citation.

### [Workflow Lisp Consumer-Side Rendering](design/workflow_lisp_consumer_side_rendering.md)
**Description:** Predecessor draft for the umbrella target's consumer-rendering track.
**Keywords:** lisp-frontend, rendering, materialized-views, prompts, observability, publish-policy, compatibility-bridges
**Use this when:** You need detailed source notes behind the umbrella target's Track C; use the umbrella target for next-work routing.

### [Workflow Lisp Lexical Execution Checkpoints](design/workflow_lisp_lexical_execution_checkpoints.md)
**Description:** Detailed source note for the umbrella target's private lexical-checkpoint track, including the implemented node-local/unique-nearest-prior default-resume prerequisite and explicit/operator-only older-boundary recovery distinction.
**Keywords:** lisp-frontend, resume, checkpoints, lexical-state, wcc, transitions, idempotency, audit, fail-closed
**Use this when:** You need detailed source notes behind the umbrella target's Track R; use the umbrella target for next-work routing.

### [Workflow Lisp Core Calculus And Compiler Middle-End](design/workflow_lisp_core_calculus_middle_end.md)
**Description:** Accepted compiler architecture for Workflow Lisp lowering in the migrated subset: a minimal core calculus with a real middle-end — ANF normalization, second-class join points, scope/effect/proof analysis, and defunctionalization into the existing validated flat runtime — with WCC schema 2 default for new compiles and legacy schema 1 retained for compatibility.
**Keywords:** lisp-frontend, core-calculus, middle-end, anf, join-points, defunctionalization, composition, lowering
**Use this when:** Planning or reviewing compiler-lane post-foundation work, especially nested structured control, loops, stdlib review/revise composition, returned-variant lowering, route compatibility, or WCC evidence.

### [Lisp Migrate Key Workflows Execution Plan](plans/2026-05-29-lisp-migrate-key-workflows-execution-plan.md)
**Description:** Approved execution-ready plan for the first migration tranche converting `cycle_guard_demo` and the `design_plan_impl_review_stack_v2_call` family to additive Workflow Lisp `.orc` surfaces with compile/dry-run/parity evidence.
**Keywords:** lisp-frontend, migration, workflow-lisp, parity, execution-plan
**Use this when:** Reproducing or reviewing the exact migration scope, file ownership, and required verification checks.

### [Lisp Migrate Key Workflows Execution Summary](plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md)
**Description:** Durable implementation summary for the 2026-05-29 migration pass, including delivered artifacts, verification outcomes, and current parity status against YAML primaries.
**Keywords:** lisp-frontend, migration, execution-summary, parity-status
**Use this when:** You need a concise durable record of what shipped and what parity gaps remain.

### [Dashboard Observability Summary GUI](design/dashboard_observability_summary_gui.md)
**Description:** Design note for the dashboard summary-hub page that renders provider/phase summaries from `RUN_ROOT/summaries/index.json` and links detailed call-frame summaries through safe run-file routes.
**Keywords:** dashboard, observability, summaries, gui, summary-hub
**Use this when:** Reviewing or extending the read-only GUI for generated workflow summaries.

### [DSL v2.14 Variant Surface Decision](design/dsl_v214_variant_surface_decision.md)
**Description:** Durable Phase 1 design note selecting `variant_output` over an `output_bundle.variants` extension for tagged-union output validation while keeping `select_variant_output` separate.
**Keywords:** dsl-v214, variant-output, output-bundle, tagged-union, decision
**Use this when:** You need the authoritative contract-surface decision before Phase 1 runtime implementation or doc alignment.

### [DSL v2.14 Materialization And Variant Draft](design/dsl_v214_materialization_variants_draft.md)
**Description:** Phase 0 reference that inventories the legacy materialization and tagged-union patterns frozen before the public v2.14 runtime release.
**Keywords:** dsl-v214, phase-0, materialization, variant-output, oracle
**Use this when:** You need the current-behavior characterization that future v2.14 implementation work is meant to preserve or intentionally replace.

### [DSL v2.14 Pointer Authority](design/dsl_v214_pointer_authority.md)
**Description:** Phase 1 design note that inventories current pointer surfaces and fixes one authority rule for published relpath artifacts versus compatibility-only pointer shims.
**Keywords:** dsl-v214, pointer-authority, relpath, publishes, compatibility
**Use this when:** You need the authoritative pointer model before Phase 1 runtime implementation or workflow migration decisions.

### [DSL v2.14 YAML Ergonomics And LOC Reduction](design/dsl_v214_yaml_ergonomics.md)
**Description:** Phase 2 follow-up design note for making v2.14 workflows shorter than the legacy stack by keeping JSON bundles native, adding shared variant fields, adding batch materialization, and enforcing LOC regression checks.
**Keywords:** dsl-v214, yaml-ergonomics, loc, variant-output, materialize-artifacts
**Use this when:** Reviewing why the first v2.14 workflow translation increased YAML size or planning the compact v2.14 authoring correction.

### [Minimal NeurIPS v2.14 Behavior Matrix](design/neurips_v214_behavior_matrix.md)
**Description:** Scenario matrix for the primitive and minimal-NeurIPS Phase 0 oracle fixtures, including preserved observations and normalized-away volatile fields.
**Keywords:** neurips, oracle, behavior-matrix, phase-0, fixtures
**Use this when:** Reviewing what the new oracle suites are expected to lock down.

### [Workflow Lisp G6 Verification Gate](workflow_lisp_g6_verification_gate.json)
**Description:** Checked-in verification-gate manifest naming the G6-counted suites, builtin stdlib inventory, and later-tranche routing for unfinished stdlib migration material.  
**Keywords:** workflow-lisp, g6, verification-gate, stdlib, routing  
**Use this when:** You need the authoritative counted-lane definition for G5B/G6 verification or want to confirm whether a builtin stdlib module is `landed`, `stub`, or `pending`.

### [Slide Decks](slides/README.md)
**Description:** Source-controlled teaching slides for workflow and DSL concepts, including a historical Ralph YAML-semantics example and prompt-injection material.
**Keywords:** slides, teaching, yaml, prompt-injection, ralph
**Use this when:** You want a short presentation-style explanation of a workflow concept.

### [Master Spec](../specs/index.md)
**Description:** Normative root of the external contract, including module map, versioning boundaries, and acceptance scope.  
**Keywords:** normative, contract, spec, versioning, conformance  
**Use this when:** You need authoritative behavior definitions.

## Workflow Author Fast Path

If your immediate goal is to write or revise a workflow, use this read order:

1. [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md)
   Why: start with the preferred `.orc` frontend, typed procedures and results,
   current availability boundaries, and the registry-backed copy-safety route.

2. [Workflow DSL and Control Flow](../specs/dsl.md)
   Why: this is the authoritative shared runtime/control-flow contract and the
   historical DSL-version contract lowered from runnable `.orc` source.

3. [Variable Model and Substitution](../specs/variables.md), [Dependencies and Injection](../specs/dependencies.md), and [Providers and Prompt Delivery](../specs/providers.md)
   Why: these three specs cover the authoring details that most often cause broken workflows: substitution rules, dependency injection behavior, and what providers actually receive.

4. [Prompt Index](../prompts/README.md), [Workflow Index](../workflows/README.md),
   plus a registry-approved `.orc` example under [workflows/examples/](../workflows/examples/)
   Why: use the prompt catalog and copy-safe Workflow Lisp examples rather than
   copying historical YAML patterns.

Minimum rule of thumb: if you have only read `docs/index.md`, you can find the
docs; if you have read the four items above, you can usually write an effective
`.orc` workflow without extra repo archaeology. For historical YAML/YML source,
use the [retired-frontend reference](workflow_drafting_guide.md) to translate
its semantics; do not try to execute or resume it.

For new DSL surfaces, macro systems, frontend languages, or reusable workflow
families, also read [Workflow Language Design Principles](design/workflow_language_design_principles.md)
before drafting the feature. It defines the semantic authority model that keeps
new authoring surfaces from becoming shorter versions of brittle YAML.

If the workflow uses inline Python/shell or helper scripts for state, routing,
resource movement, provider-output normalization, or report parsing, also read
[Workflow Command Adapter Contract](design/workflow_command_adapter_contract.md)
before adding or preserving the command boundary.

## Informative Guides (`docs/`)

### [Orchestration Start Here](orchestration_start_here.md)
**Description:** Concept model with terms and boundaries between authoring-time decisions and runtime semantics.  
**Keywords:** terminology, model, boundaries, authoring, runtime  
**Use this when:** Clarifying how queue/policy/runbook/workflow/DSL/step terms relate.

### [Runtime Execution Lifecycle](runtime_execution_lifecycle.md)
**Description:** Runtime sequence details for `when`, preflight, execution, output validation, publish/consume updates, and next-step resolution.  
**Keywords:** runtime-order, step-state, retries, timeout, consume-publish  
**Use this when:** Diagnosing run behavior and state transitions.

### [Workflow Drafting Guide](workflow_drafting_guide.md)
**Description:** Historical YAML/YML translation patterns focused on deterministic handoff and high-signal control-flow gates.
**Keywords:** retired-frontend, historical, yaml, migration, output-contracts, loop-patterns
**Use this when:** Interpreting or translating retired YAML/YML source; do not use it as a runnable authoring guide.

### [Local Workflow Steering](steering.md)
**Description:** Current local steering for the DSL v2.14 backlog-drain run, including selectable and deferred roadmap phases.  
**Keywords:** steering, local-run, roadmap-gate, dsl-v214  
**Use this when:** Running or auditing the local NeurIPS-style backlog workflow.

## Normative Spec Modules (`specs/`)

### [Master Spec Index](../specs/index.md)
**Description:** Entrypoint and authoritative map of all normative modules.  
**Keywords:** master-spec, scope, map, precedence  
**Use this when:** Navigating specs or confirming precedence rules.

### [Workflow DSL and Control Flow](../specs/dsl.md)
**Description:** Full workflow schema and control-flow semantics, including version-gated fields and mutual exclusivity rules.  
**Keywords:** dsl, schema, steps, goto, for_each, artifacts  
**Use this when:** Validating field-level behavior, shared runtime semantics, or historical lowered DSL-version behavior.

### [Variable Model and Substitution](../specs/variables.md)
**Description:** Variable namespaces, substitution locations, escapes, and undefined-variable failure semantics.  
**Keywords:** variables, substitution, namespaces, escaping  
**Use this when:** Debugging unexpected path/command/provider substitutions.

### [Dependencies and Injection](../specs/dependencies.md)
**Description:** `depends_on` dependency resolution plus v1.1.1 injection semantics, ordering, and truncation behavior.  
**Keywords:** depends_on, injection, required, optional, glob  
**Use this when:** Defining file prerequisites or prompt dependency injection behavior.

### [Providers and Prompt Delivery](../specs/providers.md)
**Description:** Provider template contracts, prompt composition order, placeholder substitution, and provider runtime semantics.  
**Keywords:** providers, prompt-composition, argv, stdin, placeholders, managed-jobs
**Use this when:** Creating provider templates or debugging what providers actually receive.

### [Step IO and Output Capture](../specs/io.md)
**Description:** Capture modes (`text|lines|json`), limits, tee behavior, and deterministic output contract enforcement behavior.  
**Keywords:** output-capture, stdout, json, expected_outputs, output_bundle  
**Use this when:** Choosing step output strictness and debugging capture/parse failures.

### [Run Identity and State](../specs/state.md)
**Description:** `run_id`, `state.json` schema, step status model, and artifact lineage state fields.  
**Keywords:** state-json, run-id, schema, artifact_versions  
**Use this when:** Interpreting run state, resume behavior, or state integrity logic.

### [Queues and Wait-For](../specs/queue.md)
**Description:** Queue directory conventions and `wait_for` behavior, including timeout and polling state fields.  
**Keywords:** queue, wait_for, inbox, processed, failed  
**Use this when:** Authoring filesystem queue flows and blocking wait steps.

### [CLI Contract](../specs/cli.md)
**Description:** Normative commands, flags, safety constraints, and runtime observability CLI controls.  
**Keywords:** cli, run, resume, report, safety, flags  
**Use this when:** Implementing or validating CLI behavior and operational commands.

### [Observability and Status JSON](../specs/observability.md)
**Description:** Debug logging expectations, prompt audit behavior, error context shape, and status JSON conventions.  
**Keywords:** observability, debug, logging, status-json, prompt-audit  
**Use this when:** Adding diagnostics or interpreting runtime visibility artifacts.

### [Security and Path Safety](../specs/security.md)
**Description:** Path safety rules, secret handling, masking guarantees, and environment precedence semantics.  
**Keywords:** security, secrets, masking, path-safety, workspace  
**Use this when:** Reviewing security boundaries and safe path handling.

### [Versioning and Migration](../specs/versioning.md)
**Description:** DSL evolution from v1.1 through current v2.x gates, migration guidance, and planned feature gating notes.
**Keywords:** versioning, migration, v2.13, managed-jobs, provider-session, adjudicated-provider
**Use this when:** Migrating workflows between DSL versions.

### [Acceptance Tests](../specs/acceptance/index.md)
**Description:** Normative acceptance criteria and conformance checklist across all spec modules.  
**Keywords:** acceptance, conformance, validation, test-matrix  
**Use this when:** Verifying implementation correctness against spec obligations.

## Informative Spec Examples (`specs/examples/`)

### [Prompt Management and QA Patterns](../specs/examples/patterns.md)
**Description:** Reusable authoring patterns for prompts, queue coordination, and deterministic QA gating.  
**Keywords:** patterns, prompt-management, qa-gating, workflows  
**Use this when:** Looking for practical multi-step workflow patterns.

### [File Dependencies Example](../specs/examples/file-dependencies.md)
**Description:** Example workflow showing dependency resolution patterns with variables and loops.  
**Keywords:** dependencies, loops, variables, required-optional  
**Use this when:** Building workflows with dynamic file prerequisites.

### [Injection Modes Example](../specs/examples/injection-modes.md)
**Description:** Side-by-side examples of `inject: true`, `list`, `content`, `append`, and no-injection modes.  
**Keywords:** injection, list-mode, content-mode, prompt-assembly  
**Use this when:** Selecting an injection mode for provider steps.

### [Multi-Agent Inbox Example](../specs/examples/multi-agent-inbox.md)
**Description:** End-to-end queue-oriented coordination flow using inbox tasks, loops, and provider steps.  
**Keywords:** multi-agent, inbox, for_each, queue-lifecycle  
**Use this when:** Designing agent queue workflows with explicit task movement.

### [Debugging Example](../specs/examples/debugging.md)
**Description:** Minimal example for diagnosing failed runs via logs and `state.json`.  
**Keywords:** debugging, failures, logs, resume  
**Use this when:** Building quick failure-diagnosis workflow snippets.

## Workflow Runbooks and Examples

### [Workflow Index](../workflows/README.md)
**Description:** Catalog of workflows under `workflows/`, with short purpose summaries and quick pointers for choosing an example.
**Keywords:** workflows, catalog, index, examples, runbooks, managed-jobs
**Use this when:** You need to find the right workflow file before reading or running it.

### [Generic Run Watchdog Workflow Lisp Primary](../workflows/library/generic_run_watchdog/watchdog.orc)
**Route scope:** `new_launch_primary`
**Copy role:** `preferred_current_guidance`
**Description:** Promoted v2.15 Workflow Lisp watchdog that probes an existing orchestrator run, publishes typed evidence, skips provider work for healthy or completed runs, and invokes a selected repair provider only when recovery is needed.
**Keywords:** workflows, watchdog, run-monitoring, repair, resume, v2.15, workflow-lisp
**Use this when:** Starting a new generic watchdog launch; supply the required extern manifests and typed inputs documented in the workflow index.

### [Workflow Examples Directory](../workflows/examples/)
**Route scope:** `reference_only`
**Copy role:** `not_new_author_template`
**New-author route:** [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md)
**Description:** Reference corpus of Workflow Lisp examples and their checked-in inputs; individual route-readiness metadata determines `.orc` copy safety.
**Keywords:** examples, reference-corpus, workflow-lisp, retries, loops, dataflow
**Use this when:** Inspecting `.orc` behavior. Select new-author examples through the route-readiness registry rather than treating every example as a template.

## Testing and Validation

### [E2E Testing Guide](../tests/README.md)
**Description:** Canonical testing guidance for this repo, including targeted pytest usage, collection checks for new tests, and workflow/demo smoke commands.  
**Keywords:** testing, e2e, pytest, verification, smoke-checks  
**Use this when:** Choosing verification commands for workflow, runtime, prompt, and demo changes before merge.

### [Acceptance Criteria](../specs/acceptance/index.md)
**Description:** Canonical acceptance checklist mapped to DSL/runtime/CLI/security contracts.  
**Keywords:** acceptance, normative-tests, obligations  
**Use this when:** Confirming whether a behavior change should be accepted or rejected.

## Backlog and Design History

### [Active Backlog Items](backlog/active/)
**Description:** Active backlog documents with scope/status and linked implementation plans.  
**Keywords:** backlog, active, scope, status  
**Use this when:** Checking what high-priority documentation-driven work is currently in flight.

### [Plans and ADR-Style Notes](plans/)
**Description:** Implementation plans and historical design notes used to track rationale and execution details.  
**Keywords:** plans, adr, history, rationale  
**Use this when:** You need design context behind existing behavior, not normative contracts.

### [Adjudicated Provider Step Design](plans/2026-04-20-adjudicated-provider-step-design.md)
**Description:** ADR for DSL `2.11` adjudicated provider steps, including candidate isolation, evaluator evidence, selection, ledgers, promotion, state, and resume contracts.
**Keywords:** adjudicated-provider, evaluator, candidates, promotion, score-ledger
**Use this when:** You need the design rationale behind the v2.11 adjudicated provider runtime and its V1 constraints.

### [Adjudicated Provider Step Implementation Plan](plans/2026-04-20-adjudicated-provider-step-implementation-plan.md)
**Description:** Implementation plan for the v2.11 adjudicated provider first release, covering DSL validation, isolated candidate workspaces, same-trust-boundary scoring, ledgers, transactional promotion, resume reconciliation, observability, and docs/examples.
**Keywords:** implementation-plan, adjudicated-provider, v2.11, candidates, scoring, promotion, resume
**Use this when:** You need the accepted implementation task breakdown for the adjudicated provider runtime and its verification gates.

### [Major-Project Implementation Escalation Ladder Design](plans/2026-04-26-major-project-implementation-escalation-ladder-design.md)
**Description:** Design for soft implementation-iteration escalation context, upward phase rerouting (`replan`, `redesign`, `roadmap revision`), structured escalation artifacts, and manifest supersession handling in major-project tranche stacks.
**Keywords:** implementation-review, escalation, replan, redesign, roadmap-revision, repeat-until, major-project
**Use this when:** You need the rationale and exact workflow/prompt contract for stopping long implementation churn by escalating to the right upstream phase.

### [Major-Project Implementation Escalation Ladder Implementation Plan](plans/2026-04-26-major-project-implementation-escalation-ladder-implementation-plan.md)
**Description:** Implementation plan for the major-project escalation ladder, including local phase forks, deterministic escalation-state helpers, routing changes, manifest `superseded` handling, prompt assets, and verification.
**Keywords:** implementation-plan, escalation, major-project, workflow-routing, manifest, prompts
**Use this when:** You need the task breakdown and verification checklist for the major-project escalation ladder implementation.

### [Major-Project Escalation Ladder Routing Revision Plan](plans/2026-04-26-major-project-escalation-ladder-routing-revision-plan.md)
**Description:** Revision plan for adjacent-only phase escalation and DSL-valid drain-level roadmap-revision dispatch through a reusable one-iteration workflow.
**Keywords:** implementation-plan, escalation, adjacent-routing, roadmap-revision, drain-iteration, major-project
**Use this when:** You need to revise the major-project escalation ladder so implementation routes to plan, plan routes to design, and design routes to roadmap revision without nested repeat-loop control flow.

### [Repeat-Until Exhaustion Escalation Implementation Plan](plans/2026-04-27-repeat-until-exhaustion-escalation-design-implementation-plan.md)
**Description:** Implementation plan for DSL v2.12 `repeat_until.on_exhausted.outputs`, typed pipeline support, and major-project review-loop non-convergence escalation.
**Keywords:** implementation-plan, repeat-until, v2.12, exhaustion, escalation, major-project
**Use this when:** You need deterministic routing for bounded review loops that fail to converge without treating successful loop iterations as runtime crashes.

### [Roadmap Revision Soft Review Implementation Plan](plans/2026-04-27-roadmap-revision-soft-review-implementation-plan.md)
**Description:** Implementation plan for making major-project roadmap revision review advisory when roadmap revision is the top available authority, while still recording findings and promoting finalized roadmap and manifest candidates.
**Keywords:** implementation-plan, roadmap-revision, advisory-review, major-project, tranche-drain
**Use this when:** You need the rationale and verification path for top-authority roadmap revision phases that should record review findings without blocking the updated roadmap.

## Finding Information

### By Task
- **Understand terminology and boundaries:** [Orchestration Start Here](orchestration_start_here.md)
- **Understand runtime state transitions:** [Runtime Execution Lifecycle](runtime_execution_lifecycle.md)
- **Author or refactor workflows:** [Workflow Author Fast Path](#workflow-author-fast-path)
- **Clarify `depends_on` vs `consumes`:** [Dependencies](../specs/dependencies.md) + [DSL](../specs/dsl.md) + [Versioning](../specs/versioning.md)
- **Check queue ownership and wait behavior:** [Queue Spec](../specs/queue.md)
- **Debug a failed run:** [Observability](../specs/observability.md) + [State](../specs/state.md) + [Debugging Example](../specs/examples/debugging.md)
- **Validate conformance:** [Acceptance Index](../specs/acceptance/index.md) + [tests/README](../tests/README.md)

### By Audience
- **Workflow authors:** [Workflow Author Fast Path](#workflow-author-fast-path)
- **Runtime operators:** [CLI](../specs/cli.md), [Runtime Lifecycle](runtime_execution_lifecycle.md), [Observability](../specs/observability.md)
- **Spec/contract reviewers:** [Master Spec](../specs/index.md), [Acceptance](../specs/acceptance/index.md), [Versioning](../specs/versioning.md)

---

*Last updated: July 2026*
*Style: detailed catalog with descriptions, keywords, and task-oriented navigation*
