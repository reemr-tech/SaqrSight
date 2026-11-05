"""Caption–media consistency.

Encoders: CLIP ViT-B/32 image encoder and a multilingual text encoder distilled into the same
embedding space (sentence-transformers clip-ViT-B-32 / clip-ViT-B-32-multilingual-v1), so Arabic
and English captions can be compared with the image.

Decision: a logistic-regression classifier over joint features of the two embeddings, trained on
the NewsCLIPpings *train* split and with thresholds chosen on its *val* split
(eval/train_consistency.py). VERITE is used only for final evaluation.

What the labels support: NewsCLIPpings provides pristine vs falsified (mismatched) pairs, so the
classifier estimates whether the caption *topic* agrees with the visible content. It cannot
establish that the event happened at the stated place or time, and it is not an out-of-context
detector. Those details are listed as needing external evidence.
"""
from __future__ import annotations

import numpy as np

from ..config import Settings
from ..media import Visual, model_input
from ..schema import COMPLETED, Finding, ModuleResult, not_applicable, not_configured
from .claims import ClaimDetails
from .models import ModelUnavailable, load_calibration, sentence_model

MODULE = "consistency_check"
CLASSIFIER_FILE = "consistency_classifier.json"


def features(img: np.ndarray, txt: np.ndarray) -> np.ndarray:
    """Joint features for L2-normalised embeddings (rows): product, |difference|, cosine."""
    img = img / np.linalg.norm(img, axis=1, keepdims=True)
    txt = txt / np.linalg.norm(txt, axis=1, keepdims=True)
    cos = np.sum(img * txt, axis=1, keepdims=True)
    return np.hstack([img * txt, np.abs(img - txt), cos])


def predict_proba(clf: dict, feats: np.ndarray) -> np.ndarray:
    mean, scale = np.array(clf["mean"]), np.array(clf["scale"])
    z = ((feats - mean) / scale) @ np.array(clf["coef"]) + clf["intercept"]
    return 1.0 / (1.0 + np.exp(-z))


def encode(visuals: list[Visual], caption: str, cfg: Settings) -> tuple[np.ndarray, np.ndarray]:
    img_model = sentence_model(cfg.clip_image_model)
    txt_model = sentence_model(cfg.clip_text_model)
    imgs = img_model.encode([model_input(v.path) for v in visuals], convert_to_numpy=True)
    txt = txt_model.encode([caption], convert_to_numpy=True)
    return imgs, np.repeat(txt, len(visuals), axis=0)


def unverifiable_details(details: ClaimDetails) -> list[str]:
    out = []
    if details.locations:
        out.append("Location (" + ", ".join(details.locations) + "): the image alone cannot confirm where it was taken.")
    if details.has_time:
        out.append("Time (" + ", ".join(details.relative_dates + details.dates)
                   + "): the image alone cannot confirm when it was taken.")
    if details.events:
        out.append("Event (" + ", ".join(details.events) + "): visible content can look consistent with an event "
                   "without showing that this specific event happened.")
    return out


def analyze(caption: str, visuals: list[Visual], details: ClaimDetails, cfg: Settings) -> ModuleResult:
    clf = load_calibration(CLASSIFIER_FILE)
    version = "clip-b32-multilingual+logreg:" + (clf.get("version", "?") if clf else "untrained")
    if not caption.strip() or not visuals:
        return not_applicable(MODULE, version, "Both a caption and an image or video are needed.")
    if not cfg.enable_models:
        return not_configured(MODULE, version, "Model-based consistency checking is switched off on this server.")
    if not clf:
        return not_configured(MODULE, version, "The consistency classifier has not been trained "
                                               "(run eval/train_consistency.py).")
    try:
        imgs, txt = encode(visuals, caption, cfg)
    except ModelUnavailable as e:
        return not_configured(MODULE, version, f"The image/text encoders could not be loaded ({e}).")
    probs = predict_proba(clf, features(imgs, txt))
    hi, lo = clf["threshold_agree"], clf["threshold_disagree"]
    frames = [v.public() | {"agreement_score": round(float(p), 3)} for v, p in zip(visuals, probs)]
    best = float(probs.max())
    # A video caption may describe any part of the clip: agreement if any sampled frame agrees,
    # low agreement only if every sampled frame disagrees.
    if best >= hi:
        decision = "agree"
    elif best <= lo:
        decision = "disagree"
    else:
        decision = "inconclusive"
    findings: list[Finding] = []
    if decision == "agree":
        findings.append(Finding(code="topic_agreement", score=round(best, 3), frames=frames,
                                message="The visible content appears consistent with what the caption describes."))
    elif decision == "disagree":
        findings.append(Finding(code="low_agreement", score=round(best, 3), frames=frames,
                                message="The visible content does not appear to match what the caption describes. "
                                        "This may indicate miscaptioning; compare the media with the claim."))
    else:
        findings.append(Finding(code="inconclusive_agreement", score=round(best, 3), frames=frames,
                                message="The model could not determine whether the caption and media agree."))
    pending = unverifiable_details(details)
    if pending:
        findings.append(Finding(code="needs_external_evidence", excerpts=pending,
                                message="These claim details cannot be assessed from the visible content."))
    long_caption = len(caption) > 300
    m = clf.get("metrics", {})
    limitations = [
        "Trained on English news image–caption pairs (NewsCLIPpings); Arabic captions rely on a multilingual "
        "text encoder aligned to CLIP and were not part of training.",
        "Estimates topic agreement only. It cannot confirm date, location, or that the image is from the "
        "described event, and does not detect out-of-context reuse on its own.",
        f"NewsCLIPpings test accuracy {m.get('accuracy', '?')}; see README for independent VERITE results.",
    ]
    if long_caption:
        limitations.append("Long caption: only the first part was encoded by the text model.")
    return ModuleResult(
        module=MODULE, status=COMPLETED, version=version, findings=findings,
        summary={"agree": "Caption and visible content appear consistent in topic.",
                 "disagree": "Caption and visible content appear not to match.",
                 "inconclusive": "Agreement between caption and visible content is inconclusive."}[decision],
        score=round(best, 3), confidence="validated" if clf.get("validated") else None,
        limitations=limitations,
        data={"decision": decision, "frames": frames, "thresholds": {"agree": hi, "disagree": lo},
              "unverifiable": pending,
              "validation_note": clf.get("validation_note", f"NewsCLIPpings test accuracy {m.get('accuracy', '?')}.")})
