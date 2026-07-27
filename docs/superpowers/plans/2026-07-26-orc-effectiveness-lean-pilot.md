# `.orc` Effectiveness Lean Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking. Independent review occurs at the protocol/runner, treatment-parity, and final-evidence gates named below, plus the later owner-approved focused contract and module-quality rereviews after accepted contract or source-layout changes; do not create per-step review ceremonies.

**Goal:** Build and run the smallest three-treatment controlled pilot that can decide whether a separately planned prospective PtychoPINN `.orc` versus one-shot experiment is warranted.

**Architecture:** Add five public `orchestrator.experiments` responsibility
surfaces and one thin CLI. Oversized runner, evaluation, and reporting
surfaces are thin facades over private responsibility owners, with every
production module capped at 500 physical lines. Freeze four record contracts,
materialize three byte-identical archive-backed workspaces, launch `DIRECT`,
`COORDINATOR`, and `ORC` concurrently, freeze products, calibrate blinded
reviewers, and run at most five live `A1` attempts to obtain three valid
exploratory blocks. The coordinator is frozen and parity-tested against the
`.orc` topology before any live outcome.

**Tech Stack:** Python 3, `pytest`, `jsonschema`, `tarfile`, `subprocess`, SHA-256 canonical JSON, Workflow Lisp, existing provider CLIs, and JSON evidence.

> **Execution status (2026-07-27):** Tasks 1–6 and the pre-calibration
> module-size gate are focused green. Locked A0 calibration round 1 passed with
> six unique sessions and external seal
> `sha256:ad2570d72a0608173232d53beee7990c0e2afaa198f549bae8769083cc8e7f8f`.
> Task 6B is complete. The Task 7 provider-free controller and its focused
> contract/module-quality gate, governed by
> `docs/plans/2026-07-27-orc-effectiveness-lean-pilot-task7-readiness-amendment.md`,
> are active. The controller implementation and focused behavioral suites are
> green; the focused rereviews and broad verification must close before lock
> creation. No pilot lock, real-provider smoke, or live `A1` attempt has run.

## Global Constraints

- Governing design: [`docs/superpowers/specs/2026-07-26-orc-effectiveness-lean-pilot-design.md`](../specs/2026-07-26-orc-effectiveness-lean-pilot-design.md).
- Do not modify or resume the paused provider-phase isolation implementation.
- Preserve all existing uncommitted shared-tree work; touch only paths named by the active task.
- Do not create worktrees. Materialize source with `git archive` into fresh ordinary directories.
- First-tranche results are `exploratory_controlled_task` only.
- `DIRECT` has exactly one provider invocation.
- `COORDINATOR` and `ORC` must be frozen and parity-approved before live results.
- The first live series targets three valid `A1` blocks within five ordered
  attempts. No outcome-dependent extension.
- Treatment-specific provider, compiler, runtime, timeout, check, and output failures remain outcomes.
- Unknown usage/cost remains `UNKNOWN`.
- Do not add a persistent lifecycle engine, attempt resume/recovery state
  machine, retries around whole treatment runs, database, registry, dashboard,
  or schema per intermediate event. Auxiliary lock/block-bound quiescence
  evidence may only prove that a surviving `STARTED` attempt's process groups
  are absent before the next ordered ID launches; it never changes or recovers
  that attempt.
- Do not implement `F1`, `F2`, `E2`, `E4`, `E5`, or `E6` in this plan.
- Use TDD for reusable code. If a task adds a test module, run `pytest --collect-only` before its tests.
- Tests assert contracts and behavior, never literal prompt wording.
- Every production Python module under `orchestrator/experiments/` remains at
  or below 500 physical lines. Public facades may not duplicate private-owner
  logic.

---

## Current Planned And Implemented File Layout

This catalog includes the accepted Task 6B/Task 7 amendments. Private support
modules preserve the original responsibility boundaries; they do not add a
public surface or a fifth record kind.

```text
orchestrator/experiments/
  __init__.py
  contracts.py       # one packaged schema, canonical JSON, four record validators
  _contracts_pilot_lock.py
  workspace.py       # git-archive materialization and deterministic product freeze
  runner.py          # thin public block-runner facade
  _runner_types.py
  _runner_apparatus.py
  _runner_preflight.py
  _runner_execution.py
  _runner_block.py
  _runner_source.py
  _runner_quiescence.py
  evaluation.py      # thin public blinded-evaluation facade
  _evaluation_support.py
  _evaluation_live.py
  _evaluation_calibration_support.py
  _evaluation_calibration_build.py
  _evaluation_calibration_mapping.py
  _evaluation_calibration_validation.py
  _evaluation_ingest.py
  reporting.py       # thin public synthesis/planning facade
  _reporting_types.py
  _reporting_sample_size.py
  _reporting_validation.py
  _reporting_reviews.py
  _reporting_metrics.py
  _reporting_synthesis.py
  _reporting_render.py
  _pilot_prepare.py
  _pilot_prepare_support.py
  _pilot_prepare_validation.py
  _pilot_evidence.py
  _pilot_evidence_support.py
  _pilot_evaluator_apparatus.py
  _pilot_evaluator_process.py
  _pilot_review.py
  _pilot_review_support.py
  _pilot_review_schema.py
  _pilot_review_assets.py
  _pilot_review_execution.py
  _pilot_review_bindings.py
  _pilot_controller.py
  _pilot_controller_state.py
  schemas/
    __init__.py
    lean-pilot-records-v1.schema.json

scripts/experiments/
  lean_pilot.py                 # thin CLI
  conventional_coordinator.py   # frozen bounded control, not a framework

workflows/experiments/repository_task_pilot/
  task_loop.orc
  prompts/
    discover.md
    plan.md
    review_plan.md
    revise_plan.md
    implement.md
    review_implementation.md
    fix_implementation.md

experiments/orc_effectiveness/lean_pilot/
  control/
    providers.json
    prompts.json
    commands.json
    runtime-control.json
  pilot-lock.json
  tasks/a1.md
  treatments/direct.json
  treatments/coordinator.json
  treatments/orc.json
  reviewers/rubric.md
  calibration/
    a0-reference.patch
    calibration-lock.json
  evidence/                     # generated, not committed unless explicitly approved

tests/experiments/
  test_lean_pilot_contracts.py
  test_lean_pilot_workspace.py
  test_lean_pilot_runner.py
  test_lean_pilot_treatment_parity.py
  test_lean_pilot_evaluation.py
  test_lean_pilot_reporting.py
  test_lean_pilot_module_layout.py
  fixtures/lean_pilot/
    arm_program.py
    scripted_provider.py
```

Do not create empty future directories. Each task creates only the paths it exercises.

## Public Interfaces

The first tranche owns these interfaces and no broader experiment API:

```python
# orchestrator/experiments/contracts.py
class PilotContractError(ValueError): ...

def canonical_json_bytes(value: object) -> bytes: ...
def canonical_sha256(value: object) -> str: ...
def load_record(path: Path, expected_kind: str) -> dict[str, object]: ...
def validate_record(value: Mapping[str, object], expected_kind: str) -> None: ...

# orchestrator/experiments/workspace.py
@dataclass(frozen=True)
class TreeEntry: ...
@dataclass(frozen=True)
class TreeManifest: ...

def materialize_git_archive(repo: Path, commit: str, destination: Path) -> TreeManifest: ...
def freeze_product(root: Path, excluded_roots: Collection[PurePosixPath]) -> TreeManifest: ...

# orchestrator/experiments/runner.py
@dataclass(frozen=True)
class ArmCommand: ...
@dataclass(frozen=True)
class ArmExecution: ...
@dataclass(frozen=True)
class BlockAttempt: ...

def run_block(*, lock: Mapping[str, object], block_id: str, work_root: Path, evidence_root: Path) -> BlockAttempt: ...

# orchestrator/experiments/evaluation.py
def build_blind_packages(*, lock: Mapping[str, object], block: Mapping[str, object], product_roots: Mapping[str, Path], base_root: Path, task_path: str, selected_final_files: Mapping[str, Sequence[str]], permitted_check_evidence: Mapping[str, Sequence[str]], output_root: Path, controller_root: Path) -> dict[str, Path]: ...
def build_calibration_packages(*, calibration_lock: Mapping[str, object], base_identity: Mapping[str, object], predecessor_lock: Mapping[str, object] | None, predecessor_controller_mapping: Mapping[str, object] | None, predecessor_controller_root: Path | None, predecessor_reviews: Sequence[Mapping[str, object]] | None, base_root: Path, task_path: str, reference_patch: Path, rubric_path: Path, selected_final_files: Sequence[str], visible_check_argv: Sequence[str], visible_check_timeout_milliseconds: int, visible_check_class: str, hidden_evaluator_class: str, evaluator_module: ModuleType, oracle_path: Path, environment: Mapping[str, str], reviewer_execution: Mapping[str, object], output_root: Path, controller_root: Path) -> dict[str, Path]: ...
def validate_calibration(*, calibration_lock: Mapping[str, object], controller_mapping: Mapping[str, object], controller_root: Path, reviews: Sequence[Mapping[str, object]], predecessor_lock: Mapping[str, object] | None, predecessor_controller_mapping: Mapping[str, object] | None, predecessor_controller_root: Path | None, predecessor_reviews: Sequence[Mapping[str, object]] | None) -> None: ...
def ingest_review(path: Path, *, package_root: Path, expected_bindings: Mapping[str, object], used_session_ids: Collection[str], prior_records: Sequence[Mapping[str, object]]) -> dict[str, object]: ...

# orchestrator/experiments/reporting.py
@dataclass(frozen=True)
class ExactSampleSizePlan: ...
@dataclass(frozen=True)
class ReviewBinding: ...
@dataclass(frozen=True)
class UnblindingBinding: ...
def load_attempt_records(*, lock: Mapping[str, object], evidence_root: Path) -> tuple[dict[str, object], ...]: ...
def build_pilot_summary(*, lock: Mapping[str, object], block_attempts: Sequence[Mapping[str, object]], reviews: Sequence[Mapping[str, object]], sealed_review_bindings: Sequence[ReviewBinding], unblinding: Sequence[UnblindingBinding]) -> dict[str, object]: ...
def render_pilot_markdown(summary: Mapping[str, object]) -> str: ...
def exact_binomial_tail(*, n: int, successes_at_least: int, rate: Fraction) -> Fraction: ...
def plan_exact_sample_size(*, null_rate: Fraction, target_rate: Fraction, alpha: Fraction, power: Fraction, max_tie_rate: Fraction, accrual_probability: Fraction, max_invalid_attempts: int, max_cost_ratio: Fraction, min_calls_per_block: int, max_calls_per_block: int, search_limit: int) -> ExactSampleSizePlan: ...
```

