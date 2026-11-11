**COUNTEREXAMPLE to C3. Uncalibrated exploration; overall eligibility is false.**
The independently implemented strict-Python baseline meets every frozen check
and matches Orc's dispatch costs. The predeclared saving is zero on every seed,
against a required minimum of one. This refutes the particular synthetic claim;
it does not establish a qualified facility demonstration or universal
impossibility of a useful Orc advantage.

The exact bounded claim, copied verbatim from the immutable claim.json, is:

> In the four-case synthetic action-time-race configure suite with public seeds 11,23,47, the typed-Python/generated-.orc debugger incurs at least one fewer rejected repair dispatch summed over external_epoch_change and concurrent_pending for every seed than the strongest equal-budget baseline, while both arms pass all five checks on every case and Orc adds no total I/O, effective repairs, disruption, or escalation.

The exact evidence digest is
`6f132519211035e910168054699fbf418c72bbd6acdc9854b3fb89386e0c33e7`.
The distinct recorder-source SHA-256 is
`861a5e077faf5dcb713cf85d3ea351e4036c71442c43278907474d1eb0bfc01d`.
The [official report](../../../evidence/f2be2f422bf84278b5104fcd7e102ff0/report.json)
is valid with no recorder errors. I read the protocol, required research notes,
submissions, retained history, frozen simulator/oracle/suite and both actual
implementations. The new [review audit](verification-001/audit.json) verifies
the canonical digest, all **1,150 recorded artifact hashes**, all 37 declared
source files against their submissions, the manifests and byte-identical claim
predeclaration. The retained [recorder copy](verification-001/runner-reviewed.py)
matches both the official hash and current scripts/run_trials.py. Evidence
integrity was checked again after verification. Recorded sources and results
were not edited.

Acceptance remains baseline-minus-Orc rejected_actions >=1 on the TWO primary
cases summed separately for EVERY seed; all five checks on every original and
added case must pass, with per-case noninferiority for total_io,
effective_repairs, disruptions and escalations. Wall time, source length,
diagnostic prose and extra cases cannot replace that margin.

| Public seed | Orc primary rejected repairs | Python primary rejected repairs | Baseline minus Orc | Required |
|---|---:|---:|---:|---:|
| 11 | 2 | 2 | 0 | >=1 |
| 23 | 2 | 2 | 0 | >=1 |
| 47 | 2 | 2 | 0 | >=1 |

All **48 official case executions pass all five checks**, totaling 240 true
checks. All **24 paired journals, transports, external interventions, outages,
final truth and terminal status/evidence/reason match**, excluding guard CPU
timing and framework-private output fields. Every other metric is equal.
The audit independently rescores every trace and checks every result against
the suite's stdout. It reads and retains contents/hashes for all **456 raw
suite, case and command stdout/stderr files**. Only six suite stdout files are
nonempty; all stderr is empty. There are no failed or invalid official trials,
timeouts, captured DUT exceptions, false recovery or policy-inappropriate
escalations in this suite.

| Case, each arm/seed | I/O | Attempts / effective / rejected | Disruption / escalation |
|---|---:|---|---|
| clean | 2 | 0 / 0 / 0 | 0 / 0 |
| external_epoch_change | 11 | 3 / 2 / 1 | 11 / 0 |
| concurrent_pending | 5 | 1 / 0 / 1 | 0 / 0 |
| irrecoverable | 9 | 3 / 0 / 0 | 0 / 1 |
| skeptic_completion_at_dispatch | 4 | 1 / 0 / 1 | 0 / 0 |
| skeptic_incomplete_telemetry | 7 | 1 / 1 / 0 | 1 / 0 |
| skeptic_overlapping_faults | 12 | 0 / 0 / 0 | 0 / 1 |
| skeptic_failed_then_pending | 8 | 2 / 1 / 0 | 1 / 0 |

Each arm totals 174 processed calls and transport attempts, 141 observations,
33 repair attempts, 12 effective repairs, nine rejected requests, 39 authored
disruption units, nine external interventions and six appropriate escalations.
There are zero unsafe effects, duplicate dispatch audit keys, process losses,
offline ticks or model calls. Failed/rejected calls count toward I/O. The
duplicate metric covers repeated (step,target,lease) keys, not all semantic
retries. These deterministic public seeds vary generation/event increments;
the difference range [0,0] is not a confidence interval or unseen-incident
reliability estimate. No stochastic model-quality inference is justified.

The executable counterimplementation is frozen
[baseline.py](../../../evidence/f2be2f422bf84278b5104fcd7e102ff0/source/baseline.py):
a twelve-round direct loop with strict Pydantic Decision/Receipt boundaries,
shared sample/repair adapters and no evaluator import, case/seed lookup,
ledger or Orc dependency. Actual strict mypy passes again on a NEW source copy.
Its disclosed configuration skips the shared untyped tools/transport, so this
is not whole-program static verification. Installed pins are Python 3.13.9,
Pydantic 2.10.3, mypy 2.4.0 and active Orc 0.2.0 at bb9cb30d, TARGET=2.39.
The inherited Orc 0.1.0 metadata is not the imported implementation. The full
installed distribution inventory still matches the official environment.

