# Workflow Lisp Procedure-Migration Identity Compatibility

- **Status:** accepted and implemented for generic prerequisites plus exactly
  one reviewed internal pilot; the evidence-only exception remains narrow
- **Kind:** migration architecture decision and compatibility clarification
- **Owner:** Workflow Lisp frontend and runtime-state owners
- **Reviewers:** procedure-first specification review, runtime-state review, and
  the owner of each known state store named by a retirement record
- **Created:** 2026-07-13
- **Last material update:** 2026-07-15
- **Related docs / plans:**
  - `docs/design/workflow_lisp_procedure_first_reuse_contract.md`
  - `docs/design/workflow_lisp_state_layout.md`
  - `docs/design/workflow_lisp_source_map.md`
  - `docs/design/workflow_language_design_principles.md`
  - `docs/plans/2026-07-13-procedure-migration-identity-compatibility-plan.md`
  - `docs/plans/2026-07-14-procedure-identity-store-match-scoped-counts-plan.md`
  - `docs/plans/2026-07-13-procedure-first-pilot-plan.md`
  - `docs/plans/2026-07-13-resume-projection-integrity-hardening-design-plan.md`
  - `specs/state.md`
- **Implementation target:** current selector is the separate resume
  projection-integrity hardening design/planning plan; migration waves remain
  gated behind its resulting implementation

Acceptance establishes the compatibility contract and reviewed implementation
sequence. Generic prerequisite Tasks 1-8 completed at handoff `f5adcb79`. The
tracked-plan pilot then completed through `0769e837`, with exactly two
completed dedicated runs and holistic specification/quality approval. This is
not a general cross-source resume/compatibility, family-wave, promotion, or
YAML-retirement claim, and projection-integrity hardening is not implemented.

## Summary

Procedure-first migrations have two, and only two, identity-compatibility
classes:

1. **Strict compatibility** preserves persisted identities exactly. If a
   live or promoted migration cannot do that, it waits for a separately
   designed, general, atomic state upgrader.
2. **Reviewed internal identity retirement** permits old identities to be
   retired only for an internal callee that is not exported, registered, or
   public; whose containing route is not promoted or live; and that has no
   matching supported live/nonterminal run (a run containing a queried
   old-identity match) or supported consumer of the queried old identities.
   This class requires repository evidence, owner attestation for every known
   state store, retained historical source/build artifacts, a machine-readable
   identity delta, and fresh fail-closed checksum-rejection evidence.

The second class is deliberately not an upgrader. Its retirement record is
evidence only: the runtime does not load it, discover it, or take directives
from it. Old state is not remapped. Resume independently applies existing root
and callee source-checksum validation. Unknown or external stores cannot be
inferred absent from a repository scan or from owner attestation about known
stores.

The four generic prerequisites are implemented: lowering mode is resolved once
and carried by Stage 3; inline checkpoint policy is caller-owned; persisted
source maps connect generated steps to both procedure definition and consuming
call site; and stable retirement evidence plus fail-closed checksum negative
proof exist. The tracked-plan pilot used the reviewed retirement class only
after the prerequisite final reviews and pre-edit store/owner gate passed; its
evidence landed at `63e03330`, `e6a85cb7`, `de522c76`, `f5dbac88`, `76205d4f`,
and `0769e837`. No
prerequisite or compatibility decision may be keyed to this pilot's family,
module, procedure, workflow, provider, or step names.

## Context And Authority

The accepted procedure-first reuse contract remains the source of truth for
the workflow/procedure boundary: workflows own durable public execution
identity; procedures are the normal internal reuse unit. `specs/state.md` is
the normative owner of persisted call frames, step identities, checkpoint
state, resume rejection, and any future state upgrader. The state-layout and
source-map designs own generated state and provenance respectively.

Current repository evidence closes the generic design gaps:

- `compiler.py::_resolve_stage3_procedure_lowering` invokes the shared
  `lowering/procedures.py::_resolve_procedure_lowering` decision once after
  Stage-3 typing/effects. `Stage3CompileResult.typed_procedures`, classic
  lowering, WCC, and `typed_frontend_ast.json` consume that same resolved
  tuple/mapping. The remaining classic iteration-scope inline-to-private
  recheck is explicitly marked schema-1 compatibility behavior, not a
  promotable/default-WCC semantic.
