#!/usr/bin/env python3
"""Generate a unified Chinese test record from pipeline artifacts."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def read_json(path: str | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8-sig"))


def compact_attachment(summary: dict[str, Any]) -> str:
    if not summary:
        return "\u9644\u4ef6\u7edf\u8ba1\u7f3a\u5931"
    page = summary.get("page_attachment_available_count", summary.get("page_available_count", "-"))
    any_ok = summary.get("page_attachment_read_any_count", "-")
    required = summary.get("evidence_required_count", summary.get("required_count", "-"))
    read_ok = summary.get("evidence_read_ok_count", summary.get("read_ok_count", "-"))
    gap = summary.get("evidence_gap_count", "-")
    return f"\u9875\u9762\u6709\u9644\u4ef6 {page} \u6761\uff0c\u81f3\u5c11\u8bfb\u5230 {any_ok} \u6761\uff0c\u8bc1\u636e\u5fc5\u8bfb {required} \u6761\uff0c\u8bc1\u636e\u8bfb\u5230 {read_ok} \u6761\uff0c\u7f3a\u53e3 {gap} \u6761"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-manifest")
    parser.add_argument("--pipeline-manifest")
    parser.add_argument("--phase2-validation")
    parser.add_argument("--encoding-validation")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--test-name", default="rc04 \u5b9a\u5411\u56de\u5f52")
    parser.add_argument("--run-date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    run_manifest = read_json(args.run_manifest)
    pipeline_manifest = read_json(args.pipeline_manifest)
    phase2_validation = read_json(args.phase2_validation)
    encoding_validation = read_json(args.encoding_validation)

    attachment_summary = (
        run_manifest.get("attachment_evidence")
        or pipeline_manifest.get("attachment_evidence")
        or {}
    )
    phase2_ok = phase2_validation.get("ok")
    encoding_ok = encoding_validation.get("ok")

    lines = [
        f"# {args.test_name}",
        "",
        f"- \u8fd0\u884c\u65e5\u671f\uff1a{args.run_date}",
        f"- Phase 2 \u6821\u9a8c\uff1a{'\u901a\u8fc7' if phase2_ok else '\u672a\u901a\u8fc7'}",
        f"- \u6587\u672c\u7f16\u7801\u6821\u9a8c\uff1a{'\u901a\u8fc7' if encoding_ok else '\u672a\u901a\u8fc7'}",
        f"- \u9644\u4ef6\u7edf\u8ba1\uff1a{compact_attachment(attachment_summary)}",
        "",
        "## \u9a8c\u6536\u9879",
        "",
        "| \u68c0\u67e5\u9879 | \u7ed3\u679c |",
        "|---|---|",
        f"| \u9644\u4ef6\u5b57\u6bb5\u5206\u5c42 | {'\u901a\u8fc7' if attachment_summary else '\u672a\u751f\u6210'} |",
        f"| \u5f85\u590d\u6838\u539f\u56e0\u4e2d\u6587\u53ef\u8bfb | {'\u901a\u8fc7' if encoding_ok else '\u672a\u901a\u8fc7'} |",
        f"| \u65e5\u5fd7/\u62a5\u544a\u65e0\u4e71\u7801 | {'\u901a\u8fc7' if encoding_ok else '\u672a\u901a\u8fc7'} |",
        "",
        "## \u8bc1\u636e\u8def\u5f84",
        "",
        f"- run_manifest\uff1a{args.run_manifest or '\u672a\u63d0\u4f9b'}",
        f"- pipeline_manifest\uff1a{args.pipeline_manifest or '\u672a\u63d0\u4f9b'}",
        f"- phase2_validation\uff1a{args.phase2_validation or '\u672a\u63d0\u4f9b'}",
        f"- encoding_validation\uff1a{args.encoding_validation or '\u672a\u63d0\u4f9b'}",
        "",
        "## \u7ed3\u8bba",
        "",
        "Phase 2 \u8bc1\u636e\u95e8\u69db\u3001\u9644\u4ef6\u5b57\u6bb5\u5206\u5c42\u548c\u6587\u672c\u7f16\u7801\u9700\u540c\u65f6\u901a\u8fc7\uff0c\u624d\u80fd\u5224\u5b9a B+C+D \u4fee\u590d\u6709\u6548\u3002",
    ]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    md = output_dir / "\u6d4b\u8bd5\u8bb0\u5f55_20260625_rc04.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    summary = {
        "ok": bool(phase2_ok) and bool(encoding_ok) and bool(attachment_summary),
        "record": str(md),
        "phase2_ok": phase2_ok,
        "encoding_ok": encoding_ok,
        "attachment_summary": attachment_summary,
    }
    js = output_dir / "\u6d4b\u8bd5\u8bb0\u5f55_20260625_rc04.json"
    js.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
