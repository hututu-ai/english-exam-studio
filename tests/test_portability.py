"""Windows portability guards.

The developer built this skill on macOS; teachers run it on Windows. These tests
lock in the invariants that keep that safe: no shell execution, explicit UTF-8 on
all text I/O, an encoding whenever a subprocess runs in text mode, POSIX-only
calls gated behind os.name, and Chinese output surviving a cp1252 console.
"""
import json,os,re,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'scripts'
sys.path.insert(0,str(SCRIPTS))
def call_arguments(text,open_index):
    """Return the argument text of a call, balancing nested parentheses."""
    depth=0;chars=[]
    for char in text[open_index:]:
        if char=='(':depth+=1
        elif char==')':
            depth-=1
            if depth==0:break
        if depth>=1:chars.append(char)
    return ''.join(chars)
class PortabilityTests(unittest.TestCase):
    def sources(self):
        for path in sorted(SCRIPTS.glob('*.py')):
            yield path,path.read_text(encoding='utf-8')
    def test_no_shell_execution(self):
        for path,text in self.sources():
            self.assertNotIn('shell=True',text,f'{path.name}: shell=True is not Windows-safe')
            self.assertIsNone(re.search(r'\bos\.(system|popen)\(',text),f'{path.name}: use subprocess with an explicit argument list')
    def test_text_file_io_is_explicitly_utf8(self):
        for path,text in self.sources():
            for match in re.finditer(r'\.(read_text|write_text)\(',text):
                arguments=call_arguments(text,match.end()-1)
                self.assertIn('encoding=',arguments,f'{path.name}: {match.group(0)} must declare encoding')
    def test_subprocess_text_mode_declares_encoding(self):
        for path,text in self.sources():
            for match in re.finditer(r'subprocess\.(Popen|run|check_output|check_call)\(',text):
                arguments=call_arguments(text,match.end()-1)
                if re.search(r'text\s*=\s*True',arguments):
                    self.assertIn('encoding=',arguments,f'{path.name}: text=True subprocess must declare encoding')
    def test_entry_points_force_utf8_output(self):
        for path,text in self.sources():
            if '__main__' not in text:continue
            self.assertTrue('force_utf8()' in text or 'reconfigure(' in text,
                            f'{path.name}: CLI entry point must force UTF-8 output for the Windows console')
    def test_posix_only_calls_are_gated_for_windows(self):
        text=(SCRIPTS/'bounded_command.py').read_text(encoding='utf-8')
        self.assertIn('os.killpg',text)
        self.assertIn("os.name!='nt'",text)
        self.assertIn("os.name=='nt'",text)
        self.assertIn('taskkill',text)
    def test_windows_executable_suffix_is_applied(self):
        text=(SCRIPTS/'platform_tools.py').read_text(encoding='utf-8')
        self.assertIn("'.exe' if IS_WINDOWS",text)
        self.assertIn("IS_WINDOWS=os.name=='nt'",text)
    def test_chinese_output_survives_a_cp1252_console(self):
        # Exit code depends on install integrity (0 complete / 1 incomplete); what matters
        # here is that Chinese report text never raises UnicodeEncodeError on a cp1252 console.
        environment={**os.environ,'PYTHONIOENCODING':'cp1252'}
        result=subprocess.run([sys.executable,str(SCRIPTS/'check_install.py')],
                              capture_output=True,env=environment,timeout=60)
        self.assertIn(result.returncode,(0,1))
        self.assertNotIn(b'UnicodeEncodeError',result.stderr)
        self.assertNotIn(b'Traceback',result.stderr)
        report=json.loads(result.stdout.decode('utf-8','replace'))
        self.assertIn(report['status'],('complete','incomplete_install'))
    def test_hashes_use_raw_bytes_not_normalized_text(self):
        # Windows write_text emits CRLF and read_text normalizes it away, so hashing text
        # would disagree with browser_check.cjs / package_lesson.py, which hash raw bytes.
        for path,text in self.sources():
            self.assertIsNone(re.search(r'sha256\([^)]*read_text',text),
                              f'{path.name}: hash file bytes, not newline-normalized text')

