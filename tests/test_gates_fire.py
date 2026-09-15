"""每条闸门都要证明"它真的会拦"，而不是"合法输入能过"。

这一轮里我自己踩过两次假检查：占位符断言因为条目正文里本来就有"非占位"三个字而永真；
检查器把同行另一个脚本的参数算错。所以这里把每条闸门写成数据：注入**具体缺陷**，
断言它报错、并且报错文字里带上实际值（哪个词、哪一段、第几题）。

另有一条覆盖率守卫：`scripts/grounding.py` 与 `scripts/culture.py` 里每个 `validate_*`
都必须在这里有反向用例（或在 EXEMPT 里写明理由）——加了新校验却忘了证明它会拦，就失败。
"""
import contextlib
import copy
import io
import json
import os
import shutil
import stat
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'tests'))   # 复用仓库自带的听力夹具（含真实 wav）
import build, grounding, culture
from preferences import DEFAULTS

BASE=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))

def section(exam):return exam['sections'][0]

def gate(fragment):
    """注入缺陷后跑结构校验，返回错误文字（必须在断言里带上实际值）。"""
    def run(mutate):
        exam=copy.deepcopy(BASE)
        mutate(exam)
        with unittest.TestCase().assertRaises((ValueError,AssertionError)) as caught:
            build.validate(exam)
        text=str(caught.exception)
        if fragment not in text:
            raise AssertionError(f'闸门报错文字里没有「{fragment}」：{text[:300]}')
        return text
    return run

def quick_word(mutate):
    def run():return gate('生词')(mutate)
    return run

