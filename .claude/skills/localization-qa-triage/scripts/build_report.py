#!/usr/bin/env python3
"""Build the triage spreadsheet from results.json.

Usage:
    python build_report.py results.json --out triage_report.xlsx [--mode generic|client-assets]

Computes each article's risk rating from its issues (same rule as SKILL.md), sorts
High -> Check manually -> Medium -> Low, and writes three sheets:
  Triage  one row per article, with reviewer status/notes columns
  Issues  one row per issue, with a reviewer verdict column (for calibration)
  About   method, rating rule and totals
"""
import argparse
import datetime as dt
import json
import sys
from collections import Counter

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

SEV_ORDER = {"Critical": 0, "Major": 1, "Minor": 2}
RISK_ORDER = {"High": 0, "Check manually": 1, "Medium": 2, "Low": 3}
RISK_FILL = {
    "High": "F4C7C3", "Check manually": "E1D5F0", "Medium": "FCE8B2", "Low": "D9EAD3",
}
HEADER_FILL = PatternFill("solid", fgColor="2F3B52")
HEADER_FONT = Font(bold=True, color="FFFFFF")
WRAP = Alignment(wrap_text=True, vertical="top")
TOP = Alignment(vertical="top")

VALID = {
    "category": {"Accuracy", "Omission", "Addition", "Numbers", "Untranslated", "Terminology",
                 "Fluency", "Locale", "Rendering", "Cultural"},
    "severity": set(SEV_ORDER),
    "confidence": {"High", "Medium", "Low"},
}


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


def check(articles):
    warnings = []
    for a in articles:
        for n, i in enumerate(a.get("issues", []), 1):
            for field, allowed in VALID.items():
                if i.get(field) not in allowed:
                    warnings.append(f"{a.get('id')}: issue {n} has {field}={i.get(field)!r}")
    return warnings


def header(ws, cols):
    for c, (name, width) in enumerate(cols, 1):
        cell = ws.cell(row=1, column=c, value=name)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 30


