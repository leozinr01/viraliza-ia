"""Grava o chat da Twitch durante a live (conexão anônima, só leitura).

Uso:  python gravar_chat.py            (usa o CANAL do config.py)
      python gravar_chat.py outro_canal
Deixe rodando enquanto estiver ao vivo. Ctrl+C para parar.
"""
import socket, sys, time, json, os, random
import config

canal = (sys.argv[1] if len(sys.argv) > 1 else config.CANAL).lower().lstrip("#@")
os.makedirs("chats", exist_ok=True)
arquivo = sys.argv[2] if len(sys.argv) > 2 else os.path.join("chats", f"{canal}_{time.strftime('%Y-%m-%d_%H-%M')}.jsonl")


def conectar():
    s = socket.socket()
    s.settimeout(360)
    s.connect(("irc.chat.twitch.tv", 6667))
    s.send(f"NICK justinfan{random.randint(10000, 99999)}\r\n".encode())
    s.send(f"JOIN #{canal}\r\n".encode())
    return s


def main():
    print(f"Gravando chat de #{canal} em {arquivo}  (Ctrl+C para parar)")
    total = 0
    with open(arquivo, "a", encoding="utf-8") as f:
        while True:
            try:
                s = conectar()
                buf = ""
                while True:
                    dados = s.recv(4096).decode("utf-8", "ignore")
                    if not dados:
                        raise ConnectionError("conexão fechada")
                    buf += dados
                    *linhas, buf = buf.split("\r\n")
                    for ln in linhas:
                        if ln.startswith("PING"):
                            s.send(ln.replace("PING", "PONG").encode() + b"\r\n")
                        elif " PRIVMSG " in ln:
                            user = ln[1:ln.find("!")]
                            msg = ln.split(" :", 1)[1] if " :" in ln else ""
                            f.write(json.dumps({"t": time.time(), "user": user, "msg": msg}, ensure_ascii=False) + "\n")
                            f.flush()
                            total += 1
                            if msg.strip().lower().startswith(config.MARCADOR):
                                print(f"  >>> MARCADOR de {user} às {time.strftime('%H:%M:%S')}")
                            elif total % 100 == 0:
                                print(f"  {total} mensagens...")
            except KeyboardInterrupt:
                print(f"\nParado. {total} mensagens salvas em {arquivo}")
                return
            except Exception as e:
                print(f"  conexão caiu ({e}), reconectando em 5s...")
                time.sleep(5)


if __name__ == "__main__":
    main()
