# Workflow Lisp Program-Search Boundary Invariants

- **Status:** adopted position statement (2026-07-24, owner-directed
  extraction)
- **Kind:** permanent architectural boundaries for any future program-search,
  self-modification, or evolution feature over Workflow Lisp
- **Provenance:** extracted from the parked
  `docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md`
  ("Program-Wide Architectural Boundaries") on the recommendation of the
  architectural critique at
  `artifacts/review/roadmap-follow-on/architectural-critique.md`. The parked
  roadmap's tranche ledger, gate lattice, and decision-record machinery are
  deliberately not extracted.
- **Authority:** these invariants constrain any future design in this space;
  this document schedules no work and activates no program.

## Why this document exists

If this system ever searches over, mutates, or machine-generates its own
workflows, the search machinery will be the most dangerous consumer the
compiler and runtime have. These invariants were designed carefully once;
they should not be re-derived per proposal. Any future search/evolution
design must either satisfy them or amend this document first, explicitly.

## 1. Immutable generation boundaries

- A running bundle is never modified. Mutation produces a *proposed next*
  bundle or runtime binding snapshot.
- Every code candidate passes through the ordinary full compiler pipeline —
  the same elaboration, typecheck, effect, and validation path as authored
  code. No reduced "candidate mode" certification exists.
- Candidate execution starts as a new registered run: a root run launched by
  an external controller through public `run`, recorded with its run id and
  state root by that experiment's lineage record, or a child where an
  admitted child route exists. The runtime is not changed. No `eval`, hot
  swap, dynamic linking, or checkpoint import ever turns candidate data into
  executing code.
- Promotion proposes a reviewable patch. Evaluation never edits canonical
  source as a side effect.

## 2. Provider output is untrusted data

A rewrite proposal — any code, prompt, or configuration a provider produces —
is data describing an intended change. It is never executable authority, an
executable closure, or a trusted fragment. It becomes behavior only by
passing through invariant 1 in full.

## 3. Neutral substrate versus feature

Any shared substrate (variant registries, trial execution, evidence capture)
may know about: concrete operation contracts, subject manifests, rewrite
proposals and certification policy, immutable variants, registered execution
instances, and exact trial identity/budget/evidence.

It must never know about: genomes, populations, generations, crossover,
mutation probabilities, fragment archives, fitness, winners, elites, or
selection semantics. Optimizer concepts live entirely in the replaceable
feature layer, which reaches the substrate only through its public contracts.

## 4. Whole-program evidence is deployment authority

Deployment-frontier membership, finalist selection and promotion require
evidence about complete, compiled and executed candidates. Contextual
fragment observations and explicit search-value estimates may guide
experiment-side proposal targeting, parent sampling and exploratory
retention, including retention of dominated candidates. They cannot alone
establish whole-program quality, validate a replacement, or authorize
promotion. Their provenance, context, uncertainty and noncausal limitations
remain explicit.

## 5. Evidence separation

Every optimization benchmark separates: adaptive search data; validation data
used to choose among already-produced candidates; and a sealed promotion
holdout opened only after candidate generation, analysis, and selection
freeze. The holdout never feeds mutation, selection, evaluator tuning, or
benchmark choice.

## 6. Honest security boundary

A candidate workspace is an output boundary, not an OS sandbox.
Provider-in-the-loop candidate evaluation is permitted under a disclosed
workspace boundary: ordinary configured agent sessions in separate clones
behind the comparison harness's shims and bubblewrap sandbox (private
`/tmp`, `/dev/shm` and process list, empty `/var/tmp`) with its stated
non-isolation (home, network, other sessions' transcripts), its
contamination scan and adjudication ([harness design](orc_effectiveness_comparison_harness.md)),
and finite envelopes, with evaluator truth outside every tree an agent can
reach. This is hygiene, not isolation, and is reported as such; effect-free
deterministic harnesses remain preferred where they suffice.

## 7. Typed-operation parity without kind erasure

A common metadata view over operations (identity, input/output types, effect
summary, provenance) is legitimate tooling. It never makes operation kinds
interchangeable: procedures remain statically lowered reuse units, workflows
remain durable public run/resume boundaries, provider calls remain effectful
invocations with fixed bindings. Matching types alone never proves semantic
substitutability; there is no universal runtime `Callable`, no runtime
closure, and no effect-erasing adapter. This restates the reuse contract's
one-typed-model rule from the search side.

## 8. Prompt identity is role-separated

Prompt-related identity is never one ambient hash. The durable role split:

- a prompt enters a subject's identity domain only when the compiler proves
  it is an actual resolved free binding of that subject;
- a prompt program's identity covers its *used* dependencies, not unused
  imports;
- fixed captures and dependency contracts belong to a protected composition
  environment;
- per-attempt rendered bytes, dependency snapshots, and transport belong to
  the attempt's governed composition snapshot, with a complete call ledger
  distinguishing not-reached, preparation failure, dispatch, and missing
  evidence.

This role split has diagnostic value independent of any search program: it
is the identity discipline that makes provider hangs, context drift, and
prompt-provenance questions answerable in the existing system.

<a id="proposed-amendment-2026-10-17"></a>

## Change note

Amended 2026-10-18 under the owner's directive to execute the structural
search roadmap; rationale in the
[structural search driver design](orc_structural_search_driver.md).

<a id="proposed-amendment-2026-10-19"></a>

Amended 2026-10-19: invariant 4 replaced under the owner's cumulative
workflow evolution extension (accepted for design, unselected for spend);
rationale in the
[cumulative campaigns design](orc_structural_search_cumulative_campaigns.md).