- WCC inline `WccCall` expansion no longer adds a synthetic workflow-call
  checkpoint. The actual inline-body effects own their ordinary checkpoint
  policies, while real workflow/private-workflow calls retain
  `reuse_validated_workflow_call`.
- `TypedProcedureDef.resolved_lowering_mode` and
  `generated_workflow_name` carry the decision through the typed AST and both
  lowerers without a new source annotation.
- WCC inline child contexts merge `_procedure_provenance_notes` through
  `_merge_origin_notes`, so persisted provider, `match`, and checkpoint
  lineage retain procedure-definition and consuming-call-site notes without a
  source-map schema change.
- `orchestrator/workflow_lisp/procedure_identity_retirement.py` provides the
  versioned evidence-only record parser, known-store scanner, and fail-closed
  validator without CLI or runtime coupling. Focused resume tests characterize
  root rejection before executor construction with a byte-identical run tree
  and callee rejection before child execution/remap with ordinary parent
  metadata permitted.
- `specs/state.md` makes call-frame IDs, step IDs, and nested call-frame state
  durable resume/lineage keys and already rejects incompatible older state in
  other schema migrations unless a tested upgrader ships.

The frozen pilot baseline
`tests/baselines/procedure_first/tracked_plan_phase.json` records a real old
call boundary, call-frame/resume nodes, and lexical checkpoint identity for
`tracked-plan-phase`. The procedure-first inventory classifies its authored
call as a procedure candidate with no public-boundary evidence, and the route
readiness registry classifies the containing example as
`migration_evidence_only`. The module exports only the retained public stack
workflow. Those facts make the pilot eligible to seek the narrow class; they
do not by themselves prove that old state has no consumer.

## Problem

Replacing a workflow-as-function call with an inline procedure intentionally
removes a child-workflow boundary. The retained public workflow can keep the
same inputs, outputs, effects, and artifacts while the old call-frame,
checkpoint, node, presentation, and source identities cease to exist. Calling
that result “parity” either forbids all useful internal cleanup or silently
breaks persisted state.

Before this design was accepted, the procedure-first reuse contract resolved
the tension with an unconditional stop whenever a persisted checkpoint
identifier could not be preserved exactly. That pre-acceptance rule correctly
protected public, live, and promoted identities, but it did not yet express the
narrow reviewed-internal retirement class for an evidence-only callee with no
supported old-state consumer. Acceptance commit `61c79cb4` has since landed the
strict-default/retirement-exception qualification in the reuse contract. The
prerequisites and first reviewed pilot are now complete; generalization remains
separately gated.

The pilot exposed generic compiler/runtime defects that could not be accepted
as migration differences. The module-level lowering-mode, inline checkpoint,
and WCC procedure/call-site provenance defects are now corrected. Resume
planning still does not audit every explicit persisted completed-step and
call-frame caller identity against the current state projection; that separate
checksum-compatible projection-integrity gap remains routed outside the pilot.

## Goals And Non-Goals

### Goals

- Define strict compatibility and one narrow retirement exception.
- Keep live/promoted state safe without a pilot-specific remapper.
- Make retirement eligibility reviewable from stable machine-readable
  evidence rather than labels or prose.
- Ensure inline lowering has caller-owned checkpoint and provenance semantics.
- Prove clean execution and interruption/resume under the new identities.
- Route the checksum-compatible projection-integrity gap into a named
  follow-up design and plan that must land before production migration waves.
- Preserve historical source/build artifacts so old runs remain explainable.

### Non-goals

- Designing or implementing the general atomic state upgrader.
- Supporting old-state resume under retired identities.
- Inferring that external stores do not exist.
- Allowing identity retirement for exported, public, promoted, or matching
  supported live/nonterminal old-identity state.
- Adding a family-name-specific compiler/runtime branch or a pilot allowlist.
- Treating compile, dry-run, terminal historical runs, or a repository scan as
  sufficient evidence alone.

## Decision

### Compatibility classes

