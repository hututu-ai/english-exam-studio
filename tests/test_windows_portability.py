"""Windows 上跑不跑得起来，不能等 CI 报红才知道（问题①的静态闸门）。

1.0.116 推上线后，Windows 格（windows-latest）跑自带测试红了，两处根因都是"开发机是 macOS，
代码里悄悄依赖了 POSIX"：

1. 测试里写了个 `#!/bin/sh` 的假 ffprobe，再 `chmod` 加上执行位——Windows 没有 /bin/sh；
2. 一条断言读 `st_mode & 0o100` 判断"解压后保留执行位"——Windows 没有 POSIX 执行位。

这两种写法在 macOS 上都是绿的：本机跑一万遍测试也发现不了，只有 CI 的 Windows 格会红，
而 CI 一次要几分钟、还得推上去。所以这里用 AST 静态扫**随发布包发给老师的每一个 .py**：

* 用了 POSIX 专有的进程/权限接口（`os.fork`/`os.killpg`/`os.setsid`/`os.geteuid`/`signal.SIGKILL`，
  或 `import pwd/grp/fcntl/termios/tty`），
* 或者依赖文件系统的执行位（`chmod` 置执行位、`st_mode` 取执行位、`stat.S_IEXEC` 之类），

同一个函数里就必须有 `os.name` / `sys.platform` 判断，或者 `skipTest`/`skipIf`/`skipUnless` 跳过。
没有就是"本机测不出、Windows 上必炸"，本机直接失败——这比等 CI 便宜得多。

规则只认 AST 节点，不认注释和字符串：`tests/test_whisper_setup.py` 造 tar 夹具时写的
`0o755` 是**打包元数据**（测的是"解压是否保留执行位"），不是给谁 chmod，所以不该误报。

本文件自己必须写下这些坏名字（那是它的规则表），所以扫描时排除自己；排除项写在 SKIP_FILES
并写明原因，另有测试钉住"排除的文件必须真的存在"，免得改名后整份清单变成空转。
"""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import package_skill

# 扫自己等于规则表把自己判违规：它必须提到 os.fork、signal.SIGKILL 这些名字。
SKIP_FILES = {
    'tests/test_windows_portability.py': '本文件是规则表本身，必须写下这些坏名字',
}

POSIX_ATTRS = {
    ('os', 'fork'): 'os.fork 是 POSIX 专有',
    ('os', 'forkpty'): 'os.forkpty 是 POSIX 专有',
    ('os', 'setsid'): 'os.setsid 是 POSIX 专有',
    ('os', 'killpg'): 'os.killpg 是 POSIX 专有',
    ('os', 'geteuid'): 'os.geteuid 是 POSIX 专有',
    ('os', 'getegid'): 'os.getegid 是 POSIX 专有',
    ('os', 'setuid'): 'os.setuid 是 POSIX 专有',
    ('os', 'setgid'): 'os.setgid 是 POSIX 专有',
    ('os', 'chown'): 'os.chown 是 POSIX 专有',
    ('os', 'chroot'): 'os.chroot 是 POSIX 专有',
    ('signal', 'SIGKILL'): 'Windows 上没有 signal.SIGKILL',
    ('signal', 'SIGHUP'): 'Windows 上没有 signal.SIGHUP',
    ('signal', 'SIGUSR1'): 'Windows 上没有 signal.SIGUSR1',
    ('signal', 'SIGUSR2'): 'Windows 上没有 signal.SIGUSR2',
}
POSIX_MODULES = {
    'pwd': 'pwd 模块只在 POSIX 上存在',
    'grp': 'grp 模块只在 POSIX 上存在',
    'fcntl': 'fcntl 模块只在 POSIX 上存在',
    'termios': 'termios 模块只在 POSIX 上存在',
    'tty': 'tty 模块只在 POSIX 上存在',
}
EXEC_STAT = {'S_IEXEC', 'S_IXUSR', 'S_IXGRP', 'S_IXOTH'}
EXEC_BITS = 0o111
# 会拉起外部进程的入口：它们的参数里出现 POSIX shell 就是 Windows 上必炸的写法。
SPAWNERS = {'Popen', 'run', 'call', 'check_call', 'check_output', 'system', 'spawnv', 'spawnl', 'execv', 'execvp'}
POSIX_SHELLS = {'sh', 'bash', 'dash', 'zsh', 'ksh', '/bin/sh', '/bin/bash', '/usr/bin/sh', '/usr/bin/bash'}
GUARDS = ('os.name', 'sys.platform', 'skipTest', 'skipIf', 'skipUnless')


