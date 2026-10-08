import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_journey
class V2(unittest.TestCase):
 setUp=test_journey.Journey.setUp
 tearDown=test_journey.Journey.tearDown
 msg=test_journey.Journey.msg
 receipt=test_journey.Journey.receipt
 def test_saved_address_confirmation(self):
  self.o=self.e.create(dict(self.data,source_id='saved',phone='0561234567',initial_address='Building 2710 apartment 506'))
  o=self.e.incoming({'id':'c1','from':self.o['phone'],'type':'text','text':{'body':'CONFIRM CHEM-OL 1'}})
  self.assertEqual(o['state'],'AWAIT_ADDRESS_CONFIRM')
  o=self.e.incoming({'id':'c2','from':self.o['phone'],'type':'text','text':{'body':'CONFIRM'}})
  self.assertEqual(o['state'],'AWAIT_RECEIPT');self.assertEqual(o['address'],'Building 2710 apartment 506')
 def test_saved_map_needs_building(self):
  self.o=self.e.create(dict(self.data,source_id='map',phone='0561234567',initial_address='https://maps.app.goo.gl/example'))
  self.e.incoming({'id':'c1','from':self.o['phone'],'type':'text','text':{'body':'CONFIRM CHEM-OL 1'}})
  o=self.e.incoming({'id':'c2','from':self.o['phone'],'type':'text','text':{'body':'CONFIRM'}})
  self.assertEqual(o['state'],'AWAIT_ADDRESS')
 def test_simple_confirm_uses_registered_choice(self):
  self.e.config['request_aliases']={'Chemistry':{'OL Cambridge':'CHEM-OL'}}
  self.assertEqual(self.msg(value='CONFIRM')['state'],'AWAIT_LOCATION')
 def test_unpriced_request_never_uses_ol_price(self):
  self.e.config['unpriced_requests']={'Chemistry':['AS unknown']}
  o=self.e.create(dict(self.data,source_id='as',phone='0561234567',package='AS unknown'))
  self.assertEqual(o['state'],'REVIEW');self.assertIsNone(o['total']);self.assertEqual(len(self.e.details(o['id'])['outbox']),1)
 def test_multiorder_selection_keeps_receipts_separate(self):
  other=self.e.create(dict(self.data,source_id='other',name='Other child'))
  o=self.msg(value='ORDER '+self.o['id']+' CONFIRM CHEM-OL 1');self.assertEqual(o['id'],self.o['id'])
  self.assertEqual(self.e.details(other['id'])['state'],'AWAIT_PACKAGE')
 def test_multiorder_stop_stops_all(self):
  self.e.create(dict(self.data,source_id='other'));self.msg(value='STOP')
  self.assertTrue(all(o['consent']==0 for o in self.e.list()))
 def test_workorder_created_only_after_funds_review(self):
  self.receipt();self.assertEqual(self.e.details(self.o['id'])['workorders'],[])
  self.e.action(self.o['id'],'approve_payment',{'funds_verified':True,'bank_reference':'F1'})
  job=self.e.details(self.o['id'])['workorders'][0];self.assertIn('OL Cambridge',job['body']);self.assertEqual(job['status'],'READY')
 def test_packing_required_before_dispatch(self):
  self.e.config['require_packing_confirmation']=True;self.receipt();self.e.action(self.o['id'],'approve_payment',{'funds_verified':True,'bank_reference':'F1'})
  from core import Invalid
  with self.assertRaises(Invalid):self.e.action(self.o['id'],'dispatch',{'eta':'Today','tracking':'T1'})
  self.e.action(self.o['id'],'mark_printed',{});self.e.action(self.o['id'],'mark_packed',{})
  self.assertEqual(self.e.action(self.o['id'],'dispatch',{'eta':'Today','tracking':'T1'})['state'],'SHIPPED')
 def test_internal_recipient_is_not_customer(self):
  self.e.config['internal_recipients']={'printing':'0561234567'};self.receipt();self.e.action(self.o['id'],'approve_payment',{'funds_verified':True,'bank_reference':'F1'})
  jobs=[q for q in self.e.details(self.o['id'])['outbox'] if q['internal']];self.assertEqual(jobs[0]['target_phone'],'971561234567');self.assertNotEqual(jobs[0]['target_phone'],self.o['phone'])
 def test_internal_delivery_independent_of_opt_out(self):
  self.e.config['internal_recipients']={'printing':'0561234567'};self.receipt();self.e.action(self.o['id'],'approve_payment',{'funds_verified':True,'bank_reference':'F1'});self.msg(value='STOP')
  q=self.e.claim();self.assertEqual(q['internal'],1);self.assertEqual(q['order']['phone'],'971561234567')
if __name__=='__main__':unittest.main()
