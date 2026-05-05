# Transparent Managed Jobs, Slurm, and GPU Routing Design

## Purpose

Agents should be able to create, edit, and run ordinary Python study commands
without manually remembering Slurm, GPU allocation, or managed-job policy. On a
local workstation, ordinary commands should run locally. On NERSC or another
Slurm GPU system, the same commands should submit, poll, resume, and verify
Slurm jobs transparently when they are classified as heavy training or
evaluation entrypoints.

The goal is to move cluster and GPU launch mechanics out of scientific scripts
and out of provider memory. Study scripts keep owning science, model configs,
metrics, and artifact writing. Managed-job infrastructure owns local versus
Slurm execution, GPU resource requests, job state, polling, resume, and terminal
artifact verification.

## Design Summary

The design has five pieces:

1. `run_managed_job`: a deterministic runner that executes one classified job
   with backend `local`, `slurm`, or `auto`.
2. managed command shims: especially a `python` shim that routes classified
   Python entrypoints through `run_managed_job` and falls through for everything
   else.
3. `provider_guard`: a runtime-owned wrapper used by managed provider steps to
   start a file watcher, install command shims in `PATH`, and record an audit.
4. `managed_jobs` provider-step DSL semantics: a declarative step modifier that
   asks the runtime to prepare the audit surface, wrap the selected provider
   command, run deterministic recovery after success/failure/timeout, and make
   resume re-enter recovery instead of relaunching the provider.
5. managed-job policy: repo-owned YAML describing roots, conventions, explicit
   local/managed overrides, Slurm resource defaults, and auto-classified scripts.

The agent experience remains ordinary:

```bash
python scripts/studies/run_pdebench_image128_suite.py ...
```

On a local machine this runs locally. On NERSC with `MANAGED_JOB_BACKEND=auto`
or `slurm`, the shim routes it through the managed-job runner if the command is
classified. Non-training commands, tests, `compileall`, and inline Python snippets
fall through to the real Python.

## Interception Boundary

The first version is transparent for provider-launched commands that resolve
through the provider process `PATH`. It is not a full filesystem or kernel-level
execution monitor.

Provider guard installs shims for:

- `python`;
- `python3`;
- `torchrun`;
- `conda`;
- `uv`.

The shims handle these launch forms:

- `python path/to/script.py ...`;
- `python3 path/to/script.py ...`;
- `python -m package.train ...`;
- `python3 -m package.train ...`;
- `torchrun path/to/script.py ...`;
- `torchrun -m package.train ...`;
- `conda run ... python path/to/script.py ...`;
- `conda run ... python -m package.train ...`;
- `uv run python path/to/script.py ...`;
- `uv run python -m package.train ...`;
- `uv run torchrun path/to/script.py ...`.

The shims delegate immediately to the real executable for unsupported forms.
They also delegate when `MANAGED_JOB_ACTIVE=1` is set, so commands launched
inside a managed job do not recursively resubmit themselves.

For nested environment launchers, support means the outer shim parses and routes
the inner payload before delegating. The managed `conda` shim must parse
supported `conda run ... <payload>` forms, identify the payload command
(`python`, `python3`, or `torchrun`), classify the target script/module, and
route the whole original `conda run ...` argv through `run_managed_job` when the
target is managed. It must not simply exec real `conda` and hope the inner
`python` resolves through the shim. The managed `uv` shim follows the same rule
for supported `uv run ... <payload>` forms. Unsupported `conda` or `uv` forms
fall through to the real executable unless validation identifies them as
bypassing a classified managed entrypoint.

The first version does not guarantee transparent interception for arbitrary
shell wrappers, absolute interpreter paths such as `/usr/bin/python`, or custom
launcher binaries. Validation should catch these unsupported launch paths when
they appear in workflow commands, backlog plans, or newly created shell scripts
under managed roots. A shell wrapper that launches heavy training should either
call `run_managed_job` explicitly or be listed as an intentional unmanaged/local
exception with a reason.

PtychoPINN agents commonly run:

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
python ...
```

`conda activate` can prepend the environment's `bin` directory ahead of the shim
directory and bypass `workflows/managed_jobs/bin/python`. After
`source ~/miniconda3/etc/profile.d/conda.sh`, `conda` is commonly a shell
function, not the executable found through `PATH`, so a PATH-level `conda` shim
is not sufficient.

The first version should support `conda run ... python ...` through the managed
`conda` shim by parsing the inner payload before delegation. It should not claim
transparent support for arbitrary checked-in `source conda.sh && conda activate
... && python ...` command strings, because `BASH_ENV` is loaded before the
`bash -lc` command body and cannot reliably wrap a `conda` function that is
defined later by `source conda.sh`.

If provider guard wants to support activation-style shells, it must use a tested
shell launcher that controls ordering explicitly:

```bash
BASH_ENV=${state_root}/managed_job_policy/shell_hook.sh
MANAGED_JOB_SHIM_DIR=/repo/workflows/managed_jobs/bin
managed_job_restore_path() {
  case ":$PATH:" in
    *":$MANAGED_JOB_SHIM_DIR:"*) ;;
    *) export PATH="$MANAGED_JOB_SHIM_DIR:$PATH" ;;
  esac
}
if declare -F conda >/dev/null 2>&1 && ! declare -F __managed_job_orig_conda >/dev/null 2>&1; then
  eval "$(declare -f conda | sed '1s/^conda/__managed_job_orig_conda/')"
