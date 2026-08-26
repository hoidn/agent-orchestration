# OMP-I1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `subagent-driven-development` task by task, `test-driven-development` for each
> behavior change, `systematic-debugging` for any unexpected failure, and
> `verification-before-completion` before claiming a task or the plan complete.
> Continue in the existing `omp-i1-prerequisites` worktree; do not create a
> nested worktree. Use one write-capable implementer at a time. Read-only scouts
> and reviewers may run in parallel.

**Goal:** Build and install the pinned OMP v17.3.4 single-file executable, add
four usable OMP provider templates, and ship a dependable prompt-to-Workflow
Lisp path with explicit session capture, deterministic typed scaffolds,
multiagent conf presets, primary-session import, and safe interactive
fork/resume.

**Architecture:** Reuse the existing provider template, provider-session 2.10,
Workflow Lisp lowering, runtime step, state 2.1, and scalar-artifact contracts.
Add one code-owned OMP binary pin, one thin launch adapter, one strict stdout
codec, closed conf/session parsers, and three prompt services. Target DSL 2.27
adds only `:session-artifact`; it synthesizes contracts the runtime already
understands. No new Executable IR node, runtime step kind, state family,
workflow retry model, or in-workflow resume form.

**Deliberate limits:** Linux `x86_64` with AVX2 and Landlock ABI 3 or newer only; OMP must already be installed on
`PATH` at the admitted digest. The `omp_conf` lane deliberately loads
repository context from its `--add-dir` workspace; `omp_no_tools` and internal
inference omit that root. Resume/import support only the linked primary journal.
These choices make additional platforms, auto-provisioning, per-call conf
selection, and child-session import harder. Add them only after a named consumer
requires them.

**Tech stack:** Python 3.11+, PyYAML 6.x safe loading, existing jsonschema and
Workflow Lisp frontend/WCC, Linux descriptor-relative filesystem APIs,
`renameat2(RENAME_NOREPLACE)`, OMP v17.3.4, Bun 1.3.14, Bazel 9.2.0 through
Bazelisk 1.29.0, `rules_rust` 0.71.3 nightly `2026-04-29`,
`hermetic_cc_toolchain` 4.2.0, pytest/pytest-xdist, deterministic fake OMP
children, and a small number of marked real-binary checks.

---

## Authority, Scope, And Ground Rules

Read before editing:

- `AGENTS.md` and `docs/index.md`;
- `docs/capability_status_matrix.md` and `docs/design/README.md`;
- `docs/plans/2026-08-14-omp-integration-design-and-roadmap.md`;
- `docs/plans/2026-08-14-omp-integration-proposal.md`;
- `specs/providers.md`, `specs/cli.md`, `specs/dsl.md`, `specs/versioning.md`,
  and `specs/state.md`;
- OMP source checkout `~/Documents/oh-my-pi` at tag `v17.3.4`, commit
  `ffd53ff92a6f575d499730475a73460dd7cc2eea`.

The revised design is feature authority until implementation closes. Existing
normative specs remain authoritative for already-implemented behavior. A
conflict is resolved in the design/plan before code is changed; do not make a
silent implementation exception.

Keep every new production module below 500 lines. Existing oversized modules
may receive only small dispatch/carrier changes; put new behavior in the OMP
or prompt modules named below. Reuse `StateManager`, `ProviderExecutor`, the
session transport factory, frontend lowering context, `WorkflowAssetResolver`,
and existing provider-session publication. Do not build a parallel framework.

No permanent test may assert literal prompt prose. Tests assert argv, bytes,
closed schemas, state transitions, artifacts, lineage, and observable provider
behavior.

## Execution Contract

For each task:

1. give one implementer that task's anticipated files and acceptance criteria;
2. add the smallest behavioral RED first and record its failure shape;
3. implement the minimum shared fix;
4. run the task's listed GREEN selectors and any additional check whose failure
   would falsify an affected contract;
5. run `pytest --collect-only` for every new or renamed test module;
6. inspect `git status --short` and `git diff --check`;
7. request a proportional review for a meaningful public, behavioral, or trust-
   boundary change; one reviewer may cover specification and maintainability,
   and add a security specialist only when a security boundary changed; and
8. commit the affected paths.

The file lists below are anticipated scope, not ownership declarations.
Necessary emergent work is admitted only with a concrete trigger, causal link
to the task, affected invariant or deliverable, and explicit closure condition.
It joins the same review and verification; amend the plan only if the public
design changes. A review or supplemental check blocks only when it demonstrates
a current requirement, affected contract, or sourced safety invariant is
violated. Preserve and disclose unrelated failures at their actual scope.

Run commands from the Orchestrator repository root unless a command explicitly
sets the OMP source checkout as its working directory. Preserve unrelated dirty
files. Do not stage the design/plan repeatedly with implementation commits;
commit the reviewed planning baseline before Task 1.
Use the `tmux` skill for both clean OMP builds, real provider/TTY checks, and
the final full pytest suite; preserve fresh command output as evidence.

### Hard stops

Stop and amend the design before continuing if implementation requires:

- a new public Core, Semantic, or Executable IR member;
- a new runtime step kind, provider-result envelope, or state family;
- implicit session persistence for ordinary OMP calls;
- authored binary paths, expected digests, lane selection, approval mode, or
  generic OMP flags;
- a provider retry or phased-delivery implementation for a session artifact;
- accepting unknown members in recognized OMP JSON events, or allowing X3's
  opaque unknown event types to affect lifecycle, settlement, identity, output,
  usage, callbacks, or metadata; unknown conf keys, session entries, link keys,
  or scaffold keys remain rejected;
- treating a digest as hostile-model authorship proof;
- persisting raw or child-authored OMP transport bytes outside the ordinary
  task output and explicit OMP session journal surfaces;
- profile-isolated direct API-key inheritance or any credential path other than
  the validated loopback auth-broker pair;
- weakening no-follow, no-replace, ownership, mode, or descriptor-inheritance
  checks; or
- bypassing a failed F1/F2/F4 gate to land any OMP provider.

Feature-local stops from the design remain binding: F3 blocks all
profile-isolated templates; a failing preset is removed rather than weakened;
F8 failure removes natural-language inference; bridge/import failure omits that
subcommand without changing provider/runtime contracts.

The Task 10 integration-remediation gate is mandatory before Task 11 resume
work may be accepted or committed as complete. Resume work started before this
plan revision may be preserved as work in progress, but it supplies no evidence
for Task 10 and must not bypass, weaken, or defer any remediation item. Task 12
remains the only OMP-I1 completion gate.

## Preflight

- [ ] Record the Orchestrator and OMP revisions and verify the implementation
  worktree is based on the frozen-ES hand-back:

  ```sh
  git status --short
  git log -1 --oneline
  git -C /home/ollie/Documents/oh-my-pi status --short
  git -C /home/ollie/Documents/oh-my-pi rev-parse HEAD
  git -C /home/ollie/Documents/oh-my-pi describe --tags --exact-match
  ```

  Expected OMP commit/tag:
  `ffd53ff92a6f575d499730475a73460dd7cc2eea`, `v17.3.4`.

- [ ] Re-run the focused clean baseline before changing code:

  ```sh
  pytest -q \
    tests/test_provider_session_transport.py \
    tests/test_provider_integration.py \
    tests/test_provider_execution.py \
    tests/test_provider_call_policy.py \
    tests/test_state_manager.py \
    tests/test_cli_run_ref_root.py \
    tests/test_cli_safety.py \
    tests/test_workflow_lisp_expressions.py
  ```

- [ ] Confirm the measured build-input hashes in the design. Any mismatch is a
  Task 1 blocker, not a pin update made by convenience:

  ```sh
  sha256sum \
    /home/ollie/Documents/oh-my-pi/bun.lock \
    /home/ollie/Documents/oh-my-pi/Cargo.lock \
    /home/ollie/Documents/oh-my-pi/Cargo.toml \
    /home/ollie/Documents/oh-my-pi/MODULE.bazel \
    /home/ollie/Documents/oh-my-pi/MODULE.bazel.lock \
    /home/ollie/Documents/oh-my-pi/.bazelversion \
    /home/ollie/.bun/bin/bun
  bun --version
  ```

  Expected: the design's measured values plus `Cargo.toml`
  `8ff17fda5daa014fefa536c347f3060d9fa159719665e31ac96d560566899bdb` (a
  crate_universe input recorded alongside `Cargo.lock`). Any mismatch is a
  Task 1 blocker, not a pin update made by convenience.

---

## Task 1: Reproduce, Install, And Pin The OMP Executable

**Purpose:** Close F4 before coding against an artifact that may not be
reproducible or executable in production.

> **Execution status:** F4 closed on the fifth recipe and was refreshed on the
> sixth after R10 expanded the audited source overlay. Two sequential clean
> canonical-root builds matched the declared/effective lock, pre-normalization
> overlay, native addon, version, size, and whole output. The current
> whitespace-normalized overlay applies to the identical patched source tree;
> no rebuild followed that transport-only normalization. The common executable
> SHA-256 is
> `df4c4d98b8a28c51651de79bc925449b6dcc3c57d2653b17aba7e5755f76dddb`;
> it is atomically installed and pinned, and the three required raw fixtures
> remain valid because the transport protocol did not change. Initial report:
> `.superpowers/sdd/2026-08-21-omp-i1-implementation-plan/task-1-report.md`;
> R10 refresh evidence is in the Task 10 report.

**Files:**

