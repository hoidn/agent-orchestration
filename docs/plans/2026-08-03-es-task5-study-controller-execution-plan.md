# ES Task 5 Study Controller Execution Plan

## Metadata

- **Status:** Tasks 1–5 are complete and Task 6 deterministic synthesis is
  selected; no live provider allocation is authorized
- **Owner:** agent-orchestration maintainers
- **Governing component plan:**
  `docs/plans/2026-08-02-workflow-lisp-es-first-effectiveness-study-component-plan.md`
- **Entry commit:** `28e76e78559d83fca9ac9499bcfb031d4043371d`,
  tree `f76682a2fec0c558927b402e3b1cec272b43938c`
- **Required plan verdicts:** `ES_TASK5_PLAN_SPEC_APPROVED`, then
  `ES_TASK5_PLAN_QUALITY_APPROVED`
- **Required implementation verdicts:** `ES_TASK5_SPEC_APPROVED`, then
  `ES_TASK5_QUALITY_APPROVED`
- **Reviewed plan candidate:** commit
  `d6fb50bc9b7279416d4998706382e5737b025508`, tree
  `77a53ff95b3dca5942e569073c6cd255a81f3650`, plan SHA-256
  `bdef93f3c47d53881514b3a42aba2b16f8d183fb2b9b3937af76088c533d223d`
- **Plan review:**
  `artifacts/review/es-task5-study-controller-plan-review.md` records
  `ES_TASK5_PLAN_SPEC_APPROVED`, then `ES_TASK5_PLAN_QUALITY_APPROVED`
- **Live boundary:** Task 6 must freeze the complete package and receive the
  exact owner adoption before any provider-bearing ES attempt

## Objective

Implement the provider-free ES study controller over the landed target-2.25
trial entry. The implementation must preserve four distinct authorities:

1. generic E2 owns trial execution, settlement, packet construction, and the
   packet-freeze ledger row;
2. a new generic artifact-only projector preserves the already-constructed E2
   packet bytes and a closed index without changing E2 state or result shapes;
3. ES owns its private package/arm/label join, reviews, hard-finding
   classification, attempt accounting, and synthesis; and
4. the Task-6 owner-adopted decision lock remains the only live-launch
   authority.

The direct implementation uses one module per closed responsibility and one
test module per slice. This makes future changes to the packet-index or review
record schemas require explicit migration, but avoids a second runner,
post-terminal reconstruction, private executor hooks, or study behavior in
the generic runtime.

## Non-negotiable boundaries

- Use Subagent-Driven Development without worktrees.
- Begin every slice with a focused failing test and preserve the RED output.
- Do not call a real provider in Task 5.
- Do not recompile retained source, reconstruct a terminal execution after
  `run_trial_entry`, invoke `execute_trial_cells` from ES, or rebuild historical
  packets.
- Do not change the DSL target, trial ledger/state schema, verdict artifact
  schema, `TrialRunResult`, trial settlement, or scorer-visible packet bytes.
- Do not import or extend `orchestrator.experiments`.
- Do not modify `scripts/experiments/es/f1_evaluator.py`; consume its public
  observation evaluator.
- Do not add tests that assert provider prompt prose.
- Use injected deterministic dependencies for all provider-shaped calls.
- Preserve interruption as an outcome or a locked invalid attempt. Never
  resume an ES attempt.

## Dependency graph

```text
T5.1 packet artifact projection
  ├── T5.2 private blinding join
  ├── T5.3 review contracts
  ├── T5.4 hard-contract classification
  └── T5.5 attempt validity/accounting
             ↓
         T5.6 synthesis
             ↓
         T5.7 controller assembly
             ↓
         T5.8 provider-free E2E and closure
```

Tasks 5.2–5.5 have disjoint production modules and may run concurrently after
Task 5.1 lands. Task 5.6 consumes 5.3–5.5. Task 5.7 owns integration and CLI
changes. Task 5.8 alone owns the shared end-to-end fixture.

## Task 0: Accept this execution plan

**Files:** this plan; create
`artifacts/review/es-task5-study-controller-plan-review.md`; update only the
minimum index/routing assertion needed for discoverability.

