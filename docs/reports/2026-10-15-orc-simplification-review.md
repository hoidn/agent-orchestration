# ORC Simplification Review: Captured Findings And Dispositions

Status: captured review evidence, 2026-10-15. This report preserves the finite
findings used to revise the [draft simplification extension](../plans/2026-10-15-orc-simplification-roadmap-extension.md).
It is neither an accepted design nor an implementation selection. Use the
[documentation hub](../index.md), current specs/designs and selected parent
plans for present behavior. The diagnostic probes below are reproducible local
experiments, not workflow recipes or live-provider qualification.

## Authority And Acceptance

The original review was supplied in the conversation and referenced code pin
`70f5529`; that commit does not contain the review. Its original process-probe
command and complete output were not recovered. Original observations are
reported claims until independently supported below, rather than reconstructed
execution evidence.

The follow-up inspected working files with HEAD at
`6005b5c1f105057a41a5a57882e5df90abf44118`. `git status --short` showed a broadly
dirty checkout containing changes to code, specs, designs, tests and untracked
experiment artifacts. HEAD alone therefore does not reproduce the working tree.
The process probe records the exact executor hash it inspected. These findings
need a scoped refresh when implementation is selected.

The [extension](../plans/2026-10-15-orc-simplification-roadmap-extension.md#status-evidence-and-authority)
owns proposed work and dependencies. The [evaluated-execution plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md)
and [evolution roadmap](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md)
retain their existing phase and selection authority. This report creates no new
target, manifest row, allocation or execution gate. In particular:

- Preserve useful boundary types, validation, memo history and actual public
  behavior while removing duplicate semantic ownership.
- A selected retained executable WCC boundary is complete only when all its
  admitted forms have structured values and its frontend re-entry/reverse
  routes are gone; one slice supplies the first deletion, not global closure.
- Same-population fresh regression evidence must keep pre-existing failures
  visible and introduce no new failures. A green baseline is not an entry gate.
- The parent's [Closeout, Per Phase](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#closeout-per-phase)
  requires a full suite per phase. That does not impose a full suite on every
  small extension slice; select affected coverage and preserve existing owners'
  full-suite obligations.

## WCC Boundary

Sources: [`wcc/model.py`](../../orchestrator/workflow_lisp/wcc/model.py),
[`wcc/elaborate.py`](../../orchestrator/workflow_lisp/wcc/elaborate.py),
[`closed/values.py`](../../orchestrator/workflow_lisp/closed/values.py) and
[`closed/build.py`](../../orchestrator/workflow_lisp/closed/build.py). Governing
owners are the [middle-end](../design/workflow_lisp_core_calculus_middle_end.md),
[frontend](../design/workflow_lisp_frontend_specification.md) and
[evaluated execution](../design/workflow_lisp_evaluated_execution.md) designs.

`WccOpaqueFrontendValue` remains in the `WccAtom` alias. The four constructor
sites in elaboration have different meanings; counting four sites does not
mean four admitted semantic forms or four instances of backend re-entry.

| Producer / payload | Current boundary behavior | Required disposition |
| --- | --- | --- |
| Expansion-owned pure `LetStarExpr` binding in `_elaborate_let_star` | Closed mode supplies an already normalized WCC body with `expr=None`; historical mode retains the expression | Remove the opaque wrapper for retained executable blocks while preserving lexical/capture facts; do not report this as current closed-mode re-elaboration |
| `UnionVariantTagExpr` in `_elaborate_expr_to_value` | `_opaque` emits a literal without re-entry | Use a typed literal; its type is a discriminant (`DiscriminantTypeRef`), not the union payload type |
| Grouped value-family branch in `_elaborate_expr_to_value` | Nine frontend classes described below cross inside the opaque wrapper | Give admitted retained forms structured children and direct closed translation; give excluded forms an explicit exclusion disposition |
| Pure `IfExpr` below target 2.26 in `_elaborate_if_to_value` | Historical compatibility path; targets at least 2.26 use `WccSelect` | Keep separate from the executable target-at-least-2.35 acceptance boundary |

The grouped branch contains `LoopStateSeedExpr`, `LoopStateUpdateExpr`,
`GeneratedRelpathSeedExpr`, `CompilerListNonemptyHeadExpr`, `ListExpr`,
`ListMapExpr`, `PathJoinUnderExpr`, `ProviderBundlePathExpr` and
`ResourceTransitionExpr`. The last is refused by the closed translator as a
resource-transition gap; its presence in this list does not make it admitted.
The others need family-specific evidence rather than a global assumption about
which children are pure or already normalized.

`closed.values._opaque` re-enters through `frontend_value` for loop-state
children, list items, compiler list head, list-map source, path child and retained
conditional/let children. `ListMapExpr` also uses `frontend_body`. Those helpers
call `_elaborate_expr_to_body`, normalize ANF again and prepare computed capture
requests during closed construction. Conversely, normalized blocks, variant
tags, generated relative-path literals and accepted bundle result paths have
direct cases. Preserve these distinctions when measuring deletion.

The direct callers of `frontend_value` in `closed.build` also include
computed capture materialization in `_body_impl`, bound argument facts in
`_reference_facts` and closed callee-creation values in `_callee_creation_argument`.
Their uses must be inventoried alongside
`closed.values`; eliminating only `_opaque` callers leaves re-entry behind.
The reverse `_frontend_expr_from_wcc_value` route and `_frontend_wcc_select_arm`
serve capture/substitution and conditional paths. A first family slice removes
its applicable branches and callers; final shared-helper deletion belongs to
boundary completion after the last retained caller is disposed of.

The accepted principle is to retain typed child facts and specialized callee/
capture information through elaboration, instead of reconstructing frontend
expressions or re-inferring generated children later. Validate lazy exactly-once
behavior, lexical shadowing, specialization, captures and effect/site identity.
Removing a Python union alias member is not runtime enforcement: require a
semantic walk over the executable WCC values, excluding deliberate metadata
and frozen source capsules, plus import-boundary and source-free artifact tests.
A repository-wide ban on every historical opaque constructor would expand the
scope beyond the retained executable boundary.

A fresh stdlib AST census counted direct `ast.Call` nodes whose callee is an
`ast.Name`; this does not detect aliases or prove reachability:

| File | `WccOpaqueFrontendValue` | `frontend_value` | `frontend_body` | `_frontend_expr_from_wcc_value` |
| --- | ---: | ---: | ---: | ---: |
| `wcc/elaborate.py` | 4 | 0 | 0 | 12 |
| `closed/values.py` | 0 | 11 | 1 | 0 |
| `closed/build.py` | 0 | 3 | 0 | 0 |

The 12 reverse calls include recursive calls and are not 12 external consumers.
To reproduce the census from the repository root:

```bash
python - <<'PY'
import ast
from pathlib import Path

names = ('WccOpaqueFrontendValue', 'frontend_value', 'frontend_body',
         '_frontend_expr_from_wcc_value')
for relative in ('wcc/elaborate.py', 'closed/values.py', 'closed/build.py'):
    tree = ast.parse((Path('orchestrator/workflow_lisp') / relative).read_text())
    calls = [node.func.id for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    print(relative, {name: calls.count(name) for name in names})
PY
```

## Executable Mode

`compiler._compile_stage3_graph` explicitly computes `closed_entry` from the
entry target and assigns `compiler_session.closed_program`. Merely changing a
constructor's default to `True` would leave this override and the dual-mode
plumbing intact. It can also alter historical consumers before their separation.

The mode has semantic effects: `conditionals._normalize_loop_recur_parts` selects
operand prefix order; workflow admission uses the compiler session; and
`typecheck_calls` handles closed-program union arguments differently. Other
branches occur in dispatch, structural-value, trial and context typechecking,
WCC elaboration and closed construction. `wcc/route.py` selects historical
route/schema behavior and is not itself the mode-branch owner.

Specialize the actual executable elaboration path, isolate retained historical
analysis/import/LSP consumers and delete the displaced flag plumbing and
branches. Do not substitute an immutable context wrapper or a default flip for
that deletion. Keep same-target artifact/identity checks and captured/generic
call evidence. The original recommendation to remove author-selected compiler
strategy (`:lowering inline`, `private-workflow`, `auto`) is also retained, but
needs a versioned source/identity disposition: preserve semantic checkpoints or
workflow boundaries with their semantic owners before deleting strategy syntax.

## Process Cleanup

Sources: [`ProviderInvocation`](../../orchestrator/providers/types.py),
[`ProviderExecutor`](../../orchestrator/providers/executor.py) and
[`ProviderExecutionControl`](../../orchestrator/providers/control.py).
`ProviderInvocation.terminate_process_tree` defaults to `False`; ordinary launch
sites pass it to `start_new_session`. Other profiles explicitly create sessions
and have different cleanup owners. Their guarantees cannot be treated as uniform.

`ProviderExecutor._terminate_process_tree` sends SIGTERM to the leader's PGID,
then returns as soon as `process.wait()` sees the leader exit. It reaches its
SIGKILL fallback only if that wait times out. Leader exit therefore does not
establish group emptiness or stdout EOF. Existing controlled cleanup separately
probes residual groups and bounds reader joins; preserve those stronger checks.

The original review reported a terminated leader with a SIGTERM-ignoring child
still alive and its inherited pipe open. The fresh isolated probe below
independently reproduced that helper defect. It did not exercise ordinary
public provider launch or qualify all provider profiles.

Fresh command, run from the repository root, exit 0:

```bash
python /tmp/orc-simplification-principles-20261015-gcgvubtk/process_probe.py
```

The exact source is embedded to avoid depending on that temporary path. It is
Linux-only, extracts the actual helper by AST, starts a dedicated session,
uses a subreaper to adopt the descendant and kills/reaps all owned children in
`finally`. To repeat, save this source to a scratch file and run it from the
repository root:

```python
"""Linux-only isolated probe; no provider call or repository mutation."""
import ast
import ctypes
import hashlib
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

source_path = Path('orchestrator/providers/executor.py')
source = source_path.read_text()
methods = [node for node in ast.walk(ast.parse(source))
           if isinstance(node, ast.FunctionDef) and node.name == '_terminate_process_tree']
assert len(methods) == 1
method = methods[0]
namespace = dict(os=os, signal=signal, subprocess=subprocess)
exec(compile(ast.Module(body=[method], type_ignores=[]), str(source_path), 'exec'), namespace)
# Adopt the orphan so this probe can reap it even if the host's PID 1 does not.
assert ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0
child_code = '''
import os, signal, time
if os.fork() == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    os.write(1, (str(os.getpid()) + "\\n").encode())
while True:
    time.sleep(1)
'''
process = subprocess.Popen([sys.executable, '-c', child_code],
                           start_new_session=True, stdout=subprocess.PIPE)
child_pid = None
try:
    assert select.select([process.stdout], [], [], 3)[0], 'child readiness timeout'
    child_pid = int(process.stdout.readline())
    namespace['_terminate_process_tree'](None, process)
    child_state = Path(f'/proc/{child_pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
    ready = bool(select.select([process.stdout], [], [], 0.05)[0])
    pipe_eof = ready and os.read(process.stdout.fileno(), 1) == b''
    print('head=' + subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip())
    print('executor_sha256=' + hashlib.sha256(source_path.read_bytes()).hexdigest())
    print(f'leader_returncode={process.returncode}')
    print(f'descendant_running_after_helper={child_state not in {"Z", "X"}}')
    print(f'stdout_eof_after_helper={pipe_eof}')
    assert process.returncode == -signal.SIGTERM
    assert child_state not in {'Z', 'X'} and not pipe_eof
finally:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=3)
    process.stdout.close()
    # Reap any adopted child, including when readiness setup failed.
    deadline = time.monotonic() + 3
    while True:
        try:
            adopted, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if adopted == 0:
            assert time.monotonic() < deadline, 'probe descendant did not settle'
            time.sleep(0.01)
    print('probe_cleanup=all_owned_children_reaped')
```

Captured stdout:

```text
head=6005b5c1f105057a41a5a57882e5df90abf44118
executor_sha256=e986a65e7964b188ba5b3d899d548a5a7d812f6e890a207046e82ac4c8afd316
leader_returncode=-15
descendant_running_after_helper=True
stdout_eof_after_helper=False
probe_cleanup=all_owned_children_reaped
```

A repair needs a declared session/PGID ownership policy before changing defaults,
residual-group checks after leader exit, finite TERM/KILL/drain/join deadlines
and explicit failure when cleanup cannot establish its owned boundary. A PGID
cannot guarantee cleanup of descendants that deliberately escape it. Test the
public ordinary-provider timeout/cancellation path, pipe holders and stubborn
children as well as controlled profiles; do not claim those tests ran here.
Authored timeouts and environment inheritance/whitelisting remain compatibility
choices with owners in providers/IO/security, not implied by a helper repair.

## Result Transport

The actual evaluated result path is
`machine._coerce_result` → `values.coerce_evaluated_value` →
`pure_expr.coerce_pure_value`. Output-contract parsing and
`type_descriptor.validate_transport_value` supply additional boundary semantics.
Their duplication supports consolidation after a semantic decision; it does not
make the current transport validator automatically normative for all results.
Sources: [`machine.py`](../../orchestrator/workflow/evaluated/machine.py),
[`values.py`](../../orchestrator/workflow/evaluated/values.py),
[`pure_expr.py`](../../orchestrator/workflow/pure_expr.py),
[`type_descriptor.py`](../../orchestrator/workflow/type_descriptor.py),
[`output_contract.py`](../../orchestrator/contracts/output_contract.py) and
[`Workflow Lisp contracts`](../../orchestrator/workflow_lisp/contracts.py).

The following in-memory probe was run from the repository root and exited 0:

```bash
python - <<'PY'
from orchestrator.workflow.type_descriptor import validate_transport_value
from orchestrator.workflow.pure_expr import coerce_pure_value

cases = [(1, 'Float'), (2**63, 'Int'), ('5', 'Int')]
for value, name in cases:
    descriptor = {'kind': 'primitive', 'name': name}
    for validator in (validate_transport_value, coerce_pure_value):
        try:
            result = validator(value, descriptor)
            print(f'{validator.__name__}({value!r}, {name}) -> {result!r} ({type(result).__name__})')
        except Exception as exc:
            print(f'{validator.__name__}({value!r}, {name}) -> {type(exc).__name__}: {exc}')
PY
```

Captured stdout:

```text
validate_transport_value(1, Float) -> 1.0 (float)
coerce_pure_value(1, Float) -> PureExprEvaluationError: value must be Float
validate_transport_value(9223372036854775808, Int) -> 9223372036854775808 (int)
coerce_pure_value(9223372036854775808, Int) -> PureExprEvaluationError: pure-expression integer arithmetic exceeded signed 64-bit bounds: value=9223372036854775808, minimum=-9223372036854775808, maximum=9223372036854775807
validate_transport_value('5', Int) -> _TransportValueError: $ is not an Int
coerce_pure_value('5', Int) -> PureExprEvaluationError: value must be Int
```

Thus the current structural transport validator widens integer `1` to Float and
accepts integers outside pure signed-64-bit range. Neither accepts numeric text
as an Int in this probe. Decide the chosen contract before replacing callers.
The decision must also cover Bool versus Int, finite numbers, nested collections,
Json depth/byte limits and projection, unknown record fields, typed paths and
supported target/profile boundaries. Preserve validation at trust boundaries
and separate decoding from canonical typed validation, diagnostics and lineage.

The semantic owners are [IO](../../specs/io.md),
[state](../../specs/state.md), [versioning](../../specs/versioning.md),
[provider result delivery](../design/provider_result_delivery.md) and the numeric/
transportable-value designs linked by the extension. Preserve historical memo
and committed-result meaning; do not re-decode, rewrite or revalidate historical
commits under newly selected rules. Artifact freshness remains a separate check.

## Shared Rules And Retirement

The remaining recommendations have concrete retained owners and subtraction
conditions:

| Finding / principle | Disposition and evidence needed |
| --- | --- |
| Primitive rules are duplicated beyond shared signatures, including Boolean/string/option/list operations and `_LIST_OPERATOR_NAMES` in `pure_expr.py` and frontend typechecking | Use one finite built-in catalog, delete duplicate tables/branches, preserve target admission, typed-Path restrictions, diagnostics and lazy short circuit. Independent expected vectors must exercise source compilation, artifact validation and runtime; agreement between two consumers of one table is insufficient. |
| Parallel live execution and replay repeat item/index/workspace/dependency preparation and bounds logic | Share only preparation with equivalent outputs/refusal timing. Live `parallel._items` resolves launch workspace and checks collisions; `effect_inputs.resolve_launch_cwd` uses strict filesystem resolution. Replay is read-only and must not acquire fresh disk/collision checks. Scheduling and dispatch remain caller-owned. |
| Effect inference can be the default while authored effects become optional restrictions | Reuse [EL-1](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#el-1--effect-contracts-and-analysis-cleanup-pending-unselected) and its [design](../design/workflow_lisp_effect_ledger_simplification.md). Preserve ES hand-back, owner selection/registration, target after 2.35, defining/import identities and post-specialization checking. Complete WCC is not an entry dependency. Serialize overlapping file edits or qualify the combined result. |
| Effect metadata may have duplicate analysis/propagation | Trace actual consumers and select the named EL-1d cleanup when its maintenance need is established. Its deeper internal deletion does not gate inferred-effect authoring. |
| Historical compatibility and temporary intrinsics inflate the estate | Retire finite selected consumer slices, including imports, editor analysis, artifact readers, native continuation assets and retained runs. Distinguish public source from private generated forms; version public admission changes and migrate callers before deleting syntax. |
| Confinement should be real and its guarantee explicit | Preserve the existing [run-ref environment gate](../plans/2026-10-14-run-ref-expression-environments-plan.md). Command-only child acceptance and private transport do not qualify public providers. Separately select or defer ordinary-provider confinement; if selected, bind policy to public run/resume and require denial/no-host-fallback evidence. This report does not reopen existing gates. |
| Architecture/test documentation should match the current system | Refresh after the already completed documentation cleanup, then fix remaining maintained owner/test guidance. State revision and counting method for counts. Historical sketches stay history; the README already describes the current pipeline. |
| Dynamic high-level composition may remove maintenance burden while retaining type-derived prompt/input/output contracts | Reuse the existing branch evaluation and DC-P authority, actual consumers and finite migration/deletion. No new evaluator or parallel permanent runtime is selected. Evaluate useful composition, diagnosis, quality and full task cost, with the best implemented W3 control. |

For the dynamic proposal, the user had explicitly preferred Scheme-like
composition and accepted losing static effects and resume when evaluating the
candidate's benefit. That preference persists and does not require repeat
permission. It is not main adoption or a waiver of unrelated runtime contracts.
The pinned branch `feat/orc-dynamic-core-cutover` at
`1ecde6e4566cf38a9d9f642e4e5c74e45d71b368` owns the existing
[DC-P authority](https://github.com/hoidn/agent-orchestration/blob/1ecde6e4566cf38a9d9f642e4e5c74e45d71b368/docs/plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md#dc-3-production-readiness-and-gate-dc-p).
Its bounded migration is `run-search` at 2.35→3.0, with sequential fresh-only
scope. It does not authorize main's broader typed Phase 6b migration or gate
main Phase 5/7. Reuse qualified branch evidence; repeat a study only for a named
remaining gap, with its oracle and finite allocation.

## Dispositions

All valid original recommendations are represented by the extension's
[coverage table](../plans/2026-10-15-orc-simplification-roadmap-extension.md#proposed-recommendation-coverage-and-completion):
structured WCC and child facts; reverse bridge deletion; executable-mode
specialization; authored lowering retirement; primitive-rule and pure parallel
consolidation; inferred effects and metadata cleanup; process teardown and
policy; canonical results and memo preservation; real confinement; finite
consumer/intrinsic retirement; honest documentation/verification; and dynamic
composition with measured consumer utility and cost.

The following interpretations were rejected or qualified, without dropping
those useful recommendations:

| Interpretation | Disposition |
| --- | --- |
| “39% dead code” from unimported modules | Import counts are observations, not reachability or supported-consumer proof. No percentage acceptance target. |
| Node counts refute ten semantic constructs | Structural `count_nodes` and semantic construct counts measure different things. Give the method and scope; do not interchange them. |
| Every provider has the same session, cleanup and sandbox guarantee | Profiles differ; the isolated helper defect does not qualify or condemn each profile. |
| Removing `WccOpaqueFrontendValue` from a type alias enforces closure | Python aliases are not runtime enforcement; semantic boundary and import tests are needed. |
| Flipping mode defaults completes executable specialization | The compiler overrides the flag from the target, and branches affect semantics. Delete the actual retained plumbing after consumer separation. |
| Existing transport validation can replace every coercer unchanged | Fresh numeric cases disagree. Select and version the canonical semantics first. |
| Shared parallel preparation should make replay perform live filesystem preflight | That changes read-only replay semantics; keep live resolution/collision checks with live execution. |
| The README's current pipeline has been deleted | Current README already has an execution-model description; repair only remaining stale maintained guidance. |
| E-B2 proves a calibrated zero gain / 4.9× cost architecture result | `ddb1f3ae` records its uncalibrated status. The [historical report](2026-10-15-calibrated-orc-versus-single-call.md) supplies no calibrated target or architecture verdict. |
| Full WCC completion gates EL-1, or branch DC-P gates main migration | Existing owners do not establish those dependencies. |
| Historical RED suites are a fresh baseline, or implementation needs a green ratchet | Refresh the selected population, preserve existing defects and require no new failures. |

Verification for this report consisted of current source/owner inspection,
`git rev-parse HEAD`, working-tree status, the isolated process probe supplied by
the coordinator and the in-memory transport probe above. No source behavior was
changed. No pytest suite, full orchestrator smoke run, live provider call,
confinement qualification or dynamic comparison was run as part of this report.
Those remain requirements of the implementation or selected evaluation owners,
not inferred success from this documentation revision.
