# ORC Programmability, Composition, And Improvement

## Status And Authority

Status: draft experiment design. This describes a proposed study, not an
implemented optimizer, an accepted execution plan, or an efficacy result.
Scheduling and selection belong to the [roadmap](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md);
bounded execution tasks belong to the [plan](../plans/2026-09-08-orc-research-demonstration-plan.md).
The [charter](../plans/2026-09-08-orc-research-charter.md) states the investment thesis.

Normative behavior remains in `specs/`. The existing [trial design](workflow_lisp_trial_runs.md)
owns child-run/evaluation methodology; [program-search boundaries](workflow_lisp_program_search_boundaries.md)
record the current architecture. This proposal adds no language target.

Owner scope clarification, 2026-09-08: **execution safety is excluded from the
conceptual assessment and proposed investment gates**. Tool use is performed by
agents/providers. This design studies how ORC composes, describes, reuses, and
optimizes those operations. Existing execution-route restrictions are
implementation facts, not evidence against the research thesis. This draft does
not silently change those restrictions or claim they are already removed.

## Question And Intended Value

Can ORC serve as a useful programming medium in which people and agents
construct new behavior, reuse components, inspect execution, and revise or
optimize complete programs?

Five hypotheses are separate: programmability/compositionality, reusability,
introspection, self-programmability, and optimization. A reusable library need
not compose well; agent-written source need not execute correctly; and selecting
among fixed arms establishes neither authoring nor self-programming. A fixed
topology's quality cannot establish representation or optimizer value.

The existing type system, source representation, and language design principles
are hypotheses about a useful programming medium, not fixed premises that every
successful solution must preserve. Initial comparisons freeze today's baseline
for interpretable evidence; a subsequent investigation may explicitly revise it.

Plausible consumers are repeated repository maintenance with explicit evidence
contracts, recurring scientific implementation/repair with a hard oracle, and
families of review/revise tasks sharing components but differing in policy.
These are hypotheses about repeated work, not claims that existing AI tools
cannot perform these tasks. One-off tasks with little reuse or evaluability
are a weak initial target.

## What Is Already Available

| Existing surface | What it contributes | Limit of that evidence |
| --- | --- | --- |
| `workflows/library/control/direct_task.orc` and the four exports in `workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc` | Real shared direct/review/fix composition and a common arm interface. | Reuse mechanism, not measured adaptation savings. |
| Full compiler, `compile --diagnostics-json`, canonical IR/source-map exports, and `explain` | Types, calls, effects, dependencies, and authored-to-executable inspection. | Structural facts, not access to private model reasoning or proof of task quality. |
| E1 `run-ref`, E2 `trial`, `TrialRunOptions`, and `run_trial_entry` | Pinned child runs, whole-arm outcomes, checks, evidence, accounting, and verdicts. | Implemented mechanism, not a completed search or effectiveness study. |
| Scripted-provider QA and trial tests | Reproducible branches, malformed results, child/check subprocesses, and failure handling. | Test harness evidence; fake providers/scorers are not a public SDK execution mode. |

The checked-in ES `qa_placement_trial.orc` is a substantial, locally pinned
study wrapper with long budgets and a study-specific provider configuration.
Do not repurpose it as a tiny portable demo. Import the arm library into one
small experiment-local wrapper instead. A public trial entry must have a
terminal `trial` body; a lower-level executor fixture that returns a later
literal is not automatically SDK-compatible.

The current clone-path `run-ref` mode accepts only deterministic effect-free
programs. Ordinary precompiled bundle workflows can contain provider operations.
Generated provider-workflow search therefore needs an explicit bundle/trial
integration proof and reconciliation with governing documents at implementation
planning; it is not already supported by relabeling clone-path execution. This
does not select a safety workstream or require a pure-program study first.

## Minimal Experiment Structure

Use one experiment-local input manifest, existing compiler/run evidence, and
one results report. Share constructed programs and behavioral fixtures across
the experiments, but score each hypothesis separately. A separate authoring
benchmark would isolate staffing more cleanly but duplicate preparation; this
design instead adds authoring to the same small experiment.

