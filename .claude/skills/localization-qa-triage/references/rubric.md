# Triage rubric

Check categories in this order. The order reflects what most often causes real damage in
published content.

## Severity definitions

- **Critical**: a reader would be misled in a way that could cause harm, cost money, create legal or
  safety exposure, or make the article fail its purpose (wrong price, wrong date of an offer,
  reversed instruction, missing legal disclaimer, missing step in a procedure, offensive content).
- **Major**: meaning of a sentence or more is wrong or lost, or the problem is clearly visible to any
  native reader (missing paragraph, untranslated heading, garbled sentence, wrong product name).
- **Minor**: small, local and noticeable mainly to a careful reader (nuance lost, single
  untranslated phrase, inconsistent term, typo, format slip).

## Confidence definitions

- **High**: the quotes alone prove the issue.
- **Medium**: very likely an issue, but context outside the quotes could change it.
- **Low**: possible issue or possibly intentional; the reviewer should glance at it.

## Categories

### 1. Accuracy (mistranslation)
Meaning changed, reversed, or wrong. Includes negation errors, wrong subject/object, false friends,
wrong sense of an ambiguous word, mistranslated idioms.
- Critical: changes an instruction, safety, legal, financial or product-capability statement.
- Major: changes the meaning of a sentence.
- Minor: nuance or emphasis lost without changing the core message.

### 2. Omission / addition
Content in the source missing from the target, or content added to the target with no source.
Compare structure: headings, paragraphs, list items, table rows, captions, CTAs, disclaimers, footnotes.
- Critical: missing disclaimer, legal text, warning, procedure step, or a whole section.
- Major: missing or added sentence, list item or CTA.
- Minor: missing or added word or phrase that slightly changes the content.
Check extraction first: if a whole block is missing, make sure it isn't a page-rendering or
extraction gap (e.g. an accordion or tab not captured). If unsure, use Low confidence.

### 3. Numbers and data
Numbers, prices, currencies, percentages, dates, times, versions, units, phone numbers, codes, URLs,
email addresses and product SKUs that don't match the source.
- Locale-correct reformatting is **not** an error (1,000.50 → 1.000,50; MM/DD → DD.MM; 12-hour → 24-hour).
- Unit or currency conversion may be intentional; flag with Low confidence unless clearly wrong.
- Critical: prices, dates/deadlines of offers, specifications, dosages, legal figures.
- Major: other factual numbers.

### 4. Untranslated or wrong-language text
Source-language text left in the target, or text in a third language. Check titles, headings,
image alt text and captions, buttons/CTAs, table headers, and meta text if captured.
- Not an error: brand and product names, trademarks, code, commands, UI strings the product
  doesn't localize, terms on a do-not-translate list.
- Major: heading, CTA, sentence or longer. Minor: isolated word or phrase.

### 5. Terminology consistency
The same source term translated in different ways within the article, or brand/product/feature
names altered, translated or misspelled.
- Generic mode: only flag *inconsistency within the article* and altered brand/product names.
  Don't flag a term as "wrong" because you would have chosen another.
- With a client glossary: also flag deviations from glossary entries (see client_assets.md).
- Usually Minor; Major when it would confuse the reader (e.g. two names for the same UI element)
  or a product name is wrong.

### 6. Fluency and grammar
Errors a native reader would notice: agreement, word order, broken or unfinished sentences,
literal machine-translation output, wrong register switches within the article (e.g. formal and
informal "you" mixed).
- Major: unintelligible or obviously garbled sentence; register mixed throughout.
- Minor: isolated grammar error, typo, punctuation error.
- Generic mode: don't flag stylistic preferences or acceptable alternative phrasing.

### 7. Locale conventions
Date, time, number, currency, address and phone formats wrong for the target locale; wrong
quotation marks or spacing rules where a convention is clear (e.g. French spaces before ; : ! ?).
- Usually Minor. Major if it causes misreading (e.g. 03/04 read as the wrong date).

### 8. Rendering and publishing
Encoding errors (mojibake like "Ã©"), broken characters, visible markup or placeholders
({0}, %s, [[link]]), truncated sentences, duplicated paragraphs.
- Major when visible in the body or headings; Minor otherwise.

### 9. Cultural suitability
Content that could be offensive, inappropriate or clearly unsuitable for the target market.
- Critical if offensive; otherwise Minor with Low confidence. This needs a human judgement.

## Do not flag

- Rephrasing, restructuring or merged/split sentences that preserve meaning.
- Synonym or style choices (in generic mode).
- Locale-correct formatting changes.
- Plausibly intentional adaptation (localized examples, local offers, local contact details),
  except as Minor/Low "may be intentional".
- Page furniture that differs between locales (menus, footers, related links).
- Source-text errors that the translator correctly worked around.
