# -*- coding: utf-8 -*-
"""Runtime and permission preflight for the Qianlima daily workflow."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = os.environ.get("QLM_BID_CONFIG", "")
DEFAULT_LOCAL_ARCHIVE = os.environ.get("QLM_LOCAL_ARCHIVE", "")
DEFAULT_SHARE_ARCHIVE = os.environ.get("QLM_SHARE_ARCHIVE", "")
REQUIRED_MODULES = {
    "openpyxl": "openpyxl", "pandas": "pandas", "requests": "requests",
    "yaml": "pyyaml", "websocket": "websocket-client", "websockets": "websockets",
    "playwright": "playwright", "docx": "python-docx", "pdfplumber": "pdfplumber",
}
OPTIONAL_OCR_MODULES = {"fitz": "pymupdf", "PIL": "pillow", "pytesseract": "pytesseract"}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_runtime_release(runtime_root: Path) -> dict:
    manifest_path = runtime_root / "runtime_release_manifest_20260622_v02.json"
    result = {
        "ok": False,
        "manifest": str(manifest_path),
        "release_id": "",
        "files_checked": 0,
        "errors": [],
    }
    if not manifest_path.exists():
        result["errors"].append("runtime release manifest is missing")
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        result["errors"].append(f"runtime release manifest cannot be parsed: {exc}")
        return result
    result["release_id"] = str(manifest.get("release_id") or "")
    if not result["release_id"]:
        result["errors"].append("runtime release_id is missing")
    for item in manifest.get("files") or []:
        target = Path(str(item.get("target") or ""))
        expected = str(item.get("sha256") or "").lower()
        if not target.exists():
            result["errors"].append(f"runtime file missing: {target}")
            continue
        result["files_checked"] += 1
        actual = file_sha256(target)
        if not expected or actual != expected:
            result["errors"].append(
                f"runtime file SHA256 mismatch: {target}; expected={expected}; actual={actual}"
            )
    result["ok"] = not result["errors"]
    return result

def run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("NODE_OPTIONS", None)
    return subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, env=env,
    )


def local_json(url: str, timeout: int = 4) -> Any:
    # Bypass system proxy; Chrome 150+ CDP expects Host: localhost.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def find_chrome() -> str:
    candidates = [
        os.environ.get("CHROME_EXE"), shutil.which("chrome"), shutil.which("chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe"),
    ]
    return next((str(Path(p)) for p in candidates if p and Path(p).exists()), "")


def dws_candidates() -> list[str]:
    rows = [
        os.environ.get("DWS_CLI"), shutil.which("dws"), shutil.which("dws.cmd"),
        str(Path.home() / "AppData" / "Roaming" / "npm" / "dws.cmd"),
    ]
    rows.extend(str(path) for path in sorted(
        (Path.home() / ".workbuddy" / "binaries" / "node" / "versions").glob("*/dws.cmd"),
        reverse=True,
    ))
    result, seen = [], set()
    for row in rows:
        if not row:
            continue
        key = str(Path(row)).lower()
        if key not in seen and Path(row).exists():
            seen.add(key)
            result.append(str(Path(row)))
    return result


def find_working_dws() -> tuple[str, str, list[str]]:
    failures = []
    for candidate in dws_candidates():
        try:
            probe = run([candidate, "--version"], timeout=20)
        except Exception as exc:
            failures.append(f"{candidate}: {exc}")
            continue
        if probe.returncode == 0:
            version = (probe.stdout or probe.stderr).strip().splitlines()
            return candidate, (version[0] if version else "unknown"), failures
        failures.append(f"{candidate}: returncode={probe.returncode}")
    return "", "", failures


def read_config_value(text: str, key: str) -> str:
    patterns = [
        rf'{re.escape(key)}\s*:\s*"([^"]+)"',
        rf'{re.escape(key)}\s*=\s*"([^"]+)"',
        rf'{re.escape(key)}\s*[:=]\s*([^\s\r\n]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip().strip('"')
    return ""


def has_config_value(text: str, key: str) -> bool:
    patterns = [
        rf"{re.escape(key)}\s*:\s*\"[^\"]+\"",
        rf"{re.escape(key)}\s*=\s*\"[^\"]+\"",
        rf"{re.escape(key)}\s*[:=]\s*\S+",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def has_label_value(text: str, label: str) -> bool:
    return bool(re.search(rf"{re.escape(label)}\s*[：:]\s*([^\s*\r\n]+)", text))


def check_kimi(port: int) -> dict:
    result = {"reachable": False, "running": False, "extension_connected": False}
    for url in (f"http://127.0.0.1:{port}/status", f"http://127.0.0.1:{port}/health"):
        try:
            data = local_json(url)
        except Exception:
            continue
        if isinstance(data, dict):
            result["reachable"] = True
            result["running"] = bool(data.get("running", True))
            result["extension_connected"] = bool(data.get("extension_connected"))
            result["extension_version"] = data.get("extension_version", "")
            break
    return result


def check_cdp(port: int) -> dict:
    result = {"reachable": False, "logged_in_hint": False}
    try:
        # Chrome 150+ rejects Host: 127.0.0.1 on DevTools HTTP (404).
        version = local_json(f"http://localhost:{port}/json/version")
        tabs = local_json(f"http://localhost:{port}/json")
    except Exception:
        return result
    result["reachable"] = bool(version)
    if isinstance(tabs, list):
        qlm = [row for row in tabs if isinstance(row, dict) and "qianlima.com" in str(row.get("url", ""))]
        result["qianlima_tab_count"] = len(qlm)
        result["logged_in_hint"] = any("login" not in str(row.get("url", "")).lower() for row in qlm)
    return result


def safe_exists(path: Path) -> tuple[bool, str]:
    try:
        return path.exists(), ""
    except PermissionError:
        return False, "permission_denied"
    except OSError as exc:
        return False, f"os_error:{exc.__class__.__name__}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Qianlima workflow runtime and permission preflight")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--local-archive-dir", default=DEFAULT_LOCAL_ARCHIVE)
    parser.add_argument("--share-archive-dir", default=DEFAULT_SHARE_ARCHIVE)
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--kimi-port", type=int, default=10086)
    parser.add_argument("--check-online", action="store_true")
    parser.add_argument("--auto-recover-browser", action="store_true",
                        help="Start/recover the dedicated CDP browser before online checks")
    parser.add_argument("--output")
    args = parser.parse_args()

    blocked, permission_required, warnings = [], [], []
    checks: dict[str, Any] = {}

    runtime_root = Path(__file__).resolve().parents[1]
    runtime_release = verify_runtime_release(runtime_root)
    checks["runtime_release"] = runtime_release
    if not runtime_release["ok"]:
        blocked.append("Runtime release identity/hash verification failed.")

    if args.check_online and args.auto_recover_browser:
        ensure_script = Path(__file__).with_name("ensure_browser_channel_20260622_v01.py")
        if not ensure_script.exists():
            blocked.append(f"Browser recovery script is missing: {ensure_script}")
        else:
            # ensure_browser_channel is CDP-only; do not pass --kimi-port (unknown arg).
            recovery = run([
                sys.executable, str(ensure_script),
                "--config", str(args.config),
                "--cdp-port", str(args.cdp_port),
            ], timeout=240)
            recovery_payload = {}
            try:
                recovery_payload = json.loads(recovery.stdout)
            except Exception:
                recovery_payload = {
                    "ok": False,
                    "reason": (recovery.stdout or recovery.stderr or "unknown recovery error")[:500],
                }
            checks["browser_auto_recovery"] = {
                "attempted": True,
                "returncode": recovery.returncode,
                "ok": bool(recovery_payload.get("ok")),
                "owner": recovery_payload.get("owner", ""),
                "started_cdp": bool(recovery_payload.get("started_cdp")),
                "login_recovered": bool(recovery_payload.get("login_recovered")),
                "reason": recovery_payload.get("reason", ""),
            }
            if recovery.returncode != 0:
                permission_required.append(
                    "Automatic browser recovery did not reach a valid CDP login; inspect browser_auto_recovery."
                )

    missing_modules = [package for module, package in REQUIRED_MODULES.items() if importlib.util.find_spec(module) is None]
    missing_ocr = [package for module, package in OPTIONAL_OCR_MODULES.items() if importlib.util.find_spec(module) is None]
    checks["python"] = {
        "executable": sys.executable, "version": sys.version.split()[0],
        "missing_required_packages": missing_modules,
        "missing_optional_ocr_packages": missing_ocr,
    }
    if missing_modules:
        blocked.append("Install required Python packages: " + ", ".join(missing_modules))
    if missing_ocr:
        warnings.append("OCR fallback is incomplete until installed: " + ", ".join(missing_ocr))

    chrome = find_chrome()
    checks["chrome"] = {"found": bool(chrome), "path": chrome}
    if not chrome:
        blocked.append("Install Google Chrome or set CHROME_EXE.")

    config_path = Path(args.config).expanduser() if args.config else None
    text = config_path.read_text(encoding="utf-8", errors="ignore") if config_path and config_path.is_file() else ""
    config_checks = {
        "file_exists": bool(config_path and config_path.is_file()),
        "account_present": has_label_value(text, "账号"),
        "password_present": has_label_value(text, "密码"),
        "webhook_present": has_config_value(text, "dingtalk_webhook_url"),
        # S3：抄送 webhook 可选；仅报告布尔，不打印 URL/token
        "backup_webhook_present": has_config_value(text, "dingtalk_webhook_url_backup"),
        "drive_space_present": has_config_value(text, "dingtalk_drive_space_id"),
        "drive_folder_present": has_config_value(text, "dingtalk_drive_parent_id_for_dws"),
        "drive_url_present": has_config_value(text, "dingtalk_drive_share_url"),
    }
    checks["sensitive_config"] = {"path_configured": bool(config_path), **config_checks}
    checks["dingtalk_webhook_backup_configured"] = bool(config_checks.get("backup_webhook_present"))
    if not config_path or not config_path.is_file():
        permission_required.append("Create the external sensitive config and provide Qianlima, Dingpan, and webhook values.")
    else:
        if not config_checks["account_present"] or not config_checks["password_present"]:
            permission_required.append("Add Qianlima account and password to the external sensitive config.")
        if not config_checks["webhook_present"]:
            permission_required.append("Add dingtalk_webhook_url to the external sensitive config.")
        if not config_checks["backup_webhook_present"]:
            warnings.append(
                "dingtalk_webhook_url_backup is not configured; Phase4 will only send the primary webhook "
                "(set backup URL to enable CC)."
            )
        if not config_checks["drive_space_present"] or not config_checks["drive_folder_present"]:
            permission_required.append("Add Dingpan space and folder IDs to the external sensitive config.")

    dws, dws_version, dws_failures = find_working_dws()
    checks["dws"] = {
        "working": bool(dws), "path": dws, "version": dws_version,
        "broken_candidate_count": len(dws_failures), "auth_checked": False,
        "auth_ok": False, "upload_command_ok": False,
    }
    if not dws:
        permission_required.append("Install or repair DingTalk Workspace CLI (dws).")
    else:
        upload_help = run([dws, "drive", "upload", "--help"], timeout=30)
        checks["dws"]["upload_command_ok"] = upload_help.returncode == 0
        if upload_help.returncode != 0:
            blocked.append("The selected dws CLI does not support drive upload.")
        if args.check_online:
            auth = run([dws, "auth", "status", "--format", "json"], timeout=60)
            checks["dws"]["auth_checked"] = True
            checks["dws"]["auth_ok"] = auth.returncode == 0
            if auth.returncode != 0:
                permission_required.append("Run dws auth login interactively, then rerun preflight.")

    local_value = args.local_archive_dir or read_config_value(text, "local_archive_dir")
    share_value = args.share_archive_dir or read_config_value(text, "share_archive_dir")
    local_archive = Path(local_value) if local_value else None
    share_archive = Path(share_value) if share_value else None
    local_exists, local_error = safe_exists(local_archive) if local_archive else (False, "not_configured")
    share_exists, share_error = safe_exists(share_archive) if share_archive else (False, "not_configured")
    checks["archives"] = {
        "local_configured": bool(local_archive), "local_exists": local_exists, "local_error": local_error,
        "share_configured": bool(share_archive), "share_exists": share_exists, "share_error": share_error,
    }
    if not local_exists:
        permission_required.append("Create or authorize the configured local archive directory.")
    if args.check_online and not share_exists:
        permission_required.append("Connect or authorize the required shared archive path.")

    cdp, kimi = check_cdp(args.cdp_port), check_kimi(args.kimi_port)
    checks["browser_channels"] = {"cdp": cdp, "kimi": kimi}
    if args.check_online and not (cdp.get("reachable") or (kimi.get("running") and kimi.get("extension_connected"))):
        if not args.auto_recover_browser:
            permission_required.append(
                "Start a logged browser channel, or rerun with --auto-recover-browser."
            )

    if blocked:
        status, exit_code = "blocked", 1
    elif permission_required:
        status, exit_code = "permission_required", 2
    elif args.check_online:
        status, exit_code = "ready", 0
    else:
        status, exit_code = "static_checks_passed", 0

    payload = {
        "ok": status in {"ready", "static_checks_passed"}, "status": status,
        "full_run_ready": status == "ready", "online_checks_performed": args.check_online,
        "checks": checks, "blocked": blocked, "permission_required": permission_required,
        "warnings": warnings,
        "rules": {
            "dry_run_is_not_full_success": True,
            "no_dingpan_doc_url_means_no_dingtalk_send": True,
            "never_print_or_package_secret_values": True,
        },
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
