# Provider-Session Resume Problem Statement

## Objective

Design and implement first-class provider-session resume support in the workflow DSL and runtime so a workflow can:

1. start a fresh provider session,
2. publish a typed session handle,
3. run one or more separate review / gating steps,
4. resume that same provider session in a later step using new feedback,
5. keep the flow artifact-driven instead of embedding provider-specific shell commands in YAML.

The initial concrete target is the existing Codex review/fix pattern, but the design should prefer a provider-agnostic surface if that can be done without hand-waving.

## Problem

Today, reusable workflows can only model provider-session resume by embedding literal provider shell commands such as `codex exec resume ...` directly in workflow YAML. That creates several problems:

- the DSL has no first-class notion of a provider session handle
- session ids are not typed artifacts, so they do not participate cleanly in publish/consume flow
- runtime ownership is unclear: prompts and providers end up being asked to manage files or ids that should belong to the runtime
- the pattern is provider-specific, brittle, and hard to reuse
- workflow `resume` and provider-session `resume` are easy to conflate even though they solve different problems

The design loop should treat this as a contract problem first, not just a convenience feature.

## First-Release Scope

The first shipped slice should be good enough to replace ad hoc Codex session-resume shell glue in example workflows.

Expected first-release capabilities:

- scalar `string` support wherever session handles need to flow as typed values
- a step-level way to say a provider step is either a fresh session or a resume of a prior session
- a runtime-owned way to capture and persist provider session metadata
- publication of a typed session-handle artifact from fresh session steps
- consumption of that artifact by later resume steps
- one concrete end-to-end provider implementation, with Codex as the acceptable first pass
- at least one example workflow migrated to the first-class DSL/runtime feature while leaving the old shell-based example in place

## Non-Goals

The first release does not need to solve all possible provider-session problems.

Explicit non-goals unless the design review proves they are unavoidable:

- support for multiple providers in the first runtime slice
- nested `call` integration beyond what already works in the runtime
- automatic retry / resume policy for provider sessions beyond normal step control flow
- multi-session fan-out orchestration features
- generalized chat-thread management beyond session handle capture/resume
- changing the meaning of workflow `resume`
- forcing the design to support every hypothetical provider before one real provider path is proven

## Constraints And Invariants

The design and implementation must respect these constraints unless the design review explicitly rejects them with a better alternative:

- Prefer a provider-agnostic DSL surface.
  A Codex-first runtime path is acceptable, but the authored workflow surface should not hard-code `codex exec resume` as the DSL feature.

- Keep workflow `resume` distinct from provider-session `resume`.
  Workflow `resume` restores orchestrator run state. Provider-session `resume` re-enters a provider-native session/thread. These must remain separate concepts in the design, state, docs, and observability.

- Treat scalar `string` support as a prerequisite if session handles require it.
  If typed session handles cannot be modeled cleanly without `string`, then `string` support must be designed and shipped first rather than bypassed.

- Keep session metadata runtime-owned.
  The runtime should own capture, persistence, and publication of provider session metadata. Prompts should not be asked to write runtime-owned session-id files.

- Preserve normal artifact/dataflow semantics.
  Session handles should move through normal typed publish/consume flow, not through hidden side channels.

- Preserve current provider output semantics unless the design explicitly redefines them.
  If a provider-specific metadata channel is needed, the design must say exactly how it coexists with normal stdout/stderr, output capture, and deterministic output validation.

- Be honest about provider-specific assumptions.
  If the first implementation depends on a Codex-specific event stream or command shape, the design must state that clearly instead of implying generality that does not yet exist.

- Do not accept vague “we can generalize later” claims unless the minimal abstraction boundary is explicit and defensible.

## Design Questions The ADR Must Resolve

The design / ADR phase should not proceed to planning until it settles these questions clearly:

- Is `string` a general scalar contract type, and exactly where is it allowed?
- What is the minimal step-level DSL surface for fresh-vs-resume provider sessions?
- What provider-template metadata is required, and what is optional?
- What exact runtime-owned metadata is persisted, where, and for what purpose?
- How is a session handle published as an artifact?
- How does a resume step bind that session handle back into a provider invocation?
- What is the first-pass Codex-specific mechanism, and which parts are intentionally not yet generalized?
- How does provider-session metadata capture interact with current output capture and output-contract validation?
- What compatibility and migration story applies to existing shell-based workflows?
- What debt or refactoring, if any, is a true prerequisite rather than a nice-to-have?

## Success Criteria

The design should be considered ready for planning only if all of the following are true:

- the first-release scope is explicit and bounded
- the provider-agnostic authored surface is concrete enough to implement
- any Codex-first limitations are explicit and honest
- the relationship between `string` support and provider-session resume is resolved
- runtime ownership of metadata and artifact publication is unambiguous
- the distinction between workflow `resume` and provider-session `resume` is crisp
- the design identifies real prerequisite debt/refactoring, if any, with closure criteria
- the design names explicit non-goals so planning does not reopen every adjacent problem

## Review Guidance

The design / ADR review loop should be hard-nosed.

Reviewers are encouraged to:

- block the design if it hand-waves over runtime ownership, migration boundaries, or provider-specific assumptions
- require internal refactoring or debt paydown before feature work when it is a correctness prerequisite, a contract prerequisite, or a major simplicity win that materially reduces feature risk
- reject fake abstraction that claims provider agnosticism without a believable minimal contract
- distinguish clearly between:
  - blocking prerequisites,
  - required in-scope work,
  - recommended follow-up,
  - out-of-scope concerns

The goal is not to maximize architecture purity. The goal is to produce a principled first release that replaces shell glue without lying about what the runtime can actually guarantee.
