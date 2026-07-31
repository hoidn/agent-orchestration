# Typed Program Gates: Staged Checking, Generational Execution, And The Parked Eval Terminal

## Metadata

- **Status:** accepted design; revision of an external exploratory draft
  ("Typed Staged Eval And The Self-Hosting Runtime Roadmap", 2026-07-27)
  into an accepted design under this repository's adopted boundaries; no
  implementation is selected
- **Kind:** target architecture, three-tranche
- **Owner:** agent-orchestration maintainers
- **Reviewers:** ordered independent `E_DESIGNS_SPEC_APPROVED`, then
  `E_DESIGNS_QUALITY_APPROVED` on 2026-07-31
- **Created:** 2026-07-27
- **Related docs:**
  - [Program-search boundary invariants](workflow_lisp_program_search_boundaries.md)
    (binding; §Boundary Compliance is the governing section of this design)
  - [Workflow Lisp trial runs](workflow_lisp_trial_runs.md) (the generational
    experiment platform; C1 below is the concrete form of its
    "diagnostics as machine API" substrate dependency, and C2 below is the
    supervision surface its `run-ref` children share)
  - [Provider at-least-once loosening amendment](../plans/2026-07-26-provider-at-least-once-loosening-amendment.md)
    (landed through ML; supplies the at-least-once attempt and single-writer
    run contract assumed by C2 and any future C3 work)
  - [Pure-result replay](workflow_lisp_pure_result_replay.md)
    (accepted M2 persistence boundary; C1's result/evidence contract below is
    deliberately durable while derived projections remain replayable)
  - [Workflow language design principles](workflow_language_design_principles.md)
    (Principles 28, 29, and 30 bind diagnostics, type density, and provider
    attention respectively)
  - [Core calculus middle end](workflow_lisp_core_calculus_middle_end.md)
    (owns the flattening route and the authority-inversion deferral C3
    depends on; this document does not re-price that risk)
  - [Lexical execution checkpoints](workflow_lisp_lexical_execution_checkpoints.md)
    (draft target; consumed by C3 only)
  - [Command adapter contract](workflow_command_adapter_contract.md)
    (existing authority under which C2 proceeds)
  - [Frontend specification](workflow_lisp_frontend_specification.md)
    (diagnostics registries, version gating conventions)
  - [MLEvolve system architecture](mlevolve_workflow_lisp_system_architecture.md)
    (a consumer family — of C1 and of the trial-runs platform, deliberately
    not of C3)
  - Seeds: `workflows/library/generic_run_watchdog/`,
    `workflows/library/scripts/probe_orchestrator_run.py`,
    `orchestrator/workflow_lisp/compiler.py` (`compile_stage3_entrypoint`)
- **Implementation target:** none selected. Ordered design review is complete;
  C1 and C2 still require an explicitly reviewed component plan and selection
  by the owning roadmap. C3 is parked with
  named re-entry conditions and must not begin implementation planning on
  this document's authority. Target 2.23 is already implemented; the first
  admitted tranche must receive a new, currently unassigned post-2.23 target.

Purpose: give workflows a typed, evidenced path through the full loop
"generate a program, check it, run it, route on the outcome" — today an
unchecked composition of provider text, shell glue, and exit codes —
without runtime eval, without weakening any adopted invariant, and without
depending on the authority-inversion rearchitecture.

Authority: normative behavior lives in `specs/`; each tranche lands as spec
amendments first at a new post-2.23 DSL target chosen at admission. Where this document
touches program search, `workflow_lisp_program_search_boundaries.md` wins;
this design is written to satisfy it outright rather than amend it.

Copy safety: all `.orc` fragments and record shapes are conceptual and
**not copy-safe**.

## Revision Provenance

