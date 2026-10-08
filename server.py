import hashlib,hmac,json,os,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from core import Engine,Invalid,validate_config
from provider import dispatch,Meta

ROOT=Path(__file__).resolve().parent

def load_env(path):
    if not path.exists(): return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1); os.environ.setdefault(k.strip(),v.strip())

load_env(ROOT/'.env')
DATA=Path(os.environ.get('DATA_DIR',str(ROOT/'data')))
DATA.mkdir(parents=True,exist_ok=True)
CONFIG_PATH=Path(os.environ.get('CONFIG_PATH',str(DATA/'config.json')))
if not CONFIG_PATH.exists(): CONFIG_PATH.write_bytes((ROOT/'config.json').read_bytes())
cfg=json.loads(CONFIG_PATH.read_text(encoding='utf-8-sig'))
seed=json.loads((ROOT/'config.json').read_text(encoding='utf-8-sig'))
# Upgrade only newly introduced settings, preserving prices, fees, secrets and bank data.
for key in ('request_aliases','unpriced_requests','internal_recipients','source_sheet','require_packing_confirmation'):
    if key not in cfg: cfg[key]=seed.get(key,{})
cfg.setdefault('templates',{}).setdefault('ar',{}).setdefault('workorder','')
engine=Engine(DATA/'orders.sqlite3',validate_config(cfg))
LIVE=os.environ.get('SEND_LIVE','false')=='true'

def auth(headers,key):
    secret=os.environ.get(key,'')
    return len(secret)>=24 and hmac.compare_digest(headers.get('Authorization',''),'Bearer '+secret)

def signature(raw,headers):
    secret=os.environ.get('META_APP_SECRET','')
    expected='sha256='+hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
    return bool(secret) and hmac.compare_digest(headers.get('X-Hub-Signature-256',''),expected)

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)
    def log_message(self,*args): pass # No customer data or tokens in access logs.
    def reply(self,data,status=200,mime='application/json'):
        b=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type',mime+'; charset=utf-8')
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u=urlparse(self.path); p=u.path
        if p=='/': return self.reply((ROOT/'dashboard.html').read_bytes(),mime='text/html')
        if p=='/health': return self.reply({'ok':True,'mode':'live' if LIVE else 'dry_run'})
        if p=='/webhooks/meta':
            q=parse_qs(u.query); token=os.environ.get('META_VERIFY_TOKEN','')
            if token and q.get('hub.mode')==['subscribe'] and hmac.compare_digest(q.get('hub.verify_token',[''])[0],token):
                return self.reply(q.get('hub.challenge',[''])[0].encode(),mime='text/plain')
            return self.reply({'error':'Verification failed'},403)
        if not auth(self.headers,'ADMIN_API_KEY'): return self.reply({'error':'Unauthorized'},401)
        try:
            if p=='/api/orders': return self.reply(engine.list())
            if p=='/api/workorders':
                with engine.conn() as c: jobs=[dict(r) for r in c.execute('SELECT * FROM workorders ORDER BY created DESC')]
                return self.reply(jobs)
            if p=='/api/config': return self.reply(engine.config)
            if p.startswith('/api/orders/'): return self.reply(engine.details(p.rsplit('/',1)[1]))
            if p.startswith('/api/receipts/'):
                rid=p.rsplit('/',1)[1]
                with engine.conn() as c: r=c.execute('SELECT * FROM receipts WHERE id=?',(rid,)).fetchone()
                if not r or not r['path']: raise Invalid('Receipt not archived yet')
                f=Path(r['path']).resolve()
                if not f.is_relative_to(DATA.resolve()): raise Invalid('Invalid receipt path')
                return self.reply(f.read_bytes(),mime=r['mime'])
            self.reply({'error':'Not found'},404)
        except Invalid as e: self.reply({'error':str(e)},400)
    def do_POST(self):
        p=urlparse(self.path).path
        try:
            if p!='/webhooks/meta' and not auth(self.headers,'ADMIN_API_KEY') and not (p=='/api/intake' and auth(self.headers,'INTAKE_API_KEY')):
                return self.reply({'error':'Unauthorized'},401)
            if p=='/webhooks/meta' and not self.headers.get('X-Hub-Signature-256','').startswith('sha256='):
                return self.reply({'error':'Invalid signature'},403)
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=1024*1024: return self.reply({'error':'Body size must be 1 byte to 1 MiB'},413)
            raw=self.rfile.read(size)
            if p=='/webhooks/meta':
                if not signature(raw,self.headers): return self.reply({'error':'Invalid signature'},403)
                d=json.loads(raw); results=[]
                for entry in d.get('entry',[]):
                    for change in entry.get('changes',[]):
                        v=change.get('value',{})
                        if v.get('metadata',{}).get('phone_number_id')!=os.environ.get('META_PHONE_NUMBER_ID'): continue
                        for m in v.get('messages',[]): results.append(engine.incoming(m))
                        for s in v.get('statuses',[]):
                            with engine.conn() as c:
                                q=c.execute('SELECT order_id FROM outbox WHERE provider_id=?',(s.get('id'),)).fetchone()
                                if q: engine.audit(c,q['order_id'],'message_status',{'provider_id':s.get('id'),'status':s.get('status')})
                return self.reply({'received':True,'messages':len(results)})
            admin=auth(self.headers,'ADMIN_API_KEY'); intake=auth(self.headers,'INTAKE_API_KEY')
            if not admin and not (p=='/api/intake' and intake): return self.reply({'error':'Unauthorized'},401)
            d=json.loads(raw)
            if p=='/api/intake': return self.reply(engine.create(d),201)
            if p=='/api/config':
                validate_config(d)
                with engine.conn() as c:
                    temp=CONFIG_PATH.with_suffix('.tmp'); temp.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8'); temp.replace(CONFIG_PATH)
                    engine.config=d
                return self.reply({'saved':True})
            if p=='/api/actions': return self.reply(engine.action(d.get('order_id'),d.get('action'),d))
            if p=='/api/dispatch': return self.reply(dispatch(engine,LIVE))
            if p=='/api/reminders': return self.reply({'queued':engine.reminder()})
            # Simulate customer messages locally; this endpoint is unavailable in live mode.
            if p=='/api/simulate' and not LIVE: return self.reply(engine.incoming(d))
            self.reply({'error':'Not found'},404)
        except (Invalid,ValueError,TypeError,KeyError) as e: self.reply({'error':str(e)},400)
        except Exception: self.reply({'error':'Internal error; check server configuration'},500)

