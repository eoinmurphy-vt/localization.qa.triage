import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".claude/skills/localization-qa-triage"
SCRIPTS = SKILL / "scripts"
FIX = ROOT / "tests/fixtures"
sys.path.insert(0, str(SCRIPTS))

import batch  # noqa: E402
import extract_text  # noqa: E402
import precheck  # noqa: E402


def run(*args, check=True):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", check=check)


def extract(tmp_path, name):
    out = tmp_path / f"{name}.txt"
    run(SCRIPTS / "extract_text.py", FIX / f"{name}.html", "--out", out)
    return out


def report_rows(path, sheet="Triage"):
    ws = openpyxl.load_workbook(path)[sheet]
    return [r for r in ws.iter_rows(min_row=2, values_only=True) if r[0] is not None]


# ---------------------------------------------------------------- extract_text

def test_extract_drops_boilerplate(tmp_path):
    text = extract(tmp_path, "src").read_text(encoding="utf-8")
    assert text.startswith("# How to set up Contoso Cloud backup")
    assert "cookies" not in text.lower()
    assert "Privacy" not in text


MODERN_PAGE = """<html><head><meta charset="windows-1252"></head><body>
<header class="site-header"><nav><a>Home</a><a>Pricing</a></nav></header>
<section class="hero-banner"><h1>Back up your files</h1></section>
<main><article>
 <header class="entry-header"><p class="byline">Updated in March</p></header>
 <div class="body-text">Backups run every night. Plans start at 4.99 per month.</div>
 <div class="section-header"><h2>How it works</h2></div>
 <p>Pick the folders<br>you want to protect.</p>
 <div class="share-bar">Share on social media</div>
 <div class="cta"><a href="/start">Start your free trial</a></div>
 <p>Caf\xe9 owners love it.</p>
</article></main>
<footer>Legal | Privacy</footer></body></html>"""


def test_extract_keeps_title_div_text_and_cta(tmp_path):
    page = tmp_path / "modern.html"
    page.write_bytes(MODERN_PAGE.encode("cp1252"))
    text, status = extract_text.extract(str(page))
    lines = text.splitlines()
    assert lines[0] == "# Back up your files"               # h1 outside <main> is kept as title
    assert "Backups run every night. Plans start at 4.99 per month." in lines
    assert "## How it works" in lines                      # heading inside a "header" div
    assert "Pick the folders you want to protect." in lines
    assert "Start your free trial" in lines                # CTA link text
    assert "Café owners love it." in lines                 # charset from <meta>
    assert "Updated in March" in lines                     # <header> inside the article is content
    assert "Share on social media" not in text
    assert "Pricing" not in text and "Privacy" not in text
    assert status["status"] == "suspect" and "short text" in status["notes"][0]


def test_extract_reports_unreadable_source(tmp_path):
    res = run(SCRIPTS / "extract_text.py", tmp_path / "missing.html", check=False)
    assert res.returncode == 1
    assert json.loads(res.stderr.strip().splitlines()[-1])["status"] == "failed"


def test_word_count_handles_scripts_without_spaces():
    assert extract_text.word_count("これは日本語の文章です。" * 40) >= 200


@pytest.mark.parametrize("final,note,suspect", [
    ("https://x.com/de-de/kb/a/", False, False),          # trailing slash only
    ("https://x.com/de-de/kb/anleitung", True, False),    # localized slug: note, not suspect
    ("https://x.com/en-us/kb/a", True, True),             # fell back to another locale
    ("https://x.com/de-de/", True, True),                 # bounced to the home page
    ("https://other.com/de-de/kb/a", True, True),         # different site
])
def test_redirects(final, note, suspect):
    got_note, got_suspect = extract_text.redirect_note("https://x.com/de-de/kb/a", final)
    assert (got_note is not None, got_suspect) == (note, suspect)


# ---------------------------------------------------------------- precheck

def test_precheck_signals(tmp_path):
    src, tgt = extract(tmp_path, "src"), extract(tmp_path, "tgt")
    res = json.loads(run(SCRIPTS / "precheck.py", src, tgt, "--source-locale", "en-US",
                         "--target-locale", "de-DE", "--json").stdout)
    missing = {m["number"] for m in res["missing_numbers"]}
    assert missing == {"24"}                      # 9.99 vs 9,99 and 1,000 vs 1.000 must match
    assert {m["number"] for m in res["extra_numbers"]} == {"12"}
    assert res["missing_urls_or_emails"] == []    # trailing period must not cause a false miss
    assert "Before you start" in res["identical_segments"]
    assert "You need version 3.2 or later." in res["identical_segments"]
    assert any("list_items" in d for d in res["structure_differences"])


@pytest.mark.parametrize("token,dec,expected", [
    ("1,500", ".", ["1500"]), ("1,500", ",", ["1.5"]), ("1.500", ",", ["1500"]),
    ("9,99", ",", ["9.99"]), ("1.000,50", ",", ["1000.5"]), ("1,000.50", ".", ["1000.5"]),
    ("31.12.2026", ",", ["31", "12", "2026"]), ("3.2.1", ".", ["3", "2", "1"]),
    ("1,00,000", ".", ["100000"]), ("5 000", ",", ["5000"]), ("0,012", ",", ["0.012"]),
    ("2024 100", ".", ["2024", "100"]), ("١٢٣٫٥", ".", ["123.5"]),
    ("१२३", None, ["123"]),
])
def test_number_parsing(token, dec, expected):
    assert precheck.parse_number(token, dec) == expected


