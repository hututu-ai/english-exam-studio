"""The update path: verify, extract safely, compare, then optionally apply.

docs/UPDATE.md asks the agent to verify SHA256SUMS, extract without allowing absolute paths,
`..`, symlinks or hidden files, confirm the package is complete, warn about the teacher's own
edits, and only then replace files. Doing that by hand is where updates break — and a half
copied skill is painful to recover on Windows.
"""
import hashlib,json,os,shutil,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import extract_package

def run(*args):
    return subprocess.run([sys.executable,str(ROOT/'scripts/extract_package.py'),*map(str,args)],
                          capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class UpdateFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.base=Path(cls.temp.name)
        # 用真实包做夹具：package_skill 会重建清单并校验完整性
        cls.pkg=cls.base/'pkg'
        shutil.copytree(ROOT,cls.pkg,ignore=shutil.ignore_patterns('__pycache__','.git','output','work'))
        made=subprocess.run([sys.executable,str(cls.pkg/'scripts/package_skill.py'),str(cls.base/'update.zip')],
                            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180,cwd=str(cls.pkg))
        assert made.returncode==0,made.stderr
        # 不再手写 SHA256SUMS.txt：更新文档要求老师下载它，所以它必须由打包脚本自己产出。
        # 这里直接用产物，等于每次回归都在验证"发布 → 下载 → 核对"这条真链路。
        assert (cls.base/'SHA256SUMS.txt').is_file(),'package_skill.py 必须同时产出 SHA256SUMS.txt'
        cls.sums=cls.base/'SHA256SUMS.txt'
        recorded=dict(line.split()[::-1] for line in cls.sums.read_text(encoding='utf-8').splitlines() if len(line.split())>=2)
        assert recorded.get('update.zip')==sha256(cls.base/'update.zip'),'发布的 SHA256SUMS.txt 条目必须与 ZIP 指纹一致'
        cls.addClassCleanup(cls.temp.cleanup)
    def test_verification_accepts_the_right_checksum_and_rejects_a_wrong_one(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            good=run(self.base/'update.zip','--sha256sums',self.sums,'--out',root/'out')
            self.assertEqual(good.returncode,0,good.stdout[-600:])
            self.assertEqual(json.loads(good.stdout)['verification']['status'],'passed')
            (root/'BAD.txt').write_text(f'{"0"*64}  update.zip\n',encoding='utf-8')
            bad=run(self.base/'update.zip','--sha256sums',root/'BAD.txt','--out',root/'out-bad')
            self.assertEqual(bad.returncode,1)
            self.assertIn('指纹与 SHA256SUMS.txt 不一致',json.loads(bad.stdout)['error'])
            (root/'MISSING.txt').write_text(f'{"0"*64}  other.zip\n',encoding='utf-8')
            missing=run(self.base/'update.zip','--sha256sums',root/'MISSING.txt','--out',root/'out-missing')
            self.assertEqual(missing.returncode,1)
            self.assertIn('没有这个压缩包的条目',json.loads(missing.stdout)['error'])
    def test_apply_refuses_before_touching_anything_when_a_file_is_not_writable(self):
        """Windows 上 OneDrive/杀毒/Office 会占住文件：预检必须在动手前拒绝，别留"改了一半"的技能目录。"""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            current=root/'current';extracted=root/'new'
            for base,version in ((current,'1.0.0'),(extracted,'1.1.0')):
                (base/'scripts').mkdir(parents=True,exist_ok=True)
                (base/'VERSION').write_text(version+'\n',encoding='utf-8')
                (base/'SKILL.md').write_text('# skill '+version,encoding='utf-8')
            target=current/'SKILL.md';os.chmod(target,0o444)
            try:
                with self.assertRaises(ValueError) as caught:
                    extract_package.apply_update(current,extracted,root/'backup')
                message=str(caught.exception)
                self.assertIn('SKILL.md',message)
                self.assertIn('现在没有改动任何文件',message)
                self.assertIn('只读',message)
                self.assertEqual(target.read_text(encoding='utf-8').strip(),'# skill 1.0.0','预检拒绝时不能动文件')
                self.assertEqual((current/'VERSION').read_text(encoding='utf-8').strip(),'1.0.0')
                self.assertFalse((root/'backup').exists(),'预检阶段不该已经建了备份')
            finally:os.chmod(target,0o644)

    def test_midway_copy_failure_rolls_back_and_names_the_right_file(self):
        """复制到一半失败（文件被占用）：用备份回滚，并说清失败的是哪个文件、备份在哪。"""
        import shutil as _shutil
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            current=root/'current';extracted=root/'new'
            for base,version in ((current,'1.0.0'),(extracted,'1.1.0')):
                (base/'scripts').mkdir(parents=True,exist_ok=True)
                (base/'VERSION').write_text(version+'\n',encoding='utf-8')
                (base/'SKILL.md').write_text('# skill '+version,encoding='utf-8')
            real=_shutil.copy2;calls={'n':0}
            def flaky(src,dst,*args,**kwargs):
                calls['n']+=1
                if calls['n']==2:raise OSError(13,'Permission denied')
                return real(src,dst,*args,**kwargs)
            with patch.object(extract_package.shutil,'copy2',side_effect=flaky):
                with self.assertRaises(ValueError) as caught:
                    extract_package.apply_update(current,extracted,root/'backup')
            message=str(caught.exception)
            self.assertIn('复制 VERSION 时失败',message,'要点名真正失败的文件，不能报成另一个')
            self.assertIn('恢复成更新前的内容',message)
            self.assertIn(str((root/'backup').resolve()),message,'要给出手动恢复的位置')
            self.assertEqual((current/'SKILL.md').read_text(encoding='utf-8').strip(),'# skill 1.0.0')
            self.assertEqual((current/'VERSION').read_text(encoding='utf-8').strip(),'1.0.0')
            self.assertTrue((root/'backup'/'SKILL.md').is_file(),'备份要真的存在，回滚才有依据')

    def test_rollback_that_also_fails_is_reported_not_pretended(self):
        """回滚也可能被同一个占用挡住：这时必须说出"哪些没回滚、从备份手动复制"，不能声称已恢复。"""
        import shutil as _shutil
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            current=root/'current';extracted=root/'new'
            for base,version in ((current,'1.0.0'),(extracted,'1.1.0')):
                (base/'scripts').mkdir(parents=True,exist_ok=True)
                (base/'VERSION').write_text(version+'\n',encoding='utf-8')
                (base/'SKILL.md').write_text('# skill '+version,encoding='utf-8')
            real=_shutil.copy2;calls={'n':0}
            def flaky(src,dst,*args,**kwargs):
                calls['n']+=1
                if calls['n']>=2:raise OSError(13,'Permission denied')
                return real(src,dst,*args,**kwargs)
            with patch.object(extract_package.shutil,'copy2',side_effect=flaky):
                with self.assertRaises(ValueError) as caught:
                    extract_package.apply_update(current,extracted,root/'backup')
            message=str(caught.exception)
            self.assertIn('没能回滚',message)
            self.assertIn('手动复制回去',message)
            self.assertIn('已把本次改动过的 0 个文件恢复',message,'没恢复成功就不能说恢复了')

    def test_windows_style_and_ads_paths_are_rejected(self):
        """Windows 老师更可能遇到：盘符路径、反斜杠、以及下载文件带上的 Zone.Identifier 数据流。"""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);evil=root/'evil.zip'
            with zipfile.ZipFile(evil,'w') as bundle:
                bundle.writestr('C:\\Windows\\x.txt','pwned')
                bundle.writestr('..\\escaped.txt','pwned')
                bundle.writestr('fine.txt:Zone.Identifier','[ZoneTransfer]')
            result=run(evil,'--out',root/'out')
            self.assertEqual(result.returncode,1)
            report=json.loads(result.stdout)
            reasons={item['entry']:item['reason'] for item in report['extract']['rejected']}
            self.assertEqual(len(reasons),3,reasons)
            self.assertTrue(all('绝对路径' in reason or '跳出解压目录' in reason or '反斜杠' in reason or '冒号' in reason
                                for reason in reasons.values()),reasons)

    def test_malicious_archive_is_refused_loudly_and_nothing_escapes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);evil=root/'evil.zip'
            with zipfile.ZipFile(evil,'w') as bundle:
                bundle.writestr('../escaped.txt','pwned')
                bundle.writestr('/absolute.txt','pwned')
                bundle.writestr('.hidden/secret','x')
                bundle.writestr('__MACOSX/junk','x')
                link=zipfile.ZipInfo('link');link.create_system=3;link.external_attr=0o120777<<16
                bundle.writestr(link,'/etc/passwd')
                bundle.writestr('fine.txt','ok')
            result=run(evil,'--out',root/'out')
            self.assertEqual(result.returncode,1)
            report=json.loads(result.stdout)
            reasons={item['entry']:item['reason'] for item in report['extract']['rejected']}
            self.assertEqual(len(reasons),5,reasons)
            self.assertFalse((root/'escaped.txt').exists(),'path traversal must not escape')
            self.assertFalse((root/'out'/'link').exists(),'symlink must not be created')
            self.assertTrue((root/'out'/'fine.txt').is_file(),'safe entries still extract')
    def test_extract_reports_complete_install_and_flat_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result=run(self.base/'update.zip','--out',root/'out')
            self.assertEqual(result.returncode,0,result.stdout[-600:])
            report=json.loads(result.stdout)
            self.assertEqual(report['installation']['status'],'complete')
            self.assertEqual(report['package_root'],str(root/'out'))
    def test_nested_package_root_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);nested=root/'nested.zip'
            with zipfile.ZipFile(nested,'w') as bundle:
                bundle.writestr('english-exam-studio/SKILL.md','x')
                bundle.writestr('english-exam-studio/VERSION','1.0.0\n')
            run(nested,'--out',root/'out')
            self.assertEqual(extract_package.package_root(root/'out'),root/'out'/'english-exam-studio')
    def test_compare_flags_locally_edited_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);target=root/'target'
            shutil.copytree(self.pkg,target)
            (target/'VERSION').write_text('0.0.1\n',encoding='utf-8')          # teacher edited it
            (target/'我的笔记.md').write_text('note',encoding='utf-8')          # teacher's own file
            result=run(self.base/'update.zip','--out',root/'out','--compare-to',target)
            self.assertEqual(result.returncode,0,result.stdout[-600:])
            comparison=json.loads(result.stdout)['comparison']
            self.assertIn('VERSION',comparison['locally_modified'])
            self.assertEqual(comparison['added'],[])
            self.assertEqual(comparison['removed'],[])
    def test_apply_requires_a_backup_and_preserves_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);target=root/'target'
            shutil.copytree(self.pkg,target)
            (target/'VERSION').write_text('0.0.1\n',encoding='utf-8')
            (target/'我的笔记.md').write_text('note',encoding='utf-8')
            refused=run(self.base/'update.zip','--out',root/'out','--compare-to',target,'--apply')
            self.assertEqual(refused.returncode,1)
            self.assertIn('--backup',json.loads(refused.stdout)['error'])
            self.assertEqual((target/'VERSION').read_text(encoding='utf-8').strip(),'0.0.1','nothing may change without a backup')
            applied=run(self.base/'update.zip','--out',root/'out','--compare-to',target,'--apply','--backup',root/'backup')
            self.assertEqual(applied.returncode,0,applied.stdout[-600:])
            self.assertNotEqual((target/'VERSION').read_text(encoding='utf-8').strip(),'0.0.1','the update must land')
            self.assertEqual((root/'backup'/'VERSION').read_text(encoding='utf-8').strip(),'0.0.1','the backup keeps the old file')
            self.assertTrue((target/'我的笔记.md').is_file(),"the teacher's own note must survive")
            again=run(self.base/'update.zip','--out',root/'out2','--compare-to',target,'--apply','--backup',root/'backup')
            self.assertEqual(again.returncode,1)
            self.assertIn('备份目录已存在',json.loads(again.stdout)['error'])
