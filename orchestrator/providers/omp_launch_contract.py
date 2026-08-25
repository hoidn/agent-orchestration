"""Closed code-owned OMP launch envelopes shared by publication and resume."""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Sequence
from orchestrator._common.safe_tree import SafeTreePathError, validate_relative_path

POSITIVE_ENV_NAMES = (
    "HOME", "LANG", "LC_ALL", "OMP_BROKER_TOKEN", "OMP_BROKER_URL", "PATH",
    "PI_CODING_AGENT_DIR", "TMPDIR", "XDG_CACHE_HOME", "XDG_CONFIG_HOME",
    "XDG_DATA_HOME", "XDG_STATE_HOME",
)
ADAPTER_WRAPPER = (sys.executable, "-m", "orchestrator.providers.omp_launch")
_PROVIDERS = {
    "omp", "omp_unrestricted_workspace", "omp_no_tools", "omp_conf",
    "omp_conf_inference",
}
_PROFILE_PROVIDERS = {"omp_no_tools", "omp_conf"}
_EMPTY_CWD = re.compile(r"omp-empty-[0-9a-f]{16}-[0-9a-f]{16}\Z")


def parse_adapter_argv(argv: list[str], lane_names: set[str]) -> dict[str, str | None]:
    """Parse the adapter's closed flag/value grammar."""
    if argv[:1] != ["run"]:
        raise ValueError("expected leading 'run' subcommand")
    args: dict[str, str | None] = {
        "lane": None, "model": None, "conf_root": None, "session_dir": None,
        "conf_root_device": None, "conf_root_inode": None,
        "conf_manifest_sha256": None,
    }
    options = {
        "--lane", "--model", "--conf-root", "--provider-session-dir",
        "--conf-root-device", "--conf-root-inode", "--conf-manifest-sha256",
    }
    seen: set[str] = set()
    index = 1
    while index < len(argv):
        option = argv[index]
        if option not in options:
            kind = "option" if option.startswith("-") else "positional argument"
            raise ValueError(f"unexpected {kind} {option!r}")
        if option in seen or index + 1 >= len(argv):
            message = f"duplicate option {option!r}" if option in seen else f"missing value for {option!r}"
            raise ValueError(message)
        value = argv[index + 1]
        index += 2
        seen.add(option)
        if option == "--lane":
            if value not in lane_names:
                raise ValueError(f"unknown lane {value!r}")
            args["lane"] = value
        elif option == "--model":
            if not value or any(ch.isspace() for ch in value):
                raise ValueError("model must be a single non-whitespace token")
            args["model"] = value
        elif option in ("--conf-root", "--provider-session-dir"):
            if not os.path.isabs(value):
                raise ValueError(f"{option} must be an absolute path")
            args["conf_root" if option == "--conf-root" else "session_dir"] = value
        elif option in ("--conf-root-device", "--conf-root-inode"):
            if not value.isdigit():
                raise ValueError(f"{option} must be a non-negative integer")
            args[option[2:].replace("-", "_")] = value
        else:
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError("--conf-manifest-sha256 must be lowercase SHA-256")
            args["conf_manifest_sha256"] = value
    if args["lane"] is None or args["model"] is None:
        raise ValueError("missing --lane or --model")
    if args["conf_root"] is not None and args["lane"] not in ("omp_conf", "omp_no_tools"):
        raise ValueError("conf-root is accepted only on conf or no-tools lane")
    if args["lane"] == "omp_conf" and args["conf_root"] is None:
        raise ValueError("the omp_conf lane requires --conf-root")
    frozen = (args["conf_root_device"], args["conf_root_inode"], args["conf_manifest_sha256"])
    if any(value is not None for value in frozen):
        if (
            args["lane"] != "omp_no_tools"
            or args["conf_root"] is None
            or any(value is None for value in frozen)
        ):
            raise ValueError("frozen conf authority is complete and no-tools-only")
    return args


