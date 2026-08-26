#!/usr/bin/env python3
import json, mmap, os, shutil, struct, subprocess, sys


def boxes(buf, start=0, end=None):
    end = len(buf) if end is None else end; p = start
    while p + 8 <= end:
        size = struct.unpack_from(">I", buf, p)[0]; typ = bytes(buf[p + 4:p + 8]); head = 8
        if size == 1: size = struct.unpack_from(">Q", buf, p + 8)[0]; head = 16
        elif size == 0: size = end - p
        if size < head or p + size > end: raise ValueError(f"bad box {typ!r} at {p}")
        yield p, size, typ, head; p += size


def children(buf, box):
    p, size, _, head = box
    return list(boxes(buf, p + head, p + size))


def child(buf, box, typ): return next(x for x in children(buf, box) if x[2] == typ)


def handler(buf, track):
    h = child(buf, child(buf, track, b"mdia"), b"hdlr")
    return bytes(buf[h[0] + 16:h[0] + 20])


def rewrite(raw, delta=0, replacements=None):
    data = bytearray(raw); pos = 0
    while True:
        a, b = data.find(b"stco", pos), data.find(b"co64", pos); choices = [x for x in (a, b) if x >= 4]
        if not choices: break
        marker = min(choices); start = marker - 4; typ = bytes(data[marker:marker + 4]); count = struct.unpack_from(">I", data, start + 12)[0]
        width = 4 if typ == b"stco" else 8; fmt = ">I" if width == 4 else ">Q"
        values = replacements if replacements is not None else [struct.unpack_from(fmt, data, start + 16 + i * width)[0] + delta for i in range(count)]
        if len(values) != count: raise ValueError("chunk count mismatch")
        for i, value in enumerate(values): struct.pack_into(fmt, data, start + 16 + i * width, value)
        pos = start + 16 + count * width
    return bytes(data)


def chunk_starts(track):
    marker = track.find(b"stsc"); start = marker - 4; count = struct.unpack_from(">I", track, start + 12)[0]
    entries = [struct.unpack_from(">III", track, start + 16 + i * 12) for i in range(count)]
    marker = track.find(b"stco"); marker = marker if marker >= 4 else track.find(b"co64")
    chunks = struct.unpack_from(">I", track, marker - 4 + 12)[0]
    starts = []; sample = 0; entry = 0
    for chunk in range(1, chunks + 1):
        while entry + 1 < len(entries) and entries[entry + 1][0] <= chunk: entry += 1
        starts.append(sample); sample += entries[entry][1]
    return starts, sample


def copy_range(src, dst, start, size):
    src.seek(start); remaining = size
    while remaining:
        data = src.read(min(remaining, 8 * 1024 * 1024))
        if not data: raise ValueError("input ended while copying MP4 box")
        dst.write(data); remaining -= len(data)


def main(src, base, dst):
    ffprobe = "/opt/homebrew/bin/ffprobe" if os.path.exists("/opt/homebrew/bin/ffprobe") else "ffprobe"
    info = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-select_streams", "d:0", "-show_packets", "-show_entries", "packet=pos,size", "-of", "json", src]))
    packet_refs = [(int(x["pos"]), int(x["size"])) for x in info["packets"]]
    with open(src, "rb") as sf, open(base, "rb") as bf:
        source = mmap.mmap(sf.fileno(), 0, access=mmap.ACCESS_READ); target = mmap.mmap(bf.fileno(), 0, access=mmap.ACCESS_READ)
        sm = next(x for x in boxes(source) if x[2] == b"moov"); dm = next(x for x in boxes(target) if x[2] == b"moov")
        et = next(x for x in children(source, sm) if x[2] == b"trak" and handler(source, x) == b"meta")
        eis = bytes(source[et[0]:et[0] + et[1]]); shift = len(eis)
        target_moov = rewrite(bytes(target[dm[0]:dm[0] + dm[1]]), delta=shift)
        starts, total = chunk_starts(eis)
        if total != len(packet_refs): raise ValueError("EIS sample count mismatch")
        start_payload = len(target) + shift + 8; offsets = []; cursor = start_payload; chunk_set = set(starts)
        for i, (_, size) in enumerate(packet_refs):
            if i in chunk_set: offsets.append(cursor)
            cursor += size
        eis = rewrite(eis, replacements=offsets)
        body = target_moov[dm[3]:] + eis
        new_moov = struct.pack(">I4s", dm[3] + len(body), b"moov") + body
        payload_size = sum(x[1] for x in packet_refs)
        with open(dst, "wb") as out:
            for p, z, typ, _ in boxes(target):
                if typ == b"moov": out.write(new_moov)
                else: copy_range(bf, out, p, z)
            out.write(struct.pack(">I4s", payload_size + 8, b"mdat"))
            for p, z in packet_refs: copy_range(sf, out, p, z)
        source.close(); target.close()


if __name__ == "__main__":
    main(*sys.argv[1:4])
