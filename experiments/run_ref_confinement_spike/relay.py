"""In-sandbox relay: loopback TCP -> bound gateway unix socket. Guest code, not trusted."""
import socket, sys, threading
PORT, SOCKET = int(sys.argv[1]), sys.argv[2]
def pump(src, dst):
    try:
        while data := src.recv(65536):
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try: s.shutdown(socket.SHUT_RDWR)
            except OSError: pass
server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", PORT))
server.listen(16)
while True:
    client, _ = server.accept()
    upstream = socket.socket(socket.AF_UNIX)
    upstream.connect(SOCKET)
    threading.Thread(target=pump, args=(client, upstream), daemon=True).start()
    threading.Thread(target=pump, args=(upstream, client), daemon=True).start()
