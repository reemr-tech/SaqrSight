"""Arabic versions of every message the checks produce.

Module messages are generated in English from structured data. This module gives each one an
Arabic counterpart, so reports (web and HTML export) are fully bilingual. Translation is applied
when a report is displayed, which also makes reports saved before this file existed bilingual.
Exact strings are looked up first; messages containing numbers, places or lists use patterns.
Unknown strings return None and the report then shows the English text only.
"""
from __future__ import annotations

import re

# Display names (proper Arabic spelling; claims.py uses normalised forms for matching).
PLACES = {
    "UAE": "الإمارات", "Dubai": "دبي", "Abu Dhabi": "أبوظبي", "Sharjah": "الشارقة", "Ajman": "عجمان",
    "Ras Al Khaimah": "رأس الخيمة", "Fujairah": "الفجيرة", "Umm Al Quwain": "أم القيوين", "Al Ain": "العين",
    "Dubai Marina": "دبي مارينا", "Burj Khalifa": "برج خليفة", "Jebel Ali": "جبل علي", "Deira": "ديرة",
    "Jumeirah": "جميرا", "Khor Fakkan": "خورفكان", "Hatta": "حتا", "Sheikh Zayed Road": "شارع الشيخ زايد",
    "Dubai International Airport": "مطار دبي الدولي", "Abu Dhabi Airport": "مطار أبوظبي",
}
EVENTS = {
    "fire": "حريق", "smoke": "دخان", "flood": "فيضان", "rain": "أمطار", "sandstorm": "عاصفة رملية", "fog": "ضباب",
    "explosion": "انفجار", "accident": "حادث", "collapse": "انهيار", "earthquake": "زلزال", "shortage": "نقص",
    "closure": "إغلاق", "outbreak": "تفشٍّ", "protest": "احتجاج", "attack": "هجوم",
}
TIMES = {"today": "اليوم", "now": "الآن", "yesterday": "أمس", "this week": "هذا الأسبوع"}
LEVELS = {"none": "لا يوجد", "low": "منخفض", "moderate": "متوسط", "high": "مرتفع"}
CATEGORIES = {"Urgency": "الاستعجال", "Fear or alarm": "التخويف أو الإثارة", "Manipulative framing": "صياغة تلاعبية",
              "Pressure to share": "الضغط للنشر"}
MATCH_TYPES = {"exact_or_near_exact": "تطابق تام أو شبه تام", "partial": "تطابق جزئي",
               "page_mentions_similar": "صورة مشابهة فقط"}
RELATIONS = {"previous_appearance": "ظهور سابق", "possible_context_discrepancy": "احتمال تعارض في السياق",
             "supporting": "داعم", "contradicting": "معارض", "insufficient": "غير كافٍ"}
REASONS = {"same event": "الحدث نفسه", "different or unclear event": "حدث مختلف أو غير واضح", "same place": "المكان نفسه",
           "different place": "مكان مختلف", "date not available": "التاريخ غير متاح", "same time": "الزمان نفسه",
           "different date": "تاريخ مختلف"}


def _list(items, table):
    return "، ".join(table.get(x.strip(), x.strip()) for x in items.split(",") if x.strip())


