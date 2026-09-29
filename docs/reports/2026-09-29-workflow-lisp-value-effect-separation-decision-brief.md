# Decision Brief: Separating Values From Effects In Workflow Lisp Execution

- **Status:** owner decisions recorded on 2026-09-29 (section 12). The choice
  between options A, B and C stays open until the spike of section 10
  reports. No option changes a current contract until the owner selects it
  and a design document is written for it.
- **Date and commit:** 2026-09-29, `main` at `1fb5b167`.
- **Consumes:**
  [core calculus middle-end](../design/workflow_lisp_core_calculus_middle_end.md),
  [design principles](../design/workflow_language_design_principles.md),
  [effect-tracking audit](2026-09-08-workflow-lisp-effect-tracking-audit.md),
  [effect ledger simplification](../design/workflow_lisp_effect_ledger_simplification.md),
  [pure-call composition](../design/workflow_lisp_pure_call_composition.md),
  [pure-result replay](../design/workflow_lisp_pure_result_replay.md),
  [lexical execution checkpoints](../design/workflow_lisp_lexical_execution_checkpoints.md),
  [M0 decision brief](2026-07-26-m0-decision-brief.md),
  `specs/state.md`, `specs/io.md`.
- **Decisions:** section 12.

## 1. The Question

Authors of `.orc` workflows meet positional limits: a form that is accepted in
one position is rejected, or crashes the compiler, in another position of the
same type. Six were reproduced (section 2.1). Each can be repaired where it
occurs. This brief asks whether they share a cause, and whether a change of
design removes the cause instead of the instances.

Terms used below:

- An **effect** is a call that acts on the world: a command, a provider call,
  a request for input, a resource transition. It happens once and may cost
  money.
- A **value** is the result of a computation over other values. It can be
  computed again at no cost.
- The **flat route** is the current compilation path: the workflow core
  calculus (WCC) is turned into a flat list of steps, and the runtime executes
  the steps.
- An **inverted runtime** executes the core calculus itself. The accepted
  design calls this authority inversion.

## 2. Evidence

All runs used command-backed procedures and no provider calls. Line references
come from the investigation of 2026-09-29; those marked † were checked again
by hand.

### 2.1 Six Reproduced Limits

| # | Form | Symptom | Raised at | Cause |
| --- | --- | --- | --- | --- |
| a | A local procedure that wraps an imported effectful procedure, used as a `match` subject or bound with `let*` | `TypeError: unsupported nested WCC M2 prefix for LetStarExpr`; bound form: `wcc_lowering_route_unsupported`, "requires case subjects with stable producer step identities" | `wcc/elaborate.py:5257`† | The effect map is rebuilt from local procedures only (`compiler.py:5026`†), so the wrapper is inferred effect-free and inlined. A union computed without a producing step cannot be a `match` subject |
| b | An effectful call inside `(loop-state :like state :current <call>)` | `TypeError: unsupported pure projection expression: ProcedureCallExpr` | `lowering/pure_projection.py:1020` | The elaborator passes `loop-state` through unexamined; the older loop lowerer assumes its fields are pure. The typechecker does not enforce that |
| c | A call to a generic helper used as a `match` subject | `proc_ref_signature_invalid` | `procedure_refs.py:203` | The typechecker of `match` discards the typechecked subject, so specialization discovery does not see the call |
| d | A pure `match` over a command or loop result whose arms build a record | `--dry-run` exits 0; the run is rejected at start: `pure replay binding references an unknown result member` | `workflow/pure_result_replay.py:2645`, `:1814` | Lowering emits references the binding's type does not declare. The replay index is built only when a run starts (`cli/commands/run.py:586-594`†) |
| e | A generic procedure with no effects that constructs an applied generic union over its own type parameter | `generic_union_unresolved_argument` at every call | `generic_unions.py:395` | The inliner copies the body into the caller without substituting the specialized types |
| f | A `match` whose arms mix a plain variant with a loop | At 2.32: "without required author-time variant proof". At 2.33: passes `--dry-run`, then fails as d | `workflow/validation.py:6779` | The result bundle reads a variant field with no proof of the selected variant |

A rewrite that binds compound subexpressions with `let*` before compilation
makes b and c work and does not help a, d, e or f. The elaborator already
produces such bindings; two call sites refuse them.

### 2.2 The Same Work Done In Several Places

| Work | Places |
| --- | --- |
| Inlining a procedure call | `functions.py:442`, `functions.py:846`, `wcc/defunctionalize.py:6685` |
| Binding a subexpression to a name | `wcc/elaborate.py:2490`, `wcc/elaborate.py:3924`, `wcc/anf.py` |
| Evaluating a pure expression | `lowering/pure_projection.py`, `lowering/values.py:611` |
| Lowering a loop body | The elaborator produces WCC; `_frontend_expr_from_wcc_loop_body` (`wcc/defunctionalize.py:6965`†) turns it back into a surface expression; `lowering/control_loops.py` lowers that |

