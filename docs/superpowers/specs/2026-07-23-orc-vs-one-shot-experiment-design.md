# `.orc` Versus One-Shot Experiment Program Design

## Metadata

- **Status:** approved experiment contract; implementation and execution are
  tracked by the linked plan
- **Kind:** experiment and operational architecture
- **Owner:** agent-orchestration maintainers
- **Domain owner for the PtychoPINN benchmark:** PtychoPINN maintainers
- **Reviewers:** independent execution-plan and cross-document consistency
  reviews approved on 2026-07-23; implementation reviews remain per task
- **Created:** 2026-07-23
- **Last material update:** 2026-07-23
- **Related documents:**
  [Workflow Demo Design](../../plans/2026-03-05-workflow-demo-design.md),
  [Workflow Demo Scaffold And Runbook](../../plans/2026-03-05-demo-scaffold-and-runbook.md),
  [Workflow Lisp Drafting Guide](../../lisp_workflow_drafting_guide.md),
  [Capability Status Matrix](../../capability_status_matrix.md),
  [Workflow Language Design Principles](../../design/workflow_language_design_principles.md),
  [Effectiveness Doubts Report](../../reports/2026-07-22-compelling-example-search-and-effectiveness-doubts.md),
  and the
  [PtychoPINN custom Torch architecture guide at `99efda1`](https://github.com/hoidn/PtychoPINN/blob/99efda11155119161d371d5d0e5ec7c33a720594/docs/workflows/custom_torch_architecture.md)
- **Implementation plan:**
  [`.orc` Versus One-Shot Experiment Program Implementation Plan](../plans/2026-07-23-orc-vs-one-shot-experiment.md)
- **Implementation target:** an evidence-grade paired-trial harness, one modern
  `.orc` repository-task workflow, frozen benchmark profiles, mixed hard/soft
  evaluation, downstream-consumer trials, and reproducible comparison reports
- **Current fallback:** the existing `orchestrator.demo` runner may still be
  used for informal serial demonstrations. It is not evidence for the claims
  governed by this design.

Purpose: define a reproducible class of experiments comparing a direct
one-provider invocation with a bounded `.orc` workflow on the same nontrivial
task, and define which conclusions those experiments may support.

Authority: this document owns the experiment contract. Existing runtime and
Workflow Lisp behavior remains owned by `specs/`, accepted design documents,
and current tests. This design does not authorize a Workflow Lisp language
change, a PtychoPINN product refactor, or automatic integration of benchmark
outputs.

Copy safety: workflow and schema fragments in this document are conceptual.
The implementation must use only surfaces marked implemented or library-
provided in the capability matrix and must compile through the ordinary
Workflow Lisp frontend.

## Summary

Adopt a staged paired-experiment program rather than a polished demonstration
or a single hidden-test contest. Each pair starts from one content-addressed,
history-free task snapshot and launches two opaque arms in parallel:

- `DIRECT`: exactly one provider invocation with normal repository tools; and
- `ORC`: one bounded, typed plan/review/implementation/check/review workflow.

The primary comparison estimates the effectiveness of the complete
orchestrated method against ordinary one-shot provider use. It does not by
itself isolate the `.orc` language from additional inference, decomposition,
review, or retry. A later same-topology non-`.orc` coordinator is required for
that narrower claim.

The benchmark portfolio deliberately combines:

1. apparatus calibration and controlled tasks with objective evaluators;
2. historical refactoring replays with known contracts but withheld future
   history;
3. a prospective PtychoPINN architecture-consequence task with no reference
   implementation; and
4. withheld downstream-consumer trials that test whether each proposed
   architecture actually makes later extensions easier.

Hidden checks are diagnostic evidence, not a universal oracle. Quality is
decided from frozen compatibility/invariant checks, blinded evidence-backed
soft review, symmetric exploratory probes, downstream consequences, and
process/cost evidence. The result may be `TIE` or `INDETERMINATE`.

## Context And Authority

### Existing comparison substrate

The March 2026 demo design established useful foundations:

- identical task injection;
- two isolated task workspaces;
- one direct provider arm and one workflow arm;
- external evaluation after both arms finish; and
- preservation of runner and evaluator artifacts.

The existing implementation is not sufficient for evidence-grade claims:

- `orchestrator.demo.provisioning` uses Git worktrees, leaving both arms tied to
  one object store and making historical-reference leakage possible;
- `orchestrator.demo.trial_runner` labels its mode `serial` and launches the
  direct arm before the workflow arm;
- its workflow was the now-retired YAML example
  `generic_task_plan_execute_review_loop.yaml`, not a current `.orc` workflow;
- evaluator selection depends on seed/task naming rather than a frozen
  experiment contract;
- workspace freeze records listings and Git status but not a complete
  content-addressed product snapshot;
- token/cost evidence is incomplete; and
- a task-specific hard evaluator can dominate the verdict even when its oracle
  is brittle.

The new program is a sibling to this substrate, not an implicit behavioral
change to the old demo. Reusable evaluator code may be adapted only behind
explicit versioned experiment contracts.

### Workflow Lisp surface

The first workflow must use currently implemented Workflow Lisp 2.15 surfaces:

- typed workflow/procedure inputs and return values;
- records, enums, unions, optionals, lists, maps, and paths;
- `provider-result` with typed structured returns;
- `:prompt-dependencies`;
- typed `command-result` through declared command boundaries, noting that the
  current surface is `Partial` and the experiment's fixed-check adapter must
  pass a certified-boundary feasibility gate;
- `let*`, `if`, `match`, and bounded `loop/recur`; and
- current source identity, result-bundle validation, and resume behavior.

The experiment must not rely on proposed DAG-level parallel steps, runtime
closures, dynamic procedure generation, arbitrary provider parameter maps, or
other designed-but-unimplemented language surfaces. Pair-level concurrency is
owned by the external experiment controller.

### PtychoPINN evidence

The custom-architecture guide makes the motivating prospective problem
concrete. A reloadable generator currently crosses public and Torch
configuration, translation/factory forwarding, a wrapper registry, a separate
core builder, output adaptation, sealed `ModelSpec`, artifact classification,
checkpoint reconstruction, workflow loading, inference, and multiple test
families.

Some of that complexity is essential:

- the scientific input/output contract;
- persisted graph-changing parameters;
- deterministic reconstruction and strict state loading;
- explicit supported artifact-era upgrades; and
- validation of data/model joins.

Some is change amplification:

- duplicated architecture catalogs;
- separate registry and construction authorities;
- architecture-family fields in one flat structural config;
- global schema churn for local topology additions;
- manual forwarding; and
- central output-shape inference.

The current clean benchmark seed is PtychoPINN commit
`c081b7b6cd160b3da7031ee325bbf0ade1025d7a`. The linked `99efda1` document is
evidence of the problem, but the current seed contains corrected `ModelSpec`
wording and the completed public object-policy migration. Neither commit is a
reference answer for the prospective task.

No forward custom-architecture redesign is currently selected by the
PtychoPINN refactoring roadmap. The prospective benchmark is therefore a new,
bounded experiment task. It is not an already-authorized continuation of that
roadmap.

### Candid effectiveness constraints

The effectiveness-doubts report is a required counterweight to showcase bias.
It records that real failures included:

- defects in guarantee/resume machinery;
- over-verification and authority ratchets;
- liveness stalls; and
- verification gaming.

The experiment must therefore preserve runtime failures, non-progress, check
changes, and reviewer disagreements as evidence. A successful compile or a
polished report is not effectiveness evidence by itself.

## Problem

The project lacks a defensible answer to four distinct questions:

1. Does a bounded orchestrated process produce a better repository change than
   an ordinary one-shot provider invocation?
2. If it does, which part helped: discovery, planning, review, correction,
   additional inference, or durable execution?
3. Is `.orc` an effective and usable representation/runtime for that process,
   compared with a small conventional coordinator implementing the same
   topology?
4. Do any observed advantages transfer from controlled replays to a genuinely
   prospective architecture decision whose correct implementation is unknown?

A single task and hidden score cannot answer all four. A workflow win may be
caused only by more calls. A direct win may reflect a workflow prompt defect.
A hidden evaluator may encode the withheld patch rather than the actual
contract. A runtime failure may reveal `.orc` substrate weakness without
saying anything about the underlying orchestration topology. Conversely, a
beautiful design proposal may be impractical when the next maintainer tries to
extend it.

The experiment needs separate estimands, frozen inputs, observable
consequences, and explicit claim boundaries.

## Goals And Non-Goals

### Goals

- Compare `DIRECT` and `ORC` from byte-identical task inputs in independent,
  history-free workspaces and separate environment instances.
- Launch paired arms concurrently within a bounded start-skew window.
- Keep provider family, model, reasoning effort, tools, visible files,
  resource allocation, and wall deadline equal where the methods permit.
- Define one-shot as one provider invocation while allowing normal inspection,
  editing, planning, and test execution inside that invocation.
- Bound workflow provider calls and revision counts without requiring a
  revision to occur.
- Freeze complete final product states before any evaluator writes or reviewer
  feedback reaches an arm.
- Pre-register task, seed, workflow, prompts, provider policy, checks,
  evaluators, metrics, invalid-trial rules, replicate count, and the separate
  quality, viability, efficiency, and consumer-consequence decision rules.
- Treat hard checks as falsifiers and contract evidence, not unquestionable
  patch-shaped truth.
- Make blinded soft evaluation evidence-backed, pairwise, and capable of
  abstaining.
- Empirically test prospective design consequences through withheld consumer
  changes.
- Record call count, elapsed time, available usage/cost data, failures,
  corrections, and workflow-authoring friction.
- Distinguish full-method effectiveness, topology value, prompt value,
  `.orc` representation/runtime value, and interruption/resume value.
- Produce actionable, scoped consequences for:
  - Workflow Lisp language/runtime;
  - `.orc` authoring ergonomics;
  - the repository-task workflow topology; and
  - individual prompts.
- Preserve enough structured evidence to rerun, audit, or invalidate a pair
  without trusting a prose report.

### Non-goals

- Proving that `.orc`, workflows, or one provider model are universally
  superior.
- Treating equal model names as equal inference expenditure.
- Hiding the workflow's extra provider calls or comparing quality without
  cost.
- Forcing either arm to create commits, plans, or visible revision churn as a
  success signal.
- Grading product patches by textual similarity to a withheld implementation.
- Allowing providers to replace the frozen check manifest in the first
  experiment.
- Building a universal arbitrary-command execution framework.
- Building a general PtychoPINN external plugin system.
- Migrating all existing PtychoPINN architectures in the prospective pilot.
- Automatically merging, cherry-picking, or promoting any benchmark output.
- Changing prompts or evaluator rules after observing confirmatory results and
  continuing to call the study one experiment.
- Reducing all evidence to one opaque scalar leaderboard.

## Decision

### 1. Use a staged benchmark program

The program has the following task classes:

| Stage | Task | Purpose | Included in effectiveness claim |
| --- | --- | --- | --- |
| `A0` | Linear-classifier port | Validate provisioning, launch, freeze, evaluation, and reporting | No |
| `A1` | nanoBragg entrypoint port | Controlled nontrivial discriminator with deterministic external behavior | Yes, controlled-task evidence |
| `R1` | PtychoPINN invocation-logging boundary replay | Medium realistic historical refactor | Yes, replay evidence |
| `R2` | PtychoPINN public object-policy 7D replay | Large cross-cutting historical refactor | Yes, replay evidence |
| `F1` | Prospective reloadable-generator extension-boundary task | Decisive forward architecture-consequence comparison | Yes, prospective evidence |
| `F2` | Withheld consumer changes against frozen `F1` outputs | Test actual future edit locality and schema evolution | Yes, consequence evidence |
| `X1` | Unrelated repository task | Test domain transfer | Required before a general claim |

`A0` is apparatus calibration and cannot be counted as a favorable result.
Historical replays are valuable controls but cannot establish forward design
quality alone. `F1` plus `F2` is the primary realistic benchmark.

The live PtychoPINN zero-consumer fork estate is a possible later ecological
replication. Its roadmap/status contradiction must first be resolved into one
new bounded task; the experiment must not infer mutation authority from stale
completion wording.

### 2. Separate estimands

| Experiment | Arms | Valid claim |
| --- | --- | --- |
| `E1` | Direct one-shot vs full `.orc` workflow | End-to-end method effectiveness |
| `E2` | Full workflow vs workflow without review/fix | Marginal value of review/correction topology |
| `E3` | `.orc` workflow vs same prompts/topology in a minimal conventional coordinator | Marginal `.orc` representation/runtime value |
| `E4` | Frozen workflow with prompt version A vs B | Prompt effect under that topology/task class |
| `E5` | Same comparison across task classes | Transfer and task-selection boundaries |
| `E6` | Uninterrupted workflow vs injected interruption/resume | Durable-execution behavior, not product-quality advantage |

Only `E3` supports a language-specific causal claim. `E1` is the required first
comparison because it answers the practical user question.

### 3. Use mixed evaluation

The decision combines four evidence lanes:

1. frozen hard compatibility and behavioral evidence;
2. blinded soft architectural/code review;
3. symmetric exploratory and downstream-consumer probes; and
4. process, cost, runtime, and ergonomics evidence unblinded last.

No lane may silently rewrite another. Reports are views over structured
results.

### 4. Build an evidence-grade sibling harness

Create a new `orchestrator.experiments` package and `scripts/experiments`
entrypoints. Do not retrofit evidence-grade semantics into
`orchestrator.demo` in place. The older demo remains usable for informal
examples while adapters can reuse stable evaluators after their inputs and
outputs are brought under the new contracts.

This choice duplicates a small amount of launch/provisioning plumbing at
first. It makes automatic migration of old demo commands harder, but avoids
claiming that a serial worktree/YAML demonstration already satisfies the new
experiment.

## Experiment Model

### Terminology

| Term | Meaning |
| --- | --- |
| **program** | One pre-registered set of hypotheses, task profiles, arm methods, evaluators, and replicate policy |
| **pair** | Two arms sharing one frozen trial contract and randomization event |
| **arm** | One opaque execution treatment assignment. `E1` uses `DIRECT` and `ORC`; other estimands use their own frozen treatment IDs |
| **replicate** | One independent pair for a task profile |
| **task profile** | Versioned task, seed, environment, check, evaluator, and product-scope contract |
| **experiment lock** | Content-addressed manifest freezing every pre-run authority |
| **arm workspace** | Physical per-arm working directory used as runtime/provider cwd; it may contain a runtime-only projection such as `.orchestrate` |
| **product projection** | Candidate-owned repository entries selected by the frozen include/exclude policy; runtime/control artifacts are absent even if physically nested under the arm workspace |
| **runtime projection** | Method-owned state, bundles, checkpoints, and logs excluded from the product projection and all product-review packages |
| **external control plane** | Workflow source, prompts, extern manifests, evaluators, controller records, and runtime installation outside the arm workspace |
| **product state** | Content-addressed candidate product projection at one point in time |
| **hard evaluator** | Deterministic or independently executable contract probe |
| **soft reviewer** | Blinded evaluator returning evidence-backed absolute and pairwise judgments |
| **consumer trial** | A fresh downstream change performed against one frozen candidate design |
| **invalid pair** | A pair that cannot estimate the intended contrast because a predeclared external/harness condition failed |
| **method failure** | A real failure of the direct method, workflow, `.orc` compiler/runtime, or task execution; it remains an outcome |

### Hypotheses

The program pre-registers directional hypotheses but does not predeclare a
winner:

- `H1`: the full workflow improves contract completeness and blinded product
  preference on nontrivial repository tasks.
- `H2`: any quality improvement remains visible after cost, elapsed time, and
  provider-call count are disclosed.
- `H3`: plan and implementation review loops explain a material share of any
  workflow advantage.
- `H4`: `.orc` expresses and operates the topology with reliability and
  evidence quality comparable to a minimal same-topology coordinator.
- `H5`: prospective candidate designs preferred by reviewers also reduce the
  effort and change amplification of withheld consumer tasks.

Failure to support a hypothesis is a valid result.

## Frozen Trial Contract

Task profiles are estimand-neutral: they own source/task/environment/check/
evaluator/product-scope facts and a stage ID. An experiment program owns one
`estimand_id`, exactly two treatment definitions, treatment-specific workflow
or coordinator assets, provider policy, a versioned replication-policy digest,
the controller-environment-lock digest, and the task-profile IDs on which that
contrast may run. Each task profile binds separately validated candidate and
evaluator environment-lock digests.

Every pilot, confirmatory, replication, and ablation series has one
`series_lock.v1`. It binds the program digest, profile strata, exact pair count
per stratum, randomization blocks, and—when applicable—the exact number of
two-step `F2` chains per candidate. A series lock is written before its first
result is visible and never extended. Additional evidence uses a new series ID
and lock.

An `E5` transfer program additionally binds one predeclared reference task
class and one transfer task class. When it reuses completed `E1` evidence
rather than rerunning the reference stratum, it binds the exact `E1` program,
series-lock, reference-profile, and terminal result-index digests plus a
treatment-equivalence manifest. That manifest proves both treatment asset
digests, provider/model/effort/tool policy, bounds, and evaluation policy are
identical across task classes. The reference series is selected by design
before the `X1` result is visible, not chosen from favorable outcomes.

An `E6` program binds an `interruption_control.v1` record, not an
interruption-specific task profile. The record identifies a deterministic
post-commit boundary signal, process-group termination policy, quiescence
proof, persisted run-ID authority, and exactly one ordinary same-ID resume
command. Missing or ambiguous boundary evidence, a changed run identity,
multiple resume attempts, `--force-restart`, or replay of an already committed
provider step fails closed. `E6` may support durability/recovery claims only,
never product-quality superiority.

Programs may share a `replication_policy.v1` digest only when that policy
explicitly enumerates every covered estimand, defines each estimand's
eligibility and claim level, requires a separate pre-result exact-N series lock
per program, and forbids cross-estimand pooling or denominator extension.

Before either arm launches, the controller writes and hashes one experiment
lock containing:

- program, task-profile, series-lock, pair, and replicate IDs and canonical
  digests;
- the series lock's exact profile stratum, scheduled replicate identity, and
  randomization block;
- opaque arm-label assignment;
- seed source repository, exact source commit, optional source subdirectory,
  archive digest, normalized file manifest digest, and initial Git tree digest;
- task brief and all shared visible instruction digests;
- workflow source/module/entrypoint digest;
- provider, prompt, and command-boundary manifest digests;
- every workflow prompt digest;
- direct prompt digest;
- visible check-manifest digest;
- hard evaluator and fixture digests;
- soft-review contract and reviewer-policy digest;
- withheld consumer-task digests;
- provider family, exact model, reasoning effort, CLI version, and allowed
  tool policy;
- environment-lock digest and environment-instance IDs;
- CPU, memory, accelerator, and concurrency allocation;
- arm and step deadlines;
- maximum arm start skew;
- workflow call and revision ceilings;
- product include/exclude rules;
- metrics, failure taxonomy, invalid-pair rules, replicate count,
  separately-locked replication rule, and decision procedure; and
- controller and report-schema versions.

Missing, unreadable, or mismatched inputs prevent launch. The controller never
repairs a lock from post-run observations.

## Snapshot And Environment Isolation

### Source snapshots

Every arm is materialized from archive bytes, not from a shared worktree.

For historical or prospective Git revisions:

1. resolve the exact source commit in a controller-only repository;
2. create a Git archive of that commit and optional subtree;
3. hash the archive and normalized extracted manifest;
4. extract the same archive independently into both arm roots;
5. initialize a fresh Git repository in each root;
6. commit the extracted snapshot as the arm's sole initial commit; and
7. remove remotes and exclude parent repositories, later refs, objects,
   patches, evaluators, and eventual maintainer solutions.

This is stronger than `git clone --no-hardlinks` for historical replay because
later commits would still be locally discoverable. Ordinary clones may be used
only for external sources whose complete history is part of the declared
visible task input.

### Environments

The two arms receive separate environment instances derived from the same
content-addressed lock. They must not share mutable caches, temp roots, test
caches, home directories, output roots, MLflow stores, or run state.

PtychoPINN trials run in independently materialized instances of a clean,
content-addressed environment image derived from the dependency intent of
`ptycho311`, not by cloning the mutable live environment. The image is rebuilt
from a frozen conda package lock plus a hash-pinned wheelhouse and excludes
editable installs and live-checkout `.pth` files. One fresh candidate instance
is materialized per arm, and hard evaluation uses a separately materialized
pristine evaluator instance. GPU allocation is either disabled for both arms or
assigned symmetrically. Parallel broad checks receive equal CPU and memory
allocation so resource contention does not become an unrecorded treatment.
Environment preflight rejects editable installs, nonempty `PYTHONPATH`, `.pth`
entries that resolve outside the frozen environment/candidate roots, or
resolved imports that point at the live parent PtychoPINN checkout. Each arm
environment resolves the candidate package from that arm's own immutable
starting tree and later mutable product files. The evaluator interpreter
resolves candidate code only from a verified extracted frozen product copy,
never from an arm or live checkout.

The orchestrator runtime used by the `ORC` arm is installed from a frozen
external experiment environment. It must not import the mutable target
workspace as its implementation source.

### Visible information

Both arms receive byte-identical:

- source snapshot;
- `AGENTS.md` and repository guidance;
- task brief;
- visible support files;
- public acceptance contract;
- visible fixed check manifest; and
- tool availability.

The `ORC` treatment additionally uses the workflow implementation and its
prompts, but external control-plane assets must not be placed in the arm
workspace or become ambient provider-readable task context. Before any other
apparatus is built, a deterministic feasibility spike must prove that:

- frozen workflow source, inactive prompts, extern manifests, evaluators, the
  peer arm, and the parent agent-orchestration checkout are outside the
  provider's filesystem/tool-visible root;
- the active role prompt can still be rendered and the provider can edit the
  candidate product files;
- generated result bundles and path-carried workflow records use either an
  external state root or a runtime-only workspace-relative area that is
  explicitly excluded from the product projection and review packages;
- each provider phase can see only its active result target and declared typed
  inputs from earlier phases—not inactive/prior raw bundles, raw prompt assets,
  or controller state—even if those runtime files are workspace-relative; and
- ordinary compile, run, bundle validation, checkpointing, and certified
  commands still work.

The provider necessarily receives its active role prompt and result contract;
that is treatment, not leakage. It must not gain ambient access to other
control assets. If current runtime or provider-tool path rules cannot preserve
this split, scored trials stop for a separately reviewed control-plane design
rather than staging treatment instructions into only one arm workspace.

Neither arm receives:

- hidden/held-out evaluators or fixtures;
- consumer-task text;
- later repository history;
- a reference patch;
- the other arm's filesystem, logs, or progress; or
- post-launch operator guidance.

The parent agent-orchestration checkout is not mounted as an ordinary readable
task path.

Historical replay also freezes provider source-retrieval policy. Network or
browser access capable of fetching repository history, remote Git operations,
and source-search tools are disabled for both historical arms while provider
API transport remains available. If that separation cannot be enforced and
probed, the replay is labeled observational/exploratory rather than
history-withheld causal evidence. Model pretraining or prior familiarity is an
irreducible limitation and is disclosed.

## Paired Launch Protocol

1. Validate the experiment lock and both extracted manifests.
2. Allocate fresh provider sessions and opaque arm labels.
3. Prepare both commands and wait at one launch barrier.
4. Start both arms within the predeclared skew bound.
5. Record process/session identity, monotonic start time, command, provider
   policy, and environment identity.
6. Allow no interactive steering after launch.
7. Treat the configured wall deadline as an arm outcome boundary.
8. On completion or timeout, establish process-tree quiescence.
9. Freeze and hash complete workspaces only after quiescence proof.
10. Build product-only snapshots using the predeclared include/exclude policy.
11. Create blinded product-review packages and seal the initial soft reviews
    before exposing held-out or hidden results.
12. Run hard evaluators against immutable extracted evaluation copies, verify
    those copies are unchanged, and adjudicate hard findings.
13. Run an integrated blinded assessment that can consider the sealed initial
    review plus hard evidence without rewriting the initial judgment.
14. Run consumer trials and symmetric exploratory probes.
15. Unblind method/cost data last.

### Direct arm

`DIRECT` is exactly one provider CLI invocation. The provider may inspect files,
form a private plan, edit, create tests, run checks, and iterate within that
invocation. The prompt must not prohibit normal competent behavior merely to
make the workflow look better.

The direct invocation cannot be resumed or supplemented after it terminates.
An arm-specific capacity or launch failure counts against end-to-end method
viability. Only a predeclared contrast-breaking harness fault or shared
apparatus/platform event that prevents the paired contrast from being valid may
invalidate the pair. A provider reasoning mistake, timeout, or broken patch is
an outcome.

### Workflow arm

`ORC` is exactly one workflow run using the frozen source and inputs. It may
make only the provider calls declared by the workflow and may use ordinary
workflow resume only for a predeclared interruption experiment or controller
recovery that preserves the exact program/input identity.

Compiler, lowering, runtime, typed-output, checkpoint, or workflow-routing
failures are method outcomes unless an independent harness audit proves that
the experiment controller supplied the wrong frozen input.

### Invalid pairs and reruns

A pair is invalid only for a predeclared contrast-breaking condition such as:

- initial archive or environment mismatch;
- controller-level launch-barrier/skew failure before both arm processes are
  started; method-specific startup latency after process creation is measured;
- wrong provider/model/effort/tool allocation;
- evaluator or reference material visible inside one arm;
- controller corruption or loss of a required frozen artifact; or
- an independently verified shared provider/platform outage or controller
  allocation failure that prevents both arms from entering the intended paired
  contrast.

Timeouts, implementation failures, `.orc` failures, bad plans, unnecessary
revisions, and failed checks are not invalidity conditions.

If a pair is invalid, discard neither arm selectively. Preserve the invalid
evidence, allocate a new pair ID, and rerun both arms. Invalid pairs never enter
the outcome denominator. Arm-specific capacity failures, timeouts,
compiler/runtime failures, and typed-output failures remain in the primary
end-to-end denominator. A separately labeled conditional-quality rerun may be
performed only under a new pair while retaining the original outcome.

### Process-tree quiescence

Each arm runs in its own process group or equivalent bounded process tree and
emits a controller-observed heartbeat. On timeout, the controller terminates
the group, escalates after a frozen grace period, reaps descendants, and proves
a bounded quiet window with repeated identical product manifests before
freezing.

A timeout remains a method outcome. If the controller cannot establish
quiescence, it records `product_freeze_trusted = false`; it must not publish a
trusted final-product digest or a fabricated quality comparison. Tests include
a hung provider and a tool subprocess that outlives its immediate parent.

## `.orc` Workflow Design

### Topology

The workflow is generic across repository tasks but intentionally fitted to
nontrivial design-and-implementation work:

```text
discover context (judgment-only; product digest enforced)
        |
draft implementation/design plan
        |
review plan P0
    | APPROVE ------------------------------+
    | BLOCKED -> BLOCKED                    |
    | REVISE                                |
    v                                       |
revise plan once                            |
    |                                       |
review plan P1                              |
    | REVISE -> EXHAUSTED                   |
    | BLOCKED -> BLOCKED                    |
    | APPROVE ------------------------------+
    v
implement
    | BLOCKED -> BLOCKED
    v
run frozen visible checks C0 on a disposable product extract
    |
review implementation I0
    | BLOCKED -> BLOCKED
    | required checks pass AND APPROVE -> COMPLETED using C0
    | required checks fail OR REVISE
    v
focused fix once
    |
run the same frozen visible checks C1 on a new disposable extract
    |
review implementation I1
    | BLOCKED -> BLOCKED
    | required checks pass AND APPROVE -> COMPLETED using C1
    | required checks fail OR REVISE -> EXHAUSTED
```

The workflow must not require a review to produce findings or a revision to
occur. `APPROVE` on the first review is legitimate. Maximum provider calls are
declared and reported. The unrolled maximum is nine provider calls when both
correction routes are exercised:

1. discovery;
2. plan;
3. plan review P0;
4. plan revision;
5. plan review P1;
6. implementation;
7. implementation review I0;
8. focused fix; and
9. implementation review I1.

The minimum successful route uses five. Deterministic digest/check adapters do
not consume provider calls. Required check failures are controller-owned
correction triggers even when a reviewer returns `APPROVE`; optional failures
remain evidence and do not route. `BLOCKED` means a provider has identified a
specific in-scope dependency or repository condition that the bounded method
cannot resolve and has returned its typed blocker evidence. `EXHAUSTED` means
the allowed correction was consumed and the second review still returns
`REVISE` or required checks still fail; it is not an external blocker and it is
not completion.

### Typed values

The workflow should define, at minimum:

- `ContextDiscovery`
  - flat typed summary fields; and
  - a must-exist path to a versioned, adapter-validated discovery manifest for
    repeated findings and paths.
- `ImplementationPlan`
  - flat typed decision/status fields; and
  - a must-exist path to the versioned plan containing intended changes,
    architecture decisions, invariants, compatibility obligations,
    verification strategy, and rejected shortcuts.
- `ReviewFindings`
  - schema version; and
  - a must-exist path to adapter-validated finding items with stable ID,
    severity, evidence path/symbol, rationale, and required correction.
- `PlanReviewDecision`
  - `APPROVE`;
  - `REVISE(findings)`; and
  - `BLOCKED(blocker evidence)`.
- `ImplementationAttempt`
  - `IMPLEMENTED` with changed product paths, checks requested, and unresolved
    limitations; or
  - `BLOCKED` with specific blocker evidence.
- `ImplementationReviewDecision`
  - `APPROVE`;
  - `REVISE(findings)`; and
  - `BLOCKED(blocker evidence)`.
- `ChecksResult`
  - schema/version and must-exist path to adapter-validated per-command
    results/log paths;
  - required/optional failure counts;
  - overall check status.
- `CorrectionTrigger`
  - required-check failure;
  - implementation-review findings; or
  - both.
- `WorkflowOutcome`
  - `COMPLETED`;
  - `BLOCKED`;
  - `EXHAUSTED`.

Provider results travel through native typed return bundles. Current transport
does not support records or unions nested inside collections, so repeated
structured items use typed must-exist path carriers plus a certified schema
adapter rather than unsupported `List[ReviewFinding]` or similar shapes.
Markdown plans and reports, if produced, are human views and do not become
routing authority.

The module declares `(:target-dsl "2.15")`. Every non-obvious provider result
and record/union payload field has meaningful typed `:description` guidance,
plus a type-correct `:format-hint` or `:example` where useful. Guidance is
prompt-only metadata and does not replace runtime validation.

`provider-result` does not itself enforce read-only filesystem access. Before
and immediately after context discovery, plan review, and implementation
review, a deterministic adapter computes the normalized product digest. Any
mutation during a judgment-only phase terminates the workflow as a method
failure before later product work. It does not become an invalid-pair excuse.
The provider bundle and repeated-item records created by those phases live in
the runtime-only area proven by the control-plane feasibility gate and are
excluded from the product digest.

### Check execution

The task profile supplies one immutable controller-owned check manifest and a
candidate-visible projection of it. The controller-owned content-addressed
manifest is authority; the visible projection is re-digested before every
invocation and cannot replace it.

A small declared command adapter, admitted only after certified-boundary
fixtures and a real compile/runtime smoke:

- accepts only structured `argv`, timeout, role, and required/optional fields;
- creates a disposable exact extract of the current product state and runs
  checks from that extract, so caches and mutating child processes cannot alter
  the candidate;
- captures stdout/stderr to logs;
- writes a typed `ChecksResult` to the runtime-bound bundle path;
- exits successfully when it has produced a valid result bundle, even when a
  represented check failed; and
- verifies the disposable product digest before and after checks and records
  any mutation as an adapter/evaluator defect.

The provider may add product tests, but it cannot replace the certified
manifest. Newly added tests may be run as additional evidence if the manifest
contains a predeclared discovery command such as a fixed pytest selector or
repository test collection.

### Prompt responsibilities

| Prompt | Responsibility | Forbidden |
| --- | --- | --- |
| context discovery | Map governing contracts, code boundaries, tests, and uncertainty without editing | Prescribing a solution or changing product files |
| plan | Choose a bounded architecture and verification strategy from discovered evidence | Treating document length or activity as quality |
| plan review | Find contract gaps, accidental scope, incompatibility, and unfalsifiable checks | Requiring revision for its own sake |
| plan revision | Correct only supported findings and preserve accepted decisions | Replanning unrelated work |
| implementation | Execute the approved plan and product checks | Editing frozen evaluator/check authorities |
| implementation review | Inspect task, plan, product diff, and check evidence | Reviewing workflow ceremony as product quality |
| focused fix | Correct accepted findings and rerun relevant checks | Broad refactoring or weakening checks |

No test may assert literal prompt wording. Tests target typed contracts,
dependency flow, routing, boundedness, and produced artifacts.

### Prospective-design fit

For the PtychoPINN prospective task, context discovery and planning must
distinguish irreducible lifecycle obligations from accidental coupling. The
prompts must not mention a descriptor class, nested tagged spec, registry
layout, or expected file count. Those are candidate hypotheses, not task facts.

## Benchmark Profiles

### `A0`: apparatus calibration

Use the existing linear-classifier port only to prove:

- archive provisioning;
- information equality;
- parallel launch;
- workspace freeze;
- evaluator isolation;
- blinded package generation; and
- report production.

Its results are marked `apparatus_only` and excluded from hypotheses.

### `A1`: controlled nanoBragg task

Use `examples/demo_task_nanobragg_entrypoint_port` with the current external
evaluator adapted to the new versioned contract. The task remains a controlled
coding discriminator. Evaluator behavior is graded rather than patch
similarity, and raw hidden cases remain subject to oracle-defect adjudication.

### `R1`: invocation-logging replay

- Source repository: PtychoPINN.
- Frozen base:
  `d3b012bf6d817fc02a03f31becf68b715d365dd9`.
- Withheld historical reference:
  `d45147bffac90b608fa0c39927ce36adf14c9c7f`.
- Task: remove the package runtime dependency on
  `scripts.studies.invocation_logging` while preserving invocation schemas,
  study-facing compatibility, and study-owned provenance.

The reference commit supplies evaluator ideas and later tests, never a patch
oracle.

### `R2`: object-policy replay

- Frozen base:
  `1a68784c8019eec97c3557ff95e509c24cdb2cfe`.
- Withheld historical reference:
  `78a7ca22e83d489d4544c79fda5a5e8b26f0e0ea`.
- Task: introduce canonical public object layout/canvas/weighting policy,
  preserve coherent legacy behavior, and evolve Torch artifact/model identity
  while preserving supported older decoding and TensorFlow behavior.

This is the large historical replay. Its detailed design tests execution and
compatibility reasoning more than requirements discovery.

### `F1`: prospective architecture-consequence task

- Frozen base:
  `c081b7b6cd160b3da7031ee325bbf0ade1025d7a`.
- Reference patch: none.
- Task class: design plus one vertical feasibility slice.

Shared neutral task brief:

> Diagnose the change amplification involved in adding a reloadable PyTorch CDI
> architecture. Design and implement the smallest coherent package-local
> extension boundary that reduces cross-cutting edits while preserving current
> construction, training, checkpoint and bundle reload, inference, public
> configuration, and supported artifact behavior. Demonstrate it with one
> migrated representative architecture and one small witness architecture.
> Document ownership, schema evolution, compatibility, rejected alternatives,
> and limitations.

Required product outputs:

- working product code and tests;
- an architecture decision document;
- a concise extension-author guide;
- a versioned extension-boundary/evidence manifest conforming to the frozen
  candidate-evidence schema; and
- the fixed solution-neutral lifecycle adapter required by the benchmark.

Before `F1` launches, the evaluator contract freezes:

- the candidate-evidence manifest schema, which separates candidate claims
  from evaluator-verified observations;
- one fixed product-relative lifecycle-adapter path and versioned JSON
  request/result schemas;
- exact supported artifact-era fixture paths and digests;
- evaluator-owned pristine tests and environment identity; and
- the commands used to exercise both the migrated representative architecture
  and the witness architecture.

The lifecycle adapter is a benchmark seam, not a prescribed internal product
architecture. Given evaluator-owned configuration and input fixtures, it must
exercise configure, public construction, forward computation, loss/backward,
one optimizer step or equivalently bounded short train, save, and
fresh-process reload/inference. The evaluator independently verifies artifacts,
state compatibility, outputs, and product behavior rather than trusting the
candidate manifest. The adapter's code and complexity remain part of the
candidate product diff, so it cannot hide an unusable extension boundary
without cost.

If a solution-neutral adapter and evaluator contract cannot be frozen before
candidate results exist, `F1` is exploratory and cannot support a confirmatory
prospective claim.

The benchmark does not require all fourteen current architectures to migrate.
It does require the candidate to state the migration boundary honestly.

One plausible product hypothesis is a package-local definition owning a stable
ID, architecture-local versioned parameters, validation, construction,
migration, and output adaptation, embedded as a tagged generator identity
inside shared `ModelSpec`. Reviewers may value the properties behind that
hypothesis, but neither task prompts nor evaluators may require its names,
classes, file layout, or exact representation.

### `F2`: downstream-consumer trials

Before `F1` launches, hash and withhold one two-step semantic chain:

1. add another small architecture whose configuration shape differs from the
   witness, then prove save/reload/inference; and
2. evolve that new architecture with an additional structural field while
   preserving reload of the earlier artifact.

For each candidate and chain replicate:

1. materialize the frozen `F1` candidate and give a fresh one-shot consumer
   session task 1;
2. freeze and hash the complete task-1 product;
3. materialize that exact task-1 output for a second fresh provider session;
4. give the second session task 2; and
5. freeze and evaluate both lineage-bound steps.

Each session receives exactly one anonymous product, that product's public
extension documentation, its current task, and identical
provider/model/effort/tools/deadline policy. It does not receive the competing
candidate, original method identity, another chain's output, or the first
consumer transcript. The series lock freezes the exact independent two-step
chain count per candidate before `F1` results; two is the initial planning
count, not a post-result minimum that may be extended. Balance candidate run
order, provider credential/time blocks, and opaque labels; there is no pairwise
presentation inside a consumer session.

Consumer sessions use the same one-shot provider method for every candidate.
They do not reuse the original `.orc` workflow, because `F2` is intended to
measure the product architecture and its documentation rather than repeat the
original orchestration treatment. The task-2 record binds the exact candidate,
task-1 archive, task-1 product digest, and fresh session identity.

## Evaluation

Evaluation is chronological even though the contracts below are grouped by
evidence kind:

1. seal initial soft reviews without held-out results;
2. run hard evaluators on immutable copies and adjudicate their findings;
3. perform an integrated review that references, but cannot rewrite, the
   initial soft judgment;
4. run admitted probes and consumer trials; and
5. unblind method/process evidence.

### 1. Initial blinded soft review

At least two independent reviewers receive:

- the shared task and public acceptance contract;
- base-to-final product diff;
- relevant final product files and candidate-authored design/docs; and
- no held-out/hidden results, arm identity, workflow, prompt, plan/review
  transcript, provider-call count, elapsed time, or cost.

One review perspective must cover PtychoPINN scientific/application semantics.
One must cover API, persistence, migration, and maintainability. If their
pairwise outcomes disagree materially, a third reviewer adjudicates.
Every reviewer uses a fresh independent session and cannot see another
reviewer's record before both individual records are sealed. A disagreement
produces a distinct typed initial-review-adjudication record; it never edits or
replaces either individual review.

Each reviewer first evaluates each candidate independently, then returns:

- dimension-level assessment;
- evidence-cited findings;
- confidence per finding;
- critical-contract concerns;
- pairwise outcome `A`, `B`, `TIE`, or `INDETERMINATE`; and
- rationale distinguishing observed facts from inference.

Required soft dimensions:

- semantic and scientific correctness;
- task-intent completeness;
- diagnosis of the current design smell;
- ownership and boundary coherence;
- artifact/reload and migration reasoning;
- maintainability and simplicity;
- extension edit locality;
- test and evidence quality;
- scope discipline;
- failure diagnostics;
- documentation sufficiency; and
- likely latent defects.

Reviewer order is counterbalanced. A reviewer may abstain. The controller does
not convert prose sentiment into routing state; typed reviewer records are
authority.

### 2. Hard evidence

Hard evaluators run only after the initial soft records are sealed. They operate
on extracted immutable evaluation copies, produce per-claim records rather than
one pass bit, and must leave each evaluated copy byte-identical.

For `F1`, the frozen hard contract includes:

- existing declared focused suites;
- candidate evidence-manifest and lifecycle-adapter schema conformance;
- unchanged construction/state signatures for existing built-ins;
- supported frozen model/checkpoint/bundle fixtures still decoding and
  strict-loading;
- both nominated architectures completing the evaluator-owned
  construct/forward/backward/optimizer-step/save/fresh-process-reload/inference
  lifecycle;
- the witness architecture preserving all structural values across save and
  fresh-process reload;
- missing, extra, unknown, or unsupported structural identity failing before a
  module is returned;
- declared structural fields changing frozen artifact/content identity
  deterministically;
- the candidate-declared supported public construction route and persisted
  rebuild resolving the same architecture implementation; and
- existing physics, loss, scaling, and data semantics remaining outside the
  extension's ownership.

These assertions are behavior-level. They must not require a particular
descriptor name, path layout, or payload nesting unless the candidate itself
declares that as public contract.

Every hard failure receives one disposition:

- `PRODUCT_DEFECT`;
- `ORACLE_DEFECT`;
- `SPEC_AMBIGUITY`;
- `INFRASTRUCTURE`; or
- `UNRESOLVED`.

Only a confirmed violation of a frozen non-negotiable contract is blocking.
Oracle-invalid checks remain disclosed but do not count against a candidate.
Disposition is made blind to arm method where possible and before cost/process
unblinding. An integrated reviewer then receives the immutable initial soft
individual records, any initial-review adjudication, and normalized hard
evidence, then records whether the new evidence confirms, weakens, or overturns
the pairwise assessment. The integrated reviewer uses a fresh session and
emits a distinct typed record. No initial record is edited in place.

### 3. Symmetric exploratory probes

Reviewers may propose additional behavioral probes. An independent adjudicator
accepts a probe only when it:

- tests the shared task contract rather than one candidate's private shape;
- can be run symmetrically;
- was proposed before arm/cost unblinding;
- cannot mutate the frozen candidates; and
- records its own source and result digest.

Exploratory probes are labeled and cannot silently become confirmatory hidden
tests.

### 4. Consumer consequences

Consumer-trial evaluation records:

- candidate-to-task-1-to-task-2 archive and session lineage;
- task completion and confirmed defects;
- elapsed time and provider usage;
- files and architectural layers touched;
- edits outside the candidate-declared extension boundary;
- shared/global schema churn;
- compatibility code added;
- documentation questions/blockers;
- lifecycle-check results; and
- soft reviewer judgment of whether low apparent churn is genuine.

This evidence is primary for the claim that an architecture improves future
extension ergonomics. A concise original patch does not win if downstream
consumers need hidden cross-cutting edits.

### 5. Process, cost, and runtime evidence

After quality judgments are sealed, reveal:

- provider calls by role and outcome;
- available input/output/cache token counts;
- usage source and completeness;
- elapsed arm and per-step time;
- configured and observed timeouts;
- visible check executions;
- plan revisions and implementation fixes;
- compiler/runtime/resume failures;
- non-progress or no-op revisions;
- authored `.orc` source size and support-manifest count; and
- experiment-specific adapter/glue burden.

If a provider does not expose reliable usage, record `unknown` with the raw
source retained. Never estimate missing token counts as measured fact.

## Comparison And Decision Procedure

Do not calculate one mandatory weighted score. For each pair report:

- hard-contract result vector;
- hidden/held-out behavioral score where applicable;
- soft-review absolute assessments;
- pairwise preference;
- consumer-trial outcomes;
- elapsed/call/usage/cost ratios;
- method/runtime failures; and
- Pareto dominance or tradeoff.

Across replicates report:

- win/tie/indeterminate counts;
- paired pass-rate and score deltas;
- reviewer agreement;
- consumer completion/defect rates;
- median and distribution of cost/time ratios; and
- failure-class frequencies.

A result may support conclusions such as:

| Observation | Supported consequence |
| --- | --- |
| `ORC` improves quality with acceptable cost and consumer consequences | Full method is viable for this task class |
| Quality ties while `ORC` costs materially more | Reduce or conditionally skip phases |
| Review/fix ablation removes the advantage | Review topology is causally useful |
| Same-topology coordinator matches quality with less friction | Orchestration helps; `.orc` ergonomics/runtime need work |
| `.orc` matches coordinator with better evidence/resume behavior | Language/runtime is a viable representation for this topology |
| Workflow loses through needless findings or churn | Revise review prompts/decision contract |
| Workflow loses through compiler/runtime failure | Fix substrate, preserve frozen trial, then rerun under a new program version |
| Hard test and blinded review disagree | Investigate oracle validity and contract ambiguity; do not force a winner |
| Prospective design looks good but consumer trials struggle | Architecture lacks demonstrated extension ergonomics |
| Results reverse across tasks | Define task-selection criteria; do not claim a universal default |

### Typed decision vector

The experiment has no single `winner` field. The frozen decision procedure
emits a vector of independently typed relations:

- `product_quality_outcome = A | B | TIE | INDETERMINATE`;
- `per_treatment_viability: Map[treatment_id, VIABLE | NONVIABLE | UNKNOWN]`;
- `viability_relation = A | B | BOTH | NEITHER | INDETERMINATE`;
- `efficiency_relation = A_DOMINATES | B_DOMINATES | TRADEOFF |
  EQUAL_WITHIN_FROZEN_BOUNDS | UNKNOWN`;
- `consumer_consequence_outcome = A | B | TIE | INDETERMINATE`; and
- per-hypothesis `SUPPORTED | NOT_SUPPORTED | INDETERMINATE`.

The experiment lock freezes two treatment IDs, their anonymous `A`/`B` mapping,
critical-contract severity, equivalence bounds, and review/adjudication rules.
It does not freeze an expected method winner. After unblinding, reports may
render `A`/`B` as `DIRECT`/`ORC`, coordinator, prompt variant, review topology,
or resume treatment according to the program's `estimand_id`.

Decision constraints:

- `product_quality_outcome` comes from the sealed integrated blinded review,
  constrained by confirmed hard-product defects and evidence completeness. A
  candidate with an unadjudicated hard failure cannot be declared the winner.
- If one arm has no reproducible trusted product freeze, pairwise product
  quality is `INDETERMINATE`. The absence still affects method viability.
- A confirmed critical frozen-contract defect prevents that candidate from
  winning product quality unless both candidates have comparable critical
  defects, in which case the integrated adjudicator may return only `TIE` or
  `INDETERMINATE`.
- per-treatment viability and `viability_relation` are computed from whether
  each complete treatment reached its frozen terminal/evidence obligations. An
  arm-specific provider,
  compiler, runtime, typed-output, timeout, or workflow failure may make that
  method non-viable even when product quality is indeterminate.
- `efficiency_relation` is Pareto-style over frozen quality-eligible outcomes
  and separately reported calls, observed usage, cost, and elapsed time. Missing
  reliable usage yields `UNKNOWN` for usage/cost claims rather than an estimate.
- `consumer_consequence_outcome` is based only on the balanced lineage-bound
  `F2` chains and their blinded consequence reviews. It cannot be inferred from
  `F1` patch size or initial reviewer preference.
- The report renders the whole vector. It never converts the vector into a
  weighted scalar or silently uses method viability to invent a product-quality
  preference.

### Replication levels

- `pilot`: one valid pair; debugging/directional evidence only.
- `exploratory`: at least three valid pairs; no confirmatory causal claim.
- `confirmatory`: one fixed, pre-registered pair count selected from pilot
  variance, discordance, cost, and the intended inference before confirmatory
  results are visible. Ten pairs is the initial planning assumption, not an
  outcome-dependent stopping rule.

Calibration and invalid pairs do not enter the valid-pair count. If the fixed
confirmatory series is underpowered or non-discriminating, close it with that
result. Any additional sample is a separately locked replication series, not
an extension of the original denominator.

## Failure Taxonomy

Every non-success or material defect receives one primary and optional
secondary class:

- `provider_judgment`;
- `task_decomposition`;
- `workflow_topology`;
- `prompt_contract`;
- `orc_authoring_ergonomics`;
- `orc_capability_gap`;
- `orc_compiler`;
- `orc_runtime`;
- `resume_or_durability`;
- `check_adapter`;
- `harness`;
- `evaluator_or_oracle`;
- `task_or_specification`;
- `environment`;
- `external_provider_capacity`;
- `non_progress`;
- `verification_weakening`; or
- `unresolved`.

Classification cites concrete evidence and is independent of winner selection.
The experiment report must disclose machinery failures even when the final
product happens to pass.

## Consequence Synthesis

### Workflow changes

A proposed topology or prompt change must cite:

- observed failure/benefit;
- task and pair IDs;
- affected phase;
- expected behavioral mechanism;
- regression risk;
- a scenario where the change could add overhead; and
- a new frozen experiment version.

Do not patch prompts between confirmatory replicates. Prompt variants are a new
`E4` comparison.

### Language and ergonomics changes

A Workflow Lisp change request must distinguish:

- an expressiveness gap;
- authoring ceremony;
- missing tooling/diagnostics;
- runtime reliability;
- missing metering/observability; and
- experiment-harness needs that do not belong in the language.

It must include frequency, current workaround, measured burden, and whether the
same-topology coordinator avoids the problem. One awkward workflow is not
enough to justify a new language primitive.

Likely pressure points to measure, not prejudge, include:

- repeated provider dispatch blocks;
- verbose nominal result types;
- provider-context transfer across fresh calls;
- command-boundary and extern-manifest ceremony;
- lack of aggregate provider usage;
- debugging typed bundle failures;
- bounded review-loop authoring; and
- absence of general parallel workflow branches.

### Product consequences

PtychoPINN benchmark outputs remain experiment candidates. No candidate changes
the canonical PtychoPINN repository during blinded evaluation. After
unblinding, a maintainer may separately review a candidate or synthesized
design for normal roadmap selection. Any later maintainer implementation is a
third candidate, not an oracle retroactively defining the experiment winner.

## Structured Artifacts

Recommended experiment root:

```text
<experiment-root>/
  contract/
    program.json
    task-profile.json
    experiment-lock.json
    content-manifest.json
  pair/
    assignment.json
    runner-state.json
    events.jsonl
  arms/
    A/
      workspace/
      process/
      freeze/
      product/
    B/
      workspace/
      process/
      freeze/
      product/
  evaluation/
    hard/
    soft/
    probes/
    consumers/
  reports/
    comparison.json
    comparison.md
```

Required structured schemas:

- `experiment_program.v1`;
- `task_profile.v1`;
- `replication_policy.v1`;
- `environment_lock.v1`;
- `series_lock.v1`;
- `experiment_lock.v1`;
- `arm_visible_manifest.v1`;
- `arm_assignment.v1`;
- `arm_execution.v1`;
- `environment_import_proof.v1`;
- `control_plane_visibility_proof.v1`;
- `visible_check_manifest.v1`;
- `checks_result.v1`;
- `context_discovery_detail.v1`;
- `implementation_plan_detail.v1`;
- `review_findings.v1`;
- `usage.v1`;
- `workspace_freeze.v1`;
- `hard_evaluation.v1`;
- `hard_finding_disposition.v1`;
- `initial_soft_review.v1`;
- `initial_review_adjudication.v1`;
- `integrated_review.v1`;
- `exploratory_probe.v1`;
- `failure_attribution.v1`;
- `pair_deviation_or_invalidation.v1`;
- `candidate_extension_evidence.v1`;
- `lifecycle_probe_request.v1`;
- `lifecycle_probe_result.v1`;
- `consumer_trial.v1`;
- `consumer_chain_lineage.v1`;
- `topology_equivalence.v1`;
- `interruption_control.v1`;
- `pair_comparison.v1`; and
- `program_synthesis.v1`.

Each schema carries its version and applicable digest bindings. Markdown is a
projection. Raw logs and provider JSONL are evidence; they do not override
validated structured records.

`experiment_lock.v1` and `arm_assignment.v1` are controller-only. Each arm
receives a redacted `arm_visible_manifest.v1` containing only its shared visible
inputs and opaque arm identity. Reviewer packages receive a separate
digest-bound projection. Neither projection can reveal the treatment mapping or
controller paths.

`workspace_freeze.v1` binds both:

- an immutable full-byte workspace archive plus a normalized entry manifest
  covering regular files, directories, and symbolic-link text; and
- a normalized product-only archive/digest produced with the task profile's
  predeclared exclusions.

Evaluators and reviewers never operate on the mutable arm workspace. Hard
evaluators run against fresh extracts, and the controller verifies the
evaluation copy's product digest before and after every evaluator.

## Compatibility And Migration

- Existing `orchestrator.demo` commands and tests remain unchanged initially.
- Existing hidden evaluators may be wrapped only after their fixture and result
  contracts are explicitly versioned.
- The old generic YAML task loop remains a historical comparison artifact; new
  experiment authoring uses `.orc`.
- The new workflow does not become a production stdlib workflow merely because
  it succeeds in the experiment.
- No `.orc` language/runtime change is a prerequisite for the first pilot
  unless compile/smoke evidence proves the accepted design cannot be expressed
  using current implemented surfaces.
- Benchmark profiles pin external source commits and do not track moving
  branches.

## Invariants And Failure Modes

### Invariants

- Both arms in one pair derive from identical archive bytes and shared visible
  inputs.
- Neither arm can read later history, the other arm, evaluators, consumer
  tasks, or reference patches through filesystem tools.
- Historical pairs counted as history-withheld causal evidence additionally
  enforce the frozen source-retrieval/network policy. If provider transport
  cannot be separated from repository retrieval, those pairs are labeled
  observational/exploratory and excluded from causal or confirmatory
  history-withheld claims; the core filesystem invariant is never downgraded.
- Candidate-facing repository/domain tools are equal. The `.orc` arm alone has
  treatment control machinery, but inactive control assets are not tool-visible.
- Pair-level execution is concurrent; workflow-internal execution remains
  whatever the frozen `.orc` defines.
- The direct arm is one provider invocation.
- The workflow arm cannot exceed its declared provider-call and revision
  bounds.
- Check and evaluator authorities cannot be edited by either arm.
- Complete workspace/product freezes precede evaluation.
- A trusted freeze requires terminated/reaped descendants and a stable
  quiet-window manifest.
- Reviewers remain blind until their typed verdicts are sealed.
- Individual reviewers use fresh sessions and cannot see peer reviews before
  sealing.
- Cost/process evidence never influences blinded quality review.
- A method failure remains an outcome unless a predeclared invalid-pair rule
  applies.
- Only behavior/contract evidence, not reference-patch resemblance, can
  disqualify a prospective candidate.
- No benchmark output mutates a canonical source repository automatically.

### Expected failures

| Failure | Required behavior |
| --- | --- |
| Archive or manifest mismatch | Refuse pair launch |
| Controller fails to start both arm processes within launch-skew bound | Mark pair invalid and preserve evidence |
| One method starts slowly after process creation | Measure as method latency; do not invalidate |
| Arm-specific provider capacity failure | Count end-to-end method failure; preserve optional conditional-quality rerun separately |
| Shared provider/platform outage before coherent pair start | Apply frozen invalidity rule to whole pair |
| Arm timeout after useful work | Freeze partial state and count method outcome |
| Arm descendants cannot be quiesced | Count method/controller evidence, mark product freeze untrusted, and make product quality indeterminate |
| Typed provider bundle invalid | Preserve provider/runtime evidence and count workflow failure |
| Check command fails | Represent failure in `ChecksResult`; continue only as workflow contract permits |
| Evaluator output invalid | Do not invent a score; classify evaluator/harness failure |
| Hard oracle disputed | Blind disposition as product/oracle/ambiguity/unresolved |
| Reviewer disagreement | Invoke third blinded adjudicator or return `INDETERMINATE` |
| Consumer cannot understand candidate seam | Record documentation/ergonomics failure; do not coach |
| Usage unavailable | Record `unknown` and retain raw source |
| Runtime crash with compatible completed boundary | Use ordinary exact-identity resume only when the program pre-authorizes it |
| Source/prompt/evaluator changes mid-study | Close current program version and create a new one |

## Declarative Acceptance Scenarios

### Scenario A: identical history-free pair

- Initial state: one Git source commit with later commits present in the
  controller repository.
- Entry point: provision one pair from the task profile.
- Expected:
  - both arm initial manifests and Git trees match;
  - each fresh repository contains only the seeded initial commit;
  - no remote or later object/reference is discoverable;
  - experiment-lock bindings match.
- Forbidden: Git worktrees, shared object databases, copied dirty/untracked
  source, or post-provision task edits.

### Scenario B: parallel direct and `.orc` execution

- Initial state: valid pair, fixture provider commands, fixed deadlines.
- Entry point: paired runner.
- Expected:
  - both commands wait at a launch barrier;
  - starts fall within the skew bound;
  - stdout/stderr and process metadata remain arm-scoped;
  - one arm's failure does not terminate or mutate the other;
  - both freeze manifests are produced.

### Scenario C: approval without ceremonial revision

- Initial state: plan review returns `APPROVE`; implementation review returns
  `APPROVE`; fixed checks pass.
- Entry point: `.orc` workflow.
- Expected: no revision/fix provider is called and outcome is `COMPLETED`.
- Forbidden: manufacturing findings or revision artifacts to demonstrate a
  loop.

### Scenario D: one bounded correction

- Initial state: plan or implementation review returns structured findings.
- Entry point: `.orc` workflow.
- Expected:
  - exactly one applicable correction call;
  - corrected typed value flows to the next phase;
  - checks rerun after an implementation fix;
  - repeated findings terminate as `EXHAUSTED` rather than looping silently.

### Scenario E: brittle hidden check

- Initial state: one hidden check fails a candidate, but blind inspection finds
  that the candidate satisfies the frozen public contract and the check assumes
  the withheld implementation's private shape.
- Entry point: hard-finding adjudication.
- Expected: disposition `ORACLE_DEFECT`, failure remains disclosed, candidate
  is not disqualified by that check.
- Forbidden: deleting the result or silently counting it as product failure.

### Scenario F: prospective consumer consequence

- Initial state: two frozen anonymous `F1` candidates and one withheld
  two-step extension chain.
- Entry point: balanced consumer runner.
- Expected:
  - fresh consumers receive only one candidate and its docs;
  - task 1 is frozen and task 2 starts from that exact lineage-bound product;
  - lifecycle checks run symmetrically;
  - completion, defects, layers touched, schema churn, and effort are recorded;
  - reviewers can distinguish true locality from hidden central glue.

### Scenario G: same-topology control

- Initial state: a frozen `topology_equivalence.v1` manifest proving equal
  fully rendered role prompts—including generated result-contract suffixes—
  call ordering, logical result schemas and validation, bounds, provider
  commands/profile/model/effort/session freshness/timeouts, task inputs, and
  check adapter.
- Entry point: run `.orc` and conventional-coordinator arms.
- Expected: differences in product/evidence/runtime burden can support an
  `.orc`-specific claim.
- Forbidden: changing prompts, call count, or review policy in only one arm.

If byte-level rendered prompts or any other treatment element cannot be shown
equivalent, the result is labeled a coordinator-package comparison and cannot
support a marginal `.orc` language/runtime claim.

### Scenario H: cross-task transfer

- Initial state: terminal, digest-bound `F1` E1 evidence and a pre-result `X1`
  series lock.
- Entry point: validate the `E5` cross-program reference and launch `X1`.
- Expected: synthesis compares the same two treatment definitions and provider
  policy across the predeclared `F1` and `X1` task classes.
- Forbidden: selecting a different E1 series after seeing `X1`, changing a
  treatment asset, or calling X1-only evidence a transfer result.

### Scenario I: injected same-ID resume

- Initial state: two byte-identical `E6` workflow arms; the assigned
  interruption arm's fixture emits a unique committed boundary containing its
  run ID and checkpoint digest.
- Entry point: both launch through the pair barrier; the interruption
  controller observes that arm's event, terminates and quiesces only its
  process group, then invokes one ordinary same-ID resume while the control arm
  remains uninterrupted.
- Expected: the resumed run reaches its terminal state without replaying the
  committed provider step, and the typed control record preserves all
  identities and argv.
- Forbidden: interruption before a validated boundary, a fresh run, changed
  state root, `--force-restart`, ambiguous boundary selection, or a second
  resume attempt.

## Verification Strategy

### Contract and unit verification

- Schema parsing, canonical serialization, digest binding, missing-field,
  unknown-field, and tamper tests.
- Archive extraction and normalized-manifest tests.
- No-later-history and no-shared-object-store tests.
- Historical source-fetch/browser/network-policy probes that either prove
  causal eligibility or emit the explicit observational-only classification.
- Product include/exclude and complete freeze-digest tests.
- Launch barrier, start skew, timeout, descendant termination, quiet-window,
  invalid-pair, and whole-pair rerun tests.
- Usage records distinguish observed values from `unknown`.
- Reviewer blinding and unblinding-order tests.
- Hard-finding disposition and `INDETERMINATE` handling tests.
- Consumer allocation and balance tests.

### Workflow verification

- `pytest --collect-only` for every new/renamed workflow test module.
- Workflow Lisp compile through the public CLI with frozen extern manifests.
- Shared validation and `run --dry-run`.
- Fixture-provider end-to-end run for:
  - immediate approval;
  - one plan revision;
  - one implementation fix;
  - mutation during each judgment-only phase;
  - invalid typed provider output;
  - check failure; and
  - exhaustion.
- Control-plane smoke proving workflow source, prompts, extern manifests,
  runtime installation, and orchestrator state remain outside the candidate
  product projection while provider tools operate on the arm workspace/product
  files; negative
  probes cover inactive prompts, evaluator assets, the peer arm, and the parent
  checkout.
- Certified command-boundary fixtures prove both passed and failed check
  results produce valid typed bundles without using stdout as authority.
- Mutating-check and outliving-child fixtures prove checks run on disposable
  extracts and cannot change the candidate product.
- One real-provider apparatus smoke after deterministic tests pass.

Tests assert behavior, types, routing, artifact lineage, and bounded calls, not
literal prompt prose.

### Evaluation verification

- Hard evaluators run from outside candidate workspaces.
- The prospective lifecycle adapter and candidate-evidence manifest validate
  against their pre-frozen solution-neutral schemas.
- Candidate order and labels are blinded/counterbalanced.
- Test fixtures prove a patch-shaped hidden check can be classified as an
  oracle defect.
- Soft-review schemas require evidence and confidence.
- Comparison reports are deterministically regenerated from structured
  records.
- A simulation report covers:
  - the target prospective architecture task;
  - a hard case where one revision is insufficient; and
  - a small task where workflow overhead is likely to dominate.
- Same-topology control tests compare byte-identical rendered provider prompts,
  generated result-contract suffixes, logical schemas, bounds, provider policy,
  and check adapters before permitting an `.orc`-specific claim.

### Broad verification

After focused selectors pass, run affected broad modules and then the repository
suite with:

```bash
pytest -q -n 16 --dist=worksteal
```

Keep broad/slow runs in tmux. PtychoPINN integration checks and any real
PtychoPINN workflow execution run in `ptycho311`.

## Success Criteria

Implementation is accepted when:

- every frozen contract has a versioned schema and tamper coverage;
- two independent archive-seeded arms begin byte-identically without later
  history;
- candidate package imports resolve inside each independent arm environment,
  never through an editable/live parent checkout;
- the controller launches them concurrently and freezes both completely;
- the direct launcher makes exactly one provider invocation;
- the `.orc` workflow compiles, validates, dry-runs, and passes fixture-provider
  routing/effect tests;
- external treatment control files remain outside the arm workspace, runtime
  state remains outside the product projection/review packages, and every
  judgment-only phase proves a stable product digest;
- the workflow performs no more than one plan revision and one implementation
  fix;
- fixed visible checks are controller-owned and cannot be weakened by an arm;
- hard, soft, exploratory, consumer, and process evidence remain distinct;
- blinded reviews can return `TIE` or `INDETERMINATE`;
- the prospective task is solution-neutral and has no reference patch;
- downstream consumer trials operate against either candidate's declared seam;
- every second consumer task is lineage-bound to a frozen first-consumer
  product from the same candidate;
- old demo behavior remains intact;
- two apparatus calibration pairs complete end to end and remain excluded from
  effectiveness claims;
- at least one controlled or replay pilot pair completes before `F1`;
- `F1` and `F2` can be executed without modifying their frozen contract;
- comparison and synthesis reports state only claims supported by their
  experiment class; and
- independent specification and quality reviews approve the implementation.

## Stop / Revise Criteria

Revise the design before confirmatory execution if:

- reference history or evaluators cannot be excluded from arm visibility;
- environment instances share mutable state that can affect results;
- candidate imports resolve to a live parent checkout or editable installation;
- external workflow/control-plane assets cannot be kept outside the arm
  workspace and provider-visible task context, or runtime state cannot be kept
  outside the product projection and undeclared phase context;
- the `.orc` workflow requires an unimplemented language surface;
- the direct arm cannot be limited to one provider invocation without changing
  normal provider competence;
- hard evaluators require one candidate's private implementation shape;
- reviewers cannot remain blind to method/cost;
- product and workflow-only changes cannot be separated reliably;
- the consumer tasks cannot be applied meaningfully to multiple candidate
  designs;
- the prospective task expands into a full fourteen-architecture migration;
- apparatus failures prevent trustworthy freeze/evaluation evidence;
- invalid-pair classification is being used to discard genuine unfavorable
  method outcomes; or
- experiment rules need to change after results are visible.

High reviewer disagreement, few discordant pairs, or task-dependent outcomes do
not justify forcing a conclusion. Return `INDETERMINATE` or
non-discriminating/underpowered, then define a separately locked replication if
more evidence is warranted.

## Documentation Impact

Implementation will add:

- a current experiment runbook;
- task-profile and schema documentation;
- the new `.orc` workflow and prompt catalog entries;
- a workflow-behavior simulation report;
- calibration and pilot evidence indexes; and
- a final effectiveness/viability synthesis report.

The March 2026 demo documents remain historical/informative and should link to
this design once the new harness is implemented. `docs/index.md`,
`workflows/README.md`, the capability matrix, and prompt indexes should be
updated only when the corresponding surfaces are actually available.

## Implementation Handoff

Implement in this order:

1. external-control-plane, provider-tool visibility, and certified-command
   feasibility spike;
2. versioned contracts and canonical hashing;
3. history-free source/environment provisioning;
4. concurrent paired runner, process-tree quiescence, freeze, and usage
   evidence;
5. modern typed `.orc` workflow plus disposable-extract fixed-check adapter;
6. hard-evaluation and finding-disposition pipeline;
7. blinded individual review, initial adjudication, and integrated review;
8. lineage-bound downstream-consumer trial controller;
9. comparison/synthesis reporting;
10. task profiles, prospective lifecycle contract, and withheld artifacts;
11. fixture simulation and apparatus calibration;
12. controlled/replay pilots;
13. prospective `F1`/`F2`;
14. byte-equivalent coordinator control, ablations, and final consequences.

The linked implementation plan supplies exact files, TDD steps, commands, and
review checkpoints.
