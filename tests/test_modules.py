"""Unit tests for analysis modules, assessment rules and evidence providers (no network, no models)."""
from datetime import date

import httpx
import pytest

from saqrsight import assessment
from saqrsight.analysis import claims, text_indicators
from saqrsight.config import Settings
from saqrsight.evidence import official_sources, reverse_image
from saqrsight.media import Visual
from saqrsight.schema import Finding, ModuleResult
from saqrsight.textutil import detect_language, normalize, normalize_with_map

TODAY = date(2026, 11, 4)


# ---------------- text -----------------------------------------------------------------------
def ctx(caption):
    return {(m["category"], m["context"]) for m in text_indicators.find_matches(caption)}


def test_normalization_keeps_original_excerpts():
    caption = "عَاجِلٌ: انشـــروها الآن"
    norm, idx = normalize_with_map(caption)
    assert "عاجل" in norm and "انشروها" in norm
    r = text_indicators.analyze(caption, "ar")
    excerpts = [e for f in r.findings for e in f.excerpts]
    assert "عَاجِلٌ" in excerpts and "انشـــروها" in excerpts   # exact original wording returned


def test_language_detection():
    assert detect_language("Fire in Dubai") == "en"
    assert detect_language("حريق في دبي") == "ar"
    assert detect_language("Breaking عاجل حريق في دبي marina now") == "mixed"
    assert normalize("أحمد  إلى") == "احمد الي"


@pytest.mark.parametrize("caption,expected", [
    ("Share this immediately!", {("share_pressure", "active"), ("urgency", "active")}),
    ("Do not share this rumor.", {("share_pressure", "negated")}),
    ("لا تنشروا الشائعات، ولا داعي للهلع", {("fear", "negated")}),
    ('A viral post claims "share this immediately" but it is fake.',
     {("share_pressure", "reported"), ("urgency", "reported")}),
    ("Rumours of a lockdown in Abu Dhabi are false.", {("fear", "debunk")}),
    ("According to NCM, dangerous conditions are expected; avoid wadis.", {("fear", "attributed_warning")}),
    ("يزعم منشور أن هناك انفجار في دبي", {("fear", "reported")}),
])
def test_text_contexts(caption, expected):
    assert ctx(caption) == expected


def test_text_levels_and_none():
    hi = text_indicators.analyze("URGENT!!! Share this before they delete it, explosion in Dubai", "en")
    assert hi.data["indicator_level"] == "high"
    assert {"urgency", "share_pressure", "manipulation", "fear"} <= set(hi.data["categories"])
    calm = text_indicators.analyze("The Dubai Metro red line opens at 5am on Friday.", "en")
    assert calm.data["indicator_level"] == "none" and not [f for f in calm.findings if f.code == "fear"]
    assert text_indicators.analyze("   ", "en").status == "not_applicable"


# ---------------- claims ---------------------------------------------------------------------
def test_claim_extraction_bilingual():
    d = claims.extract("Huge fire at Dubai Marina today")
    assert d.locations == ["Dubai", "Dubai Marina"] and d.events == ["fire"] and d.relative_dates == ["today"]
    assert d.searchable
    d = claims.extract("سيول في الشارقة يوم 3 نوفمبر 2026")
    assert "Sharjah" in d.locations and "flood" in d.events and "3 نوفمبر 2026" in d.dates
    assert not claims.extract("What a lovely day").searchable


# ---------------- assessment rules -----------------------------------------------------------
def mod(name, status="completed", codes=(), data=None, confidence=None):
    return ModuleResult(module=name, status=status, version="t",
                        findings=[Finding(code=c, message="") for c in codes],
                        data=data or {}, confidence=confidence).to_dict()


def text_mod(level="none", cats=()):
    return mod("text_analysis", data={"indicator_level": level, "categories": list(cats)})


def test_urgent_wording_alone_is_not_misleading():
    d = claims.extract("URGENT fire in Dubai now, share!")
    a = assessment.assess({"text_analysis": text_mod("high", ["urgency", "fear", "share_pressure"])}, d, True, False)
    assert a["verdict"] == "insufficient_evidence" and a["rule"] == "A4"
    assert a["priority"]["level"] == "high"   # priority independent of verdict


def test_synthetic_signal_alone_is_not_misleading():
    d = claims.extract("A camel in Al Ain")
    mods = {"text_analysis": text_mod(), "media_analysis": mod("media_analysis", codes=["possible_synthetic"],
                                                               confidence="validated"),
            "consistency_check": mod("consistency_check", data={"decision": "agree"}, confidence="validated")}
    a = assessment.assess(mods, d, True, True)
    assert a["verdict"] == "insufficient_evidence" and a["rule"] == "A2"
    assert [i["code"] for i in a["issue_types"]] == ["possible_synthetic_media"]


