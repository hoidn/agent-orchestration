# ORC Programmability, Composition, And Improvement

## Status And Authority

Status: draft experiment design. This describes a proposed study, not an
implemented optimizer, an accepted execution plan, or an efficacy result.
Scheduling and selection belong to the [roadmap](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md);
bounded execution tasks belong to the [plan](../plans/2026-09-08-orc-research-demonstration-plan.md).
The [charter](../plans/2026-09-08-orc-research-charter.md) states the investment thesis.
The plan owns current selection and resource limits; this design selects no
new study or budget. Earlier human-only, zero-paid-R1a, and constrained-authoring
proposals remain historical context, not the normal agent-session contract below.

The reduced pilot, assisted C1 feasibility and qualitative ergonomic assessment
are recorded. The remaining C1 receipt-interface repair is unselected; consult
the plan for current disposition. Completed development does not select a new
study or establish comparative efficacy.

Normative behavior remains in `specs/`. The existing [trial design](workflow_lisp_trial_runs.md)
owns child-run/evaluation methodology; [program-search boundaries](workflow_lisp_program_search_boundaries.md)
record the current architecture. This proposal adds no language target.

Owner scope clarification, 2026-09-08: **execution safety is excluded from the
conceptual assessment and proposed investment gates**. Tool use is performed by
agents/providers. This design studies how ORC composes, describes, reuses, and
optimizes those operations. Existing execution-route restrictions are
implementation facts, not evidence against the research thesis. This draft does
not silently change those restrictions or claim they are already removed.

Exhaustive imported-source identity, checkpoint, replay, and interrupted-run
recovery qualification are not general admission requirements for development.
Use fresh runs unless recovery is itself the selected use case. Correctness of
reused components requires intended callers to receive the changed policy and
preserve behavioral outputs; ergonomic value needs Experiment A's separate
assessment. Retain selective reuse that is part of the task. Actual source/artifact
attribution and metered effort remain; comparative evidence also needs fair
exposure. The active plan and its linked owner amendment own diagnostic scope;
preserved identity/recovery failures do not settle independent research axes.

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
| [`std/phase::review-revise-loop-proc`](../../orchestrator/workflow_lisp/stdlib_modules/std/phase.orc) and [`std/drain::backlog-drain-proc`](../../orchestrator/workflow_lisp/stdlib_modules/std/drain.orc) | Public procedures for bounded review/revision and reusable item continuation. | Existing composition surfaces; fit to the assessment requirements still needs proof. |
| [`verified_iteration_drain/drain::drain`](../../workflows/library/verified_iteration_drain/drain.orc) | Existing fused-session select/plan/implement/verify and review/completion routing. | A particular implemented policy, not a generic API for every mined episode. |
| [`generic_run_watchdog/watchdog::watchdog`](../../workflows/library/generic_run_watchdog/watchdog.orc) | One invocation of probe, conditional repair, and result publication. | Recurrence and demonstrated progress after recovery remain an integration seam; do not clone another watchdog. |
| `workflows/library/control/direct_task.orc` and the four exports in `workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc` | Real shared direct/review/fix composition and a common arm interface. | Existing composition mechanism; ergonomic value needs separate evidence. |
| Full compiler, `compile --diagnostics-json`, canonical IR/source-map exports, and `explain` | Types, calls, effects, dependencies, and authored-to-executable inspection. | Structural facts, not access to private model reasoning or proof of task quality. |
| E1 `run-ref`, E2 `trial`, `TrialRunOptions`, and `run_trial_entry` | Pinned child runs, whole-arm outcomes, checks, evidence, accounting, and verdicts. | Implemented mechanism, not a completed search or effectiveness study. |
| Scripted-provider QA and trial tests | Reproducible branches, malformed results, child/check subprocesses, and failure handling. | Test harness evidence; fake providers/scorers are not a public SDK execution mode. |

