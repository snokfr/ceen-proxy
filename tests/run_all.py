"""Test runner: python -m tests.run_all — every offline self-test in one go."""

import sys

import tests.test_connect_path
import tests.test_parser
import tests.test_pool
import tests.test_rotator
import tests.test_settings


def main() -> int:
    print("[Ceen Proxy] self-tests")
    ok = True
    for mod in (tests.test_connect_path, tests.test_parser,
                tests.test_pool, tests.test_rotator, tests.test_settings):
        try:
            ok = mod.run() and ok
        except Exception as exc:  # noqa: BLE001 — report, don't crash
            print(f"  [FAIL] {mod.__name__} raised {exc!r}")
            ok = False
    print(f"\n  overall: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
