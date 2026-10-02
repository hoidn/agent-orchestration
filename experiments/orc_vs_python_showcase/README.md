# One program, in ORC and in Python

A showcase with a condition. ORC is more concise, more reusable and easier to
read than Python **for a program made of a few expensive, non-deterministic
agent calls joined by deterministic routing, when the Python must give the same
guarantees**: every answer checked against its declared shape, no paid call
repeated after a crash, no stale answer accepted, the run inspectable on disk.
Against Python that gives none of those guarantees, ORC is longer. Against a
controller that is mostly computation, Python wins today; see
[Where Python wins](#where-python-wins).

Everything below was run on 2026-10-02 at `main` (`e0fd904b`). The commands
are in [Evidence](#evidence).

## The program

Draft an experiment proposal from a research question; have an agent review
it; when the review asks for changes, have an agent revise it; stop at an
approval, a block, or after three reviews; hand the result to the workspace's
launcher with the outcome. The shipped example
[`workflows/examples/improve_experiment_proposal.orc`](../../workflows/examples/improve_experiment_proposal.orc)
is exactly this program.

## Listing 1: ORC, 60 lines

The workflow without its header comment. The review loop is not written here:
it is `std/improve::improve`, a 37-line library procedure, generic over the
value, the inputs, the evidence and the block types.

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
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

  (defproc review-proposal
    ((proposal ExperimentProposal) (brief ExperimentBrief))
    -> Decision[ReviewNotes ReviewBlocker]
    :effects ((uses-provider providers.proposal.review))
    :lowering inline
    (provider-result providers.proposal.review
      :prompt prompts.proposal.review
      :inputs (brief.question proposal.hypothesis proposal.parameters)
      :returns Decision[ReviewNotes ReviewBlocker]))

  (defproc revise-proposal
    ((proposal ExperimentProposal) (brief ExperimentBrief) (review ReviewNotes))
    -> ExperimentProposal
    :effects ((uses-provider providers.proposal.revise))
    :lowering inline
    (provider-result providers.proposal.revise
      :prompt prompts.proposal.revise
      :inputs (brief.question proposal.hypothesis proposal.parameters review.notes)
      :returns ExperimentProposal))

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
           (result (improve (propose brief) brief
                            (proc-ref review-proposal)
                            (proc-ref revise-proposal)
                            3)))
      (match result
        ((APPROVED approved) (execute approved.value "approved" approved.evidence.notes))
        ((BLOCKED blocked) (execute blocked.value "blocked" blocked.reason.issue))
        ((EXHAUSTED exhausted) (execute exhausted.value "exhausted" ""))))))
```

Beside it, 17 lines of JSON bind the two provider names, the two prompt files
and the launcher command
([`workflows/examples/inputs/improve_experiment_proposal/`](../../workflows/examples/inputs/improve_experiment_proposal/)).
The two prompts are shared with the Python versions.

What the reader holds in mind: the types, the three hooks, the policy. What
the runtime supplies without a line here: each answer is parsed and checked
against `Decision[ReviewNotes ReviewBlocker]` or `ExperimentProposal`, a
mismatch failing the step with a JSON pointer and the source location; each
hook call is committed once and a resume (`orchestrator resume <run>`) never
repeats a committed call; an answer file must come from the call that claims
it; the run directory holds the state with every step's result, the
checkpoints, the typed inputs of every prompt, the provider observations and
the call frames, so `orchestrator status` and `resume` work from disk; the
launcher's result file is confined to the workspace; and the whole program is
checked before the first agent runs.

## Listing 2: the obvious Python, 33 lines

[`improve_naive.py`](improve_naive.py). Shorter than the workflow, and a
different program: an answer is trusted as it comes; a crash after the second
agent call repeats both calls on the next run; nothing records which answer
led to which decision; a typo in a dictionary key of the third step is found
after the two agents before it have been paid for.

```python
def run(question):
    proposal = {"hypothesis": question, "parameters": [{"name": "seed", "value": 0}]}
    outcome, note = "exhausted", ""
    for _ in range(3):
        decision = ask("review.md", question=question, **proposal)
        if decision["kind"] == "APPROVE":
            outcome, note = "approved", decision["evidence"]["notes"]
            break
        if decision["kind"] == "BLOCKED":
            outcome, note = "blocked", decision["reason"]["issue"]
            break
        proposal = ask("revise.md", question=question, **proposal, notes=decision["feedback"]["notes"])
    subprocess.run(["python", "scripts/launch_experiment.py", "--outcome", outcome, ...], check=True)
