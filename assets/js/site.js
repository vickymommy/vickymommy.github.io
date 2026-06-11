/* Vicky Mommy 網站 — 共用前台程式 v2（fetch 架構）
   資料來源：data/articles.json、data/community.json、data/course.json
   文章內文：content/articles/<id>.md（按需 fetch）
   新增文章：在後台（PagesCMS）操作，GitHub Action 自動重建 JSON。 */

const CAT_LABELS = {
  ai: 'AI 學習應用', growth: '媽媽自我成長',
  parenting: '親子生活指南', travel: '親子旅遊', diy: '親子手作'
};

/* ---------- 全域資料 ---------- */
let ARTICLES  = [];
let COMMUNITY = {};
let COURSE    = {};

/* ---------- 資料初始化（一次 fetch 三支 JSON）---------- */
async function initData() {
  try {
    const [artData, comm, course] = await Promise.all([
      fetch('data/articles.json').then(r => r.json()),
      fetch('data/community.json').then(r => r.json()),
      fetch('data/course.json').then(r => r.json()),
    ]);
    ARTICLES  = (artData.articles || []).sort((a, b) => (a.date < b.date ? 1 : -1));
    COMMUNITY = comm   || {};
    COURSE    = course || {};
  } catch (e) {
    console.error('[Vicky Mommy] 資料載入失敗：', e);
  }
}

/* ---------- 頁首頁尾 ---------- */
function injectChrome(active) {
  const nav = (id, href, label) =>
    '<a href="' + href + '" class="' + (active === id ? 'active' : '') + '">' + label + '</a>';
  document.getElementById('site-header').innerHTML =
    '<header class="nav"><div class="wrap nav-inner">' +
    '<a class="logo" href="index.html"><span class="heart">&#9829;</span> Vicky Mommy</a>' +
    '<nav class="menu">' +
      nav('home',      'index.html',     '首頁') +
      nav('articles',  'articles.html',  '心情日誌') +
      nav('weekly',    'weekly.html',    '分享天地') +
      nav('ipas',      'ipas.html',      'iPAS 專區') +
      nav('courses',   'courses.html',   '課程') +
      nav('community', 'community.html', '社群交流圈') +
    '</nav>' +
    '<a class="btn" href="https://lin.ee/JM7WXWo" target="_blank">加入共學團</a>' +
    '</div></header>';
  document.getElementById('site-footer').innerHTML =
    '<footer><div class="wrap"><div class="foot-grid">' +
    '<div><h4>Vicky Mommy</h4><p style="font-size:13.5px;line-height:1.7">從今天生活裡的一個小地方開始，持續學習、持續分享。</p></div>' +
    '<div><h4>逛逛</h4><a href="articles.html">心情日誌</a><a href="weekly.html">分享天地</a><a href="ipas.html">iPAS 專區</a><a href="courses.html">課程</a><a href="community.html">社群交流圈</a></div>' +
    '<div><h4>Vicky天地</h4><a href="https://www.youtube.com/c/VickyMommy" target="_blank">YouTube</a><a href="https://lin.ee/JM7WXWo" target="_blank">LINE 共學團</a><a href="https://www.facebook.com/HiVickyMommy" target="_blank">Facebook</a><a href="https://www.instagram.com/vickytsai927/" target="_blank">Instagram</a><a href="mailto:vickytsai927@gmail.com">合作邀約信箱</a></div>' +
    '</div><div class="foot-bottom">&copy; 2026 Vicky Mommy</div></div></footer>';
}

/* ---------- 卡片 HTML ---------- */
function cardHTML(a) {
  const cover = a.cover
    ? '<div class="thumb" style="background-image:url(\'' + a.cover + '\')"><span class="tag">' + (CAT_LABELS[a.category] || '') + '</span></div>'
    : '<div class="thumb thumb-blank"><span class="tag">' + (CAT_LABELS[a.category] || '') + '</span></div>';
  return '<a class="card" href="article.html?id=' + a.id + '">' + cover +
    '<div class="body"><h3>' + a.title + '</h3><p>' + (a.excerpt || '') + '</p>' +
    '<div class="meta"><span>' + a.date + '</span><span>閱讀 ' + (a.readMin || 5) + ' 分鐘</span></div></div></a>';
}