Later work must not depend on an interface absent from this block.

---

## Task 1: Add The Four Lean Record Contracts

**Files:**

- Create: `orchestrator/experiments/__init__.py`
- Create: `orchestrator/experiments/contracts.py`
- Create: `orchestrator/experiments/schemas/__init__.py`
- Create: `orchestrator/experiments/schemas/lean-pilot-records-v1.schema.json`
- Create: `tests/experiments/test_lean_pilot_contracts.py`

**Interfaces:**

- Produces `canonical_json_bytes`, `canonical_sha256`, `validate_record`, and `load_record` exactly as declared above.
- Produces four schema kinds: `pilot_lock.v1`, `block_attempt.v1`,
  `review_result.v1`, and `pilot_summary.v1`.
- Requires one strict `pilot_lock.v1.apparatus` object and one
  `command_config_path` on each of the three existing treatment objects. The
  apparatus owns the only absolute apparatus path, a relative content
  manifest, role paths for unmodified standard Workflow Lisp extern manifests,
  a closed environment identity/allowlist/credential partition, visible-check
  argv and timeout, product exclusions, and start/quiescence bounds.
- Separates durable repository identity from its canonical local root and
  binds a commit-relative source subtree plus exact Git tree object.
- Requires an exact treatment-visible asset subset, per-treatment source-asset
  closures, derived source/bundle/profile digests, and controller-only
  evaluator/reviewer assets.
- No task adds a fifth first-tranche record kind.

- [ ] **Step 1: Write the contract tests**

Cover:

- deterministic sorted UTF-8 JSON bytes with no whitespace;
- rejection of all floats, non-string mapping keys, and non-JSON values;
- `sha256:<64 lowercase hex>` digests;
- recursive unknown-field rejection;
- exact `record_kind` dispatch to one of four `$defs` in one packaged schema;
- a pilot lock requiring exactly `DIRECT`, `COORDINATOR`, and `ORC` treatments;
- `valid_block_count == 3`, `max_live_attempt_count == 5`, one smoke ID, an
  ordered five-element live-attempt-ID list, and
  `claim_level == "exploratory_controlled_task"`;
- one provider-call bound for DIRECT and `3..9` for both orchestrated
  treatments, with completion-capable orchestrated routes constrained to
  `5..9`;
- exact treatment source/command digests, task/archive identity, provider policy, reviewer/rubric identity, randomization seed, and evidence root;
- a required apparatus whose `control_root` is canonical absolute POSIX text
  other than `/`; whose manifest, role, treatment-command, and exclusion paths
  are canonical relative POSIX text; and whose nested objects reject unknown
  fields recursively;
- unique manifest paths even when duplicate paths carry different digests;
  every apparatus role path naming a manifest entry; three distinct treatment
  command-configuration paths naming manifest entries whose digests match the
  locked treatment command digests; and the task-path entry matching the task
  brief digest;
- an exact treatment-visible manifest subset that excludes every
  controller-only review/evaluator asset; complete per-treatment source
  closures containing their command configurations; and exact canonical
  source, evaluator-bundle, reviewer-command-bundle, and task-profile digest
  derivations;
- exactly two stable calibrated reviewer IDs, the locked
  `INDETERMINATE_ON_DISAGREEMENT` policy, safe selected-final-file and
  check-evidence-name allowlists, and manifest-bound rubric,
  calibration-seal, evaluator, and reviewer-command assets;
- each treatment command configuration binding the canonical locked
  provider-policy digest;
- a nonempty unique environment-key allowlist using
  `[A-Za-z_][A-Za-z0-9_]*`, required controller-owned `HOME` and `TMPDIR`, and
  unique credential-key names that are a subset of the allowlist and exclude
  those controller keys;
- explicit visible-check argv and positive timeout, explicit unique product
  exclusions (including an allowed empty list), and required positive
  maximum-start-skew and quiescence-grace bounds;
- block attempts binding the pilot-lock digest, declared attempt class,
  sequence index, and predeclared block ID; requiring
  `STARTED | VALID | INVALID | ABORTED`; permitting no treatment executions
  for `STARTED`; requiring exactly the three locked treatment executions for
  `VALID`; and preserving optional launched executions plus a reason code for
  `INVALID`/`ABORTED`;
- each nested treatment execution binding its opaque arm label, treatment ID,
  command digest, lifecycle outcome, product manifest digest when frozen,
  provider-call count, elapsed milliseconds, evidence references, integer token
  counts, and non-negative `cost_microunits` plus locked currency or `UNKNOWN`;
- review results binding reviewer/session identity, calibration/live class,
  opaque candidate labels, evidence citations, pairwise
  `A | B | TIE | INDETERMINATE`, and one sealed
  `DIRECT | COORDINATOR | ORC | UNKNOWN` guess per candidate;
- pilot summaries binding exactly three valid blocks or a terminal stop record,
  deriving method outcomes with sole-viable precedence, preserving conditional
  product-quality review, and retaining invalid/aborted block references
  outside the denominator;
- summary medians and ratios encoded as reduced positive-denominator integer
  fractions or `UNKNOWN`, never JSON floats.

Use this canonicalization contract in the test:

```python
assert canonical_json_bytes({"z": 1, "a": "λ"}) == (
    '{"a":"λ","z":1}'.encode("utf-8")
)
assert canonical_sha256({"a": 1}).startswith("sha256:")
```

- [ ] **Step 2: Run collection and observe RED**

```bash
pytest --collect-only -q tests/experiments/test_lean_pilot_contracts.py
pytest -q tests/experiments/test_lean_pilot_contracts.py
```

Expected: collection succeeds; execution fails because the package and schema do not exist.

- [ ] **Step 3: Implement the minimum canonicalization and validation**

Use one local serialization rule rather than importing provider-isolation or retirement-specific helpers:

```python
def _reject_noncanonical(value: object, path: str = "$") -> None:
    if isinstance(value, float):
        raise PilotContractError(f"float_not_allowed:{path}")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise PilotContractError(f"non_string_key:{path}")
            _reject_noncanonical(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_noncanonical(item, f"{path}[{index}]")
    elif value is not None and not isinstance(value, (str, int, bool)):
        raise PilotContractError(f"non_json_value:{path}")


def canonical_json_bytes(value: object) -> bytes:
    _reject_noncanonical(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
```

Load the packaged schema with `importlib.resources.files`, select the matching `$defs` entry by `record_kind`, and validate with `jsonschema.Draft202012Validator`. Sort validation errors by absolute path and message before raising one `PilotContractError`.

Express the local apparatus shape, path syntax, required fields, and recursive
unknown-field rejection in Draft 2020-12 schema. After schema validation, run
one narrow deterministic semantic check for manifest-path uniqueness; role,
treatment, source-closure, and review/evaluator-bundle references; the exact
treatment-visible/controller-only partition; distinct treatment command paths;
command/provider-policy binding; and the task, command, source, bundle, rubric,
calibration-seal, and task-profile digest equalities. `validate_record` does
not inspect the filesystem; `load_record` receives the same semantic check
through `validate_record`.

- [ ] **Step 4: Run GREEN**

```bash
pytest -q tests/experiments/test_lean_pilot_contracts.py
```

Expected: PASS.

- [ ] **Step 5: Commit only Task 1 paths**

```bash
git add orchestrator/experiments/__init__.py \
  orchestrator/experiments/contracts.py \
  orchestrator/experiments/schemas/__init__.py \
  orchestrator/experiments/schemas/lean-pilot-records-v1.schema.json \
  tests/experiments/test_lean_pilot_contracts.py
git commit -m "feat(experiments): add lean pilot records"
```

---

## Task 2: Materialize Archives And Freeze Products

**Files:**

- Create: `orchestrator/experiments/workspace.py`
- Create: `tests/experiments/test_lean_pilot_workspace.py`

**Interfaces:**

- Consumes `canonical_sha256` from Task 1.
- Produces `materialize_git_archive` and `freeze_product` exactly as declared.
- `TreeManifest` serializes as sorted rows with `path`, `kind`, `mode`, `size`, and `sha256` for regular files; symlinks store link text and its digest without following it.

- [ ] **Step 1: Write archive and freeze tests**

Create a temporary Git repository with regular files, an executable file, a directory, and a relative symlink. Cover:

- materializing the same `commit:subtree` three times yields byte-identical
  rootless manifests;
- a locked subtree whose resolved Git tree object differs from the expected
  tree is rejected before extraction;
- no destination contains `.git`;
- archive entries with absolute paths or `..` are rejected before extraction;
- duplicate members and file/directory path collisions are rejected;
- a relative symlink whose normalized target escapes the destination is
  rejected before any filesystem mutation;
- symlinks are recorded but never followed during hashing;
- FIFO/device/socket entries are rejected;
- product freeze rejects FIFO/device/socket entries instead of opening them;
- product exclusions are exact root-relative paths, not substring matches;
- changing a file changes the product digest;
- changing only an excluded runtime root does not change the product digest; and
- manifest ordering is normalized UTF-8 path ordering.

- [ ] **Step 2: Run collection and RED**

```bash
pytest --collect-only -q tests/experiments/test_lean_pilot_workspace.py
pytest -q tests/experiments/test_lean_pilot_workspace.py
```

Expected: missing module/functions.

- [ ] **Step 3: Implement safe archive materialization**

Run Git without a shell:

```python
archive = subprocess.run(
    ["git", "-C", str(repo), "archive", "--format=tar", treeish],
    check=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
).stdout
```

Resolve `treeish` from the locked full commit plus normalized source-subtree
path, require `git rev-parse <commit>:<subtree>` to equal the locked tree
object, and only then open the bytes with
`tarfile.open(fileobj=io.BytesIO(archive), mode="r:")`.
Validate the full member table before any filesystem mutation: normalize each
member as `PurePosixPath`; reject absolute, empty, parent, duplicate, colliding,
or unsupported entries; and require every relative symlink target, resolved
from its member parent, to remain under the archive root. Then create
directories, regular files, and symlinks explicitly. Do not call
`TarFile.extractall`.