def test_unvalidated_signals_are_ignored():
    mods = {"media_analysis": mod("media_analysis", codes=["possible_synthetic"], confidence=None),
            "consistency_check": mod("consistency_check", data={"decision": "disagree"}, confidence=None)}
    a = assessment.assess(mods, claims.ClaimDetails(), True, True)
    assert a["verdict"] == "insufficient_evidence" and a["issue_types"] == []


def test_failed_search_is_not_misleading():
    mods = {"text_analysis": text_mod(), "official_sources": mod("official_sources", status="failed"),
            "reverse_image_search": mod("reverse_image_search", status="failed")}
    assert assessment.assess(mods, claims.extract("Fire in Dubai"), True, True)["verdict"] == "insufficient_evidence"


def test_contradictions_make_potentially_misleading():
    d = claims.extract("Fire in Dubai Marina today")
    for mods, issue in [
        ({"consistency_check": mod("consistency_check", data={"decision": "disagree"}, confidence="validated")},
         "possible_miscaptioning"),
        ({"reverse_image_search": mod("reverse_image_search", codes=["possible_context_discrepancy"])},
         "possible_out_of_context"),
        ({"official_sources": mod("official_sources", codes=["contradicting"])}, "contradicted_by_official_source"),
    ]:
        a = assessment.assess(mods, d, True, True)
        assert a["verdict"] == "potentially_misleading" and a["rule"] == "A1"
        assert issue in [i["code"] for i in a["issue_types"]]
        assert a["priority"]["level"] in ("medium", "high")


def test_topic_agreement_cannot_vouch_for_place_or_time():
    agree = {"consistency_check": mod("consistency_check", data={"decision": "agree"}, confidence="validated")}
    d = claims.extract("Smoke over a building in Dubai today")
    a = assessment.assess(agree, d, True, True)
    assert a["verdict"] == "insufficient_evidence" and a["rule"] == "A4"
    assert "cannot establish" in a["explanation"]["en"] and "Dubai" in a["explanation"]["en"]
    acts = assessment.recommended_actions({}, d, a)
    assert any("first published" in x["en"] for x in acts)


def test_apparently_consistent_lists_unverified_details():
    agree = {"consistency_check": mod("consistency_check", data={"decision": "agree"}, confidence="validated")}
    a = assessment.assess(agree, claims.extract("Smoke rising over a building"), True, True)
    assert a["verdict"] == "apparently_consistent" and a["rule"] == "A3"
    assert "Still unverified" in a["explanation"]["en"]       # the event itself remains unverified
    d = claims.extract("Fire at Dubai Marina today")
    a = assessment.assess({"official_sources": mod("official_sources", codes=["supporting"])}, d, True, False)
    assert a["verdict"] == "apparently_consistent"
    assert "Still unverified" not in a["explanation"]["en"] and "Read the cited source" in a["explanation"]["en"]


# ---------------- evidence providers ---------------------------------------------------------
@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SAQRSIGHT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_VISION_API_KEY", "test-key")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-key")
    return Settings()


@pytest.fixture
def visual(tmp_path):
    from PIL import Image
    p = tmp_path / "image.jpg"
    Image.new("RGB", (40, 40), "red").save(p)
    return [Visual("image", p, 40, 40)]


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_reverse_not_configured_and_skipped(tmp_path, monkeypatch, visual):
    monkeypatch.setenv("SAQRSIGHT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GOOGLE_VISION_API_KEY", raising=False)
    assert reverse_image.analyze(visual, "x", True, Settings()).status == "not_configured"
    monkeypatch.setenv("GOOGLE_VISION_API_KEY", "k")
    r = reverse_image.analyze(visual, "x", False, Settings())
    assert r.status == "not_applicable" and "Skipped" in r.summary


def test_reverse_context_discrepancy(cfg, visual):
    def handler(req):
        if req.url.host == "vision.googleapis.com":
            return httpx.Response(200, json={"responses": [{"webDetection": {
                "pagesWithMatchingImages": [
                    {"url": "https://news.example/2019/fire", "pageTitle": "Warehouse fire in Sharjah",
                     "fullMatchingImages": [{"url": "https://news.example/a.jpg"}]},
                    {"url": "https://blog.example/similar", "pageTitle": "Something"}],
                "visuallySimilarImages": [{"url": "https://x.example/1.jpg"}]}}]})
        return httpx.Response(200, headers={"content-type": "text/html"},
                              text='<meta property="article:published_time" content="2019-05-02T10:00:00Z">')
    r = reverse_image.analyze(visual, "Huge fire in Dubai today", True, cfg, client_for(handler), TODAY)
    assert r.status == "completed"
    codes = {f.code for f in r.findings}
    assert "possible_context_discrepancy" in codes and "previous_appearances" in codes
    src = next(f for f in r.findings if f.code == "possible_context_discrepancy").sources[0]
    assert src["url"] == "https://news.example/2019/fire" and src["date"] == "2019-05-02"
    assert src["match_type"] == "exact_or_near_exact"
    assert any("different place" in n for n in src["notes"])


