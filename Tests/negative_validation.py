#!/usr/bin/env python3
"""Destructive-on-copies regression checks for the independent output validator."""
import json, mmap, shutil, struct, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Engine"))
import validate_output as v


def flip(path, offset, mask=1):
    with open(path, "r+b") as f:
        f.seek(offset); value = f.read(1)
        if not value: raise ValueError("mutation offset outside file")
        f.seek(offset); f.write(bytes([value[0] ^ mask]))


def validator(source, output):
    args = [sys.executable, str(ROOT / "Engine" / "validate_output.py"), str(source), str(output),
            "/opt/homebrew/bin/dovi_tool", "/opt/homebrew/bin/ffmpeg", "/opt/homebrew/bin/ffprobe", "cpu"]
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def expect_failure(source, good, name, mutate, needle):
    with tempfile.TemporaryDirectory(prefix="vac-negative-") as td:
        bad = Path(td) / good.name; shutil.copy2(good, bad); mutate(bad)
        result = validator(source, bad); text = result.stdout + result.stderr
        if result.returncode == 0 or needle not in text:
            raise AssertionError(f"{name} did not fail as expected ({needle!r}):\n{text[-3000:]}")
        print(f"PASS {name}: {needle}")


def uuid_mutation(path):
    mp4 = v.MappedMP4(path)
    try:
        box = next(x for x in mp4.top if x[2] == b"uuid" and bytes(mp4.b[x[0] + x[3]:x[0] + x[3] + 16]) != v.ARCHIVE_UUID)
        offset = box[0] + box[3] + 16
    finally: mp4.close()
    flip(path, offset)


def matrix_mutation(path):
    mp4 = v.MappedMP4(path)
    try:
        tk = v.child(mp4.b, mp4.track(b"vide"), b"tkhd"); q = tk[0] + tk[3]; offset = q + (52 if mp4.b[q] else 40)
    finally: mp4.close()
    flip(path, offset)


def packet_mutation(selector):
    def mutate(path):
        packet = v.packets("/opt/homebrew/bin/ffprobe", path, selector)[0]
        flip(path, int(packet["pos"]) + int(packet["size"]) - 1)
    return mutate


def temporal_mutation(path):
    packet = v.packets("/opt/homebrew/bin/ffprobe", path, "v:0")[0]
    pos, size = int(packet["pos"]), int(packet["size"])
    with open(path, "rb") as f: f.seek(pos); data = f.read(size)
    p = 0; target = None
    while p + 6 <= len(data):
        z = struct.unpack_from(">I", data, p)[0]
        if z < 2 or p + 4 + z > len(data): break
        nal = p + 4; ntype = (data[nal] >> 1) & 63
        if ntype <= 31: target = pos + nal + 1; break
        p += 4 + z
    if target is None: raise ValueError("no VCL NAL found in first packet")
    with open(path, "r+b") as f:
        f.seek(target); value = f.read(1); f.seek(target); f.write(bytes([(value[0] & 0xF8) | 2]))


def main(source, good):
    source, good = Path(source), Path(good)
    expect_failure(source, good, "unknown UUID byte", uuid_mutation, "UUID")
    expect_failure(source, good, "display matrix byte", matrix_mutation, "显示矩阵")
    expect_failure(source, good, "AAC payload byte", packet_mutation("a:0"), "AAC包内容")
    expect_failure(source, good, "EIS payload byte", packet_mutation("d:0"), "EIS包内容")
    expect_failure(source, good, "temporal-id bit", temporal_mutation, "temporal_id")


if __name__ == "__main__":
    main(*sys.argv[1:3])
