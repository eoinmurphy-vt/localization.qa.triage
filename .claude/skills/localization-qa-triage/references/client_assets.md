# Using client assets (optional)

The skill runs in **generic mode** by default. If the reviewer provides any of the assets below in
the conversation or project, switch to **client-assets mode** and say so in the output header.
Assets stay in the reviewer's own Claude workspace; this skill never needs them to be bundled.

## Glossary / termbase
Accepted formats: CSV/XLSX with source and target term columns, or a pasted list.
`assets/glossary_template.csv` shows the expected columns.
- Flag a target that uses a different translation for a glossary source term (Terminology,
  usually Minor; Major for product, feature or UI names).
- Respect the `status` column: `forbidden` target terms are always flagged; `dnt`
  (do not translate) source terms must appear unchanged in the target.
- Match inflected forms sensibly (plural, case endings). If unsure whether an inflection is a
  match, don't flag it.

## Style guide
- Apply only rules that are explicit and checkable (register/formality, quotation marks, number
  formats, capitalization of headings, gender-inclusive language rules, brand-name handling).
- Report style-guide deviations under the closest category with a "Style guide:" prefix in the
  explanation, normally Minor.
- Ignore vague guidance ("be engaging") for triage purposes.

## Do-not-translate list
Treat as glossary rows with `status = dnt`.

## Translation memory
Not needed for triage. If supplied, don't load it in full; use it only to look up a specific
segment when checking a suspected inconsistency.

## Generic baseline (no client assets)
Without client assets, rely on objective checks only. Public references the reviewer may add for
general locale conventions: the Microsoft localization style guides (per language, free to
download) and the MQM error typology. Don't treat them as the client's rules: deviations from
them are at most Minor with Low confidence.
