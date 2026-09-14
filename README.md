# ⏻ Ceen Proxy 3.0

A proxy checker **and** VPN-style tunnel in plain Python — now on
**Dear PyGui** (GPU-rendered, instant UI) in a dark **Windscribe-style**
window: power button, big exit-location line, flag-emoji country list.
Test your free-proxy list, then actually *browse through* the working
servers. Requires `pip install dearpygui` (the only dependency).

## Run it

```bash
python proxy_checker.py            # the app (window opens instantly, auto-scans)
python proxy_checker.py --selftest # offline self-tests (parser/pool/rotator)
python proxy_checker.py --smoke    # headless engine test (scan+connect)
python proxy_checker.py --liveui   # real-window test of the connect flow
python proxy_checker.py --debug    # verbose logs in the console too
```

## What it does

**● CONNECT** — the VPN face:
- the gradient power ring is the ONLY switch: click to connect, click
  again to disconnect. It glows (orbiting light, breathing, ripples on
  tap) — grey off, amber spinning while connecting, green when protected
- **Windows is switched to the tunnel automatically** on connect, so
  your IP verifiably changes on ip-check sites; restored on disconnect
- the big line under the ring ALWAYS mirrors the real tunnel (exit
  country + verified exit IP; your direct IP when unprotected) — and a
  live traffic sparkline dances next to the ring while data flows
- country list, fastest-first; tap a country to pin its fastest server
- alive servers usually appear ~4s after launch (fast port pre-check)
- a watchdog probes the tunnel every 10s: if every server dies, Ceen
  disconnects itself instead of silently going dark
- crash guards: stale "dead tunnel" proxies are cleared at startup, and
  on ANY exit (even a crash) your internet settings are restored — the
  "lost wifi" failure mode is engineered out

**▦ CHECKER** — the engine room:
- auto-scan on startup; the TCP pre-filter kills dead ports in ~1.5s
  so the full 778-proxy list finishes in ~15-25 seconds
- sortable table, alive-only filter, search, COPY/EXPORT, LOG viewer

## Project layout (every file ≤ 350 lines, commented for non-coders)

```
proxy_checker.py          5-line launcher
ceen/
  config.py               ports, paths, constants
  logging_setup.py        fresh log file per run + audits the last one
  core/                   the "brain" — no window code
    proxies/              what a proxy is + how to talk to one
      entry.py            ProxyEntry — one row of your list
      handshakes.py       raw SOCKS4/SOCKS5/HTTP-CONNECT conversations
      checker.py          the full "does this proxy work?" test
    scanning/scanner.py   test hundreds of proxies at once
      fastscan.py         the 1.5s TCP pre-check that skips dead ports
    tunnel/               your traffic's route out
      pool.py             working-server basket + country grouping
      rotator.py          the local tunnel on 127.0.0.1:8888
      pipes.py            the byte pumps that copy traffic through
      probe.py            "which country am I really in?"
  ui/                     the window (Dear PyGui, Windscribe-styled)
    theme.py bootstrap.py sparkline.py icon.py
    panel_connect.py panel_checker.py app.py behaviors.py
  utils/                  system-proxy/kill-switch + formatting helpers
tests/                    self-tests: python -m tests.run_all
```

## Logging (for easy debugging)

Every run creates `logs/ceen_proxy_<timestamp>.log`. The file keeps full
DEBUG detail (every proxy, every skip, every rotation); the console shows
just INFO. On startup the app **audits the previous run's log** and
prints how many warnings/errors it held, so problems never slip by.

## Build a standalone .exe (no Python needed)

```bash
pip install pyinstaller
pyinstaller CeenProxy.spec
```

Result: **`dist/CeenProxy.exe`** (~11 MB) — one file, custom icon, no
console, no Python required on the target PC. Copy `free-proxy-list.txt`
next to it (or set a list path in settings) and double-click. Logs and
exports are written next to the exe; settings stay in `~/.ceen_proxy.json`.

## Safety notes

**DNS privacy (remote DNS):** website names are never resolved on your
PC. Browsers hand hostnames to the local tunnel, which forwards the NAME
to the proxy — the proxy does the lookup, so your ISP's DNS servers only
ever see a connection to the proxy's IP. This holds for HTTP CONNECT,
SOCKS5 (domain address type) and SOCKS4a, and a guard test keeps local
resolver calls out of the engine. (Caveat: plain-HTTP sites are visible
to the proxy itself; HTTPS is encrypted end-to-end.)

- Free proxies can see unencrypted HTTP traffic; HTTPS stays
  end-to-end encrypted as usual.
- The Windows system-proxy switch is restored on disconnect, on normal
  exit, and even on crashes (atexit guard + startup stale-check).
- Kill switch: if every server dies mid-session, traffic is **blocked,
  never leaked**.
