"""Windows 清单里写的命令与预期，必须真的就是脚本的行为。

问题①是"Windows 一定要能跑通"。作者手上只有 macOS，真机验收只能等机器；但**清单本身**
完全可以在本机验：只要把 `py -3 scripts\\x.py` 换成本机解释器跑一遍，看输出是不是文档写的那样。

真发生过（1.0.71/1.0.72 这轮）：§7 只说要先跑浏览器验收，实际 `package_lesson.py` 同时要求
`qa-report.md`——老师补完浏览器验收再跑一次，才会撞上第二堵墙。这类"文档漏说一道闸门"的偏差，
下面这些断言就是为了当场抓住。

只跑不需要 Windows 的步骤；`winget`、`where.exe`、Edge 双击这类只做文本检查，不假装执行过。
"""
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build
from verify_output import verify_output

DOC=ROOT/'docs'/'WINDOWS.md'

COMMAND_LINE=re.compile(r'^py -3 (.+)$',re.M)
SCRIPT_REF=re.compile(r'scripts[\\/]([A-Za-z_][A-Za-z0-9_]*\.py)')
FILE_REF=re.compile(r'(?:^|\s)(examples[\\/][^\s"]+)')

def documented_commands(text):
    """取出清单里所有 `py -3 …` 命令，按原样返回（含反斜杠与引号）。"""
    return [match.group(1).strip() for match in COMMAND_LINE.finditer(text)]

def to_local_argv(command):
    """把 Windows 写法翻成本机 argv：`py -3` → 当前解释器，反斜杠 → 正斜杠。"""
    parts=command.replace('\\','/').split()
    if parts and parts[0].startswith('scripts/'):parts[0]=parts[0]
    return [sys.executable]+parts

class ChecklistIsCoherent(unittest.TestCase):
    """不执行的部分：命令指向的脚本与示例文件必须存在。"""

    def setUp(self):self.text=DOC.read_text(encoding='utf-8')

    def test_every_referenced_script_exists(self):
        commands=documented_commands(self.text)
        self.assertGreater(len(commands),3,'清单里的 py -3 命令突然变少，检查是不是被改写丢了')
        for command in commands:
            for name in SCRIPT_REF.findall(command):
                self.assertTrue((ROOT/'scripts'/name).is_file(),
                                f'清单里的命令指向不存在的脚本：scripts/{name}（{command}）')

    def test_every_referenced_example_input_exists(self):
        for match in FILE_REF.finditer(self.text):
            path=ROOT/Path(match.group(1))
            self.assertTrue(path.exists(),f'清单里写要用的示例输入不存在：{match.group(1)}')

    def test_no_posix_only_instructions_inside_code_blocks(self):
        """老师是 Windows 用户：**可复制的命令块**里不该出现 .sh、sudo、chmod、/tmp。

        只查代码块：正文里"本 Skill 不要求运行 .sh"这类说明是应有的提醒，不算违规。
        """
        blocks=re.findall(r'```[A-Za-z]*\n(.*?)```',self.text,re.S)
        self.assertGreater(len(blocks),5,'清单里的命令块突然变少，检查是不是被改写丢了')
        for block in blocks:
            for needle in ('.sh','sudo','chmod','/tmp/'):
                self.assertNotIn(needle,block,f'可复制执行的命令块里不该出现 {needle}：\n{block.strip()[:200]}')

class ChecklistMatchesReality(unittest.TestCase):
    """执行的部分：文档写的预期输出必须与真实运行一致。"""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='英语 skill Windows 清单 ')
        self.out=Path(self.temp.name)/'demo'

    def tearDown(self):self.temp.cleanup()

    def run_script(self,script,*args,expect=0):
        result=subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,args)],
                              capture_output=True,text=True,encoding='utf-8',errors='replace',cwd=str(ROOT))
        self.assertEqual(result.returncode,expect,
                         f'scripts/{script} {" ".join(map(str,args))} 退出码 {result.returncode}（预期 {expect}）：'
                         f'{(result.stderr or result.stdout)[-400:]}')
        return result

    def test_documented_build_produces_the_files_the_checklist_promises(self):
        """§5 写"应看到 index.html、打开课件.html、exam.json、build-report.json、answer-audit.json"。"""
        self.run_script('build.py','--demo','examples/demo-exam.json',self.out,
                        '--source-ledger','examples/source-ledger.json')
        for name in ('index.html','打开课件.html','exam.json','build-report.json','answer-audit.json'):
            self.assertTrue((self.out/name).is_file(),f'§5 承诺能看到 {name}，实际没有')
        result=self.run_script('verify_output.py',self.out)
        self.assertEqual(json.loads(result.stdout)['status'],'passed','§5 承诺 verify_output 是 passed')

    def test_packaging_refuses_then_explains_both_gates(self):
        """§7：没有当期浏览器验收与人工复核清单时必须拦，而且要把两道闸门都说出来。"""
        self.run_script('build.py','--demo','examples/demo-exam.json',self.out,
                        '--source-ledger','examples/source-ledger.json')
        refused=self.run_script('package_lesson.py',self.out,Path(self.temp.name)/'demo.zip',expect=1)
        message=(refused.stderr or '')+(refused.stdout or '')
        self.assertIn('浏览器点击验收',message,'拒绝原因必须提到浏览器验收')
        self.assertIn('qa-report',message,'拒绝原因必须同时提到人工复核清单（老师补完第一道才不会撞第二堵墙）')
        allowed=self.run_script('package_lesson.py',self.out,Path(self.temp.name)/'demo.zip','--allow-unchecked')
        report=json.loads(allowed.stdout)
        self.assertEqual(report['status'],'preview_only_browser_check_pending',
                         '§7 承诺 --allow-unchecked 得到"待浏览器操作验收版"')
        self.assertNotEqual(report['status'],'browser_checked','待验收版不得被写成通过')

    def test_quality_report_flow_matches_the_checklist(self):
        """§9 第 7 步：init 生成条目 → check 必须先拒空结论 → 填完返回 ok。"""
        import qa_report
        self.run_script('build.py','--demo','examples/demo-exam.json',self.out,
                        '--source-ledger','examples/source-ledger.json')
        self.run_script('qa_report.py','init',self.out)
        report_file=self.out/'qa-report.md'
        self.assertTrue(report_file.is_file(),'init 必须生成 qa-report.md')
        self.run_script('qa_report.py','check',self.out,expect=1)
        text=re.sub(r'—— 结论：$','—— 结论：单元测试夹具已按文档逐条写下实际判断。',
                    report_file.read_text(encoding='utf-8'),flags=re.M)
        report_file.write_text(text,encoding='utf-8')
        result=self.run_script('qa_report.py','check',self.out)
        self.assertEqual(json.loads(result.stdout)['status'],'ok','填完结论后 check 必须返回 ok')

if __name__=='__main__':unittest.main()
