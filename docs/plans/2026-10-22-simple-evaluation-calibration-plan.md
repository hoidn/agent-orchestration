# Task-difficulty calibration: Luna low versus Luna high

Role: selected implementation and authorized execution plan; generation underway. Calibration
tests whether natural solutions from a weaker agent score noticeably below those
from a stronger agent, without deliberately introduced flaws. The owner's latest
instruction offered “either luna low and luna high or luna and sol6.1”. The
coordinator selected **the same Luna model at low versus high effort**. Sol 6.1
is not selected. Higher effort is an experimental treatment, not a guarantee of
better output; the fixed qualification rule may still fail.

Current status: all sixteen previously authorized sessions are consumed. TD2 captured all
eight natural solutions, but PRR's judge used apparent deletions created by the
archive masks and is excluded. RPI's retained, explicitly uncertain readout has
Luna mean 6 and Terra mean 4.5, failing the required advantage. The two-task set
is not calibrated. The [recovery report](../reports/2026-10-22-natural-task-difficulty-recovery.md)
records that unchanged history. The environment correction is integrated in
`629c3b9c`, and exact per-arm effort support in `dd308a03`. Fresh LH preparation,
mask checks and generation preflight passed before dispatch. The owner then
answered “i authorize” to ten additional sessions, total cap twenty-six.
Generation is underway; no LH calibration outcome is reported at this checkpoint.

## Selected contrast (authorized; generation underway)

For each of `resume-projection-integrity` (RPI) and `pure-result-replay` (PRR),
generate two fresh independent attempts per arm:

| Arm | Exact model | Effort | Attempts per task |
| --- | --- | --- | --- |
| `direct_task` (weak) | `gpt-5.6-luna` | `low` | 2 |
| `luna_high` (strong hypothesis) | `gpt-5.6-luna` | `high` | 2 |

Freeze `arm_models` with the same exact Luna ID for both arms and
`arm_efforts: {direct_task: low, luna_high: high}`. Both use
`control/direct_task.orc`, entry `control/direct_task::direct-task`, identical
task packages, tools and seeded bases, and a 14,400-second timeout per attempt.
Effort is the sole treatment difference. Use fresh repositories and independent
runs: none of TD/TD2's known Luna-high outputs or scores becomes a new sample.
Keep those outputs as descriptive history, without relabeling their arms.

One **Terra-high** blind judge per task still scores its four randomly ordered
clones in one batch. Both experimental coder arms are Luna; Terra is not a coder
arm in this contrast. Conceal arm/model/effort provenance and use the existing
independent completeness, correctness, scope and layering rubric, 0–2 each and
0–8 total, without a reference or artificial controls. The sole primary rule is:

`luna_high.minus_control >= 2`

That is `mean(Luna high) - mean(Luna low) >= 2` on **each** task. Retain exactly
two original observations per arm and all individual scores. Missing, invalid
or excluded evidence cannot shrink the denominator or produce PASS. Both tasks
must pass to qualify the set; neither expected model strength nor observed
scores justify changing the threshold, excluding a task or correcting a rating.
No hidden tests, synthetic defects, retained fillers, retries, replacements or
orchestrated improvement loops enter this pilot. Coders may use their visible
development tests; judges may neither execute tests nor use test results.

Apply the declared terminal-single-call natural-output intake uniformly: retain
the final raw snapshot, terminal status and failure, complete actual-model and
effort receipt, and contamination decision for every original attempt. Do not
fabricate a result envelope or repair a failed attempt. The earlier amendment
and TD/TD2 outcomes remain historical; a new criterion must declare this intake
prospectively before any new call.

### Minimal offline work before preparation or spend

- [x] Finish, verify and independently review the clean review-environment
  correction below before preparing this pilot. The judge's real Git baseline
  must exclude the protected archive; do not use index flags, filtered Git
  output or instructions to ignore apparent deletions. Preserve raw patches.
  Integrated `629c3b9c`: 432 affected tests, real Bubblewrap/fake-provider smoke,
  independent review and exact reconstruction of all eight TD2 raw patches passed.
- [x] Add only the needed effort binding to the existing natural intake:
  `expected_effort` defaults to `high` for historical callers. The new criterion
  declares `arm_efforts`; launch preparation and summary validate each arm's
  declared effort against complete native receipt metadata, alongside the exact
  model. Omitted effort declarations retain existing high-effort semantics;
  old freezes, V1 receipts and C1 callers keep their behavior.
- [x] Verify low/high receipt admission and wrong-effort refusal with offline
  fake providers, plus legacy high-effort behavior and complete-denominator
  joins. Run focused checks, collection for changed tests and a public
  generation/collection/pool/judge/readout smoke before the affected parallel
  suite. No real provider is needed for these checks.
  Integrated `dd308a03` after independent review: 57 narrow checks, collection
  of 71 changed-module cases, the public same-model low/high fake-provider smoke
  and 447 affected tests passed. The broad log and exit zero are
  `/tmp/compare-arm-effort-verify-wfffy2v9/pytest.log` and `pytest.exit`.
