#!/usr/bin/env node
/* ============================================================
   Vicky Mommy 玲玲 網站｜文章內文 + 圖片 本機下載腳本
   ------------------------------------------------------------
   功能：讀 data/articles.json 的文章清單，逐篇從 vocus 下載「正文」與
        「圖片」到站內，產生 articles/<id>.html，並重新產生 data/articles.js。
   需求：Node.js 18 以上（內建 fetch，不需安裝任何套件）。
   用法：在「網站專案」資料夾開啟終端機，執行：
            node 下載文章.mjs            （只補還沒有內文的文章）
            node 下載文章.mjs --force     （全部重抓，含已完成的）
   ============================================================ */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dir = path.dirname(fileURLToPath(import.meta.url));
const DATA = path.join(__dir, 'data', 'articles.json');
const ART_DIR = path.join(__dir, 'articles');
const IMG_DIR = path.join(__dir, 'assets', 'images');
const FORCE = process.argv.includes('--force');
const SLEEP_MS = 800; // 每篇間隔，對 vocus 友善一點

const sleep = ms => new Promise(r => setTimeout(r, ms));
fs.mkdirSync(ART_DIR, { recursive: true });
fs.mkdirSync(IMG_DIR, { recursive: true });

const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36' };

/* ---------- 工具：下載圖片到 assets/images，回傳本機相對路徑 ---------- */
const imgCache = new Map();
async function downloadImage(uuidOrUrl) {
  // 取出 images.vocus.cc/<uuid>（去掉縮圖前綴與副檔名雜訊）
  let uuid = uuidOrUrl;
  const m = String(uuidOrUrl).match(/images\.vocus\.cc\/([0-9a-f-]{8,})/i);
  if (m) uuid = m[1];
  uuid = uuid.replace(/\.(jpg|jpeg|png|webp|gif)$/i, '');
  if (!/^[0-9a-f-]{8,}$/i.test(uuid)) return null;
  if (imgCache.has(uuid)) return imgCache.get(uuid);
  const url = `https://images.vocus.cc/${uuid}`;
  try {
    const res = await fetch(url, { headers: UA });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const ct = res.headers.get('content-type') || '';
    const ext = ct.includes('png') ? 'png' : ct.includes('webp') ? 'webp'
              : ct.includes('gif') ? 'gif' : 'jpg';
    const buf = Buffer.from(await res.arrayBuffer());
    const fname = `${uuid}.${ext}`;
    fs.writeFileSync(path.join(IMG_DIR, fname), buf);
    const rel = `assets/images/${fname}`;
    imgCache.set(uuid, rel);
    return rel;
  } catch (e) {
    console.warn('   ⚠ 圖片下載失敗:', uuid, e.message);
    imgCache.set(uuid, null);
    return null;
  }
}

/* ---------- 從 __NEXT_DATA__ 或原始 HTML 取出正文 HTML ---------- */
function deepFindBody(obj) {
  // 在 JSON 內遞迴找「最像文章內文」的 HTML 字串
  let best = '';
  const visit = v => {
    if (typeof v === 'string') {
      if (/<p[\s>]/i.test(v) && v.length > best.length) best = v;
    } else if (v && typeof v === 'object') {
      for (const k of Object.keys(v)) visit(v[k]);
    }
  };
  visit(obj);
  return best;
}

function extractBodyHtml(html) {
  // 策略 1：Next.js 的 __NEXT_DATA__
  const nm = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  if (nm) {
    try {
      const json = JSON.parse(nm[1]);
      const body = deepFindBody(json?.props?.pageProps ?? json);
      if (body && body.length > 200) return body;
    } catch {}
  }
  // 策略 2：抓 <article>…</article>
  const am = html.match(/<article[^>]*>([\s\S]*?)<\/article>/i);
  if (am) return am[1];
  return '';
}

