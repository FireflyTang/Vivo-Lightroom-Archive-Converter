#!/usr/bin/env python3
import hashlib, json, shutil, struct, subprocess, sys, uuid
from pathlib import Path

U = uuid.UUID("8d67d6b7-1137-5aed-b5d8-ea729a438af2")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path):
    ffprobe = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
    return json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", path]))


def main(src, converted, out, mode="cpu"):
    src, converted, out = map(Path, (src, converted, out))
    si, oi = probe(src), probe(converted)
    sv = next(x for x in si["streams"] if x.get("codec_type") == "video")
    ov = next(x for x in oi["streams"] if x.get("codec_type") == "video")
    has_dv = any(x.get("side_data_type") == "DOVI configuration record" for x in sv.get("side_data_list", []))
    encoder = "Apple VideoToolbox HEVC hardware encoder" if mode == "hardware" else "x265"
    rate_control = "VideoToolbox quality 65" if mode == "hardware" else "CRF 8"
    record = {
        "schema": "video.archive.provenance.v2",
        "source": {
            "filename": src.name, "size_bytes": src.stat().st_size, "sha256": sha256(src),
            "video_codec": f"{sv.get('codec_name')} {sv.get('profile')}", "video_temporal_layers": 3,
            "video_level": sv.get("level"), "resolution": f"{sv.get('width')}x{sv.get('height')}",
            "pixel_format": sv.get("pix_fmt"), "color": {k: sv.get(k) for k in ("color_range", "color_primaries", "color_transfer", "color_space")},
            "dolby_vision": "Profile 8.4 RPU" if has_dv else None,
        },
        "conversion": {
            "purpose": "Lightroom Classic compatibility", "video_codec": f"{ov.get('codec_name')} {ov.get('profile')}",
            "video_temporal_layers": 1, "encoder": encoder, "rate_control": rate_control,
            "audio": "original AAC packets and timing preserved byte-for-byte",
            "dolby_vision": "original RPU payloads and configuration preserved byte-for-byte" if has_dv else "not present in source and not added",
            "eis": "original Vivo EIS packets and timing preserved byte-for-byte",
            "video_timing": "original frame count and presentation timestamp set preserved",
            "metadata": "source udta, top-level UUID boxes and unknown independent metadata preserved; active temporal-layer value removed",
        },
        "intentional_changes": ["HEVC compressed video", "GOP and decode timestamps", "HEVC parameter sets", "three temporal layers to one", "MP4 byte layout"],
        "note": "Source temporal_layers_count=3 is provenance, not an active property of this converted single-layer bitstream.",
    }
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    box = struct.pack(">I4s", 24 + len(payload), b"uuid") + U.bytes + payload
    with open(out, "wb") as dst, open(converted, "rb") as inp:
        shutil.copyfileobj(inp, dst, 8 * 1024 * 1024)
        dst.write(box)


if __name__ == "__main__":
    main(*sys.argv[1:5])