function ytCard(v) {
  return '<a class="vcard" href="https://www.youtube.com/watch?v=' + v.id + '" target="_blank" rel="noopener">' +
    '<div class="vthumb"><img src="https://img.youtube.com/vi/' + v.id + '/hqdefault.jpg" loading="lazy" alt=""><span class="vplay">&#9658;</span></div>' +
    '<div class="vtitle">' + v.title + '</div></a>';
}

/* ---------- 首頁精選（最新 6 篇）---------- */
function renderFeatured() {
  const box = document.getElementById('featured-grid');
  if (!box) return;
  box.innerHTML = ARTICLES.slice(0, 6).map(cardHTML).join('');
}

/* ---------- 文章列表（articles.html）---------- */
function renderListing() {
  const box = document.getElementById('listing-grid');
  if (!box) return;
  let cat = 'all', kw = '';
  function apply() {
    const list = ARTICLES.filter(a =>
      (cat === 'all' || a.category === cat) &&
      (kw === '' || (a.title + a.excerpt + (a.tags || []).join('')).toLowerCase().includes(kw.toLowerCase()))
    );
    box.innerHTML = list.length
      ? list.map(cardHTML).join('')
      : '<p style="grid-column:1/-1;text-align:center;color:var(--ink-soft);padding:40px">沒有符合的文章，換個關鍵字試試</p>';
    const c = document.getElementById('count');
    if (c) c.textContent = '共 ' + list.length + ' 篇文章';
  }
  document.querySelectorAll('.cat').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('.cat').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    cat = b.dataset.cat;
    apply();
  }));
  const s = document.getElementById('search-input');
  if (s) s.addEventListener('input', e => { kw = e.target.value; apply(); });
  apply();
}

/* ---------- 文章內頁（article.html）---------- */
/* 從 .md 純文字中去除 frontmatter，取出 HTML body */
function stripFrontmatter(text) {
  if (!text.startsWith('---')) return text;
  const m = text.match(/^---[\s\S]*?\n---\n([\s\S]*)$/);
  return m ? m[1].trim() : text;
}

async function renderArticle() {
  const box = document.getElementById('article-root');
  if (!box) return;
  const id = new URLSearchParams(location.search).get('id');
  const a = ARTICLES.find(x => x.id === id);
  if (!a) {
    box.innerHTML = '<div class="pending">找不到這篇文章，<a href="articles.html">回到文章列表</a></div>';
    return;
  }
  document.title = a.title + '｜Vicky Mommy';

  /* 先渲染頭部，body 區放「載入中」*/
  box.innerHTML =
    '<div class="article-head"><div class="wrap" style="max-width:760px">' +
    '<span class="cat-tag">' + (CAT_LABELS[a.category] || '') + '</span>' +
    '<h1>' + a.title + '</h1>' +
    '<div class="info"><span>' + a.date + '</span><span>閱讀 ' + (a.readMin || 5) + ' 分鐘</span><span>Vicky Mommy</span></div>' +
    '</div></div>' +
    '<div id="article-body-slot"><p style="text-align:center;padding:40px;color:var(--ink-soft)">內文載入中…</p></div>' +
    '<div class="article-tags">' + (a.tags || []).map(t => '<span>#' + t + '</span>').join('') + '</div>' +
    '<div class="article-foot"><a class="btn ghost" href="articles.html">回文章列表</a>' +
    '<a class="btn" href="https://lin.ee/JM7WXWo" target="_blank">加入媽咪 AI 賦能共學團</a></div>';

  /* 非同步取得 .md 內文 */
  try {
    const mdText = await fetch('content/articles/' + id + '.md').then(r => {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.text();
    });
    const body = stripFrontmatter(mdText);
    const slot = document.getElementById('article-body-slot');
    if (slot) slot.outerHTML = body
      ? '<div class="article-body">' + body + '</div>'
      : '<div class="pending">這篇文章的完整內文正在整理中。你可以先到 <a href="' + a.source + '" target="_blank">原文連結</a> 閱讀。</div>';
  } catch (e) {
    const slot = document.getElementById('article-body-slot');
    if (slot) slot.innerHTML =
      '<div class="pending">內文暫時無法載入。你可以先到 <a href="' + (a.source || '#') + '" target="_blank">原文連結</a> 閱讀。</div>';
  }
}

