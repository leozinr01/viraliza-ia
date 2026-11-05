"""VIRALIZA · worker do notebook.

Fica ligado no notebook e faz o trabalho pesado que o site pede pelo Supabase:
  - grava o chat da Twitch quando você clica em "Iniciar gravação"
  - processa os VODs da fila (baixa, corta, legenda)
  - sobe os vídeos pro Cloudflare R2 e grava os links no banco
  - apaga vídeos com mais de 7 dias (R2 e notebook)

Uso:  python worker.py      (deixe a janela aberta)
"""
import datetime as dt, json, os, re, shutil, signal, subprocess, sys, time, unicodedata
import boto3, requests
from dotenv import dotenv_values

BASE = os.path.dirname(os.path.abspath(__file__))
ENV = dotenv_values(os.path.join(BASE, ".env"))
SB_URL = (ENV.get("SUPABASE_URL") or "").rstrip("/")
SB_KEY = ENV.get("SUPABASE_SECRET_KEY") or ""
BUCKET = ENV.get("R2_BUCKET") or "viraliza-cortes"
RETENCAO_DIAS = 7
FF_BIN = r"C:\Users\lucas\tools\ffmpeg\ffmpeg-master-latest-win64-gpl\bin"
TRAB = os.path.join(BASE, "trabalho")
CHATS = os.path.join(BASE, "chats")
LOG_JOB = os.path.join(TRAB, "_worker_job.log")
os.makedirs(TRAB, exist_ok=True)
os.makedirs(CHATS, exist_ok=True)

ETAPAS = {1: "Baixando o VOD", 2: "Analisando o áudio", 3: "Lendo o chat", 4: "Escolhendo momentos",
          5: "Gerando cortes", 6: "Montando o vídeo longo", 7: "Enviando os vídeos"}


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


# ------------------------------------------------------------------ Supabase (REST com a chave secreta)
class Banco:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"apikey": SB_KEY, "Content-Type": "application/json", "Prefer": "return=representation"})

    def _url(self, tabela):
        return f"{SB_URL}/rest/v1/{tabela}"

    def get(self, tabela, **params):
        r = self.s.get(self._url(tabela), params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    def patch(self, tabela, filtro, dados):
        r = self.s.patch(self._url(tabela), params=filtro, data=json.dumps(dados), timeout=20)
        r.raise_for_status()
        return r.json()

    def post(self, tabela, dados):
        r = self.s.post(self._url(tabela), data=json.dumps(dados), timeout=30)
        r.raise_for_status()
        return r.json()

    def delete(self, tabela, filtro):
        r = self.s.delete(self._url(tabela), params=filtro, timeout=20)
        r.raise_for_status()


# ------------------------------------------------------------------ R2
def cliente_r2():
    return boto3.client("s3", endpoint_url=f"https://{ENV['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                        aws_access_key_id=ENV["R2_ACCESS_KEY_ID"], aws_secret_access_key=ENV["R2_SECRET_ACCESS_KEY"],
                        region_name="auto")


def slug(txt, n=50):
    txt = unicodedata.normalize("NFKD", re.sub(r"#\w+", "", txt or "")).encode("ascii", "ignore").decode()
    txt = re.sub(r"[^\w\s-]", "", txt).strip().lower()
    return re.sub(r"\s+", "_", txt)[:n].strip("_") or "corte"


def subir(r2, local, chave, nome_download):
    r2.upload_file(local, BUCKET, chave, ExtraArgs={"ContentType": "video/mp4"})
    seg = RETENCAO_DIAS * 24 * 3600
    ver = r2.generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": chave}, ExpiresIn=seg)
    baixar = r2.generate_presigned_url("get_object", ExpiresIn=seg, Params={
        "Bucket": BUCKET, "Key": chave, "ResponseContentDisposition": f'attachment; filename="{nome_download}"'})
    return ver, baixar


# ------------------------------------------------------------------ processos
def env_proc():
    return dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", HF_HUB_DISABLE_SYMLINKS_WARNING="1",
                PATH=os.environ.get("PATH", "") + os.pathsep + FF_BIN)


