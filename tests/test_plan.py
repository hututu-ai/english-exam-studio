"""Turning a teacher's answers into a valid generation-plan.json.

Weak hosts have no real multi-select widget, so teachers reply with numbers ("1、3、5").
Hand-converting that is where it goes wrong: a plan that omits any of the seven features is
refused by apply_plan with a confusing build error. The tool must always record all seven, and
must never claim the teacher answered when they did not.
"""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import preferences

def run(*args,cwd=None):
    return subprocess.run([sys.executable,str(ROOT/'scripts/plan.py'),*map(str,args)],
                          capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60,
                          cwd=str(cwd) if cwd else None)

class MenuTests(unittest.TestCase):
    def test_menu_numbers_every_feature_and_range(self):
        result=run('menu')
        self.assertEqual(result.returncode,0,result.stderr)
        for index,(_,label,_) in enumerate(__import__('plan').FEATURES,1):
            self.assertIn(f'{index}. {label}',result.stdout)
        for code in ('A.','B.','C.'):
            self.assertIn(code,result.stdout)
        self.assertIn('基础功能',result.stdout)

class MakeTests(unittest.TestCase):
    def make(self,root,*args):
        result=run('make','--out',root/'plan.json',*args)
        plan=json.loads((root/'plan.json').read_text(encoding='utf-8')) if (root/'plan.json').is_file() else None
        return result,plan
    def test_numbered_reply_records_all_seven_features(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result,plan=self.make(root,'--confirmed','--range','C','--sections','reading,A','--features','1、3、5')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(set(plan['features']),set(preferences.DEFAULTS))
            self.assertEqual(sorted(key for key,value in plan['features'].items() if value),['annotations','deep_reading','quick_answers'])
            self.assertEqual((plan['sections'],plan['mode']),('reading,A','lesson'))
            # 生成的计划必须能被构建接受
            exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
            self.assertEqual(preferences.apply_plan(exam,plan)['features'],plan['features'])
    def test_listening_range_selects_intensive_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result,plan=self.make(root,'--confirmed','--range','A','--features','基础讲评即可')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((plan['sections'],plan['mode']),('listening','intensive'))
            self.assertFalse(any(plan['features'].values()),'基础讲评即可 must disable every extension')
    def test_all_and_reuse_previous(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            _,first=self.make(root,'--confirmed','--range','B','--features','全部')
            self.assertTrue(all(first['features'].values()))
            (root/'first.json').write_text(json.dumps(first,ensure_ascii=False),encoding='utf-8')
            result,second=self.make(root,'--confirmed','--range','B','--features','沿用上次','--previous',root/'first.json')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(second['features'],first['features'])
    def test_refuses_to_claim_an_unanswered_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result,plan=self.make(root,'--range','B','--features','全部')
            self.assertEqual(result.returncode,1)
            self.assertIn('confirmed',result.stderr)
            self.assertIsNone(plan,'no plan may be written without an actual answer')
    def test_errors_are_actionable(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            cases=[(('--confirmed','--range','C','--features','1'),'--sections'),
                   (('--confirmed','--range','B','--features','9'),'超出范围'),
                   (('--confirmed','--range','B','--features','沿用上次','--previous',root/'none.json'),'找不到上一份计划文件'),
                   (('--confirmed','--range','B','--features','随便'),'无法识别')]
            for args,needle in cases:
                result,_=self.make(root,*args)
                self.assertEqual(result.returncode,1,args)
                self.assertIn(needle,result.stderr,args)
                self.assertNotIn('Traceback',result.stderr)

class CheckTests(unittest.TestCase):
    def test_check_reports_a_complete_plan_and_flags_a_partial_one(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            run('make','--confirmed','--range','B','--features','1,2','--out',root/'plan.json')
            good=run('check',root/'plan.json')
            self.assertEqual(good.returncode,0,good.stdout+good.stderr)
            self.assertEqual(json.loads(good.stdout)['status'],'ok')
            plan=json.loads((root/'plan.json').read_text(encoding='utf-8'));plan['features'].pop('dictionary')
            (root/'partial.json').write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
            bad=run('check',root/'partial.json')
            self.assertEqual(bad.returncode,1)
            self.assertIn('功能必须七项全记',bad.stdout)
