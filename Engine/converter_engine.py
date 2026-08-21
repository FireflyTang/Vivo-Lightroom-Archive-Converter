#!/usr/bin/env python3
import hashlib, importlib.util, json, os, shutil, struct, subprocess, sys, tempfile, uuid
from pathlib import Path

RESOURCE = Path(os.environ.get("VAC_RESOURCE_DIR", Path(__file__).resolve().parents[1]))
ENGINE = RESOURCE / "Engine"
DOVI = Path(shutil.which("dovi_tool") or ENGINE / "dovi_tool")
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
PYTHON = sys.executable

EXPECTED_PATHS = ["/ftyp","/free","/mdat","/moov","/moov/mvhd","/moov/udta","/moov/udta/©xyz","/moov/meta","/moov/trak","/moov/trak/tkhd","/moov/trak/edts","/moov/trak/edts/elst","/moov/trak/mdia","/moov/trak/mdia/mdhd","/moov/trak/mdia/hdlr","/moov/trak/mdia/minf","/moov/trak/mdia/minf/vmhd","/moov/trak/mdia/minf/dinf","/moov/trak/mdia/minf/dinf/dref","/moov/trak/mdia/minf/stbl","/moov/trak/mdia/minf/stbl/stsd","/moov/trak/mdia/minf/stbl/stts","/moov/trak/mdia/minf/stbl/ctts","/moov/trak/mdia/minf/stbl/stss","/moov/trak/mdia/minf/stbl/stsz","/moov/trak/mdia/minf/stbl/stsc","/moov/trak/mdia/minf/stbl/co64","/moov/trak","/moov/trak/tkhd","/moov/trak/mdia","/moov/trak/mdia/mdhd","/moov/trak/mdia/hdlr","/moov/trak/mdia/minf","/moov/trak/mdia/minf/smhd","/moov/trak/mdia/minf/dinf","/moov/trak/mdia/minf/dinf/dref","/moov/trak/mdia/minf/stbl","/moov/trak/mdia/minf/stbl/stsd","/moov/trak/mdia/minf/stbl/stts","/moov/trak/mdia/minf/stbl/stsz","/moov/trak/mdia/minf/stbl/stsc","/moov/trak/mdia/minf/stbl/co64","/moov/trak","/moov/trak/tkhd","/moov/trak/mdia","/moov/trak/mdia/mdhd","/moov/trak/mdia/hdlr","/moov/trak/mdia/minf","/moov/trak/mdia/minf/nmhd","/moov/trak/mdia/minf/dinf","/moov/trak/mdia/minf/dinf/dref","/moov/trak/mdia/minf/stbl","/moov/trak/mdia/minf/stbl/stsd","/moov/trak/mdia/minf/stbl/stts","/moov/trak/mdia/minf/stbl/stsz","/moov/trak/mdia/minf/stbl/stsc","/moov/trak/mdia/minf/stbl/co64","/uuid"]
VIVO_UUID = uuid.UUID("7669766f-4d65-6469-6145-7874496e666f").bytes
VIVO_KEYS = {"com.android.camera.temperature","com.android.camera.takenmodel","com.android.camera.moduleid","com.android.camera.camerafacing","VideoModuleId","Lens","MotionTrack","Facing","FilmFormat","MicDevice","VideoBeauty","VideoSuperNight","VideoAeLux ","videoAngleExpand","VideoAvailableMemory","CpuUsage","StartShellTempure","StartBoardTempure","VideoIcState","EndShellTempure","EndBoardTempure","version"}
EXPECTED_VIDEO_MATRIX = struct.pack(">9i",0,65536,0,-65536,0,0,0,0,1073741824)
EXPECTED_STSD_SHA256 = {
    b"vide":"d7196d4b299b42ac73a44f728ca4342349f45090eba3068cf59c1f31d0acc40b",
    b"soun":"db3c7a70f068b3f6caa4689c26dd705ce78b9da57d00f176fb05c8ea8d69083a",
    b"meta":"81f8f8f1205857a67b66c4e1d5649f93d3696564734d162674245526c743eee0",
}

def run(args, capture=True, check=True, stderr=None):
    p = subprocess.run([str(x) for x in args], stdout=subprocess.PIPE if capture else None,
                       stderr=stderr if stderr is not None else subprocess.PIPE, check=False)
    if check and p.returncode:
        msg = (p.stderr or b"").decode("utf-8", "replace")[-5000:]
        raise RuntimeError(f"命令失败：{Path(str(args[0])).name}\n{msg}")
    return p.stdout if capture else b""

