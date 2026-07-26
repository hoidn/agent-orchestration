# `.orc` Versus One-Shot Experiment Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task by task.
> Use a fresh implementation agent for each task, then an independent
> specification review and an independent code-quality review before advancing.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute an evidence-grade paired experiment that compares
one realistic provider invocation with a bounded `.orc` workflow, then
separates end-to-end orchestration effects from workflow-topology, prompt, and
`.orc` representation effects.

**Architecture:** Add a sibling `orchestrator.experiments` package rather than
changing the retained `orchestrator.demo` prototype. The controller freezes
versioned contracts, creates history-free and independently provisioned paired
arms, launches them concurrently, freezes both products, and drives a
chronologically sealed hard/soft/consumer evaluation pipeline. A generic
Workflow Lisp 2.15 control source remains outside each arm workspace. Generated
runtime state may be physically workspace-relative, but it is a separate
runtime projection excluded from the candidate product projection and review
packages. The workflow uses typed values plus certified path-carried records
for repeated structures.

**Tech Stack:** Python 3, `pytest`, `jsonschema`, Git archive plumbing,
subprocesses, conda environment materialization, Workflow Lisp 2.15, the
orchestrator CLI, JSON/JSONL evidence, tmux, and the `ptycho311` environment for
PtychoPINN work.

---

## Governing Design And Execution Rules

The governing design is
[`.orc` Versus One-Shot Experiment Program Design](../specs/2026-07-23-orc-vs-one-shot-experiment-design.md).
Read it before implementing any task. If this plan and that design disagree,
the design wins and this plan must be corrected before execution continues.

The implementation approach intentionally accepts two costs:

- it temporarily duplicates a small amount of process/provisioning plumbing
  instead of refactoring the legacy demo runner; and
- historical PtychoPINN tasks require explicit archive and Gitlink
  materialization rather than convenient shared clones.

That makes automatic migration of old demo commands and historical environment
setup harder. It preserves clean claim boundaries and prevents later Git
history, mutable control-plane files, or legacy demo assumptions from entering
the scored experiment.

Execution rules:

- Do not create worktrees.
- Preserve unrelated changes in the shared checkout. Stage and commit only the
  paths named by the current task.
- Use TDD: add a focused failing test, observe the expected failure, implement
  the narrow behavior, rerun the focused selector, then run the affected
  aggregate selector.
- If a task adds or renames test modules, run `pytest --collect-only` on those
  modules before executing them.
- Run long commands, environment builds, real workflow processes, and the broad
  suite in tmux. PtychoPINN workflow processes must run in `ptycho311`.
- Do not assert literal prompt wording. Test typed guidance, dependency
  carriage, behavioral routing, bounds, and artifacts.
- Do not change Workflow Lisp semantics to make the first workflow fit. A
  capability failure closes the feasibility gate and creates a separately
  reviewed design delta.
- Do not repair an experiment apparatus after viewing scored outcomes and
  continue under the old definition digest.
- Keep workflow source, prompts, extern manifests, runtime state, evaluators,
  and controller records out of the product projection. Workflow source,
  prompts, externs, evaluators, controller records, and the runtime installation
  must also remain outside the physical arm workspace.
- General product-security hardening and security auditing are out of scope.
  Information isolation required to make the comparison valid is a
  methodological prerequisite, not an optional security tranche. If satisfying
  it requires a reusable provider-sandbox/runtime capability, `G0` stops and
  that capability receives its own reviewed design and plan.

## Planned File Layout

Create these focused implementation units:

```text
orchestrator/experiments/
  __init__.py
  contracts.py             # schema loading, canonical JSON, digest bindings
  snapshots.py             # history-free source and immutable product freezes
  provisioning.py          # paired workspaces and independent environments
  process.py               # launch barrier, subprocess lifecycle, event logs
  usage.py                 # provider usage extraction with explicit unknowns
  adapters.py              # validation of path-carried workflow records
  evaluation.py            # hard findings, dispositions, integrated evidence
  blinding.py              # blinded candidate/reviewer package construction
  consumers.py             # balanced downstream-consumer allocation
  coordinator.py           # same-topology non-.orc representation control
  reporting.py             # deterministic pair and program projections
  runner.py                # persistent experiment lifecycle state machine
  cli.py                   # validate/provision/run/freeze/evaluate/report CLI
  schemas/
    __init__.py
    experiment-program-v1.schema.json
    task-profile-v1.schema.json
    replication-policy-v1.schema.json
    environment-lock-v1.schema.json
    series-lock-v1.schema.json
    experiment-lock-v1.schema.json
    arm-visible-manifest-v1.schema.json
    arm-assignment-v1.schema.json
    arm-execution-v1.schema.json
    environment-import-proof-v1.schema.json
    control-plane-visibility-proof-v1.schema.json
    visible-check-manifest-v1.schema.json
    checks-result-v1.schema.json
    context-discovery-detail-v1.schema.json
    implementation-plan-detail-v1.schema.json
    review-findings-v1.schema.json
    usage-v1.schema.json
    workspace-freeze-v1.schema.json
    hard-evaluation-v1.schema.json
    hard-finding-disposition-v1.schema.json
    initial-soft-review-v1.schema.json
    initial-review-adjudication-v1.schema.json
    integrated-review-v1.schema.json
    exploratory-probe-v1.schema.json
    failure-attribution-v1.schema.json
    pair-deviation-or-invalidation-v1.schema.json
    candidate-extension-evidence-v1.schema.json
    lifecycle-probe-request-v1.schema.json
    lifecycle-probe-result-v1.schema.json
    consumer-trial-v1.schema.json
    consumer-chain-lineage-v1.schema.json
    topology-equivalence-v1.schema.json
    interruption-control-v1.schema.json
    pair-comparison-v1.schema.json
    program-synthesis-v1.schema.json

scripts/experiments/
  paired_trial.py           # thin public entrypoint into experiments.cli

workflows/experiments/repository_task_loop/
  task_loop.orc             # generic typed workflow
  prompts/
    discover.md
    plan.md
    review_plan.md
    revise_plan.md
    implement.md
    review_implementation.md
    fix_implementation.md
  adapters/
    assert_product_digest.py
    validate_structured_record.py
    run_fixed_checks.py

experiments/orc_effectiveness/
  README.md
  control_plane/
    providers.json
    prompts.json
    commands.json
  programs/
  tasks/
  checks/
  evaluators/
  reviewers/
  consumers/
  series/

tests/experiments/
  test_external_control_plane.py
  test_contracts.py
  test_snapshots.py
  test_provisioning.py
  test_parallel_execution.py
  test_usage.py
  test_workflow_adapters.py
  test_repository_task_loop_compile.py
  test_repository_task_loop_runtime.py
  test_freezing.py
  test_hard_evaluation.py
  test_blinding.py
  test_consumers.py
  test_runner.py
  test_benchmark_profiles.py
  fixtures/
```

Do not create every empty file at once. Each task creates only the files it
puts under test.

## Milestone Gates

| Gate | Required before | Evidence |
| --- | --- | --- |
| `G0` control-plane feasibility | apparatus implementation | external `.orc` compile/run smoke, runtime-projection and per-phase visibility proof, certified command-result pass/fail proof |
| `G1` deterministic apparatus | any provider-backed pair | contract, snapshot, provisioning, runner, freeze, and leakage-negative tests |
| `G2` workflow feasibility | any scored `.orc` arm | compile, dry-run, fixture-provider branch matrix, product-digest guards |
| `G3` calibration | any scored benchmark | two unscored `A0` pairs complete end to end |
| `G4` realistic pilot | confirmatory or prospective work | at least one `A1`, `R1`, or `R2` pilot with sealed evaluation |
| `G5` prospective lock | `F1` launch | neutral task, evaluators, review rubric, consumer briefs, fixed replicate count, and environment lock frozen |
| `G6` causal controls | `.orc`-specific claims | same-topology Python coordinator and structural equivalence proof |

Failure of a gate is a result. Do not waive it by editing a record or excluding
the failed method arm.

Tasks 2–17 are conditional on `G0=passed`. Repository inspection at plan-draft
time indicates the built-in unrestricted provider profiles and
workspace-relative result bundles are likely to fail the strict per-phase
visibility proof. Task 1 must measure that fact. A `G0_BLOCKED` outcome is a
correct execution of this plan and prevents apparatus or scored-trial work
until the separate provider-phase isolation design is fully implemented,
passes its rootless `I0G` and subsequent gates, and the original public G0
scenario is rerun successfully. The prerequisite's 2026-07-23 base has landed
and is accepted. Task 1B's exact rootless `I0G` evidence has passed and been
independently approved. Production `I0`, the remaining prerequisite gates,
and the authoritative public `G0` rerun remain blockers.

`G0` governs core control-plane/per-phase filesystem, typed-bundle, and command
isolation. The separate historical source-retrieval probe classifies `R1`/`R2`
as causal-eligible or observational-only; it does not block prospective
apparatus when the core gate passes.

## Task 1: Prove The External Control Plane And Command Boundary

This is a stop/go spike against the currently implemented runtime. It precedes
new experiment machinery because scored work is inadmissible if `.orc` source,
prompts, externs, and state must be copied into only the workflow candidate.

**Files:**

- Create: `tests/experiments/test_external_control_plane.py`
- Create: `tests/experiments/fixtures/external_control_plane/provider.py`
- Create: `tests/experiments/fixtures/external_control_plane/check_adapter.py`
- Create: `docs/reports/2026-07-23-experiment-control-plane-feasibility.md`

- [ ] **Step 1: Add the test module and verify collection**

Create tests that build two temporary roots:

```python
control_root = tmp_path / "control"
product_root = tmp_path / "candidate"
state_root = tmp_path / "run-state"
```

Generate a minimal Workflow Lisp 2.15 source and prompt/extern manifests under
`control_root`, place only a task fixture under `product_root`, and invoke the
public CLI with `cwd=product_root`, absolute control-plane arguments, and
`--state-dir` under `state_root`.

Create unreadable-to-treatment sentinel files in the inactive prompt
directory, evaluator root, peer-arm root, and parent checkout. Configure the
fixture provider with the same filesystem/tool-root mechanism intended for real
trials; the test must attempt to read each known sentinel and record that all
attempts are denied. Merely omitting those paths from the prompt is not proof.

Use a two-provider-phase fixture to create a prior structured bundle, then
prove the later phase can read only the typed value/path explicitly declared as
its input. It must not be able to inspect the undeclared raw prior bundle,
inactive raw prompts, or controller state. This negative probe is required even
when those files use a workspace-relative runtime projection.

Run:

```bash
pytest --collect-only -q tests/experiments/test_external_control_plane.py
```

Expected: the intended tests collect.

- [ ] **Step 2: Write the failing external-control-plane test**

The fixture provider must:

- observe `Path.cwd()` as the candidate root;
- read the candidate task through a declared prompt dependency;
- write one ordinary product marker;
- return a typed result through the runtime-owned bundle; and
- record no need to copy or resolve workflow source from the arm workspace;
- fail to read known inactive-prompt, evaluator, peer-arm, and parent-checkout
  sentinel paths through its available filesystem tools; and
- fail to read undeclared prior raw bundles or controller state while still
  consuming its declared typed prior-phase input.

After the run, assert:

```python
assert not list(product_root.rglob("*.orc"))
assert not any(path.name in {"providers.json", "prompts.json", "commands.json"}
               for path in product_root.rglob("*"))
assert (product_root / "product-marker.txt").is_file()
assert state_root.is_dir()
assert ".orchestrate" not in frozen_product_manifest.paths
```

The physical arm workspace may contain a `.orchestrate` runtime projection.
The test must prove it is excluded from the product projection/reviewer package
and that providers cannot inspect undeclared prior runtime contents.

Also inspect the provider invocation record and require its declared workspace
to be `product_root`; no control-plane path may be included as a prompt
dependency or product input.

Add a separate historical-policy probe for remote Git, browser/source search,
and repository-fetch tools while provider API transport still works. It emits
`history_retrieval_classification = CAUSAL_ELIGIBLE | OBSERVATIONAL_ONLY`.
Unavailable source-retrieval isolation yields `OBSERVATIONAL_ONLY`; it is not a
core `G0` assertion and does not excuse any filesystem, control-plane,
phase-boundary, bundle, or command-boundary failure.

- [ ] **Step 3: Run the test against the current CLI**

Run:

```bash
pytest -q tests/experiments/test_external_control_plane.py::test_orc_control_plane_stays_outside_candidate_product
```

Expected on the unmodified current runtime: FAIL with the first observed
unsupported isolation/path rule. Record the exact failure; do not weaken the
assertion or assume `--state-dir` relocates workspace-relative bundles.

- [ ] **Step 4: Add certified `command-result` tests and a declaration stub**

