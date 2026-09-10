# ORC Research Charter

Status: research charter, 2026-09-08, with owner-directed authoring and reuse
clarifications. Implementation and experiment allocation require separate
selection. See the [current roadmap](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md),
[experiment design](../design/orc_reuse_introspection_search_experiment.md),
and [next-step plan](2026-09-08-orc-research-demonstration-plan.md).

The reduced R1a pilot is closed. The owner selected assisted C1 development;
its current scope and subsequent work belong to the
[active plan](2026-09-08-orc-research-demonstration-plan.md#owner-selected-assisted-c1-development).
Authoring follows the design's
[normal agent sessions and evaluation boundary](../design/orc_reuse_introspection_search_experiment.md#normal-agent-sessions-and-evaluation-boundary).
The [execution boundaries](2026-09-08-orc-research-demonstration-plan.md#execution-boundaries-and-replacement-budgets)
and [input manifest](../../experiments/orc_research_demo/inputs.json) own the
finite resource limits and configured model roles. This correction selects no
new study or budget. Earlier proposals, prompts, launches, scores, and failures
remain historical evidence, not current stop rules or successful measurements.

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
| Reusability | Concrete callers and task evidence support qualitative judgment of how easily authors discover, understand, parameterize, adapt, and combine ordinary `.orc` procedures/workflows across real contexts, including glue, type conversions, forks, and local reasoning. | Imports, short source, token savings, shared-edit propagation, cache/resume, or passing semantic regression checks. |
| Introspection | Typed structure, dependencies, source mapping, and run evidence improve correct diagnosis or reduce diagnostic effort against the same source/results/logs without those views. | Many trace files, pretty graphs, or claims to reveal an agent's internal reasoning. |
| Self-programmability | An agent authors working programs, revises them from feedback, and in a separately scored closed-loop case chooses how to revise its own orchestration to meet an objective. | Generated source alone, a human-prescribed topology edit, or fixed-catalog selection. |
| Program-space optimization | Bounded whole-program variation finds useful quality/cost tradeoffs; adaptive search later beats equal-budget enumeration/random search on independent evaluation. | A fixed RICH arm beats DIRECT, compile acceptance rises, or training fitness improves. |

## First Commitment

The [session-pattern evidence](../reports/2026-09-08-orc-session-patterns.md)
motivates two priorities: reusable review-to-completion handoffs and
agent-chosen orchestration improvement from execution feedback. Use the mined
episodes to develop requirements, then assess fresh cases, including transfer
outside maintaining this orchestrator. Repeated prompts alone prove neither
automation demand nor an ORC advantage.

Prefer an adaptive scientific-study context for the existing non-orchestrator
transfer case: diagnose against a reference, test a small case, assess value,
expand or reconsider, and preserve unaffected evidence. The
[PtychoPINN mining account](../reports/2026-09-08-orc-session-patterns.md#ptychopinn-session-evidence)
motivates this choice, not a new allocation. Reuse native experiment runners
and scorers; providers supply scientific judgment. Successful process exit,
matching provenance, and compliance with a flawed metric are not scientific
success. Historical steering often supplied the decisive insight; reproducing
it after disclosure is not autonomous discovery. The
[transfer design](../design/orc_reuse_introspection_search_experiment.md#adaptive-scientific-transfer)
owns case qualification and those evidence distinctions.

The original R1a allocation was 24 behavior cells (12 fixed-arm regressions,
nine novel-case scenarios, three early Python/native controls), six portfolio
adaptations/eighteen consumer checks, and six diagnosis pairs/twelve assessments.
These are historical proposal counts for the closed reduced pilot, not mandatory
next work. Its constrained source-generation scores do not answer practical
normal-session agent programmability; preserve them without retroactive rescoring.
The exposed C1 recovery is openly assisted development. Working sources can be
salvaged with disclosed provenance and assistance; no fresh study is implied.

Use a normal installed Codex or OMP session with ordinary tools, project
instructions/skills, documentation, context management, and available LSP.
The agent owns its build/debug loop within the finite allocation; the outer
driver supplies task/workspace/accounting/evaluation. Use the same ordinary
configured profile, model, and budget policy for idiomatic Python comparisons.
Development needs public checks and feedback, not separate blinded-role
certification. Comparative measurement still needs independent assessment and
final answers outside the author's accessible workspace/context, as the linked
design requires. A pure default-agent setup is not an ORC feature claim.

Finite cost/time limits and amendments follow the active plan and input manifest.
Tokens and requests measure effort, not arbitrary source-attempt cutoffs. Charge
preparation, assistance, failures, and reviews, and report actual USD, elapsed
time, model usage, and human intervention; missing receipts are unavailable
evidence, never zero. No budget rises automatically with this correction.

Assess ergonomic reuse from representative `.orc` callers and concrete tasks.
Disclosed maintained components may be used without first completing three
novice builds. Qualitative review, optionally an LLM judge inspecting the actual
code/task evidence with a disclosed rubric and limitations, may identify friction;
semantic regression tests establish correctness only. If a credible assessment
is unavailable, leave the axis unassessed rather than invent a proxy or mandatory
benchmark. The [reuse design](../design/orc_reuse_introspection_search_experiment.md#experiment-a--reuse)
owns this evidence contract.

R1b remains unselected: its proposed three episodes distinguish task authoring,
requirement-change revision, and agent-chosen orchestration revision. Eventual
selection needs its own finite cost/time budget suitable for normal tool use;
old request/token ceilings or two source revisions cannot limit internal
debugging. Resource-cap authority does not select a successor. Scripted leaves
may isolate orchestration behavior, but actual authoring inference is charged.

Separately dispose of ES: finish the bounded approved study or explicitly
park/close it; do not enlarge it to make RICH win. Its result informs topology
choice, not whether the five hypotheses may be investigated.

## Conditional Follow-On

Qualify one live family: prefer review/planning improvement if independent
behavioral checks and blinded semantic assessment can evaluate it credibly.
Adaptive scientific planning is a candidate context within that family, not
a separately selected GPU study. Scientific-cause discovery requires live
judgment evidence beyond the initial scripted-leaf composition tests.
The linear-classifier repair reference/evaluator is the hard-oracle alternative,
with green baselines still needing preparation. Choose before candidate work,
not after unfavorable results; this is one study, not two. Start
with a finite catalog, frozen prompts/models/tools, and whole-run quality/cost.
Enumerate small spaces. Add adaptive search only when justified; separate
prompt-only and topology-only changes before joint search, with independent
held-out evaluation.

Compare the same protocol delivered as an agent skill and as idiomatic reusable
Python/native orchestration before claiming comparative ORC advantage. Use the
same ordinary configured profile, model/budget policy, semantics, and accounting,
with language-appropriate tools and documentation. Concrete Python examples can
illuminate ergonomic friction without a fixed numeric pass/fail gate. Report
setup, maintenance, failed cycles, model usage, actual USD, elapsed time, and
substantive human intervention; missing receipts are unavailable data, never
zero. These costs do not substitute for qualitative ergonomic evidence.
Changing the goal or evaluator starts an explicitly revised comparison,
not a retroactive fitness gain.

The eventual genetic-programming question is whether typed modules provide
useful mutation and recombination boundaries—not whether arbitrary Lisp text
can be mutated. Full compilation catches invalid composition; only whole-run
evaluation establishes useful behavior.
Searching network architectures, hyperparameters, or a native numerical
optimizer's steps does not establish ORC program-space search. That claim
requires varying the orchestration procedure itself and evaluating its complete
consequences under the same objective.

## Decision Rule

Record evidence per axis, then choose an action: retain a useful scope, improve
a demonstrated bottleneck, reconsider the language/foundation, or retire the
unsupported claim. The [roadmap's axis lifecycle](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#axis-lifecycle--improve-or-retire-then-simplify)
requires bounded, causal improvements with axis-appropriate reassessment—not just
minimum viable examples. Grounded before/after usage can assess ergonomic change;
generalization and measured comparative claims need independent fresh cases.
Consider principled type-system/language redesign and
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
