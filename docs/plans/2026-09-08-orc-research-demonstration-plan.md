# ORC Research Demonstration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (or `superpowers:executing-plans`
> for an approved separate execution session). Use checkboxes to track tasks.

**Status:** draft for review; documentation preparation only is authorized.
No experiment, paid provider call, implementation tranche, or source promotion
is selected by publication of this plan.

**Goal:** measure programmability/compositionality, reuse, introspection,
self-programmability, and eventually optimization as independent hypotheses,
then turn evidence into bounded improvement or retirement and simplification
of each affected scope before investing in a general optimizer or replacement
foundation.

**Architecture:** reuse the compiler, diagnostics, immutable child runs, and
trial evidence. ORC composes agent/provider operations; those agents/providers
perform tool use. The experiment controller stays outside the runtime.

**Tech stack:** existing Python/pytest, Git, Workflow Lisp compiler and E1/E2
APIs; Rust only for the later, separately approved scientific task corpus.
No new dependency, service, language form, or registry is planned for the
initial demonstrations; evidence-led follow-ons may reconsider the foundation.

**Governing documents:** the [research charter](2026-09-08-orc-research-charter.md),
[current roadmap](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md),
[demonstration design](../design/orc_reuse_introspection_search_experiment.md),
[trial design](../design/workflow_lisp_trial_runs.md), and binding
[program-search boundaries](../design/workflow_lisp_program_search_boundaries.md).
Normative execution contracts remain in `specs/`. Per owner direction on
2026-09-08, execution safety is outside this research assessment and is not an
investment criterion or proposed workstream. This draft changes no runtime
contract; implementation-route discrepancies must be stated, not mistaken for
conceptual objections to composing tool-using agents.

## Documentation Preparation — This Request

- [x] Draft the one-page charter and durable experiment design.
- [x] Overhaul current roadmap sequencing; preserve historical evidence,
  pinned ES apparatus, and unrelated pending work.
- [x] Align documentation discovery and old prospective ES routing.
- [x] Independently review design and plan; verify the documentation diff and
  existing routing checks. Do not execute the research tasks below.

Original three-axis preparation verification (2026-09-08): independent design, plan, and routing
reviews found no remaining blockers after corrections; the existing routing
module passed all 71 tests, 64 added/new relative Markdown links resolved, and
the scoped whitespace check passed. The pinned ES refreeze plan retained its
original digest. These are documentation checks, not research results or
approval to execute the draft. They do not certify the later five-axis amendment.

## Five-Axis Amendment — Documentation Work Only

The owner requested these amendments after reviewing the expanded approach.
Approval to edit these documents is not selection of the experiments below.

- [x] Add explicit programmability/compositionality and self-programmability
  hypotheses to the charter and experiment design.
- [x] Replace R1's measurement allocation with bounded R1a construction,
  reuse, and diagnosis; define R1b authoring/revision separately.
- [x] Amend plan tasks, budgets, early ordinary-code control, and per-axis
  disposition; align the roadmap and discovery/scheduling descriptions.
- [x] Independently review the amended documents and run fresh routing,
  link, whitespace, and historical-preservation checks.

Five-axis amendment verification (2026-09-08): independent design and plan
reviews found no remaining blockers after fixing preparation/freeze order and
limiting the early ordinary-code control to its allocated construction checks.
The focused routing test and full 71-test routing module passed; all 67
added/new relative Markdown links resolved and scoped whitespace checks passed.
Historical routing/scientific records and the pinned refreeze-plan digest were
preserved. R1 became R1a/R1b; no research unit was selected or marked complete,
no executable selector changed, and no new OMP steering was sent.

## Consequent-Action Amendment — Documentation Work Only

The owner requires each axis to lead beyond a minimum viable example: pursue
principled improvement where justified; otherwise abandon the unsupported line
and simplify what remains. Foundational assumptions, including the type system
and language principles, must be reconsidered where they cause the obstruction;
local fixes are not the only alternative to giving up. This amendment selects
no research, redesign implementation, or deletion work.

