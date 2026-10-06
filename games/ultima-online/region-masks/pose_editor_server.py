"""Loopback-only live pose editor, local saves, and asynchronous Blender export."""
from pathlib import Path
import argparse, functools, json, math, os, shutil, subprocess, threading, time, uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'workspace/ultima-online/female-locomotion'
SOURCE=Path(__file__).parent
EDITABLE={f'{bone}_{side}' for bone in ('upperarm','lowerarm','hand','thigh','calf','foot') for side in ('l','r')}|{'LegPlate_L','LegPlate_R','Hip_L','Hip_R'}

def find_blender():
    exe=os.environ.get('SPRITEMOTION_BLENDER') or shutil.which('blender')
    if not exe:
        found=sorted(Path(os.environ.get('ProgramFiles','C:/Program Files'),'Blender Foundation').glob('Blender */blender.exe'))
        exe=str(found[-1]) if found else None
    if not exe:raise RuntimeError('Set SPRITEMOTION_BLENDER to blender.exe.')
    return exe

def validate(doc,scene):
    if not isinstance(doc,dict) or doc.get('version')!=1 or doc.get('assetId')!=scene['assetId']:
        raise ValueError('Edits do not match this model version.')
    if not isinstance(doc.get('edits'),dict) or len(doc['edits'])>21:raise ValueError('Invalid edits collection.')
    for key,pose in doc['edits'].items():
        parts=key.split(':')
        if len(parts)!=2 or parts[0] not in scene['clips'] or not parts[1].isdigit():raise ValueError('Invalid frame.')
        if str(int(parts[1]))!=parts[1] or int(parts[1])>=len(scene['clips'][parts[0]]['frames']):raise ValueError('Frame out of range.')
        if not isinstance(pose,dict) or set(pose)-EDITABLE:raise ValueError('Invalid editable bones.')
        for q in pose.values():
            if not isinstance(q,list) or len(q)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in q):raise ValueError('Invalid quaternion.')
            if abs(math.sqrt(sum(v*v for v in q))-1)>.001:raise ValueError('Quaternion is not normalized.')
    return {'version':1,'assetId':scene['assetId'],'edits':doc['edits']}

class EditorServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,port):
        self.scene=json.loads((OUT/'editor/scene.json').read_text())
        self.jobs={};self.lock=threading.Lock()
        super().__init__(('127.0.0.1',port),functools.partial(Handler,directory=str(OUT)))

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        super().end_headers()
    def send_json(self,value,status=200):
        data=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path=='/api/edits':
            p=OUT/'editor/edits.json'
            with self.server.lock:doc=json.loads(p.read_text()) if p.exists() else None
            return self.send_json(doc)
        if parsed.path=='/api/job':
            job=parse_qs(parsed.query).get('id',[''])[0]
            with self.server.lock:state=dict(self.server.jobs.get(job,{'status':'missing'}))
            return self.send_json(state,404 if state['status']=='missing' else 200)
        source={'/editor/':'pose_editor.html','/editor/index.html':'pose_editor.html','/editor/editor.js':'pose_editor.js','/editor/editor.css':'pose_editor.css'}.get(parsed.path)
        if source:
            raw=(SOURCE/source).read_bytes();self.send_response(200);self.send_header('Content-Type',{'html':'text/html','js':'text/javascript','css':'text/css'}[source.rsplit('.',1)[1]]);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
        return super().do_GET()
    def do_POST(self):
        if self.path not in ('/api/save','/api/bake'):return self.send_json({'error':'Unknown route'},404)
        origin=self.headers.get('Origin')
        if origin and origin!=f'http://127.0.0.1:{self.server.server_port}':return self.send_json({'error':'Origin rejected'},403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<500_000:raise ValueError('Invalid request size.')
            doc=validate(json.loads(self.rfile.read(size)),self.server.scene)
            if self.path=='/api/save':
                with self.server.lock:
                    tmp=OUT/'editor/edits.tmp';tmp.write_text(json.dumps(doc,indent=2));os.replace(tmp,OUT/'editor/edits.json')
                return self.send_json({'saved':True})
            with self.server.lock:
                if any(j['status']=='running' for j in self.server.jobs.values()):return self.send_json({'error':'An export is already running.'},409)
                job=uuid.uuid4().hex[:12];folder=OUT/'editor/exports'/job;folder.mkdir(parents=True)
                edits=folder/'edits.json';edits.write_text(json.dumps(doc))
                self.server.jobs[job]={'id':job,'status':'running'}
            threading.Thread(target=self.bake,args=(job,folder,edits),daemon=True).start()
            self.send_json({'id':job},202)
        except (ValueError,TypeError,KeyError) as e:self.send_json({'error':str(e)},400)
    def bake(self,job,folder,edits):
        output=folder/'UO_Female_Edited.blend'
        try:
            command=[find_blender(),'-b',str(OUT/self.server.scene.get('sourceBlend','UO_Female_Idle_Walk_Run.blend')),'--python-exit-code','1','--python',str(ROOT/'tools/blender/apply_pose_edits.py'),'--','--edits',str(edits),'--output',str(output)]
            with (folder/'export.log').open('w') as log:
                result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode or not output.exists():raise RuntimeError('Blender export failed; see the export log.')
            state={'id':job,'status':'done','url':f'/editor/exports/{job}/{output.name}'}
        except Exception as e:state={'id':job,'status':'failed','error':str(e)}
        with self.server.lock:self.server.jobs[job]=state

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8768);args=p.parse_args()
    server=EditorServer(args.port)
    print(f'Live editor: http://127.0.0.1:{args.port}/editor/',flush=True)
    server.serve_forever()
