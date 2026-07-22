#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.openclaw/skills/tpk-ocr"

mkdir -p "$HOME/.openclaw/skills"
rm -rf "$TARGET_DIR"
cp -R "$SOURCE_DIR" "$TARGET_DIR"

echo "Installed tpk-ocr to: $TARGET_DIR"
echo "Next: cd $TARGET_DIR && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
