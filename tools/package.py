#!/usr/bin/env python3
"""Build dist/localization-qa-triage.zip with the skill folder at the top level, as Claude's
"Upload a skill" expects, and check the result. Works on Windows, macOS and Linux."""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".claude" / "skills" / "localization-qa-triage"
OUT = ROOT / "dist" / f"{SKILL.name}.zip"
SKIP_DIRS = {"__pycache__", ".pytest_cache"}
SKIP_NAMES = {".DS_Store", "Thumbs.db"}


def main():
    files = sorted(p for p in SKILL.rglob("*")
                   if p.is_file() and not SKIP_DIRS & set(p.relative_to(SKILL).parts)
                   and p.name not in SKIP_NAMES and p.suffix != ".pyc")
    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, f"{SKILL.name}/{p.relative_to(SKILL).as_posix()}")
    with zipfile.ZipFile(OUT) as z:
        names = z.namelist()
    if f"{SKILL.name}/SKILL.md" not in names:
        sys.exit(f"ERROR: {SKILL.name}/SKILL.md is missing from the ZIP")
    print("\n".join(names))
    print(f"Wrote {OUT.relative_to(ROOT).as_posix()} ({len(names)} files)")


if __name__ == "__main__":
    main()
