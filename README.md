# SaqrSight · صقر

SaqrSight helps people assess potentially misleading social-media claims about the United Arab
Emirates. You submit Arabic or English text, an image or a short video, or text with media. The app
runs a set of checks and produces an **initial assessment** report. The report explains what was
checked, what was found, what remains uncertain, and what you can verify next.

It is designed for members of the public. Its review-priority and evidence sections are meant to
help journalists, fact-checkers and media-monitoring teams triage claims.

> SaqrSight does not decide whether a claim is true. A caption that matches an image does not show
> the event happened at the stated time or place. Urgent wording does not make a claim false. An
> AI-generated image does not by itself make the accompanying claim false. The rules, interface and
> exports keep these distinctions.

## Contents
1. [Quick start](#quick-start)
2. [Feature status](#feature-status)
3. [How a submission is processed](#how-a-submission-is-processed)
4. [Assessment rules](#assessment-rules)
5. [Optional evidence providers](#optional-evidence-providers)
6. [Tests](#tests)
7. [Evaluation results](#evaluation-results)
8. [Reproducing the evaluation](#reproducing-the-evaluation)
9. [Demo script](#demo-script)
10. [Storage, privacy and security](#storage-privacy-and-security)
11. [Project structure and API](#project-structure-and-api)
12. [Limitations](#limitations)
13. [SGP1 → SGP2](#sgp1--sgp2)

## Quick start

Requires Python 3.11+ (tested with 3.13 on macOS, Apple silicon).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-ml.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. On first use the app downloads about 1.6 GB of models from Hugging
Face (the CLIP image encoder, the multilingual text encoder and the AI-image detector). After that
it runs offline.

* **Without the ML stack:** install `requirements.txt` only and set `SAQRSIGHT_ENABLE_MODELS=0`.
  The model-based checks then show as **Not configured** in every report.
* `requirements-lock.txt` is the full `pip freeze` of the tested environment.
* The database is created automatically at `data/saqrsight.sqlite3`; there is no separate setup
  step. Set `SAQRSIGHT_DATA_DIR` to store it elsewhere.
* All settings are environment variables; see [`.env.example`](.env.example).

## Feature status

| Feature | Status | Notes |
|---|---|---|
| Text submission with validation; image and video upload | **Implemented** (text) · **off in SGP1** (image/video: shown as "Coming in Senior Project 2", the server refuses uploads; `SAQRSIGHT_MEDIA_ENABLED=1` turns the prototype on) | Files are decoded to validate them (the extension is not trusted). Limits are configurable and shown before upload. |
| Report history, reopen, HTML and JSON export, delete | **Implemented** | Carried over from SGP1. Deleting a report removes its database rows and stored media. |
| SGP1 sample reports | **Implemented** | Still open, labelled **SGP1 SAMPLE REPORT**, and are never presented as analysis. |
| Language detection with manual override (Arabic / English / mixed) | **Implemented** | A script-ratio heuristic, not a trained language-ID model. |
| Bilingual interface and report labels, RTL layout | **Implemented** | Module finding text is in English; headings, verdicts, priority reasons and actions are in both languages. |
| Text language indicators (urgency, fear, manipulation, share pressure) | **Implemented** | Transparent lexicon (v1.1, incl. Gulf dialect) with negation, quotation, debunk and official-warning handling; compared with a TF-IDF + logistic regression model. |
| AI-generated image signal | **Implemented** | See [visual results](#ai-generated-image-signal) for whether it is used in verdicts. |
| Conventional editing / manipulation detection | **Planned** | Not implemented. Reports say explicitly that editing was not assessed. |
| Caption–media consistency | **Implemented** | CLIP ViT-B/32 with a multilingual text encoder and a classifier trained on NewsCLIPpings. |
| Assessment rules, review priority, issue types, recommended actions | **Implemented** | See [Assessment rules](#assessment-rules). |
| Reverse image search (Google Cloud Vision Web Detection) | **Optional** | Needs an API key and per-report user consent. Code and tests are done; it has not been run against the live service. |
| Official UAE source retrieval (Brave Search or Google Programmable Search) | **Optional** | Needs an API key and per-report user consent. Code and tests are done; it has not been run against the live service. |
| Short video (frame sampling with timestamps) | **Prototype – off in SGP1** | MP4/MOV/WebM up to 60 s. Only the sampled frames are stored. |
| Trained multilingual text-indicator model | **Planned** | Only the baseline exists. A model should be compared against it on labelled data. |
| Direct X / Telegram post links | **Planned** | Not built. Supported API access has not been confirmed. Manual caption and media entry stay available. |
| Accounts: sign up, log in, log out; each user sees only their own reports | **Implemented** | PBKDF2 password hashing, HttpOnly session cookie, login throttling (see [Security](#storage-privacy-and-security)). HTTPS is still needed for a public deployment. |
| Screens: landing, log in, sign up, dashboard, new assessment, report, search reports, models & roadmap | **Implemented** | All outputs are generated by working components; nothing on these screens is illustrative. |
| 3-level panic label (none / mild / strong) | **Implemented** | Derived by rule from the text indicators; added to the labelling kit and evaluation for the planned AraBERT dataset. |
| AraBERT v0.2, XLM-RoBERTa base, Gemini (`gemini-3-flash-preview`) | **Planned (SGP2)** | Listed with exact IDs, sizes, licences and roles on the in-app *Models & roadmap* page (`static/models-data.js`). |
| Reviewed UAE caption–image test set | **Planned** | A template is in `eval/data/uae_consistency_template.csv`. It needs images with usage rights and two reviewers. |

## How a submission is processed

1. **Validate.** Text must be 10,000 characters or fewer. Images must be JPEG, PNG or WebP, at most
   10 MB, at most 20 MP, and at least 32 px on each side. Videos must be MP4, MOV or WebM, at most
   50 MB and at most 60 s. File type is detected from magic bytes and confirmed by decoding.
   Animated images and decompression bombs are rejected.
2. **Preprocess.** The original caption is kept for display. A separate normalised copy is used for
   analysis: diacritics and tatweel are removed, Arabic letter forms and Arabic digits are unified,
   and text is lower-cased. Images are re-encoded to JPEG, which strips EXIF and GPS metadata.
   For videos, `SAQRSIGHT_VIDEO_FRAMES` frames (default 5) are sampled at evenly spaced timestamps;
   only those frames are stored, and the video file is discarded.
3. **Analyse.** Each check runs in the background with a timeout. Every check returns the shared
   result format in `saqrsight/schema.py`:
   * module name and status: `completed`, `not_applicable`, `not_configured` or `failed`;
   * findings, with caption excerpts, frame references and sources;
   * score and validated confidence where they apply;
   * model or rule version, and limitations.

   Each result is saved as soon as it arrives. A failed or slow check never discards the others.
4. **Assess.** The documented rules turn the recorded findings into a verdict, a review priority,
   issue types and recommended actions.
5. **Report.** The browser polls the report until it is complete. The report can be downloaded as
   HTML or JSON, reopened from history, or deleted.

Which checks run for each input:

| Input | Checks |
|---|---|
| Text only | Text indicators. Official sources run if configured, consented to, and the caption names an event plus a place or time. |
| Image only | AI-image signal. Reverse image search runs if configured and consented to. Consistency is *not applicable*. |
| Text + image | All of the above, plus caption–image consistency. |
| Video (± caption) | AI-image signal on each sampled frame. Text and consistency checks run only if a caption is supplied. |

## Assessment rules

The rules are in [`saqrsight/assessment.py`](saqrsight/assessment.py) (`rules-1.1`). Model scores
are never averaged together.

| Verdict | Rule |
|---|---|
| **Potentially misleading** (A1) | A meaningful contradiction was found, and the report explains it and cites the evidence. Any one of: (a) an official source covering the same event and place denies it; (b) the same image appears on pages that indicate a different time or place; (c) the validated consistency classifier decisively finds that the caption does not match the visible content. |
| **Insufficient evidence** (A2) | No contradiction, but there is a validated possible-AI-generation signal. The media's origin must be established first. |
| **Apparently consistent** (A3) | No contradiction, and one of: an official source reports the same event, place and time; or there is topic agreement **and** the caption makes no place or time claim. The report lists which details remain unverified. |
| **Insufficient evidence** (A4) | Everything else. This includes topic agreement for a caption whose key claim is a place or date (see the VERITE results below for why). |

The following can never produce "potentially misleading" on their own: urgent or alarming wording,
an AI-generation signal, a failed or unconfigured search, or "no results".

**Review priority** is set independently of the verdict. It adds up points, and every point comes
with a stated reason:

* +2: a public-safety event (fire, explosion, attack, flood, outbreak, collapse, earthquake,
  shortage, closure) that no official source has confirmed;
* +2 for a "high" language-indicator level, +1 for "moderate";
* +1: explicit pressure to share;
* +2: the verdict is potentially misleading;
* +1: a validated AI-generation signal;
* +1: a specific UAE place combined with "now", "today" or "yesterday".

A total of 4 or more is **high**, 2–3 is **medium**, 0–1 is **low**. For example, an unverified
public-safety rumour gets high priority while its verdict stays *insufficient evidence*.

**Confidence** is shown only for individual validated model findings, with their measured metrics.
No percentage is ever shown for the truth of a claim.

**Plain-language report.** Every report opens with an **"In plain words / باختصار"** summary written
for the specific claim. For example: "The post is about a fire in Dubai Marina, said to be happening
right now… Our advice: check official channels before you share it."

* It is assembled by fixed rules in [`saqrsight/plain.py`](saqrsight/plain.py) from the recorded
  findings only. No language model writes it, so it cannot add anything the checks did not find.
* A **"How to read this report"** guide explains the three verdicts, review priority and issue type.
* Reader-facing status names are *Done*, *Not needed*, *Not available* and *Could not finish*.
  Internally they remain completed, not applicable, not configured and failed.
* Model scores, thresholds and rule codes are kept in the **Technical details** part of the appendix.

The report can be downloaded in English, Arabic (fully right-to-left) or both side by side. The user
chooses the language before the download starts.

## Optional evidence providers

Both providers are off by default. The core assessment works without any API keys. When a key is
configured, the New Assessment form explains exactly what would be sent, and the user must tick a
box for each report. Without consent the check shows as *skipped*.

| Check | Provider and variables | What is sent |
|---|---|---|
| Reverse image search | Google Cloud Vision `WEB_DETECTION`: `GOOGLE_VISION_API_KEY` | The stored, metadata-stripped image, or up to `SAQRSIGHT_MAX_REVERSE_FRAMES` (default 2) video frames. |
| Official sources | `SAQRSIGHT_SEARCH_PROVIDER=brave` with `BRAVE_SEARCH_API_KEY`, or `google_cse` with `GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_CX` | Only the extracted event, place and date keywords, in English and Arabic. Never the caption itself or media. |

Check the provider's terms of use and pricing before enabling either one. Neither has been run
against the live service in this project; see the retrieval evaluation below. Timeouts
(`SAQRSIGHT_HTTP_TIMEOUT`) and query limits (`SAQRSIGHT_MAX_SEARCH_QUERIES`) are configurable.

**Reverse image search** reports each result with its match type:

* *exact or near-exact*: the same photo;
* *partial*: a crop or edit of the same photo;
* *visually similar only*: explicitly not evidence that this photo appeared elsewhere.

Publication dates are read from each page's own metadata, when the page declares one. A page that
predates the claimed time, or names a different place, is flagged as a **possible context
discrepancy**. The earliest result is never called the original.

**Official sources** search a configurable domain list (`SAQRSIGHT_OFFICIAL_DOMAINS`). The default
covers WAM, u.ae, Dubai and Abu Dhabi media offices, NCEMA, MOI, Dubai Police, Abu Dhabi Police,
NCM and MOHAP. Results from other domains are discarded. Each result is checked for the same
**event, place and time** and labelled:

* *supporting*;
* *contradicting*: the source denies the claim or calls it a rumour;
* *insufficient*: for example a different date, a missing date, or a different place.

The report keeps four outcomes separate: relevant evidence, results that were not relevant, no
relevant result "in the sources searched", and search failure or no provider configured. Sources,
excerpts, dates and links are only ever taken from provider responses.

## Tests

```bash
.venv/bin/python -m pytest -q
```

There are 42 tests, which run in about 3 seconds. They need no network or models: the models are
switched off and the providers are mocked. They cover:

* English, Arabic and mixed text, the language override, image-only, text + image, and video
  (frame timestamps; only the frames are stored);
* invalid, spoofed, empty, oversized, too-small and too-long uploads;
* HTML escaping, the bilingual exports, reopening after restart, and deletion of all rows and media;
* legacy SGP1 reports, retention purge, a crashing module, and a module timeout;
* text contexts (negation, quotation, debunk, attributed warnings) and exact Arabic excerpts;
* every assessment rule, including "urgent wording alone", "synthetic alone" and "failed search";
* provider handling of discrepancies, similar-only matches, no matches, timeouts, HTTP errors,
  off-list domains, missing dates and denials.

## Evaluation results

All numbers below were measured with the scripts in `eval/`. The raw outputs are in
`eval/results/*.json`. Training, threshold selection and final evaluation used separate data.

### Text indicators (`text-lexicon-1.1`) – main Senior Project 1 contribution

Full tables, per-category results and every remaining error are in
[`eval/results/text_report.md`](eval/results/text_report.md) (generated by `eval/make_text_report.py`).

**Method.** A transparent bilingual word list ([`lexicon.py`](saqrsight/analysis/lexicon.py)) with
context rules for negation, quotation, debunks and official warnings. Version 1.1 adds Gulf-dialect
and everyday-English forms, learned **only** from a development set
(`eval/data/text_indicators_dev_dialect.jsonl`).

**Fair test.** A new test set of 60 posts (30 English, 30 Arabic, many in Gulf dialect) was written
and frozen in git (commit `7ed7538`) **before** version 1.1 was made. Version 1.0 was scored on it
first.

| Blind test v2 | English P / R / F1 | Arabic P / R / F1 |
|---|---|---|
| Lexicon 1.0 (before) | 1.00 / 0.40 / 0.57 | 1.00 / 0.24 / 0.39 |
| **Lexicon 1.1 (current)** | **1.00 / 0.68 / 0.81** | **1.00 / 0.56 / 0.72** |
| TF-IDF + logistic regression (trained on the 90 development posts) | 1.00 / 0.52 / 0.68 | 1.00 / 0.48 / 0.65 |

* **No false alarms.** None of the 32 posts that must not be flagged (negation, quotation,
  debunks, official warnings, neutral news) was flagged, by either method.
* **Weakest category: fear/alarm** (F1 0.40 for the rules). On fear only, the machine-learning
  model did better (0.55), because fear is phrased in very varied ways. A combined approach is
  planned for Senior Project 2.
* **Paragraph-length posts** are analysed sentence by sentence (negation, quotation, debunk and
  official-warning context are judged per sentence), and are covered by regression tests in
  `tests/test_modules.py`. Version 1.1.1 fixed two context errors that only showed up in longer
  posts: negation across "or"/"أو" lists ("no need to panic or to stock up"), and a sentence that
  distrusts an authority ("the government is hiding…") no longer counts as an official warning.
  Neither changed the evaluation numbers above, because the test sets contain only short posts.
  Long real posts should be part of the real-data collection.
* **Rules beat machine learning overall.** With so little training data, the transparent rules
  found more indicators. They also show the exact words behind each finding.
* **Caveats.**
  * All posts are synthetic, written by the developer and labelled by one person. Each category
    has few examples per language, so small differences are not meaningful.
  * The older test set (v1) is no longer blind for version 1.1; its numbers are in the full report
    for reference only.

**Next step: real posts.** [`eval/annotation/GUIDELINES.md`](eval/annotation/GUIDELINES.md) explains
how to collect and anonymise 150–300 real public posts and have two people label them. Two scripts
then do the rest:
* `agreement.py` measures how much the two labellers agree (Cohen's kappa);
* `import_real.py` loads the agreed labels as a development half and a held-out test half, which the
  evaluation scripts and report pick up automatically.

### Caption–media consistency

**Training and tuning on NewsCLIPpings.** The model was trained on the merged_balanced train split
(71,072 pairs) using the authors' precomputed CLIP ViT-B/32 embeddings. Regularisation and the two
decision thresholds (agree ≥ 0.81, disagree ≤ 0.23) were chosen on val so that each decisive label
reaches at least 0.85 precision.

| NewsCLIPpings test (n = 7,264) | Accuracy | AUC | Match P/R/F1 | Mismatch P/R/F1 |
|---|---|---|---|---|
| Logistic regression | 0.680 | 0.753 | 0.667 / 0.718 / 0.692 | 0.695 / 0.642 / 0.667 |

With the abstaining thresholds: "agree" precision 0.895, "disagree" precision 0.860, and 21.7%
of pairs get a decisive label. The rest are reported as *inconclusive*.

**Independent evaluation on VERITE.** VERITE was never used for training or tuning. Images were
fetched from the published URLs; 691 of 1,000 pairs were usable (223 true, 223 miscaptioned,
245 out-of-context).

| VERITE | App encoder (multilingual) | Training encoder (OpenAI CLIP text) |
|---|---|---|
| AUC, true vs (miscaptioned + out-of-context) | 0.617 | 0.660 |
| AUC, true vs miscaptioned | 0.537 | 0.568 |
| AUC, true vs out-of-context | 0.689 | 0.744 |
| "disagree" precision / share of pairs decisive | 0.833 / 0.307 | 0.900 / 0.323 |
| "agree" precision | 0.430 | 0.491 |
| Miscaptioned pairs labelled "agree" (wrongly supported) | **29.1%** | 27.4% |
| Out-of-context pairs labelled "agree" | 10.2% | 9.0% |
| True pairs labelled "disagree" | 4.0% | 2.7% |

What this means:

* The model mainly detects **topic mismatch**, which shows up in the out-of-context pairs.
* It is close to chance at telling a true caption from a **miscaptioned** one, where a genuine
  photo is given the wrong date, place or event. That is the case this project is most concerned
  with.
* A decisive "disagree" is reasonably reliable, and is the only consistency output that can make
  a claim *potentially misleading*.
* "Agree" is not reliable for claims about place or time. After seeing these results, rule A3 was
  changed (`rules-1.0` → `rules-1.1`): topic agreement cannot make a caption with a place or time
  claim "apparently consistent". The verdict-level VERITE figures in
  `eval/results/consistency_verite.json` therefore do not independently test that rule. The model
  and thresholds were not changed.
* **Verdict level** (app encoder, `rules-1.1`): **14.8%** of miscaptioned pairs and 1.6% of
  out-of-context pairs still end up *apparently consistent*, against 11.2% of true pairs. The
  share of miscaptioned pairs with "agree" was 29.1%, so the place/time rule removes about half.
  The rest remain because the claim extractor only recognises UAE places, and most VERITE captions
  name places elsewhere. Of the remaining verdicts, 4.0% of true pairs are wrongly *potentially
  misleading*, against 4.5% of miscaptioned and 14.3% of out-of-context pairs.
* Replacing the OpenAI text encoder with the multilingual one (needed for Arabic) costs about
  0.04 AUC on English. Arabic captions are unevaluated until the reviewed UAE set exists.
* NewsCLIPpings and VERITE support match vs. mismatch (and, for VERITE, a 3-way label). Nothing in
  training teaches the model about dates or places, so the app does not claim to detect
  out-of-context reuse on its own; that comes from reverse image search.

### AI-generated image signal

> **Current default (SGP1):** the configured detector is now
> `NYUAD-ComNets/NYUAD_AI-generated_images_detector` (ViT, 85.8M parameters, Apache-2.0; classes
> `dalle` / `real` / `sd`, scored as 1 − P(real)), as named in the project plan. **It has not been
> evaluated yet.** SaqrSight therefore shows its result as *not validated* and never uses it in a
> verdict. The evaluation below (`haywoodsloan/ai-image-detector-deploy`) was the SGP1 candidate
> study. NYUAD has been added to `eval/eval_visual.py` so it can be evaluated the same way in
> Senior Project 2.

**Data.** ELSA_D3 validation shard 0. Each real LAION photo (fetched from its URL; 285 of 437
were reachable) is paired with one image generated from that photo's own caption. The generators
rotate between SD 1.4, SD 2.1, SDXL and DeepFloyd IF.

**Controls.**
* The dev/test split is by pair (142 / 143 pairs), so a photo and its generated twin never cross
  splits.
* Both classes are re-encoded to the same JPEG quality, so file format cannot separate them.
* The threshold was chosen on dev, with false-positive rate ≤ 0.10. The test split was scored
  once per condition.

**Acceptance rule**, fixed before the run: standard-test precision ≥ 0.80 and FPR ≤ 0.15.

| Candidate | Threshold | Standard P / R / FPR | JPEG q50 P / R / FPR | Half-size P / R / FPR | Screenshot P / R / FPR | Accepted |
|---|---|---|---|---|---|---|
| haywoodsloan/ai-image-detector-deploy | 0.14 | 0.81 / 0.61 / 0.14 | 0.85 / 0.43 / 0.08 | 0.82 / 0.54 / 0.12 | 0.75 / 0.53 / **0.18** | **Yes (used)** |
| Organika/sdxl-detector | 0.96 | 0.85 / 0.50 / 0.09 | 0.79 / 0.36 / 0.10 | 0.87 / 0.23 / 0.04 | 0.84 / 0.22 / 0.04 | Passed, not selected (lower dev F1) |
| Ateeqq/ai-vs-human-image-detector | 0.50* | 0.59 / 0.85 / 0.60 | 0.58 / 0.68 / 0.49 | 0.58 / 0.78 / 0.56 | 0.52 / 0.95 / 0.88 | No: flags most authentic photos |

\*No threshold reached FPR ≤ 0.10 on dev, so the default 0.5 was used.

Two candidates passed. The rule then ranks accepted models by **dev F1** (never test results), and
haywoodsloan's is higher. Organika is the more conservative alternative: it has fewer false
positives but catches only about half of generated images, and far fewer after resizing or as a
screenshot. Set it with `SAQRSIGHT_VISUAL_MODEL`. The signal is treated as validated only for the
model named in `models/visual_calibration.json`.

**Selected model's recall by generator** (standard test): SD 1.4 0.56, SD 2.1 0.65, SDXL 0.61,
DeepFloyd IF 0.61.

**What this means for reports:**
* The signal misses about 4 in 10 generated images.
* About 1 in 7 authentic photos is wrongly flagged, rising to about 1 in 5 for screenshots.
* That is why a signal never makes a claim "potentially misleading". It only moves the verdict to
  *insufficient evidence* (rule A2) and adds one point of review priority.
* Recompression and resizing lower recall. Screenshots raise false positives, and every
  screenshot report carries this caveat.

**Caveats.**
* Each test class has 143 images, so these figures carry roughly ±0.05–0.08 uncertainty.
* The selected model's training data is not documented. It may include LAION or ELSA-like
  images, which would inflate these results.
* Newer generators (for example Midjourney v6, DALL·E 3, FLUX) were not in the evaluation set.

### Evidence retrieval

* **Measured.** The relevance and stance judgement was run offline on 20 hand-labelled claim/result
  pairs in Arabic and English (`eval/data/retrieval_judgements.jsonl`). The cases are same event,
  place and time; older coverage; different place; missing date; and denials.
  * First run: accuracy **0.95**. The one error exposed a bug: explicit claim dates such as
    "3 November 2026" were never parsed.
  * After fixing it: 1.00. The set is small and was written by the developer, so treat this as a
    logic check, not a performance estimate.
* **Not measured.** Live retrieval quality, meaning how often the top 5 results contain the earlier
  appearance of an image or a relevant official source. No provider keys were available. Running
  `eval/eval_retrieval.py --live` with a labelled `eval/data/retrieval_live.jsonl` produces hit@5.
  Until that is done, no retrieval-quality figure should be quoted.

### Complete report

The example reports in `samples/example_reports/` were generated from the sample inputs by the
real pipeline. Each one was checked so that the verdict follows from the recorded module outputs
and the rule cited. Not yet done:

* a user study of whether people understand the recommended actions;
* the with/without-retrieval comparison on reviewed UAE examples, which needs provider keys and
  the reviewed set.

## Reproducing the evaluation

Downloaded datasets go in `external/`, which is git-ignored and not redistributed. Pickled
embeddings are loaded with an allow-list unpickler (`eval/safe_pickle.py`), so a tampered file
cannot execute code.

```bash
# Text indicators (no downloads): rules, machine-learning comparison, report tables
.venv/bin/python -I eval/eval_text.py
.venv/bin/python -I eval/eval_text_ml.py
.venv/bin/python -I eval/make_text_report.py

# NewsCLIPpings: data/merged_balanced/*.json and embeddings/clip_{image,text}_embeddings/*.pkl
# from https://huggingface.co/g-luo/news-clippings (Apache-2.0), about 2.2 GB, into external/newsclippings/
.venv/bin/python -I eval/train_consistency.py external/newsclippings

# VERITE: VERITE.csv and VERITE_articles.csv from github.com/stevejpapad/image-text-verification (research use)
.venv/bin/python -I eval/eval_consistency_verite.py external/verite

# ELSA_D3 validation shard 0 (elsaEU/ELSA_D3), about 490 MB, into external/elsa/val0.parquet
.venv/bin/python -I eval/eval_visual.py external/elsa/val0.parquet

# Retrieval judgement (offline), plus --live with provider keys and a labelled live file
.venv/bin/python -I eval/eval_retrieval.py

# Regenerate the example reports
.venv/bin/python -I scripts/make_examples.py
```

**Datasets and permissions**

* **NewsCLIPpings** (Luo et al., 2021). Annotations and embeddings are Apache-2.0. The raw
  VisualNews images need an access request and were not used. Mirrors that redistribute those
  images without the agreement were deliberately avoided.
* **VERITE** (Papadopoulos et al., 2024). Research use only. The images come from the
  authors' published URLs; 309 pairs were unreachable. The gated Hugging Face copy of the images
  needs an institutional email address.
* **ELSA_D3.** Real LAION images are fetched from their URLs; the generated images are from the
  dataset. Research use.

## Demo script

1. Start the app (Quick start) and open http://127.0.0.1:8000. The falcon home screen shows the
   upload limits and which checks this server has available.
2. **Arabic, text only.** Click *Try an example caption* after switching to العربية (top right).
   Submit. The report is right-to-left and quotes the exact Arabic trigger phrases. The verdict is
   *insufficient evidence*, but review priority is *high*, with reasons.
3. **Caption + image.** Attach `samples/demo_smoke_skyline.jpg` with "Huge fire at Dubai Marina
   right now". The consistency check runs, and the report explains that the place and time cannot
   be established from the image.
4. **Mismatch.** Attach the same image with "Camels racing in the desert near Al Ain". Compare the
   consistency finding with step 3.
5. **Video.** Attach `samples/demo_pan.mp4`. The report lists the 5 timestamps analysed and states
   that the findings apply only to those frames.
6. **Exports and history.** Click *Download HTML report*; a window asks for the report language
   (English, العربية — fully right-to-left — or both side by side) and then downloads it. Download
   the JSON too, open *Saved reports*, reopen a report, then delete it and confirm it is gone.
   The same choice is available directly as `/api/reports/{id}/download?format=html&lang=en|ar|both`.
7. **Optional.** Set a provider key, restart, tick the consent box and submit. Then show the
   difference with the box unticked.

Pre-generated outputs of these inputs are in `samples/example_reports/`.

## Storage, privacy and security

* **What is stored.** SQLite (`data/saqrsight.sqlite3`) holds six tables:
  * `reports`: the full report JSON, status and owner;
  * `submissions`: caption, language, media metadata, consent flag;
  * `module_results`: each module's output;
  * `sources`: every cited external URL;
  * `users`: name, email, password hash;
  * `sessions`: hashed login tokens.
* **Media files.** These are kept outside the web root in `data/media/<report-id>/`, under
  internal file names (`image.jpg`, `frame-N.jpg`). They are served only through the report API.
* **Deletion.** Deleting a report removes its rows from all four tables and its media folder;
  tests verify this. This is not forensic erasure of disk blocks or backups.
* **Retention.** Reports older than `SAQRSIGHT_RETENTION_DAYS` (default 90) are purged at
  startup. Setting it to 0 keeps reports until you delete them.
* **Logs.** Captions, media and API keys are never logged. Module errors record only the exception
  type. HTTP client loggers are silenced because request URLs can carry keys. `.env`, `data/` and
  `external/` are git-ignored.
* **Accounts.** Users sign up with a name, email and password (at least 8 characters).
  * Passwords are never stored. Each is hashed with PBKDF2-HMAC-SHA256 (310,000 iterations,
    random salt per user), in [`saqrsight/auth.py`](saqrsight/auth.py).
  * The login session is a random 256-bit token in an **HttpOnly, SameSite=Lax** cookie, so page
    scripts can't read it and other sites can't send it. The database stores only a SHA-256 hash of
    the token.
  * After 5 wrong passwords for an email, further attempts are refused for 5 minutes.
* **Per-user reports.** Every report belongs to one account. Listing, opening, downloading and
  deleting only work on your own reports; someone else's report answers "not found", exactly like
  a report that doesn't exist (tests check this).
  * Reports saved before accounts existed are **adopted by the first account created**.
* **Still needed for a public deployment:** HTTPS (then set `SAQRSIGHT_SECURE_COOKIES=1`),
  password reset by email, and rate and body-size limits at the proxy. Until then, keep the server
  bound to `127.0.0.1`.

## Project structure and API

```
app.py                      FastAPI routes
saqrsight/config.py         settings, limits, official domain list
saqrsight/schema.py         shared ModuleResult / Finding format and statuses
saqrsight/media.py          upload validation, image re-encoding, video frame sampling
saqrsight/textutil.py       language detection, normalisation with offset map
saqrsight/analysis/         text_indicators (+lexicon), claims, visual, consistency, models
saqrsight/evidence/         reverse_image, official_sources
saqrsight/assessment.py     documented verdict / priority / action rules
saqrsight/report.py         report sections and HTML export
saqrsight/pipeline.py       background execution, timeouts, incremental saving
saqrsight/storage.py        SQLite schema, migrations, deletion, retention
saqrsight/auth.py           password hashing, sessions, login throttling
static/                     landing, log in, sign up, dashboard, new assessment, report, search, models (EN/AR, RTL)
models/                     trained consistency classifier and visual calibration (JSON)
eval/                       evaluation scripts, labelled data, results
samples/                    demo inputs and example reports
tests/                      pytest suite
```

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/signup`, `/api/auth/login`, `/api/auth/logout` | Accounts (JSON body: `name`, `email`, `password`) |
| GET | `/api/auth/me` | The signed-in user, or 401 |
| GET | `/api/config` | Limits, available checks, and what external checks would send |
| GET | `/api/dashboard` | Counts for the dashboard: verdicts, priorities, panic levels, languages, indicator categories, recent reports |
| POST | `/api/reports` | Form fields `caption`, `language` (`auto`/`ar`/`en`/`mixed`), `allow_external`, `media` (or SGP1's `image`). Returns 202 with `status: processing`. |
| GET | `/api/reports?q=&verdict=&priority=&language=&panic=` | Search your reports, newest first (up to 100). Text search ignores Arabic letter variants (أ/ا, ة/ه, ى/ي) |
| GET | `/api/reports/{id}` | The report; poll until `status` is `complete` |
| GET | `/api/reports/{id}/media/{ref}` | `image` or `frame-N` |
| GET | `/api/reports/{id}/download?format=html\|json` | Export |
| DELETE | `/api/reports/{id}` | Delete the report and its media |

All `/api/reports…` and `/api/dashboard` routes require a signed-in user. Interactive API
documentation is available at `/docs` while the server runs.

## Limitations

* The text indicators are a lexicon. They miss dialect, sarcasm, Arabizi and new phrasing, and
  they describe wording, not truthfulness or reader reaction.
* The consistency model sees topic, not facts. It cannot verify place, date or identity, and is
  near chance on miscaptioned genuine photos (see VERITE).
* Arabic consistency relies on a multilingual encoder distilled to CLIP and has not been evaluated
  on Arabic captions.
* The AI-image detector's limits are in its section above. No conventional-editing detection
  exists.
* For video, only sampled frames are analysed; a manipulated segment between samples can be
  missed. Audio is ignored.
* Evidence providers are untested against live services. Their coverage depends on the provider's
  index and on page metadata.
* Claim extraction (event, place, date) is rule-based, with a UAE gazetteer. Places outside it are
  not recognised.
* Module finding messages are English-only.

## SGP1 → SGP2

**SGP1** established the design and demonstrated the submission-to-report workflow with **sample
findings**: text and image upload, eleven placeholder report sections, history, HTML/JSON export
and deletion. Reports created then are kept, open with an *SGP1 SAMPLE REPORT* label, and are never
presented as model output.

**SGP2** (this version) replaces the placeholders with:

* real analysis modules and evidence providers;
* documented rules;
* short-video support and the bilingual RTL interface;
* the measured evaluations above.

Where something could not be implemented or measured, it is marked as optional, planned or
unmeasured, and the matching check shows as *not configured* in the app.
