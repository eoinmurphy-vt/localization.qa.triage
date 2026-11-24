#!/usr/bin/env python3
"""Objective pre-checks for a source/target article pair.

Usage:
    python precheck.py source.txt target.txt [--source-locale en-US] [--target-locale de-DE] [--json]

Reports SIGNALS for Claude to verify (not confirmed issues):
  - numbers in the source missing from the target, and numbers only in the target
    (locale-aware: 1,234.5 == 1.234,5 and native digits such as ১২৩ == 123, but 1.5 != 15)
  - URLs / email addresses in the source missing from the target
  - long source segments copied unchanged into the target (possibly untranslated)
  - placeholders, markup or garbled characters in the target that the source doesn't have
  - text length ratio and heading / paragraph / list-item count differences
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import Counter

URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# A number: digits joined by . , ' ’ or Arabic separators, or by a space-type separator
# that is followed by exactly three digits (5 000, 5 000).
NUM_RE = re.compile(r"\d+(?:(?:[.,'’٫٬]|[    ](?=\d{3}(?!\d)))\d+)*")
GROUP_SEPS = set("    '’٬")
ARABIC_DECIMAL = "٫"
SENT_SPLIT = re.compile(r"(?<=[.!?。！？])\s+|\n+")
WORD_RE = re.compile(r"\w+", re.U)
CJK_LOCALES = ("zh", "ja", "ko")

# Languages that write decimals with a comma (1,5). Everything else is assumed to use a point.
COMMA_DECIMAL_LANGS = {
    "af", "az", "be", "bg", "bs", "ca", "cs", "da", "de", "el", "es", "et", "eu", "fi", "fr",
    "gl", "hr", "hu", "id", "is", "it", "kk", "lt", "lv", "mk", "nb", "nl", "nn", "no", "pl",
    "pt", "ro", "ru", "sk", "sl", "sq", "sr", "sv", "tr", "uk", "vi",
}
POINT_DECIMAL_LOCALES = {"es-mx", "es-us", "es-419", "de-ch", "de-li", "it-ch"}
COMMA_DECIMAL_LOCALES = {"en-za"}

RENDERING_PATTERNS = [
    ("placeholder", re.compile(r"\{\{[^{}\n]{1,40}\}\}|\$\{[^}\n]{1,40}\}|\{\d+\}|"
                               r"\{[A-Za-z_][\w.]{0,30}\}|%(?:\d\$)?[sd@]\b|\[\[[^\]\n]{1,60}\]\]")),
    ("markup", re.compile(r"</?(?:p|div|span|br|a|strong|em|b|i|li|ul|ol|h[1-6])(?:\s[^<>\n]*)?/?>", re.I)),
    ("html entity", re.compile(r"&(?:[a-z]{2,8}|#\d{2,5});", re.I)),
    ("garbled characters", re.compile(r"[Â-ô][\u0080-¿]|â€|�")),
]


def decimal_sep(locale: str):
    loc = (locale or "").strip().lower().replace("_", "-")
    if not loc:
        return None
    if loc in POINT_DECIMAL_LOCALES:
        return "."
    if loc in COMMA_DECIMAL_LOCALES:
        return ","
    return "," if loc.split("-")[0] in COMMA_DECIMAL_LANGS else "."


def ascii_digits(s: str) -> str:
    """Map native digits (Arabic-Indic, Devanagari, Thai, full-width...) to 0-9."""
    return "".join(str(unicodedata.decimal(ch)) if ch.isdecimal() and not ch.isascii() else ch
                   for ch in s)


def _canon(int_part: str, frac: str = "") -> str:
    i = int_part.lstrip("0") or "0"
    f = frac.rstrip("0")
    return f"{i}.{f}" if f else i


def _valid_grouping(groups, lakh_ok=False) -> bool:
    if not 1 <= len(groups[0]) <= 3:
        return False
    if all(len(g) == 3 for g in groups[1:]):
        return True
    # Indian lakh/crore grouping: 1,00,000 / 12,34,56,789
    return (lakh_ok and len(groups[0]) <= 2 and len(groups[-1]) == 3
            and all(len(g) == 2 for g in groups[1:-1]))


def parse_number(token: str, dec=None):
    """Return canonical value(s) for a number token, e.g. '1.000,50' (dec=',') -> ['1000.5'].

    Tokens that are not a single number (dates like 31.12.2026, versions like 3.2.1) are
    split into their parts, so 31.12.2026 and 12/31/2026 compare equal."""
    token = ascii_digits(token)
    parts = re.split(r"([^0-9])", token)
    groups, seps = parts[0::2], parts[1::2]
    if not seps:
        return [_canon(groups[0])]
    kinds = ["g" if s in GROUP_SEPS else "d" if s == ARABIC_DECIMAL else s for s in seps]
    marks = {k for k in kinds if k in ".,"}

    if "d" in kinds:                                   # Arabic decimal separator
        if kinds[-1] == "d" and kinds.count("d") == 1:
            return [_canon("".join(groups[:-1]), groups[-1])]
    elif len(marks) == 2:                              # 1,000.50 / 1.000,50
        last = kinds[-1]
        if last in ".," and last not in kinds[:-1] and _valid_grouping(groups[:-1]):
            return [_canon("".join(groups[:-1]), groups[-1])]
    elif len(marks) == 1:
        mark = marks.pop()
        if kinds.count(mark) == 1 and kinds[-1] == mark:
            ints, tail = groups[:-1], groups[-1]
            grouping_ok = _valid_grouping(groups)
            if len(tail) != 3 or not grouping_ok:      # 9.99, 1,5, 83.1254
                if len(ints) == 1 or _valid_grouping(ints):
                    return [_canon("".join(ints), tail)]
            elif dec == mark:                          # 1,500 in de-DE = 1.5
                return [_canon("".join(ints), tail)]
            else:                                      # 1,500 in en-US = 1500
                return [_canon("".join(groups))]
        elif _valid_grouping(groups, lakh_ok=(mark == ",")):
            return [_canon("".join(groups))]           # 1,000,000 / 1,00,000
    elif _valid_grouping(groups):                      # 5 000 / 1'000
        return [_canon("".join(groups))]
    return [_canon(g) for g in groups if g]            # dates, versions, other runs


def _strip_links(text: str) -> str:
    return EMAIL_RE.sub(" ", URL_RE.sub(" ", text))


def numbers(text: str, dec=None) -> Counter:
    return Counter(v for m in NUM_RE.findall(_strip_links(text)) for v in parse_number(m, dec))


def context(text: str, value: str, dec=None, width: int = 50) -> str:
    text = _strip_links(text)
    for m in NUM_RE.finditer(text):
        if value in parse_number(m.group(), dec):
            a, b = max(0, m.start() - width), min(len(text), m.end() + width)
            return " ".join(text[a:b].split())
    return ""


def structure(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return {
        "headings": sum(1 for l in lines if l.startswith("#")),
        "list_items": sum(1 for l in lines if l.startswith(("- ", "* "))),
        "paragraphs": sum(1 for l in lines if not l.startswith(("#", "- ", "* "))),
        "chars": len(re.sub(r"\s+", "", text)),
    }


def identical_segments(src: str, tgt: str, min_words: int = 5, min_heading_words: int = 2):
    """Source sentences (>= min_words) or headings/list items (>= min_heading_words) found verbatim in target."""
    tgt_norm = " ".join(tgt.lower().split())
    tgt_lines = {" ".join(l.strip().lstrip("#-* ").lower().split()) for l in tgt.splitlines()}
    hits = []
    for line in src.splitlines():
        line = line.strip()
        if line.startswith(("#", "- ", "* ")):
            seg = line.lstrip("#-* ").strip()
            if len(WORD_RE.findall(seg)) >= min_heading_words and " ".join(seg.lower().split()) in tgt_lines:
                hits.append(seg[:160])
                continue
        for seg in SENT_SPLIT.split(line):
            seg = seg.strip().lstrip("#-* ").strip()
            if len(WORD_RE.findall(seg)) < min_words or URL_RE.fullmatch(seg) or seg[:160] in hits:
                continue
            if " ".join(seg.lower().split()) in tgt_norm:
                hits.append(seg[:160])
    return hits


def rendering_signals(src: str, tgt: str):
    """Placeholders, markup, entities or mojibake that appear more often in the target than the source."""
    out = []
    for kind, rx in RENDERING_PATTERNS:
        extra = Counter(rx.findall(tgt)) - Counter(rx.findall(src))
        for found, count in extra.items():
            m = re.search(re.escape(found), tgt)
            a, b = max(0, m.start() - 40), min(len(tgt), m.end() + 40)
            out.append({"kind": kind, "text": found, "count": count,
                        "target_context": " ".join(tgt[a:b].split())})
    return out


def run(src: str, tgt: str, source_locale: str = "", target_locale: str = "") -> dict:
    sdec, tdec = decimal_sep(source_locale), decimal_sep(target_locale)
    sn, tn = numbers(src, sdec), numbers(tgt, tdec)
    missing_nums = [{"number": n, "count": c, "source_context": context(src, n, sdec)}
                    for n, c in (sn - tn).items()]
    extra_nums = [{"number": n, "count": c, "target_context": context(tgt, n, tdec)}
                  for n, c in (tn - sn).items()]

    def links(text):
        found = URL_RE.findall(text) + EMAIL_RE.findall(text)
        return {l.rstrip(".,;:!?)") for l in found}

    missing_links = sorted(links(src) - links(tgt))

    ss, ts = structure(src), structure(tgt)
    ratio = round(ts["chars"] / ss["chars"], 2) if ss["chars"] else None
    cjk = target_locale.lower().startswith(CJK_LOCALES) and not source_locale.lower().startswith(CJK_LOCALES)
    lo, hi = (0.2, 0.8) if cjk else (0.7, 1.6)
    ratio_flag = ratio is not None and not (lo <= ratio <= hi)
    struct_flags = [f"{k}: source {ss[k]} vs target {ts[k]}"
                    for k in ("headings", "list_items", "paragraphs") if ss[k] != ts[k]]

    return {
        "missing_numbers": missing_nums,
        "extra_numbers": extra_nums,
        "missing_urls_or_emails": missing_links,
        "identical_segments": identical_segments(src, tgt),
        "rendering": rendering_signals(src, tgt),
        "length_ratio": ratio,
        "length_ratio_expected": [lo, hi],
        "length_ratio_flag": ratio_flag,
        "structure_source": ss,
        "structure_target": ts,
        "structure_differences": struct_flags,
    }


def format_text(r: dict) -> str:
    lo, hi = r["length_ratio_expected"]
    out = ["PRE-CHECK SIGNALS (verify each before reporting)",
           f"- Length ratio target/source: {r['length_ratio']} (expected {lo}-{hi})"
           + ("  <-- outside range" if r["length_ratio_flag"] else "")]
    out += [f"- Structure differs: {f}" for f in r["structure_differences"]]
    out += [f"- Number in source not found in target: {m['number']} (x{m['count']}) ... {m['source_context']}"
            for m in r["missing_numbers"]]
    out += [f"- Number in target not in source: {m['number']} (x{m['count']}) ... {m['target_context']}"
            for m in r["extra_numbers"]]
    out += [f"- URL/email in source not in target (may be localized): {l}" for l in r["missing_urls_or_emails"]]
    out += [f"- Segment identical in target (possibly untranslated): {s}" for s in r["identical_segments"]]
    out += [f"- Rendering ({x['kind']}) only in target: {x['text']} (x{x['count']}) ... {x['target_context']}"
            for x in r["rendering"]]
    if len(out) == 2 and not r["length_ratio_flag"]:
        out.append("- No signals.")
    return "\n".join(out)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("target")
    ap.add_argument("--source-locale", default="en", help="default: en")
    ap.add_argument("--target-locale", default="")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args()

    with open(args.source, encoding="utf-8") as f:
        src = f.read()
    with open(args.target, encoding="utf-8") as f:
        tgt = f.read()
    result = run(src, tgt, args.source_locale, args.target_locale)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else format_text(result))


if __name__ == "__main__":
    main()
