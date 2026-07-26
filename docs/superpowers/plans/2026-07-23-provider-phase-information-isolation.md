# Provider-Phase Information Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task by task.
> Use a fresh implementation agent for each task, then an independent
> specification review and an independent code-quality review before advancing.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable, opt-in, fail-closed provider launch profile that lets
a provider edit one candidate product and return one active typed result while
preventing access to external control assets, controller state, peer/evaluator
roots, the parent checkout, and prior raw phase bundles.

**Architecture:** Parse and digest an external
`provider_phase_isolation.v1` policy, compile each provider attempt into an
immutable launch plan, and execute that plan through a Linux Bubblewrap backend.
The backend mounts the candidate at its existing absolute path read/write,
masks candidate `.orchestrate`, supplies a sealed provider rootfs and
isolated home/temp roots, and brokers the active result through
invocation-private scratch. Public run/resume state binds the policy,
environment, backend, and per-attempt attestation. No required isolated launch
may fall back to the ordinary subprocess path.

**Tech Stack:** Python 3, `pytest`, Bubblewrap, Linux namespaces, subprocess
process groups, JSON/JSON Schema, SHA-256 canonical identities, Workflow Lisp
2.15, the public orchestrator CLI, and tmux for long-running checks.

---

## Durable Governing Design And Execution Rules

The durable governing design reference is
[Provider-Phase Information Isolation Design](../specs/2026-07-23-provider-phase-information-isolation-design.md).
The 2026-07-23 base is accepted for implementation following independent
specification and quality re-reviews; the 2026-07-25 rootless-launch amendment
received fresh independent specification and quality approval and is also
accepted for implementation. Those approvals do not promote implementation
evidence. Read the design before implementation. If this plan and that design
disagree, correct the plan before continuing.
After substantive specification and quality approvals for this design/plan
round, the controller—not an implementation task—performs the metadata-only
transition from proposed/pending to accepted/completed and confirms the exact
post-transition checksums. No substantive contract edit may be folded into that
administrative transition.

The triggering evidence is
[Experiment Control-Plane Feasibility Report](../../reports/2026-07-23-experiment-control-plane-feasibility.md).
The `.orc` versus one-shot experiment remains stopped at `G0_BLOCKED` until
this plan is implemented, independently reviewed, and its original gate passes
through the public CLI.

The approach accepts these costs:

- Linux is the only supported backend in the first release.
- Provider executables and their runtime dependencies must come from a
  digest-verified environment instead of ambient host roots.
- Evidence-grade invocations are fresh-only; shared provider sessions remain
  unsupported.
- A phase-private result broker adds one bounded copy at provider completion.

These choices make ad hoc host tool access and multi-platform rollout harder.
Do not weaken them with a permissive fallback.

Execution rules:

- Do not create worktrees.
- Preserve unrelated changes in the shared checkout. Stage and commit only the
  files named by the active task.
- Follow strict TDD for every runtime change: write the focused test, run it and
  observe the expected failure, add only the minimum implementation, then run
  the focused and affected aggregate selectors.
- If a test module is added or renamed, run `pytest --collect-only` on it.
- Run long integration checks, live-provider checks, and
  `pytest -q -n 16 --dist=worksteal` in tmux.
- Never assert literal prompt phrasing. Assert path authority, typed dataflow,
  process behavior, state identity, artifacts, and stable diagnostic classes.
- Do not treat a copied workspace, prompt omission, reviewer-package filter, or
  test wrapper as the security boundary.
- Treat the writable candidate as an intentional shared/declassification
  channel. The v1 gate proves absence of controller-owned/raw-runtime authority
  at launch, not resistance to phases that deliberately relay data in product
  files.
- Treat provider-caused CPU, memory, process, candidate-space, synthetic-home,
  `/tmp`, and scratch exhaustion as an explicit v1 availability non-goal.
  Result-size bounds and timeout/namespace teardown protect ingestion and
  eventual quiescence; deployments needing availability isolation must add
  separately reviewed cgroup/storage quotas. The lifecycle-only
  crash-durable containment slot below may use cgroup-v2 membership/kill/empty
  proof, but configures no resource quota and does not expand this claim.
- Do not mount `/`, the host home, the parent checkout, or the control root into
  an isolated provider namespace for convenience.
- Launch `bubblewrap.v1` directly as the controller user. Per-run `sudo`,
  `pkexec`, a privileged `setpriv`, set-id group-clearing helper,
  capability-bearing broker, or an empty-group precondition is forbidden.
  Retained supplementary groups are safe only when joint host/inner namespace
  observations and the complete closed mount/descriptor projection pass.
- `mode: required` must fail before provider launch when enforcement is
  unavailable. There is no warning-only path.
- Keep history-retrieval classification separate from the core local
  filesystem gate. Shared network access means `OBSERVATIONAL_ONLY`, not an
  inferred denial.
- Do not broaden this implementation into arbitrary command sandboxing,
  cross-platform support, or shared provider-session semantics.
  The prerequisite runtime rejects every command step in a required-isolation
  workflow. The reusable launch request is a closed union:
  `workflow_provider` couples a typed result channel to root lifecycle
  scope/ordinal, while `controller_attempt` couples `result_channel: "none"`
  to a caller-owned external lifecycle/attestation sink and forbids workflow
  identity. A later experiment task must add a pinned built-in
  certified-adapter identity/runtime seam before its in-workflow checks are
  admitted. No-policy command behavior remains unchanged.

## Planned File Layout

Create the focused implementation units:

```text
orchestrator/providers/
  isolation.py                    # policy, canonical identity, launch-plan types
  isolation_environment.py        # closed manifest and run-owned frozen snapshot
  isolation_candidate.py          # candidate authority admission
  isolation_runtime_authority.py  # pinned .orchestrate/state/result authority
  isolation_network_preflight.py  # denied endpoints + listener inventory
  isolation_backend.py            # backend protocol, registry, capability probe
  isolation_bubblewrap.py         # Linux projection and process lifecycle
  provider_launch_shim.py          # bounded fd-3 bootstrap + inner group proof
  isolation_bundle_broker.py      # phase-private active-result transfer
  isolation_attestation.py        # closed attempt evidence and state references
  schemas/
    __init__.py
    provider-phase-isolation-v1.schema.json
    provider-environment-manifest-v1.schema.json
    provider-isolation-network-inventory-v1.schema.json
    provider-isolation-bundle-transfer-v1.schema.json
    provider-isolation-attestation-v1.schema.json
    provider-isolation-lifecycle-prefix-v1.schema.json

tests/
  fixtures/provider_isolation/
    probe_provider.py
    public_cli_g0/               # reviewed reusable external-control-plane templates
  test_provider_isolation_policy.py
  test_provider_isolation_schema_resources.py
  test_provider_isolation_environment.py
  test_provider_isolation_environment_cli.py
  test_provider_launch_shim.py
  test_provider_isolation_candidate.py
  test_provider_isolation_runtime_authority.py
  test_provider_isolation_network_preflight.py
  test_provider_isolation_backend.py
  test_provider_isolation_bundle_broker.py
  test_provider_isolation_attestation.py
  test_provider_isolation_execution.py
  test_provider_isolation_cli.py
  test_provider_isolation_runtime_writers.py
  test_provider_phase_information_isolation_e2e.py
```

The detailed tasks also touch these owners/files when their contract requires
it (some listed CLI helpers are new):

```text
orchestrator/providers/executor.py
orchestrator/providers/types.py
orchestrator/contracts/output_contract.py
orchestrator/workflow/executor.py
orchestrator/workflow/calls.py
orchestrator/workflow/call_frame_state.py
orchestrator/workflow/state_layout.py
orchestrator/workflow/provider_attempts.py
orchestrator/workflow/prompt_dependency_evidence.py
orchestrator/cli/main.py
orchestrator/cli/commands/provider_isolation_environment_manifest.py
orchestrator/cli/commands/provider_isolation_network_inventory.py
orchestrator/cli/commands/run.py
orchestrator/cli/commands/resume.py
orchestrator/state.py
orchestrator/workflow_lisp/lowering/effects.py
orchestrator/workflow_lisp/lowering/phase_scope.py
orchestrator/workflow_lisp/typed_prompt_inputs.py
orchestrator/workflow/prompting.py
orchestrator/workflow_lisp/build.py
orchestrator/workflow_lisp/build_artifacts.py
orchestrator/workflow_lisp/lexical_checkpoints.py
tests/test_workflow_lisp_build_artifacts.py
tests/test_workflow_lisp_lexical_checkpoints.py
tests/test_subworkflow_calls.py
tests/test_provider_attempt_allocation.py
tests/test_prompt_dependency_evidence.py
tests/test_workflow_lisp_typed_prompt_inputs.py
tests/test_workflow_lisp_lowering.py
tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py
docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md
docs/lisp_workflow_drafting_guide.md
specs/index.md
specs/versioning.md
specs/acceptance/index.md
specs/providers.md
specs/security.md
specs/state.md
specs/io.md
specs/cli.md
docs/capability_status_matrix.md
docs/design/README.md
docs/index.md
```

If implementation reveals that a different existing module owns one of these
contracts, stop and correct the plan rather than adding a parallel owner.

## Gate Sequence

| Gate | Required evidence | Failure action |
| --- | --- | --- |
| `I0E` environment feasibility | closed manifest, safe snapshot, in-prefix executable/interpreter resolution, and tamper tests pass | Stop; revise packaging before Bubblewrap |
| `I0G` rootless launch authority | ordinary-user launch with exact host/inner group binding, closed object/descriptor projection, and no privileged launcher passes both-direction tests | Stop; do not begin the production backend or reuse the sudo-backed proof |
| `I0` backend feasibility | Bubblewrap probe allows candidate/product/result behavior and denies every known external path/descriptor/terminal escape without a broad host mount | Stop; revise the design/backend before runtime integration |
| `I1` policy, admission, and broker | strict policy identity, candidate admission, fixed bundle retention, and valid/missing/invalid/symlink/oversize/retry behavior | Stop; do not integrate `ProviderExecutor` |
| `I1C` typed consumer carriage | every declared scalar/relpath is rendered and evidenced at the provider prompt seam | Stop; G0 cannot close and executor integration must not claim readiness |
| `I2` executor integration | every isolated attempt uses the launcher; the workflow root-owned lifecycle and separate controller-sink lifecycle, no-relaunch gate, timeout/retry/quiescence, result, attestation, handoff, and closure matrices pass | Fix before CLI/state work |
| `I3` public CLI/resume | distinct policy/environment/backend provenance plus every allocated lifecycle reconcile fail closed before launch | Fix before G0 rerun |
| `I4` original G0 rerun | two-phase public CLI test plus controller-attempt certified-check no-result denial/attestation proof pass all positive and negative assertions | Keep experiment `G0_BLOCKED` |
| `I5` live provider and broad regression | intended sealed provider rootfs works; affected and broad suites pass | Do not declare prerequisite complete |

## Task 1: Define The Versioned Policy And Immutable Identity

**Files:**

- Create: `orchestrator/providers/schemas/__init__.py`
- Create:
  `orchestrator/providers/schemas/provider-phase-isolation-v1.schema.json`
- Create: `orchestrator/providers/isolation.py`
- Create: `tests/test_provider_isolation_policy.py`
- Create: `tests/test_provider_isolation_schema_resources.py`
- Modify: `orchestrator/providers/__init__.py`
- Modify: `pyproject.toml`
- Modify: `specs/providers.md`
- Modify: `specs/security.md`

- [ ] **Step 1: Add and collect the policy tests**

Cover:

- the exact `provider_phase_isolation.v1` top-level fields;
- recursive rejection of unknown fields and versions;
- `mode == "required"` only;
- `backend == "bubblewrap.v1"` for the first release;
- `session_mode == "fresh_only"`;
- candidate read/write access with `.orchestrate` masked;
- an absolute provider-environment root, absolute provider-visible build
  prefix, and exact `sha256:<64 hex>` digest;
- provider prefix outside the runtime overlay roots `/home`, `/workspace`,
  `/tmp`, and `/run`, plus kernel/reserved destinations;
- `process_environment.credential_env` as a unique ordered set of valid names;
- rejection of runtime, loader, interpreter, shell-bootstrap, locale/time, and
  wildcard-reserved credential names, including `PATH`, `HOME`, `XDG_*`,
  `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`, `LD_PRELOAD`,
  `LD_LIBRARY_PATH`, `BASH_ENV`, `ENV`, `NODE_OPTIONS`, and
  `SSH_AUTH_SOCK`;
- `result_bundle.max_bytes` as a positive integer no larger than `16_777_216`;
- `shared_network_review` with an absolute private inventory path, canonical
  SHA-256 digest, and exact `accept_unlisted_reachability` decision;
- the five independently represented history-retrieval capabilities, with v1
  fixing provider transport to `allow` and all four retrieval channels to
  `deny`;
- `history_retrieval.eligibility_requirement` restricted to `classify` or
  `require_causal`;
- canonical JSON identity independent of object key order;
- whole-policy golden identities with a fixed
  `provider_environment.digest` input: changing a non-environment policy field
  changes the complete policy digest while preserving that embedded
  environment identity, and substituting the environment digest as the
  whole-policy digest is rejected; Task 1A owns the independent canonical
  manifest golden and paired cross-fill tests; and
- one canonical isolation JSON byte contract shared by policy, manifest,
  network inventory, bundle-transfer journal, and attestation: UTF-8, sorted
  keys, compact separators, `ensure_ascii=False`, `allow_nan=False`, no floats,
  and exactly one trailing LF;
- filesystem path fields require Unicode NFC, with manifest rows sorted by
  normalized relative-path UTF-8 bytes; and
- stable `provider_isolation_policy_invalid` issues with JSON paths.

Run:

```bash
pytest --collect-only -q tests/test_provider_isolation_policy.py
pytest --collect-only -q tests/test_provider_isolation_schema_resources.py
```

Expected: the intended tests collect.

- [ ] **RED: Run before creating the policy module**

```bash
pytest -q \
  tests/test_provider_isolation_policy.py \
  tests/test_provider_isolation_schema_resources.py
```

Expected: FAIL because the versioned loader/types and installed-wheel
package-data contract do not exist.

- [ ] **Step 2: Implement the minimum policy model**

Add immutable types for:

- `ProviderPhaseIsolationPolicy`
- `ProviderEnvironmentIdentity`
- `HistoryRetrievalPolicy`
- `ProviderIsolationIssue`

Load the packaged schema with `importlib.resources`; do not depend on the
current working directory. Return all deterministic validation issues before
raising the public policy error. The whole-policy identity is SHA-256 over the
complete validated `provider_phase_isolation.v1` canonical isolation JSON
bytes. It is distinct from `provider_environment.digest`, which Task 1A
computes from canonical `provider_environment_manifest.v1` bytes. Implement one shared
`canonical_isolation_json_bytes` helper and use golden ASCII, Unicode,
composed/decomposed-path, key-order, and row-order vectors; do not duplicate
serialization in later manifest or attestation modules.

Add explicit setuptools package-data for
`orchestrator.providers.schemas/*.json`. The resource test builds a wheel,
installs it into an isolated temporary target, imports only from that install,
and loads every schema present through `importlib.resources`. Inspecting or
loading resources from the source checkout is not sufficient.

- [ ] **Step 3: Add the normative policy/security contract**

Document:

- omitted policy means current unrestricted behavior;
- required policy is fail-closed;
- built-in tool bypass flags are not isolation;
- copied workspaces are not OS boundaries;
- isolated profiles require sealed provider rootfs snapshots;
- provider credentials are the intersection of the policy allowlist and each
  provider step's declared secrets; authored provider `env` is unsupported in
  v1; and
- no control/controller/evaluator/peer/parent authority may be granted.

Do not describe the feature as implemented until the final integration task
lands.

- [ ] **GREEN: Verify focused and provider contract selectors**

```bash
pytest -q tests/test_provider_isolation_policy.py
pytest -q tests/test_provider_isolation_schema_resources.py
pytest -q tests/test_provider_execution.py
git diff --check -- \
  orchestrator/providers/isolation.py \
  orchestrator/providers/schemas \
  tests/test_provider_isolation_policy.py \
  tests/test_provider_isolation_schema_resources.py \
  pyproject.toml \
  specs/providers.md \
  specs/security.md
```

Expected: PASS.

- [ ] **Step 4: Independent reviews and commit**

Specification review checks schema/design fidelity. Quality review checks
canonicalization, strict validation, packaged-resource loading, and stable
diagnostics.

```bash
git add \
  orchestrator/providers/__init__.py \
  orchestrator/providers/isolation.py \
  orchestrator/providers/schemas \
  tests/test_provider_isolation_policy.py \
  tests/test_provider_isolation_schema_resources.py \
  pyproject.toml \
  specs/providers.md \
  specs/security.md
git commit -m "feat(providers): define phase isolation policy"
```

## Task 1A: Prove The Sealed Provider Rootfs And Snapshot Identity

This task is the `I0E` stop/go gate. The actual experiment provider executable
chain—and the deterministic fixture interpreter when it is a separate
chain—must launch from the sealed rootfs offline before Bubblewrap projection
work continues; a fixture-only or toy executable is insufficient.

Current-host status is `I0E_PASSED`. The owner installed the
reviewed AppArmor user-namespace profile, and the exact Bubblewrap UID/GID-map
gate now exits zero. The manifest-inode no-atime correction passed TDD and
independent quality re-review. The fresh v4 sealed snapshot at environment
digest
`sha256:f739b415b2dd73a656657d87f603acf67462ce8f1d19a086048f8897248e9c6c`
then passed two strict descriptor reloads and fixed-bootstrap validation. The
owner-run cleared-supplementary-group diagnostic, `codex --version`, and
`codex --help` proof passed from a delegated transient user scope, including
three post-probe strict reloads and zero cgroup residue. Both final independent
evidence reviews approved promotion.

