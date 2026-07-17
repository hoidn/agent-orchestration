# Design Delta Finalizer-Projection Checkpoint-Retention Decision

> **For agentic workers:** This bounded Task 5 decision is a strict
> compatibility stop. Do not execute the hypothetical source edit,
> refresh a checkpoint baseline, or add compiler/runtime substrate from this file.

**Status:** Complete by reviewed strict-compatibility stop. Independent
specification and quality re-review approved the retained finalizer-projection
decision and its inventory reconciliation. Task 5 as a whole remains open;
blocked recovery/finalization is the current subfamily.

**Goal:** Decide whether the four finalizer-projection calls in
`workflows/library/lisp_frontend_design_delta/work_item.orc` can become inline
procedure calls while preserving the strict public-wrapper checkpoint contract.

**Executed architecture:** Keep the production source at its real path and
intercept `Path.read_bytes`, `Path.read_text`, and read-only `Path.open` for
that exact path throughout parser, compiler, and WCC processing. Compile the
retained bytes and a deterministic hypothetical inline conversion in separate
temporary workspaces, reject every exact-path `Path.open` mode containing
`w`, `a`, `x`, or `+` plus direct `Path.write_text`/`Path.write_bytes`, and
verify the real production bytes and digest again during failure-safe cleanup.
Count every intercepted read, compare complete effect-boundary checkpoint
sets, and compare workflow source-owner maps. The existing Design Delta
public-wrapper run is retained only as unaffected-route characterization; it
does not execute the four affected calls.

**Approach tradeoff:** Retention keeps three small projection helpers as
workflows and four call sites as workflow calls. This preserves existing
run/resume checkpoint identity; removing the wrappers now would require an
unaccepted identity remap, baseline refresh, or state-upgrade contract.

## Root cause and governing decision

The complete exact-path hypothetical compile changes persisted identity. Its
three `defproc :lowering inline` substitutions and four positional applications
remove four compiler-owned call checkpoints and add no replacement checkpoint
identity. That identity delta alone is sufficient for retention under strict
compatibility.

This experiment does not establish behavioral feasibility or runtime parity
for the completed/blocked finalizer paths. The deterministic public-wrapper
scenario selects and executes only selector/architect work; it does not execute
any of the four affected call nodes. Equal output, artifact, publication, and
resource-transition values from that run characterize only the unaffected
route and are not required for the retention conclusion.

The governing
`docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`
contract makes `strict_compatibility` mandatory for this live production route.
Exact checkpoint identity therefore wins over source simplification. The
bounded `reviewed_internal_identity_retirement` exception is not selected, and
this task creates no retirement record, owner gate, run-store scan, remap, or
cross-source resume claim.

Therefore:

- the production source and its derived runtime mirror remain byte-unchanged;
- `project-selected-item-finalizer-approved-plan`,
  `project-selected-item-finalizer-completed-implementation`, and
  `project-selected-item-finalizer-blocked-implementation` remain
  `defworkflow` definitions;
- their exact four occurrences remain explicit workflow calls;
- exported `run-work-item` remains a workflow;
- the four active inventory rows become `effect-adapter` rather than moving to
  history;
- no compiler/runtime substrate or checkpoint baseline refresh is authorized;
  and
- the finalizer-projection subfamily closes as retained; after its independent
  specification and quality re-review, Task 5 selects blocked
  recovery/finalization as the current subfamily.

## Exact inventory boundary

All four IDs retain their stable locators and current-source status:

- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:project-selected-item-finalizer-approved-plan:1`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:project-selected-item-finalizer-completed-implementation:1`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:project-selected-item-finalizer-approved-plan:2`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:project-selected-item-finalizer-blocked-implementation:1`

The active internal-call counts change from 22 procedure candidates, 10 effect
adapters, and 63 legacy-retire rows to 18, 14, and 63 respectively. The eight
separate public entries and one append-only history row do not change. The
inventory `source_commit` does not change because neither authored source nor
the active-source population changed.

## Reproducible same-path comparison

The executable selector is
`tests/test_workflow_lisp_procedure_first_migrations.py::test_design_delta_finalizer_hypothetical_removes_four_public_wrapper_checkpoints`.
It feeds retained and hypothetical bytes to every `Path.read_bytes`,
`Path.read_text`, and read-only `Path.open` access for the same absolute
production path without writing that path. Exact-path `Path.open` modes with
`w`, `a`, `x`, or `+`, plus `Path.write_text` and `Path.write_bytes`, fail
closed. A `finally` check compares the disk bytes and SHA-256 with the
pre-interception production file after each retained or hypothetical compile,
including an exceptional compile exit. Per-method counts and the digest of
every served read prove that the hypothetical compile receives only
hypothetical bytes; the retained source digest never appears in its served-read
evidence. Both variants record positive `read_bytes` and `read_text` counts,
and `Path.open` remains guarded and counted if a direct read occurs. Literal
counts are intentionally not a contract because compiler cache/order state may
change how many times the same selected bytes are read.

