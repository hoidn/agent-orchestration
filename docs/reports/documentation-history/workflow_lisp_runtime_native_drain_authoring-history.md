# Workflow Lisp Runtime Native Drain Authoring: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_runtime_native_drain_authoring.md](../../design/workflow_lisp_runtime_native_drain_authoring.md).

## 9. Dependencies And Sequencing

This target consumes the existing WCC route and post-foundation composition
work. Implementation should proceed in this order:

1. identify path-like and render-like fields in the Design Delta `.orc` family
   that should be replaced by typed values or private runtime context;
2. introduce typed prompt-input request records for provider calls;
3. replace deterministic helper scripts with pure typed projections where the
   closed expression surface is sufficient;
4. move ordinary terminal summaries and reports to boundary publication policy;
5. hide runtime context and generated targets behind private bindings;
6. convert durable state updates to typed transitions or certified transition
   adapters;
7. keep external tools and remaining legacy protocol work behind certified
   adapters; and
8. make the Design Delta Drain `.orc` family work as one parent-callable
   workflow family under the acceptance criteria below.

Work that can proceed independently:

- provider request-record refactors;
- projection replacement for local deterministic reshaping; and
- moving compatibility files to declared public/legacy boundaries when a live
  consumer still requires them.

Work that should wait for substrate support:

- removal of compatibility bridges required by YAML parity;
- defaulting all boundary publications to implicit rendering; and
- deleting certified adapters whose runtime-native replacement has not passed
  positive and negative behavior checks.

### 9.1 Shared Owner-Lane Prerequisites

Imported stdlib adoption claims depend on shared owner-lane capability
contracts that no single family owns. The prerequisite ledger lives in
`docs/design/workflow_lisp_shared_owner_lane_prerequisites.md`; each
prerequisite there states one minimum contract, one minimum behavior check,
and one adoption-claim rule. The lanes are:

- the parent-loop lane for imported `std/drain::backlog-drain`:
  callable-child value return and the terminal responsibility split, parent
  terminal reprojection and branch-local terminal contract alignment, the
  fixed `gap-drafter` callable boundary and generic gap-payload leaf
  carriage, and family gap re-entry convergence;
- the phase-family boundary lane for item-context-first work-item
  composition: the fixed `run-item` workflow-ref shape, generic child-phase
  reuse, called-workflow result branching and terminal reprojection, no
  internal compatibility-carrier lane, and work-item summary ownership over
  imported `finalize-selected-item`; and
- `std/phase` owner-lane self-hosting on the ordinary imported-module
  compile and validation route.

The adoption-claim rule is uniform: a family may adopt request-record,
projection, transition, publication, and cleanup slices that do not depend
on a missing prerequisite, but it must not claim imported stdlib adoption by
re-implementing missing owner-lane behavior in family-local adapters,
wrapper workflows, widened boundaries, or compatibility rereads. When a
slice hits a missing prerequisite, stop the slice and select the
prerequisite gap.

## 12. Compatibility And Migration

Phase 1 migration milestone (evidence snapshot, 2026-07-12): the
`backlog-drain` conversion was proven through the `std/drain` generic procedure
and macro on the ordinary import/specialization/WCC route. At this milestone,
the Design Delta consumer owned the inline `repeat_until` and terminal
reprojection in its parent workflow rather than delegating the loop to a
generated child workflow; consumer parity and the F5 boundary contract passed.
The snapshot did not claim intrinsic retirement: the legacy phase-drain
lowering, form-specific specialization, and name-keyed validation paths still
remained for the gated Phase 2 deletion pass. This dated paragraph is an
immutable evidence record, not live completion state; consult
`docs/capability_status_matrix.md` and
`docs/plans/2026-07-07-drain-migration-g8-retirement.md` for current status.

Existing YAML workflows remain valid. The `.orc` family may keep
compatibility bridges for YAML-era files while parity requires them. Those
bridges must be labeled and generated from typed values, not manually
maintained by workflow body plumbing.

Existing `.orc` forms remain valid:

- explicit provider input lists;
- explicit `materialize-view`;
- raw command boundaries; and
- certified adapters.

The target style narrows which of those are acceptable for new high-level
parent drain code:

- long provider input lists should move to typed request records;
- ordinary terminal reports should move to publication policy;
- deterministic reshaping should move to pure typed projection;
- durable mutation should move to resource transitions; and
- raw command boundaries should remain only for external tools or certified
  legacy behavior.

### 12.1 Transitional Surface Retirement

