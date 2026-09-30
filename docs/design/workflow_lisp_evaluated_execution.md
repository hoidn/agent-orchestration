# Workflow Lisp Evaluated Execution

## Metadata

- **Status:** accepted for the first release at gate G1 on 2026-09-29;
  revised with the spike's findings. Not implemented: the spike under
  `experiments/evaluated_execution_spike/` is throwaway evidence, and nothing
  under `orchestrator/` runs this model.
- **Kind:** execution model, run state and compiler output contract
- **Owner:** Workflow Lisp frontend and runtime
- **Created:** 2026-09-29. **Revised:** 2026-09-29, after gate G1.
- **Evidence:**
  [gate report](../reports/2026-09-29-evaluated-execution-spike.md), cited
  below as "gate report";
  [execution facts](../reports/2026-09-29-workflow-lisp-execution-facts.md);
  [value/effect separation decision brief](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md).
  The spike's reports for its three iterations and the three independent
  reviews are kept in the plan's working directory, outside the repository
  (gate report, §10); they are cited below as "spike iteration N"
- **Plan:** [evaluated execution plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md).
  Its decisions 5 and 7 fix the architecture and the scope of the first
  release; its decision 6, the number of the new target, is open.
- **Amends when the first release lands:**
  [core calculus middle-end](workflow_lisp_core_calculus_middle_end.md)
  (§10.1 constructs, §11.4 identity, §15 alternatives, §16 deferred work),
  `specs/state.md`, `specs/io.md`, `specs/cli.md`, `specs/versioning.md`,
  and the command boundary manifest of the
  [command adapter contract](workflow_command_adapter_contract.md)
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

Five rules follow.

| Rule | Statement |
| --- | --- |
| E1 | A value is the result of evaluating an expression. It has no step, no name in run state and no stored copy |
| E2 | An effect is identified by its site in its definition and the path of activations that reached it. Nothing else enters the identity |
| E3 | An effect runs only when the memo holds no committed result for its identity. A committed result is returned without running anything |
| E4 | What a reader sees as steps is a view derived from the memo and the program |
| E5 | An effect receives any transportable value as input, and returns one. A value does not have to be flattened to reach a command |

### 1.1 The first release

The owner's decision of 2026-09-29 (plan, decisions 5 and 7): evaluated
execution is built in stages, at a new target. The targets that exist today
keep the present route.

The first release covers four classes of effect: commands (external tools
and certified adapters), composed providers, calls of workflows and
procedures, and run references. Within composed providers it covers the
portable subset: no session, no context capture, no managed job, no secrets.
Every other class (trials, provider supervision, peer groups, phased
providers, adjudication, requests for human input, resource transitions,
materialized views, parallel map) and every form left out above enters
later, each with its own adapter and its own evidence through the public run
and resume entries. A program at the new target that uses a class or form
outside the release is refused at build with `closed_program_gap`, naming
the form and its source location.

The conditions of the gate report, section 6, bind the first release. Each
is a rule of this design.

| Condition | Rule |
| --- | --- |
| Invalidation covers every later committed effect, in journal order, until dependence through files is declared | C8, C9 |
| Every command boundary declares what it runs, even when that is nothing | C1 |
| What a command declares is read-only, and the run's interpreter is fixed for the run | C3, C4 |
| A view checks the terminal record against the settlements it implies | V3 |
| The request a provider or a command receives is a contract | R1 to R12 |
| Every form and every coordinator in the release has evidence through the public run and resume entries | K9, section 17 |
| Behaviour that depends on a file's modification time is outside any promise that binds bytes | C5 |

## 2. Problem

At run time a value exists only as the output of a step. The decision brief
states the consequences. Measurements since then:

| Evidence | Result |
| --- | --- |
| Totality matrix, 120 combinations of value form and position, after the shared defect repairs | 34 combinations typecheck and then fail. Every one needs a repair in code that serves only the flat step route |
| A search controller with a 14-field state, written five ways | Refused three times on the present route: the state update was 361 nodes against a bound of 256 (95 once bound values are shared in a payload); then a loop inside an `if` branch; then, in the compact form, a `let*` binding `parents` whose value is an `if` over two lists (`workflow_return_not_exportable`). An `if` over two records in a procedure called in a loop compiles and fails at run time with `pure_expr_payload_invalid`. On the spike the compact form, source unchanged, makes the decisions of its Python reference on 72 pairs of leaf scenario and budget (gate report, §2, criterion 2) |
| Rewrite of a review workflow with a library helper | A pure `match` over the helper's result is rejected; a nested `if` in a hook is rejected |
| Identity | Step ids, checkpoint ids and schema digests change when two blank lines are added or the file is moved (execution facts, A.5) |

The execution facts report lists 23 properties of the current system that an
evaluator would have to rebuild or that depend on steps being flat. This
design answers each. The gate report, section 3, lists eleven programs that
typecheck, that the present route refuses through its public entry, and that
the spike runs.

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
  first-class procedures, no recursion, a fixed effect vocabulary.
- Exactly-once effects in the world. An effect without a committed result
  runs again, unless its boundary declares `must_not_repeat`.
- Capturing or rolling back workspace files. A committed child run is
  therefore never superseded (C8, K8).
- Binding what a command reads beyond the files its boundary declares (C5).
- Changing YAML workflows or targets that exist today.

## 4. The Closed Program

The evaluator needs a program that is complete. Today part of what execution
needs is computed after the calculus, during lowering, and is keyed by step
name. The compiler therefore produces a closed program, with these
properties.

### 4.1 Properties

