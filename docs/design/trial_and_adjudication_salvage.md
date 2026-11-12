# Trial And Adjudication: Salvage Record

Status: **Historical.** This page keeps the design knowledge worth reusing from two **Retired**
features: the `trial` form (a blinded comparison of arms inside a workflow, target 2.25) and the
`adjudicated_provider` step below it (candidates, an evaluator and a score ledger, DSL v2.11).
Nothing here is implemented, selected or admitted. The page selects no work, changes no spec, and
is not copy-safe: the build refuses `trial` and the command prints "retired".

- **Direction.** None: trials are retired without a port
  ([evaluated execution](workflow_lisp_evaluated_execution.md), §19, decision 3), and no phase of
  the [roadmap](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md) owns an
  in-workflow comparison. A port needs its own design.
- **Use today.** For an experiment: the [comparison harness](../../experiments/compare/README.md)
  under `AGENTS.md` ("Experiment rules") and the
  [structural search driver](orc_structural_search_driver.md); the
  [seed-set plan](../plans/2026-11-11-seed-set-calibration-plan.md) shows a judge gate. For a pick
  inside a workflow: a parallel map and one judge call, as in
  [`best_of_n.orc`](../../experiments/orc_vs_single_call/workflows/best_of_n.orc). Section numbers
  (§) and rules (I, K, M) below are evaluated execution's.
- **Sources.** [Trial runs](workflow_lisp_trial_runs.md) and its
  [history record](../reports/documentation-history/workflow_lisp_trial_runs-history.md) (quoted
  section names are its); the [final review](../../artifacts/review/e2-trial-final-review.md);
  the trial and adjudication sections of `specs/dsl.md`, `providers.md`, `state.md` and `io.md`.
- **Code.** Local tag `archive/dead-executors-2026-11-11` holds `orchestrator/workflow/trial/`,
  `orchestrator/workflow/adjudication/`, the frontend handling and the spec sections. It does
  **not** hold the half that ran a trial (`trial/evaluation.py`, `trial/adjudication.py`, the
  scheduler in `trial/runtime.py`, the executor hosting, the runtime tests): commit `08cdd59b` is
  the last tree with all of it. Commit `f0005f17` holds the frontend, ledger and packet tests.

## What The Feature Did

A workflow declared 2 to 16 *arms*. Each arm was a child run of a named workflow in its own clone
of a repository at a pinned commit, run `reps` times, a bounded number at once. When all had
ended, the runtime ran the declared check commands in each clone, built one evidence packet per
run under a random label, and asked one evaluator provider to score each packet from 0 to 1
against a rubric. It joined labels to arms, took each arm's median, ranked the arms and applied a
fixed success rule. The user saw one step of kind `trial`, with arm names only after scoring; one
typed value; a verdict file under `artifacts/trials/`; and one JSON summary from
`orchestrate trial`. From
`workflows/experiments/qa_placement_effectiveness/qa_placement_trial.orc` (condensed):

```lisp
(trial
  :arms ((:id "DIRECT" :run-ref (run-ref :source (:repo "file:///…/seed" :commit "7386…2c1b")
                                         :program (:bundle direct-treatment) :inputs (…) …))
         (:id "RICH" :run-ref (run-ref … :program (:bundle rich-treatment) …)))
  :reps 1 :max-concurrency 4
  :evaluation
  (record
    :checks (list (record :id "visible-f1-contract" :command (list … "-m" "pytest" "-q" …)
                          :authority "correctness" :required true :timeout-ms 14400000))
    :judgment (record :provider "scorer" :rubric-asset "prompts/trial_rubric.md" …)
    :observation (record :include (list "task_spec" "workspace_delta" "check_results" …) …)
    :aggregation (record :mode "independent_rubric" :rep-combine "median" :tie "authored_order")
    :success-rule (record :superior (record :min-abs-improvement 0.10 :max-cost-ratio 4.0)
                          :non-inferior (record :min-cost-reduction 0.20) …))
  :budget (record :arm-timeout-ms 172800000 :max-evaluator-attempts 4 …))
```

`adjudicated_provider` ran several provider candidates of one step in copies of the workspace,
scored each, and copied the best one's declared outputs into the parent. `trial` reused only its
scorer identity, output parser and score-ledger writer.

## Reusable Design Decisions

"Survives" says whether the decision holds for a new design, in a workflow or in a harness.

