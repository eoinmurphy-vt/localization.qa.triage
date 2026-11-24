# Output formats

## Single article (chat)

```
RISK: High | Medium | Low | Check manually
Locales: en-US → de-DE   |   Mode: generic (no client assets) / client assets applied
Summary: <one sentence: the main reason for the rating>

Issues (most severe first):
1. [Major · Omission · High confidence]
   Source: "…"
   Target: [missing]
   Why: <one sentence>
2. …

Pre-check signals checked and dismissed: <optional, one line, e.g. "3 numbers reformatted for locale">
```

If there are no issues: `RISK: Low`, a one-line summary and "No issues found."

## Batch: result object (one line per article in results.jsonl)

`results.jsonl` holds one JSON object per line (JSON Lines). Append a line as soon as an article
is finished; never rewrite the file. Shown here pretty-printed; in the file it is one line:

```json
{
  "id": "Row 2",
  "source_url": "https://…/en-us/article",
  "target_url": "https://…/de-de/article",
  "source_locale": "en-US",
  "target_locale": "de-DE",
  "title": "Source article title",
  "extraction": "ok",
  "extraction_note": "",
  "summary": "One sentence explaining the main risk.",
  "issues": [
    {
      "category": "Omission",
      "severity": "Major",
      "confidence": "High",
      "source": "short verbatim source quote",
      "target": "[missing]",
      "explanation": "One sentence."
    }
  ]
}
```

Allowed values:
- `extraction`: `ok`, `partial`, `failed`
  - `failed` → the rating becomes Check manually. Use it when a page couldn't be read, was a
    login/consent/bot-check/error page, redirected elsewhere, or the two pages are not the same
    article. Say which in `extraction_note`.
  - `partial` → readable but incomplete (e.g. tabs or accordions not captured); say what is
    missing in `extraction_note` and use Low confidence for omissions in that area.
- `category`: Accuracy, Omission, Addition, Numbers, Untranslated, Terminology, Fluency, Locale,
  Rendering, Cultural
- `severity`: Critical, Major, Minor
- `confidence`: High, Medium, Low

Don't include a risk field: `build_report.py` computes it from the issues using the rule in SKILL.md.
Keep `id` exactly as in `batch.jsonl` (the spreadsheet's ID column, or "Row N" with the spreadsheet
row number), so the report can match results to rows and list anything not processed.
`build_report.py` also accepts a `.json` array, for older runs.