fi
conda() {
  if declare -F __managed_job_orig_conda >/dev/null 2>&1; then
    __managed_job_orig_conda "$@"
  else
    command conda "$@"
  fi
  local status=$?
  managed_job_restore_path
  return "$status"
}
managed_job_restore_path
```

The launcher must source `conda.sh`, install or re-install the managed shell
hook after the `conda` function exists, run `conda activate`, and then call
`managed_job_restore_path` before any payload `python` invocation. For shells
that execute `conda` through `PATH`, the managed `conda` shim should also
re-prepend the shim directory after successful `conda run` delegation.
Validation must still flag checked-in commands or scripts that use activation
patterns and then an absolute interpreter path. Plain `conda activate ... &&
python ...` is supported only when it is launched through this managed shell
launcher, or when the command explicitly restores `MANAGED_JOB_SHIM_DIR` after
activation and before `python`.

Required smoke coverage includes:

```bash
conda run -n ptycho311 python scripts/studies/example_train.py --output-root tmp/out
```

and, only if activation-style support is implemented:

```bash
managed-job-bash -lc 'source ~/miniconda3/etc/profile.d/conda.sh && conda activate ptycho311 && python scripts/studies/example_train.py --output-root tmp/out'
```

under provider guard, proving the invoked `python` is still the managed shim.

## Managed-Job Runner

`run_managed_job` is the execution boundary for classified commands:

```bash
python -m orchestrator.managed_jobs.run_managed_job \
  --backend auto \
  --job-name cns-h5-gap-fill \
  --state-root state/jobs/cns-h5-gap-fill \
  --output-root .artifacts/... \
  --verify-file .artifacts/.../comparison_summary.json \
  -- python scripts/studies/run_pdebench_image128_suite.py ...
```

Everything after `--` is the unchanged payload command.

The runner responsibilities are:

- resolve backend from CLI and environment;
- execute directly for `local` while marking the payload as already managed;
- materialize an immutable execution snapshot for managed Slurm jobs;
- write and submit a Slurm script for `slurm`;
- persist job state before and after submission;
- poll `squeue` while pending/running and `sacct` after terminal Slurm state;
- verify expected output files and their freshness/provenance after Slurm reports
  success;
- resume from existing `job_state.json` without blindly resubmitting;
- return a nonzero exit with log paths and terminal Slurm state on failure.

The runner should block until the managed job is terminal and verified. This
keeps the provider's ordinary command semantics simple: the command returns when
the training/evaluation job is done or has failed.

## Slurm Script Safety

The runner must preserve payload argv boundaries when generating `sbatch`
scripts. It should not join arbitrary command strings by hand.

Rules:

- the shim passes payload commands to `run_managed_job` as argv arrays;
- every managed payload execution path sets `MANAGED_JOB_ACTIVE=1` before
  launching the payload, including local backend execution, existing-allocation
  direct or `srun` execution, and generated Slurm batch scripts;
- before Slurm submission, the runner stages an immutable execution snapshot
  under the job state root, for example `state_root/snapshot/workspace`;
- the snapshot includes the entrypoint source, declared config files, named
  extractor inputs, and any policy-declared local code roots required for imports;
- generated Slurm scripts `cd` into the snapshot workspace and execute the
  snapshot payload paths, not mutable live-workspace script/config paths;
- external data roots may remain as absolute read-only paths, but the job manifest
  records their source, size/mtime manifest or checksum, and access policy;
- if the runner cannot determine a safe snapshot boundary for a classified
  command, it refuses managed submission and asks for a named extractor or an
  explicit snapshot policy entry;
- the Slurm script renderer uses one vetted quoting helper, such as
  `shlex.join(argv)`, for shell script lines;
- generated scripts should set `set -euo pipefail`;
- generated scripts should preserve the runner-set `MANAGED_JOB_ACTIVE=1` before
  running the payload to prevent recursive shim submission;
- repository-relative path arguments are normalized against the workspace and
  must not escape it unless explicitly marked as allowed external paths such as
  data roots;
- `state_root`, generated Slurm script path, stdout path, stderr path, and
  verification sidecars must live under configured workspace-safe roots such as
  `state/managed_jobs/` or `.artifacts/managed_jobs/`;
- `output_root` values may be under approved artifact roots or approved external
  scratch roots, but must be recorded as absolute resolved paths in
  `job_state.json`;
- no secret environment values should be rendered into `job.slurm`; use
  scheduler environment or named env vars instead.

## Backend Selection

Default backend is `auto`.

Precedence:

1. explicit `--backend`;
2. `MANAGED_JOB_BACKEND`;
3. scheduler/environment detection;
4. fallback to `local`.

Suggested policy:

```text
--backend local|slurm|auto  wins first
MANAGED_JOB_BACKEND         wins second
inside existing Slurm job   run local/srun mode, do not nest sbatch by default
NERSC-like environment      slurm
otherwise                   local
```

Important environment variables:

```bash
MANAGED_JOB_BACKEND=auto
MANAGED_JOB_ACCOUNT=<nersc_account>
MANAGED_JOB_PARTITION=gpu
MANAGED_JOB_CONSTRAINT=gpu
MANAGED_JOB_QOS=regular
MANAGED_JOB_TIME=12:00:00
MANAGED_JOB_NODES=1
MANAGED_JOB_GPUS=1
MANAGED_JOB_CPUS_PER_TASK=16
MANAGED_JOB_CONDA_ENV=ptycho311
MANAGED_JOB_MODE=single
```

Resource precedence is deterministic:

1. explicit `run_managed_job` CLI resource flags, when present;
2. per-entry `resources` in `force_managed` or `auto_managed`;
3. environment variables such as `MANAGED_JOB_GPUS` and `MANAGED_JOB_TIME`;
4. policy `backend_defaults`;
5. runner built-in defaults.

Every resolved resource value is written to `job_state.json`. The runner should
also write the source of each resource value, for example
`{"gpus": {"value": 1, "source": "policy.force_managed"}}`, so ambient
environment differences are auditable.

If `SLURM_JOB_ID` is already present, the runner should not submit a nested
`sbatch` job unless explicitly requested. The default should be to run the
payload directly, or use `srun` only when a mode explicitly requires it.

## Slurm Execution Modes

### Single-GPU Single Command

The first version should support this mode.

The runner writes an `sbatch` script that activates the environment, enters the
immutable snapshot workspace, and runs the staged payload command on one GPU. The
workflow sees a single managed job and a single terminal status.

### DDP Multi-GPU Single Command

For one model row that truly needs multiple GPUs, use a Slurm allocation plus
`srun torchrun` inside the batch script:

```bash
srun torchrun --nproc_per_node="${MANAGED_JOB_NPROC_PER_NODE}" \
  scripts/studies/train_large_row.py ...
