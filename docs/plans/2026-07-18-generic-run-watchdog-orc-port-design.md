# Generic Run Watchdog Workflow Lisp Port Design

**Status:** bounded migration design
**Module:** `generic_run_watchdog/watchdog`
**Entry workflow:** `generic_run_watchdog/watchdog::watchdog`
**Target DSL:** `2.15`
**Candidate path:** `workflows/library/generic_run_watchdog/watchdog.orc`
**YAML compatibility source:** `workflows/examples/generic_run_watchdog.yaml`

## Purpose And Authority

This design fixes the exact translation contract for the generic run watchdog
before its Workflow Lisp source or extern manifests exist. The port preserves
the public behavior characterized from the content-frozen YAML source while
making typed command and provider results the orchestration authority. It does
not promote the candidate, retire YAML, or broaden the watchdog result schema.

The governing authorities are:

- `docs/plans/2026-07-07-yaml-retirement-program.md`, which selects this family
  as one of exactly two new `.orc` ports;
- `docs/workflow_yaml_orc_gap_list.md`, which requires typed probe/publication,
  a typed repair/no-action union, closed provider branches, exact prompt
  dependency parity, and no report-parsing control flow;
- `docs/design/workflow_lisp_frontend_specification.md`, `specs/providers.md`,
  and `specs/dependencies.md`, which own typed results, call-local policy,
  exact prompt dependencies, retries, and completed-result reuse; and
- the YAML source with SHA-256
  `797f02672508f70a1b5071b216a30946f5a78a98d9413cca25ed5fa167c07b85`,
  which remains the family behavior baseline until promotion.

## Public Inputs

| Name | Type | Default | Constraint |
|---|---|---|---|
| `target_run_id` | `String` | `required` | Passed unchanged to the probe; the adapter retains its existing run-id validation. |
| `state_root` | `StateRoot` | `state/GENERIC-RUN-WATCHDOG` | Workspace relpath under `state`; generated watch and result targets stay beneath it. |
| `evidence_root` | `ArtifactRoot` | `artifacts/work/generic-run-watchdog` | Workspace relpath under `artifacts/work`. |
| `repair_result_target_path` | `ArtifactOutputPath` | `artifacts/work/generic-run-watchdog/repair-result.json` | Workspace relpath under `artifacts/work`; semantic compatibility target, not control authority. |
| `max_stale_minutes` | `Int` | `60` | Positive integer; the probe rejects non-positive values. |
| `repair_provider` | `RepairProvider` | `codex` | Closed enum with members `codex` and `claude_opus`; provider references never become runtime values. |

The port adds no model or effort input. Those values are fixed by the existing
family policy and selected inside the two compiler-known provider branches.

## Public Outputs

| Name | Type | Source |
|---|---|---|
| `watch_status` | `WatchStatus` | `WatchdogOutput.watch_status` from publication. |
| `repair_status` | `RepairStatus` | `WatchdogOutput.repair_status` from publication. |
| `recovery_action` | `RecoveryAction` | `WatchdogOutput.recovery_action` from publication. |
| `watchdog_result_path` | `ProducedStatePath` | Existing `state_root/watchdog-result.json` compatibility result written by publication. |

The enum members remain byte-for-byte compatible with YAML:

- `WatchStatus`: `RUNNING_OK`, `COMPLETED`, `FAILED`, `CRASHED`, `STALLED`,
  `UNKNOWN`;
- `RepairStatus`: `NO_ACTION`, `FIXED_AND_RESUMED`,
  `FIXED_AND_RELAUNCHED`, `PLAN_WRITTEN`, `BLOCKED`; and
- `RecoveryAction`: `NONE`, `RESUME`, `RELAUNCH`, `RESTART`, `DECLINED`.

## Typed Contract

The module declares these domain types rather than encoding decisions in text
or compatibility JSON:

```text
RepairProvider = codex | claude_opus
RepairRequired = YES | NO
RecommendedRecovery = NONE | RESUME | RELAUNCH | INVESTIGATE
ProviderFixComplexity = TRIVIAL | NONTRIVIAL
ProviderRepairStatus = FIXED_AND_RESUMED | FIXED_AND_RELAUNCHED | PLAN_WRITTEN | BLOCKED
ProviderRecoveryAction = RESUME | RELAUNCH | RESTART | DECLINED
FixComplexity = NOT_APPLICABLE | TRIVIAL | NONTRIVIAL

WatchProbe = {
  watch_bundle_path: ProducedStatePath,
  watch_status: WatchStatus,
  repair_required: RepairRequired,
  recommended_recovery: RecommendedRecovery,
  evidence_bundle_path: ProducedArtifactPath,
  repair_result_target_path: ArtifactOutputPath
}

ProviderRepairResult = {
  repair_status: ProviderRepairStatus,
  fix_complexity: ProviderFixComplexity,
  recovery_action: ProviderRecoveryAction,
  repair_report_path: ProducedArtifactPath,
  plan_path: String,
  new_run_id: String
}

RepairOutcome =
  NO_ACTION
  | REPAIR { result: ProviderRepairResult }

WatchdogOutput = {
  watch_status: WatchStatus,
  repair_status: RepairStatus,
  recovery_action: RecoveryAction,
  watchdog_result_path: ProducedStatePath
}
```

