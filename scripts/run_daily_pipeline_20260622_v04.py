# -*- coding: utf-8 -*-
"""Qianlima daily workflow orchestrator, 20260622 v04.

Compute one run context, execute Phase 1 through 4 fail-fast, pass explicit
artifact paths between phases, use CDP evidence reading, and write a pipeline manifest.

Active chain:
- Phase 0: ensure_browser_channel_20260622_v01.py
- Phase 1: bid_export_auto_v1.py
- Phase 2A: bid_screening_20260622_v02.py
- Phase 2B/2C: CDP v05+validator v03
- Phase 2D: bid_business_rejudge_20260622_v04.py
- Phase 3/4: gen_report_archive_push_formal_20260622_v06.py

2026-07-10 更新：统一使用 CDP 通道，删除 Kimi 分支。
2026-07-13 P0 补丁：localhost CDP Host、合法全排除、needs_retry 一次重试。
2026-07-14：S1 额度0 fail-fast / S2 CDP等锁 / S4 soft-continue 收紧 / S5 fallback 开关。
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# allow importing sibling lock helper from scripts/ or 03_脚本工具/
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
try:
    from cdp_run_lock_20260714_v01 import acquire_cdp_lock, release_cdp_lock
except ImportError:  # pragma: no cover
    acquire_cdp_lock = None  # type: ignore
    release_cdp_lock = None  # type: ignore

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SOP_ROOT = Path(__file__).resolve().parents[1]
TOOLS = SOP_ROOT / "03_脚本工具"
OUTPUT_ROOT = SOP_ROOT / "output"
DEFAULT_RUNS_DIR = SOP_ROOT / "runs"
RUNTIME_DIR = SOP_ROOT / "runtime"
BROWSER_OWNER_STATE = RUNTIME_DIR / "browser_owner_state.json"

# Chrome 150+ DevTools HTTP only accepts Host: localhost (127.0.0.1 returns 404).
CDP_HTTP_HOST = "localhost"

SCRIPT_EXPORT = TOOLS / "bid_export_auto_v1.py"
SCRIPT_BROWSER_ENSURE = TOOLS / "ensure_browser_channel_20260622_v01.py"
SCRIPT_SCREEN = TOOLS / "bid_screening_20260622_v02.py"
SCRIPT_CDP_EVIDENCE = TOOLS / "qianlima_cdp_body_attachment_reader_20260624_v05.py"
SCRIPT_CDP_EVIDENCE_VALIDATE = TOOLS / "validate_cdp_body_attachment_reader_20260622_v03.py"
SCRIPT_REJUDGE = TOOLS / "bid_business_rejudge_20260622_v04.py"
SCRIPT_FORMAL = TOOLS / "gen_report_archive_push_formal_20260622_v06.py"

PHASES = ["1", "2a", "2b", "2c", "2d", "34"]
PHASE_LABEL = {
    "preflight": "浏览器与登录预检",
    "1": "Phase 1 千里马导出",
    "2a": "Phase 2A 初筛",
    "2b": "Phase 2B VIP正文读取",
    "2c": "Phase 2C 附件预览/OCR",
    "2d": "Phase 2D 业务复判",
    "34": "Phase 3/4 日报+归档+钉盘+钉钉",
}


class PipelineError(Exception):
    def __init__(self, phase: str, reason: str):
        self.phase = phase
        self.reason = reason
        super().__init__(f"[{phase}] {reason}")


def log(msg: str) -> None:
    print(f"[pipeline] {msg}", flush=True)


def compact_date(value: str | None) -> str:
    if value:
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 8:
            return digits[:8]
    return datetime.now().strftime("%Y%m%d")


def iso_date(value: str) -> str:
    c = compact_date(value)
    return f"{c[:4]}-{c[4:6]}-{c[6:8]}"


def default_source_range(run_date: str) -> tuple[str, str]:
    end = datetime.strptime(compact_date(run_date), "%Y%m%d").date()
    start = end - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def read_pointer(*candidates: Path) -> str:
    for cand in candidates:
        p = Path(cand)
        if p.exists():
            txt = p.read_text(encoding="utf-8").strip()
            if txt:
                return txt
    return ""


def read_json(path: Path) -> dict:
    """读取 JSON 文件。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require(state: dict, key: str, phase: str, cli_flag: str) -> str:
    value = state.get(key)
    if not value:
        raise PipelineError(
            phase,
            f"缺少输入 {key}；请用 {cli_flag} 显式传入，或从更早的阶段开始跑（--start-phase）。",
        )
    if not Path(value).exists():
        raise PipelineError(phase, f"输入文件不存在：{value}")
    return str(value)


LOGIN_SCRIPT = TOOLS / "qianlima_auto_login_20260622_v02.py"
_RUNTIME = {"cdp_port": 9222, "config": None}
LOGIN_MARKERS = ("登录状态超时", "请重新登录", "need_login", "hasLoginGate", "存在登录态", "请登录后查看")




