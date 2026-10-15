# Acceptance Tests (Normative)


Status: current conformance requirements, with explicitly separated historical
format/reader obligations and unselected qualification targets. [CLI](../cli.md#executable-support-boundary)
and [versioning](../versioning.md#executable-support-and-historical-version-gates)
own executable admission; [State](../state.md) owns persistence/read schemas.

## Current Executable Conformance

Acceptance must exercise the public admitted route, not merely recognize an
older source/type header. The following requirements consume their named
normative contracts and current owner suites:

| Boundary | Required behavior | Current proof owners |
| --- | --- | --- |
| Frontend/admission | `.orc` entry target admission is separate from retained typed imports/LSP. Retired executable entries refuse before build/run publication. Old-profile resume/invalidation refuse before locks, source loading or run mutation; no conversion, repair, fallback or shim. | [CLI](../cli.md), [versioning](../versioning.md); `tests/test_executor_retirement_cutoff.py`, `tests/test_yaml_frontend_retirement.py` |
| Checked compilation | Close admitted typed definitions, imports, types/configuration and effect sites into one validated artifact. Preserve exact source provenance, closed effect admission, variant proof and static callable boundaries; unsupported effects refuse with their owner diagnostic. | [DSL](../dsl.md), [evaluated design](../../docs/design/workflow_lisp_evaluated_execution.md); `tests/test_workflow_lisp_closed_program_compile_cli.py` |
| Public lifecycle | Compile/bind before allocation; publish header/artifact/memo durably before effects; validate typed results before commit. Resume checks recipe/program/input and every committed effect input before launch, reconciliation or tail repair; committed effects are reused. | [State](../state.md#evaluated-execution-persistence-profile-target-235), [CLI](../cli.md#resume-preflight-precedence), [IO](../io.md); `tests/test_workflow_evaluated_cli.py`, `tests/test_workflow_evaluated_public_identity.py` |
| Invalidation | Validate the entire selected suffix and its coordinator restrictions, append the admitted invalidation record atomically, and rerun only the invalidated suffix as new attempts. No hidden value-dependence or force bypass. | [State](../state.md), [CLI](../cli.md); `tests/test_workflow_evaluated_invalidate_smoke.py`, `tests/test_workflow_evaluated_invalidate.py` |
| Commands/provider IO | Exact closure/input/dependency/policy identity, bounded output, selected result-file authority, finite typed value validation and before-publication checks. Dependencies/rendering are immutable per attempt; retries take fresh snapshots. | [IO](../io.md), [Providers](../providers.md), [Dependencies](../dependencies.md); `tests/test_output_contract.py`, `tests/test_prompt_contract_injection.py`, `tests/test_workflow_evaluated_provider_reads.py` |
| Security | Enforce owning path/root, secret, credential, descriptor, process and network rules at their trust boundaries. Ordinary host calls are not OS sandboxes; requested required isolation cannot silently fall back. Confined profiles require their actual independent enforcement/qualification witnesses. | [Security](../security.md), [Providers](../providers.md), [IO](../io.md); profile-specific acceptance below |
| Read-only views | Reports/dashboard reconstruct evaluated state from validated authority without source compilation or run writes. Historical readers preserve schema/privacy and untrusted-path containment; rendered state, prompt evidence, pointers and logs never become executable authority. | [State](../state.md), [Observability](../observability.md), [Security](../security.md); `tests/test_workflow_evaluated_readers.py`, `tests/test_workflow_evaluated_dashboard.py`, `tests/test_dashboard_preview.py` |

Run narrow relevant selectors first. Shared unit coverage, deterministic public
lifecycle evidence, actual confinement and live-provider qualification establish
different claims. A collected test, mock provider or private transport proof
cannot qualify native authentication/TLS or public admission. Later target
features retain their own gates; this index selects no research or migration.

## Retained Source, Format And Reader Conformance

Historical versions still constrain registered syntax, imported typed signatures,
contract refinement, exact source ownership and historical wire interpretation.
Their versioned rule is retained when the current owner in [DSL](../dsl.md),
[State](../state.md), [IO](../io.md), [Providers](../providers.md),
[Dependencies](../dependencies.md) or [Security](../security.md) says so.

In particular, preserve variant-field proof, source-versus-workspace path roots,
validate-before-publication, strict closed JSON/type contracts, canonical artifact
versus pointer authority and confidential identity-only diagnostics. Historical
step/call-frame/checkpoint identities must remain scoped and unambiguous in any
reader that consumes them; never guess from names, parse qualified IDs to repair
state, backfill/remap identities, follow state-provided serving roots or trust
report prose. Retaining a reader does not retain its old executor or mutation
API. Exact-release recovery requires the separate evidence and retained environment
in [executor retirement](../../docs/design/workflow_lisp_executor_retirement.md).

## Historical Acceptance And Delivery Evidence

<a id="canonical-list-v11--v111"></a>
<a id="completed-resume-projection-integrity-executable-proof-routing"></a>
<a id="dsl-evolution-rollout-crosswalk"></a>
<a id="future-acceptance-v12"></a>
<a id="future-acceptance-json-stdout-validation"></a>

The original numbered v1.x–2.34 checklist, projection-integrity proof routing, rollout crosswalk and then-future proposals are historical. Retained format/reader rules remain binding only where their current owning spec retains them; no historical clause admits flat execution or a legacy resume fallback. See the [preserved record](../../docs/reports/documentation-history/specs-acceptance-index-history.md#historical-operational-record-2).

<a id="future-acceptance-run-ref-confined-child-environments-target-238"></a>

## Acceptance Scope (Run-Ref Confined Child Environments, target 2.38)

Command-only Increment A is admitted: compile/run/interrupted-resume/completed-resume/report,
durable recovery, typed exports and cleanup have bounded acceptance evidence in
the [plan/report](../../docs/plans/2026-10-14-run-ref-expression-environments-plan.md).
The complete tool-enabled provider flow below remains a qualification requirement,
not public admission; private transport checks do not qualify real native auth/TLS.
Use the [command-only recipe](../../docs/lisp_workflow_drafting_guide.md#confined-workflow-children-target-238-command-only)
for current usage. The
[design](../../docs/design/workflow_lisp_run_ref_expression_environments.md#verification-and-declarative-acceptance-scenarios)
owns their full statements and the F1 to F6 gates (with F3b-channel and
F3b-checkpoint); real-sandbox cases skip when `bwrap`,
`systemd-run` or a reachable user manager is missing.

1. Normal tool-enabled flow: the design's complete module with three
   candidates through public compile/run returns a typed selection, three
   distinct child registrations and workspaces, ordinary provider attempts,
   bounded delta/accounting, and an exported file under its declared root,
   with no provisioning command in the workflow.
2. Independent environments: children see no peer, parent or control
   canaries; parent/home/socket/metadata-network access, fork, workspace
   fill, `kill 0`, spawner signals and output floods are bounded by
   enforcement; the exhausted candidate yields `FAILED` and the search
   continues.
3. Recovery across the commit gaps: public kills before the first child
   commit, after a committed child effect, during a checkpoint, between a
   checkpoint and its commit, after an unpersisted rerun, after
   terminal/export preparation and after parent commit; a holder death
   under a live controller yields `FAILED` without resume. After the first
   commit resume keeps the child id and committed calls and reruns only the
   pending attempt under §8.1.
4. Typed export and retention: exact rebased values, alias identity,
   no-overwrite writes, clone deletion followed by a dispatch-free completed
   resume, cleanup-failure retry, and refusal of tampered export, traversal,
   symlink, special file, reserved root, `:must-exist false`, incompatible
   refinement and a candidate symlink to a host canary at the next `:doc`
   read.
5. Authority and compatibility: changed image, provider configuration,
   child definition or declared input refuses before dispatch; source
   relocation keeps identity; old path-child runs read unchanged; forged
   headers/requests and injected parent descriptors refuse before release;
   a request through `provider_phase_isolation.v1` refuses as an unsupported
   backend.
