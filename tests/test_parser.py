"""Offline unit tests for the proxy-list parser (no network needed)."""

from ceen.core.proxies.entry import parse_proxy_line, load_proxy_list

CASES = [
    ("1.2.3.4:8080", ("http", "1.2.3.4", 8080, "", "")),
    ("socks5://5.6.7.8:1080", ("socks5", "5.6.7.8", 1080, "", "")),
    ("socks4://9.9.9.9:4153", ("socks4", "9.9.9.9", 4153, "", "")),
    ("user:pw@10.0.0.1:3128", ("http", "10.0.0.1", 3128, "user", "pw")),
    ("socks5://u:p@4.4.4.4:1080",
     ("socks5", "4.4.4.4", 1080, "u", "p")),
    ("[::1]:8080", ("http", "::1", 8080, "", "")),
    ("# comment", None),
    ("", None),
    ("garbage line!!", None),
    ("1.2.3.999:80", None),            # impossible IP octet
    ("1.2.3.4:99999", None),           # impossible port
]


def run() -> bool:
    """Run every case; print a friendly PASS/FAIL line; return overall ok."""
    ok = True
    for line, want in CASES:
        got = parse_proxy_line(line)
        if want is None:
            good = got is None
        else:
            good = got is not None and (
                got.scheme, got.host, got.port, got.user, got.password) == want
        print(f"  [{'ok' if good else 'FAIL'}] parse {line!r}")
        ok = ok and good

    # real file: parse + dedupe
    entries, skipped = load_proxy_list("free-proxy-list.txt")
    hosts = {(e.kind, e.host, e.port) for e in entries}
    print(f"  [{'ok' if len(hosts) == len(entries) else 'FAIL'}] "
          f"real list: {len(entries)} unique ({skipped} skipped)")
    ok = ok and len(hosts) == len(entries) and len(entries) > 0
    print(f"  parser checks: {'PASS' if ok else 'FAIL'}")
    return ok