| # | Property | Today |
| --- | --- | --- |
| P1 | Whole program. The body of every `call` target is present once, specialized, in the table of definitions (§4.2). Nothing is elaborated after the program is built | Callee bodies are elaborated during lowering |
| P2 | Only calculus. No node holds a surface expression | Loop state, lists, `list/map`, `path/join-under`, bundle paths and several effect payloads are surface objects |
| P3 | Complete effects. Each effect node carries its operation class, its resolved target, its inputs as atoms, its result type, the output contract derived from that type, its prompt assembly, its policy, its declared closure (C1) and its repeat rule (`must_not_repeat`) | Contracts, result paths, prompt rows, policy rendering and timeouts are computed in lowering |
| P4 | Sites. The program carries a table of its effect sites: one per `perform` node of each definition, named by the definition and the local path. Two call sites of one procedure are two frames over one site (§6) | One node identity is shared by every inlined copy; an ordinal from a counter tells them apart |
| P5 | Checked form. A validator checks the normal form of the program when it is built: names in scope, `jump` and `continue` targets, a `continue` naming the loop it is in, unique sites, no recursive call, a budget on every loop, every operator payload valid | Only tests check it |
| P6 | Provenance. Every node keeps its source span and form path under one key. Provenance never enters an identity or the program digest | Spans and type text with file paths enter several identities |
| P7 | An artifact. The closed program is written as canonical JSON, with its site table and its representation version. Its digest, taken without provenance, is the program identity | No such artifact |

The spike supplied each of P1 to P7 outside the elaborator (gate report,
§4) and measured what the elaborator must change: attach normalized bodies
at `call` and `workflow_call`, elaborate `done` values and surface objects,
move contract, prompt and boundary resolution into elaboration, record the
declaring module on type definitions, and derive specialization names from
canonical identities. Each is at the new target only.

### 4.2 A table of definitions

The closed program is a table: the entry's parameters, defaults and body,
and one definition per canonical callee name, each body stored once. A
`call` names its callee and carries its call site as a frame. A site is
local to its definition. An identity at run time is the activation path
(the frames, with loop iterations filled in) and the local site (§6).

A canonical callee name is the qualified name of the procedure or workflow
with its specialization arguments given by the canonical identity of each
type: the declaring module and name, and the arguments, recursively. No file
path and no type text enters it.

Size evidence (gate report, §9.2; spike iteration 2, F, and iteration 3,
D3; 52 shipped workflows, 38 built):

| Program | Tree form, nodes | Table form, nodes |
| --- | --- | --- |
| `experiments/mlevolve_pair/search.orc` | 5,571 | 5,572 |
| `experiments/mlevolve_pair/search_compact.orc` | 4,065 | 2,574 |
| `workflows/experiments/repository_task_pilot/task_loop.orc` | 2,659 | 1,284 |
| `workflows/examples/kiss_backlog_item.orc` | 900 | 568 |
| A synthetic program, each level calling the next three times, depth 4 | 652 | 87 |

The tree form grows with call nesting; the table form is linear in the
source. On all 123 test programs the two forms name the same effects in the
same order. The table form is the one representation of the first release.

### 4.3 Constructs

The accepted calculus design lists ten constructs and requires an amendment
for each addition. The closed program has these:

| Construct | Role |
| --- | --- |
| `atom` | literal, name, field access, record construction, list construction, pure operator application |
| `inject` | variant introduction |
| `select` | conditional value; each arm carries a prefix of bindings and a value |
| `block` | a body evaluated for its value, where a value position holds control (a `match` held in a loop-state field) |
| `context` | a value the run supplies (§4.4): `run-id` |
| `result_path` | the result file of a committed effect, as a value (§4.4) |
| `let` | sequencing |
| `perform` | one effect |
| `call` | evaluation of a definition's body with the arguments bound |
| `case` | variant elimination |
| `if` | branch on a strict `Bool` |
| `join`, `jump` | second-class continuation |
| `loop`, `continue`, `done` | bounded iteration, with its budget and its exhaustion body |
| `par-map` | bounded parallel iteration over a list (§11; a later release) |
| `halt` | result |

Rules of elaboration into this form:

- `record_update` and `list_nonempty_head` are operators of the pure
  catalog, not constructs. Loop-state seeds elaborate to records, updates to
  `record_update`, variant tags to literals.
- A `halt` that reaches a `join` from the join's body is the join's value.
  This is how a loop in tail position of a join body gives its value.
- An effectful expression in an argument position (of a call, a workflow
  call, a command's argv or adapter document, a provider's input) is bound by
  a `let` before the call, in source order. The present route refuses this
  form as `compiler_defect`; the spike binds it and runs `(fetch (inc 4))`
  as `fetch 4` then `fetch 5` (spike iteration 3, D1).
- A `done` value that is an effect or a `match` is bound by a `let` before
  the `done`.
- A `continue` names the loop it is in; the elaborator's retargeting
  descends into joins.
- `phase-target` is elaborated at its `with-phase` site to the field access
  or path join it denotes (X3). The atom does not survive the normal form.

### 4.4 Values the run supplies

Four forms name something that only exists at run time. Each is a value in
the closed program, supplied by the evaluator, the same on every resume.

| Rule | Form | Value |
| --- | --- | --- |
| X1 | A call that leaves out a compiler-supplied `RunCtx` parameter | The record `{run-id, state-root: "state/run", artifact-root: "artifacts/run"}`, the present route's constants. `run-id` is the run's id, which is the run root's name (`specs/state.md`: `RUN_ROOT` is `.orchestrate/runs/<run_id>`). It is a `context` value; the run's identity reaches a program only this way (R1) |
| X2 | A call that leaves out a compiler-supplied `PhaseCtx` parameter | The record `{run: <the caller's RunCtx>, phase-name, state-root: state/<phase>, artifact-root: artifacts/<phase>}`, built at the call site from the caller's context value and the phase name, with the phase-scoped roots the [state layout](workflow_lisp_state_layout.md) derives. The closed program holds it as an ordinary record; no hidden parameter exists at run time. Its equality with the present route's value is an open evidence item (§19) |
| X3 | `phase-target` | The named target's field of the phase context in scope, or the path join `<artifact-root>/<phase>/<target>.md` for a generic `PhaseCtx`, elaborated at the `with-phase` site (§4.3) |
| X4 | `provider-bundle-path` | The committed attempt's result file, relative to the workspace (§8.2): a `result_path` value read from the memo, so it is the same on every resume. At the new target the form is typed as a path under the run root, so the value meets its root; both routes today type it under `state` and refuse their own value (`outside_under_root`) |

## 5. Values

A value is immutable and typed. The evaluator holds values in an environment:
a chain of frames, one per `let`, `case` arm, `join`, loop iteration and
`call`.

