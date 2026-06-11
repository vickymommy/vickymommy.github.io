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

if __name__ == '__main__':
    build_articles()
    build_yaml_to_json('content/community.yml', 'data/community.json')
    build_yaml_to_json('content/course.yml',    'data/course.json')
    print('全部完成。')
