import hashlib,hmac,json,os,socket,subprocess,sys,tempfile,time,unittest,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class HTTP(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.key='admin-test-key-'+('a'*32);cls.intake='intake-test-key-'+('b'*32)
  with socket.socket() as s:s.bind(('127.0.0.1',0));cls.port=s.getsockname()[1]
  env=dict(os.environ,ADMIN_API_KEY=cls.key,INTAKE_API_KEY=cls.intake,DATA_DIR=cls.tmp.name,PORT=str(cls.port),BIND_HOST='127.0.0.1',SEND_LIVE='false',META_APP_SECRET='test-secret',META_PHONE_NUMBER_ID='test-phone-id',META_VERIFY_TOKEN='verify-test')
  cls.proc=subprocess.Popen([sys.executable,str(ROOT/'server.py')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  for _ in range(50):
   try:
    urllib.request.urlopen(f'http://127.0.0.1:{cls.port}/health',timeout=1);break
   except Exception:time.sleep(.05)
  else:cls.proc.terminate();raise RuntimeError('Server failed to start')
 @classmethod
 def tearDownClass(cls):cls.proc.terminate();cls.proc.wait(timeout=5);cls.tmp.cleanup()
 def req(self,path,data=None,key=None,headers=None):
  h={'Content-Type':'application/json'}
  if key:h['Authorization']='Bearer '+key
  h.update(headers or {})
  raw=json.dumps(data).encode() if data is not None else None
  req=urllib.request.Request(f'http://127.0.0.1:{self.port}'+path,data=raw,headers=h)
  try:
   with urllib.request.urlopen(req,timeout=3) as r:return r.status,r.read()
  except urllib.error.HTTPError as e:return e.code,e.read()
 def test_health(self):self.assertEqual(json.loads(self.req('/health')[1])['mode'],'dry_run')
 def test_dashboard_available(self):self.assertIn('طلبات'.encode(),self.req('/')[1])
 def test_orders_require_admin(self):self.assertEqual(self.req('/api/orders')[0],401)
 def test_intake_cannot_read_orders(self):self.assertEqual(self.req('/api/orders',key=self.intake)[0],401)
 def test_unsigned_meta_rejected(self):self.assertEqual(self.req('/webhooks/meta',{'entry':[]})[0],403)
 def test_signed_meta_accepted(self):
  d={'entry':[]};raw=json.dumps(d).encode();sig='sha256='+hmac.new(b'test-secret',raw,hashlib.sha256).hexdigest()
  self.assertEqual(self.req('/webhooks/meta',d,headers={'X-Hub-Signature-256':sig})[0],200)
 def test_verification_challenge(self):self.assertEqual(self.req('/webhooks/meta?hub.mode=subscribe&hub.verify_token=verify-test&hub.challenge=123')[1],b'123')
 def test_verify_wrong_token(self):self.assertEqual(self.req('/webhooks/meta?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=123')[0],403)
 def test_intake_full_order(self):
  cfg=json.loads(self.req('/api/config',key=self.key)[1]);cfg['delivery_fils']={'Test City':1000};cfg['bank']={'name':'TEST','holder':'TEST','iban':'TEST ONLY'}
  self.assertEqual(self.req('/api/config',cfg,key=self.key)[0],200)
  d={'source_id':'http-row','name':'Synthetic test','phone':'0557654321','subject':'Chemistry','city':'Test City','package':'OL Cambridge J27','lang':'en','consent':True}
  status,body=self.req('/api/intake',d,key=self.intake);self.assertEqual(status,201);oid=json.loads(body)['id']
  messages=[('text',{'body':'CONFIRM CHEM-04 1'}),('location',{'latitude':25,'longitude':55}),('text',{'body':'Test building flat 1'}),('image',{'id':'test-image','mime_type':'image/jpeg'})]
  for i,(typ,value) in enumerate(messages):
   status,body=self.req('/api/simulate',{'id':'http-'+str(i),'from':'971557654321','type':typ,typ:value},key=self.key);self.assertEqual(status,200)
  self.assertEqual(json.loads(body)['state'],'PAYMENT_REVIEW')
  self.assertEqual(json.loads(body)['total'],39000)
  status,body=self.req('/api/actions',{'order_id':oid,'action':'approve_payment','funds_verified':True,'bank_reference':'TESTREF'},key=self.key);self.assertEqual(json.loads(body)['state'],'PREPARING')
  status,body=self.req('/api/dispatch',{},key=self.key);self.assertEqual(json.loads(body)['mode'],'dry_run')
 def test_intake_cannot_change_config(self):self.assertEqual(self.req('/api/config',{},key=self.intake)[0],401)
if __name__=='__main__':unittest.main()
