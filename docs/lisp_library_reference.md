# Workflow Lisp Library Reference

Status: informative reference, with availability stated per execution profile.
Use this page to choose a reusable helper or complete example. The
[drafting guide](lisp_workflow_drafting_guide.md) owns authoring judgment;
[capability status](capability_status_matrix.md), linked designs and
[normative versioning](../specs/versioning.md) own availability. Existing
application sources retain their declared targets; a newer runtime does not
retarget an imported example automatically.

## Choose by task

| Task | Entry | Kind and prerequisites |
| --- | --- | --- |
| Generate independent code changes and choose one | [Generate candidates and select](#generate-candidates-and-select) | Serial target-2.35 example; caller prepares candidate repositories and provider bindings |
| Review and revise one candidate | [Review and revise](#review-and-revise) | Typed `std/improve` or native `std/dynamic/improve`; caller supplies hooks and domain data |
| Obtain a deterministic score | [Evaluate with an external command](#evaluate-with-an-external-command) | Complete target-2.35 command example, executable and manifest |
| Search under an evaluation budget | [Iterative search](#iterative-search) | Application-defined controller and local leaves, with explicitly selected target |
| Inspect a loaded module or run | [REPL guide](lisp_workflow_drafting_guide.md#inspect-a-run-with-the-workflow-lisp-repl) | Typed 2.35/2.36 or qualified native 3.0; declaration inspection does not run effects |

Selection compares alternatives; revision changes one candidate; evaluation
supplies evidence; a controller chooses what to propose next. No generic
candidate, fitness, population or merge API is supplied. The
[design lessons](orc_workflow_design_lessons.md) explain the evidence for choosing
between these patterns.

Compile and dry-run validate source, bindings and inputs without launching
providers or commands. They do not certify executable bytes. Reached execution
pins declared command closures under the
[command adapter contract](design/workflow_command_adapter_contract.md#command-closure-declaration).

## Generate candidates and select

**Kind:** example workflow. The complete maintained
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
check. It does not create clones, install environments or sandbox provider tools.
There is no current primitive for preparing repositories or running arbitrary
expressions in isolated environments. Generalized run-reference/OCI expression
environments remain proposed, not an available authoring route.

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

The [maintained operating recipe](../experiments/orc_vs_single_call/README.md#run-the-maintained-best-of-n-workflow)
provides clone preparation, complete JSON inputs and compile/dry-run/run/resume
commands from the prepared candidate working root. It is the complete launch
route; the frozen experiment measurements describe their original sources.
Candidates execute in order, not in parallel, and there are no ProcRef hooks.

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
| Typed 2.36 W3 | `std/improve`; `(improve initial review revise limit)` | `review(S) -> Decision[F B]`; `revise(S F) -> S`; local hooks may capture context; same typed round limit |
| Qualified native 3.0 | `std/dynamic/improve`; `(improve initial review revise limit)` | Ordinary functions/captures; declared boundary schemas; positive runtime limit and entry operation budget |

The typed entry target selects **one API for the whole source import graph**.
Retargeting to 2.36 requires migrating five-argument source callers, including
indirect dependencies; compatible and type-only older modules remain legal.
Complete compiled snapshots retain producer authority. W3's helper source still
has header 2.33. See [write-once §9](design/workflow_lisp_write_once.md#9-targets-and-compatibility)
for identity and resume guards. Native imports old domain declarations, not the
typed helper executable body; its four-argument helper is a separate real module.

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
An incomplete W3 local needs exactly one authored direct consumer call site;
full signatures permit reuse. Sibling/self calls, nested locals and recursion
remain excluded. See the [W3 contract](design/workflow_lisp_write_once.md#63-language-changes-to-let-proc).

The complete [experiment-proposal application](../workflows/examples/improve_experiment_proposal.orc)
retains **2.33**, explicit top-level hooks and five arguments. Its
[drafting recipe](lisp_workflow_drafting_guide.md#137-improve) lists actual
provider/prompt manifests and workspace-owned launcher requirements; it is not
a maintained 2.36 application. The pure examples above do not establish its
live-provider quality or compatibility after retargeting.

### Native consumer and prerequisites

The complete [native consumer](../tests/fixtures/workflow_lisp/dynamic/improve.orc)
imports the actual [std/dynamic/improve](../orchestrator/workflow_lisp/stdlib_modules/std/dynamic/improve.orc)
and passes captured review/revise functions. The
[complete consumer and setup](lisp_workflow_drafting_guide.md#complete-imported-improvement-consumer)
explain the staged `dynamic_consumer/improve.orc`, renamed `types.orc`, probe
scripts, command manifest, event-log environment and public smoke. A fixture
path alone is not a standalone CLI launch. Workflow and command results retain
strict declared schemas; internal functions have no inferred signatures.

Native 3.0 is branch-qualified and fresh-only: no resume, invalidation or result
reuse. A corrected fresh run may repeat previous calls and writes. Agent
orchestration forms, parallel/child/trial/resource/view/host-input effects and
provider sessions/context/phased/live surfaces remain unavailable. Ordinary
portable composed-provider and command effects are sequential. This reference
does not select adoption or change the default target.

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

The complete maintained [search_compact.orc](../experiments/mlevolve_pair/search_compact.orc)
retains **2.33**. It defines Candidate/Evaluation/Trial/SearchState/SearchResult,
seed evaluation, branch alternation, repair, fusion and termination policy. Its
[reproduction guide](../experiments/mlevolve_pair/README.md) supplies the actual
[command manifest](../experiments/mlevolve_pair/commands_compact.json) and
[local leaves](../experiments/mlevolve_pair/leaves.py); the proposal leaf is a
deterministic fixture, not a live-model optimizer. Do not pass this source to
the typed 2.35 runtime by implication or treat historical measurements as
qualification of a different target.

The [native search consumer](../tests/fixtures/workflow_lisp/dynamic/search.orc)
is a complete target-3.0 controller. Its
[staging and public reproduction](lisp_workflow_drafting_guide.md#reproduce-the-complete-local-consumers)
supply the renamed type module, leaves and accurate closure-bearing manifest.
It reproduces a ten-evaluation trace with no model credentials. A source path
without that setup is not a standalone launch.

The controller owns budget accounting and accepts only valid, strictly lower
scores; inspect the returned status/evaluation rather than assuming it solved
the task. The fixture search supplies no clone preparation, code mutation,
patch merging, arbitrary-expression sandbox, live model quality or production
throughput evidence. Different policies belong in application code.
