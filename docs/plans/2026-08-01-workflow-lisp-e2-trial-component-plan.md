# Workflow Lisp E2 `trial` Component Implementation Plan

## Metadata

- **Status:** accepted for E2 execution; Tasks 0–7 complete and Task 8 selected
- **Owner:** agent-orchestration maintainers
- **Selected tranche:** E2 only — concurrent pinned child trials, evidence
  freezing, blinding, and adjudication
- **Target DSL:** 2.25
- **Baseline:** commit `7fbfc69809a44bcb707e27718306dedc26ea25f5`,
  tree `4e7e908ec68c67d17155a1a8178bde9207206c05`
- **Predecessor gate:** `PASS_E1` in
  `artifacts/review/e1-run-ref-final-review.md`
  (`sha256:af816ae147b4c64f737c05a11a32cbfbea8e3ceba5594e9c2717f23a66486a34`)
- **Selection authority:**
  `docs/plans/2026-07-31-workflow-lisp-e1-e3-owner-selection.md`
- **Required ordered plan verdicts:** `E2_PLAN_SPEC_APPROVED`, then
  `E2_PLAN_QUALITY_APPROVED`
- **Required ordered final verdicts:** `E2_FINAL_SPEC_APPROVED`, then
  `E2_FINAL_QUALITY_APPROVED`
- **Reviewed plan candidate:** commit
  `c6046d38e53dc495270f473592a55de47731e64d`, tree
  `40c533fc0ab21230415a5ce5d84dfcc677552f51`, plan SHA-256
  `abf62404ec0f7a443a9547e9bec2c86c32941e4ffc448ef5ca437e86170a1510`
- **Plan review:** `artifacts/review/e2-trial-plan-review.md`
  (`sha256:3b739ae2dc6f66743e1e3eecca23d7887a183dd97369f9c522b0b8929de84001`);
  `E2_PLAN_SPEC_APPROVED`, then `E2_PLAN_QUALITY_APPROVED`
- **Governing inputs:**
  - `docs/design/workflow_lisp_trial_runs.md`
    (`sha256:ed4b4090b71f4310e09aa59d3f347245c640c0727eceec8baf1344a14c53cf53`)
  - `docs/design/workflow_lisp_program_search_boundaries.md`
    (`sha256:a42a1db72b887eb94cfa7c3fe93fe6e7269e99daa2867ccd484d16bbe0f0d41b`)
  - `docs/design/workflow_language_design_principles.md`
    (`sha256:36a4b4d5626e0d6f7c3444c49f74856a7d4d11cb3bad745e2c475b8b80fe0951`)
  - `docs/design/workflow_lisp_pure_result_replay.md`
    (`sha256:051b6330d122faa4e3f365e979e6dc07f4e070c50cb84134a52c1d3ef71efe27`)
  - landed ML at-least-once/single-writer behavior and the exact target-2.24
    E1 runtime at `577715f1`

## Authority reconciliation

The accepted trial-runs design and the roadmap's top-level **Current E
Program Shape And Gates** section are authoritative. E2 therefore means the
target-2.25 `trial` form over E1 `run-ref`: arms × repetitions, frozen whole-run
evidence, blinded packets, deterministic checks, adjudication, and a verdict
artifact.

The roadmap's later historical E2 section describes an older
`ExecutionAdmissionPolicy` / `ExecutionInstanceSpec` /
`RegisteredExecutionInstance` registry and handle service. That substrate
conflicts with the accepted design's explicit decision not to revive the
parked registry: Git commits are admission identity and the ordinary full
compiler is certification. It is not selected here. This plan salvages only
the non-conflicting expectations that E2 expose an experimental SDK/CLI and a
non-evolution what-if client over the same canonical trial service, reconcile
crashes without duplicate child launches, and impose zero trial overhead on
ordinary runs.

No registered handles, registry rehash/revocation machinery, prompt/provider
occurrence placeholders, E2O observation substrate, C1-C3 surface, or E4P
extension may enter E2.

## Objective

Land the smallest target-2.25 form that executes two or more exact E1
`run-ref` arms for a bounded number of repetitions, concurrently but under one
parent-owned coordinator. Every admitted cell produces a completed or failed
value. Evaluation starts only after the complete admitted evidence set is
frozen, sees opaque labels and a closed packet, runs deterministic checks
before any soft judgment, and emits a digest-bound verdict artifact. A parent
resume validates and reuses completed cells, discards and reruns incomplete
cells with fresh E1 ordinals, and never launches one cell twice from the same
authoritative settlement.

The exit proof is a new platform-owned DIRECT/COORDINATOR/ORC fixed study over
deterministic fixture repositories. It reproduces the lean pilot's treatment
separation and method-failure accounting; it is not a rerun or reinterpretation
of a pilot evidence root and makes no effectiveness claim.

## Direct architecture and deliberate cost

