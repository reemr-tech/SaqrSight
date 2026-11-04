'use strict';
// SaqrSight motion layer: GSAP (+ScrollTrigger, SplitText) and Lenis smooth scrolling.
// Effects inspired by React Bits (SplitText, BlurText, Aurora, SpotlightCard), written in plain JS.
// Everything degrades to a static page if the libraries are missing or the user prefers reduced motion.
(function () {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ok = !!(window.gsap && window.ScrollTrigger && window.SplitText) && !reduce;
  const noop = () => {};
  const api = { ok, view: noop, text: noop, report: noop, enter: noop };
  window.Motion = api;
  document.documentElement.classList.toggle('motion', ok);
  initSpotlight();            // pointer glow is cheap and harmless, keep it even without GSAP
  if (!ok) { initAurora(true); return; }

  gsap.registerPlugin(ScrollTrigger, SplitText);

  // ---------- smooth scrolling ----------
  const lenis = new Lenis({ lerp: 0.09, smoothWheel: true });
  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add(t => lenis.raf(t * 1000));
  gsap.ticker.lagSmoothing(0);

  const isArabic = el => document.documentElement.dir === 'rtl' || /[؀-ۿ]/.test(el.textContent);
  const splits = new WeakMap();
  // Undo a previous split, unless the element's content was replaced since (e.g. a language switch):
  // reverting then would restore the old text.
  function resetSplit(el) {
    const prev = splits.get(el);
    if (prev && el.textContent === prev.text) prev.s.revert();
    splits.delete(el);
  }

  // ---------- SplitText heading reveal (React Bits "SplitText") ----------
  function splitReveal(el, delay = 0) {
    if (!el || !el.offsetParent) return;
    resetSplit(el);
    const arabic = isArabic(el);   // splitting Arabic into letters breaks letter joining: use words
    const s = SplitText.create(el, { type: arabic ? 'words' : 'words,chars', mask: arabic ? 'words' : 'chars' });
    splits.set(el, { s, text: el.textContent });
    gsap.from(arabic ? s.words : s.chars, {
      yPercent: 110, opacity: 0, rotate: arabic ? 0 : 4, duration: 0.9, ease: 'expo.out',
      stagger: arabic ? 0.06 : 0.018, delay,
    });
  }

  // ---------- blur-in text (React Bits "BlurText") ----------
  function blurIn(el, delay = 0) {
    if (!el || !el.offsetParent || !el.textContent.trim()) return;
    resetSplit(el);
    const s = SplitText.create(el, { type: 'words' });
    splits.set(el, { s, text: el.textContent });
    gsap.from(s.words, { filter: 'blur(10px)', opacity: 0, y: 8, duration: 0.8, ease: 'power3.out', stagger: 0.035, delay });
  }

  // ---------- staggered entrance for cards, batched on scroll ----------
  function enter(nodes, opts = {}) {
    nodes = gsap.utils.toArray(nodes).filter(n => n && n.offsetParent);
    if (!nodes.length) return;
    const show = batch => gsap.to(batch, { opacity: 1, y: 0, duration: 0.8, ease: 'power3.out', stagger: 0.07,
      delay: opts.delay || 0, overwrite: true });
    // Elements already on screen animate straight away; the rest wait until they are scrolled into view.
    const onScreen = nodes.filter(n => n.getBoundingClientRect().top < window.innerHeight * 0.95);
    const later = nodes.filter(n => !onScreen.includes(n));
    gsap.set(nodes, { opacity: 0, y: 28 });
    if (onScreen.length) show(onScreen);
    if (later.length) {
      ScrollTrigger.batch(later, { start: 'top 95%', once: true, onEnter: show });
      ScrollTrigger.refresh();
    }
    // Safety net: content must never stay hidden if a trigger does not fire.
    setTimeout(() => {
      const hidden = nodes.filter(n => n.isConnected && parseFloat(getComputedStyle(n).opacity) < 0.05);
      if (hidden.length) show(hidden);
    }, 2500);
  }
  api.enter = enter;

  // ---------- page intro ----------
  let ready = false;   // view/text hooks wait for the intro so headings are not split three times on load
  function intro() {
    ready = true;
    const tl = gsap.timeline({ defaults: { ease: 'expo.out' } });
    tl.from('.sidebar', { x: document.documentElement.dir === 'rtl' ? 40 : -40, opacity: 0, duration: 1 })
      .from('.falcon-frame', { clipPath: 'inset(50% 0% 50% 0%)', duration: 1.3, ease: 'expo.inOut' }, 0.1)
      .from('.falcon-frame img', { scale: 1.25, filter: 'blur(10px) brightness(1.8)', duration: 1.8 }, 0.2)
      .from('.hud-corner', { scale: 2, opacity: 0, duration: 0.8, stagger: 0.06 }, 0.9)
      .from('.hud-reticle', { scale: 3, opacity: 0, rotate: -90, duration: 1.1 }, 1.0)
      .from('.hud-tag', { opacity: 0, x: -14, duration: 0.6, stagger: 0.15 }, 1.4)
      .from('.radar-ring', { scale: 0.4, opacity: 0, duration: 1.6, stagger: 0.12 }, 0.15)
      .from('.hero .eyebrow, .hero-tags span, .workflow-strip span', { y: 14, opacity: 0, duration: 0.8, stagger: 0.05 }, 0.5);
    splitReveal(document.querySelector('#compose h1'), 0.25);
    blurIn(document.querySelector('#compose .intro'), 0.6);
    enter(['#form', '.guide .card', '.example']);
    // gentle falcon parallax following the pointer
    const scene = document.querySelector('.falcon-scene');
    if (scene) {
      const img = scene.querySelector('img');
      const qx = gsap.quickTo(img, 'x', { duration: 1.2, ease: 'power3' });
      const qy = gsap.quickTo(img, 'y', { duration: 1.2, ease: 'power3' });
      const rings = gsap.utils.toArray('.radar-ring');
      scene.closest('.hero').addEventListener('pointermove', e => {
        const r = scene.getBoundingClientRect();
        const dx = (e.clientX - r.left - r.width / 2) / r.width, dy = (e.clientY - r.top - r.height / 2) / r.height;
        qx(dx * 7); qy(dy * 5);   // the photo is scaled 1.04 inside its frame, so keep the shift small
        rings.forEach((ring, i) => gsap.to(ring, { x: dx * (6 + i * 5), y: dy * (4 + i * 4), duration: 1.4, ease: 'power3' }));
      });
      // slow radar sweep rotation
      gsap.to('.radar-ring', { rotate: 360, duration: 60, repeat: -1, ease: 'none', stagger: { each: 4 } });
      // HUD: scan line sweeping the photo, rotating outer reticle ring, breathing lock, flickering tags
      gsap.fromTo('.hud-scan', { yPercent: -100 }, { yPercent: 480, duration: 3.6, ease: 'sine.inOut', repeat: -1, repeatDelay: 0.8, delay: 1.6 });
      gsap.to('.hud-reticle i', { rotate: 360, duration: 14, repeat: -1, ease: 'none' });
      gsap.to('.hud-reticle', { scale: 1.08, duration: 1.4, yoyo: true, repeat: -1, ease: 'sine.inOut', delay: 2 });
      gsap.to('.hud-tag-a', { opacity: 0.35, duration: 0.08, repeat: -1, repeatDelay: 3.2, yoyo: true, delay: 3 });
    }
  }

  // ---------- view changes ----------
  api.view = id => {
    const root = document.getElementById(id);
    if (!root) return;
    lenis.scrollTo(0, { immediate: true, force: true });   // keep Lenis in sync with the view's scroll reset
    if (!ready) return;
    gsap.fromTo(root, { opacity: 0 }, { opacity: 1, duration: 0.5, ease: 'power2.out' });
    if (id !== 'results') splitReveal(root.querySelector('h1'), 0.05);   // report() animates the results title
    if (id === 'history') enter(root.querySelectorAll('.historyitem, .empty'), { delay: 0.15 });
    if (id === 'compose') enter(['#form', '.guide .card', '.example']);
    ScrollTrigger.refresh();
  };

  // Text was replaced (language switch): re-run the reveals on the visible headings.
  api.text = () => {
    if (!ready) return;
    const visible = ['compose', 'results', 'history'].map(id => document.getElementById(id)).find(s => !s.hidden);
    if (!visible) return;
    splitReveal(visible.querySelector('h1'));
    if (visible.id === 'compose') blurIn(visible.querySelector('.intro'), 0.2);
  };

  // ---------- report rendering ----------
  // prev: {sectionKey: status} from the previous poll of the same report, or null on first render.
  api.report = (p, prev) => {
    const cards = gsap.utils.toArray('#sections > .card');
    const scanning = p.status !== 'complete' && p.mode !== 'sample';
    scan(scanning);
    if (!prev) {
      splitReveal(document.querySelector('#results h1'));
      gsap.from('#banner > *', { y: 18, opacity: 0, filter: 'blur(6px)', duration: 0.8, ease: 'power3.out', stagger: 0.08 });
      enter(['#checks', '.submitted']);
      enter(cards, { delay: 0.1 });
      gsap.from('#checks .checklist li', { scale: 0.92, opacity: 0, duration: 0.5, ease: 'back.out(2)', stagger: 0.06, delay: 0.3 });
      return;
    }
    // Same report, new poll: animate only what changed.
    (p.sections || []).forEach((s, i) => {
      if (prev[s.key] && prev[s.key] !== s.status && cards[i]) {
        gsap.fromTo(cards[i], { opacity: 0.2, y: 14, '--flash': 1 },
          { opacity: 1, y: 0, '--flash': 0, duration: 0.9, ease: 'power3.out' });
      }
    });
    gsap.utils.toArray('#checks .checklist li').forEach(li => {
      if (li.dataset.changed === '1') gsap.from(li, { scale: 0.9, duration: 0.6, ease: 'back.out(3)' });
    });
    if (p.status === 'complete' && prev.__status !== 'complete') {
      gsap.timeline()
        .from('#banner .pill', { scale: 0.6, opacity: 0, duration: 0.7, ease: 'back.out(2.5)' })
        .add(() => blurIn(document.querySelector('#banner h2')), 0.1)
        .from('#banner .priority, #banner small', { x: -12, opacity: 0, duration: 0.5, stagger: 0.08 }, 0.3);
    }
  };

  // ---------- scanning animation while checks run ----------
  let scanTl = null;
  function scan(on) {
    const figs = gsap.utils.toArray('#resultmedia figure');
    if (on && figs.length) {
      if (scanTl && figs.every(f => f.querySelector('.scan'))) return;
      if (scanTl) scanTl.kill();
      figs.forEach(f => {
        if (f.querySelector('.scan')) return;
        const s = document.createElement('div');
        s.className = 'scan';
        s.innerHTML = '<span class="scan-grid"></span><span class="scan-line"></span><span class="scan-corner tl"></span><span class="scan-corner tr"></span><span class="scan-corner bl"></span><span class="scan-corner br"></span><span class="scan-label">ANALYSING</span>';
        f.append(s);
      });
      scanTl = gsap.timeline({ repeat: -1 })
        .fromTo('#resultmedia .scan-line', { top: '-4%' }, { top: '100%', duration: 1.8, ease: 'sine.inOut', stagger: 0.25 })
        .to('#resultmedia .scan-line', { top: '-4%', duration: 1.8, ease: 'sine.inOut', stagger: 0.25 });
      gsap.fromTo('#resultmedia .scan', { opacity: 0 }, { opacity: 1, duration: 0.4 });
      gsap.to('#resultmedia .scan-grid', { opacity: 0.55, duration: 0.9, yoyo: true, repeat: -1, ease: 'sine.inOut' });
    } else if (!on && document.querySelector('#resultmedia .scan')) {
      if (scanTl) scanTl.kill();
      scanTl = null;
      gsap.to('#resultmedia .scan', {
        opacity: 0, duration: 0.6, onComplete: () => document.querySelectorAll('#resultmedia .scan').forEach(n => n.remove()),
      });
      gsap.fromTo('#resultmedia img', { filter: 'brightness(1.6) saturate(0.4)' }, { filter: 'none', duration: 1.2, ease: 'power2.out' });
    }
  }

  initAurora(false);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', intro); else intro();
})();