# 名称 → (注入缺陷的函数, 期望出现在报错里的片段)
GATES={
 # ---- 反编造：生词 / 词汇 / 篇章结构 / 句子精讲 ----
 'grounding.validate_vocabulary#词形不在原文':(
   lambda exam: section(exam)['quick_words'][0].update(word='photosynthesis'),
   '没有出现在段落'),
 'grounding.validate_vocabulary#出现次数与原文不符':(
   lambda exam: section(exam)['quick_words'][0].update(occurrences=7),
   '实际出现 1 次'),
 'grounding.validate_vocabulary#语境义引文不在段落里':(
   lambda exam: section(exam)['vocabulary'][0].update(quote='这句话原文里没有'),
   '真实子串'),
 'grounding.validate_vocabulary#引文里没有该词形':(
   lambda exam: section(exam)['vocabulary'][0].update(word='notebook',quote='opened a repair corner in the library'),
   '没有出现词形'),
 'grounding.validate_vocabulary#缺少语境义说明':(
   lambda exam: section(exam)['vocabulary'][0].update(context=''),
   '需要 context'),
 'grounding.validate_structure#结构判断没有原文依据':(
   lambda exam: section(exam)['structure'][0].update(quote='编造的一句结构依据'),
   '不在所引用段落的原文中'),
 'grounding.validate_structure#结构分析没有段落':(
   lambda exam: section(exam)['structure'][0].update(paragraph_ids=[]),
   '至少一个真实 paragraph_ids'),
 'grounding.validate_sentences#句子精讲引文不是原文':(
   lambda exam: section(exam)['sentences'][0].update(quote='不是原文的句子'),
   'quote 必须是该段原文的真实子串'),
 'grounding.validate_sentences#句子精讲缺译文':(
   lambda exam: section(exam)['sentences'][0].update(translation=''),
   '缺少 translation'),
 'grounding.validate_teaching_substance#两题解析完全一样':(
   lambda exam: section(exam)['questions'][1].update(analysis=section(exam)['questions'][0]['analysis']),
   '完全相同'),
 'grounding.validate_teaching_substance#解析里还有占位文字':(
   lambda exam: section(exam)['questions'][0].update(analysis='待补充'),
   '占位'),
 'grounding.validate_blank_tokens#挖空落在半个词上':(
   lambda exam: section(exam).update(blanks=[{'paragraph_id':'A-p1','start':1,'end':4,'purpose':'测试','question_ids':['21']}]),
   '词首'),
 # ---- 答案与证据 ----
 'build.validate_section#证据引文不在原文':(
   lambda exam: section(exam)['questions'][0].update(evidence=[{'paragraph_id':'A-p2','quote':'编造的证据句'}]),
   '不是真实子串'),
 'build.validate_section#答案不在选项里':(
   lambda exam: section(exam)['questions'][0].update(answer='Z'),
   '不在选项'),
 'build.validate_section#官方答案没有出处':(
   lambda exam: section(exam)['questions'][0].update(answer_source=''),
   'answer_source'),
 # ---- 结构由试卷决定 / 分值 ----
 'build.validate_section#kind_preset 不是六种之一':(
   lambda exam: section(exam).update(kind_preset='essay'),
   'kind_preset'),
 'build.validate_section#每小题分值大于总分':(
   lambda exam: section(exam).update(score_per_question=99,score_total=30),
   '大于本大题总分'),
 # ---- 逐句译文对齐 ----
 'build.validate_section#逐句译文与分句对不上':(
   lambda exam: section(exam)['paragraphs'][0].update(sentence_translations=['只有一条']),
   '按句切分原文是'),
 'build.validate_section#逐句译文抄英文充数':(
   lambda exam: section(exam)['paragraphs'][0].update(sentence_translations=fake_translations(exam)),
   '没有中文'),
 # ---- 文化背景：必须有可核对来源、引文必须出自本篇 ----
 'culture.validate_culture#背景没有可核对来源':(
   lambda exam: section(exam).update(culture_background=[{'title':'背景','paragraph_id':'A-p1',
     'quote':'opened a repair corner in the library','explanation':'说明','reading_connection':'与本篇的关系',
     'teaching_note':'课堂怎么用'}]),
   '来源'),
 'culture.validate_culture#背景引文是编造的':(
   lambda exam: section(exam).update(culture_background=[{'title':'背景','paragraph_id':'A-p1',
     'quote':'编造的背景引文','explanation':'说明','reading_connection':'与本篇的关系','teaching_note':'课堂怎么用',
     'sources':[{'title':'来源','url':'https://example.org','supports':'支撑哪一句'}]}]),
   '编造的背景引文'),
 # ---- 图片占位选项（图A/图B 不能冒充真实选项）----
 'build.validate_section#图片占位选项没有 option_images':(
  lambda exam:section(exam)['questions'][0].update(options={'A':'图A','B':'图B','C':'图C'}),
  '待核'),
 # ---- 图片选项 ----
 'build.validate_section#选项图片字母不在选项里':(
   lambda exam: section(exam)['questions'][0].update(options={k:'' for k in 'ABCD'},option_images={'A':'a.png','E':'e.png'}),
   '没有对应选项的字母'),
}

def fake_translations(exam):
    """按真实分句数生成逐句译文，第一条直接抄原文——用来验证"抄英文充数会被拒"。"""
    from sentence_split import split_sentences
    paragraph=section(exam)['paragraphs'][0]
    parts=split_sentences(paragraph['text'])
    return [parts[0]]+['第 %d 句译文' % (index+1) for index in range(1,len(parts))]

class GatesFire(unittest.TestCase):
    def test_every_gate_reports_the_real_problem(self):
        failures=[]
        for name,(mutate,fragment) in GATES.items():
            exam=copy.deepcopy(BASE);mutate(exam)
            try:
                with self.assertRaises((ValueError,AssertionError)) as caught:build.validate(exam)
            except AssertionError as error:
                failures.append(f'{name}：注入缺陷后竟然通过了（{error}）');continue
            text=str(caught.exception)
            if fragment not in text:failures.append(f'{name}：报错文字里没有「{fragment}」→ {text[:160]}')
        self.assertEqual(failures,[],'闸门必须拦住并说清问题：\n'+'\n'.join(failures))

    def test_gate_names_are_unique_and_labelled(self):
        self.assertEqual(len(GATES),len(set(GATES)),'闸门名必须唯一')
        for name in GATES:self.assertRegex(name,r'^(grounding|culture|build)\.',name)

    def test_coverage_guard_every_validator_has_a_negative_case(self):
        """新增一个 validate_* 却忘了证明它会拦 → 这里失败。"""
        EXEMPT={}
        covered={name.split('#')[0] for name in GATES}
        declared=[]
        for module in (grounding,culture):
            for attribute in dir(module):
                if attribute.startswith('validate_'):
                    declared.append(f'{module.__name__}.{attribute}')
        missing=[name for name in declared if name not in covered and name not in EXEMPT]
        self.assertEqual(missing,[],f'这些校验函数没有反向用例：{missing}（新增校验必须配一条"它会拦"的测试）')

    def test_valid_demo_exam_still_passes(self):
        """反向用例的另一半：没有缺陷时必须通过，否则上面的"拦住了"毫无意义。"""
        self.assertEqual(build.validate(copy.deepcopy(BASE))['status'],'structural_checks_passed')

