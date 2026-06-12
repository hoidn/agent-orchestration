# README Conceptual Rewrite Plan

Status: plan
Created: 2026-06-12
Scope: rewrite `README.md` so it introduces the project by its conceptual
thesis rather than as a generic workflow runner.

## Diagnosis of the current README

The current README describes features ("strict YAML DSL", "contract-checked",
"filesystem-native evidence") without the organizing idea that explains why
they exist. A reader cannot tell this apart from a generic pipeline tool.

## Thesis to communicate

Programming with LLM agents today is done the way machines were programmed
before compilers: hand-allocated storage (invented file paths), hand-written
calling conventions (output formats described in prose per prompt),
hand-parsed return values, hand-verification, hand-rolled recovery. This
project is the missing toolchain: workflows are typed programs, the agent is
an effectful unreliable coprocessor, and the compiler/runtime own layout,
contracts, verification, routing proof, resume, and provenance.

## Verified implementation anchors (claims must stay factual)

- Type-to-prompt contract rendering:
  `orchestrator/workflow/prompting.py:107`
  (`apply_output_contract_prompt_suffix`) appends deterministic
  output-contract blocks for `expected_outputs` / `output_bundle` /
  `variant_output`.
- Generated path ownership: `StateLayout` / `PathAllocator`
  (runtime migration foundation; `orchestrator/workflow/state_layout.py`).
- Fail-closed structured results, variant proof via `match`, values vs
  views: drafting guides and `specs/`.
- Resume, source maps, run evidence: existing observability surfaces.
- Status honesty: YAML DSL is the mature normative surface; Workflow Lisp
  is the typed frontend with parity-gated promotion
  (`docs/capability_status_matrix.md`).

## Structure

1. Title + short definition.
2. "The Missing Toolchain" — compiler analogy with hand-rolled-today vs
   toolchain-owned-here mapping table.
3. "What That Looks Like" — canonical typed union + provider-result +
   match example with annotations of what the toolchain does.
4. "Guarantees" — enforced rules.
5. "Two Authoring Surfaces" — YAML (normative) and Workflow Lisp (typed
   frontend), capability-matrix routing.
6. Practical sections retained and condensed from the existing README:
   Start Here, Install, First Dry Run, Run For Real, Observability, repo
   map, Common Commands (deduplicated), Versioning, Debugging Rule Of
   Thumb; License moved to the end.

## Verification

- `git diff --check` clean; all referenced paths resolve.
- No capability over-claims (cross-check against capability matrix labels).
