"""Extract checkable claim details (event, location, date) from a caption.

Rule-based and bilingual. Used by the consistency check (to say which details the image alone
cannot establish) and by official-source retrieval (to build queries and test relevance).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from ..textutil import normalize

# canonical English name -> normalized surface forms (English and Arabic)
LOCATIONS = {
    "UAE": ["uae", "united arab emirates", "the emirates", "الامارات", "دوله الامارات"],
    "Dubai": ["dubai", "دبي"],
    "Abu Dhabi": ["abu dhabi", "abudhabi", "ابوظبي", "ابو ظبي"],
    "Sharjah": ["sharjah", "الشارقه"],
    "Ajman": ["ajman", "عجمان"],
    "Ras Al Khaimah": ["ras al khaimah", "ras al-khaimah", "rak", "راس الخيمه"],
    "Fujairah": ["fujairah", "الفجيره"],
    "Umm Al Quwain": ["umm al quwain", "umm al-quwain", "ام القيوين"],
    "Al Ain": ["al ain", "مدينه العين"],
    "Dubai Marina": ["dubai marina", "مارينا دبي", "دبي مارينا"],
    "Burj Khalifa": ["burj khalifa", "برج خليفه"],
    "Jebel Ali": ["jebel ali", "جبل علي"],
    "Deira": ["deira", "ديره"],
    "Jumeirah": ["jumeirah", "جميرا", "جميرا"],
    "Khor Fakkan": ["khor fakkan", "خورفكان"],
    "Hatta": ["hatta", "حتا"],
    "Sheikh Zayed Road": ["sheikh zayed road", "szr", "شارع الشيخ زايد"],
    "Dubai International Airport": ["dubai airport", "dxb", "مطار دبي"],
    "Abu Dhabi Airport": ["abu dhabi airport", "auh", "مطار ابوظبي"],
}

EVENTS = {
    "fire": ["fire", "blaze", "on fire", "burning", "حريق", "حرايق", "نيران", "يحترق"],
    "smoke": ["smoke", "دخان"],
    "flood": ["flood", "flooding", "floods", "فيضان", "فيضانات", "سيول", "غرق"],
    "rain": ["rain", "heavy rain", "storm", "thunderstorm", "امطار", "مطر", "عاصفه", "عواصف"],
    "sandstorm": ["sandstorm", "dust storm", "عاصفه رمليه", "غبار"],
    "fog": ["fog", "ضباب"],
    "explosion": ["explosion", "blast", "exploded", "انفجار", "انفجارات"],
    "accident": ["accident", "crash", "collision", "حادث", "حادثه", "تصادم"],
    "collapse": ["collapse", "collapsed", "انهيار", "انهار"],
    "earthquake": ["earthquake", "tremor", "زلزال", "هزه ارضيه"],
    "shortage": ["shortage", "shortages", "empty shelves", "نقص", "نفاد"],
    "closure": ["closed", "closure", "lockdown", "shut down", "اغلاق", "مغلق", "حظر"],
    "outbreak": ["outbreak", "virus", "epidemic", "تفشي", "فيروس", "وباء"],
    "protest": ["protest", "riot", "مظاهره", "احتجاج"],
    "attack": ["attack", "drone", "missile", "هجوم", "مسيره", "صاروخ"],
}

MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december|"
          "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|"
          "يناير|فبراير|مارس|ابريل|مايو|يونيو|يوليو|اغسطس|سبتمبر|اكتوبر|نوفمبر|ديسمبر")
RELATIVE_DATES = {
    "today": "today", "tonight": "today", "this morning": "today", "this evening": "today", "now": "now",
    "right now": "now", "yesterday": "yesterday", "last night": "yesterday", "this week": "this week",
    "اليوم": "today", "الليله": "today", "هذا الصباح": "today", "صباح اليوم": "today", "مساء اليوم": "today",
    "الان": "now", "امس": "yesterday", "البارحه": "yesterday", "هذا الاسبوع": "this week",
}
DATE_PATTERNS = [
    re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2} (?:" + MONTHS + r")(?: \d{4})?\b"),
    re.compile(r"\b(?:" + MONTHS + r") \d{1,2}(?:,? \d{4})?\b"),
    re.compile(r"\b(?:19|20)\d{2}\b"),
]


@dataclass
class ClaimDetails:
    locations: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)          # explicit dates as written (normalized)
    relative_dates: list[str] = field(default_factory=list)  # today / yesterday / now ...

    @property
    def has_time(self) -> bool:
        return bool(self.dates or self.relative_dates)

    @property
    def searchable(self) -> bool:
        """Enough detail for an official-source search: an event plus a place or a time."""
        return bool(self.events and (self.locations or self.has_time))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["searchable"] = self.searchable
        return d


def _has(norm: str, form: str) -> bool:
    if re.search(r"[a-z]", form):
        return re.search(r"(?<![\w])" + re.escape(form) + r"(?![\w])", norm) is not None
    return re.search(r"(?<!\w)(?:و|ف|ب|ل|ال|وال|بال|في)?" + re.escape(form) + r"(?!\w)", norm) is not None


def extract(caption: str) -> ClaimDetails:
    norm = normalize(caption)
    d = ClaimDetails()
    for name, forms in LOCATIONS.items():
        if any(_has(norm, f) for f in forms):
            d.locations.append(name)
    for name, forms in EVENTS.items():
        if any(_has(norm, f) for f in forms):
            d.events.append(name)
    for form, value in RELATIVE_DATES.items():
        if _has(norm, form) and value not in d.relative_dates:
            d.relative_dates.append(value)
    seen = set()
    for pat in DATE_PATTERNS:
        for m in pat.finditer(norm):
            if not any(m.start() >= s and m.end() <= e for s, e in seen):
                d.dates.append(m.group(0))
                seen.add((m.start(), m.end()))
    return d
