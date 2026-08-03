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
| Migration promotion | "If a `.orc` workflow compiles and dry-runs, it can replace a historical YAML primary." | Historical promotions required explicit behavioral evidence. Current route claims come from the route-readiness registry and direct owner tests; preserved parity reports are frozen history, not a live generator input. | [Workflow Lisp Key Migration Parity Architecture](design/workflow_lisp_key_migration_parity_architecture.md), [Workflow Language Design Principles](design/workflow_language_design_principles.md), [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md) |
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
- For a historical promotion decision, read the frozen
  [Workflow Lisp Key Migration Parity Architecture](design/workflow_lisp_key_migration_parity_architecture.md);
  use route readiness and direct owner tests for current claims.

### When Auditing Historical YAML-To-`.orc` Migrations

- Start with [Workflow Lisp Key Migration Parity Architecture](design/workflow_lisp_key_migration_parity_architecture.md).
- Read [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md) and
  [Workflow Language Design Principles](design/workflow_language_design_principles.md).
- Check the relevant runtime specs and preserved reports for the behavior that
  was promoted.
- Treat compile, validation, and dry-run as current regression evidence, not a
  request to regenerate the retired manifest/report gate.

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
**Use this when:** Auditing the completed numbered stages or the provenance of the post-Stage-8 handoff. Do not use this historical roadmap to select current work; E-series shape and sequencing are owned by the incorporated evolution follow-on roadmap.

### [Workflow Lisp Language Quality And Domain Semantics Roadmap](plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md)
**Description:** Completed post-Stage-8 roadmap with two bounded series: Q0–Q5 and L0–L5 are complete. Q4's concrete `review_revise_design_docs` panel consumer is bound to current target-2.23 phased production, a target-2.23 explicit-composed sibling, and a frozen target-2.21 compatibility control. Its original design is accepted at `d7fe4549`, its Q5-era design amendment is accepted at `3c21ceb4`, and its reviewed amended plan `0f21636b` governs; Q4 closed at commit `f3335637b90feb0a87ac4c538bafac7704ac0d87`, tree `ccec170be8757c9e4fd5ed8ece6f93b04fc03299`, under external closure-record SHA-256 `85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c` after ordered Task-9 then final specification/quality approvals and a 74-pass postcommit control. Q5 is complete at `70f4a759`, tree `fec729cb`, after external ordered final reviews. L4 closed at commit `251d9d53674e863fddae4535ea4f7022914287cd`, tree `e2417d395cbcabe9adaffb136759ebff3d42b677`, under external closure-record SHA-256 `94b47f87035549191d698c63bf93b706740791d1e3ec45a29750e662fa4bf804` after accepted editor evidence and ordered design reviews, its reviewed implementation plan, current-only diagnostic publication, capability-gated progress, and Task 4 focused 356 passed and broad comparison has zero new failures after `L4_TASK4_SPEC_APPROVED` then `L4_TASK4_QUALITY_APPROVED`, followed by `L4_FINAL_SPEC_APPROVED` then `L4_FINAL_QUALITY_APPROVED`.
MR-4 closed L3's compile-path-reentrancy prerequisite, and L3 completed over
MR-4 under its reviewed plan.
L0 reliability/actionability, L1 authored symbols/signatures, L2 recovery-safe
static completion, L3 immutable per-source entry selection, L4 diagnostic
lifecycle and compile progress, and owner-reordered L5 authored reference
navigation are complete.
**Keywords:** workflow-lisp, completed-roadmap, value, prompt-calculus, prompt-identity, judgments, lsp, diagnostics, navigation, editor-tooling, principle-29
**Use this when:** Auditing the completed Q/L sequence. Q4 and Q5 are historical complete at the exact commit/tree and external ordered review records above; no Q-series gate remains. M1 remains outside Q4. L4 is historical complete at its exact commit/tree and external ordered review record above. Do not select E0 or any E-series implementation from this route — E sequencing and gates live in the incorporated evolution follow-on roadmap — nor shelved parsimony candidates or P1–P5.

### [Substrate Maintenance And Persistence Parsimony Track](plans/2026-07-26-substrate-maintenance-track.md)
**Description:** Active parallel substrate track. M0 is historical complete at `f15b888d`; M1 is historical complete at `57c2604e`, tree `fc0fdbef`, with its ordered reviews and postcommit selector closed. Phase ML is historical complete: ML-1 at `9c14dae3`, tree `0b149f96`; ML-2 at `b8783f66`, tree `b833b03c`; and ML-4 Tasks 1–4 at `c45928f4`, `b3370858`, `ed19624c`, and `758c67e0`. M2 component (a) is historical complete through `159a8f5e`, `5644bd73`, and `cf0490d1`, with completed-resume compatibility correction `ce02cd17`, a 9,868-pass broad gate, and ordered final reviews. Its [Pure-Result Replay design](design/workflow_lisp_pure_result_replay.md) is the accepted M2 component (a) design and current M3a policy owner. M3a is historical complete at `76427bde`, tree `c5d8247a`, after its Task 4 cache-witness/cursor correction, 968 focused and 9,896 broad non-security tests, ordered final review, and a 189-pass postcommit control. MC implementation and precommit evidence are complete through reviewed correction `a15c3862`, including a 2,673-pass owner union and 10,111-pass broad gate; Task 6 terminal status is resolved only by its deterministic external record. MR-4 is historical complete at `836721ce`; every other MR tranche remains unselected, and no successor substrate tranche is selected. Phase ME (lean-pilot apparatus retirement and removal) is tracked 2026-08-01, gated on the E-series canonical `PASS_E2`, and unselected.
**Keywords:** workflow-lisp, substrate, maintenance, persistence, roadmap, m0, m1, ml, mc, me, common-helpers, at-least-once, retirement, lean-pilot
**Use this when:** Auditing completed MC implementation, its reviewed compatibility correction, and its external terminal-status record from the [MC plan](plans/2026-07-30-mc-common-helper-consolidation-component-plan.md), or auditing substrate work beside the completed Q/L roadmap. A valid named external record means MC is historical complete through its bound commit; an absent, unreadable, or mismatching record means not complete. Phase ML, M2 component (a), and M3a are historical complete. M3a's supported creation policy is implemented for typed public `.orc` new/force-restart roots and fresh non-iterative typed Workflow Lisp children; generic initialization, ordinary resume, existing roots/frames, non-Workflow-Lisp callees, and iteration-owned frames retain their bounded historical behavior. Its Task 4 closure includes the reviewed typed-literal/value-document/sparse-union and cache-witness/cursor corrections, with 122 owner, 259 production-shape, 968 focused, 9,896 broad non-security, and 189 postcommit tests. Component (b), every remaining MR tranche, M3b, M3c, and M4 remain unselected; the missed pre-M3 MR windows require explicit disposition before re-entry. ML-3/provider-isolation and the report/monitor symlink-policy row remain deferred; no successor substrate tranche is selected, and no Q5 or L-series gate is reopened or re-reviewed. Phase ME retirement and removal of the lean-pilot apparatus is tracked and `PASS_E2`-gated; tracking selects nothing, and the frozen pilot control tree plus external A1-v7 evidence root are never mutated.

### [Workflow Lisp Pure-Result Replay](design/workflow_lisp_pure_result_replay.md)
**Description:** Accepted, completed M2 component-(a) design for replacing eligible successful pure-projection values with exact value-free completion shells and reconstructing the values from validated bound inputs and durable effect results.
**Keywords:** workflow-lisp, persistence, resume, replay, pure-projection, m2
**Use this when:** Auditing the M2 replay mechanism or M3a's bounded creation policy. M2 landed through `cf0490d1` with correction `ce02cd17`; M3a root/fresh-frame behavior landed at `3442aef2`, `b931b7b8`, and `8a01bc2b`. The design does not authorize memo-first effect reuse, recurrent/loop replay, component (b), M3b, or M3c.

