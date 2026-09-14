"""The one-command real-machine acceptance report.

It must always produce a complete, honest report: every step present, failures
recorded rather than raised, and skipped steps named. The browser step is skipped
here so the test needs no Node/Playwright.
"""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class SmokeReportTests(unittest.TestCase):
    def test_report_covers_every_step_and_is_valid(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result=subprocess.run([sys.executable,str(ROOT/'scripts/smoke_report.py'),'--no-browser',
                                   '--workdir',str(root/'work'),'--report-dir',str(root)],
                                  capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
            self.assertEqual(result.returncode,0,result.stderr[-800:])
            report=json.loads((root/'smoke-report.json').read_text(encoding='utf-8'))
            self.assertEqual(len(report['steps']),7)
            self.assertEqual(report['summary']['failed'],0,report['steps'])
            self.assertEqual(report['summary']['skipped'],1)
            statuses={step['name']:step['status'] for step in report['steps']}
            for name in ('1. 运行环境','2. 安装完整性','3. 宿主能力','4. 示例构建','5. 模板与产物核验','7. 打包交付'):
                self.assertEqual(statuses[name],'passed',name)
            self.assertEqual(statuses['6. 浏览器点击验收'],'skipped')
            self.assertTrue((root/'smoke-report.md').read_text(encoding='utf-8').startswith('# 实机体检报告'))
            self.assertTrue((root/'work-delivery.zip').exists())
