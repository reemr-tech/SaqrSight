# Labelling real posts – guide for annotators

This guide is for building a **real** test set for SaqrSight's text indicators. Until it exists,
all text results are measured on posts written by the developer.

Target: **150–300 posts**, about half Arabic (including Gulf dialect) and half English.

## 1. Before you start
- **Ask your advisor** whether the university needs ethics approval for collecting public social-media
  text. Keep the approval or the advisor's written OK with the project files.
- Collect only **public** posts. Copy **only the text**. Do not collect usernames, profile names,
  photos, phone numbers or links to accounts. If a post contains a person's name or number, replace
  it with `[NAME]` or `[NUMBER]`.
- Do not use any scraping tool against a platform's terms. Copy and paste manually.

## 2. What to collect (aim for a mix)
| Kind of post | Approx. share | Examples of where to look |
|---|---|---|
| Alarming or urgent claims about the UAE (fires, floods, closures, shortages, outbreaks) | 40% | Public X/Telegram posts, WhatsApp forwards shared publicly, viral rumours reported by fact-checkers |
| Posts that **deny** rumours or tell people **not** to share | 15% | Police/ministry replies, community pages |
| Official warnings (NCM, NCEMA, police) | 15% | Official accounts, WAM |
| Posts that **quote** a rumour while reporting on it | 10% | News and fact-check articles |
| Ordinary, neutral UAE posts | 20% | Traffic updates, events, weather |

Do not choose posts because SaqrSight does or does not detect them – collect first, test later.

**Include long posts too.** Aim for about **one third paragraph-length posts** (three or more sentences),
for example long WhatsApp forwards, Telegram messages, or official statements. Short captions behave
differently from paragraphs: a paragraph can mix a rumour, a denial and advice in one post. Label a
category `1` if **any part** of the post itself uses that kind of wording towards the reader; quoted or
denied parts still count as `0`. In the `notes` column write `long` for these posts so results can be
compared for short and long posts.

## 3. Fill in the spreadsheet
Use `eval/annotation/template.csv` (opens in Excel or Numbers; save as CSV, UTF-8).

| Column | What to write |
|---|---|
| `id` | Any unique id, e.g. `r-001` |
| `lang` | `ar` or `en` (for mixed posts, the main language) |
| `text` | The post text, anonymised |
| `source_type` | e.g. `x`, `telegram`, `news`, `official`, `whatsapp-public` |
| `date_collected` | e.g. `2026-11-10` |
| `urgency`, `fear`, `manipulation`, `share_pressure` | `1` if the post itself uses this kind of wording, otherwise `0` |
| `panic_level` | `none`, `mild` (some urgency or pressure, no fear-inducing wording) or `strong` (panic- or fear-inducing wording) – judged on the wording, not on whether the news is true |
| `phenomenon` | One of `indicator`, `dialect`, `negation`, `quote`, `debunk`, `warning`, `neutral` |
| `notes` | Anything unclear |

## 4. Labelling rules (same as the existing data – see `eval/data/README.md`)
Label a category **1** only when the post itself directs that wording at the reader:

| Category | Label 1 when the post… | Example |
|---|---|---|
| urgency | demands immediate attention or action | "عاجل", "الحين اطلعوا", "URGENT", "act now", "!!!", 🚨 |
| fear | uses alarming or catastrophic wording | "كارثة", "الناس محاصرين", "people are dying" |
| manipulation | claims hidden truth or absolute certainty, or invites distrust | "الإعلام ساكت", "100% confirmed", "they're hiding it" |
| share_pressure | asks readers to spread it | "دزوها", "انشروها", "share this", "RT" |

Label **0** when the wording is:
- **negated** – "لا تنشروا", "ما في داعي للخوف", "don't share this";
- **quoted or reported** – "a post claims 'share now'", "تداول منشور يقول…";
- used to **debunk** – "the rumour of a lockdown is false";
- part of an **official warning** – "NCM warns of dangerous fog".

## 5. Two annotators, then agree
1. Two people label **the same posts separately**, without discussing them: save as
   `annotator_A.csv` and `annotator_B.csv` (same ids and texts, only the label columns differ).
2. Measure agreement:
   ```bash
   .venv/bin/python -I eval/annotation/agreement.py annotator_A.csv annotator_B.csv
   ```
   This prints Cohen's kappa per category (above 0.6 is usually considered good) and writes
   `disagreements.csv`.
3. Meet, discuss each disagreement, and agree a final label. Save the final file as `adjudicated.csv`.
4. Load it into the evaluation:
   ```bash
   .venv/bin/python -I eval/annotation/import_real.py adjudicated.csv
   .venv/bin/python -I eval/eval_text.py
   .venv/bin/python -I eval/eval_text_ml.py
   .venv/bin/python -I eval/make_text_report.py
   ```
   The import splits the posts into a development half (`real_dev`, may be used to improve the word
   lists and train the model) and a test half (`real_test`, **never** used for changes). Report results
   on `real_test`.

Report the kappa values and the number of posts in your project document.
