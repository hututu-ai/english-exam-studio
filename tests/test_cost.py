import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build
from cost import analyze,lastkey,walk
class CostTests(unittest.TestCase):
    def setUp(self):
        self.exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
    def quotes(self,exam):
        return [(p,v) for p,v in walk(exam) if lastkey(p) in {'quote','source_quote'} and isinstance(v,str) and v.strip()]
    def test_dictionary_is_not_counted_as_authored_prose(self):
        base=analyze(self.exam)['authored_chars']
        with_dict=analyze({**self.exam,'dictionary':{'word':{'meaning':'x'*5000,'english':'y'*5000}}})
        self.assertEqual(with_dict['authored_chars'],base)
    def test_long_quotes_are_reported_as_savings(self):
        report=analyze(self.exam,min_quote=20)
        self.assertTrue(report['long_quote_candidates'])
        self.assertEqual(report['estimated_quote_ref_saving'],sum(c['saving'] for c in report['long_quote_candidates']))
        self.assertTrue(all(c['chars']>20 and c['saving']>0 for c in report['long_quote_candidates']))
        self.assertEqual(report['quote_chars'],sum(len(v) for _,v in self.quotes(self.exam)))
        self.assertEqual(report['inline_quotes'],len(self.quotes(self.exam)))
    def test_short_quotes_are_not_reported(self):
        report=analyze(self.exam,min_quote=500)
        self.assertEqual(report['long_quote_candidates'],[])
        self.assertEqual(report['estimated_quote_ref_saving'],0)
    def test_build_report_records_timing_and_authoring_cost(self):
        output=io.StringIO()
        with tempfile.TemporaryDirectory() as temp:
            with contextlib.redirect_stdout(output):
                build.build(ROOT/'examples/demo-reading.json',Path(temp)/'out',ROOT/'examples/source-ledger.json')
            report=json.loads(output.getvalue())
        for key in ('prepare_audio','validate','quality_gate','answer_audit','render_and_write'):
            self.assertIn(key,report['timing'])
            self.assertGreaterEqual(report['timing'][key],0)
        cost=report['authoring_cost']
        self.assertGreater(cost['authored_chars'],0)
        self.assertLess(cost['authored_chars'],10000)
        self.assertEqual(cost['inline_quotes'],len(self.quotes(self.exam)))