### [Pure-Result Replay Feasibility Component Plan](plans/2026-07-30-pure-result-replay-feasibility-component-plan.md)
**Description:** Historical-complete record for the reviewed four-implementation-task M2 component-(a) execution plan and its real compiler/state-manager/fresh-executor/new-executor-resume proof, including the transient typed dependency index, atomic value-free shells, audited persistence suppression, and checkpoint-safe replay.
**Keywords:** workflow-lisp, persistence, resume, replay, feasibility, m2, component-plan
**Use this when:** Auditing M2 task commits and executable evidence. Its normal-CLI historical-profile wording records the frozen pre-M3a boundary; current creation policy is owned by the accepted replay design, normative state spec, and separate activation plan.

### [Pure-Result Replay Activation Component Plan](plans/2026-07-30-pure-result-replay-activation-component-plan.md)
**Description:** Historical-complete M3a execution record. Tasks 1–3 landed typed public new-root/force-restart and fresh non-iterative Workflow Lisp child activation plus both-direction boundary locks; Task 4 closed the activation-wide generic replay correction at `76427bde`, tree `c5d8247a`.
**Keywords:** workflow-lisp, persistence, replay, activation, m3a, component-plan
**Use this when:** Auditing the completed M3a activation boundary. Behavior commits are `3442aef2`, `b931b7b8`, and `8a01bc2b`; closure is `76427bde`, tree `c5d8247a`, under external closure-record SHA-256 `fa8530a87a61f484e19ed1b3d5716f6e30b2061efb4ff12769bfc0b6051cf42b`. Existing roots/frames, generic initialization, non-Workflow-Lisp callees, iteration-owned frames, and recurrent pure state retain their bounded historical/durable behavior. The typed-literal/value-document/sparse-union and cache-witness/cursor corrections pass 569-test collection, 968 focused tests, 9,896 broad non-security tests, ordered final review, and a 189-pass postcommit control.

### [MC Common-Helper Consolidation Component Plan](plans/2026-07-30-mc-common-helper-consolidation-component-plan.md)
**Description:** Implementation-complete Phase-MC record for the current-census consolidation of admitted non-security canonical, scalar-validation, status/session-predicate, timeout, and atomic-replacement clones into one small `orchestrator/_common/` package, including reviewed broad-gate compatibility correction `a15c3862`; terminal status is externally resolved.
**Keywords:** substrate, mc, common-helpers, canonical-json, validation, status, atomic-io, component-plan
**Use this when:** Auditing completed MC implementation and Task 6's external-resolution contract. Tasks 0–5 landed through original Task 5 commit `71f61b26`; correction `a15c3862` passed ordered correction reviews, the 2,673-pass owner union, and the 10,111-pass broad rerun. The deterministic external record is the sole authority for ordered final review, exact closure commit/tree, postcommit result, and terminal status. Do not enter report/monitor symlink policy, provider isolation, dashboard, experiments/E-series, WCC middle-end, or any other security surface, and do not select a successor roadmap tranche.

### [M0 Green Baseline Implementation Plan](plans/2026-07-29-m0-green-baseline-component-plan.md)
**Description:** Historical reviewed five-task M0 plan. The exact candidate closed at `f15b888d`, tree `8a75f24f`, after ordered external reviews and a 418-pass postcommit control.
**Keywords:** workflow-lisp, substrate, m0, green-baseline, refusal-diagnostic, routing
**Use this when:** Auditing historical-complete M0. Use the M1 component plan for the current selected substrate tranche.

### [M1 Estate Shrink Implementation Plan](plans/2026-07-29-m1-estate-shrink-component-plan.md)
**Description:** Historical complete M1 execution record. Tasks 0–7 deleted served-purpose retirement, migration, queue, and gate machinery, narrowed bounded compatibility shims, and excluded demo support from wheels; Task 8 reversibly archived 4,168 closed/legacy run directories while retaining six current `.orc` runs; Task 9 and the postcommit selector closed at `57c2604e`, tree `fc0fdbef`.
**Keywords:** workflow-lisp, substrate, m1, estate-shrink, retirement, run-archive
**Use this when:** Auditing historical-complete M1. Route readiness, `frontend_kind` provenance, report/dashboard state views, six current-format nonterminal runs, security surfaces, and frozen YAML-retirement evidence remain outside deletion.

### [Provider At-Least-Once Recovery Component Plan](plans/2026-07-30-provider-at-least-once-recovery-component-plan.md)
**Description:** Historical complete ML-1 execution record at `9c14dae3`, tree `0b149f96`, replacing interrupted ordinary, session, supervision, peer-group, and phased provider quarantine with guarded discard-and-rerun plus the named `provider_attempt_interrupted_rerun` diagnostic.
**Keywords:** provider, recovery, at-least-once, resume, quarantine, ml-1
**Use this when:** Auditing the completed first ML runtime tranche. Preserve completed-result reuse and every source/checkpoint/integrity guard; do not touch provider isolation or security surfaces. ML-2, ML-4, and aggregate Phase ML are historical complete.

### [Provider Attempt Allocator Simplification Component Plan](plans/2026-07-30-provider-attempt-allocator-simplification-component-plan.md)
**Description:** Historical-complete ML-2 execution record replacing per-allocation process locks, repair barriers, and lifecycle ledgers with one run-lifetime writer lock and a plain monotonic counter.
**Keywords:** provider, attempt, allocator, run-lock, persistence, ml-2
**Use this when:** Auditing completed ML-2 after ML-1. Preserve ordinal uniqueness, legacy-state reads, atomic writes, and completed-result reuse; provider-isolation transfer machinery remains excluded. ML-4 and aggregate Phase ML are historical complete.

### [Adjudication Rerun Recovery Component Plan](plans/2026-07-30-adjudication-rerun-recovery-component-plan.md)
**Description:** Historical-complete ML-4 reviewed plan replacing exact-scope adjudication resume mismatch failure with partial-visit cleanup, fresh ordinary dispatch, and `adjudication_state_mismatch_rerun`; Tasks 1–4 landed at `c45928f4`, `b3370858`, `ed19624c`, and `758c67e0`, with closure through the commit containing this record.
**Keywords:** provider, adjudication, resume, recovery, rerun, ml-4
**Use this when:** Auditing historical-complete ML-4 after historical-complete ML-2. Consistent completed visits still reuse; unknown, ambiguous, escaping, or aliased cleanup scope remains fail-closed. Final controls passed 5 E2E, 156 owning adjudication, 3 lock-control (120 deselected), and 9,714 broad non-security tests (19 skipped, 5 warnings).

### [Workflow Lisp Compiler Session State Implementation Plan](plans/2026-07-27-workflow-lisp-compiler-session-state-implementation-plan.md)
**Description:** Reviewed MR-4 component plan for replacing mutable compiler-phase globals with one explicit per-compile session and proving direct-module, linked LEGACY/WCC_M4, and real-process LSP reentrancy.
**Keywords:** workflow-lisp, compiler, session-state, reentrancy, lsp, mr-4
**Use this when:** Auditing the completed MR-4 prerequisite for L3. L3 selection and per-source entry policy live in the completed Q/L roadmap and language-server design.

### [`.orc` Effectiveness Lean Pilot Design](superpowers/specs/2026-07-26-orc-effectiveness-lean-pilot-design.md)
**Description:** Historical-complete exploratory apparatus and A1-v7 evidence record. One smoke and exactly three valid live blocks completed under lock digest `b8d69ba2f3d2b2e7bc6d9181d776db0b7abacd2035f851cd44be613dac6d8503`; the authoritative summary digest is `153263159d6516d032be83bd8f53954be0ba05b39af58be23d1abdca34085e89`. Its deterministic [report](reports/2026-07-26-orc-effectiveness-lean-pilot.md) passed [final evidence review](../artifacts/review/lean-pilot-a1-v7-final-evidence-review.md), and the [owner-decision handoff](reports/2026-07-31-orc-effectiveness-lean-pilot-owner-decision.md) records `PROCEED_TO_E0_ACTIVATION`.
**Keywords:** orc, effectiveness, experiment, lean-pilot, a1-v7, evidence, owner-decision
**Use this when:** Auditing the completed [implementation plan](superpowers/plans/2026-07-26-orc-effectiveness-lean-pilot.md), [Task-7 readiness amendment](plans/2026-07-27-orc-effectiveness-lean-pilot-task7-readiness-amendment.md), or [a1-v5 incident recovery](plans/2026-07-27-lean-pilot-a1-v5-review-citation-incident-recovery.md). The evidence is exploratory only: `DIRECT` won 3/3 against `ORC`, while `ORC` was viable in 1/3. No pilot run was resumed or rerun. The handoff authorizes E0 activation only; it is not a favorable-effectiveness claim or automatic E1+ authorization.

