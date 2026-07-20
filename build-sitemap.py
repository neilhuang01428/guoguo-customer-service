#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────
# build-sitemap.py — 從 articles.json 產生 sitemap.xml（導外版）
#   來源：articles.json（文章清單）
#   產出：sitemap.xml（覆寫）；首頁 + 每篇文章一筆
#   網址：https://www.guoguo.tw/guide/ + 每篇 url（相對路徑）
#   用法：articles.json 有異動就重跑（GitHub Action 會自動跑，見 .github/workflows）
# ─────────────────────────────────────────────────────────────
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
ARTICLES_PATH = os.path.join(ROOT, "articles.json")
OUT_PATH = os.path.join(ROOT, "sitemap.xml")

BASE = "https://www.guoguo.tw/guide/"


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

    doc = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(doc)
    print("✅ 產生 sitemap.xml：{0} 筆（首頁 + {1} 篇文章）。".format(len(entries), len(articles)))


if __name__ == "__main__":
    main()
