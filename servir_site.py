"""Servidor local pra testar o site estático (imita o Cloudflare Pages: /entrar -> entrar.html).
Uso:  python servir_site.py   e abra http://localhost:8080"""
import http.server, os, socketserver, webbrowser, threading

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=PASTA, **k)

    def translate_path(self, path):
        p = super().translate_path(path)
        if not os.path.exists(p) and os.path.exists(p + ".html"):
            return p + ".html"
        return p

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", 8080), H) as s:
        print("Site em http://localhost:8080  (Ctrl+C para parar)")
        threading.Timer(1, lambda: webbrowser.open("http://localhost:8080")).start()
        s.serve_forever()