### [Lean Pilot Forensics And Post-E2 Study Inputs](reports/2026-08-01-lean-pilot-forensics-and-e2-study-inputs.md)
**Description:** Post-hoc forensic report (2026-08-01) on the A1-v7 lean pilot: all four `PROTOCOL_FAILURE` arms died on one identical discover-phase product-manifest guard event over ambient `.pytest_cache` bytes; the `DIRECT` 3/3 headline decomposes into two apparatus forfeits plus one maintainability preference between products that both passed hidden acceptance at full score. Records the QA-placement factorial arm set (DIRECT; design-QA with single-shot implementation; product-QA; rich topology), acceptance-floor, hygiene, accounting, and F1 task-selection inputs for the post-`PASS_E2` study program.
**Keywords:** lean-pilot, forensics, protocol-failure, pytest-cache, e2, fixed-study, study-design, effectiveness
**Use this when:** Reviewing the E3-gating first fixed study, preregistering any post-`PASS_E2` effectiveness study, or interpreting pilot treatment-failure accounting. It changes no locked pilot record and amends no accepted plan; the E2 Task-10 arm set stays owned by the [E2 plan](plans/2026-08-01-workflow-lisp-e2-trial-component-plan.md).

### [Workflow Lisp Evolution Follow-On Roadmap](plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md)
**Description:** Tracked E-series program roadmap (incorporated 2026-07-30): records the accepted E0 [trial-runs design](design/workflow_lisp_trial_runs.md), its accepted [typed-program-gates companion](design/workflow_lisp_typed_program_gates.md), the now-satisfied lean-pilot Layer-0 owner-handoff prerequisite, the E/M sequencing prerequisites, and the [2026-07-31 E1-E3 owner selection](plans/2026-07-31-workflow-lisp-e1-e3-owner-selection.md). The designs passed ordered `E_DESIGNS_SPEC_APPROVED` then `E_DESIGNS_QUALITY_APPROVED`. The historical E0–E5 proposal is retained only as reference; the current canonical mapping is E0 direct control, E1 `run-ref`, E2 trials, and E3 external control.
**Keywords:** workflow-lisp, evolution, variants, trials, genetic-search, prompt-evolution, roadmap, e-series, trial-runs, typed-program-gates
**Use this when:** Checking the E-series shape, gates, and sequencing prerequisites, or tracing the historical proposal. E1-E3 are owner-selected. E0 is complete at `fe7d6f9b`, tree `c20f6fd9`, with `PASS_E0`; E1 is complete at `577715f1`, tree `ef7eacbd`, with `PASS_E1`; and E2 is complete within the exact target-2.25 [component plan](plans/2026-08-01-workflow-lisp-e2-trial-component-plan.md) at `8aad035d`, tree `aafa31c`, with `PASS_E2` after ordered `E2_FINAL_SPEC_APPROVED` then `E2_FINAL_QUALITY_APPROVED`. See the digest-bound [E2 final review](../artifacts/review/e2-trial-final-review.md) (`sha256:03ae6a57fb38f6d2d093004eac0ce851f256da8e19b0ff75d24f9859a5ee2d83`). The exact slice passed 51 tests, precommit and postcommit focused gates each passed 3,557, the real-subprocess smoke passed, the adjacent repair gate passed 249, the broad non-security gate passed 11,403 with 19 skipped and 5 warnings, and the postcommit routing/readiness control passed 112. The fixed study proves the controlled 1/2/2 DIRECT/COORDINATOR/ORC call mechanism, blinded ORC/DIRECT/COORDINATOR presentation, one-of-three classification, all 29 exclusions, the zero-failure success table, and sibling-preserving deterministic COORDINATOR failure. This is mechanism proof only and makes no effectiveness, quality, security, isolation, or sandbox claim. No production `.orc` registry row was added, so route-readiness remains unchanged. The ES [component plan](plans/2026-08-02-workflow-lisp-es-first-effectiveness-study-component-plan.md) is accepted at `27be07e2`, tree `e669471a`, after ordered `ES_PLAN_SPEC_APPROVED` then `ES_PLAN_QUALITY_APPROVED`; see its [plan review](../artifacts/review/es-first-effectiveness-study-plan-review.md). ES Tasks 0–4 are complete and Task 5 is selected: the history-free F1 projection closed at `62a5c72d`, tree `5eb5ca32`, after ordered `ES_TASK1_SPEC_APPROVED` then `ES_TASK1_QUALITY_APPROVED`; see the [Task-1 review](../artifacts/review/es-first-effectiveness-study-task1-review.md). The provider-free F1 task/evaluator package closed at `d24c1818`, tree `5e8f84cb`, after ordered `ES_TASK2_SPEC_APPROVED` then `ES_TASK2_QUALITY_APPROVED`; see the [Task-2 review](../artifacts/review/es-first-effectiveness-study-task2-review.md). Exact metering and decision-lock validation closed at `0d16ca36`, tree `ee6d60eb`, after ordered `ES_TASK3_SPEC_APPROVED` then `ES_TASK3_QUALITY_APPROVED`; see the [Task-3 review](../artifacts/review/es-first-effectiveness-study-task3-review.md). The four provider-free QA-placement workflows closed at `d72c6085`, tree `4e576d09`, after ordered `ES_TASK4_SPEC_APPROVED` then `ES_TASK4_QUALITY_APPROVED`; see the [Task-4 review](../artifacts/review/es-first-effectiveness-study-task4-review.md). Live allocation remains Task-6 owner-adoption gated. Phase ME is parallel and nonblocking. E3 remains gated on fixed-study review, ES results, and a separate reviewed component plan. C1-C3, E2O, the historical registry substrate, and security work remain unselected. E4P is exclusively absorbed by successor Stage Q3.

### [E0 Canonical Direct-Control Component Plan](plans/2026-07-31-workflow-lisp-e0-direct-control-component-plan.md)
**Description:** Reviewed, selected E0-only component plan for one target-2.23 library workflow with typed task/model/effort inputs, exactly one composed provider boundary, a direct `Bool` result, committed-provider-boundary reuse, and accounting-parity conformance against an ordinary one-provider workflow.
**Keywords:** workflow-lisp, e-series, e0, direct-control, provider, accounting, component-plan
**Use this when:** Auditing completed E0 under ordered `E0_PLAN_SPEC_APPROVED` then `E0_PLAN_QUALITY_APPROVED`. E0 is complete at `fe7d6f9b`, tree `c20f6fd9`, with `PASS_E0`; see the [final review](../artifacts/review/e0-direct-control-final-review.md). The plan created no new DSL target, runtime, loader, state, trial, child-run, controller, or historical evolution-selector machinery. At E0 closure, E1 still required a separate owner decision; that decision now exists in the [current E1-E3 selection record](plans/2026-07-31-workflow-lisp-e1-e3-owner-selection.md), while the E0 plan remains historical.

