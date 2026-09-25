import base64,contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import build,make_browser_fixture as fixture
from test_verify_output_gates import VerifyOutputGates
class PortableGates(VerifyOutputGates):
    def test_export_template_tamper(self):
        d=self.payload();d['_export_template']=base64.b64encode(b'bad').decode();self.rewrite_payload(d);self.assert_refused('单文件导出模板与当前模板不一致')
    def test_image_tamper(self):
        d=self.payload();name=next(iter(d['_embedded_images']));d['_embedded_images'][name]='data:image/png;base64,YmFk';self.rewrite_payload(d);self.assert_refused('内嵌图像与来源文件不一致')
    def test_image_escape(self):
        d=self.payload();d['_embedded_images']['../bad']='data:image/png;base64,YmFk';self.rewrite_payload(d);self.assert_refused('内嵌图像路径越界')
    def test_portable_template_and_all_images_present(self):
        d=self.payload();self.assertEqual(base64.b64decode(d['_export_template']).decode(),(ROOT/'assets/lesson.html').read_text(encoding='utf-8'));self.assertEqual(len(d['_embedded_images']),4)
class AudioConversion(unittest.TestCase):
    def test_unsupported_audio_fails_clearly_when_tool_missing(self):
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);d=fixture.paper_document(b);(b/'full.ogg').write_bytes((b/'full.wav').read_bytes());d['full_audio']='full.ogg';d['sections'][0]['audio']='full.ogg';src,ledger=fixture.write_paper(b,d)
            with patch.object(build,'find_tool',return_value=None),self.assertRaisesRegex(ValueError,'该录音需要转换为兼容手机的 MP3'):
                build._render(src,b/'out',ledger)
    def test_conversion_error_is_not_hidden(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);d=fixture.paper_document(b);(b/'full.ogg').write_bytes((b/'full.wav').read_bytes());d['full_audio']='full.ogg';d['sections'][0]['audio']='full.ogg';src,ledger=fixture.write_paper(b,d)
            with patch.object(build,'find_tool',return_value='ffmpeg'),patch.object(build.subprocess,'run',return_value=SimpleNamespace(returncode=1,stderr=b'bad codec')),self.assertRaisesRegex(ValueError,'兼容音频转换失败：'):
                build._render(src,b/'out',ledger)