That result remains truthful sealed-environment evidence, but its
sudo-assisted empty-group launch is not the continuing launch prerequisite.
Task 1B supersedes only that proxy with the rootless `I0G` contract. Because
the packaged shim changes, Task 1B must publish a fresh immutable snapshot
identity; it must not mutate, relabel, or delete the accepted v4 snapshot or
proof.

**Files:**

- Create:
  `orchestrator/providers/schemas/provider-environment-manifest-v1.schema.json`
- Create: `orchestrator/providers/isolation_environment.py`
- Create: `orchestrator/providers/provider_launch_shim.py`
- Create:
  `orchestrator/cli/commands/provider_isolation_environment_manifest.py`
- Create: `tests/test_provider_isolation_environment.py`
- Create: `tests/test_provider_isolation_environment_cli.py`
- Create: `tests/test_provider_launch_shim.py`
- Create: `docs/reports/provider-isolation-environment-feasibility/README.md`
- Modify: `orchestrator/providers/isolation.py`
- Modify: `orchestrator/cli/commands/__init__.py`
- Modify: `orchestrator/cli/main.py`
- Modify: `tests/test_provider_isolation_policy.py`
- Modify: `tests/test_provider_isolation_schema_resources.py`
- Modify: `specs/providers.md`
- Modify: `specs/security.md`
- Modify: `specs/cli.md`

- [x] **Step 1: Add and collect closed-manifest tests**

The canonical `provider_environment_manifest.v1` contains the declared
provider-visible absolute build prefix, a mandatory `.` row for the mounted
root, and one ordered row per sealed-rootfs descendant. Test:

- closed schema validation at every object;
- normalized POSIX relative paths, entry kind, mode, file size/content digest,
  and original symlink text;
- ordinary writable source modes such as `0755`/`0644` normalized to exact
  post-copy no-write modes such as `0555`/`0444`, with that canonical
  destination manifest—not mutable source modes—forming
  `provider_environment.digest`; this provider-environment identity remains
  distinct from the canonical digest of the whole
  `provider_phase_isolation.v1` policy;
- the root `.` row receives the same mode/xattr and before/after identity checks
  as every descendant;
- mutable source root/entries must be controller-owned and not group/world
  writable; owner/mode mutation and ABA-style replacement fail admission;
- every row has fixed provider-visible `uid: 0`, `gid: 0`, `atime_ns: 0`, and
  `mtime_ns: 0`; host inode/ctime/owner are non-identity, while the user
  namespace maps controller-owned snapshot objects to provider-visible `0:0`;
- same bytes with different permitted source write bits/timestamps produce the
  same normalized manifest and snapshot (ownership must still satisfy the
  controller-owned admission rule), and a post-launch timestamp-stability
  probe observes no atime/mtime drift;
- nested writable source directories populated successfully through a private
  staging tree, then finalized bottom-up; symlink mode is fixed to Linux
  `0777`;
- deterministic identity independent of source-root path and directory
  enumeration order;
- an independent golden value for the canonical destination-manifest
  `provider_environment.digest`, plus paired cross-fill rejection tests using
  Task 1's whole-policy golden; assert that neither digest is substituted for
  or derived from the other;
- NFC path enforcement and deterministic UTF-8 byte ordering for Unicode
  relative paths using the shared canonical JSON vectors, with undecodable,
  surrogate-escaped, or non-NFC entry names and symlink-target bytes rejected
  rather than normalized;
- rejection of unknown fields, duplicate/ancestor-conflicting paths, absolute,
  broken, or escaping symlinks;
- rejection of sockets, FIFOs, devices, nested mountpoints (including
  same-device bind mounts detected by Linux `STATX_MNT_ID`, not `st_dev`),
  every xattr, and any inode whose `st_nlink` is not fully accounted for inside
  the rootfs; if mount ID cannot be obtained, only a trusted
  `/proc/self/mountinfo` correlation proving the same descriptor-bound property
  is acceptable, otherwise fail unavailable;
- normalization of every accepted in-source hardlink path to a distinct
  destination inode, with final `st_nlink == 1` for every regular snapshot
  file, so unrecorded source hardlink topology cannot change provider-visible
  identity;
- symmetric canonical non-overlap between the mutable environment source and
  candidate, workflow/source/extern, controller-state, scratch, control,
  evaluator, peer, and parent roots;
- the snapshot accepted only at
  `<run-root>/provider_environment_snapshots/<digest>/rootfs`, rejected under
  every other state subauthority or path alias, and still denied in
  provider-visible path space;
- exact expected digest mismatch;
- stable `provider_isolation_environment_invalid` versus
  `provider_isolation_environment_mismatch` diagnostics; and
- the controller-only
  `provider-isolation-environment-manifest --root <absolute-source>
  --provider-prefix <absolute-prefix> --output <absolute-manifest>` command
  atomically writes the same prospective assembled manifest, prints its digest,
  does not mutate/accept the source, and run-time snapshot assembly later
  requires the exact same digest. Its absolute output must be a new
  single-link `0600` regular file atomically published/fsynced in a pre-existing
  controller-owned `0700` real directory; reject symlink/existing-output,
  untrusted-ancestor and xattr cases. Its
  output authority must be disjoint in both containment directions from
  `--root`, and its basename must not already be a scanned source entry.

The completed v4 `provider-launch-shim.v1` tests historically required a
bounded binary
credential-pipe contract on fixed fd 3: magic/version, at most 32 unique
predeclared UTF-8 names of at most 128 bytes, values of at most 65,536 bytes,
and at most 262,144 total bytes, with no persistence. The environment assembler
must reject a source collision, inject the packaged resource at
`<provider_prefix>/libexec/provider-launch-shim-v1.py`, invoke it only with
manifest-backed `<provider_prefix>/bin/python -I -S`, suppress every `PYTHON*`
variable/site customization, and include the runtime-known shim,
interpreter/ELF-loader/library/Python-import/startup-configuration closure
identities in the final manifest/backend probe. Execute a nonce challenge
through that exact chain. That v4 shim joined a fresh empty session keyring,
dropped supplementary groups, closed every fd `>= 4` itself with verified
`close_range`/fdwalk behavior before reading credentials, validated only
predeclared names, set the final env without putting values in argv, zeroed its
input buffer, closed fd 3, installed seccomp denials for
`keyctl`/`add_key`/`request_key`, performed a second verified
`close_range(3, UINT_MAX)`/fdwalk after all bootstrap/import/seccomp work, and
execed the target with exactly fds 0/1/2.
Do not credit Bubblewrap or `CLOEXEC` with closure: test extra role-labeled
descriptors through a Bubblewrap-0.9.0-shaped exec boundary. Reject
`/etc/ld.so.preload`, candidate-resolving RPATH/RUNPATH, writable startup
configuration, and candidate/current-directory Python imports. Historical v4
coverage tested
truncated/oversized/duplicate/undeclared frames, source collision, interpreter
swap, child-observed env, empty groups, denied key syscalls, setup-FD closure,
and secret absence from argv/stderr/artifacts.

Run:

```bash
pytest --collect-only -q tests/test_provider_isolation_environment.py
pytest --collect-only -q tests/test_provider_isolation_environment_cli.py
pytest --collect-only -q tests/test_provider_isolation_schema_resources.py
pytest --collect-only -q tests/test_provider_launch_shim.py
pytest -q \
  tests/test_provider_isolation_environment.py \
  tests/test_provider_isolation_environment_cli.py \
  tests/test_provider_isolation_schema_resources.py \
  tests/test_provider_launch_shim.py
```

Expected: collection passes, then RED because the manifest/snapshot owner and
installed-wheel environment schema resource do not exist.

- [x] **Step 2: Implement manifesting and a run-owned snapshot**

Walk with descriptor-relative `lstat`/no-follow operations and record the root
and entry mount IDs. Reject every mount-ID crossing, including same-device bind
mounts; never infer this property from `st_dev`. Normalize manifest
modes by stripping source write bits. Populate an owner-writable, private
staging sibling without following links; copy every accepted source-hardlink
path to its own destination inode; compare source metadata before and after
each copy; require final regular-file `st_nlink == 1`; normalize owner and
atime/mtime without following links; then
`fchmod` files/directories to canonical final modes and fsync each finalized
inode bottom-up. Rebuild and require the final destination manifest, atomically
rename the complete staging directory (containing `rootfs` and its manifest) to
`provider_environment_snapshots/<digest>`, and fsync the authority parent. Open
and pin only the published `rootfs` descriptor for setup; never mount or
re-resolve the mutable source tree. Use no-atime reads for controller
verification and require the read-only projection to preserve fixed times.

Expose that same deterministic prospective assembly through the controller-only
environment-manifest command. It writes the closed manifest atomically to an
absolute output, prints its canonical digest for policy authoring, and neither
mutates the source nor creates an accepted runtime snapshot. The later run
repeats assembly into its run-owned authority and requires the operator's exact
digest. The command validates the whole rootfs and fixed shim/interpreter
startup closure; it does not claim every arbitrary provider executable is
launchable. Run validates the actual compiled provider entrypoint and complete
shebang/ELF closure.

Add mutation tests that change the source during copy, exchange a source entry,
change root mode/xattrs, mutate the finished root mode/xattrs/timestamps,
replace a parent with a symlink, and modify the source after successful
snapshot creation. All races except post-snapshot source mutation must fail
closed; post-snapshot source mutation must not change the pinned launch
identity. Inject crashes during nested-directory population, root/descendant
normalization, final chmod, manifest verification, and rename; no partial
staging tree may be resumed, mounted, or observed by a provider.

- [x] **Step 3: Prove Linux runtime closure inside the sealed rootfs**

The sealed tree mirrors provider-visible absolute paths below `/`; it includes
the declared build prefix and any manifest-backed `/lib*`, `/usr`, `/etc`
loader, NSS/DNS, CA material, and the exact reviewed launch shim/interpreter
chain needed by the provider. Test:

- non-executing shebang plus ELF `PT_INTERP`, `DT_NEEDED`, `DT_RPATH`, and
  `DT_RUNPATH` parsing discovers the complete launch chain without `ldd` or
  controller-namespace execution, applying the target loader's reviewed search
  order and manifest-backed cache/default directories;
- `$ORIGIN`/`${ORIGIN}` resolution is relative to the containing object, while
  unknown loader tokens, escaping/ambiguous paths, and unpackaged resolutions
  are rejected;
- a marker binary proves admission parsing itself cannot execute the provider,
  interpreter, or candidate;
- `PATH` resolution at the declared prefix;
- an absolute in-prefix script shebang;
- an ELF interpreter at a conventional `/lib64/...` path;
- `/usr/bin/env` accepted only when supplied by the sealed rootfs;
- missing/unpackaged shebang, interpreter, shared-library, or config paths
  rejected before launch;
- provider executable, interpreter, and effective PATH never resolve to an
  ambient host file;
- actual provider `--version`/`--help` and DNS/NSS/config probes run only inside
  a temporary sealed-rootfs Bubblewrap namespace, using a standalone raw-bwrap
  harness until the production backend exists; and
- that v4 harness invoked the real launch shim, passed credentials only through
  its bounded pipe, and proved the final child had empty supplementary groups,
  denied key syscalls, and no bootstrap FD.

Run the actual experiment provider executable chain from the sealed rootfs in
an offline `--version`/`--help` mode, plus an offline DNS/NSS/config-resolution
preflight. If deterministic backend tests use a separate fixture interpreter,
package and prove that chain too; it cannot substitute for the experiment
provider. Execute with an empty environment in a minimal rootfs-only
namespace/chroot/one-off Bubblewrap projection so shebangs and ELF loaders
cannot resolve from the host. Record command, exit status, provider/Node/Python
identities, rootfs manifest digest, loader closure, and limitations in the
feasibility report. Use tmux if packaging or checks are long-running. A skip,
fixture-only, or toy-only pass is `I0E_BLOCKED`.

- [x] **GREEN: Verify identity, mutation, and packaged executable**

```bash
pytest -q \
  tests/test_provider_isolation_environment.py \
  tests/test_provider_isolation_environment_cli.py \
  tests/test_provider_isolation_policy.py \
  tests/test_provider_isolation_schema_resources.py \
  tests/test_provider_launch_shim.py
git diff --check -- \
  orchestrator/providers/isolation.py \
  orchestrator/providers/isolation_environment.py \
  orchestrator/providers/provider_launch_shim.py \
  orchestrator/cli/commands/__init__.py \
  orchestrator/cli/main.py \
  orchestrator/cli/commands/provider_isolation_environment_manifest.py \
  orchestrator/providers/schemas/provider-environment-manifest-v1.schema.json \
  tests/test_provider_isolation_environment.py \
  tests/test_provider_isolation_environment_cli.py \
  tests/test_provider_launch_shim.py \
  tests/test_provider_isolation_policy.py \
  tests/test_provider_isolation_schema_resources.py \
  docs/reports/provider-isolation-environment-feasibility/README.md \
  specs/providers.md \
  specs/security.md \
  specs/cli.md
```

Expected: PASS, including one real intended-provider offline execution.

- [x] **Step 4: Independent reviews and commit**

Specification review checks rootfs/prefix/identity fidelity. Quality/security
review checks descriptor operations, xattrs, hardlinks, mutation windows,
conventional loader closure, secret absence, and evidence realism.

```bash
git add \
  orchestrator/providers/isolation.py \
  orchestrator/providers/isolation_environment.py \
  orchestrator/providers/provider_launch_shim.py \
  orchestrator/cli/commands/__init__.py \
  orchestrator/cli/main.py \
  orchestrator/cli/commands/provider_isolation_environment_manifest.py \
  orchestrator/providers/schemas/provider-environment-manifest-v1.schema.json \
  tests/test_provider_isolation_environment.py \
  tests/test_provider_isolation_environment_cli.py \
  tests/test_provider_launch_shim.py \
  tests/test_provider_isolation_policy.py \
  tests/test_provider_isolation_schema_resources.py \
  docs/reports/provider-isolation-environment-feasibility/README.md \
  specs/providers.md \
  specs/security.md \
  specs/cli.md
git commit -m "feat(providers): seal provider rootfs identity"
```

## Task 1B: Prove Rootless Group And Object Authority

This task is the `I0G` stop/go gate. It replaces the empty-supplementary-group
proxy used by the historical Task 1A proof with the composite rootless
contract in the governing design. It does not implement the production
Bubblewrap backend, result broker, runtime integration, or attestation schema.

Task 1B passed `I0G` for the exact v6 identity recorded in the
[rootless-launch feasibility report](../../reports/provider-isolation-rootless-launch-feasibility/README.md).
Both ordered final reviews approved the bound implementation and evidence.
This opens Task 2 (`I0`) only; the production backend and every later
integration, attestation, public `G0`, and live-provider gate remain open.

**Files:**

- Modify: `orchestrator/providers/provider_launch_shim.py`
- Modify: `orchestrator/providers/isolation_environment.py`
- Modify: `tests/test_provider_launch_shim.py`
- Modify: `tests/test_provider_isolation_environment.py`
- Modify:
  `docs/superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md`
- Modify:
  `docs/reports/provider-isolation-environment-feasibility/README.md`
- Create:
  `docs/reports/provider-isolation-rootless-launch-feasibility/README.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/design/README.md`
- Modify:
  `docs/superpowers/plans/2026-07-23-orc-vs-one-shot-experiment.md`
- Modify: `specs/providers.md`
- Modify: `specs/security.md`

- [x] **Step 1: RED-test the inner namespace validator**

Add table-driven tests for a pure fail-closed validator in the packaged shim.
The positive fixture has all four all-zero
real/effective/saved/filesystem UID/GID status columns,
`setgroups: deny`, exactly one normalized UID-map row, exactly one normalized
GID-map row, a live nonzero kernel overflow GID, and only primary/overflow
supplementary values with counts equal to the trusted launch expectations.
Negative fixtures cover:

- missing, unreadable, malformed, empty, or multi-row maps;
- each nonzero inner real, effective, saved, or filesystem UID/GID column;
- `setgroups` missing or not exactly `deny`;
- missing, malformed, zero, or out-of-range `overflowgid`;
- an inner supplementary value other than primary or overflow;
- primary/overflow count mismatch; and
- a launch argument with a negative, unbounded, duplicate, or inconsistent
  expected count; and
- missing, duplicate, malformed, early-EOF, or surviving readiness-descriptor
  behavior.

The validator must run before credential fd 3 is read. Tests assert ordering
and the stable redacted shim failure only; they do not assert prose.

Run:

```bash
pytest -q \
  tests/test_provider_launch_shim.py \
  -k 'group or shim_bootstrap_orders'
```

Expected: the new cases fail because the old shim attempts
`os.setgroups([])` and has no normalized boundary validator.

- [x] **Step 2: GREEN-implement the minimal inner validator**

Replace `_drop_supplementary_groups()` with a bounded validator that reads
`/proc/self/{uid_map,gid_map,setgroups,status}` and
`/proc/sys/kernel/overflowgid` without following a caller-supplied path.
Extend the closed shim argv with controller-supplied expected primary and
overflow counts plus one fixed setup-only boundary-readiness descriptor. After
validation and before credential ingestion, write exactly one fixed byte,
close that descriptor, verify it closed, and only then read fd 3. Do not
hard-code `65534`, infer host group IDs from provider-visible overflow values,
add a privileged clearing path, or weaken failure handling when proc data is
unavailable.

Run:

```bash
pytest -q \
  tests/test_provider_launch_shim.py \
  -k 'group or shim_bootstrap_orders'
```

Expected: pass.

- [x] **Step 3: Exercise the shim through ordinary-user Bubblewrap**

Update the controller-side raw-probe helper so its process-level tests execute
the shim inside an explicitly labeled, test-only rootless Bubblewrap wrapper.
The wrapper may project host `/` read-only only for shim-mechanics tests; it is
not production isolation evidence and must never be used by `I0`, G0, or the
public runtime. Add an availability probe/skip for hosts where the reviewed
rootless user-namespace backend cannot start. Preserve direct unit tests for
frame parsing, fd actions, redaction, and cleanup.

