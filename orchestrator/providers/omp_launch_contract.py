"""Closed code-owned OMP launch envelopes shared by publication and resume."""

from __future__ import annotations

import os
import re
import sys
import subprocess
from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit
from typing import TypedDict, cast
from orchestrator._common.safe_tree import SafeTreePathError, validate_relative_path

# The single X2 credential mechanism: both members are required for every
# profile lane, structurally validated before the version probe, and never
# printed, framed, or logged.
BROKER_URL_ENV = "OMP_AUTH_BROKER_URL"
BROKER_TOKEN_ENV = "OMP_AUTH_BROKER_TOKEN"
BROKER_SETUP_COMMAND = "omp auth-broker serve"

# The closed ``omp_conf_env.v1`` profile schema: adapter-owned attempt roots
# plus required/optional copied values and the single broker credential pair.
# No other key may enter a profile child environment.
PROFILE_ENV_NAMES = (
    "COLORTERM", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "NO_COLOR",
    "NODE_EXTRA_CA_CERTS", "OMP_AUTH_BROKER_TOKEN", "OMP_AUTH_BROKER_URL",
    "PATH", "PI_CODING_AGENT_DIR", "SHELL", "SSL_CERT_DIR", "SSL_CERT_FILE",
    "TERM", "TMPDIR", "TZ", "XDG_CACHE_HOME", "XDG_CONFIG_HOME",
    "XDG_DATA_HOME", "XDG_STATE_HOME",
)
_PROFILE_REQUIRED_ENV_NAMES = frozenset({
    "HOME", "OMP_AUTH_BROKER_TOKEN", "OMP_AUTH_BROKER_URL", "PATH",
    "PI_CODING_AGENT_DIR", "SHELL", "TMPDIR", "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
})

# Registry template name -> code-owned policy lane (frame/expectation vocab).
LANE_POLICY = {"omp": "ambient", "omp_unrestricted_workspace": "ambient-unrestricted",
               "omp_no_tools": "no-tools", "omp_conf": "conf", "omp_conf_inference": "conf-inference"}
AMBIENT_POLICIES = frozenset({"ambient", "ambient-unrestricted"})
PROFILE_POLICIES = frozenset({"no-tools", "conf", "conf-inference"})

ADAPTER_WRAPPER = (sys.executable, "-m", "orchestrator.providers.omp_launch")
_PROVIDERS = {
    "omp", "omp_unrestricted_workspace", "omp_no_tools", "omp_conf",
    "omp_conf_inference",
}
_PROFILE_PROVIDERS = {"omp_no_tools", "omp_conf"}
_EMPTY_CWD = re.compile(r"omp-empty-[0-9a-f]{16}-[0-9a-f]{16}\Z")


def valid_launch_env_names(provider: str, value: object) -> bool:
    """Validate the historical child environment-name projection by lane."""
    if provider not in _PROVIDERS or not isinstance(value, list):
        return False
    if (
        any(
            not isinstance(name, str)
            or not name
            or "\x00" in name
            or "=" in name
            for name in value
        )
        or value != sorted(set(value))
    ):
        return False
    names = set(value)
    if LANE_POLICY[provider] in PROFILE_POLICIES:
        return (
            _PROFILE_REQUIRED_ENV_NAMES <= names
            and names <= set(PROFILE_ENV_NAMES)
        )
    return True

# X2 loopback grammar: the netloc must be the exact IP literal (IPv6 in
# brackets) with an explicit decimal port; userinfo, query, and fragment are
# rejected by the caller after urlsplit.
_LOOPBACK_NETLOC = re.compile(r"^(\[::1\]|127\.0\.0\.1):([0-9]+)$")


def validate_broker_pair(env: Mapping[str, str]) -> tuple[str, str]:
    """Return the structurally valid (url, token) broker pair or raise.

    Missing members and malformed URLs fail before any OMP process starts;
    the refusal prints the exact setup command and never the credential
    values. Host admission follows X2: urlsplit hostname must be the IP
    literal ``127.0.0.1`` or ``::1``, the netloc must spell the bracketed
    IPv6/plain IPv4 literal with an explicit port in ``1..65535``, and no
    userinfo, query, or fragment may be present.
    """
    url = env.get(BROKER_URL_ENV)
    token = env.get(BROKER_TOKEN_ENV)
    if not url or not token:
        raise ValueError(
            f"profile launch requires {BROKER_URL_ENV} and {BROKER_TOKEN_ENV}; "
            f"run '{BROKER_SETUP_COMMAND}'"
        )
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValueError(
            f"{BROKER_URL_ENV} is not a valid absolute http URL; "
            f"run '{BROKER_SETUP_COMMAND}'"
        ) from exc
    match = _LOOPBACK_NETLOC.fullmatch(parsed.netloc)
    if (
        parsed.scheme != "http"
        or match is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.hostname not in ("127.0.0.1", "::1")
    ):
        raise ValueError(
            f"{BROKER_URL_ENV} must be an absolute http URL whose host is the "
            f"IP literal 127.0.0.1 or [::1] with an explicit port and no "
            f"userinfo, query, or fragment; run '{BROKER_SETUP_COMMAND}'"
        )
    port = int(match.group(2))
    if not 1 <= port <= 65535:
        raise ValueError(
            f"{BROKER_URL_ENV} port must be in 1..65535; "
            f"run '{BROKER_SETUP_COMMAND}'"
        )
    return url, token



