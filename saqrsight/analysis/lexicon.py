"""Transparent bilingual lexicon for language indicators (version text-lexicon-1.1).

1.1 adds Gulf-dialect and everyday-English forms found in eval/data/text_indicators_dev_dialect.jsonl
(development data only; the v2 test set was written and frozen before these changes).

All Arabic patterns are written in the *normalized* form produced by textutil.normalize:
no diacritics, ا for أ/إ/آ, ه for ة, ي for ى/ئ, و for ؤ. Optional Arabic proclitics (و/ف/ب/ل/ال)
are allowed by the matcher, so patterns list stems only.

Categories
  urgency         wording that demands immediate attention or action
  fear            alarming or catastrophic wording
  manipulation    claims of hidden truth, certainty pressure, or appeals to distrust
  share_pressure  explicit requests to spread the content
"""

CATEGORIES = {
    "urgency": {
        "label_en": "Urgency", "label_ar": "الاستعجال",
        "explain_en": "Wording that pushes the reader to react immediately.",
        "explain_ar": "صياغة تدفع القارئ إلى التصرف فوراً.",
        "en": [r"urgent(?:ly)?", r"breaking(?: news)?", r"right now", r"immediately", r"asap",
               r"act now", r"before it'?s too late", r"within (?:the next )?\d+ (?:hours?|minutes?)",
               r"last chance", r"happening now", r"just in", r"emergency alert", r"time is running out",
               r"hurry", r"emergency", r"get out", r"leave (?:the area|now|immediately)", r"right away"],
        "ar": [r"عاجل", r"عاجله", r"فورا", r"حالا", r"قبل فوات الاوان", r"في اسرع وقت",
               r"خلال (?:\d+ )?ساعات", r"تنبيه عاجل", r"انتبهوا", r"ضروري جدا", r"هام جدا", r"مهم جدا",
               r"الحقوا", r"بسرعه", r"طوارئ", r"اطلعوا"],
    },
    "fear": {
        "label_en": "Fear or alarm", "label_ar": "التخويف أو الإثارة",
        "explain_en": "Alarming or catastrophic wording that can heighten anxiety.",
        "explain_ar": "صياغة مثيرة للقلق أو توحي بكارثة.",
        "en": [r"panic", r"catastroph\w*", r"disaster", r"deadly", r"terrifying", r"horrific", r"chaos",
               r"collaps\w*", r"explosions?", r"people are dying", r"outbreak", r"epidemic", r"lockdown",
               r"stock up", r"shortages?", r"run(?:ning)? out", r"dangerous", r"worst ever",
               r"end of the world", r"evacuat\w+", r"mass casualt\w+", r"no one is safe", r"apocalyp\w*", r"massacre",
               r"bodies everywhere", r"trapped", r"scary", r"overwhelmed", r"nightmare", r"meltdown", r"not safe"],
        "ar": [r"كارثه", r"كارثي", r"كارثيه", r"مرعب", r"مرعبه", r"رعب", r"هلع", r"ذعر", r"فوضي", r"انهيار",
               r"انفجار", r"انفجارات", r"وباء", r"تفشي", r"حظر تجول", r"اغلاق تام", r"نقص حاد", r"نفاد",
               r"خطير", r"خطيره", r"مميت", r"مميته", r"ضحايا", r"اخلاء", r"خزنوا", r"لا احد في امان",
               r"نهايه العالم", r"مصيبه", r"الله يستر", r"وفيات", r"يخوف", r"مخيف", r"مخيفه", r"مرعوب", r"مرعوبه",
               r"مرعوبين", r"ما يطمن", r"الرفوف فاضيه", r"محاصرين"],
    },
    "manipulation": {
        "label_en": "Manipulative framing", "label_ar": "صياغة تلاعبية",
        "explain_en": "Claims of hidden truth, absolute certainty, or appeals to distrust official information.",
        "explain_ar": "ادعاء وجود حقيقة مخفية أو يقين مطلق أو دعوة إلى عدم الثقة بالمعلومات الرسمية.",
        "en": [r"they don'?t want you to know", r"(?:the )?media (?:is|are) hiding", r"what they'?re not telling you",
               r"100 ?% (?:true|confirmed|real)", r"trust me", r"wake up", r"the truth (?:they|about)",
               r"leaked", r"cover[- ]?up", r"nobody is talking about", r"banned video", r"before they delete",
               r"you won'?t believe", r"hidden truth", r"they are lying", r"(?:is|are) hiding",
               r"covering (?:it )?up", r"mainstream media", r"won'?t report", r"nobody is reporting", r"absolutely confirmed",
               r"from an insider"],
        "ar": [r"لن يخبرك", r"يخفون", r"يخفونه", r"تعتيم", r"تعتيم اعلامي", r"مسرب", r"مسربه", r"تسريب",
               r"حقيقه صادمه", r"مؤكد 100", r"100 ?% مؤكد", r"صدقوني", r"الحقيقه التي", r"قبل الحذف",
               r"قبل ما ينحذف", r"لن تصدق", r"يكذبون", r"الحقيقه المخفيه", r"الاعلام ساكت", r"ما يبونكم تعرفون",
               r"مخبيه", r"مخبين", r"يخبون", r"مصدر خاص", r"ميه بالميه", r"محد بيقولكم", r"يغطون علي",
               r"كل شي مخطط له", r"اصحوا", r"قبل لا يمسحون\w*"],
    },
    "share_pressure": {
        "label_en": "Pressure to share", "label_ar": "الضغط للنشر",
        "explain_en": "Explicit requests to forward or spread the content.",
        "explain_ar": "طلب صريح لإعادة إرسال المحتوى أو نشره.",
        "en": [r"share (?:this|it|now|immediately|widely|with everyone|before|to)", r"forward (?:this|it|to)",
               r"spread the word", r"retweet", r"repost", r"send (?:this|it) to", r"make (?:this|it) viral",
               r"tell everyone", r"pass (?:this|it) on", r"don'?t let (?:this|it) stop with you", r"rt",
               r"tag your friends", r"copy and paste", r"spread this"],
        "ar": [r"انشر", r"انشروا", r"انشرها", r"انشروها", r"شارك", r"شاركوا", r"شاركها", r"ارسل", r"ارسلوا",
               r"ارسلها", r"ارسلوها", r"عمموا", r"عممها", r"ساهم في النشر", r"لا تجعلها تقف عندك",
               r"اجعلها تصل", r"وصلها", r"ريتويت", r"دز", r"دزها", r"دزوها", r"دزوا", r"طرش", r"طرشها", r"طرشوها",
               r"طرشوا", r"حطوها في (?:كل )?القروبات", r"نزلوها", r"عيدوا التغريد", r"منشن", r"علموا الكل",
               r"انسخ"],
    },
}

