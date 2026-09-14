"""文档一致性必须由机器守住：否则"照着文档做"会在发布后才撞墙。

二十多轮改动里，真实发生过：命令改名、字段新增、README 测试数量与实际差 37 项、
文档提到不存在的参数。这些都不该靠人记得改——`scripts/check_docs.py` 每次发布前跑，
这里再把它接进测试套件，让漂移直接失败。
"""
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import check_docs

class StatusLabelChecks(unittest.TestCase):
    """标着版本号的「当前状态」小节必须跟 VERSION 一致（1.0.108）。

    真实发生过：ROADMAP 的「当前状态（按目标逐条对照，1.0.70）」在版本走到 1.0.107 之后
    还挂着 1.0.70，读者会以为那些结论是七十多版之前下的。
    """
    def tree(self,version,roadmap):
        base=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,base,ignore_errors=True)
        (base/'docs').mkdir();(base/'references').mkdir();(base/'scripts').mkdir();(base/'assets').mkdir()
        (base/'VERSION').write_text(version+'\n',encoding='utf-8')
        (base/'SKILL.md').write_text('# skill\n',encoding='utf-8')
        (base/'README.md').write_text('# readme\n',encoding='utf-8')
        (base/'assets'/'lesson.html').write_text(':root{--size:17px}\n',encoding='utf-8')
        (base/'docs'/'ROADMAP.md').write_text(roadmap,encoding='utf-8')
        return base
    def test_repository_status_section_follows_the_version(self):
        self.assertEqual(check_docs.status_label_problems(ROOT),[])
    def test_a_stale_status_label_is_reported(self):
        base=self.tree('1.0.107','## 当前状态（按目标逐条对照，1.0.70）\n')
        problems=check_docs.status_label_problems(base)
        self.assertTrue(any('1.0.70' in item and '1.0.107' in item for item in problems),problems)
    def test_a_matching_label_passes(self):
        base=self.tree('1.0.107','## 当前状态（按目标逐条对照，1.0.107）\n')
        self.assertEqual(check_docs.status_label_problems(base),[])
    def test_version_log_titles_are_not_status_claims(self):
        """`docs/VERIFICATION.md` 的「# 1.0.108 …当前状态…」是那一版的记录标题，不是现役状态声明。"""
        base=self.tree('1.0.109','# 1.0.108 顶部「当前状态」表挂着旧版本号（历史记录标题）\n')
        self.assertEqual(check_docs.status_label_problems(base),[])
        base2=self.tree('1.0.109','## 当前状态（按目标逐条对照，1.0.108）\n')
        self.assertTrue(check_docs.status_label_problems(base2),'现役状态小节仍必须跟版本走')

    def test_a_status_heading_without_a_version_is_fine(self):
        base=self.tree('1.0.107','## 当前状态\n')
        self.assertEqual(check_docs.status_label_problems(base),[])

class CommandPrefixChecks(unittest.TestCase):
    """文档里给老师照抄的命令必须写 `python3`（1.0.107）。

    实测：macOS 上 `python` 常常不存在（本机 `command -v python` 为空），
    照抄 `python scripts/xxx.py` 直接 command not found，白跑一轮。
    """
    def tree(self,docs):
        base=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,base,ignore_errors=True)
        (base/'references').mkdir();(base/'docs').mkdir();(base/'scripts').mkdir();(base/'assets').mkdir()
        (base/'SKILL.md').write_text('# skill\n',encoding='utf-8')
        (base/'README.md').write_text('# readme\n',encoding='utf-8')
        (base/'assets'/'lesson.html').write_text(':root{--size:17px}\n',encoding='utf-8')
        for name,text in docs.items():(base/name).write_text(text,encoding='utf-8')
        return base
    def test_repository_commands_use_python3(self):
        self.assertEqual(check_docs.command_prefix_problems(ROOT),[])
    def test_bare_python_in_a_reference_is_reported(self):
        base=self.tree({'references/guide.md':'python scripts/build.py a b\n'})
        problems=check_docs.command_prefix_problems(base)
        self.assertTrue(any('python3 scripts' in item for item in problems),problems)
    def test_python3_commands_pass(self):
        base=self.tree({'references/guide.md':'python3 scripts/build.py a b\n'})
        self.assertEqual(check_docs.command_prefix_problems(base),[])
    def test_historical_records_and_windows_doc_are_exempt(self):
        base=self.tree({'docs/VERIFICATION.md':'python scripts/smoke_report.py --no-browser\n',
                        'docs/WINDOWS.md':'python -m unittest discover -s tests\n'})
        self.assertEqual(check_docs.command_prefix_problems(base),[])
        self.assertEqual(check_docs.BARE_PYTHON_OK,{'docs/VERIFICATION.md','docs/WINDOWS.md'})

