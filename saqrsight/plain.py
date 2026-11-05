"""Plain-language explanations for non-specialist readers (English and Arabic).

Everything here is assembled from the recorded findings by fixed rules: no language model is
used, so the summary can only restate what the checks actually found.

  plain_summary(p)  -> {"en": [...], "ar": [...]}   short, claim-specific "In plain words" text
  PLAIN             -> friendlier wording for technical module messages (display only)
  GUIDE             -> what the verdicts, review priority and issue type mean
"""
from __future__ import annotations

import re

from .i18n_ar import EVENTS as EVENTS_AR, PLACES as PLACES_AR

EVENT_EN = {"fire": "a fire", "smoke": "smoke", "flood": "flooding", "rain": "heavy rain", "sandstorm": "a sandstorm",
            "fog": "fog", "explosion": "an explosion", "accident": "an accident", "collapse": "a collapse",
            "earthquake": "an earthquake", "shortage": "a shortage", "closure": "a closure", "outbreak": "an outbreak",
            "protest": "a protest", "attack": "an attack"}
TIME_EN = {"now": ", said to be happening right now", "today": ", said to be today", "yesterday": ", said to be yesterday",
           "this week": ", said to be this week"}
TIME_AR = {"now": "، ويُقال إنه يحدث الآن", "today": "، ويُقال إنه اليوم", "yesterday": "، ويُقال إنه حدث أمس",
           "this week": "، ويُقال إنه هذا الأسبوع"}
CATEGORY_EN = {"urgency": "urgency", "fear": "alarming words", "manipulation": "claims of hidden truth",
               "share_pressure": "pressure to share"}
CATEGORY_AR = {"urgency": "الاستعجال", "fear": "كلمات مثيرة للقلق", "manipulation": "ادعاء وجود حقيقة مخفية",
               "share_pressure": "الضغط للنشر"}

# Status names shown to readers (the stored statuses stay completed / not_applicable / not_configured / failed).
STATUS_PLAIN = {
    "completed": {"en": "Done", "ar": "تم"},
    "not_applicable": {"en": "Not needed", "ar": "غير مطلوب"},
    "not_configured": {"en": "Not available", "ar": "غير متاح"},
    "failed": {"en": "Could not finish", "ar": "تعذّر الإكمال"},
    "pending": {"en": "Running…", "ar": "قيد التنفيذ…"},
}