### [E1 `run-ref` Component Plan](plans/2026-07-31-workflow-lisp-e1-run-ref-component-plan.md)
**Description:** Reviewed, owner-selected target-2.24 plan for exact pinned-revision `run-ref` child execution in compiled-bundle and clone-path modes, with all transportable values, deterministic workspace/accounting evidence, and at-least-once discard/reuse semantics.
**Keywords:** workflow-lisp, e-series, e1, run-ref, child-run, git, component-plan
**Use this when:** Auditing E1's compiler-hermeticity, child-run, end-to-end, and final-gate proofs. The plan was accepted at `0c392ac9`, tree `3a55ac5f`, after ordered `E1_PLAN_SPEC_APPROVED` then `E1_PLAN_QUALITY_APPROVED`; see the [plan review](../artifacts/review/e1-run-ref-plan-review.md). Tasks 0–9 are complete and target 2.24 `run-ref` has `PASS_E1` at `577715f1`, tree `ef7eacbd`, after ordered final reviews; see the [final review](../artifacts/review/e1-run-ref-final-review.md). E2 is eligible only for its separate reviewed plan; E3 remains predecessor- and study-gated.

### [E2 `trial` Component Plan](plans/2026-08-01-workflow-lisp-e2-trial-component-plan.md)
**Description:** Reviewed owner-selected target-2.25 plan for bounded concurrent E1 `run-ref` arms, coordinator-owned single-writer evidence, blinded evaluation, deterministic checks, crash reconciliation, and a digest-bound verdict artifact.
**Keywords:** workflow-lisp, e-series, e2, trial, run-ref, concurrency, blinding, adjudication, component-plan
**Use this when:** Auditing E2 under the exact reviewed plan at `c6046d38`, tree `40c533fc`, after ordered plan reviews and the unchanged final candidate at `8aad035d`, tree `aafa31c`, after ordered `E2_FINAL_SPEC_APPROVED` then `E2_FINAL_QUALITY_APPROVED`. Tasks 0–10 and the canonical exit are complete with `PASS_E2`; see the [plan review](../artifacts/review/e2-trial-plan-review.md) and digest-bound [final review](../artifacts/review/e2-trial-final-review.md) (`sha256:03ae6a57fb38f6d2d093004eac0ce851f256da8e19b0ff75d24f9859a5ee2d83`). The exact slice passed 51 tests; precommit and postcommit 77-module focused gates each passed 3,557; the real-subprocess smoke passed; the adjacent repair gate passed 249; the corrected broad non-security gate passed 11,403 with 19 skipped and 5 warnings; and the postcommit routing/readiness control passed 112. Its DIRECT/COORDINATOR/ORC fixed study uses identical controlled inputs and 1/2/2 provider calls, presents the blinded order ORC/DIRECT/COORDINATOR, yields one-of-three packet-byte classification, rejects all 29 forbidden identity fields, records an all-zero success table, and retains deterministic COORDINATOR launch failure while siblings finish. This is mechanism proof only; no effectiveness, quality, security, isolation, or sandbox claim is made. E2 added no production `.orc` registry row and route-readiness remains unchanged. ES's component-plan gate is satisfied at reviewed candidate `27be07e2`; Tasks 0–4 are complete and Task 5 is selected under the [Task-4 review](../artifacts/review/es-first-effectiveness-study-task4-review.md), after Task 4 closed at `d72c6085`, tree `4e576d09`, with ordered `ES_TASK4_SPEC_APPROVED` then `ES_TASK4_QUALITY_APPROVED`. Results and final review remain pending. Phase ME is parallel and nonblocking. E3 remains gated on fixed-study review, ES results, and a separate reviewed component plan. The historical registry/handle E2 proposal, E2O, C1-C3, and security work remain unselected; existing exclusions are unchanged.

### [ES First Effectiveness Study Component Plan](plans/2026-08-02-workflow-lisp-es-first-effectiveness-study-component-plan.md)
**Description:** Reviewed post-`PASS_E2` component plan for one preregistered four-cell QA-placement study over the frozen F1 task, with a history-free source projection, exact provider receipts, hard evaluation, blinded integrated judgment, and a deterministic E3-readiness result.
**Keywords:** workflow-lisp, e-series, es, effectiveness, qa-placement, f1, preregistration, trial, metering, component-plan
**Use this when:** Executing or auditing ES under reviewed candidate `27be07e2`, tree `e669471a`, after ordered `ES_PLAN_SPEC_APPROVED` then `ES_PLAN_QUALITY_APPROVED`; see the [plan review](../artifacts/review/es-first-effectiveness-study-plan-review.md). Tasks 0–4 are complete and Task 5 is selected. The history-free F1 projection closed at `62a5c72d`, tree `5eb5ca32`, after ordered `ES_TASK1_SPEC_APPROVED` then `ES_TASK1_QUALITY_APPROVED`; see the [Task-1 review](../artifacts/review/es-first-effectiveness-study-task1-review.md). The provider-free task/evaluator package closed at `d24c1818`, tree `5e8f84cb`, after ordered `ES_TASK2_SPEC_APPROVED` then `ES_TASK2_QUALITY_APPROVED`; see the [Task-2 review](../artifacts/review/es-first-effectiveness-study-task2-review.md). Exact metering and decision-lock validation closed at `0d16ca36`, tree `ee6d60eb`, after ordered `ES_TASK3_SPEC_APPROVED` then `ES_TASK3_QUALITY_APPROVED`; see the [Task-3 review](../artifacts/review/es-first-effectiveness-study-task3-review.md). The four provider-free QA-placement treatment workflows closed at `d72c6085`, tree `4e576d09`, after ordered `ES_TASK4_SPEC_APPROVED` then `ES_TASK4_QUALITY_APPROVED`; see the [Task-4 review](../artifacts/review/es-first-effectiveness-study-task4-review.md). Tasks 5–6 remain provider-free implementation/prelaunch work. The proposed scientific thresholds are not owner-adopted by plan approval, so no provider-bearing attempt may run until the exact frozen Task-6 lock is personally adopted by Ollie or he explicitly delegates that specific scientific decision. ES selects neither E3 implementation nor any superseded experiment substrate.

### [LSP Frontend Prerequisites P-Series Roadmap](plans/2026-07-30-lsp-frontend-prerequisites-p-series-roadmap.md)
**Description:** Tracked P-series roadmap (2026-07-30): P1 diagnostic accumulation, P2 reader recovery, P3 span-to-type metadata, P4 source overlays, and P5 compile caching/incrementality, sequenced after the E program. Technical definitions stay owned by the language server design; no P item is selected by listing. Owner-slated behind E by the [2026-08-01 slating record](plans/2026-08-01-workflow-lisp-p-series-owner-slating.md).
**Keywords:** workflow-lisp, lsp, language-server, frontend, prerequisites, p-series, hover, incrementality, diagnostics, roadmap
**Use this when:** Checking P-series tracking, ordering, entry conditions, or gates. P selection requires E-program completion (or an explicit owner closure/re-park decision), a language-server design amendment, and a reviewed component plan; owner acceleration is the sole early path. The slating record queues P as E's successor program without selecting any item.

### [Workflow Lisp Recursion REC-Series Roadmap](plans/2026-08-01-workflow-lisp-recursion-rec-series-roadmap.md)
**Description:** Completed recursion/ergonomics program (2026-08-01): REC0 measured a 77% code reduction rewriting the pilot ORC treatment at the current surface ([reviewed report](reports/2026-08-01-workflow-lisp-rec0-residual-measurement.md), [review](../artifacts/review/rec0-residual-measurement-review.md), compile-verified artifact), leaving immaterial REC1 fuel-bounded-self-call and REC1b record-spread residuals; [Gate REC0](plans/2026-08-01-workflow-lisp-gate-rec0-decision.md) recorded `STOP_REC_SUGAR`, completing the program. REC2 stays a historical horizon marker; the report's stdlib `ReviewLoopResult` final-subject amendment and nested-record-return lowering relaxation remain unselected redirect candidates.
**Keywords:** workflow-lisp, recursion, bounded-iteration, loop, ergonomics, frontend, rec-series, roadmap
**Use this when:** Auditing the completed REC program, its Gate REC0 outcome, or the REC0 measurement evidence; consulting the recorded redirect candidates before proposing recursion or record-ergonomics language changes. Item IDs use `REC` because `R1`/`R2` name historical experiment-design tasks.

