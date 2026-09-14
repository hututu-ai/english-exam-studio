"""宿主适配：探测"这台机器到底能不能装/能不能验收"，并把安装路径按可靠性排好。

真实反馈（WorkBuddy 截图）：`git clone github.com` 被沙箱 TLS 拦下、网页抓取却可用。
如果探测脚本只会说"安装不完整"，助手就会反复试 clone，白烧轮次和额度。
这里锁住三件事：三条安装路径的顺序与可用性、探测本身不下载不改动、
以及"没跑通 check_install=complete 就不许说已安装"。
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import host_probe

class InstallPaths(unittest.TestCase):
    def test_paths_are_ordered_from_most_to_least_reliable(self):
        paths=host_probe.install_paths(ROOT,network=False)
        self.assertEqual([item['path'] for item in paths],['teacher_uploaded_zip','raw_files_fetch','cdn_jsdelivr','git_clone'],
                         '老师上传 ZIP 最稳，其次是抓 raw 文件，最后才是 git clone')
        for item in paths:
            self.assertTrue(item['how'].strip(),f"{item['path']} 必须写清怎么做")

    def test_without_network_probe_availability_is_honest(self):
        paths=host_probe.install_paths(ROOT,network=False)
        states={item['path']:item['available'] for item in paths}
        self.assertEqual(states['teacher_uploaded_zip'],'unknown','能不能上传附件只有宿主自己知道，不能猜')
        self.assertEqual(states['raw_files_fetch'],'not_probed')
        self.assertEqual(states['cdn_jsdelivr'],'not_probed')
        self.assertEqual(states['git_clone'],'not_probed')

    def test_network_probe_reports_reachability(self):
        with patch.object(host_probe,'reachable',side_effect=lambda url,timeout=4:'raw' in url):
            paths=host_probe.install_paths(ROOT,network=True)
        states={item['path']:item['available'] for item in paths}
        self.assertEqual(states['raw_files_fetch'],'yes')
        self.assertEqual(states['cdn_jsdelivr'],'no','raw 通而 jsDelivr 不通时也要如实标出')
        self.assertEqual(states['git_clone'],'no','沙箱拦 git 时必须如实标 no，让助手改走别的路')
        with patch.object(host_probe,'reachable',side_effect=lambda url,timeout=4:'jsdelivr' in url):
            cdn_paths=host_probe.install_paths(ROOT,network=True)
        cdn_states={item['path']:item['available'] for item in cdn_paths}
        self.assertEqual(cdn_states['cdn_jsdelivr'],'yes','jsDelivr 能连上时必须如实标 yes（它是 raw 打不开时的备选）')
        self.assertEqual(cdn_states['raw_files_fetch'],'no')

    def test_probe_never_downloads_or_mutates(self):
        """探测只发 HEAD：把 urlopen 换成记录器，确认没有读 body、没有写盘。"""
        seen=[]
        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,*args):raise AssertionError('探测不应读取响应体（等于下载）')
        def fake_urlopen(request,timeout=None):
            seen.append((getattr(request,'method',None),getattr(request,'full_url',str(request)),timeout))
            return FakeResponse()
        with patch('urllib.request.urlopen',fake_urlopen):
            self.assertTrue(host_probe.reachable('https://raw.githubusercontent.com/x/y'))
        self.assertEqual(len(seen),1)
        self.assertEqual(seen[0][0],'HEAD')
        self.assertTrue(seen[0][2] and seen[0][2]<=10,'必须有界超时，不能把宿主卡住')

class Guidance(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 宿主探测 ')
        self.root=Path(self.temp.name)          # 空目录 = 安装不完整
    def tearDown(self):self.temp.cleanup()

    def test_incomplete_install_offers_the_three_paths_and_forbids_claiming_success(self):
        report=host_probe.probe(self.root,network=False)
        self.assertNotEqual(report['installation']['status'],'complete')
        guidance='\n'.join(report['guidance'])
        self.assertIn('上传',guidance)
        self.assertIn('raw.githubusercontent.com',guidance)
        self.assertIn('不要反复尝试 git clone',guidance)
        self.assertIn('complete',guidance)
        self.assertIn('尚未完整安装',guidance)
        self.assertEqual(report['network_probed'],False)
        self.assertIn('install_paths',report)

    def test_guidance_does_not_pretend_a_zip_is_available(self):
        report=host_probe.probe(self.root,network=False)
        states={item['path']:item['available'] for item in report['install_paths']}
        self.assertNotEqual(states['teacher_uploaded_zip'],'yes','没有确实拿到附件时不能说"已可上传安装"')

    def test_complete_install_still_states_what_is_not_verified(self):
        report=host_probe.probe(ROOT,network=False)
        self.assertEqual(report['installation']['status'],'complete')
        self.assertIn('不代表真实试卷识别、听力边界或教学质量已验证',report['scope'])

    def test_cli_prints_paths_and_exits_zero(self):
        output=io.StringIO()
        with patch.object(sys,'argv',['host_probe.py','--root',str(ROOT)]),contextlib.redirect_stdout(output):
            code=host_probe.main()
        self.assertEqual(code,0)
        text=output.getvalue()
        self.assertIn('安装路径（按可靠性排序）',text)
        self.assertIn('teacher_uploaded_zip',text)

if __name__=='__main__':unittest.main()
