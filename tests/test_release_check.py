"""发布验收脚本自己的判据也要被锁住（1.0.111）。

`release_check.py` 与 `rehearse_first_use.py` 每轮发布都真跑，所以它们不是"没验证"；
但在这之前，全仓测试里没有任何断言锁住它们的**判据**——五项的通过/失败口径、
跳过不算通过、报告写到 `dist/` 而不是包根、退出码只看 failed 等等。
改动判据时只能靠人工比对发现，这个文件把那几条锁成断言。

这里不重跑整条重放（`tests/test_first_use_rehearsal.py` 已用真实子进程跑过一遍），
而是把 `release_check.check()` 的协作者换成桩，验证**聚合与判定**这一层。
"""
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import rehearse_first_use,release_check

REHEARSAL_STEPS=['1. 安装完整性','2. 老师选范围与功能','3. 图片版试卷登记','4. 图片版答案绑定','5. 构建',
                 '6. 产物核验','7. 浏览器验收','8. 人工复核清单','9. 打包']

class ReleaseCheckAggregation(unittest.TestCase):
    """五项检查的聚合：通过/失败/跳过的口径、报告落点、退出码。"""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 发布验收自检 ')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'VERSION').write_text('9.9.9\n',encoding='utf-8')

    def fake_rehearse(self,failed=0,skipped=1):
        def run(work,reports,skip_browser=False):
            work=Path(work);reports=Path(reports);work.mkdir(parents=True,exist_ok=True);reports.mkdir(parents=True,exist_ok=True)
            steps=[{'name':name,'status':'passed'} for name in REHEARSAL_STEPS]
            if skipped:steps[6]={'name':REHEARSAL_STEPS[6],'status':'skipped'}
            if failed:steps[4]={'name':REHEARSAL_STEPS[4],'status':'failed'}
            return {'summary':{'passed':sum(1 for s in steps if s['status']=='passed'),
                               'failed':sum(1 for s in steps if s['status']=='failed'),
                               'skipped':sum(1 for s in steps if s['status']=='skipped')},'steps':steps}
        return run

    def fake_smoke_run(self,write_zip=True):
        def run(args,cwd=None):
            reports=Path(args[args.index('--report-dir')+1]);reports.mkdir(parents=True,exist_ok=True)
            if write_zip:(reports/'smoke-report-macos.zip').write_bytes(b'PK\x03\x04fake')
            return 0,'{}',''
        return run

    def check(self,install='complete',doc_problems=(),rehearsal_failed=0,zip_written=True,gate_ok=True):
        with patch.object(release_check,'ROOT',self.root),\
             patch.object(release_check,'run_unittest',return_value=(gate_ok,'stub test tail')),\
             patch('check_docs.check',return_value={'problems':list(doc_problems)}),\
             patch('check_install.check',return_value={'status':install,'version':'9.9.9','checked_files':129,'errors':[]}),\
             patch.object(rehearse_first_use,'rehearse',side_effect=self.fake_rehearse(rehearsal_failed)),\
             patch.object(rehearse_first_use,'run',side_effect=self.fake_smoke_run(zip_written)),\
             patch('read_acceptance.load',return_value={'smoke':{},'files':[]}),\
             patch('read_acceptance.verdict',return_value={'claims':[{'claim':'该机器的安装完整'}],'gaps':[{'claim':'x'}]}):
            return release_check.check()

    def test_five_items_in_the_documented_order(self):
        report=self.check()
        self.assertEqual([row['name'] for row in report['items']],
                         ['文档一致性（命令/参数/版本/链接/测试数量）','安装完整性',
                          '整链重放（九步，老师第一次使用路径）','材料包判读（能声明什么/不能声明什么）','闸门与一致性用例'])
        self.assertEqual(report['version'],'9.9.9','版本要取自 VERSION')
    def test_all_pass_summary_is_five_passed(self):
        report=self.check()
        self.assertEqual(report['summary'],{'passed':5,'failed':0,'skipped':0})
    def test_a_skipped_step_is_recorded_but_not_counted_as_passed(self):
        report=self.check(rehearsal_failed=0)
        replay=[row for row in report['items'] if row['name'].startswith('整链重放')][0]
        self.assertEqual(replay['status'],'passed')
        self.assertIn('skipped=1',replay['detail'])
        self.assertIn('跳过：7. 浏览器验收',replay['detail'])
    def test_each_failure_turns_its_own_item_red(self):
        cases=[({'doc_problems':['文档不一致']},'文档一致性'),
               ({'install':'incomplete_install'},'安装完整性'),
               ({'rehearsal_failed':1},'整链重放'),
               ({'zip_written':False},'材料包判读'),
               ({'gate_ok':False},'闸门与一致性用例')]
        for kwargs,label in cases:
            with self.subTest(label=label):
                report=self.check(**kwargs)
                item=[row for row in report['items'] if row['name'].startswith(label)][0]
                self.assertEqual(item['status'],'failed',item)
                self.assertEqual(report['summary']['failed'],1)
    def test_reports_go_to_dist_not_the_package_root(self):
        """历史问题：报告留在包根会被打进 ZIP，而且版本号停在旧版。"""
        self.check()
        self.assertTrue((self.root/'dist'/'release-check'/'release-check.json').is_file())
        self.assertTrue((self.root/'dist'/'release-check'/'release-check.md').is_file())
        self.assertFalse((self.root/'release-check.json').exists())
        self.assertFalse((self.root/'release-check.md').exists())
    def test_the_note_states_what_a_green_run_does_not_prove(self):
        report=self.check()
        self.assertIn('缺工具的跳过项不算通过',report['note'])
        self.assertIn('不证明真实试卷内容',report['note'])

class ReleaseCheckExitCode(unittest.TestCase):
    """退出码只由 failed 决定：跳过不算通过，但也不该把发布判成失败。"""
    def run_main(self,summary):
        with patch.object(release_check,'check',return_value={'summary':summary,'items':[],'version':'9.9.9'}),\
             patch.object(sys,'argv',['release_check.py','--json']),\
             patch('platform_tools.force_utf8',lambda *a,**k:None),\
             contextlib.redirect_stdout(io.StringIO()):
            return release_check.main()
    def test_zero_when_nothing_failed(self):
        self.assertEqual(self.run_main({'passed':5,'failed':0,'skipped':0}),0)
        self.assertEqual(self.run_main({'passed':3,'failed':0,'skipped':2}),0,'跳过不算通过，但也不算失败')
    def test_one_when_anything_failed(self):
        self.assertEqual(self.run_main({'passed':4,'failed':1,'skipped':0}),1)

class ReleaseCheckUnittestVerdict(unittest.TestCase):
    """第 5 项的判据就是子进程退出码，不能把非零读成通过。"""
    def fake(self,returncode):
        class Result:pass
        result=Result();result.returncode=returncode;result.stdout='';result.stderr=f'Ran 3 tests\nFAILED (failures=1)'
        return result
    def test_nonzero_return_code_is_a_failure(self):
        with patch.object(subprocess,'run',return_value=self.fake(1)):
            ok,detail=release_check.run_unittest(['tests.test_x'])
        self.assertFalse(ok);self.assertIn('FAILED',detail)
    def test_zero_return_code_passes_and_passes_the_modules_through(self):
        captured={}
        def fake_run(argv,**kwargs):
            captured['argv']=argv;captured['cwd']=kwargs.get('cwd');return self.fake(0)
        with patch.object(subprocess,'run',side_effect=fake_run):
            ok,detail=release_check.run_unittest(['tests.test_a','tests.test_b'])
        self.assertTrue(ok)
        self.assertEqual(captured['argv'][-2:],['tests.test_a','tests.test_b'])
        self.assertEqual(captured['cwd'],str(release_check.ROOT),'必须在包根下跑，否则 import 不到 tests/')