A distinct `TRIAL` effect crosses the existing Workflow Lisp compiler views.
Its executable config embeds an authored-order tuple of already validated E1
`RunRefStepConfig` values plus frozen evaluation and budget contracts. A new
`orchestrator/workflow/trial/` package owns trial identity, append-only event
state, scheduling, evidence packets, checks, scoring, aggregation, and
settlement. `WorkflowExecutor` delegates one outer atomic effect to that
package.

Every `(arm, rep)` cell uses the E1 runtime service. Before fan-out, E1's
synchronous lifecycle is factored into a behavior-preserving driver whose
blocking work emits immutable progress/settlement events to a caller-owned
sink. Ordinary `run-ref` wraps it synchronously and preserves its exact ledger
paths and behavior. Trial workers perform blocking child work concurrently,
but only the trial coordinator consumes events, appends the parent/trial and
trial-scoped E1 ledgers, records a cell settlement, and finalizes its E1 edge.
The outer workflow state is written once, after the terminal trial result and
verdict validate.

Target 2.25 also admits recursively transportable record/union elements below
bounded list/optional/map containers. That is a generic structural transport
correction required by `List[ArmOutcome]`, not a trial-name exception; closed
contract validation, depth/size bounds, direct wire values, and older-target
behavior remain intact.

This makes heterogeneous arm return types, dynamically assembled arm lists,
nested trials, portable wrappers with runtime-supplied Git pins, and
enforceable token/cost ceilings harder to add later. V1 instead has one
homogeneous value contract, static arms, closed cardinality bounds, literal
pins inherited from E1, and enforceable launch/evaluator-count plus elapsed
time budgets. Usage and cost remain recorded exactly, including `"UNKNOWN"`.

## Exact authored surface

The target-2.25 form is:

```lisp
(trial
  :arms ((:id "direct"
          :run-ref
          (run-ref
            :source (:repo "/absolute/repository" :commit "0123456789abcdef0123456789abcdef01234567")
            :program (:path "experiments/direct.orc" :entry direct)
            :inputs (:task task)
            :returns Value
            :policy (:environment :deterministic-effect-free :setup ())))
         (:id "orc"
          :run-ref
          (run-ref
            :source (:repo "/absolute/repository" :commit "89abcdef0123456789abcdef0123456789abcdef")
            :program (:bundle orchestrated)
            :inputs (:task task)
            :policy (:setup ()))))
  :reps 3
  :max-concurrency 4
  :evaluation
  (record
    :checks (list
      (record :id "correctness"
              :command (list "python" "-m" "pytest" "-q" "tests/acceptance")
              :authority "correctness"
              :required true
              :timeout-ms 600000))
    :judgment
    (record :provider "scorer"
            :rubric-asset "rubrics/trial.md"
            :evidence-confidentiality "same_trust_boundary"
            :evidence-limits
            (record :max-item-bytes 65536 :max-packet-bytes 262144))
    :observation
    (record :include
            (list "task_spec" "validated_result" "workspace_delta"
                  "check_results" "declared_artifacts" "failure_evidence")
            :diff-cap-bytes 262144
            :reveal-provider-identity false)
    :aggregation
    (record :mode "independent_rubric"
            :rep-combine "median"
            :tie "authored_order")
    :success-rule
    (record :superior
            (record :min-abs-improvement 0.10 :max-cost-ratio 1.5)
            :non-inferior
            (record :min-cost-reduction 0.20)
            :count-failures-as-outcomes true))
  :budget
  (record :arm-timeout-ms 900000
          :trial-timeout-ms 3600000
          :max-evaluator-attempts 6
          :max-evaluator-concurrency 2))
```

Binding rules:

- keys are closed and unique; `:arms`, `:reps`, `:max-concurrency`,
  `:evaluation`, and `:budget` are required;
- 2–16 authored arms have unique non-empty literal string IDs; repetitions are
  1–64; total cells are at most 256; arm concurrency is 1–32 and no greater
  than total cells;
- each `:run-ref` is nested syntax elaborated into a static E1 config, not a
  first-class effect value. It retains E1's literal source/program/policy
  identity and ordinary dynamic input expressions;
- all arms have the same normalized child `value` descriptor. Exact `Value`
  is the opt-in loose contract when arms intentionally differ below that
  transport boundary; no wrapper taxonomy is required;
- `:evaluation` and `:budget` are compile-time pure structural record values.
  Runtime-dependent referees reject as
  `trial_evaluation_contract_not_pure`;
- checks have unique IDs, literal argv, authority
  `correctness|invariant`, a Boolean required flag, and a positive timeout.
  They run without a shell in the completed arm workspace. Their complete
  exit/duration/output-digest facts and bounded output bytes are evidence;
- v1 judgment is required and uses one resolved provider plus one resolved
  rubric asset for every cell. Confidentiality is exactly
  `same_trust_boundary`; item and packet limits are positive and packet ≥
  item; observation include values come from the closed list above and
  provider identity reveal is exactly false;
