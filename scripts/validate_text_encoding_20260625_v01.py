#!/usr/bin/env python3
"""Validate generated logs/reports for mojibake and leaked technical reasons."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Literal mojibake markers. Keep this list ASCII-safe so PowerShell encoding cannot corrupt it.
MOJIBAKE_LITERALS = [
    "\u003f\u003f\u003f\u003f",
    "\ufffd",
    "\u951b",  # mojibake marker
    "\u934f",  # mojibake marker
    "\u935a",  # mojibake marker
    "\u6d93",  # mojibake marker
    "\u93b7",  # mojibake marker
    "\u99c3",  # mojibake marker
    "\u9205",  # mojibake marker
    "\u922b",  # mojibake marker
    "\u7a11",  # mojibake marker
    "\u95bd",  # mojibake marker
    "\u00e6",  # latin mojibake marker
    "\u00f0\u0178",  # latin emoji mojibake marker
    "\u00c2",  # latin UTF-8 mojibake marker
]
MOJIBAKE_REGEXES = [
    re.compile(r"\?{4,}"),
    re.compile(r"[\uFFFD]{1,}"),
]
TECHNICAL_REASON_PATTERNS = [
    re.compile(r"attachment_required\s*=\s*true", re.I),
    re.compile(r"attachment_read_ok\s*=\s*false", re.I),
    re.compile(r"valid tender/spec/BOQ", re.I),
    re.compile(r"procurement-demand attachment text was not read", re.I),
    re.compile(r"body_read_ok\s*=\s*false", re.I),
    re.compile(r"vip_status\s*=\s*missing and no VIP body", re.I),
]


def iter_files(root: Path, patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    if root.is_file():
        return [root]
    for pattern in patterns:
        files.extend(p for p in root.rglob(pattern) if p.is_file())
    return sorted(set(files))


def scan_file(path: Path) -> dict:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    findings = []
    if "\ufffd" in text:
        findings.append({"type": "decode_replacement", "pattern": "U+FFFD"})
    for literal in MOJIBAKE_LITERALS:
        if literal and literal in text:
            findings.append({"type": "mojibake_literal", "pattern": literal})
    for pattern in MOJIBAKE_REGEXES:
        if pattern.search(text):
            findings.append({"type": "mojibake_regex", "pattern": pattern.pattern})
    for pattern in TECHNICAL_REASON_PATTERNS:
        if pattern.search(text):
            findings.append({"type": "technical_reason_leak", "pattern": pattern.pattern})
    return {"path": str(path), "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--include", action="append", default=None, help="Glob pattern; repeatable")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(args.root)
    patterns = args.include or ["*.md", "*.json", "*.txt"]
    files = iter_files(root, patterns)
    results = [scan_file(path) for path in files]
    bad = [row for row in results if row["findings"]]
    payload = {
        "ok": not bad,
        "root": str(root),
        "patterns": patterns,
        "files_scanned": len(files),
        "problem_files": len(bad),
        "errors": bad,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
