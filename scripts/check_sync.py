#!/usr/bin/env python3
"""
check_sync.py — 同步對帳：方格子（Vocus）的文章，網站是不是一篇不少、一篇不多。

2026-11-18 新增（規劃書階段 2「同步不能出錯」）。
每天 daily_sync 同步完會跑一次；本機也可以跑：
  cd vickymommy.github.io
  pip install requests pyyaml
  python scripts/check_sync.py

做什麼：
  1. 直接問方格子官方 API：7 個分類房間各有哪些文章（不依賴 sync_vocus.py 的結果，獨立查一次）
     另外讀方格子 /content 頁，抓「沒放進任何房間」或「放在新房間」的最新文章。
  2. 讀網站的 content/articles/*.md（標 _duplicate_of 的重複檔不算）。
  3. 比對：網站缺哪幾篇、多哪幾篇（＝方格子刪了或藏起來）、分類對不對、標題有沒有改。
  4. 讀 data/videos.json 看 YouTube 有沒有抓到。
  5. 結果寫進 data/sync_status.json（網站頁尾「最後同步」就讀這個檔）。
  6. 有問題時，把說明寫進 --report 指定的檔案，workflow 會用它開 GitHub Issue。

不會自動刪文章、不會改文章；只檢查、只回報。
"""
import argparse, json, os, re, sys, time
from datetime import datetime, timedelta, timezone

import requests
import yaml

# 房間清單、分類對照沿用 sync_vocus.py（只有一份，避免兩邊不一樣）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_vocus import ROOM_ID_TO_NAME, ROOM_CATEGORY_MAP, HEADERS, SALON_BASE_URL  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTICLES_DIR = os.path.join(BASE, "content", "articles")
STATUS_PATH = os.path.join(BASE, "data", "sync_status.json")
VIDEOS_PATH = os.path.join(BASE, "data", "videos.json")
TAIPEI = timezone(timedelta(hours=8))
API_NUM = 300  # 一次抓的上限；某房間接近這個數字時會提醒要改大


def fetch_vocus():
    """回傳 (articles, problems)。articles: {id: {"title", "rooms": [房間名]}}"""
    articles, problems = {}, []
    for room_id, room_name in ROOM_ID_TO_NAME.items():
        url = (f"https://api.vocus.cc/api/v2/site/rooms/{room_id}/contents"
               f"?num={API_NUM}&order=desc&page=1&roomId={room_id}&sort=publishAt&type=")
        data = None
        for attempt in range(3):
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:  # 網路不穩重試 3 次
                err = e
                time.sleep(3)
        if data is None:
            problems.append(f"方格子房間「{room_name}」查不到（{err}），這個分類今天沒辦法對帳")
            continue
        contents = data.get("contents", [])
        if len(contents) >= API_NUM:
            problems.append(f"方格子房間「{room_name}」超過 {API_NUM} 筆，請把 check_sync.py 和 sync_vocus.py 的 num 改大")
        for item in contents:
            art = item.get("article")
            if not art or not art.get("_id"):
                continue  # 不是文章（例如純貼文）
            a = articles.setdefault(art["_id"], {"title": art.get("title", ""), "rooms": []})
            if room_name not in a["rooms"]:
                a["rooms"].append(room_name)
        time.sleep(0.5)

    # /content 頁：抓沒放進這 7 個房間的最新文章（例如玲玲開了新房間）
    try:
        r = requests.get(f"{SALON_BASE_URL}/content", headers=HEADERS, timeout=20)
        r.raise_for_status()
        for aid in dict.fromkeys(re.findall(r"/article/([0-9a-f]{24})", r.text)):
            articles.setdefault(aid, {"title": "", "rooms": []})
    except Exception as e:
        problems.append(f"方格子 /content 頁查不到（{e}），沒放進房間的文章今天沒檢查到")
    return articles, problems


def read_site():
    """回傳 {id: {"title", "category", "file"}}（重複檔不算）"""
    site = {}
    for fname in sorted(os.listdir(ARTICLES_DIR)):
        if not fname.endswith(".md"):
            continue
        text = open(os.path.join(ARTICLES_DIR, fname), encoding="utf-8").read()
        if not text.startswith("---"):
            continue
        fm = yaml.safe_load(text[3:text.index("\n---", 3)]) or {}
        if fm.get("_duplicate_of"):
            continue
        src = str(fm.get("source", "")).rstrip("/")
        aid = src.split("/")[-1] if src.startswith("https://vocus.cc/article/") else fm.get("id", fname[:-3])
        site[aid] = {"title": str(fm.get("title", "")), "category": fm.get("category", ""), "file": fname}
    return site


