# -*- coding: utf-8 -*-
"""Deploy the clean Skill resources into a separate writable runtime directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Formal runtime scripts only. Kimi channel scripts are legacy (not copied).
ACTIVE_SCRIPTS = [
    "bid_export_auto_v1.py",
    "bid_screening_20260622_v02.py",
    "bid_business_rules_20260602_v02.py",
    "qianlima_auto_login_20260622_v02.py",
    "ensure_browser_channel_20260622_v01.py",
    "qianlima_cdp_body_attachment_reader_20260624_v05.py",
    "validate_cdp_body_attachment_reader_20260622_v03.py",
    "bid_business_rejudge_20260622_v04.py",
    "validate_phase2_rejudge_20260622_v02.py",
    "report_builder_20260615_v1.py",
    "validate_excel_template_contract_20260603_v02.py",
    "gen_report_archive_push_formal_20260622_v06.py",
    "run_daily_pipeline_20260622_v04.py",
    "runtime_preflight_20260622_v02.py",
    "cdp_run_lock_20260714_v01.py",
    "prepare_runtime_20260622_v02.py",
    "verify_release_manifest_20260623_v01.py",
]

# Kept in Skill package under scripts/ for history; never copy into production runtime.
LEGACY_SCRIPTS_NOT_DEPLOYED = [
    "kimi_webbridge_preflight_20260610_v01.py",
    "kimi_vip_body_read_20260622_v04.py",
    "kimi_attachment_preview_read_20260622_v06.py",
]
TEMPLATE_NAME = "照明招标线索日报_格式样板_20260616_v05.xlsx"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_one(source: Path, target: Path, update: bool) -> dict:
    if not source.exists():
        raise FileNotFoundError(f"Skill resource is missing: {source}")
    if target.exists() and not update:
        raise FileExistsError(
            f"Runtime file already exists: {target}. Use --update only after validating a new Skill release."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {
        "source": str(source),
        "target": str(target),
        "bytes": target.stat().st_size,
        "sha256": sha256(target),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a writable runtime from the clean Qianlima Skill")
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--output")
    parser.add_argument(
        "--allow-release-candidate",
        action="store_true",
        help="Create an isolated test runtime from release_candidate. Never use for production.",
    )
    args = parser.parse_args()

    skill_root = Path(__file__).resolve().parents[1]
    release_manifest_path = skill_root / "release-manifest.json"
    verifier = skill_root / "scripts" / "verify_release_manifest_20260623_v01.py"
    verify_cmd = [
        sys.executable,
        str(verifier),
        "--root",
        str(skill_root),
        "--manifest",
        str(release_manifest_path),
    ]
    if args.allow_release_candidate:
        verify_cmd.append("--allow-release-candidate")
    subprocess.run(verify_cmd, check=True)
    release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8-sig"))
    runtime_root = Path(args.runtime_root).resolve()
    if runtime_root == skill_root or skill_root in runtime_root.parents:
        raise ValueError("Runtime directory must be outside the installed Skill directory.")

    script_source = skill_root / "scripts"
    asset_source = skill_root / "assets"
    tool_target = runtime_root / "03_脚本工具"
    template_target = runtime_root / "02_模板"

    copied = [
        copy_one(script_source / name, tool_target / name, args.update)
        for name in ACTIVE_SCRIPTS
    ]
    copied.append(
        copy_one(asset_source / TEMPLATE_NAME, template_target / TEMPLATE_NAME, args.update)
    )
    copied.append(
        copy_one(
            asset_source / "rules_current.yaml",
            runtime_root / "filter_rules" / "rules_current.yaml",
            args.update,
        )
    )

    # Bundle tpk-ocr next to phase scripts so CDP reader can find it under 03_脚本工具/tpk-ocr.
    tpk_src = script_source / "tpk-ocr"
    tpk_dst = tool_target / "tpk-ocr"
    if tpk_src.is_dir():
        if tpk_dst.exists() and not args.update:
            raise FileExistsError(
                f"Runtime tpk-ocr already exists: {tpk_dst}. Use --update after validating a new Skill release."
            )
        if tpk_dst.exists() and args.update:
            shutil.rmtree(tpk_dst)
        shutil.copytree(tpk_src, tpk_dst)
        for path in sorted(tpk_dst.rglob("*")):
            if path.is_file():
                copied.append({
                    "source": str(tpk_src / path.relative_to(tpk_dst)),
                    "target": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                })

    for name in ("runs", "output", "runtime", "logs"):
        (runtime_root / name).mkdir(parents=True, exist_ok=True)

    payload = {
        "ok": True,
        "release_id": release_manifest.get("release_id"),
        "release_status": release_manifest.get("release_status"),
        "source_release_manifest": str(release_manifest_path),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "skill_root": str(skill_root),
        "runtime_root": str(runtime_root),
        "update": args.update,
        "candidate_test_mode": bool(args.allow_release_candidate),
        "sensitive_config_bundled": False,
        "sensitive_config_rule": (
            "Set QLM_BID_CONFIG or pass --config. Never copy account, password, webhook, "
            "token, Cookie, or Dingpan IDs into the Skill package."
        ),
        "entrypoint": str(tool_target / "run_daily_pipeline_20260622_v04.py"),
        "preflight": str(tool_target / "runtime_preflight_20260622_v02.py"),
        "template": str(template_target / TEMPLATE_NAME),
        "files": copied,
    }
    runtime_manifest = runtime_root / "runtime_release_manifest_20260622_v02.json"
    runtime_manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.resolve() != runtime_manifest.resolve():
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
