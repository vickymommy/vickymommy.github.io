#!/usr/bin/env python3
"""
update_vocus.py — 方格子文章「修改」也同步到網站（2026-11-18 新增，規劃書階段 2 尾巴）。

sync_vocus.py 只抓新文章、已存在的直接略過，所以玲玲在方格子改了內文，網站不會跟著改。
這支補上這一塊，每天在 daily_sync 裡 sync_vocus.py 後面跑：

  1. 問方格子官方 API（跟 sync_vocus 同一份房間清單），拿每篇的 lastPublishAt（方格子「更新發布」時會變）。
  2. 跟 data/vocus_versions.json 記的上次時間比：
     - 第一次看到這篇 → 只記下現在的時間和網站內文的指紋（hash），不動文章。
     - 時間沒變 → 不動。
     - 時間變了，而且網站上的內文跟上次同步時一樣（指紋相同）→ 重新抓這篇，更新內文、標籤、閱讀分鐘數。
       **保留**原本的檔名、標題、發布日期、分類、摘要、封面（玲玲在後台改過的設定不會被蓋掉）。
       圖片用新檔名下載（舊圖留著），避免玲玲換了圖片網站還顯示舊圖。
     - 時間變了，但網站上的內文被改過（指紋不同，例如玲玲在後台改了）→ **不蓋掉**，寫進 --report 檔，daily_sync 會開 Issue 請人決定。
  3. 寫回 data/vocus_versions.json（程式產生，不要手改）。

本機執行：
  pip install requests beautifulsoup4 pyyaml lxml pillow
  python scripts/update_vocus.py                 # 實際更新
  python scripts/update_vocus.py --dry-run       # 只列出會更新哪些，不寫檔
  python scripts/update_vocus.py --report /tmp/update_report.md

不會新增、刪除文章（新增是 sync_vocus.py 的事；方格子刪掉的文章由 check_sync.py 對帳通知）。
"""
import argparse, hashlib, json, os, sys, time
from datetime import datetime, timezone, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_vocus as sv  # 共用房間清單、抓文章、清廣告、下載圖片、frontmatter 讀寫（sync_vocus 已設定 UTF-8 輸出）

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(BASE, "data", "vocus_versions.json")
TPE = timezone(timedelta(hours=8))


def body_hash(body):
    return hashlib.md5(body.strip().encode("utf-8")).hexdigest()[:12]


def fetch_publish_times():
    """回傳 ({article_id: lastPublishAt}, 有沒有每個房間都抓成功)。"""
    out, all_ok = {}, True
    for room_id in sv.ROOM_IDS:
        url = (f"https://api.vocus.cc/api/v2/site/rooms/{room_id}/contents"
               f"?num=300&order=desc&page=1&roomId={room_id}&sort=publishAt&type=")
        data = None
        for attempt in range(3):
            try:
                r = requests.get(url, headers=sv.HEADERS, timeout=20)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:
                print(f"  ⚠️ 房間 {sv.ROOM_ID_TO_NAME.get(room_id, room_id)} 第 {attempt+1} 次失敗：{e}", file=sys.stderr)
                time.sleep(3)
        if data is None:
            all_ok = False
            continue
        for item in data.get("contents", []):
            art = item.get("article") or {}
            aid = art.get("_id") or item.get("contentId")
            if aid and art.get("lastPublishAt"):
                out[aid] = art["lastPublishAt"]
    return out, all_ok