def _ints(node):
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)]


def _exec_mode(node):
    """调用里出现的模式值是否带执行位（0o100/0o010/0o001 任一）。"""
    return any(isinstance(value, int) and value & EXEC_BITS for value in _ints(node))


def _texts(node):
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _called_name(node):
    """被调用的名字：`subprocess.run(...)` 取 run，`from subprocess import Popen` 后 `Popen(...)` 取 Popen。"""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _posix_shell(command):
    """命令里有没有"只有 POSIX 才有的 shell"：显式调 sh/bash，或直接跑一个 .sh。"""
    for text in _texts(command):
        stripped = text.strip()
        tokens = stripped.replace('"', ' ').replace("'", ' ').split()
        if not tokens:
            continue
        if tokens[0] in POSIX_SHELLS or stripped.endswith('.sh'):
            return stripped[:40]
    return None


class WindowsPortabilityScan:
    """把一个 Python 文件扫一遍，返回 [(行号, 规则代号, 说明)]。"""

    RULES = ('POSIX_API', 'EXEC_BIT', 'POSIX_SHELL')

    def __init__(self):
        self.problems = []

    def report(self, node, code, why):
        self.problems.append((getattr(node, 'lineno', 0), code, why))

    def has_guard(self, source, fn):
        segment = ast.get_source_segment(source, fn) or ''
        return any(token in segment for token in GUARDS)

    def check_function(self, source, fn, where):
        if self.has_guard(source, fn):
            return
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                why = POSIX_ATTRS.get((node.value.id, node.attr))
                if why:
                    self.report(node, 'POSIX_API', f'{where} 用了 {node.value.id}.{node.attr}（{why}），但没有 os.name / sys.platform 判断或 skipTest 跳过')
            if isinstance(node, ast.Attribute) and node.attr in EXEC_STAT:
                self.report(node, 'EXEC_BIT', f'{where} 用了 stat.{node.attr}（执行位是 POSIX 概念），但没有 os.name / sys.platform 判断或 skipTest 跳过')
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'chmod' and _exec_mode(node):
                self.report(node, 'EXEC_BIT', f'{where} 用 chmod 置了执行位（Windows 只认只读标记），但没有 os.name / sys.platform 判断或 skipTest 跳过')
            if isinstance(node, ast.Call) and _called_name(node) in SPAWNERS:
                shell = _posix_shell(node)
                if shell:
                    self.report(node, 'POSIX_SHELL', f'{where} 调用了 {shell}（Windows 上没有它），但没有 os.name / sys.platform 判断或 skipTest 跳过')
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitAnd) and 'st_mode' in ast.dump(node) and _exec_mode(node):
                self.report(node, 'EXEC_BIT', f'{where} 从 st_mode 里取执行位（Windows 没有这个概念），但没有 os.name / sys.platform 判断或 skipTest 跳过')

    def check(self, path):
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.check_function(source, fn, f'{path.name}:{fn.name}()')
        # 模块级也要查：import pwd 这种一进文件就崩的写法不属于任何函数。
        module_level = ast.Module(body=[n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))], type_ignores=[])
        for node in ast.walk(module_level):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split('.')[0] in POSIX_MODULES:
                        self.report(node, 'POSIX_API', f'{path.name} 顶层 import {alias.name}（{POSIX_MODULES[alias.name.split(".")[0]]}）')
            if isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0] in POSIX_MODULES:
                self.report(node, 'POSIX_API', f'{path.name} 顶层 from {node.module} import（{POSIX_MODULES[node.module.split(".")[0]]}）')
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                why = POSIX_ATTRS.get((node.value.id, node.attr))
                if why:
                    self.report(node, 'POSIX_API', f'{path.name} 顶层用了 {node.value.id}.{node.attr}（{why}）')
        return self.problems


