"""Import UTF-8 CSV rows into a running server; consent is never assumed."""
import csv,hashlib,json,os,sys,urllib.request
from pathlib import Path
if len(sys.argv)!=3: raise SystemExit('Usage: python3 import_csv.py file.csv https://orders.example.org')
key=os.environ.get('INTAKE_API_KEY','')
if len(key)<24: raise SystemExit('Set INTAKE_API_KEY in the environment')
p=Path(sys.argv[1]);base=sys.argv[2].rstrip('/')
if not(base.startswith('https://') or base.startswith('http://127.0.0.1:')):raise SystemExit('Use HTTPS (or localhost for dry-run testing)')
with p.open(encoding='utf-8-sig',newline='') as f:
 for i,row in enumerate(csv.DictReader(f),2):
  source=row.get('source_id') or hashlib.sha256(p.read_bytes()).hexdigest()+':'+str(i)
  d={k:row.get(k,'') for k in ('name','phone','subject','city','teacher','package')}
  d.update(source_id=source,lang=row.get('lang','en'),consent=row.get('consent','').strip().lower() in ('yes','true','نعم','أوافق'))
  req=urllib.request.Request(base+'/api/intake',data=json.dumps(d).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(req,timeout=20) as r:o=json.load(r)
   print(i,o['id'],o['state'])
  except Exception as e:print(i,'FAILED',type(e).__name__)
