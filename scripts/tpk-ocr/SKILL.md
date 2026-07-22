---
name: tpk-ocr
description: Use local PaddleOCR to extract Chinese and English text from screenshots, images, scanned PDFs, bid notices, certificate images, website screenshots, and table-like document images.
metadata:
  openclaw:
    skillKey: tpk-ocr
    primaryEnv: TPK_OCR_LANG
requirements:
  binaries:
    - python
---

# TPK OCR Skill

Use this skill when the user asks to extract, read, copy, recognize, or convert text from:

- screenshots
- website screenshots
- scanned PDFs
- PDF page images
- bid notice screenshots
- procurement / tender pages
- certificate images
- table-like images
- mixed Chinese and English documents

This skill runs OCR locally through PaddleOCR. It is designed for Chinese + English mixed engineering, bidding, certification, and website-document workflows.

## Primary commands

For one image:

```bash
python scripts/ocr_image.py "<image_path>" --lang ch --format md
```

For one image and save output:

```bash
python scripts/ocr_image.py "<image_path>" --lang ch --format md --output "ocr_result.md"
```

For a scanned PDF:

```bash
python scripts/ocr_pdf.py "<pdf_path>" --pages all --dpi 220 --lang ch --format md --output "ocr_result.md"
```

For selected PDF pages:

```bash
python scripts/ocr_pdf.py "<pdf_path>" --pages 1-3,5 --dpi 220 --lang ch --format md
```

## Language settings

Default language is `ch`, which is suitable for Chinese + English mixed text.

Use `--lang en` only when the document is purely English and Chinese recognition is not needed.

## Output rules

- Preserve original line order as much as possible.
- Keep important numbers, dates, amounts, model numbers, certification numbers, URLs, and project names exactly as OCR returned them.
- Do not summarize the OCR result unless the user asks.
- If the user asks for Markdown, return readable Markdown.
- If the user asks for raw OCR, return plain text.
- If the user asks for structured extraction, first OCR the source, then extract fields from the OCR text.
- If text looks like a table, keep line breaks and spacing; only convert to a Markdown table when the column structure is clear.
- If OCR confidence is low, explicitly mark uncertain lines and ask for a clearer screenshot only when necessary.

## Recommended workflow

1. Check whether the input is an image or PDF.
2. If it is a PDF with selectable text, prefer normal text extraction first.
3. If it is scanned, image-only, blurry, or a screenshot, use this OCR skill.
4. For screenshots, prefer high-resolution images. Browser zoom at 125% or 150% usually improves OCR.
5. For long bid documents, OCR only the relevant pages first, then expand if needed.

## Common usage examples

Read a bidding website screenshot:

```bash
python scripts/ocr_image.py "bid_screenshot.png" --lang ch --format md
```

Read a certificate image:

```bash
python scripts/ocr_image.py "etl_certificate.jpg" --lang ch --format json --output "etl_certificate_ocr.json"
```

Read pages 2 to 5 of a scanned PDF:

```bash
python scripts/ocr_pdf.py "tender.pdf" --pages 2-5 --dpi 240 --lang ch --format md --output "tender_pages_2_5.md"
```

## Troubleshooting

- If Chinese characters are missing, use `--lang ch`.
- If the image is very small, ask the user for a higher-resolution screenshot or render the PDF at a higher DPI.
- If the result has many wrong characters, retry with `--dpi 260` for PDFs.
- If the PDF is huge, process page ranges instead of all pages.
- If PaddleOCR model files are downloading during first use, wait for the first run to complete; later runs are faster.