- Create: `orchestrator/providers/omp_pin.py`
- Create: `orchestrator/providers/omp_source_overlay.patch`
- Create: `tests/test_provider_omp_pin.py`
- Create captured fixtures under `tests/fixtures/omp/protocol/`
- Modify after the digest is known:
  `docs/plans/2026-08-14-omp-integration-design-and-roadmap.md`
- External output, not committed: `~/.local/bin/omp`

### Step 1.1: Pin the build launcher

- [x] Download Bazelisk v1.29.0 Linux amd64 to a temporary tools directory and
  verify SHA-256
  `5a408715e932c0250d28bd84555f12edbf70117de42f9181691c736eacc4a992`
  before executing it.
- [x] Verify Bun is exactly 1.3.14 and its executable hash is
  `9fd36f87e4b90b07632b987a2e4ec81ca15a62c81bf983190cea6d715be2ad74`.
- [x] Resolve and record canonical path, version, and SHA-256 for Bun, the
  Bazelisk launcher selected from `PATH`, the Bazel executable that exact
  launcher resolves from `.bazelversion`, and Git. Record `ldd --version`,
  `uname -m`, and the code-owned host native-target selection as trusted
  observations; require the latter to be `linux-x64-modern` on this AVX2 pin.
  The root `rust-toolchain.toml` and host `rustc`, `cargo`, `cc`, and `ld` are
  not selected by the mandated Bazel build and must not be recorded as its
  producing toolchain.

### Step 1.2: Build twice from clean source

