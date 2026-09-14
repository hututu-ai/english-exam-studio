import contextlib, copy, hashlib, io, json, shutil, sys, tempfile, unittest, wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import check_install, preferences, build, import_timed_text
from unittest.mock import patch
class AddedWorkflows(unittest.TestCase):
    def test_partial_install_and_modified_template(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for n in ['SKILL.md','VERSION','scripts/check_update.py','scripts/doctor.py']:
                p=root/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,p)
            self.assertEqual(check_install.check(root)['status'],'incomplete_install')
            shutil.copytree(ROOT,root,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.git','work','dist','__pycache__'))
            self.assertEqual(check_install.check(root)['status'],'complete')
            (root/'assets/lesson.html').write_text('broken')
            self.assertEqual(check_install.check(root)['status'],'incomplete_install')
    def test_selected_features_and_pending_plan(self):
        d=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
        plan={'confirmed':True,'sections':'reading','mode':'lesson','features':{k:False for k in preferences.DEFAULTS}}
        with self.assertRaisesRegex(ValueError,'询问'):preferences.apply_plan(d,{**plan,'confirmed':False})
        with self.assertRaises(ValueError):preferences.apply_plan(d,{**plan,'features':{'quick_answers':False}})
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'plan.json';p.write_text(json.dumps(plan))
            with contextlib.redirect_stdout(io.StringIO()):build.build(ROOT/'examples/demo-reading.json',Path(t)/'output',ROOT/'examples/source-ledger.json',plan=p)
            result=json.loads((Path(t)/'output/exam.json').read_text(encoding='utf-8'))
            self.assertNotIn('writing_bank',result['sections'][0]);self.assertNotIn('structure',result['sections'][0])
            self.assertTrue(result['sections'][0]['questions'][0]['strategy'])
            result['features']['culture_background']=True
            with self.assertRaisesRegex(ValueError,'文化背景'):build.validate_features(result)
    def test_same_recording_subtitles_without_whisper_or_ffprobe(self):
        with tempfile.TemporaryDirectory(prefix='中文 path ') as t:
            root=Path(t);wav=root/'原音.wav'
            with wave.open(str(wav),'wb') as w:w.setparams((1,2,8000,0,'NONE','not compressed'));w.writeframes(b'\0\0'*16000)
            sub=root/'字幕.srt';sub.write_text('1\n00:00:00,100 --> 00:00:01,500\nHello, teacher.\n',encoding='utf-8')
            out=root/'transcript.json'
            with self.assertRaises(ValueError):import_timed_text.convert(wav,sub,out)
            with patch('audio.run',side_effect=AssertionError('External command not expected')):
                r=import_timed_text.convert(wav,sub,out,True)
            self.assertEqual(r['segments'][0]['end'],1.5);self.assertEqual(r['alignment_review'],'pending')
            sub.write_text('WEBVTT\n\n00:00.100 --> 00:01.500\nHello\n',encoding='utf-8');vtt=root/'字幕.vtt';sub.rename(vtt)
            self.assertEqual(import_timed_text.parse(vtt)[0]['start'],.1)
            sub.write_text('1\n00:00:00,100 --> 00:00:03,000\nToo long\n')
            with self.assertRaisesRegex(ValueError,'超出'):import_timed_text.convert(wav,sub,out,True)
    def test_malformed_subtitle_time_is_explained_in_chinese(self):
        """时间行坏掉时不能漏 float() 的英文原文（1.0.104）。"""
        for value,want in [('.:.','无法识别的字符'),('1:2:3.4.5','无法识别的字符'),
                           ('00:99:01,000','小于 60'),('01:02:03:04','不是 mm:ss')]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as caught:import_timed_text.seconds(value)
                message=str(caught.exception)
                self.assertIn(want,message)
                self.assertNotIn('could not convert',message,'不能把 float() 的英文原文漏给老师')
    def test_subtitle_json_that_is_not_json_says_so_in_chinese(self):
        with tempfile.TemporaryDirectory() as t:
            bad=Path(t)/'字幕.json';bad.write_text('{oops',encoding='utf-8')
            with self.assertRaises(ValueError) as caught:import_timed_text.parse(bad)
            message=str(caught.exception)
            self.assertIn('不是合法 JSON',message)
            self.assertNotIn('Expecting value',message)
    def test_dictionary_payload_respects_the_feature_toggle(self):
        # 关闭查词时不能把 4MB 词库塞进课件：既违背"未选扩展不生成"，也让 HTML 变大、打开变慢。
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);plans={}
            for name,on in (('off',False),('on',True)):
                features={k:False for k in preferences.DEFAULTS};features['dictionary']=on
                path=root/f'{name}.json';path.write_text(json.dumps({'confirmed':True,'sections':'reading','mode':'lesson','features':features}),encoding='utf-8');plans[name]=path
            with contextlib.redirect_stdout(io.StringIO()):
                build.build(ROOT/'examples/demo-reading.json',root/'off',ROOT/'examples/source-ledger.json',plan=plans['off'])
                build.build(ROOT/'examples/demo-reading.json',root/'on',ROOT/'examples/source-ledger.json',plan=plans['on'])
            off=json.loads((root/'off/exam.json').read_text(encoding='utf-8'))
            on=json.loads((root/'on/exam.json').read_text(encoding='utf-8'))
            self.assertNotIn('dictionary',off)
            self.assertNotIn('legacy_dictionary',off)
            self.assertIn('dictionary',on)
            self.assertLess((root/'off/index.html').stat().st_size,(root/'on/index.html').stat().st_size)
    def test_dictionary_scope_defaults_to_lesson_words_only(self):
        # 默认只内置本篇出现的词：4MB 整本词库会把 HTML 撑到 4.4MB，而课堂查的多半是本篇的词。
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);plan=root/'plan.json'
            plan.write_text(json.dumps({'confirmed':True,'sections':'reading','mode':'lesson','features':dict(preferences.DEFAULTS)}),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                build.build(ROOT/'examples/demo-reading.json',root/'lesson',ROOT/'examples/source-ledger.json',plan=plan)
                build.build(ROOT/'examples/demo-reading.json',root/'full',ROOT/'examples/source-ledger.json',plan=plan,dictionary_scope='full')
            lesson=json.loads((root/'lesson/exam.json').read_text(encoding='utf-8'))
            full=json.loads((root/'full/exam.json').read_text(encoding='utf-8'))
            self.assertIn('repair',lesson['dictionary'],'a word from the passage must stay offline-lookupable')
            self.assertIn('withdraw',full['dictionary'])
            self.assertNotIn('withdraw',lesson['dictionary'],'words outside this lesson must not be embedded')
            self.assertLess(len(lesson['dictionary'])*10,len(full['dictionary']),'lesson scope must be far smaller than the whole dictionary')
            self.assertGreater(len(lesson['dictionary']),20)
            self.assertLess((root/'lesson/index.html').stat().st_size,(root/'full/index.html').stat().st_size)
            report=json.loads((root/'lesson/build-report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['dictionary']['scope'],'lesson')
    def test_lesson_dictionary_scope_equals_the_straightforward_filter(self):
        """作用域裁剪用"开头 2/3 字"预筛加速：结果必须与朴素子串判断逐条一致。

        这条是默认路径，直接决定成品里能离线查哪些词、HTML 多大——优化不能悄悄改变它。
        """
        library=json.loads((ROOT/'assets'/'offline-dictionary.json').read_text(encoding='utf-8'))
        exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
        tokens,blob=build.lesson_vocabulary(exam)
        plain={k:v for k,v in library.items() if k.lower() in tokens or (len(k)>1 and k.lower() in blob)}
        self.assertTrue(plain,'夹具本身要能筛出词条，否则这个测试没有意义')
        self.assertEqual(build.scope_dictionary(library,tokens,blob),plain,'加速版必须与朴素写法逐条一致')
        self.assertNotIn('withdraw',build.scope_dictionary(library,tokens,blob),'不在本篇的词不能被放进来')
        edge={'a':{'meaning':'x'},'in':{'meaning':'y'},'zz':{'meaning':'z'},'repair corner':{'meaning':'q'},'in the library':{'meaning':'w'}}
        plain_edge={k:v for k,v in edge.items() if k.lower() in tokens or (len(k)>1 and k.lower() in blob)}
        self.assertEqual(build.scope_dictionary(edge,tokens,blob),plain_edge,'边界键（单字/两字/多词短语）也必须一致')
        self.assertIn('repair corner',build.scope_dictionary(edge,tokens,blob),'本篇出现的多词短语要按子串保留')
        self.assertNotIn('zz',build.scope_dictionary(edge,tokens,blob))

if __name__=='__main__':unittest.main()
