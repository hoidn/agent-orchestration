# E-B3: Maintained Workflows Against A Single Call On Calibration Rung 1

> **Captured evidence, not current guidance.** This report records one exploratory batch.
> - **Runtime.** It ran on a historical frozen runtime: `6f43fae1`, tag `eb3-runtime-frozen`. That runtime is E-B2's
>   `e8882086` plus the reviewed model-guard harness files. It is not a qualification of the current executable
>   surface, and it gives no instructions for running anything now.
> - **Current routing.** For current guidance, start at the [documentation index](../index.md), the
>   [workflow design lessons](../orc_workflow_design_lessons.md) and the
>   [comparison harness](../../experiments/compare/README.md).

**Result.** Neither primary claim was evaluated. Too few valued runs remained to meet the frozen run floors (three per
arm), and no run was replaced or partially graded.
- **`design_review_execute`: 0 of 3 valued runs.**
  - Runs 1 and 3 failed with executor `provider_timeout` at the 14,400 s limit. Both were exposed to the ENOSPC
    incident (below); no cause is attributed.
  - Run 2 completed but was excluded before pooling, because its executor read files from the main checkout.
- **`reviewed_change`: 2 of 3 valued runs.** Run 3 failed with `provider_timeout` after a host-resource pause used up
  its coder's 5,400 s budget. It was not resumed under R3.

The scores below are descriptive only:
- they come from five retained runs (seven patch versions);
- they are not a criterion verdict and not an efficacy estimate;
- the two judges disagreed about whether review and revision helped.

The report is complete, but the cohorts it describes are incomplete.

## Question And Criterion

The task is rung 1 of the difficulty calibration, `cf1-generic-unions` (base `c77e7ec0`, solution `1798fc70`). It ran
as the R48 package variant `cf1-generic-unions-r48`, sha256 `5e2ef0a4aa54b1c9938b57ffc65d18f9099311af9c66567c4092402c605f0f80`.
The upstream anchor of that variant is restricted to `orchestrator/`, `specs/` and `workflows/`.

| | |
| --- | --- |
| Active criterion | [`eb3-judge-primary.json`](../../experiments/compare/criteria/eb3-judge-primary.json), sha256 `0126dd13322516cd6f319fa623966d898176a807eaa28715f31cd2ff5fba3798`, commit `e4352809` |
| Superseded criterion, unchanged | [`eb3.json`](../../experiments/compare/criteria/eb3.json), sha256 `6208b5c0…`, commit `f7f91591`, and its `start.json`. This was the hidden-acceptance primary, frozen before launch |
| Protocol | [E-B3 plan](../plans/2026-10-15-calibrated-experiment-e-b3-plan.md) and its judge-primary addendum |
| Design | Nine runs: three each of `design_review_execute`, `reviewed_change` and the control `direct_task`. No replacement, no `best_of_n`. R3 resumes provider-infrastructure stops only |

### The amendment

The primary measure was amended after launch and before any pool, score or hidden result existed. At that point four
runs were live and five were pending.
- **The owner's reply,** recorded by the coordinator at 2026-10-15T22:44:49Z: "don't use hidden tests, or only use
  them as secondary criterion. they are imo too brittle and hard to design correctly".
- **The owner's choice of measure,** at 22:51:22Z: the existing blind rubric ("Rúbrica ciega existente").
- **The coordinator chose the numerical thresholds,** and an independent review approved them before the freeze
  (22:53:40Z).

| claim | rule (as frozen) | written as | origin |
| --- | --- | --- | --- |
| `design_review_execute` | mean blind score at least 1 point above the control's | `minus_control >= 0.9` | Coordinator: one ordinal step on one of four 0–2 criteria. With exactly three valued runs per arm, 0.9 is the same rule as "≥ 1" on the 1/6 (two-judge) or 1/3 (one-judge) lattice, and it is safe against float error |
| `reviewed_change` | mean paired gain (final minus first) at least 0.5, and no run worse | `paired_gain_mean >= 0.5`, `paired_gain_runs_negative <= 0` | Reused from E-A's frozen criterion. E-A set it below September's observed +0.58, which was not preregistered |
| both | `<arm>.runs >= 3` | run floors | unchanged |

**Hidden acceptance is descriptive.** It is computed by the existing `summarize` and reported last, in the appendix.
It gates no validity, selection, ranking or exclusion.

