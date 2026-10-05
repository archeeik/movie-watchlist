"""로컬 미리보기 서버. 배포본과 같은 주소 구조로 보여 준다: / → web/, /data/ → data/

    python scripts/dev_server.py [포트]
"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        clean = path.split("?", 1)[0].split("#", 1)[0]
        base = ROOT if clean.startswith("/data/") else ROOT / "web"
        self.directory = str(base)
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    Handler.extensions_map[".webp"] = "image/webp"
    print(f"http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(ROOT / "web"))).serve_forever()
