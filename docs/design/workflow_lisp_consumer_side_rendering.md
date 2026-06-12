# Workflow Lisp Consumer-Side Rendering

Status: draft target design (future target; describes intended behavior, not
the current checkout)
Kind: architecture / ergonomics and materialization-reduction target
Created: 2026-06-12
Scope: rendering typed values at consumer seams — prompt injection,
observability, entry-boundary publication, and compatibility bridges — so
producer-authored materialization shrinks to a small residue and native
typed values remain the default carrier everywhere.

Authority:

- Normative runtime and DSL behavior remains in `specs/`. This document
  defines a target; nothing here changes current behavior until its
  tranches land with evidence.
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
  owns the `materialize-view` kernel (its Tranche G4), the boundary
  authority classes, and the census discipline. Every surface in this
  design lowers to that kernel; this design adds no second rendering
  semantics. Its G4 carries the one guard-rail this design needs in
  advance: the renderer interface stays invocable independently of file
  allocation.
- `docs/design/workflow_lisp_frontend_specification.md` is the
  authoritative language baseline; language-visible changes here are
  normative spec deltas to merge on tranche acceptance.
- `docs/design/workflow_lisp_runtime_migration_foundation.md` owns prompt
  composition and structured-output authority; the prompt-injection lane
  extends composition, not output authority.
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  owns family promotion sequencing and the family idiom (its 10A
  values-before-artifacts discipline, which this design operationalizes).
- `docs/design/workflow_lisp_state_layout.md` owns allocation identity;
  durable-view roles are unchanged; ephemeral renderings allocate nothing.
- `docs/design/workflow_lisp_lexical_execution_checkpoints.md` is a sibling
  future target. Neither depends on the other; both treat views as
  regenerable from typed values.

Related docs:

- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_lexical_execution_checkpoints.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/providers.md`
- `specs/state.md`

## 1. Purpose

The G4 kernel makes file production honest: deterministic, typed,
provenance-tracked, never semantic authority. This design fixes the
remaining problem, which is direction. Materialization today is
producer-authored: the workflow that has a typed value writes files for
whoever might need them — a view for the next prompt, a summary for the
human, a legacy-shaped file for an old consumer, a published artifact for
the outside. Every ergonomic cost traces to that direction: authored
ceremony in bodies, path-typed fields ferrying content between steps,
publication decisions baked into reusable workflows, bridge files that
must be found and removed at retirement time.

The organizing principle of this design:

```text
Producers publish typed values.
Rendering happens at the consumer's seam.
```

Each consumer class gets its own lane, each lane lowers to the same G4
kernel, and body-level `materialize-view` shrinks to the one case that is
genuinely a producer concern: timed, interior publication.

This is a future target. It must not be read as a change to the G4 scope
in flight at the time of writing; G4 is the kernel this design consumes.

## 2. Executive Decision

Adopt consumer-side rendering across four lanes plus a kernel split:

```text
Consumer            Lane                                    Durability
--------------      -------------------------------------   -----------------
typed step          pass the typed value; nothing renders   none (lane zero)
next agent          render at prompt injection              ephemeral
human               observability layer renders results     derived on demand
the outside         entry-boundary :publish policy          durable view
legacy reader       bridge metadata drives maintenance      durable, labeled
(residue) mid-run   authored materialize-view in body       durable, timed
```

Lane zero is the preference order's first entry, not a footnote: whenever
the consumer is another typed step, the typed value flows and no rendering
of any durability occurs. Every other lane is the exception for a consumer
that cannot take typed delivery, and choosing a lower lane when lane zero
is available is the anti-pattern this design exists to eliminate.

Implement the work in ordered tranches:

- C0: rendering census and seam verification — classify every authored
  view, summary writer, and report target by consumer class; verify the
  G4 renderer seam (bytes-level interface independent of allocation).
- C1: typed values as prompt inputs — render at the injection seam,
  ephemeral, evidence in the composed-prompt log.
- C2: observability-derived human summaries — `report`/dashboard render
  typed terminal results; authored human-summary views retire.
- C3: entry-boundary `:publish` policy — per-variant result publication
  on entrypoint signatures, lowering to `materialize-view` at terminal
  arms; interior-publication lint.
- C4: compatibility bridges as classification metadata — bridge entries
  drive legacy-file maintenance from typed values; retirement is metadata
  deletion.
- C5: kernel split and cleanup — ephemeral vs durable renderings made
  explicit in the kernel; authored views replaced by C1-C4 retired with
  dual-run evidence.

The target success condition is not "views are easier to write." It is
that the reference family's body code contains zero `materialize-view`
forms except timed/interior publications, every remaining durable view is
attributable to a boundary policy or a bridge metadata entry, and the
typed value is the only thing a workflow author hands to any consumer.

## 3. Current-State Anchors

Stated as consumed fact, re-verified by C0 before behavior changes:

- The G4 kernel (in flight at drafting): `materialize-view`, canonical
  JSON plus versioned registered renderers, `StateLayout` role,
  byte-determinism evidence, the view-as-semantic-input lint.
- Prompt composition injects file contents declared via `:inputs` and
  appends rendered output contracts; composed prompts are logged
  artifacts.
- `orchestrate report` and the dashboard render run state; step summaries
  are observability artifacts that must not drive routing.
- Boundary authority classes exist with census artifacts (G0), including
  `compatibility_bridge` labels with owners and retirement routes.
- Provider steps declare authored artifact targets via `:targets`;
  report-target paths still travel through inputs records in the
  reference family.

## 4. Authority And Dependency Direction

### 4.1 This document consumes

- The G4 rendering kernel: renderer registry, versioning, determinism,
  allocation roles, the authority lint.
- Boundary authority classes and the census discipline.
- Prompt composition and the composed-prompt log as evidence surface.
- Observability surfaces and the summaries-are-not-routing rule.
- The 10A values-before-artifacts idiom (this design is its mechanical
  completion: when values are the only carrier, artifacts cannot become
  carriers by accident).

### 4.2 This document owns

- The consumer-lane taxonomy and the rendering-direction principle.
- The ephemeral-rendering contract (no allocation; evidence in the
  composed-prompt log).
- The entry-boundary `:publish` policy surface and its lowering.
- The bridge-metadata maintenance contract (declaration drives the file;
  deletion retires it).
- The interior-publication lint and the timed-publication residue
  definition.

### 4.3 This document does not own

- The rendering kernel itself (generic-core G4).
- Prompt source semantics and output-contract injection (foundation).
- Allocation identity (state layout).
- Family promotion sequencing and bridge retirement scheduling
  (post-foundation; its Tranche 9 consumes C4's metadata mechanics).
- Run-report formats (observability docs); C2 supplies typed inputs to
  them, not new report designs.

### 4.4 Sequencing and arbitration

This design is implemented after the generic core's G4 has acceptance
evidence; it must not be drain-selectable before that. It has no ordering
relationship with the lexical-checkpoints target: both are gated on
generic-core acceptance points, touch disjoint machinery, and may be
prioritized in either order by the selector's owner. Where both are
registered, substrate arbitration follows each document's consumed
contracts; a genuine conflict between them is a blocker, not a tiebreak.

### 4.5 Prohibited dependency directions

```text
rendering             -> semantic authority                    PROHIBITED
ephemeral rendering   -> durable allocation                    PROHIBITED
interior workflow     -> publication decisions (non-timed)     PROHIBITED
bridge file           -> existence outside bridge metadata     PROHIBITED
:publish policy       -> caller-visible workflow contract      PROHIBITED
typed prompt input    -> provider output authority changes     PROHIBITED
```

The fifth line keeps publication a deployment property: callers of a
workflow must not be able to observe or depend on its `:publish` policy
through the type system.

## 5. Goals

1. A typed value can be handed directly to any consumer: a prompt, the
   report layer, an entry publication policy, a bridge — with rendering
   performed at that seam, visibly.
2. The reference family's bodies contain no `materialize-view` except
   timed/interior publications.
3. Authored human-summary views are retired in favor of
   observability-layer rendering of typed terminal results.
4. Every durable view in a run is mechanically attributable: boundary
   policy entry, bridge metadata entry, or a timed body form. No orphan
   files.
5. Bridge retirement is metadata deletion with zero body edits.
6. Path-typed fields whose only purpose is ferrying renderable content
   between steps are eliminated from the reference family's records.
7. Output contracts carry typed values, not view references: result
   unions shed path-typed payload fields whose content is derivable from
   the typed value itself (the drain's terminal `drain-summary` report
   reference is the reference case). A view reference survives in a
   result type only as a labeled `compatibility_bridge` field while
   parity requires it.

## 6. Non-Goals

- Not a removal or weakening of the G4 kernel; every lane lowers to it.
- Not implicit-invisible publication: each lane leaves evidence (effect
  rows, composed-prompt logs, policy entries, metadata entries). Nothing
  renders without a trace.
- Not a change to provider output authority: structured output bundles,
  contract injection, and fail-closed validation are untouched.
- Not a general templating system: renderers remain registered, closed,
  and versioned; prompt-side rendering uses the same registry.
- Not a reporting redesign: C2 feeds typed values to existing
  observability surfaces.
- Not retroactive: existing YAML families keep their shapes; this design
  applies to `.orc` surfaces and the migration's target idiom.

## 7. Architecture Invariants

1. Rendering direction: producers publish typed values; rendering is
   performed at consumer seams. A body-level durable view is legitimate
   only when the publication is timed (must exist mid-run).
2. One rendering semantics: every lane calls the G4 renderer interface
   (typed value, renderer id, renderer version -> deterministic bytes);
   byte-determinism evidence is shared, not per-lane.
3. Ephemeral renderings allocate nothing durable; their evidence is the
   composed-prompt log (already a logged artifact) plus the visible
   effect entry.
4. Durable views exist only for consumers outside the program, and each
   is attributable to a declaration: `:publish` entry, bridge metadata
   entry, or timed body form.
5. Publication is a boundary property: `:publish` is legal on promoted
   entrypoint signatures only, is per-variant over union results, and is
   not part of the caller-visible contract.
6. Bridges are complete-by-construction: a legacy-shaped file maintained
   from a typed value exists if and only if a `compatibility_bridge`
   metadata entry declares it. Deleting the entry retires the file path
   from the system.
7. Authority is unchanged everywhere: typed values remain semantic
   authority; renderings of any durability are views; the
   view-as-semantic-input lint applies to all lanes.
8. Census-driven growth: new renderers and new lanes require a consumer
   class shown by the C0 census, not convenience.

## 8. Core Model

### 8.1 The renderer seam

The G4 kernel exposes rendering as a pure, deterministic, versioned
function from typed values to bytes, independent of allocation:

```text
render : (value : T, renderer : RendererId, version : Int) -> bytes
```

Lanes differ only in what happens to the bytes: injected into a composed
prompt (C1), streamed into a report view (C2), written to an allocated
view path (C3, residue), or written to a bridge-declared path (C4).

### 8.2 Lane: typed values as prompt inputs (C1)

`provider-result :inputs` accepts typed values alongside file-backed
inputs. Illustrative:

```lisp
(provider-result providers.review
  :prompt prompts.review.summary
  :inputs ((design inputs.design)          ; file-backed, as today
           (summary terminal-result        ; typed value, rendered at
             :renderer canonical-json))    ; injection; no file allocated
  :returns ReviewDecision)
