"""Image-only material: 图片版试卷、图片版答案、图片版听力原文.

Teachers with no PDF still need page order, missing-page and duplicate detection, and an
honest provenance label for answers that can only be read by eye — the machine cannot
verify the glyphs, so it must say so instead of pretending a parser checked them.
"""
import binascii,contextlib,hashlib,io,json,struct,subprocess,sys,tempfile,unittest,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build,image_pages
from image_pages import page_set_digest
from quality_gate import audit_exam
from verify_output import verify_output

def png(path,width,height,color):
    raw=b''.join(b'\x00'+bytes(color)*width for _ in range(height))
    def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',binascii.crc32(tag+data)&0xffffffff)
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))

def run(script,*args,cwd=None):
    return subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,args)],
                          capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60,cwd=str(cwd) if cwd else None)

class ImagePageInventoryTests(unittest.TestCase):
    def test_natural_order_and_page_dimensions(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'paper').mkdir()
            for index,name in enumerate(('page-1.png','page-2.png','page-10.png'),1):
                png(root/'paper'/name,60,80,(10*index,10,10))
            report=image_pages.inventory([],str(root/'paper'),'paper',relative_to=root)
            self.assertEqual([p['path'] for p in report['pages']],['paper/page-1.png','paper/page-2.png','paper/page-10.png'])
            self.assertEqual([p['index'] for p in report['pages']],[1,2,3])
            self.assertEqual((report['pages'][0]['width'],report['pages'][0]['height']),(60,80))
            self.assertNotIn('duplicate_page',{item['code'] for item in report['problems']})
    def test_nested_photo_folders_are_refused_not_silently_mixed(self):
        """老师的"原图/裁剪"两个子目录同时存在时，页集合会悄悄变成几倍、顺序还会穿插。

        真发生过：`--dir 试卷图片` 递归到 `原图/` 与 `裁剪/`，2 页的卷子变成 3 个"页"，
        而且按文件名排序把 `原图/01`、`裁剪/01`、`原图/02` 排在一起，problems 却是空的。
        """
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            png(root/'试卷图片'/'原图'/'01.png',80,60,(200,10,10))
            png(root/'试卷图片'/'原图'/'02.png',80,60,(10,200,10))
            png(root/'试卷图片'/'裁剪'/'01.png',40,60,(180,20,20))
            report=image_pages.inventory([],str(root/'试卷图片'),'paper',relative_to=root)
            codes={item['code'] for item in report['problems']}
            self.assertIn('images_from_multiple_dirs',codes,'多目录混装必须报出来，不能静默拼在一起')
            message=next(item['message'] for item in report['problems'] if item['code']=='images_from_multiple_dirs')
            self.assertIn('01.png',message,'同名页（原图/裁剪各一份）要点名')
            self.assertIn('--dir',message,'要给出可照做的下一步')
            result=run('image_pages.py','--dir',root/'试卷图片','--role','paper','--out',root/'i.json',cwd=root)
            self.assertEqual(result.returncode,1,'有问题就返回 1，不假装通过')
            self.assertTrue((root/'i.json').is_file(),'报告仍要写出来，便于照单核对')

    def test_junk_files_in_the_photo_folder_are_ignored(self):
        """手机/系统带进来的 .DS_Store、Thumbs.db、desktop.ini、说明.txt 不是页。"""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'paper').mkdir()
            png(root/'paper'/'01.png',60,80,(1,1,1));png(root/'paper'/'02.png',60,80,(2,2,2))
            for junk in ('.DS_Store','Thumbs.db','desktop.ini','说明.txt','page.docx'):
                (root/'paper'/junk).write_bytes(b'junk')
            report=image_pages.inventory([],str(root/'paper'),'paper',relative_to=root)
            self.assertEqual(report['page_count'],2,report['pages'])
            self.assertEqual(report['problems'],[])

    def test_explicit_file_list_may_span_directories(self):
        """人自己按页序列全的文件：跨目录是刻意选择，不该拦。"""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            png(root/'a'/'01.png',60,80,(1,1,1));png(root/'b'/'02.png',60,80,(2,2,2))
            report=image_pages.inventory([str(root/'a'/'01.png'),str(root/'b'/'02.png')],[],'paper',relative_to=root)
            self.assertEqual(report['page_count'],2)
            self.assertEqual(report['problems'],[])

    def test_duplicate_and_missing_pages_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'paper').mkdir()
            for number in (1,2,4,5):
                png(root/'paper'/f'page-{number}.png',60,80,(10*number,10,10))
            png(root/'paper'/'page-5b.png',60,80,(50,10,10))   # byte-identical re-shot copy of page 5
            report=image_pages.inventory([],str(root/'paper'),'paper',relative_to=root)
            codes={item['code'] for item in report['problems']}
            self.assertIn('duplicate_page',codes)
            self.assertIn('possible_missing_page',codes)
    def test_empty_and_unreadable_files_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'paper').mkdir()
            (root/'paper'/'page-1.png').write_bytes(b'')
            (root/'paper'/'page-2.png').write_bytes(b'not really a png')
            report=image_pages.inventory([],str(root/'paper'),'paper',relative_to=root)
            codes={item['code'] for item in report['problems']}
            self.assertIn('empty_file',codes)
            self.assertIn('unreadable_image',codes)
    def test_digest_is_order_sensitive(self):
        pages=[{'index':1,'path':'a.png','sha256':'a'*64},{'index':2,'path':'b.png','sha256':'b'*64}]
        self.assertNotEqual(page_set_digest(pages),page_set_digest(list(reversed(pages))))
    def test_cli_writes_the_inventory_and_reports_problems(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'paper').mkdir()
            png(root/'paper'/'page-1.png',10,10,(1,2,3))
            out=root/'inv.json'
            result=run('image_pages.py','--dir','paper','--role','paper','--out','inv.json',cwd=root)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(out.read_text(encoding='utf-8'))['page_count'],1)
            self.assertEqual(json.loads(out.read_text(encoding='utf-8'))['pages'][0]['path'],'paper/page-1.png')
    def test_pages_outside_the_report_directory_are_flagged(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'elsewhere').mkdir()
            png(root/'elsewhere'/'page-1.png',10,10,(1,2,3))
            report=image_pages.inventory([],str(root/'elsewhere'),'paper',relative_to=root/'work')
            self.assertIn('path_outside_base',{item['code'] for item in report['problems']})

class ImageLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'paper').mkdir();(self.root/'answers').mkdir()
        png(self.root/'paper'/'page-1.png',60,80,(20,20,20))
        png(self.root/'paper'/'page-2.png',60,80,(40,40,40))
        png(self.root/'answers'/'answer-1.png',50,70,(60,60,60))
        self.paper=image_pages.inventory([],str(self.root/'paper'),'paper',relative_to=self.root)
        self.answers=image_pages.inventory([],str(self.root/'answers'),'answers',relative_to=self.root)
        self.exam={'title':'t','sections':[{'id':'A','kind':'reading','paragraphs':[{'id':'A-p1','text':'The museum opens at nine.'}],
            'questions':[{'id':'21','stem':'When does it open?','options':{'A':'Eight.','B':'Nine.'},'answer':'B','answer_status':'official'}]}]}
    def tearDown(self):self.temp.cleanup()
    def ledger(self,paper=None,answers=None):
        return {'sources':[{'role':'paper','kind':'image_pages','path':'paper','sha256':(paper or self.paper)['source_sha256'],'pages':(paper or self.paper)['pages']},
                           {'role':'answers','kind':'image_pages','path':'answers','sha256':(answers or self.answers)['source_sha256'],'pages':(answers or self.answers)['pages']}],
                'sections':[{'id':'A','kind':'reading','paragraphs':self.exam['sections'][0]['paragraphs'],
                             'questions':[{'id':'21','stem':'When does it open?','options':{'A':'Eight.','B':'Nine.'},'answer':'B','answer_status':'official','answer_reference':'answer-1.png 第21题'}]}]}
    def audit(self,ledger,table):
        ledger_path=self.root/'source-ledger.json';ledger_path.write_text(json.dumps(ledger,ensure_ascii=False),encoding='utf-8')
        key_path=None
        if table is not None:
            key_path=self.root/'answers.json';key_path.write_text(json.dumps(table,ensure_ascii=False),encoding='utf-8')
        return audit_exam(self.exam,self.root,str(ledger_path),str(key_path) if key_path else None,None)
    def codes(self,result):return {error['code'] for error in result['errors']}
    def table(self,**extra):
        base={'answer_source':'answer-1.png','answer_source_sha256':self.answers['source_sha256'],'answer_source_kind':'image_transcription','answers':{'21':'B'}}
        base.update(extra);return base
    def test_image_pages_are_verified_and_the_set_passes(self):
        result=self.audit(self.ledger(),self.table())
        self.assertEqual(result['errors'],[],result['errors'])
        self.assertEqual(result['status'],'automated_checks_passed')
    def test_replaced_page_blocks(self):
        png(self.root/'paper'/'page-2.png',60,80,(200,0,0))   # re-shot page after the ledger was written
        result=self.audit(self.ledger(),self.table())
        self.assertIn('source_page_hash',self.codes(result))
    def test_reordered_pages_block(self):
        swapped=dict(self.paper);pages=self.paper['pages']
        swapped['pages']=[{**pages[1],'index':1},{**pages[0],'index':2}]
        result=self.audit(self.ledger(paper=swapped),self.table())
        self.assertIn('source_pages_digest',self.codes(result))
    def test_image_transcribed_answers_are_flagged(self):
        result=self.audit(self.ledger(),self.table())
        self.assertIn('answer_key_image_transcription',{warning['code'] for warning in result['warnings']})
    def test_script_parsed_answers_are_not_flagged(self):
        result=self.audit(self.ledger(),self.table(answer_source_kind='parsed'))
        self.assertNotIn('answer_key_image_transcription',{warning['code'] for warning in result['warnings']})
    def test_answers_cli_binds_the_transcription_to_the_image_set(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'answers').mkdir()
            png(root/'answers'/'a-1.png',40,40,(9,9,9))
            inv=image_pages.inventory([],str(root/'answers'),'answers',relative_to=root)
            (root/'inv.json').write_text(json.dumps(inv,ensure_ascii=False),encoding='utf-8')
            (root/'transcribed.txt').write_text('21 B\n22 C\n',encoding='utf-8')
            out=root/'answers.json'
            result=run('answers.py','extract',root/'transcribed.txt','--source-images',root/'inv.json','--out',out)
            self.assertEqual(result.returncode,0,result.stderr)
            table=json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual(table['answer_source_kind'],'image_transcription')
            self.assertEqual(table['answer_source_sha256'],inv['source_sha256'])
            self.assertEqual(table['answers'],{'21':'B','22':'C'})
            self.assertEqual(table['answer_source_pages'][0]['path'],'answers/a-1.png')
            self.assertIn('逐页读取图片转录',table['note'])
    def test_source_images_requires_a_real_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'not-inventory.json').write_text('{"kind":"something"}',encoding='utf-8')
            (root/'t.txt').write_text('21 B\n',encoding='utf-8')
            result=run('answers.py','extract',root/'t.txt','--source-images',root/'not-inventory.json','--out',root/'a.json')
            self.assertEqual(result.returncode,1)
            self.assertIn('image_pages.py',result.stderr)

