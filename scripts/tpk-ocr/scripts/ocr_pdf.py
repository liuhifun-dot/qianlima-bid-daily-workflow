#!/usr/bin/env python3
"""
Render scanned PDF pages to images, then OCR them with PaddleOCR.

Examples:
  python scripts/ocr_pdf.py "file.pdf" --pages all --dpi 220 --format md --output result.md
  python scripts/ocr_pdf.py "file.pdf" --pages 1-3,5 --dpi 240 --format json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

# 2026-07-13 fix: Windows GBK stdout cannot encode chars like superscript-2.
# Force stdout/stderr to UTF-8 to avoid UnicodeEncodeError after OCR completes.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Allow importing ocr_image.py from the same scripts directory.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ocr_image import OCRLine, render_text, run_ocr  # noqa: E402


def _fail(message: str, code: int = 1) -> None:
    print(f"[tpk-ocr] {message}", file=sys.stderr)
    raise SystemExit(code)


def parse_pages(page_spec: str, page_count: int) -> List[int]:
    if page_spec.strip().lower() == "all":
        return list(range(page_count))

    pages = set()
    for part in page_spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = int(start_s)
            end = int(end_s)
            if start > end:
                start, end = end, start
            for page in range(start, end + 1):
                pages.add(page - 1)
        else:
            pages.add(int(part) - 1)

    valid = sorted(p for p in pages if 0 <= p < page_count)
    if not valid:
        _fail(f"No valid pages selected. PDF has {page_count} pages; page spec was: {page_spec}")
    return valid


def render_pdf_pages(pdf_path: Path, pages: List[int], dpi: int, temp_dir: Path) -> List[Tuple[int, Path]]:
    try:
        import fitz  # PyMuPDF
    except Exception as exc:
        _fail(f"PyMuPDF is not installed. Run: pip install -r requirements.txt\nImport error: {exc}")

    doc = fitz.open(str(pdf_path))
    rendered: List[Tuple[int, Path]] = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for page_index in pages:
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        out_path = temp_dir / f"page_{page_index + 1:04d}.png"
        pix.save(str(out_path))
        rendered.append((page_index + 1, out_path))

    doc.close()
    return rendered


def render_markdown_pdf(results: List[Tuple[int, List[OCRLine]]], source: Path) -> str:
    chunks = ["# OCR Result", "", f"Source: `{source}`", ""]
    for page_number, lines in results:
        chunks.extend([f"## Page {page_number}", "", render_text(lines), ""])
        low = [line for line in lines if line.score is not None and line.score < 0.75]
        if low:
            chunks.extend([f"### Low-confidence lines on page {page_number}", ""])
            for line in low[:20]:
                chunks.append(f"- `{line.score:.3f}` {line.text}")
            if len(low) > 20:
                chunks.append(f"- ... {len(low) - 20} more low-confidence lines")
            chunks.append("")
    return "\n".join(chunks).strip() + "\n"


def render_json_pdf(results: List[Tuple[int, List[OCRLine]]], source: Path) -> str:
    payload = {
        "source": str(source),
        "page_count_ocr": len(results),
        "pages": [
            {
                "page": page_number,
                "line_count": len(lines),
                "lines": [asdict(line) for line in lines],
            }
            for page_number, lines in results
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OCR scanned PDF pages using local PaddleOCR.")
    parser.add_argument("pdf", help="Path to a PDF file.")
    parser.add_argument("--pages", default="all", help="Pages to OCR, e.g. all, 1-3,5. Default: all")
    parser.add_argument("--dpi", type=int, default=220, help="PDF rendering DPI. Default: 220")
    parser.add_argument("--lang", default=os.environ.get("TPK_OCR_LANG", "ch"), help="PaddleOCR language. Default: ch")
    parser.add_argument("--format", choices=["text", "md", "json"], default="md", help="Output format. Default: md")
    parser.add_argument("--output", "-o", help="Optional output file path.")
    parser.add_argument("--gpu", action="store_true", help="Try to use GPU if the installed PaddleOCR/PaddlePaddle build supports it.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    pdf_path = Path(args.pdf).expanduser().resolve()

    if not pdf_path.exists():
        _fail(f"Input PDF does not exist: {pdf_path}")
    if not pdf_path.is_file():
        _fail(f"Input path is not a file: {pdf_path}")
    if args.dpi < 120 or args.dpi > 400:
        _fail("DPI should usually be between 120 and 400.")

    try:
        import fitz  # PyMuPDF
    except Exception as exc:
        _fail(f"PyMuPDF is not installed. Run: pip install -r requirements.txt\nImport error: {exc}")

    doc = fitz.open(str(pdf_path))
    page_count = doc.page_count
    doc.close()

    selected_pages = parse_pages(args.pages, page_count)

    with tempfile.TemporaryDirectory(prefix="tpk_ocr_pdf_") as tmp:
        temp_dir = Path(tmp)
        rendered = render_pdf_pages(pdf_path, selected_pages, args.dpi, temp_dir)
        results: List[Tuple[int, List[OCRLine]]] = []
        total_pages = len(rendered)
        print(
            f"[tpk-ocr] PROGRESS page=0 total={total_pages} status=starting",
            file=sys.stderr,
            flush=True,
        )
        for page_number, image_path in rendered:
            print(f"[tpk-ocr] OCR page {page_number}...", file=sys.stderr, flush=True)
            print(
                f"[tpk-ocr] PROGRESS page={page_number} total={total_pages} status=ocr_running",
                file=sys.stderr,
                flush=True,
            )
            # 2026-07-13 修复：逐页容错。工程图纸某些页是纯图形无文字，
            # run_ocr 会 _fail(SystemExit)，不能让单页失败中断整个多页任务。
            try:
                lines = run_ocr(image_path=image_path, lang=args.lang, use_gpu=args.gpu)
            except SystemExit:
                print(f"[tpk-ocr] page {page_number} has no text, skipped", file=sys.stderr, flush=True)
                lines = []
            except Exception as exc:
                print(f"[tpk-ocr] page {page_number} OCR error: {exc}", file=sys.stderr, flush=True)
                lines = []
            results.append((page_number, lines))
        print(
            f"[tpk-ocr] PROGRESS page={total_pages} total={total_pages} status=done",
            file=sys.stderr,
            flush=True,
        )

    if args.format == "json":
        output = render_json_pdf(results, pdf_path) + "\n"
    elif args.format == "text":
        chunks = []
        for page_number, lines in results:
            chunks.append(f"===== Page {page_number} =====")
            chunks.append(render_text(lines))
        output = "\n\n".join(chunks).strip() + "\n"
    else:
        output = render_markdown_pdf(results, pdf_path)

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"[tpk-ocr] Wrote: {out_path}")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