- [x] Extend the roadmap with axis-specific improvement, retirement, and
  simplification branches; distinguish evidence from investment decisions.
- [x] Align the charter and design's decision rules, and make the plan's
  evidence review produce an actionable follow-on or closure, including
  assumption review and justified foundational alternatives.
- [x] Update discovery, independently review, and verify routing and preserved
  historical evidence. Leave existing experiment budgets and ES work unchanged.

Consequent-action verification (2026-09-08): independent review approved the
revised lifecycle and assumption review after correcting an overbroad platform
stop rule. The focused routing test and full 71-test routing module passed;
three added relative links and their anchors resolved, and whitespace checks
passed. Initial budgets, historical roadmap, ES boundary/refreeze digest,
independent work, and legacy routing-input digest were preserved. The five
research units remain unchanged; conditional Task 7 is unselected. No executable
selector, workflow, runtime, or research allocation changed.

Recursion-limit clarification verification (2026-09-08): independent review
approved; the focused E-series routing test, new-link checks, and whitespace
checks passed. The full routing module returned 68 passed and three failures
in surfaces untouched by this clarification: PyYAML-retirement wording, Q2
`active` wording, and the master-spec title's v2.26/v2.27 assertion. Targeted
reruns reproduced all three; they were not changed or weakened here. Research
units, selection, runtime, and current language contracts remain unchanged.

## Execution Boundaries And Replacement Budgets

R1a comprises Tasks 0–2 and its Task-4 report. Its proposed ceiling remains
five aggregate person-days (40 active person-hours across all participants,
including preparation, control construction, assessment, and review), with
zero paid provider calls. Human authors and deterministic leaf doubles supply
the first measurements. Paid preparation assistance would require an explicit
budget amendment and cost accounting; do not hide it outside the zero-call claim.

This allocation **replaces**, rather than extends, the original 48-cell,
twelve-fault, optional twelve-proposal slice:

| R1a work | Replacement allocation |
| --- | --- |
| Existing four-arm regressions | Four arms × three selected scenarios = twelve cells. |
| Novel composition | Three held-back requirements × three behavioral scenarios = nine cells. |
| Early Python/native control | One matched requirement × three scenarios = three cells. |
| Behavior-cell total | Twenty-four cells, evaluated once per frozen program. |
| Reuse | Three portfolio-wide changes × two source conditions = six timed efforts; each verifies three consumers, giving eighteen consumer checks. |
| Introspection | Six paired cases, one per fault category; two equivalent variants assigned one per evidence condition = twelve assessments. |

Oracle qualification and focused regression tests are preparation/verification,
not extra independent experimental samples; their effort still consumes the
40-hour cap. No standalone compile-mutation study remains. If preparation or
measurement does not fit, stop with partial evidence and named gaps. Do not
repopulate the retired matrix afterward or silently substitute easier cases.

R1b is separately selected Task 3 plus its Task-4 report. Proposed ceilings:
three ORC episodes, each an initial program plus at most two revisions (at most
nine complete program versions); thirty authoring-model requests including
tool-loop turns; 250,000 metered input-plus-output tokens; three aggregate
elapsed hours of agent/workflow execution; and eight aggregate person-hours
including preparation, assessment, and review. Stop on the first exhausted
ceiling. All failed requests, compile-repair attempts, and assisted preparation
consume these totals. Leaf execution uses deterministic doubles, not live domain
providers. Before allocation, freeze the authoring model/configuration and a
finite monetary ceiling in the experiment input manifest; these proposed caps
are not funding approval. Missing metering must be resolved before paid entry.

The R1b final-check allocation must be reserved before adaptive spending. The
three episodes are descriptive feasibility, not an ORC-versus-Python agent
comparison. Matching agent-control episodes need their own later allocation;
do not silently double this budget to obtain them.