| Class | Eligibility | Old-state behavior | Required path |
| --- | --- | --- | --- |
| `strict_compatibility` | Default for every migration; mandatory for exported/public boundaries, promoted/live routes, matching supported live/nonterminal runs, or any queried old-state consumer | Persisted identities remain exact and all earlier schema/bundle/lowering/checksum/program-identity guards remain satisfied. Under current checksum semantics, a changed source cannot resume a supported old run without the general upgrader | Preserve identity for parity evidence; if any supported run must cross changed source, stop and wait for the general atomic upgrader |
| `reviewed_internal_identity_retirement` | Callee is not exported, registered, or public; containing route is not promoted/live; retained public wrapper/contract is evidenced; no matching supported live/nonterminal run or queried old-identity consumer exists in every attested known store | The changed pilot source is rejected by the existing root checksum guard before `WorkflowExecutor` construction and without mutation. Existing callee-checksum behavior remains authoritative at the child boundary; ordinary parent-level metadata may already exist, but child state is not remapped | Retain history, review the identity delta, prove new-ID clean/resume behavior, and approve the evidence-only retirement record |

Classification is fail closed. Missing evidence, an unowned known store, an
unknown consumer, or an unsupported assertion selects strict compatibility.
An external store that was not enumerated remains **unknown**, not absent.

### Accepted procedure-first contract amendment

Acceptance commit `61c79cb4` amended
`workflow_lisp_procedure_first_reuse_contract.md` to the following governing
rule:

> A procedure-first migration is strict-compatible by default. If it cannot
> preserve a persisted identity exactly, it must stop unless a separately
> reviewed general atomic state upgrader applies, or the migration satisfies
> the reviewed internal identity-retirement class in this design. The
> retirement exception never applies to exported/public identities,
> live/promoted state, or a supported consumer of the old identity.

The same commit qualified the migration test's persisted checkpoint/resume
identity axis and left all other preserved-contract axes unconditional. These
acceptance changes are already landed. Generic prerequisite Tasks 1-6 are now
implemented with focused evidence; Task 8 final verification/reviews, pilot
evidence, and projection hardening remain unclaimed.

### General upgrader boundary

A general atomic state upgrader remains deferred. It is mandatory whenever a
supported old run must cross a source change, including migrations that
preserve all step/checkpoint identities, because the current root checksum
guard rejects the changed source. It must eventually own source checksum and
program identity, version detection, complete old-to-new validation, atomic
commit, rollback, idempotence, and old/new runtime compatibility. A family
adapter, manual checksum edit, baseline refresh, partial call-frame rewrite, or
alias table is not that upgrader.

A source migration with no supported old run may prove exact identity parity
as migration evidence. That evidence is not a claim that old state resumes
under the changed source.

## Generic Prerequisites Before Any Pilot Retry

### A. Resolve lowering once in Stage 3

After type/effect specialization and before either classic or WCC lowering,
one Stage-3 pass must compute each monomorphic procedure's module-level
resolved lowering mode and generated private-workflow name.
`Stage3CompileResult` must carry those resolved typed procedures, and
`typed_frontend_ast.json` must expose the same decision.

Classic lowering, WCC, source-map construction, Semantic IR construction, and
build serialization must receive that module-level decision unchanged rather
than independently recomputing it. The current classic iteration-scope
inline-to-private recheck is schema-1 compatibility behavior, not a promotable
or default-WCC semantic. The authoritative Stage-3 module resolution governs
WCC migration routes.

Procedure-first migration/promotion must use explicit lowering and reject any
candidate whose behavior would depend on the schema-1 call-local override.
Cross-route characterization must prove that the pilot and a generic explicit-
inline fixture do not trigger that override. A first-class effective-call-site
lowering carrier is deferred until a supported non-legacy route demonstrates
a real need for one; this pilot must not introduce it.

For an unchanged source, normalized comparisons must prove that semantic
projection identities, checkpoint/program-point identities, presentation
keys, and generated private-workflow bytes remain unchanged across the
refactor. Normalize workspace-root/path content before byte comparison; do not
claim that unrelated nondeterministic or absolute-path fields make the entire
executable/runtime JSON byte-identical.

### B. Make inline checkpoint policy caller-owned

An inline procedure invocation creates no child workflow, call boundary, or
call frame. It therefore must not emit a synthetic workflow-call checkpoint
or use `reuse_validated_workflow_call`. Checkpoints arise from the actual
lowered effects in the inline body and are owned by the retained caller:

- provider/command structured outputs use their ordinary validated-output
  policies;
- materialized views and transitions use their ordinary policies;
- a real nested workflow call still uses workflow-call policy; and
- a pure inline body adds no effect-boundary checkpoint merely because a
  procedure was invoked.

The checkpoint source lineage must point through the caller-owned generated
step to the procedure definition and its consuming call site.

