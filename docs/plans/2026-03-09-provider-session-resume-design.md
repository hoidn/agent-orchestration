# ADR: First-Class Provider Session Resume

**Status:** Proposed
**Date:** 2026-03-09
**Owners:** Orchestrator maintainers

## Context

Workflows can already resume an orchestrator run, but they cannot first-class resume a provider-native session or thread. The current reusable pattern is to hard-code provider shell glue such as `codex exec resume ...` directly into workflow YAML, as shown by the shell-based review/fix example. That approach has four contract problems:

1. the DSL has no first-class notion of a provider session handle
2. session ids do not participate in typed artifact publish/consume flow
3. runtime-owned metadata capture is pushed into prompts or ad hoc files
4. workflow `resume` and provider-session `resume` are easy to conflate

Current runtime structure makes this more than a syntax issue:

- scalar artifacts support `enum|integer|float|bool`, but not arbitrary `string`
- provider templates expose only `command`, `defaults`, and `input_mode`
- `ProviderExecutor` returns raw stdout/stderr bytes
- `WorkflowExecutor` immediately runs output capture on those bytes before deterministic output-contract validation

That means provider-session resume is a contract and runtime-shaping problem, not just a nicer YAML shortcut.

## Problem Statement

Add a first-class workflow feature that lets a provider step start a fresh provider session, publish a typed session handle, and later resume that same provider session in a separate step using new feedback, while keeping the authored workflow surface provider-agnostic and artifact-driven.

The first release only needs to replace the ad hoc Codex shell-glue pattern in example workflows. It does not need to solve every provider-session or chat-thread problem.

## Decision Summary

The first release should land behind the next DSL gate, `version: "2.10"`, and adopt these decisions:

1. `string` becomes a general scalar contract type with explicit exact-value parsing/serialization semantics and ships before provider-session resume.
2. Provider-session behavior is expressed through a new step-local `provider_session` tagged union, not through provider-specific shell syntax in authored workflows. `mode: fresh` and `mode: resume` are mutually exclusive authored shapes.
3. Session handles are runtime-captured, materialized on the producing top-level step's normal `steps.<Step>.artifacts` state surface, and runtime-published through the normal scalar artifact ledger only from one authoritative top-level step-finalization commit. For any session-enabled top-level step, that commit stages the exact visit's final step result, every new `artifact_versions` entry produced by that visit (including the runtime-owned `publish_artifact` entry and any authored `publishes` on the same step), and clearing of the matching `current_step` in memory, then persists them together via one atomic `state.json` rewrite; provider-session metadata files are observability only and never define publication on their own. Fresh session steps count as producers of `publish_artifact` for normal `consumes.producers` validation and runtime producer filters even though authored `publishes` remains forbidden for that same artifact. Existing structured-ref legality stays unchanged, so unqualified `root.steps.<Step>.artifacts.<publish_artifact>` access remains valid only for single-visit producers.
4. Provider templates keep their normal `command` for non-session steps and declare session capability under `session_support`, including:
   - `metadata_mode`
   - `fresh_command`
   - optional `resume_command`, which is required for any resume-capable template and must contain exactly one `${SESSION_ID}` placeholder
5. The authored DSL surface stays provider-agnostic, but the first runtime implementation is intentionally Codex-only through `metadata_mode: codex_exec_jsonl_stdout`.
6. Resume steps still declare ordinary `consumes` for lineage and producer/policy selection, but `session_id_from` must match exactly one `consumes[*]` entry on that step; that unique consume contract supplies the runtime-bound session handle, must use `freshness: any` (or omit `freshness`), and is excluded from prompt injection and `consume_bundle`; authored steps may not re-include it through `prompt_consumes` or `consume_bundle.include`.
7. For session-enabled provider steps, `--stream-output` and `--debug` stream only normalized assistant text plus ordinary stderr; raw provider metadata transport is never echoed directly to the parent console, and successful session steps must leave console stdout aligned with the normalized stdout captured for the step.
8. Provider-session observability uses always-on masked visit metadata plus a stable masked transport-spool path that are created before the runtime persists `current_step` for that visit; if resume later finds the canonical metadata record missing anyway, it synthesizes a quarantined stub before failing. Retained masked raw transport remains limited to debug, failure, and quarantined interrupted visits; existing masking rules apply across metadata, logs, state, error context, and any retained transport logs.
9. Session-enabled provider steps disable implicit provider retries in v1; authored workflow control flow remains the only supported retry mechanism.
10. Workflow `resume` refuses to replay an interrupted session-enabled visit. If a run stopped while such a step was still in flight, resume keys the quarantine decision to `current_step.step_id` plus `current_step.visit_count`, ignores older terminal results for the same step name, rewrites `state.json` to clear `current_step` and record a run-level quarantine failure for that exact visit, and fails before allocating a new visit or launching the provider again; the matching visit metadata remains quarantined and any captured transport spool is retained for operator inspection.
11. Workflow `resume` remains a run-state feature. Provider-session `resume` remains a provider-invocation feature. The two concepts stay distinct in DSL, state, docs, and observability.
12. `provider_session` is a top-level-authored root-workflow-only feature in v1; only provider steps declared directly under the root workflow's `steps:` list may use it. Imported workflows, loop bodies, and structured branch/case bodies are rejected if any nested step declares it.

## Core Contract

### 1. `string` scalar support is a prerequisite

`string` should be added as a general scalar type anywhere typed scalar values can cross workflow boundaries or artifact/dataflow boundaries:

- workflow `inputs`
- workflow `outputs`
- top-level `artifacts` with `kind: scalar`
- `expected_outputs[].type`
- `output_bundle.fields[].type`
- `set_scalar` targets

Rules:

- `string` is scalar-only.
- `kind: relpath` still requires `type: relpath`.
- typed predicates may compare strings only with `eq` and `ne`, using exact case-sensitive string equality on the preserved value.
- canonical string values are exact Unicode strings; loader/runtime validation must not trim, strip, case-fold, or otherwise whitespace-normalize them.
- empty string is valid for general `string` contracts. Provider session handles are an explicit stricter contract: any value published as or bound from a `provider_session` handle must be a non-empty exact string, and empty values fail publication or resume binding.
- workflow inputs, workflow outputs, `set_scalar`, and scalar artifact/state surfaces accept only actual string values for `type: string`; numbers and booleans are not coerced into strings.
- `expected_outputs[].type: string` reads the UTF-8 file contents exactly as written, including leading/trailing spaces and newlines.
- `output_bundle.fields[].type: string` accepts only JSON string values and preserves the decoded value exactly.
- serialization to `state.json`, `artifact_versions`, and workflow-output export preserves the exact string value with ordinary JSON escaping only; the runtime never adds or removes surrounding whitespace during persistence.