Pure operators have one implementation, the catalog of
`orchestrator/workflow/pure_expr.py`, applied to values. The typechecker reads
the same catalog. A pure operator that cannot produce a value, on overflow,
division by zero or a non-finite result, fails the run with a diagnostic
located at the expression, printing its operands.

No bound applies to the size of an expression. The bound of 256 nodes limits
a serialized payload, and no payload exists. Evaluation terminates because
the checked form (P5) refuses a recursive call and a loop without a budget.
There is no evaluation budget: the spike never needed one, and a budget
would guard against a defect the checked form already refuses.

The run's inputs are bound before anything is evaluated: declared defaults
applied, then each value checked against its declared type by the catalog's
coercion. The run's input digest is taken over the bound inputs. A missing,
undeclared or ill-typed input is refused before the run root holds a record.

## 6. Effect Identity

```text
identity        = (activation path, site)
site            = (definition, local path)
activation path = frames from the entry to the definition
```

| Rule | Statement |
| --- | --- |
| I1 | The site is the definition that contains the `perform` node and the path from the definition's body to it. Two call sites of one definition are two frames over one site |
| I2 | A frame is a call site, written `<binder>=<callee>` with the callee's canonical name (§4.2), a loop iteration `loop:<state param>[<i>]`, or, in a later release, a parallel map item `[<index>]` |
| I3 | The segments of a local path are: `then` and `else`; a `case` arm's variant; `loop:<state param>[*]` and its exhaustion body `exhausted`; a bound control construct's binder; and, last, the effect's own binder. The separator is ` / ` |
| I4 | An unnamed binder (a generated name) takes `#<k>`, its ordinal among the unnamed binders of its scope whose value performs an effect. Pure bindings take no ordinal, so a pure refactoring moves no identity. A repeated name takes `<name>#<k>` |
| I5 | An attempt is an ordinal under an identity. Attempts never change the identity |
| I6 | The canonical text of an identity is its presentation key: the entry, then each segment, with each `[*]` replaced by the iteration reached. Example: `run-search / loop:state[3] / repair=search::repair-one / propose` |
| I7 | The canonical text never names a file. A path derived from an identity uses a digest of the text (§8.2) |

Nothing else enters: no source span, no file path, no text of a type, no
position among steps, no visit count.

| Edit | Identity |
| --- | --- |
| Blank lines, comments, reformatting | Unchanged |
| The repository or the package moves | Unchanged |
| A pure binding is added, removed or renamed | Unchanged |
| A binder of an effect is renamed, or an effect moves to another branch | Changes |
| An unnamed effect is added before another in the same scope | The second changes. Naming the binding keeps it stable |
| A pure callee gains an effect | The caller's next unnamed effect changes; named effects do not |

Evidence: identities and the program digest are unchanged under blank lines,
under a move of the program and under a move of the orchestrator package;
the ordinal rule's moves are measured against the alternative (gate report,
§2, criterion 5; spike iteration 2, F(c)).

## 7. The Effect Memo

### 7.1 The journal

| Rule | Statement |
| --- | --- |
| M1 | The memo is an append-only journal of JSON lines under the run root, `memo.jsonl`. One writer holds an exclusive lock on it for the life of a run or resume. A second writer is refused with `memo_busy` |
| M2 | Each record is written and synchronized to disk before the evaluator proceeds. The run root's directory is synchronized after the journal is created |
| M3 | A final line without its newline was never written whole and is not a record. The next writer truncates it before appending |
| M4 | A result exists only as a `committed` record that no later `invalidated` record cancels. A file at a path, however valid and however recent, is not one |
| M5 | The `committed` record holds the validated value inline, beside the result file's path and digest. The value is the authority; the file is evidence |
| M6 | A command that writes to the memo from outside a run (the answer of a request for input, an invalidation) takes the writer's lock and appends under it |

| Record | Written | Content |
| --- | --- | --- |
| `started` | Before an attempt is launched | identity, attempt ordinal, digest of the resolved input and of each of its parts, result path, time |
| `committed` | After the result passed its contract | identity, attempt ordinal, input digest and parts, the validated value, result path and digest, the digests of the declared files (C2), the identities its input read (C9), the coordinator's proof when there is one (K5), time |
| `failed` | After an attempt ended without a valid result | identity, attempt ordinal, code, exit information, the contract violations if any |
| `suspended` | When an effect waits for a person (a later release) | identity, attempt ordinal, the request |
| `settled` | After a coordinator's final commit (`by: settle`), or its reconciliation on a memo hit (`by: reconcile`) | identity, attempt ordinal |
| `invalidated` | By the explicit continuation (C8) | identity, attempt ordinal, the effect chosen |
| `terminal` | Last, after every effect reached is committed and every coordinator effect is settled | no identity; `completed` with the value of `halt`, or `failed` with the code and message |

Any record after a `terminal` record means the run went on: a resume after
an invalidation, or a resume of a run whose terminal record said `failed`.

`state.json` stays. For this profile it is a view (§10), rewritten from the
memo after each record. It is not the authority for any result.

### 7.2 The resolved input

The resolved input of an effect is everything that determines what the
effect is asked to do: its arguments, its assembled prompt with the digests
of the prompt asset and of every file the prompt reads, its contract, its
provider binding with the policy in force, and for a command the digests of
what it declares (C2). Its digest, and the digest of each part, enter the
`started` and `committed` records. A divergence names the parts and the
files that differ.

### 7.3 What a command boundary declares

