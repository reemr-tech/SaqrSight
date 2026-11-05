"""Build the report sections from recorded module results, and render the standalone HTML export."""
from __future__ import annotations

import base64
import html
import io
from functools import lru_cache
from pathlib import Path

from .i18n_ar import LEVELS, MATCH_TYPES, REASONS, RELATIONS, ar, ar_all

STATUS = {
    "completed": {"en": "Completed", "ar": "مكتمل"},
    "not_applicable": {"en": "Not applicable", "ar": "غير منطبق"},
    "not_configured": {"en": "Not configured", "ar": "غير مُفعّل"},
    "failed": {"en": "Failed", "ar": "تعذّر الإكمال"},
    "pending": {"en": "Running…", "ar": "قيد التنفيذ…"},
}
TITLES = {
    "initial_assessment": {"en": "Initial Assessment", "ar": "التقييم الأولي"},
    "confidence": {"en": "Confidence", "ar": "مستوى الثقة"},
    "text_analysis": {"en": "Text Analysis", "ar": "تحليل النص"},
    "media_analysis": {"en": "Media Analysis", "ar": "تحليل الوسائط"},
    "consistency_check": {"en": "Consistency Check", "ar": "فحص الاتساق"},
    "issue_type": {"en": "Issue Type", "ar": "نوع المشكلة"},
    "review_priority": {"en": "Review Priority", "ar": "أولوية المراجعة"},
    "panic_language": {"en": "Panic-Related Language Indicators", "ar": "مؤشرات لغة الذعر"},
    "previous_media": {"en": "Previous Media Appearances", "ar": "ظهور سابق للوسائط"},
    "official_sources": {"en": "Official Source Evidence", "ar": "أدلة المصادر الرسمية"},
    "recommended_action": {"en": "Recommended Action", "ar": "الإجراء المقترح"},
}
MODULE_FOR = {"text_analysis": "text_analysis", "media_analysis": "media_analysis",
              "consistency_check": "consistency_check", "panic_language": "text_analysis",
              "previous_media": "reverse_image_search", "official_sources": "official_sources"}


def _section(key: str, status: str, summary: str, **kw) -> dict:
    kw.setdefault("summary_ar", ar(summary))
    return {"key": key, "title": TITLES[key], "status": status, "status_label": STATUS[status],
            "summary": summary, **{k: v for k, v in kw.items() if v}}


def _source(src: dict) -> dict:
    s = dict(src)
    if src.get("notes"):
        s["notes_ar"] = ar_all(src["notes"])
    if src.get("match_type"):
        s["match_type_ar"] = MATCH_TYPES.get(src["match_type"])
    if src.get("relation"):
        s["relation_ar"] = RELATIONS.get(src["relation"])
    if src.get("reasons"):
        s["reasons_ar"] = [REASONS.get(r, r) for r in src["reasons"]]
    return s


def _finding(f: dict) -> dict:
    d = f.get("details") or {}
    excerpts = f.get("excerpts") or []
    out = {"code": f["code"], "message": f["message"], "message_ar": d.get("explain_ar") or ar(f["message"]),
           "excerpts": excerpts, "frames": f.get("frames") or [],
           "sources": [_source(x) for x in f.get("sources") or []],
           "label": d.get("label_en"), "label_ar": d.get("label_ar")}
    if f["code"] == "needs_external_evidence":       # explanatory sentences, not caption quotes
        out["excerpts_ar"] = ar_all(excerpts)
    return out


def _mod_section(key: str, m: dict | None) -> dict:
    if m is None:
        return _section(key, "pending", "This check is still running.")
    summary = m.get("summary") or ""
    summary_ar = ar(summary)
    if m["status"] == "failed":
        reason = m.get("error") or "unknown error"
        summary = f"{summary} Reason: {reason}"
        summary_ar = f"{summary_ar or ''} السبب: {ar(reason) or reason}".strip()
    return _section(key, m["status"], summary, summary_ar=summary_ar,
                    findings=[_finding(f) for f in m.get("findings", [])],
                    limitations=m.get("limitations"), limitations_ar=ar_all(m.get("limitations")),
                    version=m.get("version"))


