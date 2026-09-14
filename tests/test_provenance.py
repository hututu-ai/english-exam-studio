"""The answer-provenance chain, which is this skill's headline authenticity claim.

answer original -> answers.json -> source-ledger.json -> exam.json -> build-time
cross-check. Each link must be provable; a table parsed from a different file than
the ledger registers is not provenance, and an official answer without a page or
position reference is not official.
"""
import hashlib,json,re,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import answer_audit
from quality_gate import audit_exam

def exam(answer='B',status='official'):
    return {'title':'t','sections':[{'id':'A','kind':'reading',
        'paragraphs':[{'id':'A-p1','text':'The museum opens at nine.'}],
        'questions':[{'id':'21','stem':'When does it open?','options':{'A':'Eight.','B':'Nine.'},'answer':answer,'answer_status':status}]}]}

class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'paper.pdf').write_bytes(b'%PDF-1.4 fake paper')
        (self.root/'answers.pdf').write_bytes(b'%PDF-1.4 fake answers')
        self.paper_sha=hashlib.sha256((self.root/'paper.pdf').read_bytes()).hexdigest()
        self.answers_sha=hashlib.sha256((self.root/'answers.pdf').read_bytes()).hexdigest()
    def tearDown(self):self.temp.cleanup()
    def ledger(self,include_answers=True,answer='B',status='official',reference='answers.pdf 第1页，21题',answers_sha=None):
        sources=[{'role':'paper','path':'paper.pdf','sha256':self.paper_sha}]
        if include_answers:sources.append({'role':'answers','path':'answers.pdf','sha256':answers_sha or self.answers_sha})
        question={'id':'21','stem':'When does it open?','options':{'A':'Eight.','B':'Nine.'},'answer':answer,'answer_status':status}
        if reference:question['answer_reference']=reference
        return {'sources':sources,'sections':[{'id':'A','kind':'reading',
            'paragraphs':[{'id':'A-p1','text':'The museum opens at nine.'}],'questions':[question]}]}
    def audit(self,ledger_data,table,exam_status='official'):
        ledger_path=self.root/'source-ledger.json'
        ledger_path.write_text(json.dumps(ledger_data,ensure_ascii=False),encoding='utf-8')
        key_path=None
        if table is not None:
            key_path=self.root/'answers.json'
            key_path.write_text(json.dumps(table,ensure_ascii=False),encoding='utf-8')
        return audit_exam(exam(status=exam_status),self.root,str(ledger_path),str(key_path) if key_path else None,None)
    def codes(self,result):return {error['code'] for error in result['errors']}
    def key(self,answers,sha=None):return {'answer_source':'answers.pdf','answer_source_sha256':sha or self.answers_sha,'answers':answers}
    def test_complete_consistent_chain_passes(self):
        result=self.audit(self.ledger(),self.key({'21':'B'}))
        self.assertEqual(result['status'],'automated_checks_passed',result['errors'])
    def test_official_answer_needs_a_position_reference(self):
        result=self.audit(self.ledger(reference=None),self.key({'21':'B'}))
        self.assertIn('answer_provenance',self.codes(result))
    def test_official_answer_needs_a_registered_answer_file(self):
        result=self.audit(self.ledger(include_answers=False),self.key({'21':'B'}))
        self.assertIn('official_answer_file',self.codes(result))
    def test_answer_table_needs_a_source_fingerprint(self):
        result=self.audit(self.ledger(),{'answers':{'21':'B'}})
        self.assertIn('answer_key_provenance',self.codes(result))
    def test_table_must_come_from_the_registered_answer_file(self):
        # Parsed from another file that happens to yield the same answers.
        other=self.root/'other.pdf';other.write_bytes(b'%PDF-1.4 a different answer file')
        result=self.audit(self.ledger(),self.key({'21':'B'},sha=hashlib.sha256(other.read_bytes()).hexdigest()))
        self.assertIn('answer_key_not_registered',self.codes(result))
    def test_conflicting_official_answer_blocks(self):
        result=self.audit(self.ledger(),self.key({'21':'C'}))
        self.assertIn('answer_key_mismatch',self.codes(result))
    def test_missing_entry_for_an_official_answer_blocks(self):
        result=self.audit(self.ledger(),self.key({'22':'C'}))
        self.assertIn('answer_key_entry_missing',self.codes(result))
    def test_sample_answers_do_not_require_the_official_chain(self):
        result=self.audit(self.ledger(include_answers=False,reference=None,status='sample'),None,exam_status='sample')
        codes=self.codes(result)
        self.assertNotIn('official_answer_file',codes)
        self.assertNotIn('answer_provenance',codes)
        self.assertEqual(result['status'],'automated_checks_passed',result['errors'])
    def test_word_answers_are_matched_for_grammar_items(self):
        # 语法填空 official answers are words; the key must be able to prove them.
        def grammar_exam(answer):return {'title':'t','sections':[{'id':'G','kind':'grammar',
            'paragraphs':[{'id':'G-p1','text':'The book {{56}} I read was good.'}],
            'questions':[{'id':'56','stem':'填关系代词','options':{},'answer':answer,'answer_status':'official'}]}]}
        ledger_data={'sources':[{'role':'paper','path':'paper.pdf','sha256':self.paper_sha},
                                {'role':'answers','path':'answers.pdf','sha256':self.answers_sha}],
            'sections':[{'id':'G','kind':'grammar','paragraphs':[{'id':'G-p1','text':'The book {{56}} I read was good.'}],
                'questions':[{'id':'56','stem':'填关系代词','options':{},'answer':'which','answer_status':'official','answer_reference':'answers.pdf 第1页，56题'}]}]}
        ledger_path=self.root/'source-ledger.json'
        ledger_path.write_text(json.dumps(ledger_data,ensure_ascii=False),encoding='utf-8')
        key_path=self.root/'answers.json'
        key_path.write_text(json.dumps(self.key({'56':'which'}),ensure_ascii=False),encoding='utf-8')
        ok=audit_exam(grammar_exam('which'),self.root,str(ledger_path),str(key_path),None)
        codes=self.codes(ok)
        self.assertNotIn('answer_key_entry_missing',codes)
        self.assertNotIn('answer_key_mismatch',codes)
        mismatch=audit_exam(grammar_exam('that'),self.root,str(ledger_path),str(key_path),None)
        self.assertIn('answer_key_mismatch',self.codes(mismatch))

