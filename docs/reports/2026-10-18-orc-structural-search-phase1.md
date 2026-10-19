# ORC Structural Search Phase 1: Catalog And Unguided I1 Sampling On Family (a)

> **Captured evidence, not current guidance.** This report records one Phase 1 execution of the
> [structural search roadmap](../plans/2026-10-18-orc-structural-search-roadmap.md) under the
> [live Phase 1 plan](../plans/2026-10-18-orc-structural-search-live-phase1-plan.md). It ran on frozen runtime
> worktrees of `feat/orc-structural-search` and gives no instructions for running anything now. For current
> guidance start at the [documentation index](../index.md) and the
> [driver README](../../experiments/orc_structural_search/README.md).

**Result.** Phase 2 is **not selected** for family (a). The frozen decision rule fired on `anchors_inverted`. On
`pure-result-replay`, batch 0, the OpenAI judge rated the inert stub anchor above the upstream solution (3 > 2).

One further rule would have stopped Phase 2 even if that anchor had held: **within tolerance**. Neither task
separated. On `resume-projection-integrity` the largest gap between arm means was 1.13 rubric points against a
threshold of 1.86. On `pure-result-replay` it was 2.00 against 2.39.

DIRECT was not the sole winner, so that rule would not have fired. It ranked 5th of 6 arms on
`resume-projection-integrity` and 3rd (tied) on `pure-result-replay`. The I1 interface did not collapse: its two
uncontaminated children both have skeletons that differ from the parent.

**This is an inconclusive pilot, not evidence that the neighbourhood is flat.** The separation threshold is two
pooled within-arm standard deviations, 1.86 and 2.39 points on the 0–8 rubric. The anchor gap is the judge-averaged
difference between the merged upstream fix and an inert stub:
- `resume-projection-integrity`: 1.0 and 2.0 in its two batches;
- `pure-result-replay`: 0.0 and 1.5 (per judge, the range is −1 to 2).