def build_sections(p: dict) -> list[dict]:
    mods = p.get("modules", {})
    a = p.get("assessment")
    sections = []
    if a:
        sections.append(_section("initial_assessment", "completed", a["explanation"]["en"],
                                 summary_ar=a["explanation"]["ar"], verdict=a["verdict"], label=a["label"],
                                 rule=f'{a["rule"]} ({a["rules_version"]})'))
    else:
        sections.append(_section("initial_assessment", "pending", "Waiting for all checks to finish."))

    conf_items, conf_ar = [], []
    for name in ("media_analysis", "consistency_check"):
        m = mods.get(name)
        if m and m["status"] == "completed":
            label = "AI-image detector" if name == "media_analysis" else "Caption–media consistency model"
            label_ar = "كاشف الصور المولدة" if name == "media_analysis" else "نموذج اتساق النص والوسائط"
            note = m["data"].get("validation_note", "")
            if m.get("confidence") == "validated":
                conf_items.append(f"{label}: evaluated model; output score {m['score']} (model output, not the "
                                  f"probability that the claim is true). {note}")
                conf_ar.append(f"{label_ar}: نموذج مُقيَّم؛ درجة المخرج {m['score']} (مخرج النموذج، وليست احتمال "
                               f"صحة الادعاء). {ar(note) or ''}".strip())
            else:
                conf_items.append(f"{label}: not validated for this application; no confidence is reported.")
                conf_ar.append(f"{label_ar}: لم يُتحقق منه لهذا التطبيق؛ لا يُعرض مستوى ثقة.")
    sections.append(_section("confidence", "completed" if conf_items else "not_applicable",
                             "Confidence applies to individual model findings only. No percentage is given for "
                             "whether the claim is true.",
                             summary_ar="ينطبق مستوى الثقة على نتائج النماذج المنفردة فقط. لا تُعطى نسبة مئوية لصحة الادعاء.",
                             items=conf_items, items_ar=conf_ar))
    sections.append(_mod_section("text_analysis", mods.get("text_analysis")))
    sections.append(_mod_section("media_analysis", mods.get("media_analysis")))
    sections.append(_mod_section("consistency_check", mods.get("consistency_check")))
    if a:
        it = a["issue_types"]
        sections.append(_section("issue_type", "completed",
                                 ", ".join(i["en"] for i in it) if it else "No supported issue classification.",
                                 summary_ar="، ".join(i["ar"] for i in it) if it else "لا يوجد تصنيف مدعوم للمشكلة.",
                                 issues=it))
        pr = a["priority"]
        sections.append(_section("review_priority", "completed", f'{pr["label"]["en"]} priority for human review.',
                                 summary_ar=f'أولوية {pr["label"]["ar"]} للمراجعة البشرية.',
                                 level=pr["level"], label=pr["label"], items=[r["en"] for r in pr["reasons"]],
                                 items_ar=[r["ar"] for r in pr["reasons"]]))
    else:
        sections.append(_section("issue_type", "pending", "Waiting for all checks to finish."))
        sections.append(_section("review_priority", "pending", "Waiting for all checks to finish."))

    t = mods.get("text_analysis")
    if t and t["status"] == "completed":
        lvl = t["data"]["indicator_level"]
        panic = [f for f in t["findings"] if f["code"] in ("urgency", "fear", "manipulation", "share_pressure")]
        sections.append(_section(
            "panic_language", "completed",
            f"Indicator level: {lvl}. These describe wording that may create urgency or "
            "alarm; they do not predict panic or show the claim is false.",
            summary_ar=f"مستوى المؤشرات: {LEVELS.get(lvl, lvl)}. تصف هذه المؤشرات صياغة قد تثير الاستعجال أو القلق؛ "
                       "ولا تتنبأ بالذعر ولا تثبت أن الادعاء كاذب.",
            level=lvl, findings=[_finding(f) for f in panic]))
    else:
        sections.append(_mod_section("panic_language", t))
    sections.append(_mod_section("previous_media", mods.get("reverse_image_search")))
    sections.append(_mod_section("official_sources", mods.get("official_sources")))
    acts = p.get("recommended_actions") or []
    sections.append(_section("recommended_action", "completed" if acts else "pending",
                             "Suggested next steps to verify this claim:" if acts else "Waiting for all checks to finish.",
                             summary_ar="الخطوات المقترحة للتحقق من هذا الادعاء:" if acts else None,
                             items=[x["en"] for x in acts], items_ar=[x["ar"] for x in acts]))
    return sections