- [x] Integrate a reviewed clean runtime and freeze a new criterion, operator,
  model/effort bindings, eight fresh generation inputs and commands, and the
  declared clean-review and raw-patch intake policy. All eight actual public
  dry runs and eight real Bubblewrap/fake-CLI mask checks passed with zero
  provider starts; TD/TD2 evidence remains preserved.
- [x] Prepare the concrete generation packet for the proposed ten-session
  experiment. Independent review of its 850 bound files and generation
  preflight passed. The later owner approval below supplies execution authority.
- [ ] Supervise the authorized eight generations (at most two at once)
  and two sequential blind judges, one physical call per unit. Count every root,
  child and failed start; refuse Claude/Fable, native delegation and unexpected
  models/efforts. No automatic retries or replacements.
- [ ] Audit integrity before canonical joins and report each task's actual
  outcome, original delivery failures and metered consumption. A Terra judge
  does not establish an unbiased measure; two samples per arm remain a pilot,
  and higher Luna effort need not earn a higher score. Unknown Luna prices stay
  unavailable, not zero. No ORC-benefit or quality–cost Pareto claim follows.

### Frozen offline preparation (no provider starts)

| Artifact | Exact identity |
| --- | --- |
| Clean runtime `/home/ollie/sc-runtime-luna-effort` | commit `fa057b597564be68ea94d8ffd77fa32d3cdc4eea` |
| `/home/ollie/sc-evidence/freeze-luna-effort-20261022/criterion.json` | SHA256 `ffde67d90a2aee30030a28e1f99f1f4ffd27215d67f042589b10a088f81e9b36`; immutable pre-approval snapshot, operative approval recorded separately below |
| `/home/ollie/sc-evidence/preparation/luna_effort_operator.py` | SHA256 `dd4f8ece0b6aa6c351a0320c34ed28e3a93119a9cd9f930fdc7d8cb5bd9831fe` |
| `/home/ollie/sc-evidence/freeze-luna-effort-20261022/generation-packet.json` | SHA256 `7126fe64554381db209d700d99c35bf7a80ba196afe4a5ae2295156978be4e9a`; 850 bound files |

Evidence is under `/home/ollie/sc-evidence/LH-20261022`:
`generation-prepare.json` records all eight fresh units, and
`generation-mask-smoke.json` records the eight actual sandbox/fake-CLI checks.
`operator-selfcheck.log` and `.exit` retain 28 passing offline checks;
`offline-prepare.log`/`.exit` and `offline-mask-smoke.log`/`.exit` all report
exit zero. `generation-preflight.log`/`.exit` report exit zero, no new provider
starts, sixteen historical starts and no Claude, native children or extra roots.
That preflight checkpoint precedes the live start recorded below. Raw outputs,
clean review-base derivations and the later judging packet will be bound after generation;
the original runtime, criterion and prior evidence remain immutable.

### Authorized budget and chronological decision ledger

The owner approved **ten new sessions**: eight fresh generations and two
Terra-high judges, within an overall cap of **twenty-six** including the sixteen
spent historical starts. The verbatim reply “i authorize” is recorded in
`/home/ollie/sc-evidence/LH-20261022/owner-approval-generation.json`, SHA256
`1db714f1b92c34f252618c95215843ee2ca53457d5c90fa8a2c5453ce5a48c01`.
It binds the unchanged criterion and generation packet. The same answer covers
the later derived judging packet; no further permission question is required
for those two judges. The criterion's frozen pending-status field preserves its
pre-approval snapshot; this separate approved record is operative. Earlier
pending decisions below remain the preparation chronology.

| Decision | Consequence |
| --- | --- |
| Owner offered Luna low/high or Luna/Sol 6.1; coordinator selects Luna low/high | Same exact `gpt-5.6-luna` model, different declared efforts, weak `direct_task` and strong-hypothesis `luna_high`; Terra-high judging stays unchanged. Better performance remains empirical, not guaranteed |
| Change the treatment prospectively | Generate all eight outputs afresh; do not reuse known TD2 Luna-high scores or relabel Luna/Terra records. Freeze `luna_high.minus_control >= 2` for each task before calls |
| Preserve the apparatus findings and spent budget | Finish the offline environment/effort corrections first. Keep TD/TD2 protocols, raw results and partial readout unchanged; ten additional sessions and overall cap twenty-six remain pending owner approval. No campaign or Phase 2 work is selected |
| LH offline preparation and independent packet review completed | Freeze runtime `fa057b59`, criterion `ffde67d9`, operator `dd4f8ece` and 850-file generation packet `7126fe64`; eight public dry runs, eight sandbox/fake-CLI checks, 28 self-checks and zero-start preflight passed. Budget approval and all provider execution remain pending |
| Owner replied “i authorize” on 2026-10-23 UTC | The bound approval above authorizes all eight fresh generations and two sequential Terra-high judges, cap twenty-six including sixteen historical starts. Generation launched in `sc-lh-generation`; the initial RPI Luna-low runs are `20261023T004805Z-5xwueb` and `20261023T004805Z-lbgr1g`. Execution and integrity/readout checkboxes remain open; no completion or quality result is claimed |