def norm(s):
    return re.sub(r"\s+", "", s or "")


def check_youtube():
    try:
        v = json.load(open(VIDEOS_PATH, encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "errors": [f"讀不到 data/videos.json：{e}"]}
    lists = v.get("playlists", [])
    return {
        "ok": not v.get("errors"),
        "updated": v.get("updated", ""),
        "playlists": len(lists) if isinstance(lists, list) else 0,
        "errors": v.get("errors", []),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", help="有問題時把 Issue 內文寫到這個檔案")
    args = ap.parse_args()

    now = datetime.now(TAIPEI)
    vocus, problems = fetch_vocus()
    site = read_site()

    missing = [{"id": i, "title": a["title"], "url": f"https://vocus.cc/article/{i}"}
               for i, a in vocus.items() if i not in site]
    # 多出來的：只有在 7 個房間都查得到時才算，不然可能只是今天那個房間查不到
    rooms_ok = not any("房間" in p and "查不到" in p for p in problems)
    extra = ([{"id": i, "title": s["title"], "file": s["file"]} for i, s in site.items() if i not in vocus]
             if rooms_ok else [])
    wrong_cat, title_changed = [], []
    for i, a in vocus.items():
        if i not in site:
            continue
        cats = [ROOM_CATEGORY_MAP.get(r) for r in a["rooms"]]
        if cats and site[i]["category"] not in cats:
            wrong_cat.append({"id": i, "title": a["title"], "site": site[i]["category"],
                              "vocus": "／".join(a["rooms"])})
        if a["title"] and norm(a["title"]) != norm(site[i]["title"]):
            title_changed.append({"id": i, "vocus": a["title"], "site": site[i]["title"]})

    yt = check_youtube()
    ok = not (missing or extra or wrong_cat or problems)
    status = {
        "_說明": "由 scripts/check_sync.py 每天自動產生，請勿手動編輯。網站頁尾「最後同步」讀這個檔。",
        "checkedAt": now.isoformat(timespec="seconds"),
        "ok": ok and yt["ok"],
        "articles": {
            "ok": ok,
            "vocus": len(vocus),
            "site": len(site),
            "missing": missing,
            "extra": extra,
            "wrongCategory": wrong_cat,
            "titleChanged": title_changed,
            "problems": problems,
        },
        "youtube": yt,
    }
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    print(f"方格子 {len(vocus)} 篇、網站 {len(site)} 篇；缺 {len(missing)}、多 {len(extra)}、"
          f"分類不同 {len(wrong_cat)}、標題改過 {len(title_changed)}、其他問題 {len(problems)}；"
          f"YouTube {'正常' if yt['ok'] else '有問題'}")

    if args.report and not ok:
        lines = [f"{now:%Y-%m-%d %H:%M}（台北）對帳結果：方格子 {len(vocus)} 篇、網站 {len(site)} 篇。", ""]
        if missing:
            lines += ["### 網站缺的文章（方格子有、網站沒有）"] + \
                     [f"- [{m['title'] or m['id']}]({m['url']})" for m in missing] + \
                     ["", "通常隔天自動同步會補上；連續兩天都還在，請到 Actions 看 daily_sync 的紀錄。", ""]
        if extra:
            lines += ["### 網站多的文章（方格子上找不到，可能刪了或改成不公開）"] + \
                     [f"- {e['title']}（`content/articles/{e['file']}`）" for e in extra] + \
                     ["", "網站不會自動刪。確定不要了，就把那個檔案刪掉（或請 AI 幫忙）。", ""]
        if wrong_cat:
            lines += ["### 分類跟方格子不一樣"] + \
                     [f"- {w['title']}：網站 `{w['site']}`、方格子「{w['vocus']}」" for w in wrong_cat] + [""]
        if problems:
            lines += ["### 今天沒辦法完整對帳"] + [f"- {p}" for p in problems] + [""]
        lines += ["處理完可以直接關掉這個 Issue；問題還在的話，之後每天會在這裡留言。"]
        with open(args.report, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


if __name__ == "__main__":
    main()
