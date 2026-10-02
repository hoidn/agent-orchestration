# Dynamic composition with existing boundary contracts

This is an isolated experiment, not a public `.orc` target. The
[composition source](fixtures/composition.orc) uses the existing reader and the
same checked dynamic artifact/evaluator as the pure experiment. The
[typed leaves](fixtures/leaf.orc) keep the existing compiler, `defprompt`,
document delivery and structured-output validation.

## What changes for the author

The existing [`std/improve`](../../orchestrator/workflow_lisp/stdlib_modules/std/improve.orc)
passes its explicit `inputs I` argument to `ProcRef` hooks. Its
[caller fixtures](../../tests/workflow_lisp_improve_stdlib_sources.py) pass
`proc-ref` values and context separately. These excerpts compare **callback
wiring only**; the experimental specimen is not a port of improve's loop,
approval/blocked/exhaustion policy or recovery behavior.

```lisp
; Existing typed helper interface/body excerpts:
(review ProcRef[(S I) -> Decision[F B]])
(revise ProcRef[(S I F) -> S])
; ... with inputs : I carried through the helper:
(review state.current inputs)
(revise state.current inputs r.feedback)

; Existing caller wiring:
(proc-ref review-candidate)
(proc-ref revise-candidate)
; Context is supplied separately to improve, then to each hook.
```

The experimental composition uses ordinary function values:

```lisp
(define (apply-one callback value) (callback value))

(define (make-annotator goal rubric)
  (fn (reviewed)
    (fn (candidate)
      (effect annotate
        (record
          (feedback
            (string/concat goal " | " rubric " | "
              (field reviewed "return__feedback") " | "
              (field candidate "title"))))))))

; After review has returned through its declared contract:
(let* ((next (if (field reviewed "return__approved")
               (fn (candidate) candidate)
               ((make-annotator goal rubric) reviewed)))
       (callbacks (record (next next))))
  (apply-one (field callbacks "next") seed))
```

`make-annotator` returns a function that receives the review, which returns a
function that receives the candidate. The innermost function retains `goal`,
`rubric` and `reviewed`; `apply-one` receives only the callback and candidate.
The compiler infers the captures. A validated review chooses the callback,
which is stored in a record and passed to an ordinary helper before invocation.

There are no helper type parameters, `ProcRef` signatures, capture lists or
context carrier declarations in that composition. The checked-in specimen also
calls the same `identity` body with an integer and a record. An ordinary wrong
call arity fails only if reached; an unbound lexical name still fails when
compiling. The typed route already permits a single String context without a
record, and proposed W3 would also remove explicit capture forwarding; neither
is a unique dynamic-core gain.

The `return__…` names are the existing compiled leaf's wire fields. They are an
explicit limitation of this adapter, not proposed final user-facing names.
Public inputs/results still declare schemas; this specimen deliberately uses
`Value` for its alternative final shapes. Real leaf inputs and outputs retain
more precise contracts, including nested records/unions and document paths.

## Run the complete example

From the repository/worktree root, use the following command. It creates a
fresh temporary workspace and invokes a registered local Python provider plus
a command through the real workflow executor. It makes no paid model calls.
The provider requests revision for the `reject draft` input, so both operations
execute. The JSON artifact is written to disk and read back before execution.

```bash
python - <<'PY'
from pathlib import Path
import json, os, shutil, sys, tempfile
from orchestrator.providers.types import InputMode, ProviderTemplate
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from experiments.dynamic_core_evaluation.leaf_bridge import LeafBridge
from experiments.dynamic_core_evaluation.source import compile_source
from experiments.dynamic_core_evaluation.program import DynamicProgram
from experiments.dynamic_core_evaluation.evaluator import evaluate

workspace = Path(tempfile.mkdtemp(prefix='orc-dynamic-source-'))
fixture = Path('experiments/dynamic_core_evaluation/fixtures')
shutil.copytree(fixture, workspace / fixture)
(workspace / 'docs').mkdir()
(workspace / 'docs/goal.txt').write_text('DOC_A: Keep the boundary contracts strict.\n')
log = workspace / 'dispatch.jsonl'
os.environ['DYNAMIC_CORE_DISPATCH_LOG'] = str(log)
provider = ProviderTemplate(name='dynamic-fixture',
    command=[sys.executable, str(workspace / fixture / 'scripted_leaf.py'), 'provider'],
    input_mode=InputMode.STDIN)
bridge = LeafBridge.compile(workspace / fixture / 'leaf.orc', workspace,
    operations={'review': 'leaf::review', 'annotate': 'leaf::annotate'},
    provider_externs={'providers.review': 'dynamic-fixture'},
    command_boundaries={'annotate': ExternalToolBinding(name='annotate',
        stable_command=('python', str(fixture / 'scripted_leaf.py'), 'command'))},
    provider_templates=(provider,))
program = compile_source((fixture / 'composition.orc').read_text(),
    source_path=str(fixture / 'composition.orc'), type_env=bridge.type_env)
artifact = workspace / 'program.json'
artifact.write_text(program.artifact())
result = evaluate(DynamicProgram.from_artifact(artifact.read_text()),
    {'goal': 'reject draft', 'rubric': 'clarity', 'target_doc': 'docs/goal.txt'}, leaf_bridge=bridge)
print(json.dumps({'workspace': str(workspace), 'value': result.json_value(),
                  'steps': result.steps, 'digest': program.digest,
                  'dispatches': [json.loads(line)['mode'] for line in log.read_text().splitlines()]}, indent=2))
PY
```

The final JSON includes the temporary workspace, admitted artifact digest,
node count, `provider` then `command` dispatches, and validated output. The
annotation's feedback includes the captured goal/rubric and review feedback.
Run with another goal that does not contain `reject` to take the approval
branch: it returns the draft and does not invoke the annotation command.

## Limits and checks

Each effect launches a fresh legacy leaf run, retaining its state, compiler
machinery and startup cost. Restarting the composition repeats earlier effects;
there is no candidate resume or static effect tracking. Required-output/path
checks are retained where declared; ordinary output files are not rolled back
and their presence does not prove freshness. Runtime diagnostics currently use
artifact positions rather than complete source maps.

This bounded grammar has no imports, macros, mutation or public launch route.
It demonstrates source composition and boundary reuse; full improve/MLEvolve
utility, net deletions and production adoption remain separate decisions in the
[evaluation plan](../../docs/plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md).

```bash
python -m pytest -q tests/experiments/test_dynamic_core_source.py
```
