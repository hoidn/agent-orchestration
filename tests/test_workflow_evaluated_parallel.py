"""Public evaluated execution keeps parallel effects bounded and durable."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading

import pytest

from orchestrator.workflow.evaluated import attempts, effect_execution, run_ref, runtime, views
from orchestrator.workflow.evaluated.commands import CommandPerformerError
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.evaluated.views import ViewPublicationError
from tests.test_workflow_evaluated_command_lifecycle import _publish
from tests.workflow_evaluated_parallel_helpers import COMMAND, replay_case, mapped, worker, site_index, effect
from tests.workflow_lisp_closed_program_helpers import build


def _install_launcher(monkeypatch, outcome, calls):
    def launch(node, argv, *, attempt_files, launch_cwd=None, **_kwargs):
        cwd = Path(launch_cwd)
        event = {
            "item": cwd.parent.name,
            "boundary": node["boundary"],
            "argv": tuple(argv),
            "cwd": cwd,
        }
        calls.append(event)
        value = outcome(event)
        attempt_files.create("result.json", str(value).encode(), exclusive=True)
        return str(attempt_files.workspace / "result.json")

    monkeypatch.setattr(effect_execution, "launch_command", launch)


def _track_publishers(monkeypatch):
    rows, row_threads, view_threads, allocation_threads = [], [], [], []

    def wrap_append(original):
        def append(path, record, **kwargs):
            rows.append(dict(record))
            row_threads.append(threading.get_ident())
            return original(path, record, **kwargs)

        return append

    for module in (runtime, attempts, run_ref):
        monkeypatch.setattr(module, "append_record", wrap_append(module.append_record))

    allocate = runtime.allocate_attempt

    def observed_allocate(*args, **kwargs):
        allocation_threads.append(threading.get_ident())
        return allocate(*args, **kwargs)

    monkeypatch.setattr(runtime, "allocate_attempt", observed_allocate)
    publish = views.publish_evaluated_view

    def observed_publish(*args, **kwargs):
        view_threads.append(threading.get_ident())
        return publish(*args, **kwargs)

    monkeypatch.setattr(views, "publish_evaluated_view", observed_publish)
    return rows, row_threads, view_threads, allocation_threads


def _wait(event):
    assert event.wait(5), "parallel worker did not reach its barrier"


def _async_run(authority, workspace):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(runtime.execute_pure_run, authority, {}, run_id="run-1", workspace=workspace)
    return executor, future


def _release_all(events):
    for event in events.values():
        event.set()


def _assert_input_ordered_run(authority, workspace, finished, maximum, calls):
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    commits = [row.data for row in snapshot.entries if row.data["record"] == "committed"]
    assert maximum == 2
    assert finished == ["b", "c", "d", "a"]
    assert [row["identity"] for row in commits] == [
        effect(authority, index)[0] for index in (1, 2, 3, 0)
    ]
    assert [row["value"] for row in commits] == [1, 2, 3, 0]
    assert {event["cwd"] for event in calls} == {workspace / item / "work" for item in "abcd"}


def test_public_run_bounds_overlap_and_returns_input_order_after_later_items_finish(
    tmp_path, monkeypatch
):
    calls, finished = [], []
    both_active = threading.Event()
    first_pair = threading.Barrier(2)
    releases = {item: threading.Event() for item in "abcd"}
    starts = {item: threading.Event() for item in "cd"}
    active = maximum = 0
    lock = threading.Lock()

    def outcome(event):
        nonlocal active, maximum
        item = event["item"]
        with lock:
            active += 1
            maximum = max(maximum, active)
            if item in "ab" and active == 2:
                both_active.set()
        try:
            if item in "ab":
                first_pair.wait(timeout=5)
            else:
                starts[item].set()
            _wait(releases[item])
            finished.append(item)
            return ord(item) - ord("a")
        finally:
            with lock:
                active -= 1

    _install_launcher(monkeypatch, outcome, calls)
    with replay_case(tmp_path) as authority:
        append = runtime.append_record
        d_committed = threading.Event()

        def observe_d_commit(path, record, **kwargs):
            entry = append(path, record, **kwargs)
            if record.get("record") == "committed" and record.get("identity") == effect(authority, 3)[0]:
                d_committed.set()
            return entry

        monkeypatch.setattr(runtime, "append_record", observe_d_commit)
        executor, future = _async_run(authority, tmp_path)
        try:
            _wait(both_active)
            releases["b"].set()
            _wait(starts["c"])
            releases["c"].set()
            _wait(starts["d"])
            releases["d"].set()
            _wait(d_committed)
            releases["a"].set()
            assert future.result(timeout=5) == (0, [0, 1, 2, 3])
        finally:
            _release_all(releases)
            executor.shutdown(wait=True)

        _assert_input_ordered_run(authority, tmp_path, finished, maximum, calls)

        monkeypatch.setattr(effect_execution, "launch_command", lambda *_a, **_k: pytest.fail("replayed effect"))
        assert runtime.execute_pure_resume(authority, {}, run_id="run-1", workspace=tmp_path) == (
            0,
            [0, 1, 2, 3],
        )


def _assert_sequential_dependencies(authority, calls):
    per_item_order = {
        item: [event["boundary"] for event in calls if event["item"] == item]
        for item in "abcd"
    }
    assert per_item_order == {item: ["fetch", "inc"] for item in "abcd"}
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    commits = [row.data for row in snapshot.entries if row.data["record"] == "committed"]
    by_identity = {row["identity"]: row for row in commits}
    fetch = site_index(authority, boundary="fetch")
    inc = site_index(authority, boundary="inc")
    for index in range(4):
        first_identity = effect(authority, index, site=fetch)[0]
        second = by_identity[effect(authority, index, site=inc)[0]]
        assert by_identity[first_identity]["depends_on"] == []
        assert second["depends_on"] == [first_identity]


def test_public_run_keeps_each_item_sequential_and_records_exact_dependencies(tmp_path, monkeypatch):
    calls = []
    body = f'''(let* ((first {COMMAND})
        (second (command-result inc :argv ("python" "probe.py" first) :returns Int))) second)'''

    def outcome(event):
        item_index = ord(event["item"]) - ord("a")
        return item_index + (10 if event["boundary"] == "inc" else 0)

    _install_launcher(monkeypatch, outcome, calls)
    with replay_case(tmp_path, mapped("(call worker :repo repo)"), declarations=worker(body)) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (
            0,
            [10, 11, 12, 13],
        )
        _assert_sequential_dependencies(authority, calls)


def test_public_run_handles_typed_empty_map_input_without_dispatch(tmp_path, monkeypatch):
    calls = []
    _install_launcher(monkeypatch, lambda _event: pytest.fail("empty map dispatched"), calls)
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
        (defmodule empty_parallel) (export run)
        (defworkflow run ((repos List[String])) -> List[Int] {mapped(source="repos")}))'''
    program = build(tmp_path, source)
    with _publish(tmp_path, program, inputs={"repos": []}) as authority:
        assert runtime.execute_pure_run(authority, {"repos": []}, run_id="run-1", workspace=tmp_path) == (
            0,
            [],
        )
        snapshot = read_memo(authority.memo_path, site_classes(authority.program))
        assert [row.data["record"] for row in snapshot.entries] == ["terminal"]
        assert calls == []


def test_public_run_with_single_worker_map(tmp_path, monkeypatch):
    calls, active = [], 0
    maximum = 0
    lock = threading.Lock()

    def outcome(event):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        try:
            return ord(event["item"]) - ord("a")
        finally:
            with lock:
                active -= 1

    _install_launcher(monkeypatch, outcome, calls)
    with replay_case(tmp_path, mapped().replace(":parallel 2", ":parallel 1")) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (
            0,
            [0, 1, 2, 3],
        )
        snapshot = read_memo(authority.memo_path, site_classes(authority.program))
        assert len([row for row in snapshot.entries if row.data["record"] == "started"]) == 4
        assert maximum == 1


@pytest.mark.parametrize(
    "body",
    [
        mapped().replace(":max 4", ":max 3"),
        mapped(source='(list "a" "a/../a")'),
    ],
    ids=["cap-before-dispatch", "canonical-workspace-aliases-before-dispatch"],
)
def test_map_preflight_refusals_reserve_no_attempt(tmp_path, monkeypatch, body):
    calls = []
    _install_launcher(monkeypatch, lambda _event: 0, calls)
    with replay_case(tmp_path, body) as authority:
        code, _value = runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path)
        snapshot = read_memo(authority.memo_path, site_classes(authority.program))
        assert code != 0
        assert calls == []
        assert not any(row.data["record"] == "started" for row in snapshot.entries)


def test_ordinary_item_failures_drain_siblings_and_report_lowest_input_index(tmp_path, monkeypatch):
    calls, first_pair = [], threading.Barrier(2)
    release_a, both_started = threading.Event(), threading.Event()
    c_failed, d_committed = threading.Event(), threading.Event()

    def outcome(event):
        item = event["item"]
        if item in "ab":
            first_pair.wait(timeout=5)
            both_started.set()
        if item == "a":
            _wait(release_a)
            raise CommandPerformerError("item_a_failed", "lowest item failed")
        if item == "c":
            raise CommandPerformerError("item_c_failed", "later item failed first")
        return ord(item) - ord("a")

    _install_launcher(monkeypatch, outcome, calls)
    with replay_case(tmp_path) as authority:
        append = runtime.append_record

        def observe_completion(path, record, **kwargs):
            entry = append(path, record, **kwargs)
            if record.get("record") == "failed" and record.get("code") == "item_c_failed":
                c_failed.set()
            if record.get("record") == "committed" and record.get("identity") == effect(authority, 3)[0]:
                d_committed.set()
            return entry

        monkeypatch.setattr(runtime, "append_record", observe_completion)
        executor, future = _async_run(authority, tmp_path)
        try:
            _wait(both_started)
            _wait(c_failed)
            _wait(d_committed)
            release_a.set()
            assert future.result(timeout=5) == (1, None)
        finally:
            release_a.set()
            executor.shutdown(wait=True)

        snapshot = read_memo(authority.memo_path, site_classes(authority.program))
        rows = [entry.data for entry in snapshot.entries]
        assert {row["identity"] for row in rows if row["record"] == "committed"} == {
            effect(authority, index)[0] for index in (1, 3)
        }
        failures = [row for row in rows if row["record"] == "failed"]
        assert {row["code"] for row in failures} == {"item_a_failed", "item_c_failed"}
        assert snapshot.terminal.data["code"] == "item_a_failed"
        assert {event["item"] for event in calls} == set("abcd")


def test_pure_failure_after_item_commit_preserves_all_sibling_commits(tmp_path, monkeypatch):
    command = COMMAND.replace(":returns Int", ":returns Float")
    body = f'''(let* ((value {command}))
        (if (= repo "a") (/ value 0.0) value))'''
    calls, first_pair = [], threading.Barrier(2)
    release_a, both_started, other_items_finished = threading.Event(), threading.Event(), threading.Event()
    completed = set()
    lock = threading.Lock()

    def outcome(event):
        item = event["item"]
        if item in "ab":
            first_pair.wait(timeout=5)
            both_started.set()
        if item == "a":
            _wait(release_a)
        return 1.0

    _install_launcher(monkeypatch, outcome, calls)
    with replay_case(tmp_path, mapped("(call worker :repo repo)"), declarations=worker(body, result="Float"),
            result="List[Float]") as authority:
        _rows, _row_threads, _view_threads, _allocation_threads = _track_publishers(monkeypatch)
        append = runtime.append_record

        def observe_sibling_commits(path, record, **kwargs):
            entry = append(path, record, **kwargs)
            if record.get("record") == "committed" and record.get("identity") in {
                effect(authority, index)[0] for index in range(1, 4)
            }:
                with lock:
                    completed.add(record["identity"])
                    if len(completed) == 3:
                        other_items_finished.set()
            return entry

        monkeypatch.setattr(runtime, "append_record", observe_sibling_commits)
        executor, future = _async_run(authority, tmp_path)
        try:
            _wait(both_started)
            _wait(other_items_finished)
            release_a.set()
            assert future.result(timeout=5) == (1, None)
        finally:
            release_a.set()
            executor.shutdown(wait=True)

        snapshot = read_memo(authority.memo_path, site_classes(authority.program))
        commits = [row.data for row in snapshot.entries if row.data["record"] == "committed"]
        assert {row["identity"] for row in commits} == {effect(authority, index)[0] for index in range(4)}
        assert snapshot.terminal.data["code"] == "pure_expr_division_by_zero"


def test_nested_maps_make_progress_with_each_inner_bound(tmp_path, monkeypatch):
    calls, barrier = [], threading.Barrier(4)
    active, maximum, active_by_outer, maximum_by_outer = 0, 0, {}, {}
    lock = threading.Lock()

    def outcome(event):
        nonlocal active, maximum
        parts = event["cwd"].relative_to(tmp_path).parts
        outer, child = parts[0], parts[2]
        with lock:
            active += 1
            active_by_outer[outer] = active_by_outer.get(outer, 0) + 1
            maximum = max(maximum, active)
            maximum_by_outer[outer] = max(maximum_by_outer.get(outer, 0), active_by_outer[outer])
        try:
            barrier.wait(timeout=5)
            return int(child[1:])
        finally:
            with lock:
                active -= 1
                active_by_outer[outer] -= 1

    _install_launcher(monkeypatch, outcome, calls)
    inner = '(list/map-effect ((child (list "x0" "x1" "x2" "x3"))) :max 4 :parallel 2 '
    inner += ':workspace (string/concat repo "/child/" child "/work") '
    inner += '(command-result fetch :argv ("python" "probe.py" child) :returns Int))'
    body = '(list/map-effect ((repo (list "a" "b"))) :max 2 :parallel 2 '
    body += ':workspace (string/concat repo "/work") (call worker :repo repo))'
    with replay_case(tmp_path, body, declarations=worker(inner, result="List[Int]"),
            result="List[List[Int]]") as authority:
        for outer in "ab":
            for child in ("x0", "x1", "x2", "x3"):
                directory = tmp_path / outer / "child" / child / "work"
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "probe.py").write_text("# immutable implementation\n")
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (
            0,
            [[0, 1, 2, 3], [0, 1, 2, 3]],
        )
        assert len(calls) == 8
        assert maximum == 4
        assert maximum_by_outer == {"a": 2, "b": 2}


def _install_eight_workspaces(workspace):
    for item in "efgh":
        directory = workspace / item / "work"
        directory.mkdir(parents=True)
        (directory / "probe.py").write_text("# immutable implementation\n")


def _assert_eight_commits_have_one_writer(authority, calls, rows, row_threads, view_threads,
        allocation_threads):
    raw = authority.memo_path.read_bytes()
    decoded = [json.loads(line) for line in raw.splitlines()]
    commits = [row for row in decoded if row["record"] == "committed"]
    assert len(calls) == len(commits) == 8
    assert len({row["identity"] for row in commits}) == 8
    assert len(decoded) == len(raw.splitlines()) and raw.endswith(b"\n")
    assert {row["record"] for row in rows} == {"started", "committed", "terminal"}
    assert len(rows) == len(view_threads) == 17
    assert len(set(row_threads)) == len(set(view_threads)) == len(set(allocation_threads)) == 1
    assert set(row_threads) == set(view_threads) == set(allocation_threads)


def test_eight_concurrent_commits_are_whole_and_published_by_one_thread(tmp_path, monkeypatch):
    barrier = threading.Barrier(8)
    calls = []
    body = mapped(source='(list "a" "b" "c" "d" "e" "f" "g" "h")')
    body = body.replace(":max 4", ":max 8").replace(":parallel 2", ":parallel 8")

    def outcome(event):
        barrier.wait(timeout=5)
        return ord(event["item"]) - ord("a")

    _install_launcher(monkeypatch, outcome, calls)
    with replay_case(tmp_path, body, result="List[Int]") as authority:
        _install_eight_workspaces(tmp_path)
        rows, row_threads, view_threads, allocation_threads = _track_publishers(monkeypatch)
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (
            0,
            list(range(8)),
        )
        _assert_eight_commits_have_one_writer(
            authority, calls, rows, row_threads, view_threads, allocation_threads
        )


def test_publication_failure_releases_start_waiters_without_more_writes(tmp_path, monkeypatch):
    calls = []
    _install_launcher(monkeypatch, lambda _event: 0, calls)
    with replay_case(tmp_path) as authority:
        rows, row_threads, view_threads, _allocation_threads = _track_publishers(monkeypatch)
        publish = views.publish_evaluated_view
        failed = threading.Event()

        def fail_first_start(authority, entry):
            view_threads.append(threading.get_ident())
            if entry.data["record"] == "started":
                failed.set()
                raise ViewPublicationError("injected first-start publication failure")
            return publish(authority, entry)

        monkeypatch.setattr(views, "publish_evaluated_view", fail_first_start)
        executor, future = _async_run(authority, tmp_path)
        try:
            _wait(failed)
            assert future.result(timeout=5) == (1, None)
        finally:
            executor.shutdown(wait=True)

        snapshot = read_memo(authority.memo_path, site_classes(authority.program))
        assert [entry.data["record"] for entry in snapshot.entries] == ["started"]
        assert len(rows) == len(view_threads) == 1
        assert len(set(row_threads)) == len(set(view_threads)) == 1
        assert calls == []
