"""空数组不等于"有内容"：一节带 `blanks: []` 的阅读课不能渲染成听力课。

真实卷跑出来的回归：九年级卷「四、阅读理解 A」的段落里有 `"blanks": []`（骨架与手写数据都常见），
页面与浏览器脚本用 `!!(s.audio||s.audio_note||s.blanks)` 判断听力——JS 里 `!![]` 是 **true**，
于是这一节被渲染成「Test A 第 51–55 题」并带上听力播放器，同时 `reconcile()` 又把真正跑过的
`only-one-analysis-open-per-section`、`paragraph-translation-toggles` 降级成"没有可测数据"，
交付报告因此少报了已验证的项。Python 侧 `bool([])` 是 False，所以只有 JS 三份副本有这个问题。

这里锁三件事：
1. Python 判断（空挖空不算听力、非空才算）；
2. 静态锁：三份 JS 里不得再用数组真值判断听力，也不得再按 kind 字符串判断听力；
3. 真浏览器锁：带 `blanks: []` 的阅读节必须按阅读渲染，且相关检查必须出现在"已执行"里。
"""
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
import build, section_kinds

class PresenceRules(unittest.TestCase):
    def test_python_treats_empty_blanks_as_no_blanks(self):
        reading={'kind':'阅读理解','blanks':[],'paragraphs':[{'id':'p1','text':'A passage.'}]}
        self.assertFalse(section_kinds.is_listening(reading))
        self.assertEqual(section_kinds.preset(reading),'reading')
        self.assertFalse(section_kinds.shape(reading)['audio'])
        # 没有题型名可判定时，才按挖空推断为听力；空数组仍然不算
        self.assertFalse(section_kinds.is_listening({'kind':'综合题','blanks':[]}))
        self.assertTrue(section_kinds.is_listening({'kind':'综合题','blanks':[{'paragraph_id':'p1','start':0,'end':3,'purpose':'x','question_ids':['1']}]}))
        # 题型名已经说明不是听力（阅读理解/短文填空）时，残留的挖空不改变呈现方式
        hearing=dict(reading,blanks=[{'paragraph_id':'p1','start':0,'end':3,'purpose':'x','question_ids':['1']}])
        self.assertFalse(section_kinds.is_listening(hearing),'题型名优先：阅读理解不会因为有挖空就变成听力节')

    def test_js_copies_do_not_use_array_truthiness_or_kind_names(self):
        for name in ('assets/lesson.html','scripts/browser_check.cjs'):
            text=(ROOT/name).read_text(encoding='utf-8')
            self.assertNotIn('s.audio||s.audio_note||s.blanks)',text,
                             f'{name}: 空数组 blanks 在 JS 里是 true，必须写成 (s.blanks||[]).length>0')
            self.assertIn('(s.blanks||[]).length',text,f'{name}: 缺少对 blanks 的非空判断')
            for pattern in ("s.kind==='listening'","s.kind!=='listening'","s.kind==='writing'",
                            "s.kind!=='writing'","s.kind==='reading'","s.kind==='grammar'"):
                self.assertNotIn(pattern,text,
                                 f'{name}: 不能按试题题型名判断呈现方式（{pattern}），请用 sectionPreset/isListening/isWriting 等 helper')

class PresenceInBrowser(unittest.TestCase):
    def chrome_binary(self):
        candidates=[os.environ.get('CHROME_BIN'),'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',shutil.which('google-chrome'),
                    shutil.which('chromium'),shutil.which('microsoft-edge')]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():return candidate
        return None

    def test_reading_section_with_empty_blanks_is_not_rendered_as_listening(self):
        node=shutil.which('node')
        if not node:self.skipTest('node 不可用')
        module=os.environ.get('PLAYWRIGHT_MODULE','playwright')
        probe=subprocess.run([node,'-e',f"try{{require({module!r})}}catch(e){{process.exit(3)}}"],capture_output=True,timeout=60)
        if probe.returncode!=0:self.skipTest('Playwright 不可用，跳过真实浏览器回归')
        chrome=self.chrome_binary()
        if not chrome:self.skipTest('没有可用的 Chrome/Edge，跳过真实浏览器回归')
        temp=tempfile.TemporaryDirectory(prefix='英语 skill 空挖空回归 ')
        base=Path(temp.name)
        exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
        for section in exam['sections']:
            section['blanks']=[]           # 关键：空数组，不是缺字段
        source=base/'exam.json';source.write_text(json.dumps(exam,ensure_ascii=False),encoding='utf-8')
        ledger=base/'source-ledger.json'
        ledger.write_text(json.dumps({'sources':[{'role':'original_demo','path':'exam.json',
            'sha256':__import__('hashlib').sha256(source.read_bytes()).hexdigest()}],'sections':exam['sections']},ensure_ascii=False),encoding='utf-8')
        import contextlib,io
        with contextlib.redirect_stdout(io.StringIO()):build._render(source,base/'out',ledger)
        environment={**os.environ,'CHROME_BIN':chrome,'BROWSER_ENGINE':'chromium'}
        result=subprocess.run([node,str(ROOT/'scripts/browser_check.cjs'),str(base/'out')],capture_output=True,
                              text=True,encoding='utf-8',errors='replace',timeout=300,env=environment)
        evidence=json.loads((base/'out'/'browser-check.json').read_text(encoding='utf-8'))
        self.assertEqual(evidence['status'],'passed',result.stdout[-1200:]+result.stderr[-400:])
        executed=[item['name'] for item in evidence['checks']]
        skipped=[item['name'] for item in evidence['skipped']]
        self.assertIn('only-one-analysis-open-per-section',executed,
                      '这一节有 2 道客观题，检查必须真跑，不能被当成"没有可测数据"')
        self.assertIn('paragraph-translation-toggles',executed,
                      '这一节有译文，检查必须真跑')
        self.assertNotIn('only-one-analysis-open-per-section',skipped)
        self.assertNotIn('paragraph-translation-toggles',skipped)
        temp.cleanup()

if __name__=='__main__':unittest.main()