def local_articles():
    """{article_id: (檔案路徑, frontmatter, body)}，用 source 網址認文章（8 碼舊檔名也對得到）。"""
    res = {}
    for fname in sorted(os.listdir(sv.ARTICLES_DIR)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(sv.ARTICLES_DIR, fname)
        with open(fpath, encoding="utf-8") as f:
            fm, body = sv.parse_frontmatter(f.read())
        if fm.get("_duplicate_of"):
            continue
        src = str(fm.get("source", ""))
        if src.startswith("https://vocus.cc/article/"):
            res[src.rstrip("/").split("/")[-1]] = (fpath, fm, body)
    return res


def refetch(aid, fpath, old_fm, stamp, build_id):
    art = sv.fetch_article_data(build_id, aid)
    if not art or not art.get("content"):
        return None, "抓不到方格子文章內容"
    clean = sv.clean_vocus_content(art.get("content", ""))
    # 圖片用新前綴，避免同一個位置換了圖還沿用舊檔
    body, n_img = sv.process_images(clean, f"{aid}_r{stamp}")
    tags = [t.get("name", "") for t in (art.get("tags") or []) if t.get("name")]
    fm = dict(old_fm)
    # 標題保留網站原本的（68 篇網站標題是當初刻意縮短或改標點，不要被方格子版本蓋回去）
    if tags:
        fm["tags"] = tags
    fm["readMin"] = sv.estimate_read_min(body)
    fm["sync_hash"] = sv.content_hash(body)
    with open(fpath, "w", encoding="utf-8", newline="\n") as f:
        f.write(sv.dump_frontmatter(fm, body))
    return body, f"已更新（圖片 {n_img} 張）"


def main():
    ap = argparse.ArgumentParser(description="方格子文章修改同步到網站")
    ap.add_argument("--dry-run", action="store_true", help="只列出，不寫檔")
    ap.add_argument("--report", help="有「網站也改過、沒自動更新」的文章時，把 Issue 內文寫到這個檔")
    args = ap.parse_args()

    state = {}
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            state = json.load(f).get("articles", {})

    times, all_ok = fetch_publish_times()
    if not times:
        print("⚠️ 方格子一篇都抓不到，這次不更新（交給 check_sync.py 對帳通知）", file=sys.stderr)
        return
    local = local_articles()

    baseline = updated = unchanged = 0
    conflicts, failed = [], []
    build_id = None
    stamp = datetime.now(TPE).strftime("%Y%m%d")

    for aid, (fpath, fm, body) in local.items():
        pub = times.get(aid)
        if pub is None:
            continue  # 方格子這次沒列到（房間抓失敗或已下架），保留原本紀錄
        h = body_hash(body)
        rec = state.get(aid)
        fname = os.path.basename(fpath)
        if rec is None:
            state[aid] = {"file": fname, "lastPublishAt": pub, "bodyHash": h}
            baseline += 1
            continue
        if rec.get("lastPublishAt") == pub:
            unchanged += 1
            continue
        title = fm.get("title", "")
        if rec.get("bodyHash") != h:
            conflicts.append((aid, fname, title))
            if not args.dry_run:
                # 記下這次的發布時間，同一次修改只通知一次（不會天天開 Issue）；
                # bodyHash 改成網站現在的內文，之後方格子再改、網站沒再動，就會正常自動更新
                state[aid] = {"file": fname, "lastPublishAt": pub, "bodyHash": h}
            continue
        if args.dry_run:
            print(f"  （dry-run）會更新：{fname}｜{title}")
            updated += 1
            continue
        if build_id is None:
            build_id = sv.get_build_id()
        new_body, msg = refetch(aid, fpath, fm, stamp, build_id)
        if new_body is None:
            failed.append((aid, fname, title, msg))
            continue
        state[aid] = {"file": fname, "lastPublishAt": pub, "bodyHash": body_hash(new_body)}
        print(f"  ✅ {fname}｜{title}：{msg}")
        updated += 1

    if not args.dry_run:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        with open(STATE, "w", encoding="utf-8", newline="\n") as f:
            json.dump({
                "_說明": "由 scripts/update_vocus.py 產生，請勿手動編輯。每篇方格子文章上次同步時的 lastPublishAt 與網站內文指紋。",
                "updatedAt": datetime.now(TPE).isoformat(timespec="seconds"),
                "articles": dict(sorted(state.items())),
            }, f, ensure_ascii=False, indent=1)

    print(f"修改同步：更新 {updated} 篇、沒變 {unchanged} 篇、第一次記錄 {baseline} 篇、"
          f"網站也改過沒動 {len(conflicts)} 篇、失敗 {len(failed)} 篇"
          + ("" if all_ok else "（有房間抓失敗，那些文章這次沒檢查）"))

    if args.report and (conflicts or failed):
        lines = ["方格子上有文章「更新發布」了，但下面這些**網站沒有自動更新**：", ""]
        if conflicts:
            lines += ["### 網站上的內文也被改過（為了不蓋掉，先不動）", ""]
            lines += [f"- {t}（`content/articles/{fn}`，方格子 https://vocus.cc/article/{a} ）" for a, fn, t in conflicts]
            lines += ["", "- 要保留網站上的版本：什麼都不用做，關掉這張 Issue。",
                      "- 要改成方格子的版本：請 AI 照 AGENTS.md 第 4 節「整篇重抓」處理這幾篇。",
                      "- 這次的修改只會通知一次；之後方格子再改、網站沒再動，就會自動更新。", ""]
        if failed:
            lines += ["### 抓取失敗（明天會再試）", ""]
            lines += [f"- {t}（`{fn}`）：{m}" for a, fn, t, m in failed]
        with open(args.report, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    # 這支出錯不要擋住每日同步（新文章、YouTube、對帳照常跑）；把錯誤寫進報告，daily_sync 會開 Issue
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        rep = None
        if "--report" in sys.argv:
            i = sys.argv.index("--report")
            rep = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
        if rep:
            with open(rep, "w", encoding="utf-8") as f:
                f.write(f"修改同步程式 `scripts/update_vocus.py` 執行出錯，這次沒有檢查方格子的修改（新文章同步不受影響）：\n\n```\n{type(e).__name__}: {e}\n```\n\n請把這張 Issue 貼給 AI 查原因。\n")
