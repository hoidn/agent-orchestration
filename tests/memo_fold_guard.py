"""Test-only guards for the evaluated runtime's two shared-state fast paths.

``FoldGuard``: ``memo_reducer`` keeps the process's last fold and later snapshots share its
row dicts, so a consumer that edits a row in place would corrupt every later read of that
memo. The guard records each fold that becomes the cache and is not continued afterwards
(the tip of each memo's lineage; earlier folds share the tip's rows) and, at test
teardown, requires each tip to equal a fresh reduction of its own bytes. One fresh
reduction per memo lineage per test, never one per reduction.

``StartViewGuard``: for a ``started`` row published with ``start_reached`` (no replay),
recompute the view with the replay and require the bytes just published.
"""

from __future__ import annotations

import json


class FoldGuard:
    def __init__(self, monkeypatch):
        from orchestrator.workflow.evaluated import memo_reducer

        self.memo_reducer = memo_reducer
        self.tips: dict[int, tuple[object, bytes]] = {}
        memo_reducer._LAST = None
        resume = memo_reducer._resume_cached_prefix

        def recording_resume(reducer, raw):
            cached = memo_reducer._LAST
            start = resume(reducer, raw)
            if cached is not None:
                if start:
                    self.tips.pop(id(cached[0]), None)
                else:
                    self.tips[id(cached[0])] = cached
            return start

        monkeypatch.setattr(memo_reducer, "_resume_cached_prefix", recording_resume)

    def check(self, nodeid: str) -> None:
        last = self.memo_reducer._LAST
        if last is not None:
            self.tips[id(last[0])] = last
        for reducer, raw in self.tips.values():
            fresh = self.memo_reducer._Reducer(reducer.site_classes).reduce(raw)
            for cached, entry in zip(reducer.entries, fresh.entries):
                assert cached == entry, (
                    f"{nodeid} left the memo fold inconsistent: the cached row at byte {entry.offset} is "
                    f"{json.dumps(cached.data, sort_keys=True)} but the journal holds "
                    f"{json.dumps(entry.data, sort_keys=True)}; a consumer edited a reduced row in place")
            assert len(reducer.entries) == len(fresh.entries)
        self.memo_reducer._LAST = None


def install_start_view_guard(monkeypatch) -> None:
    from orchestrator.workflow.evaluated import views
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import reduce_memo

    publish = views.publish_evaluated_view

    def checked_publish(authority, entry, **kwargs):
        publish(authority, entry, **kwargs)
        if not kwargs.get("start_reached"):
            return
        files = authority.run_files
        snapshot = reduce_memo(files.read(views.MEMO_FILENAME)[:entry.end], site_classes(authority.program))
        value, next_effect, halted = views._replay(authority, snapshot)
        terminal = views._checked_terminal(snapshot, value, halted)
        view = views._view(authority, snapshot, terminal, next_effect, halted, True)
        replayed = json.dumps(view, ensure_ascii=False, allow_nan=False).encode() + b"\n"
        assert files.read("state.json") == replayed, f"view of started row at byte {entry.offset} differs from its replay"

    monkeypatch.setattr(views, "publish_evaluated_view", checked_publish)
