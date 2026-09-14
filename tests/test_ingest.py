"""Ingestion tools: reading the teacher's paper and answer key.

These were previously untested, yet they are the first step of every real task.
The tests cover both correct parsing and the malformed inputs teachers actually
hand over (.doc, PDF renamed .docx, truncated downloads), which must produce one
actionable sentence instead of a Python traceback.
"""
import copy,json,re,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build
NS='http://schemas.openxmlformats.org/wordprocessingml/2006/main'

def write_docx(path,body):
    xml=f'<?xml version="1.0"?><w:document xmlns:w="{NS}"><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('word/document.xml',xml)
        archive.writestr('word/media/image1.png',b'\x89PNG\r\n\x1a\n'+b'0'*16)
    return path

def paragraph(text):return f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>'

MC='http://schemas.openxmlformats.org/markup-compatibility/2006'
WPS='http://schemas.microsoft.com/office/word/2010/wordprocessingShape'
V='urn:schemas-microsoft-com:vml'
WP='http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
A='http://schemas.openxmlformats.org/drawingml/2006/main'

def textbox(inner,modern):
    """Word/WPS 的文本框：现代图形写在 mc:Choice，VML 副本写在 mc:Fallback，文字是一样的。"""
    if modern:
        return (f'<mc:Choice Requires="wps"><w:drawing><wp:inline><a:graphic><a:graphicData uri="x">'
                f'<wps:wsp><wps:txbx><w:txbxContent>{inner}</w:txbxContent></wps:txbx></wps:wsp>'
                f'</a:graphicData></a:graphic></wp:inline></w:drawing></mc:Choice>')
    return (f'<mc:Fallback><w:pict><v:shape><v:textbox><w:txbxContent>{inner}</w:txbxContent></v:textbox>'
            f'</v:shape></w:pict></mc:Fallback>')

def alternate_content(inner):
    return f'<mc:AlternateContent>{textbox(inner,True)}{textbox(inner,False)}</mc:AlternateContent>'

def textbox_paragraph(inner):
    return f'<w:p><w:r>{alternate_content(inner)}</w:r></w:p>'

def write_docx_rich(path,body):
    """带 mc/wps/v 命名空间的 DOCX（文本框需要）。"""
    xml=(f'<?xml version="1.0"?><w:document xmlns:w="{NS}" xmlns:mc="{MC}" xmlns:wp="{WP}" '
         f'xmlns:a="{A}" xmlns:wps="{WPS}" xmlns:v="{V}"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path,'w') as archive:archive.writestr('word/document.xml',xml)
    return path

def table(rows):
    """构造一张真实的 DOCX 表格（答案表最常见的样子：一行题号、一行答案）。"""
    return '<w:tbl>'+''.join('<w:tr>'+''.join('<w:tc>'+paragraph(cell)+'</w:tc>' for cell in row)+'</w:tr>' for row in rows)+'</w:tbl>'


def run(script,*args):
    return subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,args)],
                          capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)