Rationale:

- a provider session handle is not an enum, number, or boolean
- introducing a one-off “session id” pseudo-type would create special-case flow rules instead of extending the scalar contract family coherently
- explicit no-trim semantics prevent workflow inputs, text-backed outputs, bundle-backed outputs, and state exports from silently diverging on whitespace or empty-string handling

### 2. Minimal step-level DSL surface

Provider steps gain an optional `provider_session` block with exactly one mode-specific shape:

```yaml
provider_session:
  mode: fresh
  publish_artifact: implementation_session_id
```

or

```yaml
provider_session:
  mode: resume
  session_id_from: implementation_session_id
```

Rules:

- steps without `provider_session` keep existing behavior
- v1 allows `provider_session` only on provider steps authored directly in the root workflow's top-level `steps:` list
- loader/runtime validation rejects `provider_session` inside imported workflows executed via `call`, inside `for_each` bodies, inside `repeat_until.steps`, and inside structured `if/else` or `match` branch/case bodies
- `provider_session` is a tagged union keyed by `mode`; authored steps must choose exactly one of the two legal shapes above
- `mode: fresh` requires `publish_artifact`
- `mode: fresh` forbids `session_id_from`
- `mode: resume` requires `session_id_from`
- `mode: resume` forbids `publish_artifact`
- `publish_artifact` and `session_id_from`, when present, must reference top-level scalar artifacts with `type: string`
- provider session handles use a stricter value rule than general `string`: a fresh step may publish `publish_artifact` only when the captured handle is a non-empty exact string, and a resume step must reject an empty consumed `session_id_from` value before `${SESSION_ID}` binding or provider launch
- on fresh steps, `publish_artifact` reserves a runtime-owned key on `steps.<Step>.artifacts`
- for normal `consumes.producers` validation and runtime producer-filter semantics, a fresh session step is treated as a producer of its `publish_artifact` exactly as if it had a runtime-owned scalar publish source on that step
- loader/runtime validation rejects any `expected_outputs[].name`, `output_bundle.fields[].name`, or `publishes.from` that matches that reserved `publish_artifact` key
- steps that declare `provider_session` may still declare authored `publishes` for other artifacts, but every same-step artifact-ledger append from that visit must be staged into the same top-level finalization bundle as the terminal `steps.<Step>` result and exact-visit `current_step` clearance
- a `resume` step must declare exactly one normal `consumes` entry whose `artifact` equals `session_id_from`; zero matches and multiple matches are both validation errors
- that unique `session_id_from` consume contract remains part of normal lineage and producer/policy enforcement, and its `policy` plus optional `producers` fields are the authoritative binding contract for the runtime-bound resume handle
- loader/runtime validation rejects `freshness: since_last_consume` on that reserved `session_id_from` consume; the field must be omitted or set to `any`
- the `session_id_from` consume is reserved for runtime binding into `${SESSION_ID}` rather than prompt text
- the runtime must exclude `session_id_from` from the default `Consumed Artifacts` prompt block
- loader/runtime validation rejects `prompt_consumes` entries that explicitly re-include `session_id_from`
- if a resume step declares `consume_bundle`, the runtime excludes `session_id_from` from the default bundled-consume set
- loader/runtime validation rejects `consume_bundle.include` entries that explicitly re-include `session_id_from`
- a resume step may declare `consume_bundle` only when at least one non-session consume remains after that exclusion
- if a resume step consumes no non-session artifacts, the runtime omits the consumed-artifacts prompt block even when `inject_consumes` is left at its default
- first release supports one session handle per provider step

Why this surface:

- it is the smallest authored abstraction that distinguishes fresh-vs-resume without naming Codex
- it gives loader/runtime validation a single unambiguous mode-specific shape instead of a partially overlapping field set
- it keeps the session handle in normal artifact lineage
- it avoids asking prompts to create runtime-owned files or echo runtime-owned session ids back in prompt text or workspace consume bundles

### 3. Provider-template metadata

Provider templates keep `command` for ordinary non-session execution and add session capability under `session_support`:

```yaml
providers:
  codex:
    command:
      [
        "codex",
        "exec",
        "--model",
        "${model}",
        "--config",
        "reasoning_effort=${effort}",
      ]
    input_mode: "stdin"
    defaults:
      model: "gpt-5.4"
      effort: "high"
    session_support:
      metadata_mode: codex_exec_jsonl_stdout
      fresh_command:
        [
          "codex",
          "exec",
          "--json",
          "--model",
          "${model}",
          "--config",
          "reasoning_effort=${effort}",
        ]
      resume_command:
        [
          "codex",
          "exec",
          "resume",
          "${SESSION_ID}",
          "--json",
          "--model",
          "${model}",
          "--config",
          "reasoning_effort=${effort}",
        ]
```

Required contract:

- `session_support.metadata_mode` and `session_support.fresh_command` are required for any provider that supports `provider_session`
- `session_support.resume_command` is required for providers that support `provider_session.mode: resume`
- `${SESSION_ID}` is legal only inside `session_support.resume_command`
- any provider template that declares `session_support.resume_command` must include exactly one unescaped `${SESSION_ID}` token in that command template after escape processing and before runtime binding; loader validation rejects zero-occurrence and multi-occurrence templates
- `command`, `session_support.fresh_command`, and `session_support.resume_command` use the same parameter-substitution and validation pipeline
- `input_mode` and `defaults` continue to apply to all command variants unless a future contract adds an explicit override surface
- when `provider_session` is absent, the runtime uses `command` and ignores `session_support`

Optionality:

- no extra generic provider metadata fields are added in v1
- provider-native metadata beyond `session_id` is persisted opaquely in runtime-owned metadata files rather than exposed as DSL fields

Why keep session command variants separate from the normal provider `command`:

- it preserves current stdout semantics for non-session steps
- it avoids silently attaching `--json` or other transport flags to steps that did not request session behavior
- it keeps the provider-specific command shape explicit without forcing authors to fork otherwise identical provider templates

Why use explicit `fresh_command` and `resume_command` instead of trying to derive a session argv shape automatically:

- it is explicit about provider-specific command structure
- it does not pretend that all providers can be modeled by the same prefix insertion rule
- it keeps the first abstraction honest while still reusing the same substitution path

### 4. Runtime-owned metadata persistence

Every valid v1 provider-session visit owns one visit-scoped runtime-owned metadata record under:

