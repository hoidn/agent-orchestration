"""Adversarial capability probe executed only inside the I0 namespace."""

from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import json
import os
from pathlib import Path
import socket


_MAX_PROBE_CONFIG_BYTES = 1024 * 1024
_MAX_PROC_DISCLOSURE_BYTES = 1024 * 1024
_PIDFD_GETFD_SYSCALL = 438
_PTRACE_ATTACH = 16
_PTRACE_DETACH = 17
_TIOCSTI = 0x5412
_TIOCSCTTY = 0x540E


def _errno_name(value: int | None) -> str:
    if value is None:
        return "ERRNO_UNKNOWN"
    return errno.errorcode.get(value, f"ERRNO_{value}")


def _load_probe_config(path: str) -> dict[str, object]:
    with open(path, "rb") as handle:
        encoded = handle.read(_MAX_PROBE_CONFIG_BYTES + 1)
    if len(encoded) > _MAX_PROBE_CONFIG_BYTES:
        raise RuntimeError("probe config exceeds the size limit")
    document = json.loads(encoded.decode("utf-8", errors="strict"))
    if not isinstance(document, dict):
        raise RuntimeError("probe config must be an object")
    expected_keys = {
        "abstract_name_hex",
        "directory_authorities",
        "expected_cmdline",
        "expected_environment",
        "forbidden_paths",
        "prior_raw_bundle",
        "relative_forbidden",
        "schema_version",
        "tcp_port",
    }
    if set(document) != expected_keys:
        raise RuntimeError("probe config has unexpected fields")
    if (
        document["schema_version"]
        != "provider_isolation_i0_probe_config.v1"
    ):
        raise RuntimeError("probe config schema is unsupported")

    for name in ("forbidden_paths", "directory_authorities"):
        values = document[name]
        if (
            not isinstance(values, list)
            or not values
            or any(
                not isinstance(value, str)
                or not value
                or not os.path.isabs(value)
                for value in values
            )
        ):
            raise RuntimeError(
                f"probe config {name} must contain absolute paths"
            )
    relative_forbidden = document["relative_forbidden"]
    if (
        not isinstance(relative_forbidden, str)
        or not relative_forbidden
        or os.path.isabs(relative_forbidden)
    ):
        raise RuntimeError(
            "probe config relative_forbidden must be relative"
        )
    prior_raw_bundle = document["prior_raw_bundle"]
    if (
        not isinstance(prior_raw_bundle, str)
        or not os.path.isabs(prior_raw_bundle)
        or prior_raw_bundle not in document["forbidden_paths"]
    ):
        raise RuntimeError(
            "probe config prior_raw_bundle must be a forbidden path"
        )
    expected_environment = document["expected_environment"]
    if (
        type(expected_environment) is not dict
        or not expected_environment
        or any(
            type(name) is not str
            or not name
            or "=" in name
            or "\x00" in name
            or type(value) is not str
            or "\x00" in value
            for name, value in expected_environment.items()
        )
    ):
        raise RuntimeError(
            "probe config expected_environment is invalid"
        )
    expected_cmdline = document["expected_cmdline"]
    if (
        type(expected_cmdline) is not list
        or not expected_cmdline
        or any(
            type(item) is not str
            or not item
            or "\x00" in item
            for item in expected_cmdline
        )
        or not os.path.isabs(expected_cmdline[0])
        or expected_cmdline[0] == "/"
        or os.path.normpath(expected_cmdline[0]) != expected_cmdline[0]
        or "//" in expected_cmdline[0]
    ):
        raise RuntimeError("probe config expected_cmdline is invalid")
    tcp_port = document["tcp_port"]
    if (
        isinstance(tcp_port, bool)
        or not isinstance(tcp_port, int)
        or not 1 <= tcp_port <= 65535
    ):
        raise RuntimeError("probe config tcp_port is invalid")
    abstract_name_hex = document["abstract_name_hex"]
    if not isinstance(abstract_name_hex, str) or not abstract_name_hex:
        raise RuntimeError("probe config abstract_name_hex is invalid")
    try:
        bytes.fromhex(abstract_name_hex)
    except ValueError as exc:
        raise RuntimeError(
            "probe config abstract_name_hex is invalid"
        ) from exc
    return document


