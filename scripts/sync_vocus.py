#!/usr/bin/env python3
"""
sync_vocus.py — 每日自動從 Vocus RSS 同步玲玲的新文章到 content/articles/

執行方式（GitHub Action 或本機）：
  cd 網站專案
  pip install requests beautifulsoup4 pyyaml
  python scripts/sync_vocus.py

功能：
  1. 抓 Vocus RSS → 找出新文章
  2. 對每篇新文章：fetch 完整頁面、抽取內文、下載圖片、產生 .md 檔
  3. 對已存在的文章：比對內容 hash，若有修改則更新
  4. source 欄位有 Vocus URL 的才是本腳本管的（後台直接新增的不動）
"""

import os, re, time, hashlib, json, sys
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

try:
    import yaml
except ImportError:
    print("缺少 pyyaml，執行 pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── 設定 ─────────────────────────────────────────────────────────────────────

RSS_URL = "https://vocus.cc/salon/651fb341fd897800018f38ed/rss"

# 路徑（相對於本腳本的上一層，即 網站專案/）
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTICLES_DIR = os.path.join(BASE, "content", "articles")
IMAGES_DIR   = os.path.join(BASE, "assets", "images")

# 請求 headers（模擬正常瀏覽器，避免被 Vocus CDN 封鎖）
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

# 分類關鍵字對應（從標題+標籤推測）
CATEGORY_KEYWORDS = {
    "ai":       ["AI", "人工智慧", "ChatGPT", "機器學習", "AIGC", "Midjourney",
                 "Claude", "Stable Diffusion", "生成式", "copilot", "Gemini",
                 "提示詞", "prompt", "自動化"],
    "travel":   ["旅遊", "旅行", "親子遊", "景點", "出遊", "出發", "旅"],
    "diy":      ["手作", "DIY", "自製", "料理", "食譜", "烘焙", "做法", "材料"],
    "growth":   ["成長", "學習", "自我", "進修", "斜槓", "副業", "讀書", "閱讀",
                 "心態", "覆盤", "目標", "習慣"],
    "parenting":["育兒", "親子", "孩子", "教育", "小孩", "幼稚園", "小學",
                 "媽媽", "爸爸", "寶寶"],
}

# ── 工具函式 ──────────────────────────────────────────────────────────────────

def parse_frontmatter(text):
    """解析 YAML frontmatter，回傳 (dict, body_str)。"""
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
    """把 frontmatter dict + body 組合成 .md 文字。"""
    # 用 allow_unicode 確保中文正確輸出
    fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False,
                       sort_keys=False).strip()
    return f"---\n{fm_str}\n---\n\n{body}"

def guess_category(title, tags):
    """從標題與標籤猜分類，猜不到預設 parenting。"""
    text = (title or "") + " " + " ".join(tags or [])
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text.lower():
                return cat
    return "parenting"

def estimate_read_min(html_body):
    """從 HTML 內文估算閱讀分鐘數（平均每分鐘 200 中文字）。"""
    text = re.sub(r"<[^>]+>", "", html_body)
    chars = len(text.strip())
    return max(1, round(chars / 200))

def make_excerpt(html_body, max_len=120):
    """從 HTML 內文取前 max_len 字作摘要。"""
    text = re.sub(r"<[^>]+>", " ", html_body)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] + ("…" if len(text) > max_len else "")

def content_hash(html_body):
    """計算 HTML 內文的 MD5 hash，用於修改偵測。"""
    return hashlib.md5(html_body.encode("utf-8")).hexdigest()[:12]

# ── RSS 解析 ──────────────────────────────────────────────────────────────────

def fetch_rss():
    """抓 Vocus RSS，回傳 list of dict（每篇文章的 metadata）。"""
    print(f"📡 抓取 RSS：{RSS_URL}")
    try:
        resp = requests.get(RSS_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ 抓 RSS 失敗：{e}", file=sys.stderr)
        return []

    # 解析 XML（處理 namespace）
    content = resp.content
    # 移除 namespace 宣告讓解析更簡單
    content = re.sub(rb'xmlns[^=]*="[^"]*"', b'', content)
    content = re.sub(rb'<([a-zA-Z]+):[a-zA-Z]+', b'<\\1_ns_', content)

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"❌ RSS 解析失敗：{e}", file=sys.stderr)
        return []

    items = []
    for item in root.iter("item"):
        def gt(tag):
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else ""

        link = gt("link")
        if not link:
            continue

        # 從 URL 取文章 ID（最後一段路徑）
        article_id = urlparse(link).path.rstrip("/").split("/")[-1]
        if not article_id:
            continue

        # 發布日期
        pub_str = gt("pubDate")
        try:
            pub_dt = datetime.strptime(pub_str, "%a, %d %b %Y %H:%M:%S %z")
            date_str = pub_dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = datetime.now().strftime("%Y-%m-%d")

        # 縮圖（可能在 enclosure 或 description 裡）
        cover_url = ""
        enc = item.find("enclosure")
        if enc is not None:
            cover_url = enc.get("url", "")

        # RSS 描述（可作 excerpt 備用）
        rss_desc = gt("description")
        if rss_desc:
            rss_desc = re.sub(r"<[^>]+>", "", rss_desc).strip()[:200]

        items.append({
            "id":         article_id,
            "title":      gt("title"),
            "source":     link,
            "date":       date_str,
            "cover_url":  cover_url,
            "rss_excerpt": rss_desc,
        })

    print(f"✓ RSS 共 {len(items)} 筆")
    return items