| Rule | Statement |
| --- | --- |
| C1 | Every command boundary in the manifest declares its implementation closure in the field `closure`: the files and directories its stable command runs, beyond the tokens of the command itself. An empty list is a declaration. A boundary without the field is refused at build with `command_boundary_closure_missing`. No build option weakens this rule |
| C2 | The resolved input of a command binds, by content: each stable-command token that names a workspace path, and each closure entry. A file is bound by its content digest; a directory by the digest of its files' sorted relative paths and digests; a path through a symbolic link also by the path it resolves to. Modification times are not bound |
| C3 | The interpreter, the first token of a stable command when it is a bare name, is resolved on `PATH` once, when the run starts. The run header records its resolved path and digest. Every attempt of the run launches the resolved path, not the name. The interpreter does not enter any effect's resolved input: a changed digest at resume is reported as `interpreter_changed` and the run continues on the recorded path; a missing path refuses the resume with `resume_interpreter_missing` |
| C4 | A closure is read-only. A resume that finds a declared file changed refuses at that effect (C7), whoever changed it. Caches and outputs live outside every closure. Commands are launched with `PYTHONDONTWRITEBYTECODE=1` |
| C5 | Outside the promise: modification times; the environment; a file opened by a computed name or imported without declaration; the network; the clock; the provider template behind a provider id and the model behind it; workspace files no boundary declares. A command whose behaviour depends on one of these may be reused with a result no fresh run would give. The promise binds bytes of declared files, nothing else |
| C6 | A provider's prompt asset and its prompt dependency files are always bound by content digest |
| C7 | A changed manifest or stable command changes the program identity: the resume is refused with `resume_program_changed` before any record is read. A changed bound file diverges only the effects that bind it: the resume stops at the first committed one, in journal order, with `effect_input_diverged`, before any launch |

The spike's evidence for C1 to C5 is its five-case table (spike iteration
3, B): with the closure declared, a changed second script, a changed
directory, a changed `PATH` program and a retargeted symbolic link
each refuse; a change of modification time alone reuses. Without a
declaration, the second script was reused silently (gate report, §6);
C1 makes the declaration required. The spike bound the interpreter per
effect, which made an upgrade refuse every resume (gate report, §6); C3
fixes it for the run instead. The spike offered `declared`, `strict` and
`trusting`; this design keeps one rule, C1, because an option that reuses
undeclared work is the defect the last review found.

## 8. Evaluation And Resume

### 8.1 What the memo decides

Evaluation of `perform` at identity `i` with resolved input `x`:

| Memo holds for `i` | Action |
| --- | --- |
| A committed result with input digest equal to the digest of `x`, not invalidated | Return the result. Run nothing. For a coordinator effect, `reconcile` first (K3) |
| A committed result with another input digest | Stop with `effect_input_diverged`, located at the site, showing both digests, which parts of the input differ and which files |
| A `started` or `failed` attempt, no commit, not invalidated | If the boundary declares `must_not_repeat`, stop with `lexical_restore_pending_effect_unsafe`. Otherwise record `effect_rerun`, naming the identity and its earlier attempts, and run the next attempt |
| An `invalidated` record after the last commit | Run the next attempt. No rerun diagnostic |
| A `suspended` record and no commit | Stop and report the pending request |
| Nothing | Run the first attempt |

`must_not_repeat` is the manifest field that exists today
(`specs/state.md`; command adapter contract). The spike stood in for it with
a build option; the field is the declaration.

### 8.2 Running an attempt

1. Derive the attempt's directory from a digest of the identity and the
   attempt ordinal, under the run root:
   `effects/<digest of the identity>/attempt-<n>/`. Create it exclusively. A
   directory that already exists fails the attempt with
   `effect_attempt_path_exists`.
2. Append `started`.
3. Launch through the performer of the effect's class (§9.2), or through
   the coordinator's `prepare` (§9.3), with the result path
   `<attempt directory>/result.json`.
4. Validate the result against the contract. Project it to the declared
   type: undeclared keys are dropped.
5. Append `committed`, or `failed`. For a coordinator effect, then `settle`
   and append `settled`.

The file of an earlier attempt is never removed or overwritten. Each attempt
has its own directory, so the evidence of a failed attempt stays beside the
result of the one that succeeded. The attempt directory also holds the
attempt's `stdout.txt`, `stderr.txt` and, for a provider, `prompt.txt` (V6).

A failed attempt stops the run, as `on_error=stop` does today: the memo gets
the attempt's `failed` record and a `terminal` record with outcome `failed`.
A resume runs the next attempt.

### 8.3 What a stop leaves, and what resume does

| The process stops | The memo holds | Resume |
| --- | --- | --- |
| Before `started` is written | Nothing for this attempt | Runs the attempt |
| While the effect runs, or while it writes its result | `started` | Treats the attempt as one without a committed result. A partial file does not parse or does not validate, so it is never a result |
| After the effect finished and before `committed` is written | `started`, and a complete result file | Same as above: the file is evidence, not a result. Only `committed` makes a result |
| After `committed`, before a coordinator's `settle` | `committed` with the proof | Returns the result; `reconcile` completes the coordinator's commit (K3) |
| After `committed` | `committed` | Returns the result |

Resume is evaluation from the entry with the memo of the run. Because
evaluation is a function of the program, the inputs and the committed
results, it reaches the same effects in the same order up to the first effect
without a commit. Evidence: 168 stops inside the process and 96 kills from
outside, each resumed to the uninterrupted value with no committed effect
run twice (gate report, §2, criterion 3).

### 8.4 The run header and the representation

The run root holds `run.json`, written before the first record: the program
digest, the input digest, the bound inputs, the representation version of
the closed program (§4.2), and the interpreters fixed for the run (C3). The
program artifact is written beside it. A resume reads the program from the
artifact and refuses before any record is read when the program digest
differs (`resume_program_changed`) or the inputs differ
(`resume_inputs_changed`).

The representation is part of the program identity. A run started under one
representation is finished, resumed or abandoned under it; a memo is never
converted. The first release ships one representation, the table form, so
the rule bites only when a later release changes the form: then a run in
flight completes on the release that started it.

### 8.5 Explicit continuation after a divergence

A resume that stops with `effect_input_diverged` does not rerun anything.
The continuation is explicit.