Task 0 selects only R1a preparation/measurement. R1b needs its own entry review
and resource allocation; it does not require positive reuse/introspection
screens. Tasks 5–7 also require separate protocols and allocation. Task 7 is a
conditional consequence of a reviewed axis result, not work hidden in R1a/R1b
or a requirement to finish all experiments first. None of
these small measurements earns `PASS_E3` or a live effectiveness claim.

## Task 0 — Close Routing And Freeze The Small Question

**Files:** this plan and the current roadmap; eventual evidence under
`docs/reports/2026-09-08-orc-research-demonstration.md` (create only on execution).

- [ ] Re-read current ES/refreeze status and coordinate with its active owner.
  Record either bounded continuation under its existing adoption gate, or an
  explicit owner prelaunch park/closure. Do not alter frozen study bytes.
- [ ] Record the accepted R1a 40-person-hour/zero-provider ceiling and the
  separate roles responsible for case preparation, authorship, and assessment.
- [ ] Review the design against current public APIs. Classify each promised
  proof as already evidenced, to be demonstrated, or blocked.
- [ ] Define the preparation/measurement boundary: Task 1 and Task 2's
  development preparation qualify the operation vocabulary, oracle, and
  components. Their outputs freeze before the assessed author sees held-back
  requirements; they are not prerequisites for permission to prepare them.
  Specify how behavioral acceptance, diagnostic truth, adaptation requests,
  comparison order, and accounting will be frozen before measurement.
- [ ] Use one experiment-local input manifest, not a new platform schema.
  Record no automatic successor selection from either utility-screen result.

**Exit:** clear authority for Tasks 1–2 and R1a's Task-4 report only; otherwise
retain the plan as a draft. ES's RICH-screen outcome is context, not a win gate.

## Task 1 — Qualify Execution And A Topology-Independent Oracle

**Read/reuse:**

- `workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc`
- `orchestrator/workflow/trial/sdk.py` (`TrialRunOptions`, `run_trial_entry`)
- `tests/experiments/test_es_qa_placement_workflows.py`
- `tests/e2e/test_e2e_workflow_lisp_trial.py`
- `tests/test_workflow_run_ref_path_compile.py`

**Proposed additions, only after selection:** one experiment-local directory
`experiments/orc_research_demo/` containing `README.md`, `inputs.json`, a small
authored `trial.orc`, and local fixture assets; one owner test module
`tests/experiments/test_orc_research_demo.py`. Do not fork the frozen ES wrapper
or inherit its unrestricted provider configuration.

- [ ] Add the smallest failing behavior test for a portable terminal-`trial`
  entry importing the existing four arms, with real local check execution and
  explicitly scripted providers/scorer inside the test harness.
- [ ] Implement only the fixture/wrapper needed for that test. Public SDK
  options have no mock/scorer injection API; keep substitutions in tests and
  label them. Do not patch correctness checks to always succeed.
- [ ] Prove one genuine two-arm child-process/check-process run reaches a
  committed verdict through the public entry. Preserve sibling-failure and
  committed-result resume evidence using existing test helpers.
- [ ] Add a known failing check control. If public execution cannot support
  the tiny proof without new runtime machinery, record the exact gap and stop
  that lane; do not invent a second executor.
- [ ] Keep predetermined QA role sequences only for the fixed-arm regression
  subset. Add operation/input/context-based doubles for novel compositions.
  The same operation and inputs must not receive different answers merely
  because a different candidate called them.
- [ ] Demonstrate on development examples that the behavioral oracle accepts
  two different correct structures and rejects a broken composition. It must
  check outputs/dependencies/control obligations, not a prescribed graph or
  literal prompt wording. Establish these proofs before assessment freezes.

**Verify:** collect the new test module, then run its narrow selectors.
Existing reference selectors to characterize first:

```bash
pytest -q tests/experiments/test_es_qa_placement_workflows.py -k 'exact_four_arm_entries_compile or four_cell_trial_compiles'
pytest -q tests/test_workflow_run_ref_path_compile.py -k 'full_compile_admits_exact_effect_free or provider_diagnostic_routes or command_diagnostic_routes'
```

**Exit:** reproducible mechanism evidence, explicitly not scientific quality,
provider variability, or sandbox evidence.

## Task 2 — Construct New Programs, Then Measure Reuse And Diagnosis

**Files:** extend only the experiment assets and owner test module above;
write measurements to the execution report, referencing ordinary compiler and
run artifacts rather than introducing a parallel trace database.

- [ ] During development preparation, establish the component boundaries.
  Existing QA exports
  are whole workflow arms, not public review/fix procedures. Reuse exports
  where sufficient; permit one bounded experiment-local extraction of shared
  workflow definitions when needed for the adaptation, counting its setup cost.
  Preserve frozen ES sources; freeze the resulting library before assessment.
- [ ] Reveal three previously unseen requirement cases. Construct and execute
  programs for bounded review/revision, conditional judgment aggregation, and
  a reusable multi-item process, using the exact qualified case definitions.
  Choosing an existing whole arm is insufficient when it does not meet the
  case's behavioral obligations. Test three frozen scenarios per case.
- [ ] Record correctness, construction/verification effort, glue, forks,
  interface edits, and predicted versus actual edit consequences. Classify
  library, language/runtime, authoring/documentation, and apparatus gaps.
  Do not modify the runtime/compiler to hide a failed expressibility case.
- [ ] Build one early matched Python/native construction-only control
  using ordinary idiomatic tooling and the same behavioral oracle. Its three
  scenario results are a feasibility comparison, not general superiority.
  Matched change/revision comparisons need later explicit allocation; they are
  not included in this three-scenario control.
- [ ] Use successfully constructed programs as the three-consumer reuse
  portfolio and build an equivalent copied-source control. Freeze behavior,
  prompts, provider policy, and checks in both conditions. If a construction
  case failed, report the missing dependency and any explicitly narrowed claim;
  do not swap in an easier known arm without recording a changed experiment.
- [ ] Apply each of three predefined portfolio-wide adaptations independently
  from its baseline: provider-policy substitution, a typed evidence-contract
  change, and a bounded review/repair policy change. Each timed effort includes
  changing and verifying all three consumers; count shared edits once. Record
  six timed efforts and eighteen consumer checks, including all caller changes,
  verification, forks, active time, errors, and any assistance cost.
- [ ] Seed six paired diagnostic cases, one per design category; retain a
  controller-owned truth manifest and event boundaries independently of
  whatever diagnostics the runtime emits.
- [ ] Compare ordinary source/log/result evidence with that same evidence
  plus structured compiler/run inspection. Assign two equivalent variants per
  pair, one per condition, with counterbalanced variant assignment and order;
  score correct attribution and recovery decision, abstention, time, and
  confidently wrong answers, not error-message wording.
- [ ] Retain all twenty-four behavior-cell outcomes, eighteen reuse consumer
  checks, and twelve diagnostic assessments. Never count repeated deterministic
  checks as additional independent samples. Fixture success establishes scoped
  behavior, not agent authorship or live task effectiveness.

**Exit:** paired measurements, including unfavorable results and unavailable
measurements. If fair diagnosis assessment cannot be staffed inside the cap,
report an untested utility claim rather than substituting diagnostic coverage.

## Task 3 — Separately Budgeted Agent Authoring And Self-Programming

**Files:** extend the same experiment assets, owner test module, and input
manifest. Add `experiments/orc_research_demo/authoring.py` only if existing
helpers cannot drive the bounded compile/run/feedback loop. No `search.py` or
general optimizer is needed. Use temporary pinned repositories for program
revisions, not candidate commits in the user's working branch.

- [ ] Obtain separate R1b selection and freeze all ceilings above, model,
  monetary cap, feedback exposure, intervention rules, and final-check reserve.
  Account for actual authoring calls; scripted leaf providers do not make this
  lane free. Without this allocation, Task 3 remains unselected.
