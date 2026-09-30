# Workflow Lisp Evaluated Execution

## Metadata

- **Status:** proposed target; not implemented. The owner approved a
  feasibility spike on 2026-09-29. Nothing here is a current contract.
- **Kind:** execution model, run state and compiler output contract
- **Owner:** Workflow Lisp frontend and runtime
- **Created:** 2026-09-29
- **Evidence:**
  [value/effect separation decision brief](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md),
  [execution facts](../reports/2026-09-29-workflow-lisp-execution-facts.md)
- **Plan:** [evaluated execution plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md)
- **Amends on acceptance:**
  [core calculus middle-end](workflow_lisp_core_calculus_middle_end.md)
  (§10.1 constructs, §11.4 identity, §15 alternatives, §16 deferred work),
  `specs/state.md`, `specs/io.md`, `specs/cli.md`, `specs/versioning.md`
- **Related:** [numeric surface](workflow_lisp_numeric_surface.md),
  [writing each fact once](workflow_lisp_write_once.md),
  [lexical execution checkpoints](workflow_lisp_lexical_execution_checkpoints.md),
  [pure-result replay](workflow_lisp_pure_result_replay.md),
  [design principles](workflow_language_design_principles.md) 5, 6, 10, 15,
  17, 27 and 28

## 1. Summary

A compiled workflow is a program in the workflow core calculus. The runtime
evaluates that program. Values live in a lexical environment and are
computed. Effects have an identity and are recorded in a memo. Resume
evaluates the program again from its entry and takes each recorded result
from the memo.

Four rules follow.

| Rule | Statement |
| --- | --- |
| E1 | A value is the result of evaluating an expression. It has no step, no name in run state and no stored copy |
| E2 | An effect is identified by its site in the program and the path of activations that reached it. Nothing else enters the identity |
| E3 | An effect runs only when the memo holds no committed result for its identity. A committed result is returned without running anything |
| E4 | What a reader sees as steps is a view derived from the memo |
| E5 | An effect receives any transportable value as input, and returns one. A value does not have to be flattened to reach a command |

## 2. Problem

At run time a value exists only as the output of a step. The decision brief
states the consequences. Measurements since then:

| Evidence | Result |
| --- | --- |
| Totality matrix, 120 combinations of value form and position, after the shared defect repairs | 34 combinations typecheck and then fail. Every one needs a repair in code that serves only the flat step route |
| A search controller with a 14-field state, written five ways | Does not compile. The state update is 361 nodes against a bound of 256. With the bound raised, a loop inside an `if` branch is rejected |
| Rewrite of a review workflow with a library helper | A pure `match` over the helper's result is rejected; a nested `if` in a hook is rejected |
| Identity | Step ids, checkpoint ids and schema digests change when two blank lines are added or the file is moved |

The execution facts report lists 23 properties of the current system that an
evaluator would have to rebuild or that depend on steps being flat. This
design answers each.

## 3. Goals And Non-Goals

Goals:

- Every program that typechecks runs. No rule of the language depends on
  where a value is used.
- Structured control nests without limit: a loop in a branch, a loop in a
  loop, a branch in a hook.
- Resume never runs an effect that committed a result.
- Effect sites and their contracts are known before a run starts.
- Identity survives formatting edits and moving the repository.
- Older targets keep their behaviour, byte for byte.

Non-goals:

- Replaying arbitrary code. The language stays closed: bounded loops, no
  first-class procedures, a fixed effect vocabulary.
- Exactly-once effects in the world. The rule is the owner's decision of
  2026-09-29: an effect without a committed result runs again, unless its
  boundary declares that it must not.
- Capturing or rolling back workspace files.
- Changing YAML workflows or targets that exist today.

## 4. The Closed Program

The evaluator needs a program that is complete. Today part of what execution
needs is computed after the calculus, during lowering, and is keyed by step
name. The compiler therefore produces a closed program, with these
properties.

