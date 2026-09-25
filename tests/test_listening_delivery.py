import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from listening_delivery import check
from audio_wiring import wire_audio
class ListeningDelivery(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
  (self.base/'g.mp3').write_bytes(b'group');(self.base/'q.mp3').write_bytes(b'question')
  self.s={'id':'L1','kind':'listening','audio':'g.mp3','audio_scope':'text','audio_alignment':{'mode':'manual','boundary':'verified'},'questions':[{'id':'1','audio':'q.mp3','audio_context':{'selection_reason':'完整答案语境'}}]}
 def test_segmented(self):self.assertEqual(check({'sections':[self.s]}, {},self.base)['status'],'segmented')
 def test_full_recording_is_not_success(self):
  self.s['audio_scope']='full_paper'
  with self.assertRaisesRegex(ValueError,'听力分段尚未完成'):check({'sections':[self.s]}, {},self.base)
 def test_missing_question_is_blocked(self):
  self.s['questions'][0].pop('audio')
  with self.assertRaisesRegex(ValueError,'缺少逐题语境音频'):check({'sections':[self.s]}, {},self.base)
 def test_duplicate_recording_is_blocked(self):
  b=copy.deepcopy(self.s);b['id']='L2'
  with self.assertRaisesRegex(ValueError,'相同录音内容'):check({'sections':[self.s,b]}, {},self.base)
 def test_downgrade_requires_teacher(self):
  with self.assertRaisesRegex(ValueError,'降低听力分段要求须记录老师本次明确同意'):check({'sections':[self.s]},{'listening_delivery':{'mode':'full_recording'}},self.base)
 def test_intensive_cannot_be_downgraded(self):
  with self.assertRaisesRegex(ValueError,'精听任务不能降级'):check({'sections':[self.s]},{'mode':'intensive','listening_delivery':{'mode':'groups','confirmed':True,'teacher_response':'只要题组'}},self.base)
 def test_invalid_mode(self):
  with self.assertRaisesRegex(ValueError,'听力交付模式无效'):check({'sections':[self.s]},{'listening_delivery':{'mode':'foo'}},self.base)
 def test_explicit_full_is_labelled(self):self.assertEqual(check({'sections':[self.s]},{'listening_delivery':{'mode':'full_recording','confirmed':True,'teacher_response':'我暂时只需要完整录音'}},self.base)['status'],'teacher_approved_full_recording')
 def test_completed_bundle_replaces_previous_fallback(self):
  bundle=self.base/'audio-work';bundle.mkdir();(bundle/'seg.mp3').write_bytes(b'cut')
  (bundle/'segments.json').write_text(json.dumps({'kind':'text','full_audio':str(self.base/'g.mp3'),'verification_mode':'manual','segments':[{'id':'L1','audio':'seg.mp3','duration':2,'start':3,'end':5,'verified':True,'question_ids':['1']}]}))
  self.s.update(audio_scope='full_paper',audio_alignment={'mode':'unsegmented'})
  d={'sections':[self.s]};wire_audio(d,self.base,bundle)
  self.assertEqual(self.s['audio_scope'],'text');self.assertEqual(self.s['audio'],'audio-work/seg.mp3')
