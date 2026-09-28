# `.orc` Workflows Versus A Single Agent Call

- **Status:** exploratory evidence. One task, six runs per configuration, model judges.
- **Date:** 2026-09-28
- **Files:** [`experiments/orc_vs_single_call/`](../../experiments/orc_vs_single_call/README.md)
- **Guidance drawn from it:** [Designing `.orc` Workflows That Beat A Single Call](../orc_workflow_design_lessons.md)

## Summary

Two `.orc` workflows produced better code than one agent call given the same
task. Both put a stronger model, from another family, in the judging role.
Three review loops that used the author's own model as reviewer did not.

| Workflow | Judge inside the workflow | Single call | Workflow | Change |
| --- | --- | --- | --- | --- |
| Generate four, select one (confirmation run) | `gpt-6-sol` | 6.42 | 7.25 | +0.83 |
| Generate four, select one (first run) | `gpt-6-sol` | 5.65 | 6.67 | +1.02 |
| Generate four, select one (first run) | Sonnet, the authors' model | 5.65 | 6.08 | +0.44 |
| Review and revise, redesigned | `gpt-6-sol` | 4.83 | 5.42 | +0.58 |
| Review and revise, redesigned | Sonnet, the author's model | 5.9 | 5.9 | 0 |
| Review and revise, quality prompt, three rounds | Sonnet, the author's model | 6.5 | 6.0 | -0.5 |
| Review and revise, generic prompt | `gpt-5.5`, the author's model | 2 of 4 complete | same | 0 |

Scores are the mean of two blind judges, out of 8. They are comparable within
a row only: each batch had its own pair of judges.

## Task And Method

**Task.** A real defect of this repository at commit `468e7908`: a Workflow
Lisp program whose `loop/recur` result is a union with a path-typed field
outside the exhausted variant compiles at target 2.28 and is rejected from
2.29. The agents receive the bug report in
[`task/bug_report/`](../../experiments/orc_vs_single_call/task/bug_report/README.md)
and the instructions in
[`task/task.txt`](../../experiments/orc_vs_single_call/task/task.txt).

**Single call.** Every implementation call in a workflow is a single call: the
same model, the same prompt, a fresh copy of the repository. A wrapper around
the agent CLI records each repository's patch after every call, so the
single-call result and the workflow result come from the same run.

**Judging.** Two independent Opus subagents per batch rate every patch under a
random id. They do not know which patches belong together, which stage a patch
comes from, or which one a workflow selected. They judge by reading code, not
by test results, on four criteria rated 0 to 2
([rubric](../../experiments/orc_vs_single_call/evaluation/rubric.md)): root
cause fixed, contracts kept, generality, and fit to the owning layer.

**Criterion.** For the confirmation run the success criterion was written
before any score was seen: the selected patch beats the mean of its group in
at least five of six runs with a mean gain of at least 0.75, and the workflow's
mean is not below the mean of single calls by the selector's own model.

## Workflow 1: Generate Four, Select One

Four implementers work on the same task in separate copies of the repository.
A selector then reads the four patches side by side, rates them against the
rubric, and names one. Nothing is modified after the implementers finish.

