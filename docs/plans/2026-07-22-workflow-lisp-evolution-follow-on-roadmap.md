# Workflow Lisp Evolution Follow-On Roadmap

Status: incorporated as the tracked E-series program (2026-07-30 owner
decision), superseding the 2026-07-24 parked disposition that was recorded
per the architectural critique at
`artifacts/review/roadmap-follow-on/architectural-critique.md`. Not active
work instructions and not a selector. The durable boundary invariants live in
`docs/design/workflow_lisp_program_search_boundaries.md`; the historical
slimmed E0 probe remains unselected and its framing is superseded by the
tracked, accepted canonical E0 trial-runs design, while the E4P
prompt-identity discipline is owned only by Stage Q3 of the active
language-quality successor roadmap. The current program shape and its
sequencing gates are recorded in the section below; the remainder of this
document is the detailed historical reference.

Created: 2026-07-22

Last materially updated: 2026-08-01

Current implementation status: the recovered E0/C1 designs passed ordered
`E_DESIGNS_SPEC_APPROVED` then `E_DESIGNS_QUALITY_APPROVED`. ML closure and
the lean-pilot owner-decision handoff are complete. The
[E0 direct-control component plan](2026-07-31-workflow-lisp-e0-direct-control-component-plan.md)
passed ordered `E0_PLAN_SPEC_APPROVED` then `E0_PLAN_QUALITY_APPROVED`. E0 is
complete, and E1 has passed its final gate. E0 Task 1's canonical
source and compile contract landed at `b71bf62a`; Task 2 runtime proof landed
at `3d41a8bf`; and Task 3 accounting-parity proof landed at `3b934373`. Task 4
closed at `46387582`.
E0 is complete at `fe7d6f9bca9ec61b9078e4048bb43aee7f4f191b`, tree
`c20f6fd9197b0d0e12a581e96ebbd898b8d1b3c3`, with outcome `PASS_E0` after
ordered `E0_FINAL_SPEC_APPROVED` then `E0_FINAL_QUALITY_APPROVED`; the fresh
postcommit direct-control/routing/route-readiness control passed 115 tests.
The owner selected E1 through E3 on 2026-07-31 through the
[durable selection record](2026-07-31-workflow-lisp-e1-e3-owner-selection.md).
E1-E3 are owner-selected, but their accepted dependency order remains
binding. E1 Tasks 0–9 are complete under the
[reviewed target-2.24 plan](2026-07-31-workflow-lisp-e1-run-ref-component-plan.md)
and [plan review](../../artifacts/review/e1-run-ref-plan-review.md). The
[final review](../../artifacts/review/e1-run-ref-final-review.md) records
`PASS_E1` at commit `577715f176fcacf9c29127f8b519d58c3a5b6470`, tree
`ef7eacbdb747d09754d02aab328606893dad07e3`, after ordered
`E1_FINAL_SPEC_APPROVED` then `E1_FINAL_QUALITY_APPROVED`; its fresh
postcommit control passed 864 tests. The
[target-2.25 E2 component plan](2026-08-01-workflow-lisp-e2-trial-component-plan.md)
is accepted at `c6046d38`, tree `40c533fc`, after ordered
`E2_PLAN_SPEC_APPROVED` then `E2_PLAN_QUALITY_APPROVED`; see the
[plan review](../../artifacts/review/e2-trial-plan-review.md). Task 1 is
selected, but no E2 behavior exists. E3 remains selected pending the
canonical E2 exit gate and review of the first fixed study. E3 adds no
language target.
Selection does not waive any feasibility,
spec-first, ordered-review, focused, broad non-security, end-to-end, or exit
gate. C1, C2, and C3 remain Designed and unselected.

Copy safety: planning reference only. The canonical direct-control source is
copy-safe after `PASS_E0` only for its bounded one-call direct-task shape. The
implemented target-2.24 `run-ref` syntax is promoted only within the exact
normative specs and reviewed component contract after `PASS_E1`; the accepted
target-design examples and every E2+ trial, controller, prompt-program, or
sandbox surface remain non-copy-safe.

## Current E Program Shape And Gates (2026-07-30)

This section is the authoritative E-series sequencing surface. Where it
conflicts with the historical proposal below, this section governs. The
historical Stage-6/Gate-S8 activation language below is obsolete: Gate S8 is
complete.

Current shape:

- **E0 (canonical):**
  `docs/design/workflow_lisp_trial_runs.md`, accepted. It
  supersedes the slimmed E0 discriminating-benchmark probe framing.
- **C1 (companion):** the typed program gates design
  (`docs/design/workflow_lisp_typed_program_gates.md`, tracked and
  accepted; `check-workflow` companion primitives).
- **Governing invariants:**
  `docs/design/workflow_lisp_program_search_boundaries.md` (adopted) binds
  any search/evolution execution.
- **Layer-0 admission gate:** the orc-effectiveness lean pilot
  (`docs/superpowers/specs/2026-07-26-orc-effectiveness-lean-pilot-design.md`
  with plan
  `docs/superpowers/plans/2026-07-26-orc-effectiveness-lean-pilot.md`). Its
  owner-decision handoff is complete at
  `docs/reports/2026-07-31-orc-effectiveness-lean-pilot-owner-decision.md` and
  authorizes E0 activation without automatically selecting E1+.

Canonical tranche mapping:

| Tranche | Sole current meaning |
| --- | --- |
| E0 | canonical one-call direct control and accounting-parity fixtures |
| E1 | pinned-workspace child execution through `run-ref` |
| E2 | concurrent trial arms, evidence freezing, blinding, and adjudication |
| E3 | external gene-bounded controller over admitted E0-E2 contracts |

The historical ledger below is provenance only and cannot redefine or select
these tranches. C1 is a companion design; C2/C3 from that companion remain
deferred unless separately incorporated.

Sequencing prerequisites (owner-directed 2026-07-30):

1. E0/C1 drafting proceeds concurrently now, but both drafts must state that
   trial execution assumes the landed ML at-least-once plus single-writer
   run contract (not the retired provider-interruption quarantine), and that
   trial persistence shapes are subordinate to the accepted M2
   persistence-parsimony design.
2. E0/E1 implementation is gated on ML closure (kill-mid-provider
   crash-resume E2E green) and the lean-pilot owner-decision handoff. Both
   prerequisites are satisfied; design approval, a reviewed component plan,
   and explicit tranche selection remain required.
3. M2 design acceptance precedes freezing E0 persistence/evidence contracts,
   so E0 adopts the parsimonious value-free completion shells and durable
   effect/public-boundary facts rather than creating a migration for M3.
   Accepted M2 component (a) creates no effect-identity memo key; any future
   memo key requires separately selected M2(b)/M3b work and Q3 identity.
4. MC, MR, and M4 substrate phases never block E work.
5. Under at-least-once semantics the lean pilot's no-resume rule is
   load-bearing: pilot runs are never resumed; interrupted pilot blocks stay
   outcomes per the pilot specification.

Incorporation was not selection. The separate 2026-07-31 owner decision now
selects E1 through E3 in dependency order; it does not select C1-C3 or waive
the reviewed-plan and predecessor-exit gates above.

Successor ordering (owner-directed 2026-07-30): the
[LSP frontend prerequisites P-series roadmap](2026-07-30-lsp-frontend-prerequisites-p-series-roadmap.md)
is sequenced after this E program; the P-series enters selection only after
E's recorded completion or an explicit owner closure/re-park decision, with
owner acceleration as the sole exception.

## Purpose

Define a conditional, evidence-driven program for:

- compiler-certified variants over immutable Workflow Lisp bundles;
- neutral registered execution instances and child-workflow trials;
- replaceable code-search and evolutionary controllers;
- optional context-stratified subject adjudication and independently selectable
  inert fragment archives;
- later role-separated prompt identity and prompt evolution; and
- only eventually, if real isolation exists, effectful mutation.

This roadmap sequences the target architecture in
[`2026-07-22-workflow-lisp-evolution-substrate-and-feature-design.md`](../superpowers/specs/2026-07-22-workflow-lisp-evolution-substrate-and-feature-design.md).
It does not redefine that design, the Workflow Lisp frontend, or runtime
specifications.

The program is intentionally allowed to stop after any gate. A stopped feature
experiment must not turn into pressure to keep building language machinery.
Neutral substrate may advance only when it has demonstrated value independent
of one optimizer.

## Authority And Routing

The following authority order applies:

1. Normative runtime and DSL behavior remains in `specs/`.
2. The evolution substrate and feature design owns target architecture,
   invariants, terminology, trust boundaries, and stop criteria.
3. This roadmap owns only proposed order, dependencies, evidence gates, and
   activation mechanics.
4. A future tranche design and implementation plan may narrow its tranche, but
   may not weaken the umbrella design or silently activate a later tranche.

The procedure-first sequence, including Stages 6-8, is complete. The active
selector is
[`2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`](2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md).
This parked document does not amend that order, change an active workflow,
create a machine-readable tranche manifest, or make E0 selectable.

Readers looking for current authoring behavior must continue to use ordinary
static `.orc`, compile-time `ProcRef`, external source generation, and new
immutable runs. The current capability status matrix and accepted frontend
designs remain authoritative.

## Why A Separate Follow-On Program

The proposal combines four questions that should not be allowed to validate
one another circularly:

1. **Substrate value:** does compiler-owned identity, certification, and trial
   coordination materially improve on ad hoc source-generation tooling?
2. **`.orc` controller value:** does expressing a controller in Workflow Lisp
   improve typed recovery, auditability, or integration over an external
   controller using the same public substrate?
3. **Optimizer value:** does a genetic or other adaptive search policy beat
   random, enumerative, or simple local search after full cost accounting?
4. **Fragment-search value:** after candidate-only code search works, does
   context/background-stratified subject selection improve sample efficiency or
   outcomes enough to justify its observation and archive machinery?

The
[candid effectiveness analysis](../reports/2026-07-22-compelling-example-search-and-effectiveness-doubts.md)
that preceded this roadmap found no existing five-minute artifact that answers
these questions. The roadmap therefore starts with evidence collection and
preserves independent baselines throughout. It does not use the system's
self-hosting history, a toy that merely compiles, or the existence of a complex
substrate as proof of effectiveness.

## Decision

If explicitly activated, use a conditional E-series around and after the
current S-series:

```text
current authority:  S6  ->  S7  ->  S8
                     \
                      E0 proving experiment
                         (non-blocking; no public language/runtime surface)

E0 = PROCEED_TO_E1 and S8 complete
                  |
                  v
                 E1 neutral subject/certification substrate
                  |
                  v
                 E2 neutral execution/trial substrate + public SDK/CLI
                  | \
                  |  +--> E4P prompt identity (independent non-evolution value)
                  |
                  +--> optional E2O contextual subject observation/aggregation
                  |         ^                                  |
                  |         |                                  |
                  v         |                                  |
                 E3 candidate-only code evolution               |
                  | \                                           |
                  |  +-- fragment hypothesis; activate E2O if --+
                  |                              not already passed
                  |                                  |
                  |                                  v
                  |                                 E3F
                  |                     contextual fragment search
                  |
                  +-- prompt hypothesis + retained substrate/controller --+
                                                                         |
E4P retained ------------------------------------------------------------+
                                                                         v
                                                                        E4E
                                                              bounded prompt evolution

E5 effectful evolution is an independent deferred horizon:
retained E2 substrate + separate sandbox/capability program
+ a new explicit roadmap amendment. Neither E4P nor E4E unlocks E5.
```

After explicit activation, E0 may begin once Stage 6 reaches an explicitly
recorded clean, committed checkpoint and no active Stage-6 operation can
overwrite its files. The complete E0 experiment and independent rerun use one
exact commit-pinned immutable source snapshot, dependency lock, compiler/runtime
build, and environment contract. The snapshot lives outside the mutable shared
checkout, using a content-addressed archive or disposable clone rather than a
git worktree. If a trial would import the changing shared checkout, E0 stops
until an immutable snapshot is available.

With that pinning, E0 is non-blocking with respect to Stages 7 and 8: a
negative or delayed E0 outcome must not delay those stages, and S7/S8 commits
cannot change the E0 implementation under test. Shared-checkout edits and broad
test gates remain serial.

E1 and later normally wait for Gate S8. Advancing them earlier requires an
explicit amendment to both the active execution sequence and this roadmap,
including a shared-surface conflict analysis. The reason is practical rather
than semantic: E1-E3F edit compiler, IR, runtime, identity, SDK, and
documentation surfaces that Stages 7-8 are intended to settle.

## Alternatives Considered

### Alternative A: Add One Monolithic Stage 9

Reject. A single stage would let a successful toy conflate substrate,
controller, and optimizer value; would couple neutral registry work to genetic
algorithm policy; and would make prompt or effectful mutation appear inevitable
once code mutation begins.

### Alternative B: Insert Evolution Before Provider Live Binding

Reject as the default. The pure slice does not need provider live binding, and
prompt/provider identity should be designed against the settled provider
transport rather than chase it. Editing shared compiler/runtime surfaces while
Stages 6-8 are active also raises avoidable coexistence risk.

### Alternative C: Keep Everything External

Retain as a valid terminal outcome, not the initial decision. E0 deliberately
uses an external controller. If ordinary source generation, compilation, new
runs, and an external ledger prove sufficient, the correct result is to stop
without adding a public substrate. If neutral substrate helps but a `.orc`
controller does not, keep the controller external.

### Selected Approach: Conditional Neutral Substrate, Then Optional Features

