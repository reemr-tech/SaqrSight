"""Run the applicable checks for a submission, saving each module result as soon as it is available.

A slow, failing or timed-out module never discards results already obtained: the report is
rebuilt and saved after every module, and the final assessment is applied once all have finished.
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import time

from . import assessment, report
from .analysis import claims, consistency, text_indicators, visual
from .config import Settings
from .evidence import official_sources, reverse_image
from .media import MediaInfo
from .schema import FAILED, ModuleResult
from .storage import Store

log = logging.getLogger("saqrsight")
_executor = cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="saqr-report")
_module_pool = cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="saqr-module")
VERSION = "0.2.0"


def _run(name: str, version: str, fn, timeout: float) -> dict:
    start = time.monotonic()
    fut = _module_pool.submit(fn)
    try:
        res: ModuleResult = fut.result(timeout=timeout)
    except cf.TimeoutError:
        res = ModuleResult(module=name, status=FAILED, version=version,
                           summary="This check did not finish in time.", error=f"Timed out after {timeout:.0f}s.")
    except Exception as e:  # never let one module break the report; never log user content
        log.warning("module %s failed: %s", name, type(e).__name__)
        res = ModuleResult(module=name, status=FAILED, version=version,
                           summary="This check could not be completed.", error=type(e).__name__)
    res.duration_ms = int((time.monotonic() - start) * 1000)
    return res.to_dict()


def finalize(p: dict) -> dict:
    details = claims.ClaimDetails(**{k: v for k, v in p["claim_details"].items() if k != "searchable"})
    a = assessment.assess(p["modules"], details, bool(p["caption"]), bool(p.get("media")))
    p["assessment"] = a
    p["priority"] = a["priority"]
    p["recommended_actions"] = assessment.recommended_actions(p["modules"], details, a)
    p["status"] = "complete"
    p["sections"] = report.build_sections(p)
    return p


def run(store: Store, cfg: Settings, p: dict, media: MediaInfo | None) -> dict:
    caption, consent = p["caption"], p["consent_external"]
    details = claims.extract(caption) if caption else claims.ClaimDetails()
    visuals = media.visuals if media else []
    t = cfg.module_timeout
    plan = [
        ("text_analysis", text_indicators.VERSION, lambda: text_indicators.analyze(caption, p["language"])),
        ("media_analysis", "ai-image-detector", lambda: visual.analyze(visuals, cfg)),
        ("consistency_check", "clip-consistency", lambda: consistency.analyze(caption, visuals, details, cfg)),
        ("reverse_image_search", reverse_image.VERSION,
         lambda: reverse_image.analyze(visuals, caption, consent, cfg)),
        ("official_sources", "official-sources-v1",
         lambda: official_sources.analyze(caption, details, consent, cfg)),
    ]
    for name, version, fn in plan:
        result = _run(name, version, fn, t)
        p["modules"][name] = result
        store.save_module(p["id"], result)
        p["sections"] = report.build_sections(p)
        store.update_payload(p)
    return finalize(p)


def submit(store: Store, cfg: Settings, p: dict, media: MediaInfo | None) -> None:
    def job():
        try:
            final = run(store, cfg, p, media)
        except Exception as e:
            log.error("report pipeline failed: %s", type(e).__name__)
            final = finalize(p)   # assess with whatever was collected
        if store.get_row(p["id"]) is not None:   # the user may have deleted it meanwhile
            store.update_payload(final)
    _executor.submit(job)