def iniciar(args, log_path, modo="w"):
    f = open(log_path, modo, encoding="utf-8")
    return subprocess.Popen([sys.executable, "-W", "ignore", *args], cwd=BASE, env=env_proc(), stdout=f,
                            stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)


def matar(p):
    if p and p.poll() is None:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)


def linhas(path, limite=300_000):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - limite))
            txt = f.read().decode("utf-8", "ignore")
    except FileNotFoundError:
        return []
    return [l.rstrip() for l in txt.replace("\r", "\n").split("\n") if l.strip()]


def progresso(path):
    etapa, detalhe = 1, ""
    for ln in linhas(path):
        m = re.match(r"(\d)/7 ", ln)
        c = re.search(r"corte (\d+)/(\d+)", ln)
        d = re.search(r"\[download\]\s+([\d.]+)%", ln)
        t = re.search(r"trecho (\d+)/(\d+)", ln)
        if m:
            etapa, detalhe = int(m.group(1)), ""
        elif c:
            detalhe = f"{c.group(1)} de {c.group(2)}"
        elif t:
            detalhe = f"trecho {t.group(1)} de {t.group(2)}"
        elif d:
            detalhe = d.group(1) + "%"
    return etapa, detalhe


# ------------------------------------------------------------------ gravações de chat
class Gravacoes:
    def __init__(self, db):
        self.db, self.procs, self.ultima_contagem = db, {}, 0

    def arquivo(self, gid):
        return os.path.join(CHATS, f"{gid}.jsonl")

    def ciclo(self):
        for g in self.db.get("gravacoes_chat", status="in.(pedido,gravando,parar)", select="id,canal,status"):
            gid, p = g["id"], self.procs.get(g["id"])
            if g["status"] == "parar":
                matar(p)
                self.procs.pop(gid, None)
                self.db.patch("gravacoes_chat", {"id": f"eq.{gid}"}, {"status": "parado", **self.contar(gid)})
                log(f"chat #{g['canal']}: gravação parada")
            elif p is None or p.poll() is not None:  # pedido novo, ou o worker reiniciou no meio da live
                self.procs[gid] = iniciar(["gravar_chat.py", g["canal"], self.arquivo(gid)],
                                          os.path.join(TRAB, f"_chat_{gid}.log"), "a")
                if g["status"] == "pedido":
                    self.db.patch("gravacoes_chat", {"id": f"eq.{gid}"}, {"status": "gravando"})
                log(f"chat #{g['canal']}: gravando")
        if time.time() - self.ultima_contagem > 15:
            self.ultima_contagem = time.time()
            for gid in list(self.procs):
                try:
                    self.db.patch("gravacoes_chat", {"id": f"eq.{gid}"}, self.contar(gid))
                except Exception:
                    pass

    def contar(self, gid):
        msgs = marc = 0
        try:
            for ln in open(self.arquivo(gid), encoding="utf-8"):
                msgs += 1
                if '"#corte' in ln.lower():
                    marc += 1
        except FileNotFoundError:
            pass
        return {"mensagens": msgs, "marcadores": marc}

    def parar_tudo(self):
        for p in self.procs.values():
            matar(p)