Specify one adapter that will use `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, execute a
frozen argv manifest, and write a valid typed record for both:

- command exit `0`, represented as `PASS`; and
- command exit nonzero, represented as `FAIL` while adapter exit remains `0`.

Add negative fixtures for a missing bundle, wrong schema version, changed
manifest digest, and stdout-only output.

- [ ] **RED: Execute command-boundary cases before adding the adapter fixture**

Write the pass/fail/missing/wrong-schema/tamper/stdout-only tests first, point
them at a declaration-only adapter, and run:

```bash
pytest -q tests/experiments/test_external_control_plane.py -k command_result
```

Expected: FAIL on the first missing command-boundary behavior. Only then
implement `check_adapter.py`.

- [ ] **Step 4B: Implement the minimum command adapter**

Implement only the behavior covered by the red cases, then rerun the selector
and require PASS.

- [ ] **Step 5: Adjudicate the control-plane prerequisite**

Use supported CLI composition only. Do not change runtime semantics during this
spike. The public invocation is conceptually:

```bash
cd <candidate-root>
python -m orchestrator run <absolute-control-root>/task_loop.orc \
  --source-root <absolute-control-root> \
  --entry-workflow external_control_plane/task_loop::run \
  --provider-externs-file <absolute-control-root>/providers.json \
  --prompt-externs-file <absolute-control-root>/prompts.json \
  --command-boundaries-file <absolute-control-root>/commands.json \
  --input-file <candidate-root>/task-inputs.json \
  --state-dir <external-state-root>
```

There are exactly two truthful outcomes:

1. all core control-plane, per-phase filesystem, bundle, and command-boundary
   assertions pass on an existing supported provider profile, so `G0` may
   close; or
2. any core assertion fails, so write `G0_BLOCKED`, stop this plan before Task
   2, and draft a separate provider-phase information-isolation design and
   implementation plan. Do not stage treatment assets in the arm workspace and
   do not implement that prerequisite opportunistically inside this plan.

The historical-policy probe is recorded alongside either core outcome but does
not redefine it. `CAUSAL_ELIGIBLE` permits the planned withheld-history claim.
`OBSERVATIONAL_ONLY` keeps Tasks 2–17 executable but makes `R1` and `R2`
observational/exploratory and excludes them from causal or confirmatory
history-withheld claims. Local later-history, evaluator, peer-arm, and parent
checkout filesystem exclusion remains core and cannot be downgraded.

Workspace-relative generated bundle/state files are acceptable only in a
dedicated runtime projection that the product projection and reviewer packages
exclude and that exposes no inactive control assets. The feasibility record
must state the observed layout rather than assuming `--state-dir` relocates
every runtime-owned path.

- [ ] **Step 6: Record and verify `G0`**

For a passing outcome, write the report with exact commands, CLI/runtime commit,
fixture digests, product pre/post manifests, and limitations. For a blocked
outcome, write the same evidence plus the exact failed assertion and the
required separate design/plan paths; then stop. Run:

```bash
pytest -q tests/experiments/test_external_control_plane.py
git diff --check -- \
  tests/experiments/test_external_control_plane.py \
  tests/experiments/fixtures/external_control_plane \
  docs/reports/2026-07-23-experiment-control-plane-feasibility.md
```

Expected: all feasibility tests pass and the report claims only what those
tests observe for `G0=passed`. For `G0_BLOCKED`, the diagnostic command is
expected to fail at the recorded isolation assertion; do not run later gates.
For an `OBSERVATIONAL_ONLY` historical classification, the probe test passes by
validating that truthful classification record; it must not pretend the
retrieval tools were unavailable.

- [ ] **Step 7: Obtain both reviews and commit**

Specification review checks the control/product/state split. Quality review
checks fixture realism and fail-closed behavior.

For `G0=passed`, commit the green regression fixtures:

```bash
git add \
  tests/experiments/test_external_control_plane.py \
  tests/experiments/fixtures/external_control_plane \
  docs/reports/2026-07-23-experiment-control-plane-feasibility.md
git commit -m "test(experiments): prove external workflow control plane"
```

For `G0_BLOCKED`, do not add a permanently failing pytest module to the broad
suite. Commit the reviewed blocked report and the separately drafted
prerequisite design/plan; retain raw diagnostic fixtures in the external
content-addressed evidence store. This experiment plan then terminates.

## Task 2: Add Versioned Contracts And Canonical Digests

**Files:**

- Create: `orchestrator/experiments/__init__.py`
- Create: `orchestrator/experiments/contracts.py`
- Create: `orchestrator/experiments/schemas/experiment-program-v1.schema.json`
- Create: `orchestrator/experiments/schemas/__init__.py`
- Create: `orchestrator/experiments/schemas/task-profile-v1.schema.json`
- Create: `orchestrator/experiments/schemas/replication-policy-v1.schema.json`
- Create: `orchestrator/experiments/schemas/environment-lock-v1.schema.json`
- Create: `orchestrator/experiments/schemas/series-lock-v1.schema.json`
- Create: `orchestrator/experiments/schemas/experiment-lock-v1.schema.json`
- Create: `orchestrator/experiments/schemas/arm-visible-manifest-v1.schema.json`
- Create: `orchestrator/experiments/schemas/arm-assignment-v1.schema.json`
- Create: `tests/experiments/test_contracts.py`

- [ ] **Step 1: Write canonicalization and schema-validation tests**

Create declaration-only `orchestrator/experiments/contracts.py` functions that
raise `NotImplementedError`, so collection succeeds without supplying behavior.
Cover:

```python
def test_canonical_digest_is_key_order_independent() -> None: ...
def test_non_finite_json_is_rejected() -> None: ...
def test_unknown_contract_field_is_rejected() -> None: ...
def test_referenced_asset_digest_mismatch_is_rejected(tmp_path: Path) -> None: ...
def test_definition_versions_cannot_be_aggregated() -> None: ...
def test_product_exclusion_change_changes_lock_digest() -> None: ...
def test_task_profile_is_estimand_neutral() -> None: ...
def test_program_binds_estimand_and_two_arbitrary_treatment_ids() -> None: ...
def test_program_binds_versioned_replication_policy_digest() -> None: ...
def test_environment_lock_binds_all_build_and_role_images() -> None: ...
def test_series_lock_requires_exact_pair_and_consumer_chain_counts() -> None: ...
def test_series_lock_cannot_change_after_first_result() -> None: ...
```

Write the full referential-tamper matrix now, before implementation: task,
source archive, workflow, prompts, provider/command externs, visible checks,
hard evaluator, review rubric, consumer brief, environment lock, series lock,
replication policy, and product-exclusion policy.

- [ ] **RED: Execute contract tests before implementation**

Run collection, then the focused module:

```bash
pytest --collect-only -q tests/experiments/test_contracts.py
pytest -q tests/experiments/test_contracts.py
```

Expected: collect-only passes; the focused execution fails on
`NotImplementedError` or the first missing contract behavior.

- [ ] **Step 2: Implement the narrow contract API**

Provide:

```python
def canonical_json_bytes(value: object) -> bytes: ...
def sha256_digest(data: bytes) -> str: ...
def digest_json(value: object) -> str: ...
def digest_file(path: Path) -> str: ...
def load_and_validate(path: Path, schema_name: str) -> dict[str, object]: ...
def validate_series_lock(
    lock: Mapping[str, object],
    program: Mapping[str, object],
    *,
    sealed_lock_digest: str | None = None,
    admitted_result_digests: Sequence[str] = (),
) -> None: ...
def validate_experiment_lock(lock: Mapping[str, object], root: Path) -> None: ...
```

Use `allow_nan=False`, UTF-8, sorted keys, compact separators, and
`sha256:<hex>`. Load bundled JSON schemas with `importlib.resources`. Schemas
must set `additionalProperties: false` at governed objects and bind every
referenced artifact by digest.

`experiment_program.v1` owns an opaque `estimand_id`, exactly two treatment
objects and treatment IDs, treatment-specific asset digests, provider policy,
the digest of one `replication_policy.v1`, and allowed estimand-neutral profile
IDs. Its optional `cross_program_reference` object binds the reference program,
profile, series-lock, terminal-result-index, and treatment-equivalence-manifest
digests used by `E5`; it is absent for ordinary within-program contrasts.
`replication_policy.v1` owns a policy ID/version, explicit estimand scope,
eligible pilot inputs, per-estimand claim/replication levels, the pre-result
sample-size selection rule, separate-series rule, and prohibitions on
outcome-dependent extension and cross-estimand pooling. Program validation
requires its own estimand to appear in that scope.
`environment_lock.v1` binds the conda explicit-lock digest, wheel
requirements and wheelhouse-manifest digests, sealed dependency-image digest,
Python/tool identity, and role-specific candidate/evaluator/controller image
digests. Task profiles bind candidate and evaluator environment-lock digests;
the program binds the controller environment-lock digest.

`series_lock.v1` owns `series_id`, the canonical program digest, an exact list
of profile strata and pair counts, the complete randomization blocks, an
optional exact `F2` chain count per candidate, and a pre-result creation seal.
Validation recomputes the program digest and rejects unknown profiles or domain
partitions. Once results exist, the caller must pass the original
controller-owned `sealed_lock_digest` plus the admitted result digests;
validation rejects a missing seal, a current-lock digest mismatch, or any extra
or missing scheduled result. Task 12 persists that seal before launch and
supplies it on every result-ingest transition, so the temporal check cannot be
spoofed by deriving authority from the mutable lock under test.

The experiment lock and treatment mapping are controller-only. Derive and
validate a redacted arm-visible manifest that contains shared visible
authorities and an opaque arm ID but no method assignment, peer path,
controller path, evaluator path, or sealed asset identity.

- [ ] **Step 3: Add referential tamper fixtures**

Implement the referential validation needed to make the already-red tamper
tests pass. Do not add new test cases after observing the implementation.

- [ ] **Step 4: Run focused and affected tests**

```bash
pytest -q tests/experiments/test_contracts.py
pytest -q tests/test_workflow_lisp_native_returns_e2e.py
```

Expected: PASS.

- [ ] **Step 5: Obtain both reviews and commit**

```bash
git add orchestrator/experiments tests/experiments/test_contracts.py
git commit -m "feat(experiments): define content-addressed trial contracts"
```

## Task 3: Build History-Free Source Snapshots

**Files:**

- Create: `orchestrator/experiments/snapshots.py`
- Create: `tests/experiments/test_snapshots.py`
- Create: `tests/experiments/fixtures/snapshot_repo/README.md`

- [ ] **Step 1: Write failing archive-materialization tests**

Create a declaration-only `snapshots.py` API that raises
`NotImplementedError`, so collection succeeds before behavior exists.
Cover:

- `git archive` of an exact commit or exact subtree;
- normalized mode/path/type/digest manifest;
- independent fresh Git repositories with one seed commit each;
- no remotes, alternates, shared object store, or later objects;
- deterministic regular file, executable bit, symlink target, directory, and
  empty-tree handling;
- explicit Gitlink materialization from a separately frozen archive; and
- refusal to copy dirty or untracked source.

- [ ] **RED: Execute snapshot tests before implementation**

Run:

```bash
pytest --collect-only -q tests/experiments/test_snapshots.py
pytest -q tests/experiments/test_snapshots.py
```

Expected: collect-only passes; focused execution fails on the first unimplemented
snapshot behavior.

- [ ] **Step 2: Implement source archive and materialization APIs**

Provide:

```python
@dataclass(frozen=True)
class SourceArchive:
    commit: str
    archive_path: Path
    archive_sha256: str
    manifest_sha256: str

def create_source_archive(repo: Path, commit: str, destination: Path,
                          subtree: str | None = None) -> SourceArchive: ...
def materialize_arm(archive: SourceArchive, destination: Path) -> dict[str, object]: ...
def materialize_gitlink(parent_root: Path, relpath: str,
                        archive: SourceArchive) -> None: ...
```

Use non-shell argv subprocess calls. Reject nonempty destinations. Create the
seed commit with deterministic author/committer identity and timestamps.

- [ ] **Step 3: Prove later-history absence**

Create a fixture repository with base and future commits. After
materialization, require:

```bash
git -C <arm> cat-file -e <future-commit>
```

to fail. Also inspect `.git/objects/info/alternates`, remotes, refs, and object
inventory.

- [ ] **Step 4: Run tests and review**

```bash
pytest -q tests/experiments/test_snapshots.py
pytest -q tests/experiments/test_contracts.py tests/experiments/test_snapshots.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add \
  orchestrator/experiments/snapshots.py \
  tests/experiments/test_snapshots.py \
  tests/experiments/fixtures/snapshot_repo
git commit -m "feat(experiments): add history-free source snapshots"
```

## Task 4: Provision Independent Paired Arms And Environments

**Files:**

- Create: `orchestrator/experiments/provisioning.py`
- Create: `orchestrator/experiments/schemas/environment-import-proof-v1.schema.json`
- Create: `orchestrator/experiments/schemas/control-plane-visibility-proof-v1.schema.json`
- Create: `tests/experiments/test_provisioning.py`

- [ ] **Step 1: Write failing pair-provisioning tests**

Require:

- two opaque arm roots from the same archive and visible-input manifest;
- equal initial product digests and distinct `.git` roots;
- external controller/evaluator roots and a runtime-state layout conforming to
  the passed `G0` proof;
- separate `HOME`, `TMPDIR`, cache, test-cache, and run roots;
- equal CPU, memory, GPU, and concurrency allocations recorded in both arm
  manifests;
- no workflow source, raw prompt, or extern asset in either arm workspace;
- no reused pair ID or nonempty destination;
- sealed treatment assignment stored outside reviewer packages; and
- repository locations supplied at runtime, never as checked-in absolute paths.

- [ ] **Step 2: Add environment-instance contract tests**

Use a fake environment materializer first. Require symmetric commands and
normalized environment identities. Reject:

- mismatched explicit package locks;
- editable installs;
- editable requirements, local-path/direct-URL requirements, or wheels without
  a frozen SHA-256;
- `.pth` entries that resolve outside the frozen environment/candidate roots;
- nonempty `PYTHONPATH`; and
- candidate-package imports resolving outside the candidate arm.

Also require:

- one clean image built only from a checksum-validated conda explicit lock and
  a hash-pinned offline wheelhouse;
- two fresh, independently writable candidate instances materialized from that
  image;
- a third fresh evaluator instance with no shared mutable prefix, cache, or
  import path; and
- evaluator import proof showing that the target package resolves only from
  the verified extracted product under evaluation.

- [ ] **RED: Execute provisioning tests before implementation**

Create declaration-only provisioning/environment APIs that raise
`NotImplementedError`, then run:

```bash
pytest --collect-only -q tests/experiments/test_provisioning.py
pytest -q tests/experiments/test_provisioning.py
```

Expected: collection passes and execution fails on the first unimplemented
provisioning/environment behavior.

- [ ] **Step 3: Implement provisioning**

Provide:

```python
@dataclass(frozen=True)
class ArmProvision:
    opaque_label: str
    product_root: Path
    home: Path
    temp: Path
    cache: Path
    environment_prefix: Path

