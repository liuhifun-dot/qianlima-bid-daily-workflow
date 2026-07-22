# ISSUE-20260714-attach-rename

| 字段 | 内容 |
|:---|:---|
| **记录时间** | 2026-07-14 |
| **状态** | resolved |
| **优先级** | P1 |
| **节点** | Phase2B |
| **脚本/模块** | `qianlima_cdp_body_attachment_reader_20260624_v05.py` |
| **标签** | `attachment` `windows` |

## 1. 问题

needs_retry 第二次下载同 PDF 时 `Path.rename` 目标已存在 → WinError 183 → VIP status=error → blocked。

## 2. 解法

目标已存在则复用/覆盖，避免裸 rename。

## 3. 验证

修复后同 run 重试不再 183；全量附件 OCR 仍弱（另案）。