```

`sbatch` remains the asynchronous scheduler boundary. `srun torchrun` runs
inside the allocation and blocks until the distributed job exits.

Equivalent module form is also valid:

```bash
srun python -m torch.distributed.run \
  --nproc_per_node="${MANAGED_JOB_NPROC_PER_NODE}" \
  studies.foo.train_large_row ...
```

Scientific scripts need DDP awareness only for this mode. Existing scripts that
already support PyTorch distributed execution can use it; independent rows
should not be forced into DDP.

### Packed Independent Rows

For several independent single-GPU rows in one allocation, a later version can
support a command-manifest mode. The batch script starts each payload with
backgrounded `srun --exclusive --gpus-per-task=1 ...`, waits for all child PIDs,
and exits nonzero if any row fails.

This is useful for running FNO and U-Net rows concurrently, but it should not be
the first required mode because it needs multi-command manifests and per-row
verification.

## Job State and Recovery

Every managed job writes `job_state.json` under its state root:

```json
{
  "backend": "slurm",
  "mode": "single",
  "identity": {
    "entry_id": "pdebench_image128_suite",
    "entrypoint": "scripts/studies/run_pdebench_image128_suite.py",
    "job_identity_hash": "a1b2c3d4e5f6",
    "source_hash": "sha256:...",
    "policy_entry_hash": "sha256:...",
    "extractor_hash": "sha256:...",
    "config_hashes": {"configs/foo.yaml": "sha256:..."}
  },
  "snapshot": {
    "workspace": "state/jobs/cns/snapshot/workspace",
    "manifest": "state/jobs/cns/snapshot/manifest.json",
    "payload_command": ["python", "scripts/studies/run_pdebench_image128_suite.py", "..."]
  },
  "job_id": "12345678",
  "submission_nonce": "20260504T000000Z-a1b2c3d4",
  "slurm_job_name": "pdebench-image128-a1b2c3d4",
  "payload_command": ["python", "scripts/studies/run_pdebench_image128_suite.py", "..."],
  "original_live_payload_command": ["python", "scripts/studies/run_pdebench_image128_suite.py", "..."],
  "submit_script": "state/jobs/cns/job.slurm",
  "stdout": "state/jobs/cns/slurm.out",
  "stderr": "state/jobs/cns/slurm.err",
  "output_root": ".artifacts/...",
  "verify_files": [".artifacts/.../comparison_summary.json"],
  "pre_submit_verify_snapshot": {
    ".artifacts/.../comparison_summary.json": {
      "exists": false,
      "size": null,
      "mtime": null,
      "sha256": null
    }
  },
  "managed_run_manifest": ".artifacts/.../managed_run_manifest.json",
  "status": "SUBMITTED",
  "terminal_state": null,
  "submitted_at": "2026-05-04T00:00:00Z"
}
```

Resume behavior:

- before resuming, recompute the command identity and refuse to reuse
  `job_state.json` if source, config, extractor, policy-entry, or normalized-arg
  hashes differ;
- resume existing Slurm jobs from the staged snapshot recorded in
  `job_state.json`; do not rewrite a submitted job to point at the current live
  workspace;
- if `job_id` exists and Slurm says pending/running, continue polling;
- if Slurm says completed, verify output files;
- if Slurm says failed/cancelled/timeout/node-fail, return structured failure;
- if Slurm history aged out but artifacts verify, mark complete;
- if there is no job and artifacts are incomplete, submit a new job only after
  the atomic submission recovery checks below;
- never resubmit just because the workflow or provider process restarted.

## Policy File

Each consuming repo owns a managed-job policy file, for example:

```yaml
roots:
  - scripts/studies
  - scripts/training

backend_defaults:
  backend: auto
  mode: single
  time: "12:00:00"
  nodes: 1
  gpus: 1
  cpus_per_task: 16

managed_conventions:
  scripts:
    - "*/train.py"
    - "*/train_*.py"

force_managed:
  - path: scripts/studies/run_pdebench_image128_suite.py
    id: pdebench_image128_suite
    job:
      name_template: "{script_stem}-{args_hash}"
      state_root_template: "state/managed_jobs/{entry_id}/{job_identity_hash}/{args_hash}"
      output_root_arg: "--output-root"
      verify_files:
        - "{output_root}/comparison_summary.json"
    resources:
      time: "12:00:00"
      gpus: 1
      cpus_per_task: 16

force_local:
  - path: scripts/studies/tiny_smoke.py
    reason: "fast local smoke check"

auto_managed:
  - path: scripts/studies/foo/new_runner.py
    id: foo_new_runner
    reason: "AST detected optimizer/backward/epochs"
    first_detected_at: "2026-05-04T00:00:00Z"
    job:
      name_template: "{script_stem}-{args_hash}"
      state_root_template: "state/managed_jobs/{entry_id}/{job_identity_hash}/{args_hash}"
      output_root_arg: "--output-root"
      verify_files:
        - "{output_root}/metrics.json"
```

`force_managed` and `force_local` are intentional human-authored policy. The
watcher may append to `auto_managed`. It should not remove existing entries or
rewrite unrelated policy.

If an automatically classified script should remain local-only, a later patch
can move it from `auto_managed` to `force_local` with a reason.

## Managed Entry Job Metadata

Transparent routing is allowed only when a managed policy entry supplies enough
metadata to derive deterministic job state and completion checks from the
ordinary command.

Each managed entry must provide either explicit job fields or a named extractor:

```yaml
job:
  name_template: "{script_stem}-{args_hash}"
  state_root_template: "state/managed_jobs/{entry_id}/{job_identity_hash}/{args_hash}"
  output_root_arg: "--output-root"
  verify_files:
    - "{output_root}/comparison_summary.json"
```

or:

```yaml
job:
  extractor: pdebench_image128_suite
