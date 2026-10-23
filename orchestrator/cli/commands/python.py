"""Thin trusted-Python import/build adaptation to the ordinary CLI runtime."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import sys
from types import ModuleType

from orchestrator.py import build
from orchestrator.py.trace import Declaration
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, render_diagnostic

logger = logging.getLogger(__name__)


def load_workflow(path, entry=None):
    path = Path(os.path.abspath(path))
    if path.suffix != '.py': raise ValueError('Python authoring requires a .py source file')
    name = '_orchestrator_author_' + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    previous = list(sys.path)
    sys.path.insert(0, str(path.parent))
    try:
        # Read current source directly: timestamp-based pyc reuse is not build identity.
        exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    finally:
        sys.path[:] = previous
    exports = {name: value for name, value in vars(module).items()
               if isinstance(value, Declaration) and value.kind == 'workflow' and value.__module__ == module.__name__}
    if entry is not None:
        if entry not in exports: raise ValueError(f'no exported Python workflow {entry!r}')
        return exports[entry]
    unique = list(dict.fromkeys(exports.values()))
    if len(unique) != 1: raise ValueError('select --entry-workflow unless exactly one workflow is exported')
    return unique[0]


def python_workflow(args):
    try:
        if getattr(args, 'imported_workflow_bundles_file', None):
            raise ValueError('imported workflow bundles are outside the bounded Python authoring surface')
        workflow = load_workflow(args.workflow, args.entry_workflow)
        built = build(workflow, provider_externs_file=args.provider_externs_file,
            prompt_externs_file=args.prompt_externs_file, command_boundaries_file=args.command_boundaries_file,
            source_roots=args.source_root or ())
        if args.py_command == 'run':
            from .run import run_workflow
            adapted = type(args)(**vars(args))
            adapted.workflow = str(built.source_path)
            adapted.source_root = [str(path) for path in built.request.source_roots]
            adapted.entry_workflow = built.request.entry_workflow
            return run_workflow(adapted).exit_code
        print(json.dumps({'source_path': str(built.source_path), 'source_map_path': str(built.source_map_path),
            'provider_externs_file': args.provider_externs_file, 'prompt_externs_file': args.prompt_externs_file,
            'command_boundaries_file': args.command_boundaries_file, 'entry_workflow': built.closed_result.entry_workflow,
            'build_key': built.closed_result.build_key, 'program_digest': built.closed_result.program.digest}, sort_keys=True))
        return 0
    except LispFrontendCompileError as exc:
        for diagnostic in exc.diagnostics: logger.error(render_diagnostic(diagnostic))
    except Exception as exc:
        logger.error('%s: %s', args.workflow, exc)
    return 2
