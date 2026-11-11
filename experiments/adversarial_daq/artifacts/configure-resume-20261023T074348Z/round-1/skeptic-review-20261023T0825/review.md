**REVIEW — COUNTEREXAMPLE to C1. Uncalibrated exploration.** The implemented
LangGraph baseline matches Orc on the predeclared I/O metric and all controls.
The official evidence and a new frozen-source reproduction both show a saving
of **zero**, against the required minimum of one call on every seed. This
refutes the exact synthetic advantage claim. Operational relevance remains
unqualified; this review does not authorize a practical LCLS-II advantage claim
or assert family/evaluator qualification. Calibration was explicitly waived.

The exact bounded claim, preserved verbatim from frozen `claim.json`, is:

> In the four-case synthetic configure-recovery suite with one debugger process loss in each interrupted case and public seeds 11,23,47, the typed-Python/generated-.orc arm uses at least one fewer accepted recovery I/O call summed over partial_readback and phase2_late for every seed than the strongest equal-budget baseline, while both arms pass all five checks on every case and Orc adds no repair attempts, rejected actions, disruption, or escalation.

The evidence digest is
`3c6bb3475de93e32c7fc9afc8d6d0317d113a788669ea8bf5e3c095bc8964cd4`.
The recorder source SHA-256 is
`861a5e077faf5dcb713cf85d3ea351e4036c71442c43278907474d1eb0bfc01d`.
These identify different things. I read the [official report](../../../evidence/ba4a285b56bf4a9d969cb9f9e5315c05/report.json),
the runner's immutable [source snapshot](../../../evidence/ba4a285b56bf4a9d969cb9f9e5315c05/source/suite.py),
both frozen dossiers/manifests, all implementation modules, the scorer and the
raw case outputs. The outer recorder is retained here as a
[reviewed byte-for-byte copy](reproduction-001/runner-reviewed.py); its hash
matches the official recorder hash. It was never edited in place.

The predeclaration requires `baseline.total_io - orc.total_io >= 1`, summed over
only `partial_readback` and `phase2_late`, separately for each seed. All five
checks must pass for every original and added case. Repair attempts, rejected
actions, disruptions and escalations must be noninferior per case. Wall time,
source length and added cases cannot replace this margin. The preserved
[pre-experiment claim](../development/trial-002/claim.json) has the same string
and acceptance criteria. The builder explicitly retracted C1 after its Python
memo experiment; this review independently tests the stronger submitted
LangGraph implementation rather than treating that concession as evidence.

| Public seed | Orc primary I/O | LangGraph primary I/O | Baseline minus Orc | Required |
|---|---:|---:|---:|---:|
| 11 | 14 | 14 | 0 | at least 1 |
| 23 | 14 | 14 | 0 | at least 1 |
| 47 | 14 | 14 | 0 | at least 1 |

All **48 official case executions pass all five checks**: 240 true checks,
zero failed checks, zero suite exceptions/timeouts and zero captured DUT errors.
The new reproduction adds 48 paired executions and 16 ablation executions,
all passing. It preserves the same per-seed primary differences and has no
exceptions. Strict mypy exits zero. These are deterministic public cases; the
observed difference range [0, 0] is not a confidence interval. Three seeds vary
generations and event increments, not independently sampled fault families.
No stochastic agent adequacy or population inference is claimed.

| Case | Accepted I/O, each arm, every seed | Repairs / rejected / disruption / escalation |
|---|---:|---|
| clean | 2 | 0 / 0 / 0 / 0 |
| partial_readback | 9 | 3 / 0 / 11 / 0 |
| phase2_late | 5 | 1 / 0 / 1 / 0 |
| irrecoverable | 9 | 3 / 0 / 0 / 1 |
| skeptic_epoch_race | 6 | 2 / 1 / 1 / 0 |
| skeptic_compound_ambiguous | 12 | 0 / 0 / 0 / 1 |
| skeptic_missing_then_late | 8 | 1 / 0 / 1 / 0 |
| skeptic_partial_uninterrupted | 9 | 3 / 0 / 11 / 0 |

Each arm totals 180 accepted I/O calls, 192 transport attempts, 39 repair
attempts, 21 effective repairs, three rejected requests, six escalations and
75 synthetic disruption units across the official matrix. The twelve extra
transport attempts are the twelve deliberately dropped requests per arm;
they have no effect and are excluded from accepted I/O equally. The stale
generation rejection is counted, has no effect and is followed by fresh
readback and recovery. Permanent and compound faults escalate correctly;
there is no unnecessary escalation or disruption under the frozen policy.
All 24 paired journals, transport histories, final truth objects and debugger
outputs are exactly equal, beyond merely equal aggregate scores. See
[supplemental checks](supplemental-checks.json).

