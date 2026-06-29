# Reference-Family Default-Path Completion Inventory Conformance Plan

## Goal

Make the checked default Design Delta `completion_inventory` path pass through
production evidence roots without weakening the gate or relying on temporary
fixture overrides.

## Steps

1. Audit completed gaps from canonical run state against the checked drain
   summary, per-gap summaries, production architecture files, and architecture
   index.
2. Backfill real production architecture documents for completed gaps that have
   recoverable source material.
3. Regenerate or update the production architecture index from those documents.
4. Keep negative coverage for missing production architecture evidence and
   missing index coverage.
5. Run the focused default-path build/conformance checks.

## Acceptance

The default checked path passes the `completion_inventory` surface without
alternate roots or placeholders, and negative tests still reject missing
production evidence.