- v1 aggregation is independent rubric scoring, median repetition combine,
  and authored-order tie breaking. One frozen success rule applies to all
  arms;
- budgets enforce positive arm/trial deadlines, an exact total evaluator
  attempt ceiling, and an evaluator concurrency ceiling. Trial timeout or
  attempt exhaustion settles pending cells as failures; already running cells
  finish and are charged. Unknown tokens/cost remain facts, not invented
  numbers;
- `trial` is admitted where `run-ref` is admitted, except that neither a trial
  nor an arm may contain a reachable nested `trial` in v1. It remains invalid
  in pure functions, pure settlement/evaluation bodies, `loop/recur`,
  `list/map-effect`, and generated iteration frames; and
- targets below 2.25 reject with `trial_target_dsl_unsupported`. Structural
  refusal codes remain the accepted `trial_*` families and add only the
  bounded shape codes `trial_arms_invalid`, `trial_arm_result_mismatch`, and
  `trial_nested_unsupported`. Each refusal carries the rejected value and
  stable secondary causes.

## Compiler-owned result and evidence types

Each site receives compiler-generated monomorphic types. `T` is the common
arm value descriptor:

```text
TrialResult$<site> = {
  outcomes: List[TrialArmOutcome$<site>],
  verdict: TrialVerdict,
  verdict_artifact: TrialVerdictPath
}

TrialArmOutcome$<site> =
    Completed { arm_id: String, rep: Int, value: T,
                evidence: CompletedTrialEvidence$<site> }
  | Failed    { arm_id: String, rep: Int, failure: TrialFailure,
                evidence: PartialTrialEvidence }
```

Completed evidence retains the validated E1 workspace delta and accounting,
deterministic check results, opaque evaluation label, packet/scorer identity,
score, and exact run/attempt lineage. Partial evidence retains only facts that
actually exist and never fills missing fields with defaults. `TrialFailure`
has a stable code, phase, retryable flag, and ordered secondary causes.
`TrialVerdict` records authored arm order, per-repetition scores/outcomes,
aggregate scores, ranking, selected arm or null, success-rule disposition,
and complete budget accounting. `TrialVerdictPath` is a load-bearing relpath
contract rooted below `artifacts/trials/` with existence required.

The result reveals authored arm IDs only after scoring. Evaluator packets and
score rows carry opaque labels. Full label bindings remain sealed in the
run-owned ledger until the unblinded verdict join.

## Identity, persistence, and replay

`TrialStaticConfig.digest` hashes target/lowering versions, site identity,
authored arm order and E1 config digests, common result contract, reps,
evaluation, budget, and compiler/runtime identity. The runtime request digest
adds the complete parent run/frame/visit identity and resolved input values.
Completion order, timestamps, workspace paths, opaque-label salt, and provider
output never enter static identity.

One `trial_event_ledger.v1` lives at the exact run/frame/step/visit scope. It
records only validated effect/public-boundary facts:

- trial request/static/evaluation/budget identities and the frozen ordered
  `(arm, rep)` cell domain;
- one sealed opaque-label map and its digest;
- per-cell allocation, scoped E1 ledger/root, prepared settlement, committed
  E1 row, completed/failed outcome, and evidence digests;
- the frozen admitted evidence-set digest before checks/scoring;
- check, packet, scorer-attempt, score, aggregation-input, verdict, artifact,
  and outer-parent-settlement digests; and
- exact terminal status and budget counters.

Pure ordering, median/ranking, rendered packet views, and report projections
are recomputed from validated facts through M2-style transient replay. There
is no second derived-value cache, effect-identity memo key, cross-run memo, or
persisted optimizer state.

Each cell owns a disjoint trial-scoped E1 attempt ledger, but the parent trial
coordinator is the sole writer of every one. Workers cannot write parent state
or ledgers. On resume:

- an exact cell settlement validates and reuses with zero child launch;
- a child completed before cell settlement is incomplete, so its exact E1
  workspace is discarded and the cell reruns with a fresh ordinal;
- a cell settled before the adjacent E1 commit edge is reconciled from the
  exact trial row with zero launch;
- missing, corrupt, ambiguous, escaping, or cross-cell authority fails closed;
  and
- failures remain values and never cancel completed or in-flight siblings.

The outer lexical checkpoint policy is `reuse_validated_trial_result` and
retains every existing root/callee/input/checkpoint guard.

## Evidence freezing, blinding, and adjudication reuse

The coordinator freezes the complete admitted cell outcome set before any
check or evaluation call. It then runs checks in authority order, builds one
packet per opaque cell label, scores independently, aggregates repetitions,
joins the sealed label map only after scoring, and writes one verdict artifact.

