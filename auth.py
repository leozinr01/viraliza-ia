"""Contas, login, contato e páginas públicas do Viraliza."""
import os, re, sqlite3, secrets, time
from flask import request, session, redirect, render_template, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "viraliza.db")
CHAVE = os.path.join(BASE, ".chave_sessao")
PROTEGIDAS = ("/app", "/api/", "/arquivo/", "/baixar/")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


def iniciar_db():
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS usuarios(id INTEGER PRIMARY KEY, nome TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL, criado REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS contatos(id INTEGER PRIMARY KEY, nome TEXT, email TEXT, assunto TEXT,
        mensagem TEXT, criado REAL NOT NULL);
    """)
    con.commit()
    con.close()


def chave_secreta():
    if not os.path.exists(CHAVE):
        open(CHAVE, "w").write(secrets.token_hex(32))
    return open(CHAVE).read().strip()


def registrar(app):
    iniciar_db()
    app.secret_key = chave_secreta()
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30)

    @app.teardown_appcontext
    def fechar(_):
        d = g.pop("db", None)
        if d:
            d.close()

    @app.before_request
    def proteger():
        if request.path.startswith(PROTEGIDAS) and not session.get("uid"):
            if request.path.startswith("/api/"):
                return jsonify(ok=False, erro="Faça login de novo"), 401
            return redirect("/entrar?proximo=" + request.path)

    @app.get("/")
    def home():
        return render_template("home.html", logado=bool(session.get("uid")))

    @app.get("/contato")
    def contato():
        return render_template("contato.html", logado=bool(session.get("uid")), enviado=False, erro=None, dados={})

    @app.post("/contato")
    def contato_enviar():
        d = {k: (request.form.get(k) or "").strip() for k in ("nome", "email", "assunto", "mensagem")}
        erro = None
        if not d["nome"] or not d["mensagem"]:
            erro = "Preencha seu nome e a mensagem."
        elif not EMAIL_RE.match(d["email"]):
            erro = "Esse e-mail não parece válido."
        if erro:
            return render_template("contato.html", logado=bool(session.get("uid")), enviado=False, erro=erro, dados=d)
        db().execute("INSERT INTO contatos(nome,email,assunto,mensagem,criado) VALUES(?,?,?,?,?)",
                     (d["nome"][:120], d["email"][:200], d["assunto"][:120], d["mensagem"][:5000], time.time()))
        db().commit()
        return render_template("contato.html", logado=bool(session.get("uid")), enviado=True, erro=None, dados={})

    @app.get("/entrar")
    def entrar():
        if session.get("uid"):
            return redirect("/app")
        return render_template("entrar.html", modo=request.args.get("modo", "entrar"), erro=None, dados={})

    def destino():
        p = request.args.get("proximo") or "/app"
        return p if p.startswith("/app") else "/app"

    @app.post("/entrar")
    def entrar_post():
        email = (request.form.get("email") or "").strip().lower()
        u = db().execute("SELECT * FROM usuarios WHERE email=?", (email,)).fetchone()
        if not u or not check_password_hash(u["senha"], request.form.get("senha") or ""):
            return render_template("entrar.html", modo="entrar", erro="E-mail ou senha incorretos.", dados={"email": email})
        session.clear()
        session.permanent = True
        session.update(uid=u["id"], nome=u["nome"].split()[0])
        return redirect(destino())

    @app.post("/criar-conta")
    def criar_conta():
        d = {"nome": (request.form.get("nome") or "").strip(), "email": (request.form.get("email") or "").strip().lower()}
        senha = request.form.get("senha") or ""
        erro = None
        if not d["nome"]:
            erro = "Como a gente te chama?"
        elif not EMAIL_RE.match(d["email"]):
            erro = "Esse e-mail não parece válido."
        elif len(senha) < 8:
            erro = "A senha precisa ter pelo menos 8 caracteres."
        elif db().execute("SELECT 1 FROM usuarios WHERE email=?", (d["email"],)).fetchone():
            erro = "Já existe uma conta com esse e-mail. Faça login."
        if erro:
            return render_template("entrar.html", modo="criar", erro=erro, dados=d)
        cur = db().execute("INSERT INTO usuarios(nome,email,senha,criado) VALUES(?,?,?,?)",
                           (d["nome"][:80], d["email"][:200], generate_password_hash(senha), time.time()))
        db().commit()
        session.clear()
        session.permanent = True
        session.update(uid=cur.lastrowid, nome=d["nome"].split()[0])
        return redirect("/app")

    @app.get("/sair")
    def sair():
        session.clear()
        return redirect("/")
