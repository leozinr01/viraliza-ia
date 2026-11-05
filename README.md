# Viraliza ⚡

Transforma a live da Twitch em **cortes verticais legendados** pra TikTok, Shorts e Reels, mais um **vídeo longo** pro YouTube. Tudo automático.

## Como funciona

```
 site estático (Cloudflare Pages)  ──►  Supabase (login + banco)  ◄──  worker.py (notebook)
                                                                        │ baixa o VOD, corta, legenda
                                                                        ▼
                                                              Cloudflare R2 (vídeos, 7 dias)
```

1. **Durante a live:** o worker grava o chat da Twitch. O streamer digita `#corte` pra marcar um momento.
2. **Depois da live:** cola o link do VOD no site e o worker processa:
   - picos de volume + picos de chat → melhores momentos;
   - Whisper transcreve e gera legenda palavra por palavra;
   - ffmpeg monta o vertical 9:16 e o vídeo longo.
3. Os vídeos sobem pro R2. O site mostra os cortes com o botão **Baixar MP4** e marca onde cada um já foi postado.

## Estrutura

| Caminho | O que é |
|---|---|
| `site_src/` | modelos das páginas (Jinja) |
| `site/` | site estático gerado. É essa pasta que vai pro Cloudflare Pages |
| `build_site.py` | gera `site/` a partir de `site_src/` |
| `servir_site.py` | servidor local pra testar (http://localhost:8080) |
| `worker.py` | roda no notebook: fila de processamento, gravação de chat, upload e limpeza |
| `cortes.py` | o processamento em si (download, detecção, legenda, render) |
| `gravar_chat.py` | grava o chat da Twitch (IRC anônimo, só leitura) |
| `supabase/schema.sql` | tabelas e regras de segurança (RLS) |
| `config.py` | ajustes: quantidade e duração dos cortes, zoom, hashtags… |
| `painel.py`, `auth.py`, `web/` | versão antiga, local, com Flask. Foi substituída pelo site + worker |

## Rodando

1. **Instale:** Python 3.13 e ffmpeg; depois rode `pip install -r requirements.txt`.
2. **Configure:** copie `.env.example` para `.env` e preencha as chaves do R2 e do Supabase.
3. **Crie o banco:** rode `supabase/schema.sql` no SQL Editor do Supabase.
4. **Ligue o worker:** `python worker.py` (deixe a janela aberta).
5. **Gere e teste o site:** `python build_site.py` e depois `python servir_site.py`.

> O `.env` **nunca** deve ir pro GitHub (já está no `.gitignore`).