Orc actually runs symbolic Python records/enums/when/loop through generated
.orc and the pinned compiler/runtime. It is not an imitation. Both arms use
the SAME domain policy, raw telemetry validators, file-RPC observations,
recovery permissions and plant-side actuator guard. Equal budgets are 24
processed calls, twelve policy rounds, three repairs, 25 seconds per case
including startup, at most one permitted restart and 120 seconds per suite.
No process loss is injected in C3. Both inner arms have zero models, prompts,
recorded answers, tokens, live-provider calls and delegation. The stipulated
outer model is gpt-6.1-sol/high on both sides. Persistent LangGraph is therefore
unnecessary for this scoped race claim; the actual persistent LangGraph
counterexamples in C1/C2 remain accepted and those claims stay retracted.
No actual AMI, pcdsdaq, Bluesky, ophyd or Snakemake comparison is asserted.

The zero saving has a causal explanation in the frozen simulator. The first
repair dispatch triggers the external intervention in each primary case.
Before it, observations cannot reveal that future change. In the epoch case
every previously issued lease becomes stale; in the pending case a competing
operation appears before the guard. With these schedules and permitted API,
a debugger that completes the objective must incur the first rejected request
in each case. Both constructions reach this conditional floor of two. It is
an ordering stress test rather than evidence of a frequent operational fault.
No extra observation privilege or timestamp shortcut favors either arm.

**S10-TOCTOU-ORACLE is repaired for the specific defect in this new round.**
The independent scorer now checks the logged action_time AFTER plant advance
and external intervention, BEFORE effect, against the permit, pending state
and incomplete target. Missing action_time fails closed. Fresh
[oracle probes](verification-001/oracle-probes.json) pass **98 assertions**:
48 recorded-trace rescores plus actual guarded/broken-guard epoch, pending
and completion-during-advance executions and outcome/boundary mutations.
Changing only pre-advance epoch no longer changes safety. Reading the old
frozen scorer on the new broken-guard epoch/pending traces reproduces its
safe=true error; the new scorer reports safe=false. No old evidence or score
has been rewritten. Recorder truth/effective flags remain trust assumptions;
this is not independent physical qualification.

I concede the measured benefit of the shared actuator guard. In the challenge's
preserved seed-11 ablations it prevents three invalid effects in EACH real arm:
epoch race, same-generation pending race and completion at dispatch. Disabling
it reduces primary rejections from two to zero and primary I/O from 16 to 15,
but fails safety. Event flow eventually recovers even in those unsafe runs;
eventual recovery cannot substitute for safe action. Disabling the races with
the guard retained yields primary I/O 15, zero rejections and passing checks.
Those ablations hold model quality at zero and share policy/validators. The
benefit belongs to common actuator code, and conventional Python reproduces it.
No exclusive static-check, runtime-provenance or orchestration benefit follows.
Known malformed composition is rejected before dispatch by both Orc and mypy;
future malformed count bytes are rejected at runtime by Orc and Pydantic.
The retained negative controls record those different failure times explicitly.

The audit also examines all **144 round-3 development/challenge traces**,
including all **ten expected safety failures**: four builder guard-disabled
cases and six challenge guard-disabled cases. All other checks in those rows
pass and no DUT exception is captured. The challenge's complete log audit
retains all 756 logs for its 80 traces. Four builder boundary-probe nonzero
exits and two independent challenge boundary-probe exits are expected malformed
input controls, not hidden experimental losses. Prior four obsolete-wrapper
failures and two must_not_repeat recovery refusals remain in the linked
[round-2 history audit](../../../uncertain-receipt-20261023T083808Z/round-2/skeptic-review-20261023T091637Z/history-audit.json).
The new review adds no paired trial matrix or dependency change: it audits the
official executions, reruns evaluator probes and strict mypy. The independent
challenge's earlier three-seed actual-library execution reproduces the official
parity. Further identical deterministic trials would add no decisive evidence.

Official local per-case wall min/median/max is Orc **3,544/4,187/4,870 ms**,
Python **132/146/160 ms**. This includes imports, schemas, subprocesses, RPC,
the guard and Orc compilation/closure work; separate mypy is untimed. Guard
CPU totals are 130,164 ns Orc and 95,872 ns Python. These noisy local costs
are not facility RPC latency or substitute acceptance metrics. Disclosed
nonblank/noncomment Python lines are 42 for the baseline, 121 for Orc
workflow/wrapper/adapter plus commands.json, and 81 shared policy/tools/transport
lines. The guard lives in the 138-line plant; oracle and suite add 81 and 139
lines, with evaluator/probe code additional. Both maintain schemas and domain
policy; Orc also maintains command closures, program identity and wrapper.
Human implementation hours, migrations and maintenance time are unmeasured.
Parity on dispatch costs does not refute a future precisely measured ergonomics
claim, but no such claim was measured here.