def build_fresh_adapter_argv(
    provider: str, model: str, *, session_dir: str | None,
    conf_root: str | None = None,
    frozen_conf: tuple[int, int, str] | None = None,
) -> tuple[str, ...]:
    """Build the sole admitted post-wrapper argv for one fresh OMP visit."""
    if provider not in _PROVIDERS or not model:
        raise ValueError("invalid OMP provider/model")
    if (provider in _PROFILE_PROVIDERS) != (conf_root is not None):
        raise ValueError("OMP conf root does not match the selected provider")
    argv = ["run", "--lane", provider, "--model", model]
    if conf_root is not None:
        argv.extend(("--conf-root", conf_root))
    if session_dir is not None:
        argv.extend(("--provider-session-dir", session_dir))
    if frozen_conf is not None:
        if provider != "omp_no_tools" or session_dir is None:
            raise ValueError("frozen conf authority is only valid for no-tools fresh visits")
        device, inode, digest = frozen_conf
        argv.extend(("--conf-root-device", str(device), "--conf-root-inode", str(inode),
                     "--conf-manifest-sha256", digest))
    return tuple(argv)


def resolved_adapter_command(argv: Sequence[str]) -> str:
    """Return the exact metadata projection used by WorkflowExecutor."""
    return " ".join((*ADAPTER_WRAPPER, *argv))


def valid_fresh_child_cwd(provider: str, cwd: object, workspace: str) -> bool:
    """Validate the lane-owned adapter child cwd value or closed profile shape."""
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or os.path.normpath(cwd) != cwd:
        return False
    return bool(_EMPTY_CWD.fullmatch(os.path.basename(cwd))) if provider in _PROFILE_PROVIDERS else cwd == workspace


def valid_observed_relpaths(value: object) -> bool:
    """Return whether a frame inventory is sorted, unique, and path-safe."""
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        return False
    if value != sorted(set(value)):
        return False
    try:
        for item in value:
            validate_relative_path(item)
    except SafeTreePathError:
        return False
    return True


def valid_private_binary_path(path: object, executable_sha256: str) -> bool:
    """Validate the deterministic private-copy path known without env values."""
    if not isinstance(path, str) or not os.path.isabs(path) or os.path.normpath(path) != path:
        return False
    digest_dir = os.path.dirname(path)
    return (bool(os.path.basename(path)) and os.path.basename(digest_dir) == executable_sha256
            and os.path.basename(os.path.dirname(digest_dir)) == "private"
            and os.path.basename(os.path.dirname(os.path.dirname(digest_dir))) == "omp-i1")


def build_interactive_argv(
    provider: str, model: str, *, private_binary: str, live_dir: str,
    mode: str, source_session_id: str, workspace: str,
    empty_cwd: str | None = None,
) -> tuple[str, ...]:
    """Build the exact X8 foreground continuation argv after path substitution."""
    if (
        provider not in (_PROVIDERS - {"omp_conf_inference"})
        or mode not in {"fork", "in_place"}
    ):
        raise ValueError("invalid OMP continuation selection")
    argv = [private_binary, "--no-title"]
    if provider == "omp_no_tools":
        argv.extend(("--no-extensions", "--no-skills", "--no-rules", "--no-tools"))
    elif provider == "omp_conf":
        argv.extend(("--no-extensions", "--no-skills", "--no-rules"))
    argv.extend(("--model", model))
    if provider == "omp_unrestricted_workspace":
        argv.append("--yolo")
    else:
        argv.extend(("--approval-mode", "write"))
    if provider in _PROFILE_PROVIDERS:
        if empty_cwd is None:
            raise ValueError("profile continuation requires an empty cwd")
        argv.extend(("--cwd", empty_cwd))
        if provider == "omp_conf":
            argv.extend(("--add-dir", workspace))
    elif empty_cwd is not None:
        raise ValueError("ambient continuation cannot carry an empty cwd")
    argv.extend(("--session-dir", live_dir))
    argv.extend(("--resume" if mode == "in_place" else "--fork", source_session_id))
    return tuple(argv)


__all__ = ["ADAPTER_WRAPPER", "POSITIVE_ENV_NAMES", "build_fresh_adapter_argv",
           "build_interactive_argv", "parse_adapter_argv", "resolved_adapter_command",
           "valid_fresh_child_cwd", "valid_observed_relpaths",
           "valid_private_binary_path"]
