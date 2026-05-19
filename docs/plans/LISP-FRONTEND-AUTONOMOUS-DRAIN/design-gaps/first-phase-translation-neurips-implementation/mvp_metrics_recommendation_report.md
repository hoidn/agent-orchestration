# MVP Metrics Recommendation Report

## Scope

This report covers only the first Workflow Lisp implementation-attempt
translation slice from
`tests/fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc`.

The authored-LOC and boilerplate baseline is the four-step equivalent YAML
slice from `workflows/library/neurips_backlog_implementation_phase.v214.yaml`:

- `ExecuteImplementation`
- `SelectImplementationOutcome`
- `PublishCompletedExecutionReport`
- `PublishBlockedProgressReport`

## Metrics

| Metric | YAML slice baseline | `.orc` slice | Result |
| --- | ---: | ---: | --- |
| Authored lines | 143 | 71 | Pass |
| Manual state-path literal sites | 5 | 0 | Pass |
| Pointer-file literal sites | 4 | 0 | Pass |
| Manual paired variant checks | 2 | 0 | Pass |
| Markdown/text extractors | 1 | 0 | Pass |
| Shell/Python glue commands kept | 2 | 0 | Pass |
| Behavioral equivalence on existing tests | 3 focused selectors passed | 3 focused selectors passed | Pass |

## Evidence Notes

- LOC evidence:
  - equivalent YAML slice line count: `143`
  - `.orc` fixture line count: `71`
- Manual state-path literal count:
  - YAML slice still authors `state_root` bundle/pointer destinations directly.
  - `.orc` slice keeps those paths out of the workflow body; the phase context
    and compiler-owned lowering own the bundle target.
- Pointer-file literal count:
  - YAML slice still authors pointer-file destinations in the completed and
    blocked publish steps.
  - `.orc` surface authors none.
- Manual paired variant checks:
  - YAML slice manually pairs `when` + `requires_variant` for `COMPLETED` and
    `BLOCKED`.
  - `.orc` uses one typed `match`; variant proof is compiler/typechecker owned,
    so the manual paired-check count is `0`.
- Markdown/text extractor count:
  - YAML slice still uses `extract` to recover `blocker_class`.
  - `.orc` provider result emits the typed union bundle directly.
- Shell/Python glue command count:
  - YAML slice keeps two inline `python -c` publish wrappers.
  - `.orc` keeps none on the authored surface.

## Success Bar Evaluation

Section 13 minimum success bar:

- Authored `.orc` is shorter than the equivalent v2.14 YAML phase: Pass.
- Manual state-path count decreases: Pass.
- Variant-only field access is statically rejected outside `match`: Pass.
  - Fresh evidence: `python -m pytest tests/test_workflow_lisp_variant_proofs.py -k requires_proof_context -q`
- Provider output contract is generated from a typed record/union: Pass.
  - Fresh evidence: `python -m pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q`
- Existing v2.14 behavior tests still pass: Pass.
  - Fresh evidence:
    - `python -m pytest tests/test_workflow_lisp_phase_translation.py -q`
    - `python -m pytest tests/test_v214_runtime_semantics.py -k implementation_state -q`
    - `python -m pytest tests/test_neurips_steered_backlog_runtime.py -k implementation_phase_materializes_state_from_execution_report -q`

## Assessment

The translated `.orc` slice is materially less brittle than the equivalent YAML
slice. The authored surface removes manual pointer publication, markdown
extraction, inline semantic glue, and explicit completed/blocked routing while
keeping the typed union internal and preserving the record-only workflow
boundary.

## Recommendation

`continue toward defmacro and procedural library work`
