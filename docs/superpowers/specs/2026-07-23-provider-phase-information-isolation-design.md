# Provider-Phase Information Isolation Design

## Metadata

- **Status:** accepted for implementation
- **Kind:** architecture decision
- **Owner:** Orchestrator maintainers
- **Reviewers:** independent specification and quality re-reviews approved the
  base design 2026-07-23 and the rootless-launch amendment 2026-07-25
- **Created:** 2026-07-23
- **Last material update:** 2026-07-25
- **Related docs / issues / plans:**
  - [`.orc` Versus One-Shot Experiment Program Design](2026-07-23-orc-vs-one-shot-experiment-design.md)
  - [`.orc` Versus One-Shot Experiment Program Implementation Plan](../plans/2026-07-23-orc-vs-one-shot-experiment.md)
  - [Provider-Phase Information Isolation Implementation Plan](../plans/2026-07-23-provider-phase-information-isolation.md)
  - [Experiment Control-Plane Feasibility Report](../../reports/2026-07-23-experiment-control-plane-feasibility.md)
  - [`specs/providers.md`](../../../specs/providers.md)
  - [`specs/security.md`](../../../specs/security.md)
  - [`specs/state.md`](../../../specs/state.md)
  - [`specs/io.md`](../../../specs/io.md)
  - [`specs/cli.md`](../../../specs/cli.md)
  - [`specs/index.md`](../../../specs/index.md)
  - [`specs/versioning.md`](../../../specs/versioning.md)
  - [`specs/acceptance/index.md`](../../../specs/acceptance/index.md)
  - [Adjudicated Provider Step](../../plans/2026-04-20-adjudicated-provider-step-design.md)
  - [Workflow Lisp Private Runtime State And Consumer Value Flow](../../design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md)
  - [Workflow Lisp Consumer-Side Rendering (predecessor detail)](../../design/workflow_lisp_consumer_side_rendering.md)
- **Implementation target:** an opt-in, fail-closed runtime isolation profile
  for ordinary provider invocations, initially backed by Linux Bubblewrap

## Summary

Provider-phase information isolation must be an operating-system-enforced
execution boundary, not a convention about prompts, current working
directories, copied workspaces, or orchestrator-managed path validation. Under
the proposed profile, each provider invocation receives the candidate product
workspace as its writable working directory, its active rendered prompt over
the existing prompt transport, a phase-private result-bundle broker, and only
the explicitly packaged provider runtime and direct process-environment
credential grants needed to execute.
Workflow source, raw prompt assets, controller state, prior raw bundles,
evaluators, peer arms, and the parent checkout are absent from the provider's
mount namespace.

The profile is explicit and fail-closed. Existing trusted/unrestricted provider
profiles retain their current behavior and do not satisfy an isolation
requirement. A required isolated invocation fails before provider launch if the
host, provider environment, or requested capability policy cannot be enforced.
Historical source-retrieval isolation is a separate capability axis: ordinary
provider API transport may remain usable while history-fetch mechanisms are
denied only when both the provider tool policy and network boundary can attest
that separation. Otherwise historical work is truthfully classified
`OBSERVATIONAL_ONLY`.

This architecture adds host- and environment-packaging constraints. It makes
portable provider launch, shared provider sessions, and ad hoc access to host
toolchains harder; those costs are accepted because a permissive fallback
would invalidate the information-isolation claim.

The Linux backend is rootless at invocation time. It must not call `sudo`,
`pkexec`, `setpriv` through a privileged parent, a set-id group-clearing
helper, or a capability-bearing broker. An ordinary unprivileged Bubblewrap
user namespace can retain the controller's supplementary group credentials;
unmapped groups being rendered as the overflow GID is not evidence that their
host-kernel DAC authority disappeared. V1 therefore proves a closed object
projection and descriptor set, in addition to validating the namespace's
one-row UID/GID maps and permanently denied `setgroups` state. A host that
cannot construct that boundary without privilege fails closed.

## Context And Authority

Current normative behavior explicitly does not provide this boundary:

- `specs/security.md` states that child processes can read or write anything
  permitted by the operating system and directs stricter use cases to an
  OS/user sandbox.
- `specs/providers.md` documents built-in Codex and Claude profiles that bypass
  the tools' own approval or sandbox mechanisms.
- The adjudicated-provider design treats candidate copies as authorities for
  orchestrator-managed validation and promotion, while explicitly excluding
  arbitrary child-process containment from its contract.
- `--state-dir` selects the `StateManager` run root. It does not currently move
  every Workflow Lisp build, checkpoint, or result-bundle projection out of the
  candidate working directory.

The `.orc` versus one-shot experiment design requires a stronger contract.
Provider phases must be able to edit the candidate and return typed results
without ambient access to inactive treatment assets, prior raw runtime state,
evaluation authorities, peer arms, or the controller. The 2026-07-23
feasibility spike demonstrated that external absolute CLI paths and an
external `--state-dir` are functionally supported, but do not deny provider
filesystem reads.

Normative runtime behavior remains owned by `specs/`. This document selects the
target architecture; implementation must update the relevant normative specs
before enabling the new profile.

## Problem

An ordinary provider is a child process with the invoking user's ambient OS
authority. Setting `cwd` to a candidate directory affects relative path
resolution but does not prevent absolute reads. Omitting a path from the
rendered prompt withholds a hint, not access. Copy-backed candidate workspaces
separate orchestrator-managed outputs, but a child can still walk to sibling
workspaces, the parent checkout, external controller roots, or runtime files
when the OS makes them visible.

This breaks the runtime's intended mediation of controller-owned authorities in
two ways:

1. A phase can inspect control information it was not assigned, including
   inactive prompts, evaluators, peer treatments, and controller records.
2. A later phase can bypass typed dataflow by reading the earlier phase's raw
   result bundle or checkpoint state.

Moving all control files under another absolute path, changing prompt
composition, or excluding `.orchestrate` from a reviewer manifest does not
solve the provider-read problem. The runtime needs a launch boundary whose
allowlist is enforceable independently of provider cooperation.

## Threat Model

The provider process and every descendant are adversarial. The controller,
host kernel, verified Bubblewrap host startup closure, reviewed packaged launch
shim, its exact sealed interpreter and complete startup code/configuration
closure, and all non-provider host users/processes are trusted not to mutate
the admitted candidate or run-owned snapshot during an invocation. Hashes establish
the reviewed TCB's identity, not its benignness. Candidate contents, the active
prompt and typed inputs, explicitly granted per-step credentials, and the
active result channel are intentionally visible.
Control/state/evaluator/peer/parent files and ambient descriptors/environment
are not.

The writable candidate is an intentional shared/declassification channel across
phases. An adversarial phase can deliberately copy any information it is
allowed to observe into a product file for a later phase, so v1 does not claim
full non-colluding or covert-channel-resistant cross-phase non-interference.
Its enforceable claim is narrower: controller-owned control authorities,
ambient host filesystem/process authority, and prior raw runtime bundles are
absent from each provider's launch authority unless deliberately copied into
the candidate by an earlier provider. Trusted kernel metadata visible through
the new procfs and metadata from the deliberately shared network are outside
that claim. Experiments requiring resistance to colluding phases need a future
per-phase workspace plus mediated product promotion.

This is a direct local filesystem/process-environment authority boundary, not a
general network DLP boundary. V1 shares the host network, so the credential
allowlist constrains only direct environment inheritance; it cannot prevent an
adversarial provider from querying a reachable cloud-metadata endpoint,
localhost agent/dashboard, or remote service. A host is eligible for I0/G0 only
when no network-reachable service exposes denied local authorities or ambient
credentials. The backend inventories pre-existing local listeners and
fail-closed probes a closed, versioned set of cloud-metadata and runtime-known
control endpoints immediately before each launch. Remaining listener/service
reachability is an explicit, attested deployment trust assumption that
operators must review; it is not an implemented denial. Any reachable service
that actually exposes denied authority invalidates I0/G0 on that host.

Remote retrieval and a granted credential's use against ordinary network
services remain outside the core claim and prevent causal history
classification unless separately enforced and probed.

## Goals And Non-Goals

### Goals

- Preserve the candidate product directory as the provider's observed `cwd`
  and allow ordinary product reads, writes, tests, and tool execution there.
- Keep the active rendered prompt and declared typed inputs usable without
  mounting their raw control-plane sources.
- Prove that every declared typed phase input is rendered into the active
  provider prompt; producing a value in state without consumer carriage is not
  sufficient.
- Expose one phase-private result target while making prior and sibling raw
  runtime bundles directly unreadable.
- Make workflow source, prompt assets, extern manifests, controller state,
  evaluators, peer arms, and the parent checkout absent from the provider's
  filesystem view.
- Mask every runtime projection under the candidate product, including
  `.orchestrate`, except for the brokered active result target.
- Use the same launcher for the public CLI path, retries, and supported resume
  paths; a fixture-only helper is not sufficient.
- Export the same no-result launcher contract for experiment-certified check
  children so provider-authored product code cannot regain denied authority
  when fixed checks execute it.
- Bind an immutable isolation policy and backend attestation into run
  provenance so resume cannot silently weaken the boundary.
- Keep provider API transport and history-retrieval denial as separately
  reported capabilities.
- Fail local eligibility when a provider-reachable cloud-metadata service or
  known orchestrator/control endpoint can expose ambient credentials or denied
  authority, and attest the trust assumption for remaining listeners.
- Emit stable, actionable diagnostics and fail before provider launch when a
  required boundary cannot be constructed.

### Non-Goals

- General data-loss prevention, secret discovery, prompt redaction, or defense
  against a compromised host kernel.
- Preventing a phase from deliberately persisting its allowed observations into
  the shared writable candidate for a later phase.
- General egress filtering or proof that arbitrary remote services do not hold
  repository history; v1's shared network remains an attested limitation.
- Sandboxing arbitrary `command` or certified-command adapters in the first
  tranche. The prerequisite runtime rejects every command step in a
  required-isolation workflow. It exports and tests the no-result launcher and
  attestation sink needed by the experiment; a later experiment task must add
  a pinned built-in certified-adapter identity/runtime seam before admitting
  its in-workflow fixed checks. No-policy workflows retain their current
  command contract.
- Claiming that copied candidate workspaces or reviewer-package exclusions are
  OS security controls.
- Retrofitting current trusted/unrestricted provider profiles into isolated
  profiles without explicit operator configuration.
- Supporting every host OS in the first implementation. The first backend is
  Linux Bubblewrap; other platforms require independently reviewed backends.
- Allowing shared or resumed provider sessions in the evidence-grade
  `fresh_only` profile. A provider session intentionally retains earlier
  conversation state and therefore has a different information-flow contract.
- Supporting managed-provider wrappers, adjudicated providers/evaluators,
  provider-backed step summaries, or live-agent notes in v1. Their current
  controller/run-root access patterns need separate projection and result
  channels; required isolation rejects them before launch.
- Containing a later hard evaluator that imports or executes provider-authored
  product code. G0 proves the provider/check-child boundary only; the
  experiment remains responsible for a separate evaluator-containment design
  and gate before scored execution.
- Projecting later soft-reviewer or F2 consumer provider sessions. Their
  peer-review, unblinding, transcript, and typed-result surfaces require a
  separate reviewed launcher profile/gate before scored use; package filtering
  is not authority isolation.
- Credential files, agent sockets, or inherited host homes in v1. The first
  profile accepts only explicitly named credential environment variables.
- Preventing an adversarial provider from exhausting CPU, memory, process,
  candidate-space, synthetic-home, `/tmp`, or result-scratch resources. V1
  bounds result ingestion and uses timeout/cancellation plus namespace
  destruction for eventual quiescence, but those are cleanup guarantees, not
  provider or host availability guarantees. Deployments that require
  availability isolation must add separately reviewed cgroup/storage quotas.
- Guaranteeing causal withheld-history evidence when provider-side browsing or
  source-retrieval capabilities cannot be independently disabled and probed.

## Decision

Add an external, runtime-owned `provider_phase_isolation.v1` policy and a
provider-launch isolation layer below workflow semantics. The policy is
selected through a new public CLI policy-file option and applies to ordinary
provider steps after provider/prompt extern resolution. It does not require a
new Workflow Lisp form or make policy data visible in the candidate.

The first backend uses Bubblewrap to construct fresh user, mount, PID, IPC, and
UTS namespaces for every provider attempt while deliberately sharing the
preflighted host network. It preserves the candidate's host absolute path
inside the namespace, bind-mounts that directory read/write, masks the
candidate `.orchestrate` tree, supplies isolated `/tmp`, `/proc`, and `HOME`,
and mounts only a sealed run-owned provider rootfs plus narrow filesystem
grants. Direct credential values cross only through the bounded fd-3 launch
shim and become final-provider environment values; no credential file or host
environment is mounted. Control, evaluator, peer, parent, and controller paths
are not mounted.

