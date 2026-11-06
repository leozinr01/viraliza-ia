// Viraliza · formulário de contato: salva a mensagem no banco e manda por e-mail pra empresa (via Resend).
//
//  POST { nome, email, assunto, mensagem, site }   ("site" é um campo escondido: se vier preenchido, é robô)
//
// Segredos (Supabase > Edge Functions > Secrets):
//   RESEND_API_KEY   chave do resend.com
//   CONTATO_PARA     pra onde vão as mensagens (padrão mail@valoriza.online)
//   CONTATO_DE       remetente, de um domínio verificado no Resend (ex.: "Viraliza <contato@valoriza.online>")
//
// Deploy:  npx supabase functions deploy contato --no-verify-jwt
// (sem verificação de login: quem manda mensagem normalmente não tem conta)
const env = (k: string) => Deno.env.get(k) ?? "";
const SB_URL = env("SUPABASE_URL");
const SB_KEY = env("SB_SECRET_KEY") || (() => { try { return Object.values(JSON.parse(env("SUPABASE_SECRET_KEYS")))[0] as string; } catch { return ""; } })()
  || env("SUPABASE_SERVICE_ROLE_KEY");
const PARA = env("CONTATO_PARA") || "mail@valoriza.online";
const DE = env("CONTATO_DE") || "Viraliza <onboarding@resend.dev>";
const ASSUNTOS = ["Dúvida", "Sugestão", "Parceria", "Problema técnico", "Outro"];

const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info", "Access-Control-Allow-Methods": "POST, OPTIONS" };
const resposta = (d: object, status = 200) => new Response(JSON.stringify(d), { status, headers: { ...CORS, "Content-Type": "application/json" } });
const limpa = (v: unknown, max: number) => String(v ?? "").replace(/\r\n?/g, "\n").trim().slice(0, max);

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  if (req.method !== "POST") return resposta({ erro: "Método não suportado." }, 405);

  const b = await req.json().catch(() => ({}));
  if (b.site) return resposta({ ok: true });  // robô: finge que deu certo e não faz nada
  const nome = limpa(b.nome, 120).replace(/\s+/g, " "), email = limpa(b.email, 200), mensagem = limpa(b.mensagem, 5000);
  const assunto = ASSUNTOS.includes(b.assunto) ? b.assunto : "Outro";
  if (!nome || !mensagem) return resposta({ erro: "Preencha nome e mensagem." }, 400);
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return resposta({ erro: "Confira o seu e-mail." }, 400);

  // 1) guarda no banco (assim nada se perde, mesmo se o e-mail falhar)
  const r = await fetch(`${SB_URL}/rest/v1/contatos`, {
    method: "POST", body: JSON.stringify({ nome, email, assunto, mensagem }),
    headers: { apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}`, "Content-Type": "application/json", Prefer: "return=minimal" },
  });
  if (!r.ok) { console.error("contatos", await r.text()); return resposta({ erro: "Não deu pra enviar agora. Tente de novo." }, 500); }

  // 2) manda pro e-mail da empresa; "responder" vai direto pra pessoa
  if (!env("RESEND_API_KEY")) { console.error("RESEND_API_KEY não configurada: mensagem só ficou no banco"); return resposta({ ok: true }); }
  const m = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${env("RESEND_API_KEY")}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: DE, to: [PARA], reply_to: email,
      subject: `[Contato] ${assunto} · ${nome}`.slice(0, 200),
      text: `${mensagem}\n\n—\nNome: ${nome}\nE-mail: ${email}\nAssunto: ${assunto}\n\n(Responda este e-mail para falar direto com a pessoa.)`,
    }),
  });
  if (!m.ok) console.error("resend", m.status, await m.text());  // a mensagem já está salva no banco
  return resposta({ ok: true });
});
