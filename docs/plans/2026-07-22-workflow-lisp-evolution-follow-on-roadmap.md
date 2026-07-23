# Workflow Lisp Evolution Follow-On Roadmap

Status: proposed follow-on roadmap; not active work instructions

Created: 2026-07-22

Current implementation status: Future; no tranche in this document is selected

Copy safety: planning reference only; do not use this document as evidence that
any evolution, variant, trial, prompt-program, or sandbox surface is implemented

## Purpose

Define a conditional, evidence-driven program for:

- compiler-certified variants over immutable Workflow Lisp bundles;
- neutral registered execution instances and child-workflow trials;
- replaceable code-search and evolutionary controllers;
- later prompt evolution; and
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

Today, the active selector remains Stage 6 Task 6 in
[`2026-07-09-procedure-first-roadmap-execution-sequence.md`](2026-07-09-procedure-first-roadmap-execution-sequence.md).
Stages 7 and 8 remain provider live binding and the `.orc` language server.
This document does not amend that order, change an active workflow, create a
machine-readable tranche manifest, or make E0 selectable.

Readers looking for current authoring behavior must continue to use ordinary
static `.orc`, compile-time `ProcRef`, external source generation, and new
immutable runs. The current capability status matrix and accepted frontend
designs remain authoritative.

## Why A Separate Follow-On Program

The proposal combines three questions that should not be allowed to validate
one another circularly:

1. **Substrate value:** does compiler-owned identity, certification, and trial
   coordination materially improve on ad hoc source-generation tooling?
2. **`.orc` controller value:** does expressing a controller in Workflow Lisp
   improve typed recovery, auditability, or integration over an external
   controller using the same public substrate?
3. **Optimizer value:** does a genetic or other adaptive search policy beat
   random, enumerative, or simple local search after full cost accounting?

The candid effectiveness analysis that preceded this roadmap found no existing
five-minute artifact that answers these questions. The roadmap therefore starts
with evidence collection and preserves independent baselines throughout. It
does not use the system's self-hosting history, a toy that merely compiles, or
the existence of a complex substrate as proof of effectiveness.

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
                  +--> optional E2O neutral observation extension
                  |         |
                  +---------+
                  |
                  v
                 E3 code-only evolution and controller comparison
                  |
                  +-- positive hypothesis + retained substrate/controller --+
                                                                          |
E4P retained -------------------------------------------------------------+
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
than semantic: E1-E3 edit compiler, IR, runtime, identity, SDK, and
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
- exact trial identity, budgets, evidence, and reconciliation.

It must not know about:

- genomes, populations, generations, crossover, mutation probabilities;
- fitness, winner, elite, or selection semantics; or
- optimizer-specific lineage.

Evolution admission may bind validated genes to one neutral execution
instance. A replaceable controller may propose and select candidates only
through those public contracts.

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

### Honest Security Boundary

A candidate workspace is an output boundary, not an OS sandbox. E0-E3 accept
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

## Proposed Tranche Ledger

These rows are proposed, not `pending`: no executable manifest exists yet.

| Tranche | Status | Entry dependency | Primary decision |
| --- | --- | --- | --- |
| E0 — Proving experiment | Not activated | Accepted design/roadmap and a recorded clean Stage-6 checkpoint | Is there enough feature or coordination value to justify reusable substrate work? |
| E1 — Neutral subject and certification substrate | Not activated | Gate E0 says `PROCEED_TO_E1`; Gate S8 complete unless explicitly amended | Can variants be identified and certified without evolution concepts or mutable compiler ASTs? |
| E2 — Neutral execution and trial substrate | Not activated | Gate E1 passed | Can exact registered variants run through crash-durable public child-run paths without claiming sandboxing? |
| E2O — Optional neutral observation extension | Not activated; optional | Gate E2 passed and the E3-readiness decision says `OBSERVATION_EXTENSION_REQUIRED` | Can bounded expression observation help neutral clients without imposing trace overhead on ordinary runs? |
| E3 — Code-only evolution | Not activated | Gate E2 passed, plus either `BLACK_BOX_SUFFICIENT` or Gate E2O passed | Do bounded evolution and/or a `.orc` controller add value over simpler and external baselines? |
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
5. Content-addressed immutable variant registry and opaque inert handles with
   resolution, rehash, retention, and revocation checks.