Existing scripted QA role sequences remain fixed-arm regression checks. For
novel programs, leaf doubles respond to declared operations, typed inputs, and
explicit fixture context, not a prescribed global topology or candidate ID.
The oracle checks outcomes, required dependencies, bounded control, and evidence
obligations while allowing multiple correct compositions. Include a deliberately
wrong composition and two different valid structures as oracle controls. Keep
substitutions in test helpers; do not add mock options to the public SDK or
replace correctness checks with unconditional success.

An external driver may pass requirements, invoke existing compile/execution
surfaces, deliver permitted feedback, and record program revisions. It supplies
neither the solution topology nor a new runtime/fitness system. Use existing
helpers unless a concrete missing integration requires a small experiment-local
adapter. Generated-workflow execution must be demonstrated through the actual
ordinary compiled-program route before its owning measurement can run.

Keep three evidence levels distinct:

1. **Mechanism:** compositions execute, inspection facts are accurate, source
   proposals compile/reject as expected, and evidence binds to whole programs.
2. **Practical utility:** construction, adaptation, diagnosis, or agent-led
   programming succeeds or improves under an explicit comparison, with measured
   effort, assistance, and failures. Authoring, feedback-driven revision, and
   closed-loop self-programming have distinct evidence requirements below.
3. **Optimization/effectiveness:** independent tasks show a useful quality/cost
   frontier or an adaptive advantage over equal-budget alternatives.

Passing one level never implies the next. R1a measures human construction,
reuse, and diagnosis with deterministic execution fixtures. Separately funded
R1b measures agent authorship and revision using the same framework. Neither
establishes live task effectiveness or general optimization advantage.

## Experiment P — Programmability And Compositionality

Freeze a documented component/operation vocabulary using development examples,
then reveal three assessment requirements unseen by the assessed author. This
means held-back tasks, not a claim about an LLM's training history. Qualify the
requirements against the intended existing surface without tailoring a library
to their exact solutions. Candidate shapes include:

- bounded review/revision with distinct approval, changes-requested, and blocked
  outcomes, preserving the latest usable result;
- independent judgments with conditional aggregation and disagreement handling;
- a reusable process composed over several items, with per-item evidence and
  correct continuation after interruption.

These are requirement families, not promised existing whole-workflow APIs.
Freeze exact cases and three behavioral scenarios per case before authoring.
Score complete behavior rather than matching a reference graph or prompt text.
Permit ordinary source composition and local adapters, but record all glue,
duplicated logic, extraction, and interface changes. A runtime/compiler change
needed to express a case is a finding about the current foundation, not a
permitted hidden repair to the assessed baseline.

Classify each result: expressible by ordinary composition; expressible with
extra glue/forks; library-interface gap; language/runtime gap; authoring or
documentation failure; or evaluator/apparatus defect. Record construction and
verification effort, predicted versus actual consequences of edits, and
preservation of unrelated behavior. Untestable cases remain untested; they do
not become successes by reducing the requirement afterward.

Build one matched Python/native construction-only control early, using
the same operation semantics and behavioral oracle. Both representations may
use idiomatic source and ordinary tools; they need not produce identical
topologies. Include documentation/onboarding and control construction costs.
This small feasibility comparison cannot establish general ORC superiority.
Matched change/revision comparisons require later explicit allocation; they are
not additional measurements hidden inside the three early control scenarios.

## Experiment A — Reuse

Use the three successful constructed programs as the reuse portfolio. If a
case is not constructible, report that dependency and narrow the reuse claim
explicitly; do not silently replace it with an easier known arm. The QA module
exports four whole workflow arms, not its private review/fix workflows or
evidence types. Reuse those exports where sufficient; where the adaptation
requires a component boundary, permit one bounded experiment-local extraction
of existing workflow definitions during development preparation, before the
assessment library freezes, and count its complete setup cost. Do not
modify frozen ES sources or present this extraction as an already public API.
Compare shared imports against equivalent copied ORC definitions implementing
the same frozen behavior. This isolates the value of reuse within ORC; it does
not establish superiority to reusable Python.

Apply three independent portfolio-wide changes from each original baseline:
substitute a provider policy; change a typed evidence contract; change a
supported bounded review/repair policy. Each timed adaptation updates and
verifies all three consumers: three changes × two source conditions gives six
timed efforts and eighteen consumer behavior checks. Count a shared edit once,
not once per consumer, and include all caller and verification work. Record
files/sites changed, duplicated contract declarations,
new component forks, regressions, verification work, active operator time, and
assistance cost. Verify resulting behavior and contracts in both conditions.

Counterbalance condition order and use equivalent task variants to reduce
learning effects. Include initial extraction/setup effort in a separate total;
report the number of repetitions needed to recover that cost. A shared helper
that requires consumer forks for ordinary adaptations is an adverse finding,
even if the original import graph is elegant.

## Experiment B — Introspection

Seed six paired diagnostic cases, one per category below. Each pair has two
equivalent variants, one per evidence condition: twelve assessments total, six
per condition. This replaces the earlier twelve-case/twenty-four-assessment
proposal; it is not an additional matrix.

- invalid result shape/type;
- missing or wrong-path output;
- prompt/dependency binding drift;
- invalid outcome-dependent artifact consumption;
- imported source/binding drift;
- interruption before versus after result commit.

Derive ground truth from the controller's injection manifest and known event
boundary, independently of the diagnostic output. Freeze acceptable authored
locations where expansion admits several correct explanations.

Both conditions receive the same source, task, ordinary logs, results, and
state. The treatment also receives structured compiler diagnostics, typed
contracts/effects, IR/source mapping, and relevant dependency/attempt evidence.
Score the violated contract, responsible authored location, changed dependency
where relevant, and correct next/recovery action. Record time, abstention,
wrong attribution, and false assertions that an effect ran or can be reused.
Do not score literal error wording.

Counterbalance variant assignment and condition order so the same analyst does not learn a
case's answer in one condition before seeing it in the other. If no fair
assessment is possible inside the budget, report mechanism coverage only and
leave diagnostic utility untested. Derived views are explanations of recorded
facts, not an alternative source of runtime authority.

## Experiment S — Agent Authoring And Self-Programming

Use the same operation interfaces and behavioral framework with fresh agent
contexts and held-back requirements. Separate three observed accomplishments:

1. **Authoring:** the agent chooses a composition from requirements and produces
   source that compiles and meets the behavioral contract.
2. **Feedback-driven revision:** the agent changes that source in response to
   diagnostics, runtime evidence, or a changed requirement while retaining
   unaffected obligations. A human-directed change is scored here, not as
   autonomous self-programming.
3. **Closed-loop self-programming:** given an objective rather than a prescribed
   topology/edit, the agent selects its orchestration, executes it, inspects
   available evidence, and chooses a program revision that addresses the
   observed shortfall. The controller schedules the bounded loop but does not
   choose the edit. If no revision is needed, record successful authoring; that
   episode supplies no revision evidence. Do not inject extra faults afterward
   simply to manufacture a closed-loop success.

The initial protocol covers three episodes, one per requirement family, with
an initial program and at most two revisions each. Designate a requirement-change
episode and a closed-loop feedback episode before running; retain first-version
and final-version results separately. Freeze public development checks and a
held-back final check per case. The agent may see development results and normal
diagnostics, never the final-check answer before freezing its selected revision.
Post-holdback repair is a new attempt requiring fresh assessment material.

Record each complete program revision, requested/predicted change, compile
result, actual execution/behavior, feedback exposed, and all human intervention.
Source/IR differences and type validity are supporting facts, not demonstrated
useful behavior. A human supplying topology or code disqualifies an unassisted
closed-loop claim but remains visible as an assisted result. Preserve every
failed proposal and first-attempt failure; report success versus total effort,
not only the best final artifact.

Leaf providers may be deterministic doubles to isolate orchestration, but the
authoring agent is real. Charge every authoring/revision request, including
tool-loop model turns, repair attempts, assistance, and preparation. Never label
this lane provider-free. The plan owns separate finite resource ceilings and
allocation; missing receipts are unavailable cost evidence. No runtime `eval`,
rewriting of the interpreter, or genetic algorithm is required for this claim.

