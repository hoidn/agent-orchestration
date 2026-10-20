# ORC Structural Search Roadmap (R3 Implementation Sequence)

Status: proposed implementation roadmap for research unit R3 (search and
representation), drafted 2026-10-18 against `main` at `90ae778c` (target 2.39
merged) and revised after an independent design review. Phases 0 and 1 were
selected on 2026-10-18 under the owner's directive to execute the roadmap,
with the allocation below. Phase 1 ran on 2026-10-18 and 2026-10-19, its compile-only
three-arm readout included (measure-free under the calibration rule; [Phase 1 report](../reports/2026-10-18-orc-structural-search-phase1.md#three-arm-readout)). Its decision rule fired
`anchors_inverted`, and neither task separated within tolerance, so Phases 2–5
are not selected for family (a) ([Phase 1 report](../reports/2026-10-18-orc-structural-search-phase1.md)). It replaces an earlier
external draft ("ORC as a Searchable Workflow Language", 2026-10-16, not in
the repository).

Authorities: the [research charter](2026-09-08-orc-research-charter.md) owns
the questions; [Experiment O](../design/orc_reuse_introspection_search_experiment.md#experiment-o--program-space-then-search)
and the demonstration plan's
[Conditional Task 6](2026-09-08-orc-research-demonstration-plan.md#conditional-task-6--test-search-and-representation-value)
own the search-evidence requirements; the
[program-search boundary invariants](../design/workflow_lisp_program_search_boundaries.md)
constrain every design in this space and must be amended explicitly before a
design departs from them; the
[evolution roadmap](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#current-research-sequence)
places R3 after R2. Two companion designs carry the contracts: the
[source-site inspection](../design/workflow_lisp_source_site_inspection.md)
(a read-only compiler-side manifest) and the
[structural search driver](../design/orc_structural_search_driver.md)
(proposal interfaces, edit validation, execution, records, controls and the
rationale of the boundary amendment applied 2026-10-18). Nothing here is copy-safe; the offline
apparatus status is in [Phase 0 Status](#phase-0-status). Use
today: `experiments/compare/` for fixed-workflow comparisons and the REPL
`:info` / `:type` / `:source` commands for static inspection.

## Thesis And Question

Agent-workflow heuristics name promising strategies without fixing their
implementation: planning granularity, context transfer, review placement,
repair and escalation interact and depend on the task distribution and
budget. Treat the orchestration strategy as an executable program and search
over it. ORC's role is to make that program space inspectable, editable,
checkable, executable and evaluable: S-expressions expose subtree boundaries,
the compiler gives those subtrees binding, type, dependency and effect
meaning, the runtime executes accepted programs under existing contracts, and
whole-workflow evaluation supplies the objective.

> Does compiler-assisted search over typed, composable workflow programs
> discover better orchestration strategies, or discover them more
> economically, than credible manual and Python-based alternatives?

The genetic-programming reading sharpens the bet. Compiler-certified
immutable candidates are strongly typed GP under another name. A typed tree
genome allows proposal interfaces narrower than "rewrite the program" or
"emit a textual diff": point at a typed site and fill it, or pick a named
structural transform the compiler applies. The wager is that
operator-design freedom beats proposer fluency in the host language. A first
bounded answer comes from three arms on one benchmark workflow, one model
and one task family: Python diffs, Lisp whole-program edits, Lisp
locus-plus-fragment edits. The convergence risk is documented: LLM mutation
chains over a DSL revisited a small set of structural forms and varied mostly
terminals ([Gurkan, Stonedahl and Wilensky, 2026](https://arxiv.org/abs/2606.05408);
cited, not reproduced here), so structural diversity is measured from the
first search run.

Authored source is the genome. The typed program, WCC and closed program are
derived per candidate and never edited or printed back; classical subtree
operators over lowered forms wait for a printer with round-trip evidence,
which does not exist.

## Baseline Facts And Constraints

Checked against code at `90ae778c`. Each fact constrains the phases below.

| Fact | Constraint |
| --- | --- |
| `explain` and the six `compile --emit-*` flags are still parsed and refuse (`orchestrator/cli/commands/explain.py`, `orchestrator/cli/commands/compile.py`) | Nothing is designed around them |
| `compile` writes `closed_program.json` and `manifest.json`; the manifest holds `build_key`, `program_digest`, target, entry, source paths and a site count; `closed_program.json` carries `configuration` and `@` provenance (`path:line:col` start plus definition form path) stripped from `program_digest` | Source joins use the in-memory build and the `@` provenance, not the manifest |
| The checker keeps no span-to-type table; per-node WCC metadata is produced per preparation through `_command_wcc_body` and not retained; `AuthoredDirectCall` records procedure and workflow calls only | The manifest needs a retention or re-elaboration change (prerequisite P-1 in the inspection design) and excludes pure-helper calls in its first version |
| `trial` SDK symbols are gone; the `trial` subcommand and form refuse; confined `run-ref` children are command-only (`refuse_confined_run_ref_sites`) | No trial revival; candidate provider calls stay on the ordinary route |
| A closed-program site row is `[owner definition, label path]`; runtime identity adds the activation path and loop ordinals | A candidate-local site locator is a separate derived identity |
| There is no run registry; a run is a directory under `--state-dir`; the workspace lock admits one active run per working directory; parent/child linkage exists only for `run-ref` children | One fresh clone per evaluation, run id as the join key, lineage in the driver's log; invariant 1 needs an explicit reading for external controllers |
| The evaluated runtime persists no usage; `experiments/compare` collects none; `run-ref` accounting is `UNKNOWN`; OMP usage cannot be summed from a missing field, since `validate_usage` in `orchestrator/providers/omp_protocol.py` rejects any closed assistant message lacking `totalTokens` or `cost.total`; Claude and Codex session parsing lives in `experiments/orc_structural_search/metering.py` | Budget units are episodes, provider calls and wall clock, and are not the objective's cost axis (metered cost; Decision Criteria); dollars only where coverage is complete |
| `experiments/compare/` is implemented: PATH shims for `claude` and `codex` under bubblewrap, a model guard refusing Fable, a contamination scan, a blind pool and `score.orc`, a frozen hashed criterion; there is no OMP shim | Reused for hygiene; mutators run through shimmed CLIs; an OMP shim is a prerequisite before OMP sessions |
| Experiment O's catalog `workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc` is at a retired target; the linear-classifier hard-oracle seed lacks a verified green baseline | Both are Phase 0 cost items, not assumed assets |
| Owner rules: no Fable model in any experiment call; tasks calibrated before treatment runs; missing receipts are unavailable, never zero | Adopted for every arm, control, judge and mutator |
| The boundaries document requires an explicit amendment before a design departs from invariants 1 and 6, and the typed-program-gates design adds a "generational child runs only" rule | Phase 0 gate: owner-accepted amendment, applied in place 2026-10-18, with its rationale in the driver design |

Consistency items surfaced by this review, to be filed with their owners as
spec-versus-code contradictions outside this roadmap's gates: `specs/cli.md`
still says the `run_trial_entry` SDK refuses although the symbol no longer
exists. The experiment design's availability table, which listed E2 `trial`,
`run_trial_entry`, the IR/source-map exports and `explain` as available, is
corrected in the change that adds this roadmap.

## Decisions Carried Forward

1. The optimizer and evaluators run in Python; candidates are ORC programs.
2. Mutate authored source, then run the full ordinary compiler. Never mutate
   executing programs or lowered artifacts.
3. Compiler context comes from the in-memory build; no second type checker,
   no string inspection of source. The orchestrator-side footprint is one
   read-only manifest module plus whatever P-1 retention needs.
4. Proposals come from ordinary configured coding-agent sessions through the
   shimmed CLIs with their normal tools. A proposal interface narrows the
   edit scope, never the agent's facilities. No Fable model in any call.
5. Complete-workflow evidence selects. Local scores target and explain.
6. Finite catalog, enumeration and unguided proposal sampling precede any
   adaptive method; adaptive search needs a useful-search-space result first.
7. One task family, sequential evaluation in separate clones, frozen external
   contracts and a small archive.
8. Structural variation and measured skeleton diversity precede fragment
   extraction, certified transforms and crossover.
9. Reuse compile, public `run` and `resume`, run records, provider adapters
   and the comparison harness. No `trial` revival, no flat-IR route, no
   `run-ref` provider children, no C2 adapters, no in-language `eval`.
10. The proposal interface is an experimental factor: I1 whole-file edit, I2
    locus-plus-fragment, I3 matched Python diff; I4 named certified
    transforms deferred to compositional work.
11. The boundary amendment precedes implementation; it was applied in place
    in the boundaries document on 2026-10-18 and the driver design carries
    its rationale.

## Search Space And Proposal Interfaces

The first neighbourhood exercises model allocation and feedback placement:
strong plan then cheap implementation; cheap implementation then tests then
strong diagnosis on failure; per-subtask planning; implement, review and
revise on request; direct implementation. These are examples, not a menu;
the optimizer may choose DIRECT, and added stages earn no intrinsic reward.

Mutable in the first study, as declared in the driver's experiment
configuration: definitions in the named mutable files, their sequencing,
conditionals, compatible calls and supported bounded repetition; provider
selection within the configured set; prompt wording only in prompt-only and
joint conditions; fresh local helpers declared in the same change. Frozen:
the exported entry signature, the task and result protocol, the evaluator,
command interfaces, imports, type declarations, tools and the environment.
Effect summaries bound kinds of operations, not call counts, cost,
termination or correctness; runtime envelopes stay necessary.

| Interface | Agent receives | Agent returns | Validation | Needs |
| --- | --- | --- | --- | --- |
| I1 whole-file | workspace, objective, mutable scope, feedback | edited mutable file(s) | frozen-surface checks over parsed forms, then full compilation | no manifest |
| I2 locus-plus-fragment | the same plus one manifest site with its typed context | one replacement expression plus declared helpers | one-site transaction with slot result-type equality, then full compilation | the manifest |
| I3 Python diff (control) | matched typed Python workflow sharing adapters, prompts, evaluator, tools, budget | textual diff | AST scope validation plus a named type checker | the Python workflow |
| I4 certified transforms (later) | named transform catalogue | a transform and target | compiler-owned rewriting | compositional work |

## Phases

| Phase | Work | Completion evidence |
| --- | --- | --- |
| 0 Governance and integration spike | Owner selection and allocation after R2's own selection; boundary amendment accepted; task family chosen per the charter and calibrated; catalog ported to 2.39 or re-authored; green baseline where family (b) is chosen; harness extension (arm spec from a candidate root, a generic-command arm, scan patterns for the archive, lineage and score records, holdout roots and other candidates' trees); clone-per-evaluation launch through public `run`; metering coverage measured per provider; one agent episode cost-calibrated; P-1 feasibility fixture | One authored candidate compiles, runs through the admitted route in a fresh clone and receives an independent score; a written list of API gaps, metering coverage and prerequisite costs |
| 1 Catalog, enumeration and unguided I1 search | Frozen-surface validation and candidate snapshots in the driver; the finite authored catalog enumerated; equal-budget unguided I1 proposal sampling with no feedback; the three-arm compile-only readout (acceptance per episode, edit locality, distinct skeletons) with REPL-derived site facts for the locus arm; skeleton-diversity and collapse readout; JSONL lineage | Structurally distinct candidates with measured whole-run quality and cost differences, or the recorded finding that the neighbourhood is tiny or flat; the compile-only three-arm readout and a collapse verdict per interface |
| 2 Manifest, I2 and adaptive search | The inspection design's manifest with P-1 resolved; the I2 one-site transaction; the adaptive loop with incumbent, archive and contextual site feedback, enabled only on Phase 1's useful-search-space result | Reproducible adaptive search over one family; at least one genuine control-flow change; complete candidate, cost and failure history; diversity and revisit rates against Phase 1 |
| 3 Comparative evidence | Three-arm interface test (I3, I1, I2) with its pre-registered endpoints; then the controls the claim requires, including the protocol delivered as an agent skill; supplied-assistance ablations; frozen sealed assessment | A report separating structural gains, search-efficiency effects, representation and integration effort, and uncertainty |
| 4 Compositional search | Fragment contracts with explicit inputs, hygienic insertion, capture-aware extraction for a documented subset, I4 certified transforms, crossover | One extracted composition transfers between workflows and survives complete-program evaluation |
| 5 Broader utility | Measured bottlenecks only: parallel evaluation across clones, richer adaptive policies, scientific transfer, protocol evolution, caching | Evidence supports each expansion |

### Phase 0 Status

The [offline apparatus plan](2026-10-18-orc-structural-search-phase0-offline-plan.md)
(mode-1 driver, edit validation, candidate snapshots, evaluation, records,
metering) and the
[source-site feasibility plan](2026-10-18-source-site-inspection-feasibility-plan.md)
(read-only manifest module) are implemented and tested with scripted
providers only. P-1 and F-a passed. Selection, the boundary amendment and
the allocation were recorded on 2026-10-18; the task-family choice and every
live run follow the
[live Phase 0 gates and Phase 1 plan](2026-10-18-orc-structural-search-live-phase1-plan.md), whose allocation, all limits
first-exhausted, is:

| Limit | Value |
| --- | --- |
| Provider calls, all roles (arms, judges, mutators, smoke) | 160 |
| Concurrent evaluations | 4 |
| Per-evaluation wall clock | 14,400 s (the harness's executor ceiling) |
| Per-episode wall clock | 3,600 s |
| Models | `claude-opus-5-5`, `claude-sonnet-5-5`, `gpt-6-sol`; never Fable |

### Phase 0 Gates

- R2 task-family qualification keeps its own selection, review and
  allocation; this phase starts after it and inherits its family, or the
  owner records a merge of the two decisions.
- The owner accepts the boundary amendment, covering invariant 1 for
  externally launched registered runs, invariant 6 for ordinary configured
  sessions under experiment hygiene, and the scope of the typed-program-gates
  rule; the driver design carries the rationale. Met 2026-10-18: applied in
  place in the boundaries document.
- Task family: review/planning improvement on the comparison-harness family,
  or hard-oracle repair (`examples/demo_task_linear_classifier_port/` with
  `orchestrator/demo/evaluators/linear_classifier.py`, or a small Python
  repair family with independent tests). A family every seed solves or every
  seed fails is uninformative; the harness calibration rule applies where its
  reviewer measure is meaningful. Family (b) needs a verified green baseline
  and enough distinct defects for three disjoint splits; that authoring cost
  is estimated before the choice.
- The Experiment O catalog is ported to 2.39 or replaced by an authored 2.39
  catalog of the seed policies; its cost is part of this phase.
- Launch path demonstrated: fresh clone under the harness layout rules,
  pinned revision, recorded environment manifest, `python -m orchestrator run`
  with `--state-dir <work root>/runs/<evaluation_id>` (run state under the
  sandbox-visible work root, outside the clone: a stated deviation from
  in-clone run state, kept so records survive teardown), run id retained,
  cancellation and teardown verified for the chosen runner. The evidence
  root, outside the work root and never shown to an agent, holds the log,
  the candidate archive and the readout.
- Mutator and arm sessions use the shimmed `claude` and `codex` CLIs; OMP
  sessions wait for a shim with the same guard.
- Metering: receipt availability measured per provider; missing usage
  recorded as unavailable; the budget unit for comparisons fixed as
  completed episodes with provider calls and wall clock reported.
- P-1 and F-a fixtures from the inspection design: WCC node metadata is
  obtainable per owner at a measured retention or re-elaboration cost, and
  it yields span, type and scope that join to closed-program sites for a
  workflow owner and a procedure owner.

### Phase 1 Gates

- Frozen-surface validation rejects a change to imports, type declarations,
  the entry signature, command boundaries or prompt bodies outside the
  condition; an unrelated edit outside the mutable scope is rejected.
- Enumeration covers every catalog entry on matched tasks before any sampled
  proposal is scored against it; unguided sampling uses the same episode
  envelope and the I1 interface that later adaptive work reuses.
- Before the manifest exists, the locus arm's site facts come from the REPL:
  span, enclosing definition and declaration-level facts from `:info` and
  `:source`, and a type from `:type` only for a site whose expression
  typechecks in module context; the readout states which sites carried no
  type.
- The three-arm compile-only readout reports, per interface, acceptance per
  episode, edit locality (changes outside the selected site or its span) and
  distinct skeletons; paid whole-run evaluation covers a stratified subset of
  accepted proposals; admissibility differs by language and is reported per
  arm, never pooled.
- The skeleton hash reads authored source, not the closed program, and
  ignores renames, prompt text and literals by construction, so a rename or
  a prompt-only child hashes equal to its parent; distinct
  skeletons per accepted candidate and the revisit rate are reported.
- The agent-visible development check is one command boundary (`dev-check`
  in the driver design) frozen across conditions; hidden checks never reach a
  candidate or the mutator.
- Exit: whole-run quality and cost differences between structurally distinct
  candidates are measured. A tiny or flat neighbourhood ends the phase with
  that finding and no adaptive work.

### Phase 2 Gates

- The manifest passes its feasibility fixtures (P-1 and F-a through F-e in
  the inspection design); site resolution under shadowing is tested; a shared
  definition keeps one static site, and its callers and specializations are
  reported as fan-out, not as extra owners.
- The I2 transaction rejects a result-type change and an edit outside the
  selected site; two structurally different valid replacements both compile
  and execute.
- A changed candidate receives fresh execution state; cross-candidate
  provider or effect reuse is disabled; cached evaluation evidence is not a
  replicate and original cost is recorded separately.
- The authored reference seed is replicated on the validation split beside
  the finalists and budgeted with them.
- A provider call in an unexecuted branch stays unobserved; missing
  measurements are not zero.
- Approximately 20 to 30 completed episodes per search run and three
  independent runs are the illustrative pilot scale, subject to the Phase 0
  allocation; screen on four development tasks, then expand. A pilot of
  roughly twelve adaptive, six validation and twelve sealed task groups is
  descriptive, not a powered study.
- `phase2.json` predates the cost-proxy rule (its `mean_cost` is wall clock
  over a multi-model catalog) and is not changed; a Phase 2 selection needs
  a successor criterion with metered cost.

### Phase 3 Gates

- The three-arm test freezes one benchmark workflow, one model, one family
  and equal search budgets in completed episodes. Endpoints: dominating
  improvements and frontier entries per completed episode (Decision
  Criteria below). Secondary: skeleton diversity and
  revisit rate, acceptance rate, repair iterations per accepted proposal,
  wall clock and provider calls, and dollars only where metering coverage is
  complete. The result is a first bounded answer, not a settlement.
- Controls follow the ladder: authored direct and planner/implementer
  seeds; the enumerated catalog; prompt and provider tuning with fixed
  topology; equal-budget random neighbourhood sampling; the same protocol
  delivered as an agent skill; ORC structural search; matched typed Python
  search. Build only what the claim needs.
- The Python control shares adapters, schemas, prompts where frozen,
  evaluator, splits, environment, models, tools, limits and budget policy,
  and may use idiomatic functions, schema libraries, AST tooling and a type
  checker named with its strictness in the frozen criterion. Incremental
  work to expose slot information is measured per language, never charged
  wholesale to one side.
- Supplied-assistance ablations omit pre-supplied typed context or
  diagnostics while ordinary compiler tools remain available; what agents
  retrieve themselves is recorded.
- Validation chooses finalists on a frozen separate set; the sealed holdout
  opens once after candidate generation, selection, evaluator and analysis
  freeze. Existing named study claims keep their own requirements.

## Family Candidates And Cost Inputs

Measured inputs for the Phase 0 choice, taken from the comparison-harness
reports. They are historical cost and qualification facts, not evidence
about search value: E-B2 ran on a rung chosen before its calibration was
complete, so only its cost section is used, and no quality result from it
is cited. The relation between task difficulty, run cost and the headroom a
family leaves for planning, review and escalation is open and is measured
in Phase 0, not inferred from these rows.

| Family (a) candidate | Qualification under the frozen calibration rule | Measured cost signal |
| --- | --- | --- |
| Rung 1 `cf1-generic-unions` | Qualified: blockers 1, 1, 1 over three patches ([continuation](../reports/2026-10-15-calibration-continuation.md)) | E-B3: `direct_task` 4,347 s mean over three runs; `reviewed_change` 5,797 s over two; `design_review_execute` reached the 14,400 s executor ceiling in both cleared attempts ([E-B3](../reports/2026-10-16-eb3-orc-versus-single-call-rung1.md)) |
| Rung 2 `resume-projection-integrity` | Qualified: mean 2.5 over two patches ([calibration](../reports/2026-10-14-task-difficulty-calibration.md)) | Single calls 13 to 58 min on the ladder; no workflow run measured |
| Rung 3 `adopted-attempt-lineage` | Borderline: mean 1.0 over two patches; a third sample is required before it qualifies | E-B2, cost section: 1,271 to 6,273 s per workflow run at concurrency four ([E-B2](../reports/2026-10-15-calibrated-orc-versus-single-call.md)) |
| Rung 4 `pure-result-replay` | Qualified: mean 2.0 over two patches | Single calls within the ladder's 13 to 58 min |
| A new family, (a) or (b) | Qualified by the frozen rule and built in the harness package layout (`task.txt`, `intent.txt`, `base_commit`, `seed/`, `anchors/`, `hidden/`) before any search spend | Unknown |

Development checks visible to agents are never the objective. Hidden
acceptance is descriptive under the owner's 2026-10-15 evaluation policy;
search and selection use the family's frozen criterion (the blind rubric for
(a), the oracle for (b)), and the judge spend that implies is budgeted.

| Cost input | Measured | Source |
| --- | --- | --- |
| Provider calls per workflow run | `direct_task` 1; `design_review_execute` 4; `reviewed_change` 4 to 6 | E-B2, Runs |
| One single call; one review | 13 to 58 min on rungs 1 to 4; 2,248 s in the continuation; reviews 2 to 6 min | Calibration and continuation reports |
| Attempts per valued run | E-B3: 9 attempts, 5 valued (three provider timeouts, one contamination exclusion); E-B2: 9 of 9 | E-B3 and E-B2, Runs |
| Judge cost | One provider call per judge per batch of at most ten clones, two judges | Harness design, decision D4 |
| Hidden acceptance (descriptive) | Local pytest, one node at a time, 1,800 s ceiling per node | `experiments/compare/summarize.py` |
| Full compile | About 2 s for one clean Stage-3 compile | LSP design, context |
| Codex weekly window and credits | Account-wide readings shared with other sessions: upper bounds, never attributions per call | Reports, Cost |
| Anthropic usage | Not metered by the harness; Claude session files carry `message.usage` per assistant message (`experiments/compare/scan.py::claude_sessions`) and are the named proxy | Harness design |
| One mutator episode | Unknown; measured in Phase 1 | |

Budget placeholders are stated in provider calls, workflow runs, wall clock
and mutator episodes; tokens appear only where a session-file reader
provides them, and no dollar figure is claimed. These are budget units, not
the objective's cost axis (Decision Criteria).

| Phase | Formula | Owner placeholders |
| --- | --- | --- |
| 1 catalog, unguided sampling, compile-only three-arm | runs = `P` policies × `R` replicates × `T₀` tasks; attempts = runs × `L` (measured 1.0 to 1.8; budget 1.5); calls = attempts × `c`; mutator episodes = unguided `E₁` + 3 × `E₀`; paid three-arm runs on a stratified subset `S` | `P`, `R`, `T₀` (at least 2), `E₁`, `E₀`, `S`, concurrency, hard call ceiling, quota policy |
| 2 adaptive pilot | candidates = seeds + accepted proposals ≤ `E₂`; screening runs = candidates × `T₂`; validation runs = (`F` finalists + the reference seed) × `V` tasks × `r` replicates; attempts = runs × `L` | `E₂` (8 to 12), `T₂` (2 to 3), `F`, `V`, `r`, hard call ceiling, quota policy |
| 3 comparison | each search arm repeats a Phase 2-scale search; each fixed arm costs `T₂` × `r` runs; sealed judging adds two judges per batch | Stated at Phase 3 selection from Phase 2's measured numbers; its own preregistration |

## Decision Points And Stop Rules

| Point | Rule |
| --- | --- |
| Family choice | Only a family qualified under the frozen rule and with measured headroom on the family criterion; otherwise Phase 0 reports "no affordable qualified family" and stops |
| Calibration | In every live phase and experiment, no provider call is spent on quality evaluation (candidate evaluation runs and judge calls whose purpose is a quality comparison) unless the quality measure passed a predeclared calibration on known controls (for a judge measure: for each judge and batch the upstream anchor's total minus the stub's is at least `calibration.margin`, and the fraction of (judge, batch) pairs failing that is at most `calibration.error_rate`, default 0, both in the criterion) and the family is qualified under its own frozen rule (family (a): the harness difficulty-calibration rule; family (b): the oracle qualification in the driver design); calibration runs are their own predeclared experiments with their own budget and pass first; an uncalibrated measure reports only measure-free figures (compile-only metrics, execution outcomes, cost) and no quality comparison, frontier or improvement claim. The rule applies to provider spend from 2026-10-19 on: the in-progress three-arm readout runs no judge stage (its controller ruling R19, 2026-10-19) and reports compile-only figures, execution outcomes and cost, with quality `unavailable: evaluator uncalibrated` |
| Phase 1 separation | Tolerance predeclared in the criterion's units (default two within-arm standard deviations, measured on the family in Phase 1), judged per task and required on at least two tasks; DIRECT sole winner or everything within tolerance is recorded under the charter's decision rule and Phase 2 is not selected for the family |
| Collapse | If the share of accepted children whose skeleton equals the parent's exceeds the predeclared threshold (default 0.75) for an interface, that interface has collapsed to renames and literals and the adaptive claim is not tested on it; if every interface collapses, Phase 2 is not selected |
| Screening | Advancement, finalist replication beside the reference seed, and the shrinkage readout (screening mean against validation mean) follow the driver's selection rule; the pilot stays descriptive |
| Quota | No new run once the owner-stated window floor is reached unless the stated credit policy covers it; the readout says what completed |
| Lost runs | Provider-infrastructure stops are resumed, never relaunched; a timeout or contamination is an outcome under the frozen rule, its attempted cost counts, and the attempt rate is reported |
| Model policy | The harness model policy of 2026-10-15 applies to every mutator, candidate and judge call |

## Verification Obligations

Narrow selectors first, then the required broader checks for implementation
changes; `pytest --collect-only` on new test modules; at least one public
compile and run integration check for the chosen launch route; one
orchestrator smoke check whenever experiment mechanics, prompts or
provisioning change. Phase 1 plumbing runs through the harness's stand-in
agent CLI (`tests/experiments/compare_harness_support.py`) behind the real
shim, then one live smoke with real agents before any criterion freezes; any
seed or experiment workflow added gets a row in the `workflows/README.md`
registry. Behavioral tests assert contracts and lineage, not
prompt text. Minimum retained records: candidate source and configuration,
parent, final diff and the I2 receipt or the I1 validation verdict,
compile outcome and diagnostic class, task,
replicate and evaluator identity, run id and state directory, final outcome,
known consumption with unavailable markers, incidents and interventions,
each referencing existing run records by path rather than copying them.

## Decision Criteria And Next Commitment

Between candidates, wherever this roadmap says "beats" or "improvement",
better means Pareto dominance on (quality, metered deployed cost), or an
extension of the non-dominated frontier, as the
[driver design's objective](../design/orc_structural_search_driver.md#objective-selection-and-local-observations)
defines them; a higher score at any cost is not an improvement, and provider
calls stand in for cost only when every compared candidate's provider calls
resolve to one and the same (model, effort) pair. A claim about a search
method (feedback-guided search against enumeration or random sampling)
compares frontier entries per completed episode at equal budget. The frozen
criteria `phase1.json`, `phase2.json` (its scalar `improvement.min_gain`
included) and `three_arm.json` keep their rules; Pareto views of their runs
are descriptive.

| Claim | Supporting evidence |
| --- | --- |
| Structural feasibility | Agents produce previously unlisted working compositions through ordinary editing and full compilation |
| Useful search space | Structurally distinct candidates show meaningful whole-workflow quality and cost differences beyond the enumerated catalog |
| Proposal interface | Locus-plus-fragment improves the endpoints against whole-program and diff interfaces, with diversity reported |
| Adaptive optimization | Feedback-guided search beats equal-budget enumeration and random controls on independent evaluation |
| Compiler assistance | Single-factor ablations, not the three-arm test, show pre-supplied typed context or diagnostics improving proposal efficiency, repair effort or outcomes; tool-retrieved exposure is reported |
| ORC-specific value | The matched Python and agent-skill comparisons show a search, reliable-transformation or integration advantage, and the report says which |
| Compositional evolution | Extracted fragments transfer and recombine usefully |

Continue when an observed gain or a useful engineering property justifies
the next increment. If only prompt or provider tuning helps, keep that scope
and defer crossover. If the valid neighbourhood is tiny, enumeration is the
result. If Python or the agent skill performs equally with comparable
integration effort, report it and reconsider the custom-language investment
on its retained uses. If skeleton diversity collapses under every interface,
the operator-freedom bet fails and the report says so. An inconclusive pilot
calls for a better-targeted experiment, not a verdict. A DIRECT winner is
valid.

The immediate commitment, selected 2026-10-18, is **Phases 0 and 1**: the
governance and integration spike, then the catalog, enumeration and unguided
search that establish whether the space is worth adaptive work. Phase 2 and
the three-arm test follow only on that evidence. Phase 1 ran, and its compile-only
three-arm readout recorded acceptance, locality, skeleton figures and a collapse
verdict for I1, I2 and I3 (no arm collapsed; all 18 children converged on one
implement-check-repair idea; quality unavailable because the evaluator is
uncalibrated). The [Phase 1 report](../reports/2026-10-18-orc-structural-search-phase1.md)
records an inconclusive pilot: the upstream anchor scored at or below every
candidate, and one anchor pair was inverted. Phase 2 is not selected, and a
better-targeted experiment needs a new owner selection. The next plan to
write is the measurement plan: an evaluator calibrated on known controls and
a task family whose agent-visible check fails sometimes. It precedes any
live `module` arm
([module condition](2026-10-19-orc-structural-search-module-rewrite-plan.md#gate-for-a-live-module-arm)).

## Routing And Records

This is an authored roadmap, not an executable selector; no tranche manifest
or queue is added. Code placement: the manifest module near
`orchestrator/workflow_lisp/`, everything else under
`experiments/orc_structural_search/` with immutable candidate files and one
append-only JSONL episode and evaluation log. Fitness, archives and selection
never enter `orchestrator/`. The boundary amendment is applied in the
boundaries document, whose change note keeps its anchor; the driver design
carries its rationale. Limits carried into every phase: one active run
per workspace, no persisted usage in the evaluated runtime, no span-to-type
table in the checker, and no OMP shim.

## Related Work

- [Automated Design of Agentic Systems](https://arxiv.org/abs/2408.08435)
  (Hu, Lu, Clune): meta-agent search over agent code with an archive; the
  general idea is not claimed as novel here.
- [GEPA optimize_anything](https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/):
  a proposal/evaluation engine that evolves instructions and demonstrations
  inside a fixed program structure; a possible backend and a comparison.
- Montana, "Strongly Typed Genetic Programming", Evolutionary Computation
  3(2), 1995: type-constrained crossover and mutation; the lineage of
  compiler-certified candidates.
- [Mutation Without Variation](https://arxiv.org/abs/2606.05408) (Gurkan,
  Stonedahl, Wilensky, 2026): LLM mutation chains over a DSL converge to
  recurring structural templates; the reason skeleton diversity is measured.
- Evolution through Large Models (Lehman et al., 2022) and AlphaEvolve
  (Novikov et al., 2025): LLM proposers in evolutionary loops; targeted
  diffs outperforming full rewrites motivates locality-native interfaces.

The proposed contribution is the practical value of a compiler-aware workflow
representation for structural mutation and recombination, established by
measured implementation and search results.