6. Source-map and reviewable-patch projection from certified variants.
7. One public read/propose/certify/register API suitable for later SDK/CLI
   exposure.
8. One non-evolution client, such as a certified refactoring preview, using the
   same manifest, policy, certifier, and variant registry without importing
   candidate, genome, fitness, or controller types.

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
- common operation metadata retains nominal kind, effect, and durability
  differences;
- ordinary workflows that do not request manifests or variants pay no
  persistent or tracing overhead; and
- independent design/specification and code-quality review approve the slice.

If stable identity requires a mutable public AST or guessed cross-bundle node
correspondence, `PASS_E1` is forbidden; choose `REVISE_E1` or `STOP_E1`.

## E2 — Neutral Execution And Trial Substrate

### Question

Can a registered variant be bound to one exact, policy-narrowed execution
envelope and launched through a crash-durable new-run path that both external
and future `.orc` clients can use?

### Deliverables

1. Neutral `ExecutionAdmissionPolicy`, complete `ExecutionInstanceSpec`, and
   content-addressed `RegisteredExecutionInstance`.
2. Exact entrypoint, runtime binding, environment, evaluator, workspace,
   observation, budget, and frozen-kernel identity in admission evidence.
3. Registry resolution and rehash before launch.
4. One runtime-native certified-workflow child-trial effect that accepts only a
   registered execution-instance handle.
5. Durable request/attempt allocation, request-to-run linkage, crash
   reconciliation, retry semantics, and no-duplicate-launch evidence.
6. Typed trial evidence and explicit separation of execution-instance
   admission rejection, trial failure, and substrate corruption. Candidate
   rejection begins in E3.
7. A public SDK and CLI using the same certification, registration, and trial
   services intended for `.orc`; no private compiler shortcut.
8. A workspace/output contract and capability ceiling that state explicitly
   that the tranche does not sandbox arbitrary generated code.
9. A non-evolution regression or what-if runner using the same execution
   registration and trial path.

### Exclusions

- no unregistered bundle or arbitrary path launch;
- no imported parent checkpoint or run identity;
- no in-process bundle replacement;
- no candidate/genome/fitness semantics in the neutral APIs;
- no provider, command, filesystem, network, or process capability in the
  first accepted harness;
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
- ordinary non-trial runs pay no controller or trial-registry overhead; and
- focused, integration, end-to-end, broad-baseline, specification, and quality
  gates pass with fresh evidence.

If useful trials require hot replacement or importing parent execution state,
`PASS_E2` is forbidden; choose `REVISE_E2` or `STOP_E2` rather than weakening
immutable generation boundaries.

## E2O — Optional Neutral Observation Extension

### Question

If an E3-readiness review demonstrates that black-box whole-candidate fitness
is insufficient, can bounded expression observation improve mutation guidance
without becoming evolution-specific compiler/runtime machinery?

E2O is omitted by default. It is a neutral E1/E2 substrate extension with its
own compiler, runtime, observability, security/redaction, and performance
owners. It executes serially before any E3 experiment that declares local
observation required. Core E3 remains valid using only whole-candidate
evidence.

After `PASS_E2` and before adding either E2O or E3 to a selector, a reviewed
readiness record over the fixed E0 benchmark and E2 trial evidence chooses
exactly one route:

- `BLACK_BOX_SUFFICIENT`: add E3 without E2O; or
- `OBSERVATION_EXTENSION_REQUIRED`: add E2O, and keep E3 ineligible until
  `PASS_E2O`; or
- `STOP_E3_HYPOTHESIS`: add neither E2O nor E3 and record a terminal stopped
  feature route.

This is a routing decision, not an E3 implementation phase, so it does not
create a dependency cycle between E2O and E3.

### Deliverables

- an opt-in compiler-instrumented trace overlay using E1 subject identities and
  E2 observation/trial contracts;
- a finite `describe` view bounded by subject depth and subject count;
- trace events keyed by exact manifest, subject, and visit identity;
- default payloads limited to type, shape, digest, redaction class, timing, and
  declared metrics;
- explicit policy for any raw value;
- a bounded public worklist/traversal contract usable between immutable trial
  generations; and
- one non-evolution diagnostics or performance-analysis client using the same
  trace contract.