Separate neutral compiler/runtime capabilities from evolution admission and
from any particular optimizer. Require a useful non-evolution consumer before
calling the substrate general. Admit prompt and effectful mutation only through
their own later gates.

## Program-Wide Architectural Boundaries

Every tranche must preserve these boundaries.

### Immutable Generation Boundaries

- A running bundle is never modified.
- Mutation produces a proposed next bundle or runtime binding snapshot.
- Every code candidate passes through the ordinary full compiler pipeline.
- Execution starts as a new registered child run; no `eval`, hot swap, dynamic
  linking, or checkpoint import turns candidate data into executing code.
- Promotion proposes a reviewable patch and never edits canonical source as a
  side effect of evaluation.

### Neutral Substrate Versus Feature

The neutral substrate may know about:

- concrete operation contracts;
- compiler-owned subject manifests;
- rewrite proposals and certification policies;
- immutable variants;
- registered execution instances;
- exact trial identity, budgets, evidence, and reconciliation; and
- when E2O is activated, compiler-owned call-site/visit identity, bounded
  context classifiers, subject-evaluation contracts, and hierarchical
  visit/trial/context aggregation.

It must not know about:

- genomes, populations, generations, crossover, mutation probabilities;
- fragment archives, locus/background selection, fitness, winner, elite, or
  selection semantics; or
- optimizer-specific lineage.

Evolution admission may bind validated genes to one neutral execution
instance. A replaceable controller may propose and select candidates only
through those public contracts.

E3 selects whole candidates. E3F may additionally select inert
`SubjectRealizationId` records under a feature-owned fragment-search contract.
Those records are proposal inputs, not executable fragments: every placement
still creates a complete immutable bundle, passes ordinary certification, and
runs whole-candidate trials.

### Typed Operation Parity Without Kind Erasure

E1 begins a common, concrete, monomorphic metadata view for typed operations:
stable identity, input type, output type, effect summary, source/provenance, and
invocation durability. This improves inspection and lets tooling compare
contracts.

It does not make the operation kinds interchangeable:

- a procedure is a statically lowered internal reuse unit;
- a workflow is a durable public run/resume boundary;
- a provider call is an effectful invocation with fixed provider, transport,
  prompt, tool, and context bindings.

Matching input and output types alone never proves semantic substitutability.
There is no universal runtime `Callable`, runtime closure, dynamically selected
workflow/procedure/provider value, or effect-erasing adapter in this roadmap.
Any later interoperation remains compile/generation-time and must preserve the
kind-specific effect and identity contract.

### Role-Separated Prompt Environments

Prompt-related identity is not one lexical or ambient hash. Tranches must keep
five roles distinct:

- a prompt definition/value enters a subject realization domain only when the
  compiler proves it is an actual resolved free binding of that subject;
- a prompt program's used semantic IR/import/free-binding dependencies enter
  its dependency-minimal registered `SemanticProgramId`, while unused
  imports/bindings do not;
- fixed prompt-program captures and dependency contracts enter a protected
  prompt-composition environment and candidate/execution identity;
- typed prompt/context inputs, fresh dependency snapshots, rendered bytes, and
  transport enter one governed per-attempt composition snapshot, while a
  complete call ledger distinguishes not reached, preparation failure,
  dispatch, and missing evidence; and
- during E3F code-fragment comparison, every prompt gene and structured
  prompt/provider/context call binding is pre-treatment background, while
  bytes influenced downstream by the code treatment are recorded as mediators
  rather than forced equal.

E4E owns prompt genes as whole-candidate/arm treatments. E3F does not acquire
prompt-fragment selection or a generic gene-locus archive by implication.
Ambient context policy remains a separate context-policy assignment rather
than being double-owned by a prompt-program instance.

Experimental-arm identity is likewise not a controller label. E3 introduces a
content-addressed experiment design with exact mutation masks, fixed assignment
complements, closed execution envelopes, randomization/input/seed policies, and
budget authority, plus frozen common inputs, same-arm information and parent
provenance, pre-work metered feature-work allocation, trusted candidate-arm and
pre-launch trial-arm bindings, a common analysis freeze, conformant controller
decisions, and complete feature-work/trial ledgers. Feature work includes
controller transitions, aggregation, comparison, and archive operations as well
as proposal, provider, compiler, certification, and admission work. E4E extends
that mechanism with prompt-only, code-only, and joint profiles; it does not
infer arm membership after seeing outcomes or let one arm externalize discovery
or feature cost to another.

### Honest Security Boundary

A candidate workspace is an output boundary, not an OS sandbox. E0-E3F accept
only an effect-free deterministic harness. E4E accepts only text-only/no-tool,
mock, replay, or genuinely sandboxed provider calls. E5 cannot start until a
separate security design and positive isolation evidence exist.

### Evidence Separation

Every optimization benchmark separates:

- adaptive search data;
- validation data used to choose among already-produced candidates; and
- a sealed promotion holdout opened only after candidate generation, analysis,
  and selection freeze.

The promotion holdout never feeds mutation, selection, evaluator tuning, or
benchmark selection.

### Existing-Substrate Reuse

Before a tranche design or plan proposes a registry, allocator, ledger,
snapshot, reconciliation path, or comparison engine, it must publish a
validated reuse inventory. For each proposed mechanism, the inventory records:

- its intended owner and contract;
- the existing substrate inspected;
- `REUSE`, `EXTEND`, `REPLACE`, or `NEW`, with the exact missing capability;
- why any divergence is necessary; and
- the migration and retirement obligation for a parallel or replaced surface.

The minimum inspection set is the durable run-state store and ordinary
resume/reconciliation machinery, existing artifact/evidence ledgers, the
retained Workflow Lisp migration-parity kernel, content-addressed compiler
artifacts under `.orchestrate/build/<hash>/`, the stdlib/compiler pipeline, and
the implemented immutable per-attempt provider-dependency snapshot contract.
These are reuse candidates, not evidence that they already satisfy an E-series
contract; a tranche must prove the fit or record a bounded gap. In particular,
the existing build tree proves build/provenance reuse, not trusted variant
registry, retention, revocation, or signed-handle authority, and the existing
provider snapshot covers only the attempt-dependency component of E4P.

E3 uses the retained migration-parity target-loading, comparison-report,
Markdown/index, gate, and CLI core as the default starting point for its
behavior side-by-sides. Direct reuse requires a minimal non-YAML comparison
fixture or extraction of a neutral comparison core because the current target
schema is migration-specific. A bespoke parallel path requires an accepted
reuse-inventory gap, explicit justification, and a named retirement owner. The
validated inventory belongs in the tranche evidence bundle; any rendered
inventory report is a view.

### Experimental Substrate Lifecycle

Until Gate E3 or `EARLY_SUBSTRATE_DISPOSITION` selects `RETAIN_SUBSTRATE`,
implemented E1/E2 surfaces remain experimental and non-promoted. Their
capability-matrix rows use the accurate implementation status but set normal
new-author use to `No` and state
`experimental/non-promoted pending substrate disposition` in routing notes.
Public accessibility of an E1 API or E2 SDK/CLI is not an external stability
promise.

No compatibility or external-stability commitment may be made before the
substrate disposition. Every E1/E2 evidence bundle records known interim
adopters, their exact dependency, and whether deletion would affect them. A
proposed stable adoption before the substrate disposition requires a roadmap
amendment rather than silently making retirement impossible. A retained E2O or E4P use that
depends on E1/E2 must be dispositioned before
`RETIRE_EXPERIMENTAL_SUBSTRATE` can validate.

If an E-series route becomes terminal after an experimental E1/E2 surface has
landed but before Gate E3 can decide its disposition, a standalone
`EARLY_SUBSTRATE_DISPOSITION` record must apply the same accepted
reuse/adopter inventory and choose `RETAIN_SUBSTRATE` or
`RETIRE_EXPERIMENTAL_SUBSTRATE`. Retention records the promotion decision;
retirement authorizes E3R. This record carries no controller, optimizer, or
fragment disposition and cannot unlock a feature tranche. The program cannot
complete while landed experimental substrate lacks one of these reviewed
dispositions.

## Proposed Tranche Ledger

These rows are proposed, not `pending`: no executable manifest exists yet.

| Tranche | Status | Entry dependency | Primary decision |
| --- | --- | --- | --- |
| E0 — Proving experiment | Not activated | Accepted design/roadmap and a recorded clean Stage-6 checkpoint | Is there enough feature or coordination value to justify reusable substrate work? |
| E1 — Neutral subject and certification substrate | Not activated | Gate E0 says `PROCEED_TO_E1`; Gate S8 complete unless explicitly amended | Can variants be identified and certified without evolution concepts or mutable compiler ASTs? |
| E2 — Neutral execution and trial substrate | Not activated | Gate E1 passed | Can exact registered variants run through crash-durable public child-run paths without claiming sandboxing? |
| E2O — Optional contextual subject observation and aggregation | Not activated; optional | Gate E2 passed and either E3 readiness says `OBSERVATION_EXTENSION_REQUIRED` or retained E3 records `PROCEED_TO_FRAGMENT_HYPOTHESIS` | Can bounded visit/context evidence and neutral subject aggregation help neutral clients without imposing trace overhead or selection semantics on ordinary runs? |
| E3 — Candidate-only code evolution | Not activated | Gate E2 passed, plus either `BLACK_BOX_SUFFICIENT` or Gate E2O passed | Do bounded whole-candidate evolution and/or a `.orc` controller add value over simpler and external baselines? |
| E3R — Experimental substrate retirement | Not activated; conditional deletion | Gate E3 or an early substrate-disposition record selects `RETIRE_EXPERIMENTAL_SUBSTRATE`, and no retained dependent use makes that disposition invalid | Can every experimental E1/E2-dependent surface and route be deleted with complete reference, state, documentation, and verification evidence? |
| E3F — Contextual fragment search | Not activated; optional follow-on | E3 retains code evolution and records `PROCEED_TO_FRAGMENT_HYPOTHESIS`; Gate E2O passed; retained substrate and controller | Does independently selecting inert subject realizations outperform candidate-only search without weakening whole-bundle certification or whole-candidate authority? |
| E4P — Prompt identity | Not activated; independently selectable after E2 | Gate E2 passed and a non-evolution prompt-identity use-case/readiness brief is accepted | Is exact prompt/invocation identity independently useful and safe enough to retain? |
| E4E — Bounded prompt evolution | Not activated | E4P retained, E3 authorizes the prompt hypothesis (or an explicit amendment substitutes one), and the neutral substrate plus one controller remain retained | Can prompt search be evaluated reproducibly enough to justify the feature under a narrow no-tool envelope? |
| E5 — Effectful evolution | Deferred horizon, not scheduled | Gate E2 substrate retained, separate sandbox/capability program passed, and an explicit roadmap amendment | Can effectful candidates be isolated and bounded strongly enough to execute at all? |

## E0 — Proving Experiment

### Question

Can a small external controller use the current compiler and runtime to explore
one directly authored pure integer expression safely enough to reveal:

- whether adaptive search has any plausible advantage;
- which identity, lineage, trial, resume, and evidence mechanics are currently
  duplicated ad hoc; and
- whether that duplication is material enough to justify E1-E2?

E0 is a feasibility and measurement tranche, not a product demo and not a
claim that arithmetic expression search generalizes to workflows.

### Scope

Use:

- one ordinary `.orc` bundle;
- one explicitly marked, directly authored integer result-expression locus;
- a deterministic, transitive effect-free public harness;
- one exact commit-pinned source snapshot, dependency lock, compiler/runtime
  build, and environment contract for the complete experiment and rerun;
- generated candidate source in new immutable bundles;
- ordinary full compilation and new runs;
- an external controller and an external experiment ledger; and
- fixed search, validation, and sealed promotion-holdout suites.

Do not add:

- public `.orc` syntax;
- stable public subject manifests;
- a variant or candidate registry;
- a runtime trial primitive;
- an `.orc` optimizer;
- prompt/provider genes; or
- effectful candidates.

### Required Baselines

Use an equal evaluation budget for:

1. the chosen adaptive/genetic strategy;
2. random valid mutation;
3. a simple non-genetic strategy such as enumerative search, hill climbing, or
   beam search appropriate to the finite grammar; and
4. the direct human-authored baseline.

The benchmark must be large enough that all methods do not trivially enumerate
the entire space, yet small enough to reproduce deterministically. If no such
honest benchmark can be defined, E0 records `NO_DISCRIMINATING_BENCHMARK`
rather than selecting a flattering toy.

### Evidence

Record:

- best-so-far and area-under-best-so-far versus trial and wall-clock budget;
- invalid proposal and failed-trial rates;
- validation and sealed holdout results;
- independent rerun survival;
- compiler, run, evaluator, and environment identities;
- controller crash/restart behavior;
- every custom mechanism required for locus recovery, source rewriting,
  compiler-artifact association, content identity, lineage, trial allocation,
  result collection, and reconciliation;
- implementation and operator effort for those mechanisms; and
- the smallest code side-by-side showing the ad hoc path versus the proposed
  substrate call shape, clearly labeled as proposed rather than implemented.

### Gate E0

A reviewed decision record must choose exactly one outcome:

- `PROCEED_TO_E1`: a discriminating benchmark exists, the evidence is
  reproducible, and either feature value or substantial repeated coordination
  machinery justifies testing a neutral substrate;
- `KEEP_EXTERNAL_AND_STOP`: the experiment is useful but ordinary compiler/run
  APIs plus a small external library are sufficient;
