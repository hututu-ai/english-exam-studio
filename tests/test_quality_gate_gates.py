"""交付闸门（`quality_gate`）的判据逐条反向验证（1.0.114）。

起因是一条机械检查：`quality_gate` 有 44 个判据码，其中 **28 个从未在任何测试里出现过**——
也就是说把"台账缺失""章节顺序与原件不一致""原文被改过""范文混进原卷区域""听力音频根本没接"
这类**会阻断构建**的判据改松，不会有任何测试报警。交付闸门是最后一道门，这里逐条注入缺陷。

做法：先建一个**完全干净**的基线（台账 + 原件文件 + exam.json 三者一致，无错误无提示），
再针对每个判据注入一处缺陷，断言该判据码出现（阻断级还要断言 `status=blocked`）。
需要真实的 `ffprobe` 才能走到的那几条，用 `FFPROBE_BIN` 指向一个桩脚本（`platform_tools.find_tool`
会优先用它），这样不需要装 ffmpeg。
"""
import contextlib
import hashlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'tests'))   # 跨平台 ffprobe 桩
import quality_gate

TEXT='The museum opens at nine in the morning.'
STEM='When does the museum open?'
OPTIONS={'A':"Eight o'clock",'B':"Nine o'clock"}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class GateFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 交付闸门判据 ')
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        (self.base/'paper.pdf').write_bytes(b'%PDF-1.4 paper')
        (self.base/'answers.pdf').write_bytes(b'%PDF-1.4 answers')
    def ledger(self,sections=None,sources=None,path=None):
        data={'sources':sources if sources is not None else
                  [{'role':'paper','path':'paper.pdf','sha256':sha(self.base/'paper.pdf')},
                   {'role':'answers','path':'answers.pdf','sha256':sha(self.base/'answers.pdf')}],
              'sections':sections if sections is not None else [self.reading_section()]}
        target=Path(path) if path else self.base/'source-ledger.json'
        target.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        return target
    def reading_section(self,text=TEXT,question=None,extra=None):
        q={'id':'21','stem':STEM,'options':dict(OPTIONS),'answer':'B',
           'answer_status':'official','answer_reference':'answers.pdf 第1页'}
        q.update(question or {})
        section={'id':'A','kind':'reading','paragraphs':[{'id':'A-p1','text':text}],'questions':[q]}
        section.update(extra or {})
        return section
    def exam(self,section=None,sections=None,extra=None):
        document={'title':'t','sections':sections if sections is not None else [section or self.reading_section()]}
        document.update(extra or {})
        return document
    def codes(self,report,where='errors'):return [row['code'] for row in report[where]]
    def audit(self,exam=None,ledger_path='__default__',**kwargs):
        path=self.ledger(sections=[self.reading_section()]) if ledger_path=='__default__' else ledger_path
        return quality_gate.audit_exam(exam if exam is not None else self.exam(),self.base,path,**kwargs)
    def assert_blocks(self,report,code):
        self.assertIn(code,self.codes(report),report['errors'])
        self.assertEqual(report['status'],'blocked')
    def assert_warns(self,report,code):
        self.assertIn(code,self.codes(report,'warnings'),report['warnings'])
        self.assertEqual(report['status'],'automated_checks_passed','提示级判据不应该阻断')


