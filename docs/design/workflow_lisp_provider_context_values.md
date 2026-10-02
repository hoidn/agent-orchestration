# Workflow Lisp Provider Context Values

- **Status:** portable ordinary-call slice implemented at target 2.31; native continuation remains proposed
- **Kind:** language and provider-boundary architecture decision
- **Owner:** Workflow Lisp frontend and provider/runtime boundary
- **Created:** 2026-09-08
- **Last material update:** 2026-10-01
- **Implementation target:** 2.31 for portable ordinary calls in the
  [composition implementation plan](../plans/2026-09-22-value-and-continuation-composition-implementation-plan.md#d-portable-context-pc-1-ordinary-call-slice);
  source/runtime support includes imported generic/private carriage, collections,
  loops, pure context edits, independent branches and committed-boundary resume.
  Real Codex capture/fresh binding is verified. Private flattened boundaries
  still reject colliding paths such as `a__b` and nested `a.b`; native
  continuation and other adapters remain unselected.
- **Roadmap:** [PC-1](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#pc-1--first-class-provider-context-pending-unselected)
  research/utility selection remains pending and unselected. The bounded
  target-2.31 implementation above was delivered separately; native support,
  additional adapters, and later improvement or retirement require their own
  selection and allocation.
- **Review and drafting record:** [design plan and comparative simulation](../plans/2026-09-08-provider-context-design-plan.md)
- **Incremental integration:** [value and continuation composition](workflow_lisp_value_and_continuation_composition.md); its Increment 4 starts with portable capture/bind under this contract, keeping native continuation and human input independent.

## Summary

Make accumulated provider context an explicit, immutable value that a program
can receive, inspect where representable, transform, return, and bind to another
provider call. Separate that context from the provider executing the call and
from the external environment in which its tools operate:

```text
invoke(provider, context₀, task, current-call-contract)
    → { result: T, context: context₁ }
```

The call is still effectful and its answer is not deterministic. The change is
that conversational dependencies become explicit dataflow rather than hidden
mutable session state. Reusing `context₀` starts independent conversational
branches; it does not resume and mutate one shared session twice.

Target 2.31 implements the portable ordinary-call slice for supported Codex
calls. Native continuation, cross-provider transfer, and other adapters remain
proposals; use the [capability matrix](../capability_status_matrix.md) and
[authoring guide](../lisp_workflow_drafting_guide.md#portable-provider-context)
for the current scope and copy-safe example.

Portable history and opaque native continuation are different representations
with different promises. This is not universal memory, live-process cloning,
workspace transfer, or a claim to capture a model's hidden internal state.

## Context And Authority

The original design inspected behavior on 2026-09-08. The implemented portable
slice is now owned normatively by [Providers](../../specs/providers.md) and
[Step IO](../../specs/io.md); broader native/cross-provider proposals below are
not implemented capabilities. The table records the starting owners and limits.

| Existing owner | Reuse and limitation |
| --- | --- |
| [Providers](../../specs/providers.md), [provider types](../../orchestrator/providers/types.py), [executor](../../orchestrator/providers/executor.py) | Existing preparation, execution, capability declarations, and session codecs are the adapter boundary. Resume support alone does not prove immutable snapshot, export, or fork support. |
| [DSL](../../specs/dsl.md), [provider expression parsing](../../orchestrator/workflow_lisp/expressions.py), [effect lowering](../../orchestrator/workflow_lisp/lowering/effects.py), [session-artifact tests](../../tests/test_workflow_lisp_session_artifact.py) | At the original 2026-09-08 inspection, target-2.27 `:session-artifact` published a fresh scalar handle separately from the typed result, and `provider-result` had no first-class context input. Target 2.31 adds the portable ordinary-call clauses below; a handle alone is still not captured content. |
| [OMP templates](../../orchestrator/providers/omp_templates.py), [CLI contract](../../specs/cli.md) | Foreground session bridging and native CLI features are distinct from ordinary workflow calls. OMP template `resume_command=None` cannot be treated as existing workflow rebinding support. |
| [Prompt calculus](workflow_lisp_prompt_calculus.md), [Step IO](../../specs/io.md) | Reuse current-call composition and output-contract ownership. Q3's content-free provenance is not conversation content and must not be repurposed as an export format. |
| [Transportable Value](workflow_lisp_transportable_value_type.md) | Existing strict-JSON carriage supplies the portable slice's storage and recursive validation. Target 2.31 proves supported imported generic, aggregate, collection and loop carriage; `Value` remains opaque and is not an implicit `Context` cast. Private flattened boundaries still reject colliding field paths such as `a__b` and nested `a.b`. |
| [Executable IR](workflow_lisp_executable_ir.md), [Semantic IR](workflow_lisp_semantic_workflow_ir.md), [State Layout](workflow_lisp_state_layout.md), [State](../../specs/state.md) | Preserve the WCC/shared-Core/validated-executable path, derived semantic explanations, generated paths, call-frame lineage, and completed-boundary reuse. Provider context is not private execution `RunCtx`. |
| [Language principles](workflow_language_design_principles.md) | Explicit dataflow/effects, real procedure composition, structural types where sufficient, opt-in stronger constraints, and runtime-owned deterministic work govern this proposal. |
| [Provider prompt queue](workflow_lisp_provider_prompt_queue.md) | A separate target for sequential native-session turns with one final typed result and recorded turn progress. Atomic result publication does not imply whole-conversation replay. It neither implements nor blocks portable context; reuse the same adapter/codec owners. |

## Problem, Goals, And Boundaries

An investigation can produce both an answer and useful accumulated working
context. At this design's 2026-09-08 starting point, a reusable workflow could
pass declared artifacts or author a handoff, but could not express an ordinary
captured value; a scalar session handle left selection, portability, branch
isolation and lifetime outside the value contract. Target 2.31 now implements
the bounded portable ordinary-call slice below. Native continuation, other
adapters, and unproved event kinds remain outside that delivered scope.

Long-term design goals (the shipped target-2.31 slice covers supported Codex
ordinary calls and the carriage positions listed below):

- Pass context through ordinary procedure arguments/returns, imported modules,
  records, collections, conditionals, and loop-carried state.
- Continue with the same provider or explicitly transfer representable content
  to another; distinguish exact preservation from conversion and loss.
- Branch from a settled snapshot without sibling conversational leakage.
- Explain which captured content and transformations informed a call.
- Make context-building policies available to ordinary composition and future
  program optimization without requiring a separate memory language.

Non-goals: automatic relevance selection, a retrieval/vector database, global
agent memory, direct tool scheduling, preserving credentials/processes/jobs,
automatic workspace merging, deterministic model reproduction, or unrestricted
access to hidden provider reasoning. Tool use remains delegated to providers and
agents. Execution safety is not the rationale or an effectiveness axis here;
existing platform contracts are neither expanded nor removed by this proposal.

## Consequences Of The Decision

| Layer | Consequence | Main cost or limitation |
| --- | --- | --- |
| Conceptual | A workflow programs the evolution of explicit conversational state, not just a graph of answers. A reusable procedure can return work plus the means to continue it. | Context is a dependency, not truth or the entire world state; preserving a mistaken premise can worsen later work. |
| Language design | Target 2.31 makes the fixed portable `Context` and `Contextual[T]` ordinary typed values for the supported carriage positions; provider calls can consume or capture them. | The private flattened-path collision case remains rejected; this does not promise arbitrary transport or native continuation. |
| Implementation / architecture | The shipped Codex ordinary-call path captures and binds portable content through existing provider, validation, artifact, and checkpoint owners. | Cross-provider import, native branching, and event kinds outside the closed codec still need separate adapter evidence. A session-ID alias is insufficient. |
| Frontend / authoring | Target 2.31 adds ordinary `provider-result` clauses, wrapper typing, context projections, and WCC/lowering/resume carriage for the supported slice. | Syntax alone does not deliver broader provider forms or native continuation; those need their own contract and proof. |
| Practical use | Reusable investigations, alternate approaches, targeted handoffs, and context-policy experiments become directly expressible and auditable. | Storage, export latency, repeated input tokens, contamination, and adapter limitations can outweigh the benefit. Existing SDK/agent handoffs are the comparison, not a straw-man stateless call. |

## Decision And Alternatives

The design distinguishes immutable `Portable` and `Native` cases. Target 2.31
implements the portable record and ordinary-call input/capture specified below;
native remains proposed. Captured context returns alongside, not inside, the
model-authored result contract. Use ordinary data transformations and reusable
procedures before adding specialized operators.

Alternatives:

1. **Only pass artifact packets.** Already practical and the baseline. Use it
   when sufficient. It does not itself capture accumulated provider history or
   define native branching; do not build this feature without a consumer that
   benefits from those additions.
2. **Pass mutable session IDs.** Smallest transport patch, but two consumers
   then mutate hidden shared state. Keep existing session compatibility; do not
   call that value semantics or independent branching.
3. **Normalize everything to plain text.** Useful as an explicit handoff
   conversion, not a lossless common representation. It discards message/tool
   structure, modality, and native continuation state.
4. **Universal memory object/service.** Adds retrieval, retention policy,
   implicit updates, and orchestration outside ordinary dataflow. No selected
   requirement justifies it.

The intended clean foundation is one provider invocation owner, one immutable
value/lineage path, and provider-specific codecs at the edge. Do not implement a
new context API as a facade over authored shell-resume workflows.

## Semantic Contracts

### Values And Representation

Target 2.31 implements the closed portable `Context` value, distinct from
`String`, opaque `Value`, and execution `RunCtx`. Native remains a proposed
semantic case. The longer-term logical representation is:

```text
Context = Portable(content, coverage, lineage)
        | Native(checkpoint, compatibility, coverage, lineage)

Contextual[T] = { result: T, context: Context }
```

`Context` and `Contextual[T]` in the portable slice use the fixed ordinary
record schemas below; `Contextual[T]` resolves to `{result:T, context:Context}`.
Existing authored records are not generic: this builtin constructor does not
add general generic `defrecord` syntax or a new transport kind. Native
representation needs a separately versioned decision; no native wire
alternative is implemented.

- **Portable:** an ordered, inspectable history of representable messages,
  tool-call/result relationships, instructions as historical records, and
  artifact references. Preserve origin, sequence, role, and payload type.
  Tool events describe past activity; they are never commands to replay.
- **Native:** a settled immutable checkpoint plus adapter/protocol identity and
  compatibility requirements. Content may be opaque. It must identify an exact
  branchable state, not a mutable session's latest position. An adapter that
  cannot provide that promise cannot produce a native `Context`.
- **Coverage:** explicitly names the capture scope, represented event kinds,
  known omissions, and conversions. “Complete” is only meaningful within that
  declared exposed scope; it never means hidden reasoning or inaccessible
  provider instructions. Unknown event kinds cannot be silently dropped.
- **Lineage:** identifies the source attempt/checkpoint and subsequent
  transformations. Content identity is distinct from provenance: identical
  bytes from different sources may share storage without erasing their origin.

Large content may be stored through immutable references under existing
run/artifact ownership. A descriptor carries its schema and content identity;
reading referenced content is explicit I/O. Copying a reference does not copy
the content. Persisting a JSON descriptor does not by itself make remote native
state durable or available on another host.

Programs may also construct portable context from an empty history or supplied
messages/evidence; capture is not its only introduction rule. Such content is
identified as authored or derived, not falsely attributed to a provider session.
Ordinary structural data is the editable surface. Validation at construction
and binding checks event relationships and computes content identity; authored
provenance annotations are claims, not authenticated capture receipts. Native
checkpoint internals are not editable: export to portable content before
applying content transformations.

### Capture, Transform, And Bind

At target 2.31, opt-in capture selects the portable representation on supported
ordinary Codex calls. It records the effective supplied context, new
task/current-call contributions, and exposed conversation through the settled
boundary; the adapter, not the model's final answer, supplies this data. Native
capture and import of pre-existing sessions remain proposed. If a required
representation or coverage cannot be delivered, capture fails explicitly.

If implemented later, importing a pre-existing session is a separate effectful
adapter operation over an exact settled checkpoint. It cannot scrape an
actively changing journal and declare its latest offset a snapshot. Existing
session-ID imports would require this validation; they are not automatic
conversions to `Context`.

Logical operations, not commitments to new builtins:

| Operation | Meaning / effect |
| --- | --- |
| Construct | Start with empty or authored materialized portable content; pure construction and structural validation, not a provider invocation. |
| Snapshot / capture | Produce an immutable context at a named settled boundary; adapter/storage I/O. |
| Inspect / select / append / replace | Operate on materialized portable history with normal data operations; pure when no content is fetched. Preserve or explicitly repair event dependencies and record changes. |
| Compact / summarize | Produce a new context with source lineage and explicit loss. If model-assisted, this is an ordinary provider effect with its own result and usage, not a pure coercion. |
| Fork | Reuse the same immutable value. No new language primitive is needed merely to give it to two calls; physical native forks happen at binding. |
| Bind | Prepare a new invocation using the chosen provider, context, and current-call contract. Resolve compatibility before launch. |
| Export native to portable | Explicit conversion with a coverage/loss report; requires adapter evidence and may be unsupported. |

Selecting a tool result without its required call identity must either include
that dependency, convert it to a standalone observation explicitly, or reject
the malformed history. Arbitrary history concatenation is not a native-session
merge. Summaries are derived claims, not replacements for source evidence.

Binding is governed by the input representation; no automatic native/portable
fallback is permitted. Portable import starts a new destination conversation.
If its transport cannot represent an event, role, or modality, require an
explicit conversion or report incompatibility before invocation. A text-only
adapter may accept a deliberately text-converted context, but must not claim
structured-history preservation. Native binding creates a private continuation
from the exact checkpoint; even sequential consumers must not mutate the seed.

### Current Instructions And External State

The destination call owns its current task, provider/model configuration, tool
configuration, and result/output contract. Portable history retains earlier
instructions as history, not as silently installed current instructions. Source
roles remain provenance even when the destination renders them as quoted
history. That role projection is declared binding behavior, not exact native
reproduction. LLM compliance is not guaranteed by metadata.

Native continuation may retain instructions internally. Its adapter must prove
compatibility with the destination call's effective contract, or reject the
binding. Do not promise that arbitrary old system instructions can be removed
by appending a new prompt. Old result schemas and bundle destinations remain
historical data; the current validated invocation owns the only current result
destination and schema.

Context contains neither the filesystem nor live interpreter/process state.
An artifact reference identifies evidence; only an included immutable snapshot
carries its bytes. Consumers must resolve remaining references explicitly and
report unavailable content. Context branching does not isolate external tool
effects or make two branches statistically independent. Workspace cloning and
external-effect handling remain separate existing facilities or separate work.

## Language And Frontend

The ordinary-call syntax below is implemented at target 2.31 for supported
Codex providers. This is a body fragment that assumes its provider, prompt,
type, and `seed` declarations; use the [portable provider context authoring
guide](../lisp_workflow_drafting_guide.md#portable-provider-context) for a
copy-safe example and current limits.

```lisp
(let* ((investigation
          (provider-result providers.investigator
            :prompt prompts.investigate
            :context seed
            :capture-context :portable
            :returns Analysis))
       (alternative
          (provider-result providers.alternative
            :prompt prompts.try-another-approach
            :context investigation.context
            :capture-context :portable
            :returns Proposal))
       (check
          (provider-result providers.checker
            :prompt prompts.check-evidence
            :context investigation.context
            :returns Assessment)))
  alternative)
```

Both later calls consume the investigation snapshot; the checker receives no
alternative-branch history through context. This alone does not constitute a
blinded evaluation: the investigation itself may contain conclusions.

Implemented typing rules for target 2.31:

- With neither clause, existing calls and result types remain unchanged.
- `:context c` accepts a `Context`; absence means the existing fresh-call path,
  not a lookup of ambient workflow memory. Existing provider ambient behavior
  is not silently redefined or claimed absent.
- `:capture-context` is a static representation selection. With capture, a call
  whose model-authored return is `T` yields `Contextual[T]`; without capture it
  yields `T`, even when consuming context. Discarding continuation is allowed.
- `:returns T` and prompt-owned returns still describe only the model's result.
  The runtime assembles the wrapper; the model is never instructed to fabricate
  the context descriptor. Existing return-contract coherence checks remain.
- Reusable procedures can accept/return `Context` or `Contextual[T]`; public
  checks cover imported generic helpers, record/list carriage, branches, and
  loop state. Private flattened carriage rejects colliding paths such as
  `a__b` and nested `a.b`; no universal `Value` conversion is implied.
- Effects stay explicit under the existing effect contract. Passing an already
  materialized value is not provider I/O; invoking, exporting, loading stored
  content, and model-assisted compaction are. This proposal does not depend on
  the separate optional-effect-ledger proposal.

### Relationship To Effect Contracts And Pure-Call Composition

The [effect-ledger proposal](workflow_lisp_effect_ledger_simplification.md)
remains separate: it does not make capture or provider invocation pure. The
implemented target-2.31 context path uses the existing effect contract for its
selected provider calls; adopting optional effect restrictions is not a
prerequisite.

The [pure-call composition design](workflow_lisp_pure_call_composition.md)
addresses a different boundary: its target-2.30 resolved-inline subset lets an
effect-free helper compose where that representation is admitted. Target 2.31
uses this path for supported materialized Context transformations and proves
the listed imported, aggregate, collection, branch and loop positions. It does
not imply universal collection eligibility. Passing materialized context is
pure; capture, provider invocation, and loading stored content are I/O. Context
lineage belongs to values and execution provenance, not mandatory effect-name
repetition on every wrapper.

Neither proposal is a blanket prerequisite for PC-1. For the shipped target-2.31
slice, public checks cover the selected transport, imported/helper, aggregate,
collection, branch, loop, and resume positions; no further feasibility spike is
needed for those positions. Evaluate any new representation or placement
narrowly if a real consumer requires it. Do not solve unrelated gaps with
context-specific pure-call syntax, a new effect atom for each transformation
policy, or alternative global-artifact transport.

### Compatibility, Provider Selection, And Tooling

Target 2.31 rejects contradictory `:session-artifact`/context-capture requests
rather than manufacturing two independently authoritative publications. Any
future support for both requires a deliberate compatibility projection.
Rebinding uses declared provider externs: current
`typecheck_effects.py` requires a compiler-known provider and `lowering/effects.py`
resolves it to a fixed provider ID. Dynamic model/effort options do not imply
dynamic provider identity. Validate known capability incompatibility statically
and checkpoint/content availability before launch.

Runtime-selected provider identity is an optional, separate language/dispatch
prerequisite if later context-policy programs need it; it is not required for
rebinding between two declared providers. That extension would need effect/type
carriage and prelaunch capability validation. Reconsider the static-provider
restriction when justified, rather than silently adding dynamic dispatch to
this feature or declaring it permanently out of scope.

Target 2.31 gates the implemented clauses and carries their input/output types
through generic specialization and WCC. Unsupported representations are
diagnosed at the authored call. The wider design calls for context dependencies
and transformation origins in semantic explanations/source maps; reuse
existing editor diagnostics, and do not treat a new dashboard or context editor
as a prerequisite.

## Implementation Architecture And Publication

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
[composition implementation plan](../plans/2026-09-22-value-and-continuation-composition-implementation-plan.md#d-portable-context-pc-1-ordinary-call-slice)
and [context carriage tests](../../tests/test_workflow_lisp_provider_context_e2e.py).
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
Recursive rendering is selected by the existing capture configuration; omitted
capture retains the legacy prompt projection, including older nested-container
schemas. Target 2.31 shared validation admits complete structural schemas at an
output bundle's single root pointer and validates nested field guidance. Computed
Context materialization uses that same generic whole-root schema path.

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

### Shared Publication Path

The existing flow remains `.orc → WCC → shared Core → validated executable IR
→ runtime`; Semantic IR, runtime plans, and reports remain their owned
projections. Context handling must travel through that path, not bypass it.

| Owner | Required responsibility |
| --- | --- |
| Expression/type/transport pipeline | Context clauses and structural wrapper typing; source spans; context carriage in generic and aggregate positions; reject unsupported casts. |
| WCC and effect lowering | Preserve explicit context dependencies and generated capture output ownership through specialization, calls, loops, and persistence. No bare global side-artifact workaround. |
| Shared provider configuration / executable validation | Versioned input/capture contract and adapter capability requirements, present consistently in loaded and persisted execution input. |
| Provider preparation and adapter/codec | Resolve exact context input and validate compatibility. The shipped path imports supported portable content for ordinary Codex calls and captures the settled exposed history. Native forking and other adapters remain future work; providers still own tool use. |
| Prompt composition | Compose the current task/inputs/output contract once; preserve the distinction between inherited history and current-call contributions. Do not reinterpret Q3 digests as stored history. |
| Existing result and state owners | Validate `T`, capture/validate context, assemble the runtime-owned wrapper, and commit one caller-visible value. |
| State layout / artifact storage | Commit the materialized typed pair through existing run/call-frame and dataflow ownership; this slice needs no content store or second persistence database. Any later storage-backed references must reuse existing artifact lifetime/export ownership. |
| Semantic/source-map/evidence projections | Explain input context identity, lineage, representation, conversions, output context, and source call without becoming executable authority. Native opacity remains visible. |

The publication unit is `{result, context}` when capture is required. Validate
the existing provider result and required outputs, capture the final selected
attempt's context, validate its coverage/representation, then commit the pair.
Failure before commit publishes neither member as a successful call result.
Attempt diagnostics and provider-created external files may remain; this is
state atomicity, not rollback of provider effects.

If the process succeeded but capture failed, do not rerun it invisibly just to
obtain context. Report capture failure under the ordinary failed-boundary
contract. A later explicit retry follows existing at-least-once semantics from
the same immutable input and a new private attempt. Partial files and native
sessions never become substitute successful results.

Compatible completed-boundary resume reuses the committed pair without calling
the provider or exporting the conversation again. Pending/interrupted attempts
follow existing discard-and-rerun behavior. Context selection, representation,
and transformations participate in program/input identity; data-content digests
participate in value identity. Changed context is changed input, not a way to
silently patch an old checkpoint. If a future native representation uses
expiring references, expiry may prevent a later bind but would not invalidate
the already committed model result.

If a future schema adds storage-backed content references for cross-run reuse,
use existing artifact export/import ownership with explicit content
availability and digest verification. A path under a deleted run is not
portable merely because it was serialized. Do not add garbage collection,
cross-host storage, or a general context catalog until an actual consumer
requires more than existing storage lifetime rules can provide.

## Practical Value And Five-Axis Evaluation

The feature is worthwhile only where explicit conversational dataflow reduces
work or enables useful inspection/search beyond a normal agent or SDK program.
It is not a unique AI capability simply because `.orc` gains syntax for it.

| Axis | Useful consequence and test | Principled next action |
| --- | --- | --- |
| Programmability / compositionality | Import a procedure returning context with its result, branch it, carry it through a loop, and feed another procedure without hidden handoff scripts. | Repair generic/transport or provider-boundary obstacles if they block a useful composition; if ordinary packets suffice, keep it in the library. |
| Reusability | Reuse an investigation's exposed observations across tasks/providers; compare reconstruction effort and actual missing/irrelevant evidence. | Improve selection and explicit reference materialization when valuable; drop native capture where portable handoffs suffice, or vice versa. |
| Introspection | Trace a bad result to the supplied history, an omission, a conversion, or a shared premise. | Improve exposed-content coverage and lineage where possible; narrow claims for opaque providers rather than pretend their hidden state is visible. |
| Self-programmability | An agent proposes revised context construction in ordinary workflow source; compile and run the revised program under existing program boundaries. | Improve representation/editability when measured obstacles justify it; do not add runtime `eval` or self-modifying live sessions just for this feature. |
| Search / optimization | Search context selection, compaction placement, branch points, and handoff policy alongside program topology; judge whole-task quality and total cost. | Use held-out tasks and account for transformation/export/token costs; simplify or remove policies that do not beat a skill/SDK control. |

Good initial consumers are reusable investigations and competing approaches
from a shared evidence point. Independent review should deliberately exclude
answer-bearing branch history when its methodology requires that separation.
Long-running scientific work additionally needs artifact/environment handling;
context alone does not reproduce its experimental state.

Native continuation may preserve useful provider-specific behavior, but neither
native resume nor portable replay guarantees lower token billing or latency.
Measure capture, conversion, storage, repeated input, cache behavior, and human
handoff work together. Default capture remains off for unrelated one-shot calls.
Captured content may be more sensitive than existing content-free diagnostics;
retain it as deliberate data, not automatically as a verbose report.

## Feasibility Prerequisites And Design Reconsideration

The questions used to select the target-2.31 ordinary-call slice are resolved
for its advertised scope: Codex 0.155.1 capture/fresh binding, the closed event
schema, `Contextual[T]` typing, atomic typed publication, imported/private and
aggregate carriage, collections, branches, loops, and committed-boundary resume
have public or real-adapter evidence in the linked implementation plan and
tests. This does not select broader PC-1 research or imply universal support.

Before making claims beyond that slice, prove or resolve these concrete questions:

1. **Additional adapters and cross-provider transfer:** demonstrate capture and
   delivery of the declared exposed history on each advertised adapter. Similar
   CLI names are not evidence of compatible event or role semantics.
2. **Native continuation or session import:** demonstrate an immutable settled
   checkpoint and independent forks before claiming native capture or binding.
   Import from a pre-existing session must establish that exact boundary;
   mutable session resume is not that capability.
3. **Other provider forms:** define semantics before exposing context capture
   on phased, supervised, peer, or adjudicated calls. In particular, decide
   which attempt/member history is returned; never silently take the last
   transcript.
4. **Expanded history/storage:** define and test each newly advertised event
   kind or storage-backed reference, including its coverage, conversion/loss,
   identity, availability, and failure behavior. The current Codex codec does
   not capture patch bytes, hidden reasoning, or unsupported tool events.

Do not turn a failed narrow prototype into an automatic abandonment decision.
Distinguish provider impossibility, an adapter gap, poor ergonomics, and a
language-foundation problem. Consider shared transport/type redesign or an
alternative language foundation when the benefit merits it. Bounded iteration,
static procedure references, and lack of unbounded recursion are current design
choices, not permanent axioms: revisit them if concrete adaptive context work
needs more. This proposal by itself does not establish that need.

Abandon or simplify a representation/operation when its promised semantics
cannot be delivered or ordinary handoffs win after reasonable improvements.
That result need not invalidate the other representation or every research axis.

## Compatibility, Deletion, And Documentation

Existing calls without the new clauses retain their contracts, storage behavior,
and identities. Gate new source and persisted fields explicitly; do not migrate
old mutable session IDs into immutable contexts by relabeling them.

Prefer replacing hand-authored session-path plumbing and duplicate transcript
packaging in the selected consumer. Retain `:session-artifact` where callers need
the existing operational bridge; retire it only if all remaining uses are
covered and a reviewed migration justifies deletion. The
[native-turn design](workflow_lisp_provider_prompt_queue.md) preserves one
final result but requires a distinct continuation/recovery contract; derive
conversational plumbing from the same adapter/codec owners rather than add a
second session manager. Its [PQ-1 roadmap entry](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns)
does not select native Context snapshots or delay portable-context work.

The target-2.31 slice updated the frontend/type and executable contracts,
[DSL](../../specs/dsl.md), [Providers](../../specs/providers.md),
[Step IO](../../specs/io.md), [State](../../specs/state.md),
[Versioning](../../specs/versioning.md), and the drafting guide. Keep capability
and documentation routes clear about the implemented portable subset, the
proposed native/other-adapter work, and copy-safe examples. The active research
study is not expanded or rescheduled by this design draft. Roadmap PC-1 tracks
that research separately; its listing does not fund or activate further work.

## Verification And Acceptance Scenarios

Use behavioral/dataflow assertions, not literal prompt wording. The target-2.31
ordinary Codex slice has public carriage/resume and real capture/fresh-bind
evidence. Fixture adapters prove deterministic mechanics; any new real adapter
or native representation needs separate capture/import/fork evidence. Neither
mechanical proof establishes research effectiveness.

1. **Composition and fork:** through the public `.orc` entrypoint, an imported
   investigation procedure returns `Contextual[T]`. Pass its context through an
   aggregate and loop-carried value into two calls. Assert identical input
   identity, distinct output continuations, preserved tool-event relationships,
   and no sibling conversational events. Repeat from a committed checkpoint;
   completed calls must not invoke or export again.
2. **Cross-provider transfer:** capture the declared exposed history from one
   real adapter and bind it to a different real provider adapter. Verify the
   actual delivered structure/content and declared projection, not only that a
   context ID was forwarded. Unsupported content must fail or require an
   explicit recorded conversion. Do not compare exact answer text as an oracle.
3. **Native branch:** where supported, consume one settled native checkpoint
   twice, sequentially and concurrently. Verify neither consumer advances the
   seed and each excludes the other's events. An adapter offering only mutable
   resume must reject this capability claim.
4. **Transformation and diagnosis:** select observations, materialize a needed
   artifact, and compact through an explicit procedure. Show source identity,
   omissions/loss, and destination consumption. A wrong-answer diagnosis must
   distinguish absent input from model judgment; do not claim hidden-state
   explanation.
5. **Failure and retry:** inject unsupported events, missing referenced content,
   corrupt capture, result-validation failure, expiry, and interruption before
   commit. Assert no half-published successful pair, no silent fallback, and
   input-preserving at-least-once retry. External side effects are not claimed
   rolled back. Include changed-context resume rejection.
6. **Current-contract ownership:** rebind history containing old instructions,
   tool schemas, and bundle destinations. Assert the new invocation's actual
   contract/bindings own current results; history is not replayed as tool work.
   Native incompatibility must be reported, not solved by an undocumented
   instruction override.
7. **No-cost-by-default and utility:** an unchanged one-shot call performs no
   context capture. On held-out continuation tasks compare the feature against
   ordinary artifact/skill/SDK handoffs, including total work, quality, missing
   evidence, diagnosis, and full costs. Shared-context reviewers are not counted
   as independent without the required information separation.

The target-2.31 ordinary Codex slice is implemented and verified within its
closed portable scope. Any broader PC-1 work still requires an independently
reviewed design, public-entry integration evidence, real adapter evidence for
each newly advertised representation, unchanged-call regressions, and honest
utility results. A successful minimum example opens the relevant improvement
questions; it is neither an ORC-superiority claim nor automatic approval for a
memory system.