The active structured-result path is mediated by an output broker. The
provider sees the usual logical `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, but its
parent directory is invocation-private scratch. After the child exits, the
launcher validates and transfers only that file to the host runtime path
before existing result-contract validation runs. Previous bundles are never
mounted.

V1 workflow integration is deliberately narrow: it accepts ordinary fresh
provider steps with a compiler/runtime-owned structured-result allocation.
Provider steps without a structured result, authored product-path bundles,
managed providers, adjudicated providers/evaluators, and provider-backed
observability are rejected with a stable unsupported-surface diagnostic.
The prerequisite runtime likewise rejects every command step in a
required-isolation workflow before any provider/command launch. The
service-level certified-check proof described below establishes the narrow
launcher capability but does not make arbitrary command externs trusted. The
experiment may admit its fixed-check adapter only after a later reviewed change
pins an implementation-owned adapter/boundary identity and routes every
product-executing child through this service.
No-policy runs preserve existing launcher, security, and state-schema behavior.
The policy-independent typed-input correctness tranche described below changes
prompt carriage for affected `provider-result :inputs` workflows under both
profiles.

The namespace launcher is a reusable service rather than a
`WorkflowExecutor`-private subprocess wrapper. Its request is one closed
subject union; attempt identity, result channel, and recovery authority are not
independent fields:

- `workflow_provider` requires a compiler/runtime-owned typed-bundle result
  channel plus the aggregate-root lifecycle scope/ordinal from
  `provider_attempt_allocations`; and
- `controller_attempt` requires `result_channel: "none"`, a caller-owned
  immutable attempt ID, command/adapter identity, and caller-owned external
  lifecycle/attestation sink. It has no workflow scope, ordinal, provider
  template, or `provider_attempt_allocations` entry.

Every cross-combination is rejected before allocation, scratch creation, or
launch. A later experiment `DIRECT` arm uses the `controller_attempt` variant.
The experiment's certified fixed-check adapter uses the same variant with zero
credentials, a fresh product extract as candidate, and the same denial
attestation for every child command. The ambient adapter may validate/copy
no-follow and interpret child exit, but must not execute provider-authored
product code itself. The experiment's raw `ArmCommand` path may not launch a
provider or product-executing check until it adopts this service.

There is no best-effort isolated mode. `mode: required` either produces a
validated launch plan and attestation or returns a pre-launch diagnostic.
Omitting the policy retains current behavior and current security claims.

### Alternatives rejected

- **Prompt omission or role instructions:** cooperative and unable to deny
  direct filesystem reads.
- **External `--state-dir` alone:** the current runtime also creates build,
  checkpoint, and bundle projections under candidate `.orchestrate`; even a
  fully external state directory would remain readable to an unrestricted
  process by absolute path.
- **Copy-backed candidate workspace alone:** isolates runtime-managed path
  operations, not the provider process.
- **File-permission changes under the same user:** brittle for writable
  directories, credentials, retries, and sibling roots; the provider retains
  the same user authority.
- **Provider tool sandbox alone:** current built-ins explicitly bypass it, and
  tool-specific policy cannot establish a uniform runtime contract.
- **Containerize the whole orchestrator:** useful as an operational outer
  boundary, but too coarse for phase-private prior bundles and per-invocation
  grants. It may be layered underneath the same backend interface later.

## Design Details

### 1. Policy and runtime model

The external policy file has one canonical JSON object:

```json
{
  "schema_version": "provider_phase_isolation.v1",
  "mode": "required",
  "backend": "bubblewrap.v1",
  "session_mode": "fresh_only",
  "workspace": {
    "access": "read_write",
    "masked_runtime_roots": [".orchestrate"]
  },
  "provider_environment": {
    "root": "/absolute/sealed/provider-rootfs",
    "provider_prefix": "/opt/orchestrator-provider",
    "digest": "sha256:..."
  },
  "process_environment": {
    "credential_env": ["OPENAI_API_KEY"]
  },
  "result_bundle": {
    "max_bytes": 16777216
  },
  "shared_network_review": {
    "inventory_path": "/absolute/private/network-inventory.json",
    "inventory_digest": "sha256:...",
    "decision": "accept_unlisted_reachability"
  },
  "history_retrieval": {
    "eligibility_requirement": "classify",
    "provider_api_transport": "allow",
    "remote_git": "deny",
    "browser": "deny",
    "source_search": "deny",
    "repository_fetch": "deny"
  }
}
```

The exact JSON Schema is normative implementation work, but these semantic
fields are fixed by this design:

- `schema_version` selects the contract.
- `mode` is `required`; no permissive downgrade belongs in this schema.
- `backend` names an exact backend contract, not merely an executable on
  `PATH`.
- `session_mode` is `fresh_only` for the first release.
- `workspace` grants the current candidate root and masks runtime-owned
  subtrees.
- `provider_environment` names a content-addressed, read-only executable
  root filesystem plus the absolute prefix at which the provider was packaged.
  The prefix must be outside runtime overlay/kernel roots such as `/home`,
  `/workspace`, `/tmp`, `/run`, `/proc`, and `/dev`. The environment source
  must not be the mutable controller checkout.
- `process_environment.credential_env` is the complete v1 list of controller
  environment-variable names whose values may be eligible to cross into a
  provider. The actual grant is the intersection with the ordinary provider
  step's declared `secrets`; a policy-listed secret not requested by that step
  is not injected, while a requested name outside the policy or absent from the
  controller environment fails before launch. Global-secret expansion follows
  the existing provider-step declaration semantics before this intersection.
  The policy contains names, never values. Authored provider `env` is
  unsupported in v1 except for runtime-owned output-bundle bindings.
- Reserved launch, interpreter, and loader variables cannot be credential
  grants or inherited. This includes `HOME`, `PATH`, `PWD`, `TMPDIR`,
  `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`, `VIRTUAL_ENV`, `CONDA_PREFIX`,
  `XDG_*`, `SSH_AUTH_SOCK`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, `BASH_ENV`, `ENV`,
  `NODE_OPTIONS`, and locale/time names. Locale and time values used inside the
  namespace are fixed values constructed by the controller, not inherited
  values.
- `result_bundle.max_bytes` is a positive bound no larger than 16,777,216
  bytes in v1. The value participates in the policy digest. The example uses
  the v1 maximum.
- `shared_network_review` references one absolute controller-private closed
  inventory report by canonical digest and records the only v1 decision,
  `accept_unlisted_reachability`. The runtime recomputes the current inventory
  and requires an exact digest match before launch; the report is never mounted
  or copied into the candidate.
- `history_retrieval` records separately enforceable capabilities.
  V1 fixes `provider_api_transport` to `allow` and each of `remote_git`,
  `browser`, `source_search`, and `repository_fetch` to `deny`; other requested
  modes are schema-invalid.
  `eligibility_requirement: "classify"` permits execution with a truthful
  `OBSERVATIONAL_ONLY` result when a requested denial cannot be enforced;
  `"require_causal"` fails before launch in that case. A requested denial that
  cannot be attested is always recorded as unenforced, never as an effective
  denial.

The policy file and private network-inventory report are runtime
controller-input authorities. Each lives in a
dedicated controller-owned real directory with mode `0700`, is a real regular
file with mode `0600` and one link, and is pinned/read descriptor-relatively
with no symlink following; group/world-accessible files, writable/untrusted
ancestors, xattrs, swaps, and aliases fail closed. Their dedicated authority
directories must be canonically disjoint in both containment directions from
the candidate, mutable environment source, published snapshot, runtime/state,
scratch, workflow/source/extern, evaluator, peer, parent, and every
provider-visible rootfs authority. Thus neither the policy's secret names and
control paths nor the full listener inventory can enter a provider mount.
The generated environment-manifest file is optional operator evidence, not a
policy field or resume input; its command applies the same private output
rules, while run recomputes the manifest from the policy's root/prefix and
requires its canonical digest to equal `provider_environment.digest`.

The CLI canonicalizes and hashes the policy before workflow execution. The
complete isolation-policy digest and `provider_environment.digest` are
different identities and are persisted under different state fields. The
former is SHA-256 over the complete canonical policy object. The latter is
SHA-256 over the canonical `provider_environment_manifest.v1` described below;
the policy merely embeds that manifest digest as one field. Therefore changing
an unrelated policy field changes the complete policy digest without changing
`provider_environment.digest`, while changing the canonical environment
manifest and updating its policy field changes both identities. Neither value
may be substituted for, cross-populated into, or inferred from the other.
Golden vectors, initial-state persistence, and resume mismatch tests must
exercise those two changes independently. The two digests, backend identity,
and effective capability result become immutable run provenance. `resume` must
reload the same canonical policy and reject any missing, swapped, or
mismatched identity.

Implementation packages six independently closed schemas:

- `provider-phase-isolation-v1.schema.json` for controller policy;
- `provider-environment-manifest-v1.schema.json` for frozen tree identity;
- `provider-isolation-network-inventory-v1.schema.json` for the
  controller-private listener review;
- `provider-isolation-bundle-transfer-v1.schema.json` for crash-safe result
  publication;
- `provider-isolation-lifecycle-prefix-v1.schema.json` for the
  non-self-referential subject/result lifecycle prefix; and
- `provider-isolation-attestation-v1.schema.json` for attempt evidence.

Each rejects unknown fields recursively. Schema validation is followed by the
semantic path, inode, digest, and capability checks in this design; JSON shape
alone is not admission.

All six records use one `canonical_isolation_json_bytes` owner. It calls
JSON serialization with UTF-8 output, lexicographically sorted object keys,
compact `(",", ":")` separators, `ensure_ascii=False`, `allow_nan=False`, and
appends exactly one LF. Schemas admit no floating-point values. Filesystem path
fields must already be Unicode NFC; manifest entries sort by the UTF-8 bytes of
their normalized POSIX relative paths before serialization. No other Unicode
folding occurs. Policy, manifest, network-inventory, bundle-transfer,
lifecycle-prefix, attestation, and state-reference digest tests must share golden
ASCII/Unicode/path-order vectors.

### 1A. Frozen provider-environment identity

`provider_environment.digest` is the digest of a canonical
`provider_environment_manifest.v1`, not a hash of an absolute directory name.
The source is a sealed root-filesystem tree whose relative paths are the exact
provider-visible absolute paths below `/`. The manifest excludes the host
source root path, includes the declared absolute `provider_prefix`, and
contains an ordered `.` directory entry for the mounted root plus one entry for
every descendant:

- normalized POSIX relative path;
- entry kind (`directory`, `regular_file`, or `symlink`);
- normalized provider-visible permission bits: source write bits are removed
  while read/execute bits are preserved; Linux symlink mode is fixed to
  `0777`;
- fixed provider-visible `uid: 0`, `gid: 0`, `atime_ns: 0`, and `mtime_ns: 0`;
- byte size and SHA-256 for regular files; and
- original link text for symlinks.

The source root must be a real directory. The `.` row records its normalized
mode, and the root is subject to the same xattr and before/after identity checks
as descendants. A manifest walk uses `lstat`, never follows a directory
symlink, rejects absolute/broken/escaping symlinks, and rejects sockets, FIFOs,
devices, nested mountpoints, any extended attribute, and any regular inode
whose link count cannot be fully accounted for by entries inside the
environment. V1 rejects rather than silently omits xattrs because loader and
`security.capability` xattrs can change executable behavior.
Accepted in-source hardlink aliases are normalized: the copier creates one
distinct destination inode per manifest path and the final snapshot requires
`st_nlink == 1` for every regular file. Source hardlink topology is therefore
not an unrecorded part of provider-visible identity.
Nested-mount rejection uses Linux mount identity, not `st_dev`: the walk
obtains `STATX_MNT_ID` for the pinned root and every no-follow entry and rejects
any different mount ID, including a same-device bind mount. If
`STATX_MNT_ID` cannot be obtained reliably, a trusted
`/proc/self/mountinfo` correlation must prove the same property or the backend
is unavailable; comparing device numbers alone is never sufficient.
Every entry name and original symlink-target text must decode as strict UTF-8
and already be NFC; undecodable, surrogate-escaped, or non-NFC bytes are
`provider_isolation_environment_invalid`, never implicitly normalized.
Canonical isolation JSON of `{schema_version, provider_prefix, entries}` is the
digest input. Host inode/ctime and the admitted controller owner ID are
explicitly non-identity implementation details: every copied object remains
controller-owned, the user
namespace maps that owner to provider-visible `0:0`, and the fixed timestamp
fields are applied rather than copied from the source.
The mutable source root and every source entry must be controller-owned and
not group/world writable during admission; otherwise another authorized writer
could defeat before/after copy checks with an ABA mutation.

Before the first attempt, the controller copies the accepted tree into the
root-owned
`<run-root>/provider_environment_snapshots/<manifest-digest>/rootfs`
authority using descriptor-relative, no-follow operations. Canonical manifest
modes are the exact post-copy modes, computed for the `.` root and every
descendant by stripping all write bits from ordinary source modes before either
source or destination identity is hashed.
The controller populates a private owner-writable staging sibling and compares
source metadata before and after each copy. It then normalizes ownership and
atime/mtime without following links, `fchmod`s regular files and directories to
canonical final modes, and fsyncs each finalized inode bottom-up. It rebuilds
and verifies the final manifest, atomically renames the complete staging
directory to the digest authority, and fsyncs the authority parent. Controller
verification reads use Linux no-atime semantics, and the read-only namespace
projection must preserve the fixed timestamps; otherwise the backend is
unavailable.
Partial staging trees and a final directory without the verified manifest are
never resumable or mountable. Provider attempts mount this published snapshot,
never the mutable policy source root. The backend opens the snapshot root as a
role-labeled setup descriptor, revalidates its identity immediately before
launch, and gives that descriptor only to Bubblewrap while it constructs the
namespace. Bubblewrap binds the descriptor rather than re-resolving the
original path and closes it before the final provider exec. Source mutation
after snapshot creation cannot change the launch; snapshot mutation or an
identity change fails closed.

Resume requires the recorded run-owned snapshot and manifest digest to remain
present and valid. It does not recopy from a later-mutated source or silently
substitute another path; a missing snapshot requires an explicitly new run so
environment provenance cannot change within one lineage.

The mutable provider-environment source must be canonically disjoint in both
containment directions from the candidate, workflow/source and extern roots,
controller state, invocation scratch, and every experiment-declared evaluator,
peer, parent, and control authority. The snapshot has one narrow host-path
exception: it must be exactly below this run's root-owned
`provider_environment_snapshots` authority and may not overlap any other
run/state subauthority. Its provider-visible manifest paths remain subject to
every denial. A source package that contains a forbidden authority—or is
contained by one—is rejected before copying; digest verification does not make
forbidden content admissible.

V1 mounts the verified run-owned rootfs snapshot read-only at `/`, then overlays
the candidate, synthetic home/temp/kernel filesystems, and active-result
scratch. This is not a bind of the host `/`: the mount-plan audit permits only
the verified snapshot descriptor as the rootfs source and still rejects
`--ro-bind / /`. `PATH` points at the declared `provider_prefix`. Absolute
shebangs, ELF interpreters, RPATH dependencies, DNS/NSS configuration, and CA
material are accepted only when their resolved provider-visible paths are
present in the manifest-backed rootfs. Thus `/usr/bin/env` is allowed only when
the sealed rootfs supplies it; an ambient or missing `/usr/bin/env` fails
preflight. This preserves prefix-sensitive conda/venv/Node environments and
conventional Linux loaders without granting any ambient host root.

V1 does not mount credential files. Non-secret provider configuration and CA
material must be part of the frozen environment. Secret transport uses only
the policy's named credential environment variables. If the intended provider
cannot run under that contract, implementation stops for a reviewed credential
extension rather than mounting the host home.

The environment assembler injects the packaged
`provider-launch-shim.v1` resource at
`<provider_prefix>/libexec/provider-launch-shim-v1.py`; the mutable source must
not prepopulate that reserved path. It invokes the shim only through the
manifest-backed `<provider_prefix>/bin/python -I -S` interpreter, with all
`PYTHON*` variables absent and no site/customization startup. The assembled
manifest contains both exact identities. The backend identity and capability
probe pin the runtime-known packaged shim digest plus the exact interpreter,
ELF loader, library, Python-import, and startup-configuration closure digests
and execute a nonce challenge through that chain. `python -I -S` must exclude
the candidate/current directory and site customization from `sys.path`; every
module imported before the shim closes setup descriptors must be
manifest-backed and read-only. `/etc/ld.so.preload` is rejected. Loader cache,
RPATH/RUNPATH, preload-equivalent configuration, and shim-import resolution
must never select candidate, scratch, synthetic-home/temp, or another writable
overlay. Thus neither a source collision, writable pre-shim code path, nor a
post-preflight replacement can become trusted.

Bubblewrap itself starts with the same empty/fixed non-secret environment
described below; credential values never appear in Bubblewrap's environment or
argv. The controller normalizes final transports to stdin/stdout/stderr
descriptors 0/1/2 and sends the declared credential map on fixed descriptor 3
using the closed `provider_launch_credentials.v1` binary frame: magic/version,
at most 32 unique predeclared UTF-8 names of at most 128 bytes, values of at
most 65,536 bytes each, and at most 262,144 total frame bytes. This frame is
never persisted or hashed. The trusted shim joins a fresh empty session
keyring, validates the rootless namespace/group boundary described in Section
5, reads and validates the frame, sets the final environment, zeroes its input
buffer, closes fd 3, loads the reviewed seccomp denial for `keyctl`, `add_key`,
and `request_key`, and execs the provider. On entry, before reading
credentials, the shim closes every
descriptor numbered 4 or above with a verified `close_range`/fdwalk
implementation. It must do this itself: v1's `/proc/self/fd/<N>` Bubblewrap
bind sources can remain inherited through Bubblewrap 0.9.0, so neither
Bubblewrap nor `CLOEXEC` is the closure authority. After reading and zeroing
the frame, the shim closes fd 3, completes environment/seccomp/bootstrap setup,
then performs a second verified `close_range(3, UINT_MAX)`/fdwalk immediately
before `execve`. That second sweep removes descriptors opened during parsing,
imports, or seccomp setup. The final provider therefore has exactly 0/1/2; no
bootstrap or setup descriptor survives exec.

Environment admission discovers script interpreters and ELF loaders/libraries
only by non-executing file-format parsing. ELF resolution parses
`PT_INTERP`, `DT_NEEDED`, `DT_RPATH`, and `DT_RUNPATH`, expands only the
reviewed loader tokens (including `$ORIGIN`/`${ORIGIN}` relative to the
containing object), and applies the target loader's documented search order
against manifest-backed directories/cache data. Every normalized resolution
must remain a present, read-only rootfs path outside every writable overlay;
unknown tokens, escapes, ambiguity, `/etc/ld.so.preload`, and unpackaged
resolutions fail admission. Shim Python startup/import resolution receives the
same closure check. It must not run `ldd` or execute an
untrusted provider, interpreter, or candidate binary in the controller
namespace to discover dependencies or version output. The required actual
provider `--version`/`--help` proof runs only inside a temporary Bubblewrap
namespace constructed from the sealed rootfs (a standalone raw-Bubblewrap
probe is sufficient before the production backend exists).

### 1B. Bubblewrap backend identity

`bubblewrap.v1` resolves to one closed canonical
`provider_isolation_backend_identity.v1` object:

- backend contract ID;
- fixed executable path `/usr/bin/bwrap` and a closed trust-chain result proving
  it is a root-owned regular file with no set-id/write-by-group-or-other bits,
  no xattrs, and a real root-owned non-group/world-writable ancestor chain;
- SHA-256, size, mode, device, and inode from the opened executable
  descriptor;
- an ordered, non-executingly resolved host startup closure for Bubblewrap's
  `PT_INTERP`, recursive `DT_NEEDED`, `DT_RPATH`/`DT_RUNPATH`, loader cache, and
  other startup configuration, with absolute path, SHA-256, size, mode,
  device/inode, and ownership/xattr/ancestor trust result for every member,
  including each symlink's original text and final target identity;
- normalized Bubblewrap version output; and
- selected crash-durable containment/gated-release contract identity,
  controller-owned cgroup-v2 mount/delegation trust identity for the first
  backend, and closed create/member/kill/empty/reload probe results; and
- required capability-probe contract digest plus closed probe results.

Its digest uses `canonical_isolation_json_bytes` and is immutable run
provenance. V1 never searches `PATH` or accepts an operator-selected executable;
missing or untrusted `/usr/bin/bwrap` makes the backend unavailable rather than
establishing trust on first use. Preflight walks the fixed path
descriptor-relatively without following symlinks, verifies the complete
ownership/mode/xattr ancestor chain, opens and hashes the binary, and verifies
pathname identity against that descriptor. Before executing it, preflight
parses the host ELF closure without `ldd` or target execution, rejects
`/etc/ld.so.preload`, relative/unsafe RPATH/RUNPATH and unknown loader tokens,
and requires every resolved loader/library/cache/config member to be a
root-owned regular file with no set-id, group/world write, or xattr after a
fully recorded safe symlink/ancestor chain. Merged-usr and SONAME symlinks are
allowed only when every link/ancestor is root-owned, non-group/world-writable,
no-xattr, non-escaping, and its link text plus final target are identity-bound.
The backend identity hashes that complete closure. Launch executes
the pinned verified
descriptor (or a platform-equivalent descriptor exec), not a later pathname
lookup. The executable descriptor is a setup-only authority and is closed
before Bubblewrap's final provider exec. Each attempt revalidates the
executable and full startup-closure trust chains, descriptor metadata, and
complete bytes immediately before exec;
version is obtained only from that pinned binary. Resume requires the recorded
executable/closure bytes, version, probe contract, and fresh successful
capability results. Replacement or mutation of the executable, loader, library,
cache, or startup configuration—including a same-version result—is an identity
mismatch.
If descriptor execution cannot be enforced, `bubblewrap.v1` is unavailable.

### 2. Invocation isolation plan

For each isolated attempt, the runtime derives an immutable
`ProviderInvocationIsolationPlan` from:

- resolved candidate workspace;
- run-owned frozen executable-environment snapshot plus the subject-specific
  provider-template or command/adapter identity;
- the closed invocation subject above, including exactly its coupled identity,
  result-channel, and recovery authority fields;
- for `workflow_provider`, run, frame, step, visit, root lifecycle
  scope/ordinal, provider-template identity, and the active compiler/runtime
  typed-result allocation object with logical and host paths;
- for `controller_attempt`, caller kind/attempt/command-or-adapter identity and
  the external sink identity, with no workflow lifecycle fields;
- prompt transport mode;
- explicitly declared typed-input renderings and dependency snapshots;
- the provider step's declared secret names after global-secret expansion and
  intersection with the policy credential allowlist;
- original secret/env provenance carried from the workflow owner, rather than
  an already merged ambient environment mapping;
- required capability policy; and
- a fresh invocation scratch root under controller-owned state.

The plan contains separate host and provider-visible paths. Provider-visible
paths preserve the candidate's absolute path and current `cwd` contract, but
that path exists inside a new mount namespace whose parent and siblings are
empty unless explicitly granted. Host mount authorities are pinned,
role-labeled setup descriptors for the admitted candidate, sealed rootfs, and
result scratch; Bubblewrap uses them only while constructing the namespace and
launch does not re-resolve their source path strings. They are never
provider-visible file descriptors.

Workflow attempts receive their identity from the existing root-owned
`provider_attempt_allocations` projection and `ProviderAttemptScope`. Schema
`2.2` generalizes that single owner to every isolated provider, including
providers without prompt dependencies, rather than adding a parallel ordinal.
It durably commits one monotonic ordinal and its `allocated` event before
prompt evidence, scratch paths, or a provider process exist. The same
`(scope, ordinal)` keys generalized `composed_prompt` evidence, attempt
lifecycle, and isolation attestation. The root-owned per-ordinal record is the
only attempt-event authority; the bundle-transfer journal remains subordinate
evidence for typed-file movement and is not a second attempt journal.

The schema-`2.2` record admits the following exact-once, monotonic lifecycle
events, with inapplicable branches forbidden rather than omitted ambiguously:

1. `allocated`;
2. optional `evidence_published(record_kind=composed_prompt)`, absent only when
   execution terminates before prompt composition;
3. optional `launch_intent`;
4. optional `launch_committed`;
5. exactly one `execution_terminal`;
6. exactly one `quiescence_terminal`;
7. exactly one `result_terminal`;
8. exactly one `attestation_prepared`;
9. exactly one
   `evidence_published(record_kind=isolation_attestation)`, which is the
   attestation-finalization event; and
10. exactly one `attempt_closed`.

Every transition is serialized by the aggregate root state owner and durably
fsynced before the next effect. An exact replay is idempotent; a conflicting
duplicate, reordered event, wrong ordinal, or cross-scope reference fails
closed. `launch_intent` is the permanent no-relaunch boundary. It records the
immutable launch token, launch-plan and result-channel identities, and a
crash-durable, PID-reuse-safe containment slot. The first backend may satisfy
that slot with a controller-owned delegated cgroup-v2 leaf whose exact identity
survives controller restart and whose `cgroup.kill` plus `populated=0` state
proves teardown; an equally strong reviewed kernel mechanism is permitted.
Process groups, PID files, namespace inode numbers, and
`--die-with-parent` alone are not credited as crash-durable identity. If the
host cannot provide the selected mechanism, `I0` fails before integration.
Using the slot for membership, kill, and empty proof does not claim resource
quotas or change the v1 availability non-goal.

After `launch_intent`, any setup child remains behind a trusted
shim/bootstrap release gate and cannot exec the provider. `launch_committed`
records the exact supervisor/start/namespace/containment identities while that
gate remains closed. Only the caller that freshly appends
`launch_committed` receives a one-use release permit; reload or idempotent event
replay never returns one. A crash after `launch_intent` may only reconcile or
terminate the exact recorded containment slot and must never invoke launch
again for that ordinal.

Recovery first validates the complete closed sequence, derives its greatest
durable event under the order above, and applies only that event's unique legal
successor. An earlier event or absence predicate never overrides a durable
later event. A later event with a missing or contradictory predecessor is
invalid state; recovery does not reinterpret it as an earlier prefix.

`execution_terminal` has the closed outcomes `prelaunch_failed`,
`launch_failed`, `exit_zero`, `exit_nonzero`, `timed_out`, `cancelled`, and
`controller_crash`; exit status and process fields are permitted only for the
applicable variants. `prelaunch_failed` forbids `launch_intent` and
`launch_committed`; `launch_failed` requires `launch_intent` and
variant-validates whether a commit exists; provider exit, nonzero, timeout,
and cancellation require `launch_committed`. `controller_crash` may close any
launch prefix. `quiescence_terminal` is either
`no_process_created`, permitted only when no launch was authorized, or
`namespace_empty` with the exact launch-token/containment proof. If quiescence
cannot be proved, resume fails closed and neither brokerage, attestation
finalization, closure, nor a later attempt may proceed.

For a schema-`2.2` workflow attempt, `result_terminal` is a closed typed-channel
union. It uses
`not_eligible` for prelaunch failure, launch failure, nonzero exit, timeout,
cancellation, or controller crash. An eligible zero exit records `missing`,
`rejected`, or `published`; `missing` and `rejected` are terminal invalid
contract outcomes without a fabricated transfer journal. `published` carries
the exact subordinate bundle-transfer-journal identity/reference and the final
existing-validator disposition `valid|invalid`. A `published(valid)` workflow
result additionally requires a closed typed-value handoff reference. The
aggregate-root state owner appends that terminal in the same atomic, fsynced
state transaction that persists the normalized typed value in its owning
step/call-frame result plus every applicable public/private artifact-lineage
entry. The handoff binds contract, bundle, normalized-value, destination-state,
and checkpoint-requirement identities. `published(invalid)` forbids a typed
handoff. Thus a durable valid result terminal can never exist without its
authoritative workflow value.

The separate controller-attempt sink admits only
`result_terminal: not_applicable`, forbids a transfer journal and typed-value
handoff, and never serializes that terminal into schema-`2.2` workflow state.

The controller derives canonical attestation bytes from those durable events
without writing a file, then appends `attestation_prepared` with the
deterministic staged/final relpaths and exact digest before either path is
created. It next stages/fsyncs, atomically publishes/fsyncs, and appends the
isolation-attestation evidence event with the exact state reference.
`attempt_closed` may append only after that finalized attestation, complete
scratch cleanup, and—when a published result is invalid—the subordinate
transfer journal's deterministic provider-masked rotation. It records the
final disposition and terminal transfer-journal reference/digest when
applicable. For a valid typed result, it also requires the atomic typed-value
handoff to remain exact and any runtime-plan-required lexical checkpoint and
index to have been durably emitted and revalidated from that authoritative
value. The checkpoint remains a derived cache, never result authority. Schema
`2.2` forbids allocating or launching ordinal `N+1` until `N` is closed; no
lifecycle event can be removed, reordered, overwritten, or published twice.

The schema-`2.2` closed event model preserves schema-`2.1` legacy validation
while preventing duplicate launch, result publication/validation, or
attestation. Retries, loops, and nested calls use the same owner. Crash
recovery reads only this projection and its referenced subordinate artifacts;
it never derives an ordinal by enumerating scratch, journal, or attestation
paths. Call-frame execution delegates allocation and lifecycle transitions to
the root state owner.

The reusable direct-arm/certified-check launcher receives an equally immutable
`controller_attempt` subject from the experiment controller; it does not
manufacture identity from a filesystem path. Its caller-owned external sink
durably owns a closed `controller_attempt_lifecycle.v1` sequence keyed only by
caller kind and attempt ID. That sequence uses the same launch,
execution/quiescence, `result_terminal: not_applicable`, attestation, cleanup,
and closure ordering and the same greatest-durable-event rule, but has no
prompt-evidence event, typed-result branch, workflow ordinal, or workflow-state
publication. The experiment controller invokes this separate service recovery
matrix; public workflow `resume` never reads or repairs it. A certified check
child receives no credential grant and uses the fresh exact product extract as
its candidate authority. The trusted adapter maps the isolated child exit to
the separately certified typed command record.

For an isolated public run, candidate authority admission starts before any
frontend/build, checkpoint, or result-projection write. The controller pins the
candidate root descriptor-relatively. A fresh run requires `.orchestrate` to be
absent, creates it with `mkdirat` as a private real directory, and pins its
identity; resume opens only the exact previously recorded root/runtime
identities. Every runtime descendant and result parent is then created/opened
relative to those held descriptors with no symlink following or mount crossing.
The authority records and rechecks Linux mount IDs for the candidate,
`.orchestrate`, and every runtime/result ancestor; a different
`STATX_MNT_ID`, including a same-device bind mount, is a crossing. A trusted
`/proc/self/mountinfo` correlation is permitted only when it proves the same
descriptor-bound property; device-number equality is not evidence.
The identities are revalidated before each attempt. Thus a preexisting
`.orchestrate` symlink cannot redirect even an early build write before the
later provider launch guard.

Plan validation rejects:

- an absent, non-directory, or symlinked candidate authority root;
- a candidate authority that contains or is contained by runtime-known
  workflow/source/extern or controller-state roots after canonical resolution;
- provider-environment identity mismatch;
- a provider executable, interpreter, shebang target, ELF dependency, or
  effective `PATH` resolution not backed by the verified rootfs snapshot;
- any mount source or destination outside the closed positive set of candidate,
  run-owned sealed-rootfs snapshot, invocation scratch, and synthetic kernel
  filesystems;
- an ordinary workflow provider without a semantic
  `runtime_structured_result` allocation, including no-bundle and authored
  product-path bundle surfaces;
- a result target whose allocation metadata is not runtime-owned; string-prefix
  checks are not allocation authority;
- a masked runtime root or active-result/staged/archive ancestry containing a
  symlink, special file, nested mount, external alias, or component not opened
  through the pinned runtime descriptor;
- any candidate symlink whose resolved in-root target enters `.orchestrate`, or
  any regular inode with aliases on both sides of that masked boundary;
- any attempt to expose all of candidate `.orchestrate`;
- managed-provider, adjudicated-provider/evaluator, provider-backed summary,
  or live-agent-note execution;
- any command step anywhere in the complete reachable compiled
  required-isolation entry-workflow closure, including loop/branch bodies and
  imported/nested call targets; a later experiment-owned pinned built-in
  adapter seam is not part of this prerequisite runtime;
- authored provider `env`, a requested secret outside the policy allowlist, or
  a requested secret with no controller value;
- unsupported session reuse;
- an unavailable backend or kernel feature; and
- a required local-isolation capability, or a
  `history_retrieval.eligibility_requirement: "require_causal"` capability,
  that the backend cannot enforce.

Evaluator, peer-arm, and parent roots are not generic policy inputs. They are
denied because the projection is a positive allowlist: arbitrary external
roots are absent unless they are one of the four allowed mount classes.
Experiment preflight separately proves symmetric non-overlap between its
evaluator/peer/parent/control authorities and both the admitted candidate and
mutable provider-environment source. The snapshot must occupy only its exact
dedicated state subauthority and its provider-visible manifest paths must pass
the same denials. The G0 sentinel test remains the executable proof of those
experiment-level placements.

### 3. Filesystem projection

The Bubblewrap projection contains:

| Provider-visible surface | Access | Source |
| --- | --- | --- |
| Candidate root at its host absolute path | read/write | candidate product workspace |
| Candidate `.orchestrate` | masked | fresh empty namespace directories |
| Active result-bundle parent | read/write, invocation-private | fresh broker scratch |
| Sealed provider rootfs, including the declared build prefix and conventional loader paths | read-only base | verified run-owned snapshot |
| Provider credentials | environment values only | explicitly named controller variables |
| `/tmp` | read/write, invocation-private | tmpfs |
| `/run` and synthetic `HOME` below it | read/write, invocation-private | tmpfs |
| `/proc` | new PID namespace view | new proc mount |
| device surface | minimal | backend-provided minimal `/dev` |

No general host root, host home, control root, controller state root, evaluator
root, peer root, or parent checkout is mounted. The backend must not use broad
host-source `--ro-bind / /` convenience mounts. A read-only root destination
whose source is the verified run-owned sealed rootfs is the designed base
projection. Executable/library/config discovery is satisfied from that
snapshot, not ambient host directories.

Before admission, the candidate tree receives a
`provider_candidate_admission.v1` scan. It rejects nested mountpoints and every
entry other than a directory, regular file, or safe in-root symlink. For each
regular `(device, inode)`, the scan counts in-candidate paths and requires that
count to equal `st_nlink`; an external hardlink is therefore rejected. The
scan obtains Linux `STATX_MNT_ID` for the pinned root and every no-follow entry
and rejects a different mount ID, so a bind mount of the same filesystem is
still rejected. A trusted `/proc/self/mountinfo` correlation may substitute
only if it proves the same descriptor-bound identity; `st_dev` comparisons
alone are forbidden. The
reserved `.orchestrate` subtree is stricter: every component must be a real
descriptor-resolved directory/regular file created by the runtime, no symlink
may occur inside it or resolve into it from elsewhere in the candidate, and a
regular inode may not have paths both inside and outside it. The active result,
deterministic staged file, invalid-attempt archive, and all of their parent
directories remain below this pinned, provider-masked authority and have no
product-visible alias.
The
candidate root, runtime-known control/source/extern roots, mutable environment
source, and scratch root must be canonically disjoint. The run-owned
environment snapshot may overlap only its exact dedicated subauthority under
the state root; candidate and scratch remain disjoint from it. The candidate is
exclusively owned by the caller for the duration of launch and execution;
experiment arms satisfy this by fresh archive materialization and one active
provider per arm.

Admission walks the candidate descriptor-relatively without following the root
or its ancestors, retains an `O_PATH`/directory descriptor, and records
verified device/inode plus ancestry identity. Immediately before launch it
rechecks that identity and binds the pinned descriptor rather than re-resolving
the candidate pathname. Root or ancestor exchange fails before launch.
Candidate contents remain intentionally writable after launch; exclusive
ownership prevents a trusted non-provider peer from replacing that authority
concurrently.
At admission the candidate root and every existing entry must be
controller-owned and not group/world writable, and the caller holds its
exclusive-ownership lease through process quiescence. Sticky shared ancestors
such as `/tmp` are allowed only when descriptor-pinned and unable to replace
the controller-owned root entry. Because the adversarial provider can later
chmod its writable product, v1 explicitly relies on the threat-model
assumption that non-provider host users/processes do not mutate it during the
invocation; this is not cross-user hostile-host isolation.

The manifest is also checked in provider-visible path space. No rootfs entry
may equal or lie below a runtime- or experiment-denied absolute authority such
as the candidate's lower-layer path, control/source/extern, state, evaluator,
peer, or parent roots. A regular file or symlink may not alias an ancestor of a
denied authority. Required ancestor directories such as `/`, `/home`, and
`/tmp` are allowed only as structural directories with no manifest descendant
at or below the denied authority; the launch overlay then supplies the admitted
candidate/synthetic subtree. Hiding packaged forbidden content with a later
overlay is not accepted evidence.

Candidate mountpoint creation follows a closed overlay rule. V1 admits
candidate roots only below `/home`, `/workspace`, or `/tmp`; the sealed rootfs
contains empty structural mountpoints for those components plus `/run`,
`/proc`, and `/dev`. The selected candidate component is a runtime-owned tmpfs
mount, the launcher creates only the resolved candidate ancestry below it, and
then bind-mounts the pinned candidate descriptor at its full host absolute
path. That first component must not collide
with the sealed provider prefix or reserved rootfs/kernel components such as
`/bin`, `/sbin`, `/usr`, `/lib*`, `/etc`, `/opt`, `/proc`, `/dev`, `/run`, or
`/var`. `/tmp` is an explicit special case: candidate ancestry may be created
inside the already-required invocation-private `/tmp` tmpfs before the exact
candidate bind. This preserves pytest/G0 candidates under `/tmp` without
exposing host temp files. The sealed rootfs need not encode a run-specific
candidate path. `HOME` is created below the invocation-private `/run` tmpfs;
synthetic result ancestry obeys the same declared-overlay rule. Mount-plan
tests cover arbitrary roots within all three admitted components, the exact
`/tmp/.../candidate` case, and collision rejection.

Absolute, broken, and escaping symlinks are rejected by candidate admission
before the namespace is built. Entry names and symlink target text must be
strict UTF-8 and NFC; undecodable/surrogate-escaped or non-NFC bytes are
`provider_isolation_candidate_invalid`. The acceptance suite supplies each form
and proves pre-launch rejection, then separately uses a safe in-root symlink
plus forbidden absolute probe paths to catch an accidental support mount.

The provider receives rendered dependency bytes through the existing prompt
transport. It also receives a canonical, source-mapped rendering of every
declared `provider-result :inputs` value under the accepted consumer-side
rendering contract. The composed-prompt evidence records binding identity,
type, renderer/version, and content digest; the isolation attestation records
only those non-content identities. A value present in state but absent from
the composed provider prompt is a pre-launch contract failure.

Policy-independent Track C1/C6 composition returns validated structured
typed-input evidence to the prompt owner and preserves the existing schema
`2.1` audit/persistence behavior. It does not add a second durable attempt
ledger as part of that correctness fix.

For schema-`2.2` isolated execution, the existing root-owned
`ProviderAttemptScope` allocator allocates once at the start of every retry
iteration, including providers with no content dependencies. One root-owned
`composed_prompt` publication for that ordinal contains dependency rows when
present, typed-input rows, renderer/value/rendered-byte identities, and the
final prompt digest. A second publication kind carries the isolation
attestation reference. Retries and nested calls cannot overwrite one another,
and both records share the same ordinal.

Typed relpaths that name product files remain usable in the candidate. A
future non-product filesystem input must be copied into a phase-specific
read-only snapshot or rejected; v1 must not mount its original control-plane
path. Rendering the typed value, rather than mounting the producer's raw
bundle, is the phase-to-phase scalar channel.

### 4. Phase-private result broker

The executor continues to allocate the host result-bundle path through current
state-layout authority. Before launch, the isolation layer creates an empty
invocation scratch directory and maps it over the provider-visible parent of
the active bundle. Thus the environment variable retains its logical path, but
the provider cannot enumerate the host directory containing prior bundles.

After the provider process becomes quiescent and the retry owner determines
that this exit is eligible for existing typed-result validation, the broker:

1. opens the scratch parent through its already held directory descriptor;
2. pins the exact basename with Linux descriptor-relative
   `openat(O_PATH|O_NOFOLLOW|O_CLOEXEC)` and classifies it with `fstat` before
   any readable open, so rejecting a FIFO or device cannot block or invoke a
   device driver;
3. only after proving that pinned inode is a regular file, obtains an
   `O_RDONLY|O_NONBLOCK|O_CLOEXEC` descriptor for that exact pinned inode (for
   example through the controller's trusted `/proc/self/fd/<pin>`), then
   requires `fstat` identity, type, and mount ID to match the pin before and
   after the bounded copy; it distinguishes absent, directory, symlink/swap,
   special, and oversized results without reopening the untrusted basename;
4. copies at most `result_bundle.max_bytes` from that descriptor to a
   same-filesystem temporary host file;
5. fsyncs the file, atomically renames it at the allocated host target, and
   fsyncs the destination directory; and
6. returns control to the existing typed bundle validator.

If the required Linux descriptor operations are unavailable, the broker fails
with `provider_isolation_bundle_broker_failed`; v1 has no pathname fallback.

If the provider does not write the bundle, the host target remains absent and
the existing missing-bundle contract violation remains authoritative. Files
other than the active target are discarded. Broker transfer does not parse or
approve the typed value; existing result-contract validation retains that
responsibility.

Retention is fixed in v1. For an exit eligible for existing typed validation, a
regular bounded active bundle is published at the existing runtime-owned host
target even when later typed validation fails, and that target remains masked
from every later provider. For a retryable nonzero exit, timeout, or
cancellation, the broker records bounded metadata and a digest directly from
the held descriptor but does not publish the canonical host target. This keeps
a failed write from colliding with the next attempt. Broker-rejected content
and all scratch siblings are never copied. After attestation publication, the
complete invocation scratch tree is removed. Each retry receives fresh
scratch; no policy field changes this behavior.

Canonical-target ownership is journaled before publication. The broker writes
and fsyncs a closed, canonical
`provider_isolation_bundle_transfer.v1` record at the deterministic
scope/ordinal path under the controller attempt authority. The record contains
the invocation identity, deterministic same-filesystem staged-file identity,
canonical target identity, digest/size, validation outcome, archive identity
when applicable, and one of the monotonic states `prepared`, `published`,
`validated`, `rotation_pending`, or `rotated`. The broker then publishes the
target and atomically advances the journal. The existing typed validator runs
as a deterministic, idempotent function of the immutable canonical target,
declared contract, and path authority. The `validated` journal terminal
publication fsyncs the bundle/contract digests, disposition, and—when
valid—the normalized-value digest exactly once; a crash may repeat the
validation invocation, but an exact replay cannot create a second semantic
outcome. The validated journal, atomic workflow-state handoff, and attestation
must agree on `valid` or `invalid`. An attempt that was not eligible for typed
validation has no canonical target journal and is attested as `not_eligible`.

The transition ordering is fixed:

1. write and fsync the deterministic staged file, then write/fsync its exact
   identity and digest in the `prepared` journal before canonical publication;
2. publish and fsync the canonical target, then atomically replace/fsync the
   journal as `published`;
3. run the idempotent existing typed validator and atomically record/fsync its
   one durable `validated` outcome before any terminal result publication;
4. for `valid`, atomically persist the normalized typed value, destination
   step/call-frame result, applicable public/private artifact lineage, and
   matching `result_terminal: published(valid)` handoff in one aggregate-root
   state transaction; for `invalid`, append only
   `result_terminal: published(invalid)`;
5. for a valid result whose runtime plan requires a lexical checkpoint,
   deterministically emit/fsync and revalidate the checkpoint record and index
   from the committed typed value before attestation preparation; record
   `not_required` in the handoff otherwise; and
6. before retrying an `invalid` result, atomically record/fsync
   `rotation_pending`, rotate the canonical file within the same filesystem,
   fsync its directory, then atomically record/fsync `rotated`.

On crash/resume, the controller reconciles the deterministic journal, staged
file, canonical target, archive, matching per-ordinal lifecycle events, and any
prepared/finalized attempt attestation before any new provider launch. A
`prepared` journal with only the exact staged file resumes its atomic rename;
the same journal with only the exact canonical file advances to `published`.
Both or neither location, or any digest mismatch, fails closed. A `published`
journal without `validated` may rerun the idempotent validator, but can publish
only the one exact durable `validated` outcome. A validated-invalid journal
without its terminal event appends only the matching invalid event. A
validated-valid journal without its terminal event uses the immutable bundle
and recorded digests to perform the single atomic workflow-state/result
handoff above; it never appends a valid terminal separately from the typed
value. A valid terminal with an absent or mismatched authoritative state
handoff is invalid state, not a recovery invitation. A crash after that
transaction but before a required lexical checkpoint idempotently emits or
revalidates the deterministic checkpoint from the committed typed value before
attestation. A valid result then completes without relaunch. An invalid result
is moved to a deterministic provider-masked invalid-attempt evidence path
before `attempt_closed` and before a new attempt may launch. A
`rotation_pending` journal recovers idempotently from either side of the rename
by checking the exact recorded digest and file locations.

Missing or broker-rejected eligible output has no fabricated publication event:
the per-ordinal authority records its exact `missing` or `rejected` terminal
variant. A noneligible workflow typed outcome records `not_eligible` without a
transfer journal. A controller-attempt `none` outcome records
`not_applicable` only in its external sink and never creates a transfer
journal. The bundle journal therefore explains file movement only; the
subject-owned lifecycle remains the complete authority for whether an attempt
may finalize or retry.

Before attestation finalization, a staged/canonical/archive file is retained
only when explained by the same scope/ordinal journal; afterward, the journal
and attestation must agree. Any unexplained file, mismatched digest/path,
impossible state/location combination, or duplicate staged/target/archive
fails closed with `provider_isolation_bundle_broker_failed`; no recovery path
blindly unlinks or overwrites any of them.

### 5. Process lifecycle and environment

The backend launches the fully rendered provider argv without a shell and
preserves existing stdin/argv prompt semantics. It uses fresh user, mount, PID,
IPC, and UTS namespaces; maps the controller owner to provider-visible uid/gid
`0:0`; disables nested user namespaces; and assigns a fixed non-host hostname.
It uses Bubblewrap's `--as-pid-1`, so the launch shim and then provider are PID
1 inside the new PID namespace while Bubblewrap's supervisor remains outside
the namespace and absent from its `/proc`. It also uses a new terminal session
(`bwrap --new-session` or an equivalent `setsid` contract), a new process
group, `--die-with-parent`,
no-new-privileges behavior, and zero effective, permitted, and inheritable
capabilities before the provider executable starts. The executable probe must
also observe the exact rootless group-boundary proof below, `NoNewPrivs: 1`,
and zero `CapAmb` and `CapBnd` in `/proc/self/status`; the effective,
permitted, and inheritable sets are `CapEff`, `CapPrm`, and `CapInh`, and all
five fields must be zero.
Session detachment is
required to prevent controlling-terminal `TIOCSTI` escape. Completion is not
reported until the provider process tree is quiescent. Timeout and cancellation
use a kernel-enforced SIGKILL/namespace-destruction path rather than relying on
PID 1's ordinary signal handling, and result brokerage begins only after every
descendant is gone.

#### Rootless supplementary-group and object-authority boundary

V1 does not require or claim an empty supplementary-group vector. On an
ordinary unprivileged Bubblewrap launch, the process can retain the
controller's supplementary kernel group credentials even though
`getgroups(2)` and `/proc/self/status` render each group that lacks a child
mapping as `/proc/sys/kernel/overflowgid`. Those retained kernel credentials
can still satisfy DAC checks on a host object that is actually projected.
Consequently, a one-row `gid_map` is necessary but is not, by itself, the
isolation boundary.

The provider launch is accepted only when all of the following hold:

- Bubblewrap was invoked directly by the unprivileged controller; the launch
  path contains no `sudo`, `pkexec`, privileged `setpriv`, set-id
  group-clearing helper, capability-bearing broker, or equivalent privilege
  transition.
- Before releasing the credential/bootstrap gate, the trusted controller
  reads the pinned final child from the host namespace and requires exactly
  one UID-map row `0 <controller-euid> 1`, exactly one GID-map row
  `0 <controller-egid> 1`, and `setgroups: deny`. The child's underlying
  supplementary-group multiset must exactly equal the controller-bound
  prelaunch multiset. PID reuse, a changed process start identity,
  vector drift, or a read that cannot be tied to the pinned child fails
  closed.
- Inside the namespace, before credentials are read, the shim requires
  all four `/proc/self/status` real/effective/saved/filesystem UID and GID
  columns zero, `setgroups: deny`, one-row maps with no additional child
  identity, nested user namespaces disabled, and every rendered supplementary
  GID either `0` or the exact readable kernel overflow GID. The live overflow
  GID must be nonzero and therefore distinct from the provider primary GID;
  otherwise the backend is unavailable because the two authority classes
  cannot be observed unambiguously. Because map output is relative to the
  reader's user namespace, the shim compares normalized row/count expectations
  supplied by the trusted launch plan rather than pretending that its
  second-column values are host IDs.
  Its normalized primary/overflow counts must match the controller-bound
  counts. Any extra row, mapped supplementary identity, malformed/unreadable
  proc/sysctl input, or enabled group mutation fails before credentials are
  read.
- The positive mount plan contains only the sealed rootfs, the admitted
  candidate, invocation-private result/home/temp surfaces, fresh kernel
  pseudo-filesystems, and minimal devices. No other host object is reachable
  by path. The sealed rootfs is entirely intentional read authority and is
  mounted read-only. Every host-backed writable projection is
  controller-owned, non-group/world-writable at admission, and either the
  intentionally writable candidate or an invocation-private runtime
  authority.
- The final descriptor allowlist is exactly `{0,1,2}`. No host directory,
  file, socket, device, IPC endpoint, process, cgroup, or mount-source
  descriptor survives. PID, IPC, network, UTS, and keyring boundaries remain
  as specified elsewhere in this design.

The latter two bullets are the reason retained groups add no effective
authority: there is no unapproved object on which their host DAC membership can
act. The namespace-map observation only proves that the provider cannot name
or manufacture additional group identities. Tests must include both
directions: a normal rootless launch with inherited groups passes the complete
closed-projection proof, while an extra projected group-readable sentinel,
extra map row, `setgroups: allow`, non-overflow supplementary rendering, or
surviving descriptor fails closed. A clone at another path, alternate `HOME`,
or separate run root can supplement experiment hygiene but never substitutes
for this OS boundary because the same host user can otherwise open both
clones. The overflow GID is read rather than hard-coded. A kernel without the
`/proc/<pid>/setgroups` control, or a host policy that forbids unprivileged
user namespaces, makes `bubblewrap.v1` unavailable.

Before `launch_intent`, the backend creates and pins the selected
crash-durable containment slot and proves it empty. The trusted shim/setup
process enters that slot behind the closed bootstrap release gate. After
`launch_committed` is fsynced, only the fresh transition caller can release the
gate; provider exec cannot precede that event. Normal completion, timeout,
cancellation, and resume after controller crash all terminate/reap through the
same slot and require its kernel empty proof before
`quiescence_terminal`. The slot is controller-only and never mounted or passed
to the provider. Bubblewrap's process group, PID namespace, and
`--die-with-parent` remain defense in depth, not the resume identity.

The controller may pass role-labeled candidate, rootfs, scratch, pinned
backend-executable, seccomp, and credential-bootstrap descriptors to the
trusted setup/shim chain. Every such descriptor is setup-only, `CLOEXEC` at the
appropriate boundary, and closed before the provider executable starts.
Because passing a descriptor through `subprocess` and referencing
`/proc/self/fd/<N>` can clear or outlive `CLOEXEC`, the controller does not
credit that flag or Bubblewrap with final closure: the packaged shim performs
the explicit close-all-above-3 step, then closes credential fd 3. Final
prompt input is argv or fd 0 and output is fd 1/2; the provider descriptor
allowlist is exactly `{0,1,2}`. V1 does not grant a mount-source,
backend executable, result-directory, credential-bootstrap, seccomp, or other
backend-private descriptor. No descriptor for workflow source, prompt assets,
controller state, a forbidden root, or an ancestor directory may cross the
final exec boundary. Descriptor closure is part of the isolation contract; a
mount namespace is insufficient when an inherited directory descriptor can
still escape with `openat("..")`.

The capability probe enumerates every process and accessible descriptor under
the namespace `/proc`, not only `/proc/self/fd`. It verifies PID 1 is the
provider command, no Bubblewrap/setup supervisor is namespace-visible, and
attempts `openat("..")`, `pidfd_getfd`, and ptrace-style duplication against
every observed directory/foreign descriptor. It also probes
`/proc/1/{environ,cmdline,mem,cwd,root}` and requires only the provider's
intentional environment, argv, candidate cwd, and sealed namespace root:
unrelated ambient environment values and host control paths are absent.

Environment inheritance changes under the isolated profile. The controller
execs Bubblewrap with an empty/fixed non-secret environment, Bubblewrap applies
`--clearenv`, and the trusted shim constructs the final provider environment.
The runtime copies only the values in the intersection of the provider step's
declared secret names and `process_environment.credential_env`, then sets
deterministic runtime-owned values:

- `PATH=<provider-visible-declared-environment-prefix>/bin`;
- `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, and `XDG_DATA_HOME` under the
  invocation-private synthetic home;