def _read_denied(path: str) -> str:
    try:
        with open(path, "rb") as handle:
            handle.read(1)
    except OSError as exc:
        return _errno_name(exc.errno)
    return "READABLE"


def _visible_fds() -> list[int]:
    values: list[int] = []
    for raw in os.listdir("/proc/self/fd"):
        if not raw.isdecimal():
            continue
        fd = int(raw, 10)
        try:
            os.fstat(fd)
        except OSError:
            continue
        values.append(fd)
    return sorted(values)


def _visible_pids() -> list[int]:
    return sorted(
        int(raw, 10)
        for raw in os.listdir("/proc")
        if raw.isdecimal()
    )


def _read_openat(directory_fd: int, relative_path: str) -> str:
    try:
        fd = os.open(
            relative_path,
            os.O_RDONLY | os.O_CLOEXEC,
            dir_fd=directory_fd,
        )
    except OSError as exc:
        return _errno_name(exc.errno)
    try:
        try:
            os.read(fd, 1)
        except OSError as exc:
            return _errno_name(exc.errno)
        return "READABLE"
    finally:
        os.close(fd)


def _probe_openat_escapes(
    directory_authorities: list[str],
    forbidden_paths: list[str],
) -> dict[str, object]:
    observations: dict[str, object] = {}
    for authority in directory_authorities:
        authority_fd: int | None = None
        parent_fd: int | None = None
        try:
            authority_fd = os.open(
                authority,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
            )
            parent_fd = os.open(
                "..",
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
                dir_fd=authority_fd,
            )
            parent_path = os.path.dirname(authority)
            observations[authority] = {
                "parent_open": "OPENED",
                "forbidden_results": {
                    forbidden: _read_openat(
                        parent_fd,
                        os.path.relpath(forbidden, start=parent_path),
                    )
                    for forbidden in forbidden_paths
                },
            }
        except OSError as exc:
            observations[authority] = {
                "parent_open": _errno_name(exc.errno),
                "forbidden_results": {
                    forbidden: "NOT_ATTEMPTED"
                    for forbidden in forbidden_paths
                },
            }
        finally:
            if parent_fd is not None:
                os.close(parent_fd)
            if authority_fd is not None:
                os.close(authority_fd)
    return observations


def _proc_fd_inventory(pids: list[int]) -> dict[str, list[dict[str, object]]]:
    inventory: dict[str, list[dict[str, object]]] = {}
    for pid in pids:
        fd_root = f"/proc/{pid}/fd"
        rows: list[dict[str, object]] = []
        for raw_fd in sorted(
            os.listdir(fd_root),
            key=lambda value: (
                not value.isdecimal(),
                int(value, 10) if value.isdecimal() else value,
            ),
        ):
            if not raw_fd.isdecimal():
                continue
            fd_path = f"{fd_root}/{raw_fd}"
            try:
                status = os.stat(fd_path)
                target = os.readlink(fd_path)
            except OSError as exc:
                try:
                    os.lstat(fd_path)
                except FileNotFoundError:
                    # The descriptor used by listdir is visible briefly in
                    # procfs but is already closed before inspection.
                    continue
                except OSError as repeated:
                    raise RuntimeError(
                        "visible proc descriptor cannot be revalidated"
                    ) from repeated
                raise RuntimeError(
                    "visible proc descriptor cannot be inspected"
                ) from exc
            rows.append(
                {
                    "fd": int(raw_fd, 10),
                    "mode": status.st_mode,
                    "target": target,
                }
            )
        inventory[str(pid)] = rows
    return inventory


