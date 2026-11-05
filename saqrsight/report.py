"""Build the report sections from recorded module results, and render the standalone HTML export."""
from __future__ import annotations

import base64
import html
import io
from functools import lru_cache
from pathlib import Path

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
    return {"key": key, "title": TITLES[key], "status": status, "status_label": STATUS[status],
            "summary": summary, **{k: v for k, v in kw.items() if v}}


def _mod_section(key: str, m: dict | None) -> dict:
    if m is None:
        return _section(key, "pending", "This check is still running.")
    findings = [{"code": f["code"], "message": f["message"], "excerpts": f.get("excerpts") or [],
                 "frames": f.get("frames") or [], "sources": f.get("sources") or [],
                 "label": (f.get("details") or {}).get("label_en"),
                 "label_ar": (f.get("details") or {}).get("label_ar")}
                for f in m.get("findings", [])]
    summary = m.get("summary") or ""
    if m["status"] == "failed":
        summary = f"{summary} Reason: {m.get('error') or 'unknown error'}"
    return _section(key, m["status"], summary, findings=findings, limitations=m.get("limitations"),
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

    conf_items = []
    for name in ("media_analysis", "consistency_check"):
        m = mods.get(name)
        if m and m["status"] == "completed":
            label = "AI-image detector" if name == "media_analysis" else "Caption–media consistency model"
            if m.get("confidence") == "validated":
                conf_items.append(f"{label}: evaluated model; output score {m['score']} (model output, not the "
                                  f"probability that the claim is true). {m['data'].get('validation_note', '')}")
            else:
                conf_items.append(f"{label}: not validated for this application; no confidence is reported.")
    sections.append(_section("confidence", "completed" if conf_items else "not_applicable",
                             "Confidence applies to individual model findings only. No percentage is given for "
                             "whether the claim is true.", items=conf_items))
    sections.append(_mod_section("text_analysis", mods.get("text_analysis")))
    sections.append(_mod_section("media_analysis", mods.get("media_analysis")))
    sections.append(_mod_section("consistency_check", mods.get("consistency_check")))
    if a:
        it = a["issue_types"]
        sections.append(_section("issue_type", "completed",
                                 ", ".join(i["en"] for i in it) if it else "No supported issue classification.",
                                 items_ar=[i["ar"] for i in it]))
        pr = a["priority"]
        sections.append(_section("review_priority", "completed", f'{pr["label"]["en"]} priority for human review.',
                                 level=pr["level"], label=pr["label"], items=[r["en"] for r in pr["reasons"]],
                                 items_ar=[r["ar"] for r in pr["reasons"]]))
    else:
        sections.append(_section("issue_type", "pending", "Waiting for all checks to finish."))
        sections.append(_section("review_priority", "pending", "Waiting for all checks to finish."))

    t = mods.get("text_analysis")
    if t and t["status"] == "completed":
        panic = [f for f in t["findings"] if f["code"] in ("urgency", "fear", "manipulation", "share_pressure")]
        sections.append(_section(
            "panic_language", "completed",
            f'Indicator level: {t["data"]["indicator_level"]}. These describe wording that may create urgency or '
            "alarm; they do not predict panic or show the claim is false.",
            findings=[{"code": f["code"], "label": f["details"]["label_en"], "label_ar": f["details"]["label_ar"],
                       "message": f["message"], "excerpts": f["excerpts"]} for f in panic]))
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
CSS = """:root{--bg:#060a12;--panel:#0c1424;--panel2:#101b2f;--line:#1a2a44;--line2:#24395c;--ink:#dce8ff;--muted:#8095b6;
--dim:#5b6f90;--cyan:#22d3ee;--green:#2df5a6;--amber:#fbbf24;--red:#ff4d6d;--violet:#7c5cff;
--mono:ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
html{background:var(--bg);color-scheme:dark}
body{font:15px/1.6 system-ui,-apple-system,'Segoe UI',Tahoma,sans-serif;max-width:900px;margin:0 auto;padding:36px 22px 48px;
color:var(--ink);background:
linear-gradient(rgba(34,211,238,.035) 1px,transparent 1px) 0 0/32px 32px,
linear-gradient(90deg,rgba(34,211,238,.035) 1px,transparent 1px) 0 0/32px 32px,
radial-gradient(900px 500px at 90% -10%,rgba(34,211,238,.09),transparent 60%),var(--bg)}
h1{font-size:28px;margin:0;letter-spacing:-.02em;color:#f1f6ff}h2{font-size:16px;margin:0 0 8px;color:#eef4ff}
header{display:flex;gap:16px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:20px}
header img{width:58px;height:58px;filter:drop-shadow(0 0 10px rgba(34,211,238,.35))}
header small{font-family:var(--mono);color:var(--cyan);letter-spacing:1px}
aside{padding:12px 16px;background:rgba(34,211,238,.06);border:1px solid var(--line);border-inline-start:3px solid var(--cyan);
border-radius:6px;margin:16px 0;color:var(--muted)}
.meta{font-family:var(--mono);font-size:12.5px;color:var(--muted);background:rgba(12,20,36,.7);border:1px solid var(--line);
border-radius:6px;padding:12px 16px;line-height:1.8}
.meta b{color:var(--ink);font-weight:600}
section{break-inside:avoid;background:linear-gradient(180deg,rgba(16,27,47,.95),rgba(12,20,36,.95));border:1px solid var(--line);
border-top:2px solid var(--cyan);border-radius:8px;padding:16px 20px;margin:14px 0}
section.st-failed{border-top-color:var(--red)}section.st-not_configured{border-top-color:var(--amber)}
section.st-not_applicable{border-top-color:var(--line2)}
.status{float:inline-end;font:600 11px/1 var(--mono);padding:5px 9px;border-radius:99px;background:rgba(45,245,166,.1);color:var(--green)}
.status.failed{background:rgba(255,77,109,.14);color:#ff8fa3}.status.not_configured{background:rgba(251,191,36,.12);color:var(--amber)}
.status.not_applicable{background:rgba(128,149,182,.12);color:var(--dim)}.status.pending{background:rgba(124,92,255,.16);color:#b6a5ff}
.verdict{font-size:22px;font-weight:700;margin:6px 0 10px}
section.v-potentially_misleading{border-color:rgba(255,77,109,.5);border-top-color:var(--red);
background:linear-gradient(120deg,rgba(255,77,109,.12),rgba(12,20,36,.96) 55%)}
section.v-apparently_consistent{border-color:rgba(45,245,166,.45);border-top-color:var(--green);
background:linear-gradient(120deg,rgba(45,245,166,.10),rgba(12,20,36,.96) 55%)}
section.v-insufficient_evidence{border-color:rgba(251,191,36,.42);border-top-color:var(--amber);
background:linear-gradient(120deg,rgba(251,191,36,.10),rgba(12,20,36,.96) 55%)}
.v-potentially_misleading .verdict{color:#ff8fa3}.v-apparently_consistent .verdict{color:var(--green)}
.v-insufficient_evidence .verdict{color:var(--amber)}
.prio{display:inline-block;font:700 12px/1 var(--mono);padding:6px 10px;border-radius:99px;margin:2px 0 8px}
.prio.high{background:rgba(255,77,109,.15);color:#ff8fa3}.prio.medium{background:rgba(251,191,36,.13);color:var(--amber)}
.prio.low{background:rgba(45,245,166,.1);color:var(--green)}
.ar{direction:rtl;text-align:right;color:#b9c8e4}
li{margin:3px 0}
q{background:rgba(251,191,36,.12);color:#fde68a;border:1px solid rgba(251,191,36,.3);border-radius:3px;padding:1px 6px;quotes:none;
line-height:2}
small{color:var(--muted)}
.chip{display:inline-block;font:12px/1 var(--mono);color:var(--cyan);background:rgba(34,211,238,.1);border-radius:3px;padding:4px 7px;margin:2px 4px 2px 0}
.src{border-inline-start:3px solid var(--cyan);padding:4px 12px;margin:8px 0}
a{color:var(--cyan);font-weight:600;word-break:break-word}
pre{white-space:pre-wrap;font:inherit;background:rgba(7,13,24,.8);border:1px solid var(--line);border-radius:6px;padding:12px 16px;margin:0}
.label{font:600 11px/1 var(--mono);color:var(--cyan);letter-spacing:1.5px;text-transform:uppercase;margin:22px 0 8px}
footer{margin-top:28px;padding-top:14px;border-top:1px solid var(--line);font-family:var(--mono);font-size:12px;color:var(--dim)}
@media print{
html,body{background:#fff!important;color:#111}
body{padding:0;max-width:none}
section,aside,.meta,pre{background:#fff!important;border-color:#ccd!important;color:#111}
h1,h2,.ar,small,.meta b,footer,header small{color:#111!important}
.status,.prio,.chip,q{background:#f1f3f7!important;color:#111!important;border-color:#ccd!important}
.verdict{color:#111!important}a{color:#0a58a0}
section{border-top-width:3px}
}"""


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


def _header(subtitle: str) -> str:
    uri = logo_data_uri()
    img = f'<img src="{uri}" alt="SaqrSight logo">' if uri else ""
    return f'<header>{img}<div><h1>SaqrSight · صقر</h1><small>{subtitle}</small></div></header>'


def _e(x) -> str:
    return html.escape(str(x))


def render_html(p: dict) -> str:
    if p.get("mode") == "sample":
        return render_legacy_sample(p)
    parts = []
    for s in p.get("sections", []):
        body = [f'<p>{_e(s["summary"])}</p>']
        if s.get("summary_ar"):
            body.append(f'<p class="ar" dir="rtl">{_e(s["summary_ar"])}</p>')
        if s["key"] == "initial_assessment" and s.get("label"):
            body.insert(0, f'<p class="verdict">{_e(s["label"]["en"])} · <span dir="rtl">{_e(s["label"]["ar"])}</span></p>')
        if s["key"] == "review_priority" and s.get("label"):
            body.insert(0, f'<span class="prio {_e(s.get("level", ""))}">{_e(s["label"]["en"])} · {_e(s["label"]["ar"])}</span>')
        for it in s.get("items", []):
            body.append(f"<li>{_e(it)}</li>")
        for it in s.get("items_ar", []):
            body.append(f'<li class="ar" dir="rtl">{_e(it)}</li>')
        for f in s.get("findings", []):
            label = f'<b>{_e(f["label"])}</b>: ' if f.get("label") else ""
            body.append(f'<p>{label}{_e(f["message"])}</p>')
            if f.get("excerpts"):
                body.append("<p>" + " ".join(f'<q dir="auto">{_e(x)}</q>' for x in f["excerpts"]) + "</p>")
            for fr in f.get("frames", []):
                ts = f' at {fr["timestamp"]}s' if "timestamp" in fr else ""
                sc = next((f" score {fr[k]}" for k in ("synthetic_score", "agreement_score") if k in fr), "")
                body.append(f'<span class="chip">{_e(fr["ref"])}{_e(ts)}{_e(sc)}</span>')
            for src in f.get("sources", []):
                meta = " · ".join(_e(x) for x in (src.get("source"), src.get("date") or "date not available",
                                                     src.get("match_type"), src.get("relation")) if x)
                body.append(f'<p class="src"><a href="{_e(src["url"])}" rel="noopener noreferrer">{_e(src.get("title") or src["url"])}'
                            f'</a><br><small>{meta}</small>'
                            + (f'<br><q dir="auto">{_e(src["excerpt"])}</q>' if src.get("excerpt") else "")
                            + ("<br><small>" + _e("; ".join(src["notes"])) + "</small>" if src.get("notes") else "")
                            + "</p>")
        if s.get("limitations"):
            body.append("<small>Limitations: " + _e(" ".join(s["limitations"])) + "</small>")
        cls = f'st-{s["status"]}' + (f' v-{s["verdict"]}' if s.get("verdict") else "")
        parts.append(f'<section class="{_e(cls)}"><span class="status {_e(s["status"])}">{_e(s["status_label"]["en"])} · '
                     f'{_e(s["status_label"]["ar"])}</span><h2>{_e(s["title"]["en"])} · '
                     f'<span dir="rtl">{_e(s["title"]["ar"])}</span></h2>{"".join(body)}</section>')
    media = p.get("media")
    media_line = "Not supplied"
    if media:
        media_line = f'{_e(media["kind"])}: {_e(media["original_name"])} ({media["width"]}×{media["height"]})'
        if media["kind"] == "video":
            ts = ", ".join(f'{v["timestamp"]}s' for v in media["visuals"])
            media_line += f' · {media["duration"]}s · findings apply to sampled frames at {ts}'
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SaqrSight assessment report</title><style>{CSS}</style>
{_header("INITIAL ASSESSMENT REPORT · تقرير تقييم أولي")}
<aside>{_e(p.get("notice", ""))}</aside>
<div class="meta"><b>Report ID</b> {_e(p["id"])}<br><b>Created</b> {_e(p["created_at"])}<br><b>Text language</b> {_e(p.get("language"))}
<br><b>Media</b> {media_line}<br><b>External searches</b> {"permitted by user" if p.get("consent_external") else "not permitted by user"}</div>
<p class="label">Submitted text · النص المرسل</p><pre dir="auto">{_e(p.get("caption") or "No text supplied.")}</pre>
<p class="label">Findings · النتائج</p>
{"".join(parts)}
<footer>Generated by SaqrSight {_e(p.get("version", ""))} · SGP2 analysis prototype. This is an initial
assessment to support human judgement, not a fact-check verdict.</footer></html>"""


def render_legacy_sample(p: dict) -> str:
    """SGP1 sample reports keep their original layout and SAMPLE labelling."""
    sections = "".join(f'<section><h2>{_e(s["title"])}</h2><p>{_e(s["finding"])}</p></section>' for s in p["sections"])
    image = _e(p["image"]["original_name"]) if p.get("image") else "Not supplied"
    return (f'<!doctype html><html lang="en"><meta charset="utf-8"><title>SaqrSight sample report</title>'
            f'<style>{CSS}</style>{_header("SGP1 SAMPLE REPORT · تقرير تجريبي")}<aside>{_e(p["notice"])}</aside>'
            f'<p>Report ID: {_e(p["id"])}<br>Created: {_e(p["created_at"])}<br>Language: {_e(p["language"])}</p>'
            f'<h2>Submitted text</h2><pre dir="auto">{_e(p["caption"] or "No text supplied.")}</pre>'
            f'<p>Image: {image}</p>{sections}<p>Milestone 1 · Local workflow prototype (SGP1)</p></html>')