Source: [`workflows/best_of_n.orc`](../../experiments/orc_vs_single_call/workflows/best_of_n.orc)

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.28")
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
    "Work in the git repository at {repo} and nowhere else. Implement this change there:\n\n{task}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover.\n\nWhen you finish, write the required JSON result to the file whose path is in the environment variable ORCHESTRATOR_OUTPUT_BUNDLE_PATH; that file is how your result is received.")

  (defprompt select-prompt
    (:fills (intent :text) (repos :value List[String]) (accounts :value List[String]))
    -> Selection
    "Several engineers independently wrote a fix for the same bug, each in their own copy of the repository. The copies are listed below, with each author's account in the same order. Choose the one to merge.\nIntended change: {intent}\nRepositories: {repos}\nAuthors' accounts: {accounts}\nIn each repository read the uncommitted changes and the code around them; change nothing in any repository and do not base your choice on test results or on how much was written. Rate every candidate 0, 1 or 2 on each of four criteria: (1) the root cause is fixed, not the symptom silenced; (2) no existing validation or guarantee is weakened and nothing changes outside the intended scope; (3) the change holds beyond the reported case; (4) it sits in the layer that owns the behaviour and reuses existing mechanisms instead of adding parallel ones.\nCompare the candidates with each other: where two differ, decide which is right by reading the code, and rate equal flaws equally.\nReport `winner`: the repository path of the best candidate, copied exactly from the list. `ranking`: every repository path, best first, each followed by a colon and its four ratings. Write your reasoning to a report file under artifacts/review/ in your current directory, then write the required JSON result to the file whose path is in the environment variable ORCHESTRATOR_OUTPUT_BUNDLE_PATH.")

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

`repos` is the list of repository copies. `list/map-effect` runs one
implementer per copy, in sequence. `select-only` re-runs the selection over
existing candidates.

### Results

Confirmation run, `gpt-6-sol` as selector:

| Run | Candidates | Group mean | Selected | Gain |
| --- | --- | --- | --- | --- |
| 7 | 7.5, 6.0, 6.0, 5.5 | 6.25 | 7.5 | +1.25 |
| 8 | 7.5, 7.5, 5.0, 5.0 | 6.25 | 7.5 | +1.25 |
| 9 | 6.5, 7.5, 7.5, 7.5 | 7.25 | 7.5 | +0.25 |
| 10 | 7.5, 5.0, 7.0, 6.0 | 6.38 | 7.5 | +1.12 |
| 11 | 6.5, 6.0, 3.5, 7.0 | 5.75 | 6.0 | +0.25 |
| 12 | 6.5, 6.5, 6.0, 7.5 | 6.62 | 7.5 | +0.88 |

| Configuration | Mean |
| --- | --- |
| Single call, Sonnet (24 candidates) | 6.42 |
| Single call, `gpt-6-sol` (6 runs) | 6.67 |
| Workflow | 7.25 |
| Ceiling: always the best candidate | 7.42 |

Both parts of the criterion hold: gain in six of six runs, mean gain +0.83,
and 7.25 against 6.67.

First run, same 24 candidates rated once, two selectors:

| Selector | Mean of selected | Gain | Runs with gain | Picked the best |
| --- | --- | --- | --- | --- |
| Sonnet | 6.08 | +0.44 | 4 of 6 | 4 of 6 |
| `gpt-6-sol` | 6.67 | +1.02 | 5 of 6 | 5 of 6 |

The Sonnet selector picked the worst of four in one run.

## Workflow 2: Review And Revise With A Stronger Reviewer

One implementer, then a reviewer from another model family. The reviewer
receives the author's account of the change and the author's replies to
earlier findings. The author may fix a finding or leave it and say why. The
third round reviews only, so the workflow always ends in a reviewed state.

Source: [`workflows/reviewed_change.orc`](../../experiments/orc_vs_single_call/workflows/reviewed_change.orc)

The review and fix prompts:

```lisp
  (defprompt review-prompt
    (:fills (repo :text) (intent :text) (account :text) (replies :text))
    -> Review
    "Review the uncommitted changes in the git repository at {repo} for code and architecture quality. Read the code; change nothing except your report and result files.\nIntended change: {intent}\nThe author's account of the change, including what was tried and discarded: {account}\nThe author's replies to earlier findings: {replies}\nJudge four things: (1) the root cause is fixed, not the symptom silenced; (2) no existing validation or guarantee is weakened and nothing changes outside the intended scope; (3) the change holds beyond the reported case; (4) it sits in the layer that owns the behaviour and reuses existing mechanisms instead of adding parallel ones.\nAPPROVE if you would merge it as is, and list anything that does not block merging as notes. REQUEST_CHANGES only for defects that must be fixed before merging, each naming the input or scenario that goes wrong; drop a finding the author has answered. WRONG_APPROACH if the design itself must change. NEEDS_HUMAN if the decision is not yours. Write your review to a report file, then write the required JSON result to the file whose path is in the environment variable ORCHESTRATOR_OUTPUT_BUNDLE_PATH.")

  (defprompt fix-prompt
    (:fills (task :text) (findings :value List[String]))
    -> Revision
    "A reviewer asks for the changes below. For each finding, either fix it, or leave it and reply why it should not be fixed: a finding can be wrong. Replace code rather than adding a second mechanism beside the first.\n\nTask: {task}\n\nFindings:\n{findings}\n\nReport three things. `summary`: one sentence. `account`: the state of the whole change now, what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover. `replies`: one paragraph for each finding you did not fix, or the word none.\n\nWhen you finish, write the required JSON result to the file whose path is in the environment variable ORCHESTRATOR_OUTPUT_BUNDLE_PATH; that file is how your result is received.")
```

The workflow:

```lisp
  (defworkflow reviewed-change
    ((task String)
     (intent String)
     (repo String))
    -> Outcome
    (let* ((change (provider-result providers.coder
                     :prompt (implement-prompt :task task)
                     :model "claude-sonnet-5-5"
                     :effort "medium"
                     :timeout-sec 5400)))
      (loop/recur :max 3
        :state (loop-state
                 (round Int 1)
                 (account String change.account)
                 (replies String "none"))
        :on-exhausted (variant Outcome UNRESOLVED :reason "round limit reached" :rounds state.round)
        (fn (state)
          (let* ((review (provider-result providers.reviewer
                           :prompt (review-prompt
                                     :repo repo
                                     :intent intent
                                     :account state.account
                                     :replies state.replies)
                     :model "gpt-6-sol"
                     :effort "high"
                     :timeout-sec 5400)))
            (match review
              ((APPROVE a)
               (done (variant Outcome READY :report a.report :rounds state.round)))
              ((REQUEST_CHANGES r)
               (if (= state.round 3)
                 (done (variant Outcome UNRESOLVED :reason r.summary :rounds state.round))
                 (let* ((revision (provider-result providers.coder
                                    :prompt (fix-prompt :task task :findings r.findings)
                     :model "claude-sonnet-5-5"
                     :effort "medium"
                     :timeout-sec 5400)))
                   (continue (loop-state :like state
                               :round (+ state.round 1)
                               :account revision.account
                               :replies revision.replies)))))
              ((WRONG_APPROACH w)
               (if (= state.round 3)
                 (done (variant Outcome UNRESOLVED :reason w.reason :rounds state.round))
                 (let* ((redo (provider-result providers.coder
                                :prompt (redo-prompt :task task :reason w.reason)
                     :model "claude-sonnet-5-5"
                     :effort "medium"
                     :timeout-sec 5400)))
                   (continue (loop-state :like state
                               :round (+ state.round 1)
                               :account redo.account
                               :replies "none")))))
              ((NEEDS_HUMAN h)
               (done (variant Outcome ESCALATED :question h.question)))))))))
)
```

### Results

| Run | Outcome | Single call | Final | Change |
| --- | --- | --- | --- | --- |
| 21 | `READY`, round 1 | 6.0 | 6.0 | 0 |
| 22 | `READY`, round 2 | 5.5 | 6.5 | +1.0 |
| 23 | `UNRESOLVED`, round 3 | 2.5 | 4.0 | +1.5 |
| 24 | `READY`, round 1 | 5.0 | 5.0 | 0 |
| 25 | `UNRESOLVED`, round 3 | 3.5 | 4.5 | +1.0 |
| 26 | `READY`, round 1 | 6.5 | 6.5 | 0 |
| **Mean** | | **4.83** | **5.42** | **+0.58** |

No run got worse. The reviewer asked for changes on three of the four
lowest-rated patches and approved the rest. Each review carried one finding
that named the input that goes wrong, for example a legitimate map value of the
shape `{"ref": "data"}` being rewritten as a reference.