The threshold exceeds every anchor gap on `pure-result-replay` and one of the two on `resume-projection-integrity`.
So on this measure, the rule asks for a difference between workflows about as large as, or larger than, the
difference between the merged fix and an inert stub. Under the charter's decision rule the result is recorded as
uncertain, not as disproof. The roadmap's response to an inconclusive pilot is a better-targeted experiment, with
the measure as the bottleneck to improve first ([Next Step](#next-step)).

## Scope And Criterion

| | |
| --- | --- |
| Question | Do the five authored catalog seeds and the accepted unguided I1 children of `direct` differ in blind judge quality by more than two pooled within-arm SDs on both tasks? The rules: DIRECT is not the sole winner and I1 has not collapsed |
| Family | (a) review/planning improvement: rung 2 `resume-projection-integrity` (base `1cd60767`) and rung 4 `pure-result-replay` (base `f80e551a`) |
| Criterion | [`criteria/phase1.json`](../../experiments/orc_structural_search/criteria/phase1.json), sha256 `84ee6307ab39e74710154654133585e53aaa9b329e5c7f9918dc9ee2f055cc80`, last changed in `27161923` before any score existed; both pools' `results.json` carry this hash |
| Primary measure | Failure-inclusive blind rubric mean per task and arm. The rubric is `score.orc`'s four criteria at 0–2 each, summed to 0–8 and averaged over the two judges. A failed or timed-out evaluation counts 0; incidents and quota incidents are excluded and counted |
| Judges | `claude-opus-5-5` and `gpt-6-sol` (Codex CLI). Upstream and stub anchors were repeated in every batch |
| Scale | Catalog: 5 seeds × 2 tasks × 2 replicates. Unguided: 6 I1 episodes against `direct` under `topology-only`. Each accepted child was evaluated on both tasks × 2 replicates; the plan said one replicate, and the driver ran the catalog's 2, which added 12 child evaluations |
| Rules | Separation tolerance 2 SD, with a floor of 0.5 points, required on 2 tasks. Collapse threshold 0.75. Anchor spread limit 2 |
| Hidden acceptance | Descriptive only; it gates nothing |
| Runtime | Runtime `RT` (`/home/ollie/ss-runtime`) at `89a67713` for every scored evaluation and every Phase 1 judge call (the smoke, its judge dry-check and the incident-1 run ran before `RT` was recreated at the shim fix). The driver ran at `89a67713` for the main run, `b6efe738` for the quota continuation (`/home/ollie/ss-driver`) and `edd486b1` for the capacity relaunch (`/home/ollie/ss-driver2`). Pools were built from the branch at `2166bc79` |

**The catalog and its realized calls.** The seeds are in
[`seeds/`](../../experiments/orc_structural_search/seeds/). Every coder is `claude-sonnet-5-5` and every
reviewer or judge inside a seed is `gpt-6-sol`.

| policy | structure | realized calls per run |
| --- | --- | --- |
| `direct` | one coder call | 1 |
| `plan_then_implement` | `claude-opus-5-5` plan, `gpt-6-sol` plan review, `claude-opus-5-5` plan revision, then the coder | 4 |
| `implement_review_revise` | coder, then a reviewer/revise loop (`:max 3`) | 6 in every run |
| `best_of_n` | two coder proposals, a `gpt-6-sol` judge, then the coder implements the chosen one | 4 |
| `implement_check_diagnose_repair` | coder, then dev-check, with diagnose/repair only on a failed check | 1: no check ever failed |

**The two I1 children** (from episodes 6 and 10) each rewrote `direct` into the same new control flow: implement,
run the agent-visible `dev-check`, and on a failed check re-call the coder with the check output, at most 3 coder
calls. Their skeletons differ from the parent and from each other. In all 8 of their evaluations the first check
passed, so they realized 1 call each, like `direct`.

## Allocation, Calls And Wall Clock

| item | calls |
| --- | --- |
| Smoke (one `direct` evaluation) | 1 |
| Incident-1 run, stopped (below) | 21 |
| Main run, continuations and relaunches (`E` = `/home/ollie/ss-evidence2`): 146 settled in its ledger, less the 19 session-limit refusals that exited within 2 s | 127 |
| Judges: the smoke dry-check (2) and Phase 1 (2 tasks × 2 judges × 2 batches = 8) | 10 |
| **Charged provider calls** | **159 of the 160 allocated** |

**Refused calls.** 29 calls were refused by a provider limit:
- 19 session-limit refusals exited within 2 s with no work: 13 catalog calls (12 at launch, 1 at the third call of a `plan_then_implement` run) and 6 episodes.
- 1 session-limit refusal exited after 106 s with no output.
- 4 Codex capacity refusals of the reviewer stopped after 27–122 s, having run 8–33 commands.
- 5 session-limit refusals came after 25–70 minutes of work.

The controller ruling of 2026-10-18 exempts only zero-work, immediate refusals. So only the 19 are uncharged, and
the other 10 count. Registered calls, refusals included, total 178. A call is one registered CLI invocation: native
subagents inside a Claude or Codex call count as part of it. The incident-1 count comes from that run's shim call
records; its own ledger settled 12 because 3 launches were killed in flight.

**Wall clock.**
- **Elapsed:** the smoke started about 11:57 PDT on 2026-10-18 and Phase 1 at 12:29. Judging ended at 09:26 on
  2026-10-19 and summarize at 10:41.
- **Interruptions included in that span:**
  - the incident-1 stop and relaunch (14:10–14:20);
  - the first Claude session-limit stop (about 17:30–18:46);
  - the second session-limit pause (about 20:11–22:35).
- **Capacity relaunch:** 06:42–07:53. This was generation time, not an interruption.
- **Hidden-acceptance passes:** 17 minutes for the first pool's summarize and about 58 minutes for the second.
- **Per-evaluation means:** in the per-policy tables. They range from 1,754 s (an unguided child) to 4,718 s
  (`plan_then_implement` on `pure-result-replay`).

**Metering coverage: unavailable.** All 79 log rows record `consumption: "unavailable"`, so token and cost figures
are absent. Cost here is calls and wall clock only. The server-side model revision is also unavailable.

## Per-Policy Results

Means are failure-inclusive. `n` counts the evaluations in the mean; `failed` is included in `n`.

**`resume-projection-integrity`.**
- **Separation:** pooled SD 0.93, threshold 1.86, largest gap 1.13. Not separated.
- **Anchors:** OK. Spread is 2 for `claude-opus-5-5` and 1 for `gpt-6-sol`.
- **DIRECT:** rank 5.

| arm | mean | SD | n | failed | hidden (descriptive) | calls mean | wall clock mean s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `best_of_n` | 5.25 | 1.06 | 2 | 0 | 0.77 | 4 | 2,578 |
| `implement_check_diagnose_repair` | 5.00 | 0.71 | 2 | 0 | 0.78 | 1 | 2,229 |
| `implement_review_revise` | 5.00 | 0.00 | 2 | 0 | 0.80 | 6 | 3,379 |
| `plan_then_implement` | 4.75 | 1.77 | 2 | 0 | 0.76 | 4 | 3,128 |
| `direct` | 4.50 | 0.71 | 2 | 0 | 0.78 | 1 | 1,776 |
| unguided (pooled) | 4.13 | 0.75 | 4 | 0 | 0.77 | 1 | 1,895 |
| child of episode 6 (`32729314…`) | 4.25 | 1.06 | 2 | 0 | 0.79 | 1 | 2,036 |
| child of episode 10 (`42724572…`) | 4.00 | 0.71 | 2 | 0 | 0.76 | 1 | 1,754 |

**`pure-result-replay`.**
- **Separation:** pooled SD 1.20, threshold 2.39, largest gap 2.00. Not separated.
- **Anchors:** inverted. Spread is 0 for `claude-opus-5-5` and 2 for `gpt-6-sol`.
- **DIRECT:** rank 3, tied with `best_of_n`.

| arm | mean | SD | n | failed | hidden (descriptive) | calls mean | wall clock mean s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `implement_review_revise` | 4.00 | 0.71 | 2 | 0 | 0.74 | 6 | 4,199 |
| `implement_check_diagnose_repair` | 3.50 | 0.00 | 2 | 0 | 0.72 | 1 | 2,353 |
| `direct` | 3.25 | 0.35 | 2 | 0 | 0.84 | 1 | 2,947 |
| `best_of_n` | 3.25 | 1.06 | 2 | 0 | 0.59 | 4 | 2,905 |
| unguided (pooled) | 2.88 | 0.75 | 4 | 0 | 0.70 | 1 | 2,311 |
| `plan_then_implement` | 2.00 | 2.83 | 2 | 1 | 0.60 | 4 | 4,718 |
| child of episode 6 (`32729314…`) | 3.00 | 0.71 | 2 | 0 | 0.66 | 1 | 1,788 |
| child of episode 10 (`42724572…`) | 2.75 | 1.06 | 2 | 0 | 0.75 | 1 | 2,834 |

**Why `plan_then_implement` has a 0.** Its replicate-2 coder printed a complete final summary after about
3,820 s. Its process then did not exit before the seed's 5,400 s step timeout (`provider_timeout`), and the
evaluation ended at 5,849 s. The frozen rule scores this failure 0 (valued-only mean 4.00). Whether the policy or the
CLI caused it is not established.

Without that run, `plan_then_implement` would have one value and drop out of the compared arms. The largest gap
would then be 1.13 (`implement_review_revise` 4.00 against unguided 2.88).

**The readout's scope.** Of the 20 catalog jobs, 19 were valued and the other is that timeout. Every quota or
capacity incident was superseded by its relaunch. The readout's `incidents` and `quota_incidents` are 0 per job.

**Hidden acceptance (descriptive).** The arms are nearly level on `resume-projection-integrity` (0.76–0.80). On
`pure-result-replay` they spread from 0.59 (`best_of_n`) to 0.84 (`direct`). This rank order does not follow the
rubric's.

### Anchors And Judges

| task | batch | judge | upstream | stub |
| --- | --- | --- | --- | --- |
| `resume-projection-integrity` | 0 | `claude-opus-5-5` | 3 | 2 |
| | 0 | `gpt-6-sol` | 3 | 2 |
| | 1 | `claude-opus-5-5` | 2 | 0 |
| | 1 | `gpt-6-sol` | 4 | 2 |
| `pure-result-replay` | 0 | `claude-opus-5-5` | 2 | 1 |
| | 0 | `gpt-6-sol` | **2** | **3** |
| | 1 | `claude-opus-5-5` | 2 | 1 |
| | 1 | `gpt-6-sol` | 4 | 2 |

**The upstream anchor scores at or below every candidate in its batch.** Judge-averaged, it scored 2–3, against
candidates at 2–6. On `resume-projection-integrity` it scored 5 and 4 in the smoke batch, where it was the only
candidate, against 3 and 3 here. This suggests the scores depend on what else is in the batch. The judges do not
place the merged solution at the top of the scale.

**All-judges-equal agreement per criterion.**

| task | `root_cause` | `scope` | `generality` | `layering` |
| --- | --- | --- | --- | --- |
| `resume-projection-integrity` | 15/18 | 8/18 | 10/18 | 5/18 |
| `pure-result-replay` | 16/17 | 5/17 | 11/17 | 12/17 |

No judge was excluded.

## Unguided I1: Diversity And Collapse

Six I1 episodes were accepted. Each of the 6 quota-refused episode attempts was superseded by its relaunch.

| figure | driver readout (all 6 accepted children) | readout over uncontaminated children (2) |
| --- | --- | --- |
| distinct skeletons | 5 | 2 |
| revisit rate | 0.17 (episode 7 copied episode 6's workflow) | 0.0 |
| terminal-only share (collapse) | 0.0 | 0.0 |
| allocation-distinct | 0 | 0 |
| collapsed (threshold 0.75) | no | no |

The driver's `episodes` count (6 accepted, 6 quota incidents) still includes the four contaminated episodes, and
was not recomputed. The collapse verdict covers I1 only; see [Limitations](#limitations).

## Scans

| subject | hits | verdict |
| --- | --- | --- |
| Evaluation runs with hits: 10, namely 4 final catalog runs, 3 superseded quota attempts and 3 runs of the uncontaminated children | own-session persisted output, memory or subagent transcripts; the stale editable install's path; `ls runs` names; the Codex reviewer's own tmux skill file | all cleared |
| Evaluation runs with hits, children of contaminated episodes: 4 | as above | marked contaminated with their episode, as were their 12 sibling evaluations without hits |
| Episodes 6 and 10 | operator rescans with both solution hashes | cleared |
| Episodes 7, 8, 9, 11 | 7 copied episode 6's `direct.orc`; 8 read `E/readout.json`, `E/log.jsonl` and candidates; 9 and 11 printed siblings' `direct.orc` | **contaminated**. Their 16 child evaluations are excluded from the readout entirely (`scoring.contaminated_children`) |
| Judge `claude-opus-5-5`, both pools (6 and 4 hits) | the judge session reading its own persisted tool results under its own session directory | cleared |
| Judge `gpt-6-sol`, both pools | 0 | — |

**The episode scan missed episode 11.** The scan matches path patterns only. Episode 11 ran
`for e in 6 7 8 9 10; do diff … episode-$e/…` with relative paths, and the driver scan raised no hit for that
command. The episode's 9 hits were other reads. The
contamination was found by reading every accepted episode's transcript.

## Decision Under The Roadmap Rule

The criterion's decision applies the first rule that fires:

1. **Anchors.** `anchors_inverted` **fired**: `pure-result-replay` has `anchors_ok: false`.
2. **Separation.** Within tolerance: 0 of the required 2 tasks separated.
3. **DIRECT.** Not the sole winner on any task.
4. **Collapse.** Available (0.0) and not collapsed.

`phase2_selected: false`. Under the roadmap's Decision Points, the separation stop alone would give the same
outcome: "everything within tolerance is recorded under the charter's decision rule and Phase 2 is not selected for
the family."

**Not selected.** Phases 2–5 are not selected for family (a), and no Phase 2 budget is requested. The offline Phase 2
apparatus ([Phase 2 plan](../plans/2026-10-18-orc-structural-search-phase2-plan.md)) stays built and unrun.

**The Phase 1 exit gate.** The gate asks that "whole-run quality and cost differences between structurally
distinct candidates are measured". It is met for cost: realized calls range from 1 to 6 and wall clock from 1,754 s to 4,718 s.
For quality, the differences were measured but sit within the measure's noise and anchor resolution.

## Limitations

**Infrastructure incidents.**
- **Incident 1** (2026-10-18 14:10). The task repository reads `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. Agents' tool
  processes inherited it, and the repository's tests overwrote result files. The run was stopped, 21 calls having
  been spent. The shim was fixed to strip the attempt's `ORCHESTRATOR_*` variables, and the catalog was relaunched
  in fresh roots. Nothing from that run is scored.
- **Incident 2.** The Claude subscription session limit ended 16 of 20 catalog evaluations and all 6 episodes:
  12 evaluations were refused at launch, and 4 `plan_then_implement` runs were cut off mid-work. The quota guard
  (`quota.py`) classified them, and `--continue` relaunched them as new attempts.
- **Incident 2b** (about 20:00–22:35). A second session limit ended 3 more catalog attempts (2
  `implement_review_revise`, 1 `plan_then_implement`) after 25–80 minutes of work. The quota guard paused new
  launches until 22:35, and the 3 were relaunched.
- **Codex capacity.** `ERROR: Selected model is at capacity` stopped 4 `implement_review_revise` runs at the
  reviewer. Under the controller ruling these are provider-availability incidents, and all 4 completed when
  relaunched.
- **Lost runs.** The roadmap says infrastructure stops are resumed, never relaunched. Under the owner's 2026-10-18
  directive to rerun the quota-affected work, quota and capacity incidents were relaunched as new attempts instead.
  The earlier attempts' work was discarded, and their calls are charged except the 19 immediate refusals.
- **Attempt rates.**
  - Catalog: 43 attempts for 20 jobs (2.15). The roadmap budgets 1.5.
  - Episodes: 12 attempts for 6 accepted (2.0).
  - Child evaluations: 24 for 24.

**The measure.**
- The upstream anchor scores at or below every candidate in its batch. One anchor pair is inverted.
- Anchor scores appear to shift with batch composition.
- Judges agree on `scope` in only 5–8 of 17–18 clones.
- With two replicates per arm, each SD rests on one degree of freedom.
- Policies were rated in different batches on each task.

**The agent-visible check carried no signal.** `dev-check` runs the base's existing tests in the task's modules,
which were green at base. It passed on the first try in every evaluation that ran it. So
`implement_check_diagnose_repair` never reached diagnose/repair, and both I1 children's loops stopped after one coder
call. In realized behaviour these check-gated structures are `direct` plus a check.

**The unguided arm is small and the episode sandbox is not isolated.** Four of six accepted episodes were
contaminated: the mutator sandbox can read sibling episode trees and the evidence root. The unguided arm therefore
rests on two children. The episode scan also misses relative-path reads.

**The three-arm compile-only readout was not run.** The roadmap's Phase 1 lists a three-arm compile-only readout
(I3, I1, I2 with `E₀` episodes each, plus paid whole-run evaluation of a stratified subset). The plan's allocation
budgeted no `E₀` episodes, and I3 is not implemented. A controller ruling (2026-10-19) records the readout as an
unmet gate. So the collapse verdict and the acceptance and locality figures exist for I1 only, and this Phase 1 gate
is unmet.

**Other limitations.**
- **Runtime defect.** Agent turns inside `loop/recur` hit `agent_turn_unresolved` on the second turn ("native store
  does not show exactly one completed turn", `orchestrator/workflow/evaluated/agent_turns.py` `_verify_completion`).
  It ended two evaluations of episode 11's child, which is excluded anyway.
- **Stale editable install.** The host's `pip -e` install points at `.worktrees/omp-i1-prerequisites`. In at least
  two scored evaluations (`6758a0cb`, `67f01d1f`), an agent script imported `orchestrator` from that tree. The scans
  cleared them as not reading the solution, but those agents' own checks partly ran against another tree. Hidden
  tests run with `PYTHONPATH` set to the scored copy.
- **One timeout.** The `plan_then_implement` `provider_timeout` on `pure-result-replay` replicate 2 is scored 0
  under the frozen rule, although its coder had printed a final summary (above).
- **Criterion amendment.** The criterion's failure-inclusive amendment and the timeout rule were recorded before any
  score existed. Its `primary_amendment` field documents them.
- **Contaminated children.** A controller ruling (2026-10-19, `149f6f09`) was made after the outcomes existed but
  before any score. It drops contaminated episodes' children from the readout entirely (`excluded_children`). The
  frozen criterion text would instead have counted their one failed row as 0.

## Next Step

Under the roadmap, an inconclusive pilot calls for a better-targeted experiment, not a verdict. This report selects
nothing.

A follow-up would need, in order:
1. **A measure whose anchors discriminate.** The upstream fix must score well above every candidate and the stub,
   independent of batch composition. Examples are absolute rubric anchoring or pairwise comparison against upstream.
2. **A family whose agent-visible check fails often enough** that check-gated control flow actually branches.
3. **Mutator isolation** from sibling episodes and the evidence root.
4. **The `agent_turn_unresolved` fix** for loop agent turns.
5. **The compile-only three-arm readout:** I3, I1 and I2 with `E₀` episodes each, plus the roadmap's paid
   whole-run evaluation of a stratified subset `S`. I3 must be implemented first.

Any of these needs a new owner selection and provider budget.

## Evidence

The evidence stays outside the repository and is retained:
- the evidence root `/home/ollie/ss-evidence2`;
- the work root `/home/ollie/ss-work2`;
- the pools `/home/ollie/ss-pools/phase1/{resume-projection-integrity,pure-result-replay}`;
- the incident-1 roots `ss-work-incident1` and `ss-evidence-incident1`;
- the smoke roots `/home/ollie/ss-evidence-smoke`, `/home/ollie/ss-work-smoke` and `/home/ollie/ss-pool-smoke`;
- the operator scripts and logs in `/home/ollie/ss-evidence-meta`.

| file | sha256 |
| --- | --- |
| `ss-evidence2/log.jsonl` (79 rows) | `796d689337b1186f52650b8d4f41ae3fc514ee3abd2db21b368c563eea20c1fc` |
| `ss-evidence2/calls.json` (call ledger) | `08716ca68edb8cd5883b8de485e0d94f12b90af22c47575ebc14c6eb67eec7e9` |
| `ss-evidence2/readout.json` (driver) | `3b3c47e5a91d2230214932ceca041ab99df9a2870ba4557b1a4ffb2c079201dd` |
| `ss-evidence2/phase1-readout.json` (`scoring readout`) | `94ade574e7b6848a8a9435453864008547e8c2c3c3dea38de96eff5d6d65f8b9` |
| `ss-evidence2/joined.json` (28 joined rows) | `daf21376443b95316a2641f35ba2d07e40f95e62b85a19c6bf9fe9094b8fe545` |
| `resume-projection-integrity/records/results.json` | `2426abe50453a8d86d8166e6b2b9b4a7bc4b4e3650163edce12ef2f02282774e` |
| `pure-result-replay/records/results.json` | `d8dcfc37d94939f7bb82a5afc62b2fd7ebffe6669c6c56f73034e7d9c5cd1539` |

Every number above comes from `summarize`'s `results.json`/`results.md` (clone-id join) and from
`python -m experiments.orc_structural_search.scoring readout` over them, the log and the driver readout. Exceptions:
- the call totals come from the call ledger, the shim call records and the judge state directories;
- the timeline comes from the controller ledger and record timestamps (the smoke start, the second pause and the capacity relaunch);
- the children's control flow comes from the episode diffs.
