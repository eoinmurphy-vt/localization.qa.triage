#!/usr/bin/env python3
"""Extract the main article text from a web page or a saved HTML file.

Usage:
    python extract_text.py <url-or-html-file> [--out article.txt] [--engine bs4|trafilatura]

Output is plain text with light structure so source and target can be compared:
    # Heading
    paragraph text
    - list item

The default engine (BeautifulSoup) keeps the title, headings, body text, tables, callouts and
button/CTA text, and drops page furniture (navigation, cookie banners, share bars, site header
and footer). Source and target pages share a template, so whatever is dropped is dropped on
both sides. --engine trafilatura is available if that package is installed.

A one-line JSON status is printed to stderr, e.g.
    {"status": "ok", "words": 812, "notes": [], "final_url": "https://..."}
status is "ok", "suspect" (short text, looks like an error/login/consent/bot-check page, or
the URL redirected to a different page) or "failed" (could not fetch or read; exit code 1).
"""
import argparse
import codecs
import json
import re
import sys
import urllib.parse
import urllib.request

HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
# Text inside these tags joins the surrounding line; any other tag starts a new line.
INLINE = {"a", "abbr", "b", "bdi", "bdo", "cite", "code", "data", "del", "dfn", "em", "font",
          "i", "ins", "kbd", "label", "mark", "q", "s", "samp", "small", "span", "strong",
          "sub", "sup", "time", "u", "var"}
LINE_BOUNDARY = {"ul", "ol", "table", "article", "main", "section", "body"}
ALWAYS_DROP = ["script", "style", "noscript", "template", "svg", "iframe", "canvas", "video",
               "audio", "object", "select", "input", "textarea", "dialog"]
# Page furniture, dropped wherever it is (unless it holds the article).
CHROME_HINT = re.compile(
    r"cookie|consent|gdpr|onetrust|breadcrumb|share|social|newsletter|subscribe|skip-?link|"
    r"skip-?to|navbar|advert|(?:language|locale|lang)-?(?:selector|switch|picker)|related|"
    r"recommended|feedback|modal|popup", re.I)
CHROME_ROLES = {"navigation", "search", "dialog", "alertdialog"}
CHROME_TAGS = {"nav"}
# Site header/footer/sidebars, dropped only outside <article>/<main>: inside the article these
# names often wrap the title, a callout or a disclaimer.
OUTER_HINT = re.compile(r"header|footer|masthead|menu|sidebar|promo|banner|toolbar|(?:^|[\s_-])nav", re.I)
OUTER_ROLES = {"banner", "contentinfo", "complementary"}
OUTER_TAGS = {"header", "footer", "aside", "form"}

SUSPECT_PAGE = re.compile(
    r"access denied|forbidden|page not found|\b404\b|sign in to continue|log in to continue|"
    r"enable javascript|accept (all )?cookies|are you a robot|captcha|just a moment|"
    r"checking your browser|attention required|verify you are human",
    re.I)
NO_SPACE_SCRIPT = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿"
                             r"฀-໿က-႟ក-៿]")
MIN_WORDS = 100


def fetch(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; localization-qa-triage)",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read(), resp.headers.get_content_charset(), resp.geturl()


def decode(raw: bytes, header_charset=None) -> str:
    """Decode HTML bytes: BOM, then HTTP charset, then <meta charset>, then UTF-8."""
    if raw.startswith(codecs.BOM_UTF8):
        return raw[3:].decode("utf-8", errors="replace")
    meta = re.search(rb"""<meta[^>]+charset\s*=\s*["']?([\w.:-]+)""", raw[:4096], re.I)
    candidates = [c for c in (header_charset, meta and meta.group(1).decode("ascii", "ignore"), "utf-8") if c]
    for enc in candidates:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    for enc in candidates:
        try:
            return raw.decode(enc, errors="replace")
        except LookupError:
            continue
    return raw.decode("utf-8", errors="replace")


