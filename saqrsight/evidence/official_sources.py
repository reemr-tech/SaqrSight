"""Retrieval from a configurable list of official UAE sources (optional).

Queries are built from the event, location and time extracted from the caption, in English and
Arabic. Only the extracted keywords are sent to the search provider – never the full caption or media.
Each result is then checked for the *same event, place and time*; keyword overlap alone is not enough.

Relation labels
  supporting      same event and place, compatible date, no denial wording
  contradicting   same event and place, and the source denies or calls the claim a rumour
  insufficient    related wording but a different place/time, or no date to compare
Results from domains outside the configured list are discarded.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import httpx

from ..analysis import claims
from ..analysis.lexicon import DEBUNK_AR, DEBUNK_EN
from ..config import Settings
from ..schema import COMPLETED, FAILED, Finding, ModuleResult, not_applicable, not_configured
from ..textutil import normalize
from .reverse_image import claimed_window, parse_date

MODULE = "official_sources"
DENIAL_RE = re.compile("|".join([r"\b(?:" + p + r")\b" for p in DEBUNK_EN + [r"den(?:y|ies|ied)", r"refut\w+"]]
                                + DEBUNK_AR + [r"ينفي", r"تنفي", r"نفي"]))
AR_EVENT = {"fire": "حريق", "smoke": "دخان", "flood": "سيول", "rain": "امطار", "sandstorm": "غبار",
            "fog": "ضباب", "explosion": "انفجار", "accident": "حادث", "collapse": "انهيار", "earthquake": "زلزال",
            "shortage": "نقص", "closure": "اغلاق", "outbreak": "تفشي", "protest": "احتجاج", "attack": "هجوم"}
AR_PLACE = {name: next((f for f in forms if not re.search(r"[a-z]", f)), name)
            for name, forms in claims.LOCATIONS.items()}


def build_queries(d: claims.ClaimDetails, limit: int) -> list[str]:
    places = [p for p in d.locations if p != "UAE"] or d.locations or ["UAE"]
    qs = []
    for ev in d.events[:2]:
        for pl in places[:2]:
            qs.append(f"{ev} {pl}")
            qs.append(f"{AR_EVENT.get(ev, ev)} {AR_PLACE.get(pl, pl)}")
    return list(dict.fromkeys(qs))[:limit]


def _domain_ok(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def search_brave(client: httpx.Client, cfg: Settings, query: str) -> list[dict]:
    sites = " OR ".join(f"site:{d}" for d in cfg.official_domains)
    r = client.get("https://api.search.brave.com/res/v1/web/search",
                   params={"q": f"{query} ({sites})", "count": 10},
                   headers={"X-Subscription-Token": cfg.brave_key, "Accept": "application/json"},
                   timeout=cfg.http_timeout)
    r.raise_for_status()
    out = []
    for it in r.json().get("web", {}).get("results", []):
        out.append({"url": it.get("url", ""), "title": it.get("title", ""),
                    "snippet": re.sub(r"<[^>]+>", "", it.get("description", "")),
                    "date": parse_date(it.get("page_age"))})
    return out


def search_google_cse(client: httpx.Client, cfg: Settings, query: str) -> list[dict]:
    r = client.get("https://www.googleapis.com/customsearch/v1",
                   params={"key": cfg.google_cse_key, "cx": cfg.google_cse_cx, "q": query, "num": 10},
                   timeout=cfg.http_timeout)
    r.raise_for_status()
    out = []
    for it in r.json().get("items", []):
        meta = (it.get("pagemap", {}).get("metatags") or [{}])[0]
        out.append({"url": it.get("link", ""), "title": it.get("title", ""), "snippet": it.get("snippet", ""),
                    "date": parse_date(meta.get("article:published_time") or meta.get("og:updated_time"))})
    return out


PROVIDERS = {"brave": search_brave, "google_cse": search_google_cse}


def judge(result: dict, d: claims.ClaimDetails, today: date) -> dict:
    """Does this source address the same event, place and time? Returns the relation and why."""
    text = f"{result['title']} {result['snippet']}"
    r = claims.extract(text)
    same_event = bool(set(r.events) & set(d.events))
    specific = [p for p in d.locations if p != "UAE"]
    same_place = (not specific) or bool(set(r.locations) & set(specific))
    window = claimed_window(d, today)
    date_known = result.get("date") is not None
    claimed_dates = [parse_date(x) for x in d.dates]
    claimed_dates = [x for x in claimed_dates if x]
    if not date_known:
        same_time = None
    elif window:
        same_time = window[0] <= result["date"] <= window[1]
    elif claimed_dates:
        same_time = any(abs((result["date"] - c).days) <= 2 for c in claimed_dates)
    else:
        same_time = None
    reasons = [("same event" if same_event else "different or unclear event"),
               ("same place" if same_place else "different place"),
               ("date not available" if same_time is None else "same time" if same_time else "different date")]
    denial = DENIAL_RE.search(normalize(text)) is not None
    if same_event and same_place and same_time is not False:
        if denial:
            relation = "contradicting"
        elif same_time:
            relation = "supporting"
        else:
            relation = "insufficient"   # matching event and place but no date to compare
    else:
        relation = "insufficient"
    relevant = same_event and same_place and same_time is not False
    return {"relation": relation, "relevant": relevant, "reasons": reasons}


def analyze(caption: str, details: claims.ClaimDetails, consent: bool, cfg: Settings,
            client: httpx.Client | None = None, today: date | None = None) -> ModuleResult:
    provider = cfg.search_provider
    version = f"official-sources-v1:{provider}"
    if not caption.strip():
        return not_applicable(MODULE, version, "No caption was supplied, so there is no claim to search for.")
    if not cfg.official_search_configured:
        return not_configured(MODULE, version, "Official-source search is not configured on this server "
                                               "(no search provider API key).")
    if not consent:
        return not_applicable(MODULE, version, "Skipped: you chose not to use external search services.")
    if not details.searchable:
        return not_applicable(MODULE, version, "The caption does not state an event with a place or time "
                                               "that can be searched for.")
    search = PROVIDERS.get(provider)
    if search is None:
        return not_configured(MODULE, version, f"Unknown search provider '{provider}'.")
    today = today or datetime.now(timezone.utc).date()
    queries = build_queries(details, cfg.max_search_queries)
    own = client is None
    client = client or httpx.Client()
    results, errors = {}, []
    try:
        for q in queries:
            try:
                for item in search(client, cfg, q):
                    if item["url"].startswith(("http://", "https://")) and _domain_ok(item["url"], cfg.official_domains):
                        results.setdefault(item["url"], item)
            except httpx.TimeoutException:
                errors.append("timeout")
            except (httpx.HTTPError, ValueError, KeyError) as e:
                errors.append(type(e).__name__)
    finally:
        if own:
            client.close()
    if errors and len(errors) == len(queries):
        return ModuleResult(module=MODULE, status=FAILED, version=version,
                            summary="Official-source search failed; no conclusion can be drawn from it.",
                            error="All searches failed (" + ", ".join(sorted(set(errors))) + ").",
                            data={"queries": queries})
    judged = []
    for item in results.values():
        j = judge(item, details, today)
        judged.append({"url": item["url"], "title": item["title"], "excerpt": item["snippet"][:400],
                       "date": item["date"].isoformat() if item["date"] else None,
                       "source": urlparse(item["url"]).hostname, **j})
    relevant = [j for j in judged if j["relevant"]]
    findings = []
    for rel, msg in (("contradicting", "Official source(s) addressing the same event and place deny it or call it a rumour."),
                     ("supporting", "Official source(s) report the same event, place and time.")):
        hits = [j for j in relevant if j["relation"] == rel]
        if hits:
            findings.append(Finding(code=rel, message=msg, sources=hits))
    weak = [j for j in judged if j not in relevant or j["relation"] == "insufficient"]
    if weak:
        findings.append(Finding(code="insufficient", sources=weak[:8],
                                message="Results that mention related terms but do not establish the same event, "
                                        "place and time. They are shown for context only."))
    if not relevant:
        findings.append(Finding(code="no_relevant_result",
                                message="No relevant result was found in the sources searched ("
                                        + ", ".join(cfg.official_domains) + "). This does not show the claim is false."))
    outcome = ("contradicting" if any(f.code == "contradicting" for f in findings) else
               "supporting" if any(f.code == "supporting" for f in findings) else
               "insufficient" if relevant else "no_relevant_result")
    lim = ["Searches only the configured official domains through a third-party search index.",
           "Relevance is judged by rule from titles and excerpts; read the source before relying on it."]
    if errors:
        lim.append(f"{len(errors)} of {len(queries)} searches failed; results may be incomplete.")
    return ModuleResult(module=MODULE, status=COMPLETED, version=version, findings=findings,
                        summary={"contradicting": "An official source appears to contradict the claim.",
                                 "supporting": "An official source appears to report the same event.",
                                 "insufficient": "Related official coverage was found but does not settle the claim.",
                                 "no_relevant_result": "No relevant result in the official sources searched."}[outcome],
                        limitations=lim,
                        data={"outcome": outcome, "queries": queries, "domains": cfg.official_domains,
                              "results_considered": len(judged)})
