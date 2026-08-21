#!/usr/bin/env python3
import shutil,struct,sys

def boxes(b,s=0,e=None):
 e=len(b) if e is None else e;p=s
 while p+8<=e:
  z=struct.unpack_from(">I",b,p)[0];t=bytes(b[p+4:p+8]);h=8
  if z==1:z=struct.unpack_from(">Q",b,p+8)[0];h=16
  elif z==0:z=e-p
  if z<h or p+z>e:raise ValueError(f"bad {t!r}@{p}")
  yield p,z,t,h;p+=z
def kids(b,x,meta=False):p,z,t,h=x;return list(boxes(b,p+h+(4 if meta else 0),p+z))
def child(b,x,t,meta=False):return next(y for y in kids(b,x,meta) if y[2]==t)
def handler(b,tr):h=child(b,child(b,tr,b"mdia"),b"hdlr");return bytes(b[h[0]+h[3]+8:h[0]+h[3]+12])
def fullbox_values(b,x):q=x[0]+x[3];return q,b[q]
def read_mvhd(b,m):
 q,v=fullbox_values(b,m);base=q+4;ts=struct.unpack_from(">I",b,base+(16 if v else 8))[0];du=struct.unpack_from(">Q" if v else ">I",b,base+(20 if v else 12))[0]
 return ts,du
def set_mvhd(b,m,ts,du,nextid):
 q,v=fullbox_values(b,m);base=q+4;struct.pack_into(">I",b,base+(16 if v else 8),ts);struct.pack_into(">Q" if v else ">I",b,base+(20 if v else 12),du);struct.pack_into(">I",b,m[0]+m[1]-4,nextid)
def tkdur(b,tr):
 x=child(b,tr,b"tkhd");q,v=fullbox_values(b,x);off=q+4+(24 if v else 16);return struct.unpack_from(">Q" if v else ">I",b,off)[0]
def settk(b,tr,val):
 x=child(b,tr,b"tkhd");q,v=fullbox_values(b,x);struct.pack_into(">Q" if v else ">I",b,q+4+(24 if v else 16),val)
def tk_matrix(b,tr):
 x=child(b,tr,b"tkhd");q,v=fullbox_values(b,x);off=q+(52 if v else 40);return bytes(b[off:off+36])
def set_tk_matrix(b,tr,value):
 if len(value)!=36:raise ValueError("invalid tkhd display matrix")
 x=child(b,tr,b"tkhd");q,v=fullbox_values(b,x);off=q+(52 if v else 40);b[off:off+36]=value
def md_duration(b,tr):
 x=child(b,child(b,tr,b"mdia"),b"mdhd");q,v=fullbox_values(b,x);off=q+4+(20 if v else 12);return struct.unpack_from(">Q" if v else ">I",b,off)[0]
def set_md_duration(b,tr,val):
 x=child(b,child(b,tr,b"mdia"),b"mdhd");q,v=fullbox_values(b,x);struct.pack_into(">Q" if v else ">I",b,q+4+(20 if v else 12),val)
def md_language(b,tr):
 x=child(b,child(b,tr,b"mdia"),b"mdhd");q,v=fullbox_values(b,x);off=q+4+(28 if v else 16);return struct.unpack_from(">H",b,off)[0]
def set_md_language(b,tr,val):
 x=child(b,child(b,tr,b"mdia"),b"mdhd");q,v=fullbox_values(b,x);off=q+4+(28 if v else 16);struct.pack_into(">H",b,off,val)
def set_name(b,tr,name):
 x=child(b,child(b,tr,b"mdia"),b"hdlr");s=x[0]+x[3]+24;e=x[0]+x[1];v=name.encode()+b"\0";b[s:e]=v+b"\0"*(e-s-len(v))
def set_first_elst(b,tr,duration):
 ed=next((x for x in kids(b,tr) if x[2]==b"edts"),None)
 if not ed:return
 el=child(b,ed,b"elst");q,v=fullbox_values(b,el);struct.pack_into(">Q" if v else ">I",b,q+8,duration)
def resize_remove(b,moov,tr,box):
 n=box[1];struct.pack_into(">I",b,moov[0],moov[1]-n);struct.pack_into(">I",b,tr[0],tr[1]-n);del b[box[0]:box[0]+n];return n
def grow_free(b,n):
 fr=next(x for x in boxes(b) if x[2]==b"free");old=bytes(b[fr[0]:fr[0]+fr[1]]);new=struct.pack(">I4s",fr[1]+n,b"free")+old[8:]+b"\0"*n;b[fr[0]:fr[0]+fr[1]]=new
