"""Fixed PRR pilot command gates; context and frozen check helper stay outside the candidate."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import time


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CONTEXT_KEYS = {"repo", "records", "diagnostics", "helper", "protected"}


class IntegrityError(RuntimeError):
    pass


def _fail(context, stage, reason):
    """Record a non-continuable integrity failure when the context grants a safe diagnostics path."""
    raw = context.get("diagnostics") if isinstance(context, dict) else None
    if isinstance(raw, str) and raw and Path(raw).is_absolute() and not _has_symlink(Path(raw)):
        directory = Path(raw)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            if directory.is_dir() and not directory.is_symlink():
                target = directory / f"{stage}-{time.time_ns()}.json"
                with target.open("x") as stream:
                    json.dump({"stage": stage, "reason": reason, "paid_continuation_allowed": False}, stream)
        except OSError:
            pass
    raise IntegrityError(reason)


def _has_symlink(path):
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _absolute_path(value, context, stage, label, *, strict=True):
    if not isinstance(value, str) or not value or "\0" in value:
        _fail(context, stage, f"{label} must be a non-empty absolute path")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != os.path.normpath(value):
        _fail(context, stage, f"{label} must be a normalized absolute path")
    if _has_symlink(path):
        _fail(context, stage, f"{label} contains a symlink")
    try:
        resolved = path.resolve(strict=strict)
    except (OSError, RuntimeError, ValueError) as error:
        _fail(context, stage, f"{label} cannot be resolved: {error}")
    return resolved


def _outside(path, repo, context, stage, label):
    if path.is_relative_to(repo):
        _fail(context, stage, f"{label} must be outside the candidate")


def _validate_context(context, stage, context_path=None):
    if not isinstance(context, dict) or set(context) != _CONTEXT_KEYS:
        _fail(context, stage, "context must contain exactly repo, records, diagnostics, helper and protected")

    repo = _absolute_path(context["repo"], context, stage, "candidate repo")
    if not repo.is_dir():
        _fail(context, stage, "candidate repo is not a directory")
    records = _absolute_path(context["records"], context, stage, "records directory")
    if not records.is_dir():
        _fail(context, stage, "records path is not a directory")
    _outside(records, repo, context, stage, "records path")
    diagnostics = _absolute_path(context["diagnostics"], context, stage, "diagnostics directory", strict=False)
    _outside(diagnostics, repo, context, stage, "diagnostics path")

    if context_path is not None:
        frozen_context = _absolute_path(context_path, context, stage, "context file")
        if not frozen_context.is_file():
            _fail(context, stage, "context file is not a regular file")
        _outside(frozen_context, repo, context, stage, "context file")

    helper = context["helper"]
    if not isinstance(helper, dict) or set(helper) != {"path", "sha256"}:
        _fail(context, stage, "helper must contain exactly path and sha256")
    helper_path = _absolute_path(helper["path"], context, stage, "frozen helper")
    if not helper_path.is_file():
        _fail(context, stage, "frozen helper is not a regular file")
    _outside(helper_path, repo, context, stage, "frozen helper")
    if not isinstance(helper["sha256"], str) or not _SHA256.fullmatch(helper["sha256"]):
        _fail(context, stage, "frozen helper has an invalid SHA256")

    protected = context["protected"]
    if not isinstance(protected, dict) or not protected or "dev-check.json" not in protected:
        _fail(context, stage, "protected manifest must include dev-check.json")
    for relative, expected in protected.items():
        if (not isinstance(relative, str) or not relative or "\0" in relative or "\\" in relative
                or PurePosixPath(relative).is_absolute()
                or str(PurePosixPath(relative)) != relative
                or any(part in {"", ".", ".."} for part in PurePosixPath(relative).parts)):
            _fail(context, stage, "protected paths must be normalized candidate-relative paths")
        if expected is not None and (not isinstance(expected, str) or not _SHA256.fullmatch(expected)):
            _fail(context, stage, f"protected input has an invalid SHA256: {relative}")
    return repo, records, diagnostics, helper_path


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_protected(repo, protected, context, stage):
    for relative, expected in protected.items():
        path = repo
        missing = False
        for index, part in enumerate(PurePosixPath(relative).parts):
            path = path / part
            if path.is_symlink():
                _fail(context, stage, f"protected path contains a symlink: {relative}")
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                missing = True
                break
            except OSError as error:
                _fail(context, stage, f"protected path cannot be inspected: {relative}: {error}")
            if index < len(PurePosixPath(relative).parts) - 1 and not stat.S_ISDIR(mode):
                _fail(context, stage, f"protected path parent is not a directory: {relative}")
        if missing:
            if expected is None:
                continue
            _fail(context, stage, f"protected input is missing: {relative}")
        if expected is None:
            _fail(context, stage, f"new protected input: {relative}")
        if not stat.S_ISREG(mode):
            _fail(context, stage, f"protected input is not a regular file: {relative}")
        try:
            if _digest(path) != expected:
                _fail(context, stage, f"changed protected input: {relative}")
        except OSError as error:
            _fail(context, stage, f"protected input cannot be read: {relative}: {error}")


def verify(context, stage, context_path=None):
    """Verify the exact check inputs, trusted helper and external context at one pilot boundary."""
    repo, _, _, helper = _validate_context(context, stage, context_path)
    try:
        helper_digest = _digest(helper)
    except OSError as error:
        _fail(context, stage, f"trusted public-check helper cannot be read: {error}")
    if helper_digest != context["helper"]["sha256"]:
        _fail(context, stage, "trusted public-check helper changed")
    _check_protected(repo, context["protected"], context, stage)
    return repo


def _bundle_path(context, value, stage, repo):
    if not isinstance(value, str) or not value or "\0" in value:
        _fail(context, stage, "output bundle must be a non-empty path")
    raw = Path(value)
    if raw.is_absolute():
        path = _absolute_path(value, context, stage, "output bundle", strict=False)
    else:
        relative = PurePosixPath(value)
        if ("\\" in value or str(relative) != value
                or any(part in {"", ".", ".."} for part in relative.parts)):
            _fail(context, stage, "relative output bundle must be a normalized in-workspace path")
        workspace = _absolute_path(str(Path.cwd()), context, stage, "command workspace")
        path = _absolute_path(str(workspace.joinpath(*relative.parts)), context, stage,
                              "output bundle", strict=False)
    if not path.is_relative_to(repo):
        _fail(context, stage, "output bundle must stay inside the candidate")
    if not path.parent.is_dir():
        _fail(context, stage, "output bundle parent is missing")
    if path.exists() or path.is_symlink():
        _fail(context, stage, "output bundle already exists")
    return path


def _report(bundle, context, stage):
    try:
        report = json.loads(bundle.read_text())
    except (OSError, ValueError) as error:
        _fail(context, stage, f"trusted public-check helper did not deliver JSON: {error}")
    if (not isinstance(report, dict) or set(report) != {"passed", "failing", "excerpt"}
            or type(report["passed"]) is not bool
            or not isinstance(report["failing"], list)
            or not all(isinstance(item, str) for item in report["failing"])
            or not isinstance(report["excerpt"], str)
            or (report["passed"] and report["failing"])
            or (not report["passed"] and not report["failing"])):
        _fail(context, stage, "trusted public-check report has an invalid shape")
    return report


def check(context, bundle, context_path=None):
    """Integrity failures stop the command; ordinary public-check failures return passed=false."""
    repo = verify(context, "before-tests", context_path)
    bundle = _bundle_path(context, bundle, "before-tests", repo)
    helper = Path(context["helper"]["path"])
    config_path = repo / "dev-check.json"
    try:
        config = json.loads(config_path.read_text())
    except (OSError, ValueError) as error:
        _fail(context, "before-tests", f"the frozen dev-check.json is invalid: {error}")
    if (not isinstance(config, dict) or config.get("timeout_sec") != 1800
            or not isinstance(config.get("argv"), list) or not config["argv"]
            or not all(isinstance(token, str) and token for token in config["argv"])):
        _fail(context, "before-tests", "the original 1800-second dev-check command is invalid")
    env = {**os.environ, "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(bundle)}
    try:
        result = subprocess.run([sys.executable, str(helper)], cwd=repo, env=env,
                                text=True, capture_output=True, timeout=1830)
    except subprocess.TimeoutExpired:
        _fail(context, "check-wrapper", "trusted public-check helper exceeded its execution envelope")
    verify(context, "after-tests", context_path)
    if result.returncode:
        _fail(context, "check-wrapper", f"trusted public-check helper exited {result.returncode}")
    _report(bundle, context, "check-wrapper")


def audit_diagnosis(context, bundle, context_path=None):
    """Permit repair only after an unchanged diagnosis snapshot and intact check inputs."""
    repo, records, _, _ = _validate_context(context, "after-diagnosis", context_path)
    verify(context, "after-diagnosis", context_path)
    bundle = _bundle_path(context, bundle, "after-diagnosis", repo)
    calls = records / "calls"
    if _has_symlink(calls) or not calls.is_dir():
        _fail(context, "after-diagnosis", "provider call records are missing or unsafe")
    if (calls / "3").exists() or (calls / "3").is_symlink():
        _fail(context, "after-diagnosis", "repair call exists before diagnosis audit")
    snapshots = [calls / str(number) / "patch-cand-1.diff" for number in (1, 2)]
    for snapshot in snapshots:
        if (_has_symlink(snapshot) or not snapshot.is_file()
                or not snapshot.resolve(strict=True).is_relative_to(records)):
            _fail(context, "after-diagnosis", "implementation or diagnosis patch snapshot is missing or unsafe")
    try:
        if snapshots[0].read_bytes() != snapshots[1].read_bytes():
            _fail(context, "after-diagnosis", "diagnosis changed the original implementation snapshot")
        with bundle.open("x") as stream:
            stream.write("true\n")
    except OSError as error:
        _fail(context, "after-diagnosis", f"diagnosis audit evidence cannot be written: {error}")


def _load_context(path):
    try:
        context = json.loads(Path(path).read_text())
    except (OSError, ValueError) as error:
        raise IntegrityError(f"frozen context cannot be read: {error}") from error
    _validate_context(context, "context", path)
    return context


def main():
    if len(sys.argv) != 3:
        print("PRR pilot integrity failure: expected MODE CONTEXT", file=sys.stderr)
        return 70
    mode, context_path = sys.argv[1:]
    try:
        context = _load_context(context_path)
        bundle = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
        if not bundle:
            _fail(context, "command", "ORCHESTRATOR_OUTPUT_BUNDLE_PATH is missing")
        if mode == "check":
            check(context, bundle, context_path)
        elif mode == "audit-diagnosis":
            audit_diagnosis(context, bundle, context_path)
        else:
            _fail(context, "command", "unknown fixed pilot command")
    except IntegrityError as error:
        print(f"PRR pilot integrity failure: {error}", file=sys.stderr)
        return 70
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