### [Workflow Lisp Language Server L6 Utility Roadmap](plans/2026-07-31-workflow-lisp-language-server-l6-utility-roadmap.md)
**Description:** Accepted design for successor L6 (2026-07-31): L6a signature/declared-type hover from the L1 catalogs, L6b references as the reverse of the L5 definition index, and L6c a standalone TextMate grammar. The frontend-free, P-independent design was accepted at commit `e7de48e2710dddefbf14717575973b4ce41b5a06`, tree `0a2bb399c10b4242c314f9fcc924cf89f6a6b9b6`, design SHA-256 `3c52e3d0fb9c5683eae80ae3d81aae7d6e75bef71ef72c7daf19e6da1ecee338`, after ordered `L6_DESIGN_SPEC_APPROVED` then `L6_DESIGN_QUALITY_APPROVED`; see the [exact review record](../artifacts/review/workflow-lisp-language-server-l6-design-review.md).
**Keywords:** workflow-lisp, lsp, language-server, hover, references, grammar, l6, roadmap
**Use this when:** Checking the accepted L6 scope, bounds, or activation gate. No implementation is selected. The [L6 utility component plan](plans/2026-07-31-workflow-lisp-language-server-l6-utility-component-plan.md) is accepted at `df2b468c`, tree `f86be7c7`, after ordered `L6_PLAN_SPEC_APPROVED` then `L6_PLAN_QUALITY_APPROVED`; see the [plan review](../artifacts/review/workflow-lisp-language-server-l6-plan-review.md). It selects nothing, and explicit owner activation must name the independently selected unit or units. The completed language-quality roadmap is not reopened by this stage.

### [Procedure-First Reuse Contract](design/workflow_lisp_procedure_first_reuse_contract.md)
**Description:** Accepted boundary and migration contract: workflows own durable public run/resume/invocation/publication identity, while typed procedures are the normal internal reuse unit with explicit lowering and caller-visible effects.
**Keywords:** workflow-lisp, procedures, workflows, reuse, effects, lowering, migration
**Use this when:** Deciding whether a reusable unit remains a workflow, becomes a procedure, or must wait for identity/effect evidence.

### [Procedure-Migration Identity Compatibility](design/workflow_lisp_procedure_migration_identity_compatibility.md)
**Description:** Accepted strict-default compatibility contract with a bounded, evidence-only internal identity-retirement class. Its runtime prerequisites remain implemented and exactly one reviewed internal pilot is complete; M1 retired the served-purpose record/scanner generator, so that implementation and the pilot artifacts are historical evidence rather than a current execution route.
**Keywords:** procedure-first, migration, identity, checkpoint, resume, compatibility, retirement
**Use this when:** Deciding whether a procedure migration must preserve identities exactly or wait for a general atomic upgrader, and when auditing the one historical reviewed retirement. Do not infer that the retired generator provides a current route for a new retirement.

### [Procedure-Migration Identity Compatibility Prerequisites Plan](plans/2026-07-13-procedure-migration-identity-compatibility-plan.md)
**Description:** Historical completed plan for generic lowering-identity, inline checkpoint/provenance, retirement-evidence, and checksum-rejection prerequisites; its final pilot handoff is `f5adcb79`, while M1 later retired the served-purpose evidence generator and preserved its artifacts.
**Keywords:** procedure-first, prerequisites, lowering, checkpoint, provenance, checksum
**Use this when:** Reviewing the completed Stage-5 prerequisite gate or its handoff to the tracked-plan pilot; do not re-execute it.

### [Tracked-Plan Procedure-First Pilot](plans/2026-07-13-procedure-first-pilot-plan.md)
**Description:** Completed first reviewed-internal-identity-retirement pilot. Evidence landed at `63e03330`, `e6a85cb7`, `de522c76`, `f5dbac88`, `76205d4f`, and `0769e837`; holistic specification and quality reviews approved HEAD `0769e837`. It retains exactly two completed dedicated runs and does not claim general cross-source compatibility, family migration, promotion, or YAML retirement.
**Keywords:** procedure-first, pilot, tracked-plan, retirement, attestation, quiescence
**Use this when:** Reviewing the completed Stage-5 pilot gate, its exact source-edit boundary, or its narrow evidence-only claim limits; do not re-execute it.

### [Procedure Identity Store Match-Scoped Counts Plan](plans/2026-07-14-procedure-identity-store-match-scoped-counts-plan.md)
**Description:** Historical completed corrective prerequisite whose generic scanner and record-layer changes landed at `e43461f9` and `5f382401`: match-scoped nonterminal and query-derived old-consumer counts gated the one pilot, whose corrected evidence and incident recovery are committed at `63e03330`. M1 removed that served-purpose scanner/record implementation.
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
**Description:** Implemented generic functional contract for typed required and optional exact relpaths on `provider-result`, deterministic bounded content injection, one immutable per-attempt snapshot, counter-only attempt allocation under the run-lifetime writer lock, and content-free evidence. Runtime plan remains topology-only and evidence is non-authoritative. The retired YAML twins supplied historical parity evidence for the promoted `verified_iteration_drain` and `generic_run_watchdog` `.orc` routes before deletion.
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

**Current status:** Stages 6–8 and the selected target-2.18 list-traversal interstage are complete. Provider-supervision v1 closed Gate S7-v1 through `4d4f05c7`; cooperative peer messaging v1.1 closed Gate S7-v1.1 through `b08c04a6` plus Task 12's documentation, verification, and ordered `TASK12_FINAL_SPEC_APPROVED` / `TASK12_FINAL_QUALITY_APPROVED` reviews. The bounded structurally typed list surface is implemented under principle 29. Language-server v1 closed Gate S8 under its reviewed nine-task implementation plan. The completed language-quality roadmap records Q0–Q5 and L0–L5 complete. L4 closed at commit `251d9d53674e863fddae4535ea4f7022914287cd`, tree `e2417d395cbcabe9adaffb136759ebff3d42b677`, under external closure-record SHA-256 `94b47f87035549191d698c63bf93b706740791d1e3ec45a29750e662fa4bf804` after ordered `L4_FINAL_SPEC_APPROVED` then `L4_FINAL_QUALITY_APPROVED`. Q5 is complete at `70f4a759`, tree `fec729cb`, after the post-correction broad comparison and external ordered final reviews; stop `3fc3a09e` remains superseded history. The consolidated lineage is now canonical. Q4's accepted design amendment keeps production target 2.23 phased, adds a target-2.23 explicit-composed sibling, and preserves the frozen target-2.21 control; Q4 is complete at commit `f3335637b90feb0a87ac4c538bafac7704ac0d87`, tree `ccec170be8757c9e4fd5ed8ece6f93b04fc03299`, under external closure-record SHA-256 `85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c`, with its ordered reviews and 74-pass postcommit control closed.

