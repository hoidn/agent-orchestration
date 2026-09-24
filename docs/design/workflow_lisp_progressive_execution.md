# Progressive Execution From An Agreed Goal

Status: draft target design; not an implemented framework or runnable example.

Scope: a software-task demo and a small callable `.orc` coordinator.

Authority: existing [language principles](workflow_language_design_principles.md),
[frontend contract](workflow_lisp_frontend_specification.md), and runtime
[provider](../../specs/providers.md) / [result](../../specs/io.md) contracts.

## Decision

Use the existing interactive agent to explore the goal with the user. Once the
user explicitly chooses to proceed, pass the agreed brief to a fixed `.orc`
coordination loop. An agent chooses and refines the next task; `.orc` dispatches
work, obtains checks, and routes the result. Workers retain their normal tools
and responsibility for local problem-solving.

Treat this as an ordinary `.orc` application. The default target is zero new
language machinery, not a claim that the exact composition has already been
proved. Planning, milestones, and specialization are workflow policy and prompt
content; they must not become compiler concepts. Names such as `pursue-goal`,
`Progress`, and `NextAction` denote ordinary authored procedures and data types,
not new builtins, type-system features, or DSL forms.

Start with one software-development profile and sequential work. This makes
arbitrary parallel task graphs and fully in-language conversation harder; those
are deliberate limits of this first design, not permanent language principles.

The alternatives are an ordinary agent with instructions, which may be enough
for a one-off task, and an agent that generates executable `.orc`, which exposes
more programmable structure but needs a separate synthesis design. The fixed
loop is useful when its coordination is something callers want to inspect,
change, or reuse. It does not guarantee better results than an ordinary agent.

## User Experience And Ownership

```text
interactive discussion -> explicit go-ahead -> agreed brief
                                                  |
                                                  v
                                     outline / choose next work
                                      /           |           \
                                   work         finish      question
                                    |             |            |
                              worker + checks   verify       return to
                                    |           completion   user chat
                                    +--> reconsider
```

- **Interactive harness:** explores alternatives, records the agreed objective,
  constraints, and completion conditions, and handles human questions. This is
  a role of the existing chat agent, not a new application or service.
- **Planning agent:** maintains broad milestones, refines only the active work,
  examines results, and chooses the next action. It may inspect the repository.
- **`.orc` coordinator:** owns the visible call sequence, structured decision
  branches, check invocation, and terminal result. It does not parse prose to
  recover execution decisions.
- **Worker agent:** investigates, implements, tests, and reports its result with
  its usual provider tools. The DSL does not orchestrate each tool invocation.
- **Project checks:** exercise the actual deliverable through existing test,
  build, or other relevant commands. Passing them is evidence, not a substitute
  for judging whether the agreed goal was achieved.

The planning agent also performs the ordinary semantic review on its next
visit. Do not add a separate reviewer to every task by default.

## Progressive Planning

The first planning visit outlines milestone objectives and selects actionable
work within the first relevant milestone. Later milestones stay broad. Further
subdivision happens within the planning visit, not through a new agent call for
every level of a task tree.

Stop subdividing when one appropriately equipped worker has a coherent task,
sufficient context, and an observable completion condition. Investigation can
itself be a task when the missing knowledge prevents useful implementation.
Do not equate actionability with a fixed depth, file count, or token allowance.

After work, the planner may continue, split, combine, reorder, or replace planned
tasks. Discovering that a type system, interface, or initial design assumption
is unsuitable is a reason to consider changing the foundation, not merely to
retry the same approach or declare the goal impossible. Changes to the user's
objective or unresolved product choices return to the user; ordinary technical
decisions remain agent work.

Keep the outline and current reasoning as compact planning text. There is no
task-ID registry, dependency graph engine, or prescribed task taxonomy. That
text informs agent judgment; it is not a hidden executable program.

## Small Contract

These are proposed semantic shapes, not copy-ready `.orc` declarations.

The coordinator accepts the agreed brief and optional previous progress.
Provider bindings supply a planner and worker; their model/effort settings can
differ using existing call policy. The software instructions and project check
commands are explicit inputs/assets, not a new profile registry.

Carry only the information needed for the next visit: the current outline and
decisions, the latest work result, and the latest check outcome/evidence. The
brief remains separate so summarizing progress cannot silently replace the
agreed goal. Earlier detailed evidence stays in ordinary run artifacts.

