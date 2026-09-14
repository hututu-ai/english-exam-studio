"""Exercise the Windows-only code branches without a Windows machine.

These paths are the ones a macOS-only development cycle never runs: `.exe` tool
lookup under LOCALAPPDATA, the Windows runtime root, and the taskkill-based
timeout branch for bounded dependency commands.
"""
import os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import bounded_command,platform_tools
class WindowsBranchTests(unittest.TestCase):
    def test_find_tool_appends_exe_under_localappdata(self):
        with tempfile.TemporaryDirectory() as temp:
            binary=Path(temp)/'english-exam-studio'/'tools'/'bin'/'ffmpeg.exe'
            binary.parent.mkdir(parents=True);binary.write_bytes(b'stub')
            environ={k:v for k,v in os.environ.items() if k not in ('FFMPEG_BIN','ENGLISH_EXAM_TOOLS')}
            environ['LOCALAPPDATA']=temp
            with patch.object(platform_tools,'IS_WINDOWS',True),patch.dict(os.environ,environ,clear=True),patch('shutil.which',return_value=None):
                self.assertEqual(platform_tools.find_tool('ffmpeg'),str(binary.resolve()))
    def test_runtime_root_uses_localappdata_on_windows(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(platform_tools,'IS_WINDOWS',True),patch.dict(os.environ,{'LOCALAPPDATA':temp},clear=True):
                self.assertEqual(platform_tools.runtime_root(),Path(temp)/'english-exam-studio')
    def test_bounded_command_uses_a_process_group_on_windows(self):
        captured={}
        class FakeProcess:
            pid=101;returncode=0
            def __init__(self,*args,**kwargs):captured.update(kwargs)
            def communicate(self,timeout=None):return 'out','err'
        environ=dict(os.environ)
        with patch.object(bounded_command.os,'name','nt'),patch.object(bounded_command.subprocess,'CREATE_NEW_PROCESS_GROUP',512,create=True),patch.object(bounded_command.subprocess,'Popen',FakeProcess),patch.object(bounded_command.subprocess,'run',side_effect=AssertionError('no taskkill expected')):
            code,out,err=bounded_command.run(['stub'],5)
        self.assertEqual((code,out,err),(0,'out','err'))
        self.assertIn('creationflags',captured)
        self.assertNotIn('start_new_session',captured)
    def test_bounded_command_kills_the_tree_with_taskkill_on_timeout(self):
        calls=[]
        class HangingProcess:
            pid=202;returncode=124
            def __init__(self,*args,**kwargs):pass
            def communicate(self,timeout=None):
                if not calls:raise subprocess.TimeoutExpired('stub',timeout)
                return '',''
        def fake_run(command,**kwargs):calls.append(command);return subprocess.CompletedProcess(command,0,'','')
        with patch.object(bounded_command.os,'name','nt'),patch.object(bounded_command.subprocess,'CREATE_NEW_PROCESS_GROUP',512,create=True),patch.object(bounded_command.subprocess,'Popen',HangingProcess),patch.object(bounded_command.subprocess,'run',side_effect=fake_run):
            code,out,err=bounded_command.run(['stub'],1)
        self.assertEqual(code,124)
        self.assertEqual(calls[0][:2],['taskkill','/PID'])
        self.assertIn('/T',calls[0]);self.assertIn('/F',calls[0])
        self.assertIn('已终止',err)
