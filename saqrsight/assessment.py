"""Documented assessment rules. No model scores are averaged or combined into a truth probability.

OVERALL ASSESSMENT (first matching rule wins)
  A1 Potentially misleading – at least one meaningful contradiction or context discrepancy:
       * an official source addressing the same event and place denies it / calls it a rumour;
       * reverse image search finds the same image on pages indicating a different time or place;
       * the validated consistency classifier finds the caption does not match the visible content
         (decisive "disagree" threshold only).
  A2 Insufficient evidence – no contradiction, but the media may be AI-generated (validated signal):
       origin of the media must be established before agreement means anything.
  A3 Apparently consistent – no contradiction, and at least one applicable content check supports
       agreement (consistency "agree", or an official source reporting the same event/place/time).
       The explanation lists which real-world details remain unverified.
  A4 Insufficient evidence – everything else (key claim not assessable from inputs/findings/sources).
  Never sufficient on their own for A1: urgent or alarming wording, a synthetic-media signal,
  a failed or unconfigured search, "no results".

REVIEW PRIORITY (independent of the assessment; points with reasons, not a score average)
  +2 the caption describes a public-safety event (fire, explosion, attack, flood, outbreak, collapse,
     earthquake, shortage, closure) that has not been confirmed by an official source
  +2 language indicator level "high";  +1 if "moderate"
  +1 explicit pressure to share
  +2 assessment is potentially misleading
  +1 validated possible-synthetic-media signal
  +1 claims a specific UAE place together with "now / today / yesterday"
  high >= 4, medium 2–3, low 0–1
"""
from __future__ import annotations

from .analysis.claims import ClaimDetails
from .schema import COMPLETED

RULES_VERSION = "rules-1.0"
SAFETY_EVENTS = {"fire", "explosion", "attack", "flood", "outbreak", "collapse", "earthquake", "shortage", "closure"}

VERDICTS = {
    "potentially_misleading": {"en": "Potentially misleading", "ar": "قد يكون مضللاً"},
    "apparently_consistent": {"en": "Apparently consistent", "ar": "يبدو متسقاً"},
    "insufficient_evidence": {"en": "Insufficient evidence", "ar": "أدلة غير كافية"},
}
PRIORITY = {"low": {"en": "Low", "ar": "منخفضة"}, "medium": {"en": "Medium", "ar": "متوسطة"},
            "high": {"en": "High", "ar": "مرتفعة"}}
ISSUES = {
    "possible_miscaptioning": {"en": "Possible miscaptioning", "ar": "احتمال وصف غير مطابق للصورة"},
    "possible_out_of_context": {"en": "Possible out-of-context reuse", "ar": "احتمال إعادة استخدام خارج السياق"},
    "possible_synthetic_media": {"en": "Possible synthetic media", "ar": "احتمال وسائط مولدة بالذكاء الاصطناعي"},
    "contradicted_by_official_source": {"en": "Contradicted by an official source", "ar": "يتعارض مع مصدر رسمي"},
}


def _done(modules: dict, name: str) -> dict | None:
    m = modules.get(name)
    return m if m and m["status"] == COMPLETED else None


def _codes(m: dict | None) -> set[str]:
    return {f["code"] for f in m["findings"]} if m else set()


