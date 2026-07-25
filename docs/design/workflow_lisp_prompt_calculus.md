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
  (:fills (criteria :doc)        ; slot kind: injected document content
          (target   :doc)
          (report_target :path)) ; slot kind: rendered path value
  "Review the target strictly according to the criteria.
   Ground every finding in a specific section.
   Write your review to {report_target}.")
```

A fragment's slots are one set seen two ways. The **templating view** is
the text: fields in the prose, bindable one at a time until fully bound.
The **signature view** is the interface: typed inputs and outputs,
one-to-one with a procedure signature (component 2). The views cannot
drift because they share the slots: for rendered kinds (`:text`, `:value`,
`:path`) the compiler checks the placeholder/slot correspondence both
ways — an undeclared `{placeholder}` or a declared rendered slot absent
from the text is a compile error — while `:doc` slots deliver as injected
blocks and need no inline placeholder.

Slots are holes with **kinds**, drawn from a closed, small vocabulary —
`:doc` (injected document content), `:text` (rendered string), `:value`
(rendered transportable value), `:path` (rendered path) — mirroring the
injection channels that already exist. A provider call site must discharge
every slot of its composed prompt — with a value, a document, or another
fragment of the matching kind — and an unfilled or wrong-kind slot is a
compile error with the slot and expected kind named. "Fully specified
prompt" becomes a checkable proposition, exactly like an unbound variable.

Kinds are **delivery channels**, and choosing between them is a real
authoring decision the design makes explicit rather than implied:

- `:doc` delivers **by injection**: the fill's content is frozen into the
  attempt snapshot and the prompt identity — maximal "what did the agent
  see" evidence, bounded by the injection size cap.
- `:path` delivers **by reference**: the agent receives the path and reads
  for itself — right for large or navigable material and tool-bearing
  agents, at a stated evidence cost: identity records which path was
  named, not what the file held when read. Choosing reference is choosing
  that weaker evidence (an authoring decision in the principle-29 sense).
  An open option, not machinery yet: recording a dispatch-time digest of
  referenced files to evidence "what was there at call start" without
  injection.

Delivery mode is the fragment author's choice per slot, not the caller's
per call: prose and delivery are coupled ("the injected content above"
versus "read the file at {p}"), so caller-side overrides could silently
contradict the fragment's own text. Same-fragment-both-modes is deferred
until a consumer demonstrates the need.

A `:path` slot may additionally be marked an **output position**
(`(report_target :path :out)`): the prose instructs writing to that path,
the signature declares it, and the runtime verifies existence there after
the attempt — today's expected-output postcondition, relocated to the
declaration the instruction lives in. This closes a real drift class
(prompt instructs writing to X while the step checks Y) by making prose,
signature, and postcondition one declaration.

Kinds are not a vocabulary beside the type system; each kind is the loose
top type of its delivery channel, and a slot *may* narrow it with a
specific type (`(criteria :doc CriteriaDoc)`) when a particular path
family or value shape genuinely matters. Refinement is ordinary
principle-29 narrowing — optional, and not the idiom: the calculus's
value is discharge checking, not nominal branding, and a fragment usable
only with bespoke types is a worse fragment.

Fragments compose: a call's prompt is a fragment application tree,
flattened deterministically at composition time into the same rendered
bytes / attempt-snapshot / evidence pipeline that exists today. There are
no runtime prompt values: composition is compile-time structure, rendering
is the existing per-attempt runtime step.

Application may be partial. Binding a subset of slots by name yields a
**residual fragment** whose signature is exactly the remaining slots,
usable anywhere a fragment is: partial application is compile-time
structural staging, not closure creation — a residual is never a runtime
value. The discharge rule generalizes accordingly: a provider call
applied to a fragment with a nonempty residual is the compile error
`prompt_slot_undischarged`, naming the open slots and their kinds.
Staging gives the generic-reviewer pattern its natural shape —
panel-invariant slots bound once, the per-lens slot bound at each use.

### 2. Prompt-carried signatures

Slots and return type together make a prompt a full procedure signature:
slots are the parameters, and the declared return type is what the prompt
elicits. A fully bound prompt handed to a provider is a call to a
procedure whose body is stochastic.

```lisp
(defprompt classify-blocker
  (:fills (evidence :doc))
  -> BlockerClass
  "...")