Run:

```bash
pytest -q tests/test_provider_launch_shim.py
```

Expected: all module tests pass from the normal owner session with no
supplementary-group deselections and no privilege prompt.

- [x] **Step 4: Add the host-relative half to the raw `I0G` proof**

Using a fresh one-use evidence authority, launch the real sealed provider/shim
chain directly as the owner. Keep the credential pipe unreleased while the
controller waits for both Bubblewrap's JSON child PID and the shim's one-byte
boundary-ready signal, binds the final child with a pidfd plus no-follow proc
directory and process-start identity, and reads its maps, `setgroups`, and
underlying group vector from the host namespace. Bubblewrap's child-PID event,
`--info-fd`, `--block-fd`, or the outer exec handshake alone is not readiness.
Require:

- exact rows `0 <controller-euid> 1` and
  `0 <controller-egid> 1`;
- `setgroups: deny`;
- exact multiset equality with the controller's captured prelaunch groups;
- matching inner primary/overflow counts;
- unchanged process-start identity and a live pidfd before and immediately
  before the first credential byte;
- no credential write before both inner readiness and host validation;
- no setup descriptor at final exec; and
- the existing capability, keyring, network, PID/session, nested-userns,
  cgroup-quiescence, nonce, version, and help checks.

The proof must use a minimal sealed-rootfs/candidate/scratch projection.
Exercise the foreign-owned, supplementary-group-readable case as a
deterministic admission/mount-plan negative fixture that rejects before
opening the sentinel; do not read an unrelated host secret as positive
evidence. A broad `--ro-bind / /` is forbidden in the accepted proof.

- [x] **Step 5: Publish and verify a fresh sealed identity**

The shim source is part of the reviewed bootstrap identity. Update its
independently pinned source digest, rebuild the prospective manifest from the
same admitted source into fresh v5-or-later names, assemble a fresh run-owned
snapshot, and strictly reload it twice before execution. Never mutate,
overwrite, repair, or delete v4. Run the diagnostic, real provider
`--version`, and real provider `--help` through the rootless proof, then
strictly reload again after each probe.

Record immutable paths, canonical environment/bootstrap digests, commands,
group observations, cgroup cleanup, log digest, and rejected attempts in the
new
`docs/reports/provider-isolation-rootless-launch-feasibility/README.md`.
The old Task 1A report remains immutable historical evidence except for its
single routing pointer to this follow-on report.

- [x] **Step 6: Add normative and evidence status updates**

Update `specs/providers.md` and `specs/security.md` with the composite
contract: retained groups can carry host DAC authority, one-row maps are only
one necessary check, and the closed object/descriptor projection is the
actual denial boundary. Record that invocation is rootless and that a host
which disables unprivileged user namespaces is unavailable rather than
silently privileged.

Promote the design amendment and `I0G` report only after both independent
reviews approve the exact implementation/evidence identity.

- [x] **Step 7: Run focused, aggregate, and broad verification**

Run narrow selectors first:

```bash
pytest --collect-only -q tests/test_provider_launch_shim.py
pytest -q \
  tests/test_provider_launch_shim.py \
  tests/test_provider_isolation_environment.py \
  tests/test_provider_isolation_environment_cli.py \
  tests/test_provider_isolation_policy.py \
  tests/test_provider_isolation_schema_resources.py
git diff --check -- \
  orchestrator/providers/provider_launch_shim.py \
  orchestrator/providers/isolation_environment.py \
  tests/test_provider_launch_shim.py \
  tests/test_provider_isolation_environment.py \
  docs/superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md \
  docs/superpowers/plans/2026-07-23-provider-phase-information-isolation.md \
  docs/superpowers/plans/2026-07-23-orc-vs-one-shot-experiment.md \
  docs/reports/provider-isolation-environment-feasibility/README.md \
  docs/reports/provider-isolation-rootless-launch-feasibility/README.md \
  docs/capability_status_matrix.md \
  docs/design/README.md \
  specs/providers.md \
  specs/security.md
```

Run `pytest -q -n 16 --dist=worksteal` in tmux and compare any failures with
the current reviewed broad baseline. Do not erase an unrelated failure or
call it passing.

- [x] **Step 8: Obtain both reviews and commit**

First request an independent specification review against the governing
design, including the host-DAC nuance and both-direction controls. After it
approves, request an independent quality/evidence review. Correct and rerun
the complete affected gate after either review finds an issue.

Stage only Task 1B paths and commit:

```bash
git add \
  orchestrator/providers/provider_launch_shim.py \
  orchestrator/providers/isolation_environment.py \
  tests/test_provider_launch_shim.py \
  tests/test_provider_isolation_environment.py \
  docs/superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md \
  docs/superpowers/plans/2026-07-23-provider-phase-information-isolation.md \
  docs/superpowers/plans/2026-07-23-orc-vs-one-shot-experiment.md \
  docs/reports/provider-isolation-environment-feasibility/README.md \
  docs/reports/provider-isolation-rootless-launch-feasibility/README.md \
  docs/capability_status_matrix.md \
  docs/design/README.md \
  specs/providers.md \
  specs/security.md
git commit -m "feat(providers): prove rootless launch authority"
```

## Task 2: Prove The Bubblewrap Backend Before Runtime Integration

This task is the `I0` stop/go spike. Do not touch `ProviderExecutor` until it
passes. Task 1B `I0G` is a hard prerequisite.

Current-host status is `I0_PASSED`. The standalone production backend passed
workflow-provider, controller-attempt, and timeout/quiescence directions under
ordinary-user Bubblewrap, and both ordered independent reviews approved the
result. This opens Task 3 only; broker, executor, public run/resume,
attestation, the public `G0` rerun, and live smoke remain unimplemented.

**Files:**

- Modify: `orchestrator/providers/isolation.py`
- Create: `orchestrator/providers/isolation_candidate.py`
- Create: `orchestrator/providers/isolation_runtime_authority.py`
- Create: `orchestrator/providers/isolation_network_preflight.py`
- Create:
  `orchestrator/providers/schemas/provider-isolation-network-inventory-v1.schema.json`
- Create: `orchestrator/providers/isolation_backend.py`
- Create: `orchestrator/providers/isolation_bubblewrap.py`
- Modify: `orchestrator/providers/provider_launch_shim.py`
- Create: `tests/fixtures/provider_isolation/probe_provider.py`
- Create: `tests/test_provider_isolation_candidate.py`
- Create: `tests/test_provider_isolation_runtime_authority.py`
- Create: `tests/test_provider_isolation_network_preflight.py`
- Create: `tests/test_provider_isolation_backend.py`
- Create: `tests/test_provider_isolation_backend_identity_negatives.py`
- Modify: `tests/test_provider_launch_shim.py`
- Modify: `orchestrator/providers/isolation_environment.py`
- Modify: `tests/test_provider_isolation_schema_resources.py`
- Create:
  `docs/reports/provider-isolation-backend-feasibility/README.md`
- Modify:
  `docs/superpowers/plans/2026-07-23-provider-phase-information-isolation.md`
- Modify:
  `docs/superpowers/plans/2026-07-23-orc-vs-one-shot-experiment.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/design/README.md`

- [x] **Step 1: Add backend capability and launch-plan tests**

The tests build separate temporary roots for:

- candidate product;
- provider environment;
- active result scratch;
- external control;
- controller state;
- evaluator;
- peer arm; and
- parent checkout sentinel.

The probe receives exact forbidden absolute paths, attempts every read, scans
candidate `.orchestrate`, reads/writes the candidate, writes its active result,
attempts relative/absolute symlink escapes, and enumerates inherited file
descriptors. The test opens one forbidden sentinel and one forbidden directory
in the controller before launch; neither descriptor may cross the boundary.
The final provider enumerates every descriptor, permits exactly normalized
stdin/stdout/stderr fds 0/1/2, and attempts `openat("..")` against every
observed directory descriptor in negative probes. Candidate, rootfs, scratch,
and pinned backend-executable descriptors may reach Bubblewrap setup, but the
shim itself must preserve only the fixed readiness fd during its initial
fd-`>=4` sweep, signal and close it after validation, verify every fd `>=4`
closed before reading credential fd 3, close fd 3 after reading, then repeat a
close-all-fds-`>=3` sweep immediately before final exec. Run Bubblewrap with
the sanitized non-secret
environment, `--clearenv`, and the real credential-bootstrap shim; values must
be absent from Bubblewrap argv/environment. Do not rely on `CLOEXEC` or
Bubblewrap to close `/proc/self/fd/<N>` bind-source descriptors. The probe also
attempts
controlling-terminal
injection; the child must be in a new terminal session and the probe must not
regain the controller TTY.

Backend lifecycle tests also require one crash-durable, PID-reuse-safe
containment slot per attempt. For the first backend, use an exact
controller-owned delegated cgroup-v2 leaf (or stop and review an equally strong
kernel mechanism), record its stable identity, place the gated setup child in
it, exercise `cgroup.kill`, and require `cgroup.events` to report
`populated 0` before quiescence. Process groups, PID files, namespace inode
numbers, and `--die-with-parent` alone are not resume authority. The shim must
remain blocked from provider exec until a freshly persisted
`launch_committed` transition returns its one-use release permit; replay or
reload cannot obtain a permit. Test crash/reload on both sides of intent and
commit, PID reuse, a nonempty slot, and missing cgroup delegation. This slot is
for lifecycle membership/teardown proof, not resource quotas.

The reusable service-level request is one discriminated union, not independent
subject/result/sink fields. `workflow_provider` requires a typed-bundle channel
and aggregate-root scope/ordinal. `controller_attempt` requires
`result_channel: "none"`, caller kind/id, command/adapter identity, and a
caller-owned external lifecycle/attestation sink; it forbids provider template,
workflow scope/ordinal, and `provider_attempt_allocations`. The controller
variant performs the identical candidate/rootfs/process/environment projection
but creates no result scratch, sets no bundle environment variable, and never
invokes the broker. Reject every cross-combination before scratch or launch.
Also exercise the controller variant as the child launcher for a trusted
certified-check adapter: use a fresh product extract as candidate, zero
credentials, a controller-owned check-attempt identity, and adversarial product
code that tries every G0 sentinel. The child must be denied while the ambient
adapter only maps its exit to the separate typed command record. Test both plan
variants before executor integration.

Network-preflight tests define a closed
`provider_isolation_network_preflight.v1` capability result. Inventory
IPv4/IPv6 TCP/UDP and abstract AF_UNIX listeners through trusted kernel
interfaces. Atomically persist a bounded, recursively closed private report
with protocol, address/port or byte-safe abstract name, and owner identity
where safely obtainable. Encode the arbitrary bytes after an abstract socket's
leading NUL as lowercase hex plus exact byte length—never normalized text—and
test undecodable bytes and embedded NULs. Canonical/golden/tamper tests cover
the packaged schema. The inventory writer atomically publishes/fsyncs a new
single-link `0600` regular file only in a pre-existing controller-owned `0700`
real directory and rejects symlink/existing-output, untrusted-ancestor, xattr,
and candidate/environment/rootfs overlap cases. The policy
must reference its exact path/digest and acceptance decision, and launch
recomputes the inventory byte-for-byte. Public evidence persists only bounded
counts/digests and safe match codes.
Bounded probes cover the versioned cloud-metadata set plus runtime-known
Internet and abstract-UNIX control endpoints. A registered loopback TCP
sentinel and a registered abstract-socket sentinel must each fail before a
provider marker with `provider_isolation_local_service_exposure`, including
when it accepts and closes without returning a response. UDP follows a bounded
protocol-specific response/kernel-error contract rather than treating
`connect(2)` success alone as proof. Unregistered listeners remain in the
digest and explicit deployment trust assumption, not an automatic denial.
Timeouts, malformed responses, endpoint-set changes, and probe-result
canonicalization are deterministic.

Candidate-admission tests reject, before Bubblewrap:

- absolute, broken, or escaping symlinks while accepting safe in-root symlinks;
- undecodable, surrogate-escaped, or non-NFC candidate entry names and symlink
  target text;
- sockets, FIFOs, devices, nested mountpoints (including same-device bind
  mounts detected with Linux `STATX_MNT_ID`, never `st_dev` alone), and
  external hardlinks;
- canonical aliases and both containment directions for candidate,
  workflow/source/extern, controller-state, provider-environment
  source, scratch, control, evaluator, peer, and parent roots, with the frozen
  snapshot admitted only at its exact root-owned state subauthority;
- a rootfs manifest entry at any denied provider-visible absolute authority;
- rootfs structural ancestor directories `/`, `/home`, and `/tmp` accepted only
  when no descendant is packaged at/below a denied authority, with regular or
  symlink ancestor aliases rejected;
- a candidate whose first path component collides with `/bin`, `/sbin`,
  `/usr`, `/lib*`, `/etc`, `/opt`, `/proc`, `/dev`, `/run`, `/var`, or the
  sealed provider prefix, while explicitly accepting
  `/tmp/.../candidate` inside the invocation-private `/tmp` tmpfs; and
- a candidate outside the closed v1 `/home`, `/workspace`, or `/tmp`
  workspace components, or a rootfs that lacks the required empty structural
  mountpoints;
- a candidate root or existing entry that is not controller-owned or is
  group/world writable at admission, while separately accepting a
  descriptor-pinned sticky `/tmp` ancestor that cannot replace the root entry; and
- concurrent/non-exclusive candidate ownership.

Runtime-authority tests run before any frontend/build writer and require:

- a fresh isolated run accepts only an absent `.orchestrate`, creates/pins one
  private real directory with descriptor-relative operations, and records its
  candidate/runtime identities;
- resume accepts only those exact recorded identities;
- preexisting `.orchestrate` files/symlinks, root/ancestor swaps, symlinks or
  nested mounts in runtime/result ancestry—including same-device bind mounts
  detected by mount ID—and cross-boundary hardlinks fail before an outside
  write marker appears;
- a safe candidate symlink is rejected if it resolves into `.orchestrate`;
- every runtime descendant, canonical result, deterministic staged file, and
  invalid-result archive is opened relative to the held authority with no
  alternate product-visible alias; and
- launch-time revalidation catches replacement after early admission.

The test must inspect the generated argv/mount plan and reject:

- host-source `--bind / /` or `--ro-bind / /`, while requiring the verified
  run-owned rootfs descriptor as the only read-only `/` source;
- host-home mounts;
- control/controller/evaluator/peer/parent mounts;
- all-candidate-`.orchestrate` mounts; and
- support roots not contained in the digest-verified rootfs snapshot;
- absence of a new terminal session, PID namespace, capability drop,
  no-new-privileges behavior, user-namespace mapping to provider-visible
  uid/gid `0:0`, nested-user-namespace disablement, `--as-pid-1`, fixed isolated
  hostname, `--die-with-parent`, invocation-private `/tmp`, or
  invocation-private `/run` containing synthetic `HOME`; and
- any mount not in the closed candidate/rootfs/scratch/synthetic-kernel set.

Backend identity tests require a closed canonical
`provider_isolation_backend_identity.v1` with contract ID, fixed
`/usr/bin/bwrap` path, root-owned regular-file/real-ancestor trust result,
opened-descriptor SHA-256/size/mode/device/inode, normalized version, capability
probe-contract digest, and closed probe results. It also contains the ordered
non-executingly resolved host `PT_INTERP`/recursive
`DT_NEEDED`/RPATH/RUNPATH/loader-cache/startup-config closure with each
member's path/digest/metadata and trust result. Reject host
`/etc/ld.so.preload`, unsafe/relative RPATH/RUNPATH or unknown tokens, and any
closure member/ancestor that is non-root-owned, group/world-writable,
xattr-bearing, escaping, or changed. Accept merged-usr/SONAME symlink chains
only when every link/ancestor is safe and the original link text plus final
root-owned regular target identity is recorded; test the actual safe system
chains plus link swap, escape, and untrusted-owner/mode negatives. Reject a
same-version
PATH-shadowed/user-owned fake on initial preflight; symlinked, non-root-owned,
set-id, group/world-writable, or xattr-bearing binary; and a symlinked,
non-root-owned, group/world-writable, or changed ancestor. Replace the trusted
executable at the same path with bytes that report the same version;
preflight/launch must reject the swap. Also mutate the opened inode in place
with same-size bytes and preserved metadata; the required immediate pre-exec
trust-chain rewalk/descriptor rehash must reject it. Launch must never perform a
later PATH/pathname lookup. Replace only the host loader, one transitive
library, or loader cache while keeping Bubblewrap bytes/version unchanged; each
must change identity and fail launch/resume.

The backend identity also binds the selected crash-durable
containment/gated-release contract, the trusted cgroup-v2
mount/delegation identity used by the first backend, and closed
create/member/kill/empty/reload probe results. A same-path changed delegation or
weaker process-group/PID-file substitute fails preflight and resume.

The candidate's first component is a runtime-owned tmpfs overlay. Tests create
arbitrary admitted candidate roots below `/home`, `/workspace`, and `/tmp`
without packaging their full ancestry,
require only that resolved candidate ancestry is created below that overlay,
and reject collisions with sealed rootfs authorities.

Admission must walk descriptor-relatively, retain an `O_PATH`/directory
descriptor plus verified `(device, inode, mount_id)` and ancestry identity,
revalidate it immediately before launch, and bind that pinned descriptor.
Every environment, candidate, and runtime-ancestry walk uses
`STATX_MNT_ID` (or a trusted `/proc/self/mountinfo` correlation proving the same
descriptor-bound property) and rejects a different ID; `st_dev` equality is
never enough. Add bounded root/ancestor exchange and same-device bind-mount
tests that prove a pathname swap or bind cannot change the mounted authority.
Candidate contents remain writable; the pin protects the authority root, not
individual product bytes. Hold the exclusive candidate lease through
quiescence and test/document the explicit threat assumption that non-provider
host users/processes do not mutate it during invocation; initial owner/mode
checks do not claim to prevent the provider from later changing product modes.

