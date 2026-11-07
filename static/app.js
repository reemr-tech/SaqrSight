'use strict';
// SaqrSight browser client. All server/user text is inserted with textContent (never innerHTML).
const $ = id => document.getElementById(id);
const IMG_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const VID_TYPES = ['video/mp4', 'video/quicktime', 'video/webm'];
let current = null, previewURL = null, busy = false, cfg = null, pollTimer = null, viewName = 'landing', user = null;
const VIEWS = ['landing', 'login', 'signup', 'dashboard', 'compose', 'results', 'history', 'models'];
const PUBLIC_VIEWS = ['landing', 'login', 'signup'];
let lang = 'en';
try { lang = localStorage.getItem('saqr-ui-lang') || 'en'; } catch (e) { /* storage unavailable */ }

function t(key, vars) {
  let s = (I18N[lang] && I18N[lang][key]) || I18N.en[key] || key;
  for (const [k, v] of Object.entries(vars || {})) s = s.replaceAll('{' + k + '}', v);
  return s;
}
function L(obj) { return obj ? (obj[lang] || obj.en || '') : ''; }   // bilingual server labels
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}
function safeLink(url, text) {
  const a = el('a', null, text || url);
  if (/^https?:\/\//i.test(url)) { a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; }
  return a;
}

// ---------- language ----------
function applyLang() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  document.querySelectorAll('[data-i18n]').forEach(n => { n.textContent = t(n.dataset.i18n); });
  document.querySelectorAll('[data-i18n-html]').forEach(n => { n.innerHTML = t(n.dataset.i18nHtml); }); // static dictionary only
  document.querySelectorAll('[data-i18n-placeholder]').forEach(n => { n.placeholder = t(n.dataset.i18nPlaceholder); });
  $('uilang').textContent = lang === 'ar' ? 'English' : 'العربية';
  renderConfig();
  updateChars();
  setBreadcrumb();
  if (current && viewName === 'results') showReport(current, true);
  if (viewName === 'history') refresh();
  if (viewName === 'dashboard') loadDashboard();
  renderModels();
  if (user) $('dashtitle').textContent = t('dashTitle', { name: user.name });
  if (window.Motion) Motion.text();
}
$('uilang').onclick = () => {
  lang = lang === 'ar' ? 'en' : 'ar';
  try { localStorage.setItem('saqr-ui-lang', lang); } catch (e) { /* ignore */ }
  applyLang();
};

// ---------- configuration and limits ----------
async function loadConfig() {
  try { cfg = await request('/api/config'); } catch (e) { cfg = null; }
  renderConfig();
}
function renderConfig() {
  if (!cfg) return;
  const l = cfg.limits;
  $('limits').textContent = t('limits', { imgf: l.image_formats.join(', '), imb: l.max_image_mb, imp: l.max_image_megapixels,
    ims: l.min_image_side, vidf: l.video_formats.join(', '), vmb: l.max_video_mb, vs: l.max_video_seconds, vf: l.video_frames_sampled });
  $('caption').maxLength = l.max_text_chars;
  // Image and video analysis is Senior Project 2: show the 'coming soon' card instead of the upload box.
  const media = !!cfg.media_enabled;
  $('drop').hidden = !media;
  $('mediasoon').hidden = media;
  if (!media) { $('media').value = ''; $('preview').hidden = true; }
  $('privacy').textContent = t('privacy', { days: l.retention_days });
  const ext = cfg.checks.reverse_image_search || cfg.checks.official_sources;
  $('consent').disabled = !ext;
  if (!ext) $('consent').checked = false;
  const items = [];
  if (cfg.checks.reverse_image_search) items.push(cfg.external.reverse_image_search);
  if (cfg.checks.official_sources) items.push(cfg.external.official_sources + ' → ' + cfg.external.official_domains.join(', '));
  $('consentdetail').textContent = ext ? t('consentOn', { items: items.join('; ') }) : t('consentOff');
  const box = $('checkstatus');
  box.replaceChildren(el('strong', null, t('available')));
  const ul = el('ul', 'checklist');
  for (const [k, on] of Object.entries(cfg.checks)) {
    const li = el('li', on ? 'on' : 'off');
    li.append(el('span', null, t('mod_' + k)), el('em', null, on ? t('on') : t('off')));
    ul.append(li);
  }
  box.append(ul);
}