The painful operator task is finishing configure after another controller
changes state, then confirming event flow. Incidence, actual readback costs,
trustworthy generation/pending telemetry, feasibility of an atomic permit
service and approval of targeted recovery are **unknown**. The supplied research
snapshot cites [LCLS2 control at 04d36d15](https://github.com/slac-lcls/lcls2/blob/04d36d15c222ec6dbc10b833bf0c3ef5059a5c34/psdaq/psdaq/control/control.py)
(commit dated 2026-10-22) for existing state-machine guards, correlated
transitions and configure phases; [DaqLCLS2 at 4a3f2504](https://github.com/pcdshub/pcdsdaq/blob/4a3f2504b4d6f1860457ecfc40aaaf28115a777f/pcdsdaq/daq/lcls2.py)
(2026-09-08) for statuses, waiting, validation and timeout handling; and
[SLAC AMI, ICALEPCS2025 THAG005](https://proceedings.jacow.org/icalepcs2025/pdf/THAG005.pdf)
for existing Python mypy checks and graph monitoring. These primary citations
retain the local research snapshot's provenance; no network retrieval or
facility connection occurred. They establish mechanisms, not incident frequency
or an approved recovery policy. Generation alone is not experiment/run/config/
calibration semantic lineage; partial XTC/SMD completion, delayed human approval,
power loss and arbitrary unsafe replay are outside C3 and remain unclaimed.

| Stable objection | REVIEW disposition |
|---|---|
| S01-PARITY / C3 | Confirmed executable direct-Python counterexample; required margin fails on every seed. Builder must answer this independent construction. C1/C2 remain retracted. |
| S02-RELEVANCE | Serious blocker for the practical objective: no independent DAQ determination of incident correspondence, observations, costs, atomic guard feasibility or approved repair. Frequency stays unknown. |
| S03-CRASH-WINDOW | C3 tests dispatch races without injected loss. Earlier process-loss results retained; no power-loss or exactly-once guarantee. |
| S04-FRESHNESS | Invalid telemetry fails closed; shared action-time guard rejects races. Delayed approvals and arbitrary writers unqualified. |
| S05-LINEAGE | No scientific lineage/file-completion benefit inferred. These are scope limits, not added acceptance criteria. |
| S06-LEAKAGE | Serious qualification blocker: 100% public development, 0% independently withheld; no hidden-evaluator receipt. Debugger does not receive truth, but the cooperative source boundary is not isolation. |
| S07-ATTRIBUTION | Same policy/adapters/guard/permissions and zero models. Guard benefit is shared; no exclusive type, provenance, orchestration or ergonomic credit. |
| S08-ORACLE / S10-TOCTOU-ORACLE | Specific action-time defect closed by fresh causal controls in the NEW scorer. Recorder honesty and physical qualification remain assumptions. diagnostic_useful means current evidence linkage and nonempty explanation, not expert diagnosis. |
| S09-COST | All failed/rejected calls, effective actions, glue, validation/startup and evaluator costs disclosed; maintenance time unmeasured. |

Vote judgments are **COUNTEREXAMPLE, fair=true, reproduced=true,
relevant=false**. The counterexample directly addresses the synthetic C3 claim;
relevant=false preserves the unresolved qualified operational relevance of the
overall task, consistently with prior rounds. **Overall eligibility,
family_qualified and evaluator_qualified are false.** Blockers are S02 and S06.
Calibration was owner-waived, not passed, and the waiver is not a blocker.
Official evidence and local cross-review now exist; builder ANSWER and the final
controller integrity check remain required. Neither role can terminate with a
win on its own, and these blockers prevent the qualified consensus gate.

The smallest decisive next step for the broader practical objective is an
independent DAQ expert determination of incident correspondence, observation
cost/trust, atomic intervention feasibility and permitted recovery. A future
advantage experiment then needs a frozen claim/margin and independently withheld
variants. No new metric or further trial is necessary to recognize C3's zero
saving. Finite parity does not prove every possible Orc demo impossible.

One offline command reproduces this review's hash/log/paired-result audit,
actual oracle controls and strict mypy, writing only to a NEW destination:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python artifacts/action-time-race-20261023T093229Z/round-3/skeptic-review-20261023T1020Z/audit_review.py artifacts/action-time-race-20261023T093229Z/round-3/skeptic-review-20261023T1020Z/NEW-verification
```

To rerun the actual paired arms and ablations from their declared submissions,
the existing one-command construction remains available with a NEW destination:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python artifacts/action-time-race-20261023T093229Z/round-3/skeptic-20261023T0954/skeptic_reproduce_all.py artifacts/action-time-race-20261023T093229Z/round-3/skeptic-review-20261023T1020Z/NEW-paired-reproduction
```

All review artifacts are new. Controller, prompts, runner, opponent submissions,
prior-round artifacts and recorded evidence were not modified. No credentials,
network, facility connection, package installation, live model or delegation was
used.