- `TMPDIR`, `TMP`, and `TEMP` under the invocation-private temp root;
- fixed locale/time values; and
- the active bundle binding for the structured-result workflow mode.

Provider parameters remain rendered argv/input values, not ambient
environment. Authored provider `env` is rejected in v1 rather than silently
dropped. `PYTHONPATH`, host `HOME`/`PATH`, virtual/conda environment variables,
dynamic-loader and interpreter bootstrap variables, Git/SSH agent variables,
editor/session variables, host cache roots, and unrelated secrets are absent.
Supplementary groups satisfy the rootless closed-object contract above, the
provider has no access to an inherited process/session keyring, and the three
key-management syscalls remain denied.
Attestation records granted credential names and presence booleans only, never
values or value hashes. The executable and every interpreter/loader path
resolved for launch must remain inside the frozen snapshot.

The first profile allows only fresh provider invocations. Session resume is
rejected with a stable diagnostic because persistent provider-side state can
carry undeclared information across phases. A later session-capable isolation
design must define session ownership, mounted session state, and intentional
information flow before relaxing this rule.

Managed-provider wrapping currently injects the live controller interpreter,
`PYTHONPATH`, and run-root audit paths. Adjudicated candidates/evaluators and
provider-backed summaries/live notes likewise use different workspace,
concurrency, or result-channel contracts. V1 rejects all of those surfaces at
public preflight and again at the runtime dispatch guard with
`provider_isolation_surface_unsupported`; it never bypasses or accidentally
wraps them. No-policy behavior for these unsupported execution surfaces is
unchanged.

