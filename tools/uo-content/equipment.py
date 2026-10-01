"""Classic equipment staging: inventory art, tiledata and server source handoff."""
from pathlib import Path
import json
import struct
import shutil
from PIL import Image
import numpy as np
from client_import import stage, file_sha

# Existing client records supply known flags, layer and physical defaults.
TEMPLATES={'helm':0x140A,'chest':0x1415,'arms':0x1410,'gloves':0x1414,'legs':0x1411,
    'boots':0x170B,'robe':0x1F03,'cloak':0x1515,'skirt':0x1516,'weapon':0xF5E,
    'shield':0x1B76,'bow':0x13B2,'quiver':0x2FB7}
LAYERS={'helm':'Helm','chest':'InnerTorso','arms':'Arms','gloves':'Gloves','legs':'InnerLegs',
    'boots':'Shoes','robe':'OuterTorso','cloak':'Cloak','skirt':'OuterLegs','weapon':'OneHanded',
    'shield':'TwoHanded','bow':'TwoHanded','quiver':'Cloak'}

def tile_layout(data):
    # Canonical complete old/new tiledata layouts. Unknown layouts must not be guessed.
    for flag_size,land,item in [(8,30,41),(4,26,37)]:
        start=512*(4+32*land)
        rest=len(data)-start
        if rest>0 and rest%(4+32*item)==0:
            return flag_size,item,start,(rest//(4+32*item))*32
    raise ValueError('Unsupported tiledata layout.')

def tile_offset(graphic,layout):
    flags,size,start,count=layout
    if not 0<=graphic<count: raise ValueError('Graphic ID is outside this tiledata file.')
    return start+(graphic//32)*(4+32*size)+4+(graphic%32)*size

def encode_art(image):
    rgba=np.asarray(image.convert('RGBA'))
    h,w=rgba.shape[:2]
    if not 0<w<=1024 or not 0<h<=1024: raise ValueError('Inventory art must be 1–1024 pixels per side.')
    rows=[];offsets=[];words=0
    for row in rgba:
        offsets.append(words);buf=bytearray();x=0;previous=0
        while x<w:
            if row[x,3]<128: x+=1;continue
            start=x
            while x<w and row[x,3]>=128: x+=1
            buf+=struct.pack('<HH',start-previous,x-start)
            for r,g,b,_ in row[start:x].astype(int):
                color=(((r*31+127)//255)<<10)|(((g*31+127)//255)<<5)|((b*31+127)//255)
                buf+=struct.pack('<H',color or 1)
            previous=x
        buf+=b'\0\0\0\0';rows.append(buf);words+=len(buf)//2
    if words>65535: raise ValueError('Inventory art exceeds classic RLE offset range.')
    return struct.pack('<IHH',0,w,h)+struct.pack(f'<{h}H',*offsets)+b''.join(rows)

def decode_art(data):
    w,h=struct.unpack_from('<HH',data,4);out=np.zeros((h,w,4),np.uint8)
    for y in range(h):
        p=8+2*h+2*struct.unpack_from('<H',data,8+2*y)[0];x=0
        while True:
            skip,n=struct.unpack_from('<HH',data,p);p+=4
            if not skip and not n:break
            x+=skip
            for i in range(n):
                c=struct.unpack_from('<H',data,p)[0];p+=2
                out[y,x+i]=[((c>>10)&31)*255//31,((c>>5)&31)*255//31,(c&31)*255//31,255]
            x+=n
    return out

def server_source(name,graphic,part,flavor='modernuo'):
    # Explicit strings are JSON-escaped into valid C# string literals, never executable prompt text.
    typename=f'SpriteMotionItem{graphic:04X}'
    safe_name=json.dumps(name,ensure_ascii=True)
    if flavor=='modernuo':
        return f'''using ModernUO.Serialization;
namespace Server.Items
{{
    [SerializationGenerator(0, false)]
    public partial class {typename} : Item
    {{
        [Constructible]
        public {typename}() : base(0x{graphic:04X})
        {{
            Name = {safe_name};
            Layer = Layer.{LAYERS[part]};
            Weight = 2.0;
        }}
    }}
}}
'''
    if flavor!='servuo': raise ValueError('Server format must be modernuo or servuo.')
    return f'''namespace Server.Items
{{
    public class {typename} : Item
    {{
        [Constructable]
        public {typename}() : base(0x{graphic:04X})
        {{
            Name = {safe_name}; Layer = Layer.{LAYERS[part]}; Weight = 2.0;
        }}
        public {typename}(Serial serial) : base(serial) {{ }}
        public override void Serialize(GenericWriter writer) {{ base.Serialize(writer); writer.Write(0); }}
        public override void Deserialize(GenericReader reader) {{ base.Deserialize(reader); reader.ReadInt(); }}
    }}
}}
'''

def stage_equipment(job,client,body,graphic,flavor='modernuo'):
    job,client=Path(job).resolve(),Path(client).resolve()
    spec=json.loads((job/'job.json').read_text(encoding='utf-8'))
    report=json.loads((job/'validation.json').read_text(encoding='utf-8'))
    if report['clipped_frames']: raise ValueError('Fix clipped frames before staging equipment.')
    data=bytearray((client/'tiledata.mul').read_bytes());layout=tile_layout(data)
    target=tile_offset(graphic,layout);source=tile_offset(TEMPLATES[spec['part']],layout)
    flags,size,_,_=layout
    if any(data[target:target+size]): raise ValueError('Static graphic has occupied tiledata; choose an unused graphic ID.')
    artidx=bytearray((client/'artidx.mul').read_bytes());index=(graphic+0x4000)*12
    if index+12<=len(artidx):
        off,length,_=struct.unpack_from('<iii',artidx,index)
        if off>=0 and length>0: raise ValueError('Static graphic already contains art.')
    image=Image.open(job/'inventory.png').convert('RGBA');encoded=encode_art(image)
    # Verify alpha without comparing quantized RGB to the unquantized source.
    if not np.array_equal(decode_art(encoded)[...,3]>0,np.asarray(image)[...,3]>=128):
        raise ValueError('Inventory art round-trip failed.')
    out=job/'staged-client'
    result=stage(job/'item.vd',client,body,out)
    data[target:target+size]=data[source:source+size]
    struct.pack_into('<H',data,target+flags+6,body)
    data[target+size-20:target+size]=spec['name'].encode('cp1252',errors='replace')[:19].ljust(20,b'\0')
    (out/'tiledata.mul').write_bytes(data)
    shutil.copy2(client/'art.mul',out/'art.mul')
    while len(artidx)<index+12:artidx+=struct.pack('<iii',-1,-1,-1)
    with (out/'art.mul').open('ab') as f:
        offset=f.tell();f.write(encoded)
    struct.pack_into('<iii',artidx,index,offset,len(encoded),0)
    (out/'artidx.mul').write_bytes(artidx)
    (out/f'SpriteMotionItem{graphic:04X}.cs').write_text(server_source(spec['name'],graphic,spec['part'],flavor))
    result.update(graphic=graphic,layer=LAYERS[spec['part']],template_graphic=TEMPLATES[spec['part']],
        server_format=flavor,server_class=f'SpriteMotionItem{graphic:04X}',server_compiled=False,
        inventory_alpha_roundtrip=True,
        remaining=['Compile/install generated cosmetic item class in your server',
          'Sync staged client files and tiledata to the selected client/server',
          'Check Body.def / Bodyconv.def / Equipconv.def routing',
          'Custom paperdoll gump and female body conversion are not generated','In-game equip test'])
    if (client/'artLegacyMUL.uop').exists():
        result['remaining'].insert(0,'Client has artLegacyMUL.uop: import inventory.png through your UOP art tool or configure classic MUL art loading; the staged art.mul may be shadowed.')
    for name in ['art.mul','artidx.mul','tiledata.mul']:
        result['source_hashes'][name]=file_sha(client/name);result['staged_hashes'][name]=file_sha(out/name)
    (out/'import-report.json').write_text(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job',required=True);p.add_argument('--client',required=True)
    p.add_argument('--body',type=int,required=True);p.add_argument('--graphic',type=lambda s:int(s,0),required=True)
    p.add_argument('--server',choices=['modernuo','servuo'],default='modernuo')
    a=p.parse_args();print(json.dumps(stage_equipment(a.job,a.client,a.body,a.graphic,a.server),indent=2))
