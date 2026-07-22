#!/usr/bin/env python3
"""
Local OCR for screenshots and images using PaddleOCR.

Examples:
  python scripts/ocr_image.py "image.png" --lang ch --format md
  python scripts/ocr_image.py "image.png" --lang ch --format json --output result.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple

# 2026-07-13 fix: Windows GBK stdout cannot encode chars like superscript-2.
# Force stdout/stderr to UTF-8 to avoid UnicodeEncodeError after OCR completes.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


@dataclass
class OCRLine:
    text: str
    score: Optional[float] = None
    box: Optional[Any] = None
    x: float = 0.0
    y: float = 0.0


def _fail(message: str, code: int = 1) -> None:
    print(f"[tpk-ocr] {message}", file=sys.stderr)
    raise SystemExit(code)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _flatten_numbers(value: Any) -> List[float]:
    numbers: List[float] = []
    if _is_number(value):
        return [float(value)]
    if isinstance(value, (list, tuple)):
        for item in value:
            numbers.extend(_flatten_numbers(item))
    else:
        # numpy arrays and PaddleOCR internal tensors often support tolist().
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            try:
                numbers.extend(_flatten_numbers(tolist()))
            except Exception:
                pass
    return numbers


def _box_origin(box: Any) -> Tuple[float, float]:
    nums = _flatten_numbers(box)
    if len(nums) >= 2:
        xs = nums[0::2]
        ys = nums[1::2]
        return (min(xs), min(ys))
    return (0.0, 0.0)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return _json_safe(tolist())
        except Exception:
            pass
    return str(value)


def _make_line(text: Any, score: Any = None, box: Any = None) -> Optional[OCRLine]:
    if text is None:
        return None
    text_str = str(text).strip()
    if not text_str:
        return None
    score_float: Optional[float] = None
    if _is_number(score):
        score_float = float(score)
    x, y = _box_origin(box)
    return OCRLine(text=text_str, score=score_float, box=_json_safe(box), x=x, y=y)


def _sort_lines(lines: List[OCRLine]) -> List[OCRLine]:
    # Simple and stable reading-order sort. Good enough for screenshots and common bid docs.
    return sorted(lines, key=lambda item: (round(item.y / 12.0), item.x, item.y))


def _init_paddleocr(lang: str, use_gpu: bool = False) -> Any:
    # Force-disable OneDNN/MKL-DNN to avoid Windows CPU crashes
    # (PaddlePaddle 3.x + OneDNN = RuntimeError on fused_conv2d).
    import os
    os.environ["FLAGS_use_mkldnn"] = "0"
    os.environ["FLAGS_use_mkldnn"] = "0"
    os.environ["MKLDNN_CACHE_CAPACITY"] = "0"
    os.environ["KMP_AFFINITY"] = "disabled"

    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as exc:
        _fail(
            "PaddleOCR is not installed. Run: pip install -r requirements.txt\n"
            f"Import error: {exc}"
        )

    # PaddleOCR 2.x and 3.x have different constructor arguments.
    # Prefer 2.x-style (use_angle_cls) because it supports the legacy ocr.ocr() API
    # which is more stable on Windows CPU than the 3.x predict() pipeline.
    attempts = [
        {"use_angle_cls": True, "lang": lang, "use_gpu": use_gpu, "show_log": False},
        {"use_angle_cls": True, "lang": lang, "show_log": False},
        {"lang": lang, "use_textline_orientation": True},
        {"lang": lang},
        {},
    ]

    last_exc: Optional[Exception] = None
    for kwargs in attempts:
        try:
            return PaddleOCR(**kwargs)
        except Exception as exc:  # pragma: no cover - depends on installed PaddleOCR version
            last_exc = exc

    _fail(f"Could not initialize PaddleOCR. Last error: {last_exc}")


def _extract_from_legacy_result(result: Any) -> List[OCRLine]:
    """Parse PaddleOCR 2.x style result: [[box, (text, score)], ...]."""
    lines: List[OCRLine] = []

    if result is None:
        return lines

    # v2 image result can be [ [line1, line2, ...] ]; unwrap page container.
    if isinstance(result, list) and len(result) == 1 and isinstance(result[0], list):
        possible_page = result[0]
        if possible_page and isinstance(possible_page[0], (list, tuple)):
            result = possible_page

    if isinstance(result, list):
        for row in result:
            try:
                if not row or len(row) < 2:
                    continue
                box = row[0]
                payload = row[1]
                if isinstance(payload, (list, tuple)) and len(payload) >= 1:
                    text = payload[0]
                    score = payload[1] if len(payload) > 1 else None
                else:
                    text = payload
                    score = None
                line = _make_line(text=text, score=score, box=box)
                if line:
                    lines.append(line)
            except Exception:
                continue
    return _sort_lines(lines)


def _object_to_dict(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if hasattr(value, "res"):
        try:
            return getattr(value, "res")
        except Exception:
            pass
    if hasattr(value, "json"):
        try:
            json_attr = getattr(value, "json")
            return json_attr() if callable(json_attr) else json_attr
        except Exception:
            pass
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:
            pass
    return value


def _extract_from_predict_result(result: Any) -> List[OCRLine]:
    """Parse PaddleOCR 3.x predict result as flexibly as possible."""
    lines: List[OCRLine] = []

    if result is None:
        return lines

    items = result if isinstance(result, list) else [result]
    for item in items:
        data = _object_to_dict(item)
        if not isinstance(data, dict):
            continue

        # Common PaddleOCR 3.x keys.
        texts = data.get("rec_texts") or data.get("texts") or data.get("text")
        scores = data.get("rec_scores") or data.get("scores") or data.get("score")
        boxes = (
            data.get("rec_polys")
            or data.get("dt_polys")
            or data.get("rec_boxes")
            or data.get("boxes")
            or data.get("text_det_polys")
        )

        if isinstance(texts, str):
            line = _make_line(texts, scores, boxes)
            if line:
                lines.append(line)
            continue

        if isinstance(texts, Sequence):
            for idx, text in enumerate(texts):
                score = scores[idx] if isinstance(scores, Sequence) and idx < len(scores) else None
                box = boxes[idx] if isinstance(boxes, Sequence) and idx < len(boxes) else None
                line = _make_line(text, score, box)
                if line:
                    lines.append(line)

    return _sort_lines(lines)


def run_ocr(image_path: Path, lang: str = "ch", use_gpu: bool = False) -> List[OCRLine]:
    if not image_path.exists():
        _fail(f"Input image does not exist: {image_path}")
    if not image_path.is_file():
        _fail(f"Input path is not a file: {image_path}")

    ocr = _init_paddleocr(lang=lang, use_gpu=use_gpu)

    # Prefer legacy OCR API when available because it returns clean coordinates and scores.
    if hasattr(ocr, "ocr"):
        try:
            result = ocr.ocr(str(image_path), cls=True)
            lines = _extract_from_legacy_result(result)
            if lines:
                return lines
        except TypeError:
            # PaddleOCR 3.x may not accept cls=True.
            try:
                result = ocr.ocr(str(image_path))
                lines = _extract_from_legacy_result(result)
                if lines:
                    return lines
            except Exception:
                pass
        except Exception:
            pass

    if hasattr(ocr, "predict"):
        try:
            result = ocr.predict(input=str(image_path))
        except TypeError:
            result = ocr.predict(str(image_path))
        lines = _extract_from_predict_result(result)
        if lines:
            return lines

    _fail("OCR finished but no text lines were detected. Try a higher-resolution image.")


def render_text(lines: List[OCRLine]) -> str:
    return "\n".join(line.text for line in lines)


def render_markdown(lines: List[OCRLine], source: Path) -> str:
    avg_score = None
    scored = [line.score for line in lines if line.score is not None]
    if scored:
        avg_score = sum(scored) / len(scored)

    chunks = [f"# OCR Result", "", f"Source: `{source}`", ""]
    if avg_score is not None:
        chunks.extend([f"Average confidence: `{avg_score:.3f}`", ""])
    chunks.extend(["## Text", "", render_text(lines), ""])

    low = [line for line in lines if line.score is not None and line.score < 0.75]
    if low:
        chunks.extend(["## Low-confidence lines", ""])
        for line in low[:30]:
            chunks.append(f"- `{line.score:.3f}` {line.text}")
        if len(low) > 30:
            chunks.append(f"- ... {len(low) - 30} more low-confidence lines")
        chunks.append("")
    return "\n".join(chunks).strip() + "\n"


def render_json(lines: List[OCRLine], source: Path) -> str:
    payload = {
        "source": str(source),
        "line_count": len(lines),
        "lines": [asdict(line) for line in lines],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OCR an image using local PaddleOCR.")
    parser.add_argument("image", help="Path to an image file: png, jpg, jpeg, webp, bmp, tif, etc.")
    parser.add_argument("--lang", default=os.environ.get("TPK_OCR_LANG", "ch"), help="PaddleOCR language. Default: ch")
    parser.add_argument("--format", choices=["text", "md", "json"], default="md", help="Output format. Default: md")
    parser.add_argument("--output", "-o", help="Optional output file path.")
    parser.add_argument("--gpu", action="store_true", help="Try to use GPU if the installed PaddleOCR/PaddlePaddle build supports it.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    image_path = Path(args.image).expanduser().resolve()
    lines = run_ocr(image_path=image_path, lang=args.lang, use_gpu=args.gpu)

    if args.format == "text":
        output = render_text(lines) + "\n"
    elif args.format == "json":
        output = render_json(lines, image_path) + "\n"
    else:
        output = render_markdown(lines, image_path)

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