**Confidence is lower than for Workflow 1.** The two judges of this batch
agreed on 19 of 60 ratings. They disagree on which design is right: one
prefers admitting the compiler's reference in the validator, the other prefers
not emitting it. They agree on direction: neither rated any final patch below
its single-call version.

## What Did Not Work

| Workflow | What happened | Why |
| --- | --- | --- |
| Review loop, generic prompt, `gpt-5.5` reviewing `gpt-5.5` | reviewer approved four of four at round 1, including two patches that failed at run time | the review prompt was the author's task text; the reviewer ran the author's tests and nothing else |
| Review loop, quality prompt, Sonnet reviewing Sonnet | reviewer asked for changes in eight of eight first reviews; mean fell from 6.5 to 6.0; one patch went from 8.0 to 4.0 and another from 3.0 to 7.5 | the author had to address every finding, right or wrong; the reviewer did not receive the author's reasoning |
| Review loop, redesigned, Sonnet reviewing Sonnet | reviewer approved four of four at round 1, including patches rated 4.5 and 5.5 | the reviewer saw the defects, listed them as notes, and did not treat them as blocking |
| Easy task, any model | 83 of 83 hidden tests for the single call and for the workflow | no headroom |

Verdicts from a same-model reviewer did not track quality: in the three-round
runs the best final patch ended `UNRESOLVED`.

## Runtime And Language Findings

Found at commit `468e7908` unless noted.

| Finding | Effect |
| --- | --- |
| A provider that writes no result file in loop iteration two or later is not detected; the runtime reads the file left by the previous iteration | stale data treated as new, no diagnostic. Reproduced with stand-in agents |
| The result path in `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is relative to the run workspace | an agent that changes directory writes it elsewhere and the run fails with `missing_bundle_file` |
| The prompt contract says the runtime materializes the result from the agent's final text when no file is written | it did not |
| Provider `codex` defaults to `gpt-5.4` | the account rejects that model |
| `--config reasoning_effort=...` | ignored by the codex CLI; the global setting applies |
| A missing provider parameter | found at run time, after the first paid call, not by `--dry-run` |
| `list/map-effect` | sequential; four implementers take four times as long |
| Targets 2.29 to 2.32 | reject a loop result union with a path field outside the exhausted variant (the task of this experiment) and a caller that matches a union result into its own union |
| A list of records inside a union variant | not admitted as a provider result |

With a wrapper that makes the result path absolute and removes the previous
result before each call, the last 105 agent calls of the experiment all delivered
their result.

## Limits

- One task of moderate size. Tasks a single call cannot finish were not tested.
- Six runs per configuration.
- The judges are models. Agreement at criterion level ranged from 19 of 60 to
  68 of 72 across batches.
- In the confirmation run the criterion holds for the mean of both judges. For
  each judge alone: five of six with +1.04, and four of six with +0.62.
- The first candidate of each group averaged 7.0 in the confirmation run and
  5.5 in the first run, against group means of 6.42 and 5.65.
- The gain comes from the pattern. A script that generates four candidates and
  selects one would show it too.
- Five calls instead of one, and 15 to 30 minutes instead of about five.

## Reproduce

Compile either workflow from the repository root:

```bash
python -m orchestrator run experiments/orc_vs_single_call/workflows/best_of_n.orc \
  --entry-workflow best_of_n::best-of-n \
  --provider-externs-file experiments/orc_vs_single_call/workflows/best_of_n.providers.json \
  --input-file <inputs.json> --dry-run
```

`inputs.json` holds `task`, `intent` and `repos`, a list of absolute paths to
repository copies. The scripts in
[`harness/`](../../experiments/orc_vs_single_call/harness/) create the copies,
install the wrapper and run a trial; their paths are those of the machine the
experiment ran on.

Per-patch ratings and the judges' reasons are in
[`evaluation/`](../../experiments/orc_vs_single_call/evaluation/results.json).