| Rule | Statement |
| --- | --- |
| C8 | `invalidate <run> <identity>` appends one `invalidated` record for the chosen effect and for every later committed effect, in journal order. The next resume runs exactly those again; every earlier commit stays. The operation is refused while a writer holds the memo (`memo_busy`), when the chosen effect has no commit (`invalidate_not_committed`), and when the suffix holds a committed coordinator effect (`invalidate_coordinator_committed`): a committed child run is never superseded (K8) |
| C9 | Each `committed` record keeps `depends_on`: the identities whose results its resolved input read, through names, arguments, results, loop state, join parameters, `case` bindings and the conditions that chose a value; an effect inside a branch does not depend on the branch's condition. In the first release this is evidence, not the scope of an invalidation: a dependence through a file, where one effect writes a path that a later one reads, leaves no trace in values, and a shipped workflow has that shape (`workflows/library/verified_iteration_drain/drain.orc`). Narrowing an invalidation to dependents through values and declared files is a later release, entered when command boundaries declare the files they read and write, with the file-dependence fixture of §17 as its evidence |

The spike followed values only and reran one of two file-dependent effects,
mixing old and new results (gate report, §6); C8 is the last review's
rule. A changed program file that diverges several effects needs one
invalidation, at the first: the suffix covers the rest.

## 9. Effect Inputs, Performers, Coordinators And Requests

### 9.1 Inputs

An effect takes values. Any transportable value is admitted: scalars,
records, unions, lists, optionals and paths, nested to any depth.

| Value | How a command or provider receives it |
| --- | --- |
| A value in `:argv` | Rendered as the present route's variable substitution renders it: a string as itself, a number as its decimal text, a `Bool` as `true` or `false`, a record or list as JSON with the substitution's spacing (`json.dumps` defaults), keys in the value's order. Both routes give the same argv bytes (spike iteration 3, F) |
| A certified adapter's inputs | One JSON object, fields in signature order, as the last argv token, as today. The document carries the declared inputs only, each projected to its declared type |
| Any value bound in `:inputs` (Phase 3 of the plan) | One typed input document in JSON, written in the attempt's directory. The command receives the path. The document is validated against the declared types before launch |
| A value that is large, or that a person should be able to read | A materialized view (a later release). The effect receives the path of the view |
| A prompt fill | As the prompt calculus defines: the `defprompt` template with each fill rendered by its renderer, then the typed prompt inputs, each named by its last field and rendered by the default renderer |

Every document an effect receives is serialized deterministically. Its
digest is part of the resolved input (§7.2). The document carries values;
it carries no run state and no path of the orchestrator's private
directories.

A file that carries data to an effect is a representation of a value. It is
never read back to decide what the workflow does next. The workflow decides
from values in the environment and from committed results.

An expression in an argument position is evaluated like any other. The author
does not have to find a name that happens to hold the same value.

### 9.2 Performers

A performer executes one class of effect. It receives the effect node of the
closed program, the resolved input, the result path and the workspace. It
returns a result or a failure. It reads no run state and writes none. A
coordinator (§9.3) is a performer with a ledger of its own.

| Class | First release | Performer built from | Notes |
| --- | --- | --- | --- |
| Command | Yes | `StepExecutor.execute_command` | Independent of the executor today |
| Provider, composed delivery, portable subset | Yes | `ProviderExecutor.prepare_invocation` and `execute`, with prompt assembly moved out of the executor | The prompt is assembled as the present route assembles it, with the differences of R2 and R3 only (spike iteration 2, B) |
| Workflow or procedure call | Yes | None. A call is evaluation | No child executor and no call frame |
| Run reference, path mode | Yes | The run-ref runtime, unchanged, behind the coordinator protocol (K7) | The child run is a separate run in its own workspace |
| Run reference, bundle mode | Later | The same runtime; the capsule is the child's closed program, built by the parent's build | |
| Request for input | Later | New | `suspended`, then `committed` by the answer command (M6) |
| Resource transition | Later | `execute_transition` | Independent today. Its idempotency key stays |
| Materialized view | Later | The existing step function | Reads its value from the environment |
| Trial | Later | The trial runtime behind the coordinator protocol | Has the pair of commits today (K6) |
| Provider, phased delivery; supervision; peer group; adjudication | Later | The existing coordinators, each changed to expose the pair of commits (K6) | One effect, one identity, its own ledger |

A program at the new target that uses a class marked later is refused at
build (§1.1). At older targets it runs as today.

### 9.3 Coordinators

A coordinator runs an effect that has a ledger of its own and a child that
the run must never start twice. Today each coordinator commits into the
run's state; the memo replaces that commit.

| Rule | Statement |
| --- | --- |
| K1 | A coordinator receives the effect node and the resolved input as values, keeps its ledger under the run root, and reads and writes no run state |
| K2 | The protocol has three calls. `prepare(node, resolved, identity, attempt)` runs the effect to the coordinator's pending commit and returns the value and a proof. The evaluator validates the value and appends `committed` with the proof. `settle(node, identity, proof)` makes the coordinator's final commit; the evaluator then appends `settled` |
| K3 | On a memo hit, `reconcile(node, resolved, identity, proof)` completes a pending final commit from the proof, and the evaluator appends `settled` (`by: reconcile`) when the memo lacks it |
| K4 | The memo's `committed` record lies between the coordinator's two commits. Killed after the pending commit, resume discards the pending attempt and starts one more child; killed after the memo's commit, resume starts none. A coordinator that makes its final commit before the memo's is a defect: killed between the two, the run cannot continue (spike iteration 2, D1) |
| K5 | The proof is the coordinator's settled result record and its artifacts, stored inline in the `committed` record. It is what `settle` and `reconcile` need, and nothing else |
| K6 | Which coordinators have the pair of commits today, and which must change, by the inventory of the execution facts, B.1, and the gate report, §7: run references (pending ledger record, final commit, reconcile call) fit unchanged; trials (prepared and final parent settlement) fit and need an adapter; phased providers make one authoritative commit, supervision and peer groups finalize directly into parent state, adjudication's parent result is committed by the caller, and human input commits reply and result together into `state.json`. Each of these five must give that up and expose `prepare`, `settle` and `reconcile` before it enters a release |
| K7 | A run reference: its static configuration is built at build time, each input bound as the reference `inputs.<name>`; the name rule of the child's inputs is the reference rule, so no valid name is unsafe. The coordinator resolves the references against a parent state that holds only the resolved input values. The visit key is derived from the identity: parent run id the run root's name, execution frame `root`, no call frame, step id `root.<digest of the identity>`, visit count 1. The runtime's ledger, `run-ref-attempts.jsonl`, is unchanged |
| K8 | A committed coordinator effect is never superseded in the first release: no new visit key or attempt for an identity that committed through a coordinator, and no rollback of the child's workspace delta (§3) |
| K9 | Every coordinator in a release has evidence through the public run and resume entries: a compiled program killed from outside at each of its two gaps, resumed to the uninterrupted value, with no committed child started twice, and refused before any launch after a declared file changes |

The run reference was shown this way, compiled from `.orc` source, with two
commands and a provider beside it (gate report, §5; spike iteration 3, E).
The owner's experiment beside the next phase runs one shipped workflow with
a coordinator that is not a run reference, through both routes; K1 to K5
are the rule it tests.

### 9.4 The request contract

A request is what a provider or a command receives. Each field has one
value, given by a rule. A field not listed here is equal on both routes.

| Rule | Field | Value |
| --- | --- | --- |
| R1 | `provider.context` | Empty. A request carries no run state: no run id, no timestamp, no run root, no inputs, no steps. A provider template that names a run variable fails the attempt as a missing placeholder does today. The run's identity reaches a program only as the `RunCtx` value (X1) |
| R2 | `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, in the environment of a provider and of a command | The attempt's own result path (§8.2), relative to the workspace, as the present route gives its path |
| R3 | The prompt's `- path:` line, in the output contract block | The same path as R2. Nothing else in the prompt differs from the present route's assembly |
| R4 | `provider.prompt_content` | Assembled in this order: the prompt asset or the rendered `defprompt` template; the typed prompt inputs; the prompt dependencies, at the position the declaration gives; the output contract block, rendered by the runtime's own renderer |
| R5 | `ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY`, in the provider's environment overlay | `sha256:` and the digest of the identity's canonical text. The same across attempts and resumes, present inside call frames as well; the present route sends none inside a call frame |
| R6 | `provider.cwd` | The workspace, named. The present route inherits the orchestrator's working directory |
| R7 | `provider_call_policy` and `timeout_sec` | The effect node's policy: `model`, `effort`, `timeout_sec` |
| R8 | `params`, `session_request`, `provider_session_dir`, `provider_session_identity`, `secrets` | The parameters the effect node declares; none of the others in the first release (§1.1) |
| R9 | `command.command` | The stable command tokens, the interpreter replaced by its resolved path (C3), then the rendered argv (§9.1), then for a certified adapter the input document |
| R10 | `command.env` | R2 and `PYTHONDONTWRITEBYTECODE=1` (C4) |
| R11 | Generated helper commands | None. The present route runs inline Python steps that write managed write roots under `.orchestrate/workflow_lisp/`; the model has no write roots and no call frames, so nothing writes them |
| R12 | A value in a command argument | Rendered as §9.1 states; equal to the present route's bytes |

Evidence: the two routes' requests were compared field by field without
normalising, on the `std/improve` example, the two single-call workflows and
the decisive program; every difference is one of R1, R2, R3, R5, R6 and R11,
with the value its rule gives (spike iteration 3, F).

## 10. Views

Readers of run state depend on rows named by step, on one current step and
on order. For this profile the runtime derives views by these rules.

| Rule | Statement |
| --- | --- |
| V1 | A view is derived from the memo and the program. Rows come from the records. The run's position comes from evaluating the program against the memo without launching anything: a `halt` value leaves no record before the terminal record, so a projection of the memo alone cannot say where the run stands |
| V2 | The run's status: `completed` or `failed` when the last record is `terminal`; otherwise `settling` when a writer holds the lock and every effect the program reaches is committed; otherwise `running` when a writer holds the lock; otherwise `interrupted`. A later release adds `suspended`, for a pending request |
| V3 | A `terminal` record is checked against the settlements it implies: every coordinator effect committed before it must have a `settled` record before it. A memo whose terminal record fails the check is reported as `memo_inconsistent`, with the identities missing a settlement, never as completed. When two terminal records exist with no other record between them, the memo is inconsistent too |
| V4 | Liveness comes from the writer's lock, not from a heartbeat: a process that died released it, and the view says `interrupted` at once. The present report says `running` until a heartbeat is 300 seconds old |
| V5 | `steps`: one row per effect identity, keyed by its canonical text, in order of first `started`. Status, result, error and timing come from the records: `running` from `started`, `completed` from `committed`, `settling` for a coordinator effect between `committed` and `settled`, `failed` from `failed`, `invalidated` from `invalidated`. `current_step` is the effect in flight; `next_effect` is the first uncommitted effect when nothing is in flight. `workflow_outputs` is the terminal record's value |
| V6 | Per-attempt files live in the attempt's directory (§8.2): `result.json`, `stdout.txt`, `stderr.txt`, and `prompt.txt` for a provider. A row's output preview reads them. Nothing is named by step name; nothing is overwritten by a later attempt |
| V7 | The memo does not carry, and the view does not report: `step_visits`, `transition_count`, `call_frames`, the prompt-context audit, judgment views, observability summaries, provider sessions and observation files, the heartbeat. The readers that need them (the resume planner, the projection integrity audit, the dashboard cursor's frame walk, the human-input guard, the prompt session lookup, the monitor email's log lookup by step name) are not used at the new target, or are adapted to V6 when their class enters. Sessions and observation files enter with the classes that need them, named by identity digest and attempt |
| V8 | A view launches nothing and may be taken while the writer holds the lock. Its cost is linear in the memo: 0.17 seconds for 5,000 effects (gate report, §5) |
| V9 | `state.json` is rewritten from the memo after each record. It carries the header keys `RunState.from_dict` requires (`schema_version`, `run_id`, `workflow_file`, `workflow_checksum`, `started_at`, `updated_at`, `status`). Readers that read only those, `error`, `workflow_outputs`, `bound_inputs` and `steps[*].status` (the monitor classifier, the watchdog probe, the usage-limit watcher, the trial SDK; execution facts, C.2) are served by it. `orchestrator report` renders the view through its present state-only projection |

The spike's view reproduced the present report's rows for a run killed
during its second command, and said `interrupted` where the present report
said `running` (gate report, §5; spike iteration 2, D2). A hand-edited memo
with a terminal record and no settlement was reported as completed (gate
report, §6); V3 is the last review's rule.

## 11. Parallel Effects

`par-map` is a later release (plan, Phase 5). Its rules are fixed here so
that identity and the memo need no change when it enters.

`par-map` evaluates a body once per item of a list, with at most `n` items in
evaluation at a time.

- Each item's body is evaluated in sequence. Items are independent.
- Identity includes the item index (I2), so it does not depend on which
  item finishes first.
- The result is a list in the order of the input.
- One writer appends to the memo (M1). Evaluations send it records; they
  never write.
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
- `effect_input_diverged` prints which parts of the resolved input differ
  and which declared files, not only that something does.

Codes this design introduces or keeps, and where each is raised:

| Code | Raised |
| --- | --- |
| `closed_program_gap` | At build: a form or effect class the closed program cannot express in this release (§1.1) |
| `command_boundary_closure_missing` | At build: a boundary without a `closure` field (C1) |
| `workflow_input_missing`, `workflow_input_unknown`, `workflow_input_invalid` | Before the run root holds a record (§5) |
| `resume_program_changed`, `resume_inputs_changed`, `resume_interpreter_missing` | At resume, before any record is read (§8.4, C3) |
| `interpreter_changed` | A diagnostic, not a refusal, at resume (C3) |
| `memo_busy` | A second writer (M1, C8) |
| `memo_inconsistent` | A view whose terminal record fails its check (V3) |
| `effect_input_diverged` | At the first committed effect whose input differs (§8.1) |
| `effect_rerun` | A diagnostic in the run's result and the view, naming the identity and its earlier attempts (§8.1) |
| `lexical_restore_pending_effect_unsafe` | An uncommitted attempt of a `must_not_repeat` boundary (§8.1); the present code, kept |
| `effect_attempt_path_exists` | An attempt directory that exists before the attempt (§8.2) |
| `invalidate_not_committed`, `invalidate_coordinator_committed` | The explicit continuation (C8) |
| `parallel_workspace_shared` | A later release (§11) |

## 13. Targets And Compatibility

- Evaluated execution applies from one new target, whose number is decision
  6 of the plan, still open. A program at that target runs on the evaluator
  only.
- Programs at targets that exist today compile and run as they do, with
  byte-identical build artifacts.
- A run started under one profile is resumed under it; a run started under
  one representation of the closed program is resumed under it (§8.4).
- A module at the new target may import a module at an older target when the
  imported definitions use only forms the closed program can express. The
  import is compiled under the new target's rules.
- A module at an older target may not call a module at the new target. The
  two run on different runtimes.
- The command boundary manifest gains the field `closure` (C1). At older
  targets the field is accepted and ignored.

## 14. What Is Preserved

| Guarantee | How |
| --- | --- |
| A result is validated before it becomes canonical state | Step 4 of §8.2, before `committed` |
| No committed provider call or child run runs again | Rule E3; K2 to K4 for a coordinator |
| A changed source is refused before any mutation | Program identity (§8.4); a changed declared file, before any launch (C7) |
| Effect sites are known before a run | The site table, P4 |
| Wrong-path writes fail closed; stdout is not a result channel | The performer reads only its result path |
| Refusals name their rule | §12 |
| One run at a time in a workspace | The workspace lock; one writer per memo (M1) |
| Runs can be inspected from the filesystem | The memo, the attempt directories and the derived views are files |
| `must_not_repeat` stops a resume at an uncommitted effect | §8.1, the present code |

## 15. What The New Target Does Not Use

Defunctionalization to steps, the older lowerers, positional resume, the
projection integrity audit, lexical checkpoints, pure projection steps, the
pure-result replay index, managed write roots, generated helper commands,
call frames in run state, and the rule that structured control is top-level
only. They stay in the repository for older targets.

## 16. Alternatives

| Alternative | Decision | Reason |
| --- | --- | --- |
| Repair the flat route position by position | Rejected at gate G1 | Four rounds of repair on one class of defect and 34 of 120 matrix cells still failing (gate report, §8). Every remaining defect has a second layer under it |
| Keep flat steps and evaluate pure expressions on demand | Not chosen | Removes the producer rule. Keeps defunctionalization, positional resume and one iteration ordinal per key |
| Restore a serialized environment at a checkpoint | Not chosen | Needs every value to be serializable at every point and an identity for every program point. Evaluation from the entry needs neither |
| Journal replay of arbitrary code | Rejected in 2026, and still | This design is not that. The language is closed, sites are listed before a run, every memo hit is checked against the input, and no effect runs unless the memo lacks its result |
| A workflow library in a host language | Rejected | Loses checks before a run and the bound on what an authored workflow can do |
| A closed program as a tree, one callee body per call path | Not chosen | Grows with call nesting: 652 nodes against 87 at depth 4 (§4.2). The table names the same effects |
| Invalidation by value dependence alone | Not chosen for the first release | Misses a dependence through a file (C9) |
| Binding the interpreter per effect | Not chosen | An upgrade of an ambient tool refuses every resume (C3) |

Two measures on the flat route were taken in Phase 0 of the plan and do not
change this design: a bound value shared in a pure payload, and a result path
per call that does not exist before the call.

The earlier rejection of journal replay gave three reasons: static effect
visibility, validation before commit, and parity evidence that a machine can
compare. The first two are kept by P4 and by §8. The third changes.
Evidence of parity between the two routes is behavioral: for the same
program, inputs and effect results, the same ordered effect identities, input
digests, result digests and final value, and a request equal field by field
apart from R1 to R12.

## 17. Evidence Requirements

Each requirement holds for the first release through the public run and
resume entries. Where the spike met it, the reference is the measure to
repeat.

| Requirement | Measure | Spike |
| --- | --- | --- |
| Totality | Every cell of the totality matrix that typechecks runs. No known defect remains at the new target. The matrix covers each form written directly, through a helper of the same module, and through an imported helper | Met on 100 typechecking cells of 120, the 32 the present route fails among them (gate report, §2, criterion 1) |
| Real programs | The `std/improve` example and the two workflows of the single-call comparison run to their expected result, unchanged in source apart from the target | Met with stand-in providers (gate report, §2, criterion 1) |
| The search controller | The MLEvolve-inspired controller makes the decisions of its Python reference, in the same order, with the same budget spent, and returns the same result. Its form is the compact one, with one helper for both branches | Met on 72 pairs of leaf scenario and budget (gate report, §2, criterion 2) |
| Growth | Doubling the fields of the controller's state and the number of its branches leaves it running. No limit depends on the size of an expression | Open |
| Structured inputs | A command receives a candidate record and the list of earlier trials, with their types, and rejects a document of another shape | Open: typed input documents are Phase 3 of the plan (§9.1) |
| Nesting | A loop in a branch, a loop in a loop, and a branch in a hook run | Met (gate report, §3) |
| Resume | For each real program, killing the process from outside in each window of each effect and resuming gives the final value of the uninterrupted run, with no committed effect run twice | Met: 96 kills (gate report, §2, criterion 3) |
| Identity | Adding blank lines, and moving the program and the package, change no identity | Met (gate report, §2, criterion 5) |
| Sites | For every run, the identities in the memo are instances of sites in the site table, split into frames and a local site | Met (gate report, §2, criterion 6) |
| Parity | On programs both routes accept, the effect traces are equal and the requests are equal apart from R1 to R12 | Met on 68 matrix cells, the shipped examples and a reduced decisive program (gate report, §2, criterion 7) |
| Older targets | Byte-identical build artifacts | Open: held by construction in the spike, no byte comparison run |
| A dependence through a file | Command A writes a path that command B reads by a fixed name, with no value between them. After A's input changes and `invalidate A`, the resume gives the value of a fresh run, and B ran again | Failed on the spike's value-only rule; C8 is the rule to test |
| A writable closure | A command whose declared closure gains a bytecode cache during a run resumes without a refusal, and a changed authored script in the same closure refuses | Open; the spike showed the refusal without C4 |
| The interpreter fixed for the run | After the `PATH` resolution of `python` changes between stop and resume, the resume runs on the recorded path, reports `interpreter_changed`, and refuses nothing | Open; the spike refused (gate report, §6) |
| An undeclared closure | A boundary without a `closure` field is refused at build, and a wrapper whose second script changed is never reused | Met for the refusal under `strict` (spike iteration 3, B); C1 makes it the only rule |
| A terminal record without its settlements | A memo with a terminal record and a coordinator commit lacking `settled` is reported `memo_inconsistent`, with no outputs | Failed on the spike (gate report, §6); V3 is the rule to test |
| A coordinator other than a run reference | One shipped workflow with such a coordinator runs through both routes; at the new target it is killed at both gaps (K9) | The owner's experiment beside Phase 2 |
| The request contract | Every field of every request compared without normalising; a field not in R1 to R12 is equal | Met (spike iteration 3, F) |

## 18. Feasibility Obligations

Each claim is an open prerequisite until its fixture passes.

| Claim | Fixture | Spike |
| --- | --- | --- |
| The closed program can be built for the corpus | P1 to P7 hold for every workflow of the repetition census corpus whose classes are in the release | 38 of 52 shipped workflows built; the 14 others use a class outside the first release, a context form (X2, X3), a capability no provider declares, or do not typecheck (gate report, §7) |
| A lexical path distinguishes every effect site, across inlined copies | A procedure with one effect, called from three arms of one `match`, in a loop | Met (gate report, §2, criterion 6) |
| Prompt assembly can run outside the executor | The assembled prompt of the `std/improve` example equals the one the flat route assembles, apart from R3 | Met for assets, templates, typed inputs and the contract block; open for the rendering of prompt dependency snapshots |
| Evaluation is a function of program, inputs and committed results | Two evaluations with one memo give the same trace and launch nothing the second time | Met (spike iteration 1, commit `92d47fe0`). Open: path existence checks, variant selection by workspace digest and secrets are each an effect or part of a resolved input; secrets are not designed |
| The views satisfy their readers | `orchestrator report`, the monitor classifier and the watchdog probe read a state derived from a memo (V9); the dashboard cursor reads it without call frames | Met for the report's rows and status (spike iteration 2, D2); open for the others |
| A coordinator can run behind the protocol with its runtime unchanged | A compiled run reference, killed at both gaps | Met (spike iteration 3, E) |
| The context forms have a closed value equal to the present route's | One program per form (X1 to X4), run on both routes | Met for X1 and X4; X2 and X3 open |
| Non-finite numbers cannot reach an input digest | The numeric surface's boundary rule, implemented at target 2.34 | Owned by the [numeric surface](workflow_lisp_numeric_surface.md) |
| A typed input document can carry records, unions and lists | One command that receives a list of records of unions and returns it unchanged | Open: Phase 3 of the plan |
| The checked form refuses a tampered type | A value's type changed in a closed program artifact is refused when the artifact is read | Open |

## 19. Decisions Still Open

Every decision of the spike's list of 38 is made above. What remains is the
owner's, or needs an experiment.

| # | Question | Answered by |
| --- | --- | --- |
| 1 | The number of the new target | The owner: plan, decision 6. A new major number, because the run state profile and the runtime change |
| 2 | When older targets are retired | The owner: plan, decision 8. After the maintained workflows run at the new target |
| 3 | Whether K1 to K5 hold for a coordinator that is not a run reference | The owner's experiment beside Phase 2: one shipped workflow with such a coordinator, through both routes |
| 4 | Whether the compiler's `PhaseCtx` (X2) and `phase-target` (X3) values equal the present route's | One program per context form, run on both routes, with the equality asserted on the values (§18) |
| 5 | Whether prompt dependency snapshots render as the present route renders them | The two routes' prompts compared on a workflow with prompt dependencies (§18) |
| 6 | When invalidation may narrow to dependents through values and declared files (C9) | A later release, when command boundaries declare the files they read and write, tested by the file-dependence fixture of §17 |
| 7 | How sessions, observation files and secrets are named and resumed | Not designed. Each enters with the class that needs it, with its own evidence (§1.1) |
