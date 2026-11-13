# Workflow Lisp Provider Live Binding

Status: **Historical — archived in place.** Superseded: `with-live-providers` refuses at build and its executor was removed on 2026-11-11 (reusable design: [salvage record](live_provider_supervision_and_peers_salvage.md)); the shared provider rules its preamble retains are stated by their owners, and the lines below that call them retained are part of the record. The complete original record below, including its original status, present-tense descriptions, schedules and acceptance language, is preserved for provenance. It supplies no current execution admission, work selection or copy-safe recipe. Current authority: [Providers](../../specs/providers.md), [Observability](../../specs/observability.md) and [evaluated execution](workflow_lisp_evaluated_execution.md). Where each of its rules went: [rule ledger](../reports/2026-11-13-design-corpus-rule-ledger.md#provider_live_binding-and-provider_peer_messaging).

The historical body begins below; original results and qualifications are unchanged.

Status: retained shared-service routing; historical executable protocol.
The target-2.16/2.17 group and target-2.23 phased execution routes are retired;
new calls, old-profile replay and old-profile mutation are unavailable in this
package. [Executor retirement](workflow_lisp_executor_retirement.md) and
[CLI](../../specs/cli.md) govern refusal and demonstrated exact-release recovery.
The design decisions worth reusing in a port to evaluated execution are in the
[salvage record](live_provider_supervision_and_peers_salvage.md).

Provider capability validation (`turn_boundary_resume`), ordinary provider execution, bounded cleanup and native session codecs remain owned by [Providers](../../specs/providers.md) and its retained adapter services.

Validated provider capabilities must fail closed on absence, malformed data or
unsupported operations. Transcript/pane bytes, receipts and diagnostic views
are never typed result authority. Partial/member attempts cannot be published
as a complete result, and cleanup/recovery cannot fabricate a commit or target
a different attempt. These invariants survive in their shared owners; the
historical group-specific state machine supplies no current launch permission.

<a id="summary"></a>
<a id="context-and-authority"></a>
<a id="t3a-observed-outcome"></a>
<a id="task-3-stoprevise-feasibility-result"></a>
<a id="problem"></a>
<a id="goals-and-non-goals"></a>
<a id="goals"></a>
<a id="non-goals"></a>
<a id="decision"></a>
<a id="chosen-approach"></a>
<a id="recorded-peer-messaging-owner-amendment-2026-07-24"></a>
<a id="alternatives-rejected"></a>
<a id="accepted-tradeoffs"></a>
<a id="authoring-and-type-contract"></a>
<a id="post-specialization-member-extraction"></a>
<a id="steering-directive-contract"></a>
<a id="language-integration"></a>
<a id="observation-pane-contract"></a>
<a id="pane-identity"></a>
<a id="non-interference"></a>
<a id="provider-capability-contract"></a>
<a id="session-transport-codec"></a>
<a id="executable-contract"></a>
<a id="runtime-ownership-and-concurrency"></a>
<a id="provider-attempt-ownership"></a>
<a id="cancellable-executor-control"></a>
<a id="turn-boundary-state-machine"></a>
<a id="launch"></a>
<a id="continue"></a>
<a id="steer"></a>
<a id="settlement"></a>
<a id="result-and-evidence-authority"></a>
<a id="atomicity-and-workspace-effects"></a>
<a id="checkpoint-retry-and-resume"></a>
<a id="invariants-and-failure-modes"></a>
<a id="invariants"></a>
<a id="fail-closed-cases"></a>
<a id="compatibility-and-versioning"></a>
<a id="verification-strategy"></a>
<a id="t1--observation-non-interference"></a>
<a id="t2--single-writer-concurrency"></a>
<a id="t3b--turn-boundary-integration"></a>
<a id="frontend-and-ir"></a>
<a id="dependencies-and-sequencing"></a>
<a id="success-criteria"></a>
<a id="stop--revise-criteria"></a>
<a id="documentation-impact"></a>
<a id="deferred-follow-ons"></a>

The original executable protocol, recovery amendments and delivery evidence are historical. Current shared-service boundaries are stated above; the original execution contract does not select or admit an evaluated port. See the [preserved record](../reports/documentation-history/workflow_lisp_provider_live_binding-history.md#summary).
