#!/usr/bin/env python3
"""
sync_vocus.py — 每日自動從 Vocus 沙龍同步玲玲的新文章到 content/articles/

【2025 更新】Vocus 已移除 RSS；改用 Next.js 頁面資料抓取。
策略：
  1. 抓主頁 → 取得 buildId（隨 Vocus 部署變動，每次需動態取得）
  2. 抓各分類房間頁 HTML → 收集文章 ID
  3. 比對已有 .md 檔 → 只處理新文章或有修改的文章
  4. 透過 /_next/data/{buildId}/zh-Hant/article/{id}.json 抓完整文章資料
  5. 清理廣告、下載圖片、產生 .md 檔

執行方式（GitHub Action 或本機）：
  cd vickymommy.github.io
  pip install requests beautifulsoup4 pyyaml lxml
  python scripts/sync_vocus.py
"""

import os, re, time, hashlib, json, sys
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    import yaml
except ImportError:
    print("缺少 pyyaml，執行 pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── 設定 ─────────────────────────────────────────────────────────────────────

SALON_ID       = "651fb341fd897800018f38ed"
SALON_BASE_URL = f"https://vocus.cc/salon/{SALON_ID}"

# 各分類房間 ID（房間新增/刪除時需更新此清單）
ROOM_IDS = [
    "67886c95fd89780001d67de3",   # AI 學習應用
    "6442523ffd89780001ddccdc",   # 媽媽自我成長
    "64424703fd89780001726386",   # 親子生活實用指南
    "64546dfdfd89780001b97f76",   # 親子旅遊
    "64425438fd89780001ddefce",   # 親子手作時間
]

# 房間 ID → 房間名稱（靜態對應，避免從 HTML 解析到錯誤標題）
ROOM_ID_TO_NAME = {
    "67886c95fd89780001d67de3": "AI 學習應用",
    "6442523ffd89780001ddccdc": "媽媽自我成長",
    "64424703fd89780001726386": "親子生活實用指南",
    "64546dfdfd89780001b97f76": "親子旅遊",
    "64425438fd89780001ddefce": "親子手作時間",
}

# 房間名稱 → 網站分類對照
ROOM_CATEGORY_MAP = {
    "AI 學習應用":    "ai",
    "媽媽自我成長":    "growth",
    "親子生活實用指南": "parenting",
    "親子旅遊":       "travel",
    "親子手作時間":    "diy",
}

# 分類關鍵字備援（房間資訊取不到時用標題/標籤推測）
CATEGORY_KEYWORDS = {
    "ai":       ["AI", "人工智慧", "ChatGPT", "機器學習", "生成式", "Copilot",
                 "Gemini", "Claude", "提示詞", "prompt", "iPAS", "自動化"],
    "travel":   ["旅遊", "旅行", "親子遊", "景點", "出遊", "旅"],
    "diy":      ["手作", "DIY", "自製", "料理", "食譜", "烘焙"],
    "growth":   ["成長", "學習", "自我", "進修", "斜槓", "閱讀", "心態", "習慣"],
    "parenting":["育兒", "親子", "孩子", "教育", "小孩", "媽媽", "爸爸", "寶寶"],
}

# 路徑設定（相對於腳本上一層，即網站根目錄）
BASE         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTICLES_DIR = os.path.join(BASE, "content", "articles")
IMAGES_DIR   = os.path.join(BASE, "assets", "images")

# 請求 headers
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

# ── 工具函式 ──────────────────────────────────────────────────────────────────

def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    try:
        end = text.index("\n---", 3)
    except ValueError:
        return {}, text
    fm = yaml.safe_load(text[3:end]) or {}
    body = text[end + 4:].strip()
    return fm, body

def dump_frontmatter(fm, body):
    fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False,
                       sort_keys=False).strip()
    return f"---\n{fm_str}\n---\n\n{body}"

def guess_category(title, tags, room_name=None):
    if room_name and room_name in ROOM_CATEGORY_MAP:
        return ROOM_CATEGORY_MAP[room_name]
    text = (title or "") + " " + " ".join(tags or [])
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text.lower():
                return cat
    return "parenting"

def estimate_read_min(html_body):
    text = re.sub(r"<[^>]+>", "", html_body)
    chars = len(text.strip())
    return max(1, round(chars / 200))