The source draft proposed a single terminal capability — `eval-workflow`,
runtime evaluation of generated fragments inside the parent run — behind
five prerequisite gates. Review found four defects: it never engaged the
program-search boundary invariants its lead consumer (evolutionary search)
is governed by, and invariant 1 there prohibits exactly its mechanism
("no `eval` … candidate execution starts as a new registered child run");
its partial-fragment evidence and mid-flight state-reuse semantics
reintroduce reconciliation machinery the adopted at-least-once ruling just
retired; its `updates-state` grants replace a process boundary with a new
authority-checking kernel that must be airtight; and its value was gated
behind the system's self-admitted highest-risk rearchitecture (authority
inversion) plus three other gates.

This revision keeps what was strong — full-pipeline staged checking,
rejection as a routable typed outcome with phase tags, persisted-source
discipline, extern allowlists, the dry-run bounded-holes rule, the honest
null hypothesis — and re-founds the architecture on a decomposition: the
proposal's value is three separable capabilities, only the last of which
needs the dangerous mechanism.

## Decomposition

| Capability | Mechanism | Invariants weakened | Prerequisites |
| --- | --- | --- | --- |
| **C1 — typed static checking** (`check-workflow`) | ordinary full compiler behind one durable result boundary; executes no candidate | none | the C1 compile-path, content-identity, diagnostic-envelope, and M2-fit entry proofs below |
| **C2 — typed generational execution** (`run/spawn`, `run/probe`, `run/resume` adapters) | ordinary child runs behind certified adapters | none | existing adapter contract plus the single-writer and no-resume-domain entry proofs below |
| **C3 — in-run fragment execution** (`eval-workflow`) | activations inside the parent run | one, with compensation (§C3) | authority inversion (G2), bounded recursion (G3), checkpoints (G1), plus C1/C2 usage evidence |

The composition `C1 → C2 → match` already is "generate, check, run, route
on the outcome" with every boundary typed:

```lisp
(let* ((verdict (check-workflow :source frag :entry "cand::run"
                                :expects candidate-signature
                                :effect-bound candidate-effects
                                :externs candidate-externs)))
  (match verdict
    ((REJECTED_STATIC r) (route-rejection :diagnostics r.diagnostics :phase r.phase))
    ((STATIC_OK ok)
      (match (run/spawn :source frag :entry "cand::run" :inputs task.spec)
        ((SPAWN_COMPLETED c) (route-success :outputs c.outputs :run c.run-id))
        ((SPAWN_FAILED f)    (route-runtime-failure :evidence f.evidence))))))
```

What C3 would add over this composition is exactly: a shared evidence tree
under one run, a single resume lineage, no process-spawn cost, and
fuel-bounded in-run composition. That residual delta is the entire
remaining case for C3, and this document treats it as an empirical
question C1/C2 usage evidence must answer — the source draft's own
go/no-go logic, promoted from a paragraph to the architecture.

## Problem (Retained, Rescoped)

Three families push against the same wall:

- **Run repair** (`generic_run_watchdog`): probes re-derive by hand, in
  Python, facts the runtime holds in typed form; repair actions
  (`python -m orchestrator resume <id>` in prompt text) are invisible to
  both runs' contracts.
- **Self-hosting development** (`lisp_frontend_design_delta` family):
  workflows that design language features cannot compile-check their own
  outputs as a typed gate; the check is delegated to prose instructions in
  provider prompts.
- **Evolutionary search** (MLEvolve family, trial-runs E3): candidate
  programs need a static fitness filter with machine-routable failure
  kinds, and generational execution with typed linkage.

The third family is served by C1 (legally — checking is certification, not
execution) and by the trial-runs platform (generationally). It is
deliberately **not** a consumer of C3.

## C1 — `check-workflow`: Full-Pipeline Static Checking As A Typed Step

### Form (conceptual)

```lisp
(defunion CheckVerdict
  (STATIC_OK
    (compiled_summary Path.check-summary)     ; Semantic-IR projection for review
    (entry_signature <structural-signature>)  ; existing compiler-catalog shape
    (effect_summary <structural-effects>))     ; existing effect-catalog shape
  (REJECTED_STATIC
    (diagnostics Path.check-diagnostics)      ; serialized diagnostics envelope
    (phase CheckRejectPhase)))                ; PARSE | EXPAND | TYPECHECK
                                              ; | LOWER | VALIDATE | SIGNATURE
                                              ; | EFFECT_BOUND | EXTERN | SCHEMA

(check-workflow
  :source   candidate.orc-source     ; typed path to a persisted .orc artifact
  :entry    "candidate::run"         ; module::export the fragment must provide
  :expects  candidate-signature      ; required entry signature (inputs + return)
  :effect-bound candidate-effects    ; entry effect summary must check subset-of bound
  :externs  candidate-externs)       ; the ONLY visible extern universe
```

