"""产出核验（`verify_output`）的交付级判据逐条反向验证（1.0.116）。

这 7 条判据此前只有 1 条被测试提到过，其余 6 条——"HTML 被改过""内嵌音频与登记的不一致"
"内嵌音频值不是 base64""内嵌音频内容与 audio/ 里的不同""媒体文件缺失或为空""内嵌数据与
exam.json 不一致"——都是**交付阻断级**：老师拿到的课件和构建时那一份不一致时，它们负责拦下。
判据改松了以前不会有任何测试报警，这里逐条注入缺陷。
"""
import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'tests'))
import make_browser_fixture as fixture
from verify_output import verify_output

EXAM_DATA=re.compile(r'<script\b(?=[^>]*\bid="examData")[^>]*>(.*?)</script\s*>',re.S)


class VerifyOutputGates(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 产出核验判据 ')
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.out=self.base/'out'
        with contextlib.redirect_stdout(io.StringIO()):
            fixture.make(self.base/'seed',self.out)
    def payload(self):
        html=(self.out/'index.html').read_text(encoding='utf-8')
        return json.loads(EXAM_DATA.search(html).group(1))
    def rewrite_payload(self,data):
        html=(self.out/'index.html').read_text(encoding='utf-8')
        match=EXAM_DATA.search(html)
        (self.out/'index.html').write_text(html[:match.start(1)]+json.dumps(data,ensure_ascii=False)+html[match.end(1):],encoding='utf-8')
    def assert_refused(self,fragment):
        with self.assertRaises(ValueError) as caught:verify_output(self.out)
        self.assertIn(fragment,str(caught.exception))

    def test_clean_output_passes(self):
        self.assertEqual(verify_output(self.out)['status'],'passed')

    def test_two_exam_data_blocks_are_refused_with_a_count(self):
        """页面里出现两份数据块（手工粘贴/宿主注入）必须点名"应正好 1 个"。"""
        html=(self.out/'index.html').read_text(encoding='utf-8')
        match=EXAM_DATA.search(html)
        (self.out/'index.html').write_text(html[:match.end()]+html[match.start():match.end()]+html[match.end():]+'\n<!-- 手工加的一行 -->\n',encoding='utf-8')
        self.assert_refused('examData 数据块应正好 1 个')
    def test_broken_payload_is_reported_in_chinese_not_a_raw_json_error(self):
        """模板首尾仍然吻合、但数据块被粘成两份时，以前漏的是英文 JSONDecodeError。"""
        html=(self.out/'index.html').read_text(encoding='utf-8')
        match=EXAM_DATA.search(html)
        (self.out/'index.html').write_text(html[:match.end()]+html[match.start():match.end()]+html[match.end():],encoding='utf-8')
        with self.assertRaises(ValueError) as caught:verify_output(self.out)
        message=str(caught.exception)
        self.assertIn('不是合法 JSON',message)
        self.assertIn('重新构建',message)

    def test_hand_edited_html_is_refused(self):
        html=(self.out/'index.html').read_text(encoding='utf-8')
        (self.out/'index.html').write_text(html+'\n<!-- 手工加的一行 -->\n',encoding='utf-8')
        self.assert_refused('生成的 HTML 与官方模板不一致')
    def test_payload_disagreeing_with_exam_json_is_refused(self):
        data=self.payload();data['title']='被改过的标题';self.rewrite_payload(data)
        self.assert_refused('内嵌的考试数据与 exam.json 不一致')
    def test_missing_media_file_is_refused(self):
        (self.out/'audio'/'Q1.wav').unlink()
        self.assert_refused('缺少或无效的媒体文件')
    def test_truncated_embedded_audio_is_refused_as_a_content_mismatch(self):
        """音频被截成 0 字节：内嵌内容与磁盘文件不一致，报"内容不一致"比"缺文件"更准确。"""
        (self.out/'audio'/'Q1.wav').write_bytes(b'')
        self.assert_refused('内嵌音频与 audio/ 里的同名文件内容不一致')
    def test_empty_or_missing_non_audio_media_is_refused(self):
        """页图被清空（非内嵌资源）走的是资源清单那条：文件为空等于成品缺图。"""
        (self.out/'sources'/'A-paper-1.png').write_bytes(b'')
        self.assert_refused('缺少或无效的媒体文件')
    def test_embedded_audio_set_must_match_the_registered_files(self):
        data=self.payload();data['_embedded_audio'].pop(next(iter(data['_embedded_audio'])))
        self.rewrite_payload(data)
        self.assert_refused('内嵌音频与音频文件不一致')
    def test_embedded_audio_value_must_be_base64(self):
        """值不是 `data:…;base64,…` 时页面里根本播不出声，必须点名而不是说成"找不到文件"。"""
        data=self.payload();data['_embedded_audio']['audio/Q1.wav']='audio/Q1.wav'
        self.rewrite_payload(data)
        self.assert_refused('不是 data:')
    def test_embedded_audio_without_a_registered_file_is_refused(self):
        """手改 HTML：声明成 folder 模式，却偷偷多内嵌一段音频。"""
        data=self.payload();data['audio_delivery']['mode']='folder'
        data['_embedded_audio']['audio/悄悄加的.wav']='data:audio/mpeg;base64,AAAA'
        self.rewrite_payload(data)
        sync=dict(data);sync.pop('_embedded_audio');sync.pop('_embedded_images',None);sync.pop('_export_template',None)      # exam.json 里没有内嵌音频这份数据
        (self.out/'exam.json').write_text(json.dumps(sync,ensure_ascii=False),encoding='utf-8')
        self.assert_refused('出现了没有对应音频文件的内嵌音频')
    def test_embedded_audio_content_must_match_the_file(self):
        data=self.payload();name=next(iter(data['_embedded_audio']))
        prefix,blob=data['_embedded_audio'][name].split(';base64,',1)
        flipped='A' if blob[0]!='A' else 'B'
        data['_embedded_audio'][name]=prefix+';base64,'+flipped+blob[1:]
        self.rewrite_payload(data)
        self.assert_refused('同名文件内容不一致')

    def test_packaging_refuses_a_symlink_in_the_delivery_folder(self):
        """交付文件夹里混进软链接时不能打包：解压方可能拿到指向别处的文件。"""
        from package_lesson import package
        try:
            (self.out/'audio'/'link.wav').symlink_to(self.out/'audio'/'Q1.wav')
        except (OSError,NotImplementedError) as error:
            self.skipTest(f'本机不支持创建软链接：{error}')
        with self.assertRaises(ValueError) as caught:
            package(self.out,self.base/'lesson.zip',allow_unchecked=True)
        self.assertIn('交付文件夹不能包含软链接',str(caught.exception))

    def test_every_check_message_is_asserted_somewhere_in_the_tests(self):
        """守卫：交付闸门里每条判据的说明，都必须在测试里被断言过（哪怕只匹配其中一段）。

        范围是"交付阻断级"的三个文件：`verify_output`（产出核验）、`package_lesson`（打包闸门）、
        `qa_report`（人工复核闸门）。判据措辞改了而测试没跟上，这条会失败。
        """
        import ast
        tests='\n'.join(path.read_text(encoding='utf-8') for path in (ROOT/'tests').glob('*.py'))
        def asserted(text):
            # 只要消息里**有任何 5 字片段**出现在测试里就算覆盖（测试常只匹配中间一段）
            return any(text[i:i+5] in tests for i in range(max(0,len(text)-4)))
        # 这两条无法用真实文件自然触发：ZIP 完整性要文件系统/压缩层出错，软链接那条已由上面的用例覆盖。
        EXEMPT={( 'package_lesson.py','ZIP 完整性检查失败')}
        absent=[]
        for name in ('verify_output.py','package_lesson.py','qa_report.py'):
            source=(ROOT/'scripts'/name).read_text(encoding='utf-8')
            for node in ast.walk(ast.parse(source)):
                if not isinstance(node,ast.Raise) or node.exc is None:continue
                if not isinstance(node.exc,ast.Call) or not node.exc.args:continue
                pieces=[piece.value for piece in ast.walk(node.exc.args[0])
                        if isinstance(piece,ast.Constant) and isinstance(piece.value,str) and len(piece.value)>=8]
                if not pieces:continue          # 没有说明的报错（如 SystemExit(main())）不算判据
                if any((name,text[:24]) in EXEMPT for text in pieces):continue
                if not any(asserted(text) for text in pieces):
                    absent.append((name,node.lineno,pieces[0][:24]))
        self.assertEqual(absent,[],f'这些判据的说明没有任何测试断言过：{absent}')


if __name__=='__main__':unittest.main()
