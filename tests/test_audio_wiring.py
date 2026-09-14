import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import audio_wiring,section_kinds

_OMIT=object()  # 表示"这个字段整个不写"，与写成 null 是两种输入

def make_wav(path,seconds=6.0):
    """真实的小 WAV：wire_audio 只做指纹与路径，不需要 ffmpeg。"""
    import wave
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\x00\x00'*int(seconds*8000))
    return path

class Fixture:
    def __init__(self,root):
        self.root=Path(root);self.src=self.root/'paper';self.src.mkdir(parents=True,exist_ok=True)
        self.bundle=self.src/'audio-work';self.bundle.mkdir(parents=True,exist_ok=True)
        self.full=make_wav(self.bundle/'full.wav',6.0)
        self.full_sha=audio_wiring.sha256(self.full)
    def segments(self,segments,verification_mode='verified',kind='text',full_audio='full.wav',name='segments.json'):
        data={'kind':kind,'source_audio_sha256':self.full_sha,'full_audio':full_audio,'segments':segments}
        if verification_mode is not _OMIT:data['verification_mode']=verification_mode
        (self.bundle/name).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');return data
    def transcript(self,same_audio=True,name='transcript.json'):
        payload={'source_audio_sha256':self.full_sha if same_audio else 'f'*64,'duration':6.0,
                 'segments':[{'start':0.0,'end':2.4,'text':'Hello there.'},{'start':2.4,'end':6.0,'text':'Nice to meet you.'}]}
        p=self.bundle/name;p.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8');return p
    def clip(self,name,seconds=2.4):
        return make_wav(self.bundle/name,seconds)
    def exam(self,questions='[{"id":"1","stem":"q"}]'):
        return {'title':'t','sections':[{'id':'L1','kind':'listening','title':'Text 1','questions':json.loads(questions)}]}