Check the [capability matrix](../capability_status_matrix.md) against the episode
date before calling historical friction a current missing feature. Provider
sessions, target-2.16 one-worker/one-supervisor coordination, and target-2.17
static peers are bounded implemented surfaces, not general cross-session or
cross-run steering. An available component can leave a composition or
discoverability problem without requiring a new primitive.

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

## Normal Agent Sessions And Evaluation Boundary

Authoring and development use a normal installed Codex or OMP coding session.
The agent retains its configured tools, documentation, project instructions and
skills, context management, and LSP when available. It owns reading, editing,
compilation, execution, tests, and debugging through its ordinary tool loop.
This default is an agent setup, not an ORC capability or effectiveness claim.

The outer driver supplies the task, workspace, allocated cost/time envelope,
accounting hooks, and evaluation. It does not implement another agent loop or
interpreter. Reuse the installed CLI directly; `authoring.py` may be a thin CLI
wrapper only where a concrete integration needs it. Ordinary task, model,
account, session, output, and metering settings remain legitimate configuration.

Scoring alone does not justify a bespoke tool whitelist, `--no-tools`,
`--no-rules`, `--no-skills`, `--no-lsp`, a source-only system prompt,
compiler-only feedback, or an arbitrary model-turn/source-attempt cutoff.
Disclose any necessary departure and its rationale as a custom condition;
do not describe that condition as the normal/default coding profile.

Use the same ordinary configured profile, model, and budget policy for ORC and
idiomatic Python comparisons, with language-appropriate documentation and tools.
Record available facilities and interventions so differences remain interpretable.
Tool calls, file edits, compilation, and debugging are internal agent work within
the allocated finite cost/time envelope, not task-level revision milestones.
Tokens and requests measure effort; they are not arbitrary source-attempt limits.
This correction neither raises existing budgets nor authorizes unlimited work.

Development checks, expected behavior, and their feedback are public to the
author. Final held-out answers, evaluator truth, and answer-bearing artifacts
must be absent from the author-accessible workspace and context before a held-out
claim is made. Evidence of isolation must describe the actual workspace/access
boundary; instructions not to read a reachable file or disabling tools do not
establish it. Use the existing environment boundary or arrange an appropriate
assessment workspace; this does not select a general sandbox implementation.

Ordinary development does not require separate blinded-role preparation or
certification. A real comparative assessment still freezes its cases, rubric,
profile, accounting, and disclosure policy; keeps final truth separate from
authors; and uses independently scoped assessment with condition-blinded scoring
where applicable. A preparer does not score its own hidden case. Exposure to an
answer makes subsequent repair openly assisted development; a new held-out claim
requires fresh assessment material under the actual boundary above.

Preserve historical prompts, launch configurations, scores, and failures.
Constrained source-generation results remain evidence for that condition and
cannot answer practical normal-session agent programmability. Salvage working
sources with their provenance and disclosed assistance; neither mandatory fresh
reruns nor retroactive rescoring follows from this correction. A healthy existing
custom-profile child may finish; the next needed invocation uses this default.

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

Checks must derive from meaningful task outcomes and real consumer contracts,
not incidental features of a reference implementation. Exact serialization,
ordering, callback counts, or intermediate writes are requirements only when an
actual consumer or task obligation needs them; otherwise accept semantically
equivalent implementations. Exercise harmless representation/initialization
differences in the existing valid controls before relying on a comparison. The
pilot's brittle aggregate/ledger checks were preventable evaluation-design
failures, not merely insufficient disclosure: publishing an irrelevant rule
would not make it valid. Distinguish a recorded checker rejection from an actual
task defect. Preserve historical scores, but withdraw conclusions unsupported
by the evaluator; do not change a meaningful requirement merely to obtain a pass.
Use code-grounded qualitative judgment or leave a question unassessed when an
automated check cannot validly answer it. This adds no qualification framework
or gate before ordinary development.

