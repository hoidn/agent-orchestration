# OMP Integration: Design And Roadmap Extension

## Metadata

- **Title:** OMP integration — provider templates, JSON session transport, prompt scaffolding, multiagent conf presets, and session bridge
- **Status:** implementation candidate; `OMP-I1` tranche 1 selected by the owner; Task 1 F4 is closed with two byte-identical whole executables, so downstream implementation is admitted subject to its own gates
- **Kind:** architecture decision + roadmap extension
- **Owner:** repository owner (decision holder)
- **Created:** 2026-08-14
- **Last material update:** 2026-08-23
- **Related:** extends [`2026-08-14-omp-integration-proposal.md`](2026-08-14-omp-integration-proposal.md); provider spec home [`specs/providers.md`](../../specs/providers.md); Workflow Lisp authoring home [`docs/lisp_workflow_drafting_guide.md`](../lisp_workflow_drafting_guide.md); OMP checkout `~/Documents/oh-my-pi`
- **Implementation target:** `OMP-I1` plus independently activated follow-ons; no frozen-ES changes
- **Upstream source pin:** OMP tag `v17.3.4`, commit `ffd53ff92a6f575d499730475a73460dd7cc2eea`. The 2026-08-21 source-launcher calibration used `/home/ollie/.local/bin/omp` (`omp/17.3.4`, launcher SHA-256 `3fce4b25628064b0cd7bfbc6245ecdada331750ed4b341aca6bd29ba4478aab5`). F4 replaced it with the OMP-built single-file executable admitted at SHA-256 `f1ffead4d40e6d3740cd2400522d967b270dad5d43a80de7e70c509d97f88211`.

## Summary

OMP-I1 adds four pieces:

1. Four public provider templates—`omp`, `omp_no_tools`, `omp_conf`, and `omp_unrestricted_workspace`—plus an internal, tool-free `omp_conf_inference` template. The ambient templates intentionally reproduce ordinary OMP behavior in a trusted workspace. `omp_conf` isolates user/global profile and configuration but deliberately exposes the workflow workspace as an additional root, which pinned OMP also loads for repository context. `omp_no_tools` and `omp_conf_inference` use the admitted neutral configuration without `--add-dir`, so they receive no repository context or workspace tool root.
2. One pinned launch adapter and one `OMP_JSON_STDOUT` codec. The adapter owns whole-binary admission, canonical session placement, positive child-environment construction, conf admission, and post-run observations. The codec owns the OMP JSON event state machine and normalized assistant output.
3. `orchestrator prompt run|import|resume`. `run` materializes an exact prompt asset, derives or accepts one typed return contract, generates an editable `.orc`, and executes it. A verified scaffold rerun uses the same subcommand. `import` turns a persisted primary OMP session into a new scaffold; it does not import child/subagent journals. `resume` rebuilds the recorded non-secret launch envelope, uses current credentials/current ambient configuration where applicable, and forks by default.
4. Target DSL `2.27` adds one generic, fresh-only `:session-artifact <symbol>` clause to `provider-result`. It lowers to the existing `2.10` provider-session step contract and synthesizes the required existing top-level scalar artifact declaration; Executable IR and runtime step forms do not change. OMP-I1 adds six closed, versioned record schemas across conf admission, session links/continuations, and generated scaffolds, but no new runtime state family.

No RPC client, phased OMP driver, per-topology provider class, generated command adapter manifest, in-workflow OMP resume surface, or model-written Workflow Lisp source.

## Problem

The useful path is simple: give OMP a prompt and optional multiagent config, watch it, receive a typed result, and retain a real session. The original proposal made that path pay for per-ensemble templates, a phase protocol, an RPC bridge, and duplicated staging.

Two existing mechanisms already cover most of the need:

- provider-session transports persist normalized metadata and feed run-scoped observation panes;
- OMP persists append-only session JSONL and can reopen or fork it.

The missing work is exact launch ownership, an OMP JSON codec, a small authoring surface for fresh-session publication, and a prompt-to-workflow front door.

## Trust Boundary

Two lanes have different contracts. Mixing them is a defect.

- **Ambient lane (`omp`, `omp_unrestricted_workspace`).** Equivalent to running OMP in the workflow workspace with the operator's normal home, agent directory, project settings, context files, tools, MCP, hooks, and extensions. It is for trusted repositories and trusted operator configuration. Its provenance records the launch and observed session, not a closed capability inventory. It is not called hermetic.
- **Profile-isolated lanes (`omp_no_tools`, `omp_conf`, internal `omp_conf_inference`).** For every attempt, the launch adapter creates fresh temporary `HOME`/XDG/process-cwd/agent-runtime roots and an admitted conf copy. A canonical run-root session directory exists only when the call explicitly requests fresh-session publication; ordinary calls use OMP `--no-session`. The adapter builds the child environment from a positive schema; inherited user/global profile, configuration, runtime-preload, credential variables, and `.env` roots are not copied. The child process's OS cwd and OMP `--cwd` are the same fresh empty directory. `omp_conf` additionally passes the real workflow workspace with OMP `--add-dir`; pinned v17.3.4 loads that root's repository context files into the system prompt as well as exposing it to tools. `omp_no_tools` and `omp_conf_inference` omit `--add-dir` and use `--no-tools`. None is called hermetic: same-UID access remains possible, and `omp_conf` deliberately admits repository context authority.

Neither lane is a general OS sandbox. Ambient lanes retain the operator account's ordinary access. Profile-isolated lanes retain same-UID read, network, and process access, but their launched trees inherit the targeted Landlock write allowlist in X5; they cannot write every path otherwise writable by that account. Parent-captured stdout proves which bytes the child emitted to its pipe; adapter records and file digests are close-time observations under an operator-trusted run root, not hostile-model authorship proofs. Mutable OMP session files are resumable artifacts.

## Decisions

### X1 — One template family, two explicit trust lanes

Registry built-ins share one launch adapter and codec:

- `omp`: ambient, approval mode `write`, stdin prompt;
- `omp_no_tools`: profile-isolated neutral conf, `--no-tools`, approval mode `write`, stdin prompt;
- `omp_conf`: profile-isolated admitted conf, approval mode `write`, stdin prompt;
- `omp_unrestricted_workspace`: ambient, `--yolo`, stdin prompt;
- `omp_conf_inference`: internal profile-isolated neutral conf, `--no-tools`, stdin prompt.

`Internal` is a supported-surface label, not an authorization boundary:
ordinary registry lookup can address `omp_conf_inference`, but it grants no
capability beyond the neutral no-tools lane. The prompt CLI never admits it as
the task-provider selector, and no evidence claim depends on registry secrecy.

Each template's ordinary command is transient: it contains no session placeholder and the adapter passes OMP `--no-session`. `ProviderTemplate.command_metadata_mode: Optional[str]` is a new code-owned transport field, defaulting to `None`; the workflow provider-template mapping does not admit it. OMP registry built-ins set it to `OMP_JSON_STDOUT`, while existing providers remain unchanged. `ProviderExecutor` initializes `ProviderInvocation.metadata_mode` from that field, overrides it from `ProviderSessionSupport` for an explicit session command, and routes either non-null mode through the accumulator in streaming, observed-nonstream, and plain nonstream paths. Persistence/publication still depends only on `session_request`. The existing `ProviderSessionSupport.fresh_command` adds reserved `${PROVIDER_SESSION_DIR}` only for explicit `provider_session: {mode:"fresh"}`. Therefore `:session-artifact` makes persistence visible, while transient OMP still receives codec-validated output/debug metadata without hidden session files.

All templates declare fresh support only. `resume_command=None` and `turn_boundary_resume=False`; OMP-I1 never authors an in-workflow resume. The operator-facing bridge in X8 is outside `ProviderExecutor`.

All five templates use code-owned default model `openai-codex/gpt-5.6-sol`, overridable only through the existing admitted `model` provider parameter/call-policy binding. `omp_conf` reads one documented workflow input, `omp_conf_root`; its code-owned `conf_root` default is `${inputs.omp_conf_root}`, resolved through the existing provider-parameter substitution context. Multiple OMP calls may share that one admitted conf. `omp_no_tools` and the internal inference workflow bind the checked-in `neutral/` conf themselves. Per-call task-conf selection is deferred until a real workflow needs it.

### X2 — One launch adapter owns every non-model invariant

`python -m orchestrator.providers.omp_launch run` is a stable internal command, not a provider framework. Its parser accepts only:

```text
--lane ambient|ambient-unrestricted|no-tools|conf|conf-inference
--model <non-empty OMP model selector>
--conf-root <path>                 # required only for conf; fixed internally for no-tools/inference
--provider-session-dir <path>     # reserved; present only in fresh_command
```

The registry fixes `--lane`; authored provider parameters cannot select it. `--model` is the template's admitted model parameter. For `omp_conf`, the template default `${inputs.omp_conf_root}` supplies `--conf-root` through the existing provider-parameter substitution namespace; the neutral lanes use a code-owned checked-in root and expose no authored override. The adapter accepts no binary path, expected digest/version, approval, cwd, credential, API-key, or generic OMP-flag override. It accepts prompt bytes only on stdin.

The ordinary/fresh command arrays differ only by the final reserved session argument. The workflow executor, which owns `StateManager`, `step_id`, and `visit_count`, resolves a new `StateManager.provider_session_visit_dir(step_id, visit_count)` join key and carries that canonical path through the active session runtime into `ProviderInvocation`. `ProviderExecutor` substitutes reserved `${PROVIDER_SESSION_DIR}` before authored/default/step parameters. After preparation, the workflow executor derives `OmpTransportExpectation` from the actual prepared argv and trusted visit/policy values, then attaches it before execution. Neither provider preparation nor execution reaches back into `StateManager`:

```text
<run-root>/provider_sessions/<safe-step-id>__v<visit-count>/
```

Provider-session state creates the sibling metadata and an empty compatibility transport spool but not the visit directory. OMP execution never appends to that spool and removes it when the visit finalizes; non-OMP transports retain existing behavior. The adapter verifies the parent descriptor, refuses any pre-existing entry, and creates the directory exclusively. No public `session_dir` parameter exists. Without `--provider-session-dir`, the adapter uses `--no-session` and neither requires nor inventories a primary JSONL.

An interrupted fresh visit is never reused or silently deleted. At-least-once recovery advances the existing visit count, creates a distinct new join-key directory, marks or preserves the old visit as interrupted, and excludes it from link resolution. The orphan remains run-owned evidence; a negative recovery fixture proves that a later attempt cannot bind or publish it.

The integration pin is code-owned and platform-specific. Its admitted record contains Linux `x86_64` with AVX2 and selected native target `//:natives-linux-x64-modern`, OMP `17.3.4`, source commit `ffd53ff92a6f575d499730475a73460dd7cc2eea`, exact Bun `1.3.14`, Bazelisk launcher, Bazelisk-resolved Bazel, and Git paths/digests, frozen `bun.lock`, root `Cargo.lock`, `MODULE.bazel`, `MODULE.bazel.lock`, and `.bazelversion` digests, the fixed local build recipe and identifier-minification mode, the Bazel-resolved Rust and C/C++ action-toolchain identities, and the whole single-file executable SHA-256. The artifact is self-built and is not represented as an upstream release binary. F4 must produce byte-identical binaries from two clean source checkouts recreated sequentially at the same recorded canonical absolute root (see the OMP pin section) under that recorded build environment before the digest is admitted; mismatch blocks OMP-I1 rather than weakening the claim. Unsupported platform, architecture, or CPU-target pairs fail closed until independently pinned and tested.

The recorded build environment is positive, not inherited: each clean build
recreates its home/XDG/cache/temp roots at the same recorded absolute paths
under the canonical build root (freshness comes from deleting and recreating
the whole tree, not from distinct pathnames), an exact `PATH`, canonical path
and
SHA-256 for Bun, the Bazelisk launcher actually selected by `build:native`, the
Bazel executable resolved by that launcher, and Git, and only explicitly
admitted locale, certificate, and build variables. Both Bazel action graphs
must select the same configured native target, Rust toolchain label, C/C++
toolchain label, and compiler/linker executable digests. `MODULE.bazel` and
`MODULE.bazel.lock` bind the module sources and checksums; the selected closure
is `rules_rust` 0.71.3 nightly `2026-04-29`, selected as
`@@rules_rust++rust+rust_linux_x86_64__x86_64-unknown-linux-gnu__nightly_tools//:rust_toolchain`,
plus `hermetic_cc_toolchain` 4.2.0 selected as
`@@hermetic_cc_toolchain++toolchains+zig_config//:x86_64-linux-gnu.2.17_cc`.
The root `rust-toolchain.toml` nightly `2026-07-28` and host `rustc`, `cargo`,
`cc`, and `ld` are not selected by this
Bazel recipe and are not producing-toolchain evidence. Parent proxy/registry
settings, `OMP_NATIVE_BUILD_BACKEND`, `OMP_BAZEL_RC`, Bazelisk overrides,
executable overrides, preloads, dynamic-loader variables, compiler/linker
flags or wrappers, Rust/Cargo overrides, and `CROSS_TARGET` are absent before
the recipe runs. Host kernel/libc and certificate stores remain
operator-trusted observations rather than a claim of a hermetic or
independently bootstrapped toolchain.

At launch, the adapter resolves the command name `omp` once from its parent `PATH`, opens the target without following symlinks, requires a regular non-writable file owned by the current effective user or root, hashes and copies the bytes from that one opened descriptor into an exclusive attempt root, closes the source, reopens only the private copy, verifies its digest, and executes that private pathname for both `--version` and the run. The source pathname is never reused for execution. This proves that the executed private file matched the admitted source bytes at the explicit post-copy check; it does not claim Linux executes an already-open source descriptor.

After replacing bracketed values, the child argv is exactly:

```text
ambient:
  <private-omp> -p --mode json --no-title --model <model>
  --approval-mode write <session>

ambient-unrestricted:
  <private-omp> -p --mode json --no-title --model <model>
  --yolo <session>

no-tools:
  <private-omp> -p --mode json --no-title --no-extensions --no-skills
  --no-rules --no-tools --model <model> --approval-mode write
  --cwd <empty-cwd> <session>

conf:
  <private-omp> -p --mode json --no-title --no-extensions --no-skills
  --no-rules --model <model> --approval-mode write
  --cwd <empty-cwd> --add-dir <workflow-workspace> <session>

conf-inference:
  <private-omp> -p --mode json --no-title --no-extensions --no-skills
  --no-rules --no-tools --model <model> --approval-mode write
  --cwd <empty-cwd> <session>

<session>:
  --session-dir <absolute-canonical-visit-dir>  # explicit fresh request
  --no-session                                  # ordinary command
```

There are zero positional prompt arguments. `--config`, `--api-key`, `--resume`, and `--fork` are forbidden. The adapter forwards stdin byte-for-byte, closes child stdin at parent EOF, streams stdout byte-for-byte, and keeps stderr diagnostic-only. The private version probe argv is exactly `[<private-omp>, "--version"]`, with stdin closed and the same lane-specific process cwd and environment as the real child; it has no OMP `--cwd` argument, must emit exactly one UTF-8 line `omp/<pinned-version>` on stdout, emit no stderr, and exit zero. Ambient children inherit the parent environment and use the workflow workspace as process cwd. The `conf` child uses `--add-dir <workflow-workspace>`, which pinned v17.3.4 treats as both a tool root and a repository-context root. `no-tools` and `conf-inference` children use the fresh empty process/OMP cwd without `--add-dir`, so they load neither repository context nor workspace files.

The conf child environment is the versioned closed schema `omp_conf_env.v1`:

- adapter-owned absolute paths beneath the attempt root: `HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME`, `XDG_CACHE_HOME`, and `TMPDIR`; `PI_CODING_AGENT_DIR` is exactly `$HOME/.omp/agent`, and `PI_CONFIG_DIR` is unset, so pinned OMP config/WATCHDOG loading and custom-agent discovery resolve to the same admitted seed;
- adapter-owned `SHELL=/bin/bash`;
- required copied value: `PATH`;
- optional copied values, and no pattern-based extras: `LANG`, `LC_ALL`, `LC_CTYPE`, `TERM`, `COLORTERM`, `NO_COLOR`, `TZ`, `NODE_EXTRA_CA_CERTS`, `SSL_CERT_FILE`, `SSL_CERT_DIR`;
- exactly one credential mechanism in OMP-I1: both non-empty `OMP_AUTH_BROKER_URL` and `OMP_AUTH_BROKER_TOKEN`. `OMP_AUTH_BROKER_URL` must parse as an absolute `http` URL with no userinfo, query, or fragment; its host must be the IP literal `127.0.0.1` or `[::1]`, and its port must be explicit and in `1..65535`. HTTPS, DNS names including `localhost`, wildcard/unspecified/link-local addresses, malformed URLs, or either missing member fail before OMP starts.