# ------------------------------------------------------------------------------------------
CSS = """:root{--bg:#060a12;--panel:#0c1424;--panel2:#101b2f;--line:#1a2a44;--line2:#24395c;--ink:#dce8ff;--muted:#8fa3c4;
--dim:#62779a;--cyan:#22d3ee;--green:#2df5a6;--amber:#fbbf24;--red:#ff4d6d;--violet:#7c5cff;
--mono:ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,monospace;
--sans:system-ui,-apple-system,'Segoe UI','Geeza Pro','Noto Naskh Arabic',Tahoma,sans-serif}
*{box-sizing:border-box}
html{background:var(--bg);color-scheme:dark}
body{font:14.5px/1.65 var(--sans);max-width:980px;margin:0 auto;padding:32px 28px 56px;color:var(--ink);background:
linear-gradient(rgba(34,211,238,.03) 1px,transparent 1px) 0 0/32px 32px,
linear-gradient(90deg,rgba(34,211,238,.03) 1px,transparent 1px) 0 0/32px 32px,
radial-gradient(900px 500px at 90% -10%,rgba(34,211,238,.09),transparent 60%),var(--bg)}
p{margin:0 0 8px}ul{margin:4px 0 0;padding-inline-start:18px}li{margin:3px 0}
a{color:var(--cyan);font-weight:600;word-break:break-word}
small,.muted{color:var(--muted)}
.ar,[dir=rtl]{font-family:'Geeza Pro','Noto Naskh Arabic','Segoe UI',Tahoma,sans-serif}
/* masthead */
.mast{display:flex;justify-content:space-between;align-items:center;gap:20px;padding-bottom:18px;border-bottom:1px solid var(--line)}
.brand{display:flex;gap:14px;align-items:center}
.brand img{width:60px;height:60px;filter:drop-shadow(0 0 10px rgba(34,211,238,.35))}
.brand h1{font-size:27px;margin:0;letter-spacing:-.02em;color:#f1f6ff;line-height:1.1}
.brand small{font:600 11px/1.4 var(--mono);color:var(--cyan);letter-spacing:1.5px}
.mast-meta{font:12px/1.7 var(--mono);color:var(--muted);text-align:end}
.mast-meta b{color:var(--ink)}
.notice{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:18px 0 22px;padding:12px 16px;border:1px solid var(--line);
border-inline-start:3px solid var(--cyan);border-radius:6px;background:rgba(34,211,238,.05);color:var(--muted);font-size:13px}
/* parts */
.part{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin:34px 0 12px;padding-bottom:8px;
border-bottom:1px solid var(--line2)}
.part h2{font-size:18px;margin:0;color:#f1f6ff;letter-spacing:-.01em}
.part h2 span{font:700 13px var(--mono);color:var(--cyan);margin-inline-end:10px}
.part .ar{font-size:17px;font-weight:700;color:#f1f6ff}
/* cards */
.card{break-inside:avoid;background:linear-gradient(180deg,rgba(16,27,47,.95),rgba(12,20,36,.95));border:1px solid var(--line);
border-radius:8px;padding:16px 20px;margin:12px 0}
.card-head{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:12px;margin-bottom:12px;padding-bottom:10px;
border-bottom:1px dashed var(--line)}
.card-head h3{margin:0;font-size:15px;color:#eef4ff}
.card-head h3 .num{font:600 12px var(--mono);color:var(--dim);margin-inline-end:8px}
.card-head .ar{text-align:end;font-size:15px;font-weight:700;color:#eef4ff}
.bi{display:grid;grid-template-columns:1fr 1fr;gap:6px 28px}
.bi>.en{direction:ltr}
.bi>.ar{direction:rtl;text-align:right;color:#c9d6ef;border-left:1px solid var(--line);padding-left:18px}
.bi>ul.ar{padding-right:18px}
.bi+.bi{margin-top:6px}
.sub{font:600 11px/1 var(--mono);letter-spacing:1.4px;color:var(--cyan);text-transform:uppercase;margin:14px 0 6px}
.sub-bi{display:flex;justify-content:space-between;margin:14px 0 6px;font:600 11px/1 var(--mono);letter-spacing:1.2px;color:var(--cyan)}
.sub-bi .ar{font:700 12px/1 var(--sans);letter-spacing:0}
.finding{border-top:1px solid var(--line);padding-top:10px;margin-top:10px}
.finding:first-of-type{border-top:0;margin-top:0;padding-top:0}
/* chips */
.status{font:600 11px/1 var(--mono);padding:5px 10px;border-radius:99px;white-space:nowrap;background:rgba(45,245,166,.1);color:var(--green)}
.status.failed{background:rgba(255,77,109,.14);color:#ff8fa3}.status.not_configured{background:rgba(251,191,36,.12);color:var(--amber)}
.status.not_applicable{background:rgba(128,149,182,.12);color:var(--dim)}.status.pending{background:rgba(124,92,255,.16);color:#b6a5ff}
.chip{display:inline-block;font:12px/1 var(--mono);color:var(--cyan);background:rgba(34,211,238,.1);border-radius:3px;padding:5px 8px;margin:3px 4px 3px 0}
q{display:inline-block;background:rgba(251,191,36,.12);color:#fde68a;border:1px solid rgba(251,191,36,.3);border-radius:3px;
padding:1px 7px;margin:2px 4px 2px 0;quotes:none}
.prio{display:inline-block;font:700 12px/1 var(--mono);padding:7px 12px;border-radius:99px}
.prio.high{background:rgba(255,77,109,.15);color:#ff8fa3;box-shadow:0 0 0 1px rgba(255,77,109,.35)}
.prio.medium{background:rgba(251,191,36,.13);color:var(--amber);box-shadow:0 0 0 1px rgba(251,191,36,.3)}
.prio.low{background:rgba(45,245,166,.1);color:var(--green);box-shadow:0 0 0 1px rgba(45,245,166,.3)}
/* summary */
.summary{border-width:1px;border-top:3px solid var(--cyan);padding:20px 22px}
.summary.v-potentially_misleading{border-color:rgba(255,77,109,.5);border-top-color:var(--red);background:linear-gradient(120deg,rgba(255,77,109,.13),rgba(12,20,36,.96) 55%)}
.summary.v-apparently_consistent{border-color:rgba(45,245,166,.45);border-top-color:var(--green);background:linear-gradient(120deg,rgba(45,245,166,.10),rgba(12,20,36,.96) 55%)}
.summary.v-insufficient_evidence{border-color:rgba(251,191,36,.42);border-top-color:var(--amber);background:linear-gradient(120deg,rgba(251,191,36,.10),rgba(12,20,36,.96) 55%)}
.verdict{display:grid;grid-template-columns:1fr 1fr;gap:28px;align-items:end;margin-bottom:12px}
.verdict .lbl{font:600 11px/1 var(--mono);letter-spacing:1.5px;color:var(--muted);margin-bottom:6px}
.verdict .val{font-size:26px;font-weight:800;letter-spacing:-.02em;line-height:1.15}
.verdict .ar{text-align:right}
.v-potentially_misleading .val{color:#ff8fa3}.v-apparently_consistent .val{color:var(--green)}.v-insufficient_evidence .val{color:var(--amber)}
.facts{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:16px}
.fact{background:rgba(7,13,24,.65);border:1px solid var(--line);border-radius:6px;padding:10px 12px}
.fact .k{font:600 10.5px/1.3 var(--mono);letter-spacing:1.2px;color:var(--dim);display:flex;justify-content:space-between;gap:6px}
.fact .k .ar{font:700 11px var(--sans);letter-spacing:0}
.fact .v{margin-top:6px;font-size:13.5px}
/* tables */
table{width:100%;border-collapse:collapse;font-size:13px}
th{font:600 10.5px/1.3 var(--mono);letter-spacing:1.2px;color:var(--dim);text-align:start;padding:8px 10px;border-bottom:1px solid var(--line2)}
th.ar,td.ar{text-align:right;direction:rtl}
td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
td .name{font-weight:600;color:#eef4ff}
/* submitted content */
.caption{background:rgba(7,13,24,.8);border:1px solid var(--line);border-radius:6px;padding:12px 16px;white-space:pre-wrap;font-size:15px}
.media{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}
.media figure{margin:0;border:1px solid var(--line2);border-radius:6px;overflow:hidden;background:#070d18}
.media img{display:block;max-height:190px;max-width:100%}
.media figcaption{font:11px/1.4 var(--mono);color:var(--muted);padding:5px 8px}
/* sources */
.src{border-inline-start:3px solid var(--cyan);padding:6px 12px;margin:8px 0;background:rgba(7,13,24,.45);border-radius:0 6px 6px 0}
.src .meta{font:12px/1.6 var(--mono);color:var(--muted)}
/* appendix */
.appx td{font-size:12.5px;color:var(--muted)}
.appx td .name{color:var(--ink)}
footer{margin-top:30px;padding-top:14px;border-top:1px solid var(--line);font-size:12px;color:var(--dim)}
footer .bi{gap:6px 28px}
.notice.one,.verdict.one{grid-template-columns:1fr}
.ar,.ar *,[dir=rtl],[dir=rtl] *{letter-spacing:0!important}
.mode-ar .lbl,.mode-ar .fact .k,.mode-ar .sub-bi,.mode-ar th,.mode-ar .status,.mode-ar .brand small,.mode-ar .mast-meta,
.mode-ar .chip,.mode-ar .part h2 span,.mode-ar .card-head .num{font-family:var(--sans);font-size:12.5px;font-weight:700}
.mode-ar .verdict .lbl,.mode-ar .fact .k,.mode-ar .sub-bi{font-size:13px}
.mode-en .card-head,.mode-ar .card-head{grid-template-columns:1fr auto}
.mode-ar{font-family:'Geeza Pro','Noto Naskh Arabic','Segoe UI',Tahoma,sans-serif}
.mode-ar .mast-meta{text-align:start}.mode-ar th{text-align:right}
.mode-ar .src{border-radius:6px 0 0 6px}
@media(max-width:700px){.bi,.verdict,.notice{grid-template-columns:1fr}.bi>.ar{border:0;padding-left:0}.facts{grid-template-columns:1fr}
.card-head{grid-template-columns:1fr}.card-head .ar{text-align:right}.mast{flex-direction:column;align-items:flex-start}.mast-meta{text-align:start}}
@media print{
@page{size:A4;margin:14mm}
html,body{background:#fff!important;color:#111}
body{padding:0;max-width:none;font-size:11.5pt}
.card,.notice,.caption,.fact,.src,.media figure{background:#fff!important;border-color:#c9d1dc!important;color:#111}
.summary{border-top-width:4px}
h1,h2,h3,.ar,.part .ar,.card-head .ar,small,.muted,.mast-meta,.mast-meta b,footer,.brand small,.verdict .lbl,.fact .k,th,
.bi>.ar,.appx td,td .name,.src .meta,.sub,.sub-bi,.part h2 span{color:#111!important}
.status,.prio,.chip,q{background:#f1f3f7!important;color:#111!important;border:1px solid #c9d1dc!important;box-shadow:none!important}
.verdict .val{color:#111!important}a{color:#0a58a0}.brand img{filter:none}
.part{break-after:avoid}
}"""