| # | Property | Today |
| --- | --- | --- |
| P1 | Whole program. The body of every `call` target is present, specialized. Nothing is elaborated after the program is built | Callee bodies are elaborated during lowering |
| P2 | Only calculus. No node holds a surface expression | Loop state, lists, `list/map`, `path/join-under`, bundle paths and several effect payloads are surface objects |
| P3 | Complete effects. Each effect node carries its operation class, its resolved target, its inputs as atoms, its result type, the output contract derived from that type, its prompt assembly, its policy and its repeat rule | Contracts, result paths, prompt rows, policy rendering and timeouts are computed in lowering |
| P4 | Sites. The program carries a table of its effect sites. Two call sites of one procedure are two sites | One node identity is shared by every inlined copy; an ordinal from a counter tells them apart |
| P5 | Checked form. A validator checks the normal form of the program when it is built | Only tests check it |
| P6 | Provenance. Every node keeps its source span and form path. Provenance never enters an identity | Spans and type text with file paths enter several identities |
| P7 | An artifact. The closed program is written as canonical JSON. Its digest is the program identity | No such artifact |

Amendments to the calculus. The accepted design lists ten constructs and
requires an amendment for each addition. The implementation already has more.
The closed program has these:

| Construct | Role |
| --- | --- |
| `atom` | literal, name, field access, record construction, pure operator application |
| `inject` | variant introduction |
| `select` | conditional value |
| `let` | sequencing |
| `perform` | one effect |
| `call` | evaluation of a specialized procedure or workflow body |
| `case` | variant elimination |
| `if` | branch on a strict `Bool` |
| `join`, `jump` | second-class continuation |
| `loop`, `continue`, `done` | bounded iteration, with its budget and its exhaustion body |
| `par-map` | bounded parallel iteration over a list (section 11) |
| `halt` | result |

## 5. Values

A value is immutable and typed. The evaluator holds values in an environment:
a chain of frames, one per `let`, `case` arm, `join`, loop iteration and
`call`.

Pure operators have one implementation, the catalog of
`orchestrator/workflow/pure_expr.py`, applied to values. The typechecker reads
the same catalog. A pure operator that cannot produce a value, on overflow,
division by zero or a non-finite result, fails the run with a diagnostic
located at the expression.

No bound applies to the size of an expression. The bound of 256 nodes limits
a serialized payload, and no payload exists. Evaluation terminates because
loops are bounded and nothing recurses. A budget on evaluation steps, derived
from the program's size and its loop bounds, reports a compiler defect if it
is exceeded.

## 6. Effect Identity

```text
identity = (site, activation path)
site     = (definition, lexical path)
```

- **Definition.** The qualified name of the workflow or procedure that
  contains the effect, with its specialization arguments given by the
  canonical identity of each type: the declaring module and name, and the
  arguments, recursively.
- **Lexical path.** The path from the definition's body to the effect node:
  binder names, branch labels, and an ordinal among unnamed siblings.
- **Activation path.** The frames from the entry to the site. A frame is a
  call site, a loop site with an iteration ordinal, or a parallel map site
  with an item index.

Nothing else enters: no source span, no file path, no text of a type, no
position among steps, no visit count.

The canonical text of an identity is its presentation key:

```text
run-search / loop[3] / repair / propose
```

An attempt is an ordinal under an identity. Attempts never change the
identity.

| Edit | Identity |
| --- | --- |
| Blank lines, comments, reformatting | Unchanged |
| The repository or the package moves | Unchanged |
| A binder is renamed, or an effect moves to another branch | Changes |
| An effect is added before another in the same sequence, both unnamed | The second changes. Naming the binding keeps it stable |

## 7. The Effect Memo

The memo is an append-only journal under the run root. One writer appends to
it. Each record is written and synchronized to disk before the evaluator
proceeds.

| Record | Written | Content |
| --- | --- | --- |
| `started` | Before an attempt is launched | identity, attempt ordinal, digest of the resolved input, time |
| `committed` | After the result passed its contract | identity, attempt ordinal, the validated result or its location and digest, time |
| `failed` | After an attempt ended without a valid result | identity, attempt ordinal, exit information, the contract violation if any |
| `suspended` | When an effect waits for a person | identity, the request |

The resolved input of an effect is everything that determines what the effect
is asked to do: its arguments, its assembled prompt with the digests of the
files the prompt reads, its contract, and its provider binding with the
options in force.