### Semantics

1. The runtime-owned check step invokes the **exact ordinary full compiler
   path** — parse, expand, typecheck, effect/proof analysis, lowering, and
   final validation — on the fragment, with `:externs` as the only extern
   universe. There is no reduced or "lowering-equivalent" checker. Ambient
   externs are never inherited.
2. The fragment must export `:entry` with a signature accepting
   `:expects`' inputs and narrowing its return; the checked entry effect
   summary must be ⊆ `:effect-bound`.
3. Any failure yields `REJECTED_STATIC` with the persisted diagnostics
   envelope and one stable phase tag. The envelope carries an ordered bounded
   list of diagnostics; each diagnostic has a stable code, severity, optional
   authored source span, structural detail values, and stable secondary
   causes for any consulted gate that declined. Human message text is a view,
   never routing authority. **Rejection is an outcome, not an error**:
   loops route on it, and the diagnostics artifact is a mutation
   operator's input. A failure of the compile service itself (missing
   binary, schema fault) is an ordinary step error, not a verdict — a
   broken checker is a bug; a broken fragment is data.
4. Nothing executes, ever. `check-workflow` has no fragment-execution
   semantics at any version. It reads one artifact and writes evidence.

### Identity, persistence, reuse, and evidence

`check-workflow` is a **durable result boundary**, not an M2-elidable pure
projection. It reads a persisted source artifact, invokes the ordinary full
compiler, and returns a routable public verdict whose evidence may be needed
after resume. Its boundary identity binds the fragment SHA-256, the complete
declared dependency digest, compiler/bundle identity, compile-service schema
version, extern-allowlist digest, expectation digest, and effect-bound digest.
Within one run, an already committed verdict is reused only after the normal
root/callee, checkpoint, input, identity, and result-envelope validations.
There is no cross-run memo and no effect-identity memo key.

Evidence under the step root is limited to the boundary identity, the exact
verdict envelope, the source-artifact lineage pointer when applicable, and
declared diagnostic/summary views. Pure projections derived from this
validated verdict use accepted M2 value-free completion shells and transient
replay; they do not duplicate the verdict as durable derived state. An
interrupted, uncommitted check attempt is discarded and re-run through the
landed ML at-least-once path under the runtime's fail-fast run-lifetime
single-writer lock.

### Dependencies

`compile_stage3_entrypoint` exists and is already used by
`build_frontend_bundle`, but that does not prove it is a public, reentrant,
content-addressed checking service. Before C1 planning, entry fixtures must
prove that the exact ordinary full compile path can be invoked repeatedly
without path-keyed stale reuse; that all source/dependency bytes and compiler
identity enter the boundary digest; and that the compiler can produce the
stable coded envelope above. If the current projection cache is path-keyed,
the smallest content-keyed correction joins C1's component plan. Missing
extern-universe restriction, schema stamping, or stable envelope serialization
is implementation work, not an assumed capability. C1 does not add candidate
execution.

### Consumers, day one

- Self-hosting dev loops: a typed compile gate replacing prose
  instructions ("run validate and read the output") in provider prompts.
- Trial-runs E3: the static fitness filter as a typed step — this is the
  concrete form of that design's "diagnostics as a stable machine API"
  substrate dependency, and the phase-tag enum is what its mutation
  operators route on.
- Any workflow that consumes generated `.orc` and wants fail-closed
  admission before spending provider attention (design principle 30).

## C2 — Certified Generational Execution Adapters

Promoted unchanged in intent from the source draft's T0, under the
existing command adapter contract; no new runtime capability.