class ProseFlagChecks(unittest.TestCase):
    """散文里提到的参数必须真有脚本认得（1.0.106）。

    原有检查只覆盖"同一行里写了 scripts/xxx.py"的参数；速度、省额度那几页常常在散文里直接写
    `--profile quick` 这类用法。打错或参数被删时，助手照抄就会撞 argparse 报错、白跑一轮。
    """
    def tree(self,docs,scripts=None):
        base=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,base,ignore_errors=True)
        (base/'references').mkdir();(base/'docs').mkdir();(base/'scripts').mkdir()
        (base/'assets').mkdir()
        (base/'SKILL.md').write_text('# skill\n',encoding='utf-8')
        (base/'README.md').write_text('# readme\n',encoding='utf-8')
        (base/'assets'/'lesson.html').write_text(':root{--size:17px;--accent:#111}\n',encoding='utf-8')
        for name,text in docs.items():(base/name).write_text(text,encoding='utf-8')
        for name,text in (scripts or {}).items():(base/'scripts'/name).write_text(text,encoding='utf-8')
        return base
    def test_repository_prose_flags_all_exist(self):
        self.assertEqual(check_docs.orphan_flag_problems(ROOT),[])
    def test_node_script_flags_count_as_known(self):
        self.assertIn('--stress',check_docs.cli_flags(ROOT),'browser_check.cjs 的参数也要算脚本认得的')
    def test_css_variables_defined_in_the_template_are_not_flags(self):
        css=check_docs.css_variables(ROOT)
        self.assertIn('--size',css)
        self.assertEqual(check_docs.doc_flag_mentions('字号控件只改 `--size`，另有 var(--accent)。',css),set())
    def test_an_unknown_prose_flag_is_reported(self):
        base=self.tree({'references/guide.md':'用 `--profiles quick` 先交付。'},
                       {'build.py':'import argparse\np=argparse.ArgumentParser()\np.add_argument("--profile")\n'})
        problems=check_docs.orphan_flag_problems(base)
        self.assertTrue(any('--profiles' in item for item in problems),problems)
    def test_a_known_prose_flag_passes(self):
        base=self.tree({'references/guide.md':'用 `--profile quick` 先交付。'},
                       {'build.py':'import argparse\np=argparse.ArgumentParser()\np.add_argument("--profile")\n'})
        self.assertEqual(check_docs.orphan_flag_problems(base),[])
    def test_a_css_variable_mention_does_not_fail(self):
        base=self.tree({'references/guide.md':'字号控件只改 `--size`。'})
        self.assertEqual(check_docs.orphan_flag_problems(base),[])

