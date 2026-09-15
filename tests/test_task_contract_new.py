"""New-task consent, material binding, semantic review and explicit rebuild integration."""
import contextlib,io,json,sys,tempfile,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import build,task_contract,teaching_review
from preferences import DEFAULTS,apply_plan

class NewTaskContract(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.src=ROOT/'examples/demo-reading.json';self.ledger=ROOT/'examples/source-ledger.json';self.out=self.root/'out'
        # Known synthetic fixture: the reply is explicitly test data, not a teacher confirmation.
        self.data={'confirmed':True,'task_id':str(uuid.uuid4()),'teacher_response':'合成测试选择：阅读、基础功能，不是真实教师回答',
            'sections':'reading','mode':'lesson','features':{k:False for k in DEFAULTS},
            'materials':task_contract.material_records(['paper='+str(self.ledger)])}
        # The ledger itself is not a material; use its declared, original synthetic source.
        ledger=json.loads(self.ledger.read_text(encoding='utf-8'));self.material=self.root/'paper.txt';self.material.write_text('test paper')
        for row in ledger['sources']:
            if row.get('path'):row['path']=str((self.ledger.parent/row['path']).resolve())
        self.l=self.root/'ledger.json';ledger['sources'].append({'role':'paper','path':str(self.material),'sha256':task_contract.sha(self.material)})
        self.l.write_text(json.dumps(ledger));self.data['materials']=task_contract.material_records(['paper='+str(self.material)])
        self.plan=self.root/'plan.json';self.plan.write_text(json.dumps(self.data))
    def completed_fixture_review(self):
        doc=build.prune_features(apply_plan(json.loads(self.src.read_text(encoding='utf-8')),self.data))
        review=teaching_review.draft(doc)
        for row in review['items']:
            sid=row['id'].split('/')[0];section=next(s for s in doc['sections'] if s['id']==sid);p=section['paragraphs'][0]
            row.update(status='accepted',reviewer='synthetic contract test',judgment='合成契约测试的固定输入，不用于证明真实教学内容已经核对。',evidence=[{'paragraph_id':p['id'],'quote':p['text'],'reason':'仅用于验证复核记录与当前合成材料的绑定和传递。'}])
        path=self.root/'review.json';path.write_text(json.dumps(review));return path
    def test_new_public_entry_and_explicit_rebuild(self):
        review=self.completed_fixture_review()
        with contextlib.redirect_stdout(io.StringIO()):build.build(self.src,self.out,self.l,plan=self.plan,review=review)
        self.assertTrue((self.out/'generation-plan.json').is_file())
        with contextlib.redirect_stdout(io.StringIO()):build.build(self.src,self.root/'rebuilt',self.l,rebuild_from=self.out,review=review)
        report=json.loads((self.root/'rebuilt'/'build-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['task_contract']['task_id'],self.data['task_id'])
    def test_modified_old_html_blocks_rebuild(self):
        review=self.completed_fixture_review()
        with contextlib.redirect_stdout(io.StringIO()):build.build(self.src,self.out,self.l,plan=self.plan,review=review)
        (self.out/'index.html').write_text('changed')
        with self.assertRaisesRegex(ValueError,'旧 HTML'):build.build(self.src,self.root/'rebuilt',self.l,rebuild_from=self.out,review=review)
    def test_new_without_plan_stops(self):
        with self.assertRaisesRegex(ValueError,'先询问老师'):build.build(self.src,self.out,self.ledger)
    def test_response_required(self):
        self.data['teacher_response']=''
        with self.assertRaisesRegex(ValueError,'本次'):task_contract.validate(self.data,self.l)
    def test_changed_material_stops(self):
        self.material.write_text('changed')
        with self.assertRaisesRegex(ValueError,'材料已变化'):task_contract.validate(self.data,self.l)
    def test_ledger_mismatch_stops(self):
        with self.assertRaisesRegex(ValueError,'台账不一致'):task_contract.validate(self.data,self.ledger)
    def test_plan_and_material_validate(self):
        self.assertTrue(task_contract.validate(self.data,self.l)['confirmed'])
    def test_no_review_stops(self):
        with self.assertRaisesRegex(ValueError,'独立内容复核'):build.build(self.src,self.out,self.l,plan=self.plan)
    def test_demo_does_not_accept_teacher_paths(self):
        own=self.root/'paper.json';own.write_bytes(self.src.read_bytes())
        with self.assertRaisesRegex(ValueError,'合成示例'):build.build(own,self.out,self.ledger,demo=True)
    def test_stale_review_stops(self):
        doc=build.prune_features(apply_plan(json.loads(self.src.read_text(encoding='utf-8')),self.data));review=teaching_review.draft(doc)
        doc['title']='changed';self.assertTrue(teaching_review.validate(doc,review,self.root)['errors'])
    def test_unknown_old_directory_stops(self):
        with self.assertRaisesRegex(ValueError,'旧课件缺少'):build.build(self.src,self.out,self.l,rebuild_from=self.root/'missing')
    def test_confirmed_choices_cannot_be_overridden(self):
        with self.assertRaisesRegex(ValueError,'覆盖教师'):build.build(self.src,self.out,self.l,plan=self.plan,selection='all,cloze')

if __name__=='__main__':unittest.main()