def provision_pair(lock: Mapping[str, object], destination: Path) -> tuple[ArmProvision, ArmProvision]: ...
def build_environment_image(
    conda_lock: Path,
    wheel_lock: Path,
    wheelhouse: Path,
    destination: Path,
) -> dict[str, object]: ...
def materialize_environment(
    image: Mapping[str, object],
    destination: Path,
    *,
    role: Literal["candidate", "evaluator"],
) -> Path: ...
def preflight_environment(
    prefix: Path,
    candidate_root: Path,
    import_names: Sequence[str],
) -> dict[str, object]: ...
```

The assignment record maps opaque labels to methods and is not copied into
either arm or blinded evaluation package.

The production path builds one immutable dependency image and materializes a
fresh writable instance per candidate arm plus a separate fresh evaluator
instance. It must never clone the mutable live `ptycho311` environment. Build
the clean image from frozen inputs:

```bash
conda create --yes --prefix <image-build-prefix> \
  --file <conda-explicit-lock>
<image-build-prefix>/bin/python -m pip install \
  --no-index \
  --require-hashes \
  --find-links <wheelhouse> \
  -r <pip-wheel-lock>
```

Every explicit conda artifact and wheel is digest-bound before the build. Seal
and digest the resulting image, then independently copy or unpack that sealed
image for each instance. The target repository and the orchestrator are not
installed into the image: candidate provider and test processes resolve target
code from their own candidate product root, while evaluator processes resolve
it from a verified immutable evaluation extract. The frozen orchestrator
wheel/runtime stays in the external controller environment; it is not
installed into only one candidate environment. Any editable metadata,
direct/local requirement, unhashed wheel, or escaping `.pth` entry fails the
build or preflight.

- [ ] **Step 4: Run focused tests**

```bash
pytest --collect-only -q tests/experiments/test_provisioning.py
pytest -q \
  tests/experiments/test_snapshots.py \
  tests/experiments/test_provisioning.py
```

Expected: PASS.

- [ ] **Step 5: Review and commit**

```bash
git add \
  orchestrator/experiments/provisioning.py \
  orchestrator/experiments/schemas/environment-import-proof-v1.schema.json \
  orchestrator/experiments/schemas/control-plane-visibility-proof-v1.schema.json \
  tests/experiments/test_provisioning.py
git commit -m "feat(experiments): provision independent paired arms"
```

## Task 5: Launch Both Arms Concurrently And Meter Observed Usage

**Files:**

- Create: `orchestrator/experiments/process.py`
- Create: `orchestrator/experiments/usage.py`
- Create: `orchestrator/experiments/schemas/arm-execution-v1.schema.json`
- Create: `orchestrator/experiments/schemas/usage-v1.schema.json`
- Create: `orchestrator/experiments/schemas/pair-deviation-or-invalidation-v1.schema.json`
- Create: `tests/experiments/test_parallel_execution.py`
- Create: `tests/experiments/test_usage.py`

- [ ] **Step 1: Write failing launch-barrier tests**

Test with fixture commands that block on a controller barrier and record
monotonic start times. Require:

- overlapping execution;
- controller launch skew within the frozen threshold;
- requested and observed CPU, memory, GPU, and concurrency allocations match
  the pair lock for both arms;
- distinct cwd/env/log/event roots;
- one arm failure not terminating or mutating the other;
- timeout termination with partial product preservation;
- periodic controller-observed heartbeats;
- process-group termination, escalation, descendant reaping, and a stable
  quiet-window product manifest before any trusted freeze;
- a hung provider and a tool subprocess that outlives its immediate parent;
- exactly one provider process for `DIRECT`; and
- arm-specific startup/capacity/runtime failure retained as a method outcome.

Predeclared contrast-breaking harness faults may produce `invalid_pair`,
including initial archive/environment mismatch, wrong resource/provider
allocation, wrong provider/model/effort/tool policy, evaluator/reference leakage
into either arm, controller artifact corruption, launch-barrier failure, or a
verified shared platform outage.
Arm-specific provider capacity, method startup, timeout, compiler/runtime,
typed-output, and product failures remain outcomes.

- [ ] **RED: Execute launch tests before implementation**

Create declaration-only process APIs, then run:

```bash
pytest --collect-only -q tests/experiments/test_parallel_execution.py
pytest -q tests/experiments/test_parallel_execution.py
```

Expected: collection passes and the first process-lifecycle assertion fails.

- [ ] **Step 2: Implement the process runner**

Provide:

```python
@dataclass(frozen=True)
class ArmCommand:
    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]
    timeout_seconds: int

def run_pair(left: ArmCommand, right: ArmCommand, evidence_root: Path,
             maximum_start_skew_ms: int) -> dict[str, object]: ...
```

Use `subprocess.Popen` with argv arrays and a dedicated process group (or the
platform-equivalent bounded process tree). Persist command, environment
identity, PID/group identity, heartbeat, timestamps, timeout/termination,
descendant-reaping result, quiet-window digests, exit status, stdout/stderr,
and JSONL events per arm.

If descendants cannot be quiesced, keep the timeout/method outcome but set
`product_freeze_trusted=false`; downstream product quality must be
`INDETERMINATE`.

- [ ] **Step 3: Write usage-parser tests**

Test recognized provider JSONL, partial usage, missing usage, malformed events,
and duplicate terminal events. Missing values must be `null` plus an explicit
completeness/source field; do not estimate from text length.

- [ ] **RED: Execute usage tests before implementing parsers**

Create declaration-only usage functions and run:

```bash
pytest --collect-only -q tests/experiments/test_usage.py
pytest -q tests/experiments/test_usage.py
```

Expected: collection passes and execution fails on unimplemented parsing.

- [ ] **Step 4: Implement narrow usage adapters**

Keep provider-specific parsing behind named, versioned functions. Return one
provider-neutral record containing observed input/output/cache tokens, calls,
source, and completeness.

- [ ] **Step 5: Run focused tests**

```bash
pytest --collect-only -q \
  tests/experiments/test_parallel_execution.py \
  tests/experiments/test_usage.py
pytest -q \
  tests/experiments/test_parallel_execution.py \
  tests/experiments/test_usage.py
```

Expected: PASS.

- [ ] **Step 6: Review and commit**

```bash
git add \
  orchestrator/experiments/process.py \
  orchestrator/experiments/usage.py \
  orchestrator/experiments/schemas/arm-execution-v1.schema.json \
  orchestrator/experiments/schemas/usage-v1.schema.json \
  orchestrator/experiments/schemas/pair-deviation-or-invalidation-v1.schema.json \
  tests/experiments/test_parallel_execution.py \
  tests/experiments/test_usage.py
git commit -m "feat(experiments): run paired arms concurrently"
```

## Task 6: Freeze Full Workspaces And Normalized Products

**Files:**

- Modify: `orchestrator/experiments/snapshots.py`
- Add: `orchestrator/experiments/schemas/workspace-freeze-v1.schema.json`
- Create: `tests/experiments/test_freezing.py`

- [ ] **Step 1: Write failing freeze tests**

Require two distinct authorities:

1. a full-byte immutable archive and manifest covering files, directories,
   executable bits, and symlink text; and
2. a product-only archive/manifest using the task profile's already-frozen
   include/exclude rules.

Test archive reproduction, manifest tampering, unsafe paths, exclusion changes,
mutation after freeze, and a mutating evaluator run against an extracted copy
whose post-run digest must fail even when the evaluator reports success.

- [ ] **RED: Execute freeze tests before implementation**

Add declaration-only freeze APIs that raise `NotImplementedError`, then run:

```bash
pytest --collect-only -q tests/experiments/test_freezing.py
pytest -q tests/experiments/test_freezing.py
```

Expected: collection passes and execution fails on the first freeze behavior.

- [ ] **Step 2: Implement freeze/extract/verify**

Provide:

```python
def freeze_workspace(workspace: Path, destination: Path,
                     product_policy: Mapping[str, object]) -> dict[str, object]: ...
def extract_verified_archive(archive: Path, expected_digest: str,
                             destination: Path) -> Path: ...
def verify_product_unchanged(root: Path, expected_manifest: Mapping[str, object]) -> None: ...
```

Do not use the mutable arm workspace for evaluation.

- [ ] **Step 3: Implement and verify evaluator-copy immutability**

Complete the behavior already specified by the RED fixture: run the evaluator
against an extracted copy, recompute the product digest afterward, and fail the
evaluation if it changed—even if the evaluator reports success.

- [ ] **Step 4: Run tests and commit**

```bash
pytest --collect-only -q tests/experiments/test_freezing.py
pytest -q tests/experiments/test_snapshots.py tests/experiments/test_freezing.py
```

After both reviews:

```bash
git add \
  orchestrator/experiments/snapshots.py \
  orchestrator/experiments/schemas/workspace-freeze-v1.schema.json \
  tests/experiments/test_freezing.py
git commit -m "feat(experiments): freeze complete and product workspaces"
```

## Task 7: Implement Deterministic Workflow Adapters

**Files:**

- Create: `orchestrator/experiments/adapters.py`
- Create: `workflows/experiments/repository_task_loop/adapters/assert_product_digest.py`
- Create: `workflows/experiments/repository_task_loop/adapters/validate_structured_record.py`
- Create: `workflows/experiments/repository_task_loop/adapters/run_fixed_checks.py`
- Create: `orchestrator/experiments/schemas/visible-check-manifest-v1.schema.json`
- Create: `orchestrator/experiments/schemas/checks-result-v1.schema.json`
- Create: `orchestrator/experiments/schemas/context-discovery-detail-v1.schema.json`
- Create: `orchestrator/experiments/schemas/implementation-plan-detail-v1.schema.json`
- Create: `orchestrator/experiments/schemas/review-findings-v1.schema.json`
- Create: `tests/experiments/test_workflow_adapters.py`

- [ ] **Step 1: Write failing adapter tests**

Cover:

- judgment-only pre/post product digests;
- tracked and untracked product mutations;
- runtime/control artifacts excluded only by the frozen product policy;
- schema/version/digest validation for path-carried repeated records;
- pass and fail fixed-command records;
- structured argv only, frozen cwd, timeouts, deterministic logs;
- check-manifest mismatch before any command runs;
- provider mutation of the check manifest; and
- adapter/process failure distinguished from represented check failure.

- [ ] **RED: Execute adapter tests before implementation**

Create declaration-only adapter APIs and run:

```bash
pytest --collect-only -q tests/experiments/test_workflow_adapters.py
pytest -q tests/experiments/test_workflow_adapters.py
```

Expected: collection passes and execution fails on the first unimplemented
schema/digest/check behavior.

- [ ] **Step 2: Implement the shared validators**

Repeated findings and plan steps are JSON records behind typed must-exist
`relpath` values because current native transport does not support
record/union values nested inside collections. The adapter validates each
file's schema version, product-relative safe paths, stable item IDs, and
content digest before the next provider phase can consume it.

- [ ] **Step 3: Implement fixed checks**

The adapter accepts a content-addressed manifest shaped like:

```json
{
  "schema_version": "visible_check_manifest.v1",
  "commands": [
    {
      "id": "focused",
      "argv": ["python", "-m", "pytest", "-q", "tests/test_target.py"],
      "timeout_seconds": 900,
      "required": true
    }
  ]
}
```

It writes the runtime-owned typed bundle plus a validated per-command record.
It exits zero for a valid report containing failed checks, and nonzero only
when it cannot honor the adapter contract.

The controller-owned manifest outside the arm workspace is authority. A
candidate-visible projection is re-digested before every invocation. The
adapter creates a fresh exact extract of the current product, runs all commands
there, and verifies the extract's input and post-command product digests.
Caches or mutations remain disposable evidence and never alter the candidate.
Add a fixture whose check child intentionally edits a file and spawns a
background writer; the adapter must disclose/reject the mutation and the
candidate digest must remain unchanged.

- [ ] **Step 4: Run focused tests**

```bash
pytest --collect-only -q tests/experiments/test_workflow_adapters.py
pytest -q \
  tests/experiments/test_external_control_plane.py \
  tests/experiments/test_workflow_adapters.py
