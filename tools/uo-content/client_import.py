"""Validate a people VD and stage patched classic anim.mul/anim.idx copies."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

def vd_blocks(path):
    data=Path(path).read_bytes()
    if len(data)<2104 or struct.unpack_from('<hh',data)!=(6,2):
        raise ValueError('Expected a people/equipment VD (type 2, 35 actions).')
    blocks={}
    for i in range(175):
        off,size,_=struct.unpack_from('<iii',data,4+i*12)
        if off==-1 and size==-1: continue
        if off<2104 or size<520 or off+size>len(data): raise ValueError('Invalid VD block bounds.')
        block=data[off:off+size]
        n=struct.unpack_from('<I',block,512)[0]
        if not 0<n<=1000 or 516+4*n>size: raise ValueError('Invalid VD frame count.')
        offsets=struct.unpack_from(f'<{n}I',block,516)
        for fi,rel in enumerate(offsets):
            pos=512+rel; limit=512+offsets[fi+1] if fi+1<n else size
            if pos<516+4*n or pos+8>limit or limit>size: raise ValueError('Invalid frame bounds.')
            cx,cy,w,h=struct.unpack_from('<hhHH',block,pos); pos+=8
            if not 0<w<=1024 or not 0<h<=1024: raise ValueError('Invalid frame size.')
            while True:
                if pos+4>limit: raise ValueError('Missing RLE terminator.')
                word=struct.unpack_from('<I',block,pos)[0]; pos+=4
                if word==0x7fff7fff: break
                count=word&0xfff; dx=(word>>22)&1023; dy=(word>>12)&1023
                dx=dx-1024 if dx&512 else dx; dy=dy-1024 if dy&512 else dy
                x,y=cx+dx,cy+h+dy
                if not count or pos+count>limit or x<0 or x+count>w or not 0<=y<h:
                    raise ValueError('Invalid RLE run.')
                pos+=count
        blocks[divmod(i,5)]=block
    return blocks

def inspect_vd(path):
    return {k:struct.unpack_from('<I',v,512)[0] for k,v in vd_blocks(path).items()}

def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

ANIM_FILES=('anim.mul','anim.idx')

def require_client_files(client, names):
    """Fail before any output folder exists when the selected client lacks a file staging needs."""
    missing=[n for n in names if not (Path(client)/n).is_file()]
    if missing: raise ValueError(f'Client folder is missing {", ".join(missing)}: choose a classic MUL client folder.')

def stage(vd, client, body, out):
    vd,client,out=Path(vd).resolve(),Path(client).resolve(),Path(out).resolve()
    if not 400<=body<=2047: raise ValueError('Choose a people animation ID from 400 to 2047.')
    require_client_files(client,ANIM_FILES)
    blocks=vd_blocks(vd)
    if len(blocks)!=175: raise ValueError('Preview VD is incomplete. Build all 35 actions before importing.')
    for a in range(35):
        if len({struct.unpack_from('<I',blocks[(a,d)],512)[0] for d in range(5)})!=1:
            raise ValueError('Facing frame counts differ.')
    if out==client or client in out.parents or out.exists():
        raise ValueError('Output must be a new folder outside the source client.')
    index=(client/'anim.idx').read_bytes()
    if len(index)%12: raise ValueError('Invalid anim.idx length.')
    first=35000+(body-400)*175
    for i in range(first,first+175):
        if (i+1)*12<=len(index):
            off,length,_=struct.unpack_from('<iii',index,i*12)
            if off>=0 and length>0: raise ValueError(f'Animation ID {body} is occupied. Choose an unused ID.')
    # Refuse a known UOP override; a staged MUL import would otherwise be invisible.
    mob=client/'mobtypes.txt'
    if mob.exists():
        for line in mob.read_text(errors='replace').splitlines():
            words=line.split('#')[0].split()
            try:
                if len(words)>=3 and int(words[0],0)==body and int(words[2],16)&0x10000:
                    raise ValueError('This animation ID is routed to UOP by mobtypes.txt.')
            except (TypeError,IndexError): pass
            except ValueError as e:
                if 'routed' in str(e): raise
    out.mkdir(parents=True)
    try:
        shutil.copy2(client/'anim.mul',out/'anim.mul')
        dst=bytearray(index)
        while len(dst)<(first+175)*12: dst+=struct.pack('<iii',-1,-1,-1)
        with (out/'anim.mul').open('ab') as f:
            for (a,d),data in sorted(blocks.items()):
                offset=f.tell(); f.write(data)
                struct.pack_into('<iii',dst,(first+a*5+d)*12,offset,len(data),0)
        (out/'anim.idx').write_bytes(dst)
        with (out/'anim.mul').open('rb') as f:
            for (a,d),data in blocks.items():
                offset,length,_=struct.unpack_from('<iii',dst,(first+a*5+d)*12)
                f.seek(offset)
                if f.read(length)!=data: raise ValueError('Staged client verification failed.')
        report=dict(body=body,source_client=str(client),vd_sha256=file_sha(vd),blocks=175,
            source_hashes={n:file_sha(client/n) for n in ['anim.mul','anim.idx']},
            staged_hashes={n:file_sha(out/n) for n in ['anim.mul','anim.idx']},
            verified=True,deployed=False,remaining=['Static item art and graphic ID','Tiledata animation and wearable layer',
            'Server item definition','Check Body.def / Bodyconv.def / Equipconv.def routing','In-game equip test'])
        (out/'import-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    except BaseException:
        # The folder is new (checked above), so removing it lets the user retry with the same --out.
        shutil.rmtree(out,ignore_errors=True)
        raise
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('stage'); s.add_argument('--vd',required=True); s.add_argument('--client',required=True)
    s.add_argument('--body',type=int,required=True); s.add_argument('--out',required=True)
    a=p.parse_args(); print(json.dumps(stage(a.vd,a.client,a.body,a.out),indent=2))
