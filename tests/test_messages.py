"""构建/音频/文化校验的报错必须"能照着改"：中文、带实际值、并且一次列全。

老师用的是中文，助手把报错转述给老师；而 1.0.44 之前 `build.py` 有 58 条英文短消息、
`audio.py` 15 条、`culture.py` 5 条，最后两条最要命的还只说结论不说数值，例如
"Quick word count must match this section"（实际几次？）、"Question 21 option count
mismatch"（要几项？）。看不懂的报错 → 助手猜着改 → 反复重建整卷：这正是"生成特别久、
特别费 token"的来源之一。

这里用两道锁：
1. 静态锁：全仓脚本里凡是 assert / raise 的报错文字都必须含中文（防止再退回英文）；
2. 行为锁：关键报错必须带上实际数值与下一步，且一次构建把所有问题都列出来。
"""
import ast
import contextlib
import copy
import hashlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build, audio, culture

CJK=re.compile(r'[\u4e00-\u9fff]')

def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

def string_parts(node):
    """assert/raise 的报错文字里出现的所有字符串常量（含 f-string 与 + 拼接）。"""
    return [child.value for child in ast.walk(node) if isinstance(child,ast.Constant) and isinstance(child.value,str)]

def error_messages(path):
    """每条 assert/raise 的报错文字 -> (行号, 拼接后的文字)。没有报错文字的 assert 也会被报出来。"""
    tree=ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node,ast.Assert):
            if node.msg is None:
                yield node.lineno,None,node
            else:
                yield node.lineno,''.join(string_parts(node.msg)),node
        elif isinstance(node,ast.Raise) and isinstance(node.exc,ast.Call) and node.exc.args:
            # SystemExit 的表达式是退出码/usage，不是给老师看的报错文字。
            if getattr(node.exc.func,'id',None) in ('SystemExit','KeyboardInterrupt'):continue
            parts=string_parts(node.exc.args[0])
            if parts:yield node.lineno,''.join(parts),node

class MessageLanguage(unittest.TestCase):
    def test_every_script_error_message_is_chinese(self):
        """报错给中文老师看，就不能只写英文；没有报错文字的 assert 也要补上说明。"""
        offenders=[]
        for path in sorted((ROOT/'scripts').glob('*.py')):
            if path.name=='browser_check.cjs':continue
            for line,text,_ in error_messages(path):
                if text is None:offenders.append(f'{path.name}:{line} assert 没有报错文字')
                elif not CJK.search(text):offenders.append(f'{path.name}:{line} {text[:60]}')
        self.assertEqual(offenders,[],'报错文字必须是中文且说明原因：\n'+'\n'.join(offenders))

    def test_guard_actually_would_catch_english(self):
        """反向验证：把英文写回去，这道锁必须报警（否则它只是空断言）。"""
        probe=Path(tempfile.mkdtemp())/'probe.py'
        probe.write_text('def f(x):\n    assert x,"Missing thing"\n',encoding='utf-8')
        found=[text for _,text,_ in error_messages(probe) if text and not CJK.search(text)]
        self.assertEqual(found,['Missing thing'])
        probe.write_text('def f(x):\n    assert x\n',encoding='utf-8')
        self.assertEqual([line for line,text,_ in error_messages(probe) if text is None],[2])

