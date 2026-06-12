#!/usr/bin/env python3
"""
build.py — 由 GitHub Action 自動執行（每次 push 觸發）。
功能：把 content/ 裡的 .md 和 .yml 重建成前台所需的 data/*.json。

本機也可手動執行：
  cd 網站專案
  python scripts/build.py
"""
import json, os, re, sys
import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def parse_frontmatter(text):
    """解析 Markdown 檔開頭的 YAML frontmatter，回傳 (dict, body_str)。"""
    if not text.startswith('---'):
        return {}, text
    try:
        end = text.index('\n---', 3)
    except ValueError:
        return {}, text
    fm = yaml.safe_load(text[3:end]) or {}
    body = text[end + 4:].strip()
    return fm, body

def build_articles():
    articles_dir = os.path.join(BASE, 'content', 'articles')
    if not os.path.isdir(articles_dir):
        print('找不到 content/articles/ — 跳過')
        return
    articles = []
    for fname in sorted(os.listdir(articles_dir)):
        if not fname.endswith('.md'):
            continue
        with open(os.path.join(articles_dir, fname), encoding='utf-8') as f:
            fm, _ = parse_frontmatter(f.read())
        articles.append({
            'id':       fm.get('id', fname[:-3]),
            'title':    fm.get('title', ''),
            'category': fm.get('category', ''),
            'date':     str(fm.get('date', '')),
            'cover':    fm.get('cover', ''),
            'excerpt':  fm.get('excerpt', ''),
            'tags':     fm.get('tags') or [],
            'source':   fm.get('source', ''),
            'readMin':  int(fm.get('readMin', 5)),
        })
    articles.sort(key=lambda a: a['date'], reverse=True)

    out = {
        '_說明': '由 GitHub Action 自動從 content/articles/*.md 重建，請勿手動編輯此檔。',
        'categories': {
            'ai': 'AI 學習應用',
            'growth': '媽媽自我成長',
            'parenting': '親子生活指南',
            'travel': '親子旅遊',
            'diy': '親子手作',
        },
        'articles': articles,
    }
    out_path = os.path.join(BASE, 'data', 'articles.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'✓ {len(articles)} 篇文章 → data/articles.json')

def build_yaml_to_json(src_rel, dst_rel):
    src = os.path.join(BASE, src_rel)
    dst = os.path.join(BASE, dst_rel)
    if not os.path.isfile(src):
        print(f'找不到 {src_rel} — 跳過')
        return
    with open(src, encoding='utf-8') as f:
        data = yaml.safe_load(f)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'✓ {src_rel} → {dst_rel}')

def build_weekly():
    """
    讀取 content/weekly/*.md，分別產生：
      - data/weekly.json          已發布（status=published），依 publish_week 分組
      - data/weekly_pending.json  待審（status=pending），供管理參考
    """
    weekly_dir = os.path.join(BASE, 'content', 'weekly')
    if not os.path.isdir(weekly_dir):
        print('找不到 content/weekly/ — 跳過')
        return

    published = []
    pending   = []

    for fname in sorted(os.listdir(weekly_dir), reverse=True):
        if not fname.endswith('.md') or fname.startswith('.'):
            continue
        fpath = os.path.join(weekly_dir, fname)
        try:
            with open(fpath, encoding='utf-8') as f:
                fm, _ = parse_frontmatter(f.read())
        except Exception:
            continue

        item = {
            'id':          str(fm.get('id', fname[:-3])),
            'title':       fm.get('title', ''),
            'url':         fm.get('url', ''),
            'source_name': fm.get('source_name', ''),
            'category':    fm.get('category', 'news'),   # news | tool
            'pub_date':    str(fm.get('pub_date', '')),
            'fetch_date':  str(fm.get('fetch_date', '')),
            'auto_excerpt': fm.get('auto_excerpt', ''),
            'note':        fm.get('note', ''),
            'status':      fm.get('status', 'pending'),
            'publish_week': str(fm.get('publish_week', '')),
        }

        if item['status'] == 'published':
            published.append(item)
        else:
            pending.append(item)

    # ── 已發布：依 publish_week 分組 ─────────────────────────────────────────
    # 排序（最新在前）
    published.sort(key=lambda x: x.get('publish_week', ''), reverse=True)

    # 取得所有週次（維持順序）
    weeks_seen = []
    for item in published:
        wk = item.get('publish_week', '')
        if wk and wk not in weeks_seen:
            weeks_seen.append(wk)

    weekly_by_week = []
    for wk in weeks_seen:
        week_items = [i for i in published if i.get('publish_week') == wk]
        weekly_by_week.append({
            'week':  wk,
            'tools': [i for i in week_items if i['category'] == 'tool'],
            'news':  [i for i in week_items if i['category'] == 'news'],
        })

    out_weekly = {
        '_說明': '由 GitHub Action 自動從 content/weekly/*.md 重建，請勿手動編輯此檔。',
        'weeks': weekly_by_week,
    }
    os.makedirs(os.path.join(BASE, 'data'), exist_ok=True)
    with open(os.path.join(BASE, 'data', 'weekly.json'), 'w', encoding='utf-8') as f:
        json.dump(out_weekly, f, ensure_ascii=False, indent=2)
    print(f'✓ {len(published)} 筆已發布 → data/weekly.json（{len(weeks_seen)} 週）')

    # ── 待審：直接存成清單 ────────────────────────────────────────────────────
    out_pending = {
        '_說明': '待玲玲審核的每週精選候選。請勿手動編輯，由 GitHub Action 自動更新。',
        'count':   len(pending),
        'items':   pending,
    }
    with open(os.path.join(BASE, 'data', 'weekly_pending.json'), 'w', encoding='utf-8') as f:
        json.dump(out_pending, f, ensure_ascii=False, indent=2)
    print(f'✓ {len(pending)} 筆待審 → data/weekly_pending.json')

if __name__ == '__main__':
    build_articles()
    build_yaml_to_json('content/community.yml', 'data/community.json')
    build_yaml_to_json('content/course.yml',    'data/course.json')
    build_weekly()
    print('全部完成。')
