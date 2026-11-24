# Localization QA Triage – Reviewer Guide

Skill version 0.1 (pilot). The shared, editable copy of this guide lives in Claude Docs; keep the two in step.

## What it does

The **localization-qa-triage** skill helps you decide which published articles to review first. It compares each source article with its localized version, lists issues it can back up with quotes, and gives each article a risk rating:

| Rating | Meaning | What to do |
|---|---|---|
| **High** | Any Critical issue, or 2+ Major issues | Review first |
| **Check manually** | The page text couldn't be read reliably (login, consent page, error) | Open the pages yourself |
| **Medium** | 1 Major issue, or 3+ Minor issues | Review next |
| **Low** | No significant issues found | Spot-check or review last |

It is a **triage aid, not a full LQA**. Only High- and Medium-confidence issues count towards the rating; Low-confidence ones are listed so you can glance at them.

## Install

- **Whole team (recommended):** a Claude organization owner uploads `localization-qa-triage.zip` in **Organization settings > Skills**.
- **Individual (testing):** **Customize > Skills > + > Create skill > Upload a skill**, then select the ZIP and make sure it is toggled on.
- **Claude Code:** open this repository; the skill loads automatically from `.claude/skills/`.

Batches need code execution / file creation enabled. Live URLs need web access enabled.

## Check one article

Paste the source and target text (or the two URLs) and ask: *"Triage this article pair. Source en-US, target de-DE."*

## Triage a batch

Upload the batch spreadsheet and ask: *"Triage all article pairs in this spreadsheet and give me a prioritized report."* You get `triage_report.xlsx` with **Triage**, **Issues** and **About** sheets, sorted High → Check manually → Medium → Low.

## Help us calibrate it

While reviewing, fill in **Reviewer status** (Triage sheet) and **Reviewer verdict** (Issues sheet). This shows how often High-rated articles really need work and which flags are noise.

## What it checks

Meaning errors, omissions/additions, numbers/prices/dates/URLs, untranslated text, terminology consistency, fluency, locale formats, rendering problems and cultural suitability. In **generic mode** (default) it doesn't flag style or word-choice preferences.

## Adding client assets later

Attach a glossary, do-not-translate list or style guide in the same chat (or a Claude Project). The skill switches to **client-assets mode**. Assets stay in your own Claude workspace and are never part of the skill package or this repository.

## Known limits

- Some sites block automated reading; those articles come back as **Check manually**.
- Content in tabs, accordions or images may not be captured, which can look like an omission.
- Severity is an estimate: treat the rating as a reading order, not a verdict.
- Results can vary slightly between runs. Don't use ratings to score translators.
