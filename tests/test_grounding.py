import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from grounding import span_problem,validate_vocabulary,validate_structure,validate_sentences,validate_blank_tokens,validate_teaching_substance
class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.base={'paragraphs':[{'id':'p1','text':'Mia showed students how to repair a loose chair leg carefully.'}]}
    def test_vocabulary_requires_real_context_quote(self):
        good={**self.base,'vocabulary':[{'word':'repair','meaning':'修理','context':'此处指修好椅子腿','paragraph_id':'p1','quote':'how to repair a loose chair leg'}]}
        validate_vocabulary(good)
        for change in ({'quote':'a sentence that never appears'},{'quote':''},{'context':''},{'paragraph_id':'p9'}):
            bad=copy.deepcopy(good);bad['vocabulary'][0].update(change)
            with self.assertRaises(AssertionError):validate_vocabulary(bad)
    def test_vocabulary_quote_must_contain_the_word(self):
        bad={**self.base,'vocabulary':[{'word':'wrench','meaning':'扳手','context':'工具','paragraph_id':'p1','quote':'how to repair a loose chair leg'}]}
        with self.assertRaises(AssertionError):validate_vocabulary(bad)
    def test_derived_form_must_point_at_source_and_not_fake_a_quote(self):
        good={**self.base,'vocabulary':[{'word':'repaired','meaning':'修好了','context':'过去式','source_paragraph':'p1'}]}
        validate_vocabulary(good)
        fake=copy.deepcopy(good);fake['vocabulary'][0]['quote']='invented sentence'
        with self.assertRaises(AssertionError):validate_vocabulary(fake)
        lost=copy.deepcopy(good);lost['vocabulary'][0]['source_paragraph']='p9'
        with self.assertRaises(AssertionError):validate_vocabulary(lost)
    def test_structure_needs_evidence_and_nonempty_paragraphs(self):
        good={**self.base,'structure':[{'title':'示范','paragraph_ids':['p1'],'analysis':'用例子说明','quote':'showed students how to repair'}]}
        validate_structure(good)
        for change in ({'paragraph_ids':[]},{'quote':''},{'quote':'not in the passage'},{'analysis':''},{'title':''}):
            bad=copy.deepcopy(good);bad['structure'][0].update(change)
            with self.assertRaises(AssertionError):validate_structure(bad)
    def test_sentences_need_source_and_analysis_fields(self):
        good={**self.base,'sentences':[{'paragraph_id':'p1','quote':'Mia showed students how to repair a loose chair leg carefully.','backbone':'Mia showed students.','chunks':'主谓宾','logic':'举例','translation':'米娅教学生如何修椅子腿。'}]}
        validate_sentences(good)
        for key in ('quote','backbone','chunks','logic','translation'):
            bad=copy.deepcopy(good);bad['sentences'][0].pop(key)
            with self.assertRaises(AssertionError):validate_sentences(bad)
    def test_listening_blanks_must_cover_a_whole_real_word(self):
        section={**self.base,'blanks':[{'paragraph_id':'p1','start':27,'end':33}]}
        validate_blank_tokens(section)
        for start,end in [(33,34),(28,33),(27,32),(61,62)]:
            bad=copy.deepcopy(section);bad['blanks'][0].update({'start':start,'end':end})
            with self.assertRaises(AssertionError):validate_blank_tokens(bad)
    def substance(self):
        return {'id':'A','paragraphs':[{'id':'p1','text':'Mia showed students how to repair.'}],'questions':[
            {'id':'21','analysis':'第一题依据 so that 说明目的。','pitfall':'不要把管理用途补进原文。','type_note':'目的题看 so that。','strategy':'先定位再核对目的。','solve_steps':['定位 notebook。','识别 so that 目的。','核对选项 B。'],'distractors':{'A':'原文未说收费。','B':'原文未收集电话。'}},
            {'id':'22','analysis':'第二题要求概括两段主旨。','pitfall':'不要用细节代替主题。','type_note':'标题题要覆盖全文。','strategy':'先概括每段再选标题。','solve_steps':['概括第一段。','概括第二段。','选择覆盖全文的 C。'],'distractors':{'A':'文章没有出售家具。','B':'文章没有比赛安排。'}}]}
    def test_span_problem_is_the_shared_rule_for_blanks_and_quotes(self):
        """挖空与引用范围共用一条判据（1.0.103）：不许落在空白、纯标点或单词中间。"""
        text='The museum opens at nine.'
        cases=[(4,10,None),                  # 'museum' 完整词
               (0,3,None),                   # 'The'
               (len(text)-5,len(text),None), # 'nine.' 连标点一起取
               (10,13,'half_word_start'),    # 取 ' op'：切在 museum 中间
               (4,8,'half_word_end'),        # 起点在词首、终点落在单词中间
               (3,4,'blank'),                # 只取一个空格
               (24,25,'punctuation'),        # 单独一个句号不是引文
               (0,0,'invalid'),(5,3,'invalid'),(0,999,'invalid')]
        for start,end,want in cases:
            with self.subTest(start=start,end=end):
                self.assertEqual(span_problem(text,start,end),want)
    def test_span_problem_allows_punctuation_only_inside_a_span(self):
        self.assertEqual(span_problem('He said "hello" loudly.',8,15),None)
        # 引用可能与挖空不同：中文引文不算纯标点（挖空仍只认英文词）
        self.assertEqual(span_problem('请阅读下列短文。',0,7),None)
        self.assertEqual(span_problem('请阅读下列短文。',0,7,require_english_word=True),'punctuation')
    def test_span_problem_does_not_mistake_chinese_for_a_cut_word(self):
        """中文没有词边界：范围贴着英文单词外侧取整段中文不能被判成截断。"""
        text='他读 book 很认真。'
        self.assertEqual(span_problem(text,0,2),None)
        self.assertEqual(span_problem(text,3,7),None)   # 'book'
        self.assertEqual(span_problem(text,10,len(text)),None)
    def test_span_problem_rejects_punctuation_only_spans(self):
        self.assertEqual(span_problem('The museum opens.',3,3),'invalid')
        self.assertEqual(span_problem('Hi!! Ok',2,4),'punctuation')
    def test_substance_accepts_varied_real_teaching(self):
        validate_teaching_substance(self.substance())
        fine=self.substance();fine['questions'][0]['strategy']='本策略按原文语境分析。'
        validate_teaching_substance(fine)
    def test_substance_rejects_copy_pasted_and_empty_teaching(self):
        good=self.substance()
        cases=[('analysis','复制套话'),('pitfall','复制套话'),('type_note','复制套话'),('strategy','复制套话')]
        for field,message in cases:
            bad=copy.deepcopy(good);bad['questions'][1][field]=bad['questions'][0][field]
            with self.assertRaisesRegex(AssertionError,message):validate_teaching_substance(bad)
        bad=copy.deepcopy(good);bad['questions'][1]['solve_steps']=list(bad['questions'][0]['solve_steps'])
        with self.assertRaisesRegex(AssertionError,'解题步骤'):validate_teaching_substance(bad)
        bad=copy.deepcopy(good);bad['questions'][0]['distractors']['A']=''
        with self.assertRaisesRegex(AssertionError,'辨析为空'):validate_teaching_substance(bad)
        bad=copy.deepcopy(good);bad['questions'][0]['distractors']['A']=bad['questions'][0]['distractors']['B']
        with self.assertRaisesRegex(AssertionError,'分别说明'):validate_teaching_substance(bad)
    def test_substance_rejects_placeholder_markers(self):
        for marker in ('TODO','待补充','此处省略','Lorem ipsum','占位符'):
            bad=self.substance();bad['questions'][0]['analysis']=f'{marker} 的说明'
            with self.assertRaisesRegex(AssertionError,'占位'):validate_teaching_substance(bad)