# Technical module wording -> (plain English, plain Arabic). Applied when a report is displayed.
PLAIN = {
    "Reverse image search is not configured on this server (no provider API key).":
        ("Not done: searching the internet for this picture is not switched on in this version of SaqrSight.",
         "لم يُجرَ: البحث عن هذه الصورة على الإنترنت غير مُفعّل في هذه النسخة من صقر."),
    "Official-source search is not configured on this server (no search provider API key).":
        ("Not done: searching official UAE sources is not switched on in this version of SaqrSight.",
         "لم يُجرَ: البحث في المصادر الرسمية في الدولة غير مُفعّل في هذه النسخة من صقر."),
    "Model-based media analysis is switched off on this server.":
        ("Not done: the AI-image check is switched off in this version of SaqrSight.",
         "لم يُجرَ: فحص الصور المولدة مُعطّل في هذه النسخة من صقر."),
    "Model-based consistency checking is switched off on this server.":
        ("Not done: the picture–caption check is switched off in this version of SaqrSight.",
         "لم يُجرَ: فحص تطابق الصورة والنص مُعطّل في هذه النسخة من صقر."),
    "Agreement between caption and visible content is inconclusive.":
        ("Not sure: the check could not tell whether the picture matches what the caption describes.",
         "غير متأكد: لم يتمكن الفحص من تحديد ما إذا كانت الصورة تطابق ما يصفه النص."),
    "The model could not determine whether the caption and media agree.":
        ("The check only gives an answer when it is confident. Here it was not, so it gives no answer either way.",
         "لا يعطي الفحص إجابة إلا عندما يكون واثقاً. لم يكن واثقاً هنا، لذا لا يرجّح أي اتجاه."),
    "Caption and visible content appear consistent in topic.":
        ("The picture appears to show the kind of scene the caption describes.",
         "تبدو الصورة متوافقة مع نوع المشهد الذي يصفه النص."),
    "The visible content appears consistent with what the caption describes.":
        ("What is visible in the picture fits the caption's topic. This does not confirm where or when it was taken.",
         "ما يظهر في الصورة يتوافق مع موضوع النص. هذا لا يؤكد مكان التقاطها أو زمانه."),
    "Caption and visible content appear not to match.":
        ("The picture does not seem to show what the caption describes.",
         "لا يبدو أن الصورة تُظهر ما يصفه النص."),
    "The visible content does not appear to match what the caption describes. This may indicate miscaptioning; compare the media with the claim.":
        ("The picture may have been given a caption that does not belong to it. Look at the picture yourself and compare it with the claim.",
         "قد تكون الصورة نُشرت مع نص لا يخصها. انظر إلى الصورة بنفسك وقارنها بالادعاء."),
    "These claim details cannot be assessed from the visible content.":
        ("What the picture cannot prove on its own:", "ما لا تستطيع الصورة إثباته وحدها:"),
    "Conventional editing or manipulation (splicing, retouching, cropping) was not assessed; no evaluated method is implemented for it.":
        ("Normal photo editing (cutting and pasting, retouching, cropping) is not checked by SaqrSight.",
         "لا يفحص صقر التعديل العادي للصور (القص واللصق أو التنقيح أو الاقتصاص)."),
}
PATTERNS = [
    (re.compile(r"No AI-generation signal on the (image|(\d+) sampled frames) checked\."),
     lambda m: ("No signs of AI generation were found in the " + ("picture." if m[2] is None else f"{m[2]} video frames checked."),
                "لم تُرصد علامات توليد بالذكاء الاصطناعي في " + ("الصورة." if m[2] is None else f"{m[2]} لقطات من الفيديو."))),
    (re.compile(r"The detector did not flag the (.+) as AI-generated at the evaluated threshold\. .*"),
     lambda m: ("The AI-image detector found no signs that this was made by AI. That does not prove it is a real or unedited photo.",
                "لم يجد كاشف الصور المولدة علامات على أنها مصنوعة بالذكاء الاصطناعي. هذا لا يثبت أنها صورة حقيقية أو غير معدّلة.")),
    (re.compile(r"Language indicator level: (\w+)\. Categories detected: (.+)\."),
     lambda m: (f"Alarm level of the wording: {m[1]}. The exact words found are listed under “Panic-Related Language Indicators”.",
                "مستوى الإثارة في الصياغة: " + {"high": "مرتفع", "moderate": "متوسط", "low": "منخفض"}.get(m[1], m[1])
                + ". الكلمات المرصودة مذكورة في قسم «مؤشرات لغة الذعر».")),
]


def plain(text: str | None) -> tuple[str, str] | None:
    if not text:
        return None
    t = " ".join(text.split())
    if t in PLAIN:
        return PLAIN[t]
    for pat, fn in PATTERNS:
        m = pat.fullmatch(t)
        if m:
            return fn(m)
    return None


GUIDE = {
    "verdicts": [
        ("Potentially misleading", "قد يكون مضللاً",
         "Something concrete contradicts the post – for example the picture does not match it, the same picture was used "
         "before for something else, or an official source denies it.",
         "هناك ما يعارض المنشور بشكل واضح – مثل عدم تطابق الصورة معه، أو استخدام الصورة نفسها سابقاً لأمر آخر، أو نفي مصدر رسمي له."),
        ("Insufficient evidence", "أدلة غير كافية",
         "The checks could neither confirm nor rule out the claim. This is not a judgement that the post is false.",
         "لم تتمكن الفحوص من تأكيد الادعاء أو نفيه. هذا ليس حكماً بأن المنشور كاذب."),
        ("Apparently consistent", "يبدو متسقاً",
         "Nothing contradicted the post and at least one check supported it. Some details may still be unverified.",
         "لم يعارض المنشورَ شيء، ودعمه فحص واحد على الأقل. قد تبقى بعض التفاصيل غير مؤكدة."),
    ],
    "priority": ("Review priority tells fact-checkers which posts to look at first. It is high for posts about public safety "
                 "or posts that push people to share – even when the verdict is “insufficient evidence”.",
                 "تُرشد أولوية المراجعة مدققي الحقائق إلى المنشورات التي يجب فحصها أولاً. تكون مرتفعة للمنشورات المتعلقة بالسلامة "
                 "العامة أو التي تدفع الناس إلى النشر، حتى لو كان التقييم «أدلة غير كافية»."),
    "issue": ("Issue type names a specific problem that was found (such as a mismatched or reused picture). "
              "“None identified” means no specific problem was proven – not that the post is true.",
              "يحدد نوع المشكلة مشكلة بعينها رُصدت (مثل صورة غير مطابقة أو مُعاد استخدامها). "
              "«لم يُحدَّد» تعني أنه لم تثبت مشكلة محددة، لا أن المنشور صحيح."),
}


