# AGENTS.md — Vicky Mommy 網站維護說明（給任何 AI 看）

> 這份是「網站現在怎麼運作」的正本。不管你是 ChatGPT／Codex、Claude 或其他 AI，動手改這個 repo 之前先讀完這份。
> 寫給人看的白話版在 `docs/維護手冊.md`；誰改過什麼在 `docs/維護紀錄.md`。
> 最後更新：2026-11-18 晚（方格子修改同步 update_vocus.py、YouTube 影片改連結、清舊檔、404.html）；2026-11-18

## 1. 這是什麼、誰在維護

- 網站：https://vickymommy.github.io/ （Vicky Mommy 玲玲的個人網站；GitHub Pages 靜態網站，沒有伺服器、沒有資料庫）
- repo：`vickymommy/vickymommy.github.io`（GitHub 組織 `vickymommy`，**公開 repo**：寫進來的任何東西全世界都看得到）
- **維護者有兩位**（2026-11-18：Justin 是組織 Owner，玲玲是 repo 協作者 write；預定玲玲也升 Owner）：
  - 玲玲（GitHub `vickytsai927`）：網站主人，管內容；改程式時通常請 ChatGPT 幫忙
  - Justin（GitHub `justin-n8n`）：建置者，玲玲可能請他協助維護；他用 Claude Code
- 兩人可能各自、在不同時間、用不同的 AI 改網站，所以第 6 節的「兩人共用規矩」一定要遵守。

## 2. 網站怎麼運作（一張圖）

```
方格子（vocus.cc，玲玲平常寫文章的地方）
   │ 每天台北 02:00  daily_sync.yml → scripts/sync_vocus.py
   ▼
content/articles/*.md  ←── 玲玲在 PagesCMS 後台（app.pagescms.org）新增「網站獨家」文章
content/*.yml          ←── 玲玲在後台改社群、課程、YouTube 設定
   │ scripts/build.py（每天同步後、或 content/ 有 push 時 build_on_push.yml）
   ▼
data/*.json  ──→  各頁 HTML 用 assets/js/site.js 讀進來顯示
```

- YouTube：`scripts/fetch_youtube.py` 依 `content/youtube.yml` 列的播放清單抓 RSS，寫 `data/videos.json`（每天 02:00＋content 變動時）。
- 修改同步：`scripts/update_vocus.py`（sync_vocus 之後）看方格子每篇的 `lastPublishAt`（玲玲「更新發布」時會變），跟 `data/vocus_versions.json` 記的比；變了而且網站上那篇沒被改過 → 自動更新內文；網站上也改過 → 不蓋掉，開 Issue「📝 方格子改過的文章，網站沒自動更新」。
- 對帳：每天同步完 `scripts/check_sync.py` 自己再問一次方格子，跟網站比對篇數、ID、分類，寫 `data/sync_status.json`；對不上就開 GitHub Issue「⚠️ 方格子與網站文章對不上」。
- 看門狗：`watchdog.yml` 每天台北 10:00 檢查 `sync_status.json` 有沒有超過 30 小時沒更新、所有 workflow 檔讀不讀得進去；有問題開 Issue「🐕 看門狗：每日同步可能沒有在跑」。
- 每一頁頁尾「文章最後同步 M/D HH:MM 🟢／🟡」讀 `data/sync_status.json`：🟢＝2 天內有同步且對帳正常，🟡＝有問題（滑鼠移上去看原因）。

**名詞**：workflow＝GitHub Actions 的自動執行設定（`.github/workflows/*.yml`）；Issue＝GitHub 上的問題單，會寄信給 Watch 的人；frontmatter＝`.md` 檔最上面兩行 `---` 之間的欄位（標題、日期、分類…）；build＝把 `content/` 轉成 `data/*.json`；push protection＝GitHub 偵測到金鑰就擋下 push 的功能。

## 3. 資料夾與檔案