def probe(path):
    return json.loads(run([FFPROBE,"-v","error","-show_streams","-show_format","-of","json",path]))

def boxes(buf, start=0, end=None):
    end = len(buf) if end is None else end; p = start
    while p + 8 <= end:
        size = struct.unpack_from(">I",buf,p)[0]; typ=bytes(buf[p+4:p+8]); head=8
        if size == 1: size=struct.unpack_from(">Q",buf,p+8)[0]; head=16
        elif size == 0: size=end-p
        if size < head or p+size > end: raise ValueError(f"损坏的 MP4 box {typ!r} @ {p}")
        yield (p,size,typ,head); p += size

def children(buf, box, meta=False):
    p,z,t,h=box; return list(boxes(buf,p+h+(4 if meta else 0),p+z))

def child(buf, box, typ, meta=False): return next(x for x in children(buf,box,meta) if x[2]==typ)

def handler(buf,tr):
    h=child(buf,child(buf,tr,b"mdia"),b"hdlr")
    return bytes(buf[h[0]+h[3]+8:h[0]+h[3]+12])

def video_matrix(buf):
    moov=next(x for x in boxes(buf) if x[2]==b"moov")
    track=next(x for x in children(buf,moov) if x[2]==b"trak" and handler(buf,x)==b"vide")
    tkhd=child(buf,track,b"tkhd"); q=tkhd[0]+tkhd[3]; version=buf[q]
    off=q+(52 if version else 40)
    return bytes(buf[off:off+36])

def sample_description_hashes(buf):
    moov=next(x for x in boxes(buf) if x[2]==b"moov"); result={}
    for track in (x for x in children(buf,moov) if x[2]==b"trak"):
        typ=handler(buf,track)
        stsd=child(buf,child(buf,child(buf,child(buf,track,b"mdia"),b"minf"),b"stbl"),b"stsd")
        result[typ]=hashlib.sha256(bytes(buf[stsd[0]:stsd[0]+stsd[1]])).hexdigest()
    return result

def structure_paths(buf):
    containers={b"moov":0,b"trak":0,b"mdia":0,b"minf":0,b"dinf":0,b"stbl":0,b"edts":0,b"udta":0,b"meta":4,b"ilst":0}
    out=[]
    def walk(s,e,path=""):
        for p,z,t,h in boxes(buf,s,e):
            q=path+"/"+t.decode("latin1"); out.append(q)
            if t in containers:
                try: walk(p+h+containers[t],p+z,q)
                except ValueError: pass
    walk(0,len(buf)); return out

def top_uuid(buf):
    result=[]
    for p,z,t,h in boxes(buf):
        if t==b"uuid" and z>=h+16: result.append((bytes(buf[p+h:p+h+16]),bytes(buf[p:p+z]),bytes(buf[p+h+16:p+z])))
    return result

def vivo_json(payload):
    if not payload.startswith(b"vivo"): raise ValueError("vivo UUID 缺少 vivo 前缀")
    start=payload.find(b"{"); end=payload.rfind(b"}")
    if start<0 or end<start: raise ValueError("vivo UUID JSON 无效")
    return json.loads(payload[start:end+1])

def rate(value):
    if not value or value=="0/0": return None
    a,b=value.split("/"); return float(a)/float(b)

def temporal_audit(path):
    with tempfile.TemporaryDirectory(prefix="vac-audit-") as td:
        raw=Path(td)/"source.hevc"; trace=Path(td)/"trace.txt"
        run([FFMPEG,"-v","error","-i",path,"-map","0:v:0","-c","copy","-bsf:v","hevc_mp4toannexb","-f","hevc",raw],capture=False)
        with open(trace,"wb") as err:
            subprocess.run([FFMPEG,"-v","trace","-i",raw,"-map","0:v:0","-c","copy","-bsf:v","trace_headers","-f","null","-"],stdout=subprocess.DEVNULL,stderr=err)
        text=trace.read_text(errors="replace")
        tids=set()
        for line in text.splitlines():
            if "nal_unit_type:" in line and "temporal_id:" in line:
                try: tids.add(int(line.rsplit("temporal_id:",1)[1].strip()))
                except ValueError: pass
        return ("sps_max_sub_layers_minus1" in text and " = 2" in text,
                "vps_max_sub_layers_minus1" in text and " = 2" in text, tids)