- [ ] **Step 4: Implement deterministic product freeze**

Walk with `os.scandir`/`lstat`, never following symlinks. Hash regular files in bounded chunks. Construct immutable `TreeEntry` rows and compute the manifest digest from their canonical serialized form.

- [ ] **Step 5: Run GREEN**

```bash
pytest -q tests/experiments/test_lean_pilot_workspace.py
```

Expected: PASS.

- [ ] **Step 6: Commit only Task 2 paths**

```bash
git add orchestrator/experiments/workspace.py \
  tests/experiments/test_lean_pilot_workspace.py
git commit -m "feat(experiments): materialize and freeze pilot workspaces"
```

---

## Task 3: Persist One Three-Treatment Block Attempt

**Files:**

- Create: `orchestrator/experiments/runner.py`
- Create: `scripts/experiments/lean_pilot.py`
- Create: `tests/experiments/test_lean_pilot_runner.py`
- Create: `tests/experiments/fixtures/lean_pilot/arm_program.py`

**Interfaces:**

- Consumes `pilot_lock.v1`, Task 2 workspace materialization/freezing, and an external evidence root.
- Resolves every task/provider/prompt/command asset only as a manifest-relative
  child of `apparatus.control_root`; it never searches the process CWD, package
  installation, repository checkout, or a fixed path.
- Before writing `STARTED`, allocating workspaces, or launching an arm, reads
  every manifest file, verifies its bytes against the locked digest, and
  rechecks all role and treatment command-configuration bindings. The three
  role configs must validate as the unmodified standard Workflow Lisp
  provider-extern, prompt-extern, and command-boundary manifests; no
  experiment-specific interpretation is permitted. Every prompt extern must
  use `asset_file` and name a verified manifest entry; `input_file` lookup is
  outside this locked apparatus.
- Constructs each `ArmCommand` from the verified configuration bytes and
  rejects missing configuration, uncontrolled environment keys, implicit
  commands/timeouts, or other defaults before launch.
- Requires the manifest to describe the exact regular-file tree beneath
  `apparatus.control_root`, rejecting any missing, duplicate, symlink,
  nonregular, or extra node, then stages only
  `apparatus.treatment_asset_paths` for each arm under one private
  controller-owned apparatus root while preserving normalized relative paths;
  controller-only assets and the original `apparatus.control_root` are never
  candidate-visible.
- Resolves the locked full commit and source-subtree path to the exact locked
  Git tree before `STARTED`, materializes the rootless subtree, and verifies
  its archive digest plus the archived task bytes against the locked task
  brief before launch.
- Recomputes each treatment's source-closure digest from its manifest rows and
  requires its command configuration to bind the exact locked provider-policy
  digest; neither source nor provider policy may be inherited from an
  uncontrolled default.
- Atomically persists one `block_attempt.v1`; valid attempts contain exactly
  three nested treatment executions.
- Does not implement resume, a database, a reusable state machine, or
  whole-treatment retry.
- Supplies every arm the same locked environment-key allowlist, distinct
  per-arm `HOME`/temporary roots, only the explicitly locked credential keys
  obtained through the existing secrets manager, and exactly the remaining
  non-controller/noncredential keys from that treatment's launcher config.
- Excludes unrelated ambient variables and records credential names/presence
  only in structured metadata, never values.

- [ ] **Step 1: Write runner tests**

The fixture arm supports `success`, `timeout`, `nonzero`, `spawn-child`, and `prelaunch-fail` modes. Cover:

- three commands start after one barrier and within the lock's maximum start skew;
- each treatment receives a distinct byte-identical workspace;
- treatment IDs are replaced by opaque arm labels in candidate-visible paths and environment;
- stdout/stderr go to evidence files outside candidate roots;
- no arm argv/environment contains the shared evidence root, peer paths,
  treatment mapping, original apparatus control root, or final block-attempt
  path;
- each arm receives only one opaque per-arm raw-result path; the controller
  validates that payload and authors the nested execution record itself;
- the strict raw result carries exactly one semantic terminal
  (`COMPLETED | BLOCKED | EXHAUSTED | PROTOCOL_FAILURE`) alongside
  provider-call count and usage/cost, and every allowed terminal is preserved;
- missing, unknown, or conflicting semantic terminals fail the raw-result
  protocol closed;
- unrelated ambient variables are absent from every arm;
- credential names/presence match `apparatus.environment.credential_keys` and structured records
  never contain credential values;
- a DIRECT arm result with provider-call count other than one is invalid;
- COORDINATOR/ORC counts outside `3..9` are invalid treatment results, not
  block invalidity; a three-call plan-review block is valid while every
  completion-capable route uses `5..9`;
- one treatment timeout terminates its process group and remains an outcome while peers complete;
- an outliving child is terminated before product freeze;
- a shared prelaunch archive/allocation failure invalidates the whole block symmetrically;
- a missing manifest file, a file outside the control root, any manifest digest
  mismatch, any role/treatment binding mismatch, or any uncontrolled config
  default fails before `STARTED`, workspace allocation, and launch;
- legacy experiment-only provider-credential/shared-environment shapes fail
  while standard Workflow Lisp extern manifests compile unchanged;
- prompt externs use only `asset_file` paths present in the verified manifest;
  dynamic `input_file` paths fail before `STARTED`;
- every asset in `apparatus.treatment_asset_paths` is staged for every arm at
  its manifest-relative path, no controller-only manifest asset is staged, and
  launch remains independent of CWD, package location, and the original
  control root after preflight;
- commands, the visible check, environment keys, exclusions, start skew, and
  quiescence grace all come from the verified lock/config assets rather than
  CWD, package-location, or hardcoded lookup;
- a validated `STARTED` attempt exists before archive/allocation work;
- every caught terminal path atomically replaces it with `VALID`, `INVALID`, or
  `ABORTED`;
- a surviving `STARTED` record after controller interruption remains durable,
  is classified as aborted during synthesis, and cannot be resumed;
- readers never observe a partial JSON record;
- one treatment launch failure after the barrier remains that treatment's outcome;
- rerunning an aborted block requires a new block ID and preserves the old evidence directory;
- the smoke ID is single-use and live IDs execute as a contiguous prefix of the
  locked list; reused, skipped, or out-of-order IDs fail before allocation;
- the runner never imports provider-isolation modules.

- [ ] **Step 2: Run collection and RED**

```bash
pytest --collect-only -q tests/experiments/test_lean_pilot_runner.py
pytest -q tests/experiments/test_lean_pilot_runner.py
```

Expected: missing runner and CLI.

- [ ] **Step 3: Implement closed command substitution**

`ArmCommand` contains immutable tuples for argv and environment additions plus a timeout. Permit only these placeholders:

```python
_ALLOWED = {
    "workspace",
    "task_path",
    "result_path",
    "provider_config",
    "prompt_config",
    "command_config",
    "apparatus_root",
}
```

Resolve the task, the unmodified standard provider/prompt/command extern
manifests, and the three treatment launcher configurations from verified
manifest bytes beneath `apparatus.control_root`. The three treatment command
files must be distinct and each verified file digest must equal the
treatment's locked `command_digest`; build `ArmCommand` only after those checks
pass. Stage a verified manifest asset under each arm's private
`apparatus_root` if and only if it is named in the locked
`apparatus.treatment_asset_paths` subset, preserving the normalized relative
path. Keep controller-only evaluator, rubric, calibration, and reviewer assets
out of every treatment root. Bind the three
extern-manifest placeholders to their staged standard role manifests—not to
the treatment launcher configuration. Do not infer assets from CWD, package
locations, or repository/fixed paths.

Construct `closed_env` only from the lock's explicit
`apparatus.environment.allowed_keys`: controller-owned per-arm `HOME` and
`TMPDIR`; only `apparatus.environment.credential_keys` resolved through the
existing secrets manager; and exactly the remaining allowed keys supplied by
each treatment launcher's `environment` object. Credential keys must be unique,
explicitly allowed, and distinct from `HOME`/`TMPDIR`. Reject overlap, missing
keys, extras, and ambient/default inheritance before `STARTED`. Do not parse
the provider extern manifest as a credential object or the command-boundary
manifest as a shared environment object. Do not copy `os.environ` wholesale,
imply even `PATH`/locale as a default, or add a new secrets backend. Record
environment key names and presence only; never serialize secret values.

Reject unknown placeholders and never invoke a shell.

- [ ] **Step 4: Implement concurrent launch and quiescence**

Create one opaque raw-result path per arm outside the candidate product. Pass
only that path—not the shared evidence root, peer directories, or final attempt
path—to the arm. The controller alone opens stdout/stderr evidence files,
collects process state, validates the raw result, computes the product
manifest, and constructs the nested treatment execution. The raw result
contains a strict semantic terminal
(`COMPLETED | BLOCKED | EXHAUSTED | PROTOCOL_FAILURE`), provider-call count,
and usage/cost. After a zero exit and a valid raw result, preserve that semantic
terminal as the treatment lifecycle. Launch failure, timeout, nonzero exit,
and an invalid raw result retain precedence over every reported semantic
terminal. A provider-call bound violation becomes `PROTOCOL_FAILURE`. A final
visible-check failure converts only semantic `COMPLETED` to `CHECK_FAILURE`; it
never erases `BLOCKED`, `EXHAUSTED`, or `PROTOCOL_FAILURE`.

Use one `threading.Barrier(4)` for three arm-launch workers plus the controller. Launch each command with:

```python
subprocess.Popen(
    argv,
    cwd=workspace,
    env=closed_env,
    stdin=subprocess.DEVNULL,
    stdout=stdout_file,
    stderr=stderr_file,
    start_new_session=True,
)
```

Only after validating the lock, reading and hashing every manifest asset, and
constructing all three commands from the verified configurations—and before
archive allocation—write the validated `STARTED` attempt to a temporary file in
the block evidence directory, `fsync` it, install it with `os.replace`, and
`fsync` the parent directory.
Before every treatment-arm and visible-check `Popen`, durably add an in-flight
spawn marker to the auxiliary lock/block-bound process-group ledger. After a
successful `Popen`, atomically replace that marker with its process-group ID;
clear it without a group only when launch failure is proven. A surviving
marker makes quiescence unprovable and halts collection. It does not authorize
attempt recovery, resume, deletion, or rerun.
Measure the three-arm start skew from monotonic timestamps taken immediately
before the actual `Popen` attempts and after durable marker persistence; do not
use barrier-arrival or pre-marker timestamps.
On timeout, send `SIGTERM` to the process group, wait the frozen
`apparatus.quiescence_grace_milliseconds`, then `SIGKILL`. Enforce the locked
maximum start skew and run exactly the locked visible-check argv with its
locked timeout; there are no timing or command defaults. Record each treatment
outcome before freezing its product. Every caught controller terminal path validates and atomically
replaces the same attempt path with `VALID`, `INVALID`, or `ABORTED`; a shared
failure terminates any process already launched. Permit only the single-use
smoke ID or next unused live ID declared by the lock. Never reuse
an ID, skip a live prefix position, or resume a surviving `STARTED` attempt.

