"""VIRALIZA: transforma o VOD da live em cortes verticais legendados + um vídeo longo pro YouTube.

Uso:
  python cortes.py <link do VOD (Twitch, YouTube ou Kick) ou arquivo .mp4> [--chat chats/arquivo.jsonl] [--teste MINUTOS]

Etapas (cada uma é salva; se rodar de novo, pula o que já foi feito):
  1. baixa o VOD          2. analisa o volume do áudio      3. lê o chat gravado
  4. escolhe os momentos  5. transcreve + legenda + renderiza os verticais
  6. monta o vídeo longo  7. gera a página de revisão (revisao.html)
"""
import argparse, json, os, re, subprocess, sys, html, glob, shutil
import numpy as np
import config

FFMPEG = shutil.which("ffmpeg") or r"C:\Users\lucas\tools\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if r.returncode != 0:
        raise RuntimeError("Falhou: " + " ".join(cmd[:6]) + "...\n" + r.stderr[-1500:])
    return r


def hms(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


# ---------------------------------------------------------------- 1. download
def baixar(fonte, pasta, teste_min):
    vod = os.path.join(pasta, "vod.mp4")
    info_path = os.path.join(pasta, "info.json")
    if os.path.exists(vod):
        return vod, json.load(open(info_path, encoding="utf-8")) if os.path.exists(info_path) else {}
    if os.path.isfile(fonte):
        shutil.copy(fonte, vod)
        return vod, {}
    print("1/7 Baixando o VOD (pode demorar)...")
    # YouTube entrega 720p/1080p com vídeo e áudio separados (bv+ba); Twitch e Kick vêm juntos (b)
    cmd = [sys.executable, "-m", "yt_dlp", "-f", "bv[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv[height<=1080]+ba/b[height<=1080]/b", "-N", "8",
           "--ffmpeg-location", FFMPEG, "--write-info-json", "-o", os.path.join(pasta, "vod.%(ext)s"),
           "--remux-video", "mp4", "--no-playlist", fonte]
    js = next((r for r in ("deno", "node") if shutil.which(r)), None)  # o YouTube precisa de um runtime JS
    if js:
        cmd[3:3] = ["--js-runtimes", js]
    if teste_min:
        cmd[3:3] = ["--download-sections", f"*0-{teste_min * 60}"]
    subprocess.run(cmd, check=True)
    for f in glob.glob(os.path.join(pasta, "vod.info.json")):
        os.replace(f, info_path)
    return vod, json.load(open(info_path, encoding="utf-8")) if os.path.exists(info_path) else {}


# ---------------------------------------------------------------- 2. áudio
def volume_por_segundo(vod, pasta):
    cache = os.path.join(pasta, "volume.npy")
    if os.path.exists(cache):
        return np.load(cache)
    print("2/7 Analisando o áudio...")
    sr = 8000
    p = subprocess.Popen([FFMPEG, "-v", "quiet", "-i", vod, "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         stdout=subprocess.PIPE)
    db = []
    while True:
        chunk = p.stdout.read(sr * 2 * 60)  # 60s por vez
        if not chunk:
            break
        a = np.frombuffer(chunk, np.int16).astype(np.float32) / 32768
        n = len(a) // sr
        if n == 0:
            break
        rms = np.sqrt((a[: n * sr].reshape(n, sr) ** 2).mean(axis=1) + 1e-10)
        db.extend(20 * np.log10(rms))
    db = np.array(db)
    np.save(cache, db)
    return db


# ---------------------------------------------------------------- 3. chat
HYPE = re.compile(r"(k{3,}|kek|lul|omegalul|pog|monka|caraca|mds|meu deus|hahaha|clip|clipa|corte|\?{3,}|!{3,})", re.I)


def ler_chat(chat_path, inicio_vod, n, canal=None):
    taxa = np.zeros(n)
    marcadores = []
    if not chat_path or not os.path.exists(chat_path):
        return taxa, marcadores
    print("3/7 Lendo o chat...")
    canal = (canal or "").lower()
    for ln in open(chat_path, encoding="utf-8"):
        m = json.loads(ln)
        t = m["t"] - inicio_vod
        msg = m["msg"].strip()
        if msg.lower().startswith(config.MARCADOR):
            if not canal or m["user"].lower() == canal:  # só o dono do canal marca
                marcadores.append(t)
                continue
        i = int(t - config.ATRASO_CHAT)
        if 0 <= i < n:
            taxa[i] += 2.0 if HYPE.search(msg) else 1.0
    print(f"    {int(taxa.sum())} pontos de chat, {len(marcadores)} marcadores {config.MARCADOR}")
    return taxa, marcadores


# ---------------------------------------------------------------- 4. momentos
def suavizar(x, w):
    return np.convolve(x, np.ones(w) / w, mode="same") if len(x) > w else x


def zscore_local(x, janela=180):
    """Quanto o valor está acima do 'normal' dos últimos minutos."""
    base = np.repeat([np.median(x[max(0, i - janela): i + 1]) for i in range(0, len(x), 10)], 10)[: len(x)]
    d = x - base
    return d / (d.std() + 1e-6)


def pontuar(db, taxa):
    s = config.PESO_AUDIO * zscore_local(suavizar(db, 3))
    if taxa.sum() > 0:
        s += config.PESO_CHAT * zscore_local(suavizar(taxa, 10))
    return s


def escolher_picos(score, qtd, distancia):
    ordem = np.argsort(score)[::-1]
    picos = []
    for i in ordem:
        if score[i] < 1.0 or len(picos) >= qtd:
            break
        if all(abs(i - p) >= distancia for p in picos):
            picos.append(int(i))
    return picos


# ---------------------------------------------------------------- 5. verticais
_modelo = None


def transcrever(audio_wav):
    global _modelo
    from faster_whisper import WhisperModel
    if _modelo is None:
        print(f"    carregando Whisper '{config.MODELO_WHISPER}' (1ª vez baixa o modelo)...")
        _modelo = WhisperModel(config.MODELO_WHISPER, device="cpu", compute_type="int8")
    segs, _ = _modelo.transcribe(audio_wav, language=config.IDIOMA, word_timestamps=True, vad_filter=True)
    palavras, texto = [], []
    for sg in segs:
        texto.append(sg.text.strip())
        palavras += [(w.start, w.end, w.word.strip()) for w in (sg.words or []) if w.word.strip()]
    return palavras, " ".join(texto)


def ass_tempo(t):
    t = max(0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def gerar_ass(palavras, caminho):
    cab = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: L,Arial Black,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,7,3,2,60,60,430,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    linhas = []
    n = config.PALAVRAS_POR_LINHA
    for g in range(0, len(palavras), n):
        grupo = palavras[g: g + n]
        for k, (ini, fim, _) in enumerate(grupo):
            prox = grupo[k + 1][0] if k + 1 < len(grupo) else fim
            txt = " ".join(("{\\c&H00F5FF&}" + w.upper() + "{\\c&HFFFFFF&}") if j == k else w.upper()
                           for j, (_, _, w) in enumerate(grupo))
            linhas.append(f"Dialogue: 0,{ass_tempo(ini)},{ass_tempo(max(prox, ini + 0.1))},L,,0,0,0,,{txt}")
    open(caminho, "w", encoding="utf-8").write(cab + "\n".join(linhas) + "\n")


_encoder = None


def encoder():
    """Usa o Quick Sync da Intel (bem mais rápido no notebook); se não der, cai pro x264."""
    global _encoder
    if _encoder is None:
        try:
            run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=black:s=320x240:d=1", "-c:v", "h264_qsv",
                 "-f", "null", "-"])
            _encoder = ["-c:v", "h264_qsv", "-global_quality", "22", "-preset", "medium"]
        except RuntimeError:
            _encoder = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]
        print(f"    encoder de vídeo: {_encoder[1]}")
    return _encoder


def renderizar_vertical(vod, ini, dur, pasta_corte):
    os.makedirs(pasta_corte, exist_ok=True)
    bruto = subprocess.run([FFMPEG, "-v", "error", "-ss", str(ini), "-t", str(dur), "-i", vod, "-vn", "-ac", "1",
                            "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    palavras, texto = transcrever(np.frombuffer(bruto, np.int16).astype(np.float32) / 32768)
    gerar_ass(palavras, os.path.join(pasta_corte, "legenda.ass"))
    z = config.ZOOM_HORIZONTAL
    filtro = (f"[0:v]split[a][b];"
              f"[a]scale=-2:480,crop=270:480,boxblur=12:2,scale=1080:1920,eq=brightness=-0.08[bg];"
              f"[b]crop=iw*{z}:ih,scale=1080:-2[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2-170,subtitles=legenda.ass,fps=30,format=nv12[v]")
    run([FFMPEG, "-y", "-v", "error", "-ss", str(ini), "-t", str(dur), "-i", os.path.abspath(vod),
         "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?", *encoder(),
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
         "corte.mp4"], cwd=pasta_corte)
    return texto


def sugerir_titulo(texto, n):
    frase = re.split(r"[.!?]", texto.strip())[0][:70].strip() if texto.strip() else ""
    tags = getattr(config, "HASHTAGS", "#gta6")
    return (frase.capitalize() + " 😂 " + tags) if frase else f"Momento #{n} {tags}"


# ---------------------------------------------------------------- 6. longo
def montar_longo(vod, score, total_seg, pasta):
    saida = os.path.join(pasta, "youtube_longo.mp4")
    if os.path.exists(saida):
        return saida, []
    print(f"6/7 Montando o vídeo longo (~{config.DURACAO_LONGO_MIN} min)...")
    alvo = config.DURACAO_LONGO_MIN * 60
    picos = escolher_picos(score, 200, config.CONTEXTO_ANTES + config.CONTEXTO_DEPOIS)
    trechos, soma = [], 0
    for p in picos:
        a, b = max(0, p - config.CONTEXTO_ANTES), min(total_seg, p + config.CONTEXTO_DEPOIS)
        trechos.append([a, b])
        soma += b - a
        if soma >= alvo:
            break
    if not trechos:  # live calma: usa o começo
        trechos = [[0, min(total_seg, alvo)]]
    trechos.sort()
    unidos = [trechos[0]]
    for a, b in trechos[1:]:
        if a <= unidos[-1][1] + 20:
            unidos[-1][1] = max(unidos[-1][1], b)
        else:
            unidos.append([a, b])
    partes = os.path.join(pasta, "partes_longo")
    os.makedirs(partes, exist_ok=True)
    lista = []
    for k, (a, b) in enumerate(unidos):
        arq = os.path.join(partes, f"p{k:03d}.mp4")
        print(f"    trecho {k + 1}/{len(unidos)}: {hms(a)} -> {hms(b)}")
        run([FFMPEG, "-y", "-v", "error", "-ss", str(a), "-t", str(b - a), "-i", vod,
             "-vf", "fps=30,format=nv12", *encoder(), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", arq])
        lista.append(f"file '{os.path.abspath(arq)}'")
    open(os.path.join(partes, "lista.txt"), "w").write("\n".join(lista))
    run([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", os.path.join(partes, "lista.txt"),
         "-c", "copy", "-movflags", "+faststart", saida])
    shutil.rmtree(partes)
    return saida, unidos


# ---------------------------------------------------------------- 7. revisão
def pagina_revisao(pasta, cortes, trechos_longo):
    cards = []
    for c in cortes:
        cards.append(f"""<div class=card><video src="{c['arquivo']}" controls preload=metadata></video>
<b>#{c['n']} · {hms(c['inicio'])} · nota {c['nota']:.1f} {'· ⭐ marcador' if c['marcador'] else ''}</b>
<p class=t>{html.escape(c['titulo'])}</p><details><summary>fala</summary>{html.escape(c['texto'])}</details></div>""")
    longo = "".join(f"<li>{hms(a)} → {hms(b)}</li>" for a, b in trechos_longo)
    open(os.path.join(pasta, "revisao.html"), "w", encoding="utf-8").write(f"""<!doctype html><meta charset=utf-8>
<title>Viraliza</title><style>body{{font-family:system-ui;background:#111;color:#eee;margin:16px}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}}
.card{{background:#1c1c1c;padding:10px;border-radius:10px}}video{{width:100%;border-radius:6px}}.t{{color:#ffd400}}</style>
<h1>Cortes verticais ({len(cortes)})</h1><div class=g>{''.join(cards)}</div>
<h1>Vídeo longo</h1><video src="youtube_longo.mp4" controls style="max-width:900px;width:100%"></video><ul>{longo}</ul>""")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fonte", help="link do VOD (Twitch, YouTube ou Kick) ou arquivo de vídeo")
    ap.add_argument("--chat", help="arquivo .jsonl gravado pelo gravar_chat.py")
    ap.add_argument("--teste", type=int, help="baixa só os primeiros N minutos (pra testar)")
    ap.add_argument("--sem-longo", action="store_true")
    ap.add_argument("--canal", help="dono do canal: só ele pode usar o #corte")
    a = ap.parse_args()

    nome = re.sub(r"\W+", "_", os.path.basename(a.fonte.rstrip("/")))[:40] + (f"_teste{a.teste}" if a.teste else "")
    pasta = os.path.join(config.PASTA_TRABALHO, nome)
    os.makedirs(pasta, exist_ok=True)

    vod, info = baixar(a.fonte, pasta, a.teste)
    db = volume_por_segundo(vod, pasta)
    n = len(db)
    print(f"    duração: {hms(n)}")
    inicio = info.get("timestamp") or 0
    taxa, marcadores = ler_chat(a.chat, inicio, n, a.canal)

    print("4/7 Escolhendo os melhores momentos...")
    score = pontuar(db, taxa)
    picos = escolher_picos(score, config.MAX_CORTES, config.DISTANCIA_MINIMA)
    janelas = []
    for m in marcadores:  # marcador = o momento foi ~logo antes de você digitar
        fim = min(n, m - 3)
        janelas.append((max(0, fim - config.DURACAO_CORTE), 99.0, True))
    for p in picos:
        ini = max(0, p - config.ANTES_DO_PICO)
        if all(abs(ini - j[0]) > config.DURACAO_CORTE for j in janelas):
            janelas.append((ini, float(score[p]), False))
    janelas = sorted(janelas, key=lambda j: -j[1])[: config.MAX_CORTES + len(marcadores)]
    janelas.sort()

    print(f"5/7 Gerando {len(janelas)} cortes verticais legendados...")
    cortes = []
    meta_path = os.path.join(pasta, "cortes.json")
    feitos = {c["n"]: c for c in json.load(open(meta_path, encoding="utf-8"))} if os.path.exists(meta_path) else {}
    for k, (ini, nota, marc) in enumerate(janelas, 1):
        dur = min(config.DURACAO_CORTE, n - ini)
        if dur < 10:
            continue
        pc = os.path.join(pasta, "verticais", f"corte_{k:02d}")
        if k in feitos and feitos[k]["inicio"] == ini and os.path.exists(os.path.join(pc, "corte.mp4")):
            cortes.append(feitos[k])
            continue
        print(f"    corte {k}/{len(janelas)}  ({hms(ini)}, nota {nota:.1f})")
        texto = renderizar_vertical(vod, ini, dur, pc)
        cortes.append({"n": k, "inicio": ini, "duracao": dur, "nota": nota, "marcador": marc, "texto": texto,
                       "titulo": sugerir_titulo(texto, k), "arquivo": f"verticais/corte_{k:02d}/corte.mp4"})
        json.dump(cortes, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    trechos = []
    if not a.sem_longo:
        _, trechos = montar_longo(vod, score, n, pasta)
    print("7/7 Gerando página de revisão...")
    pagina_revisao(pasta, cortes, trechos)
    print(f"\nPronto! Abra: {os.path.abspath(os.path.join(pasta, 'revisao.html'))}")


if __name__ == "__main__":
    main()