class FeatureGatesFire(unittest.TestCase):
    """功能档位相关的闸门（validate_features / culture）也要证明会拦。"""

    def test_full_profile_asks_for_missing_content(self):
        exam=copy.deepcopy(BASE)
        for key in ('sentences','structure','writing_bank'):section(exam).pop(key,None)
        with self.assertRaises(ValueError) as caught:
            build.validate_features({**exam,'features':dict(DEFAULTS)},profile='full')
        self.assertIn('句子精讲',str(caught.exception))

    def test_audio_evidence_out_of_range_is_rejected(self):
        exam=copy.deepcopy(BASE)
        target=section(exam)
        target['kind']='听力理解';target['kind_preset']='listening'
        target['questions'][0]['evidence']=[{'paragraph_id':'A-p1','quote':'opened a repair corner in the library','start':2,'end':1}]
        with self.assertRaises((ValueError,AssertionError)) as caught:build.validate(exam)
        text=str(caught.exception)
        self.assertIn('音频证据区间无效',text)
        self.assertIn('start=2',text)


class NeverFiredStructuralAsserts(unittest.TestCase):
    """结构闸门里"从来没有被触发过"的断言（1.0.115）。

    用 `trace` 量过：`build.py` 的 66 条 `assert` 中，`test_gates_fire` 只执行到 45 条，
    剩下 21 条**从未被任何用例执行**——把它们的判据改松不会有测试报警。
    这里逐条注入缺陷（`grounding` 的 24 条与 `culture` 的 5 条在这套用例里已全部执行到）。

    注：`build()` 里那三条需要真实时长才能走到（ffprobe）、以及模板占位符那条需要篡改模板，
    不在本类范围（见 ROADMAP 待办与验证记录）。
    """
    def expect(self,mutate,fragment):
        exam=copy.deepcopy(BASE);mutate(exam)
        with self.assertRaises((ValueError,AssertionError)) as caught:build.validate(exam)
        text=str(caught.exception)
        if fragment not in text:
            raise AssertionError(f'闸门报错文字里没有「{fragment}」：{text[:300]}')
    def test_translation_identical_to_the_source_is_refused(self):
        def mutate(exam):
            paragraph=section(exam)['paragraphs'][0]
            paragraph['text']='请阅读下列短文。'
            paragraph['sentence_translations']=['请阅读下列短文。']
        self.expect(mutate,'译文与原文完全相同')
    def test_source_groups_must_cover_every_paragraph_in_order(self):
        def mutate(exam):
            s=section(exam);s['source_groups']=[{'paragraph_ids':[s['paragraphs'][1]['id']]}]
        self.expect(mutate,'source_groups 必须按原顺序覆盖全部段落')
    def test_empty_page_images_is_refused(self):
        def mutate(exam):
            section(exam)['origin']={'page_images':[],'exam_page':1,'page_image':'a.png'}
        self.expect(mutate,'origin.page_images 必须是非空路径数组')
    def test_origin_without_a_valid_exam_page_is_refused(self):
        def mutate(exam):
            section(exam)['origin']={'exam_page':0,'page_image':'a.png'}
        self.expect(mutate,'origin 需要 page_image 或 page_images')
    def test_origin_link_must_be_http_and_state_its_relation(self):
        def mutate(exam):
            section(exam)['origin']={'exam_page':1,'page_image':'a.png','links':[{'url':'ftp://x','relation':''}]}
        self.expect(mutate,'来源链接要以 http(s):// 开头')
    def test_transfer_task_quote_must_be_real(self):
        def mutate(exam):
            section(exam)['transfer_tasks']=[{'paragraph_id':'A-p1','source_quote':'原文里没有这句','prompt':'p','check':'c'}]
        self.expect(mutate,'transfer_tasks 需要位于段落')
    def test_model_analysis_quote_must_come_from_the_sample(self):
        def mutate(exam):
            s=section(exam);s['teacher_model']='Dear Tom, I am glad to hear from you.'
            s['writing_steps']={'model_analysis':[{'quote':'范文里没有这句','analysis':'说明'}]}
        self.expect(mutate,'写作分析引文必须逐字出自')
    def test_question_audio_outside_a_listening_section_is_refused(self):
        def mutate(exam):section(exam)['questions'][0]['audio']='q1.mp3'
        self.expect(mutate,'逐题音频只能出现在听力章节')
    def test_option_without_text_or_image_is_refused(self):
        """这条只在**提供了 option_images** 时才走到：图片选项里少一个字母、又有空文字选项，就是"既没字也没图"。"""
        def mutate(exam):
            q=section(exam)['questions'][0]
            q['options']['A']=''
            q['option_images']={'B':'assets/q1-b.png'}
        self.expect(mutate,'既没有文字也没有图片')
    def test_option_image_entry_without_a_path_is_refused(self):
        def mutate(exam):
            q=section(exam)['questions'][0];q['options']['A']='';q['option_images']={'A':''}
        self.expect(mutate,'没有图片路径')
    def test_logic_link_needs_a_known_colour_label_and_explanation(self):
        def mutate(exam):
            section(exam)['questions'][0]['logic_links']=[{'color':'pink','label':'x','explanation':'y','endpoints':[]}]
        self.expect(mutate,'线索需要 color')
    def test_logic_link_needs_two_endpoints_covering_both_sides(self):
        def mutate(exam):
            section(exam)['questions'][0]['logic_links']=[
                {'color':'amber','label':'x','explanation':'y','endpoints':[{'option':'A','quote':"Eight o'clock"}]}]
        self.expect(mutate,'每条线索至少 2 个端点')
    def test_endpoint_must_be_either_option_or_paragraph(self):
        def mutate(exam):
            s=section(exam);q=s['questions'][0]
            q['logic_links']=[{'color':'amber','label':'x','explanation':'y','endpoints':[
                {'option':'A','quote':q['options']['A']},
                {'option':'B','paragraph_id':'A-p1','quote':q['options']['B']}]}]
        self.expect(mutate,'端点必须二选一')
    def test_logic_link_quote_must_be_a_real_substring(self):
        def mutate(exam):
            s=section(exam);q=s['questions'][0]
            q['logic_links']=[{'color':'amber','label':'x','explanation':'y','endpoints':[
                {'option':'A','quote':'选项里没有这句话'},
                {'paragraph_id':'A-p1','quote':s['paragraphs'][0]['text'][:20]}]}]
        self.expect(mutate,'线索引文不是所引原文/选项的真实子串')
    def test_gap_number_must_exist_in_the_section(self):
        def mutate(exam):
            paragraph=section(exam)['paragraphs'][0]
            paragraph['text']=paragraph['text']+' {{99}}'
        self.expect(mutate,'空位题号 99 在本节题目中不存在')
    def test_media_may_not_point_at_a_url(self):
        """`build()` 里的资源检查：本地文件才行（联网素材要先下载）。"""
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);exam=copy.deepcopy(BASE)
            section(exam)['paragraphs'][0]['image']='https://example.com/a.png'
            source=base/'exam.json';source.write_text(json.dumps(exam,ensure_ascii=False),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises((ValueError,AssertionError)) as caught:
                    build.build(source,base/'out',ROOT/'examples/source-ledger.json')
            self.assertIn('资源只能引用本地文件',str(caught.exception))
    def test_missing_media_file_is_reported_with_its_path(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);exam=copy.deepcopy(BASE)
            section(exam)['paragraphs'][0]['image']='这个文件不存在.png'
            source=base/'exam.json';source.write_text(json.dumps(exam,ensure_ascii=False),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises((ValueError,AssertionError)) as caught:
                    build.build(source,base/'out',ROOT/'examples/source-ledger.json')
            self.assertIn('找不到资源文件',str(caught.exception))

    # —— 需要真实构建才能走到的三条：用桩 ffprobe 给出时长 ——
    def fake_probe(self,duration):
        """给 build.subprocess.run 打桩，模拟 ffprobe 报时长（跨平台，不依赖可执行文件）。"""
        class Result:
            returncode=0;stderr=''
            def __init__(self,stdout):self.stdout=stdout
        def run(argv,**kwargs):
            if any('format=duration' in str(a) for a in argv):return Result(f'{float(duration)}\n')
            raise AssertionError('测试桩只预期 ffprobe 的时长查询：'+repr(argv))
        return run
    def listening_build_error(self,mutate,duration=8.0):
        """用仓库自带的听力夹具（含真实 wav）构建一次，注入缺陷后取报错文字。"""
        import make_browser_fixture as fixture
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            document=fixture.paper_document(base)
            mutate(document)
            source,ledger=fixture.write_paper(base,document)
            with patch.object(build.subprocess,'run',side_effect=self.fake_probe(duration)),\
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises((ValueError,AssertionError)) as caught:
                    build.build(source,base/'out',ledger)
            return str(caught.exception)
    def test_audio_evidence_end_beyond_the_clip_length_is_refused(self):
        def mutate(document):
            s=next(s for s in document['sections'] if s['kind']=='listening')
            s['questions'][0]['evidence']=[{'paragraph_id':s['paragraphs'][0]['id'],'quote':s['paragraphs'][0]['text'][:12],
                                            'start':0,'end':999}]
        self.assertIn('超出本节音频时长',self.listening_build_error(mutate))
    def test_question_audio_context_out_of_range_is_refused(self):
        def mutate(document):
            s=next(s for s in document['sections'] if s['kind']=='listening')
            s['questions'][0]['audio_context']={'start':-1,'end':2,'selection_reason':'控件测试'}
        self.assertIn('audio_context 无效',self.listening_build_error(mutate))
    def test_question_clip_duration_must_match_its_context(self):
        def mutate(document):
            s=next(s for s in document['sections'] if s['kind']=='listening')
            s['questions'][0]['audio_context']={'start':0,'end':2,'selection_reason':'控件测试'}
        self.assertIn('相差超过 0.25 秒',self.listening_build_error(mutate))
    def test_template_must_contain_exactly_one_data_placeholder(self):
        """模板被手工改坏（占位符多了/少了）必须在构建时拦下，而不是产出一个白页。"""
        import make_browser_fixture as fixture
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);document=fixture.paper_document(base)
            source,ledger=fixture.write_paper(base,document)
            fake_root=base/'fake-skill';(fake_root/'scripts').mkdir(parents=True)
            # 整份 assets 复制过去：构建还要读 template-manifest.json 等，只放一个模板会先撞"找不到清单"
            shutil.copytree(ROOT/'assets',fake_root/'assets')
            template=(ROOT/'assets'/'lesson.html').read_text(encoding='utf-8')
            (fake_root/'assets'/'lesson.html').write_text(template.replace('__EXAM_DATA__','__EXAM_DATA__ __EXAM_DATA__',1),encoding='utf-8')
            with patch.object(build,'__file__',str(fake_root/'scripts'/'build.py')),\
                 patch.object(build.subprocess,'run',side_effect=self.fake_probe(8.0)),\
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises((ValueError,AssertionError)) as caught:
                    build.build(source,base/'out',ledger)
            self.assertIn('模板里的 __EXAM_DATA__ 占位符必须正好 1 个',str(caught.exception))


if __name__=='__main__':unittest.main()
