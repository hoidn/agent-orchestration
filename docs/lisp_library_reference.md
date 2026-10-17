# Workflow Lisp Library Reference

Use this page to choose a reusable helper or complete example. Each entry
names the target it runs at. Typed 2.35/2.36 checks types before execution and
can resume a run; native 3.0 composes ordinary functions and closures in fresh
runs. The [drafting guide](lisp_workflow_drafting_guide.md) covers authoring;
[versioning](../specs/versioning.md) defines each target. A source keeps its
declared target; the runtime never retargets an example or an import.

## Choose by task

| Task | Entry | Kind and prerequisites |
| --- | --- | --- |
| Generate independent code changes and choose one | [Generate candidates and select](#generate-candidates-and-select) | Typed 2.35 example, serial; caller prepares candidate repositories and provider bindings |
| Review and revise one candidate | [Review and revise](#review-and-revise) | Typed `std/improve` or native `std/dynamic/improve`; caller supplies hooks and domain data |
| Obtain a deterministic score | [Evaluate with an external command](#evaluate-with-an-external-command) | Typed 2.35 example with its scorer and command manifest |
| Search under an evaluation budget | [Iterative search](#iterative-search) | Native 3.0 controller over local commands; the application defines the policy |
| Inspect a loaded module or run | [REPL guide](lisp_workflow_drafting_guide.md#inspect-a-run-with-the-workflow-lisp-repl) | Typed 2.35/2.36 or native 3.0; declaration inspection does not run effects |

Selection compares alternatives; revision changes one candidate; evaluation
supplies evidence; a controller chooses what to propose next. No generic
candidate, fitness, population or merge API is supplied. The
[design lessons](orc_workflow_design_lessons.md) say when each pattern pays off.

Compile and dry-run validate source, bindings and inputs without launching
providers or commands, and without reading command executables. Execution pins
the declared command closures under the
[command adapter contract](design/workflow_command_adapter_contract.md#command-closure-declaration).

## Generate candidates and select

**Kind:** example workflow. The complete
[`best_of_n.orc`](../experiments/orc_vs_single_call/workflows/best_of_n.orc)
targets **2.35**. Its `best-of-n(task: String, intent: String,
repos: List[String]) -> Selection` calls `implement-one` serially through
`list/map-effect` (maximum eight), then asks a judge to choose a repository.
`select-only(intent, repos, accounts) -> Selection` runs only the judge.
`Selection` contains `winner: String`, `ranking: List[String]` and a typed
report path. These are provider-produced judgments, not proofs of membership
or quality; the result does not merge or promote a change.

All input values come from the caller. Prepare a nonempty list of at most eight
separate existing clones from the same clean baseline, with their required
application environment already installed. Supply a task that applies to that
baseline, an intended change for judging and the clone paths. For `select-only`,
supply one account per repo in matching order; the module adds no alignment
check. It does not create clones, install environments or sandbox provider tools,
and no primitive prepares repositories or runs expressions in isolated
environments.

The module supplies its types and two prompts. The
[provider manifest](../experiments/orc_vs_single_call/workflows/best_of_n.providers.json)
binds coder/judge to `claude_unrestricted_workspace` and
`codex_unrestricted_workspace`; those configurations and CLIs must be available.
The source supplies explicit model, effort and timeout choices. These bindings
allow unrestricted workspace tools; clones provide separation, not an OS sandbox.
The judge reads candidate changes and writes under `artifacts/review` in its
working root. Its ratings exclude test results; use a separate evaluator if tests
or numerical evidence should influence selection.

From the repository root, this checks the complete source and bindings:

```bash
python -m orchestrator compile experiments/orc_vs_single_call/workflows/best_of_n.orc \
  --entry-workflow best_of_n::best-of-n \
  --source-root experiments/orc_vs_single_call/workflows \
  --provider-externs-file experiments/orc_vs_single_call/workflows/best_of_n.providers.json
```

The [operating recipe](../experiments/orc_vs_single_call/README.md#run-the-maintained-best-of-n-workflow)
gives clone preparation, complete JSON inputs and compile/dry-run/run/resume
commands from the prepared candidate working root. Candidates execute in
order, not in parallel, and there are no ProcRef hooks.

## Review and revise

`improve` runs a bounded review/revise loop. Review returns `Decision[F B]`:
APPROVE with evidence, REVISE with feedback, or BLOCKED with a reason. Revision
returns the next candidate. `Improvement[S F B]` returns APPROVED (`value`,
`evidence`), BLOCKED (`value`, `reason`) or EXHAUSTED (`value`, potentially an
unreviewed final revision). Use the returned `value` downstream. Hook failures,
malformed boundaries and timeouts retain ordinary failure behavior; they do not
become exhaustion. [Composition-first §3](design/workflow_lisp_composition_first.md#3-interface)
and [§4](design/workflow_lisp_composition_first.md#4-loop-and-termination)
own the typed outcome and round contracts.

| Entry profile | Import/call | Hooks and limits |
| --- | --- | --- |
| Typed 2.35 | `std/improve`; `(improve initial inputs review revise limit)` | `review(S I) -> Decision[F B]`; `revise(S I F) -> S`; positive compile-time round limit |
| Typed 2.36 | `std/improve`; `(improve initial review revise limit)` | `review(S) -> Decision[F B]`; `revise(S F) -> S`; local hooks may capture context; same typed round limit |
| Native 3.0 | `std/dynamic/improve`; `(improve initial review revise limit)` | Ordinary functions/captures; declared boundary schemas; positive runtime limit and entry operation budget |

The typed entry target selects **one API for the whole source import graph**.
Retargeting to 2.36 requires migrating five-argument source callers, including
indirect dependencies; compatible and type-only older modules remain legal.
Imported compiled snapshots keep the API they were built with. See
[write-once §9](design/workflow_lisp_write_once.md#9-targets-and-compatibility)
for identity and resume guards. Native imports the domain declarations, not the
typed helper's body; its four-argument helper is a separate module.

### Complete typed examples

These pure examples demonstrate the actual APIs without provider or command
setup. Save as `improve_explicit.orc` and `improve_local.orc` in a disposable
workspace using a Python environment where this checkout is importable.
The first explicitly passes the brief at 2.35:

```lisp
(workflow-lisp
  (:language "0.1") (:target-dsl "2.35")
  (defmodule improve_explicit)
  (import std/improve :only (Decision Improvement improve))
  (export run)
  (defrecord Draft (title String))
  (defrecord Brief (goal String))
  (defrecord Notes (note String))
  (defrecord Blocker (reason String))
  (defproc review ((draft Draft) (brief Brief)) -> Decision[Notes Blocker]
    :effects () :lowering inline
    (variant Decision[Notes Blocker] APPROVE
      :evidence (record Notes :note brief.goal)))
  (defproc revise ((draft Draft) (brief Brief) (notes Notes)) -> Draft
    :effects () :lowering inline draft)
  (defworkflow run ((goal String :default "clear")) -> Improvement[Draft Notes Blocker]
    (improve (record Draft :title "draft") (record Brief :goal goal)
             (proc-ref review) (proc-ref revise) 3)))
```

The second captures `goal` in grouped local hooks at 2.36:

```lisp
(workflow-lisp
  (:language "0.1") (:target-dsl "2.36")
  (defmodule improve_local)
  (import std/improve :only (Decision Improvement improve))
  (export run)
  (defrecord Draft (title String))
  (defrecord Notes (note String))
  (defrecord Blocker (reason String))
  (defworkflow run ((goal String :default "clear")) -> Improvement[Draft Notes Blocker]
    (let-proc
      ((review (draft)
         (variant Decision[Notes Blocker] APPROVE
           :evidence (record Notes :note goal)))
       (revise (draft notes) draft))
      (improve (record Draft :title "draft") (proc-ref review) (proc-ref revise) 3))))
```

Run from that workspace (replace the filename to exercise the other profile):

```bash
python -m orchestrator compile improve_explicit.orc --entry-workflow run
python -m orchestrator run improve_explicit.orc --entry-workflow run --dry-run
python -m orchestrator run improve_explicit.orc --entry-workflow run
```

Both return APPROVED with title `draft` and evidence note `clear`. The hooks
are illustrative deterministic policy; approval here proves no domain quality.
A 2.36 local hook without a full signature needs exactly one direct call site;
full signatures permit reuse. Sibling/self calls, nested locals and recursion
are not supported. See the [local hook contract](design/workflow_lisp_write_once.md#63-language-changes-to-let-proc).

The complete [experiment-proposal application](../workflows/examples/improve_experiment_proposal.orc)
targets **2.33**, with explicit top-level hooks and five arguments. Its
[drafting recipe](lisp_workflow_drafting_guide.md#137-improve) lists the
provider/prompt manifests and the workspace launcher it needs. Retargeting it
to 2.36 requires migrating its `improve` call.

### Native consumer and prerequisites

The complete [native consumer](../tests/fixtures/workflow_lisp/dynamic/improve.orc)
imports [std/dynamic/improve](../orchestrator/workflow_lisp/stdlib_modules/std/dynamic/improve.orc)
and passes captured review/revise functions. The
[consumer and setup](lisp_workflow_drafting_guide.md#complete-imported-improvement-consumer)
explain the staged `dynamic_consumer/improve.orc`, renamed `types.orc`, probe
scripts, command manifest, event-log environment and public smoke. The fixture
path alone cannot be launched from the CLI. Workflow and command results keep
strict declared schemas; internal functions have no inferred signatures.

Native 3.0 runs are fresh-only: no resume, invalidation or result reuse, so a
corrected fresh run may repeat earlier calls and writes. Provider and command
effects run sequentially. Parallel, child-run, trial, resource, view and
host-input effects, and provider session, context, phased and live surfaces,
are not available ([native target 3.0](../specs/versioning.md#native-target-30)).

## Evaluate with an external command

This complete **2.35** example evaluates an integer candidate with a small
stateless local scorer. It supplies no candidate generation or ranking policy.
Save these three files in one disposable workspace using the project Python
environment with `orchestrator` importable. No providers or extra dependencies
are required. `evaluate.orc` defines the typed boundary:

```lisp
(workflow-lisp
  (:language "0.1") (:target-dsl "2.35")
  (defmodule evaluate) (export run)
  (defworkflow run ((candidate Int)) -> Int
    (command-result score
      :argv ("python" "score.py" candidate)
      :returns Int)))
```

`commands.json` binds the authored site `score` to its executable and declares
its implementation file as the command closure:

```json
{
  "score": {
    "kind": "external_tool",
    "stable_command": ["python", "score.py"],
    "closure": ["score.py"]
  }
}
```

`score.py` receives the candidate through argv and writes the result to the
runtime-supplied bundle path; stdout is not the result channel:

```python
import json
import os
from pathlib import Path
import sys

candidate = int(sys.argv[1])
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
    json.dumps(candidate * candidate), encoding="utf-8"
)
```

From that workspace:

```bash
python -m orchestrator compile evaluate.orc --entry-workflow run \
  --command-boundaries-file commands.json
python -m orchestrator run evaluate.orc --entry-workflow run \
  --command-boundaries-file commands.json --input candidate=3 --dry-run
python -m orchestrator run evaluate.orc --entry-workflow run \
  --command-boundaries-file commands.json --input candidate=3
```

The result is `9`. Source input binding enforces `Int`; runtime result validation
checks the command's returned `Int` before commitment, including bounded integer
rules. Missing/malformed result files fail the effect. Compile/dry-run do not
read the scorer's closure bytes; execution pins them. Closure identity supplies
neither an OS sandbox nor proof of deterministic behavior. A new evaluator needs
an actual implementation and matching contract, not just a renamed call.
Typed interrupted runs use `python -m orchestrator resume RUN_ID`; completed
replay reuses committed results. Changing source or declared closure bytes
retains ordinary recovery refusals.

## Iterative search

The [native search consumer](../tests/fixtures/workflow_lisp/dynamic/search.orc)
is a complete target-3.0 controller: seed evaluation, branch alternation,
repair, fusion and a termination policy over the
[local leaves](../experiments/mlevolve_pair/leaves.py) and
[command manifest](../experiments/mlevolve_pair/commands_compact.json) of the
[paired-search specimen](../experiments/mlevolve_pair/README.md). The proposal
leaf is a deterministic fixture, not a live-model optimizer. Its
[staging and reproduction](lisp_workflow_drafting_guide.md#reproduce-the-complete-local-consumers)
supply the renamed type module, leaves and a manifest with closures; it
reproduces a ten-evaluation trace with no model credentials. The source path
alone cannot be launched from the CLI. The specimen's typed 2.33 controllers
(`search.orc`, `search_compact.orc`) are refused by the compiler at their
declared target.

The controller owns budget accounting and accepts only valid, strictly lower
scores; inspect the returned status/evaluation rather than assuming it solved
the task. The fixture search supplies no clone preparation, code mutation,
patch merging, arbitrary-expression sandbox, live model quality or production
throughput evidence. Different policies belong in application code.
