# -*- coding: utf-8 -*-
"""
Kimi WebBridge attachment preview reader for Qianlima step 2B, v05.

v01 clicked "预览" and then read document.body, which can falsely capture the
original detail page. v02 follows the site's own API. v03 additionally
navigates back to the Qianlima detail page before every preview API call,
because the API is blocked after the current tab is on a cross-origin preview
page. v04 adds a PDF canvas fallback: save the preview page as PDF, extract
embedded text if any, then OCR rendered pages with local Tesseract.
v05 adds batch input from VIP body-read JSON and writes versioned output
under package output/v2_4.

1. Read .fileItem data-filepath-id from the Qianlima detail page.
2. Call /rest/detail/alltypesdetail/getPreViewByPathId in the browser context.
3. Navigate to returned previewUrl.
4. Capture readable preview text and mark canvas-only PDF/RAR cases explicitly.

No Cookie/Token is exported or stored. Browser credentials are used only inside
the user's browser context.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path


SESSION = "bid-automation"
GROUP_TITLE = "BID-AUTO"
WEBBRIDGE_URL = "http://127.0.0.1:10086/command"
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output" / "v2_4"
PIPELINE_OUTPUT_DIR = PROJECT_DIR / "output"
PDF_OCR_DIR = OUTPUT_DIR / "pdf_ocr_20260602_v05"
TESSERACT_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

DEFAULT_TARGETS = [
    {
        "title": "番禺区第二人民医院前广场道路改造项目采购公告",
        "url": "https://www.qianlima.com/bid-601764164.html",
        "reason": "用户截图样本：页面显示附件下载/预览，真实需求书和清单可能在附件中",
    }
]


def read_pointer(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").strip().strip('"').lstrip("\ufeff")


def find_latest_vip_json() -> Path:
    pointer_candidates = [
        OUTPUT_DIR / "latest_vip_read_path.txt",
        PIPELINE_OUTPUT_DIR / "latest_vip_read_path.txt",
    ]
    for pointer in pointer_candidates:
        if pointer.exists():
            target = Path(read_pointer(pointer))
            if target.exists():
                return target
    files = sorted(OUTPUT_DIR.glob("VIP原文阅读_*_Kimi_v*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if files:
        return files[0]
    raise FileNotFoundError("找不到 VIP 原文阅读 JSON，请先运行 kimi_vip_body_read_20260622_v04.py")


def next_output_path(run_date: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(rf"^附件预览正文读取_{re.escape(run_date)}_v(\d+)\.json$")
    versions = []
    for path in OUTPUT_DIR.glob(f"附件预览正文读取_{run_date}_v*.json"):
        match = pattern.match(path.name)
        if match:
            versions.append(int(match.group(1)))
    return OUTPUT_DIR / f"附件预览正文读取_{run_date}_v{max(versions, default=0) + 1:02d}.json"


def write_pointer(output_path: Path) -> list[Path]:
    pointers = [
        OUTPUT_DIR / "latest_attachment_preview_path.txt",
        PIPELINE_OUTPUT_DIR / "latest_attachment_preview_path.txt",
    ]
    for pointer in pointers:
        pointer.write_text(str(output_path), encoding="utf-8")
    return pointers


def targets_from_vip_json(vip_path: Path, required_only: bool = True) -> list[dict]:
    data = json.loads(vip_path.read_text(encoding="utf-8"))
    targets = []
    for project in data.get("projects", []):
        files = project.get("files") or project.get("attachments") or []
        flag = project.get("attachment_preview_required")
        if required_only and not flag:
            # 20260616: some body-read JSON variants lost attachment_preview_required.
            # If visible attachments exist and the flag is missing, read them instead of silently skipping 2C.
            if flag is None and files:
                reason = "attachment_preview_required missing; visible attachments exist, fallback to preview/read"
            else:
                continue
        else:
            reason = project.get("attachment_reason") or "vip_body_read marked attachment_preview_required"
        url = project.get("url")
        if not url:
            continue
        targets.append({
            "title": project.get("title") or url.rsplit("/", 1)[-1],
            "url": url,
            "reason": reason,
            "visible_attachment_count": len(files),
        })
    return targets


def wb(action: str, args: dict, timeout: int = 120) -> dict:
    body = json.dumps({"action": action, "args": args, "session": SESSION}, ensure_ascii=True).encode("utf-8")
    req = urllib.request.Request(
        WEBBRIDGE_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or data)
    return data["data"]


def fix_mojibake(value):
    if isinstance(value, str):
        try:
            fixed = value.encode("latin-1").decode("utf-8")
            if sum("\u4e00" <= ch <= "\u9fff" for ch in fixed) > sum("\u4e00" <= ch <= "\u9fff" for ch in value):
                return fixed
        except UnicodeError:
            pass
        return value
    if isinstance(value, dict):
        return {k: fix_mojibake(v) for k, v in value.items()}
    if isinstance(value, list):
        return [fix_mojibake(v) for v in value]
    return value


def content_id_from_url(url: str) -> str:
    match = re.search(r"bid-(\d+)\.html", url)
    if not match:
        raise ValueError(f"cannot parse content id from url: {url}")
    return match.group(1)


LIST_FILE_ITEMS_JS = r"""
(() => {
  const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim();
  const files = Array.from(document.querySelectorAll('.fileItem')).map((el, index) => ({
    index,
    fileName: el.dataset.fileName || '',
    filepathId: el.dataset.filepathId || '',
    downLinkUrl: el.dataset.downLinkUrl || '',
    rowText: clean(el.innerText || el.textContent || ''),
    canPreview: !!el.querySelector('.filePreview')
  }));
  return JSON.stringify({
    url: location.href,
    title: document.title,
    bodyTextLength: document.body ? document.body.innerText.length : 0,
    files
  });
})()
"""


def preview_api_js(content_id: str, filepath_id: str) -> str:
    return f"""