- **`run/probe`** — typed probe of a target run: status enum (never free
  text), step summary, failure classification, evidence paths. Seed:
  `probe_orchestrator_run.py`, which implements most of this without a
  contract today.
- **`run/spawn`** — launch a workflow as a child generation: inputs =
  source path, entry, extern files, inputs file; outputs = typed run-id,
  terminal status enum, declared expected-output paths with fail-closed
  validation that the child actually produced them.
- **`run/resume`** — typed resume with the same outcome discipline.

All three adapters use the landed ML at-least-once and single-writer run
contract. `run/spawn` creates one ordinary child root with one writer;
`run/probe` is read-only; `run/resume` requests ordinary validated resume and
never writes child state itself. Interrupted, uncommitted child effects are
discarded and re-run by the owning runtime; committed results retain their
existing validated reuse. Each run holds the landed fail-fast run-lifetime
writer lock; a competing writer is rejected rather than merged or serialized
through adapter-specific machinery.

`run/resume` explicitly excludes lean-pilot attempts and every other run
domain whose durable contract says `resumability = never`. The adapter keys on
that semantic property, never on a path or family name, and refuses with
`run_resume_target_nonresumable`, including the rejected run identity and
resumability fact. Interrupted pilot blocks remain pilot outcomes; C2 cannot
reinterpret them as ordinary resumable child runs.

Relationship to trial-runs' `run-ref`: one supervision vocabulary, two
workspace modes. `run/spawn` runs the child in the parent workspace
(repair, dev loops); `run-ref` materializes a pinned repository revision
(experiments, candidates). The two must share the outcome vocabulary
(status enums, evidence shapes) so routing code is mode-agnostic; the
trial-runs design owns the pinned mode, this document owns the adapters,
and the shared enums land in whichever tranche is admitted first.

This shared vocabulary is a target contract, not a proof that current
adapters and future `run-ref` can already share result bytes. Before C2
planning, a minimal fixture must prove stable spawn/probe/resume envelopes,
one-writer ownership, ordinary committed-result reuse, fresh rerun of an
incomplete effect, and both directions of the `resumability = never` gate.

Exit criterion (retained verbatim in spirit): `generic_run_watchdog` and one
non-tool-using or deterministic MLEvolve candidate loop rewritten against
these adapters, with zero `python -m orchestrator` text in any provider
prompt. C2's usage record is the primary go/no-go input for C3. Candidate
execution remains subject to the trial-runs design's invariant-6 exclusion;
the adapters add no sandbox or authority.

## Boundary Compliance

Against `workflow_lisp_program_search_boundaries.md`, whose scope is any
program-search, self-modification, or evolution feature:

| Invariant | C1 | C2 | C3 (parked) |
| --- | --- | --- | --- |
| 1 — immutable generations; full pipeline; **no eval**; child runs | Satisfied: checking is certification of candidate *data*; nothing executes | Satisfied: children are ordinary registered runs | **Violates the no-eval clause for its own consumers; therefore C3 is normatively closed to search/evolution candidates (rule below)** |
| 2 — provider output is untrusted data | Strengthened: C1 gives the untrusted-data path a typed verdict | Satisfied: execution only of persisted, checked source | Inherits the C3 rule |
| 3 — neutral substrate vs feature | Satisfied: verdicts/enums carry no optimizer vocabulary | Satisfied | Satisfied |
| 4 — whole-candidate evidence | Not implicated (no fitness authority here) | Satisfied: child-run evidence is whole-run | Not implicated |
| 5 — evidence separation | Not implicated | Controller-owned, per trial-runs | Not implicated |
| 6 — honest security boundary | Nothing executes | Adapters add no isolation. Search/evolution candidates use only deterministic effect-free, text-only/no-tool, mock/replay, or genuinely sandboxed execution as required by the trial-runs design; ordinary authored runs retain their existing contract. | C3 remains closed to search/evolution candidates and adds no selected isolation work. |
| 7 — no runtime code values | Satisfied: `:source` is a path, verdicts are data | Satisfied | C3 executes fragments but never reifies them as values |
| 8 — role-separated prompt identity | Inherited unchanged | Inherited unchanged | Inherited unchanged |

