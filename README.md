---
title: TruthLayer
emoji: 🔎
colorFrom: indigo
colorTo: green
sdk: streamlit
sdk_version: 1.40.1
app_file: app.py
pinned: false
---

# TruthLayer

Automated fact-checking for marketing and research documents. Upload a PDF; every
stat, date and figure in it is extracted, checked against live public data, and
flagged **Verified**, **Inaccurate** or **False** - with the correct real number and
a link to the source.

## Why

Marketing copy rots. A deck written in 2021 still says India has 1.2 billion people,
a blog post quotes a GDP figure from 2019, and an LLM-written brief invents a
statistic that never existed. TruthLayer is the layer between a document and the
reader: it reads the claims, goes to the live source, and says which ones no longer
hold.

## How it works

1. **Extract** (`truthlayer/extract.py`) - the PDF text is split into sentences and
   every sentence carrying a number with a unit, a percentage, a currency or a stat
   keyword becomes a claim. Each claim gets a kind (population, GDP, inflation, area,
   life expectancy, revenue, users, founded ...) and an entity (a country, or the
   named organisation).
2. **Verify** (`truthlayer/verify.py`) - country claims go to the World Bank's own
   indicator API for the latest value and its year. Organisation claims go to
   Wikipedia and Wikidata. The claimed value is compared with the live one.
3. **Report** (`truthlayer/report.py`) - a verdict per claim, the real figure, the
   year it is from, and the source link. Exportable as CSV.

Tolerances: within 5% (or 1 percentage point) is Verified; 5-100% off is Inaccurate
(outdated or wrong); beyond that, or no source at all, is False.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Command line, for a batch of documents:

```bash
python -m truthlayer.cli sample/trap_sample.pdf
```

## Tests

```bash
python -m pytest tests -q
```

## Sources

- World Bank Open Data (no key): population, GDP, inflation, life expectancy,
  unemployment, area, internet users, literacy, CO2, military and health spending.
- Wikipedia API (no key): organisation and topic claims.
- Wikidata (no key): founding years.

No API keys and no paid credits, so the app keeps working after any trial runs out.

## Limits

- Claims are matched by entity and kind, so a sentence with two different figures
  for two different countries is checked on the first one only.
- Private companies usually have no public source; those come back False with
  "no public source found", which is the honest answer.
- The World Bank publishes yearly, so a claim about the current year is compared
  with the latest published year and the year is shown next to the figure.


## Optional: Google Search grounding
Free data sources (World Bank, Wikidata, Wikipedia) cover country statistics and
dates. For anything else (company facts, tech figures, recent events) set
`GEMINI_API_KEY` (free from aistudio.google.com) as an environment variable or a
Streamlit/Space secret: claims the free sources can't settle are then checked by
Gemini with Google Search grounding, and the source link is shown.