Packets exclude treatment/arm IDs, source text and filenames, proposer and
candidate lineage, child/evaluator completion order, mutable run logs,
`.orchestrate` sidecars, previous scores, and provider/model identity. Packets
include only the declared task specification, validated result, bounded E1
workspace delta, permitted declared artifacts, deterministic check results,
and explicit failure evidence. Every evaluator citation must resolve to an
item in that exact packet. Packet assembly, exclusion, limits, identity,
strict output parsing, citation validation, budgets, and aggregation are
runtime obligations, never prompt instructions.

Reuse is algorithmic, not a false claim that existing candidate-provider
packets already fit. E2 reuses adjudication scorer identity, strict JSON
output parsing, provider execution, and ledger materialization. Existing
single-winner candidate selection is explicitly not reused: E2 owns
repetition aggregation, failures-as-outcomes, success-rule disposition, and
authored-order tie handling. It introduces trial packet and trial score-row
schemas because the existing packet/rows are intrinsically
candidate-prompt/provider-shaped; trial code must not fabricate
provider-candidate metadata to fit them. Source promotion remains excluded:
E2 emits a verdict artifact only.

## Public experimental SDK, CLI, and non-evolution client

The public Python entry is a thin experimental service over ordinary compile
and run:

```python
run_trial_entry(
    workflow_file=Path(...),
    entry_workflow="...",
    inputs={...},
    workspace=Path(...),
    state_dir=Path(...),
    run_ref_root=Path(...),
) -> TrialRunResult
```

The CLI is `orchestrate trial WORKFLOW --entry-workflow NAME` with the ordinary
input/source-root/extern/state/run-ref-root flags. Both require a target-2.25
entry whose terminal public result is the exact compiler-owned trial result,
invoke the ordinary full compiler and executor, and return one versioned JSON
summary containing run ID, terminal status, verdict digest/path, and failure
diagnostic. They cannot accept raw executable configs or bypass compilation,
admission, state, or E1 runtime validation.

The first non-evolution client is a two-arm regression/what-if runner using
that same entry. Because E1 deliberately requires literal canonical repository
locators and commits, a portable checked-in wrapper cannot parameterize pins.
The E2E fixture therefore materializes and retains one concrete `.orc` wrapper
after its fixture repositories receive exact commits, then compiles and runs
that wrapper through the public SDK/CLI. This does not add a registry, dynamic
pin syntax, or a misleading copy-safe production workflow.

## Exclusions

E2 does not implement or modify:

- registries, registered execution handles, revocation/rehash services, or
  E4P's future non-empty provider occurrence maps;
- candidate/genome/population/search/fitness/promotion semantics;
- C1-C3, E2O, E3, E3F, prompt calculus, or P-series behavior;
- runtime `eval`, closures, hot replacement, parent checkpoint import,
  dynamic arm construction, heterogeneous arm result contracts, or nested
  trials;
- source promotion, canonical-source mutation, submodules, LFS, or cross-
  compiler-version children;
- provider isolation, sandboxing, secrets, permissions, capability policy,
  or any security-related implementation or test; or
- prompt prose for deterministic obligations.

## Execution discipline

Use Subagent-Driven Development without worktrees. Every behavior task begins
with the narrowest missing-behavior RED, implements only enough to turn it
GREEN, receives an independent specification review followed by a distinct
quality review, commits the exact reviewed paths, and runs its named
postcommit control. A material correction restarts that task's ordered review
pair; unchanged closed E0/E1/M2/adjudication surfaces are not re-reviewed.

Long and broad runs use tmux. New modules receive `pytest --collect-only -q`.
The final broad gate is `pytest -q -n 16 --dist=worksteal` with the standing
user-directed security/safety/secrets/provider-isolation exclusions. No
excluded test counts as passing E2 evidence.

## Task 0: Accept this E2-only component plan

**Files:** this plan; `artifacts/review/e2-trial-plan-review.md`; exact E-series
routing/status rows and routing tests.

- [x] Commit a proposed plan with status plan-review-pending and no E2
      implementation claim.
- [x] Obtain `E2_PLAN_SPEC_APPROVED` against exact plan bytes, the governing
      design digests, `PASS_E1`, and the authority reconciliation above.
- [x] Obtain distinct `E2_PLAN_QUALITY_APPROVED` once.
- [x] Correct material findings, replay the ordered pair only if bytes change,
      record the reviewed plan digest, mark it accepted-for-execution, and
      commit the routing transition.
- [x] Run the complete routing and route-readiness controls postcommit.

Task 0 review closed against commit `c6046d38`, tree `40c533fc`, after
ordered `E2_PLAN_SPEC_APPROVED` then `E2_PLAN_QUALITY_APPROVED`. The first
quality pass rejected reuse of target-2.11 single-winner selection and found
three recovery REDs scheduled before their owning mechanisms. The corrected
candidate explicitly makes aggregation trial-owned and places child,
evaluation, and outer-settlement recovery in Tasks 7, 8, and 9 respectively;
the ordered review pair then approved the same exact bytes. Bindings and the
E2-only boundary are recorded in `artifacts/review/e2-trial-plan-review.md`.
Task 1 may begin; this gate claims no target-2.25 behavior.
The acceptance/routing candidate landed at `88951b20`, tree `b66170bb`;
its postcommit routing and route-readiness control passed 112 tests.