## Historical TD/TD2 model contrast and frozen design

The protocol and execution sections below preserve the previously selected
Luna-high versus Terra-high experiment. Their launch instructions, checkboxes
and budgets do not select or authorize the new low/high experiment above; its
fresh criterion must not amend old freezes. The separately titled correction to
the review environment remains selected offline work shared by the new contrast.

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

The intake correction is integrated in `ce48c89c`, with 402 affected tests,
two public fake-provider smokes and independent review passed. Its clean analysis
runtime is `/home/ollie/sc-evidence/preparation/runtime-natural-intake` at
`ce48c89c1a9d8efd9095a328c30b0782faa911a3`; the generation/judge execution runtime
remains `5d839b19`. The amended `criterion-natural-intake.json` has SHA256
`0d7440fed6cd1b0d70f5410313e144853360610ebf06dfdb376c3403bd716018`.
The PRR continuation packet has SHA256
`b01d6574b34c2effa58c48b892bec43417d2b081321d4c428f06ad60b4d74801`;
it retains the same owner answer and original generation commands. All four
PRR attempts completed, leaving eight original natural captures and fourteen
total starts including the incident. The two blind judges remain within the
authorized sixteen-session cap. No quality scores exist at this checkpoint.

## Correct the review environment (offline; no replacement calls selected)

The owner instructed: “make the requisite env fixes; no hacks / workarounds”.
The masks concealed tracked archive files from the filesystem while leaving
them in Git's baseline. PRR's judge treated those apparent deletions as candidate
scope; none of the eight actual patches touches `docs/plans/evidence`.
Preserve the contaminated judgment and original pools. Do not suppress Git
changes with index flags, filtered output or instructions to ignore them.

Build fresh review repositories whose baseline itself excludes the explicitly
protected archive, then apply the original candidate patch unchanged. Record
both original seeded base and derived review base; use fresh Git object storage
so archived contents are absent from the review history as well as its files.
This leaves historical packages and candidate outputs unchanged, but makes
direct comparison of review HEAD IDs with the original seeded HEAD inappropriate:
the recorded derivation and exact patch identity must establish that relationship.

- [x] Add an explicit, backwards-compatible review exclusion to the existing
  pool writer. Default pools, V1 qualification receipts and C1 callers retain
  their current behavior. Reject invalid paths and any genuine candidate edit
  to an excluded path. Reject this exact-patch mode if legacy stripping would
  alter the raw patch; do not silently filter a candidate's changes.
- [x] Derive a clean deterministic review baseline without original Git history,
  apply the unchanged patch, and require the resulting Git diff to match it.
  Keep normal pool verification/restoration working against the real review base.
- [x] Verify file bytes/modes, add/delete/rename exclusions, archive absence from
  Git objects, clone integrity and a real Bubblewrap/fake-provider smoke. Run
  narrow checks before the affected parallel suite and obtain independent review.
- [x] Integrate the environment correction and record its verification.
  Prepare fresh review views of existing outputs offline; do not replace or
  reinterpret old ratings. No additional provider session is authorized by this
  correction: the sixteen-session cap is exhausted.

Environment implementation `629c3b9c` passed 69 narrow checks, collection of 30
tests in the changed modules, the public real-Bubblewrap/fake-provider smoke,
and 432 affected checks with `pytest -q -n 16 --dist=worksteal` in tmux.
Independent source review passed. Logs are
`/tmp/compare-review-env-verify-dtds7cdv/pytest.log` (exit zero) and
`/tmp/compare-review-environment-public-smoke.log` (exit zero).
`TD2-20261022/review-environment-check.json` additionally verifies all eight
actual raw patches in fresh review repositories and all 40 capture-source hashes
unchanged, without a provider call. Those views are apparatus checks, not new
samples or judgments for the selected effort contrast.

The unchanged partial readout is
`/home/ollie/sc-evidence/TD2-20261022/natural-partial-readout.json`.
RPI's original ratings remain analysis with explicit exposure uncertainty, not
a clean-environment replication. PRR's canonical summary refuses its excluded
judge. Neither this repair nor a future PRR score can retrospectively turn the
captured RPI result into a passing task.

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
