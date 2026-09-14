import copy,json,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from culture import validate_culture
class CultureTests(unittest.TestCase):
    def setUp(self):
        self.s={'paragraphs':[{'id':'p1','text':'A fictional example.'}],'culture_background':[{'paragraph_id':'p1','quote':'A fictional example.','title':'Schema fixture','explanation':'Background claim','reading_connection':'Explains the contrast in this sentence','teaching_note':'A classroom explanation','sources':[{'title':'Fixture source','url':'https://example.org','supports':'Background claim'}]}]}
    def test_structural_contract(self):validate_culture(self.s)
    def test_reject_unlinked_missing_and_placeholder(self):
        for key,value in [('quote','Absent'),('reading_connection',''),('title','合成控件测试卡')]:
            s=copy.deepcopy(self.s);s['culture_background'][0][key]=value
            with self.assertRaises(AssertionError):validate_culture(s)
    def test_source_must_map_to_claim(self):
        self.s['culture_background'][0]['sources'][0].pop('supports')
        with self.assertRaises(AssertionError):validate_culture(self.s)
    def test_browser_fixture_carries_valid_culture_content(self):
        # The UI check only opens the culture card when the fixture really has
        # culture_background data. It previously carried only culture_note, so
        # 'culture-card-and-source-location' silently never ran.
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result=subprocess.run([sys.executable,str(ROOT/'tests/make_browser_fixture.py'),str(root/'src'),str(root/'out')],
                                  capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
            self.assertEqual(result.returncode,0,result.stderr)
            exam=json.loads((root/'out/exam.json').read_text(encoding='utf-8'))
            sections=[s for s in exam['sections'] if s.get('culture_background')]
            self.assertTrue(sections,'fixture must include culture_background or the browser check skips the culture card')
            for section in sections:validate_culture(section)
