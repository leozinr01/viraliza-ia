"""VIRALIZA · envio dos vídeos pro YouTube, TikTok e Instagram (usado pelo worker).

Cada função recebe as chaves da conta conectada pelo usuário (tabela conexoes_tokens),
renova a chave quando precisa (chamando salvar(...) pra gravar a nova) e devolve o link do post.
"""
import datetime as dt, os, time
import requests

UTC = dt.timezone.utc
IG_VERSAO = "v24.0"


class ErroRede(Exception):
    """Erro com mensagem pronta pra mostrar no painel."""


def _agora():
    return dt.datetime.now(UTC)


def _vence_em(tk, folga_seg):
    if not tk.get("expira_em"):
        return False
    return dt.datetime.fromisoformat(tk["expira_em"].replace("Z", "+00:00")) < _agora() + dt.timedelta(seconds=folga_seg)


def _em(seg):
    return (_agora() + dt.timedelta(seconds=int(seg))).isoformat() if seg else None


def _json(r, onde):
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code >= 400:
        e = d.get("error")
        msg = (e.get("message") if isinstance(e, dict) else None) or d.get("error_description") or (e if isinstance(e, str) else "") or r.text[:200]
        raise ErroRede(f"{onde}: {msg}")
    return d


# ------------------------------------------------------------------ YouTube
def _yt_token(tk, env, salvar):
    if not _vence_em(tk, 120):
        return tk["access_token"]
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": env.get("GOOGLE_CLIENT_ID"), "client_secret": env.get("GOOGLE_CLIENT_SECRET"),
        "refresh_token": tk.get("refresh_token") or "", "grant_type": "refresh_token"})
    if r.status_code == 400:
        raise ErroRede("A conexão com o YouTube expirou. Conecte de novo em Conexões.")
    d = _json(r, "YouTube")
    salvar(d["access_token"], None, _em(d.get("expires_in")))
    return d["access_token"]