No other key enters the child environment. In particular, it excludes `PWD`, every proxy variable (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` and lowercase forms), `PI_CONFIG_FILES`, `PI_CODING_AGENT_SESSION_DIR`, `OMP_PROFILE`, `PI_PROFILE`, `CLAUDE_CONFIG_DIR`, `COPILOT_CUSTOM_INSTRUCTIONS_DIRS`, `NODE_OPTIONS`, `BUN_OPTIONS`, `BUN_PRELOAD`, `LD_*`, `DYLD_*`, `PYTHON*`, and every other `PI_*`/`OMP_*`. Parent credentials such as `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `AZURE_OPENAI_API_KEY`, and `AWS_*` are simply outside the positive schema and are not copied; the implementation does not try to enumerate every possible provider credential name. OMP-I1 does not attempt to discover inherited descriptors, kernel state, or other same-UID processes; that limitation is part of the non-sandbox boundary. The adapter never starts a broker, copies the local credential database, or records the broker token. A missing channel prints the exact `omp auth-broker serve` setup command and fails before the version probe.

The positive schema isolates launch configuration; it does not make the broker
bearer secret from model-facing tools in the `conf` lane. Pinned OMP and its
same-UID shell/read tools can observe the process environment or procfs, so
`omp_conf` is explicitly a trusted, credential-bearing tool lane.
`omp_no_tools` and `omp_conf_inference` disable that model-to-tool path. OMP-I1
claims only that broker values do not enter adapter frames, normalized
metadata, or diagnostic logs; assistant/tool/session output remains an
ordinary credential-bearing surface.

Every source/config/session descriptor is opened with close-on-exec and the child launch uses `close_fds=True` with no `pass_fds`. The child receives only the documented stdin/stdout/stderr pipes; descriptor inheritance is not an unstated credential channel.

The adapter rejects any child line whose decoded JSON object has `type:"orchestrator.omp_launch.v1"`. After the child closes, it verifies the admitted conf/runtime copies and, for a persisted call, binds the stdout id to exactly one `<timestamp>_<id>.jsonl`, inventories descendants/advisors, and snapshots the live tree outside the child-writable directory. It then appends exactly one final frame:

```json
{
  "type": "orchestrator.omp_launch.v1",
  "lane": "ambient|ambient-unrestricted|no-tools|conf|conf-inference",
  "persistence": "none|fresh",
  "binary": {"platform": "linux", "arch": "x86_64", "version": "17.3.4", "sha256": "<64-lower-hex>"},
  "child": {"argv": ["<non-secret strings>"], "cwd": "<absolute>", "env_names": ["<sorted names>"], "exit_code": 0},
  "session": {"id": "<stdout id>", "visit_key": null, "primary_relpath": null, "primary_sha256": null},
  "conf": {"manifest_sha256": null},
  "confinement": null,
  "observed": {"advisor_relpaths": [], "child_relpaths": []}
}
```

For `persistence:"fresh"`, `visit_key`, primary fields, and run-relative observed paths are non-null and agree with the frozen inventory. For a conf lane, `conf.manifest_sha256` is non-null. The real frame contains no secret values. Missing/duplicate session files in a persisted call, binary/version drift, path escape, malformed child protocol, session mismatch, changed admitted resources, or nonzero child exit makes the adapter exit nonzero; an exit-zero transport parse never overrides such a failure.

`confinement` is null for ambient lanes. For every profile-isolated lane it is
the closed object `{"schema_version":"omp_write_confinement.v1",
"landlock_abi":<integer at least 3>,"policy_sha256":"<64-lower-hex>"}`.
The policy digest binds the exact handled filesystem rights and role-labelled
path plus opened-descriptor identities without publishing host paths. A missing,
unsupported, unapplied, or mismatched policy fails the version probe/child and
cannot produce a successful frame.

### X3 — The OMP JSON codec is a pinned state machine

`ProviderSessionMetadataMode.OMP_JSON_STDOUT` selects `OmpJsonStdoutAccumulator` through `create_session_transport_accumulator`. The first accepted fixture is captured from the pinned whole binary and committed. The accumulator is fail-closed for every recognized event and has four ordered states: `awaiting_header → streaming → terminal_seen → frame_seen`; EOF finalizes only from `frame_seen`. `finalize()` is idempotent: an internal `require_terminal=False` observation may return an incomplete snapshot but can neither settle nor weaken the mandatory terminal/frame checks applied by the final `require_terminal=True` call.

Input framing is exact: incremental bytes are decoded as strict UTF-8, split only on LF, and each non-empty line must be one JSON object with a non-empty string `type`. A final non-LF-terminated object is accepted and parsed at EOF; whitespace-only lines are not empty and fail JSON-object validation. The first non-empty object must be the sole OMP `SessionHeader`: `type:"session"`, non-empty strings `id`, RFC 3339 `timestamp`, and absolute `cwd`; accepted optional keys are integer `version`, string `title`, `titleSource` in `auto|user`, string `parentSession` and `providerPromptCacheKey`, plus string arrays `additionalDirectories` and `previousSessionFiles`. Unknown header keys, duplicate header, duplicate JSON keys, non-finite JSON numbers, or conflicting identity fail.

For a recognized outer event, the listed members and types are mandatory and unknown outer members fail. Nested `message`, `messages`, `toolResults`, `telemetry`, and `coverage` payload members are observational opaque JSON except for the explicitly consumed fields below:

- `agent_start` and `turn_start` contain only `type`.
- `tool_execution_start` contains exactly `type`, non-empty string `toolCallId`/`toolName`, any JSON `args`, and optional string `intent`; `tool_execution_update` contains exactly `type`, non-empty string `toolCallId`/`toolName`, any JSON `args`, and any JSON `partialResult`; `tool_execution_end` contains exactly `type`, non-empty string `toolCallId`/`toolName`, any JSON `result`, and optional boolean `isError`.
- `message_start|message_end` contain one object `message`. The start opens exactly one lifecycle identified by its string `role`; the end must close the same role. Overlap, orphan end, role mismatch, or an open lifecycle at terminal/frame/EOF fails. The print-mode projection of `message_update` contains only `type` and object `assistantMessageEvent`—never an outer `message`—and is legal only while an assistant lifecycle is open.
- The printed `assistantMessageEvent` is the pinned compact discriminated union after `printableEvent` removes snapshots: `start` has only `type`; `text_start|thinking_start|toolcall_start` require non-negative integer `contentIndex`; their `_delta` forms additionally require string `delta`; `text_end|thinking_end` require string `content`; `image_end` requires an image object `content`; `toolcall_end` requires a tool-call object `toolCall`; `done` requires only reason `stop|length|toolUse`; `error` requires only reason `error|aborted`. No `partial`, `message`, or `error` snapshot is accepted. Updates never contribute output, usage, or callbacks; an `error` update must be followed by an assistant `message_end` with the same stop reason.
- A closed assistant message requires role `assistant`, non-empty strings `api`, `provider`, and `model`, finite numeric `timestamp`, `stopReason` in `stop|length|toolUse|error|aborted`, array `content`, and complete `Usage`. Text blocks require exactly `type:"text"`, string `text`, and optional string `textSignature`; image blocks require base64 string `data`, non-empty string `mimeType`, and optional `detail` in `auto|low|high|original`; tool-call blocks require non-empty string `id`/`name` and object `arguments`. Other pinned non-text block kinds are accepted but contribute no output. Text blocks are joined with one newline within a message; closed assistant messages are joined with one newline. This is the only authoritative output path and the only assistant-text callback point.
- Complete `Usage` requires finite non-negative numeric `input`, `output`, `cacheRead`, `cacheWrite`, `totalTokens`, and `cost.{input,output,cacheRead,cacheWrite,total}`. Accepted optional finite non-negative fields are `contextTokens`, `premiumRequests`, `reasoningTokens`, `orchestration.{input,cacheRead,output}`, `cttl.{ephemeral5m,ephemeral1h}`, and `server.{webSearch,webFetch}`; unknown usage keys or missing core fields fail. Usage is added exactly once at assistant `message_end`.
- `turn_end` requires object `message` and array `toolResults`; both are observational and never re-add output or usage.
- `agent_end` requires array `messages`, optional boolean `isTerminal`, and optional object `telemetry`/`coverage`. Absent `isTerminal` means true; false is nonterminal and returns to streaming. The first terminal end requires no open lifecycle and marks settlement. The last closed assistant before it must exist, have `stopReason:"stop"`, and contain no tool-call block. Final `length|toolUse|error|aborted`, including `__omp.silent_abort__`, fails. An earlier provider error is recovered only if a later successful assistant closes before settlement.
- After settlement, only pinned late `custom` message start/end pairs, repeated terminal `agent_end`, and unknown observational event types are tolerated; none can add assistant text or usage. Any post-terminal assistant lifecycle fails.
- Unknown event types after the header and before the adapter frame are tolerated as one opaque object and count as events. They cannot open or close a lifecycle, satisfy settlement or the adapter frame, contribute identity/output/usage, invoke callbacks, or enter provider-session metadata. `event_count` is exactly the number of child event objects after the header and before the adapter frame, recognized or unknown; it excludes the header and frame.

This is a behaviorless forward-compatibility envelope, not fail-open protocol
semantics: the codec validates the outer object and string discriminator, then
discards the unknown body. An opaque event cannot make a transcript pass any
predicate that would fail without it. Closed field sets still govern every
recognized event and the adapter frame.

- `orchestrator.omp_launch.v1` must be the sole final non-empty object, after settlement and with no open lifecycle. The workflow executor resolves the active visit directory before `ProviderExecutor.prepare_invocation`. After preparation and before execution, it derives immutable `OmpTransportExpectation` from the actual prepared adapter argv, explicit session request, code-owned policy, and active visit's `step_id`/`visit_count`, then attaches it to `ProviderInvocation`; the OMP accumulator factory requires it. The frame's closed schema, stdout id, lane, persistence mode, visit key, binary pin, session/conf nullability, and run-relative inventory must match that expectation. A child-authored, duplicate, early, malformed, context-free, or mismatched frame fails.

EOF before settlement/frame, any non-empty tail after the frame, zero closed assistant messages, invalid UTF-8/JSON, malformed known events, or violated ordering fails with `provider_session_transport_error`. A nonzero adapter/child exit always fails even when the stream is complete; exit zero never clears a codec error. Stderr never supplies identity, output, or usage. The downstream `assistant_text_callback`/`on_assistant_message` observer runs once for each closed assistant text fragment after that message validates; callback exceptions are swallowed as display failures and do not mutate parse state or change provider success.

One shared terminal-safe display projection is applied at every non-interactive
`ProviderExecutor` stdout/stderr/assistant-text display write and every
`ProviderObservationHandle` append, never in capture, codec, provider-result,
or journal paths. Each byte-stream sink incrementally decodes across chunks;
invalid UTF-8 bytes become visible ASCII `\xNN` escapes. Printable Unicode plus
LF and TAB pass through; every other C0/C1, DEL, ESC, BEL, carriage return, and
non-printable code point becomes an ASCII `\uXXXX`/`\UXXXXXXXX` escape. The
authoritative captured stdout/stderr, provider result, typed workflow output,
and OMP journal retain the original string/bytes. Observation display files and
their finalized transcripts contain only the projection. Raw execution logs
remain sensitive untrusted exact data and must not be rendered to a terminal
without the same projection; neither surface is authentication evidence.

Normalized provider-session metadata is a parent-generated credential-minimized projection containing the header `session_id`, exact event count, ordered per-message provider/model/usage/stop-reason rows, aggregate tokens/cost, final provider/model, and validated adapter frame. It contains no assistant text, image/content block, tool argument, tool result, or opaque event body. Transient calls retain that projection in the provider result's debug record but publish no session artifact; fresh calls additionally persist it in the existing provider-session metadata record. Authoritative assistant text continues through the existing normalized provider-result/output path, not a second metadata copy.

### X4 — Fresh-session publication is explicit Workflow Lisp syntax

Target DSL `2.27` accepts:

```lisp
(provider-result providers.implement
  :prompt prompts.task
  :inputs (...)
  :returns ImplementationSummary
  :session-artifact omp_session)
```

Rules:

- `omp_session` is the exact authored artifact name and resolves as a scalar `String`;
- lowering rejects any existing `context.top_level_artifacts` name before mutating that mapping, then emits both the existing top-level `artifacts.omp_session = {"kind":"scalar","type":"string"}` declaration and existing `provider_session: {"mode":"fresh","publish_artifact":"omp_session"}` block;
- multiple legal root calls use distinct authored names;
- legal only on a direct-root provider result; nested procedure, phase, branch, loop, imported-workflow, and resume placements fail with `provider_result_session_artifact_placement_invalid`;
- `:delivery :phased` and `:materialization-attempts` authoring are rejected with the session-artifact diagnostic because existing provider-session execution is single-attempt and OMP templates do not declare interactive phased support;
- Workflow Lisp provider results have no `:retries` clause; no retry syntax is added. The existing final validator still rejects any externally supplied or synthesized executable provider-session step carrying retries.
- the frontend checks syntax, type, placement, and collision; the final existing `WorkflowValidator._validate_provider_session` checks that the resolved template supports sessions. The only adjacent provider-contract additions are code-owned `command_metadata_mode`, the reserved `${PROVIDER_SESSION_DIR}` template placeholder/substitution path, and the workflow-executor-to-invocation expectation carrier; no new executable step member is introduced.

The clause is justified because session capture must be explicit and the runtime contract already exists. It selects the template's fresh command; omitting it selects the native `--no-session` command. Making every session-capable provider implicitly stateful would be a larger and less visible change.

### X5 — Conf admission is closed and content-addressed

`omp_conf_root` names a source tree. The launch adapter reads it with descriptor-relative no-follow traversal and accepts only regular files and directories. Symlinks, hard-linked duplicates, devices, sockets, FIFOs, path escapes, undecodable names, duplicate canonical paths, and unexpected files fail.

OMP-I1 admits exactly:

```text
config.yml
agent/WATCHDOG.yml       # optional
agent/agents/*.md        # optional regular files, one level only
```

All YAML uses the pinned ordinary safe subset: UTF-8, mappings/sequences/scalars, unique keys, and no custom tags, aliases, anchors, merge keys, or string command indirection. Unknown keys fail rather than falling through to OMP's tolerant loader.

`config.yml` is one closed mapping with these required leaves and no others:

| Key | Admitted value |
| --- | --- |
| `advisor.enabled` | boolean |
| `memory.backend` | literal string `off` |
| `task.maxConcurrency` | integer `1..32` |
| `task.maxRecursionDepth` | integer `0..2` |
| `task.disabledAgents` | exact sorted list `[designer, librarian, reviewer, scout, security-reviewer, sonic, task]` from pinned OMP v17.3.4 |

Each `agent/agents/*.md` has one YAML frontmatter mapping followed by a non-empty UTF-8 instruction body. Required keys are `name` and `description`, both non-empty strings; `name` matches `[a-z][a-z0-9_-]{0,63}` and is unique. Optional keys are:

- `model`: one non-empty pinned OMP model selector; omission inherits the invocation's already-admitted model;
- `tools`: a duplicate-free list drawn only from `read`, `grep`, `glob`, `bash`, `edit`, `write`, `task`, `hub`;
- `spawns`: a duplicate-free list of names declared in the same admitted tree.

No wildcard spawn, output schema, autoload skill, prewalk, advisor, blocking, read-mode, or other frontmatter key is admitted. The adapter lexes the body with the pinned OMP `expandAtImports` boundaries and rejects any candidate matching `(^|[ \t])@([./~A-Za-z0-9_-][^\s]*)` outside fenced or inline code, whether or not the referenced path currently exists. Email-like mid-token `@` and code examples remain legal. Bodies otherwise remain deliberate, unchecked prompt authority and enter the digest byte-for-byte.

Admitted agent names may not collide with that bundled list. Requiring `task.disabledAgents` to equal the complete pinned list prevents the task tool from reaching OMP's bundled agents while leaving only the explicitly admitted custom agent files available; missing, extra, reordered, or renamed entries fail admission.

`agent/WATCHDOG.yml` is the closed mapping `{instructions?, advisors}`. `instructions`, when present, is a non-empty string subject to the same `@`-candidate rejection. `advisors` is a non-empty list of unique closed mappings:

```text
name: non-empty string
model: non-empty pinned selector
tools: duplicate-free subset of [read, grep, glob]
instructions: non-empty string subject to the same @-candidate rejection
enabled: literal true
```

The file is legal only when `advisor.enabled` is true; true requires the file, and false forbids it. An admitted agent may spawn only a named admitted agent and only through OMP's `task` tool; bundled agents are disabled by the exact `task.disabledAgents` value. Every spawned agent/advisor uses the same process, positive child environment, admitted runtime root, model selector rules, and workspace exposure as the primary. A built-in `bash` invocation inherits that environment and current OMP cwd; it does not receive ambient credentials or profile roots. The schema adds no external agent launcher or executable. Because bodies and tools run under the operator account, they can still name or access same-UID paths outside the admitted tree; the adapter does not claim otherwise. Files that would activate skills, extensions, plugins, hooks, MCP, custom tools, prompts, commands, or rules remain absent.

Canonical conf manifest is the closed object
`{"schema_version":"omp_conf_manifest.v1","files":[...]}`. Each ordered file
row has exactly `path`, `size`, `sha256`, and literal `mode:"0644"`. Paths are
normalized UTF-8 POSIX relatives and sorted by encoded path bytes; size is a
non-negative integer; SHA-256 is 64 lowercase hex. Source files must be regular
and have no executable bit; the copy normalizes their mode rather than binding
identity to checkout umask. The manifest's exact UTF-8
`json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`
bytes are its canonical bytes and digest. This `canonical_json` definition is
also used for scaffold naming and identity; admitted inputs contain no floats.

The adapter opens the source root once and copies admitted files through
descriptor-relative, no-follow reads into a fresh pre-launch snapshot. It sets
snapshot directories/files to `0500`/`0400`, verifies content against the
canonical manifest, then seeds `config.yml`, `WATCHDOG.yml`, and `agents/*.md`
under `$HOME/.omp/agent` (also the exact `PI_CODING_AGENT_DIR`) so pinned config
and every spawn-time task-agent discovery read the same bytes. OMP-created
databases/caches live in separate writable XDG data/state/cache roots.

Before either the version probe or child exec in a profile-isolated lane, a
small code-owned launcher requires Linux Landlock ABI 3 or newer, sets
`no_new_privs`, and installs one inherited write allowlist. It handles every
ABI-3 filesystem mutation right; only `XDG_DATA_HOME`, `XDG_STATE_HOME`,
`XDG_CACHE_HOME`, `TMPDIR`, the explicit fresh session directory when present,
and the `conf` lane's admitted workspace are writable. `$HOME`, `$HOME/.omp`,
`XDG_CONFIG_HOME`, the empty process/OMP cwd, and the immutable snapshot are
not writable. Every root is opened no-follow before policy installation; no
writable root may equal or contain the runtime conf, immutable snapshot, or
empty cwd.

The adapter passes the helper a closed role/path list plus expected ABI and
policy digest. The helper reopens each path, recomputes the canonical policy,
and refuses any missing/duplicate/unknown role, wrong lane cardinality, ABI or
digest mismatch, symlink/type change, or target other than the already-private
OMP executable before calling `restrict_self` and `execve`. The restriction is
inherited by OMP, built-in tools, and every spawned descendant and cannot be
relaxed by them. Missing kernel support, rule/setup failure, an
uncreated/non-directory/overlapping root, or a write outside that exact set
fails closed.

At child close the adapter re-hashes the immutable snapshot and runtime seed
and re-reads the source through the still-open root descriptor; any
changed/missing/type-swapped admitted file fails. Runtime manifests record
their actual modes and the confinement policy digest. Landlock prevents a
launched-process transient write → spawn → restore substitution; these
checks also observe unrelated same-UID host mutation, which remains outside
the confidentiality and process-isolation claims.

Checked-in package resources under `orchestrator/omp_assets/confs/` use only that schema. Each has a checked-in canary prompt under `tests/fixtures/omp/presets/<name>/prompt.md` that asks for the topology using its admitted agent names; its expected counts live in a code-owned map keyed by the preset's canonical conf digest, never by caller-supplied path or label.

| Preset | Canary topology | Required close-time observation |
| --- | --- | --- |
| `neutral/` | primary answers without delegation | one settled primary; zero child/advisor journals |
| `advised/` | configured advisor reviews the primary | one settled primary and exactly one settled, non-empty advisor journal; zero child journals |
| `fanout/` | primary dispatches exactly two named agents | one settled primary and exactly two distinct settled child journals; zero advisor journals |
| `peer-team/` | two named agents coordinate through `hub` | fanout counts plus at least one matched successful persisted `hub` call/result |
| `advised-fanout/` | advised primary dispatches exactly two agents | advised plus fanout counts |

The adapter inventories through the frozen primary artifact-tree descriptor after OMP exits and the pinned print-mode advisor drain completes. Each non-empty line in an observed journal must be strict UTF-8, duplicate-key-rejecting JSON object. Predicates are:

- `journal(f)`: the first physical line is the pinned 256-byte `type:"title",v:1` slot (including LF and its validated `pad`), the second object is the sole `type:"session"` header, and every later object is a valid persisted OMP session entry; no malformed/truncated line, later duplicate header/title slot, symlink, non-regular file, or path escape exists;
- `settled(f)`: `journal(f)` holds, at least one `type:"message"` entry has `message.role:"assistant"`, and the last such entry has `stopReason:"stop"` with no content block whose `type` is `toolCall`;
- `advisor(f)`: `f` is a direct child of the primary artifact directory named `__advisor.jsonl` or `__advisor.<slug>.jsonl`, contains at least one non-header entry, and satisfies `settled(f)`;
- `child(f)`: `f` is any other `.jsonl` below the primary artifact directory and contains exactly one `type:"session_init"` entry with a non-empty string `agent`; it must satisfy `settled(f)`;
- `hub(f)`: within one settled primary/child journal, an assistant message contains a `toolCall` block with `name:"hub"` and non-empty `id`, and a later `message.role:"toolResult"` has `toolName:"hub"`, the same `toolCallId`, and `isError:false`.

The stdout header id must select exactly one direct primary `<timestamp>_<id>.jsonl`; that file must satisfy `settled` and is never classified as child/advisor. Every discovered advisor/child journal must satisfy its predicate even when the preset needs fewer; unclassified JSONL files fail. For every child header `cwd` that canonicalizes beneath the pinned OMP isolated-worktree root, the path must be absent at adapter close. A recognized preset digest enforces the table's exact counts; an unrecognized admitted conf enforces primary settlement, validity/settlement of every discovered journal, and worktree cleanup but no topology count. Missing, extra, malformed, unsettled, or ambiguously classified journals and unmatched/failed `hub` results fail the provider call. These are close-time observations, not authorship or provenance proofs.

### X6 — Prompt scaffolding is deterministic after one narrow synthesis call

Generation example:

```bash
python -m orchestrator prompt run \
  --prompt-file task.md \
  --output "an implementation summary with changed files and verification" \
  --provider omp_conf \
  --conf orchestrator/omp_assets/confs/advised
```

`prompt run` has two mutually exclusive argparse modes:

1. **Generate and run:** exactly one of `--prompt TEXT` or `--prompt-file PATH`; required `--provider` is exactly one of `omp`, `omp_no_tools`, `omp_conf`, or `omp_unrestricted_workspace`; optional `--model`; `--conf PATH` is required iff the provider is `omp_conf` and forbidden otherwise; at most one of `--returns JSON` and `--output TEXT`. Internal/non-OMP/unknown providers, duplicate singleton flags, empty strings, and positional extras fail with exit `2` before provider execution.
2. **Verified rerun:** exactly `--scaffold PATH`. It forbids every generation flag above and positional extras. The path must identify the scaffold root, not `run.orc`.

Before any model call or destination creation, generation opens and captures the exact non-empty UTF-8 prompt, selected conf tree, registry template, concrete effective model (the explicit value or the required non-empty code-owned OMP template default), renderer inputs, and contract request. Missing/empty model resolution fails before inference or filesystem writes. Later identity, inference, rendering, and publication use those captured values rather than reopening mutable source paths. `prompt.md` receives the exact prompt bytes; text is never guessed to be a path or rewritten. `omp_conf_inference` remains internal.

Contract modes:

1. neither contract flag → semantic scalar `String`;
2. `--returns <json>` → exact admitted semantic contract;
3. `--output TEXT` → one checked-in package resource, `orchestrator/omp_assets/infer-output-contract.orc`, runs and returns `OutputContractDraft`, a record containing only an ordered non-empty `fields: List[OutputContractField]`, where each field has exactly string `name` and `type`.

`--returns` is strict UTF-8, duplicate-key-rejecting JSON in exactly one shape:

```json
{"mode":"scalar","type":"List[String]"}
```

or:

```json
{"mode":"record","record_name":"Result","fields":[{"name":"summary","type":"String"}]}
```

Scalar objects have exactly `mode,type`. Record objects have exactly `mode,record_name,fields`, at least one field, unique field names, and valid Workflow Lisp identifiers. Canonical type strings are recursively `String`, `Bool`, `Int`, `Float`, `Optional[T]`, `List[T]`, or `Map[String,T]`; whitespace aliases, unknown keys/types, non-string members, excessive nesting beyond 16, and empty records fail.

OMP-I1's natural-language inference mapping is closed: `omp_no_tools|omp_conf → omp_conf_inference` with the checked-in `neutral/` preset. `omp` and `omp_unrestricted_workspace` have no mapping. `--output` with either unmapped task provider fails before a model call or filesystem write. Inference receives the captured task prompt and output request as typed prompt inputs, uses the selected concrete model, profile-isolated positive environment, `--no-tools`, disabled extensions/skills/rules, transient `--no-session`, and no task conf. Its provider extern points only to the internal template. It cannot read or mutate the captured prompt, selected task-provider template, task conf, task provider policy, or destination scaffold. The resulting `OutputContractDraft` is parsed structurally; invalid drafts fail with no repair turn or fallback. Authoritative semantic fields are sorted by field name after duplicate rejection.

Each draft field name and recursively parsed type passes the existing Workflow Lisp identifier/type parser. A deterministic renderer emits only known `defrecord`, workflow-signature, and `:returns` syntax. Model-authored prose and raw source never enter task return guidance; only validated identifiers and admitted canonical types do. The ordinary compiler must derive a contract structurally equal to the normalized semantic contract before the task provider starts. Invalid synthesis fails; there is no widening, repair, retry, or `String` fallback.

`output-contract.json` is the closed `scaffold_output_contract.v1` union:

```json
{
  "schema_version": "scaffold_output_contract.v1",
  "semantic": {
    "mode": "record",
    "record_name": "PromptResult_4f2a1c9d",
    "fields": [
      {"name": "changed_files", "type": "List[String]"},
      {"name": "summary", "type": "String"}
    ]
  },
  "authoring": {
    "mode": "inferred",
    "output_request_sha256": "<64-lower-hex>",
    "provider": "omp_conf_inference",
    "model": "openai-codex/gpt-5.6-sol",
    "session_id": "<non-empty>",
    "usage": {
      "input": 0,
      "output": 0,
      "cacheRead": 0,
      "cacheWrite": 0,
      "totalTokens": 0,
      "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.0}
    }
  }
}
```

`semantic` is exactly the normalized scalar or record shape accepted above. `authoring` is exactly `{mode:"default"}` for default `String`, `{mode:"exact"}` for `--returns`, or the shown inferred shape; usage numbers are finite and non-negative. Unknown keys fail at every level. Authoring provenance is bound by the scaffold manifest but excluded from semantic identity.

### X7 — Generated scaffolds are semantically addressed and non-destructive

Output tree:

```text
workflows/generated/<slug>-<identity-prefix>/
  run.orc
  prompt.md
  prompts.json
  providers.json
  output-contract.json
  scaffold.json
  conf/                    # only for omp_conf
```

Generated manifests are fixed-shape and destination-independent:

```json
{"prompts.task":"prompt.md"}
{"providers.task":"<omp|omp_no_tools|omp_conf|omp_unrestricted_workspace>"}
```
Both manifest files are the canonical JSON encoding of those exact one-key
objects plus one trailing LF; no aliases or additional metadata are emitted.

The string prompt binding is an `asset_file`; existing `WorkflowAssetResolver` resolves it against `run.orc`'s directory, so `prompt.md` is stable before the destination identity exists and needs no evaluated path mechanism. `run.orc` declares only `omp_conf_root String` when the provider is `omp_conf`; otherwise it has no workflow inputs. It applies `prompts.task` with no prompt arguments, pins the concrete model in `:model`, returns the normalized semantic type, and always authors exactly `:session-artifact omp_session`. The prompt CLI supplies only the generated conf path, when needed, through ordinary `--input omp_conf_root=...`.

Name derivation is non-recursive. The renderer version is the literal
`prompt_scaffold_renderer.v1`; changing generated source, manifests, or the
code-owned OMP provider policy requires a version bump. Default `String` and
exact scalar contracts have no record name; exact record mode uses the
operator-supplied validated name. Inferred record mode computes:

```text
record_basis = canonical_json({
  "schema": "prompt_result_name.v1",
  "renderer_version": "prompt_scaffold_renderer.v1",
  "prompt_sha256": <64-lower-hex>,
  "fields": <ordered exact [{"name":...,"type":...}]>
})
record_name = "PromptResult_" + sha256(record_basis).hexdigest()[:8]
```

Only after semantic contract and provider binding are complete does the
generator compute this exact closed object:

```json
{
  "schema": "scaffold_identity.v1",
  "renderer_version": "prompt_scaffold_renderer.v1",
  "prompt_sha256": "<64-lower-hex>",
  "semantic_contract": {"mode": "record", "record_name": "Result", "fields": [{"name": "summary", "type": "String"}]},
  "provider": {
    "extern": "providers.task",
    "registry_name": "omp|omp_no_tools|omp_unrestricted_workspace|omp_conf",
    "concrete_model": "<non-empty-selector>",
    "policy_version": "omp_provider_policy.v1",
    "lane": "ambient|no-tools|ambient-unrestricted|conf",
    "approval_mode": "write|yolo",
    "publishes_fresh_session": true
  },
  "binary": {"platform": "linux", "arch": "x86_64", "version": "17.3.4", "sha256": "<64-lower-hex>"},
  "prompt_externs": {"prompts.task": "prompt.md"},
  "provider_externs": {"providers.task": "<same-registry-name>"},
  "conf_manifest": null
}
```

For profile-isolated task providers, `conf_manifest` is the exact closed
`omp_conf_manifest.v1` object: the captured authored tree for `omp_conf`, or
the code-owned checked-in `neutral/` tree for `omp_no_tools`. It is null for
the ambient lanes. The `omp_provider_policy.v1` table is code-owned and maps
each admitted registry name to its exact lane/approval/session behavior.
Generation and verified rerun both compare the captured template, current
binary pin, and current conf policy to that table before hashing. The identity
is SHA-256 of the canonical JSON bytes above.

The scaffold identity excludes destination path, inference session/usage, timestamps, and itself; the independently derived record name is already part of `semantic_contract`. `identity-prefix` is the first 12 lowercase hex characters. `slug` is the lowercase prompt-file stem, or literal `prompt` for `--prompt`, with non-alphanumerics collapsed to `-`, trimmed, capped at 32 characters, and fallback `prompt`.

`scaffold.json` is the closed `prompt_scaffold.v1` record: `schema_version`, 64-lower-hex `identity`, `renderer_version`, `prompt_sha256`, `semantic_contract_sha256`, closed `provider` and `binary` objects matching the identity basis, nullable `conf_manifest_sha256`, and ordered `files`. Each file row has exactly scaffold-root-relative POSIX `path`, non-negative integer `size`, 64-lower-hex `sha256`, and mode `0644`; rows cover every regular file beneath the scaffold except `scaffold.json` itself, including copied authored conf files, with no duplicates. The verifier recomputes the identity from semantic inputs, refuses any current binary/provider/conf-policy pin mismatch, checks every row against no-follow reads, requires the exact directory set implied by the rows, and rejects extra nodes.

The generator resolves beneath a still-open trusted generated-root descriptor, rejects symlink/special ancestors, takes an exclusive per-identity lock, builds and compiles a complete sibling temporary directory, then publishes with Linux `renameat2(RENAME_NOREPLACE)` relative to the verified parent descriptor. It revalidates parent identity and fsyncs the new entry and parent. There is no replace-semantics fallback and no `--force`.

Any final-path entry that appears at publication loses the no-replace race. Reuse occurs only when the existing scaffold's own manifest, semantic identity, modes, and absence of extra nodes all verify. A repeated inferred generation that reaches the same semantic identity retains the first scaffold's already-bound authoring provenance and discards the new inference observation; provenance never selects executable bytes. Any other mismatch requires operator inspection/removal; the generator never deletes unknown data.

Verified rerun recomputes identity, verifies every file/conf byte and provider binding, then invokes the ordinary compiler/run path with `run.orc`, both extern manifests, and `--input omp_conf_root=<workspace-relative-conf>` only when present. Initial generation uses the same verifier and runner after publication. stdout/exit status are the ordinary run's; the scaffold path is written to stderr. Deliberately editing `run.orc` and invoking bare `orchestrator run ... --provider-externs-file ... --prompt-externs-file ...` is ordinary trusted-source execution and carries no scaffold-integrity claim.

Generation and rerun allocate the run id before execution and exclusively create
the selected `<runs-root>/<run-id>` with descriptor-relative no-follow checks;
a pre-existing run root fails before any provider runs. From the same
descriptor-relative bytes that passed verification, the prompt service creates
`<run-root>/prompt-inputs` as a private snapshot with `0500` directories and
`0400` files. The ordinary state initializer adopts that exact reserved root,
and the compiler, extern loaders, prompt resolver, and conf input receive only
snapshot paths. Compiled provenance, state, and the later link bind those
captured bytes. Mutating or replacing the writable published scaffold after
verification therefore cannot select executed bytes. This prevents workspace
publication races but, like the conf snapshots, is not protection from a
hostile same-UID process that can tamper with run-owned files.

### X8 — Session bridge separates transport evidence, file observations, and live journals

A persisted visit has parent-owned and child-writable surfaces with fixed paths:

```text
<run-root>/provider_sessions/<visit-key>.json
<run-root>/provider_sessions/<visit-key>/                    # live OMP journals
<run-root>/provider_sessions/<visit-key>.snapshot/           # frozen close-time journals
<run-root>/provider_sessions/<visit-key>.conf/               # admitted conf snapshot, profile-isolated lane
<run-root>/provider_sessions/<visit-key>.session-link.json
<run-root>/provider_sessions/<visit-key>.continuations/<n>.json
```

Raw adapter stdout is bounded in process memory only long enough for codec finalization and `ProviderExecutionResult`; OMP-I1 adds no raw-output file and never appends OMP bytes to the existing provider-session transport spool. Any empty compatibility spool created during visit initialization is removed on every finalized OMP success or failure path and is not link evidence; non-OMP behavior is unchanged. The persisted metadata projection contains no child-authored content. Task outputs and explicit OMP session journals necessarily retain model-authored text and must be treated as sensitive operator-owned run data; profile isolation is not a confidentiality boundary against the model or same-UID tools. Snapshot/conf digests record file bytes observed at close. Live JSONL remains a mutable OMP journal. None authenticates authorship against same-account or model-writable state.

After a successful persisted OMP `prompt run`, the prompt CLI asks `StateManager` to publish one no-replace closed `session_link.v1` sibling only after the run result, credential-minimized provider-session metadata, state, scaffold, and observed trees agree. Its exact shape is:

```json
{
  "schema_version": "session_link.v1",
  "run_id": "<non-empty>",
  "step_id": "<non-empty>",
  "visit_key": "<non-empty>",
  "workflow_workspace": "<absolute>",
  "scaffold_relpath": "<workspace-relative-posix>",
  "paths": {
    "state": "<run-relative-posix>",
    "metadata": "<run-relative-posix>",
    "live": "<run-relative-posix>",
    "snapshot": "<run-relative-posix>",
    "conf": "<run-relative-posix-or-null>"
  },
  "session": {"id": "<non-empty>", "primary_basename": "<one-component-jsonl>"},
  "digests": {
    "live_manifest_sha256": "<64-lower-hex>",
    "snapshot_manifest_sha256": "<64-lower-hex>",
    "conf_manifest_sha256": "<64-lower-hex-or-null>",
    "scaffold_manifest_sha256": "<64-lower-hex>",
    "authored_prompt_sha256": "<64-lower-hex>",
    "composed_prompt_sha256": "<64-lower-hex>",
    "source_sha256": "<64-lower-hex>",
    "semantic_contract_sha256": "<64-lower-hex>"
  },
  "provider": {
    "name": "omp|omp_no_tools|omp_unrestricted_workspace|omp_conf",
    "model": "<concrete-selector>",
    "lane": "ambient|no-tools|ambient-unrestricted|conf"
  },
  "scaffold_identity": "<64-lower-hex>",
  "launch": {"argv": ["<non-secret-string>"], "env_names": ["<sorted-unique-name>"]},
  "confinement": null
}
```

Every object is closed. Paths are non-empty normalized POSIX strings with no absolute form or `.`/`..` component except absolute `workflow_workspace`; nullable fields use JSON null, never omission. `primary_basename` is one component ending `.jsonl`. `scaffold_manifest_sha256` hashes exact `scaffold.json` bytes; the live/snapshot/conf values hash their canonical manifests. Source is `run.orc`; semantic contract hashes canonical `output-contract.json.semantic`. The link must agree with run state, the credential-minimized provider-session metadata and adapter frame, scaffold, and the one primary journal before publication. Run-relative paths resolve through the opened run-root descriptor; the scaffold resolves through the recorded workspace descriptor and revalidates completely. The link is observation and consistency evidence under an operator-trusted root, not model-resistant provenance.

Continuation records are a closed append-only chain. Sequence starts at `1`, has no gaps, and `previous_sha256` hashes exact link bytes for record 1 or exact preceding-record bytes thereafter:

```json
{
  "schema_version": "session_continuation.v1",
  "sequence": 1,
  "previous_sha256": "<64-lower-hex>",
  "status": "success|failed",
  "mode": "fork|in_place",
  "source": {
    "session_id": "<non-empty>",
    "primary_basename": "<one-component-jsonl>",
    "journal_sha256": "<64-lower-hex>"
  },
  "result": {
    "session_id": "<non-empty-or-null>",
    "primary_basename": "<one-component-jsonl-or-null>",
    "journal_sha256": "<64-lower-hex-or-null>"
  },
  "started_at": "<RFC3339>",
  "ended_at": "<RFC3339>",
  "child_exit_code": "<integer>",
  "failure": "<stable-code-or-null>",
  "binary": {"platform": "linux", "arch": "x86_64", "version": "17.3.4", "sha256": "<64-lower-hex>"},
  "conf_manifest_sha256": "<64-lower-hex-or-null>",
  "launch": {"argv": ["<non-secret-string>"], "env_names": ["<sorted-unique-name>"]},
  "confinement": null,
  "pre_live_manifest_sha256": "<64-lower-hex>",
  "post_live_manifest_sha256": "<64-lower-hex-or-null>"
}
```

All objects are closed; timestamps, integers, names, and hashes validate as in the link. Success requires `child_exit_code:0`, `failure:null`, all three non-null result fields, and a non-null post-live manifest satisfying the mode predicate below. Failure requires a non-empty stable failure code; all result fields are null. Its child exit is the observed integer (which may be `0` when a postcondition fails), and its post-live manifest is non-null only when the complete live tree was safely inventoried, otherwise null. After any child process starts, the bridge publishes exactly one next record with no-replace semantics even when the child or postcondition fails. Preflight failures start no child and write no record. A successful fork advances the active id/basename; successful in-place keeps them and advances the live manifest. Any malformed, gapped, or failed tail permanently blocks another orchestrator continuation and `prompt import`; append-only history is never repaired or deleted by OMP-I1.

`<run-or-session-id>` resolution is exact under the CLI's configured, already-opened runs root. The argument must be one non-empty basename component—not `.`, `..`, absolute, or containing `/`, `\`, or NUL:

1. an exact `<runs-root>/<arg>/state.json` directory match wins; that run must contain exactly one valid OMP session link and an unblocked continuation chain;
2. otherwise scan valid links and successful fork records for exact active `session_id`;
3. otherwise match their exact active `primary_basename`;
4. zero matches yields `prompt_session_not_found`; multiple matches yields `prompt_session_ambiguous` with only run/visit ids.

Only linked primary journals and successful primary forks enter the lookup index. Child/subagent/advisor ids and basenames never do; prefix matching and arbitrary paths are never delegated to OMP.

#### Forward bridge

The grammar is exactly `orchestrator prompt resume <run-or-session-id> [--in-place]`. Repeated/unknown flags and extra positionals exit `2`. It is a standalone operator operation: no `ProviderExecutor`, provider-session metadata, JSON codec, provider result, template resume command, or runtime resume form. Before locking or launching it requires `os.isatty(0)`, `os.isatty(1)`, and `os.isatty(2)` all to be true, then inherits those three unchanged streams for OMP's interactive UI.

Under an exclusive per-session lock, the bridge opens the link, contiguous chain, state, scaffold, and active live journal with descriptor-relative no-follow checks; validates the exact active id and latest live manifest; refuses a scaffold or link whose binary pin differs from the current code-owned pin; copies/re-verifies that pinned whole binary; and prints argv plus environment names to stderr. Ambient sessions use the current ambient environment/configuration and recorded workspace process cwd. Profile-isolated sessions reconstruct `omp_conf_env.v1` with the current broker pair and a verified copy of the frozen conf snapshot, never the original `omp_conf_root`; they use a new empty process/OMP cwd plus recorded workspace `--add-dir`.

The link and each continuation use null `confinement` for ambient lanes and the
same closed ABI/policy-digest object as X2 for profile-isolated lanes. The
profile bridge executes through the Task 5 Landlock helper: the fresh runtime
copy of frozen conf remains outside the write allowlist; XDG data/state/cache,
temp, and the live session directory are writable; only `conf` additionally
admits the recorded workspace.
The policy is inherited by every interactive descendant. Setup or identity
failure starts no OMP child.

After replacing bracketed values, interactive argv is exactly:

```text
ambient:
  <private-omp> --no-title --model <recorded-model> --approval-mode write
  --session-dir <live-dir> <--fork|--resume> <full-id>

ambient-unrestricted:
  <private-omp> --no-title --model <recorded-model> --yolo
  --session-dir <live-dir> <--fork|--resume> <full-id>

no-tools:
  <private-omp> --no-title --no-extensions --no-skills --no-rules --no-tools
  --model <recorded-model> --approval-mode write --cwd <empty-cwd>
  --session-dir <live-dir>
  <--fork|--resume> <full-id>

conf:
  <private-omp> --no-title --no-extensions --no-skills --no-rules
  --model <recorded-model> --approval-mode write --cwd <empty-cwd>
  --add-dir <recorded-workflow-workspace> --session-dir <live-dir>
  <--fork|--resume> <full-id>
```

The choice token is `--fork` by default and `--resume` only for `--in-place`.
There are no positionals or other flags. The exact X2 version probe runs first
with the reconstructed lane environment and process cwd.

Fork success requires the source journal byte-identical, exactly one new direct
primary JSONL, a valid title-slot/header/graph, a new header id, and
`parentSession` exactly the source id. In-place success requires no new primary
and the same header id/basename. It validates the fixed 256-byte title slot
separately: the slot may remain identical or become one valid pinned title-slot
encoding. All bytes after that slot must preserve the complete pre-resume body
as an exact prefix and add at least one complete physical record extending the
prior graph. Truncation, body replacement/reordering, malformed title update,
or title-slot-plus-history rewrite fails even when the resulting journal is
otherwise valid. Both modes require a changed live manifest and reject
extra/type-swapped files and changed scaffold/conf/binary inputs. The bridge
then publishes the continuation record above. Direct ambient
`omp --session-dir <live-dir> --resume <id>` remains an operator escape hatch,
but its unrecorded digest drift makes later orchestrator continuation refuse.

#### Reverse bridge

The grammar is exactly `orchestrator prompt import <run-or-session-id>` plus one of:

1. **New contract:** required `--provider` is exactly one of `omp`, `omp_no_tools`, `omp_unrestricted_workspace`, or `omp_conf`; optional `--model`; `--conf` required iff `omp_conf`; and at most one of `--returns`/`--output`;
2. **Reuse:** sole mode flag `--reuse-run-contract`, forbidding every provider/model/conf/contract flag.

Unknown/repeated flags, extra positionals, and internal/non-OMP providers exit `2`. Resolution returns only the active linked primary journal from an unblocked chain. The importer snapshots that one file with the same descriptor/no-follow/read-race checks; child, subagent, and advisor import is deliberately outside OMP-I1.

The pinned physical parser requires the first record to be the validated 256-byte title slot and the second to be the sole matching session header; neither participates in the branch graph. Every later object must be one recognized pinned `SessionEntry` type—`message`, `thinking_level_change`, `model_change`, `service_tier_change`, `compaction`, `branch_summary`, `custom`, `custom_message`, `label`, `title_change`, `ttsr_injection`, `session_init`, `mode_change`, `credential_pin`, or `reset_boundary`—with a unique non-empty string `id`, null-or-string `parentId`, and RFC3339 `timestamp`; unknown types fail. There is exactly one null-parent root, every parent precedes its child, and no cycle exists. The last entry in file order is the active leaf; its unique parent chain is the active branch. That branch must contain no `session_init` with an `agent` field. The source prompt is the first `type:"message"` whose `message.role` is `user` on that branch before its first assistant message. String content is used byte-for-byte. Array content must be non-empty and contain only closed text blocks with `type:"text"`, string `text`, and optional string `textSignature`; their `text` values are joined in order with exactly one `\n` and no added trailing newline. Missing/empty, image-bearing, post-assistant-only, unknown-entry, or otherwise malformed/ambiguous journals fail.

Without reuse, that extracted text is the new authored prompt and generation uses the selected new contract/provider. With reuse, the extracted composed message bytes must match the link's `composed_prompt_sha256`; prompt, semantic contract, conf, provider, and model come only from the fully verified source scaffold. This prevents compiler guidance from being appended twice and reuses the same semantic scaffold identity. Provider/model/usage fields in journals remain observations. Import never creates a provider-result bundle or imports child journals.

## Contracts And Interfaces

### Orchestrator

- `orchestrator/providers/types.py`
  - add `ProviderTemplate.command_metadata_mode`,
    `ProviderSessionMetadataMode.OMP_JSON_STDOUT`, immutable
    `OmpTransportExpectation`, and the trusted visit/expectation invocation
    carriers;
- `orchestrator/providers/omp_transport.py` and
  `orchestrator/providers/session_transport.py`
  - own `OmpJsonStdoutAccumulator` and add one expectation-requiring factory
    selection without expanding the existing Codex codec module past its current
    responsibility;
- `orchestrator/providers/omp_conf.py`
  - own the closed environment/YAML/frontmatter admission and canonical conf manifests;
- `orchestrator/providers/omp_session.py`
  - own pinned title-slot/session-journal parsing, settlement/topology predicates, and live/snapshot manifests shared by launch and bridge;
- `orchestrator/providers/omp_launch.py`
  - remain a thin `run` adapter around whole-binary admission, the three helpers above, child I/O, and final-frame emission;
- `orchestrator/providers/omp_templates.py`, `orchestrator/providers/registry.py`, and `orchestrator/providers/executor.py`
  - define/load the four public built-ins plus internal `omp_conf_inference`, attach transport for declared ordinary/session modes, resolve reserved `${PROVIDER_SESSION_DIR}` only for explicit fresh requests, and persist codec metadata;
- `orchestrator/_common/io_atomic.py`
  - expose the existing Linux descriptor-relative no-replace rename once and migrate its two current private copies before scaffold publication reuses it;
- `orchestrator/state.py`
  - add the canonical visit-directory join and generic no-replace sidecar byte I/O under the existing run root;
- Workflow Lisp target `2.27`
  - add `:session-artifact` to `ProviderResultExpr`, traversal/typecheck/lowering, feature gates, diagnostics, specs, and facade exports;
- `orchestrator/prompt_contract.py` and `orchestrator/prompt_scaffold.py`
  - separate strict contract/source rendering from capture, identity/manifest verification, and no-replace scaffold publication;
- `orchestrator/prompt_session.py` and `orchestrator/prompt_resume.py`
  - separate closed link/index/import logic from standalone interactive fork/resume reconstruction;
- `orchestrator/cli/main.py` and thin `orchestrator/cli/commands/prompt.py`
  - expose the closed `prompt run|import|resume` grammars and delegate to those services;
- `orchestrator/omp_assets/` and `pyproject.toml`
  - package the inference workflow plus neutral/advised/fanout/peer-team/advised-fanout conf resources for source and installed-wheel execution;
- one checked-in output-contract inference workflow, five checked-in conf presets, and their canary prompts.

No new Executable IR member, state family, runtime step kind, provider retry behavior, workflow-level resume form, or implicit persistent session.

### OMP pin

Production invocation supports only the OMP upstream build's single-file
executable. The owner-authorized build-determinism repair uses two sequential
fresh recreations at the recorded canonical root, each detached at commit
`ffd53ff92a6f575d499730475a73460dd7cc2eea`. Each clone first applies the
code-owned `orchestrator/providers/omp_native_archive.patch` with SHA-256
`a5bb53ab92814423139518fc535493bcdb27ee8a9350b8d93801dabafb23c375`;
the only changed upstream file is
`packages/natives/scripts/embed-native.ts`, whose patched SHA-256 is
`747221981bb2d9441e7a581871c73eb6ccb3f2f1eed063b80d45fe4043f347f1`.
The recipe then runs exactly `bun install --frozen-lockfile`,
`bun run build:native -- -- -- --jobs=1 --spawn_strategy=local`, a pinned-Bun
`node:fs` check that requires the installed native addon to be a regular
non-symlink and sets/verifies its mtime at Unix epoch 0, and
`bun --cwd=packages/coding-agent run build`. Local Bazel execution removes
variable `processwrapper-sandbox/<counter>` prefixes from compile-time paths.
The overlay reuses OMP's existing stats-bundle tar normalizer to zero each
native-archive member mtime and recompute its checksum before deterministic
gzip; normalizing the source file alone is insufficient because Bun.Archive
timestamps `Uint8Array` entries from wall clock. The three standalone `--`
tokens are the verified Bun 1.3.14 forwarding: outer and inner `bun run` each
consume one, and one literal `--` reaches `scripts/bazel-natives.ts`.
The build uses the exact positive
`PATH=/home/ollie/.bun/bin:/home/ollie/.local/opt/omp-i1-tools:/usr/bin`,
with `OMP_NATIVE_BUILD_BACKEND`, `OMP_BAZEL_RC`, `CROSS_TARGET`, and
`BUN_COMPILE_EXECUTABLE_PATH` absent and `minifyIdentifiers:false`. The
candidate Linux `x86_64` AVX2 build record contains `bazel_jobs="1"`,
`bazel_spawn_strategy="local"`, `native_addon_mtime_ns=0`, the archive-overlay
digest, Bun `1.3.14`
(`sha256:9fd36f87e4b90b07632b987a2e4ec81ca15a62c81bf983190cea6d715be2ad74`),
Bazelisk `1.29.0` Linux amd64
(`sha256:5a408715e932c0250d28bd84555f12edbf70117de42f9181691c736eacc4a992`)
driving `.bazelversion` `9.2.0`, selected target
`//:natives-linux-x64-modern`, `rules_rust` 0.71.3 nightly `2026-04-29`,
`@@rules_rust++rust+rust_linux_x86_64__x86_64-unknown-linux-gnu__nightly_tools//:rust_toolchain`,
and
`@@hermetic_cc_toolchain++toolchains+zig_config//:x86_64-linux-gnu.2.17_cc`
C/C++ toolchain label, plus actual compiler/linker executable digests from
both action graphs,
trusted host runtime facts, and the source locks below. No observation is
admitted until two whole outputs compare byte-for-byte.

Both builds use the same closed 12-variable positive environment schema,
including the fixed `OMP_I1_POSITIVE_ENV=1` recipe sentinel, with
home/cache/temp roots recreated at the same recorded absolute paths under the
canonical build root. The captured `env.txt` also contains Bash-injected
`PWD`, `SHLVL`, and `_`; those shell artifacts are not recipe inputs and are
excluded from the pin. Freshness comes from deleting and recreating the whole
tree between the sequential builds, not from distinct pathnames. Any future
admitted pin must record the resolved path and SHA-256
of Bun, the PATH-selected Bazelisk launcher, that launcher's resolved Bazel
binary, and Git; the canonical Bazel action-toolchain labels and executable
digests; and identical normalized closure records from both builds.
A changed launcher path/digest, module lock, selected target,
toolchain label/digest, or planted parent override fails before admission. The
root `rust-toolchain.toml` and host Rust/C/C++ tools are explicitly unused by
this recipe. Byte-identical outputs establish reproducibility only within that
recorded operator-trusted Linux, Bazel-module, and network/package-lock
boundary, not an independently bootstrapped supply chain.

```text
bun.lock          da59664f5956518e0b8fe66472c5de79a14f88a9a016c075308b815bd5c74f76   (declared/unchanged)
Cargo.lock        ad471d6b6cc10d96d87fb259fd7ba5287eb2262a581b69ec30b5a01879f75f8b   (declared/unchanged; crate_universe input)
Cargo.toml        8ff17fda5daa014fefa536c347f3060d9fa159719665e31ac96d560566899bdb   (declared/unchanged; crate_universe input)
MODULE.bazel      7eba8ce12e97c47f3851381c35cc781fafa0b18e9ae2ba075a31d50bf6632ef9   (declared/unchanged)
MODULE.bazel.lock 0060efc6e59203c4395a92b971859e6e51c2cef8a94fc8bf7443f9a003e9e2c9   (declared/committed source identity; every no-local clone MUST match before build)
MODULE.bazel.lock 037601949bfb583a6e301589698894df301acfe82e858b6e9619575a864ca1ed   (effective, predeclared post-resolution identity)
.bazelversion     1b9487d55bea47fea50d226cc9c53bc548877ad2a318bac8fbc8b320f429e5c5   (declared/unchanged)
```

`MODULE.bazel.lock` has two admitted identities, both bound by the pin. The
declared identity `0060efc6…` is the committed source lock at `ffd53ff9` and
must be present in each no-local clone before the recipe runs. The effective
identity `03760194…` is the deterministic post-resolution lock: the v17.3.4
release commit changed `Cargo.toml`/`Cargo.lock` (the crate_universe
extension's recorded inputs move from parent-state digests `9c98f2e7…`/
`00801985…` to `8ff17fda…`/`ad471d6b…`) but omitted regenerating
`MODULE.bazel.lock`, so Bazel 9.2.0 regenerates the crate_universe extension
content from the pinned manifests and rewrites the lock. The recorded
normalized delta is confined to that extension: the generated repos move
`pi-shell-17.3.3 → 17.3.4` and `pkg-config-0.3.33 → 0.3.34`, the generated
`crates`/`crates.bzl` content updates accordingly, and the toolchain-pinning
sections (`registryFileHashes`, `facts`, `factsVersions`,
`selectedYankedVersions`, `lockFileVersion` 28) are unchanged. This is a
narrowly documented exception for the verified v17.3.4 release omission, not
a generic lock-rewrite allowance: both acceptance builds must start at the
declared identity, run the identical recipe, end at the predeclared effective
identity, and produce byte-identical effective lock bytes, normalized lock
delta, Bazel action closures, and binaries; any other rewrite, delta, or
output fails F4. The official checkout remains clean; only the disposable
clones undergo this one expected derivation.

F4's byte-identity criterion is measured at one recorded canonical absolute
build root: the two acceptance builds run sequentially at
`/home/ollie/.cache/omp-i1/canonical`, with the entire checkout, HOME, XDG
cache/config/data/state, and temp tree deleted and recreated from the pinned
commit `ffd53ff9` between the builds. The canonical path is an explicit
admitted build input (it is embedded in the addon's `.rodata` string
constants via `__FILE__`/`env!("CARGO_MANIFEST_DIR")` paths); any future
reproducibility claim is limited to the recorded canonical root and positive
environment, not arbitrary checkout paths. The third attempted native recipe ran
serialized (`bun run build:native -- -- -- --jobs=1`). The addon embeds
per-execution `processwrapper-sandbox` instance numbers in `.rodata`; one Bazel
job made those numbers uniform within each build but did not make them repeat
across separate invocations. Bun's embedded-addon archive also records the
built `.node` mtime. The two serialized acceptance outputs therefore still
differed despite byte-identical effective locks, lock deltas, normalized action
closures, and other recorded inputs.

The fourth recipe added `--spawn_strategy=local` and normalized the copied
addon's filesystem mtime to epoch 0. Its first clean build proved the addon no
longer contained a `processwrapper-sandbox/` path and had `mtime_ns == 0`, but
the extracted archive member still carried wall-clock mtime: Bun.Archive
ignores the source timestamp for `Uint8Array` entries. That fourth attempt was
therefore diagnostic only and is not an acceptance build.

The fifth recipe retained the canonical-root wipe/recreate procedure,
`--jobs=1`, local spawn execution, pre-bundle addon checks, exact action-closure
checks, and whole-file comparison, while applying the narrowly audited
native-archive overlay described above. Both clean overlay builds passed:
the 966-action raw and normalized closures were byte-identical at
`5e088c3d1bb92bd7e4b967c1749125dbcf083ff493cf8fd82ffea59832111b43`;
the pre-bundle and embedded native addons were byte-identical at
`0e1db29a3e8205982e44e4f805a8ad7b3e9ab738a3c11340a1106d1d7cfb20c9`
with mtime 0; and both 153,254,016-byte `dist/omp` outputs reported
`omp/17.3.4` and matched whole-file at
`f1ffead4d40e6d3740cd2400522d967b270dad5d43a80de7e70c509d97f88211`.
This closes F4 without artifact normalization or a digest exception. The
canonical-root formulation supersedes the earlier two-clones-at-distinct-paths
formulation without weakening the whole-file criterion.

The two `packages/coding-agent/dist/omp` files are byte-identical, and their
common SHA-256 is admitted into the code-owned integration pin and copied into
scaffold/link identities. Any future closure hash, tool version, build output,
or `omp --version` mismatch blocks the tranche. The adapter hashes and copies
from one no-follow source descriptor, then reopens, re-hashes, and executes
only the private copy. Source launchers and npm trees are calibration inputs,
while the whole executable digest admits what runs.

The implementation binds behavior to:

- fresh stdin flags `-p`, `--mode json`, `--no-session|--session-dir`, `--cwd`, `--add-dir`, `--model`, `--approval-mode`, `--yolo`, `--no-tools`, `--no-extensions`, `--no-skills`, `--no-rules`, `--no-title`;
- standalone interactive bridge flags `--session-dir`, `--resume`, and `--fork`;
- the absence of `--config`, `--api-key`, positionals, and profile flags from provider launches;
- `SessionHeader`, `SessionMessageEntry`, `SessionInitEntry`, pinned print events, advisor transcripts, task/subagent layout, and the exact `Usage` schema in X3.

A source/tag bump requires a new single-file build/digest, fixture recapture, environment/conf schema review, codec/bridge compatibility review, and all preset canaries.

## Deferred Declarative OMP Capability Loading (`OMP-I2`)

OMP-I2 is approved only for lower-priority roadmap tracking. It cannot start before OMP-I1 closes and a separate owner activation names a consumer.

The authored boundary remains a library value, not new grammar:

```lisp
(record OmpCapabilitySet
  :skills (list "repo-navigation" "systematic-debugging")
  :extensions (list "safe-shell"))
```

A checked-in, content-addressed capability lock would resolve logical ids. Skills and executable extensions require separate admission rules, requested/loaded inventories, exact digest matching, empty ambient inventory, subagent non-widening, and no network/package mutation. OMP-I2 requires an OMP-owned loaded-capability inventory or equivalent executable evidence; canary absence alone is not proof. Plugins remain distribution containers, never directly selected capabilities.

## Feasibility Gates

These are implementation task-zero gates. The happy-path calibrations below ground the selected seams; permanent negative fixtures and full canaries remain gates:

- **F1 — transient and persisted placement:** a real pinned-binary transient run emits one header and no JSONL; an explicit fresh run emits one header id and exactly one matching primary JSONL under the canonical visit directory; a standalone full-id fork creates one child header with `parentSession` and leaves the source unchanged.
- **F2 — JSON protocol:** captured header/update/end/turn/agent/late-advisor fixtures close the exact X3 state machine, including complete usage, recovered versus final failure, absent/false/true `isTerminal`, adapter-frame ordering, EOF, callback failure, and nonzero-exit composition.
- **F3 — profile-isolated conf boundary:** the child and version probe use the same empty process cwd, exact `omp_conf_env.v1` environment, and inherited `omp_write_confinement.v1` Landlock policy; the child uses that directory as OMP `--cwd`; `$HOME/.omp/agent` is exactly `PI_CODING_AGENT_DIR`; and the closed YAML/frontmatter schemas accept only requested preset bytes. The policy requires ABI 3 or newer, makes the admitted runtime conf immutable to OMP and every descendant for their full lifetime, and permits writes only to the role-labelled XDG data/state/cache, temp, optional live-session, and conf-workspace roots. Direct and spawned write/replace/create/rename plus restore attempts against conf fail while writes to every admitted root succeed. Planted workflow/ancestor/user `.env`, excluded environment keys, ambient user/global `.omp`/`.claude`, bundled agents, skills, extensions, custom tools, MCP, prompts, commands, rules, and WATCHDOG canaries are absent. `no-tools` and `conf-inference` omit `--add-dir` and workspace write authority and do not observe a repository `AGENTS.md` marker or workspace file. `conf` deliberately uses `--add-dir`: it must observe the marker as repository context, read a directly named workspace file, and may write that workspace. This proves the pinned process/config/context and child-lifetime write-confinement envelope, not a general OS sandbox, model-confidentiality boundary, or same-UID host-process secrecy.
- **F4 — whole-binary admission:** both clean builds use the recorded positive environment, pinned source/module-lock digests, `linux-x64-modern` target, and identical Bazel action-toolchain closure records and are byte-identical; wrong platform/AVX2 target, writable/wrong-owner source binaries, wrong launcher/toolchain/output digest or version, stale scaffold pin, planted parent build override, and source-path substitution fail before the first provider request; the correct descriptor-copied private executable records one matching digest/version.
- **F5 — multiagent observation:** neutral, advised, fanout, peer-team, and advised-fanout canaries satisfy the exact `journal|settled|advisor|child|hub` predicates and counts in X5; every discovered journal settles and every recorded isolated worktree path is gone at close. These are behavioral observations, not adversarial provenance proofs.
- **F6 — approval mode:** `write` completes the ordinary worker fixture; `--yolo` is confined to the explicitly named unrestricted template.
- **F7 — bridge:** exact run/session/basename lookup rejects zero/multiple/prefix/child matches; a TTY fork and explicit in-place resume satisfy their source/destination observations; primary import extracts the active-branch first user message; child/advisor import is unreachable; malformed graphs, failed chains, and untrusted contract reuse fail.
- **F8 — output inference:** tool-free neutral-conf inference produces admitted field/type drafts, rejects invalid names/types and unmapped task providers, cannot mutate captured task-authority inputs, and compiles a structurally equal task return contract.

A failed gate blocks only the feature that depends on it. F3 failure blocks `omp_no_tools`, `omp_conf`, inference, and all presets, not ambient templates. F1/F2/F4 failure blocks every OMP provider in OMP-I1.

Calibration on 2026-08-21 against the pinned source launcher:

- `omp -p --mode json --no-session` emitted one header, update/end pairs, repeated `turn_end`/`agent_end` messages, authoritative usage only at `message_end`, and terminal `agent_end`; extracting only assistant `message_end` produced `OK` once.
- `--session-dir <empty-root>` emitted session id `01a0262f-98ec-7000-a70c-4f75936c5db3` and persisted exactly one matching primary JSONL. Its first two entries were padded `title` then `session`; the first originating task was the first primary-branch user `message`. `--fork <full-id>` emitted a new id with `parentSession` equal to the source id and preserved the source journal.
- A launch with fresh `HOME`, XDG roots, `PI_CODING_AGENT_DIR`, process/OMP cwd, empty `config.yml`, disabled extensions/skills/rules, real repository `--add-dir`, and a loopback OMP auth broker completed as `ISOLATED_OK`; its session tree had one primary JSONL and no ambient `__advisor.jsonl`, while the ambient control produced an advisor transcript. This calibrated the root/flag/broker shape only; it did not close the production environment/conf schemas in F3.
- The host Landlock version query reported ABI `8`. A localized ABI-3 policy probe made direct and inherited-grandchild overwrites outside its sole writable root fail with `EPERM` while both processes wrote successfully inside that root. This calibrates the selected kernel primitive only; the production helper, closed role/digest protocol, and full direct/spawn/restore matrix remain F3 gates.
- `omp --version` reported `17.3.4` for the source launcher. This does not close F4; F4 requires a compiled whole-executable digest plus the descriptor-copy/private-digest execution checks.

Calibration on 2026-08-23 against the admitted whole binary:

- `omp -p --mode json --no-session --no-tools --model openai-codex/gpt-5.6-sol`
  with prompt `Reply exactly OK` and closed stdin emitted one header and a
  complete successful JSONL lifecycle with assistant text `OK` and no journal.
- The equivalent explicit `--session-dir <empty-root>` call emitted one header
  and persisted exactly one matching primary JSONL. Unmodified stdout and
  primary fixtures are checked in under `tests/fixtures/omp/protocol/`.
- The installed regular current-user mode-`0555` file reports `omp/17.3.4` and
  hashes `f1ffead4d40e6d3740cd2400522d967b270dad5d43a80de7e70c509d97f88211`;
  this closes F4. Descriptor-copy launch negatives remain Task 3 acceptance.

## Roadmap

`OMP-I1` is selected after frozen-ES hand-back and consists of:

1. reproduce and pin the whole OMP executable from the recorded positive build environment, capture pinned protocol/session fixtures, and close F1/F2/F4;
2. implement the transport expectation/codec and launch adapter, including canonical visit allocation, interrupted-visit recovery, positive environment schema, binary descriptor copy, and focused provider-session tests;
3. define the four public templates plus internal inference template and verify every streaming/nonstream metadata route;
4. implement target DSL `2.27` `:session-artifact`, including scalar artifact synthesis and compile/lower/runtime coverage;
5. implement conf admission, inherited Landlock write confinement, bundled-agent disablement, and presets; close F3/F5/F6;
6. implement output-contract normalization, tool-free inference workflow, no-clobber semantically addressed scaffolding, binary-bound verified rerun, and close F8;
7. implement run-state-consistent import/resume and close F7;
8. run one real advised-fanout prompt-to-workflow trial, then update specs, capability status, docs routing, and roadmap state.

Independently gated follow-ons:

- `OMP-I2`: declarative skill/extension selection;
- RPC/mid-turn steering: only after a named consumer and a new design;
- per-call conf binding: only after a workflow needs multiple distinct OMP confs;
- richer per-agent cost accounting: only if pinned session files cannot supply sufficient facts.

No OMP item gates ES, E3, E-program closure, the P-series, or unrelated roadmap work.

## Invariants And Failure Modes

1. The task prompt's exact bytes have one owner: `prompt.md`. Ambient lanes load ordinary repository context. The `conf` lane loads context from its explicit `--add-dir` workspace; `no-tools` and `conf-inference` omit that root and receive neither repository context nor workspace tools.
2. Ordinary OMP calls are transient `--no-session`; explicit fresh publication receives only the canonical provider-session visit directory, never an authored path, and interrupted visits are never reused.
3. The ambient lane is declared ambient; profile isolation closes user/global profile and configuration discovery. Only `conf` deliberately admits repository context and a workspace tool root.
4. A profile-isolated child and version probe use the same empty process cwd;
   the child also uses it as OMP `--cwd`; `omp_conf_env.v1` is exhaustive,
   binds `PI_CODING_AGENT_DIR` to `$HOME/.omp/agent`, and is paired with the
   exact inherited `omp_write_confinement.v1` policy.
5. A conf digest identifies exact bytes observed at declared points, not
   hostile-model authorship; the launched process tree cannot mutate the
   runtime conf bytes between those points.
6. A session id publishes only after stdout identity, terminal settlement, adapter frame, and one observed primary file agree.
7. Parent-captured transport proves emitted bytes; live and frozen OMP file bytes remain untrusted local observations.
8. A run link supplies consistency under an operator-trusted run root, not cryptographic authentication.
9. Structured return guidance comes from compiler-accepted source; inference is tool-free and model-authored raw source is never executed.
10. Scaffold publication is atomic no-replace; the binary pin is part of scaffold identity; verified rerun/import refuse pin drift.
11. OMP subagents/advisors settle inside one provider step and have no second orc result channel; their files are observational.
12. Operator resume/fork is an interactive bridge outside provider/runtime resume contracts and never rewrites prior transport or frozen evidence.

Representative failures:

- build-closure, platform/AVX2 target, module-lock, or action-toolchain mismatch, non-reproducible output, whole-binary source ownership/mode, digest/version, descriptor-copy, private-copy digest, or stale scaffold pin → pre-request failure;
- absent/author-overridden fresh visit binding → validation failure; a transient call has no binding by design;
- conf process environment/cwd outside `omp_conf_env.v1`, absent/mismatched Landlock policy, write outside an admitted root, or an ambient-profile canary observation → F3 failure;
- missing/duplicate/conflicting stdout identity or failed final assistant → transport failure, no publication;
- syntactically terminal stream plus nonzero child exit → provider failure;
- missing/duplicate/mismatched primary file on a persisted call → provider failure;
- conf symlink, special file, unknown path/key, escape, or observed mutation → admission/provider failure;
- generated target race/mismatch/extra node → no-replace refusal, never force-delete;
- disk session/link/run-state inconsistency or lookup ambiguity → bridge refusal;
- live digest drift before continuation → refusal; a successful in-place continuation records a new observation while prior transport/snapshot bytes stay unchanged.

## Verification Strategy

Focused permanent checks:

- binary pin/build evidence: supported platform and AVX2 target, canonical launcher paths/digests, exact source/module locks, normalized Bazel Rust/C/C++ action-toolchain labels and executable digests, planted build overrides, byte-identical clean outputs, and final version/digest;
- codec fixtures: closed header/usage shapes, mixed lifecycles, multiple text blocks/messages, update/end deduplication, recovered and final errors, late custom advisor events, boolean terminality, unknown events, malformed known events, missing terminal/frame, nonzero exit, child frame spoof, launch/session/confinement mismatch, transient OMP debug metadata, terminal-safe non-interactive displays, and unchanged authoritative output/ordinary Codex execution;
- fake-child launch tests: exact argv and zero positionals, stdin bytes plus EOF, close-on-exec/closed inherited descriptors, source-descriptor copy plus private-copy digest/execute, wrong digest/version/path substitution, transient `--no-session`, exclusive canonical visit directory and interrupted-visit non-reuse, process/OMP cwd equality, exact environment names/values, auth-broker-only selection, workflow `.env`/repository-context negatives, workspace file-read positive, closed conf admission, inherited Landlock ABI/policy identity, direct and spawned conf write/replace/create/rename/restore refusal, every admitted write-root positive, and live/snapshot separation;
- Workflow Lisp: target gate, legal direct-root publication, exact artifact key, duplicate key, unsupported provider rejection, downstream retry incompatibility through the existing validator, every forbidden placement, compile/lower/runtime publication, omitted-clause transient selection, and two legal root calls with distinct symbols;
- prompt CLI/scaffolder: generate/rerun flag matrix, output/returns exclusion, strict returns schema, literal/file capture, pre-inference capture, closed provider→inference mapping, default/exact/inferred modes, non-recursive record name, deterministic identity/source, full manifest binding, no-replace race/reuse, and tamper/extra-node/symlink/concurrency refusal;
- bridge: exact lookup precedence/ambiguity, forged/mismatched records, failed-chain blocking, TTY requirement, frozen-conf/current-credential reconstruction, full-id fork, explicit in-place revision, source/destination manifest predicates, primary prompt extraction, child/advisor rejection, malformed graph refusal, and explicit/default/reused contract modes;
- preset canaries: one passing and failing fixture for neutral, advised, fanout, peer-team, and advised-fanout; ambient-profile negatives, repository-context positive, immutable spawn-time conf under transient write → spawn → restore attempts, and settlement/worktree cleanup;
- one real end-to-end trial: `prompt run` → generated `.orc` → OMP advised-fanout provider → typed bundle + session metadata → observation pane → interactive safe fork → import → verified deterministic scaffold reuse.

Tests assert behavior, contracts, artifacts, lineage, and dataflow. They do not assert literal prompt wording.

## Declarative Acceptance Scenario

From a clean checkout with deliberate canaries in user/ancestor/global OMP, Claude, environment, and resource roots plus a known repository context marker:

```bash
python -m orchestrator prompt run \
  --prompt-file task.md \
  --output "summary, changed files, and verification" \
  --provider omp_conf \
  --conf orchestrator/omp_assets/confs/advised-fanout
```

Expected:

- exact `task.md` bytes become the sole authored task prompt asset; the separately recorded composed-provider-prompt digest binds compiler-added return guidance;
- tool-free transient neutral OMP infers a validated return contract without mutating captured task inputs or creating a hidden session directory;
- the non-recursively named, semantically addressed scaffold compiles and its full envelope verifies before task execution;
- task OMP starts from the exact positive environment and empty process/OMP cwd under the recorded inherited Landlock policy, sees immutable admitted conf resources, receives the repository context marker through the `conf` lane's explicit `--add-dir`, can read and write an explicitly named workspace file, and sees no workflow/ancestor/user ambient profile or environment canary;
- the observation pane receives each authoritative assistant `message_end` text once through the terminal-safe display projection and complete usage once;
- typed provider result and explicit `omp_session` publish from one canonical visit directory;
- state records whole-binary/version, confinement-policy identity, normalized usage, conf digest, primary session, exact preset observations, and live/frozen paths and digests without claiming hostile-model authorship;
- all child sessions inherit the policy, consume the immutable conf, satisfy the pinned settlement predicate, and leave every recorded isolated worktree path absent at close;
- TTY safe resume uses the full id, current broker credentials, frozen conf, and recorded model to create one fork without changing the source journal, prior transport evidence, or frozen observation, then writes one continuation observation;
- default import treats transcript/disk input as untrusted; explicit run-contract reuse checks the composed prompt digest and regenerates from verified `prompt.md`/contract/conf/provider/model bytes to the same scaffold identity.

Any environment/cwd/confinement mismatch, conf mutation or write-confinement escape, ambient-profile canary observation, missing required event/usage/preset observation, unresolved child, unsafe observation control byte, false authorship/authentication claim, CLI grammar ambiguity, contract mismatch, no-replace violation, bridge ambiguity, or identity mismatch fails the scenario.

## Stop / Revise Criteria

- F1/F2/F4 failure: no OMP provider lands.
- F3 failure: ambient templates may land if clearly documented; `omp_no_tools`, `omp_conf`, inference, and presets do not.
- F5 failure: remove the failing preset rather than fake liveness evidence.
- Forward bridge failure: retain explicit session capture but omit `prompt resume`.
- Import extraction/reuse failure: retain forward resume/fork but omit `prompt import`.
- F8 failure: retain exact/default return modes; omit natural-language inference.
- Need for a direct API-key credential channel, new env/config/frontmatter key, or another inference provider: revise the corresponding closed versioned schema; do not accept unknowns.
- Need for mid-turn control: new RPC design; do not stretch JSON print mode.
- Need for multiple confs in one workflow: design explicit per-call binding; do not overload global input names silently.
- Upstream protocol/config/discovery drift: recapture and review before changing the pin.

## Documentation Impact

On landing:

- `specs/providers.md`: OMP templates, trust lanes, whole-binary launcher/codec/observation contract;
- `specs/cli.md`: `prompt run|import|resume`, content-addressed generation, verified rerun, contract modes;
- `specs/dsl.md`, `specs/versioning.md`: target `2.27` and `:session-artifact`;
- `specs/state.md`: canonical provider-session visit directory, live/frozen observation layout, and run-link consistency record;
- `docs/lisp_workflow_drafting_guide.md`: hand-authored `omp`/`omp_no_tools`/`omp_conf` examples and the reserved `omp_conf_root` input;
- `docs/capability_status_matrix.md`: OMP-I1 status by surface;
- `docs/index.md` and the follow-on roadmap: accepted design, implementation status, and deferred OMP-I2/RPC items;
- OMP upgrade runbook: source/binary pin, fixture recapture, environment/conf admission review, and canaries.

`prompt resume` is a foreground interactive handoff, not a supervised workflow service; it needs CLI help/spec coverage but no monitoring-runbook entry.

## Owner Decisions

1. Resolved 2026-08-21: `OMP-I1` tranche 1, including a real trial, is selected after frozen-ES hand-back.
2. Resolved 2026-08-21: OMP-I2 is approved only as a lower-priority design; implementation requires later activation and a named consumer.
3. Ambient OMP parity and profile-isolated configured OMP are separate trust lanes; neither borrows the other's claims.
4. Persistence is explicit: ordinary template commands use `--no-session`; `:session-artifact` selects the canonical fresh command.
5. Safe session inspection forks by default; in-place resume is explicit. Both are foreground CLI operations outside provider/workflow resume.
6. The `conf` lane exposes the repository as an additional tool and context root because pinned OMP loads context from `--add-dir`; `no-tools` and `conf-inference` omit that root. All profile-isolated lanes use the versioned exact environment/YAML/frontmatter schema and the loopback auth broker as their sole OMP-I1 credential channel.
7. Destructive scaffold `--force`, generated executable command manifests, recursive identity/name derivation, and provider overrides on verified rerun are excluded.
8. Whole-binary descriptor-copy/private-digest execution, exact codec/CLI predicates, tool-free inference, no-replace publication, and observation-not-authentication boundaries are mandatory.
9. `omp_no_tools` is a public profile-isolated template using the neutral conf and explicit `--no-tools`; it is not an ambient alias.
10. OMP is self-built under the recorded positive Linux `x86_64` AVX2 build environment, admitted only after two byte-identical clean builds with identical Bazel action-toolchain closure records, and its exact digest is part of scaffold/link identity.
