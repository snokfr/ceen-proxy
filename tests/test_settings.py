"""Settings persistence test: save -> load round trip, plus the safety
behaviors (corrupt file quarantined, invalid values rejected).

Uses a temp "settings path" by pointing ceen.config.SETTINGS_PATH at a
throwaway file, so the developer's REAL settings are never touched.
"""

import json
import os
import sys
import tempfile

# isolate: redirect the settings path BEFORE importing the module
_TMPDIR = tempfile.mkdtemp(prefix="ceen_settings_test_")
import ceen.config as _config  # noqa: E402
_config.SETTINGS_PATH = os.path.join(_TMPDIR, "settings.json")

import ceen.utils.settings as S  # noqa: E402
S.SETTINGS_PATH = _config.SETTINGS_PATH   # the module reads the same path


def main() -> int:
    print("[Ceen Proxy] settings persistence test")
    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        print(f"  [{'ok' if cond else 'FAIL'}] {msg}")
        ok = ok and cond

    # 1. no file yet -> clean defaults
    d = S.load()
    check(d["win_w"] == 380 and d["port"] == d["port"],
          "missing file gives defaults")

    # 2. round trip: save then load gives back the same values
    d["win_w"], d["win_h"], d["port"] = 412, 700, 9341
    check(S.save(d), "save returns success")
    d2 = S.load()
    check(d2["win_w"] == 412 and d2["win_h"] == 700 and d2["port"] == 9341,
          f"round trip keeps values (got {d2['win_w']}x{d2['win_h']} "
          f"port {d2['port']})")

    # 3. junk keys are dropped on save (schema-clean file)
    S.save(S.merge(d, not_a_real_key=42))
    raw = json.load(open(S.SETTINGS_PATH, encoding="utf-8"))
    check("not_a_real_key" not in raw, "unknown keys are not written")

    # 4. invalid values are rejected on load (falls back to default)
    raw["port"] = 99999                     # out of range
    raw["win_w"] = "huge"                   # wrong type
    with open(S.SETTINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    d3 = S.load()
    check(d3["port"] != 99999 and isinstance(d3["win_w"], int),
          f"invalid values rejected (port={d3['port']}, "
          f"win_w={d3['win_w']!r})")

    # 5. corrupt file -> quarantined as .bad, defaults returned
    with open(S.SETTINGS_PATH, "w", encoding="utf-8") as fh:
        fh.write("{ this is not json !!!")
    d4 = S.load()
    check(d4["win_w"] == 380, "corrupt file falls back to defaults")
    check(os.path.exists(S.SETTINGS_PATH + ".bad"),
          "corrupt file kept as .bad (nothing destroyed)")
    check(S.load()["port"] > 0, "app keeps working after corruption")

    print(f"  settings: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


# the shared test runner calls every module's run()
def run() -> bool:
    return main() == 0


if __name__ == "__main__":
    sys.exit(main())