PART_TITLES = [
    ("Content analysis", "تحليل المحتوى", ["text_analysis", "panic_language", "media_analysis", "consistency_check"]),
    ("Evidence from other sources", "أدلة من مصادر أخرى", ["previous_media", "official_sources"]),
    ("Assessment details", "تفاصيل التقييم", ["confidence", "issue_type"]),
    ("Next steps", "الخطوات التالية", ["recommended_action"]),
]
CHECKS = [("text_analysis", "Text indicators", "مؤشرات النص"),
          ("media_analysis", "AI-generated media signal", "إشارة الوسائط المولدة"),
          ("consistency_check", "Caption–media consistency", "اتساق النص والوسائط"),
          ("reverse_image_search", "Reverse image search", "البحث العكسي عن الصور"),
          ("official_sources", "Official UAE sources", "المصادر الرسمية في الدولة")]
LANG_NAMES = {"en": ("English", "الإنجليزية"), "ar": ("Arabic", "العربية"), "mixed": ("Arabic and English", "عربي وإنجليزي"),
              "not applicable": ("Not applicable", "غير منطبق")}
AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


@lru_cache(maxsize=1)
def logo_data_uri() -> str:
    """The SaqrSight logo embedded in the export, so the HTML file works on its own (offline, emailed)."""
    path = Path(__file__).resolve().parent.parent / "static" / "logo.png"
    try:
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("RGBA")
            im.thumbnail((128, 128))
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except OSError:
        return ""