Pure policy/mount-plan and fail-closed tests run on every host. Mark only the
real Bubblewrap execution cases with a Linux/backend availability condition so
the broad suite remains portable. A skip is never `I0` acceptance evidence:
this task must also record one real passing Linux execution with the exact
backend intended for deployment.

- [x] **Step 2: Verify collection**

```bash
pytest --collect-only -q tests/test_provider_isolation_backend.py
pytest --collect-only -q tests/test_provider_isolation_candidate.py
pytest --collect-only -q tests/test_provider_isolation_runtime_authority.py
pytest --collect-only -q tests/test_provider_isolation_network_preflight.py
pytest --collect-only -q tests/test_provider_isolation_schema_resources.py
pytest --collect-only -q \
  tests/test_provider_isolation_backend_identity_negatives.py
pytest --collect-only -q tests/test_provider_launch_shim.py
```

Expected: all backend tests collect.

- [x] **RED: Run the real backend probe before implementation**

```bash
pytest -q tests/test_provider_isolation_backend.py -k "projection or sentinel or symlink"
pytest -q \
  tests/test_provider_isolation_candidate.py \
  tests/test_provider_isolation_runtime_authority.py \
  tests/test_provider_isolation_network_preflight.py \
  tests/test_provider_isolation_schema_resources.py \
  tests/test_provider_launch_shim.py
```

Expected: FAIL because no backend constructs the namespace.

- [x] **Step 3: Implement backend protocol and host preflight**

Add:

- `ProviderIsolationBackend` protocol;
- backend registry mapping `bubblewrap.v1` only to fixed `/usr/bin/bwrap`;
- descriptor-relative, no-follow root-owned executable/ancestor
  mode/xattr trust validation plus Bubblewrap version identity;
- opened-descriptor executable digest/metadata, non-executingly resolved and
  pinned host loader/library/cache/config closure, and canonical backend
  identity;
- kernel/user-namespace preflight;
- crash-durable containment-slot admission, identity, membership, kill/empty
  proof, and the trusted one-use launch-release gate;
- immutable `ProviderInvocationIsolationPlan`;
- pinned `ProviderIsolationRuntimeAuthority` with descriptor-relative
  fresh/resume creation, open/read/write/atomic-replace, and identity
  revalidation operations;
- closed denied-endpoint/cloud-metadata probe plus bounded TCP/UDP/abstract-UNIX
  listener inventory and attested remaining-reachability trust assumption;
- exact `provider-launch-shim.v1`/interpreter closure and credential bootstrap
  contract;
- the closed workflow-provider/typed-root-authority versus
  controller-attempt/none-external-sink request union, with no constructible
  cross-combination;
- deterministic mount-plan rendering; and
- stable unavailable/invalid-plan diagnostics.

Backend selection must never search `PATH` or accept an override. Walk the
fixed `/usr/bin/bwrap` trust chain descriptor-relatively without symlinks,
verify root ownership/modes/xattrs, and execute only its pinned verified
descriptor (or platform-equivalent descriptor exec). Rewalk the trust chain,
rehash full executable and startup-closure bytes, and revalidate metadata at
each launch; obtain version only from that descriptor and fail unavailable
when trust, closure resolution, or descriptor execution cannot be enforced.
Never use `ldd`; statically parse the host ELF and loader cache, reject
`/etc/ld.so.preload` and unsafe RPATH/RUNPATH, and pin/recheck the complete
root-owned no-xattr closure, including every safe system-symlink text and final
regular target.

The controller subprocess boundary passes only the role-labeled setup
descriptors plus normalized fds 0/1/2 and credential fd 3.
Use Bubblewrap's descriptor-bound bind operations for the role-labeled
candidate/rootfs/scratch mount sources. Those and the pinned Bubblewrap
executable descriptor are setup-only: pass them only to Bubblewrap, then have
the packaged shim preserve only the readiness fd during its initial fd-`>=4`
closure, signal/close it after validation, and verify all fds `>=4` closed
before reading credentials. After bootstrap it closes fd 3 and repeats
`close_range(3, UINT_MAX)`/fdwalk; none may remain in the provider FD allowlist.
The final provider receives
exactly fds 0/1/2. The capability fixture must enumerate that
complete final set and attempt `openat("..")` on every directory descriptor
that appears during a negative/tamper probe.

- [x] **Step 4: Implement the minimal filesystem projection**

Use fresh user, mount, PID, IPC, and UTS namespaces; map the controller owner to
provider-visible uid/gid `0:0`; disable nested user namespaces; set a fixed
non-host hostname; start a new process group and terminal session
(`bwrap --new-session` or an equivalent `setsid` contract); and require
`--as-pid-1`, `--die-with-parent`, no-new-privileges behavior, zero effective/
permitted/inheritable/ambient/bounding capabilities at provider exec, the
Task 1B rootless group/object-authority proof, fresh empty session keyring plus
key-syscall denial,
isolated tmpfs `/tmp`, invocation-private tmpfs `/run` with synthetic `HOME`
below it, a new `/proc`, and minimal `/dev`. Mount the verified run-owned
sealed rootfs read-only at `/`; never mount the host root.
Create/pin the selected crash-durable containment slot before launch intent,
place Bubblewrap and its setup/provider descendants in that exact slot, keep
the shim behind the release gate through durable launch commit, and use the
same slot for normal, timeout, cancellation, and resume teardown/empty proof.
Create only the
directory ancestors required for:

- the candidate mounted at its host absolute path;
- the read-only provider environment;
- the synthetic isolated home; and
- the active result scratch overlay.

Mount the pinned candidate descriptor read/write, mask candidate
`.orchestrate`, and overlay only the
invocation-private active-result parent. Preserve the candidate absolute path
as `cwd`. Pass argv directly; do not invoke a shell. Resolve the executable,
shebang/interpreter, and effective `PATH` only against manifest-backed rootfs
paths.

- [x] **Step 5: Require the denial evidence**

```bash
pytest -q tests/test_provider_isolation_backend.py -k "projection or sentinel or symlink"
```

Expected:

- candidate read/write and active result write succeed;
- every known external read fails;
- candidate `.orchestrate` is empty except for active scratch ancestry;
- prior raw bundle read fails;
- symlink escapes fail; and
- pre-opened forbidden file/directory descriptors are absent or unreadable;
- final FD inventory contains only the declared transport set, every
  setup-source/backend descriptor is closed, and no observed directory
  descriptor permits `openat("..")` escape;
- every accessible `/proc/<pid>/fd` is inventoried; PID 1 is the provider, no
  Bubblewrap supervisor is namespace-visible, and `pidfd_getfd`, ptrace,
  `/proc/1/mem`, cwd/root, environ, and cmdline probes reveal no setup FD,
  unrelated ambient value, or host control path;
- terminal injection cannot reach the controller session; and
- joint host-relative and inner observations report the exact bound
  supplementary-group multiset, one-row maps, `setgroups: deny`,
  primary/overflow-only normalized counts, mapped uid/gid `0:0`,
  `NoNewPrivs: 1`, and zero `CapEff`, `CapPrm`, `CapInh`, `CapAmb`, and
  `CapBnd`; key syscalls and nested user-namespace creation fail, and hostname
  is the fixed isolated value; and
- mount-plan audit finds no broad host grant and only the verified sealed
  rootfs as the `/` source.

The process-disclosure invariant is absence of setup or foreign authority, not
blanket denial of self-observation. `pidfd_getfd` may duplicate only PID 1's
already-inventoried normalized stdio descriptors, and a valid-address
`/proc/1/mem` probe may read only its known provider-owned marker. Any
additional process, descriptor, value, path, or mismatched marker still fails
the gate.

If any denial cannot be achieved while the packaged provider runs, stop at
`I0_BLOCKED` and revise the design. Do not add a special-case assertion or host
mount.

- [x] **Step 6: Add fail-closed lifecycle cases**

Write RED tests, then implement:

- Bubblewrap missing;
- initial PATH/user-owned same-version fake and fixed-path
  owner/mode/xattr/ancestor trust failure;
- Bubblewrap replaced at the same path before launch, including a same-version
  replacement;
- Bubblewrap mutated in place with same inode/size before launch;
- Bubblewrap bytes/version unchanged while its host ELF loader, transitive
  library, loader cache, or startup configuration changes;
- user namespace unavailable;
- crash-durable containment unavailable, identity changed, membership escaped,
  release replayed, or kill/empty proof unavailable;
- provider environment digest mismatch;
- invalid environment/candidate admission, grant overlap, and root alias;
- registered local TCP/abstract-UNIX sentinel—including accept-and-close
  without a response—or cloud-metadata response, while unregistered listeners
  remain a recorded deployment assumption;
- child timeout;
- SIGKILL namespace destruction and descendant cleanup with provider as PID 1; and
- unsupported `fresh_only` session resume.

Run:

```bash
pytest -q \
  tests/test_provider_isolation_candidate.py \
  tests/test_provider_isolation_runtime_authority.py \
  tests/test_provider_isolation_network_preflight.py \
  tests/test_provider_isolation_backend_identity_negatives.py \
  tests/test_provider_isolation_backend.py
git diff --check -- \
  orchestrator/providers/isolation.py \
  orchestrator/providers/isolation_candidate.py \
  orchestrator/providers/isolation_runtime_authority.py \
  orchestrator/providers/isolation_network_preflight.py \
  orchestrator/providers/schemas/provider-isolation-network-inventory-v1.schema.json \
  orchestrator/providers/isolation_environment.py \
  orchestrator/providers/isolation_backend.py \
  orchestrator/providers/isolation_bubblewrap.py \
  orchestrator/providers/provider_launch_shim.py \
  tests/fixtures/provider_isolation/probe_provider.py \
  tests/test_provider_isolation_candidate.py \
  tests/test_provider_isolation_runtime_authority.py \
  tests/test_provider_isolation_network_preflight.py \
  tests/test_provider_isolation_schema_resources.py \
  tests/test_provider_isolation_backend.py \
  tests/test_provider_isolation_backend_identity_negatives.py \
  tests/test_provider_launch_shim.py
```

Expected: PASS with the fixture marker absent in every pre-launch failure.

- [x] **Step 7: Independent reviews and commit**

Specification review checks the projection against every design invariant.
Quality/security review inspects quoting, path resolution, mount order,
symlinks, process groups, timeout cleanup, and absence of broad mounts.

```bash
git add \
  orchestrator/providers/isolation.py \
  orchestrator/providers/isolation_candidate.py \
  orchestrator/providers/isolation_runtime_authority.py \
  orchestrator/providers/isolation_network_preflight.py \
  orchestrator/providers/schemas/provider-isolation-network-inventory-v1.schema.json \
  orchestrator/providers/isolation_environment.py \
  orchestrator/providers/isolation_backend.py \
  orchestrator/providers/isolation_bubblewrap.py \
  orchestrator/providers/provider_launch_shim.py \
  tests/fixtures/provider_isolation/probe_provider.py \
  tests/test_provider_isolation_candidate.py \
  tests/test_provider_isolation_runtime_authority.py \
  tests/test_provider_isolation_network_preflight.py \
  tests/test_provider_isolation_schema_resources.py \
  tests/test_provider_isolation_backend.py \
  tests/test_provider_isolation_backend_identity_negatives.py \
  tests/test_provider_launch_shim.py \
  docs/reports/provider-isolation-backend-feasibility/README.md \
  docs/superpowers/plans/2026-07-23-provider-phase-information-isolation.md \
  docs/superpowers/plans/2026-07-23-orc-vs-one-shot-experiment.md \
  docs/capability_status_matrix.md \
  docs/design/README.md
git commit -m "feat(providers): add fail-closed bubblewrap backend"
```

## Task 3: Implement The Phase-Private Result Broker

**Files:**

- Create: `orchestrator/providers/isolation_bundle_broker.py`
- Create:
  `orchestrator/providers/schemas/provider-isolation-bundle-transfer-v1.schema.json`
- Create: `tests/test_provider_isolation_bundle_broker.py`
- Modify: `orchestrator/providers/isolation.py`
- Modify: `orchestrator/providers/isolation_backend.py`
- Modify: `orchestrator/providers/isolation_environment.py`
- Modify: `orchestrator/providers/isolation_runtime_authority.py`
- Modify: `orchestrator/providers/isolation_bubblewrap.py`
- Modify: `orchestrator/providers/provider_launch_shim.py`
- Modify: `tests/test_provider_isolation_backend.py`
- Modify: `tests/test_provider_launch_shim.py`
- Modify: `tests/test_provider_isolation_runtime_authority.py`
- Modify: `tests/test_provider_isolation_schema_resources.py`
- Modify: `tests/fixtures/provider_isolation/probe_provider.py`
- Modify: `docs/capability_status_matrix.md`
- Modify: `specs/io.md`
- Modify: `specs/state.md`

- [x] **Step 1: Add and collect broker tests**

Cover:

- valid regular JSON file publication;
- missing scratch bundle leaves host target absent;
- empty file is copied and left for existing contract validation;
- directory, FIFO, device, and symlink rejection, with an `O_PATH` type pin
  proving no readable device open or blocking FIFO open occurs;
- escaping symlink rejection;
- exact `result_bundle.max_bytes` behavior at `limit - 1`, `limit`, and
  `limit + 1`, with oversize classified
  `provider_isolation_bundle_oversized`;
- exact non-boolean positive `result_bundle_max_bytes` carriage on the
  workflow-provider request and launch plan, with missing, zero, boolean, and
  over-limit values rejected before scratch allocation;
- exact carriage through the established
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` environment contract, with the accidental
  unsuffixed spelling absent;
- descriptor-stable type/size/copy behavior under symlink exchange, FIFO
  replacement, append/truncate mutation, and parent-path replacement;
- atomic same-filesystem publication with file fsync, rename, and destination
  directory fsync;
- sibling scratch files discarded;
- a closed canonical `provider_isolation_bundle_transfer.v1` journal whose
  deterministic scope/ordinal path and staged/target/archive identities use the
  shared serializer and packaged schema;
- recursive unknown-field rejection, canonical ASCII/Unicode/path-order
  vectors, changed journal bytes, path escape/symlink, identity mismatch, and
  illegal state transitions;
- an existing staged/target/archive file rejected unless the exact journal
  lifecycle and digest explain it;
- a fresh scratch root per attempt; and
- no prior host bundle mounted into a later plan;
- a bounded bundle from an exit eligible for typed validation is published and
  retained even when later typed validation fails;
- retryable nonzero/timeout/cancelled attempts record bounded metadata/digest
  without publishing the canonical target; and
- an invalid exit-zero result is journaled, a fake caller-acknowledgement
  interface permits its canonical target to rotate atomically to deterministic
  provider-masked evidence, and a later attempt can publish a valid result
  without target collision; Task 4 replaces that fake with real attestation;
- crash/recovery at staged-file fsync, `prepared`, canonical rename,
  `published`, caller validation/acknowledgement, `rotation_pending`, archive
  rename, and `rotated`, including `prepared` with exact staged-only versus
  canonical-only recovery; and
- both/neither staged/canonical location, unknown target/archive, wrong digest,
  and impossible state/location combinations fail closed without unlink or
  overwrite; and
- symlink/mount ancestry or a product-visible symlink/hardlink alias for any
  staged/canonical/archive authority fails before transfer.

```bash
pytest --collect-only -q tests/test_provider_isolation_bundle_broker.py
pytest --collect-only -q tests/test_provider_isolation_runtime_authority.py
pytest --collect-only -q tests/test_provider_isolation_schema_resources.py
```

- [x] **RED: Run before implementing the broker**

```bash
pytest -q \
  tests/test_provider_isolation_bundle_broker.py \
  tests/test_provider_isolation_runtime_authority.py \
  tests/test_provider_isolation_schema_resources.py
```

Expected: FAIL because broker behavior and the packaged transfer schema are
absent.

- [x] **Step 2: Implement the minimum broker**

On Linux, hold the scratch-parent directory descriptor and pin the exact active
basename with `openat(O_PATH|O_NOFOLLOW|O_CLOEXEC)`. Classify errno/type with
`fstat` before any readable open, so a FIFO cannot block and a device driver is
never invoked at the rejection boundary. Only for a proven regular file, open
that exact pinned inode `O_RDONLY|O_NONBLOCK|O_CLOEXEC` through the trusted
controller `/proc/self/fd` view and require identity, type, and mount ID to
match the pin before and after bounded reads. Never reopen the untrusted
basename; FIFO, device, and swap tests have explicit bounded completion. There
is no pathname fallback.
Write and fsync a deterministic same-filesystem staged file. Atomically persist
and fsync the closed transfer journal with its scope/ordinal, staged/target
identities, and digest before renaming the staged file to the canonical target;
fsync the destination directory, revalidate the exact target, atomically
advance/fsync the journal, and reconcile the resulting durable state before
returning success. Construct publication requests only from the exact
revalidated post-quiescence authority so request fields cannot be
cross-composed between attempts. Production capture must likewise derive the
active basename and byte limit from that authority and bind its source,
classification, digest, and size into the request; raw captures,
caller-selected larger limits, changed captures, and captures from another
attempt are not publishable. Persist and revalidate one combined
request/capture-source binding so two independently valid objects from
different attempts cannot be substituted together.
If the required descriptor or fsync operations are unavailable, fail closed.
Clean scratch only after bounded evidence fields are captured and the caller's
acknowledgement interface confirms that the evidence and any publication are
durably accounted for. Atomically quarantine each twice-proved entry under a
private no-replace name and revalidate the moved entry against its held
descriptor before removing it; a replacement at the final pathname boundary
must survive in quarantine and fail closed. Task 3 tests that interface with a
fake; it does not create or finalize an attestation.

Every prelaunch and readiness check retains full runtime-tree revalidation.
Only after workflow-provider quiescence may the invocation authority use a
broker-specific revalidation that keeps the exact scratch directory
descriptor/path/mount identity pinned while treating its provider-created
contents as opaque for descriptor-first broker classification. Controller
attempts and non-scratch runtime descendants never use that exception.

The broker transfers bytes only. It must not parse typed results or duplicate
the existing output-contract validator. It exposes explicit monotonic
`prepared`, `published`, `validated`, `rotation_pending`, and `rotated`
transitions plus a reconciliation API. Task 4 invokes the existing validator,
records `valid`/`invalid`, and finalizes attestation; Task 5 binds this
reconciliation before public resume can launch.

- [x] **Step 3: Connect broker paths to the mount plan**

The provider-visible bundle path keeps its logical current value. The
Bubblewrap plan overlays invocation scratch at the bundle parent while host
state keeps the allocated runtime target. Prove that two bundle names sharing
one host parent still receive different scratch views and cannot enumerate one
another.

- [x] **Step 4: Specify IO/state behavior**

Document active bundle brokerage, missing-bundle authority, the fixed
success/failure retention matrix, invalid-result archive lifecycle, complete
crash/recovery matrix, retry target behavior, exact policy size bound, and the
fact that the provider-visible path is a namespace mapping rather than a new
workflow value. V1 has no retention policy knob.

- [x] **GREEN: Verify broker and backend**

```bash
pytest -q \
  tests/test_provider_isolation_runtime_authority.py \
  tests/test_provider_isolation_bundle_broker.py \
  tests/test_provider_isolation_backend.py \
  tests/test_provider_launch_shim.py \
  tests/test_provider_isolation_schema_resources.py