```

Expected: PASS.

- [ ] **Step 5: Review and commit**

```bash
git add \
  orchestrator/experiments/adapters.py \
  orchestrator/experiments/schemas/visible-check-manifest-v1.schema.json \
  orchestrator/experiments/schemas/checks-result-v1.schema.json \
  orchestrator/experiments/schemas/context-discovery-detail-v1.schema.json \
  orchestrator/experiments/schemas/implementation-plan-detail-v1.schema.json \
  orchestrator/experiments/schemas/review-findings-v1.schema.json \
  workflows/experiments/repository_task_loop/adapters \
  tests/experiments/test_workflow_adapters.py
git commit -m "feat(experiments): add certified repository-task adapters"
```

## Task 8: Author The Generic Typed `.orc` Workflow

Use the `workflow-authoring` and `workflow-behavior-simulation` skills during
this task.

**Files:**

- Create: `workflows/experiments/repository_task_loop/task_loop.orc`
- Create: `workflows/experiments/repository_task_loop/prompts/discover.md`
- Create: `workflows/experiments/repository_task_loop/prompts/plan.md`
- Create: `workflows/experiments/repository_task_loop/prompts/review_plan.md`
- Create: `workflows/experiments/repository_task_loop/prompts/revise_plan.md`
- Create: `workflows/experiments/repository_task_loop/prompts/implement.md`
- Create: `workflows/experiments/repository_task_loop/prompts/review_implementation.md`
- Create: `workflows/experiments/repository_task_loop/prompts/fix_implementation.md`
- Create: `experiments/orc_effectiveness/control_plane/providers.json`
- Create: `experiments/orc_effectiveness/control_plane/prompts.json`
- Create: `experiments/orc_effectiveness/control_plane/commands.json`
- Create: `tests/experiments/test_repository_task_loop_compile.py`
- Create: `tests/experiments/test_repository_task_loop_runtime.py`
- Create: `tests/experiments/fixtures/repository_task_loop/provider.py`
- Create: `tests/experiments/fixtures/repository_task_loop/task-inputs.json`

- [ ] **Step 1: Write failing structural and runtime tests**

Test the compiled semantic/executable artifacts rather than prompt prose.
Require:

- DSL target `2.15`;
- typed task/repository/check inputs;
- context discovery, plan, plan review, optional single revision,
  second plan review, implementation, checks, implementation review, optional
  single fix, second checks, second implementation review, and typed outcome;
- `APPROVE` without ceremonial revision;
- one plan-revision and one implementation-fix ceiling;
- second `REVISE` after the applicable correction yields `EXHAUSTED`;
- provider-reported typed external/repository blocker yields `BLOCKED`;
- required check failure triggers the one focused fix even when the first
  implementation reviewer returns `APPROVE`;
- after the fix, any required check failure yields `EXHAUSTED` unless the
  second reviewer returns typed `BLOCKED`;
- optional check failures remain evidence and do not trigger correction;
- first implementation `APPROVE` completes from the first check result without
  a redundant second check;
- minimum successful route of five provider calls and unrolled maximum of nine;
- judgment-only digest guards around discovery and both reviews;
- task/repository facts supplied through typed inputs and prompt dependencies;
- direct native values where scalar/enum/path types are sufficient; and
- path carriers plus schema adapters for repeated structured items.

In the runtime module, add every fixture-provider case enumerated in Task 9
before authoring `task_loop.orc`.

- [ ] **RED: Execute workflow tests before authoring the workflow**

```bash
pytest --collect-only -q \
  tests/experiments/test_repository_task_loop_compile.py \
  tests/experiments/test_repository_task_loop_runtime.py
pytest -q \
  tests/experiments/test_repository_task_loop_compile.py \
  tests/experiments/test_repository_task_loop_runtime.py
```

Expected: collection passes; execution fails because the `.orc` source and
extern/prompt bindings do not yet exist.

- [ ] **Step 2: Define the types and return guidance**

Use the current implemented result-guidance syntax:

```lisp
:returns
  (result PlanReviewDecision
    :description "..."
    :format-hint "..."
    :example ...)
```

Every non-obvious result and payload field receives a semantic
`:description`; add typed `:format-hint` and `:example` where they reduce
ambiguity. Tests inspect that required guidance metadata exists and has a
type-correct example, never its exact words.

Do not declare unsupported values such as `List[ReviewFinding]`. Use flat
decision records/unions containing validated must-exist paths.

Use distinct typed meanings:

- `BLOCKED`: a specific unresolved dependency/condition prevents scoped work;
- `EXHAUSTED`: the one allowed correction has been consumed and review still
  returns `REVISE` or required checks still fail; and
- `COMPLETED`: a reviewed implementation with the applicable frozen check
  result.

Use separate `PlanReviewDecision` and `ImplementationReviewDecision` unions,
an `ImplementationAttempt = IMPLEMENTED | BLOCKED` union, and a
`CorrectionTrigger = REQUIRED_CHECK_FAILURE | REVIEW_FINDINGS | BOTH` enum or
union. Do not reuse a weaker generic review record whose variants disagree
with the graph.

- [ ] **Step 3: Write solution-neutral prompts**

Prompt responsibilities follow the governing design. No prompt may contain
`PtychoPINN`, `nanoBragg`, descriptor, tagged union, plugin system, preferred
file layout, expected finding count, or an instruction to manufacture a
revision.

- [ ] **Step 4: Compile through the public CLI**

Run:

```bash
python -m orchestrator compile \
  workflows/experiments/repository_task_loop/task_loop.orc \
  --source-root workflows/experiments \
  --entry-workflow repository_task_loop/task_loop::run-task \
  --provider-externs-file experiments/orc_effectiveness/control_plane/providers.json \
  --prompt-externs-file experiments/orc_effectiveness/control_plane/prompts.json \
  --command-boundaries-file experiments/orc_effectiveness/control_plane/commands.json
```

Expected: exit `0`.

- [ ] **Step 5: Run compile/contract tests**

```bash
pytest --collect-only -q tests/experiments/test_repository_task_loop_compile.py
pytest -q \
  tests/experiments/test_repository_task_loop_compile.py \
  tests/experiments/test_workflow_adapters.py
```

Expected: PASS.

- [ ] **Step 6: Simulate behavioral pressure cases**

Produce a content-addressed simulation report covering:

- a prospective architecture task;
- a hard task where one revision may be insufficient and must exhaust;
- a small task where workflow overhead likely dominates;
- an approving reviewer with no findings;
- a reviewer attempting an unsupported/no-op revision; and
- a check failure that an approving implementation reviewer cannot hide.

Store the report under:

```text
docs/reports/2026-07-23-repository-task-loop-behavior-simulation.md
```

- [ ] **Step 7: Review and commit**

```bash
git add \
  workflows/experiments/repository_task_loop \
  experiments/orc_effectiveness/control_plane \
  tests/experiments/test_repository_task_loop_compile.py \
  tests/experiments/test_repository_task_loop_runtime.py \
  tests/experiments/fixtures/repository_task_loop \
  docs/reports/2026-07-23-repository-task-loop-behavior-simulation.md
git commit -m "feat(workflows): add typed repository-task experiment loop"
```

## Task 9: Record The End-To-End Workflow Feasibility Gate

**Files:**

- Create: `docs/reports/2026-07-23-repository-task-loop-feasibility.md`

- [ ] **Step 1: Execute the prewritten fixture-provider branch matrix**

Execute real temporary workflow runs for:

- immediate plan and implementation approval;
- one useful plan revision then approval;
- repeated plan rejection yielding `EXHAUSTED` before implementation;
- one implementation finding and focused fix;
- repeated implementation finding after the focused fix yielding `EXHAUSTED`;
- first-pass implementation approval completing without a redundant fix/check
  cycle;
- first-pass reviewer `APPROVE` plus represented required-check failure still
  triggering the focused fix;
- second-pass reviewer `APPROVE` plus represented required-check failure
  yielding `EXHAUSTED`;
- optional-check failure plus reviewer `APPROVE` completing with disclosed
  optional evidence;
- malformed typed provider result;
- wrong/missing path-carried record;
- discovery mutation;
- plan-review mutation;
- implementation-review mutation; and
- provider-blocked outcome.

- [ ] **Step 2: Verify product and call bounds**

For every case, assert exact provider-role counts, phase order, product
pre/post digests, and terminal typed outcome. A judgment-only mutation must end
as method failure before later product work; it is not an invalid pair.

- [ ] **Step 3: Run public dry-run and runtime selectors**

```bash
python -m orchestrator run \
  workflows/experiments/repository_task_loop/task_loop.orc \
  --source-root workflows/experiments \
  --entry-workflow repository_task_loop/task_loop::run-task \
  --provider-externs-file experiments/orc_effectiveness/control_plane/providers.json \
  --prompt-externs-file experiments/orc_effectiveness/control_plane/prompts.json \
  --command-boundaries-file experiments/orc_effectiveness/control_plane/commands.json \
  --input-file tests/experiments/fixtures/repository_task_loop/task-inputs.json \
  --dry-run

pytest --collect-only -q tests/experiments/test_repository_task_loop_runtime.py
pytest -q \
  tests/experiments/test_repository_task_loop_compile.py \
  tests/experiments/test_repository_task_loop_runtime.py
```

Expected: all commands pass.

- [ ] **Step 4: Record evidence, obtain both reviews, and commit**

Write the report with the workflow/extern/prompt/adapter digests, exact commands
and outputs, branch coverage, call counts, product-digest guards, and both
review verdicts.

```bash
git add docs/reports/2026-07-23-repository-task-loop-feasibility.md
git commit -m "evidence(workflows): prove repository-task loop end to end"
```

`G2` is now satisfied only if Tasks 1, 7, 8, and 9 all remain green.

## Task 10: Build Chronological Hard, Soft, And Blinded Evaluation

**Files:**

- Create: `orchestrator/experiments/evaluation.py`
- Create: `orchestrator/experiments/blinding.py`
- Add:
  - `orchestrator/experiments/schemas/hard-evaluation-v1.schema.json`
  - `orchestrator/experiments/schemas/hard-finding-disposition-v1.schema.json`
  - `orchestrator/experiments/schemas/initial-soft-review-v1.schema.json`
  - `orchestrator/experiments/schemas/initial-review-adjudication-v1.schema.json`
  - `orchestrator/experiments/schemas/integrated-review-v1.schema.json`
  - `orchestrator/experiments/schemas/exploratory-probe-v1.schema.json`
  - `orchestrator/experiments/schemas/failure-attribution-v1.schema.json`
- Create: `tests/experiments/test_hard_evaluation.py`
- Create: `tests/experiments/test_blinding.py`

- [ ] **Step 1: Write chronology and immutability tests**

Require this state order:

```text
both frozen
  -> initial soft packages
  -> sealed initial reviews
  -> hard evaluation on extracted copies
  -> hard-finding dispositions
  -> integrated reviews
  -> probes/consumers
  -> method and cost unblinding
```

Hard evaluation before sealed initial reviews must fail. An integrated review
may cite the initial record and hard evidence but cannot replace either.
Individual reviewers use fresh sessions and cannot see peer records before both
seal. Every reviewer must complete an absolute candidate assessment before
pairwise comparison. At least two reviewers are required, with frozen
scientific/domain and API/persistence/migration perspectives. Any materially
different pairwise outcomes—including `A` versus `TIE`, `B` versus
`INDETERMINATE`, or opposing preferences—require a third fresh-session
initial-review adjudication record. Integrated review consumes the immutable
individual/adjudication identities plus normalized hard evidence and writes a
new record.

- [ ] **Step 2: Write hard-finding disposition tests**

Every raw failure must become exactly one of:

- `PRODUCT_DEFECT`;
- `ORACLE_DEFECT`;
- `SPEC_AMBIGUITY`;
- `INFRASTRUCTURE`; or
- `UNRESOLVED`.

Only a confirmed frozen-contract violation blocks a candidate. Add a fixture
where a patch-shaped hidden test fails a valid alternative and is adjudicated
`ORACLE_DEFECT`.

- [ ] **Step 3: Write leakage-negative blinding tests**

Reject packages containing:

- assignment or treatment identity;
- `.orc` or prompt/control-plane files;
- plans, review transcripts, provider logs, calls, tokens, elapsed time, or
  cost;
- reference patches or withheld history; or
- absolute paths revealing the method.

Initial packages contain shared task/instructions, product diff, relevant final
files, and candidate-authored product docs only. Integrated packages add sealed
hard evidence and the immutable initial-review identity.

- [ ] **Step 3A: Write exploratory-probe admission tests**

Require a proposed probe to be task-contract-relevant, implementation-neutral,
symmetrically executable, declared before unblinding, content-addressed, and
run on fresh immutable extracts. Rejected and admitted probes both retain typed
rationales; no exploratory result changes the frozen confirmatory score.

- [ ] **RED: Execute evaluation tests before implementation**

Create declaration-only evaluation/blinding APIs and run:

```bash
pytest --collect-only -q \
  tests/experiments/test_hard_evaluation.py \
  tests/experiments/test_blinding.py
pytest -q \
  tests/experiments/test_hard_evaluation.py \
  tests/experiments/test_blinding.py
```

Expected: collection passes and execution fails on the first missing chronology,
adjudication, leakage, or probe-admission behavior.

- [ ] **Step 4: Implement evaluation and blinding**

Use opaque candidate labels, deterministic package manifests, counterbalanced
presentation order, evidence-cited reviewer records, confidence, and
`A | B | TIE | INDETERMINATE`. Materially different pairwise outcomes require a
third adjudicator record.

- [ ] **Step 5: Run focused tests**

```bash
pytest --collect-only -q \
  tests/experiments/test_hard_evaluation.py \
  tests/experiments/test_blinding.py
