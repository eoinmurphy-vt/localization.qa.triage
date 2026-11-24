# Large batches

A single conversation fills up after roughly 15–20 article pairs, because every fetched article
stays in context. Batches of 100–200 articles are split across conversations (Claude chat) or
across subagents (Claude Code). The files in `runs/<batch>/` carry the state between them:

| File | Written by | Purpose |
|---|---|---|
| `batch.jsonl` | `batch.py init` | one line per article: id, row, key, URLs, guessed locales |
| `texts/` | `batch.py fetch` | `<key>.source.txt`, `<key>.target.txt`, `<key>.precheck.txt`, `fetch_log.jsonl` |
| `results.jsonl` or `results/*.jsonl` | Claude | one result object per line (`output_format.md`) |
| `triage_report.xlsx` | `build_report.py` | the deliverable |

`batch.py status runs/<batch>/batch.jsonl <results...>` always tells you what is left.

## Claude chat (Claude.ai / desktop app with the skill installed)

- Needs "Code execution and file creation" turned on. The sandbox usually has no internet access,
  so `batch.py fetch` will report that every fetch failed: use the web fetch tool for each URL.
- Process up to about 15 articles, then build an interim report so the reviewer can start, and tell
  the user how to continue:
  1. Download `batch.jsonl` and `results.jsonl`.
  2. Open a new conversation, upload both files and say "Continue the triage batch".
- In the new conversation, run `batch.py status` with the uploaded files, take the next IDs from
  its output and carry on appending to the same `results.jsonl`.

## Claude Code

- Network access is normally available, so run `batch.py fetch` once for the whole batch
  (`--workers 4` by default; lower it if the site rate-limits), then `batch.py unreadable` so
  dead links and sign-in pages are recorded without analysis.
- For more than about 15 articles, use subagents so the main conversation stays small:
  1. `batch.py status runs/<batch>/batch.jsonl runs/<batch>/results --chunks 10` prints the
     remaining IDs in groups of 10.
  2. Start one subagent per chunk, at most 3 at a time. Give each this brief (fill in the parts in
     angle brackets):

     > Use the localization-qa-triage skill to triage these articles from
     > `runs/<batch>/batch.jsonl`: <IDs>. Texts and pre-check output are in
     > `runs/<batch>/texts/<key>.*.txt` (the key is in batch.jsonl). Mode: <generic | client
     > assets at path>. For each article, append one result object per line to
     > `runs/<batch>/results/chunk-<NN>.jsonl` (schema in the skill's
     > references/output_format.md). Then run `batch.py check` on your chunk file and fix
     > anything it reports. Don't build the report. Reply with one line per article:
     > ID, rating, main issue.

  3. Each subagent writes its own chunk file, so parallel agents never write to the same file.
  4. When all chunks are done: `build_report.py runs/<batch>/results --batch
     runs/<batch>/batch.jsonl --out runs/<batch>/triage_report.xlsx`.

## When pages can't be fetched

- If many fetches fail with 403/429 or the texts look like bot-check pages, stop and tell the user:
  the site is blocking scripted requests. Options: the web fetch tool, saving the pages as HTML
  from a browser (then `extract_text.py page.html`), or pasting text.
- Never fill a gap from memory or from another locale's page.