git diff --check -- \
  orchestrator/providers/isolation.py \
  orchestrator/providers/isolation_backend.py \
  orchestrator/providers/isolation_environment.py \
  orchestrator/providers/isolation_runtime_authority.py \
  orchestrator/providers/isolation_bubblewrap.py \
  orchestrator/providers/isolation_bundle_broker.py \
  orchestrator/providers/provider_launch_shim.py \
  orchestrator/providers/schemas/provider-isolation-bundle-transfer-v1.schema.json \
  tests/test_provider_isolation_bundle_broker.py \
  tests/test_provider_isolation_backend.py \
  tests/test_provider_launch_shim.py \
  tests/test_provider_isolation_runtime_authority.py \
  tests/test_provider_isolation_schema_resources.py \
  tests/fixtures/provider_isolation/probe_provider.py \
  docs/capability_status_matrix.md \
  specs/io.md \
  specs/state.md
```

Expected: PASS.

- [x] **Step 5: Independent reviews and commit**

```bash
git add \
  orchestrator/providers/isolation.py \
  orchestrator/providers/isolation_backend.py \
  orchestrator/providers/isolation_environment.py \
  orchestrator/providers/isolation_runtime_authority.py \
  orchestrator/providers/isolation_bubblewrap.py \
  orchestrator/providers/isolation_bundle_broker.py \
  orchestrator/providers/provider_launch_shim.py \
  orchestrator/providers/schemas/provider-isolation-bundle-transfer-v1.schema.json \
  tests/test_provider_isolation_bundle_broker.py \
  tests/test_provider_isolation_backend.py \
  tests/test_provider_launch_shim.py \
  tests/test_provider_isolation_runtime_authority.py \
  tests/test_provider_isolation_schema_resources.py \
  tests/fixtures/provider_isolation/probe_provider.py \
  docs/capability_status_matrix.md \
  specs/io.md \
  specs/state.md
git commit -m "feat(providers): broker isolated phase results"
```

## Task 3A: Complete Typed Carriage And Its Implicit-Default Slice

This task closes the independent scalar-carriage G0 failure. It absorbs only
Track C1 carriage plus the necessary Track C6 implicit-default renderer
selection for existing `provider-result :inputs` from the governing
[private runtime state and consumer value-flow design](../../design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md):
existing `provider-result :inputs` values are rendered at the provider prompt
consumer seam without adding syntax. It does not implement Tracks C2–C5, the
remaining C6 authoring ergonomics, or make rendered bytes semantic authority.

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/effects.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_flow.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`
- Modify: `orchestrator/workflow_lisp/stdlib_contracts.py`
- Modify: `orchestrator/workflow_lisp/typed_prompt_inputs.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/view_renderer.py`
- Modify: `tests/test_prompt_contract_injection.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_examples.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_typed_prompt_inputs.py`
- Modify: `tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py`
- Modify: `tests/test_workflow_semantic_ir.py`
- Modify: `tests/test_workflow_view_renderer.py`
- Modify: affected characterization goldens and procedure identity baselines
- Modify:
  `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
- Modify: `docs/design/README.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `specs/providers.md`
- Modify: `specs/state.md`

- [x] **Step 1: Characterize the documented/runtime mismatch**

Before changing code, recover the minimal two-phase source from the
content-addressed G0 evidence and reduce it to one prior record containing a
unique scalar plus relpath. Record that the drafting guide currently promises
consumer-seam rendering while the lowered phase-two step and provider record
drop the scalar. Confirm the existing renderer kernel and evidence owner; do
not create a second rendering registry.

- [x] **Step 2: Add and collect RED carriage tests**

Require policy-independent consumer composition plus unrestricted execution:

- lowering carries every declared scalar and relpath binding into
  `typed_prompt_inputs` with source-map and renderer identity, including inputs
  without census/profile row metadata;
- implicit selection resolves one deterministic default from the existing
  typed renderer registry and fails on missing or ambiguous selection;
- phase two observes both unique typed values through its composed prompt;
- composed-prompt evidence records binding/type/renderer/value/rendered-byte
  digests without recording raw bundle authority;
- no materialized bridge or producer raw-bundle read is needed;
- missing state value, unknown renderer, shape mismatch, or a lowered
  binding absent from composed-prompt evidence fails before provider launch;
- composition returns validated structured evidence to the prompt owner for
  every invocation while preserving the legacy schema-`2.1` audit/persistence
  contract; and
- nested calls and ordinary root providers use the same consumer owner.

Required-isolation carriage is deliberately deferred to Task 4's launcher
integration and Task 7's public G0 test; Task 3A must not pull those later
runtime/CLI seams forward.

Assert value carriage and structured evidence, not literal prompt phrasing.

```bash
pytest --collect-only -q \
  tests/test_workflow_lisp_typed_prompt_inputs.py \
  tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py
pytest -q tests/test_workflow_lisp_lowering.py -k typed_prompt_input
pytest -q \
  tests/test_workflow_lisp_typed_prompt_inputs.py \
  tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py
```

Expected: collection passes and the reduced prior-scalar case fails for the
same reason recorded by G0.

- [x] **Step 3: Implement the minimum accepted C1 delta**

Use the existing canonical typed-prompt renderer and prompt composer. Correct
the current owner in `lowering/phase_scope.py` so absence of optional
census/profile metadata selects the reviewed type default instead of returning
an empty list; do not bypass that gate in `effects.py`. Require a one-to-one
match between lowered bindings, resolved typed values, rendered blocks, and
evidence rows before invocation preparation. Keep typed state as authority;
rendered bytes are an ephemeral provider input.

Partition no-profile inputs before resolving their runtime sources. Ordinary
calls carry supported bindings with contiguous order while unsupported
bindings remain unavailable without a checked route. Both active-phase owners
atomically retain their whole-input materialization fallback when any binding
is unsupported. If WCC lifting leaves a phase-derived call without that
fallback, reject an incomplete renderer set before provider launch.

Do not add a durable attempt ledger or change the schema-`2.1` publication
grammar in this task. Task 4 owns per-attempt schema-`2.2` combined
composed-prompt publication for isolated runs.

- [x] **Step 4: Correct status and authoring guidance**

First describe the pre-fix guide/runtime mismatch. Only after the focused and
end-to-end evidence passes:

- mark narrow C1 plus this C6 implicit-default slice implemented in the
  governing umbrella and design index;
- add an implemented/partial capability-matrix row that leaves C2–C5 and
  remaining C6 ergonomics future;
- make the drafting guide match the verified scalar/record/relpath behavior;
- define the provider prompt carriage, one-to-one evidence, and composed-prompt
  state contract in `specs/providers.md` and `specs/state.md`; and
- keep the predecessor consumer-rendering document routed as detailed history,
  not current authority.

- [x] **GREEN: Verify Track C1 and commit**

```bash
pytest -q tests/test_workflow_lisp_lowering.py -k typed_prompt_input
pytest -q \
  tests/test_workflow_lisp_typed_prompt_inputs.py \
  tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py
git diff --check -- \
  orchestrator/workflow_lisp/lowering/effects.py \
  orchestrator/workflow_lisp/lowering/phase_flow.py \
  orchestrator/workflow_lisp/lowering/phase_scope.py \
  orchestrator/workflow_lisp/stdlib_contracts.py \
  orchestrator/workflow_lisp/typed_prompt_inputs.py \
  orchestrator/workflow/executor.py \
  orchestrator/workflow/view_renderer.py \
  tests/test_prompt_contract_injection.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_examples.py \
  tests/test_workflow_lisp_loop_recur.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_typed_prompt_inputs.py \
  tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py \
  tests/test_workflow_semantic_ir.py \
  tests/test_workflow_view_renderer.py \
  docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md \
  docs/design/README.md \
  docs/lisp_workflow_drafting_guide.md \
  docs/capability_status_matrix.md \
  specs/providers.md \
  specs/state.md
```

Specification review checks Track C1 scope and value authority. Quality review
checks one renderer owner, fail-closed evidence matching, and the exact G0
scalar regression.

```bash
git add \
  orchestrator/workflow_lisp/lowering/effects.py \
  orchestrator/workflow_lisp/lowering/phase_flow.py \
  orchestrator/workflow_lisp/lowering/phase_scope.py \
  orchestrator/workflow_lisp/stdlib_contracts.py \
  orchestrator/workflow_lisp/typed_prompt_inputs.py \
  orchestrator/workflow/executor.py \
  orchestrator/workflow/view_renderer.py \
  tests/test_prompt_contract_injection.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_examples.py \
  tests/test_workflow_lisp_loop_recur.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_typed_prompt_inputs.py \
  tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py \
  tests/test_workflow_semantic_ir.py \
  tests/test_workflow_view_renderer.py \
  docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md \
  docs/design/README.md \
  docs/lisp_workflow_drafting_guide.md \
  docs/capability_status_matrix.md \
  specs/providers.md \
  specs/state.md
git commit -m "feat(workflow-lisp): render typed provider inputs"
```

## Task 4: Integrate Isolation Into Ordinary Provider Execution

**Files:**

- Create:
  `orchestrator/providers/schemas/provider-isolation-attestation-v1.schema.json`
- Create:
  `orchestrator/providers/schemas/provider-isolation-lifecycle-prefix-v1.schema.json`
- Create: `orchestrator/providers/isolation_attestation.py`
- Create: `tests/test_provider_isolation_attestation.py`
- Create: `tests/test_provider_isolation_execution.py`
- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/providers/types.py`
- Modify: `orchestrator/providers/isolation.py`
- Modify: `orchestrator/providers/isolation_backend.py`
- Modify: `orchestrator/providers/isolation_bundle_broker.py`
- Modify: `orchestrator/providers/isolation_network_preflight.py`
- Modify: `orchestrator/providers/isolation_runtime_authority.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/calls.py`
- Modify: `orchestrator/workflow/provider_attempts.py`
- Modify: `orchestrator/workflow/prompt_dependency_evidence.py`
- Modify: `orchestrator/workflow/call_frame_state.py`
- Modify: `orchestrator/state.py`
- Modify: `tests/test_provider_execution.py`
- Modify: `tests/test_provider_isolation_bundle_broker.py`
- Modify: `tests/test_provider_isolation_network_preflight.py`
- Modify: `tests/test_provider_attempt_allocation.py`
- Modify: `tests/test_prompt_dependency_evidence.py`
- Modify: `tests/test_provider_isolation_schema_resources.py`
- Modify: `tests/test_subworkflow_calls.py`
- Modify: `specs/providers.md`
- Modify: `specs/security.md`
- Modify: `specs/state.md`

- [ ] **Step 1: Characterize every current subprocess path**

Before writing tests, enumerate all `subprocess.Popen`/`subprocess.run` paths in
`ProviderExecutor`, including streaming, non-streaming, managed, session, retry,
timeout, and summary-provider variants. Record which paths can execute an
ordinary provider attempt.

Also trace `WorkflowExecutor` construction from public run/resume, nested call
frames, loop bodies, provider-backed summaries/live notes, managed wrapping,
and adjudicated providers. Record the existing
`provider_attempt_allocations`/`ProviderAttemptScope` authority and current
prompt-evidence publication event shape.

This step is inventory/design only. Do not introduce a launch seam or change
runtime code before the RED tests in Step 2.

- [ ] **Step 2: Add and collect execution tests**

Require:

- no-policy invocation uses the existing unrestricted launcher unchanged;
- required policy calls `prepare` then the isolated launcher exactly once;
- required isolation receives the same complete typed scalar/relpath rendering
  and evidence proven policy-independently in Task 3A;
- backend/policy failure creates no provider marker;
- no isolated path invokes ordinary provider `Popen`;
- stdin and argv prompt modes are preserved;
- stdout/stderr and provider session metadata parsing are preserved;
- bundle brokerage precedes existing typed validation;
- an eligible exit publishes and journals bytes; validator invocation is
  deterministic/idempotent across crash, while the `validated` journal outcome
  is published durably exactly once with bundle/contract/value digests;
- for `valid`, the aggregate-root owner atomically persists the normalized
  typed value, owning step/call-frame result, applicable public/private
  artifact lineage, and matching `result_terminal` in one state transaction;
  any required lexical checkpoint/index is then emitted and revalidated from
  that authoritative value before attestation and closure;
- for `invalid`, no typed-value handoff or checkpoint is fabricated; only the
  invalid result terminal may precede attestation/rotation/closure;
- an invalid outcome is attested and must complete deterministic
  provider-masked rotation before the retry owner launches a new attempt;
- a direct service request with caller-owned identity and
  `result_channel: "none"` skips broker/validator work yet emits the same closed
  attestation through its supplied external lifecycle sink, with broker fields
  forbidden and `not_applicable` recorded; crash recovery is driven by that
  sink rather than public workflow resume;
- request and attestation subject are the same closed tagged union:
  `workflow_provider` requires aggregate-root
  scope/ordinal/provider-template identity, a typed-bundle channel, and no
  external sink, while `controller_attempt` requires caller kind
  (`direct_arm`/`certified_check`), attempt ID, command/adapter identity,
  `none`, and an external sink and forbids workflow fields; reject every
  cross-combination before allocation/scratch/launch, and external sinks never
  allocate or publish into `provider_attempt_allocations`;
- an already allocated attempt that fails pre-launch emits a matching
  failure-code attestation without claiming a process or broker outcome;
- only ordinary fresh providers with a compiler/runtime-owned structured-result
  allocation are admitted; no-bundle, authored product-path bundle, managed,
  adjudicated/evaluator, provider-summary, and live-note surfaces fail at
  preflight and runtime dispatch with
  `provider_isolation_surface_unsupported`;
- a compiled prerequisite required-isolation workflow containing any command
  step anywhere in the complete reachable entry-workflow closure—including
  nested/imported calls and selected or unselected loop/branch bodies—fails
  before any provider/command launch with
  `provider_isolation_surface_unsupported`; service-level tests separately
  prove the controller-owned check identity, zero-credential,
  `result_channel: "none"`, and denial-attestation contract that a later pinned
  built-in experiment adapter must adopt, while no-policy command behavior is
  unchanged;
- authored provider `env` fails before launch rather than being dropped;
- the isolated launch request preserves declared-secret/global-secret
  provenance separately from the unrestricted merged environment;
- each attempt receives only the intersection of its declared secrets and
  policy credentials, with missing or out-of-policy names failing prelaunch;
- authored env uses `provider_isolation_surface_unsupported`, while a missing
  or out-of-policy declared credential uses
  `provider_isolation_grant_invalid`;
- policy-listed but step-undeclared credentials, ambient controller variables,
  unrelated secrets, host `HOME`/cache/PATH, `PYTHONPATH`, virtual/conda,
  Git/SSH, loader/interpreter/bootstrap variables, and step overrides are
  absent;
- fixed runtime `HOME`, `TMP*`, `XDG_*`, locale/time, PATH, and bundle values
  point only into synthetic or manifest-backed locations;
- registered denied Internet/abstract-UNIX endpoints—including
  accept-and-close without a response—and cloud metadata fail before launch,
  while the bounded listener inventory digest and explicit
  remaining-reachability deployment assumption reach attestation;
- retries allocate distinct attempts/scratch using the existing root-owned
  `provider_attempt_allocations`, including providers with no prompt
  dependencies;
- loop and nested-call providers delegate the same allocation to the aggregate
  root; crash/reload advances from durable state and never enumerates paths;
- one `(ProviderAttemptScope, ordinal)` keys one combined composed-prompt
  publication and one isolation attestation without duplicate ordinals;
- timeout/cancellation prove quiescence before returning; and
- `fresh_only` rejects session resume before launch.

The owning RED matrix is concrete and must collect under these exact nodes:

| Node | Required parametrized cases and assertions |
| --- | --- |
| `tests/test_provider_attempt_allocation.py::test_schema22_isolated_attempt_lifecycle_is_closed_and_monotonic` | Every valid schema-`2.2` branch, schema-`2.1` unchanged, whole-sequence validation followed by greatest-durable-event selection, mutually exclusive prefix predicates, exact replay idempotence, conflicting duplicate/reordered/cross-scope/wrong-ordinal rejection, and concurrent `N+1` allocation blocked until `N` is `attempt_closed` |
| `tests/test_provider_isolation_execution.py::test_isolated_attempt_crash_prefixes_never_relaunch` | Crash after `allocated`, composed-prompt evidence, `launch_intent`, `launch_committed`, `execution_terminal`, and `quiescence_terminal`; specifically crash after durable `prelaunch_failed` before quiescence and after durable `launch_failed` before quiescence (with every admitted commit form), preserving the terminal and appending only `no_process_created` or exact-slot `namespace_empty`; provider marker and execution-terminal count are at most one |
| `tests/test_provider_isolation_execution.py::test_isolated_attempt_noneligible_outcomes_close_without_transfer_journal` | Typed `workflow_provider` prelaunch failure, launch failure, nonzero exit, timeout, cancellation, and controller crash prove variant-correct quiescence, record `not_eligible`, finalize attestation, clean scratch, and close without a transfer journal; `none` is rejected for this subject |
| `tests/test_provider_isolation_execution.py::test_controller_attempt_sink_recovers_none_channel_without_workflow_state` | The separate caller-owned sink crash matrix selects its greatest durable event, records `not_applicable`, attests and closes without a bundle journal, workflow ordinal/state, or public `resume`; reject typed channel, workflow scope/ordinal/provider template, and any `provider_attempt_allocations` entry |
| `tests/test_provider_isolation_execution.py::test_isolated_attempt_typed_result_branches_close_exactly_once` | Missing, broker-rejected, published-valid, and published-invalid bundles; missing/rejected close invalid without a journal, published branches bind the exact subordinate journal, and invalid rotation plus scratch cleanup precede closure and any retry |
| `tests/test_provider_isolation_execution.py::test_validated_typed_result_commits_workflow_value_before_attempt_closure` | Crash after canonical publication, validation invocation, `validated` journal fsync, atomic typed-state/result-terminal handoff, required checkpoint record/index fsync, attestation, and closure; validation invocation may replay idempotently, but durable validation/result/state publication is exact-once, a valid terminal never exists without the value/lineage handoff, and closure never precedes the required checkpoint |
| `tests/test_provider_isolation_attestation.py::test_lifecycle_prefix_digest_is_canonical_bounded_and_non_self_referential` | Exact ASCII/Unicode golden bytes/digests for workflow aggregate-root/scope/ordinal and controller caller-attempt/command-or-adapter/external-sink headers followed by ordered `allocated` through `result_terminal` events; reject identity/event/reorder/extra/missing, cross-subject/scope/ordinal, and before/after-result prefix boundaries; prove the digest is unchanged by attestation preparation/publication, rotation, cleanup, and closure |
| `tests/test_provider_isolation_attestation.py::test_isolated_attempt_attestation_crash_matrix` | Crash before preparation, after `attestation_prepared` but before writing, after staged fsync, after atomic rename, after isolation-attestation evidence publication, and after `attempt_closed`; neither/staged-only/final-only recovery succeeds exactly as specified, while both paths, changed bytes, duplicate reference, or lifecycle mismatch fail closed |

```bash
pytest --collect-only -q tests/test_provider_isolation_execution.py
pytest --collect-only -q tests/test_provider_isolation_attestation.py
pytest -q tests/test_provider_isolation_schema_resources.py
```

- [ ] **RED: Run integration tests before changing the executor**

```bash
pytest -q tests/test_provider_isolation_execution.py
pytest -q \
  tests/test_provider_isolation_attestation.py \
  tests/test_provider_isolation_schema_resources.py
