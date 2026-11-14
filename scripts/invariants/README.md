# Identity invariants

Two files that must be byte-identical between a task's base and its tip when the task is not meant
to change what any source compiles to. Used by the fix tasks of
[the defect backlog plan](../../docs/plans/2026-11-13-compiler-and-runtime-defect-backlog-plan.md)
that touch `orchestrator/workflow_lisp/`.

```bash
# from the repository root; scratch space (about 150 MB) is taken under TMPDIR and removed on exit
scripts/invariants/inv.sh <base revision> /path/out/base
scripts/invariants/inv.sh <tip revision>  /path/out/tip
cmp /path/out/base/compile.json /path/out/tip/compile.json
cmp /path/out/base/digests.json /path/out/tip/digests.json
```

`inv.sh REV OUT_DIR` exports `REV` with `git archive`, runs the two scripts on the export and prints
the SHA-256 of both files. It takes a few minutes a side on a busy machine.

| File | Script | What it holds |
| --- | --- | --- |
| `compile.json` | `compile_all.py TREE OUT.json [JOBS]` | For every `.orc` of the export: the exit code and output of `orchestrator compile`, the program digest included for a file that builds |
| `digests.json` | `digests.py OUT.json` | The corpus snapshot: the program digest, or the outcome that stopped the build, of every exported workflow under the corpus roots of `tests/workflow_lisp_closed_program_corpus.py` |

**Never run the compile check inside the repository.** A compile writes `.orchestrate/build/` in the
directory it runs in. `compile_all.py` therefore compiles an export, each file in a scratch
directory of its own; do not point it at a working tree to compile in place.

Not covered: the digests of run-reference programs, and programs that build only with provider
externs supplied. A change to run-reference code needs the run-reference test modules as its check.

`tests/test_invariant_scripts.py` runs each script on a tree of two sources.