def _probe_pidfd_getfd(
    inventory: dict[str, list[dict[str, object]]],
) -> dict[str, str]:
    observations: dict[str, str] = {}
    for raw_pid, rows in inventory.items():
        pid = int(raw_pid, 10)
        target_fds = [int(row["fd"]) for row in rows]
        if not hasattr(os, "pidfd_open"):
            for target_fd in target_fds:
                observations[f"{pid}:{target_fd}"] = "UNAVAILABLE"
            continue
        try:
            pidfd = os.pidfd_open(pid, 0)
        except OSError as exc:
            result = f"PIDFD_OPEN_{_errno_name(exc.errno)}"
            for target_fd in target_fds:
                observations[f"{pid}:{target_fd}"] = result
            continue
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            for target_fd in target_fds:
                ctypes.set_errno(0)
                duplicate = libc.syscall(
                    ctypes.c_long(_PIDFD_GETFD_SYSCALL),
                    ctypes.c_int(pidfd),
                    ctypes.c_int(target_fd),
                    ctypes.c_uint(0),
                )
                if duplicate >= 0:
                    os.close(duplicate)
                    result = "ALLOWED"
                else:
                    result = _errno_name(ctypes.get_errno())
                observations[f"{pid}:{target_fd}"] = result
        finally:
            os.close(pidfd)
    return observations


def _probe_ptrace(pids: list[int]) -> dict[str, str]:
    libc = ctypes.CDLL(None, use_errno=True)
    observations: dict[str, str] = {}
    for pid in pids:
        ctypes.set_errno(0)
        result = libc.ptrace(
            ctypes.c_ulong(_PTRACE_ATTACH),
            ctypes.c_ulong(pid),
            ctypes.c_void_p(),
            ctypes.c_void_p(),
        )
        if result == 0:
            wait_failure: str | None = None
            detach_failure: str | None = None
            try:
                while True:
                    try:
                        waited_pid, wait_status = os.waitpid(pid, 0)
                        break
                    except InterruptedError:
                        continue
                if waited_pid != pid:
                    wait_failure = "WAITPID_WRONG_TARGET"
                elif not os.WIFSTOPPED(wait_status):
                    wait_failure = "WAITPID_NOT_STOPPED"
            except OSError as exc:
                wait_failure = f"WAITPID_{_errno_name(exc.errno)}"
            finally:
                ctypes.set_errno(0)
                detach_result = libc.ptrace(
                    ctypes.c_ulong(_PTRACE_DETACH),
                    ctypes.c_ulong(pid),
                    ctypes.c_void_p(),
                    ctypes.c_void_p(),
                )
                if detach_result != 0:
                    detach_failure = (
                        f"DETACH_{_errno_name(ctypes.get_errno())}"
                    )
            if detach_failure is not None:
                observations[str(pid)] = f"ALLOWED_{detach_failure}"
            elif wait_failure is not None:
                observations[str(pid)] = f"ALLOWED_{wait_failure}"
            else:
                observations[str(pid)] = "ALLOWED"
        else:
            observations[str(pid)] = _errno_name(ctypes.get_errno())
    return observations


def _read_bounded(path: str) -> bytes:
    with open(path, "rb") as handle:
        payload = handle.read(_MAX_PROC_DISCLOSURE_BYTES + 1)
    if len(payload) > _MAX_PROC_DISCLOSURE_BYTES:
        raise RuntimeError(f"{path} exceeds the disclosure probe limit")
    return payload


def _probe_self_memory(target_pid: int) -> dict[str, object]:
    if target_pid != os.getpid():
        raise RuntimeError("self-memory probe target is not the provider")
    marker = b"provider-isolation-self-memory-v1"
    buffer = ctypes.create_string_buffer(marker)
    try:
        descriptor = os.open(
            f"/proc/{target_pid}/mem",
            os.O_RDONLY | os.O_CLOEXEC,
        )
    except OSError as exc:
        return {
            "address_class": "provider_owned_marker",
            "bytes_read": 0,
            "marker_match": False,
            "status": _errno_name(exc.errno),
            "target_pid": target_pid,
        }
    try:
        try:
            payload = os.pread(
                descriptor,
                len(marker),
                ctypes.addressof(buffer),
            )
        except OSError as exc:
            return {
                "address_class": "provider_owned_marker",
                "bytes_read": 0,
                "marker_match": False,
                "status": _errno_name(exc.errno),
                "target_pid": target_pid,
            }
    finally:
        os.close(descriptor)
    return {
        "address_class": "provider_owned_marker",
        "bytes_read": len(payload),
        "marker_match": payload == marker,
        "status": "READABLE",
        "target_pid": target_pid,
    }


