import base64, hashlib, json, os, time, urllib.request, urllib.error
from pathlib import Path
from urllib.parse import urlparse
from core import Invalid

class Meta:
    def __init__(self,config): self.config=config
    def graph(self,path,data=None):
        version=os.environ.get('META_GRAPH_VERSION','')
        if not version: raise Invalid('Set META_GRAPH_VERSION to a supported version from Meta')
        token=os.environ.get('META_ACCESS_TOKEN','')
        if not token: raise Invalid('Set META_ACCESS_TOKEN')
        url='https://graph.facebook.com/'+version+'/'+path
        req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},
            data=json.dumps(data).encode() if data is not None else None)
        with urllib.request.urlopen(req,timeout=25) as r: return json.load(r)
    def payload(self,q):
        o=q['order']; cfg=self.config
        base={'messaging_product':'whatsapp','to':o['phone']}
        # Business-initiated intro always uses an approved image-header template.
        free=o['last_inbound']>time.time()-86400 and q['kind']!='intro'
        if free:
            base.update(type='text',text={'body':q['body'],'preview_url':False}); return base
        key='workorder' if q.get('internal') else ('intro' if q['kind']=='intro' else 'update')
        template=cfg.get('templates',{}).get(o['lang'],{}).get(key)
        if not template: raise Invalid(f'Approved {o["lang"]} {key} template must be configured')
        body=' '.join(q['body'].split())
        if len(body)>900: raise Invalid('Template parameter is too long; shorten the catalog or use an approved structured template')
        components=[]
        if key=='intro':
            if not q.get('image') or not q['image'].startswith('https://'): raise Invalid('Teacher catalog image HTTPS URL is required')
            components.append({'type':'header','parameters':[{'type':'image','image':{'link':q['image']}}]})
        components.append({'type':'body','parameters':[{'type':'text','text':body}]})
        base.update(type='template',template={'name':template,'language':{'code':cfg.get('template_language_codes',{}).get(o['lang'],o['lang'])},'components':components})
        return base
    def send(self,q):
        payload=self.payload(q)
        pid=os.environ.get('META_PHONE_NUMBER_ID','')
        if not pid: raise Invalid('Set META_PHONE_NUMBER_ID')
        result=self.graph(pid+'/messages',payload)
        return result['messages'][0]['id']
    def archive(self,receipt,root):
        meta=self.graph(receipt['media_id'])
        u=urlparse(meta.get('url',''))
        if u.scheme!='https' or not (u.hostname and (u.hostname=='lookaside.fbsbx.com' or u.hostname.endswith('.fbcdn.net') or u.hostname.endswith('.facebook.com'))):
            raise Invalid('Unexpected Meta media host')
        if meta.get('mime_type') not in ('image/jpeg','image/png','application/pdf'): raise Invalid('Unsupported receipt format')
        # Block redirects to arbitrary destinations before credentials can be forwarded.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs): raise Invalid('Receipt redirect rejected')
        req=urllib.request.Request(meta['url'],headers={'Authorization':'Bearer '+os.environ['META_ACCESS_TOKEN']})
        with urllib.request.build_opener(NoRedirect).open(req,timeout=25) as r:
            data=r.read(10*1024*1024+1)
        if len(data)>10*1024*1024: raise Invalid('Receipt exceeds 10 MiB')
        digest=hashlib.sha256(data).hexdigest()
        if meta.get('sha256') and meta['sha256'] not in (digest,base64.b64encode(hashlib.sha256(data).digest()).decode()): raise Invalid('Receipt hash mismatch')
        ext={'image/jpeg':'.jpg','image/png':'.png','application/pdf':'.pdf'}[meta['mime_type']]
        p=Path(root)/receipt['order_id']/(receipt['id']+ext); p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(data); os.chmod(p,0o600)
        return str(p),digest

def dispatch(engine,live=False,limit=20):
    if not live:
        # Dry mode previews without consuming the queue; switching to live needs deliberate review.
        with engine.conn() as c:
            return {'mode':'dry_run','pending':c.execute("SELECT count(*) FROM outbox WHERE state='pending'").fetchone()[0]}
    provider=Meta(engine.config); results=[]
    for _ in range(limit):
        q=engine.claim()
        if not q: break
        try:
            mid=provider.send(q); engine.finish(q['id'],'sent',provider_id=mid)
        except Invalid as e: engine.finish(q['id'],'blocked',str(e))
        except urllib.error.HTTPError as e:
            # Preserve errors for manual reconciliation. Never blindly resend financial messages.
            engine.finish(q['id'],'failed','Meta HTTP '+str(e.code))
        except Exception as e: engine.finish(q['id'],'uncertain',type(e).__name__+': reconcile delivery before retry')
        results.append(q['id'])
    return {'mode':'live','processed':len(results)}