I rehashed all **1,146 recorded artifacts** and the report digest before
reproduction and verified integrity again afterward. Every raw trace was
rescored with the unchanged independent scorer and matched the trace,
trial result and stdout row. I read all 96 top-level case stdout/stderr logs;
the receipt inventories their hashes and retains nonempty stderr content.
All six suite stderr files and all baseline case stderr files are empty.
The twelve nonempty Orc case stderr logs contain only expected `effect_rerun`
messages at injected resume points. They are recorded retry diagnostics, not
hidden successful actions or unexpected exceptions. The scorer's 14 independent
negative/control assertions pass on each of the six official trial directories:
84 assertions total. These include false success after an acknowledgment,
stale proof, generation changes, unhealthy truth, healthy refusal, unbound
escalation, absent reason, excessive time, DUT error and unsupported effect.

The preserved builder `trial-001` has **four failed case executions**, each
with all five checks false and `debugger exited 1`. Its stderr reports
`RuntimeError: missing runtime state`; the obsolete wrapper searched the wrong
state directory and could start a new run after loss. Those development
failures remain in the source dossier and supplemental review receipt. They
are not attributed to physical DAQ recovery or omitted from history. Both
skeptic development receipts report no exceptions, passing checks and passing
mypy. A brief read-only review-summary command initially assumed a list receipt
was a dictionary; correcting that inspection did not change any trial or
evidence. The official and new measured matrices have no invalid trials.

The counterimplementation is the frozen [baseline.py](../../../evidence/ba4a285b56bf4a9d969cb9f9e5315c05/source/baseline.py):
actual LangGraph 1.2.16 Functional API tasks and entrypoint, persistent
SqliteSaver, synchronous durability, deterministic interrupts bound to
target/epoch/lease, strict Pydantic 2.10.3 boundary models and a SQLite
intent/receipt ledger. Pin receipts record langgraph-checkpoint 4.3.0,
langgraph-checkpoint-sqlite 3.1.2, langchain-core 1.7.0, mypy 2.4.0 and SQLite
3.50.2, alongside all installed distributions. The reproduction confirms the
installed distribution list matches official evidence. Nothing was installed
or upgraded. This is an executed conventional construction, not an imitation
of LangGraph. Strict mypy applies to the baseline; the disclosed configuration
skips typing the shared domain-policy and transport imports.

Both arms use the same raw telemetry, domain decision function, narrow local
RPC adapter, actuator guard, recoverability policy, permissions and
24-call/25-second case limits, with one permitted loss/restart. Both use zero
models, prompts, tokens, native delegation and model calls. The baseline's
automatic interrupt authorization introduces no observation or permission
unavailable to Orc; it is not a human approval experiment. Each arm observes
again after uncertain repair receipts. The receipt ledger and task replay
avoid repeating completed observations in the tested process-loss windows.
Neither arm has evaluator-truth access in its policy. Sources are public to
the engineers; this remains a cooperative interface boundary rather than an
OS sandbox or hidden evaluator.

The useful measured benefit conceded to Orc is persistence against the
forgetful ablation. In the new seed-11 ablation, direct Python uses 10 calls
in `partial_readback`, while Orc, LangGraph and the small durable Python memo
use nine. Their two-primary-case totals are 15 versus 14. The added
uninterrupted partial case uses nine in every implementation, isolating the
restart cost. In the epoch-race control direct Python uses five calls versus
six for durable arms: extra reacquisition avoids the stale request. This
countervailing result is preserved, not averaged into C1. Model quality and
domain policy are held constant; there is no evidence here attributing the
saving exclusively to Orc, proving exclusive static checks or measuring
engineering-time savings.

Official per-case wall times range from 3,964–7,080 ms for Orc and 965–2,190 ms
for LangGraph. The reproduction ranges are 4,060–7,141 ms and 929–2,239 ms.
These include the submitted wrappers' startup, persistence and resume;
Orc also compiles as selected by its wrapper. Mypy is a separate untimed
preflight. These are local implementation costs, not a controlled ergonomics
experiment, facility RPC latency or a substitute victory metric.
The disclosed source inventory is 113 nonblank/noncomment Python lines for
the baseline and 124 across Orc workflow/adapter/wrapper, plus its command
manifest; shared domain/transport code contributes 91 lines. Baseline
maintenance includes interrupt/task ordering, receipt schema/key stability,
SQLite and checkpoint/thread setup. Orc maintenance includes command closures,
program identity, schemas and resume integration. Both maintain the same
domain guards. No human maintenance-time advantage was measured.

