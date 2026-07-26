# Security and Path Safety (Normative)

- Path safety
  - Reject absolute paths and any path containing `..` during validation.
  - Follow symlinks; if the resolved path escapes WORKSPACE, reject the path.
  - Apply checks at load time and before filesystem operations.
  - Dashboard file routes may serve only files under the selected resolved workspace root or the selected scanned run root after validation.
  - Dashboard route references must be workspace-relative or run-relative; dashboard HTML must not expose raw absolute filesystem links.
  - Dashboard paths recorded in state, logs, artifacts, provider metadata, and lineage are untrusted data. State-provided `run_root` must not define the server's file-serving authority.
  - Reusable-call additions:
    - `imports` and nested import targets resolve relative to the authored workflow file and must remain within WORKSPACE.
    - `asset_file` and `asset_depends_on` resolve from the directory containing the authored workflow file and must remain within that workflow source tree.
    - `input_file`, `depends_on`, `output_file`, `expected_outputs.path`, `output_bundle.path`, `consume_bundle.path`, and deterministic `relpath` outputs remain WORKSPACE-relative under `call`.

Note: These safety checks apply to paths the orchestrator resolves (e.g., `input_file`, `output_file`, `depends_on`, `wait_for`). Child processes invoked by `command`/`provider` can read/write any locations permitted by the OS; use OS/user sandboxing if stricter isolation is required. This remains the current runtime contract while provider-phase isolation integration is pending: packaging the versioned policy schema by itself does not change process authority.

- Provider-phase isolation boundary (versioned contract; runtime integration pending)
  - Omission of `provider_phase_isolation.v1` means current unrestricted
    behavior. It must not be interpreted as an implicit or best-effort
    isolation request.
  - A selected `mode: required` policy is fail-closed. Once integrated into
    public run/resume, an unavailable or mismatched backend, sealed
    environment, network review, grant, or capability must stop before
    provider launch; unrestricted subprocess fallback is forbidden.
  - Isolated profiles require a content-addressed, read-only, run-owned
    provider rootfs snapshot. Provider executables, interpreters, loaders,
    libraries, and non-secret configuration must resolve from that snapshot.
    The host `/`, host home, mutable environment source, or controller checkout
    must not be mounted for convenience.
  - Rootfs identity is a closed canonical manifest of the root and every
    descendant. Snapshot assembly is descriptor-relative, rejects unaccounted
    hardlinks, xattrs, special files, mount crossings, unsafe symlinks, and
    mutable source metadata, and publishes through a fresh digest authority.
    Every regular file and directory must enforce the fixed-zero-atime contract
    at the inode level; an unsupported flag, a no-op flag write, a cleared
    published flag, or timestamp drift makes the backend unavailable or the
    environment invalid rather than triggering repair.
  - Launch uses the verified snapshot directory descriptor as the root bind
    authority. Reopening its recorded pathname is not equivalent. Strict
    launch admission is symlink-free and validates the fixed packaged Python
    shim bootstrap plus the selected provider's complete non-executingly
    discovered runtime closure before Bubblewrap can start.
  - The positive filesystem grant is the writable candidate product plus
    invocation-private runtime surfaces. Candidate `.orchestrate` is masked.
    Workflow source, prompt assets, controller/control state, evaluators, peer
    arms, parent checkouts, prior raw result bundles, and their ancestor
    authorities must not be granted by mount or inherited descriptor.
  - Direct credentials are names, not values, in policy. Effective values are
    the intersection of the policy allowlist and each provider step's declared
    `secrets`; unrelated ambient environment and reserved runtime, loader,
    interpreter, shell-bootstrap, locale, and time variables are absent.
    Authored provider `env` is unsupported in v1.
  - Built-in tool approval/sandbox bypass flags remain provider behavior inside
    the outer boundary; they are not isolation controls. Candidate copies,
    changed working directories, prompt omission, and reviewer-package filters
    are also not OS isolation boundaries.
  - No control, controller, evaluator, peer, or parent authority may be added
    to make an isolated provider work. If the provider cannot run from the
    sealed environment and narrow grants, implementation must stop for a
    reviewed versioned extension.
  - This staged contract is not an implementation-status claim. Provider
    execution remains unrestricted until the production launcher, state,
    CLI/resume, and attestation integration is complete and verified.