def remove_lavf(b):
 mo=next(x for x in boxes(b) if x[2]==b"moov");ud=next((x for x in kids(b,mo) if x[2]==b"udta"),None)
 if not ud:return b
 me=next((x for x in kids(b,ud) if x[2]==b"meta"),None)
 if not me:return b
 il=next((x for x in kids(b,me,True) if x[2]==b"ilst"),None)
 if not il:return b
 too=next((x for x in kids(b,il) if x[2]==b"\xa9too"),None)
 if not too:return b
 n=too[1]
 for x in (mo,ud,me,il):struct.pack_into(">I",b,x[0],x[1]-n)
 del b[too[0]:too[0]+n];grow_free(b,n);return b
def replace_udta(b,source):
 sm=next(x for x in boxes(source) if x[2]==b"moov");su=child(source,sm,b"udta");orig=bytes(source[su[0]:su[0]+su[1]])
 mo=next(x for x in boxes(b) if x[2]==b"moov");du=child(b,mo,b"udta");delta=du[1]-len(orig)
 struct.pack_into(">I",b,mo[0],mo[1]-delta);b[du[0]:du[0]+du[1]]=orig;grow_free(b,delta);return b
def restore_ftyp(b,source):
 sf=next(x for x in boxes(source) if x[2]==b"ftyp");df=next(x for x in boxes(b) if x[2]==b"ftyp");orig=bytes(source[sf[0]:sf[0]+sf[1]]);delta=df[1]-len(orig)
 if delta<0:raise ValueError("source ftyp larger")
 fr=next(x for x in boxes(b) if x[2]==b"free");old=bytes(b[fr[0]:fr[0]+fr[1]]);newfree=struct.pack(">I4s",fr[1]+delta,b"free")+old[8:]+b"\0"*delta
 return bytearray(orig+bytes(b[df[0]+df[1]:fr[0]])+newfree+bytes(b[fr[0]+fr[1]:]))
def source_android_value(source):
 sm=next(x for x in boxes(source) if x[2]==b"moov");me=child(source,sm,b"meta");il=child(source,me,b"ilst");item=next(x for x in kids(source,il) if x[2]==b"\0\0\0\1");da=child(source,item,b"data")
 return bytes(source[da[0]+16:da[0]+da[1]])
def android_meta(value):
 hdlr=struct.pack(">I4s",32,b"hdlr")+b"\0\0\0\0\0\0\0\0mdta"+b"\0"*12
 key=b"com.android.version";entry=struct.pack(">I4s",8+len(key),b"mdta")+key
 keys=struct.pack(">I4s",16+len(entry),b"keys")+b"\0\0\0\0"+struct.pack(">I",1)+entry
 data=struct.pack(">I4s",16+len(value),b"data")+b"\0\0\0\1\0\0\0\0"+value
 item=struct.pack(">I4s",8+len(data),b"\0\0\0\1")+data
 ilst=struct.pack(">I4s",8+len(item),b"ilst")+item
 body=hdlr+keys+ilst
 return struct.pack(">I4s",8+len(body),b"meta")+body
def set_android_meta(b,source):
 raw=android_meta(source_android_value(source));mo=next(x for x in boxes(b) if x[2]==b"moov");existing=next((x for x in kids(b,mo) if x[2]==b"meta"),None)
 if existing:pos,old=existing[0],existing[1]
 else:
  tracks=[x for x in kids(b,mo) if x[2]==b"trak"];eis=next(x for x in tracks if handler(b,x)==b"meta");pos=eis[0];old=0
 delta=len(raw)-old;fr=next(x for x in boxes(b) if x[2]==b"free")
 struct.pack_into(">I",b,mo[0],mo[1]+delta);b[pos:pos+old]=raw
 # Re-find the shifted free box, then counterbalance its size so mdat offsets stay fixed.
 fr=next(x for x in boxes(b) if x[2]==b"free");oldraw=bytes(b[fr[0]:fr[0]+fr[1]])
 consumed=min(delta,max(0,fr[1]-8)) if delta>0 else delta
 newsize=fr[1]-consumed;new=struct.pack(">I4s",newsize,b"free")+oldraw[8:8+newsize-8]
 b[fr[0]:fr[0]+fr[1]]=new
 # If the metadata did not fit entirely in free space, every following mdat
 # moved by the remainder. Correct all chunk offsets in the expanded moov.
 shift=delta-consumed
 if shift:
  mo=next(x for x in boxes(b) if x[2]==b"moov");end=mo[0]+mo[1];pos=mo[0]
  while True:
   candidates=[x for marker in (b"stco",b"co64") for x in [b.find(marker,pos,end)] if x>=4]
   if not candidates:break
   m=min(candidates);typ=bytes(b[m:m+4]);start=m-4;count=struct.unpack_from(">I",b,start+12)[0];width=4 if typ==b"stco" else 8;fmt=">I" if width==4 else ">Q"
   for i in range(count):
    off=start+16+i*width;struct.pack_into(fmt,b,off,struct.unpack_from(fmt,b,off)[0]+shift)
   pos=start+16+count*width
 return b
