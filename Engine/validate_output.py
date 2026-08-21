#!/usr/bin/env python3
import hashlib,json,struct,subprocess,sys,tempfile,uuid
from pathlib import Path

ARCHIVE_UUID=uuid.UUID("8d67d6b7-1137-5aed-b5d8-ea729a438af2").bytes

def run(a,stdout=subprocess.PIPE):
 p=subprocess.run([str(x) for x in a],stdout=stdout,stderr=subprocess.PIPE)
 if p.returncode:raise RuntimeError(p.stderr.decode(errors="replace")[-4000:])
 return p.stdout
def probe(ffprobe,p,extra):return json.loads(run([ffprobe,"-v","error",*extra,"-of","json",p]))
def packets(ffprobe,p,sel):return probe(ffprobe,p,["-select_streams",sel,"-show_packets","-show_entries","packet=pts,dts,duration,size,flags,pos"])["packets"]
def payloads(path,ps):
 b=open(path,"rb").read();return [b[int(x["pos"]):int(x["pos"])+int(x["size"])] for x in ps]
def packet_semantics(ps):return [{k:x.get(k) for k in ("pts","dts","duration","size","flags")} for x in ps]
def boxes(b,s=0,e=None):
 e=len(b) if e is None else e;p=s
 while p+8<=e:
  z=struct.unpack_from(">I",b,p)[0];t=b[p+4:p+8];h=8
  if z==1:z=struct.unpack_from(">Q",b,p+8)[0];h=16
  elif z==0:z=e-p
  if z<h or p+z>e:raise ValueError("bad MP4")
  yield p,z,t,h;p+=z
def uuids(path):
 b=open(path,"rb").read();return [b[p:p+z] for p,z,t,h in boxes(b) if t==b"uuid"]
def kids(b,x):
 p,z,t,h=x;return list(boxes(b,p+h,p+z))
def child(b,x,t):return next(y for y in kids(b,x) if y[2]==t)
def handler(b,tr):
 h=child(b,child(b,tr,b"mdia"),b"hdlr");return b[h[0]+h[3]+8:h[0]+h[3]+12]
def video_matrix(path):
 b=open(path,"rb").read();mo=next(x for x in boxes(b) if x[2]==b"moov")
 tr=next(x for x in kids(b,mo) if x[2]==b"trak" and handler(b,x)==b"vide")
 tk=child(b,tr,b"tkhd");q=tk[0]+tk[3];v=b[q];off=q+(52 if v else 40)
 return b[off:off+36]
def mdhd_values(path,kind):
 b=open(path,"rb").read();mo=next(x for x in boxes(b) if x[2]==b"moov")
 tr=next(x for x in kids(b,mo) if x[2]==b"trak" and handler(b,x)==kind)
 md=child(b,child(b,tr,b"mdia"),b"mdhd");q=md[0]+md[3];v=b[q]
 duration=struct.unpack_from(">Q" if v else ">I",b,q+4+(20 if v else 12))[0]
 language=struct.unpack_from(">H",b,q+4+(28 if v else 16))[0]
 return duration,language
def dovi_box(path):
 b=open(path,"rb").read();mo=next(x for x in boxes(b) if x[2]==b"moov")
 tr=next(x for x in kids(b,mo) if x[2]==b"trak" and handler(b,x)==b"vide")
 stsd=child(b,child(b,child(b,child(b,tr,b"mdia"),b"minf"),b"stbl"),b"stsd")
 p=stsd[0]+stsd[3]+8;z=struct.unpack_from(">I",b,p)[0]
 x=next((x for x in boxes(b,p+86,p+z) if x[2] in (b"dvvC",b"dvcC")),None)
 if not x:raise ValueError("视频样本描述缺少Dolby Vision配置box")
 return b[x[0]:x[0]+x[1]]
def archive_provenance(path):
 b=open(path,"rb").read();records=[]
 for p,z,t,h in boxes(b):
  if t==b"uuid" and z>=h+16 and b[p+h:p+h+16]==ARCHIVE_UUID:
   records.append(json.loads(b[p+h+16:p+z]))
 if len(records)!=1:raise ValueError("档案provenance UUID数量错误")
 return records[0]