The three provider-only enums make the closed repair contract nominal: a
provider cannot return public `NO_ACTION`, `NOT_APPLICABLE`, or `NONE` because
none of those values inhabits its declared result types. Publication
exhaustively matches `RepairOutcome`. The `NO_ACTION` branch supplies
deterministic `NO_ACTION`, `NOT_APPLICABLE`, `NONE`, and empty compatibility
strings. The `REPAIR` branch exhaustively widens all three provider-only enums
into their corresponding public `RepairStatus`, `FixComplexity`, and
`RecoveryAction` members and passes the native typed artifact paths directly
to the publisher without reopening `repair-result.json`.

**Compiler-feasibility correction:** Workflow Lisp intentionally has no
path-to-`String` coercion. A common normalized record could not represent both
an empty no-action string and a `ProducedArtifactPath` without weakening the
repair provider contract. The exhaustive match therefore owns two
branch-local invocations of the same certified publisher command. This small
duplication preserves the nominal path proof and adds no compiler mechanism.

## Branch-Local Provider Policy

| Branch | Extern | Profile | Model | Effort | Timeout seconds |
|---|---|---|---|---|---:|
| `codex` | `providers.repair.codex` | `codex_unrestricted_workspace` | `gpt-5.4` | `high` | `7200` |
| `claude_opus` | `providers.repair.claude` | `claude_unrestricted_workspace` | `opus` | `high` | `7200` |

The provider manifest uses the shared no-default profiles. Each branch supplies
its exact model and effort through call-local policy and uses the same positive
literal timeout. The workflow compares `repair_provider` and uses an effectful
`if` whose arms each name one compiler-known extern. There is no dynamic
provider reference and no family-specific compiler branch.

## Typed Flow

| Phase | Owner | Typed result | Contract |
|---|---|---|---|
| `probe` | Certified command boundary `probe_orchestrator_run` | `WatchProbe` | Read the target run store and clock, classify it, write operator evidence plus the `watch.json` compatibility mirror, and return the same validated control fields through the runtime-owned bundle. |
| `no_action` | Pure Workflow Lisp branch | `RepairOutcome.NO_ACTION` | Selected only when `WatchProbe.repair_required == NO`; the provider is skipped and deterministic no-action values are constructed without reading a repair file. |
| `repair` | Effectful closed provider branch | `RepairOutcome.REPAIR` | Selected only when `WatchProbe.repair_required == YES`; choose one compiler-known extern, return `ProviderRepairResult`, and wrap it without parsing provider prose or compatibility JSON. |
| `publish` | Exhaustive `RepairOutcome` match plus certified command boundary `publish_run_watchdog_result` | `WatchdogOutput` | Invoke the same publisher in both branches: literals and empty strings for `NO_ACTION`, or widened enums plus native typed paths for `REPAIR`; validate fields, write the final compatibility result, and return the four typed fields through the runtime-owned bundle. |

The entry workflow therefore has this fixed sequence:

1. Allocate deterministic targets beneath the two public roots.
2. Invoke `command-result probe_orchestrator_run` and obtain `WatchProbe`.
3. Use typed equality on `repair_required` to choose the no-action value or the
   two-extern repair helper.
4. Exhaustively match `RepairOutcome` and invoke the same
   `command-result publish_run_watchdog_result` boundary in each branch. The
   no-action branch supplies deterministic sentinels; the repair branch widens
   its nominal enums and preserves native path values.
5. Return the selected branch's `WatchdogOutput` directly.

The publisher must not read `repair-result.json` or provider prose to decide
repair status or recovery action. It may validate and write semantic files, but
typed fields supplied by the workflow are the routing and output authority.

## Prompt Dependency Contract

| Provider boundary | Required exact relpath | Position | Instruction meaning | Retry | Completed reuse |
|---|---|---|---|---|---|
| `repair` | `watch.watch_bundle_path` | `prepend` | `the injected watch bundle is authoritative evidence` | `fresh immutable snapshot per new attempt` | `do not reopen dependency files` |

The repair provider has exactly one required prompt dependency and no optional
dependency. Its instruction must communicate the recorded meaning; literal
wording is not part of the contract. Runtime rendering uses the generic
deterministic exact-path order and 262144-byte limit. The prompt asset remains
`workflows/library/prompts/generic_run_watchdog/repair_run_failure.md` and is
bound by the prompt extern manifest rather than a source-relative hidden path.

## Compatibility And Artifact Authority

The command adapters and repair prompt retain these operator-facing files:

- `${state_root}/watch.json` with schema `orchestrator_run_watch/v1`;
- `${evidence_root}/${target_run_id}-evidence.json` with schema
  `orchestrator_run_watchdog_evidence/v1`;
- `${repair_result_target_path}` and its referenced report/optional plan for a
  repair-required provider invocation; and
