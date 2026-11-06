// Viraliza · conecta a conta do usuário no YouTube, TikTok ou Instagram (OAuth).
//
//  1. POST  { plataforma }     (com o login do Viraliza) -> { url } pra onde mandar o navegador
//  2. GET   ?code=...&state=...  (a rede volta pra cá)   -> repassa code e state pra página Conexões do site
//  3. POST  { code, state }     (com o login do Viraliza) -> confere que é o MESMO usuário que começou,
//                                                           troca o código pelas chaves e salva
// A troca acontece no passo 3, e não no 2, porque a volta da rede não traz o login: sem essa conferência,
// alguém poderia mandar o próprio link de conexão pra outra pessoa e ligar a conta dela no Viraliza dele.
//
// Deploy:  npx supabase functions deploy conectar --no-verify-jwt
// (sem verificação automática porque a volta da rede não traz o login; os POSTs verificam o login aqui dentro)
const env = (k: string) => Deno.env.get(k) ?? "";
const SB_URL = env("SUPABASE_URL");
// chave secreta do projeto (formato novo sb_secret_..., ou a service_role antiga)
const SB_KEY = env("SB_SECRET_KEY") || (() => { try { return Object.values(JSON.parse(env("SUPABASE_SECRET_KEYS")))[0] as string; } catch { return ""; } })()
  || env("SUPABASE_SERVICE_ROLE_KEY");

// REST do Supabase com a chave secreta (passa por cima do RLS; só esta função e o notebook usam)
async function upsert(tabela: string, conflito: string, dados: object) {
  const r = await fetch(`${SB_URL}/rest/v1/${tabela}?on_conflict=${conflito}`, {
    method: "POST", body: JSON.stringify(dados),
    headers: { apikey: SB_KEY, "Content-Type": "application/json", Prefer: "resolution=merge-duplicates,return=representation" },
  });
  if (!r.ok) throw new Error(`Banco: ${await r.text()}`);
  return (await r.json())[0];
}
async function usuario(jwt: string) {
  const r = await fetch(`${SB_URL}/auth/v1/user`, { headers: { apikey: SB_KEY, Authorization: `Bearer ${jwt}` } });
  return r.ok ? await r.json() : null;
}
const CALLBACK = `${SB_URL}/functions/v1/conectar`;
// Google: volta direto pra página Conexões do site (domínio do Viraliza, exigido na verificação do Google).
// TikTok e Instagram ainda voltam por esta função (GET abaixo), que repassa pro site.
const VOLTA_NO_SITE = new Set(["youtube"]);
const volta = (p: string, site: string) => (VOLTA_NO_SITE.has(p) ? `${site}/app/conexoes` : CALLBACK);
// sites que podem pedir conexão (o usuário volta pra ele no fim)
const SITES = [...env("SITE_URL").split(","), "http://localhost:8080"].map((s) => s.trim().replace(/\/$/, "")).filter(Boolean);

type Conta = { conta_id: string; conta_nome: string; conta_foto: string | null; access_token: string; refresh_token: string | null; expira_em: string | null };
type Rede = { auth: string; params: () => Record<string, string>; trocar: (code: string, redirect_uri: string) => Promise<Conta> };

const emSegundos = (s?: number) => (s ? new Date(Date.now() + s * 1000).toISOString() : null);

async function json(r: Response, onde: string) {
  const t = await r.text();
  let d: any;
  try { d = JSON.parse(t); } catch { d = { raw: t }; }
  if (!r.ok) throw new Error(`${onde}: ${d.error_description || d.error?.message || d.error_message || d.message || t.slice(0, 200)}`);
  return d;
}