- [ ] **Step 5: Add the thin CLI**

Implement only:

```text
validate-lock --lock PATH
run-block --lock PATH --block-id ID --work-root PATH --evidence-root PATH
freeze-product --root PATH --output PATH
```

The script imports package functions and contains no experiment semantics.

- [ ] **Step 6: Run GREEN and protocol/runner review gate**

```bash
pytest -q \
  tests/experiments/test_lean_pilot_contracts.py \
  tests/experiments/test_lean_pilot_workspace.py \
  tests/experiments/test_lean_pilot_runner.py
python scripts/experiments/lean_pilot.py --help
```

Expected: PASS and the three commands listed.

Obtain one independent review covering only:

- the four-record boundary;
- symmetric block invalidation versus treatment outcomes;
- no shell invocation;
- no attempt resume/recovery state machine beyond the single atomic
  `STARTED`-to-terminal attempt record; auxiliary process-group evidence may
  only prove quiescence before the next ordered ID and may not transition,
  recover, or rerun the surviving attempt;
- no dependency on paused provider-isolation work.

Fix supported findings, rerun the selector, and bind the reviewed source digest before continuing.

- [ ] **Step 7: Commit only Task 3 paths after the gate**

```bash
git add orchestrator/experiments/runner.py \
  scripts/experiments/lean_pilot.py \
  tests/experiments/test_lean_pilot_runner.py \
  tests/experiments/fixtures/lean_pilot/arm_program.py
git commit -m "feat(experiments): run lean three-treatment blocks"
```

---

## Task 4: Freeze DIRECT, COORDINATOR, And ORC Treatments

**Required skill:** use `workflow-authoring` for the `.orc` source and prompts.

**Files:**

- Create: `scripts/experiments/conventional_coordinator.py`
- Create: `workflows/experiments/repository_task_pilot/task_loop.orc`
- Create: `workflows/experiments/repository_task_pilot/prompts/discover.md`
- Create: `workflows/experiments/repository_task_pilot/prompts/plan.md`
- Create: `workflows/experiments/repository_task_pilot/prompts/review_plan.md`
- Create: `workflows/experiments/repository_task_pilot/prompts/revise_plan.md`
- Create: `workflows/experiments/repository_task_pilot/prompts/implement.md`
- Create: `workflows/experiments/repository_task_pilot/prompts/review_implementation.md`
- Create: `workflows/experiments/repository_task_pilot/prompts/fix_implementation.md`
- Create: `experiments/orc_effectiveness/lean_pilot/tasks/a1.md`
- Create: `experiments/orc_effectiveness/lean_pilot/treatments/direct.json`
- Create: `experiments/orc_effectiveness/lean_pilot/treatments/coordinator.json`
- Create: `experiments/orc_effectiveness/lean_pilot/treatments/orc.json`
- Create: `experiments/orc_effectiveness/lean_pilot/control/providers.json`
- Create: `experiments/orc_effectiveness/lean_pilot/control/prompts.json`
- Create: `experiments/orc_effectiveness/lean_pilot/control/commands.json`
- Create: `experiments/orc_effectiveness/lean_pilot/control/runtime-control.json`
- Create: `tests/experiments/test_lean_pilot_treatment_parity.py`
- Create: `tests/experiments/fixtures/lean_pilot/scripted_provider.py`

**Interfaces:**

- Both orchestrated treatments consume the same seven prompt files and logical result schemas.
- Both implement exactly the three-to-nine-call terminal topology and
  five-to-nine-call completion-capable topology in the governing design.
- Both call the same existing public provider adapter and request renderer. The
  coordinator may not implement a provider client or alternate wrapper.
- Every logical provider call uses a fresh session; cross-phase context is
  exactly the typed input record supplied to that phase.
- Both invoke the same controller-owned product-manifest guard around every
  judgment-only provider call; only `implement` and `fix_implementation` may
  mutate the candidate.
- The conventional coordinator exposes only `run_task(config: PilotTreatmentConfig) -> CoordinatorResult` and a script entrypoint. It is not imported by production orchestration code.

- [ ] **Step 1: Write deterministic route-parity tests first**

Drive both treatments with one scripted provider covering:

1. immediate plan approval and implementation approval — five calls;
2. one plan revision — seven calls;
3. one implementation fix — seven calls;
4. both correction routes — nine calls;
5. plan blocked — three calls;
6. implementation blocked — five calls;
7. second review still revises — exhausted;
8. a judgment-only provider mutates the product — protocol failure; and
9. required checks still fail after the one fix — exhausted.

For each route, compare:

- phase names and order;
- canonical complete provider-request payload after the same typed inputs,
  including system/user messages, tools, typed-result schema, and provider
  parameters with only transport-generated correlation IDs removed;
- distinct provider-session identities per call and no undeclared
  conversational carry-over;
- result validation outcome;
- visible-check command and result injection;
- product-manifest guard command, before/after digests, and mutation
  disposition;
- call count; and
- terminal outcome.

Do not compare implementation-specific compiler/runtime events.

- [ ] **Step 2: Run collection and RED**

```bash
pytest --collect-only -q tests/experiments/test_lean_pilot_treatment_parity.py
pytest -q tests/experiments/test_lean_pilot_treatment_parity.py
```

Expected: missing treatment assets and coordinator.

- [ ] **Step 3: Author task-local prompts**

Each prompt owns only its judgment role:

- `discover`: inspect the task/repository and return structured relevant paths, constraints, and risks without changing the product;
- `plan`: produce a bounded implementation plan from the task and discovery record;
- `review_plan`: return `APPROVE | REVISE | BLOCKED` with evidence;
- `revise_plan`: address accepted review findings once;
- `implement`: execute the approved plan and run ordinary checks;
- `review_implementation`: return `APPROVE | REVISE | BLOCKED` from task, plan, diff, and fixed-check evidence;
- `fix_implementation`: correct accepted findings once.

Prompts must not mention route counters, later phases, global method identity, or pilot comparison.

- [ ] **Step 4: Implement the bounded conventional coordinator**

Use one immutable phase table and explicit branches. A `judgment_call` helper
invokes the shared product-manifest command before and after the provider call
and fails the treatment if the digests differ. The coordinator may contain no
generic DAG, resume, plugin, registry, or persistence API. Its only loop-like
behavior is one explicit optional plan revision and one explicit optional
implementation fix.

The route shape is:

```python
discovery = judgment_call("discover", ...)
plan = judgment_call("plan", discovery, ...)
plan_review = judgment_call("review_plan", plan, ...)
if plan_review.kind == "BLOCKED":
    return blocked(plan_review)
if plan_review.kind == "REVISE":
    plan = judgment_call("revise_plan", plan, plan_review, ...)
    plan_review = judgment_call("review_plan", plan, ...)
    if plan_review.kind != "APPROVE":
        return exhausted_or_blocked(plan_review)
implementation = call("implement", plan, ...)
checks = run_fixed_checks()
review = judgment_call("review_implementation", plan, implementation, checks, ...)
if review.kind == "APPROVE" and checks.required_passed:
    return completed(...)
if review.kind == "BLOCKED":
    return blocked(review)
fixed = call("fix_implementation", plan, review, checks, ...)
checks = run_fixed_checks()
review = judgment_call("review_implementation", plan, fixed, checks, ...)
return completed_or_exhausted_or_blocked(review, checks)
```

- [ ] **Step 5: Author the `.orc` treatment through ordinary Workflow Lisp**

Use current implemented typed records, enums, `provider-result`, `let*`, and
explicit typed `if` branches. Surround every judgment-only `provider-result` with the same
controller-owned product-manifest command and compare its typed digest result;
route mutation to the same protocol-failure outcome as the coordinator. The
workflow must lower through the ordinary frontend and use no
experiment-specific compiler/runtime branch. Keep the task, prompts, provider
externs, and command externs external inputs.

- [ ] **Step 6: Make parity GREEN**

```bash
python -m orchestrator compile \
  workflows/experiments/repository_task_pilot/task_loop.orc \
  --source-root workflows/experiments/repository_task_pilot \
  --entry-workflow task_loop::run-task \
  --provider-externs-file experiments/orc_effectiveness/lean_pilot/control/providers.json \
  --prompt-externs-file experiments/orc_effectiveness/lean_pilot/control/prompts.json \
  --command-boundaries-file experiments/orc_effectiveness/lean_pilot/control/commands.json
pytest -q tests/experiments/test_lean_pilot_treatment_parity.py
```

Create the three standard extern manifests in this task. They bind the shared
provider templates, all seven prompt paths, the product-manifest command, and
the fixed-check command used by both orchestrated treatments. Use the existing
public manifest formats unchanged; do not add credentials, launcher
environment, or another experiment-specific control shape to them. Each
treatment launcher config supplies its exact locked
non-controller/noncredential environment partition and uses the staged
`{apparatus_root}` plus staged role-manifest placeholders. Every prompt extern
uses `asset_file` and names another verified asset-manifest entry.
The task-local module is `task_loop`, so the portable apparatus stages
`task_loop.orc` at its root with `prompts/` beside it; this keeps each
source-relative prompt path identical to its verified manifest path.
`control/runtime-control.json` is a verified apparatus template, not a fifth
cross-process experiment record. It binds the product-projection exclusions
and visible-check definition consumed by both orchestrated treatments, and the
launcher materializes its verified content into each candidate's excluded
runtime directory.

Expected: compile exits `0`; all nine parity routes pass.

