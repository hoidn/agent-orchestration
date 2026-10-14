"""Guest-side escape probe. Prints one JSON object; never reads host files (it cannot)."""
import errno, json, os, socket, sys
host = json.loads(sys.argv[1])
r = {}
def attempt(name, fn):
    try:
        r[name] = ["ALLOWED", repr(fn())[:200]]
    except OSError as exc:
        r[name] = ["DENIED", errno.errorcode.get(exc.errno, str(exc.errno))]
for label, path in host["absent_paths"].items():
    r["exists:" + label] = os.path.lexists(path)
attempt("tcp_1.1.1.1:53", lambda: socket.create_connection(("1.1.1.1", 53), timeout=2))
attempt("dns_example.com", lambda: socket.getaddrinfo("example.com", 443))
r["interfaces"] = [line.split(":")[0].strip() for line in open("/proc/net/dev").read().splitlines()[2:]]
def abstract():
    s = socket.socket(socket.AF_UNIX); s.settimeout(2); s.connect("\0" + host["abstract_socket"]); return "connected"
attempt("host_abstract_socket", abstract)
attempt("write_rootfs", lambda: open("/usr/local/bin/injected", "w"))
attempt("hardlink_rootfs_into_workspace", lambda: os.link(host["python_pin"], "/workspace/hl"))
attempt("hardlink_result_into_workspace", lambda: (open("/result/x", "w").close(), os.link("/result/x", "/workspace/hl2")))
attempt("unshare_user", lambda: os.unshare(os.CLONE_NEWUSER))
attempt("alternates_target", lambda: os.listdir(open("/workspace/.git/objects/info/alternates").read().strip()))
os.symlink("/etc/hostname", "/workspace/leak")
os.link("/workspace/hello.txt", "/workspace/hello-hardlink")
with open("/workspace/.git/hooks/post-checkout", "w") as hook:
    hook.write("#!/bin/sh\ntouch /tmp/hook-ran\n")
os.chmod("/workspace/.git/hooks/post-checkout", 0o755)
status = dict(line.split(":\t", 1) for line in open("/proc/self/status").read().splitlines() if ":\t" in line)
r["CapEff"], r["CapBnd"], r["NoNewPrivs"] = status["CapEff"].strip(), status["CapBnd"].strip(), status["NoNewPrivs"].strip()
r["uid"] = os.getuid()
r["open_fds"] = sorted(int(fd) for fd in os.listdir("/proc/self/fd"))
r["environ"] = sorted(os.environ)
r["mounts"] = sorted({line.split()[4] for line in open("/proc/self/mountinfo")})
r["visible_pids"] = sorted(int(p) for p in os.listdir("/proc") if p.isdigit())
print(json.dumps(r))
