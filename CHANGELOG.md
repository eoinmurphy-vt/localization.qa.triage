# Changelog

## v0.2.0 – unreleased
- **Copy-paste prompt** (`prompts/triage-prompt.md`) for reviewers without the skill, usable as
  Claude Project instructions. Same rubric and rating rule as the skill.
- **Batch helper** `batch.py`: maps the reviewer's spreadsheet (including hyperlinked cells and
  one-column-per-language layouts), fetches texts and runs the pre-check for every article, and
  reports progress so a large batch can be resumed in a new conversation or split across
  subagents.
- **Report**: results are checked and normalised before rating, so a lower-case "major" no longer
  drops an article to Low; unknown values stop the build with a list to fix. Accepts JSON Lines,
  folders of chunk files and duplicates (last wins); lists unprocessed articles; adds a "Minutes
  spent" column and live pilot metrics (confirmed rate and average minutes per tier, flag
  precision). Text from web pages can no longer turn into spreadsheet formulas.
- **Pre-check**: numbers compared by value with locale-aware decimal separators (catches 1.5 % →
  15 %), native digits (Arabic-Indic, Devanagari…) and Indian digit grouping; dates in different
  formats no longer raise false alarms; new signals for placeholders, visible markup and garbled
  characters; no longer crashes on non-Latin output in a Windows console.
- **Extraction**: keeps titles in hero banners and article headers, text in plain `<div>`s,
  CTA links and buttons; reads the page's declared charset; flags redirects to another locale,
  site or the home page; counts words correctly for Chinese, Japanese and Thai; recognises
  bot-check pages.
- Packaging is now `python tools/package.py` (works on Windows without `zip`).
- From the first real batch:
  - Extraction trims sites that wrap the whole page (menus, sidebar, footer) in `<main>`.
  - Short links that redirect to the full article URL are no longer flagged; locales such as
    `…_fr_CA` in a URL are recognised; redirects to another site (e.g. a sign-in page) are.
  - `batch.py init` takes `--source-locale` / `--target-locale`, skips exact duplicate rows,
    warns when different rows share the same links (broken links in the sheet) and carries the
    sheet's title column into the report.
  - Template problems repeated on every page (e.g. an untranslated date label) are reported once
    per batch, not per article.

## v0.1.0 – pilot
- First version: single-article and batch triage, generic mode, optional client assets.
- Scripts: text extraction, objective pre-check, Excel report builder.