def assess(modules: dict, details: ClaimDetails, has_caption: bool, has_media: bool) -> dict:
    text = _done(modules, "text_analysis")
    visual = _done(modules, "media_analysis")
    cons = _done(modules, "consistency_check")
    rev = _done(modules, "reverse_image_search")
    off = _done(modules, "official_sources")

    contradictions, support, issues = [], [], []
    if off and "contradicting" in _codes(off):
        contradictions.append({"en": "An official source addressing the same event and place denies it or calls it a rumour.",
                               "ar": "مصدر رسمي يتناول الحدث والمكان نفسيهما ينفيه أو يصفه بالشائعة.",
                               "module": "official_sources"})
        issues.append("contradicted_by_official_source")
    if rev and "possible_context_discrepancy" in _codes(rev):
        contradictions.append({"en": "The same image appears on pages that indicate a different time or place.",
                               "ar": "الصورة نفسها ظهرت في صفحات تشير إلى زمان أو مكان مختلف.",
                               "module": "reverse_image_search"})
        issues.append("possible_out_of_context")
    if cons and cons["data"].get("decision") == "disagree" and cons.get("confidence") == "validated":
        contradictions.append({"en": "The caption does not appear to match the visible content of the media.",
                               "ar": "لا يبدو أن النص يطابق المحتوى المرئي.", "module": "consistency_check"})
        issues.append("possible_miscaptioning")
    synthetic = bool(visual and visual.get("confidence") == "validated" and "possible_synthetic" in _codes(visual))
    if synthetic:
        issues.append("possible_synthetic_media")
    if cons and cons["data"].get("decision") == "agree":
        support.append({"en": "Caption and visible content appear consistent in topic.",
                        "ar": "النص والمحتوى المرئي متسقان في الموضوع.", "module": "consistency_check"})
    if off and "supporting" in _codes(off):
        support.append({"en": "An official source reports the same event, place and time.",
                        "ar": "مصدر رسمي يذكر الحدث والمكان والزمان نفسها.", "module": "official_sources"})

    unverified = []
    if details.locations:
        unverified.append({"en": "where it happened (" + ", ".join(details.locations) + ")", "ar": "مكان الحدث"})
    if details.has_time:
        unverified.append({"en": "when it happened (" + ", ".join(details.relative_dates + details.dates) + ")",
                           "ar": "زمان الحدث"})
    if details.events and not (off and "supporting" in _codes(off)):
        unverified.append({"en": "that this specific event took place", "ar": "وقوع هذا الحدث بعينه"})

    checked = [m for m in ("text_analysis", "media_analysis", "consistency_check", "reverse_image_search",
                           "official_sources") if _done(modules, m)]
    if contradictions:
        verdict, rule = "potentially_misleading", "A1"
        exp_en = "A discrepancy was identified: " + " ".join(c["en"] for c in contradictions)
        exp_ar = "تم رصد تعارض: " + " ".join(c["ar"] for c in contradictions)
    elif synthetic:
        verdict, rule = "insufficient_evidence", "A2"
        exp_en = ("The media produced a possible AI-generation signal. This does not make the claim false, but the "
                  "origin of the media must be established before its agreement with the caption means anything.")
        exp_ar = "ظهرت إشارة محتملة إلى أن الوسائط مولدة بالذكاء الاصطناعي. هذا لا يجعل الادعاء كاذباً، لكن يجب التحقق من مصدر الوسائط أولاً."
    elif support:
        verdict, rule = "apparently_consistent", "A3"
        exp_en = "No material contradiction was found. " + " ".join(s["en"] for s in support)
        exp_ar = "لم يُرصد تعارض جوهري. " + " ".join(s["ar"] for s in support)
        if unverified:
            exp_en += " Still unverified: " + "; ".join(u["en"] for u in unverified) + "."
            exp_ar += " لم يتم التحقق بعد من: " + "، ".join(u["ar"] for u in unverified) + "."
    else:
        verdict, rule = "insufficient_evidence", "A4"
        if not has_caption:
            exp_en = "No claim text was supplied, so there is no claim to assess against the media."
            exp_ar = "لم يُقدَّم نص ادعاء، لذلك لا يوجد ادعاء لتقييمه."
        else:
            exp_en = ("The key claim cannot be assessed from the available inputs, model findings or retrieved sources. "
                      "Wording indicators describe how the post is written, not whether it is true.")
            exp_ar = "لا يمكن تقييم الادعاء الأساسي من المدخلات أو النتائج أو المصادر المتاحة. مؤشرات الصياغة تصف أسلوب المنشور لا صحته."

    # --- review priority -----------------------------------------------------------------
    points, reasons = 0, []
    safety = set(details.events) & SAFETY_EVENTS
    if safety and not (off and "supporting" in _codes(off)):
        points += 2
        reasons.append({"en": "Describes a public-safety event (" + ", ".join(sorted(safety)) + ") not confirmed by an official source.",
                        "ar": "يصف حدثاً يتعلق بالسلامة العامة لم يؤكده مصدر رسمي."})
    level = text["data"]["indicator_level"] if text else "none"
    if level in ("high", "moderate"):
        points += 2 if level == "high" else 1
        reasons.append({"en": f"Language indicator level is {level}.", "ar": "مستوى مؤشرات الصياغة " + ("مرتفع." if level == "high" else "متوسط.")})
    if text and "share_pressure" in text["data"]["categories"]:
        points += 1
        reasons.append({"en": "Explicitly asks readers to share.", "ar": "يطلب صراحة من القراء النشر."})
    if verdict == "potentially_misleading":
        points += 2
        reasons.append({"en": "A discrepancy was identified.", "ar": "تم رصد تعارض."})
    if synthetic:
        points += 1
        reasons.append({"en": "Possible AI-generated media signal.", "ar": "إشارة محتملة إلى وسائط مولدة."})
    specific_place = [p for p in details.locations if p != "UAE"]
    if specific_place and set(details.relative_dates) & {"now", "today", "yesterday"}:
        points += 1
        reasons.append({"en": "Claims a specific UAE place and a very recent time.", "ar": "يذكر مكاناً محدداً في الدولة ووقتاً قريباً جداً."})
    prio = "high" if points >= 4 else "medium" if points >= 2 else "low"
    if not reasons:
        reasons.append({"en": "No priority factors were identified.", "ar": "لم تُرصد عوامل أولوية."})

    return {
        "verdict": verdict, "label": VERDICTS[verdict], "rule": rule, "rules_version": RULES_VERSION,
        "explanation": {"en": exp_en, "ar": exp_ar}, "contradictions": contradictions, "support": support,
        "unverified": unverified, "checked": checked,
        "issue_types": [{"code": i, **ISSUES[i]} for i in issues],
        "priority": {"level": prio, "label": PRIORITY[prio], "points": points, "reasons": reasons},
    }


