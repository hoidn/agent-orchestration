# Designing `.orc` Workflows That Beat A Single Call

Status: informative guidance
Source: experiments of 2026-09-28, reported in
[`.orc` Workflows Versus A Single Agent Call](reports/2026-09-28-orc-versus-single-call.md), and their rerun on the
evaluated route on 2026-10-14 ([E-A](reports/2026-10-14-orc-versus-single-call-evaluated.md),
[E-B](reports/2026-10-14-design-review-execute-versus-single-call.md),
[postmortem](reports/2026-10-14-effectiveness-experiments-postmortem.md)), the
[difficulty calibration](reports/2026-10-14-task-difficulty-calibration.md) and its
[continuation](reports/2026-10-15-calibration-continuation.md) of 2026-10-15
Audience: workflow authors and reviewers
Normative contracts: `specs/`

A single call to a current agent already plans, edits, tests and corrects
itself. A workflow improves on it only by supplying something the agent cannot
give itself. This guide records what did and did not, and the authoring
mistakes that cost runs. On the evaluated route, the two patterns that gained in
September still gained over their own first or average candidate. Each scored
less than half a point (of 8) above a single call of the selector's model. No
comparison has yet been run on a calibration-qualified task.

The linked historical compiler observations/workarounds describe the original
pre-2.35 experiment targets. For current 2.35/2.36 admission and execution,
use the [drafting guide](lisp_workflow_drafting_guide.md#2a-program-shapes-what-runs-today);
do not downgrade a new workflow to reproduce a historical workaround.

Working examples:
[`best_of_n.orc`](../experiments/orc_vs_single_call/workflows/best_of_n.orc) and
[`reviewed_change.orc`](../experiments/orc_vs_single_call/workflows/reviewed_change.orc).

## Before Drafting

Answer these four questions. If the answer to the first is "nothing", do not
add the step.

| Question | Why |
| --- | --- |
| What does each step add that the previous agent did not have? | Gains came from independent candidates to choose from, and from a judge with different knowledge than the author; both were measured on judge scores. A deterministic gate and a human decision were not measured here |
| Is the judge a different, stronger model than the author? | With the author's own model as reviewer or selector, September's results ranged from -0.5 to +0.44 on an 8-point scale. With a stronger model from another family, from +0.58 to +1.02 in September and E-A |
| Does a single call already solve the task? | On a task one call solved every time, every workflow tied and cost twice as much. A feature chosen as too large for one call (the REPL, with its public interface spelled out) was finished by one call, 16/16 and 14/16 hidden tests. Measure this before running any treatment |
| How will you know the workflow helped? | A verdict such as `READY` is not evidence. With a same-model reviewer, verdicts did not track quality |

## Choosing A Pattern

For current APIs, complete candidate-generation and selection examples, and
execution prerequisites, use the [Workflow Lisp Library Reference](lisp_library_reference.md).
The measurements below help choose a pattern; they do not define its API.

| Pattern | Use when | Measured |
| --- | --- | --- |
| Generate several candidates, select one | single calls vary in quality and a stronger judge is available | Flat route (2026-09-28): +0.83 and +1.02 over the candidate-group mean, gain in 11 of 12 runs. Evaluated route ([E-A](reports/2026-10-14-orc-versus-single-call-evaluated.md)): +1.02, gain in 4 of 6 runs, one run short of its criterion; +0.33 over single calls |
| Review and revise with a stronger reviewer | one candidate is expensive, or the change must be corrected rather than replaced | Flat route: +0.58, no run got worse; judges agreed less. Evaluated route (E-A): +0.67, no run worse; the reviewer approved 4 of 6 first patches unchanged. |
| Review and revise with the author's model | no benefit was demonstrated in this bounded experiment; validate it on the intended task | Flat route (2026-09-28) only: -0.5 to 0; not rerun on the evaluated route |
| Plan with one model, review the plan with another, then execute | not established | Not measured on a calibration-qualified task; the [E-B](reports/2026-10-14-design-review-execute-versus-single-call.md) task did not qualify |

Selection leaves candidate patches unchanged, though it can choose a worse
candidate than the alternative. Revision can damage a selected patch: in one
September run with a same-model reviewer, three review rounds took a patch two
judges would have merged from 8.0 to 4.0.

`list/map-effect` runs its body in sequence; the 2.37 `:parallel` form is
bounded and not yet publicly qualified ([capability matrix](capability_status_matrix.md)).
Four implementers take four times
as long as one. Current composition rules are in [drafting guide §2A](lisp_workflow_drafting_guide.md#2a-program-shapes-what-runs-today).

## Writing A Review Loop

Each rule fixes a defect that was observed.

| Rule | Defect it fixes |
| --- | --- |
| Write the review prompt as review criteria. Do not reuse the author's task text | reviewers read "fix", "add tests" and "verify your work" as their own instructions and approved after running the author's tests |
| Pass the author's account to the reviewer: what changed and why, what was tried and discarded, what is not covered | a reviewer asked for the very design the author had tried and reverted because it broke an existing test |
| Let the author answer a finding instead of fixing it, and tell the reviewer to drop answered findings | "address every finding" made authors apply wrong findings |
| Ask only for findings that block merging, each naming the input or scenario that goes wrong. Allow approval with notes | one prompt made the reviewer request changes every time; its findings were plausible and several made the code worse |
| Tell the author to replace code, not to add a second mechanism beside the first | "without changing the approach" left two mechanisms for one problem |
| Make the last round review only | a final fix that nobody reviewed ended the run with no usable verdict |
| Do not write "do not modify files" in a prompt that also asks for a report file | one model obeyed the first instruction and delivered nothing |

The review prompt that worked, from `reviewed_change.orc`, has five lines:
where to look, the intended change, the author's account and replies, four
criteria, and the verdict rules.

<a id="authoring-pitfalls"></a>

The experiment-era compiler symptoms/downgrades/workarounds are preserved as historical evidence, not current authoring recommendations. Use the current checks below; do not retarget to an old entry. See the [preserved record](reports/documentation-history/docs-orc_workflow_design_lessons-history.md#historical-operational-record-2).

## Current Authoring Checks

Check [admitted program shapes](lisp_workflow_drafting_guide.md#2a-program-shapes-what-runs-today)
before constructing a workflow. Use a compile-time positive bound for a bounded
loop; keep module paths consistent; access variant fields only under typed
proof; and keep pure helpers effect free. Do not invent an effectful wrapper
or choose a retired target to bypass a historical compiler defect.

Run `--dry-run` with the actual extern/command manifests and inputs before a real
call. It checks source/type/admission and input binding; it does not certify
provider authentication, model quality, native isolation or a successful run.

## Provider And Delivery Pitfalls

Each cost at least one paid call. `--dry-run` catches none of them.

| Pitfall | What to do |
| --- | --- |
| `claude_unrestricted_workspace` and `codex_unrestricted_workspace` have no default model or effort | pass `:model` and `:effort` on every `provider-result`; neither compile nor `--dry-run` checks them (the flat route's `provider_parameters_missing` check retired with that route), and the run fails with `provider_preparation_failed` when it reaches the call |
| No `:timeout-sec` | set one on every call that edits a repository |
| An agent answers in prose and the call reports `provider_result_missing` | inspect the attempt's runtime-selected delivery contract and missing-result diagnostics. The runtime renders transport/path instructions; authored prompts describe the task and typed outcome. |
| A provider writes outside the selected result path | preserve the runtime delivery path while using tool working directories; inspect the recorded attempt delivery rather than adding another result channel. |

Each call gets a fresh, exclusively created attempt directory for its result
file, so a provider that delivers nothing in a later loop iteration fails with
`provider_result_missing` instead of repeating its previous answer. Provider
`codex` defaults to `gpt-5.5` and passes `:effort` as
`model_reasoning_effort`.

## Before Spending On Real Calls

1. Compile with `--dry-run`.
2. Run every branch once with stand-in agents: scripts on `PATH` named after the
   agent CLI that write a fixed result. Check the ordered calls and the outcome
   of each branch.
3. In a loop, check that round two receives round two's findings, not round
   one's.
4. Kill a run at a commit boundary and resume it. Count the calls before and
   after.
5. Run the orchestrator from a frozen copy of the code when the main tree is
   being edited.
6. Do not edit a script that a running trial is executing.

## Evaluating A Workflow

| Rule | What went wrong without it |
| --- | --- |
| Write the success criterion before seeing scores | a secondary analysis looked like a win after the primary one had missed its bar; it took a second run to confirm it |
| Judge blind: random ids, no stage, no grouping | an unblinded reading favoured the workflow; blind judges found the revised patches worse |
| Use a judge that is not the workflow's own judge | otherwise the selector is scored by itself |
| Predeclare the paired baseline and report the comparator actually used | the best-of-N criterion here compared the selected patch with its group mean, not its first call; see the [comparison report](reports/2026-09-28-orc-versus-single-call.md#workflow-1-generate-four-select-one) |
| Repeat anchor patches across batches | judges used different parts of the scale; two anchors moved from 8.0 and 3.0 to 7.0 and 5.0 |
| Do not score with tests the agent can run | agents test themselves until they pass; every arm reached 100 percent |
| Report judge agreement | in September it ranged from 19 of 60 to 68 of 72 ratings; r = 0.81 in E-A |
| Calibrate difficulty before freezing the criterion: expected review blockers on single-call patches at least one; report the single call's hidden acceptance, which is not a condition | the reviewer approved 4 of 6 first patches unchanged, which leaves review-and-revise nothing to gain; the E-B task did not qualify. The [calibration](reports/2026-10-14-task-difficulty-calibration.md) also required every single call below half of hidden acceptance, and no rung met it; the owner removed that condition on 2026-10-15. Continuation evidence (post-data, owner-approved): with a third sample, [rung 1 qualifies](reports/2026-10-15-calibration-continuation.md) on blockers 1, 1 and 1 |
| Smoke with the real agents before freezing, and isolate them (own `/tmp`, process list, result paths inside the workspace) | live agents misplaced result files and inherited another session's environment; a batch and a half of runs were discarded |
| Compute interim readouts with the summarizer's own join and check the anchors first | a positional join reported both workflows losing; joined by clone id they met most clauses |