Also exercise each frozen treatment JSON argv through one flat staged
apparatus, the real treatment entrypoint, real DIRECT/coordinator/Workflow Lisp
paths, standard manifests, and runtime-control visible check. The
scripted-provider executable is test-only and is made visible solely by
prepending its directory to `PATH`; assert that executable and `PATH` are the
only production-environment differences. Assert the raw results and visible
check: DIRECT `1/COMPLETED`, COORDINATOR `5/COMPLETED`, and ORC
`5/COMPLETED`. This provider-free actual-launcher gate creates no lock ID,
`block_attempt.v1`, live asset, hidden registry, or fifth record.

- [ ] **Step 7: Obtain the treatment-parity review gate**

One independent reviewer verifies:

- coordinator source was frozen before live outcomes;
- no reusable second framework was created;
- prompts and logical schemas are shared;
- every route has byte/logical parity;
- all three frozen argv values pass the provider-free actual-launcher gate and
  disclose the sole test-only provider/`PATH` difference;
- judgment-only product mutation fails both treatments identically;
- DIRECT is one invocation; and
- no provider-isolation implementation path changed.

Fix supported findings, rerun compile/parity, and record the exact reviewed
treatment digests for Task 7 to bind into the immutable pilot lock.

- [ ] **Step 8: Commit Task 4 paths after the gate**

Stage exactly the governing-design/plan amendments plus the created treatment,
prompt, task, control-template, scripted-provider test helper, and parity-test
paths. Use:

```bash
git add \
  docs/superpowers/specs/2026-07-26-orc-effectiveness-lean-pilot-design.md \
  docs/superpowers/plans/2026-07-26-orc-effectiveness-lean-pilot.md \
  scripts/experiments/conventional_coordinator.py \
  workflows/experiments/repository_task_pilot/task_loop.orc \
  workflows/experiments/repository_task_pilot/prompts/discover.md \
  workflows/experiments/repository_task_pilot/prompts/plan.md \
  workflows/experiments/repository_task_pilot/prompts/review_plan.md \
  workflows/experiments/repository_task_pilot/prompts/revise_plan.md \
  workflows/experiments/repository_task_pilot/prompts/implement.md \
  workflows/experiments/repository_task_pilot/prompts/review_implementation.md \
  workflows/experiments/repository_task_pilot/prompts/fix_implementation.md \
  experiments/orc_effectiveness/lean_pilot/tasks/a1.md \
  experiments/orc_effectiveness/lean_pilot/treatments/direct.json \
  experiments/orc_effectiveness/lean_pilot/treatments/coordinator.json \
  experiments/orc_effectiveness/lean_pilot/treatments/orc.json \
  experiments/orc_effectiveness/lean_pilot/control/providers.json \
  experiments/orc_effectiveness/lean_pilot/control/prompts.json \
  experiments/orc_effectiveness/lean_pilot/control/commands.json \
  experiments/orc_effectiveness/lean_pilot/control/runtime-control.json \
  tests/experiments/test_lean_pilot_treatment_parity.py \
  tests/experiments/fixtures/lean_pilot/scripted_provider.py
git commit -m "feat(experiments): freeze lean pilot treatments"
```

---

## Task 5: Calibrate Reviewers And Build Blinded Evaluation

**Files:**

- Create: `orchestrator/experiments/evaluation.py`
- Create: `experiments/orc_effectiveness/lean_pilot/reviewers/rubric.md`
- Create: `experiments/orc_effectiveness/lean_pilot/calibration/calibration-lock.json`
- Create: `experiments/orc_effectiveness/lean_pilot/calibration/a0-reference.patch`
- Create: `tests/experiments/test_lean_pilot_evaluation.py`

**Interfaces:**

- Consumes frozen products plus the calibration lock for calibration packages
  or the immutable pilot lock for live packages.
- Produces blind packages without treatment identity and validates `review_result.v1`.
- Calibration is a hard precondition for live review, not for deterministic harness tests.

- [ ] **Step 1: Write evaluation and calibration tests**

Cover:

- pilot packages require a complete valid `pilot_lock.v1` and either its one
  locked `VALID` `SMOKE` attempt or one ordered locked `VALID` `LIVE` attempt,
  bound to the canonical lock digest with exactly the three locked treatments,
  exact attempt-class/index/ID and execution-command-digest lineage, explicit
  disjoint roots, a freshly re-frozen complete base matching the archive
  digest, and freshly re-frozen product manifests under the locked projection
  exclusions;
- block, package, calibration, and reviewer IDs used in joins are safe single
  path components;
- opaque label assignment is deterministic from the lock seed; labels appear
  in reviewer packages, while the label-to-treatment map remains controller-only;
- review packages include the task, a deterministic complete projected-tree
  base-to-final diff, selected final-file snapshots, and allowlisted check
  evidence. The diff includes unselected modifications, additions, deletions,
  and file type, mode, or symlink changes;
- packages exclude treatment IDs, treatment source, prompts, transcripts, call counts, elapsed time, cost, and label map;
- each raw canonical package manifest has a closed schema, unique normalized
  paths, package identity, and path/mode/size/digest rows verified in full
  before any top-level or per-dimension citation is accepted; package
  traversal rejects NUL paths and undeclared regular or non-regular nodes;
- the prospective calibration control lock binds its exact schema/version,
  round/revision and predecessor semantics, a closed four-field base identity
  (repository identity, revision identity, complete unexcluded archive digest,
  and projected product-manifest digest),
  task, reference patch, rubric, selected files, evaluator/oracle bytes,
  environment identity, check/evaluator classes, expected contrast, reviewers,
  package IDs, and mapping seed before package generation;
- the same lock contains one closed `reviewer_execution` object binding
  provider family, model, reasoning effort, tool policy, positive timeout,
  canonical resolved regular CLI entry path plus its exact digest/version,
  closed environment identity with a nonempty unique allowed-key list and
  credential-key subset, and the invocation-payload-schema digest;
- calibration construction requires an explicit caller-supplied
  `reviewer_execution` object, validates its CLI bytes and full closed shape,
  and rejects any difference from the prospective lock rather than supplying
  an ambient path, environment, provider, model, or timeout default;
- calibration package 1 is the separate `A0` evaluator-passing reference
  versus the unsolved `A0` base;
- package 2 reverses those labels while preserving candidate bytes;
- package 3 compares two byte-identical `A0` reference products;
- all six reviewer/package judgments use distinct session IDs, and no session
  receives more than one calibration package;
- the frozen A0 evaluator proves the reference passes and the base fails before
  reviewer packages are generated;
- no calibration package contains an `A1` reference or prior `A1` candidate;
- both reviewers must prefer the reference under both label orders;
- both reviewers must return `TIE` or `INDETERMINATE` for the identity package;
- a third reviewer cannot override failed calibration;
- at most one rubric/package revision is allowed; a second failed locked round
  yields `CALIBRATION_FAILED`;
- round 2 requires an explicit retained round-1/revision-0 lock, canonical
  controller mapping and explicit controller root, and exactly six prior
  reviews; the retained digest must match and full predecessor validation must
  produce a substantive reference-preference, label-order, or identity-control
  failure, never a passing, fabricated, malformed, or session-reuse result;
- the closed canonical controller mapping is read from its explicit root,
  contains the exact package and review-binding sets, and revalidates every
  evaluator, oracle, patch, rubric, reviewer-CLI, environment-identity,
  raw-evidence, package, and review file binding; the same two opaque labels
  have exact `REFERENCE/BASE`, `BASE/REFERENCE`, and
  `REFERENCE/REFERENCE` roles across the three ordered packages;
- live review ingestion binds the expected stable calibrated reviewer identity,
  rejects reused sessions globally, and rejects duplicate reviewer coverage
  within one block while permitting the same reviewer role on distinct blocks;
- live review ingestion requires a treatment guess for each opaque candidate
  while keeping the label map unavailable until sealing;
- evidence citations must name an exact manifest payload, optionally followed
  by a strict one-based inclusive `:line` or `:start-end` locator; the
  digest-verified base path and UTF-8 line bounds must resolve inside the
  supplied review package, while `manifest.json` remains non-citable package
  navigation metadata; the reviewer inspection contract exposes the citable
  list, navigation-only list, allowed forms, line convention, and exact-path
  precedence as structured data.

- [ ] **Step 2: Run collection and RED**

```bash
pytest --collect-only -q tests/experiments/test_lean_pilot_evaluation.py
pytest -q tests/experiments/test_lean_pilot_evaluation.py
```

Expected: missing evaluation module/rubric/reference patch and failing
lineage, full-tree-diff, calibration-lock, package-manifest, and reuse checks.

- [ ] **Step 3: Implement blind packages and calibration validation**

Use explicit, pairwise-disjoint roots and canonical archive-relative allowlists
only. Validate the full live lock/block pair before writing output, re-freeze
each product with the locked exclusions, and compute the blinded diff from the
complete projected base and final manifests. Selected final files remain an
allowlisted snapshot surface, not the diff boundary.

Treat the calibration lock as prospective controller apparatus, not as a fifth
cross-process record. Validate every lock field and bound byte/environment
identity before writing reviewer packages. Require the caller's exact closed
four-field base identity and freshly verify both the complete unexcluded base
archive and projected base manifest. Validate the separately caller-supplied
reviewer-execution object and its resolved CLI entry bytes against that lock
before writing output; Task 5 does not launch the reviewer.
Materialize the `A0` reference by
applying the frozen `a0-reference.patch` to
`examples/demo_task_linear_classifier_port`; dynamically load the bound oracle
and verify visible and hidden base `FAIL` / reference `PASS` before packaging.
Write a closed canonical package manifest binding every included payload and
store evaluator, oracle, patch, rubric, raw evaluator evidence, label mappings,
and review bindings only under the controller root.

For validation, re-read the canonical closed controller mapping from its
explicit controller root, require the exact package and six-review binding
sets, the common opaque-label pair with exact directional and identity roles,
and verify every named controller file. Round 1 must receive no predecessor.
Round 2 must receive the retained round-1/revision-0 lock, mapping, root, and
all six reviews explicitly; revalidate that complete round and accept only a
substantive calibration failure whose canonical digest and failed status match
the round-2 lock. These are controller inputs, not a fifth record.

`validate_calibration` must fail with one of:

```text
calibration_reference_not_preferred
calibration_label_order_inconsistent
calibration_identity_not_tie
calibration_reviewer_session_reused
```

- [ ] **Step 4: Write the evidence-based rubric**

Require dimensions for task completeness, behavioral correctness, maintainability, scope control, and evidence quality. Require file/path citations and permit `TIE`/`INDETERMINATE`. Do not mention `.orc`, coordinator, one-shot, expected winner, or process cost.
Require the reviewer to record treatment guesses only after the evidence-cited
quality judgment. State that `UNKNOWN` is valid and guesses do not affect the
judgment.

