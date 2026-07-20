#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────
# build-tags.py — 讀 articles.json → 依 tag 分組 → 為每個 tag 產一個
#   靜態標籤落地頁 tag/<tag_slug>/index.html。
#
#   一份檔、雙版共用（靠「相對連結」讓導外／中性都對）：
#     導外： www.guoguo.tw/guide/tag/<slug>/   （GitHub Pages 直吐 + Worker 注 chrome）
#     中性： <中性網域>/tag/<slug>/            （build-neutral.sh 複製進 dist，天生乾淨）
#   頁內連結一律相對：
#     連某篇文章  → ../../<article-slug>/   （/guide/tag/X/→/guide/Y/；中性 /tag/X/→/Y/）
#     連另一標籤  → ../<other-slug>/         （同層 tag/ 底下換一個資料夾）
#     連教學首頁  → ../../                    （回教學總覽）
#
#   視覺與卡片沿用 build-homepage.py（import 其 CSS / render_card / 色票 / logo），
#   不重畫。卡片一律 emoji 方塊（card_mode="emoji"）：標籤頁是「一份檔雙版共用」，
#   而中性版 build 會砍掉 assets/og → 若引用首圖會在中性版 404，故一律 emoji（零外部資源）。
#
#   零導外：原始檔不含任何 guoguo 導流資訊（無 guoguo.tw／電話／LINE／賣場連結）。
#           導外版的賣場頁尾由 Worker 注入到 <main> 尾端；中性版保持乾淨。
#
#   防薄內容：文章數 < THRESHOLD 的標籤，<head> 加 noindex（頁仍生、連結仍有效，
#             只是先不被索引）；之後同標籤文章變多會自動變可索引。
#
#   用法：articles.json 有異動後重跑：python3 build-tags.py
#         （build-all.sh / build-neutral.sh 也會自動跑這一支）
# ─────────────────────────────────────────────────────────────
import importlib.util
import os
import re
import shutil
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ 的上一層＝repo 根
TAG_DIR = os.path.join(ROOT, "tag")

# 文章數 < THRESHOLD 的標籤頁：加 noindex（防薄內容）。
THRESHOLD = 2

# ── 沿用 build-homepage.py 的視覺與卡片（import，不重畫）──────────────
#    檔名有連字號不能直接 import，改用 importlib 從檔案路徑載入。
#    build-homepage.py 的 main() 有 __main__ 守門，import 不會產生任何檔。
_spec = importlib.util.spec_from_file_location(
    "build_homepage",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "build-homepage.py"),  # 同在 scripts/
)
bh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bh)


def tag_slug(t):
    """標籤 → 網址／資料夾用 slug：
       strip → 小寫（只影響 ASCII）→ 空白換成 '-' → 中日文原樣保留。
       例：'防詐騙'→'防詐騙'、'App 下載'→'app-下載'、'Windows 用戶'→'windows-用戶'、
           'Apple Pencil'→'apple-pencil'。"""
    return re.sub(r"\s+", "-", t.strip().lower())


# ── 標籤頁專用的補充 CSS（接在 build-homepage.py 的基底 CSS 之後，
#    只補基底沒有的元素：麵包屑、篇數 pill、相關主題前綴、把 emoji 卡放大成填滿卡頂的色塊）──
TAG_EXTRA_CSS = r"""
/* ── 麵包屑（相對連結；沿用 mockup A 的簡潔樣式）── */
.crumb { font-family: var(--mono); font-size: .74rem; color: var(--muted); margin: 30px 4px 0; }
.crumb a { color: var(--navy); text-decoration: none; }
.crumb a:hover { text-decoration: underline; }
.crumb .sep { margin: 0 8px; color: var(--muted); }
.crumb .here { color: var(--ink); font-weight: 700; }

/* ── hero：標題 + 篇數 pill ── */
.hero h1 { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.hero .cnt-pill { font-family: var(--mono); font-size: .78rem; font-weight: 700; color: var(--navy); background: var(--navy-bg); padding: 6px 14px; border-radius: 999px; letter-spacing: .03em; }

/* ── 相關主題 chips（連 ../<slug>/；純連結，無 on 狀態）── */
.filters { align-items: center; }
.filters .flbl { font-family: var(--mono); font-size: .68rem; color: var(--muted); margin-right: 2px; }
.filters a.chip { text-decoration: none; }

/* ── 全部教學小標（沿用 h2.glabel，補一點上緣間距）── */
main h2.glabel { margin: 34px 4px 4px; }

/* ── 標籤頁卡片一律 emoji：把 .ic 放大成填滿卡頂的色塊（對齊 mockup A，取代 build-homepage 的 46px 小方塊）── */
a.g .ic { width: auto; height: auto; aspect-ratio: 1.9/1; border-radius: 10px; background: var(--cbg); color: var(--c); display: grid; place-items: center; font-size: 3rem; margin-bottom: 14px; }
"""