# ------------------------------------------------------------------ processamento de lives
class Fila:
    def __init__(self, db):
        self.db, self.job, self.proc, self.ultimo_envio = db, None, None, 0

    def ciclo(self):
        if self.job:
            return self.acompanhar()
        fila = self.db.get("lives", status="eq.fila", order="criado_em.asc", limit=1)
        if fila:
            self.comecar(fila[0])

    def comecar(self, live):
        self.job = live
        args = ["cortes.py", live["fonte"]]
        canal = None
        if live.get("gravacao_id"):
            arq = os.path.join(CHATS, f"{live['gravacao_id']}.jsonl")
            g = self.db.get("gravacoes_chat", id=f"eq.{live['gravacao_id']}", select="canal")
            canal = g[0]["canal"] if g else None
            if os.path.exists(arq):
                args += ["--chat", arq]
        if canal:
            args += ["--canal", canal]
        if live.get("teste"):
            args += ["--teste", "10"]
        if live.get("sem_longo"):
            args.append("--sem-longo")
        self.db.patch("lives", {"id": f"eq.{live['id']}"}, {"status": "processando", "etapa": 1,
                                                             "etapa_texto": ETAPAS[1], "detalhe": "", "erro": None})
        self.proc = iniciar(args, LOG_JOB)
        log(f"live {live['id'][:8]}: começou ({live['fonte']})")

    def acompanhar(self):
        lid = self.job["id"]
        atual = self.db.get("lives", id=f"eq.{lid}", select="status")
        if not atual or atual[0]["status"] == "cancelar":
            matar(self.proc)
            if atual:
                self.db.patch("lives", {"id": f"eq.{lid}"}, {"status": "cancelado", "detalhe": ""})
            log(f"live {lid[:8]}: cancelada")
            self.job = self.proc = None
            return
        if self.proc.poll() is None:
            if time.time() - self.ultimo_envio > 3:
                self.ultimo_envio = time.time()
                e, d = progresso(LOG_JOB)
                self.db.patch("lives", {"id": f"eq.{lid}"}, {"etapa": e, "etapa_texto": ETAPAS.get(e, ""), "detalhe": d})
            return
        ls = linhas(LOG_JOB)
        pronto = next((l for l in reversed(ls) if "Pronto! Abra:" in l), None)
        if self.proc.returncode != 0 or not pronto:
            erro = "\n".join(l for l in ls[-6:] if "[download]" not in l)[-800:]
            self.db.patch("lives", {"id": f"eq.{lid}"}, {"status": "erro", "erro": erro or "Falhou sem mensagem"})
            log(f"live {lid[:8]}: ERRO\n{erro}")
        else:
            pasta = os.path.dirname(pronto.split("Abra:", 1)[1].strip())
            try:
                self.enviar(lid, pasta)
            except Exception as e:
                self.db.patch("lives", {"id": f"eq.{lid}"}, {"status": "erro", "erro": f"Falha ao enviar: {e}"[:800]})
                log(f"live {lid[:8]}: erro no envio: {e}")
        self.job = self.proc = None

    def enviar(self, lid, pasta):
        self.db.patch("lives", {"id": f"eq.{lid}"}, {"etapa": 7, "etapa_texto": ETAPAS[7], "detalhe": ""})
        r2 = cliente_r2()
        user_id = self.job["user_id"]
        cortes = json.load(open(os.path.join(pasta, "cortes.json"), encoding="utf-8"))
        self.db.delete("cortes", {"live_id": f"eq.{lid}"})  # se for reprocessamento
        expira = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=RETENCAO_DIAS)).isoformat()
        linhas_db = []
        for k, c in enumerate(cortes, 1):
            self.db.patch("lives", {"id": f"eq.{lid}"}, {"detalhe": f"{k} de {len(cortes)}"})
            ver, baixar = subir(r2, os.path.join(pasta, c["arquivo"]), f"lives/{lid}/corte_{c['n']:02d}.mp4",
                                f"viraliza_{c['n']:02d}_{slug(c['titulo'])}.mp4")
            linhas_db.append({"live_id": lid, "user_id": user_id, "n": c["n"], "inicio": c["inicio"], "duracao": c["duracao"],
                              "nota": c["nota"], "marcador": c["marcador"], "texto": c["texto"][:4000], "titulo": c["titulo"][:300],
                              "video_url": ver, "download_url": baixar, "expira_em": expira})
        if linhas_db:
            self.db.post("cortes", linhas_db)
        dados = {"status": "pronto", "etapa": 7, "detalhe": "", "expira_em": expira}
        longo = os.path.join(pasta, "youtube_longo.mp4")
        if os.path.exists(longo):
            self.db.patch("lives", {"id": f"eq.{lid}"}, {"detalhe": "vídeo longo"})
            dados["longo_url"], dados["longo_download_url"] = subir(r2, longo, f"lives/{lid}/youtube.mp4",
                                                                    f"viraliza_youtube_{lid[:8]}.mp4")
        info = os.path.join(pasta, "info.json")
        if os.path.exists(info):
            i = json.load(open(info, encoding="utf-8"))
            dados["titulo"], dados["canal"] = (i.get("title") or "")[:200], (i.get("uploader") or "")[:80]
        self.db.patch("lives", {"id": f"eq.{lid}"}, dados)
        # libera espaço no notebook: o VOD e os vídeos já estão no R2
        for nome in ("vod.mp4", "youtube_longo.mp4"):
            try:
                os.remove(os.path.join(pasta, nome))
            except FileNotFoundError:
                pass
        shutil.rmtree(os.path.join(pasta, "verticais"), ignore_errors=True)
        os.remove(os.path.join(pasta, "cortes.json"))  # força gerar de novo se reprocessar
        log(f"live {lid[:8]}: PRONTA, {len(linhas_db)} cortes enviados")

    def parar(self):
        matar(self.proc)