- [ ] **Step 5: Run GREEN**

```bash
pytest -q tests/experiments/test_lean_pilot_evaluation.py
```

Expected: PASS.

- [ ] **Step 6: Generate and execute calibration before live review**

Generate all three packages from the frozen `A0` base/reference products. For
each of two reviewer identities, run each package in a distinct fresh session:
six sessions and six review records per round. Validate them against the
canonical calibration-lock digest, controller mapping, rubric digest, raw
package-manifest digest, exact two-label order, and prospective session ledger.
The controller mapping must preserve the exact locked reviewer-execution object
and the controller-only CLI-entry file binding; the later launcher receives no
unlocked execution defaults.
The live `A1` products and any `A1` reference remain
unavailable to those sessions until calibration is sealed.

If the first calibration fails, preserve its lock, rubric, packages, and
records; revise the rubric/package once under a new digest; and pass its exact
lock, on-disk controller mapping/root, and six reviews to the six new
reviewer/package sessions under round 2/revision 1. The retained predecessor
must revalidate to a substantive reference-preference, label-order, or
identity-control failure and its canonical digest/status must match the retry
lock. Any second locked-round failure records
`CALIBRATION_FAILED`. The live evidence route stops before creating the pilot
lock. Continue Task 6's
provider-free reporting implementation, but do not enter Task 7. Never add
reviewers, relax the criterion, or expose live candidate products to force a
pass.

- [ ] **Step 7: Commit only Task 5 implementation and frozen rubric/lock**

```bash
git add orchestrator/experiments/evaluation.py \
  experiments/orc_effectiveness/lean_pilot/reviewers/rubric.md \
  experiments/orc_effectiveness/lean_pilot/calibration/calibration-lock.json \
  experiments/orc_effectiveness/lean_pilot/calibration/a0-reference.patch \
  tests/experiments/test_lean_pilot_evaluation.py
git commit -m "feat(experiments): calibrate blinded pilot review"
```

Generated reviewer responses remain external evidence unless the owner separately authorizes committing them.

---

## Task 6: Add Deterministic Reporting And Sample-Size Planning

**Files:**

- Create: `orchestrator/experiments/reporting.py`
- Modify: `scripts/experiments/lean_pilot.py`
- Create: `tests/experiments/test_lean_pilot_reporting.py`

**Interfaces:**

- Consumes only validated records.
- Produces deterministic `pilot_summary.v1` and Markdown view.
- Produces exact required non-tied `N` and fixed valid-block cap `M` only when
  every numeric decision parameter is supplied.

- [ ] **Step 1: Write reporting tests**

Cover:

- win/tie/indeterminate counts for both declared comparisons;
- treatment viability and failure-class counts;
- sole-viable treatment wins the method outcome even when the failed treatment
  has no blinded review;
- two nonviable treatments produce `TIE_NONVIABLE`, with any reviewable
  product-quality judgment retained separately;
- blinded product-quality review determines the method outcome only when both
  treatments are viable;
- reviewer agreement without deleting disagreements;
- material disagreement resolved by the one locked adjudicator when supplied,
  or retained as `INDETERMINATE` with both original reviews otherwise;
- treatment-guess accuracy/confusion is computed only after unblinding and
  cannot alter sealed judgments;
- unblinding rows exactly match the label mapping recomputed from the locked
  randomization seed, block ID, and treatment set, rejecting repermutation;
- exact reduced-fraction median elapsed/cost ratios with `UNKNOWN` propagation;
- exact input/output-token medians and ratios with `UNKNOWN` propagation;
- observed `CHECK_FAILURE`/`PROTOCOL_FAILURE` hard-contract rows preserve their
  execution evidence and `TREATMENT_OUTCOME_RETAINED` disposition without
  inferring a violated clause;
- treatment-specific failures remaining in the denominator;
- invalid/aborted blocks adjacent to, not inside, the valid denominator;
- deterministic JSON and Markdown regeneration;
- Markdown renders valid/excluded blocks, comparison counts, treatment
  statistics, review diagnostics, hard-contract findings, and every exact
  metric row from the validated summary;
- readiness is derived only as `STOP_APPARATUS_NOT_VIABLE`,
  `STOP_INSUFFICIENT_VALID_BLOCKS`, or
  `EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED`, independent of which treatment
  wins;
- exact-binomial superiority and non-tied-accrual known vectors;
- rejection when target rate is not greater than null rate;
- rejection of invalid probability/rate domains;
- canonical decimal CLI inputs parsed to `Fraction` without binary float;
- rejection of omitted alpha, power, target effect, tie-rate, accrual,
  invalid-attempt, cost, call-bound, or search-limit parameters;
- rejection with `sample_size_search_exhausted` when no `N` or `M` is found
  within the explicit search limit;
- no default ten-pair or total-block output.

Use the known sensitivity check:

```python
assert exact_binomial_tail(
    n=10,
    successes_at_least=9,
    rate=Fraction(1, 2),
) == Fraction(11, 1024)
```

- [ ] **Step 2: Run collection and RED**

```bash
pytest --collect-only -q tests/experiments/test_lean_pilot_reporting.py
pytest -q tests/experiments/test_lean_pilot_reporting.py
```

Expected: missing reporting module/CLI commands.

- [ ] **Step 3: Implement deterministic synthesis**

Do not infer missing outcomes. Load the exact smoke and ordered live
`block_attempt.v1` paths declared by the lock. Require one smoke record, live
records to form a contiguous prefix, exactly three nested executions for each
`VALID` attempt, and a missing live suffix only after three valid attempts have
accrued. A failed smoke admits no live attempt, and the direct
`build_pilot_summary` interface enforces the same prefix and no-post-third-valid
rules as the loader. The evidence root is canonical absolute and equal to the
lock; attempt IDs are safe single components; attempt records are regular
non-symlink files beneath that root. Preserve every `INVALID`, `ABORTED`, or
surviving `STARTED` attempt
adjacent to the denominator, reject a missing interior record, and require all
sealed review records through caller-supplied closed `ReviewBinding` rows and
all opaque-label mappings through caller-supplied closed
`UnblindingBinding` rows. Require exact coverage of each valid block, canonical
record digests, locked reviewer/rubric identity, one package manifest per
block, two initial reviewers, and at most one locked adjudicator on material
disagreement; without it, retain the initial reviews and emit
`INDETERMINATE`. Authenticate every unblinding row by recomputing the exact
locked seed/block/treatment label map. Reject extra, missing, duplicate,
repermuted, unsafe-path, or mismatched rows. Verify execution cost currency
against the lock and permit neither-viable product-quality review only when
both products were frozen. These controller inputs are explicit evidence
bindings, not a fifth record kind or a discovered registry. The four-record
schema fixes the exact metric/diagnostic row sets and the record validator
enforces their arithmetic/set invariants. Render every substantive typed
surface solely from the summary object. CLI outputs are distinct new canonical
paths outside evidence/input overlap and use atomic no-overwrite publication.

- [ ] **Step 4: Implement exact fixed-N and accrual-cap planning**

Use `fractions.Fraction`, `math.comb`, and exhaustive integer search for both
the one-sided critical win count and the non-tied accrual probability. Parse
canonical decimal CLI strings directly as exact fractions; never round through
`float`. The CLI command is:

```text
plan-sample-size \
  --null-rate DECIMAL \
  --target-rate DECIMAL \
  --alpha DECIMAL \
  --power DECIMAL \
  --max-tie-rate DECIMAL \
  --accrual-probability DECIMAL \
  --max-invalid-attempts INTEGER \
  --max-cost-ratio DECIMAL \
  --min-calls-per-block INTEGER \
  --max-calls-per-block INTEGER \
  --search-limit INTEGER
```

Print the smallest required non-tied `N`, critical win count, exact achieved
power, the smallest fixed valid-block cap `M`, exact achieved accrual
probability, cost-ratio threshold, invalid-attempt cap, and provider-call range
derived from the supplied per-block bounds. Reaching `M` without `N` non-tied
comparisons yields `INSUFFICIENT_EVIDENCE`; never extend after unblinding. Do
not write a prospective lock automatically.

- [ ] **Step 5: Run GREEN**

```bash
pytest -q tests/experiments/test_lean_pilot_reporting.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6 paths**

```bash
git add orchestrator/experiments/reporting.py \
  scripts/experiments/lean_pilot.py \
  tests/experiments/test_lean_pilot_reporting.py