- `REVISE_BENCHMARK_ONCE`: the mechanics work but the benchmark cannot
  discriminate; one named replacement benchmark is authorized; or
- `STOP_NO_COMPELLING_VALUE`: neither search value nor substrate value is
  supported.

`REVISE_BENCHMARK_ONCE` may be used once. A second non-discriminating result
becomes `STOP_NO_COMPELLING_VALUE`.
Any future routing record persists whether this single revision allowance has
already been consumed.

E0 completion does not activate E1. `PROCEED_TO_E1` is a prerequisite for a
separate activation decision after S8.

## E1 — Neutral Subject And Certification Substrate

### Question

Can the compiler expose stable, bounded descriptions of safe rewrite subjects
and certify proposed variants without exposing mutable AST authority or
embedding evolution policy?

### Deliverables

1. The common monomorphic operation-contract metadata schema, plus concrete
   projections only for the expression-owning operation and public workflow
   harness exercised by this tranche, preserving kind and effects. Do not build
   an estate-wide registry or provider projection speculatively; E4P adds the
   provider-invocation projection when prompt identity supplies a real use.
2. Compiler-owned `SubjectManifest` and bounded `SubjectManifestView` for the
   first directly authored pure-expression surface.
3. Rewriteability and conservative downstream-influence analysis; purity alone
   is insufficient.
4. Neutral `RewriteCertificationPolicy`, `RewriteProposal`, stale-preimage and
   overlap rejection, contextual whole-bundle certification, and diagnostic
   taxonomy.
5. Certifier-emitted inert `SubjectRealizationDomainId` and
   `SubjectRealizationId` plus a resolvable `SubjectRealizationHandle` for each
   original authored payload and accepted replacement, explicitly scoped so
   content deduplication does not imply behavioral equivalence, portability, or
   launch authority. Reusable domains contain dependency-minimal compiler
   projections over only the reader/expander/import dependencies, typed lexical
   interface, and resolved free bindings actually used by the subject.
   Unprovable projections are `OCCURRENCE_ONLY`, not ambient-environment hashes.
6. Separate content-addressed inert-payload and immutable-variant registry
   records/handles with resolution, rehash, retention, and revocation checks.
7. Source-map and reviewable-patch projection from certified variants.
8. One public but explicitly experimental read/propose/certify/register API
   suitable for later SDK/CLI exposure, with no pre-disposition stability
   promise.
9. One non-evolution client, such as a certified refactoring preview, using the
   same manifest, policy, certifier, and variant registry without importing
   candidate, genome, fitness, or controller types. It is a repo-scoped
   experimental interim adopter, not a supported external stability surface.

### Exclusions

- no child trials;
- no candidate or genome registry;
- no optimizer;
- no prompt or provider mutation;
- no runtime closures or public mutable AST;
- no claim that structurally similar subjects retain identity across changed
  bundles.

### Gate E1

The reviewed decision record chooses exactly one outcome:

- `PASS_E1`: all pass conditions below hold; E2 may be activated separately;
- `REVISE_E1`: the record names a bounded design or implementation correction,
  and E2 remains ineligible until an amended E1 plan is explicitly accepted and
  the gate reruns; or
- `STOP_E1`: the neutral certification substrate is not justified or cannot
  preserve the architecture; E2 and the feature tranches remain unactivated.

`PASS_E1` requires:

- the non-evolution client is useful without semantic aliases for evolution;
- all variants are produced by the ordinary compiler path;
- stale bundle, manifest, subject, and structural preimages fail closed;
- subject identity is exact within one base bundle/compiler contract;
- original and replacement realization identity is inert, domain-scoped,
  compiler-derived, backed by a rehashable payload artifact, and every insertion
  still traverses whole-bundle certification;
- changing a reader/expander/import dependency or resolved free binding
  actually used to interpret the subject changes its reusable realization
  domain, while changing an unused import, unused binding, or unrelated
  environment value does not; if the compiler cannot prove the closed
  dependency-minimal projection, it emits an `OCCURRENCE_ONLY` realization,
  never an ambient-environment hash, and E3F may not archive, transfer, or
  independently select it;
- common operation metadata retains nominal kind, effect, and durability
  differences;
- ordinary workflows that do not request manifests or variants pay no
  persistent or tracing overhead; and
- capability/documentation routing marks every landed E1 surface
  experimental/non-promoted, and the evidence bundle records all known interim
  adopters without promising compatibility; and
- independent design/specification and code-quality review approve the slice.

If stable identity requires a mutable public AST or guessed cross-bundle node
correspondence, `PASS_E1` is forbidden; choose `REVISE_E1` or `STOP_E1`.
Prompt-semantic, per-attempt-composition, provider-policy, and prompt-gene role
negatives remain owned by the E4P/E4E evidence lane as applicable. E1 records
that unavailable later lane as `not_applicable`; it does not mock future
behavior.

## E2 — Neutral Execution And Trial Substrate

### Question

Can a registered variant be bound to one exact, policy-narrowed execution
envelope and launched through a crash-durable new-run path that both external
and future `.orc` clients can use?

### Deliverables

1. Neutral `ExecutionAdmissionPolicy`, complete `ExecutionInstanceSpec`, and
   content-addressed `RegisteredExecutionInstance`.
2. Exact entrypoint, runtime binding, environment, evaluator, workspace,
   observation, budget, and frozen-kernel identity in admission evidence. The
   schema includes a canonical complete empty provider-invocation map and
   canonical complete empty provider-call attempt ledger so E4P can enable
   total occurrence-keyed bindings and non-empty reachability evidence without
   inventing association-losing prompt/provider/context ID sets or relabeling
   existing pure E2 identities.
3. Registry resolution and rehash before launch.
4. One runtime-native certified-workflow child-trial effect that accepts only a
   registered execution-instance handle.
5. Durable request/attempt allocation, request-to-run linkage, crash
   reconciliation, retry semantics, and no-duplicate-launch evidence. The
   design starts from existing `RunState`/`StateManager` atomic durable
   mutation and root-owned `ProviderAttemptScope` allocation patterns, then
   records `EXTEND` or `NEW` for the missing
   `TrialRequestId -> TrialAttemptId -> child RunId` transaction. Existing
   `_CallFrameStateManager` state retains the parent run and is not evidence of
   an independently registered child run.
6. Typed trial evidence and explicit separation of execution-instance
   admission rejection, trial failure, and substrate corruption. Candidate
   rejection begins in E3. Experiment assignment remains a separate E3
   registry keyed by the durable trial request so neutral E2 evidence does not
   import arm or optimizer vocabulary.
7. A public but explicitly experimental SDK and CLI using the same
   certification, registration, and trial services intended for `.orc`; no
   private compiler shortcut and no pre-disposition stability promise.
8. A workspace/output contract and capability ceiling that state explicitly
   that the tranche does not sandbox arbitrary generated code.
9. A non-evolution regression or what-if runner using the same execution
   registration and trial path. Like the SDK/CLI, it is a repo-scoped
   experimental interim adopter rather than a supported external stability
   surface.

### Exclusions

- no unregistered bundle or arbitrary path launch;
- no imported parent checkpoint or run identity;
- no in-process bundle replacement;
- no candidate/genome/fitness semantics in the neutral APIs;
- no provider, command, filesystem, network, or process capability in the
  first accepted harness;
- no non-empty prompt/provider binding or provider projection; E4P owns that
  versioned capability extension while E2 owns only the canonical empty field;
- no “sandboxed” security claim.

### Gate E2

The reviewed decision record chooses exactly one outcome:

- `PASS_E2`: all pass conditions below hold; E2O, E3, or E4P may be activated
  separately according to their own prerequisites;
- `REVISE_E2`: the record names a bounded correction, and every downstream
  tranche remains ineligible until an amended E2 plan is explicitly accepted
  and the gate reruns; or
- `STOP_E2`: the neutral trial substrate is not justified or cannot preserve
  immutable generation/run boundaries; E2O-E5 remain unactivated.

`PASS_E2` requires:

- the pure-expression child variant runs through the real compiler, registry,
  runtime child-run, and typed evidence paths;
- a forced crash after child completion but before acknowledgement reconciles
  without a duplicate launch;
- forged, revoked, stale, mismatched, widened, and unauthorized-entrypoint
  handles fail before execution;
- the SDK/CLI and the non-evolution client have no privileged backdoor;
- the parent source, run, and checkpoints remain unchanged;
- the first pure profile proves an empty compiler-derived provider-call domain,
  emits the unique complete empty binding map and call-attempt ledger, and does
  not require E4P;
- ordinary non-trial runs pay no controller or trial-registry overhead; and
- capability/documentation routing marks every landed E2 surface
  experimental/non-promoted, and the evidence bundle records all known interim
  adopters without promising compatibility; and
- focused, integration, end-to-end, broad-baseline, specification, and quality
  gates pass with fresh evidence.

If useful trials require hot replacement or importing parent execution state,
`PASS_E2` is forbidden; choose `REVISE_E2` or `STOP_E2` rather than weakening
immutable generation boundaries.

## E2O — Optional Contextual Subject Observation And Aggregation

### Question

If E3 readiness or a later E3F hypothesis requires more than black-box
whole-candidate evidence, can the platform record and compose bounded
call-site/context-qualified subject evidence without embedding archive,
selection, or fitness policy in the compiler/runtime?

E2O is omitted by default. It is a neutral E1/E2 substrate extension with its
own compiler, runtime, observability, evaluation/aggregation,
security/redaction, and performance owners. Core E3 remains valid using only
whole-candidate evidence. E3F is not valid without `PASS_E2O`.

After `PASS_E2` and before adding either E2O or E3 to a selector, the initial
E3-readiness record over the fixed E0 benchmark and E2 trial evidence chooses
exactly one route:

- `BLACK_BOX_SUFFICIENT`: make E3 eligible for a separate activation without
  E2O;
- `OBSERVATION_EXTENSION_REQUIRED`: make E2O eligible for a separate
  activation and keep E3 ineligible until `PASS_E2O`; or
- `STOP_E3_HYPOTHESIS`: make neither E2O nor E3 eligible and record a terminal
  stopped feature route.

If E3 later retains code evolution and records
`PROCEED_TO_FRAGMENT_HYPOTHESIS`, a separate E3F observation-route record
chooses `USE_PASSED_E2O`, `OBSERVATION_EXTENSION_REQUIRED`, or
`STOP_E3F_OBSERVATION_UNAVAILABLE`. The first makes E3F eligible for separate
activation, the second makes E2O eligible even if initial E3 readiness chose
`BLACK_BOX_SUFFICIENT`, and the third is terminal for E3F. `PASS_E2O` is an
E3F prerequisite; it does not cause the E3 experiment to be rerun or add an
E3F row. These are routing decisions, not a dependency cycle.

### Deliverables

1. An opt-in compiler-instrumented trace overlay that extends E1 subject
   manifests/certification with static `CallSiteId` identity and compiler-proved
   call-site correspondence, then binds a per-variant
   `SubjectInstrumentationMap` into E2 execution/trial identity.
2. A finite `describe` view bounded by subject depth and subject/call-site
   count.
3. `SubjectVisitObservation` keyed by exact execution instance, trial
   contract/request/attempt, observation contract, manifest, subject, optional
   call site, compiler-derived `SubjectRealizationId`, frozen context
   classifier/class, instrumentation point/replay scope, and replay-stable
   attempt-local `VisitId`, with idempotent exact re-emission and fail-closed
   conflicting content.
4. `ContextClassifierContract` over a declared typed/redacted feature schema,
   with a closed domain, explicit `UNKNOWN`, missing-feature policy, and
   cardinality bound. It distinguishes pre-treatment strata eligible for
   comparison/selection weighting from candidate-produced post-outcome
   diagnostics. No candidate-chosen labels or unbounded call-stack key.
5. `SubjectEvaluationContract` covering typed metrics, visit and trial
   reducers, versioned typed parent composition contracts, context-risk
   projection, sampling, coverage, missingness, uncertainty, and work budget.
   The first slice admits only `RECOMPUTE_AT_PARENT` and `LOCAL_ONLY`.
6. A typed content-addressed `SubjectObservationLedger` for each attempt and
   `SubjectAssessment` whose identity includes the exact realization,
   canonical request→authorized-attempt→trial-evidence→raw-ledger tuples,
   complete closed-domain context cells, composition provenance, completeness,
   coverage, uncertainty, and aggregate projection.
7. Hierarchical visit → attempt → authorized trial request → context-class
   aggregation. Loop visit count remains a separate metric rather than implicit
   sample or context weight; replaced retry attempts are selected out before
   cross-trial reduction.
8. Authority-preserving per-context vectors. Any weighted mean, worst-case,
   quantile/CVaR, lexicographic, or Pareto projection is frozen in the contract;
   observed frequency and policy importance remain separate. Truncated or
   incomplete evidence is quality-ineligible; only a frozen
   outcome-independent declared sample may be sample-complete.
9. Default payloads limited to type, shape, digest, redaction class, timing, and
   declared metrics, with explicit policy for any raw value.
10. Crash/resume rebuilding of derived aggregates from authoritative visit and
   trial evidence under exact contract IDs.
11. A bounded public worklist/traversal contract usable only between immutable
    trial generations.
12. One non-evolution diagnostics or performance-analysis client using the same
    visit, classifier, assessment, and aggregation contracts.