class BuildMessages(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 报错 ')
        self.base=Path(self.temp.name)
        self.exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))

    def tearDown(self):self.temp.cleanup()

    def error(self,exam):
        with self.assertRaises(ValueError) as caught:build.validate(exam)
        return str(caught.exception)

    def test_quick_word_reports_the_real_count_and_the_source_form(self):
        d=copy.deepcopy(self.exam);word=d['sections'][0]['quick_words'][0]
        word['occurrences']=7
        text=self.error(d)
        self.assertIn('loose',text)
        self.assertIn('实际出现 1 次',text)
        self.assertIn('条目写的是 7',text)

    def test_invented_quick_word_is_rejected_with_the_paragraph_id(self):
        d=copy.deepcopy(self.exam);word=d['sections'][0]['quick_words'][0]
        word['word']='photosynthesis'
        text=self.error(d)
        self.assertIn('photosynthesis',text)
        self.assertIn('A-p1',text)
        self.assertIn('不要伪造',text)

    def test_option_count_mismatch_reports_both_numbers(self):
        d=copy.deepcopy(self.exam);section=d['sections'][0]
        section['expected_option_count']=4;del section['questions'][0]['options']['D']
        text=self.error(d)
        self.assertIn('第 21 题',text)
        self.assertIn('要求 4 项',text)
        self.assertIn('实际 3 项',text)

    def test_missing_evidence_quote_names_the_paragraph_and_the_quote(self):
        d=copy.deepcopy(self.exam)
        d['sections'][0]['questions'][0]['evidence']=[{'paragraph_id':'A-p2','quote':'这句话不在原文里'}]
        text=self.error(d)
        self.assertIn('A-p2',text)
        self.assertIn('这句话不在原文里',text)
        self.assertIn('scripts/quotes.py fill',text)

    def test_feature_gap_is_named_in_chinese_with_a_quick_profile_hint(self):
        d=copy.deepcopy(self.exam)
        for key in ('sentences','structure','writing_bank'):
            d['sections'][0].pop(key,None)
        with self.assertRaises(ValueError) as caught:
            build.validate_features(d,profile='full')
        text=str(caught.exception)
        self.assertIn('句子精讲',text)
        self.assertIn('sentences',text)
        self.assertIn('--profile quick',text)

    def test_every_problem_is_listed_in_one_pass_with_a_next_step(self):
        """三个互不相干的问题必须在同一次构建里全部报出来：少一轮重建就少几分钟和一轮 token。"""
        d=copy.deepcopy(self.exam)
        section=d['sections'][0]
        section['quick_words'][0]['occurrences']=9
        del section['questions'][0]['options']['D']
        section['questions'][1]['analysis']=''
        text=self.error(d)
        self.assertIn('共 3 处问题，一次改完再重跑',text)
        self.assertEqual(len([line for line in text.splitlines() if line.startswith('- ')]),3)
        self.assertIn('重跑同一条命令',text)
        self.assertIn('references/schema.md',text)

    def test_feature_gaps_are_also_listed_in_one_pass(self):
        """功能覆盖缺失以前是 assert 逐条抛：一节少三项就要重建三次（实测一个两题小样连撞三轮）。"""
        d=copy.deepcopy(self.exam)
        for key in ('sentences','structure','writing_bank'):
            d['sections'][0].pop(key,None)
        with self.assertRaises(ValueError) as caught:
            build.validate_features(d,profile='full')
        text=str(caught.exception)
        self.assertIn('共 3 处问题，一次改完再重跑',text)
        self.assertEqual(len([line for line in text.splitlines() if line.startswith('- ')]),3,
                         '三个缺项必须在同一条报错里全部列出，而不是改一个再冒一个')
        for label in ('句子精讲','篇章结构','写作积累'):
            self.assertIn(label,text)

    def test_missing_blank_field_says_what_to_write_instead_of_a_raw_keyerror(self):
        """挖空少写一个字段名时，以前会抛裸 KeyError（`ERROR: 'paragraph_id'`），助手只能猜。"""
        section=self.exam['sections'][0]
        section['blanks']=[{'paragraph_id':section['paragraphs'][0]['id'],'start':0,'end':2,
                            'purpose':'答案依据的时间词','question_ids':[str(section['questions'][0]['id'])]}]
        for field in ('paragraph_id','start','end'):
            d=copy.deepcopy(self.exam)
            d['sections'][0]['blanks'][0].pop(field)
            with self.assertRaises(ValueError) as caught:
                build.validate(d)
            text=str(caught.exception)
            self.assertIn('挖空',text,'报错要说明这是挖空的问题')
            self.assertIn(field,text,f'报错要点名缺的是哪个字段（{field}）')

    def test_structural_and_feature_gaps_are_reported_in_the_same_build(self):
        """两段校验必须一次报全：先结构、再功能覆盖的话，第一次动手的卷子最少要跑两轮。

        这是"生成特别久/费额度"的一个直接来源——每多一轮，老师多等、助手多花一轮 token。
        """
        d=copy.deepcopy(self.exam)
        section=d['sections'][0]
        section['quick_words'][0]['occurrences']=9                 # 结构问题
        for key in ('sentences','structure','writing_bank'):
            section.pop(key,None)                                  # 功能覆盖缺三项
        source=self.base/'exam.json';source.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
        ledger={'sources':[{'role':'original_demo','path':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}],'sections':d['sections']}
        ledger_path=self.base/'source-ledger.json';ledger_path.write_text(json.dumps(ledger,ensure_ascii=False),encoding='utf-8')
        with self.assertRaises(ValueError) as caught:
            with contextlib.redirect_stdout(io.StringIO()):
                build.build(source,self.base/'out',ledger_path)
        text=str(caught.exception)
        self.assertIn('共 4 处问题，一次改完再重跑',text)
        self.assertIn('条目写的是 9',text,'结构问题必须在清单里')
        self.assertIn('缺少「句子精讲」内容（sentences）',text,'功能覆盖缺项必须在同一条清单里')
        self.assertIn('缺少「写作积累」内容（writing_bank）',text)

    def test_evidence_chain_failure_shares_the_same_report_as_structure(self):
        """四关（结构/功能覆盖/证据链/答案审计）必须一次报全：逐关抛错的话新卷子最多要跑四轮。"""
        d=copy.deepcopy(self.exam)
        d['sections'][0]['quick_words'][0]['occurrences']=9          # 结构问题
        source=self.base/'exam.json';source.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
        ledger={'sources':[{'role':'original_demo','path':source.name,'sha256':'0'*64}],   # 指纹故意对不上
                'sections':d['sections']}
        ledger_path=self.base/'source-ledger.json';ledger_path.write_text(json.dumps(ledger,ensure_ascii=False),encoding='utf-8')
        with self.assertRaises(ValueError) as caught:
            with contextlib.redirect_stdout(io.StringIO()):
                build.build(source,self.base/'out',ledger_path)
        text=str(caught.exception)
        self.assertIn('条目写的是 9',text,'结构问题要在清单里')
        self.assertIn('证据链不一致',text,'证据链问题也要在同一条清单里，而不是下一轮才冒出来')
        self.assertIn('共 2 处问题',text)

    def test_one_broken_blank_is_reported_once_not_twice(self):
        """同一处挖空错误只说一遍：重复报错会把"一次列全"变成噪音。"""
        d=copy.deepcopy(self.exam)
        d['sections'][0]['blanks']=[{'paragraph_id':'NOPE','start':0,'end':2,'purpose':'x','question_ids':['21']}]
        text=self.error(d)
        self.assertEqual(text.count('NOPE'),1,text)
        self.assertIn('挖空指向了不存在的段落',text)

    def test_writing_and_inquiry_gaps_say_which_fields_are_missing(self):
        d=copy.deepcopy(self.exam);section=d['sections'][0]
        section['writing_bank'][0].pop('frame');section['writing_bank'][0].pop('scene')
        section['inquiry'][0]['paragraph_id']='NOPE'
        text=self.error(d)
        self.assertIn('writing_bank 缺少',text)
        self.assertIn('frame',text)
        self.assertIn('scene',text)
        self.assertIn('NOPE',text)