pytest -q \
  tests/experiments/test_freezing.py \
  tests/experiments/test_hard_evaluation.py \
  tests/experiments/test_blinding.py
```

Expected: PASS.

- [ ] **Step 6: Review and commit**

```bash
git add \
  orchestrator/experiments/evaluation.py \
  orchestrator/experiments/blinding.py \
  orchestrator/experiments/schemas/hard-evaluation-v1.schema.json \
  orchestrator/experiments/schemas/hard-finding-disposition-v1.schema.json \
  orchestrator/experiments/schemas/initial-soft-review-v1.schema.json \
  orchestrator/experiments/schemas/initial-review-adjudication-v1.schema.json \
  orchestrator/experiments/schemas/integrated-review-v1.schema.json \
  orchestrator/experiments/schemas/exploratory-probe-v1.schema.json \
  orchestrator/experiments/schemas/failure-attribution-v1.schema.json \
  tests/experiments/test_hard_evaluation.py \
  tests/experiments/test_blinding.py
git commit -m "feat(experiments): add sealed mixed evaluation"
```

## Task 11: Add Balanced Downstream Consumer Trials

**Files:**

- Create: `orchestrator/experiments/consumers.py`
- Add: `orchestrator/experiments/schemas/consumer-trial-v1.schema.json`
- Add: `orchestrator/experiments/schemas/consumer-chain-lineage-v1.schema.json`
- Create: `tests/experiments/test_consumers.py`

- [ ] **Step 1: Write failing allocation tests**

Require:

- consumer briefs frozen before candidate outcomes;
- each fresh consumer sees exactly one anonymous candidate and one task;
- task 1 starts from the frozen `F1` candidate, then its output is frozen and
  task 2 starts from that exact lineage-bound task-1 archive;
- the same one-shot provider method, model, effort, tools, and deadline for
  every candidate;
- fresh provider sessions at both chain steps, with no transcript transfer;
- exactly the same positive number of independent two-step chains per
  candidate, as frozen by `series_lock.v1`, with any extra or missing chain
  rejected;
- no original workflow, competing candidate, method identity, or prior
  transcript;
- consumer start from a verified candidate product archive; and
- no automatic merge back to canonical source.

- [ ] **RED: Execute consumer tests before implementation**

Create declaration-only consumer APIs and run:

```bash
pytest --collect-only -q tests/experiments/test_consumers.py
pytest -q tests/experiments/test_consumers.py
```

Expected: collection passes and execution fails on the first allocation or
lineage behavior.

- [ ] **Step 2: Implement consumer allocation and records**

Record lifecycle completion, confirmed defects, changed files/layers,
architecture-local versus global schema churn, central builder/artifact edits,
provider usage, correction cycles, documentation blockers, and soft judgment
of whether low churn hides complexity.

Every task-2 record binds the original candidate digest, task-1 task digest,
task-1 frozen product archive/digest, task-2 task digest, and both fresh session
identities. Balance candidate run order, credentials/time blocks, and opaque
labels; do not claim pairwise presentation balancing when each consumer sees
only one candidate.

- [ ] **Step 3: Run tests and commit**

```bash
pytest --collect-only -q tests/experiments/test_consumers.py
pytest -q tests/experiments/test_consumers.py
```

After both reviews:

```bash
git add \
  orchestrator/experiments/consumers.py \
  orchestrator/experiments/schemas/consumer-trial-v1.schema.json \
  orchestrator/experiments/schemas/consumer-chain-lineage-v1.schema.json \
  tests/experiments/test_consumers.py
git commit -m "feat(experiments): add balanced consumer consequence trials"
```

## Task 12: Implement The Persistent Experiment Lifecycle And Reports

**Files:**

- Create: `orchestrator/experiments/runner.py`
- Create: `orchestrator/experiments/reporting.py`
- Create: `orchestrator/experiments/cli.py`
- Create: `scripts/experiments/paired_trial.py`
- Add:
  - `orchestrator/experiments/schemas/pair-comparison-v1.schema.json`
  - `orchestrator/experiments/schemas/program-synthesis-v1.schema.json`
- Create: `tests/experiments/test_runner.py`

- [ ] **Step 1: Write failing lifecycle tests**

Expose:

```text
validate
provision
preflight
run
freeze
prepare-initial-review
record-initial-review
record-initial-adjudication
evaluate-hard
record-hard-disposition
prepare-integrated-review
record-integrated-review
propose-probe
admit-probe
run-probe
record-probe
run-consumers
unblind
summarize
```

Every subcommand accepts `--program <path>` and
`--evidence-root <path>`. Series-scoped transitions also require
`--series-lock <path>`; record-ingest transitions require
`--record <path>`. Commands resolve the pair/phase from immutable runner state
instead of accepting an operator-selected arm.

The fake-command integration test executes this canonical ordering:

```bash
python scripts/experiments/paired_trial.py validate --program <program> --series-lock <lock> --evidence-root <root>
python scripts/experiments/paired_trial.py provision --program <program> --series-lock <lock> --evidence-root <root>
python scripts/experiments/paired_trial.py preflight --program <program> --series-lock <lock> --evidence-root <root>
python scripts/experiments/paired_trial.py run --program <program> --series-lock <lock> --evidence-root <root>
python scripts/experiments/paired_trial.py freeze --program <program> --series-lock <lock> --evidence-root <root>
python scripts/experiments/paired_trial.py prepare-initial-review --program <program> --series-lock <lock> --evidence-root <root>
python scripts/experiments/paired_trial.py record-initial-review --program <program> --series-lock <lock> --evidence-root <root> --record <review-a>
python scripts/experiments/paired_trial.py record-initial-review --program <program> --series-lock <lock> --evidence-root <root> --record <review-b>
python scripts/experiments/paired_trial.py evaluate-hard --program <program> --series-lock <lock> --evidence-root <root>
python scripts/experiments/paired_trial.py record-hard-disposition --program <program> --series-lock <lock> --evidence-root <root> --record <dispositions>
python scripts/experiments/paired_trial.py prepare-integrated-review --program <program> --series-lock <lock> --evidence-root <root>
python scripts/experiments/paired_trial.py record-integrated-review --program <program> --series-lock <lock> --evidence-root <root> --record <integrated>
python scripts/experiments/paired_trial.py propose-probe --program <program> --series-lock <lock> --evidence-root <root> --record <proposal>
python scripts/experiments/paired_trial.py admit-probe --program <program> --series-lock <lock> --evidence-root <root> --record <admission>
python scripts/experiments/paired_trial.py run-probe --program <program> --series-lock <lock> --evidence-root <root>
python scripts/experiments/paired_trial.py record-probe --program <program> --series-lock <lock> --evidence-root <root> --record <probe-result>
python scripts/experiments/paired_trial.py run-consumers --program <program> --series-lock <lock> --evidence-root <root>
python scripts/experiments/paired_trial.py unblind --program <program> --series-lock <lock> --evidence-root <root>
python scripts/experiments/paired_trial.py summarize --program <program> --series-lock <lock> --evidence-root <root>
```

When initial outcomes materially differ, insert
`record-initial-adjudication --record <adjudication>` before hard evaluation.
For profiles without probes or consumers, typed `not_applicable` closure
records are required; phases are not silently skipped.

Test illegal ordering, idempotent inspection, definition mutation, one-arm
rerun refusal, arm-specific failure retention, every predeclared
contrast-breaking invalidity condition, exploratory-probe ordering, refusal to
unblind before all admitted probes and consumers seal, and a complete
fake-command pair. Explicitly test that runner state persists the pre-result
series-lock digest and that result ingestion rejects a changed lock, missing
seal, duplicate result, unscheduled result, or incomplete terminal
denominator.

- [ ] **RED: Execute lifecycle tests before implementation**

Create declaration-only runner/reporting/CLI APIs and run:

```bash
pytest --collect-only -q tests/experiments/test_runner.py
pytest -q tests/experiments/test_runner.py
```

Expected: collection passes and execution fails at the first missing transition
or decision constraint.

- [ ] **Step 2: Implement a fail-closed state machine**

Each transition consumes prior digest-bound records and writes a new immutable
phase record. Before launch, persist the canonical `series_lock.v1` digest in
controller state. Every result-ingest transition calls
`validate_series_lock(...)` with that original seal and the complete admitted
result-digest set; a missing seal, changed lock, duplicate, extra, or missing
scheduled result fails closed.

Do not implement transparent provider-process resume for primary trials. A
deliberately injected interruption/resume experiment is a program-owned `E6`
control executed by Task 16's explicit supervisor; a broken confirmatory pair
is never repaired arm-selectively.

- [ ] **Step 3: Implement deterministic reporting**

The authoritative output is JSON. Markdown is regenerated from it. Keep
separate:

- hard-contract vectors;
- initial soft judgments, initial adjudication, and integrated reviews;
- consumer outcomes;
- process/runtime failures;
- provider calls/usage/cost;
- product churn; and
- `.orc` authoring/diagnostic burden.

Do not calculate an omnibus winner score.

Emit the governing non-composite decision vector:

```text
product_quality_outcome
per_treatment_viability
viability_relation
efficiency_relation
consumer_consequence_outcome
per_hypothesis_outcomes
```

Implement the exact constraints in the design: missing trusted product evidence
makes quality indeterminate without erasing a method failure; usage gaps make
the affected efficiency claim unknown; and consumer consequence comes only from
lineage-valid balanced chains.

- [ ] **Step 4: Run focused integration**

```bash
pytest --collect-only -q tests/experiments/test_runner.py
pytest -q tests/experiments/test_runner.py
python scripts/experiments/paired_trial.py --help
```

Expected: tests pass and CLI help exits `0`.

- [ ] **Step 5: Run `G1` aggregate verification**

```bash
pytest -q \
  tests/experiments/test_contracts.py \
  tests/experiments/test_snapshots.py \
  tests/experiments/test_provisioning.py \
  tests/experiments/test_parallel_execution.py \
  tests/experiments/test_usage.py \
  tests/experiments/test_freezing.py \
  tests/experiments/test_hard_evaluation.py \
  tests/experiments/test_blinding.py \
  tests/experiments/test_consumers.py \
  tests/experiments/test_runner.py
```

Expected: PASS.

- [ ] **Step 6: Review and commit**

```bash
git add \
  orchestrator/experiments/runner.py \
  orchestrator/experiments/reporting.py \
  orchestrator/experiments/cli.py \
  orchestrator/experiments/schemas/pair-comparison-v1.schema.json \
  orchestrator/experiments/schemas/program-synthesis-v1.schema.json \
  scripts/experiments/paired_trial.py \
  tests/experiments/test_runner.py
