# Adjudicated Provider Step Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create git worktrees; this repo's `AGENTS.md` explicitly forbids them.

**Goal:** Add DSL/runtime support for adjudicated provider steps that run one logical provider step through one or more isolated candidates, score valid candidate outputs with a reusable evaluator prompt, and promote the highest-scoring candidate output into normal workflow artifacts.

**Architecture:** Add a version-gated `adjudicated_provider` execution form in DSL `2.11`. Reuse existing provider prompt composition, provider invocation, output capture, and output-contract validation where possible, but execute candidates in run-owned child workspaces and add a small adjudication runtime module for candidate metadata, score ledgers, evaluator packets, selection, and promotion. Start with artifact-producing steps only; source-edit patch promotion is out of scope.

**Tech Stack:** YAML DSL/specs, Python orchestrator loader and executable IR, provider executor, output-contract validators, state.json/run metadata, JSONL score ledgers, pytest loader/runtime/example smoke tests, workflow library prompt assets.

---

## Implementation Architecture

Implement the feature as six explicit layers, and keep the task sequence aligned
with those boundaries:

1. **DSL and loader contract.** Gate `adjudicated_provider` behind DSL `2.11`.
   Loader validation is structural and must reject workflows that cannot satisfy
   the design contract: missing `evaluator.evidence_confidentiality:
   same_trust_boundary`, invalid evidence limits, stdout-derived step capture
   surfaces, provider sessions, bad prompt-source combinations, missing output
   contracts, and statically detectable ledger/output path collisions.
2. **Frame-scoped adjudication paths and immutable baseline.** Add runtime-owned
   helpers that create one immutable baseline snapshot per execution frame,
   step id, and visit count, then copy every candidate attempt from that
   baseline. The baseline helper owns the fixed copy policy, manifest, null-path
   comparison, local-secret denylist behavior, required-path exclusion failures,
   and baseline preimage records for promotion.
3. **Scorer snapshot, evidence packets, and candidate scoring.** Resolve one
   scorer snapshot before scoring, build complete UTF-8 score-critical evidence
   packets only under the explicit same-trust-boundary attestation, scan packets
   for workflow-declared secret values before persistence, parse evaluator
   stdout as strict JSON, and suppress all stdout-derived adjudicated step state.
4. **Selection, ledger, mirror, and promotion transaction.** Select only from
   output-valid candidates. Materialize normative run-local ledger rows keyed by
   `candidate_run_key` and `score_run_key`, write the workspace-visible mirror
   only at terminal finalization, and promote selected outputs through a staged,
   resume-safe transaction with destination preimage checks, backups, rollback,
   and parent output revalidation before publication.
5. **Deadline, retry, and terminal outcome semantics.** Treat
   `timeout_sec` as one wall-clock deadline for the logical adjudicated step
   visit, and apply the effective provider retry policy independently to each
   candidate provider subprocess and each evaluator subprocess while deadline
   remains. Candidate provider retries must start from fresh baseline copies,
   evaluator retries must reuse the same persisted evaluation packet, terminal
   ledger rows must stay one row per candidate per step visit with attempt
   counts, and every adjudication-specific terminal failure must map to the
   normalized `error.type`, `exit_code`, and `outcome` contract from the design.
6. **Resume and observability.** Reconcile persisted baseline, candidate,
   scorer, packet, ledger, mirror, and promotion state before reusing any prior
   work. Resume must fail with `adjudication_resume_mismatch` when persisted
   state cannot be matched to the current workflow/scorer contract, and reports
   should expose selected candidate, score, ledger paths, promotion status, and
   failure types without making candidate artifacts normal lineage.

Do not collapse these layers into one executor method. `executor.py` should
coordinate the flow; the adjudication module should contain deterministic
helpers with focused unit tests.

## Design Reference

Use the companion design:

- `docs/plans/2026-04-20-adjudicated-provider-step-design.md`

The key constraints from that design are:

- one global score only
- no pass/fail evaluator status
- invalid candidate outputs are ineligible rather than scored
- highest finite score wins, tie-break by candidate order
- candidate work happens in isolated child workspaces
- every candidate attempt starts from the same immutable frame/step/visit
  baseline snapshot and baseline manifest
- selected candidate outputs are promoted into canonical workflow paths
- promotion is a staged transaction with preimage checks, backups, rollback, and
  publish withholding until committed
- downstream steps see ordinary selected artifacts
- evaluator prompt is a reusable library component
- evaluator evidence requires explicit `same_trust_boundary` attestation, complete
  UTF-8 score-critical packets, evidence-limit enforcement, and declared-secret
  scanning before packet persistence
- adjudicated steps do not expose candidate/evaluator stdout as
  `steps.<Step>.output`, `.lines`, or `.json`
- the score ledger row shape, idempotency keys, workspace-visible mirror
  ownership checks, and resume mismatch behavior are normative
- `timeout_sec` is one logical step-visit deadline, candidate/evaluator retries
  share that deadline with fresh candidate retry workspaces and evaluator packet
  reuse, and adjudication-specific terminal failures map to normalized outcomes
- V1 does not support arbitrary source-edit/patch promotion

## File Structure

Specs and docs:

- Modify: `specs/dsl.md` - new `2.11` step form, schema, validation rules, control-flow compatibility.
- Modify: `specs/providers.md` - candidate provider prompt composition and evaluator invocation semantics.
- Modify: `specs/io.md` - candidate-local output validation, selected-output promotion, stdout/stderr/log behavior.
- Modify: `specs/state.md` - persisted adjudication state shape and resume rules.
- Modify: `specs/observability.md` - debug/prompt audit/evaluation ledger visibility.
- Modify: `specs/security.md` - child workspace path safety and candidate isolation limits.
- Modify: `specs/versioning.md` - version gate `2.11`.
- Modify: `specs/acceptance/index.md` - conformance bullets.
- Modify: `docs/workflow_drafting_guide.md` - authoring guidance.
- Modify: `docs/index.md` - index the new design if this repo keeps plan/design index entries current.
- Modify: `workflows/README.md` - index the new example workflow.
- Create: `workflows/library/prompts/adjudication/evaluate_candidate.md` - reusable evaluator prompt.
- Create: `workflows/examples/adjudicated_provider_demo.yaml` - minimal runnable example.

Runtime:

