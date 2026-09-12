#!/usr/bin/env python3
"""Local preview with byte ranges, required for precise audio seeking."""
import argparse
import os
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from platform_tools import force_utf8


class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        self.byte_range = None
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        try:
            f = open(path, 'rb')
        except OSError:
            self.send_error(404, 'File not found')
            return None
        size = os.fstat(f.fileno()).st_size
        start, end = 0, size - 1
        header = self.headers.get('Range')
        if header:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', header.strip())
            if not match or not any(match.groups()):
                f.close(); self.send_error(400, 'Invalid range'); return None
            a, b = match.groups()
            if a:
                start = int(a)
                end = min(int(b), size - 1) if b else size - 1
            else:
                start = max(0, size - int(b))
            if start > end or start >= size:
                f.close(); self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0'); self.end_headers(); return None
            self.byte_range = (start, end)
        self.send_response(206 if header else 200)
        self.send_header('Content-Type', self.guess_type(path))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Cache-Control', 'no-cache')
        if header:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        f.seek(start)
        return f

    def copyfile(self, source, outputfile):
        try:
            if self.byte_range is None:
                return super().copyfile(source, outputfile)
            left = self.byte_range[1] - self.byte_range[0] + 1
            while left:
                chunk = source.read(min(65536, left))
                if not chunk:
                    break
                outputfile.write(chunk)
                left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # 浏览器提前断开（暂停音频、切页）属于正常现象，不打印堆栈

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def log_message(self, fmt, *args):
        pass


if __name__ == '__main__':
    force_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument('directory')
    parser.add_argument('--port', type=int, default=8918)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(RangeHandler, directory=os.path.abspath(args.directory)))
    print(f'Preview: http://127.0.0.1:{args.port}/', flush=True)
    print('（只监听本机地址，无需向局域网开放。关闭服务后本机预览链接会失效；下载的 HTML 仍可用浏览器打开。）', flush=True)
    server.serve_forever()