class MultiPageOriginTests(unittest.TestCase):
    def test_a_section_can_carry_several_source_pages(self):
        # 图片版试卷常一节跨两页（原文一页、题目一页），必须两页都随课件交付并纳入验收指纹。
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            png(root/'p1.png',40,60,(1,1,1));png(root/'p2.png',40,60,(2,2,2))
            exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
            exam['sections'][0]['origin']={'exam_page':2,'page_images':['p1.png','p2.png'],'publication_status':'未确认原始出版来源'}
            source=root/'exam.json';source.write_text(json.dumps(exam,ensure_ascii=False),encoding='utf-8')
            ledger={'sources':[{'role':'original_demo','path':'exam.json','sha256':hashlib.sha256(source.read_bytes()).hexdigest()}],'sections':exam['sections']}
            ledger_path=root/'source-ledger.json';ledger_path.write_text(json.dumps(ledger,ensure_ascii=False),encoding='utf-8')
            out=root/'out'
            with contextlib.redirect_stdout(io.StringIO()):build.build(source,out,ledger_path)
            written=json.loads((out/'exam.json').read_text(encoding='utf-8'))['sections'][0]['origin']['page_images']
            self.assertEqual(written,['sources/A-paper-1.png','sources/A-paper-2.png'])
            for name in written:self.assertTrue((out/name).is_file(),name)
            verified=verify_output(out)
            self.assertEqual(verified['status'],'passed')
            self.assertEqual(sorted(verified['resource_sha256']),['sources/A-paper-1.png','sources/A-paper-2.png'])
    def test_empty_page_images_is_rejected(self):
        exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
        exam['sections'][0]['origin']={'exam_page':2,'page_images':[],'publication_status':'未确认'}
        with self.assertRaisesRegex(ValueError,'page_images'):
            build.validate(exam)
    def test_page_images_must_be_strings(self):
        exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
        exam['sections'][0]['origin']={'exam_page':2,'page_images':['ok.png',3],'publication_status':'未确认'}
        with self.assertRaisesRegex(ValueError,'page_images'):
            build.validate(exam)
    def test_browser_checker_fingerprints_the_same_media_as_verification(self):
        # verify_output 把 page_images 计入 resource_sha256；浏览器验收若漏掉它们，
        # package_lesson 的 media_sha256 比对会永远失败，多页课件将无法交付。
        source=(ROOT/'scripts/browser_check.cjs').read_text(encoding='utf-8')
        self.assertIn('s.origin?.page_images',source,'browser_check must fingerprint every source page, not just page_image')
    def test_browser_fixture_ships_a_multi_page_section(self):
        # 通用检查在普通课件上必须跳过（否则老师自己的普通课件会验收失败）；
        # "夹具不能空转"这条保证放在这里，由测试守着。
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            made=subprocess.run([sys.executable,str(ROOT/'tests/make_browser_fixture.py'),str(root/'src'),str(root/'out')],
                                capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
            self.assertEqual(made.returncode,0,made.stderr)
            exam=json.loads((root/'out/exam.json').read_text(encoding='utf-8'))
            self.assertTrue(any(len(s.get('origin',{}).get('page_images') or [])>1 for s in exam['sections']),
                            'browser fixture must ship a multi-page section or the UI check is vacuous')

class SpreadPhotos(unittest.TestCase):
    """翻开的书：一张照片并排两页。页清单不能让"1 张=1 页"把漏页与页序核对带偏。"""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 跨页照片 ')
        self.base=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()

    def photo(self,name,width,height,color):
        png(self.base/name,width,height,color)

    def test_spread_photos_report_logical_pages(self):
        self.photo('卷面-01.png',240,160,(10,20,30))
        self.photo('卷面-02.png',240,160,(40,50,60))
        result=image_pages.inventory([],str(self.base),'paper',str(self.base),spread=True)
        self.assertEqual(result['page_count'],2,'page_count 仍是图片张数')
        self.assertEqual(result['layout'],'spread')
        self.assertEqual(result['pages_per_image'],2)
        self.assertEqual(result['logical_pages'],4,'两张跨页照片是四页')
        self.assertTrue(all(page.get('spread') and page['pages_in_image']==2 for page in result['pages']))
        self.assertIn('跨页',result['note'])
        self.assertEqual([p['code'] for p in result['problems']],[])

    def test_mixed_batch_only_marks_listed_files(self):
        self.photo('卷面-01.png',240,160,(10,20,30))
        self.photo('答案-01.png',120,200,(40,50,60))
        result=image_pages.inventory([],str(self.base),'paper',str(self.base),
                                     pages_per_image=2,spread_files=['卷面-01.png'])
        flagged={page['path']:page.get('spread',False) for page in result['pages']}
        self.assertTrue(flagged['卷面-01.png'])
        self.assertFalse(flagged['答案-01.png'])
        self.assertEqual(result['logical_pages'],3)

    def test_portrait_image_marked_as_spread_is_flagged(self):
        self.photo('竖版-01.png',120,200,(40,50,60))
        result=image_pages.inventory([],str(self.base),'paper',str(self.base),spread=True)
        self.assertEqual([p['code'] for p in result['problems']],['spread_not_landscape'])

    def test_pages_without_spread_are_unchanged(self):
        self.photo('卷面-01.png',120,200,(40,50,60))
        result=image_pages.inventory([],str(self.base),'paper',str(self.base))
        self.assertNotIn('layout',result)
        self.assertNotIn('logical_pages',result)
        self.assertFalse(result['pages'][0].get('spread',False))

    def test_build_warns_about_spread_paper_without_blocking(self):
        """跨页原卷要提醒逐页核对，但不能因此阻断构建。"""
        self.photo('卷面-01.png',240,160,(10,20,30))
        inventory=image_pages.inventory([],str(self.base),'paper',str(self.base),spread=True)
        # 台账里的键名是 sha256（image_pages 输出的叫 source_sha256），文档里就是这么写的
        inventory['sha256']=inventory.pop('source_sha256')
        exam=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
        exam['sections'][0]['origin']={'exam_page':2,'page_images':['试卷图片/卷面-01.png'],'publication_status':'未确认原始出版来源'}
        source=self.base/'exam.json';source.write_text(json.dumps(exam,ensure_ascii=False),encoding='utf-8')
        ledger={'sources':[{'role':'original_demo','path':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()},inventory],
                'sections':exam['sections']}
        report=audit_exam(exam,self.base,None,None)
        self.assertEqual(report['status'],'blocked','缺台账时必须拦下（确保这条用例走的是真正的审计路径）')
        (self.base/'source-ledger.json').write_text(json.dumps(ledger,ensure_ascii=False),encoding='utf-8')
        report=audit_exam(exam,self.base,str(self.base/'source-ledger.json'),None)
        self.assertNotEqual(report['status'],'blocked',[e['code'] for e in report['errors']])
        codes=[w['code'] for w in report['warnings']]
        self.assertIn('source_spread_pages',codes,'跨页原卷必须提醒按左右页逐页核对')