def inspect(path):
    path=Path(path); reasons=[]; temporal_checked=False
    try:
        data=path.read_bytes(); info=probe(path)
        paths=structure_paths(data)
        if paths != EXPECTED_PATHS: reasons.append("MP4 box 层级或排列与基准文件不同")
        matrix=video_matrix(data)
        if matrix != EXPECTED_VIDEO_MATRIX: reasons.append("视频轨道显示矩阵不匹配（要求原始90°旋转矩阵）")
        stsd_hashes=sample_description_hashes(data)
        if stsd_hashes != EXPECTED_STSD_SHA256: reasons.append("视频、音频或EIS样本描述与基准文件不完全一致")
        streams=info.get("streams",[])
        if len(streams)!=3: reasons.append(f"必须正好有3条轨道，实际为{len(streams)}")
        types=[s.get("codec_type") for s in streams]
        if types != ["video","audio","data"]: reasons.append(f"轨道顺序不匹配：{types}")
        v=streams[0] if streams else {}; a=streams[1] if len(streams)>1 else {}; d=streams[2] if len(streams)>2 else {}
        expected_video={"codec_name":"hevc","profile":"Main 10","codec_tag_string":"hvc1","width":3840,"height":2160,"pix_fmt":"yuv420p10le","color_range":"tv","color_space":"bt2020nc","color_transfer":"arib-std-b67","color_primaries":"bt2020","time_base":"1/90000"}
        for k,want in expected_video.items():
            if v.get(k)!=want: reasons.append(f"视频 {k} 不匹配：{v.get(k)!r}，要求 {want!r}")
        if v.get("level")!=150: reasons.append(f"原始HEVC Level必须为5.0，实际代码为{v.get('level')}")
        if abs((rate(v.get("r_frame_rate")) or 0)-60)>0.001: reasons.append("名义帧率不是60 fps")
        if not (a.get("codec_name")=="aac" and a.get("profile")=="LC" and a.get("codec_tag_string")=="mp4a" and a.get("sample_rate")=="48000" and a.get("channels")==2 and a.get("time_base")=="1/48000"):
            reasons.append("AAC-LC 48kHz 双声道音轨结构不匹配")
        if not (d.get("codec_tag_string")=="mett" and d.get("time_base")=="1/90000" and d.get("tags",{}).get("handler_name")=="MetadHandle"):
            reasons.append("EIS metadata轨道结构不匹配")
        tags=info.get("format",{}).get("tags",{})
        if [tags.get("major_brand"),tags.get("minor_version"),tags.get("compatible_brands")] != ["mp42","0","isommp42dby1"]:
            reasons.append("MP4 brands与基准不匹配")
        required_tags={"creation_time","location","location-eng","com.android.version"}
        if not required_tags.issubset(tags): reasons.append("缺少创建时间、GPS或Android版本字段")
        dv=[x for x in v.get("side_data_list",[]) if x.get("side_data_type")=="DOVI configuration record"]
        if not dv: reasons.append("缺少Dolby Vision配置")
        else:
            x=dv[0]
            expected={"dv_profile":8,"dv_level":9,"rpu_present_flag":1,"el_present_flag":0,"bl_present_flag":1,"dv_bl_signal_compatibility_id":4}
            for k,want in expected.items():
                if x.get(k)!=want: reasons.append(f"Dolby Vision {k} 不匹配")
        vus=[x for x in top_uuid(data) if x[0]==VIVO_UUID]
        if len(vus)!=1: reasons.append("必须正好有一个基准Vivo私有UUID")
        else:
            obj=vivo_json(vus[0][2])
            if set(obj)!=VIVO_KEYS: reasons.append("Vivo私有UUID的JSON字段集合与基准不同")
            if obj.get("com.android.camera.takenmodel")!="vivo X200 Ultra": reasons.append("拍摄设备不是Vivo X200 Ultra")
        if not reasons:
            temporal_checked=True
            sps,vps,tids=temporal_audit(path)
            if not (sps and vps): reasons.append("VPS/SPS没有同时声明三个时间子层")
            if not {0,1,2}.issubset(tids): reasons.append(f"temporal ID集合不包含0、1、2：{sorted(tids)}")
        obj = vivo_json(vus[0][2]) if vus else {}
        def check(name,keywords,detail,temporal=False):
            failure=next((r for r in reasons if any(k in r for k in keywords)),None)
            if temporal and not temporal_checked:
                return {"name":name,"state":"skipped","detail":"前置结构检查未通过，未运行耗时的码流层级审计"}
            return {"name":name,"state":"failed" if failure else "passed","detail":failure or detail}
        checks=[
            check("MP4容器box层级与排列",["MP4 box"],f"{len(paths)}个box路径，与已验证基准完全一致"),
            check("视频方向与Display Matrix",["显示矩阵"],"原始90°旋转矩阵逐字节匹配"),
            check("三条轨道样本描述指纹",["样本描述"],"HEVC/Dolby Vision、AAC与EIS stsd逐字节匹配"),
            check("轨道数量与顺序",["正好有3条轨道","轨道顺序"],f"{types}（视频、AAC音频、EIS数据）"),
            check("HEVC Main 10视频参数",["视频 "],f"{v.get('codec_tag_string')} · {v.get('profile')} · {v.get('width')}×{v.get('height')} · {v.get('pix_fmt')}"),
            check("HDR色彩与HEVC Level",["Level"],f"BT.2020 HLG · Limited range · Level {v.get('level')}"),
            check("60 fps名义帧率",["名义帧率"],f"r_frame_rate={v.get('r_frame_rate')} · avg={rate(v.get('avg_frame_rate'))}"),
            check("AAC原始音轨结构",["AAC-LC"],f"AAC-LC · {a.get('sample_rate')} Hz · {a.get('channels')}声道 · time_base={a.get('time_base')}"),
            check("EIS metadata轨道",["EIS metadata"],f"mett / MetadHandle · {d.get('nb_frames','?')}个包 · time_base={d.get('time_base')}"),
            check("MP4 brands",["MP4 brands"],f"{tags.get('major_brand')} · {tags.get('compatible_brands')}"),
            check("创建时间、GPS与Android字段",["缺少创建时间"],f"{tags.get('creation_time')} · {tags.get('location')}"),
            check("Dolby Vision Profile 8配置",["Dolby Vision","缺少Dolby Vision"],"Profile 8.4 · RPU存在 · HLG兼容基础层"),
            check("Vivo私有UUID及字段集合",["Vivo私有UUID","JSON字段集合","拍摄设备"],f"Vivo X200 Ultra · {len(obj)}个厂商字段"),
            check("三时间子层码流结构",["VPS/SPS","temporal ID"],"VPS/SPS声明3层，temporal_id包含0、1、2",temporal=True),
        ]
        return {"accepted":not reasons,"path":str(path),"name":path.name,"size_bytes":path.stat().st_size,
                "duration":float(info.get("format",{}).get("duration",0) or 0),"width":v.get("width"),"height":v.get("height"),
                "frame_count":int(v.get("nb_frames",0) or 0),"fps":rate(v.get("avg_frame_rate")),"video_codec":v.get("codec_name"),
                "video_profile":v.get("profile"),"pixel_format":v.get("pix_fmt"),
                "audio_description":f"AAC-LC {a.get('sample_rate','?')} Hz {a.get('channels','?')}声道",
                "dolby_vision":"Dolby Vision Profile 8" if dv else None,"eis_packets":int(d.get("nb_frames",0) or 0),
                "creation_time":tags.get("creation_time"),"location":tags.get("location"),"device":obj.get("com.android.camera.takenmodel"),"reasons":reasons,"checks":checks}
    except Exception as e:
        return {"accepted":False,"path":str(path),"name":path.name,"size_bytes":path.stat().st_size if path.exists() else 0,
                "duration":None,"width":None,"height":None,"frame_count":None,"fps":None,"video_codec":None,"video_profile":None,
                "pixel_format":None,"audio_description":None,"dolby_vision":None,"eis_packets":None,"creation_time":None,"location":None,"device":None,
                "reasons":[f"检查异常：{e}"],"checks":[{"name":"读取并解析输入文件","state":"failed","detail":str(e)}]}