STATIC = {
    # shared statuses / pipeline
    "This check did not finish in time.": "لم يكتمل هذا الفحص في الوقت المحدد.",
    "This check could not be completed.": "تعذّر إكمال هذا الفحص.",
    "This check is still running.": "لا يزال هذا الفحص قيد التنفيذ.",
    "Waiting for all checks to finish.": "بانتظار انتهاء جميع الفحوص.",
    # text indicators
    "No text was supplied.": "لم يُقدَّم نص.",
    "No urgency, fear, manipulation or share-pressure wording from the indicator list was found.":
        "لم تُرصد أي صياغة استعجال أو تخويف أو تلاعب أو ضغط للنشر من قائمة المؤشرات.",
    "Negated – the wording discourages this behaviour (for example “do not share”).":
        "منفية – الصياغة تنهى عن هذا السلوك (مثل «لا تنشر»).",
    "Quoted or reported – the post appears to describe someone else's wording.":
        "مقتبسة أو منقولة – يبدو أن المنشور ينقل كلام شخص آخر.",
    "Used while calling something a rumour or false.": "وردت في سياق وصف أمر ما بأنه شائعة أو غير صحيح.",
    "Alarming wording attributed to an authority – may be a legitimate warning; confirm the authority actually issued it.":
        "صياغة مقلقة منسوبة إلى جهة رسمية – قد تكون تحذيراً مشروعاً؛ تأكد من أن الجهة أصدرته فعلاً.",
    "Wording that pushes the reader to react immediately.": "صياغة تدفع القارئ إلى التصرف فوراً.",
    "Alarming or catastrophic wording that can heighten anxiety.": "صياغة مثيرة للقلق أو توحي بكارثة.",
    "Claims of hidden truth, absolute certainty, or appeals to distrust official information.":
        "ادعاء وجود حقيقة مخفية أو يقين مطلق أو دعوة إلى عدم الثقة بالمعلومات الرسمية.",
    "Explicit requests to forward or spread the content.": "طلب صريح لإعادة إرسال المحتوى أو نشره.",
    "Rule-based wording indicators; they describe language, not whether the claim is true.":
        "مؤشرات صياغة قائمة على قواعد؛ تصف اللغة لا صحة الادعاء.",
    "Does not predict how readers will react.": "لا تتنبأ بردة فعل القراء.",
    "Dialect, sarcasm, misspellings and transliterated Arabic (Arabizi) may be missed.":
        "قد لا تُرصد اللهجات والسخرية والأخطاء الإملائية والعربية المكتوبة بحروف لاتينية (العربيزي).",
    # media analysis
    "No image or video was supplied.": "لم تُقدَّم صورة أو فيديو.",
    "Model-based media analysis is switched off on this server.": "تحليل الوسائط بالنماذج مُعطّل على هذا الخادم.",
    "Conventional editing or manipulation (splicing, retouching, cropping) was not assessed; no evaluated method is implemented for it.":
        "لم يُفحص التعديل التقليدي أو التلاعب (اللصق أو التنقيح أو القص)؛ لا توجد طريقة مُقيَّمة لذلك.",
    "Detects possible AI generation only; it does not detect conventional photo editing.":
        "يرصد احتمال التوليد بالذكاء الاصطناعي فقط؛ ولا يرصد التعديل التقليدي للصور.",
    "Performance drops on screenshots, heavy compression and generators absent from its training data.":
        "ينخفض الأداء مع لقطات الشاشة والضغط الشديد والمولّدات غير الموجودة في بيانات تدريبه.",
    "This model has not been validated for this application; its score is shown for information and is not used in the overall assessment.":
        "لم يُتحقق من هذا النموذج لهذا التطبيق؛ تُعرض درجته للعلم ولا تُستخدم في التقييم العام.",
    # consistency
    "Both a caption and an image or video are needed.": "يلزم وجود نص وصورة أو فيديو معاً.",
    "Model-based consistency checking is switched off on this server.": "فحص الاتساق بالنماذج مُعطّل على هذا الخادم.",
    "The consistency classifier has not been trained (run eval/train_consistency.py).":
        "لم يُدرَّب مصنّف الاتساق بعد (شغّل eval/train_consistency.py).",
    "The visible content appears consistent with what the caption describes.": "يبدو المحتوى المرئي متسقاً مع ما يصفه النص.",
    "The visible content does not appear to match what the caption describes. This may indicate miscaptioning; compare the media with the claim.":
        "لا يبدو أن المحتوى المرئي يطابق ما يصفه النص. قد يشير ذلك إلى وصف غير مطابق؛ قارن الوسائط بالادعاء.",
    "The model could not determine whether the caption and media agree.": "لم يتمكن النموذج من تحديد ما إذا كان النص والوسائط متفقين.",
    "These claim details cannot be assessed from the visible content.": "لا يمكن تقييم تفاصيل الادعاء هذه من المحتوى المرئي.",
    "Caption and visible content appear consistent in topic.": "النص والمحتوى المرئي متسقان في الموضوع.",
    "Caption and visible content appear not to match.": "يبدو أن النص والمحتوى المرئي غير متطابقين.",
    "Agreement between caption and visible content is inconclusive.": "الاتفاق بين النص والمحتوى المرئي غير حاسم.",
    "Trained on English news image–caption pairs (NewsCLIPpings); Arabic captions rely on a multilingual text encoder aligned to CLIP and were not part of training.":
        "دُرِّب على أزواج صور وتعليقات إخبارية باللغة الإنجليزية (NewsCLIPpings)؛ وتعتمد النصوص العربية على مُرمِّز نصوص متعدد اللغات متوافق مع CLIP ولم تكن ضمن التدريب.",
    "Estimates topic agreement only. It cannot confirm date, location, or that the image is from the described event, and does not detect out-of-context reuse on its own.":
        "يقدّر الاتفاق في الموضوع فقط. لا يمكنه تأكيد التاريخ أو المكان أو أن الصورة من الحدث الموصوف، ولا يرصد وحده إعادة الاستخدام خارج السياق.",
    "Long caption: only the first part was encoded by the text model.": "نص طويل: رمّز نموذج النصوص الجزء الأول منه فقط.",
    # reverse image search
    "Reverse image search is not configured on this server (no provider API key).":
        "البحث العكسي عن الصور غير مُفعّل على هذا الخادم (لا يوجد مفتاح خدمة).",
    "Skipped: you chose not to send media to an external search service.":
        "تم التخطي: اخترت عدم إرسال الوسائط إلى خدمة بحث خارجية.",
    "The search service did not respond in time.": "لم تستجب خدمة البحث في الوقت المحدد.",
    "The search service could not process the image.": "تعذّر على خدمة البحث معالجة الصورة.",
    "Reverse image search failed; no conclusion can be drawn from it.": "فشل البحث العكسي عن الصور؛ لا يمكن استخلاص نتيجة منه.",
    "The same or a near-identical image appears on pages that suggest a different time or place than the caption claims. Check those pages; this indicates possible out-of-context reuse, not proof. The earliest page found is not necessarily the original.":
        "تظهر الصورة نفسها أو صورة شبه مطابقة في صفحات تشير إلى زمان أو مكان مختلف عمّا يدّعيه النص. راجع تلك الصفحات؛ هذا يشير إلى احتمال إعادة الاستخدام خارج السياق وليس دليلاً قاطعاً. وأقدم صفحة لا تعني بالضرورة المصدر الأصلي.",
    "Only visually similar images were found; they are not evidence that this photo appeared elsewhere.":
        "عُثر على صور مشابهة بصرياً فقط؛ وهي ليست دليلاً على ظهور هذه الصورة في مكان آخر.",
    "No matching pages were found by the search provider. This does not show the image is new.":
        "لم تعثر خدمة البحث على صفحات مطابقة. هذا لا يعني أن الصورة جديدة.",
    "Coverage is limited to pages indexed by the provider.": "تقتصر التغطية على الصفحات التي فهرستها خدمة البحث.",
    "Publication dates come from page metadata and may be missing or wrong.": "تُؤخذ تواريخ النشر من بيانات الصفحات الوصفية وقد تكون مفقودة أو خاطئة.",
    "Matches show where an image appeared, not who created it first.": "تُظهر المطابقات أين ظهرت الصورة، لا من أنشأها أولاً.",
    "published before the time the caption claims": "نُشرت قبل الوقت الذي يدّعيه النص",
    # official sources
    "No caption was supplied, so there is no claim to search for.": "لم يُقدَّم نص، لذا لا يوجد ادعاء للبحث عنه.",
    "Official-source search is not configured on this server (no search provider API key).":
        "البحث في المصادر الرسمية غير مُفعّل على هذا الخادم (لا يوجد مفتاح خدمة بحث).",
    "Skipped: you chose not to use external search services.": "تم التخطي: اخترت عدم استخدام خدمات البحث الخارجية.",
    "The caption does not state an event with a place or time that can be searched for.":
        "لا يذكر النص حدثاً مع مكان أو زمان يمكن البحث عنه.",
    "Official-source search failed; no conclusion can be drawn from it.": "فشل البحث في المصادر الرسمية؛ لا يمكن استخلاص نتيجة منه.",
    "Official source(s) addressing the same event and place deny it or call it a rumour.":
        "مصدر رسمي يتناول الحدث والمكان نفسيهما ينفيه أو يصفه بالشائعة.",
    "Official source(s) report the same event, place and time.": "مصدر رسمي يذكر الحدث والمكان والزمان نفسها.",
    "Results that mention related terms but do not establish the same event, place and time. They are shown for context only.":
        "نتائج تذكر مصطلحات ذات صلة لكنها لا تثبت الحدث والمكان والزمان نفسها. تُعرض للسياق فقط.",
    "An official source appears to contradict the claim.": "يبدو أن مصدراً رسمياً يعارض الادعاء.",
    "An official source appears to report the same event.": "يبدو أن مصدراً رسمياً يذكر الحدث نفسه.",
    "Related official coverage was found but does not settle the claim.": "عُثر على تغطية رسمية ذات صلة لكنها لا تحسم الادعاء.",
    "No relevant result in the official sources searched.": "لا توجد نتيجة ذات صلة في المصادر الرسمية التي بُحث فيها.",
    "Searches only the configured official domains through a third-party search index.":
        "يبحث في النطاقات الرسمية المحددة فقط عبر فهرس بحث تابع لجهة خارجية.",
    "Relevance is judged by rule from titles and excerpts; read the source before relying on it.":
        "تُقدَّر الصلة بقواعد من العناوين والمقتطفات؛ اقرأ المصدر قبل الاعتماد عليه.",
}