def scan(root=ROOT):
    problems = []
    for path in package_skill.shipped_files(root):
        if path.suffix != '.py':
            continue
        relative = path.relative_to(Path(root).resolve()).as_posix()
        if relative in SKIP_FILES:
            continue
        for lineno, code, why in WindowsPortabilityScan().check(path):
            problems.append(f'{relative}:{lineno}: [{code}] {why}')
    return problems


class ShippedCodeRunsOnWindows(unittest.TestCase):
    def scanner(self, text, name='sample.py'):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / name
            path.write_text(text, encoding='utf-8')
            return WindowsPortabilityScan().check(path)

    def test_scan_covers_the_whole_shipped_package(self):
        """扫得是不是同一批文件：范围缩了就等于闸门空转。"""
        shipped = package_skill.shipped_files(ROOT)
        py = [p.relative_to(ROOT).as_posix() for p in shipped if p.suffix == '.py']
        self.assertGreaterEqual(len(py), 40, '随包发布的 Python 文件应有几十个，少了说明 scanner/打包口径漂了')
        self.assertTrue(any(name.startswith('scripts/') for name in py), '必须扫生产脚本')
        self.assertTrue(any(name.startswith('tests/') for name in py), '必须扫随包发布的测试（老师会跑它们）')

    def test_skip_list_only_names_files_that_exist(self):
        for relative, reason in SKIP_FILES.items():
            self.assertTrue((ROOT / relative).is_file(), f'排除项 {relative} 指向不存在的文件（改名后这里会静默空转）：{reason}')

    def test_no_unguarded_posix_dependency_in_the_package(self):
        problems = scan()
        self.assertEqual([], problems, '随包发布的代码里出现了"本机是 macOS 测不出、Windows 上会炸"的写法：\n' + '\n'.join(problems))

    def test_reverse_unguarded_killpg_is_caught(self):
        found = self.scanner('import os, signal\ndef stop(p):\n    os.killpg(p.pid, signal.SIGKILL)\n')
        self.assertTrue(any(code == 'POSIX_API' for _, code, _ in found), '不判 guard 的 os.killpg/signal.SIGKILL 必须被抓到')

    def test_reverse_guarded_killpg_passes(self):
        found = self.scanner('import os, signal\ndef stop(p):\n    if os.name == "nt":\n        return\n    os.killpg(p.pid, signal.SIGKILL)\n')
        self.assertEqual([], found, '有 os.name 分流就不该报')

    def test_reverse_unguarded_exec_bit_chmod_is_caught(self):
        found = self.scanner('from pathlib import Path\ndef make(p):\n    Path(p).chmod(0o755)\n')
        self.assertTrue(any(code == 'EXEC_BIT' for _, code, _ in found), '不判 guard 的 chmod 置执行位必须被抓到')

    def test_reverse_guarded_exec_bit_chmod_passes(self):
        found = self.scanner('import os\nfrom pathlib import Path\ndef make(p):\n    if os.name != "nt":\n        Path(p).chmod(0o700)\n')
        self.assertEqual([], found, '显式认了 Windows 就不该报')

    def test_reverse_unguarded_st_mode_exec_assertion_is_caught(self):
        found = self.scanner('def check(binary):\n    assert binary.stat().st_mode & 0o100\n')
        self.assertTrue(any(code == 'EXEC_BIT' for _, code, _ in found), 'st_mode 取执行位的断言必须被抓到')

    def test_reverse_st_mode_assertion_with_skiptest_passes(self):
        found = self.scanner('import os\ndef check(self, binary):\n    if os.name == "nt":\n        self.skipTest("Windows 没有可执行位概念，执行位断言跳过")\n    self.assertTrue(binary.stat().st_mode & 0o100)\n')
        self.assertEqual([], found, '如实跳过的写法不该报')

    def test_reverse_plain_read_only_chmod_passes(self):
        """0o444 是只读（Windows 认这个），不带执行位，不该报。"""
        found = self.scanner('import os\nfrom pathlib import Path\ndef lock(p):\n    os.chmod(p, 0o444)\n    Path(p).chmod(0o644)\n')
        self.assertEqual([], found, '只读标记 Windows 是认的，不能误报')

    def test_reverse_tar_metadata_mode_is_not_a_chmod(self):
        """夹具里的 0o755 是打包元数据，不是给文件 chmod——这条防的是规则写太糙。"""
        found = self.scanner('import tarfile, io\ndef add(t, name, mode=0o755):\n    info = tarfile.TarInfo(name)\n    info.mode = mode\n    t.addfile(info, io.BytesIO(b"#!/bin/sh\\n"))\n')
        self.assertEqual([], found, 'tar 成员元数据与字符串内容不是执行位依赖，不该误报')

    def test_guard_must_be_in_the_same_function(self):
        """A 函数里有 guard 不代表 B 函数安全：否则"随便哪里写一句 os.name"就能骗过闸门。"""
        found = self.scanner('import os\nfrom pathlib import Path\ndef safe():\n    return os.name == "nt"\ndef unsafe(p):\n    Path(p).chmod(0o755)\n')
        self.assertTrue(any(code == 'EXEC_BIT' for _, code, _ in found), 'guard 必须与坏写法在同一个函数里')

    def test_top_level_posix_import_is_caught(self):
        found = self.scanner('import pwd\nimport grp\n')
        self.assertEqual(2, len([1 for _, code, _ in found if code == 'POSIX_API']), '顶层 import pwd/grp 会让 Windows 一进文件就崩')

    def test_reverse_unguarded_posix_shell_call_is_caught(self):
        found = self.scanner('import subprocess\ndef probe(stub):\n    return subprocess.run(["/bin/sh", stub], capture_output=True)\n')
        self.assertTrue(any(code == 'POSIX_SHELL' for _, code, _ in found), '调 /bin/sh 必须被抓到')
        found = self.scanner('import subprocess\ndef probe():\n    return subprocess.Popen(["./helper.sh"])\n')
        self.assertTrue(any(code == 'POSIX_SHELL' for _, code, _ in found), '直接跑 .sh 也必须被抓到')
        found = self.scanner('from subprocess import Popen\ndef probe():\n    return Popen("bash -c true", shell=True)\n')
        self.assertTrue(any(code == 'POSIX_SHELL' for _, code, _ in found), 'from subprocess import Popen 这种写法不能漏')
        found = self.scanner('import os\ndef probe():\n    os.system("chmod +x helper.sh")\n')
        self.assertTrue(any(code == 'POSIX_SHELL' for _, code, _ in found), '命令字符串里直接跑 .sh 也要抓')

    def test_reverse_guarded_posix_shell_call_passes(self):
        found = self.scanner('import os, subprocess\ndef probe(stub):\n    if os.name == "nt":\n        return None\n    return subprocess.run(["/bin/sh", stub])\n')
        self.assertEqual([], found, '有 os.name 分流就不该报')

    def test_reverse_sh_needles_outside_spawn_calls_are_not_flagged(self):
        """文档一致性检查里把 '.sh' 当"不该出现的字符串"来搜，那不是调用 shell。"""
        found = self.scanner('import unittest\ndef check(self, text):\n    for needle in (".sh", "sudo", "chmod"):\n        self.assertNotIn(needle, text)\n')
        self.assertEqual([], found, '搜索用的字符串不等于调用 shell，不能误报')

    def test_every_rule_code_is_referenced_by_a_reverse_test(self):
        """规则代号必须被某条反向用例真的断到：只在规则表里列一遍等于没验证过。"""
        here = Path(__file__).read_text(encoding='utf-8')
        for code in WindowsPortabilityScan.RULES:
            self.assertIn(f"code == '{code}'", here, f'规则 {code} 没有反向用例断言它（加规则必须同时加会咬的测试）')
        for _, why in POSIX_ATTRS.items():
            self.assertTrue(why, '每条 POSIX 规则都要写清为什么')
        for _, why in POSIX_MODULES.items():
            self.assertTrue(why, '每条模块规则都要写清为什么')


if __name__ == '__main__':
    unittest.main()
