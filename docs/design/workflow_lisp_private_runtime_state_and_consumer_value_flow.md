# Workflow Lisp Private Runtime State And Consumer Value Flow

Status: draft target design (future target; describes intended behavior, not
the current checkout)
Kind: architecture / runtime plumbing and value-flow simplification target
Created: 2026-06-13
Scope: private lexical execution checkpoints; effect-boundary resume policy;
consumer-side rendering of typed values; entry-boundary publication policy;
compatibility bridge rendering; and retirement of authored path plumbing whose
only purpose is runtime resume or consumer formatting.

Authority:

- Normative runtime and DSL behavior remains in `specs/`. This document is a
  future target; nothing here changes current behavior until its tranches land
  with evidence and any required spec deltas are accepted.
- `docs/design/workflow_lisp_frontend_specification.md` is the parent Workflow
  Lisp language contract. It owns WCC lowering as the default route for the
  migrated subset, `RunCtx`, `Resource[TState]`,
  `Transition[TRequest,TResult]`, generated `pure_projection`,
  `materialize-view`, structural private context recognition, and boundary
  authority classes.
- `docs/design/workflow_lisp_core_calculus_middle_end.md` owns WCC program
  identity: ANF bindings, join points, scopes, proof state, effect rows,
  lowering schema version, and defunctionalization. This document consumes that
  identity for checkpoint keys and adds no control constructs.
- `docs/design/workflow_lisp_state_layout.md` owns generated path allocation
  identity. This document adds checkpoint and rendering roles; it does not
  redefine path identity rules.
- `docs/design/workflow_lisp_runtime_migration_foundation.md` owns validated
  structured-output transport, private value transport, provider prompt
  composition authority, and fail-closed structured-output behavior.
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  owns family promotion sequencing, parent-callable parity, and the
  values-before-artifacts migration idiom. This document supplies a later
  substrate for removing resume-only and render-only authored plumbing; it does
  not replace promotion gates.
- `docs/design/workflow_lisp_lexical_execution_checkpoints.md` and
  `docs/design/workflow_lisp_consumer_side_rendering.md` are predecessor draft
  targets whose contracts are absorbed here as two independent tracks. They
  remain useful detailed notes until archived or superseded by this umbrella.

Related docs:

- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_core_calculus_middle_end.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_lexical_execution_checkpoints.md`
- `docs/design/workflow_lisp_consumer_side_rendering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/providers.md`
- `specs/state.md`

## 1. Purpose

Workflow Lisp has already moved the main semantic contract toward typed values,
typed resources, typed transitions, generated projections, and materialized
views. The remaining authoring friction comes from two classes of plumbing that
are not domain semantics:

1. resume-position plumbing: run-state paths, prior-state paths, loop-frame
   paths, pointer targets, and state roots carried so the runtime can find its
   place later; and
2. rendering plumbing: summary paths, bundle paths, prompt-input files,
   report targets, and compatibility files carried so a later consumer can see
   a representation of a typed value.

Both problems have the same durable shape:

```text
Authored workflows should pass typed values and declared resources.
The runtime should privately remember execution position.
Consumers should render typed values at their own seam.
```

This document merges the two future targets into one owner design while keeping
their implementation lanes independent. Track R owns private lexical execution
checkpoints and resume policy. Track C owns consumer-side rendering and
publication policy. The shared target is to remove file/path vocabulary from
authored `.orc` bodies unless the file operation is itself semantic, timed, or
an explicitly labeled compatibility bridge.

## 2. Executive Decision

Adopt a two-track target under one principle: typed values are the carrier,
private runtime state is runtime-owned, and file renderings are produced only at
consumer seams.

```text
Semantic workflow data:
  typed values, typed resources, typed transitions, provider/command bundles

Private runtime execution data:
  lexical checkpoints over WCC identity, effect-boundary resume policy,
  checkpoint validity metadata, checkpoint diagnostics