### C. Persist definition and call-site notes on WCC

For every executable node generated by inline procedure expansion, the
canonical persisted `SourceMapEntry.notes` must retain the existing provenance
labels for:

- the procedure definition origin; and
- the consuming call-site origin.

Implementation must reuse `_procedure_provenance_notes` and the current
persisted note carrier by propagating origin notes into the WCC inline child
context as classic lowering already does. No new typed source-map schema or
schema version is required for this prerequisite. Tests may inspect the two
note labels in structured `SourceMapEntry.notes`; they must not parse prose to
reconstruct paths, spans, or semantic identity. Checkpoint-point source lineage
must resolve through the same persisted entries without recompiling or reading
mutable source. Missing either note fails promotion-quality build validation.

### D. Stabilize retirement evidence and checksum rejection proof

Implementation must define a versioned JSON retirement record and validate it
as evidence with production build artifacts. It is never runtime authority,
contains no runtime directive, and need not be present or discoverable when a
run resumes.

The pilot's negative old-state prerequisite uses a **root checksum mismatch**
because the `.orc` source changes. A fresh integration test must invoke default
resume against unmodified old state, without observability or CLI override
mutations, and prove rejection before `WorkflowExecutor` construction and any
provider/command execution. The persisted run tree must remain byte-identical:
no state, status, error, `updated_at`, observability/session/process metadata,
sidecar, quarantine, backup, completed-step, `current_step`, call-frame,
checkpoint, artifact, or ledger mutation is allowed. Only process exit status
and stderr may change. The runtime neither loads the retirement record nor
remaps or ignores old state.

A separate characterization test must preserve the existing callee-checksum
contract: a mismatch fails before child workflow or provider/command execution
and does not remap child-state identities. Parent executor construction may
already have occurred, and ordinary parent-level metadata may already exist
under the current runtime contract. Prerequisite D does not require callee
checksum preflight, whole-run-tree byte identity for that path, or an
observability-order refactor.

### Separate runtime-hardening follow-up

Review discovered a broader integrity gap on checksum-compatible resumes:
explicit completed-step and call-frame caller identities are not exhaustively
audited against their scoped current projections. This is not required for the
internal pilot because changed source is rejected earlier by the root checksum
guard.
It must be routed to a named runtime-hardening plan before production migration
waves.

That follow-up's goal is to audit explicit completed/call-frame identities on
checksum-compatible resumes using the applicable scoped projection: retained
entry projection for root state, parent call-boundary projection to select a
callee under existing import/checksum rules, callee projection recursively for
frame-local state, and existing qualified-ancestry APIs for loops. Missing or
ambiguous scoped projection resolution must fail closed. This design does not
specify that hardening's insertion point, state delta, schema change, or
implementation.

These prerequisites are generic. No code or schema may name the tracked-plan
family or select behavior from a module/procedure basename.

## Retirement Evidence Contract

A retirement record uses schema
`workflow_lisp_procedure_identity_retirement.v1` and contains at least:

- migration ID, compatibility class, repository commit, compiler/build
  versions, and retained public entry;
- internal callee identity and evidence that it is neither exported nor
  registered as a supported public entry;
- inventory/source evidence for the reviewed call site and retained public
  wrapper/contract, plus route-readiness labels as supporting routing evidence
  only. A `migration_evidence_only` label is neither mandatory nor sufficient;
- all **known** state-store roots, their owners, scan/query version and time,
  normalized query digest, matching terminal/nonterminal/call-frame counts,
  whole-store terminal/nonterminal totals, and an owner attestation that no
  supported live/nonterminal run or consumer of the queried old identities
  remains in that named store;
- the explicit statement `external_store_absence: not_asserted`;
- content-addressed old and new source snapshots and production build
  artifacts, including typed frontend AST, Semantic IR, executable IR,
  runtime plan, checkpoint points, and source map;
- an old-to-new identity delta covering workflow/call-frame IDs, executable
  node and step IDs, presentation keys, program-point/checkpoint IDs, generated
  state allocations, and source-map origin keys. Each old identity is marked
  `preserved` or `retired`; each new identity is marked `preserved` or `new`.
  Retirement records contain no runtime remap directive and are never inputs
  to resume planning or execution;