- Modify: `orchestrator/loader.py` - schema validation and `2.11` support.
- Modify: `orchestrator/workflow/surface_ast.py` - surface AST kind/config for adjudicated provider steps.
- Modify: `orchestrator/workflow/executable_ir.py` - executable IR config for adjudicated provider steps.
- Modify: `orchestrator/workflow/elaboration.py` and/or `orchestrator/workflow/lowering.py` - lower surface step into executable node.
- Modify: `orchestrator/workflow/runtime_step.py` - mapping view for adjudicated provider steps.
- Modify: `orchestrator/workflow/executor.py` - dispatch to adjudicated provider execution.
- Create: `orchestrator/workflow/adjudication.py` - frame/visit-scoped paths,
  baseline snapshot manifests, candidate metadata, scorer snapshots, evaluator
  packets, score ledger rows/mirrors, selection, logical deadline/retry helpers,
  terminal outcome mapping, and transactional promotion helpers.
- Modify: `orchestrator/workflow/prompting.py` - factor or expose prompt composition helpers if needed so candidate and evaluator prompts use the same contract as provider steps.
- Modify: `orchestrator/state.py` - helper paths for run-owned candidates and score ledgers if current path helpers are insufficient.
- Modify: `orchestrator/observability/report.py` - include selected candidate and score in reports.

Tests:

- Create: `tests/test_adjudicated_provider_loader.py`
- Create: `tests/test_adjudicated_provider_baseline.py`
- Create: `tests/test_adjudicated_provider_scoring.py`
- Create: `tests/test_adjudicated_provider_runtime.py`
- Create: `tests/test_adjudicated_provider_outcomes.py`
- Create: `tests/test_adjudicated_provider_promotion.py`
- Modify: `tests/test_workflow_examples_v0.py` or existing example registry to include the demo.

## Task 1: Update Normative Specs First

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/providers.md`
- Modify: `specs/io.md`
- Modify: `specs/state.md`
- Modify: `specs/observability.md`
- Modify: `specs/security.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`

- [x] **Step 1: Add DSL `2.11` to the schema docs**

Update `specs/dsl.md` to list `2.11` as a supported version and define `adjudicated_provider` as a mutually exclusive execution form.

Document the minimal shape:

```yaml
adjudicated_provider:
  candidates:
    - id: codex_high
      provider: codex
      provider_params:
        model: gpt-5.4
        effort: high
  evaluator:
    provider: claude
    asset_file: prompts/adjudication/evaluate_candidate.md
    evidence_confidentiality: same_trust_boundary
  selection:
    tie_break: candidate_order
  score_ledger_path: artifacts/evaluations/example.candidate_scores.jsonl
```

- [x] **Step 2: Document validation rules**

Add rules covering:

- non-empty unique candidate ids
- candidate/evaluator providers must exist
- step must declare `expected_outputs` or `output_bundle`
- step must declare exactly one base prompt source unless every candidate
  declares a prompt override
- `provider_session` invalid with `adjudicated_provider`
- `output_file`, `output_capture`, and `allow_parse_error` invalid with
  `adjudicated_provider` in V1
- candidate prompt override may use only one of `asset_file` or `input_file`
- candidate prompt overrides may not define `consumes`, `depends_on`,
  `publishes`, `expected_outputs`, `output_bundle`, or `output_file`
- evaluator prompt source may use only one of `asset_file` or `input_file`
- evaluator rubric source may use only one of `rubric_asset_file` or
  `rubric_input_file`
- evaluator `evidence_confidentiality` is required and must be the literal
  `same_trust_boundary`
- evaluator `evidence_limits`, when present, may only contain literal positive
  integer `max_item_bytes` and `max_packet_bytes`, with packet bytes greater than
  or equal to item bytes
- `selection.tie_break` must be `candidate_order` when present, and
  `selection.require_score_for_single_candidate` must be boolean when present
- `score_ledger_path` must be under `artifacts/`
- statically known ledger/output path collisions fail validation
- adjudicated candidate-managed paths that depend on `${run.root}` or name the
  parent run root fail validation
- evaluator score must be finite float in `[0.0, 1.0]`

- [x] **Step 3: Document provider/evaluator prompt composition**

In `specs/providers.md`, state that candidate prompts use ordinary provider prompt composition with the step prompt unless the candidate supplies a prompt override. The evaluator prompt receives a runtime-built evaluation packet plus the reusable evaluator prompt, and its output is strict JSON independent of the step's `output_capture`.

Also document that evaluator scoring uses the persisted scorer snapshot and
complete embedded score-critical evidence only. Evaluator providers must not
depend on reading candidate or parent workspace files, bounded prompt previews,
candidate stdout/stderr, or transport logs.

- [x] **Step 4: Document IO and promotion semantics**

In `specs/io.md`, document candidate workspace output validation and selected-output promotion rules for:

- non-relpath `expected_outputs`
- relpath `expected_outputs` with `must_exist_target`
- `output_bundle`
- relpath bundle fields with `must_exist_target`

Specify the promotion transaction states and failure handling: manifest
preparation, staging, duplicate destination rejection, baseline/current parent
preimage checks, same-filesystem temp-file replacement, backup/tombstone
rollback, parent output revalidation, publish withholding until committed, and
resume behavior for `prepared`, `committing`, `rolling_back`, `failed`, and
`committed` manifests.

- [x] **Step 5: Document state, observability, security, and acceptance**

Update the remaining specs with:

- `steps.<Step>.adjudication` state shape and the fact that stdout-derived
  `output`, `lines`, `json`, `truncated`, and parse-error state are absent
- run-local score ledger paths, workspace-visible mirror ownership checks,
  mirror atomic materialization, mirror conflict errors, and mirror publish
  withholding
- `candidate_run_key`, `score_run_key`, scorer snapshot, scorer-unavailable
  metadata, evaluation packet hash, and row-shape requirements
- logical `timeout_sec` deadline semantics, candidate/evaluator retry scope,
  fresh candidate retry workspace copies, evaluator packet reuse across evaluator
  retries, one ledger row per candidate visit with attempt counts, and the
  normalized terminal `error.type` / `exit_code` / `outcome` mapping
- resume mismatch rules for missing baseline, changed candidate config, changed
  scorer identity, scorer-unavailable transitions, missing scorer snapshot, and
  interrupted promotion or ledger materialization
- candidate child-workspace isolation limits, fixed baseline copy policy,
  local-secret denylist, symlink handling, and required-path exclusion failures
- confidentiality and retention warnings for baseline snapshots, candidate
  workspaces, composed prompts, packets, ledgers, logs, and promotion staging
- acceptance bullets for evidence attestation/limits/secret detection, immutable
  baseline reuse, promotion conflicts/rollback, ledger mirror ownership, and
  resume idempotency

- [x] **Step 6: Inspect the edited docs**

Run:

```bash
sed -n '1,260p' specs/dsl.md
sed -n '1,220p' specs/providers.md
sed -n '1,220p' specs/io.md
```

Expected: the new surface is described consistently and does not imply source-edit patch promotion.

- [ ] **Step 7: Commit docs/specs**

```bash
git add specs/dsl.md specs/providers.md specs/io.md specs/state.md specs/observability.md specs/security.md specs/versioning.md specs/acceptance/index.md
git commit -m "docs: define adjudicated provider steps"
```

## Task 2: Add Loader Tests For The New Surface

**Files:**
- Create: `tests/test_adjudicated_provider_loader.py`
- Modify: `orchestrator/loader.py`

- [x] **Step 1: Write failing tests for valid minimal adjudicated step**

Create a workflow fixture in the test with:

```yaml
version: "2.11"
name: adjudicated-loader-valid
providers:
  fake:
    command: ["python", "-c", "print('ok')"]