```text
.orchestrate/runs/<run_id>/provider_sessions/<step_id>__v<visit>.json
```

Each session-enabled visit also owns a masked transport spool path:

```text
.orchestrate/runs/<run_id>/provider_sessions/<step_id>__v<visit>.transport.log
```

For session-enabled steps, the runtime reserves both canonical paths, creates the metadata record, and creates or truncates the stable masked spool file before it persists `current_step` for that visit. Only after those observability artifacts exist may the runtime advertise the visit through `current_step` and proceed toward provider launch. The runtime then durably appends masked provider transport to the spool file as it is observed and atomically rewrites the metadata record when the visit reaches a terminal outcome or is later quarantined by the workflow-resume guard.

The metadata record should include at least:

- provider name
- step id
- visit ordinal
- mode (`fresh` or `resume`)
- step status (`running`, `completed`, `failed`, or `interrupted`)
- publication state (`pending`, `published`, `suppressed_failure`, or `quarantined_interrupted_visit`)
- session id when one was observed
- metadata mode
- selected command variant (`command`, `fresh_command`, or `resume_command`)
- masked fully resolved command
- started/updated timestamps
- parser/event summary needed for diagnosis
- raw-transport log path when retained

Contract boundary:

- this JSON file is a runtime observability artifact, not a workflow-consumable authored artifact
- downstream workflow logic must use the published scalar session-handle artifact instead of reading this file directly
- `state.json` may store a terminal step-local summary such as `debug.provider_session = {mode, session_id, metadata_path, publication_state}`, but interrupted-visit quarantine must also project into the authoritative run state instead of relying on this metadata file alone
- the provisional record exists so an interrupted in-flight visit can be quarantined later without guessing whether replay is safe
- the per-visit masked transport spool exists so a later quarantine path can retain inspectable transport evidence without depending on debug mode or in-memory buffers surviving the interruption
- because `state_manager.start_step` currently durably writes `current_step` before provider-step execution enters the provider body, v1 requires the metadata JSON and stable spool path to exist first; a session-enabled visit must never become the persisted `current_step` unless those artifacts already exist at the canonical visit-qualified paths
- on normal terminal completion, the runtime updates the same record so it describes whether a discovered session id became consumable lineage or was suppressed with the failed step
- the always-on record stores masked summary data only; it must not inline the full raw provider transport stream for successful non-debug runs
- because v1 rejects `provider_session` anywhere except top-level authored root steps, this path is always relative to the top-level run root and keyed by a single stable top-level step id; no nested-scope provider-session metadata contract is defined in this slice
- the metadata key is intentionally visit-qualified as `<step_id>__v<visit>` so quarantine/update logic can target the exact in-flight visit even when the same top-level step presentation key has older terminal results from earlier visits
- if workflow resume later finds the canonical metadata record missing for an interrupted session-enabled visit anyway, it must synthesize a minimal quarantined record at that same path, note that the expected prelaunch record was absent, and point at the stable spool path before surfacing the operator error

Retention and masking policy:

- the visit-scoped metadata JSON is always written for session-enabled steps, beginning before `current_step` is persisted, and inherits the normal run-root retention lifecycle
- best-effort secret masking applies before writing provider-session metadata, raw transport logs, `state.json`, debug logs, or failure context, using the same known-secret masking contract that already applies to logs and prompt audit
- the masked raw-transport spool file is created or truncated at its stable path before `current_step` is persisted, and masked provider transport is durably appended to it while a session-enabled provider step is running
- successful non-debug visits that are neither failed nor quarantined may delete that spool during finalization after masked summary metadata has been updated
- failure handling keeps the masked raw-transport spool whenever existing failure-log behavior would already retain stdout for diagnosis
- `--debug` keeps the masked raw-transport spool even on success
- if workflow resume later quarantines an interrupted visit, the runtime must retain the masked transport spool at its stable path, update the metadata record in place to `step_status: interrupted` and `publication_state: quarantined_interrupted_visit`, and record whether any transport bytes were captured before interruption
- if workflow resume later finds the canonical metadata record missing anyway, it must synthesize that quarantined metadata record at the canonical path, create the empty stable spool file if it is absent, and record zero captured bytes unless retained transport evidence proves otherwise
- when the raw-transport spool is retained, the metadata record stores only its path plus masked parser summary fields and capture counters; it does not duplicate the full payload inline
- when `--stream-output` or `--debug` is enabled, session-aware providers stream only normalized assistant text to console stdout; raw metadata transport never goes straight to the parent console even though it may still be retained on disk under the policy above
- raw provider stderr keeps the existing console-streaming behavior because it is already a human-oriented diagnostic channel rather than the structured metadata transport
- this ADR introduces no new published artifact or external retention surface for provider-session transport data
- quarantine also records the retained spool path and canonical metadata path into the authoritative run-level failure context so reports and later resume attempts do not have to rediscover them from `current_step`

### 5. Session-handle publication, same-step publishes, and resume binding

Session-enabled steps stage all of their publication side effects only during successful step finalization. Fresh steps additionally stage a session handle directly from runtime-owned metadata:

1. provider executes
2. runtime extracts session metadata into a pending in-memory record and validates any publishable session handle as a non-empty exact string
3. runtime normalizes stdout and validates provider-authored outputs
4. the runtime assembles one visit-qualified finalization bundle that contains the final `steps.<Step>` payload, any runtime-owned `steps.<Step>.artifacts.<publish_artifact>` value, the complete set of `artifact_versions` appends produced by that visit (the runtime-owned session handle plus any authored `publishes` on the same step), and the instruction to clear `current_step` only when it still matches the same `step_id` + `visit_count`
5. the runtime atomically rewrites `state.json` once with that bundle, so terminal step state, every published artifact-lineage update from that visit, and `current_step` clearance become durable together
6. only after that state rewrite succeeds does the runtime finalize the metadata record to `publication_state: published` or `publication_state: suppressed_failure`
7. later steps consume the published artifact through ordinary `consumes`
8. resume steps bind the non-empty value resolved by the unique matching `session_id_from` consume contract into `session_support.resume_command` via `${SESSION_ID}`

Durable commit boundary:

- `state.json` is the authoritative durable publication ledger for session handles and every other artifact-ledger append emitted by a session-enabled step; provider-session metadata JSON files are secondary observability records
- after normalization and output validation, the runtime assembles one visit-qualified finalization bundle in memory for the exact `current_step.step_id` + `current_step.visit_count`
- that bundle contains the final persisted step result under `steps.<Step>`, including the runtime-owned `steps.<Step>.artifacts.<publish_artifact>` value when a fresh session step succeeds
- that same bundle also contains the full ordered set of `artifact_versions` appends produced by the visit: the runtime-owned `publish_artifact` entry for a successful fresh step plus every authored same-step `publishes` entry resolved from that visit's validated outputs
- the runtime must persist that entire bundle through one state-manager entrypoint and one atomic `state.json` rewrite; it must not write `steps.<Step>`, any session-handle artifact version, any authored same-step publish version, and `current_step` clearance through separate durable state updates for session-enabled top-level steps
- only after that state rewrite succeeds may the runtime rewrite the provider-session metadata record from `pending` to `published` or `suppressed_failure`, and then apply the normal transport-spool retention cleanup
- if the process stops before the state rewrite lands, the visit remains durably indistinguishable from an interrupted in-flight visit: `current_step` still points at that visit, no new artifact-ledger version from that visit exists (whether runtime-owned or authored), and a later workflow-resume quarantine path must treat any observed session id as unpublished
- if the process stops after the state rewrite lands but before the metadata record is finalized, the committed `state.json` outcome remains authoritative; restart/resume may reconcile the metadata record in place from the committed step result instead of rolling back lineage

Produced-value surface rules:

- `provider_session.publish_artifact` names both the top-level published artifact and the producing step's local `steps.<Step>.artifacts.<name>` entry
- that local key is runtime-owned and reserved: same-step `expected_outputs`, `output_bundle.fields`, and authored `publishes.from` entries must not use the same name
- successful fresh steps always materialize `steps.<Step>.artifacts.<publish_artifact>` in persisted step state, but only from a non-empty exact session handle; empty strings fail the step before any state commit
- resume steps never materialize a runtime-owned `steps.<Step>.artifacts.<publish_artifact>` entry from `provider_session`; v1 treats the consumed handle as authoritative for the resumed visit and does not support handle rotation or republishing from resume mode
- v1 does not relax the existing multi-visit structured-ref guard: `root.steps.<Step>.artifacts.<publish_artifact>` remains legal for workflow outputs, typed predicates, and other structured refs only when that producing step can execute at most once in the current scope
- if authored control flow can revisit the fresh producer, the session handle still enters the normal artifact ledger and remains available to later steps through ordinary `consumes`, but this slice introduces no visit-qualified/export ref syntax for that producer
- `persist_artifacts_in_state: false` is invalid on fresh session steps because the local produced-artifact surface is part of the contract
- session-enabled steps may still declare authored `publishes` for artifacts other than `provider_session.publish_artifact`, but every such publish must be derived from that visit's validated outputs and committed through the same visit-finalization bundle as the runtime-owned session handle publication, if any
- authored `publishes` must not redundantly publish the same artifact named by `provider_session.publish_artifact`
- for cross-reference validation and runtime producer filters, `provider_session.publish_artifact` makes that fresh step an eligible producer of the named top-level artifact even without authored `publishes`; later `consumes.producers` filters may name that step normally, and only successful visits contribute artifact-ledger versions
- any step with `provider_session.mode: resume` is invalid unless its selected provider template declares `session_support.resume_command` and that command contains exactly one `${SESSION_ID}` placeholder
- resume binding fails before provider launch if the uniquely matched consumed handle is empty, even though general `string` values may be empty in other workflow contexts

This is intentionally a runtime-owned publish path rather than `publishes.from: <expected_output>`.

Reason:

- the session handle is owned by runtime/provider execution metadata, not by a prompt-authored file
- forcing it through `expected_outputs` would leak runtime concerns into prompt instructions and output-contract injection
- delaying publication until final step success preserves the existing publish-on-success contract for artifact lineage

This does not bypass normal dataflow semantics after publication:

- the session handle still appears in the ordinary artifact ledger
- non-session consumer freshness rules still apply
- the resume step still declares `consumes`
- failed fresh steps may leave behind provider-native session state, but that state remains masked debug/observability data unless the step fully succeeds
- on resume steps, the consumed session handle continues to participate in lineage and producer/policy checks even though it is not injected into the prompt body, but `freshness: since_last_consume` is forbidden so an explicit authored retry can reuse the same published handle version after a failed or quarantined visit

### 6. Retry and attempt semantics

The first release must make retry behavior explicit rather than inheriting the current provider default.

Rules:

- any step with `provider_session` executes at most once per visit
- provider-default retries on exit codes `1` and `124` are disabled for session-enabled steps
- authored `retries` are invalid on any step that declares `provider_session`
- workflows that want another attempt must model it explicitly with normal control flow, which creates a new visit and therefore a new metadata record

Rationale:

- a fresh session may already exist provider-side before the local process later times out or fails output validation
- a resume step may also have sent its follow-up prompt before the local process reports failure
- silent automatic retries would therefore create ambiguous lineage and duplicate provider-side side effects

Consequences:

- the visit ordinal is sufficient as the v1 metadata key because there is exactly one provider-process attempt per visit
- a failed fresh step that already created a provider-native session records that session id only in debug metadata; it is never auto-published or auto-resumed by the runtime

### 7. Workflow-resume semantics for interrupted session visits

Disabling retries is not sufficient by itself. The runtime also needs an explicit rule for what happens when an orchestrator run is resumed after stopping mid-visit on a session-enabled step.

Rules:

- if persisted state shows `current_step.status: running` for a top-level step that declares `provider_session`, resume preflight must treat `current_step.step_id` plus `current_step.visit_count` as the authoritative identity of the in-flight visit
- missing or non-integer `current_step.visit_count` for an in-flight session-enabled step is a state-integrity failure; resume must stop rather than replay
- a persisted terminal result under `steps.<PresentationKey>` clears the interruption guard only when that result records the same `step_id` and the same `visit_count` as the in-flight `current_step`; an older `completed` or `failed` result for the same top-level step name does not clear the guard
- if the exact `step_id` + `visit_count` visit has no terminal persisted result, `orchestrator resume` must treat that visit as interrupted rather than replayable
- resume preflight must fail before incrementing `step_visits`, before selecting a new restart visit, and before launching any provider command for that step
- when quarantining, the runtime updates the metadata record keyed by `<current_step.step_id>__v<current_step.visit_count>` to `step_status: interrupted` and `publication_state: quarantined_interrupted_visit`, retains the per-visit transport spool at its stable path, and atomically rewrites `state.json` to: set run `status: failed`, clear `current_step`, preserve any older terminal `steps.<PresentationKey>` result unchanged, and record a run-level `error` object for the quarantined visit
- that run-level `error` object is the authoritative projection of quarantine into `state.json`; it must include a dedicated type such as `provider_session_interrupted_visit_quarantined`, an operator-facing message, and context containing at least `step_name`, `step_id`, `visit_count`, `metadata_path`, `transport_spool_path`, and whether the metadata record had to be synthesized
- once that run-level quarantine error exists, later `orchestrator resume` attempts against the same run must fail immediately from persisted state before restart-index planning unless the operator chooses `--force-restart` or starts a new run; the runtime must not clear or overwrite that quarantine marker just to try again
- session-enabled execution creates that metadata record and stable spool path before `current_step` is persisted; if quarantine nonetheless finds the canonical metadata record missing, resume must synthesize a minimal quarantined record there from `current_step`, note that the prelaunch record was missing, create the empty stable spool file if needed, and report that synthesized artifact path instead of failing without observability
- no session handle is published from a quarantined interrupted visit, even if partial provider metadata already contained a session id
- operators must resolve the interrupted visit manually by inspecting the quarantined metadata plus the retained transport log, if any bytes were captured before interruption, and then either starting a new run or intentionally authoring a new attempt through ordinary workflow control flow; v1 provides no automatic adoption or replay of the interrupted provider-native session
- if the exact in-flight visit already has a terminal persisted result (`completed` or `failed`), normal workflow-resume behavior continues from the first unfinished later step; the guard applies only to visits whose own persisted result is still non-terminal

Rationale:

- the current runtime resumes at the first unfinished top-level step and allocates a new visit before execution, which would silently replay provider-side side effects for ordinary provider steps
- session-enabled steps explicitly reject automatic retries because replay is not side-effect-free; workflow resume must therefore make the same safety choice for interrupted in-flight visits
- the current executor persists `current_step` before entering the provider-step body, so the visit-qualified metadata record and stable spool placeholder must already exist or resume quarantine would have no deterministic artifact to point operators at after a crash in that gap
- the current report and resume planners both treat `current_step` as the primary running marker, so quarantine must clear that marker and write a durable run-level failure record or the run will continue to look actively running
- a fail-fast resume guard is smaller and more honest than pretending the runtime can infer whether an interrupted provider-native session should be resumed, retried, or abandoned

### 8. Top-level authored-step boundary

The first release explicitly supports `provider_session` only on provider steps declared directly in the root workflow's top-level `steps:` list.

Rules:

- a root-level provider step may declare `provider_session`, but any nested step may not
- validation must reject `provider_session` inside imported workflows executed via `call`
- validation must reject `provider_session` inside `for_each` bodies, `repeat_until.steps`, and structured `if/else` or `match` branch/case bodies
- no branch-output, loop-frame-output, per-iteration indexed-key, or caller/callee export semantics are defined for provider-session metadata or runtime-owned session-handle publication in this slice
- the only new downstream structured-ref surface in scope is `root.steps.<TopLevelStep>.artifacts.<publish_artifact>` for successful fresh session steps that remain single-visit in the current scope; revisitable fresh producers stay downstream-consumable only through the normal published artifact ledger in v1

Why this restriction is necessary:

- reusable `call` gives each call frame its own run-root subtree and callee-private artifact lineage/freshness state
- structured branches/cases materialize downstream outputs on the statement frame rather than the inner step
- `repeat_until` materializes downstream outputs on the loop frame, and `for_each` stores nested step results under per-iteration indexed presentation keys
- supporting provider-session steps inside any of those nested scopes would therefore require an explicit contract for frame-local metadata paths, runtime-owned publication targets, exported-output timing, and downstream structured refs
- the brief already treats broader nested integration as non-goal territory, so v1 should reject unsupported nested surfaces instead of pretending the top-level path contract generalizes automatically

## Runtime Execution Order And Invariants

For provider-session steps, the runtime order must be:

1. validate and resolve consumed artifacts, including the requirement that `provider_session.session_id_from` match exactly one `consumes[*]` contract on the step
2. reserve that unique `provider_session.session_id_from` consume for runtime binding, require its `freshness` to be omitted or `any`, exclude it from automatic consumed-artifact prompt injection and `consume_bundle` materialization, and reject any authored `prompt_consumes` or `consume_bundle.include` that explicitly names it
3. compose the provider prompt using existing prompt rules and materialize any allowed non-session `consume_bundle`
4. resolve either `command`, `session_support.fresh_command`, or `session_support.resume_command`
5. allocate the canonical visit-qualified metadata and transport-spool paths for the exact `step_id` + `visit_count`
6. create or refresh the masked visit metadata record with `step_status: running`, `publication_state: pending`, and zero captured transport bytes, and create or truncate the masked per-visit transport spool at its stable path before persisting `current_step`
7. persist `current_step` for that same exact visit
8. execute the provider process exactly once for this visit while durably appending masked transport to the spool as it is observed
9. if `provider_session` is enabled, parse provider-session metadata from the provider-declared metadata channel
10. normalize provider stdout for ordinary `output_file` / `output_capture` and any console-streaming surface
11. run normal `expected_outputs` or `output_bundle` validation for provider-authored outputs
12. determine the final step outcome
13. assemble one visit-qualified top-level finalization bundle that contains the final `steps.<Step>` payload, any runtime-owned `steps.<Step>.artifacts.<publish_artifact>` value, and the full set of `artifact_versions` appends produced by that visit for both `provider_session.publish_artifact` and any authored same-step `publishes`, plus the instruction to clear `current_step` only when it still matches the same `step_id` + `visit_count`
14. atomically rewrite `state.json` once with that bundle, so the exact visit's terminal step result, every published artifact-lineage update from that visit, and `current_step` clearance become durable together
15. only after that state rewrite succeeds, finalize the provider-session metadata record and retention state by either:
   - recording `publication_state: published` for the same now-committed session handle, or
   - recording `publication_state: suppressed_failure`

Key invariants:

- workflow `resume` never means provider-session `resume`
- prompts do not create or own session-id files
- `session_id_from` identifies exactly one consume contract, so the producer/policy selection for the bound resume handle is never implicit, while `freshness: since_last_consume` remains forbidden for that reserved consume
- prompts and `consume_bundle` files do not receive the runtime-bound resume handle
- session handles are always typed scalar `string` artifacts, and any published or resume-bound handle is non-empty
- v1 rejects `provider_session` anywhere except top-level authored root provider steps instead of inventing implicit nested run-root or export semantics
- the visit-scoped masked metadata record and stable spool placeholder exist before `current_step` is durably advertised for that visit, are later finalized or quarantined in place, and quarantine synthesizes the record if it is unexpectedly missing
- the loader/runtime producer map for `consumes.producers` treats successful fresh session steps exactly like other artifact producers for the named `publish_artifact`, even though the publish path itself is runtime-owned
- provider-session metadata capture happens before deterministic output-contract validation
- `state.json` is the only authoritative durable publication boundary for session handles and every other artifact-ledger append emitted by a session-enabled step; provider-session metadata files may lag behind it after a crash but must never get ahead of it
- no session handle reaches the artifact ledger unless the entire producing step succeeds
- the runtime commits `steps.<Step>`, every new `artifact_versions` entry produced by that session-enabled visit, and clearing the exact matching `current_step` through one atomic state rewrite for session-enabled top-level steps
- if execution stops before that rewrite lands, the visit remains unpublished and workflow-resume quarantine treats it as interrupted even if the metadata parser had already observed a session id
- if workflow-resume quarantine fires, the runtime also commits a durable run-level `failed` status plus a quarantined-visit `error` record while clearing `current_step`, so reports and later resume attempts see an explicitly quarantined run rather than an apparently running one
- the runtime-owned `publish_artifact` key cannot collide with provider-authored local artifacts or authored `publishes.from` aliases on the same step
- no successful fresh step hides its published session handle from normal artifact lineage; every successful fresh producer appends the handle to `artifact_versions`, while unqualified `root.steps.<Step>.artifacts.<name>` refs remain governed by the existing single-visit rule
- session-enabled steps execute once per visit; any retry requires authored workflow control flow
- workflow resume never auto-replays an interrupted in-flight session-enabled visit; it compares the running `current_step.step_id` + `current_step.visit_count` against any persisted terminal result, ignores older same-name visits, and quarantines the exact in-flight visit before exit when no terminal match exists
- session-enabled steps never tee raw metadata transport to console stdout; console streaming, when enabled, is derived only from normalized assistant text
- always-on provider-session metadata is masked summary data; masked raw transport is durably spooled during execution and retained only for debug, failure, or quarantined interrupted-visit observability
- provider-authored outputs keep their current contract model
- missing or unparsable required session metadata is a runtime contract failure, not a successful provider step

## Codex-First Mechanism

The first runtime slice supports only:

- `session_support.metadata_mode: codex_exec_jsonl_stdout`

Codex-specific rules for `codex exec --json`:

- stdout must be valid JSONL, one object per line, with a top-level string `type`
- any non-JSON line, non-object line, or JSON object without a string `type` is a runtime contract failure for this metadata mode
- `thread.started` with a non-empty string `thread_id` is the source of the fresh-session handle
- a fresh session step requires exactly one stable non-empty `thread_id`; missing it on an exit-0 run, observing an empty string, or observing conflicting ids fails the step
- `task_complete.last_agent_message` is the authoritative normalized assistant text when present
- `agent_message.message` is the fallback text source only when `task_complete.last_agent_message` is absent
- if both streamed `agent_message.message` fragments and `task_complete.last_agent_message` are present, the concatenated fragment text must be an exact prefix of the final normalized assistant text; the runtime may stream that prefix live and must append only the unseen suffix after terminal success
- if streamed fragments are not an exact prefix of `task_complete.last_agent_message`, the step fails as a metadata-mode contract error instead of letting live console output diverge from captured stdout
- `turn.completed` or `task_complete` is required as the terminal success marker for an exit-0 run
- `turn.failed` or top-level `error` is a runtime contract failure even if the process exits `0`
- `item.started`, `item.completed`, tool/progress events, and unknown future event types are preserved only in the retained raw-transport log for debug, failure, or quarantine cases, and otherwise reduced to masked summary counters in the metadata record
- on resume steps, if the stream emits `thread.started.thread_id`, it must match the consumed non-empty session id; otherwise the step fails

This contract is deliberately narrow and tied to the current `codex exec --json` stream. It does not claim compatibility with Codex MCP notifications or any future Codex transport.

## Output-Capture And Output-Contract Interaction

The current runtime captures raw provider stdout immediately. That is not sufficient for session-enabled Codex steps because stdout carries a JSONL transport stream instead of plain user-facing text.

The design therefore requires a session-aware normalization seam before normal output capture:

- raw provider stdout is first interpreted according to `session_support.metadata_mode`
- for `codex_exec_jsonl_stdout`, normalized assistant text is `task_complete.last_agent_message` when present, otherwise the concatenated `agent_message.message` fragments in order
- normalized assistant text becomes the stdout seen by `output_file`, `output_capture`, and any parent-console stdout streaming surface
- when `--stream-output` or `--debug` is enabled, `codex_exec_jsonl_stdout` streams only normalized assistant text to the console through the same normalization buffer used for captured stdout: emit `agent_message.message` fragments as provisional prefix text as they arrive, append any unseen suffix from `task_complete.last_agent_message` after terminal success, and if no fragments were emitted, print the final normalized assistant text once after terminal success
- if provisional streamed fragments cannot be reconciled as an exact prefix of the final normalized assistant text, the step fails as a metadata-mode contract error rather than allowing console stdout and captured stdout to disagree
- the runtime must never echo raw Codex JSONL lines to the parent console; raw transport remains a retained observability artifact only under the policy above
- raw provider stderr continues to use the existing live-streaming behavior
- raw provider event output is summarized in the always-on masked metadata file and written to the masked raw-transport spool, which is deleted on successful non-debug completion and retained only under the retention policy above
- ordinary `expected_outputs` and `output_bundle` still validate provider-authored files after normalization

Because fresh session handles are not modeled as `expected_outputs`, the existing prompt `Output Contract` injection can stay focused on provider-authored outputs. No prompt should instruct the model to write a runtime-owned session-id file.

## Required Prerequisites And Debt Paydown

The feature does require narrow internal refactoring before the end-to-end provider-session path is safe to ship.

### Blocking prerequisites