class AnswerAuditGates(unittest.TestCase):
    """`answer_audit` 的每一条逐题判据都要有"注入缺陷必须被拦"的用例（1.0.113）。

    在此之前 15 条判据里只有 3 条被任何测试提到过（且都是答案表对照相关的），
    其余 12 条——包括 5 条**阻断级**（缺答案、缺客观题证据、证据段不存在、证据引句不在原段、
    与台账答案不一致）——把判据改松不会有测试报警。这里逐条注入缺陷。
    """
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.addCleanup(self.temp.cleanup)
    def exam(self,question=None,kind='reading',questions=None,paragraphs=None):
        base={'id':'21','stem':'When does the museum open?','options':{'A':"Eight o'clock",'B':"Nine o'clock"},
              'answer':'B','answer_status':'official','answer_source':'答案原件 第1页',
              'evidence':[{'paragraph_id':'A-p1','quote':'opens at nine'}]}
        base.update(question or {})
        return {'sections':[{'id':'A','kind':kind,
                             'paragraphs':paragraphs or [{'id':'A-p1','text':'The museum opens at nine in the morning.'}],
                             'questions':questions if questions is not None else [base]}]}
    def codes(self,report,where='blocking'):return [row['code'] for row in report[where]]
    def key(self,table):
        path=self.root/'answers.json';path.write_text(json.dumps({'answers':table},ensure_ascii=False),encoding='utf-8');return str(path)
    def ledger(self,answer='B',stem='When does the museum open?'):
        path=self.root/'source-ledger.json'
        path.write_text(json.dumps({'sections':[{'id':'A','questions':[{'id':'21','stem':stem,'answer':answer}]}]},ensure_ascii=False),encoding='utf-8')
        return str(path)

    def test_clean_baseline_passes_without_flags(self):
        """基线必须完全干净，否则下面的注入用例分不清"是注入导致的"还是本来就报。"""
        report=answer_audit.audit(self.exam())
        self.assertEqual(report['blocking'],[],report['blocking'])
        self.assertEqual(report['review'],[],report['review'])
        self.assertEqual(report['status'],'answer_checks_passed')

    # —— 阻断级 ——
    def test_answer_missing_blocks(self):
        report=answer_audit.audit(self.exam({'answer':None}))
        self.assertIn('answer_missing',self.codes(report));self.assertEqual(report['status'],'blocked')
    def test_answer_outside_options_blocks(self):
        report=answer_audit.audit(self.exam({'answer':'C'}))
        self.assertIn('answer_not_in_options',self.codes(report))
    def test_objective_without_evidence_blocks(self):
        report=answer_audit.audit(self.exam({'evidence':[]}))
        self.assertIn('evidence_missing',self.codes(report))
    def test_evidence_pointing_at_unknown_paragraph_blocks(self):
        report=answer_audit.audit(self.exam({'evidence':[{'paragraph_id':'NOPE','quote':'x'}]}))
        self.assertIn('evidence_paragraph_unknown',self.codes(report))
    def test_evidence_quote_not_in_the_passage_blocks(self):
        report=answer_audit.audit(self.exam({'evidence':[{'paragraph_id':'A-p1','quote':'nowhere in this passage'}]}))
        self.assertIn('evidence_quote_absent',self.codes(report))
    def test_official_answer_disagreeing_with_the_key_blocks(self):
        report=answer_audit.audit(self.exam(),None,self.key({'21':'C'}))
        self.assertIn('answer_key_mismatch',self.codes(report))
    def test_answer_disagreeing_with_the_ledger_blocks(self):
        report=answer_audit.audit(self.exam({'answer':'A'}),self.ledger(answer='B'))
        self.assertIn('ledger_answer_mismatch',self.codes(report))

    # —— 待核级（不阻断，但要被点名）——
    def test_key_without_an_entry_is_flagged(self):
        report=answer_audit.audit(self.exam(),None,self.key({'22':'C'}))
        self.assertIn('answer_key_missing',self.codes(report,'review'))
        self.assertEqual(report['blocking'],[])
        self.assertEqual(report['status'],'review_required')
    def test_vague_answer_source_is_flagged(self):
        report=answer_audit.audit(self.exam({'answer_source':'老师说的'}))
        self.assertIn('answer_source_vague',self.codes(report,'review'))
    def test_stem_drifting_from_the_ledger_is_flagged(self):
        report=answer_audit.audit(self.exam(),self.ledger(stem='完全不同的题干'))
        self.assertIn('ledger_stem_drift',self.codes(report,'review'))
    def test_option_without_word_overlap_with_evidence_is_flagged(self):
        report=answer_audit.audit(self.exam({'options':{'A':"Eight o'clock",'B':'Morning brightness'}}))
        self.assertIn('evidence_option_low_overlap',self.codes(report,'review'))
    def test_overlong_cloze_answer_is_flagged(self):
        question={'options':{'A':'one two three four','B':'x'},'answer':'A'}
        report=answer_audit.audit(self.exam(question,kind='cloze'))
        self.assertIn('cloze_answer_too_long',self.codes(report,'review'))
    def test_grammar_answer_with_stray_punctuation_is_flagged(self):
        question={'options':{},'answer':'which，，','evidence':[{'paragraph_id':'A-p1','quote':'opens at nine'}]}
        report=answer_audit.audit(self.exam(question,kind='grammar'))
        self.assertIn('grammar_answer_suspicious',self.codes(report,'review'))
    def distribution(self,letters):
        return [{'id':str(20+i),'stem':f'q{i}','options':{'A':'a','B':'b','C':'c','D':'d'},'answer':letter,
                 'answer_status':'official','answer_source':'答案原件 第1页',
                 'evidence':[{'paragraph_id':'A-p1','quote':'opens at nine'}]} for i,letter in enumerate(letters,1)]
    def test_cloze_answer_distribution_skew_is_flagged_just_above_the_threshold(self):
        """阈值两侧各测一次：5/11=45.5% 要报，5/12=41.7% 不报（判据是"超过 45% 提示"）。"""
        above=answer_audit.audit(self.exam(kind='cloze',questions=self.distribution('AAAAABBBBCC')))
        self.assertIn('answer_distribution_skew',self.codes(above,'review'))
        below=answer_audit.audit(self.exam(kind='cloze',questions=self.distribution('AAAAABBBBCCC')))
        self.assertNotIn('answer_distribution_skew',self.codes(below,'review'))
        self.assertEqual(below['blocking'],[],'分布只是提示，不阻断')
    def test_multi_letter_answer_is_flagged_not_blocked(self):
        question={'options':{'A':'a','B':'b','C':'c','D':'d'},'answer':'AB'}
        report=answer_audit.audit(self.exam(question))
        self.assertIn('answer_multi_letters',self.codes(report,'review'))
        self.assertEqual(report['blocking'],[])

    def test_every_criterion_in_the_source_has_a_test_somewhere(self):
        """守卫：以后新增一条判据，必须在测试里出现，否则这条会失败。"""
        source=(ROOT/'scripts'/'answer_audit.py').read_text(encoding='utf-8')
        criteria=sorted(set(re.findall(r"(?:block|flag)\('([a-z_]+)'",source)))
        self.assertGreaterEqual(len(criteria),15,'判据数量异常，先确认是不是提取正则失效了')
        tests='\n'.join(path.read_text(encoding='utf-8') for path in (ROOT/'tests').glob('*.py'))
        missing=[code for code in criteria if code not in tests]
        self.assertEqual(missing,[],f'这些判据没有任何测试提到：{missing}')

