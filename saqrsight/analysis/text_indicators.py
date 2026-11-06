"""Bilingual language-indicator baseline.

Finds wording associated with urgency, fear, manipulation and pressure to share, and returns
the exact caption phrases. Each match is qualified by its context:

  active              counted as an indicator
  negated             e.g. "Do not share this" / "لا داعي للهلع" – discourages the behaviour
  reported            inside quotation marks or after "claims", "يزعم", "تداول" – describes someone else's words
  debunk              in a sentence that calls something a rumour/false – e.g. "Rumours of a lockdown are false"
  attributed_warning  alarming wording in a sentence attributed to an authority – may be a legitimate warning

Only "active" matches contribute to the indicator level. The result is a description of wording,
not a prediction that the post will cause panic or that the claim is false.
"""
from __future__ import annotations

import re
from functools import lru_cache

from ..schema import COMPLETED, Finding, ModuleResult, not_applicable
from ..textutil import TASHKEEL_RE, TATWEEL, normalize_with_map
from . import lexicon as L

MODULE = "text_analysis"
VERSION = "text-lexicon-1.1"
AR_PREFIX = r"(?:و|ف|ب|ل|ال|وال|فال|بال|لل)?"
AR_SUFFIX = r"(?:ها|هم|ه|وا)?"
CLAUSE_SPLIT = re.compile(r"[.!?؟؛;\n،,:]")
SENTENCE_SPLIT = re.compile(r"[.!?؟\n]")


def _en(p: str) -> str:
    return r"(?<![\w'])(?:" + p + r")(?![\w'])"


def _ar(p: str) -> str:
    return r"(?<!\w)" + AR_PREFIX + "(?:" + p + ")" + AR_SUFFIX + r"(?!\w)"


@lru_cache(maxsize=1)
def _compiled():
    cats = {}
    for name, spec in L.CATEGORIES.items():
        cats[name] = [re.compile(_en(p)) for p in spec["en"]] + [re.compile(_ar(p)) for p in spec["ar"]]

    def group(en, ar):
        return re.compile("|".join([_en(p) for p in en] + [_ar(p) for p in ar]))

    return (cats, group(L.NEGATORS_EN, L.NEGATORS_AR), group(L.REPORTED_EN, L.REPORTED_AR),
            group(L.ATTRIBUTION_EN, L.ATTRIBUTION_AR), group(L.DEBUNK_EN, L.DEBUNK_AR))


def _span_bounds(text: str, pos: int, splitter: re.Pattern) -> tuple[int, int]:
    start = 0
    for m in splitter.finditer(text, 0, pos):
        start = m.end()
    m = splitter.search(text, pos)
    return start, (m.start() if m else len(text))


def _context(norm: str, start: int, end: int, category: str) -> str:
    _, negators, reported, attribution, debunk = _compiled()
    c_start, _ = _span_bounds(norm, start, CLAUSE_SPLIT)
    s_start, s_end = _span_bounds(norm, start, SENTENCE_SPLIT)
    before_clause = norm[c_start:start]
    # Negation: a negator among the last four tokens of the same clause.
    window = " ".join(before_clause.split()[-4:])
    if negators.search(window):
        return "negated"
    # Quotation: an odd number of quote marks before the match, with a closing one after it.
    if norm[:start].count('"') % 2 == 1 and '"' in norm[end:]:
        return "reported"
    if reported.search(norm[s_start:start]):
        return "reported"
    sentence = norm[s_start:s_end]
    if debunk.search(sentence) and category != "share_pressure":
        return "debunk"
    if category in ("fear", "urgency") and attribution.search(sentence):
        return "attributed_warning"
    return "active"


def _style_signals(original: str) -> list[tuple[str, str]]:
    """Typographic urgency: repeated exclamation marks, alarm emoji, shouted words."""
    out = []
    m = re.search(r"[!！]{2,}", original)
    if m:
        out.append(("repeated_exclamation", m.group(0)))
    emoji = [c for c in original if c in L.ALARM_EMOJI]
    if emoji:
        out.append(("alarm_emoji", "".join(dict.fromkeys(emoji))))
    caps = re.findall(r"\b[A-Z]{4,}\b", original)
    caps = [w for w in caps if w not in {"UAE", "NCEMA", "COVID", "WAM", "NCM", "RTA", "DEWA", "UNESCO"}]
    if len(caps) >= 2:
        out.append(("shouting", " ".join(caps[:4])))
    return out


