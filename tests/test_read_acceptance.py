"""真机验收材料：跑一次、发回来、严格判读。

真实痛点：谁都说"我在我机器上跑过了"，但报告里 `skipped` 与 `failed` 经常被读成通过；
用示例卷跑的报告也可能被当成"真实试卷已验收"。这里锁住判读的口径：

* `skipped` 一律不算通过，`--no-browser` 的报告不能支持"按钮与播放已验证"；
* 平台不是 Windows 就不能支持"Windows 已验收"；
* 报告用的是示例卷，永远不能支持"真实试卷/答案/听力边界已验收"；
* 宿主（豆包工作/WorkBuddy）端到端不在报告内。
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import read_acceptance

def report(family='windows',steps=None,summary=None):
    steps=steps or [{'name':'1. 运行环境','status':'passed'},
                    {'name':'2. 安装完整性','status':'passed'},
                    {'name':'3. 宿主能力','status':'passed'},
                    {'name':'4. 示例构建','status':'passed'},
                    {'name':'5. 模板与产物核验','status':'passed'},
                    {'name':'6. 浏览器点击验收','status':'passed'},
                    {'name':'7. 打包交付','status':'passed','detail':'status=browser_checked · zip_sha256=abc…'}]
    counts={status:sum(1 for step in steps if step['status']==status) for status in ('passed','failed','skipped')}
    return {'version':'1.0.55','family':family,'steps':steps,'summary':summary or counts}

def supported(result,text):
    return any(text in item['claim'] and item['supported'] for item in result['claims'])

def unsupported(result,text):
    return any(text in item['claim'] and not item['supported'] for item in result['gaps'])

def real_shape_report(system='Windows',family=None):
    """按 smoke_report.py 的**真实**产物形状造报告：平台信息在 environment 里。

    老测试一直用顶层 family 的夹具，而真实产物从来没有这个键——所以
    "第 3 步失败→没有 host-probe.json"时，一台 Windows 机器的报告会被读成"不是 Windows"。
    """
    env={'platform':f'{system}-10','system':system,'machine':'AMD64','python':'3.11.5',
         'executable':'C:/Python/python.exe','stdout_encoding':'utf-8','cwd':'C:/skill'}
    if family:env['family']=family
    steps=[{'name':'1. 运行环境','status':'passed'},{'name':'2. 安装完整性','status':'passed'},
           {'name':'3. 宿主能力','status':'failed'},{'name':'4. 示例构建','status':'passed'},
           {'name':'5. 模板与产物核验','status':'passed'},{'name':'6. 浏览器点击验收','status':'passed'},
           {'name':'7. 打包交付','status':'passed','detail':'status=browser_checked · zip_sha256=abc…'}]
    return {'version':'1.0.101','environment':env,'steps':steps,
            'summary':{s:sum(1 for step in steps if step['status']==s) for s in ('passed','failed','skipped')}}

class PlatformResolution(unittest.TestCase):
    """判读脚本必须认得出报告来自哪个平台，否则 Windows 验收永远无法被确认。"""
    def test_windows_report_without_host_probe_still_supports_the_windows_claim(self):
        result=read_acceptance.verdict({'smoke':real_shape_report('Windows'),'files':['smoke-report.json']})
        self.assertEqual(result['family'],'windows')
        self.assertTrue(supported(result,'Windows 实机验收已完成'),result['gaps'])
    def test_environment_family_is_used_when_present(self):
        result=read_acceptance.verdict({'smoke':real_shape_report('FreeBSD',family='macos'),'files':[]})
        self.assertEqual(result['family'],'macos')
    def test_host_probe_still_wins_for_reports_without_platform_information(self):
        """老报告（environment 里没有平台）仍要能靠 host-probe.json 判出 Windows。"""
        result=read_acceptance.verdict({'smoke':real_shape_report(''),'host':{'family':'windows'},'files':[]})
        self.assertEqual(result['family'],'windows')
        self.assertTrue(supported(result,'Windows 实机验收已完成'))
    def test_macos_system_without_family_is_read_as_macos(self):
        result=read_acceptance.verdict({'smoke':real_shape_report('Darwin'),'files':[]})
        self.assertEqual(result['family'],'macos')
        self.assertTrue(unsupported(result,'Windows 实机验收已完成'))
        self.assertIn('不是 Windows',[item.get('why','') for item in result['gaps'] if 'Windows' in item['claim']][0])
    def test_no_platform_information_says_it_cannot_tell(self):
        result=read_acceptance.verdict({'smoke':real_shape_report(''),'files':[]})
        self.assertEqual(result['family'],'unknown')
        why=[item.get('why','') for item in result['gaps'] if 'Windows' in item['claim']][0]
        self.assertIn('无法判断',why)
        self.assertNotIn('不是 Windows',why,'"没写平台"不能被当成"不是 Windows"的证据')
    def test_the_real_producer_writes_the_platform_family(self):
        import smoke_report
        _,_,block=smoke_report.environment()
        env=json.loads(block)
        self.assertIn('family',env,'smoke_report 必须把 family 写进 environment，判读脚本要靠它')
        result=read_acceptance.verdict({'smoke':{'version':'x','environment':env,'steps':[],'summary':{}},'files':[]})
        self.assertNotEqual(result['family'],'unknown')

class Verdict(unittest.TestCase):
    def test_all_green_on_windows_supports_the_build_claims(self):
        result=read_acceptance.verdict({'smoke':report('windows'),'files':['smoke-report.json']})
        self.assertTrue(supported(result,'安装完整'))
        self.assertTrue(supported(result,'浏览器实际操作与播放已执行'))
        self.assertTrue(supported(result,'browser_checked'))
        self.assertTrue(supported(result,'Windows 实机验收已完成'))
        self.assertFalse(unsupported(result,'Windows 实机验收已完成'))

    def test_no_browser_run_never_supports_the_click_claim(self):
        steps=[{'name':'1. 运行环境','status':'passed'},{'name':'2. 安装完整性','status':'passed'},
               {'name':'3. 宿主能力','status':'passed'},{'name':'4. 示例构建','status':'passed'},
               {'name':'5. 模板与产物核验','status':'passed'},
               {'name':'6. 浏览器点击验收','status':'skipped'},{'name':'7. 打包交付','status':'passed'}]
        result=read_acceptance.verdict({'smoke':report('windows',steps),'files':[]})
        self.assertTrue(unsupported(result,'浏览器实际操作与播放已执行'))
        self.assertIn('6. 浏览器点击验收',result['skipped_steps'])
        self.assertTrue(unsupported(result,'browser_checked'))

    def test_failed_install_stops_every_downstream_claim(self):
        steps=[{'name':'1. 运行环境','status':'passed'},{'name':'2. 安装完整性','status':'failed'},
               {'name':'3. 宿主能力','status':'failed'},{'name':'4. 示例构建','status':'skipped'},
               {'name':'5. 模板与产物核验','status':'skipped'},{'name':'6. 浏览器点击验收','status':'skipped'},
               {'name':'7. 打包交付','status':'skipped'}]
        result=read_acceptance.verdict({'smoke':report('windows',steps),'files':[]})
        self.assertEqual(result['claims'],[])
        self.assertEqual(result['failed_steps'],['2. 安装完整性','3. 宿主能力'])
        self.assertTrue(unsupported(result,'安装完整'))

    def test_same_green_report_on_macos_does_not_support_the_windows_claim(self):
        result=read_acceptance.verdict({'smoke':report('macos'),'files':[]})
        self.assertTrue(unsupported(result,'Windows 实机验收已完成'))
        self.assertIn('不是 Windows',[item.get('why','') for item in result['gaps'] if 'Windows' in item['claim']][0])

    def test_self_check_pack_is_not_claimed_as_browser_checked(self):
        """自检不填人工复核清单，所以只能声明"打包链路可用"，不能声明"可交付 browser_checked"。"""
        steps=[{'name':'1. 运行环境','status':'passed'},{'name':'2. 安装完整性','status':'passed'},
               {'name':'3. 宿主能力','status':'passed'},{'name':'4. 示例构建','status':'passed'},
               {'name':'5. 模板与产物核验','status':'passed'},{'name':'6. 浏览器点击验收','status':'passed'},
               {'name':'7. 打包交付','status':'passed','detail':'status=preview_only_browser_check_pending · 示例卷自检不填人工复核清单'}]
        result=read_acceptance.verdict({'smoke':report('windows',steps),'files':[]})
        self.assertTrue(supported(result,'打包链路可用'))
        self.assertTrue(unsupported(result,'browser_checked'))
        self.assertIn('qa-report.md',[item.get('why','') for item in result['gaps'] if 'browser_checked' in item['claim']][0])

    def test_real_browser_checked_delivery_is_claimed_when_reported(self):
        steps=[{'name':'1. 运行环境','status':'passed'},{'name':'2. 安装完整性','status':'passed'},
               {'name':'3. 宿主能力','status':'passed'},{'name':'4. 示例构建','status':'passed'},
               {'name':'5. 模板与产物核验','status':'passed'},{'name':'6. 浏览器点击验收','status':'passed'},
               {'name':'7. 打包交付','status':'passed','detail':'status=browser_checked · zip_sha256=abc…'}]
        result=read_acceptance.verdict({'smoke':report('windows',steps),'files':[]})
        self.assertTrue(supported(result,'可交付 browser_checked'))

    def test_real_paper_and_host_claims_are_always_out_of_scope(self):
        result=read_acceptance.verdict({'smoke':report('windows'),'files':[]})
        self.assertTrue(unsupported(result,'真实试卷内容、答案与听力边界已验收'))
        self.assertTrue(unsupported(result,'豆包工作 / WorkBuddy 端到端链路已验证'))

    def test_zip_and_directory_are_both_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            (base/'smoke-report.json').write_text(json.dumps(report('windows'),ensure_ascii=False),encoding='utf-8')
            (base/'host-probe.json').write_text(json.dumps({'family':'windows','install_paths':[]},ensure_ascii=False),encoding='utf-8')
            from_dir=read_acceptance.verdict(read_acceptance.load(base))
            self.assertTrue(supported(from_dir,'安装完整'))
            archive=base/'pack.zip'
            with zipfile.ZipFile(archive,'w') as bundle:
                bundle.write(base/'smoke-report.json','smoke-report.json')
                bundle.write(base/'host-probe.json','host-probe.json')
            from_zip=read_acceptance.verdict(read_acceptance.load(archive))
            self.assertTrue(supported(from_zip,'安装完整'))
            self.assertIn('host-probe.json',from_zip['files'])

    def test_missing_report_is_an_actionable_error(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError) as caught:read_acceptance.verdict(read_acceptance.load(Path(temp)))
            self.assertIn('smoke-report.json',str(caught.exception))

    def test_render_says_what_is_not_proven(self):
        text=read_acceptance.render(read_acceptance.verdict({'smoke':report('windows'),'files':[]}))
        self.assertIn('可以据此声明',text)
        self.assertIn('仍不能声明',text)
        self.assertIn('真实试卷',text)
        self.assertIn('skipped 与 failed 一律不当作通过',text)

class EndToEnd(unittest.TestCase):
    def test_real_smoke_report_is_readable(self):
        """真跑一次 smoke_report（跳过浏览器），产物必须能被判读。"""
        temp=tempfile.TemporaryDirectory(prefix='英语 skill 验收材料 ')
        base=Path(temp.name)
        result=subprocess.run([sys.executable,str(ROOT/'scripts/smoke_report.py'),'--no-browser','--zip',
                               '--workdir',str(base/'work'),'--report-dir',str(base/'reports')],
                              capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300)
        report_path=base/'reports'/'smoke-report.json'
        self.assertTrue(report_path.is_file(),result.stdout[-800:]+result.stderr[-400:])
        parsed=read_acceptance.verdict(read_acceptance.load(report_path))
        self.assertEqual(parsed['version'],(ROOT/'VERSION').read_text(encoding='utf-8').strip())
        if os.environ.get('PLAYWRIGHT_MODULE') and os.environ.get('CHROME_BIN'):
            self.assertTrue(parsed['summary']['passed']>=5,parsed['summary'])
        self.assertTrue(unsupported(parsed,'浏览器实际操作与播放已执行'),'--no-browser 的报告不能支持点击验收')
        self.assertTrue((base/'reports'/'host-probe.json').is_file(),'宿主探测必须随报告落盘')
        self.assertIn('family',json.loads(report_path.read_text(encoding='utf-8')),'报告本身要写明平台')
        self.assertNotEqual(parsed['family'],'unknown','真实报告必须能判出平台')
        archive=list((base/'reports').glob('smoke-report-*.zip'))
        self.assertTrue(archive,'--zip 必须产出可发回的单一文件')
        self.assertTrue(supported(read_acceptance.verdict(read_acceptance.load(archive[0])),'安装完整'))
        temp.cleanup()

if __name__=='__main__':unittest.main()