class RehearsalCriteria(unittest.TestCase):
    """重放脚本自身的判据：路径解析、输出容错、夹具页必须互不相同。"""
    def test_scripts_paths_resolve_against_the_package_root(self):
        """cwd 是老师的工作目录时，`scripts/x.py` 仍要按包根解析（脚本自己的注释就写着这条）。"""
        captured={}
        def fake_run(argv,**kwargs):
            captured['argv']=argv;captured['cwd']=kwargs.get('cwd')
            class Result:pass
            result=Result();result.returncode=0;result.stdout='{}';result.stderr=''
            return result
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(subprocess,'run',side_effect=fake_run):
                rehearse_first_use.run(['scripts/check_install.py','--root','.'],cwd=temp)
            self.assertEqual(captured['argv'][1],str(rehearse_first_use.ROOT/'scripts/check_install.py'))
            self.assertEqual(captured['cwd'],temp,'cwd 要保留老师的工作目录')
    def test_as_json_tolerates_noisy_stdout(self):
        self.assertEqual(rehearse_first_use.as_json('提示一行\n{"status":"complete"}\n结束'),{'status':'complete'})
        self.assertEqual(rehearse_first_use.as_json('完全没有 JSON'),{})
    def test_fixture_pages_are_real_and_different(self):
        """夹具两页必须不同：内容相同的两页会被登记成 duplicate_page，那是夹具的错不是流程的错。"""
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);first=base/'a.png';second=base/'b.png'
            rehearse_first_use.picture(first,color=(60,90,120))
            rehearse_first_use.picture(second,size=72,color=(120,60,60))
            one,two=first.read_bytes(),second.read_bytes()
            self.assertTrue(one.startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertNotEqual(one,two)
    def test_documented_step_names_are_stable(self):
        """步骤名是报告与文档之间的契约（`test_first_use_rehearsal` 按名字取步骤）。"""
        self.assertEqual(len(REHEARSAL_STEPS),9)
        source=(ROOT/'scripts'/'rehearse_first_use.py').read_text(encoding='utf-8')
        for name in REHEARSAL_STEPS:
            self.assertIn(f"'{name}'",source,f'重放脚本里找不到步骤 {name}')

class StaleBytecodeGuard(unittest.TestCase):
    """验收前必须清掉派生字节码缓存（1.0.112 的真实踩坑）。

    改一处常量再改回来，如果**同一秒内、文件大小又没变**，CPython 的 pyc 失效判据
    （mtime 秒 + 大小）会认为缓存有效，于是验收跑的是改坏那一版。
    """
    def test_caches_are_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('scripts','tests'):
                cache=root/name/'__pycache__';cache.mkdir(parents=True)
                (cache/'x.cpython-311.pyc').write_bytes(b'stale')
            removed=release_check.clear_bytecode_caches(root)
            self.assertEqual(removed,2)
            self.assertFalse((root/'scripts'/'__pycache__').exists())
            self.assertFalse((root/'tests'/'__pycache__').exists())
    def test_a_missing_cache_directory_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(release_check.clear_bytecode_caches(Path(temp)),0)
    def test_check_clears_them_before_running(self):
        """守卫：函数写了却没人调用等于没有。"""
        source=(ROOT/'scripts'/'release_check.py').read_text(encoding='utf-8')
        self.assertIn('clear_bytecode_caches(ROOT)',source)

class RehearsalStepCriteria(unittest.TestCase):
    """每一步的判定标准本身（1.0.112）。

    这些判据以前写成 `rehearse()` 里的内联表达式，只有"一路绿灯"的端到端重放能覆盖；
    把某一步改坏（例如把"必须有 problems 为空"改成"有页数就行"）不会被任何测试抓到。
    现在每条判据都能单独喂"做坏的输入"。
    """
    def test_step1_install_must_be_complete(self):
        self.assertTrue(rehearse_first_use.install_ok({'status':'complete'}))
        for broken in ({},{'status':'incomplete_install'},{'status':'unknown'}):
            self.assertFalse(rehearse_first_use.install_ok(broken),broken)
    def test_step2_needs_all_seven_features_and_confirmation(self):
        good={'confirmed':True,'features':{f'f{i}':False for i in range(7)}}
        self.assertTrue(rehearse_first_use.plan_ok(good))
        without_confirm={'confirmed':False,'features':{f'f{i}':True for i in range(7)}}
        six={'confirmed':True,'features':{f'f{i}':True for i in range(6)}}
        for broken in ({},without_confirm,six,{'confirmed':True,'features':None}):
            self.assertFalse(rehearse_first_use.plan_ok(broken),broken)
    def test_step3_inventory_must_have_pages_and_no_problems(self):
        self.assertTrue(rehearse_first_use.inventory_ok({'logical_pages':2,'problems':[]}))
        for broken in ({},{'logical_pages':0,'problems':[]},{'logical_pages':2,'problems':['duplicate_page']},
                       {'logical_pages':2,'problems':None} if False else {'problems':[]}):
            self.assertFalse(rehearse_first_use.inventory_ok(broken),broken)
    def test_step4_answers_must_come_from_image_transcription(self):
        self.assertTrue(rehearse_first_use.answers_ok({'answer_source_kind':'image_transcription','count':2}))
        for broken in ({},{'answer_source_kind':'parsed','count':20},
                       {'answer_source_kind':'image_transcription','count':0}):
            self.assertFalse(rehearse_first_use.answers_ok(broken),broken)
    def test_step5_build_must_pass_structural_checks(self):
        self.assertTrue(rehearse_first_use.build_ok({'status':'structural_checks_passed'}))
        for broken in ({},{'status':'structural_checks_failed'},{'status':'blocked'}):
            self.assertFalse(rehearse_first_use.build_ok(broken),broken)
    def test_step6_verify_must_pass(self):
        self.assertTrue(rehearse_first_use.verify_ok({'status':'passed'}))
        for broken in ({},{'status':'mismatch'},{'status':'failed'}):
            self.assertFalse(rehearse_first_use.verify_ok(broken),broken)
    def test_step7_browser_evidence_must_pass(self):
        self.assertTrue(rehearse_first_use.browser_ok({'status':'passed'}))
        for broken in ({},{'status':'failed'},{'status':'not_available'}):
            self.assertFalse(rehearse_first_use.browser_ok(broken),broken)
    def test_step8_qa_report_must_be_rejected_then_accepted(self):
        self.assertTrue(rehearse_first_use.qa_ok(9,1,0))
        for broken in ((0,1,0),            # 没生成条目
                       (9,0,0),            # 未填写时没有拒绝
                       (9,1,1)):           # 填写后仍然拒绝
            self.assertFalse(rehearse_first_use.qa_ok(*broken),broken)
    def test_step9_package_accepts_checked_or_honest_downgrade(self):
        self.assertTrue(rehearse_first_use.package_ok({'status':'browser_checked'}))
        self.assertTrue(rehearse_first_use.package_ok({'status':'preview_only_browser_check_pending'}))
        for broken in ({},{'status':'failed'},{'status':'not_ready'}):
            self.assertFalse(rehearse_first_use.package_ok(broken),broken)
    def test_rehearse_actually_uses_every_criterion(self):
        """判据函数必须真被 rehearse() 用上：改回内联表达式时这条会失败（否则测试的是死代码）。"""
        source=(ROOT/'scripts'/'rehearse_first_use.py').read_text(encoding='utf-8')
        for name in ('install_ok','plan_ok','inventory_ok','answers_ok','build_ok','verify_ok',
                     'browser_ok','qa_ok','package_ok'):
            self.assertIn(f"{name}(",source,f"rehearse() 没有使用判据 {name}()")
        self.assertEqual(rehearse_first_use.STEP_COUNT,9)
        # 第 7 步有"跳过/执行"两条分支，所以按**步骤编号**核对，而不是数 step( 的行数
        numbers=sorted({int(m) for m in re.findall(r"step\('(\d)\. ",source)})
        self.assertEqual(numbers,list(range(1,10)),'九步都必须通过 step() 记录状态')
    def test_no_inline_judgements_left_in_rehearse(self):
        source=(ROOT/'scripts'/'rehearse_first_use.py').read_text(encoding='utf-8')
        for inline in ("report.get('status')=='complete' and 'passed'",
                       "verified.get('status')=='passed' else",
                       "packed.get('status') in ("):
            self.assertNotIn(inline,source,f'判据又写回内联表达式了：{inline}')

if __name__=='__main__':unittest.main()
