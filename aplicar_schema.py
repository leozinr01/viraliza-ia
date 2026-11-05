"""Cria/atualiza as tabelas do Viraliza no Supabase usando SUPABASE_DB_URL do .env."""
import os, sys, psycopg
from dotenv import dotenv_values
BASE = os.path.dirname(os.path.abspath(__file__))
url = dotenv_values(os.path.join(BASE, ".env")).get("SUPABASE_DB_URL") or ""
if not url or "[YOUR-PASSWORD]" in url:
    sys.exit("Preencha SUPABASE_DB_URL no .env (com a senha no lugar de [YOUR-PASSWORD]).")
sql = open(os.path.join(BASE, "supabase", "schema.sql"), encoding="utf-8").read()
with psycopg.connect(url, connect_timeout=20) as con:
    con.execute(sql)
    con.commit()
    tabs = con.execute("select tablename, rowsecurity from pg_tables where schemaname='public' order by 1").fetchall()
print("Tabelas no banco:")
for t, rls in tabs:
    print(f"  {t:16} segurança (RLS): {'ligada' if rls else 'DESLIGADA'}")
