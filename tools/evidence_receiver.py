"""Local-only receiver for browser captures: POST raw PNG bytes to /save?name=<file>.png.

Writes only into planning/evidence/<subdir> (default vfx-sample-v1); rejects path tricks. Bind is 127.0.0.1.
python tools/evidence_receiver.py [--port 5181] [--subdir vfx-sample-v1]
"""
from __future__ import annotations

import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
PORT = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 5181
SUBDIR = sys.argv[sys.argv.index('--subdir') + 1] if '--subdir' in sys.argv else 'vfx-sample-v1'
OUT = ROOT / 'planning' / 'evidence' / SUBDIR
NAME = re.compile(r'^[A-Za-z0-9._-]{1,120}\.(png|json|txt)$')


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        query = parse_qs(urlparse(self.path).query)
        name = (query.get('name') or [''])[0]
        if urlparse(self.path).path != '/save' or not NAME.match(name):
            self.send_response(400)
            self.end_headers()
            return
        length = int(self.headers.get('Content-Length', '0'))
        if length <= 0 or length > 64 * 1024 * 1024:
            self.send_response(413)
            self.end_headers()
            return
        OUT.mkdir(parents=True, exist_ok=True)
        target = OUT / name
        target.write_bytes(self.rfile.read(length))
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(str(target).encode('utf-8'))

    def log_message(self, fmt, *args):
        sys.stdout.write('RECEIVER ' + (fmt % args) + '\n')
        sys.stdout.flush()


if __name__ == '__main__':
    print(f'RECEIVER writing to {OUT} on 127.0.0.1:{PORT}', flush=True)
    HTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