1. `string` scalar support across loader, output contracts, workflow inputs/outputs, and artifact dataflow, with exact-value parsing/serialization rules that remove the current implicit `.strip()` behavior for string-typed values.
2. A shared provider-command compilation path that can validate and substitute `command`, `session_support.fresh_command`, and `session_support.resume_command` consistently.
3. A provider-execution normalization seam between subprocess execution and both `OutputCapture` and console streaming, so session metadata can be extracted before user-facing stdout is captured or displayed.
4. A step-finalization seam that can stage the exact visit's persisted step result, runtime-owned session publication, every authored same-step artifact publication on a session-enabled step, and matching `current_step` clearance into one state-manager commit, expose fresh session producers to normal `consumes.producers` validation/filtering, and commit artifact-ledger updates only after output validation succeeds.
5. Loader/runtime validation that disables implicit provider retries and rejects `retries` on session-enabled steps.
6. Loader/runtime validation that restricts `provider_session` to top-level authored root provider steps, rejects it inside imported workflows/call frames and all nested local-scope bodies, enforces a mutually exclusive mode-tagged shape (`fresh` requires `publish_artifact` and forbids `session_id_from`; `resume` requires `session_id_from` and forbids `publish_artifact`), requires `session_id_from` to match exactly one `consumes[*]` contract, reserves that consume for runtime binding, requires its `freshness` to be omitted or `any`, keeps it out of prompt injection and `consume_bundle`, enforces that published and resume-bound session handles are non-empty exact strings, requires every resume-capable provider template to expose exactly one `${SESSION_ID}` placeholder in `session_support.resume_command`, reserves `publish_artifact` as a runtime-owned local artifact key, guarantees successful fresh steps materialize the handle on the normal `steps.<Step>.artifacts` surface while resume steps do not republish handles, and preserves the existing rule that unqualified structured refs to multi-visit producers stay invalid.
7. Resume-planner / executor preflight that detects an interrupted in-flight session-enabled visit by matching `current_step.step_id` plus `current_step.visit_count` against the persisted terminal result for that exact visit, quarantines its metadata record, synthesizes that canonical record if it is unexpectedly missing, atomically projects the quarantine into `state.json` by clearing `current_step` and recording a run-level quarantine failure, and fails `orchestrator resume` before incrementing step visits or launching the provider again.
8. Provider-session observability plumbing that writes masked summary metadata and creates or truncates the stable masked raw-transport spool before `state_manager.start_step` persists `current_step`, durably spools masked raw transport during execution, updates metadata on terminal success/failure or quarantine, deletes the spool on successful non-debug completion, and retains it for debug, failure, or quarantine inspection.
9. Session-aware console-streaming plumbing so `--stream-output` and `--debug` emit normalized assistant text instead of raw provider transport for session-enabled steps.

Closure criteria for the prerequisite refactor:

- one code path builds non-session, fresh-session, and resume-session provider commands
- one code path validates/persists `string` values without trimming them, while preserving exact parity across workflow inputs, text-backed outputs, bundle-backed outputs, artifact ledgers, and workflow-output export
- one code path can return raw stdout plus normalized stdout plus optional provider-session metadata and terminal-event summary
- one code path controls both captured stdout and live console stdout for session-enabled steps, never writes raw metadata transport directly to the parent console, and guarantees that successful session steps finish with the same normalized stdout on both surfaces
- session handles are non-empty exact strings at both publication and resume-binding time; empty handles fail before state commit or provider launch
- session handles are staged until final step success; failed steps never produce new artifact versions
- one atomic `state.json` rewrite commits `steps.<Step>`, every new `artifact_versions` entry produced by a session-enabled top-level step visit (including `publish_artifact` and any authored same-step publishes), and clearing the exact matching `current_step` together; provider-session metadata records are finalized only after that commit and may be reconciled from committed state if they lag behind after a crash
- resume steps are rejected unless `session_id_from` matches exactly one `consumes[*]` contract and uses `freshness: any` (or omits `freshness`), so provider binding never depends on artifact-name collisions or on preflight consume bookkeeping that would burn explicit retries
- resume-only session consumes never leak into the automatic `Consumed Artifacts` prompt block or any `consume_bundle` file
- resume-capable provider templates are rejected unless `session_support.resume_command` binds exactly one `${SESSION_ID}` placeholder, so a resume step cannot silently ignore its consumed handle
- `provider_session` is rejected anywhere except top-level authored root provider steps, so the runtime never has to guess branch/loop/call publication scope
- `orchestrator resume` fails before replay when the persisted restart point is an interrupted in-flight session-enabled visit, using exact `current_step.step_id` + `current_step.visit_count` matching rather than step-name matching, and the corresponding visit metadata path always exists for operator inspection because the record/spool placeholder was created before `current_step` or synthesized during quarantine if unexpectedly missing
- quarantine clears `current_step`, sets run `status: failed`, and records a durable run-level error naming the quarantined visit plus its metadata/spool paths, so reporting and later resume attempts observe a first-class no-replay state instead of a stale running marker
- successful fresh session steps materialize the same handle on both `steps.<Step>.artifacts` and `artifact_versions`, without relaxing the existing structured-ref ban on multi-visit producers
- successful fresh session steps count as ordinary producers of `publish_artifact` for `consumes.producers` validation and runtime producer filters even though authored `publishes` is forbidden for that artifact
- runtime-owned `publish_artifact` names cannot be shadowed by `expected_outputs`, `output_bundle`, or authored `publishes.from`
- session-enabled steps run exactly once per visit
- provider-session metadata is always persisted as masked summary data from visit start onward, and masked raw transport is durably spooled during execution but retained on disk only for debug, failure, or quarantined interrupted visits
- normal non-session provider steps keep existing behavior

### Required in-scope feature work

- DSL/spec validation for `string`, `provider_session`, `session_support.fresh_command`, `session_support.resume_command` including exact-value `string` parsing/serialization semantics, a mutually exclusive mode-tagged `provider_session` shape (`fresh` requires `publish_artifact` and forbids `session_id_from`; `resume` requires `session_id_from` and forbids `publish_artifact`), explicit non-empty provider-session-handle enforcement at fresh-handle publication and resume binding time, the exactly-one-matching-`session_id_from` consume rule, the `freshness: any`-only rule for that reserved consume, the exactly-one-`${SESSION_ID}` bind rule for resume-capable templates, the no-`retries` rule, the top-level-authored-root-step-only v1 restriction for `provider_session`, the reserved non-injected/non-bundled `session_id_from` consume behavior, and the reserved runtime-owned `publish_artifact` local-artifact key
- resume preflight that blocks replay of interrupted in-flight session-enabled visits by checking the exact in-flight visit identity, atomically records the quarantine in authoritative run state, and surfaces quarantined visit metadata to the operator even when it must synthesize the missing canonical record first
- runtime publication of fresh session handles only from a single crash-consistent successful-finalization state write that also includes every other artifact-ledger append produced by that same session-enabled step visit, while still registering fresh producers for normal `consumes.producers` validation and runtime producer filtering
- runtime materialization of successful fresh session handles on `steps.<Step>.artifacts.<publish_artifact>` so single-visit workflow outputs and structured refs can bind them, while revisitable producers remain consume-only in v1
- resume binding from consumed scalar artifact to provider invocation
- Codex `thread.started` / `task_complete` / `agent_message` parsing and visit-scoped provider-session metadata persistence
- masked observability for provider-session metadata and any retained debug/failure/quarantine raw transport logs, with the canonical metadata record and stable spool path created before `current_step` is persisted
- session-aware stdout streaming so `--stream-output` and `--debug` show normalized assistant text from the same normalization buffer used by `output_capture`, instead of raw provider transport on session-enabled steps
- one migrated example workflow that proves the feature end-to-end while leaving the shell-based example intact