- a closed `retired_identity_query_evidence` object that content-addresses the
  frozen pre-edit scan containing `old_identity_query`. Every reviewed
  retirement record carries this binding, even when its production artifacts
  happen to enumerate every reviewed identity. This evidence is the
  authoritative source for the retired side only; it does not replace the
  production-derived preserved or new identities; it supplements the
  production table only for retired domain-qualified rows absent from those
  artifacts. The binding includes the evidence path and digest, query version,
  canonical query-list digest, identity count and exact domain membership map,
  frozen-baseline path and digest, the historical source path recorded by the
  pre-edit query, the retained old-source artifact path, and their one required
  shared digest. The historical and retained paths may differ because the live
  path can contain migrated source after capture; the validator does not reread
  current bytes there. It content-verifies the retained old-source artifact
  against the query's historical digest instead. The validator reads retained
  evidence bytes only: it neither recompiles the old source with the current
  compiler nor requires full per-workflow production bundles;
- artifact-contract comparison as a **keyed multiset**, preserving duplicate
  contracts. Keys include owning public entry, semantic step role, contract
  kind, artifact/field name, JSON pointer, type/variant, and publication role;
- execution order as a separate ordered sequence. Equal artifact multisets do
  not excuse an unreviewed execution-order change;
- persisted `SourceMapEntry.notes` proof for procedure definition and
  consuming call site;
- clean-run and interruption/resume evidence produced under the new IDs; and
- root-checksum evidence from default resume without observability or CLI
  override mutations, represented as a closed union selected by
  `evidence_mode`. `actual_tree` carries real `before_tree_digest` and
  `after_tree_digest` values and proves they are equal.
  `generic_characterization` instead carries `characterization_path`,
  `characterization_sha256`, `projection_sha256`, and the exact
  `tree_immutability: before_equals_after` result; it omits both tree-digest
  fields. The characterization file is content-addressed, uses the generic
  `workflow_lisp_root_checksum_characterization.v1` schema, and its inner
  projection digest is recomputed canonically. Both modes record that
  `WorkflowExecutor` construction and provider/command execution did not
  occur, and the closed evidence shape forbids unknown, missing, or mixed mode
  fields. Mode admissibility follows only from the immutable record fields,
  not a mutable project phase. Generic characterization never satisfies an
  actual old-state-negative or pilot-completion gate; a later actual-pilot
  negative is separate evidence and does not retroactively convert the
  retirement record; and
- callee-checksum characterization showing failure before child workflow or
  provider/command execution and no child-state identity remap, while recording
  any ordinary parent-level metadata permitted by the current runtime contract.

Repository evidence proves only repository facts. Store-owner attestation
proves only the named owner's knowledge of the named store at the recorded
time. Neither can establish the absence of unlisted external stores. If such a
store later appears, ordinary checksum rules apply without consulting the
retirement record. The record is not retroactively a remap authorization.

Historical old source and build artifacts are retained and readable for audit,
reports, and diagnosis. They are not selectable as current executable state
and are not rewritten to resemble the new build.

The validator derives the production identity table from the content-addressed
old/new artifacts and unions the frozen retired-identity query into the old
side. That union must match `identity_delta` exactly, including dispositions;
missing and extra identities both fail. Every query identity must occur in its
declared domain at most once. The sorted unique flattening of the domain lists
must equal the canonical sorted raw-identity query list, whose digest and count
are replayed independently. Because one raw identity may validly inhabit more
than one domain, the validator expands the domain map into unique
`(identity_kind, identity)` rows for the production-table and `identity_delta`
union; it does not require the domain lists to be disjoint. A query identity
that occurs anywhere in the new production identity table is a leaked retired
identity and is a hard validation failure, not a preserved identity or a
reason to trim the frozen query. Any mismatch in the
query version, canonical digest, identity count, exact domain membership map,
frozen-baseline digest, historical-source path binding, retained old-source
path binding, or their shared old-source digest fails closed.

This query evidence is evidence-only. Validation has no mutation output and
cannot authorize or perform a state-store, workflow-source, or build-artifact
write or mutation, identity alias, runtime remap, resume decision, or compiler
fallback. The mechanism and schema are migration-family-neutral and must not
select behavior from module, workflow, procedure, pilot, or repository names.

