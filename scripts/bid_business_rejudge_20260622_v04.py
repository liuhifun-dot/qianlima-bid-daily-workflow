# -*- coding: utf-8 -*-
r"""
2B 业务复判入口。

目标：
- 承接第二步筛选 JSON、VIP 正文读取 JSON 和附件预览/OCR JSON。
- 有正文时使用正文证据；没有正文时明确标记 need_vip_text，不把标题规则伪装成正文判断。
- 输出给第三步存档/钉钉前使用的结构化复判结果。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from bid_business_rules_20260602_v02 import classify_business_opportunity, trim_qianlima_text


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output" / "v2_4"
PIPELINE_OUTPUT_DIR = PROJECT_DIR / "output"

def read_pointer(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").strip().strip('"').lstrip("\ufeff")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def find_latest(pointer_names, glob_pattern):
    candidates = []
    for name in pointer_names:
        candidates.extend([
            OUTPUT_DIR / name,
            PIPELINE_OUTPUT_DIR / name,
        ])
    for pointer in candidates:
        if pointer.exists():
            target = Path(read_pointer(pointer))
            if target.exists():
                return target
            raise FileNotFoundError(f"指针存在但目标不存在: {pointer} -> {target}")

    files = sorted(OUTPUT_DIR.glob(glob_pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if files:
        return files[0]
    raise FileNotFoundError(f"找不到 {glob_pattern}")


def next_output_path(run_date: str):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(rf"^业务复判结果_{re.escape(run_date)}_v(\d+)\.json$")
    versions = []
    for p in OUTPUT_DIR.glob(f"业务复判结果_{run_date}_v*.json"):
        m = pattern.match(p.name)
        if m:
            versions.append(int(m.group(1)))
    return OUTPUT_DIR / f"业务复判结果_{run_date}_v{max(versions, default=0) + 1:02d}.json"


def write_pointer(output_path: Path):
    pointers = [
        OUTPUT_DIR / "latest_business_review_path.txt",
        PIPELINE_OUTPUT_DIR / "latest_business_review_path.txt",
    ]
    for pointer in pointers:
        pointer.write_text(str(output_path), encoding="utf-8")
    return pointers


def trim_page_tail(text: str) -> str:
    """去掉千里马正文后的商机推荐/站点页脚，避免相关商机污染业务判断。"""
    return trim_qianlima_text(text)


def normalize_vip_projects(vip_data):
    by_url = {}
    for item in vip_data.get("projects", []):
        url = item.get("url")
        if url:
            by_url[url] = item
    return by_url


def normalize_match_key(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def normalize_attachment_projects(attachment_data):
    by_url = {}
    by_title = {}
    for item in attachment_data.get("results", []):
        target = item.get("target") or {}
        url = target.get("url") or item.get("url")
        title = target.get("title") or item.get("title")
        if url:
            by_url[url] = item
        if title:
            by_title[normalize_match_key(title)] = item
    return by_url, by_title



BAD_VIP_STATUSES = {"need_login", "captcha", "body_empty", "blocked", "missing_detail_url", "error"}
# Only systemic auth/security failures should abort the whole rejudge batch.
SYSTEMIC_VIP_BLOCK = {"need_login", "captcha", "login_timeout"}


def screening_needs_vip_body(screening: dict | None) -> bool:
    if not screening:
        return False
    for key in ("recommended", "considered", "low_score"):
        rows = screening.get(key) or []
        if isinstance(rows, list) and rows:
            return True
    return False


def assert_vip_read_is_usable(
    vip_data: dict,
    vip_path: Path | None,
    allow_incomplete: bool = False,
    screening: dict | None = None,
):
    """Gate VIP evidence for formal rejudge.

    P0 policy (2026-07-13):
    - Missing VIP path is still fatal.
    - Empty VIP is legal when Phase 2A has no VIP targets (full hard exclude) or legal_empty=true.
    - Systemic need_login/captcha with zero successful body reads aborts the batch.
    - Per-item body_empty / partial failure does NOT abort; judge_item marks needs_review.
    """
    if allow_incomplete:
        return
    if not vip_path:
        raise RuntimeError("缺少 VIP 正文读取 JSON，禁止生成最终业务复判。请先完成 2B/2C 正文读取。")
    summary = vip_data.get("summary") or {}
    projects = vip_data.get("projects") or []
    legal_empty = bool(vip_data.get("legal_empty"))

    if not projects:
        if legal_empty or not screening_needs_vip_body(screening):
            return
        raise RuntimeError(
            "VIP 正文读取 JSON 没有任何项目，但初筛仍有待读项目，禁止进入最终复判。"
            "这通常表示 CDP 未登录、读取脚本未真正跑到详情页，或正文读取链路失效。"
        )

    systemic = {
        k: int(summary.get(k) or 0)
        for k in SYSTEMIC_VIP_BLOCK
        if int(summary.get(k) or 0)
    }
    ok_count = int(summary.get("ok") or 0)
    if not ok_count:
        ok_count = sum(1 for item in projects if item.get("body_read_ok") or item.get("status") == "ok")

    # Entire batch failed auth/captcha — hard stop (cannot produce reliable keep/reject).
    if systemic and ok_count == 0:
        sample = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "status": item.get("status"),
            }
            for item in projects
            if item.get("status") in SYSTEMIC_VIP_BLOCK
        ][:5]
        raise RuntimeError(
            "VIP 正文读取存在系统性登录失效或验证码，且无任何成功正文，禁止进入最终复判。"
            f" summary={json.dumps(systemic, ensure_ascii=False)} "
            f" sample={json.dumps(sample, ensure_ascii=False)}"
        )
    # Per-item gaps intentionally fall through to judge_item -> needs_review.


def extract_attachment_text(attachment_item) -> str:
    if not attachment_item:
        return ""
    parts = []
    for result in attachment_item.get("attachment_results", []):
        capture = result.get("capture") or {}
        pdf_ocr = result.get("pdf_ocr") or {}
        for value in [
            capture.get("text"),
            capture.get("textPreview"),
            pdf_ocr.get("text"),
            pdf_ocr.get("textPreview"),
        ]:
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
    return "\n".join(parts)


# 无效附件文本标志：只读到这些内容不算有效招标文件文本
INVALID_ATTACHMENT_MARKERS = [
    "资格承诺函", "委托代理协议", "项目委托代理协议",
    "toolbar", "工具栏", "预览不支持",
]

# 有效招标文件文本标志：包含这些词才算有效
VALID_ATTACHMENT_MARKERS = [
    "招标文件", "磋商文件", "谈判文件", "询价文件", "采购文件",
    "工程量清单", "技术规范", "技术要求", "技术规格",
    "招标范围", "采购内容", "建设内容", "工程内容",
    "灯具", "照明", "路灯", "亮化", "LED",
    "施工工期", "工期", "质保期", "质量要求",
]


def is_valid_attachment_text(text: str) -> bool:
    """附件必须读到招标文件/技术规范/工程量清单级正文，不能只读到预览工具栏、资格承诺函或委托代理协议。"""
    if not text or len(text.strip()) < 300:
        return False
    invalid_markers = [
        "正在加载", "上一页", "下一页", "放大", "缩小", "仅供预览", "无法预览", "请下载",
    ]
    admin_only_markers = [
        "资格承诺函", "投标人资格", "授权委托书", "法定代表人证明",
        "委托代理协议", "代理协议", "廉洁承诺书",
    ]
    tender_markers = [
        "招标文件", "采购文件", "竞争性磋商文件", "竞争性谈判文件",
        "询价文件", "工程量清单", "技术规范", "技术要求", "用户需求书",
        "采购需求", "项目需求", "施工图", "图纸", "合同主要条款",
    ]
    scope_markers = [
        "施工范围", "工程内容", "建设内容", "采购内容", "工作内容",
        "清单", "控制价", "报价清单", "安装", "调试", "验收",
        "灯具", "照明", "路灯", "亮化", "光伏", "充电桩",
    ]
    compact = text.strip()
    if any(marker in compact for marker in invalid_markers) and len(compact) < 800:
        return False
    has_tender_marker = any(marker in compact for marker in tender_markers)
    has_scope_marker = any(marker in compact for marker in scope_markers)
    has_admin_marker = any(marker in compact for marker in admin_only_markers)
    if has_admin_marker and not (has_tender_marker and has_scope_marker):
        return False
    return has_tender_marker and has_scope_marker



def screening_items(screening):
    items = []
    for category in ["recommended", "considered", "low_score", "excluded"]:
        for item in screening.get(category, []):
            item = dict(item)
            item["_screening_category"] = category
            items.append(item)
    return items


def screening_excluded_judgment(item):
    reason = (
        item.get("exclude_reason")
        or item.get("reject_reason")
        or item.get("reason")
        or "初筛阶段已排除，未进入 VIP 正文读取范围"
    )
    scores = item.get("scores") or {}
    score_text = ""
    if isinstance(scores, dict) and scores:
        score_text = "；评分：" + "，".join(
            f"{key}={value}" for key, value in scores.items() if value not in (None, "")
        )
    evidence_text = f"初筛排除依据：{reason}{score_text}".strip()
    return {
        "recommendation_level": "D",
        "decision": "reject",
        "final_decision": "reject",
        "project_type": "初筛排除",
        "business_direction": "初筛排除项",
        "doable_scope": "",
        "judgment_reason": evidence_text,
        "reason": evidence_text,
        "needs_vip_text": False,
        "manual_review_reason": "",
        "scope_hits": [],
        "product_hits": [],
        "construction_hits": [],
        "broad_recall_hits": [],
        "exclude_hits": [str(reason)],
        "display_hits": [],
        "maintenance_hits": [],
        "risk_points": [evidence_text],
        "evidence": [{"keyword": "初筛排除", "snippet": evidence_text}],
        "vip_status": "not_required_initial_excluded",
        "body_read_ok": False,
        "attachment_status": "not_required_initial_excluded",
        "attachment_text_used": False,
        "attachment_required": False,
        "attachment_read_ok": False,
        "exclude_reason": reason,
        "screening_reason": reason,
        "screening_exclude_reason": reason,
        "initial_category": "excluded",
        "screening_category": "excluded",
        "screening_bucket": "excluded",
    }


def normalize_decision_contract(judgment):
    decision = judgment.get("decision")
    if decision == "provisional_keep":
        judgment["decision"] = "needs_review"
        judgment["final_decision"] = "needs_review"
        judgment["manual_review_reason"] = (
            judgment.get("manual_review_reason")
            or "标题/摘要命中业务范围，但正文未读取成功，不能自动推荐"
        )
        judgment["judgment_reason"] = (
            judgment.get("judgment_reason")
            or "正文缺失，需人工复核后再决定是否推荐候选"
        )
        judgment["reason"] = judgment["judgment_reason"]
        if not judgment.get("evidence"):
            judgment["evidence"] = [{
                "keyword": "正文缺失",
                "snippet": judgment["manual_review_reason"],
            }]
        return judgment
    judgment.setdefault("final_decision", decision)
    return judgment


def text_preview_for_evidence(*values: str, limit: int = 180) -> str:
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if text:
            return text[:limit]
    return ""


def complete_evidence_contract(judgment, *, title: str, preview: str, body_text: str, vip_status: str):
    """Fill evidence/body flags required by the Phase 2 validator without weakening validation."""
    body_read_ok = vip_status == "ok" and bool(str(body_text or "").strip())
    judgment["body_read_ok"] = body_read_ok

    decision = judgment.get("decision")
    if decision == "reject" and not judgment.get("evidence"):
        reason = (
            judgment.get("judgment_reason")
            or judgment.get("reason")
            or "未发现照明/路灯/亮化/户外灯具/分布式光伏施工等可做业务证据"
        )
        checked_text = text_preview_for_evidence(body_text, preview, title)
        if checked_text:
            snippet = f"{reason}；已核查材料摘录：{checked_text}"
        else:
            snippet = f"{reason}；无可用正文摘录，需确认正文读取链路是否完整"
            if vip_status != "ok":
                judgment["decision"] = "needs_review"
                judgment["final_decision"] = "needs_review"
                judgment["manual_review_reason"] = (
                    judgment.get("manual_review_reason")
                    or f"VIP正文状态为 {vip_status}，不能自动排除"
                )
                judgment["reason"] = judgment["manual_review_reason"]
                judgment["judgment_reason"] = judgment["manual_review_reason"]
                judgment["evidence"] = [{"keyword": "正文未读", "snippet": judgment["manual_review_reason"]}]
                return judgment
        judgment["evidence"] = [{"keyword": "排除依据", "snippet": snippet}]
    return judgment


def screening_low_score_judgment(item):
    """Handle low_score items: treated as initial screening exclusion per加强版规则1."""
    scores = item.get("scores") or {}
    total_score = scores.get("总分") or scores.get("原始总分") or "N/A"
    matched_kw = item.get("matched_related_kw") or item.get("matched_core_kw") or []
    kw_text = "、".join(matched_kw[:5]) if matched_kw else "无"
    recall = item.get("recall_basis", "")
    reason = f"初筛评分不足（总分{total_score}），未达推荐阈值；命中关键词：{kw_text}；召回依据：{recall}"
    score_detail = ""
    if isinstance(scores, dict) and scores:
        score_detail = "；评分明细：" + "，".join(
            f"{key}={value}" for key, value in scores.items()
            if value not in (None, "") and key not in ("原始总分",)
        )
    evidence_text = f"初筛排除依据：{reason}{score_detail}"
    return {
        "recommendation_level": "D",
        "decision": "reject",
        "final_decision": "reject",
        "project_type": "初筛低分",
        "business_direction": "初筛低分项",
        "doable_scope": "",
        "judgment_reason": evidence_text,
        "reason": evidence_text,
        "needs_vip_text": False,
        "manual_review_reason": "",
        "scope_hits": [],
        "product_hits": [],
        "construction_hits": [],
        "broad_recall_hits": [],
        "exclude_hits": [str(reason)],
        "display_hits": [],
        "maintenance_hits": [],
        "risk_points": [evidence_text],
        "evidence": [{"keyword": "初筛低分排除", "snippet": evidence_text}],
        "vip_status": "not_required_initial_excluded",
        "body_read_ok": False,
        "attachment_status": "not_required_initial_excluded",
        "attachment_text_used": False,
        "attachment_required": False,
        "attachment_read_ok": False,
        "screening_exclude_reason": reason,
        "initial_category": "low_score",
    }



ATTACHMENT_EVIDENCE_KEYWORDS = [
    "\u9644\u4ef6", "\u6e05\u5355", "\u9700\u6c42", "\u91c7\u8d2d\u9700\u6c42", "\u5de5\u7a0b\u91cf", "\u5de5\u7a0b\u91cf\u6e05\u5355",
    "\u62db\u6807\u6587\u4ef6", "\u8be2\u6bd4\u6587\u4ef6", "\u91c7\u8d2d\u6587\u4ef6", "\u6280\u672f\u89c4\u8303", "\u9879\u76ee\u8981\u6c42",
    "BOQ", "tender", "spec", "specification"
]
ATTACHMENT_GATE_REASON_CN = "\u9879\u76ee\u9700\u8981\u62db\u6807\u6587\u4ef6/\u91c7\u8d2d\u9700\u6c42/\u5de5\u7a0b\u91cf\u6e05\u5355\u4f5c\u4e3a\u8bc1\u636e\uff0c\u4f46\u9644\u4ef6\u6b63\u6587\u672a\u6210\u529f\u5b8c\u6574\u8bfb\u53d6\uff0c\u9700\u4eba\u5de5\u590d\u6838"
BODY_GATE_REASON_CN = "VIP\u6b63\u6587\u672a\u6210\u529f\u8bfb\u53d6\uff0c\u4e0d\u80fd\u81ea\u52a8\u63a8\u8350\uff0c\u9700\u4eba\u5de5\u590d\u6838"
VIP_MISSING_REASON_CN = "VIP\u6b63\u6587\u7f3a\u5931\uff0c\u4e0d\u80fd\u81ea\u52a8\u6392\u9664\uff0c\u9700\u4eba\u5de5\u590d\u6838"


def _as_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def _attachment_rows(attachment_item):
    item = attachment_item or {}
    rows = item.get("attachments") or item.get("attachment_results") or []
    return rows if isinstance(rows, list) else []


def _attachment_count(attachment_item, vip_item=None):
    item = attachment_item or {}
    direct = _as_int(item.get("attachment_count"), 0)
    if direct:
        return direct
    rows = _attachment_rows(item)
    if rows:
        return len(rows)
    vip = vip_item or {}
    vip_rows = vip.get("attachments") or vip.get("files") or []
    return len(vip_rows) if isinstance(vip_rows, list) else 0


def _attachment_read_ok_count(attachment_item):
    item = attachment_item or {}
    direct = _as_int(item.get("attachment_read_ok_count"), 0)
    if direct:
        return direct
    count = 0
    for row in _attachment_rows(item):
        if row.get("text_read_ok") or row.get("read_ok") or row.get("attachment_read_ok"):
            count += 1
    return count


def _attachment_unresolved_count(attachment_item):
    item = attachment_item or {}
    direct = _as_int(item.get("attachment_unresolved_count"), 0)
    if direct:
        return direct
    total = _attachment_count(item)
    return max(0, total - _attachment_read_ok_count(item))


def _attachment_text_from_rows(attachment_item):
    texts = []
    for row in _attachment_rows(attachment_item):
        value = row.get("text") or row.get("content") or row.get("parsed_text") or ""
        if isinstance(value, str) and value.strip():
            texts.append(value)
    return "\n".join(texts)


def _attachment_manifest(attachment_item):
    """Preserve page attachment names and links for the report layer."""
    output = []
    seen = set()
    for row in _attachment_rows(attachment_item):
        name = str(row.get("name") or row.get("filename") or "附件").strip()
        name = re.sub(r"(?:标书代写)?多份优惠", "", name).strip() or "附件"
        source_url = str(row.get("source_url") or row.get("href") or "").strip()
        real_url = str(row.get("real_url") or row.get("resolved_url") or "").strip()
        normalized_name = re.sub(r"\s+", "", name).casefold()
        generic_name = bool(re.fullmatch(r"附件(?:下载)?\d*", normalized_name))
        key = ("url", real_url or source_url) if generic_name else ("name", normalized_name)
        if not key[1] or key in seen:
            continue
        seen.add(key)
        output.append({
            "name": name,
            "source_url": source_url,
            "real_url": real_url,
            "file_type": str(row.get("type") or row.get("file_type") or "").strip(),
            "download_ok": bool(row.get("download_ok")),
            "text_read_ok": bool(row.get("text_read_ok") or row.get("read_ok")),
            "text_length": int(row.get("text_length") or 0),
            "error": str(row.get("error") or "").strip(),
        })
    return output


def _mentions_attachment_evidence(text):
    text = str(text or "")
    return any(keyword in text for keyword in ATTACHMENT_EVIDENCE_KEYWORDS)

def judge_item(item, vip_item=None, attachment_item=None):
    if item.get("_screening_category") == "excluded":
        return screening_excluded_judgment(item)
    if item.get("_screening_category") == "low_score":
        return screening_low_score_judgment(item)

    title = item.get("title", "")
    preview = item.get("preview", "") or item.get("content_preview", "")
    vip_status = (vip_item or {}).get("status", "missing")
    vip_content = (vip_item or {}).get("content") or ""
    vip_preview = (vip_item or {}).get("content_preview") or ""
    attachment_text = extract_attachment_text(attachment_item)
    body_text = trim_page_tail(f"{vip_content}\n{vip_preview}\n{attachment_text}".strip())
    judgment = classify_business_opportunity(
        title=title,
        preview=preview,
        body_text=body_text,
        vip_status=vip_status,
        screening_exclude_reason=item.get("exclude_reason", ""),
    ).to_dict()
    judgment = normalize_decision_contract(judgment)
    judgment = complete_evidence_contract(
        judgment,
        title=title,
        preview=preview,
        body_text=body_text,
        vip_status=vip_status,
    )
    judgment["reason"] = judgment["judgment_reason"]
    judgment["vip_status"] = vip_status
    raw_attachment_status = (attachment_item or {}).get("status", "missing")
    attachment_rows_text = _attachment_text_from_rows(attachment_item)
    if attachment_rows_text:
        attachment_text = (attachment_text + "\n" + attachment_rows_text).strip()
        body_text = trim_page_tail(f"{vip_content}\n{vip_preview}\n{attachment_text}".strip())

    page_attachment_count = _attachment_count(attachment_item, vip_item)
    page_attachment_read_ok_count = _attachment_read_ok_count(attachment_item)
    page_attachment_unresolved_count = _attachment_unresolved_count(attachment_item)
    visible_attachments = bool((vip_item or {}).get("attachments") or (vip_item or {}).get("files"))
    page_attachment_available = bool(
        (attachment_item or {}).get("attachment_available")
        or visible_attachments
        or page_attachment_count > 0
    )
    page_attachment_read_complete = bool((attachment_item or {}).get("attachment_read_ok"))
    page_attachment_read_any_ok = page_attachment_read_complete or page_attachment_read_ok_count > 0
    page_attachment_status = raw_attachment_status

    decision_now = judgment.get("decision") or judgment.get("final_decision")
    decision_needs_attachment_gate = decision_now in {"keep", "needs_review"}
    attachment_valid_text_ok = bool(
        is_valid_attachment_text(attachment_text)
        and (attachment_item or {}).get("attachment_read_ok") is not False
    )
    explicit_evidence_required = bool(
        judgment.get("attachment_required")
        or judgment.get("needs_attachment_read")
        or judgment.get("attachment_must_read")
        or judgment.get("has_attachment")
        or (attachment_item or {}).get("attachment_required")
        or (vip_item or {}).get("attachment_preview_required")
    )
    attachment_hint = _mentions_attachment_evidence(title) or _mentions_attachment_evidence(preview) or _mentions_attachment_evidence(body_text)
    evidence_required_flag = bool(
        explicit_evidence_required
        or (decision_needs_attachment_gate and page_attachment_available and attachment_hint)
    )
    evidence_read_ok = bool(evidence_required_flag and attachment_valid_text_ok)

    # Page layer: factual state of the attachment area, independent from business decision.
    judgment["page_attachment_available"] = page_attachment_available
    judgment["page_attachment_count"] = page_attachment_count
    judgment["page_attachment_status"] = page_attachment_status
    judgment["page_attachment_read_complete"] = page_attachment_read_complete
    judgment["page_attachment_read_any_ok"] = page_attachment_read_any_ok
    judgment["page_attachment_read_ok_count"] = page_attachment_read_ok_count
    judgment["page_attachment_unresolved_count"] = page_attachment_unresolved_count
    judgment["page_attachment_error"] = (attachment_item or {}).get("error", "")
    judgment["page_attachments"] = _attachment_manifest(attachment_item)
    judgment["progress_timeline"] = list((vip_item or {}).get("progress_timeline") or [])
    judgment["body_facts"] = dict((vip_item or {}).get("body_facts") or {})

    # Evidence layer: whether attachment evidence is required for this business judgment.
    judgment["evidence_required"] = evidence_required_flag
    judgment["evidence_read_ok"] = evidence_read_ok
    judgment["evidence_gap_reason"] = ATTACHMENT_GATE_REASON_CN if evidence_required_flag and not evidence_read_ok else ""

    # Compatibility fields kept for existing validators/report builders.
    judgment["attachment_available"] = page_attachment_available
    judgment["attachment_required"] = evidence_required_flag
    judgment["needs_attachment_read"] = evidence_required_flag
    judgment["attachment_flow_ok"] = page_attachment_read_any_ok
    judgment["attachment_valid_text_ok"] = attachment_valid_text_ok
    judgment["attachment_read_ok"] = evidence_read_ok
    judgment["attachment_effective_text_length"] = len(attachment_text.strip()) if attachment_valid_text_ok else 0
    if evidence_read_ok:
        judgment["attachment_status"] = "ok"
        judgment["attachment_invalid_reason"] = ""
    elif evidence_required_flag:
        judgment["attachment_status"] = page_attachment_status or "missing"
        judgment["attachment_invalid_reason"] = ATTACHMENT_GATE_REASON_CN
    else:
        judgment["attachment_status"] = page_attachment_status
        judgment["attachment_invalid_reason"] = ""

    if evidence_required_flag and not evidence_read_ok:
        judgment["decision"] = "needs_review"
        judgment["final_decision"] = "needs_review"
        judgment["recommendation_level"] = "C"
        missing_reason = ATTACHMENT_GATE_REASON_CN
        prior_reason = str(judgment.get("manual_review_reason") or "").strip(" ;?")
        judgment["manual_review_reason"] = (
            f"{prior_reason}; {missing_reason}" if prior_reason else missing_reason
        )
        base_reason = str(judgment.get("judgment_reason") or judgment.get("reason") or "").strip(" ;?")
        judgment["reason"] = f"{base_reason}; {missing_reason}" if base_reason else missing_reason
        evidence = judgment.setdefault("evidence", [])
        gate_evidence = {"keyword": "\u9644\u4ef6\u8bc1\u636e\u95e8\u69db", "snippet": missing_reason, "source": "phase2_gate"}
        if isinstance(evidence, list):
            evidence.append(gate_evidence)
        else:
            judgment["evidence"] = [gate_evidence]

    if not judgment.get("body_read_ok") and judgment.get("decision") == "keep":
        judgment["decision"] = "needs_review"
        judgment["final_decision"] = "needs_review"
        judgment["recommendation_level"] = "C"
        reason = BODY_GATE_REASON_CN
        prior_reason = str(judgment.get("manual_review_reason") or "").strip(" ;")
        judgment["manual_review_reason"] = (
            f"{prior_reason}; {reason}" if prior_reason else reason
        )
        base_reason = str(judgment.get("judgment_reason") or judgment.get("reason") or "").strip(" ;")
        judgment["reason"] = f"{base_reason}; {reason}" if base_reason else reason

    vip_status_val = str(judgment.get("vip_status") or "")
    source_bucket = str(
        judgment.get("screening_bucket")
        or judgment.get("source_bucket")
        or judgment.get("screening_decision")
        or judgment.get("initial_decision")
        or ""
    ).lower()
    hard_screening_reject = source_bucket in {"excluded", "exclude", "low_score", "low"}
    if (
        judgment.get("decision") == "reject"
        and not judgment.get("body_read_ok")
        and vip_status_val in {"", "missing"}
        and not hard_screening_reject
    ):
        judgment["decision"] = "needs_review"
        judgment["final_decision"] = "needs_review"
        judgment["recommendation_level"] = "C"
        reason = VIP_MISSING_REASON_CN
        prior_reason = str(judgment.get("manual_review_reason") or "").strip(" ;")
        judgment["manual_review_reason"] = (
            f"{prior_reason}; {reason}" if prior_reason else reason
        )
        base_reason = str(judgment.get("judgment_reason") or judgment.get("reason") or "").strip(" ;")
        judgment["reason"] = f"{base_reason}; {reason}" if base_reason else reason

    judgment["positive_hits"] = sorted(set(
        judgment.get("scope_hits", [])
        + judgment.get("product_hits", [])
        + judgment.get("construction_hits", [])
        + judgment.get("broad_recall_hits", [])
    ))
    judgment["ambiguous_hits"] = sorted(set(
        judgment.get("display_hits", []) + judgment.get("maintenance_hits", [])
    ))
    return judgment


def parse_args():
    parser = argparse.ArgumentParser(description="Phase 2D 业务复判 20260622 v04")
    parser.add_argument("--screening-json", help="第二步筛选结果 JSON；默认读 latest_screening_result_path.txt")
    parser.add_argument("--vip-json", help="VIP 正文读取 JSON；默认读 latest_vip_read_path.txt，缺失时仍可做标题级预判")
    parser.add_argument("--attachment-json", help="附件预览读取 JSON；默认读 latest_attachment_preview_path.txt，缺失时只用 VIP 页面正文")
    parser.add_argument(
        "--allow-incomplete-vip",
        action="store_true",
        help="Debug only: allow incomplete VIP evidence for a dry-run draft.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mark output as a non-production draft. Required with --allow-incomplete-vip.",
    )
    args = parser.parse_args()
    if args.allow_incomplete_vip and not args.dry_run:
        parser.error("--allow-incomplete-vip is forbidden in formal mode; add --dry-run for a draft.")
    return args


def main():
    args = parse_args()
    screening_path = Path(args.screening_json) if args.screening_json else find_latest(
        ["latest_screening_result_path.txt"], "标讯筛选结果_*_v*.json"
    )
    screening = load_json(screening_path)

    vip_path = None
    vip_data = {"projects": []}
    if args.vip_json:
        vip_path = Path(args.vip_json)
        vip_data = load_json(vip_path)
    else:
        try:
            vip_path = find_latest(["latest_vip_read_path.txt"], "VIP原文阅读_*_v*.json")
            vip_data = load_json(vip_path)
        except FileNotFoundError:
            vip_path = None
    assert_vip_read_is_usable(
        vip_data,
        vip_path,
        allow_incomplete=args.allow_incomplete_vip,
        screening=screening,
    )

    attachment_path = None
    attachment_data = {"results": []}
    if args.attachment_json:
        attachment_path = Path(args.attachment_json)
        attachment_data = load_json(attachment_path)
    else:
        try:
            attachment_path = find_latest(["latest_attachment_preview_path.txt"], "附件预览正文读取_*_v*.json")
            attachment_data = load_json(attachment_path)
        except FileNotFoundError:
            attachment_path = None

    vip_by_url = normalize_vip_projects(vip_data)
    attachment_by_url, attachment_by_title = normalize_attachment_projects(attachment_data)
    run_date = screening.get("meta", {}).get("run_date") or datetime.now().strftime("%Y%m%d")
    results = []
    for item in screening_items(screening):
        url = item.get("url")
        vip_item = vip_by_url.get(url)
        attachment_item = attachment_by_url.get(url) or attachment_by_title.get(normalize_match_key(item.get("title", "")))
        judged = judge_item(item, vip_item, attachment_item)
        judged.update({
            "title": item.get("title", ""),
            "url": url,
            "screening_category": item.get("_screening_category"),
            "score": item.get("scores", {}).get("总分"),
            "region": item.get("region", ""),
            "amount_wan": item.get("amount_wan"),
        })
        results.append(judged)

    summary = {}
    level_summary = {}
    for item in results:
        summary[item["decision"]] = summary.get(item["decision"], 0) + 1
        level = item.get("recommendation_level", "unknown")
        level_summary[level] = level_summary.get(level, 0) + 1

    output_path = next_output_path(str(run_date))
    output = {
        "version": "business_rejudge_20260622_v04",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "screening_json": str(screening_path),
        "vip_json": str(vip_path) if vip_path else "",
        "attachment_json": str(attachment_path) if attachment_path else "",
        "dry_run": bool(args.dry_run),
        "evidence_incomplete": bool(args.allow_incomplete_vip),
        "release_gate": "draft_only" if args.allow_incomplete_vip else "formal_eligible",
        "summary": summary,
        "level_summary": level_summary,
        "total": len(results),
        "results": results,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    pointers = write_pointer(output_path)

    print(f"业务复判完成: {summary}")
    print(f"输出: {output_path}")
    print("指针:")
    for pointer in pointers:
        print(f"  - {pointer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
