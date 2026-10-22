# Task-difficulty calibration: smaller agent versus Terra

Role: selected implementation and execution plan. Owner correction (2026-10-22):
calibration establishes that a task is difficult enough for a weaker agent to
perform noticeably worse than a stronger agent, without deliberately introduced
flaws. The owner instructed “fix the calibration plan, then reexecute it” and
selected a smaller model against Terra high.

## Objective and frozen design

Produce fresh, natural solutions to `resume-projection-integrity` (RPI) and
`pure-result-replay` (PRR). For each task run two independent `gpt-5.6-luna` high
attempts and two independent `gpt-5.6-terra` high attempts. Both use the same
`direct_task` workflow, task text, tools, timeout and fresh seeded repositories.
The model tier is the experimental difference; expected weakness/strength is a
hypothesis, not a result. No synthetic defects, empty controls, upstream patches,
retained fillers, repairs or orchestrated improvement loops enter this experiment.

One Terra-high judge scores all four anonymized natural solutions for each task
in one randomized batch, using the existing independent completeness,
correctness, scope and layering rubric (0–2 each, total 0–8). The judge receives
neither model identities nor a reference solution. During judging, existing
filesystem masks hide archived `docs/plans/evidence` reports in each clone;
source patches and original packages remain byte-identical. A task qualifies when:

`mean(Terra high) - mean(Luna high) >= 2`.

This is the only scientific acceptance threshold. Show every individual score.
Require exactly the declared two observations per arm; missing, invalid or
excluded evidence cannot shrink the denominator or produce PASS. Both tasks
must pass to declare this two-task set calibrated. Otherwise report which task
failed or remains inconclusive; do not change the threshold after seeing scores.
No hidden tests are run. Agent-visible development checks may be used naturally
by both coders but their failure rates and blocker counts do not select tasks.

The selected budget is eight generation sessions plus two judging sessions,
**ten planned, hard cap ten**, including any native children. This follows the
new owner instruction; historical AT recovery allowance is not transferred.
Use at most two concurrent generation sessions; run judges after collection.
No Claude, Fable, higher model, native delegation, automatic retry or replacement.
All physical dispatches count, including unsuccessful attempts. Preserve raw
patches, failed outcomes, model metadata and metering. No campaign is selected.

## Minimal implementation

Reuse `prepare.run_arm`/`ArmSpec`, public compile/run, collection, pool creation,
blind scorer, clone-ID joins and existing `measures`/`verdict`. Name the weak arm
`direct_task` and the stronger arm `terra_high`; both bind the identical direct
workflow. Freeze `purpose: calibration`, `calibration_kind: task_difficulty`,
`anchors: []`, reference null, no artificial `calibration` block, and primary
`terra_high.minus_control >= 2`. Declare both arm counts and actual model bindings.

- [x] Admit an explicitly anchor-free pool for this calibration kind and reject
  contradictory controls/reference. Include custom final-patch arms in the
  existing batch composer, preserving special multi-candidate/stage behavior.
- [x] Validate the complete declared task-difficulty denominator before a
  scientific verdict. Reuse existing means and primary comparison.
- [x] Allow exact `gpt-5.6-luna` only with a per-run opt-in, retaining default
  Terra behavior. Mirror the existing Claude environment handoff for Codex:
  `COMPARE_CODEX_MODELS` → `ORC_ALLOWED_CODEX_MODELS`; admit only the known
  Luna/Terra IDs and constrain each launch to its expected model. Preserve native
  agent disabling and all existing route/config restrictions. Scans and receipts
  verify the exact frozen model, rather than accepting both indiscriminately.
- [x] Verify focused tests and test collection, a public offline smoke spanning
  generation/collection/pool/judging/readout, and required affected checks.
  Independent code/plan and public-smoke reviews passed. Verification: 29 new
  cases collected; 484 affected tests passed with `-q -n 16 --dist=worksteal`;
  11 public scoring/integration tests passed. Integrate before paid execution.
- [ ] Freeze a fresh runtime, criterion, eight generation inputs, operator,
  model constraints and source identities. Validate actual dry-run commands and
  masks; preserve the sealed cf1 split and all historical package/seed bytes.
- [ ] Execute and supervise the ten-session experiment, collect every attempt,
  inspect contamination, join native receipts and compute both task gaps.
- [ ] Record and independently review the actual outcome; integrate current
  status/routing without relabeling historical evidence or selecting a campaign.

This reuses the current harness and adds no judge rounds, adaptive thresholds,
new execution framework, reservoir or campaign machinery. It makes direct score
comparison with earlier artificial-control exercises inappropriate. Two samples
per arm provide a small pilot, not statistical reliability; Terra judging may
also favor its own family's implementations. These are reported limitations,
not extra gates. If no frozen Luna price is available, report tokens and known
Terra list-price equivalents with total monetary cost unavailable.

## Superseded evaluator-control exercise (AS)

The earlier revision of this plan selected the wrong calibration objective.
AS's four Terra-high calls were already dispatched when the owner corrected it.
Retain their completion and audit as an auxiliary evaluator-control check only;
**AS cannot qualify task difficulty**, regardless of its control-separation result.

Its runtime is clean `48799d3dc3d5d1159c1d9acfc9ddc598452505f9` at
`/home/ollie/sc-runtime-simple`; evidence is `/home/ollie/sc-evidence/AS-20261022`.
Criterion SHA256 `673f02cfe15e37cf9f5b6952bbfd927afd5843f731a76ef63766b99938b921b1`
and operator packet SHA256
`4ab0d3d8ff6f1f1a7deaf4f5e8f8a61b3a8207ae3c94b554968702427c467fde`
remain unchanged. They select `control-means-v1`, three artificial controls and
five historical fillers per batch; none enter the corrected difficulty pilot.
The original selection was committed in `a832f56a` before those calls. Preserve
its 32 clones, 70 bound files, four native sessions and prospective criterion.
The independent prelaunch check, 88 guard tests and two provider-free dry runs
remain evidence about that apparatus, not task difficulty. Historical AT remains
completed `FAIL_NOT_QUALIFIED` under its own frozen rules.

AS finished all four sessions without native children. Its frozen-price cost is
USD 3.7637748. The independent audit covered 94 structured actions; no task tests
ran and no candidates were edited. PRR's judge saw archived JUnit reports embedded
in candidate documentation and was conservatively excluded, leaving no accepted
combined evaluator verdict. `/home/ollie/sc-evidence/AS-20261022/superseded-readout.json`
records these facts and explicitly sets task-difficulty qualification to false.
