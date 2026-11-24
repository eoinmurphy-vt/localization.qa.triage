# Localization QA Triage

A Claude prompt and skill that help linguist reviewers decide **which published articles to review
first**. It compares source and localized (target) articles, flags quality risks it can back up with
quotes, and rates each article **High / Medium / Low** (or **Check manually** when a page can't be
read).

It is a triage aid, not a full LQA. Reviewers make the final call.

## Ways to use it

| Option | Setup | Good for | Needs |
|---|---|---|---|
| **A. Copy-paste prompt** ([prompts/triage-prompt.md](prompts/triage-prompt.md)) | None | Trying it today; 1–10 articles per chat | Any Claude chat; web access to read URLs, or paste the text |
| **B. Claude Project** | 5 minutes, once | A team using the same instructions every day | Prompt A pasted as the Project's instructions |
| **C. Skill** (release ZIP) | Upload once; an org owner can install it for everyone | Whole spreadsheets → sorted Excel report with reviewer columns | Skills and code execution enabled in the Claude organization |
| **D. Claude Code** | Install Claude Code, clone this repo | 100–200 article batches, fetching pages directly | Claude Code on the same Claude account; network access to the site |

A and B need nothing installed and use the same rubric and rating rule as the skill. C and D add
what a prompt can't do reliably: read the spreadsheet, keep progress across sessions, apply the
rating rule in code, and build the report.

## Repository layout

```
prompts/triage-prompt.md                 copy-paste prompt (options A and B)
.claude/skills/localization-qa-triage/   the skill (this folder is what gets zipped)
  SKILL.md                               instructions Claude follows
  references/                            rubric, output formats, large batches, client assets
  scripts/                               batch.py, extract_text.py, precheck.py, build_report.py
  assets/glossary_template.csv           expected glossary columns
docs/reviewer-guide.md                   how reviewers install and use it
tests/                                   script tests + a sample article pair
tools/package.py                         builds dist/localization-qa-triage.zip
.github/workflows/                       CI tests; release ZIP on version tags
CLAUDE.md                                conventions for working on this repo with Claude Code
```

## Installing the skill

**Claude (web / desktop app):** download `localization-qa-triage.zip` from the latest
[release](../../releases), then **Customize > Skills > + > Create skill > Upload a skill**.
Organization owners can install it for everyone in **Organization settings > Skills**.

**Claude Code:** open this repo with Claude Code. Skills in `.claude/skills/` load automatically,
and Claude Code can fetch live URLs and run the scripts locally, which suits large batches.

See [docs/reviewer-guide.md](docs/reviewer-guide.md) for the reviewer workflow.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest -q          # run script tests
python tools/package.py      # build dist/localization-qa-triage.zip
```

## Releasing

1. Update `CHANGELOG.md`.
2. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`
3. GitHub Actions runs the tests, builds the ZIP and attaches it and the prompt to a GitHub release.

## Data handling

Don't commit client content: article text, batch spreadsheets, results or triage reports.
Put working files in `runs/` (git-ignored). Client glossaries and style guides must never be added
to this repo or the skill package.

### 📝 License

This project is licensed under the Apache 2.0 License. © 2026 Vistatec, Ltd.

---