"""No code outside `targets.py` compares a target with a version, beyond the sites listed here.

The list holds today's target gates, wire values and the version helpers that read them, one entry
per file with its count of matching lines. It may only shrink: a new gate belongs in
`orchestrator/contracts/closed_program/targets.py`, and a removed site removes its entry
(Lane D stage 4 plan, R13).
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = "orchestrator/contracts/closed_program/targets.py"

# The admission set and the current-target name are admission, not gates; every other match counts.
COMPARISON = re.compile(
    r"""["']2\.\d\d["']"""  # a version literal, alone, in a set or as a getattr default
    r"|\(\s*2\s*,\s*\d\d\s*\)"  # a version tuple
    r"""|\w*(?:target|version)\w*\.split\(\s*["']\.["']\s*\)"""  # a tuple built from a dotted target
    r"|\b(?!SUPPORTED_TARGET_DSL_VERSIONS\b|CURRENT_TARGET_DSL_VERSION\b)[A-Z_]*TARGET_DSL_VERSIONS?\b"  # a named version
    r"|\btarget_dsl_(?:supports_\w+|uses_evaluated_execution|version_at_least)\s*\("  # a target predicate
    r"""|\bmin_target_dsl_version\s*=\s*["']"""  # a registry row's minimum
)

# Row numbers are those of the stage 4 plan's difference table ("Where behavior depends on the target").
ALLOWED = {
    "orchestrator/cli/commands/repl.py": 1,  # 7
    "orchestrator/contracts/closed_program/check.py": 4,  # 2, 4, 10, 14 (checker label gates, R14)
    "orchestrator/contracts/closed_program/check_agents.py": 2,  # 5 (checker label gates, R14)
    "orchestrator/contracts/closed_program/check_host_input.py": 1,  # 11 (checker label gate)
    "orchestrator/lsp/navigation.py": 3,  # 7, 8
    "orchestrator/prompt_scaffold_render.py": 1,  # 14
    "orchestrator/py/emit.py": 5,  # 7, 11, 12
    "orchestrator/py/trace.py": 2,  # 11, 12
    "orchestrator/workflow/prompting.py": 2,  # 15
    "orchestrator/workflow/provider_phased_delivery/ledger.py": 2,  # 14
    "orchestrator/workflow/run_ref/config.py": 5,  # 14 (stored and built config bytes, R12)
    "orchestrator/workflow/run_ref/confined_config.py": 1,  # 6
    "orchestrator/workflow/run_ref/path_contracts.py": 1,  # 2
    "orchestrator/workflow/run_ref/wire.py": 2,  # 2
    "orchestrator/workflow_lisp/agent_forms.py": 2,  # 5
    "orchestrator/workflow_lisp/closed/__init__.py": 1,  # 2 (re-export of the floor)
    "orchestrator/workflow_lisp/closed/build.py": 1,  # 14
    "orchestrator/workflow_lisp/closed/effects.py": 1,  # 10
    "orchestrator/workflow_lisp/closed/target.py": 3,  # 2
    "orchestrator/workflow_lisp/compiler.py": 6,  # 3, 7, 9
    "orchestrator/workflow_lisp/expressions.py": 6,  # 3, 6, 8, 11
    "orchestrator/workflow_lisp/form_registry.py": 4,  # 5, 8 (and the minimum check itself)
    "orchestrator/workflow_lisp/functions.py": 3,  # 7
    "orchestrator/workflow_lisp/modules.py": 1,  # 3
    "orchestrator/workflow_lisp/parallel_map.py": 1,  # 4
    "orchestrator/workflow_lisp/procedure_specialization.py": 7,  # 3, 7
    "orchestrator/workflow_lisp/procedure_typecheck.py": 13,  # 3, 7
    "orchestrator/workflow_lisp/procedures.py": 3,  # 7
    "orchestrator/workflow_lisp/repl_expr.py": 2,  # 3, 7
    "orchestrator/workflow_lisp/repl_inspect.py": 1,  # 7
    "orchestrator/workflow_lisp/syntax.py": 1,  # 3
    "orchestrator/workflow_lisp/type_env.py": 2,  # 5
    "orchestrator/workflow_lisp/typecheck_effects.py": 2,  # 10, 11
    "orchestrator/workflow_lisp/workflows.py": 1,  # 3
}


def comparison_lines(text: str) -> list[int]:
    """Line numbers of `text` that compare a target with a version, imports and `def` lines excepted."""

    skip: set[int] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            skip.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            skip.add(node.lineno)
    return [n for n, line in enumerate(text.splitlines(), 1) if n not in skip and COMPARISON.search(line)]


def test_target_comparisons_stay_in_targets_or_on_the_shrinking_list() -> None:
    found = Counter()
    for path in sorted((ROOT / "orchestrator").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel != TARGETS and (count := len(comparison_lines(path.read_text(encoding="utf-8")))):
            found[rel] = count

    assert dict(found) == ALLOWED, (
        "a target is compared with a version outside targets.py: add a predicate there, "
        "or shrink ALLOWED when a site goes"
    )


def test_the_pattern_sees_each_comparison_shape() -> None:
    planted = "\n".join((
        'a = str(getattr(module, "TARGET", "2.39"))',
        'b = target not in {"2.39", "2.40"}',
        "c = tuple(map(int, target_dsl_version.split('.'))) >= (2, 36)",
        "d = target >= PARALLEL_MAP_MIN_TARGET_DSL_VERSION",
        "e = syntax.target_dsl_supports_effect_ceilings(target)",
        'f = spec(min_target_dsl_version="2.38")',
        "g = target in SUPPORTED_TARGET_DSL_VERSIONS",
        "h = path.split('.')",
    ))

    assert comparison_lines(planted) == [1, 2, 3, 4, 5, 6]
