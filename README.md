# Agent Orchestration

A compiler and runtime that turns LLM-agent workflows into typed, checked,
replayable programs.

A workflow is a program in Workflow Lisp (`.orc`). Its steps invoke coding
agents and shell commands. The compiler checks, before anything runs, what
each step must produce, what it may touch, and how its outcome routes the
rest of the program. The runtime enforces those contracts on what the agents
actually produce, commits nothing that fails them, and can resume any run
from its last committed effect. There is no service: a run is a directory
under `.orchestrate/runs/<run_id>/` holding state, composed prompts, logs,
and the source map back to the authored program.

The stance is that an LLM agent is an unreliable, effectful coprocessor. The
deterministic side of the system should own every correctness obligation it
can carry, and the agent should be asked only for the part that needs
judgement.

## Why: correctness obligations should not live in prose

When you compile a C program you do not assign addresses to variables, invent
a calling convention per function, or parse the bytes a callee leaves behind.
The toolchain does that. Agent pipelines today have no such toolchain, so each
one hand-rolls the same machinery: file paths for intermediate state threaded
through prompts and glue, output formats described in prose, results parsed
with regex, "looks done" decided by inspection, and reruns from scratch after
a failure halfway through.

| A CPU toolchain gives you | Hand-rolled in agent pipelines | Owned by the compiler and runtime here |
| --- | --- | --- |
| Storage layout | Invented file paths for every intermediate artifact | Runtime-allocated state layout, private by default, provenance-tracked |
| Calling conventions | Output format restated in prose in every prompt | The declared result type is rendered into the prompt as an output contract and enforced on the result |
| Type checking | Stringly-typed status fields compared by convention | Records, tagged unions, enums, and path contracts checked before execution |
| Defined failure semantics | Partial junk left on disk when a step half-finishes | Fail-closed validation; nothing becomes canonical state until it passes |
| Compiled control flow | Routing by parsing model output | Branches and bounded loops over typed outcomes, compiled to a resumable program |
| Debugger and symbols | Scrolling transcripts | Source maps from every effect back to the authored form, plus inspectable run state |
| Crash recovery | Rerun and pray | `resume <run_id>` replays committed effects from a memo and continues |

## Sixty seconds of Workflow Lisp

