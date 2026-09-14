"""`preview.py` 是老师"证据重听跳到某一秒"的本地服务，此前**一个测试都没有**。

`SKILL.md` 承诺："本地HTTP预览用 `scripts/preview.py OUTPUT_DIRECTORY --port 8918`，支持音频
Range 请求；普通不支持 Range 的服务器可能导致证据重听从头播放"。Range 的边界很容易写错
（后缀 `bytes=-500`、开区间 `bytes=500-`、越界、目录、路径穿越），所以这里把承诺逐条钉住。
"""
import http.client
import os
import sys
import tempfile
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import preview

AUDIO=bytes(range(256))*40          # 10240 字节的"音频"，内容可预测
PAGE=b'<!doctype html><title>lesson</title>'

class PreviewRange(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='英语 skill 预览 ')
        cls.root=Path(cls.temp.name)
        (cls.root/'audio').mkdir()
        (cls.root/'audio'/'L1.mp3').write_bytes(AUDIO)
        (cls.root/'index.html').write_bytes(PAGE)
        handler=partial(preview.RangeHandler,directory=str(cls.root))
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.port=cls.server.server_address[1]
        cls.addClassCleanup(cls.temp.cleanup)

    def tearDown(self):
        pass

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close()

    def get(self,path,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        try:
            connection.request('GET',path,headers=headers or {})
            response=connection.getresponse()
            body=response.read()
            return response.status,dict(response.getheaders()),body
        finally:connection.close()

    def test_full_request_is_200_with_range_support_advertised(self):
        status,headers,body=self.get('/audio/L1.mp3')
        self.assertEqual(status,200)
        self.assertEqual(headers.get('Accept-Ranges'),'bytes','浏览器要靠这个才知道能做精确跳转')
        self.assertEqual(int(headers['Content-Length']),len(AUDIO))
        self.assertEqual(body,AUDIO)
        self.assertTrue(headers.get('Content-Type','').startswith('audio/'),headers.get('Content-Type'))

    def test_byte_range_returns_206_with_the_exact_slice(self):
        status,headers,body=self.get('/audio/L1.mp3',{'Range':'bytes=10-19'})
        self.assertEqual(status,206)
        self.assertEqual(headers.get('Content-Range'),f'bytes 10-19/{len(AUDIO)}')
        self.assertEqual(int(headers['Content-Length']),10)
        self.assertEqual(body,AUDIO[10:20])

    def test_suffix_range_is_the_last_n_bytes(self):
        status,headers,body=self.get('/audio/L1.mp3',{'Range':'bytes=-10'})
        self.assertEqual(status,206)
        self.assertEqual(headers.get('Content-Range'),f'bytes {len(AUDIO)-10}-{len(AUDIO)-1}/{len(AUDIO)}')
        self.assertEqual(body,AUDIO[-10:])

    def test_open_ended_range_goes_to_the_end(self):
        status,headers,body=self.get('/audio/L1.mp3',{'Range':'bytes=100-'})
        self.assertEqual(status,206)
        self.assertEqual(body,AUDIO[100:])
        self.assertEqual(headers.get('Content-Range'),f'bytes 100-{len(AUDIO)-1}/{len(AUDIO)}')

    def test_range_end_beyond_size_is_clamped(self):
        status,headers,body=self.get('/audio/L1.mp3',{'Range':f'bytes=0-{len(AUDIO)+999}'})
        self.assertEqual(status,206)
        self.assertEqual(headers.get('Content-Range'),f'bytes 0-{len(AUDIO)-1}/{len(AUDIO)}')
        self.assertEqual(body,AUDIO)

    def test_range_start_beyond_size_is_416_with_total_size(self):
        status,headers,body=self.get('/audio/L1.mp3',{'Range':f'bytes={len(AUDIO)+1}-{len(AUDIO)+5}'})
        self.assertEqual(status,416,'越界要如实拒绝，不能悄悄返回整段（否则"跳到某秒"会从头播）')
        self.assertEqual(headers.get('Content-Range'),f'bytes */{len(AUDIO)}')

    def test_reversed_range_is_rejected(self):
        status,_,_=self.get('/audio/L1.mp3',{'Range':'bytes=50-10'})
        self.assertEqual(status,416)

    def test_legal_but_unparsable_ranges_are_ignored_not_refused(self):
        """多段 Range / 未知单位 / 乱写的值：按 RFC 7233 "MAY ignore" 忽略后返回 200 整段。

        以前这些一律 400——会让这类播放器**完全放不出声音**（老师按证据重听时会以为音频坏了），
        而整段返回只是多传一点数据。
        """
        for header in ('bytes=0-99,200-299','items=0-10','bytes=abc-def','bytes=--'):
            with self.subTest(header=header):
                status,headers,body=self.get('/audio/L1.mp3',{'Range':header})
                self.assertEqual(status,200,f'{header} 应当被忽略并返回整段')
                self.assertEqual(body,AUDIO)
                self.assertEqual(headers.get('Accept-Ranges'),'bytes')
                self.assertEqual(int(headers['Content-Length']),len(AUDIO))

    def test_html_is_served_as_html(self):
        status,headers,body=self.get('/index.html')
        self.assertEqual(status,200)
        self.assertTrue(headers.get('Content-Type','').startswith('text/html'))
        self.assertEqual(body,PAGE)

    def test_directory_request_does_not_crash(self):
        status,_,body=self.get('/audio/')
        self.assertIn(status,(200,301,302,404),'目录请求要么列目录要么重定向，不能 500')
        self.assertNotIn(b'Traceback',body)

    def test_path_traversal_is_not_served(self):
        for path in ('/../../../../etc/passwd','/..%2f..%2fetc%2fpasswd','/audio/../../../etc/passwd'):
            status,_,body=self.get(path)
            self.assertNotEqual(status,200,f'{path} 不该被本机服务读出来')
            self.assertNotIn(b'root:',body)

    def test_missing_file_is_404(self):
        status,_,_=self.get('/audio/nope.mp3')
        self.assertEqual(status,404)

if __name__=='__main__':unittest.main()
