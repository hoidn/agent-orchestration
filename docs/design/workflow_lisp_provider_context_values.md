# Workflow Lisp Provider Context Values

- **Status:** proposed; not an implemented authoring surface
- **Kind:** language and provider-boundary architecture decision
- **Owner:** Workflow Lisp frontend and provider/runtime boundary
- **Created:** 2026-09-08
- **Last material update:** 2026-09-08
- **Implementation target:** unassigned; this proposal selects no implementation
- **Roadmap:** [PC-1](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#pc-1--first-class-provider-context-pending-unselected), pending and unselected; feasibility, compositional implementation, and consequent improvement/retirement require their own selection and allocation
- **Review and drafting record:** [design plan and comparative simulation](../plans/2026-09-08-provider-context-design-plan.md)

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

Portable history and opaque native continuation are different representations
with different promises. This is not universal memory, live-process cloning,
workspace transfer, or a claim to capture a model's hidden internal state.

## Context And Authority

Current behavior and design constraints were inspected in the working tree on
2026-09-08. Normative specifications remain unchanged by this proposal.

| Existing owner | Reuse and limitation |
| --- | --- |
| [Providers](../../specs/providers.md), [provider types](../../orchestrator/providers/types.py), [executor](../../orchestrator/providers/executor.py) | Existing preparation, execution, capability declarations, and session codecs are the adapter boundary. Resume support alone does not prove immutable snapshot, export, or fork support. |
| [DSL](../../specs/dsl.md), [provider expression parsing](../../orchestrator/workflow_lisp/expressions.py), [effect lowering](../../orchestrator/workflow_lisp/lowering/effects.py), [session-artifact tests](../../tests/test_workflow_lisp_session_artifact.py) | Target-2.27 `:session-artifact` publishes a fresh scalar handle separately from the typed result. The inspected `provider-result` keywords include no first-class context input. A handle is not captured content. |
| [OMP templates](../../orchestrator/providers/omp_templates.py), [CLI contract](../../specs/cli.md) | Foreground session bridging and native CLI features are distinct from ordinary workflow calls. OMP template `resume_command=None` cannot be treated as existing workflow rebinding support. |
| [Prompt calculus](workflow_lisp_prompt_calculus.md), [Step IO](../../specs/io.md) | Reuse current-call composition and output-contract ownership. Q3's content-free provenance is not conversation content and must not be repurposed as an export format. |
| [Transportable Value](workflow_lisp_transportable_value_type.md) | Existing strict-JSON carriage is useful infrastructure, but exact opaque `Value` is not an implicit cast, inspectable context type, or proof that all nested context positions already work. |
| [Executable IR](workflow_lisp_executable_ir.md), [Semantic IR](workflow_lisp_semantic_workflow_ir.md), [State Layout](workflow_lisp_state_layout.md), [State](../../specs/state.md) | Preserve the WCC/shared-Core/validated-executable path, derived semantic explanations, generated paths, call-frame lineage, and completed-boundary reuse. Provider context is not private execution `RunCtx`. |
| [Language principles](workflow_language_design_principles.md) | Explicit dataflow/effects, real procedure composition, structural types where sufficient, opt-in stronger constraints, and runtime-owned deterministic work govern this proposal. |
| [Provider prompt queue](workflow_lisp_provider_prompt_queue.md) | A separate proposal for a private atomic multi-turn session. It neither implements nor precludes first-class context; its ownership decision must be reconciled before either proposal duplicates transport logic. |

## Problem, Goals, And Boundaries

An investigation can produce both an answer and useful accumulated working
context. Today a reusable workflow can pass declared artifacts or author a
handoff, but cannot express this whole continuation as an ordinary captured
value. A scalar session handle leaves selection, portability, branch isolation,
and lifetime outside the value contract.

Required outcomes:

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
| Language design | Context is a duplicable value; provider calls optionally consume and produce it. Content transformations compose with ordinary data operations and effectful procedures. | Type/transport restrictions that prevent ordinary composition must be repaired or explicitly identified as prerequisites, not hidden behind root-only syntax. |
| Implementation / architecture | Capture and bind extend the existing provider boundary; immutable content and runtime-produced result metadata use existing storage, validation, and checkpoints. | Export fidelity, native branching, and atomic result/context publication are substantive new responsibilities. A session-ID alias is insufficient. |
| Frontend / authoring | Small additions to `provider-result`, ordinary projections, compiler diagnostics, and source-mapped explanations expose context flow. | Syntax alone does not deliver the feature. WCC, generic specialization, public boundaries, lowering, and resume must carry the same contract. |
| Practical use | Reusable investigations, alternate approaches, targeted handoffs, and context-policy experiments become directly expressible and auditable. | Storage, export latency, repeated input tokens, contamination, and adapter limitations can outweigh the benefit. Existing SDK/agent handoffs are the comparison, not a straw-man stateless call. |

## Decision And Alternatives

Use immutable context values with two explicit representation cases, `Portable`
and `Native`. Extend the existing provider boundary with opt-in context input
and capture. Return captured context alongside, not inside, the model-authored
result contract. Use ordinary data transformations and reusable procedures
before adding specialized operators.

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

`Context` is a proposed transportable language value, distinct from `String`,
opaque `Value`, and execution `RunCtx`. The logical representation is:

```text
Context = Portable(content, coverage, lineage)
        | Native(checkpoint, compatibility, coverage, lineage)

Contextual[T] = { result: T, context: Context }
```

These are semantic shapes, not an approved wire schema. `Contextual[T]` should
use the ordinary generic-record machinery. The irreducible special boundary is
validation/transport of captured context and native references, not a new
provider-specific family of source types.

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

Capture on a completed provider call records its effective supplied context,
new task/current-call contributions, and the exposed conversation through the
settled boundary. The adapter, not the model's final answer, supplies this data.
Opt-in capture specifies portable or native representation. If a required
representation or coverage cannot be delivered, capture fails explicitly.

Importing a pre-existing session is a separate effectful adapter operation over
an exact settled checkpoint. It is not scraping an actively changing journal
and declaring its latest offset a snapshot. Existing session-ID imports require
this validation; they are not automatic conversions to `Context`.

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

Illustrative proposed syntax, **not runnable current `.orc`**:

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

Proposed typing rules:

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
- A reusable procedure can accept/return `Context` or `Contextual[T]`, place it
  in ordinary aggregates, and carry it through loops. These positions are
  requirements to prove, not claims of current transport support.
- Effects stay explicit under the existing effect contract. Passing an already
  materialized value is not provider I/O; invoking, exporting, loading stored
  content, and model-assisted compaction are. This proposal does not depend on
  the separate optional-effect-ledger proposal.

### Relationship To Effect Contracts And Pure-Call Composition

The [revised effect proposal](workflow_lisp_effect_ledger_simplification.md)
separates inferred operations from optional authored restrictions. It does not
make capture or provider invocation pure. Context-bearing procedures should
propagate the effects of their selected calls automatically; an intentionally
named provider ceiling may restrict rebinding, while an unconstrained reusable
helper need not name every possible destination.

The [pure-call composition proposal](workflow_lisp_pure_call_composition.md)
addresses a different boundary: an effect-free inline helper should not be
rejected in an aggregate or pure map merely because it is a procedure call.
Materialized context selection/packaging is a relevant consumer, but context
type/transport and collection eligibility remain separate feasibility questions.
Passing an immutable stored-content reference is pure; dereferencing it is I/O.
Context lineage belongs to values and execution provenance, not mandatory
effect-name repetition on every wrapper.

Neither proposal is a blanket prerequisite for PC-1. The compositional spike
must identify whether an obstruction is actual I/O, missing transport/type
support, expression normalization, or private-boundary identity. Select the
necessary shared correction, or reconsider the foundation where justified.
Do not solve it with context-specific pure-call syntax, a new effect atom for
each transformation policy, or an alternative global-artifact transport.

### Compatibility, Provider Selection, And Tooling

Initially diagnose contradictory `:session-artifact`/context-capture requests
rather than manufacturing two independently authoritative publications. The
implementation design must define a deliberate compatibility projection before
allowing both. Initial rebinding uses declared provider externs: current
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

Compiler/editor consequences: reserve/gate the new clauses only when accepted;
carry input and output types through generic specialization and WCC; diagnose
unsupported representation at the authored call; expose context dependencies
and transformation origins in semantic explanations/source maps. Reuse existing
editor diagnostics. A new dashboard or context editor is not a prerequisite.

## Implementation Architecture And Publication

The existing flow remains `.orc → WCC → shared Core → validated executable IR
→ runtime`; Semantic IR, runtime plans, and reports remain their owned
projections. Context handling must travel through that path, not bypass it.

| Owner | Required responsibility |
| --- | --- |
| Expression/type/transport pipeline | Context clauses and structural wrapper typing; source spans; context carriage in generic and aggregate positions; reject unsupported casts. |
| WCC and effect lowering | Preserve explicit context dependencies and generated capture output ownership through specialization, calls, loops, and persistence. No bare global side-artifact workaround. |
| Shared provider configuration / executable validation | Versioned input/capture contract and adapter capability requirements, present consistently in loaded and persisted execution input. |
| Provider preparation and adapter/codec | Resolve exact context input, validate compatibility, fork/bind natively or import declared portable content, then capture settled output. Providers still own tool use. |
| Prompt composition | Compose the current task/inputs/output contract once; preserve the distinction between inherited history and current-call contributions. Do not reinterpret Q3 digests as stored history. |
| Existing result and state owners | Validate `T`, capture/validate context, assemble the runtime-owned wrapper, and commit one caller-visible value. |
| State layout / artifact storage | Allocate attempt-private staging and immutable committed content, retain content referenced by live values, and support existing run/call-frame ownership. No second persistence database. |
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
silently patch an old checkpoint. Native reference expiry may prevent a later
bind, but does not invalidate the already committed model result.

For cross-run reuse, use existing artifact export/import ownership with explicit
content availability and digest verification. A path under a deleted run is
not portable merely because it was serialized. Do not add garbage collection,
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

Before implementation selection, prove or resolve these concrete questions:

1. **Real adapter capability:** demonstrate settled exposed-history capture and
   a declared portable import on the intended providers. Demonstrate immutable
   native branching separately if claiming it. Similar CLI names are not proof.
2. **Composite value carriage:** a compile/run/resume spike must pass captured
   context through an imported generic procedure, nested return, supported
   collection operations, and loop state. The current scalar session-artifact
   route and transportable `Value` do not prove this. Treat aggregate/type
   limitations as language/transport work, not as reasons to fake first-class
   support with global artifacts. Include a reusable materialized-content
   transformation in an aggregate and a supported collection/loop position;
   distinguish a procedure-placement failure from unsupported collection
   transport. Optional annotations alone cannot establish this capability.
3. **Runtime-produced wrapper:** prove existing `T` output validation remains
   unchanged while the runtime atomically publishes context alongside it.
   Particularly cover tagged results and compiler-owned direct-root returns.
4. **History and instruction fidelity:** define the first supported event
   schema, role projection, tool relationship rules, unsupported modalities,
   coverage reports, and exact native compatibility checks with adapter evidence.
5. **Other provider forms:** explicitly define semantics before exposing context
   capture on phased, supervised, peer, or adjudicated calls. In particular,
   decide which attempt/member history is returned; never silently take the last
   transcript. Ordinary calls are the initial vertical slice, not a promise that
   every composite form already has one unambiguous context.

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
covered and a reviewed migration justifies deletion. If accepted, reconcile the
prompt-queue proposal: preserve its distinct atomic multi-turn behavior where
needed, but derive conversational plumbing from the same adapter/capture/bind
owner rather than add a second session manager. No proposal is superseded here.

At implementation time update the frontend/type and executable contracts,
[DSL](../../specs/dsl.md), [Providers](../../specs/providers.md),
[Step IO](../../specs/io.md), [State](../../specs/state.md),
[Versioning](../../specs/versioning.md), and the drafting guide together.
Capability and documentation indexes must continue to distinguish proposal,
partial adapter support, and copy-safe implemented examples. The active research
study is not expanded or rescheduled by this design draft. Roadmap PC-1 tracks
this proposal separately; its listing does not fund or activate implementation.

## Verification And Acceptance Scenarios

Use behavioral/dataflow assertions, not literal prompt wording. Fixture adapters
prove deterministic mechanics; real provider adapters must separately establish
capture/import/fork feasibility. Neither proves effectiveness.

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

Acceptance requires an independently reviewed implementation design resolving
the prerequisites, public-entry integration evidence, real adapter evidence for
each advertised representation, unchanged-call regressions, and honest utility
results. A successful minimum example opens the relevant improvement questions;
it is neither an ORC-superiority claim nor automatic approval for a memory system.
