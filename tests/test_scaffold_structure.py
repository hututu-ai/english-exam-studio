"""试卷有什么题型就做什么题型：骨架不再替老师补听力、阅读、完形、语法填空。

1.0.46 之前 `scaffold.py` 把每个大题都写成 `kind='reading'`、标题写成"待确认题型 N"，
并且**每一节**都追加同两条待办："听力补 audio 与原文""写作补题目要求与范文归属"，
再加一条"补 translation / structure / sentences / vocabulary / quick_words / writing_bank"。
结果是一份没有听力、只有阅读和写作的卷子，也会被推着去生成听力与精读栏目。

这里用一份中考式卷面文字（大题标题、分值、页脚、读写综合 A/B）验收：
题型名、板块、顺序、分值全部来自试卷；没有的题型不生成、也不提示补全。
"""
import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build, scaffold, section_kinds

PAPER='''九年级上册 Unit 1 适应性训练卷
（本卷满分120分，考试用时90分钟）
一、听说应用(30分，共30分)
1. What does the woman want to buy?
A. A book. B. A pen. C. A bag.
二、语法选择(本大题共10小题，每小题1分，共10分)
Qu Yuan is a great poet. As part of the post-2010 generation, he enjoyed a 31 childhood.
31. A. happy B. happier C. happiest
三、完形填空(本大题共10小题，每小题1分，共10分)
Chinese knot is a traditional folk art with a long history.
46. A. sizes B. kinds C. colours
四、阅读理解(本大题共15小题，每小题2分，共30分)
A
Student Science Fair: Show Your Invention!
51. What is the passage mainly written for?
A. Science teachers. B. Science experts. C. Primary school students.
五、短文填空(本大题共10小题，每小题1.5分，共15分)
Tom's dream is to use technology to make people's lives better.
66. ________ small prize
六、读写综合(本大题分为A、B两部分，共25分)
A. 回答问题(本题共5小题，每小题2分，共10分)
76. How did Qian Yufan feel when he saw the flowers?
B. 书面表达(本题15分)
81. 假设你是李华，请写一份发言稿。
九年级(上)·Unit 1 第1页(共6页)
'''

READING_ONLY='''九年级英语质量检测
（本卷满分90分，考试用时80分钟）
一、阅读理解(本大题共10小题，每小题2分，共20分)
A
Many students join reading clubs at school.
1. Why do students join the club?
A. To read more books. B. To play games. C. To do sports.
二、书面表达(本题20分)
21. 请以"My Reading Plan"为题写一篇短文。
'''

