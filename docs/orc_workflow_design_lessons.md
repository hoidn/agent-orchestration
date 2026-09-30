# Designing `.orc` Workflows That Beat A Single Call

Status: informative guidance
Source: experiments of 2026-09-28, reported in
[`.orc` Workflows Versus A Single Agent Call](reports/2026-09-28-orc-versus-single-call.md)
Audience: workflow authors and reviewers
Normative contracts: `specs/`

A single call to a current agent already plans, edits, tests and corrects
itself. A workflow improves on it only by supplying something the agent cannot
give itself. This guide records what did and did not, and the authoring
mistakes that cost runs.

Working examples:
[`best_of_n.orc`](../experiments/orc_vs_single_call/workflows/best_of_n.orc) and
[`reviewed_change.orc`](../experiments/orc_vs_single_call/workflows/reviewed_change.orc).

## Before Drafting

Answer these four questions. If the answer to the first is "nothing", do not
add the step.

| Question | Why |
| --- | --- |
| What does each step add that the previous agent did not have? | The only sources of gain found were independent candidates to choose from, and a judge with different knowledge than the author. A deterministic gate and a human decision are two more; they were not measured here |
| Is the judge a different, stronger model than the author? | With the author's own model as reviewer or selector, results ranged from -0.5 to +0.44 on an 8-point scale. With a stronger model from another family, from +0.58 to +1.02 |
| Does a single call already solve the task? | On a task one call solved every time, every workflow tied and cost twice as much |
| How will you know the workflow helped? | A verdict such as `READY` is not evidence. With a same-model reviewer, verdicts did not track quality |

## Choosing A Pattern

| Pattern | Use when | Measured |
| --- | --- | --- |
| Generate several candidates, select one | single calls vary in quality and a stronger judge is available | +0.83 and +1.02 over the single call, gain in 11 of 12 runs |
| Review and revise with a stronger reviewer | one candidate is expensive, or the change must be corrected rather than replaced | +0.58, no run got worse; judges agreed less |
| Review and revise with the author's model | do not use | -0.5 to 0 |

Selection cannot damage a candidate. Revision can: in one run three review
rounds took a patch two judges would have merged from 8.0 to 4.0.