def main(src,out,dovi,ffmpeg,ffprobe,mode="cpu"):
 src=Path(src);out=Path(out)
 si=probe(ffprobe,src,["-show_streams","-show_format"]);oi=probe(ffprobe,out,["-show_streams","-show_format"])
 if len(oi["streams"])!=3:raise ValueError("输出轨道数不是3")
 v=oi["streams"][0]
 expected={"codec_name":"hevc","profile":"Main 10","codec_tag_string":"hvc1","width":3840,"height":2160,"pix_fmt":"yuv420p10le","color_range":"tv","color_space":"bt2020nc","color_transfer":"arib-std-b67","color_primaries":"bt2020","time_base":"1/90000"}
 for k,w in expected.items():
  if v.get(k)!=w:raise ValueError(f"输出视频{k}错误：{v.get(k)}")
 if video_matrix(src)!=video_matrix(out):raise ValueError("视频显示旋转矩阵未原样保留")
 if dovi_box(src)!=dovi_box(out):raise ValueError("Dolby Vision配置box未原样保留")
 for kind,label in ((b"vide","视频"),(b"soun","AAC"),(b"meta","EIS")):
  if mdhd_values(src,kind)!=mdhd_values(out,kind):raise ValueError(f"{label}媒体时长或语言代码不一致")
 sd=[x for x in v.get("side_data_list",[]) if x.get("side_data_type")=="DOVI configuration record"]
 if len(sd)!=1:raise ValueError("输出未被识别为Dolby Vision")
 expected_dv={"dv_profile":8,"dv_level":9,"rpu_present_flag":1,"el_present_flag":0,"bl_present_flag":1,"dv_bl_signal_compatibility_id":4}
 for k,w in expected_dv.items():
  if sd[0].get(k)!=w:raise ValueError(f"输出Dolby Vision {k}错误")
 print("VERIFY\tPASS\t视频参数、HDR、方向矩阵与Dolby Vision配置",flush=True)
 svp=packets(ffprobe,src,"v:0");ovp=packets(ffprobe,out,"v:0")
 if len(svp)!=len(ovp) or sorted(int(x["pts"]) for x in svp)!=sorted(int(x["pts"]) for x in ovp):raise ValueError("视频帧数或PTS集合不一致")
 print(f"VERIFY\tPASS\t视频帧数与显示时间戳（{len(ovp)}帧）",flush=True)
 for sel,label in (("a:0","AAC"),("d:0","EIS")):
  a=packets(ffprobe,src,sel);b=packets(ffprobe,out,sel)
  if packet_semantics(a)!=packet_semantics(b):raise ValueError(f"{label}包时间属性不一致")
  if [hashlib.sha256(x).digest() for x in payloads(src,a)] != [hashlib.sha256(x).digest() for x in payloads(out,b)]:raise ValueError(f"{label}包内容不一致")
  print(f"VERIFY\tPASS\t{label}包内容与时间逐包一致（{len(b)}包）",flush=True)
 with tempfile.TemporaryDirectory(prefix="vac-verify-") as td:
  td=Path(td);sr=td/"s.hevc";orr=td/"o.hevc";a=td/"s.rpu";b=td/"o.rpu"
  for p,r in ((src,sr),(out,orr)):run([ffmpeg,"-v","error","-i",p,"-map","0:v:0","-c","copy","-bsf:v","hevc_mp4toannexb","-f","hevc",r],stdout=subprocess.DEVNULL)
  run([dovi,"extract-rpu","-i",sr,"-o",a],stdout=subprocess.DEVNULL);run([dovi,"extract-rpu","-i",orr,"-o",b],stdout=subprocess.DEVNULL)
  if a.read_bytes()!=b.read_bytes():raise ValueError("Dolby Vision RPU不一致")
  trace=subprocess.run([ffmpeg,"-v","trace","-i",orr,"-map","0:v:0","-c","copy","-bsf:v","trace_headers","-f","null","-"],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE).stderr.decode(errors="replace")
  tids=set()
  for line in trace.splitlines():
   if "nal_unit_type:" in line and "temporal_id:" in line:
    try:tids.add(int(line.rsplit("temporal_id:",1)[1].strip()))
    except ValueError:pass
  lines=trace.splitlines()
  if not all(any(name in line and line.rstrip().endswith("= 0") for line in lines) for name in ("sps_max_sub_layers_minus1","vps_max_sub_layers_minus1")):raise ValueError("输出VPS/SPS不是单时间层")
  if tids!={0}:raise ValueError(f"输出temporal_id不是单层：{sorted(tids)}")
  print("VERIFY\tPASS\tDolby Vision RPU逐字节一致且输出为单时间层",flush=True)
 run([ffmpeg,"-v","error","-i",out,"-map","0","-f","null","-"],stdout=subprocess.DEVNULL)
 print("VERIFY\tPASS\t全部轨道完整解码读取",flush=True)
 sus=uuids(src);ous=uuids(out)
 for u in sus:
  if u not in ous:raise ValueError("原始顶层UUID未保留")
 top=[t for _,_,t,_ in boxes(out.read_bytes())]
 if top!=[b"ftyp",b"moov",b"free",b"mdat",b"mdat",b"uuid",b"uuid"]:raise ValueError(f"输出顶层MP4结构异常：{top}")
 tags=oi["format"].get("tags",{});st=si["format"].get("tags",{})
 for k in ("major_brand","minor_version","compatible_brands","creation_time","location","location-eng","com.android.version"):
  if tags.get(k)!=st.get(k):raise ValueError(f"元数据{k}不一致")
 for i,(ss,os_) in enumerate(zip(si["streams"],oi["streams"])):
  if ss.get("tags",{})!=os_.get("tags",{}):raise ValueError(f"第{i+1}条轨道元数据不一致")
 print("VERIFY\tPASS\tMP4结构、UUID、拍摄元数据与轨道元数据",flush=True)
 provenance=archive_provenance(out);conversion=provenance.get("conversion",{})
 expected=("Apple VideoToolbox HEVC hardware encoder","VideoToolbox quality 65") if mode=="hardware" else ("x265","CRF 8")
 if (conversion.get("encoder"),conversion.get("rate_control"))!=expected:
  raise ValueError("档案provenance编码器或码率控制记录错误")
 print("VERIFY\tPASS\t档案来源与转换方式记录",flush=True)
 print("VERIFIED\tALL\t输出完整复检通过",flush=True)
if __name__=="__main__":main(*sys.argv[1:7])