| Boundary | Required meaning |
| --- | --- |
| Planner result | `Work(task, updated_plan)`, `Finish(summary, updated_plan)`, or `Ask(question, updated_plan)` |
| Work result | What changed or was learned, relevant produced artifacts, and remaining uncertainty; not just `Bool` |
| Check result | Whether the configured checks passed, failed, or could not run, with their actual output available |
| Coordinator result | `Done(summary, progress)`, `NeedsInput(question, progress)`, or `Incomplete(reason, progress)` |

Use small records/tagged outcomes only where routing or useful result passing
justifies the distinction. The boundary table does not require a separate
wrapper type for every row; reuse compatible existing shapes without erasing
meaningful outcome distinctions. Keep task descriptions and planning
explanations as strings and consumed evidence as ordinary artifact/path values.
Do not require a nested `List[Task]`, a generic JSON scheduler, or a task ontology.
Provider results use the runtime's validated result transport, not stdout or
markdown status extraction. Render the actual brief, task, instructions, and
relevant evidence through supported prompt inputs/fills/dependencies.

Avoid copying unchanged progress fields through every branch where implemented
record-update or composition facilities suffice. If state plumbing dominates
the coordinator, investigate the general interface rather than creating a stack
of progress-conversion helpers or assuming proposed composition features exist.

`Work` dispatches one worker, runs the applicable project checks, and feeds both
results back to the planner. A failed check leads to reconsideration, which can
choose repair, investigation, or a different approach. It does not imply an
identical retry or immediately require the user.

A check that cannot run also prevents completion. Feed a reported setup problem
back for repair or investigation; ask the user only when their input is needed.

`Finish` is a completion proposal. Return `Done` only after the planner has
assessed the agreed completion conditions and the configured final checks pass
against the delivered workspace. A final check failure returns to planning;
successful checks alone cannot establish semantic completion.

`Ask` returns `NeedsInput` to the surrounding chat. After an answer, that agent
calls the same coordinator again with the clarified brief and prior progress.
This is a new invocation with explicit inputs, not a claim that workflow
`resume` injects human answers. The planner checks the current workspace before
relying on prior completion claims; it does not blindly repeat earlier work.

Target 2.32 now offers `(request-input question)` for an explicitly chosen
same-run variant. It returns `HumanReply` after CLI submission and resume,
including inside imported calls and loops. That capability does not silently
change this demo's `NeedsInput` contract; choose one interaction boundary when
implementing the caller, and remove any restart glue it genuinely replaces.

Use the existing bounded-loop mechanism. Exhaustion returns `Incomplete` with
useful progress, never `Done`; the bound is an execution limit, not a definition
of good task granularity. Invalid provider output and infrastructure failures
retain normal runtime diagnostics. Do not invent a recovery subsystem or turn
malformed outputs into successful decisions.

## Software Specialization

One software instruction asset supplies repository conventions, available
skills/tools, the testing approach appropriate to the task, and short examples
of the desired comment style. For example: explain a non-obvious constraint or
reason for a choice; do not narrate obvious syntax. Do not promise that a persona
such as “master developer” enforces those properties.

The planner adds task-specific context before dispatch. A worker receives the
original objective, its current task and completion conditions, relevant prior
findings, and the software instructions. It need not receive every prior chat
message. This is an explicit, potentially lossy handoff, not native session
continuation. The target-2.31 portable context facility is available when its
captured content is useful, but is not required for this explicit handoff.

No automatic model router is required. Bind planner and worker independently;
using the same provider/model for both is valid. Add further specialization only
when actual tasks benefit from a different instruction set or provider binding.

## Existing Foundation And Feasibility Boundary

The [capability matrix](../capability_status_matrix.md) distinguishes available
pieces from proposed features:

- [Direct task invocation](../../workflows/library/control/direct_task.orc)
  demonstrates ordinary provider calls with model/effort inputs. Its Boolean
  return is not the richer work-result contract proposed here.
- [Verified iteration](../../workflows/library/verified_iteration_drain/drain.orc)
  demonstrates bounded repeated work, checks, and result routing. Reuse its
  mechanisms where they fit, not its full ledger, commit, and review procedure.
  Its check script also packages commit-based review evidence; it is not assumed
  to be a drop-in checker for uncommitted work.
- Typed outcomes, record loop state, and supported prompt dataflow are existing
  building blocks. The exact coordinator composition above still needs an
  executable integration proof. Individual feature tests do not establish it.
- General task-record list traversal, runtime-selected provider values, and
  unbounded recursion are not prerequisites. Provider bindings are declared;
  this design does not imply arbitrary providers can be passed as runtime data.
