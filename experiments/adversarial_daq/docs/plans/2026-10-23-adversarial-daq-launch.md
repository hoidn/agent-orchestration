# Adversarial DAQ launch record

Role: operational plan and decision ledger for the owner-requested run of the supplied package. This does not reopen the completed implementation plan or qualify a benchmark.

## Scope and authorization

- Owner requested running the supplied adversarial.orc package.
- Owner selected "sol 6.1 high or astra high"; use exact gpt-6.1-sol, high, for both outer roles.
- Owner explicitly waived calibration: "no calibragion ok". Record results as an uncalibrated adversarial exploration; do not imply the standard family/evaluator qualification passed.
- Retain the supplied four-round, 16-controller-call bound and 1800/900-second provider timeouts. No monetary cap was specified. No extra model judge, native delegation by researcher roles, paid calibration, live inner-model trials or automatic paid retries are selected.
- All simulation stays synthetic. No facility connections. Clean provider authentication is only for the chosen Codex transport; trial processes get neither credentials nor networking.

## Execution plan

1. Reconstruct the supplied files unchanged and prepare the pinned runtime/dependencies. DONE.
2. Compile, dry-run, collect and run package tests with fixture providers. DONE.
3. Pin live provider model/effort and add the smallest deployment boundary required by the supplied protocol. Keep the runner and role prompts intact. Verify deployment offline and independently review it. DONE.
4. Recompile/dry-run the configured controller, run one deterministic workflow smoke, then launch in tmux with streamed output. Capture actual run ID and verify persisted state and live process. DONE.
5. Monitor read-only, recording progress and terminal result. Resume committed work for a mechanical failure while preserving the original controller-site bound; record any failed extra attempts, with no silent provider changes or added experiments. DONE.

## Preparation evidence

- Package: experiments/adversarial_daq; 67 supplied files reproduced byte-for-byte from this conversation. Original SHA-256 map: artifacts/launch/supplied-files.sha256.json.
- Runtime: git archive bb9cb30d8d4b2ea8b24b6d1ee996b198f640a1d2, installed editable from research/agent-orchestration-main in package .venv.
- Dependencies: jsonschema 4.26.0, PyYAML 6.0.3, pytest 9.1.1. Python 3.13 on Linux; original verification on macOS is historical.
- Original compile/dry-run passed. Narrow runner tests: 16 passed. Collection: 32 tests. Full package: 32 passed in 12.90s with -n 16 --dist=worksteal. Logs under artifacts/launch/. No live model calls in these checks.
- Supplied source snapshot contains no standalone shift/control .log fixtures for the archived attached demo. That demo is research material, not the requested outer controller; do not fabricate its missing files.

## Deployment decision and tradeoff

Use one native Codex permission profile for researcher tools (deny filesystem root, allow minimal runtime and read-only package/dependencies, write only artifacts/runtime channels, deny selected auth and network) and a network-disabled Bubblewrap invocation around the original trial runner. Nested provider Bubblewrap plus Codex sandbox was rejected by the host; a real offline tool-sandbox check established the single-profile replacement. This avoids changing the simulator/evidence protocol. It makes host-specific dependencies and live inner-model experiments unavailable without a new explicit deployment decision. These boundaries do not independently certify the agent-authored oracle or make shared experiment files immutable.

## Integration ledger

- Keep all 67 supplied files unchanged. The generated deployment source is adversarial_live.orc at the package root, module adversarial_live::run. Keeping it at the root preserves the original module-relative prompts; the module name follows the compiler filename contract. Deployment manifests and scoped brief live under deployment/.
- Model policy: four provider sites explicitly compile to gpt-6.1-sol/high. The provider wrapper removes the builtin unrestricted flag and supplies native permissions; real provider source and helper hashes are recorded before launch.
- Installed mypy 2.4.0, LangGraph 1.2.16 and langgraph-checkpoint-sqlite 3.1.2 before candidate work so the existing-tool baseline is available. Full environment is recorded in artifacts/launch/environment.json.
- The independent reviewer found provider nesting failed despite a passing --version check. The replacement profile was verified offline against allowed artifact writes, denied controller writes, denied host/auth reads and denied network. No model call was used for this diagnosis.
- Public CLI integration smoke at artifacts/launch/smoke-213bbf582d164b2abfefc84ef2d8f2bf/summary.json: four deterministic provider results with exact model/effort, six actual confined trials, integrity true and synthetic CLAIM_REFUTED. This is control-flow evidence only.
- Provider authentication is a dedicated temporary directory with only the selected Codex credential initially copied; no host profile/plugins/skills are selected. Model tools cannot read that directory. CLI refresh/session state may persist there until cleanup.