(async () => {{
  const url = 'https://detail.vip.qianlima.com/rest/detail/alltypesdetail/getPreViewByPathId?contentId={content_id}&filepathId={filepath_id}';
  try {{
    const resp = await fetch(url, {{credentials:'include'}});
    const text = await resp.text();
    let parsed = null;
    try {{ parsed = JSON.parse(text); }} catch (e) {{}}
    return JSON.stringify({{
      requestUrl: url,
      httpStatus: resp.status,
      contentType: resp.headers.get('content-type'),
      rawPreview: text.slice(0, 1200),
      json: parsed
    }});
  }} catch (e) {{
    return JSON.stringify({{requestUrl:url, error:String(e)}});
  }}
}})()
"""


CAPTURE_PREVIEW_PAGE_JS = r"""
(() => {
  const text = document.body ? document.body.innerText : '';
  const iframeSrcs = Array.from(document.querySelectorAll('iframe')).map((el) => el.src || el.getAttribute('src') || '');
  return JSON.stringify({
    url: location.href,
    title: document.title,
    textLength: text.length,
    text: text,
    textPreview: text.slice(0, 5000),
    iframeSrcs,
    canvasCount: document.querySelectorAll('canvas').length
  });
})()
"""


TOOLBAR_WORDS = ["切换侧栏", "上一页", "下一页", "自动缩放", "适合页面", "放大", "缩小"]


CANVAS_META_JS = r"""
(() => JSON.stringify({
  url: location.href,
  title: document.title,
  canvases: Array.from(document.querySelectorAll('canvas')).map((c, i) => ({
    index: i,
    width: c.width,
    height: c.height,
    clientWidth: c.clientWidth,
    clientHeight: c.clientHeight,
    canExport: (() => {
      try {
        c.toDataURL('image/png');
        return true;
      } catch (e) {
        return false;
      }
    })()
  }))
}))()
"""


def canvas_data_url_js(index: int) -> str:
    return f"""
(() => {{
  const canvas = document.querySelectorAll('canvas')[{index}];
  if (!canvas) return JSON.stringify({{error:'canvas not found', index:{index}}});
  try {{
    return JSON.stringify({{index:{index}, dataUrl: canvas.toDataURL('image/png')}});
  }} catch (e) {{
    return JSON.stringify({{index:{index}, error:String(e)}});
  }}
}})()
"""


def download_pdf_js(download_url: str, max_bytes: int) -> str:
    return f"""