An ordinary-code agent control uses the same semantic task, model/budget policy,
operation interfaces, and behavioral oracle, with normal idiomatic tooling and
language-appropriate documentation. Model familiarity and onboarding are
reported confounds. Comparative agent-authoring claims require matched episodes;
the initial three ORC episodes alone establish at most descriptive feasibility.

## Experiment O — Program Space, Then Search

Start with the existing four complete workflows: DIRECT, DESIGN_QA, PRODUCT_QA,
and RICH. Freeze prompts, model/provider configuration, tool availability, task
contract, evaluator, and budget policy. A selector chooses a whole candidate
ID; this is finite catalog selection, not generated topology or genetic search.
Enumerating four entries is the appropriate nonadaptive baseline.

The former optional twelve-proposal compile-only exercise is no longer a
standalone commitment. Fold compile rejection, structural distinctness, and
dependency/identity checks into construction and revision evidence. Later search
may vary existing review stages, supported bounds, or compatible components
within its frozen vocabulary. Pin proposals and use the full compiler, but
measure whole-run behavior for fitness. Effects describe operations, not exact
execution cost or call count.

For a later executable neighborhood, integrate one generated proposal through
ordinary compiled workflow/trial execution first. Then expand only the
predeclared vocabulary. Assess whether variants have distinct behavior and
useful quality/cost tradeoffs before choosing an adaptive optimizer.

Future genetic-programming promise depends on testable properties:

- **Closure:** many proposed changes remain well-formed and type-compatible.
- **Behavioral locality:** a small edit usually changes the intended policy,
  not unrelated contracts or prompt bindings.
- **Compositional utility:** shared modules remain useful across different
  combinations; matching types alone does not prove substitutability.
- **Manageable interactions:** review, retries, prompts, and context can
  interact; evaluate recombined whole programs instead of inheriting parents'
  scores or adding component scores.
- **Affordable selection:** evaluation is repeatable and cheaper than the
  benefit recovered over future uses; optimizer overhead counts too.

If the space is tiny, enumerate it. If larger, compare adaptive search against
equal-budget random search and the best fixed reviewed program. Invalid
proposals consume proposal budget; diagnostic-repair calls consume inference
budget. Prompt-only and topology-only ablations precede joint-search claims.
Local traces can guide proposals but never replace whole-candidate fitness.
No population store, crossover system, genome schema, or self-modifying runtime
is justified merely by calling the research evolutionary.

## Corpus And Evaluation For A Later Live Study

Prefer one scientific repair family using
`examples/demo_task_linear_classifier_port/` and the independent evaluator in
`orchestrator/demo/evaluators/linear_classifier.py`. The checked-in Rust seed is
an unfinished port: first produce a verified green target against the Python
reference, then bounded defect variants. Existing numerical inputs are not
independent repair tasks. NanoBragg is a possible later transfer check, not a
second first-stage project; the sliding-window seed has no matching checked-in
hidden evaluator and is not a ready substitute.

A proposed twelve-episode pilot is descriptive. Group whole defect families
before dividing adaptive, validation, and sealed holdout sets; keep near
duplicates and numerical variants together. Qualify split sizes and evaluator
sensitivity before candidate generation. Use at least three stochastic
repetitions per candidate/task to characterize noise, paired by task/execution
block; repetitions do not increase independent task count.

Freeze the evaluator, candidate vocabulary, prompts/models/tools, accounting,
retry/time limits, partitions, and decision rule before adaptive work. The
optimizer sees adaptive evidence; validation selects complete candidates; the
holdout is opened once after selection and analysis are fixed. Candidates and
proposers must not see held-out evaluator data: this is protection against
measurement leakage, not an execution-safety claim. A failed holdout is a
failed claim; a revised attempt needs new holdout material.

Hard objective correctness outranks soft judgment. Retain all failed runs,
timeouts, compile rejections, retries, and apparatus incidents under a
predeclared disposition rule. Missing cost receipts mean unavailable data,
never zero. Account separately for construction, adaptation, proposal,
evaluation, execution, operator intervention, and maintenance.

