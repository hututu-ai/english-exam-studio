"""结构闸门的"每条断言都真的被反向用例执行到"守卫（1.0.115，1.0.116 改为子进程）。

起因：用 `trace` 量过之后发现，`build.py` 的 66 条 `assert` 里只有 45 条被执行过——
21 条判据**从未被任何用例触发**，把它们改松不会有测试报警（其中 1 条还是永远走不到的死判据，
已删除）。补齐反向用例后，这里把"零未执行"钉成断言，防止以后再退回去。

**为什么放在子进程里跑**（1.0.116 的教训）：最早这个守卫是在本进程内 `trace` 其它测试模块的。
单独跑没问题，但放进整套测试时会 **SIGSEGV（退出码 139）**：整套跑完后留下的对象
（实测是 preview 用例里一个未关闭的 socket）在 `trace` 生效期间被 GC，触发 CPython 在
"跟踪 + 终结器"交互下的崩溃。现在守卫把测量丢给一个**独立解释器**，父进程只看它的 JSON 结论：
子进程即使崩了也只是这条测试失败（并附上 stderr），不会把整套测试带走。

范围：`TARGETS` 是"用 assert 表达判据"的结构/内容闸门（`build.py`、`grounding.py`、`culture.py`）。
`verify_output.py`/`package_lesson.py`/`qa_report.py` 的判据是显式 `raise`（没有 assert），
由 `tests/test_verify_output_gates.py` 的静态守卫覆盖；`audio.py` 的 15 条 assert 由音频用例覆盖
（那批用例会真的调 ffmpeg，不放进这里每次 trace）。
"""
import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
GATE_MODULES=['tests.test_gates_fire','tests.test_grounding','tests.test_culture']
TARGETS=['build.py','grounding.py','culture.py']

WORKER=r'''
import ast,contextlib,io,json,sys,trace,unittest
from pathlib import Path
root=Path(sys.argv[1])
sys.path.insert(0,str(root/'scripts'));sys.path.insert(0,str(root/'tests'))
import os;os.chdir(root)
modules=json.loads(sys.argv[2]);targets=json.loads(sys.argv[3])
suite=unittest.TestLoader().loadTestsFromNames(modules)
runner=trace.Trace(count=1,trace=0)
result=unittest.TestResult()
with contextlib.redirect_stdout(io.StringIO()):
    runner.runfunc(lambda: suite.run(result))
counts={}
for (path,lineno),hits in runner.counts.items():
    if hits:counts.setdefault(Path(path).name,set()).add(lineno)
unexecuted={}
for name in targets:
    source=(root/'scripts'/name).read_text(encoding='utf-8')
    lines={node.lineno for node in ast.walk(ast.parse(source)) if isinstance(node,ast.Assert)}
    missing=sorted(lines-counts.get(name,set()))
    if missing:unexecuted[name]=missing
json.dump({'unexecuted':unexecuted,'tests_run':result.testsRun,
           'errors':len(result.errors),'failures':len(result.failures)},sys.stdout)
'''


class StructuralGateCoverage(unittest.TestCase):
    _measured=None            # 两个用例共用一次测量（trace 一遍几秒）

    @classmethod
    def measurement(cls):
        if cls._measured is None:
            completed=subprocess.run([sys.executable,'-c',WORKER,str(ROOT),
                                      json.dumps(GATE_MODULES),json.dumps(TARGETS)],
                                     capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600)
            assert completed.returncode==0,f'覆盖测量子进程异常退出（{completed.returncode}）：{(completed.stderr or "")[-400:]}'
            cls._measured=json.loads(completed.stdout)
        return cls._measured

    def test_every_assert_in_the_structural_gates_is_executed(self):
        measured=self.measurement()
        assert measured['tests_run']>0,'反向用例一条都没跑到'
        assert measured['errors']==0 and measured['failures']==0,'反向用例自身有问题，覆盖率不可信'
        self.assertEqual(measured['unexecuted'],{},
                         f"这些断言从未被任何反向用例执行到（判据改松不会有报警）：{measured['unexecuted']}")

    def test_the_measurement_can_see_unexecuted_asserts(self):
        """守卫自身的反向验证：确认测量确实能看见 assert 行号（不是空跑）。"""
        measured=self.measurement()
        self.assertIsInstance(measured['unexecuted'],dict)
        source=(ROOT/'scripts'/'build.py').read_text(encoding='utf-8')
        lines={node.lineno for node in ast.walk(ast.parse(source)) if isinstance(node,ast.Assert)}
        self.assertGreater(len(lines),0,'build.py 里应该有 assert')


if __name__=='__main__':unittest.main()
