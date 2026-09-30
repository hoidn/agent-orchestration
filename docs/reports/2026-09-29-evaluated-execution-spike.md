# Evaluated Execution Spike: Report For Gate G1

## Metadata

- **Date:** 2026-09-29
- **Kind:** evidence record for one decision of the owner
- **Decision:** gate G1 of the
  [evaluated execution plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md):
  repair the present execution route, or build evaluated execution
- **Design under test:**
  [evaluated execution](../design/workflow_lisp_evaluated_execution.md)
- **Spike code:** `experiments/evaluated_execution_spike/`, tests in
  `tests/experiments/test_evaluated_execution_spike*.py`. Throwaway. Nothing
  under `orchestrator/` was changed by it
- **Branch:** `feat/orc-phase0`

## 1. Summary

The spike ran in three iterations. After each, a reviewer of another model
family attacked it with programs of its own. Each review asked for changes.
The last one gives this judgment: build the model, with conditions.

| Question | Answer |
| --- | --- |
| Does evaluation with an environment of values and a memo of effects run the programs that the present route refuses? | Yes, for every program tried that typechecks and whose effects the spike can perform |
| Does resume give the uninterrupted result, with no committed effect run twice? | Yes, at every point where a process was killed, for commands, providers and one coordinator |
| Is the evaluator small? | Evaluator and memo are 625 lines |
| Is the model proven for production? | No. Two rules of resume are unsafe as the spike has them, five coordinators have no adapter, and 14 of 52 shipped workflows do not build |
| What would the present route need to reach the same programs? | A repair per form and per position. The repairs plan shows the rate: four rounds on one class of defect, and 34 of 120 cells still failing |

Recommendation: build evaluated execution, in stages, at a new target, with
the conditions of section 6 met before its first use on a real run. Keep the
present route for the targets that exist.

## 2. What Was Tested

The criteria were fixed in the plan before the spike started.

| # | Criterion | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Every fixture that typechecks evaluates | Pass, with a limit | The 100 cells of the totality matrix that typecheck, the 32 that the present route fails among them; the six programs of the decision brief; a loop in a branch, a loop in a loop, a nested `if` in a hook; the `std/improve` example. Limit: 38 of 52 shipped workflows build |
| 2 | The search controller makes the decisions of its Python reference | Pass | The compact controller, source unchanged, on 72 pairs of leaf scenario and budget. The first fixture did not expose a defect of the controller's source; the first review did, and the source was repaired |
| 3 | Interrupt after each effect, resume, same result, no committed effect twice | Pass | 168 stops inside the process; then processes killed from outside at each window of each effect: 68 in the first decisive experiment, 28 in the second. The reviewers killed their own |
| 4 | A valid file left by an attempt that did not commit is never a result | Pass | Each attempt has its own result path; the file of an interrupted attempt is not read |
| 5 | Identity unchanged under blank lines and under a move of program and package | Pass | Also checked: identity or program digest DOES change when an effect's meaning changes |
| 6 | Every identity in a memo is an instance of a site listed before the run | Pass | Checked on every run of every test |
| 7 | Parity with the present route on programs it accepts | Pass, with named differences | Equal values and ordered effects on 68 matrix cells and the shipped examples. Requests compared field by field; eight fields differ, each by a stated rule, and the present route runs helper commands that the program does not contain (section 6) |
| 8 | Evaluator and memo under 2,000 lines | Pass | 625 lines. The whole spike is 2,331, of which 314 are measurement code |
| 9 | What could not be built from the elaborator as it is | Reported | Ten properties, each supplied by the spike outside the elaborator (section 4) |

## 3. What The Present Route Refuses

Each of these typechecks. Each was run through the public entry.

| Program | Present route | Spike |
| --- | --- | --- |
| A loop inside a branch | `workflow_boundary_type_invalid` | runs |
| A loop inside a loop | `compiler_defect` | runs |
| A `match` whose subject is a pure call | `wcc_lowering_route_unsupported` | runs |
| A union-typed field of loop state | `compiler_defect` | runs |
| An effectful call as a `done` value | `compiler_defect` | runs |
| An effectful call as the argument of another | `compiler_defect` | runs |
| A `let*` binding whose value is an `if` over two lists, in a procedure called in a loop | `workflow_return_not_exportable` | runs |
| The same over two records or two integers | compiles, fails at run time, `pure_expr_payload_invalid` | runs |
| A run reference whose input is the value of an effect | `run_ref_input_binding_invalid` | runs |
| A computed argument of a command | `workflow_return_not_exportable` | runs |
| The search controller, in either form | two different refusals | makes the reference's decisions |