- `${state_root}/watchdog-result.json` with schema
  `orchestrator_run_watchdog_result/v1`.

Probe and publish dual-write their runtime-owned output bundle and the existing
semantic file. The repair provider returns a native typed record and also
writes the current semantic repair result/report files. Compatibility mirrors
are not orchestration control authority. The evidence file remains an
operator/provider input referenced by the watch bundle, and the final result
file remains the durable public path named by `watchdog_result_path`; neither
fact permits parsing a compatibility representation to choose a workflow
branch.

The adapters remain generic external effects. Probe owns run-store and clock
reads. Publish owns deterministic final serialization. Inline shell, stdout
scraping, and compiler special cases are not substitutes.

## Retry And Resume Contract

- If probe has not committed, retry may execute it again and observe the
  current run store and clock. Its writes are deterministic at the bound paths.
- Once probe commits, a downstream provider retry or resume reuses that
  validated probe result. The repair attempt receives a fresh immutable
  snapshot of the committed watch bundle on every new attempt.
- A retryable provider failure does not publish a result and does not turn
  process exit or prose into recovery success. The next attempt uses the same
  branch-local policy and a fresh dependency snapshot.
- Once the provider boundary commits, resume reuses its validated typed result
  without reopening the watch dependency or calling the provider again.
- If publication fails before commit, resume reruns only publication from the
  committed typed probe and repair/no-action results. Publication overwrites the
  same deterministic compatibility result and must be idempotent.
- The ordinary root/callee checksum guards, provider/command checkpoint
  validation, executable identity, and generated-path checks remain unchanged.
  Ambiguous or invalid resume state fails closed under the generic runtime.

A new observation of a target run after a completed probe requires a new
watchdog run, not mutation of an already committed probe boundary.

## Parity Cases

| Case | Probe fixture | Provider calls | Required proof |
|---|---|---|---|
| `running_or_completed` | `repair_required=NO` for current running or terminal-success state | `0` | No provider checkpoint; publish preserves watch status and emits `NO_ACTION`, `NONE`, and the bound result path. |
| `repair_required_codex` | Failed, stalled, or unknown state with `repair_required=YES` | `1 codex` | Exact Codex branch policy, one prompt dependency, typed repair result, compatibility artifacts, and final publication agree. |
| `repair_required_claude` | Failed, stalled, or unknown state with `repair_required=YES` | `1 claude` | Exact Claude branch policy with the same typed and artifact contract; no Codex invocation occurs. |
| `provider_retry` | Repair-required probe followed by one retryable provider failure | `2 attempts in one branch` | First attempt publishes nothing; retry captures a fresh dependency snapshot and only the validated successful typed result reaches publication. |
| `completed_resume` | Interrupt after committed repair provider result and before publication commit | `0 additional` | Resume reuses probe/provider checkpoints, performs one idempotent publication, and produces the same four outputs and semantic result. |

Migration parity must additionally prove the exact six inputs/four outputs,
both provider profiles, probe and publication command boundaries, the prompt
dependency metadata, required compile artifacts, and non-regression against
the frozen YAML characterization. Compile or dry-run success alone is not a
promotion claim.

## Feasibility And Genericity

This shape uses already implemented generic surfaces:

- `tests/test_workflow_lisp_structured_results.py` and
  `tests/test_workflow_lisp_native_returns_e2e.py` cover typed command/provider
  records and native transportable results;
- `tests/test_workflow_lisp_expressions.py` and
  `tests/test_workflow_lisp_variant_proofs.py` cover typed `if`, unions,
  exhaustive projection, and proof-scoped fields;
- `tests/test_workflow_lisp_provider_call_policy_e2e.py` covers call-local
  model/effort/timeout through public compile/run/resume;
- `tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py` covers exact
  required relpaths, immutable attempt snapshots, retry refresh, and completed
  reuse; and
- the promoted verified-iteration port demonstrates closed provider branches,
  command results, prompt dependencies, and direct typed publication through
  the ordinary WCC/schema-2 route.

The remaining work is family source, extern data, adapter dual-write, prompt
typed-return guidance, parity registration, runtime scenarios, and promotion
evidence. It requires no new language primitive and no family specific compiler
branch.

## Explicit Deferral

The proposal to separate recovery action from recovery certification in
`docs/backlog/active/2026-05-30-watchdog-recovery-status-model.md` is explicitly
deferred. This port preserves the existing `repair_status`, `recovery_action`,
watch-status, compatibility schemas, and four public outputs. It neither closes
that backlog item nor introduces liveness/certification fields under migration
cover. A later reviewed schema/version change must update YAML compatibility,
the `.orc` types, adapters, provider contract, consumers, and parity evidence
together.

## Implementation Handoff

The next tranche may add only the provider, prompt, and command manifests plus
adapter dual-write/typed-input support. The following tranche authors
`watchdog.orc` and adjusts the prompt to return the typed provider record while
retaining semantic files. Promotion remains a later gate after compile,
shared-validation, both runtime branches, retry/resume, typed parity, routing,
and independent reviews all pass. The YAML source remains untouched throughout
those tranches.
