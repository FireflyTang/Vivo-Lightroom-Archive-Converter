#!/usr/bin/env python3
import collections, hashlib, json, mmap, re, shutil, struct, subprocess, sys, tempfile, uuid
from pathlib import Path

ARCHIVE_UUID = uuid.UUID("8d67d6b7-1137-5aed-b5d8-ea729a438af2").bytes
PROBE_BYTES = 256 * 1024 * 1024
ANALYZE_MICROSECONDS = 100 * 1000 * 1000


def run(args, stdout=subprocess.PIPE):
    p = subprocess.run([str(x) for x in args], stdout=stdout, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors="replace")[-5000:])
    return p.stdout, p.stderr


def probe(ffprobe, path, extra):
    # CRF 8 can make the first HEVC access unit larger than FFprobe's default
    # 5 MiB probe budget.  In that case valid AAC-LC extradata is present, but
    # FFprobe reports profile=None because it has not reached the first audio
    # packet yet.  Keep the semantic check strict and give probing enough bytes
    # to actually identify every stream.
    out, _ = run([ffprobe, "-v", "error", "-probesize", PROBE_BYTES,
                  "-analyzeduration", ANALYZE_MICROSECONDS, *extra, "-of", "json", path])
    return json.loads(out)


def packets(ffprobe, path, selector):
    return probe(ffprobe, path, ["-select_streams", selector, "-show_packets", "-show_entries", "packet=pts,dts,duration,size,flags,pos"])["packets"]


def packet_semantics(values):
    return [{k: x.get(k) for k in ("pts", "dts", "duration", "size", "flags")} for x in values]


def packet_hashes(path, values):
    result = []
    with open(path, "rb") as f:
        for item in values:
            f.seek(int(item["pos"])); remaining = int(item["size"]); h = hashlib.sha256()
            while remaining:
                chunk = f.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise ValueError("媒体包在文件边界前被截断")
                h.update(chunk); remaining -= len(chunk)
            result.append(h.digest())
    return result


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()


def boxes(buf, start=0, end=None):
    end = len(buf) if end is None else end; p = start
    while p + 8 <= end:
        z = struct.unpack_from(">I", buf, p)[0]; typ = bytes(buf[p + 4:p + 8]); h = 8
        if z == 1: z = struct.unpack_from(">Q", buf, p + 8)[0]; h = 16
        elif z == 0: z = end - p
        if z < h or p + z > end: raise ValueError(f"bad MP4 box {typ!r}@{p}")
        yield p, z, typ, h; p += z
    if p != end: raise ValueError("MP4 box 尾部存在无法归属的数据")


def kids(buf, box, meta=False):
    p, z, _, h = box
    return list(boxes(buf, p + h + (4 if meta else 0), p + z))


def child(buf, box, typ, meta=False):
    return next(x for x in kids(buf, box, meta) if x[2] == typ)


def handler(buf, track):
    h = child(buf, child(buf, track, b"mdia"), b"hdlr")
    return bytes(buf[h[0] + h[3] + 8:h[0] + h[3] + 12])


class MappedMP4:
    def __init__(self, path):
        self.f = open(path, "rb"); self.b = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        self.top = list(boxes(self.b)); self.moov = next(x for x in self.top if x[2] == b"moov")
    def close(self):
        self.b.close(); self.f.close()
    def top_bytes(self, typ):
        return [bytes(self.b[p:p + z]) for p, z, t, _ in self.top if t == typ]
    def moov_child(self, typ):
        x = next((x for x in kids(self.b, self.moov) if x[2] == typ), None)
        return bytes(self.b[x[0]:x[0] + x[1]]) if x else None
    def track(self, kind):
        return next(x for x in kids(self.b, self.moov) if x[2] == b"trak" and handler(self.b, x) == kind)
    def video_matrix(self):
        tk = child(self.b, self.track(b"vide"), b"tkhd"); q = tk[0] + tk[3]; off = q + (52 if self.b[q] else 40)
        return bytes(self.b[off:off + 36])
    def mdhd_values(self, kind):
        md = child(self.b, child(self.b, self.track(kind), b"mdia"), b"mdhd"); q = md[0] + md[3]; v = self.b[q]
        duration = struct.unpack_from(">Q" if v else ">I", self.b, q + 4 + (20 if v else 12))[0]
        language = struct.unpack_from(">H", self.b, q + 4 + (28 if v else 16))[0]
        timescale = struct.unpack_from(">I", self.b, q + 4 + (16 if v else 8))[0]
        return timescale, duration, language
    def stsd(self, kind):
        tr = self.track(kind); stsd = child(self.b, child(self.b, child(self.b, child(self.b, tr, b"mdia"), b"minf"), b"stbl"), b"stsd")
        return bytes(self.b[stsd[0]:stsd[0] + stsd[1]])
    def dovi_box(self):
        stsd = self.stsd(b"vide"); p = 16; z = struct.unpack_from(">I", stsd, p)[0]
        return next((bytes(stsd[x:x + n]) for x, n, t, _ in boxes(stsd, p + 86, p + z) if t in (b"dvvC", b"dvcC")), None)


