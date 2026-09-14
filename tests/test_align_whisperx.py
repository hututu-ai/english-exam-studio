import contextlib,importlib.metadata,io,json,runpy,sys,tempfile,types,unittest,wave
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import align_whisperx as aligner,audio,platform_tools
try:
    import numpy  # 预先载入：patch.dict 会在退出时恢复 sys.modules，若 numpy 是在补丁期间才首次导入，会被摘掉并在下一次 import 时重复初始化（ImportError: cannot load module more than once per process）
except ImportError:numpy=None

AUDIO_SHA='a'*64

def fake_modules(words,rate=16000):
    """伪造 torch/whisperx/nltk：本机没有可用的 torch，这里只测校验与记录逻辑。"""
    calls={'load':0,'align':0}
    torch=types.ModuleType('torch');torch.set_num_threads=lambda n:None
    nltk=types.ModuleType('nltk');nltk.data=types.SimpleNamespace(path=[],find=lambda name:None)
    whisperx=types.ModuleType('whisperx')
    def load_align_model(**kw):
        calls['load']+=1;return ('model','metadata')
    def align(segments,model,metadata,samples,device,return_char_alignments=False):
        calls['align']+=1
        return {'word_segments':[{'word':w[0],'start':w[1],'end':w[2]} if isinstance(w,(tuple,list)) else dict(w) for w in words]}
    whisperx.load_align_model=load_align_model;whisperx.align=align
    return {'torch':torch,'whisperx':whisperx,'nltk':nltk},calls

def write_wav(path,seconds,rate=16000):
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate)
        w.writeframes(b'\x00\x00'*int(seconds*rate))
    return Path(path)

