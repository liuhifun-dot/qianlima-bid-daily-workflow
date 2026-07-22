# -*- coding: utf-8 -*-
"""Verify the installed Skill release identity and payload hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REQUIRED_FIELDS = {
    "skill_name",
    "release_id",
    "release_date",
    "package_sha256",
    "files",
    "entrypoint",
    "template",
    "rules",
    "minimum_python_version",
    "release_status",
}

# Operational / local-only trees must not fail release integrity checks.
# (e.g. 日志/ written during patch verification)
IGNORED_PAYLOAD_PREFIXES = (
    "日志/",
    "logs/",
    ".git/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    "runs/",
    "output/",
    "runtime/",
    "改动说明/_retest_",  # 复测原始输出，不计入发布完整性
)


def is_ignored_payload(relative_posix: str) -> bool:
    name = relative_posix.replace("\\", "/")
    if name.endswith(".pyc") or name.endswith(".pyo"):
        return True
    # operational backups / retest dumps
    if name.startswith("release-manifest.json.bak") or "/release-manifest.json.bak" in f"/{name}":
        return True
    return any(name.startswith(prefix) or f"/{prefix}" in f"/{name}" for prefix in IGNORED_PAYLOAD_PREFIXES)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(root: Path, manifest_path: Path, allow_release_candidate: bool = False) -> dict:
    errors = []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    missing = sorted(REQUIRED_FIELDS - set(manifest))
    if missing:
        errors.append(f"manifest missing fields: {missing}")
    release_status = manifest.get("release_status")
    allowed_statuses = {"released", "release_candidate"} if allow_release_candidate else {"released"}
    if release_status not in allowed_statuses:
        errors.append(
            f"release_status is not allowed: {release_status!r}; allowed={sorted(allowed_statuses)}"
        )

    listed_paths = []
    for item in manifest.get("files") or []:
        relative = item.get("path")
        expected = str(item.get("sha256") or "").lower()
        if not relative or not expected:
            errors.append(f"invalid file manifest entry: {item}")
            continue
        normalized = Path(relative).as_posix()
        listed_paths.append(normalized)
        target = root / relative
        if not target.exists():
            errors.append(f"missing release file: {relative}")
            continue
        actual = sha256(target)
        if actual != expected:
            errors.append(f"SHA256 mismatch: {relative}; expected={expected}; actual={actual}")

    duplicate_paths = sorted({path for path in listed_paths if listed_paths.count(path) > 1})
    if duplicate_paths:
        errors.append(f"duplicate manifest paths: {duplicate_paths}")

    payload_paths = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.resolve() != manifest_path.resolve()
        and not is_ignored_payload(path.relative_to(root).as_posix())
    )
    unlisted_paths = sorted(set(payload_paths) - set(listed_paths))
    stale_paths = sorted(set(listed_paths) - set(payload_paths))
    if unlisted_paths:
        errors.append(f"unlisted release files: {unlisted_paths}")
    if stale_paths:
        errors.append(f"manifest lists missing payload files: {stale_paths}")

    for key in ("entrypoint", "template", "rules"):
        relative = manifest.get(key)
        if relative and not (root / relative).exists():
            errors.append(f"{key} does not exist: {relative}")

    result = {
        "ok": not errors,
        "release_id": manifest.get("release_id"),
        "release_status": manifest.get("release_status"),
        "root": str(root),
        "manifest": str(manifest_path),
        "package_sha256": manifest.get("package_sha256"),
        "package_sha256_note": manifest.get("package_sha256_note", ""),
        "files_checked": len(manifest.get("files") or []),
        "payload_files_checked": len(payload_paths),
        "unlisted_files": unlisted_paths,
        "stale_manifest_files": stale_paths,
        "errors": errors,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Qianlima Skill release manifest")
    parser.add_argument("--root", help="Skill root; defaults to the parent of scripts/")
    parser.add_argument("--manifest", help="release-manifest.json path")
    parser.add_argument("--output")
    parser.add_argument(
        "--allow-release-candidate",
        action="store_true",
        help="Allow integrity validation of a release_candidate; deployment still requires released.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    manifest_path = Path(args.manifest).resolve() if args.manifest else root / "release-manifest.json"
    if not manifest_path.exists():
        print(json.dumps({"ok": False, "errors": [f"manifest not found: {manifest_path}"]}, ensure_ascii=False))
        return 1
    result = verify(root, manifest_path, allow_release_candidate=args.allow_release_candidate)
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())