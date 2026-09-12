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
import build, parts, scope, doctor, audio
import bounded_command, platform_tools
from verify_output import verify_output

def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

class Workflow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill ')
        self.base=Path(self.temp.name)
        self.exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
    def tearDown(self):self.temp.cleanup()

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

    def test_doctor_requires_runnable_probe_and_mp3(self):
        for probe_ok,mp3,asr_ok,expected in [(False,True,True,'no_ffmpeg'),(True,False,True,'no_ffmpeg'),(True,True,False,'silence_only'),(True,True,True,'full_auto')]:
            output=io.StringIO()
            with patch.object(sys,'argv',['doctor.py','--json']),patch.object(doctor,'tool',side_effect=lambda *names:names[0]),patch.object(doctor,'find_models',return_value=[{'path':'ggml-base.bin','size_gb':.15}]),patch.object(doctor,'first_line',side_effect=['ffmpeg version test','ffprobe version test' if probe_ok else '', 'usage: whisper' if asr_ok else '']),patch.object(doctor,'full_output',return_value='libmp3lame' if mp3 else 'aac'),contextlib.redirect_stdout(output):
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

    def test_embedded_audio_and_missing_ffprobe(self):
        # A synthetic tone is a media fixture, never presented as exam speech.
        wav=self.base/'测试 音频.wav'
        with wave.open(str(wav),'wb') as f:
            f.setparams((1,2,8000,0,'NONE','not compressed'))
            f.writeframes(b''.join(struct.pack('<h',int(1000*math.sin(i*.2))) for i in range(16000)))
        d=copy.deepcopy(self.exam);s=d['sections'][0];s['kind']='listening';s['id']='L1'
        s['audio_scope']='full_paper';s['audio_alignment']={'mode':'unsegmented'}
        s['audio']=wav.name;d['full_audio']=wav.name
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
            if mode=='embedded':
                (out/'audio/full.wav').write_bytes(b'corrupted')
                with self.assertRaises(ValueError):verify_output(out)

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

if __name__=='__main__':unittest.main()
