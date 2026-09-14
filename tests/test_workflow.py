import contextlib
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build, parts, scope, doctor, audio, preferences, answers, check_install
from package_lesson import package
import bounded_command, platform_tools
from verify_output import verify_output

def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

def make_qa_report(out):
    """交付同时要求已完成的人工复核清单；用工具自身的模板生成并填好结论。"""
    import re
    from qa_report import collect,render
    items,report,_=collect(out)
    text=re.sub(r'—— 结论：$','—— 结论：单元测试夹具已逐条核对。',render(items,report),flags=re.M)
    (Path(out)/'qa-report.md').write_text(text,encoding='utf-8')

class Workflow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill ')
        self.base=Path(self.temp.name)
        self.exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
    def tearDown(self):self.temp.cleanup()

    def test_invalid_ids_and_cross_section_paragraph_collision(self):
        d=copy.deepcopy(self.exam);d['sections'][0]['questions'][0]['id']='21"]'
        with self.assertRaises(ValueError):build.validate(d)
        d=copy.deepcopy(self.exam);other=copy.deepcopy(d['sections'][0]);other['id']='B'
        for i,q in enumerate(other['questions']):q['id']=str(30+i)
        d['sections'].append(other)
        with self.assertRaisesRegex(ValueError,'段落 ID 跨章节重复'):build.validate(d)

    def test_delivery_requires_current_browser_evidence_and_complete_html(self):
        out=self.base/'output'
        with contextlib.redirect_stdout(io.StringIO()):build.build(ROOT/'examples/demo-reading.json',out,ROOT/'examples/source-ledger.json')
        self.assertTrue((out/'打开课件.html').exists())
        with self.assertRaisesRegex(ValueError,'浏览器'):package(out,self.base/'lesson.zip')
        self.assertEqual(package(out,self.base/'preview.zip',True)['status'],'preview_only_browser_check_pending')
        # Unit fixture only: integration workflow creates real browser evidence.
        data=(out/'index.html').read_bytes()
        evidence={'status':'passed','engine':'unit-test-fixture','html_sha256':hashlib.sha256(data).hexdigest(),'checks':[{'name':'unit fixture','status':'passed'}],'errors':[]}
        write(out/'browser-check.json',evidence)
        make_qa_report(out)
        self.assertEqual(package(out,self.base/'lesson.zip')['status'],'browser_checked')
        evidence['html_sha256']='stale';write(out/'browser-check.json',evidence)
        with self.assertRaisesRegex(ValueError,'浏览器'):package(out,self.base/'stale.zip')
        (out/'index.html').write_bytes(data[:-200])
        with self.assertRaises(ValueError):verify_output(out)

    def test_scope_order_and_unknown(self):
        a=self.exam['sections'][0];b=copy.deepcopy(a);b['id']='B'
        d={**self.exam,'sections':[a,b],'full_audio':'unused.mp3'}
        selected=scope.select(d,'B,A')
        self.assertEqual([s['id'] for s in selected['sections']],['A','B'])
        self.assertNotIn('full_audio',selected)
        self.assertEqual(len(scope.select(d,'B')['sections']),1)
        with self.assertRaises(ValueError):scope.select(d,'C')
        with self.assertRaises(ValueError):scope.select(d,'A','intensive')
        with self.assertRaises(ValueError):scope.select(d,'all,TYPO')
        d['sections'][0]['kind']='listening'
        chosen=scope.select(d,'A','intensive')
        self.assertEqual(scope.select(chosen)['generation_scope']['mode'],'intensive')

    def test_range_letters_work_when_section_ids_are_not_letters(self):
        """老师的原话是 A 只做听力／B 整卷／C 指定板块；初中卷节 ID 是 S1/S2…，字母要对得上。

        以前 `--sections A` 会报"材料中没有这个板块：A"——助手把老师说的 A 直接传下去就卡住。
        但示例卷的阅读节 ID 恰好是 "A"，所以只有"对不上任何章节 ID"时才按范围字母解释。
        """
        sections=[{'id':'S1','kind':'听说应用','kind_preset':'listening','questions':[{'id':'1'}]},
                  {'id':'S2','kind':'语法选择','kind_preset':'cloze','questions':[{'id':'6'}]},
                  {'id':'S3','kind':'阅读理解','kind_preset':'reading','questions':[{'id':'26'}]}]
        exam={'sections':sections}
        self.assertEqual([s['id'] for s in scope.select(copy.deepcopy(exam),'A','intensive')['sections']],['S1'],
                         'A = 只做听力：即使节 ID 不是 A，也要选中听力节')
        self.assertEqual([s['id'] for s in scope.select(copy.deepcopy(exam),'B')['sections']],['S1','S2','S3'],
                         'B = 整卷讲评')
        with self.assertRaisesRegex(ValueError,'指定板块'):scope.select(copy.deepcopy(exam),'C')
        with self.assertRaisesRegex(ValueError,'B 表示'):scope.select(copy.deepcopy(exam),'B,S1')
        with self.assertRaisesRegex(ValueError,'没有听力节'):
            scope.select({'sections':[{'id':'S9','kind':'阅读理解','questions':[{'id':'1'}]}]},'A','intensive')
        # 能对上章节 ID 时仍按 ID 走：示例卷的阅读节就叫 A
        self.assertEqual([s['id'] for s in scope.select(copy.deepcopy(self.exam),'A')['sections']],['A'])

    def test_doctor_requires_runnable_probe_and_mp3(self):
        for probe_ok,mp3,asr_ok,expected in [(False,True,True,'no_ffmpeg'),(True,False,True,'no_ffmpeg'),(True,True,False,'silence_only'),(True,True,True,'full_auto')]:
            output=io.StringIO()
            # 固定安装状态：doctor 在安装不完整时只报 installation 并提前返回（这是设计），
            # 不该让"工作树刚改过、还没重新打包"影响这个测能力档位的用例。
            with patch.object(sys,'argv',['doctor.py','--json']),patch.object(check_install,'check',return_value={'status':'complete','version':'fixture','checked_files':0,'errors':[]}),patch.object(doctor,'tool',side_effect=lambda *names:names[0]),patch.object(doctor,'find_models',return_value=[{'path':'ggml-base.bin','size_gb':.15}]),patch.object(doctor,'first_line',side_effect=['ffmpeg version test','ffprobe version test' if probe_ok else '', 'usage: whisper' if asr_ok else '']),patch.object(doctor,'full_output',return_value='libmp3lame' if mp3 else 'aac'),contextlib.redirect_stdout(output):
                doctor.main()
            self.assertEqual(json.loads(output.getvalue())['capability'],expected)

    def test_scope_keeps_expected_coverage_and_skips_unselected_invalid_section(self):
        d=copy.deepcopy(self.exam)
        d['expected_question_ids']=['21','22','23']
        self.assertEqual(scope.select(d)['expected_question_ids'],['21','22','23'])
        d=copy.deepcopy(self.exam)
        d['sections'].append({'id':'L1','kind':'listening','title':'未选中且未编写的听力','questions':[]})
        d['full_audio']='not-provided.mp3'
        source=self.base/'exam.json';write(source,d)
        ledger={'sources':[{'role':'original_demo','path':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}],'sections':d['sections']}
        ledger_path=self.base/'source-ledger.json';write(ledger_path,ledger)
        with contextlib.redirect_stdout(io.StringIO()):
            build.build(source,self.base/'reading-only',ledger_path,selection='A')
        self.assertEqual(verify_output(self.base/'reading-only')['status'],'passed')

    def test_dependency_timeout_and_explicit_tool(self):
        code,out,err=bounded_command.run([sys.executable,'-c','import time; time.sleep(10)'],.2)
        self.assertEqual(code,124)
        self.assertIn('已终止',err)
        tool=self.base/'portable ffmpeg.exe';tool.write_bytes(b'fixture')
        with patch.dict('os.environ',{'FFMPEG_BIN':str(tool)}):
            self.assertEqual(platform_tools.ffmpeg_bin(),str(tool.resolve()))

    def test_parts_preserve_top_level(self):
        d={**self.exam,'custom_setting':{'中文':'值'},'dictionary':{},'full_audio':'音频/full.mp3'}
        source=self.base/'exam.json';write(source,d)
        parts.split(source,self.base/'parts')
        parts.merge(self.base/'parts',self.base/'merged.json')
        self.assertEqual(d,json.loads((self.base/'merged.json').read_text(encoding='utf-8')))
        section=self.base/'parts/A.json';bad=json.loads(section.read_text(encoding='utf-8'));bad['id']='OTHER';write(section,bad)
        with self.assertRaises(ValueError):parts.merge(self.base/'parts',source)

    def test_parts_check_flags_real_hazards_not_missing_passages(self):
        """合并前体检只管"合并会不会出事"：没有原文段落是正常形态，不该假失败；题号重复才要拦。"""
        sections=[{'id':'S1','kind':'听说应用','kind_preset':'listening','questions':[{'id':'1'}],'paragraphs':[{'id':'S1-p1','text':'Transcript.'}]},
                  {'id':'S2','kind':'配对阅读','kind_preset':'seven','questions':[{'id':'41'}]},
                  {'id':'S3','kind':'读写综合','kind_preset':'writing','questions':[{'id':'81'}]}]
        source=self.base/'exam.json';write(source,{**self.exam,'sections':sections})
        parts.split(source,self.base/'parts')
        report=parts.check(self.base/'parts')
        self.assertEqual(report['status'],'ok','配对阅读/书面表达本来就没有原文段落，不该报错')
        self.assertTrue(all('没有原文段落' in note for note in report['notes']),report['notes'])
        self.assertEqual(report['questions'],3)
        # 题号跨节重复：合并后构建会报重复，体检要更早发现
        part=self.base/'parts'/'S2.json';data=json.loads(part.read_text(encoding='utf-8'))
        data['questions']=[{'id':'1','stem':'dup'}];write(part,data)
        problems=parts.check(self.base/'parts')['problems']
        self.assertTrue(any('题号 1 同时出现在 S1 与 S2' in item for item in problems),problems)
        # 没有小题 / 没有 kind 仍然算问题
        data['questions']=[];write(part,data)
        problems=parts.check(self.base/'parts')['problems']
        self.assertTrue(any('还没有小题' in item for item in problems),problems)

    def test_embedded_audio_and_missing_ffprobe(self):
        # A synthetic tone is a media fixture, never presented as exam speech.
        wav=self.base/'测试 音频.wav'
        with wave.open(str(wav),'wb') as f:
            f.setparams((1,2,8000,0,'NONE','not compressed'))
            f.writeframes(b''.join(struct.pack('<h',int(1000*math.sin(i*.2))) for i in range(16000)))
        d=copy.deepcopy(self.exam);s=d['sections'][0];s['kind']='listening';s['id']='L1'
        s['audio_scope']='full_paper';s['audio_alignment']={'mode':'unsegmented'}
        s['audio']=wav.name;d['full_audio']=wav.name
        s['questions'][0].update(audio=wav.name,audio_context={'start':0,'end':2,'selection_reason':'Synthetic PCM fixture'})
        s['blanks']=[{'paragraph_id':s['paragraphs'][0]['id'],'start':0,'end':2,'purpose':'测试','question_ids':['21']}]
        d['dictionary']={};source=self.base/'exam.json';write(source,d)
        ledger={'sources':[{'role':'original_demo','path':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}],'sections':d['sections']}
        ledger_path=self.base/'source-ledger.json';write(ledger_path,ledger)
        for mode in ['embedded','folder']:
            out=self.base/mode
            with patch.object(build,'find_tool',return_value=None),contextlib.redirect_stdout(io.StringIO()):
                build.build(source,out,ledger_path,audio_mode=mode)
            self.assertEqual(verify_output(out)['status'],'passed')
            html=(out/'index.html').read_text(encoding='utf-8')
            self.assertEqual(';base64,' in html.split('<script id="examData"')[1].split('</script>')[0],mode=='embedded')
            report=json.loads((out/'build-report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['audio_embedded'],mode=='embedded')
            self.assertEqual(report['audio_delivery']['external_audio_count'],1)
            if mode=='folder':
                digest=hashlib.sha256((out/'index.html').read_bytes()).hexdigest()
                write(out/'browser-check.json',{'status':'passed','engine':'unit-test-fixture','html_sha256':digest,'media_sha256':verify_output(out)['resource_sha256'],'checks':[{'status':'passed'}]})
                make_qa_report(out)
                package(out,self.base/'folder.zip')
                (out/'audio/full.wav').write_bytes(b'changed after browser check')
                with self.assertRaisesRegex(ValueError,'浏览器'):package(out,self.base/'changed.zip')
                (out/'audio/full.wav').unlink()
                with self.assertRaises(ValueError):verify_output(out)
            if mode=='embedded':
                (out/'audio/full.wav').write_bytes(b'corrupted')
                with self.assertRaises(ValueError):verify_output(out)

        wav.write_bytes(wav.read_bytes()[:-100])
        with patch.object(build,'find_tool',return_value=None),self.assertRaisesRegex(ValueError,'WAV 数据被截断'):
            build.build(source,self.base/'truncated-wav',ledger_path)

    def test_external_transcript_skips_asr(self):
        source=self.base/'input.mp3';source.write_bytes(b'fixture')
        transcript=self.base/'timed.json'
        write(transcript,{'source_audio_sha256':audio.sha256(source),'segments':[{'start':1,'end':2,'text':'Hello there.'}]})
        from types import SimpleNamespace
        args=SimpleNamespace(out=str(self.base/'asr'),input=str(source),model=None,reuse=False,transcript=str(transcript),no_asr=False,no_gpu=False,jobs=1,threads=1,language='en',timeout=5,min_gap=1.2)
        with patch.object(audio,'probe',return_value=3),patch.object(audio,'find_silences',return_value=[]),patch.object(audio,'run',side_effect=AssertionError('Must not transcribe')),contextlib.redirect_stdout(io.StringIO()):
            audio.analyze(args)
        result=json.loads((self.base/'asr/transcript.json').read_text(encoding='utf-8'))
        self.assertEqual(result['segments'][0]['text'],'Hello there.')

    def test_audio_resume_rejects_same_length_new_window(self):
        from types import SimpleNamespace
        source=self.base/'original.mp3';source.write_bytes(b'original recording')
        manifest=self.base/'segments-input.json'
        row={'id':'L1','start':1,'end':2,'question_ids':['1'],'evidence':'test','verified':True}
        write(manifest,{'kind':'text','expected_count':1,'segments':[row]})
        args=SimpleNamespace(input=str(source),manifest=str(manifest),out=str(self.base/'clips'),transcript=None,resume=False,allow_unverified=False,threads=1,jobs=1)
        def encode(cmd,**kw):Path(cmd[-1]).write_bytes(str(cmd).encode('utf-8'));return ''
        with patch.object(audio,'probe',side_effect=lambda p:6 if Path(p).resolve()==source.resolve() else 1),patch.object(audio,'run',side_effect=encode) as runner,contextlib.redirect_stdout(io.StringIO()):
            audio.cut(args);args.resume=True;runner.reset_mock();audio.cut(args)
            self.assertEqual(runner.call_count,0)
            row.update(start=3,end=4);write(manifest,{'kind':'text','expected_count':1,'segments':[row]})
            audio.cut(args);self.assertEqual(runner.call_count,1)
            runner.reset_mock();source.write_bytes(b'different recording');audio.cut(args)
            self.assertEqual(runner.call_count,1)
            self.assertEqual((self.base/'clips/full.mp3').read_bytes(),source.read_bytes())

    def test_reported_html_hash_uses_raw_bytes_not_normalized_text(self):
        # Windows write_text emits CRLF while read_text normalizes it away. The reported
        # hash must still match browser_check.cjs and package_lesson.py, which hash bytes.
        out=self.base/'crlf'
        with contextlib.redirect_stdout(io.StringIO()):
            build.build(ROOT/'examples/demo-reading.json',out,ROOT/'examples/source-ledger.json')
        page=out/'index.html'
        page.write_bytes(page.read_bytes().replace(b'\n',b'\r\n'))
        result=verify_output(out)
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['html_sha256'],hashlib.sha256(page.read_bytes()).hexdigest())
        self.assertIn(b'\r\n',page.read_bytes())
    def test_narrower_rebuild_drops_stale_media_but_keeps_teacher_files(self):
        d=copy.deepcopy(self.exam)
        other=copy.deepcopy(d['sections'][0]);other['id']='B';other['title']='阅读 B'
        for p in other['paragraphs']:p['id']=p['id'].replace('A-','B-')
        for q in other['questions']:q['id']=str(int(q['id'])+2)
        for key in ('structure','logic_steps','inquiry','writing_bank','vocabulary','sentences','quick_words'):
            for item in other.get(key,[]):
                if 'paragraph_id' in item:item['paragraph_id']=item['paragraph_id'].replace('A-','B-')
                if 'paragraph_ids' in item:item['paragraph_ids']=[x.replace('A-','B-') for x in item['paragraph_ids']]
        for q in other['questions']:
            for ev in q.get('evidence',[]):ev['paragraph_id']=ev['paragraph_id'].replace('A-','B-')
        image=self.base/'page-b.png';image.write_bytes(b'\x89PNG\r\n\x1a\n'+b'0'*32)
        other['origin']={'exam_page':3,'page_image':str(image)}
        d['sections'].append(other);d['expected_question_ids']=['21','22','23','24']
        source=self.base/'exam.json';write(source,d)
        ledger={'sources':[{'role':'original_demo','path':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}],'sections':d['sections']}
        ledger_path=self.base/'source-ledger.json';write(ledger_path,ledger)
        out=self.base/'out'
        with contextlib.redirect_stdout(io.StringIO()):build.build(source,out,ledger_path)
        stale=out/'sources/B-paper.png'
        self.assertTrue(stale.exists(),'full build should package section B media')
        keep=out/'教师备注.txt';keep.write_text('note',encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):build.build(source,out,ledger_path,selection='A')
        self.assertFalse(stale.exists(),'narrower rebuild must not ship the previous scope media')
        self.assertTrue(keep.exists(),'hand-placed teacher files must survive a rebuild')
    def test_listening_lesson_embeds_audio_and_supports_folder_mode(self):
        first="Excuse me, when does the library close today?"
        second="It closes at six, but the reading room stays open until nine."
        wav=self.base/'L1.wav'
        with wave.open(str(wav),'wb') as handle:
            handle.setparams((1,2,8000,0,'NONE','not compressed'));handle.writeframes(b'\x00\x00'*8000)
        start=second.index('six')
        section={'id':'L1','kind':'listening','title':'听力 Test 1','expected_option_count':4,
            'audio':wav.name,'audio_scope':'full_paper','audio_alignment':{'mode':'unsegmented'},
            'paragraphs':[{'id':'L1-p1','speaker':'W','text':first,'translation':'W：请问图书馆今天几点关门？'},
                          {'id':'L1-p2','speaker':'M','text':second,'translation':'M：六点关门，但阅览室开放到九点。'}],
            'questions':[{'id':'1','stem':'When does the library close today?',
                'options':{'A':'At five.','B':'At six.','C':'At seven.','D':'At nine.'},
                'answer':'B','answer_status':'sample','answer_source':'本地合成听力测试',
                'question_type':'细节理解 · 时间信息','type_note':'题干问关门时间。',
                'solve_steps':['听关键词 close today。','定位 It closes at six。','对应选项 B，排除 nine。'],
                'pitfall':'不要用阅览室的 nine 代替关门时间。','analysis':'It closes at six 对应 B。',
                'evidence':[{'paragraph_id':'L1-p2','quote':'It closes at six'}],
                'distractors':{'A':'原文不是五点。','C':'原文没有七点。','D':'九点是阅览室时间。'},
                'strategy':'区分主句与转折补充信息。'}],
            'blanks':[{'paragraph_id':'L1-p2','start':start,'end':start+3,'question_ids':['1'],'purpose':'答案依据的时间词'}],
            'quick_words':[{'word':'close','lemma':'close','meaning':'关门','note':'动词。','paragraph_id':'L1-p1','occurrences':1}],
            'vocabulary':[{'word':'close','meaning':'v. 关门','context':'指停止营业的时间。','paragraph_id':'L1-p1','quote':'when does the library close today'}]}
        exam={'title':'听力测试','expected_question_ids':['1'],'sections':[section]}
        source=self.base/'exam.json';write(source,exam)
        ledger={'sources':[{'role':'original_demo','path':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}],
                'sections':[{'id':'L1','kind':'listening','paragraphs':[{'id':p['id'],'text':p['text']} for p in section['paragraphs']],
                             'questions':[{'id':'1','stem':section['questions'][0]['stem'],'options':section['questions'][0]['options'],'answer':'B','answer_status':'sample'}]}]}
        ledger_path=self.base/'source-ledger.json';write(ledger_path,ledger)
        for mode,embedded in (('embedded',True),('folder',False)):
            out=self.base/('out-'+mode)
            with contextlib.redirect_stdout(io.StringIO()):
                build.build(source,out,ledger_path,audio_mode=mode)
            report=json.loads((out/'build-report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['audio_delivery']['mode'],mode)
            self.assertEqual(report['audio_embedded'],embedded)
            self.assertTrue((out/'audio/L1.wav').exists(),'audio backup must travel with the lesson')
            self.assertEqual(verify_output(out)['status'],'passed')
    def test_quick_profile_allows_missing_enrichment_but_full_rejects_it(self):
        d=copy.deepcopy(self.exam);section=d['sections'][0]
        for key in ('sentences','structure','writing_bank','logic_steps','inquiry'):
            section.pop(key,None)
        source=self.base/'exam.json';write(source,d)
        ledger={'sources':[{'role':'original_demo','path':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}],'sections':d['sections']}
        ledger_path=self.base/'source-ledger.json';write(ledger_path,ledger)
        with self.assertRaisesRegex((AssertionError,ValueError),'缺少「句子精讲」内容（sentences）'):
            with contextlib.redirect_stdout(io.StringIO()):
                build.build(source,self.base/'full-out',ledger_path)
        out=self.base/'quick-out'
        with contextlib.redirect_stdout(io.StringIO()):
            build.build(source,out,ledger_path,profile='quick')
        report=json.loads((out/'build-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['profile'],'quick')
        self.assertEqual({item['missing'] for item in report['feature_coverage']['missing_enrichment']},{'sentences','structure','writing_bank'})
        self.assertEqual(report['delivery_status'],'quick_profile_content_and_browser_review_required')
        self.assertTrue(any('快速档' in item for item in report['pending_items']))
        self.assertEqual(verify_output(out)['status'],'passed')
    def test_plan_profile_is_honoured_without_the_cli_flag(self):
        # The plan records profile=quick, but build() used to ignore that field and run the
        # full requirements, so an agent following the docs got a hard failure (or the slow path).
        d=copy.deepcopy(self.exam);section=d['sections'][0]
        for key in ('sentences','structure','writing_bank','logic_steps','inquiry'):
            section.pop(key,None)
        source=self.base/'exam.json';write(source,d)
        ledger={'sources':[{'role':'original_demo','path':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}],'sections':d['sections']}
        ledger_path=self.base/'source-ledger.json';write(ledger_path,ledger)
        plan=self.base/'plan.json'
        write(plan,{'confirmed':True,'sections':'reading','mode':'lesson','profile':'quick','features':{k:False for k in preferences.DEFAULTS}})
        out=self.base/'out'
        with contextlib.redirect_stdout(io.StringIO()):
            build.build(source,out,ledger_path,plan=plan)
        report=json.loads((out/'build-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['profile'],'quick')
        self.assertEqual({item['missing'] for item in report['feature_coverage']['missing_enrichment']},{'sentences','structure','writing_bank'})
        self.assertEqual(report['generation_scope']['mode'],'lesson')
        with self.assertRaisesRegex((AssertionError,ValueError),'缺少「句子精讲」内容（sentences）'):
            with contextlib.redirect_stdout(io.StringIO()):
                build.build(source,self.base/'out-full',ledger_path,profile='full',plan=plan)
    def test_plan_rejects_an_unknown_profile(self):
        plan={'confirmed':True,'sections':'reading','mode':'lesson','profile':'fast','features':{k:False for k in preferences.DEFAULTS}}
        with self.assertRaisesRegex(ValueError,'profile'):
            preferences.apply_plan(copy.deepcopy(self.exam),plan)
    def test_six_kinds_with_official_answers_pass_the_whole_chain(self):
        # End-to-end approximation of a real task: every objective 题型's official answer is
        # proven against an answer-key file, across listening/reading/seven/cloze.
        import subprocess
        src=self.base/'paper'
        made=subprocess.run([sys.executable,str(ROOT/'tests/make_browser_fixture.py'),str(src),str(self.base/'seed')],
                            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        self.assertEqual(made.returncode,0,made.stderr)
        exam=json.loads((src/'exam.json').read_text(encoding='utf-8'))
        ledger=json.loads((src/'source-ledger.json').read_text(encoding='utf-8'))
        official={}
        for section in exam['sections']:
            for q in section['questions']:
                if q.get('options'):
                    q['answer_status']='official';q['answer_source']=f'答案原件第 {q["id"]} 题'
                    official[str(q['id'])]=str(q['answer'])
        self.assertGreaterEqual(len(official),6)
        for section in ledger['sections']:
            for q in section.get('questions',[]):
                if str(q['id']) in official:
                    q['answer_status']='official';q['answer_reference']=f'答案原件第 {q["id"]} 题'
        key=src/'answer-key.txt'
        key.write_text('\n'.join(f'{k} {v}' for k,v in sorted(official.items(),key=lambda item:int(item[0])))+'\n',encoding='utf-8')
        write(src/'exam.json',exam)
        ledger['sources']=[{'role':'original_demo','path':'exam.json','sha256':hashlib.sha256((src/'exam.json').read_bytes()).hexdigest()},
                           {'role':'answers','path':key.name,'sha256':hashlib.sha256(key.read_bytes()).hexdigest()}]
        write(src/'source-ledger.json',ledger)
        table=src/'answers.json';write(table,answers.extract(key))
        out=self.base/'official-out'
        with contextlib.redirect_stdout(io.StringIO()):
            build.build(src/'exam.json',out,src/'source-ledger.json',answer_key=str(table))
        report=json.loads((out/'build-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['quality_gate']['status'],'automated_checks_passed',report['quality_gate']['errors'])
        self.assertGreaterEqual(report['answer_audit']['counts']['official'],6)
        self.assertEqual(report['answer_audit']['blocking'],[])
    def test_delivery_report_discloses_skipped_browser_checks(self):
        # 跳过项（功能未开启/无数据）不能被读成"已通过"，交付报告必须如实列出。
        out=self.base/'skipped-out'
        with contextlib.redirect_stdout(io.StringIO()):
            build.build(ROOT/'examples/demo-reading.json',out,ROOT/'examples/source-ledger.json')
        verified=verify_output(out)
        page=(out/'index.html').read_bytes()
        write(out/'browser-check.json',{'status':'passed','engine':'unit-test-fixture','html_sha256':hashlib.sha256(page).hexdigest(),
            'media_sha256':verified['resource_sha256'],'checks':[{'name':'ran','status':'passed'}],
            'skipped':[{'name':'not-applicable','reason':'功能未开启'}],'errors':[]})
        make_qa_report(out)
        self.assertEqual(package(out,self.base/'skipped.zip')['status'],'browser_checked')
        report=json.loads((out/'delivery-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['browser_checks'],{'passed':1,'skipped':1})
        self.assertEqual(report['browser_checks_skipped'][0]['name'],'not-applicable')
        self.assertIn('未经验证',report['scope'])
if __name__=='__main__':unittest.main()