def link(cell, url):
    if url:
        cell.value = url
        cell.hyperlink = url
        cell.font = Font(color="1155CC", underline="single")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results")
    ap.add_argument("--out", default="triage_report.xlsx")
    ap.add_argument("--mode", default="generic", choices=["generic", "client-assets"])
    args = ap.parse_args()

    with open(args.results, encoding="utf-8") as f:
        articles = json.load(f)
    if not isinstance(articles, list):
        sys.exit("results.json must be a JSON array of article objects")

    for w in check(articles):
        print("WARNING:", w, file=sys.stderr)

    for a in articles:
        a["risk"] = rate(a)
        issues = sorted(a.get("issues", []), key=lambda i: (SEV_ORDER.get(i.get("severity"), 9),
                                                             {"High": 0, "Medium": 1}.get(i.get("confidence"), 2)))
        a["issues"] = issues
        counted = [i for i in issues if i.get("confidence") in ("High", "Medium")]
        a["_counts"] = Counter(i.get("severity") for i in counted)
        a["_lowconf"] = len(issues) - len(counted)
        a["_score"] = 10 * a["_counts"]["Critical"] + 4 * a["_counts"]["Major"] + a["_counts"]["Minor"]
        top = counted[0] if counted else (issues[0] if issues else None)
        a["_top"] = (f"{top.get('severity')} · {top.get('category')}: {top.get('explanation', '')}" if top else "")
        if a["risk"] == "Check manually":
            a["_top"] = "Text not readable: " + (a.get("extraction_note") or "extraction failed")

    articles.sort(key=lambda a: (RISK_ORDER[a["risk"]], -a["_score"]))

    wb = Workbook()
    ws = wb.active
    ws.title = "Triage"
    cols = [("Priority", 9), ("ID", 12), ("Risk", 15), ("Critical", 9), ("Major", 8), ("Minor", 8),
            ("Low-conf.", 9), ("Top issue", 50), ("Summary", 50), ("Title", 30), ("Source URL", 40),
            ("Target URL", 40), ("Locales", 14), ("Extraction", 22), ("Reviewer status", 20),
            ("Reviewer notes", 40)]
    header(ws, cols)
    for r, a in enumerate(articles, 2):
        c = a["_counts"]
        extraction = a.get("extraction", "ok") + (f" – {a['extraction_note']}" if a.get("extraction_note") else "")
        values = [r - 1, a.get("id", ""), a["risk"], c["Critical"], c["Major"], c["Minor"], a["_lowconf"],
                  a["_top"], a.get("summary", ""), a.get("title", ""), None, None,
                  f"{a.get('source_locale', '')} → {a.get('target_locale', '')}", extraction, "To review", ""]
        for col, v in enumerate(values, 1):
            cell = ws.cell(row=r, column=col, value=v)
            cell.alignment = WRAP if col in (8, 9, 10, 14, 16) else TOP
        link(ws.cell(row=r, column=11), a.get("source_url"))
        link(ws.cell(row=r, column=12), a.get("target_url"))
        ws.cell(row=r, column=3).fill = PatternFill("solid", fgColor=RISK_FILL[a["risk"]])
        ws.cell(row=r, column=3).font = Font(bold=True)
    last = len(articles) + 1
    ws.auto_filter.ref = f"A1:P{last}"
    dv = DataValidation(type="list", formula1='"To review,Reviewed – issues confirmed,Reviewed – no real issues,Skipped"',
                        allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"O2:O{max(last, 2)}")

    wi = wb.create_sheet("Issues")
    icols = [("ID", 12), ("Article risk", 14), ("Severity", 10), ("Category", 14), ("Confidence", 11),
             ("Source quote", 45), ("Target quote", 45), ("Explanation", 50), ("Reviewer verdict", 18),
             ("Reviewer comment", 35)]
    header(wi, icols)
    r = 2
    for a in articles:
        for i in a["issues"]:
            vals = [a.get("id", ""), a["risk"], i.get("severity"), i.get("category"), i.get("confidence"),
                    i.get("source", ""), i.get("target", ""), i.get("explanation", ""), "", ""]
            for col, v in enumerate(vals, 1):
                wi.cell(row=r, column=col, value=v).alignment = WRAP if col in (6, 7, 8, 10) else TOP
            wi.cell(row=r, column=2).fill = PatternFill("solid", fgColor=RISK_FILL[a["risk"]])
            r += 1
    wi.auto_filter.ref = f"A1:J{max(r - 1, 1)}"
    dv2 = DataValidation(type="list", formula1='"Valid,Valid – wrong severity,Not an issue,Unsure"', allow_blank=True)
    wi.add_data_validation(dv2)
    dv2.add(f"I2:I{max(r - 1, 2)}")

    wa = wb.create_sheet("About")
    totals = Counter(a["risk"] for a in articles)
    cats = Counter(i.get("category") for a in articles for i in a["issues"])
    about = [
        ("Localization QA triage report", ""),
        ("Generated", dt.datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Mode", "Generic (no client style guide or glossary)" if args.mode == "generic"
         else "Client assets applied"),
        ("Articles", len(articles)),
        ("High", totals["High"]), ("Check manually", totals["Check manually"]),
        ("Medium", totals["Medium"]), ("Low", totals["Low"]),
        ("", ""),
        ("Rating rule", "Counts issues with High/Medium confidence. High = any Critical or 2+ Major; "
                        "Medium = 1 Major or 3+ Minor; Low = otherwise; Check manually = text could not be read reliably."),
        ("Purpose", "Prioritises human review. It is not a full LQA; a reviewer makes the final call."),
        ("Calibration", "Fill in 'Reviewer status' (Triage) and 'Reviewer verdict' (Issues) so the "
                        "flag accuracy can be measured and the prompt improved."),
        ("", ""),
        ("Issues by category", ""),
    ] + [(k, v) for k, v in cats.most_common()]
    for r, (k, v) in enumerate(about, 1):
        wa.cell(row=r, column=1, value=k).font = Font(bold=True)
        wa.cell(row=r, column=2, value=v).alignment = WRAP
    wa["A1"].font = Font(bold=True, size=14)
    wa.column_dimensions["A"].width = 22
    wa.column_dimensions["B"].width = 90

    wb.save(args.out)
    print(f"Wrote {args.out}: {len(articles)} articles — " +
          ", ".join(f"{k} {totals[k]}" for k in RISK_ORDER if totals[k]))


if __name__ == "__main__":
    main()
