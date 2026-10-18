"""Waiting for a scan verdict (judging.await_verdict) on a scan file that is not JSON yet."""

import json
import threading

from experiments.orc_structural_search import judging


def test_await_verdict_says_once_that_a_scan_is_not_json_and_keeps_polling(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(judging, "POLL_SEC", 0.01)
    scan = tmp_path / "scan.json"
    scan.write_text('{"hits": [')  # being written
    later = {"hits": [{"file": "f", "line": 1, "pattern": "p"}], "verdict": {"verdict": "cleared"}}
    timer = threading.Timer(0.3, lambda: scan.write_text(json.dumps(later)))
    timer.start()
    found = judging.await_verdict(scan, lambda value: value, "prepare.py scan --run R")
    timer.join()
    printed = capsys.readouterr().out
    assert (found, printed.count(f"{scan} is not JSON")) == (later, 1)
