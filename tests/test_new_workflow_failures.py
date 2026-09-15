"""Exercise rejected states, without certifying fixture content as real teaching review."""
import copy,contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'tests'))
import listening_pipeline as lp, teaching_review as tr, speech_worker, speech_runtime, task_contract, build
from test_task_contract_new import NewTaskContract
from test_teaching_review_new import SemanticReview

class BuildFailures(unittest.TestCase):
    setUp=NewTaskContract.setUp
    def test_conflicting_plan_rebuild(self):
        with self.assertRaisesRegex(ValueError,'新计划与 --rebuild-from 只能选一个'):build.build(self.src,self.out,self.l,plan=self.plan,rebuild_from=self.root)
    def test_overriding_profile(self):
        with self.assertRaisesRegex(ValueError,'不要用额外参数覆盖教师已确认的范围'):build.build(self.src,self.out,self.l,plan=self.plan,profile='quick')
    def test_pending_public_review(self):
        r=self.root/'r.json';r.write_text(json.dumps(tr.draft(json.loads(self.src.read_text(encoding='utf-8')))))
        with self.assertRaisesRegex(ValueError,'内容复核未完成'):build.build(self.src,self.out,self.l,plan=self.plan,review=r)
    def test_empty_materials(self):
        with self.assertRaisesRegex(ValueError,'新建课件必须登记本次材料'):task_contract.material_records([])

class SourceFailures(unittest.TestCase):
    setUp=SemanticReview.setUp
    reviewed=SemanticReview.reviewed
    def test_snapshot_claim_gates(self):
        text='This archived source paragraph is long enough for this synthetic test.'
        snap={'url':'https://example.invalid','retrieved_at':'2026-09-15','text':text,'text_sha256':tr.fingerprint(text),'status':'retrieved'}
        source={'url':snap['url'],'snapshot':'s.json','excerpt':text,'supports':'source claim'}
        cases=[('retrieved_at','',None,'来源地址或检索日期不符'),('text_sha256','wrong',None,'来源正文指纹不符'),('status','failed',None,'来源未成功抓取'),(None,None,{'excerpt':'fabricated source quotation'},'excerpt 未逐字来自已抓取正文'),(None,None,{'supports':''},'未说明来源支持哪条事实')]
        for key,value,change,message in cases:
            with self.subTest(message=message):
                a=copy.deepcopy(snap);b=copy.deepcopy(source)
                if key:a[key]=value
                if change:b.update(change)
                (self.base/'s.json').write_text(json.dumps(a));self.s['culture_background']=[{'title':'fixture','sources':[b]}]
                self.assertIn(message,'\n'.join(tr.validate(self.exam,self.reviewed(),self.base)['errors']))
    def test_capture_rejects_too_large_or_inaccessible_page(self):
        for raw,message in [(b'x'*3000001,'来源超过3MB，请改用具体资料页'),(b'<p>login</p>','来源正文不足，请核对是否被登录或访问限制拦截')]:
            response=Mock();response.read.return_value=raw;response.headers.get_content_charset.return_value='utf-8';response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            with patch.object(tr.urllib.request,'urlopen',return_value=response),self.assertRaisesRegex(ValueError,message):tr.capture('https://example.invalid',self.base/'out.json')
    def test_review_cli_required_paths(self):
        for cmd,message in [('check','请用 --review 指定复核记录'),('draft','请用 --out 指定待复核清单路径')]:
            err=io.StringIO()
            with patch.object(sys,'argv',['review',cmd,str(ROOT/'examples/demo-reading.json')]),contextlib.redirect_stderr(err),self.assertRaises(SystemExit):tr.main()
            self.assertIn(message,err.getvalue())

