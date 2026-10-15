# Workflow Lisp Library Reference

Status: informative reference for current evaluated targets 2.35 and 2.36.
Use this page to choose a reusable API, an example workflow, or a composition
pattern for generating, evaluating, selecting and improving candidates. The
[drafting guide](lisp_workflow_drafting_guide.md) owns general authoring judgment;
[capability status](capability_status_matrix.md), the linked designs and
[normative CLI contract](../specs/cli.md) own availability and execution.

## Choose by task

| Task | Entry | Kind | Current availability |
| --- | --- | --- | --- |
| Generate independent code changes, then choose one | [Generate candidates and select](#generate-candidates-and-select) | Example workflow | Canonical 2.35 source; serial, bounded, manually prepared clones |
| Review and revise one typed candidate | [Review and revise with `std/improve`](#review-and-revise-with-stdimprove) | Library API | 2.35 explicit-input API; 2.36 local-hook API |
| Score a candidate with a deterministic executable | [Evaluate with an external command](#evaluate-with-an-external-command) | Composition pattern | Typed `command-result` with a declared command boundary at 2.35 |
| Search across candidates under an evaluation budget | [Iterative search](#iterative-search) | Example workflow | Maintained compact controller at 2.35; application-defined policy |
| Keep one conversation across review and revise | [`design_review_execute_agents.orc`](../workflows/examples/design_review_execute_agents.orc); [Agent sessions](lisp_workflow_drafting_guide.md#agent-sessions-target-238) | Example workflow | Implemented at 2.38; [deterministic and bounded adapter-smoke evidence](reports/2026-10-14-agent-sessions-pq1a-qualification.md) recorded; acceptance comparison pending |

These entries do different work. Selection compares alternatives; review/revise
changes a candidate; an evaluator supplies evidence; a search controller decides
what to propose next. There is no built-in generic candidate, fitness, population
or merge API. Choose the policy before composing the calls; the
[workflow design lessons](orc_workflow_design_lessons.md) explain the observed
tradeoffs and their evidence limits.

Run the commands below from the repository root unless the linked operating
recipe explicitly sets a candidate workspace. Compile/dry-run validates source,
bindings and inputs; it does not execute providers or certify declared command
bytes. Execution pins reached command implementations under the
[command adapter contract](design/workflow_command_adapter_contract.md#command-closure-declaration).

## Generate candidates and select

**Kind:** example workflow, not a stdlib best-of-N API.
**Availability:** the canonical
[`best_of_n.orc`](../experiments/orc_vs_single_call/workflows/best_of_n.orc)
targets evaluated execution 2.35. It implements candidates serially using
`list/map-effect` with a maximum of eight, then asks a judge to select one.

| Surface | Inputs | Output and behavior |
| --- | --- | --- |
| `best-of-n` | `task: String`, `intent: String`, `repos: List[String]` | `Selection`; calls `implement-one` for each repo, then the judge |
| `implement-one` | `task: String`, `repo: String` | `String` account from the coder's `Change` result |
| `select-only` | `intent: String`, ordered `repos: List[String]`, ordered `accounts: List[String]` | `Selection`; only the judge runs |
| `Selection` | Judge result | `winner: String`, `ranking: List[String]`, `report: SelectionReport` |

There are no procedure-reference hooks. The module defines both prompts,
records, report-path type and workflows. Deployment supplies
[`best_of_n.providers.json`](../experiments/orc_vs_single_call/workflows/best_of_n.providers.json):
`providers.coder` binds to `claude_unrestricted_workspace` and
`providers.judge` to `codex_unrestricted_workspace`. Those provider configurations
and CLIs must be available. The source's model and effort choices belong to this
example, rather than a library default. No external prompt or command manifest
is needed.

Complete canonical module:

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule best_of_n)
  (export best-of-n select-only)

  (defpath SelectionReport
    :kind relpath
    :under "artifacts/review"
    :must-exist true)

  (defrecord Change
    (summary String)
    (account String))

  (defrecord Selection
    (winner String)
    (ranking List[String])
    (report SelectionReport))

  (defprompt implement-prompt
    (:fills (task :text) (repo :text))
    -> Change
    "Work in the git repository at {repo} and nowhere else. Implement this change there:\n\n{task}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover.")

  (defprompt select-prompt
    (:fills (intent :text) (repos :value List[String]) (accounts :value List[String]))
    -> Selection
    "Several engineers independently wrote a fix for the same bug, each in their own copy of the repository. The copies are listed below, with each author's account in the same order. Choose the one to merge.\nIntended change: {intent}\nRepositories: {repos}\nAuthors' accounts: {accounts}\nIn each repository read the uncommitted changes and the code around them; change nothing in any repository and do not base your choice on test results or on how much was written. Rate every candidate 0, 1 or 2 on each of four criteria: (1) the root cause is fixed, not the symptom silenced; (2) no existing validation or guarantee is weakened and nothing changes outside the intended scope; (3) the change holds beyond the reported case; (4) it sits in the layer that owns the behaviour and reuses existing mechanisms instead of adding parallel ones.\nCompare the candidates with each other: where two differ, decide which is right by reading the code, and rate equal flaws equally.\nReport `winner`: the repository path of the best candidate, copied exactly from the list. `ranking`: every repository path, best first, each followed by a colon and its four ratings. Write your reasoning to a report file under artifacts/review/ in your current directory.")

  (defworkflow implement-one
    ((task String)
     (repo String))
    -> String
    (let* ((change (provider-result providers.coder
                     :prompt (implement-prompt :task task :repo repo)
                     :model "claude-sonnet-5-5"
                     :effort "medium"
                     :timeout-sec 5400)))
      change.account))

  (defworkflow best-of-n
    ((task String)
     (intent String)
     (repos List[String]))
    -> Selection
    (let* ((accounts (list/map-effect ((repo repos)) :max 8
                       (call implement-one :task task :repo repo)))
           (selection (provider-result providers.judge
                        :prompt (select-prompt :intent intent :repos repos :accounts accounts)
                        :model "gpt-6-sol"
                        :effort "high"
                        :timeout-sec 5400)))
      selection))

  (defworkflow select-only
    ((intent String)
     (repos List[String])
     (accounts List[String]))
    -> Selection
    (provider-result providers.judge
      :prompt (select-prompt :intent intent :repos repos :accounts accounts)
      :model "gpt-6-sol"
      :effort "high"
      :timeout-sec 5400))
)
```

### Operating route and limits

The caller prepares one independent clone per candidate from the same clean
baseline, and passes the clone paths in `repos`. The
[maintained operating recipe](../experiments/orc_vs_single_call/README.md#run-the-maintained-best-of-n-workflow)
shows clone preparation, typed JSON inputs, compile, dry-run, execution, resume
and report from the shared candidate working root. Its input task must describe
a real change in the chosen base repository; the shown `calc.py` task is an
illustration. For source/binding verification alone:

```bash
python -m orchestrator compile experiments/orc_vs_single_call/workflows/best_of_n.orc \
  --entry-workflow best_of_n::best-of-n \
  --source-root experiments/orc_vs_single_call/workflows \
  --provider-externs-file experiments/orc_vs_single_call/workflows/best_of_n.providers.json
```

`best-of-n` accepts a caller-supplied list, rather than a candidate count or
repository revision. Use a nonempty list of at most eight separate existing
clones. `select-only` needs one account per repo in the same order; the module
does not add an alignment check. The judge reads uncommitted changes and writes
a report under `artifacts/review` in the working root. The selection prompt
compares code and explicitly excludes test results from its ratings; add a
separate evaluator when tests or numerical evidence are required.

The result selects a repository; it does not merge, promote, reset or delete any
candidate. The winner and rankings are provider-produced strings, not a runtime
proof of membership or quality. Inspect the returned report and candidate before
applying a change. Clones prevent accidental shared edits but supply no OS
sandbox; these bindings run unrestricted provider tools. Do not infer parallel
execution or runtime-owned clone preparation from this example. The
[run-ref confinement design](design/workflow_lisp_run_ref_expression_environments.md)
has a separate implemented command-only surface; use the
[command-only recipe](lisp_workflow_drafting_guide.md#confined-workflow-children-target-238-command-only)
for its host/image prerequisites and limits. Confined provider admission and this
best-of-N consumer migration remain pending; this recipe still uses existing
unrestricted clones.

## Review and revise with `std/improve`

**Kind:** library API imported from `std/improve`.
**Availability:** admitted compositions at evaluated targets 2.35 and 2.36;
remaining composition and tooling limits are stated below.

`improve` takes a record candidate and typed review/revise procedure references.
A review returns `Decision[F B]`: `APPROVE` with evidence, `REVISE` with feedback,
or `BLOCKED` with a reason. A revise hook returns the next candidate. The helper
returns `Improvement[S F B]`: `APPROVED` (`value`, `evidence`), `BLOCKED` (`value`,
`reason`), or `EXHAUSTED` (`value`, possibly an unreviewed final revision).
`S` is the candidate record; `F` the feedback/evidence and `B` the blocker type.
Use the returned `value` downstream. Approval records the hook's assessment,
rather than proving substantive correctness.
[Composition-first §3](design/workflow_lisp_composition_first.md#3-interface)
owns outcome pairing and [§4](design/workflow_lisp_composition_first.md#4-loop-and-termination)
owns the round limit. One round reviews and, on `REVISE`, revises. The limit is
a compile-time integer constant of at least one, not a runtime workflow input.
Timeouts, malformed hook results, cancellation and provider failures keep their
runtime failure behavior; they do not become `EXHAUSTED`.

The entry target chooses one API for the entire **source import graph**:

| Entry target | Call | Hook signatures |
| --- | --- | --- |
| 2.35 | `(improve initial inputs review revise limit)` | `review(S I) -> Decision[F B]`; `revise(S I F) -> S` |
| 2.36 | `(improve initial review revise limit)` | `review(S) -> Decision[F B]`; `revise(S F) -> S` |

Every source importer sees that API, even with an older defining-module target.
Retargeting requires migrating five-argument source callers; compatible and
type-only imports remain legal. Complete imported snapshots retain producer
authority. The selected W3 helper still has source header 2.33. See
[write-once §9](design/workflow_lisp_write_once.md#9-targets-and-compatibility)
for old module identities, snapshot conflicts and resume guards.

W3 is implemented at 2.36; the [closeout](reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md) owns exact qualification and delivery evidence.
The following two source forms have bounded public compile/run and
committed-stop/resume/completed-replay evidence with deterministic provider
shims in `tests/test_workflow_evaluated_consumers.py`. This does not qualify
arbitrary compositions, package upgrades, all old checkpoints or evaluated LSP.

#### Target 2.36 local hooks

The maintained
[`improve_experiment_proposal.orc`](../workflows/examples/improve_experiment_proposal.orc)
uses inferred signatures and lexical captures. Its complete module follows
(source comments omitted). `propose` constructs the initial hypothesis and seed
parameter; review/revise use configured provider/prompt externs; `execute` hands
the returned proposal and outcome to the workspace's launcher. The entry takes
`question: String` and returns `ExperimentRun(status: String)`.
The [provider manifest](../workflows/examples/inputs/improve_experiment_proposal/providers.json)
binds both hooks to `codex`; the
[prompt manifest](../workflows/examples/inputs/improve_experiment_proposal/prompts.json)
resolves [review](../workflows/examples/prompts/workflows/improve_experiment_proposal/review.md) and
[revise](../workflows/examples/prompts/workflows/improve_experiment_proposal/revise.md). The
[command manifest](../workflows/examples/inputs/improve_experiment_proposal/commands.json)
binds the workspace-owned launcher described below.

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.36")
  (defmodule improve_experiment_proposal)
  (import std/improve :only (Decision improve))
  (export run-experiment)


  (defrecord Parameter (name String) (value Int))
  (defrecord ExperimentProposal
    (hypothesis String)
    (parameters List[Parameter]))
  (defrecord ExperimentBrief (question String))
  (defrecord ReviewNotes (notes String))
  (defrecord ReviewBlocker (issue String))
  (defrecord ExperimentRun (status String))

  (defproc propose ((brief ExperimentBrief)) -> ExperimentProposal
    :effects ()
    :lowering inline
    (record ExperimentProposal
      :hypothesis brief.question
      :parameters (list (record Parameter :name "seed" :value 0))))

  (defproc execute
    ((proposal ExperimentProposal) (outcome String) (note String))
    -> ExperimentRun
    :effects ((uses-command launch_experiment))
    :lowering inline
    (command-result launch_experiment
      :argv ("python" "scripts/launch_experiment.py"
             "--outcome" outcome
             "--note" note
             "--hypothesis" proposal.hypothesis
             "--parameters" proposal.parameters)
      :returns ExperimentRun))

  (defworkflow run-experiment ((question String)) -> ExperimentRun
    (let* ((brief (record ExperimentBrief :question question))
           (initial (propose brief)))
      (let-proc
        ((review-proposal
          (proposal)
          (provider-result providers.proposal.review
            :prompt prompts.proposal.review
            :inputs (brief.question proposal.hypothesis proposal.parameters)
            :returns Decision[ReviewNotes ReviewBlocker]))
         (revise-proposal
          (proposal review)
          (provider-result providers.proposal.revise
            :prompt prompts.proposal.revise
            :inputs (brief.question proposal.hypothesis proposal.parameters review.notes)
            :returns ExperimentProposal)))
        (let* ((result (improve initial
                                (proc-ref review-proposal)
                                (proc-ref revise-proposal)
                                3)))
          (match result
            ((APPROVED approved) (execute approved.value "approved" approved.evidence.notes))
            ((BLOCKED blocked) (execute blocked.value "blocked" blocked.reason.issue))
            ((EXHAUSTED exhausted) (execute exhausted.value "exhausted" ""))))))))
```

Both hooks capture the lexical `brief`; `ExperimentBrief` remains useful
domain data for proposal construction and prompt inputs. Declared provider
and prompt externs stay available in the local bodies and are not captures.
Actual lexical Provider/Prompt parameters or aliases keep their existing
admission limits; W3 adds no runtime capability transport.

`initial` fixes the candidate type; the review result fixes feedback/blocker
types and the revise parameter. Each incomplete local has exactly one authored
direct consumer call site, the `improve` call. Several arguments of that call
share the site; loop iterations do not add sites. Two authored calls, including
alternative branches, need full signatures or distinct locals. Aliases,
`bind-proc` and returned/conditional ProcRefs do not carry an outer call's
expectation into an incomplete local. Full annotations preserve ordinary
reuse. Sibling/self calls, nested local definitions and recursion remain
outside W3; captures keep creator binding identity under later shadowing.

The complete
[reviewed-change fixture](../tests/fixtures/workflow_lisp/w3_consumers/reviewed_change.orc)
shows fully typed local hooks with lexical `repo`/`intent` for review and `task`
for revision. It preserves domain reports, `ReviewState`, request lineage and
READY/ESCALATED/UNRESOLVED outcomes. Both REQUEST_CHANGES and WRONG_APPROACH
become BLOCKED on round three, so no fourth candidate is produced. Consult the
whole fixture for those guards rather than copying a truncated hook body.
The separate canonical
[`reviewed_change.orc`](../experiments/orc_vs_single_call/workflows/reviewed_change.orc)
now targets 2.35 and uses its own hand-written loop; it is not this W3 consumer.

#### Compile, run and resume the maintained proposal

Run from the repository root. The provider/prompt manifests resolve declared
externs; the command manifest supplies the required `closure` declaration.
Compilation validates that declaration without reading the launcher's bytes;
dry-run also binds the typed inputs and does not certify command bytes.
The input file supplies `question`. Compilation uses the maintained entry
at 2.36 without rewriting its source:

```bash
python -m orchestrator compile workflows/examples/improve_experiment_proposal.orc \
  --entry-workflow improve_experiment_proposal::run-experiment \
  --provider-externs-file workflows/examples/inputs/improve_experiment_proposal/providers.json \
  --prompt-externs-file workflows/examples/inputs/improve_experiment_proposal/prompts.json \
  --command-boundaries-file workflows/examples/inputs/improve_experiment_proposal/commands.json
```

Dry-run with its typed inputs:

```bash
python -m orchestrator run workflows/examples/improve_experiment_proposal.orc \
  --entry-workflow improve_experiment_proposal::run-experiment \
  --provider-externs-file workflows/examples/inputs/improve_experiment_proposal/providers.json \
  --prompt-externs-file workflows/examples/inputs/improve_experiment_proposal/prompts.json \
  --command-boundaries-file workflows/examples/inputs/improve_experiment_proposal/commands.json \
  --input-file workflows/examples/inputs/improve_experiment_proposal/inputs.json \
  --dry-run
```

For execution, supply the configured providers and remove `--dry-run`.
The workspace must contain `scripts/launch_experiment.py`; the command
manifest declares it in `closure`, so its bytes participate in the pin.
The launcher receives `--outcome`, `--note`, `--hypothesis` and `--parameters`
(JSON), and writes `{"status": ...}` to `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
It receives the helper's returned proposal in every outcome, with an empty
note on `EXHAUSTED`; this script is workspace-owned, not supplied by the example.

After an interrupted run, replace `RUN_ID` with the recorded run ID from that
same workspace. The second command replays the completed run:

```bash
python -m orchestrator resume RUN_ID
python -m orchestrator resume RUN_ID
```

The public fixture harness stops after a committed effect, resumes its memo
prefix to completion and then replays the completed run without new dispatch
or byte changes. That interruption is controlled by the test harness. Source,
package or declared closure changes retain existing resume refusals; migrating
or retargeting an old source does not promise compatible resume. The
[evaluated lifecycle recipe](lisp_workflow_drafting_guide.md#a-complete-235-recipe-compile-run-resume-report-invalidate)
and [CLI contract](../specs/cli.md#evaluated-execution-target-235) own operator
behavior for both evaluated targets.

#### Target 2.35 explicit inputs

At 2.35 use the five-argument form with explicit domain inputs and complete
hook signatures. The preserved
[`improve_legacy/improve_experiment_proposal.orc`](../tests/fixtures/workflow_lisp/improve_legacy/improve_experiment_proposal.orc)
has source header 2.33 and is a complete explicit-input source specimen. Its
entry is retired when launched unchanged; use it to inspect the API, or retarget
an isolated copy to 2.35 before compiling/running with the same proposal
manifests and launcher contract above. Its name does not make the five-argument
API unsupported at 2.35. For bounded evaluated consumer evidence and remaining
composition limits, see
[composition-first §11.4](design/workflow_lisp_composition_first.md#114-evaluated-w3-boundaries).

#### `improve` rejections

The [W3 contract](design/workflow_lisp_write_once.md#63-language-changes-to-let-proc)
owns incomplete-local restrictions; the
[evaluated composition boundary](design/workflow_lisp_composition_first.md#114-evaluated-w3-boundaries)
owns the remaining OPEN pure-helper, combined-capture and relay cases.
Independent successful compositions do not close those fixtures. Retargeting
a five-argument caller to 2.36 requires migration to its four-argument API;
it does not promise compatible resume of an older run.


## Evaluate with an external command

**Kind:** composition pattern using `command-result`, not a built-in evaluator.
**Availability:** typed certified adapters are admitted at evaluated target
2.35. The existing
[`commands_compact.json`](../experiments/mlevolve_pair/commands_compact.json)
and [`leaves.py`](../experiments/mlevolve_pair/leaves.py) supply this evaluator.
No provider or prompt is involved.

The candidate is an application-defined record with integer coefficients `a`
and `b`. The evaluator scores `a*x + b*x*x` against `2*x + 3*x*x` at
`x = [-2, -1, 1, 2]`. It returns
`Evaluation(valid: Bool, score: Float, error: String)`; lower scores are better.
Coefficients outside `[-5, 5]` produce `valid=false`, `score=0.0` and
`error="coefficient_out_of_domain"`. Check validity before comparing scores.

Here is a complete standalone module. Save it as
`experiments/mlevolve_pair/evaluate_one.orc` to use the commands below. It uses
its own module identity, matching its file under the `experiments` source
root. The two type definitions have the same fields as the maintained controller.
All candidate values come from the two typed workflow inputs, and the evaluator
binding comes from the command manifest below.

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule mlevolve_pair/evaluate_one)
  (export evaluate-one)

  (defrecord Candidate (a Int) (b Int))
  (defrecord Evaluation (valid Bool) (score Float) (error String))

  (defworkflow evaluate-one ((a Int) (b Int)) -> Evaluation
    (let* ((candidate (record Candidate :a a :b b))
           (evaluation (command-result evaluate-one-candidate
                         :adapter evaluate_candidate
                         :inputs ((a candidate.a) (b candidate.b))
                         :returns Evaluation)))
      evaluation)))
```

### Manifest, executable and typed-result lineage

Save the complete JSON below as
`experiments/mlevolve_pair/commands_evaluate_one.json`. It uses the maintained
evaluator contract and executable, with only `owner_module` changed to match
this standalone module. The stock `commands_compact.json` owns the search
module and cannot be passed unchanged to this alternate source.

```json
{
  "evaluate_candidate": {
    "kind": "certified_adapter",
    "stable_command": [
      "python",
      "experiments/mlevolve_pair/leaves.py",
      "evaluate"
    ],
    "input_contract": {
      "type": "object"
    },
    "output_type_name": "Evaluation",
    "effects": [
      "structured_result"
    ],
    "path_safety": {
      "kind": "workspace_relpath"
    },
    "source_map_behavior": "step",
    "fixture_ids": [
      "mlevolve_pair_score"
    ],
    "negative_fixture_ids": [
      "mlevolve_pair_score_invalid"
    ],
    "behavior_class": "structured_result",
    "input_signature": [
      {
        "name": "a",
        "type_name": "Int",
        "required": true,
        "transport_key": "a"
      },
      {
        "name": "b",
        "type_name": "Int",
        "required": true,
        "transport_key": "b"
      }
    ],
    "artifact_contracts": [
      "mlevolve_evaluation_bundle"
    ],
    "state_writes": [],
    "error_codes": [
      "mlevolve_candidate_invalid"
    ],
    "owner_module": "mlevolve_pair/evaluate_one",
    "replacement_path": null,
    "invocation_protocol": "json_object_positional_arg",
    "closure": [
      "experiments/mlevolve_pair/leaves.py"
    ]
  }
}
```

1. `:adapter evaluate_candidate` resolves this manifest row. Its signature maps
   `a` and `b` to the same JSON keys, and `owner_module` matches the module above.
   `evaluate-one-candidate` names the authored effect site; it is not the
   executable or an evaluator implementation.
2. `stable_command` invokes `python experiments/mlevolve_pair/leaves.py evaluate`;
   the certified-adapter protocol appends the JSON object as a positional
   argument. In `leaves.py`, `main` parses it and calls `evaluate(**request)`.
   That function implements integer/domain validation and the sum of squared
   errors. The declared closure includes this implementation file.
3. `main` writes the result JSON to `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, supplied
   by the runtime. Standard output is not this result channel. The manifest's
   `output_type_name` and the source's `:returns Evaluation` agree; runtime
   validation commits the typed result for the `evaluation` binding. A missing
   or malformed bundle fails the effect, rather than producing an invalid
   domain evaluation.

`fixture_ids`, negative fixtures, artifact contracts and error-code metadata
record the adapter contract; they do not run tests or magically implement the
score. The executable bytes and the source type contract supply the actual
behavior. The
[command adapter contract](design/workflow_command_adapter_contract.md) and
[evaluated IO contract](../specs/io.md#evaluated-command-and-provider-io-target-235)
own boundary validation, closure identity and result delivery.

### Operating route and limits

Use the project Python environment and run from the repository root so the
relative script and closure paths resolve. No candidate file, evaluator install,
provider executable or additional script is required beyond the maintained
Python leaf:

```bash
python -m orchestrator compile experiments/mlevolve_pair/evaluate_one.orc \
  --entry-workflow evaluate-one --source-root experiments \
  --command-boundaries-file experiments/mlevolve_pair/commands_evaluate_one.json
python -m orchestrator run experiments/mlevolve_pair/evaluate_one.orc \
  --entry-workflow evaluate-one --source-root experiments \
  --command-boundaries-file experiments/mlevolve_pair/commands_evaluate_one.json \
  --input a=2 --input b=3
```

This returns the valid zero-score evaluation. Add `--dry-run` to the run command
to validate the typed invocation without launching the leaf. Use
`python -m orchestrator resume RUN_ID` after interruption and
`python -m orchestrator report --run-id RUN_ID --format json` to inspect the
result, substituting the recorded ID. Normal command recovery reuses committed
results and may retry an uncommitted attempt; this evaluator is stateless.

The adapter does not generate candidates, rank a population or implement a
stopping rule. Its declared input signature transports scalars, not an arbitrary
candidate object. A new evaluator needs its own executable and accurate typed
manifest; renaming this call alone does not supply either. Closure pinning is
not an OS sandbox or a proof of deterministic behavior. The numerical fixture
is not a sealed benchmark or evidence of live model quality.

## Iterative search

**Kind:** example workflow with application-defined search policy.
**Availability:** the maintained
[`search_compact.orc`](../experiments/mlevolve_pair/search_compact.orc) targets
2.35 and is the complete runnable source for this entry. It defines every type,
`result`, `branch-step`, seed and controller expression; use the whole module.
The older [`search.orc`](../experiments/mlevolve_pair/search.orc) is historical
policy evidence whose old-target entry is retired.

| Surface | Actual contract |
| --- | --- |
| `run-search` | `max_evaluations: Int = 12`, `target_score: Float = 0.0` → `SearchResult` |
| `Candidate` | Integer coefficients `a`, `b`, defined in the module |
| `Evaluation` | `valid`, `score`, `error`; same evaluator as the preceding entry |
| `Trial` | Action, branch, parents, candidate, evaluation and acceptance |
| `SearchState` | A/B incumbents and evaluations, best result, history, counters, pending repair and fusion flag |
| `SearchResult` | Candidate, evaluation, evaluations used, status and typed trial trace |
| Proposal leaf | `operation`, `branch`, `candidate_a/b`, `other_a/b`, `history_size` → `Candidate` |
| Evaluation leaf | `a`, `b` → `Evaluation` |

There are no ProcRef hooks. The dependency is
[`commands_compact.json`](../experiments/mlevolve_pair/commands_compact.json),
which binds `propose_candidate` and `evaluate_candidate` to separate operations
of [`leaves.py`](../experiments/mlevolve_pair/leaves.py). Both rows declare that
file as closure and match the controller's module owner. No provider/prompt
manifest or live model is needed. Proposal is a deterministic test fixture;
changing it is a domain implementation change, not a generic library setting.

### Candidate dataflow and policy

`branch-step` binds `current` to A or B's incumbent and `other` to the opposite
incumbent. `base` is the pending invalid candidate for a repair, otherwise
`current`. `candidate` is the proposal adapter's returned record. These names
are ordinary lexical bindings in this module, not language primitives or values
supplied invisibly by the runtime. `candidate_a/b` and `other_a/b` are scalar
manifest input keys derived from those records. Fusion explicitly passes A's
incumbent as the first candidate and B's as the other.

The controller evaluates both seeds, alternates branches and replaces an
incumbent only for a valid, strictly lower score. Invalid branch proposals schedule
one repair of that candidate/branch; an invalid repair is not retried. Ties and
invalid branch evaluations increment that branch's stall count. When both branches stall twice,
one fusion is attempted; the fixture combines A's `a` with B's `b`. The workflow
owns routing and acceptance, while the leaf only executes the requested
operation. History stays typed in the controller; the proposal receives only
its length (`history_size`), not the whole trace.

### Operating route and limits

Use the [maintained reproduction route](../experiments/mlevolve_pair/README.md)
for the policy and fixture explanation. Compile and execute from the repository
root:

```bash
python -m orchestrator compile experiments/mlevolve_pair/search_compact.orc \
  --entry-workflow run-search --source-root experiments \
  --command-boundaries-file experiments/mlevolve_pair/commands_compact.json
python -m orchestrator run experiments/mlevolve_pair/search_compact.orc \
  --entry-workflow run-search --source-root experiments \
  --command-boundaries-file experiments/mlevolve_pair/commands_compact.json \
  --input max_evaluations=12 --input target_score=0.0
```

Add `--dry-run` for input/admission validation. Resume with the recorded run ID
and inspect the typed result using the same resume/report route as the external
evaluator. Seeds, repair and fusion all count against the evaluation budget.
Valid budgets are integers from two through sixteen; invalid budgets return
`invalid_budget` with zero evaluations. The serial loop also has a safety bound
of sixteen. Terminal statuses are `solved`, `budget_exhausted`,
`loop_bound_exhausted` and `invalid_budget`; a returned candidate may be unsolved,
so read its evaluation and status.

The comparison with Python and interrupted/completed resume uses scripted
leaves. It does not establish live-provider search quality, model cost, GPU
throughput or production behavior, and Python has no equivalent durable
recovery implementation in this specimen. This numerical controller does not
manage clones, mutate code, merge patches or create an OS sandbox. Use the
preceding generation/selection example for manually prepared code workspaces, or
the [confined command-only recipe](lisp_workflow_drafting_guide.md#confined-workflow-children-target-238-command-only)
for runtime-owned command workspaces. Confined providers and the complete
generation/selection migration remain pending qualification.