// ---------- views ----------
function setBreadcrumb() {
  $('breadcrumb').textContent = t('bc_' + viewName);
}
function view(id) {
  if (!user && !PUBLIC_VIEWS.includes(id)) id = 'landing';
  if (user && PUBLIC_VIEWS.includes(id)) id = 'dashboard';
  viewName = id;
  for (const name of VIEWS) $(name).hidden = name !== id;
  const navFor = { dashboard: 'dashnav', compose: 'newnav', results: 'newnav', history: 'historynav', models: 'modelsnav' };
  for (const n of ['dashnav', 'newnav', 'historynav', 'modelsnav']) $(n).classList.toggle('active', navFor[id] === n);
  setBreadcrumb();
  window.scrollTo(0, 0);
  if (window.Motion) Motion.view(id);
}
function error(message) { $('error').textContent = message; $('error').hidden = !message; }
async function request(url, options) {
  const r = await fetch(url, Object.assign({ credentials: 'same-origin' }, options));
  if (r.status === 401 && user && !url.startsWith('/api/auth/')) {   // session expired or logged out elsewhere
    setUser(null);
    view('login');
  }
  if (!r.ok) {
    let message = 'Request failed. Please try again.';
    try { const e = await r.json(); if (typeof e.detail === 'string') message = e.detail; } catch (e) { /* ignore */ }
    throw Error(message);
  }
  return r.status === 204 ? null : r.json();
}

// ---------- compose ----------
function updateChars() {
  const max = cfg ? cfg.limits.max_text_chars : 10000;
  $('chars').textContent = $('caption').value.length.toLocaleString() + ' / ' + max.toLocaleString();
  const v = $('caption').value;
  const ar = (v.match(/[؀-ۿ]/g) || []).length, la = (v.match(/[A-Za-z]/g) || []).length;
  const d = $('detected');
  if ($('language').value !== 'auto' || ar + la === 0) { d.hidden = true; return; }
  const share = ar / (ar + la);
  const name = share >= 0.8 ? t('langAr') : share <= 0.2 ? t('langEn') : t('langMixed');
  d.textContent = t('detected', { lang: name });
  d.hidden = false;
}
function preview() {
  if (previewURL) URL.revokeObjectURL(previewURL);
  previewURL = null;
  const f = $('media').files[0];
  $('preview').hidden = !f;
  if (!f) return;
  const l = cfg ? cfg.limits : { max_image_mb: 10, max_video_mb: 50 };
  const isImg = IMG_TYPES.includes(f.type), isVid = VID_TYPES.includes(f.type);
  const tooBig = (isImg && f.size > l.max_image_mb * 1048576) || (isVid && f.size > l.max_video_mb * 1048576);
  if ((!isImg && !isVid) || tooBig) { $('media').value = ''; $('preview').hidden = true; error(t('badFile')); return; }
  error('');
  previewURL = URL.createObjectURL(f);
  $('previewimg').hidden = !isImg;
  $('previewvid').hidden = !isVid;
  if (isImg) $('previewimg').src = previewURL; else $('previewvid').src = previewURL;
  $('filename').textContent = f.name;
  $('filesize').textContent = (f.size / 1048576).toFixed(2) + ' MB';
}
function clear() {
  if (busy) return;
  $('form').reset();
  preview();
  updateChars();
  error('');
  stopPolling();
  view('compose');
}
$('form').onsubmit = async e => {
  e.preventDefault();
  if (busy) return;
  error('');
  if (!$('caption').value.trim() && !$('media').files.length) { error(t('needInput')); return; }
  busy = true;
  $('analyze').disabled = $('clear').disabled = true;
  $('analyze').firstElementChild.textContent = t('analyzing');
  const data = new FormData();
  data.append('caption', $('caption').value);
  data.append('language', $('language').value);
  data.append('allow_external', $('consent').checked ? 'true' : 'false');
  if ($('media').files[0]) data.append('media', $('media').files[0]);
  try {
    const p = await request('/api/reports', { method: 'POST', body: data });
    showReport(p);
    poll(p.id);
    refreshCount();
  } catch (err) {
    error(err.message);
  } finally {
    busy = false;
    $('analyze').disabled = $('clear').disabled = false;
    $('analyze').firstElementChild.textContent = t('analyze');
  }
};