The operator task is retaining diagnostic progress and uncertain configure
receipts after debugger loss, then verifying acquisition. Its frequency and
actual observation cost are **unknown**. The supplied research snapshot cites
[LCLS2's pinned controller](https://github.com/slac-lcls/lcls2/blob/04d36d15c222ec6dbc10b833bf0c3ef5059a5c34/psdaq/psdaq/control/control.py)
for configure phases and transition correlation, and
[DaqLCLS2](https://github.com/pcdshub/pcdsdaq/blob/4a3f2504b4d6f1860457ecfc40aaaf28115a777f/pcdsdaq/daq/lcls2.py)
for status waiting, validation and timeouts. These establish relevant existing
mechanisms, not incidence or an approved recovery. The
[SLAC AMI paper](https://proceedings.jacow.org/icalepcs2025/pdf/THAG005.pdf)
also defeats a broader suggestion that Python graphs inherently lack preflight
type checking. These primary URLs retain the supplied research's dates and
provenance; this review used synthetic local tools and did not retrieve external
sources or contact a facility. Actual pcdsdaq/Bluesky/ophyd are not run here;
no comparison with their controls behavior is claimed.

| Stable objection | REVIEW disposition |
|---|---|
| S01-PARITY | Confirmed by official evidence and new frozen-source execution. C1 fails its unchanged margin on every seed; the builder must answer this actual LangGraph construction. No further experiment is needed to demonstrate this bounded parity. |
| S02-RELEVANCE | Remains serious for the practical DAQ objective: no expert receipt establishes incident correspondence, frequency, readback costs or approved targeted repairs. Operational relevance remains false/unqualified. |
| S03-CRASH-WINDOW | Scoped limitation: kills occur before the interrupted request's effect, after earlier receipts were available. No applied-operation/lost-receipt, power-loss or arbitrary offline evolution guarantee. |
| S04-FRESHNESS | Race rejection is reproduced and credited to the shared actuator guard. Synthetic ticks/generations are explicit observations, not mtime shortcuts. Immediate deterministic authorization does not test real delayed human approval. |
| S05-LINEAGE | Experiment/run/calibration revision and partial XTC/SMD completion are absent. Not necessary for C1; no scientific-data readiness benefit may be inferred. |
| S06-LEAKAGE | All cases, seeds and oracle are public development material. No genuinely withheld material or independent evaluator receipt exists. No generalization or family/evaluator qualification is established. |
| S07-ATTRIBUTION | Same policy/validators and zero models isolate completed-work persistence. Durable conventional tools reproduce the benefit. Typing/provenance/ergonomics advantages beyond C1 remain unmeasured. |
| S08-ORACLE | Frozen synthetic scorer cross-checks pass. `safe` assesses effective actions; rejected attempts are separately reported. Physical truth, disruption weights and impossible-case policy remain authored benchmark assumptions, not expert certification. |
| S09-COST | Glue, receipt persistence and local time disclosed. No source-length or human maintenance-effort claim substituted for the I/O margin. |

**Vote judgments:** `position=COUNTEREXAMPLE`, `fair=true`, `reproduced=true`,
`relevant=false` for qualified practical DAQ relevance. The synthetic numerical
refutation is direct and relevant to C1; the false relevance flag preserves the
previously disclosed operational qualification limit rather than changing C1's
metric. **Eligibility is false** while serious operational objections remain.
Blockers are S02's missing expert determination and S06's absent independently
withheld evaluation/receipt for an operational or generalization claim.
Calibration waiver is not a blocker and is not a passed qualification.
The blocker list does not demand a new experiment to recognize C1's parity.

If the broader search continues, the smallest decisive next step is an expert
determination of whether this combined configure/debugger-loss situation occurs
with costly enough observations under the proposed permitted repair policy to
matter to operators. A new advantage claim would then need its own predeclared
cost margin and genuinely withheld variants. A future ergonomics claim needs
measured engineering effort. Neither finite parity nor this relevance gap
establishes universal impossibility of an Orc advantage. The builder's ANSWER
and the controller's final integrity check remain required procedural steps.

One offline command reproduces the review using frozen official sources,
verified recorder bytes, actual libraries, strict mypy, both paired arms,
the two Python ablations and retained raw outputs. Supply a new destination:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python artifacts/configure-resume-20261023T074348Z/round-1/skeptic-review-20261023T0825/review_reproduce.py artifacts/configure-resume-20261023T074348Z/round-1/skeptic-review-20261023T0825/NEW-reproduction --ablations
```

The completed [review reproduction receipt](reproduction-001/receipt.json),
[reproduction source](review_reproduce.py) and
[supplemental checks](supplemental-checks.json) are new review artifacts.
Original submissions, controller, prompts, runner and recorded evidence were
not edited. No live model, delegation, network or facility call was made.