class ReadingCostClaims(unittest.TestCase):
    """harness.md 的"读多少"读数与它引用的标记，必须与文件实际状态一致（1.0.105）。

    省额度就靠这张表。真发生过：写着"两份加起来约 60KB"（实际 73KB）、"本页约 5KB"
    （实际 8KB），还引用了 SKILL.md 里已被改写过的字面标记。
    """
    def tree(self,transform=None):
        """用**真实**的 SKILL.md / schema.md / harness.md 建一棵树，只对 harness 做一次改写。

        读数检查就是拿真实字节数比对，所以必须用真实文件：自己写一份合成 harness，
        它自身的体积（"本页约 8KB"）就先对不上，测不出真正要测的东西。
        """
        base=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,base,ignore_errors=True)
        (base/'references').mkdir()
        (base/'SKILL.md').write_bytes((ROOT/'SKILL.md').read_bytes())
        (base/'references'/'schema.md').write_bytes((ROOT/'references'/'schema.md').read_bytes())
        harness=(ROOT/'references'/'harness.md').read_text(encoding='utf-8')
        (base/'references'/'harness.md').write_text(transform(harness) if transform else harness,encoding='utf-8')
        return base
    def test_repository_reading_cost_claims_match_the_files(self):
        self.assertEqual(check_docs.reading_cost_problems(ROOT),[])
        harness=(ROOT/'references/harness.md').read_text(encoding='utf-8')
        for phrase in ('只做听力（范围 A）','写教学内容（整卷）','全部文档（不应发生）'):
            self.assertIn(phrase,harness,f'省额度表缺少"{phrase}"这一行')
    def test_a_stale_size_claim_is_caught(self):
        base=self.tree(lambda text:text.replace('两份加起来约 73KB','两份加起来约 60KB').replace('本页（约 8KB）','本页（约 5KB）'))
        problems=check_docs.reading_cost_problems(base)
        self.assertTrue(any('两份大文档合计' in item and '60KB' in item for item in problems),problems)
        self.assertTrue(any('本页' in item and '5KB' in item for item in problems),problems)
    def test_a_missing_size_claim_is_caught(self):
        base=self.tree(lambda text:text.replace('两份加起来约 73KB','两份加起来'))
        self.assertTrue(any('找不到' in item for item in check_docs.reading_cost_problems(base)))
    def test_a_renamed_marker_is_caught(self):
        base=self.tree(lambda text:text.replace('「只在本次有听力时读这一节」','「只在本次有数学时读这一节」'))
        self.assertTrue(any('找不到的标记' in item for item in check_docs.reading_cost_problems(base)))
    def test_the_documented_numbers_are_not_flagged(self):
        self.assertEqual([item for item in check_docs.reading_cost_problems(self.tree()) if '差超过' in item],[])

class DocConsistency(unittest.TestCase):
    def test_repository_docs_are_consistent(self):
        report=check_docs.check()
        self.assertEqual(report['problems'],[],'文档与代码/版本/测试数量必须一致：\n'+'\n'.join(report['problems']))

    def test_version_appears_in_three_places(self):
        version=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
        manifest=json.loads((ROOT/'assets'/'template-manifest.json').read_text(encoding='utf-8'))
        readme=(ROOT/'README.md').read_text(encoding='utf-8')
        self.assertEqual(manifest['template_version'],version)
        self.assertIn(f'## {version}：',readme)
        self.assertEqual(re.findall(r'^## (\d+\.\d+\.\d+)：',readme,re.M)[0],version,
                         'README 最新一节必须是当前版本（新版本写在新章节里）')

    def test_every_script_is_reachable_from_docs_or_explicitly_internal(self):
        text=check_docs.doc_text()
        missing=[name for name in check_docs.script_names()
                 if name not in text and name not in check_docs.INTERNAL]
        self.assertEqual(missing,[],f'这些脚本既没写进文档也没登记为内部工具：{missing}')

    def test_references_have_no_orphans(self):
        skill=(ROOT/'SKILL.md').read_text(encoding='utf-8')
        readme=(ROOT/'README.md').read_text(encoding='utf-8')
        orphans=[path.name for path in sorted((ROOT/'references').glob('*.md'))
                 if path.name not in skill and path.name not in readme]
        self.assertEqual(orphans,[],f'references 里的孤儿文档（老师看不到）：{orphans}')

class CheckerBehaviour(unittest.TestCase):
    """反向验证：检查器真的抓得住漂移，而不是永远返回 ok。"""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 文档检查 ')
        self.base=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()

    def test_flags_are_attributed_to_the_nearest_script_on_the_line(self):
        """同一行两个脚本时，参数要算到它前面最近的那个脚本上（避免误报）。"""
        scripts=ROOT/'scripts'
        line='先用 scripts/image_pages.py 登记，再用 scripts/answers.py extract --source-images 绑定'
        marks=[(match.start(),match.group(1)) for match in check_docs.SCRIPT_MENTION.finditer(line)]
        flag=check_docs.FLAG_MENTION.search(line)
        owner=[name for position,name in marks if position<flag.start()][-1]
        self.assertEqual(owner,'answers.py')
        self.assertIn('--source-images',check_docs.argparse_options(scripts/'answers.py'))

    def test_a_wrong_flag_is_reported(self):
        fake=self.base/'scripts';fake.mkdir()
        (fake/'demo.py').write_text('import argparse\np=argparse.ArgumentParser()\np.add_argument("--real")\n',encoding='utf-8')
        options=check_docs.argparse_options(fake/'demo.py')
        self.assertIn('--real',options)
        self.assertNotIn('--imaginary',options)

    def test_parser_options_include_choices(self):
        options=check_docs.argparse_options(ROOT/'scripts'/'scope.py')
        self.assertIn('--mode',options)