steps:
  - name: Draft
    id: draft
    adjudicated_provider:
      candidates:
        - id: fake_a
          provider: fake
      evaluator:
        provider: fake
        input_file: evaluator.md
        evidence_confidentiality: same_trust_boundary
    input_file: prompt.md
    expected_outputs:
      - name: result
        path: state/result.txt
        type: string
```

Assert loader validation succeeds.

- [x] **Step 2: Write failing tests for version gate and exclusivity**

Cover:

- `version: "2.10"` with `adjudicated_provider` fails
- step with both `provider` and `adjudicated_provider` fails
- step with `command` and `adjudicated_provider` fails
- step with `provider_session` and `adjudicated_provider` fails

- [x] **Step 3: Write failing tests for candidate validation**

Cover:

- empty candidates list
- duplicate candidate ids
- unknown candidate provider
- candidate prompt override with both `asset_file` and `input_file`
- candidate with forbidden `consumes`, `depends_on`, `publishes`,
  `expected_outputs`, `output_bundle`, or `output_file`
- missing step base prompt when not every candidate declares `asset_file` or
  `input_file`
- all candidates declare prompt overrides and the step base prompt is omitted

- [x] **Step 4: Write failing tests for evaluator validation**

Cover:

- missing evaluator provider
- unknown evaluator provider
- evaluator with both `asset_file` and `input_file`
- evaluator rubric with both `rubric_asset_file` and `rubric_input_file`
- missing `evidence_confidentiality`
- `evidence_confidentiality` value other than `same_trust_boundary`
- evidence limits with unknown keys, non-integer values, zero/negative values,
  substitution strings, or `max_packet_bytes < max_item_bytes`
- missing step output contract
- both `expected_outputs` and `output_bundle`
- step-level `output_file`, `output_capture`, or `allow_parse_error`
- invalid `selection.tie_break`
- non-boolean `selection.require_score_for_single_candidate`
- score ledger outside `artifacts/`
- static score-ledger collision with an `expected_outputs.path`, `output_bundle.path`,
  or published relpath artifact pointer path
- candidate-managed `input_file`, `depends_on`, `consume_bundle.path`, or output
  path that depends on `${run.root}` or resolves into the parent run root

- [x] **Step 5: Run tests to confirm they fail**

```bash
pytest tests/test_adjudicated_provider_loader.py -q
```

Expected: failures showing `adjudicated_provider` is unknown or unsupported.

- [ ] **Step 6: Commit failing tests**

```bash
git add tests/test_adjudicated_provider_loader.py
git commit -m "test: pin adjudicated provider loader contract"
```

## Task 3: Implement Loader And IR Support

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/runtime_step.py`

- [x] **Step 1: Add `2.11` to supported versions**

In `orchestrator/loader.py`, add `2.11` to `SUPPORTED_VERSIONS`.

- [x] **Step 2: Add surface and IR step kinds**

Add `ADJUDICATED_PROVIDER = "adjudicated_provider"` to `SurfaceStepKind` and the executable node kind/config equivalents.

- [x] **Step 3: Add surface config fields**

Store the raw `adjudicated_provider` mapping on `SurfaceStep`, similar to `provider` and `provider_params`.

- [x] **Step 4: Validate adjudicated provider blocks**

Add `_validate_adjudicated_provider(...)` in `orchestrator/loader.py`. Keep validation structural; do not evaluate prompt text.

This validator must implement the full loader/schema rules from Task 1,
including evidence confidentiality, evidence limits, stdout-surface rejection,
rubric source exclusivity, base-prompt inheritance, static ledger collisions, and
the first-release `${run.root}` restriction for candidate-managed paths.

- [x] **Step 5: Update exclusivity logic**

Include `adjudicated_provider` in the execution-field mutual exclusion checks, `wait_for` conflicts, and structured-step lowering checks where provider is currently considered.

- [x] **Step 6: Lower to executable IR**

Preserve the config through elaboration/lowering so runtime steps expose:

```python
step["adjudicated_provider"]
step["input_file"] or step["asset_file"]
step["expected_outputs"] or step["output_bundle"]
```

- [x] **Step 7: Run loader tests**

```bash
pytest tests/test_adjudicated_provider_loader.py -q
```

Expected: pass.

- [x] **Step 8: Run collect-only for touched test module**

```bash
pytest --collect-only tests/test_adjudicated_provider_loader.py -q
```

Expected: all new tests collect.

- [ ] **Step 9: Commit loader support**

```bash
git add orchestrator/loader.py orchestrator/workflow/surface_ast.py orchestrator/workflow/executable_ir.py orchestrator/workflow/elaboration.py orchestrator/workflow/lowering.py orchestrator/workflow/runtime_step.py tests/test_adjudicated_provider_loader.py
git commit -m "feat: validate adjudicated provider steps"
```

## Task 4: Add Baseline, Candidate Workspace, And Promotion Transaction Helpers

**Files:**
- Create: `orchestrator/workflow/adjudication.py`
- Create: `tests/test_adjudicated_provider_baseline.py`
- Create: `tests/test_adjudicated_provider_promotion.py`
- Modify: `orchestrator/state.py` if path helpers belong there