## Task 1: Close feasibility proofs 5 and 6 before production work

**Files:** create `tests/test_workflow_lisp_e2_trial_feasibility.py`; test-only
fixtures/helpers. No production or normative file changes.

- [x] RED/characterization: two complete E1 envelopes and one failed-arm
      evidence value
      enter a test-only opaque packet adapter, the existing adjudication scorer
      identity and strict-output primitives consume them, and trial-shaped
      score rows can remain candidate-provider-free. Characterize existing
      single-winner selection as inapplicable rather than reusing it.
- [x] Prove the packet's citable set includes the bounded workspace delta and
      excludes treatment, source, provider, completion-order, and sidecar
      facts.
- [x] Model the intended durable cell facts over one clean and one
      crash/resume execution; prove committed E1 effects are not re-spent,
      incomplete effects require fresh ordinals, derived ordering/median values
      are transient, and no memo key appears.
- [x] Characterize the current rejection of record/union elements below list
      containers and bind it as the exact target-2.25 prerequisite owned by
      Task 3 rather than weakening the typed outcome contract.
- [x] Collect and run the new module, obtain ordered Task-1 reviews, commit,
      and run its postcommit control. Any failed proof stops E2 before specs or
      production code and records `REVISE_E2` or `STOP_E2`.

Task 1 closed at exact reviewed commit
`456acc7a517fae2797b7e4f10bb73c1e11a6dd15`, tree
`7b7e53517e1c10bf9673337bff6bc811ad971004`. The six-test feasibility
module has SHA-256
`e5ac975de81c89264694e364871475ede4769084f54b25fdbd41cdcb0c0debe2`.
Ordered `E2_TASK1_SPEC_APPROVED` then `E2_TASK1_QUALITY_APPROVED` approved
those exact bytes. Its public E1 contracts prove closed packet projection,
score-ledger materialization, real attempt deletion/relaunch accounting,
committed-result reuse without re-spend, and the current nested-transport
rejection. The failed cell is deliberately failed-arm evidence rather than an
invented E1 failure envelope. The adjacent regression gate passed 165 tests;
the fresh postcommit module passed six tests. This is feasibility evidence
only: production trial packet/citation/aggregation remain Task 8, executable
trial/M2 parity remains Tasks 9–10, and Task 3 owns nested transport admission.

## Task 2: Land target-2.25 normative contracts first

**Files:** `specs/dsl.md`, `specs/providers.md`, `specs/state.md`,
`specs/observability.md`, `specs/versioning.md`, `specs/index.md`; create
`tests/test_workflow_lisp_e2_trial_contract.py`.

- [x] RED unsupported target 2.25, absent form/state/provider/observability
      rows, missing refusal codes, and any registry/handle wording presented as
      current authority.
- [x] Specify the exact syntax, bounds, result/outcome types, identity,
      trial/E1 settlement order, persistence/M2 rule, packet exclusions,
      evaluator/citation contract, budget behavior, SDK/CLI boundary, and
      non-security claim.
- [x] Add target 2.25 only; targets through 2.24 remain byte-compatible.
- [x] Run spec/version/routing selectors, ordered Task-2 reviews, commit, and
      postcommit controls.

Task 2 closed at exact reviewed commit
`6b43108742a4f6c36b698dc6385f0e8d94851d41`, tree
`0fa896c3f861e9497f327e09b27c3c3c5ea0a5b6`. Seven new contract tests
admit the ordinary target-2.25 frontend while target 2.26 remains fail-closed,
and the normative DSL/provider/state/observability/version/index surfaces now
bind the bounded static trial contract. The specs also close Task 3's generic
transport resource bounds at root depth 0, maximum depth 64, and 16,777,216
inclusive bytes of canonical compact sorted-key UTF-8 direct JSON. Initial
quality review found an ambiguity between excluding authored source identity
and admitting delta/artifact evidence; the correction excludes the authored
arm/workflow identity while explicitly retaining selected bounded changed
paths, diff content, and artifact relpaths. Ordered
`E2_TASK2_SPEC_APPROVED` then `E2_TASK2_QUALITY_APPROVED` approved the exact
corrected bytes. Fresh postcommit controls passed 81 normative/routing tests
and 149 target-gating tests (819 deselected). This gate adds no `trial` parser,
compiler node, or runtime behavior; Task 3 owns the selected generic transport
widening.

## Task 3: Admit bounded nested structural transport

**Files:** shared normalized type/transport/result-contract owners; create
`tests/test_workflow_lisp_nested_transportable_value.py`.