The thin external driver follows the [normal-session contract](#normal-agent-sessions-and-evaluation-boundary).
The author invokes existing compile/execution surfaces and chooses its own
debugging steps. Generated-workflow execution must be demonstrated through the
ordinary compiled-program route before its owning measurement can run.
For comparative measurement, independently scope preparation, authoring, and
assessment; freeze equivalent semantics and evidence exposure, use fresh author
contexts, and counterbalance condition/variant order. These evaluation roles
are not a separate runtime or a prerequisite for ordinary development.

Keep three evidence levels distinct:

1. **Mechanism:** compositions execute, inspection facts are accurate, source
   proposals compile/reject as expected, and evidence binds to whole programs.
2. **Practical utility:** concrete task evidence supports construction,
   ergonomic reuse, diagnosis, or agent-led programming, with assistance and
   failures disclosed. Comparative claims need a suitable comparison and measured
   effort where relevant; each axis has its own evidence requirements below.
3. **Optimization/effectiveness:** independent tasks show a useful quality/cost
   frontier or an adaptive advantage over equal-budget alternatives.

Passing one level never implies the next. R1a's intended measurement concerns
agent-assisted construction, reuse, and diagnosis; deterministic execution fixtures
support behavioral checks, while ergonomic reuse follows Experiment A. R1a
does not measure human performance, live-task efficacy, or autonomous
closed-loop success. If separately selected, R1b measures actual agent authorship,
requirement-change revision, and agent-chosen closed-loop revision using the same
behavioral framework. Neither lane establishes general optimization advantage.

### Session-Derived Workloads

The [sanitized session-pattern report](../reports/2026-09-08-orc-session-patterns.md)
supplies requirements-development evidence, not independent tasks, failure
rates, saved time, or outcomes. Group sessions and forks by underlying task or
failure family; keep repeated prompts, before/after revisions, and variants of
one episode together. These already-mined examples are development material.
Use fresh withheld requirements and artifacts for assessment, without a literal
history-text or prompt-phrasing oracle.

Qualify a recurring present-day need before selecting a case. Distinguish
visibility/status requests, deliberate commit/continue approval, workflow-caused
friction, and user objective changes from a protocol that can be automated.
Record whether the dated problem is resolved, needs composition/discoverability,
or still fails on the current surface. Include non-orchestrator transfer when
selecting a comparative composition assessment.

Prioritize review/revise-to-selected-completion with usable results and
unaffected accepted work preserved, then agent-chosen orchestration improvement
from evidence, including at least one non-orchestrator transfer case within
the composition requirements. The original R1a protocol proposed 24 behavior
cells (12 fixed-arm regressions, nine novel-case scenarios, and three matched
Python/native construction scenarios),
six portfolio adaptations/eighteen consumer checks, and six paired diagnosis
cases with twelve assessments. Those counts describe the historical protocol
whose reduced pilot is closed; they are not mandatory next work. R1b's proposed
three episodes remain separately selectable. These priorities create no new
matrix, arms, or independent samples. The completed assisted C1 development used the
[execution boundaries](../plans/2026-09-08-orc-research-demonstration-plan.md#execution-boundaries-and-replacement-budgets)
and [input manifest](../../experiments/orc_research_demo/inputs.json) for finite
monetary/time limits and their authorized amendments. Request and token counts
are effort metrics, not stop ceilings. Preparation, all
models/subagents/reviews, failed or repair calls, adaptations, and assessments
count inside these ceilings. Record model/configuration and pricing/usage
accounting before launch; comparative measurement additionally needs the
evaluation boundary above. Pre-selection documentation-amendment
assistance is disclosed separately as prior planning overhead, not a measured
sample and not asserted free. Missing receipts are unavailable cost evidence,
never zero; no preparation is laundered outside the caps. R1b requires separate
selection with its own explicit finite allocation; authority to raise
resource caps does not itself expand study scope or select a successor.

#### Adaptive Scientific Transfer

Prefer an adaptive scientific-study context for a selected
non-orchestrator composition case, informed by the
[PtychoPINN evidence](../reports/2026-09-08-orc-session-patterns.md#ptychopinn-session-evidence).
It fits the review/completion, judgment/reconsideration, and multi-item
selective-continuation requirements. It selects no extra family, public API,
assessment case, or matrix. A possible protocol is
diagnose → pilot → judge scientific value → expand, repair, or rethink → preserve
unaffected work. This illustrates obligations, not a reference graph to copy.
Useful scenarios cover process success without scientific acceptance,
pilot-driven reconsideration, and selective reuse after a correction.
In R1a/R1b, domain judgments are declared fixture observations, not live discovery.

Providers choose scientific causes, materiality, and whether to rethink; ORC
composes operations and routes their declared outputs. Tool use stays with
providers. Reuse the domain's maintained runner, scorer, calibration, and
numerical routines, available equally to ORC and Python/skill controls. A new
combination of supported surfaces still needs a minimal executable integration
proof; existing components alone do not close the feasibility gaps below.
R1a/R1b use controlled interfaces and doubles for these domain operations;
integration proof concerns ORC execution. Actual native scientific operations
belong to a separately qualified live study.

The case must distinguish execution success, scientific quality, an invalid
evaluator, an implementation defect, useful prior evidence, current comparison
evidence, and a changed objective. Preserve each comparison's actual contract:
a failed value gate may call for a different method, bounded diagnosis, or
stopping that scope; it does not prescribe always stopping the whole study.
Audit dependencies before selectively rerunning affected work. A hash mismatch
or an old label alone is not a universal scientific rerun rule, and relabeling
does not make incompatible evidence current. If a revised causal protocol
changes the comparison, or the evaluator/objective changes, record an explicit
amendment, new baseline, and fresh assessment before any improvement claim.
These study judgments do not bypass
the native runner's enforced identity or reuse contracts.
Selective reuse of scientific artifacts is workload behavior; it does not
establish Experiment A's ergonomic reuse of ORC abstractions across contexts.

Historical steering often supplied the scientific answer. Freeze pre-intervention
contracts and available observations symmetrically in both conditions; exclude
held-back causes, prescribed topology edits, and later diagnosis-bearing document
revisions from scored-agent context. Declared requirement-change feedback is
allowed in its assigned episode, with assisted discovery scored separately from
unassisted discovery. Deterministic leaves establish control and evidence flow;
they do not prove that an agent can discover a physical cause or improve science.

## Experiment P — Programmability And Compositionality

Use the [normal agent build/debug loop](#normal-agent-sessions-and-evaluation-boundary),
including public development checks and feedback. Score the resulting behavior
and complete effort; internal tool turns and compiler repairs are not separate
task attempts. Once requirements or answers have been exposed, further work on
that case is disclosed development rather than a fresh unseen-task measurement.

For a separately selected assessment, freeze a documented component/operation
vocabulary using development examples, then reveal the selected requirements
unseen by the assessed author. The original protocol proposed three cases. This
means held-back tasks, not a claim about an LLM's training history. Qualify the
requirements against the intended existing surface without tailoring a library
to their exact solutions. Candidate shapes include:

- review/completion handoff: bounded revision with approval, changes-requested,
  and blocked outcomes, preserving usable results through selected completion;
- conditional judgment and disagreement: combine independent assessments of
  findings and choose revision, acceptance, or bounded reconsideration;
- reusable multi-item continuation: per-item evidence, scoped policy changes at
  meaningful task boundaries, and retained unaffected accepted work.

Providers assess findings, materiality, success, and whether to rethink; ORC
composes operations and routes/records their decisions deterministically.
Changed material or dependencies can invalidate relevant reviews: neither
always-preserve nor always-redo is correct. Recovery, steering delivery, and
batch contribution attribution are pressure cases or conditional follow-ons,
not three additional projects. Distinguish a steering message being sent,
received, and applied. A task-decision-boundary simulation proves only that
composition; arbitrary tmux/live cross-run delivery needs its own integration
evidence before any such capability claim.

These are requirement families, not promised existing whole-workflow APIs.
Freeze selected cases and their behavioral scenarios before measured authoring.
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

The hypothesis is ergonomic reuse of ordinary `.orc` abstractions across real
contexts: can authors discover, understand, parameterize, adapt, and combine
procedures/workflows while reasoning locally about the result? Inspect concrete
authored callers and usage examples for boilerplate, glue, type conversions,
helper forks, and edits that spread beyond the intended change.

Start from disclosed maintained working components and representative consumers;
reuse assessment does not depend on all three novice construction attempts
succeeding. Try the public stdlib procedures and existing workflow exports
first. Record provenance, preparation, assistance, and actual interface changes;
preserve construction failures and historical portfolio results unchanged.

Assess the examples qualitatively against their tasks. An optional LLM-as-judge
review must inspect the actual code and task evidence, disclose its rubric and
limitations, and remain a judgment, not an objective measurement. No new judge
framework or compulsory benchmark is required. If examples are unrepresentative
or credible assessment is unavailable, leave ergonomic reuse unassessed.

Semantic regression checks establish correctness of the examples, not ergonomic
value. Imports, source brevity, token savings, shared-edit propagation, caching,
and resume do not define ergonomic reuse. An idiomatic Python comparison can
illuminate particular friction, without a fixed numeric pass/fail gate. The
original shared-versus-copied portfolio, six adaptations/eighteen checks, and
20% token-effort screen are historical protocol details, not this assessment.

## Experiment B — Introspection

The original diagnostic proposal used six paired cases, one per category below,
with two equivalent variants per pair: twelve assessments total. This historical
proposal replaced twelve cases/twenty-four assessments; the plan owns the closed
pilot's reduced scope and any separately selected future assessment.

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
where relevant, and correct next/recovery action. Record total metered model
input-plus-output token effort, actual USD, elapsed time, request count,
human intervention, abstention, wrong attribution, and false assertions that
an effect ran or can be reused. Cached tokens count as input; reported
reasoning/output is counted once. Do not score literal error wording.

Counterbalance variant assignment and condition order so the same analyst does not learn a
case's answer in one condition before seeing it in the other. If no fair
assessment is possible inside the budget, report mechanism coverage only and
leave diagnostic utility untested. Derived views are explanations of recorded
facts, not an alternative source of runtime authority.
The six categories remain orchestration diagnosis. A scientific context does
not turn missing-output or binding-drift diagnosis into evidence of physical
root-cause discovery. Report domain judgment separately; distinguish an invalid
evaluator or numerical implementation from a scientifically poor valid result.
Any recorded hypotheses or decision rationales used as context must be public
supplied evidence available in both conditions, subject to the answer-exclusion
rule above; traces do not reveal an agent's private reasoning.

## Experiment S — Agent Authoring And Self-Programming

This is the separately selectable R1b lane, not an expansion of R1a. R1a's
agent-assisted construction, reuse, and diagnosis outputs do not count as
human performance, live-task efficacy, or autonomous closed-loop evidence.
R1b remains unselected. Its proposed three episodes need an explicit finite
cost/time allocation suitable for normal tools; old proposed request/token or
source-attempt ceilings do not govern the agent loop. This design selects or
raises no budget; the eventual plan must reserve final-assessment resources.

Use the same operation interfaces and behavioral framework with fresh agent
contexts and held-back requirements. Separate three observed accomplishments:

1. **Authoring:** the agent chooses a composition from requirements and produces
   source that compiles and meets the behavioral contract.
2. **Requirement-change revision:** the agent changes a working program for a
   changed task requirement while retaining unaffected obligations. Ordinary
   compile/debug repair is part of authoring, not this separate accomplishment.
   A human-directed change is assisted revision, not autonomous self-programming.
3. **Closed-loop self-programming:** given an objective rather than a prescribed
   topology/edit, the agent selects its orchestration, executes it, inspects
   available evidence, and chooses a program revision that addresses the
   observed shortfall. The outer driver provides the episode and budget; the
   agent controls its tool/debug loop and edit. If no revision is needed,
   record successful authoring; that episode supplies no revision evidence.
   Do not inject extra faults afterward
   simply to manufacture a closed-loop success.

The proposed protocol covers three episodes, one per requirement family. Any
retained two-revision limit counts objective-level orchestration milestones,
not model turns, tool calls, file edits, or internal debugging. Designate
review/completion handoff for closed-loop orchestration revision; use the other
two families for requirement-change revision and initial authoring, assigning
them before running.
The agent receives the goal and development results and chooses its edit.
Reviewer placement/order, context selection, or retry/invalidation policy are
possible choices, not required mutations or a human-specified topology.
Retain first-version and final-version results separately. Freeze public
development checks and a held-back final check per case, using the actual
workspace/context boundary above. The agent receives development results and
normal diagnostics; final-check answers remain outside its access until the
selected revision is frozen.
Post-holdback repair is assisted development; a new independent measurement
requires fresh assessment material.

Record each task-level program revision, requested/predicted change, compile
result, actual execution/behavior, feedback exposed, and all human intervention.
Source/IR differences and type validity are supporting facts, not demonstrated
useful behavior. A human supplying topology or code disqualifies an unassisted
closed-loop claim but remains visible as an assisted result. Preserve every
failed proposal and first-attempt failure; report success versus total effort,
not only the best final artifact.

Separate candidate program/prompt changes from objective or evaluator changes.
An agent's rationale may challenge the evaluator, decomposition, or design.
Stop or route bounded reconsideration; record an explicit protocol amendment,
new baseline, and fresh assessment before claiming improvement under a changed
objective/evaluator. Do not interpret changed success criteria as a better
candidate, or force revision until green when the evidence calls the approach
into question. The provider owns that semantic judgment; ORC records its result.
In a scientific transfer episode, an agent-authored change to diagnostic order,
pilot/replication policy, or selective continuation can establish orchestration
revision. Human-prescribed orchestration edits are assisted revision; declared
provider results or fixture observations remain permitted evidence from which
the agent can independently choose its ORC edit. A supplied scientific answer
does not establish independent scientific discovery; R1b control revisions do
not establish live scientific insight. Apply the pre-intervention context
boundary in Adaptive Scientific Transfer above.

Leaf providers may be deterministic doubles to isolate orchestration, but the
authoring agent is real. Public leaf doubles establish control/dataflow and
behavior, not real prompt-quality efficacy; a text-only prompt mutation earns
no such quality claim. Charge every authoring/revision request, including
tool-loop model turns, repair attempts, assistance, and preparation. Never label
this lane provider-free. R1b's separate plan owns its finite resource ceilings
and allocation; missing receipts are unavailable cost evidence, never zero. No
runtime `eval`, rewriting of the interpreter, or genetic algorithm is required
for this claim.

An ordinary-code agent control uses the same semantic task, ordinary configured
profile, model/budget policy, operation interfaces, and behavioral oracle, with
idiomatic tooling and language-appropriate documentation. Model familiarity and
onboarding are reported confounds. Comparative agent-authoring claims require
matched episodes;
the initial three ORC episodes alone establish at most descriptive feasibility.
Later practical comparisons should also include an agent following the same
protocol as a skill and an idiomatic Python controller, with equal model,
tools, semantic requirements, and budgets. Neither these controls nor paired
revision trials are implicit additions to R1a's three early Python/native
construction cells or R1b's three episodes; prepare and allocate them explicitly.

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
For scientific transfer, vary the ORC procedure: diagnostic order, pilot and
replication decisions, continuation, or evidence-reuse policy. Changing network
architecture code, hyperparameters, or native optimizer steps alone does not
vary that procedure. Local assessments must faithfully test their stated claim;
selection still requires complete-program evaluation, including interactions
and total cost. A metric change starts a new comparison.

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
Live prompt/topology mutation belongs to separately approved R3 after usable
execution and evaluation exist. Revising the objective starts a new comparison;
it cannot retroactively improve a candidate's score on the old objective.
No population store, crossover system, genome schema, or self-modifying runtime
is justified merely by calling the research evolutionary.

## Corpus And Evaluation For A Later Live Study

R2 selects one task family under its own finite protocol before candidate work.
Prefer a qualifying mined review/planning-improvement family when independent
behavior checks and blinded semantic quality judgments detect known defects
and distinguish useful completion from review churn. Qualification must show
that sensitivity on development artifacts before freezing fresh assessment
material. Neither historical prompts nor deterministic leaf doubles supply an
independent quality oracle.
The review/planning family may include adaptive scientific planning if it can
be independently evaluated under this separately approved one-family protocol.
Qualify orchestration control and domain judgment separately using pre-intervention
artifacts; later answer-bearing revisions cannot supply scored context. This
adds no mandatory GPU suite or third lane. Native execution and evaluator
preparation, all provider/tool work, and failed studies count in full costs.

The hard-oracle scientific repair family at
`examples/demo_task_linear_classifier_port/`, with independent evaluator
`orchestrator/demo/evaluators/linear_classifier.py`, supplies existing assets for
the alternative if needed at qualification. Its Rust seed is unfinished:
produce a verified green target against the Python reference before bounded
defect variants; existing assets alone do not establish corpus readiness.
Select one family, not a second study or an automatic fallback after results.
Numerical variants are not independent repair tasks. NanoBragg remains a later
transfer possibility; the sliding-window seed lacks a matching hidden evaluator.

A proposed twelve-episode pilot is descriptive. Group underlying task/defect
families before dividing adaptive, validation, and sealed holdout sets; keep near
duplicates, session forks, and numerical variants together. Qualify split sizes
and evaluator sensitivity before candidate generation. Use at least three
stochastic repetitions per candidate/task to characterize noise, paired by task/execution
block; repetitions do not increase independent task count.

Freeze the evaluator, candidate vocabulary, prompts/models/tools, accounting,
retry/time limits, partitions, and decision rule before adaptive work. The
optimizer sees adaptive evidence; validation selects complete candidates; the
holdout is opened once after selection and analysis are fixed. Candidates and
proposers must not see held-out evaluator data: this is protection against
measurement leakage, not an execution-safety claim. A failed holdout is a
failed claim; a revised attempt needs new holdout material.

Hard objective correctness outranks soft judgment where it applies; semantic
quality assessment must still test progress toward the selected user goal.
Retain all failed runs, timeouts, compile rejections, retries, and apparatus
incidents under a predeclared disposition rule. Missing cost receipts mean
unavailable data, never zero. Account for whole-run quality/cost, including
setup, construction, adaptation, proposal, evaluation, execution, maintenance,
and every failed attempt. Record interventions' purpose and substance and
whether accepted obligations survived. Unproductive review and wasted status
polls are diagnostic costs, not objectives to minimize regardless of quality.

The accepted trial design's default confirmatory rule is ≥10 percentage points
absolute improvement with an interval excluding zero at ≤1.5× provider cost,
or statistically non-inferior success at ≥20% lower cost; its holdout floor is
≥30 independent cases with a power calculation. This small pilot neither
waives those requirements nor earns `PASS_E3`. Any experiment-specific amendment
must be explicit and frozen before the study.

## ORC-Specific Comparison And Disposition

The historical copied-ORC control tested adaptation effort, not ergonomic reuse.
Experiment A owns the qualitative reuse assessment. DIRECT tests topology value.
Random/enumerative search tests the optimizer. **None tests the value of ORC
against another reusable representation.** Before claiming that advantage,
compare one credible reusable Python/native program with the same agent
operations, topology, evaluator, model/tools, recovery responsibilities, and
accounting. A matched-topology comparison isolates representation mechanics;
open authoring comparisons instead hold requirements and operation semantics
constant and permit different valid programs. Allow each representation its
normal reuse and inspection tools;
do not handicap the control with deliberately duplicated or opaque code.

Assess each selected scope using evidence appropriate to its claim. The original
R1a measurement screens remain historical; they do not require completing the
closed pilot or turn correctness and effort proxies into ergonomic value:

- Programmability: report the capability map and complete behavioral results
  for the selected requirements. Correct ordinary composition establishes scoped
  feasibility, not a comparative advantage. Record the early ordinary-code
  comparison, construction cost, and any required glue or missing interface.
- Reuse: concrete callers and task evidence support a qualitative assessment
  of discovering, adapting, and composing ordinary `.orc` abstractions across
  representative contexts, following Experiment A. Correct examples are
  necessary evidence for those examples, not a numeric ergonomic pass gate.
- Introspection: a separately selected comparison predeclares diagnostic
  correctness and effort criteria; confidently wrong diagnoses must not increase.
  The original six-pair/20% screen belongs to the historical protocol.
- Mechanics: real checks distinguish passing and failing outputs; actual
  calls/artifacts match the declared composition; evidence identifies complete
  evaluated programs. A known broken oracle is a failed apparatus result.

For R1b, report authoring, requirement-change revision, and closed-loop outcomes
separately with their full costs. At least one unassisted, behaviorally verified closed-loop
revision establishes that mechanism in its case; it does not demonstrate
generality, superior economics, or optimization. Human-prescribed edits, mere
compile repair, and unchanged successful programs cannot substitute for it.

These are scoped evidence requirements, not statistically powered claims. Record
each of the five axes as supported within scope, adverse, inconclusive, or
untested. Case-level outcomes and uncertainty remain visible. Neither failing
reuse and introspection nor merely asserting untested programmability decides
the entire project. Any further allocation needs a bounded question supported
by existing evidence or an explicit, limited test of a named unresolved issue.
Do not move thresholds after results.

Dependencies follow the claim: authoring measurement needs executable cases and
a functioning oracle, not favorable reuse/diagnosis results. A fixed-catalog R2
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

Compare the changed system with its predecessor and relevant simpler control,
accounting for preparation, migration, and maintenance as well as execution.
Use retained regressions for behavioral changes and independently prepared fresh
cases for generalization or measured comparative claims. Ergonomic improvement
can instead be assessed through representative actual before/after usage and
grounded judgment; it does not require a new portfolio or hidden-case exercise.
A fix fitted to one example is not evidence of general improvement; repeated
exposure to a holdout requires fresh material for a held-out claim.

Use those same axis-specific cycles and the [plan's conditional Task 7](../plans/2026-09-08-orc-research-demonstration-plan.md#conditional-task-7--improve-or-retire-the-selected-scope)
after the first case: extend reuse to distinct consumers; target observed causes
in diagnosis; assess transferred self-programming revisions; and test search
locality, interactions, and whole-program contributions rather than summing
component scores. Repeated metric gains without goal progress, review churn,
or growing glue trigger provider-led reconsideration, not forced extra reviewers.
Compare local remedies, type/language redesign, and alternative foundations
before scoped retirement and simplification. There is no global MVE-pass gate.

Each separately allocated cycle predeclares the evidence that would justify its
claimed improvement, resource horizon, and stopping rule. Qualitative ergonomic
assessment needs representative examples and a disclosed basis for judgment,
not a fabricated numeric threshold. A useful baseline may remain when its
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

The active plan owns selected development; a later comparative allocation may
use Tasks 1 and 2 to establish operation-based doubles, a real-check execution
path, the development library, fair diagnosis, and paired controls, counting
their complete preparation cost. Demonstrate that the oracle accepts different
valid compositions and rejects a broken one before freezing the assessment
protocol/library and starting measurement. These are outputs of preparation, not
circular prerequisites for a later decision to prepare. This draft itself does
not accept, allocate, or claim completed metering or independence proof.
Failure stops the affected lane within its cap; classify the actual gap.

R1b additionally needs a demonstrated ordinary compiled-program execution path
for one generated provider-workflow composition and an accepted inference budget.
It does not inherit a mock SDK API or effectful clone-path mode that does not
exist. Select bounded integration preparation to establish the proof before
authoring measurement; do not turn a missing route into a second runtime.
Qualification/preparation of the selected task family and live domain-provider
allocation remain separate prerequisites for R2 efficacy work.

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
