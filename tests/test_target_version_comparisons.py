"""No code outside `targets.py` compares a target with a version, beyond the sites listed here.

The list holds today's target gates, wire values and the version helpers that read them: per file,
each matching line, stripped. A new or rewritten site fails, so swapping one gate for another in the
same file fails too. "Only shrink" is a review rule, not something the test can enforce: the list
can grow by editing it, and a new gate belongs in `orchestrator/contracts/closed_program/targets.py`
(Lane D stage 4 plan, R13). The pattern catches written comparisons, not every possible one.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = "orchestrator/contracts/closed_program/targets.py"

# The two admission sets (source, readable program labels) and the current-target name are admission, not gates;
# every other match counts.
COMPARISON = re.compile(
    r"""["']2\.\d\d["']"""  # a version literal, alone, in a set or as a getattr default
    r"|\(\s*2\s*,\s*\d\d\s*\)"  # a version tuple
    r"""|\w*(?:target|version)\w*\.(?:split|partition|rpartition)\(\s*["']\.["']"""  # parts of a dotted target
    r"""|\w*(?:target|version)\w*\.startswith\(\s*["']2\."""  # a prefix test
    r"|\bfloat\(\s*\w*(?:target|version)"  # a target read as a number
    r"|\bVersion\s*\("  # a parsed version object
    r"|\b(?!SUPPORTED_TARGET_DSL_VERSIONS\b|READABLE_PROGRAM_TARGET_DSL_VERSIONS\b|CURRENT_TARGET_DSL_VERSION\b)[A-Z_]*TARGET_DSL_VERSIONS?\b"  # a named version
    r"|\btarget_dsl_(?:supports_\w+|uses_evaluated_execution|version_at_least)\s*\("  # a target predicate
    r"|\b_available_at_target\s*\("  # the registry's own gate
    r"|\b(?:get_form_spec|registered_form_heads)\s*\(.*\btarget_dsl_version\s*=\s*(?!None\b)"  # a registry gate
    r"""|\bmin_target_dsl_version\s*=\s*["']"""  # a registry row's minimum
)

# Row numbers are those of the stage 4 plan's difference table ("Where behavior depends on the target").
ALLOWED = {
    "orchestrator/contracts/closed_program/check.py": (  # 2, 4, 10, 14 (checker label gates, R14)
        'or not target_dsl_uses_evaluated_execution(target)):',
        'if not target_dsl_supports_parallel_map(self.tree["target"]):',
        'if self.tree["target"] not in {"2.39", "2.40"}:',
        'elif config.target_dsl_version != PATH_MODE_RUN_REF_TARGET_DSL_VERSION or config.program.__class__.__name__ != "PathProgram":',
    ),
    "orchestrator/contracts/closed_program/check_agents.py": (  # 5 (checker label gates, R14)
        'if (not target_dsl_supports_agent_sessions(checker.tree.get("target", ""))',
        'if not target_dsl_supports_agent_sessions(checker.tree.get("target", "")):',
    ),
    "orchestrator/contracts/closed_program/check_host_input.py": (  # 11 (checker label gate)
        "if checker.tree['target'] != '2.40':",
    ),
    "orchestrator/prompt_scaffold_render.py": (  # 14
        '\'  (:target-dsl "2.27")\',',
    ),
    "orchestrator/workflow/prompting.py": (  # 15
        'int(part) for part in target_dsl_version.split(".")',
        'return parts >= (2, 22)',
    ),
    "orchestrator/workflow/provider_phased_delivery/ledger.py": (  # 14
        '"target_dsl": "2.23",',
        'or row["target_dsl"] != "2.23"',
    ),
    "orchestrator/workflow/run_ref/config.py": (  # 14 (stored and built config bytes, R12)
        '_DEFAULT_TARGET_DSL_VERSION = "2.35"',
        '_SUPPORTED_TARGET_DSL_VERSIONS = frozenset({"2.35", "2.36", "2.37", "2.38", "2.39", "2.40"})',
        'target_dsl_version: str = _DEFAULT_TARGET_DSL_VERSION,',
        'or target_dsl_version not in _SUPPORTED_TARGET_DSL_VERSIONS',
        'or row["target_dsl_version"] not in _SUPPORTED_TARGET_DSL_VERSIONS',
    ),
    "orchestrator/workflow/run_ref/confined_config.py": (  # 6
        'if type(target_dsl_version) is not str or not target_dsl_supports_run_ref_confined(target_dsl_version):',
    ),
    "orchestrator/workflow/run_ref/path_contracts.py": (  # 2
        'if type(program) is not ClosedProgram or not target_dsl_uses_evaluated_execution(program.tree["target"]):',
    ),
    "orchestrator/workflow/run_ref/wire.py": (  # 2
        'or not target_dsl_uses_evaluated_execution(',
        '+ EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION',
    ),
    "orchestrator/workflow_lisp/closed/__init__.py": (  # 2 (re-export of the floor)
        '__all__ = ["EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION"]',
    ),
    "orchestrator/workflow_lisp/closed/build.py": (  # 14
        'target_dsl_version=PATH_MODE_RUN_REF_TARGET_DSL_VERSION,',
    ),
    "orchestrator/workflow_lisp/closed/target.py": (  # 2
        'major, minor = (int(part) for part in target.split("."))',
    ),
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
    found = {}
    for path in sorted((ROOT / "orchestrator").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if rel != TARGETS and (numbers := comparison_lines(text)):
            found[rel] = tuple(text.splitlines()[n - 1].strip() for n in numbers)

    assert found == ALLOWED, (
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
        "i = float(target_dsl_version) >= 2.39",
        "j = target_dsl_version.split('.', 1)",
        "k = int(target_dsl_version.partition('.')[2]) >= 39",
        "l = target_dsl_version.startswith('2.3')",
        "m = _available_at_target(spec, target_dsl_version)",
        "n = Version(t) >= Version(MIN)",
        "o = get_form_spec(head, target_dsl_version=target)",
        "p = registered_form_heads(target_dsl_version=None)",
        "q = target.startswith('/')",
    ))

    assert comparison_lines(planted) == [1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 15]
