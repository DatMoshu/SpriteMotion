"""One local build at a time, using frozen saved fits and durable last-successful job references."""
import json
from pathlib import Path
import sys
from threading import Lock, Thread

from adjustments import atomic_write

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/uo-content'))
import pipeline
from rebuild import rebuild_job


class Builds:
    def __init__(self, data, store):
        self.data, self.store = data, store
        self.path = data/'lab-builds.json'
        self.lock = Lock()
        self.status = {'state':'idle'}

    def state(self):
        with self.lock: return dict(self.status)

    def start(self, request):
        if not isinstance(request,dict) or set(request) != {'item','mode','coverage','action'}:
            raise ValueError('Expected item, mode, coverage and action.')
        if request['mode'] not in ('build','rebuild') or request['coverage'] not in ('preview','full','action'):
            raise ValueError('Invalid build mode.')
        if type(request['action']) is not int or not 0<=request['action']<=34: raise ValueError('Invalid action.')
        catalog = json.loads((self.data/'lab-items.json').read_text())
        item = next((i for i in catalog['items'] if i['id']==request['item']),None)
        if item is None: raise ValueError('Builds require a mapped source item; directory imports are preview-only.')
        document = self.store.state()['adjustments']
        last = json.loads(self.path.read_text()) if self.path.exists() else {}
        parent = last.get(item['id'])
        if request['mode']=='rebuild' and not parent: raise ValueError('Build this item once before rebuilding changed blocks.')
        with self.lock:
            if self.status['state']=='building': raise ValueError('A lab build is already running.')
            self.status = {'state':'building','item':item['id']}
        Thread(target=self.run,args=(request,catalog,item,document,last,parent),daemon=True).start()
        return self.state()

    def run(self, request, catalog, item, document, last, parent):
        try:
            if request['mode']=='rebuild':
                if not isinstance(parent,str) or not parent.isalnum(): raise ValueError('Invalid saved job ID.')
                job = rebuild_job(pipeline.HOME/'jobs'/parent,document)
            else:
                mapping = json.loads(Path(catalog['mapping']).read_text())
                part = next(p for p in mapping['parts'] if p['code']==item['part'])
                mode = 'full' if request['coverage']=='full' else 'preview'
                spec = {'name':item['id'], 'part':part['studio_part'], 'mode':mode, 'fit':'preserve',
                        'source_files':item['files'], 'palette':item.get('palette'), 'pack_mapping':catalog['mapping'],
                        'pack_part':item['part'], 'fit_item':{k:item[k] for k in ('id','slot','part')}, 'fit_adjustments':document}
                if request['coverage']=='action': spec['actions']=[request['action']]
                job = pipeline.create_job(spec,item['files'][0]); pipeline.run_job(job)
            last[item['id']]=job.name
            atomic_write(self.path,json.dumps(last,indent=2).encode())
            status={'state':'complete','item':item['id'],'job':job.name,'review':f'/builds/{job.name}/review/index.html',
                    'unchanged':job.name==parent}
        except Exception as error:
            status={'state':'failed','item':item['id'],'error':str(error)}
        with self.lock: self.status=status