def _places(details: dict) -> list[str]:
    places = [p for p in details.get("locations", []) if p != "UAE"] or details.get("locations", [])
    return [p for p in places if not any(p != q and p in q for q in places)]   # "Dubai" inside "Dubai Marina"


def _claim(details: dict, has_caption: bool) -> tuple[str, str]:
    if not has_caption:
        return ("You sent a picture without a caption, so there was no claim to check it against.",
                "أرسلت صورة دون نص، لذلك لا يوجد ادعاء لمقارنتها به.")
    events, places = details.get("events", []), _places(details)
    rel = details.get("relative_dates", [])
    t_en = TIME_EN.get(rel[0], "") if rel else (f", dated {details['dates'][0]}" if details.get("dates") else "")
    t_ar = TIME_AR.get(rel[0], "") if rel else (f"، بتاريخ {details['dates'][0]}" if details.get("dates") else "")
    pl_en = " and ".join(places)
    pl_ar = " و".join(PLACES_AR.get(p, p) for p in places)
    if events:
        ev_en = EVENT_EN.get(events[0], events[0])
        ev_ar = EVENTS_AR.get(events[0], events[0])
        return ((f"The post is about {ev_en}" + (f" in {pl_en}" if places else "") + f"{t_en}."),
                (f"يتحدث المنشور عن {ev_ar}" + (f" في {pl_ar}" if places else "") + f"{t_ar}."))
    if places or t_en:
        return (f"The post makes a claim about {pl_en or 'the UAE'}{t_en}.",
                f"يقدّم المنشور ادعاءً عن {pl_ar or 'الإمارات'}{t_ar}.")
    return ("The post does not name a specific event, place or time that could be checked.",
            "لا يذكر المنشور حدثاً أو مكاناً أو زماناً محدداً يمكن التحقق منه.")


def _codes(m: dict | None) -> set:
    return {f["code"] for f in (m or {}).get("findings", [])} if m and m.get("status") == "completed" else set()