Compatibility bridges and family-specific compiler checks are acceptable only
as migration scaffolding. They may let the `.orc` family run before the final
authoring shape is complete, but they are not themselves target completion.

Do not measure progress by accumulating compatibility-bridge bookkeeping. Progress
means deleting the bridge, isolating it at a declared public/legacy boundary, or
replacing the caller with typed stdlib/family composition.

This target does not reopen the lexical checkpoint/resume substrate. It
consumes the private checkpoint route and requires remaining resume-only
authored drain plumbing to be removed, hidden, or explicitly classified as
non-semantic compatibility.

Full target completion requires a retirement pass that shows:

- compatibility bridges needed only for YAML-era files have either been removed
  or are isolated at declared public/legacy boundaries with owner, consumer,
  schema, and retirement condition;
- body code no longer constructs compatibility paths, pointer files, or summary
  files by hand;
- `PhaseCtx`, `ItemCtx`, `DrainCtx`, selection, and recovery records are
  library/domain records backed by generic `RunCtx`, resource, transition, and
  `StateLayout` mechanics rather than privileged runtime scope categories; and
- `backlog-drain`, `finalize-selected-item`, and related phase/drain behavior
  are owned by `std/*` or family library modules through ordinary imported
  `.orc` composition, signature/effect checking, and typed transitions, not by
  Design-Delta-specific lowering or typecheck branches.
  The promoted route must not branch on literal compiler names such as
  `std/drain`, `backlog-drain`, `finalize-selected-item`, or `phase_drain`.

If a compiler/runtime hook remains after this target is claimed complete, its
contract must be generic enough to serve other workflow families without naming
phase, item, drain, selection, recovery, or Design Delta concepts.

### 12.2 Phase/Drain Stdlib Conversion Path

The current phase/drain lowering path should be converted by moving domain
contracts upward into stdlib or family `.orc` modules and narrowing compiler
support downward to generic linking, typing, effects, and runtime contracts.

The target ownership split is:

| Concern | Final owner |
| --- | --- |
| `RunCtx`, resource identity/version, transition commit, resume identity, path safety | runtime and generic frontend substrate |
| `Resource<TState>`, `Transition<TRequest, TResult>`, effect summaries, private binding | generic Workflow Lisp contracts |
| `PhaseCtx`, `ItemCtx`, `DrainCtx`, `SelectionResult`, `SelectedItemResult`, `GapResult` | `std/context`, `std/resource`, `std/drain`, or family modules |
| `backlog-drain`, `finalize-selected-item`, `complete-work-item`, selection/gap/item routing helpers | imported `.orc` stdlib/family procedures |
| Design Delta selector, architect, work-item, recovery, and terminal result shapes | `lisp_frontend_design_delta/*` modules |

Conversion should proceed in this order:

1. Define the stdlib/family records, unions, and procedures in `.orc` modules
   with ordinary exported signatures. The source of truth for drain behavior
   becomes imported code, not Python lowering helpers.
2. Replace frontend checks that name `DrainCtx`, `ItemCtx`, selected-item
   variants, or gap variants with generic capability checks: workflow-ref
   signature compatibility, closed union/record types, required effects,
   declared transition contracts, and private-context availability.
3. Lower `backlog-drain` and `finalize-selected-item` through the ordinary
   import/specialization/WCC path. Any ergonomic surface may be a macro or
   stdlib wrapper, but it must expand to ordinary calls, `match`, loops,
   projections, and `resource-transition` operations.
4. Keep any intrinsic lowering branch only as a schema-1 or compatibility
   route while the stdlib route is checked against the public contract and
   declared semantic effects.
5. Delete or quarantine Design-Delta-specific assumptions from compiler
   modules once the stdlib route passes compile, shared validation, and the
   minimal runtime check for its public contract.

The final stdlib route may still use compiler support for generic features such
as imported workflow refs, WCC control lowering, hidden private bindings,
source-map frames, typed resource transitions, and materialized-view kernels.
It must not require a compiler branch that understands "the Design Delta drain"
or exact YAML state-machine mechanics.

## 18. Implementation Handoff

A later implementation plan should be organized around the reference family:

1. identify the internal path, context, rendering, projection, adapter, and
   transition surfaces that must be removed or converted;
2. introduce typed request records;
3. add or finish lowering for implicit provider-input rendering and boundary
   publication;
4. convert deterministic helpers to typed projections;
5. convert state updates to typed transitions or certified adapters;
6. simplify the `.orc` source;
7. run compile, shared validation, and focused dry-run/smoke checks for the
   changed behavior; and
8. remove obsolete follow-up text after the working reference family supports the
   behavior.
