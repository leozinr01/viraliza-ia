"""VIRALIZA — painel web.   Rode:  python painel.py   e abra http://localhost:5000"""
import os, sys, json, glob, re, shutil, subprocess, threading, webbrowser, time
from flask import Flask, request, jsonify, send_from_directory, send_file, abort, Response, session, redirect, render_template
import auth
import config

BASE = os.path.dirname(os.path.abspath(__file__))
TRAB = os.path.join(BASE, config.PASTA_TRABALHO)
CHATS = os.path.join(BASE, "chats")
PREFS = os.path.join(BASE, "preferencias.json")
FF_BIN = r"C:\Users\lucas\tools\ffmpeg\ffmpeg-master-latest-win64-gpl\bin"
os.makedirs(TRAB, exist_ok=True)
os.makedirs(CHATS, exist_ok=True)
app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
auth.registrar(app)

ETAPAS = ["Baixando o VOD", "Analisando o áudio", "Lendo o chat", "Escolhendo momentos",
          "Gerando cortes verticais", "Montando o vídeo longo", "Finalizando"]


# ------------------------------------------------------------------ utilidades
def prefs():
    try:
        return json.load(open(PREFS, encoding="utf-8"))
    except Exception:
        return {}


def salvar_prefs(**kw):
    p = prefs()
    p.update(kw)
    json.dump(p, open(PREFS, "w", encoding="utf-8"))


def live_dir(live):
    if not re.fullmatch(r"[\w\-]+", live or ""):
        abort(404)
    d = os.path.join(TRAB, live)
    if not os.path.isdir(d):
        abort(404)
    return d


def slug(txt, n=50):
    txt = re.sub(r"#\w+|[^\w\s-]", "", txt or "").strip().lower()
    return re.sub(r"\s+", "_", txt)[:n].strip("_") or "corte"


# Os processos rodam separados do painel (log em arquivo), então fechar/reiniciar o painel não interrompe nada.
def _arq(nome, ext):
    return os.path.join(TRAB, f"_{nome}.{ext}")


def pid_vivo(pid):
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ok = k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    return bool(ok) and code.value == 259  # STILL_ACTIVE


def iniciar(nome, args):
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", HF_HUB_DISABLE_SYMLINKS_WARNING="1",
               PATH=os.environ.get("PATH", "") + os.pathsep + FF_BIN)
    log = open(_arq(nome, "log"), "w", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "-W", "ignore", *args], cwd=BASE, env=env, stdout=log,
                         stderr=subprocess.STDOUT,
                         creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    json.dump({"pid": p.pid}, open(_arq(nome, "json"), "w"))


def rodando(nome):
    try:
        return pid_vivo(json.load(open(_arq(nome, "json")))["pid"])
    except Exception:
        return False


def parar(nome):
    try:
        pid = json.load(open(_arq(nome, "json")))["pid"]
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
    except Exception:
        pass


