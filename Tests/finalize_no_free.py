#!/usr/bin/env python3
"""Regression check for PyAV MP4 prefixes that contain no top-level free box."""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Engine"))
import finalize_mp4 as f


def box(kind, payload=b""):
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def main():
    encoder = box(b"\xa9too", box(b"data", b"\0" * 24))
    ilst = box(b"ilst", encoder)
    meta = box(b"meta", b"\0\0\0\0" + ilst)
    udta = box(b"udta", meta)
    prefix = bytearray(box(b"ftyp", b"isom\0\0\0\0isom") + box(b"moov", udta))
    original_size = len(prefix)

    result = f.remove_lavf(prefix)
    top = list(f.boxes(result))
    free = next(x for x in top if x[2] == b"free")
    moov = next(x for x in top if x[2] == b"moov")

    assert len(result) == original_size
    assert free[1] == len(encoder)
    assert b"\xa9too" not in bytes(result[moov[0]:moov[0] + moov[1]])
    print("PASS no-free PyAV prefix: encoder tag replaced by equal-size free box")


if __name__ == "__main__":
    main()
