#!/usr/bin/env python3
"""Deterministic Codex-JSONL stand-in for the ES public-entry tests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any


VERSION = "codex-cli 0.145.0"
CONTROL_PATH_ENV = "ES_TASK5_FAKE_CONTROL_PATH"


def _fixture_root() -> Path:
    launcher = Path(shutil.which(sys.argv[0]) or sys.argv[0])
    if not launcher.is_absolute():
        launcher = Path.cwd() / launcher
    return launcher.parent.parent


def _control_path() -> Path:
    explicit = os.environ.get(CONTROL_PATH_ENV)
    if explicit is not None:
        path = Path(explicit)
        if not explicit or not path.is_absolute():
            raise SystemExit(88)
        return path
    return _fixture_root() / "fake-control.json"


def _control() -> dict[str, Any]:
    path = _control_path()
    if not path.is_file():
        if CONTROL_PATH_ENV in os.environ:
            raise SystemExit(88)
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise SystemExit(88) from None
    if not isinstance(value, dict):
        raise SystemExit(88 if CONTROL_PATH_ENV in os.environ else 80)
    return value


def _manifest() -> dict[str, Any] | None:
    path = os.environ.get("ORC_ES_PROVIDER_BOUNDARY_MANIFEST_PATH")
    if not path:
        return None
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(81)
    return value


def _current_slot(
    manifest: dict[str, Any] | None,
    *,
    prompt: bytes,
) -> str | None:
    if manifest is None:
        return None
    prompt_sha256 = "sha256:" + hashlib.sha256(prompt).hexdigest()
    cwd = Path.cwd().resolve()
    calls = manifest.get("calls")
    matching: list[str] = []
    if isinstance(calls, list):
        for call in calls:
            selector = call.get("cwd_selector") if isinstance(call, dict) else None
            prompt_sha256s = (
                call.get("prompt_sha256s") if isinstance(call, dict) else None
            )
            if (
                not isinstance(prompt_sha256s, list)
                or not prompt_sha256s
                or any(
                    not isinstance(value, str)
                    or len(value) != 71
                    or not value.startswith("sha256:")
                    or any(
                        character not in "0123456789abcdef"
                        for character in value[7:]
                    )
                    for value in prompt_sha256s
                )
                or prompt_sha256s != sorted(set(prompt_sha256s))
            ):
                raise SystemExit(89)
            if (
                not isinstance(call, dict)
                or prompt_sha256 not in prompt_sha256s
                or not isinstance(call.get("call_slot_id"), str)
                or not isinstance(selector, dict)
                or not isinstance(selector.get("path"), str)
                or call.get("output_bundle_path")
                != os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
                or call.get("provider_attempt_site_key")
                != os.environ.get("ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY")
            ):
                continue
            root = Path(selector["path"])
            if selector.get("kind") == "exact":
                cwd_matches = cwd == root
            else:
                try:
                    cwd.relative_to(root)
                except ValueError:
                    cwd_matches = False
                else:
                    cwd_matches = selector.get("kind") == "under"
            if cwd_matches:
                matching.append(call["call_slot_id"])
    if len(matching) == 1:
        return matching[0]
    if matching:
        raise SystemExit(87)
    journal = manifest.get("journal_path")
    if not isinstance(journal, str):
        raise SystemExit(82)
    rows = [
        json.loads(line)
        for line in Path(journal).read_text(encoding="utf-8").splitlines()
    ]
    if not rows or not isinstance(rows[-1].get("call_slot_id"), str):
        raise SystemExit(83)
    return rows[-1]["call_slot_id"]


def _output_path() -> Path:
    value = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
    if not value:
        raise SystemExit(84)
    path = Path(value)
    return path if path.is_absolute() else Path.cwd() / path


def _write_treatment_result(slot: str | None) -> None:
    artifact_by_role = {
        "D": "artifacts/work/qa-placement/design.md",
        "DR": "artifacts/review/qa-placement/design-review.md",
        "DREV": "artifacts/work/qa-placement/design.md",
        "PR": "artifacts/review/qa-placement/product-review.md",
    }
    output = _output_path()
    output_name = output.as_posix()
    role = (
        slot.rsplit(".", 1)[-1]
        if slot is not None
        else (
            "DR"
            if "review_design" in output_name
            else "DREV"
            if "revise_design" in output_name
            else "D"
            if "produce_design" in output_name
            else "PR"
            if "review_product" in output_name
            else "I"
        )
    )
    artifact = artifact_by_role.get(role)
    if artifact is not None:
        target = Path.cwd() / artifact
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"fixture artifact for {role}\n", encoding="utf-8")

    output.parent.mkdir(parents=True, exist_ok=True)
    value: object = (
        {"decision": _control().get("review_decision", "APPROVE")}
        if role in {"DR", "PR"}
        else True
    )
    output.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _evaluation_packet(prompt: bytes) -> dict[str, Any]:
    text = prompt.decode("utf-8", "strict")
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(value, dict)
            and value.get("schema") == "trial.evaluation_packet.v1"
            and isinstance(value.get("evaluation_id"), str)
        ):
            return value
    raise SystemExit(85)


def _try_evaluation_packet(prompt: bytes) -> dict[str, Any] | None:
    try:
        return _evaluation_packet(prompt)
    except SystemExit as exc:
        if exc.code == 85:
            return None
        raise


def _capture(
    prompt: bytes,
    slot: str | None,
    *,
    arguments: list[str],
) -> None:
    capture_root = os.environ.get("ES_TASK5_FAKE_CAPTURE_DIR")
    if (
        not capture_root
        and CONTROL_PATH_ENV not in os.environ
        and _control_path().is_file()
    ):
        capture_root = (_fixture_root() / "captured-prompts").as_posix()
    if not capture_root:
        cwd = Path.cwd()
        capture_root = next(
            (
                (ancestor / "captured-prompts").as_posix()
                for ancestor in (cwd, *cwd.parents)
                if (ancestor / "children").is_dir()
                and (ancestor / "runs").is_dir()
            ),
            None,
        )
    if not capture_root:
        return
    record = {
        "arguments": arguments,
        "cwd": Path.cwd().as_posix(),
        "output_bundle_path": os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH"),
        "provider_attempt_site_key": os.environ.get(
            "ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY"
        ),
        "prompt": prompt.decode("utf-8", "strict"),
        "slot": slot,
    }
    raw = json.dumps(
        record,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    identity = hashlib.sha256(raw).hexdigest()
    root = Path(capture_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{identity}.json").write_bytes(raw)


def _assistant_text(slot: str | None, prompt: bytes) -> str:
    packet = _try_evaluation_packet(prompt)
    if packet is None:
        return "fixture treatment completed"
    citable = packet.get("citable_item_ids")
    if not isinstance(citable, list) or not citable or not isinstance(citable[0], str):
        raise SystemExit(86)
    return json.dumps(
        {
            "candidate_id": packet["evaluation_id"],
            "score": 0.75,
            "summary": "deterministic provider-free score",
            "citations": [citable[0]],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def main() -> int:
    arguments = sys.argv[1:]
    if arguments:
        launcher_argument = Path(arguments[0])
        try:
            launcher_name = launcher_argument.resolve(strict=True).name
        except OSError:
            launcher_name = launcher_argument.name
        if launcher_name == "codex.js":
            arguments = arguments[1:]
    if arguments == ["--version"]:
        print(VERSION)
        return 0
    prompt = sys.stdin.buffer.read()
    manifest = _manifest()
    expected_arguments = (
        [
            "exec",
            "--json",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--model",
            "gpt-5.5",
            "--config",
            "model_reasoning_effort=high",
            "--",
            "-",
        ]
        if manifest is not None
        else [
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--model",
            "gpt-5.5",
            "--config",
            "reasoning_effort=high",
        ]
    )
    if arguments != expected_arguments:
        _capture(prompt, None, arguments=arguments)
        return 64

    slot = _current_slot(manifest, prompt=prompt)
    _capture(prompt, slot, arguments=arguments)
    control = _control()
    fail_slot = control.get(
        "fail_slot",
        os.environ.get("ES_TASK5_FAKE_FAIL_SLOT"),
    )
    fail_provider_attempt_site_key = control.get("fail_provider_attempt_site_key")
    failed = (slot is not None and slot == fail_slot) or (
        isinstance(fail_provider_attempt_site_key, str)
        and bool(fail_provider_attempt_site_key)
        and fail_provider_attempt_site_key
        == os.environ.get("ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY")
    )
    if _try_evaluation_packet(prompt) is None and not failed:
        _write_treatment_result(slot)

    session = hashlib.sha256(
        (slot or "DISCOVERY").encode("ascii") + b"\0" + prompt
    ).hexdigest()[:24]
    events = (
        {"type": "thread.started", "thread_id": f"fixture-{session}"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "fixture-message",
                "type": "agent_message",
                "text": _assistant_text(slot, prompt),
            },
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 17,
                "cached_input_tokens": 3,
                "cache_write_input_tokens": 0,
                "output_tokens": 5,
                "reasoning_output_tokens": 1,
            },
        },
    )
    for event in events:
        print(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
    return 9 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
