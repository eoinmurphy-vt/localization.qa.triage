#!/usr/bin/env python3
"""Build the triage spreadsheet from the per-article results.

Usage:
    python build_report.py RESULTS... --out triage_report.xlsx [--batch batch.jsonl]
                           [--mode generic|client-assets]

RESULTS are .jsonl files (one result object per line), .json files (an array or one
object) or folders of them. If an article appears more than once, the last one wins.
--batch adds every article from batch.jsonl that has no result as "Not processed".

Values are checked and normalised first (e.g. "major" -> "Major"); anything that can't be
normalised stops the script with a list of what to fix, because a misspelt severity would
otherwise silently push a risky article to the bottom of the list.

Computes each article's risk rating from its issues (same rule as SKILL.md), sorts
High -> Check manually -> Medium -> Low -> Not processed, and writes three sheets:
  Triage  one row per article, with reviewer status / minutes / notes columns
  Issues  one row per issue, with a reviewer verdict column (for calibration)
  About   method, rating rule, totals and pilot metrics that fill in as reviewers work
"""
import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

SEV_ORDER = {"Critical": 0, "Major": 1, "Minor": 2}
RISK_ORDER = {"High": 0, "Check manually": 1, "Medium": 2, "Low": 3, "Not processed": 4}
RISK_FILL = {"High": "F4C7C3", "Check manually": "E1D5F0", "Medium": "FCE8B2", "Low": "D9EAD3",
             "Not processed": "E0E0E0"}
CATEGORIES = ["Accuracy", "Omission", "Addition", "Numbers", "Untranslated", "Terminology",
              "Fluency", "Locale", "Rendering", "Cultural"]
CATEGORY_SYNONYMS = {
    "mistranslation": "Accuracy", "meaning": "Accuracy", "translation": "Accuracy",
    "omitted": "Omission", "missing": "Omission", "added": "Addition",
    "number": "Numbers", "data": "Numbers", "untranslated text": "Untranslated",
    "wrong language": "Untranslated", "language": "Untranslated", "terminology consistency": "Terminology",
    "term": "Terminology", "terms": "Terminology", "grammar": "Fluency", "spelling": "Fluency",
    "typo": "Fluency", "locale conventions": "Locale", "formatting": "Locale", "format": "Locale",
    "rendering and publishing": "Rendering", "publishing": "Rendering", "encoding": "Rendering",
    "cultural suitability": "Cultural", "culture": "Cultural",
}
EXTRACTION_SYNONYMS = {"ok": "ok", "partial": "partial", "suspect": "partial", "failed": "failed",
                       "fail": "failed", "error": "failed", "mismatch": "failed"}
STATUS_CHOICES = ["To review", "Reviewed – issues confirmed", "Reviewed – no real issues", "Skipped"]
VERDICT_CHOICES = ["Valid", "Valid – wrong severity", "Not an issue", "Unsure"]
RULE_TEXT = ("Counts issues with High/Medium confidence. High = any Critical or 2+ Major; "
             "Medium = 1 Major or 3+ Minor; Low = otherwise; Check manually = text could not be "
             "read reliably or the pages are not the same article.")


# ---------------------------------------------------------------- loading and validation

def _read_file(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".jsonl":
        items = []
        for n, line in enumerate(text.splitlines(), 1):
            if line.strip():
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise SystemExit(f"{path}:{n}: invalid JSON line ({e.msg}). Fix or remove it.")
        return items
    data = json.loads(text) if text.strip() else []
    return data if isinstance(data, list) else [data]


def load_results(paths):
    """Read results from files/folders. Returns (articles, warnings); later duplicates win."""
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in (".json", ".jsonl"))
        elif p.exists():
            files.append(p)
        else:
            raise SystemExit(f"Results file not found: {p}")
    by_id, warnings = {}, []
    for f in files:
        for n, a in enumerate(_read_file(f), 1):
            if not isinstance(a, dict):
                raise SystemExit(f"{f}: item {n} is not a JSON object")
            key = str(a.get("id") or f"{f.name}#{n}")
            if key in by_id:
                warnings.append(f"{key}: result appears more than once; keeping the last one")
                del by_id[key]
            by_id[key] = a
    return list(by_id.values()), warnings


def _key(v) -> str:
    return re.sub(r"[^a-z]+", " ", str(v or "").lower()).strip()