The last review confirmed the two refusals of run references and computed
arguments through the public entry. For that reason the second decisive
experiment compares the two routes on a reduced program. The review states
what that comparison shows: parity of value, effect order and the request
fields tested, for the reduced program. It shows no parity for the forms the
present route does not run.

## 4. What The Spike Supplied Outside The Compiler

The design asks the compiler for a closed program. The elaborator does not
produce one today. The spike built each missing property itself.

| Property | Lines in the spike (measured) | Change in the elaborator, same subset (estimate) |
| --- | --- | --- |
| Callee bodies attached at each call | 81, and 70 to stop after typecheck | about 60 |
| A `done` value that is an effect or a `match` | 31 | about 30 |
| Surface objects translated to closed forms | 73 | about 150 |
| Effect nodes with contract, prompt and declared files | 137 | 150 to 250 |
| Sites | 80 as a tree, 59 as a table | none if the builder assigns them |
| A validator of the normal form | 101 | about 100 |
| Names that hold no file path | 43 | about 60 |
| The program as an artifact with a digest | 38 | about 100 |

The third review judges the estimates: they cover the subset shown and not
the forms left out. Those are listed in section 7.

## 5. What Three Reviews Found

| Round | Verdict | Findings that changed the design |
| --- | --- | --- |
| 1 | Changes required; supports continued evaluation only under conditions | A committed result is reused after the command's script changed. The controller's source disagreed with its reference. The provider's policy was not passed |
| 2 | Changes required; supports building with conditions | Five more ways to change what a command runs without changing the bytes that were bound. The view said "completed" before a coordinator's final commit. The coordinator's protocol was shown only with a node written by hand |
| 3 | Changes required for the spike's resume rules; build with conditions | Invalidation misses a dependence through a file. The default binding still reuses a wrapper's hidden dependency |

Facts that the reviewers established with their own programs:

- The present route has the defect of round 1 too. It returns the same mixed
  value, 206, where an uninterrupted run gives 6 or 306. It binds nothing of
  what a command runs.
- The protocol with a coordinator holds for a run reference compiled from
  `.orc` source: the coordinator's pending commit, the memo's commit, the
  coordinator's final commit. Killed after the pending commit, resume starts
  one more child. Killed after the memo's commit, resume starts none.
- No edit of a program can attach a committed result to the wrong effect.
  The program's digest is checked before any record is read.
- A view of a run of 5,000 effects takes 0.17 seconds, can be made while the
  run holds the writer's lock, and launches nothing.
- For a process that died, the present report says "running" until a
  heartbeat is 300 seconds old. The memo's lock gives "interrupted" at once.

## 6. Conditions Before The First Use On A Real Run

From the last review. Each is a rule that the design must state and that a
test must hold.

| Condition | Why |
| --- | --- |
| Invalidation covers every later committed effect, in the order of the journal, until dependence through files is declared | One effect writes a file that a later one reads by a fixed path. No value passes between them. Invalidating the first reran only the first, and the result mixed old and new. A shipped workflow has that shape (`verified_iteration_drain/drain.orc`) |
| Every command boundary declares what it runs, even when that is nothing | With no declaration, a changed script called by an unchanged wrapper was reused without a refusal |
| What a command declares is read-only, and the run's interpreter is fixed for the run | Binding the interpreter found on `PATH` makes an upgrade refuse every resume. A declared directory that the program writes into, such as a bytecode cache, refuses the next resume |
| A view checks the terminal record against the settlements it implies | A memo edited by hand, with a terminal record and no settlement, was reported as completed |
| The request a provider or a command receives is a contract | Eight fields differ from the present route: provider context, environment, prompt content, execution site key, working directory, command environment, pinned interpreter path, and the flat route's descriptor-rooted `WorkspaceFiles` owner (the spike has none). Provider and command processes can observe the first seven; `WorkspaceFiles` is an internal executor capability. |
| Every form and every coordinator in the release has evidence through the public run and resume entries | The spike has an adapter for one coordinator |