Local evaluators may prioritize loci or supply surrogate scores. They remain
advisory, cannot certify causality, and cannot override worse whole-candidate
evidence.

This is “recursive” adjudication as finite tree processing, not recursive
runtime `eval`, recursive procedure calls, durable checkpoints for every
expression, or a provider traversing mutable compiler ASTs. Instrumentation is
opt-in, sampled/bounded, and absent from ordinary workflow execution.

### Gate E2O

The reviewed decision record chooses exactly one outcome:

- `PASS_E2O`: neutral trace contracts, the non-evolution client, redaction,
  bounded overhead, and whole-candidate authority all pass; an E3 plan may
  depend on them;
- `REVISE_E2O`: the record names a bounded correction and E3 remains
  ineligible until the amended gate passes; or
- `OMIT_E2O`: tracing is unnecessary, too costly, too leaky, or too ambiguous;
  E3 remains ineligible until a new reviewed readiness record either changes
  the route to `BLACK_BOX_SUFFICIENT` based on new evidence or records
  `STOP_E3_HYPOTHESIS`.

If instrumentation dominates trial cost, leaks protected values, or cannot
distinguish observation from causal attribution, `PASS_E2O` is forbidden.

## E3 — Code-Only Evolution

### Question

Given a neutral certified-variant and trial substrate, do a bounded optimizer
and a Workflow Lisp controller offer value that simpler strategies and an
external controller do not?

### E3A: Trusted Evolution Admission

Add:

- compiler-owned code loci referencing neutral rewrite policies;
- bounded genome schemas containing code genes only;
- trusted genome and candidate admission;
- exact candidate-to-execution-instance registration;
- content identity distinct from lineage/population occurrence;
- fixed evaluator, observation, environment, workspace, budget, kernel, and
  single trial-entrypoint contracts; and
- rejection of every prompt, provider-policy, context-policy, or effectful gene.

The evolution layer validates and narrows neutral policy; it does not compile
code itself and does not create a second trial path.

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
candidates and terminal trial sets should match; any difference must reduce to
a versioned controller-policy input.

The `.orc` controller may use ordinary typed procedures, workflows, loops,
records, and child-trial effects. It does not receive AST values, dynamic
callables, a magic current-bundle reference, or compiler-private authority.

### Required Comparisons

Report separately:

- substrate versus the E0 ad hoc coordination path;
- external versus `.orc` control over the same substrate when
  `ORC_CONTROLLER_FEASIBLE`, or the reviewed feasibility boundary and external
  result when `ORC_CONTROLLER_INFEASIBLE`;
- the chosen optimizer versus random and a simple search baseline; and
- human-authored baseline versus selected candidate on validation and sealed
  promotion holdout.

Charge compilation, trials, evaluator calls, storage, wall time, provider cost
if any, expression-observation overhead if enabled, and operator attention.

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

Line counts may be reported but are not the verdict. The comparison must include
identity, crash recovery, audit evidence, and maintenance burden that would
otherwise be hidden in helper code.

### Gate E3

The reviewer first chooses one evidence outcome:

- `E3_EVIDENCE_ACCEPTED`: the required comparisons are complete and valid, so
  the dispositions below may be selected; or
- `REVISE_E3_EXPERIMENT`: the record names a bounded experimental correction,
  no E3 feature is promoted, and E4E remains ineligible until an amended E3
  plan is explicitly accepted and rerun; or
- `STOP_E3_UNEXECUTABLE_OR_INVALID`: trusted admission/controller execution
  cannot be implemented within the architecture, or no valid evidence or
  bounded correction is possible; this implies `NO_CONTROLLER_FEATURE` and
  `STOP_EVOLUTION_FEATURE`, leaves E4E ineligible, and records either
  `RETAIN_SUBSTRATE` or
  `RETIRE_EXPERIMENTAL_SUBSTRATE` from the independent E0-E2 substrate
  evidence.

With `E3_EVIDENCE_ACCEPTED`, the decision record chooses all three
dispositions:

**Substrate disposition**

- `RETAIN_SUBSTRATE`: neutral non-evolution and coordination value is real; or
- `RETIRE_EXPERIMENTAL_SUBSTRATE`: its complexity exceeds its demonstrated
  value and no compatibility commitment prevents removal.

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