- [x] Build sequentially at one recorded canonical absolute root
  `/home/ollie/.cache/omp-i1/canonical`: for each of the two acceptance builds,
  delete the entire checkout/HOME/XDG cache-config-data-state/temp tree,
  recreate it from the pinned commit with `git clone --no-local`, and detach
  at the pinned commit. The canonical path is an explicit admitted build input
  (embedded in the addon's `.rodata` string constants). Any successful
  reproducibility claim would be limited to this recorded root and positive
  environment, not arbitrary checkout paths. Each recreated clone MUST start at the declared
  source identities: `MODULE.bazel.lock` must hash
  `0060efc6e59203c4395a92b971859e6e51c2cef8a94fc8bf7443f9a003e9e2c9` before any
  build command (fail otherwise). Do not build from the mutable source
  checkout.
- [x] Construct each build environment from an empty mapping with fresh
  `HOME`, XDG cache/config/data/state roots, and `TMPDIR`; an exact `PATH`
  containing only the recorded tool directories; and only the locale,
  certificate, and fixed build variables the recipe needs. Reject inherited
  proxy/registry configuration, `OMP_NATIVE_BUILD_BACKEND`, `OMP_BAZEL_RC`,
  Bazelisk version/source/home overrides, `BUN_COMPILE_EXECUTABLE_PATH`,
  Bun/Node preload/options, dynamic-loader variables, compiler/linker flags or
  wrappers, Rust/Cargo overrides, and `CROSS_TARGET` before any build command.
- [x] In each clone, under that exact positive environment, run exactly:

  ```sh
  patch=/home/ollie/Documents/agent-orchestration/.worktrees/omp-i1-prerequisites/orchestrator/providers/omp_source_overlay.patch
  test "$(sha256sum "$patch" | cut -d' ' -f1)" = f128fb6b8565b3221b9819b6f55b6f7f58d46a1163236d1a4c12d79d54f9c245
  git apply --check "$patch"
  git apply "$patch"
  bun install --frozen-lockfile
  bun run build:native -- -- -- --jobs=1 --spawn_strategy=local
  bun -e "import { lstatSync, utimesSync } from \"node:fs\"; const p=\"packages/natives/native/pi_natives.linux-x64-modern.node\"; const bytes=Buffer.from(await Bun.file(p).arrayBuffer()); if (bytes.includes(Buffer.from(\"processwrapper-sandbox/\"))) throw new Error(\"native addon retains processwrapper-sandbox path\"); const s=lstatSync(p); if (!s.isFile() || s.isSymbolicLink()) throw new Error(\"native addon must be a regular non-symlink\"); utimesSync(p, 0, 0); const normalized=lstatSync(p, { bigint: true }); if (normalized.mtimeNs !== 0n) throw new Error(\"native addon mtime normalization failed\")"
  bun --cwd=packages/coding-agent run build
  ```

  The native build uses `--spawn_strategy=local` so compile-time
  `CARGO_MANIFEST_DIR`/`__FILE__` paths stay under the stable canonical execroot
  instead of a numbered `processwrapper-sandbox` directory. `--jobs=1` remains
  pinned to minimize execution-order variance. The following pinned-Bun command
  requires the copied addon to be a regular non-symlink, sets its atime/mtime to
  epoch 0, and verifies `mtimeNs == 0n` before Bun.Archive reads it.
  The audited overlay changes only `packages/natives/scripts/embed-native.ts`.
  It reuses the existing `packages/stats/scripts/generate-client-bundle.ts`
  tar-header normalizer to set each member mtime to zero and recompute the tar
  checksum before pinned Bun performs deterministic gzip compression. Require
  the patched script to hash
  `747221981bb2d9441e7a581871c73eb6ccb3f2f1eed063b80d45fe4043f347f1`;
  any additional clone diff or patch/script digest drift fails F4.

  The three standalone `--` tokens are verified on Bun 1.3.14: outer and inner
  `bun run` each consume one, leaving the launcher's literal `--` plus both
  Bazel flags for `scripts/bazel-natives.ts`. Record
  `bazel_jobs="1"`, `bazel_spawn_strategy="local"`, and
  `native_addon_mtime_ns=0` in the candidate pin and build observations.

  Bun 1.3.14 parses `--cwd <dir> run <script>` (space form) as a no-op that
  prints `bun run` help and exits 0; the equals form
  `bun --cwd=packages/coding-agent run build` is the pinned CLI syntax that
  executes the same intended script (verified minimal repro on Bun 1.3.14,
  and the form the OMP repo itself uses). Both clean builds run this exact
  corrected command.

  `OMP_NATIVE_BUILD_BACKEND`, `OMP_BAZEL_RC`, Bazelisk overrides,
  `CROSS_TARGET`, and `BUN_COMPILE_EXECUTABLE_PATH` must be absent; native
  compilation therefore stays on the recorded Bazelisk launcher path, and
  local `build-binary.ts` uses the verified Bun executable with
  `minifyIdentifiers:false`.
- [x] In each clone, invoke the exact verified Bazelisk launcher path used by
  `build:native`—not the resolved Bazel binary directly—to capture the
  configured action closure for `//:natives-linux-x64-modern`; require it to
  resolve the recorded Bazel path/digest again. Normalize and
  record the selected Rust and C/C++ toolchain labels plus SHA-256 for the
  actual compiler/linker executable artifacts referenced by Rust compile,
  C/C++ compile, and link actions. Require `rules_rust` 0.71.3 nightly
  `2026-04-29`, selected as
  `@@rules_rust++rust+rust_linux_x86_64__x86_64-unknown-linux-gnu__nightly_tools//:rust_toolchain`,
  and `hermetic_cc_toolchain` 4.2.0 selected as
  `@@hermetic_cc_toolchain++toolchains+zig_config//:x86_64-linux-gnu.2.17_cc`;
  a missing action, host-tool path, or different label is an F4 failure.
- [x] Require both clones' normalized closure records to be byte-identical and
  bind them to the measured `MODULE.bazel` and `MODULE.bazel.lock` digests.
  The module files' pinned component checksums are the source identities for
  the downloaded Bazel toolchains; do not substitute the unused root
  `rust-toolchain.toml`.
- [x] Re-hash `bun.lock`, `Cargo.lock`, `Cargo.toml`, `MODULE.bazel`,
  `MODULE.bazel.lock`, and `.bazelversion` after each build. The v17.3.4
  release commit changed `Cargo.toml`/`Cargo.lock` but omitted
  `MODULE.bazel.lock` regeneration, so Bazel 9.2.0 deterministically rewrites
  that lock (documented, predeclared effective identity
  `037601949bfb583a6e301589698894df301acfe82e858b6e9619575a864ca1ed`; declared
  source identity `0060efc6…` stays the clone-start requirement). Require:
  `bun.lock`, `Cargo.lock`, `Cargo.toml`, `MODULE.bazel`, and `.bazelversion`
  to equal the measured design values, and `MODULE.bazel.lock` to equal the
  predeclared effective value. Both builds must produce byte-identical
  effective lock bytes and normalized lock delta. This is a narrowly
  documented exception for the verified release omission; any other rewrite or
  any delta/closure/output difference invalidates the closure — do not bind a
  different post-mutation file by convenience.

- [x] Require both `packages/coding-agent/dist/omp` files to exist, be regular
  files, report `omp/17.3.4`, and compare byte-for-byte with `cmp` (whole-file;
  no equivalence or path normalization of the artifact). Before final bundling,
  require the native addon to contain no `processwrapper-sandbox/` path and to
  have `mtime_ns == 0`; after bundling, decompress the embedded addon from both
  outputs and require it to be byte-identical. Hash the common whole output
  only after every comparison passes. If any check differs, stop. Do not pin
  one build or add a digest exception.

### Step 1.3: Install and encode the pin

- [x] Install the verified file atomically as `~/.local/bin/omp`, owned by the
  current user and mode `0555`; ensure that directory precedes any other OMP on
  `PATH`.
- [x] Add a frozen `OmpBinaryPin` with platform, architecture, AVX2 target,
  version, source commit, build-launcher paths/digests, selected Bazel
  action-toolchain labels and executable digests, source/module-lock hashes,
  audited native-archive overlay SHA-256, positive environment schema,
  `bazel_jobs`, `bazel_spawn_strategy`, `native_addon_mtime_ns`, and final
  executable SHA-256. Expose pure helpers
  that validate platform, CPU target, build observations, and a supplied
  version/digest observation; do not add an override environment variable.
- [x] Add RED/GREEN tests for supported platform/CPU target, wrong platform,
  wrong version/digest/launcher path/launcher digest, wrong Bazel target,
  Rust/C/C++ toolchain label or executable digest drift, spawn-strategy drift,
  addon-mtime drift, non-string values, exact canonical serialization, and
  planted parent build overrides rejected before launch.

### Step 1.4: Capture the first real fixtures

- [x] Use the installed binary for one transient `-p --mode json --no-session`
  response and one explicit fresh-session response. Use the fixed model
  `openai-codex/gpt-5.6-sol`, prompt `Reply exactly OK`, and no tools for this
  calibration only.
- [x] Commit raw stdout JSON fixtures and one primary session JSONL fixture.
  Remove no fields; tests may normalize expected timestamps/ids structurally.
  Check that fixtures contain no credential value before staging.

### Verification

```sh
pytest --collect-only -q tests/test_provider_omp_pin.py
pytest -q tests/test_provider_omp_pin.py
~/.local/bin/omp --version
```

Expected: pin unit tests pass and stdout is exactly `omp/17.3.4` plus LF.

**Commit:** `Pin reproducible OMP executable`

---

## Task 2: Extract Descriptor-Safe Filesystem Primitives

**Purpose:** Implement no-follow tree reads and no-replace publication once,
then reuse them for conf, sessions, scaffolds, and links.

**Files:**

- Modify: `orchestrator/_common/io_atomic.py`
- Create: `orchestrator/_common/safe_tree.py`
- Modify: `orchestrator/providers/isolation_bundle_broker.py`
- Modify: `orchestrator/providers/isolation_environment.py`
- Modify: `tests/test_common_io_atomic.py`
- Create: `tests/test_safe_tree.py`
- Run adjacent existing isolation tests; do not refactor unrelated broker logic

### Step 2.1: Write REDs

Cover:

- Linux `renameat2(RENAME_NOREPLACE)` success and destination collision;
- absence of a replace fallback;
- descriptor-relative regular-file walking with deterministic UTF-8 POSIX rows;
- rejection of symlinks, hard-linked duplicates, devices/FIFOs, undecodable
  names, `.`/`..`, absolute paths, path swaps, and duplicate canonical paths;
- streaming SHA-256 and copy to a caller-owned destination descriptor;
- close-on-exec on every returned/opened descriptor.

### Step 2.2: Implement the minimum helpers

- [ ] Move the two existing private no-replace implementations into one public
  `rename_noreplace_at` helper and make both existing callers delegate to it.
- [ ] Add only low-level safe-tree operations shared by at least two OMP
  consumers: deterministic descriptor walk, regular-file hash/read, and
  descriptor-relative copy. Domain allowlists and JSON schemas stay in their
  domain modules.
- [ ] Keep file contents streamed; do not load session journals wholesale.
- [ ] Preserve existing isolation error types by translating the common helper's
  typed error at the old boundary.

### Verification

```sh
pytest --collect-only -q tests/test_common_io_atomic.py tests/test_safe_tree.py
pytest -q \
  tests/test_common_io_atomic.py \
  tests/test_safe_tree.py \
  tests/test_provider_isolation_bundle_broker.py \
  tests/test_provider_isolation_environment.py
```

**Commit:** `Share descriptor-safe filesystem operations`

---

## Task 3: Add The Strict OMP JSON Transport

**Purpose:** Close F2 and make OMP output valid in transient, persisted,
streaming, observed-nonstream, plain nonstream, and controlled execution paths.

**Files:**

- Modify: `orchestrator/providers/types.py`
- Create: `orchestrator/providers/omp_protocol.py`
- Create: `orchestrator/providers/omp_transport.py`
- Modify: `orchestrator/providers/session_transport.py`
- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/workflow/provider_supervision/bindings.py`
- Modify exports only as required: `orchestrator/providers/__init__.py`
- Create: `tests/test_provider_omp_transport.py`
- Modify: `tests/test_provider_session_transport.py`
- Modify: `tests/test_provider_execution.py`
- Modify: `tests/test_provider_integration.py`
- Modify: `orchestrator/providers/observation.py`
- Modify: `tests/test_provider_observation.py`

### Step 3.1: Add protocol REDs

Using the real captured fixture plus minimal derived mutations, test:

- strict UTF-8, LF framing, final non-LF object, duplicate JSON key rejection,
  non-finite number rejection, and whitespace-only line rejection;
- sole first `session` header and every admitted header field/type;
- `message_start/update/end`, content block, tool call/result, turn, agent, and
  usage shapes exactly as X3 specifies;
- multiple text blocks/messages joined in validated order;
- recovered errors versus final errors;
- absent/false/true `isTerminal` semantics from the pinned type;
- opaque unknown events before and after settlement increment only
  `event_count`; they cannot rescue a missing lifecycle/settlement/frame or
  alter identity, output, usage, callbacks, or metadata. Malformed recognized
  events still fail closed;
- terminal/frame ordering, duplicate/spoofed frame, EOF before frame, and data
  after frame;
- ambient null versus profile-isolated closed confinement frame shape,
  minimum ABI, policy digest, and expectation mismatch;
- callback exceptions do not alter parser state;
- `finalize(require_terminal=False)` followed by mandatory finalization cannot
  settle or weaken state;
- nonzero child exit remains failure after a syntactically complete stream;
- credential-bearing assistant text, tool payloads, and opaque events affect
  the ordinary output/session surfaces as specified but never enter normalized
  provider-session metadata or diagnostic logs;
- split UTF-8, invalid bytes, and JSON-escaped OSC/CSI, ESC, BEL, carriage
  return, C0/C1, DEL, and other non-printable code points reach every
  non-interactive stdout/stderr/assistant/observation display only as visible
  ASCII escapes while captured provider/session/output values stay unchanged.

### Step 3.2: Add transport contracts

- [ ] Add `ProviderSessionMetadataMode.OMP_JSON_STDOUT`.
- [ ] Add `ProviderTemplate.command_metadata_mode: Optional[str] = None`; built-in
  construction may set it, but workflow provider mappings cannot.
- [ ] Define frozen `OmpTransportExpectation` and typed optional
  `ProviderInvocation.provider_session_dir`/expectation carriers in
  `providers/types.py`. They contain no secret, bind whether write confinement
  is required, and cannot be synthesized from a child frame.
- [ ] Define a small `SessionTransportAccumulator` protocol so executor code no
  longer type-narrows every accumulator to Codex.

### Step 3.3: Implement the state machine

- [ ] Put closed object/field validators in `omp_protocol.py` and incremental
  state/normalization in `omp_transport.py`; keep both below 500 lines.
- [ ] Extend only `create_session_transport_accumulator` for factory selection;
  require the expectation for OMP mode and thread it through all four executor
  routes.
- [ ] Keep `supports_resume_boundary_observation` Codex-only; OMP fresh sessions
  do not become turn-boundary resume capable.
- [ ] Initialize invocation metadata from `command_metadata_mode`, then override
  it only when an explicit `ProviderSessionSupport` command is selected.
- [ ] Route whenever `metadata_mode` is non-null, not only when
  `session_request` is non-null. Preserve persistence decisions based solely on
  `session_request`.
- [ ] Feed the same accumulator through controlled, streaming, observed, and
  nonstream paths. Finalize exactly once semantically even if snapshot calls
  occur earlier.
- [ ] Freeze and restore both invocation carriers in
  `workflow/provider_supervision/bindings.py`; supervision must not silently
  discard the trusted visit identity.
- [ ] Keep raw bytes in memory only. OMP never appends them to a transport
  spool; return only the credential-minimized metadata projection from X3.
  Preserve existing non-OMP spool behavior.
- [ ] Apply X3's one incremental terminal-safe projection at shared executor
  live stdout/stderr/assistant-text and observation append boundaries, not in
  capture, codec, provider-result, journal, or raw-log paths.

### Verification

```sh
pytest --collect-only -q \
  tests/test_provider_omp_transport.py \
  tests/test_provider_observation.py
pytest -q \
  tests/test_provider_omp_transport.py \
  tests/test_provider_session_transport.py \
  tests/test_provider_execution.py \
  tests/test_provider_integration.py \
  tests/test_provider_observation.py
```

**Commit:** `Parse pinned OMP JSON transport`

---

## Task 4: Validate OMP Conf Trees And Persisted Sessions

**Purpose:** Close the non-process half of F3/F5: exact YAML/frontmatter
admission, bundled-agent exclusion, journal parsing, settlement, manifests, and
preset observation.

**Files:**

- Modify: `pyproject.toml`
- Create: `orchestrator/providers/omp_conf.py`
- Create: `orchestrator/providers/omp_session.py`
- Create: `orchestrator/providers/omp_observation.py`
- Create: `tests/test_provider_omp_conf.py`
- Create: `tests/test_provider_omp_session.py`
- Create: `tests/test_provider_omp_observation.py`
- Create small fixtures under `tests/fixtures/omp/conf/` and
  `tests/fixtures/omp/sessions/`

### Step 4.1: Admit one YAML dependency

- [ ] Add `PyYAML>=6.0.2,<7` to runtime dependencies. Do not write a partial YAML
  parser.
- [ ] Build a `SafeLoader` subclass that rejects duplicate keys, aliases,
  anchors, merge keys, and custom tags before domain validation.

### Step 4.2: Write conf REDs

Test the exact X5 tree and schemas:

- only `config.yml`, optional `agent/WATCHDOG.yml`, and one-level
  `agent/agents/*.md`;
- exact `advisor.enabled`, `memory.backend`, `task.maxConcurrency`,
  `task.maxRecursionDepth`, and sorted `task.disabledAgents` values;
- disabled list exactly
  `designer,librarian,reviewer,scout,security-reviewer,sonic,task`;
- no custom agent name collision with that list;
- unique name/description, admitted model/tools/spawns, and same-tree spawn
  references;
- `@` import rejection outside fenced/inline code;
- advisor true/file pairing and closed advisor fields;
- every safe-tree rejection, source mutation between reads, and canonical
  manifest stability.

### Step 4.3: Write session/observation REDs

Test:

- exact 256-byte title slot including LF and pad;
- sole physical session header and recognized `SessionEntry` union;
- graph ids/parents/order/root/leaf rules;
- primary basename/id selection;
- `journal`, `settled`, `advisor`, `child`, and `hub` predicates;
- all discovered journals must settle even when topology counts are otherwise
  met;
- primary never classifies as child/advisor;
- isolated child worktree path must be absent at close;
- recognized digest count enforcement and unrecognized-conf behavior;
- live versus immutable snapshot manifests and mutation refusal.

### Step 4.4: Implement modules

- [ ] `omp_conf.py` owns schema validation, canonical manifest bytes, source
  revalidation, immutable snapshot, and runtime seed later confined by Task 5.
- [ ] `omp_session.py` owns physical title/header/entry parsing and branch graph.
- [ ] `omp_observation.py` owns settlement/topology classification and manifest
  comparison. It consumes parsed records; it does not reparse JSON ad hoc.
- [ ] All descriptor work delegates to Task 2 helpers and closes descriptors on
  every error path.

### Verification

```sh
python -m pip install -e .
pytest --collect-only -q \
  tests/test_provider_omp_conf.py \
  tests/test_provider_omp_session.py \
  tests/test_provider_omp_observation.py
pytest -q \
  tests/test_provider_omp_conf.py \
  tests/test_provider_omp_session.py \
  tests/test_provider_omp_observation.py
```

**Commit:** `Validate OMP conf and session observations`

---

## Task 5: Launch OMP Through Four Provider Templates

**Purpose:** Close F1, process-level F3, and F6 with one launch adapter,
inherited child-lifetime write confinement, and no public
binary/lane/session-directory override.

**Files:**

- Create: `orchestrator/providers/omp_launch.py`
- Create: `orchestrator/providers/omp_write_confinement.py`
- Create: `orchestrator/providers/omp_templates.py`
- Modify: `orchestrator/providers/registry.py`
- Modify: `orchestrator/providers/types.py`
- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/validation.py`
- Create the launch-time neutral package:
  `orchestrator/omp_assets/__init__.py` and exact resources under
  `orchestrator/omp_assets/confs/neutral/`
- Modify package data: `pyproject.toml`
- Create: `tests/test_provider_omp_launch.py`
- Create: `tests/test_provider_omp_templates.py`
- Modify: `tests/test_provider_call_policy.py`
- Modify: `tests/test_state_manager.py`
- Modify: `tests/test_workflow_shared_validation.py`
- Create: `tests/test_omp_package_assets.py`
- Modify the narrow provider-session workflow tests selected by discovered
  callsites
- Create: `tests/fixtures/omp/fake_omp.py`

### Step 5.1: Write visit and substitution REDs

Test:

- `StateManager.provider_session_visit_dir(step_id, visit_count)` shares the
  metadata join key and rejects invalid identity/count;
- metadata/empty compatibility-spool creation never creates the child-writable
  live directory; finalized OMP success or failure removes that empty spool;
- `${PROVIDER_SESSION_DIR}` is legal exactly once only in a fresh command;
- the reserved value wins before authored/default/step parameters and cannot be
  escaped or overridden;
- transient invocation has OMP metadata mode but no visit dir/persistence;
- interrupted recovery increments the visit count, marks/preserves the old visit,
  allocates a new directory, and cannot publish the orphan.

### Step 5.2: Write fake-child launch REDs

Exercise `omp_launch.run(..., pin=fake_pin, binary_resolver=fake_resolver)`
directly; production `main()` always supplies the code-owned pin/resolver. Use
the real kernel Landlock path for confinement cases rather than mocking the
safety boundary.
Test:

- exact argv for ambient, ambient-unrestricted, no-tools, conf, and
  conf-inference; zero positional prompt arguments;
- stdin bytes and EOF, stdout byte preservation plus sole final adapter frame,
  and diagnostic-only stderr;
- ordinary `--no-session` versus exclusive fresh `--session-dir`;
- source opened no-follow, owner/mode/type check, descriptor-copy hash, private
  reopen/hash, private-only version/run execution, and source path substitution;
- exact version probe output/exit/stderr contract;
- ambient workspace cwd/environment; profile-isolated empty process/OMP cwd;
  `conf` alone receives `--add-dir`, while `no-tools` and `conf-inference` do
  not;
- exact positive environment, `PI_CODING_AGENT_DIR == $HOME/.omp/agent`,
  loopback broker URL grammar, paired token, excluded env canaries, and a
  planted parent fd not inherited by either probe or child;
- ambient null confinement; profile probe and child require Landlock ABI 3 or
  newer and report one matching `omp_write_confinement.v1` policy digest;
- profile direct and spawned create/write/truncate/replace/rename/restore
  attempts under `$HOME/.omp` fail while each exact XDG data/state/cache, temp,
  optional live-session, and conf-only workspace write root succeeds;
- unavailable ABI, setup failure, missing/non-directory/overlapping/extra write
  root, confinement-frame absence/mismatch, and helper bypass fail before success;
- admitted custom agents are discovered repeatedly from the immutable
  `$HOME/.omp/agent/agents`, while bundled/user/global agents remain absent;
- conf source/runtime mutation, primary id/file mismatch, spoofed frame,
  unsettled child/advisor, and nonzero child exit;
- no OMP output spool on transient, successful fresh, or failed fresh
  execution; non-OMP spool retention remains unchanged.

### Step 5.3: Implement runtime handoff

- [ ] Extend provider command validation for reserved session-dir placement and
  accepted metadata modes. Reject authored workflow key
  `command_metadata_mode`; do not silently enable it.
- [ ] Before command preparation, resolve the active session runtime and its
  canonical visit directory.
- [ ] Pass only that trusted directory into `prepare_invocation`;
  `${PROVIDER_SESSION_DIR}` substitutes from the carrier, never from
  authored/default/step parameters or child output.
- [ ] Implement `omp_write_confinement.py` as the small dependency-free Linux
  exec helper. Require Landlock ABI 3, handle every ABI-3 filesystem mutation
  right, set `no_new_privs`, admit only no-follow-opened existing directory
  roots, reject any root containing the runtime conf/snapshot/empty cwd, install
  the role-labelled write allowlist, and `execve` the private OMP binary. Its
  private parser accepts expected ABI/digest, the fixed protected roles,
  exactly one each of XDG data/state/cache/temp write roles, optional
  session/conf-workspace roles, then `--` plus the private OMP argv. It reopens
  and recomputes everything; unknown/duplicate/wrong-cardinality roles or a
  non-private target fail before restriction/exec. Do not activate or widen the
  unfinished public provider-isolation subsystem.
- [ ] For every profile-isolated version probe and child, execute through that
  helper with immutable `$HOME/.omp` and only XDG data/state/cache, temp,
  optional live-session, and conf-only workspace write roots. Ambient lanes
  remain unconfined and explicitly report null confinement.
- [ ] Bind the exact rights/roles/paths and opened descriptor identities into a
  canonical private policy digest, carry the required/null expectation through
  the accumulator, and emit only ABI plus digest in the adapter frame and
  normalized metadata.
- [ ] After preparation, derive one frozen expectation from the actual prepared
  adapter argv, code-owned lane policy, concrete model, workspace, explicit
  persistence, and active visit. Attach it to the prepared invocation before
  execution.
- [ ] Carry both values unchanged through supervision and execution. Provider
  code never reaches into `StateManager`.
- [ ] The accumulator factory requires an expectation for OMP mode and compares
  the adapter frame against it.
- [ ] Persist the accumulator's full credential-minimized OMP metadata
  projection, not only event count. Never copy assistant content, tool payloads,
  opaque events, or broker-token values into provider-session metadata or logs.
  This is a persistence boundary, not secrecy from `omp_conf` model-facing
  tools: the conf lane is explicitly credential-bearing as X2 states.
  Remove the empty compatibility spool on finalized successful or failed OMP
  fresh visits; transient calls create no spool and non-OMP retention is
  unchanged.
- [ ] Set `close_fds=True` and no `pass_fds` on every probe/helper/child launch.
  Close-time snapshot/source/runtime rehash remains supplemental observation,
  never the enforcement mechanism.

### Step 5.4: Register exact templates

Use `sys.executable -m orchestrator.providers.omp_launch` as the wrapper prefix.
The adapter parser accepts only `run`, `--lane`, `--model`, optional
conf-lane-only `--conf-root`, and fresh-only `--provider-session-dir`. Each
ordinary template command ends after its admitted model/conf values; its
`fresh_command` is the same token list plus
`--provider-session-dir ${PROVIDER_SESSION_DIR}`. The adapter converts that
private argument to OMP's `--session-dir`; ordinary calls convert to
`--no-session`.
Register:

- `omp`: ambient, write approval;
- `omp_no_tools`: profile-isolated neutral conf, no workspace `--add-dir`,
  `--no-tools`, write approval;
- `omp_conf`: profile-isolated `${inputs.omp_conf_root}`, workspace `--add-dir`,
  write approval;
- `omp_unrestricted_workspace`: ambient, `--yolo`;
- `omp_conf_inference`: registry-available internal template used only by the
  prompt service, neutral conf, no workspace `--add-dir`, and `--no-tools`.

All default to `openai-codex/gpt-5.6-sol`, stdin input, ordinary
`--no-session`, fresh-only session support, no resume command, and command
metadata mode `OMP_JSON_STDOUT`. Prompt CLI admission, not the registry name,
keeps inference off the public prompt-provider selector.

`Internal` is not a registry-authorization claim: authored workflows can name
the neutral no-tools template, but the prompt task-provider grammar cannot.

### Verification

```sh
pytest --collect-only -q \
  tests/test_provider_omp_launch.py \
  tests/test_provider_omp_templates.py \
  tests/test_omp_package_assets.py

pytest -q \
  tests/test_provider_omp_launch.py \
  tests/test_provider_omp_templates.py \
  tests/test_omp_package_assets.py \
  tests/test_provider_call_policy.py \
  tests/test_provider_execution.py \
  tests/test_provider_integration.py \
  tests/test_state_manager.py \
  tests/test_at72_provider_state_persistence.py \
  tests/test_workflow_shared_validation.py

```

Run one marked real-binary transient/fresh smoke and the unprivileged transient
write → spawn → restore confinement probe only after fake-child tests pass.

**Commit:** `Launch pinned OMP provider templates`

---

## Task 6: Add Target 2.27 `:session-artifact`

**Purpose:** Expose explicit fresh-session capture without widening public
runtime contracts.

**Files:**

- Modify target gates:
  `orchestrator/workflow_lisp/syntax.py`,
  `orchestrator/workflow/validation.py`,
  `orchestrator/workflow/run_ref/config.py`, and
  `orchestrator/workflow/run_ref/bundle_transport.py`
- Modify AST/elaboration/facade:
  `orchestrator/workflow_lisp/expressions.py` and
  `orchestrator/workflow_lisp/__init__.py`
- Modify typecheck placement:
  `orchestrator/workflow_lisp/typecheck_context.py`,
  `orchestrator/workflow_lisp/typecheck_dispatch.py`,
  `orchestrator/workflow_lisp/workflows.py`,
  `orchestrator/workflow_lisp/typecheck_proofs.py`,
  `orchestrator/workflow_lisp/typecheck_loop_recur.py`,
  `orchestrator/workflow_lisp/typecheck_resume.py`, and
  `orchestrator/workflow_lisp/typecheck_effects.py`
- Modify lowering/reconstruction:
  `orchestrator/workflow_lisp/lowering/effects.py`,
  `orchestrator/workflow_lisp/wcc/elaborate.py`, and
  `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Inspect but do not change unless references prove otherwise:
  `orchestrator/workflow_lisp/expression_traversal.py`,
  `orchestrator/workflow_lisp/functions.py`, and
  `orchestrator/workflow_lisp/macros.py`
- Create: `tests/test_workflow_lisp_session_artifact.py`
- Create: `tests/test_workflow_lisp_session_artifact_e2e.py`
- Create focused `.orc` fixtures under
  `tests/fixtures/workflow_lisp/session_artifact/`
- Modify narrow version/facade tests discovered from the target-gate references

### Step 6.1: Write syntax/type REDs

Cover:

- target 2.26 rejection and 2.27 admission;
- exact bare symbol syntax, missing value, duplicate keyword, and invalid symbol;
- symbol resolves as scalar `String` artifact;
- collision with authored or previously synthesized artifact, with no partial
  registry mutation;
- two root-sequential provider calls with different symbols;
- non-root procedure, phase, branch, loop, imported-workflow, and resume
  placement rejection;
- `:delivery :phased` and any materialization-attempt pairing rejection when a
  session artifact is present;
- Workflow Lisp provider results have no `:retries` clause. Do not add one;
  exercise retry incompatibility only through the existing downstream
  executable-workflow validator.
- unsupported provider rejected by the existing final session validator;
- omitted clause remains transient.

A legal root placement is the entry workflow's top-level expression or its
sequential `let*` binding spine. It is not any effect nested beneath another
control/procedure/phase/loop owner.

### Step 6.2: Write lowering/runtime REDs

Compile a minimal source and assert only existing shapes:

```json
"artifacts": {"omp_session": {"kind": "scalar", "type": "string"}}
```

and on the provider step:

```json
"provider_session": {"mode": "fresh", "publish_artifact": "omp_session"}
```

Then execute with a fake OMP provider and assert the existing artifact path
publishes the session id. Assert no Core/Semantic/Executable IR schema member,
runtime step kind, or state schema changes.

### Step 6.3: Implement the narrow field

- [ ] Add immutable `SessionArtifactSpec` and an optional field on
  `ProviderResultExpr`. It is a declaration, not a `NameExpr`; expression,
  hygiene, and free-name traversals must not visit it.
- [ ] Thread one inherited `session_artifact_allowed` typecheck flag from the
  entry workflow root/`let*` spine. Clear it at every branch, loop, resume,
  phase, live-provider, procedure, and function boundary.
- [ ] In `_lower_provider_result_operation`, reject an existing
  `context.top_level_artifacts` name before mutation, then add the scalar
  declaration and existing `provider_session` block.
- [ ] Carry the spec through both WCC payload/reconstruction sites; add no
  WCC/runtime node.

### Verification

```sh
pytest --collect-only -q \
  tests/test_workflow_lisp_session_artifact.py \
  tests/test_workflow_lisp_session_artifact_e2e.py
pytest -q \
  tests/test_workflow_lisp_session_artifact.py \
  tests/test_workflow_lisp_session_artifact_e2e.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_e1_normative_contract.py \
  tests/test_workflow_lisp_e2_trial_contract.py \
  tests/test_artifact_dataflow_integration.py \
  tests/test_at72_provider_state_persistence.py
```

**Commit:** `Publish OMP sessions from Workflow Lisp`

---

## Task 7: Package Presets And Build Deterministic Scaffolds

**Purpose:** Implement exact/default contract parsing and verified no-clobber
source generation before any CLI starts a provider.

**Files:**

- Modify launch-time package: `orchestrator/omp_assets/__init__.py`
- Create: `orchestrator/omp_assets/infer-output-contract.orc`
- Add exact conf resources under `orchestrator/omp_assets/confs/advised/`,
  `fanout/`, `peer-team/`, and `advised-fanout/`; reuse Task 5's `neutral/`
- Modify package data as required: `pyproject.toml`
- Create: `orchestrator/prompt_contract.py`
- Create: `orchestrator/prompt_scaffold.py`
- Create: `tests/test_prompt_contract.py`
- Create: `tests/test_prompt_scaffold.py`
- Modify: `tests/test_omp_package_assets.py`
- Create preset prompt fixtures under `tests/fixtures/omp/presets/`

### Step 7.1: Write contract REDs

Test strict duplicate-key-rejecting JSON for:

- default semantic `String`;
- exact scalar and record modes;
- canonical `Optional`, `List`, and `Map[String,T]` recursion;
- invalid identifiers, duplicate fields, unknown keys/types, bool-as-int errors,
  empty record, and depth above 16;
- inferred draft accepts only ordered `{name,type}` rows;
- deterministic `PromptResult_<8hex>` derived without recursive identity;
- closed `scaffold_output_contract.v1` default/exact/inferred provenance.

### Step 7.2: Write scaffold REDs

Test:

- exact prompt bytes in `prompt.md` and no path guessing;
- deterministic `run.orc`, prompt/provider manifests, output contract, and
  scaffold identity for all four public providers;
- generated source target 2.27, pinned concrete model, exact semantic return,
  and exactly one `:session-artifact omp_session`;
- `omp_conf_root` input/conf copy only for `omp_conf`;
- `omp_no_tools` identity binds the code-owned neutral conf manifest without an
  authored conf override;
- binary pin and provider policy are identity inputs;
- scaffold-root-relative manifest rows, modes, full file coverage, and no extra
  nodes;
- symlink/special parent refusal, concurrent same-identity publication,
  `RENAME_NOREPLACE`, verified reuse, mismatched occupant refusal, and no delete
  or force path;
- any source/conf/provider/binary pin drift rejects rerun.
- verification-to-execution race fixtures replace `run.orc`, `prompt.md`, each
  extern manifest, and copied conf after verification; execution must consume
  only the captured private snapshot and no substituted byte.

### Step 7.3: Implement package resources and services

- [ ] Materialize all package resources through `importlib.resources`; do not
  assume a source checkout path. Extend rather than replace Task 5's neutral
  package.
- [ ] Keep `prompt_contract.py` pure: parse, normalize, hash, and render types.
- [ ] Keep `prompt_scaffold.py` responsible for capture, identity, rendering,
  manifest verification, compilation check, lock, and no-replace publication.
- [ ] Reuse `WorkflowAssetResolver`, the ordinary frontend compiler, Task 2
  filesystem helpers, Task 4 conf validation, and Task 1 binary pin.
- [ ] From the same no-follow descriptors/bytes that passed verification,
  materialize one run-owned private execution snapshot with `0500` directories
  and `0400` files. The ordinary compiler, extern loaders, prompt resolver, and
  conf input receive only snapshot paths; bind compiled provenance and later
  link checks to those captured bytes, not a reopened live scaffold path.
- [ ] Never evaluate model-authored source. The renderer emits only fixed syntax
  from admitted identifiers and canonical types.

### Verification

```sh
pytest --collect-only -q \
  tests/test_prompt_contract.py \
  tests/test_prompt_scaffold.py \
  tests/test_omp_package_assets.py

pytest -q \
  tests/test_prompt_contract.py \
  tests/test_prompt_scaffold.py \
  tests/test_omp_package_assets.py

python -m pip wheel . --no-deps -w /tmp/orchestrator-omp-wheel
```

Install the wheel into a temporary venv and verify all OMP package resources are
readable there before committing.

**Commit:** `Generate verified OMP prompt scaffolds`

---

## Task 8: Add `prompt run` And Tool-Free Output Inference

**Purpose:** Provide the simple user path: prompt text/file in, typed Workflow
Lisp scaffold and real run out.

**Files:**

- Modify: `orchestrator/cli/main.py`
- Create: `orchestrator/cli/commands/prompt.py`
- Modify: `orchestrator/cli/commands/__init__.py`
- Modify minimally for a caller-selected internal run id:
  `orchestrator/cli/commands/run.py` and `orchestrator/state.py`
- Create: `tests/test_cli_prompt.py`
- Modify only if existing parser assertions require it: `tests/test_cli_safety.py`
- Add inference workflow tests to `tests/test_prompt_contract.py`

### Step 8.1: Write closed CLI grammar REDs

Test `python -m orchestrator prompt run` for:

- exactly one of `--prompt`/`--prompt-file`;
- required public provider in
  `omp|omp_no_tools|omp_conf|omp_unrestricted_workspace`;
- `--conf` required iff `omp_conf`;
- optional model and mutually exclusive optional `--returns`/`--output`;
- no internal/non-OMP provider, duplicate singleton, empty value, positional
  extra, or generation flag with `--scaffold`;
- all parse errors exit 2 before provider execution or destination creation;
- verified rerun accepts exactly `--scaffold PATH`.

### Step 8.2: Write orchestration REDs

- [ ] Capture prompt, provider template, concrete model, conf, and contract
  request before inference or destination creation; mutate each source after
  capture and prove generated bytes use the capture.
- [ ] Default and `--returns` perform no inference call.
- [ ] `--output` is accepted only through the design's closed provider mapping;
  `omp_no_tools` and `omp_conf` map to `omp_conf_inference`; the two ambient
  providers fail before a model call.
- [ ] The packaged inference workflow receives typed task prompt/output request,
  uses neutral profile isolation, no tools/session, returns only
  `OutputContractDraft`, and fails without repair/fallback.
- [ ] Generated source compiles before execution; CLI delegates to the ordinary
  run path and propagates its stdout/exit status.
- [ ] Scaffold path is printed only to stderr.
- [ ] Allocate the run id before scaffold verification, create the private
  execution snapshot beneath that run root, and pass only its paths to the
  ordinary compiler/runner. Barrier-controlled swaps of every live scaffold
  input after verification must not change compiled or provider-visible bytes.

### Step 8.3: Add a minimal structured run seam

- [ ] Add a public `StateManager.new_run_id()` using the current format.
- [ ] Add immutable `RunWorkflowResult` with `exit_code`, exact `run_id` and
  `run_root`, final workflow outputs, session id/status, and normalized usage.
- [ ] Allow `run_workflow(..., run_id=<internal value>)` as a keyword-only
  service argument and return `RunWorkflowResult`; the public `run` parser
  exposes no new flag and CLI dispatch returns only `result.exit_code`.
- [ ] Prompt run allocates the id, verifies the published scaffold, and
  materializes its private snapshot by exclusive no-follow creation at
  `<runs-root>/<run-id>/prompt-inputs`; a pre-existing run root fails before
  execution. It then invokes ordinary `run_workflow` with that id and only
  snapshot paths and requires the returned `run_root` to be the reserved root.
  Inference reads the typed `OutputContractDraft` from
  `result.workflow_outputs`; prompt execution uses the same captured provenance
  plus `result.run_root`/session fields for later link publication. Neither path
  parses stdout, scans run directories, or reopens the live scaffold.
- [ ] Do not refactor the rest of `run.py` or duplicate workflow execution.

### Verification

```sh
pytest --collect-only -q tests/test_cli_prompt.py
pytest -q \
  tests/test_cli_prompt.py \
  tests/test_cli_run_ref_root.py \
  tests/test_cli_safety.py \
  tests/test_prompt_contract.py \
  tests/test_prompt_scaffold.py
```

Smoke the default and exact modes against a fake OMP child through the actual
CLI, not by calling only service functions.

**Commit:** `Run prompts through generated Workflow Lisp`

---

## Task 9: Publish Session Links And Import Primary Sessions

**Purpose:** Bind successful prompt runs to state/scaffold/session observations,
then allow a primary OMP conversation to seed a new verified workflow.

**Files:**

- Create: `orchestrator/prompt_session.py`
- Modify: `orchestrator/cli/commands/prompt.py`
- Modify: `orchestrator/state.py`
- Create: `tests/test_prompt_session.py`
- Modify: `tests/test_cli_prompt.py`

### Step 9.1: Write link/index REDs

Test exact closed `session_link.v1` validation and publication:

- link writes only after successful prompt run and agreement among state,
  credential-minimized provider-session metadata, adapter frame, primary
  journal, snapshot/conf manifests, scaffold, source, prompt, and contract;
- every run-relative/scaffold-relative path resolves no-follow beneath its
  opened root;
- no OMP transport spool exists or participates in link identity;
- link and state provenance bind the private execution-snapshot bytes captured
  before task execution, not a later reopening of the mutable live scaffold;
- binary pin, provider policy/model/lane, visit key, session id, and null/exact
  confinement identity agree;
- no-replace collision fails; failure leaves no partial link;
- interrupted/orphan/failed provider visits are not index candidates;
- exact lookup precedence run id, active session id, active primary basename;
- zero, prefix, child/advisor, malformed, blocked-chain, and ambiguous matches
  fail with stable codes and no arbitrary path reaches OMP.

### Step 9.2: Write import REDs

Test the exact grammar and parser:

- new contract mode accepts the same four public providers/model/conf/contract
  matrix as `prompt run`;
- reuse mode is the sole flag and rejects every override;
- title/header/entry graph is validated before extracting text;
- active branch is found by following the final leaf to root;
- source prompt is first user `message` before first assistant on that branch;
- string content is byte-for-byte; array content accepts only text blocks joined
  once with LF;
- missing/empty/image/tool/ambiguous/post-assistant-only prompt fails;
- new-contract import treats extracted text as new authored prompt;
- reuse verifies composed prompt digest and takes prompt/contract/conf/provider/
  model only from the source scaffold;
- import never selects or copies child/advisor journals.

### Step 9.3: Implement link and import

- [ ] `prompt_session.py` owns closed record parsing, no-replace link write,
  continuation-chain validation, exact index lookup, active primary resolution,
  and prompt extraction.
- [ ] After `prompt run` returns zero, load the known run id and publish the link;
  a link failure changes the command to nonzero.
- [ ] `prompt import` reuses Task 7/8 generation and run services. It creates no
  provider-result bundle from transcript bytes and no second session channel.

### Verification

```sh
pytest --collect-only -q tests/test_prompt_session.py
pytest -q \
  tests/test_prompt_session.py \
  tests/test_cli_prompt.py \
  tests/test_provider_omp_session.py \
  tests/test_state_manager.py
```

**Commit:** `Link and import primary OMP sessions`

---

## Task 10: Repair Integrated Launch, Observation, Publication, And Authority Seams

**Purpose:** Repair the cross-module defects found in the post-Task-9 range
review before adding another consumer of the same launch and session contracts.
This task is blocking: Task 11 resume work and Task 12 closure cannot be
accepted until R1-R8 and R10 each have a failing regression, the shared
root-cause fix, and fresh evidence on the exact candidate tree, and R9 has
explicit report and routing evidence.

**Files:**

- Modify: `orchestrator/providers/omp_launch.py`
- Modify: `orchestrator/providers/omp_launch_contract.py`
- Modify: `orchestrator/providers/omp_launch_fs.py`
- Modify: `orchestrator/providers/omp_observation.py`
- Modify: `orchestrator/providers/omp_templates.py`
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/run_lock.py`
- Modify: `orchestrator/cli/commands/prompt.py`
- Modify: `orchestrator/prompt_session_agreement.py`
- Modify: `orchestrator/prompt_session_lookup.py`
- Modify the owning OMP launch, observation, prompt-session, run-seam, and CLI
  tests. Reuse those modules; do not create another launch, broker, observer,
  settlement, or path-safety abstraction.
- Modify: `orchestrator/providers/omp_pin.py`
- Rename/modify: `orchestrator/providers/omp_source_overlay.patch`
- Modify: `orchestrator/providers/omp_conf.py`
- Modify: `orchestrator/contracts/prompt_contract.py`
- Modify the packaged fanout conf and owning pin/conf/prompt-contract tests.

### Blocking remediation ledger

- **R1 — deployable binary admission:** remove the developer-specific production
  executable path. Resolve code-owned command name `omp` once from the admitted
  parent `PATH`, then preserve the existing no-follow mode/digest/private-copy
  checks and correct ownership admission to match X2: effective-user or root
  ownership passes, foreign ownership fails. A correct pinned executable on
  another supported host must work; absent, substituted, writable, or wrong-
  digest binaries fail before probing.
- **R2 — real broker and lane environments:** never fabricate a port, listener,
  URL, or token. Profile lanes require the operator-supplied
  `OMP_AUTH_BROKER_URL` / `OMP_AUTH_BROKER_TOKEN` pair defined by X2, validate it
  structurally before the version probe, and print the exact setup command when
  missing. Do not add a connectivity preflight: a syntactically valid unreachable
  broker reaches the real child and fails the call without local-credential
  fallback or fabricated replacement credentials.
  Profile `HOME`/XDG/temp roots are adapter-owned attempt roots with the admitted
  conf materialized at the pinned discovery path. Ambient lanes retain their
  documented parent environment. Every lane uses X2's exact OMP argv; remove
  implementation-only defaults and misspelled broker variables.
- **R3 — real profile completion:** replace the real-binary check that treats
  denied OMP initialization as success evidence. One real `omp_no_tools` call
  and one real `omp_conf` fresh call must complete with a live broker while the
  direct/descendant mutation negatives and every admitted write-root positive
  remain enforced. OMP JSON-transport providers never receive the runtime-owned
  bundle path: when it is absent, prompt guidance requires final assistant JSON
  only and the parent materializes it with exclusive no-follow creation;
  provider-planted leaves fail.
- **R4 — one structured settlement authority:** remove raw-byte substring
  settlement detection. The adapter and parent must agree through parsed,
  schema-validated lifecycle state, including valid whitespace and omitted
  optional `isTerminal`; malformed, conflicting, nonterminal, or unsettled
  streams still fail. Primary-journal selection requires exactly one match.
- **R5 — production topology observation:** call the existing close-time
  observer from the real fresh launch path. It must recursively validate the
  primary, advisor, child, hub, settlement, recognized-preset cardinality, and
  isolated-worktree cleanup contract. Recognized topology authority is one
  code-owned map keyed by canonical packaged-conf digest for all five presets;
  preset labels and paths cannot select counts. Delete the shallower duplicate
  inventory path once the observer owns this decision.
- **R6 — advisor-compatible links:** session-link publication and lookup admit
  valid observed advisor journals while continuing to exclude advisor/child
  journals from primary selection and import. `advised` and `advised-fanout`
  must publish and resolve links; extra, malformed, or unsettled journals fail.
- **R7 — write-after-verification run roots:** open and identity-check the
  externally reserved run root no-follow before `mkdir`, lock creation, or any
  other write. Acquire the writer lock beneath that retained directory
  authority. Directory and symlink swaps fail without creating a file in the
  replacement target.
- **R8 — closed CLI and durable tests:** shallow or wrong-shape absolute
  `--scaffold` paths return the stable prompt error instead of `IndexError`.
  Replace literal prompt-heading assertions with contract/digest/dataflow
  assertions. The complete OMP-I1 range must pass `git diff --check`; patch-file
  whitespace is not exempt.
- **R9 — authority quarantine:** target 2.27, OMP providers, prompt commands,
  and session-link layout remain implementation-candidate surfaces until Task
  12 updates their normative specs and capability routing. No intermediate
  report or index may claim OMP-I1 complete or copy-safe.
- **R10 — descendant approval non-widening:** the pinned source overlay removes
  OMP's hardcoded headless-subagent `yolo` setting. Approved `task` dispatch
  must preserve the primary `write` mode in every descendant; write-tier tools
  complete, exec-tier tools remain blocked without interactive approval, and
  only the explicitly named unrestricted provider may use global `--yolo`.

### Step 10.1: Write integration REDs

Add the smallest regression for each R1-R8 and R10 failure before production changes:

- supported-host resolution with a PATH-installed pinned binary and no
  developer cache path, including effective-user/root-owned positives and a
  foreign-owner negative;
- missing, malformed, and misspelled broker pairs failing before the probe, a
  syntactically valid unreachable broker reaching the child and failing without
  fallback, and a live broker completing, plus exact ambient/profile environment
  and argv projections;
- real profile initialization completing without granting mutation under the
  protected OMP home;
- formatted and omitted-`isTerminal` settlement, duplicate primary journals,
  recursive advisor/child observations, and unmatched/failed hub results;
- in `tests/test_provider_omp_observation.py`, all five packaged-conf canonical
  digests selecting their exact topology, with renamed/copied paths and
  substituted labels unable to select or change that topology;
- advised/advised-fanout link publication, lookup, and primary-only import;
- pre-lock directory and symlink swaps with a planted replacement target; and
- shallow scaffold paths plus behavior-based prompt composition assertions.
- pinned-source approval inheritance, including a real spawned write-tier
  positive and spawned exec-tier negative; and OMP final-text bundle
  materialization without a provider-planted leaf.

Record the pre-fix failure for each ledger item. A fake child may prove failure
classification and races, but it cannot close R1-R6 without the named real
checks.

### Step 10.2: Repair launch and credential handoff

- [ ] Implement R1-R3 in the existing pin, launch, contract, and confinement
  modules. Reuse stdlib path/URL/process primitives and the existing descriptor-
  safe helpers; add no broker client or process manager.
- [ ] Keep credentials out of argv, frames, normalized metadata, reports, and
  logs. Redact the real broker token from child diagnostics.
- [ ] Preserve the strict platform/AVX2, binary digest, closed profile schema,
  Landlock, no-follow, descriptor inheritance, and transient/fresh boundaries.
- [ ] Implement R10 in the audited source overlay, refresh the two-clean-build
  pin, and remove exec-tier tools from write-mode canary agents that do not
  need them.

### Step 10.3: Unify observation and session agreement

- [ ] Implement R4-R6 by routing production through the existing protocol and
  close-time observer authorities. Remove duplicate byte heuristics and shallow
  topology decisions after all callers use the shared path.
- [ ] Keep disk journals observational: topology admission does not become an
  authorship or authentication claim.
- [ ] Bind the exact recursive observation report into the adapter frame,
  using only X2's accepted closed projections: primary identity under `session`
  and advisor/child relpaths under `observed`. Hub settlement, preset cardinality,
  unrecognized files, and cleanup remain close-time admission decisions and do
  not add frame, metadata, or link members. Amend the design before adding any
  new projection.

### Step 10.4: Close run-root, CLI, test-policy, and hygiene defects

- [ ] Implement R7 at the shared reserved-root/lock boundary so every prompt-run
  caller receives the same fail-before-write guarantee.
- [ ] Implement R8 without adding compatibility aliases or prompt-text locks.
- [ ] Record R9 in the Task 10 report as an intentional merge/claim boundary
  owned by Task 12, not as deferred implementation debt.

### Verification

Collect every added or renamed module first, then run the narrow owners:

```sh
pytest --collect-only -q \
  tests/test_provider_omp_launch.py \
  tests/test_provider_omp_observation.py \
  tests/test_prompt_session_publication.py \
  tests/test_cli_prompt_run_seam.py \
  tests/test_run_lock.py \
  tests/test_cli_prompt_import.py

pytest -q \
  tests/test_provider_omp_pin.py \
  tests/test_provider_omp_transport.py \
  tests/test_provider_omp_launch.py \
  tests/test_provider_omp_observation.py \
  tests/test_provider_omp_session.py \
  tests/test_prompt_session.py \
  tests/test_prompt_session_publication.py \
  tests/test_prompt_session_lookup_errors.py \
  tests/test_cli_prompt.py \
  tests/test_cli_prompt_import.py \
  tests/test_cli_prompt_run_seam.py \
  tests/test_run_lock.py \
  tests/test_state_manager.py
```

Under tmux, run the marked real-binary checks with the validated live broker:

- ambient transient completion;
- `omp_no_tools` transient completion;
- `omp_conf` fresh completion with immutable conf and workspace authority;
- one advised-fanout fresh call whose descendants retain `write` approval,
  whose final assistant JSON is parent-materialized without a provider-planted
  leaf, whose recursive observation and session link agree, and whose primary
  can be imported.

Then run `pytest -q -n 16 --dist=worksteal`, direct Pyright over the changed
modules, module compilation, installed-wheel fake-child smoke, and
`git diff --check d97ffa7da352f6b9f9ed652e892896f53e5db06a` over the full
OMP-I1 range. Task 10 is incomplete if any failure is merely reclassified as
unrelated without demonstrating that it cannot falsify R1-R10.

Request one contract/maintainability review and one security review over the
Task 10 diff plus the production call path. Both must review real integration,
not helper tests alone.

**Commit:** `Repair OMP integration seams`

---

## Task 11: Add Foreground TTY Fork And Resume

**Purpose:** Let the operator safely continue the linked primary OMP session
without pretending ProviderExecutor supports interactive resume.

**Files:**

- Create: `orchestrator/prompt_resume.py`
- Modify: `orchestrator/cli/commands/prompt.py`
- Create: `tests/test_prompt_resume.py`
- Modify: `tests/test_cli_prompt.py`
- Add a fake interactive OMP fixture under `tests/fixtures/omp/`

### Step 11.1: Write CLI/preflight REDs

Test:

- exact `prompt resume <run-or-session-id> [--in-place]` grammar;
- all fd 0/1/2 must be TTY before lock or child start;
- lookup uses only Task 9's active primary index;
- failed/gapped continuation chain, live digest drift, scaffold/conf/binary pin
  drift, missing current broker, and lock contention prevent launch;
- no preflight failure writes a continuation record.

### Step 11.2: Write child/postcondition REDs

Using a pseudoterminal and fake child, assert:

- stdin/stdout/stderr are inherited unchanged and `close_fds=True`;
- exact ambient, unrestricted, no-tools, and conf argv/environment/cwd from X8;
- default uses full-id `--fork`; `--in-place` uses full-id `--resume`;
- ambient uses current ambient configuration and null confinement;
  profile-isolated uses current broker credentials plus frozen conf, new empty
  cwd, recorded workspace, and the inherited Task 5 Landlock policy;
- profile direct/spawned mutation attempts against the fresh runtime copy of
  frozen conf fail while the exact live-session and conf-only workspace write
  roots remain usable;
- fork preserves source, creates exactly one new direct primary, new id, and
  exact `parentSession`;
- in-place keeps the same primary id/basename; its fixed 256-byte title slot is
  either identical or one valid pinned title-slot encoding, all subsequent
  pre-resume bytes remain an exact prefix, and at least one complete physical
  record extends the prior graph;
- valid truncation, body replacement/reordering, malformed title update, or
  title-slot-plus-history rewrite fails even when the resulting graph and child
  exit are otherwise valid;
- after any started child, exactly one next no-replace continuation record is
  written; success/failure nullability and hash-chain rules are exact;
- failed continuation permanently blocks another orchestrator continuation.

### Step 11.3: Implement standalone bridge

- [x] Keep `prompt_resume.py` independent of `ProviderExecutor` and workflow
  runtime forms.
- [x] Share Task 1 binary copy/probe, Task 4 session/conf parsing, Task 5 lane
  policy and Landlock exec helper, and Task 9 link/chain lookup. Ambient records
  null confinement; profile records the exact ABI/policy digest.
- [x] Hold one descriptor-relative per-session lock across preflight, child, post
  validation, and record publication.
- [x] Print non-secret argv and environment names to stderr before launch; never
  record broker token values.

### Verification

```sh
pytest --collect-only -q tests/test_prompt_resume.py
pytest -q \
  tests/test_prompt_resume.py \
  tests/test_prompt_session.py \
  tests/test_cli_prompt.py
```

Launch the actual CLI under tmux for one real safe fork; use the `tmux` skill
and interact with the TTY. Do not treat a non-TTY unit test as visual/interactive
proof.

**Commit:** `Fork and resume linked OMP sessions`

---

## Task 12: Close Preset Canaries, End-To-End Trial, And Documentation

**Purpose:** Prove the selected behavior on the real binary, then make docs say
exactly what shipped.

**Files:**

- Create/modify real integration tests under `tests/test_omp_integration.py`
- Finalize package resources and canary fixtures from Task 7
- Modify: `specs/providers.md`
- Modify: `specs/cli.md`
- Modify: `specs/dsl.md`
- Modify: `specs/versioning.md`
- Modify: `specs/state.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md`
- Modify: `docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md`
- Modify final status:
  `docs/plans/2026-08-14-omp-integration-design-and-roadmap.md`
- Create: `docs/omp_upgrade_runbook.md`

### Step 12.1: Close real feasibility gates

Run against the installed pinned binary and loopback auth broker:

- [x] F1 transient, fresh, and standalone full-id fork placement;
- [x] F2 captured protocol and nonzero-exit composition;
- [x] F3 exact profile environment/cwd and agent-directory binding; Landlock ABI
  and policy identity; direct and descendant conf create/write/truncate/replace/
  rename/restore refusal;
  every admitted write-root positive; ambient resource negatives;
  repository-context/workspace read-write positive for `conf` and negative for
  `no-tools`/inference; bundled-agent disablement; and no inherited planted fd;
- [x] F4 installed binary/version/digest and private-copy execution;
- [x] F5 neutral/advised/fanout/peer-team/advised-fanout exact observations;
- [x] F6 write/yolo confinement;
- [x] F7 lookup, real TTY fork, in-place resume, import, and refusal cases;
- [x] F8 tool-free typed output inference and invalid-draft refusal.

Mark network/credential cases `e2e` and `requires_secrets`; they may skip in an
ordinary suite but must be run explicitly here. Do not loosen a predicate to
make a model run pass. Retry only a documented transient provider failure; a
second behavior mismatch is a real gate failure.

### Step 12.2: Run the declarative trial

From a clean temporary workspace with planted ambient canaries:

```sh
python -m orchestrator prompt run \
  --prompt-file task.md \
  --output "summary, changed files, and verification" \
  --provider omp_conf \
  --conf orchestrator/omp_assets/confs/advised-fanout
```

Verify:

- exact prompt capture and structurally compiled inferred contract;
- deterministic scaffold and binary-bound identity;
- advised-fanout session topology and settled journals;
- typed result plus published `omp_session`;
- terminal-safe observation pane text and complete usage exactly once;
- credential-minimized metadata, Landlock policy identity and immutable conf
  observation, absence of an OMP transport spool, live/snapshot/conf manifests,
  and link;
- TTY default fork and one continuation record;
- `prompt import --reuse-run-contract` returns to the same scaffold identity.

### Step 12.3: Sync documentation

- [x] Providers spec: four public templates, internal inference, exact trust
  lanes, binary pin, launch/codec/observation boundaries, no-tools behavior.
- [x] CLI spec: closed run/import/resume grammars, output modes, scaffold
  identity, no-replace, TTY behavior.
- [x] DSL/version specs: target 2.27 and only `:session-artifact`.
- [x] State spec: visit directory, interrupted non-reuse, credential-minimized
  metadata with no OMP transport spool, live/snapshot/conf, link and
  continuation records.
- [x] Drafting guide: minimal `omp`, `omp_no_tools`, and `omp_conf` examples;
  state that `omp_conf --add-dir` loads repository context while no-tools and
  inference omit the workspace root.
- [x] Capability matrix/index/roadmap: mark only tested surfaces implemented;
  retain OMP-I2, RPC steering, per-call conf, other platforms, and child import
  as future.
- [x] Upgrade runbook: source tag/commit, recorded positive build environment,
  two-build digest gate, fixture recapture, env/conf review, canaries, scaffold
  pin bump.

### Step 12.4: Final verification

Narrow first:

```sh
pytest -q \
  tests/test_provider_omp_pin.py \
  tests/test_common_io_atomic.py \
  tests/test_safe_tree.py \
  tests/test_provider_omp_transport.py \
  tests/test_provider_omp_conf.py \
  tests/test_provider_omp_session.py \
  tests/test_provider_omp_observation.py \
  tests/test_provider_omp_launch.py \
  tests/test_provider_omp_templates.py \
  tests/test_workflow_lisp_session_artifact.py \
  tests/test_workflow_lisp_session_artifact_e2e.py \
  tests/test_prompt_contract.py \
  tests/test_prompt_scaffold.py \
  tests/test_omp_package_assets.py \
  tests/test_cli_prompt.py \
  tests/test_cli_prompt_import.py \
  tests/test_prompt_session.py \
  tests/test_prompt_resume.py \
  tests/test_run_lock.py
```

Then the real selected e2e tests under tmux. Finally run the repository gate:

```sh
pytest -q -n 16 --dist=worksteal
```

Also build/install the wheel in a fresh venv and run one fake-child
`python -m orchestrator prompt run` smoke from outside the source checkout.
Inspect new-module line counts; split only a module above 500 lines, without
inventing an abstraction for future use.

Request one final contract/maintainability review and one security review in
parallel over the whole OMP-I1 range. Apply the blocking rule in the execution
contract; after any fix, rerun its affected narrow test plus the full suite.
Do not claim completion from inspection.

**Commit:** `Complete OMP prompt integration`

---

## Completion Evidence

OMP-I1 is complete only when all of the following are recorded from fresh
commands:

1. the two clean OMP builds are byte-identical and the installed binary matches
   the committed platform/version/digest pin;
2. Task 10's R1-R10 ledger is closed on the exact candidate tree; no
   developer-specific binary path, fabricated/misspelled broker channel,
   expected real-profile failure, dead observer, advisor-link contradiction,
   abnormal child admission, descendant `yolo` widening, provider-planted
   bundle leaf, pre-verification write, prompt-text assertion, or range-wide
   diff-check failure remains;
3. F1-F8 are closed or the corresponding optional feature was removed and the
   design/specs were revised before merge;
4. all four public templates execute their exact lane policy, and ordinary
   calls remain transient;
5. target 2.27 compiles and runs `:session-artifact` through the existing
   provider-session/scalar-artifact contract;
6. default/exact/inferred prompt scaffolds compile, verify, and refuse tamper or
   overwrite;
7. the real advised-fanout trial produces the typed result, published session,
   exact topology observation, link, safe fork, and deterministic import reuse;
8. installed-wheel resource and CLI smoke passes outside the source checkout;
9. focused tests, marked real tests, and
   `pytest -q -n 16 --dist=worksteal` pass; and
10. no unresolved review finding demonstrates a specification, security, or
   maintainability contract violation.