| 路徑 | 是什麼 | 可以手改嗎 |
|---|---|---|
| `index.html`、`articles.html`、`article.html`、`videos.html`、`community.html`、`courses.html`、`ipas.html` | 7 個頁面 | 可以（版面／程式） |
| `assets/js/site.js` | 所有頁面共用的程式（讀 data、畫頁首頁尾、文章列表） | 可以 |
| `assets/css/style.css` | 共用樣式 | 可以 |
| `assets/images/` | 文章圖片（同步程式下載的＋後台上傳的） | 不要刪；同步程式會管 |
| `content/articles/*.md` | 每篇文章一個檔（frontmatter＋內文 HTML） | 見第 4 節 |
| `content/community.yml`、`course.yml`、`youtube.yml` | 社群、課程、YouTube 設定（後台在改） | 可以，但通常讓玲玲在後台改 |
| `data/*.json` | **程式產生的**，前台讀這裡：`articles.json`、`community.json`、`course.json`（build.py）、`videos.json`（fetch_youtube.py）、`sync_status.json`（check_sync.py） | ❌ 不要手改，改 `content/` 再跑對應程式；push 到 `content/` 時 build_on_push 也會自動重產 |
| `scripts/sync_vocus.py` | 方格子同步（房間清單 `ROOM_IDS` 在這裡，只有這一份） | 小心改 |
| `scripts/build.py` | content → data/*.json | 可以 |
| `scripts/fetch_youtube.py` | YouTube 播放清單 → data/videos.json | 可以 |
| `scripts/update_vocus.py` | 方格子修改同步（見第 4 節）；`--dry-run` 只列不寫 | 小心改 |
| `data/vocus_versions.json` | update_vocus 記每篇上次同步的發布時間與內文指紋 | ❌ 不要手改 |
| `scripts/check_sync.py` | 每日對帳，只讀不改文章 | 可以 |
| `scripts/check_workflows.py` | 檢查 `.github/workflows/*.yml` 讀不讀得進去 | 可以 |
| `.github/workflows/` | `daily_sync.yml`（每日同步）、`build_on_push.yml`（content 變動重建）、`watchdog.yml`（看門狗）；舊的 `build.yml` 2026-11-18 已移除 | 改了一定要跑 `check_workflows.py` |
| `.pages.yml` | PagesCMS 後台設定：後台看得到哪些欄位 | 改了要到後台確認 |
| `robots.txt`、`sitemap.xml` | 目前**封鎖搜尋引擎**（開發中）；定案後才開放 | 要玲玲同意才改 |
| `docs/` | 白話維護手冊、交接提示詞、維護紀錄 | 可以；改網站行為時要一起更新 |
| `weekly.html` | 轉址頁：分享天地 2026-11-18 移除後，舊連結自動回首頁 | 保留，不用改 |
| `404.html` | 找不到的網址都到這頁：舊版 `/articles/<id>.html` 自動轉 `article.html?id=<id>`，其他 3 秒回首頁 | 可以 |

## 4. 文章的兩條路（最容易出錯的地方）

- **方格子同步來的文章**：frontmatter 的 `source` 是 `https://vocus.cc/article/...`。由 `sync_vocus.py` 管。
  - 新文章由 `sync_vocus.py` 加；**修改**由 `update_vocus.py` 處理（2026-11-18 起）：玲玲在方格子改完按「更新發布」，隔天 02:00 網站內文、標籤、閱讀分鐘數自動更新；**檔名、標題、發布日期、分類、摘要、封面保留網站原本的**（68 篇網站標題本來就跟方格子不同，是刻意的）。圖片用新檔名下載，舊圖留著。
  - 如果網站上那篇內文也被改過（後台 Edit 內文，或後台存檔時編輯器重排了 HTML），`update_vocus.py` 不會蓋掉，只開一次 Issue 請人決定。
  - 方格子內嵌的 YouTube（`<iframe>`）會被網站的 DOMPurify 擋掉，所以同步時一律改成縮圖＋「▶ 在 YouTube 觀看影片」連結（`sync_vocus.py` 的 `youtube_iframes_to_links()`）。
  - 手動要整篇換成方格子版本，兩種做法：
    - ① **建議**：直接改那篇 `.md` 的內文（玲玲在後台「心情日誌」Edit 也是改這個檔）。同步程式不會蓋回去。
    - ② 整篇重抓（例如改了很多圖）：把那篇 `.md` 暫時移到 repo 外（**這是暫存不是刪除**，重抓成功前不要丟掉），commit 後手動跑 daily_sync，會當新文章重抓。手動改過的分類、摘要、標籤會變回自動判斷的值，重抓後要對照舊檔改回來；重抓失敗就把舊檔放回。
  - 安裝套件：`pip install -r requirements.txt`（版本都鎖死，跟 workflow 一樣；要升級改 `requirements.txt` 並本機測過）。
- **網站獨家文章**：`source` 空白，在後台新增，同步程式不會碰。
- 分類只能單選，值是 `ai`、`event`、`share`、`growth`、`parenting`、`travel`、`diy`（對照在 `.pages.yml` 與 `sync_vocus.py` 的 `ROOM_CATEGORY_MAP`）。
- 一篇文章只會有一個 `.md`。2026-06 搬來的舊文章檔名是 8 碼（例如 `633bd5b0.md`），之後同步的是 24 碼，兩種都正常；同步程式用 `source` 網址判斷文章是否已存在，不看檔名。（2026-11-18 前有 11 個 `_duplicate_of` 空白重複檔，已移除；`build.py`、`check_sync.py` 仍會略過這種檔。）
- 2026-11-18 清掉的 2026-06 初版舊檔（`articles/*.html`、`old/`、`data/articles.js`、`data/extra.js`、`vocus_clean.json`、根目錄下載腳本、`build.yml`）只在 git 歷史裡，要找回用 `git log --all -- <路徑>`。

## 5. 改完怎麼驗證

1. 本機預覽：在 repo 根目錄跑 `python -m http.server 8724`，開 http://localhost:8724/ ，看 console 沒有錯誤、手機寬度（375px）沒有橫向捲動。
2. 改了 `content/`：跑 `python scripts/build.py`，確認 `data/*.json` 有更新。
3. 改了 `.github/workflows/`：push 前跑 `python scripts/check_workflows.py`（要 `pip install pyyaml`），必須回傳 0。**2026-09-17 曾因一個縮排錯誤，自動同步停了兩個月沒人發現。**
4. 改了同步或對帳：跑 `python scripts/check_sync.py`，看「方格子 X 篇、網站 Y 篇；缺 0、多 0」。
5. 改了 `assets/css/style.css` 或 `assets/js/site.js`：第 3 節那 7 個 HTML 裡的版本號要一起改，不然使用者的瀏覽器會用舊檔。格式是 `style.css?v=20261118d`（日期＋同一天第幾次的字母），7 頁要一樣。批次改：`sed -i 's/?v=20261118d/?v=新版號/g' *.html`（Windows 注意不要把換行改成 CRLF）。
6. push 後：到 https://github.com/vickymommy/vickymommy.github.io/actions 看 workflow 是綠色；線上頁面重新整理確認。
7. 手動跑同步：網頁 Actions →「每日自動同步」→ Run workflow；或指令 `gh workflow run daily_sync.yml -R vickymommy/vickymommy.github.io`。

## 6. 兩人共用規矩（一定要做）

1. **動手前先 `git pull`**（或在 GitHub 網頁上看最新版），免得蓋掉另一位剛改的。
2. **改完在 `docs/維護紀錄.md` 最上面加一行**：`- YYYY-MM-DD｜誰（玲玲／Justin，用什麼 AI）｜改了什麼（一句話）`。只寫做了什麼，不寫心得或私人內容（公開 repo）。
3. commit 訊息用中文寫清楚改了什麼。
4. 改到網站行為（新頁面、新流程、新排程）時，同一次 commit 更新這份 `AGENTS.md` 和 `docs/維護手冊.md`。
5. 自動產生的 commit（`auto: 每日同步…`）是 GitHub Actions 機器人做的，不用記維護紀錄。
6. 「網站行為」＝使用者看得到的功能或流程（新頁面、新欄位、新排程、同步方式）；只改顏色、字、排版算一般修改，記維護紀錄就好。
7. push 被拒（遠端比較新，通常是每天的機器人 commit 或另一位剛改過）：先 `git pull --rebase` 再 push。`docs/維護紀錄.md` 撞到時，兩邊的行都保留，按日期排。
8. 權限有變（誰升 Owner、誰退出）：改本檔第 1 節、`docs/維護手冊.md` 第一、六節、`README.md` 最後一行。

## 6b. 資安設定（2026-11-18，見 `docs/維護紀錄.md`；完整分析在 Justin 本機）

- **每一頁都有 CSP**（轉址頁 `weekly.html` 除外；`<meta http-equiv="Content-Security-Policy">`）：程式只能來自自己網站和 `https://cdnjs.cloudflare.com`；不能用 `onclick=`、`onerror=` 這類寫在 HTML 裡的事件（請用 `addEventListener`）；不能嵌 iframe。**要加外部程式、字型、iframe 時，7 個頁面＋`404.html` 的 CSP 都要一起改**，改完看瀏覽器 console 有沒有 CSP 錯誤。`404.html` 的內嵌程式用 sha256 雜湊放行，改了那段程式要重算雜湊。
- **DOMPurify** 鎖版本＋`integrity`（SRI）。升級時到 cdnjs 拿新版本的 SRI 雜湊，改 `article.html` 那個 `<script>` 的網址和 `integrity`（上面註解的版本號也順手改）。
- **GitHub Actions 只能用 GitHub 官方的 action**（repo 設定），而且 `uses:` 寫完整 commit SHA，後面註解版本號。不要改回 `@v4` 這種標籤。
- **Python 套件版本鎖在 `requirements.txt`**，不要在 workflow 裡寫沒版本的 `pip install`。
- **main 分支有 ruleset**：禁止 force push、禁止刪除。一般 push 不受影響；推不上去就先 `git pull --rebase`。
- 同步程式會拿掉方格子內文所有 `on*` 事件屬性和 YouTube iframe，不要把它們加回來。

## 7. 禁止事項

- ❌ 不放任何密碼、金鑰、token、個人電話地址（公開 repo；push protection 會擋一部分，但不要依賴它）。目前 workflow 只用 GitHub 自動給的 `GITHUB_TOKEN`，**不需要也不要新增 secrets**。
- ❌ 不刪 `content/articles/` 的文章、不刪 `assets/images/`；真的要下架先問玲玲。
- ❌ 不手改 `data/*.json`。
- ❌ 不改 `robots.txt`／`sitemap.xml` 開放搜尋引擎、不加 GA 追蹤碼，除非玲玲說要。
- ❌ 不自動關掉對帳／看門狗開的 Issue；先查原因、修好，再由人關。
- ❌ 不改 GitHub 組織或 repo 的安全設定（2FA、secret scanning、Dependabot）。

## 8. 收到 Issue 時怎麼查

| Issue 標題 | 意思 | 先做什麼 |
|---|---|---|
| ⚠️ 方格子與網站文章對不上 | 對帳發現缺文章、多文章或分類不同 | 看 Issue 內文列的文章；缺的通常手動重跑 daily_sync 就好；多的可能是玲玲把方格子文章設成不公開（只通知，不會自動刪） |
| 📝 方格子改過的文章，網站沒自動更新 | 方格子那篇「更新發布」了，但網站上那篇也被改過，為了不蓋掉沒更新 | Issue 內文列了是哪幾篇：要保留網站版本就關掉 Issue；要換成方格子版本照第 4 節「整篇重抓」 |
| 🐕 看門狗：每日同步可能沒有在跑 | Issue 內文會寫是哪一種：① 超過 30 小時沒同步 ② workflow 檔格式壞了 | ① 到 Actions 看 daily_sync 最近一次：紅色就看錯誤訊息修；根本沒跑（排程被 GitHub 停掉）就到 Actions 頁面按「Enable workflow」再手動跑一次 ② 跑 `check_workflows.py` 看哪個檔哪一行，修好 push（push 後看門狗會自動再檢查一次） |
| 其他「失敗」Issue | 某個 workflow 執行失敗 | 點 Issue 裡的執行連結看錯誤訊息 |

同一件事每天會留言在同一張 Issue，不會一天開一張。修好後手動 Close。

## 9. 已知限制與待決定

- 方格子文章修改：會同步內文，但標題、分類、摘要、封面維持網站原本的；要改這些請在後台改（第 4 節）。
- 一篇文章在方格子掛兩個房間：網站只能選一個分類（要不要做複選等玲玲決定）。
- 方格子某個房間超過 300 篇時，`sync_vocus.py` 與 `check_sync.py` 的 `num=300` 要改大。
- 玲玲在方格子開新房間（對帳會先報「網站缺」）：
  1. 房間 ID：方格子沙龍（`https://vocus.cc/salon/651fb341fd897800018f38ed`）裡點那個房間，網址裡 24 碼英數字的那一段（跟 `ROOM_IDS` 現有的長得一樣）；不確定就請玲玲把房間網址貼過來。
  2. `scripts/sync_vocus.py`：`ROOM_IDS`、`ROOM_ID_TO_NAME`、`ROOM_CATEGORY_MAP` 各加一筆（`check_sync.py` 會沿用，不用另改）。
  3. 如果要用**新的分類**（不是現有 7 個之一），還要加在：`.pages.yml` 分類選項、`assets/js/site.js` 開頭的分類對照、`scripts/build.py` 的分類對照、`docs/維護手冊.md` 第二節的分類清單；改了 site.js 要更新 `?v=`。
  4. 手動跑一次 daily_sync，確認對帳「缺 0」。
- GitHub 公開 repo 連續 60 天沒 commit 會停排程；每天的同步 commit 會自然避開。
- 網站定位（合作邀約頁、媒體經歷頁等）、搜尋引擎開放、GA4：等玲玲決定。