The dispositions answer separate questions, but only these combinations are
valid:

- `RETIRE_EXPERIMENTAL_SUBSTRATE` requires `NO_CONTROLLER_FEATURE` and
  `STOP_EVOLUTION_FEATURE`;
- `STOP_EVOLUTION_FEATURE` requires `NO_CONTROLLER_FEATURE`;
- either code-evolution retention outcome requires `RETAIN_SUBSTRATE` and
  exactly one of `ADOPT_ORC_CONTROLLER` or `KEEP_CONTROLLER_EXTERNAL`; and
- `ADOPT_ORC_CONTROLLER` requires `ORC_CONTROLLER_FEASIBLE`, while
  `ORC_CONTROLLER_INFEASIBLE` forces `KEEP_CONTROLLER_EXTERNAL` for either
  code-evolution retention outcome; and
- E4E eligibility requires
  `RETAIN_CODE_EVOLUTION_AND_PROCEED_TO_PROMPT_HYPOTHESIS` together with
  `RETAIN_SUBSTRATE` and a retained controller.

Thus neutral substrate may survive a stopped evolution feature, and a useful
evolution controller may remain external, but no controller or prompt feature
can outlive the substrate it uses. Replacing that substrate requires a new
umbrella-design and roadmap amendment, not an invalid disposition combination.

## E4P — Prompt Identity

### Question

Can prompt programs and their invocations be identified and reconstructed
honestly enough to help non-evolution clients, given provider drift and the
distinction between semantic prompt content and exact invocation bytes?

### Deliverables

Prompt identity work may be proposed after E2 even if E3 is still running. Its
accepted readiness brief names the independent non-evolution use case; the E4P
row then owns its design, design review, plan, and implementation rather than
depending on a design it is supposed to produce. It binds:

- typed semantic prompt-program identity;
- the concrete provider-invocation projection into E1's common operation
  metadata, retaining provider effect, transport, and invocation-durability
  semantics rather than treating it as a procedure;
- protected dependency-content snapshot;
- exact rendered invocation bytes;
- transport binding;
- provider/model/call-policy identity that is declared or attested, without
  claiming hidden remote state is reproducible;
- tool, workspace, session, and context policy;
- evaluator prompt identity outside the mutable genome.

E4P does not activate prompt mutation by itself.

### Gate E4P

The reviewed decision record chooses exactly one outcome:

- `RETAIN_PROMPT_IDENTITY`: exact local invocation reconstruction, protected
  snapshot handling, declared-drift detection, qualified remote-provider
  claims, and the non-evolution use case all pass; E4E may use this substrate
  only if its other prerequisites also pass;
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

Prompt genes require:

- `PASS_E2` and a still-retained neutral substrate;
- E4P `RETAIN_PROMPT_IDENTITY`;
- E3
  `RETAIN_CODE_EVOLUTION_AND_PROCEED_TO_PROMPT_HYPOTHESIS`, with either
  `ADOPT_ORC_CONTROLLER` or `KEEP_CONTROLLER_EXTERNAL`; or
- an explicit umbrella-design and roadmap amendment that retains or replaces
  the substrate and controller and supplies a prompt-specific hypothesis
  despite a negative code-search result;
- text-only/no-tool, mock, replay, or genuinely sandboxed providers;
- no session reuse in the first slice; and
- equal-budget prompt-only, code-only, and joint arms.

Trials record prompt and code identities separately, but report fitness at
whole-candidate and experimental-arm level. Joint improvement is not causal
proof for either gene.

### Compelling Example Deliverables

Show side by side:

- a fixed hand-authored prompt and a selected prompt candidate;
- exact semantic, snapshot, rendered-byte, transport, and provider-envelope
  identities for each;
- prompt-only, code-only, and joint controller declarations using one trial
  substrate; and
- the same experiment with one declared drift injection that blocks comparison
  rather than silently mixing populations.

Report randomized contemporaneous arms and uncertainty for opaque provider
drift. A polished response sample is not effectiveness evidence.

### Gate E4E

The reviewed decision record chooses exactly one outcome:

- `ADOPT_BOUNDED_PROMPT_EVOLUTION`, only if:
  - exact candidate reproduction succeeds within the declared envelope;
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
- capability-matrix and documentation-routing changes, or an explicit
  `not_applicable` reason; and