def recommended_actions(modules: dict, details: ClaimDetails, a: dict) -> list[dict]:
    acts = []
    rev, off, vis = modules.get("reverse_image_search"), modules.get("official_sources"), modules.get("media_analysis")
    if a["verdict"] == "potentially_misleading":
        acts.append({"en": "Avoid sharing this post until the discrepancy is resolved; open the cited sources and compare them with the claim.",
                     "ar": "تجنّب نشر هذا المنشور حتى يُحل التعارض، وافتح المصادر المذكورة وقارنها بالادعاء."})
    if details.has_time:
        acts.append({"en": "Check when the photo or video was first published; compare that date with the time the post claims.",
                     "ar": "تحقق من تاريخ أول نشر للصورة أو الفيديو وقارنه بالوقت الذي يدّعيه المنشور."})
    if details.locations:
        acts.append({"en": "Compare landmarks, signs and buildings in the media with earlier coverage of the stated location.",
                     "ar": "قارن المعالم واللافتات والمباني في الوسائط بتغطيات سابقة للمكان المذكور."})
    if set(details.events) & SAFETY_EVENTS:
        acts.append({"en": "Consult official channels such as WAM, NCEMA, the relevant police force or emirate media office before acting on or sharing the claim.",
                     "ar": "راجع القنوات الرسمية مثل وام أو الهيئة الوطنية لإدارة الطوارئ والأزمات أو الشرطة أو المكتب الإعلامي للإمارة قبل التصرف أو النشر."})
    if rev and rev["status"] != COMPLETED and vis and vis["status"] != "not_applicable":
        acts.append({"en": "Run a reverse image search yourself (for example Google Lens or TinEye) to look for earlier appearances.",
                     "ar": "أجرِ بحثاً عكسياً عن الصورة بنفسك (مثل Google Lens أو TinEye) للبحث عن ظهور سابق لها."})
    if off and off["status"] != COMPLETED and details.events:
        acts.append({"en": "Search the official sources listed in this report directly for the event, place and date.",
                     "ar": "ابحث مباشرة في المصادر الرسمية المذكورة عن الحدث والمكان والتاريخ."})
    if any(i["code"] == "possible_synthetic_media" for i in a["issue_types"]):
        acts.append({"en": "Look for the original uploader and other angles of the same scene; AI-generated images rarely have independent corroborating footage.",
                     "ar": "ابحث عن الناشر الأصلي وزوايا أخرى للمشهد نفسه؛ نادراً ما تتوفر لقطات مستقلة تؤكد الصور المولدة."})
    if not acts:
        acts.append({"en": "Look for independent, reputable reporting of the same claim before relying on it.",
                     "ar": "ابحث عن تغطية مستقلة وموثوقة للادعاء نفسه قبل الاعتماد عليه."})
    return acts
