#!/usr/bin/env python3
import heapq, json, shutil, subprocess, sys
from fractions import Fraction
import av


def annexb_nals(path):
    with open(path, "rb") as f:
        buf = b""
        eof = False
        while not eof:
            chunk = f.read(4 * 1024 * 1024)
            if chunk: buf += chunk
            else: eof = True
            starts = []; i = 0
            while i + 3 <= len(buf):
                if i + 4 <= len(buf) and buf[i:i + 4] == b"\0\0\0\1": starts.append((i, i + 4)); i += 4
                elif buf[i:i + 3] == b"\0\0\1": starts.append((i, i + 3)); i += 3
                else: i += 1
            limit = len(starts) if eof else max(0, len(starts) - 1)
            for n in range(limit):
                start = starts[n][1]; end = starts[n + 1][0] if n + 1 < len(starts) else len(buf)
                if start < end: yield buf[start:end]
            if eof: break
            if starts: buf = buf[starts[-1][0]:]
            elif len(buf) > 16 * 1024 * 1024: raise ValueError("无法解析 Annex-B NAL 边界")


def access_units(path):
    prefix = []; current = None
    for nal in annexb_nals(path):
        if not nal: continue
        ntype = (nal[0] >> 1) & 63
        if ntype == 35:
            if current is not None: yield b"".join(len(n).to_bytes(4, "big") + n for n in current)
            current = prefix + [nal]; prefix = []
        elif current is None: prefix.append(nal)
        else: current.append(nal)
    if current is not None: yield b"".join(len(n).to_bytes(4, "big") + n for n in current)


def video_meta(path):
    container = av.open(path); stream = container.streams.video[0]
    values = [(p.pts, p.dts, p.is_keyframe) for p in container.demux(stream) if p.dts is not None]
    time_base = stream.time_base; metadata = dict(stream.metadata); container.close()
    return values, time_base, metadata


def main(source_path, encoded_path, injected_hevc, template_path, output_path):
    src_meta, source_time_base, source_video_metadata = video_meta(source_path)
    enc_meta, _, _ = video_meta(encoded_path)
    if len(src_meta) != len(enc_meta): raise ValueError(f"frame count mismatch: {len(src_meta)}, {len(enc_meta)}")
    src_pts = sorted(x[0] for x in src_meta); display_order = sorted(range(len(enc_meta)), key=lambda i: enc_meta[i][0])
    mapped_pts = [None] * len(enc_meta)
    for rank, i in enumerate(display_order): mapped_pts[i] = src_pts[rank]
    first_delta = src_pts[1] - src_pts[0] if len(src_pts) > 1 else 1
    last_delta = src_pts[-1] - src_pts[-2] if len(src_pts) > 1 else first_delta
    def grid(k):
        if k < 0: return src_pts[0] + k * first_delta
        if k >= len(src_pts): return src_pts[-1] + (k - len(src_pts) + 1) * last_delta
        return src_pts[k]
    display_rank = [0] * len(enc_meta)
    for rank, i in enumerate(display_order): display_rank[i] = rank
    reorder_depth = max((i - display_rank[i] for i in range(len(enc_meta))), default=0)
    mapped_dts = [grid(i - reorder_depth) for i in range(len(enc_meta))]

    source = av.open(source_path); encoded = av.open(encoded_path); template = av.open(template_path)
    sa = source.streams.audio[0]; ev = encoded.streams.video[0]; tv = template.streams.video[0]
    out = av.open(output_path, "w", options={"movflags": "+faststart", "strict": "unofficial"})
    ov = out.add_stream_from_template(tv); ov.codec_context.extradata = ev.codec_context.extradata; ov.codec_context.codec_tag = "hvc1"; ov.time_base = source_time_base; ov.metadata.update(source_video_metadata)
    oa = out.add_stream_from_template(sa); oa.time_base = sa.time_base; out.metadata.update(source.metadata)
    ffprobe = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
    meta_probe = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_entries", "format_tags", "-of", "json", source_path]))
    android = meta_probe.get("format", {}).get("tags", {}).get("com.android.version")
    if android is not None: out.metadata["com.android.version"] = android

    def video_items():
        aus = iter(access_units(injected_hevc))
        for i, meta in enumerate(enc_meta):
            try: au = next(aus)
            except StopIteration: raise ValueError(f"access unit count shorter than encoded frame count at {i}")
            p = av.Packet(au); p.pts = mapped_pts[i]; p.dts = mapped_dts[i]
            p.duration = mapped_dts[i + 1] - mapped_dts[i] if i + 1 < len(mapped_dts) else last_delta
            p.time_base = source_time_base; p.is_keyframe = meta[2]; p.stream = ov
            yield Fraction(p.dts) * p.time_base, 0, p
        try: next(aus); raise ValueError("access unit count exceeds encoded frame count")
        except StopIteration: pass

    def audio_items():
        for ap in source.demux(sa):
            if ap.dts is None: continue
            p = av.Packet(bytes(ap)); p.pts, p.dts, p.duration = ap.pts, ap.dts, ap.duration
            p.time_base = ap.time_base; p.is_keyframe = ap.is_keyframe; p.stream = oa
            yield Fraction(p.dts) * p.time_base, 1, p

    last_by_stream = {}
    try:
        for index, (_, _, packet) in enumerate(heapq.merge(video_items(), audio_items(), key=lambda x: (x[0], x[1]))):
            try: out.mux(packet)
            except Exception:
                print(f"mux failure queue={index} stream={packet.stream.index} pts={packet.pts} dts={packet.dts} duration={packet.duration} last={last_by_stream.get(packet.stream.index)}", file=sys.stderr)
                raise
            last_by_stream[packet.stream.index] = (packet.pts, packet.dts, packet.duration)
    finally:
        out.close(); source.close(); encoded.close(); template.close()


if __name__ == "__main__":
    main(*sys.argv[1:6])