def linhas_log(nome):
    try:
        with open(_arq(nome, "log"), "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 300_000))
            txt = f.read().decode("utf-8", "ignore")
    except FileNotFoundError:
        return []
    return [l.rstrip() for l in txt.replace("\r", "\n").split("\n") if l.strip()]


def progresso():
    linhas = linhas_log("cortes")
    p = {"etapa": 0, "texto": "", "download": "", "sub": None, "codigo": None}
    log = []
    for ln in linhas:
        m = re.match(r"(\d)/7 (.*)", ln)
        c = re.search(r"corte (\d+)/(\d+)", ln)
        d = re.search(r"\[download\]\s+([\d.]+)%", ln)
        t = re.search(r"time=(\d+:\d+:\d+)", ln)
        if m:
            p.update(etapa=int(m.group(1)), texto=m.group(2).rstrip("."), sub=None)
        elif c:
            p["sub"] = [int(c.group(1)), int(c.group(2))]
        elif d:
            p["download"] = d.group(1) + "%"
        elif t and "frame=" in ln:
            p["download"] = "baixado " + t.group(1)
        if not (ln.startswith("[download]") or "frame=" in ln or "Opening '" in ln):
            log.append(ln)
    if linhas and not rodando("cortes"):
        p["codigo"] = 0 if any("Pronto! Abra:" in l for l in linhas[-5:]) else 1
    return p, log[-40:]


def ler_estado(d):
    p = os.path.join(d, "estado.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def resumo_live(d):
    live = os.path.basename(d)
    meta = os.path.join(d, "cortes.json")
    cortes = json.load(open(meta, encoding="utf-8")) if os.path.exists(meta) else []
    est = ler_estado(d)
    info = {}
    if os.path.exists(os.path.join(d, "info.json")):
        try:
            i = json.load(open(os.path.join(d, "info.json"), encoding="utf-8"))
            info = {"titulo": i.get("title"), "canal": i.get("uploader") or i.get("channel")}
        except Exception:
            pass
    postados = sum(1 for c in cortes if any(est.get(str(c["n"]), {}).get(r) for r in ("tiktok", "shorts", "reels")))
    longo = os.path.join(d, "youtube_longo.mp4")
    return {"id": live, "qtd": len(cortes), "postados": postados, "info": info,
            "data": time.strftime("%d/%m %H:%M", time.localtime(os.path.getmtime(d))),
            "longo": os.path.exists(longo), "longo_postado": bool(est.get("longo", {}).get("youtube")),
            "capa": cortes[0]["arquivo"] if cortes else None,
            "incompleta": not os.path.exists(os.path.join(d, "revisao.html"))}


# ------------------------------------------------------------------ API
@app.get("/api/status")
def status():
    lives = [resumo_live(d) for d in sorted(glob.glob(os.path.join(TRAB, "*")), key=os.path.getmtime, reverse=True)
             if os.path.isdir(d)]
    prog, log_cortes = progresso()
    return jsonify(chat=rodando("chat"), cortes=rodando("cortes"), log_chat=linhas_log("chat")[-6:],
                   log_cortes=log_cortes, prog=prog, etapas=ETAPAS, lives=lives,
                   canal=prefs().get("canal") or ("" if config.CANAL == "seu_canal_aqui" else config.CANAL),
                   marcador=config.MARCADOR,
                   chats=sorted((os.path.basename(c) for c in glob.glob(os.path.join(CHATS, "*.jsonl"))), reverse=True))


@app.post("/api/chat/iniciar")
def chat_iniciar():
    canal = ((request.json or {}).get("canal") or "").strip().lower().lstrip("@#")
    if not canal:
        return jsonify(ok=False, erro="Digite o nome do seu canal da Twitch")
    salvar_prefs(canal=canal)
    if not rodando("chat"):
        iniciar("chat", ["gravar_chat.py", canal])
    return jsonify(ok=True)


@app.post("/api/chat/parar")
def chat_parar():
    parar("chat")
    return jsonify(ok=True)


@app.post("/api/processar")
def processar():
    if rodando("cortes"):
        return jsonify(ok=False, erro="Já tem uma live sendo processada")
    d = request.json or {}
    fonte = (d.get("fonte") or "").strip()
    if not fonte:
        return jsonify(ok=False, erro="Cole o link do VOD da Twitch")
    args = ["cortes.py", fonte]
    if d.get("chat"):
        args += ["--chat", os.path.join("chats", os.path.basename(d["chat"]))]
    if d.get("teste"):
        args += ["--teste", "10"]
    if d.get("sem_longo"):
        args.append("--sem-longo")
    iniciar("cortes", args)
    return jsonify(ok=True)


@app.post("/api/cancelar")
def cancelar():
    parar("cortes")
    return jsonify(ok=True)


@app.get("/api/live/<live>")
def api_live(live):
    d = live_dir(live)
    meta = os.path.join(d, "cortes.json")
    return jsonify(resumo=resumo_live(d), estado=ler_estado(d),
                   cortes=json.load(open(meta, encoding="utf-8")) if os.path.exists(meta) else [])


@app.post("/api/live/<live>/corte/<n>")
def marcar(live, n):
    d = live_dir(live)
    est = ler_estado(d)
    est.setdefault(n, {}).update(request.json or {})
    json.dump(est, open(os.path.join(d, "estado.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return jsonify(ok=True)


@app.post("/api/live/<live>/excluir")
def excluir(live):
    d = live_dir(live)
    if rodando("cortes"):
        return jsonify(ok=False, erro="Espere o processamento atual terminar")
    shutil.rmtree(d, ignore_errors=True)
    return jsonify(ok=not os.path.exists(d), erro="Algum arquivo está aberto em outro programa. Feche e tente de novo.")


@app.post("/api/live/<live>/abrir")
def abrir_pasta(live):
    os.startfile(live_dir(live))
    return jsonify(ok=True)


@app.get("/arquivo/<live>/<path:caminho>")
def arquivo(live, caminho):
    return send_from_directory(live_dir(live), caminho, conditional=True)


@app.get("/baixar/<live>/<n>")
def baixar(live, n):
    d = live_dir(live)
    est = ler_estado(d)
    if n == "longo":
        caminho = os.path.join(d, "youtube_longo.mp4")
        nome = f"viraliza_{live}_youtube.mp4"
    else:
        cortes = {str(c["n"]): c for c in json.load(open(os.path.join(d, "cortes.json"), encoding="utf-8"))}
        if n not in cortes:
            abort(404)
        c = cortes[n]
        caminho = os.path.join(d, c["arquivo"])
        nome = f"viraliza_{int(n):02d}_{slug(est.get(n, {}).get('titulo') or c['titulo'])}.mp4"
    if not os.path.exists(caminho):
        abort(404)
    return send_file(caminho, as_attachment=True, download_name=nome, mimetype="video/mp4")


# ------------------------------------------------------------------ páginas
@app.get("/app")
def inicio():
    return Response(pagina(PAG_INICIO, "Viraliza"), mimetype="text/html")


@app.get("/app/live/<live>")
def pagina_live(live):
    live_dir(live)
    return Response(pagina(PAG_LIVE, "Cortes · Viraliza"), mimetype="text/html")


def pagina(corpo, titulo):
    return f"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{titulo}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
<link rel="icon" href="data:image/svg+xml,{ICONE_URL}">
<style>{CSS}</style><script>{JS_BASE}</script></head><body>
<header class="top"><a class="logo" href="/app">{LOGO}<span>viraliza</span></a>
<div class="row"><div id="pillchat" class="pill" hidden><i></i>gravando chat</div>
<span class="meta">{session.get("nome","")}</span><a class="btn sec sm" href="/sair">Sair</a></div></header>
<div id="toast"></div>{corpo}</body></html>"""


LOGO = """<svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#ff2e63"/><stop offset="1" stop-color="#ff9f1c"/></linearGradient></defs>
<rect width="32" height="32" rx="9" fill="url(#g)"/><path d="M18 5 9 18h6l-2 9 10-14h-6z" fill="#fff"/></svg>"""
ICONE_URL = ("%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='9' "
             "fill='%23ff2e63'/%3E%3Cpath d='M18 5 9 18h6l-2 9 10-14h-6z' fill='%23fff'/%3E%3C/svg%3E")

CSS = """
:root{--bg:#09090d;--p1:#121219;--p2:#181821;--line:#262631;--txt:#f5f5f8;--mut:#8e8ea0;--brand:#ff2e63;--brand2:#ff9f1c;
--ok:#22c55e;--grad:linear-gradient(135deg,#ff2e63,#ff9f1c);--r:16px}
*{box-sizing:border-box}html{color-scheme:dark}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.5 Inter,system-ui,Segoe UI,sans-serif;
background-image:radial-gradient(900px 400px at 85% -10%,rgba(255,46,99,.12),transparent),radial-gradient(700px 360px at -10% 10%,rgba(255,159,28,.07),transparent);min-height:100vh}
a{color:inherit}h1,h2,h3,.logo span,.num{font-family:"Space Grotesk",Inter,sans-serif;letter-spacing:-.02em}
.top{display:flex;align-items:center;justify-content:space-between;padding:16px 28px;border-bottom:1px solid var(--line);
position:sticky;top:0;background:rgba(9,9,13,.8);backdrop-filter:blur(12px);z-index:5}
.logo{display:flex;align-items:center;gap:10px;text-decoration:none}.logo span{font-size:22px;font-weight:700}
.pill{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;padding:6px 12px;border-radius:99px;background:rgba(255,46,99,.12);color:#ff7a9a}
.pill i{width:8px;height:8px;border-radius:50%;background:var(--brand);animation:pulse 1.2s infinite}
@keyframes pulse{50%{opacity:.25}}
.wrap{max-width:1240px;margin:0 auto;padding:32px 28px 80px}
.hero h1{font-size:34px;margin:0 0 4px}.hero p{color:var(--mut);margin:0 0 28px}
.grad{background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:24px}
.stat{background:var(--p1);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px}
.stat .num{font-size:28px;font-weight:700}.stat .lbl{color:var(--mut);font-size:13px}
.cols{display:grid;grid-template-columns:1fr 1.4fr;gap:18px;margin-bottom:36px}
.card{background:var(--p1);border:1px solid var(--line);border-radius:var(--r);padding:22px}
.card h2{font-size:18px;margin:0 0 4px;display:flex;align-items:center;gap:10px}
.card .desc{color:var(--mut);font-size:14px;margin:0 0 18px}
.step{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:8px;background:var(--grad);font-size:13px;color:#fff;font-family:Inter}
label.f{display:block;font-size:12px;font-weight:600;color:var(--mut);margin:0 0 6px;text-transform:uppercase;letter-spacing:.04em}
input[type=text],select,textarea{width:100%;background:var(--bg);border:1px solid var(--line);color:var(--txt);padding:11px 13px;border-radius:10px;font:inherit;outline:none;transition:border .15s}
input[type=text]:focus,select:focus,textarea:focus{border-color:var(--brand)}
.fld{margin-bottom:14px}.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.chk{display:flex;align-items:center;gap:8px;color:var(--mut);font-size:14px;cursor:pointer}
.chk input{accent-color:var(--brand);width:16px;height:16px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;border:0;border-radius:10px;padding:11px 18px;font:600 14px Inter,sans-serif;cursor:pointer;text-decoration:none;color:#fff;background:var(--grad);transition:transform .1s,filter .15s,opacity .15s;white-space:nowrap}
.btn:hover{filter:brightness(1.1)}.btn:active{transform:scale(.97)}.btn:disabled{opacity:.45;cursor:default;filter:none}
.btn.sec{background:var(--p2);border:1px solid var(--line)}.btn.sec:hover{border-color:#3a3a48}
.btn.dang{background:transparent;color:#ff6b81;border:1px solid rgba(255,107,129,.3)}
.btn.full{width:100%}.btn.sm{padding:7px 11px;font-size:13px;border-radius:8px}
.btn svg{width:16px;height:16px}
.live-st{display:flex;align-items:center;gap:14px;padding:14px;border-radius:12px;background:var(--p2);border:1px solid var(--line);margin-bottom:14px}
.big-dot{width:14px;height:14px;border-radius:50%;background:#444;flex:none}.big-dot.on{background:var(--brand);box-shadow:0 0 0 6px rgba(255,46,99,.18);animation:pulse 1.2s infinite}
.hint{font-size:13px;color:var(--mut);margin-top:12px}.hint b{color:var(--txt)}
.mini-log{font:12px/1.5 ui-monospace,Consolas,monospace;color:var(--mut);margin-top:10px;max-height:90px;overflow:auto}
.prog{margin-top:18px;padding:16px;border-radius:12px;background:var(--p2);border:1px solid var(--line)}
.prog-top{display:flex;justify-content:space-between;font-size:14px;font-weight:600;margin-bottom:10px}
.bar{height:8px;border-radius:99px;background:#262631;overflow:hidden}.bar i{display:block;height:100%;background:var(--grad);border-radius:99px;transition:width .5s}
.etapas{display:flex;gap:6px;margin-top:12px;flex-wrap:wrap}.etapas span{font-size:12px;padding:3px 9px;border-radius:99px;background:#1f1f29;color:var(--mut)}
.etapas span.feito{color:var(--ok);background:rgba(34,197,94,.1)}.etapas span.agora{color:#fff;background:rgba(255,46,99,.25)}
details.log summary{cursor:pointer;color:var(--mut);font-size:13px;margin-top:12px}
details.log pre{background:#050508;border-radius:10px;padding:12px;font-size:12px;max-height:260px;overflow:auto;white-space:pre-wrap;color:#b9b9c8;margin:8px 0 0}
.sec-h{display:flex;align-items:end;justify-content:space-between;margin:0 0 16px}.sec-h h2{margin:0;font-size:22px}
.lives{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:16px}
.lv{background:var(--p1);border:1px solid var(--line);border-radius:var(--r);overflow:hidden;display:flex;flex-direction:column;transition:border .15s,transform .15s}
.lv:hover{border-color:#3a3a48;transform:translateY(-2px)}
.lv .capa{aspect-ratio:16/9;background:#000;position:relative;overflow:hidden;display:block}
.lv .capa video{width:100%;height:100%;object-fit:cover;filter:brightness(.8)}
.lv .capa .tag{position:absolute;left:10px;top:10px}
.lv .body{padding:14px 16px;display:flex;flex-direction:column;gap:10px;flex:1}
.lv h3{margin:0;font-size:16px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.meta{color:var(--mut);font-size:13px}
.tag{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:4px 10px;border-radius:99px;background:rgba(0,0,0,.6);color:#fff;backdrop-filter:blur(6px)}
.tag.ok{background:rgba(34,197,94,.15);color:#4ade80}.tag.warn{background:rgba(255,159,28,.15);color:#ffb84d}
.empty{border:1px dashed var(--line);border-radius:var(--r);padding:40px;text-align:center;color:var(--mut)}
.lv .acts{display:flex;gap:8px;margin-top:auto}
/* página da live */
.back{color:var(--mut);text-decoration:none;font-size:14px}.back:hover{color:var(--txt)}
.lhead{display:flex;justify-content:space-between;align-items:end;gap:16px;flex-wrap:wrap;margin:10px 0 24px}
.lhead h1{margin:0;font-size:30px}
.yt{display:grid;grid-template-columns:1.6fr 1fr;gap:22px;align-items:center;margin-bottom:34px}
.yt video{width:100%;border-radius:12px;background:#000;aspect-ratio:16/9}
.yt h2{margin:6px 0 8px;font-size:22px}
.tabs{display:flex;gap:6px;background:var(--p1);border:1px solid var(--line);padding:4px;border-radius:12px}
.tabs button{border:0;background:none;color:var(--mut);font:600 13px Inter;padding:7px 12px;border-radius:8px;cursor:pointer}
.tabs button.on{background:var(--p2);color:var(--txt)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:18px}
.ct{background:var(--p1);border:1px solid var(--line);border-radius:var(--r);overflow:hidden;display:flex;flex-direction:column;transition:opacity .2s}
.ct.descartado{opacity:.35}
.ct .vid{position:relative;background:#000}.ct video{width:100%;aspect-ratio:9/16;display:block}
.ct .vid .tags{position:absolute;top:10px;left:10px;right:10px;display:flex;gap:6px;justify-content:space-between;pointer-events:none}
.ct .body{padding:12px;display:flex;flex-direction:column;gap:10px}
.ct textarea{font-size:13px;resize:vertical;min-height:56px;color:#ffd27a}
.redes{display:flex;gap:6px}.rd{flex:1;border:1px solid var(--line);background:var(--p2);color:var(--mut);font:600 12px Inter;padding:7px 4px;border-radius:8px;cursor:pointer}
.rd.on{background:rgba(34,197,94,.14);border-color:rgba(34,197,94,.4);color:#4ade80}
.minis{display:flex;gap:6px}.minis .btn{flex:1}
#toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(20px);background:#fff;color:#111;font-weight:600;padding:10px 18px;border-radius:10px;opacity:0;transition:.25s;pointer-events:none;z-index:9}
#toast.show{opacity:1;transform:translateX(-50%)}
@media(max-width:900px){.cols,.yt{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}}
@media(max-width:600px){.wrap{padding:20px 16px 60px}.top{padding:12px 16px}.hero h1{font-size:26px}}
"""

ICON_DL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 20h14"/></svg>'

JS_BASE = """
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function toast(t){const e=$('#toast');e.textContent=t;e.classList.add('show');clearTimeout(e._t);e._t=setTimeout(()=>e.classList.remove('show'),2200)}
async function post(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
 const j=await r.json();if(!j.ok&&j.erro)toast(j.erro);return j}
const ICON_DL='""" + ICON_DL + """';
function hms(s){s=Math.floor(s);return Math.floor(s/3600)+':'+String(Math.floor(s%3600/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0')}
"""

PAG_INICIO = """<main class="wrap">
<section class="hero"><h1>Sua live vira <span class="grad">conteúdo</span>.</h1>
<p>Grave o chat durante a live, cole o link do VOD e o Viraliza entrega os cortes prontos pra postar.</p></section>
<div class="stats">
 <div class="stat"><div class="num" id="s-lives">0</div><div class="lbl">lives processadas</div></div>
 <div class="stat"><div class="num" id="s-cortes">0</div><div class="lbl">cortes gerados</div></div>
 <div class="stat"><div class="num" id="s-post">0</div><div class="lbl">cortes postados</div></div>
 <div class="stat"><div class="num" id="s-fila">0</div><div class="lbl">esperando postagem</div></div>
</div>
<div class="cols">
 <section class="card"><h2><span class="step">1</span>Durante a live</h2>
  <p class="desc">Grava o chat da Twitch pra achar os momentos que mais bombaram.</p>
  <div class="live-st"><div class="big-dot" id="dot"></div><div style="flex:1"><b id="st-chat">Parado</b>
   <div class="meta" id="st-chat2">Inicie antes de entrar ao vivo</div></div></div>
  <div class="fld"><label class="f" for="canal">Seu canal na Twitch</label><input type="text" id="canal" placeholder="ex: leozinrwz"></div>
  <button class="btn full" id="b-chat">Iniciar gravação</button>
  <p class="hint">Rolou algo absurdo? Digite <b id="marc">#corte</b> no chat pelo celular, o corte é garantido.</p>
  <div class="mini-log" id="log-chat"></div>
 </section>
 <section class="card"><h2><span class="step">2</span>Depois da live</h2>
  <p class="desc">Cole o link do VOD. Ele baixa, encontra os melhores momentos e gera tudo sozinho.</p>
  <div class="fld"><label class="f" for="fonte">Link do VOD</label><input type="text" id="fonte" placeholder="https://www.twitch.tv/videos/123456789"></div>
  <div class="fld"><label class="f" for="selchat">Chat gravado dessa live</label><select id="selchat"></select></div>
  <div class="row" style="justify-content:space-between">
   <div class="row"><label class="chk"><input type="checkbox" id="teste">Teste rápido (10 min)</label>
   <label class="chk"><input type="checkbox" id="semlongo">Sem vídeo longo</label></div>
   <div class="row"><button class="btn dang" id="b-canc" hidden>Cancelar</button><button class="btn" id="b-proc">Gerar cortes</button></div>
  </div>
  <div class="prog" id="prog" hidden>
   <div class="prog-top"><span id="p-txt"></span><span id="p-pct"></span></div>
   <div class="bar"><i id="p-bar" style="width:0"></i></div>
   <div class="etapas" id="p-et"></div>
   <details class="log"><summary>Ver detalhes</summary><pre id="log-cortes"></pre></details>
  </div>
 </section>
</div>
<div class="sec-h"><h2>Suas lives</h2></div>
<div class="lives" id="lives"></div>
</main>
<script>
let S={},primeira=true;
$('#b-chat').onclick=async()=>{if(S.chat){await post('/api/chat/parar');toast('Gravação parada')}else{const j=await post('/api/chat/iniciar',{canal:$('#canal').value});if(j.ok)toast('Gravando o chat!')}tick()};
$('#b-proc').onclick=async()=>{const j=await post('/api/processar',{fonte:$('#fonte').value,chat:$('#selchat').value,teste:$('#teste').checked,sem_longo:$('#semlongo').checked});if(j.ok)toast('Começou! Pode deixar rodando.');tick()};
$('#b-canc').onclick=async()=>{await post('/api/cancelar');tick()};
async function excluir(id){if(!confirm('Excluir a live '+id+' e todos os cortes dela?'))return;const j=await post('/api/live/'+id+'/excluir');if(j.ok)toast('Excluída');tick()}
function render(){
 $('#pillchat').hidden=!S.chat;$('#dot').className='big-dot'+(S.chat?' on':'');
 $('#st-chat').textContent=S.chat?'Gravando o chat de '+($('#canal').value||'...'):'Parado';
 $('#st-chat2').textContent=S.chat?'Pode ir pra live, deixa isso aberto':'Inicie antes de entrar ao vivo';
 $('#b-chat').textContent=S.chat?'Parar gravação':'Iniciar gravação';$('#b-chat').className='btn full'+(S.chat?' sec':'');
 $('#log-chat').textContent=S.log_chat.slice(-3).join('\\n');$('#marc').textContent=S.marcador;
 if(primeira){$('#canal').value=S.canal||''}
 const sel=$('#selchat'),v=sel.value;
 sel.innerHTML='<option value="">Sem chat (só pelo áudio)</option>'+S.chats.map(c=>`<option value="${esc(c)}">${esc(c.replace('.jsonl','').replace(/_/g,' '))}</option>`).join('');
 sel.value=primeira&&S.chats.length?S.chats[0]:v;
 const P=S.prog,on=S.cortes;
 $('#b-proc').disabled=on;$('#b-proc').textContent=on?'Processando...':'Gerar cortes';$('#b-canc').hidden=!on;
 if(on||P.codigo!==null&&S.log_cortes.length){
  $('#prog').hidden=false;
  let pct=((P.etapa-1)/7)*100;if(P.etapa==5&&P.sub)pct+=(P.sub[0]-1)/P.sub[1]*(100/7);
  if(P.etapa==1&&P.download.endsWith('%'))pct=parseFloat(P.download)/7;
  let txt=P.texto+(P.etapa==5&&P.sub?` (${P.sub[0]} de ${P.sub[1]})`:'')+(P.etapa==1&&P.download?` · ${P.download}`:'');
  if(!on){pct=P.codigo===0?100:pct;txt=P.codigo===0?'Pronto! Seus cortes estão logo abaixo 👇':'Parou antes de terminar. Veja os detalhes.'}
  $('#p-txt').textContent=txt;$('#p-pct').textContent=Math.round(pct)+'%';$('#p-bar').style.width=pct+'%';
  $('#p-et').innerHTML=S.etapas.map((e,i)=>`<span class="${i+1<P.etapa||(!on&&P.codigo===0)?'feito':i+1==P.etapa&&on?'agora':''}">${e}</span>`).join('');
  const l=$('#log-cortes');const fim=l.scrollTop+l.clientHeight>=l.scrollHeight-5;l.textContent=S.log_cortes.join('\\n');if(fim)l.scrollTop=1e9;
 }
 const L=S.lives,tot=L.reduce((a,l)=>a+l.qtd,0),post=L.reduce((a,l)=>a+l.postados,0);
 $('#s-lives').textContent=L.filter(l=>l.qtd).length;$('#s-cortes').textContent=tot;$('#s-post').textContent=post;$('#s-fila').textContent=tot-post;
 const html=L.length?L.map(l=>`<article class="lv">
  <a class="capa" href="${l.qtd?'/app/live/'+l.id:'#'}">${l.capa?`<video src="/arquivo/${l.id}/${l.capa}#t=8" preload="metadata" muted></video>`:''}
   ${l.incompleta?`<span class="tag warn">${on?'processando':'incompleta'}</span>`:`<span class="tag">${l.qtd} cortes</span>`}</a>
  <div class="body"><h3 title="${esc(l.info.titulo||l.id)}">${esc(l.info.titulo||'Live '+l.id)}</h3>
   <div class="meta">${esc(l.info.canal||'')} ${l.info.canal?'·':''} ${l.data}</div>
   <div class="row">${l.qtd?`<span class="tag ${l.postados==l.qtd?'ok':''}">${l.postados}/${l.qtd} postados</span>`:''}${l.longo?`<span class="tag ${l.longo_postado?'ok':''}">YouTube ${l.longo_postado?'✓':'pronto'}</span>`:''}</div>
   <div class="acts">${l.qtd?`<a class="btn sm" href="/app/live/${l.id}" style="flex:1">Ver cortes</a>`:''}<button class="btn sm dang" onclick="excluir('${l.id}')">Excluir</button></div>
  </div></article>`).join(''):'<div class="empty">Nenhuma live ainda. Grave o chat, faça sua live e cole o link do VOD aqui em cima.</div>';
 const key=JSON.stringify(L);if(key!==render._k){$('#lives').innerHTML=html;render._k=key}
 primeira=false;
}
async function tick(){S=await (await fetch('/api/status')).json();render()}
tick();setInterval(tick,2000);
</script>"""

PAG_LIVE = """<main class="wrap">
<a class="back" href="/app">← Voltar</a>
<div class="lhead"><div><h1 id="titulo">Carregando...</h1><div class="meta" id="sub"></div></div>
<div class="row"><button class="btn sec sm" id="b-pasta">Abrir pasta</button></div></div>
<section class="card yt" id="yt" hidden><video id="ytv" controls preload="metadata"></video>
 <div><span class="tag" style="background:rgba(255,0,0,.15);color:#ff6b6b">YouTube</span><h2>Vídeo longo</h2>
 <p class="meta" id="yt-info"></p>
 <div class="row" style="margin-top:16px"><a class="btn" id="yt-dl">${ICON_DL} Baixar MP4</a>
 <button class="rd" id="yt-post" style="flex:none;padding:10px 14px">Marcar como postado</button></div></div></section>
<div class="sec-h"><h2>Cortes verticais <span class="meta" id="cnt"></span></h2>
<div class="tabs" id="tabs"><button class="on" data-f="todos">Todos</button><button data-f="pend">Falta postar</button><button data-f="post">Postados</button><button data-f="desc">Descartados</button></div></div>
<div class="grid" id="grid"></div>
</main>
<script>
const LIVE=location.pathname.split('/').pop(),REDES={tiktok:'TikTok',shorts:'Shorts',reels:'Reels'};
let D,filtro='todos';
document.querySelectorAll('[id=yt-dl]').forEach(a=>a.innerHTML=a.innerHTML.replace('${ICON_DL}',ICON_DL));
$('#b-pasta').onclick=()=>post(`/api/live/${LIVE}/abrir`);
function est(n){return D.estado[n]||(D.estado[n]={})}
function salvar(n,d){Object.assign(est(n),d);post(`/api/live/${LIVE}/corte/${n}`,d)}
function postado(n){const e=est(n);return Object.keys(REDES).some(r=>e[r])}
function filtrar(){let c=0;document.querySelectorAll('.ct').forEach(el=>{const n=el.dataset.n,e=est(n),p=postado(n);
 const ok=filtro=='todos'?!e.descartado:filtro=='pend'?!p&&!e.descartado:filtro=='post'?p:e.descartado;el.hidden=!ok;if(ok)c++});
 $('#cnt').textContent=`· ${D.cortes.filter(c=>postado(c.n)).length} de ${D.cortes.length} postados`}
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#tabs button').forEach(x=>x.classList.remove('on'));b.classList.add('on');filtro=b.dataset.f;filtrar()});
function card(c){const e=est(c.n);return `<article class="ct ${e.descartado?'descartado':''}" data-n="${c.n}">
 <div class="vid"><video src="/arquivo/${LIVE}/${c.arquivo}" controls preload="metadata"></video>
 <div class="tags"><span class="tag">#${c.n} · ${hms(c.inicio)}</span>${c.marcador?'<span class="tag warn">⭐ #corte</span>':`<span class="tag">🔥 ${c.nota.toFixed(1)}</span>`}</div></div>
 <div class="body"><textarea rows="2" data-k="titulo">${esc(e.titulo||c.titulo)}</textarea>
 <a class="btn full" href="/baixar/${LIVE}/${c.n}">${ICON_DL} Baixar MP4</a>
 <div class="redes">${Object.entries(REDES).map(([r,l])=>`<button class="rd ${e[r]?'on':''}" data-r="${r}">${e[r]?'✓ ':''}${l}</button>`).join('')}</div>
 <div class="minis"><button class="btn sec sm" data-a="copiar">Copiar título</button><button class="btn sec sm" data-a="desc">${e.descartado?'Restaurar':'Descartar'}</button></div>
 </div></article>`}
$('#grid').addEventListener('click',ev=>{const b=ev.target.closest('button');if(!b)return;const el=b.closest('.ct'),n=el.dataset.n;
 if(b.dataset.r){const v=!est(n)[b.dataset.r];salvar(n,{[b.dataset.r]:v});b.classList.toggle('on',v);b.textContent=(v?'✓ ':'')+REDES[b.dataset.r];if(v)toast('Marcado como postado no '+REDES[b.dataset.r])}
 else if(b.dataset.a=='copiar'){navigator.clipboard.writeText(el.querySelector('textarea').value);toast('Título copiado')}
 else if(b.dataset.a=='desc'){const v=!est(n).descartado;salvar(n,{descartado:v});el.classList.toggle('descartado',v);b.textContent=v?'Restaurar':'Descartar'}
 filtrar()});
$('#grid').addEventListener('change',ev=>{if(ev.target.dataset.k){salvar(ev.target.closest('.ct').dataset.n,{titulo:ev.target.value});toast('Título salvo')}});
async function carregar(){D=await (await fetch('/api/live/'+LIVE)).json();const r=D.resumo;
 document.title=(r.info.titulo||'Live '+LIVE)+' · Viraliza';$('#titulo').textContent=r.info.titulo||'Live '+LIVE;
 $('#sub').textContent=[r.info.canal,r.data,r.qtd+' cortes'].filter(Boolean).join(' · ');
 if(r.longo){$('#yt').hidden=false;$('#ytv').src=`/arquivo/${LIVE}/youtube_longo.mp4`;$('#yt-dl').href=`/baixar/${LIVE}/longo`;
  $('#yt-info').textContent='Os melhores momentos da live em ordem, pronto pra subir no YouTube.';
  const yb=$('#yt-post'),sy=()=>{const v=!!est('longo').youtube;yb.classList.toggle('on',v);yb.textContent=v?'✓ Postado no YouTube':'Marcar como postado'};sy();
  yb.onclick=()=>{salvar('longo',{youtube:!est('longo').youtube});sy()}}
 $('#grid').innerHTML=D.cortes.map(card).join('');filtrar()}
carregar();
</script>"""

if __name__ == "__main__":
    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:5000")).start()
    print("Viraliza rodando em http://localhost:5000  (feche esta janela para desligar)")
    app.run(port=5000, threaded=True)