def _e(x) -> str:
    return html.escape(str(x))


class _Lang:
    """Renders bilingual content in one of three modes: "en", "ar" or "both" (side by side)."""

    def __init__(self, mode: str):
        self.mode = mode if mode in ("en", "ar", "both") else "both"

    def pick(self, en, ar_text):
        return ar_text or en if self.mode == "ar" else en

    def bi(self, en, ar_text, tag="p") -> str:
        if not en and not ar_text:
            return ""
        if self.mode == "both":
            return (f'<div class="bi"><{tag} class="en">{_e(en or "")}</{tag}>'
                    f'<{tag} class="ar" dir="rtl">{_e(ar_text or "")}</{tag}></div>')
        return f"<{tag}>{_e(self.pick(en, ar_text))}</{tag}>"

    def bilist(self, en_items, ar_items) -> str:
        en_items, ar_items = en_items or [], ar_items or []
        if not en_items and not ar_items:
            return ""
        li = lambda xs: "".join(f"<li>{_e(x)}</li>" for x in xs)  # noqa: E731
        if self.mode == "both":
            return f'<div class="bi"><ul class="en">{li(en_items)}</ul><ul class="ar" dir="rtl">{li(ar_items)}</ul></div>'
        return f"<ul>{li(ar_items if self.mode == 'ar' and ar_items else en_items)}</ul>"

    def pair(self, en, ar_text) -> str:
        """Short inline label: 'English · عربي' in both mode, otherwise one language."""
        if self.mode == "both":
            return f'{_e(en)} · <span dir="rtl">{_e(ar_text)}</span>'
        return _e(self.pick(en, ar_text))

    def heading(self, en, ar_text, extra_en="") -> str:
        """Two labels at the ends of a row (both), or a single label."""
        if self.mode == "both":
            return f'<span>{_e(en)}{extra_en}</span><span class="ar" dir="rtl">{_e(ar_text)}</span>'
        return f"<span>{_e(self.pick(en, ar_text))}</span>"


def _when(iso: str) -> tuple[str, str]:
    from datetime import datetime
    try:
        d = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso, iso
    t = d.strftime("%H:%M")
    return (f"{d.day} {d.strftime('%B %Y')}, {t} UTC", f"{d.day} {AR_MONTHS[d.month - 1]} {d.year}، الساعة {t} (UTC)")


def _status(L: _Lang, s: dict) -> str:
    return f'<span class="status {_e(s["status"])}">{L.pair(s["status_label"]["en"], s["status_label"]["ar"])}</span>'


