"""Build the report sections from recorded module results, and render the standalone HTML export."""
from __future__ import annotations

import html

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
                             acts[0]["en"] if acts else "Waiting for all checks to finish.",
                             items=[x["en"] for x in acts], items_ar=[x["ar"] for x in acts]))
    return sections


# ------------------------------------------------------------------------------------------
CSS = """body{font:15px/1.55 system-ui,-apple-system,'Segoe UI',Tahoma,sans-serif;max-width:860px;margin:32px auto;
padding:0 20px;color:#173c37;background:#fff}h1{font-size:26px;margin:0}h2{font-size:17px;margin:0 0 6px}
header{display:flex;gap:14px;align-items:center;border-bottom:2px solid #174d42;padding-bottom:12px}
aside{padding:12px 16px;background:#fff1d8;border:1px solid #b18432;border-radius:8px;margin:16px 0}
section{break-inside:avoid;border:1px solid #dfe6e1;border-radius:8px;padding:12px 16px;margin:12px 0}
.status{float:inline-end;font-size:12px;padding:2px 8px;border-radius:99px;background:#eef2ee}
.status.failed{background:#fde4e0}.status.not_configured{background:#f2efe6}
.verdict{font-size:20px;font-weight:700}.ar{direction:rtl;text-align:right;color:#445}
q{background:#fff6d6;padding:0 3px;quotes:none}small{color:#667}pre{white-space:pre-wrap;font:inherit}
@media print{body{margin:0}}"""


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
                body.append(f"<small>{_e(fr['ref'])}{_e(ts)}{_e(sc)}</small><br>")
            for src in f.get("sources", []):
                meta = " · ".join(_e(x) for x in (src.get("source"), src.get("date") or "date not available",
                                                     src.get("match_type"), src.get("relation")) if x)
                body.append(f'<p><a href="{_e(src["url"])}" rel="noopener noreferrer">{_e(src.get("title") or src["url"])}'
                            f'</a><br><small>{meta}</small>'
                            + (f'<br><q dir="auto">{_e(src["excerpt"])}</q>' if src.get("excerpt") else "")
                            + ("<br><small>" + _e("; ".join(src["notes"])) + "</small>" if src.get("notes") else "")
                            + "</p>")
        if s.get("limitations"):
            body.append("<small>Limitations: " + _e(" ".join(s["limitations"])) + "</small>")
        parts.append(f'<section><span class="status {_e(s["status"])}">{_e(s["status_label"]["en"])} · '
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
<header><svg width="40" height="40" viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="30" fill="#174d42"/><path d="M14 38c10-2 18-10 22-20 2 8 8 12 14 12-6 4-10 4-14 2-4 6-12 8-22 6z" fill="#e7c27a"/></svg>
<div><h1>SaqrSight · صقر</h1><small>Initial assessment report · تقرير تقييم أولي</small></div></header>
<aside>{_e(p.get("notice", ""))}</aside>
<p>Report ID: {_e(p["id"])}<br>Created: {_e(p["created_at"])}<br>Text language: {_e(p.get("language"))}
<br>Media: {media_line}<br>External searches: {"permitted by user" if p.get("consent_external") else "not permitted by user"}</p>
<h2>Submitted text</h2><pre dir="auto">{_e(p.get("caption") or "No text supplied.")}</pre>
{"".join(parts)}
<p><small>Generated by SaqrSight {_e(p.get("version", ""))} · SGP2 analysis prototype. This is an initial
assessment to support human judgement, not a fact-check verdict.</small></p></html>"""


def render_legacy_sample(p: dict) -> str:
    """SGP1 sample reports keep their original layout and SAMPLE labelling."""
    sections = "".join(f'<section><h2>{_e(s["title"])}</h2><p>{_e(s["finding"])}</p></section>' for s in p["sections"])
    image = _e(p["image"]["original_name"]) if p.get("image") else "Not supplied"
    return (f'<!doctype html><html lang="en"><meta charset="utf-8"><title>SaqrSight sample report</title>'
            f'<style>{CSS}</style><h1>SaqrSight · Sample report</h1><aside>{_e(p["notice"])}</aside>'
            f'<p>Report ID: {_e(p["id"])}<br>Created: {_e(p["created_at"])}<br>Language: {_e(p["language"])}</p>'
            f'<h2>Submitted text</h2><pre dir="auto">{_e(p["caption"] or "No text supplied.")}</pre>'
            f'<p>Image: {image}</p>{sections}<p>Milestone 1 · Local workflow prototype (SGP1)</p></html>')
