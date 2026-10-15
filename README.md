# Agent Orchestration

A compiler and runtime that turns LLM-agent workflows into typed, checked,
replayable programs.

A workflow is a program in Workflow Lisp (`.orc`). Its steps invoke coding
agents and shell commands. The compiler checks, before anything runs, what
each step must produce, what it may touch, and how its outcome routes the
rest of the program. The runtime enforces those contracts on what the agents
actually produce, commits nothing that fails them, and can resume a run
from its last committed effect. There is no service: a run is a directory
under `.orchestrate/runs/<run_id>/` holding state, composed prompts, logs,
and the checked program with the source location of every node.

## Motivation

Most agent frameworks check one call at a time. A schema validates what a
single model call returns, and the host language carries the result to the
next call. What is not checked is the pipeline: that a later prompt is filled
only from fields an earlier step is guaranteed to produce, that every outcome
is handled, that every loop ends, what each step may touch, and what can be
reused when a run dies halfway. Those obligations live in glue code and
prompts, and they surface at run time, one failure at a time.

Here the pipeline is the program, and the program is checked as a whole
before it runs. Each step declares the type of its result. The compiler checks
that every prompt is filled only with values that exist and have the right
shape, that every outcome is routed somewhere, that every loop ends, and what
each step may touch. During the run, what the agent actually returns is
validated against the same type before any later step can read it; a result
that fails is never committed, and a run that stops can resume from its last
committed result.

## Example

Claude drafts a plan. Codex reviews it. Claude revises the plan with that
feedback. Codex executes the revised plan. This is
[`workflows/examples/plan_review_execute.orc`](workflows/examples/plan_review_execute.orc),
and it compiles with the command in its header. When the plan is a real design
document, [`design_review_execute.orc`](workflows/examples/design_review_execute.orc)
keeps it as a markdown file under `docs/design/` and passes its typed path.

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

`-> Plan` and `-> Feedback` fix the contracts: the runtime appends the required fields,
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
| Where artifacts may live | Path types with a root and an existence requirement | compile time, and at run time when a result carrying the path is validated |
| Termination | Bounded loops with a typed exhaustion outcome; no recursion; no first-class procedures | compile time |
| Pure computation | A closed operator set whose failures are refusals rather than exceptions; compile-time folding must agree with the runtime evaluator on shared golden vectors | both |
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
  recursion, calls, halt.
- **The compiled artifact is a closed program.** Loops are bounded, there are
  no runtime closures, and the effect vocabulary is fixed, so every effect site
  and its contract is known before a run starts.