Claude drafts a plan. Codex reviews it. Claude revises the plan with that
feedback. Codex executes the revised plan. This is
[`workflows/examples/plan_review_execute.orc`](workflows/examples/plan_review_execute.orc),
and it compiles with the command in its header.

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule plan_review_execute)
  (export run)

  (defrecord Plan (steps List[String]))
  (defrecord Feedback (findings List[String]))
  (defrecord Execution (summary String))

  (defprompt draft-plan (:fills (task :text)) -> Plan
    "Plan this task as ordered steps, naming the files each step touches. Change no files.\n\nTask: {task}")
  (defprompt review-plan (:fills (task :text) (steps :value List[String])) -> Feedback
    "Review this plan: what would make it fail or leave the task's scope? Change nothing.\n\nTask: {task}\nPlan: {steps}")
  (defprompt revise-plan (:fills (task :text) (steps :value List[String]) (findings :value List[String])) -> Plan
    "Revise the plan so that every finding is addressed. Change no files.\n\nTask: {task}\nPlan: {steps}\nFindings: {findings}")
  (defprompt execute-plan (:fills (task :text) (steps :value List[String])) -> Execution
    "Execute this plan in the current repository.\n\nTask: {task}\nPlan: {steps}")

  (defworkflow run ((task String)) -> Execution
    (let* ((draft (provider-result providers.claude :model "claude-fable-5-1" :effort "high"
                    :prompt (draft-plan :task task)))
           (feedback (provider-result providers.codex
                       :prompt (review-plan :task task :steps draft.steps)))
           (revised (provider-result providers.claude :model "claude-fable-5-1" :effort "high"
                      :prompt (revise-plan :task task :steps draft.steps :findings feedback.findings))))
      (provider-result providers.codex
        :prompt (execute-plan :task task :steps revised.steps))))
)
```

The prompts say what to do. They do not describe JSON. `-> Plan` and
`-> Feedback` fix the contracts: the runtime appends the required fields,
their types and the result location to the composed prompt, parses what the
agent writes, and validates it before the next call can use it. A field
access such as `feedback.findings` is checked at compile time against the
declared record, so a prompt can only be filled with a value that exists and
has the right type. Compiling this module yields a closed program with exactly
four effect sites, known before anything runs. If the last call fails, resume
takes the first three results from the memo and runs only the execution again.
Provider names bind to agent CLIs in a small manifest outside the program, so
the same source runs against different agents.

| Codex's answer to `review-plan` | Result |
| --- | --- |
| `{"findings":["Step 2 edits a file that does not exist"]}` | Claude's revise prompt is filled with a list of strings |
| `{"findings":"add tests"}` | a string is not a list of strings; rejected |
| `{"findings":["add tests", 7]}` | wrong element type; rejected |
| `{}` | required field missing; rejected |

Branching and loops are typed the same way: a reviewer that may approve or
request changes returns a tagged union, `match` must cover every variant, and
a loop is bounded with a typed exhaustion outcome. The bundled `std/improve`
helper packages that review-and-revise loop; see
[`workflows/examples/improve_experiment_proposal.orc`](workflows/examples/improve_experiment_proposal.orc).

## What is checked, and where

| Obligation | Discharged by | When |
| --- | --- | --- |
| The shape of an agent's result | Declared record or union type, rendered as the output contract and validated on return | compile time for the declaration; run time, before any consumer sees the value |
| Routing on an outcome | Tagged unions; exhaustive `match`; variant fields unreachable without proof | compile time, with a runtime guard in the lowered program |
| What a procedure may do | Declared or inferred effects: providers used, commands run, paths written; imported procedures carry theirs | compile time |
| What a shell command may run and read | A command boundary manifest with a closure declaration; nothing undeclared runs | compile time, enforced at run time from target 2.35 |
| Where artifacts may live | Path types with a root and an existence requirement | compile time and on every write |
| Termination | Bounded loops with a typed exhaustion outcome; no recursion; no first-class procedures | compile time |
| Pure computation | A closed, total operator set; compile-time folding must agree with the runtime evaluator on shared golden vectors | both |
| "Done" means done | Validate, write to a temporary location, atomic rename; nothing else becomes canonical state | run time |
| Resume | Every effect has a semantic identity; a committed result is taken from the memo rather than rerun | run time |

Reports, logs, dashboards, and the agent's own prose summaries are views.
Nothing routes on them.

## Execution model

```text
.orc source
  -> frontend AST
  -> macro and import expansion, compile-time procedure specialization
  -> typecheck
  -> core-calculus elaboration (ANF)
  -> scope, effect, and proof analysis
  -> closed program
  -> evaluation with an effect memo, on disk, resumable
