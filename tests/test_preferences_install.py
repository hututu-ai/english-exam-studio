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
        d=json.loads((ROOT/'examples/demo-reading.json').read_text())
        plan={'confirmed':True,'sections':'reading','mode':'lesson','features':{k:False for k in preferences.DEFAULTS}}
        with self.assertRaisesRegex(ValueError,'询问'):preferences.apply_plan(d,{**plan,'confirmed':False})
        with self.assertRaises(ValueError):preferences.apply_plan(d,{**plan,'features':{'quick_answers':False}})
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'plan.json';p.write_text(json.dumps(plan))
            with contextlib.redirect_stdout(io.StringIO()):build.build(ROOT/'examples/demo-reading.json',Path(t)/'output',ROOT/'examples/source-ledger.json',plan=p)
            result=json.loads((Path(t)/'output/exam.json').read_text())
            self.assertNotIn('writing_bank',result['sections'][0]);self.assertNotIn('structure',result['sections'][0])
            self.assertTrue(result['sections'][0]['questions'][0]['strategy'])
            result['features']['culture_background']=True
            with self.assertRaisesRegex(AssertionError,'文化背景'):build.validate_features(result)
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
if __name__=='__main__':unittest.main()