- **Evaluated execution** (targets 2.35 to 2.38): values are computed in a
  lexical environment and have no stored copy. An effect is identified by its
  site and the path of activations that reached it, and nothing else. An
  effect runs only when the memo holds no committed result for that identity.
  Resume evaluates the program again from its entry and takes each committed
  result from the memo. What a reader sees as "steps" is a view derived from
  the memo and the program. At 2.38 an agent keeps its native conversation
  across turns, with a typed result and a memo commit per turn
  ([agent sessions](docs/lisp_workflow_drafting_guide.md#agent-sessions-target-238)).
- **Identity is semantic and versioned.** It derives from the effect's site
  and the activations that reached it, loop ordinals included, under the run's
  schema version; never from source spans, file paths, or formatting. Resume
  fails closed on a run whose schema it does not know instead of replaying
  into a program with a different meaning.
- **Program and effect authority.** The checked closed program is what runs.
  The memo journal is the authority for committed effects. Reports and state
  projections are derived views and are never parsed as execution authority.

Deeper reading:
[core calculus and middle end](docs/design/workflow_lisp_core_calculus_middle_end.md),
[evaluated execution](docs/design/workflow_lisp_evaluated_execution.md),
[frontend specification](docs/design/workflow_lisp_frontend_specification.md),
and the normative [spec index](specs/index.md).

## Experiments

| Study | What was measured | Outcome |
| --- | --- | --- |
| [Workflows versus a single agent call](docs/reports/2026-09-28-orc-versus-single-call.md) | A real compiler defect, six runs per configuration, two blind model judges per batch, 8-point rubric | Generate-four-select-one with a stronger judge from another model family: +0.83 and +1.02 over the candidate-group mean. With the author's own model as reviewer or selector: between -0.5 and +0.44. Review-and-revise with a stronger reviewer from another family: +0.58 |
| [Workflows versus single calls, rerun on the evaluated route](docs/reports/2026-10-14-orc-versus-single-call-evaluated.md) | The same defect and criterion, frozen before any run; six runs per workflow and six single calls, sandboxed agents, two blind judges | Review-and-revise replicated (+0.67 over its first patch, no run worse); generate-four-select-one fell one run short (4 of 6 runs gained, mean +1.02); both scored under half a point above the single calls |
| [Design lessons](docs/orc_workflow_design_lessons.md) | What a workflow must add that the agent cannot give itself | Gains come from independent candidates and from a judge with different knowledge than the author |

## Scale and provenance

| | |
| --- | --- |
| First commit | 2025-09-14 |
| Commits on `main` | about 3,200 |
| Python in `orchestrator/` | about 260k lines |
| Tests collected | about 16,100 |
| Core contract versions | DSL v1.1 through v2.38, each with a normative spec and migration rules |
| Agent CLIs driven | Codex, Claude Code, Gemini CLI, oh-my-pi |
| Runtime dependencies | `jsonschema`, `PyYAML`; Python 3.11+ and `bash` |

Much of the compiler and runtime was built by agent runs driven by this
runtime: design, plan, implement, and review loops whose plans, reviews, and
closeout evidence are checked in under `docs/plans/` and `docs/reports/`.
The same runtime has driven autonomous design-to-review tranches on physics
codebases outside this repository, among them ptychographic reconstruction and
EPR spectroscopy simulation; those runs used an earlier YAML frontend that has
since been retired in favor of `.orc`.

## Roadmap

Statuses follow the
[capability status matrix](docs/capability_status_matrix.md).

- **Provider isolation** (versioned contract; run integration pending). The
  contract launches agents under `bubblewrap` from a sealed, digest-verified
  root filesystem snapshot, with the runtime's own state masked and every
  mismatch failing closed. The backend exists; `run` and `resume` do not use
  it yet. See [`specs/providers.md`](specs/providers.md).

## Try it

```bash
git clone https://github.com/hoidn/agent-orchestration.git
cd agent-orchestration
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11 or later
pip install -e ".[dev]"
python -m orchestrator --help
```

### First compile check

Compile a workflow without running any provider:

```bash
python -m orchestrator compile \
  workflows/examples/plan_review_execute.orc \
  --entry-workflow plan_review_execute::run \
  --provider-externs-file workflows/examples/inputs/plan_review_execute/providers.json
```

Dry-run the example above with its provider bindings and a task:

```bash
python -m orchestrator run workflows/examples/plan_review_execute.orc \
  --entry-workflow plan_review_execute::run \
  --provider-externs-file workflows/examples/inputs/plan_review_execute/providers.json \
  --input-file workflows/examples/inputs/plan_review_execute/inputs.json \
  --dry-run
```

Drop `--dry-run` to run it for real. The example calls the `claude` and
`codex` CLIs, so both must be installed and logged in. A run that stops
partway resumes from its last committed effect:

```bash
python -m orchestrator resume <run_id> --stream-output
```

A read-only language server over the same compiler gives editors diagnostics,
definitions and symbols: install the `[lsp]` extra and run
`python -m orchestrator.lsp`.

Inspect a run:

| Question | Where |
| --- | --- |
| What did each step produce, and what failed? | `.orchestrate/runs/<run_id>/state.json`, the effect memo `memo.jsonl` beside it, or `orchestrator repl --run-id <run_id>` |
| What did the agent actually see, including the injected contract? | `.orchestrate/runs/<run_id>/effects/<effect>/attempt-<n>/prompt.txt` |
| Readable report | `python -m orchestrator report --run-id <run_id> --format md` |
| Local read-only dashboard | `python -m orchestrator dashboard --workspace "$(pwd)"` |
| Headless email alerts on completion, failure, or crash | `python -m orchestrator monitor`; see [`docs/workflow_monitoring.md`](docs/workflow_monitoring.md) |

If agent behavior looks wrong, read the composed prompt before changing
workflow logic. If routing looks wrong, read `state.json` and the declared
contracts before changing prompts.

## Versions and compatibility

Releases are tagged. A workflow names its target in its header
(`(:target-dsl "2.35")`), and each release executes a fixed set of targets:

| Release | Executes |
| --- | --- |
| `v0.2.0` | Targets 2.35 and 2.36; 2.37 adds parallel `list/map-effect` and 2.38 adds agent sessions and command-only confined child workflows |
| `v0.1.0` (2026-10-13) | Targets 2.14 through 2.34 on the earlier flat runtime, and 2.35 through 2.37 |

Compiling a workflow checks it against the installed release without running
anything. A target the release no longer executes is refused at its header
with `workflow_execution_target_retired`; check out the release that executes
it (`git checkout v0.1.0`) and reinstall. Retiring a target bumps the minor
version, and the previous release stays tagged.
[`specs/versioning.md`](specs/versioning.md#version-gating-summary) records
what each target admits.

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
| [`orchestrator/`](orchestrator/) | Workflow Lisp frontend and compiler, the `std/` library modules, validator, evaluator, providers, CLI, dashboard, language server |
| [`specs/`](specs/) | Normative DSL, CLI, state, provider, IO, security, and versioning contracts |
| [`docs/`](docs/) | Guides, design docs, plans, and reports |
| [`workflows/`](workflows/) | Runnable examples, library workflows, templates, and prompt assets |
| [`experiments/`](experiments/) | Material of the studies cited above: workflows, rubrics, ratings, harnesses |
| [`tests/`](tests/) | Unit, compiler, runtime, workflow, and fixture tests |

## License

Functional Source License, Version 1.1, MIT Future License
(`FSL-1.1-MIT`). See [`LICENSE.md`](LICENSE.md).
