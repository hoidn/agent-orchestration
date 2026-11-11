**REVIEW: COUNTEREXAMPLE to C2. Uncalibrated exploration; eligibility is false.**
Actual persistent LangGraph matches Orc on the unchanged acceptance criterion.
The required saving is at least one rejected repair per public seed; the
measured saving is zero on every seed. A separately reproduced safety-oracle
defect and the unresolved operational/held-out qualifications remain blockers.
This is an executable refutation of this particular synthetic advantage claim,
not a qualified facility demonstration or a universal impossibility finding.

The exact bounded claim, copied verbatim from the frozen claim.json, is:

> In the four-case synthetic uncertain-receipt configure suite with public seeds 11,23,47, the typed-Python/generated-.orc debugger incurs at least one fewer rejected repair dispatch summed over applied_partial and completed_offline for every seed than the strongest equal-budget baseline, while both arms pass all five checks on every case and Orc adds no accepted I/O, effective repairs, disruption, or escalation.

The evidence digest is
`12eae422aa8739f1a4ea882437ee189bf09f64db2a776d1676e2ad0aac193de6`.
The distinct recorder-source SHA-256 is
`861a5e077faf5dcb713cf85d3ea351e4036c71442c43278907474d1eb0bfc01d`.
I read the protocol, required research notes, submissions and referenced prior
review/answer; the immutable [source snapshot](../../../evidence/c5f2edc9792d4f1abb7f1313e4ae6275/source/suite.py),
both implementations, simulator, independent scorer, report and raw outputs.
The retained [recorder copy](reproduction-001/runner-reviewed.py) matches the
official hash and unchanged scripts/run_trials.py. All **1,189 recorded artifact
hashes** and the canonical report digest were verified before and after the new
execution. The [predeclaration](../development/predeclared-claim.json) is
byte-identical to the submitted claim.json. The builder's retraction is recorded;
the construction and execution, rather than that concession, establish parity.

Acceptance requires baseline-minus-Orc rejected_actions >= 1, summed over ONLY
applied_partial and completed_offline, separately on each seed. All five checks
must pass on all eight original/added cases. total_io, effective_repairs,
disruptions and escalations must be noninferior per case. Wall time, source
length, added cases and diagnostic prose cannot replace this margin. total_io
counts processed calls, including rejected requests; nothing is hidden by the
word “accepted” in the claim's cost clause.

| Public seed | Orc primary rejected repairs | LangGraph primary rejected repairs | Baseline minus Orc | Required |
|---|---:|---:|---:|---:|
| 11 | 0 | 0 | 0 | >=1 |
| 23 | 0 | 0 | 0 | >=1 |
| 47 | 0 | 0 | 0 | >=1 |

All **48 official case executions pass all five checks**, totaling 240 true
checks, with no invalid trials, timeouts, suite errors or captured DUT errors.
The new [frozen-source reproduction](reproduction-001/receipt.json) repeats all
48 executions with actual installed libraries and the unchanged scorer. Its
primary differences are also zero on every seed; strict mypy passes, malformed
future count bytes fail strict Pydantic validation, and dependencies remain
unchanged. These public deterministic seeds vary initial generation/event
increments, not independently sampled incident families. The observed
difference range [0,0] is not a confidence interval. No stochastic agent quality
or population estimate follows from the three-seed floor.
The separate [reproduction audit](reproduction-audit.json) also verifies all
24 new pairs' full trace equality and reads their 456 logs.

| Case | Processed I/O per arm | Attempts / effective / rejected | Disruption / escalation |
|---|---:|---|---|
| clean | 2 | 0 / 0 / 0 | 0 / 0 |
| applied_partial | 12 | 3 / 2 / 0 | 11 / 0 |
| completed_offline | 5 | 1 / 1 / 0 | 1 / 0 |
| irrecoverable | 9 | 3 / 0 / 0 | 0 / 1 |
| skeptic_epoch_race | 6 | 2 / 1 / 1 | 1 / 0 |
| skeptic_compound_ambiguous | 12 | 0 / 0 / 0 | 0 / 1 |
| skeptic_offline_pending | 5 | 1 / 1 / 0 | 1 / 0 |
| skeptic_loss_missing_readback | 14 | 3 / 2 / 0 | 11 / 0 |

Each official arm totals 195 processed calls/transport attempts, 39 repairs,
21 effective repairs, three rejected requests, zero duplicate dispatches,
75 authored disruption units, 27 offline ticks, twelve injected losses and six
policy-appropriate escalations. Every lost receipt belongs to an effective
processed repair, before response publication. Completed_offline really evolves
during downtime; short downtime leaves pending work visible. Both proof samples
must follow the outage. Compound ambiguity escalates without speculative repair;
the permanent fault escalates after three failed attempts. No unnecessary
escalation or disruption appears under the declared synthetic policy.