- [x] **Step 1: Write failing unit tests for frame/visit-scoped paths**

Test that a helper builds paths like:

```text
.orchestrate/runs/run-1/adjudication/root/root.draft/1/baseline/workspace
.orchestrate/runs/run-1/adjudication/root/root.draft/1/candidate_scores.jsonl
.orchestrate/runs/run-1/candidates/root/root.draft/1/fake_a/workspace
.orchestrate/runs/run-1/candidates/root/root.draft/1/fake_a/evaluation_packet.json
.orchestrate/runs/run-1/promotions/root/root.draft/1/manifest.json
```

Assert `frame_scope`, `step_id`, `visit_count`, and `candidate_id` are path-safe.
Reject ids that would escape paths or collide after normalization.

- [x] **Step 2: Write failing unit tests for immutable baseline copy policy**

Create a parent workspace with ordinary files plus excluded roots and paths:

```text
.orchestrate/runs/old/state.json
.git/config
node_modules/pkg/index.js
__pycache__/x.pyc
.env
.env.example
docs/source.md
state/input.txt
relative-ok-symlink -> docs/source.md
absolute-bad-symlink -> /tmp/outside
escaping-bad-symlink -> ../outside
```

Assert baseline creation:

- copies ordinary files, `.env.example`, and safe relative symlinks
- excludes `.orchestrate/`, `.git/`, dependency/cache roots, local-secret
  denylist files, absolute symlinks, escaping symlinks, broken symlinks, and
  excluded-target symlinks
- writes a deterministic manifest with copy policy version, local-secret
  denylist version, included entries, excluded entries with reason codes, and
  `baseline_digest`
- does not honor `.gitignore`

- [x] **Step 3: Write failing unit tests for required path null-path comparison**

Model `input_file`, plain `depends_on`, `consume_bundle.path`, materialized
consume pointer files, and declared output value-file destinations. Assert a
required orchestrator-managed path that existed in the parent but was excluded
by the fixed baseline policy fails before provider launch with a
baseline-excluded failure type. Assert optional excluded paths are recorded as
absent rather than copied or redacted.

- [x] **Step 4: Write failing unit tests for baseline destination preimages**

Assert promotion destination preimages are recorded as:

- `file` with SHA-256 hash and mode metadata
- `absent`
- `unavailable` for paths that cross excluded roots, escaping symlinks,
  directories-as-files, absolute paths, broken symlinks, or other unresolvable
  states

Assert `unavailable` is a promotion conflict.

- [x] **Step 5: Write failing unit tests for relpath promotion transaction**

Set up:

```text
candidate/workspace/state/design_path.txt -> docs/plans/demo-design.md
candidate/workspace/docs/plans/demo-design.md
```

Run promotion for an expected output spec with `type: relpath` and
`must_exist_target: true`. Assert both the pointer file and target document are
staged, copied to the parent workspace, parent output validation runs after
commit, the manifest reaches `committed`, and normal publication is still a
separate executor responsibility.

- [x] **Step 6: Write failing unit tests for output bundle promotion transaction**

Set up a bundle JSON with a relpath field and a target file. Assert promotion
stages and commits the bundle plus the relpath target.

- [x] **Step 7: Write failing unit tests for promotion conflicts and rollback**

Cover:

- destination changed from the baseline preimage before staging
- destination changed between staging and commit
- existing directory at a file destination
- duplicate destination paths with different source hashes or roles
- parent output validation failure after commit triggers rollback of only files
  touched by this transaction
- rollback restores file backups, deletes absent-baseline tombstones, removes
  only manifest-created empty parent directories, and fails with
  `promotion_rollback_conflict` if a touched destination no longer matches the
  staged source or baseline preimage

- [x] **Step 8: Write failing unit tests for promotion resume states**

Create manifest fixtures for `prepared`, `committing`, `rolling_back`, `failed`,
and `committed`. Assert resume repeats safe preimage checks, treats destinations
already matching staged sources as committed, completes rollback when needed,
returns recorded failures without publication, and revalidates canonical parent
outputs for committed manifests.

- [x] **Step 9: Implement adjudication path helpers**

In `orchestrator/workflow/adjudication.py`, add small dataclasses and helpers:

```python
@dataclass(frozen=True)
class AdjudicationVisitPaths:
    adjudication_root: Path
    baseline_root: Path
    baseline_workspace: Path
    baseline_manifest_path: Path
    run_score_ledger_path: Path
    scorer_root: Path
    promotion_manifest_path: Path

@dataclass(frozen=True)
class CandidateRuntimePaths:
    candidate_root: Path
    workspace: Path
    stdout_log: Path
    stderr_log: Path
    prompt_path: Path
    evaluation_packet_path: Path
    evaluation_output_path: Path

def adjudication_visit_paths(run_root: Path, frame_scope: str, step_id: str, visit_count: int) -> AdjudicationVisitPaths:
    ...

def candidate_paths(run_root: Path, frame_scope: str, step_id: str, visit_count: int, candidate_id: str) -> CandidateRuntimePaths:
    ...
```

- [x] **Step 10: Implement baseline snapshot helpers**

Add helpers that create and validate the immutable baseline:

```python
def create_baseline_snapshot(
    *,
    parent_workspace: Path,
    run_root: Path,
    visit_paths: AdjudicationVisitPaths,
    workflow_checksum: str,
    resolved_consumes: Mapping[str, Any],
    required_path_surfaces: Sequence[PathSurface],
    optional_path_surfaces: Sequence[PathSurface],
) -> BaselineManifest:
    ...

def prepare_candidate_workspace_from_baseline(
    *,
    baseline_workspace: Path,
    candidate_workspace: Path,
) -> None:
    ...
```

Implement fixed policy `adjudicated_provider.baseline_copy.v1`, local-secret
denylist recording, safe relative symlink preservation, required-path
exclusion failures, null-path comparison, and deterministic manifest digesting.
Keep this copy-backed; do not use git worktrees.

- [x] **Step 11: Implement transactional promotion helpers**

Add:

```python
def promote_candidate_outputs(
    *,
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    candidate_workspace: Path,
    parent_workspace: Path,
    baseline_manifest: BaselineManifest,
    promotion_manifest_path: Path,
) -> None:
    ...
```

