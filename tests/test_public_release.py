import json,sys,unittest,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core import Invalid,validate_config
class PublicRelease(unittest.TestCase):
 def test_config_requires_packages(self):
  with self.assertRaises(Invalid):validate_config({})
 def test_negative_delivery_fee_rejected(self):
  with self.assertRaises(Invalid):validate_config({'packages':[],'delivery_fils':{'City':-1}})
 def test_bad_package_type_rejected(self):
  with self.assertRaises(Invalid):validate_config({'packages':['not an object']})
 def test_config_has_no_customer_sheet_id(self):
  cfg=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
  self.assertEqual(cfg['source_sheet']['spreadsheet_id'],'YOUR_SPREADSHEET_ID')
 def test_no_runtime_data_or_env_in_release(self):
  if not shutil.which('git') or not (ROOT/'.git').exists(): self.skipTest('Tracked-file check requires a git checkout')
  files=subprocess.check_output(['git','-C',str(ROOT),'ls-files'],text=True).splitlines()
  self.assertNotIn('.env',files)
  self.assertFalse(any(p.startswith('data/') for p in files))
 def test_form_source_is_configurable(self):
  source=(ROOT/'integrations/google-forms.gs').read_text(encoding='utf-8')
  self.assertIn("getProperty('SOURCE_SPREADSHEET_ID')",source)
if __name__=='__main__':unittest.main()
