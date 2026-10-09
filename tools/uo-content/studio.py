"""Local SpriteMotion content studio. Bind to loopback; never exposes a network service."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from urllib.parse import urlparse
import pipeline
import starters

pool=ThreadPoolExecutor(max_workers=1)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(pipeline.HOME),**kwargs)

    def reply(self,value,status=200):
        raw=json.dumps(value).encode()
        self.send_response(status); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store')
        self.end_headers(); self.wfile.write(raw)

    def local(self):
        expected={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in expected: return False
        origin=self.headers.get('Origin')
        return not origin or origin in {'http://'+h for h in expected}

    def do_GET(self):
        if not self.local(): return self.reply({'error':'Local requests only.'},403)
        path=urlparse(self.path).path
        if path=='/api/starters': return self.reply(starters.catalog())
        if path.startswith('/starter-assets/'):
            try:
                item=starters.entry(path.removeprefix('/starter-assets/'))
                if 'asset' not in item: raise ValueError('This layer has no wearable model.')
                raw=(starters.ASSETS/item['asset']).read_bytes()
            except ValueError as error: return self.reply({'error':str(error)},404)
            self.send_response(200); self.send_header('Content-Type','model/gltf-binary')
            self.send_header('Content-Disposition',f'attachment; filename="{item["asset"]}"')
            self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        if path=='/api/config':
            return self.reply(dict(ready=(pipeline.BACKEND/'provenance.json').exists(),parts=pipeline.PARTS))
        if path=='/api/jobs':
            jobs=[]
            for p in sorted((pipeline.HOME/'jobs').glob('*/job.json'),key=lambda p:p.stat().st_mtime,reverse=True):
                try:
                    spec=json.loads(p.read_text(encoding='utf-8')); status=json.loads((p.parent/'status.json').read_text(encoding='utf-8'))
                    status.update(id=p.parent.name,part=spec['part'],mode=spec['mode'],spec=spec,
                        rendered=len(list((p.parent/'render/clothing/frames').glob('*/*/*.png'))))
                    if (p.parent/'validation.json').exists(): status['validation']=json.loads((p.parent/'validation.json').read_text(encoding='utf-8'))
                    jobs.append(status)
                except (OSError,json.JSONDecodeError): pass
            return self.reply(jobs)
        if path=='/':
            data=(pipeline.HERE/'index.html').read_bytes()
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
        if not path.startswith('/jobs/'): return self.reply({'error':'Not found'},404)
        # SimpleHTTPRequestHandler normalizes traversal; only serve resolved files inside jobs.
        target=Path(self.translate_path(self.path)).resolve()
        if pipeline.HOME.resolve() not in target.parents or not target.is_file():
            return self.reply({'error':'Not found'},404)
        return super().do_GET()

    def do_POST(self):
        if not self.local(): return self.reply({'error':'Local requests only.'},403)
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self.reply({'error':'Expected JSON.'},415)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<140*1024*1024: raise ValueError('Request exceeds 100 MB upload limit.')
            data=json.loads(self.rfile.read(size))
            path=urlparse(self.path).path
            if path=='/api/build':
                starter=data.pop('starter',None)
                upload=data.pop('upload',None)
                if starter:
                    if upload or data.get('reuse'):
                        raise ValueError('Choose one source asset.')
                    settings,asset=starters.settings(starter,data)
                    job=pipeline.create_job(settings,asset)
                elif upload:
                    name=Path(upload['name']).name
                    ext=Path(name).suffix.lower()
                    if ext not in pipeline.MODELS|pipeline.IMAGES: raise ValueError('Unsupported asset format.')
                    with tempfile.TemporaryDirectory() as temp:
                        asset=Path(temp)/name
                        asset.write_bytes(base64.b64decode(upload['data'],validate=True))
                        job=pipeline.create_job(data,asset)
                elif data.get('reuse'):
                    old=self.job(data.pop('reuse'))
                    oldspec=json.loads((old/'job.json').read_text(encoding='utf-8'))
                    job=pipeline.create_job(data,oldspec.get('asset'))
                else: job=pipeline.create_job(data)
                pool.submit(pipeline.run_job,job)
                return self.reply({'id':job.name},202)
            if path=='/api/cancel':
                job=self.job(data['id'])
                status=json.loads((job/'status.json').read_text(encoding='utf-8'))
                if status['state']!='building': raise ValueError('Only an active render can be stopped.')
                render=job/'render/clothing'; render.mkdir(parents=True,exist_ok=True)
                (render/'STOP').touch()
                return self.reply({'message':'Stop requested; the current frame will finish.'})
            if path=='/api/stage':
                from client_import import stage
                job=self.job(data['id'])
                if data.get('graphic'):
                    from equipment import stage_equipment
                    report=stage_equipment(job,data['client'],int(data['body']),int(str(data['graphic']),0),data.get('server','modernuo'))
                else:
                    report=stage(job/'item.vd',data['client'],int(data['body']),job/'staged-client')
                return self.reply(report)
            return self.reply({'error':'Not found'},404)
        except Exception as e:
            return self.reply({'error':str(e)},400)

    @staticmethod
    def job(identifier):
        import re
        if not re.fullmatch('[a-f0-9]{12}',str(identifier)): raise ValueError('Invalid job ID.')
        path=pipeline.HOME/'jobs'/identifier
        if not (path/'job.json').exists(): raise ValueError('Job not found.')
        return path

def recover_interrupted_jobs(jobs):
    """Mark jobs left queued/building as failed. Returns [(status file, error)] for unreadable status files, which are skipped."""
    skipped=[]
    for file in Path(jobs).glob('*/status.json'):
        try:
            status=json.loads(file.read_text(encoding='utf-8'))
            interrupted=status['state'] in ('queued','building')
        except (OSError,ValueError,KeyError,TypeError) as e:
            skipped.append((file,e)); continue
        if interrupted:
            status.update(state='failed',error='Studio stopped during build. Load the settings and build again.')
            pipeline.write_json(file,status)
    return skipped

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--port',type=int,default=8772)
    args=p.parse_args(); (pipeline.HOME/'jobs').mkdir(parents=True,exist_ok=True)
    # Jobs interrupted by a server shutdown are never presented as still rendering.
    for file,error in recover_interrupted_jobs(pipeline.HOME/'jobs'):
        print(f'Skipped job {file.parent.name}: unreadable status.json ({error})',flush=True)
    print(f'SpriteMotion content studio: http://127.0.0.1:{args.port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