_WHAT = {"image": "الصورة"}


def _what(en: str) -> str:
    m = re.fullmatch(r"(\d+) sampled frames", en)
    return f"{m[1]} لقطات مأخوذة" if m else _WHAT.get(en, en)


PATTERNS: list[tuple[re.Pattern, callable]] = [
    (re.compile(r"Language indicator level: (\w+)\. Categories detected: (.+)\."),
     lambda m: f"مستوى مؤشرات الصياغة: {LEVELS.get(m[1], m[1])}. الفئات المرصودة: {_list(m[2], CATEGORIES)}."),
    (re.compile(r"(\d+) of (\d+) checked visual\(s\) produced a possible AI-generation signal\."),
     lambda m: f"أظهرت {m[1]} من أصل {m[2]} من الوسائط المفحوصة إشارة محتملة إلى التوليد بالذكاء الاصطناعي."),
    (re.compile(r"No AI-generation signal on the (.+) checked\."),
     lambda m: f"لا توجد إشارة إلى التوليد بالذكاء الاصطناعي في {_what(m[1])}."),
    (re.compile(r"The detector produced a possible AI-generation signal for (this image\.|(\d+) of (\d+) sampled frames\.) .*"),
     lambda m: ("أظهر الكاشف إشارة محتملة إلى التوليد بالذكاء الاصطناعي "
                + ("لهذه الصورة." if m[2] is None else f"في {m[2]} من أصل {m[3]} لقطات مأخوذة.")
                + " هذه إشارة للمراجعة وليست دليلاً؛ إذ تخطئ الكواشف مع الصور المعدّلة أو المضغوطة أو غير المألوفة، "
                  "والصورة المولدة لا تجعل النص كاذباً بحد ذاتها.")),
    (re.compile(r"The detector did not flag the (.+) as AI-generated at the evaluated threshold\. .*"),
     lambda m: f"لم يصنّف الكاشف {_what(m[1])} على أنها مولدة بالذكاء الاصطناعي عند العتبة المُقيَّمة. "
               "هذا لا يثبت أن الوسائط أصلية أو غير معدّلة."),
    (re.compile(r"Evaluated on (\d+) held-out images: precision ([\d.]+), recall ([\d.]+), false-positive rate on authentic images ([\d.]+)\."),
     lambda m: f"قُيِّم على {m[1]} صورة اختبار: الدقة {m[2]}، والاستدعاء {m[3]}، ومعدل الإنذارات الخاطئة على الصور الأصلية {m[4]}."),
    (re.compile(r"The (AI-image detector|image/text encoders) could not be loaded \((.+)\)\."),
     lambda m: ("تعذّر تحميل كاشف الصور المولدة" if m[1] == "AI-image detector" else "تعذّر تحميل مُرمِّزات الصور والنصوص")
               + f" ({m[2]})."),
    (re.compile(r"Location \((.+)\): the image alone cannot confirm where it was taken\."),
     lambda m: f"المكان ({_list(m[1], PLACES)}): لا يمكن للصورة وحدها تأكيد مكان التقاطها."),
    (re.compile(r"Time \((.+)\): the image alone cannot confirm when it was taken\."),
     lambda m: f"الزمان ({_list(m[1], TIMES)}): لا يمكن للصورة وحدها تأكيد وقت التقاطها."),
    (re.compile(r"Event \((.+)\): visible content can look consistent with an event without showing that this specific event happened\."),
     lambda m: f"الحدث ({_list(m[1], EVENTS)}): قد يبدو المحتوى المرئي متسقاً مع حدث ما دون أن يثبت وقوع هذا الحدث بعينه."),
    (re.compile(r"NewsCLIPpings test accuracy ([\d.?]+); see README for independent VERITE results\."),
     lambda m: f"دقة اختبار NewsCLIPpings {m[1]}؛ راجع ملف README لنتائج VERITE المستقلة."),
    (re.compile(r"NewsCLIPpings test accuracy ([\d.?]+)\."), lambda m: f"دقة اختبار NewsCLIPpings {m[1]}."),
    (re.compile(r"Reverse image search: (.+)\."),
     lambda m: "البحث العكسي عن الصور: " + {"possible context discrepancy": "احتمال تعارض في السياق",
                                          "earlier appearances found": "عُثر على ظهور سابق",
                                          "only similar images": "صور مشابهة فقط",
                                          "no matches": "لا توجد مطابقات"}.get(m[1], m[1]) + "."),
    (re.compile(r"(\d+) page\(s\) contain the same or a near-identical image\."),
     lambda m: f"تحتوي {m[1]} صفحة على الصورة نفسها أو صورة شبه مطابقة."),
    (re.compile(r"page title refers to a different place \((.+)\)"),
     lambda m: f"عنوان الصفحة يشير إلى مكان مختلف ({_list(m[1], PLACES)})"),
    (re.compile(r"Could not reach the search service \((.+)\)\."), lambda m: f"تعذّر الوصول إلى خدمة البحث ({m[1]})."),
    (re.compile(r"The search service returned an error \(HTTP (\d+)\)\."), lambda m: f"أعادت خدمة البحث خطأً (HTTP {m[1]})."),
    (re.compile(r"No relevant result was found in the sources searched \((.+)\)\. This does not show the claim is false\."),
     lambda m: f"لم يُعثر على نتيجة ذات صلة في المصادر التي بُحث فيها ({m[1]}). هذا لا يعني أن الادعاء كاذب."),
    (re.compile(r"(\d+) of (\d+) searches failed; results may be incomplete\."),
     lambda m: f"فشلت {m[1]} من أصل {m[2]} عمليات بحث؛ قد تكون النتائج ناقصة."),
    (re.compile(r"All searches failed \((.+)\)\."), lambda m: f"فشلت جميع عمليات البحث ({m[1]})."),
    (re.compile(r"Timed out after (\d+)s\."), lambda m: f"انتهت المهلة بعد {m[1]} ثانية."),
    (re.compile(r"Unknown search provider '(.+)'\."), lambda m: f"خدمة بحث غير معروفة '{m[1]}'."),
]


def ar(text: str | None) -> str | None:
    """Arabic for a module-generated English message, or None if unknown."""
    if not text:
        return None
    t = " ".join(text.split())
    if t in STATIC:
        return STATIC[t]
    for pat, fn in PATTERNS:
        m = pat.fullmatch(t)
        if m:
            return fn(m)
    return None


def ar_all(texts) -> list[str]:
    return [x for x in (ar(t) for t in texts or []) if x]
