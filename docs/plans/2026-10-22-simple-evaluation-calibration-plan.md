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

The initial TD budget was eight generation sessions plus two judging sessions,
**ten planned, hard cap ten**, including any native children. The authorized TD2
recovery budget is recorded below; historical AT allowance is not transferred.
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
- [x] Freeze a fresh runtime, criterion, eight generation inputs, operator,
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

## Frozen natural pilot execution

Runtime: clean `b067d37ce1bdf96f7281c1e0265384727cbb24e5` at
`/home/ollie/sc-runtime-difficulty`. Criterion:
`/home/ollie/sc-evidence/freeze-difficulty-20261022/criterion.json`, SHA256
`d92fccd9ff6a661bfc11032e47688906b83268c6b0fc80e995083be7c5c59b24`.
Generation packet SHA256
`e3dc89e7036fde367fbca217470de9e23698347866375fb76085df5bee7d784b`
binds 781 files, including the operator, actual CLI/native binary, inputs and
commands. The preservation manifest binds 364 historical files. All eight
public dry runs and actual Bubblewrap mask checks passed without providers;
11 operator checks and independent source/packet review passed.

Execution started 2026-10-22 under `/home/ollie/sc-evidence/TD-20261022`.
The first two original run IDs are `20261022T212827Z-ofrf57` and
`20261022T212827Z-iimnec`; native metadata confirms Luna high with no children.
The operator reserved two judge sessions and did not retry. The first generation
wave was interrupted at 21:40 UTC by a real model-policy violation: a coder's broad
local test run invoked legacy readiness probes through raw subprocesses. Four
Claude sessions requested Fable; two recorded Fable responses before termination.
Together with the two Luna roots this is at least six actual dispatches. No final
solutions or judge observations were accepted; this is an invalid apparatus run,
not evidence that either task passed or failed the quality-gap criterion. See the
[captured incident report](../reports/2026-10-22-natural-task-difficulty-calibration.md)
for the native inventory, accounting correction and causal limits.

The incident is preserved under the original evidence root. No further provider
calls are selected from that frozen packet. The correction is experiment-side:
when Claude is explicitly forbidden, mask its installed binaries and auth/config
inside Bubblewrap, scrub its credential environment, and prevent Bash startup
profiles from replacing the inherited guarded PATH. Verify the observed bypass
with fake binaries and preserve the original task/seed bytes. This makes login
profile conveniences unavailable in those sessions; explicit arbitrary PATH/API
bypass remains a stated detection boundary. Freeze a corrected runtime and
concrete recovery packet before seeking any additional spend; a fresh complete
pilot needs ten sessions, exceeding the original cap after this incident.

## Recovery (TD2; budget approved)

The correction is integrated on main in `bda0f693`; documentation routing follows
in `5d839b19`. A clean detached runtime at
`/home/ollie/sc-runtime-difficulty-recovery` uses `5d839b19236bc821fb08d04d7e4609a4da935eae`.
The prospective criterion is
`/home/ollie/sc-evidence/freeze-difficulty-recovery-20261022/criterion.json`, SHA256
`488196790454b9a1367a3b44acc55b4b1dab2c6ee0bdb46d45827bf5cc21215a`.

Tasks, seeded repositories, generation/judging bindings, rubric, two-point gap
and exact observation counts are unchanged. TD2 uses fresh repositories and
hides the interrupted TD work root from both coders and judges. Its operator
counts scoped Claude session starts even without assistant responses and retains
model-policy violations as non-clearable evidence.

The owner approved **ten new sessions plus six incident starts, total cap
sixteen**, answering “Autorizar 16 sesiones totales” on 2026-10-22. This increases
the original cap by six. The recorded approval binds the criterion and generation
packet; the same answer also covers the later judging packet. No additional judge approval question is required.
There are no automatic retries or replacements. An absent or mismatched approval
record stops execution before any worker starts.

Offline verification passed 202 affected tests with `-q -n 16 --dist=worksteal`
in tmux, four public CLI smoke checks and 15 recovery-operator self-checks.
Independent code, criterion and operator reviews passed. Full-suite testing was
not repeated; the frozen task bytes and prior evidence remain unchanged.

All eight prepared generation commands passed public dry runs. Eight additional
production-shim checks used only a fake Codex executable with real HOME: all 127
mask roots, installed Claude/auth isolation, credential scrubbing and interactive
shell guard resolution passed. The prepared run records and indexes remain
unchanged, with zero provider dispatches. The diagnostic PATH deliberately
excludes real Codex fallback and does not qualify arbitrary PATH/API bypass.

