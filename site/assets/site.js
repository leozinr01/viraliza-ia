/* ================= VIRALIZA · animações do site ================= */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const rand = (a, b) => a + Math.random() * (b - a);
  const pick = a => a[Math.floor(Math.random() * a.length)];
  const reduz = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fmtMil = v => v.toFixed(1).replace('.', ',') + ' mil';
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };

  /* nav fica sólida ao rolar */
  const nav = $('#nav');
  const navCheck = () => nav && nav.classList.toggle('solid', scrollY > 10);
  addEventListener('scroll', navCheck, { passive: true }); navCheck();

  /* brilho que segue o mouse */
  if (!reduz && matchMedia('(pointer:fine)').matches && $('.hero')) {
    const g = el('div', 'glow-cursor'); document.body.appendChild(g);
    addEventListener('pointermove', e => { g.style.transform = `translate(${e.clientX}px,${e.clientY + scrollY}px)`; g.style.position = 'absolute'; }, { passive: true });
  }

  /* botões magnéticos */
  if (!reduz) $$('.magnet').forEach(b => {
    b.addEventListener('pointermove', e => {
      const r = b.getBoundingClientRect();
      b.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * .18}px,${(e.clientY - r.top - r.height / 2) * .3}px)`;
    });
    b.addEventListener('pointerleave', () => b.style.transform = '');
  });

  /* ---------- palavra que gira no título ---------- */
  const rot = $('#rot');
  if (rot && !reduz) {
    const palavras = ['viral.', 'TikTok.', 'Shorts.', 'Reels.', 'conteúdo.', 'grana.'];
    let i = 0;
    setInterval(() => {
      rot.firstElementChild.classList.add('out');
      setTimeout(() => { i = (i + 1) % palavras.length; rot.innerHTML = `<span class="grad">${palavras[i]}</span>`; }, 330);
    }, 2400);
  }

  /* ---------- legenda palavra por palavra ---------- */
  function karaoke(alvo, frases, ms = 340) {
    if (!alvo) return () => {};
    let words = [], w = -1, f = 0, timer;
    const montar = t => { words = t.split(' '); alvo.innerHTML = words.map(x => `<span>${x}</span>`).join(' '); w = -1; };
    const passo = () => {
      w++;
      if (w >= words.length + 3) { f = (f + 1) % frases.length; montar(frases[f]); }
      $$('span', alvo).forEach((s, k) => s.classList.toggle('on', k === w));
    };
    montar(frases[0]);
    timer = setInterval(passo, ms);
    return t => { montar(t); };
  }

  /* ---------- pessoas e comentários (fictícios, pra demonstração) ---------- */
  const GENTE = [['bia.gta', '#ff7ab6'], ['rafa_vc', '#7cc4ff'], ['zeca777', '#ffd166'], ['mlkdoido', '#9effa0'], ['gabs.tv', '#c8a2ff'], ['nanda.games', '#ff9f6b'], ['duda_rp', '#6bf0ff'], ['xandao', '#ffb3c4']];
  const COMENTARIOS = ['kkkkkkkk o carro voou 😭', 'como que tu sai vivo disso', 'live lendária demais', 'parte 2 pfv 🙏', 'vim pelo corte, fiquei pela live',
    'o chat surtou nessa kkk', 'esse jogo tá absurdo', 'salvei pra mostrar pros amigos', 'cadê o link da live??', 'isso merecia 1 milhão de views',
    'eu gritei junto 💀', 'a reação no final kkkkk', 'GTA 6 tá outro nível', 'segue que esse cara é brabo'];

  /* ---------- cena desenhada: cidade neon com carro andando ---------- */
  const PALM = '<svg viewBox="0 0 60 100"><path d="M29 100c2-25 3-45 1-62l3 0c3 18 2 38-1 62z"/><path d="M31 38C20 25 8 26 0 34c10-3 20-2 29 6zM31 38c4-15 14-22 26-22-10 4-18 11-23 23zM31 38C28 22 18 14 6 15c10 4 18 12 22 24zM31 38c10-8 22-7 29 1-10-3-19-2-27 3z"/></svg>';
  const CAR = '<svg viewBox="0 0 200 70"><defs><linearGradient id="cg" x1="0" x2="1"><stop offset="0" stop-color="#ff2e63"/><stop offset="1" stop-color="#ff9f1c"/></linearGradient></defs><path d="M10 48c0-8 4-14 14-16l34-6 22-14c6-4 12-5 20-5h36c9 0 15 3 21 9l16 14 14 3c6 1 9 5 9 11v8H10z" fill="url(#cg)"/><path d="M84 26l18-11c3-2 6-2 9-2h20l2 13zM139 26l-2-13h6c5 0 9 2 12 5l9 8z" fill="#2a0b3b" opacity=".85"/><rect x="176" y="40" width="14" height="5" rx="2" fill="#fff6c2"/><circle cx="52" cy="56" r="12" fill="#0b0310"/><circle cx="52" cy="56" r="5" fill="#666"/><circle cx="152" cy="56" r="12" fill="#0b0310"/><circle cx="152" cy="56" r="5" fill="#666"/></svg>';
  function predios(cls, n, min, max) {
    let h = '';
    for (let k = 0; k < 2; k++) for (let i = 0; i < n; i++)
      h += `<i${Math.random() < .2 ? ' class="ant"' : ''} style="height:${rand(min, max).toFixed(0)}%;flex:${rand(.6, 1.6).toFixed(2)}"></i>`;
    return `<div class="city ${cls}">${h}</div>`;
  }
  function cena(tall) {
    return '<div class="sky"></div><div class="stars"></div><div class="sun"></div>' +
      predios('far', tall ? 10 : 18, 30, 100) + predios('near', tall ? 8 : 14, 20, 80) +
      `<div class="palms">${PALM.repeat(tall ? 4 : 8)}</div><div class="road"></div><div class="car">${CAR}</div><div class="flashbang"></div>`;
  }
  $$('[data-scene]').forEach(e => {
    if (e.dataset.hue) e.style.setProperty('--hue', e.dataset.hue + 'deg');
    e.innerHTML = cena(e.dataset.scene === 'tall');
  });

  /* ---------- feed do celular ---------- */
  const CLIPS = [
    { hue: 0, cap: 'mano ele tá vindo a 300 por hora', desc: 'fuga a 300 por hora 🏎️ #gta6 #fyp', likes: 12.4, coms: 842, n: 7 },
    { hue: 40, cap: 'olha o tamanho desse assalto chat', desc: 'o assalto na Ocean Drive 💰 #gta6', likes: 31.9, coms: 2103, n: 8 },
    { hue: -50, cap: 'perdi eles na curva kkkkk', desc: 'a polícia ficou pra trás 🚔 #gta6', likes: 8.7, coms: 391, n: 9 },
    { hue: 160, cap: 'eu não acredito que pulei daqui', desc: 'pulou do prédio kkkk 💀 #gta6', likes: 54.2, coms: 4870, n: 10 },
  ];
  $$('.feed').forEach(feed => {
    const screen = feed.closest('.screen');
    let i = 0, atual = null, likes = CLIPS[0].likes;
    const cap = el('div', 'cap'); screen.appendChild(cap);
    const setCap = karaoke(cap, CLIPS.map(c => c.cap), 300);
    const prog = $('#phProg', screen) || $('.ph-prog i', screen);
    function mostrar(k, primeira) {
      const c = CLIPS[k];
      const s = el('div', 'slide' + (primeira ? '' : ' prox'), `<div class="scene" style="--hue:${c.hue}deg">${cena(true)}</div>`);
      feed.appendChild(s);
      requestAnimationFrame(() => requestAnimationFrame(() => {
        s.classList.remove('prox');
        if (atual) { const velho = atual; velho.classList.add('sai'); setTimeout(() => velho.remove(), 800); }
        atual = s;
      }));
      setCap(c.cap);
      likes = c.likes;
      const d = $('#phDesc', screen); if (d) d.textContent = c.desc;
      const cm = $('#coms', screen); if (cm) cm.textContent = c.coms.toLocaleString('pt-BR');
      const lk = $('#likes', screen); if (lk) lk.textContent = fmtMil(likes);
      const n = $('#clipN'); if (n) n.textContent = '#' + c.n;
      if (prog) { prog.style.animation = 'none'; void prog.offsetWidth; prog.style.animation = 'prog 6s linear forwards'; }
    }
    mostrar(0, true);
    if (!reduz) setInterval(() => { i = (i + 1) % CLIPS.length; mostrar(i); }, 6000);

    // comentários subindo na tela + coração
    const box = $('.ph-comments', screen);
    if (box && !reduz) setInterval(() => {
      const [u, c] = pick(GENTE);
      const p = el('div', 'pc'); p.style.setProperty('--c', c);
      p.innerHTML = `<i></i><span><b>${u}</b>${pick(COMENTARIOS)}</span>`;
      box.appendChild(p); while (box.children.length > 5) box.firstChild.remove();
      likes += rand(.1, .5); const lk = $('#likes', screen); if (lk) lk.textContent = fmtMil(likes);
      const h = $('#heart', screen); if (h) { h.classList.remove('pop'); void h.offsetWidth; h.classList.add('pop'); }
    }, 1500);
  });

  /* ---------- palco do hero (live, chat, gráfico) ---------- */
  const stage = $('#stage');
  if (stage) {
    if (!reduz) addEventListener('mousemove', e => {
      stage.style.setProperty('--mx', ((e.clientX / innerWidth) - .5).toFixed(3));
      stage.style.setProperty('--my', ((e.clientY / innerHeight) - .5).toFixed(3));
    });
    const chat = $('#chat'), spark = $('#spark'), tag = $('#spikeTag');
    const calmos = ['boa noite rapaziada', 'vai roubar o banco?', 'que carro é esse', 'salve salve', 'primeira vez aqui', 'vai de helicóptero', 'gg', 'que gráfico mano'];
    const hype = ['KKKKKKKKKKK', 'clipa isso 😭', 'mds 😱😱', 'não acredito', 'KEKW KEKW', '#corte', 'absurdo', 'que isso mano'];
    const pts = Array(40).fill(8);
    let quente = 0, views = 48.2, viewers = 1284, tick = 0;
    const msg = () => {
      const [u, c] = pick(GENTE), h = quente > 0;
      const d = el('div', null, `<b style="color:${c}">${u}</b>: <span class="${h ? 'hype' : ''}">${h ? pick(hype) : pick(calmos)}</span>`);
      chat.appendChild(d); while (chat.children.length > 14) chat.firstChild.remove();
    };
    const graf = () => {
      pts.shift(); pts.push(quente > 0 ? rand(30, 42) : rand(4, 14));
      spark.setAttribute('d', pts.map((v, i) => `${i ? 'L' : 'M'}${(i / (pts.length - 1) * 300).toFixed(1)} ${(44 - v).toFixed(1)}`).join(' '));
    };
    const pico = () => {
      quente = 9; tag.classList.add('on');
      const v = $('.lw-video'); v.classList.remove('boom'); void v.offsetWidth; v.classList.add('boom');
      setTimeout(() => { const f = $('.fly-clip'); f.classList.remove('go'); void f.offsetWidth; f.classList.add('go'); }, 700);
      setTimeout(() => {
        $$('.chip.c1,.chip.c2').forEach(c => { c.classList.remove('ping'); void c.offsetWidth; c.classList.add('ping'); });
        views += rand(3, 9); $('#views').textContent = fmtMil(views);
      }, 1750);
      setTimeout(() => tag.classList.remove('on'), 3200);
    };
    for (let i = 0; i < 10; i++) { msg(); graf(); }
    // título da live muda de tempos em tempos
    const titulo = $('#lwTitle');
    const TITULOS = ['roubo na praia 💰', 'conhecendo o mapa inteiro 🗺️', 'vivendo a vida de namorado com a Lucia 💕', 'fuga pela Ocean Drive 🚔',
      'comprando a primeira mansão 🏝️', 'corrida ilegal na madrugada 🏎️', 'fugindo da polícia de lancha 🚤', 'zerando missões com o chat 🎮',
      'procurando easter eggs 👀', 'assalto ao banco de Vice City 🏦'];
    let ti = 0;
    if (titulo && !reduz) setInterval(() => {
      let n; do { n = Math.floor(Math.random() * TITULOS.length); } while (n === ti);
      ti = n;
      titulo.classList.add('troca');
      setTimeout(() => { titulo.textContent = 'GTA 6 · ' + TITULOS[ti]; titulo.classList.remove('troca'); }, 300);
    }, 4200);
    if (!reduz) setInterval(() => {
      tick++; if (quente > 0) quente--;
      msg(); if (quente > 0) msg(); graf();
      if (tick % 3 === 0) { viewers += Math.round(rand(-4, 12)); $('#viewers').textContent = viewers.toLocaleString('pt-BR'); }
      if (tick % 16 === 4) pico();
    }, 380);
  }

  /* ---------- VOD: onda com picos ---------- */
  const wave = $('#wave');
  if (wave) {
    const N = innerWidth < 640 ? 70 : 140, picos = [0.17, 0.32, 0.52, 0.87], nomes = ['🔥 0:42', '🔥 1:17', '⭐ #corte', '🔥 3:31'];
    let h = '';
    for (let i = 0; i < N; i++) {
      const x = i / N, perto = picos.some(p => Math.abs(p - x) < 0.012);
      const alt = perto ? rand(80, 100) : 12 + 30 * Math.abs(Math.sin(i * .37)) * Math.random() + rand(0, 14);
      h += `<i class="${perto ? 'pk' : ''}" style="--h:${alt.toFixed(0)}%;--t:${(x * 1.3).toFixed(2)}s"></i>`;
    }
    h += '<div class="scan"></div>' + picos.map((p, k) => `<span class="mk" style="left:${p * 100}%;--t:${(p * 1.3).toFixed(2)}s">${nomes[k]}</span>`).join('');
    wave.innerHTML = h;
  }

  /* ---------- card de comentários ---------- */
  karaoke($('#karaoke'), ['mano ele não viu o carro vindo', 'o chat inteiro gritou junto', 'clipa isso agora pelo amor']);
  const comList = $('#comList');
  if (comList) {
    const add = () => {
      const [u, c] = pick(GENTE), top = Math.random() < .3;
      const d = el('div', 'cm' + (top ? ' top' : ''), `<i style="--c:${c}"></i><div><b>${u}</b>${pick(COMENTARIOS)}</div><small>${Math.round(rand(12, top ? 4800 : 900)).toLocaleString('pt-BR')}</small>`);
      comList.appendChild(d); while (comList.children.length > 6) comList.firstChild.remove();
    };
    for (let i = 0; i < 4; i++) add();
    if (!reduz) setInterval(add, 2200);
  }

  /* ---------- digitação ---------- */
  $$('.typed').forEach(e => {
    const txt = e.dataset.type; let i = 0;
    setInterval(() => { i = i > txt.length + 12 ? 0 : i + 1; e.textContent = txt.slice(0, i); }, 90);
  });

  /* ---------- barras de detecção ---------- */
  const bars = $('#bars');
  if (bars) {
    bars.innerHTML = '<i></i>'.repeat(22);
    const bs = $$('i', bars);
    const mexe = () => {
      const p = Math.floor(rand(4, 18));
      bs.forEach((b, k) => { const d = Math.abs(k - p); b.style.height = (d < 2 ? rand(80, 100) : rand(12, 45)) + '%'; b.classList.toggle('hot', d < 2); });
    };
    mexe(); setInterval(mexe, 1600);
  }


  /* ---------- brilho nos cards ---------- */
  $$('.cell').forEach(c => c.addEventListener('pointermove', e => {
    const r = c.getBoundingClientRect();
    c.style.setProperty('--x', (e.clientX - r.left) + 'px'); c.style.setProperty('--y', (e.clientY - r.top) + 'px');
  }));

  /* ---------- revelar ao rolar + contadores ---------- */
  const conta = e => {
    const alvo = +e.dataset.count, t0 = performance.now();
    if (!alvo) { e.textContent = '0'; return; }
    const step = t => { const p = Math.min(1, (t - t0) / 1400); e.textContent = Math.round(alvo * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  };
  $$('.hero [data-count]').forEach(conta);
  const io = new IntersectionObserver(es => es.forEach(e => {
    if (!e.isIntersecting) return;
    e.target.classList.add('in');
    $$('[data-count]', e.target).forEach(conta);
    io.unobserve(e.target);
  }), { threshold: .2 });
  $$('.reveal').forEach(x => io.observe(x));
})();