The accepted trial design's default confirmatory rule is ≥10 percentage points
absolute improvement with an interval excluding zero at ≤1.5× provider cost,
or statistically non-inferior success at ≥20% lower cost; its holdout floor is
≥30 independent cases with a power calculation. This small pilot neither
waives those requirements nor earns `PASS_E3`. Any experiment-specific amendment
must be explicit and frozen before the study.

## ORC-Specific Comparison And Disposition

The copied-ORC control tests reuse. DIRECT tests topology value.
Random/enumerative search tests the optimizer. **None tests the value of ORC
against another reusable representation.** Before claiming that advantage,
compare one credible reusable Python/native program with the same agent
operations, topology, evaluator, model/tools, recovery responsibilities, and
accounting. A matched-topology comparison isolates representation mechanics;
open authoring comparisons instead hold requirements and operation semantics
constant and permit different valid programs. Allow each representation its
normal reuse and inspection tools;
do not handicap the control with deliberately duplicated or opaque code.

For R1a, propose these exploratory continuation
criteria, frozen before measurement:

- Programmability: report the capability map and complete behavioral results
  for all three requirements. Correct ordinary composition establishes scoped
  feasibility, not a comparative advantage. Record the early ordinary-code
  comparison, construction cost, and any required glue or missing interface.
- Reuse: all intended compositions/adaptations retain correct behavior; shared
  definitions reduce median portfolio adaptation-plus-verification effort by at least
  20%, without additional regressions. Report setup break-even separately.
- Introspection: at least one more correct complete diagnosis out of six,
  or at least 20% less median diagnosis time with no loss in correctness;
  confidently wrong diagnoses must not increase.
- Mechanics: real checks distinguish passing and failing outputs; actual
  calls/artifacts match the declared composition; evidence identifies complete
  evaluated programs. A known broken oracle is a failed apparatus result.

For R1b, report authoring, feedback revision, and closed-loop outcomes separately
with their full costs. At least one unassisted, behaviorally verified closed-loop
revision establishes that mechanism in its case; it does not demonstrate
generality, superior economics, or optimization. Human-prescribed edits, mere
compile repair, and unchanged successful programs cannot substitute for it.

These are draft descriptive screens, not statistically powered claims. Record
each of the five axes as supported within scope, adverse, inconclusive, or
untested. Case-level outcomes and uncertainty remain visible. Neither failing
reuse and introspection nor merely asserting untested programmability decides
the entire project. Any further allocation needs a bounded question supported
by existing evidence or an explicit, limited test of a named unresolved issue.
Do not move thresholds after results.

Dependencies follow the claim: authoring measurement needs executable cases and
a functioning oracle, not positive reuse/diagnosis screens. A fixed-catalog R2
study can proceed under its own approval without successful autonomous authoring.
Adaptive R3 needs a useful executable variation space and credible evaluation,
not five positive scores or a RICH win. Reuse can remain useful if agent authoring
fails, and self-programming can remain useful if adaptive search adds no value.

A DIRECT winner narrows topology choice; it does not refute reuse. Failure of
adaptive search can leave useful workflow tooling. Reimplementation is justified
by a demonstrated valuable capability and a better alternative to an obstruction
in the current foundation. Value may be evidenced outside ORC; a credible
obstruction alone can justify a bounded redesign investigation before committing
to replacement. If fair controls erase a line's benefits, or its evaluation
cannot be made affordable and credible, stop expanding that line when no
justified remedy remains. Use the roadmap's portfolio criteria, not failure of
one evaluation/search lane, to decide whether the custom platform should end.

### Evidence For Improvement And Retirement

