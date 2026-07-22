# -*- coding: utf-8 -*-
"""
Kimi WebBridge preflight guard.

This script only fixes one low-risk condition automatically:
an allowed Kimi WebBridge PID file points to a process that no longer exists.

It must never touch Chrome cookies, tokens, browser data, profiles, or user
browser windows.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


KIMI_HOME = Path.home() / ".kimi-webbridge"
ALLOWED_PID_FILES = {
    (KIMI_HOME / "daemon.pid").resolve(),
    (KIMI_HOME / "kimi-webbridge.pid").resolve(),
}
KIMI_EXE = KIMI_HOME / "bin" / "kimi-webbridge.exe"


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
    )
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def read_pid(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
        return int(text)
    except Exception:
        return None


def check_pid_file(path: Path, fix_stale: bool) -> dict:
    resolved = path.resolve()
    if resolved not in ALLOWED_PID_FILES:
        return {
            "path": str(path),
            "allowed": False,
            "status": "forbidden_path",
            "action": "none",
        }

    if not path.exists():
        return {
            "path": str(path),
            "allowed": True,
            "status": "missing",
            "action": "none",
        }

    pid = read_pid(path)
    if pid is None:
        return {
            "path": str(path),
            "allowed": True,
            "status": "invalid_pid_content",
            "action": "stop",
        }

    exists = pid_exists(pid)
    if exists:
        return {
            "path": str(path),
            "allowed": True,
            "pid": pid,
            "process_exists": True,
            "status": "pid_process_alive",
            "action": "none",
        }

    if fix_stale:
        path.unlink()
        action = "deleted_stale_pid"
    else:
        action = "stale_pid_detected_no_delete"

    return {
        "path": str(path),
        "allowed": True,
        "pid": pid,
        "process_exists": False,
        "status": "stale_pid",
        "action": action,
    }


def run_kimi(args: list[str]) -> dict:
    if not KIMI_EXE.exists():
        return {"ok": False, "error": f"missing_exe: {KIMI_EXE}"}
    proc = subprocess.run(
        [str(KIMI_EXE), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Kimi WebBridge safe preflight")
    parser.add_argument(
        "--fix-stale-pid",
        action="store_true",
        help="Delete only allowed Kimi PID files whose process no longer exists.",
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="Run kimi-webbridge start after stale PID cleanup.",
    )
    args = parser.parse_args()

    pid_results = [
        check_pid_file(path, fix_stale=args.fix_stale_pid)
        for path in sorted(ALLOWED_PID_FILES, key=str)
    ]

    result = {
        "ok": True,
        "safety": {
            "deleted_browser_data": False,
            "closed_user_browser": False,
            "touched_cookie_token_profile": False,
        },
        "pid_results": pid_results,
        "status_before_start": run_kimi(["status"]),
    }

    if args.start:
        result["start"] = run_kimi(["start"])
        result["status_after_start"] = run_kimi(["status"])

    print(json.dumps(result, ensure_ascii=False, indent=2))

    for item in pid_results:
        if item.get("status") in {"forbidden_path", "invalid_pid_content"}:
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
