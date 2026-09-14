"""用一份"像真的"初中卷检查 scaffold 的解析结构。

为什么单开一个文件：`tests/make_paper_structure_fixture.py` 测的是**已经写好的 exam.json**
怎么渲染；这里考的是**老师交上来的卷子文字**怎么被读成骨架。真实初中卷有几个固定形态，
此前一次性踩中三个 bug（1.0.91 修）：
  * 听说应用的选项写成单独一行 `A. 图A B. 图B C. 图C` → 被当成小标题，一道大题被切成 6 个空节；
  * 同一行里多个选项只被记成"A"的长文本，B/C 丢失；
  * 大题标题的分值在小标题出现时整段丢失（阅读 A/B/C 都没有分值）。

这里把这份卷子钉住：节数、题型名、板块、题数、分值、选项都要对得上。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import scaffold

def blocks(texts):
    return {'blocks':[{'type':'paragraph','text':text} for text in texts]}

def mc_questions(start,count,per_line='A. a B. b C. c D. d'):
    lines=[]
    for number in range(start,start+count):
        lines.append(f'{number}. Question {number}?')
        lines.append(per_line)
    return lines

def junior_paper():
    """九年级卷：听说应用 / 语法选择 / 完形填空 / 阅读理解 A–C / 配对阅读 / 短文填空 / 读写综合 A–B。"""
    texts=[
        '九年级(上)·Unit 1 适应性训练  英语试卷',
        '本卷满分120分，考试用时90分钟',
        '一、听说应用（本大题共5小题，每小题1分，共5分）',
        'A. 听句子选图 根据所听句子的内容和所提的问题，选择符合题意的图片。',
    ]
    for number in range(1,6):
        texts+= [f'{number}. What does the speaker mean?','A. 图A B. 图B C. 图C']
    texts+=[ '第 2 页（共 6 页）','二、语法选择（本大题共10小题，每小题1分，共10分）']
    texts+=mc_questions(6,10)
    texts+=['三、完形填空（本大题共10小题，每小题1.5分，共15分）']
    texts+=mc_questions(16,10)
    texts+=['四、阅读理解（本大题共15小题，每小题2分，共30分）']
    for subtitle,start in (('A. 阅读短文，选择最佳答案。',26),('B. 阅读短文，选择最佳答案。',31),('C. 阅读短文，回答问题。',36)):
        texts.append(subtitle)
        texts+=mc_questions(start,5) if 'choice' not in subtitle else mc_questions(start,5)
    texts+=['五、配对阅读（本大题共5小题，每小题2分，共10分）']
    for number in range(41,46):texts.append(f'{number}. Someone wants something.')
    texts+=['六、短文填空（本大题共10小题，每小题1.5分，共15分）','请用适当的词完成下面的短文。']
    for number in range(46,56):texts.append(f'{number}. ______')
    texts+=['七、读写综合（本大题分为A、B两部分，共35分）','A. 回答问题（本题共5小题，每小题2分，共10分）']
    for number in range(56,61):texts.append(f'{number}. What do you think?')
    texts+=['B. 书面表达（本题15分）','请根据要求写一篇短文。','第 6 页（共 6 页）']
    return texts

class RealJuniorPaperStructure(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 初中卷 ')
        self.base=Path(self.temp.name)

    def tearDown(self):self.temp.cleanup()

    def ledger(self):
        paper=self.base/'paper.json'
        paper.write_text(json.dumps(blocks(junior_paper()),ensure_ascii=False),encoding='utf-8')
        return scaffold.build_ledger(paper,None,None)

    def test_sections_follow_the_paper_not_our_presets(self):
        ledger=self.ledger()
        sections=ledger['sections']
        self.assertEqual([s['kind'] for s in sections],
                         ['听说应用','语法选择','完形填空','阅读理解','阅读理解','阅读理解',
                          '配对阅读','短文填空','读写综合','读写综合'])
        self.assertEqual([s['group'] for s in sections],
                         ['听说应用','语法选择','完形填空','阅读理解','阅读理解','阅读理解',
                          '配对阅读','短文填空','读写综合','读写综合'])
        self.assertEqual(ledger['unparsed'],[],'这份规范卷子不该有解析不了的行')

    def test_question_counts_and_scores(self):
        sections={s['id']:s for s in self.ledger()['sections']}
        counts=[(s['kind'],len(s['questions'])) for s in sections.values()]
        self.assertEqual(counts,[('听说应用',5),('语法选择',10),('完形填空',10),('阅读理解',5),
                                 ('阅读理解',5),('阅读理解',5),('配对阅读',5),('短文填空',10),
                                 ('读写综合',5),('读写综合',0)])
        first=sections['S1']
        self.assertEqual((first['score_per_question'],first['score_total']),(1.0,5.0),'听说应用是一节，大题总分就是它的总分')
        for sid in ('S4','S5','S6'):
            section=sections[sid]
            self.assertEqual(section['score_per_question'],2.0,'小标题没写分值时继承大题的每小题分值')
            self.assertEqual(section['score_total'],10.0,'大题的"共30分"不能挂在每一节上，要按每小题×本节题数推算')
            self.assertTrue(any('推算' in item for item in section['todo']),'推算出来的分值必须在待办里说明')
        self.assertEqual((sections['S2']['score_per_question'],sections['S2']['score_total']),(1.0,10.0))
        self.assertEqual((sections['S3']['score_per_question'],sections['S3']['score_total']),(1.5,15.0))
        self.assertEqual((sections['S7']['score_per_question'],sections['S7']['score_total']),(2.0,10.0))
        self.assertEqual((sections['S9']['score_per_question'],sections['S9']['score_total']),(2.0,10.0))
        self.assertEqual(sections['S10']['score_total'],15.0)
        self.assertIsNone(sections['S10'].get('score_per_question'),'书面表达只有整题分值，不该编出每小题分值')

    def test_continuation_option_line_is_split_not_treated_as_a_heading(self):
        """`A. 图A B. 图B C. 图C` 是选项续行：要拆成 A/B/C，而不是切成新的一节。"""
        sections=self.ledger()['sections']
        self.assertEqual(len(sections),10,'选项行不该把一道大题切成好几节')
        self.assertEqual(sections[0]['questions'][0]['options'],{'A':'图A','B':'图B','C':'图C'})
        self.assertEqual(sections[0]['questions'][-1]['options'],{'A':'图A','B':'图B','C':'图C'})

    def test_kind_preset_is_declared_from_kind_and_subtitle(self):
        """机器骨架要把"呈现方式"写清楚：读写综合 B 是写作节，不能落成 custom。

        只按 kind 判断时，"读写综合"底下的 A（回答问题）与 B（书面表达）都会是 custom：
        写作节会因此丢掉写作工作区与必填栏目。
        """
        paper=self.base/'paper.json'
        paper.write_text(json.dumps(blocks(junior_paper()),ensure_ascii=False),encoding='utf-8')
        ledger=self.base/'ledger.json'
        import scaffold as _scaffold
        ledger.write_text(json.dumps(_scaffold.build_ledger(paper,None,None),ensure_ascii=False),encoding='utf-8')
        exam,_todo=_scaffold.exam_from_ledger(ledger,None)
        presets={s['id']:s.get('kind_preset') for s in exam['sections']}
        self.assertEqual(presets['S1'],'listening','听说应用是听力节')
        self.assertEqual(presets['S2'],'cloze')
        self.assertEqual(presets['S4'],'reading')
        self.assertEqual(presets['S6'],'reading','读写综合 A（回答问题）是阅读节')
        self.assertEqual(presets['S7'],'seven','配对阅读按七选五呈现')
        self.assertEqual(presets['S8'],'grammar','短文填空按语法填空呈现')
        self.assertEqual(presets['S9'],'reading')
        self.assertEqual(presets['S10'],'writing','读写综合 B（书面表达）必须是写作节')
        writing=[s for s in exam['sections'] if s['id']=='S10'][0]
        self.assertIn('writing_steps',writing,'写作节要带写作步骤骨架')
        self.assertIn('teacher_model',writing,'写作节要带范文位')
        listening=[s for s in exam['sections'] if s['id']=='S1'][0]
        self.assertIn('blanks',listening,'听力节要带挖空位')

    def test_unknown_kind_leaves_kind_preset_unset(self):
        """认不出来时不要瞎宣告：留空，让内容推断决定（宣告了会冻结成 custom）。"""
        texts=['一、综合运用（本题10分）','71. 请完成下面的任务。']
        import scaffold as _scaffold
        paper=self.base/'unknown.json'
        paper.write_text(json.dumps(blocks(texts),ensure_ascii=False),encoding='utf-8')
        ledger=self.base/'unknown-ledger.json'
        ledger.write_text(json.dumps(_scaffold.build_ledger(paper,None,None),ensure_ascii=False),encoding='utf-8')
        exam,_=_scaffold.exam_from_ledger(ledger,None)
        self.assertIsNone(exam['sections'][0].get('kind_preset'),'认不出来的题型不要写死呈现方式')

    def test_image_placeholder_options_are_flagged_in_the_skeleton(self):
        """图片选项的卷面只写"图A/图B"：骨架必须提示用 option_images，构建也会拦下纯占位。"""
        ledger=self.ledger()
        todo='\n'.join(ledger['sections'][0]['todo'])
        self.assertIn('占位',todo)
        self.assertIn('option_images',todo)
        reading_todo='\n'.join(ledger['sections'][3]['todo'])
        self.assertNotIn('占位',reading_todo,'正常的文字选项不该被误报')

    def test_paper_title_and_exam_info_are_kept(self):
        ledger=self.ledger()
        self.assertIn('九年级(上)',ledger['title'])
        self.assertEqual(ledger['paper_info'],{'full_score':120.0,'minutes':90.0})
        self.assertTrue(any('页码' in item['reason'] for item in ledger['ignored_lines']),'页码要被忽略并记录原因')

if __name__=='__main__':unittest.main()