`state.json` stays. For this profile it is a summary and a view (section
10), rewritten from the memo. It is not the authority for any result.

## 8. Evaluation And Resume

Evaluation of `perform` at identity `i` with resolved input `x`:

| Memo holds for `i` | Action |
| --- | --- |
| A committed result with input digest equal to the digest of `x` | Return the result. Run nothing |
| A committed result with another input digest | Stop with `effect_input_diverged`, located at the site, showing both digests and which part of the input differs |
| A `started` or `failed` attempt and no commit | If the boundary declares that the effect must not repeat, stop with `lexical_restore_pending_effect_unsafe`. Otherwise record a rerun diagnostic and run a new attempt |
| A `suspended` record and no commit | Stop and report the pending request |
| Nothing | Run the first attempt |

Running an attempt:

1. Append `started`.
2. Give the effect a result path derived from the identity and the attempt
   ordinal, under the run root. The path does not exist before the attempt.
3. Launch through the performer of the effect's class.
4. Validate the result against the contract.
5. Append `committed`, or `failed`.

The file of an earlier attempt is never removed or overwritten. Each attempt
has its own path, so the evidence of a failed attempt stays beside the result
of the one that succeeded.

What a failure at each moment leaves, and what resume does:

| The process stops | The memo holds | Resume |
| --- | --- | --- |
| Before `started` is written | Nothing for this attempt | Runs the attempt |
| While the effect runs, or while it writes its result | `started` | Treats the attempt as one without a committed result. A partial file does not parse or does not validate, so it is never a result |
| After the effect finished and before `committed` is written | `started`, and a complete result file | Same as above: the file is evidence, not a result. Only `committed` makes a result |
| After `committed` | `committed` | Returns the result |

A result exists only as a `committed` record. A file at a path, however
valid and however recent, is not one.

Resume is evaluation from the entry with the memo of the run. Because
evaluation is a function of the program, the inputs and the committed
results, it reaches the same effects in the same order up to the first effect
without a commit.

The program identity and the bound inputs are recorded when a run starts. A
resume with another program identity or other inputs is refused before
anything is evaluated, as today.

## 9. Effect Inputs And Performers

### 9.1 Inputs

An effect takes values. Any transportable value is admitted: scalars,
records, unions, lists, optionals and paths, nested to any depth.

| Value | How a command or provider receives it |
| --- | --- |
| A scalar used in `:argv` | Rendered into the argument |
| Any value bound in `:inputs` | One typed input document in JSON, written under the run root at a path derived from the effect's identity and attempt. The command receives the path. The document is validated against the declared types before launch |
| A value that is large, or that a person should be able to read | A materialized view. The effect receives the path of the view |
| A prompt fill | As the prompt calculus defines |

The input document is serialized deterministically. Its digest is part of the
resolved input of section 7.

A file that carries data to an effect is a representation of a value. It is
never read back to decide what the workflow does next. The workflow decides
from values in the environment and from committed results.

An expression in an argument position is evaluated like any other. The author
does not have to find a name that happens to hold the same value.

### 9.2 Performers

A performer executes one class of effect. It receives the effect node of the
closed program, the resolved input, the result path and the workspace. It
returns a result or a failure. It reads no run state and writes none.

| Class | Performer built from | Notes |
| --- | --- | --- |
| Command | `StepExecutor.execute_command` | Already independent of the executor |
| Provider, composed delivery | `ProviderExecutor.prepare_invocation` and `execute`, with prompt assembly moved out of the executor | Prompt dependency snapshots become part of the resolved input |
| Workflow or procedure call | None. A call is evaluation | No child executor and no call frame |
| Resource transition | `execute_transition` | Already independent. Its idempotency key stays |
| Materialized view | The existing step function | Reads its value from the environment |
| Request for input | New | `suspended`, then `committed` by the answer command |
| Provider, phased delivery | The existing coordinator behind the performer interface | The coordinator commits state itself today |
| Supervision, peer group | The existing coordinators behind the performer interface | One effect, one identity, its own internal ledger |
| Run reference, trial | The existing runtimes behind the performer interface | One effect; the child run is a separate run in its own workspace |