(async () => {{
  const url = {json.dumps(download_url, ensure_ascii=True)};
  try {{
    const resp = await fetch(url, {{credentials:'include'}});
    const buffer = await resp.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    const head = Array.from(bytes.slice(0, 16)).map(b => String.fromCharCode(b)).join('');
    const sampleBytes = bytes.slice(0, Math.min(bytes.length, {max_bytes}));
    let binary = '';
    for (let i = 0; i < sampleBytes.length; i += 1) binary += String.fromCharCode(sampleBytes[i]);
    return JSON.stringify({{
      requestUrl: url,
      httpStatus: resp.status,
      contentType: resp.headers.get('content-type') || '',
      contentLength: bytes.length,
      sampledBytes: sampleBytes.length,
      head,
      base64: btoa(binary),
      truncated: bytes.length > {max_bytes}
    }});
  }} catch (e) {{
    return JSON.stringify({{requestUrl:url, error:String(e)}});
  }}
}})()
"""


def safe_stem(value: str, fallback: str) -> str:
    stem = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value or "", flags=re.UNICODE).strip("._")
    return (stem or fallback)[:80]


def extract_text_from_rendered_pdf(pdf_path: Path, min_chars: int) -> dict:
    try:
        import fitz
    except Exception as exc:
        return {"status": "pdf_dependency_missing", "error": f"PyMuPDF import failed: {exc}"}

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        return {"status": "pdf_open_failed", "error": str(exc), "source_pdf": str(pdf_path)}

    direct_parts = []
    for page in doc:
        direct_parts.append(page.get_text("text") or "")
    direct_text = "\n".join(part.strip() for part in direct_parts if part.strip())
    if len(direct_text) >= min_chars:
        doc.close()
        return {
            "status": "pdf_text_ok",
            "source_pdf": str(pdf_path),
            "method": "pymupdf_text",
            "pages": len(direct_parts),
            "textLength": len(direct_text),
            "text": direct_text,
            "textPreview": direct_text[:5000],
        }

    if not TESSERACT_EXE.exists():
        doc.close()
        return {
            "status": "pdf_ocr_unavailable",
            "source_pdf": str(pdf_path),
            "directTextLength": len(direct_text),
            "error": f"tesseract not found: {TESSERACT_EXE}",
        }

    try:
        from PIL import Image
        import pytesseract
    except Exception as exc:
        doc.close()
        return {
            "status": "pdf_ocr_dependency_missing",
            "source_pdf": str(pdf_path),
            "directTextLength": len(direct_text),
            "error": str(exc),
        }

    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_EXE)
    ocr_parts = []
    page_count = min(len(doc), 8)
    for page_index in range(page_count):
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        text = pytesseract.image_to_string(image, lang="chi_sim+eng", config="--psm 6")
        if text.strip():
            ocr_parts.append(text.strip())
    doc.close()

    ocr_text = "\n\n".join(ocr_parts).strip()
    return {
        "status": "pdf_ocr_ok" if len(ocr_text) >= min_chars else "pdf_ocr_too_short",
        "source_pdf": str(pdf_path),
        "method": "tesseract_chi_sim_eng",
        "pages": page_count,
        "directTextLength": len(direct_text),
        "textLength": len(ocr_text),
        "text": ocr_text,
        "textPreview": ocr_text[:5000],
    }


def download_and_parse_pdf_from_detail(content_id: str, file_item: dict, detail_url: str, min_chars: int, max_bytes: int = 8_000_000) -> dict:
    download_url = file_item.get("downLinkUrl") or ""
    if not download_url:
        return {"status": "pdf_download_url_missing"}

    wb("navigate", {"url": detail_url, "newTab": False})
    time.sleep(2)

    try:
        data = wb("evaluate", {"code": download_pdf_js(download_url, max_bytes=max_bytes)}, timeout=180)
        raw = data.get("value") if isinstance(data, dict) else data
        payload = json.loads(raw)
    except Exception as exc:
        return {"status": "pdf_download_fetch_failed", "error": str(exc), "downloadUrl": download_url}

    if payload.get("error"):
        return {"status": "pdf_download_fetch_failed", "error": payload["error"], "download": payload}

    head = payload.get("head") or ""
    content_type = (payload.get("contentType") or "").lower()
    if "%PDF" not in head and "pdf" not in content_type:
        preview = ""
        try:
            preview = base64.b64decode(payload.get("base64") or b"").decode("utf-8", errors="replace")[:1000]
        except Exception:
            pass
        return {
            "status": "pdf_download_not_pdf",
            "download": {k: v for k, v in payload.items() if k != "base64"},
            "textPreview": preview,
        }

    if payload.get("truncated"):
        return {"status": "pdf_download_too_large", "download": {k: v for k, v in payload.items() if k != "base64"}}

    PDF_OCR_DIR.mkdir(parents=True, exist_ok=True)
    file_id = file_item.get("filepathId") or "no_file_id"
    file_name = safe_stem(file_item.get("fileName") or "", f"file_{file_id}")
    pdf_path = PDF_OCR_DIR / f"{content_id}_{file_id}_{file_name}_download.pdf"
    pdf_path.write_bytes(base64.b64decode(payload.get("base64") or b""))

    result = extract_text_from_rendered_pdf(pdf_path, min_chars=min_chars)
    result["download"] = {k: v for k, v in payload.items() if k != "base64"}
    if result.get("status") == "pdf_text_ok":
        result["status"] = "pdf_download_text_ok"
    elif result.get("status") == "pdf_ocr_ok":
        result["status"] = "pdf_download_ocr_ok"
    return result


def ocr_current_preview_canvas(content_id: str, file_item: dict, min_chars: int, max_pages: int) -> dict:
    try:
        from PIL import Image
        import pytesseract
    except Exception as exc:
        return {"status": "pdf_ocr_dependency_missing", "error": str(exc)}

    if not TESSERACT_EXE.exists():
        return {"status": "pdf_ocr_unavailable", "error": f"tesseract not found: {TESSERACT_EXE}"}

    PDF_OCR_DIR.mkdir(parents=True, exist_ok=True)
    file_id = file_item.get("filepathId") or "no_file_id"
    file_name = safe_stem(file_item.get("fileName") or "", f"file_{file_id}")

    try:
        meta_data = wb("evaluate", {"code": CANVAS_META_JS}, timeout=120)
        meta_raw = meta_data.get("value") if isinstance(meta_data, dict) else meta_data
        meta = json.loads(meta_raw)
    except Exception as exc:
        return {"status": "pdf_canvas_meta_failed", "error": str(exc)}

    canvases = [item for item in meta.get("canvases", []) if item.get("canExport")]
    if not canvases:
        return {"status": "pdf_canvas_export_unavailable", "canvas_meta": meta}

    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_EXE)
    text_parts = []
    image_paths = []
    errors = []
    for item in canvases[:max_pages]:
        index = item["index"]
        try:
            data = wb("evaluate", {"code": canvas_data_url_js(index)}, timeout=120)
            raw = data.get("value") if isinstance(data, dict) else data
            payload = json.loads(raw)
            if payload.get("error"):
                errors.append({"index": index, "error": payload["error"]})
                continue

            data_url = payload.get("dataUrl") or ""
            if "," not in data_url:
                errors.append({"index": index, "error": "dataUrl missing comma"})
                continue
            image_bytes = base64.b64decode(data_url.split(",", 1)[1])
            image_path = PDF_OCR_DIR / f"{content_id}_{file_id}_{file_name}_canvas{index + 1}.png"
            image_path.write_bytes(image_bytes)
            image_paths.append(str(image_path))

            image = Image.open(image_path)
            text = pytesseract.image_to_string(image, lang="chi_sim+eng", config="--psm 6")
            if text.strip():
                text_parts.append(text.strip())
        except Exception as exc:
            errors.append({"index": index, "error": str(exc)})

    ocr_text = "\n\n".join(text_parts).strip()
    return {
        "status": "pdf_ocr_ok" if len(ocr_text) >= min_chars else "pdf_ocr_too_short",
        "method": "canvas_to_png_tesseract_chi_sim_eng",
        "canvas_meta": meta,
        "pages": min(len(canvases), max_pages),
        "image_paths": image_paths,
        "errors": errors,
        "textLength": len(ocr_text),
        "text": ocr_text,
        "textPreview": ocr_text[:5000],
    }


def ocr_current_preview_pdf(content_id: str, file_item: dict, detail_url: str, preview_url: str, min_chars: int, max_pages: int) -> dict:
    canvas_result = ocr_current_preview_canvas(content_id, file_item, min_chars=min_chars, max_pages=max_pages)
    if canvas_result.get("status") == "pdf_ocr_ok":
        return canvas_result

    download_result = download_and_parse_pdf_from_detail(content_id, file_item, detail_url=detail_url, min_chars=min_chars)
    if download_result.get("status") in {"pdf_download_text_ok", "pdf_download_ocr_ok"}:
        download_result["canvas_ocr"] = canvas_result
        return download_result

    wb("navigate", {"url": preview_url, "newTab": False})
    time.sleep(3)

    PDF_OCR_DIR.mkdir(parents=True, exist_ok=True)
    file_id = file_item.get("filepathId") or "no_file_id"
    file_name = safe_stem(file_item.get("fileName") or "", f"file_{file_id}")
    pdf_path = PDF_OCR_DIR / f"{content_id}_{file_id}_{file_name}.pdf"

    try:
        saved = wb(
            "save_as_pdf",
            {
                "paper_format": "a4",
                "landscape": False,
                "scale": 1.0,
                "print_background": True,
                "path": str(pdf_path),
            },
            timeout=180,
        )
    except Exception as exc:
        return {"status": "pdf_save_as_pdf_failed", "error": str(exc), "source_pdf": str(pdf_path)}

    saved_path = Path(saved.get("path") or pdf_path)
    result = extract_text_from_rendered_pdf(saved_path, min_chars=min_chars)
    result["save_as_pdf"] = saved
    result["canvas_ocr"] = canvas_result
    result["download_parse"] = download_result
    return result


def classify_preview(file_item: dict, api_result: dict, capture: dict | None) -> tuple[str, str]:
    if api_result.get("error"):
        return "preview_api_error", api_result["error"]

    payload = api_result.get("json") or {}
    code = payload.get("code")
    if code != 200:
        return "preview_not_supported", f"preview api code={code}, msg={payload.get('msg', '')}"

    data = payload.get("data") or {}
    if not data.get("previewUrl"):
        return "preview_url_missing", "preview api returned no previewUrl"

    if capture is None:
        return "preview_capture_missing", "previewUrl exists but capture did not run"

    text = capture.get("text") or ""
    text_length = capture.get("textLength") or 0
    canvas_count = capture.get("canvasCount") or 0
    toolbar_hits = sum(1 for word in TOOLBAR_WORDS if word in text)

    if text_length >= 500 and toolbar_hits < 4:
        return "ok", "preview page contains readable body text"

    ext = (file_item.get("fileName") or "").lower().rsplit(".", 1)[-1]
    if canvas_count > 0 and ext == "pdf":
        return "pdf_canvas_only", "PDF preview opened, but text layer is not readable from DOM"

    if text_length < 200:
        return "preview_text_too_short", "preview page text is too short"

    return "preview_toolbar_only", "preview page captured mostly toolbar/navigation text"


def read_target(target: dict, first: bool, max_files: int, enable_pdf_ocr: bool, ocr_min_chars: int, ocr_max_pages: int) -> dict:
    nav_args = {"url": target["url"], "newTab": first}
    if first:
        nav_args["group_title"] = GROUP_TITLE
    wb("navigate", nav_args)
    time.sleep(3)

    data = wb("evaluate", {"code": LIST_FILE_ITEMS_JS})
    raw = data.get("value") if isinstance(data, dict) else data
    page = fix_mojibake(json.loads(raw))
    content_id = content_id_from_url(target["url"])

    attachment_results = []
    for file_item in (page.get("files") or [])[:max_files]:
        if not file_item.get("filepathId"):
            attachment_results.append({"file": file_item, "status": "missing_filepath_id"})
            continue

        # The preview API must be called while the active tab is still on qianlima.com.
        wb("navigate", {"url": target["url"], "newTab": False})
        time.sleep(2)

        api_data = wb("evaluate", {"code": preview_api_js(content_id, file_item["filepathId"])}, timeout=120)
        api_raw = api_data.get("value") if isinstance(api_data, dict) else api_data
        api_result = fix_mojibake(json.loads(api_raw))

        capture = None
        payload = api_result.get("json") or {}
        preview_url = ((payload.get("data") or {}).get("previewUrl")) if payload.get("code") == 200 else None
        if preview_url:
            wb("navigate", {"url": preview_url, "newTab": True})
            time.sleep(8)
            capture_data = wb("evaluate", {"code": CAPTURE_PREVIEW_PAGE_JS}, timeout=120)
            capture_raw = capture_data.get("value") if isinstance(capture_data, dict) else capture_data
            capture = fix_mojibake(json.loads(capture_raw))

        status, reason = classify_preview(file_item, api_result, capture)
        pdf_ocr = None
        if status == "pdf_canvas_only" and enable_pdf_ocr:
            pdf_ocr = ocr_current_preview_pdf(
                content_id,
                file_item,
                detail_url=target["url"],
                preview_url=preview_url,
                min_chars=ocr_min_chars,
                max_pages=ocr_max_pages,
            )
            if pdf_ocr.get("status") in {"pdf_text_ok", "pdf_ocr_ok", "pdf_download_text_ok", "pdf_download_ocr_ok"}:
                status = "pdf_ocr_ok"
                reason = "PDF preview was canvas-only, but text was recovered by canvas image OCR, browser download parsing, or saved preview PDF OCR"
            else:
                reason = f"{reason}; OCR fallback status={pdf_ocr.get('status')}"

        attachment_results.append(
            {
                "file": file_item,
                "status": status,
                "reason": reason,
                "preview_api": api_result,
                "capture": capture,
                "pdf_ocr": pdf_ocr,
            }
        )

    readable_statuses = {"ok", "pdf_ocr_ok"}
    target_status = "ok" if any(item.get("status") in readable_statuses for item in attachment_results) else "no_readable_attachment_text"
    return {
        "target": target,
        "content_id": content_id,
        "status": target_status,
        "page": page,
        "attachments_total": len(page.get("files") or []),
        "attachment_results": attachment_results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", action="append", help="Qianlima detail URL. Can be passed multiple times.")
    parser.add_argument("--vip-json", help="VIP body-read JSON. Default reads latest_vip_read_path.txt.")
    parser.add_argument("--all-vip-projects", action="store_true", help="Read every project in vip-json, not only attachment_preview_required ones.")
    parser.add_argument("--run-date", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--output", help="Explicit output JSON path. Default creates output/v2_4/附件预览正文读取_YYYYMMDD_vNN.json.")
    parser.add_argument("--max-files", type=int, default=5)
    parser.add_argument("--no-pdf-ocr", action="store_true", help="Disable PDF canvas OCR fallback.")
    parser.add_argument("--ocr-min-chars", type=int, default=200)
    parser.add_argument("--ocr-max-pages", type=int, default=6)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_vip_json = ""
    if args.url:
        targets = [{"title": url.rsplit("/", 1)[-1], "url": url, "reason": "manual url"} for url in args.url]
    else:
        vip_path = Path(args.vip_json) if args.vip_json else find_latest_vip_json()
        source_vip_json = str(vip_path)
        targets = targets_from_vip_json(vip_path, required_only=not args.all_vip_projects)
        if not targets:
            targets = DEFAULT_TARGETS
    output_path = Path(args.output) if args.output else next_output_path(args.run_date)
    output = {
        "version": "attachment_preview_read_20260602_v05",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "browser_session": SESSION,
        "browser_group_title": GROUP_TITLE,
        "source_vip_json": source_vip_json,
        "pdf_ocr_enabled": not args.no_pdf_ocr,
        "ocr_min_chars": args.ocr_min_chars,
        "ocr_max_pages": args.ocr_max_pages,
        "targets_total": len(targets),
        "summary": {},
        "results": [],
    }

    for idx, target in enumerate(targets, 1):
        print(f"[{idx}/{len(targets)}] {target['title']}")
        try:
            item = read_target(
                target,
                first=(idx == 1),
                max_files=args.max_files,
                enable_pdf_ocr=not args.no_pdf_ocr,
                ocr_min_chars=args.ocr_min_chars,
                ocr_max_pages=args.ocr_max_pages,
            )
        except Exception as exc:
            item = {"target": target, "status": "error", "error": str(exc), "attachment_results": []}
        output["summary"][item["status"]] = output["summary"].get(item["status"], 0) + 1
        output["results"].append(item)
        print(f"  -> {item['status']}")
        for result in item.get("attachment_results", []):
            file_name = (result.get("file") or {}).get("fileName", "")
            capture = result.get("capture") or {}
            pdf_ocr = result.get("pdf_ocr") or {}
            ocr_len = pdf_ocr.get("textLength", 0)
            print(f"     {result.get('status')} len={capture.get('textLength', 0)} ocr={ocr_len} {file_name[:60]}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    pointers = write_pointer(output_path)
    print(f"saved: {output_path}")
    print("pointers:")
    for pointer in pointers:
        print(f"  - {pointer}")
    print(output["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