### 2.3 Runtime Facts

- The runtime's plan has edges for order, fallthrough, transfer and loop body.
  It has no edges for which value depends on which
  (`workflow/runtime_plan.py:608-649`).
- A result is stored under the step's presentation name. One value can be
  stored in up to seven places (`specs/state.md`,
  `workflow_lisp_pure_result_replay.md:104-109`).
- A command call has no identity and its inputs are not recorded. A provider
  attempt has an identity that includes the visit count, so an interrupted
  call gets a new identity on resume (`workflow/provider_attempts.py:204-325`).
- A provider or command result file is written to a path with no iteration
  part. The runtime creates the parent directory and does not remove an
  existing file (`workflow/executor.py:7394-7424`). Reproduced: a command that
  wrote its result only in iteration 1 completed iterations 2 and 3 with
  iteration 1's value, and a second run read the first run's file.
- Resume after a command that exited with a known failure fails closed with
  `lexical_restore_pending_effect_unsafe`
  (`lexical_checkpoint_restore.py:1273-1285`). The owning design scopes that
  rule to an effect that started and whose completion is unknown.
- The workspace is not captured. Resume assumes the files are as the failed
  run left them.

### 2.4 What Accepted Documents Already Say

| Statement | Source |
| --- | --- |
| A program that passes typecheck elaborates, normalizes and defunctionalizes without rejection. A failure after typecheck is a compiler defect by definition | core calculus §9, §12 |
| Per-form lowerers cost forms × contexts and were the reason for the core calculus | core calculus §15 |
| Authority inversion is deferred, not rejected. Revisit after the flat route has proven the calculus on a real promoted family | core calculus §15 |
| Journal replay in the style of Temporal is rejected: it trades away static effect visibility, validation before commit and machine-diffable parity evidence for composition generality "this architecture achieves at compile time" | core calculus §15 |
| Effect identity keys and memo-first resume re-enter on named evidence: re-spend traced to positional invalidation in three runs, or one forced full re-execution | M0 decision brief, M2 depth |
| The effect system is partly overbuilt. Reconsider the foundation if later composition work shows a structural limit | effect-tracking audit, Assessment |

The owner stated on 2026-09-29 that the Design Delta family is deprecated,
apart from its reusable library procedures. It is therefore not evidence for
the revisit condition, although `docs/index.md` still lists it as the promoted
primary. The decision rests on recent programs: the
[`std/improve` example](../../workflows/examples/improve_experiment_proposal.orc)
and the two workflows of the
[single-call comparison](2026-09-28-orc-versus-single-call.md). The composition
work of 2026-09-28 produced the limits in 2.1.

## 3. Root Cause

At run time a value exists only as the output of a step. Three consequences
follow.

1. **Branching needs a producer.** A `match` is a transfer between steps
   chosen by a step's output. A union that no step produced cannot be a
   subject (case a).
2. **Pure computation is a second world.** Pure expressions were added as
   `pure_projection` steps and a run-time replay index. Each position that
   accepts a value must say which world it accepts, and the two worlds have
   different rules (cases b, d, f).
3. **The effect system is consumed for placement.** The audit's consumer
   inventory lists "whether that work belongs in a pure projection, needs an
   execution boundary" first. An error in inferred effects therefore changes
   how code is lowered, not only what is reported (case a).

The limits are instances. The rule is the cause.

## 4. Options

### A. Repair the flat route

Carry out the accepted design. Accept bound prefixes at every elaborator call
site; include imported procedures in the effect map; keep the typechecked
subject of `match`; substitute specialized types when inlining; emit only
declared references; build the replay index during `--dry-run`; give a pure
union a producing pure step; lower loops from WCC without the round trip;
delete the older lowerers.

- Removes: the six instances and the duplicated lowerers.
- Keeps: the rule in section 3, positional resume, the replay index, lexical
  checkpoints.
- Every new language form still needs lowering to steps, a resume story and a
  replay story.

### B. Flat route with values as expressions

Keep flat steps for effects. Stop materializing pure results as rows. A
control node or a step input carries a pure expression over effect results,
and the runtime evaluates it when needed, using the existing closed
interpreter (`workflow/pure_expr.py`).

- Removes: the producer rule, pure rows, the replay index.
- Keeps: defunctionalization, positional resume, lexical checkpoints.
- The executable IR gains the dependency of each expression on effect
  results. That is the dataflow graph the runtime lacks today.

### C. Inverted runtime with an effect memo

The runtime executes the core calculus with a lexical environment. State is a
memo of effect results. Each effect has an identity: its site in the program
plus the activation path that reached it (call sites and loop ordinals). Each
memo entry records a digest of the effect's resolved input and the validated
result.

