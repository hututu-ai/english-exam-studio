"""文档里"照抄就能用"的示例与字段表，必须真的能用。

真发生过两轮：
- 1.0.74：`references/schema.md` 的规范示例缺 `structure.quote`、`quick_words`、`writing_bank`，
  构建对这三项都是硬要求——助手按权威文档抄一遍要连撞三轮。
- 1.0.75：`references/teacher-options.md` 列的 culture_background 字段少了 `reading_connection`
  与 `sources[].supports`，而 `culture.validate_culture` 两项都要——又一轮白改。

这里的做法是"按文档写的字段拼一份数据，真的交给校验器"：文档漏写哪个必填字段，
校验器就会拦，测试即失败。文档样例不再是陷阱。
"""
import contextlib
import copy
import hashlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build

SCHEMA=ROOT/'references'/'schema.md'
JSON_BLOCK=re.compile(r'```json\n(.*?)\n```',re.S)

def documented_examples():
    return JSON_BLOCK.findall(SCHEMA.read_text(encoding='utf-8'))

class SchemaExampleBuilds(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 文档示例 ')
        self.root=Path(self.temp.name)

    def tearDown(self):self.temp.cleanup()

    def ledger_for(self,exam):
        """按示例自己写一份台账：示例只有 A 节两题，台账照抄它的原文与答案。"""
        section=exam['sections'][0]
        paper=self.root/'原卷.txt'
        paper.write_text('\n'.join(p['text'] for p in section['paragraphs']),encoding='utf-8')
        questions=[]
        for question in section['questions']:
            questions.append({'id':question['id'],'stem':question['stem'],'options':question['options'],
                              'answer':question['answer'],'answer_status':question.get('answer_status','sample')})
        ledger={'sources':[{'role':'original_demo','path':paper.name,
                            'sha256':hashlib.sha256(paper.read_bytes()).hexdigest()}],
                'sections':[{'id':section['id'],'kind':section['kind'],
                             'paragraphs':[{'id':p['id'],'text':p['text']} for p in section['paragraphs']],
                             'questions':questions}]}
        path=self.root/'source-ledger.json'
        path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf-8')
        return path

    def test_the_main_schema_example_builds_as_written(self):
        blocks=documented_examples()
        self.assertTrue(blocks,'references/schema.md 里应当有一份可照抄的 JSON 示例')
        exam=json.loads(blocks[0])
        source=self.root/'exam.json'
        source.write_text(json.dumps(exam,ensure_ascii=False,indent=2),encoding='utf-8')
        out=self.root/'out'
        with contextlib.redirect_stdout(io.StringIO()):
            build.build(source,out,self.ledger_for(exam))          # 失败会抛 ValueError，测试即失败
        report=json.loads((out/'build-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'],'structural_checks_passed')
        self.assertEqual(report['feature_coverage']['status'],'passed',
                         '文档示例必须满足它自己声明的 full 档要求，否则照抄的助手会反复撞墙')
        self.assertTrue((out/'index.html').is_file())

    def test_second_example_is_a_fragment_not_a_full_document(self):
        """文档里第二段 JSON 是七选五的单组片段，不该被当成整份 exam.json。"""
        blocks=documented_examples()
        if len(blocks)<2:return
        fragment=json.loads(blocks[1])
        self.assertNotIn('sections',fragment,'第二段是片段示例；若改成整份文档，请把它也接进构建测试')

class DocumentedFieldListsAreEnough(unittest.TestCase):
    """字段表也要"照抄能用"：只按文档列出的字段拼数据，校验器必须放行。"""

    def setUp(self):
        self.teacher_options=(ROOT/'references'/'teacher-options.md').read_text(encoding='utf-8')

    def culture_paragraph(self):
        for paragraph in self.teacher_options.split('\n\n'):
            if 'culture_background' in paragraph and '为数组' in paragraph:return paragraph
        self.fail('references/teacher-options.md 里应当有一段说明 culture_background 字段的说明')

    def test_culture_fields_listed_in_the_doc_are_enough_for_the_validator(self):
        """1.0.75 的实战：文档只列了 title/paragraph_id/quote/explanation/teaching_note/sources，
        少了 reading_connection 与 sources[].supports，照着写就会被 culture 校验拦下。"""
        import culture
        paragraph=self.culture_paragraph()
        item={'title':'博物馆开放时间','paragraph_id':'A-p1','quote':'The museum opens at nine.',
              'explanation':'英国多数博物馆上午十点前后开门。','teaching_note':'讲时间表达时顺带提一句。'}
        if 'reading_connection' in paragraph:
            item['reading_connection']='这段背景解释了原文为什么用一般现在时交代固定开放时间。'
        source={'title':'某馆官网','url':'https://example.org/hours'}
        if 'supports' in paragraph:source['supports']='支持"多数博物馆上午开门"这一背景事实。'
        item['sources']=[source]
        section={'paragraphs':[{'id':'A-p1','text':'The museum opens at nine.'}],'culture_background':[item]}
        try:
            culture.validate_culture(section)
        except AssertionError as error:
            self.fail(f'按文档列的字段写会被拦下，说明字段表不全：{error}')

    def test_documented_plan_example_passes_plan_check(self):
        """文档里的 generation-plan.json 示例要能直接被 plan.py check 接受。"""
        import plan
        block=re.search(r'```json\n(.*?)\n```',self.teacher_options,re.S)
        self.assertIsNotNone(block,'teacher-options.md 应当给出一份计划示例')
        with tempfile.TemporaryDirectory(prefix='英语 skill 计划示例 ') as temp:
            path=Path(temp)/'generation-plan.json'
            path.write_text(block.group(1),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                report=plan.check(str(path))
        self.assertEqual(report['status'],'ok',f'文档里的计划示例被 plan.py 拒绝：{report["problems"]}')

    def test_culture_field_list_matches_the_validator_source(self):
        """哪些栏是必填，不靠读源码正则猜，而是"删一栏看校验器拦不拦"——校验器加了必填项，这里就会红。"""
        import culture

        def complete_item():
            return {'title':'博物馆开放时间','paragraph_id':'A-p1','quote':'The museum opens at nine.',
                    'explanation':'英国多数博物馆上午十点前后开门。',
                    'reading_connection':'这段背景解释了原文为什么用一般现在时交代固定开放时间。',
                    'teaching_note':'讲时间表达时顺带提一句。',
                    'sources':[{'title':'某馆官网','url':'https://example.org/hours',
                                'supports':'支持"多数博物馆上午开门"这一背景事实。'}]}

        def accepted(item):
            section={'paragraphs':[{'id':'A-p1','text':'The museum opens at nine.'}],'culture_background':[item]}
            try:
                culture.validate_culture(section);return True
            except AssertionError:return False

        self.assertTrue(accepted(complete_item()),'完整条目本身要能通过，否则下面"谁必填"的推导没有意义')
        required=[]
        for key in ('title','paragraph_id','quote','explanation','reading_connection','teaching_note','sources'):
            item=complete_item();item.pop(key,None)
            if not accepted(item):required.append(key)
        without_supports=complete_item();without_supports['sources']=[{'title':'某馆官网','url':'https://example.org/hours'}]
        if not accepted(without_supports):required.append('supports')
        self.assertTrue(required,'校验器应当至少要求 title 与 quote 之类的栏目')
        paragraph=self.culture_paragraph()
        missing=sorted(key for key in required if key not in paragraph)
        self.assertEqual(missing,[],f'culture-field-list-missing: {missing} 在校验器里是必填，但文档字段表没写')

class SchemaChecklistIsComplete(unittest.TestCase):
    """`schema.md` 顶部那张"要写哪些字段"的表，必须覆盖构建真正强制要求的字段。

    要求不是人抄的，而是**逐字段删掉看构建拦不拦**推出来的：校验器将来加了必填字段、
    而顶部表没跟上，这个测试就会红——照抄顶部表的助手不会因为漏字段反复重建。
    """

    def setUp(self):
        self.exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
        text=(ROOT/'references'/'schema.md').read_text(encoding='utf-8')
        start=text.find('## 先看这里')
        self.assertNotEqual(start,-1,'schema.md 顶部必须有「先看这里：按本次选择决定要写哪些字段」')
        self.checklist=text[start:text.find('```json',start)]

    def test_section_level_requirements_are_listed(self):
        import build
        d=json.loads(json.dumps(self.exam,ensure_ascii=False))
        # 打开演示卷真正具备的那些功能（它没有文化背景卡，开了会额外要求 culture_background）
        d['features']={k:True for k in ('annotations','dictionary','classroom_tools','quick_answers','writing_transfer','deep_reading')}
        d['features']['culture_background']=False
        report,problems=build.feature_report(d,'full')
        self.assertEqual(problems,[],f'完整示例不该有缺项：{problems[:2]}')
        required=set(report['sections'][0]['required_content'])
        self.assertTrue(required,'夹具要能算出必填栏目，否则这个测试没有意义')
        missing=sorted(key for key in required if key not in self.checklist)
        self.assertEqual(missing,[],f'schema.md 顶部清单没写这些必填栏目：{missing}')

    def test_question_level_requirements_are_listed(self):
        """每个必填的题目字段都靠"删掉它、看构建是否报错"来确认，再从顶部清单里找有没有写。"""
        import build
        for key in ('question_type','type_note','solve_steps','pitfall','analysis','evidence','answer_status','answer_source','strategy'):
            d=json.loads(json.dumps(self.exam,ensure_ascii=False))
            d['sections'][0]['questions'][0].pop(key,None)
            _,structural=build.section_report(d)
            _,feature=build.feature_report(d,'full')
            problems=structural+feature
            self.assertTrue(any(key in str(item) for item in problems),
                            f'夹具里的第 1 题删掉 {key} 后构建居然不报错，这个测试的前提不成立')
            self.assertIn(key,self.checklist,f'第 1 题明明必须写 {key}，schema.md 顶部清单却没提')

if __name__=='__main__':unittest.main()
