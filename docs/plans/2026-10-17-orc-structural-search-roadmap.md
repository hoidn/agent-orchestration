# ORC Structural Search Roadmap

Status: **proposed, unselected** (2026-10-17). Research plan for compiler-assisted
search over ORC workflow programs. It sequences work, names gates and states
budgets as placeholders; selecting any phase is an owner act that fills those
placeholders. Owner: ORC research maintainers.

This is the "separate bounded plan and budget" that the
[evolution roadmap's R3 row](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#current-research-sequence)
requires. The [charter](2026-09-08-orc-research-charter.md) owns the thesis,
the five hypotheses and the decision rule. The
[structural-search experiment design](../design/orc_structural_search_experiment.md)
owns the protocol contracts (search space, evaluator, controls, splits,
identities, accounting). The
[source-site inspection design](../design/workflow_lisp_source_site_inspection.md)
owns the frontend component. The
[program-search boundaries](../design/workflow_lisp_program_search_boundaries.md)
bind every phase; Phase 0 depends on the
[proposed amendment](../design/workflow_lisp_program_search_boundaries.md#proposed-amendment-2026-10-17)
to its §1 and §6 being approved. The
[comparison harness](../design/orc_effectiveness_comparison_harness.md) and its
[README](../../experiments/compare/README.md) own the evaluation apparatus.
This plan restates none of their contracts.

Not in this plan: a budget, a revival of `trial` or the flat route, any change
to [CE-1](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#ce-1--checked-program-evaluation-pending-unselected)
(checked program evaluation stays unselected; candidates execute through
ordinary `run`), and any optimizer vocabulary under `orchestrator/`.

## Phase 0 Rationale

The charter orders the work: "Start with a finite catalog ... Enumerate small
spaces. Add adaptive search only when justified." The measured record supports
that order. On the rung-3 task E-B2 ran (chosen on the owner's blocker rule;
borderline under the frozen rule), `design_review_execute` and the single call both passed 0.49 of hidden tests
and `reviewed_change`'s revisions raised hidden acceptance in 0 of 3 runs
([E-B2](../reports/2026-10-15-calibrated-orc-versus-single-call.md)); on rung 1,
E-B3 left both claims not evaluated with 5 of 9 attempts valued
([E-B3](../reports/2026-10-16-eb3-orc-versus-single-call-rung1.md)). If
structurally distinct policies do not separate beyond the within-arm spread on
a qualified family, compiler-assisted search has nothing to find there, and
Phases 1–3 are not selected for that family. A DIRECT winner or a tie within
noise is a valid outcome under the charter's decision rule.

The tension Phase 0 must resolve first: tasks small enough to be cheap are
finished by one call (calibration rung 1: one call passed 0.90–0.94 of hidden
tests), which leaves review, planning and escalation nothing to do and makes
the objective flat; tasks that qualify cost 21–105 minutes per workflow run at
concurrency four (E-B2 means 1,271–6,273 s) and lose attempts to provider
timeouts at the 14,400 s ceiling. Phase 0's first question is whether any
family is both qualified and affordable for search.

## Phases

| Phase | Entry gate | Work | Deliverables and completion evidence |
| --- | --- | --- | --- |
| **0 — Landscape** | Owner selection with the placeholders below filled; owner approval of the boundaries amendment (its §1 and §6 stand as written until then). | (a) Choose the family (see Family); record its qualification under the frozen calibration rule. (b) Retarget the chosen seed module to 2.39 (remove authored `:lowering`; imported 2.35 modules keep their contracts) and record its compile. (c) Extend the harness: arm spec from a candidate root; generic-command arm; archive/lineage/holdout scan patterns. (d) Run the policy catalog (the five policies plus DIRECT, mapped onto existing seeds) through the harness, scored by hidden acceptance, `R` replicates each on `T₀` tasks. (e) Run the three-arm proposal-interface study. (f) Calibrate the cost model with the measured episode and run costs. | Compile record of the 2.39 seed; harness extension with its tests passing; a landscape readout: per-policy hidden-acceptance mean and spread per task, separation against the within-arm SD on each task, DIRECT's position, lost-run rate, calls and wall clock per run; the three-arm readout (acceptance per episode, edit locality, distinct skeletons, cost per accepted proposal); the cost model filled with measured numbers. |
| **1 — Source-site inspection and edit transaction** | Phase 0 readout shows separation on at least two tasks of the family: on each, at least two catalog policies differ by more than the predeclared tolerance (default 2 SD of the within-arm spread), and DIRECT is not the sole winner. Owner selection. | Execute the source-site design's feasibility probe (span→type and span→environment retention, or the accepted REPL-style fallback); implement the read-only manifest, replacement typecheck in site context and the edit transaction with scope validation, under `orchestrator/workflow_lisp/` beside `repl_inspect.py`/`LoadedModule`. | The feasibility probe recorded before implementation; every scenario of the source-site design's [verification table](../design/workflow_lisp_source_site_inspection.md#verification-and-declarative-integration-scenarios) passing as tests; narrow selectors, then `pytest -q -n 16 --dist=worksteal`. |
| **2 — Search MVP** | Phase 1 accepted; owner selection with a hard call ceiling and a quota policy. | One search run of 8–12 mutator episodes on 2–3 screening tasks of the family, one replicate per candidate-task; whole-run hidden acceptance as the objective; a small archive; the lineage record; finalists replicated on the validation split. Descriptive only. | A reproducible search run with at least one genuine control-flow change among accepted candidates; complete candidate/cost/failure history; the screening and shrinkage readout (finalists' validation mean against their screening mean); the collapse-rule readout. |
| **3 — Comparative study** | Phase 2 shows an accepted candidate above the incumbent on validation by more than the tolerance; owner selection with its own preregistered criterion and budget. | The controls ladder of the experiment design (DIRECT, catalog best, prompt-only, feedback-free random, agent skill, ORC search, matched Python search) at equal evaluation counts and episode envelopes; the sealed assessment under the blind rubric with anchors and two judges. | A report separating structural gain, search-efficiency effect, representation effect and integration effort, each with its uncertainty, under the frozen criterion. |
| **4 — Compositional search** | Phase 3 attributes a gain to structure; three-arm study did not collapse on the locus arm; owner selection. | Fragment contract with explicit input mapping; capture-aware extraction for a documented subset; hygienic insertion; typed holes with random fill; named certified rewrites as source templates over existing library procedures; classical typed operators. | An extracted composition transfers between two workflows without manual rewriting of its internals and survives complete-program evaluation. |

Each gate is a review of the previous phase's readout against the charter's
[decision rule](2026-09-08-orc-research-charter.md#decision-rule): retain a
useful scope, improve a demonstrated bottleneck, reconsider the foundation, or
retire the unsupported claim.

## Family

Phase 0 chooses one family before any search spend and does not launch a
second family to replace unfavorable results. Candidates, with what is
measured about each:

| Family | Qualification under the frozen rule (`experiments/compare/criteria/calibration.json`, `qualifies` and `borderline`) | Objective headroom | Cost signal |
| --- | --- | --- | --- |
| Rung 1 `cf1-generic-unions` | Qualified: blockers 1, 1, 1 over three patches ([continuation](../reports/2026-10-15-calibration-continuation.md)) | Small: single calls and finals at 148–158 of 164 hidden nodes; `direct_task.hidden_mean` 0.933 in E-B3 | E-B3: `direct_task` 4,347 s mean; `reviewed_change` 5,797 s; `design_review_execute` timed out at the 14,400 s executor ceiling in both cleared attempts |
| Rung 2 `resume-projection-integrity` | Qualified: mean 2.5 over two patches ([calibration](../reports/2026-10-14-task-difficulty-calibration.md)) | 88/119 and 87/119 in calibration (0.26 headroom) | Single calls 13–58 min on the ladder; no workflow run measured |
| Rung 3 `adopted-attempt-lineage` | Borderline: mean 1.0 over two patches; a third sample is required before it qualifies | 16–30 of 52; within-arm SD 0.13–0.16 | E-B2: 1,271–6,273 s per run at concurrency four |
| Rung 4 `pure-result-replay` | Qualified: mean 2.0 over two patches | 85/134 and 87/134 | Single calls within the ladder's 13–58 min |
| A new family | Must be qualified by the frozen rule and built in the package layout (`task.txt`, `intent.txt`, `base_commit`, `seed/`, `anchors/`, `hidden/`) before any search spend | Unknown | Unknown |

Development checks visible to agents are never the objective: every arm reaches
100 percent on tests it can run ([design lessons](../orc_workflow_design_lessons.md#evaluating-a-workflow)).
Hidden acceptance is measured outside the candidate workspace.

## Cost Model

Measured inputs (every figure from a report's Cost or Runs section, or from the
named code):

| Quantity | Measured | Source |
| --- | --- | --- |
| Wall clock per workflow run, rung 3, concurrency ≤ 4 | `direct_task` 1,271 s; `reviewed_change` 2,598 s; `design_review_execute` 6,273 s (means) | E-B2, Cost |
| Wall clock per workflow run, rung 1 | `direct_task` 4,347 s (3 runs); `reviewed_change` 5,797 s (2 runs); `design_review_execute` attempts 16,584 s and 16,640 s, both executor timeouts | E-B3, Runs |
| Provider calls per run | `direct_task` 1; `design_review_execute` 4; `reviewed_change` 4–6 | E-B2, Runs |
| One single call; one review | 13–58 min on rungs 1–4; 2,248 s (continuation). Reviews 2–6 min; 192 s | Calibration, Results; continuation, Result |
| Attempts per valued run | E-B3: 9 attempts, 5 valued (three provider timeouts, one after an operational pause; one contamination exclusion). E-B2: 9 of 9 valued | E-B3, Runs; E-B2, Runs |
| Within-arm spread of hidden acceptance | Rung 3: 30, 30, 16 of 52 for both `design_review_execute` and `direct_task` (SD 0.13 population, 0.16 sample); `reviewed_change` 16, 21, 16 | E-B2, Runs |
| Hidden acceptance cost | Local pytest, one node at a time, 1,800 s ceiling per node (`experiments/compare/summarize.py::NODE_TIMEOUT_SEC`); 164 nodes on rung 1, 52 on rung 3 | `summarize.py`; reports |
| Judge cost | One provider call per judge per batch of at most ten clones, two judges | Harness design, Decision (D4); E-B2, Cost |
| Full compile | 1.87 s for one clean Stage-3 compile | LSP design, Context And Authority |
| Codex weekly window | E-B2: 10 smoke calls coincided with 0% → 13%, then 37 calls (31 arm, 6 judge) with 13% → 40%: 0.73 points per call for the batch, 0.85 for the whole session; calibration: 18 calls took 96% → 100% and 1,245.01 credits; E-B3: 28 generation calls, a reset window rose 1% → 54%; continuation: 2 calls, 59% → 64%. All account-wide readings shared with other sessions: upper bounds, not attributions | Reports, Cost |
| Anthropic usage | Not metered by the harness; Claude session files carry `message.usage` per assistant message (`experiments/compare/scan.py::claude_sessions`; `orchestrator/providers/native_store_claude.py`) and are the named proxy | Harness design, Non-Goals; experiment design, Cost Accounting |
| One mutator episode | `UNKNOWN`; the three-arm study measures it | — |

Unit costs. One **evaluation** is one workflow run of one candidate on one task:
`c` provider calls (1–6), `w` wall clock (1,271–6,273 s measured; up to the
14,400 s executor ceiling plus overhead on a timeout), plus a local hidden
acceptance pass of `h` per task (`UNKNOWN`; measured in Phase 0). One **episode** is one mutator call, any number of free compiles,
and the candidate's screening evaluations. Attempts per valued run `L` is 1.0–1.8
measured; budget 1.5. Every budget below is stated in provider calls, workflow
runs, wall clock and mutator episodes. Tokens appear only where a session-file
reader provides them; `UNKNOWN` is retained; no dollar figure is claimed.

| Phase | Formula | With defaults | Owner placeholders |
| --- | --- | --- | --- |
| 0 landscape | runs = `P` policies × `R` replicates × `T₀` tasks; attempts = runs × `L`; calls = attempts × `c`; sequential wall clock = attempts × `w` + runs × `h` | `P` = 6, `R` = 3, `T₀` = 2: 36 valued runs, 54 attempts, 54–324 calls, 19–94 sequential hours plus 36 `h` | `R`, `T₀` (at least 2, the Phase 1 gate's minimum), concurrency, hard call ceiling, quota policy (weekly window or credits), stop at `__%` window left |
| 0 three-arm study | mutator calls = 3 × `E₀`; evaluations = stratified subset `S` runs × `L` | `E₀` = 8: 24 mutator calls; `S` = 12: 18 attempts, 18–108 calls | `E₀`, `S`, the one seed, the one model |
| 2 pilot | candidates = seeds + accepted proposals ≤ 2 + `E₂`; screening runs = candidates × `T₂`; validation runs = `F` finalists × `V` tasks × `r` replicates; attempts = runs × `L` | `E₂` = 12, `T₂` = 3: 42 screening runs; `F` = 2, `V` = 3, `r` = 3: 18 validation runs; 90 attempts, 90–540 evaluation calls, 32–157 sequential hours plus 60 `h`, 12 mutator calls | `E₂` (8–12), `T₂` (2–3), `F`, `V`, `r`, hard call ceiling, quota policy |
| 3 comparison | each search arm repeats a Phase 2-scale search; each fixed arm costs `T₂` × `r` runs; sealed judging adds 2 judges × batches | Stated at Phase 3 selection from Phase 2's measured numbers | Everything; its own preregistration |

At E-B2's 0.73–0.85 points per call upper bound, the whole of Phase 0
(landscape 54–324 calls plus three-arm 42–132 calls: 96–456 calls) is roughly
0.7–3.9 weekly windows, and the Phase 2 pilot (102–552 calls, mutator calls
included) 0.7–4.7 windows; the true share is unknown because nothing
attributes the drain per call.
The quota policy is stated at selection as the harness plan's R8 did (continue
on credits, or stop at a stated window percentage).

## Decision Points And Stop Rules

| Point | Rule |
| --- | --- |
| Family choice | Only a family qualified under the frozen rule with objective headroom above the tolerance; otherwise Phase 0 reports "no affordable qualified family" and stops. |
| Phase 0 separation | Tolerance predeclared in hidden-fraction units (default 2 × within-arm SD, measured on the family in Phase 0 itself); judged per task and required on at least two tasks. DIRECT sole winner or all within tolerance: record under the charter's decision rule; Phases 1–3 not selected for the family. |
| Three-arm collapse | If the experiment design's [collapse stop rule](../design/orc_structural_search_experiment.md#diversity-metric-and-collapse-stop-rule) fires for the locus arm, Phase 4's typed-operator track is not selected; if it fires for every arm, Phase 2 is not selected. |
| Screening | Advancement, finalist replication and the shrinkage readout follow the experiment design's [selection rule](../design/orc_structural_search_experiment.md#evaluator-objective-and-selection-rule); the pilot stays descriptive, and no Phase 3 selection rests on a screening readout alone. |
| Quota | No new run when the owner-stated window floor is reached unless the stated credit policy covers it; the readout says what completed. |
| Lost runs | Provider-infrastructure stops are resumed, never relaunched; a timeout or contamination is an outcome under the frozen rule, its attempted cost counts, and the attempt rate is reported. |
| Model policy | The harness's model policy of 2026-10-15 applies to every mutator, candidate and judge call. |

## Verification Obligations

- Documentation-only change (this plan and its designs): link and anchor check
  of every added reference; no test or code change.
- Phase 0: the harness extension's tests (`tests/experiments/test_compare_*.py`,
  extended), one plumbing run with the stand-in agent CLI of
  `tests/experiments/compare_harness_support.py` through the real shim, then one
  live smoke with real agents before freezing the criterion
  ([design lessons](../orc_workflow_design_lessons.md#before-spending-on-real-calls)).
- Phase 1: the source-site design's feasibility probe recorded before
  implementation; its scenarios as tests; narrow selectors first, then the broad
  suite in tmux.
- Phases 2–3: criterion frozen and hashed before any score; every provider call
  behind the shims; scan and adjudication before pooling; readouts computed with
  `summarize.py`'s own join and anchors checked first.
- Any seed or experiment workflow added gets a row in `workflows/README.md`'s
  registry and route-readiness registry.

## Reuse

| Phase | Reuses | Adds |
| --- | --- | --- |
| 0 | `experiments/compare/` (`prepare.py`, `repos.py`, `pool.py`, `scan.py`, `summarize.py`, shims, criteria, task packages rungs 1–4); the frozen calibration rule; seeds `experiments/orc_vs_single_call/workflows/{reviewed_change,best_of_n}.orc`, `workflows/examples/{design_review_execute,plan_review_execute}.orc`, `workflows/library/control/direct_task.orc`, `experiments/compare/control/review_once.orc`, `std/improve`; REPL `:info`/`:source` for site selection; `reader.read_sexpr_text` for the locus arm's reader-tree comparison; `compile --diagnostics-json` | Arm spec from a candidate root; generic-command arm; scan patterns; the 2.39 seed retarget |
| 1 | `repl_expr.py::LoadedModule`, `repl_inspect.py`, `closed/frontend.py::TypedProgram`, `typecheck_context.py::TypedExpr`, `reader.py::SourceReadTrace`, `expression_traversal.free_expr_names`, `contracts/closed_program/program.py` digests and sites; `lsp/navigation.py` and `authored_symbols.py` as precedents | The manifest, replacement typecheck and transaction |
| 2 | Everything above; `record.json`'s `state_root` and `runtime_commit` as the lineage pattern | `experiments/orc_structural_search/` driver, records, prompts, skeleton projection |
| 3 | Harness pooling, judges, anchors, criterion hashing | Python and skill controls as generic-command arms |
| 4 | `free_expr_names`, `map_expr`; `std/improve` and review helpers as rewrite targets | Fragment archive and operators |

Not reused: `trial` (refuses `workflow_execution_target_retired`; the E2 SDK,
`TrialRunOptions` and `run_trial_entry`, is removed at main), `explain` (refuses `workflow_explain_retired`),
every `--emit-*` flag (refuses `workflow_lisp_cli_input_unsupported`), the
historical evolution substrate design, and the uncommitted OMP-only cost ledger
in another session's working tree.

## Documentation And Registry Obligations

Done in the change that adds this plan: the three documents, the amendment
block, the corrected "What Is Already Available" table of the
[existing experiment design](../design/orc_reuse_introspection_search_experiment.md#what-is-already-available),
index and design README entries, one capability-matrix row, and the R3 row's
pointer. Owed at Phase 0: registry rows for retargeted seeds; the landscape
report under `docs/reports/`. Owed at Phase 1: the capability-matrix row moves
from Designed to its measured status; the REPL and LSP designs gain a pointer
to the component.

## Owner Inputs At Selection

Family. Phase 0: `R`, `T₀`, `E₀`, `S`, the one seed and the one model for the
three-arm study. Phase 2: `E₂`, `T₂`, `F`, `V`, `r`. Every phase: concurrency,
hard call ceiling, quota policy. Separation tolerance (or the default); collapse
threshold (or the default); approval of the boundaries amendment.
