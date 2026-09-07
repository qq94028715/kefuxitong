"""自动维护前端版本号（frontend/src/version.js）。

用法：
    python scripts/bump_version.py                # patch +1：v0.16.1 -> v0.16.2
    python scripts/bump_version.py --minor        # v0.16.1 -> v0.17.0
    python scripts/bump_version.py --major        # v0.16.1 -> v1.0.0
    python scripts/bump_version.py --set v1.2.0   # 直接指定
    python scripts/bump_version.py --build-only   # 只刷新 BUILD / BUILD_TIME，不动版本号

git pre-commit 钩子会自动调用本脚本（patch +1），
若本次提交不想改版本号：  SKIP_VERSION_BUMP=1 git commit ...
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # kefuxitong/
VERSION_FILE = ROOT / "frontend" / "src" / "version.js"

VER_RE = re.compile(r"export const APP_VERSION = '(v\d+\.\d+\.\d+)'")
BUILD_RE = re.compile(r"export const BUILD = '(\d+)'")
TIME_RE = re.compile(r"export const BUILD_TIME = '([^']*)'")


def parse(ver: str) -> tuple[int, int, int]:
    return tuple(int(x) for x in ver.lstrip("v").split("."))  # type: ignore[return-value]


def git_commit_count() -> int:
    """当前分支 commit 数（pre-commit 时 +1，表示即将生成的那个）。"""
    try:
        out = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            return int(out.stdout.strip()) + 1
    except Exception:
        pass
    return -1


def next_version(cur: str, mode: str, explicit: str | None) -> str:
    if explicit:
        return explicit if explicit.startswith("v") else "v" + explicit
    major, minor, patch = parse(cur)
    if mode == "major":
        return f"v{major + 1}.0.0"
    if mode == "minor":
        return f"v{major}.{minor + 1}.0"
    return f"v{major}.{minor}.{patch + 1}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patch", action="store_true")
    ap.add_argument("--minor", action="store_true")
    ap.add_argument("--major", action="store_true")
    ap.add_argument("--set", dest="set_ver")
    ap.add_argument("--build-only", action="store_true")
    args = ap.parse_args()

    if os.environ.get("SKIP_VERSION_BUMP") == "1":
        print("[bump] SKIP_VERSION_BUMP=1，跳过版本更新")
        return 0

    if not VERSION_FILE.exists():
        print(f"[bump] 找不到 {VERSION_FILE}", file=sys.stderr)
        return 1

    src = VERSION_FILE.read_text(encoding="utf-8")

    m_ver = VER_RE.search(src)
    m_build = BUILD_RE.search(src)
    if not m_ver or not m_build:
        print("[bump] version.js 格式异常，未找到 APP_VERSION / BUILD", file=sys.stderr)
        return 1

    cur = m_ver.group(1)
    cur_build = int(m_build.group(1))

    mode = "major" if args.major else "minor" if args.minor else "patch"
    new_ver = cur if args.build_only else next_version(cur, mode, args.set_ver)

    # BUILD：优先用 git commit 数，取不到就自增
    cnt = git_commit_count()
    new_build = str(cnt) if cnt > 0 else str(cur_build + 1)
    new_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    out = VER_RE.sub(f"export const APP_VERSION = '{new_ver}'", src)
    out = BUILD_RE.sub(f"export const BUILD = '{new_build}'", out)
    out = TIME_RE.sub(f"export const BUILD_TIME = '{new_time}'", out)

    VERSION_FILE.write_text(out, encoding="utf-8")

    if new_ver != cur:
        print(f"[bump] {cur} -> {new_ver}  (build {new_build}, {new_time})")
    else:
        print(f"[bump] 版本保持 {new_ver}，刷新 build {new_build} / {new_time}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