The frozen generation packet is
`/home/ollie/sc-evidence/freeze-difficulty-recovery-20261022/generation-packet.json`,
SHA256 `2eb21b9248f40bc05ebab7f42a5c35ecc30d1373a56b57110c10792259b9e4cd`.
It binds 849 files, including the correction, operator, diagnostic helper and
verification evidence. The preservation manifest covers 455 historical files.
The preflight reported zero new dispatches and six historical starts. The
immutable criterion retains its pre-approval proposal status; the operative
`TD2-20261022/owner-approval-generation.json` binds the later owner answer, SHA256
`f84689a45a00d525660a7d88db0461c40ecc55c0712a7f523cd2a2991a4d170f`.
Generation began at 22:05 UTC with the two RPI Luna-high attempts. Outcomes and
all quality judgments remain pending; no further approval is needed for the two
judging sessions within this same cap.

At 22:21 UTC both original TD2 RPI Luna runs completed with exit zero and one
verified Luna-high receipt each. Before dispatching Terra, the operator stopped
because git worktree enumeration added `durable-host-input` and `python-api`
under the already-masked main checkout. No roots disappeared, no protection was
lost and no third session started. Eight zero-provider Bubblewrap checks using
the exact original mask lists confirm both new paths were already hidden
(`TD2-20261022/mask-roots-change.json`).

Preserve the completed attempts, original operator, approval and packet. A new
continuation operator may accept only added roots already covered by frozen
masks outside the rebound candidate tree; genuine protection changes still stop.
It must verify the successful two-run prefix and launch only the six untouched
generation attempts, followed by the two already-authorized judges. This is no
retry, replacement, criterion change or budget increase. Bind the continuation
packet to the same owner approval before dispatch.

The bounded continuation passed 18 self-checks, public prefix validation and
independent source/packet review. The original 849 bound files remain unchanged;
the new 822-file packet is
`freeze-difficulty-recovery-20261022/generation-continuation-packet.json`, SHA256
`aee3ed157a887b48b2ee8c8b7928fe95feaa14909aca51d194f434a1d40bfff2`.
`TD2-20261022/owner-approval-continuation-generation.json` binds the same owner
answer and original approval hash, without increasing the cap. Both completed
Luna observations were publicly adjudicated as clear after an independent audit
of all 420 structured actions: scan hits concerned generic tmux skill examples
or each run's own private temporary sockets. This is an integrity decision, not
a quality score. The continuation completed the two RPI Terra sessions, then
stopped before PRR: the second Terra session left its native final response and
captured code patch but omitted the workflow's `result.json` envelope. Its
original outcome remains `failed/provider_result_missing`. Four TD2 sessions
and six incident starts have been consumed; six sessions remain authorized.

## Natural-output intake amendment (before judging)

The original completed-workflow intake is interrupted. Before any quality
scores, adopt the same collection rule for every original observation: evaluate
the final raw patch captured by its sole provider call, including terminal
delivery failures. Require a preserved terminal outcome, captured patch,
exactly one actual-model session with a complete positive-usage receipt, and
cleared contamination evidence. A captured empty patch is still an observation;
an absent snapshot or unverifiable receipt is missing evidence. All declared
observations remain in the denominator.

This is an explicit operational amendment made after observing one Terra
delivery failure, not a result under the original frozen protocol. Keep the
original criterion, records, native responses and failed status immutable. Do
not fabricate `result.json`, repair code, retry, replace or omit an attempt.
Report delivery outcomes alongside quality scores. Freeze the amended criterion,
analysis runtime and intake lineage before any judge starts; preserve the
original generation runtime, commands, task text and tools for the four
untouched PRR attempts.

The tasks, models, two samples per arm, rubric and two-point mean-gap threshold
are unchanged. The independent method review accepted this bounded change:
the missing envelope is a harness delivery failure, while the task and rubric
assess implemented repository behavior. Any qualification belongs only to the
amended protocol. This makes direct comparison with the original intake rule
inappropriate and must be disclosed with the results.

The existing owner instruction to fix and simplify calibration, and the total
sixteen-session authorization, cover this continuation: four untouched PRR
generations plus two blind judges. No additional spend or campaign is selected.

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