Resume evaluates the workflow from its entry. An effect whose identity and
input digest are in the memo returns the recorded result and does not run.
Pure expressions are computed again. A digest mismatch stops with a named
diagnostic.

- Removes: the producer rule, defunctionalization to steps for this route,
  pure rows, the replay index, positional resume, and the placement consumer
  of the effect system.
- Keeps: typecheck, elaboration to WCC, output contracts, validation before a
  result is committed, the fail-closed policy for an effect that started and
  whose completion is unknown.
- A variant restores a serialized environment at a checkpoint instead of
  evaluating again. It needs the environment serialization that lexical
  checkpoints already specify, and keeps their identity digests.

This differs from the rejected alternative in three ways. The language is
closed: loops are bounded, there are no first-class procedures, and the effect
vocabulary is fixed, so effect sites can be listed before a run. Evaluation
cannot repeat external work, because an effect runs only when it is absent
from the memo. Each memo hit is checked against the input digest, so
evaluation does not "replay until it happens to reach the previous state".

### D. Everything is a step

Remove the pure world. Record construction, projection and `match` become
steps with stored results.

- Removes the two-world boundary.
- Multiplies stored rows and step count, against the direction of the
  pure-result replay design, which exists to stop storing pure values.
- Not recommended.

### E. A library in a host language

Express workflows as functions in a general-purpose language, with typed
results and a journaled effect call.

- Removes the compiler.
- Loses what a closed language gives: checks over the whole workflow before
  any call is paid for, effect sites known before a run, and a bound on what
  an agent-authored workflow can do.
- Not recommended while agent-authored workflows are a goal.

## 5. Comparison

| Criterion | A | B | C |
| --- | --- | --- | --- |
| Removes the producer rule | No | Yes | Yes |
| Totality | By enumeration of forms × positions | By enumeration, fewer positions | By construction: evaluation is defined by recursion over the calculus |
| Effect sites known before a run | Yes | Yes | Yes, given a correct effect inference |
| Result validated before it is committed | Yes | Yes | Yes |
| Parity evidence | Byte identity of lowered output | Byte identity for effect steps | Behavioral: ordered effect identities, input digests, result digests, final value |
| Resume without repeated effects | Positional; fails closed in the cases of 2.3 | Positional | By effect identity |
| Parallel effects | Order-dependent positions | Order-dependent positions | Identity does not depend on order |
| Code serving only the mechanism that remains | `lowering/` 22,767 lines, `wcc/defunctionalize.py` 7,630, lexical checkpoints 7,409, `pure_result_replay.py` 2,929 | Same minus the replay index | Retired for the new target once older targets are retired |
| Risk | Low per change, unbounded in count | Medium | High: runtime, validation and resume are rebuilt for this route |
| Reversible | Yes | Yes | Yes while it is confined to a new target |

Line counts are sizes of existing modules, not a promise of deletion.

## 6. The Effect System Under Each Option

The audit separates four things called effects: authored `:effects` clauses,
the inferred summary, semantic operation records, and checkpoint and
dependency evidence.

| Layer | A and B | C |
| --- | --- | --- |
| Authored `:effects` | Inference by default, optional checked upper bound, as the revised effect ledger design proposes | Same |
| Inferred summary | Needed for placement, boundary classification, child-run placement, specialization | Needed for listing effect sites, child-run placement, specialization. Placement is no longer a consumer |
| Operation records | Rebuilt from lowered steps | Derived from effect sites |
| Checkpoint and dependency evidence | Lexical checkpoints and prompt dependency evidence | The memo entry: identity, input digest, result |

Under C the effect system shrinks because a consumer disappears, not because
knowledge is discarded. Under A and B the audit's finding stands: one bit is
not enough.

Reducing the effect system alone does not remove the producer rule. It
removes annotation burden and the class of defect in case a.

## 7. Changes That Do Not Depend On The Option

| Change | Reason |
| --- | --- |
| Include imported procedures in the effect map | Case a. One test on `main` relies on the defect: a wrapper that declares `:effects ()` around an effectful import |
| Keep the typechecked subject of `match` | Case c |
| Substitute specialized types when inlining | Case e |
| Build the replay index during `--dry-run` | Case d is found at compile time |
| Write each result to a path that names the call, and require the file to be absent before the call | Stale result, 2.3. Supervision calls already require absence (`specs/io.md:157-174`) |
| Scope `pending_effect_unsafe` to an effect whose completion is unknown | 2.3 |
| Accept bound prefixes in `loop-state` fields and in `match` subjects in the elaborator | Case b and the crash in case a. Added to the list after the owner approved the other rows; it is in the same shared stage |
| A generated matrix of forms × positions: every program that typechecks must compile and run | Measures totality; defines done for A, and the input set for a spike of C |

