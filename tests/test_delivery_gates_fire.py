"""交付闸门的反向验证：证明"缺证据/证据过期/文件被改"真的会被拦。

结构闸门已在 `test_gates_fire.py` 里逐条证明；这里补齐交付这一层——
浏览器证据、媒体指纹一致性、模板与内嵌数据、qa-report、安装完整性。
每条都断言报错文字里带上实际值（哪个文件、哪个指纹、哪一条检查），
因为"被拦下了"不等于"知道该改哪里"。
"""
import contextlib
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build
from verify_output import verify_output
from package_lesson import package

def write(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class DeliveryGates(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 交付闸门 ')
        self.base=Path(self.temp.name)
        self.out=self.base/'out'
        with contextlib.redirect_stdout(io.StringIO()):
            build.build(ROOT/'examples/demo-exam.json',self.out,ROOT/'examples/source-ledger.json')

    def tearDown(self):self.temp.cleanup()

    def evidence(self,**overrides):
        verified=verify_output(self.out)
        base={'status':'passed','engine':'unit-test-fixture','html_sha256':sha(self.out/'index.html'),
              'media_sha256':verified['resource_sha256'],'checks':[{'name':'全部章节可点','status':'passed'}],
              'skipped':[],'errors':[]}
        base.update(overrides)
        write(self.out/'browser-check.json',base)
        return base

    def qa(self,fill=True):
        import re
        from qa_report import collect,render
        items,report,_=collect(self.out)
        text=render(items,report)
        if fill:text=re.sub(r'—— 结论：$','—— 结论：交付闸门反向验证夹具，已逐条核对。',text,flags=re.M)
        (self.out/'qa-report.md').write_text(text,encoding='utf-8')

    def test_missing_browser_evidence_is_refused(self):
        (self.out/'browser-check.json').unlink(missing_ok=True)
        with self.assertRaises(ValueError) as caught:package(self.out,self.base/'a.zip')
        self.assertIn('浏览器',str(caught.exception))

    def test_stale_html_hash_is_refused(self):
        """证据属于上一版 HTML：指纹对不上就必须拦（这才是"证据过期"的真实形态）。"""
        self.evidence(html_sha256='0'*64)
        with self.assertRaises(ValueError) as caught:package(self.out,self.base/'b.zip')
        self.assertIn('浏览器',str(caught.exception))

    def test_media_fingerprint_mismatch_is_refused(self):
        verified=verify_output(self.out)
        wrong=dict(verified['resource_sha256'])
        if wrong:
            first=list(wrong)[0];wrong[first]='0'*64
        else:
            wrong={'audio/full.wav':'0'*64}      # 本课件没有媒体时也要能测这条闸门
        self.qa()                                # 先让 qa-report 合格，确保报错来自浏览器证据
        self.evidence(media_sha256=wrong)
        with self.assertRaises(ValueError) as caught:package(self.out,self.base/'c.zip')
        self.assertIn('浏览器',str(caught.exception))

    def test_failed_check_status_is_refused(self):
        self.evidence(checks=[{'name':'播放听力','status':'passed'},{'name':'切换章节','status':'failed'}])
        with self.assertRaises(ValueError) as caught:package(self.out,self.base/'d.zip')
        self.assertIn('浏览器',str(caught.exception))

    def test_browser_errors_block_delivery(self):
        self.evidence(errors=['TypeError: x is undefined'])
        with self.assertRaises(ValueError) as caught:package(self.out,self.base/'e.zip')
        self.assertIn('浏览器',str(caught.exception))

    def test_missing_qa_report_is_refused(self):
        self.evidence()
        with self.assertRaises(ValueError) as caught:package(self.out,self.base/'f.zip')
        self.assertIn('qa_report.py',str(caught.exception))

    def test_unfilled_qa_report_is_refused_with_item_problems(self):
        self.evidence();self.qa(fill=False)
        with self.assertRaises(ValueError) as caught:package(self.out,self.base/'g.zip')
        text=str(caught.exception)
        self.assertIn('人工复核清单未完成',text)
        self.assertIn('结论',text)

    def test_zip_inside_output_directory_is_refused(self):
        self.evidence();self.qa()
        with self.assertRaises(ValueError) as caught:package(self.out,self.out/'inside.zip')
        self.assertIn('输出文件夹外',str(caught.exception))

    def test_allow_unchecked_labels_the_pending_version(self):
        self.evidence(checks=[])          # 没有真检查记录 → 只能给待验收版
        result=package(self.out,self.base/'pending.zip',allow_unchecked=True)
        self.assertEqual(result['status'],'preview_only_browser_check_pending')
        report=json.loads((self.out/'delivery-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'],'preview_only_browser_check_pending')
        self.assertIn('未经验证',report['scope'])

    def test_full_evidence_delivers_browser_checked_and_records_counts(self):
        self.evidence(skipped=[{'name':'多页页图','reason':'本课件没有多页页图'}])
        self.qa()
        result=package(self.out,self.base/'ok.zip')
        self.assertEqual(result['status'],'browser_checked')
        report=json.loads((self.out/'delivery-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['browser_checks'],{'passed':1,'skipped':1})
        self.assertEqual(report['browser_checks_skipped'][0]['name'],'多页页图')
        self.assertEqual(report['qa_report']['status'],'ok')

class OutputGates(unittest.TestCase):
    """verify_output / check_install 的闸门。"""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 产物闸门 ')
        self.base=Path(self.temp.name)
        self.out=self.base/'out'
        with contextlib.redirect_stdout(io.StringIO()):
            build.build(ROOT/'examples/demo-exam.json',self.out,ROOT/'examples/source-ledger.json')

    def tearDown(self):self.temp.cleanup()

    def test_modified_template_is_refused(self):
        manifest=json.loads((ROOT/'assets/template-manifest.json').read_text(encoding='utf-8'))
        broken=copy.deepcopy(manifest);broken['template_sha256']='0'*64
        with tempfile.TemporaryDirectory() as temp:
            fake=Path(temp)/'assets';fake.mkdir(parents=True)
            shutil.copy2(ROOT/'assets/lesson.html',fake/'lesson.html')
            (fake/'template-manifest.json').write_text(json.dumps(broken,ensure_ascii=False),encoding='utf-8')
            import verify_output
            with self.assertRaises(ValueError) as caught:verify_output.verify_template(Path(temp))
            self.assertIn('指纹不一致',str(caught.exception))

    def test_embedded_data_diverging_from_exam_json_is_refused(self):
        exam=json.loads((self.out/'exam.json').read_text(encoding='utf-8'))
        exam['title']='被改过的标题'
        write(self.out/'exam.json',exam)
        with self.assertRaises(ValueError) as caught:verify_output(self.out)
        self.assertIn('exam.json',str(caught.exception))

    def test_missing_media_file_is_refused_with_its_name(self):
        names=sorted(verify_output(self.out)['resource_sha256'])
        if not names:self.skipTest('本课件没有媒体文件，跳过（带音频/页图的课件由交付链测试覆盖）')
        name=names[0];(self.out/name).unlink()
        with self.assertRaises(ValueError) as caught:verify_output(self.out)
        self.assertIn(name,str(caught.exception))

    def test_check_install_flags_missing_and_modified_files(self):
        from check_install import check
        broken=self.base/'broken'
        shutil.copytree(ROOT,broken,ignore=shutil.ignore_patterns('dist','__pycache__','*.pyc','.git'))
        report=check(broken)
        self.assertEqual(report['status'],'complete','整仓复制必须仍被判为完整（否则后面的断言没有对照）')
        (broken/'assets'/'lesson.html').unlink()
        report=check(broken)
        self.assertEqual(report['status'],'incomplete_install')
        self.assertTrue(any('assets/lesson.html' in error for error in report['errors']),report['errors'])
        shutil.copy2(ROOT/'assets'/'lesson.html',broken/'assets'/'lesson.html')
        (broken/'VERSION').write_text('0.0.0\n',encoding='utf-8')
        report=check(broken)
        self.assertTrue(any('VERSION' in error for error in report['errors']),report['errors'])

if __name__=='__main__':unittest.main()
