# Workflow Lisp Evolution Follow-On Roadmap

Status: current research sequencing, overhauled on 2026-09-08 at the owner's
request. This roadmap owns prospective order and disposition; the
[research charter](2026-09-08-orc-research-charter.md) owns the questions,
the [demonstration design](../design/orc_reuse_introspection_search_experiment.md)
owns the experiment, and the
[implementation plan](2026-09-08-orc-research-demonstration-plan.md) describes
selected assisted development and conditional successors. The reduced R1a pilot,
assisted C1 feasibility, and code-grounded qualitative ergonomic assessment are
recorded. The proposal's documentation portion is addressed; the C1
receipt-interface implementation remains unselected.
On 2026-09-28 the owner selected CF-1a and slated CF-1b ahead of R1b's
review/revision composition; see the
[CF-1 selection record](#cf-1--composition-first-procedures-pending-unselected).
CF-1a is closed, CF-1b is implemented at target 2.33, and CF-1c consumer
migration is on hold. On 2026-09-29 the owner approved the defect repairs of
the [value/effect decision brief](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md) and the brief's feasibility spike after
them. The repairs and spike are complete; gate G1 selected evaluated
execution, with the closed-program compiler selected as Phase 2 at target
2.35. The owner's 2026-10-01 delivery amendment introduces an early migration
pilot and consumer-driven later additions; see
[Independent Work And Successor](#independent-work-and-successor).
Publication alone does not select
later studies, new language surfaces, or source promotion.

## Direction And Evidence

Start from ORC's existing composition and inspection capabilities without
presuming its type system, language principles, or representation are the right
final foundation. Test five axes independently: programmability/compositionality,
reuse, introspection, self-programmability, and optimization. Tool execution
belongs to the agents/providers; ORC describes and observes their composition.
Novel construction, ergonomic reuse of abstractions, useful diagnosis, actual
agent-authored feedback/revision, and search advantage need different evidence.
A good fixed topology is not proof of a good search method, and neither
proves that ORC is the best representation.

Each axis receives its own supported-within-scope, adverse, inconclusive, or
untested evidence assessment and a separate investment decision. Failed reuse
and diagnosis screens do not automatically park the whole project; untested
promise does not automatically authorize expansion. The
[design](../design/orc_reuse_introspection_search_experiment.md) owns proof
obligations; the consequent-action branches below own what to improve, retain,
replace, or abandon after assessment.

E0 direct control, E1 pinned child execution, and E2 trials are complete under
their existing component contracts and recorded final reviews. Their evidence
is preserved below. E3's historical selection is not implementation completion,
a new selection by this document, or a waiver of the proposed research plan
and budget gates. No new language surface or general optimizer is selected.

ES tests a fixed QA-placement comparison. A RICH win is neither a prerequisite
for any of the five axes nor evidence that they work.
Existing `BLACK_BOX_SUFFICIENT`, `OBSERVATION_EXTENSION_REQUIRED`, and
`STOP_E3_HYPOTHESIS` report values retain their fixed-screen meanings and
bytes. They no longer select, stop, or automatically expand future research.
The current roadmap disposition, not those legacy field names, owns that
decision. Scientific rules, denominators, and unfavorable results remain
unchanged.

## Current Research Sequence

The later [execution-scope amendment](#current-es-boundary) retires the old
ES/research/trial executors from the package. Sequence/proposal and scientific
dispositions below remain distinct from current executable availability; any
future selected study must use an admitted route rather than the removed SDK.

| Unit | Question and bounded work | Entry and exit |
| --- | --- | --- |
| R0 — ES disposition | Owner selected **prelaunch park** on 2026-09-08; preserve the completed prompt correction and frozen scientific evidence. | Complete as a disposition, not scientific completion. [Recorded hand-back](#current-es-boundary); resumption needs explicit owner selection and the existing adoption gate. |
| R1a — construction, reuse, and introspection | Reduced pilot closed with partial construction, unavailable reuse-proxy measurements, and inconclusive diagnosis. Assisted C1 ORC/Python feasibility and a code-grounded qualitative ergonomic assessment are recorded. The documentation portion of the follow-on is addressed; the remaining C1 original/terminal receipt-interface repair is ready but unselected. See the [active plan](2026-09-08-orc-research-demonstration-plan.md#proposed-follow-on--explicit-current-value-handoff) and [execution report](../reports/2026-09-08-orc-research-demonstration.md#assisted-c1-development-and-corrected-interpretation). R1b, R2, and R3 remain unselected and require separate selection. | Compare real behavior and actual development friction before substantial redesign. Neither three successful novice builds, shared-edit propagation, nor a token threshold defines reuse ergonomics. If representative evidence is absent, leave the axis unassessed. A fresh scored comparison needs its own selection and held-back final cases, not a rerun of the old matrix by default. |
| R1b — agent authoring and self-programming | Separately budgeted actual agent authoring, feedback-driven revision, and one agent-chosen orchestration-improvement episode using the review-handoff family. Normal tools, execution and debugging belong inside each authoring session; scripted leaves do not test prompt-quality improvement. | Requires a working execution path, oracle, and composition cases, not passing R1a's reuse/introspection utility screens. Its review/revision composition authors against the CF-1b value-returning review helper, not `std/phase`, so that a known library defect is not measured as authoring friction; if CF-1a stops CF-1b, R1b proceeds on `std/phase` with that defect recorded as a confound. A cost/time envelope appropriate to normal sessions and a named model require approval before allocation; task-level revision episodes do not impose a compiler-only or fixed-model-turn loop. Scripted leaf providers do not make authoring free or establish task efficacy. |
| R2 — task qualification and finite catalog | Qualify one live family before candidate work: prefer session-derived review/planning improvement when independently evaluable, with linear-classifier repair as the hard-oracle alternative. Compare a finite authored catalog under one separately preregistered budget, not two studies. | Separate review and explicit allocation; R1b success is not required. Retain actual task failures and cost; no general effectiveness claim from a descriptive pilot. |
| R3 — search and representation | Test adaptive topology/prompt search against fixed and enumeration/random controls; compare the same protocol as an agent skill and credible reusable Python/native orchestration before claiming ORC-specific superiority. Evaluate whole-program and combined-change effects. | Requires a usable executable program space and evaluation, not all five axes passing. Separate bounded plan and budget; the proposed [structural search roadmap](2026-10-18-orc-structural-search-roadmap.md) drafts that plan, places catalog enumeration before any adaptive search, and remains unselected. Broader generated provider-workflow execution is an implementation capability question, not a prerequisite safety project. |

These units obtain evidence; they are not a demonstration-only roadmap or an
automatic march toward R3. Each unit's review also selects a proposed action
from the axis lifecycle below. An improvement or retirement can follow R1a,
R1b, R2, or R3 without waiting for all five axes to be tested. Execution still
requires explicit selection and its own bounded allocation.

Language/foundation improvements are tracked independently:
[EL-1](#el-1--effect-contracts-and-analysis-cleanup-pending-unselected),
[EC-1](#ec-1--pure-call-expression-composition-pending-unselected),
[PC-1](#pc-1--first-class-provider-context-pending-unselected),
[CF-1](#cf-1--composition-first-procedures-pending-unselected), and
[W3](#w3--local-hooks-with-inferred-context).
Each has its own feasibility and consequence gates. They are not extra research
units, new R1a deliverables, or automatic prerequisites for the five-axis studies.
One explicit exception is recorded: CF-1b precedes R1b's review/revision
composition by owner selection on 2026-09-28.

The separate [evaluated-execution plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md#delivery-order-and-preserved-capabilities)
owns runtime delivery: Phase 2 closed program → Phase 3 executable core →
Phase 6a pilot → pure lexical-capture correction → Phase 4c/W3 → Phase 5
parallel map → Phase 6b maintained-consumer migration → Phase 7 retirement,
per owner selection on 2026-10-07. Other Phase 4 additions remain independent.
Portable context is a named later delivery, not silently included in the
first-release provider subset. Composition, macro provenance, typed prompt
and result contracts, and artifact production/consumption/lineage are
preserved obligations, not expendable simplifications. This implementation
sequence neither adds a research unit nor selects R1b/R2/R3 or a general
search framework. Pilot authoring evidence informs improvements; it does
not require all five axes to pass before useful capabilities can ship.

Native sequential turns are separately recorded as
[PQ-1 in runtime Phase 4](2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns)
on 2026-10-01 and selected on 2026-10-14. The first slice is implemented at
target 2.38: the two-agent `design_review_execute` variant on Claude and Codex.
[PQ-1a](../reports/2026-10-14-agent-sessions-pq1a-qualification.md) records
deterministic proofs and bounded adapter smokes; the separately authorized
clean and failed/resumed acceptance comparison (PQ-1c) has not run. The
`reviewed_change` coder variant remains a future second slice, with its turn
shape selected then. [Agent Sessions](../design/workflow_lisp_agent_sessions.md)
supersedes the [queue design](../design/workflow_lisp_provider_prompt_queue.md)
for first delivery, with one shared native-turn owner and a typed memo commit
per turn. This adds no research unit or prerequisite for portable context,
the executable core, or the early migration pilot.

The [demonstration plan](2026-09-08-orc-research-demonstration-plan.md) owns
detailed ceilings and controls; no machine-readable roadmap manifest is added.
Its selected recovery follows the design's [normal agent sessions](../design/orc_reuse_introspection_search_experiment.md#normal-agent-sessions-and-evaluation-boundary):
ordinary Codex/OMP authoring, with task delivery, accounting and final evaluation
outside the coding loop. Keep normal project instructions, tools and context
management; isolate final answers rather than disabling the agent's environment.
The earlier no-tools/three-turn results remain constrained-generation evidence,
not a verdict on practical tool-enabled authoring. Preserve successful development
work and its actual configuration; no clean-benchmark relabeling or automatic rerun.

The original R1a protocol replaced its earlier proposal with 24 behavior
cells: four frozen arms × three regression checks (12), three novel
composition cases × three behavior checks (9), and one matched Python/native
construction case × three checks (3), plus six metered portfolio adaptations,
each verifying all three consumers (eighteen consumer checks). Owner subtraction
removed exhaustive identity/recovery gates. Reduced construction and four available
D3/D4 diagnostic assessments are now recorded; reuse lacks a complete measured
baseline portfolio. See the execution report's reduced measurement closeout.
The owner rejects that portfolio proxy as the meaning of reuse: the current
question concerns ergonomic reuse of `.orc`, assessed through concrete usage and
reasoned judgment. Already-produced maintenance tests check behavior only.
The brittle aggregate/ledger rejections also exposed an avoidable evaluation
design failure, not merely missing disclosure. Future selected checks must test
meaningful task/consumer obligations and accept equivalent implementations;
invalid rejections cannot support language-quality conclusions. Preserve the
historical checker results without reviving their incidental constraints.
Its reduced diagnostic allocation was D2/D3/D4: three pairs/six assessments.
Preserve the original six-pair/twelve-assessment record and D1/D5/D6 limitations;
do not claim its threshold from the reduced set. The active demonstration plan
owns current selection; these retained counts do not prescribe another pilot or
hold the selected development task behind unavailable historical cells.
The standalone twelve-proposal compile probe remains retired;
relevant compile checks belong inside authoring.

R1b's authoring/revision and closed-loop budget is separate from the selected
agent-assisted R1a allocation. The early Python/native control tests construction feasibility, not
general representation superiority; the fuller comparison remains required
before a comparative claim. Mechanism checks and scripted-leaf success do not
establish autonomous task quality, measured diagnosis benefit, or optimization
advantage. Missing assessment evidence must remain missing, not be replaced
with test counts.

### Session-Derived Priorities And Consequences

The [mining report](../reports/2026-09-08-orc-session-patterns.md) supplies
development examples, not independent task counts, current bug diagnoses, or
evidence that the proposed workflows work. The [design](../design/orc_reuse_introspection_search_experiment.md#session-derived-workloads)
owns their behavioral translation. These priorities specialize the existing
R1a/R1b cases and conditional work; they add neither units nor allocations.

First compose review/revision with the selected completion handoff, preserving
accepted work whose relevant dependencies remain valid. Then test an agent
choosing a useful orchestration revision from observed shortcomings. Keep
fresh assessment families distinct from mined episodes and require a
non-orchestrator consumer within the existing construction portfolio.

Prefer the [adaptive scientific-study transfer](../design/orc_reuse_introspection_search_experiment.md#adaptive-scientific-transfer)
motivated by PtychoPINN: reference-based diagnosis, pilot/value assessment,
method reconsideration, and selective continuation with useful prior evidence.
Qualify it inside the existing three requirements and their scenarios, not a
fourth family or live GPU campaign. Native runners/scorers remain the baseline;
providers perform tool use and scientific judgment. Initial scripted leaves
test composition, not discovery of a physical cause. R2 may qualify scientific
planning within its existing review/planning family under its separate budget.

Carry the counterexamples into assessment and consequent action: do not rerun
valid prior controls solely to make a pristine aggregate, optimize a proxy
that misses the selected goal, or abandon a promising direction solely after
a fixed number of low-gain attempts. Providers distinguish an implementation
defect, inadequate evidence, a weak method, and a premise worth revisiting;
current-comparison evidence still has to satisfy its actual contract. Reuse,
repair, a different method, or an explicit changed comparison can each be the
right consequence. A search claim must vary orchestration policy, not merely
the scientific model or its hyperparameters. These refinements change no unit,
sample count, execution allocation, or active accounting/recovery decision.

Recovery, scoped steering, and batch-contribution attribution are pressure
cases or separately selected consequences, not additional mandatory projects.
After evidence, use Task 7 to improve the demonstrated bottleneck or retire its
extra machinery: compose existing recovery with recurrence/progress checks;
prove receiving/applying scoped guidance rather than merely sending it; or
evaluate interacting changes before adding search operators. Prefer existing
stdlib procedures, management skills, and ordinary tooling to duplicate engines.
Preserve useful fixed workflows if a richer controller or autonomy claim fails.

Repeated review churn, rising glue/bookkeeping cost, or metric gain without
task progress should prompt provider-led reconsideration of the objective,
decomposition, evaluator, or language assumptions. Do not prescribe more retries
or reviewers by default. A changed evaluation contract requires an explicit
new comparison and fresh assessment; it cannot improve an old score retroactively.
External transfer and matched simpler controls distinguish user value from
repairing complexity introduced by this orchestrator itself.

Execution safety is not an investment criterion or research objective in this
sequence. Existing clone-path execution currently accepts deterministic
effect-free programs; that is an implementation fact, not evidence that
provider-backed ORC search lacks value. This documentation change does not
alter runtime behavior. It does not adopt the historical generated-execution
environment gates as prerequisites for the new research program.

## Axis Lifecycle — Improve Or Retire, Then Simplify

A minimum viable example establishes a starting point, not the finished
capability or a permanent entitlement to maintenance. After each assessment,
whether an experiment or a grounded qualitative design/usage review:

1. **Diagnose:** distinguish a real conceptual/economic limit from a library,
   authoring, foundation, or evaluator defect. Preserve the adverse result;
   a broken apparatus leaves the substantive claim untested.
2. **Reconsider the solution, then choose a consequence:** retain a useful
   bounded capability; improve a named bottleneck; investigate a type/language
   redesign or replacement foundation; or retire the unsupported scope. Apply
   the assumption review below before treating current-foundation limits as
   grounds for abandonment. Inconclusive work may receive a specific uncertainty-resolving assessment,
   not an open-ended extension. With no justified allocation, park the line
   without new feature work and name what evidence could reopen it.
3. **Improve and re-evaluate:** choose a direction with a causal account of why
   it should help, a named recurring use, an expected observable improvement, and a
   predeclared stop rule. Then build its smallest discriminating proof, which
   need not be the smallest patch to today's architecture. Allocate one bounded
   cycle at a time. For ergonomic reuse, compare real before/after usage and
   explain the judgment; qualitative human/LLM review is valid and no numerical
   proxy is compulsory. For behavioral claims, compare old/new behavior on
   relevant cases and regressions; fixing one example alone is not transfer.
4. **Close the loop:** keep a change only for demonstrated benefit within its
   stated scope. Further cycles require fresh evidence, not renewed promises.
   If no credible affordable improvement or foundational alternative remains,
   abandon that research claim and
   execute its scoped simplification. Failure to improve a useful baseline can
   retire the extension while retaining that baseline.

The following are conditional development directions, not five preapproved
feature projects. Evidence criteria and resource ceilings are set before each selected
cycle; the initial R1a/R1b allocations do not fund these additions.

### Assumptions Are Revisable, Not Protected Assets

Judge the user capability separately from its current realization. Failed ORC
composition, typing, or generation is evidence about that realization—not proof
that the capability is unhelpful or impossible. Existing design principles are
choices to explain and, where evidence warrants, revise. Past investment and
accepted documents do not make them permanent research constraints.

When a foundational assumption appears responsible, compare materially different
responses before prescribing local repair or abandonment: improve the current
implementation; redesign the responsible subsystem or language; use a different
foundation; or drop the capability. Judge each against the user objective,
expressibility, predictable behavior, ergonomics, evidence quality, and lifetime
cost. State what observation would distinguish the credible alternatives. A
named obstruction or useful ordinary-code control can justify a bounded design
investigation; do not require the obstructed ORC implementation to first prove
the capability that it prevents.

For example, if typing impedes useful composition or agent-authored changes,
ask whether the cause is annotation burden/inference, insufficient expressiveness,
the chosen type model, or the division between static and runtime contracts.
Consider a type-system overhaul, weaker/different static guarantees with runtime
validation, revised module/control-flow semantics, or a host-language foundation
where relevant—not only more adapters around the current checker. These are
alternatives to investigate, not a prescribed weakening or a claim that types
are the problem. Preserve required observable behavior; do not protect a
particular way of proving it without comparing its benefits and costs.

Track design-derived language limitations in the same axis report: the owning
rule and its rationale, the blocked use or workaround cost, and the evidence
that would justify reconsideration. For example, the
[core-calculus design](../design/workflow_lisp_core_calculus_middle_end.md)
§13.3 excludes unbounded recursion, while its §15 discusses bounded general
recursion as future work; the
[frontend specification](../design/workflow_lisp_frontend_specification.md)
§13 describes bounded loops. These are current design boundaries, not permanent
research prohibitions or proof that recursion is unnecessary.

If a useful recursively decomposed task or dynamically discovered search tree
is awkward to express, compare explicit worklists/iteration, delegation to an
agent, and revisiting recursion, call frames, or the execution model. Count
whether a workaround hides composition, introspection, or editable program
structure; delegation is not automatically equivalent for these axes. Reopen
the relevant design when the blocked use or recurring workaround burden gives
a credible reason, rather than merely raising a bound or rejecting the use case.
Language-level expressiveness and a run's resource budget are separate: a study
can have finite time/cost ceilings without requiring every program to have a
statically known recursion depth. No recursion feature is selected here.

Minimality applies after choosing a viable design. A larger coherent redesign
may be simpler than accumulating local workarounds. Conversely, redesign is not
an automatic escape from unfavorable results: use the smallest proof that tests
its rationale before committing to migration, and revise governing designs/specs
explicitly if chosen. Current runtime contracts still describe current behavior;
they are not a prohibition on proposing replacements. Exhausted allocation is
a funding/uncertainty result, not proof that redesign cannot work.

| Axis | Principled improvement after the first evidence | Retirement trigger and consequent simplification |
| --- | --- | --- |
| Programmability / compositionality | Turn recurring glue, nonlocal edits, and failed combinations into explicit component-boundary or semantic problems. Compare interface/documentation fixes with type-system, module/control-flow, or language redesign when those assumptions cause the difficulty; local patches have no automatic priority. Recheck new combinations, predictable edit consequences, and construction effort against idiomatic Python/native composition. | If ordinary composition remains bespoke integration, or simpler composition meets the same needs at lower total cost and no credible redesign or remedy warrants a bounded proof, abandon the general-purpose ORC authoring claim. Keep only independently useful fixed workflows or the narrow composable subset; cancel unsupported generalization and migrate affected consumers to the simpler representation. Generated-space work must narrow to what remains expressible. |
| Reusability | Review ergonomic reuse of actual `.orc` abstractions: discoverability, understandable contracts, parameterization/adaptation, composition, local reasoning, and required glue/type conversions/forks. Use concrete caller examples and qualitative human or LLM-assisted judgment; simpler ordinary-code examples can clarify the tradeoff. Improve the evidenced friction, not a contrived portfolio score. | If an abstraction remains awkward or adds no useful leverage, simplify its interface, inline/specialize it, or revisit the language/type assumptions causing the problem. Regression tests retain behavior but do not prove ergonomic value. Leave reuse unassessed when representative examples or credible judgment are unavailable; no fixed consumer count, token-saving threshold, or optimizer-driven library expansion. |
| Introspection | Target observed attribution/recovery mistakes: make existing source, dependency, and attempt evidence answer those questions with fewer steps. Correct misleading mappings and remove redundant views before adding instrumentation. Recheck diagnosis correctness, time, and confidence on unseen faults against normal logs/debugging. | If structured inspection adds no practical diagnostic value after justified corrections, stop richer introspection work and remove experiment-only viewers, duplicate projections, or extra instrumentation with no other consumer. Retain compiler facts and run evidence required by actual execution, recovery, or another supported axis; failure of a view does not invalidate those contracts. |
| Self-programmability | Identify whether failure is expressing a change, reading feedback, choosing a useful orchestration revision, or transferring it. Compare authoring/feedback fixes with a different source representation, type discipline, or edit model when those constrain agents; test agent-chosen revisions across fresh goals with less assistance and preserved unrelated behavior. Compare matched ordinary-code agents before claiming an ORC advantage. | If agents cannot produce beneficial revisions within viable total effort and no credible representation/feedback/foundation alternative warrants investigation, retire the unsupported autonomy claim. If ordinary-code agents succeed more economically, consider moving the capability there rather than abandoning autonomy itself. Remove displaced revision machinery and speculative self-modification surfaces; retain useful assisted authoring or human-authored workflows. This does not by itself retire non-agent search. |
| Optimization / search | First establish useful behavioral diversity and affordable evaluation. Improve measured bottlenecks in mutation validity, edit locality, recombination, interactions, or evaluation cost. Add adaptive or genetic operators only where they can improve independent quality/cost outcomes over fixed, enumeration, and random controls, including search overhead amortized over actual future use. | If variants have no useful differences, evaluation cannot be made credible/affordable, or adaptive search offers no repayable advantage after justified corrections, abandon the unsupported search level. Use a fixed default or small enumerated catalog; cancel/remove optimizer loops, population/crossover stores, and search-only metadata where they exist and lack another consumer. Keep useful programs and their evidence. |

### Portfolio Consequences And Completion

All retirement triggers above include the assumption review, not merely failed
local patches. An axis is not all-or-nothing: a useful inspection subset, assisted authoring,
or finite catalog can survive failure of richer versions. Record the retained
scope and the abandoned claim explicitly. A dependent branch must either use
that retained subset or be retired too; it cannot silently assume the discarded
capability. Fixed-catalog R2 does not require self-programming; non-agent search
can survive failed agent authoring. If the executable composition space itself
is inadequate, generated-program claims need narrowing or a demonstrated
replacement before proceeding. Diagnosis/reuse utility failures alone are not
automatic vetoes of those branches.

Use this evidence to choose the project's foundation, not just its next demo:

- **Build upon directly:** retained axes provide practical value and their
  bottlenecks admit local improvements with worthwhile maintenance cost.
- **Redesign, reimplement, or migrate:** a valuable capability is evidenced,
  an obstruction belongs to this foundation, and a small alternative proof
  removes it. Evidence of value can come from other implementations; current ORC
  success is not required. Revisit the type system or language principles if
  implicated, and compare adopting an adequate existing foundation; count migration
  and ongoing ownership, and delete the displaced path rather than maintain
  two permanent systems. No whole-project rewrite follows from one failed case.
- **Abandon the custom platform:** fair alternatives cover every retained use
  at lower total cost and no justified improvement remains. Stop expansion,
  migrate or explicitly close remaining consumers, and retire the unsupported
  platform. Archive research evidence rather than relabel unfavorable results.

Every retirement must name the consumers to migrate or retain, speculative work
to cancel, code/configuration/docs to remove or narrow, and contracts still
needed elsewhere. For never-built machinery, cancellation is the simplification;
do not invent code to delete. Closure requires verification of retained behavior
and updated discovery/selection routing, not just a report saying “abandon.”
Historical results and pinned ES assets are not deletion targets. This amendment
selects no removals and does not reopen or cancel independent P/ME/OMP/EL-1 work.

<a id="el-1--effect-contracts-and-analysis-cleanup-pending-unselected"></a>
<a id="el-1--effect-contracts-and-analysis-cleanup-selected-239"></a>

## EL-1 — Effect Contracts And Analysis Cleanup (Delivered: 2.39)

**Governing design:**
[Effect Ledger Simplification](../design/workflow_lisp_effect_ledger_simplification.md).
**Status:** EL-1a/b/c delivered at target **2.39** for the selected bounded
contract and two maintained consumers. [Task 5](2026-10-15-orc-simplification-roadmap-extension.md#target-239-selected-implementation)
owns implementation, independent acceptance, public lifecycle evidence and
remaining evidence limits. The ES prelaunch-park hand-back recorded above is
satisfied. Omission infers effects, empty/named restrictions remain checked,
and new definitions compose inline without authored lowering; finite private-form
admission preserves genuine packaged stdlib expansion.

The [2.35 source floor](2026-10-15-orc-simplification-roadmap-extension.md#f--pre-235-source-compatibility-retirement)
retires pre-2.35 source/import/REPL/LSP compatibility. Six maintained stdlib
modules use 2.35; admitted definition origins 2.35–2.38 retain their exact
ordinary declarations, specialization exceptions and lowering semantics.
Historical data readers do not reopen source admission. EL-1d is cancelled
for this selection: existing summary consumers remain real, and no named
maintenance/performance need justifies a representation rewrite. The
[audit](../reports/2026-09-08-workflow-lisp-effect-tracking-audit.md) remains
prior-behavior evidence, not an implementation or utility proof.

Prioritize inference-default authoring with meaningful optional restrictions and
inferred inspection over the existing analysis representation. Internal cleanup
is a separate conditional decision, not the price of obtaining those benefits.

The [agent-authoring plan](2026-10-02-agent-authoring-improvements-plan.md)
reuses the delivered 2.39 contract as stream D; it does not create a second
effect-inference implementation. Target 2.35's effect contract stays fixed.

| Step | Bounded work and evidence | Consequence / next decision |
| --- | --- | --- |
| EL-1a — resolve contracts and feasibility | Delivered the reviewed 2.39 version boundary, defining-scope subjects, generated omission, definition-origin imports, post-specialization restrictions and inferred/incomplete inspection contract. | The frontend, effect-ledger and versioning owners govern the supported contract; no new analysis representation or runtime was selected. |
| EL-1b — authoring and inspection vertical slice | Delivered inferred omission, identity-aware subset/empty checks, origin-aware specialization, REPL/LSP projections, caller-owned inline composition and finite source admission using existing inference. Public compile/run/resume and admitted old-origin controls belong to Task 5. | The procedure guide and capability matrix route to the bounded recipes and evidence. Evaluated LSP F2 remains OPEN_NOT_WAIVED; annotation relief does not establish general composition or utility. |
| EL-1c — improve or narrow from authoring evidence | Delivered the two selected 2.39 consumer migrations and four local comparisons: dependency addition/removal, provider substitution under a ceiling, and imported hook adaptation. The compact search omits its mirrored command ledger; the proposal retains intentional purity/launch-command restrictions. | The ordinary evaluated runtime, command configuration, policy, schemas and returned values remain. Local compile/dataflow evidence does not measure human/agent productivity, provider quality or broader utility; untested axes remain untested. |
| EL-1d — optional consumer-led analysis cleanup | Cancelled for this selection; retain the existing EffectSummary consumers for placement, cycles, lowering, inspection and admission serialization. | No fixed-footprint rewrite, new facts schema or permanent dual analysis. A future cleanup requires a concrete maintenance or measured performance need and separate selection. |

**Entry and dependencies:** the owner selected EL-1a/b/c and target 2.39 after
the existing ES hand-back. The Task 5 plan bounds two maintained consumers,
existing compiler/editor owners, four local authoring comparisons, and public
compile/run/resume controls; it introduces no paid-provider allocation or study
selector. The delivered sequence preserves reviewed EL-1a → EL-1b → EL-1c
dependencies. Optional EL-1d is not a prerequisite for EL-1b or EC-1 and is
cancelled here. No other research allocation or frozen ES package changes.

**Compatibility and closure:** intentionally new syntax gets versioned
acceptance/rejection tests; internal cleanup gets unchanged-behavior checks.
Preserve completed-result reuse, concrete operation/source identity, and
historical evidence. Each completed step records supported behavior, utility
limits, the next justified improvement or cancellation, and any displaced
machinery to remove. This work neither gates an E/ES/P exit nor changes studies.

## EC-1 — Pure-Call Expression Composition (Pending, Unselected)

**Governing proposal:**
[Pure-Call Expression Composition](../design/workflow_lisp_pure_call_composition.md).
**Status:** research workstream pending and unselected. Separately owner-requested
Package C of the [composition implementation plan](2026-09-22-value-and-continuation-composition-implementation-plan.md)
implements the resolved-inline subset at target 2.30, with selected-hook,
once-only evaluation and public committed-boundary resume evidence. Reuse that
mechanical evidence when selecting EC-1 work; do not repeat implementation merely
to satisfy the historical sequence below. Practical benefit and principled
expansion/retirement remain separate decisions. No research allocation changes;
EL-1's optional annotations are not a prerequisite.

| Step | Bounded work and evidence | Consequence / next decision |
| --- | --- | --- |
| EC-1a — prove the normalization boundary | Name a repeated composition obstruction and compare existing `defun`/explicit-binding controls. Resolve phase placement before source rejection, once-only argument representation, specialization/proof scope, private-boundary identity, and target/version semantics. Start with the audit's inline helper but include a runtime-dependent case. | Produce the smallest reviewed implementation plan supported by evidence. Classify actual effects, type/transport, representation, and identity limitations separately; consider shared normalization or a foundational correction before declaring the consumer infeasible. |
| EC-1b — supported inline composition | Admit the design's resolved-inline subset across record/union fields, list elements, pure maps, and pure callers; include nested/imported/selected-hook cases, not just a constant. Verify argument order/count, branch and map scope, errors, source attribution, and public-entry run/resume; retain real effect/type/transport restrictions. | Publish an honest supported subset and remaining gaps. Delete displaced edge-only rejection or duplicate conversion paths for the new regime; do not count a fixture-specific bypass or helper duplication as completion. |
| EC-1c — principled expansion or retirement | Apply the subset to recurring reuse/context consumers and assess all five axes independently where evidence exists. Measure duplicate helpers, coupled edits, diagnosis, author/agent repair effort, and useful candidate quality/cost. Compare simpler controls; investigate expansion/control costs rather than assume normalization is free. | Extend shared mechanisms where worthwhile. Revisit callable roles, types, collection transport, or language/lowering assumptions when they repeatedly obstruct useful work. Retain a valuable subset, redesign its foundation, or retire the approach and remove scaffolding; a passing minimum is not the endpoint and one failed axis does not cancel the others. |

**Entry and dependencies:** a named consumer, explicit selection, and a finite
bounded allocation; accepted design/version contracts and reviewed plan before
implementation. EC-1b follows EC-1a; EC-1c follows a working representative
subset. Preserve the compiler/frozen-study hand-back boundary for overlapping
work. Neither EL-1 completion nor a successful RICH study is required. Prefer
EC-1 ahead of annotation relief when the actual obstruction is expression
composition; do not force an unrelated cleanup first.

**Foundation review:** bounded loops, static references, the `defun`/`defproc`
split, and absent unbounded recursion are revisable design choices, not automatic
abandonment criteria. A concrete need may justify a type-system or language
redesign, but this listing does not authorize general effect polymorphism,
runtime evaluation, new execution engines, or erasure of private checkpoints.
Completion evidence must name the retained contract and consequent action.

**Coordination with PC-1:** select only a demonstrated shared prerequisite.
Materialized context transformations can exercise EC-1, while loading/capture
and context transport have different owners. PC-1a does not require all of
EL-1/EC-1, and neither is funded by R1a. Scheduling and source ownership for
overlapping compiler edits must be coordinated before execution.

## PC-1 — First-Class Provider Context (Pending, Unselected)

**Governing proposal:**
[Provider Context Values](../design/workflow_lisp_provider_context_values.md).
**Status:** research workstream pending and unselected. Separately owner-requested
Package D of the [composition implementation plan](2026-09-22-value-and-continuation-composition-implementation-plan.md)
implements portable ordinary Codex context at target 2.31. Public typed/private/
generic/loop carriage, pure editing, independent branches, committed-boundary
resume and real normal-tools capture/fresh binding are verified. This is not
native/cross-provider support or research utility evidence; the small comparison
did not establish an advantage over a result handoff. No R1a allocation or
research selector changes follow from implementation.

The intended capability is explicit immutable conversational dataflow: capture
context, pass/return it through ordinary reusable procedures, transform it, and
bind it to another provider call. Portable content and native continuation have
different promises; existing session handles, private execution `RunCtx`, and
content-free prompt evidence are not implementations of this proposal. Tools
remain provider/agent-owned. Use the [authoring guide](../lisp_workflow_drafting_guide.md#portable-provider-context)
for the implemented slice; broader design sketches remain proposals. A selected
PC-1 task should audit and reuse the existing implementation/evidence, then
address a real consumer or unsupported boundary, not recreate the same minimum.

| Step | Bounded work and evidence | Consequence / next decision |
| --- | --- | --- |
| PC-1a — resolve feasibility and design | Name a recurring investigation/handoff consumer and its artifact/skill/SDK baseline. Review the proposal and qualify real adapter capture/import; separately prove immutable native branching if claimed. Test the required generic, aggregate, imported-return, and loop-carried value path, and atomic result/context publication. | Select a reviewed implementation plan only for a demonstrated useful direction. Classify failures as adapter, representation, type/transport, or conceptual limitations; consider a coherent foundation redesign before abandoning the capability. An unsupported native route need not stop a viable portable route. |
| PC-1b — compositional vertical slice | Implement capture → reusable return → explicit transformation → two independent bindings, with source/coverage/loss inspection and completed-boundary resume. Use declared provider identities initially; runtime-selected provider identity is separate optional foundation work. Verify actual delivered context and absence of sibling conversational leakage. | A passing example establishes the mechanism only. Accept the supported scope, identify actual recurring costs/limitations, and proceed to an explicitly budgeted utility/improvement decision rather than declaring all five axes proved. |
| PC-1c — improve and compare | Measure shared adaptation, diagnosis, agent-authored context-policy revision, and whole-task context-policy search where each is justified. Compare total authoring, capture/conversion, input-token, storage, and maintenance cost with credible ordinary handoffs on fresh tasks. Improve the identified bottleneck one bounded cycle at a time. | Apply independent five-axis outcomes and the assumption review. Extend selection/compaction, adapter coverage, or language foundations only when evidence supports them; do not require every axis to succeed before retaining a useful subset. |
| PC-1d — retain, redesign, or retire and simplify | Record retained representations/operations, unsupported claims, affected consumers, and the evidence behind the chosen consequence. Re-evaluate any foundational alternative before committing to migration. | Retain demonstrated useful context flow; replace an obstructive foundation where justified; otherwise remove/cancel unused context operators, duplicate session/transcript plumbing, and experiment-only machinery. Preserve independently useful provider/session and artifact contracts. Cancellation is sufficient for never-built work. |

**Entry:** explicit owner selection of the bounded PC-1 step, accepted governing
design where implementation is proposed, reviewed component plan, and a finite
allocation. A named obstruction or useful ordinary-code control can justify
PC-1a; neither a positive result on all five axes nor completion of R3 is
required. Do not demand that today's type system first express the capability
whose obstruction motivates its redesign.

**Foundation review:** preserve ordinary composition as the goal, not a root-only
session-artifact workaround. Reconsider type/transport, module/control-flow,
static provider selection, and recursion assumptions when concrete uses justify
it. Native opacity limits introspection; context does not clone a workspace or
establish independent judgments. Avoid a universal memory service or parallel
session manager. [PQ-1](2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns)
owns the separate native-turn delivery: share adapter/codec owners without
making portable capture wait for native continuation or claiming that either
implements the other.

The [pure-call composition target](../design/workflow_lisp_pure_call_composition.md)
and [revised effect proposal](../design/workflow_lisp_effect_ledger_simplification.md)
identify possible shared foundation corrections. PC-1a distinguishes actual I/O,
transport/type gaps, expression representation, and private-boundary identity;
it does not make either entire proposal a prerequisite or treat optional
annotations as proof of context composition.

**Routing:** this adds one pending, unselected workstream and no executable
manifest/queue row. The five research units and their current allocations stay
unchanged. The [current research sequence](#current-research-sequence) and
its [demonstration plan](2026-09-08-orc-research-demonstration-plan.md#proposed-follow-on--explicit-current-value-handoff)
own R1a's current disposition and selection of any remaining implementation.
PC-1 cannot be launched by its coordinator without separate selection/funding.

## CF-1 — Composition-First Procedures (Pending, Unselected)

**Governing proposal:**
[Composition-First Procedures](../design/workflow_lisp_composition_first.md).
**Status:** CF-1a selected by the owner on 2026-09-28 as a bounded task and
closed the same day (amendment boundary below);
CF-1b slated as an owner-requested package ahead of R1b, conditional on CF-1a;
CF-1c absorbs the pending qualitative utility evaluation of the 2.28–2.32
composition increments; CF-1d and generic records remain unselected. On
2026-09-28 the owner accepted the type-system delta as governing for CF-1b and
assigned target 2.33 to generic unions and `std/improve` together; the
[CF-1b plan](2026-09-28-cf1b-composition-first-implementation-plan.md) owns
its tasks, and the
[master plan](2026-09-28-composition-first-master-plan.md) covers the whole
design, including consumer migration and retirement. CF-1b is implemented at
target 2.33 (2026-09-28); its plan records the implemented tasks and the
closeout: the full-suite comparison, fresh public run evidence, and the
merge to `main`. CF-1c consumer migration is on hold (selection
record, step 4). The section heading
keeps its original anchor. The proposal's repository observations were verified
at `31580550`; its interface, generic-union delta, and loop pseudocode are
schematic. It supersedes, as inputs only, the three September 2026 composition
drafts that were never added to the repository.

The intended capability is that a reusable procedure returns the value it
computed together with the domain outcome the caller branches on, through
first-order generic unions instantiated at compile time. The `std/phase`
review loop is the worked example: it currently returns review metadata
without the candidate, seeds initial evidence, and pairs the previous review
with an already-revised candidate on exhaustion. A flat result union such as
`Improvement[S F B]` fixes that at the return boundary without changing the
bounded-loop policy. Budget conventions, review-specific state ledgers,
snapshot/version identifiers, explanation surfaces, and executor extraction
are outside this workstream.

| Step | Bounded work and evidence | Consequence / next decision |
| --- | --- | --- |
| CF-1a — investigate substrate and settle the bounded plan | Adopt the proposed generic-union contract through the parametric type owner, select the module name and target boundary, and probe existing generic exhaustion/lexical-input support without requiring the new generic-union syntax. Confirm removing `ctx` drops no identity/resume dependency. Inventory the maintained consumers' public results and validation obligations. The initial prompt route is concrete provider results plus domain adapters; direct generic `defprompt` results are deferred. | Accept a plan once material contract/ownership choices are resolved and discovered substrate gaps have explicit owner-level corrections and acceptance checks. Do not require implementing generic unions before planning them. If projection, capture or transport obstructs the use case, reconsider those foundations rather than add seeds/counters or abandon composition by default. |
| CF-1b — generic unions and the value-returning slice | Implement the type owner's application, constructor-identity and recursive argument-binding contract through the existing specialization pipeline, with diagnostics and version boundaries. Ship `Decision[F B]`, `Improvement[S F B]`, and `improve`; a structured-value caller whose revised candidate reaches a deterministic consumer; an unrelated `Outcome[T E]`; supported non-record `I` coverage while retaining `S is-record` as the first-delivery loop/exhaustion limit; imported alias/homonym and unused-type-argument identity checks; public compile/run/resume with interruptions after committed review and revision. Use the concrete-prompt adapter route. | Record supported behavior and remaining limits. New-feature executable evidence is acceptance of this step, not a prerequisite implementation for CF-1a. Keep existing `std/phase` exports available and identify only review/revise's mismatch as legacy behavior. No cross-API checkpoint compatibility or utility advantage follows from a passing slice. **Implemented 2026-09-28 at target 2.33.** The supported contract is in the design (§§3–6, and §7's effect behavior before EL-1), its limits in design §11, and the evidence in the [capability matrix](../capability_status_matrix.md). A hook may also return an applied union straight from `provider-result`; adapters remain the route for concrete results. |
| CF-1c — migrate and substitute on real callers | Follow the [master plan](2026-09-28-composition-first-master-plan.md): a shared review-domain module, then the three examples migrated by parallel subagents through domain review/revision adapters, then the utility evaluation, and only after that evidence the two design-delta library phases and retirement. Preserve approved and blocked report/findings/blocker data and validation, including findings consumption after resume. The examples publish no previous-review metadata on exhaustion; the library phases keep it with typed initial absence. Existing provider procedure bodies need not change. Substitute the reviewer with sequential two-review-plus-adjudication, then add a typed proposal field consumed downstream and record actual editing/plumbing cost. The historical parametric-document example is not an unchanged-hook migration. This also serves the [composition plan's](2026-09-22-value-and-continuation-composition-implementation-plan.md) qualitative follow-on evaluation for the increments actually exercised; do not run a duplicate study or claim unexercised context/human-input benefits. | Assess programmability, reuse and diagnosis on actual usage, without a productivity score or new harness. Improve demonstrated recurring friction, reconsider an obstructive foundation, or retain a smaller useful subset. Inventory consumers per declaration; retire only displaced review/revise helpers/macros and unused supporting types, preserving independent `std/phase` exports. Remove adapters only when their domain obligations have another real owner. |
| CF-1d — optional extensions by named caller | Direct instantiated generic `defprompt` results joined the 2.33 contract on 2026-09-29, with provider-boundary tests; the remaining extensions are fixer-side blockage, generic records, and document snapshot/version references, each only when a maintained caller needs it and through the existing owner. For direct generic prompt results, prove instantiation/contract-generation ordering and compare with the working adapter route. | Cancel unbuilt extensions freely; after adverse evidence, remove unnecessary built machinery while preserving independently useful behavior. None is required to close CF-1b or CF-1c, and none reopens the budget or ledger machinery excluded here. |

**Selection record (2026-09-28):** the owner selected the following order,
grounded in the C1 report's friction table, which names the `std/phase` result
as lacking the final subject, and in the roadmap's own lifecycle rule that a
named obstruction with an ordinary-code control justifies a bounded design
investigation:

1. CF-1a now, as a bounded owner task. It consists of checks of existing
   capabilities and contract decisions, not implementation of the new
   capability: apply the accepted amendments from the
   [design review](../reports/2026-09-28-workflow-lisp-composition-first-review.md);
   settle the type-owner amendment for generic unions; check the generic
   exhaustion projection and the `ctx` dependency; and fix the first-delivery
   prompt route as concrete provider results converted by domain adapters,
   with direct generic prompt results as a later extension. **Stop rule:** if
   the type-system amendment is refused, or the exhaustion projection cannot
   be corrected at its owner, CF-1b is not started, the gap is recorded in the
   design, and CF-1 returns to pending. **Executed 2026-09-28:** the generic
   exhaustion projection holds at compile and run. The initial check found a
   dropped final `continue` for `:max` ≥ 2; the owner-level repair now preserves
   it, including public committed-boundary resume. See the
   [check report](../reports/2026-09-28-cf1a-exhaustion-projection-check.md) and
   step 2's verification record. The stop rule is not triggered;
2. the owner-level substrate correction under the
   [runtime prerequisite plan](2026-09-28-cf1-runtime-prerequisites.md), before
   CF-1b's helper/runtime evidence. Use the already-resolved declared terminal
   outputs and remove the redundant snapshot-name selector; do not grow its
   recognized spellings or introduce first/longest-name preferences. Accept
   when the generic final-`continue` regression passes without `xfail`, ordinary
   `std/phase::review-revise-loop-proc` carries the final review evidence after
   multiple revisions, and public fresh/resumed results agree without replay.
   The owner's subsequent cleanup request also covers ambiguous output/failure
   handling and name-derived restoration in these affected paths, using existing
   compiled descriptors rather than new schemas or guessing fallbacks.
   **Integrated on `main`, 2026-09-28:** the selector is removed, ordinary
   imported `std/phase` and fresh/resume checks pass, and 725 adjacent tests
   pass after the restoration cleanup. The full-suite comparison is recorded
   in the runtime plan; the master plan's no-new-failures gate remains open
   because of one additional provider-cancellation failure in unchanged code,
   despite its entire module passing isolated in both storage layouts;
3. CF-1b as an owner-requested package under the
   [CF-1b plan](2026-09-28-cf1b-composition-first-implementation-plan.md), in
   the same manner as Packages C and D of the composition plan;
4. CF-1c through the utility evaluation, selected on 2026-09-28: master-plan
   Tasks 8–12, which also serve as the utility evaluation of the 2.28–2.32
   increments. The design-delta library migration and the retirement
   (Tasks 13–15) depend on that evidence and a separate owner decision.
   **On hold (owner, 2026-09-28, after CF-1b):** consumer migration starts
   only when a generate-and-select helper exists and workflows that judge use
   a model other than the author's. The evidence is the
   [single-call comparison](../reports/2026-09-28-orc-versus-single-call.md);
5. R1b afterwards, on the corrected interface.

The demonstration plan's proposed local repair is independent of this order:
it is neither a prerequisite of CF-1 nor part of it.

The [capability matrix](../capability_status_matrix.md) row records CF-1b as
`Implemented` at target 2.33. Where the demonstration plan's handoff text says
no library redesign is selected, it predates this selection; this section is
the prospective-order authority.

**Entry and dependencies:** CF-1a is closed. CF-1b needed CF-1a resolved,
accepted governing/version contracts, and a reviewed plan; it is implemented.
CF-1c needs a working slice and is on hold under step 4. EL-1 is not a
prerequisite. The original 2.33 evidence used generic-hook forwarding: `improve`
had no direct validator command, and its transitive summary included selected
adapters' provider/command effects wherever the hooks were declared. The
recorded below-2.33 cross-module omission is historical evidence; those source
targets are outside the current 2.35 floor.

Current [Task 5 routing](2026-10-15-orc-simplification-roadmap-extension.md#target-239-selected-implementation)
permits new definition origins at 2.39 to omit effect declarations. Imported
`std/improve` definitions remain at 2.35 with their legacy effect contract and
forwarding declarations; a 2.39 caller does not reinterpret them. This does not
select CF-1c or change EC-1/PC-1 gates. Compiler edits in the
type-environment and specialization owners must be coordinated with any
concurrent EC-1 or PC-1 work before execution. No research allocation changes.

**Amendment boundary:** the
[review-amendment task](2026-09-28-composition-first-review-amendments.md) updates
contracts and records the separately executed feasibility check. The
generic-record `:on-exhausted` prerequisite **holds; its runtime defect is
corrected on `main`** (2026-09-28; selection record, step 2). The final-value
regression passes without `xfail`, including public committed-boundary resume;
the runtime plan records broad verification separately. **CF-1a closed
(2026-09-28)** once its two remaining checks held. Fixed-input capture across
resume: after resume the hooks still receive the fixed `inputs`, shown by
`test_resume_after_a_committed_iteration_exhausts_without_replaying_committed_hooks`
and, for a `String` workflow parameter as `inputs`,
`test_resume_keeps_a_string_workflow_parameter_as_inputs_and_replays_no_committed_hook`,
both in `tests/test_workflow_lisp_improve_stdlib.py`, and by the example's
resume tests in `tests/test_workflow_lisp_improve_example_e2e.py`. The `ctx`
dependency: `improve` has no `ctx` parameter and resumes correctly, and
`std/phase` keeps its `ctx` parameter unchanged, so no existing program loses
a `ctx`-borne dependency. The first-delivery `S is-record` limit is retained,
while `I` need not be a record or authored loop state.

The same check found that a pure inline review hook fails after typecheck;
it is now reported as a `compiler_defect` diagnostic, and a pure revise hook
as `workflow_return_not_exportable`. CF-1b's deterministic tests therefore use
command- or provider-backed review hooks. This separate frontend defect is not
a CF-1 prerequisite; [design §11](../design/workflow_lisp_composition_first.md#11-known-defects-and-rules-at-target-233) lists it with the other known defects.

**Compatibility and closure:** new declarations change bundled-module digests
and require a target bump with versioned acceptance/rejection tests and recorded
definition-origin regimes. Old checkpoints are not reinterpreted and missing
candidate values are not synthesized. Each completed step records supported
behavior, utility limits, the next justified improvement or cancellation, and
any displaced machinery to remove. This work neither gates an E/ES/P exit nor
changes studies.

**Routing:** no executable manifest/queue row is added. The five research
units and their allocations stay unchanged. CF-1a is closed; its runtime
correction is integrated, with verification tracked in step 2. CF-1b is
implemented at target 2.33 and precedes R1b.
CF-1c is on hold under the entry conditions in step 4; when it starts, it runs
through the utility evaluation (Tasks 8–12). Its later library
migration/retirement (Tasks 13–15) and CF-1d require separate owner decisions
and any necessary allocation.

## W3 — Local Hooks With Inferred Context

**Status:** implemented at 2.36, in the
[evaluated-execution delivery sequence](2026-09-29-workflow-lisp-evaluated-execution-plan.md#delivery-order-and-preserved-capabilities),
integrated by owner clarification on 2026-10-01. Owner selection on 2026-10-07
assigns target 2.36 and one `std/improve` API per source import graph, with old
source callers migrated when retargeting. Bounded Tasks 4/6/11–13/14A/14B and
F-CODE-1 are accepted. Exact compatibility03 old-artifact/resume controls are
accepted for the final frozen package. The [closeout](../reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md)
owns final Task F qualification, original RED campaigns, bounded causal
dispositions, reviews and delivery.
This is W3 of the existing
[write-once design](../design/workflow_lisp_write_once.md#6-w3-hooks-see-their-context),
not a new research unit or runtime-closure feature.

The [repetition-reduction plan](2026-09-29-workflow-lisp-repetition-reduction-plan.md#w3-planning-amendment)
owns Task 4 qualification and Tasks 11–14 delivery: multiple local bindings,
inferred lexical captures, signatures from the expected `ProcRef`, then
removal of `inputs I` and context-only records from `improve` callers.

Qualify W3 independently of unselected W0/W1/W2/W4. The accepted bounded
contract in write-once §§6/9 uses one authored direct consumer site for
incomplete local signatures, readiness within that call and target-local
capture canonicalization; full signatures retain reuse. The
[Phase 4c execution plan](2026-10-07-evaluated-execution-phase-4c-w3-plan.md)
records accepted bounded qualification, graph/snapshot/package source
selection and compatibility03 exact old-artifact/retained-run controls; the
[closeout](../reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md) owns
final F verification, review and delivery.
Source graph selection preserves old-target module bytes/path, complete
snapshot authority and existing overlap refusal. Preserve definition-site
values, once-only captured effects, public fresh-run/resume behavior and older-target compatibility. Existing
`bind-proc` remains the option for reusable top-level hooks.

Judge the change by concrete deletions, clearer callers and the locality of
adding a hook input, with behavior preserved. Record line counts as evidence;
a fixed percentage is not an adoption gate. Reuse the shipped proposal
example and `reviewed_change.orc` comparison; this needs no new live study.

The parent sequence owns its placement: Phase 3 supplies the runtime;
Task 4 qualification and Phase 6a assess the caller improvement; complete
the separate pure-capture correction, then Phase 4c delivers Tasks 11–14 before
Phase 5; Phase 6b migrates the maintained consumer inventory.
Qualification preparation can overlap Phase 3. W3 syntax is not a condition
for running the early pilot, and its delivery does not wait for unrelated
Phase 4 effect ports. The component's Phase E is this same Phase 4c work,
not a second schedule. Phase 2 order, CF-1c hold and research allocations
stay unchanged; no executable selector/manifest or active-run state changes.

## AA-1 — Agent Authoring Improvements (Pending, Unselected)

The [agent-authoring plan](2026-10-02-agent-authoring-improvements-plan.md)
owns four small, independently selectable improvements: a short guide with
checked examples, actionable diagnostics, bounded outcome simulation using
the evaluator, and EL-1's optional effect restrictions. Measure success by
correct programs and the effort to obtain them, not by documentation volume
or a new tooling framework.

Record a baseline authoring trial before any selected AA-1 improvement lands;
the owner must first choose the task-selection rule, model and cost budget.
Guide and diagnostic work can use the latest runnable target. Simulation
execution needs Phase 3 and is only for evaluated targets; value synthesis
can be investigated against the Phase 2 artifact after selection. Stream D
reuses EL-1's delivered 2.39 contract; this separate authoring trial remains
unselected. None gates or expands 2.35 delivery.

Start with guidance and remedies demonstrated by the trial. Automated edits,
editor actions and exhaustive branch exploration are not entry requirements.
Record negative results and remaining coverage gaps. This proposal neither
selects a live study nor changes R1b or the existing research allocations.

## CE-1 — Checked Program Evaluation (Pending, Unselected)

The [checked-evaluation design](../design/workflow_lisp_checked_program_evaluation.md)
proposes one operation: compile generated source against parent-declared
limits, commit the checked program or a rejection, then evaluate accepted
code with the existing evaluator and memo. Reuse ordinary imports and type
contracts; do not introduce a scope language, library catalog, promotion
service, or a second interpreter.

Entry requires owner acceptance, an assigned target after 2.35 and the
Phase 2–3 substrate. Resolve import authority, resolved effect bounds,
durable fragment validation and retry/invalidation safety before producing
an executable implementation plan. EL-1's subject-resolution work can supply
the bound check; its whole annotation and analysis migration is not a
prerequisite. AA-1 simulation and a new Python frontend are not prerequisites.

First evidence is a bounded generated program: valid execution, a repairable
compile rejection, refusal of an out-of-bound effect, and interrupted resume
without recompilation or repeated committed effects. The design owns the
remaining correctness checks. Library search, catalogs, promotion and
separate review/check forms require a demonstrated later need.

Both AA-1 and CE-1 are proposal entries only. No executable manifest or queue
is added, no active run changes selection, and the current runtime delivery
order and five research units remain unchanged.

## Current ES Boundary

**Execution-scope amendment, 2026-10-13:** the selected
[executor retirement](../design/workflow_lisp_executor_retirement.md) removes
ES/research/trial execution and the trial SDK from the current package. The
prelaunch park below remains the historical scientific disposition; its frozen
protocol, allowances, results and proposals are preserved, not reopened or
cancelled by this amendment. E0's evaluated direct-task entry and admitted
path-mode run references retain their current owners. No live selector/queue
or active run is advanced by this documentation change.

The [ES component plan](2026-08-02-workflow-lisp-es-first-effectiveness-study-component-plan.md)
retains its completed Tasks 0–5 and fixed-screen protocol. The
[pinned F1v2 refreeze plan](2026-08-03-es-f1-large-scope-refreeze-execution-plan.md)
retains execution progress and binding requirements: Tasks 0, 1, 2, 3, and 3A
are complete; consolidated Task 4 remains incomplete and is now **parked**.
Existing ES Task 7 remains behind that plan's owner-adopted lock.
No live permission follows from this roadmap.

**Owner disposition, 2026-09-08:** Ollie selected “Park ES; advance R1a entry”
in the execution session. R0 is closed by this explicit prelaunch park. Retain
the verified prompt-authority correction and remaining gaps (local historical
evidence: `es-f1-task4-runtime-prompt-authority-correction.json`, not a tracked
repository artifact),
all frozen task/evaluator/reference evidence, and the unconsumed canonical
smoke/study allowances. This is neither cancellation nor scientific completion.
The pinned refreeze plan and scientific package bytes are unchanged.

The owner's subsequent instruction to finish roadmap execution accepted bounded
R1a continuation under the proposed USD 50, 120-request, 1,000,000-token,
eight-agent-hour and 40-human-person-hour first-exhausted ceilings. The earlier
token-ceiling overrun remains preserved historical evidence. Under the later
owner-approved dollar-cap recovery, current prospective work is instead gated by
the qualified per-request admission ledger. Public Task-1 mechanism proof now
includes a passing public scored-verdict smoke plus the known failing required-
check control, while preserving the earlier accounting failure in the record.
The later oracle-qualification claim was withdrawn: current oracle and case/truth
artifacts are retained but not accepted as qualification or an assessment freeze.
Measured construction, reuse, and diagnosis were not completed. The coordinator
subsequently hit an actual per-request reservation denial under the same USD50
total cap; that is not a claim that all USD50 was spent. The bounded
tighter-reservation investigation (local historical evidence:
`2026-09-08-orc-request-reservation-recovery-plan.md`, not a tracked repository
plan)
found no existing smaller enforced output limit on the pinned OpenRouter route;
no behavior-preserving bound reduction was adopted. The owner subsequently
authorized autonomous finite cap amendments in the OMP execution session, with
an initial USD75 cumulative ceiling recorded in the owning demonstration plan.
That continuation preserves all prior charges and remaining evidence obligations;
it is separate from changing the model's output limit. The
[execution record](../reports/2026-09-08-orc-research-demonstration.md) owns current
receipts, recovery state, and any resumed process. R1b and later allocations
retain their separate selection rules.

Coordinate with the active Task-4 owner before changing overlapping files.
Do not edit reference products, evaluator assets, lock bytes, run evidence, or
the refreeze plan to implement this scheduling change. The prior dated
[E1–E3 selection](2026-07-31-workflow-lisp-e1-e3-owner-selection.md) and
[post-E2 sequencing](2026-08-01-workflow-lisp-post-e2-stage-sequencing.md)
remain provenance; their prospective ES-to-E3 implications are superseded by
R0–R3. A parked study is recorded as parked, not scientifically completed.

## Independent Work And Successor

- The [simplification roadmap extension](2026-10-15-orc-simplification-roadmap-extension.md)
  owns the finite manual engineering delivery: process cleanup, the retained
  executable WCC boundary, compatible rule consolidation, the 2.35 source-floor
  retirement and target-2.39 EL-1a/b/c with its two maintained consumer migrations.
  Its per-lane acceptance and failure accounting remain authoritative. EL-1's
  ES hand-back and owner/target conditions are satisfied; WCC is not an EL-1
  prerequisite. EL-1d is cancelled for this selection. Ordinary public-provider
  confinement is deferred; inherited ordinary environment, authored timeouts and
  the existing unlimited-execution policy are retained under D2.
  The bounded [DC-P decision](2026-10-15-orc-simplification-roadmap-extension.md#dynamic-adoption-authority)
  retains typed W3 for the demonstrated fixed improve/search consumers and stops
  this 3.0 adoption/migration lane. It neither closes broader dynamic-language
  research nor deletes the qualified dynamic branch. No research unit,
  machine-queue activation or main runtime-delivery gate changes.
- [AA-1](#aa-1--agent-authoring-improvements-pending-unselected) and
  [CE-1](#ce-1--checked-program-evaluation-pending-unselected) record the
  simplified authoring and checked-evaluation proposals. Both remain pending
  and unselected, outside the 2.35 first-release scope.
- The [P-series](2026-07-30-lsp-frontend-prerequisites-p-series-roadmap.md)
  remains the slated successor after recorded E-program completion or explicit
  owner closure/re-park. No P item is selected or accelerated here.
- Phase ME retirement and removal are complete; the
  [substrate maintenance track](2026-07-26-substrate-maintenance-track.md#phase-me-lean-pilot-apparatus-retirement-and-removal)
  records the disposition and links its historical scope and gates. No successor
  is selected here.
- [OMP-I1](2026-08-14-omp-integration-design-and-roadmap.md) remains complete;
  OMP-I2 remains pending and unselected under its existing named-consumer,
  loading-evidence, and owner-activation conditions. Neither gates this spine.
- [EL-1](#el-1--effect-contracts-and-analysis-cleanup-pending-unselected) has
  delivered the selected bounded 2.39 authoring/inspection/consumer scope;
  optional EL-1d is cancelled for this selection.
  [EC-1](#ec-1--pure-call-expression-composition-pending-unselected) remains
  independently pending and unselected. Their sections retain their own scope,
  evidence limits and future selection conditions. Neither gates an E/ES/P
  exit or changes a research allocation; existing runtime evidence and
  frozen-study boundaries remain intact.
- C1–C3, E2O, the historical execution registry/fragment machinery, and other
  unselected work remain unselected. The completed REC and Q/L programs are
  not reopened.
- [PC-1](#pc-1--first-class-provider-context-pending-unselected) is pending and
  unselected under its own feasibility, design, plan, and allocation gates.
  Listing it neither reopens completed programs nor makes it an E/ES/P exit gate.
- [CF-1](#cf-1--composition-first-procedures-pending-unselected) has CF-1a
  closed and CF-1b implemented at target 2.33, ahead of R1b; CF-1c is on
  hold under its recorded entry conditions. The heading keeps its original
  anchor. It owns the value-returning review helper and generic-union delta;
  `std/phase` remains available beside `std/improve` until CF-1c decides
  otherwise.
- [W3](#w3--local-hooks-with-inferred-context) is integrated into runtime
  delivery as Phase 4c. The repetition-reduction planset owns its technical
  tasks: Task 4 qualification with Phase 6a, then Tasks 11–14, followed by
  Phase 6b consumer migration. Target 2.36 and one source-graph API are selected;
  implementation is present at 2.36, exact compatibility03
  controls are accepted; the closeout owns final F gate status. Pure correction precedes W3,
  then Phase 5; it adds no prerequisite to Phases 2–3.
- Historical candidate order recorded by the owner on 2026-09-28 from the
  [single-call comparison](../reports/2026-09-28-orc-versus-single-call.md#runtime-and-language-findings).
  Each candidate was then unselected until planned:
  1. provider result delivery defects: the result path in
     `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is relative to the run workspace;
     materialization of the result from the agent's final text does not
     happen. Closed on 2026-09-29: a result file left by an earlier call is
     removed before the next call; provider `codex` defaults to `gpt-5.5` and
     passes the effort as `model_reasoning_effort`;
  2. parallel execution of `list/map-effect` bodies, which then ran in sequence;
     the [Phase 5 plan](2026-10-07-evaluated-execution-phase-5-plan.md#status-entry-and-decisions)
     now owns selected implementation and qualification;
  3. a comparison of workflows with a single call on a large task.
- Follow-up work recorded on 2026-09-28 from the final review of CF-1b, each
  unselected until planned:
  1. closed on 2026-09-29: a generic procedure with no effects now constructs
     an applied union over its own type parameters at target 2.33;
  2. at targets below 2.33 a bracketed type that is not a generic union, such
     as a misspelt `Lst[Int]`, reports `generic_union_requires_dsl_2_33`
     where it reported `type_expression_invalid`; what those targets accept
     is unchanged;
  3. three tests in `tests/test_workflow_lisp_generic_unions_runtime.py` run
     programs that the public run rejects at start, because their helper
     skips that validation; they need a public-run form or a strict `xfail`
     naming the pure-result replay limit.
- Defect repairs selected by the owner on 2026-09-29 from the
  [value/effect decision brief](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md), section 7, are implemented: effect
  inference over imported procedures, typed `match` subjects for generic
  calls with type-dependent hooks, specialized types in inlined bodies,
  bound prefixes in `loop-state` fields and `match` subjects, applied-union
  `defprompt` results, the replay index during `--dry-run`, fresh result
  files, at-least-once resume with a `must_not_repeat` opt-out, one run at a
  time in a workspace, compiler-defect diagnostics, the watchdog in its own
  workspace, and lexical scope for hoisted and pure bindings at every target.
  The known defects that remain, cases d and f of the brief among them, are
  listed in [composition-first §11](../design/workflow_lisp_composition_first.md#11-known-defects-and-rules-at-target-233).
- **Selected runtime work:** gate G1 selected evaluated execution on
  2026-09-29. The [parent plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md#status-authorities-and-scope)
  owns current delivery status and the [preserved delivery order](2026-09-29-workflow-lisp-evaluated-execution-plan.md#delivery-order-and-preserved-capabilities).
  Phase 2 compilation and Phase 3 runtime are delivered at 2.35; W3 is delivered
  at 2.36 under its [closeout](../reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md).
  [Phase 5](2026-10-07-evaluated-execution-phase-5-plan.md#status-entry-and-decisions)
  is in progress at 2.37, with bounded Task 4 accepted and full public gates
  pending. This delivery does not select a new research study or retirement.

## Routing And Historical Records

This is an authored roadmap, not an executable selector. No E-series tranche
manifest or queue is introduced. Existing route-readiness records continue to
describe implemented execution capabilities, not research selection.

This incorporation elaborates the existing EL-1 listing and promotes its
previously unnumbered pure-call companion to EC-1; PC-1 is unchanged in scope.
There are now three named pending language/foundation workstreams rather than
two named entries plus a companion. The 2026-09-28 incorporation adds
[CF-1](#cf-1--composition-first-procedures-pending-unselected) as a fourth
named workstream; the same day the owner selected CF-1a and slated CF-1b ahead
of R1b. The five research units, their allocations, and completed records are
unchanged; R1b's entry now names the corrected review interface. The five research units, selected work,
allocations, and completed records are unchanged. No executable manifest/queue
row, ready-to-run implementation plan, or live workflow selection is added.

The 2026-10-01 W3 incorporation makes the already proposed local-hook work
discoverable here and expands its existing plan tasks. The five research
units and the plan's 15 task numbers remain unchanged. The historical planning
cut had Tasks 1–14 pending and Task 15 deferred. The current selected W3 cut
has bounded Task 4 qualification and Tasks 6/11–13/14A/14B accepted; complete
Task 14 and final F qualification are recorded in the closeout; exact bounded
compatibility03 controls are accepted.
Other component tasks retain their unselected status and Task 15 stays deferred.
No machine-selected next item changes or separate delivery track is created. The 2026-10-07 owner selection
chose W3 at 2.36, after pure-capture correction and before Phase 5. That selection
and the original Phase 4c evidence gates are historical; the linked closeout
records the accepted bounded result and its remaining qualifications. The
15 component task numbers and research allocations remain unchanged; no live
machine selector or manifest is changed.

`workflows/examples/inputs/review_revise_design_docs/roadmap_follow_on_inputs.json`
is a legacy review example with historical context, not a live stage selector
or current research authority. Its old context must not overwrite this
research direction if that example is used later.

- <a id="superseded-historical-routing-and-completion-evidence"></a>[Historical section: `superseded-historical-routing-and-completion-evidence`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#superseded-historical-routing-and-completion-evidence)
- <a id="current-e-program-shape-and-gates-2026-07-30"></a>[Historical section: `current-e-program-shape-and-gates-2026-07-30`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#current-e-program-shape-and-gates-2026-07-30)
- <a id="purpose"></a>[Historical section: `purpose`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#purpose)
- <a id="authority-and-routing"></a>[Historical section: `authority-and-routing`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#authority-and-routing)
- <a id="why-a-separate-follow-on-program"></a>[Historical section: `why-a-separate-follow-on-program`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#why-a-separate-follow-on-program)
- <a id="decision"></a>[Historical section: `decision`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#decision)
- <a id="alternatives-considered"></a>[Historical section: `alternatives-considered`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#alternatives-considered)
- <a id="alternative-a-add-one-monolithic-stage-9"></a>[Historical section: `alternative-a-add-one-monolithic-stage-9`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#alternative-a-add-one-monolithic-stage-9)
- <a id="alternative-b-insert-evolution-before-provider-live-binding"></a>[Historical section: `alternative-b-insert-evolution-before-provider-live-binding`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#alternative-b-insert-evolution-before-provider-live-binding)
- <a id="alternative-c-keep-everything-external"></a>[Historical section: `alternative-c-keep-everything-external`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#alternative-c-keep-everything-external)
- <a id="selected-approach-conditional-neutral-substrate-then-optional-features"></a>[Historical section: `selected-approach-conditional-neutral-substrate-then-optional-features`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#selected-approach-conditional-neutral-substrate-then-optional-features)
- <a id="program-wide-architectural-boundaries"></a>[Historical section: `program-wide-architectural-boundaries`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#program-wide-architectural-boundaries)
- <a id="immutable-generation-boundaries"></a>[Historical section: `immutable-generation-boundaries`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#immutable-generation-boundaries)
- <a id="neutral-substrate-versus-feature"></a>[Historical section: `neutral-substrate-versus-feature`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#neutral-substrate-versus-feature)
- <a id="typed-operation-parity-without-kind-erasure"></a>[Historical section: `typed-operation-parity-without-kind-erasure`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#typed-operation-parity-without-kind-erasure)
- <a id="role-separated-prompt-environments"></a>[Historical section: `role-separated-prompt-environments`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#role-separated-prompt-environments)
- <a id="honest-security-boundary"></a>[Historical section: `honest-security-boundary`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#honest-security-boundary)
- <a id="evidence-separation"></a>[Historical section: `evidence-separation`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#evidence-separation)
- <a id="existing-substrate-reuse"></a>[Historical section: `existing-substrate-reuse`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#existing-substrate-reuse)
- <a id="experimental-substrate-lifecycle"></a>[Historical section: `experimental-substrate-lifecycle`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#experimental-substrate-lifecycle)
- <a id="proposed-tranche-ledger"></a>[Historical section: `proposed-tranche-ledger`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#proposed-tranche-ledger)
- <a id="e0--proving-experiment"></a>[Historical section: `e0--proving-experiment`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#e0--proving-experiment)
- <a id="question"></a>[Historical section: `question`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#question)
- <a id="scope"></a>[Historical section: `scope`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#scope)
- <a id="required-baselines"></a>[Historical section: `required-baselines`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#required-baselines)
- <a id="evidence"></a>[Historical section: `evidence`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#evidence)
- <a id="gate-e0"></a>[Historical section: `gate-e0`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#gate-e0)
- <a id="e1--neutral-subject-and-certification-substrate"></a>[Historical section: `e1--neutral-subject-and-certification-substrate`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#e1--neutral-subject-and-certification-substrate)
- <a id="question-1"></a>[Historical section: `question-1`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#question-1)
- <a id="deliverables"></a>[Historical section: `deliverables`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#deliverables)
- <a id="exclusions"></a>[Historical section: `exclusions`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#exclusions)
- <a id="gate-e1"></a>[Historical section: `gate-e1`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#gate-e1)
- <a id="e2--neutral-execution-and-trial-substrate"></a>[Historical section: `e2--neutral-execution-and-trial-substrate`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#e2--neutral-execution-and-trial-substrate)
- <a id="question-2"></a>[Historical section: `question-2`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#question-2)
- <a id="deliverables-1"></a>[Historical section: `deliverables-1`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#deliverables-1)
- <a id="exclusions-1"></a>[Historical section: `exclusions-1`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#exclusions-1)
- <a id="gate-e2"></a>[Historical section: `gate-e2`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#gate-e2)
- <a id="e2o--optional-contextual-subject-observation-and-aggregation"></a>[Historical section: `e2o--optional-contextual-subject-observation-and-aggregation`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#e2o--optional-contextual-subject-observation-and-aggregation)
- <a id="question-3"></a>[Historical section: `question-3`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#question-3)
- <a id="deliverables-2"></a>[Historical section: `deliverables-2`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#deliverables-2)
- <a id="gate-e2o"></a>[Historical section: `gate-e2o`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#gate-e2o)
- <a id="e3--candidate-only-code-evolution"></a>[Historical section: `e3--candidate-only-code-evolution`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#e3--candidate-only-code-evolution)
- <a id="question-4"></a>[Historical section: `question-4`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#question-4)
- <a id="e3a-trusted-evolution-admission"></a>[Historical section: `e3a-trusted-evolution-admission`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#e3a-trusted-evolution-admission)
- <a id="e3b-replaceable-controllers"></a>[Historical section: `e3b-replaceable-controllers`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#e3b-replaceable-controllers)
- <a id="required-comparisons"></a>[Historical section: `required-comparisons`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#required-comparisons)
- <a id="compelling-example-deliverables"></a>[Historical section: `compelling-example-deliverables`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#compelling-example-deliverables)
- <a id="gate-e3"></a>[Historical section: `gate-e3`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#gate-e3)
- <a id="e3r--experimental-substrate-retirement"></a>[Historical section: `e3r--experimental-substrate-retirement`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#e3r--experimental-substrate-retirement)
- <a id="question-5"></a>[Historical section: `question-5`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#question-5)
- <a id="e3f--contextual-fragment-search"></a>[Historical section: `e3f--contextual-fragment-search`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#e3f--contextual-fragment-search)
- <a id="question-6"></a>[Historical section: `question-6`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#question-6)
- <a id="entry-conditions"></a>[Historical section: `entry-conditions`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#entry-conditions)
- <a id="substrate-inputs-versus-feature-work"></a>[Historical section: `substrate-inputs-versus-feature-work`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#substrate-inputs-versus-feature-work)
- <a id="required-comparisons-1"></a>[Historical section: `required-comparisons-1`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#required-comparisons-1)
- <a id="compelling-example-deliverables-1"></a>[Historical section: `compelling-example-deliverables-1`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#compelling-example-deliverables-1)
- <a id="gate-e3f"></a>[Historical section: `gate-e3f`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#gate-e3f)
- <a id="e4p--prompt-identity"></a>[Historical section: `e4p--prompt-identity`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#e4p--prompt-identity)
- <a id="question-7"></a>[Historical section: `question-7`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#question-7)
- <a id="deliverables-3"></a>[Historical section: `deliverables-3`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#deliverables-3)
- <a id="gate-e4p"></a>[Historical section: `gate-e4p`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#gate-e4p)
- <a id="e4e--bounded-prompt-evolution"></a>[Historical section: `e4e--bounded-prompt-evolution`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#e4e--bounded-prompt-evolution)
- <a id="question-8"></a>[Historical section: `question-8`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#question-8)
- <a id="entry-conditions-1"></a>[Historical section: `entry-conditions-1`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#entry-conditions-1)
- <a id="compelling-example-deliverables-2"></a>[Historical section: `compelling-example-deliverables-2`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#compelling-example-deliverables-2)
- <a id="gate-e4e"></a>[Historical section: `gate-e4e`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#gate-e4e)
- <a id="e5--effectful-evolution"></a>[Historical section: `e5--effectful-evolution`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#e5--effectful-evolution)
- <a id="cross-tranche-evidence-contract"></a>[Historical section: `cross-tranche-evidence-contract`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#cross-tranche-evidence-contract)
- <a id="verification-ladder"></a>[Historical section: `verification-ladder`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#verification-ladder)
- <a id="concurrency-and-shared-surface-rules"></a>[Historical section: `concurrency-and-shared-surface-rules`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#concurrency-and-shared-surface-rules)
- <a id="activation-procedure"></a>[Historical section: `activation-procedure`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#activation-procedure)
- <a id="selector-decision-records"></a>[Historical section: `selector-decision-records`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#selector-decision-records)
- <a id="activation-and-gate-state-model"></a>[Historical section: `activation-and-gate-state-model`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#activation-and-gate-state-model)
- <a id="program-completion"></a>[Historical section: `program-completion`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#program-completion)
- <a id="program-wide-stop-and-revise-conditions"></a>[Historical section: `program-wide-stop-and-revise-conditions`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#program-wide-stop-and-revise-conditions)
- <a id="first-handoff"></a>[Historical section: `first-handoff`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#first-handoff)

The superseded routing, original tranche designs and completion evidence are in
the [historical record](2026-07-22-workflow-lisp-evolution-follow-on-roadmap-history.md#superseded-historical-routing-and-completion-evidence).
These legacy anchors preserve citations; they select no new work.