def youtube(tk, env, salvar, arquivo, titulo, descricao, privacidade, curto, progresso):
    token = _yt_token(tk, env, salvar)
    if curto and "#shorts" not in f"{titulo} {descricao}".lower():
        descricao = (descricao + "\n\n#Shorts").strip()
    meta = {"snippet": {"title": (titulo or "Corte")[:100], "description": descricao[:5000], "categoryId": "20"},
            "status": {"privacyStatus": privacidade, "selfDeclaredMadeForKids": False}}
    tam = os.path.getsize(arquivo)
    r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                      json=meta, timeout=30, headers={"Authorization": f"Bearer {token}", "X-Upload-Content-Type": "video/mp4",
                                                      "X-Upload-Content-Length": str(tam)})
    _json(r, "YouTube")
    progresso("enviando o vídeo")
    with open(arquivo, "rb") as f:
        r = requests.put(r.headers["Location"], data=f, timeout=(30, 3600),
                         headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"})
    vid = _json(r, "YouTube")["id"]
    return (f"https://youtube.com/shorts/{vid}" if curto else f"https://youtu.be/{vid}"), None


# ------------------------------------------------------------------ TikTok
TT = "https://open.tiktokapis.com/v2"


def _tt_token(tk, env, salvar):
    if not _vence_em(tk, 300):
        return tk["access_token"]
    r = requests.post(f"{TT}/oauth/token/", timeout=30, data={
        "client_key": env.get("TIKTOK_CLIENT_KEY"), "client_secret": env.get("TIKTOK_CLIENT_SECRET"),
        "grant_type": "refresh_token", "refresh_token": tk.get("refresh_token") or ""})
    d = r.json() if r.content else {}
    if not d.get("access_token"):
        raise ErroRede("A conexão com o TikTok expirou. Conecte de novo em Conexões.")
    salvar(d["access_token"], d.get("refresh_token"), _em(d.get("expires_in")))
    return d["access_token"]


def _tt_post(token, caminho, corpo):
    r = requests.post(f"{TT}{caminho}", json=corpo, timeout=30,
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"})
    d = r.json() if r.content else {}
    err = d.get("error") or {}
    if r.status_code >= 400 or (err.get("code") and err["code"] != "ok"):
        raise ErroRede(f"TikTok: {err.get('message') or err.get('code') or r.text[:200]}")
    return d.get("data") or {}


def tiktok(tk, env, salvar, arquivo, titulo, descricao, privacidade, curto, progresso):
    """Modo "rascunho" (padrão, funciona sem aprovação): o vídeo vai pra caixa de entrada do app do TikTok
    e a pessoa toca em publicar. Modo "direto" (TIKTOK_MODO=direto, depois da auditoria): publica na hora."""
    token = _tt_token(tk, env, salvar)
    tam = os.path.getsize(arquivo)
    pedaco = tam if tam <= 64 * 2**20 else 10 * 2**20          # até 64 MB vai inteiro
    partes = max(1, tam // pedaco)                               # o último pedaço leva o resto
    fonte = {"source": "FILE_UPLOAD", "video_size": tam, "chunk_size": pedaco, "total_chunk_count": partes}
    direto = (env.get("TIKTOK_MODO") or "rascunho").lower() == "direto"
    if direto:
        opcoes = _tt_post(token, "/post/publish/creator_info/query/", {}).get("privacy_level_options") or ["SELF_ONLY"]
        quer = {"public": "PUBLIC_TO_EVERYONE", "unlisted": "MUTUAL_FOLLOW_FRIENDS", "private": "SELF_ONLY"}[privacidade]
        nivel = quer if quer in opcoes else ("SELF_ONLY" if "SELF_ONLY" in opcoes else opcoes[0])
        legenda = (descricao or titulo or "")[:2200]
        d = _tt_post(token, "/post/publish/video/init/", {"post_info": {"title": legenda, "privacy_level": nivel},
                                                          "source_info": fonte})
    else:
        d = _tt_post(token, "/post/publish/inbox/video/init/", {"source_info": fonte})
    progresso("enviando o vídeo")
    with open(arquivo, "rb") as f:
        for i in range(partes):
            ini = i * pedaco
            fim = tam - 1 if i == partes - 1 else ini + pedaco - 1
            f.seek(ini)
            r = requests.put(d["upload_url"], data=f.read(fim - ini + 1), timeout=(30, 600),
                             headers={"Content-Type": "video/mp4", "Content-Range": f"bytes {ini}-{fim}/{tam}"})
            if r.status_code >= 400:
                raise ErroRede(f"TikTok recusou o envio do vídeo ({r.status_code}).")
    progresso("TikTok processando")
    for _ in range(120):
        st = _tt_post(token, "/post/publish/status/fetch/", {"publish_id": d["publish_id"]})
        s = st.get("status")
        if s == "FAILED":
            raise ErroRede(f"TikTok: {st.get('fail_reason') or 'falhou'}")
        if s == "SEND_TO_USER_INBOX":
            return None, "Enviado pros rascunhos do TikTok: abra o app e toque em publicar."
        if s == "PUBLISH_COMPLETE":
            ids = st.get("publicaly_available_post_id") or st.get("publicly_available_post_id") or []
            return (f"https://www.tiktok.com/video/{ids[0]}" if ids else None), None
        time.sleep(5)
    return None, "Enviado; o TikTok ainda está processando."


# ------------------------------------------------------------------ Instagram (Reels)
IG = f"https://graph.instagram.com/{IG_VERSAO}"


def _ig_token(tk, salvar):
    if not _vence_em(tk, 7 * 86400):  # chave dura 60 dias; renova na última semana
        return tk["access_token"]
    r = requests.get("https://graph.instagram.com/refresh_access_token", timeout=30,
                     params={"grant_type": "ig_refresh_token", "access_token": tk["access_token"]})
    if r.status_code >= 400:
        if _vence_em(tk, 0):
            raise ErroRede("A conexão com o Instagram expirou. Conecte de novo em Conexões.")
        return tk["access_token"]
    d = r.json()
    salvar(d["access_token"], None, _em(d.get("expires_in")))
    return d["access_token"]


def instagram(tk, conta_id, salvar, url_publica, legenda, progresso):
    """O Instagram busca o vídeo sozinho pela URL (o link assinado do R2)."""
    token = _ig_token(tk, salvar)
    c = _json(requests.post(f"{IG}/{conta_id}/media", timeout=60, data={
        "media_type": "REELS", "video_url": url_publica, "caption": (legenda or "")[:2200],
        "share_to_feed": "true", "access_token": token}), "Instagram")["id"]
    progresso("Instagram processando")
    for _ in range(120):
        s = _json(requests.get(f"{IG}/{c}", timeout=30, params={"fields": "status_code,status", "access_token": token}), "Instagram")
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise ErroRede(f"Instagram recusou o vídeo: {s.get('status') or s['status_code']}")
        time.sleep(5)
    else:
        raise ErroRede("O Instagram demorou demais pra processar o vídeo. Tente de novo.")
    mid = _json(requests.post(f"{IG}/{conta_id}/media_publish", timeout=60,
                              data={"creation_id": c, "access_token": token}), "Instagram")["id"]
    link = requests.get(f"{IG}/{mid}", timeout=30, params={"fields": "permalink", "access_token": token}).json().get("permalink")
    return link, None
