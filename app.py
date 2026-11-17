import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'.deps'))
import base64
import io
import json
import mimetypes
from urllib.parse import urlsplit, unquote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image
from core import service

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        root=Path(__file__).parent.joinpath('web','dist').resolve()
        target=(root/(unquote(urlsplit(self.path).path).lstrip('/') or 'index.html')).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            self.send_error(404); return
        body=target.read_bytes()
        mime=mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
        self.send_response(200); self.send_header('Content-Type',mime); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 8_000_000:
                raise ValueError('请求大小应在 8 MB 以内')
            obj=json.loads(self.rfile.read(size))
            if self.path=='/api/generate':
                im=service.embed(service.generate(obj['public']),obj.get('secret',''),obj.get('key',''))
                buf=io.BytesIO(); im.save(buf,format='PNG')
                result={'png':base64.b64encode(buf.getvalue()).decode(),'capacity_bytes':11960,'scan_status':'unverified'}
            elif self.path in ('/api/extract','/api/detect'):
                im=Image.open(io.BytesIO(base64.b64decode(obj['png'],validate=True)))
                if im.format!='PNG' or im.width*im.height>4_000_000:
                    raise ValueError('仅接收不超过 400 万像素的 PNG')
                result=service.extract(im,obj.get('key','')) if self.path.endswith('extract') else service.detect(im,obj.get('method','chi_square'))
            else:
                self.send_error(404); return
            status=200
        except (ValueError,KeyError,OSError) as exc:
            status=400; result={'error':str(exc)}
        body=json.dumps(result,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.end_headers(); self.wfile.write(body)

if __name__=='__main__':
    print('打开 http://127.0.0.1:8000 ，Ctrl+C 退出')
    ThreadingHTTPServer(('127.0.0.1',8000),Handler).serve_forever()