The complete effect-boundary checkpoint projections are:

- retained public-wrapper checkpoint digest:
  `sha256:d0c2ef05da988b3fb6bd93a30f426ee6dec55ed4f905b72ae6efeaa63c12e8a8`;
- hypothetical inline checkpoint digest:
  `sha256:275f8563b6fd7c3909f13cdf4554b570fe2fcded94c7e4fdb46385b9844a0c0d`;
- added checkpoint identities: none; and
- removed checkpoint identities: exactly four.

The exact removed checkpoint IDs and presentation names are:

| Checkpoint ID | Presentation name |
| --- | --- |
| `ckpt:719e087e3f3fd34effef1df2` | `lisp_frontend_design_delta/work_item::finalize-selected-item-from-completed-implementation::lisp_frontend_design_delta/work_item::finalize-selected-item-from-completed-implementation__implementation__call_lisp_frontend_design_delta/work_item::project-selected-item-finalizer-completed-implementation` |
| `ckpt:a50e5dd2106381d32be8aed9` | `lisp_frontend_design_delta/work_item::finalize-selected-item-from-completed-implementation::lisp_frontend_design_delta/work_item::finalize-selected-item-from-completed-implementation__plan__call_lisp_frontend_design_delta/work_item::project-selected-item-finalizer-approved-plan` |
| `ckpt:bad73d47b2fb350f033b5621` | `lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation::lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation__implementation__call_lisp_frontend_design_delta/work_item::project-selected-item-finalizer-blocked-implementation` |
| `ckpt:e915cc6153281198cd61b3e7` | `lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation::lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation__plan__call_lisp_frontend_design_delta/work_item::project-selected-item-finalizer-approved-plan` |

The workflow source-owner comparison proves only:

- every common retained workflow-owner key has the same path;
- the hypothetical workflow-owner map adds no key; and
- exactly these three workflow-owner keys disappear:
  - `lisp_frontend_design_delta/work_item::project-selected-item-finalizer-approved-plan`;
  - `lisp_frontend_design_delta/work_item::project-selected-item-finalizer-completed-implementation`; and
  - `lisp_frontend_design_delta/work_item::project-selected-item-finalizer-blocked-implementation`.

The experiment makes no claim about affected inline-procedure provenance.

The existing deterministic public-wrapper runs also produce equal values for:

- typed public workflow outputs;
- artifact paths and contents;
- publication paths and view digests;
- resource-transition step IDs, resource IDs, and replay flags; and
- provider and command attempt sequences.

Neither run executes an affected finalizer call. These equalities are
unaffected-route characterization only; they prove no finalizer behavioral or
runtime parity and are not needed to reject the checkpoint identity change.

## Source and mirror provenance

Commit `79a397bbee257526a07634b30876b1ef4dc0b3fd` is the authorized mirror
correction provenance: it added the Task 5 rule that a changed production owner
and its derived runtime mirror must move together and remain byte-equal. It did
not authorize a source migration and did not change either file.

At this decision boundary, both files have SHA-256
`216e53dedc2e815d33166c2f3d5e5b6e69319b91bee9a97222a197f771b2dcba`:

- `workflows/library/lisp_frontend_design_delta/work_item.orc`; and
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/work_item.orc`.

The hypothetical exists only as deterministic test input. No source, mirror,
YAML, compiler/runtime implementation, checkpoint baseline, inventory history,
or run store is changed by this decision.

## Verification contract

The reviewed retained decision is supported by fresh checks proving:

1. JSON parsing and 18/14/63 active-count reconciliation;
2. all four rows are active `effect-adapter` records with both exact selectors;
3. the three definitions, four calls, and exported `run-work-item` remain
   structurally present;
4. the same-path comparison counts every intercepted read, proves no retained
   byte digest leaks into the hypothetical compile, reproduces both full
   checkpoint digests, finds exactly four removals with no additions, rejects
   every write-capable `Path.open` variant and direct pathlib write helper, and
   proves disk bytes/digest unchanged after each compile;
5. `source_commit`, public-entry count, and history remain unchanged;
6. common retained workflow-owner keys are equal, exactly the three converted
   workflow-owner keys disappear, no owner key is added, and no affected inline
   provenance is claimed;
7. the unaffected-route runtime characterization is explicitly excluded from
   finalizer parity evidence;
8. production source and runtime mirror have no diff; and
9. focused tests, collection, and touched-file diff checks pass.

This is a fail-closed retention result, not Task 5 completion.
