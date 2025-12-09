import http.server
import socketserver
import os


PORT = 5173
ROOT = os.path.dirname(__file__)


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.lstrip("/") or "index.html"
        return os.path.join(ROOT, path)


with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving {ROOT} at http://localhost:{PORT}")
    httpd.serve_forever()
