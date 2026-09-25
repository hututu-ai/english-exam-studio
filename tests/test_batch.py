import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import batch
from preferences import DEFAULTS as FEATURES
class Batch(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.base=Path(self.t.name)
  (self.base/'a.pdf').write_bytes(b'a');(self.base/'b.pdf').write_bytes(b'b')
  self.m={'confirmed':True,'teacher_response':'两套都只做阅读，只用基础功能，材料配对正确','settings':{'sections':'reading','mode':'lesson','features':{k:False for k in FEATURES}},'papers':[{'id':'a','materials':{'paper':'a.pdf'}},{'id':'b','materials':{'paper':'b.pdf'}}]}
 def run_init(self):
  p=self.base/'input.json';p.write_text(json.dumps(self.m),encoding='utf-8');return batch.initialize(p,self.base/'batch')
 def test_independent_jobs_and_pending(self):
  self.assertEqual(self.run_init()['papers'],2);a=json.loads((self.base/'batch/a/generation-plan.json').read_text(encoding='utf-8'));b=json.loads((self.base/'batch/b/generation-plan.json').read_text(encoding='utf-8'));self.assertNotEqual(a['task_id'],b['task_id']);self.assertNotEqual(a['materials'],b['materials']);self.assertEqual(batch.status(self.base/'batch')['status'],'incomplete')
 def test_declined_confirmation(self):
  self.m['confirmed']=False
  with self.assertRaisesRegex(ValueError,'批量任务须先确认'):self.run_init()
 def test_empty(self):
  self.m['papers']=[]
  with self.assertRaisesRegex(ValueError,'批量清单没有试卷'):self.run_init()
 def test_unsafe_id(self):
  self.m['papers'][0]['id']='../bad'
  with self.assertRaisesRegex(ValueError,'每套试卷 ID 必须唯一'):self.run_init()
 def test_pairing_duplicate_requires_confirmation(self):
  self.m['papers'][1]['materials']['paper']='a.pdf'
  with self.assertRaisesRegex(ValueError,'共用了同一材料'):self.run_init()
  self.m['papers'][1]['shared_materials_confirmed']=True;self.assertEqual(self.run_init()['papers'],2)
 def test_no_overwrite(self):
  self.run_init()
  with self.assertRaisesRegex(ValueError,'批量输出目录已存在'):self.run_init()
 def test_directory_escape(self):
  self.run_init();p=self.base/'batch/batch.json';d=json.loads(p.read_text(encoding='utf-8'));d['jobs'][0]['directory']='../x';p.write_text(json.dumps(d),encoding='utf-8')
  with self.assertRaisesRegex(ValueError,'批量任务目录越界'):batch.status(self.base/'batch')
 def test_fake_complete_is_refused(self):
  self.run_init();o=self.base/'batch/a/output';o.mkdir()
  for n in ['index.html','exam.json','build-report.json','generation-plan.json','teaching-review.json','browser-check.json']:(o/n).write_text('{}',encoding='utf-8')
  r=batch.status(self.base/'batch');self.assertEqual(r['papers'][0]['status'],'needs_review');self.assertIn('产物使用了另一套生成计划',r['papers'][0]['reason'])
 def test_delivery_gates_and_success(self):
  from unittest.mock import patch
  from contextlib import ExitStack
  self.run_init();root=self.base/'batch'
  for job in ('a','b'):
   folder=root/job;o=folder/'output';o.mkdir()
   plan=json.loads((folder/'generation-plan.json').read_text(encoding='utf-8'))
   files={'index.html':'html','exam.json':{},'generation-plan.json':plan,'teaching-review.json':{},'browser-check.json':{'status':'passed','html_sha256':'checked'},'build-report.json':{'task_contract':{'task_id':plan['task_id']}}}
   for name,value in files.items():(o/name).write_text(value if isinstance(value,str) else json.dumps(value),encoding='utf-8')
   (folder/'exam.json').write_text('{}',encoding='utf-8')
  with ExitStack() as stack:
   stack.enter_context(patch('task_contract.validate',return_value={}))
   stack.enter_context(patch('verify_output.verify_output',return_value={'html_sha256':'checked'}))
   stack.enter_context(patch('preferences.apply_plan',side_effect=lambda data,plan:data))
   stack.enter_context(patch('build.prune_features',side_effect=lambda data:data))
   review=stack.enter_context(patch('teaching_review.validate',return_value={'errors':[]}))
   qa=stack.enter_context(patch('qa_report.check',return_value={'status':'ok'}))
   self.assertEqual(batch.status(root)['status'],'verified')
   report=root/'a/output/build-report.json';saved=report.read_text(encoding='utf-8');report.write_text('{}',encoding='utf-8')
   result=batch.status(root);self.assertEqual(result['status'],'incomplete');self.assertEqual(result['papers'][1]['status'],'verified');self.assertEqual(result['papers'][0]['reason'],'构建报告未绑定本套试卷')
   report.write_text(saved,encoding='utf-8');review.return_value={'errors':['unreviewed']}
   self.assertEqual(batch.status(root)['papers'][0]['reason'],'教学复核记录尚未完成或已过期')
   review.return_value={'errors':[]};qa.return_value={'status':'incomplete'}
   self.assertEqual(batch.status(root)['papers'][0]['reason'],'逐题内容与试听复核记录未通过')