```

Required derived values:

- stable `job_name`;
- stable `state_root`;
- zero or more `output_root` values, when the command has output-root semantics;
- one or more deterministic completion checks.

For managed training or evaluation entries, completion checks must include at
least one artifact check, completion-marker check, or structured-log check. A
successful scheduler exit alone is not enough. `verification: none` is allowed
only for explicitly local or unmanaged non-artifact commands; it is not valid for
a classified managed training/evaluation entrypoint.

Completion checks must prove the observed artifacts belong to this managed job,
not merely that a file exists at the output path or changed after submission.
Before submission, the runner records existence, size, mtime, and optionally
content hash for every verify target. After scheduler success, verification
requires one of these producer-identity contracts:

- a managed-run manifest or completion marker containing this
  `job_identity_hash`, `submission_nonce`, and `slurm_job_id`; or
- an output root derived exclusively from this `job_identity_hash` and
  `submission_nonce`, plus freshness checks proving the verify targets were
  produced after the Slurm job start time.

Freshness by itself is not enough, because another process can write the same
file path. If a reused output root contains an unchanged stale artifact, or if a
shared output root lacks a managed-run manifest/completion marker for the current
job, verification must fail even when the scheduler state is `COMPLETED`.

Generic `output_root_arg` supports only simple split and equals forms:

```text
--output-root VALUE
--output-root=VALUE
```

Short flags, config-file-derived output roots, multiple output roots, or
internally derived artifact roots require a named extractor. Extractors are
entrypoint-specific deterministic functions that parse argv and, when needed,
read declared config files using structured parsers. They must not execute the
training script.

The stable argument hash should be computed from the payload command after
normalizing repository-relative paths and excluding volatile wrapper fields. The
same ordinary command should map to the same `state_root` across provider
restarts when the executable source/config contract has not changed, so resume
can find `job_state.json`.

The default state-root template includes both `entry_id` and
`job_identity_hash`. `job_identity_hash` is a short hash of:

- normalized script path or module name;
- source content hash for the entrypoint;
- declared config-file hashes parsed by the extractor;
- named extractor id/version or extractor implementation hash;
- policy-entry job metadata that affects state, verification, or resources.

This avoids collisions between different scripts that share the same basename
and argument list, and it prevents a modified script or config from verifying
stale artifacts produced by an older command contract. `job_state.json` must
store the full identity fields and resume must refuse reuse when they differ
from the current command.

If a command is classified as managed but no job metadata or extractor can
derive completion checks, the shim must not silently run it locally. It should
fail with a clear policy error asking for verification metadata or an explicit
`force_local` entry. This keeps transparent routing recoverable instead of
best-effort.

## Policy Update Protocol

The watcher may run while the provider is editing files, including the policy
file. Policy updates therefore need an explicit merge protocol.

When adding an `auto_managed` entry, the watcher:

1. takes an exclusive lock on `workflows/managed_jobs/policy.yaml.lock`;
2. reloads the current policy from disk;
3. checks whether the path is already classified by convention, `force_managed`,
   `force_local`, or `auto_managed`;
4. if the path is newly classified by the reloaded policy, writes only an audit
   event and does not edit the policy;
5. if the path is explicitly `force_local`, writes a conflict audit event and
   does not override it;
6. otherwise appends one `auto_managed` entry in memory;
7. writes the updated YAML to a temporary file in the same directory;
8. atomically replaces the policy file with the temporary file;
9. releases the lock.

If the already-loaded base policy is valid but a later reload is temporarily
unparsable because the provider is editing it, or if the lock cannot be obtained
quickly, the watcher writes the detection to a run-scoped sidecar:

```text
${state_root}/managed_job_policy/pending.jsonl
```

The provider guard passes the sidecar path to the shims with
`MANAGED_JOB_PENDING_POLICY`. The runtime shim reads the merged view of
`policy.yaml` plus that run-scoped pending sidecar. Pending entries must not be
stored in a repo-global path, because stale pending detections from one run
must not affect unrelated future provider sessions.

A deterministic post-provider reconciliation step later merges pending entries
into `policy.yaml` using the same lock/reload/atomic-replace protocol. If
same-session routing from pending entries is disabled by policy, the shim should
ignore `MANAGED_JOB_PENDING_POLICY` and only route from durable policy. The
first version should allow same-session routing from the run-scoped sidecar
because it lets a provider create and run a new training entrypoint in one
session without waiting for a separate durable-policy merge.

If same-session pending entries affect routing, they must be reconciled before
the managed provider step is considered successful. Provider guard should run
the deterministic reconciliation at normal provider exit. If reconciliation
fails, the provider step fails with a policy error even if the provider command
itself exited successfully. Backlog completion must not depend on a managed job
that only exists in unreconciled run-scoped pending policy.

Startup is stricter: if the initial base policy cannot be parsed before the
provider starts, `provider_guard` fails fast. Pending-sidecar fallback is only
for transient reload failures after a valid base policy has already been loaded.

## Auto-Classification Watcher

The watcher monitors configured roots for Python file create and modify events.
On each changed `.py` file:

1. ignore paths outside configured roots;
2. ignore excluded paths such as tests or explicitly local smoke scripts;
3. debounce briefly so partial writes are not scanned;
4. parse the file with `ast`;
5. require entrypoint evidence;
6. detect training-like code using conservative signals;
7. if the file is not training-like, do nothing;
8. if the file is already classified, do nothing;
9. if the file is training-like and unclassified, append it to `auto_managed` or
   to the pending sidecar using the policy update protocol;
10. write an audit event under the provider state root.

Entrypoint evidence is required before auto-classification. A helper module that
contains `torch.optim` or `.backward()` is not enough. The scanner should require
at least one of:

- `if __name__ == "__main__"` block;
- a `main()` function invoked from a module entrypoint;
- direct `argparse`, `click`, or `typer` command-line invocation;
- a known project runner registration;
- a script path or module name matching the managed training convention.

Initial training signals:

- imports or references to `torch.optim`;
- calls to `.backward()`;
- calls to optimizer-like `.step()`;
- calls to `Trainer.fit(...)`;
- argparse flags such as `--epochs`, `--batch-size`, `--device`, or
  `--output-root`;
- project-local study runner APIs known to train or evaluate models.

The detector should be conservative. False positives are acceptable if they are
easy to move to `force_local`; false negatives are handled by later validation
and by explicit `force_managed` entries.

Auto-classified entries need job metadata. The watcher should attach default job
metadata only when it can identify a deterministic output-root argument and
verification pattern from known extractor rules. If it cannot, it should write a
pending entry with `requires_job_metadata: true`. Such an entry is visible to
review/reconciliation, but the shim should fail rather than route it until job
metadata is added.

## Runtime Command Routing

The provider guard configures the provider process environment:

```bash
PATH=/abs/workspace/workflows/managed_jobs/bin:$PATH
MANAGED_JOB_SHIM_DIR=/abs/workspace/workflows/managed_jobs/bin
MANAGED_JOB_POLICY=/abs/workspace/workflows/managed_jobs/policy.yaml
MANAGED_JOB_PENDING_POLICY=/abs/workspace/state/<run>/managed_job_policy/pending.jsonl
MANAGED_JOB_STATE_ROOT=/abs/workspace/state/<run>/managed_job_policy
MANAGED_JOB_AUDIT_PATH=/abs/workspace/state/<run>/managed_job_policy/<step>/managed_job_events.jsonl
MANAGED_JOB_BACKEND=auto
MANAGED_JOB_REAL_PYTHON=/resolved/path/to/python
MANAGED_JOB_REAL_PYTHON3=/resolved/path/to/python3
MANAGED_JOB_REAL_TORCHRUN=/resolved/path/to/torchrun
MANAGED_JOB_REAL_CONDA=/resolved/path/to/conda
MANAGED_JOB_REAL_UV=/resolved/path/to/uv
```

All managed-job environment paths exported by `provider_guard` must be absolute,
resolved paths. Shims must not interpret `workflows/managed_jobs/bin`,
`workflows/managed_jobs/policy.yaml`, pending-policy paths, audit paths, or state
roots relative to the provider's current working directory, because providers may
`cd` before launching Python.

The managed `python` shim inspects the invoked Python command. If the command is
classified by convention, `force_managed`, or `auto_managed`, it routes through
the managed-job runner. Otherwise it immediately execs the real Python.

Runtime routing should be deterministic and fast. It should not run AST analysis
on every Python invocation that is already classified.

Command classification should use the invoked entrypoint and committed policy,
not live source inspection. For example:

- `python scripts/studies/run_pdebench_image128_suite.py ...` is routed if the
  script is in `force_managed` or `auto_managed`;
- `python -m studies.foo.train ...` is routed if the module matches the managed
  convention;
- `python - <<'PY' ... PY`, `python -m compileall ...`, and tests fall through.

The shim should also read pending sidecar entries produced by the watcher. This
lets a provider create a new training entrypoint and run it in the same provider
session even if the durable policy merge is deferred because the policy file was
being edited.

To avoid the race where a provider writes a script and immediately runs it
before the watcher classifies it, the shim has one synchronous fallback:

- if the invoked script/module is under a managed root;
- and it is not classified by durable policy or run-scoped pending policy;
- and it is a safely resolved file-backed Python entrypoint;
- then the shim may synchronously run the same AST entrypoint classifier on that
  file before deciding.

If synchronous classification finds a training-like entrypoint, the shim records
the detection through the same run-scoped pending sidecar path and then applies
the job-metadata rule. If metadata is available from an extractor, it routes
through `run_managed_job`; if metadata is missing, it fails with a policy error.
If the file is not training-like, it falls through to the real Python.

For `python -m package.train`, synchronous classification should not import or
execute package code. It may classify the module synchronously only when it can
map the module name to a file by safe path rules:

- convert the module name to a relative path under configured managed roots;
- accept `package/train.py` or `package/train/__main__.py`;
- require the resolved file to stay inside the workspace and a managed root;
- do not use `importlib.import_module` or execute package `__init__.py`.

If safe path mapping fails, module-form routing is limited to durable policy or
convention matches. The shim should then fall through or fail according to the
existing policy classification result; it should not execute imports to inspect
the module.

Before prepending the shim directory to `PATH`, `provider_guard` resolves the
real executables and exports them through the `MANAGED_JOB_REAL_*` variables.
Each shim must exec only its corresponding real executable from those variables,
never resolve by searching the shim-prepended `PATH`. This prevents recursive
shim invocation, including nested forms such as `uv run python ...` and
`conda run ... python ...`.

The `conda` and `uv` shims are not simple pass-through wrappers for supported
forms. They must parse launcher options until the payload boundary, identify
whether the payload is one of the supported Python or Torch launch forms, and run
the same classification and job-metadata derivation used by the Python shim. If
the payload is managed, they invoke `run_managed_job` with the original outer
argv as the payload command. If it is unmanaged, they exec the real `conda` or
`uv`. Inside the managed job, `MANAGED_JOB_ACTIVE=1` makes the outer shim
delegate to the real launcher, so the environment-local Python may run normally
without causing another submission.

## Unsupported Launch Validation

Because the v1 interception boundary is `PATH` shims, unsupported launch forms
need deterministic validation rather than an implied transparency guarantee.

The validator should scan:

- workflow YAML files being launched or edited in the current patch;
- the active selected backlog item and its checked commands;
- current-run plan and prompt artifacts used by the selected item;
- changed shell scripts under managed roots.

It should not scan every historical plan under `docs/plans/` by default. Broad
repo scans are allowed as an explicit audit mode, but normal workflow validation
should stay scoped to current-run or changed files to avoid stale historical
noise.

It should flag likely heavy training launches that bypass the shim, including:

- absolute interpreters such as `/usr/bin/python`, `/opt/conda/bin/python`, or
  `/global/.../python`;
- shell scripts that invoke a managed training entrypoint through an absolute
  interpreter;
- direct `sbatch` or `srun` wrappers for classified managed entries unless they
  explicitly call `run_managed_job`;
- custom launch binaries that call classified managed entries without going
  through a supported shim.

Validation should not reject all shell scripts. It should reject only shell or
YAML/planning surfaces that appear to launch a managed training entrypoint while
bypassing the managed-job boundary. Accepted alternatives are: use a supported
shimmed form, call `run_managed_job` explicitly, or add an intentional
`force_local`/unmanaged exception with a reason.

Validation should also detect `conda activate ... && python ...` patterns in
checked-in shell/planning surfaces. Provider guard alone is not enough, because
activation can reorder `PATH` after the guard installs shims. These patterns are
acceptable only when launched through the tested managed shell launcher, such as
`managed-job-bash`, or when they explicitly restore `MANAGED_JOB_SHIM_DIR` after
activation and before the Python invocation.

## Managed Provider DSL Integration

Managed-job interception and recovery should be declared on provider steps, not
hand-wired through provider command templates and companion YAML gates. A
provider role label such as review, implementation, or fix is not sufficient to
decide whether management is needed because the runtime generally permits
provider file operations. A step opts in when its provider is write-capable and
the workflow wants transparent classification/recovery for commands the provider
launches.

Conceptual shape:

```yaml
steps:
  - name: ExecuteImplementation
    provider: implementation_provider
    timeout_sec: 86400
    managed_jobs:
      policy: workflows/managed_jobs/policy.yaml
      watch_roots:
        - scripts/studies
        - scripts/training
      backend: auto
      poll_budget_sec: 82800
      on:
        complete: ReviewImplementation
        failed: FixImplementation
        invalid: FixImplementation
        outstanding: fail_resumable