// ---------- polling ----------
function stopPolling() { if (pollTimer) clearTimeout(pollTimer); pollTimer = null; }
function poll(id) {
  stopPolling();
  pollTimer = setTimeout(async () => {
    try {
      const p = await request('/api/reports/' + encodeURIComponent(id));
      if (current && current.id === id) showReport(p, true);
      if (p.status !== 'complete') poll(id); else refresh();
    } catch (e) { stopPolling(); }
  }, 1200);
}

// ---------- report rendering ----------
function mediaURL(id, ref) { return '/api/reports/' + encodeURIComponent(id) + '/media/' + encodeURIComponent(ref); }

function renderFinding(f) {
  const box = el('div', 'finding');
  const head = el('p');
  if (f.label) head.append(el('b', null, (lang === 'ar' && f.label_ar ? f.label_ar : f.label) + ': '));
  head.append(document.createTextNode(lang === 'ar' && f.message_ar ? f.message_ar : f.message));
  box.append(head);
  if (lang === 'ar' && f.excerpts_ar && f.excerpts_ar.length) {
    const ul = el('ul');
    for (const x of f.excerpts_ar) ul.append(el('li', null, x));
    box.append(ul);
  } else if (f.excerpts && f.excerpts.length) {
    const ex = el('p', 'excerpts');
    for (const x of f.excerpts) { const q = el('q', null, x); q.dir = 'auto'; ex.append(q, ' '); }
    box.append(ex);
  }
  if (f.frames && f.frames.length) {
    const fr = el('p', 'frames');
    for (const x of f.frames) {
      const score = undefined;   // raw model scores are kept for the Technical details in the downloaded report
      const ref = lang === 'ar' && x.ref === 'image' ? 'الصورة' : x.ref;
      const label = (x.timestamp !== undefined ? t('frameAt', { t: x.timestamp }) : ref) +
        (score !== undefined ? ' · ' + t('score') + ' ' + score : '');
      fr.append(el('span', 'chip', label));
    }
    box.append(fr);
  }
  for (const s of f.sources || []) {
    const src = el('div', 'source');
    src.append(safeLink(s.url, s.title || s.url));
    const meta = (lang === 'ar'
      ? [s.source, s.date || t('noDate'), s.match_type_ar || s.match_type, s.relation_ar || s.relation]
      : [s.source, s.date || t('noDate'), s.match_type, s.relation]).filter(Boolean).join(' · ');
    src.append(el('small', null, meta));
    if (s.excerpt) { const q = el('q', null, s.excerpt); q.dir = 'auto'; src.append(q); }
    const notes = lang === 'ar' && s.notes_ar && s.notes_ar.length ? s.notes_ar.join('؛ ') : (s.notes || []).join('; ');
    if (notes) src.append(el('small', 'note', notes));
    box.append(src);
  }
  return box;
}

function renderSection(s) {
  const card = el('article', 'card section status-' + s.status);
  if (s.key === 'initial_assessment' || s.key === 'recommended_action') card.classList.add('wide');
  const top = el('div', 'section-top');
  top.append(el('h2', null, L(s.title)), el('span', 'status-chip ' + s.status, L(s.status_label)));
  card.append(top);
  const summary = lang === 'ar' && s.summary_ar ? s.summary_ar : s.summary;
  if (s.key === 'review_priority' && s.label) card.append(el('p', 'priority ' + s.level, L(s.label)));
  card.append(el('p', 'summary', summary));
  const items = lang === 'ar' && s.items_ar && s.items_ar.length ? s.items_ar : s.items;
  if (items && items.length) {
    const ul = el('ul');
    for (const it of items) ul.append(el('li', null, it));
    card.append(ul);
  }
  for (const f of s.findings || []) card.append(renderFinding(f));
  const lims = lang === 'ar' && s.limitations_ar && s.limitations_ar.length ? s.limitations_ar : s.limitations;
  if (lims && lims.length) {
    const d = el('details', 'limits');
    d.append(el('summary', null, t('limitations')));
    for (const x of lims) d.append(el('p', null, x));
    card.append(d);
  }
  return card;
}