- [ ] Use bounded preparation inside R1b to demonstrate one generated
  provider-workflow composition through ordinary compilation and execution
  with operation-based doubles and real checks. The current clone-path mode
  is effect-free; do not invent a mock SDK API or mislabel that route. Resolve
  any implementation/document discrepancy before measurement. A failed proof
  stops this lane, not unrelated R1a or R2 work, and selects no safety project.
- [ ] Freeze three agent episodes with fresh contexts, one per requirement
  family. Use the framework, not R1a solution source, as context. Designate a
  requirement-change episode and a closed-loop objective/feedback episode.
  Reserve final unseen checks; do not let their answers guide revisions.
- [ ] Have the agent choose a composition and produce an ordinary source
  program. Pin and fully compile every version; execute accepted versions
  against public development checks. Retain rejected source and diagnostics.
- [ ] Supply only the predeclared feedback or changed requirement. Permit at
  most two revisions per episode. In the closed-loop case, the agent chooses
  the orchestration edit from its goal and execution evidence; the controller
  does not prescribe a topology. Mere compile repair is scored separately.
- [ ] Record predicted change, complete program identity, actual behavior,
  unaffected obligations, human assistance, all requests/tokens/time/cost, and
  first/final results. Structural distinctness is not behavioral improvement.
  Budget-exhausted episodes and first-version failures remain visible.
- [ ] Freeze each selected final revision before the held-back check. Do not
  repair against final-check answers. Classify authoring, feedback revision,
  and unassisted closed-loop evidence separately. An already successful program
  with no revision supplies authoring evidence only.

**Exit:** scoped evidence or a named failed prerequisite for each accomplishment,
with actual expenditure. No superiority, live domain quality, genetic-search,
or automatic R2/R3-selection claim follows. This lane is not conditional on a
positive reuse or introspection utility screen.

## Task 4 — Review Evidence And Choose Consequent Actions

**Files:** execution report and current roadmap; do not rewrite recorded
measurements after seeing the answer.

- [ ] Produce a report after R1a whether or not R1b is selected; later append
  separately identified R1b evidence. Review whole diff and evidence for
  contract compliance and simplicity. Separate mechanism, utility, and efficacy.
- [ ] Run narrow owner tests and one genuine public-entry integration smoke.
  For selected implementation changes, run the applicable broad gate in tmux
  as `pytest -q -n 16 --dist=worksteal`, after narrow checks. Report failures
  and environment limitations; do not weaken checks to obtain a green gate.
- [ ] Publish actual effort, missing receipts, all failed/rejected cases, and
  maintenance added. Compare the measurements to the design's predeclared
  exploratory continuation rule.
