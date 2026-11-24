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

## Batch: result object (one per article, appended to results.json)

`results.json` is a JSON array. Each element:

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
      "source": "short source quote",
      "target": "[missing]",
      "explanation": "One sentence."
    }
  ]
}
```

Allowed values:
- `extraction`: `ok`, `partial`, `failed` (`failed` → rating becomes Check manually; `partial` is
  noted in the report and lowers trust in omission findings)
- `category`: Accuracy, Omission, Addition, Numbers, Untranslated, Terminology, Fluency, Locale,
  Rendering, Cultural
- `severity`: Critical, Major, Minor
- `confidence`: High, Medium, Low

Don't include a risk field: `build_report.py` computes it from the issues using the rule in SKILL.md.
Keep `id` equal to whatever identifies the row in the reviewer's original spreadsheet (an ID column
if there is one, otherwise "Row N" with the spreadsheet row number).
