#!/usr/bin/env python3
"""Batch helper: read the reviewer's spreadsheet, fetch article texts, track progress.

Usage:
    python batch.py init SPREADSHEET --out runs/b1/batch.jsonl [--sheet NAME]
                         [--source-col COL] [--target-col COL ...] [--id-col COL]
    python batch.py fetch runs/b1/batch.jsonl --texts runs/b1/texts [--workers 4]
                          [--ids "Row 2,Row 3"] [--refetch]
    python batch.py status runs/b1/batch.jsonl RESULTS... [--chunks 10]

init    Finds the source and target URL columns (and an ID column, if any) in an .xlsx or
        .csv file, guesses locales from the URLs and writes one JSON line per article.
        COL is a header name, a column letter (B) or a 1-based number. Several target
        columns (one per language) give one article per target.
fetch   Needs network access. Saves <key>.source.txt, <key>.target.txt and
        <key>.precheck.txt per article in the texts folder, plus fetch_log.jsonl.
        Articles fetched before are skipped unless --refetch.
status  Shows how many articles have a result and which are still to do, so a batch can
        be resumed in a new session. RESULTS are the files/folders given to build_report.py
        (missing ones count as empty). --chunks N splits the remaining IDs into groups of N.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_report  # noqa: E402
import extract_text  # noqa: E402
import precheck  # noqa: E402

URL_RE = re.compile(r"^\s*https?://\S+\s*$", re.I)
HYPERLINK_FORMULA = re.compile(r'^=\s*HYPERLINK\(\s*"([^"]+)"', re.I)
SOURCE_HINT = re.compile(r"source|\bsrc\b|original|english|\ben\b|\bfrom\b", re.I)
TARGET_HINT = re.compile(r"target|\btgt\b|transl|locali[sz]ed|\bto\b", re.I)
ID_HINT = re.compile(r"^\s*(id|article\s*id|#|no\.?|number|key|ref(erence)?)\s*$", re.I)
LOCALE_HINT = re.compile(r"locale|language|\blang\b|market", re.I)
LANGS = {
    "af", "am", "ar", "az", "be", "bg", "bn", "bs", "ca", "cs", "cy", "da", "de", "el", "en", "es",
    "et", "eu", "fa", "fi", "fil", "fr", "ga", "gl", "gu", "he", "hi", "hr", "ht", "hu", "hy", "id",
    "is", "it", "ja", "ka", "kk", "km", "kn", "ko", "lo", "lt", "lv", "mk", "ml", "mn", "mr", "ms",
    "my", "nb", "ne", "nl", "no", "pa", "pl", "ps", "pt", "ro", "ru", "si", "sk", "sl", "so", "sq",
    "sr", "sv", "sw", "ta", "te", "th", "tl", "tr", "uk", "ur", "uz", "vi", "zh", "zu",
}


# ---------------------------------------------------------------- reading the spreadsheet

def read_table(path, sheet=None):
    """Return (sheet_name, other_sheets, rows); rows are (row_number, [values]), links resolved."""
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(p)  # not read-only: hyperlinks are needed
        ws = wb[sheet] if sheet else wb.worksheets[0]
        rows = []
        for row in ws.iter_rows():
            vals = []
            for c in row:
                v = c.value
                is_url = isinstance(v, str) and URL_RE.match(v)
                if not is_url and c.hyperlink is not None and c.hyperlink.target:
                    v = c.hyperlink.target          # cell shows a title, links to the article
                elif isinstance(v, str) and HYPERLINK_FORMULA.match(v):
                    v = HYPERLINK_FORMULA.match(v).group(1)
                vals.append(v)
            if row:
                rows.append((row[0].row, vals))
        return ws.title, [n for n in wb.sheetnames if n != ws.title], rows
    raw = p.read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return p.name, [], list(enumerate(csv.reader(raw.splitlines(), dialect), 1))


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _cell(vals, j):
    return vals[j] if j < len(vals) else None


def col_index(spec, headers):
    s = str(spec).strip()
    for j, h in enumerate(headers):
        if str(h or "").strip().lower() == s.lower():
            return j
    if re.fullmatch(r"[A-Za-z]{1,3}", s):
        n = 0
        for ch in s.upper():
            n = n * 26 + ord(ch) - 64
        return n - 1
    if s.isdigit():
        return int(s) - 1
    raise SystemExit(f"Column {spec!r} not found. Headers: {', '.join(str(h) for h in headers if h)}")


def letter(j: int) -> str:
    s, j = "", j + 1
    while j:
        j, r = divmod(j - 1, 26)
        s = chr(65 + r) + s
    return s


def guess_locale(url: str) -> str:
    """Best-effort locale from a URL path (/de-de/, /fr/, /ca/fr/) or subdomain (de.example.com)."""
    parts = urlsplit(url or "")
    segs = [s for s in parts.path.lower().split("/") if s][:4]
    for s in segs:
        m = re.fullmatch(r"([a-z]{2,3})[-_]([a-z]{2}|\d{3}|hans|hant)", s)
        if m and m.group(1) in LANGS:
            region = m.group(2)
            return f"{m.group(1)}-{region.upper() if len(region) == 2 else region.title()}"
    for a, b in zip(segs, segs[1:]):                     # /{country}/{language}/
        if len(a) == 2 and len(b) == 2 and b in LANGS:
            return f"{b}-{a.upper()}"
    for s in segs:
        if s in LANGS:
            return s
    sub = (parts.hostname or "").split(".")[0]
    return sub if sub in LANGS else ""


def _norm_locale(v) -> str:
    s = str(v or "").strip()
    m = re.fullmatch(r"([A-Za-z]{2,3})(?:[-_]([A-Za-z]{2}))?", s)
    if not m or m.group(1).lower() not in LANGS:
        return ""
    return m.group(1).lower() + (f"-{m.group(2).upper()}" if m.group(2) else "")


def cmd_init(args):
    sheet, other_sheets, rows = read_table(args.spreadsheet, args.sheet)
    nonempty = [(n, v) for n, v in rows if sum(not _blank(x) for x in v) >= 1]
    hdr_i = next((i for i, (_, v) in enumerate(nonempty) if sum(not _blank(x) for x in v) >= 2), None)
    if hdr_i is None:
        raise SystemExit("Couldn't find a header row with at least two filled cells.")
    headers = [str(h).strip() if not _blank(h) else "" for h in nonempty[hdr_i][1]]
    data = nonempty[hdr_i + 1:]
    ncols = max([len(headers)] + [len(v) for _, v in data])
    headers += [""] * (ncols - len(headers))
    name = lambda j: f'{letter(j)} "{headers[j]}"' if headers[j] else letter(j)  # noqa: E731

    url_cols = []
    for j in range(ncols):
        vals = [_cell(v, j) for _, v in data if not _blank(_cell(v, j))]
        if vals and sum(isinstance(x, str) and bool(URL_RE.match(x)) for x in vals) >= 0.5 * len(vals):
            url_cols.append(j)

    notes = []
    src = col_index(args.source_col, headers) if args.source_col else None
    tgts = [col_index(c, headers) for c in args.target_col] if args.target_col else []
    if src is None:
        named = [j for j in url_cols if SOURCE_HINT.search(headers[j]) and j not in tgts]
        if len(named) == 1:
            src = named[0]
        elif not named and len(url_cols) == 2 and not tgts:
            src = url_cols[0]
            notes.append("no column is labelled source/target: assumed the left URL column is the source")
        else:
            raise SystemExit("Can't tell which column holds the source URLs. URL columns: "
                             + ", ".join(name(j) for j in url_cols) + ". Re-run with --source-col.")
    if not tgts:
        others = [j for j in url_cols if j != src]
        named = [j for j in others if TARGET_HINT.search(headers[j])]
        tgts = named or others
        if not tgts:
            raise SystemExit("No target URL column found. Re-run with --target-col.")
    if args.id_col:
        id_col = col_index(args.id_col, headers)
    else:
        id_col = next((j for j, h in enumerate(headers) if ID_HINT.match(h)), None)
    loc_col = next((j for j, h in enumerate(headers)
                    if LOCALE_HINT.search(h) and j not in (src, *tgts, id_col)), None)

    items, keys, skipped = [], set(), 0
    for n, vals in data:
        base = _cell(vals, id_col) if id_col is not None else None
        if isinstance(base, float) and base.is_integer():
            base = int(base)
        base = str(base).strip() if not _blank(base) else f"Row {n}"
        for t in tgts:
            s_url, t_url = _cell(vals, src), _cell(vals, t)
            if _blank(s_url) or _blank(t_url):
                skipped += 1
                continue
            aid = base if len(tgts) == 1 else f"{base} {headers[t] or letter(t)}"
            key = re.sub(r"[^\w.-]+", "_", aid).strip("_")[:60] or f"row{n}"
            k, i = key, 2
            while k.lower() in keys:
                k, i = f"{key}-{i}", i + 1
            keys.add(k.lower())
            hint = _cell(vals, loc_col) if loc_col is not None else None
            items.append({
                "id": aid, "row": n, "key": k,
                "source_url": str(s_url).strip(), "target_url": str(t_url).strip(),
                "source_locale": guess_locale(str(s_url)),
                "target_locale": guess_locale(str(t_url)) or _norm_locale(hint),
                **({"locale_hint": str(hint)} if not _blank(hint) else {}),
            })
    if not items:
        raise SystemExit("No rows with both a source and a target URL.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    pairs = Counter(f"{i['source_locale'] or '?'} -> {i['target_locale'] or '?'}" for i in items)
    print(f'Sheet "{sheet}": {len(items)} articles from rows {data[0][0]}-{data[-1][0]}'
          + (f" ({skipped} row(s) without both URLs skipped)" if skipped else ""))
    if other_sheets:
        print("Other sheets (not read): " + ", ".join(other_sheets))
    print(f"Source URL: {name(src)}   Target URL: " + ", ".join(name(t) for t in tgts)
          + f"   ID: {name(id_col) if id_col is not None else 'row number'}")
    print("Locales guessed from URLs: " + ", ".join(f"{k} ({v})" for k, v in pairs.most_common()))
    for n in notes:
        print("NOTE:", n)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- fetching

def fetch_one(item, texts: Path, refetch: bool):
    key = item["key"]
    sp, tp, pp = (texts / f"{key}.{s}.txt" for s in ("source", "target", "precheck"))
    if not refetch and sp.exists() and tp.exists():
        return {"id": item["id"], "key": key, "cached": True}
    s_text, s_st = extract_text.extract(item["source_url"])
    t_text, t_st = extract_text.extract(item["target_url"])
    for path, text in ((sp, s_text), (tp, t_text)):
        if text:
            path.write_text(text + "\n", encoding="utf-8")
        elif path.exists():
            path.unlink()
    if s_text and t_text:
        res = precheck.run(s_text, t_text, item.get("source_locale") or "en", item.get("target_locale") or "")
        pp.write_text(precheck.format_text(res) + "\n", encoding="utf-8")
    return {"id": item["id"], "key": key, "source": s_st, "target": t_st}


def cmd_fetch(args):
    items = build_report.load_batch(args.batch)
    if args.ids:
        wanted = {s.strip() for s in args.ids.split(",")}
        items = [i for i in items if str(i["id"]) in wanted]
    texts = Path(args.texts)
    texts.mkdir(parents=True, exist_ok=True)
    log_path = texts / "fetch_log.jsonl"
    log = {}
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                log[str(e["id"])] = e

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for e in pool.map(lambda it: fetch_one(it, texts, args.refetch), items):
            if not e.get("cached") or str(e["id"]) not in log:
                log[str(e["id"])] = e
    with log_path.open("w", encoding="utf-8") as f:
        for e in log.values():
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    counts, problems = Counter(), []
    for it in items:
        e = log.get(str(it["id"]), {})
        sides = [(side, e.get(side) or {}) for side in ("source", "target")]
        worst = ("failed" if any(st.get("status") == "failed" for _, st in sides) else
                 "suspect" if any(st.get("status") == "suspect" for _, st in sides) else
                 "ok" if all(st.get("status") == "ok" for _, st in sides) else "cached")
        counts[worst] += 1
        for side, st in sides:
            if st.get("status") in ("failed", "suspect"):
                why = st.get("error") or "; ".join(st.get("notes", []))
                problems.append(f"  {it['id']} {side}: {st['status']} - {why}")
    print(f"{len(items)} articles: " + ", ".join(f"{k} {v}" for k, v in counts.items()) + f". Texts in {texts}")
    if problems:
        print("Check these before analysing (open the text; rate Check manually if it isn't the article):")
        print("\n".join(problems[:40]) + ("\n  ..." if len(problems) > 40 else ""))
    if counts["failed"] == len(items) and items:
        print("Every fetch failed: no network access, or the site blocks scripted requests. "
              "Use the web fetch tool, saved HTML files or pasted text instead.")


# ---------------------------------------------------------------- status

def cmd_status(args):
    items = build_report.load_batch(args.batch)
    existing = [p for p in args.results if Path(p).exists()]
    results = build_report.load_results(existing)[0] if existing else []
    problems = build_report.normalise(results)
    done_ids = {str(a.get("id")) for a in results}
    batch_ids = [str(i["id"]) for i in items]
    remaining = [i for i in batch_ids if i not in done_ids]
    risks = Counter(build_report.rate(a) for a in results if str(a.get("id")) in set(batch_ids))
    summary = ", ".join(f"{k} {risks[k]}" for k in build_report.RISK_ORDER if risks[k])
    print(f"{len(batch_ids) - len(remaining)}/{len(batch_ids)} done" + (f": {summary}" if summary else ""))
    unknown = done_ids - set(batch_ids)
    if unknown:
        print(f"NOTE: {len(unknown)} result IDs are not in the batch file, e.g. {sorted(unknown)[:3]}")
    if problems:
        print(f"NOTE: {len(problems)} result values need fixing; build_report.py will list them.")
    if remaining:
        if args.chunks:
            for n in range(0, len(remaining), args.chunks):
                print(f"Chunk {n // args.chunks + 1}: " + ", ".join(remaining[n:n + args.chunks]))
        else:
            print(f"Remaining ({len(remaining)}): " + ", ".join(remaining[:20])
                  + (" ..." if len(remaining) > 20 else ""))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="spreadsheet -> batch.jsonl")
    p.add_argument("spreadsheet")
    p.add_argument("--out", required=True)
    p.add_argument("--sheet")
    p.add_argument("--source-col")
    p.add_argument("--target-col", action="append")
    p.add_argument("--id-col")
    p.set_defaults(func=cmd_init)
    p = sub.add_parser("fetch", help="extract texts and run the pre-check")
    p.add_argument("batch")
    p.add_argument("--texts", required=True)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--ids", help="comma-separated IDs (default: all)")
    p.add_argument("--refetch", action="store_true")
    p.set_defaults(func=cmd_fetch)
    p = sub.add_parser("status", help="progress and remaining IDs")
    p.add_argument("batch")
    p.add_argument("results", nargs="*")
    p.add_argument("--chunks", type=int, default=0)
    p.set_defaults(func=cmd_status)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