Use existing output-contract shapes. Copy only declared output files and
referenced relpath targets with `must_exist_target`, but do it through the
manifest/staging transaction from the design: source hashing, duplicate
destination checks, baseline/current parent preimage comparison, staging
validation, atomic per-file replacement, backups/tombstones, rollback, manifest
state transitions, and resume entrypoints.

- [x] **Step 12: Run baseline and promotion tests**

```bash
pytest tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py -q
```

Expected: pass.

- [x] **Step 13: Run collect-only for new helper tests**

```bash
pytest --collect-only tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py -q
```

Expected: all new tests collect.

- [ ] **Step 14: Commit helpers**

```bash
git add orchestrator/workflow/adjudication.py orchestrator/state.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py
git commit -m "feat: add adjudicated baseline and promotion helpers"
```

## Task 5: Add Evidence, Scorer Snapshot, Selection, And Ledger Helpers

**Files:**
- Create: `tests/test_adjudicated_provider_scoring.py`
- Modify: `orchestrator/workflow/adjudication.py`
- Modify: `orchestrator/workflow/prompting.py` if prompt composition must expose
  exact rendered candidate prompt content and output-contract suffix hashes

- [x] **Step 1: Write failing unit tests for scorer snapshot identity**

Assert scorer resolution stores evaluator provider, substituted provider params,
base evaluator prompt content/hash, optional rubric content/hash, evaluator JSON
contract version, evaluation packet schema version, evidence limits,
`evidence_confidentiality`, secret-detection policy version, and
`scorer_identity_hash`.

Assert changing evaluator params, evaluator prompt content, rubric content,
evidence limits, evidence confidentiality policy, or secret-detection policy
changes `scorer_identity_hash`.

- [ ] **Step 2: Write failing unit tests for scorer-unavailable metadata**

Assert missing evaluator provider, missing evaluator prompt, unreadable rubric,
or provider-param substitution failure records normalized
`scorer_resolution_failure_key` metadata without building packets. Assert
output-valid candidates get `score_status: "scorer_unavailable"` and invalid
candidates remain `score_status: "not_evaluated"`.

- [x] **Step 3: Write failing unit tests for complete evidence packet construction**

Build a candidate with a rendered prompt, expected-output value files, required
relpath targets, injected consume relpath target content, an optional rubric, and
an output bundle variant. Assert the packet embeds complete UTF-8 score-critical
evidence, hashes every item, records byte sizes and read status, excludes
candidate/evaluator stdout/stderr and bounded previews, and computes
`evaluation_packet_hash`.

- [x] **Step 4: Write failing unit tests for evidence rejection**

Cover:

- score-critical item exceeds `max_item_bytes`
- total packet exceeds `max_packet_bytes`
- score-critical item is non-UTF-8 or binary
- score-critical item cannot be read
- score-critical item contains a non-empty workflow-declared secret value

Assert packet persistence and evaluator launch are skipped, the failure type is
specific (`secret_detected_in_score_evidence` for declared secret values), and
selection rules later treat the candidate as unscored.

- [x] **Step 5: Write failing unit tests for evaluator JSON parsing**

Assert evaluator stdout must be strict JSON with matching `candidate_id`, finite
numeric `score` in `[0.0, 1.0]`, and non-empty `summary`. Reject NaN, infinity,
strings for score, out-of-range scores, candidate mismatch, empty summaries,
arrays, trailing text, and parse errors.

- [x] **Step 6: Write failing unit tests for selection rules**

Cover:

- no output-valid candidates fails with `adjudication_no_valid_candidates`
- one output-valid candidate with `require_score_for_single_candidate: false`
  selects by `single_candidate_contract_valid` even when scorer resolution or
  evaluation fails
- one output-valid candidate with `require_score_for_single_candidate: true`
  fails closed without a valid score
- multi-candidate scorer resolution failure fails with
  `adjudication_scorer_unavailable`
- multi-candidate partial scoring fails with
  `adjudication_partial_scoring_failed`
- highest finite score wins and ties use declared candidate order

- [x] **Step 7: Write failing unit tests for normative ledger row shape and keys**

Assert one row is generated per candidate, including prompt/contract failures.
Rows must include required fields from the design, nullable fields must match
`score_status`, and `candidate_run_key`/`score_run_key` must change when their
identity inputs change. Assert duplicate `score_run_key` rows are suppressed
during regeneration.

- [ ] **Step 8: Write failing unit tests for workspace-visible ledger mirror**

Cover:

- `score_ledger_path` is substituted in the current frame, path-checked under
  parent workspace, and must stay under `artifacts/`
- dynamic collisions with required relpath targets, selected promotion
  destinations, or published relpath artifact pointer paths fail with
  `ledger_path_collision`
- existing non-empty mirrors are replaceable only when every JSONL row has the
  same owner tuple: `row_schema`, `run_id`, `execution_frame_id`, `step_id`, and
  `visit_count`
- invalid JSONL, missing ownership fields, different schema/run/frame/step/visit,
  or two step visits sharing one mirror path fail with `ledger_conflict`
- mirror materialization is atomic and only occurs at terminal finalization, not
  while promotion is pending

- [x] **Step 9: Implement scoring, selection, and ledger helpers**

Add deterministic helpers in `orchestrator/workflow/adjudication.py` for scorer
snapshot persistence, scorer-unavailable metadata, evidence packet construction,
secret scanning, evaluator JSON parsing, selection, ledger row generation,
run-local ledger regeneration, dynamic ledger collision checks, and atomic mirror
materialization.

- [x] **Step 10: Run scoring tests**

```bash
pytest tests/test_adjudicated_provider_scoring.py -q
```

Expected: pass.

- [x] **Step 11: Run collect-only for scoring tests**

```bash
pytest --collect-only tests/test_adjudicated_provider_scoring.py -q
```

Expected: all new tests collect.

- [ ] **Step 12: Commit scoring helpers**

```bash
git add orchestrator/workflow/adjudication.py orchestrator/workflow/prompting.py tests/test_adjudicated_provider_scoring.py
git commit -m "feat: add adjudicated scoring and ledger helpers"
```

## Task 6: Add Runtime Execution With Mocked Providers

**Files:**
- Create: `tests/test_adjudicated_provider_runtime.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/prompting.py` if prompt composition must be factored
- Modify: `orchestrator/observability/report.py` if runtime reports need new fields immediately

- [x] **Step 1: Write failing runtime test for two valid candidates**

