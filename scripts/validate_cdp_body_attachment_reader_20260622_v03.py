# -*- coding: utf-8 -*-
"""Validate CDP body and attachment evidence without accepting false success."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

MIN_BODY_CHARS = 200
MIN_ATTACHMENT_CHARS = 80
VALID_VIP_STATUSES = {
    "ok", "need_login", "captcha", "body_empty", "blocked",
    "missing_detail_url", "error",
}
VALID_ATTACHMENT_STATUSES = {
    "complete", "partial", "no_attachment", "unreadable",
    "need_login", "captcha", "blocked", "missing_detail_url", "error",
}


def compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def key_of(item: Dict[str, Any]) -> str:
    return str(item.get("url") or item.get("bid_id") or item.get("title") or "").strip()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def input_projects(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = []
        found = False
        for name in ("recommended", "considered", "low_score", "projects", "items", "results"):
            value = data.get(name)
            if isinstance(value, list):
                found = True
                rows.extend(value)
        if not found and all(isinstance(value, dict) for value in data.values()):
            rows = list(data.values())
    else:
        rows = []
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = key_of(row)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(row)
    return result


def validate(input_rows: List[Dict[str, Any]], vip_rows: List[Dict[str, Any]],
             attachment_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    retry_reasons: List[str] = []
    blocked_reasons: List[str] = []

    if len(input_rows) != len(vip_rows):
        errors.append(f"input_count={len(input_rows)} but vip_count={len(vip_rows)}")
    if len(input_rows) != len(attachment_rows):
        errors.append(f"input_count={len(input_rows)} but attachment_count={len(attachment_rows)}")

    input_keys = {key_of(row) for row in input_rows if key_of(row)}
    vip_keys = {key_of(row) for row in vip_rows if key_of(row)}
    attachment_keys = {key_of(row) for row in attachment_rows if key_of(row)}
    if input_keys != vip_keys:
        errors.append("VIP output project IDs do not exactly match input.")
    if input_keys != attachment_keys:
        errors.append("Attachment output project IDs do not exactly match input.")

    for index, item in enumerate(vip_rows, start=1):
        tag = f"vip[{index}] {key_of(item)}"
        status = item.get("status")
        if status not in VALID_VIP_STATUSES:
            errors.append(f"{tag}: invalid status={status}")
            continue

        if item.get("body_read_ok"):
            if not item.get("body_identity_ok"):
                errors.append(f"{tag}: body_read_ok=true but body_identity_ok=false")
            length = len(compact(item.get("body_text")))
            if length < MIN_BODY_CHARS:
                errors.append(f"{tag}: body_read_ok=true but effective body text is {length} chars")
            if status != "ok":
                errors.append(f"{tag}: body_read_ok=true but status={status}")
        else:
            if not item.get("body_invalid_reason") and not item.get("error"):
                errors.append(f"{tag}: body failure has no reason")
            if status in {"need_login", "body_empty"}:
                retry_reasons.append(f"{tag}: status={status}; restore state and retry this project once")
            elif status in {"captcha", "blocked", "missing_detail_url", "error"}:
                blocked_reasons.append(f"{tag}: status={status}")
            elif status == "ok":
                retry_reasons.append(f"{tag}: status=ok but body_read_ok=false")

        if status in {"need_login", "captcha"} and item.get("body_read_ok"):
            errors.append(f"{tag}: login/captcha page cannot be body evidence")

    for index, item in enumerate(attachment_rows, start=1):
        tag = f"attachment[{index}] {key_of(item)}"
        status = item.get("attachment_status")
        if status not in VALID_ATTACHMENT_STATUSES:
            errors.append(f"{tag}: invalid attachment_status={status}")
        attachments = item.get("attachments")
        if not isinstance(attachments, list):
            errors.append(f"{tag}: attachments must be a list")
            attachments = []
        successful = 0
        unresolved = 0  # 阻塞性未读（非签章/可选）
        any_unread = 0
        for child_index, child in enumerate(attachments, start=1):
            child_tag = f"{tag}/file[{child_index}]"
            effective = len(compact(child.get("text")))
            if child.get("text_read_ok"):
                successful += 1
                if effective < MIN_ATTACHMENT_CHARS:
                    errors.append(f"{child_tag}: text_read_ok=true but only {effective} effective chars")
                if child.get("ocr_required"):
                    errors.append(f"{child_tag}: OCR required cannot be marked text_read_ok")
            else:
                any_unread += 1
                optional = bool(child.get("optional_non_body") or child.get("skipped"))
                if not optional:
                    unresolved += 1
                if not child.get("error"):
                    errors.append(f"{child_tag}: unreadable attachment has no reason")
            if child.get("download_ok") and not child.get("sha256"):
                errors.append(f"{child_tag}: downloaded file has no SHA256")

        if item.get("attachment_count") != len(attachments):
            errors.append(f"{tag}: attachment_count mismatch")
        if item.get("attachment_read_ok_count") != successful:
            errors.append(f"{tag}: attachment_read_ok_count mismatch")
        # unresolved_count：兼容 total unread；若有 blocking 字段则以 blocking 为准
        reported_unresolved = item.get("attachment_unresolved_count")
        reported_blocking = item.get("attachment_blocking_unresolved_count")
        if reported_blocking is not None:
            if reported_blocking != unresolved:
                errors.append(
                    f"{tag}: attachment_blocking_unresolved_count mismatch "
                    f"(got {reported_blocking}, expect {unresolved})"
                )
        elif reported_unresolved is not None and reported_unresolved != any_unread:
            # 旧字段：按「全部未读」计
            if reported_unresolved != unresolved and reported_unresolved != any_unread:
                errors.append(f"{tag}: attachment_unresolved_count mismatch")
        if item.get("attachment_read_ok"):
            # 有正文级文本且无阻塞性缺口即可；签章/可选未读不否定 complete
            if not attachments or not successful or unresolved:
                errors.append(f"{tag}: attachment_read_ok=true but evidence is incomplete")
            if status != "complete":
                errors.append(f"{tag}: attachment_read_ok=true but status={status}")
        if item.get("attachment_required") and not item.get("attachment_read_ok"):
            if not item.get("error"):
                errors.append(f"{tag}: required attachment evidence is incomplete without reason")
            warnings.append(f"{tag}: final decision must be needs_review")
            if status in {"need_login"}:
                retry_reasons.append(f"{tag}: required attachment status={status}")
            elif status in {"captcha", "blocked", "missing_detail_url", "error"}:
                blocked_reasons.append(f"{tag}: required attachment status={status}")
            else:
                warnings.append(f"{tag}: structured attachment gap accepted for Phase 2D needs_review gate")

    required_count = sum(bool(row.get("attachment_required")) for row in attachment_rows)
    read_ok_count = sum(bool(row.get("attachment_read_ok")) for row in attachment_rows)
    systemic_attachment_failure = required_count > 0 and read_ok_count == 0
    if systemic_attachment_failure:
        # 按 SKILL.md 规则：附件读取失败应进 needs_review，不是 blocked
        # 只在有明确 errors 时才 blocked
        warnings.append(
            f"systemic attachment evidence gap: required={required_count}, read_ok=0; Phase 2D will mark as needs_review"
        )

    if errors or blocked_reasons:
        status = "blocked"
    elif retry_reasons:
        status = "needs_retry"
    else:
        status = "ok"

    return {
        "status": status,
        "ok": status == "ok",
        "needs_retry": status == "needs_retry",
        "blocked": status == "blocked",
        "errors": errors,
        "warnings": warnings,
        "retry_reasons": retry_reasons,
        "blocked_reasons": blocked_reasons,
        "systemic_attachment_failure": systemic_attachment_failure,
        "stats": {
            "input_count": len(input_rows),
            "vip_count": len(vip_rows),
            "attachment_count": len(attachment_rows),
            "body_read_ok_count": sum(bool(row.get("body_read_ok")) for row in vip_rows),
            "need_login_count": sum(row.get("status") == "need_login" for row in vip_rows),
            "body_empty_count": sum(row.get("status") == "body_empty" for row in vip_rows),
            "attachment_required_count": required_count,
            "attachment_read_ok_count": read_ok_count,
        },
    }

def unwrap_vip(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict):
        return data.get("projects") or []
    return data if isinstance(data, list) else []


def unwrap_attachments(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict):
        return data.get("results") or []
    return data if isinstance(data, list) else []


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CDP body/attachment evidence v03")
    parser.add_argument("--input", required=True, help="Phase 2A input JSON")
    parser.add_argument("--vip-json", required=True)
    parser.add_argument("--attachment-json", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = validate(
        input_projects(load_json(Path(args.input))),
        unwrap_vip(load_json(Path(args.vip_json))),
        unwrap_attachments(load_json(Path(args.attachment_json))),
    )
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