### 5A. Shared-network deployment preflight

V1 does not create a network namespace or egress broker. Immediately before
each launch, the backend therefore captures the provider-reachable network
namespace's pre-existing IPv4/IPv6 TCP/UDP and abstract AF_UNIX listener
inventory through trusted kernel interfaces. Pathname AF_UNIX sockets remain
governed by the mount allowlist; abstract sockets do not. Abstract names are
arbitrary bytes: the closed inventory stores the bytes after the leading NUL
as lowercase hex plus an exact byte length, never as normalized text, and
tests undecodable bytes and embedded NULs. The backend performs bounded negative
probes against a closed, versioned cloud-metadata endpoint set and every
runtime-known Internet or abstract-UNIX orchestrator, dashboard, or
control-service endpoint. A successful connection or any response from a denied
endpoint fails with
`provider_isolation_local_service_exposure` before a provider marker exists.
For TCP and abstract AF_UNIX, completed connection establishment is sufficient:
an endpoint that accepts and immediately closes without sending a response is
still reachable and must fail. UDP reachability uses the bounded
protocol-specific request/response or kernel-error contract; UDP `connect(2)`
success alone is not treated as listener proof.

The capability contract includes a negative test that starts a loopback
sentinel service containing a unique denied value. Preflight must stop the
attempt; allowing the provider to launch or retrieve the value is `I0_BLOCKED`.
The controller writes a private, bounded, closed
`provider_isolation_network_inventory.v1` report with protocol, local
address/port or byte-safe abstract-name hex/length, and owner identity where
safely obtainable.
Before run, an operator reviews that full report and supplies the exact
path/digest plus `accept_unlisted_reachability` decision through
`shared_network_review`. Launch recomputes the inventory and rejects any digest
mismatch. Public attestation contains only the inventory digest/counts,
endpoint-set digest, review decision, safe probe statuses, and explicit
statement that all unlisted local/remote reachability is a deployment trust
assumption; it does not disclose private socket names.