### Recommended follow-up

- richer report surfaces for provider-session metadata
- a second concrete provider before introducing more abstract metadata modes
- example-library guidance on when provider-session resume is appropriate versus when a fresh provider step is cleaner

### Explicitly not a prerequisite

- generalized chat-thread management
- multi-session fan-out
- supporting `provider_session` anywhere except top-level authored root provider steps
- automatic recovery of partially completed provider sessions after step failure
- automatic replay or adoption of an interrupted in-flight provider-session visit under workflow resume
- a provider-agnostic event schema before one real provider path is proven

## Non-Goals

This ADR does not include:

- support for multiple providers in the first runtime slice
- changes to the meaning of workflow `resume`
- automatic conversion of older workflows
- hidden provider-command synthesis based on shell magic outside declared provider templates
- implicit provider retries on session-enabled steps
- automatic adoption of a session created by a failed fresh step
- automatic replay of an interrupted in-flight provider-session visit during workflow resume
- exposing provider-session metadata files as authored workflow artifacts
- `provider_session` anywhere except top-level authored root provider steps
- multi-session orchestration semantics

## Sequencing Constraints

The implementation order should be fixed:

1. approve this ADR
2. ship `string` scalar contracts
3. ship loader/spec validation for provider-session schema, session command variants, and no-`retries` rules
4. ship provider execution normalization plus crash-consistent successful-finalization publication semantics
5. ship the Codex metadata parser and example workflow migration
6. ship smoke verification

Additional constraints:

- do not implement provider-session resume before `string` exists
- do not claim multi-provider generality before a second provider exists
- do not remove the shell-based example in the first release
- do not let `orchestrator resume` silently replay an interrupted in-flight session-enabled visit
- do not let quarantined interrupted visits drop their captured transport evidence
- do not leave `current_step` pointing at a quarantined interrupted visit after resume refuses replay
- do not silently allow `provider_session` anywhere except top-level authored root provider steps before a dedicated nested-scope contract exists
- do not publish a session-handle artifact before final step success is known
- do not let provider-session metadata records claim `published` before the authoritative state commit that persists the final step result, every same-step artifact-lineage update, and `current_step` clearance
- do not let session-enabled steps inherit the current provider auto-retry default
- do not allow `session_id_from` consumes to use `freshness: since_last_consume` in v1
- do not blur workflow-run resume wording in CLI/docs/reporting

## Migration And Compatibility

Compatibility story:

- existing workflows continue to work unchanged
- `provider_session`, `session_support`, and scalar `string` support are version-gated at `2.10`
- `string` is new in `2.10`, so exact whitespace-preserving semantics apply only to newly authored `type: string` contracts; existing non-string scalar and `relpath` behavior stays unchanged
- provider templates can add `session_support` without changing existing non-session steps because `command` remains the non-session path
- any template that declares `session_support.resume_command` under `2.10` must include exactly one `${SESSION_ID}` placeholder or fail validation; templates without `provider_session` support remain unaffected
- workflows that declare `provider_session` can run in `2.10` only when the session-enabled step is a provider step authored directly under the root workflow's top-level `steps:` list; `provider_session` remains a mutually exclusive mode-tagged block (`fresh` requires `publish_artifact` and forbids `session_id_from`; `resume` requires `session_id_from` and forbids `publish_artifact`), imported workflows, loop bodies, and structured branch/case bodies remain invalid in the first release, and any resume step whose `session_id_from` matches zero or multiple `consumes[*]` entries or declares `freshness: since_last_consume` fails validation
- workflows do not get a new exception to the existing multi-visit reference model: a successful fresh session handle is always published into normal artifact lineage for later `consumes`, but unqualified workflow outputs and typed predicates may target `root.steps.<Step>.artifacts.<publish_artifact>` only when that producer is single-visit in the current scope
- resuming a run that stopped mid-visit on a session-enabled step now fails fast instead of replaying that step automatically; the guard is keyed to the exact `current_step.visit_count` for that top-level step rather than any older same-name result, quarantine clears `current_step` and records a durable run-level error for that exact visit, and operators must inspect the quarantined metadata plus the retained transport log, if any bytes were captured before interruption, and choose a new run or an explicit authored retry path
- older workflows keep using their current provider behavior and shell glue if they choose
- the first release adds a new example workflow that uses the first-class feature while leaving `workflows/examples/dsl_review_first_fix_loop.yaml` in place as a legacy reference

There is no automatic migration requirement in this slice. Migration is manual and opt-in by upgrading the workflow version and provider template surface.

## Rejected Alternatives

### 1. Hard-code `codex exec resume` as a DSL feature

Rejected because it bakes a provider command into the authored workflow surface and does not generalize even minimally.

### 2. Force session handles through `expected_outputs`

Rejected because it makes prompts responsible for writing a runtime-owned value and complicates `Output Contract` injection with a file the provider should not own.

### 3. Reuse the normal provider `command` and silently append session transport flags

Rejected because it would either change non-session stdout semantics or require hidden runtime command rewriting that the authored provider template did not declare.

### 4. Pretend the first release is provider-general

Rejected because only the Codex `exec --json` event path is concrete today. A fake abstraction would make the DSL look more stable than the runtime actually is.

### 5. Let publication rely on separate best-effort state writes or metadata-file markers

Rejected because the current runtime already persists the whole run state with atomic file replacement. Splitting terminal step persistence, any same-step artifact publication, and `current_step` clearing across separate durable writes would keep a crash window that leaks or drops lineage from a session-enabled visit.

## Outcome

The first release should be a principled, bounded feature:

- provider-agnostic in authored workflow shape
- explicitly Codex-first in runtime implementation
- crash-consistent at the exact-visit `steps` + all same-step `artifact_versions` + `current_step` publication boundary
- explicit about retry boundaries, quarantine state projection, and non-goals
- honest about prerequisites

That is enough to replace shell glue without lying about what the runtime can guarantee.
