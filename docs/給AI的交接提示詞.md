# 給 AI 的交接提示詞

> 要請 AI（ChatGPT、Claude……）改網站時，把下面「複製這段」整段貼上，再把最後一行的＿＿換成你想做的事。
> 玲玲、Justin 都可以用同一段。

---

## 複製這段

```
你要幫我維護一個網站：https://vickymommy.github.io/
GitHub repo：https://github.com/vickymommy/vickymommy.github.io （公開 repo）

開始前請先做這三件事：
1. 讀 repo 根目錄的 AGENTS.md（網站怎麼運作、哪些檔不能手改、改完怎麼驗證、禁止事項），照它做。
2. 讀 docs/維護紀錄.md 最上面 10 行，看最近誰改了什麼，不要蓋掉別人剛改的。
3. 讀 docs/維護手冊.md 了解平常怎麼操作。

做事的規矩：
- 先用白話跟我說你打算改哪些檔、為什麼，我說好你才動手。
- 我不是工程師，請一步一步講，每次只給我一個動作；要我按的按鈕寫出畫面上的字。
- 改完照 AGENTS.md 第 5 節驗證，告訴我你怎麼確認的；沒辦法驗證的要直接說。
- 改完在 docs/維護紀錄.md 最上面加一行（日期｜誰＋用什麼 AI｜改了什麼）。
- 不要放任何密碼、金鑰、電話地址進 repo；不要刪文章和圖片。
- 遇到不確定的，先問我，不要猜。

我想做的事：＿＿
```

---

## 如果 AI 不能直接讀 GitHub

有些 AI 只能看你貼的文字。那就：
1. 打開 https://github.com/vickymommy/vickymommy.github.io/blob/main/AGENTS.md ，全選複製，貼給 AI。
2. 再貼上面那段。
3. AI 叫你改檔案時，在 GitHub 網頁上打開那個檔 → 右上角鉛筆圖示（Edit）→ 改 → 「Commit changes」。

## 如果是收到 Issue 信

把 Issue 的網址和內容一起貼給 AI，最後一行寫「我收到這張 Issue，請幫我查原因、告訴我要不要處理」。
