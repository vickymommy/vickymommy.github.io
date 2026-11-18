#!/usr/bin/env python3
"""
fetch_youtube.py — 每天抓玲玲 YouTube「指定播放清單」的最新影片，寫進 data/videos.json

【2026-11-18 改版】
  以前：抓整個頻道最新 15 支（不分主題，生活影片、Shorts 都會混進來），寫進 content/community.yml。
  現在：只抓 content/youtube.yml 列的播放清單（AI 相關），每個清單用 YouTube 公開的
        播放清單 RSS（不需 API 金鑰）：
          https://www.youtube.com/feeds/videos.xml?playlist_id=<播放清單ID>
        RSS 每個清單最多回傳 15 支，網站每個清單只顯示最新幾支（showPerPlaylist），夠用。

不會出錯的設計：
  - 某個清單抓失敗、或抓到 0 支 → 保留 data/videos.json 裡這個清單上一次的影片，不清空。
  - 有任何清單出問題 → 記在 data/videos.json 的 "errors"，workflow 下一步會自動開 GitHub Issue 通知。
  - 程式本身一律正常結束（exit 0），不讓 YouTube 暫時連不上擋住方格子文章的同步與部署。

執行方式（GitHub Action 或本機）：
  cd vickymommy.github.io
  pip install requests pyyaml
  python scripts/fetch_youtube.py
"""

import json, os, sys
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

import requests

# 2026-11-18：Windows 終端機預設 cp950，印 ✓／emoji 會當掉 → 一律用 UTF-8 輸出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import yaml
except ImportError:
    print("缺少 pyyaml，執行 pip install pyyaml", file=sys.stderr)
    sys.exit(1)

BASE        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_YML  = os.path.join(BASE, "content", "youtube.yml")
OUT_JSON    = os.path.join(BASE, "data", "videos.json")
FEED_URL    = "https://www.youtube.com/feeds/videos.xml?playlist_id={}"
TAIPEI      = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}
NS = {
    "a":  "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


def fetch_playlist(pid):
    """回傳 [{'id','title','published'}, ...]（新到舊）；失敗丟例外。"""
    resp = requests.get(FEED_URL.format(pid), headers=HEADERS, timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    videos = []
    for entry in root.findall("a:entry", NS):
        vid = entry.findtext("yt:videoId", default="", namespaces=NS)
        if not vid:
            continue
        videos.append({
            "id":        vid,
            "title":     entry.findtext("a:title", default="", namespaces=NS),
            "published": entry.findtext("a:published", default="", namespaces=NS),
        })
    videos.sort(key=lambda v: v["published"], reverse=True)
    return videos


def main():
    with open(CONFIG_YML, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    old = {}
    if os.path.isfile(OUT_JSON):
        try:
            with open(OUT_JSON, encoding="utf-8") as f:
                old = {p.get("key"): p for p in json.load(f).get("playlists", [])}
        except Exception:
            old = {}

    playlists, errors = [], []
    for p in cfg.get("playlists") or []:
        key, pid, title = p.get("key"), p.get("id"), p.get("title", "")
        try:
            videos = fetch_playlist(pid)
            if not videos:
                raise ValueError("抓到 0 支影片（播放清單可能被改成私人或刪除）")
            print(f"✅ {title}：{len(videos)} 支")
        except Exception as e:
            videos = (old.get(key) or {}).get("videos", [])
            msg = f"{title}（{pid}）抓取失敗：{e}；保留上次的 {len(videos)} 支"
            print(f"⚠️ {msg}", file=sys.stderr)
            errors.append(msg)
        playlists.append({
            "key":    key,
            "id":     pid,
            "title":  title,
            "intro":  p.get("intro", ""),
            "url":    f"https://www.youtube.com/playlist?list={pid}",
            "videos": videos,
        })

    out = {
        "_說明":          "由 scripts/fetch_youtube.py 每天自動產生，請勿手動編輯；要改播放清單請改 content/youtube.yml。",
        "updated":        datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M"),
        "channel":        cfg.get("channel", ""),
        "channelIntro":   cfg.get("channelIntro", ""),
        "showPerPlaylist": int(cfg.get("showPerPlaylist", 3)),
        "playlists":      playlists,
        "errors":         errors,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"✓ {len(playlists)} 個播放清單 → data/videos.json" + (f"（{len(errors)} 個有問題）" if errors else ""))


if __name__ == "__main__":
    main()