def test_precheck_numbers_by_value_not_digits():
    src = "The fee is 1.5% and the limit is 100,000. Offer ends 12/31/2026."
    tgt_ok = "Die Gebühr beträgt 1,5 % und das Limit liegt bei 100.000. Angebot endet am 31.12.2026."
    tgt_bad = "Die Gebühr beträgt 15 % und das Limit liegt bei 100.000. Angebot endet am 31.12.2026."
    ok = precheck.run(src, tgt_ok, "en-US", "de-DE")
    assert ok["missing_numbers"] == [] and ok["extra_numbers"] == []
    bad = precheck.run(src, tgt_bad, "en-US", "de-DE")
    assert [m["number"] for m in bad["missing_numbers"]] == ["1.5"]
    assert [m["number"] for m in bad["extra_numbers"]] == ["15"]


def test_precheck_native_digits():
    src = "Send up to 100,000 and pay 2.5%."
    tgt = "अधिकतम १,००,००० भेजें, २.५% दें।"
    res = precheck.run(src, tgt, "en-US", "hi-IN")
    assert res["missing_numbers"] == [] and res["extra_numbers"] == []


def test_precheck_rendering_signals():
    res = precheck.run("Hello {name}, welcome.", "Hallo {name}, willkommen. Grüße â€™ {0} &amp;", "en", "de")
    kinds = {r["kind"] for r in res["rendering"]}
    assert kinds == {"placeholder", "garbled characters", "html entity"}
    assert all(r["text"] != "{name}" for r in res["rendering"])   # also in source


def test_precheck_cli_prints_non_latin_text(tmp_path):
    s, t = tmp_path / "s.txt", tmp_path / "t.txt"
    s.write_text("Pay 25 now.\n", encoding="utf-8")
    t.write_text("ادفع 26 الآن.\n", encoding="utf-8")
    out = run(SCRIPTS / "precheck.py", s, t, "--target-locale", "ar").stdout
    assert "Number in target not in source: 26" in out


# ---------------------------------------------------------------- build_report

def test_report_order_and_ratings(tmp_path):
    out = tmp_path / "report.xlsx"
    run(SCRIPTS / "build_report.py", FIX / "results.json", "--out", out)
    rows = [(r[1], r[2]) for r in report_rows(out)]
    assert rows == [("Row 2", "High"), ("Row 5", "Check manually"), ("Row 3", "Medium"),
                    ("Row 4", "Low"), ("Row 6", "Low")]


def _issue(**kw):
    return {"category": "Accuracy", "severity": "Major", "confidence": "High",
            "source": "s", "target": "t", "explanation": "e", **kw}


def test_report_normalises_case_instead_of_underrating(tmp_path):
    res = tmp_path / "results.jsonl"
    res.write_text(json.dumps({"id": "A", "issues": [
        _issue(category="accuracy", severity="critical", confidence="high")]}) + "\n", encoding="utf-8")
    out = tmp_path / "r.xlsx"
    run(SCRIPTS / "build_report.py", res, "--out", out)
    assert report_rows(out)[0][2] == "High"


def test_report_stops_on_unknown_values(tmp_path):
    res = tmp_path / "results.jsonl"
    res.write_text(json.dumps({"id": "A", "issues": [_issue(severity="High")]}) + "\n", encoding="utf-8")
    proc = run(SCRIPTS / "build_report.py", res, "--out", tmp_path / "r.xlsx", check=False)
    assert proc.returncode == 2 and "severity='High'" in proc.stderr


def test_report_merges_folders_dedupes_and_lists_unprocessed(tmp_path):
    chunks = tmp_path / "results"
    chunks.mkdir()
    (chunks / "chunk-01.jsonl").write_text(
        json.dumps({"id": "Row 2", "issues": []}) + "\n"
        + json.dumps({"id": "Row 3", "issues": [_issue()]}) + "\n", encoding="utf-8")
    (chunks / "chunk-02.jsonl").write_text(          # Row 2 re-done: last one wins
        json.dumps({"id": "Row 2", "issues": [_issue(severity="Critical", source="=HYPERLINK(1)")]}) + "\n",
        encoding="utf-8")
    batch_file = tmp_path / "batch.jsonl"
    batch_file.write_text("".join(json.dumps({"id": i, "source_url": "https://e.com/en/a",
                                              "target_url": "https://e.com/de/a"}) + "\n"
                                  for i in ("Row 2", "Row 3", "Row 4")), encoding="utf-8")
    out = tmp_path / "r.xlsx"
    proc = run(SCRIPTS / "build_report.py", chunks, "--batch", batch_file, "--out", out)
    assert "more than once" in proc.stderr
    assert [(r[1], r[2]) for r in report_rows(out)] == [
        ("Row 2", "High"), ("Row 3", "Medium"), ("Row 4", "Not processed")]
    quote = openpyxl.load_workbook(out)["Issues"]["F2"]
    assert quote.value == "=HYPERLINK(1)" and quote.data_type == "s"   # page text never becomes a formula


