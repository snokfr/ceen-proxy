"""Offline rotator test: fake upstream proxies + a real request through them.

No real internet needed — two fake HTTP proxies run on localhost; one is
broken on purpose so we can prove the rotator benches it and fails over
to the healthy one.
"""

import socket
import threading
import time
import urllib.request

from ceen.core.proxies.entry import ProxyEntry
from ceen.core.tunnel.pool import ProxyPool
from ceen.core.tunnel.rotator import RotatorServer


def _fake_proxy(port: int, fail_first: bool) -> threading.Thread:
    """A pretend HTTP proxy: answers GETs with a tiny page (or dies)."""
    hits = {"n": 0}

    def handle(conn: socket.socket) -> None:
        try:
            conn.settimeout(4)
            conn.recv(65536)
            hits["n"] += 1
            if fail_first and hits["n"] == 1:
                conn.close()                    # simulate a dead upstream
                return
            body = b"hello from fake proxy"
            conn.sendall(b"HTTP/1.0 200 OK\r\nContent-Length: "
                         + str(len(body)).encode() + b"\r\n\r\n" + body)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def serve() -> None:
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(4)
        srv.settimeout(6)
        try:
            while True:
                c, _ = srv.accept()
                threading.Thread(target=handle, args=(c,), daemon=True).start()
        except socket.timeout:
            pass
        finally:
            srv.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return t


def run() -> bool:
    """Start fakes, send one request through the rotator, check results."""
    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        print(f"  [{'ok' if cond else 'FAIL'}] {msg}")
        ok = ok and cond

    print("[Ceen Proxy] rotator self-test")
    _fake_proxy(9701, fail_first=False)
    _fake_proxy(9702, fail_first=True)

    # 9702 listed first -> the rotator should bench it and use 9701
    a = ProxyEntry("http", "HTTP", "127.0.0.1", 9702)
    b = ProxyEntry("http", "HTTP", "127.0.0.1", 9701)
    pool = ProxyPool([a, b])
    rot = RotatorServer(9871, pool, timeout=3.0)
    rot.start()
    time.sleep(0.3)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(
            {"http": "http://127.0.0.1:9871"}))
        with opener.open("http://example.invalid/ping", timeout=8) as r:
            body = r.read()
        check(b"hello from fake proxy" in body, "request served via rotation")
        check(len(pool) == 1, "dead upstream benched automatically")
        time.sleep(0.5)                      # let byte accounting settle
        req, up, down, _ = rot.stats()
        check(req >= 1 and down > 0, f"stats tracked ({req} req, {down} B)")
    except Exception as exc:  # noqa: BLE001
        check(False, f"request through rotator failed: {exc}")
    finally:
        rot.stop()
        rot.join(timeout=3)
    check(not rot.is_alive(), "rotator stops cleanly")
    print(f"  rotator checks: {'PASS' if ok else 'FAIL'}")
    return ok
