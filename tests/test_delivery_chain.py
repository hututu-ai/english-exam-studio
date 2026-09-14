"""Every supported configuration must survive the whole delivery chain.

1.0.37 added multi-page source images but only `verify_output` learned about them, so
every such lesson was refused by package_lesson with "缺少与当前 HTML 对应的浏览器
点击验收" — a whole feature that could never be delivered. Verifying one link is not
enough: each configuration here is built, template-verified, given browser evidence and
packaged, so a mismatch between the tools shows up as a failing configuration.
"""
import contextlib,hashlib,io,json,os,shutil,struct,subprocess,sys,tempfile,unittest,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build
from verify_output import verify_output
from package_lesson import package
from preferences import DEFAULTS

def png(path,width,height,color):
    raw=b''.join(b'\x00'+bytes(color)*width for _ in range(height))
    def chunk(tag,data):
        import binascii
        return struct.pack('>I',len(data))+tag+data+struct.pack('>I',binascii.crc32(tag+data)&0xffffffff)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))

def make_qa_report(out):
    """交付同时要求已完成的人工复核清单；用工具自身的模板生成并填好结论。"""
    import re
    from qa_report import collect,render
    items,report,_=collect(out)
    text=re.sub(r'—— 结论：$','—— 结论：单元测试夹具已逐条核对。',render(items,report),flags=re.M)
    (Path(out)/'qa-report.md').write_text(text,encoding='utf-8')

class DeliveryChainTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def write(self,path,value):
        Path(path).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');return Path(path)
    def read(self,path):return json.loads(Path(path).read_text(encoding='utf-8'))
    def ledger_for(self,source):
        data=self.read(source)
        return self.write(self.root/'source-ledger.json',
            {'sources':[{'role':'original_demo','path':Path(source).name,'sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest()}],
             'sections':data['sections']})
    def deliver(self,name,source,out,ledger,**kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            build.build(source,out,ledger,**kwargs)
        verified=verify_output(out)
        self.assertEqual(verified['status'],'passed',f'{name}: template verification failed')
        page=(out/'index.html').read_bytes()
        self.write(out/'browser-check.json',{'status':'passed','engine':'unit-test-fixture',
            'html_sha256':hashlib.sha256(page).hexdigest(),'media_sha256':verified['resource_sha256'],
            'checks':[{'name':'fixture','status':'passed'}],'skipped':[],'errors':[]})
        make_qa_report(out)
        result=package(out,self.root/f'{name}.zip')
        self.assertEqual(result['status'],'browser_checked',f'{name}: packaging refused the lesson')
        self.assertTrue((self.root/f'{name}.zip').is_file())
        return result
    def demo(self,transform=None):
        data=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
        if transform:transform(data)
        return self.write(self.root/'exam.json',data)
    def plan(self,features,profile=None,sections='all'):
        payload={'confirmed':True,'sections':sections,'mode':'lesson','features':features}
        if profile:payload['profile']=profile
        return self.write(self.root/'plan.json',payload)
    def test_default_configuration_delivers(self):
        source=self.demo()
        self.deliver('default',source,self.root/'out-default',self.ledger_for(source))
    def test_all_features_off_delivers(self):
        source=self.demo()
        plan=self.plan({key:False for key in DEFAULTS})
        self.deliver('features-off',source,self.root/'out-off',self.ledger_for(source),plan=plan)
    def test_quick_profile_delivers(self):
        source=self.demo()
        self.deliver('quick',source,self.root/'out-quick',self.ledger_for(source),profile='quick')
    def test_full_dictionary_scope_delivers(self):
        source=self.demo()
        self.deliver('dict-full',source,self.root/'out-dict',self.ledger_for(source),dictionary_scope='full')
    def test_multi_page_source_images_deliver(self):
        png(self.root/'page-2.png',80,120,(20,20,20));png(self.root/'page-3.png',80,120,(60,60,60))
        def add_origin(data):
            data['sections'][0]['origin']={'exam_page':2,'page_images':['page-2.png','page-3.png'],'publication_status':'未确认原始出版来源'}
        source=self.demo(add_origin)
        result=self.deliver('multi-page',source,self.root/'out-multi',self.ledger_for(source))
        report=self.read(self.root/'out-multi'/'delivery-report.json')
        self.assertEqual(report['browser_checks'],{'passed':1,'skipped':0})
        self.assertEqual(result['status'],'browser_checked')
    def test_listening_only_intensive_delivers(self):
        # 用户明确要过“只要听力”：整卷里只保留听力 Text，并走完整交付链。
        fixture=self.root/'fixture'
        made=subprocess.run([sys.executable,str(ROOT/'tests/make_browser_fixture.py'),str(fixture),str(self.root/'seed')],
                            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        self.assertEqual(made.returncode,0,made.stderr)
        source=fixture/'exam.json';ledger=fixture/'source-ledger.json'
        out=self.root/'out-listening'
        with contextlib.redirect_stdout(io.StringIO()):
            build.build(source,out,ledger,selection='L1',mode='intensive',audio_mode='folder')
        scope=self.read(out/'exam.json')
        self.assertEqual([s['id'] for s in scope['sections']],['L1'])
        self.assertEqual(scope['generation_scope']['mode'],'intensive')
        self.assertEqual(scope['audio_delivery']['mode'],'folder')
        verified=verify_output(out)
        self.assertEqual(verified['status'],'passed')
        page=(out/'index.html').read_bytes()
        self.write(out/'browser-check.json',{'status':'passed','engine':'unit-test-fixture',
            'html_sha256':hashlib.sha256(page).hexdigest(),'media_sha256':verified['resource_sha256'],
            'checks':[{'name':'fixture','status':'passed'}],'skipped':[],'errors':[]})
        make_qa_report(out)
        self.assertEqual(package(out,self.root/'listening.zip')['status'],'browser_checked')
    def test_browser_checker_and_verification_fingerprint_the_same_media(self):
        # 跨工具契约：两边收集的媒体必须完全一致，否则 package_lesson 会永远拒绝交付
        # （1.0.37 的多页页图就是这样整类课件交付不出去）。不需要 Playwright——
        # 浏览器脚本在启动浏览器之前就算好了 media_sha256。
        node=shutil.which('node')
        if not node:self.skipTest('node 不可用，跳过跨工具媒体一致性实测')
        png(self.root/'page-2.png',80,120,(20,20,20));png(self.root/'page-3.png',80,120,(60,60,60))
        data=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
        data['sections'][0]['origin']={'exam_page':2,'page_images':['page-2.png','page-3.png'],'publication_status':'未确认原始出版来源'}
        source=self.write(self.root/'exam.json',data)
        out=self.root/'out-shared'
        with contextlib.redirect_stdout(io.StringIO()):build.build(source,out,self.ledger_for(source))
        environment={key:value for key,value in os.environ.items() if key!='PLAYWRIGHT_MODULE'}
        subprocess.run([node,str(ROOT/'scripts/browser_check.cjs'),str(out)],capture_output=True,
                       text=True,encoding='utf-8',errors='replace',timeout=60,env=environment)
        evidence=json.loads((out/'browser-check.json').read_text(encoding='utf-8'))
        self.assertEqual(sorted(evidence.get('media_sha256',{})),sorted(verify_output(out)['resource_sha256']),
                         '浏览器验收与模板核验必须指纹同一组媒体，否则交付门槛会拒绝整类课件')
    def chrome_binary(self):
        candidates=[os.environ.get('CHROME_BIN'),'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',shutil.which('google-chrome'),
                    shutil.which('chromium'),shutil.which('microsoft-edge')]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():return candidate
        return None
    def test_a_plan_made_by_the_tool_delivers(self):
        # plan.py 的输出必须能直接被构建接受（弱宿主靠它走编号清单回退），并走完整交付链。
        source=self.demo()
        plan_path=self.root/'generated-plan.json'
        made=subprocess.run([sys.executable,str(ROOT/'scripts/plan.py'),'make','--confirmed','--range','B',
                             '--features','1,3,5','--out',str(plan_path)],
                            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        self.assertEqual(made.returncode,0,made.stderr)
        result=self.deliver('plan-tool',source,self.root/'out-plan',self.ledger_for(source),plan=plan_path)
        self.assertEqual(result['status'],'browser_checked')
        written=self.read(self.root/'out-plan'/'exam.json')
        self.assertEqual([key for key,value in written['features'].items() if value],['annotations','quick_answers','deep_reading'])
    def test_an_ordinary_lesson_passes_the_real_browser_check(self):
        # 1.0.37 曾把"夹具必须带多页"写成通用断言，导致任何普通课件（无页图）验收直接失败。
        # 这条用真实浏览器跑一次最普通的课件，确保它仍然能被接受。
        node=shutil.which('node')
        if not node:self.skipTest('node 不可用')
        module=os.environ.get('PLAYWRIGHT_MODULE','playwright')
        probe=subprocess.run([node,'-e',f"try{{require({module!r})}}catch(e){{process.exit(3)}}"],capture_output=True,timeout=60)
        if probe.returncode!=0:self.skipTest('Playwright 不可用，跳过真实浏览器验收')
        chrome=self.chrome_binary()
        if not chrome:self.skipTest('没有可用的 Chrome/Edge，跳过真实浏览器验收')
        source=self.demo()
        out=self.root/'out-plain'
        with contextlib.redirect_stdout(io.StringIO()):build.build(source,out,self.ledger_for(source))
        environment={**os.environ,'CHROME_BIN':chrome,'BROWSER_ENGINE':'chromium'}
        result=subprocess.run([node,str(ROOT/'scripts/browser_check.cjs'),str(out),'--stress'],capture_output=True,
                              text=True,encoding='utf-8',errors='replace',timeout=300,env=environment)
        evidence=json.loads((out/'browser-check.json').read_text(encoding='utf-8'))
        self.assertEqual(evidence['status'],'passed',result.stdout[-1500:]+result.stderr[-500:])
        self.assertEqual([item['name'] for item in evidence['skipped']].count('multi-page-origin-renders-every-page'),1,
                         'a lesson without multi-page images must skip that check, not fail')