The neutral E2O service emits evidence and aggregates. It never archives or
selects a realization, assigns candidate fitness, constructs a
`LocusBackgroundId`, or declares a winner. E3/E3F may use an exact
`SubjectEvaluationContractId` as frozen search input only through their own
admission and feature-owned policy.

This is “recursive” adjudication as finite tree processing, not recursive
runtime `eval`, recursive procedure calls, durable checkpoints for every
expression, or a provider traversing mutable compiler ASTs. Instrumentation is
opt-in, sampled/bounded, and absent from ordinary workflow execution.

### Gate E2O

The reviewed decision record chooses exactly one outcome:

- `PASS_E2O`: exact instrumentation/visit/ledger/assessment identity,
  retry-safe canonical evidence tuples, explicit enabled metric composition,
  retained closed-domain context cells, truncation fail-closed behavior, the
  non-evolution client, redaction, cardinality/coverage bounds, and acceptable
  overhead all pass; the requesting E3 or E3F route may proceed;
- `REVISE_E2O`: the record names a bounded correction and the requesting route
  remains ineligible until the amended gate passes; or
- `OMIT_E2O`: observation is unnecessary, too costly, too leaky, too sparse, or
  too ambiguous. Before E3 this requires a new readiness record choosing
  `BLACK_BOX_SUFFICIENT` or `STOP_E3_HYPOTHESIS`; after retained E3 it leaves
  the historical `PROCEED_TO_FRAGMENT_HYPOTHESIS` decision intact, requires a
  superseding E3F observation-route record with
  `STOP_E3F_OBSERVATION_UNAVAILABLE`, and keeps E3F unactivated while
  candidate-only evolution remains retained.

`PASS_E2O` is forbidden if instrumentation dominates trial cost, leaks
protected values, collapses material context heterogeneity, permits visit or
retry multiplication to change weight, lacks a valid parent metric algebra, or
cannot distinguish neutral assessment from causal/selection authority.

## E3 — Candidate-Only Code Evolution

### Question

Given a neutral certified-variant and trial substrate, do a bounded optimizer
whose selectable/reproductive unit is the whole candidate, and a Workflow Lisp
controller, offer value that simpler strategies and an external controller do
not?

### E3A: Trusted Evolution Admission

Add:

- compiler-owned code loci referencing neutral rewrite policies;
- bounded genome schemas containing code genes only;
- trusted genome and candidate admission;
- exact candidate-to-execution-instance registration;
- content identity distinct from lineage/population occurrence;
- content-addressed experiment and arm contracts for the fixed baseline and
  code-only comparison arms, including exact mutation masks, complete fixed
  assignment complements, and a closed `ArmExecutionEnvelopeContract` that
  classifies every registered execution-instance field as fixed or as a
  code-locus-derived variant/instrumentation field, plus
  input/seed/randomization/pairing policies and budget-equivalence policy;
- a content-addressed `SearchControllerPolicyContract` covering initialization,
  proposal scheduling, local guidance, fitness/uncertainty aggregation,
  repetition and adaptive allocation, diversity, parent/survivor selection,
  failure handling, stopping, RNG derivation, and checkpoint semantics;
- a trusted append-only controller-decision registry whose content-addressed
  records bind every evidence-affecting transition to its exact experiment,
  arm, policy, predecessor checkpoint, input snapshot, realized randomness,
  output, implementation provenance, conformance evidence, and completed
  metered controller-transition work;
- an explicit controller-policy comparison mode: the same policy and typed
  arm-space adapter for a gene-space ablation, or a complete declared per-arm
  policy map for an optimizer/controller treatment;
- a content-addressed `ExperimentInformationIsolationContract` in
  `ISOLATED_ARMS` mode, with every common grammar, seed, dataset partition,
  static guide, and operator prior registered and frozen under one exact
  registry head/count before arm work;
- typed information references and arm-scoped artifact visibility so every
  later controller decision, proposal, parent, search output, trial/assessment
  input, and fragment checkpoint resolves through the same arm, while the
  shared baseline receives a separate binding in each arm;
- trusted candidate-to-arm binding and pre-launch trial-to-arm assignment,
  with an atomic unique assignment per durable `TrialRequestId`, rather than
  controller/report arm labels;
- pre-work, unique-by-request arm allocation for every controller transition,
  proposal/provider/compiler/certification/candidate-admission operation,
  fitness/uncertainty or subject aggregation, evidence pairing/validation,
  matched comparison, and fragment-archive query/update, with
  work-kind-specific contract/bounds validation and exact
  success/failure/resource/cost outcomes;
  only the closed initialization/common-freeze cases use design-bootstrap
  authority, every other assignment is authorized by a causally prior
  controller decision, shared feature work receives its precommitted per-arm
  charge, physical artifact/cache deduplication remains hidden from search
  policy, and each arm retains its normalized logical operation charge;
- full referential-equality and information-provenance validation across
  design, admission, baseline, arm/envelope, frozen common input, same-arm
  parent/input, search-work assignment/output, candidate, trial
  contract/request, assignment, and ledger
  records, plus one atomic common analysis-freeze record and trusted
  content-addressed arm ledgers whose frozen controller-decision sequence and
  feature-work/trial domains contain every policy decision, assignment,
  rejected/failed work item, controller/provider/compiler/evaluator/
  aggregation/pairing/archive charge, and selected terminal trial evidence.
  The initial freeze rule is precommitted and
  outcome-independent. Sequential stopping remains ineligible until a later
  design supplies a typed complete global-look/signal ledger; complete but
  policy-nonconformant ledgers remain ineligible;
- fixed evaluator, observation, environment, workspace, budget, kernel, and
  single trial-entrypoint contracts; and
- rejection of every prompt, provider-policy, context-policy, or effectful gene.

The evolution layer validates and narrows neutral policy; it does not compile
code itself and does not create a second trial path.
E3A binds and audits a selected controller policy but does not choose its
behavior. E3B owns and versions the feature-level optimizer/controller
semantics; the E3A registry enforces those declared semantics for either
implementation.
The initial E3 comparison is arm-isolated: input/seed pairing does not authorize
one arm to consume another arm's candidates, scores, assessments, search
outputs, controller state, or operator observations. Any later cooperative
cross-arm search requires an umbrella-design and roadmap amendment with
directed transfer authority, receiving/shared-cost accounting, and an
interference-qualified claim.
E3 may use E2O subject assessments to choose which locus to mutate, if E2O was
required and passed. In that route, evolution admission binds the exact
`SubjectEvaluationContractId` values as post-trial search-guidance policy
without adding a `FragmentSearchContract`; black-box E3 binds an empty vector.
Neither route may maintain an independently selectable fragment population,
transfer a realization from a discarded candidate, or assign fragment fitness.
Those behaviors belong only to E3F.

### E3B: Replaceable Controllers

Before controller implementation, a reviewed feasibility record chooses exactly
one outcome:

- `ORC_CONTROLLER_FEASIBLE`: the current language can express the controller
  without runtime closures, hidden dynamic code, or compiler-private authority,
  so implement the bounded optimizer in both forms; or
- `ORC_CONTROLLER_INFEASIBLE`: the record names the exact missing capability
  and why adding it is outside this tranche or violates its boundaries; run the
  external controller only, and force `KEEP_CONTROLLER_EXTERNAL` if code
  evolution is retained.

Under `ORC_CONTROLLER_FEASIBLE`, implement one bounded optimizer twice:

1. an external controller using only the public SDK/CLI; and
2. a `.orc` controller using the same public substrate.

The two controllers receive identical seeds, policies, budgets, invalid
proposals, crash injections, and deterministic suites. Content-addressed
candidates, controller-decision records, and terminal trial sets should match
under the same `SearchControllerPolicyId`. The implementation identity is
provenance only. Any semantic difference must be rerun as a precommitted
`DECLARED_CONTROLLER_POLICY_TREATMENT`; it cannot be excused as an
implementation detail.

The `.orc` controller may use ordinary typed procedures, workflows, loops,
records, and child-trial effects. It does not receive AST values, dynamic
callables, a magic current-bundle reference, or compiler-private authority.

### Required Comparisons

Report separately:

- substrate versus the E0 ad hoc coordination path;
- external versus `.orc` control over the same substrate when
  `ORC_CONTROLLER_FEASIBLE`, or the reviewed feasibility boundary and external
  result when `ORC_CONTROLLER_INFEASIBLE`;
- the chosen optimizer versus random and a simple search baseline under
  `DECLARED_CONTROLLER_POLICY_TREATMENT`, with the same gene space, execution
  envelope, budgets, and datasets so the declared controller policy is the
  treatment; and
- human-authored baseline versus selected candidate on validation and sealed
  promotion holdout.

Charge controller transitions, proposal and provider work, compilation,
certification, candidate admission, evaluator and subject aggregation, evidence
pairing and matched comparison, archive query/update, trials, storage, wall
time, expression-observation overhead if enabled, and operator attention.
System-observable feature and trial work comes from the complete common-freeze
arm ledgers, including failed and shared work under the precommitted per-arm
allocation rule; externally supplied/operator work follows the precommitted
accounting policy and is explicitly qualified when it cannot be measured
directly.

### Compelling Example Deliverables

E3 must produce code-first, reproducible side-by-sides rather than only an
architecture report:

1. **Variant creation:** the E0 source-rewrite/identity/compile/ledger code
   beside the E1-E2 public SDK call sequence, with identical behavior and
   failure cases.
2. **Controller:** external controller beside `.orc` controller for the same
   experiment when feasible. If infeasible, show the external controller beside
   the smallest unsupported/rejected `.orc` sketch and the feasibility
   diagnostic; do not present the sketch as runnable.
3. **Behavior:** direct authored expression beside the promoted candidate,
   plus failing examples showing type, effect, stale-preimage, and forged-handle
   rejection.
4. **Recovery:** a live or deterministic crash-after-launch demonstration
   showing one child run, one reconciled attempt, and no duplicate evaluation.
5. **Experimental authority:** a valid fixed-baseline/code-only assignment
   beside rejected cases that mutate outside the arm mask, alter a fixed
   complement, use individually valid but contradictory authority links,
   perform controller/search/provider/compiler/evaluator/pairing/archive work
   before arm allocation, assign/reassign a trial after launch, bind one
   request to two arms, omit a failed feature-work or trial assignment from the
   arm ledger, use different analysis cutoffs across arms, hide a different
   scheduling/selection/stopping policy in one arm, omit or forge a controller
   decision, import another arm's parent/evidence/search result, backdate it as
   a common prior, or claim equal budget from unequal charged work.

Line counts may be reported but are not the verdict. The comparison must include
identity, crash recovery, audit evidence, and maintenance burden that would
otherwise be hidden in helper code.

The behavior side-by-side must start from the retained migration-parity
target-loading, report, Markdown/index, gate, and CLI core. Before relying on
that path, E3 must demonstrate a minimal non-YAML comparison fixture or extract
a neutral comparison core; otherwise its reuse inventory must justify and
retire the divergent implementation.

### Gate E3

The reviewer first chooses one evidence outcome:

- `E3_EVIDENCE_ACCEPTED`: the required comparisons are complete and valid,
  trusted arm/candidate/trial assignment rejects forged labels and
  out-of-mask changes, the full authority chain has referential equality,
  controller semantics resolve from the precommitted comparison mode and
  policy contracts, every frozen controller-decision stream is complete and
  conformant and backed by terminal metered work, every controller,
  aggregation/evaluation, pairing/comparison, and archive operation is
  preassigned and charged (including failed and shared work), every non-common
  information input and parent has complete same-arm provenance under
  `ISOLATED_ARMS`, and budget/randomization authority resolves from the
  precommitted experiment design plus complete frozen feature-work-and-trial
  arm ledgers, so the dispositions below may be selected; or
- `REVISE_E3_EXPERIMENT`: the record names a bounded experimental correction,
  no E3 feature is promoted, and E3F/E4E remain ineligible until an amended E3
  plan is explicitly accepted and rerun; or
- `STOP_E3_UNEXECUTABLE_OR_INVALID`: trusted admission/controller execution
  cannot be implemented within the architecture, or no valid evidence or
  bounded correction is possible; this implies `NO_CONTROLLER_FEATURE`,
  `STOP_EVOLUTION_FEATURE`, and `STOP_AT_CANDIDATE_ONLY`, leaves E3F/E4E
  ineligible under the ordinary route, and records either
  `RETAIN_SUBSTRATE` or
  `RETIRE_EXPERIMENTAL_SUBSTRATE` from the independent E0-E2 substrate
  evidence.

With `E3_EVIDENCE_ACCEPTED`, the decision record chooses all four
dispositions:

**Substrate disposition**

- `RETAIN_SUBSTRATE`: neutral non-evolution and coordination value is real; or
- `RETIRE_EXPERIMENTAL_SUBSTRATE`: its complexity exceeds its demonstrated
  value, the accepted reuse/adopter inventory proves that no retained dependent
  use or compatibility commitment prevents removal, every retained E2O/E4P
  dependency is dispositioned, and the decision authorizes and requires E3R.
  The decision record alone is not retirement evidence or program completion.

**Controller disposition**

- `ADOPT_ORC_CONTROLLER`: `.orc` improves typed recovery, auditability, or
  integration at acceptable complexity;
- `KEEP_CONTROLLER_EXTERNAL`: the public substrate/controller is useful but
  `.orc` is infeasible within scope or adds no material value; or
- `NO_CONTROLLER_FEATURE`: neither controller warrants a supported feature.

**Optimizer disposition**

