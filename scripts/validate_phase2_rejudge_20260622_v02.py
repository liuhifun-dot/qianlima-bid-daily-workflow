# -*- coding: utf-8 -*-
"""
Validate Phase 2 business rejudge JSON before report generation.

Automation gates:
- final_decision must be keep / needs_review / reject;
- attachment_required=true and attachment_read_ok=false always forces needs_review;
- keep always requires body_read_ok=true;
- keep/reject must carry non-empty evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


KEEP_TEXT = {"keep", "recommend", "recommended", "推荐", "推荐候选"}
REVIEW_TEXT = {"needs_review", "review", "pending_review", "待人工复核", "待复核", "待定"}
REJECT_TEXT = {"reject", "excluded", "exclude", "排除", "放弃"}
FORBIDDEN_DECISION_TEXT = {"确认投标", "确认跟进"}
BAD_VIP_STATUSES = {"need_login", "captcha", "error", "login_timeout"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def flatten_results(data: dict) -> list[dict]:
    if isinstance(data.get("results"), list):
        return data["results"]

    rows: list[dict] = []
    for section in ["recommendations", "pending_review", "exclusions"]:
        value = data.get(section, {})
        if isinstance(value, dict):
            for tag, item in value.items():
                if isinstance(item, dict):
                    row = dict(item)
                    row.setdefault("tag", str(tag))
                    rows.append(row)
        elif isinstance(value, list):
            rows.extend([item for item in value if isinstance(item, dict)])
    return rows


def normalized_decision(item: dict) -> str:
    raw = str(item.get("final_decision") or item.get("decision") or "").strip()
    if raw in FORBIDDEN_DECISION_TEXT:
        return "forbidden"
    if raw in KEEP_TEXT:
        return "keep"
    if raw in REVIEW_TEXT:
        return "needs_review"
    if raw in REJECT_TEXT:
        return "reject"
    return raw


def evidence_text(item: dict) -> str:
    evidence = item.get("evidence", "")
    if isinstance(evidence, list):
        parts = []
        for part in evidence:
            if isinstance(part, dict):
                parts.append(str(part.get("snippet") or part.get("text") or part.get("evidence") or ""))
            else:
                parts.append(str(part))
        return "\n".join(p for p in parts if p).strip()
    return str(evidence or "").strip()


def attachment_required(item: dict) -> bool:
    return bool(
        item.get("attachment_required")
        or item.get("needs_attachment_read")
        or item.get("attachment_must_read")
    )


def has_hard_screening_reject(item: dict) -> bool:
    bucket = str(
        item.get("screening_bucket")
        or item.get("source_bucket")
        or item.get("screening_decision")
        or item.get("initial_decision")
        or item.get("source_decision")
        or item.get("initial_category")
        or item.get("screening_category")
        or ""
    ).lower()
    if bucket in {"excluded", "exclude", "low_score", "low"}:
        return True
    # rejudge excluded rows may use screening_exclude_reason / exclude_hits
    reason = str(
        item.get("exclude_reason")
        or item.get("screening_reason")
        or item.get("screening_exclude_reason")
        or ""
    ).strip()
    if not reason and item.get("exclude_hits"):
        reason = str(item.get("exclude_hits"))
    return bool(reason and not item.get("body_read_ok"))


def validate(path: Path, vip_path: Path | None = None) -> dict:
    data = load_json(path)
    rows = flatten_results(data)
    errors: list[str] = []
    warnings: list[str] = []

    if not rows:
        errors.append("Phase 2 JSON has no project rows.")

    # 判定当天是否为“合法全排除”场景：
    # 所有行均为 reject 且都带硬筛选理由（Phase 2A 硬规则排除），
    # 此时根本没有项目需要读 VIP 正文，VIP JSON 为空是正常结果，不应逼迫造数据。
    all_hard_reject = bool(rows) and all(
        normalized_decision(item) == "reject" and has_hard_screening_reject(item)
        for item in rows
    )
    needs_vip_body = any(
        normalized_decision(item) in {"keep", "needs_review"}
        for item in rows
    )

    if vip_path:
        vip_data = load_json(vip_path)
        vip_projects = vip_data.get("projects") or []
        vip_summary = vip_data.get("summary") or {}
        # blocking 状态（need_login/captcha/error/login_timeout）任何时候都必须拦截
        blocking = {k: int(vip_summary.get(k) or 0) for k in BAD_VIP_STATUSES if int(vip_summary.get(k) or 0)}
        if blocking:
            errors.append(f"VIP body JSON has blocking statuses: {blocking}.")
        if not vip_projects:
            legal_empty_flag = bool(vip_data.get("legal_empty"))
            if legal_empty_flag or (all_hard_reject and not needs_vip_body):
                # 合法全排除：无项目需读正文，VIP 空是正常的，降级为 warning 放行
                warnings.append(
                    f"VIP body JSON has no projects: {vip_path}. "
                    "Phase 2A 全部硬规则排除或 legal_empty=true，无项目需要读取 VIP 正文，判定为合法空结果。"
                )
            else:
                errors.append(
                    f"VIP body JSON has no projects: {vip_path}. Phase 2B did not actually read VIP bodies."
                )

    for idx, item in enumerate(rows, 1):
        tag = str(item.get("tag") or item.get("index") or idx)
        title = str(item.get("title") or "").strip()
        decision = normalized_decision(item)
        if not title:
            errors.append(f"[{tag}] missing title.")
        if decision == "forbidden":
            errors.append(f"[{tag}] final decision uses forbidden wording; use 推荐候选/待人工复核/排除.")
            continue
        if decision not in {"keep", "needs_review", "reject"}:
            errors.append(f"[{tag}] invalid or missing final decision: {decision!r}.")
            continue

        if attachment_required(item) and not bool(item.get("attachment_read_ok")):
            if decision != "needs_review":
                errors.append(
                    f"[{tag}] attachment is required but not read; final decision must be needs_review."
                )
            if decision == "needs_review" and not str(
                item.get("manual_review_reason")
                or item.get("manual_action_required")
                or item.get("review_reason")
                or item.get("attachment_error")
                or ""
            ).strip():
                warnings.append(f"[{tag}] attachment failed but review reason is weak.")
        if decision in {"keep", "reject"} and not evidence_text(item):
            errors.append(f"[{tag}] {decision} item has empty evidence.")

        if decision == "keep" and not bool(item.get("body_read_ok")):
            errors.append(f"[{tag}] recommended item has body_read_ok=false; cannot recommend without VIP body evidence.")

        vip_status = str(item.get("vip_status") or item.get("body_read_status") or "").strip()
        if vip_status in BAD_VIP_STATUSES:
            errors.append(f"[{tag}] VIP body read status is {vip_status}; Phase 2 must stop before final report.")

        if decision == "reject" and not bool(item.get("body_read_ok")) and vip_status in {"", "missing"}:
            if not has_hard_screening_reject(item):
                errors.append(
                    f"[{tag}] reject item has no VIP body and vip_status={vip_status!r}; "
                    "needs an explicit hard-screening reason."
                )

    return {
        "ok": not errors,
        "path": str(path),
        "rows": len(rows),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 2 rejudge JSON v02 with strict attachment evidence gate.")
    parser.add_argument("--business-json", required=True, help="Phase 2 final rejudge JSON path")
    parser.add_argument("--vip-json", help="VIP body read JSON path; required for formal automation gates")
    parser.add_argument("--output", help="Optional validation result JSON path")
    args = parser.parse_args()

    result = validate(Path(args.business_json), Path(args.vip_json) if args.vip_json else None)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8-sig")
    print(text)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
