"""Language detection and text normalization. The original caption is never modified."""
from __future__ import annotations

import re
import unicodedata

ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
LATIN_RE = re.compile(r"[A-Za-z]")
TASHKEEL_RE = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
TATWEEL = "ـ"
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def detect_language(text: str) -> str:
    """Return 'ar', 'en', 'mixed' or 'not applicable' from script proportions.

    A transparent script heuristic, not a trained language-identification model.
    'en' here means Latin script; other Latin-script languages are not distinguished.
    """
    ar = len(ARABIC_RE.findall(text))
    la = len(LATIN_RE.findall(text))
    if ar + la == 0:
        return "not applicable" if not text.strip() else "en"
    share = ar / (ar + la)
    if share >= 0.8:
        return "ar"
    if share <= 0.2:
        return "en"
    return "mixed"


def normalize_arabic(text: str) -> str:
    text = TASHKEEL_RE.sub("", text).replace(TATWEEL, "")
    text = re.sub("[إأآٱ]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    return text


_QUOTES = {"“": '"', "”": '"', "«": '"', "»": '"', "„": '"', "’": "'", "‘": "'"}


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Normalize for analysis and return, for every output character, its index in the original.

    The map lets findings quote the exact original caption wording.
    """
    out: list[str] = []
    idx: list[int] = []
    prev_space = True
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFKC", ch):
            if TASHKEEL_RE.match(c) or c == TATWEEL:
                continue
            c = normalize_arabic(c).translate(ARABIC_DIGITS)
            c = _QUOTES.get(c, c).lower()
            for d in c:
                if d.isspace():
                    if prev_space:
                        continue
                    d, prev_space = " ", True
                else:
                    prev_space = False
                out.append(d)
                idx.append(i)
    while out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def normalize(text: str) -> str:
    """Analysis copy: NFKC, lower-case, unified Arabic letter forms and digits, collapsed whitespace."""
    return normalize_with_map(text)[0]