A nonempty reviewed inventory is not an automatic failure. This preflight is an
operational eligibility check, not a network non-interference proof:
deployment owners must ensure no unlisted service reachable with the granted
credential exposes the denied local control plane. `OBSERVATIONAL_ONLY`
history classification never waives this prerequisite.

### 6. Capability separation and historical classification

Filesystem isolation and history-retrieval isolation are different
capabilities:

- Bubblewrap mount isolation can enforce the core filesystem boundary while
  sharing the host network needed for provider API transport.
- Shared network access cannot prove that remote Git, browser, source-search,
  or repository-fetch paths are unavailable.
- A future `CAUSAL_ELIGIBLE` profile must combine provider-tool capability
  controls with an enforceable egress boundary or broker and negative probes.
  Provider API transport must be explicitly allowed through that boundary.
- `eligibility_requirement: "classify"` computes and persists the best
  supported classification without weakening local filesystem isolation.
  `eligibility_requirement: "require_causal"` fails before launch unless the
  complete causal capability set is enforced and probed.

The runtime records one of:

- `CAUSAL_ELIGIBLE`: all four fixed v1 history-retrieval denials are enforced
  and probed while the fixed provider transport allowance succeeds; or
- `OBSERVATIONAL_ONLY`: provider transport works but one or more retrieval
  denials cannot be enforced or demonstrated.