- `RETAIN_CODE_EVOLUTION_AND_PROCEED_TO_PROMPT_HYPOTHESIS`: adaptive search
  beats named simple baselines with gains surviving validation, sealed holdout,
  and independent rerun, and a named prompt-search hypothesis is justified;
- `RETAIN_CODE_EVOLUTION_STOP_BEFORE_PROMPT`: code-only search is worth
  retaining, but prompt evolution is not justified; or
- `STOP_EVOLUTION_FEATURE`: adaptive search does not justify a supported
  evolution feature.

**Fragment-search disposition**

- `PROCEED_TO_FRAGMENT_HYPOTHESIS`: candidate-only code evolution is retained,
  a named benchmark contains plausible reusable building blocks, and a
  precommitted E3F comparison could distinguish independent fragment selection
  from candidate-only locus guidance; or
- `STOP_AT_CANDIDATE_ONLY`: no valid fragment-search hypothesis justifies the
  additional observation, context/background, archive, and reproduction
  machinery.

The dispositions answer separate questions, but only these combinations are
valid:

- `RETIRE_EXPERIMENTAL_SUBSTRATE` requires `NO_CONTROLLER_FEATURE` and
  `STOP_EVOLUTION_FEATURE`, and is invalid while a retained E2O/E4P use or
  other recorded adopter still requires the substrate;
- `STOP_EVOLUTION_FEATURE` requires `NO_CONTROLLER_FEATURE`;
- either code-evolution retention outcome requires `RETAIN_SUBSTRATE` and
  exactly one of `ADOPT_ORC_CONTROLLER` or `KEEP_CONTROLLER_EXTERNAL`; and
- `STOP_EVOLUTION_FEATURE` requires `STOP_AT_CANDIDATE_ONLY`, while either
  code-evolution retention outcome must choose exactly one fragment-search
  disposition;
- `PROCEED_TO_FRAGMENT_HYPOTHESIS` authorizes only an E2O activation if needed
  and a later E3F activation after `PASS_E2O`; it does not adopt fragment search;
- `ADOPT_ORC_CONTROLLER` requires `ORC_CONTROLLER_FEASIBLE`, while
  `ORC_CONTROLLER_INFEASIBLE` forces `KEEP_CONTROLLER_EXTERNAL` for either
  code-evolution retention outcome; and
- absent an accepted umbrella-design and roadmap amendment, E4E eligibility
  requires `RETAIN_CODE_EVOLUTION_AND_PROCEED_TO_PROMPT_HYPOTHESIS` together
  with `RETAIN_SUBSTRATE` and a retained controller. An amendment may supply a
  prompt-specific hypothesis only under the exact alternative predecessor
  predicate defined in E4E Entry Conditions, or replace substrate/controller
  contracts only by defining and passing their acceptance gates; it does not
  make an otherwise invalid E3 disposition combination valid.

Thus neutral substrate may survive a stopped evolution feature, and a useful
evolution controller may remain external, but no controller or prompt feature
or fragment feature can outlive the substrate it uses. Replacing that substrate requires a new
umbrella-design and roadmap amendment, not an invalid disposition combination.

## E3R — Experimental Substrate Retirement

### Question

When Gate E3 rejects the experimental substrate, can the repo remove it rather
than retain an unused registry, SDK/CLI, trial effect, client, or compatibility
surface?

E3R is a deletion tranche, not a feature fallback. Its accepted plan must:

1. freeze an exact inventory of E1 manifests, certifiers, realization and
   variant registries, handles, API, and client; E2 execution registries,
   handles, child-trial effect, request/attempt/run state and services,
   SDK/CLI, and client; E3 evolution admission, experiment/arm/assignment
   registries, controller/library implementation, routes, tests, and fixtures;
   and every dependent E2O/E4P surface;
2. classify every inventory entry as `DELETE`,
   `RETAIN_SHARED_NON_E_SERIES`, or `HISTORICAL_EVIDENCE_ONLY`, with an owner
   and exact dependency justification;
3. run repository-reference, public-export, CLI, documentation, example,
   selector-route, supported run-root, and recorded-adopter scans before
   deletion, failing closed on tree races or unreadable supported state;
4. require zero undispositioned supported consumers, then delete source,
   registrations, tests, fixtures, examples, and documentation routes in
   dependency order;
5. retain history only through content-addressed evidence or version-control
   provenance, not a live compatibility archive, pointer, or unbounded shim;
6. disposition supported run state explicitly and record deletion tombstones
   or history bindings without making them live execution authority; and
7. update deleted E-series capability-matrix rows to `Retired`, leave any
   retained shared non-E-series row at its truthful status, and record fresh
   before/after reference scans, focused deletion checks, one end-to-end
   ordinary-workflow regression, the broad suite, and independent
   specification and quality review.

Before an E3R row can be added, the routing owner publishes a schema-validated
`RetirementPreflightEvidenceBundle` containing the frozen inventory digest,
per-entry owner and proposed disposition, supported run-root and adopter-scan
roots, reference/export/CLI/docs/example/route scan results, unresolved
consumer count, and reviewer approvals. The E3R activation contract requires
that bundle's identity and a zero unresolved-consumer count. The bundle is
structured evidence; any rendered preflight report is a view and cannot
authorize activation.

Gate E3R chooses exactly one outcome:

- `PASS_E3R`: live references and supported resumable consumers are absent or
  explicitly dispositioned, the deletion set and routing changes are complete,
  ordinary non-experimental workflows remain non-regressive, and the
  retirement evidence passes review; or
- `REVISE_SUBSTRATE_DISPOSITION`: a retained use, supported state consumer, or
  other concrete contract makes deletion unsafe. E3R stops before any
  irreversible deletion, and a new decision of the originating kind—Gate E3 or
  `EARLY_SUBSTRATE_DISPOSITION`—must supersede
  `RETIRE_EXPERIMENTAL_SUBSTRATE`; no partial deletion or compatibility shim is
  authorized. Unexpected supported adoption requires that superseding
  retention decision or an accepted breaking-transition amendment.

## E3F — Contextual Fragment Search

### Question

After candidate-only code evolution works, can a controller retain and select
an inert subject realization independently of the candidate that exposed it,
while preserving context/background heterogeneity and still requiring complete
certification and whole-candidate evaluation for every new placement?

E3F is an optional feature follow-on, not part of E3 acceptance and not a
prerequisite for prompt evolution. Failure or omission leaves retained
candidate-only evolution intact.

### Entry Conditions

Activation requires all of:

- E3 `E3_EVIDENCE_ACCEPTED`, `RETAIN_SUBSTRATE`, one retained controller, one
  code-evolution retention outcome, and
  `PROCEED_TO_FRAGMENT_HYPOTHESIS`;
- `PASS_E2O`, whether E2O ran before E3 or was activated afterward for this
  hypothesis;
- E1 compiler-derived `REUSABLE_WITHIN_DOMAIN` inert
  `SubjectRealizationId` records and resolvable, rehashable payload handles for
  original and replacement payloads under exact dependency-minimal realization
  domains; `OCCURRENCE_ONLY` records are ineligible;
- one precommitted deterministic pure benchmark with multiple loci,
  nontrivial linkage, reusable building blocks, and enough search space that
  candidate-only and fragment-aware strategies do not trivially enumerate it;
- fixed trial, evaluator, context classifier, aggregation, archive, selection,
  and budget contracts; and
- a separate activation decision and E3F plan. E3's hypothesis does not create
  a selector row by itself.

### Substrate Inputs Versus Feature Work

E3F consumes, but does not redefine, neutral substrate:

- E1 owns subject manifests, original/replacement realization
  domains/identities and inert payload registry, whole-bundle certification,
  and variant identity;
- E2 owns execution-instance/trial identity and retry reconciliation; and
- E2O owns the call-site manifest/correspondence extension, per-variant
  instrumentation maps, typed raw observation ledgers, visit identity, bounded
  context classifiers, `SubjectEvaluationContract`, typed/content-addressed
  `SubjectAssessment`, hierarchical aggregation, coverage, uncertainty,
  redaction, and the non-evolution client.

E3F owns only search semantics:

1. An exact experiment-arm-bound `FragmentSearchContract` binding eligible
   loci, exact E2O assessment contracts, background construction,
   matched-comparison eligibility, archive policy, realization
   selection/reproduction, coverage thresholds, uncertainty, evidence
   partitions, multiple comparisons, independent validation, adaptive reuse,
   and bounds.
2. A trusted `LocusExcludedExecutionProjection` and `LocusBackgroundId` over the
   admission and experiment/arm contracts, one target **code** locus, all other
   genome assignments, and explicit non-locus execution fields—not an
   `ExecutionInstanceId` with undocumented omissions. Every prompt gene and
   every canonical
   `ProviderInvocationBinding` remains in the projection; E3F does not select a
   prompt locus.
3. `MatchedTrialEvidencePair` and `SubjectSubstitutionComparison` only for
   trusted candidate pairs that differ at one locus under the same projection,
   binding exact request, authorized attempt, trial evidence, raw-ledger,
   assessment, trusted pre-launch experiment assignment,
   input/environment/seed/budget pairing, and compiler call-site
   correspondence identities. When provider calls exist, exact
   `PromptEnvironmentPairingEvidence` requires equality for each
   `PRE_TREATMENT_BACKGROUND` prompt/program/provider/context component and
   records code-influenced values or invocation bytes as mediators rather than
   matching on them. It resolves complete occurrence-domain
   `ProviderCallAttemptLedger` records so proved non-reachability,
   preparation failure, and missing evidence cannot collapse.
4. Content-addressed `FragmentArchiveEntry` and
   typed update event/checkpoint records plus an atomic lineage-head
   compare-and-set under the complete `FragmentSearchContractId`, referencing
   resolvable inert `SubjectRealizationHandle`, exact `SubjectAssessmentId`,
   and substitution-comparison identities.
5. Independent realization retention, robust/Pareto ranking, diversity, locus
   selection, and reproduction.
6. Idempotent controller resume for the fragment archive and pending
   comparisons from exact predecessor checkpoints without double-counting trial
   attempts, accepting a stale lineage head, exceeding adaptive-use budgets, or
   changing policy IDs.

The archive may retain a realization from a losing candidate when a local typed
oracle, valid matched substitutions, or explicit diversity policy supports that
decision. It must keep call-site, pre-treatment context class, surrounding
background, coverage, uncertainty, evaluator, and aggregation cells. It may
not assign one context-free intrinsic fitness, condition selection on
candidate-produced post-outcome classes, or treat an unmatched multi-locus
candidate as causal evidence.

The pinned pure E3F benchmark proves empty compiler-derived call domains and
uses the unique `NO_PROVIDER_INVOCATIONS` prompt-pairing result over complete
empty binding maps and attempt ledgers. This does not make E4P an E3F
prerequisite. If a later E3F amendment admits a provider-call occurrence, E4P
identity and complete ledgers are required; an omitted event, preparation
failure mislabeled as not reached, changed non-target prompt gene, or swap of
prompt/provider/context instances between call occurrences rejects pairing
with `SUBSTITUTION_BACKGROUND_MISMATCH` or
`PROMPT_PAIRING_UNCONTROLLED_MISMATCH`.

An archive entry remains inert. Selecting it creates a `RewriteProposal` for an
exact current subject after the inert handle and payload artifact are resolved
and rehashed. The normal certifier must parse, type/proof/effect check, rebuild
the whole bundle, emit a new registered variant, and admit a complete new
candidate/execution instance before any trial. E3F adds no runtime `eval`, hot
swap, code value, fragment launcher, checkpoint import, or context-specific
runtime dispatch. Any later call-site specialization is a separate
generation-time rewrite profile and is outside this tranche.

Only search/training evidence updates the archive. Independent validation tests
a frozen transfer decision; sealed promotion-holdout observations are reported
only after candidate/archive/analysis freeze and never enter fragment
selection, pairing, archive state, or policy tuning.

### Required Comparisons

Run equal-cost, equal-seed arms over the same mutation grammar and suites:

1. a black-box candidate-only baseline with no E2O search guidance, rerun under
   the E3F pinned benchmark even if the retained E3 route used E2O;
2. candidate-only search binding E2O assessments only for locus priority,
   proving the value of observation without independent fragment selection;
3. independent fragment retention using local typed assessments; and
4. independent fragment retention using local assessments plus verified
   context/background substitution history.

Encode these as a precommitted
`DECLARED_CONTROLLER_POLICY_TREATMENT`: each arm's complete controller policy
is explicit, while gene space, execution envelope, fitness contract, datasets,
budgets, and all policy fields outside the named locus-guidance/archive/
selection treatment remain fixed. A fragment-aware win is therefore a result
for the declared search policy, not evidence that its hidden scheduler or
stopping rule was more favorable.

All four arms remain `ISOLATED_ARMS`. They may start from the same frozen
population seeds and grammar, but each arm builds its own assessments, archive,
controller state, parents, and search outputs. A fragment-aware archive cannot
guide either candidate-only baseline, and one fragment-aware arm cannot receive
the other arm's retained realization. Matching content does not erase source-arm
provenance or discovery cost.

When an arm lacks enough matched comparisons or coverage, report that
explicitly; do not backfill a scalar. Charge tracing, storage, aggregation,
pairing trials, archive maintenance, recompilation, whole-candidate trials,
wall time, and operator attention through the same policy-linked metered
assignments and complete common-freeze controller-decision/feature-work/trial
ledgers introduced in E3. In particular, every subject aggregation, matched
comparison, archive query/update, and selection/controller transition has a
prior work assignment, terminal outcome, resource charge, and same-arm output
provenance.

