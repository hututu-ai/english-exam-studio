"""老师第一次使用的整条路径必须可重放：一条命令跑通并出报告。

这条路径（安装 → 选范围与功能 → 图片材料登记 → 图片答案绑定 → 构建 → 核验 → 浏览器 →
人工复核清单 → 打包）是老师真正会走的；任何一环在发布后断掉，都要在测试里先断。
本测试用 --no-browser 跑（浏览器验收另有真机用例），断言每一步都有明确状态：
**跳过的步骤如实标 skipped，不算通过。**
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class FirstUseRehearsal(unittest.TestCase):
    def test_documented_first_use_path_replays(self):
        with tempfile.TemporaryDirectory(prefix='英语 skill 首次使用 ') as temp:
            base=Path(temp)
            result=subprocess.run([sys.executable,str(ROOT/'scripts/rehearse_first_use.py'),'--no-browser',
                                   '--workdir',str(base/'work'),'--report-dir',str(base/'reports'),'--json'],
                                  capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600)
            report_path=base/'reports'/'first-use-report.json'
            self.assertTrue(report_path.is_file(),result.stdout[-1500:]+result.stderr[-600:])
            report=json.loads(report_path.read_text(encoding='utf-8'))
            self.assertEqual(report['summary']['failed'],0,[s for s in report['steps'] if s['status']=='failed'])
            steps={item['name']:item for item in report['steps']}
            for name in ('1. 安装完整性','2. 老师选范围与功能','3. 图片版试卷登记','4. 图片版答案绑定',
                         '5. 构建','6. 产物核验','8. 人工复核清单','9. 打包'):
                self.assertEqual(steps[name]['status'],'passed',f"{name} 应当可重放：{steps[name]['detail']}")
            self.assertEqual(steps['7. 浏览器验收']['status'],'skipped','--no-browser 时必须如实标 skipped')
            self.assertFalse(report['browser_verified'])
            self.assertIn('不算通过',report['note'])
            self.assertIn('不证明真实试卷内容',report['note'])

if __name__=='__main__':unittest.main()