```

Expected: FAIL because `ProviderExecutor` has no isolation launch seam and the
attestation module/packaged schema do not exist.

- [ ] **Step 3: Add the narrow launch seam**

Pass an optional validated isolation runtime context into `ProviderExecutor`.
Build one internal provider process request after existing provider-template
and parameter rendering. Carry one closed subject union plus typed-input
evidence, declared secret names, and authored-env provenance as typed fields
rather than inferring any from paths or an already merged environment. The
workflow variant contains its coupled scope/ordinal and semantic typed-result
allocation; the controller variant contains its coupled caller identity,
`none`, and external sink. Route:

- no policy to the current launcher; and
- required policy to the selected backend.

Do not reimplement prompt composition, provider parameter binding, streaming
decoding, session parsing, retry decisions, or typed output validation. Require
the existing validator to be deterministic/idempotent for the same immutable
bundle and contract; exactly-once applies to its durable `validated`
publication, not to invocation count. Invoke the broker's
transition/reconciliation API around it: publication precedes validation,
`validated` journal persistence precedes the atomic authoritative
workflow-value/result-terminal handoff, any required lexical checkpoint/index
is then emitted from that value, and only then may attestation and closure
proceed. An invalid attested result is rotated and its scratch cleaned before
`attempt_closed` permits retry allocation/launch.

Generalize the existing root-owned provider-attempt allocator to every isolated
`workflow_provider` attempt only. Under schema `2.2`, extend that owner—without
adding a competing attempt journal—with the exact monotonic lifecycle:
`allocated`, optional `composed_prompt` evidence, optional `launch_intent`,
optional `launch_committed`, exactly one `execution_terminal`, exactly one
`quiescence_terminal`, exactly one `result_terminal`, exactly one
`attestation_prepared`, exactly one isolation-attestation evidence
publication, and exactly one `attempt_closed`. Preserve schema-`2.1` legacy
validation. Allocate before prompt composition, scratch creation, or process
launch. Required isolation enables the existing durable root-state write
barrier even when the compiled bundle has no prompt-dependency contract.

Each transition is root-serialized/fsynced; exact replay is idempotent and a
conflicting replay fails closed. `launch_intent` records the immutable plan,
result-channel, launch token, and crash-durable containment slot and is the
permanent no-relaunch boundary. `launch_committed` records the exact gated
process identity; only a caller that freshly appends it receives the one-use
provider-release permit. The root workflow `result_terminal` owns typed
not-eligible, missing, rejected, and published-valid/invalid outcomes; the
separate controller sink alone owns `none/not_applicable`. A subordinate
bundle-transfer journal exists only for the published workflow typed branch and
repeats the exact scope/ordinal. `attestation_prepared` is fsynced with
paths/digest before either file is written. `attempt_closed` follows finalized
attestation, scratch cleanup, and any invalid-result rotation; no later ordinal
may allocate or launch before closure.

For workflow lifecycle recovery, validate the complete sequence, select its
greatest durable event, and apply only that event's legal successor. Earlier
absence predicates never override a durable later event.
`prelaunch_failed` without quiescence remains unchanged and gains only
`no_process_created`; `launch_failed` without quiescence remains unchanged,
reconciles its exact intent/containment slot, and gains only
`namespace_empty`. A later event missing a required predecessor is invalid
state rather than an earlier-prefix recovery case.

Do not represent `none` inside the workflow lifecycle. Build one closed request
union: `workflow_provider` requires a typed bundle and root
scope/ordinal/provider-template identity; `controller_attempt` requires
`none`, caller attempt/command-or-adapter identity, and an external lifecycle
sink and forbids workflow identity. Implement its recovery against that sink
as a separate service matrix; neither public `resume` nor
`provider_attempt_allocations` may carry it.

For `published(valid)`, use one aggregate-root state transaction to persist the
normalized typed value, owning step/call-frame result, applicable
public/private artifact lineage, and matching result terminal. Bind the
contract, bundle, value, destination-state, and checkpoint requirement in the
handoff. Emit/revalidate a required deterministic lexical checkpoint/index
from the committed value before attestation; record `not_required` otherwise.
A valid terminal without that state handoff, or closure before the required
checkpoint, fails closed.

Generalize the existing owner in
`orchestrator/workflow/prompt_dependency_evidence.py` for schema `2.2` rather
than creating a parallel prompt ledger. Its per-ordinal closed record contains
dependency rows when present, the validated typed-input rows returned by Task
3A, renderer/value/rendered-byte identities, and final prompt digest. It
contains no raw prompt or credential. Test no-dependency providers,
dependency-plus-typed providers, retries, nested calls, crash/reload, and
duplicate/wrong-ordinal publication.

- [ ] **Step 4: Emit per-attempt attestation**

Persist workflow-provider `provider_isolation_attestation.v1` through the
aggregate root run/state authority. Publish controller-attempt attestations only
through the caller-supplied immutable sink; do not allocate a provider ordinal
or write them into workflow state. Package a closed recursive schema and use
the Task 1 canonical isolation JSON byte owner; do not add another serializer.
Include policy/environment/backend identities, admitted candidate/rootfs
checks, safe mount destinations/access modes, typed-input non-content
identities, granted credential names/presence booleans, effective capability
classification, process quiescence, and the same closed
subject/result/recovery union used by the request. The workflow typed-bundle
variant carries the closed `result_terminal` disposition: `not_eligible`,
`missing`, `rejected`, or `published(valid|invalid)`.
Not-eligible/missing/rejected variants forbid a fabricated transfer journal;
published requires the exact subordinate journal identity/reference, and valid
also requires the atomic workflow-value handoff identity plus required
checkpoint disposition. The controller `none` variant requires the external
sink, forbids broker/handoff/workflow fields, and records `not_applicable`. An
allocated attempt that fails before launch records its stable failure code and
forbids fabricated process/broker success.
Also include the closed denied
endpoint-set digest, bounded listener-inventory digest/counts, probe statuses,
and explicit unlisted-reachability trust assumption. Redact credentials,
listener names/addresses not needed for a safe match code, and external
forbidden source paths where the record could leak them.

Derive canonical bytes in memory, append/fsync `attestation_prepared` before
creating its deterministic staged/final paths, then write/fsync, atomically
publish/fsync, and append the closed state reference
`{schema_version, path, sha256}` against the unified attempt ordinal for
`workflow_provider`. Before deriving those bytes, build the closed
`provider_isolation_lifecycle_prefix.v1` array through `result_terminal` from
the applicable aggregate-root or external-sink authority, serialize it with
Task 1's canonical byte owner, and record its lowercase SHA-256 as
`lifecycle_prefix_digest`. Package its closed schema beside the attestation
schema. Recompute it during validation/recovery; reject any header identity,
event, order, membership, or terminal-boundary mismatch, while ignoring only
the explicitly excluded later attestation/rotation/cleanup/closure state.
Finish any required checkpoint, exact scratch cleanup, and invalid-result
rotation before appending `attempt_closed`; test the complete separate recovery
matrix of the supplied external authority/sink for `controller_attempt`. Test
every subject/result/recovery cross-combination,
unknown nested fields, changed bytes, path escape/symlink,
digest/invocation mismatch, duplicate evidence kind, secret-shaped fields,
typed-bundle/none conditional-field violations, allocated pre-launch failure,
every crash point in the matrix above, and reload validation. Invalid evidence
uses `provider_isolation_attestation_invalid`.

- [ ] **GREEN: Verify all provider execution paths**

```bash
pytest -q \
  tests/test_provider_isolation_execution.py \
  tests/test_provider_execution.py \
  tests/test_managed_provider_execution.py \
  tests/test_managed_provider_runtime.py \
  tests/test_provider_attempt_allocation.py \
  tests/test_prompt_dependency_evidence.py \
  tests/test_provider_isolation_bundle_broker.py \
  tests/test_provider_isolation_network_preflight.py \
  tests/test_provider_isolation_attestation.py \
  tests/test_provider_isolation_schema_resources.py \
  tests/test_subworkflow_calls.py
```

Expected: PASS.

- [ ] **Step 5: Independent reviews and commit**

Specification review checks that isolation is below workflow semantics and
selected on every ordinary provider path. Quality review checks that no
streaming/session/timeout regression or unrestricted fallback was introduced.

```bash
git add \
  orchestrator/providers/isolation_attestation.py \
  orchestrator/providers/schemas/provider-isolation-attestation-v1.schema.json \
  orchestrator/providers/schemas/provider-isolation-lifecycle-prefix-v1.schema.json \
  orchestrator/providers/executor.py \
  orchestrator/providers/types.py \
  orchestrator/providers/isolation.py \
  orchestrator/providers/isolation_backend.py \
  orchestrator/providers/isolation_bundle_broker.py \
  orchestrator/providers/isolation_network_preflight.py \
  orchestrator/providers/isolation_runtime_authority.py \
  orchestrator/workflow/executor.py \
  orchestrator/workflow/calls.py \
  orchestrator/workflow/provider_attempts.py \
  orchestrator/workflow/prompt_dependency_evidence.py \
  orchestrator/workflow/call_frame_state.py \
  orchestrator/state.py \
  tests/test_provider_isolation_attestation.py \
  tests/test_provider_isolation_schema_resources.py \
  tests/test_provider_isolation_execution.py \
  tests/test_provider_execution.py \
  tests/test_provider_isolation_bundle_broker.py \
  tests/test_provider_isolation_network_preflight.py \
  tests/test_provider_attempt_allocation.py \
  tests/test_prompt_dependency_evidence.py \
  tests/test_subworkflow_calls.py \
  specs/providers.md \
  specs/security.md \
  specs/state.md
