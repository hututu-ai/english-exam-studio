import hashlib,io,json,os,sys,tarfile,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import extract_package,prepare_whisper as setup
DEMO_MODEL=b'model-bytes'*100
DEMO_SHA=hashlib.sha256(DEMO_MODEL).hexdigest()
def demo_tarball(target):
    with tarfile.open(target,'w:gz') as t:
        def add(name,data,mode=0o644):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=mode;t.addfile(info,io.BytesIO(data))
        add('whisper.cpp/CMakeLists.txt',b'project(whisper)')
        add('whisper.cpp/build/whisper-cli',b'#!/bin/sh\n',0o755)
    return target
class WhisperSetup(unittest.TestCase):
    def test_plan_never_downloads_and_explains_location(self):
        with tempfile.TemporaryDirectory() as t,patch.object(setup,'fetch',side_effect=AssertionError('Network unexpected')):
            root=Path(t)/'tools';r=setup.prepare(root);self.assertEqual(r['status'],'plan');self.assertFalse(root.exists())
    def test_windows_architecture_and_digest(self):
        releases=[{'tag_name':'v1','assets':[{'name':'whisper-bin-x64.zip','digest':'sha256:'+'a'*64},{'name':'whisper-bin-arm64.zip','digest':'sha256:'+'b'*64}]}]
        self.assertEqual(setup.windows_asset(releases,'AMD64')[1]['name'],'whisper-bin-x64.zip')
        self.assertEqual(setup.windows_asset(releases,'ARM64')[1]['name'],'whisper-bin-arm64.zip')
        with self.assertRaises(ValueError):setup.windows_asset(releases,'mips')
    def test_archive_traversal_and_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);z=root/'bad.zip'
            with zipfile.ZipFile(z,'w') as f:f.writestr('../outside','bad')
            with self.assertRaises(ValueError):setup.unpack(z,root/'out')
            with zipfile.ZipFile(z,'w') as f:
                f.writestr('__MACOSX/file','skip');f.writestr('folder/runtime.dll','real')
                link=zipfile.ZipInfo('folder/link');link.create_system=3;link.external_attr=0o120777<<16;f.writestr(link,'/outside')
            setup.unpack(z,root/'clean');self.assertFalse((root/'clean/folder/link').exists());self.assertTrue((root/'clean/folder/runtime.dll').exists())
    def test_zero_exit_without_transcript_is_failure(self):
        import audio
        with tempfile.TemporaryDirectory() as t:
            stem=Path(t)/'result'
            with patch.object(audio,'whisper_exe',return_value='whisper-cli'),patch.object(audio,'run',return_value='failed to read audio'):
                with self.assertRaisesRegex(ValueError,'未生成转写'):audio.whisper_rows('input.wav','model.bin','en',stem,1,10,True)

    def test_verified_runtime_reuses_offline(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);binary=root/'whisper-cli';binary.write_text('stub');model=root/'model.bin';model.write_bytes(b'test model')
            (root/'runtime.json').write_text(json.dumps({'whisper_bin':str(binary),'whisper_model':str(model),'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest()}))
            with patch.object(setup,'run',return_value='help'),patch.object(setup,'fetch',side_effect=AssertionError('Network unexpected')):
                self.assertTrue(setup.prepare(root,True)['reused'])

    def test_tar_runtime_keeps_exec_bit_and_skips_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);good=root/'good.tar.gz'
            with tarfile.open(good,'w:gz') as tar:
                def add(name,data,mode=0o644,kind=tarfile.REGTYPE):
                    info=tarfile.TarInfo(name);info.mode=mode;info.type=kind
                    if kind==tarfile.REGTYPE:info.size=len(data);tar.addfile(info,io.BytesIO(data))
                    else:info.linkname=data.decode();tar.addfile(info)
                add('whisper.cpp/build/whisper-cli',b'#!/bin/sh\n',0o755)
                add('whisper.cpp/README.md',b'read me')
                add('whisper.cpp/evil',b'/outside',kind=tarfile.SYMTYPE)
            out=root/'out';setup.unpack(good,out)
            binary=out/'whisper.cpp/build/whisper-cli'
            self.assertTrue(binary.is_file())
            if os.name=='nt':
                # Windows 没有 POSIX 执行位（chmod 只影响只读标记），这条断言在那边没有意义；
                # 跳过而不是让它失败——CI 的 Windows 格就是靠这条才没被误判成"解压坏了"。
                self.skipTest('Windows 没有可执行位概念，执行位断言跳过')
            self.assertTrue(binary.stat().st_mode&0o100,'解压后应保留执行位')
            self.assertFalse((out/'whisper.cpp/evil').exists());self.assertTrue((out/'whisper.cpp/README.md').is_file())
            with self.assertRaises(ValueError)as caught:
                bad=root/'bad.tar.gz'
                with tarfile.open(bad,'w:gz') as tar:
                    info=tarfile.TarInfo('../outside.txt');info.size=4;tar.addfile(info,io.BytesIO(b'evil'))
                setup.unpack(bad,root/'escaped')
            self.assertIn('不安全',str(caught.exception));self.assertFalse((root/'outside.txt').exists())

    def test_macos_prepare_downloads_builds_and_verifies_model(self):
        platform_patch=patch.object(setup.platform,'system',return_value='Darwin');platform_patch.start();self.addCleanup(platform_patch.stop)
        calls=[]
        def fake_fetch(url,target=None,deadline=None):
            calls.append(url)
            if 'huggingface.co/api/models' in url:
                return {'sha':'rev123','siblings':[{'rfilename':'ggml-base.bin','lfs':{'sha256':DEMO_SHA}}]}
            if 'resolve/' in url:Path(target).write_bytes(DEMO_MODEL);return Path(target)
            if 'releases/latest' in url:return {'tag_name':'v1.7.4','tarball_url':'http://x/src.tar.gz'}
            return demo_tarball(Path(target))
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'tools'
            with patch.object(setup,'fetch',side_effect=fake_fetch),patch.object(setup,'whisper_bin',return_value=None),\
                 patch.object(setup.shutil,'which',side_effect=lambda name:'/usr/bin/'+name),patch.object(setup,'run',return_value='ok'):
                report=setup.prepare(root,True,seconds=30)
            self.assertEqual(report['status'],'ready_for_smoke_test')
            self.assertNotIn('reused',report)
            self.assertEqual(report['model_sha256'],DEMO_SHA)
            self.assertTrue(Path(report['whisper_bin']).is_file())
            self.assertEqual((root/'models/ggml-base.bin').read_bytes(),DEMO_MODEL)
            self.assertTrue((root/'runtime.json').is_file())
            self.assertEqual(list((root/'models').glob('*.download')),[],'校验完成后不应留下半成品')
            self.assertTrue(any('huggingface' in u for u in calls))

    def test_model_digest_mismatch_refuses_to_install(self):
        platform_patch=patch.object(setup.platform,'system',return_value='Darwin');platform_patch.start();self.addCleanup(platform_patch.stop)
        def fake_fetch(url,target=None,deadline=None):
            if 'huggingface.co/api/models' in url:
                return {'sha':'rev123','siblings':[{'rfilename':'ggml-base.bin','lfs':{'sha256':'0'*64}}]}
            if 'resolve/' in url:Path(target).write_bytes(DEMO_MODEL);return Path(target)
            if 'releases/latest' in url:return {'tag_name':'v1.7.4','tarball_url':'http://x/src.tar.gz'}
            return demo_tarball(Path(target))
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'tools'
            with patch.object(setup,'fetch',side_effect=fake_fetch),patch.object(setup,'whisper_bin',return_value=None),\
                 patch.object(setup.shutil,'which',side_effect=lambda name:'/usr/bin/'+name),patch.object(setup,'run',return_value='ok'):
                with self.assertRaisesRegex(ValueError,'模型校验失败'):setup.prepare(root,True,seconds=30)
            self.assertFalse((root/'models/ggml-base.bin').exists())
            self.assertFalse((root/'runtime.json').exists(),'校验没过就不该写运行时凭据')

    def test_path_safety_rules_agree_across_modules(self):
        hostile=['/etc/passwd','C:/windows/system32','..\\..\\evil','../outside.txt','a/../../b','','.','.git/config','__MACOSX/x','a/__MACOSX/b','sub\\evil','x:y']
        benign=['whisper.cpp/build/whisper-cli','models/ggml-base.bin','a/b/c.txt']
        for name in hostile:
            with self.subTest(name=name):
                ok,reason=extract_package.safe_parts(name)
                self.assertFalse(ok,name+' 应被 extract_package 拒绝')
                self.assertTrue(reason)
                try:accepted=setup.safe_name(name)
                except ValueError:accepted=False
                self.assertFalse(accepted,name+' 应被 prepare_whisper 拒绝')
        for name in benign:
            with self.subTest(name=name):
                self.assertTrue(extract_package.safe_parts(name)[0])
                self.assertTrue(setup.safe_name(name))
if __name__=='__main__':unittest.main()