class AudioFailures(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.exam=self.root/'exam.json';self.exam.write_text(json.dumps({'sections':[]}));self.tr=self.root/'tr.json';self.tr.write_text(json.dumps({'source_audio_sha256':'same','segments':[{'start':0,'end':3,'text':'Hello there.'}]}))
        self.args=SimpleNamespace(out=str(self.root/'out'),audio='fixture.wav',exam=str(self.exam),transcript=str(self.tr),python=None,cache=str(self.root/'cache'),model='base.en',seconds=5,windows=None)
    def test_transcript_binding_and_bounds(self):
        for change,msg in [({'source_audio_sha256':'other'},'已有转写不是本次原音，禁止复用'),({'segments':[{'start':0,'end':100}]},'已有转写时间无效或超出原音')]:
            self.tr.write_text(json.dumps({'source_audio_sha256':'same','segments':[{'start':0,'end':3,'text':'ok'}],**change}))
            with patch.object(lp,'sha256',return_value='same'),patch.object(lp,'probe',return_value=20),self.assertRaisesRegex(ValueError,msg):lp.execute(self.args)
    def test_override_windows_bound_to_audio(self):
        win=self.root/'windows.json';win.write_text(json.dumps({'source_audio_sha256':'other'}));self.args.windows=str(win)
        with patch.object(lp,'sha256',return_value='same'),patch.object(lp,'probe',return_value=20),self.assertRaisesRegex(ValueError,'人工修订窗口属于另一份原音'):lp.execute(self.args)
    def test_failed_smoke_preparation_stops(self):
        self.args.transcript=None
        with patch.object(lp,'sha256',return_value='same'),patch.object(lp,'probe',return_value=20),patch.object(lp,'runtime_probe',return_value={'status':'package_ready','python':sys.executable}),patch.object(lp,'run',return_value=(1,'','ffmpeg failure')),self.assertRaisesRegex(ValueError,'短音频准备失败'):lp.execute(self.args)
    def manifest(self):
        return {'source_audio_sha256':'same','expected_group_ids':['L1'],'expected_question_ids':['1'],'issues':[], 'segments':[{'id':'L1','question_ids':['1'],'verified':True,'evidence':'仅供裁剪闸门单元测试使用的合成核对记录。'}, {'id':'Q1','group_id':'L1','question_ids':['1'],'verified':True,'evidence':'仅供裁剪闸门单元测试使用的合成核对记录。'}]}
    def test_final_cut_rejections(self):
        cases=[('sha','切片清单与本次原音不符'),('missing','已核对清单遗漏题组或题号'),('issues','切片清单还有未解决问题'),('unreviewed','尚未记录实际试听与题意核对'),('empty_questions','缺少整段或逐题清单')]
        for change,message in cases:
            m=self.manifest()
            if change=='sha':m['source_audio_sha256']='wrong'
            if change=='missing':m['expected_question_ids'].append('2')
            if change=='issues':m['issues']=['needs correction']
            if change=='unreviewed':m['segments'][0]['verified']=False
            if change=='empty_questions':m['segments']=m['segments'][:1];m['expected_question_ids']=[]
            p=self.root/'manifest.json';p.write_text(json.dumps(m));self.args.manifest=str(p);self.args.transcript=None
            with self.subTest(change=change),patch.object(lp,'sha256',return_value='same'),patch.object(lp,'cut',return_value={}),self.assertRaisesRegex(ValueError,message):lp.finalize(self.args)
    def test_group_and_question_cuts_are_separate(self):
        p=self.root/'manifest.json';p.write_text(json.dumps(self.manifest()));self.args.manifest=str(p);self.args.transcript=None
        with patch.object(lp,'sha256',return_value='same'),patch.object(lp,'cut',return_value={}) as cut:
            result=lp.finalize(self.args)
        self.assertEqual(result['status'],'cuts_verified_by_record');self.assertEqual(cut.call_count,2)
        self.assertEqual(Path(cut.call_args_list[1].args[0].out).name,'questions')
    def test_cli_missing_input_and_budget(self):
        for extra,message in [(['--seconds','0'],'运行预算须为1–3600秒'),([], '请用 --exam 提供本次听力原文与题目'),(['--exam',str(self.exam)],'听力处理前请先记录老师的选择')]:
            err=io.StringIO()
            with patch.object(sys,'argv',['pipeline','run','--audio','x','--out',str(self.root),*extra]),contextlib.redirect_stderr(err),self.assertRaises(SystemExit):lp.main()
            self.assertIn(message,err.getvalue())
    def test_cli_material_and_selected_scope(self):
        plan=self.root/'plan.json';plan.write_text('{}')
        for materials,exam,message in [([],{'sections':[]},'原音未绑定本次已确认计划'),([{'role':'audio','sha256':'same'}],{'sections':[]},'老师本次未选择听力')]:
            err=io.StringIO()
            with patch.object(sys,'argv',['pipeline','run','--audio','x','--out',str(self.root),'--exam',str(self.exam),'--plan',str(plan),'--source-ledger','x']),patch.object(task_contract,'validate',return_value={'materials':materials}),patch('preferences.apply_plan',return_value=exam),patch.object(lp,'sha256',return_value='same'),contextlib.redirect_stderr(err),self.assertRaises(SystemExit):lp.main()
            self.assertIn(message,err.getvalue())
    def test_failed_resource_download_stops(self):
        nltk=Mock();nltk.download.return_value=False
        with patch.dict(sys.modules,{'torch':Mock(),'whisperx':Mock(),'nltk':nltk}),patch.object(sys,'argv',['worker','--prepare-resources','--cache',str(self.root/'cache')]),self.assertRaisesRegex(ValueError,'分句资源下载失败'):speech_worker.main()
    def test_setup_error_is_preserved_and_not_retried(self):
        with patch.object(speech_runtime,'probe',return_value={'status':'needs_setup'}),patch.object(speech_runtime,'run',return_value=(1,'partial','Permission denied full error')) as run:
            result=speech_runtime.prepare(self.root/'env',approved=True)
        self.assertEqual(result['stderr'],'Permission denied full error');self.assertEqual(run.call_count,1);self.assertTrue(result['command'])

del NewTaskContract,SemanticReview
if __name__=='__main__':unittest.main()