class ExtractTests(unittest.TestCase):
    def test_extract_preserves_paragraph_table_and_image_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            table='<w:tbl><w:tr><w:tc>'+paragraph('11. What time?')+'</w:tc><w:tc>'+paragraph('A. Five')+'</w:tc></w:tr></w:tbl>'
            source=write_docx(root/'paper.docx',paragraph('Reading A')+paragraph('The museum opens at nine.')+table)
            result=run('extract.py',source,root/'out')
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads((root/'out/extracted.json').read_text(encoding='utf-8'))
            self.assertEqual([b['type'] for b in data['blocks']],['paragraph','paragraph','table'])
            self.assertEqual(data['blocks'][2]['rows'],[['11. What time?','A. Five']])
            self.assertEqual(data['images'],['images/image1.png'])
            self.assertTrue((root/'out/images/image1.png').exists())
    def test_text_box_content_is_not_duplicated(self):
        """文本框在中文卷里很常见，Word/WPS 会写两份等价副本，读两份会把题干变成两遍。"""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            inner=paragraph('11. When does the museum open?')
            body=paragraph('Reading A')+textbox_paragraph(inner)+paragraph('A. At eight.')
            source=write_docx_rich(root/'paper.docx',body)
            result=run('extract.py',source,root/'out')
            self.assertEqual(result.returncode,0,result.stderr)
            blocks=json.loads((root/'out/extracted.json').read_text(encoding='utf-8'))['blocks']
            texts=[b['text'] for b in blocks]
            self.assertEqual(texts,['Reading A','11. When does the museum open?','A. At eight.'],'文本框内容只能出现一次')
            self.assertTrue(blocks[1].get('textbox'),'要标明这段含文本框内容，便于对照原件核对顺序')

    def test_text_box_paragraphs_are_kept_on_separate_lines(self):
        """一个文本框里有多段时不能粘成一句。"""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            inner=paragraph('First line in box')+paragraph('Second line in box')
            source=write_docx_rich(root/'paper.docx',textbox_paragraph(inner))
            run('extract.py',source,root/'out')
            blocks=json.loads((root/'out/extracted.json').read_text(encoding='utf-8'))['blocks']
            self.assertEqual(blocks[0]['text'],'First line in box\nSecond line in box')

    def test_table_cell_with_text_box_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            cell=f'<w:tc><w:p><w:r><w:t>题号</w:t></w:r>{alternate_content(paragraph("11"))}</w:p></w:tc>'
            source=write_docx_rich(root/'paper.docx',f'<w:tbl><w:tr>{cell}<w:tc>{paragraph("B")}</w:tc></w:tr></w:tbl>')
            run('extract.py',source,root/'out')
            blocks=json.loads((root/'out/extracted.json').read_text(encoding='utf-8'))['blocks']
            self.assertEqual(blocks[0]['rows'],[['题号\n11','B']],'单元格里的文本框同样不能重复')

    def test_extract_reports_bad_input_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            notzip=root/'fake.docx';notzip.write_text('not a zip',encoding='utf-8')
            nodoc=root/'nodoc.docx'
            with zipfile.ZipFile(nodoc,'w') as archive:archive.writestr('readme.txt','x')
            nobody=root/'nobody.docx'
            with zipfile.ZipFile(nobody,'w') as archive:archive.writestr('word/document.xml',f'<?xml version="1.0"?><w:document xmlns:w="{NS}"></w:document>')
            for source,needle in ((notzip,'不是有效的 DOCX'),(nodoc,'word/document.xml'),(nobody,'w:body')):
                result=run('extract.py',source,root/('out-'+source.stem))
                self.assertEqual(result.returncode,1,source.name)
                self.assertIn('ERROR:',result.stderr)
                self.assertIn(needle,result.stderr)
                self.assertNotIn('Traceback',result.stderr,source.name)

