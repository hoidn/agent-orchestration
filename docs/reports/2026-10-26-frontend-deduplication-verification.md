# Frontend Deduplication Verification — 2026-10-26

**Role:** captured implementation, behavior and size evidence. Current contracts
are the [frontend](../design/workflow_lisp_frontend_specification.md#23-command-result),
[command boundary](../design/workflow_command_adapter_contract.md) and
[host-input](../design/workflow_lisp_durable_host_input.md) owners.
The [implementation plan](../plans/2026-10-26-frontend-deduplication-plan.md)
owns selection, decisions and completed integration gates.

## Scope and implementation

The isolated branch `feat/frontend-deduplication` implements three bounded
source/configuration forms: binding-supplied static command argv, a declared
prompt's host answer type, and shared command closures. The runtime, checked
artifact schema, Python authoring API and dependencies are unchanged. Explicit
forms and flat command maps remain supported. No tool-arity, command-return,
W1 constructor or typed failure-propagation inference was added.

| Commit | Change |
| --- | --- |
| `37dcb9c0` | Declared-prompt host answer inference; canonical imported type ownership |
| `faa73587` | External binding argv resolution before typed export; malformed imports refuse |
| `af09779e` | Discriminated shared-closure envelope; ordinary concrete bindings and retained raw capture |
| `9d4d2489` | Preserve resolved nested command argv in the existing typed match-subject path |
| `6cd27f16` | Combined public CLI execution, settlement, drift and recovery checks |

The full disposable DAQ compile first exposed the nested argv defect after the
initial command tranche passed. Completion was reopened, a portable regression
was added, and the correction above preceded successful before/after compilation.
The live DAQ workspace, pending request, frozen runtime and historical scorecards
were not edited or relaunched.

## Verification evidence

These are overlapping checks, not additive totals. Broad suites ran in tmux
from their respective repository roots with `-n 16 --dist=worksteal`; collection was checked for
changed test modules. Independent specification and code-quality reviews
approved the tranches, and an independent integrated code review reported no
regression issues. Final documentation review approved after the imported-type
prerequisites were clarified. The coordinator inspected and locally integrated
the reviewed diff, preserving all 29 pre-existing tracked changes outside staging.

| Check | Observed result |
| --- | --- |
| Baseline host/input-document/closure modules | 162 passed in 7.10s |
| Final host-input module after canonical type corrections | 99 passed in 5.73s |
| Host-adjacent prompt/generic/import/evaluated-host modules | 321 passed in 10.67s |
| Initial argv input-document/adapter/typed-frontend modules | 199 passed in 6.63s |
| Shared closure/configuration/build-artifact checks | 197 passed in 13.27s |
| Nested command focused regressions | 40 passed, 104 deselected in 3.24s |
| Nested command adjacent regression set | 372 passed in 11.31s |
| New combined public CLI module | 10 passed in 29.40s |
| Final fourteen-module regression set below | 580 passed in 93.16s; exit 0 |
| Maintained Lisp example after removing redundant host `:returns` | 1 passed in 11.22s; collect-only first collected 26 cases |
| Fresh integration on local `main`, including pre-existing working-tree edits | 293 passed in 43.23s; exit 0 |

The final regression command was:

```bash
python -m pytest -q -n 16 --dist=worksteal \
  tests/test_workflow_lisp_host_input.py \
  tests/test_workflow_lisp_command_input_documents.py \
  tests/test_workflow_lisp_command_adapters.py \
  tests/test_workflow_lisp_command_boundary_closure.py \
  tests/test_workflow_lisp_closed_program_frontend.py \
  tests/test_workflow_lisp_closed_program_compile_cli.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_lsp_cli_parity.py \
  tests/test_workflow_lisp_frontend_deduplication_e2e.py \
  tests/test_workflow_host_input_e2e.py \
  tests/test_workflow_evaluated_input_documents.py \
  tests/test_workflow_evaluated_command_replay.py \
  tests/test_workflow_evaluated_closure.py \
  tests/test_workflow_evaluated_resume_retry.py
```

The maintained example smoke used the actual collected parameter order:

```bash
python -m pytest --collect-only -q tests/test_workflow_host_input_e2e.py
python -m pytest -q 'tests/test_workflow_host_input_e2e.py::test_public_cli_workflows_recover_typed_outcomes_once[APPROVED-lisp]'
```

The final local integration command was:

```bash
python -m pytest -q -n 16 --dist=worksteal \
  tests/test_workflow_lisp_host_input.py \
  tests/test_workflow_lisp_command_input_documents.py \
  tests/test_workflow_lisp_command_boundary_closure.py \
  tests/test_workflow_lisp_frontend_deduplication_e2e.py \
  'tests/test_workflow_host_input_e2e.py::test_public_cli_workflows_recover_typed_outcomes_once[APPROVED-lisp]'
```

Before the final ledger update, the staged tree exactly matched reviewed feature
tree `61c1a8ee`. All original unstaged patch payloads were preserved, including
the two documentation files also touched by this feature; the other 27 original
tracked edits retained identical file hashes. The live DAQ workflow and command
manifest retained the identifying hashes below. All fourteen edited Markdown
files passed relative-link checks with explicit HTML anchors recognized;
staged whitespace checks passed.

The combined module exercises public `compile`, `run`, `input get`, `input
answer` and `resume` on expanded and abbreviated fixtures. It observes actual
command order and dispatch counts; absent, empty and populated documents;
concrete checked command/answer/closure contracts; changed shown evidence before
settlement and its restoration; changed shared helper bytes after approval and
their restoration; SIGKILL after a durably observed `must_not_repeat` write
which must refuse redispatch; and committed replay with no second write.
Source-free typed import and canonical prompt specialization have separate
owner tests. Public CLI resume still rebuilds recorded source/configuration for
currentness checks before using retained authority; these checks do not promise
public resume after source deletion or across rewritten builds.

A review probe found a **pre-existing generic host composition limit**: a generic
`defproc ask[T](value: T) -> String` directly matching a `request-input` whose
prompt declares a local enum can fail with `compiler_defect` /
`CanonicalNameError` (`owner_facts` is `None`). The reviewer reproduced the same
failure on baseline `1a8d5520` with explicit `:returns`, and on the implementation
with explicit and inferred returns. This change does not fix or qualify every
generic host combination; its required source-free import and specialization
cases pass. The limitation remains outside this frontend abbreviation scope.

All checks used deterministic local commands, local host settlement and, where
needed, the existing recording provider stub. Authenticated provider/judge
spend was zero. This is no quality comparison, calibration experiment,
LangGraph rejudging or live-device qualification.

## Same-format authoring measurements

Both source variants retain the same physical line layout. Both manifest
variants use JSON `indent=2` with a final newline. Unchanged configuration and
helper libraries are counted; moving a declaration is not counted as deletion.
Physical lines, bytes and duplicated facts are separate measurements.

### Disposable DAQ copy

The before copy came from
`/home/ollie/Documents/daq-debate-framework-v4-live/artifacts/debate/demo`.
The identifying before hashes are:

- `workflows/daq_diagnosis.orc`:
  `b83e7ccfa7d2cf4d8f0bcc6316074d1c19cd9be7f9584c726049e1f73e4a48a1`
- `inputs/commands.json`:
  `058b27810e71ff04258a7cebf88f48c39b599147cd272d63ea49bc3d21010ec9`

| Authored surface | Physical lines before → after | Bytes before → after |
| --- | --- | --- |
| Workflow | 132 → 132 | 9,469 → 8,945 |
| Command manifest | 115 → 76 | 2,108 → 1,453 |
| Other six configuration/helper files, unchanged | 542 → 542 | 26,451 → 26,451 |
| All eight files | 789 → 750 | 38,028 → 36,849 |

The eight-file total includes `demo.json`, `inputs/providers.json`,
`scripts/daq.py`, `tools/client.py`, `tools/daq.py`, `tools/evidence.py` and the
two changed files. The workflow has 121 nonblank/noncomment lines in both forms;
the manifest has 115 → 76. Eleven argv clauses remove 33 repeated literal
occurrences. Authored closure-path occurrences fall from 32 to four. Workflow
physical LOC is unchanged: the static argv omissions save bytes on existing
lines. The complete authoring reduction is 39 physical lines and 1,179 bytes.
The separate baseline one-line-array formatting observation (115 → 43 manifest
lines with equal parsed JSON) is not a language improvement and is excluded
from this before/after comparison.

Both disposable copies compiled with 13 sites and equal canonical program
digest `sha256:b430f5010be1f56086aafadea1411090f873ebc87a011f959d3360467886bf9a`.
Their normalized command configurations were equal. Build keys differed:
`f1240137d61110a4` before and `0c409bccd06b2623` after. Whole closed artifacts
were not byte-equal: `body` and `definitions` retained differing authored
locations. Equal digest in this observation is not a general identity or
cross-build recovery promise. No DAQ action or provider was executed.

### Portable combined integration fixture

The measured fixture is generated by `fixture_source()` and
`fixture_manifest()` in
[`tests/test_workflow_lisp_frontend_deduplication_e2e.py`](../../tests/test_workflow_lisp_frontend_deduplication_e2e.py).

| Authored surface | Physical lines before → after | Bytes before → after |
| --- | --- | --- |
| Workflow | 20 → 20 | 1,276 → 1,118 |
| Command manifest | 50 → 52 | 738 → 860 |
| Tool and shared helper, unchanged | 25 → 25 | 1,009 → 1,009 |
| Complete fixture | 95 → 97 | 3,023 → 2,987 |

Nonblank/noncomment totals are 94 → 96. Four argv clauses remove twelve repeated
literal occurrences, one repeated host answer type is removed, and the shared
helper path is declared once instead of four times. The envelope adds enough
structure that this small fixture **grows by two physical lines**, while saving
36 bytes overall. These forms remove repeated facts; they do not guarantee a
LOC reduction for every manifest size.

## Framework cost and retained evidence

Relative to design commit `1a8d5520`, production code through `6cd27f16` adds
156 and deletes 68 lines: **net +88 across five frontend files**. Tests add
877 and delete 20 lines: net +857 across eight test files. These are framework
and verification costs, separate from authored workflow/configuration savings.
Documentation and README growth are not language LOC savings. No runtime file
or new dependency contributes to the production diff.

Local execution logs and raw measurements were retained under
the implementation worktree's `.tmp/frontend-dedup/`, including
`final-regression.log`, `doc-example-smoke.log`, `daq-measure/metrics.json` and
`generic-metrics.json`. The main workspace's `.tmp/frontend-dedup/` retains
`main-integration.log`, its exit status and the final documentation link check.
They are untracked local evidence, not required repository inputs. This report
captures the stable readout; it does not claim full-suite coverage beyond the
listed regression set or close the independent LSP F2 qualification gate.