def word_count(text: str) -> int:
    """Whitespace words, counting runs of Chinese/Japanese/Thai etc. as ~2 characters per word."""
    n = 0
    for tok in text.split():
        k = len(NO_SPACE_SCRIPT.findall(tok))
        n += max(1, k // 2) if k else 1
    return n


def _locale_segments(path: str):
    segs = [s for s in path.lower().split("/") if s][:3]
    return [s for s in segs if re.fullmatch(r"[a-z]{2,3}(?:[-_][a-z0-9]{2,4})?", s)]


def redirect_note(requested: str, final: str):
    """Return (note, is_suspect) when the fetched URL ended somewhere else.

    A localized slug (/de/kb/how-to -> /de/kb/anleitung) is normal. A different site, a
    different locale segment, or a bounce to a home/section page is suspect."""
    if not final or final == requested:
        return None, False
    a, b = urllib.parse.urlsplit(requested), urllib.parse.urlsplit(final)
    if a.path.rstrip("/").lower() == b.path.rstrip("/").lower() and a.netloc.lower() == b.netloc.lower():
        return None, False
    host = lambda u: u.netloc.lower().removeprefix("www.")  # noqa: E731
    suspect = (host(a) != host(b)
               or _locale_segments(a.path) != _locale_segments(b.path)
               or len([s for s in b.path.split("/") if s]) < min(2, len([s for s in a.path.split("/") if s])))
    return f"redirected to {final}", suspect


def extract_trafilatura(html: str):
    try:
        import trafilatura
    except ImportError:
        return None
    try:
        return trafilatura.extract(html, include_comments=False, include_tables=True,
                                   output_format="markdown")
    except (TypeError, ValueError):  # older trafilatura without markdown output
        return trafilatura.extract(html, include_comments=False, include_tables=True)


def _attrs(tag) -> str:
    return " ".join([tag.get("id") or "", " ".join(tag.get("class") or [])])


def _holds_article(tag, protected) -> bool:
    return any(p is tag for el in protected for p in el.parents)


def _inside_article(tag) -> bool:
    return any(p.name in ("article", "main") or p.get("role") == "main" for p in tag.parents)


def _title_h1(soup):
    for h1 in soup.find_all("h1"):
        if _inside_article(h1):
            return h1
    return soup.find("h1")


def _pick_root(soup, h1):
    if h1 is not None:
        for p in h1.parents:
            if p.name in ("article", "main") or p.get("role") == "main":
                return p
    main = soup.find("main") or soup.find(attrs={"role": "main"})
    if main is not None:
        return main
    articles = soup.find_all("article")
    if articles:
        return max(articles, key=lambda a: len(a.get_text()))
    return soup.body or soup


def _prefix(el, root) -> str:
    for p in [el, *el.parents]:
        if p.name in HEADINGS:
            return "#" * int(p.name[1]) + " "
        if p.name == "li":
            return "- "
        if p is root or p.name in LINE_BOUNDARY:
            break
    return ""


def extract_bs4(html: str) -> str:
    from bs4 import BeautifulSoup
    from bs4.element import PreformattedString

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(ALWAYS_DROP):
        tag.decompose()

    h1 = _title_h1(soup)
    root = _pick_root(soup, h1)
    protected = [el for el in (h1, root) if el is not None]
    root_is_body = root is (soup.body or soup)
    root_len = len(root.get_text())
    for tag in soup.find_all(True):
        if getattr(tag, "decomposed", False) or tag is root or tag.name in ("html", "body"):
            continue
        role = (tag.get("role") or "").lower()
        attrs = _attrs(tag)
        chrome = tag.name in CHROME_TAGS or role in CHROME_ROLES or bool(attrs and CHROME_HINT.search(attrs))
        outer = (tag.name in OUTER_TAGS or role in OUTER_ROLES or bool(attrs and OUTER_HINT.search(attrs)))
        if not (chrome or (outer and not _inside_article(tag))):
            continue
        if tag is h1 or _holds_article(tag, protected):
            continue
        # With no <main>/<article> to anchor on, never drop a wrapper that holds most of the page.
        if root_is_body and len(tag.get_text()) > 0.5 * root_len:
            continue
        tag.decompose()

    for br in root.find_all("br"):
        br.replace_with("\n")

    pieces = []  # [container, text]
    current = None
    for s in root.find_all(string=True):
        if isinstance(s, PreformattedString):  # comments, doctype, CDATA
            continue
        container = s.parent
        while container is not root and container.name in INLINE:
            container = container.parent
        if container is not current:
            pieces.append([container, ""])
            current = container
        pieces[-1][1] += str(s)

    lines = []
    for container, text in pieces:
        text = " ".join(text.split())
        if text:
            lines.append(_prefix(container, root) + text)
    if h1 is not None and not any(p is root for p in h1.parents):
        lines.insert(0, "# " + " ".join(h1.get_text(" ", strip=True).split()))
    out = []
    for line in lines:  # drop exact consecutive duplicates (responsive copies of the same block)
        if not out or out[-1] != line:
            out.append(line)
    return "\n".join(out)


def extract(src: str, engine: str = "bs4"):
    """Return (text, status) for a URL or a saved HTML file. Never raises."""
    status = {"status": "ok", "words": 0, "notes": [], "engine": engine}
    try:
        if re.match(r"https?://", src):
            raw, charset, final = fetch(src)
            status["final_url"] = final
            note, suspect = redirect_note(src, final)
            if note:
                status["notes"].append(note)
                if suspect:
                    status["status"] = "suspect"
        else:
            with open(src, "rb") as f:
                raw, charset = f.read(), None
        html = decode(raw, charset)
        text = None
        if engine == "trafilatura":
            text = extract_trafilatura(html)
            if text is None:
                status["notes"].append("trafilatura unavailable or found nothing; used bs4")
                status["engine"] = "bs4"
        if text is None:
            text = extract_bs4(html)
    except Exception as e:  # network blocked, 403, missing file, parser error...
        status.update(status="failed", error=f"{type(e).__name__}: {e}"[:200])
        return "", status

    words = word_count(text)
    status["words"] = words
    if words < MIN_WORDS:
        status["status"] = "suspect"
        status["notes"].append(f"short text ({words} words)")
    if SUSPECT_PAGE.search(text[:1500]) and words < 400:
        status["status"] = "suspect"
        status["notes"].append("looks like an error, login, consent or bot-check page")
    return text, status


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="URL or path to a saved .html file")
    ap.add_argument("--out", help="write text here (default: stdout)")
    ap.add_argument("--engine", choices=["bs4", "trafilatura"], default="bs4")
    args = ap.parse_args()

    text, status = extract(args.src, args.engine)
    if status["status"] != "failed":
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        else:
            print(text)
    print(json.dumps(status, ensure_ascii=False), file=sys.stderr)
    sys.exit(1 if status["status"] == "failed" else 0)


if __name__ == "__main__":
    main()
