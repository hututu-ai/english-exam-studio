import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import teaching_review as tr

class SemanticReview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.item={'word':'library','meaning':'图书馆','context':'本句为图书馆开放时间','paragraph_id':'p','quote':'The library opens at nine.'}
        self.s={'id':'A','paragraphs':[{'id':'p','text':'The library opens at nine.'}], 'vocabulary':[self.item],'questions':[{'id':'1','evidence':[{'paragraph_id':'p','quote':'opens at nine'}]}]}
        self.exam={'title':'test','sections':[self.s]}
    def reviewed(self):
        review=tr.draft(self.exam)
        for row in review['items']:
            row.update(status='accepted',reviewer='synthetic unit fixture',judgment='本单元样例核对：名词在句中指开放的图书馆，与后续时间表达一致。',evidence=[{'paragraph_id':'p','quote':'The library opens at nine.','reason':'地点名词与开放时间相连，提供具体语境依据。'}])
        return review
    def test_pending_not_accepted(self):self.assertTrue(tr.validate(self.exam,tr.draft(self.exam),self.base)['errors'])
    def test_reviewed_record_passes(self):self.assertEqual(tr.validate(self.exam,self.reviewed(),self.base)['errors'],[])
    def test_wrong_sense_changed_after_review_rejected(self):
        review=self.reviewed();self.item['meaning']='医院';self.assertTrue(tr.validate(self.exam,review,self.base)['errors'])
    def test_fake_quote_rejected(self):
        r=self.reviewed();r['items'][0]['evidence'][0]['quote']='Not in passage';self.assertTrue(tr.validate(self.exam,r,self.base)['errors'])
    def test_arbitrary_the_gap_not_an_answer_clue(self):
        self.s['blanks']=[{'paragraph_id':'p','start':0,'end':3,'focus_type':'answer_evidence','question_ids':['1'],'purpose':'声称是本题时间答案的证据'}]
        self.assertTrue(any('答案引句' in x for x in tr.validate(self.exam,self.reviewed(),self.base)['errors']))
    def test_phonetic_gap_requires_actual_reason(self):
        self.s['blanks']=[{'paragraph_id':'p','start':0,'end':3,'focus_type':'phonetic_difficulty','purpose':'训练该表达在语流中的弱读形式'}]
        self.assertTrue(any('语音难点' in x for x in tr.validate(self.exam,self.reviewed(),self.base)['errors']))
    def test_source_url_alone_does_not_pass(self):
        self.s['culture_background']=[{'title':'background','sources':[{'url':'https://example.invalid','supports':'claim'}]}]
        self.assertTrue(any('snapshot' in x for x in tr.validate(self.exam,self.reviewed(),self.base)['errors']))
    def test_source_excerpt_must_be_in_snapshot(self):
        text='This is the archived source paragraph, used only by a synthetic test.'
        (self.base/'snapshot.json').write_text(json.dumps({'url':'https://example.invalid','retrieved_at':'2026-09-15','text':text,'text_sha256':tr.fingerprint(text),'status':'retrieved'}))
        self.s['culture_background']=[{'title':'background','sources':[{'url':'https://example.invalid','supports':'claim','snapshot':'snapshot.json','excerpt':'a false quotation not in source'}]}]
        self.assertTrue(any('excerpt' in x for x in tr.validate(self.exam,self.reviewed(),self.base)['errors']))
    def test_duplicate_review_rejected(self):
        r=self.reviewed();r['items']*=2;self.assertTrue(tr.validate(self.exam,r,self.base)['errors'])