# ------------------------------------------------------------------ limpeza
def limpar(db):
    """Apaga do R2 vídeos com mais de 7 dias e vídeos de lives que foram excluídas no site."""
    r2 = cliente_r2()
    vivas = {l["id"] for l in db.get("lives", select="id")}
    limite = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=RETENCAO_DIAS)
    apagar = []
    for pg in r2.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="lives/"):
        for o in pg.get("Contents", []):
            lid = o["Key"].split("/")[1]
            if lid not in vivas or o["LastModified"] < limite:
                apagar.append({"Key": o["Key"]})
    for i in range(0, len(apagar), 1000):
        r2.delete_objects(Bucket=BUCKET, Delete={"Objects": apagar[i:i + 1000]})
    if apagar:
        log(f"limpeza: {len(apagar)} vídeos antigos apagados do R2")
    # VODs locais esquecidos (ex.: processamento cancelado) com mais de 2 dias
    for vod in __import__("glob").glob(os.path.join(TRAB, "*", "vod.mp4*")):
        if time.time() - os.path.getmtime(vod) > 2 * 86400:
            os.remove(vod)


# ------------------------------------------------------------------ main
def main():
    faltando = [k for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY") if not ENV.get(k)]
    if faltando:
        print("Faltam estes campos no arquivo .env:", ", ".join(faltando))
        sys.exit(1)
    db = Banco()
    db.get("worker", select="id")  # testa a conexão/chave
    # se o worker caiu no meio de um processamento, devolve pra fila (continua de onde parou)
    for l in db.patch("lives", {"status": "eq.processando"}, {"status": "fila", "detalhe": "retomando"}):
        log(f"live {l['id'][:8]}: retomando depois de reiniciar")
    grav, fila = Gravacoes(db), Fila(db)
    log("Worker do Viraliza ligado. Deixe esta janela aberta. (Ctrl+C para desligar)")
    ultimo_ping = ultima_limpeza = 0
    erros = 0
    try:
        while True:
            try:
                if time.time() - ultimo_ping > 30:
                    db.patch("worker", {"id": "eq.1"}, {"visto_em": dt.datetime.now(dt.timezone.utc).isoformat(),
                                                        "info": "processando" if fila.job else "livre"})
                    ultimo_ping = time.time()
                grav.ciclo()
                fila.ciclo()
                if time.time() - ultima_limpeza > 3600:
                    ultima_limpeza = time.time()
                    limpar(db)
                erros = 0
            except requests.RequestException as e:
                erros += 1
                log(f"sem conexão com o Supabase ({e.__class__.__name__}), tentando de novo...")
                time.sleep(min(60, 5 * erros))
            time.sleep(3)
    except KeyboardInterrupt:
        log("Desligando... (gravações de chat e processamento em andamento serão interrompidos)")
        grav.parar_tudo()
        fila.parar()


if __name__ == "__main__":
    main()