Use a mocked `ProviderExecutor.execute` that writes different candidate outputs
based on the provider/candidate invocation and returns successful stdout.

Use a mocked evaluator provider that returns:

```json
{"candidate_id": "a", "score": 0.4, "summary": "Weaker"}
{"candidate_id": "b", "score": 0.9, "summary": "Better"}
```

Assert candidate `b` is promoted and published.

- [ ] **Step 2: Write failing runtime test for single-candidate scoring**

Assert one candidate still runs evaluator, writes a ledger row, and promotes.

Add variants where scorer resolution fails and where evaluation fails. With
`require_score_for_single_candidate: false`, assert the output-valid candidate
is promoted with `selected_score: null`, a ledger row records
`score_status: "scorer_unavailable"` or `"evaluation_failed"`, and publication
still occurs after terminal ledger finalization. With
`require_score_for_single_candidate: true`, assert the same failures block
promotion.

- [ ] **Step 3: Write failing runtime test for invalid candidate exclusion**

Candidate `a` omits required output. Candidate `b` produces valid output.
Assert only `b` is evaluated and selected, and `a` appears in the adjudication
state as `contract_failed`.

- [x] **Step 4: Write failing runtime test for multi-candidate partial scoring**

Two candidates produce valid outputs. Make one evaluator return invalid JSON or
fail evidence construction. Assert the step fails with
`adjudication_partial_scoring_failed`, no promotion happens, no normal artifacts
are published, and ledger rows identify the scored and unscored candidates.

- [ ] **Step 5: Write failing runtime test for stdout suppression**

Make candidate and evaluator providers print valid-looking JSON/text to stdout.
Assert stdout/stderr are stored only in runtime-owned logs and the completed
adjudicated step result does not populate `output`, `lines`, `json`,
`truncated`, or `debug.json_parse_error`.

- [x] **Step 6: Write failing runtime test for tie-break**

Two candidates receive the same score. Assert the earlier declared candidate is
selected.

- [x] **Step 7: Extract provider prompt composition helper if needed**

`WorkflowExecutor._execute_provider_with_context` currently composes prompt text
and immediately invokes the provider. Extract a private helper such as:

```python
def _compose_provider_prompt_for_step(self, step, context, state, *, output_contract_step=None) -> tuple[str | None, dict | None]:
    ...
```

Keep ordinary provider-step behavior unchanged.

- [x] **Step 8: Implement `_execute_adjudicated_provider_with_context`**

In `orchestrator/workflow/executor.py`, add a runtime path that:

1. resolves canonical output contract paths
2. runs consume preflight once in the current execution frame
3. creates or reuses the immutable baseline snapshot
4. prepares each candidate workspace from the baseline
5. composes candidate prompts, including prompt overrides and output-contract
   suffixes, with candidate workspace path authority
6. prepares provider invocations with each candidate provider/params
7. executes provider invocations with `cwd=candidate_workspace`
8. captures candidate stdout/stderr to candidate logs only
9. validates candidate outputs with `workspace=candidate_workspace`
10. resolves scorer snapshot or scorer-unavailable metadata
11. builds evaluator packets only for output-valid candidates with complete
    score-critical evidence
12. runs evaluator provider with evaluator CWD and parses strict JSON
13. computes selection or terminal adjudication failure
14. writes run-local ledger rows after selection/failure state is known
15. checks dynamic ledger collisions
16. promotes selected outputs through the transaction helper
17. regenerates terminal run-local ledger and materializes the mirror if
    configured
18. revalidates canonical parent output contract
19. withholds `publishes` until promotion committed and mirror finalization has
    succeeded
20. returns a normal step result with selected artifacts plus an `adjudication`
    state block

- [x] **Step 9: Add dispatch paths**

Update top-level and nested execution dispatch so `adjudicated_provider` works
where provider steps currently work, except with `provider_session` rejected.

- [x] **Step 10: Run runtime tests**

```bash
pytest tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_scoring.py -q
```

Expected: pass.

- [ ] **Step 11: Commit runtime support**

```bash
git add orchestrator/workflow/executor.py orchestrator/workflow/prompting.py orchestrator/workflow/adjudication.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_scoring.py
git commit -m "feat: execute adjudicated provider candidates"
```

## Task 7: Add Deadline, Retry, And Outcome Semantics

**Files:**
- Create: `tests/test_adjudicated_provider_outcomes.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/adjudication.py`
- Modify: `orchestrator/exec/retry.py` only if a small reusable remaining-deadline helper belongs there
- Modify: `orchestrator/state.py` only if normalized outcome helpers need shared state support

- [ ] **Step 1: Write failing tests for one logical step deadline**

Use a fake monotonic clock or patched deadline helper so the tests do not sleep.
Cover a step with `timeout_sec` where baseline creation, candidate copies,
candidate subprocesses, evaluator subprocesses, retry delays, selection, ledger
materialization, promotion, and final parent validation share one deadline that
starts after `when` and consume preflight succeed.

Assert candidate and evaluator provider invocations receive only the remaining
deadline as their `timeout_sec`. The full step timeout must not restart per
candidate, per evaluator, or per retry attempt. If the deadline expires between
runtime-owned phases, assert the runtime starts no new candidate, evaluator,
ledger mirror, or promotion operation and the step fails with `error.type:
"timeout"`, `exit_code: 124`, and `outcome` class `timeout` with
`retryable: true`.

- [ ] **Step 2: Write failing tests for candidate retry scope**

Create a two-attempt candidate where the first provider attempt exits with `1`
or `124` after writing partial files, and the second attempt succeeds. Set:

```yaml
retries:
  max: 1
  delay_ms: 10
```

Assert retries apply to that candidate provider subprocess only; the whole
adjudicated step visit is not restarted, other candidates are not rerun, and the
step visit count does not increment. Assert every candidate provider retry
starts from a fresh copy of the immutable baseline, so partial files from the
failed attempt are absent in the successful attempt workspace. Assert terminal
candidate metadata records both attempt summaries, and the ledger still emits one
row for that candidate visit with `attempt_count: 2`.

- [ ] **Step 3: Write failing tests for evaluator retry scope**

Use one output-valid candidate and an evaluator that fails or times out once,
then succeeds. Assert evaluator retries reuse the same persisted
`evaluation_packet_hash`, do not rerun the candidate provider, and record
evaluator attempt metadata while keeping one ledger row for the candidate visit.