if __name__=='__main__':unittest.main()


class CrossDocumentChecks(unittest.TestCase):
    """跨文档校对：功能清单、产物清单、安装判断标准。三条都必须真的抓得住。"""

    def test_feature_list_must_match_the_authoritative_menu(self):
        features=check_docs.canonical_features()
        good=[(index,label) for index,(label,_) in enumerate(features,1)]
        self.assertEqual(check_docs.feature_list_problems('doc',good,features),[])
        wrong_name=[(1,'批注'),(2,'查单词')]+[(index,label) for index,(label,_) in enumerate(features[2:],3)]
        problems=check_docs.feature_list_problems('doc',wrong_name,features)
        self.assertTrue(problems, '功能名不一致必须被抓出')
        self.assertIn('查词',problems[0])
        wrong_order=[(1,'查词'),(2,'批注')]+[(index,label) for index,(label,_) in enumerate(features[2:],3)]
        self.assertTrue(check_docs.feature_list_problems('doc',wrong_order,features),'顺序不一致必须被抓出')
        partial=[(1,'批注'),(2,'查词')]
        self.assertEqual(check_docs.feature_list_problems('doc',partial,features),[],
                         '只引用前两项不算清单，不该误报')

    def test_install_docs_must_state_the_complete_criterion(self):
        problems=check_docs.install_claim_problems([('docs/X.md','先跑 check_install.py')])
        self.assertTrue(problems,'只说 check_install 不说 complete 必须被抓出')
        self.assertIn('complete',problems[0])
        self.assertEqual(check_docs.install_claim_problems([('docs/X.md','跑 check_install.py 到 complete 才算装上')]),[])

    def test_deliverable_names_only_reads_real_deliverable_blocks(self):
        text='```text\n本次试卷讲评/\n├── index.html  课件\n├── exam.json   数据\n└── qa-report.md\n```\n'
        self.assertEqual(check_docs.deliverable_names(text),{'index.html','exam.json','qa-report.md'})
        other='```json\n{"path":"schema.md","exam":"exam.json"}\n```\n'   # 没有 index.html 的块不算产物清单
        self.assertEqual(check_docs.deliverable_names(other),set(),'示例代码块不该被当成产物清单')
        mixed='```text\n├── index.html\n├── schema.md\n├── FAQ.md\n```\n'
        self.assertEqual(check_docs.deliverable_names(mixed),{'index.html'},'仓库文档名不属于交付物')

    def test_duplicate_numbered_sections_are_flagged(self):
        """真发生过：WINDOWS.md 顶部插了"## 0. 一条命令"后，原来的"## 0. 打开正确的目录"还在。"""
        good='## 0. 准备\n### 1.1 子节\n## 1. 正式步骤\n## 1.0.69：版本小节\n'
        self.assertEqual(check_docs.numbered_section_problems('doc',good),[],
                         '版本号与子小节不算重复编号，不能误报')
        bad='## 0. 一条命令跑完\n## 0. 打开正确的目录\n## 1. Python\n'
        problems=check_docs.numbered_section_problems('docs/WINDOWS.md',bad)
        self.assertEqual(len(problems),1,'同号小节必须被抓出')
        self.assertIn('## 0.',problems[0])

    def test_declared_test_count_reads_both_phrasings(self):
        """只认一种写法时，README 换个说法这条检查就静默失效——必须两种都认，读不到才算没写。"""
        self.assertEqual(check_docs.declared_test_count('测试总数 **260** 与 README 一致'),260)
        self.assertEqual(check_docs.declared_test_count('**262 项测试通过**（1 项如实跳过）'),262)
        self.assertIsNone(check_docs.declared_test_count('这一版只改文档，没有动代码'))

    def test_harness_steps_must_be_numbered_without_gaps(self):
        """主流程是助手照着做的一串步骤：漏号/重号会直接让人跳步。"""
        good=''.join(f'### 第 {n} 步 做第{n}件事\n\n' for n in range(1,5))
        self.assertEqual(check_docs.step_sequence_problems('references/harness.md',good),[])
        gapped='### 第 1 步 甲\n\n### 第 3 步 乙\n\n### 第 4 步 丙\n\n'
        problems=check_docs.step_sequence_problems('references/harness.md',gapped)
        self.assertTrue(problems,'漏号必须被抓出')
        self.assertIn('1、3、4',problems[0])
        duplicated='### 第 1 步 甲\n\n### 第 2 步 乙\n\n### 第 2 步 丙\n\n'
        self.assertTrue(check_docs.step_sequence_problems('references/harness.md',duplicated),'重号必须被抓出')
        short='### 第 2 步 只有一个\n'
        self.assertEqual(check_docs.step_sequence_problems('docs/X.md',short),[],
                         '只有一两个步骤的文档不算主流程，不该误报')

    def test_agent_manifest_lists_the_canonical_feature_menu_in_order(self):
        """`agents/openai.yaml` 的默认提示词是宿主给老师看的第一句话，功能名与顺序必须与 plan.py 一致。

        没有 PyYAML 依赖：这个文件是简单的 `key: "value"`，只把 default_prompt 那一行取出来即可。
        """
        import plan
        manifest=(ROOT/'agents'/'openai.yaml').read_text(encoding='utf-8')
        line=next((row for row in manifest.splitlines() if row.strip().startswith('default_prompt:')),None)
        self.assertIsNotNone(line,'agents/openai.yaml 必须给出 default_prompt')
        labels=[label for _,label,_ in plan.FEATURES]
        positions=[line.find(label) for label in labels]
        self.assertNotIn(-1,positions,f'default_prompt 少了功能：{[label for label,pos in zip(labels,positions) if pos<0]}')
        self.assertEqual(positions,sorted(positions),'default_prompt 里功能顺序必须与 plan.py 菜单一致')

    def test_broken_relative_links_are_flagged(self):
        """文档改名或写错一个字母，读者就停在 404；本地相对链接必须真实存在。"""
        with tempfile.TemporaryDirectory(prefix='英语 skill 断链 ') as temp:
            root=Path(temp);(root/'docs').mkdir();(root/'references').mkdir()
            (root/'docs'/'ok.md').write_text('见 [规范](../references/spec.md) 与 [外部](https://example.org/x.md) 与 [锚点](#x)\n',encoding='utf-8')
            (root/'references'/'spec.md').write_text('# 规范\n',encoding='utf-8')
            (root/'README.md').write_text('链接正常\n',encoding='utf-8')
            (root/'SKILL.md').write_text('链接正常\n',encoding='utf-8')
            saved=check_docs.ROOT
            try:
                check_docs.ROOT=root
                self.assertEqual(check_docs.broken_link_problems(root),[],'正常链接与外部链接不该误报')
                (root/'docs'/'ok.md').write_text('见 [规范](../references/missing.md)\n',encoding='utf-8')
                problems=check_docs.broken_link_problems(root)
                self.assertEqual(len(problems),1,'断链必须被抓出')
                self.assertIn('missing.md',problems[0])
            finally:
                check_docs.ROOT=saved

    def test_install_path_order_must_match_the_probe(self):
        """老师最依赖"先试哪条"：文档里的安装路径必须写全、且顺序与 host_probe 一致。"""
        order=['teacher_uploaded_zip','raw_files_fetch','cdn_jsdelivr','git_clone']
        good=[('doc','① 让老师把 ZIP 当附件上传 → ② 抓 raw.githubusercontent.com → ③ 打不开就走 jsdelivr → ④ 最后才是 git clone')]
        self.assertEqual(check_docs.install_path_doc_problems(good,order),[])
        preamble=[('doc','沙箱常拦 git clone 的 TLS。① 让老师把 ZIP 当附件上传 → ② 抓 raw.githubusercontent.com → ③ jsdelivr → ④ 最后才是 git clone')]
        self.assertEqual(check_docs.install_path_doc_problems(preamble,order),[],
                         '正文里"沙箱常拦 git clone"是背景说明，不该算成推荐顺序')
        missing=[('doc','① 附件上传 → ② raw.githubusercontent.com → ③ git clone')]
        problems=check_docs.install_path_doc_problems(missing,order)
        self.assertTrue(problems,'少写一条安装路径必须被抓出')
        self.assertIn('jsdelivr',problems[0])
        wrong=[('doc','① 先 git clone → ② 附件上传 → ③ raw.githubusercontent.com → ④ jsdelivr')]
        self.assertTrue(check_docs.install_path_doc_problems(wrong,order),'顺序写反必须被抓出')

    def test_feature_list_detection_needs_consecutive_numbers(self):
        """中文里"共 4 处问题（…）"这类句子不该被当成功能清单，否则正常文档会被误报。"""
        with tempfile.TemporaryDirectory(prefix='英语 skill 清单识别 ') as temp:
            root=Path(temp)
            (root/'README.md').write_text('这次是 4 处问题（不是功能清单）\n还有 7 个文件（也不是）\n',encoding='utf-8')
            (root/'SKILL.md').write_text('# x\n',encoding='utf-8')
            saved=check_docs.ROOT
            try:
                check_docs.ROOT=root
                self.assertEqual(check_docs.doc_feature_lists(),[],'编号不连续的句子不算功能清单')
                (root/'README.md').write_text('1. 批注（x）\n2. 查词（y）\n3. 速对答案（z）\n',encoding='utf-8')
                found=check_docs.doc_feature_lists()
                self.assertEqual(len(found),1,'从 1 开始的连续清单要被抓到')
                self.assertEqual([number for number,_ in found[0][1]],[1,2,3])
            finally:
                check_docs.ROOT=saved

    def test_skippable_sections_stay_marked_with_their_condition(self):
        """SKILL.md 里"什么时候可以不读"的标记必须存在、贴在节标题下、并且写明条件。

        省额度靠的是助手知道"哪些可以不读"；标记被文档重构弄丢，这条就静默失效了。
        """
        lines=(ROOT/'SKILL.md').read_text(encoding='utf-8').splitlines()
        marked=[index for index,line in enumerate(lines) if line.startswith('>') and '跳过' in line]
        self.assertGreaterEqual(len(marked),8,f'应当有若干节被标为可跳过，实际 {len(marked)} 处')
        for index in marked:
            self.assertTrue(any(lines[position].startswith('#') for position in range(max(0,index-3),index)),
                            f'第 {index+1} 行的跳过标记必须紧跟在节标题下面')
            condition=lines[index]
            self.assertTrue(any(word in condition for word in ('模板行为说明','听力','交付或答疑')),
                            f'跳过标记必须写明条件：{condition[:40]}')
        harness=(ROOT/'references'/'harness.md').read_text(encoding='utf-8')
        self.assertIn('模板行为说明',harness,'harness 的读法表要指向模板行为标记')
        self.assertIn('只在本次有听力时读',harness,'harness 的读法表要指向听力条件标记')

    def test_repository_cross_document_consistency(self):
        report=check_docs.check()
        self.assertEqual(report['problems'],[],'\n'.join(report['problems']))

    def test_leftover_release_report_at_package_root_is_flagged(self):
        """真发生过：脚本把报告改写到 dist/ 后，旧报告留在根目录被打进了发布包（版本号还是旧的）。"""
        with tempfile.TemporaryDirectory(prefix='英语 skill 残留报告 ') as temp:
            clean=Path(temp)
            self.assertEqual(check_docs.stale_report_problems(clean),[],'干净的包不该被误报')
            (clean/'release-check.md').write_text('# 发布验收报告 · 1.0.9\n通过 3 / 失败 2\n',encoding='utf-8')
            problems=check_docs.stale_report_problems(clean)
            self.assertTrue(problems,'根目录残留旧验收报告必须被抓出（它会进出现在发给老师的 ZIP 里）')
            self.assertIn('release-check.md',problems[0])
            (clean/'release-check.json').write_text('{"version":"1.0.9"}\n',encoding='utf-8')
            self.assertEqual(len(check_docs.stale_report_problems(clean)),2,'json 与 md 都要报')

    def test_packaging_skips_root_release_report_residue(self):
        """打包层同样不能把它发出去：即使文档检查还没跑，ZIP 里也不该有旧报告。"""
        import package_skill
        self.assertEqual(package_skill.ROOT_REPORT_RESIDUE,check_docs.ROOT_REPORT_RESIDUE,
                         '打包排除清单与文档检查必须同源，避免一处改了另一处漏改')
        self.assertIn('release-check.md',package_skill.ROOT_REPORT_RESIDUE)