# ── 取得現有文章 ──────────────────────────────────────────────────────────────

def get_existing_vocus_articles():
    """
    掃描 content/articles/*.md，回傳以 source URL 為 key 的 dict。
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
            result[src] = {
                "filepath": fpath,
                "fm": fm,
                "body": body,
                "sync_hash": fm.get("sync_hash", ""),
            }
    return result

# ── 圖片下載 ──────────────────────────────────────────────────────────────────

def download_image(url, article_id, img_idx, is_cover=False):
    """
    下載圖片到 assets/images/<article_id>_<nn>.<ext>
    回傳本地路徑字串（相對於網站根目錄），失敗回傳 None。
    """
    if not url or url.startswith("data:"):
        return None

    # 處理相對 URL
    if url.startswith("//"):
        url = "https:" + url

    # 取副檔名
    path_part = urlparse(url).path
    ext = os.path.splitext(path_part)[1].lower()
    # 常見圖片副檔名；若無或不認識，預設 .jpg
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"

    if is_cover:
        fname = f"{article_id}_cover{ext}"
    else:
        fname = f"{article_id}_{img_idx:03d}{ext}"

    local_path = os.path.join(IMAGES_DIR, fname)
    rel_path   = f"assets/images/{fname}"

    # 已下載過就跳過
    if os.path.exists(local_path):
        return rel_path

    try:
        time.sleep(0.5)  # 每張圖片之間稍作延遲，避免被封鎖
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(resp.content)
        print(f"   📷 下載圖片：{fname}")
        return rel_path
    except Exception as e:
        print(f"   ⚠️ 圖片下載失敗（{url}）：{e}", file=sys.stderr)
        return None

# ── 文章頁面抓取 ──────────────────────────────────────────────────────────────

def fetch_article_page(url):
    """
    抓取 Vocus 文章頁面，回傳 BeautifulSoup 物件。
    失敗回傳 None。
    """
    try:
        time.sleep(1)  # 禮貌性延遲
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"   ⚠️ 抓取文章頁面失敗（{url}）：{e}", file=sys.stderr)
        return None

def extract_cover_from_page(soup):
    """
    從頁面的 og:image meta 取封面圖 URL。
    """
    og = soup.find("meta", property="og:image")
    if og:
        return og.get("content", "")
    # 備用：找第一張 img
    img = soup.find("img")
    if img:
        return img.get("src", "")
    return ""

def extract_tags_from_page(soup):
    """
    從頁面找標籤（Vocus 通常放在 <meta name="keywords">）。
    """
    kw = soup.find("meta", attrs={"name": "keywords"})
    if kw:
        content = kw.get("content", "")
        return [t.strip() for t in content.split(",") if t.strip()]
    return []

def extract_article_body(soup, article_id):
    """
    從 Vocus 文章頁面提取 HTML 內文，並把圖片下載為本地檔案。
    回傳 (clean_html, cover_local_path, img_count)。

    Vocus 頁面的內文可能在不同的 CSS class 下，嘗試多個選擇器。
    """
    # 嘗試多個可能的內文容器（Vocus 可能改版，優先順序由高到低）
    selectors = [
        {"name": "div", "class_": re.compile(r"draft-editor-content|article-content|content__body|essay-content")},
        {"name": "article"},
        {"name": "div", "attrs": {"data-block": "true"}},
    ]

    content_div = None
    for sel in selectors:
        if "class_" in sel:
            content_div = soup.find(sel["name"], class_=sel["class_"])
        elif "attrs" in sel:
            content_div = soup.find(sel["name"], sel["attrs"])
        else:
            content_div = soup.find(sel["name"])
        if content_div:
            break

    if not content_div:
        # 最後備用：取 <main> 或 <body> 裡最長的 <div>
        main = soup.find("main") or soup.find("body")
        if main:
            divs = main.find_all("div", recursive=False)
            if divs:
                content_div = max(divs, key=lambda d: len(d.get_text()))

    if not content_div:
        return "", "", 0

    # ── 清理不需要的元素 ────────────────────────────────────────────
    for tag in content_div.find_all(["script", "style", "noscript",
                                      "nav", "header", "footer",
                                      "aside", "form", "button"]):
        tag.decompose()

    # 移除廣告、評論計數器等動態元素（常見 class 關鍵字）
    noise_classes = re.compile(
        r"advert|sponsor|comment|counter|like|share|follow|subscribe|"
        r"recommend|related|sidebar|modal|overlay|cookie|banner",
        re.IGNORECASE
    )
    for tag in content_div.find_all(class_=noise_classes):
        tag.decompose()

    # ── 圖片下載並替換路徑 ──────────────────────────────────────────
    img_count = 0
    for img in content_div.find_all("img"):
        src = img.get("src", "") or img.get("data-src", "")
        if not src:
            img.decompose()
            continue
        img_count += 1
        local = download_image(src, article_id, img_count)
        if local:
            img["src"] = local
            # 移除 srcset, data-src 等屬性
            for attr in ["srcset", "data-src", "data-srcset"]:
                if img.has_attr(attr):
                    del img[attr]
        else:
            img.decompose()  # 下載失敗就移除

    # ── 外部連結加 target="_blank" rel="noopener" ────────────────────
    for a in content_div.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http"):
            a["target"] = "_blank"
            a["rel"] = "noopener"

    # 取出最終 HTML
    body_html = content_div.decode_contents().strip()

    # 取封面圖（og:image 優先）
    cover_url = extract_cover_from_page(soup)
    cover_local = ""
    if cover_url:
        cover_local = download_image(cover_url, article_id, 0, is_cover=True) or ""

    return body_html, cover_local, img_count

# ── 建立 .md 檔 ───────────────────────────────────────────────────────────────

def create_article_md(rss_item, body_html, cover_local, tags, is_update=False):
    """
    從 RSS metadata + 抓取的 body 產生（或更新）content/articles/<id>.md。
    """
    article_id = rss_item["id"]
    fpath = os.path.join(ARTICLES_DIR, f"{article_id}.md")

    # 如果是更新，保留既有 frontmatter 中不應覆蓋的欄位
    existing_fm = {}
    if is_update and os.path.exists(fpath):
        try:
            with open(fpath, encoding="utf-8") as f:
                existing_fm, _ = parse_frontmatter(f.read())
        except Exception:
            pass

    category = existing_fm.get("category") or guess_category(
        rss_item["title"],
        tags
    )
    excerpt = existing_fm.get("excerpt") or make_excerpt(body_html)

    fm = {
        "id":         article_id,
        "title":      rss_item["title"],
        "date":       rss_item["date"],
        "category":   category,
        "cover":      cover_local or existing_fm.get("cover", ""),
        "excerpt":    excerpt,
        "tags":       tags or existing_fm.get("tags", []),
        "source":     rss_item["source"],
        "readMin":    estimate_read_min(body_html),
        "sync_hash":  content_hash(body_html),
    }

    md_text = dump_frontmatter(fm, body_html)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(md_text)

    action = "更新" if is_update else "新增"
    print(f"  ✅ {action} {article_id}.md（{rss_item['title'][:40]}）")

# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR,   exist_ok=True)

    # 1. 抓 RSS
    rss_items = fetch_rss()
    if not rss_items:
        print("RSS 無內容，結束。")
        return

    # 2. 讀現有 Vocus 文章（用 source URL 索引）
    existing = get_existing_vocus_articles()
    print(f"📂 現有 Vocus 文章：{len(existing)} 篇")

    added = 0
    updated = 0
    skipped = 0

    for rss_item in rss_items:
        source_url = rss_item["source"]
        article_id = rss_item["id"]
        print(f"\n── 處理：{article_id} ──")

        # 3. 抓完整頁面
        soup = fetch_article_page(source_url)
        if not soup:
            print(f"   ⚠️ 無法取得頁面，略過")
            skipped += 1
            continue

        body_html, cover_local, img_count = extract_article_body(soup, article_id)
        if not body_html:
            # 用 RSS description 作備用
            body_html = f"<p>{rss_item['rss_excerpt']}</p>" if rss_item["rss_excerpt"] else ""
            print(f"   ⚠️ 無法提取內文，使用 RSS 描述作備用")

        tags = extract_tags_from_page(soup)

        # 4. 判斷：新文章 or 有修改
        if source_url not in existing:
            # 全新文章
            create_article_md(rss_item, body_html, cover_local, tags, is_update=False)
            added += 1
        else:
            # 已存在：比對 hash
            old_hash = existing[source_url]["sync_hash"]
            new_hash = content_hash(body_html)
            if old_hash != new_hash:
                create_article_md(rss_item, body_html, cover_local, tags, is_update=True)
                updated += 1
            else:
                print(f"  — 無修改，略過")
                skipped += 1

    print(f"\n🎉 完成：新增 {added}、更新 {updated}、略過 {skipped}")

if __name__ == "__main__":
    main()