`terminal_run_count` and `nonterminal_run_count` are query-scoped counts of
distinct top-level runs containing at least one queried-identity match. Several
matches in one run count once. A match below a run directory inherits the
status of that first path component's top-level `state.json`. A nested match
without that state file fails the scan; an unreadable supported state file also
fails the scan; and a readable matching state with a missing or unknown
`status` counts as nonterminal. `store_terminal_run_count` and
`store_nonterminal_run_count` disclose all top-level runs in the named store
and remain digest- and freshness-bound, but they do not select strict
compatibility. The eligibility gate uses only the match-scoped
`nonterminal_run_count` and query-derived old call-frame/consumer counts.

## Pilot Application

The tracked-plan pilot was the first reviewed use of the retirement class. Its
completed evidence proves eligibility only for that content-addressed callee,
wrapper, store set, and run set. The route remains
`migration_evidence_only`; that label supports review but never decides
eligibility for another migration.

Before approval, the pilot owner must enumerate and attest every known store,
including the repository workspace's `.orchestrate/runs` root and any other
workspace/run roots intentionally used for this example. The scan must cover
top-level state, nested call frames, checkpoint records/indexes, retained
build manifests, and supported tooling that addresses the old call frame. A
repository-local zero match cannot support a claim about EasySpin,
PtychoPINN, paper repositories, copied workspaces, backups, CI artifacts, or
other external locations unless each is explicitly enumerated and attested.

If any known store contains a matching supported nonterminal run or a queried
old-identity consumer, the pilot returns to strict compatibility and waits for
identity preservation or the general upgrader. Unrelated active runs remain
disclosed in the whole-store totals but do not select compatibility. Terminal
historical evidence may remain, provided its old source/build artifacts are
retained and no supported resume/consumer contract is claimed.

## Dependencies And Sequencing

1. Treat acceptance of this clarification and the procedure-first contract
   amendment as a completed historical prerequisite from commit `61c79cb4`;
   do not re-amend either accepted authority during implementation.
2. Implement prerequisite A and prove normalized semantic identity stability
   on generic fixtures and both lowering routes.
3. Implement B and C; prove policy ownership and persisted two-note provenance
   on a generic inline effectful procedure fixture.
4. Implement the evidence-only retirement record validator and fresh checksum-
   rejection integration proof required by prerequisite D.
5. Retain the frozen old source/build artifacts and identity baseline without
   changing the pilot source or refreshing the old baseline.
6. Complete the known-store scans against the old identities, then obtain a
   genuine named human-owner attestation for every scanned store. An agent must
   never synthesize, guess, default, paraphrase, or sign an attestation. Any
   missing or ambiguous attestation selects strict compatibility and triggers
   the unattended stop without asking, retrying, or editing source.
7. Only after Step 6 passes, make the one pilot source migration.
8. Generate the content-addressed new artifacts, complete old-to-new identity
   delta and artifact/order comparisons, and produce clean-run plus real
   interruption/resume evidence under the new IDs.
9. Assemble and validate the completed retirement record, then obtain
   independent specification/runtime-state approval before accepting any
   reviewed retired identity.
10. Run negative old-state, focused, family parity, and broad verification,
    then update capability/status/routing docs only after implementation
    evidence passes.
11. Route the separate checksum-compatible projection-integrity hardening to a
    named plan and land it before production migration waves; it does not block
    this internal pilot.

Steps 2-4 are prerequisites, not acceptable differences to discover after the
family edit. If the current state/acceptance specs do not already state the
checksum compatibility and upgrader boundary accurately, clarify them before
the pilot source edit; do not add the separate projection audit to this plan.

The prerequisite implementation plan completed Steps 2-4 and retained the old
pilot baseline without editing the pilot source. Task 8 and its independent
reviews passed before Step 6 and the later source edit.

## Invariants And Failure Modes

- Strict compatibility is always the fallback.
- Retirement never crosses a public/exported/promoted boundary.
- No state is silently renamed, aliased, partially remapped, or baseline-
  refreshed.
- Artifact contracts are compared independently from execution order.
- Procedure definition and consuming call site both survive in persisted
  source-map notes.
- New-ID resume reuses only evidence valid under the new executable.
- Existing schema, bundle, lowering, root-checksum, and callee-checksum guards
  remain authoritative for old-state rejection.
- Pilot root-checksum rejection occurs before `WorkflowExecutor` construction
  or provider/command execution and leaves the persisted run tree
  byte-identical.
