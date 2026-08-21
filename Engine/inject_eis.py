#!/usr/bin/env python3
import json,struct,subprocess,sys

def boxes(buf,start=0,end=None):
    end=len(buf) if end is None else end;p=start
    while p+8<=end:
        size=struct.unpack_from(">I",buf,p)[0];typ=bytes(buf[p+4:p+8]);head=8
        if size==1:size=struct.unpack_from(">Q",buf,p+8)[0];head=16
        elif size==0:size=end-p
        if size<head or p+size>end:raise ValueError(f"bad box {typ!r} at {p}")
        yield p,size,typ,head;p+=size
def children(buf,box):p,size,typ,head=box;return list(boxes(buf,p+head,p+size))
def child(buf,box,typ):return next(x for x in children(buf,box) if x[2]==typ)
def handler(buf,trak):
    h=child(buf,child(buf,trak,b"mdia"),b"hdlr");return bytes(buf[h[0]+16:h[0]+20])
def rewrite(raw,delta=0,replacements=None):
    data=bytearray(raw);pos=0
    while True:
        a=data.find(b"stco",pos);b=data.find(b"co64",pos);choices=[x for x in (a,b) if x>=4]
        if not choices:break
        t=min(choices);start=t-4;typ=bytes(data[t:t+4]);count=struct.unpack_from(">I",data,start+12)[0];width=4 if typ==b"stco" else 8
        fmt=">I" if width==4 else ">Q";values=replacements if replacements is not None else [struct.unpack_from(fmt,data,start+16+i*width)[0]+delta for i in range(count)]
        if len(values)!=count:raise ValueError("chunk count mismatch")
        for i,v in enumerate(values):struct.pack_into(fmt,data,start+16+i*width,v)
        pos=start+16+count*width
    return bytes(data)
def chunk_starts(trak):
    m=trak.find(b"stsc");start=m-4;count=struct.unpack_from(">I",trak,start+12)[0];entries=[struct.unpack_from(">III",trak,start+16+i*12) for i in range(count)]
    m=trak.find(b"stco");m=m if m>=4 else trak.find(b"co64");chunks=struct.unpack_from(">I",trak,m-4+12)[0]
    starts=[];sample=0;ei=0
    for c in range(1,chunks+1):
        while ei+1<len(entries) and entries[ei+1][0]<=c:ei+=1
        starts.append(sample);sample+=entries[ei][1]
    return starts,sample
def main(src,base,dst):
    source=bytearray(open(src,"rb").read());target=bytearray(open(base,"rb").read());sm=next(x for x in boxes(source) if x[2]==b"moov");dm=next(x for x in boxes(target) if x[2]==b"moov")
    et=next(x for x in children(source,sm) if x[2]==b"trak" and handler(source,x)==b"meta");eis=bytes(source[et[0]:et[0]+et[1]])
    ffprobe="/opt/homebrew/bin/ffprobe" if __import__('os').path.exists('/opt/homebrew/bin/ffprobe') else "ffprobe"
    info=json.loads(subprocess.check_output([ffprobe,"-v","error","-select_streams","2","-show_packets","-show_entries","packet=pos,size","-of","json",src]))
    payloads=[bytes(source[int(x["pos"]):int(x["pos"])+int(x["size"])]) for x in info["packets"]]
    shift=len(eis);dp,ds,_,dh=dm;fixed=rewrite(bytes(target[dp:dp+ds]),delta=shift);start_payload=len(target)+shift+8
    starts,total=chunk_starts(eis)
    if total!=len(payloads):raise ValueError("EIS sample count mismatch")
    offsets=[];cursor=start_payload;ss=set(starts)
    for i,p in enumerate(payloads):
        if i in ss:offsets.append(cursor)
        cursor+=len(p)
    eis=rewrite(eis,replacements=offsets);body=fixed[dh:]+eis;moov=struct.pack(">I4s",dh+len(body),b"moov")+body
    result=bytes(target[:dp])+moov+bytes(target[dp+ds:]);payload=b"".join(payloads);result+=struct.pack(">I4s",len(payload)+8,b"mdat")+payload
    open(dst,"wb").write(result)
if __name__=="__main__":main(*sys.argv[1:4])
