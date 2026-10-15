# Postmortem: The 2026-10-14 Effectiveness Experiments

Status: complete. This postmortem covers the run of the
[effectiveness harness plan](../plans/2026-10-14-effectiveness-harness-and-experiments-plan.md).

**Outcomes:**
- **E-A:** [E-A report](2026-10-14-orc-versus-single-call-evaluated.md). `reviewed_change` replicates; `best_of_n`
  falls one run short.
- **E-B:** [E-B report](2026-10-14-design-review-execute-versus-single-call.md). Not evaluated: the task did not
  qualify.

## Summary

The workflows did not fail. Under the frozen criterion, E-A reproduced September's result for `reviewed_change`
(+0.67 over the first patch, no run worse). `best_of_n` met two of its three clauses, with a mean group gain of
+1.02, but only 4 of 6 runs were positive against at least 5 required. Against the single call, both workflows
gain less than half a point on the 0–8 scale.

What failed was the execution of the study:
- three harness defects surfaced only with live agents and cost a batch and a half of discarded runs;
- the E-B task was too easy to qualify;
- an interim readout computed with a wrong join told the owner the workflows were losing, and the owner stopped
  scoring on it.

## What Went Wrong

| # | problem | root cause | impact |
| --- | --- | --- | --- |
| 1 | The reviewer wrote its report beside `result.json`, and the relpath did not resolve (2 of 4 review calls) | The harness put run state outside the agent's workspace, so prompts named result paths `../../../records/...` (R34) | First batch discarded |
| 2 | Agents shared `/tmp`, tmux servers and the process list with other runs and sessions. A stale tmux server carried `PYTHONPATH` at the main checkout, which holds the E-B solution | No sandbox. `TMPDIR` does not stop hard-coded `/tmp` paths (R35) | First E-B qualification pair discarded; first batch discarded |
| 3 | `best_of_n` implementers wrote their result inside `cand-k` | The workflow's workspace is the tree, the agents work in `cand-k`, and the runtime presents result paths relative to the workspace (R37) | Six `best_of_n` runs discarded |
| 4 | The E-B task did not qualify: one call passed 16/16 and 14/16 hidden tests | The public-interface appendix needed by the hidden tests specified the feature closely, and difficulty was never measured before the criterion was frozen | E-B not evaluated |
| 5 | The owner was told the workflows were losing (best_of_n −1.67, reviewed_change −0.83, the judge "noisy") | An ad hoc script joined ratings to clones by position in `mapping.json`'s batch order. Judges receive clones in another order | Scoring stopped for 30 minutes on a wrong premise |
| 6 | Operational errors | See the list below | Lost time; one run (run-10) discarded |

The operational errors (item 6):
- a `pkill -f` pattern matched the controller's own shell;
- a queue started empty because its list was built in a piped loop's subshell;
- a helper re-scanned a run and reset its verdict;
- a stopped run was relaunched instead of resumed;
- concurrency rose above the ruled cap of four for an hour.

Why the provider-free smoke missed defects 1 to 3: the stand-in agents wrote results through the absolute
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, never `cd`'d into a candidate, and never used `/tmp` or tmux. The defects come
from how real agents read a relative path and from their habits (tmux, `/tmp` logs), which only live agents show.
The live smoke ran after the criterion was frozen and alongside the first batch, so every defect cost runs.

## What Went Right

- **Pre-registration held.** Each criterion was committed before its runs. Each harness fix led to an amendment
  that cites the previous hash and lists the discarded runs, before any rerun. No discarded run was ever scored.
- **Contamination detection.** The scan and adjudication found the cross-session channel (defect 2), and every
  verdict carries its reason.
- **The verdict comes from `summarize`.** It joins by position in each judge's inputs and refuses any batch whose copied-back clone id disagrees. The anchors behaved as
  designed in every batch, and the two judges agree at r = 0.81.
- **Resumable runs.** Resumes worked: an owner-ordered stop and a judge stop each resumed without repeating a
  committed call.

## Actions

| action | where | status |
| --- | --- | --- |
| Run state in the agent's workspace; the agent CLI in a bubblewrap sandbox; `best_of_n`'s state linked from each candidate | harness (`experiments/compare/`), design | done |
| Measure difficulty before freezing a criterion: the single call below half of hidden acceptance, and expected review blockers ≥ 1 | design, "Difficulty calibration for follow-on experiments" | rule recorded; the next E-B task is to be chosen under it |
| Run a live smoke with the real CLIs, inspected by hand, before the criterion is frozen, not with the batch | design Verification Strategy (follow-on) | proposed |
| Interim readouts only through `summarize`'s join, and anchors checked before any conclusion | coordinator practice (memory) | adopted |
| Product: present provider result paths so that a workflow whose agents work in another directory (`best_of_n`) does not lose results. For example, show the absolute path or say what it is relative to | runtime, provider result delivery | proposed; not part of this plan |

Amended 2026-10-15 (ruling R55, `amends_4` of the calibration criterion): the owner removed the hidden-acceptance
condition from the difficulty-calibration row above. That row is the 2026-10-14 record. The current rule, review
blockers alone with hidden acceptance reported as description, is in the
[design](../design/orc_effectiveness_comparison_harness.md) ("Difficulty calibration for follow-on experiments").

## Answer To "Why Did The Strategies Fail Now When They Succeeded Before"

They did not fail. The impression came from the wrong interim readout (item 5). E-A's numbers are close to
September's:

| measure | September ([report](2026-09-28-orc-versus-single-call.md), confirmation run) | now |
| --- | --- | --- |
| `best_of_n` mean gain over its candidate group | +0.83, positive in 6 of 6 runs | +1.02, positive in 4 of 6 runs |
| `best_of_n` against single calls of the selector's model | 7.25 against 6.67 (+0.58) | 6.08 against 5.75 (+0.33) |
| `reviewed_change` gain over the first patch | +0.58 | +0.67 |

The judges, the batch layout and the runtime differ from September (E-A report, Limits). The `best_of_n` clause
that failed turns on one run. Each judge alone would reverse a different clause, so the
honest reading is "small positive effect, not robustly above the bar".

Two limits make a stronger claim impossible on this task:
- **The reviewer had little to do.** It approved 4 of 6 first patches.
- **The selector cannot exploit good candidates.** The spread within a run is large (up to 3.5–8), and in 2 of 6 runs
  the selector picked a candidate at or below its group's mean.

Both point to the difficulty rule above.

## Closeout

- **Suite at `037b8ab9`:** `pytest -q -n 16 --dist=worksteal -m "not e2e"` gave 13 failed and 14723 passed. That is
  the 11 failures that predate the branch plus two load flakes, which pass in isolation.
- **Branch:** `feat/compare-harness`. It contains the design and plan, the harness, `score.orc`, the control, the
  task packages, the frozen and amended criteria, the lean-pilot retirement (`61b7d04d`) and the three reports.
  It is merged into `main` with a merge commit (R40), so every cited commit stays reachable.
- **Rulings:** the plan's appendix lists every ruling, R1 to R41.
- **The EasySpin (ES) boundary edit** was left to the session that owns it. That session had not committed it
  when this plan closed.
- **Evidence:** run records, pools, patches, results and scan outputs are kept in the evidence directory beside
  the repository (`agent-orchestration-compare-evidence/ea/` and `eb/`). The candidate trees and clones were
  deleted after the reports were written.