def _finding_html(L: _Lang, f: dict) -> str:
    out = ['<div class="finding">']
    en_msg = (f"{f['label']}: " if f.get("label") else "") + f["message"]
    ar_msg = ((f"{f['label_ar']}: " if f.get("label_ar") else "") + f["message_ar"]) if f.get("message_ar") else ""
    out.append(L.bi(en_msg, ar_msg))
    if f.get("excerpts_ar"):                       # explanatory lines with an Arabic version
        out.append(L.bilist(f["excerpts"], f["excerpts_ar"]))
    elif f.get("excerpts"):                        # exact caption quotes: shown as written
        out.append(f'<div class="sub-bi">{L.heading("EXCERPTS FROM THE CAPTION", "مقتطفات من النص")}</div>'
                   + "<div>" + "".join(f'<q dir="auto">{_e(x)}</q>' for x in f["excerpts"]) + "</div>")
    if f.get("frames"):
        chips = []
        for fr in f["frames"]:
            ts = f' · {fr["timestamp"]}s' if "timestamp" in fr else ""
            word = "الدرجة" if L.mode == "ar" else "score"
            sc = next((f" · {word} {fr[k]}" for k in ("synthetic_score", "agreement_score") if k in fr), "")
            ref = fr["ref"]
            if L.mode == "ar":
                ref = "الصورة" if ref == "image" else ref.replace("frame-", "لقطة ")
                ts = f' · {fr["timestamp"]} ث' if "timestamp" in fr else ""
            chips.append(f'<span class="chip">{_e(ref)}{_e(ts)}{_e(sc)}</span>')
        out.append("<div>" + "".join(chips) + "</div>")
    for src in f.get("sources", []):
        meta_en = " · ".join(x for x in (src.get("source"), src.get("date") or "date not available",
                                          src.get("match_type"), src.get("relation")) if x)
        meta_ar = " · ".join(x for x in (src.get("source"), src.get("date") or "التاريخ غير متاح",
                                          src.get("match_type_ar"), src.get("relation_ar")) if x)
        block = (f'<div class="src"><a href="{_e(src["url"])}" rel="noopener noreferrer">{_e(src.get("title") or src["url"])}</a>'
                 + L.bi(meta_en, meta_ar, "div").replace('class="bi"', 'class="bi meta"', 1).replace("<div>", '<div class="meta">', 1))
        if src.get("excerpt"):
            block += f'<q dir="auto">{_e(src["excerpt"])}</q>'
        if src.get("notes"):
            block += L.bi("; ".join(src["notes"]), "؛ ".join(src.get("notes_ar") or []), "div")
        if src.get("reasons"):
            block += L.bi(", ".join(src["reasons"]), "، ".join(src.get("reasons_ar") or []), "div")
        out.append(block + "</div>")
    out.append("</div>")
    return "".join(out)


def _card(L: _Lang, s: dict, num: str) -> str:
    body = [L.bi(s["summary"], s.get("summary_ar"))]
    if s["key"] == "review_priority" and s.get("label"):
        body.insert(0, f'<p><span class="prio {_e(s.get("level", ""))}">{L.pair(s["label"]["en"], s["label"]["ar"])}</span></p>')
    body.append(L.bilist(s.get("items"), s.get("items_ar")))
    body += [_finding_html(L, f) for f in s.get("findings", [])]
    title_ar = f'<div class="ar" dir="rtl">{_e(s["title"]["ar"])}</div>' if L.mode == "both" else ""
    return (f'<section class="card"><div class="card-head"><h3><span class="num">{_e(num)}</span>{_e(L.pick(s["title"]["en"], s["title"]["ar"]))}</h3>'
            f'{_status(L, s)}{title_ar}</div>{"".join(body)}</section>')


def _part(L: _Lang, num: str, en: str, ar_title: str) -> str:
    side = f'<div class="ar" dir="rtl">{_e(ar_title)}</div>' if L.mode == "both" else ""
    return f'<div class="part"><h2><span>{_e(num)}</span>{_e(L.pick(en, ar_title))}</h2>{side}</div>'