def _pick(value, allowed, synonyms=None):
    """Map a value onto an allowed spelling, case-insensitively; None if impossible."""
    k = _key(value)
    lookup = {_key(a): a for a in allowed}
    if synonyms:
        lookup.update({_key(s): v for s, v in synonyms.items()})
    if k in lookup:
        return lookup[k]
    first = re.split(r" and | or |\s", k)[0] if k else ""
    return lookup.get(first)


def normalise(articles):
    """Fix casing/synonyms in place. Returns a list of problems that need a human/Claude fix."""
    problems = []
    for a in articles:
        aid = a.get("id", "?")
        if not a.get("id"):
            problems.append(f"article {aid}: missing 'id'")
        ext = a.get("extraction") or "ok"
        a["extraction"] = EXTRACTION_SYNONYMS.get(_key(ext))
        if a["extraction"] is None:
            problems.append(f"{aid}: extraction={ext!r} (use ok, partial or failed)")
        issues = a.get("issues") or []
        if not isinstance(issues, list):
            problems.append(f"{aid}: 'issues' must be a list")
            issues = []
        a["issues"] = issues
        for n, i in enumerate(issues, 1):
            for field, allowed, syn in (("category", CATEGORIES, CATEGORY_SYNONYMS),
                                        ("severity", list(SEV_ORDER), None),
                                        ("confidence", ["High", "Medium", "Low"], None)):
                fixed = _pick(i.get(field), allowed, syn)
                if fixed is None:
                    problems.append(f"{aid}: issue {n} has {field}={i.get(field)!r} "
                                    f"(allowed: {', '.join(allowed)})")
                else:
                    i[field] = fixed
    return problems


def rate(article):
    if article.get("extraction") == "failed":
        return "Check manually"
    counted = [i for i in article.get("issues", []) if i.get("confidence") in ("High", "Medium")]
    c = Counter(i.get("severity") for i in counted)
    if c["Critical"] >= 1 or c["Major"] >= 2:
        return "High"
    if c["Major"] == 1 or c["Minor"] >= 3:
        return "Medium"
    return "Low"


def load_batch(path):
    items = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


# ---------------------------------------------------------------- spreadsheet helpers

def _styles():
    from openpyxl.styles import Alignment, Font, PatternFill
    return {
        "header_fill": PatternFill("solid", fgColor="2F3B52"),
        "header_font": Font(bold=True, color="FFFFFF"),
        "wrap": Alignment(wrap_text=True, vertical="top"),
        "top": Alignment(vertical="top"),
        "center": Alignment(vertical="center", wrap_text=True),
        "fill": lambda risk: PatternFill("solid", fgColor=RISK_FILL[risk]),
        "Font": Font,
    }


def put(ws, row, col, value, align=None):
    """Write a cell. Text starting with '=' (from a web page) is stored as text, never a formula."""
    cell = ws.cell(row=row, column=col, value=value)
    if isinstance(value, str) and value.startswith("="):
        cell.data_type = "s"
    if align is not None:
        cell.alignment = align
    return cell


def header(ws, cols, st):
    for c, (name, width) in enumerate(cols, 1):
        cell = ws.cell(row=1, column=c, value=name)
        cell.fill, cell.font, cell.alignment = st["header_fill"], st["header_font"], st["center"]
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 30


def link(cell, url, st):
    if url and re.match(r"https?://", str(url)):
        cell.value = url
        cell.hyperlink = url
        cell.font = st["Font"](color="1155CC", underline="single")
    elif url:
        cell.value = str(url)