function renderLegacy(p) {
  const banner = $('banner');
  banner.className = 'report-banner sample';
  banner.replaceChildren(el('span', 'pill', t('sampleBadge')), el('h2', null, t('sampleBanner')), el('p', null, p.notice));
  $('checks').hidden = true;
  $('sections').replaceChildren(...p.sections.map(s => {
    const c = el('article', 'card');
    c.append(el('h2', null, s.title), el('p', null, s.finding));
    return c;
  }));
}

let renderedMediaFor = null;
function showReport(p, keepView) {
  // Statuses from the previous render of the same report, so only changes are animated.
  let prev = null;
  if (current && current.id === p.id && renderedMediaFor === p.id) {
    prev = { __status: current.status };
    for (const s of current.sections || []) prev[s.key] = s.status;
    prev.__modules = Object.fromEntries(Object.entries(current.modules || {}).map(([k, m]) => [k, m.status]));
  }
  current = p;
  $('reportdate').textContent = new Date(p.created_at).toLocaleString(lang === 'ar' ? 'ar-AE' : undefined);
  $('resultcaption').textContent = p.caption || t('noText');
  $('reportid').textContent = t('reportLine', { id: p.id, lang: p.language });
  const strip = $('resultmedia');
  const visuals = p.media ? p.media.visuals : (p.image ? [{ ref: 'image' }] : []);
  const sameMedia = renderedMediaFor === p.id;
  renderedMediaFor = p.id;
  if (!sameMedia) strip.replaceChildren();
  for (const v of sameMedia ? [] : visuals) {
    const fig = el('figure');
    const img = el('img');
    img.src = p.media ? mediaURL(p.id, v.ref) : '/api/reports/' + encodeURIComponent(p.id) + '/image';
    img.alt = v.timestamp !== undefined ? t('frameAt', { t: v.timestamp }) : 'Submitted image';
    fig.append(img);
    if (v.timestamp !== undefined) fig.append(el('figcaption', null, t('frameAt', { t: v.timestamp })));
    strip.append(fig);
  }
  if (!sameMedia && p.media && p.media.kind === 'video') {
    strip.append(el('p', 'note', t('frameNote', { ts: p.media.visuals.map(v => v.timestamp + 's').join(', ') })));
  }
  if (p.mode === 'sample') {
    renderLegacy(p);
    if (!keepView) view('results');
    if (window.Motion) Motion.report(p, prev);
    return;
  }

  const banner = $('banner');
  const a = p.assessment;
  banner.className = 'report-banner ' + (a ? a.verdict : 'processing');
  banner.replaceChildren();
  if (a) {
    banner.append(el('span', 'pill', L(a.label)));
    const plainList = p.plain ? (lang === 'ar' ? p.plain.ar : p.plain.en) : [L(a.explanation)];
    const box = el('div', 'plainwords');
    box.append(el('p', 'plainwords-title', t('inPlain')));
    const ul = el('ul');
    for (const line of plainList) ul.append(el('li', null, line));
    box.append(ul);
    banner.append(box);
    banner.append(el('p', 'priority ' + a.priority.level, t('priority') + ': ' + L(a.priority.label)));
    const guide = el('details', 'guide-box');
    guide.append(el('summary', null, t('howToRead')));
    for (const k of ['misleading', 'insufficient', 'consistent', 'priority', 'issue']) {
      const row = el('p');
      row.append(el('b', null, t('g_' + k) + ': '), document.createTextNode(t('g_' + k + '_d')));
      guide.append(row);
    }
    banner.append(guide);
  } else {
    banner.append(el('span', 'pill', '…'), el('h2', null, t('processing')));
  }
  const checks = $('checks');
  checks.hidden = false;
  checks.replaceChildren(el('h2', null, t('checksTitle')));
  const ul = el('ul', 'checklist');
  for (const k of ['text_analysis', 'media_analysis', 'consistency_check', 'reverse_image_search', 'official_sources']) {
    const m = (p.modules || {})[k];
    const status = m ? m.status : 'pending';
    const li = el('li', status);
    const statusLabel = t('st_' + status);
    li.append(el('span', null, t('mod_' + k)), el('em', null, statusLabel));
    if (m && m.summary) li.title = m.summary;
    if (prev && prev.__modules && (prev.__modules[k] || 'pending') !== status) li.dataset.changed = '1';
    ul.append(li);
  }
  checks.append(ul);
  $('sections').replaceChildren(...(p.sections || []).map(renderSection));
  if (!keepView) view('results');
  if (window.Motion) Motion.report(p, prev);
}