Consumer renderings:
  prompt injection renderings, observability summaries, entrypoint publications,
  compatibility bridge files, rare timed body materializations
```

The two tracks are independent after the shared census:

```text
Track R: private lexical execution checkpoints
  R0 resume/plumbing census
  R1 checkpoint schema and shadow emission
  R2 restore for pure and structured regions
  R3 effect-boundary resume policies
  R4 transition-aware resume
  R5 resume-only authored plumbing retirement
  R6 default flip and legacy cleanup

Track C: consumer-side rendering
  C0 rendering/plumbing census and renderer seam verification
  C1 typed values as prompt inputs
  C2 observability-derived human summaries
  C3 entry-boundary publish policy
  C4 compatibility bridges as metadata
  C5 durable/ephemeral rendering cleanup
```

Merging the targets does not mean making either track block the other. The
combined document exists because the architectural anti-pattern is shared:
authoring workflows around generated files rather than around typed values.

## 3. Problem

Workflow Lisp can express more of the workflow semantics natively, but current
families still show path-shaped surfaces:

- loop state carries run-state paths and summary paths;
- reusable calls accept prior-state or output-target paths;
- public boundaries expose targets that should be runtime-derived or
  generated-internal;
- summaries and prompt inputs are written by producers even when the consumer
  is the only reason a rendering exists;
- compatibility files survive as body-level ceremony instead of as declared
  bridge metadata; and
- resume behavior relies on step state and generated path identity, but not on
  a private representation of the lexical continuation and bindings that the
  program could resume from.

The result is over-authored `.orc`: workflows expose and thread values that are
neither user intent nor domain state. That makes parent workflows verbose,
raises the chance of pointer-as-state mistakes, and obscures which values are
semantic authority.

## 4. Goals

1. Keep typed values and typed resources as semantic authority.
2. Give the runtime a private, schema-versioned checkpoint model for execution
   position over WCC program identity.
3. Keep domain durability in `Resource[TState]` and
   `Transition[TRequest,TResult]`; checkpoints must not become audit state.
4. Render typed values at consumer seams: provider prompt injection,
   observability/reporting, entrypoint publication, and compatibility bridges.
5. Shrink authored `.orc` bodies by retiring resume-only and render-only path
   fields from loop state, records, public boundaries, and call signatures.
6. Preserve source maps, Semantic IR, executable IR, and diagnostics for every
   generated checkpoint, rendering, publication, and bridge.
7. Keep compatibility bridges explicit, labeled, and removable without body
   rewrites.
8. Allow Track R and Track C to proceed independently once the shared census and
   prerequisites are satisfied.

## 5. Non-Goals

- No checkpoint-only semantics. Checkpoints never replace resource transitions,
  transition audit, idempotency, conflict detection, or parity-comparable
  domain state.
- No resource-only execution model. Loop position, lexical bindings, and
  continuation identity should not be forced into domain resources merely to
  make resume possible.
- No invisible rendering. Consumer-side rendering must leave evidence in
  composed-prompt logs, observability artifacts, publication records, Semantic
  IR, or bridge metadata.
- No new general templating language. Renderers remain registered, versioned,
  deterministic, and typed.
- No change to provider or command output authority. Structured results still
  travel through validated runtime-bound bundles.
- No runtime closures or dynamic procedure values.
- No removal of compatibility views while parity or legacy consumers still
  require them.
- No claim that the two tracks must land in a single implementation drain.

## 6. Authority And Dependency Direction

### 6.1 This document consumes

- WCC program identity and lowering schema identity.
- Structural private context recognition and boundary authority classes.
- `Resource[TState]`, `Transition[TRequest,TResult]`, idempotency, audit,
  conflict policy, and resume-safe transition results.
- `materialize-view` renderer registry, determinism, and view authority rules.
- StateLayout allocation identities for generated private paths.
- Provider prompt composition and composed-prompt logs.
- Semantic IR, executable IR, and source-map provenance contracts.

### 6.2 This document owns

- The umbrella principle: authored `.orc` should carry typed values and
  declared resources, not resume/render path plumbing.
- The lexical checkpoint content model, validity rules, storage contract, and
  effect-boundary resume policy taxonomy.
- The consumer rendering lane taxonomy: typed step, prompt injection,
  observability, entry publication, compatibility bridge, and timed body
  materialization.
- The shared census taxonomy for resume-only and render-only authored plumbing.
- The acceptance boundary for retiring path fields from public boundaries,
  loop state, records, and call signatures.

### 6.3 This document does not own

- WCC calculus changes.
- Transition execution semantics.
- Renderer implementation internals beyond consumer-lane invocation contracts.
- Concrete generated path naming.
- Provider output validation.
- Migration promotion thresholds.
- Dashboard or report product design beyond consuming typed terminal values.

### 6.4 Prohibited dependency directions

```text
checkpoint state      -> semantic authority                  PROHIBITED
rendered file         -> typed semantic input                 PROHIBITED
compatibility bridge  -> unlabeled body-level file ceremony   PROHIBITED
prompt rendering      -> provider output authority changes    PROHIBITED
runtime resume need   -> public authored input                PROHIBITED
consumer need         -> producer-owned path field by default PROHIBITED
checkpoint mismatch   -> silent reuse                         PROHIBITED
non-idempotent effect -> blind rerun                          PROHIBITED
```

## 7. Core Model

### 7.1 Three ledgers

The target separates three kinds of state:

| Ledger | Owns | Durable? | Semantic authority? |
| --- | --- | ---: | ---: |
| Typed value flow | provider/command/workflow results, pure projections, structured values | Depends on producer contract | Yes |
| Resource ledger | domain resources, transitions, versions, audit | Yes | Yes |
| Execution checkpoint ledger | lexical continuation, bindings, proof state, pending-effect policy | Disposable cache | No |

The checkpoint ledger may make resume cheaper and less intrusive. It does not
prove domain correctness. On any conflict between checkpoint state and resource
state, resource state wins and the checkpoint is discarded or invalidated.

### 7.2 Consumer rendering lanes

Rendering moves to the consumer seam:

| Consumer | Preferred lane | Durability | Notes |
| --- | --- | --- | --- |
| Typed workflow step | Pass typed value | None | No rendering. |
| Provider prompt | Render at prompt injection | Ephemeral | Evidence in composed-prompt logs. |
| Human/operator | Observability renders typed result | Derived on demand or cached | Must not drive routing. |
| Public entrypoint consumer | Entry-boundary `:publish` policy | Durable view | Lowered to `materialize-view` at terminal boundary. |
| Legacy reader | Compatibility bridge metadata | Durable labeled bridge | Deleting metadata retires the bridge. |
| Mid-run timed publication | Authored `materialize-view` | Durable view | Allowed only when timing is semantic. |

Lane zero is always the default: if the next consumer can take a typed value,
nothing should render.

### 7.3 Lexical checkpoint content

A checkpoint records enough private runtime data to resume a WCC execution
region:

```text
checkpoint {
  program_identity
  lowering_schema_version
  source_module_digest
  wcc_node_id
  lexical_environment_digest
  typed_bindings
  active_variant_proofs
  loop_frame_state
  pending_effect_policy
  completed_effect_refs
  resource_version_observations
}
```

Typed bindings may contain validated typed values or references to validated
runtime-owned bundles. They must not contain arbitrary Python objects, open
file handles, unvalidated stdout, or paths treated as semantic authority.

### 7.4 Checkpoint validity

A checkpoint is valid only when all of the following match:

- workflow/module identity;
- WCC lowering schema version;
- executable program digest;
- checkpoint schema version;
- typed binding schemas;
- effect-boundary policy;
- resource version observations for resource-sensitive regions; and
- structured-output bundle hashes for completed provider/command effects that
  are being reused.

Mismatch fails closed. The runtime may recompute from a prior safe boundary, but
it must not silently reuse a stale checkpoint.

### 7.5 Effect-boundary resume policies

Every effect boundary has an explicit policy:

| Effect kind | Resume behavior |
| --- | --- |
| Pure projection | Recompute or reuse deterministic checkpoint. |
| Materialized view | Regenerate from typed value unless durable publication policy says to preserve existing bytes. |
| Provider call | Reuse only validated structured output with matching prompt/input contract and hash evidence. |
| Command / certified adapter | Reuse only declared output bundle or certified resume protocol. |
| Resource transition | Use idempotency key and transition audit; do not replay as a blind command. |
| External non-idempotent effect | Fail closed unless a certified resume protocol exists. |

The policy is part of Semantic IR and executable IR evidence.

### 7.6 Boundary cleanup rule

Every authored path-like value in a parent-callable candidate must classify as:

- `public_authored`;
- `compatibility_bridge`;
- `runtime_derived`;
- `generated_internal`;
- `materialized_view`; or
- `public_artifact`.

Promotion-quality `.orc` boundaries expose only `public_authored` values and
explicitly accepted compatibility bridges. Resume-only paths and render-only
paths are not promoted public inputs.

## 8. Shared Census And Classification

Before either track changes behavior, create a shared checked census:

| Class | Meaning | Target |
| --- | --- | --- |
| `resume_only` | Exists only to recover program position | Private checkpoint |
| `domain_resource` | Represents semantic durable state | `Resource` / `Transition` |
| `prompt_rendering` | Exists only to feed provider prompt text | Prompt-seam rendering |
| `human_rendering` | Exists only for human/operator view | Observability rendering |
| `entry_publication` | Public artifact intentionally produced by entrypoint | `:publish` policy |
| `compatibility_bridge` | Legacy consumer still needs file shape | Bridge metadata |
| `timed_publication` | File must exist at a specific interior time | Authored `materialize-view` |
| `genuine_external_io` | External process or system tool needs path | Certified command/adapter |

The census must cover public inputs, loop-state fields, record fields,
materialized outputs, prompt-input files, summary/report targets, pointer paths,
provider targets, adapter inputs, and bridge files in the reference family.

## 9. Track R: Private Lexical Execution Checkpoints

### R0: Resume semantics census and characterization

Record current resume behavior, generated path identity, loop-frame state,
`resume-or-start` usage, run-state path flow, and fail-closed schema checks.

Acceptance:

- current resume fixtures are characterized;
- every resume-only authored field is classified;
- no domain resource is mislabeled as checkpoint-only.

### R1: Checkpoint schema and shadow emission

Emit checkpoint records beside current runtime state without using them for
restore.

Acceptance:

- checkpoints include schema version, WCC identity, binding schema, effect
  policy, and source-map provenance;
- checkpoint emission is deterministic for the same executable/run/frame;
- mismatch diagnostics exist and fail closed in shadow validation.

### R2: Restore for pure and structured regions

Restore pure bindings, `let*`, `match`, loop counters, branch proofs, and
structured control positions from checkpoints where no unsafe pending effect is
involved.

Acceptance:

- branch-local and loop-local resume fixtures restore without authored
  run-state paths;
- variant proof state is restored only when proof identity matches;
- stale checkpoint and executable drift fixtures fail closed.

### R3: Effect-boundary resume policies

Attach resume policy to every generated effect boundary.

Acceptance:

- pure, provider, command, workflow call, materialized view, and transition
  boundaries all emit policy metadata;
- unsafe non-idempotent command replay is rejected;
- provider reuse requires validated structured-output evidence.

### R4: Transition-aware resume

Integrate checkpoints with transition audit and idempotency keys.

Acceptance:

- committed transitions are not blindly replayed;
- idempotent transition replay returns the committed result with audit evidence;
- resource version conflicts invalidate dependent checkpoints.

### R5: Resume-only authored plumbing retirement

Remove or hide path fields whose only purpose is checkpoint/resume recovery.

Acceptance:

- promoted boundaries do not expose resume-only state paths;
- loop state carries typed values and resources, not checkpoint paths;
- `resume-or-start` remains for domain reusable state, not program-position
  recovery.

### R6: Default flip and legacy cleanup

Make lexical checkpoints the default resume substrate for eligible WCC regions,
with compatibility behavior retained only for historical runs.

Acceptance:

- default restore uses checkpoints in eligible regions;
- legacy step-granular resume remains available for historical compatible runs;
- cleanup removes dead resume-only public plumbing after evidence proves no
  current consumer.

## 10. Track C: Consumer-Side Rendering

### C0: Rendering census and renderer seam verification

Classify every authored `materialize-view`, summary writer, report target,
prompt input, bridge file, and path field by consumer class.

Acceptance:

- renderer interface can produce deterministic bytes independent of allocation;
- every render-only path has a consumer class;
- body-level materializations are either timed publications or retirement
  candidates.

### C1: Typed values as prompt inputs

Allow prompt inputs to bind typed values directly. Prompt composition renders
them through registered renderers at the injection seam.

Acceptance:

- provider prompt receives the rendered content without a producer-authored
  file;
- composed-prompt logs identify renderer id, renderer version, typed input
  identity, and source value;
- provider output authority is unchanged.

### C2: Observability-derived human summaries

Let reporting and dashboard surfaces render typed terminal values and transition
audit into human summaries.

Acceptance:

- human summaries for the reference family are generated from typed terminal
  results;
- routing never consumes those summaries;
- old summary writer behavior has dual-run comparison before retirement.

### C3: Entry-boundary `:publish` policy

Move durable public output views to entrypoint result policy instead of body
code.

Illustrative surface:

```lisp
(defworkflow drain
  ((steering SteeringDoc)
   (target-design TargetDesignDoc)
   (baseline-design BaselineDesignDoc))
  -> DrainResult
  (:publish
    ((DONE.drain-summary :renderer markdown :role drain-summary)
     (BLOCKED.drain-summary :renderer markdown :role drain-summary)
     (EXHAUSTED.drain-summary :renderer markdown :role drain-summary)))
  ...)
