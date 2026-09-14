"""Version comparison for the update checker.

The installed version can legitimately be ahead of the published release (development
builds did exactly that), and string equality used to report that as "update available",
i.e. it advised a downgrade.
"""
import contextlib,io,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import check_update
from check_update import version_key
class VersionKeyTests(unittest.TestCase):
    def test_numeric_order_not_lexicographic(self):
        self.assertLess(version_key('1.0.2'),version_key('1.0.10'))
        self.assertLess(version_key('1.0.9'),version_key('1.0.10'))
        self.assertLess(version_key('1.9.0'),version_key('1.10.0'))
    def test_leading_v_and_short_versions(self):
        self.assertEqual(version_key('v1.0.13'),version_key('1.0.13'))
        self.assertEqual(version_key('1.2'),version_key('1.2.0'))
    def test_prerelease_sorts_below_the_plain_release(self):
        self.assertLess(version_key('1.0.15-dev'),version_key('1.0.15'))
        self.assertLess(version_key('1.0.15-rc1'),version_key('1.0.15'))
        self.assertGreater(version_key('1.0.15-dev'),version_key('1.0.14'))
    def test_unknown_text_has_no_key(self):
        self.assertIsNone(version_key('未知（找不到 VERSION，可能不是完整安装包）'))
class CompareTests(unittest.TestCase):
    def test_same_version(self):
        self.assertEqual(check_update.compare('1.0.13','1.0.13'),'up_to_date')
        self.assertEqual(check_update.compare('v1.0.13','1.0.13'),'up_to_date')
    def test_older_installed_offers_update(self):
        self.assertEqual(check_update.compare('1.0.12','1.0.13'),'update_available')
        self.assertEqual(check_update.compare('1.0.2','1.0.10'),'update_available')
        self.assertEqual(check_update.compare('1.0.15-dev','1.0.15'),'update_available')
    def test_newer_installed_never_advises_a_downgrade(self):
        self.assertEqual(check_update.compare('1.0.22','1.0.13'),'newer_than_release')
        self.assertEqual(check_update.compare('1.0.15-dev','1.0.14'),'newer_than_release')
    def test_missing_remote_is_unknown(self):
        self.assertEqual(check_update.compare('1.0.13',None),'unknown')
class CliTests(unittest.TestCase):
    class FakeResponse:
        def __init__(self,payload):self.payload=payload
        def read(self):return json.dumps(self.payload).encode('utf-8')
        def __enter__(self):return self
        def __exit__(self,*args):return False
    def run_main(self,argv,payload=None):
        output=io.StringIO()
        target=patch.object(check_update.urllib.request,'urlopen',return_value=self.FakeResponse(payload)) if payload is not None else contextlib.nullcontext()
        with target,contextlib.redirect_stdout(output),patch.object(sys,'argv',['check_update.py',*argv]):
            code=check_update.main()
        return code,output.getvalue()
    def test_offline_reports_local_version_without_network(self):
        with patch.object(check_update.urllib.request,'urlopen',side_effect=AssertionError('no network expected')):
            code,text=self.run_main(['--offline','--json'])
        payload=json.loads(text)
        self.assertEqual(code,0)
        self.assertEqual(payload['status'],'unknown_remote')
        self.assertTrue(payload['installed_version'])
    def test_newer_install_is_reported_as_no_downgrade(self):
        code,text=self.run_main(['--json'],{'tag_name':'v1.0.13','name':'v1.0.13'})
        payload=json.loads(text)
        self.assertEqual(code,0)
        self.assertEqual(payload['status'],'newer_than_release')
        self.assertIn('无需降级',payload['update_steps'][0])
    def test_outdated_install_offers_the_download(self):
        code,text=self.run_main(['--json'],{'tag_name':'v99.0.0','name':'future'})
        payload=json.loads(text)
        self.assertEqual(code,0)
        self.assertEqual(payload['status'],'update_available')
        self.assertIn('releases/latest/download',payload['update_steps'][0])
    def test_network_failure_falls_back_to_unknown_remote(self):
        output=io.StringIO()
        with patch.object(check_update.urllib.request,'urlopen',side_effect=check_update.urllib.error.URLError('offline')),contextlib.redirect_stdout(output),patch.object(sys,'argv',['check_update.py','--json']):
            code=check_update.main()
        payload=json.loads(output.getvalue())
        self.assertEqual(code,0)
        self.assertEqual(payload['status'],'unknown_remote')
        self.assertIn('URLError',payload['note'])