// ---------- history ----------
function searchParams() {
  const params = new URLSearchParams();
  for (const [key, id] of [['q', 'q'], ['verdict', 'fverdict'], ['panic', 'fpanic'], ['priority', 'fpriority'], ['language', 'flang']]) {
    const v = $(id).value.trim();
    if (v) params.set(key, v);
  }
  return params;
}
async function refreshCount() {
  if (!user) return;
  try { $('count').textContent = (await request('/api/reports')).length; } catch (e) { /* ignore */ }
}
async function refresh() {
  if (!user) return;
  try {
    const params = searchParams();
    const reports = await request('/api/reports' + (params.toString() ? '?' + params : ''));
    if (!params.toString()) $('count').textContent = reports.length;
    $('resultcount').textContent = params.toString() ? t('resultCount', { n: reports.length }) : '';
    $('historyintro').textContent = t('historyIntro', { days: cfg ? cfg.limits.retention_days : 30 });
    const list = $('historylist');
    list.replaceChildren();
    if (!reports.length) list.append(el('div', 'card empty', searchParams().toString() ? t('noMatches') : t('empty')));
    for (const r of reports) {
      const row = el('article', 'card historyitem');
      const d = el('div');
      d.append(reportMeta(r));
      const cap = el('p', null, r.caption || t('imageOnly'));
      cap.dir = 'auto';
      d.append(cap);
      const open = el('button', 'secondary', t('open'));
      open.onclick = () => openReport(r.id);
      row.append(d, open);
      list.append(row);
    }
    if (viewName === 'history' && window.Motion) Motion.enter(list.children);
  } catch (e) {
    $('historylist').textContent = e.message;
  }
}

// ---------- shared report summary line (search results, dashboard) ----------
function reportMeta(r) {
  const meta = el('div', 'meta-row');
  if (r.mode === 'sample') meta.append(el('span', 'tag sample', t('sampleBadge')));
  if (r.assessment) meta.append(el('span', 'tag v-' + r.assessment, t('v_' + r.assessment)));
  if (r.panic_level) meta.append(el('span', 'tag p-' + r.panic_level, t('p_' + r.panic_level)));
  if (r.priority) meta.append(el('span', 'tag pr-' + r.priority, t('priority') + ': ' + t('pr_' + r.priority)));
  if (r.status === 'processing') meta.append(el('span', 'tag', '…'));
  meta.append(el('small', null, new Date(r.created_at).toLocaleString(lang === 'ar' ? 'ar-AE' : undefined)));
  return meta;
}
async function openReport(id) {
  try {
    const p = await request('/api/reports/' + encodeURIComponent(id));
    showReport(p);
    if (p.status !== 'complete') poll(p.id);
  } catch (e) { alert(e.message); }
}