def dropdown(ws, choices, cell_range):
    from openpyxl.worksheet.datavalidation import DataValidation
    dv = DataValidation(type="list", formula1='"' + ",".join(choices) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(cell_range)


# ---------------------------------------------------------------- main

def prepare(articles):
    for a in articles:
        a["risk"] = a.get("risk") if a.get("_not_processed") else rate(a)
        a["issues"] = sorted(a.get("issues", []), key=lambda i: (
            SEV_ORDER.get(i.get("severity"), 9), {"High": 0, "Medium": 1}.get(i.get("confidence"), 2)))
        counted = [i for i in a["issues"] if i.get("confidence") in ("High", "Medium")]
        a["_counts"] = Counter(i.get("severity") for i in counted)
        a["_lowconf"] = len(a["issues"]) - len(counted)
        a["_score"] = 10 * a["_counts"]["Critical"] + 4 * a["_counts"]["Major"] + a["_counts"]["Minor"]
        top = counted[0] if counted else (a["issues"][0] if a["issues"] else None)
        a["_top"] = f"{top.get('severity')} · {top.get('category')}: {top.get('explanation', '')}" if top else ""
        if a["risk"] == "Check manually":
            a["_top"] = "Text not readable: " + (a.get("extraction_note") or "extraction failed")
        elif a["risk"] == "Not processed":
            a["_top"] = "No result yet – run the triage for this article or review it manually"
    articles.sort(key=lambda a: (RISK_ORDER[a["risk"]], -a["_score"]))


def write_workbook(articles, out, mode):
    from openpyxl import Workbook

    st = _styles()
    wb = Workbook()
    ws = wb.active
    ws.title = "Triage"
    cols = [("Priority", 9), ("ID", 12), ("Risk", 15), ("Critical", 9), ("Major", 8), ("Minor", 8),
            ("Low-conf.", 9), ("Top issue", 50), ("Summary", 50), ("Title", 30), ("Source URL", 40),
            ("Target URL", 40), ("Locales", 14), ("Extraction", 22), ("Reviewer status", 22),
            ("Minutes spent", 10), ("Reviewer notes", 40)]
    header(ws, cols, st)
    for r, a in enumerate(articles, 2):
        c = a["_counts"]
        extraction = a.get("extraction", "") + (f" – {a['extraction_note']}" if a.get("extraction_note") else "")
        locales = f"{a.get('source_locale') or '?'} → {a.get('target_locale') or '?'}"
        values = [r - 1, a.get("id", ""), a["risk"], c["Critical"], c["Major"], c["Minor"], a["_lowconf"],
                  a["_top"], a.get("summary", ""), a.get("title", ""), None, None, locales, extraction,
                  "To review", None, ""]
        for col, v in enumerate(values, 1):
            put(ws, r, col, v, st["wrap"] if col in (8, 9, 10, 14, 17) else st["top"])
        link(ws.cell(row=r, column=11), a.get("source_url"), st)
        link(ws.cell(row=r, column=12), a.get("target_url"), st)
        ws.cell(row=r, column=3).fill = st["fill"](a["risk"])
        ws.cell(row=r, column=3).font = st["Font"](bold=True)
    last = max(len(articles) + 1, 2)
    ws.auto_filter.ref = f"A1:Q{last}"
    dropdown(ws, STATUS_CHOICES, f"O2:O{last}")
    from openpyxl.worksheet.datavalidation import DataValidation
    minutes = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
    ws.add_data_validation(minutes)
    minutes.add(f"P2:P{last}")

    wi = wb.create_sheet("Issues")
    icols = [("ID", 12), ("Article risk", 14), ("Severity", 10), ("Category", 14), ("Confidence", 11),
             ("Source quote", 45), ("Target quote", 45), ("Explanation", 50), ("Reviewer verdict", 20),
             ("Reviewer comment", 35)]
    header(wi, icols, st)
    r = 2
    for a in articles:
        for i in a["issues"]:
            vals = [a.get("id", ""), a["risk"], i.get("severity"), i.get("category"), i.get("confidence"),
                    i.get("source", ""), i.get("target", ""), i.get("explanation", ""), "", ""]
            for col, v in enumerate(vals, 1):
                put(wi, r, col, v, st["wrap"] if col in (6, 7, 8, 10) else st["top"])
            wi.cell(row=r, column=2).fill = st["fill"](a["risk"])
            r += 1
    wi.auto_filter.ref = f"A1:J{max(r - 1, 2)}"
    dropdown(wi, VERDICT_CHOICES, f"I2:I{max(r - 1, 2)}")

    wa = wb.create_sheet("About")
    totals = Counter(a["risk"] for a in articles)
    cats = Counter(i.get("category") for a in articles for i in a["issues"])
    rows = [
        ("Localization QA triage report", ""),
        ("Generated", dt.datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Mode", "Generic (no client style guide or glossary)" if mode == "generic" else "Client assets applied"),
        ("Articles", len(articles)),
    ] + [(k, totals[k]) for k in RISK_ORDER if totals[k] or k != "Not processed"] + [
        ("", ""),
        ("Rating rule", RULE_TEXT),
        ("Purpose", "Prioritises human review. It is not a full LQA; a reviewer makes the final call."),
        ("Calibration", "Fill in 'Reviewer status' and 'Minutes spent' (Triage) and 'Reviewer verdict' "
                        "(Issues). The pilot metrics below update as you go."),
        ("", ""),
    ]
    for r, (k, v) in enumerate(rows, 1):
        put(wa, r, 1, k).font = st["Font"](bold=True)
        put(wa, r, 2, v, st["wrap"])
    wa["A1"].font = st["Font"](bold=True, size=14)

    # Pilot metrics: live formulas over the reviewer columns.
    r = len(rows) + 1
    put(wa, r, 1, "Pilot metrics").font = st["Font"](bold=True, size=12)
    r += 1
    for col, name in enumerate(["Tier", "Articles", "Reviewed", "Issues confirmed", "Confirmed rate",
                                "Avg minutes"], 1):
        put(wa, r, col, name).font = st["Font"](bold=True)
    for tier in RISK_ORDER:
        r += 1
        t = f'"{tier}"'
        put(wa, r, 1, tier).fill = st["fill"](tier)
        wa.cell(row=r, column=2, value=f"=COUNTIF(Triage!C:C,{t})")
        wa.cell(row=r, column=3, value=f'=COUNTIFS(Triage!C:C,{t},Triage!O:O,"Reviewed*")')
        wa.cell(row=r, column=4, value=f'=COUNTIFS(Triage!C:C,{t},Triage!O:O,"{STATUS_CHOICES[1]}")')
        wa.cell(row=r, column=5, value=f'=IF(C{r}=0,"",D{r}/C{r})').number_format = "0%"
        wa.cell(row=r, column=6, value=f'=IFERROR(AVERAGEIFS(Triage!P:P,Triage!C:C,{t}),"")').number_format = "0.0"
    r += 2
    put(wa, r, 1, "Flag precision").font = st["Font"](bold=True)
    wa.cell(row=r, column=2, value='=IFERROR(COUNTIF(Issues!I:I,"Valid*")/(COUNTIF(Issues!I:I,"Valid*")'
                                   '+COUNTIF(Issues!I:I,"Not an issue")),"")').number_format = "0%"
    put(wa, r, 3, "share of reviewed flags that were real issues", st["wrap"])

    r += 2
    put(wa, r, 1, "Issues by category").font = st["Font"](bold=True)
    for k, v in cats.most_common():
        r += 1
        put(wa, r, 1, k)
        put(wa, r, 2, v)
    wa.column_dimensions["A"].width = 22
    wa.column_dimensions["B"].width = 60
    for letter in "CDEF":
        wa.column_dimensions[letter].width = 16
    wb.save(out)
    return totals


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="+", help=".jsonl / .json files or folders")
    ap.add_argument("--out", default="triage_report.xlsx")
    ap.add_argument("--batch", help="batch.jsonl from batch.py init: list articles with no result")
    ap.add_argument("--mode", default="generic", choices=["generic", "client-assets"])
    args = ap.parse_args()

    articles, warnings = load_results(args.results)
    for w in warnings:
        print("WARNING:", w, file=sys.stderr)
    problems = normalise(articles)
    if problems:
        print("Fix these values in the results file, then run again:", file=sys.stderr)
        for p in problems:
            print("  -", p, file=sys.stderr)
        sys.exit(2)

    if args.batch:
        fields = ("title", "source_url", "target_url", "source_locale", "target_locale")
        batch_items = {str(i.get("id")): i for i in load_batch(args.batch)}
        for a in articles:              # fill gaps (e.g. the spreadsheet's title) from the batch
            item = batch_items.get(str(a.get("id")), {})
            for k in fields:
                if not a.get(k) and item.get(k):
                    a[k] = item[k]
        done = {str(a.get("id")) for a in articles}
        for aid, item in batch_items.items():
            if aid not in done:
                articles.append({"id": item.get("id"), **{k: item.get(k) for k in fields},
                                 "risk": "Not processed", "_not_processed": True,
                                 "extraction": "", "issues": [], "summary": ""})

    prepare(articles)
    totals = write_workbook(articles, args.out, args.mode)
    print(f"Wrote {args.out}: {len(articles)} articles - " +
          ", ".join(f"{k} {totals[k]}" for k in RISK_ORDER if totals[k]))


if __name__ == "__main__":
    main()