- [x] RED recursively transportable records and closed unions below
      list/optional/map containers for direct values, output bundles,
      persistence, resume, and strict JSON; retain rejection for any
      non-transportable leaf, non-string map key, invalid union tag, excessive
      nesting, or oversized value.
- [x] Implement one generic recursive predicate/encoder/validator shared by
      Workflow Lisp and runtime result contracts. Do not add a trial-name
      branch, envelope, nominal wrapper, or alternate wire format.
- [x] Gate the authored widening at target 2.25 while allowing compiler-owned
      target-2.25 trial contracts to use the same machinery; targets through
      2.24 retain their accepted source behavior.
- [x] Run native-return/Value/record/union/list/map/persistence/resume selectors,
      ordered Task-3 reviews, commit, and postcommit controls.

Task 3 closed at exact reviewed commit `43ae8d5c`, tree `3b81d218`,
from staged candidate SHA-256
`417d34dc1d797d19e85bff71952b4be028a2af4fd507fe2d965a3f49665b3a16`.
Ordered `E2_TASK3_SPEC_APPROVED` then `E2_TASK3_QUALITY_APPROVED` approved
those exact bytes. The generic target-2.25 widening covers direct values,
output bundles, run-ref persistence and capsules, imported/native child
boundaries, path-mode admission, and resume fingerprints while targets through
2.24 retain their prior defaults. Closed-union discriminant collisions,
invalid leaves/keys/tags, excessive depth/size, and unrepresentable Float
inputs fail deterministically. The fresh postcommit non-security control
passed 934 tests under 16-worker work-stealing. Task 4 may begin; no `trial`
form or production E2 trial behavior landed in this task.

## Task 4: Add the typed `trial` form and generated result contracts

**Files:** Workflow Lisp syntax/form/expression/type/effect owners; create
`orchestrator/workflow_lisp/typecheck_trial.py` and
`orchestrator/workflow_lisp/trial_result_contract.py`; create
`tests/test_workflow_lisp_trial.py`.

- [x] RED exact form parsing, closed keys, cardinality/budget/evaluation
      validation, same-value-type arms, every transportable `T`, and all
      malformed/refusal cases.
- [x] RED placement in ordinary bodies/branches/procedures and rejection in
      pure/loop/generated/nested-trial contexts.
- [x] Elaborate nested run-ref syntax into static configs without evaluating a
      first-class effect value; derive the exact monomorphic result/union/path
      contracts and `RunsTrialEffect`.
- [x] Run collect-only plus type/effect/form selectors, ordered Task-4 reviews,
      commit, and postcommit controls.

Task 4 closed at exact reviewed commit `ba430ed2`, tree `dd649f39`, from
staged candidate SHA-256
`caa496695fabb213c83bfe580b2bd11ee423ab199c1b06af16d5f3b385491bf6`.
The ordered specification stage passed
`E2_TASK4_SPEC_CONTRACT_APPROVED` and `E2_TASK4_SPEC_TYPE_APPROVED`; the
subsequent quality stage passed `E2_TASK4_QUALITY_PARSER_CONTRACT_APPROVED`
and `E2_TASK4_QUALITY_TYPE_INTEGRATION_APPROVED` on those exact bytes. The
fresh broad non-security Workflow Lisp gate passed 4,921 tests with one skip,
and the postcommit frontend control passed 518 tests. Task 5 may begin; Task 4
landed no `TRIAL` IR, lowering, persistence, checkpoint, or runtime producer.

## Task 5: Carry `TRIAL` through IR, lowering, persistence, and checkpoints

**Files:** shared surface/core/semantic/executable/runtime-plan/runtime-step,
persisted-surface, source-map, WCC and checkpoint owners; create narrow
`orchestrator/workflow_lisp/lowering/trial.py`; extend compiler artifacts.

- [x] RED exact cross-view identity and round trip for direct/record/union/
      optional/list/map/path/Value arms; changed arm/evaluation/budget inputs
      change only their owning identities.
- [x] Add one distinct `TRIAL` node/config and specialized result contract;
      preserve source spans and WCC/legacy compatibility for older targets.
- [x] Install `reuse_validated_trial_result` as a fail-closed checkpoint policy
      with no runtime producer yet.
- [x] Run compiler/IR/persisted/checkpoint selectors, ordered Task-5 reviews,
      commit, and postcommit controls.

Task 5 closed at exact reviewed commit `a7a8a083`, tree `c36e90f6`, from
staged candidate SHA-256
`bf56adc3c6f3d26d68e4cf1c76d9a8431a2fe162b8bc7bbc8ec57d522c819ee0`.
Ordered `E2_TASK5_SPEC_APPROVED` then `E2_TASK5_QUALITY_APPROVED` approved
those exact bytes after the generic union-projection validator was corrected
to bind projected discriminants to an exact required enum schema. The fresh
broad non-security Workflow Lisp gate passed 5,018 tests with one skip, and
the postcommit output-contract/trial-lowering control passed 73 tests. Task 6
may begin; no concurrent trial execution or Task-7 runtime producer exists
yet.

