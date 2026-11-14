"""digests.py OUT.json: the corpus snapshot. For every exported workflow of the corpus roots of the tree on
`PYTHONPATH` (`tests/workflow_lisp_closed_program_corpus.py`), its program digest, or the outcome that stopped it."""
import json, sys, tempfile
from pathlib import Path
from tests.workflow_lisp_closed_program_corpus import Built, corpus, try_build
out = {}
with tempfile.TemporaryDirectory() as scratch:
    for i, workflow in enumerate(corpus()):
        result = try_build(workflow, Path(scratch) / str(i))
        if isinstance(result.outcome, Built):
            out[workflow.key] = result.program.digest
        else:
            out[workflow.key] = f"{type(result.outcome).__name__}:{getattr(result.diagnostic, 'code', None)}"
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, sort_keys=True))
print(len(out), "rows;", sum(1 for v in out.values() if v.startswith("sha256")), "built")
