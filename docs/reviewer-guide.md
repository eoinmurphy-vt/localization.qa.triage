# Localization QA Triage – Reviewer Guide

Version 0.2 (pilot). The shared, editable copy of this guide lives in Claude Docs; keep the two in step.

## What it does

It helps you decide which published articles to review first. It compares each source article with its localized version, lists issues it can back up with quotes, and gives each article a risk rating:

| Rating | Meaning | What to do |
|---|---|---|
| **High** | Any Critical issue, or 2+ Major issues | Review first |
| **Check manually** | The page couldn't be read reliably (login, consent or bot-check page, error, redirect) or the pages don't match | Open the pages yourself |
| **Medium** | 1 Major issue, or 3+ Minor issues | Review next |
| **Low** | No significant issues found | Spot-check or review last |

It is a **triage aid, not a full LQA**. Only High- and Medium-confidence issues count towards the rating; Low-confidence ones are listed so you can glance at them.

## Pick a way to run it

| You have… | Use |
|---|---|
| A few articles, nothing installed | **Copy-paste prompt**: open `prompts/triage-prompt.md`, paste it into a new chat, fill in the article table at the end. Up to 10 pairs per chat. |
| A team using it daily | **Claude Project**: paste the prompt (without the Articles section) into the Project instructions once; then each chat only needs the article table. |
| A whole spreadsheet and the skill installed | **Skill**: upload the spreadsheet and ask for a prioritized report (below). |
| 100+ articles and Claude Code | **Claude Code**: open this repository and ask Claude to triage the spreadsheet. |

## Install the skill

- **Whole team (recommended):** a Claude organization owner uploads `localization-qa-triage.zip` in **Organization settings > Skills**.
- **Individual (testing):** **Customize > Skills > + > Create skill > Upload a skill**, then select the ZIP and make sure it is toggled on.
- **Claude Code:** open this repository; the skill loads automatically from `.claude/skills/`.

The skill needs code execution / file creation enabled. Reading live URLs needs web access enabled.

## Check one article

Paste the source and target text (or the two URLs) and ask: *"Triage this article pair. Source en-US, target de-DE."*

## Triage a batch

Upload the batch spreadsheet and ask: *"Triage all article pairs in this spreadsheet and give me a prioritized report."* Claude confirms which columns hold the URLs, works through the articles, and gives you `triage_report.xlsx` with **Triage**, **Issues** and **About** sheets, sorted High → Check manually → Medium → Low.

A chat handles about 15 articles. For bigger batches Claude gives you an interim report and two files (`batch.jsonl`, `results.jsonl`). Start a new chat, upload both and say *"Continue the triage batch"*. Claude Code handles whole batches in one go.

## Help us measure it

While reviewing, fill in on the **Triage** sheet:
- **Reviewer status**: whether the article really had issues.
- **Minutes spent**: roughly how long the review took.

and on the **Issues** sheet, **Reviewer verdict** for each flag. The **About** sheet then shows, per tier, how many articles had confirmed issues, the average minutes per article, and what share of flags were real. That tells us whether the order saves time and which flags are noise.

## What it checks

Meaning errors, omissions/additions, numbers/prices/dates/URLs, untranslated text, terminology consistency, fluency, locale formats, rendering problems and cultural suitability. In **generic mode** (default) it doesn't flag style or word-choice preferences.

## Adding client assets later

Attach a glossary, do-not-translate list or style guide in the same chat (or a Claude Project). The skill switches to **client-assets mode**. Assets stay in your own Claude workspace and are never part of the skill package or this repository.

## Known limits

- Some sites block automated reading; those articles come back as **Check manually**. Test a few of your URLs first.
- Content in tabs, accordions or images may not be captured, which can look like an omission.
- Severity is an estimate: treat the rating as a reading order, not a verdict.
- Results can vary slightly between runs. Don't use ratings to score translators.
