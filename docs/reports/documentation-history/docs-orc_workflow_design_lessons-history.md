# docs/orc_workflow_design_lessons.md: Historical Sections

Status: **Historical.** Original tense, versioned acceptance language, receipts
and commands are preserved as evidence, not current execution or work selection.
Current owner: [orc_workflow_design_lessons.md](../../orc_workflow_design_lessons.md).

## Historical operational record 2

## Authoring Pitfalls

Each row was hit while writing the example workflows. A rule is a restriction
the language makes on purpose. A defect is a failure after typecheck or a
wrong diagnostic; [Composition-First Procedures §11](../../design/workflow_lisp_composition_first.md#11-known-defects-and-rules-at-target-233)
lists each historical defect with its cause and the test that pins it. Before
writing new source, check the current evaluated shapes and restrictions in
[drafting guide §2A](../../lisp_workflow_drafting_guide.md#2a-program-shapes-what-runs-today).

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
nobody fills, and a misspelt provider, each with file, line and column. On the
retired flat route it also built the pure-result replay index and reported the
`pure_result_replay_unavailable` rejections above before any effect ran.

## Original provider-delivery incidents and advice

## Provider And Delivery Pitfalls

Each cost at least one paid call. `--dry-run` catches none of them.

| Pitfall | What to do |
| --- | --- |
| `claude_unrestricted_workspace` and `codex_unrestricted_workspace` have no default model or effort | pass `:model` and `:effort` on every `provider-result`; neither compile nor `--dry-run` checks them (the flat route's `provider_parameters_missing` check retired with that route), and the run fails with `provider_preparation_failed` when it reaches the call |
| No `:timeout-sec` | set one on every call that edits a repository |
| An agent does the work and answers in prose, and the run fails with `provider_result_missing` (`missing_bundle_file` on the flat route) | end each prompt with an explicit sentence: write the JSON result to the file named by `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` |
| That path is relative to the run workspace; an agent that changes directory writes the file elsewhere | keep the agent's work inside the workspace, or wrap the agent CLI to make the path absolute |
