# ORC Structural Search Cumulative Campaigns

- **Status:** partial: C1 whole-program cumulative campaigns are implemented
  offline in `experiments/orc_structural_search/` with scripted providers,
  including the evidence store, campaign protocol, breeding pool, parent
  policies and final assessments. The
  [offline guide](../../experiments/orc_structural_search/README.md#cumulative-campaigns-without-provider-calls)
  exercises the lifecycle with synthetic qualification; it establishes no live
  qualification or research utility. No live campaign or provider spend is
  selected. C2 remains contract level only.
- **Kind:** experiment-side contract for multi-generation search campaigns
  over whole `.orc` programs (stage C1, normative once selected) and for the
  conditional persistent contextual fragment evidence that may follow (stage
  C2, contract level only). Status-independent: the identities, store,
  protocol, policies, endpoints and attribution rules below do not change
  when a campaign is selected or runs.
- **Owns:** campaign and trial identities, the persistent evidence store, the
  campaign protocol, the breeding pool and its two parent policies, diversity
  pressure and the revisit rule, the endpoint, budget-accounting and power
  contract, the qualification receipt V2's family block (one rule file per
  package; V1 unchanged), the C2 fragment contract, the estimate and
  attribution rules, and the rationale for the 2026-10-19 amendment of
  boundary invariant 4.