**Current substrate status:** M0 is historical complete at commit
`f15b888d0c4862f7e229b990255d5f34c7392591`, tree
`8a75f24fde68b657d2f84b28aa8b4d34df5089cf`, under the reviewed
[M0 Green Baseline Implementation Plan](plans/2026-07-29-m0-green-baseline-component-plan.md)
and external closure-record SHA-256
`88f35cdd872ba9e5a9602d3e756ee81e2911c2384e74c6fa2388cdb907e2ba0e`;
its postcommit control passed 418 tests. M1 is historical complete at commit
`57c2604e595d22dc9d9d656409607f81b332b5f8`, tree
`fc0fdbefe2cdd99cf0f9de604aa63582f79425ea`, under the
[M1 Estate Shrink Implementation Plan](plans/2026-07-29-m1-estate-shrink-component-plan.md);
its ordered final reviews and postcommit selector passed. Phase ML is
historical complete. [ML-1 recovery](plans/2026-07-30-provider-at-least-once-recovery-component-plan.md)
closed at commit `9c14dae37310755bd9cbd3de03b9256433acd9fe`, tree
`0b149f96ace8873b0381a4cd530468b1d24a083f`; its postcommit control passed 72
tests. [ML-2 allocator simplification](plans/2026-07-30-provider-attempt-allocator-simplification-component-plan.md)
closed at commit `b8783f66db4680bdec048e1b54ac14c1ae8b4d1b`, tree
`b833b03cb91396cddf64a12cbbbc8d016cd306ad`.
[ML-4 adjudication recovery](plans/2026-07-30-adjudication-rerun-recovery-component-plan.md)
landed Tasks 1–4 at `c45928f4`, `b3370858`, `ed19624c`, and `758c67e0`, with
final closure through the commit containing this record; its final controls
passed 5 E2E, 156 owning adjudication, 3 lock-control tests with 120 deselected,
and 9,714 broad non-security tests with 19 skipped and 5 warnings. M2 component
(a) is historical complete through `159a8f5e`, `5644bd73`, and `cf0490d1`,
with correction `ce02cd17`; its final broad gate passed 9,868 tests with 19
skipped and 5 warnings, followed by ordered final reviews. Its
[Pure-Result Replay design](design/workflow_lisp_pure_result_replay.md) is
accepted. M3a Tasks 1–3 landed at `3442aef2`, `b931b7b8`, and `8a01bc2b`;
typed public `.orc` new/force-restart roots and fresh non-iterative typed
Workflow Lisp children now select the profile. The Task 4
typed-literal/value-document/sparse-union correction passed ordered review;
the first final quality and restarted final specification reviews then
rejected cache-hit witness/cursor bypasses. Their TDD correction passes 122
owner tests, 259 production-shape tests, 569-test collection, 968 focused
tests, and 9,896 broad non-security tests with 19 skipped and 5 warnings. M3a
is historical complete at commit
`76427bdedbbac300bbd82d45db7fa6e24a770f84`, tree
`c5d8247ab6d47b209d14ee203513a0eda876acb1`, after restarted ordered final
review and a 189-pass postcommit control, under external closure-record
SHA-256 `fa8530a87a61f484e19ed1b3d5716f6e30b2061efb4ff12769bfc0b6051cf42b`.
Component (b) remains evidence-gated and unselected. MC implementation is
complete through Task 5 plus reviewed correction `a15c3862`; its broad gate
passed 10,111 tests and its owner union passed 2,673 tests. Task 6 terminal
status is resolved only by the deterministic external record defined in the
reviewed
[MC Common-Helper Consolidation Component Plan](plans/2026-07-30-mc-common-helper-consolidation-component-plan.md).
MR-4 is historical complete at `836721ce`; every remaining MR tranche, M3b,
M3c, and M4 remains unselected. ML-3/provider-isolation and the report/monitor
symlink-policy row remain deferred; no Q5 or L-series gate is reopened or
re-reviewed. No successor substrate tranche is selected.

**Current procedure-first substrate:** Native returns, typed guidance, the resolved-effect substrate, lowering/checkpoint/provenance prerequisites, generic resume projection-integrity hardening, the bounded migration wave, provider-supervision v1, cooperative peer messaging v1.1, bounded target-2.18 list traversal, prompt-calculus Q0–Q3, and language-server v1 plus its L0 reliability, L1 authored-symbol/signature, L2 recovery-static-completion, L3 per-source-entry-selection, and L5 authored-reference-navigation tranches are implemented and gated. The match-scoped retirement scanner/record implementation and the one reviewed internal pilot are historical evidence after M1, not a current generator route. The wave intentionally retains 32 effect adapters and therefore does not establish universal procedure-first conversion. Its 63 YAML legacy rows completed the Stage-6 deletion queues; no numbered roadmap stage remains active. No current non-numbered substrate tranche is selected; the incorporated E track owns its own unselected gates.

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
**Use this when:** Reviewing the separate, unscheduled process-per-turn session-resume proposal. Q5 phased delivery uses an interactive turn-queue adapter and its own coordinator; neither proposal implements or depends on the other.

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
**Description:** Implemented target-2.19 opt-in, exact, opaque transport-contract top over strict JSON, with public `type: value` / `kind: value`, existing direct-root `__result__` carriage, no envelope, and no implicit conversion to or from narrower source types.
**Keywords:** lisp-frontend, value, json, transport, direct-root, principle-29, target-2.19
**Use this when:** Authoring or reviewing target-2.19+ opaque transport results; `Value` is available for authoring there. Q0 is complete, `Json` remains a distinct non-transportable type, and target-2.20 prompt fragments may use exact `Value` as their default or explicit result.

### [Workflow Lisp Prompt Calculus](design/workflow_lisp_prompt_calculus.md)
**Description:** Implemented target-2.20 Q1 prompt core, target-2.21 Q2 output positions, and target-2.22 Q3 prompt-attempt identity/diagnostics: importable `defprompt`, closed kind-based slots, one `:path :out` role, exact v1/v2 compiled-fragment identity, one-render Q3 traces, content-free functional-v2 evidence, fixed-order comparison, additive prompt-context reports, and compatible completed-boundary resume. Q4 judgment views remain separately owned.
**Keywords:** lisp-frontend, prompts, defprompt, slots, prompt-identity, judgments, principle-29
**Use this when:** Authoring or reviewing the bounded Q1–Q3 surfaces. Q3 adds no call keyword: target 2.22 enables non-authoritative identity evidence and reporting for a direct fragment-backed call. The surface still excludes partial application, runtime prompt values, call-site `:inputs`/`:prompt-dependencies`/`:returns`, optional or dynamic output sets, judgments, and procedure/provider substitution.

### [Workflow Lisp Phased Contract Delivery](design/workflow_lisp_phased_contract_delivery.md)
**Description:** Implemented and closed target-2.23 Stage-Q5 surface under accepted design `872a29af` and reviewed plan `45468c55`. Tasks 1–13 close through `bb67f680`; Task 14 closes at `70f4a759`, tree `fec729cb`, after the post-correction broad comparison and external ordered final reviews. Stop `3fc3a09e` is retained as superseded historical provenance.
**Keywords:** lisp-frontend, prompts, phased-delivery, target-2.23, provider-attention, principle-30, turn-boundary
**Use this when:** Authoring or reviewing explicit phased delivery, its compatibility boundary, or its evidence/runtime machinery. The final exact tree received external ordered `Q5_FINAL_SPEC_APPROVED` then `Q5_FINAL_QUALITY_APPROVED`; the earlier 10,919/42 result remains superseded candidate evidence.

### [Workflow Lisp Phased Contract Delivery Implementation Plan](plans/2026-07-27-workflow-lisp-phased-contract-delivery-implementation-plan.md)
**Description:** Reviewed Q5 execution plan committed at `45468c55` after ordered `Q5_PLAN_SPEC_APPROVED` then `Q5_PLAN_QUALITY_APPROVED`; Tasks 1–13 are complete through `bb67f680`, Task 14 closes at `70f4a759`, and the 2026-07-28 stop record at `3fc3a09e` is explicitly superseded historical provenance.
**Keywords:** lisp-frontend, prompts, phased-delivery, implementation-plan, target-2.23, q5
**Use this when:** Auditing Q5’s reviewed order and ownership. Task 13 records the real attempt-10 pass, focused 2,245-pass gate, ordered reviews, and commit `bb67f680`; Task 14 records the post-correction broad comparison and external final exact-tree reviews at `70f4a759`.

### [Workflow Lisp Prompt Output Positions Implementation Plan](plans/2026-07-26-workflow-lisp-prompt-output-positions-implementation-plan.md)
**Description:** Completed seven-task Q2 TDD record for target-2.21 `:path :out`,
v2 fragment carriage, generic file-plus-structured contract composition,
atomic validation, a real review consumer, resume evidence, and Q3 handoff.
**Keywords:** lisp-frontend, prompt-calculus, output-position, implementation-plan, target-2.21
**Use this when:** Auditing Q2 implementation order, verification, the bounded
Task-7 capture incident, and ordered final reviews. Q2 is shipped; Q3
subsequently closed. Current selection comes from the active
[language-quality roadmap](plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md)
according to its remaining entry gates.