def _probe_process_disclosure(
    *,
    pids: list[int],
    inventory: dict[str, list[dict[str, object]]],
    forbidden_paths: list[str],
) -> dict[str, object]:
    environ = _read_bounded("/proc/1/environ")
    cmdline_payload = _read_bounded("/proc/1/cmdline")
    environ_rows = [
        row for row in environ.split(b"\x00") if row
    ]
    environment: dict[str, str] = {}
    for row in environ_rows:
        name, separator, value = row.partition(b"=")
        if not separator:
            raise RuntimeError("provider environment row lacks a value")
        decoded_name = name.decode("utf-8", errors="strict")
        if decoded_name in environment:
            raise RuntimeError("provider environment contains a duplicate name")
        environment[decoded_name] = value.decode("utf-8", errors="strict")
    cmdline = [
        row.decode("utf-8", errors="replace")
        for row in cmdline_payload.split(b"\x00")
        if row
    ]
    return {
        "pidfd_getfd": _probe_pidfd_getfd(inventory),
        "ptrace_attach": _probe_ptrace(pids),
        "proc_mem": _probe_self_memory(os.getpid()),
        "cwd": os.readlink("/proc/1/cwd"),
        "root": os.readlink("/proc/1/root"),
        "environ": environment,
        "environ_names": sorted(environment),
        "environ_forbidden_hits": sorted(
            forbidden
            for forbidden in forbidden_paths
            if os.fsencode(forbidden) in environ
        ),
        "cmdline": cmdline,
        "cmdline_forbidden_hits": sorted(
            forbidden
            for forbidden in forbidden_paths
            if os.fsencode(forbidden) in cmdline_payload
        ),
    }


def _capability_verdict(record: dict[str, object]) -> str:
    try:
        expected_environment = record["expected_environment"]
        expected_cmdline = record["expected_cmdline"]
        if (
            type(expected_environment) is not dict
            or not expected_environment
            or type(expected_cmdline) is not list
            or not expected_cmdline
        ):
            return "failed"
        if (
            record["fds"] != [0, 1, 2]
            or record["pids"] != [1]
            or record["prior_raw_bundle_result"] == "READABLE"
            or record["escape_result"] == "READABLE"
            or record["relative_escape_result"] == "READABLE"
        ):
            return "failed"
        denied_reads = record["denied_reads"]
        if not isinstance(denied_reads, dict) or any(
            value == "READABLE" for value in denied_reads.values()
        ):
            return "failed"
        openat = record["openat_escape_attempts"]
        if not isinstance(openat, dict) or any(
            value == "READABLE"
            for observation in openat.values()
            for value in observation["forbidden_results"].values()
        ):
            return "failed"
        inventory = record["proc_fd_inventory"]
        if (
            not isinstance(inventory, dict)
            or set(inventory) != {"1"}
            or [row["fd"] for row in inventory["1"]] != [0, 1, 2]
        ):
            return "failed"
        disclosure = record["process_disclosure"]
        if (
            set(disclosure["pidfd_getfd"])
            != {f"1:{descriptor}" for descriptor in (0, 1, 2)}
            or any(
                value.startswith("ALLOWED")
                for value in disclosure["ptrace_attach"].values()
            )
            or disclosure["cwd"] != record["cwd"]
            or disclosure["root"] != "/"
            or disclosure["environ"] != expected_environment
            or disclosure["environ_names"] != sorted(expected_environment)
            or disclosure["cmdline"] != expected_cmdline
            or disclosure["environ_forbidden_hits"]
            or disclosure["cmdline_forbidden_hits"]
        ):
            return "failed"
        proc_mem = disclosure["proc_mem"]
        if (
            not isinstance(proc_mem, dict)
            or proc_mem["target_pid"] != 1
            or proc_mem["address_class"] != "provider_owned_marker"
            or (
                proc_mem["status"] == "READABLE"
                and (
                    proc_mem["marker_match"] is not True
                    or proc_mem["bytes_read"] != 33
                )
            )
            or (
                proc_mem["status"] != "READABLE"
                and (
                    proc_mem["marker_match"] is not False
                    or proc_mem["bytes_read"] != 0
                )
            )
        ):
            return "failed"
        terminal = record["terminal_injection"]
        if (
            set(terminal) != {"fd:0", "fd:1", "fd:2", "/dev/tty"}
            or any(
                set(operation) != {"tiocsti", "tiocsctty"}
                or any(value == "ALLOWED" for value in operation.values())
                for operation in terminal.values()
            )
        ):
            return "failed"
    except (KeyError, TypeError):
        return "failed"
    return "passed"