- Adjudicated provider child workspaces (v2.11)
  - Candidate workspaces are run-owned copies created from a fixed immutable baseline snapshot. They are isolation boundaries for orchestrator-managed output validation and promotion, not OS sandboxes.
  - Baseline copy policy `adjudicated_provider.baseline_copy.v1` excludes `.orchestrate/`, `.git/`, dependency/cache roots, common generated cache directories, local secret denylist entries such as `.env`, unsafe symlinks, broken symlinks, and symlinks whose resolved targets would escape or point into excluded paths.
  - Safe relative symlinks may be preserved when both the link and resolved target remain inside the copied baseline and outside excluded roots.
  - Required orchestrator-managed paths that existed in the parent workspace but are excluded by the baseline policy fail before provider launch with a baseline-exclusion error. Optional excluded paths are recorded as absent.
  - Candidate-managed runtime paths must not depend on `${run.root}` or target the parent run root in the first release.
  - Baseline snapshots, candidate workspaces, composed prompts, evaluator packets, score ledgers, logs, and promotion staging can contain sensitive source or prompt material. Retain and share run roots using the same confidentiality assumptions as the original workspace.
  - `evaluator.evidence_confidentiality: same_trust_boundary` is an explicit author attestation that the evaluator provider may receive complete score-critical evidence. The runtime may scan declared secret values before packet persistence, but this is not a substitute for choosing providers within the right trust boundary.

- Reusable-call operational-risk boundary (Task 10 contract; v2.5 execution)
  - The first `call` tranche is intentionally non-isolating.
  - The loader/runtime must not claim proof of arbitrary child-process filesystem effects from imported `command` / `provider` steps.
  - Every DSL-managed reusable-workflow write root that must remain distinct across invocations is expected to be surfaced as a typed workflow `input` with `type: relpath`.
  - Call sites are expected to bind distinct per-invocation values for those write-root inputs whenever repeated or concurrent calls could otherwise alias the same managed paths.
  - Reusable workflows that hard-code DSL-managed write roots instead of parameterizing them as typed `relpath` inputs are outside the first shippable reusable-library subset and should be rejected once Task 11 implements `call`.
  - This contract covers orchestrator-managed paths only. Undeclared child-process reads/writes remain an accepted operational risk until a later execution-boundary change exists.

- Secrets handling
  - `secrets: string[]` declares environment variable names that MUST be present in the orchestrator environment.
  - Missing secrets cause step failure (exit 2) and populate `error.context.missing_secrets`.
  - Empty-string values count as present.
  - Precedence: if a key exists in both `env` and `secrets`, the child receives the `env` value and it is masked in logs as a secret.
  - Masking: best-effort replacement of known secret values with `***` in logs, state, and prompt audit.

- Environment inheritance
  - Child processes inherit the orchestrator environment, then secrets are overlaid, then step `env` is applied (step `env` wins on conflicts).

- Cross-platform note
  - Examples use POSIX tools (`bash`, `find`, `mv`, `test`). On Windows, use WSL or adapt to PowerShell equivalents.

- Dashboard content isolation
  - Dashboard previews render approved file bodies as escaped text or escaped JSON only; prompt, log, provider transport, state, backup, artifact, HTML, and SVG payloads must not execute in the dashboard origin.
  - Preview and raw responses set `X-Content-Type-Options: nosniff`.
  - Dashboard HTML routes set a restrictive Content Security Policy with `default-src 'none'`, `base-uri 'none'`, `object-src 'none'`, `frame-ancestors 'none'`, and `script-src 'none'`, plus only the minimal style/image allowances needed by the server-rendered UI.
  - Raw file responses default to `Content-Disposition: attachment` and `text/plain; charset=utf-8` for textual files or `application/octet-stream` for non-text files.
  - Dashboard routes must be read-only: they must not mutate workflow YAML, run state, logs, artifacts, backups, provider session files, or workspace source files, and must not execute operator commands.