## Task 6: Split E1 lifecycle and implement trial identities and ledgers

**Files:** behavior-preserving E1 lifecycle extraction; create
`orchestrator/workflow/trial/{contracts,config,ledger}.py`; create
`tests/test_run_ref_lifecycle_driver.py` and
`tests/test_workflow_trial_ledger.py`.

- [x] RED canonical static/request/evaluation/budget identities, closed ledger
      rows, ordered cell domain, sealed opaque map, per-cell disjoint E1 roots,
      and tamper/extra/missing/ambiguity/escape failures.
- [x] RED clean/reuse, incomplete discard/fresh ordinal, pending-E1-commit
      reconciliation, and exact cross-cell rejection.
- [x] RED the E1 driver emits closed allocation/progress/prepared events,
      blocks each next stage until its caller acknowledges the preceding
      event, supports an exact arm deadline, and permits only the caller to
      mutate ledgers. A worker killed or timed out mid-child produces an
      incomplete attempt, never a synthetic settlement.
- [x] Add the minimum generic lifecycle/event and effect-instance-root seams;
      ordinary run-ref wraps them synchronously and keeps its exact existing
      paths, event order, settlement bytes, crash behavior, and public API.
- [x] Persist only the M2-compatible facts enumerated above; no derived result
      cache or memo key.
- [x] Run E1 regression plus lifecycle/ledger selectors, ordered Task-6
      reviews, commit,
      and postcommit controls.

Task 6 closed at exact reviewed commit `5d28619d`, tree `44eb381b`, from
staged candidate SHA-256
`9e4ed9fca5e536692e2017864350caccec8cbee737b3237161e525a378b3f24f`.
Ordered `E2_TASK6_SPEC_APPROVED` then `E2_TASK6_QUALITY_APPROVED` approved
those exact bytes after the ordinary `run-ref` wrapper was corrected to keep
its historical malformed-ledger error translation across the extracted
lifecycle preflights. The fresh lifecycle/ledger selector passed 28 tests,
the E1-plus-Task-6 regression selector passed 791 tests, and the broad
non-security Workflow Lisp gate passed 5,018 tests with one skip. Task 7 then
closed the bounded concurrent runtime; Task 8 is the selected successor.

## Task 7: Implement bounded concurrent arm execution

**Files:** create `orchestrator/workflow/trial/runtime.py` and scheduler helper;
create `tests/test_workflow_trial_runtime.py`.

- [x] RED randomized completion order still yields authored `(arm, rep)`
      result order; active children never exceed the cap; each cell has one
      exact E1 request.
- [x] RED failures are values and do not cancel siblings; arm/trial timeout
      settles pending cells while in-flight cells finish; all work is charged.
- [x] RED crashes at trial allocation, E1 preparation, cell settlement,
      and E1-finalize boundaries reconcile without duplicate child launch.
- [x] Implement workers that perform blocking E1 stages and submit immutable
      lifecycle events; one coordinator acknowledges stages and serializes
      every parent-owned ledger/settlement transition.
- [x] Run concurrency/property/crash/resume plus E1 controls, ordered Task-7
      reviews, commit, and postcommit controls.

Task 7 closed at exact reviewed commit `41e64d14`, tree `fb6082d9`, from
candidate-manifest SHA-256
`3e5bee691d762ce9915579ce522eedd17900d4fbf6c3b05c7fa2c1dc53baee64`
and staged-diff SHA-256
`3e8f5ff27347cd8170429ace7cb53b72e341856db32054da862e6df4d6740f5e`.
The ordered Task-7 specification approval preceded
`E2_TASK7_QUALITY_APPROVED`. Review-driven corrections made deadlines durable
across resume, required complete current E1 authority before failed-cell
reuse, validated existing state before mutation, replaced a timing-based
concurrency proof with an event dependency, and preflighted every mixed
bundle/path E1 request with per-arm capsule authority before creating trial
state. Fresh verification passed 29 Task-7 tests, 518 adjacent E1/trial tests,
the 900-test 16-worker E1/trial union, and 5,018 broad non-security Workflow
Lisp tests with one skip; the postcommit Task-7 control passed 29 tests. Task 8
may begin. The concurrent cell producer now exists, while evidence freeze,
checks, evaluator scoring, verdict production, and the public executor surface
remain absent until their owning tasks close.

## Task 8: Freeze evidence, run checks, blind packets, and adjudicate

**Files:** create
`orchestrator/workflow/trial/{checks,packets,evaluation,verdict}.py`; extract
only generic evaluator transport/scoring seams from adjudication as needed;
create `tests/test_workflow_trial_evaluation.py`.

- [ ] RED checks run after child completion and before scoring, in authority
      order, via literal argv/no shell, with complete bounded evidence.
