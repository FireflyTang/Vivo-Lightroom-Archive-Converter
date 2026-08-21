#!/usr/bin/env python3
import sys,json,subprocess,shutil
from fractions import Fraction
import av

def annexb_nals(data):
    starts=[];i=0
    while i+3<len(data):
        if data[i:i+4]==b"\0\0\0\1":starts.append((i,4));i+=4
        elif data[i:i+3]==b"\0\0\1":starts.append((i,3));i+=3
        else:i+=1
    for n,(p,sc) in enumerate(starts):
        end=starts[n+1][0] if n+1<len(starts) else len(data);yield data[p+sc:end]

def access_units(path):
    prefix=[];units=[];current=None
    for nal in annexb_nals(open(path,"rb").read()):
        if not nal:continue
        ntype=(nal[0]>>1)&63
        if ntype==35:
            if current is not None:units.append(current)
            current=prefix+[nal] if not units else [nal];prefix=[]
        elif current is None:prefix.append(nal)
        else:current.append(nal)
    if current is not None:units.append(current)
    return [b"".join(len(n).to_bytes(4,"big")+n for n in au) for au in units]

def packets(container,stream):return [p for p in container.demux(stream) if p.dts is not None]

def main(source_path,encoded_path,injected_hevc,dv_template_path,output_path):
    source=av.open(source_path);encoded=av.open(encoded_path);template=av.open(dv_template_path)
    sv=source.streams.video[0];ev=encoded.streams.video[0];tv=template.streams.video[0]
    src_vp=packets(source,sv);enc_vp=packets(encoded,ev)
    source.close();source=av.open(source_path);sv=source.streams.video[0];sa=source.streams.audio[0]
    src_ap=packets(source,sa);aus=access_units(injected_hevc)
    if not (len(src_vp)==len(enc_vp)==len(aus)):raise ValueError(f"frame count mismatch: {len(src_vp)}, {len(enc_vp)}, {len(aus)}")
    src_pts=sorted(p.pts for p in src_vp);display_order=sorted(range(len(enc_vp)),key=lambda i:enc_vp[i].pts)
    mapped_pts=[None]*len(enc_vp)
    for rank,i in enumerate(display_order):mapped_pts[i]=src_pts[rank]
    first_delta=src_pts[1]-src_pts[0];last_delta=src_pts[-1]-src_pts[-2]
    def grid(k):
        if k<0:return src_pts[0]+k*first_delta
        if k>=len(src_pts):return src_pts[-1]+(k-len(src_pts)+1)*last_delta
        return src_pts[k]
    # Packets arrive in decode order. Shift that grid back by the maximum
    # reorder depth so DTS never follows its own PTS, while retaining the new
    # GOP's actual decode order.
    display_rank=[0]*len(enc_vp)
    for rank,i in enumerate(display_order):display_rank[i]=rank
    reorder_depth=max(i-display_rank[i] for i in range(len(enc_vp)))
    mapped_dts=[grid(i-reorder_depth) for i in range(len(enc_vp))]
    out=av.open(output_path,"w",options={"movflags":"+faststart","strict":"unofficial"})
    ov=out.add_stream_from_template(tv);ov.codec_context.extradata=ev.codec_context.extradata;ov.codec_context.codec_tag="hvc1";ov.time_base=sv.time_base;ov.metadata.update(sv.metadata)
    oa=out.add_stream_from_template(sa);oa.time_base=sa.time_base;out.metadata.update(source.metadata)
    ffprobe=shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
    meta_probe=json.loads(subprocess.check_output([ffprobe,"-v","error","-show_entries","format_tags","-of","json",source_path]))
    android=meta_probe.get("format",{}).get("tags",{}).get("com.android.version")
    if android is not None:out.metadata["com.android.version"]=android
    queue=[]
    for i,(ep,au) in enumerate(zip(enc_vp,aus)):
        p=av.Packet(au);p.pts=mapped_pts[i];p.dts=mapped_dts[i];p.duration=(mapped_dts[i+1]-mapped_dts[i]) if i+1<len(mapped_dts) else last_delta
        p.time_base=sv.time_base;p.is_keyframe=ep.is_keyframe;p.stream=ov;queue.append((Fraction(p.dts)*p.time_base,0,p))
    for ap in src_ap:
        p=av.Packet(bytes(ap));p.pts,p.dts,p.duration=ap.pts,ap.dts,ap.duration;p.time_base=ap.time_base;p.is_keyframe=ap.is_keyframe;p.stream=oa
        queue.append((Fraction(p.dts)*p.time_base,1,p))
    queue.sort(key=lambda x:(x[0],x[1]))
    last_by_stream={}
    for qi,(_,_,p) in enumerate(queue):
        try:out.mux(p)
        except Exception:
            print(f"mux failure queue={qi} stream={p.stream.index} pts={p.pts} dts={p.dts} duration={p.duration} last={last_by_stream.get(p.stream.index)}",file=sys.stderr)
            raise
        last_by_stream[p.stream.index]=(p.pts,p.dts,p.duration)
    out.close();source.close();encoded.close();template.close()
if __name__=="__main__":main(*sys.argv[1:6])
