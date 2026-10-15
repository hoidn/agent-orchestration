# Workflow Lisp Provider Context Values: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_provider_context_values.md](../../design/workflow_lisp_provider_context_values.md).

### Reviewed Portable Ordinary-Call Slice

Astra reviewed the representation and shared owners on 2026-09-22. Start with
materialized inline JSON, not a mandatory blob handle. Existing typed transport
already supplies persistence, recursive validation, a depth limit of 64, and a
16 MiB value limit. Reject oversized captures explicitly. Deferred content
references remain a future option when a real caller exceeds this bound; the
initial value has no loader, dangling run-local handle, or separate lifetime
registry. Copy/export of the value carries its content bytes.

The closed schema uses ordinary records and unions:

```text
Context {
  schema: String,                    // exactly "portable-context.v1"
  events: List[ContextEvent],
  coverage: List[ContextCoverage],    // per source origin
  lineage: List[ContextTransform]
}
ContextOrigin = CAPTURED(provider: String, attempt: String)
              | AUTHORED(label: String)
ContextEvent = TASK(origin, sequence: Int, text: String)
             | ASSISTANT(origin, sequence: Int, item_id: String, text: String)
             | COMMAND(origin, call_sequence: Int, result_sequence: Int,
                       item_id: String, command: String, output: String,
                       exit_code: Int)
             | FILE_CHANGE(origin, sequence: Int, item_id: String,
                           status: String, changes: List[ContextFileChange])
ContextFileChange { path: String, kind: String }
ContextCoverage {
  origin: ContextOrigin, scope: String,
  retained_kinds: List[String], omitted_kinds: List[String],
  conversions: List[String]
}
ContextTransform {
  sources: List[ContextOrigin], operation: String, loss: List[String]
}
```

Each event's `origin` has type `ContextOrigin`. Captured attempt identity comes
from the existing run/frame/step/visit/attempt owner; do not create a second
identity registry. Sequence positions are nonnegative positions within that
origin's exposed trace; a command's completion follows its call. TASK identity
is its origin/sequence; assistant/command identity is origin plus source item ID,
not a globally unique item ID assumption. File-change identity follows the same
origin/item-ID rule. Each source position is unique across message, file-change
and command endpoints within an origin. The event list governs authored
presentation order; sequence positions remain source provenance. Capture emits
messages and completed exchanges in their completion order, retaining both
command positions to expose intervening messages. Reordering is an explicit
transformation, not a rewrite of captured positions. Origin coverage must account
for every event; duplicate or
inconsistent origin declarations, item identities, or relationships reject.
Authored origin annotations remain claims. Construction and pure transformation
use ordinary records/unions, preserve relationships, and record source origins,
operation and explicit loss. These are provenance claims available to pure code,
not exact parent content digests that ordinary expressions cannot compute.
Exact input/output value identities remain owned by runtime dependency tracking.
Binding derives canonical content identity through that existing owner; no pure
hash builtin or self-maintained digest field is required. Selecting unchanged
captured events preserves origin; editing captured payloads creates AUTHORED
events with transformation lineage rather than retaining a captured-content
claim. Capture preserves the inherited coverage and transformation lineage.

First adapter: installed **Codex 0.155.1**, using the existing `codex exec --json`
transport and `ProviderExecutionResult.raw_stdout`. Target 2.31 implements
opt-in closed event decoding in the existing session codec, with declared
coverage limited to exposed task/assistant/command/file-change history, not all
possible Codex activity. `CodexExecJsonlAccumulator` still normalizes ordinary
assistant output/session metadata; that normalization alone is not capture.
The closed first codec accepts these envelope/item families:

| JSONL event/item | Capture behavior |
| --- | --- |
| `thread.started`, `turn.started`, `turn.completed` | Validate fresh thread/turn settlement, then omit transport/usage bookkeeping explicitly. |
| `item.started`, `item.updated`, `item.completed` for `agent_message` | Validate item identity/type lifecycle; retain the completed text as ASSISTANT, omit interim transport updates. A completed message need not have a start event. |
| Same three item envelopes for `command_execution` | Require start before updates/completion; retain start/completion positions, command, final aggregated output and exit code as COMMAND. Completion is authoritative for output. |
| Item envelopes for `file_change` | Validate start/update/completion lifecycle; starts and updates have `in_progress` status. Retain completion position, item ID, terminal status (`completed` or `failed`) and source-ordered path/kind rows as FILE_CHANGE. A completed item may lack a start; unmatched updates, incomplete items and unknown kinds reject. |
| Same three item envelopes for `reasoning` | Exclude explicitly from exposed task/assistant/command coverage; never label the context a capture of hidden reasoning. |
| `turn.failed` or `error` | Fail the capture/call; no successful pair. |
| Any other envelope or item kind | Reject as unsupported; never infer that it is ignorable bookkeeping. |