// ---------- dashboard ----------
function bars(target, counts, order, labelFor, clsFor) {
  const box = $(target);
  box.replaceChildren();
  const max = Math.max(1, ...order.map(k => counts[k] || 0));
  for (const k of order) {
    const row = el('div', 'bar-row');
    const track = el('div', 'bar-track');
    const fill = el('div', 'bar-fill ' + (clsFor ? clsFor(k) : ''));
    fill.style.setProperty('--w', ((counts[k] || 0) / max * 100) + '%');
    track.append(fill);
    row.append(el('span', 'bar-label', labelFor(k)), track, el('b', 'bar-value', String(counts[k] || 0)));
    box.append(row);
  }
}
async function loadDashboard() {
  if (!user) return;
  $('dashtitle').textContent = t('dashTitle', { name: user.name });
  let d;
  try { d = await request('/api/dashboard'); } catch (e) { return; }
  $('count').textContent = d.total;
  const stats = $('stats');
  stats.replaceChildren();
  for (const [value, label, cls] of [[d.total, t('stTotal'), ''], [d.this_week, t('stWeek'), ''],
    [d.priorities.high, t('stHigh'), 'red'], [d.panic_levels.strong, t('stStrong'), 'amber']]) {
    const tile = el('article', 'card stat ' + cls);
    tile.append(el('b', 'stat-value', String(value)), el('span', 'stat-label', label));
    stats.append(tile);
  }
  bars('chartverdict', d.verdicts, ['potentially_misleading', 'insufficient_evidence', 'apparently_consistent'], k => t('v_' + k), k => 'v-' + k);
  bars('chartpanic', d.panic_levels, ['strong', 'mild', 'none'], k => t('p_' + k), k => 'p-' + k);
  bars('chartpriority', d.priorities, ['high', 'medium', 'low'], k => t('pr_' + k), k => 'pr-' + k);
  bars('chartcategory', d.categories, ['urgency', 'fear', 'manipulation', 'share_pressure'], k => t('cat_' + k), () => 'cat');
  const list = $('recentlist');
  list.replaceChildren();
  if (!d.recent.length) list.append(el('p', 'empty', t('dashEmpty')));
  for (const r of d.recent) {
    const row = el('div', 'recent-row');
    const left = el('div');
    const cap = el('p', null, r.caption || t('imageOnly'));
    cap.dir = 'auto';
    left.append(cap, reportMeta(r));
    const open = el('button', 'secondary', t('open'));
    open.onclick = () => openReport(r.id);
    row.append(left, open);
    list.append(row);
  }
  if (window.Motion) Motion.enter(document.querySelectorAll('#dashboard .card'));
}

// ---------- models & roadmap ----------
function renderModels() {
  const data = window.SAQR_MODELS;
  if (!data) return;
  const legend = $('modelslegend');
  legend.replaceChildren(...['now', 'prototype', 'planned'].map(s => el('span', 'status-tag s-' + s, t('ms_' + s))));
  const list = $('modelslist');
  list.replaceChildren();
  for (const g of data.groups) {
    const section = el('div', 'model-group');
    section.append(el('h2', null, L(g)));
    const grid = el('div', 'model-grid');
    for (const m of g.items) {
      const card = el('article', 'card model s-' + m.status);
      const top = el('div', 'section-top');
      top.append(el('h3', null, m.name), el('span', 'status-tag s-' + m.status, t('ms_' + m.status)));
      const id = el('code', 'model-id', m.id);
      id.dir = 'ltr';
      card.append(top, id);
      const dl = el('dl');
      for (const [k, v] of [['m_size', m.size], ['m_role', m.role], ['m_result', m.result], ['m_licence', m.licence]]) {
        dl.append(el('dt', null, t(k)), el('dd', null, L(v)));
      }
      card.append(dl);
      if (m.links.length) {
        const links = el('p', 'model-links');
        for (const l of m.links) links.append(safeLink(l.url, l.label + ' ↗'));
        card.append(links);
      }
      grid.append(card);
    }
    section.append(grid);
    list.append(section);
  }
}

