# -*- coding: utf-8 -*-
"""
千里马 VIP 自动登录（方案A）——双通道：CDP 与 Kimi WebBridge。

2026-06-17 修复要点：
- 增加 --check，满足 automation/daily_bid_pipeline.ps1 的登录态预检调用。
- 登录前先处理“登录状态超时，请重新登录”弹窗。
- 使用 UTF-8 文本和结构化 DOM 选择器，避免中文乱码导致按钮识别失败。
- Phase1 使用 CDP 主线；Kimi 只在对应 mode 下用于已登录浏览器会话恢复。

2026-07-15 修复要点：
- 打开页面后**先等弹窗出现**（layui 延迟弹出），再点 a.layui-layer-btn0「确定」。
- 点确定后等弹窗消失；再进登录页并**等到密码框可见**后才填账密。
- 账号框严格排除搜索框；必须与 password 同表单/邻近，避免填进顶栏搜索。

2026-07-15 追加（用户纠正：刷新时间 / 弹窗延迟）：
- 进站/导航后有**页面刷新稳定期**，弹窗不是立刻出来；稳定期内禁止填任何输入框。
- 弹窗未出、gate 仍在、密码表单未就绪时一律不填账密（防账号进顶栏搜索框）。
- 填前清掉搜索框里误填的账号；填后校验账号不在搜索框。
- 点「确定」后等待弹层真正消失 + 短刷新稳定，再跳登录页。

安全边界：不清 Cookie、不清浏览器数据、不关闭浏览器、不改密码。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

try:
    import websockets
except Exception:
    websockets = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SOP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = os.environ.get("QLM_BID_CONFIG", "")
KIMI_URL = "http://127.0.0.1:10086/command"
KIMI_SESSION = "bid-automation"
VIP_ROOT = "https://vip.qianlima.com/"
LOGIN_URL = "https://vip.qianlima.com/login/"


def js_json(obj: str) -> str:
    return json.dumps(obj, ensure_ascii=False)


JS_STATE = r"""(() => {
  const text = document.body ? (document.body.innerText || '') : '';
  const visible = (el) => {
    if (!el) return false;
    const style = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };
  const dialogs = [...document.querySelectorAll('.el-message-box,.el-dialog,.layui-layer,.modal,.opc-content,.opc-box,[role=dialog]')]
    .filter(visible).map(el => el.innerText || '').join('\n');
  const inputs = [...document.querySelectorAll('input')].filter(visible);
  // 更精确的登录表单检测：需要同时有账号输入框和登录按钮，或者密码输入框
  const hasAccountInput = inputs.some(i => {
    const type = (i.getAttribute('type') || '').toLowerCase();
    const ph = i.getAttribute('placeholder') || '';
    const name = (i.getAttribute('name') || '').toLowerCase();
    const id = (i.id || '').toLowerCase();
    // 排除搜索框等通用输入
    if (/search|搜索|查询/.test(ph) || /search|query/.test(name) || /search|query/.test(id)) return false;
    return type !== 'password' && /用户名|账号|手机|手机号/.test(ph);
  });
  const hasPasswordInput = inputs.some(i => (i.getAttribute('type') || '').toLowerCase() === 'password');
  const gate = /登录状态超时|请重新登录|请登录后查看/.test(text);
  const memberIdentity = /高级会员|会员到期|到期时间|会员中心/.test(text);
  const authenticatedWorkspace = /我的导出记录|标讯订阅/.test(text);
  // 登录表单需要同时有账号输入框和密码输入框，或者有明确的登录按钮
  const hasLoginButton = [...document.querySelectorAll('button,a,input[type=submit]')].some(el => {
    const t = (el.innerText || el.textContent || el.value || '').replace(/\s+/g, '').trim();
    return t === '登录' && !/微信|注册|快捷/.test(el.className || '');
  });
  const loginFormVisible = (hasAccountInput && hasPasswordInput) || (hasAccountInput && hasLoginButton);
  return JSON.stringify({
    url: location.href,
    title: document.title,
    logged: !gate && !loginFormVisible && (memberIdentity || authenticatedWorkspace),
    gate,
    captcha: /验证码|滑动|拖动滑块|安全验证|Access Verification/.test(text),
    riskBlocking: /账号风险|风险提醒|身份验证/.test(dialogs),
    hasAccountInput,
    hasPasswordInput,
    sample: text.slice(0, 320)
  });
})()"""

JS_DISMISS_LOGIN_TIMEOUT = r"""(() => {
  const text = document.body ? (document.body.innerText || '') : '';
  if (!/登录状态超时|请重新登录|登录已过期/.test(text)) return JSON.stringify({ok:false, reason:'no-login-timeout'});
  const visible = (el) => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity) !== 0 && r.width > 0 && r.height > 0;
  };
  const norm = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, '').trim();
  // 优先在弹窗容器内找「确定」
  const boxes = [...document.querySelectorAll(
    '.el-message-box, .el-dialog, .layui-layer, .modal, [role=dialog], .opc-box, .opc-content'
  )].filter(visible);
  const scope = boxes.find(b => /登录状态超时|请重新登录|登录已过期/.test(b.innerText || '')) || document.body;
  const btns = [...scope.querySelectorAll('button,a,span,div')].filter(visible);
  // layui: 真实按钮是 a.layui-layer-btn0；父级 div.layui-layer-btn 也含「确定」但点了无效
  let btn = btns.find(el => /layui-layer-btn0/.test(String(el.className || '')));
  if (!btn) btn = btns.find(el => norm(el) === '确定' && el.tagName === 'A');
  if (!btn) btn = btns.find(el => norm(el) === '确定' && el.tagName === 'BUTTON');
  if (!btn) btn = btns.find(el => norm(el) === '确定' && el.childElementCount === 0);
  if (!btn) btn = btns.find(el => norm(el) === '确定');
  if (!btn) return JSON.stringify({ok:false, reason:'confirm-not-found', boxes: boxes.length});
  const r = btn.getBoundingClientRect();
  const x = Math.round(r.x + r.width / 2);
  const y = Math.round(r.y + r.height / 2);
  try { btn.click(); } catch (e) {}
  try {
    btn.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, view:window}));
    btn.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, view:window}));
    btn.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
  } catch (e) {}
  return JSON.stringify({
    ok:true, reason:'clicked-confirm', x, y, text: norm(btn),
    tag: btn.tagName, cls: String(btn.className || '').slice(0, 60)
  });
})()"""

JS_OPEN_PASSWORD_LOGIN = r"""(() => {
  const visible = (el) => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };
  if ([...document.querySelectorAll('input[type=password]')].some(visible)) return 'password-visible';
  const btn = [...document.querySelectorAll('button,a,span,div')]
    .filter(visible)
    .find(el => (el.innerText || el.textContent || '').replace(/\s+/g, '').trim() === '密码登录');
  if (btn) { btn.click(); return 'clicked-password-login'; }
  return 'password-login-not-found';
})()"""


JS_CLEAR_SEARCH_POLLUTION = r"""(() => {
  const visible = (el) => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };
  const isSearch = (i) => {
    const ph = i.getAttribute('placeholder') || '';
    const name = (i.getAttribute('name') || '').toLowerCase();
    const id = (i.id || '').toLowerCase();
    const cls = String(i.className || '').toLowerCase();
    const r = i.getBoundingClientRect();
    // 顶栏输入一律当搜索（y 很小、无 password 邻近）
    if (r.top < 90 && r.height > 0 && r.width > 120) return true;
    return /search|搜索|查询|keyword|全文|header/.test(ph + name + id + cls);
  };
  const pwdVisible = [...document.querySelectorAll('input[type=password]')].filter(visible);
  let cleared = 0;
  for (const i of [...document.querySelectorAll('input')].filter(visible)) {
    const type = (i.getAttribute('type') || 'text').toLowerCase();
    if (type === 'password' || type === 'hidden' || type === 'checkbox' || type === 'radio') continue;
    if (!isSearch(i)) continue;
    if (!String(i.value || '').trim()) continue;
    // 勿清登录表单里与密码邻近的账号框
    const ir = i.getBoundingClientRect();
    let nearPwd = false;
    for (const p of pwdVisible) {
      const pr = p.getBoundingClientRect();
      if (Math.abs(ir.left - pr.left) < 100 && Math.abs(pr.top - ir.top) < 160) nearPwd = true;
    }
    if (nearPwd) continue;
    i.focus();
    i.value = '';
    i.dispatchEvent(new Event('input', {bubbles:true}));
    i.dispatchEvent(new Event('change', {bubbles:true}));
    cleared += 1;
  }
  return 'cleared:' + cleared;
})()"""


def js_fill_account(account: str) -> str:
    """只填登录表单账号框；严禁搜索框（含顶栏空 placeholder 搜索）。"""
    return f"""(() => {{
  const text = document.body ? (document.body.innerText || '') : '';
  // 超时弹窗还在时禁止填任何东西（否则焦点常在顶栏搜索）
  if (/登录状态超时|请重新登录|登录已过期/.test(text)) {{
    const layer = document.querySelector('.layui-layer, .el-message-box, [role=dialog]');
    if (layer) {{
      const s = getComputedStyle(layer), r = layer.getBoundingClientRect();
      if (s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0) return 'blocked-by-timeout-dialog';
    }}
  }}
  const visible = (el) => {{
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  }};
  const isSearch = (i) => {{
    const ph = i.getAttribute('placeholder') || '';
    const name = (i.getAttribute('name') || '').toLowerCase();
    const id = (i.id || '').toLowerCase();
    const cls = String(i.className || '').toLowerCase();
    const r = i.getBoundingClientRect();
    if (r.top < 90 && r.width > 120) return true;  // 顶栏搜索
    return /search|搜索|查询|keyword|全文|header/.test(ph + name + id + cls);
  }};
  const pwdVisible = [...document.querySelectorAll('input[type=password]')].filter(visible);
  if (!pwdVisible.length) return 'no-pwd-form-yet';
  const score = (i) => {{
    const type = (i.getAttribute('type') || '').toLowerCase();
    const ph = i.getAttribute('placeholder') || '';
    if (type === 'password' || type === 'hidden') return -100;
    if (isSearch(i)) return -100;
    let n = 0;
    if (/用户名|账号|手机|手机号|邮箱|会员/.test(ph)) n += 20;
    if (/请输入/.test(ph)) n += 2;
    const form = i.closest('form');
    if (form && pwdVisible.some(p => form.contains(p))) n += 15;
    const ir = i.getBoundingClientRect();
    let nearPwd = false;
    for (const p of pwdVisible) {{
      const pr = p.getBoundingClientRect();
      if (Math.abs(ir.left - pr.left) < 100 && pr.top - ir.top > 0 && pr.top - ir.top < 140) {{
        n += 12;
        nearPwd = true;
      }}
    }}
    if (!nearPwd && !(form && pwdVisible.some(p => form.contains(p)))) n -= 20;
    if (ir.top > 120) n += 3;
    if (ir.top < 90) n -= 50;
    return n;
  }};
  const ranked = [...document.querySelectorAll('input')].filter(visible)
    .map(i => [score(i), i]).filter(x => x[0] >= 15).sort((a,b)=>b[0]-a[0]);
  if (!ranked.length) return 'no-account-input';
  const input = ranked[0][1];
  if (isSearch(input)) return 'refused-search-box';
  input.focus();
  input.value = '';
  input.value = {js_json(account)};
  input.dispatchEvent(new Event('input', {{bubbles:true}}));
  input.dispatchEvent(new Event('change', {{bubbles:true}}));
  // 二次校验：搜索框不得含本账号
  for (const i of [...document.querySelectorAll('input')].filter(visible)) {{
    if (!isSearch(i)) continue;
    if (String(i.value || '') === {js_json(account)}) {{
      i.value = '';
      i.dispatchEvent(new Event('input', {{bubbles:true}}));
      return 'leaked-to-search-cleared';
    }}
  }}
  return 'ok:' + (input.getAttribute('placeholder') || input.name || input.id || 'filled');
}})()"""


def js_fill_password(password: str) -> str:
    return f"""(() => {{
  const visible = (el) => {{
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  }};
  const inputs = [...document.querySelectorAll('input[type=password]')].filter(visible);
  if (!inputs.length) return 'no-pwd-input';
  const input = inputs[0];
  input.focus();
  input.value = '';
  input.value = {js_json(password)};
  input.dispatchEvent(new Event('input', {{bubbles:true}}));
  input.dispatchEvent(new Event('change', {{bubbles:true}}));
  return 'ok';
}})()"""


JS_CLICK_LOGIN = r"""(() => {
  const visible = (el) => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };
  const norm = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, '').trim();
  const els = [...document.querySelectorAll('button,a,div,span')].filter(visible);
  let btn = els.find(el => norm(el) === '登录' && !/微信|注册|快捷|密码登录/.test(el.className || ''));
  if (!btn) btn = els.find(el => norm(el) === '登录');
  if (!btn) return 'no-login-button';
  btn.click();
  return 'clicked';
})()"""

JS_IGNORE_RISK = r"""(() => {
  const visible = (el) => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };
  const dialogs = [...document.querySelectorAll('.el-message-box,.el-dialog,.layui-layer,.modal,.opc-content,.opc-box,[role=dialog]')].filter(visible);
  const box = dialogs.find(el => /账号风险|风险提醒/.test(el.innerText || ''));
  if (!box) return 'no-risk';
  const btns = [...box.querySelectorAll('button,a,span,div')].filter(visible);
  const btn = btns.find(el => ['忽略','取消','暂不修改'].includes((el.innerText || el.textContent || '').replace(/\s+/g, '').trim()))
    || box.querySelector('.cancel-btn,.opc-btn.cancel-btn');
  if (btn) { btn.click(); return 'ignored'; }
  return 'risk-no-button';
})()"""


def decode_state(value: str | None) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        pass
    m = re.search(r"\{.*\}", str(value), flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


def is_logged(state: dict) -> bool:
    return bool(state.get("logged")) and not bool(state.get("gate"))


def read_credentials(config_path: Path) -> tuple[str, str]:
    text = config_path.read_text(encoding="utf-8", errors="ignore") if config_path.exists() else ""

    def grab(label: str) -> str:
        m = re.search(rf"{label}\s*[：:]\s*([^\s`*\r\n]+)", text)
        return m.group(1).strip() if m else ""

    return grab("账号"), grab("密码")


# ---- CDP ----
def find_page(port: int) -> str:
    # Chrome 150+ DevTools HTTP 端点只接受 Host: localhost（拒绝 127.0.0.1）；并绕过系统代理。
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://localhost:{port}/json", timeout=10) as r:
        tabs = json.loads(r.read().decode("utf-8", errors="replace"))
    pages = [t for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    qlm = [t for t in pages if "qianlima.com" in (t.get("url") or "")]
    target = (qlm or pages or [None])[0]
    if not target:
        raise RuntimeError(f"CDP 未找到可控页面；确认专用调试 Chrome 已开（端口 {port}）。")
    return target["webSocketDebuggerUrl"]


async def cdp_eval(ws, cid: int, code: str):
    await ws.send(json.dumps({"id": cid, "method": "Runtime.evaluate", "params": {"expression": code, "returnByValue": True}}, ensure_ascii=False))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == cid:
            return msg.get("result", {}).get("result", {}).get("value")


async def cdp_call(ws, cid: int, method: str, params: dict | None = None):
    await ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}, ensure_ascii=False))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == cid:
            return msg


async def cdp_click_xy(ws, cid_base: int, x: int, y: int) -> None:
    """CDP 坐标点击，绕过部分 el-message-box 对 element.click 的拦截。"""
    for i, typ in enumerate(("mouseMoved", "mousePressed", "mouseReleased")):
        params = {"type": typ, "x": x, "y": y, "button": "left", "clickCount": 1}
        await cdp_call(ws, cid_base + i, "Input.dispatchMouseEvent", params)
    await asyncio.sleep(0.3)


async def cdp_get_state(ws, cid: int) -> dict:
    return decode_state(await cdp_eval(ws, cid, JS_STATE))


async def cdp_poll_state(ws, cid_base: int, timeout: float, interval: float = 0.8):
    """轮询页面状态，直到超时；返回 (last_state, elapsed)。"""
    t0 = time.time()
    n = 0
    state = {}
    while time.time() - t0 < timeout:
        state = await cdp_get_state(ws, cid_base + n)
        n += 1
        yield state, time.time() - t0
        await asyncio.sleep(interval)


async def cdp_dismiss_login_timeout(ws, cid_base: int = 100) -> str:
    raw = await cdp_eval(ws, cid_base, JS_DISMISS_LOGIN_TIMEOUT)
    info = {}
    try:
        info = json.loads(raw) if isinstance(raw, str) and str(raw).startswith("{") else {"raw": raw}
    except Exception:
        info = {"raw": raw}
    if info.get("ok") and info.get("x") and info.get("y"):
        await cdp_click_xy(ws, cid_base + 10, int(info["x"]), int(info["y"]))
        await asyncio.sleep(1.5)
    return str(info)


async def wait_page_settle(ws, cid_base: int = 5, min_seconds: float = 2.5) -> None:
    """页面刷新/导航后的稳定期：弹窗与表单都可能延迟出现，此间禁止填表。"""
    await asyncio.sleep(min_seconds)
    # readyState 再确认一轮
    try:
        ready = await cdp_eval(
            ws,
            cid_base,
            "document.readyState || ''",
        )
        if ready != "complete":
            await asyncio.sleep(1.2)
    except Exception:
        await asyncio.sleep(0.8)


async def wait_for_timeout_dialog_or_ready(
    ws, cid_base: int = 200, timeout: float = 22.0, min_settle: float = 2.0
) -> dict:
    """打开/刷新后：先过刷新稳定期，再等「登录超时弹窗」/已登录/登录表单。

    用户反馈：点进站后要等一会才弹框（有刷新时间）；太快操作会把账号填进搜索框。
    """
    await wait_page_settle(ws, cid_base, min_seconds=min_settle)
    last = {}
    gate_seen_at: float | None = None
    async for state, elapsed in cdp_poll_state(ws, cid_base + 10, timeout, interval=0.7):
        last = state
        if is_logged(state):
            last["_wait"] = f"logged@{elapsed + min_settle:.1f}s"
            return last
        # 密码表单就绪且无超时门 → 可进填表
        if (
            state.get("hasPasswordInput")
            and state.get("hasAccountInput")
            and not state.get("gate")
        ):
            last["_wait"] = f"login_form@{elapsed + min_settle:.1f}s"
            return last
        if state.get("gate"):
            # 文案出现后还要再等弹层「确定」按钮渲染稳定（layui 延迟）
            if gate_seen_at is None:
                gate_seen_at = elapsed
            if elapsed - gate_seen_at >= 1.2:
                last = await cdp_get_state(ws, cid_base + 500)
                last["_wait"] = f"gate_stable@{elapsed + min_settle:.1f}s"
                return last
            continue
    last["_wait"] = f"timeout_no_gate@{timeout + min_settle}s"
    return last


async def wait_gate_cleared(ws, cid_base: int = 300, timeout: float = 12.0) -> dict:
    """点确定后等待超时弹窗消失，并再留短刷新稳定期。"""
    last = {}
    async for state, elapsed in cdp_poll_state(ws, cid_base, timeout, interval=0.6):
        last = state
        if not state.get("gate"):
            # 点确定后页面常会刷新/重绘，再稳一会
            await asyncio.sleep(1.5)
            last = await cdp_get_state(ws, cid_base + 400)
            last["_wait"] = f"gate_cleared@{elapsed:.1f}s"
            return last
        # 弹窗仍在：稍等再点，避免刷新中点空
        if elapsed >= 1.0 and int(elapsed * 2) % 3 == 0:
            await cdp_dismiss_login_timeout(ws, cid_base + 50 + int(elapsed * 2))
    last["_wait"] = f"gate_still@{timeout}s"
    return last


async def wait_password_login_form(ws, cid_base: int = 400, timeout: float = 15.0) -> dict:
    """等到密码登录表单（密码框+账号框）可见且无超时弹窗，禁止在表单未就绪时填表。"""
    last = {}
    async for state, elapsed in cdp_poll_state(ws, cid_base, timeout, interval=0.6):
        last = state
        if is_logged(state):
            last["_wait"] = f"logged@{elapsed:.1f}s"
            return last
        if state.get("gate"):
            # 表单等待中若又弹出超时框，先不要填
            if elapsed > 1.0:
                await cdp_dismiss_login_timeout(ws, cid_base + 700 + int(elapsed))
            continue
        if state.get("hasPasswordInput") and state.get("hasAccountInput"):
            last["_wait"] = f"form_ready@{elapsed:.1f}s"
            return last
        if elapsed > 1.5:
            await cdp_eval(ws, cid_base + 800 + int(elapsed), JS_OPEN_PASSWORD_LOGIN)
    last["_wait"] = f"form_timeout@{timeout}s"
    return last


async def cdp_prepare(ws) -> dict:
    await cdp_call(ws, 1, "Page.enable")
    await cdp_call(ws, 2, "Runtime.enable")
    # 进站后先过刷新稳定期，再等弹窗/登录态（不要立刻乱点/填搜索框）
    state = await wait_for_timeout_dialog_or_ready(ws, 11, timeout=20.0, min_settle=2.5)
    if is_logged(state):
        return state

    if state.get("gate"):
        await cdp_dismiss_login_timeout(ws, 30)
        state = await wait_gate_cleared(ws, 40, timeout=12.0)
        if is_logged(state):
            return state

    await cdp_eval(ws, 50, JS_IGNORE_RISK)
    await cdp_eval(ws, 51, JS_CLEAR_SEARCH_POLLUTION)
    await asyncio.sleep(0.5)

    if state.get("hasPasswordInput") and state.get("hasAccountInput") and not state.get("gate"):
        return state

    # 仍无表单：回 VIP 再等一轮弹窗（含刷新时间）
    await cdp_call(ws, 60, "Page.navigate", {"url": VIP_ROOT})
    state = await wait_for_timeout_dialog_or_ready(ws, 70, timeout=18.0, min_settle=3.0)
    if is_logged(state):
        return state
    if state.get("gate"):
        await cdp_dismiss_login_timeout(ws, 80)
        state = await wait_gate_cleared(ws, 90, timeout=12.0)
        if is_logged(state):
            return state

    # 进登录页并等密码表单
    if not (state.get("hasPasswordInput") and state.get("hasAccountInput")) or state.get("gate"):
        await cdp_call(ws, 100, "Page.navigate", {"url": LOGIN_URL})
        state = await wait_for_timeout_dialog_or_ready(ws, 110, timeout=15.0, min_settle=2.5)
        if state.get("gate"):
            await cdp_dismiss_login_timeout(ws, 120)
            await wait_gate_cleared(ws, 130, timeout=10.0)
        await cdp_eval(ws, 140, JS_OPEN_PASSWORD_LOGIN)
        await cdp_eval(ws, 141, JS_CLEAR_SEARCH_POLLUTION)
        state = await wait_password_login_form(ws, 150, timeout=15.0)
    return state


async def check_cdp(ws_url: str) -> dict:
    async with websockets.connect(ws_url, max_size=None) as ws:
        return await cdp_prepare(ws)


async def login_cdp(ws_url: str, account: str, password: str) -> dict:
    async with websockets.connect(ws_url, max_size=None) as ws:
        state = await cdp_prepare(ws)
        if is_logged(state):
            return state
        if state.get("captcha") or state.get("riskBlocking"):
            return state

        # 必须等到密码表单且无超时弹窗，绝不在刷新期/搜索框填账号
        if not (state.get("hasPasswordInput") and state.get("hasAccountInput")) or state.get("gate"):
            if state.get("gate"):
                await cdp_dismiss_login_timeout(ws, 190)
                await wait_gate_cleared(ws, 195, timeout=10.0)
            await cdp_call(ws, 200, "Page.navigate", {"url": LOGIN_URL})
            st2 = await wait_for_timeout_dialog_or_ready(ws, 210, timeout=15.0, min_settle=2.5)
            if st2.get("gate"):
                await cdp_dismiss_login_timeout(ws, 220)
                await wait_gate_cleared(ws, 230, timeout=10.0)
            await cdp_eval(ws, 240, JS_OPEN_PASSWORD_LOGIN)
            await cdp_eval(ws, 241, JS_CLEAR_SEARCH_POLLUTION)
            state = await wait_password_login_form(ws, 250, timeout=15.0)
            if is_logged(state) or state.get("captcha") or state.get("riskBlocking"):
                return state

        if not state.get("hasPasswordInput") or state.get("gate"):
            state = await cdp_get_state(ws, 255)
            state["fill_account_error"] = "no-pwd-or-gate-still"
            return state  # 仍无密码框 / 弹窗未关：绝不填搜索框

        await cdp_eval(ws, 258, JS_CLEAR_SEARCH_POLLUTION)
        await asyncio.sleep(0.4)
        fill_acc = await cdp_eval(ws, 260, js_fill_account(account))
        if not str(fill_acc).startswith("ok"):
            await cdp_eval(ws, 261, JS_CLEAR_SEARCH_POLLUTION)
            await cdp_eval(ws, 262, JS_OPEN_PASSWORD_LOGIN)
            state = await wait_password_login_form(ws, 270, timeout=10.0)
            if state.get("gate") or not state.get("hasPasswordInput"):
                state["fill_account_error"] = str(fill_acc)
                return state
            fill_acc = await cdp_eval(ws, 280, js_fill_account(account))
            if not str(fill_acc).startswith("ok"):
                state = await cdp_get_state(ws, 281)
                state["fill_account_error"] = str(fill_acc)
                await cdp_eval(ws, 282, JS_CLEAR_SEARCH_POLLUTION)
                return state

        fill_pwd = await cdp_eval(ws, 290, js_fill_password(password))
        if fill_pwd != "ok":
            state = await cdp_get_state(ws, 291)
            state["fill_password_error"] = str(fill_pwd)
            return state

        await cdp_eval(ws, 300, JS_CLICK_LOGIN)
        await asyncio.sleep(3.0)
        # 登录后可能再弹风险/超时，等稳定
        t0 = time.time()
        while time.time() - t0 < 14:
            await cdp_eval(ws, 310, JS_IGNORE_RISK)
            st = await cdp_get_state(ws, 315)
            if st.get("gate"):
                await cdp_dismiss_login_timeout(ws, 320)
            state = await cdp_get_state(ws, 330)
            if is_logged(state):
                return state
            if state.get("captcha") or state.get("riskBlocking"):
                return state
            await asyncio.sleep(1.0)
        return await cdp_get_state(ws, 340)


# ---- Kimi ----
def kimi_command(action: str, args: dict | None = None, timeout: int = 30):
    body = json.dumps({"action": action, "args": args or {}, "session": KIMI_SESSION}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(KIMI_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def kimi_value(resp) -> str:
    if isinstance(resp, dict):
        data = resp.get("data")
        if isinstance(data, dict):
            if "value" in data:
                return data.get("value") or ""
            if "result" in data:
                return str(data.get("result") or "")
        if "result" in resp:
            return str(resp.get("result") or "")
    return str(resp or "")


def kimi_eval(code: str, timeout: int = 30) -> str:
    return kimi_value(kimi_command("evaluate", {"code": code}, timeout=timeout))


def _kimi_wait_gate_or_form(timeout: float = 18.0, min_settle: float = 2.5) -> dict:
    """Kimi 通道同样遵守：刷新稳定期 → 等弹窗/表单，期间不填表。"""
    time.sleep(min_settle)
    t0 = time.time()
    last = {}
    gate_seen_at = None
    while time.time() - t0 < timeout:
        last = decode_state(kimi_eval(JS_STATE))
        if is_logged(last):
            return last
        if last.get("hasPasswordInput") and last.get("hasAccountInput") and not last.get("gate"):
            return last
        if last.get("gate"):
            if gate_seen_at is None:
                gate_seen_at = time.time()
            if time.time() - gate_seen_at >= 1.2:
                return last
        time.sleep(0.7)
    return last


def kimi_prepare() -> dict:
    try:
        state = decode_state(kimi_eval(JS_STATE))
    except Exception:
        kimi_command("navigate", {"url": VIP_ROOT, "newTab": True})
        state = _kimi_wait_gate_or_form(timeout=18.0, min_settle=3.0)
    if is_logged(state):
        return state
    # 先等弹窗稳定再点确定
    state = _kimi_wait_gate_or_form(timeout=12.0, min_settle=2.0)
    if is_logged(state):
        return state
    if state.get("gate"):
        kimi_eval(JS_DISMISS_LOGIN_TIMEOUT)
        time.sleep(2.0)
    kimi_eval(JS_IGNORE_RISK)
    kimi_eval(JS_CLEAR_SEARCH_POLLUTION)
    time.sleep(0.8)
    state = decode_state(kimi_eval(JS_STATE))
    if is_logged(state):
        return state
    if not state.get("hasAccountInput") or not state.get("hasPasswordInput") or state.get("gate"):
        kimi_command("navigate", {"url": VIP_ROOT, "newTab": False})
        state = _kimi_wait_gate_or_form(timeout=15.0, min_settle=3.0)
        if state.get("gate"):
            kimi_eval(JS_DISMISS_LOGIN_TIMEOUT)
            time.sleep(2.0)
        kimi_eval(JS_IGNORE_RISK)
        kimi_eval(JS_CLEAR_SEARCH_POLLUTION)
        state = decode_state(kimi_eval(JS_STATE))
        if is_logged(state):
            return state
    if not state.get("hasAccountInput") or not state.get("hasPasswordInput") or state.get("gate"):
        kimi_command("navigate", {"url": LOGIN_URL, "newTab": False})
        state = _kimi_wait_gate_or_form(timeout=12.0, min_settle=2.5)
        if state.get("gate"):
            kimi_eval(JS_DISMISS_LOGIN_TIMEOUT)
            time.sleep(2.0)
        kimi_eval(JS_OPEN_PASSWORD_LOGIN)
        kimi_eval(JS_CLEAR_SEARCH_POLLUTION)
        time.sleep(1.2)
    return decode_state(kimi_eval(JS_STATE))


def check_kimi() -> dict:
    return kimi_prepare()


def login_kimi(account: str, password: str) -> dict:
    state = kimi_prepare()
    if is_logged(state) or state.get("captcha") or state.get("riskBlocking"):
        return state
    if state.get("gate"):
        kimi_eval(JS_DISMISS_LOGIN_TIMEOUT)
        time.sleep(2.0)
        state = decode_state(kimi_eval(JS_STATE))
    kimi_eval(JS_OPEN_PASSWORD_LOGIN)
    kimi_eval(JS_CLEAR_SEARCH_POLLUTION)
    time.sleep(1.2)
    state = decode_state(kimi_eval(JS_STATE))
    if not state.get("hasPasswordInput") or state.get("gate"):
        return state  # 表单未就绪 / 弹窗未关：不填搜索框
    fill_acc = kimi_eval(js_fill_account(account))
    if not str(fill_acc).startswith("ok"):
        kimi_eval(JS_CLEAR_SEARCH_POLLUTION)
        return decode_state(kimi_eval(JS_STATE))
    kimi_eval(js_fill_password(password))
    kimi_eval(JS_CLICK_LOGIN)
    time.sleep(4)
    kimi_eval(JS_IGNORE_RISK)
    time.sleep(2)
    return decode_state(kimi_eval(JS_STATE))


def exit_for_state(mode: str, state: dict, check_only: bool) -> int:
    payload = {"ok": is_logged(state), "mode": mode, "check_only": check_only, "state": state}

    # Login success has priority. Some Qianlima pages keep hidden or stale risk/login
    # widgets in the DOM even when the VIP homepage is already logged in. Do not fail
    # a healthy member-center session just because those stale markers are present.
    if is_logged(state):
        payload["reason"] = f"[{mode}] 登录态有效" if check_only else f"[{mode}] 自动登录成功"
        if state.get("captcha") or state.get("riskBlocking"):
            payload["warning"] = "页面存在验证码/风险提示相关 DOM，但当前已登录，按登录态有效处理。"
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if state.get("captcha") or state.get("riskBlocking"):
        payload["ok"] = False
        payload["reason"] = "出现验证码/账号风险二次验证，自动登录无法通过，转人工。"
        print(json.dumps(payload, ensure_ascii=False))
        return 2

    payload["reason"] = f"[{mode}] 未检测到登录态"
    print(json.dumps(payload, ensure_ascii=False))
    return 1 if check_only else 2


def main() -> int:
    ap = argparse.ArgumentParser(description="千里马 VIP 自动登录/登录态检查")
    ap.add_argument("--mode", choices=["cdp", "kimi"], default="cdp", help="cdp=Phase1专用调试Chrome；kimi=Kimi WebBridge")
    ap.add_argument("--check", action="store_true", help="只检查登录态，不填写账号密码")
    ap.add_argument("--cdp-port", type=int, default=9222)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    args = ap.parse_args()

    try:
        if args.mode == "cdp":
            if websockets is None:
                print(json.dumps({"ok": False, "reason": "缺少 websockets 库"}, ensure_ascii=False))
                return 2
            ws_url = find_page(args.cdp_port)
            if args.check:
                return exit_for_state(args.mode, asyncio.run(check_cdp(ws_url)), True)
            if not args.config:
                print(json.dumps({"ok": False, "reason": "未配置 QLM_BID_CONFIG 或 --config"}, ensure_ascii=False))
                return 2
            account, password = read_credentials(Path(args.config))
            if not account or not password:
                print(json.dumps({"ok": False, "reason": "配置里未读到账号/密码"}, ensure_ascii=False))
                return 2
            return exit_for_state(args.mode, asyncio.run(login_cdp(ws_url, account, password)), False)

        if args.check:
            return exit_for_state(args.mode, check_kimi(), True)
        account, password = read_credentials(Path(args.config))
        if not account or not password:
            print(json.dumps({"ok": False, "reason": "配置里未读到账号/密码"}, ensure_ascii=False))
            return 2
        return exit_for_state(args.mode, login_kimi(account, password), False)

    except Exception as exc:
        print(json.dumps({"ok": False, "mode": args.mode, "reason": f"登录执行异常：{exc}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
