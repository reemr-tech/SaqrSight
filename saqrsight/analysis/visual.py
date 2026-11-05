"""Possible AI-generated image signal for an image or sampled video frames.

The detector is a pretrained image classifier chosen by eval/eval_visual.py. Its scores are shown
as a *signal*, never as proof. The assessment rules use the signal only when
models/visual_calibration.json records that this exact model was evaluated and lists the decision
threshold chosen on the development split; otherwise the score is reported as unvalidated.

This module does not detect conventional editing (splicing, retouching, cropping). No method for
that has been implemented or evaluated, so the report says so explicitly.
"""
from __future__ import annotations

from ..config import Settings
from ..media import Visual, model_input
from ..schema import COMPLETED, Finding, ModuleResult, not_applicable, not_configured
from .models import ModelUnavailable, image_classifier, load_calibration

MODULE = "media_analysis"
SYNTHETIC_LABELS = ("artificial", "ai", "fake", "generated", "sdxl", "synthetic", "ai_generated")


def synthetic_score(preds: list[dict]) -> float:
    """Probability mass the classifier assigns to its 'AI-generated' label(s)."""
    total = 0.0
    for p in preds:
        label = str(p["label"]).lower().replace("-", "_").replace(" ", "_")
        if any(label == s or label.startswith(s) for s in SYNTHETIC_LABELS):
            total += float(p["score"])
    return min(1.0, total)


def score_images(model_id: str, images) -> list[float]:
    clf = image_classifier(model_id)
    out = clf(list(images), top_k=None)
    if out and isinstance(out[0], dict):
        out = [out]
    return [synthetic_score(p) for p in out]


def analyze(visuals: list[Visual], cfg: Settings) -> ModuleResult:
    model_id = cfg.visual_model
    version = f"ai-image-detector:{model_id}"
    if not visuals:
        return not_applicable(MODULE, version, "No image or video was supplied.")
    if not cfg.enable_models:
        return not_configured(MODULE, version, "Model-based media analysis is switched off on this server.")
    try:
        scores = score_images(model_id, [model_input(v.path) for v in visuals])
    except ModelUnavailable as e:
        return not_configured(MODULE, version, f"The AI-image detector could not be loaded ({e}).")

    cal = load_calibration("visual_calibration.json")
    validated = bool(cal and cal.get("model") == model_id and cal.get("selected"))
    threshold = float(cal["threshold"]) if validated else 0.5
    frames = []
    for v, s in zip(visuals, scores):
        ref = v.public() | {"synthetic_score": round(s, 3), "flagged": s >= threshold}
        frames.append(ref)
    flagged = [f for f in frames if f["flagged"]]
    findings: list[Finding] = []
    what = "image" if visuals[0].ref == "image" else f"{len(visuals)} sampled frames"
    if flagged:
        msg = ("The detector produced a possible AI-generation signal for "
               + ("this image." if what == "image" else f"{len(flagged)} of {len(visuals)} sampled frames.")
               + " This is a signal for review, not proof; detectors make errors on edited, compressed or"
                 " unfamiliar images, and an AI-generated image does not by itself make the caption false.")
        findings.append(Finding(code="possible_synthetic", message=msg, frames=flagged,
                                score=max(f["synthetic_score"] for f in flagged)))
    else:
        findings.append(Finding(
            code="no_synthetic_signal", frames=frames, score=max(scores),
            message=f"The detector did not flag the {what} as AI-generated at the evaluated threshold. "
                    "This does not show the media is authentic or unedited."))
    findings.append(Finding(code="editing_not_assessed",
                            message="Conventional editing or manipulation (splicing, retouching, cropping) "
                                    "was not assessed; no evaluated method is implemented for it."))
    limitations = [
        "Detects possible AI generation only; it does not detect conventional photo editing.",
        "Performance drops on screenshots, heavy compression and generators absent from its training data.",
    ]
    note = ""
    if validated:
        m = cal.get("metrics", {})
        confidence = "validated"
        note = (f"Evaluated on {cal.get('test_size', '?')} held-out images: precision {m.get('precision', '?')}, "
                f"recall {m.get('recall', '?')}, false-positive rate on authentic images {m.get('fpr', '?')}.")
        limitations.append(note)
    else:
        confidence = None
        limitations.append("This model has not been validated for this application; its score is shown "
                           "for information and is not used in the overall assessment.")
    summary = (f"{len(flagged)} of {len(frames)} checked visual(s) produced a possible AI-generation signal."
               if flagged else f"No AI-generation signal on the {what} checked.")
    return ModuleResult(module=MODULE, status=COMPLETED, version=version, findings=findings, summary=summary,
                        score=round(max(scores), 3), confidence=confidence, limitations=limitations,
                        data={"frames": frames, "threshold": threshold, "validated": validated,
                              "validation_note": note})