def find_matches(caption: str) -> list[dict]:
    """Return every lexicon match with its category, exact original excerpt and context."""
    norm, idx = normalize_with_map(caption)
    cats = _compiled()[0]
    matches: list[dict] = []
    for category, patterns in cats.items():
        spans: list[tuple[int, int]] = []
        for pat in patterns:
            for m in pat.finditer(norm):
                spans.append((m.start(), m.end()))
        # keep the longest non-overlapping spans
        spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
        last_end = -1
        for s, e in spans:
            if s < last_end:
                continue
            last_end = e
            end = idx[e - 1] + 1
            while end < len(caption) and (TASHKEEL_RE.match(caption[end]) or caption[end] == TATWEEL):
                end += 1   # keep diacritics that belong to the last matched letter
            excerpt = caption[idx[s]: end]
            matches.append({"category": category, "excerpt": excerpt, "start": idx[s],
                            "context": _context(norm, s, e, category)})
    matches.sort(key=lambda m: m["start"])
    return matches


def level_for(active: list[dict]) -> str:
    cats = {m["category"] for m in active}
    n = len(active)
    if n == 0:
        return "none"
    if len(cats) >= 3 or ("share_pressure" in cats and cats & {"fear", "urgency"} and n >= 3):
        return "high"
    if len(cats) >= 2 or n >= 3:
        return "moderate"
    return "low"


CONTEXT_TEXT = {
    "negated": "Negated – the wording discourages this behaviour (for example “do not share”).",
    "reported": "Quoted or reported – the post appears to describe someone else's wording.",
    "debunk": "Used while calling something a rumour or false.",
    "attributed_warning": "Alarming wording attributed to an authority – may be a legitimate warning; "
                          "confirm the authority actually issued it.",
}


def analyze(caption: str, language: str) -> ModuleResult:
    if not caption.strip():
        return not_applicable(MODULE, VERSION, "No text was supplied.")
    matches = find_matches(caption)
    style = _style_signals(caption)
    active = [m for m in matches if m["context"] == "active"]
    findings: list[Finding] = []
    for category, spec in L.CATEGORIES.items():
        ex = [m["excerpt"] for m in active if m["category"] == category]
        if category == "urgency":
            ex += [s[1] for s in style]
        if ex:
            findings.append(Finding(code=category, message=spec["explain_en"],
                                    excerpts=list(dict.fromkeys(ex)),
                                    details={"label_en": spec["label_en"], "label_ar": spec["label_ar"],
                                             "explain_ar": spec["explain_ar"]}))
    for ctx, text in CONTEXT_TEXT.items():
        ex = [m["excerpt"] for m in matches if m["context"] == ctx]
        if ex:
            findings.append(Finding(code="context_" + ctx, message=text, excerpts=list(dict.fromkeys(ex)),
                                    details={"categories": sorted({m["category"] for m in matches
                                                                   if m["context"] == ctx})}))
    counted = active + [{"category": "urgency"} for _ in style]
    level = level_for(counted)
    cats = sorted({m["category"] for m in counted})
    if level == "none":
        summary = "No urgency, fear, manipulation or share-pressure wording from the indicator list was found."
    else:
        summary = (f"Language indicator level: {level}. Categories detected: "
                   + ", ".join(L.CATEGORIES[c]["label_en"] for c in cats) + ".")
    return ModuleResult(
        module=MODULE, status=COMPLETED, version=VERSION, findings=findings, summary=summary,
        data={"indicator_level": level, "categories": cats, "matches": matches,
              "style_signals": [s[0] for s in style], "language": language},
        limitations=[
            "Rule-based wording indicators; they describe language, not whether the claim is true.",
            "Does not predict how readers will react.",
            "Dialect, sarcasm, misspellings and transliterated Arabic (Arabizi) may be missed.",
        ])
