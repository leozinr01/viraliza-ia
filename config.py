# ============ CONFIGURAÇÕES DO VIRALIZA ============

# Seu canal da Twitch (sem @, minúsculo)
CANAL = "leozinrwz"

# Palavra que você (ou um mod) digita no chat pra marcar um momento
MARCADOR = "#corte"

# ---- Cortes verticais (TikTok / Shorts / Reels) ----
MAX_CORTES = 15            # quantos cortes curtos gerar por live
DURACAO_CORTE = 55         # segundos
ANTES_DO_PICO = 35         # quantos segundos antes do pico o corte começa
DISTANCIA_MINIMA = 90      # segundos mínimos entre dois cortes
ZOOM_HORIZONTAL = 0.65     # fração da largura do gameplay mostrada no vertical (menor = mais zoom)

# ---- Vídeo longo (YouTube) ----
DURACAO_LONGO_MIN = 20     # duração alvo em minutos (10 a 35)
CONTEXTO_ANTES = 90        # segundos de contexto antes de cada momento
CONTEXTO_DEPOIS = 60       # segundos depois

# Hashtags que vão no título sugerido de cada corte
HASHTAGS = "#gta6 #gta #fyp"

# ---- Legendas ----
MODELO_WHISPER = "small"   # "base" = mais rápido, "small" = melhor (notebook fraco: small ainda ok)
IDIOMA = "pt"
PALAVRAS_POR_LINHA = 3

# ---- Pesos da detecção ----
PESO_AUDIO = 1.0
PESO_CHAT = 1.5
ATRASO_CHAT = 8            # segundos: o chat reage depois do que aconteceu na tela

PASTA_TRABALHO = "trabalho"