git commit -m "feat(providers): route required isolation through executor"
```

## Task 5: Bind The Policy Through Public Run, State, And Resume

**Files:**

- Create: `tests/test_provider_isolation_cli.py`
- Create:
  `docs/reports/provider-isolation-state-downgrade-characterization/README.md`
- Create:
  `orchestrator/cli/commands/provider_isolation_network_inventory.py`
- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/providers/isolation_bundle_broker.py`
- Modify: `orchestrator/providers/isolation_runtime_authority.py`
- Modify: `orchestrator/contracts/output_contract.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/workflow/state_layout.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/build_artifacts.py`
- Modify: `orchestrator/workflow_lisp/lexical_checkpoints.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/calls.py`
- Modify: `orchestrator/workflow/call_frame_state.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_state_manager.py`
- Create: `tests/test_provider_isolation_runtime_writers.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_lexical_checkpoints.py`
- Modify: `tests/test_subworkflow_calls.py`
- Modify: `tests/test_workflow_state_compatibility.py`
- Modify: `tests/test_workflow_state_projection.py`
- Modify: `specs/index.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `specs/cli.md`
- Modify: `specs/state.md`

- [ ] **Step 1: Add public CLI/state contract tests**

Before changing the state loader, build/install the pinned pre-feature runtime
at experiment baseline commit
`7437409d4619843d1c660a1a5e1905e4afd1020d` from a disposable archive/clone
outside the shared checkout (not a worktree). Run that actual wheel against a
minimal otherwise-valid schema-`2.2` isolated state through its ordinary resume
load path. Record commit, wheel SHA-256, Python version, exact command, exit
status, and rejection output in
`docs/reports/provider-isolation-state-downgrade-characterization/README.md`.
A new-runtime matrix test alone is not evidence about an old binary; if the
pinned runtime accepts or reaches execution, stop and revise the downgrade
barrier before implementation.

Cover:

- absolute `--provider-isolation-policy-file` accepted by `run`;
- policy and private inventory are pinned/read as single-link `0600` real
  regular files in dedicated controller-owned
  `0700` real directories with safe ancestors; group/world access, xattrs,
  symlinks/swaps, and unexplained aliases fail before frontend build;
- those controller-input authority directories are symmetrically disjoint from
  candidate, mutable environment, snapshot, workflow/source/extern,
  runtime/state, scratch, evaluator, peer, and parent authorities, and no
  rootfs manifest path may expose them; test both containment directions and
  symlink aliases;
- `provider-isolation-network-inventory --output <absolute-path>` atomically
  writes but does not accept the closed private report and prints its canonical
  digest;
- relative, missing, invalid, or digest-mismatched files rejected before
  provider launch;
- policy review path/digest/decision and freshly recomputed inventory must match
  exactly on run/resume; inventory change requires a new explicit review;
- policy file remains external and is not copied to candidate;
- policy parsing and candidate/runtime-authority admission occur before
  `build_frontend_bundle` or any `.orchestrate`/checkpoint/result write;
- public preflight rejects a command hidden in a nested/imported call, loop, or
  unselected branch before any provider/command marker;
- a fresh run creates a pinned real `.orchestrate` only when absent, while
  resume reopens the exact recorded candidate/runtime identities; a symlink,
  mount/ancestry swap, cross-boundary alias, or mismatched identity fails before
  any outside build marker;
- isolated frontend build artifacts, `StateManager` workspace sidecars,
  `StateLayout` allocations, lexical checkpoints, result materialization, and
  typed-result reads all use the same
  descriptor-relative authority; no direct `Path.mkdir`/`write_*` owner remains
  for isolated `.orchestrate` descendants;
- the canonical whole-policy digest and exact
  `provider_environment.digest` persisted once per run as distinct, explicitly
  named identities, with a persistence round-trip test proving both values
  survive independently alongside backend identity;
- backend identity binds the opened Bubblewrap bytes/metadata, version, and
  complete host loader/library/cache/startup-config closure plus probe
  contract/results; same-path/same-version executable or closure-member
  replacement is rejected on launch and resume;
- the sealed snapshot lives only at
  `<run-root>/provider_environment_snapshots/<digest>/rootfs`; resume reuses
  and revalidates it, rejects missing/tampered/aliased placement, and never
  recopies from a later-mutated source;
- closed per-attempt attestation references persisted under root authority and
  verified by path plus digest;
- state load/resume recomputes
  `provider_isolation_lifecycle_prefix.v1` from the exact persisted subject
  header and ordered `allocated` through `result_terminal` prefix, rejects
  identity/event/extra/missing/boundary mismatch, and proves later
  attestation/rotation/cleanup/closure events do not change the digest;
- resume validates and reconciles every root-owned schema-`2.2` per-ordinal
  `workflow_provider` lifecycle in every scope before launch; it validates the
  whole sequence, selects the greatest durable event, applies only its legal
  successor, and invokes bundle-transfer reconciliation only for a typed
  lifecycle branch that authorizes subordinate bundle evidence;
- public state/load/resume rejects `workflow_provider` with `none` or an
  external sink and rejects `controller_attempt`, caller-sink, or
  command/adapter identity in `provider_attempt_allocations`; controller
  attempts recover only through Task 4's separate external-sink service tests;
- a published-but-unsettled target is validated/finalized without relaunch when
  valid only after the atomic authoritative workflow-value/result-terminal
  transaction and required checkpoint persistence, while an invalid
  target/attestation is idempotently attested, rotated, cleaned, and closed
  before a new attempt;
- public crash after durable `prelaunch_failed` but before quiescence preserves
  that terminal and appends only `no_process_created`; crash after durable
  `launch_failed` but before quiescence preserves that terminal, reconciles the
  exact intent/containment identity, and appends only `namespace_empty`;
- public invalid-exit-zero -> resume -> valid and crash-at-each
  allocate/intent/commit/terminal/quiescence/publication/validation-journal/
  typed-state-and-result-terminal/checkpoint/attestation/rotate/cleanup/close
  boundary cases preserve exact scope/ordinal/digest identity, never launch one
  ordinal twice, never publish a semantic validation or workflow value twice,
  and never expose the invalid archive to a provider;
- `WorkflowExecutor` receives the immutable isolation context built by public
  `run`/`resume` and passes it through root, loop, retry, and nested call-frame
  providers without reading workflow inputs;
- an isolated fresh run uses state schema `2.2`, while unrestricted fresh runs
  remain schema `2.1`;
- embedded `call_frames[*].state` inherits its aggregate root schema version;
  isolated call frames are `2.2`, contain no duplicate root-only
  policy/allocator/attestation authority, and delegate through the root;
- root/frame schema mismatch, embedded root-only isolation fields, or a frame
  attempt whose `ResumeScopePath` contradicts the parent chain is rejected on
  load/resume;
- an older schema-`2.1` runtime rejects ordinary resume of isolated schema
  `2.2` before execution;
- `resume` reuses the recorded absolute path only after digest verification;
- explicit identical resume path accepted;
- changing a non-environment policy field while preserving
  `provider_environment.digest` rejects resume as a whole-policy identity
  mismatch;
- tampering with or substituting the recorded sealed-rootfs manifest while
  preserving unrelated policy fields rejects resume as a
  provider-environment identity mismatch;
- swapping or cross-filling the whole-policy and provider-environment digest
  fields is rejected; golden, persistence, and resume tests assert the two
  identities independently even when both mismatches use
  `provider_isolation_resume_identity_mismatch`;
- missing, changed, or different policy rejected;
- an unrestricted historical run cannot be silently resumed as isolated;
- an isolated run cannot be silently resumed unrestricted; and
- schema `2.2` with missing/partial isolation identity and schema `2.1` with an
  isolation identity are rejected rather than normalized;
- `resume --force-restart` rejects schema-`2.2` isolated runs, and a new
  schema-`2.1` run created by an older binary cannot satisfy the original run
  ID/attestation identity; and
- missing/changed policy, backend/environment identity, or recorded snapshot
  uses `provider_isolation_resume_identity_mismatch`;
- schema/root/call-frame isolation-shape contradictions use
  `provider_isolation_state_invalid`;
- invalid attestation references use
  `provider_isolation_attestation_invalid`; and
- all other CLI errors use their named stable diagnostic classes.

The public persistence/resume RED matrix is owned by these exact nodes:

| Node | Required cases |
| --- | --- |
| `tests/test_provider_isolation_cli.py::test_public_resume_reconciles_every_isolated_attempt_lifecycle_prefix_before_launch` | Table-drive every prefix after allocation, intent, commit, execution terminal, quiescence terminal, each result branch, attestation preparation/publication, invalid rotation, cleanup, and closure across root, retry, loop, and nested-call scopes. Include `[allocated, execution_terminal(prelaunch_failed)]`, `[allocated, intent, execution_terminal(launch_failed)]`, and every admitted committed launch-failed form; greatest-event selection preserves each terminal and appends only its legal quiescence proof, with no provider marker |
| `tests/test_provider_isolation_cli.py::test_public_resume_never_relaunches_unsettled_intent_or_commit` | Intent/commit prefixes preserve exact scope/ordinal, return no release permit after reload, terminate only the exact crash-durable containment slot, and fail with `provider_isolation_process_not_quiescent` when empty proof is unavailable |
| `tests/test_provider_isolation_cli.py::test_public_resume_closes_typed_noneligible_attempts_without_bundle_journal` | Typed workflow-provider prelaunch/launch failure, nonzero exit, timeout, cancellation, and controller crash attest and close without a transfer journal; no public `none` case exists |
| `tests/test_provider_isolation_cli.py::test_public_resume_reconciles_typed_result_and_attestation_crash_matrix` | Crash after validation invocation, `validated` journal fsync, atomic typed-state/result-terminal handoff, and required checkpoint/index fsync; invocation replay is idempotent, durable publications are exact-once, valid closure requires state plus checkpoint, missing/rejected invalid outcomes close without a journal, published invalid rotates/cleans/closes then allocates `N+1`, and prepared attestation recovery covers neither/staged-only/final-only/both/wrong digest |
| `tests/test_provider_isolation_cli.py::test_public_resume_revalidates_lifecycle_prefix_digest` | Recompute the Task 4 golden prefix from persisted workflow root/scope/ordinal plus ordered events; reject subject/scope/ordinal/event tamper, cross-subject substitution, reordered/extra/missing events, and prefix ending before or after `result_terminal`; crash/recovery after attestation preparation/publication, rotation, cleanup, and closure preserves the same digest |
| `tests/test_provider_isolation_cli.py::test_public_resume_rejects_impossible_isolated_attempt_lifecycle` | Open predecessor plus later ordinal, later event missing a required predecessor, conflicting replay, wrong attempt identity, workflow-provider plus `none`/external sink, controller-attempt data in `provider_attempt_allocations`, valid terminal without its typed-state handoff, unexpected scratch/attestation/checkpoint files, subordinate journal mismatch, and finalized-attestation mismatch all fail before launch |
| `tests/test_provider_isolation_cli.py::test_public_resume_persists_policy_and_environment_digests_independently` | Golden round trip, non-environment policy-only change, environment-manifest-only change, and swapped/cross-filled digest fields |

- [ ] **Step 2: Verify collection and RED**

```bash
pytest --collect-only -q tests/test_provider_isolation_cli.py
pytest --collect-only -q tests/test_provider_isolation_runtime_writers.py
pytest -q tests/test_provider_isolation_cli.py
pytest -q tests/test_provider_isolation_runtime_writers.py
```

Expected: collection passes, execution fails because the CLI option/state
binding does not exist.

- [ ] **Step 3: Implement run plumbing**

Add the controller-only inventory command in `orchestrator/cli/main.py`; it
records the full private report without claiming acceptance. Parse the absolute
policy path in `orchestrator/cli/main.py`, load the reviewed inventory
path/digest/decision, pin the policy/controller-input files no-follow, validate
their dedicated authority modes/non-overlap, recompute the inventory, and
validate all of them before frontend build. For an isolated fresh run,
admit/pin the candidate and
securely create the runtime authority before any frontend/build/checkpoint or
result-projection writer runs; pass that authority into `build_frontend_bundle`,
`StateManager`, and later executor owners. Then canonicalize/preflight the
complete compiled surface before constructing the executor. Persist the path
and immutable identities in initial run state. Pass one immutable isolation
runtime context through
`orchestrator/cli/commands/run.py` into `WorkflowExecutor`; do the same from
resume only after identity validation. Public preflight inspects the compiled
surface and rejects managed/adjudicated/summary/live-note/no-semantic-bundle
uses and every command step across all reachable nested/imported
call/loop/branch bodies—including an unselected branch—before any
provider/command marker.

`orchestrator/workflow/calls.py` is the nested `WorkflowExecutor` construction
seam. It must pass the same immutable context into child executors; a child may
not reload policy or manufacture a weaker context.

Initial schema-`2.2` state persists the whole canonical policy digest,
`provider_environment.digest`, and backend identity as separately named
fields. Neither digest is derived from the other during serialization or
reload.

Do not put policy bytes, provider environment paths, or attestation records in
workflow inputs, context, prompt dependencies, or product files.

- [ ] **Step 4: Implement resume compatibility**

Teach `resume` to reconstruct the recorded option, reopen the exact pinned
candidate/runtime authority without path following, and sweep every allocated
root-owned workflow-provider lifecycle in every scope before any provider
launch. Validate each complete sequence, derive its greatest durable event, and
dispatch exactly one legal successor; never choose an earlier absence case
when `execution_terminal` or a later event exists. Preserve durable
`prelaunch_failed`/`launch_failed` terminals and append only their
variant-correct quiescence proof. Invoke deterministic bundle-transfer
reconciliation only for a typed branch whose events authorize that subordinate
journal. For valid output, require the atomic authoritative
workflow-value/result-terminal transaction and any required checkpoint/index
before attestation, cleanup, and `attempt_closed`. Before accepting or
recovering attestation bytes, reconstruct the closed
`provider_isolation_lifecycle_prefix.v1` header plus ordered events through
`result_terminal`, canonicalize with the shared owner, and require its digest
to match; excluded later attestation/rotation/cleanup/closure events must leave
it unchanged. Unknown files, open-predecessor/later-ordinal combinations,
missing predecessors, impossible lifecycle/journal/target/archive/checkpoint
states, prefix identity/event/boundary mismatch, or a valid terminal without
its typed state fail closed. Use an explicit schema matrix:

- schema `2.1` is accepted only for unrestricted runs;
- schema `2.2` is accepted only with a complete, valid isolation identity; and
- every other combination is rejected.

Within schema `2.2`, public run/state/resume accepts only
`workflow_provider` plus a typed channel and root scope/ordinal. Reject
`workflow_provider` plus `none`/external sink and all `controller_attempt`
fields in workflow state. The controller-owned external sink and its service
recovery entry point are Task 4 authority, not a public-resume branch.

Do not add isolation as an optional schema-`2.1` field. Older runtimes already
reject an unknown top-level schema on ordinary resume, so `2.2` is the
same-lineage fail-closed downgrade barrier. Their historical force-restart
route creates a new unrestricted run and is excluded by run-ID/attestation
evidence. The new runtime must continue to resume valid unrestricted `2.1` runs
without rewriting them. Reject `--force-restart` when the source state is
isolated schema `2.2`; the caller must start a separately named run through
`run` and cannot represent it as continuation evidence.

- [ ] **Step 5: Specify CLI/state behavior**

Document the new option, absolute-path rule, immutable resume identity,
pre-launch failures, attestation location, schema `2.1`/`2.2` matrix, older
runtime rejection, embedded call-frame inheritance/root-only fields, unified
provider-attempt publication events, greatest-durable-event resume precedence,
terminal-to-quiescence variant mapping, closed subject/result/recovery
authority union, atomic typed-value/result-terminal handoff and checkpoint
ordering, the canonical non-self-referential
`provider_isolation_lifecycle_prefix.v1` digest and recovery validation,
separate controller-sink recovery, and legacy no-policy compatibility.
Update `specs/index.md`, `specs/versioning.md`, and
`specs/acceptance/index.md` so the normative schema/acceptance footprint is
routed rather than mentioned only in leaf specs.

- [ ] **GREEN: Verify public CLI, state, and resume**

```bash
pytest -q \
  tests/test_provider_isolation_cli.py \
  tests/test_provider_isolation_runtime_writers.py \
  tests/test_resume_command.py \
  tests/test_state_manager.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_lexical_checkpoints.py \
  tests/test_subworkflow_calls.py \
  tests/test_workflow_state_compatibility.py \
  tests/test_workflow_state_projection.py \
  tests/test_workflow_lisp_cli.py
```

Expected: PASS.

- [ ] **Step 6: Independent reviews and commit**

```bash
git add \
  orchestrator/cli/main.py \
  orchestrator/cli/commands/provider_isolation_network_inventory.py \
  orchestrator/cli/commands/run.py \
  orchestrator/cli/commands/resume.py \
  orchestrator/providers/isolation_bundle_broker.py \
  orchestrator/providers/isolation_runtime_authority.py \
  orchestrator/contracts/output_contract.py \
  orchestrator/state.py \
  orchestrator/workflow/state_layout.py \
  orchestrator/workflow_lisp/build.py \
  orchestrator/workflow_lisp/build_artifacts.py \
  orchestrator/workflow_lisp/lexical_checkpoints.py \
  orchestrator/workflow/executor.py \
  orchestrator/workflow/calls.py \
  orchestrator/workflow/call_frame_state.py \
  tests/test_provider_isolation_cli.py \
  tests/test_provider_isolation_runtime_writers.py \
  tests/test_resume_command.py \
  tests/test_state_manager.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_lexical_checkpoints.py \
  tests/test_subworkflow_calls.py \
  tests/test_workflow_state_compatibility.py \
  tests/test_workflow_state_projection.py \
  docs/reports/provider-isolation-state-downgrade-characterization/README.md \
  specs/index.md \
  specs/versioning.md \
  specs/acceptance/index.md \
  specs/cli.md \
  specs/state.md
git commit -m "feat(cli): persist provider isolation identity"
```

## Task 6: Make Historical Retrieval Classification Computed And Truthful

This task does not need to produce `CAUSAL_ELIGIBLE`. The first Bubblewrap
profile is expected to preserve provider transport by sharing network access,
which is insufficient to prove remote-history denial.

**Files:**

- Modify: `orchestrator/providers/isolation.py`
- Modify: `orchestrator/providers/isolation_backend.py`
- Modify: `orchestrator/providers/isolation_bubblewrap.py`
- Modify: `orchestrator/providers/isolation_network_preflight.py`
- Modify: `tests/test_provider_isolation_policy.py`
- Modify: `tests/test_provider_isolation_backend.py`
- Modify: `tests/test_provider_isolation_execution.py`
- Modify: `tests/test_provider_isolation_network_preflight.py`
- Modify: `specs/providers.md`
- Modify: `specs/security.md`

- [ ] **Step 1: Write RED classification tests**

Require:

- shared network plus successful provider transport and no provider-tool
  attestation yields `OBSERVATIONAL_ONLY`;
- missing probes never count as denials;
- filesystem isolation status remains independent;
- successful closed denied-endpoint probes plus a reviewed remaining-listener
  trust assumption satisfy the local G0 prerequisite but do not count as any
  of the four remote-history denials;
- `OBSERVATIONAL_ONLY` never waives a registered
  local/cloud-metadata endpoint failure, including successful
  connect/accept-and-close without response;
- `eligibility_requirement: require_causal` fails prelaunch with
  `provider_isolation_capability_unavailable` when any required evidence is
  missing; and
- `CAUSAL_ELIGIBLE` requires all four v1 retrieval channels to be requested as
  `deny`, enforced, and probed while the fixed provider-transport `allow`
  succeeds; and
- any policy that attempts to allow a retrieval channel or deny provider
  transport is rejected by the v1 policy schema rather than classified
  vacuously.

Do not issue real remote Git/browser/source-search requests in unit tests.

- [ ] **Step 2: Implement capability evidence and classification**

Represent each capability with:

- requested policy;
- enforcement mechanism identity;
- probe status;
- observed result; and
- classification rationale code.

The Bubblewrap shared-network backend reports the retrieval denials as
unenforced unless a separately implemented provider/egress mechanism supplies
valid evidence. It must not infer denial from the absence of a tool invocation.

- [ ] **Step 3: Verify**

```bash
pytest -q \
  tests/test_provider_isolation_policy.py \
  tests/test_provider_isolation_backend.py \
  tests/test_provider_isolation_network_preflight.py \
  tests/test_provider_isolation_execution.py
```

Expected: PASS with the default first-release profile classified
`OBSERVATIONAL_ONLY`.

- [ ] **Step 4: Independent reviews and commit**

```bash
git add \
  orchestrator/providers/isolation.py \
  orchestrator/providers/isolation_backend.py \
  orchestrator/providers/isolation_bubblewrap.py \
  orchestrator/providers/isolation_network_preflight.py \
  tests/test_provider_isolation_policy.py \
  tests/test_provider_isolation_backend.py \
  tests/test_provider_isolation_network_preflight.py \
  tests/test_provider_isolation_execution.py \
  specs/providers.md \
  specs/security.md
