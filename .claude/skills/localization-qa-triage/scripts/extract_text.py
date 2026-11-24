#!/usr/bin/env python3
"""Extract the main article text from a web page or a saved HTML file.

Usage:
    python extract_text.py <url-or-html-file> [--out article.txt]

Output is plain text with light structure so source and target can be compared:
    # Heading
    paragraph text
    - list item

Uses trafilatura if installed, otherwise BeautifulSoup with simple boilerplate removal.
A one-line JSON status is printed to stderr, e.g. {"status": "ok", "words": 812}.
status is "ok", "suspect" (short text or looks like a login/consent/error page) or "failed".
"""
import argparse
import json
import re
import sys
import urllib.request

BLOCK_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "figcaption",
              "blockquote", "th", "td", "dt", "dd", "summary"]
DROP_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside",
             "form", "svg", "iframe", "button", "template"]
BOILERPLATE_HINT = re.compile(
    r"cookie|consent|banner|breadcrumb|related|share|social|newsletter|subscribe|"
    r"footer|header|navbar|nav-|menu|sidebar|promo|advert|skip-link|feedback",
    re.I)
SUSPECT_PAGE = re.compile(
    r"access denied|page not found|404|sign in to continue|log in to continue|"
    r"enable javascript|accept (all )?cookies|are you a robot|captcha",
    re.I)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (localization-qa-triage)",
        "Accept-Language": "*",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def extract_trafilatura(html: str):
    try:
        import trafilatura
    except ImportError:
        return None
    text = trafilatura.extract(html, include_comments=False, include_tables=True,
                               output_format="markdown")
    return text


def extract_bs4(html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(DROP_TAGS):
        tag.decompose()
    for tag in soup.find_all(True):
        if tag.attrs is None:
            continue
        attrs = " ".join([tag.get("id") or "", " ".join(tag.get("class") or []),
                          tag.get("role") or ""])
        if attrs.strip() and BOILERPLATE_HINT.search(attrs) and tag.name not in ("html", "body", "main", "article"):
            tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    lines = []
    title = soup.find("h1")
    for el in root.find_all(BLOCK_TAGS):
        # keep only innermost blocks to avoid duplicating nested text
        if el.find(BLOCK_TAGS):
            continue
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text:
            continue
        if el.name.startswith("h"):
            lines.append("#" * int(el.name[1]) + " " + text)
        elif el.name == "li":
            lines.append("- " + text)
        else:
            lines.append(text)
    if title is not None and root is not soup and title not in root.find_all("h1"):
        lines.insert(0, "# " + " ".join(title.get_text(" ", strip=True).split()))
    # drop exact consecutive duplicates
    out = []
    for line in lines:
        if not out or out[-1] != line:
            out.append(line)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="URL or path to a saved .html file")
    ap.add_argument("--out", help="write text here (default: stdout)")
    args = ap.parse_args()

    try:
        if re.match(r"https?://", args.src):
            html = fetch(args.src)
        else:
            with open(args.src, encoding="utf-8", errors="replace") as f:
                html = f.read()
    except Exception as e:  # network blocked, 403, missing file...
        print(json.dumps({"status": "failed", "error": str(e)[:200]}), file=sys.stderr)
        sys.exit(1)

    text = extract_trafilatura(html) or extract_bs4(html)
    words = len(text.split())
    status = "ok"
    reasons = []
    if words < 150:
        status, _ = "suspect", reasons.append("short text (%d words)" % words)
    if SUSPECT_PAGE.search(text[:1500]) and words < 400:
        status, _ = "suspect", reasons.append("looks like an error, login or consent page")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    print(json.dumps({"status": status, "words": words, "notes": reasons}), file=sys.stderr)


if __name__ == "__main__":
    main()
