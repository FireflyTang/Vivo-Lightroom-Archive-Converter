#!/usr/bin/env python3
import hashlib, importlib.util, json, mmap, os, shutil, struct, subprocess, sys, time, uuid
from contextlib import contextmanager
from pathlib import Path

RESOURCE = Path(os.environ.get("VAC_RESOURCE_DIR", Path(__file__).resolve().parents[1]))
ENGINE = RESOURCE / "Engine"
DOVI = Path(shutil.which("dovi_tool") or ENGINE / "dovi_tool")
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
PYTHON = sys.executable

VIVO_UUID = uuid.UUID("7669766f-4d65-6469-6145-7874496e666f").bytes
KNOWN_AUDIO_STSD = "db3c7a70f068b3f6caa4689c26dd705ce78b9da57d00f176fb05c8ea8d69083a"
KNOWN_EIS_STSD = "81f8f8f1205857a67b66c4e1d5649f93d3696564734d162674245526c743eee0"
SAFE_TOP_LEVEL = {b"ftyp", b"free", b"skip", b"wide", b"mdat", b"moov", b"uuid"}


def run(args, capture=True, check=True, stderr=None):
    p = subprocess.run([str(x) for x in args], stdout=subprocess.PIPE if capture else None,
                       stderr=stderr if stderr is not None else subprocess.PIPE, check=False)
    if check and p.returncode:
        msg = (p.stderr or b"").decode("utf-8", "replace")[-5000:]
        raise RuntimeError(f"命令失败：{Path(str(args[0])).name}\n{msg}")
    return p.stdout if capture else b""


