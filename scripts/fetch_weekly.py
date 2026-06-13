#!/usr/bin/env python3
"""
fetch_weekly.py — 每日自動從第三方 RSS 來源抓文章，存入 content/weekly/ 待審清單

執行方式（GitHub Action 或本機）：
  cd 網站專案
  pip install requests beautifulsoup4 pyyaml
  python scripts/fetch_weekly.py

來源設定：
  優先讀取 content/weekly_sources.yml（玲玲可在後台管理）。
  找不到時備援使用腳本內硬寫的 FALLBACK_SOURCES。

流程：
  1. 載入 content/weekly_sources.yml（或備援清單）
  2. 從各來源 RSS 抓最新文章（去重複）
  3. 新項目寫入 content/weekly/<date>_<id>.md（status: pending）
  4. 玲玲在 PagesCMS 後台填心情分享後改 status 為 published
  5. build.py 把 published 的項目輸出到 data/weekly.json 供前台顯示
"""

import os, re, hashlib, time, sys, html as html_mod
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    import yaml
except ImportError:
    print("缺少 pyyaml，執行 pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── 路徑 ──────────────────────────────────────────────────────────────────────

BASE             = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEEKLY_DIR       = os.path.join(BASE, "content", "weekly")
SOURCES_YML_PATH = os.path.join(BASE, "content", "weekly_sources.yml")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

# ── 備援來源清單（當 weekly_sources.yml 找不到時使用）──────────────────────────
#
# 正常情況下不會用到這份清單；它的作用只是讓腳本在 YAML 遺失時也能繼續運作。

FALLBACK_SOURCES = [
    {"name": "親子天下",      "url": "https://www.parenting.com.tw/api/rss/article", "category": "news", "max_items": 5, "enabled": True},
    {"name": "翻轉教育",      "url": "https://flipedu.parenting.com.tw/rss",          "category": "news", "max_items": 3, "enabled": True},
    {"name": "未來親子",      "url": "https://futureparenting.cwgv.com.tw/rss",       "category": "news", "max_items": 3, "enabled": True},
    {"name": "媽媽經",        "url": "https://www.familymatters.com.tw/feed/",        "category": "news", "max_items": 3, "enabled": True},
    {"name": "Product Hunt（AI 工具）", "url": "https://www.producthunt.com/feed",    "category": "tool", "max_items": 5, "enabled": True},
    {"name": "The Rundown AI","url": "https://www.therundown.ai/rss",                 "category": "tool", "max_items": 3, "enabled": True},
    {"name": "AI 工具王",     "url": "https://www.toolify.ai/zh/rss",                 "category": "tool", "max_items": 3, "enabled": True},
]

# ── 關鍵字篩選規則（由 Justin 維護，不對玲玲開放）──────────────────────────────
#
# 某些 RSS 來源（如 Product Hunt）內容雜，需要過濾只留 AI 相關的。
# key = 來源名稱（部分符合即可，不分大小寫）
# value = 至少要出現其中一個關鍵字才納入（在標題 + 描述中搜尋）

KEYWORD_FILTERS = {
    "product hunt": ["AI", "ai", "GPT", "LLM", "automation", "generator",
                     "machine learning", "chatbot", "artificial intelligence"],
}

# ── 載入來源設定 ──────────────────────────────────────────────────────────────

def load_sources():
    """
    優先讀 content/weekly_sources.yml；找不到或讀取失敗時用 FALLBACK_SOURCES。
    回傳加上 filter_keywords 的完整來源清單。
    """
    sources = None

    if os.path.isfile(SOURCES_YML_PATH):
        try:
            with open(SOURCES_YML_PATH, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            sources = data.get("sources", []) if data else []
            print(f"📋 來源設定：從 content/weekly_sources.yml 讀取（{len(sources)} 筆）")
        except Exception as e:
            print(f"⚠️ 讀取 weekly_sources.yml 失敗：{e}，改用備援清單", file=sys.stderr)

    if sources is None:
        sources = FALLBACK_SOURCES
        print(f"📋 來源設定：使用備援清單（{len(sources)} 筆）")

    # 根據 KEYWORD_FILTERS 注入關鍵字篩選
    for src in sources:
        name_lower = src.get("name", "").lower()
        for filter_key, keywords in KEYWORD_FILTERS.items():
            if filter_key in name_lower:
                src["filter_keywords"] = keywords
                break

    return sources

# ── 工具函式 ──────────────────────────────────────────────────────────────────

def short_id(url):
    """用 URL 產生 8 碼短 hash，作為項目 ID。"""
    return hashlib.md5(url.encode()).hexdigest()[:8]

def clean_text(html_or_text, max_len=300):
    """移除 HTML 標籤、解碼 HTML 實體（&#8230; → …），截取前 max_len 字。"""
    text = re.sub(r"<[^>]+>", " ", html_or_text or "")
    text = html_mod.unescape(text)          # ← 解碼 &#8230; &amp; 等實體
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] + ("…" if len(text) > max_len else "")

def parse_rss(source):
    """
    抓取單一 RSS 來源，回傳 list of dict。
    每個 dict 包含：title, url, pub_date, excerpt, source_name, category
    """
    import xml.etree.ElementTree as ET

    name       = source.get("name", "")
    rss_url    = source.get("url", "")
    cat        = source.get("category", "news")
    max_n      = source.get("max_items", 5)
    kw_filter  = source.get("filter_keywords", [])

    print(f"  📡 {name}：{rss_url}")
    try:
        time.sleep(0.5)
        resp = requests.get(rss_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"     ⚠️ 抓取失敗：{e}", file=sys.stderr)
        return []

    # 解析 XML（移除 namespace 以簡化）
    content = resp.content
    content = re.sub(rb'xmlns[^=]*="[^"]*"', b'', content)
    content = re.sub(rb'<([a-zA-Z]+):([a-zA-Z]+)', b'<\\1_\\2', content)
    content = re.sub(rb'</([a-zA-Z]+):([a-zA-Z]+)', b'</\\1_\\2', content)

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"     ⚠️ XML 解析失敗：{e}", file=sys.stderr)
        return []

    items = []
    for item in root.iter("item"):
        def gt(tag):
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else ""

        title  = gt("title")
        link   = gt("link") or gt("guid")
        if not link or not title:
            continue

        # 關鍵字篩選（AI 工具類只留有相關字眼的）
        if kw_filter:
            combined = (title + " " + gt("description")).lower()
            if not any(kw.lower() in combined for kw in kw_filter):
                continue

        pub_str = gt("pubDate") or gt("dc_date")
        try:
            from email.utils import parsedate_to_datetime
            pub_dt   = parsedate_to_datetime(pub_str)
            pub_date = pub_dt.strftime("%Y-%m-%d")
        except Exception:
            pub_date = datetime.now().strftime("%Y-%m-%d")

        description = gt("description") or gt("content_encoded") or ""
        excerpt = clean_text(description)

        items.append({
            "title":       title,
            "url":         link,
            "pub_date":    pub_date,
            "excerpt":     excerpt,
            "source_name": name,
            "category":    cat,
        })

        if len(items) >= max_n:
            break

    print(f"     ✓ 取得 {len(items)} 筆")
    return items

