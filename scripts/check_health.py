r"""kefuxitong 服务体检：一条命令看出是后端挂了、前端挂了，还是端口被占。

用法：
    python scripts/check_health.py
    scripts\check_health.bat        # Windows 双击运行

检查项：局域网 IP / 后端 8000 / 前端 5173 / 前端→后端代理 / 端口占用进程 / 数据库 / 当前版本
注意：本机有 HTTP 代理（FlClash 等），脚本已强制绕过代理直连，避免误报。
"""
from __future__ import annotations

import os
import re
import socket
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = "http://127.0.0.1:8000"
FRONTEND = "http://127.0.0.1:5173"

OK, BAD, WARN = "[OK]", "[!!]", "[??]"


def http_status(url: str, timeout: float = 3.0) -> tuple[int, str]:
    """返回 (状态码, 说明)。0 表示连不上。强制不走代理。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as r:
            return r.status, "ok"
    except urllib.error.HTTPError as e:
        return e.code, "http-error"
    except Exception as e:  # noqa: BLE001
        return 0, type(e).__name__


def port_owner(port: int) -> str:
    """查端口被哪个进程占用（Windows netstat + tasklist）。"""
    try:
        # Windows 中文系统 netstat 输出是 GBK，不能用 utf-8 解码
        raw = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True, timeout=8, shell=False,
        ).stdout
        out = raw.decode("gbk", errors="ignore")
    except Exception:
        return "未知"
    pids = []
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.append(parts[-1])
    if not pids:
        return "无"
    names = []
    for pid in dict.fromkeys(pids):
        try:
            t = subprocess.run(
                ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                capture_output=True, timeout=8,
            ).stdout.decode("gbk", errors="ignore")
            m = re.search(r'"([^"]+\.exe)"', t)
            names.append(f"{m.group(1)}(PID {pid})" if m else f"PID {pid}")
        except Exception:
            names.append(f"PID {pid}")
    return "、".join(names)


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def read_version() -> str:
    f = ROOT / "frontend" / "src" / "version.js"
    try:
        m = re.search(r"export const APP_VERSION = '([^']+)'", f.read_text(encoding="utf-8"))
        return m.group(1) if m else "未读取到"
    except Exception:
        return "未读取到"


def check_db() -> tuple[str, str]:
    db = ROOT / "backend" / "data" / "kefuxitong.db"
    if not db.exists():
        return BAD, f"找不到 {db}"
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        n = {}
        for t in ("users", "question", "knowledge", "chat_session", "training_batch"):
            try:
                n[t] = con.execute(f'select count(*) from "{t}"').fetchone()[0]
            except Exception:
                n[t] = "-"
        con.close()
        size = db.stat().st_size / 1024
        return OK, f"{size:.0f} KB ｜ " + " ".join(f"{k}={v}" for k, v in n.items())
    except Exception as e:  # noqa: BLE001
        return BAD, f"打不开：{e}"


def main() -> int:
    print("=" * 58)
    print(" kefuxitong 服务体检")
    print("=" * 58)

    ip = lan_ip()
    ver = read_version()
    print(f"\n【访问地址】")
    print(f"  本机      http://localhost:5173")
    print(f"  局域网    http://{ip}:5173       （当前版本 {ver}）")

    print(f"\n【服务状态】")
    b_code, _ = http_status(f"{BACKEND}/docs")
    f_code, _ = http_status(f"{FRONTEND}/")
    print(f"  后端 8000  {'正常' if b_code == 200 else '未响应'}  (HTTP {b_code})  占用：{port_owner(8000)}")
    print(f"  前端 5173  {'正常' if f_code == 200 else '未响应'}  (HTTP {f_code})  占用：{port_owner(5173)}")

    print(f"\n【前端→后端代理】")
    if f_code == 200:
        p_code, _ = http_status(f"{FRONTEND}/api/agent/categories")
        if p_code in (200, 401, 403, 422):
            print(f"  {OK} 代理通（HTTP {p_code}，401/403 表示已到达后端只是没登录）")
        elif p_code == 0:
            print(f"  {BAD} 请求未到达前端（HTTP 0）")
        else:
            print(f"  {WARN} HTTP {p_code}，可能是后端未启动（502）或接口变更")
    else:
        print(f"  {WARN} 前端未启动，跳过代理检查")

    print(f"\n【数据库】")
    flag, msg = check_db()
    print(f"  {flag} {msg}")

    # 结论与建议
    print(f"\n【诊断结论】")
    if b_code == 200 and f_code == 200:
        print(f"  {OK} 前后端都正常。局域网访问不了的话，先查 Windows 防火墙是否放行 node.exe，")
        print(f"     并确认对方电脑与你在同一网段（你的 IP：{ip}）。")
        bad = 0
    else:
        bad = 1
        if b_code != 200:
            print(f"  {BAD} 后端没起来。启动：")
            print(f"     cd backend && .venv\\Scripts\\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
        if f_code != 200:
            print(f"  {BAD} 前端没起来。启动：")
            print(f"     cd frontend && npm run dev")
            print(f"     （或 node node_modules/vite/bin/vite.js --host 0.0.0.0 --port 5173）")
        print(f"  提示：也可双击 scripts\\start.bat 一次性拉起前后端。")

    if "HTTP_PROXY" in os.environ or "http_proxy" in os.environ:
        print(f"\n  注意：检测到系统代理 {os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')}，")
        print(f"        本脚本已绕过代理直连。若浏览器打不开，检查浏览器是否走了代理。")

    print("=" * 58)
    return bad


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        sys.exit(130)