def render_html(p: dict, images: list[dict] | None = None, lang: str = "both") -> str:
    """Standalone report. lang: "en", "ar" or "both" (side by side).
    images: [{"ref", "timestamp", "uri"}] thumbnails to embed (optional)."""
    if p.get("mode") == "sample":
        return render_legacy_sample(p)
    L = _Lang(lang)
    sec = {s["key"]: s for s in p.get("sections", [])}
    a = p.get("assessment") or {}
    mods = p.get("modules", {})
    when_en, when_ar = _when(p.get("created_at", ""))
    lang_en, lang_ar = LANG_NAMES.get(p.get("language"), (p.get("language"), p.get("language")))
    uri = logo_data_uri()

    # ---- summary ----
    verdict = a.get("verdict", "pending")
    label = a.get("label") or {"en": "Pending", "ar": "قيد الانتظار"}
    pr = a.get("priority") or {}
    prl = pr.get("label") or {"en": "—", "ar": "—"}
    issues = a.get("issue_types") or []
    if L.mode == "both":
        verdict_html = (f'<div class="verdict"><div><div class="lbl">INITIAL ASSESSMENT</div><div class="val">{_e(label["en"])}</div></div>'
                        f'<div class="ar" dir="rtl"><div class="lbl">التقييم الأولي</div><div class="val">{_e(label["ar"])}</div></div></div>')
    else:
        verdict_html = (f'<div class="verdict one"><div><div class="lbl">{_e(L.pick("INITIAL ASSESSMENT", "التقييم الأولي"))}</div>'
                        f'<div class="val">{_e(L.pick(label["en"], label["ar"]))}</div></div></div>')
    fact = lambda en, ar_t, v: (f'<div class="fact"><div class="k">{L.heading(en, ar_t)}</div><div class="v">{v}</div></div>')  # noqa: E731
    summary = (
        f'<section class="card summary v-{_e(verdict)}">{verdict_html}'
        + L.bi((a.get("explanation") or {}).get("en"), (a.get("explanation") or {}).get("ar"))
        + '<div class="facts">'
        + fact("REVIEW PRIORITY", "أولوية المراجعة", f'<span class="prio {_e(pr.get("level", ""))}">{L.pair(prl["en"], prl["ar"])}</span>')
        + fact("ISSUE TYPE", "نوع المشكلة", "".join(f"<div>{L.pair(i['en'], i['ar'])}</div>" for i in issues)
               or L.pair("None identified", "لم يُحدَّد"))
        + fact("DECISION RULE", "قاعدة القرار", f'{_e(a.get("rule", "—"))} · {_e(a.get("rules_version", ""))}')
        + "</div>"
        + f'<div class="sub-bi">{L.heading("WHY THIS PRIORITY", "أسباب الأولوية")}</div>'
        + L.bilist([r["en"] for r in pr.get("reasons", [])], [r["ar"] for r in pr.get("reasons", [])])
        + "</section>")

    # ---- checks table ----
    rows = []
    for key, en, ar_name in CHECKS:
        m = mods.get(key) or {"status": "pending", "summary": ""}
        st = {"status": m["status"], "status_label": STATUS.get(m["status"], STATUS["pending"])}
        en_cell = f'<td><span class="name">{_e(en)}</span><br><small>{_e(m.get("summary", ""))}</small></td>'
        ar_cell = (f'<td class="ar" dir="rtl"><span class="name">{_e(ar_name)}</span><br>'
                   f'<small>{_e(ar(m.get("summary")) or m.get("summary", ""))}</small></td>')
        if L.mode == "both":
            rows.append(f"<tr>{en_cell}<td>{_status(L, st)}</td>{ar_cell}</tr>")
        elif L.mode == "ar":
            rows.append(f"<tr>{ar_cell}<td>{_status(L, st)}</td></tr>")
        else:
            rows.append(f"<tr>{en_cell}<td>{_status(L, st)}</td></tr>")
    head = {"both": '<th>CHECK · RESULT</th><th>STATUS · <span dir="rtl">الحالة</span></th><th class="ar">الفحص · النتيجة</th>',
            "en": "<th>CHECK · RESULT</th><th>STATUS</th>", "ar": '<th class="ar">الفحص · النتيجة</th><th>الحالة</th>'}[L.mode]
    checks = f'<section class="card"><table><thead><tr>{head}</tr></thead><tbody>' + "".join(rows) + "</tbody></table></section>"

    # ---- submitted content ----
    media = p.get("media")
    media_en, media_ar = "No image or video supplied", "لم تُقدَّم صورة أو فيديو"
    if media:
        kind_ar = "صورة" if media["kind"] == "image" else "فيديو"
        media_en = f'{media["kind"].capitalize()}: {media["original_name"]} ({media["width"]}×{media["height"]})'
        media_ar = f'{kind_ar}: \u2066{media["original_name"]} ({media["width"]}×{media["height"]})\u2069'
        if media["kind"] == "video":
            ts = ", ".join(f'{v["timestamp"]}s' for v in media["visuals"])
            media_en += f' · {media["duration"]}s. Findings apply only to the sampled frames at {ts}.'
            media_ar += f' · {media["duration"]} ثانية. تنطبق النتائج على اللقطات المأخوذة فقط عند {ts}.'
    figs = "".join(
        f'<figure><img src="{_e(im["uri"])}" alt="{_e(im["ref"])}"><figcaption>{_e(im["ref"])}'
        + (f' · {im["timestamp"]}s' if im.get("timestamp") is not None else "") + "</figcaption></figure>"
        for im in images or [])
    content = (f'<section class="card"><div class="sub-bi">{L.heading("CAPTION AS SUBMITTED", "النص كما أُرسل")}</div>'
               f'<div class="caption" dir="auto">{_e(p.get("caption") or L.pick("No text supplied", "لم يُقدَّم نص"))}</div>'
               f'<div class="sub-bi">{L.heading("MEDIA", "الوسائط")}</div>'
               + L.bi(media_en, media_ar)
               + (f'<div class="media">{figs}</div>' if figs else "") + "</section>")

    # ---- numbered parts ----
    parts = []
    for i, (en, ar_title, keys) in enumerate(PART_TITLES, start=1):
        cards = "".join(_card(L, sec[k], f"{i}.{j}") for j, k in enumerate([k for k in keys if k in sec], start=1))
        parts.append(_part(L, f"{i:02d}", en, ar_title) + cards)

    # ---- appendix ----
    appx_rows = []
    for key, en, ar_name in CHECKS:
        m = mods.get(key)
        if not m:
            continue
        en_cell = (f'<td><span class="name">{_e(en)}</span><br><small>{_e(m.get("version", ""))}</small>'
                   + "".join(f"<div>• {_e(x)}</div>" for x in m.get("limitations", [])) + "</td>")
        ar_cell = (f'<td class="ar" dir="rtl"><span class="name">{_e(ar_name)}</span><br><small>{_e(m.get("version", ""))}</small>'
                   + "".join(f"<div>• {_e(x)}</div>" for x in ar_all(m.get("limitations"))) + "</td>")
        appx_rows.append("<tr>" + {"both": en_cell + ar_cell, "en": en_cell, "ar": ar_cell}[L.mode] + "</tr>")
    appx_head = {"both": '<th>CHECK · VERSION · LIMITATIONS</th><th class="ar">الفحص · الإصدار · القيود</th>',
                 "en": "<th>CHECK · VERSION · LIMITATIONS</th>", "ar": '<th class="ar">الفحص · الإصدار · القيود</th>'}[L.mode]
    rules_v = a.get("rules_version", "")
    appendix = (_part(L, "A", "Appendix: methods and limitations", "ملحق: المنهجية والقيود")
                + f'<section class="card appx"><table><thead><tr>{appx_head}</tr></thead><tbody>' + "".join(appx_rows)
                + "</tbody></table>"
                + L.bi(f"Decision rules {rules_v}: model scores are never averaged into a truth score. Urgent wording, "
                       "an AI-generation signal or a failed search can never make a claim misleading on their own.",
                       f"قواعد القرار {rules_v}: لا تُدمج درجات النماذج في درجة صحة واحدة. لا تكفي الصياغة العاجلة أو إشارة "
                       "التوليد بالذكاء الاصطناعي أو فشل البحث وحدها لاعتبار الادعاء مضللاً.")
                + "</section>")

    consent_en = "permitted by user" if p.get("consent_external") else "not permitted by user"
    consent_ar = "بإذن المستخدم" if p.get("consent_external") else "دون إذن المستخدم"
    notice_ar = ("تقييم أولي صادر عن فحوص آلية. يدعم التحقق البشري ولا يحل محله. "
                 "النتائج المعلَّمة بـ«غير مُفعّل» أو «تعذّر الإكمال» لم تُقيَّم.")
    notice = (f'<div class="notice"><div>{_e(p.get("notice", ""))}</div><div class="ar" dir="rtl">{_e(notice_ar)}</div></div>'
              if L.mode == "both" else f'<div class="notice one"><div>{_e(L.pick(p.get("notice", ""), notice_ar))}</div></div>')
    when = (f'{_e(when_en)}<br><span dir="rtl">{_e(when_ar)}</span>' if L.mode == "both" else _e(L.pick(when_en, when_ar)))
    subtitle = {"both": "INITIAL ASSESSMENT REPORT · تقرير تقييم أولي", "en": "INITIAL ASSESSMENT REPORT",
                "ar": "تقرير تقييم أولي"}[L.mode]
    html_attrs = 'lang="ar" dir="rtl"' if L.mode == "ar" else 'lang="en"'
    footer = L.bi(
        f"Report ID {p['id']} · text language: {lang_en} · external searches: {consent_en} · "
        f"SaqrSight {p.get('version', '')} (SGP2 analysis prototype). This is an initial assessment to support "
        "human judgement, not a fact-check verdict.",
        f"معرّف التقرير {p['id']} · لغة النص: {lang_ar} · البحث الخارجي: {consent_ar} · صقر {p.get('version', '')} "
        "(نموذج التحليل، المرحلة الثانية). هذا تقييم أولي لدعم الحكم البشري وليس حكماً نهائياً للتحقق من الحقائق.", "div")
    return f"""<!doctype html><html {html_attrs}><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SaqrSight report · {_e(p["id"][:8])}</title><style>{CSS}</style>
<body class="mode-{L.mode}">
<header class="mast"><div class="brand">{f'<img src="{uri}" alt="SaqrSight logo">' if uri else ""}<div><h1>SaqrSight · صقر</h1>
<small>{_e(subtitle)}</small></div></div>
<div class="mast-meta"><b>{_e(L.pick("Report", "التقرير"))}</b> {_e(p["id"][:8].upper())}<br>{when}</div></header>
{notice}
{_part(L, "00", "Summary", "الملخص")}
{summary}
<div class="sub-bi">{L.heading("CHECKS PERFORMED", "الفحوص المنفذة")}</div>
{checks}
{_part(L, "·", "Submitted content", "المحتوى المرسل")}
{content}
{"".join(parts)}
{appendix}
<footer>{footer}</footer></body></html>"""


