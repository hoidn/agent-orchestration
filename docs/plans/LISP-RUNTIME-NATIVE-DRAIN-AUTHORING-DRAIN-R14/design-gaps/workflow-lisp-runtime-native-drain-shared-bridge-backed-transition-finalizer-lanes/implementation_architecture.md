# Shared Bridge-Backed Transition Finalizer Lanes Implementation Architecture

## Scope

This gap separates typed terminal return from retained compatibility effects in
the Design Delta selected-item/finalizer route.

## Contract

Imported `finalize-selected-item` must be able to return typed terminal values
without body-owned summary materialization, report parsing, pointer files,
compatibility bundle rereads, or hidden `StateExisting` transport.

If a public summary, legacy file, or durable state update is still required, it
is a separate effect over the already-typed terminal result:

- boundary publication;
- declared compatibility bridge for a named legacy consumer;
- typed `resource-transition` or certified transition backend; or
- runtime-owned checkpoint/resume state outside authored workflow data.

The source fix must not restore `run_state_path`, summary paths, pointer paths,
or generated roots to user-facing/domain records, loop state, selected-item
payloads, child-call signatures, or provider prompt subjects.

## Acceptance

The selected-item/finalizer route compiles through typed terminal return, no
ordinary internal composition path carries `run_state_path` or summary paths to
make the return work, and retained publication/bridge/transition behavior is
separate from value return.

Closeout artifacts may still need refresh after this slice. That is follow-up
work unless stale artifacts are direct runtime inputs or reveal a current
behavior defect.
