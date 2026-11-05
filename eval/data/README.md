# Evaluation data

## `text_indicators_dev.jsonl` / `text_indicators_test.jsonl`

Developer-written short social-media-style posts about the UAE, in English and Arabic (MSA and some
Gulf dialect). They are **synthetic**, not collected from real accounts, so they contain no personal
data. They are a proxy until a reviewed sample of real posts is available.

* `dev` was used while writing the lexicon. `test` was written after the lexicon was frozen
  (`text-lexicon-1.0`) and has not been used to change it.
* Fields: `id`, `lang` (`en`/`ar`), `text`, `labels` (active indicator categories), `phenomenon`
  (`indicator`, `negation`, `quote`, `debunk`, `warning`, `neutral`, `dialect`).

**Labelling criteria.** A category is labelled only when the post itself directs that kind of
wording at the reader:

| Category | Label when the post… |
|---|---|
| `urgency` | demands immediate attention or action ("URGENT", "right now", "عاجل", "فوراً", repeated `!!`, 🚨) |
| `fear` | uses alarming or catastrophic wording about a situation ("disaster", "people are dying", "كارثة", "هلع") |
| `manipulation` | claims hidden truth, absolute certainty or invites distrust ("they don't want you to know", "مسرب", "100% confirmed") |
| `share_pressure` | asks readers to spread it ("share this", "انشروها", "forward to everyone") |

Not labelled: negated wording ("do not share", "لا داعي للهلع"), wording quoted or attributed to
someone else's post, wording used to call something a rumour, and safety advisories attributed to an
authority (legitimate warnings). Labels were assigned by one annotator (the developer); a second
annotator should review them before results are used beyond this prototype.

## `uae_consistency_template.csv`

Template for the separately reviewed UAE caption–image test set (Arabic and English). It contains
no images: rows must be filled by a reviewer with images they have the right to use, following
the instructions in the README's evaluation section.