The last three rows wrap a coordinator that today reads the executor's
cursor. Until each is ported, a program that uses it stays on a target of the
flat route.

## 10. Views

Readers of run state depend on rows named by step, on one current step and
on order. For this profile the runtime derives:

| View | Derived from |
| --- | --- |
| `steps` | One row per effect identity, keyed by its presentation key, in order of first start. Status, result, error and timing come from the memo |
| `current_step` | The effect in flight. With several in flight, the first started |
| `current_effects` | Every effect in flight |
| `workflow_outputs` | The value of `halt` |
| Logs and session files | Named by presentation key and attempt ordinal |

The resume planner, the projection integrity audit, lexical checkpoints and
the pure-result replay index are not used by this profile.

## 11. Parallel Effects

`par-map` evaluates a body once per item of a list, with at most `n` items in
evaluation at a time.

- Each item's body is evaluated in sequence. Items are independent.
- Identity includes the item index, so it does not depend on which item
  finishes first.
- The result is a list in the order of the input.
- One writer appends to the memo. Evaluations send it records; they never
  write.
- When an item fails, the others run to completion and their results are
  committed. The map then fails. Resume runs only the items without a
  commit.
- Every effect of an item runs in a working directory given by the map as an
  expression over the item. Before launch the runtime checks that no two
  items resolve to the same directory, and refuses with
  `parallel_workspace_shared` if they do.

Surface form:

```lisp
(list/map-effect ((repo repos)) :max 8 :parallel 4 :workspace repo
  (call implement-one :task task :repo repo))
```

Without `:parallel` the form means what it means today.

Limits, stated so that the form is not taken for more than it is:

- It evaluates a batch. The list is fixed before the first item starts, and
  the map returns when every item has settled. A policy that chooses its next
  candidate after seeing each result is a different policy; running it in
  parallel changes what it decides. This form does not express it.
- A budget counted in effects is charged per item, before the item starts. An
  item that would exceed the budget does not start.
- There is no cancellation in this version. A running item is not stopped
  when another fails.
- It is adopted when a workflow needs it. It does not repair any failure of
  sequential programs.

## 12. Diagnostics

- A refusal that compares a value with a limit prints the value and the
  limit.
- A failure after typecheck says that it is a compiler defect, names the
  stage and points at the authored form.
- A run-time failure of a pure operator points at the expression and prints
  its operands.
- `effect_input_diverged` prints what differs, not only that something does.

## 13. Targets And Compatibility

- Evaluated execution applies from one new target. A program at that target
  runs on the evaluator only.
- Programs at targets that exist today compile and run as they do, with
  byte-identical build artifacts.
- A run started under one profile is resumed under it.
- A module at the new target may import a module at an older target when the
  imported definitions use only forms the closed program can express. The
  import is compiled under the new target's rules.
- A module at an older target may not call a module at the new target. The
  two run on different runtimes.

## 14. What Is Preserved

| Guarantee | How |
| --- | --- |
| A result is validated before it becomes canonical state | Step 4 of section 8, before `committed` |
| No committed provider call runs again | Rule E3 |
| A changed source is refused before any mutation | Program identity, section 8 |
| Effect sites are known before a run | The site table, P4 |
| Wrong-path writes fail closed; stdout is not a result channel | The performer reads only its result path |
| Refusals name their rule | Section 12 |
| One run at a time in a workspace | The workspace lock |
| Runs can be inspected from the filesystem | The memo and the derived views are files |

## 15. What The New Target Does Not Use

Defunctionalization to steps, the older lowerers, positional resume, the
projection integrity audit, lexical checkpoints, pure projection steps, the
pure-result replay index, and the rule that structured control is top-level
only. They stay in the repository for older targets.

## 16. Alternatives

| Alternative | Decision | Reason |
| --- | --- | --- |
| Repair the flat route position by position | Rejected as the long-term route | Every remaining defect of the matrix has a second layer under it. Each new form needs a lowering, a resume story and a replay story |
| Keep flat steps and evaluate pure expressions on demand | Not chosen | Removes the producer rule. Keeps defunctionalization, positional resume and one iteration ordinal per key |
| Restore a serialized environment at a checkpoint | Not chosen | Needs every value to be serializable at every point and an identity for every program point. Evaluation from the entry needs neither |
| Journal replay of arbitrary code | Rejected in 2026, and still | This design is not that. The language is closed, sites are listed before a run, every memo hit is checked against the input, and no effect runs unless the memo lacks its result |
| A workflow library in a host language | Rejected | Loses checks before a run and the bound on what an authored workflow can do |