Minimum viable examples begin assessment; they do not complete development
along an axis. The [roadmap's axis lifecycle](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#axis-lifecycle--improve-or-retire-then-simplify)
owns concrete improvement and simplification branches. Keep evidence labels
(supported within scope, adverse, inconclusive, untested) separate from actions
(retain, improve, replacement investigation, retire); none selects work by itself.

An improvement proposal must identify an observed bottleneck, a causal change,
the recurring use that benefits, and a falsifiable expected gain. Distinguish
interface/library, author/feedback, semantic-foundation, and evaluation failures
before choosing a remedy. Where a design assumption causes the obstruction,
compare local fixes with revising that assumption, including type-system or
language overhaul and a different foundation. For example, test whether useful
composition is blocked by annotation/inference, the type model's expressiveness,
or the static/runtime contract boundary; do not presume either stronger typing
or weaker typing is the answer. Record credible alternatives and the evidence
that would distinguish them. A failed current encoding is not a failed user
capability, and an unimplemented redesign is uncertainty, not impossibility.

Include design-derived expressiveness limits in that review, not just type
ergonomics. Record the current restriction, rationale, blocked requirement,
workaround burden, and trigger for reconsideration in the existing report.
The absence of unbounded recursion is one such limitation: compare iterative
or delegated encodings with revised recursion/execution semantics when useful
work warrants it. Assess preserved composition and inspection, not just whether
an agent can perform the task outside ORC. Bounded experiment resources do not
imply a permanent language-level boundedness requirement. A chosen revision must
address affected call identity, checkpoint/resume, and source-mapping contracts;
this does not claim general recursion is already implemented or select it.

Choose the coherent target before minimizing its implementation. A small proof
may exercise a different architecture rather than patch the current one. If the
chosen design changes accepted principles or normative contracts, amend their
owning documents before implementation; do not silently bypass current behavior
or treat those documents as an immutable ban on redesign.

Compare the changed system with its frozen predecessor
and relevant simpler control, charging preparation, migration, and maintenance
as well as execution. Check both the original regression and new cases prepared
independently of the repair. A fix fitted to the demonstration is not evidence
of general improvement; repeated exposure to a holdout requires fresh material.

Each separately allocated cycle predeclares its useful improvement threshold,
cost/reuse horizon, and stopping rule. A useful baseline may remain when its
extension fails. If evidence shows no credible affordable remedy, including a
foundational alternative worth testing, retire the
unsupported claim rather than perpetually enlarge the benchmark or platform.
Inconclusive/untested results justify at most a bounded uncertainty-resolving
test or a parked decision with an explicit reopening condition, not a false
claim of impossibility. Preserve earlier evidence and report changed scope.

Retirement has an architectural obligation: identify consumers and dependencies,
remove or cancel machinery justified only by the retired claim, and verify
retained behavior. A diagnostic view may be dispensable while the compiler/run
facts it displays remain necessary. Fixed workflows, assisted authoring, and
non-agent search likewise need not depend on the strongest retired hypothesis.
Historical evidence remains evidence, not active feature-routing authority.

## Feasibility Gaps And Deliberate Omissions

Selecting R1a permits Task 1 and Task 2 preparation to establish operation-based
doubles, a real-check execution path, the development library, fair diagnosis,
and paired controls, counting their complete preparation cost. Demonstrate that
the oracle accepts different valid compositions and rejects a broken one before
freezing the assessment protocol/library and starting measurement. These are
outputs of preparation, not circular prerequisites for permission to prepare.
Failure stops the affected lane within its cap; classify the actual gap.

R1b additionally needs a demonstrated ordinary compiled-program execution path
for one generated provider-workflow composition and an accepted inference budget.
It does not inherit a mock SDK API or effectful clone-path mode that does not
exist. Select bounded integration preparation to establish the proof before
authoring measurement; do not turn a missing route into a second runtime.
Scientific corpus preparation and live domain-provider allocation remain
separate prerequisites for R2 efficacy work.

No new runtime, DSL form, generic optimizer framework, trace service, or
benchmark registry is proposed for the initial demonstrations. Existing evidence formats and compiler output
are sufficient until a concrete consumer demonstrates otherwise. No normative
spec amendment is presumed for the initial construction demonstration; any
observed contract gap must be stated before planning a capability change.
These initial scope limits do not forbid a separately justified redesign of
the language, type system, or its principles after the assumption review.

This makes broad self-evolution claims slower to earn, leaves some repetitive
wrapper authoring, and provides limited early statistical power. Those are
explicit costs of answering the smallest useful question first, rather than
assuming either abandonment or a ground-up rewrite is already warranted.