Report at least:

- best-so-far and area under best-so-far versus total trial and cost budget;
- validation, sealed holdout, and independent rerun outcomes;
- candidate-only versus fragment-aware sample efficiency;
- archive retention, retrieval, successful-transfer, failed-transfer, and
  duplicate rates;
- per-context and worst-context outcomes, background heterogeneity, coverage,
  uncertainty, unknown-class rate, and cardinality;
- the frequency with which a realization retained from a losing candidate
  later improves a separately certified parent; and
- all overhead needed to preserve raw-ledger, assessment, pairing, and archive
  identity.

### Compelling Example Deliverables

Show code-first, reproducible side by side:

1. candidate-only survivor/reproduction code beside fragment-aware
   survivor-plus-archive reproduction over the same controller;
2. a losing two-locus candidate whose locally valid fragment is retained,
   inserted alone into a different same-arm parent, recertified as a complete
   bundle, and either accepted or rejected by new whole-candidate evidence;
3. one realization's separate call-site/context/background cells beside the
   incorrect naïve scalar summary, with a case where the scalar would choose
   the wrong realization;
4. a valid matched single-locus substitution beside an unmatched multi-locus
   pair rejected with `SUBSTITUTION_BACKGROUND_MISMATCH`; and
5. the public contract path beside the manual external bookkeeping needed for
   exact realization, raw-ledger, retry, classifier, assessment, background,
   pairing, and recertification identity.

Line count alone is not evidence. The example is compelling only if the
fragment-aware arm improves a meaningful outcome or sample efficiency after all
costs, not merely because its API is shorter.

### Gate E3F

The reviewed decision record chooses exactly one outcome:

- `ADOPT_CONTEXTUAL_FRAGMENT_SEARCH`, only if:
  - at least one nontrivial building block transfers from a losing candidate to
    a separately certified parent under adequate local or matched evidence;
  - the fragment-aware arm beats candidate-only and locus-guided baselines on a
    precommitted effectiveness or sample-efficiency criterion after full cost
    accounting;
  - gains survive validation, sealed holdout, and independent rerun;
  - the declared fragment-search policy treatment has complete, conformant
    controller-decision streams and differs from each baseline only in the
    precommitted feature-policy fields;
  - every controller, aggregation, pairing/comparison, and archive operation,
    including failures, appears in the complete arm work ledger and all shared
    feature overhead is allocated by the precommitted per-arm cost policy;
  - every common input was frozen before arm work, and every later parent,
    assessment, archive checkpoint, and search input has complete same-arm
    provenance with no operator-mediated cross-arm leakage;
  - context/background heterogeneity, unknowns, coverage, and uncertainty
    remain visible and bounded;
  - retry/replay, archive resume, assessment identity, and matched-pair
    eligibility pass fault injection;
  - occurrence-only realizations cannot enter the archive; the pure benchmark
    emits the unique complete-empty `NO_PROVIDER_INVOCATIONS` pairing result,
    and any later provider-bearing amendment rejects incomplete ledgers,
    false not-reached claims, or changed/swapped non-target invocation
    bindings;
  - multiplicity/adaptive-use limits stop selection, inert payload handles
    resolve and rehash, and promotion-holdout evidence cannot enter the archive;
    and
  - no archive record can execute, promote, or override whole-candidate
    fitness;
- `KEEP_CANDIDATE_ONLY`: fragment selection is ineffective, too costly, too
  sparse, too context-sensitive, too gameable, or unnecessary. Retain the E3
  outcome and retain E2O only if its independent neutral value warrants it; or
- `REVISE_E3F_EXPERIMENT`: the record names one bounded experimental or contract
  correction. E3 remains authoritative, no fragment feature is adopted, and a
  rerun requires an accepted amended E3F plan; or
- `STOP_E3F_UNEXECUTABLE_OR_INVALID`: fragment identity, evidence, archive
  resume, or full-recertification boundaries cannot be implemented safely, or
  no valid evidence and no bounded correction is possible. Candidate-only E3
  remains authoritative; E2O is retained only on its independent neutral value.

No E3F outcome unlocks E4E or E5. E3F cannot weaken, invalidate, or silently
change the retained E3 candidate-selection contract.

## E4P — Prompt Identity

### Question

Can prompt programs and their invocations be identified and reconstructed
honestly enough to help non-evolution clients, given provider drift and the
distinctions among lexical prompt bindings, fixed composition captures,
per-attempt inputs/dependencies, exact invocation bytes, and ambient provider
bindings?

### Deliverables

Prompt identity work may be proposed after E2 even if E3 is still running. Its
readiness record chooses `PROMPT_IDENTITY_USE_CASE_READY` only when its brief
names an independent non-evolution use case; otherwise it chooses
`DEFER_PROMPT_IDENTITY` and authorizes no row. The E4P row then owns its design,
design review, plan, and implementation rather than depending on a design it is
supposed to produce. It binds:

- a stable typed `PromptProgramInterfaceContract` and a resolvable,
  content-addressed `RegisteredPromptSemanticProgram` as the sole owner of
  dependency-minimal `SemanticProgramId`: used semantic IR/import/free-binding
  dependencies change identity, unused imports/bindings and formatting do not,
  and an unprovable projection is ineligible rather than ambient-hashed;
- the role-classification rule that puts an actual compiler-resolved prompt
  free binding in `SubjectRealizationDomainId`, but leaves unrelated captures,
  runtime inputs, and ambient provider state out of that fragment domain;
- content-addressed `PromptCompositionEnvironment` and
  `PromptProgramInstance` records, including protected fixed captures,
  declared runtime dependency contracts, resolve/rehash behavior, and canonical
  empty captures;
- content-addressed `ProviderPolicyInstance` and `ContextPolicyInstance`
  records with non-overlapping ownership and canonical empty protected
  capture/context artifacts, plus a total occurrence-keyed
  `ProviderInvocationBinding` map associating exactly one prompt program and
  provider/context policy with every compiler-derived provider-call
  occurrence; duplicate, missing, extra, or interface-incompatible entries
  fail admission;
- the concrete provider-invocation projection into E1's common operation
  metadata, retaining provider effect, transport, and invocation-durability
  semantics rather than treating it as a procedure;
- a versioned E2 execution/trial identity extension that enables non-empty
  structured per-call maps and complete call-attempt ledgers rather than
  independent ID sets and never relabels an already registered pure E2
  identity;
- a governed `PromptAttemptCompositionSnapshot` with resolvable protected
  artifacts for typed prompt inputs, runtime context inputs, attempt
  dependencies, exact invocation bytes, and transport bindings, distinct from
  fixed composition captures. It reuses the implemented immutable
  per-attempt provider-dependency snapshot only for its attempt-dependency
  component; typed prompt/context snapshots, exact invocation/transport
  artifacts, and the complete occurrence ledger remain E4P work. Digest-only
  records support equality, not reconstruction;
- exact `PromptAttemptIdentity` linking execution, trial request/attempt,
  provider-call occurrence/attempt, prompt-program/composition environment,
  provider/context policy instances, the governed attempt snapshot, provider
  contract, and session identity;
- a complete occurrence-domain `ProviderCallAttemptLedger` that distinguishes
  `NOT_REACHED`, `PREPARATION_FAILED`, later dispatch/terminal states, and
  `INCOMPLETE`, and is the sole authority for prompt-attempt association;
- provider/model/call-policy identity that is declared or attested, without
  claiming hidden remote state is reproducible;
- tool, workspace, session, and context policy;
- evaluator prompt identity outside the mutable genome.

E4P does not activate prompt mutation by itself.

### Gate E4P

The reviewed decision record chooses exactly one outcome:

- `RETAIN_PROMPT_IDENTITY`: exact local invocation reconstruction from
  resolved/rehashable governed artifacts, protected capture/attempt snapshot
  handling, role-correct identity changes, total per-call association
  integrity, complete reachability evidence, declared-drift detection,
  qualified remote-provider claims, and the non-evolution use case all pass.
  A used versus unused semantic dependency, referenced code-subject lexical
  prompt, fixed capture, runtime input, and transport/provider change must
  affect only their respective layers. A semantic prompt mutation that
  preserves the interface must not change provider-policy identity, while an
  interface change is rejected as outside the prompt-only profile. Swapped
  call bindings, a missing occurrence, a bare digest with no governed
  artifact, and attempts to relabel missing or preparation-failure evidence as
  `NOT_REACHED` must fail. E4E may use this substrate only if its other
  prerequisites also pass;
- `REVISE_E4P`: the record names a bounded correction, and E4E remains
  ineligible until an amended E4P plan is explicitly accepted and rerun; or
- `STOP_E4P`: prompt identity is not independently useful or safe enough to
  retain, and E4E remains unactivated.

## E4E — Bounded Prompt Evolution

### Question

Given retained prompt identity, neutral trial substrate, and a supported
controller, can prompt candidates be compared reproducibly enough to justify a
narrow prompt-search feature?

### Entry Conditions

Prompt genes require all of:

- `PASS_E2`;
- E4P `RETAIN_PROMPT_IDENTITY`;
- one active neutral substrate and one supported controller;
- exactly one prompt-hypothesis authorization:
  1. E3 selected
     `RETAIN_CODE_EVOLUTION_AND_PROCEED_TO_PROMPT_HYPOTHESIS`, together with
     `RETAIN_SUBSTRATE` and exactly one of `ADOPT_ORC_CONTROLLER` or
     `KEEP_CONTROLLER_EXTERNAL`; or
  2. an accepted umbrella-design and roadmap amendment supplies a
     prompt-specific hypothesis after an eligible terminal route that did not
     authorize one and
     explicitly retains the existing substrate/controller or defines
     replacement contracts and their acceptance gates;
- text-only/no-tool, mock, replay, or genuinely sandboxed providers;
- no session reuse in the first slice; and
- an E3-compatible content-addressed experiment design extended with
  prompt-only, code-only, and joint arm contracts, trusted candidate-arm
  bindings, pre-launch trial assignments, randomized input/seed scheduling,
  verified equal-budget policy, `COMMON_GENE_ABLATION_POLICY` with one exact
  controller policy and precommitted typed arm-space adapter across all three
  gene arms, `ISOLATED_ARMS` with frozen common pre-treatment inputs and
  same-arm parent/evidence/archive provenance, complete conformant
  controller-decision streams backed by complete metered feature work, and
  closed arm execution envelopes that classify every execution field rather
  than trusting an opaque projection.

The amendment branch substitutes only for E3's positive code-search/prompt-
hypothesis authorization. It does not waive `PASS_E2`, E4P
`RETAIN_PROMPT_IDENTITY`, an accepted active substrate/controller, or any E4E
safety or evidence condition. A replacement substrate or controller must pass
the amendment's named acceptance gate before E4E activation.

The selector predicate `ALTERNATIVE_PROMPT_HYPOTHESIS_ELIGIBLE` is true only
after one of these accepted, applied terminal records:

- Gate E3 `E3_EVIDENCE_ACCEPTED` with
  `RETAIN_CODE_EVOLUTION_STOP_BEFORE_PROMPT` and `RETAIN_SUBSTRATE`;
- Gate E3 `E3_EVIDENCE_ACCEPTED` with `STOP_EVOLUTION_FEATURE` and
  `RETAIN_SUBSTRATE`;
- Gate E3 `STOP_E3_UNEXECUTABLE_OR_INVALID` with `RETAIN_SUBSTRATE`; or
- E3 readiness `STOP_E3_HYPOTHESIS` followed by
  `EARLY_SUBSTRATE_DISPOSITION` selecting `RETAIN_SUBSTRATE`.

It is false for an open or CAS-unapplied record,
`REVISE_E3_EXPERIMENT`, `RETIRE_EXPERIMENTAL_SUBSTRATE`, and the ordinary
positive prompt-hypothesis outcome. The two amendments must name the exact
eligible predecessor record and, where no controller was retained, define and
pass a replacement-controller gate.

Trials record prompt and code identities separately, but report fitness at
whole-candidate and experimental-arm level. Joint improvement is not causal
proof for either gene. The selected prompt assignment is a
whole-candidate/arm treatment, not an E3F fragment locus. In the prompt-only
arm every code assignment, non-target prompt, provider policy, context policy,
and non-gene execution field remains fixed to the registered baseline; the
code-only and first joint masks follow their own exact complements. Exact
invocation bytes or dependency values produced downstream of the treatment are
recorded as mediators/outcomes and are not automatically reclassified as
pre-treatment background. Arm membership and budget claims resolve from
trusted records, never controller/report labels. Prompt-versus-code attribution
is ineligible if an arm receives different fitness, scheduling, repetition,
parent/survivor selection, or stopping semantics. Only the declared masks,
allowed mutation operators, and typed arm-space adapter may differ, and their
asymmetries qualify the result. The prompt-only arm may not consume a prompt,
parent, score, provider proposal, or controller observation discovered in the
joint or code-only arm; the symmetric rule applies to every arm.

### Compelling Example Deliverables

Show side by side:

- a fixed hand-authored prompt and a selected prompt candidate;
- exact dependency-minimal semantic-program, protected composition-capture,
  governed attempt-composition, complete call-ledger, and structured
  provider-invocation identities for each;
- content-addressed prompt-only, code-only, and joint mutation masks, fixed
  complements, candidate bindings, and pre-launch trial assignments using one
  trial substrate and one common controller policy, beside rejected
  forged-label, out-of-mask, hidden-policy, missing-decision, cross-arm-parent,
  and backdated-common-prior examples; and
