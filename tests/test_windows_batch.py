"""Windows 上"零命令行"收材料包的那条路，必须真的能双击就跑。

老师里有一部分不会/不愿开终端；`docs/WINDOWS.md` 一条命令再简单，也要求他们会复制粘贴。
`一键体检.bat` 是给他们的入口：双击 → 跑 `smoke_report.py --zip` → 把报告 zip 发回。
批处理有两个真实坑，这个文件用测试钉住：**必须是 CRLF**（LF 的 .bat 在 cmd 里会报错），
**中文要先 `chcp 65001`**（否则 cp936 控制台下乱码）。
"""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import package_skill

BATCH=ROOT/'一键体检.bat'

class WindowsOneClickBatch(unittest.TestCase):
    def setUp(self):
        self.assertTrue(BATCH.is_file(),'Windows 老师需要这个双击入口：一键体检.bat')
        self.raw=BATCH.read_bytes()
        self.text=self.raw.decode('utf-8')

    def test_uses_crlf_and_utf8_without_bom(self):
        self.assertIn(b'\r\n',self.raw)
        self.assertNotIn(b'\n',self.raw.replace(b'\r\n',b''),'不能有裸 LF 行尾')
        self.assertFalse(self.raw.startswith(b'\xef\xbb\xbf'),'带 BOM 时 cmd 会把第一行当命令名报错')
        for number,line in enumerate(self.text.split('\n'),1):
            if line and not line.endswith('\r'):
                self.fail(f'第 {number} 行缺少 CRLF：{line[:40]!r}')

    def test_switches_codepage_before_printing_chinese(self):
        first_lines=[line.strip() for line in self.text.split('\r\n')[:5]]
        self.assertEqual(first_lines[0],'@echo off')
        self.assertLess(first_lines.index('chcp 65001 >nul'),5,'中文输出前必须切到 UTF-8 代码页')
        self.assertIn('chcp 65001',self.text)

    def test_runs_the_documented_command_and_pauses(self):
        self.assertIn('scripts\\smoke_report.py --zip',self.text,'必须跑文档里那条体检命令')
        self.assertIn('where py',self.text,'没有 py 启动器时要退回 python')
        self.assertIn('pause',self.text,'跑完要停住，老师才看得到路径')
        self.assertIn('%~dp0',self.text,'必须切到脚本所在目录，双击时的工作目录并不确定')

    def test_refuses_to_run_outside_the_skill_folder(self):
        self.assertIn('SKILL.md',self.text,'不在技能包根目录时要给出中文提示并退出')

    def test_has_no_posix_only_constructs(self):
        for needle in ('#!/','chmod','sudo','/tmp/','$(',)  :
            self.assertNotIn(needle,self.text,f'Windows 批处理里不该出现 {needle}')

    def test_batch_is_shipped_inside_the_release_zip(self):
        names=[p.name for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink()
               and not any(x.startswith('.') or x in ('dist','work','__pycache__') for x in p.relative_to(ROOT).parts)
               and p.suffix not in ('.pyc','.zip') and p.name not in ('install-manifest.json','SHA256SUMS.txt')]
        self.assertIn('一键体检.bat',names,'它必须随发布包一起发给老师，否则等于没有')

    def test_referenced_script_exists(self):
        self.assertTrue((ROOT/'scripts'/'smoke_report.py').is_file())

if __name__=='__main__':unittest.main()