def progress(value,msg): print(f"PROGRESS\t{value:.3f}\t{msg}",flush=True)

def convert(path, hardware=False):
    missing=[]
    for name,tool in (("ffmpeg",FFMPEG),("ffprobe",FFPROBE),("dovi_tool",DOVI)):
        if not Path(tool).is_file() or not os.access(tool,os.X_OK): missing.append(name)
    if importlib.util.find_spec("av") is None: missing.append("PyAV")
    if missing: raise RuntimeError("缺少运行依赖："+", ".join(missing)+"。请先运行 install_dependencies.command，然后重新打开App。")
    src=Path(path).resolve(); audit=inspect(src)
    if not audit["accepted"]: raise RuntimeError("输入严格检查未通过：\n"+"\n".join(audit["reasons"]))
    suffix="_LR_VT_Q65_archive.mp4" if hardware else "_LR_CRF8_archive.mp4"
    out=src.with_name(src.stem+suffix)
    if out.exists(): raise RuntimeError(f"目标已存在，拒绝覆盖：{out}")
    temp_out=src.with_name("."+out.name+".incomplete")
    if temp_out.exists(): temp_out.unlink()
    with tempfile.TemporaryDirectory(prefix="vivo-lr-archive-",dir=src.parent) as td:
        td=Path(td); raw_src=td/"source.hevc"; encoded=td/"encoded.hevc"; encoded_mp4=td/"encoded.mp4"
        rpu=td/"rpu.bin"; dv_hevc=td/"dv.hevc"; dv_template=td/"dv_template.mp4"; avmux=td/"avmux.mp4"; eis=td/"eis.mp4"; finalmeta=td/"finalmeta.mp4"
        progress(.03,"提取并核验Dolby Vision")
        run([FFMPEG,"-v","error","-i",src,"-map","0:v:0","-c","copy","-bsf:v","hevc_mp4toannexb","-f","hevc",raw_src],capture=False)
        run([DOVI,"extract-rpu","-i",raw_src,"-o",rpu],capture=False)
        progress(.10,"VideoToolbox Q65 单时间层硬件编码" if hardware else "x265 CRF 8 单时间层编码")
        if hardware:
            # VideoToolbox is Apple's hardware encoder (Metal itself does not
            # accelerate x265). Keep this explicitly opt-in: its rate control,
            # GOP and parameter-set output are not byte/structure equivalent
            # to the validated libx265 CRF 8 archive path.
            encode_args = ["-c:v","hevc_videotoolbox","-profile:v","main10","-q:v","65","-pix_fmt","p010le"]
        else:
            encode_args = ["-c:v","libx265","-preset","medium","-crf","8","-pix_fmt","yuv420p10le","-x265-params","keyint=60:min-keyint=1:high-tier=1"]
        run([FFMPEG,"-hide_banner","-loglevel","error","-noautorotate","-i",src,"-map","0:v:0","-an","-sn","-dn",*encode_args,"-color_range","tv","-color_primaries","bt2020","-color_trc","arib-std-b67","-colorspace","bt2020nc","-tag:v","hvc1",encoded_mp4],capture=False)
        # Extract the exact encoded access units from the timestamped MP4. A raw
        # encode followed by remuxing would lose B-frame presentation order.
        run([FFMPEG,"-v","error","-i",encoded_mp4,"-map","0:v:0","-c","copy","-bsf:v","hevc_mp4toannexb","-f","hevc",encoded],capture=False)
        progress(.62,"重新注入原始Dolby Vision RPU")
        run([DOVI,"inject-rpu","-i",encoded,"-r",rpu,"-o",dv_hevc],capture=False)
        run([FFMPEG,"-v","error","-r","60","-i",dv_hevc,"-c","copy","-tag:v","hvc1",dv_template],capture=False)
        progress(.70,"恢复原始显示时间和AAC")
        run([PYTHON,ENGINE/"mux_exact.py",src,encoded_mp4,dv_hevc,dv_template,avmux],capture=False)
        progress(.77,"复制原始EIS轨道")
        run([PYTHON,ENGINE/"inject_eis.py",src,avmux,eis],capture=False)
        progress(.83,"恢复容器、GPS和厂商元数据")
        run([PYTHON,ENGINE/"finalize_mp4.py",src,eis,finalmeta],capture=False)
        run([PYTHON,ENGINE/"append_provenance.py",src,finalmeta,temp_out,"hardware" if hardware else "cpu"],capture=False)
        progress(.88,"逐项验证输出")
        run([PYTHON,ENGINE/"validate_output.py",src,temp_out,DOVI,FFMPEG,FFPROBE,"hardware" if hardware else "cpu"],capture=False)
        os.utime(temp_out,ns=(src.stat().st_atime_ns,src.stat().st_mtime_ns))
        os.replace(temp_out,out)
    progress(1,"完成")
    print(f"OUTPUT\t{out}",flush=True)

def main():
    if len(sys.argv) not in {3,4} or sys.argv[1] not in {"inspect","convert"}: raise SystemExit("usage: converter_engine.py inspect|convert FILE [hardware]")
    if sys.argv[1]=="inspect": print(json.dumps(inspect(sys.argv[2]),ensure_ascii=False))
    else:
        try: convert(sys.argv[2], hardware=(len(sys.argv)==4 and sys.argv[3]=="hardware"))
        except Exception as e:
            hardware=(len(sys.argv)==4 and sys.argv[3]=="hardware")
            suffix="_LR_VT_Q65_archive.mp4" if hardware else "_LR_CRF8_archive.mp4"
            p=Path(sys.argv[2]).resolve(); tmp=p.with_name("."+p.stem+suffix+".incomplete")
            if tmp.exists(): tmp.unlink()
            print(str(e),file=sys.stderr)
            raise SystemExit(1)
if __name__=="__main__": main()