Add exhausted-evaluator variants:

- single valid candidate with `require_score_for_single_candidate: false`
  promotes with `selected_score: null` and `score_status:
  "evaluation_failed"`
- single valid candidate with `require_score_for_single_candidate: true` fails
  with `adjudication_partial_scoring_failed`
- multiple output-valid candidates fail with `adjudication_partial_scoring_failed`
  and no promotion

- [ ] **Step 4: Write failing tests for non-retried terminal failures**

Set `retries.max` on the adjudicated step and force each terminal runtime
failure below. Assert the runtime does not rerun candidates or evaluators after
the failure is known:

- dynamic `ledger_path_collision`
- workspace-visible `ledger_conflict`
- `ledger_mirror_failed`
- `promotion_conflict`
- `promotion_validation_failed`
- `promotion_rollback_conflict`

Do not full-smoke resume mismatch here; Task 9 owns resume reconciliation. This
task should only pin the non-retryable terminal mapping for
`adjudication_resume_mismatch` through the shared outcome helper.

- [x] **Step 5: Write failing tests for normalized terminal outcome mapping**

Add direct helper tests or runtime tests for the design's terminal outcome
matrix. Cover:

- success: `status: "completed"`, `exit_code: 0`, outcome phase/class
  `completed`, `retryable: false`
- `adjudication_no_valid_candidates`
- `adjudication_scorer_unavailable`
- `adjudication_partial_scoring_failed`
- `timeout`
- `ledger_path_collision`
- `ledger_conflict`
- `ledger_mirror_failed`
- `promotion_conflict`
- `promotion_validation_failed`
- `promotion_rollback_conflict`
- `adjudication_resume_mismatch`

Assert each failure writes the expected primary `error.type`, `exit_code`,
`outcome.phase`, `outcome.class`, and `outcome.retryable` without exposing
candidate/evaluator stdout-derived `output`, `lines`, or `json` state.

- [x] **Step 6: Implement adjudication deadline and retry helpers**

In `orchestrator/workflow/adjudication.py`, add focused helpers such as:

```python
@dataclass(frozen=True)
class AdjudicationDeadline:
    started_monotonic: float
    timeout_sec: float | None

    def remaining_timeout_sec(self, now: float) -> float | None:
        ...

    def require_time_remaining(self, phase: str, now: float) -> None:
        ...
```

Use these helpers from `WorkflowExecutor._execute_adjudicated_provider_with_context`
before every runtime-owned phase and when preparing provider invocations. Reuse
the existing provider timeout behavior for subprocess termination, but pass the
remaining logical budget instead of the original step timeout.

- [ ] **Step 7: Implement candidate and evaluator retry loops**

Resolve the effective provider retry policy once for the adjudicated step, using
the same precedence ordinary provider steps use for step `retries` and executor
defaults. Apply that policy independently to:

- each candidate provider subprocess
- each evaluator subprocess for an output-valid candidate

For candidate retries, recreate the candidate attempt workspace from the
immutable baseline before each attempt. For evaluator retries, reuse the same
persisted evaluation packet and never rerun candidate generation. Honor
`delay_ms` only while the logical deadline still has enough remaining time; if
the delay would cross the deadline, fail with the normalized timeout outcome.

- [x] **Step 8: Implement normalized adjudication outcomes**

Add a small mapping from adjudication terminal condition to primary
`error.type`, `exit_code`, and normalized `outcome`. Keep candidate-level
provider/evaluator exits in candidate metadata and ledger rows; the logical step
result exposes only the primary adjudicated terminal condition. Ensure retry
logic does not handle promotion, ledger, mirror, parent-validation, or resume
mismatch failures as retryable subprocess failures.

- [x] **Step 9: Run outcome tests**

```bash
pytest tests/test_adjudicated_provider_outcomes.py tests/test_adjudicated_provider_runtime.py -q
```

Expected: pass.

- [x] **Step 10: Run collect-only for outcome tests**

```bash
pytest --collect-only tests/test_adjudicated_provider_outcomes.py -q
```

Expected: all new tests collect.

- [ ] **Step 11: Commit deadline, retry, and outcome support**

```bash
git add orchestrator/workflow/executor.py orchestrator/workflow/adjudication.py orchestrator/exec/retry.py orchestrator/state.py tests/test_adjudicated_provider_outcomes.py tests/test_adjudicated_provider_runtime.py
git commit -m "feat: pin adjudicated provider outcomes"
```

## Task 8: Add Library Evaluator Prompt And Example Workflow

**Files:**
- Create: `workflows/library/prompts/adjudication/evaluate_candidate.md`
- Create: `workflows/examples/adjudicated_provider_demo.yaml`
- Modify: `tests/test_workflow_examples_v0.py`
- Modify: `workflows/README.md`

- [x] **Step 1: Write the reusable evaluator prompt**

Create `workflows/library/prompts/adjudication/evaluate_candidate.md` with a
generic task:

```md
Review the candidate artifact described in the evaluation packet.

Score the candidate as a single global value from 0.0 to 1.0 based on how well
it satisfies the original task, consumed artifacts, and output contract.

Do not use pass/fail categories. Do not prefer verbosity for its own sake.
Write strict JSON with candidate_id, score, and summary.
```

Keep the prompt generic. Do not mention EasySpin or major-project tranches.

- [x] **Step 2: Add a minimal example workflow**

Create `workflows/examples/adjudicated_provider_demo.yaml` using local/mockable
providers that can be patched in tests. It should run one adjudicated provider
step that writes a simple document artifact, evaluates two candidates, and
publishes the selected output. Include `evaluator.evidence_confidentiality:
same_trust_boundary`, an `artifacts/` score ledger mirror path, and only
artifact-based downstream dataflow.

- [x] **Step 3: Add mocked-provider example smoke test**

Update the example test registry or add a focused test that executes the demo
with provider executor patched. Assert:

- two candidate rows exist in the score ledger
- ledger rows have owner tuple fields, stable `candidate_run_key` and
  `score_run_key`, evaluator identity fields, score status, selection reason, and
  terminal promotion status
- the workspace-visible ledger mirror is materialized only after terminal
  finalization
- selected candidate output was promoted
- downstream workflow output reads the selected artifact

- [x] **Step 4: Update workflow index**

Add the example to `workflows/README.md`.

- [x] **Step 5: Run example tests**

```bash
pytest tests/test_workflow_examples_v0.py -k adjudicated -q
```

