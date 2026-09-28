"""Route exhausted `loop/recur` union results to loop-frame state (target 2.33+).

The runtime publishes `repeat_until.on_exhausted.outputs` verbatim, so a
compiler-emitted `{"ref": ...}` there is never dereferenced. Targets below 2.29
therefore point the exhausted variant's result case straight at the loop-frame
state artifact. Target 2.29 stopped doing that, because a `done` that returns
the same variant must publish its own payload rather than the state. From
target 2.33 the direct state read is used again whenever no `done` in the body
can produce the exhausted variant, which is the shape of a bounded
improvement loop whose exhaustion variant is only ever built by
`:on-exhausted`. Targets 2.29-2.32 keep their current lowering.
"""

from __future__ import annotations

from ..expression_traversal import walk_expr
from ..expressions import DoneExpr, LoopRecurExpr, UnionVariantExpr
from ..syntax import target_dsl_supports_generic_unions, target_dsl_supports_rich_loop_values


def exhaustion_state_ref_allowed(
    loop_expr: LoopRecurExpr,
    *,
    variant_name: str,
    target_dsl_version: str,
) -> bool:
    """Return whether the result case for `variant_name` may read exhaustion state."""

    if not target_dsl_supports_rich_loop_values(target_dsl_version):
        return True
    if not target_dsl_supports_generic_unions(target_dsl_version):
        return False
    done_variants = _done_variant_names(loop_expr)
    return done_variants is not None and variant_name not in done_variants


def _done_variant_names(loop_expr: LoopRecurExpr) -> frozenset[str] | None:
    """Variant names `done` can return, or None when one `done` is not a literal."""

    names: set[str] = set()
    for node in walk_expr(loop_expr.body_expr):
        if not isinstance(node, DoneExpr):
            continue
        if not isinstance(node.result_expr, UnionVariantExpr):
            return None
        names.add(node.result_expr.variant_name)
    return frozenset(names)
