# Workflow Lisp Prompt Calculus

- **Status:** proposed direction (owner-directed 2026-07-25; design review
  pending)
- **Kind:** language direction — a typed, compositional prompt layer
- **Owner:** Workflow Lisp frontend + provider runtime
- **Related docs:**
  - `docs/design/workflow_lisp_frontend_specification.md`
  - `docs/plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-design.md`
    (implemented per-attempt snapshot contract)
  - `docs/design/workflow_lisp_program_search_boundaries.md` (invariant 8:
    role-separated prompt identity — the E4P discipline)
  - `docs/design/workflow_lisp_provider_peer_messaging.md` (runtime-owned
    prompt preludes)
  - `docs/design/workflow_lisp_pure_list_traversal.md` (mapping substrate)
  - `docs/design/workflow_language_design_principles.md`
- **Sequencing:** head of the post-Stage-8 queue by owner direction. No
  dependency on Stage 8; consumes the list-traversal delta when it lands.

## The asymmetry this direction closes

The language types exactly half of its interface to the stochastic
coprocessor. Agent *results* receive the full treatment: unions, variant
proofs, fail-closed validation, provenance. The *programs sent to the
agent* — prompts, which determine everything downstream — are opaque extern
files. Nothing verifies that a prompt mentions its inputs, discharges its
task, or matches the result type it is supposed to elicit; an empty
instructions file is first detected as a useless provider result, at
provider-call prices.

The strategic claim (owner, 2026-07-25): the language's differentiation
against general-purpose scripting is domain semantics — prompts, judgments,
reviews as typed objects — not generic orchestration, which merely defends.
A compiler that can say "this prompt is incomplete" is not competing with
Python.

## Existing seeds (convergent, currently ad hoc)

Five shipped mechanisms already grope toward this layer:

1. **Output-contract rendering** — the declared result type is rendered
   into the prompt as a deterministic contract block: the one existing
   type-to-prompt bridge.
2. **Prompt dependencies** — typed, ordered, frozen content injection with
   per-attempt snapshots: composition through the filesystem, untyped at
   the fragment level.
3. **The generic-reviewer pattern** — one template prompt plus injected
   per-lens instruction files: fragment composition by convention, with no
   check that an instruction file is nonempty, relevant, or shaped for the
   declared result.
4. **Runtime-owned preludes** — the peer-protocol injection: structured
   prompt blocks owned by the runtime, composed positionally.
5. **E4P prompt-identity roles** (salvaged to
   `workflow_lisp_program_search_boundaries.md` §8) — the identity
   discipline: resolved-binding domains, used-dependency-minimal program
   identity, protected composition environments, per-attempt snapshots.

A prompt calculus unifies these rather than adding a sixth convention.

## Components

### 1. `defprompt` — importable fragments with typed slots

A prompt fragment is a compile-time language object, importable and
composable like a type or procedure:

```lisp
(defprompt lens-review
  (:fills (criteria CriteriaDoc)      ; slot: injected document
          (target   DocContent)       ; slot: injected document
          (report_target ReportTargetPath))  ; slot: rendered value
  "Review the target strictly according to the criteria.
   Ground every finding in a specific section.
   Write your review to {report_target}.")
```

Slots are typed holes. A provider call site must discharge every slot of
its composed prompt — with a typed value, an injected document, or another
fragment — and an unfilled or ill-typed slot is a compile error with the
slot and expected type named. "Fully specified prompt" becomes a checkable
proposition, exactly like an unbound variable.

Fragments compose: a call's prompt is a fragment application tree,
flattened deterministically at composition time into the same rendered
bytes / attempt-snapshot / evidence pipeline that exists today. There are
no runtime prompt values: composition is compile-time structure, rendering
is the existing per-attempt runtime step.

### 2. Fragment/result coherence

A fragment that instructs a classification declares the union it elicits:

```lisp
(defprompt classify-blocker
  (:elicits BlockerClass)
  ...)
```

A call composing this fragment must have a `:returns` compatible with the
declared elicitation (the union itself, or a record/union containing it).
This makes the existing output-contract bridge bidirectional: types render
into prompts, and prompts declare the types they aim at, checked against
each other.

### 3. Prompt identity (E4P discipline, instantiated)

Composed prompts get used-dependency-minimal identity per invariant 8: the
fragments actually composed, the slots actually filled, and the resolved
bindings — not unused imports, not ambient hashes. Consequences: "did this
review run under the same prompt as last week" is a computable question;
prompt drift is a diff between identities; and the evidence ledger's
"what did this agent see" gains a stable name for the program half.

### 4. Judgment provenance and domain views

Attempt evidence already records which prompt, model, effort, and injected
inputs produced each result. This component lifts that association to the
inspection layer: a typed judgment — a result together with its producing
prompt identity, provider policy, and evidence set — plus a stdlib of
`materialize-view` renderers over common judgment shapes: per-lens verdict
matrices, panel disagreement tables, findings-over-iterations series.
Reports remain views (principle 7); the semantics live in the typed
results and the evidence, and the views make them legible.

### 5. Mapping over prompts

With fragments as importable objects and the list-traversal delta landed,
the review panel reaches its final form: map a procedure over a list of
fragment references or criteria documents, collect a list of judgments,
render the matrix. No new machinery in this component; it is the
composition of components 1–4 with `list/map-effect`.

## Boundaries

- **Completeness is structural, not semantic.** The checker verifies that
  every slot is discharged with the right type — never that the prose will
  persuade, or that the model will comply. Overclaiming here would violate
  the honesty the evidence layer is built on; the quality of a fragment
  remains a prompt-engineering judgment, versioned and identified but not
  verified.
- **No runtime prompt values.** Workflow code cannot construct, mutate, or
  branch on prompt content at runtime; composition is compile-time
  structure, and runtime contribution remains what it is today — typed
  value rendering and frozen document injection into declared slots.
- **No optimization semantics.** Prompt variation, search, and fitness are
  the parked E-series; if ever revived they operate over this layer under
  the program-search boundary invariants, which this direction neither
  relaxes nor anticipates.
- **Union parsimony (owner direction, 2026-07-25).** This layer must not
  multiply unions. `:elicits` targets any transportable type — enums,
  records, scalars — not preferentially unions; judgments are records
  (result + provenance), not new outcome unions; and fragment machinery
  introduces no DONE/FAILED-shaped types anywhere. Unions remain reserved
  for outcomes a caller genuinely routes on; outcomes that are only ever
  propagated belong to the failure channel, not the type.
- **Migration is additive.** Extern prompt files remain valid; `defprompt`
  is the typed successor adopted per prompt, with the generic-reviewer
  pattern as the first migration candidate.

## First tranche

`defprompt` with typed slots, slot-discharge checking at provider call
sites, and deterministic fragment flattening into the existing rendering
pipeline — components 1 and the structural half of 2. Everything else
(identity, judgment views, elicitation checking beyond direct unions)
follows in separate small tranches, each with its own consumer named.

Verification sketch for the tranche: RED fixtures for unfilled slot,
ill-typed fill, and nested-fragment discharge; goldens proving composed
rendering is byte-identical to an equivalent hand-authored prompt file;
one end-to-end run converting the generic-reviewer example to fragments
with unchanged provider behavior and evidence shape.