class WindowsConsoleAndFailureMessages(unittest.TestCase):
    """中文 Windows 的控制台是 cp936——这是老师最可能遇到的环境，也是当年崩过的那个。

    顺带守住"报错必须中文且能照着改"：路径写错时抛英文 errno（`[Errno 2] No such file or
    directory: '.../index.html'`）等于让老师和助手一起猜——`verify_output.py`、`package_lesson.py`、
    `quotes.py`、`answers.py` 都真实出现过。
    """

    ENCODINGS=('cp936','cp1252','gbk')

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill 控制台 ')
        self.base=Path(self.temp.name)

    def tearDown(self):self.temp.cleanup()

    def run_cli(self,encoding,*argv):
        environment={**os.environ,'PYTHONIOENCODING':encoding}
        result=subprocess.run([sys.executable,str(SCRIPTS/argv[0]),*map(str,argv[1:])],
                              capture_output=True,env=environment,cwd=str(ROOT),timeout=120)
        return result

    def test_success_paths_print_chinese_under_cp936(self):
        cases=(('check_install.py',),('doctor.py','--minutes','1'),('plan.py','menu'),
               ('cost.py','examples/demo-reading.json'),('host_probe.py','--json'))
        for encoding in self.ENCODINGS:
            for argv in cases:
                with self.subTest(encoding=encoding,argv=argv):
                    result=self.run_cli(encoding,*argv)
                    combined=result.stdout+result.stderr
                    self.assertNotIn(b'UnicodeEncodeError',combined,f'{argv[0]} 在 {encoding} 控制台上崩了')
                    self.assertNotIn(b'Traceback',combined,f'{argv[0]} 在 {encoding} 控制台上抛了堆栈')
                    self.assertRegex(result.stdout.decode('utf-8'),r'[\u4e00-\u9fff]',
                                     f'{argv[0]} 的中文输出必须是 UTF-8（控制台编码 {encoding} 也不能变成乱码）')

    def test_missing_path_failures_explain_in_chinese(self):
        """路径写错时必须是中文、带路径与下一步；英文 errno 与裸堆栈都不合格。"""
        missing=self.base/'并不存在的目录'
        cases=(('verify_output.py',missing),
               ('package_lesson.py',missing,self.base/'x.zip'),
               ('quotes.py','check',self.base/'nope.json'),
               ('answers.py','extract',self.base/'nope.txt','--out',self.base/'a.json'),
               ('answers.py','check',self.base/'nope.json','--ledger',self.base/'l.json'),
               ('build.py',self.base/'nope.json',self.base/'out','--source-ledger',self.base/'l.json'),
               ('plan.py','check',self.base/'nope.json'),
               ('read_acceptance.py',self.base/'nope.json'),
               ('parts.py','check',self.base/'nope-dir'),
               ('image_pages.py','--dir',missing,'--role','paper','--out',self.base/'i.json'))
        for encoding in self.ENCODINGS:
            for argv in cases:
                with self.subTest(encoding=encoding,argv=argv):
                    result=self.run_cli(encoding,*argv)
                    combined=(result.stdout+result.stderr)
                    text=combined.decode('utf-8','replace')
                    self.assertIn(result.returncode,(0,1,2),f'{argv[0]} 退出码异常：{result.returncode}')
                    self.assertNotIn(b'Traceback',combined,f'{argv[0]} 抛了堆栈：{text[-200:]}')
                    self.assertNotIn(b'UnicodeEncodeError',combined,argv[0])
                    self.assertNotIn('[Errno',text,f'{argv[0]} 把英文 errno 直接甩给了老师：{text.strip()[:160]}')
                    self.assertNotIn('No such file',text,f'{argv[0]} 的报错仍是英文：{text.strip()[:160]}')
                    self.assertRegex(text,r'[\u4e00-\u9fff]',f'{argv[0]} 的报错必须中文：{text.strip()[:160]}')

    def test_wrong_file_type_explains_in_chinese_instead_of_a_traceback(self):
        """把计划/台账当成 exam.json 传进来：必须中文说明，不能漏英文堆栈。

        `exam.json`、`generation-plan.json` 常常同目录，助手看错参数是很常见的失手；
        以前 quotes/cost/scope/answer_audit 会抛 AttributeError / TypeError 裸堆栈。
        """
        wrong=ROOT/'examples/teaching-plan.json'
        self.assertTrue(wrong.is_file(),'这条用例依赖仓库里的计划示例')
        cases=(('quotes.py','check',wrong),('cost.py',wrong),('scope.py',wrong),('answer_audit.py',wrong),
               ('audio.py','cut',self.base/'并不存在的音频.mp3','--manifest',wrong,'--out',self.base/'o'))
        for encoding in self.ENCODINGS:
            for argv in cases:
                with self.subTest(encoding=encoding,argv=argv):
                    result=self.run_cli(encoding,*argv)
                    combined=result.stdout+result.stderr
                    text=combined.decode('utf-8','replace')
                    self.assertEqual(result.returncode,1,f'{argv[0]} 应以 1 退出：{text[-200:]}')
                    self.assertNotIn(b'Traceback',combined,f'{argv[0]} 漏了英文堆栈：{text[-200:]}')
                    self.assertNotIn('AttributeError',text,f'{argv[0]} 漏了 AttributeError：{text[-160:]}')
                    self.assertNotIn('TypeError',text,f'{argv[0]} 漏了 TypeError：{text[-160:]}')
                    self.assertRegex(text,r'[\u4e00-\u9fff]',f'{argv[0]} 的报错必须中文：{text[-160:]}')
                    if argv[0]=='audio.py':
                        self.assertIn('切片清单',text,f'{argv[0]} 应说明该给的是切片清单：{text[-160:]}')
                    else:
                        self.assertIn('exam.json',text,f'{argv[0]} 的报错应说明该给什么文件：{text[-160:]}')
                        self.assertIn('generation-plan.json',text,f'{argv[0]} 应点名可能的混淆文件：{text[-160:]}')

    def test_explain_error_keeps_existing_chinese_messages(self):
        """已经是中文的说明不要被再包一层，免得读起来像机器翻译。"""
        from platform_tools import explain_error
        self.assertEqual(explain_error(ValueError('章节 A 的挖空下标无效')),'章节 A 的挖空下标无效')
        self.assertIn('找不到文件或目录',explain_error(FileNotFoundError(2,'No such file','/x/index.html')))
        self.assertIn('/x/index.html',explain_error(FileNotFoundError(2,'No such file','/x/index.html')))
        self.assertIn('没有权限读写',explain_error(PermissionError(13,'Permission denied','/x')))
        self.assertIn('处理时出错',explain_error(RuntimeError('boom')))
        self.assertIn('（先跑 build.py）',explain_error(ValueError('x'),'先跑 build.py'))