git commit -m "feat(experiments): add paired-trial lifecycle"
```

## Task 13: Freeze Benchmark Profiles And External Evaluators

Do not trust commit or Gitlink values copied from prose. Resolve and verify each
source in the controller repository, inspect the chosen commit's declared
Gitlinks, materialize only required Gitlinks from their exact object IDs, and
then freeze those observations into the profile.

**Files:**

- Create: `experiments/orc_effectiveness/README.md`
- Create: `experiments/orc_effectiveness/programs/e1-direct-vs-orc.json`
- Create: `experiments/orc_effectiveness/policies/pilot-replication-v1.json`
- Create: `experiments/orc_effectiveness/profiles/a0.json`
- Create: `experiments/orc_effectiveness/profiles/a1.json`
- Create: `experiments/orc_effectiveness/profiles/r1.json`
- Create: `experiments/orc_effectiveness/profiles/r2.json`
- Create: `experiments/orc_effectiveness/profiles/f1.json`
- Create: `experiments/orc_effectiveness/tasks/a0-linear-classifier.md`
- Create: `experiments/orc_effectiveness/tasks/a1-nanobragg-entrypoint.md`
- Create: `experiments/orc_effectiveness/tasks/r1-invocation-logging.md`
- Create: `experiments/orc_effectiveness/tasks/r2-object-policy.md`
- Create: `experiments/orc_effectiveness/tasks/f1-generator-extension-boundary.md`
- Create: `experiments/orc_effectiveness/consumers/f2-add-architecture.md`
- Create: `experiments/orc_effectiveness/consumers/f2-evolve-architecture.md`
- Create: `experiments/orc_effectiveness/control_plane/direct.md`
- Create: `experiments/orc_effectiveness/environments/controller.json`
- Create: `experiments/orc_effectiveness/environments/generic.json`
- Create: `experiments/orc_effectiveness/environments/ptycho311.json`
- Create: `experiments/orc_effectiveness/environments/ptycho311-conda-explicit.txt`
- Create: `experiments/orc_effectiveness/environments/ptycho311-wheels.lock`
- Create: `experiments/orc_effectiveness/environments/ptycho311-wheelhouse-manifest.json`
- Create: `experiments/orc_effectiveness/environments/evaluator-ptycho311.json`
- Create: `experiments/orc_effectiveness/checks/a0.json`
- Create: `experiments/orc_effectiveness/checks/a1.json`
- Create: `experiments/orc_effectiveness/checks/r1.json`
- Create: `experiments/orc_effectiveness/checks/r2.json`
- Create: `experiments/orc_effectiveness/checks/f1.json`
- Create: `experiments/orc_effectiveness/evaluators/a0.py`
- Create: `experiments/orc_effectiveness/evaluators/a1.py`
- Create: `experiments/orc_effectiveness/evaluators/r1.py`
- Create: `experiments/orc_effectiveness/evaluators/r2.py`
- Create: `experiments/orc_effectiveness/evaluators/f1.py`
- Create: `experiments/orc_effectiveness/evaluators/fixtures/a0/manifest.json`
- Create: `experiments/orc_effectiveness/evaluators/fixtures/a1/manifest.json`
- Create: `experiments/orc_effectiveness/evaluators/fixtures/r1/manifest.json`
- Create: `experiments/orc_effectiveness/evaluators/fixtures/r2/manifest.json`
- Create: `experiments/orc_effectiveness/evaluators/fixtures/f1/manifest.json`
- Create: `experiments/orc_effectiveness/reviewers/product-quality-v1.json`
- Create: `orchestrator/experiments/schemas/candidate-extension-evidence-v1.schema.json`
- Create: `orchestrator/experiments/schemas/lifecycle-probe-request-v1.schema.json`
- Create: `orchestrator/experiments/schemas/lifecycle-probe-result-v1.schema.json`
- Create: `tests/experiments/test_benchmark_profiles.py`
- Create: `tests/experiments/test_benchmark_evaluators.py`
- Create: `tests/experiments/test_f1_lifecycle_contract.py`

- [ ] **Step 1: Add failing profile validation tests**

Require:

- exact source repository and source commit resolve;
- source archive and normalized manifest digests match;
- future/withheld commit is absent from materialized arms;
- evaluator, fixture, task, check, rubric, prompt, workflow, environment, and
  consumer digests resolve;
- every task profile carries `profile_id` and `stage_id` but no
  `estimand_id` or treatment identity;
- the `E1` program owns `estimand_id=E1`, exactly two arbitrary treatment IDs,
  their treatment assets/provider policy, the digest of the schema-valid
  pilot replication policy, the controller-environment lock, and the five
  allowed profile IDs;
- later programs, rather than reused task profiles, own `E2`–`E6`;
- each profile binds schema-valid candidate and evaluator environment locks
  whose dependency/image/input digests resolve;
- `A0` is `apparatus_only`;
- `F1` has no reference patch;
- `F1` integrated product-quality outcome and `F2` consequences are co-primary;
- the pilot policy fixes two `A0` pairs and one pair for each selected
  controlled/replay pilot;
- every later confirmatory series requires its own pre-result
  `series_lock.json` with fixed `N`, with no denominator extension;
- invalidity and unblinding rules are frozen; and
- no profile selects the dirty live PtychoPINN checkout.
- historical programs freeze a provider-tool policy that disables browser,
  source search, remote Git, and repository fetching while retaining provider
  API transport; an unenforceable policy downgrades the profile to
  observational/exploratory.

- [ ] **RED: Execute profile tests before creating definitions**

```bash
pytest --collect-only -q tests/experiments/test_benchmark_profiles.py
pytest -q tests/experiments/test_benchmark_profiles.py
```

Expected: collection passes and execution fails because the enumerated profiles
and digest-bound assets do not exist.

- [ ] **Step 2: Verify historical source identities**

Verify, rather than assume, the design's candidate commits:

- `R1` base `d3b012bf6d817fc02a03f31becf68b715d365dd9`,
  withheld `d45147bffac90b608fa0c39927ce36adf14c9c7f`;
- `R2` base `1a68784c8019eec97c3557ff95e509c24cdb2cfe`,
  withheld `78a7ca22e83d489d4544c79fda5a5e8b26f0e0ea`; and
- `F1` base `c081b7b6cd160b3da7031ee325bbf0ade1025d7a`.

If any does not resolve or does not contain the intended problem state, update
the design and plan before locking a replacement.

- [ ] **Step 3: Freeze executable environment identities**

In tmux, build one orchestrator wheel from the selected clean controller
commit. Inspect the live environment only as dependency-intent evidence; do not
clone it and do not accept its editable installations as frozen inputs:

```bash
conda run --no-capture-output -n ptycho311 \
  python -m build --wheel --outdir <external-evidence-root>/wheels
conda list --explicit -n ptycho311 \
  > <external-evidence-root>/environment-inputs/ptycho311-live-observation.txt
conda run --no-capture-output -n ptycho311 python -m pip freeze \
  > <external-evidence-root>/environment-inputs/ptycho311-live-pip-observation.txt