- the same experiment with one declared drift injection that blocks comparison
  rather than silently mixing populations.

Report randomized contemporaneous arms and uncertainty for opaque provider
drift. A polished response sample is not effectiveness evidence.

### Gate E4E

The reviewed decision record chooses exactly one outcome:

- `ADOPT_BOUNDED_PROMPT_EVOLUTION`, only if:
  - exact candidate reproduction succeeds within the declared envelope;
  - the prompt-only arm varies only its declared prompt loci and fixes every
    code, non-target prompt, provider, context, and other execution field; the
    joint arm varies only its declared code-and-prompt mask and fixes its
    complete complement; and treatment-influenced invocation bytes are not
    used as matching strata;
  - every candidate and trial resolves to a precommitted arm binding and
    pre-launch assignment, forged prompt-only labels and out-of-mask changes
    fail, every arm resolves the exact common controller policy, every
    controller-decision stream is complete, conformant, and metered, every
    non-common parent and information input resolves through the same arm, every
    controller/evaluator/aggregation/pairing/archive operation and failure is
    charged, and the complete feature-work-and-trial arm ledgers satisfy the
    budget-equivalence and randomization policies;
  - protected prompt dependencies do not leak to untrusted candidates or
    normal observability;
  - declared drift blocks comparison;
  - prompt-only or joint gains survive validation, sealed holdout, independent
    rerun, and equal-cost baselines;
  - no tool-enabled or unrestricted provider is admitted; and
  - documentation explicitly qualifies opaque remote-provider
    reproducibility;
- `REVISE_E4E_EXPERIMENT`: the record names a bounded correction, no prompt
  feature is promoted, and a rerun requires an explicitly accepted amended
  plan; or
- `STOP_PROMPT_EVOLUTION`: the feature is not supported by valid effectiveness
  or safety evidence.

`REVISE_E4E_EXPERIMENT` and `STOP_PROMPT_EVOLUTION` leave independently useful
E4P identity intact. Every E4E outcome is terminal with respect to this
roadmap; none unlocks E5.

## E5 — Effectful Evolution

E5 is a horizon marker, not scheduled work.

It covers possible future mutation of provider bindings, prompt read sets,
procedures, workflow bodies, commands, filesystem behavior, or other effectful
loci. Typed input/output parity is not enough to make any of these safe.

Before an E5 roadmap amendment, a separate reviewed security program must
deliver:

- a real OS/process/network/filesystem isolation boundary;
- an ordered capability model with `UNKNOWN_OR_UNBOUNDED` failing closed;
- credential, controller, evaluator, canonical-source, and promotion-holdout
  separation;
- resource and provider-cost enforcement;
- bounded artifact egress and protected-input handling;
- termination and cleanup semantics;
- adversarial escape, confused-deputy, symlink/TOCTOU, exfiltration, fork-bomb,
  and denial-of-service tests; and
- an operational threat model specifying what remains trusted.

Only then may an amendment select one narrow effectful locus. The first
positive slice must still use immutable generation boundaries and exact
registered execution instances. Arbitrary self-modifying workflows, recursive
in-run `eval`, unrestricted tool-using prompt mutation, and mutation of the
evaluator or frozen trust kernel remain out of scope.

If the isolation boundary cannot prevent candidate access to controller,
evaluator, credentials, canonical source, or sealed holdout, E5 remains
deferred indefinitely.

## Cross-Tranche Evidence Contract

Every activated tranche publishes a reviewed evidence bundle containing:

- exact identities for every source, compiler, runtime, environment, policy,
  evaluator, and external contract that the tranche actually uses;
- task-local and integration commands with fresh output;
- negative or fault-injection outcomes within the tranche's authority;
- cost, wall-time, storage, and operator-effort accounting appropriate to the
  slice;
- claims supported and claims explicitly not made;
- the validated existing-substrate reuse inventory, including every accepted
  divergence and its migration or retirement owner;
- known interim adopters and compatibility commitments, or an explicit
  `not_applicable` reason;
- capability-matrix and documentation-routing changes, or an explicit
  `not_applicable` reason; and
- the gate decision and only the next action that decision authorizes.

Additional lanes apply only when their prerequisite capability exists:

| Evidence lane | Required tranches |
| --- | --- |
| Commit-pinned experiment, benchmark definition, precommitted baselines, search/validation/holdout partitions | E0, E3, E3F, E4E |
| Subject/rewrite/original-and-replacement realization payload/variant registry identity, stale/revoked/forged negatives | E1 and every later tranche that consumes realizations or variants |
| Execution-instance admission, request/attempt/run reconciliation, crash/restart, duplicate prevention | E2 and every later tranche that launches trials |
| Subject visit/context identity, raw-ledger roots, typed assessments, composition, redaction, cardinality, coverage, retry-safe aggregation, and overhead | E2O and any later experiment that opts into E2O |
| Genome/candidate identity, content-addressed experiment/arm, search-controller-policy, and arm-information-isolation contracts, frozen common inputs plus typed same-arm information/parent provenance, explicit common-policy versus declared-policy-treatment mode, conformant content-addressed controller decisions backed by metered transitions, complete fixed complements, closed execution envelopes, pre-work allocation and terminal charge for every feature-work kind, precommitted per-arm allocation of shared feature cost, trusted unique-request candidate/trial bindings, common analysis freeze, complete controller/feature-work/trial arm ledgers, lineage, and population/controller resume | E3, E3F, and E4E |
| Frozen deletion inventory and per-entry disposition, public-export/reference/CLI/docs/example/selector-route scans, supported run-root/adopter scans, deletion tombstones or history bindings, capability/routing retirement, and fresh before/after verification | E3R only |
| Fragment-search contract, reusable realization archive, context/background cells, matched substitution, unique complete-empty no-provider or complete provider-ledger prompt pairing, independent transfer, and archive resume | E3F only |
| Prompt lexical-role tests, dependency-minimal registered semantic-program and composition-environment/program-instance identity, total per-call bindings, governed attempt-composition artifacts, complete call-attempt ledgers, exact invocation/provider identity, and protected-content handling | E4P, E4E, any provider-bearing E3F amendment, and any amended E5 prompt locus |
| Sandbox/capability/threat-model and adversarial isolation evidence | E5 only |

An earlier tranche records an unavailable later lane as `not_applicable`, not
as a failed gate and not through a mock claiming future behavior.

Reports and side-by-sides are views. Where present, structured registry records,
typed trial evidence, compiler artifacts, run state, and committed source
remain authority.

## Verification Ladder

Each tranche runs only the applicable lanes, in this order:

1. universal task-local schema, identity, deterministic-canonicalization, and
   documentation consistency checks;
2. E0's pinned-build reproduction and baseline experiment checks, or the
   narrow owning implementation tests for the tranche;
3. E1+ compiler/type/effect/source-map, dependency-minimal reusable-domain
   versus occurrence-only identity, inert realization payload registry/handle,
   and variant-registry tests when variant substrate is in scope;
4. E2+ execution admission, SDK/CLI, request/attempt/run reconciliation, and
   fault injection when trial substrate is in scope;
5. E2O instrumentation-map and visit/context-to-realization binding,
   raw-ledger, typed-assessment,
   composition, retry-safe aggregation, redaction, cardinality, coverage, and
   performance tests only when E2O is activated;
6. E3/E3F/E4E candidate, content-addressed
   arm/mutation-mask/fixed-complement/closed-execution-envelope and
   search-controller-policy contracts, common-policy and
   declared-policy-treatment modes, decision-registry completeness and policy
   conformance, frozen-common-input and same-arm parent/information provenance,
   cross-arm visibility/leakage negatives, unique-request pre-work assignment
   and terminal charge for controller, proposal/provider/compiler/
   certification/admission, evaluator/aggregation, pairing/comparison, archive,
   and common-freeze work, precommitted per-arm shared-work allocation,
   pre-launch trial assignment, common analysis freeze, complete
   controller/feature-work/trial ledgers, budget/randomization,
   controller-resume, optimizer-baseline, validation, and sealed-holdout
   checks;
7. E3F reusable-realization archive, background/prompt-pairing (including the
   unique complete-empty no-provider result and complete-ledger not-reached
   proof), independent-transfer, swapped-binding rejection, and candidate-only
   comparison checks only when E3F is activated;
8. E3R frozen-inventory, supported-state/adopter, public-export/reference,
   route, deletion-order, tombstone/history, and ordinary-workflow
   non-regression checks only when retirement is activated;
9. E4P/E4E prompt role-classification, used/unused semantic dependency
   identity, governed composition/attempt reconstruction, total call-binding
   association, reachability/preparation/missing-evidence distinctions,
   protected-content, declared-drift, mediator/non-target matching, and
   provider-envelope checks;
10. E5 adversarial sandbox and capability enforcement checks only after E5 is
   amended into the roadmap;
11. one end-to-end usage through every real public entrypoint introduced or
   consumed by the tranche;
12. broad suite at implementation-tranche closeout; and
13. independent specification and code-quality review.

After narrow selectors, broad, slow, or full pytest runs use:

```bash
pytest -q -n 16 --dist=worksteal
```

Long-running checks stay in tmux. Existing unrelated failures are compared by
exact test identity; verification is not weakened to make a gate pass.

## Concurrency And Shared-Surface Rules

- E0 executes only against its one commit-pinned immutable source/build and
  environment snapshot. It is logically non-blocking for S7-S8; its
  shared-checkout plan/record commits and any shared-checkout broad tests remain
  serialized, while S7/S8 source changes cannot enter the E0 experiment.
- E0 may not modify public compiler, IR, runtime, CLI, or `.orc` language
  contracts. If it discovers that such a change is required, it stops and
  records that requirement for E1.
- E1 owns compiler subject manifests, original/replacement realization
  domains, inert payload registry/handles, certification, variant identity, and
  common operation metadata.
- E2 owns registered execution instances, child-trial runtime behavior,
  request/attempt/run reconciliation, SDK, and CLI.
- E2O, when activated, has a separate plan owning its exact compiler
  call-site/correspondence extension, per-variant instrumentation maps, runtime
  observation, observability, neutral evaluation/aggregation, redaction, and
  performance surfaces. It is serialized
  with E1-E2 owners and completes before an E3 or E3F experiment that requires
  it.
- E3 owns evolution admission, the general content-addressed experiment/arm
  and search-controller-policy contracts, trusted controller-decision registry
  and conformance mechanism, arm-information isolation plus input-provenance
  registry, trusted metered feature-work allocation/terminal-charge registry
  and per-arm shared-cost rule, trusted candidate/trial assignment mechanism,
  complete controller/feature-work/trial ledgers, and controller/library policy
  over E1-E2.
- E3R owns deletion and retirement routing for rejected E1/E2 substrate. It
  runs only after other E-series work is quiescent and is serialized with
  every owner whose surface or supported run state appears in its frozen
  inventory.
- E3F owns only feature-level background comparison, fragment archive,
  realization selection, and reproduction over retained E1-E3 plus E2O
  contracts. It cannot add a fragment execution path.
- E4P owns neutral prompt-program, composition-environment,
  provider/context-policy instance, total per-call binding, governed
  per-attempt composition, and complete call-ledger identity, including the
  additive E2 identity revision. E4E owns only prompt-evolution admission and
  prompt/code/joint arm profiles over E3's general experiment-assignment
  mechanism plus whole-candidate controller policy over retained E1-E4P
  substrate; it does not extend E3F into prompt-fragment selection.
- E5 requires separately assigned security ownership and may not be smuggled
  into an earlier tranche as a “small capability extension.”
- No two active plans may edit the same compiler, lowering, runtime, registry,
  state, provider, or specification owner without a reviewed sequencing
  amendment.

## Activation Procedure

This draft becomes executable only through a separate accepted routing change.
Activation must:

1. record user acceptance of the umbrella design and this roadmap;
2. amend the current execution sequence so Stage 8 is “final stage of the
   current S-series,” not the global final stage, and link this conditional
   E-series;
3. select only E0 initially;
4. create an E0 component plan and exact experiment decision-record target;
5. if a workflow-driven drain will select work, create the E0 brief and a
   one-row machine-readable manifest under a dedicated
   `WORKFLOW-LISP-EVOLUTION` program namespace, with E0 marked `pending`;
6. include for every activated manifest row its brief, design, design-review,
   plan, plan-review, execution-report, implementation-review, item-summary,
   prerequisites, design depth, status, and completion gate;
7. reserve every gate, readiness/feasibility, activation, and amendment
   decision-record path and validate its schema before any predecessor
   transition that may consume it;
8. validate the manifest and selector deterministically before launch;
9. inspect active-run state for cached versus live selector inputs and prevent
   stale workflow steps from overwriting the new route;
10. update `docs/capability_status_matrix.md` truthfully at each lifecycle
    transition: initial rows are `Designed` or `Future`; landed E1/E2 rows use
    their implemented availability with normal new-author use `No` and
    `experimental/non-promoted pending substrate disposition` routing;
    `RETAIN_SUBSTRATE`
    records the explicit promotion decision; and `PASS_E3R` changes retired
    rows to `Retired` and removes normal routing; and
11. update documentation routing and record the exact next selected item.

The initial manifest contains E0 only. Add E1, E2, optional E2O, E3,
conditional E3R, optional E3F, E4P, E4E, or an amended E5 as a new `pending`
row only after its exact predecessor records and one row-authorizing decision
authorize it. The proposed ledger is not itself a machine queue, and later
rows must not be preloaded as automatically ready or ambiguously blocked work.

