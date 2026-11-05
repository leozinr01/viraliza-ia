/* Viraliza · cliente do Supabase + utilidades comuns */
window.VZ = (() => {
  const sb = supabase.createClient(VIRALIZA_CONFIG.supabaseUrl, VIRALIZA_CONFIG.supabaseKey, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true }
  });

  async function sessao() {
    const { data } = await sb.auth.getSession();
    return data.session;
  }

  /* mostra/esconde itens do topo conforme o login */
  async function ajustarNav() {
    const s = await sessao();
    document.querySelectorAll('[data-auth]').forEach(e => e.hidden = !s);
    document.querySelectorAll('[data-anon]').forEach(e => e.hidden = !!s);
  }
  document.addEventListener('DOMContentLoaded', ajustarNav);

  /* páginas do painel chamam isso: sem login, manda pro /entrar */
  async function exigirLogin() {
    const s = await sessao();
    if (!s) { location.replace('/entrar?proximo=' + encodeURIComponent(location.pathname + location.search)); throw new Error('sem login'); }
    return s;
  }

  async function sair() { await sb.auth.signOut(); location.href = '/'; }

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function toast(t) {
    let e = document.getElementById('toast');
    if (!e) { e = document.createElement('div'); e.id = 'toast'; document.body.appendChild(e); }
    e.textContent = t; e.classList.add('show'); clearTimeout(e._t); e._t = setTimeout(() => e.classList.remove('show'), 2400);
  }

  /* traduz erros comuns do Supabase */
  function erroPt(err) {
    const m = (err && (err.message || err.error_description)) || String(err || '');
    const mapa = [
      [/invalid login credentials/i, 'E-mail ou senha incorretos.'],
      [/email not confirmed/i, 'Confirme seu e-mail antes de entrar. Veja sua caixa de entrada.'],
      [/user already registered/i, 'Já existe uma conta com esse e-mail. Faça login.'],
      [/password should be at least/i, 'A senha precisa ter pelo menos 8 caracteres.'],
      [/rate limit|too many/i, 'Muitas tentativas. Espere um minuto e tente de novo.'],
      [/unable to validate email|invalid.*email/i, 'Esse e-mail não parece válido.'],
      [/lives_fonte_check/i, 'Cole o link de um VOD da Twitch, YouTube ou Kick.'],
      [/failed to fetch|network/i, 'Sem conexão. Confira sua internet.'],
    ];
    for (const [re, t] of mapa) if (re.test(m)) return t;
    return 'Algo deu errado: ' + m;
  }

  return { sb, sessao, exigirLogin, sair, esc, toast, erroPt };
})();