def _ioctl_result(fd: int, request: int, argument: object) -> str:
    try:
        fcntl.ioctl(fd, request, argument)
    except OSError as exc:
        return _errno_name(exc.errno)
    return "ALLOWED"


def _probe_terminal_injection() -> dict[str, dict[str, str]]:
    observations = {
        f"fd:{fd}": {
            "tiocsti": _ioctl_result(fd, _TIOCSTI, b"\x00"),
            "tiocsctty": _ioctl_result(fd, _TIOCSCTTY, 0),
        }
        for fd in (0, 1, 2)
    }
    try:
        tty_fd = os.open("/dev/tty", os.O_RDWR | os.O_CLOEXEC)
    except OSError as exc:
        result = _errno_name(exc.errno)
        observations["/dev/tty"] = {
            "tiocsti": result,
            "tiocsctty": result,
        }
    else:
        try:
            observations["/dev/tty"] = {
                "tiocsti": _ioctl_result(tty_fd, _TIOCSTI, b"\x00"),
                "tiocsctty": _ioctl_result(tty_fd, _TIOCSCTTY, 0),
            }
        finally:
            os.close(tty_fd)
    return observations


def _status_fields() -> dict[str, str]:
    selected = {
        "CapAmb",
        "CapBnd",
        "CapEff",
        "CapInh",
        "CapPrm",
        "Gid",
        "Groups",
        "NoNewPrivs",
        "Uid",
    }
    values: dict[str, str] = {}
    for line in Path("/proc/self/status").read_text(
        encoding="ascii",
        errors="strict",
    ).splitlines():
        name, separator, payload = line.partition(":")
        if separator and name in selected:
            values[name] = payload.strip()
    return values


def _single_id_map(path: str) -> list[int]:
    rows = Path(path).read_text(
        encoding="ascii",
        errors="strict",
    ).splitlines()
    if len(rows) != 1:
        raise RuntimeError("identity map is not a single row")
    fields = rows[0].split()
    if len(fields) != 3 or any(not field.isdecimal() for field in fields):
        raise RuntimeError("identity map row is malformed")
    return [int(field, 10) for field in fields]


def _denied_syscall(number: int, argument: int = 0) -> str:
    libc = ctypes.CDLL(None, use_errno=True)
    ctypes.set_errno(0)
    result = libc.syscall(
        ctypes.c_long(number),
        ctypes.c_ulong(argument),
        ctypes.c_void_p(),
        ctypes.c_void_p(),
        ctypes.c_void_p(),
        ctypes.c_void_p(),
    )
    if result >= 0:
        return "ALLOWED"
    value = ctypes.get_errno()
    return _errno_name(value)


def _probe_tcp(address: str, port: int) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(0.2)
        result = client.connect_ex((address, port))
    if result == 0:
        return "REACHABLE"
    return _errno_name(result)


