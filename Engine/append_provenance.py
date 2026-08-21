#!/usr/bin/env python3
import hashlib,json,struct,sys,uuid
U=uuid.UUID("8d67d6b7-1137-5aed-b5d8-ea729a438af2")
def main(src,converted,out,mode="cpu"):
 s=open(src,"rb").read();b=open(converted,"rb").read()
 encoder="Apple VideoToolbox HEVC hardware encoder" if mode=="hardware" else "x265"
 rate_control="VideoToolbox quality 65" if mode=="hardware" else "CRF 8"
 record={"schema":"video.archive.provenance.v1","source":{"filename":__import__('os').path.basename(src),"size_bytes":len(s),"sha256":hashlib.sha256(s).hexdigest(),"video_codec":"HEVC Main 10","video_temporal_layers":3,"video_level":"5.0","resolution":"3840x2160","color":"10-bit BT.2020 HLG"},"conversion":{"purpose":"Lightroom Classic compatibility","video_codec":"HEVC Main 10","video_temporal_layers":1,"encoder":encoder,"rate_control":rate_control,"audio":"original AAC packets and timing preserved","dolby_vision":"original RPU payloads preserved","eis":"original com.android.camera.eisFrameVideo packets preserved","video_timing":"original presentation timestamps preserved"},"note":"Source temporal_layers_count=3 is provenance, not an active property of this converted single-layer bitstream."}
 p=json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode();box=struct.pack(">I4s",24+len(p),b"uuid")+U.bytes+p;open(out,"wb").write(b+box)
if __name__=="__main__":main(*sys.argv[1:5])