git commit -m "feat(providers): attest retrieval capability separately"
```

## Task 7: Rerun The Original G0 Scenario Through The Public CLI

Do not copy the previously failing diagnostic module into the repository
unchanged. Recreate its behavior as a green integration test only after Tasks
1, 1A, 2, 3, 3A, 4, 5, and 6 pass.

**Files:**

- Create: `tests/fixtures/provider_isolation/public_cli_g0/`, containing
  `fixture_manifest.json`, the reviewed `.orc`, both prompt templates,
  provider-extern/command-boundary templates, and task-input templates
- Create: `tests/test_provider_phase_information_isolation_e2e.py`
- Create:
  `docs/reports/2026-07-23-experiment-control-plane-feasibility-rerun.md`
- Modify: `tests/fixtures/provider_isolation/probe_provider.py`
- Modify: `tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py`
- Modify: `tests/README.md`

- [ ] **Step 1: Recover and audit the external diagnostic fixture**

Use the durable content-addressed evidence location recorded in the G0
feasibility report:

```text
/home/ollie/.local/share/agent-orchestration/evidence/sha256-1847661aa2baa7ca372b12fcf97de7f9b5b18d05c2a2ad023d6d8b5691aa8027
```

Rebuild its deterministic tar stream and require SHA-256
`1847661aa2baa7ca372b12fcf97de7f9b5b18d05c2a2ad023d6d8b5691aa8027`
before reading the fixture. Then inventory every entry without following links.
The frozen tree contains 24 absolute symlinks into mutable historical `/tmp`
roots, including pytest `*current` links and two `control/bin/codex` links.
Record their text with `lstat`/`readlink`, but never resolve, copy through, or
execute them: the archive digest authenticates link text, not target bytes.
Recover behavior only from audited regular files inside the content-addressed
tree and recreate any needed launcher as a reviewed relative/in-tree fixture.
Port only behavior required by the durable governing design:

- external workflow/prompt/provider/command manifests;
- candidate-only task fixture;
- external controller/evaluator/peer roots;
- parent-checkout sentinel with guaranteed cleanup;
- two provider phases;
- declared typed value and relpath flow;
- prior-bundle/runtime enumeration;
- product pre/post manifests; and
- a public CLI invocation with external `--state-dir` and required isolation
  policy.

Materialize the audited behavior once under
`tests/fixtures/provider_isolation/public_cli_g0/`. Its closed fixture manifest
lists every checked-in template and digest. The integration test copies those
templates into fresh per-run candidate, control, controller-input, evaluator,
peer, parent, and external-state roots and fills only absolute paths and
digests generated for that run. No later task may reconstruct the fixture with
ad hoc shell commands or placeholder paths.

- [ ] **Step 2: Add and collect the public integration tests**

Add:

- successful two-phase run with all denial probes;
- backend-unavailable fail-closed run;
- registered loopback TCP and abstract-AF_UNIX denied-sentinel preflights that
  fail before provider launch, including accept-and-close without a response;
- changed policy on resume rejection;
- attestation proves production isolated launcher selection; and
- truthful `OBSERVATIONAL_ONLY` history classification.

The reusable self-verifying public gate is exactly
`tests/test_provider_phase_information_isolation_e2e.py::test_public_cli_isolates_each_provider_phase`.
That node validates the checked-in fixture manifest, materializes fresh roots,
invokes the production public CLI, and asserts inside the node every required
positive typed scalar/relpath/result-bundle behavior, forbidden
read/enumeration denial, product pre/post-manifest invariant, production
launcher selection, policy/environment/backend identity, per-attempt
attestation, and certified command-result/no-result-child semantic required by
Steps 3 and 4. A zero CLI exit or externally inspected smoke directory is not
sufficient.

```bash
pytest --collect-only -q \
  tests/test_provider_phase_information_isolation_e2e.py
```

- [ ] **RED: Run the end-to-end test before final wiring fixes**

```bash
pytest -q \
  tests/test_provider_phase_information_isolation_e2e.py::test_public_cli_isolates_each_provider_phase
```

Expected: if all preceding tasks (1, 1A, 2, 3, 3A, 4, 5, and 6) are correctly
integrated this may already pass. If it
fails, require the first real public-boundary mismatch and fix the owning
runtime path; do not weaken a denial assertion.

- [ ] **Step 3: Require every original G0 assertion**

The passing test must prove:

- provider `cwd` is exactly the candidate root;
- active task content arrives through the declared prompt dependency;
- typed prior value/path arrive in phase two;
- the unique prior scalar appears in the phase-two provider observation and
  its structured typed-input evidence, not merely in state;
- an ordinary product marker is written;
- no workflow/control manifest enters the candidate product;
- `.orchestrate` is excluded from the product manifest and masked from the
  provider;
- inactive prompt, evaluator, peer, parent, and controller reads fail;
- prior raw bundle, checkpoint, build, and state enumeration/read attempts
  fail;
- both typed bundles validate and checkpoint normally; and
- policy/environment/backend identities and attempt attestations are present.
- closed denied-endpoint/cloud-metadata probes pass, the bounded
  TCP/UDP/abstract-AF_UNIX listener inventory is attested, and the operator
  explicitly reviews/accepts the remaining-reachability deployment assumption.

The mutable environment package/source, candidate, and every
control/evaluator/peer/parent/state root must also pass symmetric host-path
admission. The snapshot must be exactly inside its dedicated run-state
subauthority, while all rootfs entries pass provider-visible manifest-path
denial. The test candidate remains under `/tmp/.../candidate` to exercise the
special admitted tmpfs mountpoint rule.

- [ ] **Step 4: Rerun command-result boundary regression**

Recover the behavior, not necessarily the temporary fixture implementation,
for:

- child exit 0 -> typed `PASS`;
- child nonzero -> typed `FAIL` while adapter exits 0;
- missing bundle;
- wrong schema version;
- frozen-manifest digest mismatch before child launch; and
- stdout-only JSON.

Run each product-executing child through the reusable
`result_channel: "none"` isolation launcher with a controller-owned
check-attempt identity, zero credentials, and matching attestation. Add an
adversarial product check that attempts every external
control/evaluator/peer/parent/state/prior-runtime sentinel (including through a
provider-authored symlink) and prove all reads fail while ordinary product test
execution works. After provider quiescence, the trusted harness must create the
fresh exact product extract through the same descriptor-safe candidate
admission/snapshot rules: reject special files, unsafe symlinks, mount-ID
crossings, external hardlinks, ancestry exchange, and source mutation before
launch. It may verify the frozen manifest and map isolated child exit to the
typed record; it must not execute product code ambiently. Use the existing
command-boundary contract owner/tests where possible. The prerequisite runtime
still rejects every in-workflow command and this service proof does not claim
arbitrary command isolation.

The exact public gate node named in Step 2 must invoke and assert these
certified-check cases as part of its self-verifying contract. Supporting
focused nodes may remain, but they do not replace that gate.

- [ ] **GREEN: Run focused public-boundary verification**

```bash
pytest -q \
  tests/test_provider_phase_information_isolation_e2e.py \
  tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py \
  tests/test_workflow_lisp_provider_call_policy_e2e.py \
  tests/test_provider_isolation_cli.py
```

Expected: PASS.

- [ ] **Step 5: Write the exact passing rerun record**

Only after the fresh public test passes, write
`docs/reports/2026-07-23-experiment-control-plane-feasibility-rerun.md` with:

- passing runtime commit and dirty-tree scope;
- exact public CLI invocation and test node IDs;
- policy, sealed-rootfs manifest, backend, and per-attempt attestation digests;
- denied-endpoint-set and listener-inventory digests, safe probe statuses, and
  explicit remaining-network-reachability trust assumption;
- explicit scalar and relpath consumer observations;
- every forbidden read/enumeration outcome;
- product pre/post manifests;
- command-boundary regression result;
- historical classification and limitations; and
- the shared-candidate declassification limitation; and
- independent review state.

This companion is the only passing G0 record. Do not rewrite the historical
report's `G0_BLOCKED` decision.

- [ ] **Step 6: Independent reviews and commit**

Specification review checks exact correspondence to all G0 requirements.
Quality/security review checks that the test uses public runtime wiring,
forbidden reads are real, sentinels are cleaned, and attestation prevents a
fixture-only pass.

```bash
git add \
  tests/fixtures/provider_isolation/public_cli_g0 \
  tests/test_provider_phase_information_isolation_e2e.py \
  tests/fixtures/provider_isolation/probe_provider.py \
  tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py \
  tests/README.md \
  docs/reports/2026-07-23-experiment-control-plane-feasibility-rerun.md
git commit -m "test(providers): prove phase information isolation end to end"
```

## Task 8: Reuse The Accepted Provider Rootfs In A Controlled Live Smoke

**Files:**

- Create: `docs/reports/provider-isolation-live-smoke/README.md`
- Create only reviewed, non-secret environment-lock/attestation artifacts under
  the report directory
- Modify implementation/tests only if the live smoke exposes a contract bug

- [ ] **Step 1: Revalidate the accepted sealed provider rootfs**

Reuse the exact sealed rootfs identity that passed both `I0E` and the
rootless `I0G` rebind; do not rebuild an untracked variant for the live smoke.
Revalidate it from its explicit lock outside the candidate and control roots.
Record:

- source lock digest;
- normalized environment manifest and digest;
- provider CLI/version identity;
- absence of editable installs and live-checkout `PYTHONPATH`/`.pth` entries;
- credential injection mechanism without credential values;
- Bubblewrap executable plus host loader/library/cache closure identity,
  version, and host capability preflight;
- closed denied-endpoint/cloud-metadata probe results plus the bounded
  TCP/UDP/abstract-AF_UNIX listener-inventory digest; and
- explicit successful-connect/accept-and-close sentinel coverage from the
  accepted backend evidence; and
- an explicit operator review of the unlisted local/remote reachability trust
  assumption.

Do not commit credentials, mutable caches, the environment itself, or raw
provider conversations. If packaging must change, return to Task 1A/1B,
create a new digest, rerun `I0E`, `I0G`, and `I0`, and review that identity
before continuing.

- [ ] **Step 2: Run the live smoke in tmux**

Use a minimal external two-phase workflow and the exact policy intended for
experiments. The provider must:

- read/edit only the candidate;
- write one typed result per phase;
- leave all forbidden sentinel probes denied;
- retain passing registered denied-endpoint probes without claiming general
  network isolation; and
- complete with matching attestations and a clean product manifest.

If the intended real provider requires a broad host mount, stop and revise the
provider environment packaging. Do not add the mount.

- [ ] **Step 3: Record bounded evidence**

Write exact command, runtime commit, policy/environment/backend digests,
provider version/model/effort, product pre/post manifests, attestation digests,
denied-endpoint/listener-inventory digests, remaining-reachability trust
assumption, exit status, and limitations. Redact secrets and provider content
not required to prove the boundary.

- [ ] **Step 4: Independent reviews and commit**

Specification review verifies the smoke uses the designed profile. Quality and
security review verify evidence integrity, redaction, environment provenance,
and the absence of a broad host grant.

```bash
git add docs/reports/provider-isolation-live-smoke
git commit -m "docs(providers): record isolated live-provider smoke"
```

## Task 9: Route Documentation And Close The Prerequisite

**Files:**

- Reuse without modification; must already be tracked by Task 7:
  `tests/fixtures/provider_isolation/public_cli_g0/`
- Reuse without modification; must already be tracked by Task 7:
  `tests/test_provider_phase_information_isolation_e2e.py`
- Modify: `docs/index.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/design/README.md`
- Modify:
  `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify:
  `docs/superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md`
- Modify:
  `docs/superpowers/specs/2026-07-23-orc-vs-one-shot-experiment-design.md`
- Modify:
  `docs/superpowers/plans/2026-07-23-orc-vs-one-shot-experiment.md`
- Modify:
  `docs/reports/2026-07-23-experiment-control-plane-feasibility.md`
- Modify:
  `docs/reports/2026-07-23-experiment-control-plane-feasibility-rerun.md`
- Modify: `specs/index.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `specs/providers.md`
- Modify: `specs/security.md`
- Modify: `specs/state.md`
- Modify: `specs/io.md`
- Modify: `specs/cli.md`

- [ ] **Step 1: Update routing and status consistently**

Only after fresh implementation evidence:

- mark the Linux required profile implemented;
- keep unrestricted profiles explicitly unrestricted;
- state other host backends are unsupported;
- record the live-smoke evidence path/digest;
- keep historical retrieval `OBSERVATIONAL_ONLY` unless a separate enforcing
  backend actually passed; and
- mark the original feasibility report's blocker as resolved by a later
  implementation, linking the exact passing companion report without rewriting
  its historical `G0_BLOCKED` result.

Update the original experiment plan before it resumes:

- Task 1 accepts G0 only from the exact passing companion report and
  attestation-backed public test;
- revise the master G0 table/invariants and external-control-plane scenario so
  G0 command evidence means legacy typed pass/fail/result semantics plus the
  separately exercised zero-credential no-result child launcher/attestation;
  it does not claim that the prerequisite public workflow admits command
  steps;
- Task 5 `DIRECT` provider execution must call the reusable isolation launcher
  with `result_channel: "none"` and a controller-owned arm-attempt identity;
- raw `ArmCommand` subprocess execution may still launch certified
  non-provider adapters, but cannot launch a provider or execute
  provider-authored product code;
- add DIRECT launcher parity/denial/attestation tests before Task 5 execution;
- revise the governing experiment design and plan so apparatus Task 4 adds one
  implementation-owned certified-check adapter/command-child seam pinned by
  exact code and boundary-schema digests; only that built-in identity may lift
  the prerequisite's blanket workflow-command rejection, while arbitrary
  command externs remain unsupported;
- require that adapter to create its disposable exact product extract with the
  candidate admission/descriptor-safe snapshot contract and launch every
  product-executing child through the same service with
  `result_channel: "none"`, zero credentials, a controller-owned check-attempt
  identity, and denial attestation; add provider-authored
  special-file/symlink/mount/mutation and sentinel confused-deputy tests before
  apparatus Tasks 7–8;
- add a named `G1C` certified-check-containment gate, required before master
  Tasks 7–8 or any product-executing check, which passes only after that pinned
  built-in adapter identity, disposable-product contract, no-result child
  launch, and attestation are implemented and reviewed;
- add a named `G4E` evaluator-containment design/gate before any scored task may
  import or execute provider-authored product code: the ambient hard evaluator
  may not import the target in-process, and frozen-copy immutability alone is
  not authority isolation; keep this outside the G0 claim and leave scored work
  stopped until that gate passes;
- add a named `G4R` reviewer/consumer provider-containment design/gate before
  master Tasks 10–11 or any scored soft-reviewer/F2 session; package filtering
  is not authority isolation, so those fresh sessions must adopt the reusable
  launcher with surface-specific projections/typed results or another reviewed
  boundary that proves peer/unblinding/control/transcript denials; and
- preserve the same sealed-rootfs, candidate admission, environment, process,
  and historical-classification contract for both arms.

Use the `consistency-quality-pass` skill for this routing update.

- [ ] **Step 2: Run narrow and integration verification**

```bash
pytest -q \
  tests/test_provider_isolation_policy.py \
  tests/test_provider_isolation_schema_resources.py \
  tests/test_provider_isolation_environment.py \
  tests/test_provider_isolation_candidate.py \
  tests/test_provider_isolation_backend.py \
  tests/test_provider_isolation_bundle_broker.py \
  tests/test_provider_isolation_attestation.py \
  tests/test_provider_isolation_execution.py \
  tests/test_provider_isolation_cli.py \
  tests/test_provider_phase_information_isolation_e2e.py \
  tests/test_provider_execution.py \
  tests/test_resume_command.py \
  tests/test_state_manager.py \
  tests/test_subworkflow_calls.py \
  tests/test_workflow_state_compatibility.py \
  tests/test_workflow_state_projection.py \
  tests/test_workflow_lisp_typed_prompt_inputs.py \
  tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py \
  tests/test_workflow_lisp_provider_call_policy_e2e.py
```

Expected: PASS.

- [ ] **Step 3: Rerun the exact self-verifying public-CLI gate**

Require the Task 7 fixture manifest and test module to be tracked before
running:

```bash
git ls-files --error-unmatch \
  tests/test_provider_phase_information_isolation_e2e.py \
  tests/fixtures/provider_isolation/public_cli_g0/fixture_manifest.json
pytest -q \
  tests/test_provider_phase_information_isolation_e2e.py::test_public_cli_isolates_each_provider_phase
```

Expected: PASS. This exact node rematerializes the public-CLI fixture and
self-verifies every denial, attestation, product, typed-result, and certified
command-result/no-result-child semantic owned by Task 7. Do not substitute a
hand-written shell invocation or placeholder paths.

- [ ] **Step 4: Run the broad suite in tmux**

```bash
pytest -q -n 16 --dist=worksteal
```

Expected: PASS. Investigate any failure; do not weaken verification to obtain a
green result.

- [ ] **Step 5: Run documentation and diff checks**

```bash
git diff --check
git status --short
```

Inspect the complete scoped diff and verify no raw credentials, mutable
environments, temporary failing G0 fixtures, or unrelated dirty paths are
staged.

- [ ] **Step 6: Obtain final independent reviews**

Specification review checks all design invariants, public CLI/resume behavior,
and truthful historical classification. Quality/security review checks
launcher completeness, namespace/mount safety, broker safety, process
quiescence, evidence quality, docs consistency, and test realism.

- [ ] **Step 7: Commit the status/docs update**

```bash
git add \
  docs/capability_status_matrix.md \
  docs/index.md \
  docs/design/README.md \
  docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md \
  docs/lisp_workflow_drafting_guide.md \
  docs/superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md \
  docs/superpowers/specs/2026-07-23-orc-vs-one-shot-experiment-design.md \
  docs/superpowers/plans/2026-07-23-orc-vs-one-shot-experiment.md \
  docs/reports/2026-07-23-experiment-control-plane-feasibility.md \
  docs/reports/2026-07-23-experiment-control-plane-feasibility-rerun.md \
  specs/index.md \
  specs/versioning.md \
  specs/acceptance/index.md \
  specs/providers.md \
  specs/security.md \
  specs/state.md \
  specs/io.md \
  specs/cli.md
git commit -m "docs(providers): close phase isolation prerequisite"
```

## Completion And Experiment Handoff

The prerequisite is complete only when:

- `I0E`, `I0G`, `I0`, `I1`, `I1C`, and `I2` through `I5` pass with fresh
  evidence;
- the required profile fails closed on backend/environment/policy mismatch;
- the original two-phase G0 public-CLI scenario passes without weakening any
  denial;
- the zero-credential controller-attempt certified-check child denies every G0
  sentinel/confused-deputy path and emits matching no-result attestation;
- the intended live provider runs from the sealed rootfs without broad
  host mounts;
- state and resume bind exact isolation identity;
- historical classification is evidence-backed and truthful;
- narrow, integration, smoke, and broad verification pass;
- both final reviews approve; and
- the reviewed changes are committed.

Then return to
[`.orc` Versus One-Shot Experiment Program Implementation Plan](2026-07-23-orc-vs-one-shot-experiment.md),
record Task 1/G0 as passed from the exact Task 7 companion report after Task
9's fresh revalidation, and only then begin Task 2. Task 7 is the authoritative
post-implementation Task-1 rerun; do not create a third gate record. Do not
reinterpret this plan's successful implementation as a retroactive pass of the
original `G0_BLOCKED` run.