const REDES: Record<string, Rede> = {
  youtube: {
    auth: "https://accounts.google.com/o/oauth2/v2/auth",
    params: () => ({
      // select_account: sempre pergunta qual conta Google (cada pessoa conecta o canal dela)
      client_id: env("GOOGLE_CLIENT_ID"), response_type: "code", access_type: "offline", prompt: "select_account consent",
      scope: "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
    }),
    async trocar(code, redirect_uri) {
      const tk = await json(await fetch("https://oauth2.googleapis.com/token", {
        method: "POST",
        body: new URLSearchParams({ code, client_id: env("GOOGLE_CLIENT_ID"), client_secret: env("GOOGLE_CLIENT_SECRET"), redirect_uri, grant_type: "authorization_code" }),
      }), "Google");
      const ch = await json(await fetch("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true", {
        headers: { Authorization: `Bearer ${tk.access_token}` },
      }), "YouTube");
      const c = ch.items?.[0];
      if (!c) throw new Error("Essa conta Google não tem um canal no YouTube.");
      return { conta_id: c.id, conta_nome: c.snippet.title, conta_foto: c.snippet.thumbnails?.default?.url ?? null,
               access_token: tk.access_token, refresh_token: tk.refresh_token ?? null, expira_em: emSegundos(tk.expires_in) };
    },
  },
  tiktok: {
    auth: "https://www.tiktok.com/v2/auth/authorize/",
    params: () => ({ client_key: env("TIKTOK_CLIENT_KEY"), response_type: "code", scope: "user.info.basic,video.upload,video.publish" }),
    async trocar(code, redirect_uri) {
      const tk = await json(await fetch("https://open.tiktokapis.com/v2/oauth/token/", {
        method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ client_key: env("TIKTOK_CLIENT_KEY"), client_secret: env("TIKTOK_CLIENT_SECRET"), code, grant_type: "authorization_code", redirect_uri }),
      }), "TikTok");
      if (!tk.access_token) throw new Error(`TikTok: ${tk.error_description || tk.error || "não autorizou"}`);
      const u = await json(await fetch("https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name,avatar_url", {
        headers: { Authorization: `Bearer ${tk.access_token}` },
      }), "TikTok");
      const user = u.data?.user ?? {};
      return { conta_id: tk.open_id, conta_nome: user.display_name || "TikTok", conta_foto: user.avatar_url ?? null,
               access_token: tk.access_token, refresh_token: tk.refresh_token ?? null, expira_em: emSegundos(tk.expires_in) };
    },
  },
  instagram: {
    auth: "https://www.instagram.com/oauth/authorize",
    params: () => ({ client_id: env("INSTAGRAM_APP_ID"), response_type: "code", scope: "instagram_business_basic,instagram_business_content_publish" }),
    async trocar(code, redirect_uri) {
      const curto = await json(await fetch("https://api.instagram.com/oauth/access_token", {
        method: "POST",
        body: new URLSearchParams({ client_id: env("INSTAGRAM_APP_ID"), client_secret: env("INSTAGRAM_APP_SECRET"), grant_type: "authorization_code", redirect_uri, code }),
      }), "Instagram");
      const t0 = curto.access_token ?? curto.data?.[0]?.access_token;
      // troca pela chave de 60 dias (o notebook renova antes de vencer)
      const longo = await json(await fetch(`https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret=${encodeURIComponent(env("INSTAGRAM_APP_SECRET"))}&access_token=${encodeURIComponent(t0)}`), "Instagram");
      const me = await json(await fetch(`https://graph.instagram.com/me?fields=user_id,username,profile_picture_url,account_type&access_token=${encodeURIComponent(longo.access_token)}`), "Instagram");
      if (me.account_type && !["BUSINESS", "MEDIA_CREATOR"].includes(me.account_type))
        throw new Error("Só contas profissionais (Criador ou Empresa) podem publicar pelo Viraliza. Mude o tipo da conta no Instagram e conecte de novo.");
      return { conta_id: String(me.user_id), conta_nome: me.username, conta_foto: me.profile_picture_url ?? null,
               access_token: longo.access_token, refresh_token: null, expira_em: emSegundos(longo.expires_in) };
    },
  },
};