```

Acceptance:

- publication policy lowers to terminal-boundary `materialize-view`;
- result type remains a typed result, not a view reference, unless a
  compatibility bridge field is explicitly declared;
- changing publication policy does not change workflow call typing.

### C4: Compatibility bridges as metadata

Represent legacy required files as bridge metadata over typed values.

Acceptance:

- bridge metadata declares owner, consumer, renderer, schema/version,
  retirement condition, and typed source value;
- deleting bridge metadata retires the bridge without body edits;
- bridge files are never consumed as semantic authority by typed steps.

### C5: Durable/ephemeral rendering cleanup

Make ephemeral rendering and durable rendering explicit in the kernel and retire
body-level renderings that are no longer timed publications.

Acceptance:

- prompt rendering allocates no durable view path;
- durable publications and bridges allocate through StateLayout;
- reference-family bodies contain no `materialize-view` except justified timed
  publications.

## 11. Dependencies And Sequencing

Prerequisites:

- WCC schema 2 identity is available for target regions.
- `RunCtx`, resources, transitions, materialized views, and boundary authority
  classes are accepted in the frontend baseline.
- StateLayout can allocate checkpoint, publication, and bridge roles.
- Semantic IR and executable IR can carry checkpoint and rendering evidence.

Suggested sequencing:

```text
U0 shared census
  -> R1/R2 checkpoint shadow and pure-region restore
  -> R3/R4 effect and transition-aware resume
  -> R5/R6 resume-only plumbing retirement

