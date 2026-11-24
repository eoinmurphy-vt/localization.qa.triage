# Localization QA Triage

A Claude skill that helps linguist reviewers decide **which published articles to review first**.
It compares source and localized (target) articles, flags quality risks it can back up with quotes,
and rates each article **High / Medium / Low** (or **Check manually** when a page can't be read).

It is a triage aid, not a full LQA. Reviewers make the final call.

## Repository layout

```
.claude/skills/localization-qa-triage/   the skill (this folder is what gets zipped)
  SKILL.md                               instructions Claude follows
  references/                            rubric, output formats, client-asset handling
  scripts/                               extract_text.py, precheck.py, build_report.py
  assets/glossary_template.csv           expected glossary columns
docs/reviewer-guide.md                   how reviewers install and use it
tests/                                   script tests + a sample article pair
tools/package.sh                         builds dist/localization-qa-triage.zip
.github/workflows/                       CI tests; release ZIP on version tags
CLAUDE.md                                conventions for working on this repo with Claude Code
```

## Using the skill

**Claude (web / desktop app):** download `localization-qa-triage.zip` from the latest
[release](../../releases), then **Customize > Skills > + > Create skill > Upload a skill**.
Organization owners can install it for everyone in **Organization settings > Skills**.

**Claude Code:** open this repo with Claude Code. Skills in `.claude/skills/` load automatically,
and Claude Code can fetch live URLs and run the scripts locally, which suits large batches.

See [docs/reviewer-guide.md](docs/reviewer-guide.md) for the reviewer workflow.

## Development

```bash
pip install -r requirements-dev.txt
pytest -q                 # run script tests
./tools/package.sh        # build dist/localization-qa-triage.zip
```

## Releasing

1. Update `CHANGELOG.md`.
2. Tag and push: `git tag v0.1.0 && git push origin v0.1.0`
3. GitHub Actions runs the tests, builds the ZIP and attaches it to a GitHub release.

## Data handling

Don't commit client content: article text, batch spreadsheets, `results.json` or triage reports.
Put working files in `runs/` (git-ignored). Client glossaries and style guides must never be added
to this repo or the skill package.
