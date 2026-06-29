# Work-Item Mixed-Caller Hidden Phase Context Contract Plan

## Goal

Restore the shared private `phase-ctx__work-item` binding for both direct
parent-call routes and imported selected-item stdlib routes.

## Steps

1. Reproduce the focused hidden-context failure for `run-work-item`.
2. Normalize the callee hidden requirement for `run-work-item`.
3. Admit the two structural caller modes: entry/bootstrap and
   `ItemCtx + typed payload`.
4. Ensure lowering and boundary projection emit private
   `phase-ctx__work-item` metadata rather than public context fields.
5. Run focused compile, diagnostic, and boundary/build checks for the two
   admitted modes and one invalid caller shape.

## Acceptance

Both admitted caller modes work through one shared route, invalid callers fail
closed, and no public/domain signature is widened to carry `phase-ctx`.