- [ ] Record supported-within-scope, adverse, inconclusive, or untested for
  each of the five axes separately from its recommended action. Use the
  [roadmap's axis lifecycle](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#axis-lifecycle--improve-or-retire-then-simplify):
  retain a useful scope, improve a named bottleneck, reconsider an implicated
  language/foundation assumption, or retire the unsupported scope and simplify.
- [ ] In the same report, identify each axis's retained use, observed limit,
  proposed causal remedy and re-evaluation, or retirement/cancellation targets.
  For inconclusive/untested work, specify the smallest uncertainty-resolving
  test or an explicit park with reopening evidence; do not infer impossibility.
  A positive demo alone is not a completed improvement program.
- [ ] Before declaring an axis blocked or prescribing abandonment, distinguish
  failure of today's encoding from failure of the intended capability. When a
  foundational assumption is implicated, compare credible local, type/language
  redesign, and alternative-foundation responses against the same user goal.
  Record the design principles challenged and the smallest proof that could
  distinguish the alternatives, rather than require today's checker/runtime
  to demonstrate the capability it prevents. Budget exhaustion is not disproof.
- [ ] Record encountered design-derived language limits in the same report,
  including the absence of unbounded recursion where relevant: owning rule,
  rationale, blocked use/workaround cost, and evidence for reopening the design.
  Compare iterative/delegated encodings with recursion or execution-model
  revision without assuming those encodings preserve composition/inspection.
  Keep per-run time/cost ceilings distinct from language expressiveness;
  Task 7 can investigate a justified limit without selecting its removal now.
- [ ] For any proposed follow-on, name its owner, finite resource ceiling,
  useful improvement threshold, expected reuse/payback horizon, fresh-case
  check, stop rule, and simplification if it fails. Request separate Task-7
  selection; do not spend the remainder of an R1 budget on unplanned repair.
- [ ] Trace consequences for dependent work and the project foundation.
  Failure of reuse/diagnosis does not settle other axes; failure of autonomous
  revision can retain assisted authoring or non-agent search. A lost executable
  composition space does require narrowing or replacement of generated-program
  work. Recommend direct improvement, language/subsystem redesign,
  migration/reimplementation, or
  platform abandonment according to the roadmap's portfolio criteria.

**Exit:** evidence plus a concrete proposed improvement, retention, or retirement
decision for each assessed scope; untested scopes have explicit unresolved
questions and allocation/park recommendations. No outcome automatically approves
R1b, Tasks 5–7, EL-1, a general GA, or code deletion.

## Conditional Task 5 — Qualify One Live Task Family

**Starting assets:** `examples/demo_task_linear_classifier_port/` and
`orchestrator/demo/evaluators/linear_classifier.py`.

- [ ] First establish a verified green Rust target against the independent
  Python reference; existing unfinished port seeds are not repair baselines.
- [ ] Prepare twelve bounded repair episodes grouped by genuinely distinct
  defect families; prepartition families into adaptive/validation/sealed
  holdout sets. Qualify exact split sizes and evaluator sensitivity before
  proposing or selecting candidates. No numerical input reseeding counts as
  a new independent repair task.
- [ ] Preregister one finite authored-arm study with fixed prompts, models,
  tools, objective, retries, and owner-approved cost/time/provider ceilings.
  Include at least three stochastic repetitions per candidate/task for initial
  noise characterization; these do not increase independent task count.
- [ ] Reserve the holdout allocation before adaptive spending. Publish a
  descriptive pilot only; twelve episodes cannot satisfy the trial design's
  powered-effectiveness requirements or its ≥30-independent-holdout floor.

**Exit:** qualified task/evaluator and affordable pilot, or stop. No live
execution until a separately reviewed bounded protocol is accepted. NanoBragg
transfer and additional domains remain out of this first study. A fixed authored
catalog does not require successful R1b autonomous authoring. Apply Task 4's
consequent-action review to this evidence before proposing further development.

## Conditional Task 6 — Test Search And Representation Value

- [ ] Compare fixed reviewed candidates and full enumeration/random search
  before choosing an adaptive method. Four candidates normally warrant
  enumeration; do not build a GA to rediscover their maximum.
- [ ] Before expanding the candidate catalog, prove one source proposal can
  compile and run as an ordinary whole-workflow trial with the fixed provider
  configuration. Resolve the current bundle/clone-path integration and any
  governing-document discrepancy in that bounded implementation plan. Tool
  use remains delegated to agents/providers; no safety workstream is proposed.
- [ ] For an adaptive claim, freeze equal proposal/evaluation budgets, charge
  invalid proposals and diagnostic-repair calls, retain separate prompt-only
  and topology-only ablations, and select whole candidates on validation.
- [ ] Extend the early Python/native feasibility control for any ORC-specific
  comparative claim. Use a credible reusable Python/native
  control with the same workflow behavior, model/tools, evaluator, recovery
  obligations, and total engineering/operating accounting. This is a control,
  not a second platform product. For agent-authoring comparisons, match semantic
  requirements and budgets with idiomatic solutions; identical topology is
  required only when that is the particular representation-mechanics control.
- [ ] Power any confirmatory study, freeze its decision rule, and open a new
  sealed holdout once. Retain ORC for measured programming, reuse, diagnosis,
  self-programming, reliability, or search benefits; favorable topology alone cannot establish representation
  value. Stop expansion if simpler controls remain as useful at lower cost.

**Exit:** evidence-backed continue/narrow/reimplement/abandon decision. No
automatic self-modification, crossover machinery, or multi-domain claim. Apply
Task 4's review: a negative search result must also identify the simpler retained
policy and the search-only work to retire, not just stop new experiments.

## Conditional Task 7 — Improve Or Retire The Selected Scope

This task may follow any Task-4 review, including review of Tasks 5–6. It is not
a mandatory R4 stage or five parallel feature projects. Select one bounded
axis-specific change or closure at a time; investigate dependencies before
combining scopes. Reuse the execution report and roadmap for decisions, and
write a scoped implementation plan under `docs/plans/` only after the affected
contracts, consumers, remedy/removals, and verification are known. No speculative
file inventory, new framework, or permanent second implementation is prescribed.

- [ ] Obtain explicit selection and allocation for the reviewed consequence.
  Freeze its affected claim/use, baseline, causal hypothesis or retirement
  rationale, success/stop criteria, owner, and complete cost ceiling. Initial
  research budgets are unchanged and do not authorize this work.
- [ ] Inventory concrete callers, interfaces, configuration, derived evidence,
  docs, and pending features that the change affects. Mark what has independent
  consumers, what must migrate, and what becomes unnecessary. Never-built
  features are cancelled, not reported as deleted implementation.
- [ ] For improvement, first choose the target from the reviewed alternatives.
  Add the narrow regression that exposes the diagnosed bottleneck, implement
  the smallest coherent remedy for that target, and remove displaced glue or
  paths. The target need not preserve today's type model or language principles.
  Introduce semantic changes only after the owning design/spec amendment and
  feasibility proof, not as hidden repairs to the old assessment.
- [ ] Compare the revised capability with the original and relevant simpler
  control on independently prepared fresh cases plus retained regressions.
  Account for implementation, onboarding, migration, assistance, operation,
  and maintenance; measure the chosen axis, not just compile/test counts.
- [ ] For a type-system, language, or replacement-foundation investigation,
  explicitly challenge the implicated assumptions and test a discriminating
  case on the alternative. A credible obstruction can justify investigation;
  it does not require prior success in ORC. Before committing to the overhaul,
  demonstrate the useful capability and improved tradeoff, including unaffected
  obligations, migration, and ownership. Amend superseded design principles
  explicitly. A successful proof supports a separately scoped adoption decision,
  not automatic whole-project rewriting or two permanent implementations.
- [ ] For retirement, migrate or explicitly close affected consumers, remove
  unneeded experimental code/configuration/views, and cancel unsupported pending
  features. Keep facts/contracts used by retained capabilities and preserve
  scientific evidence. No unrelated ES, P/ME/OMP/EL-1 removal is implied.
- [ ] Run the narrow retained-behavior and routing checks; add a genuine
  integration/resume check when the selected change affects those contracts,
  followed by the applicable broad gate under the repo's tmux/pytest rules.
  Update discovery and any actual selectors; closed work must not remain
  silently pending or selectable. Review the actual diff and evidence.
- [ ] Close with measured improvement and explicit retained scope, or execute
  the approved fallback retirement/simplification. If that fallback was not
  selected, stop and request its scoped approval; do not infer deletion authority
  from failure. A useful original baseline can remain while its extension is
  retired. Further cycles require new evidence and allocation; unresolved
  uncertainty is recorded, not relabeled a success or a fatal flaw.

**Exit:** verified improvement, or verified scoped retirement/cancellation and
a simpler retained system. A replacement proof or unresolved prerequisite exits
with its explicit next decision, without claiming migration or cleanup complete.