## Live launch

- Run ID: 20261023T074348Z-6xkkuo, tmux daq-adversarial on /tmp/claude-tmux-sockets/claude.sock. First dispatch failed in CLI parsing before inference due to duplicated --skip-git-repo-check; wrapper was corrected and exact registry argv parser regression passed. Ordinary resume reused the same run; first actual model session starts at proposal attempt 2.
- Verified real CLI header: gpt-6.1-sol, high, custom permissions. Builder read protocol/source and successfully ran Python/import checks inside the native sandbox.
- Read-only monitoring is a real 30-second loop in tmux daq-watch, using the public report CLI. It writes artifacts/launch/latest-report.json and stops at terminal/interrupted/suspended status, without automatic retries or model calls. Live streams: artifacts/launch/live-resume.log; monitor: artifacts/launch/watch.log.
- Run remains active in round 1 BUILD; no experiment outcome is claimed at launch.

## Review transport recovery

- Round 1 BUILD, CHALLENGE and the official six paired trials committed. All 48 case executions passed every check; total accepted I/O 180 per arm. Official evidence digest: 3c6bb3475de93e32c7fc9afc8d6d0317d113a788669ea8bf5e3c095bc8964cd4.
- First REVIEW attempt stopped with provider_exit_nonzero: Selected model is at capacity, after the CLI reported 3,999 tokens. This is transport failure, not a verdict. Preserve logs/state in artifacts/launch/capacity-retry-001.json and capacity-failure-report.json.
- Coordinator selected one ordinary resume of the same run and same gpt-6.1-sol/high, preserving the original 16 controller provider sites. The capacity failure adds one paid failed attempt to those sites; the earlier CLI-argument failure occurred before inference. No remeasurement, model change or added experiment.

## Completed rounds 1 and 2

Both completed rounds have matching COUNTEREXAMPLE positions, fair/reproduced true, relevant false, and intact evidence. Their acceptance gate correctly did not close. No source or runtime state was edited to force agreement.

- Round 1: evidence artifacts/evidence/ba4a285b56bf4a9d969cb9f9e5315c05/report.json; digest 3c6bb3475de93e32c7fc9afc8d6d0317d113a788669ea8bf5e3c095bc8964cd4. Six arm/seed trials, 48 case executions, zero failed reported checks.
  - Orc I/O 180; baseline I/O 180. Recorded case wall time totals: Orc 137.375s; baseline 39.646s. Both paired baselines use actual LangGraph.
  - Skeptic report: artifacts/configure-resume-20261023T074348Z/round-1/skeptic-review-20261023T0825/review.md. Builder report: artifacts/configure-resume-20261023T074348Z/round-1/builder-answer-20261023T0900/report.md.
- Round 2: evidence artifacts/evidence/c5f2edc9792d4f1abb7f1313e4ae6275/report.json; digest 12eae422aa8739f1a4ea882437ee189bf09f64db2a776d1676e2ad0aac193de6. Six arm/seed trials, 48 case executions, zero failed reported checks.
  - Orc I/O 195; baseline I/O 195. Recorded case wall time totals: Orc 115.142s; baseline 27.531s. Both paired baselines use actual LangGraph.
  - Skeptic report: artifacts/uncertain-receipt-20261023T083808Z/round-2/skeptic-review-20261023T091637Z/review.md. Builder report: artifacts/uncertain-receipt-20261023T083808Z/round-2/builder-answer-20261023T092417Z/report.md.

Round 2 independently reproduced S10: a broken actuator can apply a stale permit while the old scorer reports safe=true because it checks pre-advance state. The actual paired arms used the correct guard. The frozen scorer was not changed. Round 3 is active with a new action-time scorer and new concurrency cases; it has no official result yet. Its proposed baseline is strict Python/Pydantic, because its scoped race has no crash or durable-approval claim.

## Completed round 3 and round 4 measurements

