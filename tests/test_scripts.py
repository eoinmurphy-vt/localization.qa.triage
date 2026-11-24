import json
import subprocess
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".claude/skills/localization-qa-triage/scripts"
FIX = ROOT / "tests/fixtures"


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, check=True)


def extract(tmp_path, name):
    out = tmp_path / f"{name}.txt"
    run(SCRIPTS / "extract_text.py", FIX / f"{name}.html", "--out", out)
    return out


def test_extract_drops_boilerplate(tmp_path):
    text = extract(tmp_path, "src").read_text()
    assert text.startswith("# How to set up Contoso Cloud backup")
    assert "cookies" not in text.lower()
    assert "Privacy" not in text


def test_precheck_signals(tmp_path):
    src, tgt = extract(tmp_path, "src"), extract(tmp_path, "tgt")
    res = json.loads(run(SCRIPTS / "precheck.py", src, tgt, "--target-locale", "de-DE", "--json").stdout)
    missing = {m["number"] for m in res["missing_numbers"]}
    assert missing == {"24"}                      # 9.99 vs 9,99 and 1,000 vs 1.000 must match
    assert {m["number"] for m in res["extra_numbers"]} == {"12"}
    assert res["missing_urls_or_emails"] == []    # trailing period must not cause a false miss
    assert "Before you start" in res["identical_segments"]
    assert "You need version 3.2 or later." in res["identical_segments"]
    assert any("list_items" in d for d in res["structure_differences"])


def test_report_order_and_ratings(tmp_path):
    out = tmp_path / "report.xlsx"
    run(SCRIPTS / "build_report.py", FIX / "results.json", "--out", out)
    ws = openpyxl.load_workbook(out)["Triage"]
    rows = [(r[1], r[2]) for r in ws.iter_rows(min_row=2, values_only=True) if r[0]]
    assert rows == [("Row 2", "High"), ("Row 5", "Check manually"), ("Row 3", "Medium"),
                    ("Row 4", "Low"), ("Row 6", "Low")]
