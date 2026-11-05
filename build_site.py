"""Monta o site estático em ./site a partir dos modelos em ./site_src.
Uso:  python build_site.py
Depois é só publicar a pasta ./site (Cloudflare Pages, Netlify, Vercel...)."""
import base64, hashlib, os, re, time, urllib.request
from jinja2 import Environment, FileSystemLoader

BASE = os.path.dirname(os.path.abspath(__file__))
SRC, OUT = os.path.join(BASE, "site_src"), os.path.join(BASE, "site")
PAGINAS = {"index.html": "index.html", "entrar.html": "entrar.html", "contato.html": "contato.html",
           "app.html": "app/index.html", "live.html": "app/live.html", "conexoes.html": "app/conexoes.html",
           "privacidade.html": "privacidade.html", "termos.html": "termos.html"}
SB_URL = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.49.4/dist/umd/supabase.js"


def sri(url):
    dados = urllib.request.urlopen(url, timeout=30).read()
    return "sha384-" + base64.b64encode(hashlib.sha384(dados).digest()).decode()


def main():
    env = Environment(loader=FileSystemLoader(SRC), autoescape=True)
    v = time.strftime("%Y%m%d%H%M")
    integ = sri(SB_URL)
    tag_antiga = f'<script src="{SB_URL}"></script>'
    tag_nova = f'<script src="{SB_URL}" integrity="{integ}" crossorigin="anonymous"></script>'
    for src, dst in PAGINAS.items():
        html = env.get_template(src).render(v=v).replace(tag_antiga, tag_nova)
        caminho = os.path.join(OUT, dst)
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        open(caminho, "w", encoding="utf-8").write(html)
        print("  ", dst)
    open(os.path.join(OUT, "_headers"), "w").write(
        "/*\n  X-Frame-Options: DENY\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n"
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()\n")
    print("Site montado em", OUT)


if __name__ == "__main__":
    main()