class ScaffoldChainTests(unittest.TestCase):
    def test_paper_and_key_become_a_ledger_and_exam_skeleton(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            paper=write_docx(root/'paper.docx',paragraph('Reading A')+paragraph('The museum opens at nine and entry is free.')
                +paragraph('11. When does the museum open?')+paragraph('A. At eight.')+paragraph('B. At nine.')
                +paragraph('C. At ten.')+paragraph('D. At eleven.')+paragraph('12. How much is entry?')
                +paragraph('A. Free.')+paragraph('B. Ten yuan.')+paragraph('C. Twenty yuan.')+paragraph('D. Thirty yuan.'))
            key=write_docx(root/'key.docx',paragraph('11 B')+paragraph('12 A'))
            extracted=run('extract.py',paper,root/'work')
            self.assertEqual(extracted.returncode,0,extracted.stderr)
            answers=run('answers.py','extract',key,'--out',root/'answers.json')
            self.assertEqual(answers.returncode,0,answers.stderr)
            ledger=run('scaffold.py','ledger','--paper',root/'work/extracted.json','--answers',root/'answers.json','--out',root/'ledger.json')
            self.assertEqual(ledger.returncode,0,ledger.stderr)
            data=json.loads((root/'ledger.json').read_text(encoding='utf-8'))
            self.assertEqual(data['unparsed'],[])
            questions=[q for section in data['sections'] for q in section['questions']]
            self.assertEqual([q['id'] for q in questions],['11','12'])
            self.assertEqual([list(q['options']) for q in questions],[['A','B','C','D'],['A','B','C','D']])
            self.assertEqual([(q['answer'],q['answer_status']) for q in questions],[('B','official'),('A','official')])
            exam=run('scaffold.py','exam','--ledger',root/'ledger.json','--out',root/'exam.json')
            self.assertEqual(exam.returncode,0,exam.stderr)
            skeleton=json.loads((root/'exam.json').read_text(encoding='utf-8'))
            self.assertEqual(skeleton['expected_question_ids'],['11','12'])
            # The machine-derived inventory must be flagged: the build's "no missing question"
            # check is vacuous while it comes from the same parse.
            self.assertEqual(skeleton['expected_question_ids_source'],'machine_draft')
            with self.assertRaisesRegex(ValueError,'机器草稿'):
                build.validate(copy.deepcopy(skeleton))
            reviewed=copy.deepcopy(skeleton);reviewed['expected_question_ids_source']='checked'
            try:build.validate(reviewed)
            except ValueError as error:self.assertNotIn('机器草稿',str(error))
            self.assertEqual(len(skeleton['sections']),1)
    def test_scaffold_rejects_a_paper_json_without_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            bad=root/'paper.json';bad.write_text('{"nope":1}',encoding='utf-8')
            result=run('scaffold.py','ledger','--paper',bad,'--out',root/'ledger.json')
            self.assertEqual(result.returncode,1)
            self.assertIn('ERROR:',result.stderr)
            self.assertNotIn('Traceback',result.stderr)

class AnswerKeyTests(unittest.TestCase):
    def key(self,root,body):
        return write_docx(root/'key.docx',body)
    def test_extracts_ranges_dotted_and_circled_answers(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=self.key(root,paragraph('21-25 ABCDA')+paragraph('26. B')+paragraph('27 Ⓒ')+paragraph('28-30 ABC')+paragraph('31 A'))
            result=run('answers.py','extract',source,'--out',root/'answers.json')
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads((root/'answers.json').read_text(encoding='utf-8'))
            self.assertEqual(data['answers'],{'21':'A','22':'B','23':'C','24':'D','25':'A','26':'B','27':'C','28':'A','29':'B','30':'C','31':'A'})
            self.assertEqual(data['unparsed'],[])
            self.assertEqual(data['answer_source_sha256'],__import__('hashlib').sha256(source.read_bytes()).hexdigest())
    def test_two_row_number_answer_table_is_parsed(self):
        """答案表最常见的排法：上一行题号、下一行答案（答题卡/参考答案表）。

        以前这种原件解析出 0 条答案，只留一句"含数字但未识别出题号+答案"——老师最常见的答案表反而不支持。
        """
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=self.key(root,paragraph('参考答案')+table([['题号','1','2','3','4','5'],['答案','B','C','A','D','B']]))
            data=json.loads(run('answers.py','extract',source,'--out',root/'a.json').stdout and (root/'a.json').read_text(encoding='utf-8'))
            self.assertEqual(data['answers'],{'1':'B','2':'C','3':'A','4':'D','5':'B'})
            self.assertEqual(data['unparsed'],[])
            self.assertEqual(data['matched_lines'][0]['pattern'],'number_row_then_answer_row','要标明这条是怎么来的，便于回原件核对')

    def test_several_table_blocks_and_word_answers_are_supported(self):
        """一张表可以分几段（1–2 题、3–4 题），语法填空那类答案是单词/短语而不是字母。"""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            body=(paragraph('参考答案')+table([['题号','1','2'],['答案','B','C']])
                  +table([['题号','3','4'],['答案','which','has been']]))
            data=json.loads((lambda p:run('answers.py','extract',p,'--out',root/'a.json') and (root/'a.json').read_text(encoding='utf-8'))(self.key(root,body)))
            self.assertEqual(data['answers'],{'1':'B','2':'C','3':'which','4':'has been'})

    def test_table_column_mismatch_is_reported_not_guessed(self):
        """题号行 3 列、答案行 2 列时不许按顺序硬对齐：给中文原因，进 unparsed。"""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=self.key(root,table([['题号','1','2','3'],['答案','B','C']]))
            run('answers.py','extract',source,'--out',root/'a.json')
            data=json.loads((root/'a.json').read_text(encoding='utf-8'))
            self.assertEqual(data['answers'],{},'列数不一致时不许猜')
            reasons=' '.join(item['reason'] for item in data['unparsed'])
            self.assertIn('列数不一致',reasons)
            self.assertIn('不要按顺序硬对齐',reasons)

    def test_table_empty_answer_cell_is_flagged(self):
        """空格子不能当空答案吞掉：其余题照常解析，空格子点名报出。"""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=self.key(root,table([['题号','1','2'],['答案','B','']]))
            run('answers.py','extract',source,'--out',root/'a.json')
            data=json.loads((root/'a.json').read_text(encoding='utf-8'))
            self.assertEqual(data['answers'],{'1':'B'})
            self.assertTrue(any('第 2 题' in item['reason'] for item in data['unparsed']),data['unparsed'])

    def test_table_answer_key_reaches_an_official_ledger(self):
        """整条链：表格答案原件 → answers.json → 台账里是 official。"""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            paper=write_docx(root/'paper.docx',paragraph('Reading A')+paragraph('The museum opens at nine and entry is free.')
                +paragraph('11. When does the museum open?')+paragraph('A. At eight.')+paragraph('B. At nine.')
                +paragraph('C. At ten.')+paragraph('D. At eleven.'))
            key=self.key(root,table([['题号','11'],['答案','B']]))
            self.assertEqual(run('extract.py',paper,root/'work').returncode,0)
            self.assertEqual(run('answers.py','extract',key,'--out',root/'answers.json').returncode,0)
            self.assertEqual(run('scaffold.py','ledger','--paper',root/'work/extracted.json','--answers',root/'answers.json','--out',root/'ledger.json').returncode,0)
            ledger=json.loads((root/'ledger.json').read_text(encoding='utf-8'))
            question=[q for section in ledger['sections'] for q in section['questions']][0]
            self.assertEqual((question['id'],question['answer'],question['answer_status']),('11','B','official'))

    def test_conflicting_duplicate_answer_is_listed_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=self.key(root,paragraph('26. B')+paragraph('26 C'))
            result=run('answers.py','extract',source,'--out',root/'answers.json')
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads((root/'answers.json').read_text(encoding='utf-8'))
            self.assertTrue(any(item['reason'].startswith('题号 26') for item in data['unparsed']),data['unparsed'])
    def test_bad_answer_file_is_actionable(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            notzip=root/'fake.docx';notzip.write_text('not a zip',encoding='utf-8')
            result=run('answers.py','extract',notzip,'--out',root/'a.json')
            self.assertEqual(result.returncode,1)
            self.assertIn('ERROR:',result.stderr)
            self.assertNotIn('Traceback',result.stderr)
    def test_check_blocks_on_mismatch_and_passes_when_consistent(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            table=root/'answers.json'
            table.write_text(json.dumps({'answers':{'21':'B'}}),encoding='utf-8')
            def ledger(answer,status):
                path=root/f'ledger-{status}-{answer}.json'
                path.write_text(json.dumps({'sections':[{'id':'A','questions':[{'id':'21','answer':answer,'answer_status':status}]}]}),encoding='utf-8')
                return path
            consistent=run('answers.py','check',table,'--ledger',ledger('B','official'))
            self.assertEqual(consistent.returncode,0,consistent.stderr)
            mismatch=run('answers.py','check',table,'--ledger',ledger('C','official'))
            self.assertEqual(mismatch.returncode,1)
            self.assertEqual(json.loads(mismatch.stdout)['status'],'blocked')
            # A non-official inferred answer may differ without blocking the chain.
            inferred=run('answers.py','check',table,'--ledger',ledger('C','inferred'))
            self.assertEqual(inferred.returncode,0,inferred.stderr)
    def test_extracts_word_and_phrase_answers_for_grammar_items(self):
        # 语法填空 answers are words, not A-H letters; a key file must be able to express them.
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=self.key(root,paragraph('21-25 ABCDA')+paragraph('56. which')+paragraph('57、has been')
                            +paragraph('58. which/that')+paragraph('59. to make (to do)'))
            result=run('answers.py','extract',source,'--out',root/'answers.json')
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads((root/'answers.json').read_text(encoding='utf-8'))
            self.assertEqual(data['answers']['56'],'which')
            self.assertEqual(data['answers']['57'],'has been')
            self.assertEqual(data['answers']['58'],'which','variants keep the primary form')
            self.assertEqual(data['answers']['59'],'to make')
            self.assertEqual(data['unparsed'],[])
    def test_question_stems_are_not_mistaken_for_word_answers(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=self.key(root,paragraph('21. What does the man suggest?')
                            +paragraph('22. The book which I read was good indeed today'))
            result=run('answers.py','extract',source,'--out',root/'answers.json')
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads((root/'answers.json').read_text(encoding='utf-8'))
            self.assertEqual(data['answers'],{},'paper text must not be read as an answer key')

class QuotesTests(unittest.TestCase):
    def demo(self):return json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
    def write(self,root,data,name='exam.json'):
        path=root/name;path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');return path
    def test_repo_example_has_no_quote_problems(self):
        # Regression: structure uses paragraph_ids (plural); check must not demand paragraph_id.
        result=run('quotes.py','check',ROOT/'examples/demo-reading.json')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        report=json.loads(result.stdout)
        self.assertEqual(report['status'],'ok')
        self.assertEqual(report['problems'],[])
        self.assertGreater(report['quotes_checked'],0)
    def test_wrong_structure_and_evidence_quotes_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);data=self.demo()
            data['sections'][0]['structure'][0]['quote']='not in any paragraph'
            data['sections'][0]['questions'][0]['evidence'][0]['quote']='also not in the passage'
            result=run('quotes.py','check',self.write(root,data))
            self.assertEqual(result.returncode,1)
            report=json.loads(result.stdout)
            self.assertEqual(report['status'],'needs_fix')
            self.assertEqual(len(report['problems']),2)
    def test_fill_resolves_a_range_and_drops_the_ref(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);data=self.demo()
            text=data['sections'][0]['paragraphs'][0]['text']
            start=text.index('showed students');end=start+len('showed students how to repair')
            data['sections'][0]['structure']=[{'title':'示范','paragraph_ids':['A-p1'],'analysis':'用例子说明','quote_ref':[start,end]}]
            path=self.write(root,data)
            result=run('quotes.py','fill',path)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['filled'],1)
            filled=json.loads(path.read_text(encoding='utf-8'))
            item=filled['sections'][0]['structure'][0]
            self.assertNotIn('quote_ref',item)
            self.assertEqual(item['quote'],'showed students how to repair')
            self.assertEqual(run('quotes.py','check',path).returncode,0)
    def test_fill_refuses_ambiguous_multi_paragraph_range(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);data=self.demo()
            data['sections'][0]['structure']=[{'title':'总述','paragraph_ids':['A-p1','A-p2'],'analysis':'两段合看','quote_ref':[0,10]}]
            result=run('quotes.py','fill',self.write(root,data))
            self.assertEqual(result.returncode,1)
            self.assertIn('无法判断范围属于哪一段',result.stderr)
            self.assertNotIn('Traceback',result.stderr)
    def test_fill_refuses_a_range_that_cuts_a_word(self):
        """切在单词中间得到的仍是"逐字子串"，下游闸门查不出来，所以 fill 必须自己拦（1.0.103）。"""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);data=self.demo()
            text=data['sections'][0]['paragraphs'][0]['text']
            at=text.index('students')+2
            data['sections'][0]['structure']=[{'title':'示范','paragraph_ids':['A-p1'],'analysis':'用例子说明','quote_ref':[at,at+5]}]
            path=self.write(root,data);before=path.read_text(encoding='utf-8')
            result=run('quotes.py','fill',path)
            self.assertEqual(result.returncode,1)
            self.assertIn('截断',result.stderr)
            self.assertNotIn('Traceback',result.stderr)
            self.assertEqual(path.read_text(encoding='utf-8'),before,'拒绝时一个字节都不该写回去')
    def test_fill_refuses_blank_and_punctuation_only_ranges(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);data=self.demo()
            text=data['sections'][0]['paragraphs'][0]['text']
            for start,end,want in [(text.index(' '),text.index(' ')+1,'空白'),(text.index('.'),text.index('.')+1,'标点')]:
                with self.subTest(chars=(start,end)):
                    case=copy.deepcopy(data)
                    case['sections'][0]['structure']=[{'title':'示范','paragraph_ids':['A-p1'],'analysis':'用例子说明','quote_ref':[start,end]}]
                    result=run('quotes.py','fill',self.write(root,case))
                    self.assertEqual(result.returncode,1)
                    self.assertIn(want,result.stderr)
                    self.assertNotIn('Traceback',result.stderr)
    def test_check_flags_a_quote_cut_out_of_a_word(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);data=self.demo()
            evidence=data['sections'][0]['questions'][0]['evidence'][0]
            paragraph=next(p for p in data['sections'][0]['paragraphs'] if p['id']==evidence['paragraph_id'])
            text=paragraph['text']
            at=next(m.start()+2 for m in re.finditer(r'[A-Za-z]{6,}',text))   # 切进某个单词中间
            evidence['quote']=text[at:at+5]
            result=run('quotes.py','check',self.write(root,data))
            self.assertEqual(result.returncode,1)
            report=json.loads(result.stdout)
            self.assertEqual(report['status'],'needs_fix')
            self.assertTrue(any('截断' in problem for problem in report['problems']),report['problems'])
    def test_check_flags_blank_or_empty_quotes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for value in ('   ',''):
                with self.subTest(quote=value):
                    data=self.demo()
                    data['sections'][0]['questions'][0]['evidence'][0]['quote']=value
                    result=run('quotes.py','check',self.write(root,data))
                    self.assertEqual(result.returncode,1)
                    report=json.loads(result.stdout)
                    self.assertTrue(any('空白' in problem for problem in report['problems']),report['problems'])
    def test_fill_rejects_an_out_of_range_ref(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);data=self.demo()
            data['sections'][0]['structure']=[{'title':'示范','paragraph_ids':['A-p1'],'analysis':'用例子说明','quote_ref':[0,99999]}]
            result=run('quotes.py','fill',self.write(root,data))
            self.assertEqual(result.returncode,1)
            self.assertIn('超出段落长度',result.stderr)
            self.assertNotIn('Traceback',result.stderr)