// ---------- accounts ----------
function setUser(u) {
  user = u;
  document.body.classList.toggle('signed-in', !!u);
  document.body.classList.toggle('signed-out', !u);
  $('username').textContent = u ? u.name : '';
  $('useremail').textContent = u ? u.email : '';
  if (!u) { current = null; stopPolling(); $('count').textContent = '0'; }
}
async function checkAuth() {
  try {
    const r = await fetch('/api/auth/me', { credentials: 'same-origin' });
    setUser(r.ok ? await r.json() : null);
  } catch (e) { setUser(null); }
}
function authError(form, message) {
  const box = form.querySelector('.autherror');
  box.textContent = message || '';
  box.hidden = !message;
}
async function submitAuth(form, url, body) {
  authError(form, '');
  const btn = form.querySelector('button[type=submit]');
  btn.disabled = true;
  try {
    const u = await request(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    setUser(u);
    form.reset();
    await loadConfig();
    view('dashboard');
    loadDashboard();
  } catch (e) {
    authError(form, e.message);
  } finally {
    btn.disabled = false;
  }
}
$('loginform').onsubmit = e => {
  e.preventDefault();
  submitAuth($('loginform'), '/api/auth/login', { email: $('loginemail').value, password: $('loginpassword').value });
};
$('signupform').onsubmit = e => {
  e.preventDefault();
  submitAuth($('signupform'), '/api/auth/signup',
    { name: $('signupname').value, email: $('signupemail').value, password: $('signuppassword').value });
};
$('logout').onclick = async () => {
  try { await request('/api/auth/logout', { method: 'POST' }); } catch (e) { /* ignore */ }
  setUser(null);
  view('landing');
};
for (const [id, target] of [['hdrlogin', 'login'], ['landlogin', 'login'], ['tologin', 'login'],
  ['hdrsignup', 'signup'], ['landsignup', 'signup'], ['tosignup', 'signup']]) {
  $(id).onclick = () => view(target);
}
$('landmodels').onclick = () => { if (user) view('models'); else view('login'); };

// ---------- wiring ----------
$('caption').oninput = updateChars;
$('language').onchange = updateChars;
$('media').onchange = preview;
$('remove').onclick = () => { $('media').value = ''; preview(); };
$('clear').onclick = clear;
$('another').onclick = clear;
$('newnav').onclick = () => { if (!busy) view('compose'); };
$('historynav').onclick = () => { if (busy) return; view('history'); refresh(); };
$('dashnav').onclick = () => { if (busy) return; view('dashboard'); loadDashboard(); };
$('modelsnav').onclick = () => { if (!busy) view('models'); };
$('dashnew').onclick = () => view('compose');
$('searchform').onsubmit = e => { e.preventDefault(); refresh(); };
for (const id of ['fverdict', 'fpanic', 'fpriority', 'flang']) $(id).onchange = refresh;
$('example').onclick = () => { $('caption').value = t('exampleText'); updateChars(); $('caption').focus(); };
for (const type of ['dragenter', 'dragover']) $('drop').addEventListener(type, e => { e.preventDefault(); $('drop').classList.add('drag'); });
for (const type of ['dragleave', 'drop']) $('drop').addEventListener(type, e => { e.preventDefault(); $('drop').classList.remove('drag'); });
$('drop').addEventListener('drop', e => {
  if (e.dataTransfer.files.length !== 1) { error(t('oneFile')); return; }
  $('media').files = e.dataTransfer.files;
  preview();
});
// HTML download: ask for the report language first, then download in that language.
function lastReportLang() { try { return localStorage.getItem('saqr-report-lang'); } catch (e) { return null; } }
function downloadReport(format, reportLang) {
  if (!current) return;
  const extra = format === 'html' ? '&lang=' + encodeURIComponent(reportLang || 'both') : '';
  window.location.href = '/api/reports/' + encodeURIComponent(current.id) + '/download?format=' + format + extra;
}
$('downloadhtml').onclick = () => {
  if (!current) return;
  const last = lastReportLang();
  document.querySelectorAll('.langchoice').forEach(b => {
    b.classList.toggle('last', b.dataset.lang === last);
    b.dataset.lastLabel = t('lastUsed');
  });
  $('langdialog').showModal();
  if (window.Motion && Motion.ok) gsap.fromTo('.langdialog form > *', { y: 12, opacity: 0 }, { y: 0, opacity: 1, duration: 0.45, stagger: 0.05, ease: 'power3.out', overwrite: true });
  (document.querySelector('.langchoice.last') || document.querySelector('.langchoice')).focus();
};
document.querySelectorAll('.langchoice').forEach(b => {
  b.onclick = () => {
    try { localStorage.setItem('saqr-report-lang', b.dataset.lang); } catch (e) { /* ignore */ }
    $('langdialog').close();
    downloadReport('html', b.dataset.lang);
  };
});
$('langdialog').addEventListener('click', e => { if (e.target === $('langdialog')) $('langdialog').close(); });   // click outside
$('downloadjson').onclick = () => downloadReport('json');
$('delete').onclick = async () => {
  if (!current || !confirm(t('confirmDelete'))) return;
  try {
    await request('/api/reports/' + encodeURIComponent(current.id), { method: 'DELETE' });
    current = null;
    stopPolling();
    clear();
    await refresh();
    view('history');
  } catch (e) { alert(e.message); }
};
// ---------- start ----------
applyLang();
loadConfig();
checkAuth().then(() => {
  if (user) { view('dashboard'); loadDashboard(); } else view('landing');
});