def _probe_abstract(name_hex: str) -> str:
    name = bytes.fromhex(name_hex)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(0.2)
        result = client.connect_ex(b"\x00" + name)
    if result == 0:
        return "REACHABLE"
    return _errno_name(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-config", required=True)
    args = parser.parse_args()
    config = _load_probe_config(args.probe_config)
    forbidden_paths = config["forbidden_paths"]
    directory_authorities = config["directory_authorities"]
    assert isinstance(forbidden_paths, list)
    assert isinstance(directory_authorities, list)
    assert all(isinstance(path, str) for path in forbidden_paths)
    assert all(isinstance(path, str) for path in directory_authorities)
    prior_raw_bundle = config["prior_raw_bundle"]
    relative_forbidden = config["relative_forbidden"]
    tcp_port = config["tcp_port"]
    abstract_name_hex = config["abstract_name_hex"]
    expected_environment = config["expected_environment"]
    expected_cmdline = config["expected_cmdline"]
    assert isinstance(prior_raw_bundle, str)
    assert isinstance(relative_forbidden, str)
    assert isinstance(tcp_port, int)
    assert isinstance(abstract_name_hex, str)
    assert isinstance(expected_environment, dict)
    assert isinstance(expected_cmdline, list)
    network_observations = {
        "host_loopback_tcp": _probe_tcp("127.0.0.1", tcp_port),
        "host_abstract_unix": _probe_abstract(abstract_name_hex),
        "cloud_metadata": _probe_tcp("169.254.169.254", 80),
    }
    if (
        network_observations["host_loopback_tcp"] != "REACHABLE"
        or network_observations["host_abstract_unix"] != "REACHABLE"
        or network_observations["cloud_metadata"] == "REACHABLE"
    ):
        return 97
    candidate = Path.cwd()
    candidate_write = candidate / "provider-write.txt"
    candidate_write.write_text("provider-owned\n", encoding="utf-8")

    escape = candidate / "provider-escape-link"
    if forbidden_paths:
        escape.symlink_to(forbidden_paths[0])
        try:
            escape_result = _read_denied(os.fspath(escape))
        finally:
            escape.unlink()
    else:
        escape_result = "NOT_EXERCISED"

    relative_escape = candidate / "provider-relative-escape-link"
    relative_escape.symlink_to(relative_forbidden)
    try:
        relative_escape_result = _read_denied(os.fspath(relative_escape))
    finally:
        relative_escape.unlink()

    denied_reads = {
        path: _read_denied(path)
        for path in sorted(forbidden_paths)
    }
    openat_escape_attempts = _probe_openat_escapes(
        directory_authorities,
        forbidden_paths,
    )
    pids = _visible_pids()
    proc_fd_inventory = _proc_fd_inventory(pids)
    process_disclosure = _probe_process_disclosure(
        pids=pids,
        inventory=proc_fd_inventory,
        forbidden_paths=forbidden_paths,
    )
    terminal_injection = _probe_terminal_injection()
    tty_result = _read_denied("/dev/tty")
    runtime_root = candidate / ".orchestrate"
    runtime_entries = sorted(
        entry.name for entry in runtime_root.iterdir()
    )
    record = {
        "schema_version": "provider_isolation_i0_probe.v1",
        "candidate_write": candidate_write.read_text(encoding="utf-8"),
        "cwd": os.fspath(candidate),
        "denied_reads": denied_reads,
        "environment_names": sorted(os.environ),
        "escape_result": escape_result,
        "expected_cmdline": list(expected_cmdline),
        "expected_environment": dict(expected_environment),
        "fds": _visible_fds(),
        "hostname": os.uname().nodename,
        "gid_map": _single_id_map("/proc/self/gid_map"),
        "groups": os.getgroups(),
        "key_syscalls": {
            "add_key": _denied_syscall(248),
            "keyctl": _denied_syscall(250),
            "request_key": _denied_syscall(249),
        },
        "nested_user_namespace": _denied_syscall(272, 0x10000000),
        "network_namespace_identity": {
            "device": os.stat("/proc/self/ns/net").st_dev,
            "inode": os.stat("/proc/self/ns/net").st_ino,
        },
        "network_observations": network_observations,
        "openat_escape_attempts": openat_escape_attempts,
        "pids": pids,
        "prior_raw_bundle_result": _read_denied(prior_raw_bundle),
        "proc_fd_inventory": proc_fd_inventory,
        "process_disclosure": process_disclosure,
        "process_identity": {
            "pid": os.getpid(),
            "process_group": os.getpgrp(),
            "session": os.getsid(0),
        },
        "relative_escape_result": relative_escape_result,
        "runtime_entries": runtime_entries,
        "overflow_gid": int(
            Path("/proc/sys/kernel/overflowgid")
            .read_text(encoding="ascii", errors="strict")
            .strip()
        ),
        "setgroups": Path("/proc/self/setgroups")
        .read_text(encoding="ascii", errors="strict")
        .strip(),
        "status": _status_fields(),
        "terminal_injection": terminal_injection,
        "tty_result": tty_result,
        "uid_map": _single_id_map("/proc/self/uid_map"),
    }
    record["capability_verdict"] = _capability_verdict(record)
    encoded = (
        json.dumps(record, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    output_value = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE")
    if output_value is not None:
        Path(output_value).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if record["capability_verdict"] == "passed" else 98


if __name__ == "__main__":
    raise SystemExit(main())