- [Provider context values](workflow_lisp_provider_context_values.md) now has an
  implemented target-2.31 ordinary Codex subset; native continuation remains
  proposed. [Agentic source synthesis](../backlog/active/2026-06-01-workflow-lisp-agentic-decomposition-synthesis.md)
  remains separate work. This application does not close that backlog item.

The intended addition is one concrete, callable coordinator with small
planner/worker prompt assets and a software demo using the existing compile/run
path. Do not start with a configurable policy framework or plugin registry.
Extract general-purpose helpers only when they remove actual duplication or a
demonstrated awkward caller boundary. The target introduces no CLI, scheduler,
database, framework-specific run store, language keyword, or workflow-specific
compiler/runtime node. Existing workflows need no migration.

`check-project` is a possible ordinary helper name, not a new primitive. Its
responsibility is limited to invoking project checks and exposing their outcomes
and evidence through existing result contracts. It must not become another
execution engine or take over planning, retries, or progress management.

Before treating this as implementation-ready, prove planner outcome matching,
worker result carriage, check-failure routing, and progress continuation through
the ordinary public workflow path. Resolve whether existing command-result
mechanics can expose project check failures as data without importing the drain's
commit assumptions. Classify obstacles before expanding the design:

- An implementation defect calls for a fix in the existing owning layer.
- An awkward general-purpose interface calls for considering a principled
  simplification there, rather than bespoke adapters for this workflow.
- A requirement for substantial new language or runtime machinery calls for
  reconsidering the approach and its alternatives before expanding scope.

Justify any language change by the general capability or ergonomic problem it
solves; this demo may supply that evidence. Zero new machinery is the default,
not a ban on revisiting language assumptions when evidence supports it. These
are concrete feasibility prerequisites, not reasons to build a wider framework
first or hide one behind helpers.

The separate [incremental composition design](workflow_lisp_value_and_continuation_composition.md)
addresses the identified value-flow and conversation gaps. It is not a mandatory
bundle of prerequisites for this application; use only corrections its actual
implementation needs.

## Demo And Verification

Choose a real feature in an existing software repository, with meaningful
milestones and project-native acceptance checks. No particular demonstration
feature is selected by this design.

The public-path integration check should exercise a task result, a failed check
that causes revised work, eventual completion, and the question/incomplete
outcomes. Deterministic providers may establish routing correctness; a normal
tool-enabled provider session must separately demonstrate useful work. Include
a continuation after a user answer without treating it as crash recovery.

The walkthrough should let a reader see the agreed brief, broad outline,
selected task, relevant instructions, actual result, check evidence, and why
the next action changed. Use existing artifacts and output; no dashboard or
separate identity ledger is needed. Compare the delivered feature with the
agreed goal, including qualitative review of comment usefulness. Do not assert
literal prompt wording or demand artificially exact prose/receipt formatting.

Assess reuse by adapting the caller to another genuine task and examining the
edits and concepts it requires. Human or LLM review can help explain friction;
passing a fixed number of examples is not a measure of ergonomic reuse. If
coordination costs more attention than it saves for a task, use the ordinary
agent path. Review added calls, handoffs, type declarations, and bookkeeping as
real costs even when no DSL extension is involved. Interface repair is ordinary
development, not conditional on an experimental budget or a demonstration score.

## Improvement Without Premature Generalization

Keep improvements tied to demonstrated needs across the five axes:

- **Composition:** make the coordinator callable with useful results. If callers
  need adapters around equivalent values, revisit that boundary or language
  design; remove abstractions that do not simplify actual callers.
- **Reuse:** improve task/profile substitution where adaptation is awkward.
  Keep genuinely domain-specific behavior local instead of forcing universality.
- **Introspection:** expose missing decision inputs and outcomes through existing
  run artifacts. Remove duplicate reports rather than adding another ledger.
- **Self-programmability:** this version changes plans, not executable control
  structure. If real tasks need agents to choose a different coordination
  topology, design generated `.orc` composition then; do not pretend task-text
  edits already demonstrate program synthesis.
- **Program-space optimization:** ordinary modules leave policies available for
  later comparison and revision. Search infrastructure is justified only after
  useful alternatives and meaningful evaluation exist; it is not part of this
  demo. Retire policies that do not earn their complexity.

Using the implemented host-input and portable-context facilities in this
coordinator, or adding parallel decomposition and recursion, should follow
observed needs. A troublesome
current type or language restriction warrants reconsidering the foundation,
not automatically abandoning the use case. Conversely, a capability that adds
no practical value should be dropped and its surrounding machinery simplified.
