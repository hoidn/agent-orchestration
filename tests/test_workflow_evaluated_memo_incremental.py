"""Continuing a reduction from the process's last fold equals reducing the bytes from scratch."""

from __future__ import annotations

import pytest

from orchestrator.workflow.evaluated import memo_reducer
from orchestrator.workflow.evaluated.memo_reducer import MemoError, reduce_memo
from tests.test_workflow_evaluated_memo import FETCH, SITES, _committed, _line, _row, _started


def _fresh(raw: bytes, sites=SITES):
    return memo_reducer._Reducer(sites).reduce(raw)


def _journal() -> list[bytes]:
    lines = [_line(_started(FETCH, 1)), _line(_started(FETCH, 2)), _line(_committed(FETCH, 2))]
    anchor = len(b"".join(lines[:2]))
    lines += [_line(_row("invalidated", from_commit=anchor, time=3.0)), _line(_started(FETCH, 3)),
              _line(_committed(FETCH, 3)), _line(_row("terminal", outcome="completed", value=1))]
    return lines


def _prefixes() -> list[bytes]:
    """Growth record by record, repeats, torn tails, a memo replaced by other bytes, and truncations."""
    lines = _journal()
    grown = [b"".join(lines[:count]) for count in range(len(lines) + 1)]
    torn = [grown[3] + lines[3][:7], grown[4], grown[5] + lines[5][:-1], grown[6]]
    replaced = [_line(_started(FETCH, 1)).replace(b'"time":1.0', b'"time":9.0')]
    return [*grown, grown[7], *torn, grown[3], replaced[0], grown[2], grown[7], grown[1], grown[7], grown[7]]


def test_every_reduction_in_sequence_equals_a_fresh_reduction():
    memo_reducer._LAST = None
    for raw in _prefixes():
        assert reduce_memo(raw, SITES) == _fresh(raw)


def test_a_different_site_table_never_continues_a_cached_fold():
    lines = _journal()
    reduce_memo(b"".join(lines[:2]), SITES)
    other = {FETCH: "provider"}
    with pytest.raises(MemoError) as cached:
        reduce_memo(b"".join(lines[:3]), other)
    with pytest.raises(MemoError) as fresh:
        _fresh(b"".join(lines[:3]), other)
    assert str(cached.value) == str(fresh.value)


@pytest.mark.parametrize("bad", [b"{not json}\n", _line(_committed(FETCH, 1)), _line(_started(FETCH, 2))])
def test_a_refused_continuation_raises_exactly_what_a_fresh_reduction_raises(bad):
    prefix = b"".join(_journal()[:3])
    reduce_memo(prefix, SITES)
    with pytest.raises(MemoError) as cached:
        reduce_memo(prefix + bad, SITES)
    with pytest.raises(MemoError) as fresh:
        _fresh(prefix + bad)
    assert (cached.value.code, str(cached.value)) == (fresh.value.code, str(fresh.value))
    assert reduce_memo(prefix, SITES) == _fresh(prefix)


def test_the_saved_fold_covers_every_reducer_state_field():
    names = set(vars(memo_reducer._Reducer(SITES)))
    assert names - {"site_classes", "terminal"} == set(memo_reducer._STATE)