```

The composer renders the value through the registry, injects the bytes
with a provenance header (value type, renderer id and version, source
binding), and records everything in the composed-prompt log. The lowering
carries a visible rendering effect. Renderer defaults to canonical JSON;
human-oriented renderers must be named explicitly.

### 8.3 Lane: observability-derived summaries (C2)

The runtime already holds validated typed terminal results.
`orchestrate report` and the dashboard render them through the same
registry, so "the drain summary" is a *derived presentation of the typed
result*, generated on demand, never authored, never stale, and never a
file the workflow had to write. Authored human-summary views become
redundant and retire with dual-run evidence (rendered report content
matches the retired view's content for the same typed value).

### 8.4 Lane: entry-boundary publication (C3)

Promoted entrypoints may declare per-variant result publication:

```lisp
(defworkflow drain (...) -> DrainResult
  :publish ((DONE    :as drain-summary)
            (BLOCKED :as blocker-report :renderer markdown)))
            ;; variants omitted publish nothing
```

The authored vocabulary is semantic: a variant and a publication role.
Renderers default from the role's declaration in the renderer/role
registry; naming one inline is an explicit override, not part of the row
shape. Authors never write `materialize-view` here and never see one —
the compiler lowers each policy row to the kernel form at the matching
terminal arm, with the same internal status as pure operators lowering to
generated `pure_projection` steps. Evaluation semantics distinguish the
published value (it is the result validated against the return type), and
the union's runtime variant selects the row. `:publish` is not part of
the caller-visible contract (invariant 5); interior workflows may not
declare it, and a non-timed body-level `materialize-view` in an interior
workflow trips the `interior_publication` lint.

### 8.5 Lane: bridges as metadata (C4)

A `compatibility_bridge` classification entry gains the fields needed to
*be* the materialization: source value binding (which typed result),
renderer id and version, target path contract, owner, and retirement
route. The runtime maintains the file from the typed value whenever the
value commits. Consequences: the bridge inventory is mechanically
complete (invariant 6); parity can enumerate every legacy surface from
metadata; and the post-foundation Tranche 9 simplification pass retires a
bridge by deleting its entry — no body code exists to find.

### 8.6 The residue

Timed, interior publication remains authored: per-iteration progress
views a human may read mid-run, and evidence files that must exist before
a later step consumes them by contract. These keep the full G4 form in
the body — which is correct, because their timing is workflow semantics,
not deployment.

## 9. Tranche C0: Rendering Census And Seam Verification

### 9.1 Contract

Classify every rendering the system performs or authors today by
consumer class, and verify the kernel seam this design depends on.

### 9.2 Tasks

- Census: every authored `materialize-view`, view-writer remnant,
  summary/report target, path-typed record field ferrying renderable
  content, and path-typed *result payload* field referencing a derivable
  view, labeled by consumer class (`prompt`, `human`, `external`,
  `legacy`, `timed`) and target lane (lane zero or C1-C4 or residue).
  Lane-zero entries — typed consumers currently served through files —
  are the highest-value findings: they need no rendering machinery at
  all, only the typed value passed directly.
- Verify the renderer seam: bytes-level rendering callable without
  allocation (the G4 guard-rail), with shared determinism vectors.
- Confirm composed-prompt logs capture injected content sufficiently to
  serve as ephemeral-rendering evidence.

### 9.3 Acceptance

- The census artifact exists, is CI-validated, and every entry names its
  lane; the seam verification passes against the shipped G4.

## 10. Tranche C1: Typed Values As Prompt Inputs

### 10.1 Tasks

- Frontend: typed-value entries in `:inputs` with optional `:renderer`;
  typecheck against the registry; forbid renderer-less human-oriented
  injection (canonical JSON default is machine-shaped by intent).
- Composition: render-at-injection with provenance header; composed-
  prompt log entries carry value type, renderer id/version, and source
  binding; visible rendering effect in lowering and Semantic IR.
- No durable allocation: assert no `materialized_value_view` allocation
  occurs for C1 renderings (invariant 3).
- Retire ferry fields: for each reference-family record field that exists
  only to carry renderable content between steps, replace with direct
  typed-value injection and remove the field.

### 10.2 Acceptance

- A fixture feeds a typed value to a prompt with zero files allocated;
  the composed prompt shows the rendered content and provenance header.
- Dual-run evidence: agent-visible prompt content is byte-identical
  between the old file-backed shape and the typed-injection shape for
  the same value.
- The reference family compiles with the identified ferry fields removed.

## 11. Tranche C2: Observability-Derived Summaries

### 11.1 Tasks

- `report`/dashboard consume validated typed terminal results through the
  renderer registry; summary presentation derives on demand.
- Dual-run retirement of authored human-summary views: rendered report
  content matches retired view content for identical typed values; then
  the authored views and their census entries flip to `retired`.
- Guard: derived presentations remain observability artifacts; nothing
  routes on them (consumed rule, re-asserted in tests).

### 11.2 Acceptance

- The drain's terminal summary is visible in `orchestrate report` for a
  family fixture run with zero authored summary views in the family.

## 12. Tranche C3: Entry-Boundary Publication Policy

### 12.1 Tasks

- Frontend: `:publish` on promoted entrypoint signatures; per-variant
  rows over union results; policy totality check (every row names a
  declared variant; omissions are explicit non-publication).
- Role-bound renderer defaults: publication role declarations carry their
  default renderer and version, so policy rows stay in semantic
  vocabulary (`:as <role>`); inline `:renderer` is an explicit override
  with its own review flag.
- Lowering: insert `materialize-view` of the returned value at terminal
  arms per policy; identical evidence to hand-written forms (sugar
  property).
- Lint `interior_publication`: non-timed body-level `materialize-view`
  in a non-entry workflow is an error; timed forms carry an explicit
  `:timed` marker reviewed under the census.
- Contract isolation: `:publish` absent from caller-visible signatures,
  Semantic IR call contracts, and type identity (invariant 5 negative
  fixtures).

### 12.2 Acceptance

- A fixture entry publishes per-variant; the omitted variant publishes
  nothing; the lowered output is bit-identical to the hand-written
  `materialize-view` equivalent.
- An interior workflow with a non-timed view trips the lint; a caller
  observing `:publish` through any contract surface fails its fixture.

## 13. Tranche C4: Bridges As Metadata

### 13.1 Tasks

- Extend bridge classification entries with source binding, renderer
  id/version, path contract, owner, retirement route.
- Runtime maintenance: on commit of the source value, the bridge file is
  (re)rendered; staleness is impossible by construction.
- Migration: each existing bridge file's authored producer is replaced by
  a metadata entry with dual-run evidence; orphan detection — a
  legacy-shaped maintained file with no metadata entry fails CI.
- Tranche 9 interface: retirement = entry deletion; provide the
  post-foundation pass a mechanical bridge inventory.

### 13.2 Acceptance

- A legacy consumer reads an unchanged bridge file maintained from the
  typed value; deleting the metadata entry retires the path with zero
  body edits; the orphan check demonstrably fails a planted orphan.

## 14. Tranche C5: Kernel Split And Cleanup

### 14.1 Tasks

- Make the ephemeral/durable distinction explicit in the kernel contract
  (G4 doc delta routed to its owner): durable allocation is a lane
  property, not a rendering property.
- Evidence-gated cleanup: census entries replaced by C1-C4 retire; the
  residue census (timed forms) is reviewed and each entry justified.
- Retire result-payload view references: reference-family result types
  shed fields that only reference derivable views (the drain terminal
  summary reference first), with any parity-required survivor kept as a
  labeled `compatibility_bridge` field until its route retires (goal 7).
- Drafting-guide and review-criteria deltas: authors hand consumers typed
  values; `materialize-view` in review is a flag unless timed or at a
  declared boundary; a path-typed result field whose content is derivable
  from the typed value is a flag unless bridge-labeled.

### 14.2 Acceptance

- Census end-state: every durable view in a reference-family run is
  attributable (policy, metadata, or justified timed form); zero
  unattributed files (goal 4 proven mechanically).

## 15. Failure Modes

| Failure | Detection | Response |
| --- | --- | --- |
| Renderer version drift between lanes | shared determinism vectors per renderer version | fail closed; lanes pin versions; no silent re-render under a new version |
| Injected rendering exceeds prompt budget | composition size checks | fail the step with a typed diagnostic naming the binding; never silently truncate |
| `:publish` row references a missing variant | policy totality check at compile | compile error |
| Bridge file diverges from typed value | impossible while maintained (rendered on commit); orphan check for unmaintained files | CI failure on orphans |
| Derived report content drifts from retired view expectations | dual-run retirement evidence; renderer versioning | retirement blocked until match |
| Ephemeral lane silently allocates | C1 no-allocation assertion | test failure (invariant 3) |

## 16. Verification Strategy

- Shared renderer determinism vectors across all lanes and the kernel.
- C1 no-allocation and prompt-content dual-run assertions.
- C2/C4 dual-run retirement evidence per replaced view/bridge.
- C3 sugar-equivalence (policy lowering vs hand-written forms) and
  contract-isolation negatives.
- Census attribution sweep: enumerate every `materialized_value_view`
  allocation and bridge file in a family run and join against policy
  entries, metadata entries, and timed forms — zero unmatched.
- Lint negatives for `interior_publication` and view-as-semantic-input
  across the new lanes.

## 17. Declarative Acceptance Scenarios

### 17.1 A value goes to a prompt without a file

A review step receives the drain's typed terminal result directly; the
composed prompt shows the rendered JSON with its provenance header; no
view file exists anywhere in the run for that injection.

### 17.2 The summary nobody wrote

A full drain fixture run produces no authored summary view, yet
`orchestrate report` shows the terminal summary rendered from the typed
result.

### 17.3 Publication at the boundary only

The drain entry declares `:publish` rows for `DONE` and `BLOCKED`;
`EXHAUSTED` publishes nothing; an interior phase workflow attempting a
non-timed `materialize-view` fails the lint.

### 17.4 Bridge retirement is a one-line deletion

A YAML-era consumer reads its expected file, maintained from the typed
run state; when parity stops requiring it, deleting the bridge metadata
entry removes the surface — `git diff` shows metadata only, no body
changes.

### 17.5 The residue is justified

The only `materialize-view` left in the family body is the per-iteration
progress view, marked `:timed`, with a census entry explaining who reads
it mid-run.

## 18. Success Criteria

1. Reference-family bodies contain no `materialize-view` except justified
   timed forms (Scenario 17.5).
2. Every durable view in a family run is mechanically attributable to a
   policy entry, bridge entry, or timed form; the attribution sweep
   reports zero unmatched.
3. Authored human-summary views: zero; observability renders typed
   results (Scenario 17.2).
4. Ferry fields eliminated from the reference family's records; typed
   values are the only cross-step carrier of renderable content.
5. Bridge inventory is metadata-complete; at least one real bridge
   retired by entry deletion.
6. All lanes share one renderer semantics with shared determinism
   evidence; no lane-specific rendering code paths.
7. Spec deltas merged on acceptance; drafting guide and review criteria
   updated to the values-only authoring rule.

## 19. Summary Recommendation

Adopt consumer-side rendering as the follow-on to the G4 kernel. The
generic core made file production honest; this design makes it rare.
Producers publish typed values; the prompt seam, the observability layer,
the entry boundary, and the bridge metadata each render for their own
consumer through one deterministic registry; and the only files a
workflow author still writes by hand are the ones whose mid-run timing is
itself workflow semantics. Ergonomics improve because the ceremony
disappears; the architecture improves because every file that exists is
attributable to a declaration that says who it is for.
