# OMP Providers And Native Continuation

Status: current component contract for retained OMP provider calls and verified
native continuation of existing sessions. [Providers](../../specs/providers.md),
[CLI](../../specs/cli.md), [state](../../specs/state.md) and
[security](../../specs/security.md) own their respective contracts. The
[upgrade runbook](../omp_upgrade_runbook.md) owns installation, the code-owned pin
and qualification procedure. The original [integration design and roadmap](../plans/2026-08-14-omp-integration-design-and-roadmap.md)
preserves implementation history, exact historical creation schemas and receipts.

The executable cutoff retired prompt creation, scaffold generation/rerun,
`prompt import` in every mode and workflow session-artifact publication on retired
targets. Their old acceptance scenarios are historical. Native `prompt resume`
retains its read-side scaffold/link/journal validation and is independent of
workflow compile, run and resume. New Agent Sessions have their own
[contract](workflow_lisp_agent_sessions.md); they do not implicitly restore the
OMP scaffold lifecycle.

## Templates, Pin And Trust Lanes

The code-owned public family is `omp`, `omp_unrestricted_workspace`,
`omp_no_tools` and `omp_conf`; `omp_conf_inference` is an internal inference
selector, not public author choice or a secrecy boundary. Templates use stdin
and the `omp_json_stdout` codec through
`python -m orchestrator.providers.omp_launch`. Ordinary admitted calls use
`--no-session`. There is no template resume command or turn-boundary resume.
Workflows cannot override executable, lane, approval mode or launch environment.
Template presence does not establish general evaluated-call availability:
`omp_conf` requires an admitted `omp_conf_root` in substituted parameters, while
the current evaluated performer supplies empty native params/context and has no
route to supply that root. This document retains conf admission and existing
conf-session continuation contracts; it does not enable that missing invocation
path.

`omp` (write approval) and `omp_unrestricted_workspace` (`--yolo`) use the
workspace and inherited ambient environment/profile. They require trusted
operator configuration and are not hermetic or closed capability inventories.
`omp_no_tools`, `omp_conf` and internal inference use fresh HOME/XDG/temp/process
cwd roots, a positive child environment, admitted conf bytes and the code-owned
Landlock ABI-3-or-newer write policy. No-tools/inference expose neither tools nor
workspace context; conf exposes the recorded workspace as repository context.

Binary admission requires Linux `x86_64`, AVX2 and the exact
`OmpBinaryPin` version/digest in code. Profile-isolated lanes additionally require
Landlock ABI 3 or newer; ambient launches use the execution-only helper prefix
and do not claim profile confinement. The adapter resolves OMP once from `PATH`,
rejects non-regular/symlink, wrongly owned or writable executable inputs, reads
and copies the pinned binary by descriptor into an exclusive private attempt
root, verifies the private copy and executes that copy. Version probe and run use
the same lane environment and cwd. The probe must return the exact pinned UTF-8
version line, exit zero and no stderr; source-path replacement cannot redirect
execution after verification. The runbook owns upgrades; a historical launch
receipt never admits another binary.

## Profile Environment And Conf Admission

Profile launches require the caller roots and admitted PATH specified in the
runbook. The adapter generates fresh child roots, sets
`PI_CODING_AGENT_DIR=HOME/.omp/agent`, unsets `PI_CONFIG_DIR`, and admits only the
code-owned positive environment (including required PATH/shell and allowed
locale/certificate entries). The child receives no
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. Credentials enter through the current
`OMP_AUTH_BROKER_URL`/`OMP_AUTH_BROKER_TOKEN` pair; the adapter does not start a
broker. URL admission requires HTTP, loopback IP literal, explicit port 1..65535,
and no userinfo/query/fragment; `localhost` is not an IP literal.

`omp_conf` is a trusted credential-bearing tool lane. Same-UID reads, network and
process access remain; tools can observe broker credentials in environment or
procfs and persist them in output/journals. Profile isolation is neither a secret
vault nor model/same-UID confidentiality. No-tools disables the model-to-tool
path, without claiming a general OS sandbox.

Conf is a closed, content-addressed tree: `config.yml`, optional
`agent/WATCHDOG.yml`, and one-level `agent/agents/*.md`. Descriptor-relative
no-follow admission rejects symlinks, special entries, duplicate hardlinks and
path escapes. UTF-8 safe YAML rejects duplicate keys, tags, aliases, anchors,
merges and command indirection; unknown keys fail closed.

Admitted configuration fixes memory off, bounds task concurrency to 1..32 and
recursion to 0..2, checks adviser booleans, and disables the exact pinned bundled
agent set. The optional task-approval setting is admitted only with declared
custom agents; the pinned overlay prevents headless child tasks inheriting an
unrestricted writer. Agent names/descriptions are nonempty, names are unique
and nonbundled, optional model/tools/spawns are closed and refer to admitted
names; no wildcard expands authority. WATCHDOG advisers are unique with bounded
read/grep/glob tools and validated instructions. Instruction imports via `@`
are rejected outside inline/fenced code (ordinary mid-token email is not an
import). Admitted prose remains trusted author input, not semantic verification.
The launch/conf modules and runbook own exact key/tool/name allowlists.

Landlock policy protects code-owned input/conf roots while admitting only the
lane's required write roots; every descendant inherits it. Conf additionally
admits its recorded workspace. The frozen conf copy is outside the write
allowlist. Child task configuration cannot widen this policy.

## Codec And Result Authority