```

The step's provider template remains the ordinary provider command. The runtime
selects the normal provider command, `session_support.fresh_command`, or
`session_support.resume_command` according to existing provider semantics, then
wraps that selected command with `provider_guard` internally. The
`${SESSION_ID}` placeholder stays in the inner provider command and is resolved
by the existing provider-session machinery before the managed-job wrapper runs.

`managed_jobs` is a step modifier, not a new provider type. It does not change
prompt composition, `consumes`, `publishes`, `output_bundle`, or provider
parameter substitution. It adds a deterministic execution envelope around the
provider child process and a deterministic post-provider recovery phase.

The field should be version-gated at the next DSL version after the currently
implemented surface. It is valid only on provider steps. It is invalid on command
steps, adjudicated provider steps in the first version, or steps with provider
`retries`, because retrying the provider child process is not the recovery model
for outstanding managed jobs. Route targets under `managed_jobs.on` are validated
like ordinary `goto` targets; `outstanding` supports only `fail_resumable` in the
first version.

Runtime responsibilities for a managed provider step:

- resolve and validate the policy path, watch roots, backend, and poll budget;
- prepare a run-owned audit directory and canonical
  `managed_job_events.jsonl` before launching the provider;
- launch the selected provider command through `provider_guard` with the audit
  path, policy path, watch roots, backend, real executable paths, shim directory,
  pending-policy sidecar, and state root supplied by the runtime;
- wrap both fresh and resume provider-session commands when the provider step
  uses `provider_session`;
- after provider success, failure, timeout, or interruption, run managed-job
  recovery before normal workflow routing;
- poll and verify audited jobs without resubmitting;
- record a structured recovery summary in the step result and a run-root sidecar;
- route `complete`, `failed`, and `invalid` outcomes according to
  `managed_jobs.on`;
- leave the managed provider step failed with a resumable recovery state when
  `outstanding: fail_resumable` and audited jobs are still validly
  pending/running after the poll budget;
- on `orchestrator resume <run_id>`, re-enter the recovery phase for the same
  managed provider visit instead of relaunching the provider command.

The runtime-owned recovery summary should expose at least:

```json
{
  "managed_job_outcome": "COMPLETE",
  "recovery_status": "COMPLETE",
  "audit_path": ".orchestrate/runs/.../managed_jobs/ExecuteImplementation/managed_job_events.jsonl",
  "jobs": [
    {
      "job_state_path": "state/managed_jobs/.../job_state.json",
      "status": "VERIFIED",
      "terminal_state": "COMPLETED"
    }
  ]
}
```

`managed_job_outcome` values are `COMPLETE`, `FAILED`, and `INVALID`.
`OUTSTANDING` is not a successful routeable outcome in the first version; it is
a resumable failed-state diagnostic so a later resume continues the same
deterministic wait.

The managed provider state is runtime-owned. Workflow authors should not need to
publish audit pointer artifacts, pass `audit_path` through `provider_params`, add
manual `RecoverManagedJobs` command steps, or route timeout failures into a
separate recovery gate. Those are runtime semantics of `managed_jobs`.

Provider templates still need an importable guard implementation. The first
implementation should choose one explicit distribution mode:

- installed orchestration package available in the target environment;
- copied repo-local `workflows/managed_jobs/` helper package; or
- provider template/runtime environment sets `PYTHONPATH` to include the
  orchestration checkout.

For PtychoPINN, the least surprising initial distribution mode is to copy the
small `workflows/managed_jobs/` helper surface into the repo and invoke that
repo-local entrypoint from the runtime wrapper. Provider templates should not
assume `python -m orchestrator.managed_jobs.provider_guard` works unless the
package is installed or `PYTHONPATH` is explicitly configured.

Manual wrapping remains a migration fallback for older runtimes that do not
support `managed_jobs`. It must not be the preferred design because it requires
every workflow author to reproduce audit preparation, provider-command binding,
failure routing, recovery, and resume semantics correctly. A fallback Codex
provider wrapper would look like:

```yaml
providers:
  codex:
    defaults:
      audit_path: ""
    command:
      - python
      - workflows/managed_jobs/provider_guard.py
      - --policy
      - workflows/managed_jobs/policy.yaml
      - --state-root
      - ${inputs.state_root}/managed_job_policy
      - --audit-path
      - ${audit_path}
      - --watch-root
      - scripts/studies
      - --watch-root
      - scripts/training
      - --
      - codex
      - exec
      - --dangerously-bypass-approvals-and-sandbox
      - --skip-git-repo-check
      - --model
      - ${model}
      - --config
      - reasoning_effort=${effort}
    input_mode: stdin