class WireAudio(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.f=Fixture(self.tmp.name)
        self.f.clip('L1.mp3')
    def wire(self,d=None,directory=None):
        return audio_wiring.wire_audio(d if d is not None else self.f.exam(),self.f.src,directory if directory is not None else self.f.bundle)

    def test_clip_is_wired_with_relative_path_and_verified_boundary(self):
        self.f.segments([{'id':'L1','audio':'L1.mp3','duration':2.4,'start':0.0,'end':2.4,'verified':True,'opening_quote':'Hello there.','closing_quote':'Nice to meet you.'}])
        tr=self.f.transcript();d=self.f.exam();report=self.wire(d)
        section=d['sections'][0]
        self.assertEqual(section['audio'],'audio-work/L1.mp3')
        self.assertEqual(section['audio_scope'],'text');self.assertEqual(section['audio_duration'],2.4)
        self.assertEqual(section['audio_alignment']['boundary'],'verified')
        self.assertEqual(section['audio_alignment']['mode'],'verified')
        self.assertEqual(section['audio_alignment']['full_start'],0.0)
        self.assertEqual(section['audio_alignment']['transcript_file'],'audio-work/transcript.json')
        self.assertEqual(section['audio_alignment']['transcript_sha256'],audio_wiring.sha256(tr))
        self.assertEqual(d['full_audio'],'audio-work/full.wav')
        self.assertEqual(report['pending'],[]);self.assertEqual(report['mode'],'verified')
        self.assertEqual(report['sections'][0]['mode'],'text_clip')
    def test_unverified_segment_is_marked_and_pending(self):
        self.f.segments([{'id':'L1','audio':'L1.mp3','duration':2.4,'start':0.0,'end':2.4,'verified':False}],verification_mode='auto_silence')
        d=self.f.exam();report=self.wire(d)
        self.assertEqual(d['sections'][0]['audio_alignment']['boundary'],'auto_silence')
        self.assertTrue(any('静音自动分段' in x for x in report['pending']))
        self.assertTrue(any('qa-report' in x for x in report['pending']))
    def test_missing_verification_mode_is_not_replaced_by_verified(self):
        """清单整个不写 mode 时不许凭空补 verified——页面靠它判断是否标「边界待核对」。"""
        self.f.segments([{'id':'L1','audio':'L1.mp3','duration':2.4,'start':0.0,'end':2.4,'verified':True}],verification_mode=_OMIT)
        d=self.f.exam();report=self.wire(d)
        alignment=d['sections'][0]['audio_alignment']
        self.assertNotIn('mode',alignment)
        self.assertEqual(alignment['boundary'],'verified')
        self.assertTrue(any('verification_mode' in x for x in report['pending']))
    def test_transcript_from_another_recording_is_never_attached(self):
        self.f.segments([{'id':'L1','audio':'L1.mp3','duration':2.4,'start':0.0,'end':2.4,'verified':True}])
        self.f.transcript(same_audio=False)
        d=self.f.exam();report=self.wire(d)
        self.assertNotIn('transcript_file',d['sections'][0]['audio_alignment'])
        self.assertTrue(any('source_audio_sha256 不匹配' in x for x in report['pending']),report['pending'])
    def test_missing_full_audio_does_not_guess_a_transcript(self):
        self.f.segments([{'id':'L1','audio':'L1.mp3','duration':2.4,'start':0.0,'end':2.4,'verified':True}],full_audio='gone.wav')
        self.f.transcript()
        d=self.f.exam();report=self.wire(d)
        self.assertNotIn('transcript_file',d['sections'][0]['audio_alignment'])
        self.assertNotIn('full_audio',d)
        self.assertTrue(any('整卷原音不在磁盘上' in x for x in report['pending']),report['pending'])
    def test_transcript_without_source_hash_is_not_attached_when_audio_is_missing(self):
        """没有 source_audio_sha256 的转写最容易误命中：算不出指纹时 None==None 会把它当同源，必须拒绝。"""
        self.f.segments([{'id':'L1','audio':'L1.mp3','duration':2.4,'start':0.0,'end':2.4,'verified':True}],full_audio='gone.wav')
        (self.f.bundle/'transcript.json').write_text(json.dumps({'segments':[{'start':0,'end':1,'text':'x'}]}),encoding='utf-8')
        d=self.f.exam();report=self.wire(d)
        self.assertNotIn('transcript_file',d['sections'][0]['audio_alignment'])
        self.assertTrue(any('整卷原音不在磁盘上' in x for x in report['pending']),report['pending'])
    def test_already_wired_sections_are_left_alone(self):
        self.f.segments([{'id':'L1','audio':'L1.mp3','duration':2.4,'start':0.0,'end':2.4,'verified':True}])
        d=self.f.exam();d['sections'][0]['audio']='teacher/mine.mp3'
        report=self.wire(d)
        self.assertEqual(d['sections'][0]['audio'],'teacher/mine.mp3')
        self.assertEqual(report['sections'],[],'已接好音频的节不再改写，quality_gate 也不会重复注入')
    def test_full_paper_fallback_names_the_reason(self):
        self.f.segments([{'id':'L9','audio':'L9.mp3','duration':2.4,'start':0.0,'end':2.4,'verified':True}])
        d=self.f.exam();d['sections'].append({'id':'L2','kind':'listening','title':'Text 2','questions':[{'id':'2','stem':'q2'}]})
        report=self.wire(d)
        section=d['sections'][0]
        self.assertEqual(section['audio'],'audio-work/full.wav');self.assertEqual(section['audio_scope'],'full_paper')
        self.assertEqual(section['audio_alignment'],{'mode':'unsegmented','boundary':'not_split'})
        self.assertTrue(any('未分段' in x for x in report['pending']))
        self.assertEqual([x['mode'] for x in report['sections']],['full_paper','full_paper'])
    def test_single_listening_section_falls_back_to_the_only_segment(self):
        self.f.segments([{'id':'TEXT-A','audio':'L1.mp3','duration':2.4,'start':0.0,'end':2.4,'verified':True}])
        d=self.f.exam();report=self.wire(d)
        self.assertEqual(d['sections'][0]['audio'],'audio-work/L1.mp3')
        self.assertEqual(report['sections'][0]['mode'],'text_clip')
    def test_question_clips_get_context_relative_to_the_text_clip(self):
        self.f.segments([{'id':'L1','audio':'L1.mp3','duration':2.4,'start':1.0,'end':3.4,'verified':True}])
        qdir=self.f.bundle/'questions';qdir.mkdir(exist_ok=True);make_wav(qdir/'Q1.mp3',1.2)
        (qdir/'segments.json').write_text(json.dumps({'kind':'question','full_audio':'full.wav','source_audio_sha256':self.f.full_sha,
            'verification_mode':'verified','segments':[{'id':'Q1','audio':'Q1.mp3','duration':1.2,'start':2.0,'end':3.2,'verified':True,
            'question_ids':['1'],'evidence':'第1题所需语境'}]},ensure_ascii=False),encoding='utf-8')
        d=self.f.exam();report=self.wire(d)
        q=d['sections'][0]['questions'][0]
        self.assertEqual(q['audio'],'audio-work/questions/Q1.mp3');self.assertEqual(q['audio_duration'],1.2)
        self.assertEqual(q['audio_context']['text_id'],'L1')
        self.assertEqual(q['audio_context']['start'],1.0,'题目切片要换成本文段内的相对时间')
        self.assertEqual(q['audio_context']['end'],2.2)
        self.assertEqual(q['audio_context']['selection_reason'],'第1题所需语境')
        self.assertEqual(report['questions_with_clip'],1)
    def test_question_clip_without_text_bundle_starts_at_zero(self):
        """只有逐题切片、没有整段清单时，题目时间要相对切片自身（不是 30s 处的绝对时间）。"""
        solo=self.f.src/'audio-q';qdir=solo/'questions';qdir.mkdir(parents=True)
        make_wav(qdir/'Q1.mp3',1.0)
        (qdir/'segments.json').write_text(json.dumps({'kind':'question','segments':[{'id':'Q1','audio':'Q1.mp3','duration':1.0,
            'start':30.0,'end':31.0,'question_ids':['1']}]},ensure_ascii=False),encoding='utf-8')
        d=self.f.exam();audio_wiring.wire_audio(d,self.f.src,solo)
        q=d['sections'][0]['questions'][0]
        self.assertEqual(q['audio_context']['start'],0.0);self.assertEqual(q['audio_context']['end'],1.0)
        self.assertEqual(q['audio_context']['selection_reason'],'按题意保留本题所需完整语境')
        self.assertEqual(q['audio'],'audio-q/questions/Q1.mp3')
    def test_non_listening_sections_are_not_touched(self):
        self.f.segments([{'id':'L1','audio':'L1.mp3','duration':2.4,'start':0.0,'end':2.4,'verified':True}])
        d=self.f.exam();d['sections'].append({'id':'R1','kind':'reading','title':'阅读','questions':[{'id':'2','stem':'r'}]})
        self.wire(d)
        self.assertNotIn('audio',d['sections'][1])
    def test_rel_handles_a_different_drive_like_windows(self):
        with patch.object(audio_wiring.os.path,'relpath',side_effect=ValueError('different drives')):
            result=audio_wiring.rel('D:/audio/L1.mp3','C:/paper')
        self.assertTrue(result.endswith('D:/audio/L1.mp3'),result)
        self.assertNotIn('\\\\',result,'跨盘时应给绝对路径且统一成正斜杠')
        self.assertEqual(audio_wiring.rel('/a/b/L1.mp3','/a'),'b/L1.mp3')
    def test_bundle_dir_prefers_explicit_and_refuses_missing(self):
        self.assertEqual(audio_wiring.bundle_dir(self.f.src,str(self.f.bundle)),self.f.bundle.resolve())
        with self.assertRaisesRegex(AssertionError,'音频目录不存在'):audio_wiring.bundle_dir(self.f.src,str(self.f.src/'nope'))
        self.f.segments([{'id':'L1','audio':'L1.mp3','duration':1.0,'start':0,'end':1,'verified':True}])
        self.assertEqual(audio_wiring.bundle_dir(self.f.src),self.f.bundle,'未指定时按 audio-work/audio-out 等约定自动识别')
    def test_wrong_segment_kind_is_refused(self):
        self.f.segments([{'id':'L1','audio':'L1.mp3','duration':1.0,'start':0,'end':1,'verified':True}],kind='question')
        with self.assertRaisesRegex(AssertionError,'不是 text 类型的切段清单'):self.wire()
    def test_quality_gate_flags_a_missing_boundary(self):
        """页面只在 auto_silence/未分段时标「边界待核对」，所以 boundary 必须写明。"""
        import quality_gate
        d={'sections':[{'id':'L1','kind':'listening','audio':'L1.mp3','audio_duration':2.4,
                        'audio_alignment':{'mode':'text','full_start':0.0,'full_end':2.4}}]}
        report=quality_gate.audit_exam(d,self.f.src)
        codes=[e['code'] for e in report['errors']]
        self.assertIn('audio_alignment_boundary_missing',codes,report['errors'])
        self.assertTrue(any('boundary' in e['message'] for e in report['errors']))
    def test_quality_gate_does_not_require_boundary_for_unsegmented(self):
        import quality_gate
        d={'sections':[{'id':'L1','kind':'listening','audio':'full.wav','audio_duration':6.0,
                        'audio_alignment':{'mode':'unsegmented','boundary':'not_split'}}]}
        report=quality_gate.audit_exam(d,self.f.src)
        self.assertNotIn('audio_alignment_boundary_missing',[e['code'] for e in report['errors']])
if __name__=='__main__':unittest.main()