All **24 official pairs have identical journals, transports, outages, final
truth, outputs, checks and non-time metrics**, beyond equal aggregates. The
[official audit](reproduction-001/official-audit.json) rescores every trace,
cross-checks suite stdout/result rows and reads all 456 retained suite, case
and command stdout/stderr files. The only nonempty stdout files are the six
suite result logs. Twelve nonempty Orc stderr logs contain expected effect_rerun
diagnostics; all baseline stderr logs are empty. All 120 ordinary independent
rescore/mutation controls pass. The negative control below nevertheless fails
the intended safety requirement; passing ordinary controls does not cure it.

The conventional construction is the frozen [baseline.py](../../../evidence/c5f2edc9792d4f1abb7f1313e4ae6275/source/baseline.py):
LangGraph 1.2.16 Functional API entrypoint/tasks, persistent SqliteSaver,
synchronous durability, durable interrupts bound to target/epoch/lease, and
Pydantic 2.10.3 strict boundaries. Pins include langgraph-checkpoint 4.3.0,
langgraph-checkpoint-sqlite 3.1.2, langchain-core 1.7.0, mypy 2.4.0, Python
3.13.9 and SQLite 3.50.2. Orc executes actual typed Python/generated .orc through
orchestrator 0.2.0 at bb9cb30d and TARGET=2.39; neither arm is an imitation.

Both use the SAME raw validators, domain policy, transport, actuator guard and
durable intent/readback helper. Interrupted tasks re-enter explicit
reconciliation, not an exactly-once actuator transaction. Immediate deterministic
authorization adds no observation, model, permission or I/O; delayed human
approval is untested. Each arm has zero inner models/prompts/tokens, 24 calls,
25 seconds per case, one restart, twelve policy rounds and three repair attempts;
suite timeout is 120 seconds. No model or delegation was invoked in this review.
The disclosed strict-mypy config skips shared untyped adapters: it is not a
whole-program proof. Retained static probes reject known str/int mismatch before
RPC; future malformed bytes fail at runtime. No static system predicts physical
truth or future bytes.

The preserved seed-11 [challenge ablations](../skeptic-challenge-20261023/reproduction-001/receipt.json)
execute actual libraries with the same simulator/scorer:

| Variant | Primary I/O | Primary rejected / duplicate repairs | Outcome |
|---|---:|---|---|
| Orc or LangGraph, shared ledger | 17 | 0 / 0 | all checks pass |
| Orc native replay, ledger disabled | 17 | 2 / 2 | all checks pass; plant rejects stale attempts |
| LangGraph replay, ledger disabled | 17 | 2 / 2 | identical result |
| Fresh-observation Python, memo/ledger disabled | 15 | 0 / 0 | all checks pass |
| Uninterrupted Orc or LangGraph | 17 | 0 / 0 | all checks pass |

I concede the measured benefit of explicit uncertain-action reconciliation:
it avoids two stale repair dispatches without extra processed calls relative
to native replay in BOTH durable frameworks. That benefit belongs to shared
glue. Fresh observation is cheaper here. Equal uninterrupted aggregate I/O mixes
different per-case progress schedules; it does not isolate persistence speed.
The actual Orc must_not_repeat variant usefully refuses uncertain replay but
fails both primary recovery objectives. Refusal is not restored acquisition.
Model quality is held at zero, shared policy and validators are controlled, and
the ledger intervention isolates reconciliation. General static-check,
runtime-provenance and engineering-effort benefits are unmeasured under C2.

The [history audit](history-audit.json) reads all 84 builder round-2 development
traces (two failures), all 68 challenge matrix/ablation traces (zero failures),
and all four prior initial wrapper failures. The two round-2 DUT exits are
code 2 with lexical_restore_pending_effect_unsafe in must_not_repeat. The suite
conservatively makes every check false; this does not establish an unsafe
physical effect or timeout. Both controls pass. The four old code-1 failures
report RuntimeError: missing runtime state from an obsolete wrapper. Their
complete failed stderr is retained in the audit. Known negative compile/runtime
probes have expected nonzero exits and are not hidden failed trials. No prior
failure or old oracle revision is represented as new official evidence.

**S10-TOCTOU-ORACLE remains a serious, executable defect.** The independently
rerun [negative control](reproduction-001/oracle-gap.json) uses the real added
EpochRace plant and an intentionally broken guard. A lease samples epoch 563;
advance changes the action-time epoch to 564; the broken guard actually applies
timing with the old lease, producing epoch 565. The unchanged oracle reports
safe=true. It compares against row.before.epoch=563, captured BEFORE advance,
instead of action-time truth. This is a false-negative safety judgment, not a
successful full recovery probe: objective_met and diagnostic_useful are false.
The measured arms use the correct guard and reject the raced action. Their
numerical zero-rejection primary counterexample stands, but the scorer cannot
independently certify action-time permit validity.

Smallest decisive repair: in a NEW round, log immutable truth after advance
and immediately before applying a repair; have the independent oracle check
epoch, pending state and target against that snapshot; require the broken-guard
probe to score safe=false, then rerun the same paired suite. Do not edit or
relabel the frozen C2 scorer/results. No new metric or margin is needed to
recognize C2's numerical refutation.