def probe(path):
    return json.loads(run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", path]))


def boxes(buf, start=0, end=None):
    end = len(buf) if end is None else end
    p = start
    while p + 8 <= end:
        size = struct.unpack_from(">I", buf, p)[0]
        typ = bytes(buf[p + 4:p + 8])
        head = 8
        if size == 1:
            if p + 16 > end:
                raise ValueError(f"截断的扩展 MP4 box {typ!r} @ {p}")
            size = struct.unpack_from(">Q", buf, p + 8)[0]
            head = 16
        elif size == 0:
            size = end - p
        if size < head or p + size > end:
            raise ValueError(f"损坏的 MP4 box {typ!r} @ {p}")
        yield p, size, typ, head
        p += size
    if p != end:
        raise ValueError(f"MP4 box 尾部存在 {end-p} 个无法归属的字节")


def children(buf, box, meta=False):
    p, z, _, h = box
    return list(boxes(buf, p + h + (4 if meta else 0), p + z))


def child(buf, box, typ, meta=False):
    return next(x for x in children(buf, box, meta) if x[2] == typ)


def handler(buf, track):
    h = child(buf, child(buf, track, b"mdia"), b"hdlr")
    return bytes(buf[h[0] + h[3] + 8:h[0] + h[3] + 12])


def video_matrix(buf):
    moov = next(x for x in boxes(buf) if x[2] == b"moov")
    track = next(x for x in children(buf, moov) if x[2] == b"trak" and handler(buf, x) == b"vide")
    tkhd = child(buf, track, b"tkhd")
    q = tkhd[0] + tkhd[3]
    off = q + (52 if buf[q] else 40)
    return bytes(buf[off:off + 36])


def matrix_rotation(matrix):
    known = {
        struct.pack(">9i", 65536, 0, 0, 0, 65536, 0, 0, 0, 1073741824): 0,
        struct.pack(">9i", 0, 65536, 0, -65536, 0, 0, 0, 0, 1073741824): 90,
        struct.pack(">9i", -65536, 0, 0, 0, -65536, 0, 0, 0, 1073741824): 180,
        struct.pack(">9i", 0, -65536, 0, 65536, 0, 0, 0, 0, 1073741824): 270,
    }
    return known.get(matrix)


def sample_description_hashes(buf):
    moov = next(x for x in boxes(buf) if x[2] == b"moov")
    result = {}
    for track in (x for x in children(buf, moov) if x[2] == b"trak"):
        typ = handler(buf, track)
        stsd = child(buf, child(buf, child(buf, child(buf, track, b"mdia"), b"minf"), b"stbl"), b"stsd")
        result[typ] = hashlib.sha256(bytes(buf[stsd[0]:stsd[0] + stsd[1]])).hexdigest()
    return result


def top_uuid(buf):
    result = []
    for p, z, typ, h in boxes(buf):
        if typ == b"uuid" and z >= h + 16:
            result.append((bytes(buf[p + h:p + h + 16]), hashlib.sha256(bytes(buf[p:p + z])).hexdigest(), bytes(buf[p + h + 16:p + z])))
    return result


def vivo_json(payload):
    if not payload.startswith(b"vivo"):
        raise ValueError("Vivo UUID 缺少 vivo 前缀")
    start, end = payload.find(b"{"), payload.rfind(b"}")
    if start < 0 or end < start:
        raise ValueError("Vivo UUID JSON 无效")
    value = json.loads(payload[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("Vivo UUID JSON 不是对象")
    return value


def rate(value):
    if not value or value == "0/0":
        return None
    a, b = value.split("/")
    return float(a) / float(b)


def temporal_audit(path, seconds=2):
    args = [FFMPEG, "-v", "trace", "-i", path, "-map", "0:v:0"]
    if seconds:
        args += ["-t", str(seconds)]
    args += ["-c:v", "copy", "-bsf:v", "trace_headers", "-f", "null", "-"]
    p = subprocess.run([str(x) for x in args], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    text = p.stderr.decode("utf-8", "replace")
    tids = set()
    for line in text.splitlines():
        if "nuh_temporal_id_plus1" in line and "=" in line:
            try:
                tids.add(int(line.rsplit("=", 1)[1].strip()) - 1)
            except ValueError:
                pass
    lines = text.splitlines()
    declared = lambda name, value: any(name in line and line.rstrip().endswith(f"= {value}") for line in lines)
    return declared("sps_max_sub_layers_minus1", 2), declared("vps_max_sub_layers_minus1", 2), tids


def metadata_ledger(buf, info):
    top = list(boxes(buf))
    moov = next(x for x in top if x[2] == b"moov")
    udta = next((x for x in children(buf, moov) if x[2] == b"udta"), None)
    uuids = top_uuid(buf)
    return {
        "policy": "未知但边界独立的数据原样复制；与新码流相关的数据语义重建；无法证明安全的结构拒绝",
        "top_level_boxes": [x[2].decode("latin1") for x in top],
        "top_level_uuid_count": len(uuids),
        "top_level_uuid_sha256": [x[1] for x in uuids],
        "udta": "原样复制并逐字节核验" if udta else "源文件不存在，输出不得虚构",
        "movie_meta": "原样复制未知键；仅移除会错误描述输出的活动三时间层值",
        "format_metadata_keys": sorted(info.get("format", {}).get("tags", {}).keys()),
        "audio": "压缩包、时间与轨道元数据逐包/逐字段核验",
        "eis": "数据包、时间与样本描述逐包/逐字段核验",
    }


def classify(v):
    fps = rate(v.get("avg_frame_rate")) or rate(v.get("r_frame_rate")) or 0
    dim = (v.get("width"), v.get("height"))
    if v.get("profile") == "Main" and v.get("pix_fmt") == "yuv420p" and v.get("color_primaries") == "bt709" and v.get("color_transfer") == "bt709" and v.get("color_space") == "bt709":
        if dim == (1920, 1080) and 28.5 <= fps <= 31.5:
            return "1080p30 SDR 8-bit", 30, False
        if dim == (3840, 2160) and 58 <= fps <= 62:
            return "4K60 SDR 8-bit", 60, False
    if v.get("profile") == "Main 10" and v.get("pix_fmt") == "yuv420p10le" and dim == (3840, 2160) and 58 <= fps <= 62 and v.get("color_primaries") == "bt2020" and v.get("color_transfer") == "arib-std-b67" and v.get("color_space") == "bt2020nc":
        return "4K60 HLG Dolby Vision 8.4 10-bit", 60, True
    return None


def inspect(path):
    path = Path(path)
    reasons = []
    try:
        info = probe(path)
        streams = info.get("streams", [])
        types = [s.get("codec_type") for s in streams]
        v = streams[0] if streams else {}
        a = streams[1] if len(streams) > 1 else {}
        d = streams[2] if len(streams) > 2 else {}
        with path.open("rb") as fh:
            data = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
            top = list(boxes(data))
            top_types = [x[2] for x in top]
            unsafe = sorted({x.decode("latin1") for x in top_types if x not in SAFE_TOP_LEVEL})
            if unsafe:
                reasons.append("存在无法证明可安全迁移的顶层 MP4 box：" + ", ".join(unsafe))
            if top_types.count(b"ftyp") != 1 or top_types.count(b"moov") != 1 or b"mdat" not in top_types:
                reasons.append("MP4 必须具有唯一 ftyp、唯一 moov 和至少一个 mdat")
            matrix = video_matrix(data)
            rotation = matrix_rotation(matrix)
            if rotation is None:
                reasons.append("显示矩阵不是已验证的 0°/90°/180°/270°正交旋转")
            stsd = sample_description_hashes(data)
            if stsd.get(b"soun") != KNOWN_AUDIO_STSD:
                reasons.append("AAC 样本描述包含尚未验证的结构")
            if stsd.get(b"meta") != KNOWN_EIS_STSD:
                reasons.append("EIS 样本描述包含尚未验证的结构")
            vus = [x for x in top_uuid(data) if x[0] == VIVO_UUID]
            if len(vus) != 1:
                reasons.append("必须正好有一个 Vivo 私有 UUID")
                obj = {}
            else:
                obj = vivo_json(vus[0][2])
                if obj.get("com.android.camera.takenmodel") != "vivo X200 Ultra":
                    reasons.append("拍摄设备不是 Vivo X200 Ultra")
            ledger = metadata_ledger(data, info)
            data.close()

        if types != ["video", "audio", "data"]:
            reasons.append(f"轨道必须依次为视频、AAC、EIS，实际为 {types}")
        if v.get("codec_name") != "hevc" or v.get("codec_tag_string") != "hvc1" or v.get("time_base") != "1/90000" or v.get("color_range") != "tv":
            reasons.append("HEVC hvc1、limited range 或 1/90000 时间基结构不匹配")
        profile = classify(v)
        if not profile:
            reasons.append("视频不属于已验证的 1080p30 SDR、4K60 SDR 或 4K60 HLG/Dolby Vision 档案")
            archive_profile, nominal_fps, wants_dv = "未知", 0, False
        else:
            archive_profile, nominal_fps, wants_dv = profile
        if not (a.get("codec_name") == "aac" and a.get("profile") == "LC" and a.get("codec_tag_string") == "mp4a" and a.get("sample_rate") == "48000" and a.get("channels") == 2 and a.get("time_base") == "1/48000"):
            reasons.append("AAC-LC 48 kHz 双声道音轨结构不匹配")
        if not (d.get("codec_tag_string") == "mett" and d.get("time_base") == "1/90000" and d.get("tags", {}).get("handler_name") == "MetadHandle"):
            reasons.append("Vivo EIS metadata 轨道结构不匹配")
        dv = [x for x in v.get("side_data_list", []) if x.get("side_data_type") == "DOVI configuration record"]
        if wants_dv:
            if len(dv) != 1:
                reasons.append("HLG 档案缺少唯一 Dolby Vision 配置")
            else:
                expected = {"dv_profile": 8, "rpu_present_flag": 1, "el_present_flag": 0, "bl_present_flag": 1, "dv_bl_signal_compatibility_id": 4}
                for k, want in expected.items():
                    if dv[0].get(k) != want:
                        reasons.append(f"Dolby Vision {k} 不匹配")
        elif dv:
            reasons.append("SDR 档案意外包含尚未验证的 Dolby Vision 配置")
        sps, vps, tids = temporal_audit(path, 2)
        if not (sps and vps):
            reasons.append("VPS/SPS 没有同时声明三个时间子层")
        if tids and not tids.issubset({0, 1, 2}):
            reasons.append(f"发现超出声明范围的 temporal ID：{sorted(tids)}")

        tags = info.get("format", {}).get("tags", {})
        checks = []
        def add(name, ok, detail):
            checks.append({"name": name, "state": "passed" if ok else "failed", "detail": detail})
        add("受支持的 MP4 与轨道骨架", not any("MP4" in r or "轨道必须" in r for r in reasons), f"{types}；顶层 {ledger['top_level_boxes']}")
        add("自适应视频档案", profile is not None, f"{archive_profile}；Level {v.get('level')}；平均 {rate(v.get('avg_frame_rate')) or 0:.6f} fps")
        add("方向矩阵", rotation is not None, f"原样保留 {rotation if rotation is not None else '?'}° 显示矩阵")
        add("AAC 原始音轨", not any("AAC" in r for r in reasons), f"AAC-LC · {a.get('sample_rate')} Hz · {a.get('channels')}声道")
        add("Vivo EIS 数据轨", not any("EIS" in r for r in reasons), f"mett / MetadHandle · {d.get('nb_frames', '?')}包")
        add("HDR 与 Dolby Vision 条件路径", not any("Dolby Vision" in r for r in reasons), "RPU/dvvC 原样迁移" if wants_dv else "源片为 SDR，不添加 HDR/Dolby Vision")
        add("Vivo 私有元信息", not any("Vivo 私有" in r or "拍摄设备" in r for r in reasons), f"Vivo X200 Ultra；{len(obj)}个字段，整个 UUID box 原样复制")
        add("未知元信息安全账本", not any("无法证明" in r or "尚未验证的结构" in r for r in reasons), f"{ledger['top_level_uuid_count']}个 UUID；udta：{ledger['udta']}")
        add("三时间子层输入", sps and vps, f"VPS/SPS 声明3层；抽样 temporal_id={sorted(tids)}")
        add("拍摄字段按存在性保存", True, f"时间={tags.get('creation_time', '未提供')}；GPS={tags.get('location', '源文件未提供')}；不虚构缺失字段")
        return {
            "accepted": not reasons, "path": str(path), "name": path.name, "size_bytes": path.stat().st_size,
            "duration": float(info.get("format", {}).get("duration", 0) or 0), "width": v.get("width"), "height": v.get("height"),
            "frame_count": int(v.get("nb_frames", 0) or 0), "fps": rate(v.get("avg_frame_rate")), "nominal_fps": nominal_fps,
            "archive_profile": archive_profile, "rotation": rotation, "video_codec": v.get("codec_name"), "video_profile": v.get("profile"),
            "pixel_format": v.get("pix_fmt"), "audio_description": f"AAC-LC {a.get('sample_rate', '?')} Hz {a.get('channels', '?')}声道",
            "dolby_vision": "Dolby Vision Profile 8.4" if wants_dv else "无（SDR原片）", "has_dolby_vision": wants_dv,
            "eis_packets": int(d.get("nb_frames", 0) or 0), "creation_time": tags.get("creation_time"), "location": tags.get("location"),
            "device": obj.get("com.android.camera.takenmodel"), "metadata_ledger": ledger, "reasons": reasons, "checks": checks,
        }
    except Exception as e:
        return {"accepted": False, "path": str(path), "name": path.name, "size_bytes": path.stat().st_size if path.exists() else 0,
                "duration": None, "width": None, "height": None, "frame_count": None, "fps": None, "nominal_fps": None,
                "archive_profile": None, "rotation": None, "video_codec": None, "video_profile": None, "pixel_format": None,
                "audio_description": None, "dolby_vision": None, "has_dolby_vision": False, "eis_packets": None,
                "creation_time": None, "location": None, "device": None, "metadata_ledger": None,
                "reasons": [f"检查异常：{e}"], "checks": [{"name": "读取并解析输入文件", "state": "failed", "detail": str(e)}]}


def progress(value, msg):
    print(f"PROGRESS\t{value:.3f}\t{msg}", flush=True)


@contextmanager
def timed(name):
    started = time.monotonic()
    try:
        yield
    except Exception:
        print(f"TIMING\t{name}\t{time.monotonic() - started:.3f}\tFAILED", flush=True)
        raise
    else:
        print(f"TIMING\t{name}\t{time.monotonic() - started:.3f}\tPASS", flush=True)


def convert(path, hardware=False):
    missing = []
    for name, tool in (("ffmpeg", FFMPEG), ("ffprobe", FFPROBE)):
        if not Path(tool).is_file() or not os.access(tool, os.X_OK):
            missing.append(name)
    if importlib.util.find_spec("av") is None:
        missing.append("PyAV")
    src = Path(path).resolve()
    audit = inspect(src)
    if audit.get("has_dolby_vision") and (not Path(DOVI).is_file() or not os.access(DOVI, os.X_OK)):
        missing.append("dovi_tool（仅 Dolby Vision 输入需要）")
    if missing:
        raise RuntimeError("缺少运行依赖：" + ", ".join(missing) + "。请先运行 install_dependencies.command，然后重新打开 App。")
    if not audit["accepted"]:
        raise RuntimeError("输入安全检查未通过：\n" + "\n".join(audit["reasons"]))
    suffix = "_LR_VT_Q65_archive.mp4" if hardware else "_LR_CRF8_archive.mp4"
    out = src.with_name(src.stem + suffix)
    if out.exists():
        raise RuntimeError(f"目标已存在，拒绝覆盖：{out}")
    temp_out = src.with_name("." + out.name + ".incomplete")
    if temp_out.exists():
        temp_out.unlink()
    import tempfile
    with tempfile.TemporaryDirectory(prefix="vivo-lr-archive-", dir=src.parent) as td:
        td = Path(td)
        raw_src, encoded, encoded_mp4 = td / "source.hevc", td / "encoded.hevc", td / "encoded.mp4"
        rpu, dv_hevc, dv_template = td / "rpu.bin", td / "dv.hevc", td / "dv_template.mp4"
        avmux, eis, finalmeta = td / "avmux.mp4", td / "eis.mp4", td / "finalmeta.mp4"
        has_dv = audit["has_dolby_vision"]
        if has_dv:
            progress(.03, "提取并核验 Dolby Vision RPU")
            with timed("提取并核验 Dolby Vision RPU"):
                run([FFMPEG, "-v", "error", "-i", src, "-map", "0:v:0", "-c", "copy", "-bsf:v", "hevc_mp4toannexb", "-f", "hevc", raw_src], capture=False)
                run([DOVI, "extract-rpu", "-i", raw_src, "-o", rpu], capture=False)
        else:
            progress(.03, "确认 SDR 输入，不添加 HDR 或 Dolby Vision")
        progress(.10, ("VideoToolbox Q65" if hardware else "x265 CRF 8") + f" · {audit['archive_profile']} · 单时间层编码")
        is_10bit = audit["video_profile"] == "Main 10"
        if hardware:
            encode_args = ["-c:v", "hevc_videotoolbox", "-profile:v", "main10" if is_10bit else "main", "-q:v", "65", "-pix_fmt", "p010le" if is_10bit else "yuv420p"]
        else:
            encode_args = ["-c:v", "libx265", "-preset", "medium", "-crf", "8", "-pix_fmt", "yuv420p10le" if is_10bit else "yuv420p",
                           "-x265-params", f"keyint={audit['nominal_fps']}:min-keyint=1:high-tier=1"]
        color = ["-color_range", "tv"]
        if is_10bit:
            color += ["-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc"]
        else:
            color += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
        with timed("单时间层 HEVC 编码"):
            run([FFMPEG, "-hide_banner", "-loglevel", "error", "-noautorotate", "-i", src, "-map", "0:v:0", "-an", "-sn", "-dn",
                 *encode_args, *color, "-fps_mode", "passthrough", "-tag:v", "hvc1", encoded_mp4], capture=False)
        with timed("提取编码码流并插入 AUD"):
            run([FFMPEG, "-v", "error", "-i", encoded_mp4, "-map", "0:v:0", "-c", "copy", "-bsf:v", "hevc_mp4toannexb,hevc_metadata=aud=insert", "-f", "hevc", encoded], capture=False)
        if has_dv:
            progress(.62, "逐帧重新注入原始 Dolby Vision RPU")
            with timed("逐帧重新注入原始 Dolby Vision RPU"):
                run([DOVI, "inject-rpu", "-i", encoded, "-r", rpu, "-o", dv_hevc], capture=False)
                run([FFMPEG, "-v", "error", "-r", str(audit["nominal_fps"]), "-i", dv_hevc, "-c", "copy", "-tag:v", "hvc1", dv_template], capture=False)
            video_es, template = dv_hevc, dv_template
        else:
            video_es, template = encoded, encoded_mp4
        progress(.70, "恢复原始视频 PTS 与 AAC 压缩包")
        with timed("恢复原始视频 PTS 与 AAC 压缩包"):
            run([PYTHON, ENGINE / "mux_exact.py", src, encoded_mp4, video_es, template, avmux], capture=False)
        progress(.77, "逐包复制原始 EIS 轨道")
        with timed("逐包复制原始 EIS 轨道"):
            run([PYTHON, ENGINE / "inject_eis.py", src, avmux, eis], capture=False)
        progress(.83, "恢复方向、GPS、时间与未知独立元信息")
        with timed("恢复方向、GPS、时间与未知独立元信息"):
            run([PYTHON, ENGINE / "finalize_mp4.py", src, eis, finalmeta], capture=False)
        with timed("写入来源与转换记录"):
            run([PYTHON, ENGINE / "append_provenance.py", src, finalmeta, temp_out, "hardware" if hardware else "cpu"], capture=False)
        os.utime(temp_out, ns=(src.stat().st_atime_ns, src.stat().st_mtime_ns))
        progress(.88, "运行独立的完整输出复检")
        with timed("独立完整输出复检"):
            run([PYTHON, ENGINE / "validate_output.py", src, temp_out, DOVI, FFMPEG, FFPROBE, "hardware" if hardware else "cpu"], capture=False)
        os.replace(temp_out, out)
    progress(1, "完成，全部核验通过")
    print(f"OUTPUT\t{out}", flush=True)


def main():
    if len(sys.argv) not in {3, 4} or sys.argv[1] not in {"inspect", "convert"}:
        raise SystemExit("usage: converter_engine.py inspect|convert FILE [hardware]")
    if sys.argv[1] == "inspect":
        print(json.dumps(inspect(sys.argv[2]), ensure_ascii=False))
    else:
        try:
            convert(sys.argv[2], hardware=(len(sys.argv) == 4 and sys.argv[3] == "hardware"))
        except Exception as e:
            hardware = len(sys.argv) == 4 and sys.argv[3] == "hardware"
            suffix = "_LR_VT_Q65_archive.mp4" if hardware else "_LR_CRF8_archive.mp4"
            p = Path(sys.argv[2]).resolve()
            tmp = p.with_name("." + p.stem + suffix + ".incomplete")
            if tmp.exists():
                tmp.unlink()
            print(str(e), file=sys.stderr)
            raise SystemExit(1)


if __name__ == "__main__":
    main()