```

## Listing 3: Python with the same guarantees, 118 lines

[`improve_equivalent.py`](improve_equivalent.py). It builds by hand what the
workflow gets from the runtime: shape declarations and a `check` that names
the JSON pointer of a mismatch (31 lines); a `Run` whose append-only journal
commits each effect once and replays committed effects on resume, with a
torn last line treated as uncommitted (25 lines); an `ask` that deletes the
answer file before the call so an old answer cannot pass for a new one (10
lines); `run`/`resume` entry points (13 lines). The policy itself, `improve`
and `run_experiment`, is 14 lines, the same size as in Listing 2.

It still lacks what cannot be bolted on afterwards: no check of the whole
program before the first agent is paid (a typo in `revise_proposal` surfaces
after the review has run); no lineage view; no confinement of the launcher;
and its journal identifies an effect by its ordinal, which is sound only
while control flow depends on nothing but committed answers. A reviewer who
lets the two panel reviewers below run concurrently breaks resume silently.

[`selfcheck.py`](selfcheck.py) proves the three guarantees it does give:
a crash after the second committed effect and a resume make three agent
calls in all, not five; an answer with `notes: 7` is refused at
`/evidence/notes: expected str`; a call that writes no answer is refused
rather than served the previous answer.

## The comparison

| | ORC (Listing 1) | Python, obvious (2) | Python, same guarantees (3) |
| --- | ---: | ---: | ---: |
| Lines of code (no blanks, comments, docstrings) | 60 + 17 JSON | 33 | 118 |
| Lines that state the policy | 10 (`run-experiment`) | 13 (`run`) | 14 (`improve`, `run_experiment`) |
| Answer shape checked, mismatch located | yes, from `:returns` | no | yes, 30 lines |
| Resume repeats no committed call | yes | no | yes, 30 lines, by convention |
| Stale answer refused | yes | no | yes |
| Program checked before the first agent runs | yes, `--dry-run`, 1.5 s | no | no |
| `match` must cover every outcome | compile error | no | no |
| Run inspectable on disk: state, checkpoints, typed prompt inputs, provider observations | yes | no | journal only |

Concision: ORC beats the Python that matches its guarantees (77 lines against
118, with the policy the same size) and loses to the Python that does not (77
against 33). The 44 lines the ORC spends over the obvious Python are its type
declarations (8), the `:effects`/`:lowering` ceremony on four procedures (8),
the extern bindings (17) and the generic hook signatures; they are the price
of the compile-time checks in the table.

## Reuse: a second reviewer and a panel

The example's own test suite substitutes the reviewer with a panel: a second
reviewer and an adjudication in which the stricter verdict wins, so an inner
block is never downgraded. These 25 lines are added and `(proc-ref
review-proposal)` becomes `(proc-ref review-by-panel)`; nothing else changes.

```lisp
  (defproc review-statistics
    ((proposal ExperimentProposal) (brief ExperimentBrief))
    -> Decision[ReviewNotes ReviewBlocker]
    :effects ((uses-provider providers.proposal.statistics-review))
    :lowering inline
    (provider-result providers.proposal.statistics-review
      :prompt prompts.proposal.review
      :inputs (brief.question proposal.hypothesis proposal.parameters)
      :returns Decision[ReviewNotes ReviewBlocker]))
  (defproc review-by-panel
    ((proposal ExperimentProposal) (brief ExperimentBrief))
    -> Decision[ReviewNotes ReviewBlocker]
    :effects ((uses-provider providers.proposal.review)
              (uses-provider providers.proposal.statistics-review))
    :lowering inline
    (let* ((methods (review-proposal proposal brief))
           (statistics (review-statistics proposal brief)))
      (match methods
        ((BLOCKED blocked) methods)
        ((REVISE revise)
         (match statistics
           ((BLOCKED blocked) statistics)
           ((REVISE other) methods)
           ((APPROVE approve) methods)))
        ((APPROVE approve) statistics))))