class DuplicateDetection(unittest.TestCase):
    """重复检测：把"白写两遍"的字数算出来，但绝不自动删改。"""

    def setUp(self):
        self.exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))

    def test_repeated_quote_is_reported_with_saving_math(self):
        from cost import duplicates
        exam=json.loads(json.dumps(self.exam,ensure_ascii=False))
        section=exam['sections'][0]
        quote=section['sentences'][0]['quote']
        section['questions'][0]['evidence']=[{'paragraph_id':section['sentences'][0]['paragraph_id'],'quote':quote}]
        found=duplicates(exam)
        group=[item for item in found['repeated_quotes'] if item['chars']==len(quote)]
        self.assertTrue(group,'同一句引文出现在 sentences 与 evidence 里，必须被检测出来')
        self.assertGreaterEqual(group[0]['count'],2)
        self.assertEqual(group[0]['saving'],len(quote)*(group[0]['count']-1))
        self.assertGreater(found['estimated_saving'],0)

    def test_near_duplicate_prose_is_detected_across_sections(self):
        from cost import duplicates
        exam=json.loads(json.dumps(self.exam,ensure_ascii=False))
        long_prose='先看首段的例子，再回到题干核对时间与动作，最后排除凭空加条件的选项，这样每一步都有原文依据可指。'
        clone=json.loads(json.dumps(exam['sections'][0],ensure_ascii=False))
        clone['id']='B'
        for i,question in enumerate(clone['questions']):question['id']=str(30+i)
        exam['sections'][0]['questions'][0]['analysis']=long_prose
        clone['questions'][0]['analysis']=long_prose[:-1]+'！'        # 只差一个标点：近似而非完全相同
        exam['sections'].append(clone)
        found=duplicates(exam)
        self.assertTrue(found['near_prose'],'跨节近似解析必须被检测出来（构建只拦同一节内的完全重复）')
        self.assertIn('sections[0]',found['near_prose'][0]['a'])
        self.assertGreaterEqual(found['near_prose'][0]['ratio'],0.9)

    def test_duplicate_word_entries_in_the_same_section(self):
        from cost import duplicates
        exam=json.loads(json.dumps(self.exam,ensure_ascii=False))
        section=exam['sections'][0]
        section['vocabulary'].append(json.loads(json.dumps(section['vocabulary'][0])))
        found=duplicates(exam)
        self.assertTrue(found['duplicate_entries'],'同一节里同一个词写两遍必须被报出')
        self.assertEqual(found['duplicate_entries'][0]['word'],section['vocabulary'][0]['word'].lower())

    def test_optimized_scan_matches_the_plain_pairwise_scan(self):
        """近似重复扫描用长度上界 + quick_ratio 先筛：**结果必须与朴素两两扫描完全一致**。

        真实整卷上朴素扫描是 O(n²) 次 difflib.ratio()，光这一项就要几秒到十几秒（实测 32 节 3.3s），
        而它只是编写量报告；优化不能改变报出来的条目与顺序。
        """
        import difflib
        from cost import AUTHORED_KEYS,QUOTE_KEYS,duplicates,lastkey,walk
        exam=json.loads(json.dumps(self.exam,ensure_ascii=False))
        base_text='先看首段的例子，再回到题干核对时间与动作，最后排除凭空加条件的选项，这样每一步都有原文依据可指'
        for index,offset in enumerate(('。','！','；')):
            clone=json.loads(json.dumps(exam['sections'][0],ensure_ascii=False))
            clone['id']=f'C{index}'
            for number,question in enumerate(clone['questions']):question['id']=str(40+index*10+number)
            clone['questions'][0]['analysis']=base_text+offset
            clone['questions'][0]['pitfall']=base_text+offset+'注意别把推断当原文。'
            exam['sections'].append(clone)

        def plain_pairwise(document,threshold=0.9,min_chars=30,max_items=400):
            prose=[]
            for path,value in walk({k:v for k,v in document.items() if k not in ('dictionary','legacy_dictionary')}):
                if isinstance(value,str) and value.strip() and lastkey(path) in AUTHORED_KEYS:
                    prose.append((path,value.strip()))
            near=[];seen=set()
            sample=[(p,v) for p,v in prose if len(v)>=min_chars][:max_items]
            for i in range(len(sample)):
                for j in range(i+1,len(sample)):
                    (pa,va),(pb,vb)=sample[i],sample[j]
                    if va==vb or (va,vb) in seen:continue
                    ratio=difflib.SequenceMatcher(None,va,vb).ratio()
                    if ratio>=threshold:
                        seen.add((va,vb))
                        near.append({'ratio':round(ratio,2),'chars':min(len(va),len(vb)),'saving':min(len(va),len(vb)),
                                     'a':pa,'b':pb,'sample':va[:50]})
            near.sort(key=lambda item:item['saving'],reverse=True)
            return near[:20]

        expected=plain_pairwise(exam)
        self.assertTrue(expected,'夹具本身要能产生近似重复，否则这个测试没有意义')
        found=duplicates(exam)
        self.assertEqual(found['near_prose'],expected,'优化后的扫描必须报出同样的条目与顺序')

    def test_hopeless_pairs_never_reach_the_expensive_ratio(self):
        """长度差太大时 ratio() 不可能达标：这类组合不该再调用昂贵的 ratio()。"""
        import difflib
        from cost import duplicates
        exam=json.loads(json.dumps(self.exam,ensure_ascii=False))
        for index,length in enumerate((35,80,200,400,900)):
            clone=json.loads(json.dumps(exam['sections'][0],ensure_ascii=False))
            clone['id']=f'L{index}'
            for number,question in enumerate(clone['questions']):question['id']=str(60+index*10+number)
            clone['questions'][0]['analysis']=('这一段解析只讲本题依据，长度' + str(length) + '，')*max(1,length//18)
            exam['sections'].append(clone)
        calls={'ratio':0}
        original=difflib.SequenceMatcher.ratio
        def counting(self):
            calls['ratio']+=1
            return original(self)
        difflib.SequenceMatcher.ratio=counting
        try:
            found=duplicates(exam)
        finally:
            difflib.SequenceMatcher.ratio=original
        prose=[value for _,value in __import__('cost').walk(exam)
               if isinstance(value,str) and len(value)>=30]
        pairs=len(prose)*(len(prose)-1)//2
        self.assertLess(calls['ratio'],pairs*0.25,
                        f'提前筛掉的不可能达标的组合太少：调用 {calls["ratio"]} 次 / 共 {pairs} 对')
        self.assertIsInstance(found['near_prose'],list)

    def test_review_candidates_never_miss_a_real_shared_phrase(self):
        """倒排索引是**必要**条件：凡是真有 >=min_common 字连续相同的对，必须都在候选里。"""
        from cost import candidate_pairs
        texts=['把 loose 的语境义讲清楚，注意与 lose 区分。',
               '注意与 lose 区分：把 loose 的语境义讲清楚。',
               '这一句完全无关，讲的是别的事情，没有任何共同长片段。',
               '本句里有没有十个字连续一样呢，应该没有吧。']
        pairs=set(candidate_pairs(texts,10))
        self.assertIn((0,1),pairs,'共享"把 loose 的语境义讲清楚"必须成为候选')
        import difflib
        for i in range(len(texts)):
            for j in range(i+1,len(texts)):
                match=difflib.SequenceMatcher(None,texts[i],texts[j]).find_longest_match(0,len(texts[i]),0,len(texts[j]))
                if match.size>=10:
                    self.assertIn((i,j),pairs,f'({i},{j}) 实际共享 {match.size} 字，不能在候选里漏掉')
        self.assertEqual(candidate_pairs(['短'],10),[],'短于 min_common 的文本没有候选对')
        self.assertEqual(candidate_pairs(['abc','abd'],2),[(0,1)],'min_common 很小时退回全量组合，结果仍要对')

    def test_review_pairs_hint_total_matches_the_plain_pairwise_scan(self):
        """去重复核清单也要"加速不改结果"：条数、内容与顺序都必须与朴素扫描一致。"""
        import difflib
        from cost import AUTHORED_KEYS,review_pairs,walk,lastkey
        fields=('analysis','type_note','pitfall','strategy','context','note','why','explanation')
        exam=json.loads(json.dumps(self.exam,ensure_ascii=False))
        for index,offset in enumerate(('。','！','；')):
            clone=json.loads(json.dumps(exam['sections'][0],ensure_ascii=False))
            clone['id']=f'R{index}'
            for number,question in enumerate(clone['questions']):question['id']=str(70+index*10+number)
            clone['questions'][0]['analysis']='先看首段的例子，再回到题干核对时间与动作，最后排除凭空加条件的选项'+offset
            exam['sections'].append(clone)

        def plain(document,min_common=10):
            from collections import defaultdict
            index=defaultdict(list)
            for path,value in walk(document):
                if not isinstance(value,str) or not value.strip():continue
                key=lastkey(path)
                if key in fields:index[key].append({'path':path,'chars':len(value.strip()),'text':value.strip()[:60]})
            hints=[]
            for key,rows in index.items():
                for i in range(len(rows)):
                    for j in range(i+1,len(rows)):
                        a,b=rows[i]['text'],rows[j]['text']
                        match=difflib.SequenceMatcher(None,a,b).find_longest_match(0,len(a),0,len(b))
                        if match.size>=min_common:
                            hints.append({'field':key,'common_chars':match.size,'shared':a[match.a:match.a+match.size],
                                          'a':rows[i]['path'],'b':rows[j]['path']})
            hints.sort(key=lambda item:item['common_chars'],reverse=True)
            return hints

        expected=plain(exam)
        self.assertTrue(expected,'夹具要能产生提示，否则这个测试没有意义')
        found=review_pairs(exam)
        self.assertEqual(found['hint_total'],len(expected),'提示总数必须与朴素扫描一致')
        self.assertEqual(found['same_phrase_hints'],expected[:20],'前 20 条的内容与顺序也必须一致')
        self.assertIn('analysis',found['index'])

    def test_clean_exam_reports_no_savings(self):
        from cost import duplicates
        exam={'title':'没有重复的卷子','sections':[
            {'id':'A','paragraphs':[{'id':'A-p1','text':'First passage text for the check.'}],
             'questions':[{'id':'1','analysis':'第一题的解析，讲清依据与排除理由，不与别题重复。',
                           'evidence':[{'paragraph_id':'A-p1','quote':'First passage text'}]}]},
            {'id':'B','paragraphs':[{'id':'B-p1','text':'Second passage text for the check.'}],
             'questions':[{'id':'2','analysis':'第二题另讲一套方法，句子与上一节完全不同，避免近似。',
                           'evidence':[{'paragraph_id':'B-p1','quote':'Second passage text'}]}]}]}
        found=duplicates(exam)
        self.assertEqual(found['estimated_saving'],0,found)
        self.assertEqual(found['repeated_quotes'],[])
        self.assertEqual(found['near_prose'],[])
        self.assertEqual(found['duplicate_entries'],[])

    def test_analyze_exposes_duplicate_summary_and_notes(self):
        report=analyze(self.exam)
        self.assertIn('duplicates',report)
        self.assertIn('estimated_saving',report['duplicates'])
        self.assertTrue(any('重复' in note for note in report['notes']))

    def test_build_report_counts_duplicates_without_blocking(self):
        import tempfile
        from pathlib import Path as _Path
        with tempfile.TemporaryDirectory() as temp:
            base=_Path(temp)
            exam=json.loads(json.dumps(self.exam,ensure_ascii=False))
            section=exam['sections'][0]
            quote=section['sentences'][0]['quote']
            section['questions'][0]['evidence']=[{'paragraph_id':section['sentences'][0]['paragraph_id'],'quote':quote}]
            source=base/'exam.json';source.write_text(json.dumps(exam,ensure_ascii=False),encoding='utf-8')
            ledger={'sources':[{'role':'original_demo','path':source.name,
                                'sha256':__import__('hashlib').sha256(source.read_bytes()).hexdigest()}],
                    'sections':exam['sections']}
            (base/'source-ledger.json').write_text(json.dumps(ledger,ensure_ascii=False),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):build.build(source,base/'out',base/'source-ledger.json')
            report=json.loads((base/'out'/'build-report.json').read_text(encoding='utf-8'))
            self.assertIn('estimated_saving',report['authoring_cost'])
            self.assertEqual(report['status'],'structural_checks_passed','重复内容只提醒，绝不阻断构建')

class ReviewIndex(unittest.TestCase):
    """去重复核清单：脚本不判断改写，只并排列出 + 连续相同片段的弱信号。"""

    def setUp(self):
        self.exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))

    def test_index_lists_same_kind_prose_by_location(self):
        from cost import review_pairs
        report=review_pairs(self.exam)
        self.assertIn('analysis',report['index'])
        rows=report['index']['analysis']
        question_rows=[row for row in rows if row['path'].startswith('sections[0].questions[')]
        self.assertEqual(len(question_rows),2,'两题的解析都应列出')
        self.assertTrue(all(row['path'].startswith('sections[0].') for row in rows))
        self.assertTrue(all(row['chars']>0 and row['text'] for row in rows))
        self.assertIn('脚本不判断',report['scope'])

    def test_long_shared_phrase_is_hinted(self):
        from cost import review_pairs
        exam=json.loads(json.dumps(self.exam,ensure_ascii=False))
        shared='遇到目的题先找 so that 再看选项是否保留行动对象'
        exam['sections'][0]['questions'][0]['analysis']=shared+'，然后排除无关项。'
        exam['sections'][0]['questions'][1]['analysis']=shared+'，最后核对标题覆盖全文。'
        report=review_pairs(exam)
        self.assertTrue(report['same_phrase_hints'],'连续 ≥10 字相同必须给出提示')
        hint=report['same_phrase_hints'][0]
        self.assertGreaterEqual(hint['common_chars'],10)
        self.assertIn('so that',hint['shared'])

    def test_paraphrase_is_not_claimed_as_duplicate(self):
        """真正的改写（无长片段相同）不该被当成重复——脚本只说"请人工看"。"""
        from cost import review_pairs
        exam=json.loads(json.dumps(self.exam,ensure_ascii=False))
        exam['sections'][0]['questions'][0]['analysis']='先看首段的例子，再回到题干核对时间与动作。'
        exam['sections'][0]['questions'][1]['analysis']='先读第一段的例子，然后对照题干检查时间和动作。'
        report=review_pairs(exam)
        self.assertEqual(report['same_phrase_hints'],[],'改写不该被断言成重复')
        self.assertIn('analysis',report['index'],'但内容仍要列进人工扫读清单')

    def test_build_report_carries_the_review_index_and_pending_item(self):
        import tempfile
        from pathlib import Path as _Path
        with tempfile.TemporaryDirectory() as temp:
            base=_Path(temp)
            source=base/'exam.json';source.write_text(json.dumps(self.exam,ensure_ascii=False),encoding='utf-8')
            ledger={'sources':[{'role':'original_demo','path':source.name,
                                'sha256':__import__('hashlib').sha256(source.read_bytes()).hexdigest()}],
                    'sections':self.exam['sections']}
            (base/'source-ledger.json').write_text(json.dumps(ledger,ensure_ascii=False),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):build.build(source,base/'out',base/'source-ledger.json')
            report=json.loads((base/'out'/'build-report.json').read_text(encoding='utf-8'))
            self.assertIn('review_index',report['authoring_cost'])
            self.assertTrue(any('去重复核' in item for item in report['pending_items']),report['pending_items'])
            self.assertEqual(report['status'],'structural_checks_passed','去重复核只提醒，不阻断')
