"""qa-report.md 是唯一必须由人（Agent）写结论的交付物，因此它必须能被机器生成、也必须能被机器拒绝。

1.0.44 之前，七份文档都要求"把结论写进 qa-report.md"，但没有任何脚本生成或校验它：
交付是否合规完全取决于 Agent 是否自觉。这里验证三件事：
1. init 必须把机器已知的证据（答案审计、浏览器跳过项、待核项）落到条目里，而不是空模板；
2. check 必须拒绝空结论、占位文字、被删掉的章节和被清空的文件；
3. package_lesson 必须把 qa-report 当成交付闸门，且 --allow-unchecked 仍能交付"待验收版"。
"""
import contextlib,io,json,re,sys,tempfile,unittest,unittest.mock
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import qa_report

FILLED='已逐条核对，结论与原件一致。'

def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')

def fill(text,conclusion=FILLED):
    """把模板里所有 '—— 结论：' 的行补上结论，模拟 Agent 填写后的文件。"""
    return re.sub(r'—— 结论：$',f'—— 结论：{conclusion}',text,flags=re.M)

class QaReport(unittest.TestCase):
    def setUp(self):
        self._tmp=tempfile.TemporaryDirectory();self.base=Path(self._tmp.name);self.out=self.base/'lesson'
        self.out.mkdir()
        write(self.out/'build-report.json',{'profile':'standard','delivery_status':'browser_checked',
            'pending_items':['未在真机 Windows 上运行'],
            'quality_gate':{'warnings':[{'code':'audio_alignment_auto_silence','location':'L1 第3段'}]}})
        write(self.out/'answer-audit.json',{'counts':{'official':12,'inferred':1,'sample':0,'unresolved':0},
            'review':[{'question':'21','message':'两个来源一致'}],
            'blocking':[{'question':'34','message':'答案原件的表格行错位'}]})
        write(self.out/'browser-check.json',{'status':'passed',
            'checks':[{'name':'播放听力'},{'name':'查看答案'}],
            'skipped':[{'name':'生词本导出','reason':'该功能未开启'}]})

    def tearDown(self):self._tmp.cleanup()

    def report(self):return self.out/'qa-report.md'

    def test_collect_uses_real_evidence_not_a_blank_template(self):
        items,report,browser=qa_report.collect(self.out)
        flat=[row for section in qa_report.SECTIONS for row in items[section]]
        text='\n'.join(flat)
        self.assertIn('official 12 题',text)
        self.assertIn('第21题语义复核：两个来源一致',text)
        self.assertIn('第34题阻断项复核：答案原件的表格行错位',text)
        self.assertIn('生词本导出',text)
        self.assertIn('未经',text)  # skipped 项必须标成"未经验证"
        self.assertIn('未在真机 Windows 上运行',text)
        self.assertEqual(len(items),len(qa_report.SECTIONS))
        for section in qa_report.SECTIONS:self.assertTrue(items[section],section)

    def test_duplicate_breakdown_reaches_the_review_checklist(self):
        """逐字重复项要带分类落到清单里（1.0.109）：只给总数的话，老师不知道该改 quote_ref 还是删词条。"""
        write(self.out/'build-report.json',{'profile':'standard','delivery_status':'browser_checked',
            'authoring_cost':{'repeated_quotes':3,'exact_prose':1,'near_prose':0,'duplicate_entries':2,'estimated_saving':288},
            'quality_gate':{'warnings':[]}})
        items,_,_=qa_report.collect(self.out)
        text='\n'.join(items[qa_report.SECTIONS[1]])
        self.assertIn('重复引文 3 组',text)
        self.assertIn('完全相同解析 1 组',text)
        self.assertIn('同节重复词条 2 处',text)
        self.assertIn('约可省 288 字符',text)
        self.assertIn('quote_ref',text)
        self.assertNotIn('高度相似解析 0 组',text,'为 0 的分类不列进去，避免噪音')

    def test_duplicate_detail_rows_come_from_the_same_exam_json(self):
        """明细要直接可读（哪条引文重复、重复词条是哪两处），不必再跑一次命令。"""
        quote='The students opened a repair corner in the library last Friday afternoon.'
        exam={'sections':[{'id':'A','kind':'reading','paragraphs':[{'id':'A-p1','text':quote*3}],
            'vocabulary':[{'word':'repair','meaning':'x'},{'word':'repair','meaning':'y'}],
            'questions':[{'id':'21','analysis':quote,'evidence':[{'paragraph_id':'A-p1','quote':quote}]},
                         {'id':'22','analysis':quote,'evidence':[{'paragraph_id':'A-p1','quote':quote}]}]}]}
        write(self.out/'exam.json',exam)
        write(self.out/'build-report.json',{'profile':'standard','delivery_status':'x',
            'authoring_cost':{'repeated_quotes':1,'exact_prose':1,'near_prose':0,'duplicate_entries':1,'estimated_saving':300}})
        items,_,_=qa_report.collect(self.out)
        item=[row for row in items[qa_report.SECTIONS[1]] if row.startswith('逐字重复项')][0]
        self.assertIn('\n',item,'有明细时条目应带多行')
        self.assertIn('· 引文出现',item)
        self.assertIn('· 同节重复词条 repair',item)
        self.assertEqual(item.split('\n')[0].count('—— 结论'),0,'结论占位只在渲染时加到首行')
    def test_detail_rows_are_absent_without_exam_json(self):
        """没有 exam.json（旧产物）时只给计数与命令，不报错。"""
        write(self.out/'build-report.json',{'profile':'standard','delivery_status':'x',
            'authoring_cost':{'repeated_quotes':2,'exact_prose':0,'near_prose':0,'duplicate_entries':0,'estimated_saving':120}})
        items,_,_=qa_report.collect(self.out)
        item=[row for row in items[qa_report.SECTIONS[1]] if row.startswith('逐字重复项')][0]
        self.assertNotIn('\n',item)
        self.assertIn('重复引文 2 组',item)
    def test_detail_rows_are_capped_with_a_pointer_to_the_full_list(self):
        exam={'sections':[{'id':f'S{s}','kind':'reading','paragraphs':[{'id':f'S{s}-p1','text':'x'*200}],
            'vocabulary':[{'word':'repair','meaning':'a'},{'word':'repair','meaning':'b'}],'questions':[]} for s in range(8)]}
        write(self.out/'exam.json',exam)
        rows=qa_report.duplicate_rows(self.out)
        self.assertLessEqual(len(rows),qa_report.DETAIL_MAX)
        self.assertTrue(any('另有' in row and '--duplicates' in row for row in rows),rows)
    def test_rendered_detail_lines_are_not_counted_as_items(self):
        """明细行不是 "- [ ]"，check() 的条目计数与结论要求不受影响。"""
        quote='The students opened a repair corner in the library last Friday afternoon.'
        write(self.out/'exam.json',{'sections':[{'id':'A','kind':'reading','paragraphs':[{'id':'A-p1','text':quote*3}],
            'vocabulary':[{'word':'repair','meaning':'x'},{'word':'repair','meaning':'y'}],'questions':[]}]})
        write(self.out/'build-report.json',{'profile':'standard','delivery_status':'x',
            'authoring_cost':{'repeated_quotes':1,'exact_prose':0,'near_prose':0,'duplicate_entries':1,'estimated_saving':200}})
        items,report,_=qa_report.collect(self.out)
        path=self.out/'qa-report.md'
        path.write_text(fill(qa_report.render(items,report)),encoding='utf-8')
        result=qa_report.check(self.out)
        self.assertEqual(result['status'],'ok',result['problems'])
        self.assertEqual(result['items'],result['concluded'])
        # 条目数必须等于 collect() 产出的真实条目数：明细被算成条目时这里会变大
        expected=sum(len(items[section]) for section in qa_report.SECTIONS)
        self.assertEqual(result['items'],expected,
                         '明细行不是复核条目，不能被 check() 计数（否则老师要为每条明细写一遍结论）')
    def test_no_duplicates_is_stated_explicitly(self):
        items,_,_=qa_report.collect(self.out)   # 夹具的 build-report 没有 authoring_cost
        text='\n'.join(items[qa_report.SECTIONS[1]])
        self.assertIn('逐字重复项：无',text)

    def test_collect_without_any_reports_still_produces_every_section(self):
        empty=self.base/'empty';empty.mkdir()
        items,report,browser=qa_report.collect(empty)
        for section in qa_report.SECTIONS:self.assertTrue(items[section],section)
        self.assertIn('无',items[qa_report.SECTIONS[4]][0])
        self.assertIn('0 项',items[qa_report.SECTIONS[3]][0])

    def test_collect_tolerates_host_reports_without_item_names(self):
        """宿主自己写的 browser-check.json 可能只有 {status:passed}；清单必须照样生成，不能崩。"""
        write(self.out/'browser-check.json',{'status':'passed','checks':[{'status':'passed'},{}],
            'skipped':[{}]})
        items,report,_=qa_report.collect(self.out)          # 不得抛 TypeError
        section='\n'.join(items[qa_report.SECTIONS[3]])
        self.assertIn('已执行的浏览器操作 2 项',section)
        self.assertIn('未命名检查',section)
        self.assertIn('未说明原因',section)
        self.report().write_text(fill(qa_report.render(items,report)),encoding='utf-8')
        self.assertEqual(qa_report.check(self.out)['status'],'ok')

    def test_cli_init_refuses_to_overwrite_then_check_gates_on_conclusions(self):
        self.assertEqual(self.run_cli('init'),(0,'ok'))
        self.assertTrue(self.report().is_file())
        self.assertEqual(self.run_cli('init'),(1,'exists'))  # 不加 --force 不得覆盖已填写的结论
        self.assertEqual(self.run_cli('init','--force')[0],0)
        self.assertEqual(self.run_cli('check'),(1,'needs_fix'))
        self.report().write_text(fill(self.report().read_text(encoding='utf-8')),encoding='utf-8')
        self.assertEqual(self.run_cli('check'),(0,'ok'))

    def run_cli(self,*argv):
        output=io.StringIO()
        with unittest.mock.patch.object(sys,'argv',['qa_report.py',argv[0],str(self.out),*argv[1:]]),contextlib.redirect_stdout(output):
            code=qa_report.main()
        return code,json.loads(output.getvalue())['status']

    def test_init_writes_filled_template_rejects_empty_conclusions(self):
        items,report,_=qa_report.collect(self.out)
        self.report().write_text(qa_report.render(items,report),encoding='utf-8')
        result=qa_report.check(self.out)
        self.assertEqual(result['status'],'needs_fix')
        self.assertGreater(result['items'],0)
        self.assertEqual(result['concluded'],0)
        self.assertTrue(all('结论过短' in problem for problem in result['problems']))
        self.report().write_text(fill(self.report().read_text(encoding='utf-8')),encoding='utf-8')
        result=qa_report.check(self.out)
        self.assertEqual(result['status'],'ok',result['problems'])
        self.assertEqual(result['concluded'],result['items'])

    def test_check_rejects_placeholder_and_short_conclusions(self):
        """占位文字必须先于"过短"被报出——否则 '待填' 只会显示"结论过短"，看不出真正原因。

        另注：条目正文里本身含"非占位"字样，所以断言必须匹配问题前缀而不是 `in problem`，
        否则这里会变成一个永远为真的空断言。
        """
        items,report,_=qa_report.collect(self.out)
        template=qa_report.render(items,report)
        for bad in qa_report.PLACEHOLDERS:
            self.report().write_text(fill(template,bad),encoding='utf-8')
            result=qa_report.check(self.out)
            self.assertEqual(result['status'],'needs_fix',bad)
            self.assertTrue(result['problems'],bad)
            self.assertTrue(all(problem.startswith('结论仍是占位文字（') for problem in result['problems']),result['problems'][:2])
        for short in ('好','刚刚好六字'):
            self.report().write_text(fill(template,short),encoding='utf-8')
            result=qa_report.check(self.out)
            self.assertEqual(result['status'],'needs_fix',short)
            self.assertTrue(all(problem.startswith('结论过短（') for problem in result['problems']),result['problems'][:2])
        self.report().write_text(fill(template,'刚好够长结论'),encoding='utf-8')
        self.assertEqual(len('刚好够长结论'),qa_report.MIN_CONCLUSION)
        self.assertEqual(qa_report.check(self.out)['status'],'ok')

    def test_honest_sentences_containing_placeholder_words_are_not_rejected(self):
        """'待核/待补充' 出现在正常句子里是诚实结论，例如"已核对，无待核项"；只有整句近乎占位才拒。"""
        for honest in ('已逐题核对原卷，无待核项。','本卷听力边界不待补充，切点已试听。','全部条目核对完毕，没有 TODO 也没有省略。'):
            items,report,_=qa_report.collect(self.out)
            self.report().write_text(fill(qa_report.render(items,report),honest),encoding='utf-8')
            result=qa_report.check(self.out)
            self.assertEqual(result['status'],'ok',(honest,result['problems'][:2]))
        items,report,_=qa_report.collect(self.out)
        template=qa_report.render(items,report)
        for lazy in ('待核。','结论待补充','略'):
            self.report().write_text(fill(template,lazy),encoding='utf-8')
            result=qa_report.check(self.out)
            self.assertEqual(result['status'],'needs_fix',lazy)
            self.assertTrue(all(problem.startswith('结论仍是占位文字（') for problem in result['problems']),(lazy,result['problems'][:2]))

    def test_check_rejects_missing_file_section_and_emptied_file(self):
        missing=qa_report.check(self.out)
        self.assertEqual(missing['status'],'missing')
        self.assertIn('qa_report.py init',missing['problems'][0])
        items,report,_=qa_report.collect(self.out)
        template=fill(qa_report.render(items,report))
        section=qa_report.SECTIONS[2]
        self.report().write_text(template.replace(section,'## 3. 听力的边界'),encoding='utf-8')
        result=qa_report.check(self.out)
        self.assertEqual(result['status'],'needs_fix')
        self.assertTrue(any(f'缺少章节：{section}'==problem for problem in result['problems']),result['problems'])
        self.report().write_text('# 交付前人工复核\n\n全部都没问题。\n',encoding='utf-8')
        result=qa_report.check(self.out)
        self.assertEqual(result['status'],'needs_fix')
        self.assertTrue(any('没有任何' in problem for problem in result['problems']),result['problems'])

    def test_check_ignores_prose_and_only_reads_checkbox_items(self):
        items,report,_=qa_report.collect(self.out)
        text=fill(qa_report.render(items,report))+'\n补充说明：结论：总之没问题，老师可直接上课使用。\n'
        self.report().write_text(text,encoding='utf-8')
        self.assertEqual(qa_report.check(self.out)['status'],'ok')

    def test_sections_are_fixed_and_unique(self):
        self.assertEqual(len(set(qa_report.SECTIONS)),len(qa_report.SECTIONS))
        self.assertEqual(len(qa_report.SECTIONS),5)
        self.assertTrue(all(section.startswith('## ') for section in qa_report.SECTIONS))

if __name__=='__main__':unittest.main()