# ── 讀現有待審清單（去重複用）──────────────────────────────────────────────────

def get_existing_weekly_urls():
    """掃描 content/weekly/*.md，回傳所有 url 的 set（避免重複抓取）。"""
    urls = set()
    if not os.path.isdir(WEEKLY_DIR):
        return urls
    for fname in os.listdir(WEEKLY_DIR):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(WEEKLY_DIR, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                content = f.read()
            if not content.startswith("---"):
                continue
            end = content.index("\n---", 3)
            fm = yaml.safe_load(content[3:end]) or {}
            if fm.get("url"):
                urls.add(fm["url"])
        except Exception:
            pass
    return urls

# ── 寫入待審項目 ──────────────────────────────────────────────────────────────

def write_pending_item(item):
    """把一筆待審項目寫入 content/weekly/<date>_<id>.md（status: pending）。"""
    item_id   = short_id(item["url"])
    today     = datetime.now().strftime("%Y-%m-%d")
    fname     = f"{today}_{item_id}.md"
    fpath     = os.path.join(WEEKLY_DIR, fname)

    if os.path.exists(fpath):
        return

    fm = {
        "id":           item_id,
        "fetch_date":   today,
        "title":        item["title"],
        "url":          item["url"],
        "source_name":  item["source_name"],
        "category":     item["category"],
        "pub_date":     item["pub_date"],
        "auto_excerpt": item["excerpt"],
        "status":       "pending",
        "note":         "",
        "publish_week": "",
    }

    fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False,
                       sort_keys=False).strip()
    md_text = f"---\n{fm_str}\n---\n\n"

    with open(fpath, "w", encoding="utf-8") as f:
        f.write(md_text)

    print(f"   ✅ 新增待審：{fname}（{item['title'][:50]}）")

# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(WEEKLY_DIR, exist_ok=True)

    # 載入來源設定（YAML 優先，備援次之）
    sources = load_sources()

    # 取得現有 URL（去重複）
    existing_urls = get_existing_weekly_urls()
    print(f"📂 現有待審/已發布項目：{len(existing_urls)} 筆（用於去重複）\n")

    total_added = 0

    for source in sources:
        if not source.get("enabled", True):
            print(f"  ⏭️  {source.get('name', '')}（停用）")
            continue

        items = parse_rss(source)
        for item in items:
            if item["url"] in existing_urls:
                continue
            write_pending_item(item)
            existing_urls.add(item["url"])
            total_added += 1

    print(f"\n🎉 完成：共新增 {total_added} 筆待審項目到 content/weekly/")
    print("   → 玲玲在 PagesCMS 後台填入心情分享並改 status 為 published 後即可上線。")

if __name__ == "__main__":
    main()
