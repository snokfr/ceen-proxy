"""Offline unit tests for the tunnel pool (rotation, grouping, backups)."""

from ceen.core.proxies.entry import ProxyEntry
from ceen.core.tunnel.pool import ProxyPool, group_by_country


def _e(host: str, port: int, cc: str, latency) -> ProxyEntry:
    """Build a proxy that pretends it was already checked (alive)."""
    e = ProxyEntry("socks5", "SOCKS5", host, port)
    e.alive, e.latency, e.exit_cc, e.country = True, latency, cc, cc
    return e


def run() -> bool:
    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        print(f"  [{'ok' if cond else 'FAIL'}] {msg}")
        ok = ok and cond

    print("[Ceen Proxy] pool self-test")
    # round-robin + benching + sticky
    pool = ProxyPool([_e("1.1.1.1", 80, "US", 100), _e("2.2.2.2", 80, "DE", 50)])
    check(pool.next().host == "2.2.2.2", "fastest server served first")
    pool.disable(pool.next())
    check(len(pool) == 1, "disabled server removed from rotation")
    pool.set_sticky(pool.snapshot()[0])
    check(pool.next().host == pool.next().host, "sticky server always wins")

    # country grouping: fastest-first inside each group
    groups = group_by_country([
        _e("3.3.3.3", 1, "US", 900), _e("4.4.4.4", 2, "US", 120),
        _e("5.5.5.5", 3, "DE", 400)])
    by_cc = {cc: srv for _n, cc, srv in groups}
    check(by_cc["US"][0].host == "4.4.4.4", "group sorts servers fastest-first")
    check(groups[0][1] == "US", "groups sorted by their best latency")

    # backups (starred servers) lead the rotation
    pool2 = ProxyPool([_e("6.6.6.6", 1, "US", 100), _e("7.7.7.7", 2, "US", 200)])
    pool2.reorder({"socks5://7.7.7.7:2"})
    check(pool2.next().host == "7.7.7.7", "starred backup rotates first")

    print(f"  pool checks: {'PASS' if ok else 'FAIL'}")
    return ok