def render_legacy_sample(p: dict) -> str:
    """SGP1 sample reports keep their original layout and SAMPLE labelling."""
    sections = "".join(f'<section class="card"><h3>{_e(s["title"])}</h3><p>{_e(s["finding"])}</p></section>' for s in p["sections"])
    image = _e(p["image"]["original_name"]) if p.get("image") else "Not supplied"
    return (f'<!doctype html><html lang="en"><meta charset="utf-8"><title>SaqrSight sample report</title>'
            f'<style>{CSS}</style><header class="mast"><div class="brand"><div><h1>SaqrSight · صقر</h1><small>SGP1 SAMPLE REPORT · تقرير تجريبي</small></div></div></header><div class="notice"><div>{_e(p["notice"])}</div><div class="ar" dir="rtl">عرض توضيحي لسير العمل فقط. جميع النتائج نصوص مؤقتة وليست نتائج ذكاء اصطناعي.</div></div>'
            f'<p>Report ID: {_e(p["id"])}<br>Created: {_e(p["created_at"])}<br>Language: {_e(p["language"])}</p>'
            f'<h2>Submitted text</h2><pre dir="auto">{_e(p["caption"] or "No text supplied.")}</pre>'
            f'<p>Image: {image}</p>{sections}<footer>Milestone 1 · Local workflow prototype (SGP1)</footer></html>')