- the gate decision and only the next action that decision authorizes.

Additional lanes apply only when their prerequisite capability exists:

| Evidence lane | Required tranches |
| --- | --- |
| Commit-pinned experiment, benchmark definition, precommitted baselines, search/validation/holdout partitions | E0, E3, E4E |
| Subject/rewrite/variant registry identity, stale/revoked/forged negatives | E1 and every later tranche that consumes variants |
| Execution-instance admission, request/attempt/run reconciliation, crash/restart, duplicate prevention | E2 and every later tranche that launches trials |
| Expression trace/redaction/overhead evidence | E2O and any later experiment that opts into E2O |
| Genome/candidate identity, lineage, population/controller resume | E3 and E4E |
| Prompt semantic/snapshot/invocation/provider identity and protected-content handling | E4P, E4E, and any amended E5 prompt locus |
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
3. E1+ compiler/type/effect/source-map and variant-registry tests when variant
   substrate is in scope;
4. E2+ execution admission, SDK/CLI, request/attempt/run reconciliation, and
   fault injection when trial substrate is in scope;
5. E2O trace/redaction/performance tests only when E2O is activated;
6. E3/E4E candidate, controller-resume, optimizer-baseline, validation, and
   sealed-holdout checks;
7. E4P/E4E prompt identity, protected-content, declared-drift, and provider
   envelope checks;
8. E5 adversarial sandbox and capability enforcement checks only after E5 is
   amended into the roadmap;
9. one end-to-end usage through every real public entrypoint introduced or
   consumed by the tranche;
10. broad suite at implementation-tranche closeout; and
11. independent specification and code-quality review.

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
- E1 owns compiler manifests, certification, variant identity, and common
  operation metadata.
- E2 owns registered execution instances, child-trial runtime behavior,
  request/attempt/run reconciliation, SDK, and CLI.
- E2O, when activated, has a separate plan owning its exact compiler
  instrumentation, runtime observation, observability, redaction, and
  performance surfaces. It is serialized with E1-E2 owners and completes
  before an E3 experiment that requires it.
- E3 owns only evolution admission and controller/library policy over E1-E2.
- E4P owns neutral prompt-program and invocation identity. E4E owns only
  prompt-evolution admission and experiment/controller policy over retained
  E1-E4P substrate.
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
7. validate the manifest and selector deterministically before launch;
8. inspect active-run state for cached versus live selector inputs and prevent
   stale workflow steps from overwriting the new route;
9. update `docs/capability_status_matrix.md` with `Designed` or `Future`
   statuses without implying implementation; and
10. update documentation routing and record the exact next selected item.

The initial manifest contains E0 only. Add E1, E2, optional E2O, E3, E4P, E4E,
or an amended E5 as a new `pending` row only after its exact predecessor gate
and activation decision authorize it. The proposed ledger is not itself a
machine queue, and later rows must not be preloaded as automatically ready or
ambiguously blocked work.

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

Writing a design, roadmap, plan, report, or example never changes a tranche to
`Completed`.

## Program Completion

The follow-on program is complete under any of these legitimate outcomes:

1. E0 stops with evidence that no reusable substrate is warranted.
2. E1 or E2 lands useful neutral substrate and later feature gates stop.
3. E3 retains code-only evolution externally or in `.orc` while E4P, E4E, and
   E5 stop or remain deferred.
4. E4P lands independently useful prompt identity, with or without an E4E
   feature.
5. E4E lands a bounded no-tool prompt-evolution feature while E5 remains
   deferred.
6. A later amended E5 slice passes its independent security and effectiveness
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
- prompt drift or leakage prevents honest comparison;
- ordinary workflows pay material evolution/tracing overhead when disabled; or
- effectful candidates cannot be isolated from trusted state and authority.

If the only compelling use remains one optimizer over one workflow, keep it in
an external or feature-specific package. Do not generalize the language core.

## First Handoff

After user acceptance and an explicit activation amendment, write only the E0
proving-experiment plan. That plan must choose the exact deterministic
benchmark, precommit baselines and partitions, inventory all ad hoc machinery,
and name the decision-record path.

Do not write any later-tranche implementation plan from this draft. E1, E2,
E2O, E3, E4P, E4E, and E5 plans remain gate-dependent.