`omp_json_stdout` is a state machine for the pinned event protocol, not arbitrary
JSON/text extraction. It validates recognized schemas, event order, assistant
text/usage closure, final terminal and the sole adapter frame. Malformed UTF-8,
JSON, recognized events, early EOF or inconsistent settlement fail even with
exit zero. Unknown events remain opaque, behaviorless observations and cannot
supply output/usage or authenticate settlement. A closed non-assistant lifecycle
arms a response boundary; the next closed assistant replaces earlier output.
Without that next assistant, prior output remains. Observation callbacks still
receive all validated assistant text fragments. Safe display projection does not
rewrite captured raw evidence.

The validated normalized final assistant JSON is parent-materialized into the
attempt's absent result leaf with descriptor-relative no-follow traversal and
exclusive creation. Existing/planted leaves fail. The output contract performs
semantic validation; journal/codec observations never replace it.
[Provider result delivery](provider_result_delivery.md) owns OMP's retained
`legacy` rendering selector and single result carrier. This is not assistant-text
fallback for an ordinary file-transport provider.

## Existing Session Evidence: Current Read Contract

Historical sessions have run-relative metadata/live/snapshot/optional-conf,
`session_link.v1` and `session_continuation.v1` siblings described by
[state](../../specs/state.md). The closed schemas remain required for reading and
native continuation even though their original creation commands are retired.
They bind exact run/step/visit/workspace, scaffold identity, source/composed/
authored prompt and semantic-contract digests, provider/model/lane, binary pin,
non-secret launch projection and null-or-closed confinement. Nullable fields are
explicit nulls; hashes and normalized confined relative paths validate strictly.
These are consistency observations under an operator-trusted root, not
model-resistant authenticated provenance. Raw journals remain sensitive.

`prompt_resume_preflight.capture_scaffold_inputs` and
`prompt_session_scaffold.verify_private_scaffold` remain live readers. They check
public/private scaffold bytes and manifests, exact `run.orc` source, semantic
output contract, authored/composed prompt digests, provider/model/lane, frozen
conf, link and current binary pin. Retained historical rendering is used only
to verify exact old bytes. This compiler-independent operation does not compile,
regenerate, repair or republish a scaffold. `verify_captured_occupant` and the
journal readers still enforce captured identity and scaffold/conf/link agreement.

The pinned physical journal parser validates the fixed 256-byte title slot,
sole matching session header, recognized entry types, unique IDs, preceding
parents, one null-parent root and acyclic graph. The last physical entry selects
the active leaf; its branch cannot introduce an agent `session_init`. Unknown
entry types and malformed/ambiguous records fail. Current native validation
retains these checks from the historical bridge; retiring reverse import does
not remove them.

## Native Resume Lookup And Locking

`orchestrator prompt resume <run-or-session-id> [--in-place]` requires fd 0, 1 and
2 to be TTYs before locking or launching. Unknown/repeated flags or extra
positionals fail. The argument is exactly one nonempty basename, excluding dot,
dot-dot, slash, backslash, NUL and absolute paths. Under the configured opened
runs root, exact run-directory match wins and requires one valid link; otherwise
lookup matches exact active session ID, then exact primary basename. Only linked
primaries and successful primary forks are indexed. Zero/multiple matches fail
with not-found/ambiguous; ambiguity exposes run/visit IDs only. No prefix,
child/adviser lookup or arbitrary path delegation is admitted.

The exclusive per-session lock covers all preflight, interactive child,
postconditions and no-replace continuation append. It is not a workspace
execution lock. Under the lock, descriptor-relative no-follow readers validate
link, contiguous chain, state, scaffold, primary identity and latest live
manifest against the current pin. A verified private binary is copied/probed
again. Setup/identity failure starts no child and appends nothing.

Ambient continuation uses current ambient configuration and recorded workspace.
Profile continuation reconstructs `omp_conf_env.v1` with current broker
credentials and a verified runtime copy of frozen conf, never the original conf
root. Fresh cwd and code-owned lane flags preserve no-tools versus workspace
context, approval and inherited Landlock restrictions. Argv/environment-name
reporting contains no secrets. This direct interactive operation does not use
ProviderExecutor, codec, a template resume command or workflow result transport.

## Fork, In-Place And Append-Only Outcomes

Default fork requires the source journal byte-identical and exactly one new
direct primary with a new session ID and `parentSession` equal to the source.
`--in-place` requires no new primary and the same ID/basename. Its title slot may
remain exact or become one valid pinned encoding; bytes after it must retain the
entire old body as an exact prefix and add at least one complete physical record
extending the graph. Both modes require a changed live manifest and reject extra
or type-swapped files and scaffold/conf/binary drift. An otherwise valid rewritten
journal does not satisfy these predicates.

Continuation sequence starts at 1 without gaps. `previous_sha256` binds exact
link bytes for the first record and exact prior record thereafter. Every
post-start outcome appends exactly one closed success/failure record with
no-replace semantics. Success requires exit zero, null failure, complete non-null
result identity/digest and safe post-live manifest. Failure has a stable code,
null result fields, observed exit (possibly zero after postcondition failure)
and post-live manifest only if safely inventoried. Only successful outcomes
advance the active primary/manifest. Malformed, gapped or failed tails block
further orchestrator continuation; history is never repaired or deleted.
Unrecorded direct OMP mutations cause later digest validation to refuse.

## Deferred Capability Loading

OMP-I2 is gated and unselected. Closing OMP-I1 does not select capability loading.
A named consumer and separate owner activation must precede new logical
skills/extensions: closed content-addressed admission, exact requested/loaded
inventory, empty ambient discovery, inherited non-widening authority and no
network/package mutation. OMP-owned proof of actual loaded inventory/executable
behavior is required; absence of a canary is insufficient. No new provider
qualification, session-store schema or capability authorization is introduced by
this documentation promotion.
