#!/usr/bin/env python3
"""Objective pre-checks for a source/target article pair.

Usage:
    python precheck.py source.txt target.txt [--target-locale de-DE] [--json]

Reports SIGNALS for Claude to verify (not confirmed issues):
  - numbers in the source missing from the target (locale-insensitive: 1,234.5 == 1.234,5)
  - numbers in the target not present in the source
  - URLs / email addresses in the source missing from the target
  - long source segments copied unchanged into the target (possibly untranslated)
  - text length ratio and heading / paragraph / list-item count differences
"""
import argparse
import json
import re
from collections import Counter

NUM_RE = re.compile(r"\d+(?:[.,   ' ]\d{3})*(?:[.,]\d+)?")
URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
SENT_SPLIT = re.compile(r"(?<=[.!?。！？])\s+|\n+")
WORD_RE = re.compile(r"\w+", re.U)
CJK_LOCALES = ("zh", "ja", "ko")


def norm_num(s: str) -> str:
    return re.sub(r"\D", "", s)


def numbers(text: str) -> Counter:
    text = URL_RE.sub(" ", text)
    return Counter(norm_num(m) for m in NUM_RE.findall(text) if norm_num(m))


def context(text: str, needle_digits: str, width: int = 50) -> str:
    for m in NUM_RE.finditer(text):
        if norm_num(m.group()) == needle_digits:
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("target")
    ap.add_argument("--target-locale", default="")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args()

    src = open(args.source, encoding="utf-8").read()
    tgt = open(args.target, encoding="utf-8").read()

    sn, tn = numbers(src), numbers(tgt)
    missing_nums = [{"number": n, "count": c, "source_context": context(src, n)}
                    for n, c in (sn - tn).items()]
    extra_nums = [{"number": n, "count": c, "target_context": context(tgt, n)}
                  for n, c in (tn - sn).items()]

    def links(text):
        found = URL_RE.findall(text) + EMAIL_RE.findall(text)
        return {l.rstrip(".,;:!?)") for l in found}

    s_links, t_links = links(src), links(tgt)
    missing_links = sorted(s_links - t_links)

    ss, ts = structure(src), structure(tgt)
    ratio = round(ts["chars"] / ss["chars"], 2) if ss["chars"] else None
    cjk = args.target_locale.lower().startswith(CJK_LOCALES)
    lo, hi = (0.2, 0.8) if cjk else (0.7, 1.6)
    ratio_flag = ratio is not None and not (lo <= ratio <= hi)

    struct_flags = []
    for k in ("headings", "list_items", "paragraphs"):
        if ss[k] != ts[k]:
            struct_flags.append(f"{k}: source {ss[k]} vs target {ts[k]}")

    result = {
        "missing_numbers": missing_nums,
        "extra_numbers": extra_nums,
        "missing_urls_or_emails": missing_links,
        "identical_segments": identical_segments(src, tgt),
        "length_ratio": ratio,
        "length_ratio_expected": [lo, hi],
        "length_ratio_flag": ratio_flag,
        "structure_source": ss,
        "structure_target": ts,
        "structure_differences": struct_flags,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("PRE-CHECK SIGNALS (verify each before reporting)")
    print(f"- Length ratio target/source: {ratio} (expected {lo}-{hi})" + ("  <-- outside range" if ratio_flag else ""))
    for f in struct_flags:
        print(f"- Structure differs: {f}")
    for m in missing_nums:
        print(f"- Number in source not found in target: {m['number']} (x{m['count']}) ... {m['source_context']}")
    for m in extra_nums:
        print(f"- Number in target not in source: {m['number']} (x{m['count']}) ... {m['target_context']}")
    for l in missing_links:
        print(f"- URL/email in source not in target (may be localized): {l}")
    for s in result["identical_segments"]:
        print(f"- Segment identical in target (possibly untranslated): {s}")
    if not any([ratio_flag, struct_flags, missing_nums, extra_nums, missing_links, result["identical_segments"]]):
        print("- No signals.")


if __name__ == "__main__":
    main()
