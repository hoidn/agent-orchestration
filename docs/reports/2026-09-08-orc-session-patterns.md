# Session Patterns For ORC Research

Date: 2026-09-08. Status: sanitized historical requirements-development evidence.
This report informs [case selection and evaluation](../design/orc_reuse_introspection_search_experiment.md#session-derived-workloads).
It is neither a transcript export nor an effectiveness result or work allocation.
The [research charter](../plans/2026-09-08-orc-research-charter.md) owns the thesis;
the [execution plan](../plans/2026-09-08-orc-research-demonstration-plan.md) owns tasks and budgets.

## Corpus And Limits

The supplied inspection joined CLI thread metadata in local `state_5.sqlite`
to public user messages in `history.jsonl`, selecting exact `cwd` equality with
this `agent-orchestration` checkout root and `source = cli`. The February–September
2026 slice contains 9,083 entries across 110 session IDs; matching metadata
contains 111 CLI threads. Deduplication used `(session_id, ts, text)`: one
duplicate was removed and one malformed history line, snapshot line 732, skipped.
The five-file surviving rollout set includes inherited fork history. Related
sessions and forks require grouping by the underlying task/failure episode.

Only public messages were inspected for this account, without private reasoning
or bulk tool-result collection. One separately identified public agent postmortem
below supplies a reported observation, not an independently audited code result.
Locators refer to the inspected snapshot: `history.jsonl` line numbers and UTC
dates identify selected evidence, not stable repository links. Local histories
are provenance only; future tests must use sanitized standalone artifacts.

The slice includes orchestration work targeting other repositories. A message,
session, repeated wording, or numerical variant is not an independent workload,
failure, intervention, or saved hour. Persistence requests can reflect status
visibility, a deliberate approval boundary, or changed user intent. They do not
alone show a missing primitive, automation opportunity, or comparative ORC value.

The exact forms `workflow status?` / `status?` account for 595 entries across
eight session IDs; `stage and commit` / `stage and comit` account for 331 across
twenty IDs. These count recorded instructions, not failures or potential savings;
their purpose still needs episode-level interpretation.

## Evidence Anchors

These short descriptions preserve the task pattern without exporting transcripts.
Descriptions are paraphrases except the explicitly quoted completion question.

| UTC date | Snapshot locator | Observed request or account | Requirement suggested, subject to qualification |
| --- | --- | --- | --- |
| Mar 7 | `history.jsonl:8796–8799` | Fresh reviewer B; resume author A for bounded fixes and review. | Carry findings and usable work across review/completion handoffs. |
| Apr 15 | `history.jsonl:10613–10616,10705` | Diagnose prompt causes, edit, and rerun phases using separate artifacts; compare A/B. | Tie revisions to evidence and attributable whole-run consequences. |
| Apr 20 | `history.jsonl:11204,11206` | Repeat prompt revision/rerun until satisfactory; ask how many cycles and what changed. | Measure quality, revision substance, and total cost, including failed attempts. |
| Jun 2–3 | `history.jsonl:15612,15636,15639,15768,15771` | “did it actually *finish* implementation”; assess valid findings, update the plan, execute/update implementation. | Separate a useful intermediate result from selected completion and assess findings semantically. |
| Jun 29 | `history.jsonl:17551,17562` | Request subtractive bookkeeping/prompt edits and creation/naming of a workflow-management skill. | Consider a reusable agent protocol alongside orchestration machinery. |
| Jul 23 | `history.jsonl:18737,18739` | Contrast ORC and one-shot execution; derive workflow/language changes; discuss soft evaluation. | Compare representations fairly and qualify semantic evaluation. |
| Jul 29–Aug 4 | `history.jsonl:18988,19033,19195` | Stop evidence polish after five refinements and ask for the next attempt; preserve closed reviews; scope steering/invalidation; prefer behavioral checks. | Check goal progress and retain unaffected acceptance while changed material can invalidate relevant reviews. |
| Aug 14 | `history.jsonl:19417,19432` | Stop growth of a proof analyzer; avoid bending the product to its scanner. | Reconsider the evaluator/decomposition/foundation when measured progress misses the goal. |
| Aug 15 | `history.jsonl:19439,19443` | Batch disjoint changes and combine checks; request exact contribution deltas after a regression. | Preserve per-change attribution when work/checks are shared. |

A public agent postmortem in
`rollout-2026-08-04T13-19-38-019fce6e-89d5-74e3-a532-ed3fbd41b51e.jsonl:495947`
reported ten commits and 967 insertions while pursuing 39 unresolved routes.
Those are agent-reported numbers, not a code audit or measured avoidable cost.
Together with the later scanner objections, they motivate testing for review
churn and evaluator-driven work that does not advance the user's objective.

The research interest predates this amendment: `history.jsonl:9022` (Mar 8)
asks about programs for evolutionary selection; `history.jsonl:18718–18719`
(Jul 22) concerns expression adjudication and posthoc mutation. These establish
intent to study program improvement, not evidence that search already works.

## Translation Into Development Cases

Prioritize two needs within the existing design: review/revise-to-selected-
completion while retaining usable results and unaffected accepted work; and
agent-chosen orchestration improvement from observed evidence. Map them to the
existing three requirement families: review/completion handoff, conditional
judgment/disagreement with revise/reconsider decisions, and reusable multi-item
continuation with scoped policy changes at meaningful task boundaries.
These are requirements, not a prescribed graph or three promised generic APIs.
Include a non-orchestrator transfer case within those three, not an extra arm.
Prefer the [adaptive scientific transfer](../design/orc_reuse_introspection_search_experiment.md#adaptive-scientific-transfer)
context supported by the PtychoPINN evidence below for an already allocated case.

Qualify present-day recurrence against the episode date and
[current capabilities](../capability_status_matrix.md). Existing public
`std/phase::review-revise-loop-proc`, `std/drain::backlog-drain-proc`, and the
verified-iteration drain are reuse candidates before local extraction. The
generic watchdog performs one invocation; recurrence and progress after recovery
are an integration seam. Provider sessions and bounded supervision/static peers
do not establish arbitrary cross-session steering. Classify a case as resolved,
composition/discoverability friction, or still failing before asserting a gap.

Recovery, steering delivery, and batch attribution are pressure cases or later
conditional questions, not separate first-stage projects. Sending, receipt, and
application of steering differ; simulating a task boundary does not prove live
tmux or cross-run transport. Providers judge materiality, valid findings, success,
and reconsideration; ORC composes, routes, and records those judgments.

## Assessment And Claim Boundaries

Keep all already-mined material in development. Group before/after revisions,
repeated prompts, variants, and forks before selecting fresh withheld requirements
and artifacts. Check behavior, dependencies, retained obligations, and meaningful
completion; do not score historical wording or literal prompt phrases.
Scientific steering often supplied the answer: expose only pre-intervention
contracts and observations equally to both conditions. Exclude later
diagnosis-bearing document revisions; score declared requirement-change
feedback and assisted discovery separately from unassisted discovery.

The design assigns review/completion handoff to the existing R1b closed-loop
episode: an actual authoring agent sees a goal and development evidence and
chooses the orchestration edit. A correct initial program needs no manufactured
fault. Deterministic domain leaves test flow, not real prompt-quality efficacy.
Record setup, maintenance, all attempts, and intervention purpose/substance;
unproductive reviews and polls are diagnostic costs, not goals to minimize.

For conditional R2, prefer a qualifying review/planning-improvement family only
if independent behavior checks and blinded semantic judgments detect known
defects. The linear-classifier hard-oracle alternative has existing assets but
still needs a qualified green baseline. Choose one family before candidate work
under one finite protocol. These sessions add no trials,
funding, sample size, or basis for relaxing the design's holdout rules. Later
agent-plus-skill and idiomatic Python comparisons need their own equal-budget
allocation; live prompt/topology search belongs to separately approved R3.

Metric gains without goal progress, repeated review churn, or growing glue call
for provider-led reconsideration of the approach, evaluator, or foundation.
Changing the objective/evaluator requires an explicit amendment, new baseline,
and fresh assessment, not a retroactive improvement claim. Follow the existing
axis lifecycle for transferred cases, local remedies, language/type redesign,
alternative foundations, or scoped retirement with simplification. Execution
safety remains excluded from the research assessment.

## PtychoPINN Session Evidence

This additional inspection covered the current PtychoPINN checkout and its
historical temporary/trash clones and worktrees, excluding separately rooted
PtychoPINN2 and the paper repository. It found 3,863 metadata threads: 331 CLI,
72 VS Code, 2,197 exec, and 1,263 spawned descendants across 19 root lineages.
There are 7,829 canonical input entries across 319 IDs, October 2025–September
2026. Only 26 root and 674 child rollout files survive; all 2,197 older exec
rollouts are missing. Public paired replies are concentrated in July–September
2026 and sometimes stop at commentary; repository records corroborate selected
outcomes. The 167 exec first prompts concerning experiment sessions show intended
automation, not completed autonomous work. Two history entries came from exec;
12 are explicit automated watchdog ticks. Copied fork history, repeated turns,
and descendants of one episode are not independent human interventions or samples.

Scientific, orchestration, and paper/CNS work are mixed within this scope.
These counts delimit qualitative requirement evidence; they establish no
prevalence, saved time, or ORC advantage. All newly mined material is development
material. Locators below use the inspected `history.jsonl` snapshot and UTC dates;
portable `PtychoPINN:path` references identify corroborating source sections or
symbols, with no dependency on that sibling checkout for future assessments.

1. **Diagnose, pilot, judge value, then expand.** Compare TensorFlow/Torch
   stitching before broadening (2025-11-13, `history.jsonl:1146`); examine failed
   reconstructions against a reference and competing causes (2026-02-17, `6127`);
   recover the figure command, run a small pilot, then reproduce (Aug 7, `19312`).
   Counterexample: the Feb 24 objection (`6935`) rejects abandoning a stage after
   two low-gain attempts; a cheap stopping rule cannot replace scientific judgment.
   `PtychoPINN:docs/plans/2026-09-03-srunet-single-factor-arms.md`, Global Constraints
   and Latest correction, permits seeds 17/42 only after seed-3 promotion and
   records all valid arms stopped, with none adopted.

2. **Rethink the scientific method when its objective misses the goal.**
   Jul 13 steering (`18353,18359`) replaces a gain sweep with physical derivation;
   Sep 3 (`20265,20267,20268`) moves from a failed affine pilot to a different
   likelihood method. `PtychoPINN:docs/plans/2026-09-02-phase-gauge-refinement.md`,
   Execution status and revision after the affine gate, records decreasing affine
   objective while phase MAE worsens from about 0.293 to 0.476 rad, cancellation of
   the other 89 records, withdrawal of overlap-fitted tilt, and data-derived tilt
   plus likelihood refinement. Counterexample: Jul 14 (`18362`) distinguishes
   failure localization from a causal mechanism and requests existing checkpoints
   only; a plausible account or additional sweeps do not establish physical cause.

3. **Retain useful evidence and invalidate only the affected comparison.**
   Jul 14 (`18389→18393`) reverses a pristine six-arm aggregate requirement:
   retain earlier CNN results as prior evidence and finish corrected Hybrid work.
   Sep 3 (`20280,20281,20314`) requests a numerical repair, selective reruns, and
   an audit of which recent SRU runs became invalid. The phase-gauge plan's revision
   after the seeded sweep preserves the unaffected seed row while rerunning
   affected polish rows after float64 loss accumulation fixes premature stopping.
   Counterexample: useful prior evidence is not automatically current comparison
   evidence; a revised causal protocol may require an explicit amendment, new
   baseline, and fresh assessment. Neither an old label nor any hash mismatch
   alone decides scientific reuse; the comparison's actual contract does.

4. **Evaluate the requested scientific quality, separately from process success.**
   Jul 11 (`18262`) asks for performance/SSIM rather than byte equivalence; Sep 1
   (`20190`) replaces invented metrics with stitched SSIM/MAE on the same objects.
   A spawned reviewer's public final,
   `rollout-2026-09-08T17-51-20-01a083a5-dcb9-7232-96ad-ad5376878fad.jsonl:195`,
   rejects the C4-CI holdout: amplitude SSIM 0.647902 is below 0.652454 despite the
   other bounds and identities passing. `PtychoPINN:docs/plans/2026-09-08-synthetic-quality-metrics-v3-recalibration.md`,
   Execution result, corroborates nine successful processes without an activated
   current-metric-v3 gate. Counterexample: this is observed delegated judgment,
   not ORC effectiveness; passing identity checks cannot establish quality or
   authorize changing a failed holdout's envelope. This is historical evidence,
   not an instruction to resume that calibration here.

5. **Reuse the study procedure; keep native science native.** Compose a study
   (Jan 26, `3516`), iterate against an incumbent (Mar 12, `9227`), and investigate
   architecture search (Apr 27, `12060`); Jul 10 (`18156`) conditions a reusable
   driver on ergonomic future ablations. Counterexample: architecture/hyperparameter
   search alone is not ORC program search. `PtychoPINN:ptycho/workflows/synthetic_pipeline.py::_assert_stage_identity`
   and `PtychoPINN:scripts/simulation/README.md`, Stage identity and reuse, already
   provide stage-aware reuse; `PtychoPINN:ptycho_torch/reconstruction_scoring.py::score_canvas`
   owns maintained scoring. ORC and Python/skill controls can call those same
   tools. Duplicating their runner, scorer, calibration, or numerical optimization
   inside ORC would add cost without testing the representation's value.