All options share typecheck and elaboration to WCC, so none of these is
discarded by a later choice.

## 8. Recommendation

1. Make the changes in section 7.
2. Run a bounded feasibility spike of option C (section 10), outside
   production paths.
3. Decide between A, B and C on the spike's results.

Do not invest in the parts of option A that serve only the flat route (a
producing step for pure unions, direct loop lowering, deletion of the older
lowerers) before that decision.

What this makes harder: two execution routes exist while older targets remain
supported; parity evidence between routes changes from byte identity to
behavior; `specs/state.md` gains a second state profile.

## 9. Unproven Claims

Each claim is an open prerequisite until its fixture passes.

| Claim | Fixture |
| --- | --- |
| WCC carries everything evaluation needs: types at effect sites for output contracts, and source provenance | Evaluate the six programs of 2.1 in their direct form and the `std/improve` example from WCC alone |
| Effect identity is stable across resume | Interrupt a three-iteration loop after each effect; resume; assert no effect runs twice and the final value equals an uninterrupted run |
| Pure evaluation has no hidden input | The pure interpreter does no I/O (`workflow/pure_expr.py:8-16`), but relpath contract checks on pure outputs read the filesystem (`contracts/output_contract.py:1537-1578`). Delete a file named by a pure path value between run and resume; the result must be a named diagnostic or an unchanged value, never a silent difference |
| Effect sites can be listed before a run | For every program, the memo's keys after the run are a subset of the sites listed before it |
| Behavior matches the flat route | The effect trace equals the flat route's on the `std/improve` example and the two workflows of the single-call comparison, with stand-in effects |
| Option B's executable IR can carry expression dependencies without breaking shared validation | Not designed. Needs its own fixture before B can be selected |

Operations that read the world and are not yet modeled as effects: relpath
existence checks on pure values, `produce-one-of` selection by workspace
digest (`workflow_lisp/phase_flow.py:343-349`), secrets read from the
environment, and wall-clock trial deadlines. Under C each becomes an effect or
moves to an effect boundary.

## 10. Spike: Scope And Criteria Fixed In Advance

Scope: an evaluator for `let`, effect call, `case`, join point and bounded
loop; effects are commands and stand-in providers, with no real provider call;
a memo file; resume. It reuses output contract validation and the command
executor. It is throwaway code and is not wired to `orchestrator run`. It
follows the elaborator repairs of section 7, which it depends on.

| Criterion | Pass |
| --- | --- |
| The six programs of 2.1, direct form, source unchanged | All six return the expected value |
| Resume at every effect boundary | No effect runs twice; final value equal |
| Static effect sites | Superset of memo keys for every program |
| Effect trace against the flat route | Equal on programs both accept |
| Size | Evaluator and memo under 2,000 lines, excluding reused modules. The number is an estimate to make the claim falsifiable |

A failed criterion is a finding, not a reason to adjust the criterion.

## 11. What Any Option Must Preserve

From the specifications, for the targets that exist today:

- state schema `2.1`, its key formats and progress fields (`specs/state.md`);
- no committed provider call runs again on resume (`specs/state.md:380-384`,
  `specs/io.md:106-110`);
- an interrupted provider visit reruns with exactly one
  `provider_attempt_interrupted_rerun` (`specs/providers.md:7-15`);
- a result is validated before it becomes canonical state (principle 10);
- a changed source is rejected before any mutation (`specs/state.md:1009-1012`);
- wrong-path writes fail closed and stdout is not a result channel
  (`specs/io.md:46-48`, `:81-82`);
- refusals name their rule (principle 28).

Option C meets these for older targets by leaving them on the flat route. For
a new target it needs a specified state profile of its own.

## 12. Decisions

Recorded from the owner on 2026-09-29.

| # | Question | Decision |
| --- | --- | --- |
| 1 | The changes in section 7 | Approved as defect repairs, compiler and runtime |
| 2 | The spike in section 10 | Approved, after the compiler repairs |
| 3 | Are the revisit conditions of 2.4 met | Not on the Design Delta family, which is deprecated apart from its reusable library procedures. Base the decision on recent programs |
| 4 | Version policy for an inverted runtime | Decide after the spike |
| 5 | The documented limits of target 2.33 | Relabel as known defects, as core calculus §12 requires. Deliberate restrictions stay rules |

Open: the choice between options A, B and C, and the version policy.

## 13. Limits Of This Brief

- YAML workflows are out of scope. They stay on the existing runtime.
- No option was implemented. Section 5's risk and size entries are judgments.
- The evidence is from command-backed programs. Provider behavior is inferred
  from shared code paths.
- The re-entry evidence for memo-first resume was not tallied against past
  runs.
- Workspace capture is not addressed by any option.
