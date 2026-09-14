"""结构由试卷决定：题型名、板块顺序、板块名称、每节要讲什么，都跟着老师给的试卷走。

1.0.46 之前 build.py 把 kind 限死在六种预设里，模板按固定题型顺序重排章节、并用写死的中文
覆盖试卷自己的板块名。后果：读后续写/任务型阅读/词汇运用只能硬塞进"写作/阅读/语法填空"，
一份"完形→阅读"顺序的卷子会被显示成"阅读→完形"。

这里验收新规则：
  * kind 是试卷自己的题型名，kind_preset 只决定呈现方式（缺省按内容推断）；
  * group/group_title/short 决定导航分组、顺序与名称，顺序 = 试卷顺序；
  * 每节要求哪些栏目由"这节实际有什么材料 + 老师选了什么功能"决定，不由题型名决定；
  * 真浏览器里核对导航分组、顺序、名称与工具呈现。
"""
import contextlib
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'tests'))
import build, scope, quality_gate, section_kinds
import make_paper_structure_fixture

def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

class PaperStructure(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 试卷结构 ')
        self.base=Path(self.temp.name)
        self.source=self.base/'paper'
        self.out=self.base/'out'
        self.document=make_paper_structure_fixture.make(self.source,self.out)
    def tearDown(self):self.temp.cleanup()

    def report(self):return json.loads((self.out/'build-report.json').read_text(encoding='utf-8'))

    def test_paper_kinds_names_and_order_survive_the_build(self):
        report=self.report()
        coverage=report['feature_coverage']['sections']
        self.assertEqual([item['kind'] for item in coverage],
                         ['听说应用','语法选择','完形填空','阅读理解','配对阅读','短文填空'],
                         '构建报告必须保留试卷自己的题型名（含初中的短文填空），且顺序就是试卷顺序')
        self.assertEqual([item['kind_preset'] for item in coverage],
                         ['listening','cloze','cloze','reading','seven','grammar'])
        self.assertEqual(report['status'],'structural_checks_passed')
        self.assertEqual(report['template_verification']['status'],'passed')

    def test_navigation_groups_come_from_the_paper_not_from_a_fixed_order(self):
        exam=json.loads((self.out/'exam.json').read_text(encoding='utf-8'))
        groups=section_kinds.groups(exam['sections'])
        self.assertEqual([g['title'] for g in groups],
                         ['一、听说应用','二、语法选择','三、完形填空','四、阅读理解','五、配对阅读','六、短文填空'])
        self.assertEqual([len(g['sections']) for g in groups],[1,1,1,1,1,1])
        # 直接锁死用户提出的那件事：不能出现预设名，也不能出现原卷没有的板块
        titles=[g['title'] for g in groups]
        for preset_label in ('听力','阅读','七选五','完形','语法填空','写作'):
            self.assertNotIn(preset_label,titles,f'导航里出现了预设题型名「{preset_label}」，说明还在按模板套结构')
        self.assertEqual(sorted(titles),sorted(['一、听说应用','二、语法选择','三、完形填空','四、阅读理解','五、配对阅读','六、短文填空']),
                         '导航板块必须与试卷完全一致，不能多也不能少')

    def test_question_numbers_must_follow_the_paper_order(self):
        """板块顺序改了、题号没跟着改，构建必须拦下：这是"顺序由试卷决定"的另一半。"""
        exam=json.loads((self.source/'exam.json').read_text(encoding='utf-8'))
        exam['sections']=list(reversed(exam['sections']))
        write(self.source/'exam.json',exam)
        gate=quality_gate.audit_exam(exam,self.source,str(self.source/'source-ledger.json'))
        self.assertIn('question_order',[error['code'] for error in gate['errors']])

    def test_declared_preset_beats_leftover_content(self):
        """宣告了题型就以宣告为准：一节阅读里残留写作字段，不能把它渲染成写作节。"""
        reading={'kind':'阅读理解','kind_preset':'reading','writing_steps':{'task':'x'},'teacher_model':'y',
                 'paragraphs':[{'id':'p1','text':'A'}],'questions':[{'id':'1','stem':'s'}]}
        self.assertEqual(section_kinds.preset(reading),'reading')
        self.assertFalse(section_kinds.is_writing(reading))
        self.assertFalse(section_kinds.is_listening(reading))
        # 没有宣告时才按内容推断
        self.assertTrue(section_kinds.is_writing({'kind':'读写综合','teacher_model':'model'}))
        self.assertTrue(section_kinds.is_grammar({'kind':'综合题','questions':[{'knowledge':{'title':'t'}}]}))
        self.assertTrue(section_kinds.is_listening({'kind':'综合题','blanks':[{'start':0,'end':2}]}))
        self.assertFalse(section_kinds.is_listening({'kind':'综合题','blanks':[]}))

    def test_js_and_python_agree_on_preset_priority(self):
        """三份实现必须同一条优先级：宣告 > 题型名/别名 > 内容推断。"""
        cases=[({'kind':'阅读理解','kind_preset':'reading','teacher_model':'y'},'reading'),
               ({'kind':'短文填空'},'grammar'),
               ({'kind':'x','blanks':[]},'custom'),
               ({'kind':'x','blanks':[{'start':0,'end':2}]},'listening'),
               ({'kind':'x','questions':[{'knowledge':{'title':'t'}}]},'grammar')]
        for section,expected in cases:
            self.assertEqual(section_kinds.preset(section),expected,section)

    def test_kind_preset_accepts_only_real_presets(self):
        exam=json.loads((self.source/'exam.json').read_text(encoding='utf-8'))
        exam['sections'][0]['kind_preset']='essay'
        with self.assertRaises(ValueError) as caught:build.validate(copy.deepcopy(exam))
        self.assertIn('kind_preset',str(caught.exception))
        # 不写 kind_preset 也必须能构建：题型名自己就能命中预设（听说应用→listening）
        exam['sections'][0].pop('kind_preset')
        self.assertEqual(build.validate(copy.deepcopy(exam))['status'],'structural_checks_passed')
        # 但把听力节改名成"阅读理解"却留着逐题音频，构建必须拦下：呈现方式不能被残留数据含糊过去
        renamed=copy.deepcopy(exam);renamed['sections'][0]['kind']='reading'
        with self.assertRaises(ValueError) as caught:build.validate(renamed)
        self.assertIn('逐题音频只能出现在听力章节',str(caught.exception))

    def test_scope_finds_sections_by_paper_name_preset_and_group(self):
        exam=json.loads((self.source/'exam.json').read_text(encoding='utf-8'))
        for token,expected in [('短文填空',['F1']),('grammar',['F1']),('四、阅读理解',['R1']),('R1',['R1']),
                               ('配对阅读',['M1']),('seven',['M1']),('任务型阅读',['R1'])]:
            self.assertEqual([s['id'] for s in scope.select(copy.deepcopy(exam),token)['sections']],expected,token)
        intensive=scope.select(copy.deepcopy(exam),'听说应用','intensive')
        self.assertEqual([s['id'] for s in intensive['sections']],['L1'],
                         '精听模式要认得出"听说应用"这种试卷自己的听力题型名')
        self.assertIn('full_audio',intensive)

    def test_requirements_follow_the_material_not_the_kind_name(self):
        exam=json.loads((self.source/'exam.json').read_text(encoding='utf-8'))
        by_id={s['id']:s for s in exam['sections']}
        # 听力章节若没有转写原文，就不该要求生词表（以前按 kind 一律要求）
        listening=copy.deepcopy(by_id['L1']);listening['paragraphs']=[]
        report=build.validate_features({'features':{},'sections':[listening]},profile='full')
        self.assertEqual(report['sections'][0]['required_content'],['blanks'])
        # 有两段原文的自定义题型必须有句子精讲；单段则不需要
        two=copy.deepcopy(by_id['R1'])
        self.assertIn('sentences',build.validate_features({'features':{},'sections':[two]},profile='full')['sections'][0]['required_content'])
        one=copy.deepcopy(by_id['R1']);one['paragraphs']=one['paragraphs'][:1]
        self.assertNotIn('sentences',build.validate_features({'features':{},'sections':[one]},profile='full')['sections'][0]['required_content'])
        # 声明为写作预设的章节必须交范文与写作步骤
        writing=copy.deepcopy(by_id['R1']);writing.update(kind='读写综合',kind_preset='writing');writing.pop('teacher_model',None)
        with self.assertRaises(ValueError) as caught:
            build.validate_features({'features':{},'sections':[writing]},profile='full')
        self.assertIn('teacher_model',str(caught.exception),'声明为 writing 预设就必须交范文，不能靠题型名混过去')

class PaperStructureBrowser(unittest.TestCase):
    def chrome_binary(self):
        candidates=[os.environ.get('CHROME_BIN'),'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',shutil.which('google-chrome'),
                    shutil.which('chromium'),shutil.which('microsoft-edge')]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():return candidate
        return None

    def test_real_browser_shows_the_paper_order_names_and_tools(self):
        node=shutil.which('node')
        if not node:self.skipTest('node 不可用')
        module=os.environ.get('PLAYWRIGHT_MODULE','playwright')
        probe=subprocess.run([node,'-e',f"try{{require({module!r})}}catch(e){{process.exit(3)}}"],capture_output=True,timeout=60)
        if probe.returncode!=0:self.skipTest('Playwright 不可用，跳过真实浏览器验收')
        chrome=self.chrome_binary()
        if not chrome:self.skipTest('没有可用的 Chrome/Edge，跳过真实浏览器验收')
        temp=tempfile.TemporaryDirectory(prefix='英语 skill 试卷结构浏览器 ')
        base=Path(temp.name)
        out=base/'out'
        make_paper_structure_fixture.make(base/'paper',out)
        environment={**os.environ,'CHROME_BIN':chrome,'BROWSER_ENGINE':'chromium'}
        result=subprocess.run([node,str(ROOT/'scripts/browser_check.cjs'),str(out)],capture_output=True,
                              text=True,encoding='utf-8',errors='replace',timeout=300,env=environment)
        evidence=json.loads((out/'browser-check.json').read_text(encoding='utf-8'))
        self.assertEqual(evidence['status'],'passed',result.stdout[-1500:]+result.stderr[-500:])
        names=[item['name'] for item in evidence['checks']]
        self.assertIn('chapter-bar-follows-paper-structure',names,
                      '导航必须按试卷的分组、顺序、名称渲染')
        self.assertIn('custom-kinds-get-tools-from-content',names,
                      '预设之外的题型名必须按本节内容得到正确的工具')
        self.assertEqual([item['name'] for item in evidence['skipped']],[])
        temp.cleanup()

if __name__=='__main__':unittest.main()