```

- **The middle end is a small core calculus in ANF**, roughly ten constructs:
  atoms, `let`, effect performs, variant inject and case, join points, bounded
  recursion, calls, halt. Programs that typecheck lower; there is no
  "well-typed but dies after lowering" class of failure on the admitted subset.
- **The compiled artifact is a closed program.** Loops are bounded, there are
  no runtime closures, and the effect vocabulary is fixed, so every effect site
  and its contract is known before a run starts.
- **Evaluated execution** (targets 2.35 and 2.36): values are computed in a
  lexical environment and have no stored copy. An effect is identified by its
  site and the path of activations that reached it, and nothing else. An
  effect runs only when the memo holds no committed result for that identity.
  Resume evaluates the program again from its entry and takes each committed
  result from the memo. What a reader sees as "steps" is a view derived from
  the memo and the program.
- **Identity is semantic and versioned.** It derives from module, role, call
  frame, and loop scope plus a lowering schema version, never from source
  spans. Resume fails closed across schema boundaries instead of replaying
  into a program with a different meaning.
- **Two authority lanes.** A semantic IR records what a workflow means: types,
  effects, provenance. An executable IR is what runs. Reports and debug
  projections are derived from them and are never parsed as authority.

Deeper reading:
[core calculus and middle end](docs/design/workflow_lisp_core_calculus_middle_end.md),
[evaluated execution](docs/design/workflow_lisp_evaluated_execution.md),
[frontend specification](docs/design/workflow_lisp_frontend_specification.md),
and the normative [spec index](specs/index.md).

## Evidence rather than claims

The repository records negative results next to positive ones.

| Study | What was measured | Outcome |
| --- | --- | --- |
| [Workflows versus a single agent call](docs/reports/2026-09-28-orc-versus-single-call.md) | A real compiler defect, six runs per configuration, two blind model judges per batch, 8-point rubric | Generate-four-select-one with a stronger judge from another model family: +0.83 and +1.02 over the candidate-group mean. Review-and-revise with the author's own model as reviewer: between -0.5 and +0.44, no reliable gain |
| [Earlier pilot](docs/reports/2026-07-26-orc-effectiveness-lean-pilot.md) | A PyTorch port task, direct call versus coordinator versus workflow | The direct call won all three blocks; the workflow was viable in one of three. Recorded as such |
| [Language limitations found in use](docs/reports/2026-09-29-orc-language-limitations-and-solutions.md) | A search controller written five ways against the flat step runtime | Three refusals, one 361-node expression against a 256-node bound. This motivated evaluated execution, which now runs the same program |
| [Design lessons](docs/orc_workflow_design_lessons.md) | What a workflow must add that the agent cannot give itself | Independent candidates plus a judge with different knowledge than the author were the only measured sources of gain |

The conclusion the evidence supports is narrow: a workflow beats a single call
when it supplies something the agent lacks, and the cost of finding out is one
disciplined experiment. The runtime's value is that the experiment is
cheap to run and its evidence is complete.

## Scale and provenance

| | |
| --- | --- |
| First commit | 2025-09-14 |
| Commits on `main` | about 2,900 |
| Python in `orchestrator/` | about 350k lines |
| Tests collected | 23,988 |
| Core contract versions | DSL v1.1 through v2.36, each with a normative spec and migration rules |
| Agent CLIs driven | Codex, Claude Code, Gemini CLI, oh-my-pi |
| Runtime dependencies | `jsonschema`, `PyYAML`; Python 3.11+ and `bash` |

Much of the compiler and runtime was built by agent runs driven by this
runtime: design, plan, implement, and review loops whose plans, reviews, and
closeout evidence are checked in under `docs/plans/` and `docs/reports/`.
The same runtime has driven autonomous design-to-review tranches on physics
codebases outside this repository, among them ptychographic reconstruction and
EPR spectroscopy simulation; those runs used an earlier YAML frontend that has
since been retired in favor of `.orc`.

## Where this points

Statuses follow the
[capability status matrix](docs/capability_status_matrix.md).

- **Checked program evaluation** (proposed). An agent produces source text; the
  ordinary compiler checks it against input and result types, permitted
  imports, an effect bound, and a budget fixed by the parent program; the
  ordinary runtime evaluates it. A rejected program returns located
  diagnostics that feed a normal repair loop. See
  [the design](docs/design/workflow_lisp_checked_program_evaluation.md).
- **Provider isolation** (versioned contract; runtime integration pending).
  Agents launch under `bubblewrap` from a sealed, digest-verified root
  filesystem snapshot, with the runtime's own state masked and every mismatch
  failing closed. See [`specs/providers.md`](specs/providers.md).
- **Human in the loop** (implemented, target 2.32). `request-input` suspends a
  run on a typed question; resume validates and consumes the exact reply.
- **Editor support** (implemented). A read-only language server over the
  production compiler: diagnostics, definitions, symbols. Install with the
  `[lsp]` extra and run `python -m orchestrator.lsp`.

## Try it

```bash
git clone git@github.com:hoidn/agent-orchestration.git
cd agent-orchestration
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m orchestrator --help
```

### First compile check

Compile a workflow without running any provider:

```bash
python -m orchestrator compile \
  workflows/examples/review_revise_design_docs.orc \
  --provider-externs-file workflows/examples/inputs/review_revise_design_docs/providers.json \
  --prompt-externs-file workflows/examples/inputs/review_revise_design_docs/prompts.json