## What Was Compared

| arm | top-level bindings (frozen) | time limits |
| --- | --- | --- |
| `design_review_execute` | planner and reviser `claude-opus-5-5`; reviewer and executor `gpt-6.1-sol` (Codex CLI) | three calls of 3,600 s, then the executor at 14,400 s |
| `reviewed_change` | coder `claude-sonnet-5-5`; reviewer `gpt-6-sol` (Codex CLI) | 5,400 s per call |
| control `direct_task` | `gpt-6.1-sol` (Codex CLI), effort high | 14,400 s |

**The control is one Codex CLI invocation, not one primitive model request.**
- The task base's `AGENTS.md` (lines 39–43) tells Codex to delegate: implementation to `gpt-6-luna` and review to
  `gpt-6-sol`.
- Native children ran in every arm that made a Codex call, and in the Codex judge (see Calls And Models).

**Claude subagents were pinned to Opus.** The shim set `CLAUDE_CODE_SUBAGENT_MODEL=claude-opus-5-5` and
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`. That pin applied even under the Sonnet coder, so `reviewed_change` ran as a
Sonnet/Opus hybrid.

**The frozen model list was incomplete.** The criterion's `model_policy` named only the top-level OpenAI bindings, and
its experiment text said "one gpt-6.1-sol call".
- Native `gpt-6-luna` and `gpt-6-sol` children, and one `gpt-6-astra` child, were found from metadata before any
  quality readout.
- An independent review (`native-model-review.md`) ruled that native non-Fable children are part of the pinned CLI
  invocation. They are disclosed, they gate nothing, and the criterion was not changed.
- The only hard model rule is that no Fable model is used.

## The Calibration It Rests On

- **Post-data qualification.** Rung 1 qualified on review blockers 1, 1 and 1, under the owner-approved post-data
  continuation (R56; [continuation report](2026-10-15-calibration-continuation.md)). It did not pass the original Task
  8 gate ([calibration report](2026-10-14-task-difficulty-calibration.md)).
- **Calibration hidden fractions.** Its single calls passed 149, 148 and 154 of 164 hidden tests. These are context
  for the appendix only.
- **Same delegation instruction.** The calibration controls ran under the same `AGENTS.md` delegation instruction. That
  is a fact about the source; nothing is inferred about what those agents did.
- **E-B2's uncalibrated performance figures stay withdrawn,** and nothing here compares against them.

## Runs

`wall_clock_sec` is the memo's mtime minus the first provider start (`prepare.collect`). It excludes waiting for
admission or reaping. It includes host contention and the RC3 pause.

| run | run id | outcome | registered CLI calls | wall clock s | scan hits | verdict | valued |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DRE1 | `20261015T222114Z-eniw0y` | failed: executor `provider_timeout` (14,400 s) | 4 | 16,584 | 34 | cleared | no |
| DRE2 | `20261015T222114Z-0xxo9y` | completed | 4 | 14,797 | 23 | **contaminated** | no (excluded before pooling) |
| DRE3 | `20261016T001445Z-ehdo84` | failed: executor `provider_timeout` (14,400 s) | 4 | 16,640 | 74 | cleared | no |
| DT1 | `20261015T222114Z-kbtwjf` | completed | 1 | 4,015 | 87 | cleared | yes |
| DT2 | `20261015T232815Z-p996m7` | completed | 1 | 2,775 | 38 | cleared | yes |
| DT3 | `20261016T045700Z-84kjmh` | completed | 1 | 6,251 | 54 | cleared | yes |
| RC1 | `20261015T222114Z-s4db2e` | completed, review loop `UNRESOLVED` | 6 | 6,040 | 22 | cleared | yes |
| RC2 | `20261016T000200Z-ibw2jd` | completed, review loop `UNRESOLVED` | 6 | 5,555 | 16 | cleared | yes |
| RC3 | `20261016T065641Z-qcdj6a` | failed: coder `provider_timeout` (5,400 s) after a host-resource pause | 1 | 5,922 | 6 | cleared | no |

**Totals.**
- There were 28 registered generation CLI calls over the nine attempts.
- Summed attempt wall clock is 78,578.9 s. That is a sum over attempts, not the batch's elapsed time; generation ran
  from 2026-10-15T22:21Z to 2026-10-16T08:35Z.
- The harness means cover valued runs only. `direct_task` has 3 runs at 1 call and 4,347 s on average.
  `reviewed_change` has 2 runs at 6 calls and 5,797 s on average.

**Excluded run (DRE2).**
- A native Codex child of the executor (call 4) ran `sed -n '1,260p'` on six main-checkout files, including
  `docs/workflow_drafting_guide.md` and `specs/dsl.md`.
- Evidence: rollout `…ffbaf1009587`, line 1684. The matching output, line 1699, contains the full content of at least
  two of those files.
- DRE2 was adjudicated contaminated (D5) before pooling. It is never graded.

**Schedule.**
- The queue kept its launch order and ran at most four runs at once.
- Pauses changed the gaps between runs:
  - for the amendment, 22:44–22:53Z;
  - after the disk incident, 00:55Z to DT3's start at 04:57Z;
  - before RC3, through a manual admission gate.
- DT3 started only after the other seven had ended. RC3 started alone at 06:56:41Z, once all eight others were
  terminal and `/home` had 76.6 GB free.
- The RC3 gate wrapped a frozen copy of its original command (wrapper `bc6adc1a…`, frozen command `0f2ead67…`). The
  scientific invocation was byte-identical.
- So arm interleaving held for runs 1–2 and not for run 3. No timing difference is attributed to the arms.

## Primary Results (Descriptive; Both Claims Not Evaluated)

Each version is scored on the blind rubric: root cause, scope, generality and layering, each 0–2, for a total of 0–8.
The score is the mean of the two judges. Batches mixed stages: batch 0 holds RC1 final and RC2 first, batch 1 holds
RC1 first and RC2 final, and batch 2 holds DT1–3. Both anchors were in every batch.

| version | batch | `claude-opus-5-5` | `gpt-6-sol` | mean |
| --- | --- | --- | --- | --- |
| DT1 final | 2 | 6 | 5 | 5.5 |
| DT2 final | 2 | 4 | 4 | 4.0 |
| DT3 final (4 `docs/design/` files stripped, D8) | 2 | 5 | 4 | 4.5 |
| RC1 first | 1 | 8 | 5 | 6.5 |
| RC1 final | 0 | 7 | 7 | 7.0 |
| RC2 first | 0 | 3 | 0 | 1.5 |
| RC2 final | 1 | 4 | 4 | 4.0 |

| measure (`results.json`) | both judges | `claude-opus-5-5` alone | `gpt-6-sol` alone |
| --- | --- | --- | --- |
| `direct_task.mean` (3 runs) | 4.67 | 5.00 | 4.33 |
| `reviewed_change.mean` (2 runs) | 5.50 | 5.50 | 5.50 |
| `reviewed_change` paired gain, RC1 / RC2 | +0.5 / +2.5 | −1 / +1 | +2 / +4 |
| `reviewed_change.paired_gain_mean` | +1.5 | 0.0 | +3.0 |
| `reviewed_change.minus_control` (secondary; confounded by model and time limit) | +0.83 | +0.50 | +1.17 |
| `design_review_execute` | no valued run | — | — |

- **Where the numbers come from.** The both-judges column is `summarize`. The per-judge columns come from
  `results.json` `clones.<id>.ratings`, joined by clone id.
- **Disposition.** `summarize` marks the RC gain entries met (+1.5 ≥ 0.5; 0 runs negative) and `reviewed_change.runs`
  not met (2 < 3). No DRE measure exists, so the DRE verdict entries carry `observed` and `met` as null. Under the
  verdict rules both claims are therefore **not evaluated**.
- **The judges disagree on revision.** The +1.5 average comes entirely from `gpt-6-sol`. Opus rated RC1's revision
  lower (8 → 7) and RC2's higher (3 → 4).
- **Exact agreement per criterion,** over all 13 clones: root cause 7, scope 5, generality 10, layering 11.

| anchor | judge | batch 0 | batch 1 | batch 2 |
| --- | --- | --- | --- | --- |
| upstream | `claude-opus-5-5` | 4 | 4 | 2 |
| stub | `claude-opus-5-5` | 1 | 0 | 0 |
| upstream | `gpt-6-sol` | 1 | 2 | 1 |
| stub | `gpt-6-sol` | 2 | 2 | 2 |

**The anchors.**
- Opus scored the upstream change above the stub in every batch.
- `gpt-6-sol` scored the upstream change **below** the stub in batches 0 and 2 (1 against 2), and equal to it in
  batch 1 (2 against 2).
- In batch 0, `gpt-6-sol`'s stated reason for its upstream rating includes a "malformed indentation block" in the loop
  runtime. That is the judge's judgment in one batch; it was not independently checked.
- These are observations about the instrument's scores only. No conclusion about rubric validity is drawn from them.
- No judge was excluded, re-rated or rescaled after scoring (`anchor_use`).

## Judges, Pool And Summarize

- **Pool.** 13 clones in 3 batches (4, 4, 5): seven patch versions and six anchor clones. `mapping.json` sha256 is
  `7a702929…`, bound to the active criterion. `git apply --check` passed for all 8 collected patches.
- **Judges.** Each judge made 3 registered calls and bound `0126dd13…`. Both completed and passed `verify-pool` (13
  clones unchanged), the structural journal check and the guard identity check.
  - `claude-opus-5-5` (`20261016T090009Z-zzcpml`) had 10 scan hits, all cleared: the judge's own persisted tool
    outputs.
  - `gpt-6-sol` (`20261016T093552Z-de6hce`) had 0 hits.
- **`summarize`.**
  - It ran once, started at 09:59:38Z, and exited 0.
  - The results file is `results.json`, sha256 `3c29fa7f…`.
  - After it finished and before any measure was read, the coordinator ran a model census, a `-tmp-` sweep and a
    Codex-rollout check over its temporary root. All found zero.
  - The manual validity checklist (`manual-final-validity.json`) passed within the recorded limits.
  - The primary readout came at 11:07:33Z; hidden acceptance was read after it.

## Calls And Models

These are metadata counts, not API requests, tokens or cost.

| scope | registered CLI calls | Codex rollouts (top / native) | Claude session files |
| --- | --- | --- | --- |
| Generation (9 attempts) | 28 (15 Codex, 13 Claude) | 15 / 61 | 32 |
| Judges | 6 (3 per judge) | `gpt-6-sol` judge 3 / 6; Opus judge 0 | Opus judge 10 |
| **Total** | **34** | **85** (18 / 67) | **42** |

The 18 top-level rollouts are the 18 Codex CLI invocations: 15 in generation and 3 by the judge.

**Post-archive lineage erratum (descriptive only).**
- The first final metadata file, `model-metadata-science-final.json` (sealed in the archive), classified two RC2
  child rollouts as top-level. Its RC2 split was 5 / 5, against 3 / 7 in fact.
- Each of those files begins with the child's own `session_meta` (a `thread_spawn` source with a parent thread),
  followed by an inherited copy of the parent's metadata. The first file classified the last row.
- `model-metadata-science-final-v2.json` classifies the first row instead. It agrees with
  `codex-native-lineage-generation-final.json` for every file.
- The archived first file is preserved, not resealed. Context-event counts, models, census, scans, scores and criteria
  are unchanged.

- **The pre-freeze S2 probe** (5 shim calls, 4 Opus sessions including a native subagent) is separate and not counted
  above.
- **Codex context-model events (330 in total)** are `turn_context` records, not calls:

  | model | events |
  | --- | --- |
  | `gpt-6-luna` | 172 |
  | `gpt-6-sol` | 135 |
  | `gpt-6.1-sol` | 21 |
  | `gpt-6-astra` | 2 |

  - Every top-level context used its configured model.
  - The two Astra events come from one native child of DRE1's executor (session `01a14285…`, depth 1).
  - The shared Codex config default is `gpt-6-astra` (sha256 `d0c2c9a3…`).
- **Claude assistant rows (raw):**
  - `claude-opus-5-5`: 3,309. These include all 490 of the Opus judge's rows.
  - `claude-sonnet-5-5`: 1,721.
  - That is 5,030 in total, plus exactly 1 Sonnet row recovered separately from a damaged RC2 line.
  - One RC2 conversational row is lost, with its type and model unknown.
- **The DRE planner, Opus judge and S2 sessions** were Opus. RC1 and RC3 sessions include pinned Opus subagents.

**No Fable within recorded coverage.** No Fable hit appeared in any recorded census, rollout, derived scan or sweep. That
is not absolute proof:
- the one lost row is unknown;
- the guard covers `PATH` lookups and the subagent environment only, so an absolute CLI path, a reset `PATH` or a
  direct API call would escape it.

The user's global Claude settings, which default to Fable, were not changed.

## Contamination Scan

All 354 hits were adjudicated before pooling (`run-contamination-review.md`, `run-adjudications.json`, per-hit
inventory).

| group | hits | ruling |
| --- | --- | --- |
| Executed read of main-checkout files (DRE2) | 1 | contaminated |
| Main-checkout paths printed by `cat` of a skill file, never accessed (DT2) | 7 | cleared |
| `gh` text printed by a skill file, with no network action (DRE3) | 1 | cleared |
| Own tmux sockets in the run's private, bwrap-bound `/tmp` (all nine runs) | 334 | cleared |
| The run's own persisted Claude tool output (DRE2, RC1, RC3) | 6 | cleared |
| The Codex CLI's ENOSPC log naming its own rollout (DRE1–3) | 5 | cleared |

**Shared-home observations (not hits, not contamination).** Home is detected, not sealed:
- DT1 read its own neovim LSP log in the shared home.
- DRE1 measured shared orchestrator state and a test-fixture cache with `du` and `ps`.
- DT3 listed file names under `~/.codex`.
- Every run read user skill files.

Each run had a private `/tmp`, process list and `/dev/shm`. Home, transcripts and the network were shared.

**Stale editable install.** An unqualified `import orchestrator` on the host resolves to a stale worktree.
- The executor ran with `PYTHONPATH=<runtime> -P`, and agents had `PYTHONPATH` stripped.
- No agent's actual imports are inferred.

## Incidents

### Host ENOSPC (2026-10-16 00:39Z, discovered 00:55Z)

**Cause.** RC1's private `/tmp` filled `/home` with about 62 GiB of pytest temporaries.

**Exposure was asymmetric.** No control run was exposed:

| run | storage-error strings |
| --- | --- |
| DRE1 | 16 in rollouts, 23 in shim output |
| DRE2 | 8 |
| DRE3 | 5 |
| RC2 | 4 |
| all others | 0 |

**What was lost or repaired.**
- **Raw records were never rewritten.** Codex rollouts hold 10 truncated writes, each followed by a valid retry with
  the same native ordinal. The derived scan view drops the 10 fragments and keeps the complete retries. The fragments
  and their first-attempt timestamps remain in the raw rollouts and in `derived-scan-freeze.json`.
- **RC2's Claude session:**
  - one `claude-sonnet-5-5` assistant row was recovered byte-identically;
  - one conversational row is lost;
  - one request-blob body is lost.
- **Three shim stderr tails are lost:** DRE1 call 4, DRE2 call 4, DRE3 call 2.
- **The scan used a derived view.** All nine runs were scanned through `derived_scan.py` (sha256 `60867a75…`) with
  freeze `derived-scan-freeze.json` (`970ad52b…`). Both were frozen and independently approved before any scan. The
  view applies 11 proven repairs, and the unchanged frozen `scan.py` reads it.

### Temporary-file cleanup

The coordinator archived closed trees only, after each run was terminal with no live process. Every archive passed a
zstd CRC check and an exact `tar` listing before the `tmp` was removed. Candidates, memos and guard files were kept.

| run | archive (`/var/tmp/…`) | sha256 | listed paths | permission method |
| --- | --- | --- | --- | --- |
| RC1 | `eb3-reviewed-change-run1-tmp-20261015.tar.zst` | `a4bd944f…` | 1,117,148 | recursive `chmod -R u+rwX` (after a first-pass `chmod 0700` on error), after the archive |
| DRE2 | `eb3-dre-run2-tmp-20261015.tar.zst` | `11c366e3…` | 403,043 | recursive `chmod -R u+rwX`, after the archive |
| DRE3 | `eb3-dre-run3-tmp-20261015.tar.zst` | `96103b9c…` | 306,661 | directories only |
| DT3 | `eb3-direct-run3-tmp-20261015.tar.zst` | `2c8b9fd9…` | 1,089,455 | directories only |
| RC3 | `eb3-reviewed-change-run3-tmp-20261016.tar.zst` | `546edfd7…` | 924,002 (plus 1 socket) | directories only |

**What can and cannot be claimed about permissions.**
- The RC1 and DRE2 archives preserve the original permissions.
- The recursive `u+rwX` added mode bits to files, and those bits are shared by any hard link outside the tree. So no
  claim is made that every host permission was left unaffected.
- File content hashes of the runtime, task and guard were unchanged when re-checked before pooling.

**Who cleaned what.**
- The coordinator performed no live cleanup. A reviewed live-garbage helper was refused at its own read-only
  preflight, and that refusal stood.
- DRE1's own agent ran `rm -rf` and `chmod -R u+w` on its own pytest garbage during its run.

**Large temporaries were not confined to one arm.** DT3's temporaries reached 57.8 GB apparent.

### RC3 host-resource pause (an operational deviation that was not preregistered)

**Why RC3 was stopped.** During RC3's first call, `/home` fell from about 19 GiB to about 4 GiB free within 50 s.
- At 08:06:47Z all 30 of RC3's processes were sent SIGSTOP, each identified by PID and start-time ticks recorded at
  the stop. A follow-up at 08:15:51Z (`rc3-resource-pause-uid-followup.json`) found the same PIDs and start ticks
  under uid 1000. Nothing else was stopped, and neither record was rewritten.
- No live cleanup was applied, and no safe way to recover capacity existed while RC3 was live
  (`rc3-resource-pause-review.md`).

**Why the timeout ran out.** RC3's coder call had a 5,400 s budget. It started at 06:56:41Z, so its deadline was
08:26:41Z. The orchestrator's deadline is monotonic, so the pause consumed the budget.

**How it unwound:**
1. 08:29:21Z: SIGCONT was sent to the host orchestrator process only, after the deadline plus 120 s. Its own timeout
   then ended the sandbox. No SIGCONT was sent to the sandbox or the model.
2. 08:35:09Z: at the fallback check, the outer `bwrap` was already gone, so **no SIGKILL was sent**.
3. 08:35:23Z: SIGCONT was sent to the host `tee` processes. EOF reached the orchestrator, and the memo became
   terminal: `failed / provider_timeout`.
4. 08:35:58Z: SIGCONT was sent to the queue wrapper and the queue.
5. 08:36:47Z: all 30 original processes were gone.

**How it is treated.**
- The timeout was caused by the pause, so it says nothing about the coder's capability.
- There was no R3 resume, no replacement and no partial grading.
- RC3's 5,922 s includes the pause.
- RC3's partial candidate is preserved in two forms:
  - a sealed diff (`rc3-partial-candidate.diff.zst`, sha256 `16026594…`), which represents two nested native Claude
    worktrees as gitlinks only and so is not the full partial candidate;
  - the science archive, which holds the full candidate directory including those worktrees' files.

## Cost

| | |
| --- | --- |
| Generation | 28 registered CLI calls; 78,578.9 s summed over attempts |
| Judges | 6 calls |
| Pre-freeze probe | 5 calls |
| Codex weekly window | account-wide: 73% before launch (2026-10-15T22:11Z). The window then reset; the new window rose from 1% (2026-10-16T00:28Z) to 54% (09:35Z) |
| Codex credits | 28,549.41 throughout |

These readings cover the whole account while other sessions were running, so they are not this experiment's cost.
Anthropic usage is not metered by the harness. No dollar or token figure is claimed.

## Limitations

- **Incomplete cohorts on one task.** DRE has 0 of 3 valued runs and RC 2 of 3. The scores describe five runs and
  give no reliable causal estimate. "Met" entries on two RC runs are not a success.
- **Post-data and post-launch.**
  - Rung 1 qualified post-data (R56), not under the original gate.
  - The primary measure was amended after launch and before any readout, at the owner's request. The owner chose the
    rubric and the coordinator chose the thresholds.
  - The original criterion and start record remain frozen.
- **The instrument.**
  - The rubric is unvalidated and ordinal.
  - Self-preference across model families is possible. Opus planned for DRE and pins RC's subagents, and `gpt-6-sol`
    reviews for RC and is in the same family as the control.
  - RC's paired gain compares scores from different batches.
  - `gpt-6-sol` scored the upstream (reference) change at or below the stub.
  - Agreement was moderate.
- **Model composition.**
  - Native Codex delegation took place, including one Astra child.
  - Claude subagents were forced to Opus.
  - The frozen model list was incomplete.
  - Calls are CLI invocations.
- **Incidents and scheduling.**
  - The ENOSPC exposure was asymmetric.
  - Raw rows and tails were lost.
  - The scan used a derived view.
  - RC3 was stopped by a host resource pause.
  - DT3 and RC3 were admitted late and run one at a time.
  - Two early cleanups changed permissions recursively.
- **Shared environment.** Home, transcripts, the network, the stale editable install and the fixture cache are covered
  by detection only.
- **Historical runtime.** The runtime is `6f43fae1` with package `5e2ef0a4…`. This is not current-engine
  qualification.

## Evidence And Archive

The evidence root is `agent-orchestration-compare-evidence/eb3/`, beside the repository.

**Science archive:** `/var/tmp/eb3-science-20261016.tar.zst`.
- Size: 251,768,020 bytes. sha256 `4c3cceb4faac6b3e29e91e8edad5752fecb3831728267194851c6b495b8126c0`.
- Seal receipt: `science-archive-seal-20261016T110851Z.json`, "sealed and verified".
- Manifest sha256: `54c9f50c689087aef8022fbc112b4036f6713dcdff330ed723af34d0fa73d722` (`science-archive-20261016T110851Z-outputs.sha256`).
- Contents: 133,897 files (6,965,715,718 bytes) and 2,135 symlinks.
- Verification:
  - zstd CRC passed;
  - the 195,138 `tar` entries equal the listing;
  - a fresh extraction matched every checksum and symlink;
  - no source changed while it was copied;
  - 8 evidence-directory entries were deliberately excluded: caches, scratch directories, the archiver's own plan
    file, and the derived home of hard links, which can be rebuilt from the raw journals and the driver.
  - Separately, 8 special objects in the agent trees were skipped: 6 sockets and 2 FIFOs. Their metadata is recorded
    in `METADATA.json`; they have no byte payload.
- The completeness cross-check found 0 missing among 127 unique raw paths, and all 85 rollouts were covered.

**What the archive includes.**
- The archive's `runtime/` directory holds the Git bundle and the two criteria.
  - The bundle is self-contained and verified, and holds tag `eb3-runtime-frozen` → `6f43fae1`.
  - The two criteria, `eb3.json` and `eb3-judge-primary.json`, were exported separately from their pinned commits.
  - At the seal, the package hash checked at the frozen runtime was `5e2ef0a4…`.
- The core packet is **not** self-contained. Its forensic dependencies are the five closed-`tmp` archives listed
  above, which remain in `/var/tmp`, and each was re-hashed as equal at the seal.
- To archive the pool, `pool/clones` was changed from 0311 to 0711 after every scientific actor had finished, and
  restored to 0311 after the seal.
- This report was written after the seal, so it is not in the packet and its hash is not circular.

**What is retained.** The runtime worktree and its tag, the evidence root, the science archive and the five external
archives are retained. The coordinator removes the work root only after the final review and local `main` integration.

## Appendix: Hidden Acceptance (Descriptive Only, Read Last)

A node passes if it passes alone in a copy of the clone with `hidden/` over it. There are 164 nodes.

| version | passed of 164 |
| --- | --- |
| DT1 final | 152 |
| DT2 final | 152 |
| DT3 final | 155 |
| RC1 first | 158 |
| RC1 final | 158 |
| RC2 first | 153 |
| RC2 final | 155 |
| upstream anchor (each batch) | 164, 164, 164 |
| stub anchor (each batch) | 1, 1, 1 |

- **Means.** `direct_task.hidden_mean` is 0.933 and `reviewed_change.hidden_mean` is 0.954.
- **RC hidden paired gain.** RC1 0, RC2 +2 nodes, so the mean is one node (1/164 = 0.0061).
- **Unpaired comparison.** `reviewed_change.hidden_minus_control` is +0.021. That compares RC's final-patch mean with
  the control's mean, and it is a separate comparison from the paired gain.
- **Rubric versus tests.** A rubric score is not a functional-test measure. The anchors' hidden results here do not
  re-grade any judge rating.
- **Context.** Calibration single calls passed 148–154 of 164.
- **Environment difference.** `summarize` ran with:
  - the guard first on `PATH`;
  - the Opus subagent pin;
  - a fresh, owned `TMPDIR=/home/ollie/eb3-ht`, which is 18 characters long, 14 more than `/tmp`.

  Calibration and the pre-batch anchor check ran with `TMPDIR` unset. The upstream anchors passed 164/164 in every batch,
  and the stub anchors 1/164. This
  is a descriptive environment difference and does not invalidate the primary.
- **No ranking.** Nothing was selected, ranked, excluded or gated on these numbers.
