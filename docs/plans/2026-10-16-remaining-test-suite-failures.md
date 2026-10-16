# Remaining test suite failures

**Status:** Complete for the captured current working tree. The final verification
and commit boundary are recorded below; earlier checkpoints preserve their results.

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

## Subsequent integrated repairs (checkpoint record)

Pending statements in this section describe their respective checkpoints.

Loop-carrier registration now hydrates the retained concrete type, and syntax
and expression lookup share the declaration path and macro occurrence IDs.
Semantic family identity remains declaration plus introduction ordinal. The
independent contract and quality review passed; 218 owner cases and the public
command-only compile/run smoke passed. All eight original loop-related cases
also passed on integrated main.

Six test files now match the current provider invocation and file/2 guidance
contracts: complete invocation doubles, decoded authored annotations, selected
contract/prompt dataflow checks and two missing helper imports. All 172 affected
cases passed. The review tightened the Bool guidance oracle to reject an extra
wrapped overall annotation; the two final guidance cases passed again. These
snapshot-relative edits preserve the pre-existing provider and consumer work.

Preparation now retains opaque expression facts through the existing normalized
fact producer and accepts both raw checked Values and exact typed wrappers.
Independent review passed; the three original failures and 128 related cases
passed. A further integrated-main run covering use-site scope and both shared
provider-double callers passed all 70 cases.

This commit checkpoint includes compiler repairs and complete provider invocation
doubles. The three file/2-dependent test edits remain uncommitted alongside the
pre-existing file/2 implementation and consumer changes they require.
The final ten-module check on integrated main passed 310 cases in 7.43 seconds.

Eight documentation regressions now distinguish historical feature/wire contracts
from current source admission and route to their actual owners. The exact estate
projection, parity evidence, diagnostics and static-reader contracts remain
covered. Independent contract and quality review passed after adding two missing
owner/row checks. All 252 cases in the five affected modules passed, followed by
the two revised cases; six source-floor/retirement controls also passed. The final
five files were integrated at their reviewed hashes without changing documents.

Process cleanup now signals retained pidfds before global discovery and still
signals newly captured children within the same cleanup iteration. The redundant
pre-stop scan is skipped only for an expired target; other-expired-invocation
descendant evidence remains intact. Ancestor admission uses the existing pinned
edge identity while preserving strict source/payload validation. Five regression
cases, 388 owner cases and 11 fake-CLI timeout/recovery cases passed; three sealed
I0 environment cases remain skipped because their required identity is unset.
Both changed test modules collected 212 cases. Independent review passed and all
four files were integrated at reviewed hashes. The prior intermittent recovery
count failure passed narrowly; its original fine-grained cause remains unproven.

The watcher reuses checked state within an uninterrupted poll iteration while
retaining fresh reads after waits and recovery actions. The Neovim harness now
controls create-ACK/build scheduling and uses protocol barriers, preserving
current diagnostics and exact save-progress assertions. Separate real-stdio
checks retain public-module startup coverage. Independent review passed; 81
owner cases passed with one existing xfail. Both discovery cases used eight
Python starts through discovery, versus twelve in the original receipt; this
is a startup-count result, not a wall-time speed claim. The three reviewed files
were integrated at their frozen hashes.

The baseline-node ledger now accounts for all 106 failed cases passing focused
checks. One collection error remains. This accounting is not a final full suite
result: retained research demo algorithm/oracle coverage must be separated from
its archived retired-executor assertions, followed by the full default suite
and completion audit.

The integrated-main checkpoint for these documentation, process/isolation and
watcher/Neovim repairs passed 721 cases, with three existing environment skips
and one existing xfail, in 50.47 seconds. The complete default suite is pending.

The research demo collection error is repaired under the existing executor-retirement
decision. The complete original test module is preserved byte-exact in
`tests/fixtures/retired_execution/orc_research_demo.py.txt`. Its two exclusive trial
execution cases remain historical; all nine pure numeric and fifteen mixed
algorithm/oracle cases remain active as explicit leaf-composition unit fixtures.
Independent review confirmed the assertion/mutation ledger, exact numeric AST,
locally valid missing/reset/stale-root controls and independent expected values.
The existing `novel_cases.py` is included unchanged as their sole non-stdlib import
dependency; it requires no other untracked experiment assets. This retains algorithm
coverage without restoring or claiming historical workflow execution. Integrated
main collected all 24 retained cases and passed those plus both public retirement
checks (26 passed in 3.23 seconds). Full default-suite verification remains pending.

## Final verification and completion audit

The full default suite ran from main at `715673be`, with the current working-tree
changes present, using checkout-local `PYTHONPATH` and:

```bash
pytest -q -n 16 --dist=worksteal --tb=short \
  --junitxml=/tmp/orc-suite-repair-20261016/final-suite.xml \
  --basetemp=/tmp/orcf-20261016
```

Result: **16,044 passed, 117 skipped, 2 xfailed**, zero failures or collection
errors, exit 0, in 755.39 seconds. Independent and coordinator audits agree:

- All 106 original failed cases pass; one expanded case has two passing targets.
- All 15,897 previously passing cases remain passing, including reviewed renames.
- All 117 skip and two xfail identities and reasons remain unchanged.
- The 16,163 final case identities exactly match the reviewed population mapping:
  16,123 baseline cases, eight mapped originals replaced by nine successors,
  one collection-error record removed, and 40 explicit additions. Of those
  additions, 24 preserve research algorithm/oracle coverage; the two exclusive
  retired-execution cases remain in the exact original archive.
- The full file snapshots include tracked and nonignored untracked files, content,
  mode/ownership and symlink targets. There was no source, configuration or fixture
  drift, and no snapshot error. The sole added file was a native fake-launcher cache
  generated by `test_ambient_exec_is_not_mutable_after_verify` under `.tmp`;
  its embedded temporary script path and digest-derived name identify the test.

Receipts are in `/tmp/orc-suite-repair-20261016/`: `final-suite.log`,
`final-suite.xml`, `final-suite.exit`, the command and before/after/drift manifests,
`final-population-allowances.json`, `final-root-completion-audit.json`, and
`final-suite-independent-audit.json` / `final-suite-independent-review.md`.
Each repair also retains its independent review and focused/public-smoke evidence.
The final documentation-only closure changes no runnable input or test contract.

This establishes the repaired current working tree, not a clean-HEAD qualification.
Task commits on main are `a8ffc599`, `ae3cb66c`, `5f05b5cb` and `715673be`; unrelated
user commits and local work remain preserved. Three reviewed test adjustments in
`tests/test_workflow_evaluated_consumers.py`, `tests/test_workflow_evaluated_providers.py`
and `tests/test_workflow_lisp_result_guidance_e2e.py` remain uncommitted with the
pre-existing file/2 implementation changes they require. No push or live-provider
campaign was performed. The default-suite repair objective is complete; existing
live/environment prerequisite gates and the two pre-existing xfails are unchanged.