**Normative rule (this design's substitute for an invariant-1 amendment):**
search/evolution candidate *execution* uses generational child runs only
(`run/spawn` or `run-ref`). `eval-workflow`, if it ever lands, is not
available to that purpose; a trial or evolution controller invoking it on
candidate source is a policy violation, reviewable in the same way as a
gene-bound breach. Lifting this rule is the amendment debate, to be had
then, explicitly, against recorded C1/C2 usage evidence — not implied now.

## C3 — `eval-workflow`, Parked Terminal Tranche

Retained as a candidate direction because the residual delta (shared
evidence tree, single resume lineage, no spawn cost, fuel-bounded in-run
composition) is real for the repair and self-hosting families. Rewritten
from the source draft in three ways, then parked.

### Retained design

Persisted-source-only discipline (no strings; digest-verified resume,
fail-closed on mismatch); extern allowlist or nothing; full Stage-3 check
via C1's service before any fragment effect; tagged outcome union
(`ACCEPTED` / `REJECTED_STATIC` / `EXHAUSTED`) that routing must `match`
on; fuel with strictly decreasing eval-depth and a typecheck-time
contradiction diagnostic for depth-0 grants; the dry-run rule that eval
sites render as *bounded holes*, visually distinct from enumerated steps,
never as enumerated certainty; macro expansion to `eval-workflow` requires
the site's declared effects to include the eval effect.

### Rewritten: no parent-state authority

The source draft's `updates-state` grants are **removed entirely**. A
fragment receives a runtime-allocated private write root and its declared
typed inputs; its only channel into parent state is the typed `ACCEPTED`
payload, validated at the boundary exactly like a provider step's
structured result. No grant checker exists because no grant exists. This
restores the property the process boundary gave for free: candidate code
cannot address the parent run's typed state, structurally.

### Rewritten: at-least-once execution semantics

All-or-nothing at the eval boundary. `EXHAUSTED`, crash, or interruption
discards the fragment's private write root wholesale — no partial
evidence, no mid-fragment resume, no reconciliation of completed fragment
effects. A completed verdict is a committed result reused on resume; an
incomplete evaluation reruns fresh under a new activation ordinal. This
deletes the source draft's most complex machinery and aligns with the
adopted at-least-once ruling. Consequence accepted: a nearly-complete
fragment's work is discarded on interruption; fragments wanting durable
partial progress are the generational path's use case, by design.

### Re-entry conditions (all required, none waivable by this document)

1. **Usage evidence:** C1 and C2 in production use, with a recorded review
   finding concrete workflows where the composition demonstrably fails to
   serve — where the shared-lineage/shared-evidence delta is the blocker,
   not convenience.
2. **G2 on its own merits:** authority inversion carries Level-B dual-run
   equivalence evidence on promoted families, sequenced and priced by its
   own owners. Eval's attractiveness must not re-price G2's risk (retained
   verbatim from the source draft — its best sentence).
3. **G1/G3 as specified** in their own documents (checkpoints proven on
   the flat route; bounded recursion via activation ordinals).
4. **Boundary review:** the normative closure of C3 to candidate execution
   re-affirmed, or the invariant-1 amendment debate held explicitly.

## Diagnostics Registry Additions

C1 stable rejection codes: `check_source_not_orc`, `check_entry_missing`,
`check_signature_mismatch`, `check_effect_bound_exceeded`,
`check_extern_not_allowlisted`, `check_service_schema_mismatch`.
C2: adapter-contract outcome enums (spawn/probe/resume status,
`spawn_expected_output_missing`, `run_resume_target_nonresumable`).
C3 (reserved, not registered until unparked): `eval_fuel_contradiction`,
`eval_fuel_exhausted`, `eval_digest_mismatch_on_resume`,
`macro_hidden_effect` extension.

Every rejection envelope includes the code and rejected structural value or
identity fact. Phase tags provide coarse routing; stable codes provide precise
routing; rendered prose remains a non-authoritative view.

## Design-Principle Compliance

- **Principle 28 — refusals name their rule.** C1 and C2 expose the stable
  codes above, attach a declined gate to any downstream consequence, and key
  authority on signature/effect/resumability facts rather than identifier
  spelling.
- **Principle 29 — types are opt-in constraints.** `:expects`,
  `:effect-bound`, and typed child outputs constrain only what the caller
  requests. Structural records are admissible without nominal re-wrapping;
  nominal force is reserved for rooted evidence paths, routed verdict
  variants, and persisted run/boundary identities. Signature and effect
  projections reuse the compiler's existing structural catalogs rather than
  introducing `SignatureEcho` or `EffectSummaryEcho` brands.
- **Principle 30 — conserve provider attention.** Compilation, signature and
  effect checks, child lifecycle commands, output validation, and routing are
  deterministic mechanisms. They never become instructions in a provider
  prompt. Prompt prose is retained only for genuinely ambiguous authored
  judgment.

## Roadmap

| Tranche | Depends on | Delivers | Evidence gate |
| --- | --- | --- | --- |
| C1 `check-workflow` | ordered design approval; compile-path/content-identity/envelope/M2-fit proofs; explicit selection and a new unassigned post-2.23 target | typed static checking step; stable-code and phase-tag routing | both-direction service fixtures; envelope golden files; one dev-loop workflow using the gate; same-run committed-result reuse and M2-compatible derived replay proven |
| C2 adapters | ordered design approval; command adapter contract; single-writer/no-resume-domain proof; explicit selection and a new unassigned post-2.23 target | `run/probe`, `run/spawn`, `run/resume`; shared outcome vocabulary with `run-ref` | adapter fixtures; ordinary child crash/resume proof; nonresumable-attempt refusal proof; watchdog + one admissible candidate loop migrated; zero CLI text in prompts |
| C3 `eval-workflow` | parked | — | re-entry conditions above |

C1 and C2 are independent and may proceed in either order or in parallel
only after ordered design review and explicit roadmap selection. Both land
spec-first (`specs/dsl.md` form/adapters,
`specs/state.md` evidence shapes, `specs/versioning.md` target row);
C1 adds one bounded runtime-owned compile/result boundary but no candidate
execution; C2 stays behind certified command adapters. Neither weakens an
adopted invariant.

## What This Approach Makes Harder

- The composition `check → spawn` re-reads and re-compiles the fragment in
  the child (the check verdict certifies admission; the child's own
  compile remains the execution authority). Cost: one redundant compile
  per accepted fragment — negligible against provider time, and it
  preserves "the child is an ordinary run" with no certification-transport
  machinery.
- Cross-generation evidence stays per-run, joined by typed run-ids rather
  than a shared tree; tooling that wants one tree must render the join
  (`orchestrate report` following spawn edges) instead of reading one
  root.
- Workflows genuinely needing in-run typed composition of generated
  fragments wait for C3 or restructure around the generational path.

## Rejected Alternatives

Inherited from the source draft and still correct: journal-replay eval
substrate; eval on the flat runtime (second identity lane in disguise);
string-based eval; ambient extern inheritance. Added by this revision:
**in-run eval as the v1 mechanism** (rejected for the four defects in
§Revision Provenance — boundary collision, at-least-once regression,
grant-kernel surface, five-gate sequencing); **parent-state grants at any
version** (rejected outright: the typed return is the only channel).
"Sub-runs forever" is retained as the explicit null hypothesis: if C1+C2
usage never surfaces the residual delta, C3 is not built, and that is this
document succeeding, not failing.

## Review Questions

1. `run/spawn` inputs transport: file-based only in v1 (inputs file +
   extern files), matching the CLI contract, or typed value transport?
   Default: file-based; revisit with C2 usage.
2. Do the C2 adapters and `run-ref` share one status enum family from
   birth, or converge at the second tranche? Default: shared from birth;
   the first admitted tranche defines it, the other consumes it.