def plain_summary(p: dict) -> dict:
    a = p.get("assessment")
    if not a:
        return {"en": ["The checks are still running."], "ar": ["لا تزال الفحوص قيد التنفيذ."]}
    mods = p.get("modules", {})
    d = p.get("claim_details") or {}
    en, ar = [], []
    c_en, c_ar = _claim(d, bool(p.get("caption")))
    en.append(c_en); ar.append(c_ar)
    matches = ((mods.get("text_analysis") or {}).get("data") or {}).get("matches", [])
    if any(m["context"] in ("debunk", "negated") for m in matches) and not any(m["context"] == "active" for m in matches):
        en.append("The post itself seems to warn against a rumour or discourage sharing, rather than spread the claim.")
        ar.append("يبدو أن المنشور نفسه يحذّر من شائعة أو ينهى عن النشر، لا أنه ينشر الادعاء.")

    cons = mods.get("consistency_check") or {}
    decision = (cons.get("data") or {}).get("decision") if cons.get("status") == "completed" else None
    places = _places(d)
    when = bool(d.get("relative_dates") or d.get("dates"))
    verdict = a["verdict"]
    if verdict == "potentially_misleading":
        mods_hit = {c["module"] for c in a.get("contradictions", [])}
        if "consistency_check" in mods_hit:
            en.append("The picture does not seem to show what the caption describes, so the caption may not belong to it.")
            ar.append("لا يبدو أن الصورة تُظهر ما يصفه النص، لذا قد لا يكون النص خاصاً بها.")
        if "reverse_image_search" in mods_hit:
            en.append("The same picture appeared earlier on other pages, in a different time or place.")
            ar.append("ظهرت الصورة نفسها سابقاً في صفحات أخرى، في زمان أو مكان مختلف.")
        if "official_sources" in mods_hit:
            en.append("An official source covering the same event denies it or calls it a rumour.")
            ar.append("مصدر رسمي يتناول الحدث نفسه ينفيه أو يصفه بالشائعة.")
    elif a.get("rule") == "A2":
        en.append("The picture may have been made with AI, so it cannot count as evidence until its origin is known.")
        ar.append("قد تكون الصورة مصنوعة بالذكاء الاصطناعي، لذا لا يمكن اعتبارها دليلاً حتى يُعرف مصدرها.")
    elif verdict == "apparently_consistent":
        if decision == "agree":
            en.append("The picture appears to fit the caption, and none of the checks found anything that contradicts it.")
            ar.append("تبدو الصورة متوافقة مع النص، ولم يجد أي فحص ما يعارضه.")
        if "supporting" in _codes(mods.get("official_sources")):
            en.append("An official source reports the same event, place and time.")
            ar.append("مصدر رسمي يذكر الحدث والمكان والزمان نفسها.")
    else:
        if decision == "agree" and (places or when):
            what_en = " or ".join(x for x in ([f"that it is {' and '.join(places)}"] if places else []) +
                                  (["when it was taken"] if when else []))
            en.append(f"The picture fits the topic, but it cannot show {what_en}.")
            ar.append("الصورة تتوافق مع الموضوع، لكنها لا تستطيع إثبات المكان أو الزمان.")
        elif p.get("caption"):
            en.append("With the checks available, we could not confirm it or rule it out.")
            ar.append("بالفحوص المتاحة، لم نتمكن من تأكيده أو نفيه.")

    vis = mods.get("media_analysis") or {}
    if vis.get("status") == "completed":
        if "possible_synthetic" in _codes(vis):
            if a.get("rule") != "A2":
                en.append("The AI-image detector gave a possible sign that the picture was made by AI (it is not always right).")
                ar.append("أعطى كاشف الصور المولدة إشارة محتملة إلى أن الصورة مصنوعة بالذكاء الاصطناعي (وهو لا يصيب دائماً).")
        else:
            if (p.get("media") or {}).get("kind") == "video":
                en.append("We found no signs that the video frames we checked were made by AI, although that does not prove the video is real or unedited.")
                ar.append("لم نجد علامات على أن لقطات الفيديو التي فحصناها مصنوعة بالذكاء الاصطناعي، وإن كان ذلك لا يثبت أن الفيديو حقيقي أو غير معدّل.")
            else:
                en.append("We found no signs that the picture was made by AI, although that does not prove it is real or unedited.")
                ar.append("لم نجد علامات على أن الصورة مصنوعة بالذكاء الاصطناعي، وإن كان ذلك لا يثبت أنها حقيقية أو غير معدّلة.")

    txt = mods.get("text_analysis") or {}
    if txt.get("status") == "completed":
        data = txt.get("data") or {}
        if data.get("indicator_level") in ("moderate", "high"):
            words = []
            for f in txt.get("findings", []):
                if f["code"] in CATEGORY_EN:
                    words += [w for w in f.get("excerpts", []) if len(w) > 2]
            quoted = "، ".join(f"«\u2068{w}\u2069»" for w in words[:3])   # isolate quotes so English words keep their order
            cats = [c for c in ("urgency", "fear", "manipulation", "share_pressure") if c in data.get("categories", [])]
            examples = ", ".join(f"“{w}”" for w in words[:3])
            en.append("The wording uses pressure tactics that are common in rumours ("
                      + ", ".join(CATEGORY_EN[c] for c in cats) + ")" + (f", such as {examples}." if examples else "."))
            ar.append("تستخدم الصياغة أساليب ضغط شائعة في الشائعات (" + "، ".join(CATEGORY_AR[c] for c in cats) + ")"
                      + (f"، مثل {quoted}." if quoted else "."))
        elif data.get("indicator_level") == "none":
            en.append("The wording itself does not use alarm or pressure tactics.")
            ar.append("لا تستخدم الصياغة نفسها أساليب إثارة أو ضغط.")

    not_searched = [k for k in ("reverse_image_search", "official_sources")
                    if (mods.get(k) or {}).get("status") in ("not_configured", "failed")
                    or "Skipped" in ((mods.get(k) or {}).get("summary") or "")]
    if not_searched:
        en.append("We did not search the internet or official sources for this report.")
        ar.append("لم نبحث في الإنترنت أو المصادر الرسمية لهذا التقرير.")

    if verdict == "potentially_misleading":
        en.append("Our advice: do not share it until you have checked the points above.")
        ar.append("نصيحتنا: لا تنشره قبل أن تتحقق من النقاط أعلاه.")
    elif (a.get("priority") or {}).get("level") == "high":
        en.append("Our advice: check official channels such as WAM, the police or NCEMA before you share it.")
        ar.append("نصيحتنا: راجع القنوات الرسمية مثل وام أو الشرطة أو الهيئة الوطنية لإدارة الطوارئ قبل أن تنشره.")
    else:
        en.append("Our advice: look for reliable, independent reports of the same thing before relying on it.")
        ar.append("نصيحتنا: ابحث عن تغطية موثوقة ومستقلة للأمر نفسه قبل الاعتماد عليه.")
    return {"en": en, "ar": ar}
