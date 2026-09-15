import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import listening_pipeline as lp,speech_runtime

class ListeningPipeline(unittest.TestCase):
    def test_intro_and_second_repeat_are_excluded(self):
        text='I bought a football in that new department store. It cost fifteen pounds.'
        exam={'sections':[{'id':'L1','kind':'listening','paragraphs':[{'id':'p','text':text}],'questions':[{'id':'1'}]}]}
        rows=[{'start':0,'end':15,'text':'现在听下面第一段录音'}, {'start':20,'end':30,'text':text},{'start':32,'end':42,'text':text}]
        r=lp.group_windows(exam,{'segments':rows},50);self.assertFalse(r['issues']);self.assertAlmostEqual(r['segments'][0]['start'],19.7);self.assertFalse(r['segments'][0]['verified'])
    def test_no_text_does_not_invent_windows(self):
        r=lp.group_windows({'sections':[{'id':'L1','kind':'listening','paragraphs':[]}]},{'segments':[]},40);self.assertTrue(r['issues']);self.assertFalse(r['segments'])
    def test_no_matching_text_stops(self):
        r=lp.group_windows({'sections':[{'id':'L1','kind':'listening','paragraphs':[{'text':'Something completely different.'}]}]},{'segments':[{'start':1,'end':4,'text':'Nothing matches today'}]},5);self.assertTrue(r['issues'])
    def test_question_preserves_whole_sentence_and_pending(self):
        words=[{'word':t,'start':i,'end':i+.5} for i,t in enumerate(['We','should','not','leave','until','nine.'])]
        exam={'sections':[{'id':'L1','questions':[{'id':'1','evidence':[{'quote':'until nine'}]}]}]}
        r=lp.question_contexts(exam,{'segments':[{'id':'L1','start':0,'end':6,'words':words}]})
        self.assertFalse(r['issues']);self.assertEqual(r['segments'][0]['context'],'We should not leave until nine.');self.assertFalse(r['segments'][0]['verified'])
    def test_ambiguous_evidence_stops(self):
        words=[{'word':w,'start':i,'end':i+.2} for i,w in enumerate(['nine','nine'])]
        r=lp.question_contexts({'sections':[{'id':'L1','questions':[{'id':'1','evidence':[{'quote':'nine'}]}]}]},{'segments':[{'id':'L1','start':0,'end':3,'words':words}]});self.assertTrue(r['issues'])
    def test_existing_timed_text_skips_runtime(self):
        with patch.object(speech_runtime,'probe',side_effect=AssertionError('must not probe')):
            self.assertEqual(speech_runtime.choose(timed_transcript=True)['backend'],'timed_transcript')
    def test_install_needs_authorization(self):
        with tempfile.TemporaryDirectory() as t,patch.object(speech_runtime,'probe',return_value={'status':'needs_setup'}),patch.object(speech_runtime,'run',side_effect=AssertionError('must not install')):
            self.assertEqual(speech_runtime.prepare(Path(t)/'venv')['status'],'awaiting_install_approval')
    def test_venv_executable_not_resolved_out_of_environment(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'python';p.write_text('fixture')
            with patch.object(Path,'resolve',side_effect=AssertionError('must not resolve venv symlinks')):
                self.assertIn(str(p),speech_runtime.candidates(str(p)))
