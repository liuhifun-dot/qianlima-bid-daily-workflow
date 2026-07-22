# -*- coding: utf-8 -*-
"""Dedicated CDP single-writer lock for the Qianlima daily pipeline.

S2 (2026-07-14):
- One writer per CDP port (default 9222).
- Wait for lock up to wait_seconds (default 600 = 10 minutes) when another
  pipeline of this family holds it.
- Stale locks (dead PID) are reclaimed with a warning.
- Does not kill foreign Chrome processes; only coordinates pipeline entry.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def lock_path_for_port(port: int) -> Path:
    base = Path(os.environ.get("TEMP") or os.environ.get("TMP") or Path.home() / "AppData" / "Local" / "Temp")
    return base / f"qlm_bid_cdp_{int(port)}.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if handle:
                kernel32.CloseHandle(handle)
                return True
            # If access denied, process may still exist
            err = kernel32.GetLastError()
            return err == 5  # ERROR_ACCESS_DENIED
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def read_lock(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"pid": -1, "corrupt": True}


def write_lock(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def acquire_cdp_lock(
    port: int,
    *,
    run_id: str = "",
    wait_seconds: int = 600,
    poll_seconds: float = 5.0,
    owner: str = "run_daily_pipeline",
) -> dict:
    """Block until lock is acquired or raise TimeoutError / RuntimeError.

    wait_seconds: default 600 (10 min). Use 300 for 5 min floor in callers if needed.
    """
    path = lock_path_for_port(port)
    deadline = time.time() + max(0, int(wait_seconds))
    host = socket.gethostname()
    my_pid = os.getpid()

    while True:
        existing = read_lock(path)
        if existing:
            holder_pid = int(existing.get("pid") or 0)
            if holder_pid == my_pid:
                return {"ok": True, "path": str(path), "reentrant": True, **existing}
            if holder_pid > 0 and _pid_alive(holder_pid):
                if time.time() >= deadline:
                    raise TimeoutError(
                        f"CDP port {port} 已被占用：pid={holder_pid} run_id={existing.get('run_id')} "
                        f"owner={existing.get('owner')} path={path}。"
                        f"已等待 {wait_seconds}s，请确认无并行流水线后重试。"
                    )
                remaining = int(deadline - time.time())
                print(
                    f"[cdp_lock] waiting port={port} holder_pid={holder_pid} "
                    f"run_id={existing.get('run_id')} remaining_s={remaining}",
                    flush=True,
                )
                time.sleep(poll_seconds)
                continue
            # stale
            print(
                f"[cdp_lock] reclaim stale lock port={port} dead_pid={holder_pid} path={path}",
                flush=True,
            )

        payload = {
            "pid": my_pid,
            "port": int(port),
            "run_id": run_id or "",
            "owner": owner,
            "host": host,
            "acquired_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "python": sys.executable,
        }
        try:
            write_lock(path, payload)
        except Exception as exc:
            if time.time() >= deadline:
                raise RuntimeError(f"无法写入 CDP 锁文件 {path}: {exc}") from exc
            time.sleep(poll_seconds)
            continue

        # verify we own it (simple race check)
        check = read_lock(path) or {}
        if int(check.get("pid") or 0) == my_pid:
            print(f"[cdp_lock] acquired port={port} pid={my_pid} run_id={run_id} path={path}", flush=True)
            return {"ok": True, "path": str(path), **payload}

        if time.time() >= deadline:
            raise TimeoutError(f"CDP 锁竞争失败 port={port} path={path}")
        time.sleep(poll_seconds)


def release_cdp_lock(port: int) -> bool:
    path = lock_path_for_port(port)
    existing = read_lock(path)
    if not existing:
        return False
    if int(existing.get("pid") or 0) not in (0, os.getpid()):
        # do not delete others' locks
        return False
    try:
        path.unlink(missing_ok=True)
        print(f"[cdp_lock] released port={port} path={path}", flush=True)
        return True
    except Exception as exc:
        print(f"[cdp_lock] release failed port={port}: {exc}", flush=True)
        return False


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="CDP single-writer lock helper")
    parser.add_argument("action", choices=["acquire", "release", "status"])
    parser.add_argument("--port", type=int, default=9222)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--wait-seconds", type=int, default=600)
    args = parser.parse_args()
    if args.action == "status":
        p = lock_path_for_port(args.port)
        data = read_lock(p)
        print(json.dumps({"path": str(p), "lock": data}, ensure_ascii=False, indent=2))
        return 0
    if args.action == "release":
        ok = release_cdp_lock(args.port)
        print(json.dumps({"ok": ok}, ensure_ascii=False))
        return 0 if ok else 1
    info = acquire_cdp_lock(args.port, run_id=args.run_id, wait_seconds=args.wait_seconds)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
