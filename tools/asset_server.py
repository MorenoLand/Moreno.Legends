from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
import re
from disc import configure_overwrite, write_output

ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "build" / "mml2-mesh-viewer"
OUTPUT = ROOT / "assets" / "converted"

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(VIEWER), **kwargs)

    def do_POST(self):
        name = unquote(urlsplit(self.path).path.removeprefix("/upload/"))
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}\.glb", name):
            self.send_error(400, "Invalid asset name")
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid content length")
            return
        if size < 20 or size > 64 * 1024 * 1024:
            self.send_error(413, "GLB size outside accepted range")
            return
        data = self.rfile.read(size)
        if len(data) != size or data[:4] != b"glTF":
            self.send_error(400, "Invalid GLB payload")
            return
        OUTPUT.mkdir(parents=True, exist_ok=True)
        target = OUTPUT / name
        changed = write_output(target, data)
        body = f"{'Saved' if changed else 'Unchanged'} {target.relative_to(ROOT).as_posix()}".encode()
        self.send_response(201 if changed else 200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print(body.decode())

    def log_message(self, format, *args):
        print(format % args)

if __name__ == "__main__":
    configure_overwrite(True)
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