def worker():
    while True:
        try:
            dispatch(engine,LIVE)
            if LIVE:
                with engine.conn() as c:
                    receipts=[dict(r) for r in c.execute("SELECT * FROM receipts WHERE path IS NULL AND status IN ('received','approved') LIMIT 5")]
                for r in receipts:
                    try:
                        path,digest=Meta(engine.config).archive(r,DATA/'receipts')
                        with engine.conn() as c:
                            c.execute('UPDATE receipts SET path=?,sha256=? WHERE id=?',(path,digest,r['id']))
                    except Exception:
                        # Receipt remains pending archive; never auto-approve payment.
                        pass
        except Exception: pass
        time.sleep(5)

if __name__=='__main__':
    for key in ('ADMIN_API_KEY','INTAKE_API_KEY'):
        if len(os.environ.get(key,''))<24: raise SystemExit(f'{key} must contain at least 24 characters')
    if hmac.compare_digest(os.environ['ADMIN_API_KEY'],os.environ['INTAKE_API_KEY']):
        raise SystemExit('Use different ADMIN_API_KEY and INTAKE_API_KEY values')
    if LIVE:
        for key in ('META_GRAPH_VERSION','META_ACCESS_TOKEN','META_PHONE_NUMBER_ID','META_APP_SECRET','META_VERIFY_TOKEN'):
            if not os.environ.get(key): raise SystemExit(f'Missing {key}')
    threading.Thread(target=worker,daemon=True).start()
    port=int(os.environ.get('PORT','8080')); host=os.environ.get('BIND_HOST','127.0.0.1')
    print(f'IGCSE orders: http://{host}:{port} (mode: {"live" if LIVE else "dry_run"})',flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()