// ---------- "state": prova assinada de quem pediu a conexão (evita alguém conectar a conta dele em outro usuário)
const b64 = (b: ArrayBuffer | Uint8Array) => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const de64 = (s: string) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
const txt = (s: string) => new TextEncoder().encode(s);
const chave = () => crypto.subtle.importKey("raw", txt(env("ESTADO_SEGREDO") || SB_KEY), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
async function assinar(dados: object) {
  const corpo = b64(txt(JSON.stringify(dados)));
  return `${corpo}.${b64(await crypto.subtle.sign("HMAC", await chave(), txt(corpo)))}`;
}
type Estado = { u: string; p: string; s: string; exp: number };
async function conferir(state: string): Promise<Estado | null> {
  try {  // state vem de fora: qualquer coisa malformada vira "inválido", não erro 500
    const [corpo, sig] = state.split(".");
    if (!corpo || !sig) return null;
    if (!await crypto.subtle.verify("HMAC", await chave(), de64(sig), txt(corpo))) return null;  // comparação em tempo constante
    const d = JSON.parse(new TextDecoder().decode(de64(corpo)));
    return d.exp > Date.now() && REDES[d.p] ? d : null;
  } catch {
    return null;
  }
}

const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info", "Access-Control-Allow-Methods": "POST, OPTIONS" };
const resposta = (d: object, status = 200) => new Response(JSON.stringify(d), { status, headers: { ...CORS, "Content-Type": "application/json" } });
const voltar = (site: string, q: Record<string, string>) => Response.redirect(`${site}/app/conexoes?${new URLSearchParams(q)}`, 302);

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });

  if (req.method === "POST") {
    const jwt = (req.headers.get("Authorization") || "").replace(/^Bearer /, "");
    const user = jwt ? await usuario(jwt) : null;
    if (!user?.id) return resposta({ erro: "Faça login de novo." }, 401);
    const { plataforma, code, state: stRecebido } = await req.json().catch(() => ({}));

    // 3) o site devolve o código da rede, já com o login de quem está na tela
    if (code) {
      const st = await conferir(stRecebido || "");
      if (!st) return resposta({ erro: "Link de conexão inválido ou expirado. Tente de novo." }, 400);
      if (st.u !== user.id) return resposta({ erro: "Essa conexão foi iniciada por outra conta do Viraliza. Clique em Conectar de novo.", p: st.p }, 403);
      try {
        const conta = await REDES[st.p].trocar(String(code).replace(/#_$/, ""), volta(st.p, st.s));
        const con = await upsert("conexoes", "user_id,plataforma", {
          user_id: st.u, plataforma: st.p, conta_id: conta.conta_id, conta_nome: conta.conta_nome, conta_foto: conta.conta_foto,
        });
        await upsert("conexoes_tokens", "conexao_id", {
          conexao_id: con.id, access_token: conta.access_token, refresh_token: conta.refresh_token, expira_em: conta.expira_em,
        });
        return resposta({ ok: st.p, conta: conta.conta_nome });
      } catch (e) {
        console.error(st.p, e);
        return resposta({ erro: String((e as Error).message || e).slice(0, 300), p: st.p }, 400);
      }
    }

    // 1) o painel pede a URL de login da rede
    const rede = REDES[plataforma];
    if (!rede) return resposta({ erro: "Plataforma inválida." }, 400);
    const origem = (req.headers.get("Origin") || "").replace(/\/$/, "");
    const site = SITES.includes(origem) ? origem : SITES[0];
    const state = await assinar({ u: user.id, p: plataforma, s: site, exp: Date.now() + 15 * 60_000, n: crypto.randomUUID() });
    return resposta({ url: `${rede.auth}?${new URLSearchParams({ ...rede.params(), redirect_uri: volta(plataforma, site), state })}` });
  }

  // 2) a rede devolve o usuário pra cá: só repassa pro site, que termina no passo 3 com o login
  if (req.method === "GET") {
    const q = new URL(req.url).searchParams, state = q.get("state") || "";
    const st = await conferir(state);
    if (!st) return new Response("Link de conexão inválido ou expirado. Volte ao Viraliza e tente de novo.", { status: 400 });
    if (q.get("error") || !q.get("code")) return voltar(st.s, { erro: "Você cancelou a conexão.", p: st.p });
    return voltar(st.s, { code: q.get("code")!, state });
  }
  return resposta({ erro: "Método não suportado." }, 405);
});