class AdapterArgs(TypedDict):
    lane: str
    model: str
    conf_root: str | None
    session_dir: str | None
    conf_root_device: str | None
    conf_root_inode: str | None
    conf_manifest_sha256: str | None


def parse_adapter_argv(argv: list[str], lane_names: set[str]) -> AdapterArgs:
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
    return cast(AdapterArgs, args)


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
    """Validate the fresh private launch-attempt path without opening it."""
    if (
        not isinstance(path, str)
        or not os.path.isabs(path)
        or os.path.normpath(path) != path
        or os.path.basename(path) != "omp"
    ):
        return False
    attempt_dir = os.path.dirname(path)
    digest_dir = os.path.dirname(attempt_dir)
    attempt = os.path.basename(attempt_dir)
    return (
        bool(re.fullmatch(r"attempt-[0-9a-f]{32}", attempt))
        and os.path.basename(digest_dir) == executable_sha256
        and os.path.basename(os.path.dirname(digest_dir)) == "private"
        and os.path.basename(os.path.dirname(os.path.dirname(digest_dir)))
        == "omp-i1"
    )


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




def build_child_argv(
    lane: str,
    policy: str,
    model: str,
    session_dir: str | None,
    workspace: str,
    empty_cwd: str | None,
) -> list[str]:
    """Exact X2 child argv for every lane (print-mode JSON, no title)."""
    argv = ["-p", "--mode", "json", "--no-title"]
    if policy in ("no-tools", "conf-inference"):
        argv += ["--no-extensions", "--no-skills", "--no-rules", "--no-tools"]
    elif policy == "conf":
        argv += ["--no-extensions", "--no-skills", "--no-rules"]
    argv += ["--model", model]
    if policy == "ambient-unrestricted":
        argv += ["--yolo"]
    else:
        argv += ["--approval-mode", "write"]
    if policy in PROFILE_POLICIES:
        argv += ["--cwd", empty_cwd]
        if policy == "conf":
            argv += ["--add-dir", workspace]
    argv += ["--session-dir", session_dir] if session_dir is not None else ["--no-session"]
    return argv


def relay_child_output(
    proc: "subprocess.Popen[bytes]", out, err, redact: bytes | None = None
) -> tuple[str | None, bool]:
    """Relay child bytes while the shared X3 state machine settles them."""
    import threading

    from .omp_transport import OmpJsonStdoutAccumulator

    accumulator = OmpJsonStdoutAccumulator(expectation=None)
    stdout, stderr = proc.stdout, proc.stderr
    assert stdout is not None and stderr is not None

    def _drain_stderr() -> None:
        try:
            data = stderr.read()
        except OSError:
            return
        if redact is not None:
            data = data.replace(redact, b"[redacted]")
        err.write(data.decode("utf-8", errors="replace"))

    thread = threading.Thread(target=_drain_stderr, daemon=True)
    thread.start()
    while True:
        chunk = stdout.read(1 << 16)
        if not chunk:
            break
        out.write(chunk)
        accumulator.feed(chunk)
    proc.wait()
    thread.join()
    session_id, error = accumulator.finalize_child_stream()
    return session_id, error is None


__all__ = ["ADAPTER_WRAPPER", "AMBIENT_POLICIES", "BROKER_SETUP_COMMAND",
           "BROKER_TOKEN_ENV", "BROKER_URL_ENV", "LANE_POLICY",
           "PROFILE_ENV_NAMES", "PROFILE_POLICIES",
           "build_child_argv", "build_fresh_adapter_argv",
           "build_interactive_argv", "parse_adapter_argv",
           "relay_child_output", "resolved_adapter_command",
           "valid_launch_env_names", "validate_broker_pair",
           "valid_fresh_child_cwd", "valid_observed_relpaths",
           "valid_private_binary_path"]
