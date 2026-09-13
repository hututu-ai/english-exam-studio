import hashlib,json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import prepare_whisper as setup
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
if __name__=='__main__':unittest.main()