class QualityGateCriteria(GateFixture):
    def test_clean_baseline_has_no_errors_and_no_warnings(self):
        """基线必须完全干净，否则注入用例分不清"是注入导致的"还是本来就报。"""
        report=self.audit()
        self.assertEqual(report['errors'],[],report['errors'])
        self.assertEqual(report['warnings'],[],report['warnings'])
        self.assertEqual(report['status'],'automated_checks_passed')

    # —— 台账与原件 ——
    def test_source_ledger_missing_blocks(self):
        self.assert_blocks(self.audit(ledger_path=self.base/'不存在.json'),'source_ledger_missing')
    def test_empty_source_list_blocks(self):
        self.assert_blocks(self.audit(ledger_path=self.ledger(sources=[])),'source_files_missing')
    def test_pages_source_without_image_kind_blocks(self):
        (self.base/'p1.png').write_bytes(b'\x89PNG fake')
        source={'role':'paper','path':'scan.pdf','sha256':'x'*64,'pages':[
            {'path':'p1.png','index':1,'sha256':sha(self.base/'p1.png')}]}
        report=self.audit(ledger_path=self.ledger(sources=[source]))
        self.assertIn('source_pages_kind',self.codes(report))
    def test_scope_outside_the_ledger_blocks(self):
        exam=self.exam(extra={'generation_scope':{'partial':True,'section_ids':['Z']}})
        self.assert_blocks(self.audit(exam),'invalid_scope')
    def test_section_order_mismatch_blocks(self):
        ledger=self.ledger(sections=[self.reading_section(),{'id':'B','kind':'reading','paragraphs':[],'questions':[]}])
        self.assert_blocks(self.audit(self.exam(),ledger_path=ledger),'source_section_order')
    def test_changed_paragraph_text_blocks(self):
        exam=self.exam(section=self.reading_section(text='The museum opens at ten in the morning.'))
        self.assert_blocks(self.audit(exam),'source_paragraphs')
    def test_missing_question_blocks(self):
        exam=self.exam(section=self.reading_section(question={'id':'22'}))
        self.assert_blocks(self.audit(exam),'source_questions')
    def test_answer_disagreeing_with_the_ledger_blocks(self):
        exam=self.exam(section=self.reading_section(question={'answer':'A'}))
        self.assert_blocks(self.audit(exam),'official_answer_mismatch')

    # —— 答案表 ——
    def test_answer_key_file_missing_blocks(self):
        self.assert_blocks(self.audit(answer_key=str(self.base/'没有这个文件.json')),'answer_key_missing_file')
    def test_answer_table_without_a_registered_answer_file_blocks(self):
        key=self.base/'answers.json'
        key.write_text(json.dumps({'answers':{'21':'B'},'answer_source_sha256':'a'*64}),encoding='utf-8')
        ledger=self.ledger(sources=[{'role':'paper','path':'paper.pdf','sha256':sha(self.base/'paper.pdf')}])
        self.assert_blocks(self.audit(ledger_path=ledger,answer_key=str(key)),'answer_file_fingerprint_missing')

    # —— 结构与内容 ——
    def test_answer_leaked_in_the_grammar_source_blocks(self):
        section={'id':'G','kind':'grammar','paragraphs':[{'id':'G-p1','text':'The book {{56}} which I read.'}],
                 'questions':[{'id':'56','stem':'关系代词','options':{},'answer':'which','answer_status':'official'}]}
        report=self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section]))
        self.assertIn('answer_leaked_in_source',self.codes(report))
    def test_multiline_paragraph_in_a_passage_blocks(self):
        exam=self.exam(section=self.reading_section(text='First line.\nSecond line keeps going.'))
        self.assert_blocks(self.audit(exam),'collapsed_paragraphs')
    def test_one_structure_card_for_a_multi_paragraph_passage_blocks(self):
        section=self.reading_section(extra={'structure':[{'title':'总述','analysis':'讲一件事'}]})
        section['paragraphs']=[{'id':f'A-p{i}','text':TEXT} for i in (1,2,3)]
        report=self.audit(self.exam(section=section),ledger_path=self.ledger(sections=[section]))
        self.assertIn('structure_too_generic',self.codes(report))
    def test_placeholder_structure_analysis_blocks(self):
        section=self.reading_section(extra={'structure':[{'title':'总述','analysis':'全文共 3 段，按顺序逐段精读。'}]})
        report=self.audit(self.exam(section=section),ledger_path=self.ledger(sections=[section]))
        self.assertIn('structure_placeholder',self.codes(report))
    def test_model_text_inside_the_paper_area_blocks(self):
        section={'id':'W','kind':'writing','paragraphs':[{'id':'W-p1','text':'Dear Tom, I am glad to hear from you. '*4,'role':'model'}],
                 'questions':[{'id':'81','stem':'书面表达','options':{},'answer':'范文','answer_status':'sample'}]}
        report=self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section]))
        self.assertIn('model_in_source',self.codes(report))
    def test_writing_steps_with_wrong_type_blocks(self):
        section={'id':'W','kind':'writing','paragraphs':[{'id':'W-p1','text':'Write a letter.'}],
                 'questions':[{'id':'81','stem':'书面表达','options':{},'answer':'范文','answer_status':'sample'}],
                 'writing_steps':{'outline':'不是数组','language':[],'model_analysis':[]}}
        report=self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section]))
        self.assertIn('writing_field_type',self.codes(report))

    # —— 听力 ——
    def listening_section(self,extra=None,questions=None,audio='L1.mp3',write_audio=True):
        if write_audio and audio:(self.base/audio).write_bytes(b'fake audio bytes')
        section={'id':'L1','kind':'listening','title':'Text 1',
                 'paragraphs':[{'id':'L1-p1','text':'The two speakers talk about their weekend plan.'}],
                 'questions':questions if questions is not None else [{'id':'1','stem':'q','options':{'A':'a','B':'b'},'answer':'A'}]}
        if audio:section['audio']=audio      # 不给音频时不要留 audio=None：闸门会去拼路径
        section.update(extra or {})
        return section
    def test_listening_without_any_audio_blocks(self):
        section=self.listening_section(audio=None,write_audio=False)
        report=self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section]))
        self.assertIn('listening_audio_absent',self.codes(report))
    def test_listening_without_audio_but_with_a_note_warns(self):
        section=self.listening_section(audio=None,write_audio=False,extra={'audio_note':'老师这里没有听力音频'})
        self.assert_warns(self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section])),
                          'listening_audio_not_provided')
    def test_collapsed_dialogue_blocks(self):
        section=self.listening_section(extra={'paragraphs':[{'id':'L1-p1','text':'M: Hello there. W: Hi, how are you?'}]})
        report=self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section]))
        self.assertIn('dialogue_collapsed',self.codes(report))
    def test_missing_alignment_blocks(self):
        section=self.listening_section()
        report=self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section]))
        self.assertIn('audio_alignment_missing',self.codes(report))
    def test_telling_the_teacher_to_drag_manually_blocks(self):
        section=self.listening_section(extra={'audio_alignment':{'mode':'text','boundary':'verified','full_start':0,'full_end':1},
            'questions':[{'id':'1','stem':'q','options':{'A':'a','B':'b'},'answer':'A','audio':'q1.mp3',
                          'audio_context':{'start':0,'end':1,'selection_reason':'教师自行拖动到本题'}}]})
        (self.base/'q1.mp3').write_bytes(b'question audio')
        report=self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section]))
        self.assertIn('manual_audio_workaround',self.codes(report))
    def test_all_question_clips_copied_from_the_whole_text_blocks(self):
        (self.base/'q1.mp3').write_bytes(b'fake audio bytes')      # 与整段音频逐字节相同
        questions=[{'id':str(i),'stem':'q','options':{'A':'a','B':'b'},'answer':'A','audio':'q1.mp3'} for i in (1,2)]
        section=self.listening_section(extra={'audio_alignment':{'mode':'text','boundary':'verified','full_start':0,'full_end':1}},
                                       questions=questions)
        report=self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section]))
        self.assertIn('question_audio_cloned',self.codes(report))
    def test_unsegmented_alignment_warns(self):
        section=self.listening_section(extra={'audio_alignment':{'mode':'unsegmented','boundary':'not_split'}})
        self.assert_warns(self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section])),
                          'audio_unsegmented')
    def test_invalid_source_window_blocks(self):
        section=self.listening_section(extra={'audio_alignment':{'mode':'text','boundary':'verified','full_start':5,'full_end':5}})
        report=self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section]))
        self.assertIn('audio_source_window',self.codes(report))
    def test_unusable_ffprobe_blocks(self):
        """本机没有 ffprobe（或它跑不起来）时，时长无法核对 → 必须阻断而不是放过。"""
        section=self.listening_section(extra={'audio_alignment':{'mode':'text','boundary':'verified','full_start':0,'full_end':1}})
        with patch.dict(os.environ,{'FFPROBE_BIN':''}):
            report=self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section]))
        self.assertIn('audio_probe',self.codes(report))

    # —— 需要 ffprobe 才能走到的那几条：用桩脚本 ——
    def fake_probe(self,duration):
        """给被测模块的 subprocess.run 打桩，模拟 ffprobe 报时长。

        不写可执行脚本：Windows 上没有 /bin/sh、可执行位也没有意义，
        直接替换调用点既跨平台、又只测我们关心的判据（时长不符/转写指纹/转写来源）。
        """
        class Result:
            returncode=0;stderr=''
            def __init__(self,stdout):self.stdout=stdout
        def run(argv,**kwargs):
            if any('format=duration' in str(a) for a in argv):return Result(f'{float(duration)}\n')
            raise AssertionError('测试桩只预期 ffprobe 的时长查询：'+repr(argv))
        return run
    def listening_with_alignment(self,full_end=1.0,extra=None):
        (self.base/'transcript.json').write_text(json.dumps({'source_audio_sha256':'f'*64,'segments':[]}),encoding='utf-8')
        alignment={'mode':'text','boundary':'verified','full_start':0.0,'full_end':full_end,
                   'transcript_file':'transcript.json','transcript_sha256':sha(self.base/'transcript.json')}
        alignment.update(extra or {})
        return self.listening_section(extra={'audio_alignment':alignment})
    def test_duration_mismatch_blocks(self):
        section=self.listening_with_alignment(full_end=9.0)
        with patch.object(quality_gate.subprocess,'run',side_effect=self.fake_probe(1.0)):
            report=self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section]))
        self.assertIn('audio_source_duration',self.codes(report))
    def test_missing_transcript_evidence_blocks(self):
        section=self.listening_section(extra={'audio_alignment':{'mode':'text','boundary':'verified','full_start':0.0,'full_end':1.0,
                                                                 'transcript_file':'transcript.json'}})
        with patch.object(quality_gate.subprocess,'run',side_effect=self.fake_probe(1.0)):
            report=self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section]))
        self.assertIn('audio_transcript_hash',self.codes(report))
    def test_transcript_from_another_recording_blocks(self):
        section=self.listening_with_alignment()
        with patch.object(quality_gate.subprocess,'run',side_effect=self.fake_probe(1.0)):
            report=self.audit(self.exam(sections=[section]),ledger_path=self.ledger(sections=[section]))
        self.assertIn('transcript_source_audio',self.codes(report))

    def test_every_gate_code_in_the_source_is_mentioned_somewhere_in_the_tests(self):
        """守卫：新增判据却没有测试会直接失败（本轮补齐前有 28 个码从未被测试提到）。"""
        tests='\n'.join(path.read_text(encoding='utf-8') for path in (ROOT/'tests').glob('*.py'))
        missing={}
        for name in ('quality_gate.py','answer_audit.py'):
            source=(ROOT/'scripts'/name).read_text(encoding='utf-8')
            codes=sorted(set([*__import__('re').findall(r"add\('([a-z_]+)'",source),
                              *__import__('re').findall(r"warn\('([a-z_]+)'",source),
                              *__import__('re').findall(r"block\('([a-z_]+)'",source),
                              *__import__('re').findall(r"flag\('([a-z_]+)'",source)]))
            absent=[code for code in codes if code not in tests]
            if absent:missing[name]=absent
        self.assertEqual(missing,{},f'这些判据码没有任何测试提到：{missing}')


if __name__=='__main__':unittest.main()