`OBSERVATIONAL_ONLY` is not a core filesystem-isolation failure. It does not
weaken or waive any local control-plane, evaluator, peer, parent, state, or raw
bundle denial.

### 7. Attestation and observability

Every isolated attempt emits a controller-owned
`provider_isolation_attestation.v1` record containing:

- policy, provider-environment, and backend digests;
- backend executable identity and version;
- host capability checks;
- local-listener/cloud-metadata preflight identity and shared-network
  limitation;
- the same closed invocation-subject union used by the launch request:
  `workflow_provider` requires root-owned scope/ordinal, provider-template
  identity, and a typed-bundle channel, while `controller_attempt` requires
  caller-owned kind (`direct_arm` or `certified_check`), attempt ID,
  command/adapter identity, external sink identity, and the `none` channel;
  every cross-variant field combination is forbidden;
- candidate authority and masked relative paths;
- redacted provider-visible mount destinations with access modes;
- for a workflow typed-bundle subject, result-broker source/destination
  identities, transfer outcome, and valid typed-value handoff identity; for a
  controller subject, broker/handoff fields absent and `not_applicable`;
- `lifecycle_prefix_schema` fixed to
  `provider_isolation_lifecycle_prefix.v1` and the exact
  `lifecycle_prefix_digest`, plus terminal
  `execution_terminal`, `quiescence_terminal`, and `result_terminal`
  dispositions, with inapplicable fields forbidden by the tagged variants;
- declared final provider descriptor roles and the backend capability probe's
  final-descriptor inventory and setup-descriptor closure result;
- the rootless group-boundary observation: exact UID/GID map rows,
  `setgroups` state, kernel overflow GID, normalized provider-visible
  supplementary-group vector/count, controller group-vector digest/count, and
  closed-object-projection verdict; host group names are not recorded;
- effective capability classifications;
- process-tree termination outcome; and
- stable failure code when launch does not occur.

`provider_isolation_lifecycle_prefix.v1` is SHA-256 over exactly one
`canonical_isolation_json_bytes` encoding of a closed JSON array. Element zero
is exactly one closed header. The workflow header has exactly the fields
`schema_version`, `subject_kind`, `aggregate_root_identity`, `scope`, and
`ordinal`; the first two values are exactly
`provider_isolation_lifecycle_prefix.v1` and `workflow_provider`, and the
remaining values are the canonical JSON values stored by the aggregate-root
authority for that attempt. The controller header has exactly the fields
`schema_version`, `subject_kind`, `caller_attempt_identity`,
`command_or_adapter_identity`, and `external_sink_identity`; the first two
values are exactly `provider_isolation_lifecycle_prefix.v1` and
`controller_attempt`, and the remaining values are the canonical JSON values
stored by that external sink for that attempt.

The remaining array elements are the already-canonical lifecycle event objects,
in their durable order, beginning with `allocated` and ending with and
including `result_terminal`. No other wrapper, separator, or byte prefix is
hashed; the digest value is the 64-character lowercase hexadecimal SHA-256 of
those canonical bytes. The input explicitly excludes `attestation_prepared`,
isolation-attestation evidence publication, invalid-result rotation, scratch
cleanup, `attempt_closed`, and the attestation record itself. The digest is
therefore non-self-referential and remains byte-stable while those later
events/effects complete.

Before preparing an attestation, and again on state validation, recovery, and
report use, the owning aggregate root or external sink reconstructs the same
closed header and event prefix from its authority, canonicalizes it once, and
requires the recomputed digest to equal `lifecycle_prefix_digest`. A changed
subject tag or identity, cross-subject/scope/ordinal substitution, reordered or
tampered event, extra/missing event within the prefix, or prefix ending before
or after `result_terminal` fails closed. Later attestation, rotation, cleanup,
and closure events must not alter the recomputed digest.

The record has a packaged, closed JSON Schema with
`additionalProperties: false` at every object. The schema expresses the
subject/result/recovery coupling as one discriminated union rather than
independent enums. Capability evidence is a closed
nested object whose rows contain requested mode, enforcement mechanism
identity, probe status, observed result, and rationale code. Attestation JSON
is canonicalized in memory for a deterministic subject-owned path: the
aggregate-root per-ordinal path for `workflow_provider`, or the caller sink's
attempt-ID path for `controller_attempt`. Before any staged or final file
exists, the applicable lifecycle authority fsyncs `attestation_prepared` with
the staged/final identities and digest. It then stages/fsyncs, atomically
publishes/fsyncs the final file and directory, and only then appends
`evidence_published(record_kind=isolation_attestation)`. That finalization
event references the record as `{schema_version, path, sha256}` in the
applicable authority. The path must resolve under that authority (and is stored
as a normalized relative path), and the digest must match before recovery or
report use.
Unknown fields, changed bytes, a mismatched invocation identity, or secret
value-shaped fields make the evidence invalid.

Workflow-provider attestations publish through the schema-`2.2` aggregate-root
state reference and the existing `provider_attempt_allocations` ordinal.
Controller-attempt attestations publish only through the immutable sink
supplied by the experiment controller; they do not allocate or publish into
workflow provider state. The external sink owns the complete
`controller_attempt_lifecycle.v1` recovery sequence and exact-once durable
event publications before the launcher reports completion. It remains keyed
by the caller's immutable attempt ID and is never treated as workflow provider
state or recovered by public workflow `resume`.

The attestation is evidence, not authority for result values. The canonical
policy, validated launch plan, OS backend, and existing bundle validator remain
the authority chain. Provider-visible paths and secret values must be redacted
or represented by stable digests where disclosure would itself leak control
information.

## Contracts And Interfaces

### Public CLI

Add:

```text
orchestrator provider-isolation-environment-manifest \
  --root <absolute-source-root> --provider-prefix <absolute-prefix> \
  --output <absolute-manifest-path>
orchestrator provider-isolation-network-inventory --output <absolute-json-path>
orchestrator run ... --provider-isolation-policy-file <absolute-json-path>
orchestrator resume <run-id> --provider-isolation-policy-file <same-path>
```

The environment command performs the same whole-rootfs no-follow admission and
deterministic prospective assembly—including packaged-shim injection and the
fixed shim/interpreter startup closure—as run, atomically writes the closed
manifest, and prints the digest needed in policy. It does not claim that every
arbitrary executable in the rootfs is launchable. It neither mutates the source
nor marks an environment accepted; run independently rebuilds the run-owned
snapshot, requires that exact digest, and validates the actual resolved
provider entrypoint/shebang/ELF closure from the compiled invocation. The
inventory command writes the closed controller-private report
atomically, prints its canonical digest, and never marks it accepted. The
operator reviews it and places its absolute path/digest/decision in the policy.
Both commands require a pre-existing dedicated controller-owned `0700` output
directory and publish an owner-only `0600`, single-link regular file with
file/directory fsync; neither follows or replaces a symlink or unexplained
existing output. The environment-manifest output authority is disjoint in both
containment directions from its source root, and its basename cannot already
be a scanned source entry, so publishing the report cannot mutate the identity
it reports.
The policy and inventory files are runtime controller inputs and are not copied
into the candidate; the optional manifest output is likewise never copied.
Relative paths are rejected in v1 to avoid workspace-dependent authority.
Resume may recover the original policy/inventory absolute paths from recorded
invocation arguments, but it must verify the same canonical digests and freshly
recomputed inventory; an operator-supplied replacement never silently
supersedes either.

### Provider runtime

`ProviderExecutor` delegates process creation to a launcher interface:

```text
prepare(policy, invocation, subject, typed_inputs, declared_secret_names,
        authored_env)
  -> validated plan + preflight attestation
launch(plan, argv, stdin, env, timeout) -> process result + broker result
recover_workflow_provider(root_state, scope, ordinal) -> reconciled lifecycle
recover_controller_attempt(subject, external_sink) -> reconciled lifecycle
```

`subject` is the closed union defined above; the API has no separate
attempt-identity or result-channel parameters that could be cross-combined.
Workflow recovery reads only the schema-`2.2` aggregate root. Controller
recovery reads only the caller's external sink. Either recovery API rejects
the other authority's fields before effects.

The unrestricted launcher remains the default when no isolation policy is
selected. A required policy never falls back to it. `WorkflowExecutor`, the
public CLI run/resume builders, nested call-frame execution, retries, and loops
must propagate the same root-owned isolation context to this interface; the
provider executor may not infer attempt identity from paths.

The isolated launch request carries declared-secret and authored-env provenance
separately. It must not consume the ordinary merged environment currently
produced for unrestricted launches, because that mapping has already copied
ambient controller variables and cannot distinguish a controller secret from a
step override. The isolated builder reconstructs its environment from fixed
runtime values and the validated controller-secret intersection.

### State and resume

Isolated runs use state schema `2.2`, with immutable isolation-policy identity
and one generalized root-owned `provider_attempt_allocations` projection. It
durably allocates every isolated `workflow_provider` attempt before scratch
creation and owns the closed per-ordinal lifecycle described above. The same
ordinal permits at most one combined `composed_prompt` publication and one
finalized isolation-attestation publication. The latter carries the closed
`{schema_version, path, sha256}` reference; there is no second ordinal,
parallel attempt journal, or parallel attestation-index authority.

Before any launch on resume, the aggregate root manager reconciles every
allocated ordinal in order. Reconciliation is fail-closed and follows this
matrix. It first validates the whole event sequence, derives the greatest
durable lifecycle event, and dispatches exactly that event's legal successor.
An earlier absence rule never wins over a later durable event:

- `allocated` with or without composed-prompt evidence but without
  `launch_intent`, `execution_terminal`, or any later event: consume the
  ordinal as
  `execution_terminal: controller_crash`, append
  `quiescence_terminal: no_process_created`, and continue its result,
  attestation, cleanup, and closure transitions. Resume never silently reuses
  an allocated ordinal as a fresh attempt.
- `launch_intent` without `launch_committed`, `execution_terminal`, or any
  later event: never launch again. Terminate any setup child still held behind
  the deterministic release gate through the exact containment slot, record
  `execution_terminal: controller_crash`, and append
  `quiescence_terminal: namespace_empty`. Missing, ambiguous, or nonempty
  containment proof makes the run non-resumable.
- `launch_committed` without `execution_terminal`: never launch again. Reconcile
  the exact recorded supervisor/process/namespace/containment identity,
  forcibly terminate and reap it if needed, record an exact durable supervisor
  outcome when one exists or `controller_crash` otherwise, and append
  `quiescence_terminal: namespace_empty`.
- `execution_terminal` without `quiescence_terminal`: preserve the terminal
  bytes and append only its variant-required proof. `prelaunch_failed` has no
  intent/commit and receives `no_process_created`. `launch_failed` requires
  intent, reconciles the exact containment slot, and receives
  `namespace_empty`. `controller_crash` receives `no_process_created` only
  without intent and `namespace_empty` after intent. Exit, nonzero, timeout,
  and cancellation require commit and receive `namespace_empty`. Failure to
  prove the required variant fails closed without a second execution terminal,
  launch, brokerage, attestation, closure, or retry.
- `quiescence_terminal` without `result_terminal`: this workflow matrix has no
  `not_applicable`/`none` branch because a schema-`2.2`
  `workflow_provider` always has a typed channel. Record `not_eligible` for
  prelaunch/launch failure, nonzero exit, timeout, cancellation, or controller
  crash; or reconcile the exact typed scratch and subordinate transfer journal
  for an eligible zero exit. A
  published journal permits idempotent validator invocation but only one
  durable `validated` outcome. For `valid`, atomically persist the authoritative
  typed value/artifact lineage and matching result terminal in one root-state
  transaction; for `invalid`, append only the matching invalid terminal.
  Missing and rejected branches append their terminal invalid outcomes without
  inventing a journal. None of these branches relaunches the attempt.
- `result_terminal` without `attestation_prepared`: derive the one canonical
  attestation only after a valid terminal's atomic typed-value handoff is
  present and exact and any required lexical checkpoint/index has been
  durably emitted and revalidated from that value. Then append preparation with
  its paths/digest before writing and proceed to publication. A valid terminal
  with absent or mismatched workflow state is invalid.
- `attestation_prepared` without isolation-attestation evidence: with neither
  path present, recreate the exact prepared bytes; with staged-only, finish the
  atomic rename; with final-only and exact bytes, publish the state reference.
  For a valid typed result, first revalidate its authoritative state handoff and
  required checkpoint/index. Both paths, changed bytes, an unexplained file,
  missing handoff/checkpoint, or lifecycle disagreement fails closed.
- finalized isolation-attestation evidence without `attempt_closed`:
  revalidate its bytes and recompute its
  `provider_isolation_lifecycle_prefix.v1` digest through `result_terminal`,
  finish any required invalid-result rotation, verify the valid typed handoff
  and required checkpoint when applicable, remove only the exact recorded
  scratch tree, and append closure. Later rotation, cleanup, and closure state
  must leave that prefix digest unchanged.
- `attempt_closed`: verify the attestation and terminal transfer evidence and
  any valid typed-value/checkpoint handoff, and perform no second launch, result
  processing, state publication, rotation, cleanup, or evidence publication.
  A missing or mismatched authoritative workflow value is invalid state, never
  reconstructed after closure. A valid result completes from this ordinal; a
  closed retryable disposition permits the retry owner to allocate `N+1`.

Every scope is swept before any provider launch. A later ordinal behind an open
predecessor, impossible transition, duplicate event, wrong identity,
unexpected artifact, or inability to prove quiescence uses the existing
fail-closed state/process/broker diagnostics. Recovery never guesses an
outcome, reuses an ordinal for another process, or overwrites unexplained
bytes.