```

An unstated return type is `Value` — loose by choice, per principle 29.
Provider call sites *derive* their result type from the composed prompt
instead of re-declaring it, exactly as any call site takes its type from
the callee's signature; a call-site annotation is optional and is checked
against the signature, never trusted over it. The existing
output-contract rendering keys off this one declaration, so the bridge
runs both ways from a single source: the return type renders into the
prompt as the contract block, and the provider's result validates against
it at the runtime boundary.

Two consequences follow. Prompts and procedures become
signature-interchangeable: a deterministic `defproc` with the same
signature can stand in for a prompt-backed call, making provider doubles
in tests type-checked substitutions rather than conventions. And the
anti-inference line is unmoved: the signature is authored at the
`defprompt`, never derived from the prose — the checker reads structure,
not meaning.

### 3. Prompt identity (E4P discipline, instantiated)

Composed prompts get used-dependency-minimal identity per invariant 8: the
fragments actually composed, the slots actually filled, and the resolved
bindings — not unused imports, not ambient hashes; partial application
adds no identity surface, since residuals are staging and identity
attaches to the fully composed tree at the call. Consequences: "did this
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
render the matrix. Partial application supplies the idiom —
panel-invariant slots bound once outside the map, only the per-lens slot
bound in the body. No new machinery in this component; it is the
composition of components 1–4 with `list/map-effect`.

## Worked example: opt-in density across a workflow's life

The same review panel at two moments, demonstrating the calculus together
with design principle 29 (types are opt-in constraints). Day one —
exploratory, nearly typeless:

```lisp
(defprompt lens-review
  (:fills (criteria :doc) (target :doc) (report_target :path))
  "Review the target according to the criteria.
   Write your review to {report_target}.")

(defworkflow entry
  ((doc Path)                       ; generic path: no root/existence ceremony yet
   (lens_names List[String]))       ; the panel is a list of strings
  -> Value                          ; opt-in top type: no result contract yet
  (list/map-effect ((name lens_names)) :max 8
    (provider-result providers.reviewer  ; result type from the prompt's
      :prompt (lens-review               ; signature — unstated, so Value
                :criteria (path/join-under "lenses" (string/concat name ".md"))
                :target doc
                :report_target (path/join-under "artifacts/review" (string/concat name ".md"))))))
```

Zero `defrecord`, `defunion`, or `defpath` declarations — yet slot-discharge
checking, path containment, per-attempt evidence, mid-panel resume, and the
spend cap all hold, because they are structural. Result-shape validation is
deliberately loose: a loose contract is a loose check, chosen.

Hardened later, narrowing only where narrowing pays (each step legal under
"contracts may only narrow"): the prompt's declared return type becomes a
record once its fields are consumed; the report path becomes a rooted must-exist family once
downstream relies on it; one `defenum` verdict appears at the single place
a caller routes with `match`; and the irreconcilable-contradiction outcome
becomes an authored failure (`fail :class "panel_contradiction" ...`)
rather than a variant threaded through every caller. Reusable aggregation
bridges both eras without re-wrapping through a structural constraint:

```lisp
(defproc worst-severity
  :forall (T)
  ((items List[T]))
  :where ((T is-record) (T has-field severity_count Int))
  -> Int
  ...)
```

Feature status within this example: structural constraints, `string/concat`,
evidence, and resume exist today; `list/map-effect`, `path/join-under`, and
the list operators are the pure-list-traversal delta; `defprompt` with
prompt-carried signatures is this design's first tranche; `Value` and authored `fail` are
parsimony-wave candidates in the roadmap's post-Stage-8 queue.

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
  Partial application stays inside the boundary: residuals are
  compile-time structure, never values.
- **No optimization semantics.** Prompt variation, search, and fitness are
  the parked E-series; if ever revived they operate over this layer under
  the program-search boundary invariants, which this direction neither
  relaxes nor anticipates.
- **Type parsimony (owner direction, 2026-07-25).** The calculus mints no
  new nominal types and imposes no obligation to define any: slot
  signatures are kinds from the closed vocabulary, refinement is optional,
  and any value, path, or document satisfying the kind discharges the
  slot. The return type is likewise optional, defaulting to loose
  `Value`. A design that makes fragment
  authors build type taxonomies before writing prose has failed this
  boundary.
- **Union parsimony (owner direction, 2026-07-25).** This layer must not
  multiply unions. Declared return types target any transportable type —
  enums, records, scalars — not preferentially unions; judgments are records
  (result + provenance), not new outcome unions; and fragment machinery
  introduces no DONE/FAILED-shaped types anywhere. Unions remain reserved
  for outcomes a caller genuinely routes on; outcomes that are only ever
  propagated belong to the failure channel, not the type.
- **Type-parameterized fragments (deferred).** Type-generic prose — a
  fragment whose instructions hold for a family of elicited types
  ("classify into exactly one of the categories in the contract below")
  — is admitted in one future form only: an explicit type parameter on
  the `defprompt`, reusing the structural `:forall`/`:where` mechanism,
  with the type argument instantiated visibly at the call site,
  constraints bounded by contract-render totality (every admissible type
  must render a coherent contract block), and prompt identity including
  the instantiation. Deriving the contract block from a call-site
  annotation or the enclosing procedure's return type is context flow
  and remains ruled out regardless of duplication pressure. Admission
  condition: two or more fragments with byte-identical prose differing
  only in declared return type; until then the honest state is concrete
  duplicated fragments.
- **Migration is additive.** Extern prompt files remain valid; `defprompt`
  is the typed successor adopted per prompt, with the generic-reviewer
  pattern as the first migration candidate.

## First tranche

`defprompt` with prompt-carried signatures (slots as parameters, return
type defaulting to `Value`), partial application with residual
signatures, discharge checking at provider call sites, call-site result
derivation, and deterministic fragment flattening into the existing
rendering pipeline — components 1 and 2. Output-position slots follow in
a second tranche once the post-attempt verification wiring is in scope;
identity and judgment views follow in separate small tranches, each with
its own consumer named.

Verification sketch for the first tranche: RED fixtures for an unfilled
slot, an ill-typed fill, nested-fragment discharge, a provider call
applied to a nonempty residual, a placeholder/slot mismatch inside a
fragment, and a call-site annotation contradicting the prompt's
signature; goldens proving composed rendering is byte-identical to an
equivalent hand-authored prompt file; one end-to-end run converting the
generic-reviewer example to fragments with unchanged provider behavior
and evidence shape.