```

Derive and review `ptycho311-conda-explicit.txt` from the declared dependency
intent and immutable conda artifacts. Resolve each required non-conda
dependency to a non-editable wheel, record every SHA-256 in
`ptycho311-wheels.lock` and `ptycho311-wheelhouse-manifest.json`, and explicitly
exclude the live PtychoPINN and orchestrator editable installs. Build the clean
image using Task 4's offline lock-and-wheelhouse path, then smoke-test fresh
candidate and evaluator instances before freezing `ptycho311.json` and
`evaluator-ptycho311.json`.

Record the exact image, lock, wheel, Python, provider CLI, relevant tool, and
import-proof digests in `environments/*.json`. The controller wheel remains
external to candidate and evaluator environments. A copied live `.pth` file,
editable or direct reference, unresolved pip dependency, or unhashed wheel is a
hard preflight failure.

- [ ] **Step 3A: Author the closed program and task profiles**

Create the `E1` program, pilot replication policy, five estimand-neutral
profile JSON records, direct prompt, task briefs, and per-profile check
manifests. Each profile binds the exact source/archive, task, environment,
visible checks, evaluator/fixtures, review rubric, product projection,
invalidity rules, and applicable consumer assets. The program binds
`estimand_id=E1`, the `DIRECT` and `ORC` treatment definitions, all
treatment-specific prompt/workflow assets, provider/tool/source-fetch policy,
the schema-valid `pilot-replication-v1.json` digest, the controller-environment
lock, and the five allowed profile IDs. Validate every environment JSON as
`environment_lock.v1`; the candidate/evaluator role and lock/image/wheelhouse
digests must match the role-specific profile references.

`control_plane/direct.md` must permit normal competent one-invocation behavior:
inspection, private planning, editing, testing, and iteration. It receives the
same task/repository dependencies as the workflow arm and does not prescribe a
solution, forbid tools, or ask for `.orc`-specific artifacts.

- [ ] **Step 4: Write evaluator and lifecycle tests**

Before adapting evaluator code, test:

- each evaluator's normalized input/result schema and immutable-copy behavior;
- known positive/negative fixtures for `A0`, `A1`, `R1`, and `R2`;
- oracle-disposition metadata for every hard claim;
- candidate evidence-manifest validation; and
- the two fresh-process `F1` lifecycle operations.

The frozen candidate adapter path is:

```text
tools/orc_experiment/architecture_lifecycle.py
```

The evaluator invokes it twice from a fresh pristine evaluator environment,
with the verified product extract as cwd:

```bash
cd <verified-product-extract>
<evaluator-python> tools/orc_experiment/architecture_lifecycle.py \
  --request <train-save-request.json> \
  --result <train-save-result.json>
<evaluator-python> tools/orc_experiment/architecture_lifecycle.py \
  --request <reload-infer-request.json> \
  --result <reload-infer-result.json>
```

The first request covers configure, public construction, forward,
loss/backward, one optimizer step or bounded short train, and save. The second
starts from the first frozen artifact and covers fresh-process reload and
inference. `evaluators/fixtures/f1/manifest.json` enumerates every supported
artifact-era fixture with its exact path, origin, intended contract, and
SHA-256; no post-result fixture may be added to the locked series.
Before either operation, record an `environment_import_proof.v1` showing that
the target package's `__file__` is beneath `<verified-product-extract>`, the
interpreter is beneath the fresh evaluator prefix, and neither path reaches an
arm workspace or live checkout.

- [ ] **RED: Execute evaluator tests before implementation**

Create declaration-only evaluator functions and run:

```bash
pytest --collect-only -q \
  tests/experiments/test_benchmark_evaluators.py \
  tests/experiments/test_f1_lifecycle_contract.py
pytest -q \
  tests/experiments/test_benchmark_evaluators.py \
  tests/experiments/test_f1_lifecycle_contract.py
```

Expected: collection passes and the first missing evaluator/lifecycle behavior
fails.

- [ ] **Step 5: Adapt behavior-level evaluators**

Reuse stable linear-classifier and nanoBragg evaluator logic behind versioned
contracts. Historical tests introduced by withheld commits may inspire
evaluator overlays, but no reference patch, private name, or patch similarity
becomes scoring authority.

For every hard assertion, record the public contract it tests and the
adjudication path for an oracle dispute.

Before `F1` can become confirmatory, use
`candidate-extension-evidence-v1.schema.json`,
`lifecycle-probe-request-v1.schema.json`, and
`lifecycle-probe-result-v1.schema.json` as the sole canonical schema
authorities. The `F1` profile binds their digests; the candidate, controller,
and evaluator do not define competing task-local schemas.

Freeze a solution-neutral candidate evidence manifest and the fixed
product-relative lifecycle-adapter CLI. The
adapter accepts evaluator-owned versioned JSON requests and emits versioned
results for both the migrated representative and witness architectures. It
must exercise configure, public construction, forward, loss/backward, one
optimizer step or bounded short train, save, and fresh-process reload/inference.
Evaluator-owned pristine tests verify artifacts and behavior rather than
trusting candidate claims. The adapter remains in the candidate diff and its
ceremony is included in the soft/ergonomics evaluation.

If this interface cannot be frozen before candidates run, mark `F1`
exploratory and forbid confirmatory prospective claims.

- [ ] **Step 6: Freeze the prospective task and consumer briefs**

Keep the neutral `F1` wording from the design. Do not mention a descriptor,
tagged union, plugin system, named class, preferred layout, or expected file
count. Freeze both `F2` briefs before any `F1` arm executes.

- [ ] **Step 7: Run profile and evaluator tests**

```bash
pytest --collect-only -q tests/experiments/test_benchmark_profiles.py
pytest -q \
  tests/experiments/test_benchmark_profiles.py \
  tests/experiments/test_benchmark_evaluators.py \
  tests/experiments/test_f1_lifecycle_contract.py
```

Expected: PASS with every referenced digest materialized.

- [ ] **Step 8: Review and commit**

One reviewer checks benchmark neutrality and source/history isolation. The
other checks evaluator validity and artifact completeness.

```bash
git add \
  experiments/orc_effectiveness \
  orchestrator/experiments/schemas/candidate-extension-evidence-v1.schema.json \
  orchestrator/experiments/schemas/lifecycle-probe-request-v1.schema.json \
  orchestrator/experiments/schemas/lifecycle-probe-result-v1.schema.json \
  tests/experiments/test_benchmark_profiles.py \
  tests/experiments/test_benchmark_evaluators.py \
  tests/experiments/test_f1_lifecycle_contract.py
git commit -m "feat(experiments): freeze repository-task benchmark profiles"
```

## Task 14: Pass Calibration And Run Controlled/Replay Pilots

This task creates evidence, not product implementation. Do not tune prompts,
checks, exclusion rules, or invalidity policy after seeing an arm result.

**Files:**

- Create: `experiments/orc_effectiveness/series/apparatus-v1/`
- Create: `experiments/orc_effectiveness/series/apparatus-v1/series-lock.json`
- Create: `experiments/orc_effectiveness/series/controlled-v1/`
- Create: `experiments/orc_effectiveness/series/controlled-v1/series-lock.json`
- Create: `experiments/orc_effectiveness/series/replay-v1/`
- Create: `experiments/orc_effectiveness/series/replay-v1/series-lock.json`
- Create: `docs/reports/2026-07-23-orc-experiment-calibration-and-pilots.md`

- [ ] **Step 1: Verify the frozen environment and materialize fresh arm instances**

Verify the content-addressed controller wheel and environment identities frozen
in Task 13. For preflight, materialize two independent `ptycho311` candidate
instances plus a separate pristine evaluator instance. Every later pair
materializes fresh independent candidate instances, and every hard-evaluation
copy receives a fresh evaluator instance, instead of reusing a mutable
environment. The controller uses the external frozen orchestrator environment;
neither candidate nor evaluator environment receives a treatment-only
orchestrator install. Record normalized `conda list --explicit`, Python
identity, wheel/image digest, role, instance ID, and import origins.

Reject the run if either candidate import resolves through an editable install,
nonempty `PYTHONPATH`, a `.pth` entry escaping the frozen
environment/candidate roots, or the live parent checkout.

Reject hard evaluation if its interpreter is not in the dedicated evaluator
prefix or the target import does not resolve beneath the verified immutable
product extract.

Before any result is visible, freeze three exact `series_lock.v1` records:

- `apparatus-v1`: exactly two `A0` pairs;
- `controlled-v1`: exactly one `A1` pair; and
- `replay-v1`: exactly one `R1` pair and one `R2` pair.

Each lock binds the same `E1` program digest, its exact profile strata and
randomization blocks, and forbids extension after first-result ingestion.

- [ ] **Step 2: Run the complete deterministic apparatus suite**

In tmux:

```bash
pytest -q tests/experiments
pytest -q -n 16 --dist=worksteal
```

Expected: focused suite and repository broad suite pass from fresh output. If
the broad suite has a pre-existing failure, preserve the exact baseline and
adjudicate ownership before any provider-backed trial.

- [ ] **Step 3: Run two unscored `A0` pairs**

Use the lifecycle CLI from validation through unblinding and summary. Confirm:

- concurrent launch;
- one direct provider invocation;
- bounded workflow calls;
- full/product freezes;
- initial soft sealing before hard evidence;
- leakage-negative blinded packages;
- nullable usage;
- and deterministic report regeneration.

Any apparatus change after a pair creates a new apparatus digest; rerun both
calibration pairs under that digest. `A0` never counts toward effectiveness.

- [ ] **Step 4: Obtain apparatus reviews**

Independent reviewers inspect the frozen definitions, both arm histories,
freeze manifests, evaluation chronology, and generated comparison. Close `G3`
only after both approve.

- [ ] **Step 5: Run `A1`, then `R1` and `R2` pilots**

Run one pilot pair per profile in tmux. A method-specific compiler/runtime,
capacity, timeout, typed-output, planning, or product failure remains the
observed outcome. A predeclared asymmetric harness fault—such as wrong
environment/allocation or evaluator leakage in one arm—may invalidate the
contrast; arm-specific method failure may not.

For the replay tasks, evaluate behavior and compatibility without disclosing
the withheld reference until initial reviews, hard dispositions, integrated
reviews, and admitted probes are sealed.

- [ ] **Step 6: Write the pilot report**

Separate:

- apparatus validity;
- end-to-end product evidence;
- reviewer agreement/disagreement;
- hidden-check dispositions;
- cost/time/call evidence;
- `.orc` workflow/runtime failures;
- and hypotheses still unsupported.

Do not name a universal winner. Close `G4` when at least one realistic pilot
has complete sealed evidence.

- [ ] **Step 7: Review and commit evidence**

Commit only content-addressed definitions, structured records, indexes, and
the report. Large raw archives may live in the declared external evidence
store with immutable digests in the repository.

```bash
git add \
  experiments/orc_effectiveness/series/apparatus-v1 \
  experiments/orc_effectiveness/series/controlled-v1 \
  experiments/orc_effectiveness/series/replay-v1 \
  docs/reports/2026-07-23-orc-experiment-calibration-and-pilots.md
git commit -m "evidence(experiments): record calibration and replay pilots"
```

## Task 15: Run Prospective PtychoPINN And Consumer Consequence Trials

**Files:**

- Create: `experiments/orc_effectiveness/series/prospective-v1/`
- Create: `experiments/orc_effectiveness/series/prospective-v1/series-lock.json`
- Create: `experiments/orc_effectiveness/series/prospective-v1/consumers/`
- Create: `docs/reports/2026-07-23-ptychopinn-architecture-consequence-experiment.md`

- [ ] **Step 1: Lock `G5` before launch**

Apply the already-frozen pilot replication policy, then create
`prospective-v1/series-lock.json`. Freeze a fixed replicate count using only
eligible pilot variance, discordance, cost, and intended inference. Pilot pairs
are excluded from the confirmatory denominator. Ten pairs is the planning
assumption, not an automatic choice. Record the chosen count before the first
confirmatory `F1` result is visible. The same lock freezes an exact number of
two-step `F2` chains per candidate; two is the initial planning count, not a
minimum or permission to extend. Reject any later change to either count.

If the fixed series later proves underpowered, close it as underpowered. Any
additional sample is a separately locked replication series.

- [ ] **Step 2: Preflight every `F1` pair**

Verify identical source/task/visible-check/environment digests, opaque
assignment, no reference history, external control plane, and no dirty seed.
Launch each pair concurrently without post-launch steering.

- [ ] **Step 3: Complete the chronological evaluation**

For every pair:

1. freeze both full and product workspaces;
2. prepare and seal initial soft reviews without hidden results;
3. run hard evaluators on immutable extracts;
4. adjudicate every failure;
5. seal integrated reviews;
6. run admitted symmetric probes;
7. keep method/cost data blinded.

- [ ] **Step 4: Run balanced `F2` consumer trials**

For each frozen candidate, run exactly the number of independent lineage chains
declared in `prospective-v1/series-lock.json`. A fresh one-shot session performs
task 1; freeze and hash that product; then a second fresh session performs task
2 from the exact task-1 product without receiving the first transcript. Use
identical provider method and allocations for all candidates. Evaluate both
chain steps for construction, save, fresh-process reload, inference,
compatibility with the earlier artifact, edit locality, shared-schema churn,
and documentation sufficiency. An extra chain requires a new series ID and
lock; it never enlarges this denominator.

- [ ] **Step 5: Seal consequences and unblind last**

Require every admitted probe and every scheduled `F2` chain/consequence review
to have a terminal typed record. Then, and only then, run:

```bash
python scripts/experiments/paired_trial.py unblind \
  --program experiments/orc_effectiveness/programs/e1-direct-vs-orc.json \
  --series-lock experiments/orc_effectiveness/series/prospective-v1/series-lock.json \
  --evidence-root <external-evidence-root>/prospective-v1
```

Expected: unblinding succeeds only after the full chronology is sealed.

- [ ] **Step 6: Report consequence evidence**

The report must distinguish:

- a design that is locally elegant but difficult to extend;
- low file churn caused by genuine ownership versus opaque generic glue;
- hidden-test disagreement caused by oracle brittleness;
- current lifecycle correctness;
- future consumer success;
- and quality/cost tradeoffs.

No experiment output is merged automatically into PtychoPINN.

- [ ] **Step 7: Obtain both reviews and commit**

```bash
git add \
  experiments/orc_effectiveness/series/prospective-v1 \
  docs/reports/2026-07-23-ptychopinn-architecture-consequence-experiment.md
git commit -m "evidence(experiments): record prospective consequence trials"
```

## Task 16: Add Same-Topology Control And Mechanism Ablations

Do not make `.orc`-specific claims from `DIRECT` versus `ORC` alone.

**Files:**

- Create: `orchestrator/experiments/coordinator.py`
- Create: `orchestrator/experiments/interruption.py`
- Modify: `orchestrator/experiments/cli.py`
- Modify: `scripts/experiments/paired_trial.py`
- Create: `orchestrator/experiments/schemas/topology-equivalence-v1.schema.json`
- Create: `orchestrator/experiments/schemas/interruption-control-v1.schema.json`
- Create: `tests/experiments/test_coordinator_equivalence.py`
- Create: `tests/experiments/test_coordinator_runtime_parity.py`
- Create: `tests/experiments/test_ablation_programs.py`
- Create: `tests/experiments/test_interruption_control.py`
- Create: `workflows/experiments/repository_task_loop/no_review_fix.orc`
- Create: `experiments/orc_effectiveness/programs/e2-review-fix-ablation.json`
- Create: `experiments/orc_effectiveness/programs/e3-orc-vs-coordinator.json`
- Create: `experiments/orc_effectiveness/programs/e4-prompt-variant.json`
- Create: `experiments/orc_effectiveness/programs/e5-transfer.json`
- Create: `experiments/orc_effectiveness/programs/e6-resume.json`
- Create: `experiments/orc_effectiveness/policies/control-replication-v1.json`
- Create: `experiments/orc_effectiveness/control_plane/prompt_variants/e4.json`
- Create: `experiments/orc_effectiveness/control_plane/prompt_variants/e4-review-b.md`
- Create: `experiments/orc_effectiveness/interruptions/e6-after-committed-boundary.json`
- Create: `experiments/orc_effectiveness/profiles/x1.json`
- Create: `experiments/orc_effectiveness/tasks/x1-unrelated-domain.md`
- Create: `experiments/orc_effectiveness/checks/x1.json`
- Create: `experiments/orc_effectiveness/evaluators/x1.py`
- Create: `experiments/orc_effectiveness/evaluators/fixtures/x1/manifest.json`
- Create: `experiments/orc_effectiveness/environments/x1.json`
- Create: `experiments/orc_effectiveness/environments/evaluator-x1.json`
- Create: `experiments/orc_effectiveness/series/e2-review-fix-v1/series-lock.json`
- Create: `experiments/orc_effectiveness/series/e3-orc-vs-coordinator-v1/series-lock.json`
- Create: `experiments/orc_effectiveness/series/e4-prompt-variant-v1/series-lock.json`
- Create: `experiments/orc_effectiveness/series/e5-transfer-v1/series-lock.json`
- Create: `experiments/orc_effectiveness/series/e6-resume-v1/series-lock.json`
- Create: `docs/reports/2026-07-23-orc-representation-and-mechanism-controls.md`

- [ ] **Step 1: Write failing topology-equivalence tests**

Compare a declarative coordinator manifest with compiled `.orc` artifacts.
Require identical:

- prompt files and digests;
- fully rendered provider prompt bytes, including generated result-contract
  suffixes;
- provider roles, model/effort policy, timeouts, and call ceilings;
- logical result schemas;
- structured-output validation behavior;
- phase order and branch bounds;
- check adapter and task inputs; and
- session-freshness policy and terminal outcomes.

- [ ] **Step 1A: Write failing fixture-level runtime parity tests**

With deterministic providers, exercise immediate approval, both correction
routes, required-check failure, `BLOCKED`, and `EXHAUSTED` through `.orc` and
the coordinator. Compare provider invocation bytes, typed inputs/results,
adapter calls, routing events, and terminal outcomes.

- [ ] **Step 1B: Write failing program, profile, and series tests**

Before creating any treatment asset, require:

- task profiles remain estimand-neutral;
- every program owns exactly one estimand, exactly two opaque treatment IDs,
  all treatment-specific assets, and a schema-valid replication-policy digest;
- treatment IDs are `full_review_fix` versus `no_review_fix` for `E2`,
  `orc_runtime` versus `conventional_coordinator` for `E3`, `prompt_a` versus
  `prompt_b` for `E4`, `direct` versus `orc` for `E5`, and `uninterrupted`
  versus `interrupted_then_resumed` for `E6`;
- every program has its own digest-bound `series_lock.v1`, exact profile strata
  and pair count, randomization blocks, and no path or digest shared as another
  program's lock;
- all five programs bind the exact digest of
  `control-replication-v1.json`, whose declared scope explicitly enumerates
  `E2`–`E6`, chooses each program's fixed sample size before its first result,
  forbids denominator extension and cross-estimand pooling, and defines
  estimand-specific eligibility/claim levels;
- each lock becomes immutable at first-result ingestion;
- the `E2` no-review treatment binds an actual bounded topology source, not a
  controller flag;
- `E4` binds both prompt-asset digests while tests assert behavior/contracts,
  never literal prompt wording;
- `E5` binds the predeclared `F1` reference profile, exact E1 prospective
  program/series-lock/terminal-result-index digests, and a treatment-equivalence
  manifest proving both treatment assets and provider/model/effort/tool,
  bounds, and evaluation policies are identical for `F1` and `X1`;
- the `E6` fixture interrupts only after a committed provider boundary, binds
  the resume policy, and excludes product-quality superiority from its claims;
  and
- `X1` binds a source/task, visible checks, evaluator fixtures, clean candidate
  environment, and separate evaluator environment before its outcome is
  visible.

- [ ] **Step 1C: Write failing interruption-controller runtime tests**

Define a declaration-only `run_interruption_control(...)` API. With deterministic
fake processes, require the controller to:

- launch byte-identical uninterrupted and interruption-assigned workflow arms
  through the ordinary pair barrier, with the same workflow/provider policy;
- observe exactly one schema-valid committed-boundary event containing the
  persisted run ID and checkpoint digest from the interruption-assigned arm;
- terminate only that arm's original workflow process group after the event,
  while leaving the control arm uninterrupted;
- wait for descendant quiescence and verify the committed checkpoint remains
  valid;
- invoke exactly once
  `python -m orchestrator resume <same-run-id> --state-dir <same-state-dir>`
  without `--force-restart`;
- preserve program, source, input, control-plane, and root identities;
- prove already committed provider work is not replayed; and
- reject absent/ambiguous boundaries, changed run IDs, nonquiescent process
  trees, invalid checkpoints, fresh-run fallback, or a second resume attempt.

- [ ] **RED: Execute all control-definition tests before implementation**

Create declaration-only coordinator and interruption APIs. Do not create the
treatment assets yet. Run:

```bash
pytest --collect-only -q \
  tests/experiments/test_coordinator_equivalence.py \
  tests/experiments/test_coordinator_runtime_parity.py \
  tests/experiments/test_ablation_programs.py \
  tests/experiments/test_interruption_control.py
pytest -q \
  tests/experiments/test_coordinator_equivalence.py \
  tests/experiments/test_coordinator_runtime_parity.py \
  tests/experiments/test_ablation_programs.py \
  tests/experiments/test_interruption_control.py
```

Expected: collection passes and execution fails first on missing coordinator
behavior or a missing frozen control asset.

- [ ] **Step 2: Implement the smallest conventional coordinator and definitions**

Use the existing provider and adapter APIs. The conventional coordinator must
not add resume, dynamic DAG, or general orchestration abstractions; it exists
only to replay the frozen topology without `.orc` compile/runtime machinery.
The separate `E6` supervisor may invoke the already-supported orchestrator
resume command under its frozen control contract, but does not implement new
resume semantics.

Create the five estimand-owned programs and five separately locked series.
Profiles remain estimand-neutral; `E2`–`E4` and `E6` may reuse eligible
existing task profiles. `E5` binds the freshly frozen `X1` profile plus the
predeclared `F1` reference evidence and treatment-equivalence manifest. The
program, not the profile, owns treatment-specific workflow, coordinator,
prompt, cross-program reference, or interruption assets.

Freeze one schema-valid `control-replication-v1.json` before any control
result. Its scope names `E2`–`E6`, its rules prohibit pooling outcomes or
denominators across estimands, and it requires a separately fixed exact-N
series lock for each program. Bind that same canonical policy digest explicitly
inside every E2–E6 program; sharing the policy never shares a series lock.

Implement `no_review_fix.orc` as the explicit bounded control topology. Freeze
the `E4` prompt-B asset and manifest, the `E6` deterministic interruption
fixture, and the complete `X1` check/evaluator/environment set. Do not create a
generic ablation framework.

Implement `interruption.py` as a narrow `E6` supervisor and add only the
`run-interruption-control` CLI transition. The supervisor launches both frozen
workflow arms through the ordinary pair barrier, watches the interruption
arm's digest-bound committed-boundary event, terminates and quiesces only that
process group, validates its checkpoint and persisted run ID, then executes
this exact argv shape once:

```text
python -m orchestrator resume <run_id> --state-dir <state_dir>
```

It must not use a new run ID, `run`, `--force-restart`, or an implicit retry.
Its terminal `interruption_control.v1` record binds the original and resumed
process identities, event/checkpoint digests, exact resume argv, quiescence
proof, provider-step replay counts, and final run status.

- [ ] **Step 2A: Run GREEN definitions, equivalence, and runtime parity**

```bash
pytest -q \
  tests/experiments/test_coordinator_equivalence.py \
  tests/experiments/test_coordinator_runtime_parity.py \
  tests/experiments/test_ablation_programs.py \
  tests/experiments/test_interruption_control.py
```

Expected: PASS before any provider-backed representation control runs.

- [ ] **Step 2B: Obtain both ordered reviews before evidence work**

One independent reviewer verifies each estimand, treatment contrast, exact
series lock, claim boundary, and X1 neutrality. A second independent reviewer
checks coordinator/runtime parity, fixture determinism, clean environment
bindings, and test sufficiency. Do not launch a control until both approve the
same definition digests.

- [ ] **Step 3: Run the representation control**

Only this matched `.orc` versus coordinator comparison supports conclusions
about `.orc` representation/runtime contribution. Report product quality,
evidence completeness, runtime reliability, authoring burden, and diagnostic
cycles separately.

If any rendered prompt, result contract, provider command/policy, timeout,
schema validation, ordering, or bound is not byte/logically equivalent, label
the result a coordinator-package comparison. Do not use it for a marginal
`.orc` language/runtime claim.

Freeze `e3-orc-vs-coordinator-v1/series-lock.json` with an exact pair count,
then run the ordinary lifecycle with:

```bash
python scripts/experiments/paired_trial.py validate \
  --program experiments/orc_effectiveness/programs/e3-orc-vs-coordinator.json \
  --series-lock experiments/orc_effectiveness/series/e3-orc-vs-coordinator-v1/series-lock.json \
  --evidence-root <external-evidence-root>/e3-orc-vs-coordinator-v1
```

Continue through the Task 12 canonical transition sequence. Do not start the
provider-backed comparison unless `topology_equivalence.v1` validates.

- [ ] **Step 4: Run mechanism ablations as new locked programs**

Run:

- full workflow versus no-review/fix topology;
- selected prompt variants under the same topology;
- a program-owned interruption/resume control separate from product-quality
  claims; and
- transfer replication on `X1` before any general-domain claim.

Select and freeze the unrelated `X1` task/source before viewing its outcomes;
bind it to the `E5` program. Before `X1` launches, bind the canonical
`prospective-v1` E1 program/series-lock/terminal-result-index and `F1` profile
digests. Reject E5 unless a recomputed equivalence manifest proves the two E5
treatments use byte-identical E1 treatment assets, provider/model/effort/tool
policy, bounds, and evaluation policy; only the task-class profile may differ.
This exact reference is chosen by the design and may not be replaced after
viewing `X1`.

Each program carries its exact `estimand_id` (`E2`–`E6`), new definition
digest, separate series lock, and fixed sample size. No lock may be extended
after its first result; additional evidence receives a new program or series
version.

Validate each program/lock pair explicitly:

```bash
python scripts/experiments/paired_trial.py validate \
  --program experiments/orc_effectiveness/programs/e2-review-fix-ablation.json \
  --series-lock experiments/orc_effectiveness/series/e2-review-fix-v1/series-lock.json \
  --evidence-root <external-evidence-root>/e2-review-fix-v1
python scripts/experiments/paired_trial.py validate \
  --program experiments/orc_effectiveness/programs/e4-prompt-variant.json \
  --series-lock experiments/orc_effectiveness/series/e4-prompt-variant-v1/series-lock.json \
  --evidence-root <external-evidence-root>/e4-prompt-variant-v1
python scripts/experiments/paired_trial.py validate \
  --program experiments/orc_effectiveness/programs/e5-transfer.json \
  --series-lock experiments/orc_effectiveness/series/e5-transfer-v1/series-lock.json \
  --evidence-root <external-evidence-root>/e5-transfer-v1
python scripts/experiments/paired_trial.py validate \
  --program experiments/orc_effectiveness/programs/e6-resume.json \
  --series-lock experiments/orc_effectiveness/series/e6-resume-v1/series-lock.json \
  --evidence-root <external-evidence-root>/e6-resume-v1
```

After validation, execute the complete Task 12 transition sequence separately
for `E2`–`E5`. For `E6`, replace only the ordinary `run` transition with the
specialized supervisor, launched in tmux:

```bash
python scripts/experiments/paired_trial.py run-interruption-control \
  --program experiments/orc_effectiveness/programs/e6-resume.json \
  --series-lock experiments/orc_effectiveness/series/e6-resume-v1/series-lock.json \
  --fixture experiments/orc_effectiveness/interruptions/e6-after-committed-boundary.json \
  --state-dir <external-state-root>/e6-resume-v1 \
  --evidence-root <external-evidence-root>/e6-resume-v1
```

The controller internally performs the one exact same-ID resume command above.
Then continue only the applicable freeze/evidence/report transitions. `E6`
reports recovery/reliability evidence and never contributes a product-quality
preference.

- [ ] **Step 5: Run tests and obtain post-evidence reviews**

```bash
pytest --collect-only -q \
  tests/experiments/test_coordinator_equivalence.py \
  tests/experiments/test_coordinator_runtime_parity.py \
  tests/experiments/test_ablation_programs.py \
  tests/experiments/test_interruption_control.py
pytest -q \
  tests/experiments/test_coordinator_equivalence.py \
  tests/experiments/test_coordinator_runtime_parity.py \
  tests/experiments/test_ablation_programs.py \
  tests/experiments/test_interruption_control.py
```

After all five evidence series are terminal, obtain two new independent
reviews. The first checks every evidence record and report claim against its
estimand, lock, chronology, and pre-evidence approved definitions. The second
checks reproducibility, runtime/equivalence evidence, E5 reference bindings,
and E6 same-ID resume proof. The pre-evidence Step 2B reviews do not satisfy
this post-evidence gate.

- [ ] **Step 6: Commit the reviewed implementation and evidence**

```bash
git add \
  orchestrator/experiments/coordinator.py \
  orchestrator/experiments/interruption.py \
  orchestrator/experiments/cli.py \
  orchestrator/experiments/schemas/topology-equivalence-v1.schema.json \
  orchestrator/experiments/schemas/interruption-control-v1.schema.json \
  scripts/experiments/paired_trial.py \
  tests/experiments/test_coordinator_equivalence.py \
  tests/experiments/test_coordinator_runtime_parity.py \
  tests/experiments/test_ablation_programs.py \
  tests/experiments/test_interruption_control.py \
  workflows/experiments/repository_task_loop/no_review_fix.orc \
  experiments/orc_effectiveness/programs \
  experiments/orc_effectiveness/policies/control-replication-v1.json \
  experiments/orc_effectiveness/control_plane/prompt_variants \
  experiments/orc_effectiveness/interruptions \
  experiments/orc_effectiveness/profiles/x1.json \
  experiments/orc_effectiveness/tasks/x1-unrelated-domain.md \
  experiments/orc_effectiveness/checks/x1.json \
  experiments/orc_effectiveness/evaluators/x1.py \
  experiments/orc_effectiveness/evaluators/fixtures/x1 \
  experiments/orc_effectiveness/environments/x1.json \
  experiments/orc_effectiveness/environments/evaluator-x1.json \
  experiments/orc_effectiveness/series/e2-review-fix-v1 \
  experiments/orc_effectiveness/series/e3-orc-vs-coordinator-v1 \
  experiments/orc_effectiveness/series/e4-prompt-variant-v1 \
  experiments/orc_effectiveness/series/e5-transfer-v1 \
  experiments/orc_effectiveness/series/e6-resume-v1 \
  docs/reports/2026-07-23-orc-representation-and-mechanism-controls.md
git commit -m "evidence(experiments): add representation and mechanism controls"
```

## Task 17: Synthesize Consequences And Route Current Documentation

**Files:**

- Create: `docs/reports/2026-07-23-orc-viability-effectiveness-synthesis.md`
- Modify: `docs/index.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `workflows/README.md`
- Modify: `docs/plans/2026-03-05-workflow-demo-design.md`
- Modify: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`
- Modify: `docs/superpowers/specs/2026-07-23-orc-vs-one-shot-experiment-design.md`

- [ ] **Step 1: Generate the authoritative program summary**

Regenerate `program-synthesis.v1` from validated structured records. Separate:

- end-to-end orchestration effectiveness;
- `.orc` viability;
- `.orc` language/runtime contribution;
- authoring and diagnostic ergonomics;
- review/fix topology effect;
- prompt effect;
- task/domain dependence;
- consumer consequences;
- quality/cost Pareto relationships;
- and indeterminate claims.

- [ ] **Step 2: Convert observations into scoped proposals**

Every proposed workflow, prompt, language, runtime, or ergonomics change cites
specific pair/task evidence, its expected mechanism, measured burden, a case
where it could add overhead, and whether the same-topology coordinator avoids
the problem.

Do not implement language changes in this task. Create separate design
requests only for observed recurring gaps.

- [ ] **Step 3: Update documentation truthfully**

Mark the new experiment route implemented only for the stages actually
completed. Retain the March demo as prototype history and link it to the
decision-grade route. Update the capability matrix without promoting an
experimental workflow to stdlib/production authority.

- [ ] **Step 4: Run consistency review**

Use `consistency-quality-pass` to check:

- stage IDs versus estimand IDs;
- schema names versus produced records;
- initial versus integrated review terminology;
- fixed sample and invalid-pair rules;
- control-plane/product boundaries;
- history-free source claims;
- outcome labels;
- and status wording across the design, plan, README, index, matrix, and
  synthesis.

- [ ] **Step 5: Run final verification**

Use tmux for the broad suite:

```bash
pytest --collect-only -q tests/experiments
pytest -q tests/experiments
pytest -q -n 16 --dist=worksteal
python -m orchestrator compile \
  workflows/experiments/repository_task_loop/task_loop.orc \
  --source-root workflows/experiments \
  --entry-workflow repository_task_loop/task_loop::run-task \
  --provider-externs-file experiments/orc_effectiveness/control_plane/providers.json \
  --prompt-externs-file experiments/orc_effectiveness/control_plane/prompts.json \
  --command-boundaries-file experiments/orc_effectiveness/control_plane/commands.json
git diff --check
```

Expected: tests pass, compile exits `0`, and no whitespace errors are reported.
If the broad suite has an external baseline, the final record must give exact
collection/pass/fail/error/skip counts and classify every failure without
weakening verification.

- [ ] **Step 6: Obtain final independent reviews and commit**

One reviewer checks complete conformance to the governing experiment design.
One checks implementation/evidence quality and reproducibility.

```bash
git add \
  docs/reports/2026-07-23-orc-viability-effectiveness-synthesis.md \
  docs/index.md \
  docs/capability_status_matrix.md \
  workflows/README.md \
  docs/plans/2026-03-05-workflow-demo-design.md \
  docs/plans/2026-03-05-demo-scaffold-and-runbook.md \
  docs/superpowers/specs/2026-07-23-orc-vs-one-shot-experiment-design.md
git commit -m "docs(experiments): publish orc effectiveness synthesis"

git status --short
```

Expected: only unrelated pre-existing user changes remain.

## Completion Definition

The roadmap is complete only when:

- `G0` through the gates required for the claims being made have fresh evidence;
- at least one complete realistic direct/`.orc` pair exists;
- the prospective `F1` comparison and balanced `F2` consequence trials are
  complete for any forward-architecture claim;
- the same-topology control is complete for any `.orc`-specific claim;
- hard, initial-soft, integrated-review, consumer, and process evidence remain
  separately inspectable;
- fixed replicate counts and invalid-pair rules were honored;
- all runtime/workflow failures remain visible in the denominator;
- every finding maps to the correct layer without silently redesigning the
  language;
- focused, broad, compile, dry-run, fixture-provider, and real apparatus
  checks have fresh output; and
- both final independent reviews approve.

It is also a valid completion outcome for a locked series to report
`INDETERMINATE`, underpowered, non-discriminating, or `.orc` not viable. The
apparatus exists to learn which conclusion is true, not to guarantee a
workflow win.
