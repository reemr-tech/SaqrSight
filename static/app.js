'use strict';
// SaqrSight browser client. All server/user text is inserted with textContent (never innerHTML).
const $ = id => document.getElementById(id);
const IMG_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const VID_TYPES = ['video/mp4', 'video/quicktime', 'video/webm'];
let current = null, previewURL = null, busy = false, cfg = null, pollTimer = null, viewName = 'compose';
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
  $('breadcrumb').textContent = viewName === 'history' ? t('bcHistory') : viewName === 'results' ? t('bcReport') : t('bcNew');
}
function view(id) {
  viewName = id;
  for (const name of ['compose', 'results', 'history']) $(name).hidden = name !== id;
  $('newnav').classList.toggle('active', id !== 'history');
  $('historynav').classList.toggle('active', id === 'history');
  setBreadcrumb();
  window.scrollTo(0, 0);
  if (window.Motion) Motion.view(id);
}
function error(message) { $('error').textContent = message; $('error').hidden = !message; }
async function request(url, options) {
  const r = await fetch(url, options);
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
    refresh();
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
      const score = x.synthetic_score ?? x.agreement_score;
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
    banner.append(el('span', 'pill', L(a.label)), el('h2', null, L(a.explanation)));
    const pr = el('p', 'priority ' + a.priority.level, t('priority') + ': ' + L(a.priority.label));
    banner.append(pr, el('small', null, t('rule') + ' ' + a.rule + ' · ' + a.rules_version));
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
    const statusLabel = { completed: lang === 'ar' ? 'مكتمل' : 'Completed', not_applicable: lang === 'ar' ? 'غير منطبق' : 'Not applicable',
      not_configured: lang === 'ar' ? 'غير مُفعّل' : 'Not configured', failed: lang === 'ar' ? 'تعذّر الإكمال' : 'Failed',
      pending: lang === 'ar' ? 'قيد التنفيذ…' : 'Running…' }[status];
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
async function refresh() {
  try {
    const reports = await request('/api/reports');
    $('count').textContent = reports.length;
    $('historyintro').textContent = t('historyIntro', { days: cfg ? cfg.limits.retention_days : 30 });
    const list = $('historylist');
    list.replaceChildren();
    if (!reports.length) list.append(el('div', 'card empty', t('empty')));
    for (const r of reports) {
      const row = el('article', 'card historyitem');
      const d = el('div');
      const badge = r.mode === 'sample' ? t('sampleBadge') : [r.assessment && L({ en: r.assessment.replaceAll('_', ' '), ar: { potentially_misleading: 'قد يكون مضللاً', apparently_consistent: 'يبدو متسقاً', insufficient_evidence: 'أدلة غير كافية' }[r.assessment] }), r.status === 'processing' ? '…' : null].filter(Boolean).join(' · ');
      d.append(el('small', null, (badge ? badge.toUpperCase() + ' · ' : '') + new Date(r.created_at).toLocaleString(lang === 'ar' ? 'ar-AE' : undefined)));
      const cap = el('p', null, r.caption || t('imageOnly'));
      cap.dir = 'auto';
      d.append(cap);
      const open = el('button', 'secondary', t('open'));
      open.onclick = async () => {
        try {
          const p = await request('/api/reports/' + encodeURIComponent(r.id));
          showReport(p);
          if (p.status !== 'complete') poll(p.id);
        } catch (e) { alert(e.message); }
      };
      row.append(d, open);
      list.append(row);
    }
    if (viewName === 'history' && window.Motion) Motion.enter(list.children);
  } catch (e) {
    $('historylist').textContent = e.message;
  }
}

// ---------- wiring ----------
$('caption').oninput = updateChars;
$('language').onchange = updateChars;
$('media').onchange = preview;
$('remove').onclick = () => { $('media').value = ''; preview(); };
$('clear').onclick = clear;
$('another').onclick = clear;
$('newnav').onclick = () => { if (!busy) view('compose'); };
$('historynav').onclick = () => { if (busy) return; view('history'); refresh(); };
$('example').onclick = () => { $('caption').value = t('exampleText'); updateChars(); $('caption').focus(); };
for (const type of ['dragenter', 'dragover']) $('drop').addEventListener(type, e => { e.preventDefault(); $('drop').classList.add('drag'); });
for (const type of ['dragleave', 'drop']) $('drop').addEventListener(type, e => { e.preventDefault(); $('drop').classList.remove('drag'); });
$('drop').addEventListener('drop', e => {
  if (e.dataTransfer.files.length !== 1) { error(t('oneFile')); return; }
  $('media').files = e.dataTransfer.files;
  preview();
});
try { const saved = localStorage.getItem('saqr-report-lang'); if (saved) $('reportlang').value = saved; } catch (e) { /* ignore */ }
$('reportlang').onchange = () => { try { localStorage.setItem('saqr-report-lang', $('reportlang').value); } catch (e) { /* ignore */ } };
for (const format of ['html', 'json']) {
  $('download' + format).onclick = () => {
    if (!current) return;
    const extra = format === 'html' ? '&lang=' + encodeURIComponent($('reportlang').value) : '';
    window.location.href = '/api/reports/' + encodeURIComponent(current.id) + '/download?format=' + format + extra;
  };
}
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
view('compose');
applyLang();
loadConfig().then(refresh);