Unknown conversation item kinds, unsupported content, malformed or incomplete
command lifecycles, and conflicting terminal items fail capture. Do not silently
drop MCP, image, or other unsupported events. Supporting them later
requires their schema and adapter evidence, not a generic opaque payload escape.

The FILE_CHANGE addition was Astra-reviewed after a real capture failed on the
agent's ordinary result-file write. It follows the pinned
[Codex 0.155.1 event schema](https://raw.githubusercontent.com/openai/codex/rust-v0.155.1/codex-rs/exec/src/exec_events.rs),
which supplies paths/kinds/status, not patch bytes. Kinds are exactly `add`,
`delete`, or `update`; preserve paths verbatim and rows in source order without
reading files, resolving paths, or deduplicating. Empty change lists are legal.
Failed patches are retained tool outcomes, not evidence of which writes took
effect. All envelopes must pass shared lifecycle/identity checks, including
conflicts with omitted reasoning items. A second real probe exposed a stale
completion-only comment in that schema: the pinned
[JSONL event publisher](https://raw.githubusercontent.com/openai/codex/rust-v0.155.1/codex-rs/exec/src/event_processor_with_jsonl_output.rs)
emits starts and preserves their ID at completion. Capture accepts that actual
lifecycle; a nonterminal completion still rejects. Intermediate metadata is
transport state, not a separate captured file-change result.

Coverage retains FILE_CHANGE. When one occurs, record the conversion marker
`codex-file-change-metadata-only`: all declared terminal payload fields were retained,
with start/update transport collapsed into the completed event,
but patch/diff bytes are unavailable in this transport and no restorable
filesystem state is supplied. This is not omitted source content or claimed
transformation loss. The ordinary binding preserves this coverage.

The runtime supplies the exact composed current-call task before history
insertion, since JSONL does not echo it. Retain inherited events exactly once,
then append this call's task and exposed events under its new origin. Do not
parse rendered prompts to recover context or recapture a quoted seed as a new
task. Binding starts a fresh Codex call and renders structured history as quoted
data with declared role/rendering conversion. The separately composed current
task, tools, result schema and output destination still govern. This proves
portable content delivery, not native conversation reproduction or guaranteed
model adherence.

An input-plus-capture call appends a `bind-as-quoted-json` lineage entry naming
the inherited coverage origins. Its empty loss list means no portable event
payload was discarded; it does not claim preservation of native message roles
or provider continuation state. The prompt identifies the payload as historical
data, with current-call instructions and output contracts kept separate.

The original adapter feasibility probe used two fresh calls through the
existing provider executor, explicitly selecting Terra. It captured a real
`command_execution` start/completion pair reading a dummy marker, then delivered
the structured history to a fresh call; the second call extracted the marker
without executing a command. Its temporary artifacts under `/tmp` were not a
durable dependency. That early probe established the history substrate only.
Since then, the public target-2.31 `.orc` capture/bind path and a real normal-tools
Codex capture/fresh-bind have been verified; see the
[composition implementation plan](../../plans/2026-09-22-value-and-continuation-composition-implementation-plan.md#d-portable-context-pc-1-ordinary-call-slice)
and [context carriage tests](../../../tests/test_workflow_lisp_provider_context_e2e.py).
Neither that evidence nor the early probe proves cross-provider transfer or
native fork.
[Official noninteractive documentation](https://learn.chatgpt.com/docs/non-interactive-mode)
also describes JSONL thread/turn/item events. Installed OMP 18.1.14 differs from
the repo's supported pin 17.3.4, so it is not an advertised second adapter; no pin
was relaxed. Cross-provider transfer and native fork remain unproved.

One shared type-instantiation owner must construct `Contextual[T]` for parsing,
capture typing, substitution and canonical rendering. Reuse ordinary recursive
descriptors. Extend existing parametric inference through record fields so a
generic parameter is inferable from a wrapper-only argument. Substitution must
rebuild the concrete name **and definition** (`Contextual[Int]`, not stale
`Contextual[T]`) before specialization renders/reparses signatures. Keep the
model result type `T` distinct from the expression result `Contextual[T]` across
WCC and lowering; the model never writes the wrapper.

Publish two **atomic typed artifacts**, `result:T` and `context:Context`, in the
existing provider step result and one existing dataflow finalization transaction.
Validate the complete `Contextual[T]` pair against the ordinary size/depth limits
before commit, including the wrapper's added nesting; separately valid members
are insufficient if the combined value cannot be passed or returned.
Do not flatten nested `T` paths into `__`-joined wrapper names: legal fields such
as `a__b` and nested `a.b` collide. Preserve or reconstruct the already validated
typed result document from the output-contract owner, rather than rereading a
mutable result file after validation. Failed capture publishes neither artifact.

For capture only, derive the existing `output_bundle` representation with exactly
one mandatory `__result__` field at JSON pointer `""`, carrying the complete
recursive schema of `T`, including record and union roots. Do not use
`variant_output` or conditional projection for this model-facing contract. The
model still writes `T`, never `{result, context}`. The existing output validator
returns validated `T` under `__result__`; runtime consumes that value and publishes
only `result` and `context`. Uncaptured provider and command contracts stay
unchanged. Shared validation compares canonical transport schemas rather than
nominal enum/path names reconstructed by schema decoding.

Use the existing prompt-schema renderer for nested records, variants and
collections, preserving authored field/variant guidance. Retain root declaration
attribution and nested validation paths; do not promise declaration-level
attribution for every nested field. Root `Bool` retains existing bundle parsing,
including string-to-boolean conversion, whereas nested structural values require
actual JSON booleans and exact record/variant keys. This deliberate stricter
structural contract preserves typed `T`, not every permissive flattened input.
Astra approved this capture-only representation. It avoids a new validated-
document API, at the cost of recursive prompt/guidance support and root-centered
diagnostics. Target 2.31 also verifies imported/private whole-value carriage in
the supported positions; flattened-path collisions remain rejected below.
Structural rendering does not depend on capture: with or without it, a record or
union inside a list, optional or map renders its fields, or its discriminant
and variants, at every depth. The nominal `record_name` and `union_name` lines
render only under portable capture (`specs/versioning.md`, exceptions to target
stability). Target 2.31 shared validation admits complete structural
schemas at an output bundle's single root pointer and validates nested field
guidance. Computed Context materialization uses that same generic whole-root
schema path.

Whole structural references feed the pure evaluator's typed `field_access` in
the target-2.31 path; record-reference projection uses that shared route, not
context-specific prefix splitting or another evaluator.
Existing private-return projection may still join field paths with `__`.
The broad `__`-prefixed key filter in `pure_projection._runtime_binding_value`
has been replaced with exact compiler-metadata filtering; unit and public
execution checks preserve legal user fields. These were shared pre-existing
defects, not reserved user syntax. Target 2.31 preserves whole-value projection
through the verified imported/private/aggregate routes. The existing private
flattening representation rejects a real collision such as `a__b` beside
nested `a.b`; provider capture preserves those distinct shapes. Do not describe
private carriage as transparent for that rejected case or add ambiguous
flattening to the two-artifact publication path.

At target 2.31+, shared private-boundary admission uses the existing complete
transportability predicate with the procedure's defining type environment.
Generic templates stay compile-time until monomorphic specialization. When a
captured pair supplies whole record artifacts but a private call or loop seed
needs flattened leaves, materialize the existing typed pure projection before
that boundary. Do not invent nested artifact references or a Context-only
boundary kind. Older targets retain their prior admission and binding shape.
Private calls still require explicit bindings in expression positions excluded
by pure-call composition; `(let* ((copy (keep state))) (done copy))` is the
supported loop form, not implicit normalization of `(done (keep state))`.

Initial clauses are `:context <Context expression>` and
`:capture-context :portable`, on ordinary calls only. Reject native selection,
phased/peer/supervised/adjudicated capture, unsupported adapters, and simultaneous
`:session-artifact` publication. Omission preserves existing bytes/behavior.
The admitted DSL target is 2.31, following independently selected composition
targets 2.28–2.30. The compiler's
context dependency and capture selection use one optional ordinary-provider map:

```text
provider_context: {
  input?: {ref: String},
  capture?: "portable",
  result_descriptor?: <existing normalized descriptor for T>
}
```

Require at least input or capture; require the result descriptor exactly when
capture is selected. It describes model result `T`, agrees with
that call's whole-root output contract, and is not the wrapper descriptor. Fixed
Context schema and fixed artifact names need no extra configurable descriptors
or names. Unknown keys, wrong target/provider kind, conflicting session
publication, and malformed/unavailable/wrongly typed input reject before launch.
Computed construction/transformation uses existing typed pure projection to
materialize a whole Context; direct whole-value references use the existing ref
resolver. No new source carrier or dependency registry is introduced.

This documented map is the source/persisted representation. Executable lowering
parses `input.ref` with the scoped reference catalog and replaces only that value
with an existing bound address. Runtime resolves the address; ordinary recursive
dependency discovery can then see a context-producing pure projection. Semantic
IR retains the source map, checks it against Surface authority, and compares the
executable map against an independently shared-lowered Surface projection. With
context present, missing Surface authority is an error. Reuse the existing
lowering pass once for that check, including owner-specific proof allowances;
do not derive semantic authority from the executable map or add a second resolver.
The cost is a second lowering pass for context-bearing coherence checks; expose
the existing binding traversal only if that cost becomes material.

Shared structured-reference projection preserves complete recursive schemas for
inputs and step/branch/loop/call outputs, alongside availability/proof metadata.
Compare the context input with the fixed full descriptor, not merely `record`.
One shared derivation supplies capture's two artifact contracts to the validation
catalog and replay owner. Those replace exposed model-field artifacts for the
capturing step; the model-facing whole-root bundle contract still describes T.
Check descriptor/output-contract agreement before launch and adapter capability
after configured-provider resolution, not by an authored provider name. Astra
approved this binding/contract decision; public runtime verification is recorded
in the composition implementation plan.

Parser/traversal/typechecking retain `context_expr` and static `capture_context`;
WCC and `LowerableProviderResult` retain a typed operand plus selection and the
resolved model-result descriptor, separate from the expression wrapper type.
Propagate the same map through `workflow/elaboration.py` into `SurfaceStep`,
`CoreProviderStep` conversions/serialization, `workflow/lowering.py` into
`ProviderStepConfig`, and `PersistedSurfaceStep` encoding/decoding. There is no
`SurfaceProviderStep` class; enforce ordinary-provider-only admission on the
shared surface/persisted structures and keep the field out of `StepCommonConfig`.
Omit absent fields to preserve unchanged calls. Include `runtime_step.py` mapping
iteration/access, semantic provider projections/coherence, shared validation,
and reference/dependency discovery; otherwise persistence or execution can lose
the operand even when frontend typing succeeds.

The closed dashboard/read-only graph encoding needs
`persisted_workflow_surface_graph.v5` for optional `PersistedSurfaceStep.provider_context`.
Select v5 iff context occurs in the reachable serialized graph, including nested
control and finalization; unused imports do not count. Otherwise preserve the
existing v4/v3/v2/v1 selection and absent-field bytes. Decoding rejects context
in older schemas and v5 without context, and deeply freezes present maps.
Reuse shared map/descriptor validation: ordinary provider, node target >=2.31,
closed keys and descriptor/capture pairing; nulls and phased combinations reject.
Extend existing trial, Q3 (including older fragment schema), and Q5 schema
memberships to v5 without relaxing their target/pairing/authority checks.
Graph-level coexistence does not permit incompatible features on one step.
Adapter support, context-ref availability/type, session publication and result
agreement remain executable-validation responsibilities, not reconstructed
dashboard authority. Existing supported-schema consumers need v5 acceptance;
no run-state schema or execution-persistence owner is added. Context-bearing
artifacts require an updated reader; unchanged graphs retain their wire format.
The v2.31 implementation delivers this closed graph encoding with the ordinary
portable context surface; it does not deliver native continuation or broader
provider forms.

Insert quoted history through the existing prompt-composition owner **before**
final prompt identity is sealed; recorded Q3 evidence must match the actual
invocation. Internally use the existing fresh session-capable Codex JSONL command
without publishing a session artifact or enabling mutable session resume. The
existing codec owns decoding and the existing finalizer owns state publication.
Runnable failing contract tests precede implementation; the real probe is not
a substitute for public typed-value proof.

The original proof list beyond the live adapter probe has been addressed for
the shipped slice: wrapper-only generic inference and mismatch refusal; root
Bool/union/record results; legal `__` fields; whole-record projection; imported
and private helper carriage; list/loop carriage; capture/precommit failure;
committed-boundary resume; changed-input identity rejection; and fresh branches
from one immutable seed. The collision case between a literal `a__b` path and
nested `a.b` is deliberately rejected at private flattened boundaries; provider
capture itself preserves both shapes. Cross-provider and native claims remain
unproved.