Two measures on the flat route are useful before this design exists in code,
and the plan carries them as interim work. They do not change this design.

- Sharing a bound value in a pure payload, where today it is copied at each
  use. This removes the size refusal of the search controller. Raising the
  bound does not: with the bound raised, the controller is refused for a loop
  inside a branch.
- A result path per call, absent before the call. The repairs plan removes a
  stale file before each call, which also removes the file of the previous
  iteration. Section 8 keeps every attempt's file.

The earlier rejection of journal replay gave three reasons: static effect
visibility, validation before commit, and parity evidence that a machine can
compare. The first two are kept by P4 and by section 8. The third changes.
Evidence of parity between the two routes is behavioral: for the same
program, inputs and effect results, the same ordered effect identities, input
digests, result digests and final value.

## 17. Evidence Requirements

| Requirement | Measure |
| --- | --- |
| Totality | Every cell of the totality matrix that typechecks runs. No known defect remains at the new target. The matrix covers each form written directly, through a helper of the same module, and through an imported helper |
| Real programs | The `std/improve` example and the two workflows of the single-call comparison run to their expected result, unchanged in source apart from the target |
| The search controller | The MLEvolve-inspired controller makes the decisions of its Python reference, in the same order, with the same budget spent, and returns the same result. Its form is the compact one, with one helper for both branches, not the one with a copy of the code per branch |
| Growth | Doubling the fields of the controller's state and the number of its branches leaves it running. No limit depends on the size of an expression |
| Structured inputs | A command receives a candidate record and the list of earlier trials, with their types, and rejects a document of another shape |
| Nesting | A loop in a branch, a loop in a loop, and a branch in a hook run |
| Resume | For each real program, interrupting after each effect and resuming gives the final value of the uninterrupted run, with no committed effect run twice |
| Identity | Adding blank lines, and moving the program and the package, change no identity |
| Sites | For every run, the identities in the memo are instances of sites in the site table |
| Parity | On programs both routes accept, the effect traces are equal |
| Older targets | Byte-identical build artifacts |

## 18. Feasibility Obligations

Each claim is an open prerequisite until its fixture passes. The spike of the
plan tests the first five.

| Claim | Fixture |
| --- | --- |
| The closed program can be built for the corpus | P1 to P7 hold for every workflow of the repetition census corpus |
| A lexical path distinguishes every effect site, across inlined copies | A procedure with one effect, called from three arms of one `match` |
| Prompt assembly can run outside the executor | The assembled prompt of the `std/improve` example equals the one the flat route assembles |
| Evaluation is a function of program, inputs and committed results | Two evaluations with one memo give the same trace. The known hidden inputs, path existence checks, variant selection by workspace digest, secrets and the wall clock, are each an effect or part of an effect's resolved input |
| The views satisfy their readers | `orchestrator report`, the dashboard cursor, the monitor classifier and the watchdog probe, run against a state derived from a memo |
| The wrapped coordinators can run behind the performer interface | One supervision group and one trial, each as a single effect |
| Non-finite numbers cannot reach an input digest | The numeric surface's boundary rule |
| A typed input document can carry records, unions and lists | One command that receives a list of records of unions and returns it unchanged |

## 19. Decisions For The Owner

| # | Decision | Recommendation |
| --- | --- | --- |
| 1 | The number of the new target | A new major number, because the run state profile and the runtime change |
| 2 | Whether effect classes that wrap a coordinator are in the first release | No. Commands, composed providers, calls, transitions, views and requests for input first |
| 3 | Whether the memo stores results inline or by reference | Inline up to a size limit, by reference above it |
| 4 | Whether a changed input stops a resume or reruns from that effect | Stop. Rerunning is a separate, explicit command |
| 5 | When older targets are retired | After the maintained workflows run at the new target |