The painful task is resuming a configure debugger after an applied repair loses
its receipt and hardware may complete during downtime. Its frequency, actual
readback costs, trustworthiness of these lease/pending observations and approval
of targeted repairs are **unknown**. The supplied research snapshot cites
[LCLS2 control at 04d36d15](https://github.com/slac-lcls/lcls2/blob/04d36d15c222ec6dbc10b833bf0c3ef5059a5c34/psdaq/psdaq/control/control.py)
(commit dated 2026-10-22) for existing configure phases/state-machine guards and
[DaqLCLS2 at 4a3f2504](https://github.com/pcdshub/pcdsdaq/blob/4a3f2504b4d6f1860457ecfc40aaaf28115a777f/pcdsdaq/daq/lcls2.py)
(2026-09-08) for statuses, validation and timeouts. The
[AMI ICALEPCS2025 paper](https://proceedings.jacow.org/icalepcs2025/pdf/THAG005.pdf)
already documents Python mypy checks and graph/runtime monitoring. These primary
references retain the supplied snapshot's provenance; I did not refresh them or
contact a facility. They establish mechanisms, not incident incidence or an
approved recovery. Actual pcdsdaq/Bluesky/ophyd/AMI are not executed here, and
their controls behavior is not what C2 measures.

Official per-case Orc wall time is 3,453/4,819/5,974 ms min/median/max;
LangGraph is 768/1,132/1,514 ms. This includes startup, imports, checkpointing,
intent fsync, subprocesses, Orc compilation/resume/closures and validation;
mypy is separate. It is local implementation overhead, not facility latency
or the acceptance metric. Disclosed nonblank/noncomment Python lines are 88
for the baseline, 121 for Orc workflow/wrapper/adapter plus commands.json, and
119 shared policy/tools/transport lines. Both maintain schemas and recovery
policy; LangGraph also maintains task/interrupt ordering and checkpoint identity,
while Orc maintains command closures and program identity. Evaluation code is
additional cost. Human authoring time, migrations and future maintenance effort
are unmeasured; source length cannot substitute for an ergonomics experiment.

| Stable objection | REVIEW disposition |
|---|---|
| S01-PARITY / C2 | Confirmed executable LangGraph counterexample; unchanged margin fails on all three seeds. Builder must answer this construction. C1 remains retracted. |
| S02-RELEVANCE | Blocker: independent DAQ determination of incident correspondence, observation cost/trust and permitted recovery is absent; frequency remains unknown. |
| S03-CRASH-WINDOW | Applied-effect/lost-receipt and offline completion now exercised. Process loss/disk intact only; no power-loss or arbitrary exactly-once guarantee. |
| S04-FRESHNESS | Shared guard rejects generation race; readback rejects stale/missing/ambiguous observations. Delayed approvals and arbitrary external writers unqualified. |
| S05-LINEAGE | No experiment/run/calibration lineage or partial XTC/SMD readiness claim. Generation is not scientific lineage. |
| S06-LEAKAGE | Blocker for qualification: 100% public development / 0% independently withheld material; no hidden-evaluator receipt. API boundary is cooperative, not isolation. |
| S07-ATTRIBUTION | Same deterministic policy/tools, zero models. Reconciliation benefit is shared, not exclusive to Orc. No model-quality or preflight/provenance exclusivity claim. |
| S08-ORACLE / S10-TOCTOU-ORACLE | Blocker: independently reproduced stale-permit effect scores safe. New action-time telemetry/scoring requires a new round. |
| S09-COST | All processed attempts/effects/disruption/escalation retained; no unmeasured maintenance or source-length advantage substituted for C2. |

Vote judgments are **COUNTEREXAMPLE, fair=true, reproduced=true, relevant=false**.
The numerical construction is directly relevant to exact C2; relevant=false
preserves the unresolved qualified operational relevance of the overall task.
**Eligibility is false**, with blockers S02, S06 and S10. Calibration was
owner-waived, never passed; neither family nor evaluator qualification passed.
The builder's ANSWER and controller integrity check remain required. Neither
role can terminate with a win on its own.

For an operational advantage search, obtain an independent expert determination
of this incident, observations, costs and permitted repairs before retuning,
then freeze a new predeclared claim and genuinely withheld evaluation. A future
ergonomics claim requires measured engineering effort against the implemented
durable and fresh-observation baselines. Finite parity does not prove that every
possible useful Orc demonstration is impossible.

One offline command reproduces this review's frozen-source paired executions,
hash verification, strict mypy, boundary check, ordinary oracle controls and
negative safety control. Choose a NEW destination from the workspace root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python artifacts/uncertain-receipt-20261023T083808Z/round-2/skeptic-review-20261023T091637Z/review_reproduce.py artifacts/uncertain-receipt-20261023T083808Z/round-2/skeptic-review-20261023T091637Z/NEW-reproduction
```

The [review utility](review_reproduce.py), [history utility](history_audit.py),
receipts and report are new files. Existing submissions, recorded evidence,
controller, prompts, runner and dependencies were not modified. All tools and
trials were synthetic/local; no credentials, network, live models or delegation
were used.