U0 shared census
  -> C0 renderer seam verification
  -> C1/C2 prompt and observability rendering
  -> C3/C4 publication and bridge policy
  -> C5 render-only plumbing retirement
```

Track R and Track C may proceed in either order after U0/C0/R0 if their touched
runtime files are not in conflict. A selector may choose one track, both tracks,
or a narrow shared slice. Neither track may claim the other track's acceptance
evidence.

## 12. Invariants And Failure Modes

Invariants:

- Typed values and resources remain semantic authority.
- Checkpoints are private, disposable, schema-versioned runtime cache.
- Views are representations unless a public contract explicitly publishes
  them; even then, the typed value remains the semantic producer.
- Resource transitions are the only in-language durable mutation surface.
- A consumer that can accept typed values must not force rendering.
- Compatibility bridges must be declared in metadata, not hidden in body code.
- All generated checkpoint/rendering/bridge nodes are source-mapped.

Failure modes:

- Checkpoint schema mismatch: fail closed, recompute from prior safe boundary if
  possible.
- Executable digest mismatch: reject checkpoint reuse.
- Resource version conflict: invalidate dependent checkpoint and surface
  transition conflict diagnostics.
- Pending non-idempotent effect: fail closed unless a certified resume protocol
  exists.
- Renderer version mismatch: regenerate only if the consumer policy permits it;
  otherwise fail closed for durable published bytes.
- Bridge metadata missing for a required legacy file: fail bridge validation,
  not workflow typing.
- Rendered file used as typed semantic input: compile or validation error.

## 13. Evidence And Implementation Boundaries

Required evidence:

- shared census artifact for resume-only and render-only path fields;
- checkpoint shadow emission with source maps and Semantic IR entries;
- restore fixtures for pure, branch, loop, and proof-carrying regions;
- effect-boundary policy fixtures for provider, command, workflow call,
  materialized view, and transition effects;
- transition-aware resume fixtures proving idempotent replay and conflict
  invalidation;
- prompt-injection rendering fixture with composed-prompt evidence;
- observability rendering fixture that proves human summaries do not drive
  routing;
- entry-boundary publication fixture with typed result unchanged;
- bridge metadata fixture where deleting metadata retires a file without body
  edits; and
- negative fixtures for view-as-state, checkpoint drift, unsafe command replay,
  unclassified public path, and orphan bridge files.

Prohibited evidence:

- treating a checkpoint as parity-comparable domain state;
- proving resume by keeping public run-state paths in the promoted boundary;
- treating a prompt-rendered file as provider output authority;
- using body-level `materialize-view` where only a prompt, report, boundary, or
  bridge consumer needs bytes;
- deleting compatibility files without bridge-retirement evidence; or
- claiming the umbrella complete because only Track R or only Track C landed.

## 14. Compatibility And Migration

Existing workflows continue to run with current step-granular resume and
authored materialization. This target introduces migration paths:

- checkpoint shadow emission before restore is enabled;
- dual-run comparison before replacing resume-only authored state;
- dual-run comparison before retiring summary/view writer behavior;
- bridge metadata alongside existing compatibility files before body cleanup;
- explicit fallback for historical runs whose executable or checkpoint schema
  predates this target; and
- promotion gates that reject unclassified generated/internal public paths.

`resume-or-start` remains valid for reusable domain state. The migration narrows
its use: it should not be the mechanism for recovering lexical execution
position.

## 15. Verification Strategy

Use narrow fixtures first, then family-level proof.

Narrow fixtures:

- pure `let*` restore;
- `match` branch restore with variant proof;
- loop resume with counter and state value;
- provider result reuse from validated structured output;
- unsafe command pending-effect rejection;
- idempotent transition replay;
- prompt rendering from typed value;
- observability summary from typed terminal result;
- entrypoint publication with unchanged result type; and
- bridge metadata generation and deletion.

Family-level fixtures:

- parent drain boundary exposes only authored inputs plus accepted bridges;
- loop state carries typed values/resources, not resume-only paths;
- provider prompts consume typed values without producer-authored prompt files;
- terminal summaries are rendered by observability or publish policy;
- compatibility bridge files are generated from metadata; and
- strict parity distinguishes typed semantic output from views and checkpoints.

## 16. Declarative Acceptance Scenarios

### 16.1 Resume without authored run-state plumbing

Initial state: a parent `.orc` drain has entered a nested loop and completed a
pure branch selection.

Entrypoint: interrupt after checkpoint shadow emission, then resume the same run
with the same executable identity.

Expected result: the runtime restores the lexical loop position and typed
bindings from a private checkpoint. No public `run_state_path`,
`loop_state_path`, or generated checkpoint path is required.

Forbidden result: the workflow resumes only because the author carried a
runtime bookkeeping path through loop state.

### 16.2 Transition wins over checkpoint

Initial state: a checkpoint observes resource version `v1`, then an external
valid transition advances the resource to `v2`.

Entrypoint: resume from the checkpoint.

Expected result: the checkpoint is invalidated or the region recomputes from a
safe boundary; transition audit remains authority.

Forbidden result: checkpoint restore overwrites or ignores the newer resource
version.

### 16.3 Prompt consumes typed value

Initial state: a provider step needs a typed `ReviewContext` in its prompt.

Entrypoint: run the provider with `ReviewContext` supplied as a typed input.

Expected result: prompt composition renders the value at injection time, records
renderer evidence in the composed-prompt log, and does not require a
producer-authored file.

Forbidden result: an earlier workflow step writes a prompt-input file solely so
the provider can read it.

### 16.4 Summary nobody wrote

Initial state: a workflow returns a typed `DrainResult`.

Entrypoint: inspect the run through `orchestrator report` or dashboard summary.

Expected result: observability renders the human summary from the typed result
and transition audit. The summary is not consumed by routing or parity as
semantic state.

Forbidden result: workflow body calls a summary writer only for human
inspection.

### 16.5 Boundary publication only

Initial state: a workflow result variant should publish a markdown summary for
external users.

Entrypoint: run a workflow whose entrypoint declares `:publish` for that result
variant.

Expected result: terminal-boundary publication materializes the view through the
registered renderer and StateLayout allocation. The workflow call type remains
the typed result.

Forbidden result: intermediate body code carries a `summary_path` field through
records solely for final publication.

### 16.6 Bridge retirement by metadata deletion

Initial state: a legacy consumer requires a JSON compatibility file generated
from a typed result.

Entrypoint: run with bridge metadata enabled, then remove the bridge metadata
after the consumer is retired.

Expected result: with metadata enabled, the file is generated as a labeled
bridge; after deletion, no body code changes are needed and no orphan file is
produced.

Forbidden result: bridge generation is hardcoded in the workflow body.

## 17. Success Criteria

This umbrella target succeeds when:

- resume-only and render-only path plumbing is classified across the reference
  family;
- private lexical checkpoints restore eligible WCC regions and fail closed on
  drift, schema mismatch, unsafe pending effects, and resource conflicts;
- resource transitions remain the only semantic durable mutation route;
- prompt rendering, observability rendering, entry-boundary publication, and
  compatibility bridge rendering all consume typed values;
- body-level `materialize-view` remains only for justified timed publications;
- promoted public boundaries expose no resume-only or render-only generated
  paths;
- Semantic IR, executable IR, source maps, and diagnostics explain every
  generated checkpoint, rendering, publication, and bridge; and
- Track R and Track C both have independent acceptance evidence, with family
  parity proving typed values rather than files are the semantic carrier.

## 18. Summary Recommendation

Use this umbrella as the next cleanup target only if the implementation driver
wants one coherent objective: eliminate authored runtime/file plumbing from
Workflow Lisp without weakening semantic authority. Keep the tracks independent:
Track R makes resume private and lexical; Track C makes rendering
consumer-owned. The shared result is a simpler `.orc` style where authors pass
typed values and resources, while the runtime owns execution memory and
consumers own representations.