# Context markers (normalized). Used to qualify, not to suppress silently.
NEGATORS_EN = [r"don'?t", r"do not", r"never", r"no need to", r"not", r"stop", r"avoid", r"please don'?t",
               r"there is no", r"no reason to", r"without"]
NEGATORS_AR = [r"لا", r"لم", r"لن", r"عدم", r"ليس", r"ممنوع", r"تجنب", r"تجنبوا", r"لا داعي", r"دون", r"بدون",
               r"ما في", r"مافي", r"ما في داعي"]

REPORTED_EN = [r"claim(?:s|ed|ing)?", r"alleg\w+", r"a (?:viral )?post (?:says|said|claims)", r"circulating",
               r"reportedly", r"rumou?rs? (?:that|saying)", r"so-called", r"falsely"]
REPORTED_AR = [r"يزعم", r"زعم", r"تزعم", r"تداول", r"متداول", r"يتداول", r"ادعاء", r"يدعي", r"تدعي",
               r"منشور يقول", r"اشاعه تقول"]

ATTRIBUTION_EN = [r"according to", r"authorit(?:y|ies)", r"ministry", r"police", r"ncm", r"ncema",
                  r"official(?:ly|s)?", r"advis(?:ed|es|ory)", r"issued an? (?:warning|alert)",
                  r"meteorolog\w+", r"civil defen[cs]e", r"government"]
ATTRIBUTION_AR = [r"وفقا ل", r"حسب", r"اعلنت", r"اعلن", r"وزاره", r"شرطه", r"الجهات المختصه", r"المركز الوطني",
                  r"الهيئه", r"رسمي", r"رسميه", r"تحذير رسمي", r"الدفاع المدني", r"الحكومه", r"للارصاد",
                  r"الارصاد"]

DEBUNK_EN = [r"rumou?rs?", r"fake", r"hoax", r"misleading", r"not true", r"no truth", r"false(?:ly)?",
             r"fabricated", r"debunk\w*", r"misinformation"]
DEBUNK_AR = [r"شايعه", r"شايعات", r"اشاعه", r"اشاعات", r"مفبرك", r"مفبركه", r"كاذب", r"كاذبه",
             r"لا صحه", r"غير صحيح", r"عار عن الصحه", r"تنفي", r"نفت", r"مضلل", r"مضلله"]

ALARM_EMOJI = "🚨⚠‼❗🔴📢🆘"