`list/map-effect` runs its body in sequence. Four implementers take four times
as long as one. A `command-result` or a `call` of a workflow runs as its body;
a call to an inline procedure that holds the command is refused ([drafting guide §2A](lisp_workflow_drafting_guide.md#2a-program-shapes-what-runs-today)).

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

## Authoring Pitfalls

Each row was hit while writing the example workflows. A rule is a restriction
the language makes on purpose. A defect is a failure after typecheck or a
wrong diagnostic; [Composition-First Procedures §11](design/workflow_lisp_composition_first.md#11-known-defects-and-rules-at-target-233)
lists each known defect with its cause and the test that pins it. Before
writing, check the program's shape in the [drafting guide §2A](lisp_workflow_drafting_guide.md#2a-program-shapes-what-runs-today): a loop in a branch or in
another loop, a large state update, a record as a command input, decimals, and
a helper shared by branches inside a loop, each with the form that runs.

| Symptom | Kind | Cause | Write instead |
| --- | --- | --- | --- |
| `compiler_defect` (`unsupported nested WCC M2 prefix for LetStarExpr`) | Defect, below 2.33 | a `match` subject that elaborates to bindings, such as a `let*` expression, or a local wrapper around an imported effectful procedure, which older targets infer effect-free and inline | target 2.33; below it, bind the effectful call first: `(let* ((v (check ...))) (match v ...))` |
| `compiler_defect` (`unsupported pure projection expression: ProcedureCallExpr`) | Defect, below 2.33 | an effectful call written inside `loop-state :like` | bind it first: `(let* ((next (revise ...))) (continue (loop-state :like state :current next)))`, or target 2.33 |
| `compiler_defect_loop_control_value` (from 2.33; `compiler_defect` below) | Defect | an effectful `if` or `match` as a `loop-state` field, or bound by `let*` in a loop body | a `match` in tail position whose arms `continue`; a procedure called there with a literal argument fails with `workflow_signature_mismatch`, so pass fields of the loop state, or call one helper that chooses the branch |
| `proc_ref_signature_invalid` | Defect | below 2.33, the call to a generic helper used directly as a `match` subject; at 2.33 too, a generic call with hooks in a `loop-state` field under `continue` | bind the helper's result with `let*`, then `match`; at 2.33 the direct subject compiles |
| `workflow_return_not_exportable` at `:max` | Rule | the bound comes from a workflow parameter | a compile-time integer constant of at least 1 |
| `workflow_boundary_type_invalid`, "max_iterations must be > 0" | Rule | `:max 0` | zero is rejected at compile time; it is not a run-time outcome |
| `workflow_boundary_type_invalid`, "may only override scalar repeat_until outputs" | Defect | targets 2.29 and later: a loop result union with a path field outside the exhausted variant | declare target 2.28 |
| `workflow_boundary_type_invalid`, "without required author-time variant proof" | Defect | a `match` whose arms mix a plain variant with a loop, or, from 2.29, a caller that matches a union result into its own union. At 2.33 the first shape fails `--dry-run` with `pure_result_replay_unavailable`, "source contract disagrees with its binding type" | put the first check inside the loop, or give every arm an effectful step |
| `pure_result_replay_unavailable`, "unknown result member" or "crosses the indexed frame scope", at `--dry-run` | Defect | pure bindings over a loop or command result: a record built with a literal in a `match` arm, or bindings in an `if` branch over a `call` made in that branch | pass the fields to the next effect instead of binding them |
| `collection_element_type_unsupported` | Rule | a list of records inside a union variant or a provider result | `List[String]`, or a path to a file the agent writes |
| `module_path_mismatch` | Rule | the file name differs from the module name | name the file after the module |
| `compiler_defect` or `workflow_return_not_exportable` in `std/improve.orc` | Defect | a pure `improve` hook | make the hook command- or provider-backed |
| Empty effect summary | Defect, below 2.33 | hooks imported from another module | declare the hooks in the calling module when the summary matters, or target 2.33 |

Run `--dry-run` before any real call. It caught a missing `match` arm, a field
of the wrong variant, an `Int` passed to a text slot, a prompt placeholder
nobody fills, and a misspelt provider, each with file, line and column. It
also builds the pure-result replay index, so it reports the
`pure_result_replay_unavailable` rejections above before any effect runs.

## Provider And Delivery Pitfalls

Each cost at least one paid call. `--dry-run` catches only the first.

| Pitfall | What to do |
| --- | --- |
| `claude_unrestricted_workspace` and `codex_unrestricted_workspace` have no default model or effort | pass `:model` and `:effort` on every `provider-result`; compile and `--dry-run` report `provider_parameters_missing` at the call |
| No `:timeout-sec` | set one on every call that edits a repository |
| An agent does the work and answers in prose, and the run fails with `missing_bundle_file` | end each prompt with an explicit sentence: write the JSON result to the file named by `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` |
| That path is relative to the run workspace; an agent that changes directory writes the file elsewhere | keep the agent's work inside the workspace, or wrap the agent CLI to make the path absolute |

The runtime removes a call's result file before the call starts, so a provider
that delivers nothing in a later loop iteration fails with
`missing_bundle_file` instead of repeating its previous answer. Provider
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
| Pair the comparison: the workflow's first call is the single call | it removes run-to-run variation from the comparison |
| Repeat anchor patches across batches | judges used different parts of the scale; two anchors moved from 8.0 and 3.0 to 7.0 and 5.0 |
| Do not score with tests the agent can run | agents test themselves until they pass; every arm reached 100 percent |
| Report judge agreement | it ranged from 19 of 60 to 68 of 72 |