class AudioAndCultureMessages(unittest.TestCase):
    def test_segment_count_mismatch_reports_expected_and_actual(self):
        temp=tempfile.TemporaryDirectory();base=Path(temp.name)
        manifest=base/'manifest.json'
        write(manifest,{'expected_count':5,'kind':'text','segments':[{'id':'s1','start':0,'end':1,'text':'x'}]})
        args=type('Args',(),{'manifest':str(manifest),'input':'unused.mp3','transcript':None,'allow_unverified':False,'resume':False})()
        import unittest.mock as mock
        with mock.patch.object(audio,'probe',return_value=60.0),mock.patch.object(audio,'sha256',return_value='deadbeef'):
            with self.assertRaises(AssertionError) as caught:audio.cut(args)
        text=str(caught.exception)
        self.assertIn('5 段',text)
        self.assertIn('1 段',text)

    def test_unverified_segment_message_explains_verified_and_allow_unverified(self):
        temp=tempfile.TemporaryDirectory();base=Path(temp.name)
        manifest=base/'manifest.json'
        write(manifest,{'expected_count':1,'kind':'question','segments':[{'id':'Q21','start':0,'end':2,'evidence':'第 21 题','question_ids':['21']}]})
        args=type('Args',(),{'manifest':str(manifest),'input':'unused.mp3','transcript':None,'allow_unverified':False,'resume':False})()
        import unittest.mock as mock
        with mock.patch.object(audio,'probe',return_value=60.0),mock.patch.object(audio,'sha256',return_value='deadbeef'):
            with self.assertRaises(AssertionError) as caught:audio.cut(args)
        text=str(caught.exception)
        self.assertIn('verified',text)
        self.assertIn('--allow-unverified',text)
        self.assertIn('qa-report',text)

    def test_culture_messages_ask_for_sources_not_guesses(self):
        section={'id':'A','paragraphs':[{'id':'A-p1','text':'Real passage text.'}],
            'culture_background':[{'paragraph_id':'A-p1','quote':'Real passage text.','title':'T',
                'explanation':'背景事实','reading_connection':'与本篇的关系','teaching_note':'课堂怎么用'}]}
        with self.assertRaises(AssertionError) as caught:culture.validate_culture(section)
        self.assertIn('来源',str(caught.exception))
        self.assertIn('不能凭印象写背景',str(caught.exception))
        bad=copy.deepcopy(section);bad['culture_background'][0]['quote']='编造的句子'
        bad['culture_background'][0]['sources']=[{'url':'https://example.org','title':'t','supports':'s'}]
        with self.assertRaises(AssertionError) as caught:culture.validate_culture(bad)
        self.assertIn('编造的句子',str(caught.exception))

if __name__=='__main__':unittest.main()
