#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────
# build-sitemap.py — 從 articles.json 產生 sitemap.xml（導外版）
#   來源：articles.json（文章清單）
#   產出：sitemap.xml（覆寫）；首頁 + 每篇文章一筆
#   網址：https://www.guoguo.tw/guide/ + 每篇 url（相對路徑）
#   用法：articles.json 有異動就重跑（GitHub Action 會自動跑，見 .github/workflows）
# ─────────────────────────────────────────────────────────────
import importlib.util
import json
import os
from urllib.parse import quote

ROOT = os.path.dirname(os.path.abspath(__file__))
ARTICLES_PATH = os.path.join(ROOT, "articles.json")
OUT_PATH = os.path.join(ROOT, "sitemap.xml")

BASE = "https://www.guoguo.tw/guide/"

# 沿用 build-tags.py 的 tag_slug() 與 THRESHOLD，確保 sitemap 的標籤網址 slug 規則、
# 收錄門檻與實際產出的標籤頁完全一致（檔名有連字號 → 用 importlib 載入）。
_spec = importlib.util.spec_from_file_location(
    "build_tags", os.path.join(ROOT, "build-tags.py")
)
_bt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bt)
tag_slug = _bt.tag_slug
THRESHOLD = _bt.THRESHOLD


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;"))


def url_entry(loc, lastmod, changefreq, priority):
    lines = ["  <url>", f"    <loc>{esc(loc)}</loc>"]
    if lastmod:
        lines.append(f"    <lastmod>{esc(lastmod)}</lastmod>")
    lines.append(f"    <changefreq>{changefreq}</changefreq>")
    lines.append(f"    <priority>{priority}</priority>")
    lines.append("  </url>")
    return "\n".join(lines)


def main():
    with open(ARTICLES_PATH, encoding="utf-8") as f:
        articles = json.load(f)

    dates = [a.get("date") for a in articles if a.get("date")]
    home_lastmod = max(dates) if dates else ""

    entries = [url_entry(BASE, home_lastmod, "weekly", "1.0")]
    for a in articles:
        url = a.get("url")
        if not url:
            continue
        entries.append(url_entry(BASE + url, a.get("date", ""), "monthly", "0.8"))

    # 標籤頁：只收「文章數 ≥ THRESHOLD」的標籤（防薄內容，與 build-tags.py 的 noindex 門檻一致）。
    # lastmod 取該標籤旗下文章的最新日期。網址對 slug 做 quote（中日文 → %XX）。
    tag_dates = {}
    for a in articles:
        for t in (a.get("tags") or []):
            if not t:
                continue
            tag_dates.setdefault(t, []).append(a.get("date", ""))
    tag_count = 0
    for t in sorted(tag_dates.keys()):
        dates_t = [d for d in tag_dates[t] if d]
        if len(tag_dates[t]) < THRESHOLD:
            continue
        loc = BASE + "tag/" + quote(tag_slug(t)) + "/"
        entries.append(url_entry(loc, max(dates_t) if dates_t else "", "weekly", "0.7"))
        tag_count += 1

    doc = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(doc)
    print(
        "✅ 產生 sitemap.xml：{0} 筆（首頁 + {1} 篇文章 + {2} 個標籤頁，"
        "≥{3} 篇的標籤才收）。".format(len(entries), len(articles), tag_count, THRESHOLD)
    )


if __name__ == "__main__":
    main()