### Selector Decision Records

Activation must create—not merely mention—a decision-record namespace such as
`docs/plans/WORKFLOW-LISP-EVOLUTION/decisions/` and name each exact target path
in the activated manifest. This roadmap does not create that namespace while
the program is unactivated.

The follow-on program routing owner authors each record; an independent
design/specification reviewer accepts it. The controller under evaluation may
produce evidence but cannot approve or mutate its own route. Gate,
readiness/feasibility, activation, and amendment decisions use one validated
record family rather than prose-specific schemas:

```text
SelectorDecisionRecord = {
  decision_id: Digest,
  decision_kind:
    E0_GATE | E1_GATE | E2_GATE | E2O_GATE | E3_GATE | E3R_GATE
    | E3F_GATE | E4P_GATE | E4E_GATE | E5_GATE
    | E3_READINESS | E3_CONTROLLER_FEASIBILITY
    | E3F_OBSERVATION_ROUTE | E4P_READINESS
    | EARLY_SUBSTRATE_DISPOSITION
    | TRANCHE_ACTIVATION | ROADMAP_AMENDMENT,
  activation_target: Optional[TrancheId],
  decision_contract_id: Digest,
  prerequisite_decision_ids: Vector[Digest],
  evidence_bundle_ids: Vector[Digest],
  allowed_outcomes: NonEmptyVector[DecisionOutcomeTag],
  selected_outcome: DecisionOutcomePayload,
  revision_ordinal: Int,
  authorized_next_manifest_rows: Vector[ManifestRowRef],
  authorized_route_outcomes: Vector[RouteOutcome],
  expected_selector_preimage_id: Digest,
  reviewer_approval_ids: NonEmptyVector[Digest],
  supersedes_decision_id: Optional[Digest]
}

ManifestRowRef = {
  tranche_id: TrancheId,
  manifest_row_id: Digest
}

DecisionOutcomePayload =
    { outcome_tag: SimpleDecisionOutcomeTag }
  | E3GateDecision
  | {
      substrate_disposition:
        RETAIN_SUBSTRATE | RETIRE_EXPERIMENTAL_SUBSTRATE
    }
  | {
      activation_outcome: ACTIVATE_TARGET | DEFER_TARGET
    }

SimpleDecisionOutcomeTag =
  DecisionOutcomeTag excluding {
    ACTIVATE_TARGET, DEFER_TARGET,
    E3_EVIDENCE_ACCEPTED, REVISE_E3_EXPERIMENT,
    STOP_E3_UNEXECUTABLE_OR_INVALID,
    RETAIN_SUBSTRATE, RETIRE_EXPERIMENTAL_SUBSTRATE,
    ADOPT_ORC_CONTROLLER, KEEP_CONTROLLER_EXTERNAL,
    NO_CONTROLLER_FEATURE,
    RETAIN_CODE_EVOLUTION_AND_PROCEED_TO_PROMPT_HYPOTHESIS,
    RETAIN_CODE_EVOLUTION_STOP_BEFORE_PROMPT, STOP_EVOLUTION_FEATURE,
    PROCEED_TO_FRAGMENT_HYPOTHESIS, STOP_AT_CANDIDATE_ONLY
  }

E3GateDecision =
    { evidence_outcome: REVISE_E3_EXPERIMENT }
  | {
      evidence_outcome:
        E3_EVIDENCE_ACCEPTED | STOP_E3_UNEXECUTABLE_OR_INVALID,
      substrate_disposition:
        RETAIN_SUBSTRATE | RETIRE_EXPERIMENTAL_SUBSTRATE,
      controller_disposition:
        ADOPT_ORC_CONTROLLER | KEEP_CONTROLLER_EXTERNAL
        | NO_CONTROLLER_FEATURE,
      optimizer_disposition:
        RETAIN_CODE_EVOLUTION_AND_PROCEED_TO_PROMPT_HYPOTHESIS
        | RETAIN_CODE_EVOLUTION_STOP_BEFORE_PROMPT
        | STOP_EVOLUTION_FEATURE,
      fragment_search_disposition:
        PROCEED_TO_FRAGMENT_HYPOTHESIS | STOP_AT_CANDIDATE_ONLY
    }
```

`TRANCHE_ACTIVATION` has exactly `ACTIVATE_TARGET` and `DEFER_TARGET` as its
allowed outcomes; only the former may name one matching manifest row.
`E4P_READINESS` has exactly `PROMPT_IDENTITY_USE_CASE_READY` and
`DEFER_PROMPT_IDENTITY`. `EARLY_SUBSTRATE_DISPOSITION` has exactly
`RETAIN_SUBSTRATE` and `RETIRE_EXPERIMENTAL_SUBSTRATE` and carries no feature
dispositions.

`decision_contract_id` selects the versioned validator and exact
subject-specific outcome set; an author cannot make a record self-authorizing
by choosing `allowed_outcomes`. `manifest_row_id` digests the complete proposed
activation row, not only its tranche label. `activation_target` is present only
for `TRANCHE_ACTIVATION`, and gate records never add manifest rows. A gate,
readiness, feasibility, or amendment record may establish eligibility or a
terminal route, but exactly one accepted `TRANCHE_ACTIVATION` owns each row
addition. `SimpleDecisionOutcomeTag` excludes Gate E3 evidence/disposition and
activation outcomes, so neither may validate through the generic variant.

Gate E3 uses a tagged `selected_outcome`. `REVISE_E3_EXPERIMENT` carries no
dispositions. `E3_EVIDENCE_ACCEPTED` and
`STOP_E3_UNEXECUTABLE_OR_INVALID` carry substrate, controller, optimizer, and
fragment-search dispositions; the validator enforces every combination rule
in Gate E3, including the dispositions forced by the stop outcome.

The complete row-adding transition table is:

| Activation target | Required accepted records |
| --- | --- |
| E0 | accepted program activation amendment and user acceptance |
| E1 | Gate E0 `PROCEED_TO_E1` and either Gate S8 completion or an accepted sequencing amendment authorizing pre-S8 activation |
| E2 | Gate E1 `PASS_E1` |
| E2O before E3 | Gate E2 `PASS_E2` and E3 readiness `OBSERVATION_EXTENSION_REQUIRED` |
| E3 black-box | Gate E2 `PASS_E2` and E3 readiness `BLACK_BOX_SUFFICIENT` |
| E3 after E2O | Gate E2 `PASS_E2`, E3 readiness `OBSERVATION_EXTENSION_REQUIRED`, and Gate E2O `PASS_E2O` |
| E2O after E3 | Gate E3 `PROCEED_TO_FRAGMENT_HYPOTHESIS` and E3F observation route `OBSERVATION_EXTENSION_REQUIRED` |
| E3F | retained E3 with `PROCEED_TO_FRAGMENT_HYPOTHESIS`, Gate E2O `PASS_E2O`, and either E3F route `USE_PASSED_E2O` or route `OBSERVATION_EXTENSION_REQUIRED` followed by a fresh post-`PASS_E2O` activation |
| E3R | Gate E3 `RETIRE_EXPERIMENTAL_SUBSTRATE` with the required compatible dispositions, or `EARLY_SUBSTRATE_DISPOSITION` selects retirement; either route also binds a validated `RetirementPreflightEvidenceBundle` with zero unresolved consumers |
| E4P | Gate E2 `PASS_E2` and E4P readiness `PROMPT_IDENTITY_USE_CASE_READY` |
| E4E | Gate E4P `RETAIN_PROMPT_IDENTITY` plus either the exact retained E3 prompt-hypothesis disposition combination or `ALTERNATIVE_PROMPT_HYPOTHESIS_ELIGIBLE` with accepted umbrella-design and roadmap amendments and their passed retain/replace gates for substrate and controller |
| E5 | an accepted roadmap amendment, its security/capability acceptance records, and every prerequisite named by that amendment |

E3 controller feasibility constrains the E3 decision and adds no row. E3
readiness `STOP_E3_HYPOTHESIS` adds no row and, if landed E1/E2 substrate
remains, requires `EARLY_SUBSTRATE_DISPOSITION` before program completion. E3F
observation `STOP_E3F_OBSERVATION_UNAVAILABLE` also adds no row, but its
prerequisite Gate E3 `RETAIN_SUBSTRATE` already supplies the substrate
disposition. Gate outcomes never imply a row merely because prerequisite
evidence exists.

Each record is immutable after acceptance. A correction writes a new record
with an incremented revision and `supersedes_decision_id`; it does not rewrite
gate history. An already consumed decision may be superseded only by a
contract-defined follow-on route/recovery transition, such as E2O
`OMIT_E2O`, or by an explicit amendment; silent correction is forbidden. The
selector transition atomically compares and updates the canonical selector
plus manifest preimage; a stale CAS changes neither. An accepted record whose
CAS fails remains evidence but is not applied selector authority, so a fresh,
reviewer-accepted activation record must name the new preimage.

The selector persists distinct gate, readiness/feasibility, amendment, and
activation decision IDs, while each manifest row persists its exact
`activation_decision_id`. A workflow may not collapse them into one generic
pointer or infer readiness from report prose, an uncommitted file, or the mere
existence of evidence.

Before E-series activation, minimal selector fixtures must prove E1 activation,
both E3F routes including deferred post-`PASS_E2O` activation, an E3R route, a
terminal E0 stop, an early substrate disposition after a stopped E3
hypothesis, stale-preimage rejection, and invalid Gate E3 disposition
rejection. If the active selector cannot validate the decision contract or
atomically digest selector and manifest state, activation is blocked pending a
separate implementation plan; prose emulation is forbidden.

## Activation And Gate State Model

Prose uses the following states:

- `Not activated`: proposed work with no selector authority.
- `Pending`: activated manifest work whose prerequisites are not yet satisfied
  or whose selector has not started it.
- `In progress`: one selected tranche with an owning plan/run.
- `Completed`: implementation and its completion gate have passed with fresh
  evidence.
- `Stopped`: a reviewed terminal outcome under the tranche's stop criteria.
- `Deferred`: intentionally unscheduled pending a named external prerequisite.
- `Decision open`: a required gate, route, feasibility, activation, or
  amendment record has a target but no accepted outcome; it authorizes no
  selector transition.
- `Decision accepted`: an immutable validated record is evidence or eligibility
  authority; only an applied activation record adds a manifest row.
- `Decision superseded`: historical decision retained after an explicit
  revision record; it is not current selector authority.
- `Decision accepted, CAS unapplied`: the record passed review but its expected
  preimage was stale; it changed no selector or manifest state.

Writing a design, roadmap, plan, report, or example never changes a tranche to
`Completed`.

## Program Completion

The follow-on program is complete under any of these legitimate outcomes:

1. E0 stops with evidence that no reusable substrate is warranted.
2. Gate E3 or an early substrate-disposition record selects retirement and E3R
   reaches `PASS_E3R`; the disposition decision alone is not completion.
3. E1 or E2 lands useful neutral substrate, Gate E3 or an early
   substrate-disposition record retains it, and later feature gates stop.
4. E3 retains code-only evolution externally or in `.orc` while E3F, E4P, E4E,
   and E5 stop or remain deferred.
5. E3F adopts contextual fragment search, or stops while candidate-only E3
   remains retained.
6. E4P lands independently useful prompt identity after Gate E3 or an early
   substrate-disposition record retains its E1/E2 substrate, with or without
   an E4E feature.
7. E4E lands a bounded no-tool prompt-evolution feature while E5 remains
   deferred.
8. A later amended E5 slice passes its independent security and effectiveness
   gates.

Completion therefore means “the last authorized gate reached a reviewed
terminal decision,” not “all E0-E5 features shipped.”

## Program-Wide Stop And Revise Conditions

Stop or narrow the program if:

- E0 shows negligible duplicated coordination machinery and no discriminating
  optimizer value;
- useful subject identity requires a mutable compiler AST or guessed
  cross-bundle correspondence;
- certification cannot reuse the ordinary full compiler;
- trials require hot replacement, imported parent checkpoints, or arbitrary
  path execution;
- common operation metadata obscures workflow/procedure/provider effects,
  identity, or durability;
- the public SDK is more complex than the ad hoc baseline without improving
  recovery, audit, or reuse;
- the `.orc` controller is more complex than the external controller without
  a measured integration benefit;
- adaptive search fails to beat random/simple baselines after full cost
  accounting;
- contextual fragment selection fails to beat candidate-only/locus-guided
  baselines after trace, pairing, archive, and full-recertification costs, or
  only appears to win by collapsing context/background heterogeneity;
- prompt binding roles, per-call associations, or treatment-influenced bytes
  cannot be distinguished without ambient hashes or post-treatment matching;
- prompt drift or protected-content leakage prevents honest comparison;
- ordinary workflows pay material evolution/tracing overhead when disabled; or
- an unrecorded supported adopter or compatibility promise would make the
  selected substrate-retirement route false;
- effectful candidates cannot be isolated from trusted state and authority.

If the only compelling use remains one optimizer over one workflow, keep it in
an external or feature-specific package. Do not generalize the language core.

## First Handoff

After user acceptance and an explicit activation amendment, write only the E0
proving-experiment plan. That plan must choose the exact deterministic
benchmark, precommit baselines and partitions, inventory all ad hoc machinery,
and name the decision-record path.

Do not write any later-tranche implementation plan from this draft. E1, E2,
E2O, E3, E3R, E3F, E4P, E4E, and E5 plans remain gate-dependent.
