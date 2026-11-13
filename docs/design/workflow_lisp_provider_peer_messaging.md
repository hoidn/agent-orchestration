# Workflow Lisp Provider Peer Messaging

Status: **Historical — archived in place.** Superseded: `with-live-provider-peers` refuses at build, and its executor and `peer-*` commands were removed on 2026-11-11 (reusable design: [salvage record](live_provider_supervision_and_peers_salvage.md)); the shared provider rules its preamble retains are stated by their owners, and the lines below that call them retained are part of the record. The complete original record below, including its original status, present-tense descriptions, schedules and acceptance language, is preserved for provenance. It supplies no current execution admission, work selection or copy-safe recipe. Current authority: [Providers](../../specs/providers.md), [Observability](../../specs/observability.md) and [evaluated execution](workflow_lisp_evaluated_execution.md). Where each of its rules went: [rule ledger](../reports/2026-11-13-design-corpus-rule-ledger.md#provider_live_binding-and-provider_peer_messaging).

The historical body begins below; original results and qualifications are unchanged.

Status: retained shared-service routing; historical executable protocol.
The target-2.16/2.17 group and target-2.23 phased execution routes are retired;
new calls, old-profile replay and old-profile mutation are unavailable in this
package. [Executor retirement](workflow_lisp_executor_retirement.md) and
[CLI](../../specs/cli.md) govern refusal and demonstrated exact-release recovery.
The design decisions worth reusing in a port to evaluated execution are in the
[salvage record](live_provider_supervision_and_peers_salvage.md).

Structural `interactive_terminal_turn_queue.v1` validation, adapter start/offer/close/join/abort and receipt integrity remain owned by [Providers](../../specs/providers.md). Retaining an adapter does not admit a peer-group coordinator.

Validated provider capabilities must fail closed on absence, malformed data or
unsupported operations. Transcript/pane bytes, receipts and diagnostic views
are never typed result authority. Partial/member attempts cannot be published
as a complete result, and cleanup/recovery cannot fabricate a commit or target
a different attempt. These invariants survive in their shared owners; the
historical group-specific state machine supplies no current launch permission.

<a id="summary"></a>
<a id="authority-and-non-regression-boundary"></a>
<a id="feasibility-result"></a>
<a id="current-transport-finding"></a>
<a id="fresh-real-client-probe"></a>
<a id="goals"></a>
<a id="non-goals"></a>
<a id="language-contract"></a>
<a id="surface"></a>
<a id="effects"></a>
<a id="target-gate"></a>
<a id="wcc-and-lowering"></a>
<a id="executable-contract"></a>
<a id="structural-provider-capability"></a>
<a id="runtime-owned-peer-surface"></a>
<a id="commands"></a>
<a id="endpoint-identity"></a>
<a id="message-size-and-text"></a>
<a id="member-lifecycle"></a>
<a id="readiness"></a>
<a id="send-and-acknowledgement"></a>
<a id="cooperative-finish-and-natural-close"></a>
<a id="message-ledger-and-evidence"></a>
<a id="coordinator-and-atomic-settlement"></a>
<a id="races"></a>
<a id="checkpoint-retry-and-resume"></a>
<a id="fail-closed-cases"></a>
<a id="compatibility-and-versioning"></a>
<a id="verification-strategy"></a>
<a id="capability-and-adapter"></a>
<a id="ingress-and-ledger"></a>
<a id="frontend-and-ir"></a>
<a id="runtime"></a>
<a id="real-gates"></a>
<a id="implementation-record"></a>
<a id="success-criteria"></a>
<a id="stop--revise-criteria"></a>
<a id="deferred-follow-ons"></a>

The original executable protocol, recovery amendments and delivery evidence are historical. Current shared-service boundaries are stated above; the original execution contract does not select or admit an evaluated port. See the [preserved record](../reports/documentation-history/workflow_lisp_provider_peer_messaging-history.md#summary).