def strip_temporal_layer_value(raw):
    if raw is None: return None
    b = bytearray(raw); meta = (0, len(b), b"meta", 8); keys = child(b, meta, b"keys")
    q = keys[0] + keys[3] + 4; count = struct.unpack_from(">I", b, q)[0]; p = q + 4; index = None
    for i in range(1, count + 1):
        z = struct.unpack_from(">I", b, p)[0]
        if bytes(b[p + 4:p + 8]) == b"mdta" and bytes(b[p + 8:p + z]) == b"com.android.video.temporal_layers_count": index = i
        p += z
    if index is None: return bytes(b)
    ilst = child(b, meta, b"ilst"); item = next((x for x in kids(b, ilst) if x[2] == struct.pack(">I", index)), None)
    if item:
        n = item[1]; struct.pack_into(">I", b, 0, len(b) - n); struct.pack_into(">I", b, ilst[0], ilst[1] - n); del b[item[0]:item[0] + n]
    return bytes(b)


def archive_provenance(mp4):
    records = []
    for p, z, typ, h in mp4.top:
        if typ == b"uuid" and z >= h + 16 and bytes(mp4.b[p + h:p + h + 16]) == ARCHIVE_UUID:
            records.append(json.loads(bytes(mp4.b[p + h + 16:p + z])))
    if len(records) != 1: raise ValueError("档案 provenance UUID 数量错误")
    return records[0]


def annexb_temporal_ids(ffmpeg, path):
    p = subprocess.Popen([str(ffmpeg), "-v", "error", "-i", str(path), "-map", "0:v:0", "-c:v", "copy", "-bsf:v", "hevc_mp4toannexb", "-f", "hevc", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buf = b""; tids = set()
    while True:
        chunk = p.stdout.read(4 * 1024 * 1024)
        if not chunk: break
        buf += chunk
        starts = []
        i = 0
        while True:
            a = buf.find(b"\x00\x00\x01", i)
            if a < 0: break
            start = a + 3
            if a > 0 and buf[a - 1] == 0: start = a + 3
            starts.append((a, start)); i = start
        if len(starts) < 2:
            if len(buf) > 16 * 1024 * 1024: raise ValueError("无法解析 Annex-B NAL 边界")
            continue
        for n in range(len(starts) - 1):
            start, end = starts[n][1], starts[n + 1][0]
            if end - start >= 2: tids.add((buf[start + 1] & 7) - 1)
        buf = buf[starts[-1][0]:]
    a = buf.find(b"\x00\x00\x01")
    if a >= 0:
        start = a + 3
        if len(buf) - start >= 2: tids.add((buf[start + 1] & 7) - 1)
    stderr = p.stderr.read(); rc = p.wait()
    if rc: raise RuntimeError(stderr.decode(errors="replace")[-4000:])
    return tids


def parameter_sets_are_single_layer(ffmpeg, path):
    p = subprocess.run([str(ffmpeg), "-v", "trace", "-i", str(path), "-map", "0:v:0", "-frames:v", "1", "-c:v", "copy", "-bsf:v", "trace_headers", "-f", "null", "-"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    text = p.stderr.decode(errors="replace"); lines = text.splitlines()
    return all(any(name in line and line.rstrip().endswith("= 0") for line in lines) for name in ("sps_max_sub_layers_minus1", "vps_max_sub_layers_minus1"))


def quality_sample(ffmpeg, src, out, mode):
    graph = "[0:v]select='not(mod(n,300))',setpts=N,split=2[s1][s2];[1:v]select='not(mod(n,300))',setpts=N,split=2[o1][o2];[s1][o1]psnr[p];[s2][o2]ssim[s]"
    p = subprocess.run([str(ffmpeg), "-v", "info", "-noautorotate", "-i", str(src), "-noautorotate", "-i", str(out), "-filter_complex", graph, "-map", "[p]", "-map", "[s]", "-an", "-f", "null", "-"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    text = p.stderr.decode(errors="replace")
    if p.returncode: raise RuntimeError(text[-5000:])
    pm = re.findall(r"PSNR[^\n]*average:([0-9.]+)", text); sm = re.findall(r"SSIM[^\n]*All:([0-9.]+)", text)
    if not pm or not sm: raise ValueError("无法取得画质抽样指标")
    psnr, ssim = float(pm[-1]), float(sm[-1]); minimum = (40.0, .96) if mode == "hardware" else (45.0, .98)
    if psnr < minimum[0] or ssim < minimum[1]: raise ValueError(f"画质抽样低于安全阈值：PSNR {psnr:.2f} / SSIM {ssim:.6f}")
    return psnr, ssim


def main(src, out, dovi, ffmpeg, ffprobe, mode="cpu"):
    src, out = Path(src), Path(out)
    si = probe(ffprobe, src, ["-show_streams", "-show_format"]); oi = probe(ffprobe, out, ["-show_streams", "-show_format"])
    if [x.get("codec_type") for x in oi["streams"]] != ["video", "audio", "data"]: raise ValueError("输出轨道结构不是视频、AAC、EIS")
    sv, ov = si["streams"][0], oi["streams"][0]
    for k in ("codec_name", "profile", "codec_tag_string", "width", "height", "pix_fmt", "color_range", "color_space", "color_transfer", "color_primaries", "time_base"):
        if ov.get(k) != sv.get(k): raise ValueError(f"输出视频 {k} 与原片不一致：{ov.get(k)!r} != {sv.get(k)!r}")
    sa, oa = si["streams"][1], oi["streams"][1]
    for k in ("codec_name", "profile", "codec_tag_string", "sample_rate", "channels", "channel_layout", "time_base"):
        if oa.get(k) != sa.get(k): raise ValueError(f"输出 AAC {k} 与原片不一致：{oa.get(k)!r} != {sa.get(k)!r}")
    sd, od = si["streams"][2], oi["streams"][2]
    for k in ("codec_tag_string", "time_base"):
        if od.get(k) != sd.get(k): raise ValueError(f"输出 EIS {k} 与原片不一致：{od.get(k)!r} != {sd.get(k)!r}")
    sm, om = MappedMP4(src), MappedMP4(out)
    try:
        if sm.video_matrix() != om.video_matrix(): raise ValueError("视频显示矩阵未逐字节保留")
        for kind, label in ((b"vide", "视频"), (b"soun", "AAC"), (b"meta", "EIS")):
            if sm.mdhd_values(kind) != om.mdhd_values(kind): raise ValueError(f"{label}时间刻度、时长或语言代码不一致")
        if sm.stsd(b"meta") != om.stsd(b"meta"): raise ValueError("EIS 样本描述未逐字节保留")
        source_dovi, output_dovi = sm.dovi_box(), om.dovi_box()
        if source_dovi != output_dovi: raise ValueError("Dolby Vision 配置未按存在性逐字节保留")
        print("VERIFY\tPASS\t视频规格、方向矩阵、轨道时间基与 EIS 样本描述", flush=True)

        source_uuids = collections.Counter(hashlib.sha256(x).digest() for x in sm.top_bytes(b"uuid"))
        output_source_uuids = collections.Counter(hashlib.sha256(x).digest() for x in om.top_bytes(b"uuid") if x[8:24] != ARCHIVE_UUID)
        if source_uuids != output_source_uuids: raise ValueError("源文件顶层 UUID box 未全部逐字节保留")
        if sm.moov_child(b"udta") != om.moov_child(b"udta"): raise ValueError("udta/GPS/拍摄元信息未逐字节保留")
        if strip_temporal_layer_value(sm.moov_child(b"meta")) != om.moov_child(b"meta"): raise ValueError("未知 movie metadata 未保留，或活动三时间层值未正确移除")
        if sm.top_bytes(b"ftyp") != om.top_bytes(b"ftyp"): raise ValueError("MP4 brands/ftyp 未逐字节保留")
        print("VERIFY\tPASS\t未知独立元信息、UUID、udta、GPS 与 movie metadata 字节级账本", flush=True)
    finally:
        sm.close(); om.close()

    svp, ovp = packets(ffprobe, src, "v:0"), packets(ffprobe, out, "v:0")
    if len(svp) != len(ovp) or sorted(int(x["pts"]) for x in svp) != sorted(int(x["pts"]) for x in ovp): raise ValueError("视频帧数或显示 PTS 集合不一致")
    print(f"VERIFY\tPASS\t视频帧数与显示 PTS 集合（{len(ovp)}帧）", flush=True)
    for selector, label in (("a:0", "AAC"), ("d:0", "EIS")):
        a, b = packets(ffprobe, src, selector), packets(ffprobe, out, selector)
        if packet_semantics(a) != packet_semantics(b): raise ValueError(f"{label}包时间属性不一致")
        if packet_hashes(src, a) != packet_hashes(out, b): raise ValueError(f"{label}包内容不一致")
        print(f"VERIFY\tPASS\t{label}内容与时间逐包一致（{len(b)}包）", flush=True)

    if not parameter_sets_are_single_layer(ffmpeg, out): raise ValueError("输出 VPS/SPS 不是单时间层")
    tids = annexb_temporal_ids(ffmpeg, out)
    if tids != {0}: raise ValueError(f"输出完整码流 temporal_id 不是单层：{sorted(tids)}")
    print("VERIFY\tPASS\t完整码流 VPS/SPS 与所有 NAL 均为单时间层", flush=True)

    source_dv = any(x.get("side_data_type") == "DOVI configuration record" for x in sv.get("side_data_list", []))
    output_dv = any(x.get("side_data_type") == "DOVI configuration record" for x in ov.get("side_data_list", []))
    if source_dv != output_dv: raise ValueError("Dolby Vision 存在性发生变化")
    if source_dv:
        with tempfile.TemporaryDirectory(prefix="vac-rpu-verify-") as td:
            td = Path(td); sr, oraw, a, b = td / "s.hevc", td / "o.hevc", td / "s.rpu", td / "o.rpu"
            for pth, raw in ((src, sr), (out, oraw)):
                run([ffmpeg, "-v", "error", "-i", pth, "-map", "0:v:0", "-c", "copy", "-bsf:v", "hevc_mp4toannexb", "-f", "hevc", raw], stdout=subprocess.DEVNULL)
            run([dovi, "extract-rpu", "-i", sr, "-o", a], stdout=subprocess.DEVNULL); run([dovi, "extract-rpu", "-i", oraw, "-o", b], stdout=subprocess.DEVNULL)
            if a.read_bytes() != b.read_bytes(): raise ValueError("Dolby Vision RPU 未逐字节保留")
        print("VERIFY\tPASS\tDolby Vision 配置与逐帧 RPU 字节级一致", flush=True)
    else:
        print("VERIFY\tPASS\tSDR 原片与输出均无 Dolby Vision", flush=True)

    st, ot = si["format"].get("tags", {}), oi["format"].get("tags", {})
    if st != ot: raise ValueError(f"容器可见元数据字段不一致：source={st} output={ot}")
    for i, (a, b) in enumerate(zip(si["streams"], oi["streams"])):
        if a.get("tags", {}) != b.get("tags", {}): raise ValueError(f"第{i+1}条轨道可见元数据不一致")
    print("VERIFY\tPASS\t全部可见容器与轨道元数据逐字段一致", flush=True)

    psnr, ssim = quality_sample(ffmpeg, src, out, mode)
    print(f"VERIFY\tPASS\t原生色彩域画质抽样 PSNR {psnr:.2f} dB / SSIM {ssim:.6f}", flush=True)
    run([ffmpeg, "-v", "error", "-i", out, "-map", "0", "-f", "null", "-"], stdout=subprocess.DEVNULL)
    print("VERIFY\tPASS\t全部输出轨道完整解码/读取", flush=True)

    om = MappedMP4(out)
    try: provenance = archive_provenance(om)
    finally: om.close()
    if provenance.get("schema") != "video.archive.provenance.v2": raise ValueError("provenance schema 错误")
    source_record = provenance.get("source", {})
    if source_record.get("sha256") != file_sha256(src) or source_record.get("size_bytes") != src.stat().st_size:
        raise ValueError("provenance 中的原片哈希或大小未经独立复算验证")
    expected = ("Apple VideoToolbox HEVC hardware encoder", "VideoToolbox quality 65") if mode == "hardware" else ("x265", "CRF 8")
    conversion = provenance.get("conversion", {})
    if (conversion.get("encoder"), conversion.get("rate_control")) != expected: raise ValueError("provenance 编码器或码率控制记录错误")
    if out.stat().st_mtime_ns != src.stat().st_mtime_ns: raise ValueError("输出文件系统修改时间未原样保留")
    print("VERIFY\tPASS\t来源哈希、转换方式与必要变化记录", flush=True)
    print("VERIFIED\tALL\t输出完整复检通过", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:7])