class ScaffoldStructure(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 骨架 ')
        self.base=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()

    def ledger(self,text):
        paper=self.base/'paper.txt';paper.write_text(text,encoding='utf-8')
        return scaffold.build_ledger(str(paper),None,None)

    def skeleton(self,text):
        paper=self.base/'paper.txt';paper.write_text(text,encoding='utf-8')
        ledger=scaffold.build_ledger(str(paper),None,None)
        path=self.base/'ledger.json';path.write_text(json.dumps(ledger,ensure_ascii=False),encoding='utf-8')
        return scaffold.exam_from_ledger(str(path),None)

    def test_paper_headings_become_the_section_names_in_paper_order(self):
        ledger=self.ledger(PAPER)
        self.assertEqual([s['kind'] for s in ledger['sections']],
                         ['听说应用','语法选择','完形填空','阅读理解','短文填空','读写综合','读写综合'],
                         '题型名与顺序必须来自试卷；读写综合的 A/B 各成一节但同属一个板块')
        self.assertEqual([s['group'] for s in ledger['sections']],
                         ['听说应用','语法选择','完形填空','阅读理解','短文填空','读写综合','读写综合'])
        self.assertEqual([s['title'] for s in ledger['sections']][-2:],
                         ['A. 回答问题(本题共5小题，每小题2分，共10分)','B. 书面表达(本题15分)'])
        self.assertEqual([s['id'] for s in ledger['sections']],['S1','S2','S3','S4','S5','S6','S7'])

    def test_paper_title_scores_footers_and_headings_never_become_reading_text(self):
        ledger=self.ledger(PAPER)
        self.assertEqual(ledger['title'],'九年级上册 Unit 1 适应性训练卷')
        self.assertEqual(ledger['paper_info'],{'full_score':120.0,'minutes':90.0})
        reasons=[item['reason'] for item in ledger['ignored_lines']]
        self.assertTrue(any('卷头' in reason for reason in reasons))
        self.assertTrue(any('页脚' in reason for reason in reasons))
        for section in ledger['sections']:
            for paragraph in section['paragraphs']:
                self.assertNotIn('满分120分',paragraph['text'],'卷首说明不能混进原文')
                self.assertNotIn('共6页',paragraph['text'],'页脚不能混进原文')
                self.assertNotIn('、听说应用',paragraph['text'],'大题标题不能混进原文')
        scores={s['id']:(s.get('score_per_question'),s.get('score_total')) for s in ledger['sections']}
        self.assertEqual(scores['S2'],(1.0,10.0),'每小题1分、共10分来自试卷标题')
        self.assertEqual(scores['S4'],(2.0,30.0))
        self.assertEqual(scores['S5'],(1.5,15.0))

    def test_paper_scores_and_exam_info_reach_the_skeleton(self):
        exam,_=self.skeleton(PAPER)
        self.assertEqual(exam.get('full_score'),120)
        self.assertEqual(exam.get('exam_minutes'),90)
        scores={s['id']:(s.get('score_per_question'),s.get('score_total')) for s in exam['sections']}
        self.assertEqual(scores['S2'],(1.0,10.0),'每小题1分、共10分来自试卷标题')
        self.assertEqual(scores['S7'],(None,15.0),'「本题15分」只记整题分值，不写成每小题15分')

    def minimal(self):
        """一节两题的最小可用卷：只测分值校验，不牵扯教学内容。"""
        def question(qid):
            # 各题的讲解文字必须不同：构建会拦下复制套话（validate_teaching_substance）
            return {'id':qid,'stem':'第 '+qid+' 题的题干','options':{},'answer':'x','answer_status':'sample','answer_source':'原件第 '+qid+' 题',
                    'question_type':'题型','type_note':'第 '+qid+' 题的题型说明','solve_steps':['看题干'+qid,'找依据'+qid,'核对选项'+qid],
                    'pitfall':'第 '+qid+' 题的易错点','analysis':'第 '+qid+' 题的解析','strategy':'第 '+qid+' 题的方法'}
        return {'title':'分值测试卷','expected_question_ids':['1','2'],
                'sections':[{'id':'A','kind':'短文填空','title':'短文填空','paragraphs':[{'id':'p1','text':'Some text.','translation':'译文'}],
                             'questions':[question('1'),question('2')]}]}

    def test_impossible_scores_are_rejected(self):
        exam=self.minimal();exam['sections'][0].update(score_per_question=0)
        with self.assertRaises(ValueError) as caught:build.validate(copy.deepcopy(exam))
        self.assertIn('大于 0 的数字',str(caught.exception))
        exam=self.minimal();exam['sections'][0].update(score_per_question=99,score_total=30)
        with self.assertRaises(ValueError) as caught:build.validate(copy.deepcopy(exam))
        self.assertIn('大于本大题总分',str(caught.exception))
        exam=self.minimal();exam['full_score']=-1
        with self.assertRaises(ValueError) as caught:build.validate(copy.deepcopy(exam))
        self.assertIn('full_score',str(caught.exception))

    def test_score_mismatch_is_a_warning_not_a_block(self):
        exam=self.minimal();exam['sections'][0].update(score_per_question=1,score_total=30)   # 1分×2题≠30分
        report=build.validate(copy.deepcopy(exam))
        self.assertEqual(report['status'],'structural_checks_passed')
        self.assertTrue(any('按此应有 30.0 题' in w and '本节只放了 2 题' in w for w in report['warnings']),report['warnings'])

    def test_skeleton_keeps_paper_kinds_and_infers_presets(self):
        exam,_=self.skeleton(PAPER)
        self.assertEqual([s['kind'] for s in exam['sections']],
                         ['听说应用','语法选择','完形填空','阅读理解','短文填空','读写综合','读写综合'])
        self.assertEqual([section_kinds.preset(s) for s in exam['sections']],
                         ['listening','cloze','cloze','reading','grammar','reading','writing'],
                         '呈现预设按题型名推断；读写综合本身认不出来，但它的小标题写明了 A. 回答问题 → reading、'
                         'B. 书面表达 → writing——这是卷面上的证据，比"一律留人工确认"更准（1.0.92 改）')
        self.assertEqual([s.get('score_total') for s in exam['sections']],
                         [30.0,10.0,10.0,30.0,15.0,10.0,15.0],
                         '读写综合 A/B 的分值各自来自它们自己的标题')
        self.assertEqual([s.get('score_per_question') for s in exam['sections']],
                         [None,1.0,1.0,2.0,1.5,2.0,None],
                         '"本题15分"是整题分值，不能写成每小题15分')

    def test_no_listening_no_writing_means_no_such_todo(self):
        """原卷只有阅读和写作时，骨架不得提示补听力、也不得要求写作节的精读栏目。"""
        _,todo=self.skeleton(READING_ONLY)
        self.assertTrue(any('阅读理解' in item for item in todo))
        joined='\n'.join(todo)
        self.assertIn('不要补原卷没有的题型',joined)
        reading_todo=[item for item in todo if item.startswith('S1（阅读理解）')]
        self.assertTrue(reading_todo)
        for item in reading_todo:
            self.assertNotIn('audio',item,'没有听力的卷子不该出现补音频的待办')
            self.assertNotIn('writing_steps',item,'没有写作的板块不该出现补范文的待办')
        writing_todo=[item for item in todo if item.startswith('S2（书面表达）')]
        self.assertTrue(writing_todo,'写作板块应当有自己的待办')
        self.assertTrue(any('writing_steps' in item for item in writing_todo),
                        '写作板块要明确补写作步骤与范文')

    def test_listening_section_gets_audio_and_blank_todo(self):
        exam,todo=self.skeleton(PAPER)
        listening=exam['sections'][0]
        self.assertEqual(listening['kind'],'听说应用')
        self.assertIn('blanks',listening,'听力板块的骨架里应有精听挖空位')
        joined='\n'.join(item for item in todo if item.startswith('S1（听说应用）'))
        self.assertIn('audio',joined)
        self.assertIn('blanks',joined)

    def test_sections_without_parsed_questions_are_flagged_not_invented(self):
        paper='''九年级英语测试
一、听说应用(30分，共30分)
二、阅读理解(本大题共5小题，每小题2分，共10分)
A
A short passage.
1. What is it about?
A. School. B. Sports. C. Music.
'''
        ledger=self.ledger(paper)
        first=ledger['sections'][0]
        self.assertEqual(first['kind'],'听说应用')
        self.assertEqual(first['questions'],[])
        self.assertTrue(any('没有解析到小题' in item for item in first['todo']),
                        '图片选项/图表题解析不到时要如实提示人工补，而不是照搬别节')

    def test_alias_tables_are_identical_in_python_template_and_browser_check(self):
        expected=section_kinds.KIND_ALIASES
        for path in (ROOT/'assets/lesson.html',ROOT/'scripts/browser_check.cjs'):
            text=path.read_text(encoding='utf-8')
            match=re.search(r"const KIND_ALIASES=\{(.*?)\};",text,re.S)
            self.assertIsNotNone(match,f'{path.name} 里找不到 KIND_ALIASES')
            found=dict(re.findall(r"'([^']+)':'([^']+)'",match.group(1)))
            self.assertEqual(found,expected,f'{path.name} 的题型别名表与 scripts/section_kinds.py 不一致')
    def test_preset_priority_is_the_same_in_all_three_implementations(self):
        """三份实现必须同一条优先级：宣告 > 题型名/别名 > **小标题/标题别名** > 内容推断。

        模板与浏览器脚本里少了"小标题"这一步，构建说是写作节、页面却按自定义渲染，
        这类分歧不会有任何报错，只能靠这条静态锁。
        """
        order=['declared','SECTION_PRESETS','KIND_ALIASES[kind]','aliasIn','audio','writing_steps','knowledge']
        for path in (ROOT/'assets'/'lesson.html',ROOT/'scripts'/'browser_check.cjs'):
            text=path.read_text(encoding='utf-8')
            self.assertIn('function aliasIn(',text,f'{path.name} 缺少 aliasIn（小标题别名匹配）')
            match=re.search(r"function sectionPreset\(s\)\{(.*?)\n?function ",text,re.S)
            self.assertIsNotNone(match,f'{path.name} 里找不到 sectionPreset')
            body=match.group(1)
            positions=[]
            for marker in order:
                index=body.find(marker)
                self.assertNotEqual(index,-1,f'{path.name} 的 sectionPreset 缺少判断步骤：{marker}')
                positions.append(index)
            self.assertEqual(positions,sorted(positions),f'{path.name} 的优先级顺序与 scripts/section_kinds.py 不一致：{positions}')
        presets=re.search(r"const SECTION_PRESETS=\[(.*?)\];",(ROOT/'assets/lesson.html').read_text(encoding='utf-8'))
        self.assertEqual(dict.fromkeys(re.findall(r"'([a-z]+)'",presets.group(1))),dict.fromkeys(section_kinds.SECTION_PRESETS))

if __name__=='__main__':unittest.main()