- Existing callee-checksum rejection occurs before child workflow or
  provider/command execution and performs no child-state identity remap;
  ordinary parent-level metadata may already exist.
- Reports, notes, and retirement labels are evidence views, not state
  authority.
- Retirement records are never runtime inputs.

| Failure | Required behavior |
| --- | --- |
| Known store lacks an owner or attestation | Select strict compatibility and stop the retirement path |
| Matching supported nonterminal run or queried old-identity consumer is found | Select strict compatibility; do not migrate |
| External-store absence is inferred from repository evidence | Reject the retirement record |
| Reported module-level lowering differs between Stage 3 and WCC | Fail compilation/build validation |
| Migration behavior depends on the classic schema-1 iteration call-local override | Reject migration/promotion; do not add an effective-call-site carrier in this pilot |
| Inline point receives workflow-call policy without a child frame | Fail checkpoint-policy validation |
| Either procedure/call-site source note is missing on a WCC inline generated node | Fail promotion-quality source-map validation |
| Artifact multiset differs | Stop unless the contract change receives a separate design |
| Execution order differs | Record and review separately; stop if behavior or effect order changes |
| Root checksum differs for the changed pilot source | Default resume rejects before `WorkflowExecutor` construction; the persisted run tree remains byte-identical |
| Root-checksum proof observes `WorkflowExecutor` construction, provider/command activity, or persisted mutation | Fail the retirement gate |
| Callee checksum differs after parent resume has begun | Preserve existing behavior: fail before child workflow or provider/command execution and do not remap child-state identities; ordinary parent-level metadata may already exist |
| Callee-checksum proof observes child workflow/provider/command execution or a child-state identity remap | Fail the retirement gate; do not require parent-executor preflight or whole-run-tree byte identity |
| A checksum-compatible completed/call-frame identity may be stale | Route the separate scoped-projection hardening before production migration waves; do not widen the pilot |

## Declarative Acceptance / Integration Scenarios

### Strict-compatible migration

Given a procedure-first candidate with no supported old run, compile the old
and new source through production build entrypoints. The keyed persisted-
identity sets are identical, artifact multisets are equal, execution order is
equivalent, and every earlier compatibility guard is characterized. This is
exact identity parity evidence, not old-state resume evidence.

Given any supported old run and changed source, the current root checksum guard
rejects resume even if every step/checkpoint identity is exact.
The migration stops for the deferred atomic upgrader, which must explicitly own
checksum and program-identity compatibility. It must not claim strict old-state
resume from identity equality alone.

### Reviewed internal retirement

Given a callee that is neither exported, registered, nor public, a containing
route that is not promoted/live, retained-wrapper contract evidence, a complete
retirement record, and owner attestations for all known stores with no matching
supported nonterminal run or queried old-identity consumer, compile and run the
new inline procedure.
A clean run completes with the same public contract and artifact multiset. A
second **new-source** run interrupted after the first generated provider
boundary resumes on the same run ID, reuses only validated new-ID work, and
completes with the clean run's public result. Persisted step/checkpoint source-
map notes carry both procedure-definition and call-site provenance labels. A
route label may support review but cannot establish or defeat eligibility.

### Old-state negative rejection

Given an unmodified old `state.json`, call frame, and checkpoint sidecars whose
root source checksum differs from the new source, invoke resume with the new
executable using default resume with no observability or CLI override
mutations. The existing root checksum guard rejects it before the projection
audit, `WorkflowExecutor` construction, or provider/command execution. Capture
the whole persisted run tree before and after: it remains byte-identical. Only
process exit status and stderr may differ. The runtime neither discovers the
retirement record nor creates a new-ID record, ignores old state, or applies a
partial map.

### Existing callee-checksum characterization

Given an existing callee-checksum mismatch path, resume through the parent and
characterize the current boundary. The mismatch fails before child workflow or
provider/command execution and performs no child-state identity remap. Parent
executor construction and ordinary parent-level metadata are permitted by the
current runtime contract, so this scenario does not require preflight rejection
or whole-run-tree byte identity. Record and classify any parent-level delta.

### Missing-attestation negative

Given repository evidence with zero local matches but one known store without
owner attestation, validation rejects
`reviewed_internal_identity_retirement`. It does not infer the store empty and
does not fall through to migration; strict compatibility remains selected.

### Public-boundary negative

Given an exported callee or a promoted/live route, a retirement record is
rejected even when all scanned stores have zero matches. The general upgrader
or exact identity preservation is required.