def video_sample_entry(b,tr):
 stsd=child(b,child(b,child(b,child(b,tr,b"mdia"),b"minf"),b"stbl"),b"stsd")
 p=stsd[0]+stsd[3]+8;z=struct.unpack_from(">I",b,p)[0]
 if bytes(b[p+4:p+8]) not in (b"hvc1",b"hev1") or z<86:raise ValueError("invalid HEVC visual sample entry")
 return stsd,(p,z,bytes(b[p+4:p+8]),8)
def restore_dovi_config(b,source,sv,dv):
 sstsd,sentry=video_sample_entry(source,sv);dstsd,dentry=video_sample_entry(b,dv)
 schild=next((x for x in boxes(source,sentry[0]+86,sentry[0]+sentry[1]) if x[2] in (b"dvvC",b"dvcC")),None)
 if not schild:raise ValueError("source Dolby Vision configuration box missing")
 raw=bytes(source[schild[0]:schild[0]+schild[1]])
 existing=next((x for x in boxes(b,dentry[0]+86,dentry[0]+dentry[1]) if x[2] in (b"dvvC",b"dvcC")),None)
 if existing:
  if existing[1]!=len(raw):raise ValueError("unexpected destination Dolby Vision box size")
  b[existing[0]:existing[0]+existing[1]]=raw;return b
 hvc=next(x for x in boxes(b,dentry[0]+86,dentry[0]+dentry[1]) if x[2]==b"hvcC")
 delta=len(raw);insert=hvc[0]+hvc[1]
 dm=next(x for x in boxes(b) if x[2]==b"moov");dmdia=child(b,dv,b"mdia");dminf=child(b,dmdia,b"minf");dstbl=child(b,dminf,b"stbl")
 for x in (dm,dv,dmdia,dminf,dstbl,dstsd,dentry):struct.pack_into(">I",b,x[0],x[1]+delta)
 b[insert:insert]=raw
 # The pipeline deliberately reserves a top-level free box between moov and
 # mdat. Consume it so inserting dvvC does not move media payload offsets.
 fr=next(x for x in boxes(b) if x[2]==b"free")
 if fr[1]<8+delta:raise ValueError("insufficient reserved free space for Dolby Vision box")
 old=bytes(b[fr[0]:fr[0]+fr[1]]);newsize=fr[1]-delta
 b[fr[0]:fr[0]+fr[1]]=struct.pack(">I4s",newsize,b"free")+old[8:8+newsize-8]
 return b
def main(src,base,dst):
 s=bytearray(open(src,"rb").read());b=bytearray(open(base,"rb").read());b=remove_lavf(b);b=replace_udta(b,s);b=restore_ftyp(b,s);b=set_android_meta(b,s)
 sm=next(x for x in boxes(s) if x[2]==b"moov");dm=next(x for x in boxes(b) if x[2]==b"moov");sts,sdu=read_mvhd(s,child(s,sm,b"mvhd"));stracks=[x for x in kids(s,sm) if x[2]==b"trak"]
 dtracks=[x for x in kids(b,dm) if x[2]==b"trak"];sv=next(x for x in stracks if handler(s,x)==b"vide");sa=next(x for x in stracks if handler(s,x)==b"soun");se=next(x for x in stracks if handler(s,x)==b"meta")
 dv=next(x for x in dtracks if handler(b,x)==b"vide");da=next(x for x in dtracks if handler(b,x)==b"soun");de=next(x for x in dtracks if handler(b,x)==b"meta")
 set_mvhd(b,child(b,dm,b"mvhd"),sts,sdu,max(4,len(dtracks)+1));settk(b,dv,tkdur(s,sv));set_tk_matrix(b,dv,tk_matrix(s,sv));set_first_elst(b,dv,tkdur(s,sv));settk(b,da,tkdur(s,sa));settk(b,de,tkdur(s,se))
 set_md_duration(b,dv,md_duration(s,sv));set_md_duration(b,da,md_duration(s,sa))
 for source_track,dest_track in ((sv,dv),(sa,da),(se,de)):set_md_language(b,dest_track,md_language(s,source_track))
 set_name(b,da,"SoundHandle")
 # Source audio has no edit list; remove the muxer-added zero edit.
 ed=next((x for x in kids(b,da) if x[2]==b"edts"),None)
 if ed:
  n=resize_remove(b,dm,da,ed);grow_free(b,n)
 # Append every source top-level UUID exactly once.
 for p,z,t,h in boxes(s):
  if t==b"uuid":
   raw=bytes(s[p:p+z])
   if raw not in b:b.extend(raw)
 b=restore_dovi_config(b,s,sv,dv)
 open(dst,"wb").write(b)
if __name__=="__main__":main(*sys.argv[1:4])
