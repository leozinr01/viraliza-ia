/* ================= VIRALIZA · animações ================= */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const rand = (a, b) => a + Math.random() * (b - a);
  const reduz = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* nav fica sólida ao rolar */
  const nav = $('#nav');
  const navCheck = () => nav && nav.classList.toggle('solid', scrollY > 10);
  addEventListener('scroll', navCheck, { passive: true }); navCheck();

  /* ---------- cena: cidade neon ---------- */
  const PALM = '<svg viewBox="0 0 60 100"><path d="M29 100c2-25 3-45 1-62l3 0c3 18 2 38-1 62z"/><path d="M31 38C20 25 8 26 0 34c10-3 20-2 29 6zM31 38c4-15 14-22 26-22-10 4-18 11-23 23zM31 38C28 22 18 14 6 15c10 4 18 12 22 24zM31 38c10-8 22-7 29 1-10-3-19-2-27 3z"/></svg>';
  const CAR = '<svg viewBox="0 0 200 70"><defs><linearGradient id="cg" x1="0" x2="1"><stop offset="0" stop-color="#ff2e63"/><stop offset="1" stop-color="#ff9f1c"/></linearGradient></defs><path d="M10 48c0-8 4-14 14-16l34-6 22-14c6-4 12-5 20-5h36c9 0 15 3 21 9l16 14 14 3c6 1 9 5 9 11v8H10z" fill="url(#cg)"/><path d="M84 26l18-11c3-2 6-2 9-2h20l2 13zM139 26l-2-13h6c5 0 9 2 12 5l9 8z" fill="#2a0b3b" opacity=".85"/><rect x="176" y="40" width="14" height="5" rx="2" fill="#fff6c2"/><circle cx="52" cy="56" r="12" fill="#0b0310"/><circle cx="52" cy="56" r="5" fill="#666"/><circle cx="152" cy="56" r="12" fill="#0b0310"/><circle cx="152" cy="56" r="5" fill="#666"/></svg>';

  function cidade(cls, n, min, max) {
    let h = '';
    for (let k = 0; k < 2; k++) for (let i = 0; i < n; i++) {
      const alt = rand(min, max), ant = Math.random() < .2 ? ' class="ant"' : '';
      h += `<i${ant} style="height:${alt.toFixed(0)}%;flex:${rand(.6, 1.6).toFixed(2)}"></i>`;
    }
    return `<div class="city ${cls}">${h}</div>`;
  }
  $$('[data-scene]').forEach(el => {
    const tall = el.dataset.scene === 'tall';
    if (el.dataset.hue) el.style.setProperty('--hue', el.dataset.hue + 'deg');
    el.innerHTML = '<div class="sky"></div><div class="stars"></div><div class="sun"></div>' +
      cidade('far', tall ? 10 : 18, 30, 100) + cidade('near', tall ? 8 : 14, 20, 80) +
      `<div class="palms">${PALM.repeat(tall ? 4 : 8)}</div>` +
      `<div class="road"></div><div class="car">${CAR}</div><div class="flashbang"></div>`;
  });

  /* ---------- palavra que gira no título ---------- */
  const rot = $('#rot');
  if (rot && !reduz) {
    const palavras = ['viral.', 'TikTok.', 'Shorts.', 'Reels.', 'conteúdo.', 'grana.'];
    let i = 0;
    setInterval(() => {
      const atual = rot.firstElementChild;
      atual.classList.add('out');
      setTimeout(() => {
        i = (i + 1) % palavras.length;
        rot.innerHTML = `<span class="grad">${palavras[i]}</span>`;
      }, 330);
    }, 2400);
  }

  /* ---------- legenda karaokê ---------- */
  function karaoke(el, frases, ms = 380) {
    if (!el) return;
    let f = 0, w = -1, words = [];
    const montar = () => { words = frases[f].split(' '); el.innerHTML = words.map(x => `<span>${x}</span>`).join(' '); };
    montar();
    setInterval(() => {
      w++;
      if (w >= words.length + 2) { w = -1; f = (f + 1) % frases.length; montar(); return; }
      $$('span', el).forEach((s, k) => s.classList.toggle('on', k === w));
    }, ms);
  }
  karaoke($('#caption'), ['QUANDO O PLANO DÁ ERRADO', 'OLHA ISSO CHAT', 'NÃO ACREDITO KKKK', 'FOI DE BASE 💀']);
  karaoke($('#karaoke'), ['MANO ELE NÃO VIU', 'O CARRO VOOU KKKKK', 'CLIPA ISSO AGORA']);

  /* ---------- palco do hero ---------- */
  const stage = $('#stage');
  if (stage) {
    // parallax com o mouse
    if (!reduz) addEventListener('mousemove', e => {
      stage.style.setProperty('--mx', ((e.clientX / innerWidth) - .5).toFixed(3));
      stage.style.setProperty('--my', ((e.clientY / innerHeight) - .5).toFixed(3));
    });

    const chat = $('#chat'), spark = $('#spark'), tag = $('#spikeTag');
    const users = [['gabsz', '#ff7ab6'], ['mlk_doido', '#7cc4ff'], ['tetinha99', '#ffd166'], ['rafa.gta', '#9effa0'], ['xandao', '#c8a2ff'], ['bia_lol', '#ff9f6b'], ['zeca777', '#6bf0ff']];
    const calmos = ['boa noite rapaziada', 'vai roubar o banco?', 'que carro é esse', 'salve salve', 'primeira vez aqui', 'vai de helicóptero', 'joga com fone?', 'gg'];
    const hype = ['KKKKKKKKKKK', 'CLIPA ISSO', 'MDS 😱😱', 'NÃO ACREDITO', 'KEKW KEKW', '#corte', 'ABSURDO', 'QUE ISSO MANO'];
    const pts = Array(40).fill(8);
    let quente = 0, likes = 12.4, views = 48.2, viewers = 1284;

    function msg() {
      const [u, c] = users[Math.floor(Math.random() * users.length)];
      const h = quente > 0, t = h ? hype[Math.floor(Math.random() * hype.length)] : calmos[Math.floor(Math.random() * calmos.length)];
      const d = document.createElement('div');
      d.innerHTML = `<b style="color:${c}">${u}</b>: <span class="${h ? 'hype' : ''}">${t}</span>`;
      chat.appendChild(d);
      while (chat.children.length > 14) chat.firstChild.remove();
    }
    function graf() {
      pts.shift();
      pts.push(quente > 0 ? rand(30, 42) : rand(4, 14));
      spark.setAttribute('d', pts.map((v, i) => `${i ? 'L' : 'M'}${(i / (pts.length - 1) * 300).toFixed(1)} ${(44 - v).toFixed(1)}`).join(' '));
    }
    function pico() {
      quente = 9;
      tag.classList.add('on');
      $$('[data-scene="wide"]').forEach(s => { s.classList.remove('boom'); void s.offsetWidth; s.classList.add('boom'); });
      setTimeout(() => {
        const f = $('.fly-clip'); f.classList.remove('go'); void f.offsetWidth; f.classList.add('go');
      }, 700);
      setTimeout(() => {
        const sc = $('.phone .screen'); sc.classList.remove('flash'); void sc.offsetWidth; sc.classList.add('flash');
        $$('.chip.c1,.chip.c2').forEach(c => { c.classList.remove('ping'); void c.offsetWidth; c.classList.add('ping'); });
        views += rand(3, 9); $('#views').textContent = '+' + views.toFixed(1).replace('.', ',') + ' mil';
      }, 1750);
      setTimeout(() => tag.classList.remove('on'), 3200);
    }
    let tick = 0;
    setInterval(() => {
      tick++;
      if (quente > 0) quente--;
      msg(); if (quente > 0) msg();
      graf();
      if (tick % 3 === 0) { viewers += Math.round(rand(-4, 12)); $('#viewers').textContent = viewers.toLocaleString('pt-BR'); }
      if (tick % 4 === 0) {
        likes += rand(.1, .4); $('#likes').textContent = likes.toFixed(1).replace('.', ',') + ' mil';
        const h = $('#heart'); h.classList.remove('pop'); void h.offsetWidth; h.classList.add('pop');
      }
      if (tick % 22 === 6) pico();
    }, 380);
    for (let i = 0; i < 10; i++) { msg(); graf(); }
  }

  /* ---------- digitação ---------- */
  $$('.typed').forEach(el => {
    const txt = el.dataset.type; let i = 0;
    setInterval(() => { i = i > txt.length + 12 ? 0 : i + 1; el.textContent = txt.slice(0, i); }, 90);
  });

  /* ---------- barras de detecção ---------- */
  const bars = $('#bars');
  if (bars) {
    bars.innerHTML = '<i></i>'.repeat(22);
    const bs = $$('i', bars);
    const mexe = () => {
      const pico = Math.floor(rand(4, 18));
      bs.forEach((b, k) => {
        const d = Math.abs(k - pico), h = d < 2 ? rand(80, 100) : rand(12, 45);
        b.style.height = h + '%'; b.classList.toggle('hot', d < 2);
      });
    };
    mexe(); setInterval(mexe, 1600);
  }

  /* ---------- brilho que segue o mouse nos cards ---------- */
  $$('.cell').forEach(c => c.addEventListener('pointermove', e => {
    const r = c.getBoundingClientRect();
    c.style.setProperty('--x', (e.clientX - r.left) + 'px');
    c.style.setProperty('--y', (e.clientY - r.top) + 'px');
  }));

  /* ---------- revelar ao rolar + contadores ---------- */
  const conta = el => {
    const alvo = +el.dataset.count, suf = el.dataset.suf || '', t0 = performance.now();
    const step = t => { const p = Math.min(1, (t - t0) / 1400), v = Math.round(alvo * (1 - Math.pow(1 - p, 3))); el.textContent = v + suf; if (p < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  };
  const io = new IntersectionObserver(es => es.forEach(e => {
    if (!e.isIntersecting) return;
    e.target.classList.add('in');
    $$('[data-count]', e.target).forEach(conta);
    io.unobserve(e.target);
  }), { threshold: .15 });
  $$('.reveal').forEach(el => io.observe(el));

})();