@unittest.skipIf(numpy is None,'本机没有 numpy：WhisperX 对齐本身依赖它，跳过')
class AlignWhisperX(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.audio_file=self.root/'audio.mp3';self.audio_file.write_bytes(b'fake audio')
        self.cache=self.root/'cache';self.duration=10.0;self.wav_rate=16000
        for patcher in [patch.object(importlib.metadata,'version',return_value='3.8.6'),
                        patch.object(audio,'probe',side_effect=lambda path:self.duration),
                        patch.object(audio,'sha256',return_value=AUDIO_SHA),
                        patch.object(audio,'run',side_effect=self.fake_run),
                        patch.object(platform_tools,'ffmpeg_bin',return_value='ffmpeg')]:
            patcher.start();self.addCleanup(patcher.stop)
    def fake_run(self,command,timeout=None):
        write_wav(Path(command[-1]),self.duration,self.wav_rate);return ''
    def plan(self,segments,name='plan.json'):
        p=self.root/name;p.write_text(json.dumps({'segments':segments},ensure_ascii=False),encoding='utf-8');return p
    def run_align(self,plan,words=(('Hello',0.1,0.4),),out='transcript.json'):
        mods,calls=fake_modules(list(words))
        with patch.dict(sys.modules,mods):
            report=aligner.align(str(self.audio_file),str(plan),str(self.root/out),str(self.cache))
        return report,calls
    def refusal(self,plan):
        with patch.dict(sys.modules,fake_modules([])[0]):
            with self.assertRaises(ValueError) as caught:
                aligner.align(str(self.audio_file),str(plan),str(self.root/'never.json'),str(self.cache))
        return str(caught.exception)

    def test_missing_segments_array_is_explained(self):
        p=self.root/'bad.json';p.write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'segments 数组'):
            with patch.dict(sys.modules,fake_modules([])[0]):
                aligner.align(str(self.audio_file),str(p),str(self.root/'t.json'),str(self.cache))
    def test_empty_segments_points_at_the_workflow(self):
        message=self.refusal(self.plan([]))
        self.assertIn('先确认题组所在的实际时间窗',message);self.assertIn('whisperx-workflow.md',message)
    def test_missing_fields_and_wrong_types_are_named(self):
        cases=[({'start':1,'end':2,'text':'x'},'第 1 项 缺少 id'),
               ({'id':'L1','end':2,'text':'x'},'缺少 start'),
               ({'id':'L1','start':'1','end':2,'text':'x'},'必须是秒数'),
               ({'id':'L1','start':1,'end':2,'text':'  '},'缺少 text'),
               ({'id':'L1','start':1,'end':2,'text':['x']},'缺少 text')]
        for segment,expected in cases:
            with self.subTest(segment=segment):self.assertIn(expected,self.refusal(self.plan([segment])))
    def test_non_object_segment_is_explained(self):
        self.assertIn('不是对象',self.refusal(self.plan(['L1'])))
    def test_overlap_and_out_of_range_windows_refused(self):
        cases=[[{'id':'L1','start':1,'end':5,'text':'a'},{'id':'L2','start':4,'end':6,'text':'b'}],
               [{'id':'L1','start':0,'end':12,'text':'a'}]]
        for segments in cases:
            with self.subTest(segments=segments):self.assertIn('时间窗无效或与前一段重叠',self.refusal(self.plan(segments)))
    def test_alignment_text_change_requires_note(self):
        segment={'id':'L1','start':1,'end':3,'text':'£50','alignment_text':'fifty pounds'}
        self.assertIn('normalization_note',self.refusal(self.plan([segment])))
        segment['normalization_note']='按录音展开金额读法，原文不变'
        report,_=self.run_align(self.plan([segment],name='plan2.json'))
        self.assertEqual(report['segments'][0]['text'],'£50')
        self.assertEqual(report['segments'][0]['alignment_text'],'fifty pounds')

    def test_words_are_offset_into_audio_time_and_review_stays_pending(self):
        plan=self.plan([{'id':'L1','start':1.0,'end':3.0,'text':'Hello world.'}])
        report,_=self.run_align(plan,words=(('Hello',0.1,0.4),('world',0.5,0.9)))
        self.assertEqual(report['status'],'aligned_review_required');self.assertEqual(report['issues'],[])
        self.assertEqual(report['alignment_review'],'pending')
        self.assertEqual(report['source_audio_sha256'],AUDIO_SHA)
        self.assertEqual([(w['start'],w['end']) for w in report['segments'][0]['words']],[(1.1,1.4),(1.5,1.9)])
        self.assertIn('Original text retained',report['note'])
        saved=json.loads((self.root/'transcript.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['fingerprint'],report['fingerprint'])
    def test_invalid_word_times_become_issues_not_silent_success(self):
        plan=self.plan([{'id':'L1','start':1.0,'end':3.0,'text':'Hello'}])
        report,_=self.run_align(plan,words=(('Hello',5.0,1.0),))
        self.assertEqual(report['status'],'alignment_failed')
        self.assertEqual(report['issues'][0]['reason'],'missing_or_invalid_time')
        self.assertEqual(report['segments'][0]['words'],[])
    def test_no_aligned_words_is_recorded(self):
        plan=self.plan([{'id':'L1','start':1.0,'end':3.0,'text':'Hello'}])
        report,_=self.run_align(plan,words=())
        self.assertEqual(report['issues'],[{'id':'L1','reason':'no_aligned_words'}])
        self.assertEqual(report['status'],'alignment_failed')
    def test_wrong_wav_format_is_refused_with_reason(self):
        self.wav_rate=8000
        plan=self.plan([{'id':'L1','start':1.0,'end':3.0,'text':'Hello'}])
        with self.assertRaisesRegex(ValueError,'缓存的 WAV 格式不对'):self.run_align(plan)
    def test_same_fingerprint_reuses_without_reloading_model(self):
        plan=self.plan([{'id':'L1','start':1.0,'end':3.0,'text':'Hello'}])
        first,calls=self.run_align(plan,words=(('Hello',0.1,0.4),))
        self.assertEqual(calls,{'load':1,'align':1})
        second,again=self.run_align(plan,words=(('Hello',0.1,0.4),))
        self.assertEqual(again,{'load':0,'align':0},'同源同计划应直接复用，不重新加载模型')
        self.assertEqual(second['fingerprint'],first['fingerprint'])
        self.assertEqual(second['status'],'aligned_review_required')
    def test_plan_errors_come_before_the_environment_check(self):
        """计划写错时不该先报"没装 WhisperX"——否则老师会去装一个用不上的依赖（1.0.104，顺序已锁定）。"""
        plan=self.plan([{'start':1,'end':2,'text':'x'}])   # 缺 id
        mods,_=fake_modules([])
        with patch.dict(sys.modules,mods):
            with self.assertRaises(ValueError) as caught:
                aligner.align(str(self.audio_file),str(plan),str(self.root/'never.json'),str(self.cache))
        self.assertIn('缺少 id',str(caught.exception))
    def test_missing_whisperx_is_explained_in_chinese_with_an_alternative(self):
        plan=self.plan([{'id':'L1','start':1.0,'end':3.0,'text':'Hello'}])
        missing=type('PackageNotFoundError',(Exception,),{})
        with patch.object(importlib.metadata,'version',side_effect=missing('whisperx')),\
             patch.object(importlib.metadata,'PackageNotFoundError',missing):
            with self.assertRaises(ValueError) as caught:
                aligner.align(str(self.audio_file),str(plan),str(self.root/'never.json'),str(self.cache))
        message=str(caught.exception)
        self.assertIn('没有安装 WhisperX',message)
        self.assertIn('import_timed_text',message,'要给出"已有字幕就不用装"的替代路径')
        self.assertNotIn('No package metadata',message)
    def test_broken_plan_json_is_chinese(self):
        bad=self.root/'bad.json';bad.write_text('{oops',encoding='utf-8')
        with self.assertRaises(ValueError) as caught:
            aligner.align(str(self.audio_file),str(bad),str(self.root/'never.json'),str(self.cache))
        self.assertIn('不是合法 JSON',str(caught.exception))
    def test_cli_exit_code_is_two_when_issues_exist(self):
        plan=self.plan([{'id':'L1','start':1.0,'end':3.0,'text':'Hello'}])
        mods,_=fake_modules([{'word':'x','start':9.0,'end':1.0}])
        argv=['align_whisperx.py',str(self.audio_file),str(plan),'--out',str(self.root/'cli.json'),'--cache',str(self.cache)]
        with patch.dict(sys.modules,mods),patch.object(sys,'argv',argv),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:runpy.run_module('align_whisperx',run_name='__main__')
        self.assertEqual(caught.exception.code,2)
        self.assertTrue((self.root/'cli.json').is_file(),'异常也要留下对齐报告，不能只有退出码')
if __name__=='__main__':unittest.main()