### [Workflow Lisp Prompt Identity Diagnostics](design/workflow_lisp_prompt_identity_diagnostics.md)
**Description:** Implemented target-2.22 Q3 design for content-free,
attempt-scoped role identities, exact composition validation, drift
classification, preparation-failure evidence, and report projection over
direct fragment-backed provider calls.
**Keywords:** lisp-frontend, prompts, prompt-identity, diagnostics, target-2.22, q3
**Use this when:** Auditing or using the implemented
[Q3 plan](plans/2026-07-27-workflow-lisp-prompt-identity-diagnostics-implementation-plan.md),
its direct-fragment-only target boundary, content-free evidence/report schema,
fixed drift order, or compatibility/non-authority guarantees. Q4's concrete
consumer is bound, and its original design and pre-Q5 plan were accepted after
ordered reviews. Q5 Task 14 and the canonical transplant are complete; the
Q5-era Q4 design amendment is accepted at `3c21ceb4`; Q4 is now an implemented
closure candidate under reviewed amended plan `0f21636b`.

### [Workflow Lisp Judgment Views](design/workflow_lisp_judgment_views.md)
**Description:** Implemented Q4 inspection-only design joining validated provider
results to exact Q3 attempt evidence through one generic co-persisted locator,
then deriving deterministic matrices, disagreement tables, and attempt series
without adding workflow authority.
**Keywords:** lisp-frontend, prompts, prompt-identity, judgments, provenance, q4
**Use this when:** Reviewing Q4's accepted result/evidence association,
persisted-surface contract resolution, pure report projection, or the bound
target-2.23 explicit-composed generic-reviewer panel beside current phased
production and its frozen target-2.21 control. The implementation is complete
at commit `f3335637b90feb0a87ac4c538bafac7704ac0d87`, tree
`ccec170be8757c9e4fd5ed8ece6f93b04fc03299`, under external closure-record
SHA-256
`85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c`
and the reviewed amended
[implementation plan](plans/2026-07-29-workflow-lisp-judgment-views-implementation-plan.md)
at `0f21636b`; the postcommit focused control passed 74 tests. The design
amendment is accepted at `3c21ceb4`; Q5 closure and the canonical transplant
are complete; M1 remains outside Q4.

### [Workflow Lisp Judgment Views Implementation Plan](plans/2026-07-29-workflow-lisp-judgment-views-implementation-plan.md)
**Description:** Reviewed amended Q4 execution plan at `0f21636b`, whose
original pre-Q5 bytes were accepted at `fbcba410` and whose accepted design
amendment is at `3c21ceb4`. Tasks 0–9 and their ordered reviews are complete.
The plan has one Task 0 entry gate
followed by nine implementation tasks for normative
contracts, the exact export compatibility gate, the generic WCC
path-expression seam, atomic result locators, persisted-surface contract
resolution, closed reports, the panel consumer, deterministic resume, bounded
real use, and closure.
**Keywords:** lisp-frontend, judgments, provenance, implementation-plan, q4
**Use this when:** Auditing completed Q4. Its reviewed closure is commit
`f3335637b90feb0a87ac4c538bafac7704ac0d87`, tree
`ccec170be8757c9e4fd5ed8ece6f93b04fc03299`, under external closure-record
SHA-256
`85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c`,
and its postcommit focused control passed 74 tests. Q5 Task 14 and canonical
transplant are complete; M1 remains outside Q4.

### [Workflow Lisp Prompt Identity Diagnostics Implementation Plan](plans/2026-07-27-workflow-lisp-prompt-identity-diagnostics-implementation-plan.md)
**Description:** Reviewed execution and closure plan for target-2.22 Q3 compiler
carriage, one-render traces, closed role identity, prelaunch evidence, and
content-free report projection.
**Keywords:** lisp-frontend, prompts, prompt-identity, diagnostics, implementation-plan, target-2.22, q3
**Use this when:** Auditing Q3's task-by-task TDD, compatibility controls,
focused/broad gates, and ordered closure reviews. The implementation is
present; Q4's consumer gate and original design/plan acceptance are complete.
Q5 Task 14 and the canonical transplant are complete; the Q5-era design
amendment is accepted at `3c21ceb4`, and Q4 is complete at
`f3335637b90feb0a87ac4c538bafac7704ac0d87` under reviewed amended plan
`0f21636b`.

### [Workflow Lisp Language Server](design/workflow_lisp_language_server.md)
**Description:** Implemented `.orc` LSP v1 plus L0 reliability/actionability, L1 authored symbols/signatures, L2 recovery-safe static completion, L3 immutable per-source entry selection, L4 current-only diagnostic lifecycle/progress, and L5 authored reference navigation: a read-only stdio consumer of the production Stage-3 compiler with one-probe no-watcher reverse invalidation, structured initialization failures, visible compiler notes/expansion roles, content-keyed pure-projection export reuse, clean-open/save diagnostics, exact direct-call/prompt-head/direct-retained-proc-ref go-to-definition, compiler-owned ten-kind document symbols, namespace-preserving callable/form completion, and exact source-path-to-export selection under one canonical workspace root. L2 gives valid recovery states only the process-frozen form rows with `isIncomplete=true` and no stale callable; L3 replaces the scalar with immutable `entry_workflows`; L4 hides non-current presentation while retaining ownership and emits capability-gated serialized progress; L5 adds only exact authored-to-authored prompt-head and final unexpanded direct-retained proc-ref edges.
**Keywords:** lisp-frontend, lsp, editor-tooling, diagnostics, go-to-definition, language-server, completed-roadmap
**Use this when:** Auditing the implemented compiler/tooling contract. For installation, client initialization, editing behavior, freshness, progress, and current limits, use the [Workflow Lisp Language Server Setup](workflow_lisp_language_server_setup.md). L4 is complete at commit `251d9d53674e863fddae4535ea4f7022914287cd`, tree `e2417d395cbcabe9adaffb136759ebff3d42b677`, under external closure-record SHA-256 `94b47f87035549191d698c63bf93b706740791d1e3ec45a29750e662fa4bf804` after ordered `L4_FINAL_SPEC_APPROVED` then `L4_FINAL_QUALITY_APPROVED`.

### [Workflow Lisp LSP Diagnostic Lifecycle And Compile Progress](design/workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md)
**Description:** Implemented L4 contract for a current-only diagnostic publication
view over retained contribution ownership and one capability-gated,
non-blocking work-done lifecycle per logical serialized compile-pump interval.
**Keywords:** workflow-lisp, lsp, diagnostics, freshness, progress, editor-tooling, l4
**Use this when:** Reviewing implemented L4 semantics and evidence. The design
and plan have their ordered approvals; implementation `11629551` and
`0d5f7009` passed ordered Task 1/2 specification then quality reviews, and
Neovim/docs Task 3 `bdd1e822` passed its ordered reviews. The Task 4 focused
selector reports 356 passed and the broad comparison has zero new failures.
L4 is complete at commit
`251d9d53674e863fddae4535ea4f7022914287cd`, tree
`e2417d395cbcabe9adaffb136759ebff3d42b677`, under external closure-record
SHA-256
`94b47f87035549191d698c63bf93b706740791d1e3ec45a29750e662fa4bf804`
after ordered `L4_TASK4_SPEC_APPROVED` then `L4_TASK4_QUALITY_APPROVED`, followed
by `L4_FINAL_SPEC_APPROVED` then `L4_FINAL_QUALITY_APPROVED`.