def read_browser_owner_state() -> dict:
    if not BROWSER_OWNER_STATE.exists():
        return {}
    try:
        return json.loads(BROWSER_OWNER_STATE.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def write_browser_owner_state(mode: str, phase: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "active_mode": mode,
        "last_login_ok_at": datetime.now().isoformat(timespec="seconds"),
        "last_success_phase": phase,
        "note": "统一使用 CDP 通道，Kimi 通道已弃用（2026-07-10）。",
    }
    BROWSER_OWNER_STATE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def check_login_mode(mode: str) -> bool | None:
    if not LOGIN_SCRIPT.exists():
        return False
    cmd = [sys.executable, str(LOGIN_SCRIPT), "--mode", mode, "--check"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(SOP_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
    except Exception:
        return None
    if proc.returncode == 0:
        return True
    if proc.returncode == 2:
        return None
    return False


def guard_phase1_browser_owner() -> None:
    """Phase 1 浏览器通道守卫。

    Phase 1 脚本（bid_export_auto_v1.py）只支持 CDP 通道。
    2026-07-10 更新：统一使用 CDP，删除 Kimi 分支。
    """
    cdp_login = check_login_mode("cdp")
    if cdp_login is True:
        write_browser_owner_state("cdp", "phase1_preflight")
        return
    if cdp_login is None:
        raise PipelineError("1", "CDP 千里马登录态检查遇到安全验证/异常页面，停止等待人工处理。")

    # CDP 未登录
    raise PipelineError("1", "CDP 未登录，无法执行 Phase 1。请手动登录或检查自动登录配置。")

def select_evidence_provider(requested: str) -> str:
    """Phase 2B/2C 证据通道选择。

    2026-07-10 更新：统一使用 CDP，删除 Kimi 分支。
    """
    if requested == "kimi":
        log("警告：--evidence-provider kimi 已弃用，自动切换到 cdp")
        requested = "cdp"

    if requested == "cdp":
        state = check_login_mode("cdp")
        if state is True:
            write_browser_owner_state("cdp", "phase2_provider_selected")
            return "cdp"
        if state is None:
            raise PipelineError("2b", "CDP 通道出现验证码或异常页面，停止证据读取。")
        if attempt_login("cdp") and check_login_mode("cdp") is True:
            write_browser_owner_state("cdp", "phase2_provider_login_restored")
            return "cdp"
        raise PipelineError("2b", "CDP 通道未登录且自动恢复失败。")

    # auto 模式：只检查 CDP
    state = check_login_mode("cdp")
    if state is True:
        write_browser_owner_state("cdp", "phase2_provider_auto")
        return "cdp"
    if state is None:
        raise PipelineError("2b", "CDP 通道处于验证码/异常页面。")
    raise PipelineError("2b", "CDP 未检测到有效千里马登录态；禁止跳过正文和附件证据。")


def attempt_login(mode: str = "cdp") -> bool:
    if not LOGIN_SCRIPT.exists():
        log("未找到自动登录脚本，跳过自动登录。")
        return False
    cmd = [sys.executable, "-X", "utf8", str(LOGIN_SCRIPT), "--mode", mode, "--cdp-port", str(_RUNTIME["cdp_port"])]
    if _RUNTIME.get("config"):
        cmd += ["--config", str(_RUNTIME["config"])]
    log(f"检测到登录失效，尝试自动登录（方案A，通道={mode}）…")
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if p.stdout:
        print(p.stdout)
    if p.returncode != 0 and p.stderr:
        print(p.stderr, file=sys.stderr)
    return p.returncode == 0


def read_config_field(config_text: str, key: str) -> str:
    """Read a key from external sensitive config (same patterns as Phase 4 gen_report)."""
    patterns = [
        rf"{re.escape(key)}:\s*\"([^\"]*)\"",
        rf"{re.escape(key)}\s*=\s*\"([^\"]*)\"",
        rf"{re.escape(key)}\s*[:=]\s*([^\s\r\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, config_text)
        if match:
            return match.group(1).strip().strip('"')
    return ""


def resolve_failure_webhook() -> str:
    """Prefer named webhook field; fall back to URL scan without printing secrets."""
    cfg_value = _RUNTIME.get("config") or os.environ.get("QLM_BID_CONFIG", "")
    if not cfg_value:
        return ""
    cfgp = Path(str(cfg_value))
    if not cfgp.is_file():
        return ""
    text = cfgp.read_text(encoding="utf-8", errors="ignore")
    for key in ("dingtalk_webhook_url", "dingtalk_failure_webhook_url", "webhook_url"):
        value = read_config_field(text, key)
        if value.startswith("https://oapi.dingtalk.com/robot/send"):
            return value
    match = re.search(
        r"https://oapi\.dingtalk\.com/robot/send\?access_token=[A-Za-z0-9_-]+",
        text,
    )
    return match.group(0) if match else ""


def notify_dingtalk(text: str) -> bool:
    """Send failure/ops alert. Never log webhook URL or token. Returns success."""
    webhook = resolve_failure_webhook()
    if not webhook:
        log("失败告警未发送：未找到 dingtalk_webhook_url（或 QLM_BID_CONFIG 未配置）")
        return False
    try:
        import urllib.request

        req = urllib.request.Request(
            webhook,
            data=json.dumps(
                {"msgtype": "text", "text": {"content": text}},
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        if '"errcode":0' in body.replace(" ", "") or '"errcode": 0' in body:
            log("失败告警已发送到钉钉")
            return True
        log(f"失败告警钉钉返回非成功：{body[:200]}")
        return False
    except Exception as exc:
        log(f"失败告警发送异常：{type(exc).__name__}: {exc}")
        return False


# Long-running phases: inherit stdout so schedulers see heartbeats (not silent capture).
INHERIT_STDOUT_PHASES = {"1", "2b", "preflight"}


def run_phase(phase: str, script: Path, args: list[str], timeout: int, login_retry: bool = False, login_mode: str = "cdp") -> subprocess.CompletedProcess:
    if not script.exists():
        raise PipelineError(phase, f"阶段脚本缺失：{script}")
    cmd = [sys.executable, "-X", "utf8", str(script), *args]
    log(f"{PHASE_LABEL[phase]} -> {' '.join(cmd)}")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    inherit = phase in INHERIT_STDOUT_PHASES
    effective_timeout = max(timeout, 1500) if phase == "1" else timeout

    def execute_once() -> subprocess.CompletedProcess:
        if inherit:
            # Inherit stdout/stderr so Agent/scheduler sees progress in real time.
            return subprocess.run(
                cmd,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=effective_timeout,
            )
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=effective_timeout,
        )

    proc = execute_once()
    if proc.stdout:
        print(proc.stdout)
    if proc.returncode != 0:
        blob = (proc.stdout or "") + "\n" + (proc.stderr or "")
        # 仅登录类失败才重试；额度 0 / 业务失败不得整段 Phase1 重跑（会误吞失败甚至假成功）
        should_retry_login = login_retry and any(marker in blob for marker in LOGIN_MARKERS)
        if should_retry_login and attempt_login(login_mode):
            log(f"[login_retry] phase={phase} 检测到登录类失败，自动登录后重跑一次")
            proc = execute_once()
            if proc.stdout:
                print(proc.stdout)
        elif login_retry and phase == "1" and proc.returncode != 0:
            log(f"[login_retry] phase=1 非登录失败（rc={proc.returncode}），不重跑")
        if proc.returncode != 0:
            if proc.stderr:
                print(proc.stderr, file=sys.stderr)
            raise PipelineError(phase, f"脚本返回码 {proc.returncode}")
    return proc

def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def cdp_endpoint(port: int) -> str:
    return f"http://{CDP_HTTP_HOST}:{port}"


def screening_needs_vip_body(screening: dict) -> bool:
    """True when Phase 2A kept any project that must enter VIP body/attachment reading."""
    for key in ("recommended", "considered", "low_score"):
        rows = screening.get(key) or []
        if isinstance(rows, list) and rows:
            return True
    return False


def write_empty_evidence_artifacts(evidence_dir: Path, run_date: str, reason: str) -> tuple[str, str]:
    """Legal full-exclude path: no VIP targets, emit empty but valid artifacts."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    vip_path = evidence_dir / f"VIP原文阅读_CDP_{run_date}_v05.json"
    attachment_path = evidence_dir / f"附件预览正文读取_CDP_{run_date}_v05.json"
    generated = datetime.now().isoformat(timespec="seconds")
    write_json(
        vip_path,
        {
            "version": "CDP-v05",
            "generated_at": generated,
            "source": "pipeline_empty_evidence",
            "total": 0,
            "summary": {"ok": 0, "need_login": 0, "captcha": 0, "error": 0, "body_empty": 0},
            "projects": [],
            "legal_empty": True,
            "reason": reason,
        },
    )
    write_json(
        attachment_path,
        {
            "version": "CDP-v05",
            "generated_at": generated,
            "source_vip_json": str(vip_path),
            "targets_total": 0,
            "summary": {"ok": 0, "partial": 0, "unreadable": 0, "no_attachment": 0},
            "results": [],
            "legal_empty": True,
            "reason": reason,
        },
    )
    return str(vip_path), str(attachment_path)


def pick_latest_evidence(evidence_dir: Path, run_date: str) -> tuple[str, str]:
    vip_candidates = sorted(
        evidence_dir.glob(f"VIP*CDP_{run_date}_v*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    attachment_candidates = sorted(
        (p for p in evidence_dir.glob(f"*CDP_{run_date}_v*.json") if not p.name.startswith("VIP")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not vip_candidates or not attachment_candidates:
        raise PipelineError("2b", "CDP evidence reader did not produce both VIP and attachment JSON files.")
    return str(vip_candidates[0]), str(attachment_candidates[0])


def run_cdp_evidence_validation(
    screening: str,
    vip_json: str,
    attachment_json: str,
    validation_out: Path,
    timeout: int = 300,
) -> dict:
    """Run CDP evidence validator; return parsed result even when exit code is non-zero."""
    if not SCRIPT_CDP_EVIDENCE_VALIDATE.exists():
        raise PipelineError("2b", f"阶段脚本缺失：{SCRIPT_CDP_EVIDENCE_VALIDATE}")
    cmd = [
        sys.executable, "-X", "utf8", str(SCRIPT_CDP_EVIDENCE_VALIDATE),
        "--input", screening,
        "--vip-json", vip_json,
        "--attachment-json", attachment_json,
        "--output", str(validation_out),
    ]
    log(f"{PHASE_LABEL['2b']} 校验 -> {' '.join(cmd)}")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if validation_out.exists():
        try:
            return read_json(validation_out)
        except Exception:
            pass
    blob = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    try:
        return json.loads(blob)
    except Exception:
        return {
            "ok": False,
            "status": "blocked",
            "needs_retry": False,
            "blocked": True,
            "errors": [f"validator exit={proc.returncode}; output unparseable"],
        }


def run_phase2_evidence(
    *,
    screening: str,
    run_dir: Path,
    run_date: str,
    run_id: str,
    cdp_port: int,
    config: str | None,
    phase_timeout: int,
    state: dict,
    force_reread: bool = False,
) -> str:
    """Phase 2B/2C: CDP body+attachment with legal-empty short circuit and needs_retry once."""
    screening_payload = read_json(Path(screening))
    evidence_dir = run_dir / "03_body" / "cdp_evidence"
    validation_out = run_dir / "04_attachment" / f"CDP证据校验_{run_id}.json"

    already = (
        not force_reread
        and state.get("vip_json")
        and state.get("attachment_json")
        and Path(state["vip_json"]).exists()
        and Path(state["attachment_json"]).exists()
    )

    if not screening_needs_vip_body(screening_payload):
        log("Phase 2A 无推荐/待读项目（合法全排除），跳过 VIP 正文/附件读取，写入空证据产物。")
        vip_path, att_path = write_empty_evidence_artifacts(
            evidence_dir,
            run_date,
            "Phase 2A 全部硬规则排除或无可读项目；VIP 空为合法结果",
        )
        state["vip_json"] = vip_path
        state["attachment_json"] = att_path
        write_json(
            validation_out,
            {
                "ok": True,
                "status": "ok",
                "needs_retry": False,
                "blocked": False,
                "legal_empty": True,
                "warnings": ["合法全排除：跳过 CDP 证据读取与项目级校验"],
                "errors": [],
            },
        )
        state["cdp_evidence_validation"] = str(validation_out)
        return vip_path

    if already:
        log(f"沿用已有证据：vip={state['vip_json']} attachment={state['attachment_json']}")
        vip_path = state["vip_json"]
        att_path = state["attachment_json"]
        result = run_cdp_evidence_validation(screening, vip_path, att_path, validation_out)
        state["cdp_evidence_validation"] = str(validation_out)
        if result.get("ok") or result.get("status") == "ok":
            return vip_path
        if result.get("needs_retry") or result.get("status") == "needs_retry":
            log("已有证据校验为 needs_retry，将重新读取一次。")
        elif result.get("blocked") or result.get("status") == "blocked":
            raise PipelineError(
                "2b",
                f"CDP 证据校验 blocked：{result.get('errors') or result.get('blocked_reasons')}",
            )
        else:
            raise PipelineError("2b", f"CDP 证据校验失败：{result}")

    max_attempts = 2  # first pass + one needs_retry recovery
    last_result: dict = {}
    for attempt in range(1, max_attempts + 1):
        evidence_args = [
            "--input", screening,
            "--output-dir", str(evidence_dir),
            "--date", run_date,
            "--cdp", cdp_endpoint(cdp_port),
        ]
        if config:
            evidence_args += ["--config", str(config)]
        log(f"CDP 证据读取 attempt {attempt}/{max_attempts}")
        run_phase(
            "2b",
            SCRIPT_CDP_EVIDENCE,
            evidence_args,
            phase_timeout,
            login_retry=True,
            login_mode="cdp",
        )
        vip_path, att_path = pick_latest_evidence(evidence_dir, run_date)
        state["vip_json"] = vip_path
        state["attachment_json"] = att_path
        last_result = run_cdp_evidence_validation(screening, vip_path, att_path, validation_out)
        state["cdp_evidence_validation"] = str(validation_out)

        if last_result.get("ok") or last_result.get("status") == "ok":
            log("CDP 证据校验 ok")
            return vip_path

        if (last_result.get("needs_retry") or last_result.get("status") == "needs_retry") and attempt < max_attempts:
            log(f"[needs_retry] 第{attempt}次证据校验需重试：{last_result.get('retry_reasons') or last_result.get('errors')}")
            attempt_login("cdp")
            time.sleep(3)
            continue

        if last_result.get("blocked") or last_result.get("status") == "blocked":
            raise PipelineError(
                "2b",
                f"CDP 证据校验 blocked：{last_result.get('errors') or last_result.get('blocked_reasons')}",
            )

        # S4 soft-continue：白名单 + 比例阈值（默认 50%；小样本 input<=2 要求全 ok）
        if _soft_continue_allowed(last_result, min_ratio=_RUNTIME.get("soft_continue_min_ratio", 0.5)):
            stats = last_result.get("stats") or {}
            body_ok = int(stats.get("body_read_ok_count") or 0)
            input_count = int(stats.get("input_count") or 0) or 1
            log(
                f"[soft-continue] ratio={body_ok}/{input_count} "
                f"reasons={last_result.get('retry_reasons')}"
            )
            return vip_path

        if last_result.get("needs_retry") or last_result.get("status") == "needs_retry":
            stats = last_result.get("stats") or {}
            log(
                f"[soft-continue-denied] stats={stats} "
                f"reasons={last_result.get('retry_reasons')}"
            )

        raise PipelineError(
            "2b",
            f"CDP 证据校验失败（status={last_result.get('status')}）："
            f"{last_result.get('errors') or last_result.get('retry_reasons') or last_result}",
        )

    raise PipelineError("2b", f"CDP 证据读取在 needs_retry 后仍失败：{last_result}")


def _soft_continue_allowed(result: dict, min_ratio: float = 0.5) -> bool:
    """S4: allow soft-continue only for body_empty-only retries with enough body_ok ratio."""
    if result.get("blocked") or result.get("status") == "blocked":
        return False
    if not (result.get("needs_retry") or result.get("status") == "needs_retry"):
        return False
    if _RUNTIME.get("no_soft_continue"):
        return False

    stats = result.get("stats") or {}
    body_ok = int(stats.get("body_read_ok_count") or 0)
    input_count = int(stats.get("input_count") or 0)
    if body_ok <= 0 or input_count <= 0:
        return False

    reasons = [str(r) for r in (result.get("retry_reasons") or [])]
    blocked_reasons = [str(r) for r in (result.get("blocked_reasons") or [])]
    all_msgs = reasons + blocked_reasons
    ban = ("need_login", "captcha", "status=error", "missing_detail_url", "blocked")
    for msg in all_msgs:
        low = msg.lower()
        if any(b in low or b in msg for b in ban):
            return False
        # 白名单：仅 body_empty 类
        if "body_empty" not in msg and "body empty" not in low:
            # empty reasons list is ok only if body_empty_count>0 and no other retry reasons
            if reasons:
                return False

    if reasons:
        if not all("body_empty" in r for r in reasons):
            return False

    # 小样本：<=2 条要求全部 body_ok
    if input_count <= 2:
        return body_ok >= input_count

    ratio = body_ok / float(input_count)
    return ratio + 1e-9 >= float(min_ratio)


def main() -> int:
    parser = argparse.ArgumentParser(description="标讯自动化 总入口编排脚本 Phase 1->4")
    # 日期（开跑只算一次）
    parser.add_argument("--run-date", help="YYYYMMDD；默认本机今天")
    parser.add_argument("--source-start-date", help="YYYY-MM-DD；默认昨天")
    parser.add_argument("--source-end-date", help="YYYY-MM-DD；默认今天")
    # 阶段控制
    parser.add_argument("--start-phase", choices=PHASES, default="1", help="从哪个阶段开始（断点续跑）")
    parser.add_argument("--end-phase", choices=PHASES, default="34", help="跑到哪个阶段为止")
    # 运行目录
    parser.add_argument("--run-id", help="默认 run_date_HHMMSS")
    parser.add_argument("--run-dir", help="默认 SOP_ROOT/runs/<run_id>")
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT), help="Phase1 导出与 latest 指针根目录")
    # 断点续跑时显式喂入的上游产物
    parser.add_argument("--raw-export", help="千里马导出 Excel（跳过 Phase1 时必填）")
    parser.add_argument("--screening-json", help="初筛 JSON")
    parser.add_argument("--vip-json", help="VIP 正文 JSON")
    parser.add_argument("--attachment-json", help="附件读取 JSON")
    parser.add_argument("--business-json", help="最终业务复判 JSON（--start-phase 34 时必填）")
    # 浏览器/阶段参数
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--evidence-provider", choices=["auto", "cdp"], default="cdp",
                        help="Phase2正文/附件通道；统一使用 CDP（2026-07-10 更新）")
    parser.add_argument("--max-files", type=int, default=3, help="Phase2C 每项目附件数上限")
    parser.add_argument("--ocr-max-pages", type=int, default=4, help="Phase2C OCR 页数上限")
    # Phase3/4 透传给 formal v06
    parser.add_argument("--template")
    parser.add_argument("--config")
    parser.add_argument("--local-archive-dir")
    parser.add_argument("--share-archive-dir")
    parser.add_argument("--dry-run", action="store_true", help="Phase4 只生成、不归档/上传/发钉钉")
    parser.add_argument("--no-send", action="store_true", help="归档上传但不发钉钉")
    parser.add_argument(
        "--phase-timeout",
        type=int,
        default=3600,
        help="单阶段子进程超时秒数（默认 3600；2B 多项目+OCR 常超过 30 分钟）",
    )
    parser.add_argument(
        "--cdp-lock-wait-seconds",
        type=int,
        default=600,
        help="S2：专用 CDP 等锁秒数（默认 600=10 分钟；可用 300=5 分钟）",
    )
    parser.add_argument(
        "--soft-continue-min-body-ratio",
        type=float,
        default=0.5,
        help="S4：2B soft-continue 最低 body_ok/input 比例（默认 0.5）",
    )
    parser.add_argument(
        "--no-soft-continue",
        action="store_true",
        help="S4：关闭 soft-continue，末次 needs_retry 一律失败",
    )
    parser.add_argument(
        "--allow-existing-export-download",
        action="store_true",
        help="S5：Phase1 额度 0 时允许下载导出记录中已生成文件（默认关）",
    )
    args = parser.parse_args()
    _RUNTIME["cdp_port"] = args.cdp_port
    # Prefer explicit --config; fall back to QLM_BID_CONFIG for failure alerts / login.
    _RUNTIME["config"] = args.config or os.environ.get("QLM_BID_CONFIG") or None
    _RUNTIME["soft_continue_min_ratio"] = float(args.soft_continue_min_body_ratio)
    _RUNTIME["no_soft_continue"] = bool(args.no_soft_continue)

    run_date = compact_date(args.run_date)
    if args.source_start_date and args.source_end_date:
        source_start, source_end = args.source_start_date, args.source_end_date
    else:
        source_start, source_end = default_source_range(run_date)
    run_id = args.run_id or f"{run_date}_{datetime.now().strftime('%H%M%S')}"
    run_dir = Path(args.run_dir) if args.run_dir else (DEFAULT_RUNS_DIR / run_id)
    output_root = Path(args.output_root)
    for sub in ["02_screening", "03_body", "04_attachment", "05_rejudge", "99_logs"]:
        (run_dir / sub).mkdir(parents=True, exist_ok=True)

    start_idx = PHASES.index(args.start_phase)
    end_idx = PHASES.index(args.end_phase)
    if start_idx > end_idx:
        raise SystemExit(f"--start-phase {args.start_phase} 晚于 --end-phase {args.end_phase}")
    plan = PHASES[start_idx:end_idx + 1]

    # S2：阶段含 1 或 2b 时需要独占专用 CDP
    needs_cdp = any(p in plan for p in ("1", "2b", "2c"))
    cdp_lock_held = False

    state = {
        "raw_export": args.raw_export or "",
        "screening_json": args.screening_json or "",
        "vip_json": args.vip_json or "",
        "attachment_json": args.attachment_json or "",
        "business_json": args.business_json or "",
        "run_manifest": "",
    }

    manifest = {
        "pipeline": "run_daily_pipeline_20260622_v04_unattended_phase0",
        "run_id": run_id,
        "run_date": run_date,
        "source_start_date": source_start,
        "source_end_date": source_end,
        "run_dir": str(run_dir),
        "start_phase": args.start_phase,
        "end_phase": args.end_phase,
        "dry_run": args.dry_run,
        "no_send": args.no_send,
        "cdp_port": args.cdp_port,
        "allow_existing_export_download": bool(args.allow_existing_export_download),
        "soft_continue_min_body_ratio": float(args.soft_continue_min_body_ratio),
        "no_soft_continue": bool(args.no_soft_continue),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "phases": [],
        "status": "running",
    }

    log(f"run_id={run_id}  日期={run_date}  来源范围={source_start}..{source_end}")
    log(f"计划阶段：{' -> '.join(plan)}  dry_run={args.dry_run} no_send={args.no_send}")

    def _release_lock_safe():
        nonlocal cdp_lock_held
        if cdp_lock_held and release_cdp_lock:
            try:
                release_cdp_lock(args.cdp_port)
            except Exception as exc:
                log(f"CDP 锁释放异常（可忽略）：{exc}")
            cdp_lock_held = False

    try:
        if needs_cdp:
            if acquire_cdp_lock is None:
                raise PipelineError("preflight", "缺少 cdp_run_lock_20260714_v01.py，无法获取 CDP 单写锁")
            wait_s = max(300, int(args.cdp_lock_wait_seconds))  # 下限 5 分钟
            log(f"S2 获取专用 CDP 锁 port={args.cdp_port} wait_seconds={wait_s}")
            try:
                lock_info = acquire_cdp_lock(
                    args.cdp_port,
                    run_id=run_id,
                    wait_seconds=wait_s,
                    owner="run_daily_pipeline",
                )
            except TimeoutError as exc:
                raise PipelineError("preflight", str(exc)) from exc
            cdp_lock_held = True
            atexit.register(_release_lock_safe)
            manifest["cdp_lock"] = {k: lock_info.get(k) for k in ("pid", "port", "path", "acquired_at")}

        if "1" in plan:
            preflight_args = ["--cdp-port", str(args.cdp_port)]
            if args.config:
                preflight_args += ["--config", str(args.config)]
            # Phase 0 preflight 重试：最多3次，间隔30秒（验证码等瞬态问题可自愈）
            preflight_ok = False
            for _attempt in range(1, 4):
                try:
                    run_phase("preflight", SCRIPT_BROWSER_ENSURE, preflight_args, 240)
                    preflight_ok = True
                    break
                except PipelineError as exc:
                    if _attempt < 3:
                        log(f"preflight 第{_attempt}次失败（{exc.reason}），30秒后重试...")
                        time.sleep(30)
                    else:
                        raise
            if preflight_ok:
                manifest["phases"].append({
                    "phase": "preflight",
                    "label": PHASE_LABEL["preflight"],
                    "status": "ok",
                    "output": "cdp",
                })
            guard_phase1_browser_owner()

        evidence_provider = ""
        for phase in plan:
            if phase == "1":
                p_args = ["--cdp-port", str(args.cdp_port), "--output-root", str(output_root),
                          "--start-date", iso_date(source_start), "--end-date", iso_date(source_end)]
                # 登录超时后 Phase1 内自动填账密恢复（无人值守，禁止卡登录框）
                _cfg = args.config or os.environ.get("QLM_BID_CONFIG")
                if _cfg:
                    p_args += ["--config", _cfg]
                if args.allow_existing_export_download:
                    p_args += ["--allow-existing-export-download"]
                    log("S5：已开启 --allow-existing-export-download（额度 0 时可下载已生成行）")
                run_phase(phase, SCRIPT_EXPORT, p_args, max(args.phase_timeout, 1500), login_retry=True)
                state["raw_export"] = read_pointer(
                    output_root / "latest_qianlima_export_path.txt",
                    OUTPUT_ROOT / "latest_qianlima_export_path.txt",
                )
                src_meta = output_root / "latest_qianlima_export_source.json"
                if src_meta.exists():
                    try:
                        meta = json.loads(src_meta.read_text(encoding="utf-8"))
                        manifest["export_source"] = meta.get("source")
                        if meta.get("source") == "fallback_existing_export":
                            log(f"S5 注意：Phase1 使用 fallback 已生成导出 → {meta.get('file')}")
                    except Exception:
                        pass
                out = state["raw_export"]
                write_browser_owner_state("cdp", "phase1_export_completed")

            elif phase == "2a":
                raw = require(state, "raw_export", phase, "--raw-export")
                run_phase(phase, SCRIPT_SCREEN, ["--input", raw, "--date", run_date], args.phase_timeout)
                state["screening_json"] = read_pointer(
                    OUTPUT_ROOT / "v2_4" / "latest_screening_result_path.txt",
                    OUTPUT_ROOT / "latest_screening_result_path.txt",
                )
                screening_payload = read_json(Path(state["screening_json"]))
                raw_export_count = (screening_payload.get("meta") or {}).get("total_raw")
                if raw_export_count is not None:
                    manifest["raw_export_count"] = raw_export_count
                out = state["screening_json"]

            elif phase == "2b":
                screening = require(state, "screening_json", phase, "--screening-json")
                if not evidence_provider:
                    evidence_provider = select_evidence_provider(args.evidence_provider)
                    state["evidence_provider"] = evidence_provider
                    manifest["evidence_provider"] = evidence_provider
                out = run_phase2_evidence(
                    screening=screening,
                    run_dir=run_dir,
                    run_date=run_date,
                    run_id=run_id,
                    cdp_port=args.cdp_port,
                    config=args.config,
                    phase_timeout=args.phase_timeout,
                    state=state,
                )
                vip_payload = read_json(Path(state["vip_json"]))
                # 合法全排除：projects 为空且标记 legal_empty / 或 screening 无需 VIP
                legal_empty = bool(vip_payload.get("legal_empty")) or not screening_needs_vip_body(
                    read_json(Path(screening))
                )
                if not (vip_payload.get("projects") or []) and not legal_empty:
                    raise PipelineError(
                        phase,
                        "VIP 正文读取结果为空，且初筛仍有待读项目；禁止继续复判/生成日报。"
                        "请先恢复登录态或修复正文读取脚本。",
                    )
                out = state["vip_json"]

            elif phase == "2c":
                # CDP 正文+附件在 2B 一并完成；2C 仅确认 attachment 产物路径
                out = require(state, "attachment_json", phase, "--attachment-json")

            elif phase == "2d":
                screening = require(state, "screening_json", phase, "--screening-json")
                vip = require(state, "vip_json", phase, "--vip-json")
                attachment = require(state, "attachment_json", phase, "--attachment-json")
                run_phase(phase, SCRIPT_REJUDGE,
                          ["--screening-json", screening, "--vip-json", vip, "--attachment-json", attachment],
                          args.phase_timeout)
                state["business_json"] = read_pointer(
                    OUTPUT_ROOT / "v2_4" / "latest_business_review_path.txt",
                    OUTPUT_ROOT / "latest_business_review_path.txt",
                )
                out = state["business_json"]

            elif phase == "34":
                business = require(state, "business_json", phase, "--business-json")
                p_args = ["--business-json", business, "--run-date", run_date,
                          "--source-start-date", source_start, "--source-end-date", source_end,
                          "--run-id", run_id, "--run-dir", str(run_dir)]
                if state.get("vip_json"):
                    p_args += ["--vip-json", state["vip_json"]]
                if state.get("raw_export"):
                    p_args += ["--raw-export", state["raw_export"]]
                if state.get("screening_json"):
                    p_args += ["--screening-json", state["screening_json"]]
                if args.template:
                    p_args += ["--template", args.template]
                if args.config:
                    p_args += ["--config", args.config]
                if args.local_archive_dir:
                    p_args += ["--local-archive-dir", args.local_archive_dir]
                if args.share_archive_dir:
                    p_args += ["--share-archive-dir", args.share_archive_dir]
                if args.dry_run:
                    p_args += ["--dry-run"]
                if args.no_send:
                    p_args += ["--no-send"]
                run_phase(phase, SCRIPT_FORMAL, p_args, args.phase_timeout)
                state["run_manifest"] = str(run_dir / f"run_manifest_{run_id}.json")
                out = state["run_manifest"]

            else:
                raise PipelineError(phase, "未知阶段")

            manifest["phases"].append({"phase": phase, "label": PHASE_LABEL[phase], "status": "ok", "output": out})
            if not out:
                log(f"警告：{phase} 未能定位到输出文件路径（指针为空）")

    except PipelineError as exc:
        manifest["phases"].append({"phase": exc.phase, "label": PHASE_LABEL.get(exc.phase, exc.phase),
                                   "status": "failed", "reason": exc.reason})
        manifest["status"] = "failed"
        manifest["failed_phase"] = exc.phase
        notify_dingtalk(f"[标讯自动化] 运行失败，停在 {exc.phase}：{exc.reason}（run_id={run_id}）需人工处理。")
        manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
        mpath = run_dir / f"pipeline_manifest_{run_id}.json"
        write_json(mpath, manifest)
        print(json.dumps({"ok": False, "failed_phase": exc.phase, "reason": exc.reason,
                          "pipeline_manifest": str(mpath)}, ensure_ascii=False, indent=2), file=sys.stderr)
        _release_lock_safe()
        return 1
    finally:
        _release_lock_safe()

    manifest["status"] = "ok"
    manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
    manifest["state"] = state
    # P2-01：从 run_manifest 透传 full_run_success / phase34_ok，避免与 pipeline ok 混淆
    full_run_success = None
    phase34_ok = None
    phase34_status = None
    rm = state.get("run_manifest") or ""
    if rm and Path(rm).exists():
        try:
            rm_data = json.loads(Path(rm).read_text(encoding="utf-8-sig"))
            full_run_success = rm_data.get("full_run_success")
            phase34_ok = rm_data.get("phase34_ok")
            if args.dry_run:
                phase34_status = "dry_run_complete"
            elif args.no_send:
                phase34_status = "archive_only_complete"
            else:
                phase34_status = "full_run_complete" if full_run_success else "phase34_partial"
        except Exception:
            pass
    manifest["full_run_success"] = full_run_success
    manifest["phase34_ok"] = phase34_ok
    manifest["phase34_status"] = phase34_status
    mpath = run_dir / f"pipeline_manifest_{run_id}.json"
    write_json(mpath, manifest)
    out_payload = {
        "ok": True,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "phases_run": plan,
        "dry_run": args.dry_run,
        "no_send": args.no_send,
        "phase34_ok": phase34_ok,
        "phase34_status": phase34_status,
        "full_run_success": full_run_success,
        "run_manifest": state.get("run_manifest", ""),
        "pipeline_manifest": str(mpath),
        "success_semantics": {
            "ok": "pipeline 各阶段无异常跑完",
            "phase34_ok": "日报生成流程完成（含 dry-run）",
            "full_run_success": "非dry-run且归档+钉盘+钉钉均成功；dry-run 时为 false（预期）",
        },
    }
    if args.dry_run:
        out_payload["note"] = "dry_run=true 时 full_run_success=false 为预期，请以 ok=true + phase34_ok 为准"
    print(json.dumps(out_payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PipelineError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise
