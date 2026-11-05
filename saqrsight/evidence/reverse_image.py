"""Reverse image search through Google Cloud Vision Web Detection (optional).

What is sent: the stored, metadata-stripped JPEG of the image, or of at most
SAQRSIGHT_MAX_REVERSE_FRAMES sampled video frames. Nothing is sent unless GOOGLE_VISION_API_KEY is
set *and* the user ticked the consent box for this submission.

Match types returned by the provider and how they are reported:
  full_matching_images     -> "exact or near-exact match"
  partial_matching_images  -> "partial match" (e.g. crop or edit of the same photo)
  visually_similar_images  -> "visually similar only" (NOT evidence that the same photo appeared)
Pages are only those the provider returns. The earliest date found is never called the original.
"""
from __future__ import annotations

import base64
import re
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from ..analysis import claims
from ..config import Settings
from ..media import Visual
from ..schema import COMPLETED, FAILED, Finding, ModuleResult, not_applicable, not_configured

MODULE = "reverse_image_search"
VERSION = "google-vision-web-detection-v1"
ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
DATE_META = ("article:published_time", "og:published_time", "datepublished", "date", "pubdate",
             "publishdate", "dc.date", "dcterms.created", "article:modified_time")


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: str | None = None

    def handle_starttag(self, tag, attrs):
        if self.found or tag != "meta":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
        if key in DATE_META and a.get("content"):
            self.found = a["content"]


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    return None


def page_date(client: httpx.Client, url: str, timeout: float) -> date | None:
    """Publication date from the page's own metadata, if it declares one."""
    try:
        with client.stream("GET", url, timeout=timeout, follow_redirects=True,
                           headers={"User-Agent": "SaqrSight-research-prototype"}) as r:
            if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
                return None
            body = b""
            for chunk in r.iter_bytes():
                body += chunk
                if len(body) > 400_000:
                    break
        p = _MetaParser()
        p.feed(body.decode("utf-8", errors="ignore"))
        return parse_date(p.found)
    except (httpx.HTTPError, ValueError):
        return None


def claimed_window(details: claims.ClaimDetails, today: date) -> tuple[date, date] | None:
    """Approximate time window implied by relative wording ("today", "yesterday", "now")."""
    rel = set(details.relative_dates)
    if rel & {"today", "now"}:
        return today - timedelta(days=1), today
    if "yesterday" in rel:
        return today - timedelta(days=2), today
    if "this week" in rel:
        return today - timedelta(days=7), today
    explicit = [d for d in (claims.parse_claim_date(x, today.year) for x in details.dates) if d]
    if explicit:
        return min(explicit) - timedelta(days=2), max(explicit) + timedelta(days=2)
    return None


