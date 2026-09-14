"""图片选项：初中卷「听句子选图」的 A/B/C 是图片，不能用文字描述代替。

1.0.50 之前 `q.options` 只能是文字，图片选项无处安放：老师给了选图题，助手只能写"图A/图B"，
课件里学生看到的是文字而不是图。这里验收新字段 `option_images`：

  {"options":{"A":"","B":"","C":""},
   "option_images":{"A":"assets/q1-a.png","B":"assets/q1-b.png","C":"assets/q1-c.png"},
   "answer":"B"}

要点：构建要把图片复制进课件；`verify_output` 与 `browser_check.cjs` 的媒体指纹必须包含这些图片
（1.0.37 就是漏了一处，导致整类课件永远交付不出去）；图片选项照旧能点选；文字选项与图片选项可混用。
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build
from verify_output import verify_output

def png(path,width,height,color):
    raw=b''.join(b'\x00'+bytes(color)*width for _ in range(height))
    def chunk(tag,data):
        import binascii
        return struct.pack('>I',len(data))+tag+data+struct.pack('>I',binascii.crc32(tag+data)&0xffffffff)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))

def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

class OptionImages(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 图片选项 ')
        self.base=Path(self.temp.name)
        self.exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
    def tearDown(self):self.temp.cleanup()

    def lesson(self,images=True,letters=('A','B','C')):
        exam=json.loads(json.dumps(self.exam,ensure_ascii=False))
        section=exam['sections'][0];question=section['questions'][0]
        for index,letter in enumerate(letters):
            question['options'][letter]=''
            if images:
                png(self.base/f'q1-{letter}.png',60,40,(30+index*40,60,90))
        question['option_images']={letter:f'q1-{letter}.png' for letter in letters}
        question['option_alts']={letter:f'第{question["id"]}题选项{letter}的图片（合成测试图）' for letter in letters}
        question['answer']='B' if 'B' in letters else letters[0]
        question['answer_source']='答案原件第 %s 题' % question['id']
        source=self.base/'exam.json';write(source,exam)
        ledger={'sources':[{'role':'original_demo','path':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}],
                'sections':exam['sections']}
        ledger_path=self.base/'source-ledger.json';write(ledger_path,ledger)
        return source,ledger_path

    def test_build_copies_option_images_and_fingerprints_them(self):
        source,ledger=self.lesson()
        out=self.base/'out'
        with contextlib.redirect_stdout(io.StringIO()):build.build(source,out,ledger)
        built=json.loads((out/'exam.json').read_text(encoding='utf-8'))
        question=built['sections'][0]['questions'][0]
        names=question['option_images']
        self.assertEqual(sorted(names),['A','B','C'])
        for name in names.values():
            self.assertTrue(name.startswith('assets/'),name)
            self.assertTrue((out/name).is_file(),f'{name} 没有被复制进课件')
        verified=verify_output(out)
        self.assertEqual(verified['status'],'passed')
        for name in names.values():
            self.assertIn(name,verified['resource_sha256'],'选项图片必须进媒体指纹，否则浏览器验收与打包会对不上')

    def test_browser_and_template_fingerprint_the_same_media_set(self):
        """跨工具契约：node 端收集的媒体必须与 verify_output 完全一致。"""
        node=shutil.which('node')
        if not node:self.skipTest('node 不可用')
        source,ledger=self.lesson()
        out=self.base/'out-shared'
        with contextlib.redirect_stdout(io.StringIO()):build.build(source,out,ledger)
        environment={key:value for key,value in os.environ.items() if key!='PLAYWRIGHT_MODULE'}
        subprocess.run([node,str(ROOT/'scripts/browser_check.cjs'),str(out)],capture_output=True,
                       text=True,encoding='utf-8',errors='replace',timeout=60,env=environment)
        evidence=json.loads((out/'browser-check.json').read_text(encoding='utf-8'))
        self.assertEqual(sorted(evidence.get('media_sha256',{})),sorted(verify_output(out)['resource_sha256']),
                         '选项图片必须同时被两边指纹，否则 package_lesson 会拒绝交付整类课件')

    def test_validation_rejects_mismatched_or_empty_image_options(self):
        source,ledger=self.lesson()
        exam=json.loads(source.read_text(encoding='utf-8'))
        bad=json.loads(json.dumps(exam,ensure_ascii=False))
        bad['sections'][0]['questions'][0]['option_images']['E']='q1-A.png'   # E 不在 options 里
        with self.assertRaises(ValueError) as caught:build.validate(bad)
        self.assertIn('没有对应选项的字母',str(caught.exception))
        blank=json.loads(json.dumps(exam,ensure_ascii=False))
        blank['sections'][0]['questions'][0]['option_images'].pop('C')
        with self.assertRaises(ValueError) as caught:build.validate(blank)
        self.assertIn('既没有文字也没有图片',str(caught.exception))
        empty=json.loads(json.dumps(exam,ensure_ascii=False))
        empty['sections'][0]['questions'][0]['option_images']={}
        with self.assertRaises(ValueError) as caught:build.validate(empty)
        self.assertIn('option_images',str(caught.exception))

    def test_text_and_image_options_can_mix(self):
        source,ledger_path=self.lesson(letters=('A','B'))
        exam=json.loads(source.read_text(encoding='utf-8'))
        exam['sections'][0]['questions'][0]['options']['C']='a written option'
        write(source,exam)
        ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
        ledger['sources'][0]['sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
        ledger['sections']=exam['sections']          # 台账与试卷必须同时更新，否则证据链对不上（构建会拦）
        write(ledger_path,ledger)
        out=self.base/'out-mixed'
        with contextlib.redirect_stdout(io.StringIO()):build.build(source,out,ledger_path)
        built=json.loads((out/'exam.json').read_text(encoding='utf-8'))
        question=built['sections'][0]['questions'][0]
        self.assertEqual(sorted(question['option_images']),['A','B'])
        self.assertEqual(question['options']['C'],'a written option')

class OptionImagesInBrowser(unittest.TestCase):
    def chrome_binary(self):
        candidates=[os.environ.get('CHROME_BIN'),'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',shutil.which('google-chrome'),
                    shutil.which('chromium'),shutil.which('microsoft-edge')]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():return candidate
        return None

    def test_images_load_and_still_select(self):
        node=shutil.which('node')
        if not node:self.skipTest('node 不可用')
        module=os.environ.get('PLAYWRIGHT_MODULE','playwright')
        probe=subprocess.run([node,'-e',f"try{{require({module!r})}}catch(e){{process.exit(3)}}"],capture_output=True,timeout=60)
        if probe.returncode!=0:self.skipTest('Playwright 不可用，跳过真实浏览器验收')
        chrome=self.chrome_binary()
        if not chrome:self.skipTest('没有可用的 Chrome/Edge，跳过真实浏览器验收')
        holder=OptionImages('test_build_copies_option_images_and_fingerprints_them');holder.setUp()
        try:
            source,ledger=holder.lesson();out=holder.base/'out-browser'
            with contextlib.redirect_stdout(io.StringIO()):build.build(source,out,ledger)
            environment={**os.environ,'CHROME_BIN':chrome,'BROWSER_ENGINE':'chromium'}
            result=subprocess.run([node,str(ROOT/'scripts/browser_check.cjs'),str(out)],capture_output=True,
                                  text=True,encoding='utf-8',errors='replace',timeout=300,env=environment)
            evidence=json.loads((out/'browser-check.json').read_text(encoding='utf-8'))
            self.assertEqual(evidence['status'],'passed',result.stdout[-1200:]+result.stderr[-400:])
            names=[item['name'] for item in evidence['checks']]
            self.assertIn('option-images-render-and-select',names,'图片选项必须在真实浏览器里加载出来并能点选')
        finally:
            holder.tearDown()

if __name__=='__main__':unittest.main()