def make_excerpt(html_body, max_len=120):
    text = re.sub(r"<[^>]+>", " ", html_body)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] + ("…" if len(text) > max_len else "")

def content_hash(html_body):
    return hashlib.md5(html_body.encode("utf-8")).hexdigest()[:12]

# ── 動態取得 buildId ──────────────────────────────────────────────────────────

def get_build_id():
    """
    每次 Vocus 部署後 buildId 會變動，必須動態從主頁取得。
    """
    print(f"📡 取得 Vocus buildId...")
    try:
        resp = requests.get(SALON_BASE_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        m = re.search(r'"buildId"\s*:\s*"([^"]+)"', resp.text)
        if not m:
            raise RuntimeError("找不到 buildId")
        build_id = m.group(1)
        print(f"✓ buildId: {build_id}")
        return build_id
    except Exception as e:
        print(f"❌ 取得 buildId 失敗：{e}", file=sys.stderr)
        sys.exit(1)

# ── 收集文章 ID ───────────────────────────────────────────────────────────────

def collect_article_ids():
    """
    從各房間頁面 HTML 收集文章 ID（HTML 包含該房間所有文章的 SSR 資料）。
    同時抓 /content 主頁補足未分類文章。
    回傳：{article_id: room_name_or_None}
    """
    article_map = {}   # article_id → room_name

    print(f"\n📂 收集文章清單（共 {len(ROOM_IDS)} 個分類房間）")

    # 各房間頁
    for room_id in ROOM_IDS:
        url = f"{SALON_BASE_URL}/room/{room_id}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"  ⚠️ 無法抓房間頁 {room_id}：{e}", file=sys.stderr)
            continue

        # 房間名稱從靜態對照表取得（避免從 HTML 解析到文章標題）
        room_name = ROOM_ID_TO_NAME.get(room_id)

        ids = list(dict.fromkeys(re.findall(r'/article/([0-9a-f]{24})', resp.text)))
        for aid in ids:
            if aid not in article_map:
                article_map[aid] = room_name

        print(f"  房間 {room_id[:8]}...：{len(ids)} 篇")
        time.sleep(0.5)

    # /content 頁面補足未分類文章
    try:
        resp = requests.get(f"{SALON_BASE_URL}/content", headers=HEADERS, timeout=20)
        resp.raise_for_status()
        ids = list(dict.fromkeys(re.findall(r'/article/([0-9a-f]{24})', resp.text)))
        new_count = 0
        for aid in ids:
            if aid not in article_map:
                article_map[aid] = None
                new_count += 1
        if new_count:
            print(f"  /content 頁補入 {new_count} 篇未分類文章")
    except Exception as e:
        print(f"  ⚠️ /content 頁取失敗（略過）：{e}", file=sys.stderr)

    print(f"✓ 共發現 {len(article_map)} 篇文章")
    return article_map

# ── 讀取現有 Vocus 文章 ───────────────────────────────────────────────────────

def get_existing_vocus_articles():
    """
    掃描 content/articles/*.md，回傳以 article_id 為 key 的 dict。
    只收錄 source 以 https://vocus.cc/ 開頭的（Vocus 文章）。
    """
    result = {}
    if not os.path.isdir(ARTICLES_DIR):
        return result
    for fname in os.listdir(ARTICLES_DIR):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(ARTICLES_DIR, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                fm, body = parse_frontmatter(f.read())
        except Exception:
            continue
        src = fm.get("source", "")
        if src.startswith("https://vocus.cc/"):
            # 優先從 source URL 取完整 24 碼 article_id（相容舊式 8 碼短 ID 檔）
            if src.startswith("https://vocus.cc/article/"):
                aid = src.rstrip("/").split("/")[-1]
            else:
                aid = fm.get("id", fname.replace(".md", ""))
            result[aid] = {
                "filepath":  fpath,
                "fm":        fm,
                "body":      body,
                "sync_hash": fm.get("sync_hash", ""),
            }
    return result

# ── 抓取文章資料 ──────────────────────────────────────────────────────────────

def fetch_article_data(build_id, article_id):
    """
    透過 Next.js data endpoint 取得完整文章資料。
    回傳 parsedArticle dict，失敗回傳 None。
    """
    url = (f"https://vocus.cc/_next/data/{build_id}"
           f"/zh-Hant/article/{article_id}.json")
    try:
        time.sleep(1)
        resp = requests.get(url, headers={**HEADERS, "Accept": "application/json"},
                            timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("pageProps", {}).get("parsedArticle")
    except Exception as e:
        print(f"  ⚠️ 抓取文章資料失敗（{article_id}）：{e}", file=sys.stderr)
        return None

# ── 內文清理 ──────────────────────────────────────────────────────────────────

# 廣告相關 HTML 清理模式
AD_DIV_PATTERNS = [
    re.compile(r'<div[^>]*class="why-see-ad-placeholder"[^>]*>.*?</div>', re.DOTALL),
    re.compile(r'<div[^>]*translate="no"[^>]*style="[^"]*height:\s*300px[^"]*"[^>]*>.*?</div>', re.DOTALL),
    re.compile(r'<div[^>]*id="vocus_[^"]*"[^>]*>.*?</div>', re.DOTALL),
    re.compile(r'<div[^>]*class="[^"]*ad[^"]*"[^>]*>.*?</div>', re.DOTALL | re.IGNORECASE),
]

def clean_vocus_content(html):
    """
    移除 Vocus 廣告佔位符和不需要的元素。
    用 BeautifulSoup 做主要清理，regex 做補充。
    """
    # BeautifulSoup 清理
    soup = BeautifulSoup(html, "lxml")

    # 移除廣告相關元素
    for el in soup.find_all(class_=re.compile(r'why-see-ad|ad-placeholder', re.I)):
        el.decompose()
    for el in soup.find_all(id=re.compile(r'vocus_', re.I)):
        el.decompose()
    # 移除 height:300px 的 div（通常是廣告容器）
    for el in soup.find_all("div", style=re.compile(r'height:\s*300px', re.I)):
        el.decompose()
    # 移除 translate="no" 的廣告 div
    for el in soup.find_all("div", attrs={"translate": "no"}):
        if el.find(id=re.compile(r'vocus_')):
            el.decompose()
    # 移除 script, style, noscript
    for el in soup.find_all(["script", "style", "noscript"]):
        el.decompose()

    # 外部連結加 target="_blank"
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("http"):
            a["target"] = "_blank"
            a["rel"] = "noopener"

    result = str(soup)
    # 移除 lxml 加的 <html><body> 包裝
    result = re.sub(r'^<html><body>|</body></html>$', '', result.strip())
    return result.strip()

# ── 圖片下載 ──────────────────────────────────────────────────────────────────

def download_image(url, article_id, img_idx, is_cover=False):
    if not url or url.startswith("data:"):
        return None
    if url.startswith("//"):
        url = "https:" + url

    path_part = urlparse(url).path
    ext = os.path.splitext(path_part)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"

    fname = (f"{article_id}_cover{ext}" if is_cover
             else f"{article_id}_{img_idx:03d}{ext}")
    local_path = os.path.join(IMAGES_DIR, fname)
    rel_path   = f"assets/images/{fname}"

    if os.path.exists(local_path):
        return rel_path

    try:
        time.sleep(0.5)
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(resp.content)
        print(f"   📷 下載圖片：{fname}")
        return rel_path
    except Exception as e:
        print(f"   ⚠️ 圖片下載失敗（{url[:60]}）：{e}", file=sys.stderr)
        return None

def process_images(html, article_id):
    """
    從 HTML 中找出所有 img，下載圖片並替換為本地路徑。
    回傳 (updated_html, img_count)。
    """
    soup = BeautifulSoup(html, "lxml")
    img_count = 0
    for img in soup.find_all("img"):
        src = img.get("src", "") or img.get("data-src", "")
        if not src or src.startswith("data:"):
            img.decompose()
            continue
        img_count += 1
        local = download_image(src, article_id, img_count)
        if local:
            img["src"] = local
            for attr in ["srcset", "data-src", "data-srcset", "loading"]:
                img.attrs.pop(attr, None)
        else:
            img.decompose()

    result = str(soup)
    result = re.sub(r'^<html><body>|</body></html>$', '', result.strip())
    return result.strip(), img_count

# ── 產生 .md 檔 ───────────────────────────────────────────────────────────────

def create_or_update_article(article_id, art_data, room_name, is_update=False):
    """
    從 parsedArticle JSON + room_name 產生/更新 content/articles/<id>.md。
    """
    fpath = os.path.join(ARTICLES_DIR, f"{article_id}.md")

    # 取得原始內文並清理
    raw_html = art_data.get("content", "")
    clean_html = clean_vocus_content(raw_html)
    body_html, img_count = process_images(clean_html, article_id)

    # 封面圖
    cover_url = art_data.get("thumbnailUrl", "")
    cover_local = ""
    if cover_url:
        cover_local = download_image(cover_url, article_id, 0, is_cover=True) or ""

    # 標籤
    tags = [t.get("name", "") for t in (art_data.get("tags") or []) if t.get("name")]

    # 發布日期
    pub_raw = art_data.get("lastPublishAt", "") or art_data.get("createdAt", "")
    try:
        date_str = pub_raw[:10]  # "YYYY-MM-DD"
    except Exception:
        date_str = datetime.now().strftime("%Y-%m-%d")

    # 分類
    existing_fm = {}
    if is_update and os.path.exists(fpath):
        try:
            with open(fpath, encoding="utf-8") as f:
                existing_fm, _ = parse_frontmatter(f.read())
        except Exception:
            pass

    category = existing_fm.get("category") or guess_category(
        art_data.get("title", ""), tags, room_name
    )
    excerpt = existing_fm.get("excerpt") or art_data.get("abstract", "") or make_excerpt(body_html)
    if len(excerpt) > 150:
        excerpt = excerpt[:150] + "…"

    source_url = f"https://vocus.cc/article/{article_id}"

    fm = {
        "id":        article_id,
        "title":     art_data.get("title", ""),
        "date":      date_str,
        "category":  category,
        "cover":     cover_local or existing_fm.get("cover", ""),
        "excerpt":   excerpt,
        "tags":      tags or existing_fm.get("tags", []),
        "source":    source_url,
        "readMin":   estimate_read_min(body_html),
        "sync_hash": content_hash(body_html),
    }

    md_text = dump_frontmatter(fm, body_html)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(md_text)

    action = "更新" if is_update else "新增"
    title_short = art_data.get("title", "")[:40]
    print(f"  ✅ {action} {article_id}.md（{title_short}）img={img_count}")

# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR,   exist_ok=True)

    # 1. 取 buildId
    build_id = get_build_id()

    # 2. 收集所有文章 ID
    article_map = collect_article_ids()
    if not article_map:
        print("找不到任何文章，結束。")
        return

    # 3. 讀現有 Vocus 文章
    existing = get_existing_vocus_articles()
    print(f"\n📂 現有 Vocus 文章：{len(existing)} 篇")

    added = updated = skipped = errors = 0

    for article_id, room_name in article_map.items():
        source_url = f"https://vocus.cc/article/{article_id}"

        # 判斷是否已存在且有 hash
        is_existing = article_id in existing

        # 新文章：直接抓
        # 已存在文章：也要抓以比對 hash（若已有 sync_hash 才能比對）
        # 優化：若已存在且不是今天新的，可視情況略過
        # 這裡保守做法：所有文章都抓一次（可加速優化：先跳過超過 N 天的）

        if is_existing:
            # 若上次 sync_hash 存在，先不抓（節省 API 呼叫）
            # 實際比對需抓完整資料，可依需求開啟
            # 這裡採「新文章優先，已存在略過」以節省時間
            skipped += 1
            continue

        # 抓完整文章資料
        print(f"\n── 抓取新文章：{article_id} ──")
        art_data = fetch_article_data(build_id, article_id)
        if not art_data:
            print(f"  ⚠️ 無法取得資料，略過")
            errors += 1
            continue

        try:
            create_or_update_article(article_id, art_data, room_name, is_update=False)
            added += 1
        except Exception as e:
            print(f"  ❌ 寫入失敗：{e}")
            errors += 1

    print(f"\n{'='*60}")
    print(f"✅ 同步完成")
    print(f"   新增：{added} 篇  更新：{updated} 篇  略過：{skipped} 篇  錯誤：{errors} 篇")
    print(f"   文章存放於 content/articles/")

if __name__ == "__main__":
    main()