git commit -m "feat(experiments): synthesize lean pilot evidence"
```

---

## Task 6A: Enforce The Pre-Calibration Module-Size Gate

**Status:** complete; focused verification and scoped independent quality
re-review approved.

**Files:**

- Keep as thin facades: `orchestrator/experiments/runner.py`,
  `orchestrator/experiments/evaluation.py`,
  `orchestrator/experiments/reporting.py`
- Create: the private `_runner_*`, `_evaluation_*`, and `_reporting_*` modules
  listed in the planned layout
- Modify: the three corresponding focused test modules only where internal
  monkeypatch ownership moved
- Create: `tests/experiments/test_lean_pilot_module_layout.py`

This quality gate was added before calibration after the original three
facades reached 1,447, 2,117, and 868 physical lines. It changes code
ownership only: the planned public interfaces, four record kinds, run-block
signature, behavior, and evidence contract remain unchanged.

- [x] **Step 1: Establish the failing structural gates**

Require exact public-facade compatibility, scan the complete runner private
module set for prohibited provider-isolation imports or shell invocation, and
require every production module in `orchestrator/experiments/` to contain at
most 500 physical lines.

- [x] **Step 2: Extract existing responsibilities without duplication**

Split runner apparatus/preflight/execution/block ownership, evaluation
live/calibration/ingestion ownership, and reporting
planning/loading/review/metrics/synthesis/rendering ownership into private
modules. Do not add a framework, hidden registry, record kind, or public API.

- [x] **Step 3: Run focused and adjacent verification**

Collect the new layout test, run the runner, evaluation, reporting, contracts,
workspace, and parity/integration selectors, compile every production module,
and record fresh line counts. No calibration or live evidence may run during
this step.

- [x] **Step 4: Obtain the scoped independent quality re-review**

The reviewer checks responsibility cohesion, absence of duplicate logic and
cycles, exact facade/API preservation, complete runner static scanning, the
500-line gate, and focused behavior preservation. Calibration and Task 7 stay
blocked until this review approves.

---

## Task 6B: Close The Task 7 Readiness Contracts

**Plan:** `docs/plans/2026-07-27-orc-effectiveness-lean-pilot-task7-readiness-amendment.md`

**Execution boundary:** This is the final provider-free reusable-contract gate
before Task 7's pilot-specific controller slice. It does not launch the smoke
or a live A1 attempt and does not touch the paused provider-isolation
implementation.

- [x] Add RED contract tests for Git-subtree identity, closed apparatus
  visibility, derived digests, review/evaluator bundles, and provider-policy
  binding.
- [x] Implement rootless `commit:subtree` allocation and verify the locked tree,
  archive, source task, and staged task bytes.
- [x] Stage only the explicit treatment-asset subset and reject extra
  control-root nodes.
- [x] Permit locked `VALID SMOKE` package construction without making smoke
  reviewable or scorable.
- [x] Publish each smoke/live label map once at the deterministic
  `label-maps/<package-id>.json` path beneath the locked evidence root, without
  overwrite or symlink following, and retain prior block maps.
- [x] Bind reviewer slots exactly, allow stable reviewer identities across
  blocks, and preserve global session freshness at ingestion and synthesis.
- [x] Require caller allowlists to equal the locked selected-file and derived
  check-evidence paths.
- [x] Keep every `orchestrator/experiments` production module at or below 500
  physical lines.
- [x] Run focused and broad verification and obtain one scoped independent
  contract/code re-review before evidence execution.

---

## Task 7: Run The Apparatus Smoke And Bounded A1 Pilot

**Files:**

- Create:
  `experiments/orc_effectiveness/lean_pilot/apparatus-source-map.json`
- Create:
  `experiments/orc_effectiveness/lean_pilot/evaluation/nanobragg-entrypoint.json`
- Create:
  `experiments/orc_effectiveness/lean_pilot/reviewers/live-review-command.json`
- Create:
  `experiments/orc_effectiveness/lean_pilot/reviewers/live-review-output.schema.json`
- Create: `orchestrator/experiments/_pilot_prepare.py`
- Create: `orchestrator/experiments/_pilot_prepare_support.py`
- Create: `orchestrator/experiments/_pilot_prepare_validation.py`
- Create: `orchestrator/experiments/_pilot_evidence.py`
- Create: `orchestrator/experiments/_pilot_evidence_support.py`
- Create: `orchestrator/experiments/_pilot_evaluator_apparatus.py`
- Create: `orchestrator/experiments/_pilot_evaluator_process.py`
- Create: `orchestrator/experiments/_pilot_review.py`
- Create: `orchestrator/experiments/_pilot_review_support.py`
- Create: `orchestrator/experiments/_pilot_review_schema.py`
- Create: `orchestrator/experiments/_pilot_review_assets.py`
- Create: `orchestrator/experiments/_pilot_review_execution.py`
- Create: `orchestrator/experiments/_pilot_review_bindings.py`
- Create: `orchestrator/experiments/_pilot_controller.py`
- Create: `orchestrator/experiments/_pilot_controller_state.py`
- Create: `orchestrator/experiments/_runner_quiescence.py`
- Modify: `orchestrator/experiments/_runner_execution.py`
- Modify: `orchestrator/experiments/_runner_block.py`
- Modify: `scripts/experiments/lean_pilot.py`
- Test: `tests/experiments/test_lean_pilot_prepare.py`
- Test: `tests/experiments/test_lean_pilot_evidence.py`
- Test: `tests/experiments/test_lean_pilot_review.py`
- Test: `tests/experiments/test_lean_pilot_controller.py`
- Test: `tests/experiments/test_lean_pilot_controller_state.py`
- Test: `tests/experiments/test_lean_pilot_cli.py`
- Test: `tests/experiments/test_lean_pilot_runner.py`
- Test fixture:
  `tests/experiments/fixtures/lean_pilot/fake_reviewer_cli.py`
- Test fixture:
  `tests/experiments/fixtures/lean_pilot/spawning_evaluator.py`
- Create: `experiments/orc_effectiveness/lean_pilot/pilot-lock.json`
- Create: `docs/reports/2026-07-26-orc-effectiveness-lean-pilot.md`
- Modify only if status/routing changed: `docs/index.md`
- Modify only if status/routing changed: `docs/design/README.md`
- Modify only if status/routing changed: `docs/capability_status_matrix.md`

**Execution boundary:** This task first implements a provider-free,
pilot-specific controller, then creates evidence. It adds no public API,
record kind, reusable framework, or module above 500 physical lines. It does
not modify reusable runtime, Workflow Lisp, provider-isolation, or PtychoPINN
product code.

- [ ] **Step 1: Implement the pilot-specific controller, require passing calibration, then freeze the pilot lock before any real-provider outcome**

Enter this task only with a passing locked calibration. If both calibration
rounds failed, preserve `CALIBRATION_FAILED`, complete Task 6 and its
verification, route that terminal status, and skip every remaining Task 7 step.

Keep `scripts/experiments/lean_pilot.py` as the thin command facade and add only
`prepare` and `execute`. Put source/control-root/lock preparation, copied-product
evaluation/package preparation, calibrated review/binding publication, and
bounded sequencing respectively in `_pilot_prepare.py`, `_pilot_evidence.py`,
`_pilot_review.py`, and `_pilot_controller.py`. Keep those planned surfaces
thin and place their boring validation, execution, and binding helpers in the
Task 7 private support modules listed above. Keep every private production
module at or below 500 physical lines and add no export from
`orchestrator.experiments`.

`prepare` receives explicit source-map, repository-root, full-revision,
fresh-control-root, fresh-evidence-root, calibration-seal, and lock-output
paths. `execute` receives the immutable lock plus explicit disjoint work,
evaluation-copy, package, and canonical reviewer-environment paths. Neither
command may infer one of those inputs.

Before authoring the lock, require a caller-supplied canonical absolute path
for a fresh external apparatus control root. Reject the path if it already
exists or if materialization would encounter any undeclared destination.
Create the root and deterministically copy the frozen Task 4 sources into these
exact flat apparatus paths:

| Canonical authoritative source | Derived apparatus path |
| --- | --- |
| `scripts/experiments/conventional_coordinator.py` | `treatment_driver.py` |
| `workflows/experiments/repository_task_pilot/task_loop.orc` | `task_loop.orc` |
| `workflows/experiments/repository_task_pilot/prompts/discover.md` | `prompts/discover.md` |
| `workflows/experiments/repository_task_pilot/prompts/plan.md` | `prompts/plan.md` |
| `workflows/experiments/repository_task_pilot/prompts/review_plan.md` | `prompts/review_plan.md` |
| `workflows/experiments/repository_task_pilot/prompts/revise_plan.md` | `prompts/revise_plan.md` |
| `workflows/experiments/repository_task_pilot/prompts/implement.md` | `prompts/implement.md` |
| `workflows/experiments/repository_task_pilot/prompts/review_implementation.md` | `prompts/review_implementation.md` |
| `workflows/experiments/repository_task_pilot/prompts/fix_implementation.md` | `prompts/fix_implementation.md` |
| `experiments/orc_effectiveness/lean_pilot/control/providers.json` | `providers.json` |
| `experiments/orc_effectiveness/lean_pilot/control/prompts.json` | `prompts.json` |
| `experiments/orc_effectiveness/lean_pilot/control/commands.json` | `commands.json` |
| `experiments/orc_effectiveness/lean_pilot/control/runtime-control.json` | `runtime-control.json` |
| `experiments/orc_effectiveness/lean_pilot/tasks/a1.md` | `task.md` |
| `experiments/orc_effectiveness/lean_pilot/treatments/direct.json` | `treatments/direct.json` |
| `experiments/orc_effectiveness/lean_pilot/treatments/coordinator.json` | `treatments/coordinator.json` |
| `experiments/orc_effectiveness/lean_pilot/treatments/orc.json` | `treatments/orc.json` |

`experiments/orc_effectiveness/lean_pilot/apparatus-source-map.json` is the
single closed mapping. Read repository sources from one caller-named full Git
commit, never the live working tree. It names the seventeen treatment-visible
destinations in the table above and classifies the following controller-only
closure explicitly:

- `review/rubric.md`, `review/calibration-seal.json`, and
  `review/calibration-lock.json`;
- `evaluation/config.json`, the nanoBragg evaluator module at its existing
  repository-shaped relative path, and exactly its runtime `cases.json`,
  expected-tensor, and hidden-input fixtures; and
- `review/reviewer-command.json` plus
  `review/review-result.schema.json`.

Do not discover or infer these assets from repository layout. Verify every
derived regular file is byte-identical to its named canonical source, reject
missing or extraneous files, and generate `apparatus.asset_manifest` only from
that closed tree. Bind the exact `treatment_asset_paths` subset; evaluator,
rubric, calibration, and reviewer-command assets remain controller-only.
After manifest generation, treat the external control root as immutable
through smoke and every live attempt. This is derived apparatus
materialization, not a second authoritative source, CWD/package inference,
hidden registry, fifth experiment record, or tracked flat snapshot.

Bind:

- `valid_block_count: 3`;
- `max_live_attempt_count: 5`;
- one opaque `smoke_id` and an ordered five-element `live_attempt_ids` list;
- `claim_level: exploratory_controlled_task`;
- one canonical absolute `apparatus.control_root` and every required A1 task,
  provider, prompt, command-boundary, treatment-command, visible-check, and
  evaluator/config asset as a unique canonical relative path plus digest in
  `apparatus.asset_manifest`;
- a durable repository identity plus explicit canonical repository root,
  commit, source-subtree path, exact Git tree object, rootless archive digest,
  and task path inside that subtree;
- exact treatment-visible and controller-only asset partitioning,
  per-treatment source-asset closures, and derived source digests;
- task/provider/prompt/command-boundary role paths, each naming one manifest
  entry, with the task entry digest equal to `task.brief_digest`;
- exact DIRECT, COORDINATOR, and ORC source/command digests plus three distinct
  treatment `command_config_path` values, each naming the manifest entry whose
  digest equals that treatment's command digest;
- this exact prospective provider policy object:

  ```json
  {
    "family": "codex-cli",
    "model": "gpt-5.5",
    "reasoning_effort": "high",
    "tool_policy": "codex_unrestricted_workspace",
    "timeout_milliseconds": 1800000,
    "currency": "USD"
  }
  ```

  Its canonical digest is
  `sha256:f6894af0098ad618ceaf74d6e46a76ab0519549d15f31f8b8685e40862bd0b25`;
  the immutable pilot lock is the runtime authority for the object;
- environment identity and the complete nonempty allowed-key list, with no
  ambient environment key implied, plus the unique allowed credential-key
  subset excluding `HOME` and `TMPDIR`;
- the exact launcher partition: treatment configurations supply only `PATH`
  and `PYTHONUNBUFFERED`, the controller supplies `HOME` and `TMPDIR`, and
  `SecretsManager` alone supplies credential-backed `CODEX_HOME`; the lock
  allowlist is exactly those five names and its sole credential key is
  `CODEX_HOME`;
- explicit visible-check argv and positive timeout;
- exactly two stable calibrated reviewer IDs, selected-final-file and
  permitted-check-evidence-name allowlists, reviewer rubric and passing
  calibration-seal paths/digests, controller-only evaluator/reviewer-command
  bundle bindings, and `INDETERMINATE_ON_DISAGREEMENT`;
- deterministic randomization seed;
- explicit canonical relative product-projection exclusions;
- positive maximum-start-skew and quiescence-grace bounds; and
- evidence root outside candidate products.

The lock names every input explicitly. Task 7 and the runner may not infer any
asset from CWD, package installation, repository layout, or a fixed path. On
each block, Task 3 verifies every manifest file and digest beneath the locked
control root, validates the three unmodified standard extern manifests, and
requires each prompt extern to bind a verified `asset_file` before checking all
role/treatment/environment bindings and writing `STARTED`, allocating, or
launching. It then stages only the verified assets named by
`apparatus.treatment_asset_paths` under each arm's private apparatus root at
the same relative path; controller-only assets and the original control root
are not passed to any treatment.

Validate:

```bash
python scripts/experiments/lean_pilot.py validate-lock \
  --lock experiments/orc_effectiveness/lean_pilot/pilot-lock.json