## Verification Strategy And Success Criteria

Implementation is acceptable only when all of the following are fresh and
passing:

- unit tests prove one-time module-level lowering resolution, authoritative
  WCC propagation and reporting, cross-route characterization that the pilot
  and a generic explicit-inline fixture do not trigger the classic schema-1
  local override, and rejection when migration would depend on that override;
- golden comparisons prove normalized classic/WCC semantic projection,
  checkpoint/program-point, presentation, and generated-workflow identities
  byte-stable for unchanged sources;
- generic inline fixtures prove effect-owned checkpoint policies and the
  absence of a synthetic workflow-call policy/frame;
- build/source-map tests prove the existing persisted definition and call-site
  note labels on WCC inline generated nodes through the production build route,
  without parsing note prose;
- retirement-schema tests reject missing store owners, missing attestations,
  external-absence claims, duplicate/ambiguous identity rows, and implicit
  remap directives;
- artifact parity uses keyed-multiset comparison and separately compares order;
- the pilot passes clean run and real interruption/resume under new IDs;
- a fresh root-checksum negative test uses default resume without observability
  or CLI override mutations and proves rejection before `WorkflowExecutor`
  construction or provider/command execution, a byte-identical persisted run
  tree, and no runtime dependency on the retirement record or partial
  remap/ignore behavior;
- a callee-checksum characterization test proves failure before child workflow
  or provider/command execution and no child-state identity remap, while
  allowing and recording ordinary parent-level metadata under the current
  runtime contract;
- a negative public/promoted fixture cannot select retirement;
- the pilot family parity, checkpoint/source-map suites, orchestrator smoke,
  and broad suite pass; and
- independent specification and runtime-state reviews approve the record.

Compilation, dry-run, source inspection, or a local zero-match scan is not a
success criterion by itself.

## Stop / Revise Criteria

Stop and revise this design if:

- any prerequisite requires a family/procedure-name special case;
- module-level lowering mode cannot be owned once by Stage 3 without changing
  normalized persisted semantic identity fields for unchanged source;
- inline procedure checkpoints cannot be expressed by ordinary effect policy;
- existing persisted notes cannot carry both required provenance labels on WCC
  inline generated nodes;
- any known matching supported live/nonterminal run or queried old-identity
  consumer exists;
- root-checksum rejection does not occur before `WorkflowExecutor`
  construction or mutates any part of the persisted run tree;
- callee-checksum rejection permits child workflow/provider/command execution
  or remaps any child-state identity;
- the pilot changes a public contract, artifact multiset, publication,
  terminal outcome, effect ordering, or retained wrapper identity; or
- migration waves begin treating this one retirement approval as blanket
  authority for other callees or stores.

## Documentation And Normative Impact

The following acceptance-level changes already landed in commit `61c79cb4`:

- this design became accepted without claiming its prerequisites implemented;
- `docs/design/workflow_lisp_procedure_first_reuse_contract.md` gained the
  strict-default/reviewed-internal-retirement qualification and the same
  qualification on Migration Test item 6; and
- the frontend specification gained the concise compatibility qualification
  and link, while routing/status surfaces selected the prerequisite plan and
  paused the pilot.

With the generic prerequisites and one pilot implemented, the contract references
describe the observed behavior: `specs/state.md` and `specs/acceptance/index.md`
own the distinct root/callee checksum and future-upgrader rules;
`docs/design/workflow_lisp_source_map.md` owns WCC propagation of the existing
procedure-definition and consuming-call-site notes without a schema change;
and the pilot plan owns the detailed pre-edit store/owner and retirement-record
production gates. The recorded Task 8 approval and pilot evidence, rather than
these references alone, authorized the completed source edit.

The capability matrix, authoring guide, route-readiness registry, and other
implementation-status surfaces remain gated on their own required evidence.

A separate projection-integrity audit must be routed into a named follow-on
design and plan before production migration waves. It is not a pilot
prerequisite or a normative impact of this design. Any necessary checksum and
acceptance clarification must land before the pilot claims migration success;
capability, status, and route-readiness updates wait for passing evidence.

## Open Questions

None remains open for this accepted architecture. Concrete artifact paths, the
command that enumerates known stores, and the named human owners belong in the
pilot implementation plan and retirement record. They must not be defaulted
or inferred by the compiler.