- **Consumes, unchanged, from the [driver design](orc_structural_search_driver.md):**
  mutator sessions and `module`, admission, snapshots and `candidate_id`, the
  public `run` route, the task family with calibration and the V1
  [external qualification receipt](orc_structural_search_driver.md#external-qualification-receipt)
  (V2's family block is owned here),
  the metered Pareto [objective](orc_structural_search_driver.md#objective-selection-and-local-observations),
  [metering](orc_structural_search_driver.md#metering-and-consumption),
  [hygiene](orc_structural_search_driver.md#evaluation-hygiene),
  [records](orc_structural_search_driver.md#records), the skeleton hash and
  the endpoint classes; site facts from the
  [source-site inspection](workflow_lisp_source_site_inspection.md) with its
  [exclusions](workflow_lisp_source_site_inspection.md#34-exclusions).
- **Authority:** the [program-search boundary invariants](workflow_lisp_program_search_boundaries.md)
  (binding, invariant 4 as amended 2026-10-19), the
  [structural search roadmap](../plans/2026-10-18-orc-structural-search-roadmap.md)
  (Phase 2 and conditional Phase 2b), the experiment rules of the owner's
  2026-10-19 model-cap amendment (`AGENTS.md`, "Experiment rules") and the
  [harness model policy](orc_effectiveness_comparison_harness.md#experiment-model-policy).
- **Selection:** the
  [pilot plan](../plans/2026-10-19-orc-structural-search-cumulative-pilot-plan.md)
  records the selected offline C1 implementation and verification. Live
  selection remains under the roadmap's Phase 2 Gates, which point at Staging
  And Gates below as the single live gate list; numbers (power, budget, caps,
  wall-clock ceilings) belong to the pilot plan, and every live campaign is a
  separate owner approval.
- **Compatibility:** no runtime, spec, target or memo change. `orchestrator/`
  receives no populations, scores, selection policy or fitness.

## Summary And Scope

The question: does cumulative, multi-generation search over whole programs
produce a better quality/deployed-cost frontier at a fixed total search
budget than one-step search from the frontier alone? Most proposals may
fail, match their parents or do worse; a weak candidate may still carry
structure that becomes useful after further mutation. So breeding is
separated from deployment: a results archive with a derived frontier (the
driver's Pareto objective, tolerances and quality floor) sits beside a
bounded breeding pool, a bounded frontier subset plus a bounded reservoir of
non-frontier candidates. Reservoir membership conveys no deployment
endorsement. Persistent fitness is a query over evidence, never a scalar
attached to syntax.

Two stages, in this order:

| Stage | Content | Status |
| --- | --- | --- |
| C1 Whole-program cumulative pilot | Persistent evidence store, campaign checkpoint/resume, results archive with the metered frontier, breeding pool, the two parent policies, diversity pressure and the revisit rule, cumulative budget readout | Implemented offline with scripted providers; roadmap Phase 2; live qualification and separate spend gates remain |
| C2 Persistent contextual fragment evidence | Fragment identity with capture contracts, invocation accounting, context schema, estimates, composite adapter | Contract level only; roadmap Phase 2b, conditional on C1 (Staging And Gates) |

Out of scope: RL training, a new IR, automatic extraction of every subtree,
crossover, a general optimizer framework, a quality-diversity grid in C1,
dashboards, any runtime route. Whole-module mutation, ordinary compiler
admission, immutable snapshots, calibrated evaluation and enforced budgets
stay as the driver defines them.

## Identities

C1 adds two identities beside the driver's and keeps the local ones.

| Identity | Definition | Stage |
| --- | --- | --- |
| `candidate_id` | Unchanged ([driver](orc_structural_search_driver.md#candidate-snapshots-and-identities)): content address over source, dependency digests, externs, command boundaries and runtime commit | C1 |
| `context_key` | Versioned hash (`context_key_version`, tuple) of criterion-frozen context only: the adaptive task package SHA-256s, the criterion SHA-256, the runtime commit, the evaluator version, the criterion's envelope (episode and evaluation wall clocks, per-call timeout) and the model policy (admitted IDs and efforts as the criterion freezes them). Replicates, concurrency, horizon and `B_plan` are campaign parameters outside the key's inputs but inside the criterion hash, so a two-replicate warm start and one-replicate campaigns under one criterion pool | C1 |
| `campaign_id` | The operator's label plus the store-assigned campaign sequence number; unique per store, and a label is never reused. A warm start is its own campaign per context, `warm-` plus the twelve digest characters `context_key[5:17]` (after the version prefix) plus the sequence, never a fixed label | C1 |
| `evaluation_id` | Unchanged; local to a campaign's launches; a relaunched attempt is a new `evaluation_id` under the same job | C1 |
| `trial_id` | SHA-256 over `campaign_id`, the public `run` id, `evaluation_id` and the attempt number: one actual launch. Copied or derived records carry `origin_trial_id`; only original trials count as samples; ingest is idempotent on `trial_id` | C1 |
| `episode_id` | Unchanged; the campaign and generation are fields on the row | C1 |
| `fragment_id`, `site_id`, `invocation_id`, context schema | Reserved; defined at contract level under Stage C2. The driver's candidate-local `site_id` is unchanged and never a persistent fragment identity | C2 |

A campaign's context is fixed and frozen. Whole-program evidence pools
across campaigns only under equal `context_key`; a changed price table,
model allowlist, criterion, package, envelope or runtime commit partitions
evidence. Because the criterion hash is an input, pooling holds within one
criterion: a follow-up study under another criterion runs its own warm
start unless a cross-criterion pooling rule is predeclared. The campaign
record, not the id, carries the policy and its
parameters, the budget declaration, the seed set, the run seed and the
initial-evidence selection. Resume, memo replay, projected arm membership
and reimport of the same evidence never create a new `trial_id`; a
genuinely fresh run in another campaign is a new trial even when its local
`evaluation_id` equals an earlier one. Hosted model revisions stay
`unavailable` and are not part of any identity.

## Persistent Evidence Store

A configured durable root, experiment-owned and shared by successive
campaigns. It is neither runtime memo state nor a mutator-visible archive:
it is masked from mutator sessions like the evidence root and added to the
contamination scan patterns of the
[driver's hygiene table](orc_structural_search_driver.md#evaluation-hygiene).
Immutable source manifests and raw evidence references live here, outside
disposable task clones; run records are referenced by path, never copied.

Records are append-only, versioned JSONL in the existing log conventions
(`records.append_record`, `records.read_records`); one writer at a time,
enforced by a lock file under the root; indexes are derived and rebuildable
from the records and are never authoritative.

| Record | Carries |
| --- | --- |
| `subject` | A registered candidate: `candidate_id`, parent, source manifest references, skeleton hash, allocation policy set, behaviour descriptor, registering campaign |
| `trial` | One launch: `trial_id`, `campaign_id`, `evaluation_id`, run id and state directory, task, split, replicate, `context_key`, outcome, consumption or `unavailable`, incident and retry fields, receipt references |
| `assessment` | A quality value for a trial, ingested only through `scoring.read_pool` (criterion hash check, qualification proof, the harness clone-id join; a pool `read_pool` refuses is refused, and superseded attempts receive no row): evaluator and criterion SHA-256, pool and clone ids, the proof hash, the split's access class |
| `exposure` | Written on actual use only: `adaptive` for the adaptive packages at campaign start, `validation` when the validation stage launches, `sealed` when `open_sealed` runs; a declared but unused role is not an exposure |
| `disposition` | A superseding record: contamination, invalidation, correction or a sealed-split opening, with the reason and the records it supersedes; evidence is never deleted |
| `campaign` | Registration, context tuple, policy parameters, budget declaration, warm-start evidence selection with its original acquisition cost |
| `checkpoint` | Written atomically (temporary file, rename): archive membership, reservoir state, RNG state, the ingestion position per log and the ledger index already committed |

Minimum operations: register a subject; ingest an observation idempotently
(keyed by `trial_id` and record kind; a repeated ingest is a no-op); query
compatible evidence by `candidate_id` and `context_key`; derive an estimate
(Estimates And Attribution); checkpoint and resume a campaign. No cross-file
transaction and no second memo are introduced: a checkpoint references
committed ledger and evidence records, and derived views are rebuilt from
them. Split access rules persist across campaigns through two operations:
`exposure(store)` returns, per task package SHA-256, the roles it has
actually held and the campaigns that held them; `check_split_roles(store,
adaptive, validation, sealed)` runs at campaign start, at validation setup
and before a sealed opening, and compares the criterion's declared roles
against prior actual exposures: an `adaptive` exposure anywhere refuses the
validation and sealed roles; a `validation` exposure refuses the sealed
role; a `sealed` exposure refuses every role except a second sealed
assessment of the same frozen study, which `open_sealed` itself refuses.
Two campaigns under one criterion may therefore declare the same
validation and sealed packages and both start; validation runs once and the
sealed package opens once. A sealed opening is a disposition record.

Footprint: at most one new module for the campaign and evidence store; the
driver, `mode1`, `adaptive` (parent selection, feedback, judged
generations), `judging`, `scoring`, `three_arm`, `ledger`, `metering` and
`records` pieces are reused, not duplicated.

## Campaign Protocol

A campaign is registered with its frozen context, policy, budget, seed set,
run seed and initial evidence, then runs generations until a stop rule
fires:

```python
state = store.resume(campaign_id) or store.start(campaign_id)
while not stopped(state):                       # budget, futility, invalid evidence, infrastructure
    parents = policy.draw(state.pool, state.rng, episodes_per_generation)
    for parent in parents:
        brief = diversity_brief(parent, state.evaluated_summaries)
        child = run_episode(parent, brief, condition="module")   # driver; admission unchanged
        if child.accepted and not revisit(child, state):
            trials = evaluate(child, adaptive_tasks)             # public runs, one per task and replicate
            store.ingest(trials)
    store.ingest(judge_generation(...))         # per generation, blind, anchors as today
    state = rebuild(store, campaign_id)         # archive, frontier, reservoir from this campaign's records
    store.checkpoint(state)
```

Per-child ceiling: the criterion's `envelope.child_planned_maximum` bounds
the planned provider-call maximum of any child (`ledger.planned_calls`); a
child above it is rejected with `planned_maximum_exceeded`, which counts
toward the futility rule like any rejection. The ceiling restricts the
search space and is recorded as such; its purpose is budget predictability,
since the whole-batch pre-check reserves every job's planned maximum before
a launch and an unbounded child would make the cap unsizable.

Trial identity follows Identities: every launch is one `trial_id`; an
incident resume keeps its `evaluation_id` and `trial_id`; a quota relaunch
is a new attempt and a new `evaluation_id` under the same job, so a new
`trial_id`, and the superseded attempt receives a disposition while its
consumption still counts. Interrupted attempts retain their measured
consumption and follow the driver's incident retry and disposition policy.

Checkpoint and resume: a checkpoint is written after every generation and
after every ledger settlement (an evaluation or a judge batch). Resume
reads the checkpoint, replays nothing, re-ingests nothing before the
recorded ingestion position and continues from the recorded RNG state, so
committed decisions are preserved and a restarted campaign draws the
parents it would have drawn. A campaign killed mid-generation completes
that generation from the log: episodes and evaluations already logged are
never repeated (job keys and `trial_id`s), the remaining work runs, and the
checkpoint is then rewritten. A checkpoint never inspects validation or
sealed outcomes.

Dispositions supersede: a contaminated, malformed or invalidated trial
ceases to contribute to estimates, frontiers and the reservoir when derived
views are rebuilt; the original record and its reason stay.

Warm start: a campaign may begin from whole-program evidence already in the
store only under equal `context_key`. Warm-start evidence keeps its
original campaign's acquisition cost, recorded separately and reported
beside the campaign's own budget. Compared policies start from identical
initial evidence, or the report discloses and accounts for the unequal
prior investment.

Stop rules, predeclared per campaign and recorded as the checkpoint's
`stopped` reason: the planned horizon; the futility rule (Diversity
Pressure And Revisits); the ledger's hard call cap; quota exhaustion; the
per-campaign wall-clock ceiling (generation time, quota pauses excluded);
invalid evidence (a generation pool whose calibration verdict fails the
criterion's control margins or spread limit stops the campaign and attaches
an `invalidated` disposition to that generation's assessments, since no
uncalibrated evidence may be spent on; an unadjudicated contamination or a
malformed ingest likewise); a second judge incident; and persistent
infrastructure failure at a predeclared count. An early stop is valid; an
interrupted campaign is reported incomplete, and measure-free from an
invalidation onward; no horizon is extended after outcomes are seen.

## Breeding Pool And Parent Policies

Two structures, rebuilt per campaign from the store after every generation
(`rebuild(store, campaign_id)`). A rebuild sees the campaign's recorded
initial-evidence selection (the shared warm start), its own evaluated
children and its current generation's scheduled children, never a sibling
campaign's children; estimates still pool by `context_key` across
campaigns, but selection, briefs and stop rules see only the campaign.

1. **Results archive.** Every admitted, evaluated candidate in this
   campaign, initial evidence included, with its evidence; its frontier is
   the driver's
   [objective](orc_structural_search_driver.md#objective-selection-and-local-observations)
   (tolerances, quality floor, cost `unavailable` off the frontier).
2. **Breeding pool.** A bounded frontier subset (the driver's spread rule
   and `ARCHIVE_SIZE`) plus a bounded reservoir (`RESERVOIR_SIZE`) of
   non-frontier candidates, neutral or worse, dominated, below the floor or
   cost-unavailable, provided they are fully valued on the matched adaptive
   support and carry no disposition. Admission is on evaluation; eviction
   when full follows the frozen rule (oldest first unless the criterion says
   otherwise). Reservoir membership conveys no deployment endorsement, and
   evidence is preserved when a parent leaves the pool.

Two parent policies, compared at equal total budget from identical initial
evidence, each with the same mutation facilities, task set, envelope,
seeded RNG scheme and stop rules:

| Policy | Parent draw |
| --- | --- |
| Frontier-only (baseline) | Uniform over the frontier subset |
| Mixture | With the frozen `exploration_fraction` (a fixed minority of draws), uniform over the reservoir; otherwise uniform over the frontier subset; an empty reservoir falls back to the frontier draw and the fallback is logged |

The criterion freezes `RESERVOIR_SIZE`, the admission and eviction rule and
`exploration_fraction` before any campaign. Frontier-only evolution is a
credible baseline: many failed proposals followed by occasional direct
improvements can accumulate progress. The reservoir tests the additional
hypothesis that useful descendants sometimes need dominated parents; it is
not assumed superior. No fitted search-value predictor exists in C1.

Every proposal still receives whole-module context, may compile and repair
within its episode and submits one final child; every executing child
passes full admission. Exploration relaxes no resource limit and makes no
metadata executable authority. Final promotion is the driver's final-choice
rule over the validation split with the reference seed, then the sealed
holdout opened once; adaptive retention and final promotion are distinct
decisions in the records. The validation split is mandatory for both: a
qualified validation package disjoint from the adaptive tasks and from the
sealed package is a gate (Staging And Gates); without it, campaigns may run
and be reported descriptively (adaptive trajectories, endpoints at the
budget cuts), but no final choice is made, nothing is promoted, the sealed
split is not opened, and the report says so. Successor criteria are
versioned; historical criteria and reports stay frozen; no calls-only
selection returns through a compatibility fallback.

## Diversity Pressure And Revisits

The live three-arm run accepted 18 of 18 proposals that converged on one
implement-check-repair idea, yet those 18 children had 17 distinct
skeletons
([Phase 1 report](../reports/2026-10-18-orc-structural-search-phase1.md#three-arm-readout)):
the convergence was semantic, not syntactic, and the revisit key below
would have flagged at most one of them. Diversity pressure therefore rests
on the brief; the revisit and futility rules only refuse to pay for exact
or skeleton-level repeats, and no mechanism guarantees semantic novelty.

- **Brief summaries.** Each proposal brief carries controller-selected
  structural summaries of the children already evaluated in this campaign,
  initial evidence included and never a sibling campaign's children:
  skeleton-level descriptors (form heads and arity outline, control heads,
  provider roles, loop presence, allocation policy set) and a coarse
  `idea_key` (the control-head multiset, the provider-role sequence and
  whether a check gates a repair), with the instruction that the proposal
  must differ structurally from them. The `idea_key` feeds the brief's
  "already tried" list and a predeclared convergence diagnostic, the share
  of this campaign's evaluated children per `idea_key`; it never blocks an
  evaluation. The
  brief never carries evaluator artifacts, scores of other candidates,
  validation or sealed outcomes, or any path under the evidence or store
  roots; the parent's own evidence stays the only feedback, as under the
  historical mode 2.
- **Revisit rule.** The match set is every candidate already evaluated or
  scheduled in the current generation in this campaign, initial evidence
  included, never a sibling campaign's children. A child whose `program_digest`
  equals one of theirs, or whose skeleton hash and allocation policy set
  both equal one's, is a revisit: logged with the matched `candidate_id`,
  not re-evaluated, and counted toward the futility rule. The `subject`
  record carries the policy set and a skeleton maps to every policy set
  seen with it, so a same-skeleton child with a changed policy set is a
  `policy_only` child under the driver's endpoint classes and is evaluated.
- **Futility rule.** One rule, frozen in the criterion as `consecutive`
  (illustrative value 4): the streak counts revisit, rejected and exhausted
  episodes; an incident neither counts nor resets it; a fresh evaluated
  child resets it; reaching `consecutive` stops the campaign.
- **Behaviour descriptor.** Recorded per evaluated candidate for reporting
  only, and the only semantic signal: realized provider calls (from
  `realized_perform_sites`), distinct provider roles, loop presence and
  `allocation_changed`. No quality-diversity grid in C1; one may be added
  later on evidence.

Reported per generation and campaign: distinct skeletons, the driver's
skeleton-only revisit rate and terminal-only share (`readout`, as in Phase
1), the campaign's revisit count under the digest-or-skeleton-plus-policy
key, the `idea_key` convergence share and the descriptor spread.

## Endpoints, Budget Accounting And Power

**Primary endpoints**, predeclared in the successor criterion and read at
fixed cumulative search budgets from checkpoints:

- best supported quality at each of a few fixed deployed-cost ceilings;
- cheapest deployed cost meeting each of a few fixed quality targets;
- the final independently validated frontier: finalists and the reference
  seed replicated on the validation split on matched tasks, then the sealed
  holdout opened once after selection and analysis freeze. The validation
  split is mandatory: without a qualified validation package there is no
  final choice, no promotion and no sealed opening, and the campaigns are
  reported descriptively.

The budget cuts are 50%, 75% and 100% of `B_plan`, the per-campaign
planned metered budget computed at freeze from the price table and the
planned calls and recorded in the criterion. The reading at a cut is the
last checkpoint whose cumulative metered cost is at or below it. Metered
cost is the primary axis, with calls and wall clock reported beside it. A
campaign with any unavailable receipt is not comparable at the cost cuts;
it is compared at calls cuts labelled a secondary proxy, valid only when
every call resolves to the admitted models at their fixed efforts, and
never silently. "Supported" means valued on the full matched adaptive
task-by-replicate support with at least the criterion's `min_trials`.
These cuts keep frontier point count from becoming the objective.
Secondary: improvements per episode, frontier entries, diversity and
descendant lineage (frontier contributions by ancestor and policy).
Adaptive frontier trajectories are recorded at checkpoints; checkpoints
never inspect sealed outcomes.

**Cumulative budget.** The union of a campaign's ledger entries: proposal
and repair calls, compile and evaluation overhead, judges, retries, failed
proposals and substantive human intervention (an intervention row with wall
clock and a note). Three columns stay explicit and are never summed into
one: priced provider compute (metered tokens under the criterion's frozen
price table), wall clock, and unpriced work. Missing receipts are
`unavailable`, never zero. Warm-start evidence keeps its original
acquisition cost apart.

**Power before spend.** The pilot plan predeclares, with this formula and
these inputs, the minimal detectable campaign-level effect, replicate
campaigns per policy, generations per campaign, episodes per generation and
the derived call budget with a hard cap:

- endpoint unit: one value per campaign (for example best supported
  quality at ceiling `c` at budget `B`), compared between `R` replicate
  campaigns per policy;
- per-evaluation spread `sigma_e`: pooled within-arm SD 0.93 and 1.20
  rubric points on Phase 1's two tasks, each on one degree of freedom
  ([per-policy results](../reports/2026-10-18-orc-structural-search-phase1.md#per-policy-results));
- a finalist's mean over `r` replicates has SD `sigma_e / sqrt(r)`; the
  campaign-level SD `sigma_c` is at least that, plus between-campaign search
  variance, which is unknown and is stated as an assumption;
- minimal detectable difference between two policies:
  `delta = (z_(1-alpha/2) + z_(1-beta)) * sigma_c * sqrt(2 / R)`, with
  `alpha` and `beta` predeclared;
- wall clock per evaluation: Phase 1's one-call catalog runs took 29 to 49
  min (1,754 to 2,947 s mean per policy) and its multi-call seeds up to
  4,718 s mean ([Phase 1 report](../reports/2026-10-18-orc-structural-search-phase1.md#per-policy-results));
  the three-arm Codex-coder subset took 908 to 1,072 s; the planning value
  for a one-call evaluation is 35 min, and a per-campaign wall-clock
  ceiling (generation time, quota pauses excluded) is predeclared from the
  per-generation figures: sequential episodes, evaluations at the
  configured concurrency with a barrier per generation, the judge batch and
  the hidden-acceptance pass;
- provider calls per evaluation `c_eval`: 1 at the parent's structure, up to
  the child's planned maximum (`ledger.planned_calls`) otherwise; acceptance
  rate `a` from Phase 1 and the three-arm run;
- calls per campaign:
  `G * E * (1 + a * T * r * c_eval) + judge batches per generation * judges * T + (F + 1) * V * r * c_eval` plus validation judging (no separate smoke: the warm start's first evaluation serves as the live smoke), for `G` generations, `E` episodes per generation, `T` adaptive tasks, `r` replicates, `F` finalists, `V` validation tasks; total = 2 policies × `R` campaigns.

If the affordable design cannot detect a plausible effect (at Phase 1's
spread the largest observed gaps were 1.13 and 2.00 points), the plan says
so and sizes a smaller descriptive pilot instead of hiding it. Every live
campaign is a separate owner approval under the model cap.

## Stage C2: Fragment Identity, Invocation Accounting And Context

Contract level; unselected. Implemented only when Staging And Gates selects
it, under its own plan. Nothing in C1 depends on it.

**Fragment identity.** `fragment_id` is a versioned content identity of one
supported authored subtree and its static composition contract: a hash over
normalized authored syntax with operation kind, canonical input and output
types, proven free-binding and capture contracts, fixed captured values and
the fingerprints of used resolved dependencies. Actual literals, prompt
bodies and provider policies are preserved; lexical binders are
alpha-normalized where binding identity is known. Changing a used prompt or
helper changes the identity; moving the same closed fragment or editing an
unrelated sibling does not. The skeleton hash erases meaningful terminals
by construction and is unsuitable. Syntactic identity is conservative, not
a proof of semantic equivalence: behaviourally identical rewrites may
receive different IDs. The manifest's list of in-scope bindings is not a
free-capture proof: free bindings come from compiler identities or an
explicit complete binding contract for the supported subset; ambiguous
closure or dependency resolution reports `identity_unavailable`, never an
identity manufactured from matching text.

**Supported subset.** Whole programs are registered; nominated exact
authored `provider-result` expressions, non-generic authored procedure and
workflow bodies and direct call subtrees with resolved identity, bindings
and dependencies may be, explicitly per study. Registration implies no
executable transfer. Provider invocations are the first fully observed
class; composite bodies gain execution estimates only after their activation
boundaries, nested effect membership and result/failure joins pass the
Verification fixtures. Macro-generated forms, ambiguous specializations,
unsupported captures and pure or composition nodes without validated
boundaries stay unsupported or unobserved (the manifest's
[exclusions](workflow_lisp_source_site_inspection.md#34-exclusions) apply),
and memo effect records establish no source-branch coverage
([records](orc_structural_search_driver.md#records)). The contract is
complete accounting for every observed invocation of every nominated
fragment, not a score for every syntactic node.

**Invocation accounting.** `invocation_id` is the trial, the runtime owner
and activation path, the site and the visit; attempts are subordinate
records. An invocation attaches its observed return or local contract
result where available, terminal status and the actual included effect
receipts, with inclusive cost and constituent effect IDs. Retries count.
Nested subtrees overlap, so whole-run cost is the union of underlying
receipts, never a sum of overlapping fragment totals; wall-clock durations
likewise do not add across overlapping work. A missing boundary or receipt
yields `unavailable` or an explicitly labelled lower bound; a skipped
branch is `not_reached`, never a zero-cost success. Where the validated memo
view (effect identity, class, attempt count, status) cannot supply a
composite's boundaries, the need for neutral invocation-boundary evidence
is a separately scoped runtime change under invariant 3, never inferred
from effect events.

**Context and pooling.** Exact provenance (candidate and build, site,
caller, input and artifact fingerprints, task package, environment,
provider and model revisions, evaluator, criterion, split, envelope,
timestamps) is recorded apart from the compatibility key. Default pooling is
equality under a versioned context schema: task package and sampling
stratum, caller role and relevant upstream state or protocol, input and
output contract, resolved dependencies, model, effort and revision,
environment, evaluator and rubric, envelope. Input fingerprints are
preserved; an input-specific dimension is omitted only by an explicit
pooling rule naming the distribution estimated; context that cannot be
isolated partitions by the enclosing owner or candidate. Candidate IDs,
source coordinates and invocation ordinals never enter every key, so two
programs can share a fragment and a bucket with distinct provenance, and
different callers can share a fragment ID with separate estimates. An
unresolved hosted-model revision receives an evaluation epoch; an unchanged
alias proves no continuity. Similar-context transfer may later supply a
labelled prior with zero observed samples; no learned context model is
required.

## Estimates And Attribution

**C1 (normative when selected): whole-program evidence.** An estimate is a
query over the store for one subject under one context: a quality, cost,
latency and failure vector with uncertainty, from which the criterion
derives ranking and frontier membership. Estimates pool across campaigns
under equal `context_key` (whole-program evidence reuse); selection,
briefs and stop rules see only the campaign (Breeding Pool And Parent
Policies). Every estimate states its
subject, `context_key`, metric and estimator versions and contributing
`trial_id`s; its trial, attempt and task counts; its summaries with units
and uncertainty; its coverage, unavailable or censored quantities and
excluded evidence; and whether it is observed performance, an associated
outcome, intervention evidence or a prior. A subject with no compatible
trials returns `unobserved` with zero trials; absence of evidence is never
a poor score. Simple empirical summaries come first, uncertainty at the
independent trial and task level with the method recorded and insufficient
support marked; comparisons use matched task support or an explicit
weighting rule, and accumulation never silently changes the target
distribution. Failures follow the driver's rule (failed or envelope-timeout
trials score 0, other incidents are excluded, consumption is retained);
missing receipts are unavailable, never zero; whole-run cost is the union
of a trial's receipts. An edited candidate is a new `candidate_id` whose
parent's trials stay searchable through lineage and are never copied.
Search-value records (parent selections, mutation attempts, evaluated
offspring, descendant frontier contributions, with campaign, policy and
horizon) are lineage associations, not unbiased estimates of future
usefulness; they never modify observed execution fitness, and no fitted
predictor is used.

**C2 (conditional): fragment evidence.** Terminal whole-program quality may
be linked to every reached fragment as an **associated outcome**: not a
local quality score, not an additive contribution, not evidence that the
fragment caused success, and always linked to its one originating trial.
Nine visits inside one run are nine invocations and one terminal-quality
cluster, not nine independent measurements. A causal claim requires a
declared intervention: replace or remove a fragment while controlling other
changes, evaluate matched tasks with replication, and report uncertainty and
interaction scope. A local evaluator may supply a separate metric under its
own versioned contract; it never substitutes for whole-program validation.
An edited fragment gets a new ID; an unchanged fragment keeps its evidence,
and a changed context may prevent pooling. Available successful fragments
are never averaged while their unobserved failures are hidden.

## Boundary Compliance

Against the [invariants](workflow_lisp_program_search_boundaries.md) as
amended 2026-10-19:

| Invariant | This design |
| --- | --- |
| 1 Immutable generations, full compiler, registered runs, no eval | Unchanged from the driver: every child is a new snapshot through the ordinary pipeline, every trial a new public run; the store imports nothing into executing code |
| 2 Provider output is untrusted data | Unchanged: a proposal is data until validation and the compiler accept it; brief summaries are text, never executable authority |
| 3 Neutral substrate versus feature | The store, archive, reservoir, policies, estimates and lineage live under `experiments/orc_structural_search/`; `orchestrator/` receives no populations, scores, selection policy or fitness; a proven need for neutral invocation-boundary evidence is a separately scoped runtime change, never inferred from effect events |
| 4 Whole-program evidence is deployment authority (amended) | Frontier membership, finalist selection and promotion bind to whole-program trials; reservoir retention, parent sampling and (C2) proposal targeting may use dominated candidates, contextual fragment observations and search-value records, which cannot alone establish whole-program quality, validate a replacement or authorize promotion, and carry explicit provenance, context, uncertainty and noncausal limits |
| 5 Evidence separation | Adaptive, validation and sealed splits stay disjoint across campaigns through the store's exposure classes; the sealed holdout opens once after selection and analysis freeze and never feeds mutation, selection or evaluator tuning |
| 6 Honest security boundary | Unchanged: ordinary configured sessions under the harness shims, sandbox and scan; the store root is masked and scanned; hygiene, not isolation |
| 7 Typed-operation parity without kind erasure | Matching fragment types never establish substitutability; C2 identities carry the operation kind; no runtime callable or effect-erasing adapter |
| 8 Role-separated prompt identity | Prompt identity includes used resolved dependencies; attempt-rendered bytes stay execution provenance; C2's `fragment_id` enters a prompt only when the compiler proves it a resolved free binding |

Rationale for the amendment. The replaced invariant 4 read: "Selection and
promotion judgments bind to evidence about complete, certified, executed
candidates. Local attribution (per-fragment, per-site, per-visit signals)
is diagnostic only and never selection or promotion authority on its own."
Invariant 3 already permits neutral evidence
capture and places fitness in the feature layer. Merely storing diagnostic
fragment evidence would not require an amendment; using local evidence and
dominated candidates for breeding does. The amended text permits local
evidence to influence acquisition decisions (what to propose from, which
parent to draw, what to retain for exploration) and keeps whole-program
evidence as the only authority for the frontier, finalists and promotion.
The driver design's
[amendment section](orc_structural_search_driver.md#amendment-to-the-boundary-invariants)
records the 2026-10-18 amendment of invariants 1 and 6, which this design
inherits.

## Staging And Gates

**Offline C1 (no provider spend; scripted providers through the actual
compiler, public execution and production ingestion).** The store, campaign
protocol, breeding pool, both policies, diversity pressure and the revisit
and futility rules, the cumulative budget readout and the endpoint
computation from checkpoints; at most one new module; the Verification
fixtures passing. Launchers refuse fresh adaptive work until this stage is
delivered and the successor criterion is frozen.

**Live C1 campaign gate.** This list is the single authoritative gate list;
the roadmap's Phase 2 Gates and the pilot plan's preconditions reference it
and add nothing. Each item is recorded in the ledger with its evidence
before any provider spend:

1. The accepted measure: the
   [measurement plan](../plans/2026-10-19-orc-structural-search-measurement-plan.md)'s
   Step A passed, or the owner-approved A′ passed under that plan's
   predeclared revision, with B2 keeping it calibrated; C1's criterion
   inherits the accepted measure's rubric.
2. Every package the study uses covered by a qualification rule file: the
   frozen `calibration-amends-5.json` covers rungs 2 and 4 only, so any
   further package (the sealed package, the validation package) needs the
   successor amendment `amends_6` (same k, thresholds, borderline and stop
   rules; scope the named additional packages; runtime validity this
   study's frozen commit; owner-accepted before its spend), and the V2
   receipt takes one rule file per package
   (`family.rules: {package_sha256: {file, sha256}}`).
3. Metering wired with the price table frozen in the successor criterion,
   and `B_plan` recorded there.
4. A sealed package that, by the exposure record, never held any role in
   the store beyond being a holdout, as `check_split_roles` shows.
5. A qualified validation package, disjoint from the adaptive tasks and the
   sealed package (rung 3 after a fresh qualification under `amends_6`, its
   two historical samples not carrying over, or another package qualified
   under `amends_6`), its estimated cost in the owner's worst-case total,
   and `check_split_roles` showing no prior `adaptive` or `sealed`
   exposure. Without it, campaigns may run and be reported descriptively,
   but no final choice, promotion or sealed opening follows.
6. The `module` condition's offline tasks delivered; the pilot mutates under
   `module` ([module gate](../plans/2026-10-19-orc-structural-search-module-rewrite-plan.md#gate-for-a-live-module-arm)).
7. Mutator isolation (`COMPARE_HIDE` masking) covering the store root and
   every earlier evidence root.
8. This amendment accepted: roadmap, boundaries document, driver design,
   capability matrix, design README and experiment README updated together.
9. The model cap of `AGENTS.md`'s experiment rules: every route, judges,
   reviewers, coders, nested CLI processes and native agents included, at or
   below Sonnet/Terra, with the admitted IDs as the criterion's `models`
   allowlist (`claude-sonnet-5-5` and `gpt-5.6-terra` at adoption) and a
   guard refusing any other; Fable forbidden; every seed or parent a capped
   copy, historical seeds unchanged.
10. The pilot plan's predeclared power statement, horizon, checkpoints,
    replicate campaigns, stop rules, per-campaign wall-clock ceiling,
    `envelope.child_planned_maximum` and hard call caps sized to the
    whole-batch planned-maximum pre-check; an owner approval per live
    campaign. No uncalibrated experiment.

**C2 selection condition.** C2 is written as an implementation plan only
when C1 shows a frontier gain from the mixture at equal budget, or a
demonstrated proposal-targeting need that whole-program evidence cannot
serve. It is also the entry increment of the roadmap's Phase 4
compositional work. Until then fragment evidence is `unavailable` and
whole-program evolution stands alone.

**Beyond the pilot.** Proceed only when measured gains or a demonstrated
engineering benefit justify the next increment. If exploration adds cost
without improving the final frontier, keep the frontier-only policy. If
fragment attribution proves unreliable, keep whole-program evolution and
report fragment evidence as unavailable.

## What This Makes Harder

- Evidence compatibility is strict: any change to the model allowlist,
  price table, criterion, package set, envelope or runtime commit partitions
  the store, so cross-campaign pooling will be rare and warm starts need
  matching contexts.
- Campaign recovery adds a checkpoint discipline, a single writer and a
  rebuild step; attribution weakens, since the reservoir's value is a
  lineage association and `module` already trades attribution for larger
  proposals.
- Power is poor at Phase 1's spread with few replicate campaigns, so the
  first pilot is likely descriptive; a null result is a valid outcome.
- Skeleton-level revisits miss same-idea convergence (17 distinct skeletons
  among the 18 converged three-arm children), so diversity pressure rests
  on the brief and the `idea_key` diagnostic; no mechanism guarantees
  semantic novelty.
- Split exhaustion: every task exposed to a campaign is lost to later
  validation or sealed use, and the family has few qualified rungs; the
  model cap bounds policy variation to two admitted models, so structural
  variation carries the study.
- Sequential clone-per-trial evaluation stays slow and disk-heavy; a
  campaign of several generations runs for days; C2's identity and boundary
  work is substantial and may report `identity_unavailable` for most
  composites.

## Verification

Behavioural checks, no prompt-text assertions, scripted providers for every
offline fixture.

**C1 offline, required before the live gate:**

- Store: process A records trials and process B reopens the root and
  extends the same estimates; a repeated ingest, a resume and a reimport add
  no trial while a fresh run does; a disposition removes a trial from
  estimates, frontier and reservoir on rebuild while the record remains;
  different `context_key`s partition and equal keys pool, a two-replicate
  warm start with one-replicate campaigns included; a second writer and a
  reused campaign label are refused; an assessment reaches the store only
  through `read_pool`, and a pool it refuses is refused; the store root is a
  scan pattern absent from every brief and workspace.
- Protocol: a campaign killed between generations, and one killed
  mid-generation, resume from the checkpoint and the log with identical
  archive, reservoir and parent draws, no repeated episode or evaluation
  and no duplicated trial; an interrupted attempt retains its consumption;
  `check_split_roles` refuses a package once actually exposed as adaptive
  for the validation or sealed role, a validation-exposed package for the
  sealed role and a sealed-exposed package for every role, while two
  campaigns under one criterion declaring the same validation and sealed
  packages both start, validation runs once and the sealed package opens
  once; two interleaved campaigns under one criterion never see each
  other's children in a brief, the revisit set, the frontier or the
  reservoir, while their estimates pool by `context_key`; a child above
  `envelope.child_planned_maximum` is rejected with
  `planned_maximum_exceeded` and counts toward futility; warm-start cost is
  reported apart; a generation pool failing
  its calibration verdict stops the campaign with an `invalidated`
  disposition on its assessments; launchers refuse a successor criterion
  without metered cost, a quality floor, `B_plan`, the wall-clock ceiling
  and the frozen policy and futility parameters.
- Stepping stone: a deterministic fixture exposes only the transitions
  A → B → C, where B is dominated by A and C improves the frontier; the
  mixture policy breeds B and reaches C, frontier-only never evaluates C;
  both spend the same planned budget from identical initial evidence. The
  fixture proves reachability and accounting, not benefit.
- Diversity and revisits: a scripted structural repeat yields a logged
  revisit, no evaluation and a futility count; `consecutive` revisits,
  rejections and exhaustions in any mix stop the campaign with a recorded
  reason, an incident neither counts nor resets, and a fresh evaluated
  child resets; a same-skeleton child with a changed policy set is
  evaluated as `policy_only`; a fixture of distinct skeletons sharing one
  `idea_key` is evaluated, raises the convergence share and never stops the
  campaign (the known gap, reported as such); the brief carries summaries
  and `idea_key`s of evaluated siblings and never their scores, validation
  or sealed outcomes or evidence paths; the behaviour descriptor is recorded
  for every evaluated candidate.
- Endpoints: best quality at fixed cost ceilings and cheapest cost at fixed
  quality targets are computed from the last checkpoint at or below each
  cut of `B_plan`; a campaign with an unavailable receipt is excluded from
  the cost cuts and reported at calls cuts labelled a secondary proxy; cost
  `unavailable` or a floor miss keeps a candidate off the frontier and
  reported; without a validation package the readout is descriptive and the
  final choice and sealed opening refuse; the final-choice rule refuses
  without a criterion hash; the finalizer refuses while the successor route
  is incomplete.

**C1 live (the calibrated pilot):** matched independent campaigns per
policy; campaign frontiers compared at equal cumulative budgets with
uncertainty, failures and prior evidence costs; finalists validated after
generation freezes, the reference on matched tasks, the sealed holdout
opened once; a null result reported without extending the horizon.

**C2 (conditional):** the same closed fragment in two candidate locations
has one ID; alpha-renaming preserves it; a used literal, prompt or capture
change alters it; unresolved closure is `identity_unavailable`; two calls to
one fragment create distinct visits; a skipped branch is `not_reached`;
nesting deduplicates cost; retries count; incomplete joins stay unavailable;
nine visits in one trial contribute one terminal-quality cluster; a
malformed observation is refused at ingest.
