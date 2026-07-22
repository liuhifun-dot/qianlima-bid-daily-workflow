# -*- coding: utf-8 -*-
"""
Kimi WebBridge VIP body reader for Qianlima step 2, v03.

20260615 修改：读不到正文(need_login/empty/error)时先检查登录态，
被踢/掉线则自动重登(kimi)一次再重试该项目(每次运行最多重登2次)。
原因：CDP(Phase1) 与 Kimi(Phase2) 两通道会抢同一账号登录态、自己踢自己。
当前文件为正式运行版。

Reads non-reject projects from a business rejudge JSON, opens each Qianlima
detail page with the user's logged-in browser session, extracts visible body
text and attachment hints, then writes a versioned VIP body JSON and latest
pointer files for the next business rejudge pass.

Safety:
- Does not clear browser data.
- Does not close the user's Chrome.
- Does not export Cookie/Token.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path


SESSION = "bid-automation"
GROUP_TITLE = "BID-AUTO"
WEBBRIDGE_URL = "http://127.0.0.1:10086/command"
SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PACKAGE_ROOT / "output" / "v2_4"
PIPELINE_OUTPUT_DIR = PACKAGE_ROOT / "output"
SCREENSHOT_DIR = PACKAGE_ROOT / "output" / "screenshots"  # 正文截图保存目录


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


LOGIN_CHECK_JS = r"""(()=>{const t=document.body?document.body.innerText:'';return JSON.stringify({logged:(t.includes('退出')||t.includes('我的关注')||t.includes('订阅中心')||t.includes('高级会员')),gate:(t.includes('请登录')||t.includes('登录状态超时')||t.includes('请重新登录')||t.includes('请登录后查看'))});})()"""


def kimi_session_kicked() -> bool:
    """导航到千里马 VIP 首页，判断当前 Kimi 浏览器登录态是否被踢/未登录。"""
    try:
        wb("navigate", {"url": "https://vip.qianlima.com/"}, timeout=60)
        time.sleep(2)
        data = wb("evaluate", {"code": LOGIN_CHECK_JS}, timeout=60)
        raw = data.get("value") if isinstance(data, dict) else data
        st = json.loads(raw)
        return bool(st.get("gate")) or not bool(st.get("logged"))
    except Exception:
        return True


def relogin_kimi() -> bool:
    """掉线/被踢时调用方案A自动登录(kimi 通道)重登。"""
    login_script = SCRIPT_DIR / "qianlima_auto_login_20260610_v01.py"
    if not login_script.exists():
        return False
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(login_script), "--mode", "kimi"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        if proc.stdout:
            print(proc.stdout.strip())
        return proc.returncode == 0
    except Exception as exc:
        print(f"  ! 重登异常: {exc}")
        return False


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


def read_pointer(path: Path) -> Path:
    target = Path(path.read_text(encoding="utf-8").strip().strip('"'))
    if not target.exists():
        raise FileNotFoundError(f"pointer target does not exist: {target}")
    return target


def find_latest_business_json() -> Path:
    for p in [
        OUTPUT_DIR / "latest_business_review_path.txt",
        PIPELINE_OUTPUT_DIR / "latest_business_review_path.txt",
    ]:
        if p.exists():
            return read_pointer(p)
    files = sorted(OUTPUT_DIR.glob("业务复判结果_*_v*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("No business rejudge JSON found")
    return files[0]


def extract_compact_date(path: Path) -> str:
    match = re.search(r"(20\d{6})", path.name)
    if match:
        return match.group(1)
    return datetime.now().strftime("%Y%m%d")


def versioned_path(run_date: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(rf"^VIP原文阅读_{re.escape(run_date)}_Kimi_v(\d+)\.json$")
    versions = []
    for p in OUTPUT_DIR.glob(f"VIP原文阅读_{run_date}_Kimi_v*.json"):
        m = pattern.match(p.name)
        if m:
            versions.append(int(m.group(1)))
    return OUTPUT_DIR / f"VIP原文阅读_{run_date}_Kimi_v{max(versions, default=0) + 1:02d}.json"


def write_latest_pointers(output_path: Path) -> list[Path]:
    pointers = [
        OUTPUT_DIR / "latest_vip_read_path.txt",
        PIPELINE_OUTPUT_DIR / "latest_vip_read_path.txt",
    ]
    for pointer in pointers:
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(str(output_path), encoding="utf-8")
    return pointers


def trim_qianlima_text(text: str) -> str:
    if not text:
        return ""
    markers = [
        "\n招标项目商机\n",
        "\n数据纠错\n",
        "\nTEL\n千里马咨询电话",
        "\n相关推荐\n",
        "\n各省招标网\n",
        "\n友情链接\n",
        "\n产品意见征集\n",
        "\n千里马 投标服务",
    ]
    positions = [text.find(m) for m in markers if text.find(m) > 300]
    if positions:
        text = text[: min(positions)]
    return text.strip()


EXTRACT_JS = r"""
(() => {
  const text = document.body ? document.body.innerText : '';
  const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim();
  const attachments = Array.from(document.querySelectorAll('.fileItem, a, span, button'))
    .map((el, index) => {
      const t = clean(el.innerText || el.textContent || '');
      const href = el.href || el.getAttribute('href') || '';
      const className = clean(el.className || '').slice(0, 160);
      const dataset = Object.assign({}, el.dataset || {});
      const blob = `${t} ${href} ${className} ${JSON.stringify(dataset)}`;
      const looksLikeFile = /\.(pdf|doc|docx|rar|zip)(\?|#|$|\s)/i.test(blob)
        || t.includes('附件') || t.includes('下载') || t.includes('预览') || className.includes('fileItem');
      if (!looksLikeFile) return null;
      return {index, tag: el.tagName, text: t, href, className, dataset};
    })
    .filter(Boolean)
    .slice(0, 100);
  return JSON.stringify({
    url: location.href,
    title: document.title,
    textLength: text.length,
    content: text,
    content_preview: text.slice(0, 1500),
    attachments,
    hasLoginGate: text.includes('请登录后查看') || text.includes('登录状态超时') || text.includes('请重新登录'),
    hasCaptcha: text.includes('验证码') || text.includes('人机验证') || text.includes('滑动验证'),
    hasBidBody: text.includes('招标详情') || text.includes('采购公告') || text.includes('项目名称') || text.includes('采购范围') || text.includes('工程范围')
  });
})()
"""


ATTACHMENT_BODY_KEYWORDS = [
    "招标文件",
    "采购文件",
    "需求书",
    "用户需求",
    "工程量清单",
    "施工图",
    "图纸",
    "技术规格",
    "技术要求",
    "清单",
]


BODY_MARKERS = ["采购范围", "招标范围", "建设内容", "采购内容", "项目概况", "工程概况", "服务内容", "工程范围"]


def attachment_preview_required(payload: dict, content: str) -> tuple[bool, str]:
    attachments = payload.get("attachments") or []
    if not attachments:
        return False, ""
    attachment_text = "\n".join(
        f"{item.get('text', '')} {item.get('href', '')} {json.dumps(item.get('dataset') or {}, ensure_ascii=False)}"
        for item in attachments
        if isinstance(item, dict)
    )
    if any(keyword in attachment_text for keyword in ATTACHMENT_BODY_KEYWORDS):
        return True, "附件名称或数据包含招标文件/需求书/工程量清单/施工图/技术要求等，必须进入附件预览或下载解析"
    if len(content) < 800 or not any(marker in content for marker in BODY_MARKERS):
        return True, "页面可见正文不足或缺少采购范围/建设内容/工程范围等正文标记，需读取附件正文"
    return False, ""


def select_projects(data: dict, limit: int | None = None) -> list[dict]:
    projects = []
    # Format 1: Business rejudge JSON (has "results" key)
    if "results" in data:
        for item in data["results"]:
            if item.get("decision") == "reject":
                continue
            if not item.get("url"):
                continue
            projects.append(item)
    # Format 2: Screening result JSON (has "recommended"/"considered" keys)
    else:
        for category in ["recommended", "considered"]:
            for item in data.get(category) or []:
                if not item.get("url"):
                    continue
                # Add screening_category for traceability
                item.setdefault("screening_category", category)
                projects.append(item)
    if limit:
        return projects[:limit]
    return projects



_CHROME_ANY=("个人中心","公告-招标","公告-中标","收藏 导出","结构化数据下载","用手机查看","商机推荐","进度跟踪","摘要信息","相关推荐","返回顶部","官方标书代写","1对1专家服务","喜鹊标书","AI投标助手","400-900","在线咨询","咨询热线","下载APP","服务号","帮助中心","扫码关注","企业详情","相似采购商")
def _clean_body(content: str) -> str:
    out=[]
    for ln in str(content or "").replace("\r","").split("\n"):
        ln=ln.strip()
        if not ln or ln in ("全文","官方","收藏","导出","打印","|","/","\u00b7","招标详情","摘要信息","企业信息"): continue
        if any(k in ln for k in _CHROME_ANY): continue
        out.append(ln)
    return "\n".join(out).strip()
def _extract_duration(text: str) -> str:
    import re as _re
    m=_re.search(r"(工期|施工期|服务期|交货期|完成期限)[^。\n]{0,20}?(\d+\s*(个月|日历天|个日历天|天|年|周))", text or "")
    return m.group(2).strip() if m else ""
def _extract_payment(text: str) -> str:
    import re as _re
    m=_re.search(r"(资金来源|付款方式|支付方式|资金性质)[：:]\s*([^。\n；]{0,30})", text or "")
    return m.group(2).strip() if m else ""


def take_body_screenshot(project_url: str, run_date: str) -> str:
    """对正文区域截图，返回截图路径（相对路径）
    
    优先定位正文区域（招标详情/采购公告），如果找不到则截取整个页面。
    """
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        # 从 URL 提取项目 ID 作为文件名
        url_hash = project_url.split('/')[-1].replace('.html', '')[:20]
        screenshot_filename = f"body_{run_date}_{url_hash}.png"
        screenshot_path = SCREENSHOT_DIR / screenshot_filename
        
        # 千里马详情页正文区域选择器（按优先级排序）
        body_selectors = [
            # 招标详情区域
            ".bid-detail",
            ".project-detail",
            ".content-detail",
            # 公告内容区域
            ".notice-content",
            ".announcement-content",
            # 通用内容区域
            ".main-content",
            "article",
            ".detail-content",
            "#content",
            ".content",
        ]
        
        # 尝试找到正文区域并截图
        for selector in body_selectors:
            try:
                # 检查元素是否存在
                check_js = f"document.querySelector('{selector}') !== null"
                exists = wb("evaluate", {"code": check_js}, timeout=30)
                if exists.get("value"):
                    # 元素存在，截图该区域
                    result = wb("screenshot", {
                        "selector": selector,
                        "path": str(screenshot_path),
                        "format": "png"
                    }, timeout=60)
                    if result.get("ok"):
                        print(f"  ✓ 正文区域截图成功: {selector}")
                        return str(screenshot_path.relative_to(PACKAGE_ROOT))
            except Exception:
                continue
        
        # 如果没找到特定区域，截取整个页面可见区域
        result = wb("screenshot", {
            "path": str(screenshot_path),
            "format": "png"
        }, timeout=60)
        if result.get("ok"):
            print(f"  ✓ 页面截图成功（未找到特定正文区域）")
            return str(screenshot_path.relative_to(PACKAGE_ROOT))
        
        return ""
    except Exception as e:
        print(f"  ✗ 截图失败: {e}")
        return ""


def read_one(project: dict, first: bool, run_date: str = "") -> dict:
    args = {"url": project["url"], "newTab": first}
    if first:
        args["group_title"] = GROUP_TITLE
    wb("navigate", args, timeout=120)
    time.sleep(3)
    data = wb("evaluate", {"code": EXTRACT_JS}, timeout=120)
    raw = data.get("value") if isinstance(data, dict) else data
    payload = fix_mojibake(json.loads(raw))
    content = trim_qianlima_text(payload.get("content", ""))
    needs_attachment_preview, attachment_reason = attachment_preview_required(payload, content)
    status = "ok"
    if payload.get("hasCaptcha"):
        status = "captcha"
    elif payload.get("hasLoginGate") and not payload.get("hasBidBody"):
        status = "need_login"
    elif len(content) < 200:
        status = "empty"
    
    # 正文区域截图（仅在状态为 ok 时截图）
    screenshot_path = ""
    if status == "ok" and run_date:
        screenshot_path = take_body_screenshot(project["url"], run_date)
    
    return {
        "url": project["url"],
        "title": project.get("title", ""),
        "status": status,
        "page_title": payload.get("title", ""),
        "text_length": len(content),
        "content_source": "page_visible_text",
        "attachments": payload.get("attachments") or [],
        "attachment_preview_required": needs_attachment_preview,
        "attachment_reason": attachment_reason,
        "content": content,
        "content_preview": content[:1500],
        "body_clean": _clean_body(content),
        "duration": _extract_duration(_clean_body(content)),
        "payment": _extract_payment(_clean_body(content)),
        "screening_category": project.get("screening_category"),
        "score": project.get("score"),
        "recommendation_level_before_body": project.get("recommendation_level"),
        "decision_before_body": project.get("decision"),
        "screenshot_path": screenshot_path,  # 新增：正文截图路径
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read Qianlima VIP visible body text with Kimi WebBridge")
    parser.add_argument("--business-json", help="Input business rejudge JSON. Defaults to latest_business_review_path.txt.")
    parser.add_argument("--limit", type=int, default=0, help="Optional project limit for testing.")
    parser.add_argument(
        "--allow-login-failure",
        action="store_true",
        help="Debug only: write JSON even when login/captcha/error occurs and still return 0. Never use in the formal workflow.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    business_path = Path(args.business_json) if args.business_json else find_latest_business_json()
    business = json.loads(business_path.read_text(encoding="utf-8"))
    run_date = extract_compact_date(business_path)
    projects = select_projects(business, limit=args.limit or None)
    output_path = versioned_path(run_date)

    results = []
    relogin_used = 0
    for idx, project in enumerate(projects, 1):
        print(f"[{idx}/{len(projects)}] {project.get('title', '')[:80]}")
        try:
            item = read_one(project, first=(idx == 1), run_date=run_date)
        except Exception as exc:
            item = {
                "url": project.get("url", ""),
                "title": project.get("title", ""),
                "status": "error",
                "error": str(exc),
                "text_length": 0,
                "content": "",
                "content_preview": "",
                "screening_category": project.get("screening_category"),
                "score": project.get("score"),
                "decision_before_body": project.get("decision"),
            }
        # 读不到正文(need_login/empty/error)时先查登录态；被踢则自动重登一次再重试该项目
        if item.get("status") in ("need_login", "empty", "error") and relogin_used < 2:
            if kimi_session_kicked():
                relogin_used += 1
                print(f"  ! 读不到正文且登录态失效，自动重登(第{relogin_used}次)...")
                if relogin_kimi():
                    try:
                        item = read_one(project, first=False)
                    except Exception as exc:
                        item["retry_error"] = str(exc)
        print(f"  -> {item.get('status')} length={item.get('text_length', 0)} attachment_required={item.get('attachment_preview_required')}")
        results.append(item)
        time.sleep(1)

    summary = {}
    for item in results:
        summary[item["status"]] = summary.get(item["status"], 0) + 1

    output = {
        "version": "vip_read_kimi_webbridge_20260602_v03",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(business_path),
        "browser_session": SESSION,
        "browser_group_title": GROUP_TITLE,
        "total": len(results),
        "summary": summary,
        "attachment_preview_required_total": sum(1 for item in results if item.get("attachment_preview_required")),
        "projects": results,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    pointers = write_latest_pointers(output_path)
    print(f"saved: {output_path}")
    print(summary)
    print("pointers:")
    for pointer in pointers:
        print(f"  - {pointer}")
    blocking = {k: summary.get(k, 0) for k in ("need_login", "captcha", "error") if summary.get(k, 0)}
    if blocking and not args.allow_login_failure:
        print(
            "ERROR: VIP 正文读取存在登录态/验证码/脚本错误，禁止进入 2D/3/4。"
            f" blocking={json.dumps(blocking, ensure_ascii=False)}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

