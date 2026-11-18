#!/usr/bin/env python3
"""
check_workflows.py — 檢查 .github/workflows/*.yml 讀不讀得進去。

2026-11-18 新增（規劃書階段 2「壞了一定有人知道」）。
起因：9/17 改 daily_sync.yml 時有幾行沒縮排，整個檔案讀不進去，
GitHub 連排程都不跑，網站停了兩個月才發現。

改完任何 workflow、推上 GitHub 之前，先在本機跑：
  python scripts/check_workflows.py
每天的 watchdog.yml 也會跑一次。全部通過回傳 0，有錯回傳 1。
"""
import glob, os, sys
import yaml

# 2026-11-18：Windows 終端機預設 cp950，印 ✓／emoji 會當掉 → 一律用 UTF-8 輸出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bad = 0
for path in sorted(glob.glob(os.path.join(BASE, ".github", "workflows", "*.yml"))):
    name = os.path.basename(path)
    try:
        data = yaml.safe_load(open(path, encoding="utf-8"))
        # YAML 會把 on: 讀成 True，兩種都接受
        if not isinstance(data, dict) or "jobs" not in data or not (("on" in data) or (True in data)):
            raise ValueError("缺少 on: 或 jobs:")
        print(f"✓ {name}")
    except Exception as e:
        bad += 1
        print(f"✗ {name}：{e}")
sys.exit(1 if bad else 0)
