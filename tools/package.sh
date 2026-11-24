#!/usr/bin/env bash
# Build dist/localization-qa-triage.zip with the skill folder at the top level,
# as Claude's "Upload a skill" expects.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p dist
rm -f dist/localization-qa-triage.zip
(cd .claude/skills && zip -qr ../../dist/localization-qa-triage.zip localization-qa-triage \
  -x '*/__pycache__/*' '*.pyc' '*/.DS_Store')
unzip -l dist/localization-qa-triage.zip
