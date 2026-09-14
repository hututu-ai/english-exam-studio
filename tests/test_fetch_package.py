"""`fetch_package.py` 是"没有 ZIP 时"唯一能执行的那条路，必须真的能跑、且说实话。

真问题：宿主下不了发布 ZIP 时，文档让助手"逐个抓文件"——约 120 次手工网络请求，
少一个或截断一个，后面构建才报错，查起来很贵。这个脚本一条命令抓完并逐个核对哈希。
测试用本机 HTTP 服务做夹具，因此离线可复现。
"""
import hashlib
import http.server
import json
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import fetch_package

def sha256(payload):return hashlib.sha256(payload).hexdigest()

class LocalSite:
    """把一棵目录树挂到 127.0.0.1 的随机端口上。"""

    def __init__(self,root):
        self.root=Path(root)
        handler=self._handler()
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_address[1]}'

    def _handler(self):
        root=self.root
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(root),**kwargs)
            def log_message(self,*args):pass
        return Handler

    def close(self):
        self.server.shutdown();self.server.server_close()

class FetchPackage(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 抓取 ')
        self.base=Path(self.temp.name)
        self.site_dir=self.base/'site';self.site_dir.mkdir()
        self.out=self.base/'out'

    def tearDown(self):self.temp.cleanup()

    def write_package(self,files,version='9.9.9',manifest_files=None):
        entries={}
        for name,payload in files.items():
            target=self.site_dir/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(payload)
            entries[name]=sha256(payload)
        document={'version':version,'files':manifest_files if manifest_files is not None else entries}
        (self.site_dir/'install-manifest.json').write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
        return entries

    def serve(self):
        return LocalSite(self.site_dir)

    def test_fetches_every_listed_file_and_verifies_hashes(self):
        files={'SKILL.md':'# 技能\n'.encode('utf-8'),'VERSION':b'9.9.9\n',
               'assets/媒体/示例.txt':'中文文件名也要能下载\n'.encode('utf-8')}
        self.write_package(files)
        site=self.serve()
        try:report=fetch_package.fetch_package(site.base,self.out)
        finally:site.close()
        self.assertEqual(report['status'],'fetched_all_files',report)
        self.assertEqual(report['written'],3)
        self.assertEqual((self.out/'SKILL.md').read_text(encoding='utf-8'),'# 技能\n')
        self.assertEqual((self.out/'assets/媒体/示例.txt').read_text(encoding='utf-8'),'中文文件名也要能下载\n')
        # 诚实边界：清单与文件同源，不能声称来源已证明
        self.assertFalse(report['trust']['source_verified'])
        self.assertIn('同一通道',report['trust']['why'])
        self.assertIn('check_install',report['next_step'])

    def test_fetched_tree_passes_check_install_on_the_real_package(self):
        """真链路：把真实技能包挂到本机 HTTP 上按清单抓下来，必须能跑到 check_install=complete。

        这一步抓到过一个真缺陷：`install-manifest.json` 不在它自己的 files 列表里，
        只抓"清单列出的文件"会缺清单本身 → check_install 报 incomplete_install。
        """
        import contextlib,io,shutil
        sys.path.insert(0,str(ROOT/'scripts'))
        import check_install,package_skill
        site_dir=self.base/'real'
        shutil.copytree(ROOT,site_dir,ignore=shutil.ignore_patterns('dist','work','__pycache__','.git','*.zip'))
        # 副本先按发布流程重建清单：清单必须与文件一致，否则测的就不是抓取而是"清单过期"
        package_skill.package(site_dir,self.base/'pkg.zip')
        version=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
        self.site_dir=site_dir
        site=self.serve()
        try:report=fetch_package.fetch_package(site.base,self.out,expected_version=version)
        finally:site.close()
        self.assertEqual(report['status'],'fetched_all_files',report['mismatched'][:2])
        self.assertTrue((self.out/'install-manifest.json').is_file(),'目标目录必须有清单本身，否则 check_install 无法核对')
        fetched=json.loads((self.out/'install-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(report['written'],len(fetched['files']),'清单列出的每个文件都要抓下来')
        result=check_install.check(self.out)
        self.assertEqual(result['status'],'complete',result.get('errors'))
        self.assertEqual(result['version'],version)

    def test_version_mismatch_is_refused_with_the_actual_version(self):
        self.write_package({'VERSION':b'1.0.0\n'},version='1.0.0')
        site=self.serve()
        try:
            with self.assertRaises(ValueError) as caught:
                fetch_package.fetch_package(site.base,self.out,expected_version='1.0.83')
        finally:site.close()
        self.assertIn('1.0.0',str(caught.exception))
        self.assertIn('1.0.83',str(caught.exception))

    def test_hash_mismatch_is_reported_and_never_counted_as_success(self):
        payload=b'correct content\n'
        self.write_package({'SKILL.md':payload})
        (self.site_dir/'SKILL.md').write_bytes(b'tampered content\n')      # 文件与清单不一致
        site=self.serve()
        try:report=fetch_package.fetch_package(site.base,self.out)
        finally:site.close()
        self.assertEqual(report['status'],'incomplete_fetch')
        self.assertEqual(report['written'],0)
        self.assertEqual(len(report['mismatched']),1)
        self.assertIn('SKILL.md',report['mismatched'][0]['file'])
        self.assertFalse((self.out/'SKILL.md').exists(),'哈希不符的文件不该落盘')

    def test_manifest_with_escaping_paths_is_refused(self):
        entries={'../../逃逸.txt':'0'*64,'C:/Windows/x.txt':'1'*64,'ok.txt':sha256(b'ok\n')}
        self.write_package({'ok.txt':b'ok\n'},manifest_files=entries)
        site=self.serve()
        try:report=fetch_package.fetch_package(site.base,self.out)
        finally:site.close()
        self.assertEqual(report['status'],'incomplete_fetch')
        self.assertEqual(len(report['refused']),2,'越界与盘符路径都要拒绝')
        self.assertTrue((self.out/'ok.txt').is_file(),'合法条目仍要正常抓取')
        self.assertFalse((self.base/'逃逸.txt').exists(),'拒绝的条目绝不能写到输出目录之外')

    def test_unreachable_base_fails_bounded_with_a_chinese_reason(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]      # 已关闭的端口
        with self.assertRaises(ValueError) as caught:
            fetch_package.fetch_package(f'http://127.0.0.1:{port}',self.out,timeout=2)
        text=str(caught.exception)
        self.assertIn('下载失败',text)
        self.assertIn('不做无限重试',text)

    def test_missing_files_are_listed_not_silently_skipped(self):
        self.write_package({'present.txt':b'ok\n'},manifest_files={'present.txt':sha256(b'ok\n'),'absent.txt':'2'*64})
        site=self.serve()
        try:report=fetch_package.fetch_package(site.base,self.out)
        finally:site.close()
        self.assertEqual(report['status'],'incomplete_fetch')
        self.assertEqual([item['file'] for item in report['missing']],['absent.txt'])
        self.assertEqual(report['written'],1)

if __name__=='__main__':unittest.main()
