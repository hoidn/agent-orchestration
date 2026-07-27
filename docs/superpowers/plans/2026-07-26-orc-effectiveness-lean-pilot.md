# `.orc` Effectiveness Lean Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking. Independent review occurs only at the protocol/runner, treatment-parity, and final-evidence gates named below; do not create per-step review ceremonies.

**Goal:** Build and run the smallest three-treatment controlled pilot that can decide whether a separately planned prospective PtychoPINN `.orc` versus one-shot experiment is warranted.

**Architecture:** Add five focused `orchestrator.experiments` modules and one thin CLI. Freeze four record contracts, materialize three byte-identical archive-backed workspaces, launch `DIRECT`, `COORDINATOR`, and `ORC` concurrently, freeze products, calibrate blinded reviewers, and run at most five live `A1` attempts to obtain three valid exploratory blocks. The coordinator is frozen and parity-tested against the `.orc` topology before any live outcome.

**Tech Stack:** Python 3, `pytest`, `jsonschema`, `tarfile`, `subprocess`, SHA-256 canonical JSON, Workflow Lisp, existing provider CLIs, and JSON evidence.

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
- Do not add a persistent lifecycle engine, resume, retries around whole treatment runs, database, registry, dashboard, or schema per intermediate event.
- Do not implement `F1`, `F2`, `E2`, `E4`, `E5`, or `E6` in this plan.
- Use TDD for reusable code. If a task adds a test module, run `pytest --collect-only` before its tests.
- Tests assert contracts and behavior, never literal prompt wording.

---

## Planned File Layout

```text
orchestrator/experiments/
  __init__.py
  contracts.py       # one packaged schema, canonical JSON, four record validators
  workspace.py       # git-archive materialization and deterministic product freeze
  runner.py          # one in-memory three-treatment block; no persistent lifecycle
  evaluation.py      # blind packages, calibration gate, result ingestion
  reporting.py       # deterministic pilot summary and exact sample-size planning
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
def build_blind_packages(*, lock: Mapping[str, object], block: Mapping[str, object], output_root: Path) -> dict[str, Path]: ...
def validate_calibration(reviews: Sequence[Mapping[str, object]]) -> None: ...
def ingest_review(path: Path, expected_lock_digest: str) -> dict[str, object]: ...

# orchestrator/experiments/reporting.py
@dataclass(frozen=True)
class ExactSampleSizePlan: ...
def build_pilot_summary(*, lock: Mapping[str, object], block_attempts: Sequence[Mapping[str, object]], reviews: Sequence[Mapping[str, object]]) -> dict[str, object]: ...
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
one narrow deterministic semantic check for manifest-path uniqueness, role and
treatment path references, distinct treatment command paths, and the task and
treatment digest equalities. `validate_record` does not inspect the filesystem;
`load_record` receives the same semantic check through `validate_record`.

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

- materializing the same commit three times yields byte-identical manifests;
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
    ["git", "-C", str(repo), "archive", "--format=tar", commit],
    check=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
).stdout
```

Open the bytes with `tarfile.open(fileobj=io.BytesIO(archive), mode="r:")`.
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
- Stages every verified manifest asset for each arm under one private
  controller-owned apparatus root while preserving its normalized relative
  path; the original `apparatus.control_root` is never candidate-visible.
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
- every verified asset is staged for every arm at its manifest-relative path,
  and launch remains independent of CWD, package location, and the original
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
pass. Stage every verified manifest asset under each arm's private
`apparatus_root`, preserving the normalized relative path. Bind the three
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
- no resume/recovery lifecycle machinery beyond the single atomic
  `STARTED`-to-terminal attempt record;
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

- opaque label assignment is deterministic from the lock seed but absent from reviewer packages;
- review packages include task, base-to-final diff, selected final files, and allowed check evidence;
- packages exclude treatment IDs, treatment source, prompts, transcripts, call counts, elapsed time, cost, and label map;
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
- live review ingestion rejects a reviewer/session reused from calibration or another live review;
- live review ingestion requires a treatment guess for each opaque candidate
  while keeping the label map unavailable until sealing;
- evidence citations must resolve inside the supplied review package.

- [ ] **Step 2: Run collection and RED**

```bash
pytest --collect-only -q tests/experiments/test_lean_pilot_evaluation.py
pytest -q tests/experiments/test_lean_pilot_evaluation.py
```

Expected: missing evaluation module/rubric/lock.

- [ ] **Step 3: Implement blind packages and calibration validation**

