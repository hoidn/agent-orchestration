# Workflow Lisp Provider Prompt Dependencies

Status: current component contract for admitted evaluated execution. This document
owns the dependency-injection component; [dependencies](../../specs/dependencies.md),
[providers](../../specs/providers.md), [I/O](../../specs/io.md) and
[security](../../specs/security.md) retain their normative responsibilities.
The [frontend](workflow_lisp_frontend_specification.md) owns versioned syntax and
types; [evaluated execution](workflow_lisp_evaluated_execution.md) owns execution
identity and recovery. The original [design and delivery record](../plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-design.md)
retains rationale, qualification and retired representations.

## Purpose And Scope

A provider may receive explicit file contents as prompt context without turning
business inputs, file observations, result lineage or prompt text into one
untyped channel. Dependencies are exact workspace-relative file paths, evaluated
through the typed provider-result surface. A dependency read is an input to one
reached provider attempt, not a prerequisite that schedules another workflow.

Source support in a historical language version does not admit execution of that
target. The [executable cutoff](../../specs/cli.md#executable-support-boundary)
continues to reject retired targets and old recovery profiles. This component
adds no YAML frontend, flat executor, prompt scaffold creation or general file
capability.

## Authored And Typed Surface

`provider-result` may carry `:prompt-dependencies` with ordered `:required` and
`:optional` groups, `:position prepend|append`, and a literal `:instruction`.
At least one dependency group must be nonempty. The frontend checks exact
workspace-relpath operands using its supported typed, effect-free path
expressions; this is not a glob, directory walk, new path-literal syntax or
substitution language. The instruction is a literal string, not a dynamically
computed prompt. Omission of position selects `prepend`.

Required means absence is an error. Optional permits absence only: an existing
unsafe, unreadable, non-regular or invalid-text input does not become ignorable.
Path normalization, workspace confinement and symlink/read-boundary validation
remain the dependency and I/O owners' responsibility. Injection never grants
permission to read outside the workspace or weakens those owners' rejection
rules. Prompt context is still untrusted data, not executable instructions or
filesystem authority.

## Current Consumers And Attempt Boundary

`orchestrator/workflow_lisp/closed/effects.py::_closed_prompt_dependencies`
closes required/optional values and preserves position/instruction. On the
evaluated route,
`orchestrator/workflow/evaluated/providers.py::provider_dependency_rows`
combines document fills and explicit dependency operands; fills are required.
`_snapshot_dependencies` resolves them with `DependencyResolver.resolve_exact`
and calls `snapshot_content_dependencies_with_sha256`. `resolve_provider_io`
returns those observations with the provider source in one immutable
`ProviderIOReads` value.

Each reached attempt takes one content snapshot. Rendering and evidence consume
that snapshot without reopening paths. Raw SHA-256 and normalized prompt text
come from the same captured bytes: strict UTF-8 decoding and universal-newline
normalization affect text, while the digest identifies the raw file. A retry
makes a fresh snapshot; a changed workspace must not silently reuse a prior
attempt's in-memory observation. Resolution/rendering failure prevents provider
invocation and must not fabricate successful dependency evidence.

The snapshot helper lives in `orchestrator/deps/content_snapshot.py`; its shared
read primitive is `read_text_with_sha256`. This route does not implement the old
plan's allocator-owned platform probe or descriptor-allocation protocol. Shared
path/I/O safety contracts apply at their actual consumers; the historical
proposal is not a second current read algorithm.

## Deterministic Rendering And Bounds

Canonical targets are deduplicated and sorted lexicographically. Required wins
when the same target is authored in both roles. Authored order remains provenance
where recorded; it does not change the deterministic render order. The
instruction and file framing have one renderer; arbitrary custom rendering is
outside this contract.

The injection block has an exact 262,144-byte UTF-8 cap, excluding its outer
separator. Instruction content is limited to 261,630 bytes, with the existing
512-byte reserve. The renderer takes valid UTF-8 prefixes without splitting a
code point and stops at the first omitted or truncated entry. It does not skip
a large earlier file to fit later ones. Prepend/append chooses the block's
position relative to authored prompt text; it does not append a second output
contract or change runtime-owned [result delivery](provider_result_delivery.md).

## Evidence And Recovery

Dependency rows and content digests describe observed inputs. They do not certify
file authorship, prompt truth, provider behavior or result validity. Provider
results still pass their typed output contract. The evaluated checked effect,
site/activation identity, attempt inputs and memo input parts own reuse under
[evaluated execution](workflow_lisp_evaluated_execution.md) and
[state](../../specs/state.md), including C6 consistency. Resume re-resolves the
committed prefix's provider inputs (C6/C7), including
source/dependency bytes, to detect `effect_input_diverged`; reuse avoids provider
redispatch, not general input verification. Target-2.38 confined attempt-snapshot
exceptions remain bounded by their evaluated owner. There is no additional
allocation lifecycle ledger, offline-index admission rule or flat checkpoint
identity for this component.

Retained historical readers and import/type analysis remain governed by their
versioned owners. The old design's WCC/Core/runtime-plan carriage, allocation
ledger/index and two-family rollout were implementation history. Their stored
bytes and qualification receipts remain in the original record; they do not
select another port or restore an executable route. Binary injection, dynamic
instructions, globs and a new renderer remain outside the selected surface.
