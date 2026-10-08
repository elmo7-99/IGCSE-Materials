import copy,json,tempfile,time,unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import Engine,Invalid,phone,validate_config
from provider import Meta,dispatch

CFG={'packages':[{'sku':'CHEM-OL','name':'OL Cambridge','subject':'Chemistry','teacher':'Dr Peter Alfred','price_fils':38000,'active':True,'image_url':'https://example.org/chemistry.jpg'}],
 'delivery_fils':{'Sharjah (الشارقة)':2000},'bank':{'name':'TEST BANK','holder':'TEST HOLDER','iban':'TEST ONLY'},
 'templates':{'en':{'intro':'test_intro','update':'test_update'},'ar':{'intro':'test_intro_ar','update':'test_update_ar'}}}
class Journey(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.e=Engine(Path(self.tmp.name)/'db',copy.deepcopy(CFG));self.count=0
  self.data={'source_id':'form-row-1','name':'Test Customer','phone':'0551234567','subject':'Chemistry','city':'Sharjah (الشارقة)','package':'OL Cambridge','lang':'en','consent':True}
  self.o=self.e.create(self.data)
 def tearDown(self):self.tmp.cleanup()
 def msg(self,typ='text',value=None):
  self.count+=1;m={'id':str(self.count),'from':'971551234567','type':typ}
  if typ=='text':m['text']={'body':value}
  else:m[typ]=value
  return self.e.incoming(m)
 def receipt(self):
  self.msg(value='CONFIRM CHEM-OL 2');self.msg('location',{'latitude':25.3,'longitude':55.4});self.msg(value='Sharjah, Building 1, Flat 2');return self.msg('image',{'id':'MEDIA-1','mime_type':'image/jpeg'})
 def test_complete_journey(self):
  o=self.receipt();self.assertEqual(o['state'],'PAYMENT_REVIEW');self.assertEqual(o['total'],78000)
  o=self.e.action(o['id'],'approve_payment',{'funds_verified':True,'bank_reference':'BANK-001'});self.assertEqual(o['state'],'PREPARING')
  o=self.e.action(o['id'],'dispatch',{'eta':'Tomorrow 2–5pm','tracking':'SHIP-001'});self.assertEqual(o['state'],'SHIPPED')
  o=self.e.action(o['id'],'deliver',{'proof':'Courier confirmation'});self.assertEqual(o['state'],'DELIVERED')
  self.assertEqual(len(self.e.details(o['id'])['outbox']),8)
 def test_duplicate_registration(self):self.assertEqual(self.e.create(self.data)['id'],self.o['id']);self.assertEqual(len(self.e.list()),1)
 def test_multiple_orders_same_parent(self):
  d=dict(self.data,source_id='other');o=self.e.create(d)
  self.assertNotEqual(o['id'],self.o['id']);self.assertTrue(self.msg(value='hello')['needs_order_selection'])
 def test_duplicate_message(self):
  m={'id':'duplicate','from':self.o['phone'],'type':'text','text':{'body':'CONFIRM CHEM-OL 1'}}
  self.e.incoming(m);self.assertTrue(self.e.incoming(m)['duplicate']);self.assertEqual(len(self.e.details(self.o['id'])['outbox']),2)
 def test_invalid_package_does_not_change_price(self):
  o=self.msg(value='CONFIRM RANDOM 1');self.assertEqual(o['state'],'AWAIT_PACKAGE');self.assertIsNone(o['total'])
 def test_receipt_is_not_payment_confirmation(self):self.assertEqual(self.receipt()['state'],'PAYMENT_REVIEW')
 def test_cannot_ship_before_payment(self):
  with self.assertRaises(Invalid):self.e.action(self.o['id'],'dispatch',{'eta':'Soon','tracking':'X'})
 def test_cannot_approve_without_verifying_funds(self):
  self.receipt()
  with self.assertRaises(Invalid):self.e.action(self.o['id'],'approve_payment',{'bank_reference':'X'})
 def test_stop_cancels_queue(self):
  o=self.msg(value='STOP');self.assertEqual(o['consent'],0);self.assertIsNone(self.e.claim())
  self.assertEqual(self.e.details(o['id'])['outbox'][0]['state'],'cancelled')
 def test_staff_handoff(self):self.assertEqual(self.msg(value='STAFF')['paused'],1)
 def test_three_invalid_messages_pause(self):
  for _ in range(3):o=self.msg(value='hello')
  self.assertEqual(o['paused'],1)
 def test_missing_price_goes_to_review(self):
  self.e.config['packages'][0]['active']=False
  d=dict(self.data,source_id='2',phone='0561234567');self.assertEqual(self.e.create(d)['state'],'REVIEW')
 def test_missing_delivery_fee_no_total(self):
  self.e.config['delivery_fils']={};o=self.msg(value='CONFIRM CHEM-OL 1');self.assertIsNone(o['total'])
 def test_reject_receipt(self):
  o=self.receipt();o=self.e.action(o['id'],'reject_payment',{'reason':'Amount differs'});self.assertEqual(o['state'],'AWAIT_RECEIPT')
 def test_missing_bank_blocks_payment_request(self):
  self.e.config['bank']={};o=self.receipt();self.assertEqual(o['state'],'REVIEW')
 def test_no_consent_rejected(self):
  with self.assertRaises(Invalid):self.e.create(dict(self.data,source_id='2',consent=False))
 def test_arabic_phone(self):self.assertEqual(phone('٠٥٥١٢٣٤٥٦٧'),'971551234567')
 def test_old_inbound_uses_template(self):
  self.e.incoming({'id':'old','from':self.o['phone'],'timestamp':str(time.time()-90000),'type':'text','text':{'body':'CONFIRM CHEM-OL 1'}})
  q=self.e.claim();self.e.finish(q['id'],'sent');q=self.e.claim();self.assertEqual(Meta(CFG).payload(q)['type'],'template')
 def test_intro_requires_template_even_with_open_window(self):
  q=self.e.claim();q['order']['last_inbound']=time.time();self.assertEqual(Meta(CFG).payload(q)['type'],'template')
 def test_window_reply_can_be_text(self):
  q=self.e.claim();q['kind']='location';q['order']['last_inbound']=time.time();self.assertEqual(Meta(CFG).payload(q)['type'],'text')
 def test_dry_run_never_consumes_queue(self):
  self.assertEqual(dispatch(self.e)['mode'],'dry_run');self.assertEqual(self.e.details(self.o['id'])['outbox'][0]['state'],'pending')
 def test_same_reference_not_usable_twice(self):
  self.receipt();self.e.action(self.o['id'],'approve_payment',{'funds_verified':True,'bank_reference':'X'})
  self.e.action(self.o['id'],'dispatch',{'eta':'Today','tracking':'X'});self.e.action(self.o['id'],'deliver',{'proof':'Received'})
  self.o=self.e.create(dict(self.data,source_id='second'));self.receipt()
  with self.assertRaises(Invalid):self.e.action(self.o['id'],'approve_payment',{'funds_verified':True,'bank_reference':'X'})
 def test_crashed_sender_marked_uncertain(self):
  q=self.e.claim()
  with self.e.conn() as c:c.execute('UPDATE outbox SET claimed=? WHERE id=?',(time.time()-200,q['id']))
  self.assertIsNone(self.e.claim());self.assertEqual(self.e.details(self.o['id'])['outbox'][0]['state'],'uncertain')
 def test_failed_message_blocks_later_messages(self):
  self.msg(value='CONFIRM CHEM-OL 1');q=self.e.claim();self.e.finish(q['id'],'failed','test');self.assertIsNone(self.e.claim())
 def test_reminder_only_once(self):
  with self.e.conn() as c:c.execute('UPDATE orders SET updated=?',(time.time()-90000,))
  self.assertEqual(self.e.reminder(),1);self.assertEqual(self.e.reminder(),0)
 def test_config_rejects_duplicate_sku(self):
  c=copy.deepcopy(CFG);c['packages'].append(c['packages'][0])
  with self.assertRaises(Invalid):validate_config(c)
 def test_html_payload_remains_data(self):
  o=self.msg(value='CONFIRM CHEM-OL 1');self.msg('location',{'latitude':25,'longitude':55});o=self.msg(value='<script>alert(1)</script>');self.assertEqual(o['address'],'<script>alert(1)</script>')
if __name__=='__main__': unittest.main()