```

Prompts should not need Slurm details. Scientific scripts should not need Slurm
changes unless they opt into true DDP.

## Failure Policy

The provider should keep working when classification succeeds.

The managed provider wrapper should fail fast only for infrastructure failures:

- base policy YAML is missing or unparsable at startup;
- policy file cannot be written;
- watcher cannot start;
- a changed file path escapes configured roots;
- an entry conflicts with `force_local` or another explicit policy;
- managed-job shim cannot find the real Python executable.

Managed-job runtime failures are separate from provider-guard failures. If the
provider runs a classified command and the Slurm job fails, `run_managed_job`
returns nonzero with a structured error and log paths. The provider can inspect
and fix it like any other failed shell command.

Transient policy reload failures after startup are not fail-fast by themselves;
they use the run-scoped pending sidecar path described in the policy update
protocol.

## Deterministic Managed-Job Recovery Semantics

Provider timeout or interruption must not rely on a future provider remembering
to inspect managed-job state. Recovery is therefore a runtime phase of a
`managed_jobs` provider step, not a workflow-authored command step.

The provider guard audit records every managed job state path touched during the
provider session. After the provider child process exits, times out, or is
interrupted, the runtime recovery phase:

1. reads the runtime-prepared canonical `managed_job_events.jsonl`;
2. loads each touched `job_state.json`;
3. polls outstanding Slurm jobs within `managed_jobs.poll_budget_sec`;
4. verifies completed jobs;
5. writes a recovery summary sidecar;
6. updates the managed provider step result with `managed_job_outcome`;
7. routes only real job failures, missing verification artifacts, or invalid job
   states to the configured fix branch.

The audit path must be prepared before the managed provider runs. It cannot
depend on the provider step successfully extracting an `output_bundle`, provider
stdout, prompt-injected `consumes`, or a post-provider artifact, because those
surfaces may be absent after timeout. The runtime owns this path and passes it to
`provider_guard`; workflow authors do not bind it through `provider_params`.

Append protocol:

- provider guard, shims, and `run_managed_job` append JSONL records to the
  runtime-prepared canonical `managed_job_events.jsonl` using a file lock and
  atomic append;
- each managed-job event records `run_id`, provider step identity, visit count,
  pid, timestamp, `job_state_path`, `submission_nonce`, and event type;
- after appending a `submitted`, `adopted`, `verified`, or `failed` event, the
  writer fsyncs the audit file or containing directory according to platform
  support;
- the recovery phase treats a missing audit file as an infrastructure failure,
  but treats an existing empty audit file as "no managed jobs were launched."

Do not use provider retries to recover outstanding managed jobs. Retry transient
scheduler-query errors inside the runtime recovery phase. A valid still-running
job should either be polled to terminal state within the poll budget or leave the
managed provider step failed with a resumable `recovery_status=OUTSTANDING`
diagnostic. `OUTSTANDING` is intentionally diagnostic-only in the first version:
the workflow must not branch on it as a normal success artifact.

The recovery phase must not resubmit jobs. The workflow should not enter the
implementation fix loop until recovery has distinguished valid outstanding Slurm
work from actual job failure.

## Provider Timeout Semantics

Managed provider steps still run under orchestrator `timeout_sec`. The provider
child process may be killed while `run_managed_job` is polling a valid Slurm job.
This must be safe and must not cause duplicate submissions.

Rules:

- before invoking `sbatch`, `run_managed_job` writes and fsyncs a durable
  `PRE_SUBMIT` state containing the command identity, submission nonce, Slurm
  job name/comment, submit script path, and payload command;
- `sbatch` must use `--parsable` and include the unique job name/comment derived
  from that nonce when the scheduler supports it;
- after `sbatch --parsable` returns a job id, `run_managed_job` atomically
  writes and fsyncs `job_state.json` with `job_id` before entering polling;
- if interrupted after `PRE_SUBMIT` but before `job_id` persistence, a later
  invocation must query scheduler state by the recorded nonce/job name/comment
  before any new submission;
- if exactly one matching scheduler job is found, adopt its job id and continue
  polling;
- if the scheduler query is ambiguous or unavailable and artifacts do not verify,
  return a structured `AMBIGUOUS_SUBMISSION` failure with recovery instructions
  instead of submitting again;
- provider timeouts should be configured to exceed expected queue plus run time
  for normal operation, but correctness must not rely on that;
- timeout recovery is owned by persisted managed-job state, not by provider
  memory or prompt instructions.

This means a provider timeout may fail the provider step, but it should not
invalidate the Slurm job. Resume or fix-loop execution should recover by
inspecting the existing managed-job state first.

## Audit Outputs

Each managed provider step writes a compact runtime-owned audit bundle under its
run root:

- `managed_job_events.jsonl`: canonical recovery audit read by
  managed-provider recovery; contains one JSONL record per managed-job lifecycle
  event with `job_state_path`, `submission_nonce`, scheduler identifiers, and
  event type;
- `file_events.jsonl`: file watcher events and classification decisions;
- `auto_managed_updates.json`: entries appended during the provider run;
- `summary.json`: counts, policy path, watch roots, and any fatal errors.

Each managed job writes a compact execution bundle:

- `job_state.json`: backend, resources, command, job id, terminal state;
- `snapshot/manifest.json`: immutable execution snapshot manifest with staged
  source/config/extractor files and external data-root provenance;
- `job.slurm`: generated Slurm script when backend is `slurm`;
- `stdout` and `stderr` paths;
- `poll_events.jsonl`: scheduler status transitions;
- `verification.json`: output-file freshness and provenance verification result;
- managed-run manifest or completion marker under the output root when required
  by the policy entry.

The policy file remains the durable runtime authority.

## Scope

In scope:

- `run_managed_job` with local and single-GPU Slurm backends;
- backend selection from CLI and environment;
- Slurm script generation, submission, polling, resume, and verification;
- provider guard;
- `managed_jobs` provider-step DSL validation and runtime execution envelope;
- managed provider resume semantics that re-enter recovery without relaunching
  the provider command;
- file watcher;
- AST classifier;
- append-only policy update logic;
- managed Python shim integration;
- validation for workflow YAML, plans, and shell scripts that use unsupported
  launch forms for managed training commands;
- tests and docs for the policy lifecycle.

Out of scope for the first version:

- packed multi-command Slurm jobs;
- new DDP support inside scientific scripts that do not already support it;
- editor plugins or filesystem-level write prevention;
- a general-purpose scheduler DSL for arbitrary non-provider command steps;
- rewriting scientific scripts to be Slurm-aware.

## Verification

Required checks:

- backend selection honors CLI/env/default precedence;
- local backend executes payload directly and preserves exit status;
- Slurm backend writes a valid script with expected resources;
- Slurm script generation preserves argv boundaries with the vetted quoting
  helper and rejects unsafe state/log/script paths;
- Slurm jobs execute the staged snapshot payload, not the mutable live workspace
  script/config paths;
- snapshot manifests include source/config/extractor hashes and declared external
  data-root provenance;
- resource precedence is tested across CLI, per-entry policy, environment,
  backend defaults, and built-in defaults;
- Slurm submit/poll code maps pending/running/completed/failed states correctly
  using mocked `sbatch`, `squeue`, and `sacct`;
- `conda run` and `uv run` shims parse supported inner payloads and route the
  original outer argv through `run_managed_job` for classified managed
  entrypoints instead of relying on inner Python PATH resolution;
- managed job identity includes source, config, extractor, policy-entry, and
  normalized-argument hashes, and resume refuses stale state when any identity
  component changes;
- Slurm submission writes and fsyncs `PRE_SUBMIT` before `sbatch`, persists job id
  atomically after `sbatch --parsable`, adopts exactly one matching scheduler job
  after an interrupted submit, and refuses ambiguous resubmission;
- `managed_jobs` loader validation accepts managed provider steps and rejects
  invalid policy paths, unsafe watch roots, missing route targets, and unsupported
  `on` outcomes;
- managed provider runtime prepares a canonical audit path before launching the
  provider and passes it to `provider_guard` without workflow-authored
  `provider_params` or pointer artifacts;
- managed provider runtime wraps normal provider commands and v2.10
  `session_support.fresh_command` / `resume_command` selections;
- managed provider recovery scans provider-audited job states after success,
  failure, or timeout, polls/verifies existing jobs, and does not resubmit;
- provider guard, shims, and managed-job runner append audit events with locking
  and fsync semantics;
- managed provider timeout/failure enters the runtime recovery phase before the
  normal implementation review/fix route;
- resume from an interrupted or outstanding managed provider visit re-enters
  recovery without relaunching the provider command;
- resume does not resubmit when an existing job is pending/running;
- completed Slurm jobs require artifact verification before success;
- artifact verification rejects stale files from a reused output root unless a
  managed-run manifest, completion marker, or exclusive job-derived output root
  ties them to the current `job_identity_hash` and `submission_nonce`;
- managed training/evaluation policy entries require deterministic completion
  checks before transparent routing;
- the shim derives stable job name, state root, and completion checks from policy;
- unclassified scripts under managed roots are synchronously classified by the
  shim before fallback;
- AST classifier identifies representative training scripts;
- AST classifier ignores non-training scripts and tests;
- watcher appends a new training-like file to `auto_managed`;
- existing `force_local` entries are respected;
- existing `force_managed` entries are respected;
- policy updates are append-only and preserve existing entries;
- Python shim falls through for ordinary commands;
- Python shim routes classified training entrypoints;
- managed provider runtime starts the guard/watcher, runs the selected child
  provider command, records audit files, and preserves provider exit semantics
  when there are no infrastructure or managed-job recovery failures;
- shim coverage includes `python`, `python3`, `torchrun`, `conda run`, and
  `uv run` supported forms;
- unsupported absolute interpreter or shell-wrapper launch paths are flagged by
  validation when they appear in workflows, plans, or changed shell scripts;
- startup base-policy parse failure is fail-fast, while transient reload failure
  uses the run-scoped pending sidecar;
- policy auto-updates use lock/reload/atomic replace;
- pending sidecar entries are read by the shim and later reconciled into policy;
- managed provider runtime fails the step if same-session pending entries
  affected routing but reconciliation failed;
- helper modules with training internals but no entrypoint evidence are not
  auto-classified;
- module-form synchronous classification uses safe path mapping and never imports
  package code;
- conda activation cannot permanently move the shim directory behind the active
  environment's `bin` path when launched through supported `conda run` or
  managed-shell activation forms;
- unsupported raw `source conda.sh && conda activate ... && python ...` checked-in
  commands are flagged unless they restore the shim path before `python`;
- `managed-job-bash -lc 'source .../conda.sh && conda activate ptycho311 &&
  python ...'` remains intercepted under provider guard if activation-style
  support is implemented.

