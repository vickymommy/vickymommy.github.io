#!/usr/bin/env python3
"""
fetch_youtube.py — 每日自動從玲玲的 YouTube 頻道 RSS 抓最新影片，更新 content/community.yml

背景：
  「社群交流圈」「iPAS 專區」頁面顯示的影片清單，原本是 content/community.yml 裡
  手動維護的固定清單，玲玲上傳新影片不會自動出現。
  YouTube 頻道本身有公開的 RSS Feed（不需 API Key），格式：
    https://www.youtube.com/feeds/videos.xml?channel_id=<頻道ID>
  這支腳本讀取該 RSS（固定回傳該頻道最新 15 支影片），自動合併進
  content/community.yml 的 videos 清單，取代人工維護。

執行方式（GitHub Action 或本機）：
  cd vickymommy.github.io
  pip install requests pyyaml
  python scripts/fetch_youtube.py

注意：
  - 只更新 videos 清單，其餘欄位（channel/playlist/line/fb/ig/socialIntro 等）
    維持 content/community.yml 原有內容，不會被覆蓋。
  - 影片標題等資訊由 RSS 提供，無法人工覆寫；若要排除某支影片（例如非教學相關的
    生活動態），可在下方 EXCLUDE_VIDEO_IDS 加入影片 ID。
"""

import os, re, sys
import xml.etree.ElementTree as ET

import requests

try:
    import yaml
except ImportError:
    print("缺少 pyyaml，執行 pip install pyyaml", file=sys.stderr)
    sys.exit(1)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMUNITY_YML = os.path.join(BASE, "content", "community.yml")

# 玲玲的 YouTube 頻道 ID（從 https://www.youtube.com/c/VickyMommy 解析取得，
# 頻道自訂網址若日後變動，頻道 ID 本身不會變）
CHANNEL_ID = "UCcQrEf8kKplpj0dW9M5QJLg"
FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"

# 保留最新幾支影片（RSS 本身固定回傳最新 15 支）
MAX_VIDEOS = 15

# 若有不想顯示在網站上的影片，把 video ID 加進這裡（由 Justin 維護）
EXCLUDE_VIDEO_IDS = set()

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


def fetch_latest_videos():
    """回傳 [{'id':..., 'title':..., 'published':...}, ...]，依發布時間新到舊。"""
    try:
        resp = requests.get(FEED_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ 抓取 YouTube RSS 失敗：{e}", file=sys.stderr)
        return None

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"❌ RSS 解析失敗：{e}", file=sys.stderr)
        return None

    videos = []
    for entry in root.findall("a:entry", NS):
        vid_el   = entry.find("yt:videoId", NS)
        title_el = entry.find("a:title", NS)
        pub_el   = entry.find("a:published", NS)
        if vid_el is None or title_el is None:
            continue
        vid = vid_el.text
        if vid in EXCLUDE_VIDEO_IDS:
            continue
        videos.append({
            "id":        vid,
            "title":     title_el.text or "",
            "published": pub_el.text if pub_el is not None else "",
        })

    videos.sort(key=lambda v: v["published"], reverse=True)
    return videos[:MAX_VIDEOS]


def main():
    if not os.path.isfile(COMMUNITY_YML):
        print(f"❌ 找不到 {COMMUNITY_YML}", file=sys.stderr)
        sys.exit(1)

    with open(COMMUNITY_YML, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    old_videos = data.get("videos") or []
    old_ids = [v.get("id") for v in old_videos]

    videos = fetch_latest_videos()
    if videos is None:
        print("⚠️ 抓取失敗，保留 content/community.yml 原有影片清單，不覆蓋")
        return

    new_ids = [v["id"] for v in videos]
    added = [v for v in new_ids if v not in old_ids]

    data["videos"] = [{"id": v["id"], "title": v["title"]} for v in videos]

    with open(COMMUNITY_YML, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"✅ 已更新 content/community.yml，共 {len(videos)} 支影片"
          + (f"（新增 {len(added)} 支：{', '.join(added)}）" if added else "（無新影片）"))


if __name__ == "__main__":
    main()