/* ---------- 社群交流圈 ---------- */
function renderCommunity() {
  const box = document.getElementById('community-root');
  if (!box) return;
  const E = COMMUNITY;
  box.innerHTML =
    '<section><div class="wrap">' +
    '<div class="sec-head"><span class="pill">社群交流圈</span><h2>Vicky 的 AI 社群交流圈</h2><p>' + (E.socialIntro || '') + '</p></div>' +
    '<div class="community-hero"><img src="' + (E.socialImage || '') + '" alt="社群交流圈"></div>' +
    '<div class="chip-row">' +
      '<a class="btn" href="' + (E.playlist || '#') + '" target="_blank">AI應用交流分享會</a>' +
      '<a class="btn ghost" href="' + (E.channel || '#') + '" target="_blank">YouTube 頻道</a>' +
    '</div>' +
    '<div class="vgrid">' + (E.videos || []).map(ytCard).join('') + '</div>' +
    '<div class="join-row">' +
      '<a class="com2" href="' + (E.line || '#') + '" target="_blank"><h4>媽咪 AI 賦能共學團</h4><p>1000+ 夥伴一起學</p></a>' +
      '<a class="com2" href="' + (E.fb || '#') + '" target="_blank"><h4>Facebook</h4><p>HiVickyMommy</p></a>' +
      '<a class="com2" href="' + (E.ig || '#') + '" target="_blank"><h4>Instagram</h4><p>@vickytsai927</p></a>' +
    '</div></div></section>';
}

/* ---------- iPAS 專區 ---------- */
function isIpas(a) {
  return /iPAS|AI ?應用規劃師|經濟部|產業人才能力鑑定/i.test(a.title + ' ' + (a.tags || []).join(' '));
}

function renderIpas() {
  const box = document.getElementById('ipas-root');
  if (!box) return;
  const E = COMMUNITY;
  const arts = ARTICLES.filter(isIpas);
  box.innerHTML =
    '<section><div class="wrap">' +
    '<div class="sec-head"><span class="pill">iPAS 專區</span><h2>iPAS AI 應用規劃師</h2></div>' +
    '<div class="chip-row">' +
      '<a class="btn" href="' + (E.ipasStudy || '#') + '" target="_blank">前往 iPAS 備考站</a>' +
      '<a class="btn ghost" href="' + (E.playlist || '#') + '" target="_blank">AI應用交流分享會</a>' +
      '<a class="btn ghost" href="' + (E.ipasChannel || '#') + '" target="_blank">iPAS 官方頻道</a>' +
      '<a class="btn ghost" href="https://www.ipas.org.tw/AIAP" target="_blank">官方專區</a>' +
    '</div>' +
    '<h3 class="block-title">iPAS 相關影片</h3>' +
    '<div class="vgrid">' + (E.videos || []).map(ytCard).join('') + '</div>' +
    '<h3 class="block-title">iPAS 相關文章（' + arts.length + ' 篇）</h3>' +
    '<div class="grid">' + arts.map(cardHTML).join('') + '</div>' +
    '</div></section>';
}

/* ---------- 課程 ---------- */
function renderCourses() {
  const box = document.getElementById('courses-root');
  if (!box) return;
  const c = COURSE;
  const E = COMMUNITY;
  box.innerHTML =
    '<section><div class="wrap">' +
    '<div class="sec-head"><span class="pill">課程</span><h2>跟著Vicky一起學</h2><p>給想開始、但不知道從哪裡下手的媽媽與初學者。</p></div>' +
    '<div class="course-card">' +
    '<h3>' + (c.title || '') + '</h3>' +
    '<div class="course-sub">' + (c.sub || '') + '</div>' +
    '<p class="course-desc">' + (c.desc || '') + '</p>' +
    '<ul class="course-outline">' + (c.outline || []).map(o => '<li>' + o + '</li>').join('') + '</ul>' +
    '<div class="course-meta">' + (c.meta || '') + '　｜　' + (c.suitable || '') + '</div>' +
    '<div class="chip-row" style="margin-top:18px">' +
      '<a class="btn" href="' + (c.link || E.line || '#') + '" target="_blank">前往課程頁面（報名）</a>' +
      '<a class="btn ghost" href="' + (E.channel || '#') + '" target="_blank">先看免費影片</a>' +
    '</div></div></div></section>';
}

/* ---------- DOMContentLoaded 進入點 ---------- */
document.addEventListener('DOMContentLoaded', async function () {
  injectChrome(document.body.dataset.page);
  await initData();
  renderFeatured();
  renderListing();
  await renderArticle();
  renderCommunity();
  renderIpas();
  renderCourses();
});
