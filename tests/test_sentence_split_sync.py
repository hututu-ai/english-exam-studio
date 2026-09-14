"""切句必须两边一致：构建用 Python 校验对齐，页面用 JS 分行显示。

如果两边切出的句子不一样，译文就会在页面上错位——而且构建还是"通过"的。
所以这里拿一份语料把两边跑一遍逐句比对（模板里的函数源码直接抽出来执行，
避免"测试里抄一份 JS"这种自我安慰）。
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from sentence_split import split_sentences

CORPUS=[
 'On Friday, the students at Willow School opened a repair corner in the library. It started with a broken chair. Now it is a small museum of fixed things.',
 'Mr. Li is 14 years old. He likes Chinese knots! What about you?',
 'The price is 3.5 yuan. It is cheap.',
 'He said, "I am ready." Then he left.',
 'It takes 25 minutes... and then it ends.',
 'No ending punctuation',
 'Dr. Smith works with Prof. Wang, etc. They publish in the U.S. every year.',
 'One sentence? Yes! Really?\nAnd a new line after it.',
 '',
 '   ',
 'Wait—what about dashes, commas, and semicolons; they do not end a sentence.',
 'A sentence ending with an ellipsis… Then another one.',
]

class SplitterSync(unittest.TestCase):
    def js_source(self):
        template=(ROOT/'assets/lesson.html').read_text(encoding='utf-8')
        constants=re.search(r'const SENTENCE_ABBREVIATIONS=.*?;',template,re.S)
        function=re.search(r'function splitSentences\(text\)\{.*?return out\}',template,re.S)
        self.assertIsNotNone(constants,'模板里找不到 SENTENCE_ABBREVIATIONS')
        self.assertIsNotNone(function,'模板里找不到 splitSentences')
        return constants.group(0)+'\n'+function.group(0)

    def test_javascript_and_python_split_identically(self):
        node=shutil.which('node')
        if not node:self.skipTest('node 不可用，跳过切句一致性检查')
        temp=tempfile.TemporaryDirectory(prefix='英语 skill 切句 ')
        base=Path(temp.name)
        corpus=base/'corpus.json';corpus.write_text(json.dumps(CORPUS,ensure_ascii=False),encoding='utf-8')
        harness=base/'harness.js'
        harness.write_text(self.js_source()+"""
const fs=require('fs');
const corpus=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
process.stdout.write(JSON.stringify(corpus.map(text=>splitSentences(text))));
""",encoding='utf-8')
        result=subprocess.run([node,str(harness),str(corpus)],capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertEqual(result.returncode,0,result.stderr[-400:])
        js=json.loads(result.stdout)
        py=[split_sentences(text) for text in CORPUS]
        for text,expected,actual in zip(CORPUS,py,js):
            self.assertEqual(actual,expected,f'两边切句不一致：{text!r}\npython={expected}\njs={actual}')
        temp.cleanup()

    def test_corpus_covers_the_tricky_cases(self):
        """语料本身要真的覆盖缩写、小数、引号、省略号、空串，否则这条同步测试没有意义。"""
        joined='\n'.join(CORPUS)
        for marker in ('Mr. Li','3.5','"I am ready."','...','U.S.','\n'):
            self.assertIn(marker,joined,marker)
        self.assertEqual(split_sentences(''),[])

if __name__=='__main__':unittest.main()