# ---------------------------------------------------------------- batch

def test_guess_locale():
    assert batch.guess_locale("https://e.com/de-de/help/a") == "de-DE"
    assert batch.guess_locale("https://e.com/ca/fr/blog/a") == "fr-CA"
    assert batch.guess_locale("https://e.com/ja/a") == "ja"
    assert batch.guess_locale("https://fr.example.com/a") == "fr"
    assert batch.guess_locale("https://e.com/zh-hans/a") == "zh-Hans"
    assert batch.guess_locale("https://e.com/help/article-1") == ""


def test_batch_init_from_xlsx_with_hyperlinked_titles(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Article ID", "Title", "Source", "Target", "Reviewer"])
    ws.append(["A-1", "Backup", "https://e.com/en-us/backup", None, "Ana"])
    ws["D2"] = "Sicherung"
    ws["D2"].hyperlink = "https://e.com/de-de/backup"
    ws.append(["A-2", "Restore", "https://e.com/en-us/restore", "https://e.com/de-de/restore", "Ana"])
    ws.append(["A-3", "Draft", "https://e.com/en-us/draft", None, "Ana"])
    xlsx = tmp_path / "batch.xlsx"
    wb.save(xlsx)
    out = tmp_path / "b" / "batch.jsonl"
    proc = run(SCRIPTS / "batch.py", "init", xlsx, "--out", out)
    items = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert [(i["id"], i["target_url"], i["target_locale"]) for i in items] == [
        ("A-1", "https://e.com/de-de/backup", "de-DE"), ("A-2", "https://e.com/de-de/restore", "de-DE")]
    assert 'Source URL: C "Source"' in proc.stdout and "1 row(s) without both URLs skipped" in proc.stdout


def test_batch_init_csv_with_two_unlabelled_url_columns(tmp_path):
    csv_file = tmp_path / "pairs.csv"
    csv_file.write_text("Name;EN;Live page\nA;https://e.com/en/a;https://e.com/fr/a\n", encoding="utf-8")
    out = tmp_path / "batch.jsonl"
    run(SCRIPTS / "batch.py", "init", csv_file, "--out", out)
    item = json.loads(out.read_text(encoding="utf-8"))
    assert (item["id"], item["source_locale"], item["target_locale"]) == ("Row 2", "en", "fr")


def test_batch_fetch_and_status(tmp_path):
    batch_file = tmp_path / "batch.jsonl"
    # Saved HTML files stand in for URLs, so the test needs no network.
    items = [{"id": f"Row {n}", "key": f"Row_{n}", "source_url": str(FIX / "src.html"),
              "target_url": str(FIX / "tgt.html"), "source_locale": "en-US", "target_locale": "de-DE"}
             for n in (2, 3)]
    batch_file.write_text("".join(json.dumps(i) + "\n" for i in items), encoding="utf-8")
    texts = tmp_path / "texts"
    proc = run(SCRIPTS / "batch.py", "fetch", batch_file, "--texts", texts)
    assert "2 articles" in proc.stdout
    pre = (texts / "Row_2.precheck.txt").read_text(encoding="utf-8")
    assert "Number in source not found in target: 24" in pre
    results = tmp_path / "results.jsonl"
    results.write_text(json.dumps({"id": "Row 2", "issues": [_issue(severity="Critical")]}) + "\n",
                       encoding="utf-8")
    out = run(SCRIPTS / "batch.py", "status", batch_file, results, tmp_path / "none.jsonl").stdout
    assert out.splitlines()[0] == "1/2 done: High 1"
    assert "Remaining (1): Row 3" in out


# ---------------------------------------------------------------- skill package and prompt

RULE_LINES = [
    "- **High**: any Critical, or 2 or more Major",
    "- **Medium**: exactly 1 Major, or 3 or more Minor",
    "- **Low**: everything else",
    "- **Check manually**: extraction failed or the pair doesn't match",
]


def test_skill_frontmatter():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    fields = dict(line.split(": ", 1) for line in m.group(1).splitlines())
    assert set(fields) == {"name", "description"}
    assert fields["name"] == SKILL.name
    assert len(fields["description"]) <= 1024


@pytest.mark.parametrize("path", [SKILL / "SKILL.md", ROOT / "prompts/triage-prompt.md"])
def test_rating_rule_is_identical_everywhere(path):
    text = path.read_text(encoding="utf-8")
    for line in RULE_LINES:
        assert line in text, f"{path.name} is out of step with the rating rule"


def test_package(tmp_path):
    proc = run(ROOT / "tools/package.py")
    assert "Wrote dist/localization-qa-triage.zip" in proc.stdout
    with zipfile.ZipFile(ROOT / "dist/localization-qa-triage.zip") as z:
        names = z.namelist()
    assert "localization-qa-triage/SKILL.md" in names
    assert "localization-qa-triage/scripts/batch.py" in names
    assert not any("__pycache__" in n for n in names)