```

The compiler checks that the panel returns the `Decision` the loop expects
and declares both providers it uses; the loop, the checkpoints inside it and
the resume behaviour are unchanged, which
`test_panel_reviewer_substitution_changes_only_the_selected_hook` and
`test_panel_returns_an_inner_block_never_a_downgraded_verdict` pin. In Python
the panel is ten lines and as readable; what Python cannot check is that it
kept the journal discipline, and its journal, which names an effect by its
prompt file, records both reviews as `review.md` and no longer says which
reviewer's verdict won.

Reuse runs the other way too: `std/improve::improve` drives any
review-revise loop over any record type with any pair of hooks, and the
checkpoints inside it belong to the library, not to each caller. A Python
`improve()` is as generic over values; it is generic over effects only if
every caller threads the journal through every hook, by hand, forever.

## Readability

Listing 1 reads top-down as the policy: the types, the three hooks, the loop
call, the three outcomes. The reader does not need to know how an answer is
validated, committed or resumed, because none of that is in the file.
Listing 3 is two thirds plumbing, and the plumbing is where the bugs live:
the stale-answer check, the torn journal line, the ordinal identity. Listing
2 is the most readable of the three and the least truthful about what happens
when something goes wrong.

## Evidence

Dry run of the shipped example, state under a scratch directory (exit 0,
1.5 s; the lint warnings are about generated boundary names):

```bash
python -m orchestrator run workflows/examples/improve_experiment_proposal.orc \
  --entry-workflow improve_experiment_proposal::run-experiment \
  --provider-externs-file workflows/examples/inputs/improve_experiment_proposal/providers.json \
  --prompt-externs-file workflows/examples/inputs/improve_experiment_proposal/prompts.json \
  --command-boundaries-file workflows/examples/inputs/improve_experiment_proposal/commands.json \
  --input-file workflows/examples/inputs/improve_experiment_proposal/inputs.json \
  --state-dir /tmp/showcase-state --dry-run
```

Two copies of the example, each broken in one place, refused by the same
command before any agent runs (exit 2):

| Change | Refusal |
| --- | --- |
| The `EXHAUSTED` arm removed from `match` | `improve_experiment_proposal.orc:76:7: [union_match_non_exhaustive] match must cover every variant of std/improve::Improvement[ExperimentProposal ReviewNotes ReviewBlocker]; missing EXHAUSTED` |
| `review.notes` misspelt `review.note` in `revise-proposal` | `improve_experiment_proposal.orc:53:71: [record_field_unknown] unknown field note` |

The example's end-to-end module, run alone
(`pytest -q -p no:cacheprovider tests/test_workflow_lisp_improve_example_e2e.py`):
11 passed in 9.5 s, among them
`test_resume_reaches_the_same_consumer_without_repeating_provider_work`
(interrupted after the committed review, and after the committed revision:
on resume the agent calls are the same three, the launcher runs once) and
`test_resume_after_the_final_continue_projects_the_latest_proposal`.

The Python self-check (`python -m experiments.orc_vs_python_showcase.selfcheck`):
`selfcheck: ok (resume repeats no call; malformed and missing answers refused)`.

## Where Python wins

The claim holds for programs whose substance is a handful of effects. It
fails for controllers whose substance is computation.
[The MLEvolve comparison](../../docs/reports/2026-09-29-mlevolve-orc-python-comparison.md)
wrote the same two-branch search policy in both languages: the Python
controller is 128 lines and runs; the ORC controller is 239 lines and does not
compile, because its explicit control flow produces a 361-node pure expression
against a limit of 256, after rejections of record-valued command arguments
and of effectful calls in several expression positions. (That report also
found a repeated command boundary consuming the previous iteration's result
file. At today's `main` its retained probe,
`experiments/mlevolve_pair/probes/missing_bundle.orc`, fails the second
iteration with `contract_violation` / `missing_bundle_file`, "Expected output
bundle file was not created": that defect is repaired.)

Smaller costs visible in this showcase: a third broken copy, passing the whole
proposal where the launcher wants a string, is refused with
`workflow_return_not_exportable: Stage 3 lowering requires command argv values
to resolve to literals or workflow inputs`, a true refusal in the compiler's
words rather than the author's; the dry run prints twelve lint warnings about
names the author never wrote; a `Float` literal cannot yet be written in an
expression at this target; and the totality matrix at target 2.33 records 82
form-and-position cells the present route still gets wrong.

So the honest statement is conditional. When the program is agent calls and
routing, and the guarantees matter, the workflow is the shorter, more
reusable and more readable of the two equivalent programs. When the program
is a search over rich state, write it in Python and keep the agent calls at a
boundary.