- [ ] RED one mechanical evidence freeze precedes all evaluation calls; packet
      inclusion/exclusion, byte caps, opaque labels, sealed joins, and
      packet-only citations fail closed in both directions.
- [ ] RED strict invalid/then-valid evaluator behavior, scorer identity,
      attempt budgets, median combine, authored-order ties, failures-as-
      outcomes, success-rule disposition, and verdict artifact digest.
- [ ] RED evaluator-attempt exhaustion settles pending evaluations while
      in-flight evaluations finish and remain charged; crashes after evidence
      freeze, check settlement, and score settlement resume from the earliest
      validated phase without refreezing or rescoring committed work.
- [ ] Add trial packet/score schemas while reusing existing scorer/provider
      primitives; do not run adjudicated-provider candidate fan-out or source
      promotion.
- [ ] Run adjudication regression plus evaluation/blinding selectors, ordered
      Task-8 reviews, commit, and postcommit controls.

## Task 9: Integrate executor, state, observability, SDK, and CLI

**Files:** minimal executor/state/checkpoint/observability dispatch; create
`orchestrator/workflow/trial/sdk.py` and
`orchestrator/cli/commands/trial.py`; CLI registration; create
`tests/test_workflow_trial_integration.py` and `tests/test_cli_trial.py`.

- [ ] RED one outer atomic workflow settlement, validated completed reuse,
      derived-pure replay parity, current-only bounded status/report sidecar,
      and zero trial imports/work/sidecars for ordinary non-trial runs.
- [ ] RED a crash before outer-parent settlement reuses the validated terminal
      trial result and performs no child, check, or evaluator effect twice.
- [ ] RED SDK and CLI compile the same `.orc` entry through the ordinary full
      compiler, invoke the same runtime, return the same versioned summary,
      and reject raw configs, wrong targets, non-trial results, and privileged
      bypass attempts.
- [ ] Prove a generated exact-pin two-arm `.orc` what-if wrapper works through
      both surfaces and that no portable/dynamic-pin syntax was added.
- [ ] Run integration/CLI/ordinary-run selectors plus one deterministic
      orchestrator smoke, ordered Task-9 reviews, commit, and postcommit
      controls.

## Task 10: Prove the fixed study and close E2

**Files:** create `tests/e2e/test_e2e_workflow_lisp_trial.py`; exact
routing/status rows; this plan; `artifacts/review/e2-trial-final-review.md`.

- [ ] Run one deterministic two-arm E2E through the real compiler, parent
      executor, concurrent E1 children, checks, scorer, verdict, clean reuse,
      and interrupted/resumed reconciliation.
- [ ] Run one new platform-owned DIRECT/COORDINATOR/ORC fixed-study fixture
      with identical pins/inputs/budgets, opaque randomized presentation, and
      explicit treatment-specific failure accounting. Preserve authored output
      order only after unblinding.
- [ ] Run the treatment-labeling probe over evaluator-visible packet bytes;
      require chance-level labeling and exact exclusion diagnostics for every
      injected forbidden field.
- [ ] Run collect-only, all focused E2/E1/M2/adjudication/CLI selectors, one
      real subprocess smoke, `git diff --check`, and the broad 16-worker
      non-security suite in tmux.
- [ ] Obtain `E2_FINAL_SPEC_APPROVED`, then distinct
      `E2_FINAL_QUALITY_APPROVED`, against exact candidate bytes and evidence;
      commit the unchanged candidate and rerun focused/routing/readiness
      controls.
- [ ] Record exactly one exit: `PASS_E2`, `REVISE_E2`, or `STOP_E2`.
      `PASS_E2` makes the already selected E3 eligible only for review of this
      first fixed study and a separate E3 component plan; it does not select
      E2O, C1-C3, or any historical registry substrate.

## Final acceptance checklist

- [ ] Target 2.25 is normative, gated, and backward compatible.
- [ ] Static homogeneous arms and bounds compile into one distinct durable
      trial effect over exact E1 configs.
- [ ] Authored-order results, sibling-independent failure values, concurrency,
      deadlines, and evaluator-attempt budgets are deterministic and proven.
- [ ] Clean/resume parity reuses committed cells, reruns incomplete cells with
      fresh ordinals, launches no duplicate, and obeys M2 persistence.
- [ ] Evidence freezes before evaluation; packets are closed, bounded,
      treatment-blind, and citation-complete.
- [ ] Deterministic authority precedes judgment; scoring, repetition combine,
      success rule, unblinded join, and verdict artifact validate exactly.
- [ ] SDK, CLI, and non-evolution wrapper share the ordinary compiler/runtime
      path and expose no privileged backdoor.
- [ ] Feasibility proofs 5–6, fixed-study E2E, labeling probe, focused/broad
      gates, ordered reviews, and postcommit controls are fresh and bound.
- [ ] E3 remains study-review/plan-gated and all later/unselected surfaces stay
      truthfully absent.