class AnswerFormTests(unittest.TestCase):
    """同一个答案的不同合法写法，不许在两道闸门之间判出不同结果（1.0.101）。

    schema 允许 `answer` 写"合理变体数组"（页面按 `answer.includes(key)` 判定，显示成 A / B），
    而答案原件里的多选会解析成 'AB'。这两种写法以前一道闸门放行、另一道闸门阻断。
    """
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.addCleanup(self.temp.cleanup)
    def key(self,table):
        p=self.root/'answers.json';p.write_text(json.dumps({'answers':table,'answer_source_sha256':'x'*64},ensure_ascii=False),encoding='utf-8');return str(p)
    def exam(self,answer,status='official'):
        return {'title':'t','sections':[{'id':'A','kind':'reading',
            'paragraphs':[{'id':'A-p1','text':'Both a and b are fine.'}],
            'questions':[{'id':'21','stem':'Which two?','options':{'A':'a','B':'b','C':'c','D':'d'},
                'answer':answer,'answer_status':status,'answer_source':'答案第1页',
                'evidence':[{'paragraph_id':'A-p1','quote':'Both a and b are fine.'}]}]}]}
    def gates(self,answer,table):
        from answer_audit import audit as answer_audit
        exam=self.exam(answer);key=self.key(table)
        audit=answer_audit(exam,None,key)
        gate=audit_exam(exam,self.root,None,key,None)
        audit_codes=[e['code'] for e in audit['blocking']]
        gate_codes=[e['code'] for e in gate['errors']]
        return audit,audit_codes,[c for c in gate_codes if c.startswith('answer_key')],gate_codes

    def test_shared_comparison_covers_letters_variants_and_words(self):
        from answers import answer_match
        for expected,given,want in [('AB',['A','B'],True),('AB','AB',True),('A',['A','B'],True),('AB',['A'],False),
                                    ('A',['B'],False),('which','which',True),('which','that',False),
                                    ('AB',['A','B','C'],False),('A、B',['B','A'],True),('HEAD','head',True),
                                    ('CAT',['C','A'],False),('AB',[],False),('',['A'],False)]:
            with self.subTest(expected=expected,given=given):
                self.assertEqual(answer_match(expected,given),want)
    def test_both_gates_accept_the_same_legitimate_forms(self):
        for answer,table in [(['A','B'],{'21':'AB'}),(['A','B'],{'21':'A'}),('AB',{'21':'AB'}),('AB',{'21':'A B'}),(['A','B'],{'21':'A、B'})]:
            with self.subTest(answer=answer,table=table):
                _,audit_codes,gate_key_codes,gate_codes=self.gates(answer,table)
                self.assertEqual(audit_codes,[],audit_codes)
                self.assertEqual(gate_key_codes,[],gate_key_codes)
    def test_both_gates_block_the_same_real_mismatches(self):
        for answer,table in [(['A'],{'21':'AB'}),(['A','B','C'],{'21':'AB'}),('cat',{'21':'AB'}),(['B'],{'21':'A'})]:
            with self.subTest(answer=answer,table=table):
                audit,audit_codes,gate_key_codes,_=self.gates(answer,table)
                self.assertIn('answer_key_mismatch',audit_codes,audit_codes)
                self.assertIn('answer_key_mismatch',gate_key_codes,gate_key_codes)
    def test_a_word_answer_for_an_mcq_still_blocks_on_its_own(self):
        """没有答案表时也要拦住：'cat' 不是选项字母，不能因为"字母都在 A–H 里"就放过。"""
        from answer_audit import audit as answer_audit
        audit=answer_audit(self.exam('cat'),None,None)
        self.assertIn('answer_not_in_options',[e['code'] for e in audit['blocking']],audit['blocking'])
    def test_multi_letter_answer_is_accepted_but_flagged_for_review(self):
        from answer_audit import audit as answer_audit
        audit=answer_audit(self.exam('AB'),None,None)
        self.assertEqual([e['code'] for e in audit['blocking']],[],audit['blocking'])
        flags=[e for e in audit['review'] if e['code']=='answer_multi_letters']
        self.assertTrue(flags,audit['review'])
        self.assertIn('多选',flags[0]['message'])
        self.assertIn('单选',flags[0]['message'])
        self.assertEqual(audit['status'],'review_required')
    def test_a_variant_array_of_single_letters_is_not_flagged_as_multi_select(self):
        from answer_audit import audit as answer_audit
        audit=answer_audit(self.exam(['A','B']),None,None)
        self.assertEqual([e['code'] for e in audit['blocking']],[],audit['blocking'])
        self.assertNotIn('answer_multi_letters',[e['code'] for e in audit['review']],audit['review'])
