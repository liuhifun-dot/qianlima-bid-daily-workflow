# -*- coding: utf-8 -*-
"""Ensure CDP Chrome is ready for unattended runs.

The formal implementation uses the dedicated CDP Chrome profile.
This helper never closes user browsers and never clears browser data.

P1/P2 (2026-07-13):
- check-only / already-logged-in may succeed without sensitive config
- config is required only for auto-login recovery or first-time CDP start
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


VIP_ROOT = "https://vip.qianlima.com/"
DEFAULT_CONFIG = os.environ.get("QLM_BID_CONFIG", "")
DEFAULT_PROFILE = Path(os.environ.get(
    "QLM_CDP_PROFILE",
    str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Google" / "Chrome" / "User Data CDP"),
))


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else int(payload.get("exit_code", 2))


def local_json(url: str, timeout: int = 4):
    # 绕过系统代理（如 127.0.0.1:7897），否则本地探测会被代理拦截。
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def port_ready(port: int) -> bool:
    # Chrome 150+ DevTools HTTP 端点只接受 Host: localhost，拒绝 127.0.0.1（返回 404）。
    try:
        return bool(local_json(f"http://localhost:{port}/json/version"))
    except Exception:
        return False


def find_chrome() -> str:
    candidates = [
        os.environ.get("CHROME_EXE"),
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe"),
    ]
    return next((str(Path(p)) for p in candidates if p and Path(p).exists()), "")


def run_login(script: Path, config: Path | None, cdp_port: int, check: bool) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-X", "utf8", str(script), "--mode", "cdp"]
    if check:
        cmd.append("--check")
    cmd += ["--cdp-port", str(cdp_port)]
    # --check does not need credentials; only pass config when present.
    if config is not None and str(config):
        cmd += ["--config", str(config)]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=150,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )


def start_cdp(chrome: str, profile: Path, port: int) -> None:
    profile.mkdir(parents=True, exist_ok=True)
    cmd = [
        chrome,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-minimized",
        VIP_ROOT,
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure CDP Chrome is ready for unattended runs")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--login-script")
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE))
    parser.add_argument("--wait-seconds", type=int, default=45)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    script = Path(args.login_script) if args.login_script else Path(__file__).with_name(
        "qianlima_auto_login_20260622_v02.py"
    )
    config = Path(args.config) if args.config else None
    config_exists = bool(config and config.exists())
    payload = {
        "ok": False,
        "started_cdp": False,
        "login_recovered": False,
        "config_exists": config_exists,
        "config_required": False,
        "cdp_port": args.cdp_port,
    }
    if not script.exists():
        payload.update(reason=f"登录脚本不存在：{script}", exit_code=2)
        return emit(payload)

    # ===== CDP 通道检查 =====
    cdp_ready = port_ready(args.cdp_port)
    if cdp_ready:
        check = run_login(script, config, args.cdp_port, True)
        if check.returncode == 0:
            payload.update(
                ok=True,
                reason="CDP 已启动且千里马登录态有效",
                config_required=False,
            )
            return emit(payload)
        if args.check_only:
            payload.update(
                reason="CDP 已启动但登录态无效",
                exit_code=3,
                config_required=not config_exists,
            )
            return emit(payload)
        if not config_exists:
            payload.update(
                reason="CDP 登录态无效且本机敏感配置缺失，无法自动恢复登录",
                exit_code=3,
                config_required=True,
            )
            return emit(payload)
        login = run_login(script, config, args.cdp_port, False)
        if login.returncode == 0:
            payload.update(ok=True, login_recovered=True, reason="CDP 普通登录已自动恢复")
            return emit(payload)
        payload.update(reason="CDP 自动登录失败，可能存在验证码、风险验证或页面结构变化", exit_code=3)
        return emit(payload)

    if args.check_only:
        payload.update(reason="CDP 未启动，且没有可直接用于 Phase 1 的登录通道", exit_code=3)
        return emit(payload)
    if not config_exists:
        payload.update(
            reason="首次运行缺少本机敏感配置，不能启动 CDP 并自动恢复登录",
            exit_code=3,
            config_required=True,
        )
        return emit(payload)

    # 启动 CDP Chrome
    chrome = find_chrome()
    if not chrome:
        payload.update(reason="未找到 Chrome；请安装 Chrome 或设置 CHROME_EXE", exit_code=2)
        return emit(payload)
    start_cdp(chrome, Path(args.profile_dir), args.cdp_port)
    payload["started_cdp"] = True
    deadline = time.monotonic() + max(args.wait_seconds, 5)
    while time.monotonic() < deadline and not port_ready(args.cdp_port):
        time.sleep(1)
    if not port_ready(args.cdp_port):
        payload.update(reason="已尝试启动专用 CDP Chrome，但端口未就绪", exit_code=2)
        return emit(payload)

    check = run_login(script, config, args.cdp_port, True)
    if check.returncode == 0:
        payload.update(ok=True, reason="已启动专用 CDP Chrome，持久登录态有效")
        return emit(payload)
    login = run_login(script, config, args.cdp_port, False)
    if login.returncode == 0:
        payload.update(ok=True, login_recovered=True, reason="已启动专用 CDP Chrome并自动恢复普通登录")
        return emit(payload)
    payload.update(reason="专用 CDP Chrome 已启动，但自动登录失败；需要人工处理验证码或风险验证", exit_code=3)
    return emit(payload)


if __name__ == "__main__":
    raise SystemExit(main())
