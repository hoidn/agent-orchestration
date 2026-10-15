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
  - The Linux launch is rootless at invocation time. An unprivileged user
    namespace can retain the controller's supplementary kernel groups even
    when inner APIs render them as the overflow GID, so an empty or
    overflow-only displayed vector is not a standalone authority proof.
    Before bootstrap release, a host-relative observer must bind the pinned
    child's one-row UID/GID maps, `setgroups: deny`, process identity, and
    underlying group multiset to the controller's prelaunch values. Before
    credential ingestion, the inner shim must independently validate
    all four real/effective/saved/filesystem UID/GID columns as zero, one-row
    normalized maps, `setgroups: deny`, a live nonzero kernel overflow GID
    distinct from provider primary GID `0`, and the expected primary/overflow
    counts. An ambiguous zero overflow GID makes the backend unavailable.
    Isolation derives from the complete positive
    mount allowlist, controller ownership of persistent writable projections,
    fresh kernel/runtime objects, and final descriptor allowlist `{0,1,2}`.
    Any foreign host object, extra mount/map/descriptor, observation drift,
    malformed proc value, or enabled group mutation fails closed.
    `sudo`, `pkexec`, privileged `setpriv`, set-id group clearing, and
    capability-bearing launch brokers are not valid v1 launch mechanisms.
  - A Bubblewrap child-PID/status record is not a final-boundary readiness
    proof. The inner shim must signal readiness exactly once on a setup-only
    descriptor after its validation and before credential fd 3 is read. The
    controller must withhold every credential byte until that signal and a
    pidfd/start-identity-bound host observation both pass, then recheck child
    identity immediately before release. Missing, early, duplicate, malformed,
    stale, or changed evidence fails closed, and the readiness descriptor must
    not survive credential ingestion or provider exec.
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

- Run-ref confinement profile `run_ref_confinement.v1` (proposed for target 2.38; unimplemented, not copy-safe)
  - Status: proposed and not current admission. Nothing here changes the
    process authority of current commands, providers or `run-ref` children
    stated above. Authority:
    [run-ref confined child environments](../docs/design/workflow_lisp_run_ref_expression_environments.md#isolation-credentials-and-resource-contract)
    (D1, F3 deltas table); security acceptance also requires an independent
    isolation review and the design's F3, F3b-channel and F3b-checkpoint
    gates.
  - The profile is a sibling of `provider_phase_isolation.v1` on the same
    rootless Bubblewrap substrate (descriptor-bound root, cgroup v2
    containment slots, `DurableLaunchReleaseGate`, result broker). It is not
    registered as a provider-isolation backend and never selects, renames,
    weakens or satisfies `provider_phase_isolation.v1`; a request for it
    through that policy refuses as an unsupported backend. No container
    engine, setuid helper or host execution fallback exists.
  - Rootfs: the runtime imports the digest-pinned `:image` at installation
    into a sealed content-addressed snapshot under the snapshot assembly
    rules above, with empty mount points `/workspace`, `/result`, `/tmp`,
    `/run`, `/dev` and `/proc` in its manifest. Image entrypoints never run.
    Each holder launch rehashes the rootfs through a retained descriptor and
    binds that descriptor. Provider executables, `/bin/sh`, `/usr/bin/env`,
    `setsid` and the relay interpreter are image executable pins; no host
    binary is bound, and host `PATH` pins or package-origin checks never
    authorize them.
  - Containment: each holder launch runs in its own transient delegated user
    scope (`Delegate=yes`, `MemoryMax`, `MemorySwapMax=0`, `TasksMax`,
    `CPUQuota`, `OOMPolicy=continue`) around a launcher released only by an
    exact token after the scope's limits and policy read back equal to the
    request and the scope root is verified empty. The scope holds a `holder`
    slot, a `host` slot for host helpers and one slot per leaf. An
    unavailable user manager, refused delegation, a missing controller or a
    read-back mismatch refuses before release with
    `run_ref_environment_unavailable`. The provider-isolation containment
    root and this scope never share a path.
  - Holder: one `bwrap` per child attempt and controller session with user,
    IPC, PID, network, UTS and cgroup namespaces unshared,
    `--disable-userns`, all capabilities dropped, `--clearenv`,
    `--new-session` and `--die-with-parent`; size-bounded tmpfs at
    `/workspace` (`:workspace-mib`), `/tmp` and HOME (256 MiB), `/dev/shm`
    (64 MiB) and `/result` (128 MiB); `/dev` and `/run` read-only; no
    `/sys`; the sanitized `.git` read-only at `/workspace/.git`. The
    in-namespace holder processes hold only `/dev/null`, the two inherited
    unix socketpairs and guest-owned objects. Leaves run serially under the
    image's `setsid` in their own slots; the host trusts only cgroup
    membership, whole-slot quiescence, its deadlines and its own bounded
    reads. A foreign holder-slot member refuses with
    `run_ref_environment_escape_rejected` and kills the scope; a holder
    death fails the pending attempt with `run_ref_environment_lost`.
    Admission records `kernel.yama.ptrace_scope >= 1`.
  - Authority outside the clone: the child's control root (run header,
    checked child artifact, memo, attempt evidence, checkpoint header, holder
    release gate) lives beneath the parent run root, next to
    `run-ref-attempts.jsonl`, outside the clone and every mount and
    descriptor granted to the guest. The guest sees only the workspace
    execution copy, bounded scratch, the result ingress and, for
    `:model-only`, the relay socket. Host `/`, home, parent and peer
    workspaces, the source mirror, credentials, SSH agents, engine sockets
    and orchestration state are absent.
  - Host Git materialization runs with no credential helpers, SSH agent,
    global or system configuration or proxy environment, and leaves no
    alternates, shared mutable objects, worktree links, executable hooks,
    host-bearing remotes or parent links reachable from the clone;
    submodules and LFS stay rejected. Delta collection never runs
    repository-controlled hooks, filters, external diff or configuration.
  - Host reads of candidate-controlled data: the holder tmpfs is read only
    by the checkpoint copier and result import, through one root descriptor
    per mount opened from `/proc/<holder>/root`, validated by holder-slot
    membership and never reopened by path; traversal is component-wise with
    `O_NOFOLLOW` and an `st_dev` pin, regular files and directories only,
    symlink targets as strings, bounded bytes; `st_nlink > 1` is admitted on
    the tmpfs only. Every other host read uses the existing descriptor-rooted
    owner on the host clone after quiescence. Clone files named by
    stable-command tokens, document fills and prompt dependencies are bound
    by content at `started` through that no-follow reader: a symlinked token
    binds its target string and never a host target. Executables, closures
    and interpreters must be image pinned; one that resolves into the clone
    refuses at dispatch before `started` with
    `run_ref_environment_effect_unsupported`.
  - Network: `:none` grants none. `:model-only` keeps the network namespace
    unshared and binds one unix socket to a host-owned inference gateway.
    It admits only qualified provider/model operations toward a fixed upstream,
    with request/response byte limits, an attempt-bound expiring capability,
    a request ceiling and the remaining durable child wall budget. Cancellation,
    expiry, revocation and exhaustion cancel pending local auth and transport
    operations and streams. Token/cost ceilings require endpoint-specific
    enforcement evidence; if installation policy requires an unsupported
    ceiling, admission refuses. Bytes or disconnection do not establish remote
    generation/cost limits, and incomplete usage/cost is UNKNOWN. No arbitrary
    URL, CONNECT, redirects, host tools, filesystem API or credential reads are
    exposed. The image-pinned relay runs in the provider leaf and dies with it;
    capabilities are revoked at attempt stop and excluded from durable artifacts.
    Qualified Codex managed ChatGPT login may be reused only by a private
    persistent pinned native auth owner, with serialized acquisition, initial
    account/origin/routing binding and strict refusal on mismatch or error as
    specified by D7. Native refresh stays native. Authfiles, permanent upstream
    credentials and owner RPC channels never enter the guest; the host owner
    cannot execute candidate coding or tools. Unsupported transports refuse.
  - Enforced resources: CPU, memory, process count, workspace and scratch
    bytes, export bytes, file count and depth, and bounded stdout/stderr; a post-run `du`
    is insufficient. Protected evidence is charged to a separate
    installation-policy evidence allowance, never to `:output-mib`.
    Effective limits and kernel settings are retained in admission evidence.
    Cumulative child wall time includes host-side work and is checked by the
    live controller. The [durable wall-budget rule](state.md#confined-wall-budget-recovery)
    charges open intervals through recovery quiescence, including controller
    downtime and host suspension using fixed `CLOCK_BOOTTIME`; a different
    boot with an open interval refuses resume. This accounting does not
    enforce an autonomous wall deadline while the controller is absent; no
    watchdog is selected. Kernel containment remains in force, and recovery
    must kill and empty every exact boot-bound remnant, including `host`,
    before checkpoint reads or replacement. Ambiguous identity or failed
    quiescence blocks recovery, never authorizes a replacement or FAILED.

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