/* ---------- 清理 HTML：只保留需要的標籤，圖片改為本機 ---------- */
async function cleanHtml(raw) {
  let h = raw;
  // 先處理圖片：把所有 img 的 src 換成本機下載後的路徑
  const imgTags = [...h.matchAll(/<img[^>]*>/gi)].map(x => x[0]);
  for (const tag of imgTags) {
    const srcM = tag.match(/src=["']([^"']+)["']/i);
    let local = null;
    if (srcM) local = await downloadImage(srcM[1]);
    if (local) h = h.replace(tag, `<figure><img src="${local}" loading="lazy" alt="文章配圖"></figure>`);
    else h = h.replace(tag, '');
  }
  // 保留 YouTube iframe
  // 移除 script/style/svg/noscript 等
  h = h.replace(/<(script|style|svg|noscript|button|nav|header|footer)[\s\S]*?<\/\1>/gi, '');
  // 將標題標籤統一為 h2
  h = h.replace(/<h[1-6][^>]*>/gi, '<h2>').replace(/<\/h[1-6]>/gi, '</h2>');
  // 移除所有標籤的 class/style/data-* 等屬性（保留 a 的 href、img 的 src、iframe 的 src）
  h = h.replace(/<(p|h2|ul|ol|li|blockquote|strong|em|b|i|figure|figcaption|br|div|span)\b[^>]*>/gi,
                (mm, t) => `<${t.toLowerCase()}>`);
  // div/span 轉成段落語意：直接去掉外層 div/span 標籤
  h = h.replace(/<\/?(div|span)>/gi, '');
  // 連結只留 href
  h = h.replace(/<a\b[^>]*href=["']([^"']+)["'][^>]*>/gi, '<a href="$1" target="_blank" rel="noopener">');
  // 清掉空段落與多餘空白
  h = h.replace(/<p>\s*<\/p>/gi, '').replace(/\n{3,}/g, '\n\n').trim();
  return h;
}

/* ---------- 主流程 ---------- */
const data = JSON.parse(fs.readFileSync(DATA, 'utf-8'));
let done = 0, skip = 0, fail = 0;

for (const a of data.articles) {
  const fullId = (a.source || '').match(/article\/([0-9a-f]+)/)?.[1];
  const outFile = path.join(ART_DIR, `${a.id}.html`);
  const already = a.bodyFile && fs.existsSync(path.join(__dir, a.bodyFile));
  if (!FORCE && already) { skip++; continue; }
  if (!fullId) { console.warn('跳過（找不到原文ID）:', a.id); fail++; continue; }

  process.stdout.write(`下載 ${a.id}  ${a.title.slice(0, 24)}… `);
  try {
    const res = await fetch(a.source, { headers: UA });
    const html = await res.text();
    const rawBody = extractBodyHtml(html);
    if (!rawBody || rawBody.length < 150) throw new Error('找不到正文');
    const clean = await cleanHtml(rawBody);
    if (clean.length < 80) throw new Error('正文過短');
    fs.writeFileSync(outFile, clean, 'utf-8');
    a.bodyFile = `articles/${a.id}.html`;
    // 順便把封面也下載到本機
    if (a.cover && a.cover.includes('images.vocus.cc')) {
      const rel = await downloadImage(a.cover);
      if (rel) a.cover = rel;
    }
    console.log('✓');
    done++;
  } catch (e) {
    console.log('✗', e.message);
    fail++;
  }
  await sleep(SLEEP_MS);
}

/* ---------- 寫回 articles.json 並重新產生 articles.js ---------- */
fs.writeFileSync(DATA, JSON.stringify(data, null, 2), 'utf-8');

const forJs = JSON.parse(JSON.stringify(data));
for (const a of forJs.articles) {
  const bf = a.bodyFile;
  a.body = (bf && fs.existsSync(path.join(__dir, bf))) ? fs.readFileSync(path.join(__dir, bf), 'utf-8') : '';
  delete a.bodyFile;
}
const js = '/* 自動產生：由 data/articles.json 轉出。*/\n' +
           'window.SITE_DATA = ' + JSON.stringify({ categories: forJs.categories, articles: forJs.articles }, null, 1) + ';\n';
fs.writeFileSync(path.join(__dir, 'data', 'articles.js'), js, 'utf-8');

console.log('\n========================================');
console.log(`完成：新增內文 ${done} 篇｜略過(已完成) ${skip} 篇｜失敗 ${fail} 篇`);
console.log(`圖片已下載到 assets/images/（共 ${imgCache.size} 張）`);
console.log('已更新 data/articles.json 與 data/articles.js');
console.log('用瀏覽器打開 index.html 或 articles.html 即可看到結果。');
console.log('========================================');