```

Dry-run the example above with its provider bindings and a task:

```bash
python -m orchestrator run workflows/examples/plan_review_execute.orc \
  --entry-workflow plan_review_execute::run \
  --provider-externs-file workflows/examples/inputs/plan_review_execute/providers.json \
  --input-file workflows/examples/inputs/plan_review_execute/inputs.json \
  --dry-run
```

Run for real once your agent CLI works in the same shell, and resume if it
stops partway:

```bash
python -m orchestrator run <workflow.orc> --entry-workflow <module::entry> \
  --provider-externs-file <providers.json> --prompt-externs-file <prompts.json> \
  --input-file <inputs.json> --stream-output

python -m orchestrator resume <run_id> --stream-output
```

Inspect a run:

| Question | Where |
| --- | --- |
| What did each step produce, and what failed? | `.orchestrate/runs/<run_id>/state.json` |
| What did the agent actually see, including the injected contract? | `.orchestrate/runs/<run_id>/logs/<Step>.prompt.txt` |
| Readable report | `python -m orchestrator report --run-id <run_id> --format md` |
| Local read-only dashboard | `python -m orchestrator dashboard --workspace "$(pwd)"` |
| Headless email alerts on completion, failure, or stall | `python -m orchestrator monitor`; see [`docs/workflow_monitoring.md`](docs/workflow_monitoring.md) |

If agent behavior looks wrong, read the composed prompt before changing
workflow logic. If routing looks wrong, read `state.json` and the declared
contracts before changing prompts.

## Reading paths

| Goal | Read |
| --- | --- |
| Map of the documentation | [`docs/index.md`](docs/index.md) |
| Whether a surface is implemented, partial, designed, or legacy | [`docs/capability_status_matrix.md`](docs/capability_status_matrix.md) |
| The execution model in prose | [`docs/orchestration_start_here.md`](docs/orchestration_start_here.md) |
| Author a `.orc` workflow | [`docs/lisp_workflow_drafting_guide.md`](docs/lisp_workflow_drafting_guide.md) |
| Which example to copy | [`workflows/README.md`](workflows/README.md#which-example-should-i-copy) |
| Normative contracts | [`specs/index.md`](specs/index.md) |
| Design principles behind the language | [`docs/design/workflow_language_design_principles.md`](docs/design/workflow_language_design_principles.md) |

## Repository map

| Path | Purpose |
| --- | --- |
| [`orchestrator/`](orchestrator/) | Workflow Lisp frontend and compiler, validator, evaluator, providers, CLI, dashboard, language server |
| [`specs/`](specs/) | Normative DSL, CLI, state, provider, IO, security, and versioning contracts |
| [`docs/`](docs/) | Guides, design docs, plans, and reports, including negative results |
| [`workflows/`](workflows/) | Runnable examples, the standard library's reusable procedures, and prompt assets |
| [`experiments/`](experiments/) | Material of the studies cited above: workflows, rubrics, ratings, harnesses |
| [`tests/`](tests/) | Unit, compiler, runtime, workflow, and fixture tests |

## License

Functional Source License, Version 1.1, MIT Future License
(`FSL-1.1-MIT`). See [`LICENSE.md`](LICENSE.md).
