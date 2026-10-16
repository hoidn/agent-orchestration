# Remaining test suite failures

## Objective and authority

Repair the remaining failures in the current working tree and verify the full
default pytest population. This plan selects repairs, not new language features
or changes to historical qualification claims. Current contracts are routed by
`docs/index.md`, `docs/capability_status_matrix.md`, and `docs/design/README.md`.

The previous full result (15,874 passed, 71 failed) is diagnostic input only.
Current main starts at `be3e3040` with pre-existing uncommitted work. Preserve it.
Initial diff, status, hashes, failure traces and new verification receipts live
in `/tmp/orc-suite-repair-20261016/`.

## Execution

1. Reproduce representative failures, then run the complete default suite with
   `PYTHONPATH=$PWD pytest -q -n 16 --dist=worksteal` in tmux. The explicit path
   prevents subprocesses importing the unrelated installed omp worktree.
   Preserve all failures and distinguish obsolete cache entries from live tests.
2. Repair compiler causes against current 2.35–2.39 contracts: typed union tags,
   lexical scope, procedure effects, loop carrier identity, and transport checks.
   Delegate bounded implementation slices after root-cause diagnosis; reproduce
   each regression before editing and inspect affected callers and contracts.
3. Restore compiler-owned navigation facts lost through inline normalization;
   preserve the LSP current-snapshot and namespace checks. Verify direct calls,
   imported calls, and real stdio editor sessions.
4. Diagnose and repair remaining runtime, isolation, probe, documentation and
   test-harness failures. Preserve external prerequisite checks and historical
   evidence. Do not skip, xfail, delete or weaken tests to conceal defects.
5. Run focused owner tests after each repair. Collect modified modules when tests
   are added or renamed. Run public workflow smoke checks for compiler/runtime
   changes, then repeat the full default suite in tmux with 16 workers. Record
   node populations, skips, failures, source drift and any genuine limitations.
6. Obtain independent contract and code-quality review of implementation changes,
   inspect the final diff and verification personally, and close the goal only
   with a passing full suite on the final integrated source.

## Constraints and tradeoffs

Use existing implementations and narrowly scoped fixes. Do not restore retired
execution paths, add compatibility layers, or run paid/live providers. Retaining
the full test population makes diagnosis more expensive than suppressing failing
checks, but preserves the contracts the suite is meant to enforce. Changes to
files with existing local work must preserve those edits; no blanket staging,
reset, stash or push is part of this repair plan. The user subsequently requested
staging and committing the completed repairs; commit only the reviewed task files.

## Partial repair checkpoint

The fresh baseline on unchanged main source finished with 15,897 passed,
106 failed, 117 skipped, two xfailed and one collection error. Source/test hashes
showed no drift during that run. This supersedes the earlier 71-failure input.

Reviewed repairs retain authored direct-call facts for LSP navigation, preserve
generic union discriminants during re-typechecking, canonicalize concrete
workflow effects across admitted origins, reject forbidden leaves in structured
workflow returns, and recognize the current replay handler in growth-test tracing.
The repair files were integrated into main with byte-for-byte checks against the
reviewed worktree, preserving all pre-existing edits.

Focused evidence includes 152 LSP/editor checks, 130 adjacent compiler checks,
36 return-contract checks, one public compile smoke and the exhaustive growth
check passing. The broader type-owner run passed 519 cases and retained two
known loop-carrier failures. These are partial results, not a passing full suite.
The integrated main checkpoint collected 325 cases in the changed test modules;
its combined compiler, LSP/editor and public CLI check passed 665 cases with only
the same two loop-carrier failures. Hash comparison confirmed that every file
outside this checkpoint remained unchanged from the initial snapshot.
Loop carriers, preparation values, process handling, documentation tests and the
additional failures from the fresh baseline remain to be repaired and verified.