def test_reverse_only_similar_no_matches_and_failures(cfg, visual):
    only_similar = lambda req: httpx.Response(200, json={"responses": [{"webDetection": {  # noqa: E731
        "visuallySimilarImages": [{"url": "https://x.example/1.jpg"}]}}]})
    r = reverse_image.analyze(visual, "x", True, cfg, client_for(only_similar), TODAY)
    assert {f.code for f in r.findings} == {"only_similar_images"} and r.data["outcome"] == "only_similar_images"
    nothing = lambda req: httpx.Response(200, json={"responses": [{"webDetection": {}}]})  # noqa: E731
    r = reverse_image.analyze(visual, "x", True, cfg, client_for(nothing), TODAY)
    assert {f.code for f in r.findings} == {"no_matches"}

    def timeout(req):
        raise httpx.ReadTimeout("slow", request=req)
    r = reverse_image.analyze(visual, "x", True, cfg, client_for(timeout), TODAY)
    assert r.status == "failed" and "in time" in r.error
    r = reverse_image.analyze(visual, "x", True, cfg, client_for(lambda req: httpx.Response(403)), TODAY)
    assert r.status == "failed" and "403" in r.error


def brave(results):
    return lambda req: httpx.Response(200, json={"web": {"results": results}})


def test_official_sources_relations(cfg):
    d = claims.extract("Fire at Dubai Marina today")
    results = [
        {"url": "https://www.dubaipolice.gov.ae/news/1", "title": "Dubai Police deny rumours of fire in Dubai Marina",
         "description": "No truth to the fire reports", "page_age": "2026-11-04T08:00:00"},
        {"url": "https://wam.ae/en/article/2", "title": "Civil defence controls fire in Dubai Marina tower",
         "description": "Fire contained", "page_age": "2026-11-04T09:00:00"},
        {"url": "https://wam.ae/en/article/old", "title": "Fire in Dubai Marina building",
         "description": "", "page_age": "2021-03-01T09:00:00"},
        {"url": "https://wam.ae/en/article/nodate", "title": "Fire in Dubai Marina", "description": ""},
        {"url": "https://wam.ae/en/article/other", "title": "Flooding in Ras Al Khaimah", "description": "",
         "page_age": "2026-11-04T09:00:00"},
        {"url": "https://unofficial.example/fire", "title": "Fire in Dubai Marina", "description": "",
         "page_age": "2026-11-04T09:00:00"},
    ]
    r = official_sources.analyze("Fire at Dubai Marina today", d, True, cfg, client_for(brave(results)), TODAY)
    assert r.status == "completed"
    by = {f.code: f for f in r.findings}
    assert [s["url"] for s in by["contradicting"].sources] == ["https://www.dubaipolice.gov.ae/news/1"]
    assert [s["url"] for s in by["supporting"].sources] == ["https://wam.ae/en/article/2"]
    weak = {s["url"]: s for s in by["insufficient"].sources}
    assert "different date" in weak["https://wam.ae/en/article/old"]["reasons"]
    assert "date not available" in weak["https://wam.ae/en/article/nodate"]["reasons"]
    assert "different place" in weak["https://wam.ae/en/article/other"]["reasons"]
    all_urls = {s["url"] for f in r.findings for s in f.sources}
    assert "https://unofficial.example/fire" not in all_urls   # outside configured domains
    assert r.data["outcome"] == "contradicting"
    assert all("Marina" not in q or "fire" in q or "حريق" in q for q in r.data["queries"])


def test_official_sources_no_result_failure_and_not_searchable(cfg):
    d = claims.extract("Fire at Dubai Marina today")
    r = official_sources.analyze("x", d, True, cfg, client_for(brave([])), TODAY)
    assert r.data["outcome"] == "no_relevant_result"
    assert "in the sources searched" in next(f for f in r.findings if f.code == "no_relevant_result").message

    def boom(req):
        raise httpx.ConnectError("down", request=req)
    r = official_sources.analyze("x", d, True, cfg, client_for(boom), TODAY)
    assert r.status == "failed"
    r = official_sources.analyze("nice weather", claims.extract("nice weather"), True, cfg)
    assert r.status == "not_applicable"
    r = official_sources.analyze("x", d, False, cfg)
    assert r.status == "not_applicable" and "Skipped" in r.summary


# ---------------- Arabic report wording ------------------------------------------------------
def test_every_module_message_has_arabic():
    """All messages produced by the modules in these scenarios have an Arabic version."""
    from saqrsight.i18n_ar import ar
    results = [
        text_indicators.analyze("URGENT!!! Share this now, explosion in Dubai", "en"),
        text_indicators.analyze("Do not share. Rumours of a lockdown are false. According to NCM, dangerous fog.", "en"),
        text_indicators.analyze("Nice weather today", "en"),
        text_indicators.analyze("", "en"),
    ]
    texts = []
    for r in results:
        texts += [r.summary] + r.limitations + [f.message for f in r.findings]
    for t in ["Reverse image search: no matches.", "3 page(s) contain the same or a near-identical image.",
              "No relevant result was found in the sources searched (wam.ae). This does not show the claim is false.",
              "Location (Dubai): the image alone cannot confirm where it was taken.", "Timed out after 120s."]:
        texts.append(t)
    missing = [t for t in texts if t and ar(t) is None]
    assert missing == []


# ---------------- paragraph-length posts -----------------------------------------------------
PARAGRAPHS = {
    "alarming_en": ("URGENT!!! I just got a message from a friend who works at the port. There was a huge explosion "
                    "near Jebel Ali this morning and people are trapped inside the warehouses. The media is completely "
                    "silent and nobody is reporting it. They don't want you to know how bad it is. Stock up on water and "
                    "food tonight because shortages are coming. Share this with everyone you know before they delete it!",
                    "high"),
    "debunk_en": ("Over the past two days a message has been circulating on WhatsApp claiming that \"Dubai will go into "
                  "total lockdown tomorrow, share this immediately\". Dubai Police confirmed that this is a rumour and "
                  "that there are no plans for any lockdown. Residents are asked not to share unverified messages and to "
                  "follow official channels only. There is no need to panic or to stock up on food.", "none"),
    "advisory_en": ("The National Centre of Meteorology has issued an orange alert for heavy rain across the northern "
                    "emirates from Thursday evening. According to NCM, dangerous driving conditions are expected and "
                    "flooding may occur in low-lying areas. Authorities advise residents to avoid wadis and to stay "
                    "indoors where possible.", "none"),
    "alarming_ar": ("عاجل!! وصلتني رسالة من واحد يشتغل في المستشفى، يقول إن في انفجار كبير صار في جبل علي الصبح والناس "
                    "محاصرين داخل المستودعات. الإعلام ساكت ومحد قاعد يتكلم عن الموضوع، وما يبونكم تعرفون الحقيقة. خزنوا "
                    "ماي وأكل الليلة لأن بيصير نقص حاد. دزوها لكل القروبات قبل لا يمسحونها!", "high"),
    "debunk_ar": ("تداولت بعض الحسابات خلال اليومين الماضيين رسالة تقول \"دبي بتدخل حظر تجول كامل بكرة، انشروها فوراً\". "
                  "وأكدت شرطة دبي أن هذا الخبر شائعة ولا صحة له، ولا توجد أي خطط لحظر التجول. ويُطلب من السكان عدم نشر "
                  "الرسائل غير الموثقة ومتابعة القنوات الرسمية فقط، ولا داعي للهلع أو تخزين المواد الغذائية.", "none"),
    "advisory_ar": ("أصدر المركز الوطني للأرصاد تنبيهاً برتقالياً لهطول أمطار غزيرة على الإمارات الشمالية بدءاً من مساء "
                    "الخميس. وحسب المركز، من المتوقع أن تكون ظروف القيادة خطيرة وقد تحدث فيضانات في المناطق المنخفضة.",
                    "none"),
}


@pytest.mark.parametrize("name", PARAGRAPHS)
def test_paragraph_posts(name):
    text, level = PARAGRAPHS[name]
    r = text_indicators.analyze(text, "")
    assert r.data["indicator_level"] == level, [(m["excerpt"], m["context"]) for m in r.data["matches"]]
    if level == "high":
        assert set(r.data["categories"]) == {"urgency", "fear", "manipulation", "share_pressure"}


def test_negation_scope_and_distrust():
    assert ctx("There is no need to panic or to stock up on food.") == {("fear", "negated")}
    assert ("share_pressure", "active") in ctx("They will not tell you the truth so share this now!")
    assert ("fear", "active") in ctx("The government is hiding the real numbers, people are trapped!")
    assert ctx("According to NCM, dangerous conditions are expected.") == {("fear", "attributed_warning")}