1. Commit an implementation-free candidate.
2. Obtain `ES_TASK5_PLAN_SPEC_APPROVED` against its exact commit/tree/digest.
3. Obtain distinct `ES_TASK5_PLAN_QUALITY_APPROVED` against the same bytes.
4. Correct material findings and replay the ordered pair once.
5. Commit the accepted-plan transition and run the routing control.

Task 0 is complete against candidate `d6fb50bc`, tree `77a53ff9`, after
ordered `ES_TASK5_PLAN_SPEC_APPROVED` then distinct
`ES_TASK5_PLAN_QUALITY_APPROVED`. That gate selected Task 1 and authorized only
provider-free implementation; it did not adopt or execute the scientific lock.

## Task 1: Preserve the generic E2 packet bytes at freeze time

**Files:** create `orchestrator/workflow/trial/packet_artifacts.py`; modify
`orchestrator/workflow/trial/adjudication.py`; create
`tests/test_workflow_trial_packet_artifacts.py`; modify only the narrow existing
trial-adjudication fixtures needed to assert the new artifact.

RED first:

- one deterministic E2 evaluation must publish the exact canonical packet
  bytes before the first scorer invocation;
- the artifact index must bind the request, ledger header,
  `evidence_frozen`, `checks_frozen`, `packets_frozen`, sealed map, packet set,
  and exact ordered cell/label/digest/path rows;
- packet paths must be
  `artifacts/trials/<request-hex>/packets/<packet-digest-hex>.json`, with the
  index at `.../packets/index.json`;
- the existing verdict's `trial_request_digest` must be sufficient to derive
  the index path; and
- the scorer must receive byte-identical packet values after projection.

GREEN with one generic persistence function called immediately after the
existing packet freeze. Canonical regular files are write-once. Exact-existing
bytes are idempotent. Symlinks, nonregular paths, overwrite attempts, malformed
canonical JSON, missing/extra/duplicate rows, cell/label disagreement, and
digest drift fail closed. A crash after any packet write but before the index
is recoverable only by replaying the ordinary E2 evaluation boundary, which
revalidates exact-existing bytes; no new ledger row is added.

Verification:

```bash
pytest --collect-only -q tests/test_workflow_trial_packet_artifacts.py
pytest -q tests/test_workflow_trial_packet_artifacts.py \
  tests/test_workflow_trial_adjudication.py \
  tests/test_workflow_trial_packet_projection.py
```

Task 1 is complete at commit `9b1ba3df`, tree `cd7e25ce`, after 16 tests
collected, the 67-test focused gate passed, and ordered
`ES_TASK5_T1_SPEC_APPROVED` then distinct
`ES_TASK5_T1_QUALITY_APPROVED`. Tasks 2–5 are selected for their disjoint
provider-free implementations. This transition does not authorize live
provider allocation.

## Task 2: Implement the private package/arm/cell/label join

**Files:** create `scripts/experiments/es/blinding.py`; create
`tests/experiments/test_es_blinding.py`.

RED the exact positional assignment
`zip((PACKAGE-01, PACKAGE-02, PACKAGE-03, PACKAGE-04), arm_order)`, its join to
`TrialCellKey(arm, 1)`, the sealed E2 label map, and the packet index. Apply
`opaque_package_order` only for reviewer presentation. Reject duplicate,
missing, extra, wrong-repetition, cross-cell, or digest-mismatched data.

The public review projection contains only ordered opaque labels and packet
paths. It must not contain an arm, package, cell, workflow, source, sealed-map,
or private-join field. Unblinding occurs only after review and hard-evidence
records freeze. Orient only the sealed integrated RICH/DIRECT pair.

```bash
pytest --collect-only -q tests/experiments/test_es_blinding.py
pytest -q tests/experiments/test_es_blinding.py
```

## Task 3: Implement exact review and adjudication records

**Files:** create `scripts/experiments/es/reviews.py`; create the four closed
review schemas under `experiments/orc_effectiveness/f1_es/evaluator/`; create
`tests/experiments/test_es_reviews.py`.

Require four candidate rows and each perspective's exact ordered dimensions.
Require the canonical six ordered pair rows with
`A | B | TIE | INDETERMINATE`, bounded nonempty rationales, and packet-local
citations. The wrapper binds attempt, review kind, perspective when applicable,
fresh session/provider-attempt identity, receipt, packet set, presentation
order, and payload digest.

Material disagreement is only a normalized pair-outcome difference. One
block-level adjudicator receives both immutable initial records, reproduces
agreed rows, and decides only disputed rows. No dispute rejects before a call.
Invalid/missing initial review is failure, not disagreement. Adjudicator or
integrated-review failure yields the prescribed sealed indeterminate rows.

```bash
pytest --collect-only -q tests/experiments/test_es_reviews.py
pytest -q tests/experiments/test_es_reviews.py
```

## Task 4: Derive hard findings and the primary override

**Files:** create `scripts/experiments/es/hard_contract.py`; create
`tests/experiments/test_es_hard_contract.py`.

Derive dispositions controller-side. False complete observations default to
`PRODUCT_DEFECT`; exact oracle, conflicting-spec, or treatment-local
infrastructure proofs may replace that default. Missing, conflicting, or
multiple non-product proofs yield `UNRESOLVED`. Provider/candidate-authored
dispositions are rejected. Incomplete ten-clause coverage never enters
`evaluate_observations`.

Exhaustively test raw `RICH`, `DIRECT`, `TIE`, and `INDETERMINATE` against
missing trusted freeze, one-sided product blockers, unresolved blockers,
same-clause comparable blockers, noncomparable blockers, and attempted scorer
or prose substitution.

```bash
pytest --collect-only -q tests/experiments/test_es_hard_contract.py
pytest -q tests/experiments/test_es_hard_contract.py
```

## Task 5: Implement attempt validity and exact accounting

**Files:** create `scripts/experiments/es/attempts.py`; create
`experiments/orc_effectiveness/f1_es/attempt-record.schema.json`; create
`tests/experiments/test_es_attempts.py`.

Admit only the six frozen invalidity codes. Derive coherent allocation from
the validated E2 header and treatment start from the first durable
`cell_allocation_started`. Treatment-specific failures remain outcomes even
when all arms share a symptom. Settled scorer/reviewer/adjudicator/integrated
failures remain evaluation outcomes.

Require exact coverage of four arm settlements, four E2 scorer settlements,
two initial reviews, conditional zero/one adjudicator, one integrated review,
and every incurred receipt. Missing accounting, ledger disagreement, or an
impossible join is apparatus invalidity. Interruption after complete terminal
authority remains reportable; otherwise freeze the attempt invalid. Select
only the next locked attempt ID and enforce the absolute call ceiling.

```bash
pytest --collect-only -q tests/experiments/test_es_attempts.py
pytest -q tests/experiments/test_es_attempts.py
```

Tasks 2–5 are complete at commit `467f92f4`, tree `c3c79853`, against
reviewed staged binary-diff SHA-256
`b466a2fe3ed54fc297b33c7795b8b8d15a09715988a36974d85ca7b2531a3172`.
The final candidate passed 166 focused tests and public-module Pyright with no
errors before and after commit. The ordered final-byte reviews recorded
`ES_TASK5_T2_T5_SPEC_APPROVED` then distinct
`ES_TASK5_T2_T5_QUALITY_APPROVED`. Review corrections preserved fixed E2 cell
order while keying randomized package assignment, bound non-product proofs to
one frozen controller authority, rebuilt the complete decision lock and
randomization manifest against external expected bindings, and distinguished
an absent ledger from a supplied invalid ledger. Task 6 is selected for
provider-free implementation; this transition authorizes no live study call.

## Task 6: Implement deterministic synthesis

**Files:** create `scripts/experiments/es/synthesis.py`; create
`experiments/orc_effectiveness/f1_es/report.schema.json`; create
`tests/experiments/test_es_synthesis.py`.

Emit the typed four-arm vector, the derived RICH/DIRECT primary outcome,
factorial mechanism contrasts, hard findings, viability, known call/token/time
distributions, failure classes, claim limits, screen result, and E3 readiness
input. Enforce the exact decision lock (`N=2`, `M=3`, viability, known cost
ratio, unresolved-RICH rule) without filling a missing primary value from a
score, cost, or prose.

Regeneration consumes only immutable indexed records and must be byte
identical. Reject missing attempts, denominator extension, mutation of any
packet/review/finding/receipt record, or schema drift.

```bash
pytest --collect-only -q tests/experiments/test_es_synthesis.py
pytest -q tests/experiments/test_es_synthesis.py
```

## Task 7: Assemble the controller and provider-free CLI

**Files:** create `scripts/experiments/es/controller.py`; modify
`scripts/experiments/es/cli.py`; create
`tests/experiments/test_es_controller.py`; modify
`tests/experiments/test_es_cli.py`.

Validate every source/task/workflow/prompt/provider/check/evaluator/
environment/randomization/lock binding before launch. Invoke only
`run_trial_entry`; consume its persisted generic packet index; sequence two
initial reviews, optional adjudication, hard evaluation, integrated review,
receipt join, attempt settlement, and synthesis.

Use injected call dependencies. Task 5 may expose deterministic validation and
synthesis commands, but no live-launch bypass around Task 6. Prove both review
routes, every evaluator failure class, arm timeout, common invalidity,
interruption, fresh next-attempt selection, and the call ceiling. Add an import
guard over every new ES module for the retired package and forbidden private
runtime hooks.

```bash
pytest --collect-only -q \
  tests/experiments/test_es_controller.py \
  tests/experiments/test_es_cli.py
pytest -q \
  tests/experiments/test_es_controller.py \
  tests/experiments/test_es_cli.py
```

## Task 8: Prove provider-free public-entry end to end and close Task 5

**Files:** create `tests/experiments/fixtures/es_task5/fake_codex.py`; create
`tests/experiments/test_es_controller_e2_integration.py`; create
`artifacts/review/es-first-effectiveness-study-task5-review.md`; update the ES
plan and routing status only after the reviewed implementation is fixed.

Exercise the checked-in Task-4 trial through public `run_trial_entry` with a
deterministic local provider. Complete four cells, four scorers, two initial
reviews, both zero-adjudication and one-adjudication routes, hard evaluation,
integrated review, receipt join, packet persistence, and report synthesis.
Also prove a sibling-preserving arm failure, a terminal reviewer failure, and
an interruption whose attempt is never resumed and whose replacement uses the
next locked ID.

Run collection before the new modules, then the combined gate:

```bash
pytest --collect-only -q \
  tests/test_workflow_trial_packet_artifacts.py \
  tests/experiments/test_es_blinding.py \
  tests/experiments/test_es_reviews.py \
  tests/experiments/test_es_hard_contract.py \
  tests/experiments/test_es_attempts.py \
  tests/experiments/test_es_synthesis.py \
  tests/experiments/test_es_controller.py \
  tests/experiments/test_es_controller_e2_integration.py

pytest -q \
  tests/test_workflow_trial_packet_artifacts.py \
  tests/test_workflow_trial_packet_projection.py \
  tests/test_workflow_trial_adjudication.py \
  tests/experiments/test_es_blinding.py \
  tests/experiments/test_es_reviews.py \
  tests/experiments/test_es_hard_contract.py \
  tests/experiments/test_es_attempts.py \
  tests/experiments/test_es_synthesis.py \
  tests/experiments/test_es_controller.py \
  tests/experiments/test_es_controller_e2_integration.py \
  tests/experiments/test_es_cli.py
```

Run Pyright over every changed public Python module. Then run the broad suite
in tmux with `pytest -q -n 16 --dist=worksteal` and the standing non-security
scope, obtain ordered `ES_TASK5_SPEC_APPROVED` then distinct
`ES_TASK5_QUALITY_APPROVED` against exact bytes, commit, and rerun the focused
and routing controls postcommit.

## Completion criteria

Task 5 is complete only when the generic packet artifact projection is
byte-authoritative and idempotent, the full ES controller works through the
public E2 entry without live providers, every locked failure/override/
accounting route is covered, deterministic report regeneration succeeds from
immutable records, ordered final reviews approve the exact implementation,
and postcommit controls pass. Completion selects Task 6; it does not adopt the
scientific lock or authorize a live provider call.