1. **The runtime builds what the judge sees, from a closed list.** *Problem:* a prompt cannot hide
   which arm made a result. *Decision:* one packet per run from six named members (`task_spec`,
   `validated_result`, `workspace_delta`, `check_results`, `declared_artifacts`,
   `failure_evidence`). Arm ids, source, commit, program, provider, model, completion order,
   logs, run state and earlier scores never enter; the task enters only if all arms got the same
   inputs; authors choose only the rubric. *Survives:* as is. *Source:*
   `trial/packets.py::build_trial_cell_evaluation_packet`.
2. **Check the packet for leaks.** *Problem:* a projection can be wrong. *Decision:* each sealed
   identity (arm ids, locators, commits, program names, the evaluator's alias) is searched for as
   a whole token in the packet and in check output; a hit refuses
   (`trial_blinding_policy_invalid`). Diff text and paths are exempt. The exit test: a classifier
   over packet bytes stayed at chance. *Survives:* with a change; the exemption is a hole (item 4
   below). *Source:* `_validate_nonexempt_blinding`; final review.
3. **Opaque labels, sealed, drawn once.** *Problem:* a restart must not deal new labels.
   *Decision:* each (arm, rep) cell gets `opaque-<sha256>` from 32 random bytes; the map goes in
   the ledger header before any arm starts and is read back on resume. Packets and score rows
   carry only the label; the join runs once, after scores are frozen, and must be one to one. No
   seed exists: order is authored order, and salt and completion order enter no identity.
   *Survives:* yes, if the judge cannot read the seal. *Source:* `build_sealed_opaque_label_map`.
4. **A judgment is strict data, keyed by what was judged and by whom.** *Problem:* prose must not
   become a score, nor a score attach to other evidence. *Decision:* one JSON object with exactly
   `candidate_id` (the packet's label), `score` (finite, 0 to 1), `summary` and `citations` (item
   ids of that packet). An invalid reply is an `output_invalid` attempt: charged, never repaired.
   `score_run_key` hashes request, contract, evidence freeze, label, packet digest and scorer
   identity (provider, parameters, prompt, rubric, limits), not the number. *Survives:* yes, as a
   pure check after a typed provider result. *Source:* `parse_trial_evaluator_output`;
   `adjudication/scoring.py`.
5. **Freeze the evidence before judging and the referee before running.** *Problem:* evidence or
   rubric changed after results are seen. *Decision:* no check or judge call starts until every
   cell is terminal and the outcome set's digest is in the ledger. Checks, rubric, limits,
   aggregation and success rule form one compile-time pure record for all arms, so an edited
   threshold is another trial (`trial_evaluation_contract_not_pure`). *Survives:* yes; the
   harness's hashed criterion is the same idea. *Source:* state spec; "Evaluation contract".
6. **Failures are outcomes; no winner from a partly judged set.** *Problem:* dropping failed arms
   or picking among the scored few biases the result. *Decision:* the value is `{outcomes,
   verdict, verdict_artifact}`; an outcome is `Completed {arm_id, rep, value, evidence}` or
   `Failed {arm_id, rep, failure, evidence}`. A failed arm cancels no sibling. An arm has an
   aggregate only when all its repetitions were scored; fewer than two such arms is
   `insufficient_scored_arms`. A tie follows authored order and selects nothing by itself.
   *Survives:* the rules; failure as a value has no mechanism (see the mapping). *Source:*
   `aggregate_trial_verdict`; `select_candidate`.
7. **Budget: count launches, charge before launch, never refund.** *Problem:* a crash must not
   create free attempts or more time. *Decision:* deadlines per arm and per trial, stored as
   absolute times; a total ceiling on evaluator attempts; concurrency caps. An attempt is
   recorded before the provider is prepared, and one found open after a crash is closed
   `provider_failed` and stays charged. At exhaustion, unstarted work settles as failed and
   running work finishes. Unknown cost is `UNKNOWN`, never zero. *Survives:* as is. *Source:*
   `trial/ledger.py` (`TrialRuntimeBudgetWindow`, `replay_trial_evaluator_attempts`).
8. **One writer, two commits, rerun only what did not settle.** *Problem:* concurrent arms and a
   crash mid-trial. *Decision:* workers send events; only the coordinator writes ledgers. On
   resume a settled cell is reused, a child that finished before its cell settled is discarded
   and rerun under a new ordinal, and a committed score is never replaced. The trial is one
   effect with a prepared and a final row around the parent commit. *Survives:* yes: K2–K4 ask
   for this pair, and `experiments/evaluated_execution_spike/trial.py` ran the trial behind it
   with stand-ins. *Source:* state spec.
9. **An arm has its own clone; evidence is bounded.** *Problem:* shared state, and evidence that
   is huge or secret. *Decision:* cell roots are disjoint, named by index and digest. A child's
   changes return as a normalized delta, never applied to the parent. The clone is an output
   boundary, not a sandbox (`same_trust_boundary`). Byte caps refuse before any call; only the
   diff is cut, with omitted counts. `adjudicated_provider` also refused a packet that held a
   declared secret. *Survives:* yes. *Source:* `derive_trial_cell_effect_scopes`;
   `adjudication/evidence.py`.

Not reusable: the promotion transaction (`adjudication/promotion.py`), since evaluated execution
rolls nothing back (K8) and applying a winner is one command; the baseline copy with its secret
denylist (`adjudication/baseline.py`), replaced by single-commit clones (`repos.build_candidate`
in the harness); the per-site result types and the ledger's 22 row kinds.

## What Was Wrong Or Unfinished (Do Not Copy)

1. **Nothing was calibrated.** No check of the judge on known controls, no task difficulty
   qualification, no control in the scored set, no repeated judgment, no model limit; the probe
   tested blindness, not validity. This conflicts with "No uncalibrated experiments" (`AGENTS.md`).
2. **Its "better" is not the owner's.** `superior` took a 0.10 gain at up to `max-cost-ratio`
   times the cost, against the runner-up only; the rule is Pareto dominance over quality and
   model-aware cost (driver, "Objective, Selection And Local Observations"). Check commands
   ranked above the judge, which saw their output ("Evaluation authority hierarchy"); the owner
   makes the blind rubric primary and tests secondary.
3. **The verdict could not select.** `build_run_ref_accounting` defaults a child's cost to
   `UNKNOWN` and `evaluate_trial_packets` wrote `UNKNOWN` for every evaluator attempt, so two
   scored arms give `cost_unknown` and a null `selected_arm`. Only a unit test reached `superior`.
4. **Blinding held only if the judge did not look.** The label map lay in the ledger header under
   the run root; the evaluator was a tool-using provider with the same OS user and no mount
   boundary; nothing recorded what it read. Diff text and paths were exempt from the leak check
   and no path was stripped, so an arm that writes a design note shows itself by shape.
5. **One judgment per run, alone.** Calls shared no reference, so drift was invisible. A failed
   judgment voided its arm's aggregate, and the fixture's attempt ceiling equals its cell count:
   "a kill during judging still spends in-flight attempts and can change the decision" (§9.3).
6. **Identity and time were by position.** The site digest hashed the form's line and column
   (`typecheck_trial.py`) and the ledger path used frame, step and visit count; evaluated
   identity excludes both (§6). A trial was refused in a loop, a map and another trial. Every arm
   had one deadline from the opening of the trial, so a cell that waits for a slot has less time.
7. **Not portable, never consumed.** Arms needed a literal repository locator and commit. No
   source read the typed result: the one tracked trial is the last expression of a workflow
   declared `-> Value`. Six required keys admitted one value each.
8. **Weight and defects.** About 11,000 lines. `_append` reloads and rewrites the whole ledger per
   row, through one 600-line check ([core audit](../reports/2026-11-11-project-audit/core.md)). A
   four-arm smoke ended `trial_evaluator_attempts_exhausted` on every arm
   ([record](../reports/2026-09-08-orc-research-demonstration.md)); the spike's recovery raised
   `KeyError: 'cell'` (§9.3).

## Mapping Onto Evaluated Execution

Every "missing" entry is an open prerequisite, not a known-feasible step.

| Part | Mechanism that exists | Missing |
| --- | --- | --- |
| Arms at once | Parallel map (§11): one item per arm and repetition, a directory each, results in input order, identity by item index (I2) | Public qualification of the form. Agent turns, phased providers and host input are refused in a worker. No cancellation |
| An arm as a run at a pinned commit | Path run references: a child in its own clone | A path child must be effect-free (`run_ref/closed_path.py::_require_closed_effects`); confined children are command-only and their provider part is dropped; children of one parent run one at a time. An arm that calls a provider is a map item in a directory the caller supplies |
| A failed arm as a value | A provider result of union type, when the provider reports its own failure | A failed or timed-out attempt stops the run (§8.2), and the map then fails (§11) |
| The judge | One `provider-result`; a score enum rejects out-of-range values at the contract | A judge without tools: every built-in template is a tool-using agent. The label echo and citation check |
| Checks; repeated judgments | `command-result` in the arm's directory; a map or loop over repetition indices, each its own identity | Nothing |
| Labels and order | A command that maps a seed to a permutation; its committed value replays | The language has no random source. The value is readable in the memo |
| A person scores | Durable host input (§9.5): a typed answer, shown files hashed | It suspends the run; serial only |
| Budget | `:timeout-sec` per call; `:max` caps a list, not spend; the run-wide `--max-cost-usd` ([CLI](../../specs/cli.md)) stops before the next provider call and refuses on an unmetered attempt | A budget for one comparison or one arm, a ceiling on judge attempts, a deadline for a group. The cap is per invocation and is not stored |
| The comparison as one unit | A coordinator effect (§9.3, K2–K5): own ledger, proof in the memo, never superseded (K8) | The adapter. §9.3 names what must be shown before it: an interrupted-judge budget policy, settlement against the actual memo commit, distinct inputs per arm, child capsules |

**Soundness.** Three obstacles, heaviest first.

- *Blinding inside one run tree.* The memo holds every committed value inline (M5) and each
  attempt directory holds its prompt and output: a label map, a permutation and every arm's
  result lie open to a judge with tools and the same OS user. Two ways out, both unproven: a
  judge without tools whose whole input is a closed packet (decisions 1 and 2), or a judge under
  a mount boundary that shows only the candidates, as the harness has outside the runtime.
- *What a judgment is bound to.* The resolved input covers the prompt, the files it names and the
  provider policy (§7.2), not a repository the judge reads through tools: the judgment is bound
  to a path, not to bytes. Passing the patch or its digest as a value restores decision 4.
- *Replay or a new judgment.* After `committed`, a judgment replays and is never asked again.
  Before it, resume runs the next attempt, a new draw, and the earlier reply is evidence only
  (§8.3). That is sound while stops do not depend on scores. Two can: a contract that rejects
  some replies, and `invalidate`, which discards a judgment after it was read. A coordinator
  effect cannot be invalidated (K8), and repeats the whole comparison when killed before its
  commit (K4).

**Closest reachable.** A pick among runs of one program, where no arm needs hiding. A copy of
`best_of_n.orc` with `:parallel 4 :workspace repo` compiled at target 2.39 with two effect sites
(compile-only probe; not run). It yields a choice, not a measurement: no controls, no calibration.

## What The Harness And Seed-Set Study Already Cover

| Concern | Old trial design | Harness / seed-set design | Prefer |
| --- | --- | --- | --- |
| What the judge reads | A closed JSON packet, bounded and hashed | An applied-patch clone rebuilt from the seeded base, with the surrounding code | Harness for code; the packet for a judge without tools |
| Hiding identity | Opaque label, exclusion list, token scan | Random clone id; a random order per judge; fixed seed-commit dates; `seed/` files never in a diff; `docs/design/` and `artifacts/` stripped from patches; the mapping outside the clones' ancestors | Harness |
| Keeping the judge honest | Nothing; any provider alias | An empty-root sandbox that mounts only its batches' clones; a private home; a scan of the judge's calls and sessions; `verify-pool` restores a changed clone; "judge ran tests" is a hit; a model guard and a scan of the model that answered | Harness |
| Controls and drift | None | Anchors in every batch; the judge gate V1 (controls), V2 (reference rank), V3 (retest), V4 (agreement with hidden tests), on two natural controls per task | Harness |
| Judging mode | One packet per call; check output shown | At most ten clones per call; no test results shown | Harness |
| Joining scores | Label echo; a row bound to packet digest and scorer identity; a hash-chained ledger | Position and the copied-back clone path; batch membership; criterion hash and judge model bound in the run; provider starts paired with shim records | Harness, plus the old digest binding |
| Missing judgment; failed arm | Fails the run and voids the arm's aggregate; a failed arm is never scored | Refuses the summary, and a missing observation cannot shrink the denominator; a failure or timeout scores 0, an incident is excluded and listed (driver) | Harness |
| "Better" | Leader against runner-up: margin and cost ratio | Pareto dominance with tolerances; a frontier; a frozen price table | Harness (owner rule) |
| Cost and spend | Cost recorded, always `UNKNOWN`; deadlines and an attempt ceiling | Calls per run and tokens from native receipts, unavailable never zero; `COMPARE_MAX_CALLS`, nested launches refused, tranche caps, a spend ledger under one lock | Harness |
| Crash while judging | The attempt stays charged and may cost an arm | The scoring run is resumed, never rerun | Harness |

**What the old design did that the harness does not.**

- *No file times.* `pool.build_batches` builds a batch's clones in member order and the anchors
  last, so creation times order them. A packet carries no times. A change that builds the clones
  in random order exists on the seed-set study's branch and is not on `main` yet.
- *A leak check on the judged content.* The harness strips two path prefixes and scans what agents
  and judges did; nothing checks the pooled patches themselves for text that marks an arm.
- *A rating bound to bytes, with reasons that resolve.* A rating row names a clone, whose patch is
  recorded beside it; the row carries no digest, and the judge's `reason` is free text.
- *One durable unit.* A trial resumed to one verdict; the harness is a sequence of operator steps.

**What the harness learned that the old design lacked.** Judges disagree with themselves on
identical code and can rank a merged fix below candidates. Agents read solutions, records and
other sessions unless a mount boundary stops them, and start nested provider CLIs outside the
count. A judge may edit or test what it rates. A shift between batches can pass for a difference
between arms. A task set can be too easy to show anything, so difficulty is calibrated first, on
natural solutions and with no planted flaw.

## Names Worth Keeping

- `arm`, `rep`, `cell` (`TrialCellKey`); "authored order"; `opaque label`, `sealed label map`;
  `evidence freeze`; `packet` and `citable_item_ids`; `scorer identity`; `score_run_key`.
- Attempt statuses `preparation_failed`, `provider_failed`, `output_invalid`, `scored`; "charged
  attempt"; `Completed | Failed` and `TrialFailure {code, phase, retryable, secondary_causes}`.
- `KNOWN` / `UNKNOWN` for tokens and cost; `cost_unknown`, `insufficient_scored_arms`;
  `same_trust_boundary`; `trial_blinding_policy_invalid`, `trial_packet_citation_invalid`,
  `trial_evaluation_contract_not_pure`.

Safe to lose: the `trial` grammar and its single-valued keys; `TrialResult$<site-digest>` and the
fixed verdict types; `trial_event_ledger.v1`, its row kinds and path plan; the dispositions
`superior` and `non_inferior_lower_cost`; `adjudicated_provider` with its baseline copy, promotion
manifest and mirror ledger; the `workflow_trial_run_result.v1` wire and the command. The
[Lane D plan](../plans/2026-11-11-lane-d-dead-executors-and-state-manager-plan.md) makes `trial` a
retired form name, so a port with other semantics needs a new name.

## Not Verified

- No provider was called. Two compile-only probes ran outside the repository: the parallel pick
  above, and a `trial` form at target 2.39, which `main` then refused with `closed_program_gap` (it now
  refuses with `form_retired`).
- At commit `08cdd59b`, `trial/evaluation.py` was read in full, the scheduler of
  `trial/runtime.py` and `trial/adjudication.py` in part, `trial/sdk.py` and the executor hosting
  not at all; the ledger's lifecycle check, `settlement.py`, `config.py`, `promotion.py` and
  `baseline.py` by outline. Whether a running child was stopped at its deadline was not traced.
- That real trials always ended `cost_unknown` is inferred from the code and one end-to-end
  assertion of a null selection; no verdict of a real-provider trial was read. The record of the
  four-arm run does not give the cause of its exhausted attempts. The labelling probe was not
  rerun. The file-time ordering of harness clones was read from `pool.build_batches`, not shown
  on a pool. `--max-cost-usd` was read in its plan, before it landed.
- Every "missing" row, in particular whether a judge without tools or under a mount boundary can
  be a provider option, and whether parallel map passes its public qualification (its public kill, resume and consumer
  tests are on `main`; the closeout is open).
- Spec sections and frontend symbols named here have left `main` or leave it when the two packages
  are deleted; they remain at the tag.
