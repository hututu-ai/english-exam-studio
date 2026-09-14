"""逐句译文：必须与原文分句一一对应，且不能拿英文充数、不能悄悄漏句。

老师反馈「没有句子翻译」。展示层做成"整篇逐句"还是"点某句看该句"还没定，但两种都依赖同一份数据：
`paragraph.sentence_translations`（每句一条，顺序与原文一致）。这里先把这个数据层焊死：

* 句数对不上 → 阻断（错位的译文比没有译文更糟）；
* 没翻译的句子 → 允许，但必须用空字符串占位，并出现在待核项里（不能悄悄少一条）；
* 译文里没有中文（等于抄了英文原句）→ 阻断。
"""
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build
from sentence_split import split_sentences

TEXT='Mr. Li is 14 years old. He likes Chinese knots! What about you?'
TWO_TEXTS=['Mr. Li is 14 years old.','He likes Chinese knots!','What about you?']

class Splitter(unittest.TestCase):
    def test_splitter_is_conservative(self):
        self.assertEqual(split_sentences(TEXT),TWO_TEXTS)
        self.assertEqual(split_sentences('The price is 3.5 yuan. It is cheap.'),['The price is 3.5 yuan.','It is cheap.'])
        self.assertEqual(split_sentences('He said, "I am ready." Then he left.'),['He said, "I am ready."','Then he left.'])
        self.assertEqual(split_sentences('No ending punctuation'),['No ending punctuation'])
        self.assertEqual(split_sentences('  '),[])

class SentenceTranslations(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 逐句译文 ')
        self.base=Path(self.temp.name)

    def tearDown(self):self.temp.cleanup()

    def exam(self,translations):
        def question(qid):
            return {'id':qid,'stem':'第 '+qid+' 题','options':{},'answer':'x','answer_status':'sample','answer_source':'原件第 '+qid+' 题',
                    'question_type':'题型','type_note':'第 '+qid+' 题说明','solve_steps':['一'+qid,'二'+qid,'三'+qid],
                    'pitfall':'易错'+qid,'analysis':'解析'+qid,'strategy':'方法'+qid}
        paragraph={'id':'p1','text':TEXT,'translation':'李先生 14 岁。他喜欢中国结！你呢？'}
        if translations is not None:paragraph['sentence_translations']=translations
        return {'title':'逐句译文测试','expected_question_ids':['1','2'],
                'sections':[{'id':'A','kind':'综合填空','title':'综合填空','paragraphs':[paragraph],
                             'quick_words':[{'word':'Li','lemma':'Li','meaning':'李（姓）','note':'人物姓名','paragraph_id':'p1','occurrences':1}],
                             'vocabulary':[{'word':'knots','meaning':'结','paragraph_id':'p1','quote':'He likes Chinese knots!',
                                            'context':'这里指中国结','question_ids':['1'],'teaching_prompt':'What does he like?',
                                            'transfer':'She likes Chinese knots too.'}],
                             'questions':[question('1'),question('2')]}]}

    def validate(self,translations):
        return build.validate(copy.deepcopy(self.exam(translations)))

    def test_aligned_translations_pass(self):
        report=self.validate(['李先生 14 岁。','他喜欢中国结！','你呢？'])
        self.assertEqual(report['status'],'structural_checks_passed')
        self.assertEqual(report['warnings'],[])

    def test_count_mismatch_blocks_with_the_real_sentence_count(self):
        with self.assertRaises(ValueError) as caught:self.validate(['只有一句译文'])
        text=str(caught.exception)
        self.assertIn('逐句译文有 1 条',text)
        self.assertIn('3 句',text)

    def test_english_translation_is_rejected(self):
        """抄英文原句（或换个说法但仍是英文）都不是译文：必须有中文。"""
        for fake in ('Mr. Li is 14 years old.','Li is fourteen.'):
            with self.assertRaises(ValueError) as caught:
                self.validate([fake,'他喜欢中国结！','你呢？'])
            self.assertIn('没有中文',str(caught.exception))
            self.assertIn('不能把英文原句抄一遍',str(caught.exception))

    def test_untranslated_sentences_are_allowed_but_never_hidden(self):
        report=self.validate(['李先生 14 岁。','','你呢？'])
        self.assertEqual(report['status'],'structural_checks_passed')
        self.assertTrue(any('有 1 句未翻译' in w and '[2]' in w for w in report['warnings']),report['warnings'])

    def test_empty_array_is_rejected(self):
        with self.assertRaises(ValueError) as caught:self.validate([])
        self.assertIn('非空数组',str(caught.exception))

    def test_untranslated_sentences_reach_pending_items(self):
        """未译句子必须出现在构建报告的待核项里（qa-report 会照单生成待填条目）。"""
        exam=self.exam(['李先生 14 岁。','','你呢？'])
        source=self.base/'exam.json';source.write_text(json.dumps(exam,ensure_ascii=False),encoding='utf-8')
        ledger={'sources':[{'role':'original_demo','path':source.name,
                            'sha256':__import__('hashlib').sha256(source.read_bytes()).hexdigest()}],
                'sections':exam['sections']}
        (self.base/'source-ledger.json').write_text(json.dumps(ledger,ensure_ascii=False),encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):build.build(source,self.base/'out',self.base/'source-ledger.json',profile='quick')
        report=json.loads((self.base/'out'/'build-report.json').read_text(encoding='utf-8'))
        self.assertTrue(any('未翻译' in item for item in report['pending_items']),report['pending_items'])

    def test_paragraphs_without_the_field_are_untouched(self):
        report=self.validate(None)
        self.assertEqual(report['status'],'structural_checks_passed')
        self.assertEqual(report['warnings'],[])

if __name__=='__main__':unittest.main()