- Round 3 completed with matching COUNTEREXAMPLE positions, fair/reproduced true, relevant false and intact evidence. C3 required at least one fewer rejected repair dispatch for each seed; both arms had two in the primary cases for every seed. The independent baseline uses plain Python with strict mypy/Pydantic, not LangGraph, because this claim has no process-loss requirement.
  - Evidence: artifacts/evidence/f2be2f422bf84278b5104fcd7e102ff0/report.json; digest 6f132519211035e910168054699fbf418c72bbd6acdc9854b3fb89386e0c33e7. Six arm/seed trials, 48 case executions, all 240 reported checks true; total I/O 174 per arm. Case wall-time sums: Orc 100.640s, baseline 3.508s.
  - S10's specific scorer defect was fixed only in the new round and independently checked against broken-actuator controls. Missing operational relevance and independently withheld evaluation remained blockers. Reports: artifacts/action-time-race-20261023T093229Z/round-3/skeptic-review-20261023T1020Z/review.md and builder-answer-20261023T101517Z/report.md under the same round root.
- Round 4 BUILD and CHALLENGE committed and official measurements completed. Review and answer are still pending at this ledger entry. C4 requires at least one fewer unapproved repair dispatch after implementation drift for each seed. The independent comparator is actual LangGraph with SQLite checkpoints/tasks/interrupts, GNU SHA checks and durable pre-dispatch intent reconciliation.
  - Evidence: artifacts/evidence/dda36d7986b04999a409d45cf8cd49fb/report.json; digest 9fce118eebf69a7af80359d30dfec19383e61d9747b370d44a1f5e40de54ccb7. Six arm/seed trials, 54 case executions, all 270 reported checks true; zero unapproved dispatches and total I/O 150 per arm. Case wall-time sums: Orc 120.609s, LangGraph 30.301s.
  - Both development submissions retain S12: the negative ablation that omits declared implementation dependencies can replay an Orc repair and exceed the three-attempt cap (four actual attempts). Full-declaration paired cases pass. This does not establish an unconditional replay/attempt bound or compare maintenance effort.
- Timing sums include local process startup, compilation, schemas, persistence and simulator work. They are not measured facility recovery latency or a model-aware deployed-compute comparison. Inner arms use no model calls.
- The independent report observer was found stopped on the earlier capacity failure, while coordinator polling of state and live logs had continued. Restarted the read-only observer during round 4 BUILD; confirmed it reports the active step. No workflow/provider restart or new spend resulted.
- Rechecked all 67 supplied file hashes during round 4: unchanged.

## Round 4 review integrity failure

The skeptic's review invoked a checkpoint-inspection helper against the official SQLite files. SQLite `mode=ro` still updated shared-memory sidecars. The reviewer disclosed the error and left the changes in place rather than restoring files to evade the integrity check. Coordinator independently rehashed all four official evidence trees: rounds 1–3 still verify; round 4 fails because exactly 15 `.sqlite-shm` files changed. The round-4 report digest still verifies. This preserves the numerical observations but prevents accepting round 4 under the frozen protocol. The announced reviewer position is REVISE; its typed result and the builder answer are pending at this entry. A new run is not started automatically.

## Terminal verification

The run completed on 2026-10-23 at approximately 11:15 UTC. Public CLI report and runtime state both return INCONCLUSIVE after all four rounds: "budget exhausted without evidence-backed agreement; no impossibility claim". The read-only observer recorded completion and stopped. All 16 intended provider sites committed; the memo has 18 started attempts, including the pre-inference CLI failure and the paid capacity failure described above.

Rounds 1–3 have matching COUNTEREXAMPLE votes with intact evidence; missing operational relevance and independent withheld evaluation prevent acceptance. Round 4 has matching REVISE votes and intact=false. The builder independently reproduced all 54 round-4 cases from unchanged frozen sources in a new directory: 270 passing checks, zero primary saving on all three seeds. It did not replace the damaged official evidence. Its report is artifacts/implementation-drift-answer-20261023T110829Z/round-4/report.md; the skeptic report is artifacts/implementation-drift-20261023T102317Z/round-4/skeptic-review-20261023T110019Z/review.md.

Final coordinator verification rehashed the 67 supplied files and 10 deployment files (all unchanged), verified the three intact evidence sets, and confirmed exactly 15 changed SQLite SHM artifacts in round 4. Final records are artifacts/launch/final-report.json and artifacts/launch/final-verification.json. No acceptance gate, candidate, prompt, runner or runtime state was modified to change the outcome. No new paid run was launched.

The observed hypotheses did not establish an Orc advantage over the implemented competitors. Rounds 1, 2 and 4 used real LangGraph; round 3 used strict Python/Pydantic. Neither finite public simulations nor their agreement establish universal parity, real-facility safety or engineering/maintenance effort. Calibration was waived, not passed. Round 2's scorer limitation and round 4's review-induced integrity failure remain visible in the evidence.