# ── 標籤頁外殼（零導外：masthead 只有 logo/品牌字，無任何連結；
#    <main> 供 Worker 在尾端注入賣場頁尾；中性版則到卡片為止，乾淨結束）──
TAG_PAGE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{title}</title>
<meta name="description" content="{desc}" />
{robots}<style>{css}</style>
</head>
<body data-pagefind-ignore>
<div class="wrap">
  <header class="mast">
    <div class="card-head">
      <div class="top">
        <div class="logo">
          {logo}
          <div><div class="wm">果果國際</div><div class="wm-sub">GUOGUO INTERNATIONAL</div></div>
        </div>
        <div class="tagline"><b>台灣最專業的 Apple 福利機供應商</b><br>iPad 選購，都交給我們</div>
      </div>
    </div>
  </header>

  <nav class="crumb"><a href="../../">iPad 使用教學</a><span class="sep">›</span><span>主題</span><span class="sep">›</span><span class="here">{tag_name}</span></nav>

  <main>
    <div class="hero">
      <div class="kicker">主題標籤</div>
      <h1>{tag_name}<span class="cnt-pill">共 {count} 篇</span></h1>
      <p class="sub">{sub}</p>
{filters}
    </div>

    <h2 class="glabel">{tag_name} · 全部教學</h2>
    <div class="grid2">
{cards}
    </div>
  </main>

  <div class="copy">© 果果國際 GUOGUO INTERNATIONAL</div>
</div>
</body>
</html>
"""


def relink_article(a):
    """回傳一份 article 副本，把 url 改成相對路徑 ../../articles/<slug>/
       （a.url 已含 articles/ 前綴），讓 render_card 產出的連結在
       /guide/tag/X/ 與 /tag/X/ 兩處都對（→ /guide/articles/Y/、/articles/Y/）。"""
    a2 = dict(a)
    a2["url"] = "../../" + (a.get("url", "") or "")
    return a2


def build_filters(tag, related, counts):
    """相關主題 chips：連同層其他標籤 ../<slug>/。無相關標籤則整塊省略。"""
    if not related:
        return ""
    chips = []
    for t in related:
        href = "../{0}/".format(quote(tag_slug(t)))
        chips.append(
            '      <a class="chip" href="{href}">{name}<span class="cnt">({n})</span></a>'.format(
                href=bh.esc(href), name=bh.esc(t), n=counts[t]
            )
        )
    return (
        '      <div class="filters">\n'
        '        <span class="flbl">相關主題：</span>\n'
        + "\n".join(chips)
        + "\n      </div>"
    )


def build_page(tag, articles, colors, related, counts):
    count = len(articles)
    # 卡片：沿用 render_card；一律 emoji（零外部資源，中性版也不 404）；連結相對 ../../<slug>/
    cards = "\n".join(
        bh.render_card(relink_article(a), colors, card_mode="emoji") for a in articles
    )
    sub = "跟「{0}」有關的教學都收在這裡，果果一篇篇整理好，你想看哪篇就點哪篇。".format(tag)
    robots = ""
    if count < THRESHOLD:
        robots = '<meta name="robots" content="noindex" />\n'
    css = bh.CSS.replace("__SHOP_CSS__", "") + TAG_EXTRA_CSS
    return TAG_PAGE.format(
        title=bh.esc("{0}｜iPad 使用教學 · 果果國際".format(tag)),
        desc=bh.esc("跟「{0}」有關的 iPad 使用教學，共 {1} 篇，果果整理好方便你一次看。".format(tag, count)),
        robots=robots,
        css=css,
        logo=bh.LOGO_SVG,
        tag_name=bh.esc(tag),
        count=count,
        sub=bh.esc(sub),
        filters=build_filters(tag, related, counts),
        cards=cards,
    )


def main():
    articles = bh.load_articles()
    colors = bh.category_colors(articles)

    # tag → 該標籤的文章清單（保序：先出現的文章排前面；再依日期新→舊排）
    tag_to_articles = {}
    for a in articles:
        for t in (a.get("tags") or []):
            if not t:
                continue
            tag_to_articles.setdefault(t, []).append(a)
    for t in tag_to_articles:
        tag_to_articles[t].sort(key=lambda a: a.get("date", ""), reverse=True)

    counts = {t: len(v) for t, v in tag_to_articles.items()}

    # 相關主題 = 與本標籤「同一篇文章上一起出現」的其他標籤，依全站篇數多→少、再字序
    def related_of(tag):
        rel = set()
        for a in tag_to_articles[tag]:
            for t in (a.get("tags") or []):
                if t and t != tag:
                    rel.add(t)
        return sorted(rel, key=lambda t: (-counts[t], t))

    # 砍掉重建 tag/（每次全量重生，idempotent）
    if os.path.isdir(TAG_DIR):
        shutil.rmtree(TAG_DIR)
    os.makedirs(TAG_DIR, exist_ok=True)

    total = 0
    noindexed = 0
    for tag in sorted(tag_to_articles.keys()):
        slug = tag_slug(tag)
        arts = tag_to_articles[tag]
        page = build_page(tag, arts, colors, related_of(tag), counts)
        d = os.path.join(TAG_DIR, slug)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
            f.write(page)
        total += 1
        if len(arts) < THRESHOLD:
            noindexed += 1

    print(
        "✅ 產生 {0} 個標籤頁（tag/<slug>/index.html）；其中 {1} 個 < {2} 篇 → 加 noindex。".format(
            total, noindexed, THRESHOLD
        )
    )


if __name__ == "__main__":
    main()
