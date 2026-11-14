# Identity invariants

Two files, and a third on request, that must be byte-identical between a task's base and its tip
when the task is not meant to change what any source compiles to. Used by the fix tasks of
[the defect backlog plan](../../docs/plans/2026-11-13-compiler-and-runtime-defect-backlog-plan.md)
that touch `orchestrator/workflow_lisp/` and by the tasks of
[the staged-workflow authoring plan](../../docs/plans/2026-11-13-staged-workflow-authoring-revisions-plan.md).

```bash
# from the repository root; scratch space (about 150 MB) is taken under TMPDIR and removed on exit
scripts/invariants/inv.sh <base revision> /path/out/base
scripts/invariants/inv.sh <tip revision>  /path/out/tip
cmp /path/out/base/digests.json /path/out/tip/digests.json
# compile.json: every row of the base equal on the tip; then the files the tip adds, with their exit codes
python -c 'import json,sys; b,t=(json.load(open(p)) for p in sys.argv[1:]); print([k for k in b if b[k]!=t.get(k)], {k: t[k]["exit"] for k in t.keys()-b.keys()})' \
  /path/out/base/compile.json /path/out/tip/compile.json
```

The first list is empty when nothing that compiled moved. When the tip adds no tracked `.orc`,
`cmp` of the two `compile.json` files says the same.

`inv.sh REV OUT_DIR` exports `REV` with `git archive`, runs the two scripts on the export and prints
the SHA-256 of both files. It takes a few minutes a side on a busy machine. With `RUNREF=DIR` (a
directory that does not exist yet, the same for both sides) it also runs the run-reference test
modules of the export serially in `DIR` and writes `runref.json`; that adds 15 to 25 minutes a side.
The programs embed `DIR`, so a `runref.json` hash holds only for that directory; record it with
the hash.

| File | Script | What it holds |
| --- | --- | --- |
| `compile.json` | `compile_all.py TREE OUT.json [JOBS]` | For every `.orc` of the export: the exit code and output of `orchestrator compile`, the program digest included for a file that builds. A source that mentions `providers.<x>` (dotted names included) gets a generated provider externs file binding each such name, and one that mentions `prompts.<x>` a generated prompt externs file binding each to a scratch `input_file`, so its provider calls reach typecheck. Prints the files, the builds and how many of the builds name a provider |
| `digests.json` | `digests.py OUT.json` | The corpus snapshot: the program digest, or the outcome that stopped the build, of every exported workflow under the corpus roots of `tests/workflow_lisp_closed_program_corpus.py` |
| `runref.json` (`RUNREF=DIR`) | `program_digests.py BASETEMP OUT.json` | For each test folder of a serial run of the run-reference test modules, the distinct digests of the run-reference programs it left, with the package identity and test-made commits removed |

**Never run the compile check inside the repository.** A compile writes `.orchestrate/build/` in the
directory it runs in. `compile_all.py` therefore compiles an export, each file in a scratch
directory of its own; do not point it at a working tree to compile in place.

Not covered, each compiled and recorded as it fails (counts on `main` at `9bb55dda`: 638 files,
75 build): a module with no entry workflow (84 files, `entry_workflow_required`); one that needs
a commands file (51 `command_adapter_missing_contract`, 42 `command_boundary_closure_missing`);
one whose providers are named only in an imported module (2 `provider_result_provider_invalid`);
and the 266 retired or unsupported targets.

`tests/test_invariant_scripts.py` runs each script on a tree of two sources.