Workflow smoke:

- a `managed_jobs` dummy provider creates a toy training-like file under a
  watched root;
- the watcher appends it to `auto_managed`;
- the runtime records managed-provider audit and recovery sidecars;
- the provider step routes through the configured managed-job outcome;
- a later invocation of that script is routed by the shim.

Slurm smoke, when a Slurm environment is available:

- run a tiny classified Python payload through `MANAGED_JOB_BACKEND=slurm`;
- confirm a job id is persisted;
- confirm scheduler terminal state is recorded;
- confirm expected output verification controls success.

## Migration Plan

1. Add managed-job policy and guard infrastructure to the orchestration repo.
2. Add `run_managed_job` with local and single-GPU Slurm modes.
3. Add managed Python shim and policy-driven routing.
4. Add `managed_jobs` provider-step DSL validation, runtime wrapping, recovery,
   and resume semantics.
5. Copy the policy scaffold and shim directory into PtychoPINN.
6. Seed `force_managed` with known heavy legacy study entrypoints.
7. Add `managed_jobs` declarations to write-capable NeurIPS provider steps that
   should transparently manage heavy study commands. If a review provider is
   intentionally left unmanaged, first make that step actually read-only or
   record why it cannot modify the workspace.
8. Run a smoke workflow that creates a synthetic training-like script and proves
   auto-classification without provider interruption.
9. Run local managed-job smoke tests.
10. Run Slurm smoke tests on NERSC before using the system for production rows.
11. Keep prompts mostly unchanged; document only the high-level behavior in
   AGENTS.md and workflow runbooks.

## Documentation Impact

AGENTS.md should get a short policy note:

- long-running study commands may be transparently managed by the environment;
- agents should continue using normal study commands;
- do not hand-write ad hoc `sbatch` wrappers unless a task explicitly calls for
  infrastructure work.

Workflow docs should explain:

- how to declare `managed_jobs` on provider steps;
- backend environment variables;
- where job state and Slurm logs are written;
- how resume behaves;
- how to add intentional `force_managed` or `force_local` entries;
- how to debug a managed-job failure.