`controller_attempt` recovery is deliberately separate. The experiment
controller asks the launcher service to reconcile the caller-owned external
sink; public workflow `resume` rejects a `controller_attempt` record or
`result_channel: none` anywhere in `provider_attempt_allocations`. The service
validates the complete external sequence, chooses its greatest durable event,
and applies only the legal successor through quiescence,
`result_terminal: not_applicable`, attestation publication, cleanup, and
closure. It never reads or writes workflow state, a provider ordinal, a typed
bundle journal, or a lexical checkpoint. Conversely, the external sink rejects
`workflow_provider`, typed-channel, root-scope, or provider-ordinal data.

This is intentionally not an additive field under schema `2.1`: an older
runtime must see the unknown schema and reject ordinary resume rather than
ignore an isolation field and continue the same run unrestricted.

The new runtime supports two explicit state cases:

- schema `2.1` remains the unrestricted legacy/current contract and cannot be
  resumed with a required isolation policy; and
- schema `2.2` requires the complete isolation policy, provider-environment,
  and backend identity and cannot be resumed without them.

There is no in-place `2.1` to `2.2` upgrader. An operator who needs isolation
for an old unrestricted run starts a new run. Typed workflow type/value
semantics do not change; schema `2.2` strengthens only the crash-safe ordering
that commits a valid value before attempt closure. `resume --force-restart` is
rejected for schema-`2.2` isolated runs by the new runtime. An older runtime
may offer its historical force-restart
behavior, but that creates a new schema-`2.1` run ID with no isolation
attestation; it is not a continuation and is ineligible for isolated-run or
experiment evidence.
The old-binary rejection claim requires execution evidence from the pinned
pre-feature runtime/wheel against a minimal otherwise-valid schema-`2.2`
state, recording commit/version, wheel digest, exact command, exit, and
rejection output. A test of only the new loader's schema matrix cannot
establish this downgrade property.

Embedded `RunState` objects in `call_frames[*].state` inherit the aggregate
root's schema version. Under an isolated root they are schema `2.2`, contain no
duplicate isolation policy, attempt-allocation, or attestation authority, and
delegate those operations to the root manager. Root/frame schema mismatch,
embedded root-only isolation fields, or a call-frame attempt that cannot be
projected onto its validated `ResumeScopePath` is rejected on load and resume.

### Stable diagnostics

At minimum:

- `provider_isolation_policy_invalid`
- `provider_isolation_backend_unavailable`
- `provider_isolation_environment_mismatch`
- `provider_isolation_environment_invalid`
- `provider_isolation_grant_invalid`
- `provider_isolation_candidate_invalid`
- `provider_isolation_surface_unsupported`
- `provider_isolation_session_unsupported`
- `provider_isolation_attempt_allocation_invalid`
- `provider_isolation_launch_failed`
- `provider_isolation_process_not_quiescent`
- `provider_isolation_bundle_broker_failed`
- `provider_isolation_bundle_oversized`
- `provider_isolation_capability_unavailable`
- `provider_isolation_local_service_exposure`
- `provider_isolation_attestation_invalid`
- `provider_isolation_resume_identity_mismatch`
- `provider_isolation_state_invalid`

Diagnostics distinguish pre-launch apparatus failure from a provider method
failure. They include safe context and never expose credential values.

## Dependencies And Sequencing

1. Add normative provider/security/state/CLI contracts, the versioned policy
   schema, and canonical identity owner.
2. Build the frozen-environment snapshot/identity and pass `I0E` with the real
   intended provider/shim closure before projection work.
3. Pass rootless launch gate `I0G` without `sudo` or another privileged
   launcher. Joint host/inner observations must prove the supplementary-group
   binding and a closed object/descriptor projection; rebuild the sealed
   environment because the reviewed shim identity changes.
4. Pass standalone Bubblewrap `I0` with the exact sealed rootfs, host startup
   closure, candidate admission, process boundary, and deterministic probes
   before changing runtime launch behavior.
5. Implement the phase-private result broker and typed-input consumer carriage.
6. Integrate the launcher into ordinary provider execution, retry, timeout,
   state, and resume paths.
7. Rerun the original public-CLI G0 fixture through the real integrated path.
8. Run a controlled live-provider smoke using the exact packaged environment
   intended for trials.
9. Only after both reviews and fresh evidence may the `.orc` versus one-shot
   plan resume at Task 2.

The legacy command-result adapter's typed pass/fail proof can proceed
independently. It does not establish product-code filesystem isolation; the
zero-credential no-result child-launcher proof is required before G0 can pass.

## Invariants And Failure Modes

### Invariants

- A required isolated invocation never launches through the unrestricted
  subprocess path.
- Provider `cwd` is the candidate authority root inside the namespace.
- No undeclared inherited file or directory descriptor crosses into the
  provider.
- Candidate, rootfs, scratch, and backend-executable setup descriptors are all
  closed before final provider exec.
- Candidate/runtime authority is pinned before the first frontend or state
  projection write, and every isolated `.orchestrate` descendant is accessed
  descriptor-relatively through it.
- The candidate product is writable, but candidate `.orchestrate` is masked.
- Only the current attempt's result scratch is provider-visible.
- Prior raw bundles, checkpoint records, and controller state are not mounted.
- The raw-runtime-bundle denial is a launch-authority property, not a claim that
  collaborating phases cannot relay data through shared product files.
- Raw workflow source, prompt assets, extern manifests, evaluators, peer arms,
  and the parent checkout are not mounted.
- Active prompt/dependency content is delivered without mounting its source
  control path.
- Every declared typed provider input has canonical composed-prompt evidence;
  a state-only value is a pre-launch failure.
- Isolated process environments contain only fixed runtime values and the
  per-step/policy direct credential intersection.
- Passing I0/G0 requires the denied-endpoint/cloud-metadata operational
  preflight and explicit review of the remaining listener trust assumption;
  `OBSERVATIONAL_ONLY` does not waive either.
- Provider executable, interpreter, loader, and `PATH` resolution remain
  inside the verified environment snapshot.
- Host and provider-visible result paths are mapped explicitly; the provider
  never receives a host control-state path as a usable filesystem grant.
- One root-owned `(scope, ordinal)` record is the attempt lifecycle authority;
  `launch_intent` prevents relaunch, every terminal branch proves quiescence,
  and result/attestation publications are exact-once.
- Resume requires the same policy, provider environment, and backend contract.
- An isolated run is schema `2.2`; schema `2.1` can never carry or resume as an
  isolated run.
- `OBSERVATIONAL_ONLY` never appears as evidence of denied history retrieval.
- Product projection and review packages continue to exclude `.orchestrate`.

### Failure modes

| Failure | Required behavior |
| --- | --- |
| Bubblewrap missing or user namespaces disabled | Fail before provider launch with `provider_isolation_backend_unavailable` |
| Fixed Bubblewrap path/ancestor or host loader/library/cache closure trust fails, or a PATH/user-owned same-version fake is offered | Fail backend preflight; never execute the fake or changed closure |
| Provider environment digest mismatch | Fail before launch; do not inspect ambient host binaries |
| Provider environment has xattrs, special files, unsafe links/mounts, or external hardlinks | Reject before snapshot/launch with `provider_isolation_environment_invalid` |
| Candidate has unsafe links, special files, nested mounts, external hardlinks, or overlapping authority | Reject before launch with `provider_isolation_candidate_invalid` |
| Fresh/resumed `.orchestrate`, result ancestry, or runtime identity is symlinked, aliased, mounted, or swapped | Reject before any affected build/state/result write with `provider_isolation_candidate_invalid` |
| Grant overlaps a denied authority | Reject policy/plan with `provider_isolation_grant_invalid` |
| Active bundle scratch missing or invalid | Preserve existing missing/invalid bundle semantics or emit broker failure when transfer itself fails |
| Provider writes siblings beside active bundle | Discard siblings; do not publish them |
| Canonical result/archive exists without an exactly matching transfer journal and attestation lifecycle | Fail closed with `provider_isolation_bundle_broker_failed`; never unlink or overwrite it |
| Crash after `launch_intent` or `launch_committed` | Reconcile/terminate only the exact recorded gated launch, prove quiescence, and finalize its failure attestation; never launch that ordinal again |
| Crash after durable `execution_terminal: prelaunch_failed` or `launch_failed` but before quiescence | Select that terminal as the greatest durable event, preserve it byte-for-byte, and append only `no_process_created` for prelaunch failure or exact-slot `namespace_empty` for launch failure; never route through an earlier prefix or append another execution terminal |
| Crash during typed validation, after the `validated` journal, or between valid result handoff and checkpoint | Validation invocation may replay idempotently, but publish one durable validation outcome; atomically persist the valid workflow value with its result terminal, then emit/revalidate any required checkpoint before attestation and closure |
| Duplicate, reordered, impossible, or mismatched per-ordinal lifecycle event | Reject resume with `provider_isolation_state_invalid`; do not infer outcome, allocate a retry, or publish evidence |
| Crash before or after attestation publication | Reconcile the exact `attestation_prepared` staged/final identity, publish at most one isolation-attestation evidence event, finish cleanup/rotation, and append at most one `attempt_closed`; any byte or lifecycle mismatch fails with `provider_isolation_attestation_invalid` |
| Subject, result channel, and recovery authority are cross-combined | Reject before allocation/scratch/launch; public workflow resume accepts only typed `workflow_provider` root records, while controller-sink recovery accepts only `controller_attempt` plus `none` |
| A setup-only or undeclared descriptor reaches final provider exec | Fail the capability probe/launch with `provider_isolation_launch_failed`; do not accept the backend |
| Provider uid/gid mapping, zero capability sets, nested-userns denial, or fixed hostname cannot be proved | Fail backend preflight; do not launch |
| Cloud metadata or a closed-set local control endpoint is provider-reachable | Fail before launch with `provider_isolation_local_service_exposure`; the host is ineligible for I0/G0 |
| Unlisted local/remote reachability is not reviewed or is found to expose denied authority | Do not claim I0/G0; the attested deployment trust assumption is unsatisfied |
| Child leaves descendants | Terminate namespace; mark attempt apparatus failure until quiescence is proved |
| Retry requested | Allocate fresh namespace and result scratch; do not expose failed raw output |
| Retryable attempt writes a bundle | Attest bounded metadata/digest, discard exact scratch, leave canonical host target absent, append `attempt_closed`, then allocate/launch a retry with fresh scratch |
| Authored provider env requested | Reject before launch with `provider_isolation_surface_unsupported`; do not silently drop it |
| Declared secret is missing or outside the policy allowlist | Reject before launch with `provider_isolation_grant_invalid`; do not broaden the grant |
| Managed/adjudicated/summary/live-note provider surface requested | Reject at public preflight and runtime dispatch with `provider_isolation_surface_unsupported` |
| Prerequisite required-isolation workflow contains any command step | Reject the compiled surface before any provider or command launch with `provider_isolation_surface_unsupported`; later certified-adapter admission requires a pinned built-in contract and isolated child launcher |
| Policy/environment/backend/snapshot resume identity mismatch | Reject before provider launch with `provider_isolation_resume_identity_mismatch` |
| Schema `2.1` plus required isolation, schema `2.2` without complete identity, or root/call-frame mismatch | Reject resume with `provider_isolation_state_invalid`; never infer or drop the boundary |
| `--force-restart` targets schema `2.2` | Reject in the isolation-aware runtime; an externally produced new unrestricted run has a different ID and is never accepted as continuation evidence |
| Network/tool denial unavailable | Record `OBSERVATIONAL_ONLY`; fail only when caller explicitly requires causal eligibility |
| Unsupported shared session | Reject before launch with `provider_isolation_session_unsupported` |

## Security, Operations, And Performance

This design reduces provider filesystem authority and changes how provider
credentials and executable environments are supplied. Packaging must avoid
copying broad host homes or mutable caches. Direct credential grants should be
limited to provider transport and rotated/audited under existing operational
policy. Because v1 shares general remote egress, operators must also verify
that no reachable service can turn those credentials into access to denied
local control data.

Bubblewrap adds one namespace construction per provider attempt and an output
copy at the result boundary. The expected cost is small relative to provider
latency, but startup, large executable environments, and result-size bounds
must be measured. Provider environments should be content-addressed and reused
read-only; invocation homes, temp roots, and result scratch remain private.

Operators need a preflight command or report that distinguishes backend
availability, environment mismatch, filesystem enforcement, and historical
retrieval classification. Rollback is selecting no isolation policy for
trusted workflows; evidence-grade workflows must never use rollback as a
transparent fallback.

## Evidence And Implementation Boundaries

The implementation is the provider subprocess path used by the public
`orchestrator run` and `resume` commands. A test that directly calls Bubblewrap,
a PATH-shadowed provider fixture, a copied candidate workspace, or an external
wrapper is only supporting evidence unless the public runtime creates the same
validated plan and launcher.

The original G0 fixture remains the primary integration acceptance scenario
after the prerequisite lands. It must use:

- the public CLI;
- absolute external workflow/prompt/extern paths;
- an external `--state-dir`;
- the built-in provider resolution path;
- two provider phases and real typed bundle validation; and
- known forbidden sentinels plus enumeration of prior runtime files.

The fixture's provider script is an adversarial observer, not the isolation
implementation. A pass must be accompanied by backend attestation showing that
the production launcher path was selected. Raw diagnostic artifacts are
evidence-only and do not override runtime state or typed results.

The passing rerun is recorded in the exact companion report
`docs/reports/2026-07-23-experiment-control-plane-feasibility-rerun.md`.
That report must identify the passing runtime commit, public CLI command,
policy/environment/backend identities, test node IDs and results, attestation
digests, and product manifests. The historical feasibility report remains
`G0_BLOCKED`; it links to the companion only after that evidence exists.

## Compatibility And Migration

- Existing workflows without `--provider-isolation-policy-file` retain the
  existing unrestricted launcher/security/state-schema contract. Affected
  `provider-result :inputs` workflows receive the policy-independent C1/C6
  correctness fix, so their declared typed prompt values are no longer
  silently dropped; compatibility tests cover that intentional prompt-input
  change.