Expected: pass.

- [ ] **Step 6: Commit prompt and example**

```bash
git add workflows/library/prompts/adjudication/evaluate_candidate.md workflows/examples/adjudicated_provider_demo.yaml workflows/README.md tests/test_workflow_examples_v0.py
git commit -m "test: add adjudicated provider workflow example"
```

## Task 9: Add Resume And Observability Coverage

**Files:**
- Modify: `tests/test_adjudicated_provider_runtime.py`
- Modify: `tests/test_adjudicated_provider_scoring.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `specs/state.md` if implementation exposes any extra state detail

- [ ] **Step 1: Add failing resume-after-candidates test**

Simulate a run where candidate outputs and score ledger entries exist but
promotion has not happened. Resume should verify baseline metadata, candidate
metadata, scorer identity or scorer-unavailable metadata, and packet hashes
before reusing scores, then promote once without duplicating ledger rows.

- [ ] **Step 2: Add failing resume-after-promotion test**

Simulate interrupted state after promotion but before step result finalization.
Resume should follow the promotion manifest state, revalidate canonical outputs,
regenerate the terminal run-local ledger, materialize the mirror if configured,
withhold publication if mirror materialization fails, and not duplicate ledger
rows.

- [ ] **Step 3: Add failing resume mismatch tests**

Cover:

- baseline missing while candidate workspace, packet, terminal metadata, or
  ledger row exists
- candidate config hash or composed prompt hash changed for unfinished candidate
- current scorer identity differs from persisted scorer snapshot
- persisted scorer-unavailable key differs from current scorer-resolution failure
  or current scorer would now resolve successfully
- terminal score/evaluation metadata exists without matching scorer snapshot
- ledger rows with `scorer_unavailable` lack matching scorer-resolution failure
  metadata

Assert each case fails with `adjudication_resume_mismatch` unless a future
explicit force-rerun path is being tested.

- [ ] **Step 4: Add report projection test**

Assert `orchestrator report` or the observability projection includes selected
candidate id, selected score or null score, selection reason, score ledger path,
run-local ledger path, promotion status, and adjudication failure type when
present.

- [ ] **Step 5: Implement resume reconciliation**

Persist enough metadata under the step `adjudication` state and candidate roots
to detect:

- baseline created and manifest digest
- candidate completed
- scorer snapshot or scorer-unavailable metadata completed
- evaluation packet persisted
- evaluation completed or failed
- selection completed
- run-local ledger materialized
- promotion manifest prepared, committing, rolling back, failed, or committed
- workspace-visible mirror materialized
- publication completed

Keep markers runtime-owned; prompts do not write them.

- [ ] **Step 6: Run resume/observability tests**

```bash
pytest tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_scoring.py -k "resume or observability or mismatch" -q
```

Expected: pass.

- [ ] **Step 7: Commit resume and observability**

```bash
git add orchestrator/workflow/executor.py orchestrator/state.py orchestrator/observability/report.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_scoring.py specs/state.md
git commit -m "feat: make adjudicated provider resume-safe"
```

## Task 10: Final Docs, Validation, And Smoke Checks

**Files:**
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `docs/index.md`
- Modify: `specs/acceptance/index.md` if gaps remain
- Modify: `docs/plans/2026-04-20-adjudicated-provider-step-design.md` only if implementation reveals needed corrections
- Modify: `docs/plans/2026-04-20-adjudicated-provider-step-implementation-plan.md` to mark completed tasks if executing in-place

- [x] **Step 1: Update workflow drafting guidance**

Add a short section explaining when to use `adjudicated_provider`:

- use for high-value artifact-producing provider steps where multiple providers
  or prompt variants should be compared
- do not use for arbitrary implementation/source edits in V1
- keep evaluator prompt reusable and task rubrics small
- require explicit same-trust-boundary attestation and treat packets, ledgers,
  baseline snapshots, and promotion staging as sensitive run state
- keep adjudicated steps artifact-producing; do not rely on stdout-derived step
  variables
- downstream steps should consume promoted artifacts normally

- [x] **Step 2: Update docs index**

Add discoverability entries for the design and any new docs if the repo index is
being kept current.

- [x] **Step 3: Run narrow unit tests**

```bash
pytest tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py -q
```

Expected: pass.

- [x] **Step 4: Run collect-only for new tests**

```bash
pytest --collect-only tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py -q
```

Expected: all tests collect.

- [x] **Step 5: Run workflow/example smoke**

```bash
python -m orchestrator run workflows/examples/adjudicated_provider_demo.yaml --dry-run
pytest tests/test_workflow_examples_v0.py -k adjudicated -q
```

Expected: dry-run validates and mocked runtime smoke passes.

- [x] **Step 6: Run related workflow tests**

```bash
pytest tests/test_workflow_examples_v0.py tests/test_prompt_contract_injection.py -q
```

Expected: pass.

- [x] **Step 7: Inspect git diff**

```bash
git diff --stat
git diff --check
```

Expected: no whitespace errors and no unrelated changes.

- [x] **Step 8: Commit final docs**

```bash
git add docs/workflow_drafting_guide.md docs/index.md specs/acceptance/index.md docs/plans/2026-04-20-adjudicated-provider-step-design.md docs/plans/2026-04-20-adjudicated-provider-step-implementation-plan.md
git commit -m "docs: document adjudicated provider authoring"
```

## Resolved V1 Constraints

- Candidate workspace copies exclude `.git` and the fixed dependency/cache and
  local-secret denylist roots from the design.
- V1 supports one evaluator prompt source plus an optional rubric source. It does
  not support evaluator prompt variants.
- The run-local score ledger is always written. `score_ledger_path` is an
  optional workspace-visible terminal mirror under `artifacts/`.
- `timeout_sec` is one logical step-visit deadline. Candidate and evaluator
  retries share that deadline, do not retry the whole adjudicated step, and do
  not retry ledger, mirror, promotion, validation, or resume mismatch failures.
- Candidate execution is sequential in V1. Preserve the data model so
  `max_concurrency` can be added later without changing ledger semantics.

## Rollback Plan

If runtime implementation becomes too invasive, keep the spec/design documents
and stop after loader/schema validation behind version `2.11`. Since existing
workflows do not use `adjudicated_provider`, the feature is isolated by version
gate and new step form. Remove the example workflow from the index if the runtime
does not ship.