// ---------- spotlight cards (React Bits "SpotlightCard") ----------
function initSpotlight() {
  document.addEventListener('pointermove', e => {
    const card = e.target.closest && e.target.closest('.card, .report-banner, .historyitem');
    if (!card) return;
    const r = card.getBoundingClientRect();
    card.style.setProperty('--mx', (e.clientX - r.left) + 'px');
    card.style.setProperty('--my', (e.clientY - r.top) + 'px');
  }, { passive: true });
}

// ---------- living aurora + drifting sand behind the hero (React Bits "Aurora"/"Particles") ----------
function initAurora(staticOnly) {
  const hero = document.querySelector('.hero');
  if (!hero) return;
  const canvas = document.createElement('canvas');
  canvas.className = 'aurora';
  canvas.setAttribute('aria-hidden', 'true');
  hero.prepend(canvas);
  const ctx = canvas.getContext('2d');
  const blobs = [
    { c: [34, 211, 238], r: 0.55, x: 0.72, y: 0.35, sx: 0.08, sy: 0.10, p: 0 },
    { c: [124, 92, 255], r: 0.45, x: 0.30, y: 0.70, sx: 0.10, sy: 0.06, p: 2 },
    { c: [45, 245, 166], r: 0.50, x: 0.55, y: 0.80, sx: 0.07, sy: 0.08, p: 4 },
    { c: [14, 116, 144], r: 0.35, x: 0.90, y: 0.65, sx: 0.05, sy: 0.09, p: 1 },
  ];
  const grains = Array.from({ length: 70 }, () => ({ x: Math.random(), y: Math.random(), s: 0.6 + Math.random() * 1.6,
    v: 0.00006 + Math.random() * 0.00016, a: 0.15 + Math.random() * 0.35 }));
  let w = 0, h = 0, dpr = 1, visible = true, raf = 0;
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = hero.clientWidth; h = hero.clientHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function draw(t) {
    ctx.clearRect(0, 0, w, h);
    const s = t / 1000;
    for (const b of blobs) {
      const x = (b.x + Math.sin(s * b.sx + b.p) * 0.12) * w;
      const y = (b.y + Math.cos(s * b.sy + b.p) * 0.12) * h;
      const r = b.r * Math.max(w, h) * (0.9 + 0.1 * Math.sin(s * 0.3 + b.p));
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, `rgba(${b.c},0.22)`);
      g.addColorStop(1, `rgba(${b.c},0)`);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);
    }
    for (const p of grains) {
      if (!staticOnly) { p.x += p.v * 16; p.y -= p.v * 6; if (p.x > 1) p.x = 0; if (p.y < 0) p.y = 1; }
      ctx.fillStyle = `rgba(34,211,238,${p.a})`;
      ctx.beginPath(); ctx.arc(p.x * w, p.y * h, p.s, 0, Math.PI * 2); ctx.fill();
    }
  }
  function loop(t) { draw(t); raf = visible ? requestAnimationFrame(loop) : 0; }
  resize();
  window.addEventListener('resize', () => { resize(); if (staticOnly) draw(0); });
  if (staticOnly) { draw(0); return; }
  new IntersectionObserver(([e]) => {
    visible = e.isIntersecting && !document.hidden;
    if (visible && !raf) raf = requestAnimationFrame(loop);
  }).observe(hero);
  document.addEventListener('visibilitychange', () => { visible = !document.hidden; if (visible && !raf) raf = requestAnimationFrame(loop); });
}
