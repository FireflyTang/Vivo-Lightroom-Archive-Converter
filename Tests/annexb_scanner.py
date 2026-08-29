#!/usr/bin/env python3
"""Regression checks for the native-find streaming Annex-B scanner."""
import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Engine"))
import mux_exact


def main():
    chunk = 4 * 1024 * 1024
    first = b"\x40\x01" + b"a" * (chunk - 8)
    second = b"\x46\x01\x50" + b"b" * 31
    third = b"\x26\x01" + b"c" * 127
    expected = [first, second, third]
    # The second three-byte start code begins two bytes before the scanner's
    # 4 MiB read boundary.  The final NAL uses a four-byte start code.
    raw = b"\0\0\0\1" + first + b"\0\0\1" + second + b"\0\0\0\1" + third
    with tempfile.TemporaryDirectory(prefix="vac-annexb-") as td:
        path = Path(td) / "mixed.hevc"
        path.write_bytes(raw)
        actual = list(mux_exact.annexb_nals(path))
    assert actual == expected
    digest = hashlib.sha256(b"".join(actual)).hexdigest()
    print(f"PASS mixed 3/4-byte and cross-chunk Annex-B boundaries: {digest}")


if __name__ == "__main__":
    main()