Use archive-relative paths only. Materialize the `A0` reference by applying the
frozen `a0-reference.patch` to
`examples/demo_task_linear_classifier_port`; verify it passes the existing
linear-classifier evaluator while the unmodified base fails. Write a package
manifest binding every included file digest. Keep the label map in the
controller evidence root and never copy it into reviewer roots.

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
calibration lock. The live `A1` products and any `A1` reference remain
unavailable to those sessions until calibration is sealed.

If the first calibration fails, preserve its lock, rubric, packages, and
records; revise the rubric/package once under a new digest; and run six new
reviewer/package sessions. If the second round fails, record
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
- treatment-guess accuracy/confusion is computed only after unblinding and
  cannot alter sealed judgments;
- exact reduced-fraction median elapsed/cost ratios with `UNKNOWN` propagation;
- treatment-specific failures remaining in the denominator;
- invalid/aborted blocks adjacent to, not inside, the valid denominator;
- deterministic JSON and Markdown regeneration;
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
accrued. Preserve every `INVALID`, `ABORTED`, or surviving `STARTED` attempt
adjacent to the denominator, reject a missing interior record, and require all
sealed review records named by the lock. Render Markdown solely from the
summary object.

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

## Task 7: Run The Apparatus Smoke And Bounded A1 Pilot

**Files:**

- Create: `experiments/orc_effectiveness/lean_pilot/pilot-lock.json`
- Create: `docs/reports/2026-07-26-orc-effectiveness-lean-pilot.md`
- Modify only if status/routing changed: `docs/index.md`
- Modify only if status/routing changed: `docs/design/README.md`
- Modify only if status/routing changed: `docs/capability_status_matrix.md`

**Execution boundary:** This task creates evidence. It does not modify reusable runtime, Workflow Lisp, provider-isolation, or PtychoPINN product code.

- [ ] **Step 1: Require passing calibration, then freeze the pilot lock before any real-provider outcome**

Enter this task only with a passing locked calibration. If both calibration
rounds failed, preserve `CALIBRATION_FAILED`, complete Task 6 and its
verification, route that terminal status, and skip every remaining Task 7 step.

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

Task 5 adds its evaluator, rubric, calibration, and other review/config assets
through a separately explicit mapping before this step is executed; do not
discover or infer them from repository layout. Verify every derived regular
file is byte-identical to its named canonical source, reject missing or
extraneous files, and generate `apparatus.asset_manifest` only from that closed
tree. After manifest generation, treat the external control root as immutable
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
- task/provider/prompt/command-boundary role paths, each naming one manifest
  entry, with the task entry digest equal to `task.brief_digest`;
- exact DIRECT, COORDINATOR, and ORC source/command digests plus three distinct
  treatment `command_config_path` values, each naming the manifest entry whose
  digest equals that treatment's command digest;
- provider/model/effort/tool/timeout policy;
- environment identity and the complete nonempty allowed-key list, with no
  ambient environment key implied, plus the unique allowed credential-key
  subset excluding `HOME` and `TMPDIR`;
- explicit visible-check argv and positive timeout;
- reviewer rubric and passing calibration digests;
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
launching. It then stages every verified asset under each arm's private
apparatus root at the same relative path; the original control root is not
passed to any treatment.

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

Treatment-specific failure is preserved and the locked live series proceeds
without treatment changes. A shared apparatus defect yields
`STOP_APPARATUS_NOT_VIABLE`; repairing it requires a separately locked pilot,
not a second smoke or mutation of this denominator.

- [ ] **Step 3: Run up to five live attempts to obtain three valid A1 blocks**

Launch each attempt with the next ordered opaque live ID from the immutable
lock. Preserve every `INVALID`, `ABORTED`, or surviving `STARTED` record and
advance to the next ID only for predeclared shared contrast-breaking faults.
The runner rejects reused, skipped, or out-of-order IDs before allocation.

Stop when three valid blocks accrue or after five live attempts, whichever
comes first. Do not extend after viewing any result. Failure to accrue three
valid blocks yields `STOP_INSUFFICIENT_VALID_BLOCKS`.

- [ ] **Step 4: Conduct blinded live review**

For every valid block, generate opaque packages and obtain two fresh independent reviews. Use a third blinded adjudicator only for material disagreement. Seal all initial reviews before unblinding treatment/cost evidence.

- [ ] **Step 5: Generate the authoritative pilot summary**

Generate JSON first, then Markdown:

```bash
python scripts/experiments/lean_pilot.py summarize \
  --lock experiments/orc_effectiveness/lean_pilot/pilot-lock.json \
  --evidence-root <external-evidence-root> \
  --json-output <external-evidence-root>/pilot-summary.json \
  --markdown-output docs/reports/2026-07-26-orc-effectiveness-lean-pilot.md
```

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