Behaviour that depends on a file's modification time is outside any promise
that binds bytes. The design must say so.

## 7. What Is Not Shown

| Gap | Kind |
| --- | --- |
| Coordinators other than a run reference: trials, provider supervision, peer groups, phased providers, adjudication, requests for human input | Architecture. Each commits into the run's state today. Each would adopt the three-step protocol. Trials already have the pair of commits; the others do not |
| `materialize_view`, `resource_transition`: no performer | Volume |
| `phase-target`: cannot be built, the elaborator drops the scope it needs | A change in the elaborator |
| A context that the compiler supplies to a call (`PhaseCtx`) | A design decision |
| Views beyond the report: dashboard, monitor, watchdog probe, prompt audit, judgment views | Architecture. A memo does not hold step visits, call frames, sessions or observation files |
| Sessions and observation files of providers, secrets | Not designed |
| Parallel map, typed input documents | Later phases of the plan |
| 14 of 52 shipped workflows do not build | Ten for a missing performer, two for the two context forms above, one for a capability that no built-in provider declares, one does not typecheck today |

## 8. The Alternative: Repairing The Present Route

The shared defect repairs plan is the measurement. It is merged to `main`.

| Fact | Value |
| --- | --- |
| Tasks at the start, at the end | 10, 16 |
| Cells of the totality matrix that typecheck and fail, after all repairs | 34 of 120 |
| Rounds of repair of name capture | 4. Each review found another site |
| Environments in which lowering resolves a name | 6 |
| Defects of that class still open | 2, in forms that no shipped program uses |
| Separate refusals met by one search controller | 3: the size of an expression, a loop in a branch, an `if` over lists |
| Forms found outside the matrix in one day, by people writing programs | 6 |

Every one of these has one cause: a value exists at run time only as the
output of a step. A repair of the present route addresses a form in a
position. The matrix counts the pairs. The last review states the
comparison: continuing on the present route is possible, and the evidence
points to a larger set of repairs by position than implementing values with
a memo.

The repairs were still worth making. They removed silent wrong values and
made resume, the workspace lock and result files correct for the programs
that run today, which the new model will also need.

## 9. Decisions

### 9.1 The decision of the gate

| Option | What it means | Evidence |
| --- | --- | --- |
| A. Build evaluated execution, in stages | Phases 2 to 7 of the plan, at a new target. The present route stays for the targets that exist | Sections 2, 3 and 5 |
| B. Build it, and first run one more experiment | One shipped workflow with a coordinator other than a run reference, through both routes, before Phase 2 starts | Section 7, first row |
| C. Repair the present route | A plan per form and position, measured by the matrix | Section 8 |

Recommended: A, with the first release limited to commands, composed
providers, calls and run references, and with the conditions of section 6 in
its acceptance. Option B costs little and removes the largest unknown; it
can run beside Phase 2, which does not depend on it.

### 9.2 Decisions of design that are hard to reverse

The spike had to guess 38 decisions that the design does not make. The full
list is in the spike's report, iteration 3. The last review names the five
whose wrong choice is hardest to undo once memos exist on disk.

| Decision | Recommendation |
| --- | --- |
| The identity of an effect | A table of definitions, each body stored once. Identity is the site within its definition and the activation path at run time. It halves the size of the largest shipped workflow's program (2,659 nodes to 1,284) and names the same effects in the same order on the 123 test programs |
| What the terminal record means | It is written last, after every settlement, and is the only source of "completed". A record after it reopens the run |
| What a command declares | Its implementation files, read-only. Declaration is required |
| What invalidation covers | The chosen effect and every later committed effect, until file dependence is declared |
| Whether a request carries the run's variables | No. The run's identity reaches a program only as a value |

## 10. How The Evidence Was Produced

- Implementation and reviews were by different model families. No reviewer
  repeated the implementer's tests; each wrote its own programs.
- The coordinator ran the spike's modules on the merged branch after each
  iteration: 369 tests, then 530, then 565, each module alone.
- No test calls a real provider. Effects are command-backed procedures and
  stand-in providers.
- Reports and reviews, with the programs the reviewers used, are in the
  working directory of the plan, which is not part of the repository.
