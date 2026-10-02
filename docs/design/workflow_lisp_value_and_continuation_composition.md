# Incremental Value And Continuation Composition

Status: Increments 1–5 are implemented at targets 2.28–2.32. Human input includes
normal public CLI admission and durable nested/loop recovery. Execution evidence
and final compatibility results live in the linked plan.

Purpose: remove composition obstacles exposed by
[progressive execution](workflow_lisp_progressive_execution.md), without adding
an agent framework to the language. Earlier targets retain their prior
boundaries and workarounds. Most examples below are design sketches. The
[Durable Host Input guide](../lisp_workflow_drafting_guide.md#durable-host-input)
provides a copy-safe `request-input` module and current authoring steps.

## Decision And Ownership

Improve existing value boundaries before introducing new capabilities. Keep
each correction independently useful: union prompt inputs, rich loop values,
pure helper expressions, portable provider context, and human input. The first
three extend existing composition paths; the last two genuinely add provider or
host interaction and must not be described as syntax-only fixes.

This design owns the union-input and rich-loop deltas, the incremental dependency
boundaries, and the minimal human-input target. It consumes, rather than replaces,
the existing [pure-call design](workflow_lisp_pure_call_composition.md) and
[provider-context design](workflow_lisp_provider_context_values.md). Consumer
rendering remains owned by the
[value-flow architecture](workflow_lisp_private_runtime_state_and_consumer_value_flow.md).
The [frontend baseline](workflow_lisp_frontend_specification.md) and `specs/`
continue to own implemented behavior. None of these increments changes roadmap
selection or research allocations.

The intended author model is: a value returned by one operation can be consumed
by another without author-written serialization or wrapper taxonomies, wherever
the destination's real semantics support it. This does not make provider calls
pure, native contexts universally portable, or runtime callables transportable.

Alternatives are retaining local workarounds or replacing the value/callable
foundation wholesale. Prefer shared boundary corrections first: workarounds
remain useful controls, while a redesign needs evidence that the corrections
cannot deliver ordinary composition without accumulating special cases.

What this choice makes harder: broader containers, arbitrary runtime callables,
and multiple simultaneous human conversations do not arrive together. Explicit
limits are preferable to claiming uniformity before the relevant paths work.

## Baseline: Capability Is Not Uniform

| Boundary | Current evidence and limit |
| --- | --- |
| Structured transport | Target 2.25 admits records/closed unions under lists, optionals, and string-keyed maps; see [versioning](../../specs/versioning.md) and [nested transport tests](../../tests/test_workflow_lisp_nested_transportable_value.py). This is not trial-only support. |
| Loop carriage | Target 2.29 carries rich lists through state, recursive exhaustion exits and committed-boundary resume. Older targets retain their original limits. |
| Prompt consumption | Target 2.28 now admits whole closed unions and eligible lists through the [existing renderer](../../orchestrator/workflow_lisp/typed_prompt_inputs.py), including imported private returns and resumed consumption. Below 2.28 the previous boundary remains. This does not admit every result type as a prompt input. |
| Helper expressions | Target 2.30 composes resolved inline effect-free helpers through expression positions; private/effectful or unrepresentable calls retain explicit placement requirements. |
| Conversation | Target 2.31 implements portable ordinary Codex context. Target 2.32 permits one outstanding human-input request per root at a time; sequential questions are allowed after the prior request is consumed. Imported calls, loops and answer/cancel recovery are supported. |

Current-target probes established rich-list transport and pure-map typechecking,
not full runtime traversal. Do not describe all record/union lists as unsupported
based on target-2.18 tests, or infer end-to-end support from newer type admission.

## Increment 1: Consume A Whole Union In A Provider Prompt

Implemented at target 2.28, where `decision` is a validated union result:

```lisp
(provider-result providers.worker
  :prompt prompts.act
  :inputs (brief decision)
  :returns WorkResult)
```

No new syntax. Extend the existing typed-input route to closed unions, then
lists of those unions where the selected target already admits their complete
transport contract. Use the existing canonical JSON representation: one
discriminant and only the active payload, preserving nested values and nulls.
Do not stringify values, introduce a wrapper record, or require an explicit
renderer for this ordinary case.

Selection, lowering, value resolution, normalization/validation, and prompt
composition must agree on the binding. Resolve the whole value through the
existing typed producer/call boundary; do not reconstruct it by eagerly reading
every variant's fields. If reconstruction is required, the existing discriminant
must select the active payload before field resolution. Rendering the whole
union grants no branch proof for arbitrary source-level field access.

Reuse the existing descriptor/validation and canonical renderer owners. Remove
the exclusion for the newly admitted regime, not the validator. Preserve the
one-binding/one-resolved-value/one-rendered-block contract, current output-schema
ownership, and phase fallback behavior. No producer-authored bridge file or
second result store is introduced.

### Flattened-boundary carriage

A flattened union has no whole-result reference: its step artifact map is not
the source value. Preserve an existing whole-value reference when one actually
exists (for example, a transported list). Otherwise use one compiler-owned
`value_source` kind, `typed_union_projection`, in the existing typed-input
contract. Its exact fields are `kind`, the existing normalized type `descriptor`,
and `source`. The source is a small descriptor-shaped tree:

- `{"kind":"reference","reference":"root.steps.producer.artifacts.variant"}`;
- `{"kind":"literal","value":...}` for finite JSON data;
- `{"kind":"record","fields":{"field_name":source,...}}`; or
- `{"kind":"union","discriminant":source,"variants":{"TAG":{"field_name":source,...},...}}`.

Reference and literal nodes are atomic, including whole records, unions, and
lists. The discriminant is a reference or literal, never a record/union node.
Validate exact node keys and each branch against its corresponding descriptor.
A dynamic discriminant needs every declared alternative; a known literal tag
needs only that selected alternative. Reconstructed records contain their
declared fields. Lists remain whole transported values, not index projections.
These are control-plane tags, never inferred from payload keys.

Derive branch sources from the actual flattened boundary contracts and output
references. Preserve that information at the compiler's value-binding owner;
a merged field map may already have discarded a scalar when another variant
uses the same name for a nested record. Do not reconstruct references by guessing
artifact names. In particular, `SCALAR(value Int) | RECORD(value Nested)` remains
supported: alternatives own distinct source subtrees even though their value
field names overlap. The source carrier needs neither a flat pointer map nor
a conditional-expression language.

Preserved terminal references also serve ordinary private-workflow returns. At
the new target, the existing direct-output lowering path must use those refs
instead of falling back to a pure projection merely because the merged local
map lost a branch field. Keep the private call/frame and provider checkpoint;
only the redundant projection disappears. This requires no dynamic-union
extension to the pure-expression or replay payload.

Do not capture that merged local map as a whole-value lexical binding: it may
already have lost a branch field. For a flattened whole-union local carrying
the new source metadata, omit only the redundant whole-value restore binding,
as the existing returned-union path already does. Keep effect checkpoints,
call frames, and separate branch-proof descriptors. Durable flattened outputs
remain authoritative. Ordinary value documents exclude exact reserved compiler
metadata, not every user field beginning with `__`.

Resume dependency discovery must recognize every artifact member declared by
the provider's existing `variant_output` contract. Declared address membership
is distinct from an exact type suitable for a pure replay dependency: do not
choose the first alternative's contract or broaden typed pure replay reads.
The existing discriminant-first prompt resolver owns active-value resolution;
this correction adds no second union evaluator or checkpoint source-tree form.

The shared output validator must respect the already-declared selected field
ownership. An inactive variant's JSON pointer is not forbidden merely because
it equals an active pointer, contains an active descendant, or lies inside an
active atomic subtree. Compare pointer segments, still reject unrelated
inactive siblings, and validate active values normally. Apply that correction
to variant bundles and union-projected output bundles alike. Astra review
identified this as an existing contract bug, not a new schema or target-gated
transport capability; it changes no emitted bytes or checkpoint representation.

The consumer resolver walks the descriptor, resolves the discriminant first,
and visits only the selected alternative's fields. A reference or literal node
is resolved atomically; its contents are data, not further instructions.
Reconstruct nested records through their declared fields, retain whole lists,
then use the existing transport-value validator and canonical renderer. Missing
active data or an unknown tag fails before provider launch. Inactive references
are neither resolved nor prerequisites for the active value.

The typed-input contract owns normalization of this closed source shape;
prompt fragments consume that same contract for value slots. Runtime callers,
including phased prompt preparation, pass the complete source to one resolver.
Reference discovery inspects explicit source nodes, never literal payloads.
This does not change path-slot semantics, the pure-expression evaluator, or the
producer's result store. Emit and admit the new source only for target 2.28 or later;
preserve old-target lowering and the existing scalar/reference source kind.

Evidence: provider A returns each alternative of a union with disjoint fields;
provider B receives the complete active value without a manual `match` or file
bridge. Cover both ordinary `:inputs` and prompt value fills, empty payloads,
nested records/lists, absent inactive fields, imported procedure returns, and
malformed discriminants. A payload key named `ref` remains data, not a binding
instruction. Assert delivered data and no inactive-field reads, not literal
prompt wording. Run through public compile/run/resume, not just the renderer
helper. Retire redundant match-and-repackage code after parity is demonstrated.

Delivery evidence: the nine-case public E2E module covers clean and resumed
ordinary/fragment delivery, scalar/record overlap, empty alternatives and
malformed input. Independent spec and quality reviews passed. A maintained
consumer scan found no redundant match-and-repackage example to remove; existing
matches make real business/control decisions. This improves composability and
removes an authoring workaround from the test example, but establishes neither
ergonomic reuse across projects nor superiority to agent/SDK alternatives.

## Increment 2: Carry Rich Values Through A Complete Loop

Selected target: **2.29**, implemented in the development worktree with public
runtime/exhaustion/committed-resume evidence in implementation-plan Tasks 3–4.
Pure-only default resume without a prior semantic boundary remains unsupported;
this increment does not change that existing policy.

Admit already-transportable `List[record]` and `List[union]` values as whole loop
state fields, including inside the ordinary state record. The same value must
survive initial state, `continue`, `done`, committed-boundary resume, and explicit
exhaustion. A loop that cannot return its useful remaining work on exhaustion
has not completed this increment.

Target shape:

```lisp
(loop/recur
  :max 20
  :state (record Progress :remaining tasks)
  :on-exhausted
    (variant Outcome INCOMPLETE :remaining state.remaining)
  (fn (state)
    ;; Ordinary task selection and work; no new task-list primitive.
    ...))
```

Use the current target/type environment consistently for admission, boundary
projection, loop-frame contracts, result construction, and restore. Preserve
the complete element descriptor and tagged wire values. Carry a whole list;
do not flatten it into an index-specific set of fields or erase it to `Value`.
Existing loop-frame storage is the owner, not a new task queue or state service.
Keep its mapping-shaped `state_value`: named flattened projections retain their
existing keys; the empty key `""` denotes the anonymous whole-root projection
from exact artifact `state`. Source field names cannot be empty. Snapshot,
exhaustion selection, persisted-state comparison, and state overlay must agree
on this convention, including empty lists. No new checkpoint format is needed.

An imported updater inside a nested loop branch exposed a shared lexical-scope
gap: each branch retained only its immediate parent's local producers, dropping
the loop state from deeper branches. Astra reviewed owner-preserving lexical
forwarding as the correction at 2.29. Validation retains ordered enclosing
frames, each with its original artifact catalog and availability restrictions;
`parent` selects the nearest producer before checking its member. `self` remains
current-local and `root` root-only. Missing members cannot fall through. Proof
keys retain the defining catalog identity, not a merged forwarding view; two
same-named producers remain distinct while aliases of one producer agree.

Executable binding uses the same enclosing-frame search and binds the original
node ID through existing result addresses. Runtime uses those addresses and
current-iteration maps for both values and contracts, without falling back to
stale persisted results. Add no forwarding execution step, per-ref allowance,
or serialized scope form. Restrict compiler alias canonicalization to proven
same-owner aliases; preserve older-target semantics and generated identities.
This makes scope-owner provenance explicit in validation rather than hiding it
in merged dictionaries. Verify shadowing, inherited proofs, inaccessible sibling
branches, current-iteration absence, and genuine nested resume before closure.

The final workflow result boundary must accept the same existing transportable
value whether returned directly or wrapped in an ordinary record/union. Review
found an older catalog analysis forcing `allow_union=False` beneath collections
in wrapped returns. At target 2.29, validate complete **return** contracts through
the existing recursive descriptor/result owner, including ordinary non-loop
returns and imported/private return matching. Keep parameter admission unchanged
and preserve the old analysis for targets through 2.28. Do not add a loop-only
return flag, or rely on the shallow transportability predicate that accepts a
record before examining its fields. Illegal nested Provider/Prompt/Json/callable
types and path constraints still reject; active-variant metadata remains intact.

Gate these root-state corrections at this increment's selected target. Older
targets already admit scalar/root-list state but can persist an empty projection
map; applying new strict comparisons to them would invalidate old restores.
Use the existing workflow version during capture and restore, not another flag
or migration record. Under the new target, absent or mismatched root state is
an invalid checkpoint, not permission to skip comparison.

Compiler review also exposed two shared projection obligations. Preserve the
historical no-environment loop projection below 2.29: merely excluding a direct
`List[record]` still accidentally admits that list, or `List[Optional[record]]`,
inside a state record. Use the existing target gate at the shared projection
owner rather than a blacklist of nested shapes.

For record-wrapped unions, reuse the existing contract owner's union-output
activity metadata with the actual projection prefix/path. Carry it alongside
the existing root-union projection. Resolve a field's discriminant before its
payload: materialize known active fields, use existing typed internal placeholders
only for proven inactive fields, and preserve already-projected refs for an
unknown runtime tag. Sparse producer outputs require the existing discriminant
or match path before dereferencing. A body match's selected arm is not evidence
about an unrelated result union. Shared record/variant/local-value traversal
belongs in `lowering/values.py`, not a second loop-only path walker.

Seed, continue, done, exhaustion and final normalization must agree on activity.
In particular, an inactive relpath placeholder must not fail final normalization,
while an active missing path must still fail its authored contract. Keep internal
placeholder handling separate from strict authored output validation; attaching
metadata to an operation that ignores it does not establish this behavior.
The `materialize_artifacts` executor's new-target final-normalization path
consumes this metadata through the existing
structured-output discriminant/activity helpers before source resolution and
validation. Internal loop-frame projections remain total; final authored
projections may omit inactive fields. Do not replace active path validation with
a blanket relaxation or add another union predicate evaluator.
Two independent nested unions retain their own discriminants. This reuses the
existing metadata for supported flattened shapes; it does not introduce a new
ancestor-tag predicate language or flatten unions held inside whole collection
descriptors. Astra reviewed this correction after a disjoint nested-variant
counterexample defeated the initial record traversal patch. Implementation and
runtime evidence remain required.

Ordinary pure projection must obey the same activity contract. Computed records
and `record-update` cannot be routed around the pure evaluator merely because
they contain a union. At 2.29, derive activity through the shared contract owner
for generated and caller-supplied pure output contracts. Resolve each union
group's discriminant before reading or validating its fields; omit proven
inactive outputs and reject missing or invalid discriminants. Apply identical
behavior to fresh evaluation and reused pure-result bundles.

Use each `FlattenedContractField.source_path` to generate the existing
`output_bundle.fields` JSON pointer relative to the evaluated value under
`/result`. Runtime extraction and discriminant lookup consume that mapping;
they must not guess paths from `return__`, `state__`, or `result__` names.
Preserve explicit whole-root mappings and all target-2.28-and-earlier behavior.
This extends the generated projection contract, not the pure-expression schema.

Ordinary structural returns need this same owner. At target 2.29 and later,
`lowering/values.py` delegates returns requiring evaluation/materialization to
the existing pure projection, supplying concrete boundary fields and matching
output contracts. A direct-reference shortcut is valid only when it covers the
complete required projection; an empty or partial reference map cannot discard
literals. Resolve nested names, field accesses and constructors through the
shared inline-value traversal before consuming each structural path segment.
Literal `a__b` remains one field; only a real collision with nested `a.b` triggers
the existing projection-collision diagnostic. Imported/private returns and loops
use the same mapping. Preserve historical lowering through 2.28. Astra approved
this correction after valid two-union returns exposed the legacy constructor
walker; it may generate more ordinary pure projections, but adds no evaluator.
Implementation and direct/imported/loop execution evidence are still pending.

Keep evaluated values and persisted pure-result bundles canonical and sparse.
At every pure seed/state/result boundary, copy discriminants and universally
shared fields directly. For each independent union group, partition the other
fields by their declared activity sets. Emit sibling `if` projections: the
active branch copies guarded fields and the inactive branch emits the existing
typed placeholders. This adds one branch level, not a recursive else chain or
Cartesian product. Unknown activity permits neither a placeholder nor an
unconditional read from a sparse producer. Final authored output remains sparse
and strictly validated. The cost is extra generated conditional/projection
steps; no second evaluator, store, or implicit loop mode is introduced.

**Reviewed shared proof correction (implementation pending):** the original
assumption that existing guards suffice was disproved by one pure producer with
two independent unions. Producer-name-only proof loses both group and lexical
scope identity. At 2.29, extend the existing `requires_variant` contract with the
closed alternative `{ref, allowed}`: an ordinary scoped reference to a declared,
persisted union discriminant and a nonempty, duplicate-free list of its declared
variant names. Mixed old/new guard forms reject. Arbitrary enum artifacts are
not discriminants; the declared group/field metadata must agree. This is finite
variant membership, not an ancestor-predicate language.

Replace keys in the existing proof context with `(resolved producer identity,
declared discriminant artifact) -> possible variants`. Distinct lexical owners
remain distinct even when their display names match; `self` and `parent` aliases
of the same owner agree. A read needs a nonempty possible set contained in the
field's complete `active_variants`; contradictory refinement rejects. Match
cases refine the exact selector to a singleton. Independent groups never grant
one another proof. Preserve role, group, discriminant and activity metadata in
shared normalization, including materialized outputs that retain availability;
truly total internal frame outputs remain ordinary total contracts.
An inherited scalar materialization inherits its value constraints, not its
source's sparse availability: it has already resolved and validated that field.
Retained sparse materialization is declared by its explicit projection contract.

Shared validation, elaboration, executable lowering, and execution own this
correction. Bind guard refs with existing scoped output addresses, enforce the
same accessible/persisted/single-visit restrictions as field reads, and check
the exact current-iteration value before both top-level and nested execution.
Restore/replay uses those same addresses, not a persisted proof cache. Do not
search inaccessible artifacts, invent producers, guess aliases, or bypass the
shared validator. At 2.29+, legacy `{step, value}` requires one unambiguous root
discriminant; multiple groups require the precise form. Preserve all <=2.28
generated bytes and runtime behavior. This adds no opcode, expression schema,
or state schema. Astra approved the shared correction after scoped lookup alone
proved insufficient; Tasks 3–4 now record public run/resume evidence and the
review-driven runtime corrections.

Generated per-group conditionals inside ordinary loops use the existing
compiler-owned nested-`if` lane. At 2.29 the existing repeat ownership map also
records exact compiler-emitted repeat IDs with empty metadata when they have no
exhaustion diagnostic. Capture that map once from finalized lowering output in
both ordinary and WCC lowering; nested-`if` capture uses its membership rather
than the presence of a diagnostic field. Ownership and optional diagnostic
metadata are different facts. Do not manufacture a diagnostic to obtain
conditional support or infer ownership merely from the frontend name.

Shared validation requires each declared ID to identify exactly one emitted
repeat and its existing metadata to match exactly, including the empty case.
Empty declarations require this target and the Workflow Lisp frontend; present
diagnostic values remain validated. Preserve unknown-key, missing/duplicate-ID,
undeclared-metadata and undeclared-nested-`if` rejection. These existing side
tables end at validation: add no serialized ownership field, runtime operation,
checkpoint shape or general nested-match admission. Lower targets keep their
historical capture and bytes. Astra approved this correction after the original
diagnostic-key predicate missed deeper totalization conditionals in an ordinary
no-diagnostic loop.

Exhaustion should expose the last committed state through the same supported
value projections as ordinary loop exit. Reuse the existing construction from
the updated `continue` state and final-frame publication strategy; do not add
an exhaustion-time evaluator. The initial correction admits
direct state roots/fields and recursive ordinary record/variant packaging,
including renamed fields and existing scalar literals. A destination field need
not have the same name as its state source. Existing typechecking enforces the
types; no extra equal-name rule is appropriate. This does not admit arbitrary
computed/effectful exhaustion expressions. Existing scalar behavior and zero/empty-list
cases remain valid. A failed iteration is still a runtime failure, not a
successful exhaustion result.
Recursive packaging checks each leaf: a literal inside a wrapper is not a
reason to reject that wrapper as failing an all-fields-must-reference-state rule.

State restoration and final-result restoration are different operations. A
normal `done` result or exhaustion wrapper may differ from the state; root-list
results can use `__result__` rather than `return`. Restore final outputs through
their existing result bindings/artifacts, never an unconditional whole-state
fallback. For the new target, remove the shortcut that substitutes state solely
because a result variant matches the exhaustion variant. The result projection
already constructed from updated `continue` state covers exhaustion; normal
completion must preserve its own payload, even with the same variant name.
Keep old-target generated mappings unchanged.

This is not a one-line change to the admission predicate. Prove the full path
through loop projection, lowering, generated contracts, runtime resolution,
persistence, and export. If a descriptor cannot survive that path, repair the
shared owner or name the representation gap before widening acceptance.

Evidence: a provider produces typed tasks; an imported procedure carries and
updates the list for multiple iterations; both normal completion and exhaustion
return the actual remaining values. Exercise both root-list and record-contained
list state; their current snapshot paths differ and neither proves the other.
Include a union alternative change, empty/singleton lists, `record-update`, and
interruption after a committed iteration. Resume must preserve values and not
repeat completed provider work.
Include renamed/nested exhaustion packaging, normal `done` using the exhaustion
variant with different data, and rejection of an empty-root snapshot mismatch.
Keep an old-target empty projection snapshot as a compatibility control.
Malformed nested values must fail existing validation. Exercise the actual
public execution path with runtime data rather than constant-folded fixtures.

Top-level optional/map loop state and additional exhaustion expressions remain
explicit follow-ons, not accidental admissions. Expand them when a caller needs
them, using the same contracts; otherwise retain clear diagnostics. No recursion
or general task-graph engine is required for this increment.

## Increment 3: Reuse Pure Helpers Without Placement Penalties

Implement the existing pure-call composition target, independently of optional
effect annotations. A reducible effect-free inline procedure should work in a
record field, list element, pure map body, or pure function without manual
pre-binding or a duplicate `defun` wrapper.

The design owner already specifies resolution before normalization, exactly-once
argument evaluation, branch/element scope, imported specialization, and private
execution-boundary distinctions. Keep those contracts; do not merely remove
effect checks or add a special helper form for each consumer position.

Use the same small transformation in direct, aggregate, map, imported, and
resolved-hook positions. Compare with the explicit-binding control, including
an argument that fails if incorrectly evaluated, duplicated, or suppressed.
Effectful and unrepresentable private-frame calls retain honest refusals.
Remove the displaced wrapper/pre-binding ceremony from actual callers.

This increment can proceed independently of 1 and 2 with scalar examples;
combined acceptance then uses a rich task value. Effect inference ergonomics
remain under [EL-1](workflow_lisp_effect_ledger_simplification.md), not a
prerequisite or a substitute for expression composition.

## Increment 4: Portable Provider Context, Before Native Continuations

Implemented at target 2.31 for the supported ordinary Codex codec. The
[owning contract](workflow_lisp_provider_context_values.md) distinguishes this
slice from native/cross-provider proposals; the plan records actual usage limits.

Use the existing provider-context contract, beginning with ordinary calls and
portable capture/bind. Do not create a second memory API. The initial supported
content and coverage must be explicit, and capture must come from the adapter's
exposed conversation, not a model-authored approximation labelled as history.

Within that supported scope, a procedure receives context and returns both result
and context; another procedure can transform, branch, and bind the captured value
to a declared provider. The runtime owns the result/context pair and existing
storage owns its content. An unchanged call does no capture. A summary remains
an explicit lossy transformation; a context reference remains distinct from the
filesystem or a mutable session ID.

Prove a real capture and destination binding first, then ordinary imported
arguments/returns, aggregates, loop carriage, and two consumers of the same
snapshot. A different provider requires separate real transfer evidence. Report
unsupported content or explicit conversion; do not silently discard it. Use
increments 1–3 only where those actual compositions require them. Do not force
all context work to wait for every unrelated language improvement.

Native checkpoint capture/fork is a separate follow-on under the same owner,
not a prerequisite for useful portable context. Neither representation gets a
root-only exception that masquerades as a first-class value. Remove superseded
handoff packaging where capture genuinely replaces it; keep artifact handoffs
when they are simpler or carry information the provider never exposed.

## Increment 5: One Human Question As A Host Interaction

This is a new capability, unlike ordinary value composition. The target is one
host-mediated request operation: ask a question, wait without a live provider
process, receive an answer or explicit cancellation, and continue the same
workflow at that expression. Initial replies are text, with a distinct cancelled
outcome; structured forms and multiple simultaneous requests are not required.
The target permits one outstanding request per root at a time; sequential
questions are allowed after the previous request is consumed. An overlapping
request must be diagnosed, never silently replace the pending question.
The operation and its ordinary reply union must compose inside a procedure and
loop, not only at an entrypoint.

The implemented source spelling is `(request-input question)`, where `question`
has exact type `String`. It returns the ordinary closed builtin union
`HumanReply = ANSWERED(text String) | CANCELLED`. Astra reviewed this preparation
contract. Target **2.32** is admitted after the portable-context target 2.31.
Public CLI tests cover imported conversational loops, answer/cancel recovery
after downstream failure, and interruption after consumption before checkpoint
publication. The state/CLI/frontend specifications own current behavior.
Model it as one recorded `host-input` effect
through the normal compiler/runtime path, not a provider impersonating the user,
a busy polling workflow, or a hidden task scheduler.

The runtime records the pending question against its existing run/frame/visit
identity and suspends the run. Reuse the existing suspended run status and state
store where feasible; a pending request is not a crash or failed provider call.
The host lists the pending question and submits a response for that exact
request through one runtime API. CLI and interactive-agent integrations are
clients of the same API, not separate implementations. No new web UI is needed.

Response submission records data; ordinary resume continues execution. Resuming
without a response leaves the request pending. An identical repeated submission
is idempotent; a conflicting or stale response is rejected without overwriting
the accepted one. Once consumed, the reply is an ordinary value and completed
upstream work is not replayed. Cancellation is a caller-visible outcome, not an
invented answer. A request inside a loop has a distinct visit on each iteration.

The question cannot mutate the original run inputs or program identity. The
workflow explicitly incorporates the answer into its next brief/context value.
This distinguishes conversational continuation from changing an old checkpoint.
No arbitrary call-stack serialization, approval framework, or event bus is part
of the design.

### Reviewed Preparation Contract

Use one new leaf operation, `request_input`, with a typed question source and
the fixed reply contract. Thread it through the existing expression, inferred
effect, WCC perform, executable validation, and dispatch owners. Do not encode
it as a provider or a command. The new unparameterized effect follows the
existing subject-free effect pattern; this is not an effect-ledger redesign.

The concrete leaf contract below passed Astra re-review. Keep the operation
name `request_input` consistently through WCC and shared executable views; the
source/effect spellings remain `request-input` / `host-input`. WCC carries the
question as its ordinary typed positional operand. Before the atomic WCC boundary,
elaborate the question through existing body/prebinding and continuation
sequencing, retaining any prefix from a procedure call, `let*`, or control form.
The existing atomic elaborator rejects such prefixes, so later ANF alone is not
sufficient. Then use ordinary ANF/projection to obtain the literal/ref leaf.
Its existing result-type metadata identifies
the fixed builtin union; do not add a second descriptor payload when it can be
derived there. The shared leaf config is exactly
`request_input: {question: {literal: String}}` or
`request_input: {question: {ref: String}}`, using existing reference resolution
and dependency discovery. Validate exactly one source and its runtime String
value. No prompt template interpolation, provider options, bundle destination,
or per-question result type is involved.

Use the ordinary union artifact projection for the fixed reply: an answered
result exposes `variant = ANSWERED` and `text`; cancellation exposes only
`variant = CANCELLED`. The runtime validates the reply with the existing typed
value validator before atomic finalization. Compiler terminal refs and active
union metadata follow that same existing projection. The builtin type and
reserved form are target-gated, and the inferred `HostInputEffect` follows the
subject-free `RunsTrialEffect` pattern; its optional declared spelling is
`:effects ((host-input))`.

Extend the existing compiled-node result-contract owner for this bundle-free
operation: the fixed `variant` contract admits only `ANSWERED`/`CANCELLED`, and
`text` is String in the answered case. Member admission, durable dependency type
validation and value retrieval must use that contract, not just an artifact-name
allowlist. Validate the complete active reply before consumption; cancellation
never synthesizes or dereferences `text`. Preserve `returned_union_type_name`
and active-variant metadata through ordinary terminal binding. No provider bundle
or serialized descriptor payload is needed. Astra identified these replay and
pre-atomic sequencing obligations in its leaf-contract review.

Concrete propagation owners include the expression registry/traversal and type
prelude, WCC elaboration/defunctionalization, a leaf lowering function, shared
surface/core/executable types and conversions, persisted-surface encoding,
runtime-plan views, semantic coherence and dependency validation, and ordinary
plus loop executor dispatch. Use one operation-specific config, not fields on
all common step configuration. Register 2.32 only with the implemented capability;
an unimplemented intervening target must not be admitted merely to fill a number
gap. Input command registration lives in the existing CLI parser/dispatch and
commands package; it remains a thin client of the single runtime API below.
The explicit propagation map includes `workflow/elaboration.py`,
`workflow/runtime_plan.py`, `workflow/runtime_step.py`, `wcc/anf.py`, and
`workflow/pure_result_replay.py`; state serialization must handle the optional
root field in both `to_dict` and `from_dict`, omitting it when absent.

The read-only persisted workflow graph is a closed encoding, so this new leaf
requires `persisted_workflow_surface_graph.v6`; do not add it to v5 silently.
Select v6 exactly when a reachable step, nested body, finalizer or imported
workflow contains `request_input`. Otherwise retain the existing v5/v4/v3/v2/v1
selection and bytes. Unused imports do not select v6. Reachability includes all
retained control branches and actual transitive calls, independent of eventual
execution; existing unreachable-node rejection stays in force. The operation
map is required on `REQUEST_INPUT`, forbidden on other kinds, and gated by the
containing workflow node's target 2.32+, not just the entry's target. Reject null,
extra keys, both/neither sources and non-string payloads. A request-only graph
needs no provider context. Decoder shape, kind, target and graph-schema selection
must agree; diagnose `request_input_persistence_mismatch` before generic key
rejection hides that reason. Mixed
graphs retain provider-context, trial and Q2/Q3/Q5 carriage without relaxing their
individual contracts. This extends the graph reader, not the run-state schema,
question store or execution authority. Astra approved this bounded encoding
amendment; implementation and public target admission remain separate.

The authoritative root `RunState` has one optional `human_input` record, omitted
for old runs and unused workflows. It contains a persisted opaque request ID,
the existing root/frame/runtime-node/visit/loop identity, question text, status
(`pending`, `answered`, or `consumed`), and an optional typed reply. A UUID
allocated once at durable creation suffices; deriving another identity hash or
keeping a request registry is unnecessary. The existing state schema remains
compatible through this additive optional field; source and lowered admission
require the eventual selected target.

The closed record uses `request_id`, `resume_scope` (the existing
`{root_workflow_file, call_frame_ids}`), `runtime_step_id`, `enclosing_step`
(`{step_name, step_id, visit_count}`), `loop_iteration` (null or existing
`{kind, loop_step_id, iteration}`), `question`, `status`, and optional `reply`.
Reply is absent while pending, otherwise exactly the approved tagged answer or
cancellation. The containing root supplies run identity; nested states may not
own this field. Existing frame snapshots/cursors/visits remain ancestor authority,
not another copied suspended-stack record. Aggregate ownership validation alone
does not prove execution position: resume must also validate reached calls
against parent visits and loop progress before reusing them.

Retain the latest consumed record until another question replaces it. This
gives a bounded idempotency window: the identical reply to that latest request
is accepted even after consumption, while a conflict rejects. Once the next
request exists, earlier IDs are stale. An outstanding unanswered or answered
request cannot be replaced by a different request. Reaching the same suspended
leaf reuses its persisted identity and question; it does not create another
visit or silently change the question.

Use the existing root writer lock and aggregate-state transaction owner. One
transaction publishes the request, preserves the reached cursors, and marks only
the root run suspended. Reached child frames retain their existing incomplete
`running` status and cursors: they are resumable stack frames, not independently
running processes. The root request names the waiting leaf. This preserves the
existing same-frame retry-lineage selection without adding another frame status.
Submission reloads state under the
root writer lock, validates the exact request ID, and records an answer or
cancellation without running the workflow. Consumption publishes the ordinary
leaf result and marks that request consumed in one aggregate-root write. A
crash must not produce a consumed request without its result or expose an
unpersisted question. Nested state is already root-aggregated; do not add a
second request file, lock service, or independent frame-state authority.

Extend `StateManager._mutate_scoped_state` at its existing traversal owner to
accept root scope and a callback over the candidate root and reached state
chain; its present leaf-only, nonempty-path API cannot perform this transaction.
Reuse the aggregate ownership checks rather than treating their mutation lock
as a persistence transaction. Finalize a loop leaf using the existing
iteration-qualified result placement and dataflow rules inside the same write.
Do not return a result for later generic publication after marking it consumed.
Refresh live call-frame managers through the existing root-refresh helper after
success or rollback. After consumption, refresh the active deep-copied executor
state and retained call-frame projections before ordinary finalizers can publish
stale values. Suspension unwinds without further publication.

The reviewed private transaction interface retains the existing leaf
`commit_guard` and accepts exactly one of `mutation(leaf)` or
`scoped_mutation(candidate_root, reached_chain)`. Root scope is permitted and
has chain `(candidate_root,)`. Clone, traverse once, guard, mutate candidates,
rebuild bottom-up and write once. Callbacks never write or execute work.
Extract one non-writing `_apply_result_with_dataflow` helper in `state.py` and
route existing ordinary/loop/call-frame finalizers through it, preserving their
different guard and cursor-clear rules. Consumption invokes that helper inside
the scoped transaction; it cannot accept an arbitrary completion callback.

`workflow/human_input.py` owns record/query/submit/consume entrypoints.
`record_human_input(manager, ...)` derives scope from the existing aggregate
owner and returns a detached committed request. `get_human_input(run_root)`
reads the atomic snapshot. `submit_human_input(run_root, request_id, reply)`
loads inside the existing writer lock, writes only the accepted reply/status,
and never resumes. `consume_human_input(manager, request_id, *, result,
step_name, loop_name=None, index=None, <existing dataflow arguments>)` requires
an answered exact request, a successful result matching the complete reply,
and correct placement. Existing loop result keys differ from runtime node IDs;
validate both using the existing `IterationStepKeyProjection` and compiled nested
node ID supplied by execution. Check its frame key, presentation name and exact
runtime ID, then use `step_key` for publication; never derive the presentation
name from the runtime suffix. These are execution arguments, not new persisted
request identities. It publishes result/dataflow plus consumed/root-running state
in the same write, returning committed leaf state. Pending consumption fails;
already-consumed calls cannot republish results/dataflow. Re-entry at a consumed
identity uses ordinary completed-result replay, not another UUID.

Reuse existing scope/visit/loop value validators without fabricating a provider
attempt. Keep state-to-operation validator imports function-local. After write
failure reload the actual disk snapshot (a replacement may already be durable);
restore pretransaction state only if no snapshot exists. Refresh originating
call-frame managers in `finally`, after success or failure. Detached executor
state refresh is part of the implemented integration. This Astra-reviewed leaf adds
no independent traversal, store, lock, or generalized continuation service.

Expose a single query/submit runtime API with thin CLI clients:

```text
orchestrator input get RUN_ID
orchestrator input answer RUN_ID REQUEST_ID --text TEXT
orchestrator input cancel RUN_ID REQUEST_ID
orchestrator resume RUN_ID
```

The query returns structured request/status data; answering and cancelling do
not implicitly resume. Empty answer text is valid and differs from cancellation.
All input commands use the existing run lookup and `--state-dir` convention.
An unanswered resume validates the existing run and returns suspended before
the execution prologue can dispatch work. An answered resume reaches the same
leaf, validates its frame/node/visit, and consumes the recorded reply.

Reuse validated visits for every enclosing call/loop on the request's scope
chain before the executor increments visits or starts a new step, not just for
the final request leaf. A loop leaf uses its enclosing cursor/visit and existing
iteration-qualified runtime node ID: nested loop steps have no independent
top-level cursor. Do not put a nested node into top-level `current_step` or
allocate a replacement call frame before matching the pending request.

Propagate a dedicated `HumanInputSuspended(Exception)` through nested execution.
The executor's generic step exception handler must re-raise it without calling
`fail_run`; only the root catches it and returns the committed suspended state,
without a completion/failure epilogue. This bypasses the current child-call
conversion of non-completed results into failures. Calls and loops preserve
their cursors and completed work. Keep SIGINT handling unchanged. This is a
control transfer for one durable operation, not arbitrary stack serialization.

Suspension alone proves none of these paths. Regression evidence covers question/answer, cancellation,
restart while waiting, duplicate/stale submission, and two sequential questions
inside an imported loop without replaying preceding provider calls. Update the
CLI/state/effect contracts together when this new capability is accepted.
Inject failed writes during publication and consumption; assert no consumed
record lacks its finalized result. Check root suspension, running child frames,
and unchanged ancestor/leaf visits and frame IDs across unanswered and answered
resume. Keep existing checksum and bound-input validation intact.

Completed replies use the existing lexical checkpoint mechanism, with one
closed `reuse_validated_human_reply` policy (Astra-reviewed integration amendment,
2026-09-22). Its only requirement is
`human_reply: {result_contract_digest: ...}`, derived from the fixed reply
contract; both effect and boundary kinds must be `request_input`. A completed
reference contains the existing base identity, `evidence_kind: human_reply`,
the fixed contract digest and the canonical digest of the complete committed
artifact mapping. Reuse existing checkpoint scope/frame/iteration identity;
do not copy the request record or reply into another store or invent a bundle.

Collection prefers the committed leaf result supplied by the atomic finalizer.
Authoritative validation resolves the exact runtime node/visit in the validated
scope through existing state/iteration projections, requires one completed
candidate, validates the complete `HumanReply`, and compares both digests.
Neither a matching display name nor the highest visit is sufficient. The latest
root request is not historical authority: a later question replaces that record,
but does not invalidate earlier durable replies. Missing or mismatched evidence
fails closed; pending/answered requests retain the dedicated host-resume route.
No existing provider/command policy is repurposed: those require real bundle
evidence, whereas a human reply is a bundle-free durable value.

Admission evidence includes a provider-free question followed by downstream failure
and resume, two sequential questions, exact call/iteration identity, malformed
or missing artifacts, and interruption after atomic consumption but before
checkpoint publication. That interruption may recover the durable result or
fail closed, but must never issue a replacement question.

Until then, progressive execution retains its explicit `NeedsInput` return and
new invocation. It must not pretend that current `resume` accepts human answers.
Provider context may improve the information shown with a question, but is not
a dependency of asking one.

## Compatibility, Proof, And Consequent Simplification

Use a target-aware contract at every affected boundary. Do not globally relax
validators, erase types, or silently change historical accepted representations
to make a new example pass. Implementation planning chooses each increment's
version boundary, recorded in its package section. Preserve old
target fixtures and existing persisted runs. For newly admitted shapes, prove
compile/run/resume with the complete descriptors and actual execution path.

The first three increments aim to reuse existing execution forms. That is an
architecture target, not established proof: if it needs a shared contract/schema
extension, name and review it instead of inserting a workflow-specific branch.
Context and human input have genuine new invocation/state responsibilities;
their existence must not expand the scope of simpler corrections.

After each increment, adapt the concrete coordinator and inspect what disappears:
manual union repackaging, task serialization, repeated state copying, duplicate
helpers, hand-built conversation packets, or manual question/restart glue. Keep
the simpler application when an abstraction adds no practical value. Assess
ergonomic reuse through actual edits and reasoned review, not a fixed pass count.

All five axes remain distinct: composition must work end to end; reuse must
reduce caller burden; inspection must expose actual values and decisions;
self-programming benefits from simpler ordinary source; program-space search
needs useful alternatives and task-level evaluation. None is established merely
by passing a minimum fixture. Improve recurring gaps at their shared owner,
reconsider types/callable roles/recursion if justified, or retire machinery that
does not earn its cost. Interface repair is ordinary development, not dependent
on an experiment budget.

## Documentation And Handoff

Increment 1 updates provider-input/rendering contracts and the consumer-value
owner; increment 2 updates loop/value projection, state, and frontend contracts;
increment 3 follows EC-1; increment 4 follows PC-1; increment 5 updates host-I/O,
CLI, state/resume, and frontend/effect contracts. Normative specs change only with
accepted contracts, not by copying these sketches into current guidance.

For each selected increment: resolve its named feasibility questions, implement
at the existing owner, run narrow boundary tests, then a public-entry integration
check and proportionate regressions. Add real adapter evidence for context and
host interaction evidence for questions. Do not launch the research experiment
or rewrite the coordinator as a prerequisite for a compiler/transport fix.

The [drafting plan](../plans/2026-09-22-value-and-continuation-composition-design-plan.md)
records this documentation task. The separate
[implementation plan](../plans/2026-09-22-value-and-continuation-composition-implementation-plan.md)
breaks the target into independently deliverable packages, with explicit
preparation tasks for unresolved normalization, adapter, and host-I/O contracts.
The owner requested execution of that plan on 2026-09-22. This design remains
the target contract, not an implementation schedule or research allocation.
