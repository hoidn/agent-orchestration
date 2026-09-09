# ORC Research Charter

Status: draft research charter, 2026-09-08. Implementation and experiment
allocation require separate selection. See the [current roadmap](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md),
[experiment design](../design/orc_reuse_introspection_search_experiment.md),
and [next-step plan](2026-09-08-orc-research-demonstration-plan.md).

## Thesis

Use the existing system as a starting point to test whether ORC is a useful
**programming medium for agent activity**: people and agents can compose new
behavior, reuse its components, inspect execution, and revise or optimize the
resulting programs. Agents/providers perform tool use. Execution safety is
outside this assessment, not a criterion for pursuing the project.
The type system, representation, language principles, and derived limits such
as the absence of unbounded recursion are revisable choices, not protected
research premises.

The distinctive claim concerns the quality and economics of this programming
medium, not tasks that existing AI tools supposedly cannot perform or an
assumption that more agents produce better answers.

## Five Independently Falsifiable Hypotheses

| Hypothesis | Required evidence | What does not establish it |
| --- | --- | --- |
| Programmability / compositionality | Previously unseen requirements become correct programs through ordinary composition, with measured construction effort, glue, and interface changes. | Four predefined arms exist, a program compiles, or a reusable library is present. |
| Reusability | The same components support distinct workflows and predefined changes with less adaptation/verification effort and no extra regressions than equivalent copied workflows; later, compare reusable Python/native orchestration. | Imports exist, source is shorter, or one example compiles. |
| Introspection | Typed structure, dependencies, source mapping, and run evidence improve correct diagnosis or reduce diagnostic effort against the same source/results/logs without those views. | Many trace files, pretty graphs, or claims to reveal an agent's internal reasoning. |
| Self-programmability | An agent authors working programs, revises them from feedback, and in a separately scored closed-loop case chooses how to revise its own orchestration to meet an objective. | Generated source alone, a human-prescribed topology edit, or fixed-catalog selection. |
| Program-space optimization | Bounded whole-program variation finds useful quality/cost tradeoffs; adaptive search later beats equal-budget enumeration/random search on independent evaluation. | A fixed RICH arm beats DIRECT, compile acceptance rises, or training fitness improves. |

## First Commitment

R1a retains 40 aggregate person-hours and zero paid provider calls. Construction
replaces part of the old allocation: three unseen composition cases, paired
reuse/diagnosis measurements, and an early Python/native control. The
[plan](2026-09-08-orc-research-demonstration-plan.md) caps these at 24 behavior
cells, six timed portfolio adaptations (eighteen consumer checks), and twelve
diagnostic assessments. Novel programs face behavioral checks, not a prescribed
topology. Publish partial and negative results within the cap.

R1b separately budgets actual agent authoring, feedback-driven revision, and a
bounded closed-loop self-programming case using the same behavioral framework.
Scripted leaf providers isolate orchestration behavior, but authoring inference
is real and must be charged. Authoring, revision, and closed-loop results remain
distinct. Neither a genetic algorithm nor runtime `eval` is required.

Separately dispose of ES: finish the bounded approved study or explicitly
park/close it; do not enlarge it to make RICH win. Its result informs topology
choice, not whether the five hypotheses may be investigated.

## Conditional Follow-On

Qualify one repair-task family using the linear-classifier reference/evaluator;
green baselines and independent task partitions still need preparation. Start
with a finite catalog, frozen prompts/models/tools, and whole-run quality/cost.
Enumerate small spaces. Add adaptive search only when justified; separate
prompt-only and topology-only changes before joint search, with independent
held-out evaluation.

The eventual genetic-programming question is whether typed modules provide
useful mutation and recombination boundaries—not whether arbitrary Lisp text
can be mutated. Full compilation catches invalid composition; only whole-run
evaluation establishes useful behavior.

## Decision Rule

Record evidence per axis, then choose an action: retain a useful scope, improve
a demonstrated bottleneck, reconsider the language/foundation, or retire the
unsupported claim. The [roadmap's axis lifecycle](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#axis-lifecycle--improve-or-retire-then-simplify)
requires bounded, causal improvements with fresh-case re-evaluation—not just
minimum viable examples. Consider principled type-system/language redesign and
alternative foundations before interpreting a current limitation as a fatal
flaw. No credible affordable improvement or alternative means abandonment
and simplification of that scope, including cancellation of speculative work
and removal of unneeded abstractions. Preserve useful subsets and dependent
contracts; search failure does not erase reuse or assisted authoring.

Untested promise authorizes no indefinite expansion. A DIRECT winner is valid.
Compare credible reusable Python/native controls before claiming ORC-specific
advantage. Evidence of obstruction can justify a bounded redesign investigation;
commit to reimplementation for evidenced value and a demonstrated better
alternative, not only after ORC itself succeeds. Abandon the custom platform if fair
alternatives cover its retained uses more economically and no justified remedy
remains. Record uncertain results without treating them as disproof.