- Existing built-in provider names remain valid. Their own bypass flags do not
  provide isolation; when wrapped by a required outer profile, the outer
  namespace is the security boundary.
- Existing schema `2.1` state can be inspected and resumed only under its
  original unrestricted contract. It is not upgraded in place to isolated
  provenance.
- New isolated runs use schema `2.2`. Older runtimes reject ordinary resume of
  that schema before execution, closing the same-lineage downgrade path that an
  additive `2.1` field would create. Their historical force-restart route is a
  distinct unrestricted lineage and is excluded by run-ID/attestation checks.
- A new runtime accepts schema `2.1` only for unrestricted resume and schema
  `2.2` only with complete isolation identity. Resume with no policy, a changed
  policy, or a different provider environment is rejected.
- Isolation-aware `resume --force-restart` rejects schema `2.2`. A new run
  created by an older unrestricted binary has schema `2.1`, a new run ID, and
  no isolation attestation; controllers and reports must reject it rather than
  link it to the isolated lineage.
- No new Workflow Lisp syntax or output authority is introduced. This
  prerequisite explicitly absorbs narrow Track C1 carriage plus the necessary
  Track C6 implicit-default-selection slice for existing
  `provider-result :inputs`: it changes current partial behavior so every
  declared typed value selects one deterministic registered renderer and is
  rendered at the provider consumer seam with evidence. The governing umbrella
  design and capability status must record this exact implemented slice while
  leaving C2–C5 and the remaining C6 ergonomics future/partial.
- Command and adjudicated-provider contracts do not gain implicit sandbox
  guarantees. Adjudicated candidates may opt into the same provider launcher
  only after a separate integration review proves its candidate/promotion
  lifecycle remains correct.

## Verification Strategy

### Unit and contract tests

- Policy schema, whole-policy canonical digest, distinct canonical
  `provider_environment.digest`, independent golden vectors, absolute-path
  validation, grant overlap, and fail-closed backend selection.
- `provider_isolation_lifecycle_prefix.v1` ASCII/Unicode canonical-byte and
  digest goldens for both subject variants; identity, event, ordering,
  extra/missing, cross-subject/scope/ordinal, and prefix-boundary tamper
  rejection; recovery recomputation; and digest stability after
  `attestation_prepared`, attestation publication, rotation, cleanup, and
  `attempt_closed`.
- Bubblewrap executable plus non-executingly resolved host startup-closure
  identity, including same-version executable, loader/library/cache replacement,
  unsafe RPATH/RUNPATH, and `/etc/ld.so.preload` rejection.
- Frozen-environment manifest canonicalization, xattr/special-node/link/mount
  rejection (including same-device bind mounts by Linux mount ID),
  descriptor-relative snapshotting, source/snapshot mutation, and
  executable/interpreter resolution inside the snapshot.
- Candidate admission for nested mounts, special nodes, unsafe symlinks,
  external hardlinks, root aliases, runtime-boundary aliases, early
  `.orchestrate` admission, same-device bind mounts in candidate/runtime
  ancestry, and concurrent ownership.
- Mount-plan generation for candidate, masked runtime root, provider
  environment, invocation-private `/run` plus synthetic home, `/tmp`, proc,
  active bundle scratch, new terminal session, user/UID/GID mapping,
  nested-userns denial, fixed hostname, zero capability sets, and absence of
  broad host grants.
- Crash-durable containment-slot admission, exact membership, gated provider
  release only after fresh `launch_committed`, kernel empty proof, PID-reuse
  resistance, and fail-closed backend selection when the selected mechanism is
  unavailable.
- Result broker behavior for valid, missing, directory, symlink, oversized,
  device-safe `O_PATH` classification, mutating/swapped/FIFO outputs, sibling
  outputs, transfer-journal crash
  recovery, invalid-result rotation, crash-safe file/directory fsync, fixed
  retention, and failed-write-to-successful-retry behavior.
- Environment allowlisting, rejection of authored/bootstrap environment,
  per-step/policy secret intersection, and secret-safe attestation.
- Local-listener inventory, closed denied-endpoint/cloud-metadata probes,
  explicit remaining-reachability trust assumption, and fail-closed registered
  loopback sentinel-service detection.
- Closed attestation schema, canonical state reference/digest validation,
  tamper rejection, and root-owned attempt allocation/lifecycle across plain
  steps, retries, loops, calls, crash, and reload. Crash injection covers after
  allocation, launch intent, gated launch commit, process terminal,
  quiescence, typed publication/validation, atomic workflow-value/result
  handoff, required checkpoint persistence, attestation preparation before any
  file write, attestation publication, invalid-result rotation, scratch
  cleanup, and `attempt_closed`. Crash-before-quiescence cases explicitly cover
  durable `prelaunch_failed` and `launch_failed`, preserve the terminal bytes,
  append only `no_process_created` or exact-slot `namespace_empty`
  respectively, and prove no second terminal or relaunch. The matrix also
  covers nonzero exit, timeout, cancellation, missing/rejected/invalid bundles,
  idempotent validation with exactly-once durable terminal publication, and
  exact no-relaunch/no-double-publication behavior.
- Closed request-union and recovery-authority tests reject
  `workflow_provider` with `none` or an external sink and reject
  `controller_attempt` with a typed channel, root scope/ordinal, provider
  template, or any `provider_attempt_allocations` entry. Separate
  controller-sink crash tests cover the `none` result through external
  lifecycle closure without public workflow resume.
- Declared scalar and relpath consumer rendering, including a failure when a
  typed value exists in state but lacks composed-prompt evidence.
- Resume compatibility for exact match and every identity mismatch, including
  changing a non-environment policy field while preserving
  `provider_environment.digest`, changing the canonical environment manifest
  while preserving unrelated policy fields, and rejecting swapped/cross-filled
  digest values.
- A recorded pinned pre-feature-runtime execution proving its ordinary resume
  rejects `2.2`, plus new-runtime state-schema tests proving schema `2.1`
  cannot opt into isolation on resume and schema `2.2` cannot drop or omit
  isolation identity.
- Force-restart tests proving the isolation-aware runtime rejects schema `2.2`
  and no new unrestricted run can satisfy the original run/attestation
  identity.
- Stable diagnostic classification.

### Backend integration tests

- The provider can read/write the candidate and execute a packaged tool.
- Absolute reads of control, evaluator, peer, parent, and controller sentinels
  fail.
- A forbidden sentinel opened by the controller before launch is still
  unreadable through `/proc/self/fd` or descriptor-relative access.
- The probe enumerates every final provider descriptor, rejects anything beyond
  the declared transport set, and attempts `openat("..")` on every observed
  directory descriptor; attestation proves all setup descriptors closed.
- Host-relative and inner-namespace observations jointly prove the exact
  rootless supplementary-group/object-authority contract: bound inherited
  multiset, one-row maps, `setgroups: deny`, primary/overflow-only inner
  rendering, normalized count agreement, and a closed mount/descriptor
  projection. The same probe proves provider-visible uid/gid `0:0`,
  `NoNewPrivs: 1`, and zero effective, permitted, inheritable, ambient, and
  bounding capabilities; nested user-namespace creation fails, and hostname
  is the fixed isolated value.
- A loopback service exposing a unique denied sentinel is detected by preflight
  and prevents provider launch, including accept-and-close without a response;
  passing-host evidence records the reviewed inventory and no reachable
  closed-set cloud-metadata/control endpoint.
- Relative and absolute symlinks do not escape to denied roots.
- Candidate `.orchestrate` is masked.
- Phase two consumes the declared typed value/path but cannot enumerate or read
  phase one's raw result.
- The provider cannot use a controlling terminal or inherited descriptor to
  recover host authority.
- Timeout/cancellation leaves no provider descendants.
- Backend unavailability fails before the provider fixture runs.

### Public CLI and live smoke

- Compile and run a two-phase external `.orc` workflow through the public CLI,
  then verify typed completion, product write, denial probes, product manifest,
  state provenance, and attestation.
- Rerun the certified command-result cases to ensure the prerequisite does not
  regress existing boundary behavior.
- Run one controlled provider-API smoke from the frozen environment. It must
  edit only the candidate, return a typed bundle, and leave the forbidden
  sentinel probes denied.
- Run the narrow selectors first, then the repository's prescribed parallel
  broad suite in tmux.

## Declarative Acceptance / Integration Scenarios

### Scenario A: isolated two-phase public CLI run

Initial state:

- external control root containing one two-phase `.orc`, active/inactive
  prompts, and extern manifests;
- candidate root containing only the visible task/product files;
- external controller-state, evaluator, peer-arm, and parent-checkout
  sentinels;
- a digest-verified provider environment; and
- `provider_phase_isolation.v1` with `mode: required`.

Entrypoint: `python -m orchestrator run` with the external workflow path,
external source/extern paths, a separate controller-input policy path,
candidate `cwd`, and external `--state-dir`.

Expected result:

- both phases complete through ordinary provider and typed-result runtime
  paths;
- phase two receives its declared typed value/path;
- the provider observes candidate `cwd`, reads the task, and writes the product
  marker;
- no `.orc`, prompt manifest, provider manifest, command manifest, or runtime
  state enters the product projection;
- every known forbidden read and every enumerated prior-runtime read fails;
- only the active result scratch is visible per phase; and
- state contains a matching isolation attestation.

Forbidden behavior: unrestricted fallback, readable prior bundle, readable
controller state, readable inactive prompt/evaluator/peer/parent sentinel, or a
product manifest containing `.orchestrate`.

Real dependencies: public CLI, frontend build, runtime executor, state manager,
Bubblewrap, and result validator. Fixture-backed dependency: provider model
process. This proves the production integration path because the fixture is
selected through ordinary built-in provider command resolution and the state
attests the runtime launcher.

### Scenario B: fail closed when enforcement is unavailable

Initial state: the same workflow and policy, but Bubblewrap is absent or its
required namespace capability probe fails.

Entrypoint: the same public CLI.

Expected result: the run fails before the provider marker is created, records
`provider_isolation_backend_unavailable`, and contains no typed provider result.

Forbidden behavior: launching the provider with ordinary `subprocess` or
changing the run to an unrestricted classification.

### Scenario C: truthful historical-policy classification

Initial state: filesystem isolation passes and provider API transport works,
but the selected profile cannot enforce one of remote Git, browser,
source-search, or repository-fetch denial.

Entrypoint: isolation preflight plus one provider transport probe.

Expected result: local filesystem isolation remains usable and the persisted
classification is `OBSERVATIONAL_ONLY`.

Forbidden behavior: emitting `CAUSAL_ELIGIBLE`, weakening local sentinel
denials, or representing a missing probe as a denial.

## Success Criteria

- Normative specs define the new policy, state, resume, and diagnostic
  contracts.
- Required isolation selects the production launcher and cannot fall back.
- All Scenario A positive and negative assertions pass through the public CLI.
- The controller-attempt certified-check fixture executes provider-authored
  product code through the zero-credential no-result launcher, denies every G0
  sentinel/confused-deputy path, and emits the matching tagged attestation.
- Scenario B proves fail-closed behavior before provider launch.
- Scenario C reports capability separation truthfully.
- Result brokerage preserves current typed bundle validation, including missing
  and invalid result behavior.
- Exact policy/environment/backend identity is recorded and resume-enforced.
- One controlled live-provider smoke passes with the intended frozen
  environment.
- Narrow, integration, smoke, and broad verification are fresh and green.
- Specification and quality reviews approve the implementation and evidence.

Task sequencing reruns G0 before the live/broad closure. Only after that G0
rerun and every remaining success criterion/review passes may the blocked
`.orc` versus one-shot plan proceed at Task 2.

## Stop / Revise Criteria

Revisit this design if:

- Bubblewrap cannot launch the intended provider environment without broad host
  root/home mounts;
- preserving candidate product editing requires mounting any control,
  evaluator, peer, parent, or controller authority;
- the output broker cannot preserve existing missing/invalid bundle semantics;
- descendants cannot be made reliably quiescent on timeout/cancellation;
- resume cannot bind the exact policy/environment/backend identity;
- a test passes only through a wrapper or fixture path that the public runtime
  does not use; or
- implementation expands into general command sandboxing, multi-platform
  parity, or shared-session information flow without a new reviewed design.

## Documentation Impact

Implementation must update:

- `specs/index.md`
- `specs/versioning.md`
- `specs/acceptance/index.md`
- `specs/providers.md`
- `specs/security.md`
- `specs/state.md`
- `specs/io.md`
- `specs/cli.md`
- `docs/capability_status_matrix.md`
- `docs/design/README.md`
- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/index.md`
- the `.orc` versus one-shot feasibility report after G0 is rerun
- the exact passing companion report
  `docs/reports/2026-07-23-experiment-control-plane-feasibility-rerun.md`

The current feasibility report remains historical evidence of the pre-feature
runtime and must not be rewritten to imply the prerequisite already existed.

## Implementation Handoff

Use the companion
[implementation plan](../plans/2026-07-23-provider-phase-information-isolation.md).
The likely code owners are:

- provider policy/types and executable environment validation under
  `orchestrator/providers/`;
- a Bubblewrap backend and result broker under
  `orchestrator/providers/`;
- provider launch integration in `orchestrator/providers/executor.py`;
- public runtime-context construction and propagation in
  `orchestrator/workflow/executor.py`, including the nested executor seam in
  `orchestrator/workflow/calls.py` and root-delegating state in
  `orchestrator/workflow/call_frame_state.py`;
- accepted typed-input lowering/rendering in
  `orchestrator/workflow_lisp/lowering/phase_scope.py`,
  `orchestrator/workflow_lisp/lowering/effects.py`,
  `orchestrator/workflow_lisp/typed_prompt_inputs.py`, and
  `orchestrator/workflow/prompting.py`;
- CLI run/resume policy loading under `orchestrator/cli/`;
- immutable run provenance in state management; and
- focused backend plus public-CLI integration tests under `tests/`.

Do not implement this as an experiment-only wrapper. The experiment consumes
the reusable runtime capability after it is independently accepted. Before the
experiment plan implements its `DIRECT` arm, that plan must add adoption tests
for this same launcher service with `result_channel: "none"` and
controller-owned attempt identity; raw `ArmCommand` execution is not eligible
to launch a provider.