### [Workflow Lisp L4 Diagnostic Lifecycle And Compile Progress Implementation Plan](plans/2026-07-28-workflow-lisp-language-server-l4-diagnostic-lifecycle-progress-implementation-plan.md)
**Description:** Reviewed four-task TDD plan for current-only diagnostic
publication, a pure non-blocking progress controller, real stdio and Neovim
acceptance, and exact broad comparison plus closure.
**Keywords:** workflow-lisp, lsp, diagnostics, progress, implementation-plan, tdd, l4
**Use this when:** Executing or auditing L4 task boundaries, controls, ordered
reviews, and acceptance gates. Tasks 1–3 are committed through `bdd1e822`;
repository-real Neovim acceptance passes, the focused selector reports 356
passed, and the broad comparison has zero new failures. Task 4 focused 356
passed and broad comparison has zero new failures after ordered
`L4_TASK4_SPEC_APPROVED` then `L4_TASK4_QUALITY_APPROVED`. L4 is complete at
commit `251d9d53674e863fddae4535ea4f7022914287cd`, tree
`e2417d395cbcabe9adaffb136759ebff3d42b677`, under external closure-record
SHA-256
`94b47f87035549191d698c63bf93b706740791d1e3ec45a29750e662fa4bf804`
after ordered `L4_FINAL_SPEC_APPROVED` then `L4_FINAL_QUALITY_APPROVED`.

### [Workflow Lisp LSP Authored Reference Navigation](design/workflow_lisp_lsp_authored_reference_navigation.md)
**Description:** Implemented and incorporated Stage-L5 authored-to-authored definition-index amendment for prompt application heads plus the feasibility-admitted narrow direct-retained `proc-ref` shape. The exact projection joins original syntax to compiler catalog identity fail closed; macro heads remain null shape-wide, macro-consumed/erased/expanded/generated-owner/specialized-owner proc-refs remain null, direct `(call ...)` navigation is unchanged regression coverage, and WCC/generated calls stay excluded.
**Keywords:** workflow-lisp, lsp, authored-references, go-to-definition, prompt-heads, proc-ref, macro-heads, compiler-retention
**Use this when:** Auditing L5's exact-span/identity projection, common freshness preflight, namespace/visibility cases, closed feasibility disposition, or retained macro/proc-ref gaps. The shipped execution and closure record lives in the [reviewed implementation plan](plans/2026-07-27-workflow-lisp-l5-authored-reference-navigation-implementation-plan.md).

### [Workflow Lisp L5 Authored Reference Navigation Implementation Plan](plans/2026-07-27-workflow-lisp-l5-authored-reference-navigation-implementation-plan.md)
**Description:** Reviewed six-task TDD and closure record for collision-safe five-field reference rows, exact prompt-head and narrowly retained proc-ref joins, visibility and full preflight/null matrices, a repository-real review-workflow stdio gate, and durable baseline/routing incorporation.
**Keywords:** lisp-frontend, lsp, authored-references, prompt-heads, proc-ref, implementation-plan, tdd
**Use this when:** Auditing the shipped L5 implementation boundary, task commits, focused/broad evidence, and ordered reviews. The plan includes only feasibility-admitted prompt heads and direct-retained unexpanded proc-refs in non-generated, non-specialized authored owners; macro heads, erased/macro-consumed/expanded/specialized proc-refs, new direct-call behavior, WCC/generated shapes, and compiler/frontend changes remain excluded.

### [Workflow Lisp Language Server Setup](workflow_lisp_language_server_setup.md)
**Description:** Practical setup and operating guide for the implemented optional `.orc` language server, including installation, `python -m orchestrator.lsp`, one-root initialization, clean-save behavior, freshness/restart rules, closed navigation, and deliberate v1 limits.
**Keywords:** lisp-frontend, lsp, setup, editor, diagnostics, navigation
**Use this when:** Configuring a generic LSP client or interpreting current dirty, pending, failed, invalidated, stale, initialization-failure, no-watcher save, or work-done-progress behavior. L1–L5 are shipped and complete; L4's historical evidence remains in its implementation plan.

### [Workflow Lisp Language Server Implementation Plan](plans/2026-07-25-workflow-lisp-language-server-implementation-plan.md)
**Description:** Completed reviewed nine-task Stage-8 TDD record for exact-byte source tracing, a read-only in-memory build seam, immutable single-root state, diagnostic parity, stdio/watcher transport, compiler-owned callee provenance, closed navigation, packaging, and end-to-end closure.
**Keywords:** lisp-frontend, lsp, implementation-plan, diagnostics, navigation, stage-8
**Use this when:** Auditing Stage-8 implementation order, evidence, and ordered reviews. It is no longer an active selector.

### [Workflow Lisp Language Server L1 Implementation Plan](plans/2026-07-26-workflow-lisp-language-server-l1-implementation-plan.md)
**Description:** Completed five-task L1 TDD record for compiler-owned ten-kind
authored-symbol projection, exact selection spans, namespace-preserving
callable signatures, freshness preservation, and repository-real stdio
closure.
**Keywords:** lisp-frontend, lsp, authored-symbols, signatures, implementation-plan
**Use this when:** Auditing L1 implementation order, evidence, and ordered
reviews. L1 is complete; L2 recovery-safe static completion is also complete
under its own reviewed plan.

### [Workflow Lisp Language Server L2 Implementation Plan](plans/2026-07-27-workflow-lisp-language-server-l2-implementation-plan.md)
**Description:** Completed five-task TDD record for one process-frozen form
registry, a fail-closed recovery-state classifier, full/static/empty completion
wiring, a real stdio recovery-to-full transition, and serialized L2 closure.
**Keywords:** lisp-frontend, lsp, recovery-completion, implementation-plan, tdd
**Use this when:** Auditing L2 implementation order, evidence, or final
reviews. The plan passed `L2_PLAN_SPEC_APPROVED` then
`L2_PLAN_QUALITY_APPROVED`, landed implementation through `10e3ccc3`, and
closed with `L2_FINAL_SPEC_APPROVED` then `L2_FINAL_QUALITY_APPROVED`.

### [Workflow Lisp Language Server L3 Per-Source Entry Selection Implementation Plan](plans/2026-07-28-workflow-lisp-language-server-l3-per-source-entry-selection-implementation-plan.md)
**Description:** Completed three-task TDD plan for the immutable
`entry_workflows` map, exact structured initialization refusals and
source-path lookup, mixed application/library reentrancy, production CLI F2
capture parity, real stdio proof, and shipped-documentation closure.
**Keywords:** lisp-frontend, lsp, entry-selection, per-source, implementation-plan, tdd
**Use this when:** Auditing L3's task-by-task reviews, focused/broad evidence,
and closure. The plan passed `L3_PLAN_SPEC_APPROVED` then
`L3_PLAN_QUALITY_APPROVED`; implementation landed through `fc1b01ee`,
`9e59929d`, and xdist-evidence correction `8c704f3f`, then closed under
`L3_FINAL_SPEC_APPROVED` and `L3_FINAL_QUALITY_APPROVED`.

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
**Description:** Historical architecture for the former manifest-driven promotion gate, preserved with its command-result, review/revise, carried-findings, reusable-state, defaults, and evidence rationale.
**Keywords:** lisp-frontend, migration, parity, historical, command-result, review-revise-loop, resume-or-start
**Use this when:** Auditing a frozen historical promotion decision; use route readiness and direct owner tests for current route claims.

### [Workflow Lisp Runtime Migration Foundation](design/workflow_lisp_runtime_migration_foundation.md)
**Description:** Completed foundation target covering command/provider structured-output authority, private lowered-value transport, prompt extern source semantics, and generated state/path allocation; its manifest-driven promotion-gate tranche is retired history.
**Keywords:** lisp-frontend, migration, historical-parity, command-output, provider-output, private-values, statelayout, pathallocator
**Use this when:** Auditing or extending the implemented structured-output, private-value, prompt-extern, or generated-path baseline.

### [Workflow Lisp Post-Foundation Composition And Stdlib Migration](design/workflow_lisp_post_foundation_composition_stdlib_migration.md)
**Description:** Historical post-foundation roadmap whose landed WCC, composition, and stdlib contracts are incorporated into current component docs. Its generated post-WCC inventory and manifest-driven parity gate are retired.
**Keywords:** lisp-frontend, post-foundation, stdlib, composition, nested-control, private-context, certified-adapters, historical

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