```

Expected: exits `0` and prints the canonical lock digest.

- [ ] **Step 2: Run one unscored real-provider apparatus smoke**

Use one fresh provider/model allocation per arm and the same three treatments
on A1 under the exact locked closed environment and standard manifests. The
provider-free actual-launcher gate from Task 4 is a reviewed prerequisite, not
a post-lock block; its test-only provider executable and `PATH` override are
not apparatus assets or permitted here. The mechanical smoke gate requires all
three nested executions, process-group quiescence, frozen products, parsed
call accounting, and generated blind packages; it does not score task quality
and does not enter the live denominator.
The smoke package cannot be bound to a `review_result.v1` or summary input.

Treatment-specific failure is preserved and the locked live series proceeds
without treatment changes. A shared apparatus defect yields
`STOP_APPARATUS_NOT_VIABLE`; repairing it requires a separately locked pilot,
not a second smoke or mutation of this denominator.

Run the verified hidden evaluator only on a fresh projected copy whose source
and copied manifests both equal the committed product digest. Evaluator
runtime uses a fresh controller-owned tree containing the exact verified
module/fixture closure at its repository-relative paths; after verification it
does not execute or read those bytes from the locked control root.
Publish the immutable package-preparation intent before any evaluation-copy,
evaluator, or package mutation. A matching intent without completion requires
a separately locked pilot. A matching completion may reload without
re-execution only after the complete manifest-declared package tree is
revalidated by path, mode, size, and digest with no missing, extra, symlinked,
or other non-regular nodes, and the label map and evaluator artifacts also
revalidate.
Evaluator `PASS`/`FAIL` is candidate evidence. If evaluator
execution/output validation or blind-package construction fails after
`run_block` has already committed a `VALID` smoke, preserve the attempt and
incident artifacts, emit no fabricated summary, and require a separately
locked pilot. Do not rewrite the committed attempt or add a fifth record to
force `STOP_APPARATUS_NOT_VIABLE`.

- [ ] **Step 3: Run up to five live attempts to obtain three valid A1 blocks**

Launch each attempt with the next ordered opaque live ID from the immutable
lock. Preserve every `INVALID`, `ABORTED`, or surviving `STARTED` record; each
consumes its ordered ID and is never retried. Do not launch the next ID until
process-group quiescence is established. The runner rejects reused, skipped,
or out-of-order IDs before allocation.

Stop when three valid blocks accrue or after five live attempts, whichever
comes first. Do not extend after viewing any result. Failure to accrue three
valid blocks yields `STOP_INSUFFICIENT_VALID_BLOCKS`. `INVALID`, `ABORTED`,
and surviving `STARTED` records consume their ordered IDs and are never rerun.
Prepare hidden-evaluator evidence and the immutable per-block package/label map
immediately for each valid attempt, but do not start live review until
denominator collection is complete. The post-`VALID` apparatus-defect rule
from Step 2 applies identically to live attempts.

- [ ] **Step 4: Conduct blinded live review**

For every valid block, generate opaque packages and obtain one fresh session
for each of the two stable calibrated reviewer identities. The locked
`INDETERMINATE_ON_DISAGREEMENT` policy uses no uncalibrated adjudicator. Seal
all initial reviews before unblinding treatment/cost evidence.

Join each result to the exact package ID, canonical package-manifest digest,
reviewer ID, rubric digest, review class, and manifest candidate-label order.
The live schema requires exactly three candidates, all five dimensions for
each, and all three unordered candidate pairs exactly once. Missing,
duplicate, reversed-duplicate, or foreign-label pairs fail closed.

Publish one immutable launch intent per reviewer slot. Validation failure
before that intent consumes no session. Require the content-bound live schema
to pass the exact calibration-supported structural contract and reject
unsupported or unproven schema keywords before staging or intent. Stage the
already-verified live schema and rubric bytes at deterministic
controller-runtime paths outside the closed candidate package, and use only
those staged paths in the CLI and prompt. Exact partial staging may complete on
pre-intent re-entry; staged drift fails closed before intent. Once the provider
starts, never relaunch the slot; a retained complete terminal transport may be
finalized provider-free, while an incomplete slot halts without unblinding or
summary. Publish canonical review bindings for all required reviews before
reading any label-map content and publishing canonical unblinding bindings. If
five attempts yield fewer than three valid blocks, still review every valid
block before generating the truthful shortfall summary.

- [ ] **Step 5: Generate the authoritative pilot summary**

Generate JSON first, then Markdown:

```bash
python scripts/experiments/lean_pilot.py summarize \
  --lock experiments/orc_effectiveness/lean_pilot/pilot-lock.json \
  --evidence-root <external-evidence-root> \
  --review-bindings <external-evidence-root>/review-bindings.json \
  --unblinding-bindings <external-evidence-root>/unblinding-bindings.json \
  --json-output <fresh-external-summary-root>/pilot-summary.json \
  --markdown-output docs/reports/2026-07-26-orc-effectiveness-lean-pilot.md
```

The summary root is a fresh canonical location outside the evidence root and
all inputs. Both output paths must be absent before publication.

The report must state one of:

- `STOP_APPARATUS_NOT_VIABLE`;
- `STOP_INSUFFICIENT_VALID_BLOCKS`; or
- `EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED`.

It must not claim that ORC, `.orc`, or Workflow Lisp is generally effective.
The deterministic summary does not choose whether to stop, repeat, or invest.
That owner decision occurs after the final evidence review and is recorded in
the next route, not backfilled into `pilot_summary.v1`.

- [ ] **Step 6: Obtain the final evidence review gate**

One independent reviewer checks:

- exact lock/denominator adherence;
- calibration and blinding;
- treatment-failure accounting;
- parity claim boundary;
- cost/usage unknown handling;
- deterministic report regeneration; and
- absence of prospective/general claims.

A second review is required only if the first identifies a concrete contract violation after results exist; it verifies the repair and that the definition digest changed when required. Do not require a second ceremonial approval when the first review approves.

- [ ] **Step 7: Run final verification**

Run focused checks first:

```bash
pytest --collect-only -q tests/experiments
pytest -q tests/experiments
python scripts/experiments/lean_pilot.py validate-lock \
  --lock experiments/orc_effectiveness/lean_pilot/pilot-lock.json
```

Because this adds a reusable package and workflow, run the affected broad suite in tmux:

```bash
pytest -q -n 16 --dist=worksteal
```

Record exact pass/fail/skip counts. Do not weaken checks to close the report.

- [ ] **Step 8: Route the observed status and commit reviewed paths**

Update indexes/status only with facts established by the run. Stage the frozen lock, source/rubric assets, implementation, tests, and report; do not stage external raw provider logs or unrelated shared-tree changes.

Use a commit message describing the observed result rather than implying a win, for example:

```bash
git commit -m "evidence(experiments): record lean orc effectiveness pilot"
```

---

## Completion Definition

The reusable first-tranche implementation is complete when:

- all four record contracts validate;
- archive, runner, evaluation, parity, and reporting focused suites pass;
- the protocol/runner and treatment-parity gates approve before live outcomes;
- affected broad verification has fresh evidence; and
- no prospective PtychoPINN implementation, deferred estimand, or
  provider-isolation completion was added.

Evidence execution then completes at exactly one truthful terminal:

1. `CALIBRATION_FAILED` — both locked calibration rounds failed; preserve all
   packages/reviews and create no pilot lock;
2. `STOP_APPARATUS_NOT_VIABLE` — calibration and the reviewed provider-free
   actual-launcher gate passed, but the one locked real-provider smoke had a
   shared apparatus failure;
3. `STOP_INSUFFICIENT_VALID_BLOCKS` — the smoke passed, fewer than three valid
   live blocks accrued within five attempts, and the reviewed summary preserves
   every attempt; or
4. `EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED` — the smoke and exactly three
   valid live blocks completed, the reviewed deterministic summary preserves
   all failures, disagreements, guesses, invalid/aborted attempts, and unknown
   usage/cost, and the claim remains task-specific and exploratory.

A DIRECT-favorable, tied, indeterminate, non-discriminating, or ORC-nonviable
result is valid evidence completion. The summary never chooses the investment
decision. After `EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED`, the owner may stop,
commission a newly locked controlled-pilot revision, or authorize a separate
prospective `F1`/`F2` design by supplying the numeric decision policy. No other
route authorizes prospective work.