def analyze(visuals: list[Visual], caption: str, consent: bool, cfg: Settings,
            client: httpx.Client | None = None, today: date | None = None) -> ModuleResult:
    if not visuals:
        return not_applicable(MODULE, VERSION, "No image or video was supplied.")
    if not cfg.reverse_search_configured:
        return not_configured(MODULE, VERSION, "Reverse image search is not configured on this server "
                                               "(no provider API key).")
    if not consent:
        return not_applicable(MODULE, VERSION, "Skipped: you chose not to send media to an external search service.")
    today = today or datetime.now(timezone.utc).date()
    selected = visuals[: max(1, cfg.max_reverse_frames)]
    own = client is None
    client = client or httpx.Client()
    try:
        requests = [{"image": {"content": base64.b64encode(v.path.read_bytes()).decode()},
                     "features": [{"type": "WEB_DETECTION", "maxResults": 20}]} for v in selected]
        try:
            r = client.post(ENDPOINT, params={"key": cfg.google_vision_key}, json={"requests": requests},
                            timeout=cfg.http_timeout)
        except httpx.TimeoutException:
            return _failed("The search service did not respond in time.")
        except httpx.HTTPError as e:
            return _failed(f"Could not reach the search service ({type(e).__name__}).")
        if r.status_code != 200:
            return _failed(f"The search service returned an error (HTTP {r.status_code}).")
        responses = r.json().get("responses", [])
        details = claims.extract(caption) if caption else claims.ClaimDetails()
        window = claimed_window(details, today)
        exact_pages, similar_count, frames_checked = [], 0, []
        for v, resp in zip(selected, responses):
            frames_checked.append(v.public())
            if "error" in resp:
                return _failed("The search service could not process the image.")
            web = resp.get("webDetection", {})
            similar_count += len(web.get("visuallySimilarImages", []))
            for page in web.get("pagesWithMatchingImages", []):
                url = page.get("url", "")
                if not url.startswith(("http://", "https://")):
                    continue
                match = ("exact_or_near_exact" if page.get("fullMatchingImages")
                         else "partial" if page.get("partialMatchingImages") else "page_mentions_similar")
                title = re.sub(r"<[^>]+>", "", page.get("pageTitle", ""))[:300]
                exact_pages.append({"url": url, "title": title or None, "source": urlparse(url).netloc,
                                    "match_type": match, "frame": v.ref, "date": None})
        # Publication dates: read from page metadata for a few exact/near-exact matches only.
        exact_pages.sort(key=lambda p: p["match_type"] != "exact_or_near_exact")
        for p in exact_pages[:5]:
            if p["match_type"] != "page_mentions_similar":
                d = page_date(client, p["url"], min(5.0, cfg.http_timeout))
                p["date"] = d.isoformat() if d else None
        findings: list[Finding] = []
        for p in exact_pages:
            p["relation"] = "previous_appearance"
            notes = []
            if p["date"] and window and parse_date(p["date"]) < window[0]:
                notes.append("published before the time the caption claims")
                p["relation"] = "possible_context_discrepancy"
            if p["title"] and details.locations:
                t = claims.extract(p["title"])
                if t.locations and not set(t.locations) & set(details.locations):
                    notes.append("page title refers to a different place (" + ", ".join(t.locations) + ")")
                    p["relation"] = "possible_context_discrepancy"
            p["notes"] = notes
        discrepancies = [p for p in exact_pages if p["relation"] == "possible_context_discrepancy"]
        matches = [p for p in exact_pages if p["match_type"] != "page_mentions_similar"]
        if discrepancies:
            findings.append(Finding(
                code="possible_context_discrepancy", sources=discrepancies[:10],
                message="The same or a near-identical image appears on pages that suggest a different time or "
                        "place than the caption claims. Check those pages; this indicates possible "
                        "out-of-context reuse, not proof. The earliest page found is not necessarily the original."))
        if matches:
            findings.append(Finding(code="previous_appearances", sources=matches[:10],
                                    message=f"{len(matches)} page(s) contain the same or a near-identical image."))
        if not matches and (similar_count or exact_pages):
            findings.append(Finding(code="only_similar_images",
                                    message="Only visually similar images were found; they are not evidence that "
                                            "this photo appeared elsewhere."))
        if not matches and not similar_count and not exact_pages:
            findings.append(Finding(code="no_matches", message="No matching pages were found by the search provider. "
                                    "This does not show the image is new."))
        status_word = ("possible context discrepancy" if discrepancies else
                       "earlier appearances found" if matches else
                       "only similar images" if similar_count else "no matches")
        return ModuleResult(module=MODULE, status=COMPLETED, version=VERSION, findings=findings,
                            summary=f"Reverse image search: {status_word}.",
                            limitations=["Coverage is limited to pages indexed by the provider.",
                                         "Publication dates come from page metadata and may be missing or wrong.",
                                         "Matches show where an image appeared, not who created it first."],
                            data={"outcome": status_word.replace(" ", "_"), "frames_sent": frames_checked,
                                  "provider": "Google Cloud Vision"})
    finally:
        if own:
            client.close()


def _failed(reason: str) -> ModuleResult:
    return ModuleResult(module=MODULE, status=FAILED, version=VERSION,
                        summary="Reverse image search failed; no conclusion can be drawn from it.", error=reason)
